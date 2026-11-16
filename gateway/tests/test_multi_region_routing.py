import pytest
import httpx
from unittest.mock import AsyncMock
import gateway.src.main as gateway_module
from gateway.src.main import app, route_table
from gateway.src.traffic_manager import traffic_coordinator, LimiterMode

AUTH_HEADERS = {"X-Internal-Secret": "internal-secret-token"}


@pytest.fixture(autouse=True)
def reset_gateway_state():
    """Resets route table and traffic controller before each test."""
    route_table.set_target(
        target_region="region-a",
        target_role="ACTIVE",
        dns_ttl_seconds=2,
        propagation_percent=100,
    )
    # Reset regional health and lags to defaults
    for r in ["region-a", "region-b", "region-c", "region-d", "region-e"]:
        route_table.set_region_health(r, "HEALTHY")
        route_table.set_region_lag(r, 0.0 if r == "region-a" else 0.8)
    route_table.max_stale_seconds = 5.0
    route_table.route_selector.max_stale_seconds = 5.0

    # Reset traffic coordinator
    traffic_coordinator.set_mode(LimiterMode.TOKEN_BUCKET)
    traffic_coordinator.update_config(
        token_capacity=100.0,
        token_refill_rate=50.0,
        leaky_capacity=20,
        leaky_drain_rate=2.0,
    )
    traffic_coordinator.reset_all()


@pytest.mark.asyncio
async def test_eventual_read_routing_across_five_client_regions(async_client):
    """
    Tests that clients from 5 different geographic origins are routed to their nearest
    eligible, healthy, and fresh region for eventual-consistency reads.
    """
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        200,
        json=[{"id": "prod-1", "name": "Laptop", "price": 1299.0}],
        headers={"content-type": "application/json"},
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # 1. India client -> Mumbai (region-a)
        res_in = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "india"},
        )
        assert res_in.status_code == 200
        assert res_in.headers["X-Served-Region"] == "region-a"
        assert res_in.headers["X-Consistency-Level"] == "eventual"
        assert float(res_in.headers["X-Simulated-WAN-Delay-Ms"]) == 18.0

        # 2. Southeast Asia client -> Singapore (region-b)
        res_sea = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "southeast-asia"},
        )
        assert res_sea.status_code == 200
        assert res_sea.headers["X-Served-Region"] == "region-b"
        assert res_sea.headers["X-Consistency-Level"] == "eventual"
        assert float(res_sea.headers["X-Simulated-WAN-Delay-Ms"]) == 14.0

        # 3. Europe client -> Frankfurt (region-c)
        res_eu = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "europe"},
        )
        assert res_eu.status_code == 200
        assert res_eu.headers["X-Served-Region"] == "region-c"
        assert res_eu.headers["X-Consistency-Level"] == "eventual"
        assert float(res_eu.headers["X-Simulated-WAN-Delay-Ms"]) == 16.0

        # 4. North America client -> Virginia (region-d)
        res_na = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "north-america"},
        )
        assert res_na.status_code == 200
        assert res_na.headers["X-Served-Region"] == "region-d"
        assert res_na.headers["X-Consistency-Level"] == "eventual"
        assert float(res_na.headers["X-Simulated-WAN-Delay-Ms"]) == 15.0

        # 5. South America client -> São Paulo (region-e)
        res_sa = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "south-america"},
        )
        assert res_sa.status_code == 200
        assert res_sa.headers["X-Served-Region"] == "region-e"
        assert res_sa.headers["X-Consistency-Level"] == "eventual"
        assert float(res_sa.headers["X-Simulated-WAN-Delay-Ms"]) == 18.0
    finally:
        gateway_module.http_client = original_client


@pytest.mark.asyncio
async def test_fallback_when_nearest_replica_is_unhealthy(async_client):
    """
    When the nearest replica (e.g. Frankfurt for Europe) is DOWN,
    the gateway must automatically select the next lowest-latency eligible replica (Virginia).
    """
    # Break Frankfurt health
    route_table.set_region_health("region-c", "DOWN")

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        200, json={"id": "prod-1"}, headers={"content-type": "application/json"}
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        res = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "europe"},
        )
        assert res.status_code == 200
        # Virginia (region-d) is next nearest (95ms vs 120ms Mumbai)
        assert res.headers["X-Served-Region"] == "region-d"
        assert "fallback" in res.headers["X-Route-Reason"].lower()
        assert "unhealthy" in res.headers["X-Route-Reason"].lower()
    finally:
        gateway_module.http_client = original_client


@pytest.mark.asyncio
async def test_fallback_when_nearest_replica_exceeds_max_staleness(async_client):
    """
    When the nearest replica exceeds the max acceptable staleness (e.g. 8.4s > 5.0s),
    the gateway must route to the next lowest-latency replica that satisfies RPO freshness.
    """
    # Degrade Frankfurt lag to 8.4s
    route_table.set_region_lag("region-c", 8.4)

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        200, json={"id": "prod-1"}, headers={"content-type": "application/json"}
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        res = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "europe"},
        )
        assert res.status_code == 200
        # Bypasses stale Frankfurt; Virginia (0.8s lag) is chosen
        assert res.headers["X-Served-Region"] == "region-d"
        assert "fallback" in res.headers["X-Route-Reason"].lower()
        assert "stale" in res.headers["X-Route-Reason"].lower()
    finally:
        gateway_module.http_client = original_client


@pytest.mark.asyncio
async def test_fallback_to_active_writer_when_all_standbys_ineligible(async_client):
    """
    If all standby regions are stale (>5.0s lag) or unhealthy,
    the gateway must fall back to the active writer (Mumbai) to guarantee bounded staleness.
    """
    for r in ["region-b", "region-c", "region-d", "region-e"]:
        route_table.set_region_lag(r, 10.0)

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        200, json={"id": "prod-1"}, headers={"content-type": "application/json"}
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        res = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-Region": "europe"},
        )
        assert res.status_code == 200
        assert res.headers["X-Served-Region"] == "region-a"
        assert "active_fallback" in res.headers["X-Route-Reason"].lower()
    finally:
        gateway_module.http_client = original_client


@pytest.mark.asyncio
async def test_strong_reads_always_route_to_active_writer(async_client):
    """
    Proves that strong-consistency reads (inventory checks, order status, or explicit header)
    are always routed to the active writer (region-a) even when another region is closer.
    """
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        200, json={"product_id": "prod-1", "stock": 42}, headers={"content-type": "application/json"}
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # A. Inventory endpoint is implicitly strong
        res_inv = await async_client.get(
            "/api/ecommerce/inventory/prod-1",
            headers={"X-Client-Region": "europe"},  # Client in Europe, nearest is Frankfurt (16ms)
        )
        assert res_inv.status_code == 200
        assert res_inv.headers["X-Served-Region"] == "region-a"  # Routed to Mumbai (active writer)!
        assert res_inv.headers["X-Consistency-Level"] == "strong"
        assert res_inv.headers["X-Route-Reason"] == "active_writer_strong_read"

        # B. Generic record read with explicit strong consistency header
        res_rec = await async_client.get(
            "/api/records/inventory:prod-1",
            headers={"X-Client-Region": "north-america", "X-Consistency-Level": "strong"},
        )
        assert res_rec.status_code == 200
        assert res_rec.headers["X-Served-Region"] == "region-a"
        assert res_rec.headers["X-Consistency-Level"] == "strong"
    finally:
        gateway_module.http_client = original_client


@pytest.mark.asyncio
async def test_writes_always_route_to_active_writer_regardless_of_client_location(async_client):
    """
    CRITICAL INVARIANT: Application writes (order creations, updates) MUST ALWAYS reach
    the active primary writer (region-a) and NEVER be round-robined or sent to standby replicas.
    """
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        201,
        json={"order_id": "ord-1234", "status": "CONFIRMED"},
        headers={"content-type": "application/json"},
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # Test writes originating from all 5 global client regions
        for client_reg in ["india", "southeast-asia", "europe", "north-america", "south-america"]:
            res_order = await async_client.post(
                "/api/ecommerce/orders",
                json={"product_id": "prod-1", "quantity": 2},
                headers={"X-Client-Region": client_reg},
            )
            assert res_order.status_code == 201
            # Primary writer must always be region-a
            assert res_order.headers["X-Served-Region"] == "region-a"
            assert res_order.headers["X-Active-Region"] == "region-a"
            assert res_order.headers["X-Consistency-Level"] == "write"
            assert res_order.headers["X-Route-Reason"] == "active_writer_write"
    finally:
        gateway_module.http_client = original_client


@pytest.mark.asyncio
async def test_writer_safety_rejects_writes_when_active_target_demoted(async_client):
    """
    Writer Safety Invariant: If active target is not ACTIVE (e.g. during fencing or unpromoted),
    writes are immediately rejected by gateway with HTTP 403.
    """
    route_table.set_region_role("region-a", "STANDBY")

    res = await async_client.post(
        "/api/ecommerce/orders",
        json={"product_id": "prod-1", "quantity": 1},
    )
    assert res.status_code == 403
    assert "Write rejected by gateway" in res.json()["detail"]["error"]


@pytest.mark.asyncio
async def test_token_bucket_rate_limiter_throttles_excess_requests(async_client):
    """
    Validates Token Bucket rate limiting:
    When capacity is depleted, gateway returns HTTP 429 Too Many Requests with rate limit headers.
    """
    # Configure tiny bucket (capacity 3, refill rate 0.1 tokens/sec)
    traffic_coordinator.set_mode(LimiterMode.TOKEN_BUCKET)
    traffic_coordinator.update_config(token_capacity=3.0, token_refill_rate=0.1)

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(200, json=[])
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # First 3 requests consume available tokens
        for _ in range(3):
            r = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "test-shopper"})
            assert r.status_code == 200

        # 4th request must be throttled with HTTP 429
        r_throttled = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "test-shopper"})
        assert r_throttled.status_code == 429
        assert "Retry-After" in r_throttled.headers
        assert r_throttled.headers["X-RateLimit-Remaining"] == "0"
        assert "Rate limit exceeded" in r_throttled.json()["error"]
    finally:
        gateway_module.http_client = original_client


@pytest.mark.asyncio
async def test_routing_profiles_and_preview_endpoints(async_client):
    """Validates metadata APIs for client profiles and previewing routing decisions."""
    # 1. Profiles API
    res_prof = await async_client.get("/api/v1/routing/profiles")
    assert res_prof.status_code == 200
    data_prof = res_prof.json()
    assert "india" in data_prof["profiles"]
    assert "europe" in data_prof["profiles"]
    assert data_prof["profiles"]["europe"]["latencies_ms"]["region-c"] == 16.0

    # 2. Preview Decision API for write
    res_dec_w = await async_client.get(
        "/api/v1/routing/decision",
        params={"method": "POST", "path": "/api/ecommerce/orders", "client_region": "europe"},
    )
    assert res_dec_w.status_code == 200
    dec_w = res_dec_w.json()
    assert dec_w["target_region"] == "region-a"
    assert dec_w["consistency_level"] == "write"

    # 3. Preview Decision API for eventual read
    res_dec_r = await async_client.get(
        "/api/v1/routing/decision",
        params={"method": "GET", "path": "/api/ecommerce/products", "client_region": "europe"},
    )
    assert res_dec_r.status_code == 200
    dec_r = res_dec_r.json()
    assert dec_r["target_region"] == "region-c"
    assert dec_r["consistency_level"] == "eventual"
