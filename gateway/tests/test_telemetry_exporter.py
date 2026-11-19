import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import httpx

import gateway.src.main as gateway_module
from gateway.src.main import app, route_table
from gateway.src.telemetry_exporter import GatewayTelemetryExporter, telemetry_exporter
from gateway.src.telemetry import telemetry_collector
from gateway.src.traffic_manager import traffic_coordinator, LimiterMode


@pytest.fixture(autouse=True)
def reset_exporter_and_telemetry():
    """Resets telemetry collector and exporter state between tests."""
    telemetry_collector.reset()
    telemetry_exporter.reset()
    traffic_coordinator.set_mode(LimiterMode.OFF)
    traffic_coordinator.reset_all()
    route_table.set_target("region-a", dns_ttl_seconds=2, propagation_percent=100)
    for r in ["region-a", "region-b", "region-c", "region-d", "region-e"]:
        route_table.set_region_health(r, "HEALTHY")
        route_table.set_region_lag(r, 0.0 if r == "region-a" else 0.8)
    yield
    telemetry_collector.reset()
    telemetry_exporter.reset()


# =========================================================================
# Test 1: Truthful Exporter Health at Startup
# =========================================================================
def test_exporter_truthful_health_at_startup():
    """
    Verifies that the exporter does NOT report healthy before a successful export
    has occurred, even if consecutive_failures is 0.
    """
    exporter = GatewayTelemetryExporter(
        controller_url="http://test-controller:8000",
        internal_token="secret",
        gateway_instance_id="gw-test",
    )
    status = exporter.get_status()

    # Truthful health checks:
    assert status["is_running"] is False
    assert status["last_successful_export"] is None
    assert status["consecutive_failures"] == 0
    assert status["is_healthy"] is False  # Must NOT be healthy before first export!


# =========================================================================
# Test 2: Bounded Retry Mechanism & Exhaustion
# =========================================================================
@pytest.mark.asyncio
async def test_exporter_bounded_retry_and_exhaustion():
    """
    Verifies that:
    1. A batch remains in retry loop during temporary Controller failures.
    2. Bounded retries use exponential backoff up to max_retries.
    3. The batch is marked as dropped ONLY after exhausting max_retries.
    4. Consecutive failures are accurately tracked.
    5. queue.task_done() is called correctly.
    """
    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_client.post.return_value = httpx.Response(
        503, content=b'{"error": "Controller temporarily unavailable"}'
    )

    exporter = GatewayTelemetryExporter(
        controller_url="http://test-controller:8000",
        internal_token="secret",
        gateway_instance_id="gw-test",
        interval_seconds=0.1,
        queue_capacity=5,
        max_retries=3,
        backoff_base=0.01,  # Fast backoff for testing
        backoff_max=0.05,
    )
    exporter._client = mock_client
    exporter._running = True

    batch = exporter.build_batch()
    queue = exporter._get_queue()
    await queue.put(batch)

    # Run one pass of worker loop logic
    worker_task = asyncio.create_task(exporter._worker_loop())

    # Wait for queue to be processed
    await asyncio.wait_for(queue.join(), timeout=2.0)

    # Stop worker
    await exporter.stop()

    # 1 initial attempt + 3 retries = 4 total attempts
    assert mock_client.post.call_count == 4
    assert exporter.consecutive_failures == 4
    assert exporter.dropped_batches_count == 1
    assert exporter.total_exported_batches == 0
    assert exporter.get_status()["is_healthy"] is False


# =========================================================================
# Test 3: Successful Retry Resets Consecutive Failures
# =========================================================================
@pytest.mark.asyncio
async def test_exporter_successful_retry_resets_failures():
    """
    Verifies that when a batch fails on initial attempt but succeeds on retry:
    1. consecutive_failures is reset to 0.
    2. total_exported_batches is incremented.
    3. dropped_batches_count remains 0 (not dropped!).
    4. is_healthy becomes True.
    """
    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(500, content=b'{"error": "Internal Error"}')
        return httpx.Response(200, content=b'{"status": "accepted"}')

    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_client.post.side_effect = mock_post

    exporter = GatewayTelemetryExporter(
        controller_url="http://test-controller:8000",
        internal_token="secret",
        gateway_instance_id="gw-test",
        interval_seconds=0.1,
        queue_capacity=5,
        max_retries=3,
        backoff_base=0.01,
        backoff_max=0.05,
    )
    exporter._client = mock_client
    exporter._running = True

    batch = exporter.build_batch()
    queue = exporter._get_queue()
    await queue.put(batch)

    worker_task = asyncio.create_task(exporter._worker_loop())
    await asyncio.wait_for(queue.join(), timeout=2.0)
    await exporter.stop()

    assert call_count == 2
    assert exporter.consecutive_failures == 0
    assert exporter.total_exported_batches == 1
    assert exporter.dropped_batches_count == 0
    assert exporter.last_successful_export is not None
    assert exporter.get_status()["is_healthy"] is True


# =========================================================================
# Test 4: Queue Overflow & Dropped Batch Accounting
# =========================================================================
def test_exporter_queue_overflow():
    """
    Verifies that when the bounded queue reaches capacity:
    1. Subsequent batches are dropped immediately without blocking.
    2. dropped_batches_count is incremented accurately.
    3. Queue size never exceeds capacity.
    """
    exporter = GatewayTelemetryExporter(
        controller_url="http://test-controller:8000",
        internal_token="secret",
        gateway_instance_id="gw-test",
        queue_capacity=3,
    )

    for i in range(7):
        b = exporter.build_batch()
        enqueued = exporter.enqueue_batch(b)
        if i < 3:
            assert enqueued is True
        else:
            assert enqueued is False

    status = exporter.get_status()
    assert status["current_queue_size"] == 3
    assert status["queue_capacity"] == 3
    assert status["dropped_batches_count"] == 4


# =========================================================================
# Test 5: Accurate Reporting of Dropped Batches on Resumed Communication
# =========================================================================
@pytest.mark.asyncio
async def test_exporter_reports_accurate_dropped_count_on_recovery():
    """
    Verifies that when communication resumes after drops, the batch sent to
    the Controller accurately contains the current dropped_telemetry_count.
    """
    last_submitted_json = None

    async def mock_post(url, json=None, headers=None):
        nonlocal last_submitted_json
        last_submitted_json = json
        return httpx.Response(200, content=b'{"status": "accepted"}')

    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_client.post.side_effect = mock_post

    exporter = GatewayTelemetryExporter(
        controller_url="http://test-controller:8000",
        internal_token="secret",
        gateway_instance_id="gw-test",
        queue_capacity=2,
    )
    exporter._client = mock_client

    # Simulate 5 dropped batches due to overflow
    for _ in range(7):
        exporter.enqueue_batch(exporter.build_batch())
    assert exporter.dropped_batches_count == 5

    # Now send a batch (communication restored)
    recovery_batch = exporter.build_batch()
    success = await exporter.send_batch(recovery_batch)

    assert success is True
    assert last_submitted_json is not None
    assert last_submitted_json["dropped_telemetry_count"] == 5


# =========================================================================
# Test 6: Counter Reset Handling & Non-Negative Rates
# =========================================================================
def test_exporter_counter_reset_handling():
    """
    Verifies that if Gateway restarts or counters reset to 0:
    1. Interval deltas are never negative.
    2. Computed rates are never negative.
    3. Regional counters also handle resets without negative deltas.
    """
    exporter = GatewayTelemetryExporter(
        controller_url="http://test-controller:8000",
        internal_token="secret",
        gateway_instance_id="gw-test",
        interval_seconds=1.0,
    )

    # Step 1: Accumulate high traffic
    telemetry_collector.record_client_request(
        method="POST",
        path="/api/ecommerce/orders",
        ingress_bytes=50000,
        egress_bytes=100000,
        duration_ms=25.0,
        status_code=200,
        traffic_source="online_store",
    )
    telemetry_collector.record_upstream(
        region_id="region-a",
        request_bytes=50000,
        response_bytes=100000,
        duration_ms=20.0,
        status_code=200,
    )

    batch_1 = exporter.build_batch()
    assert batch_1["client_ingress_bytes"] == 50000
    assert batch_1["interval_client_ingress_bytes"] == 50000
    assert batch_1["client_ingress_rate"] > 0
    assert batch_1["regional_traffic"]["region-a"]["interval_requests"] == 1

    # Step 2: Reset telemetry (e.g. Gateway restart or counter reset)
    telemetry_collector.reset()

    # Record small amount of traffic after reset
    telemetry_collector.record_client_request(
        method="POST",
        path="/api/ecommerce/orders",
        ingress_bytes=200,
        egress_bytes=800,
        duration_ms=10.0,
        status_code=200,
        traffic_source="online_store",
    )
    telemetry_collector.record_upstream(
        region_id="region-a",
        request_bytes=200,
        response_bytes=800,
        duration_ms=8.0,
        status_code=200,
    )

    batch_2 = exporter.build_batch()
    # Verification: Deltas must NOT be negative (e.g. 200 - 50000 = -49800)
    assert batch_2["client_ingress_bytes"] == 200
    assert batch_2["interval_client_ingress_bytes"] == 200
    assert batch_2["interval_client_egress_bytes"] == 800
    assert batch_2["interval_requests"] == 1
    assert batch_2["client_ingress_rate"] >= 0.0
    assert batch_2["client_egress_rate"] >= 0.0
    assert batch_2["upstream_ingress_rate"] >= 0.0
    assert batch_2["upstream_egress_rate"] >= 0.0

    # Regional deltas must also not be negative
    reg_a = batch_2["regional_traffic"]["region-a"]
    assert reg_a["interval_requests"] == 1
    assert reg_a["interval_request_bytes"] == 200
    assert reg_a["interval_response_bytes"] == 800
    assert reg_a["request_rate"] >= 0.0
    assert reg_a["upstream_egress_rate"] >= 0.0


# =========================================================================
# Test 7: Actual Elapsed Time for Interval Rates
# =========================================================================
def test_exporter_actual_elapsed_time_rates():
    """
    Verifies that the exporter uses the actual elapsed time between batches
    to calculate rates, rather than a hardcoded interval assumption.
    """
    exporter = GatewayTelemetryExporter(
        controller_url="http://test-controller:8000",
        internal_token="secret",
        gateway_instance_id="gw-test",
        interval_seconds=1.0,
    )

    telemetry_collector.record_client_request(
        method="GET",
        path="/api/ecommerce/products",
        ingress_bytes=1000,
        egress_bytes=2000,
        duration_ms=15.0,
        status_code=200,
        traffic_source="online_store",
    )
    batch_1 = exporter.build_batch()

    # Simulate 2.0 seconds elapsed before next batch
    exporter._prev_timestamp = datetime.now(timezone.utc) - timedelta(seconds=2.0)

    telemetry_collector.record_client_request(
        method="GET",
        path="/api/ecommerce/products",
        ingress_bytes=4000,
        egress_bytes=8000,
        duration_ms=15.0,
        status_code=200,
        traffic_source="online_store",
    )
    batch_2 = exporter.build_batch()

    # Delta ingress = 4000 bytes over ~2.0s -> ~2000 B/s (NOT 4000 B/s if assuming 1s)
    assert batch_2["interval_client_ingress_bytes"] == 4000
    assert 1900.0 <= batch_2["client_ingress_rate"] <= 2100.0
    assert 1.9 <= batch_2["reporting_interval_seconds"] <= 2.1


# =========================================================================
# Test 8: Controller Outage Does Not Block Customer Requests
# =========================================================================
@pytest.mark.asyncio
async def test_exporter_customer_requests_unblocked_during_controller_outage(async_client):
    """
    Verifies that customer requests through the Gateway proceed normally without
    latency degradation or errors even when the Controller is completely down.
    """
    # Point exporter to invalid URL
    telemetry_exporter.controller_url = "http://127.0.0.1:59998"

    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        200, json={"items": [{"id": "p1", "name": "Item 1", "price": 10.0}]}
    )
    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client

    try:
        # Customer requests should succeed immediately
        for _ in range(5):
            res = await async_client.get(
                "/api/ecommerce/products",
                headers={"X-Client-Region": "europe", "X-Traffic-Source": "online_store"},
            )
            assert res.status_code == 200
            assert "items" in res.json()

        # Telemetry collector recorded customer traffic truthfully
        assert telemetry_collector.total_requests == 5
        assert telemetry_collector.status_2xx == 5
    finally:
        gateway_module.http_client = original_client


# =========================================================================
# Test 9: Gateway /health Endpoint Truthful Diagnostics
# =========================================================================
@pytest.mark.asyncio
async def test_gateway_health_endpoint_diagnostics(async_client):
    """
    Verifies that GET /health and GET /api/v1/traffic/exporter/status report all
    12 required diagnostic fields truthfully.
    """
    res = await async_client.get("/health")
    assert res.status_code == 200
    data = res.json()

    # Check top-level health
    assert "status" in data
    assert "service" in data
    assert "exporter" in data

    # Check all 12 required fields
    required_fields = [
        "is_running",
        "gateway_instance_id",
        "controller_url",
        "reporting_interval_seconds",
        "queue_capacity",
        "current_queue_size",
        "total_exported_batches",
        "dropped_batches_count",
        "consecutive_failures",
        "last_successful_export",
        "last_error",
        "is_healthy",
    ]
    for field in required_fields:
        assert field in data["exporter"], f"Missing field in exporter status: {field}"
        assert field in data, f"Missing field in root health status: {field}"

    # Also check /api/v1/traffic/exporter/status
    res_exp = await async_client.get("/api/v1/traffic/exporter/status")
    assert res_exp.status_code == 200
    exp_data = res_exp.json()
    for field in required_fields:
        assert field in exp_data, f"Missing field in exporter status endpoint: {field}"


# =========================================================================
# Test 10: Clean Exporter Start & Shutdown
# =========================================================================
@pytest.mark.asyncio
async def test_exporter_clean_start_and_shutdown():
    """
    Verifies that the background sampler and worker tasks start cleanly,
    handle cancellation gracefully during shutdown, and leave no orphan tasks.
    """
    exporter = GatewayTelemetryExporter(
        controller_url="http://test-controller:8000",
        internal_token="secret",
        gateway_instance_id="gw-test-lifecycle",
        interval_seconds=0.1,
    )

    await exporter.start()
    assert exporter._running is True
    assert exporter._sampler_task is not None
    assert exporter._worker_task is not None

    # Let loops run briefly
    await asyncio.sleep(0.15)

    # Shutdown
    await exporter.stop()
    assert exporter._running is False
    assert exporter._sampler_task is None
    assert exporter._worker_task is None
