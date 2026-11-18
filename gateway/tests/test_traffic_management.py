import asyncio
import time
import pytest
import httpx
from unittest.mock import AsyncMock
import gateway.src.main as gateway_module
from gateway.src.main import app, route_table
from gateway.src.traffic_manager import traffic_coordinator, LimiterMode

AUTH_HEADERS = {"X-Internal-Secret": "internal-secret-token"}


@pytest.fixture(autouse=True)
async def setup_and_teardown_traffic():
    # Setup clean state
    route_table.set_target(
        target_region="region-a",
        target_role="ACTIVE",
        dns_ttl_seconds=2,
        propagation_percent=100,
    )
    traffic_coordinator.set_mode(LimiterMode.TOKEN_BUCKET)
    traffic_coordinator.update_config(
        token_capacity=10.0,
        token_refill_rate=2.0,
        leaky_capacity=20,
        leaky_drain_rate=2.0,
    )
    traffic_coordinator.reset_all()
    await traffic_coordinator.leaky_shaper.start()

    yield

    await traffic_coordinator.leaky_shaper.stop()
    traffic_coordinator.reset_all()


# =========================================================================
# Test 1: Token bucket initially full
# =========================================================================
@pytest.mark.asyncio
async def test_1_token_bucket_initially_full(async_client):
    """Scenario 1: Verifies token bucket is initially full (10 tokens) with 0 rejections."""
    res = await async_client.get("/api/v1/traffic/status")
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "TOKEN_BUCKET"
    assert data["token_bucket"]["capacity"] == 10.0
    assert data["token_bucket"]["tokens_remaining"] == 10.0
    assert data["token_bucket"]["accepted_requests"] == 0
    assert data["token_bucket"]["rejected_requests"] == 0


# =========================================================================
# Test 2: Burst allowed up to capacity
# =========================================================================
@pytest.mark.asyncio
async def test_2_burst_allowed_up_to_capacity(async_client):
    """Scenario 2: Burst of 10 requests is completely allowed up to full capacity."""
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(200, json={"items": []})
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        for i in range(10):
            res = await async_client.get(
                "/api/ecommerce/products",
                headers={"X-Client-ID": "burst-shopper"},
            )
            assert res.status_code == 200

        status_res = await async_client.get("/api/v1/traffic/status")
        data = status_res.json()["token_bucket"]
        assert data["accepted_requests"] == 10
        assert data["rejected_requests"] == 0
        assert data["tokens_remaining"] < 2.5
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 3: Rejection after token exhaustion
# =========================================================================
@pytest.mark.asyncio
async def test_3_rejection_after_token_exhaustion(async_client):
    """Scenario 3: After exhausting 10 tokens, the 11th request is rejected with HTTP 429."""
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(200, json={"items": []})
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # Exhaust 10 tokens
        for _ in range(10):
            r = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "exhaust-shopper"})
            assert r.status_code == 200

        # 11th request must be rejected
        res_rejected = await async_client.get(
            "/api/ecommerce/products",
            headers={"X-Client-ID": "exhaust-shopper"},
        )
        assert res_rejected.status_code == 429
        assert "Retry-After" in res_rejected.headers
        assert res_rejected.headers["X-RateLimit-Remaining"] == "0"
        assert res_rejected.headers["X-RateLimit-Mode"] == "TOKEN_BUCKET"
        assert "Rate limit exceeded" in res_rejected.json()["error"]

        status_res = await async_client.get("/api/v1/traffic/status")
        assert status_res.json()["token_bucket"]["rejected_requests"] == 1
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 4: Refill over time
# =========================================================================
@pytest.mark.asyncio
async def test_4_refill_over_time(async_client):
    """Scenario 4: Tokens refill monotonically over time at the configured refill rate."""
    traffic_coordinator.update_config(token_capacity=4.0, token_refill_rate=2.0)  # 2 tokens/sec

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(200, json=[])
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # Consume all 4 tokens
        for _ in range(4):
            r = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "refill-shopper"})
            assert r.status_code == 200

        # Immediate 5th request fails
        r5 = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "refill-shopper"})
        assert r5.status_code == 429

        # Wait 0.6s (at 2 tokens/sec, refills ~1.2 tokens -> exactly 1 token available)
        await asyncio.sleep(0.6)

        # 1 request succeeds
        r_after1 = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "refill-shopper"})
        assert r_after1.status_code == 200

        # Subsequent request exhausted again
        r_after2 = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "refill-shopper"})
        if r_after2.status_code == 200:
            r_after3 = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "refill-shopper"})
            assert r_after3.status_code == 429
        else:
            assert r_after2.status_code == 429
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 5: Concurrent token consumption
# =========================================================================
@pytest.mark.asyncio
async def test_5_concurrent_token_consumption(async_client):
    """
    Scenario 5: 20 simultaneous concurrent async requests against a bucket of capacity 8.
    Asyncio locks prevent race conditions: exactly 8 succeed, exactly 12 are throttled.
    """
    traffic_coordinator.update_config(token_capacity=8.0, token_refill_rate=0.01)  # No fast refill

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(200, json=[])
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        tasks = [
            async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "concurrent-shopper"})
            for _ in range(20)
        ]
        responses = await asyncio.gather(*tasks)

        status_codes = [r.status_code for r in responses]
        success_count = status_codes.count(200)
        throttled_count = status_codes.count(429)

        assert success_count == 8, f"Expected exactly 8 successes, got {success_count}"
        assert throttled_count == 12, f"Expected exactly 12 throttled, got {throttled_count}"
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 6: Leaky bucket FIFO order
# =========================================================================
@pytest.mark.asyncio
async def test_6_leaky_bucket_fifo_order(async_client):
    """
    Scenario 6: Verifies that the Leaky Bucket shaper processes requests strictly in FIFO order.
    """
    traffic_coordinator.set_mode(LimiterMode.LEAKY_BUCKET)
    traffic_coordinator.update_config(leaky_capacity=10, leaky_drain_rate=15.0)

    processed_order = []

    async def mock_backend(method, url, **kwargs):
        # Extract request marker from query
        params = kwargs.get("params", {})
        seq = params.get("seq")
        processed_order.append(seq)
        return httpx.Response(200, json={"seq": seq})

    mock_client = AsyncMock()
    mock_client.request.side_effect = mock_backend
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # Enqueue seq 1, 2, 3 rapidly
        tasks = [
            async_client.get(f"/api/ecommerce/products?seq={i}", headers={"X-Client-ID": "fifo-client"})
            for i in [1, 2, 3, 4, 5]
        ]
        responses = await asyncio.gather(*tasks)

        assert all(r.status_code == 200 for r in responses)
        assert processed_order == ["1", "2", "3", "4", "5"]
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 7: Constant drain rate
# =========================================================================
@pytest.mark.asyncio
async def test_7_constant_drain_rate(async_client):
    """
    Scenario 7: Verifies that the dispatcher releases queued requests at the constant configured drain rate.
    Drain rate: 4 req/sec -> interval ~0.25s between releases.
    """
    traffic_coordinator.set_mode(LimiterMode.LEAKY_BUCKET)
    traffic_coordinator.update_config(leaky_capacity=10, leaky_drain_rate=4.0)

    completion_times = []

    async def mock_backend(*args, **kwargs):
        completion_times.append(time.monotonic())
        return httpx.Response(200, json={"status": "ok"})

    mock_client = AsyncMock()
    mock_client.request.side_effect = mock_backend
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        tasks = [
            async_client.get(f"/api/ecommerce/products?item={i}", headers={"X-Client-ID": "drain-client"})
            for i in range(3)
        ]
        responses = await asyncio.gather(*tasks)
        assert all(r.status_code == 200 for r in responses)
        assert len(completion_times) == 3

        # First to second gap should be at least ~0.2s
        gap_1_2 = completion_times[1] - completion_times[0]
        gap_2_3 = completion_times[2] - completion_times[1]
        assert gap_1_2 >= 0.20, f"Gap between requests 1 and 2 was {gap_1_2}s (expected ~0.25s)"
        assert gap_2_3 >= 0.20, f"Gap between requests 2 and 3 was {gap_2_3}s (expected ~0.25s)"
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 8: Queue overflow
# =========================================================================
@pytest.mark.asyncio
async def test_8_leaky_bucket_queue_overflow(async_client):
    """
    Scenario 8: When the bounded queue is full (capacity=2), excess requests are immediately rejected with HTTP 429.
    """
    traffic_coordinator.set_mode(LimiterMode.LEAKY_BUCKET)
    # Slow drain rate (0.01) so items queue up
    traffic_coordinator.update_config(leaky_capacity=2, leaky_drain_rate=0.01)

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(200, json={})
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # Enqueue items to fill the queue and overflow it
        tasks = [
            asyncio.create_task(async_client.get(f"/api/ecommerce/products?q={i}"))
            for i in range(5)
        ]
        await asyncio.sleep(0.05)

        # Speed up drain to finish queued tasks cleanly without hanging
        traffic_coordinator.update_config(leaky_drain_rate=100.0)
        responses = await asyncio.gather(*tasks)

        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, f"Expected 429 overflow in responses, got {status_codes}"
        overflow_res = next(r for r in responses if r.status_code == 429)
        assert "overflow" in overflow_res.json()["message"].lower()
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 9: Request cancellation
# =========================================================================
@pytest.mark.asyncio
async def test_9_request_cancellation(async_client):
    """
    Scenario 9: Client cancels a queued request before it is dequeued.
    The dispatcher handles cancellation gracefully without breaking the queue worker.
    """
    traffic_coordinator.set_mode(LimiterMode.LEAKY_BUCKET)
    traffic_coordinator.update_config(leaky_capacity=10, leaky_drain_rate=1.0)

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(200, json={"ok": True})
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # Launch request and cancel it immediately
        task = asyncio.create_task(async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "cancel-client"}))
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Next normal request succeeds cleanly through the same queue worker
        res_next = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "next-client"})
        assert res_next.status_code == 200
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 10: Gateway failure while processing a queued request
# =========================================================================
@pytest.mark.asyncio
async def test_10_gateway_failure_while_processing_queued_request(async_client):
    """
    Scenario 10: When a dequeued request encounters an upstream service failure (503),
    the dispatcher remains operational and subsequent queued requests continue processing.
    """
    traffic_coordinator.set_mode(LimiterMode.LEAKY_BUCKET)
    traffic_coordinator.update_config(leaky_capacity=10, leaky_drain_rate=10.0)

    call_count = 0

    async def mock_upstream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("Regional service temporarily unavailable")
        return httpx.Response(200, json={"status": "recovered"})

    mock_client = AsyncMock()
    mock_client.request.side_effect = mock_upstream
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # First request fails with 503
        r1 = await async_client.get("/api/ecommerce/products?req=1")
        assert r1.status_code == 503

        # Second request through the same leaky bucket queue succeeds with 200
        r2 = await async_client.get("/api/ecommerce/products?req=2")
        assert r2.status_code == 200
        assert r2.json()["status"] == "recovered"
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 11: Idempotent checkout retries
# =========================================================================
@pytest.mark.asyncio
async def test_11_idempotent_checkout_retries(async_client):
    """
    Scenario 11: Retries of the same order creation with identical Idempotency-Key
    return the cached response and do not call the upstream region service a second time.
    """
    mock_client = AsyncMock()
    order_payload = {"order_id": "ord-idemp-101", "product_id": "prod-laptop-01", "quantity": 1, "status": "CONFIRMED"}
    mock_client.request.return_value = httpx.Response(201, json=order_payload, headers={"content-type": "application/json"})
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        idemp_headers = {
            "Idempotency-Key": "idemp-key-xyz-777",
            "X-Client-Region": "europe",
        }
        req_body = {"product_id": "prod-laptop-01", "quantity": 1}

        # 1. Initial order placement
        res1 = await async_client.post("/api/ecommerce/orders", json=req_body, headers=idemp_headers)
        assert res1.status_code == 201
        assert res1.json()["order_id"] == "ord-idemp-101"
        assert mock_client.request.call_count == 1

        # 2. Retried order placement with same Idempotency-Key
        res2 = await async_client.post("/api/ecommerce/orders", json=req_body, headers=idemp_headers)
        assert res2.status_code == 201
        assert res2.json()["order_id"] == "ord-idemp-101"
        assert res2.headers.get("X-Idempotency-Replay") == "true"

        # Mock client must NOT have been called a second time!
        assert mock_client.request.call_count == 1
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 12: Switching between limiter modes
# =========================================================================
@pytest.mark.asyncio
async def test_12_switching_between_limiter_modes(async_client):
    """
    Scenario 12: Dynamically switching between modes (OFF -> TOKEN_BUCKET -> LEAKY_BUCKET -> OFF).
    """
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(200, json=[])
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # 1. Switch to OFF: No rate limiting
        res_off = await async_client.put(
            "/internal/traffic/config",
            json={"mode": "OFF"},
            headers=AUTH_HEADERS,
        )
        assert res_off.status_code == 200
        assert res_off.json()["traffic_control"]["mode"] == "OFF"

        # Under OFF mode, 25 requests all pass
        for _ in range(25):
            r = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "mode-switcher"})
            assert r.status_code == 200
            assert r.headers["X-RateLimit-Mode"] == "OFF"

        # 2. Switch to TOKEN_BUCKET with capacity=2
        res_tb = await async_client.put(
            "/internal/traffic/config",
            json={"mode": "TOKEN_BUCKET", "token_capacity": 2.0, "token_refill_rate": 0.05},
            headers=AUTH_HEADERS,
        )
        assert res_tb.status_code == 200
        assert res_tb.json()["traffic_control"]["mode"] == "TOKEN_BUCKET"
        traffic_coordinator.reset_all()

        r1 = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "tb-client"})
        r2 = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "tb-client"})
        r3 = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "tb-client"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429
        assert r3.headers["X-RateLimit-Mode"] == "TOKEN_BUCKET"

        # 3. Switch to LEAKY_BUCKET
        res_lb = await async_client.put(
            "/internal/traffic/config",
            json={"mode": "LEAKY_BUCKET", "leaky_capacity": 5, "leaky_drain_rate": 20.0},
            headers=AUTH_HEADERS,
        )
        assert res_lb.status_code == 200
        assert res_lb.json()["traffic_control"]["mode"] == "LEAKY_BUCKET"

        r_lb = await async_client.get("/api/ecommerce/products", headers={"X-Client-ID": "lb-client"})
        assert r_lb.status_code == 200
        assert r_lb.headers["X-RateLimit-Mode"] == "LEAKY_BUCKET"

        # 4. Switch back to OFF
        res_off2 = await async_client.put(
            "/internal/traffic/config",
            json={"mode": "OFF"},
            headers=AUTH_HEADERS,
        )
        assert res_off2.status_code == 200
        assert res_off2.json()["traffic_control"]["mode"] == "OFF"
    finally:
        gateway_module.http_client = original_client
