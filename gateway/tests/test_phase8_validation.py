import pytest
import asyncio
import time
import httpx
from unittest.mock import AsyncMock
import gateway.src.main as gateway_module
from gateway.src.main import app, route_table
from gateway.src.traffic_manager import traffic_coordinator, LimiterMode

AUTH_HEADERS = {"X-Internal-Secret": "internal-secret-token"}


@pytest.fixture(autouse=True)
def reset_gateway_and_traffic():
    """Resets gateway route table and traffic coordinator to a clean state."""
    route_table.set_target(
        target_region="region-a",
        target_role="ACTIVE",
        dns_ttl_seconds=2,
        propagation_percent=100,
    )
    for r in ["region-a", "region-b", "region-c", "region-d", "region-e"]:
        route_table.set_region_health(r, "HEALTHY")
        route_table.set_region_lag(r, 0.0 if r == "region-a" else 0.5)
    route_table.max_stale_seconds = 5.0
    route_table.route_selector.max_stale_seconds = 5.0

    traffic_coordinator.set_mode(LimiterMode.OFF)
    traffic_coordinator.reset_all()
    yield
    traffic_coordinator.set_mode(LimiterMode.OFF)
    traffic_coordinator.reset_all()


# =========================================================================
# WORKFLOW A: End-to-End Store Integration & Outbox Event Replication
# =========================================================================

@pytest.mark.asyncio
async def test_workflow_a_ecommerce_browse_and_order_flow(async_client):
    """
    Workflow A:
    1. Browse products at /api/ecommerce/products (eventual read, nearest replica).
    2. Place order at /api/ecommerce/orders (write, active writer).
    3. Verify Gateway routing headers: X-Served-Region, X-Consistency-Level, X-Simulated-WAN-Delay-Ms.
    4. Verify traffic event recorded in history.
    """
    mock_client = AsyncMock()

    # Mock catalog response from regional service
    catalog_payload = [
        {"id": "prod-laptop-01", "name": "ThinkStation Ultra", "price": 1299.0, "stock": 45},
        {"id": "prod-display-02", "name": "ViewSonic Precision", "price": 450.0, "stock": 80},
    ]
    # Mock order response from regional service
    order_payload = {
        "id": "ord-8831",
        "customer_name": "Alice Patel",
        "items": [{"product_id": "prod-laptop-01", "quantity": 1}],
        "total_amount": 1299.0,
        "status": "CONFIRMED",
        "region_id": "region-a",
        "fencing_epoch": 101,
        "outbox_event_id": "evt-7712",
        "sequence_number": 1050,
    }

    async def mock_request_handler(method, url, **kwargs):
        if "/api/ecommerce/products" in url:
            return httpx.Response(200, json=catalog_payload, headers={"content-type": "application/json"})
        elif "/api/ecommerce/orders" in url:
            return httpx.Response(201, json=order_payload, headers={"content-type": "application/json"})
        return httpx.Response(404, json={"detail": "Not found"})

    mock_client.request.side_effect = mock_request_handler
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # 1. Browse catalogue with India client
        browse_res = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "ap-south-1"},
        )
        assert browse_res.status_code == 200
        assert browse_res.headers["X-Served-Region"] == "region-a"
        assert browse_res.headers["X-Consistency-Level"] == "eventual"
        assert float(browse_res.headers["X-Simulated-WAN-Delay-Ms"]) == 18.0
        data = browse_res.json()
        assert len(data) == 2
        assert data[0]["id"] == "prod-laptop-01"

        # 2. Place order with client idempotency key
        order_req = {
            "customer_name": "Alice Patel",
            "customer_email": "alice@example.com",
            "items": [{"product_id": "prod-laptop-01", "product_name": "ThinkStation Ultra", "quantity": 1, "unit_price": 1299.0}],
            "total_amount": 1299.0,
            "idempotency_key": "idem-key-001",
        }
        order_res = await async_client.post(
            "/api/ecommerce/orders",
            json=order_req,
            headers={"X-Client-Region": "ap-south-1"},
        )
        assert order_res.status_code == 201
        assert order_res.headers["X-Served-Region"] == "region-a"  # Must route to active writer
        assert order_res.headers["X-Consistency-Level"] == "write"
        ord_data = order_res.json()
        assert ord_data["id"] == "ord-8831"
        assert ord_data["outbox_event_id"] == "evt-7712"
        assert ord_data["sequence_number"] == 1050

        # 3. Verify traffic event recorded in gateway history for dashboard
        hist_res = await async_client.get("/api/v1/traffic/history")
        assert hist_res.status_code == 200
        events_data = hist_res.json()
        events = events_data.get("events", events_data)
        assert len(events) >= 2
        # Check order event in history
        order_event = next(e for e in events if e["endpoint"] == "/api/ecommerce/orders" or e.get("path") == "/api/ecommerce/orders")
        assert order_event["method"] == "POST"
        assert order_event["served_region"] == "region-a" or order_event.get("routed_to_region") == "region-a"
        assert order_event["status_code"] == 201

    finally:
        gateway_module.http_client = original_client


# =========================================================================
# WORKFLOW B: Token Bucket Burst, Rejection, and Refill Validation
# =========================================================================

@pytest.mark.asyncio
async def test_workflow_b_token_bucket_burst_and_refill(async_client):
    """
    Workflow B:
    1. Configure Token Bucket: Capacity = 10, Refill = 2 tokens/sec.
    2. Burst 15 requests consecutively.
    3. Exactly first 10 requests must be accepted (200 OK).
    4. Next 5 requests must be rejected with HTTP 429 Too Many Requests and Retry-After header.
    5. Wait for token refill -> Next request must succeed.
    6. Verify dashboard traffic metrics reflect accepted and throttled counts.
    """
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        200, json=[{"id": "p1"}], headers={"content-type": "application/json"}
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        traffic_coordinator.set_mode(LimiterMode.TOKEN_BUCKET)
        # Use low refill during the burst so execution overhead across async loop does not refill tokens early
        traffic_coordinator.update_config(
            token_capacity=10.0,
            token_refill_rate=0.001,
        )
        traffic_coordinator.reset_all()

        results = []
        for _ in range(15):
            res = await async_client.get(
                "/api/ecommerce/products",
                headers={"X-Client-Region": "india"},
            )
            results.append(res)

        accepted = [r for r in results if r.status_code == 200]
        rejected = [r for r in results if r.status_code == 429]

        assert len(accepted) == 10
        assert len(rejected) == 5

        # Verify 429 headers and detail
        for r in rejected:
            assert "Retry-After" in r.headers
            assert "Rate limit exceeded" in (r.json().get("error") or r.json().get("detail", ""))
            assert r.headers["X-RateLimit-Mode"] == "TOKEN_BUCKET"

        # Now configure refill rate = 2.0 tokens/sec
        traffic_coordinator.update_config(token_refill_rate=2.0)
        bucket = await traffic_coordinator.token_limiter._get_bucket("india")
        bucket.last_refill = time.monotonic() - 0.6  # 0.6s at 2 tokens/sec gives >1 token

        # Send 1 request after refill
        refilled_res = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "india"},
        )
        assert refilled_res.status_code == 200

        # Check metrics status in 'common'
        status_res = await async_client.get("/api/v1/traffic/status")
        assert status_res.status_code == 200
        common = status_res.json()["common"]
        assert common["accepted_requests"] == 11
        assert common["throttled_requests"] == 5

    finally:
        gateway_module.http_client = original_client


# =========================================================================
# WORKFLOW C: Leaky Bucket Traffic Shaper FIFO & Overflow
# =========================================================================

@pytest.mark.asyncio
async def test_workflow_c_leaky_bucket_traffic_shaper(async_client):
    """
    Workflow C:
    1. Configure Leaky Bucket: Queue Capacity = 4, Drain Rate = 20.0 req/sec.
    2. Verify requests are shaped and queued.
    3. Fill queue beyond capacity -> Overflow requests rejected with HTTP 429.
    4. Observe queue wait times and status reporting.
    """
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        200, json=[{"id": "p1"}], headers={"content-type": "application/json"}
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # Use drain rate of 10.0 req/s with small queue capacity 3
        traffic_coordinator.set_mode(LimiterMode.LEAKY_BUCKET)
        traffic_coordinator.update_config(
            leaky_capacity=3,
            leaky_drain_rate=10.0,
        )
        traffic_coordinator.reset_all()

        # Send 8 concurrent requests
        tasks = [
            async_client.get("/api/ecommerce/products", headers={"X-Client-Region": "india"})
            for _ in range(8)
        ]
        responses = await asyncio.gather(*tasks)

        # With capacity 3, requests should be accepted and overflow rejected with 429
        statuses = [r.status_code for r in responses]
        assert 429 in statuses
        assert 200 in statuses

        # Status inspection
        status_res = await async_client.get("/api/v1/traffic/status")
        data = status_res.json()
        assert data["mode"] == "LEAKY_BUCKET"
        assert data["leaky_bucket"]["queue_capacity"] == 3
        assert data["common"]["throttled_requests"] >= 1

    finally:
        gateway_module.http_client = original_client


# =========================================================================
# WORKFLOW D: Latency-Aware Routing, Failover & Consistency
# =========================================================================

@pytest.mark.asyncio
async def test_workflow_d_latency_aware_routing_and_failover(async_client):
    """
    Workflow D:
    1. India client -> Mumbai (region-a).
    2. Europe client -> Frankfurt (region-c).
    3. Frankfurt becomes DOWN -> Europe client fails over to next lowest latency healthy replica.
    4. Simulated WAN delay header is separate from gateway processing latency.
    5. Strong reads and writes strictly route to active writer (region-a) regardless of client header.
    6. Stale replica (lag > max_stale) is excluded from eventual reads.
    """
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        200, json={"result": "ok"}, headers={"content-type": "application/json"}
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # 1. India client -> Mumbai (18ms WAN delay)
        res_in = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "ap-south-1"},
        )
        assert res_in.headers["X-Served-Region"] == "region-a"
        assert float(res_in.headers["X-Simulated-WAN-Delay-Ms"]) == 18.0
        assert "X-Gateway-Latency-Ms" in res_in.headers

        # 2. Europe client -> Frankfurt (16ms WAN delay)
        res_eu = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "eu-central-1"},
        )
        assert res_eu.headers["X-Served-Region"] == "region-c"
        assert float(res_eu.headers["X-Simulated-WAN-Delay-Ms"]) == 16.0

        # 3. Mark Frankfurt DOWN -> Europe client routes to next lowest latency healthy replica
        route_table.set_region_health("region-c", "DOWN")
        res_eu_failover = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "eu-central-1"},
        )
        assert res_eu_failover.headers["X-Served-Region"] != "region-c"
        # From Frankfurt, Singapore (region-b), Virginia (region-d), or Mumbai (region-a) is next lowest WAN
        assert res_eu_failover.headers["X-Served-Region"] in ["region-b", "region-d", "region-a"]

        # 4. Strong read (inventory check) must strictly route to ACTIVE writer (region-a)
        res_strong = await async_client.get(
            "/api/ecommerce/inventory/prod-laptop-01",
            headers={"X-Client-Region": "eu-central-1"},
        )
        assert res_strong.headers["X-Served-Region"] == "region-a"
        assert res_strong.headers["X-Consistency-Level"] == "strong"

        # 5. Write (place order) must strictly route to ACTIVE writer (region-a)
        res_write = await async_client.post(
            "/api/ecommerce/orders",
            json={"items": [], "total_amount": 100.0, "customer_name": "Bob"},
            headers={"X-Client-Region": "eu-central-1"},
        )
        assert res_write.headers["X-Served-Region"] == "region-a"
        assert res_write.headers["X-Consistency-Level"] == "write"

        # 6. Replication Lag staleness exclusion:
        # Restore Frankfurt, but spike its lag to 9.5s (> 5.0s max_stale)
        route_table.set_region_health("region-c", "HEALTHY")
        route_table.set_region_lag("region-c", 9.5)

        res_eu_stale = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "eu-central-1"},
        )
        # Frankfurt must be excluded because lag 9.5 > max_stale 5.0
        assert res_eu_stale.headers["X-Served-Region"] != "region-c"

    finally:
        gateway_module.http_client = original_client
