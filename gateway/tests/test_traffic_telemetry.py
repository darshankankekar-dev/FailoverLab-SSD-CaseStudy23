import asyncio
import json
import pytest
import httpx
from unittest.mock import AsyncMock
from fastapi.responses import StreamingResponse

import gateway.src.main as gateway_module
from gateway.src.main import app, route_table
from gateway.src.traffic_manager import traffic_coordinator, LimiterMode
from gateway.src.telemetry import telemetry_collector, normalize_endpoint, detect_traffic_source
from gateway.src.metrics import gateway_metrics


@pytest.fixture(autouse=True)
async def reset_telemetry_state():
    """Resets routing, traffic limiter, metrics, and telemetry collector before each test."""
    route_table.set_target(
        target_region="region-a",
        target_role="ACTIVE",
        dns_ttl_seconds=2,
        propagation_percent=100,
    )
    for r in ["region-a", "region-b", "region-c", "region-d", "region-e"]:
        route_table.set_region_health(r, "HEALTHY")
        route_table.set_region_lag(r, 0.0 if r == "region-a" else 0.8)

    traffic_coordinator.set_mode(LimiterMode.OFF)
    traffic_coordinator.reset_all()
    telemetry_collector.reset()
    gateway_metrics.reset()

    yield

    traffic_coordinator.reset_all()
    telemetry_collector.reset()
    gateway_metrics.reset()


# =========================================================================
# Test 1: Request-body byte measurement
# =========================================================================
@pytest.mark.asyncio
async def test_request_body_byte_measurement(async_client):
    """
    Verifies that client request payload bytes are accurately measured from incoming
    request bodies without Content-Length estimation, and never persisted.
    """
    payload_dict = {
        "items": [{"product_id": "prod-laptop-01", "quantity": 2, "unit_price": 999.0}],
        "customer_name": "Alice Tester",
        "customer_email": "alice@example.com",
        "shipping_address": "123 Distributed Systems Way",
        "client_region": "ap-south-1",
    }
    payload_bytes = json.dumps(payload_dict).encode("utf-8")
    expected_ingress_bytes = len(payload_bytes)

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        status_code=201,
        content=b'{"order_id": "ord-test-01", "status": "CONFIRMED"}',
        headers={"content-type": "application/json"},
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        res = await async_client.post(
            "/api/ecommerce/orders",
            content=payload_bytes,
            headers={"Content-Type": "application/json", "X-Client-Region": "ap-south-1"},
        )
        assert res.status_code == 201

        # Check telemetry collector cumulative ingress
        assert telemetry_collector.cumulative_ingress_bytes == expected_ingress_bytes

        # Check traffic events history
        events = traffic_coordinator.get_traffic_history(limit=10)
        assert len(events) >= 1
        last_evt = events[-1]
        assert last_evt["request_payload_bytes"] == expected_ingress_bytes
        assert last_evt["endpoint"] == "/api/ecommerce/orders"
        assert last_evt["request_category"] == "orders"
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 2: Response-body byte measurement
# =========================================================================
@pytest.mark.asyncio
async def test_response_body_byte_measurement(async_client):
    """
    Verifies that client response payload bytes returned by the Gateway are accurately
    measured and recorded in telemetry.
    """
    mock_catalog = [
        {"id": "prod-1", "name": "Mechanical Keyboard", "price": 149.0},
        {"id": "prod-2", "name": "USB-C Hub", "price": 49.0},
    ]
    catalog_bytes = json.dumps(mock_catalog).encode("utf-8")
    expected_egress_bytes = len(catalog_bytes)

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        status_code=200,
        content=catalog_bytes,
        headers={"content-type": "application/json"},
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        res = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "ap-south-1"},
        )
        assert res.status_code == 200
        assert len(res.content) == expected_egress_bytes

        # Telemetry collector records egress bytes
        assert telemetry_collector.cumulative_egress_bytes == expected_egress_bytes

        # Event stream records egress bytes
        events = traffic_coordinator.get_traffic_history(limit=5)
        assert len(events) >= 1
        assert events[-1]["response_payload_bytes"] == expected_egress_bytes
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 3: Empty request and response bodies
# =========================================================================
@pytest.mark.asyncio
async def test_empty_request_and_response_bodies(async_client):
    """
    Verifies that requests with no body (e.g. GET) and responses with no body (e.g. 204 No Content)
    are handled gracefully with 0 bytes recorded, without division by zero or errors.
    """
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        status_code=204,
        content=b"",
        headers={"content-type": "application/json"},
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        res = await async_client.get("/api/ecommerce/products/prod-empty")
        assert res.status_code == 204
        assert len(res.content) == 0

        # Check that 0 bytes were counted
        assert telemetry_collector.cumulative_ingress_bytes == 0
        assert telemetry_collector.cumulative_egress_bytes == 0
        assert telemetry_collector.total_requests == 1
        assert telemetry_collector.status_2xx == 1

        events = traffic_coordinator.get_traffic_history(limit=5)
        assert events[-1]["request_payload_bytes"] == 0
        assert events[-1]["response_payload_bytes"] == 0
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 4: Multiple streamed response chunks
# =========================================================================
@pytest.mark.asyncio
async def test_multiple_streamed_response_chunks(async_client):
    """
    Verifies that chunked/streamed responses are measured chunk-by-chunk at the ASGI layer
    without consuming or buffering the stream, accumulating exact total bytes.
    """
    chunks = [b"chunk-alpha-12345;", b"chunk-beta-67890;", b"chunk-gamma-final"]
    expected_total_bytes = sum(len(c) for c in chunks)

    async def sample_generator():
        for c in chunks:
            yield c

    @app.get("/test/streaming/chunks")
    async def temp_streaming():
        return StreamingResponse(sample_generator(), media_type="text/plain")

    res = await async_client.get("/test/streaming/chunks")
    assert res.status_code == 200
    assert res.content == b"".join(chunks)
    assert len(res.content) == expected_total_bytes

    # Telemetry collector must record the exact accumulated chunk bytes
    assert telemetry_collector.cumulative_egress_bytes == expected_total_bytes


# =========================================================================
# Test 5: Upstream request/response byte measurement
# =========================================================================
@pytest.mark.asyncio
async def test_upstream_request_and_response_byte_measurement(async_client):
    """
    Verifies that upstream proxy traffic to the regional service is measured separately
    from client-facing traffic: request bytes sent to region, response bytes received.
    """
    req_body = b'{"record_key": "inventory-item-42", "val": 100}'
    resp_body = b'{"status": "saved", "version": 3}'

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        status_code=200,
        content=resp_body,
        headers={"content-type": "application/json"},
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        res = await async_client.post(
            "/api/records",
            content=req_body,
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 200

        # Verify upstream regional accounting for region-a
        reg_a = telemetry_collector.regions["region-a"]
        assert reg_a.requests_total == 1
        assert reg_a.request_payload_bytes == len(req_body)
        assert reg_a.response_payload_bytes == len(resp_body)
        assert reg_a.status_2xx == 1

        # Other regions must remain zero
        for r_id in ["region-b", "region-c", "region-d", "region-e"]:
            assert telemetry_collector.regions[r_id].requests_total == 0
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 6: 429 Rate-limited responses
# =========================================================================
@pytest.mark.asyncio
async def test_429_rate_limited_responses(async_client):
    """
    Verifies that HTTP 429 rate-limited requests:
    - Measure incoming request payload bytes (even if rejected).
    - Measure outgoing 429 JSON response payload bytes.
    - Increment rate_limited_429 counter.
    - Do NOT make an upstream request (upstream counters remain 0).
    """
    traffic_coordinator.set_mode(LimiterMode.TOKEN_BUCKET)
    traffic_coordinator.update_config(token_capacity=1.0, token_refill_rate=0.01)

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(200, json={"items": []})
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # First request consumes 1 token
        r1 = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "test-ratelimit-user"})
        assert r1.status_code == 200

        # Second request with a 30-byte POST body is throttled
        post_body = b'{"order": "throttle-me-test"}'
        r2 = await async_client.post(
            "/api/ecommerce/orders",
            content=post_body,
            headers={"X-Client-ID": "test-ratelimit-user", "Content-Type": "application/json"},
        )
        assert r2.status_code == 429
        assert "Retry-After" in r2.headers

        # Verify rate_limited_429 counter incremented
        assert telemetry_collector.rate_limited_429 == 1

        # Upstream regional requests: only 1 was sent (the first GET), 0 for the 429 request!
        assert telemetry_collector.regions["region-a"].requests_total == 1

        # Event stream contains 429 with request and response payload bytes
        events = traffic_coordinator.get_traffic_history(limit=5)
        evt_429 = [e for e in events if e["status_code"] == 429][0]
        assert evt_429["rate_limiter_decision"] == "rejected"
        assert evt_429["request_payload_bytes"] == len(post_body)
        assert evt_429["response_payload_bytes"] > 0
        assert evt_429["upstream_region"] is None
        assert evt_429["upstream_request_bytes"] == 0
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 7: 5xx and upstream error handling
# =========================================================================
@pytest.mark.asyncio
async def test_5xx_and_upstream_error_handling(async_client):
    """
    Verifies that upstream failures (ConnectError, TimeoutException) are tracked
    in regional error counters without crashing the gateway.
    """
    mock_client = AsyncMock()
    original_client = gateway_module.http_client

    # 1. Test connect failure (503)
    mock_client.request.side_effect = httpx.ConnectError("Connection refused by region-a")
    gateway_module.http_client = mock_client

    try:
        res_503 = await async_client.get("/api/ecommerce/products")
        assert res_503.status_code == 503
        reg_a = telemetry_collector.regions["region-a"]
        assert reg_a.failed_requests >= 1

        # 2. Test timeout (504)
        mock_client.request.side_effect = httpx.TimeoutException("Read timed out from region-a")
        res_504 = await async_client.get("/api/ecommerce/products")
        assert res_504.status_code == 504
        assert reg_a.timeouts >= 1

        # Verify 5xx cumulative counter in customer-facing telemetry
        assert telemetry_collector.status_5xx >= 2
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 8: Region-specific traffic accounting
# =========================================================================
@pytest.mark.asyncio
async def test_region_specific_traffic_accounting(async_client):
    """
    Verifies that traffic routed to different regions is accounted strictly in each
    region's respective counters without cross-region pollution.
    """
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(200, content=b'{"ok": true}')
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # Route 1: Target region-a
        route_table.set_target("region-a")
        await async_client.post("/api/records", json={"k": "1"})
        await async_client.post("/api/records", json={"k": "2"})

        # Route 2: Shift target to region-b
        route_table.set_target("region-b")
        await async_client.post("/api/records", json={"k": "3"})
        await async_client.post("/api/records", json={"k": "4"})
        await async_client.post("/api/records", json={"k": "5"})

        # Check regional breakdown
        assert telemetry_collector.regions["region-a"].requests_total == 2
        assert telemetry_collector.regions["region-b"].requests_total == 3
        assert telemetry_collector.regions["region-c"].requests_total == 0
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 9: Idempotency replay prevents double counting
# =========================================================================
@pytest.mark.asyncio
async def test_idempotency_replay_prevents_double_counting(async_client):
    """
    Verifies that when an Idempotency-Key retry is served from cache:
    - Upstream request is NOT executed.
    - Upstream payload bytes and request count for the region DO NOT increase.
    - Customer-facing request count is incremented for both requests.
    - No double-counting occurs.
    """
    order_payload = json.dumps({"product_id": "laptop-1", "quantity": 1}).encode()
    order_response = json.dumps({"order_id": "ord-idemp-99", "status": "CONFIRMED"}).encode()

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        status_code=201,
        content=order_response,
        headers={"content-type": "application/json"},
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # First request (mutation execution)
        res1 = await async_client.post(
            "/api/ecommerce/orders",
            content=order_payload,
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": "idemp-unique-token-999",
                "X-Client-Region": "ap-south-1",
            },
        )
        assert res1.status_code == 201
        assert res1.headers.get("X-Idempotency-Replay") is None

        # Upstream called exactly 1 time
        assert telemetry_collector.regions["region-a"].requests_total == 1
        upstream_bytes_initial = telemetry_collector.regions["region-a"].request_payload_bytes
        assert upstream_bytes_initial == len(order_payload)

        # Second request (idempotent replay)
        res2 = await async_client.post(
            "/api/ecommerce/orders",
            content=order_payload,
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": "idemp-unique-token-999",
                "X-Client-Region": "ap-south-1",
            },
        )
        assert res2.status_code == 201
        assert res2.headers.get("X-Idempotency-Replay") == "true"

        # Upstream regional counters MUST NOT HAVE CHANGED!
        assert telemetry_collector.regions["region-a"].requests_total == 1
        assert telemetry_collector.regions["region-a"].request_payload_bytes == upstream_bytes_initial

        # Customer-facing total requests is 2
        assert telemetry_collector.total_requests == 2

        # Traffic event for replay shows is_replay=True and rate_limiter_decision="idempotent_replay"
        events = traffic_coordinator.get_traffic_history(limit=5)
        assert events[-1]["is_replay"] is True
        assert events[-1]["rate_limiter_decision"] == "idempotent_replay"
        assert events[-1]["upstream_request_bytes"] == 0
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 10: SSE Event Payload Telemetry
# =========================================================================
@pytest.mark.asyncio
async def test_sse_event_payload_telemetry(async_client):
    """
    Verifies that the Gateway SSE traffic event stream emits rich payload telemetry:
    request_payload_bytes, response_payload_bytes, client_region, served_region,
    request_category, status_code, measured duration, rate_limiter_decision.
    """
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        200,
        content=b'[{"id":"p1"}]',
        headers={"content-type": "application/json"},
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        res = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "eu-central-1", "X-Request-ID": "test-sse-payload-1"},
        )
        assert res.status_code == 200

        events = traffic_coordinator.get_traffic_history(limit=5)
        assert len(events) >= 1
        evt = events[-1]

        assert "request_payload_bytes" in evt
        assert "response_payload_bytes" in evt
        assert evt["response_payload_bytes"] == len(b'[{"id":"p1"}]')
        assert evt["client_region"] == "eu-central-1"
        assert evt["served_region"] in ("region-c", "region-a")
        assert evt["request_category"] == "catalog"
        assert evt["status_code"] == 200
        assert evt["rate_limiter_decision"] == "accepted"
        assert evt["duration_ms"] >= 0.0
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 11: Distinction between Online Store and Synthetic Load Generator
# =========================================================================
@pytest.mark.asyncio
async def test_traffic_source_distinction(async_client):
    """
    Verifies that the Gateway distinguishes real Online Store traffic from synthetic
    Load Generator traffic and internal system probes.
    """
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(200, json=[])
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # 1. Online store customer request
        await async_client.get(
            "/api/shop/products",
            headers={"X-Client-ID": "shopper-ap-south-1"},
        )

        # 2. Synthetic load generator request
        await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-ID": "load-generator-harness", "X-Traffic-Source": "load_generator"},
        )

        # 3. Internal health check
        await async_client.get("/health/live")

        snapshot = telemetry_collector.get_telemetry_snapshot()
        sources = snapshot["traffic_sources"]

        assert sources["online_store"]["requests_total"] >= 1
        assert sources["load_generator"]["requests_total"] >= 1
        assert sources["internal"]["requests_total"] >= 1
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 12: Telemetry API endpoint & Prometheus exposition
# =========================================================================
@pytest.mark.asyncio
async def test_telemetry_endpoint_and_prometheus_export(async_client):
    """
    Verifies that /api/v1/traffic/telemetry and /metrics expose full payload telemetry
    with correct Prometheus types, labels, and structured JSON.
    """
    # Query dedicated telemetry endpoint
    res_telem = await async_client.get("/api/v1/traffic/telemetry")
    assert res_telem.status_code == 200
    data = res_telem.json()

    assert "customer_facing" in data
    assert "upstream_regions" in data
    assert "request_classes" in data
    assert "traffic_sources" in data
    assert data["measurement_info"]["measurement_type"] == "application_payload_bytes"

    # Query Prometheus endpoint
    res_prom = await async_client.get("/metrics")
    assert res_prom.status_code == 200
    prom_text = res_prom.text

    assert "failoverlab_gateway_ingress_payload_bytes_total" in prom_text
    assert "failoverlab_gateway_egress_payload_bytes_total" in prom_text
    assert "failoverlab_gateway_upstream_requests_total{region=\"region-a\"}" in prom_text
    assert "failoverlab_gateway_rate_limited_total" in prom_text
