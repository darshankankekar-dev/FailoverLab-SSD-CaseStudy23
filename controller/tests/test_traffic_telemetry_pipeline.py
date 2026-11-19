import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.models import TrafficSampleEntity
from src.services.traffic_service import traffic_service, to_utc_naive, to_utc_aware
from src.schemas.traffic import TrafficBatchSubmission
from gateway.src.telemetry_exporter import GatewayTelemetryExporter


@pytest.fixture(autouse=True)
def clean_traffic_service():
    """Ensures each test starts with empty in-memory telemetry state."""
    traffic_service.reset()
    yield
    traffic_service.reset()


def make_valid_batch(
    batch_id: str = None,
    gateway_id: str = "gateway-1",
    timestamp: datetime = None,
    ingress_bytes: int = 15000,
    egress_bytes: int = 45000,
    request_count: int = 120,
    interval_seconds: float = 1.0,
) -> dict:
    ts = timestamp or datetime.now(timezone.utc)
    b_id = batch_id or f"batch-{uuid.uuid4().hex[:12]}"
    return {
        "schema_version": "1.0",
        "gateway_instance_id": gateway_id,
        "batch_id": b_id,
        "timestamp": ts.isoformat(),
        "reporting_interval_seconds": interval_seconds,
        "client_ingress_bytes": ingress_bytes,
        "client_egress_bytes": egress_bytes,
        "interval_client_ingress_bytes": 1500,
        "interval_client_egress_bytes": 4500,
        "upstream_ingress_bytes": 40000,
        "upstream_egress_bytes": 12000,
        "interval_upstream_ingress_bytes": 4000,
        "interval_upstream_egress_bytes": 1200,
        "client_ingress_rate": 1500.0,
        "client_egress_rate": 4500.0,
        "upstream_ingress_rate": 4000.0,
        "upstream_egress_rate": 1200.0,
        "request_count": request_count,
        "interval_requests": 12,
        "request_rate": 12.0,
        "status_2xx": 115,
        "status_3xx": 0,
        "status_4xx": 3,
        "status_5xx": 2,
        "rate_limited_429": 1,
        "latency_avg_ms": 28.5,
        "latency_p50_ms": 22.0,
        "latency_p95_ms": 58.0,
        "latency_p99_ms": 95.0,
        "regional_traffic": {
            "region-a": {
                "region_id": "region-a",
                "requests_total": 80,
                "request_payload_bytes": 8000,
                "response_payload_bytes": 28000,
                "status_2xx": 78,
                "status_3xx": 0,
                "status_4xx": 2,
                "status_5xx": 0,
                "failed_requests": 0,
                "timeouts": 0,
                "average_latency_ms": 24.0,
            },
            "region-b": {
                "region_id": "region-b",
                "requests_total": 25,
                "request_payload_bytes": 2500,
                "response_payload_bytes": 8000,
                "status_2xx": 24,
                "status_3xx": 0,
                "status_4xx": 1,
                "status_5xx": 0,
                "failed_requests": 0,
                "timeouts": 0,
                "average_latency_ms": 35.0,
            },
            "region-c": {
                "region_id": "region-c",
                "requests_total": 10,
                "request_payload_bytes": 1000,
                "response_payload_bytes": 3000,
                "status_2xx": 9,
                "status_3xx": 0,
                "status_4xx": 0,
                "status_5xx": 1,
                "failed_requests": 1,
                "timeouts": 0,
                "average_latency_ms": 42.0,
            },
            "region-d": {
                "region_id": "region-d",
                "requests_total": 3,
                "request_payload_bytes": 300,
                "response_payload_bytes": 600,
                "status_2xx": 3,
                "status_3xx": 0,
                "status_4xx": 0,
                "status_5xx": 0,
                "failed_requests": 0,
                "timeouts": 0,
                "average_latency_ms": 45.0,
            },
            "region-e": {
                "region_id": "region-e",
                "requests_total": 2,
                "request_payload_bytes": 200,
                "response_payload_bytes": 400,
                "status_2xx": 1,
                "status_3xx": 0,
                "status_4xx": 0,
                "status_5xx": 1,
                "failed_requests": 1,
                "timeouts": 0,
                "average_latency_ms": 60.0,
            },
        },
        "traffic_sources": {
            "online_store": {"requests_total": 90, "ingress_bytes": 12000, "egress_bytes": 38000},
            "load_generator": {"requests_total": 30, "ingress_bytes": 3000, "egress_bytes": 7000},
        },
        "dropped_telemetry_count": 0,
        "events": [
            {
                "id": "evt-test-1",
                "timestamp": ts.isoformat(),
                "method": "POST",
                "endpoint": "/api/ecommerce/orders",
                "client_region": "eu-central-1",
                "served_region": "region-a",
                "request_type": "write",
                "rate_limiter_decision": "accepted",
                "status_code": 201,
                "duration_ms": 45.2,
                "request_payload_bytes": 450,
                "response_payload_bytes": 980,
                "request_category": "order_checkout",
                "upstream_region": "region-a",
                "upstream_request_bytes": 450,
                "upstream_response_bytes": 980,
                "upstream_duration_ms": 42.0,
                "traffic_source": "online_store",
                "is_replay": False,
            }
        ],
    }


@pytest.mark.asyncio
async def test_valid_traffic_batch_ingestion(client: AsyncClient, db_session: AsyncSession):
    """Verifies that a well-formed batch submitted with internal auth is accepted and persisted."""
    batch = make_valid_batch(batch_id="batch-valid-1")
    resp = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["batch_id"] == "batch-valid-1"

    # Verify DB persistence
    res = await db_session.execute(
        select(TrafficSampleEntity).where(TrafficSampleEntity.batch_id == "batch-valid-1")
    )
    sample = res.scalar_one_or_none()
    assert sample is not None
    assert sample.client_ingress_bytes == 15000
    assert sample.client_egress_bytes == 45000
    assert sample.request_count == 120
    assert sample.timestamp.tzinfo is None


@pytest.mark.asyncio
async def test_missing_internal_authentication(client: AsyncClient):
    """Verifies that request without X-Internal-Secret is rejected with HTTP 401."""
    batch = make_valid_batch(batch_id="batch-noauth")
    resp = await client.post("/internal/telemetry/traffic-batch", json=batch)
    assert resp.status_code == 401
    assert "X-Internal-Secret" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_authentication_token(client: AsyncClient):
    """Verifies that request with wrong secret is rejected with HTTP 401."""
    batch = make_valid_batch(batch_id="batch-wrongauth")
    resp = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "invalid-hacker-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_payload_future_dated(client: AsyncClient):
    """Verifies that a future-dated batch (> 10s skew) is rejected."""
    future_time = datetime.now(timezone.utc) + timedelta(minutes=5)
    batch = make_valid_batch(batch_id="batch-future", timestamp=future_time)
    resp = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert resp.status_code == 422  # Pydantic validation failure


@pytest.mark.asyncio
async def test_invalid_payload_negative_numbers(client: AsyncClient):
    """Verifies that negative byte counters are rejected."""
    batch = make_valid_batch(batch_id="batch-neg")
    batch["client_ingress_bytes"] = -50
    resp = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_payload_unsupported_version(client: AsyncClient):
    """Verifies that unsupported schema version is rejected with HTTP 400."""
    batch = make_valid_batch(batch_id="batch-ver")
    batch["schema_version"] = "99.0"
    resp = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_batch_idempotency(client: AsyncClient, db_session: AsyncSession):
    """Verifies that submitting the exact same batch twice is idempotent and does not duplicate DB rows."""
    batch = make_valid_batch(batch_id="batch-dup-1")

    # First submission
    resp1 = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "accepted"

    # Second submission (retry)
    resp2 = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "duplicate"
    assert "already processed" in resp2.json()["message"]

    # Verify count in DB is exactly 1
    count = await db_session.scalar(
        select(func.count(TrafficSampleEntity.id)).where(TrafficSampleEntity.batch_id == "batch-dup-1")
    )
    assert count == 1


@pytest.mark.asyncio
async def test_out_of_order_batch_handling(client: AsyncClient):
    """Verifies out-of-order batches do not regress live latest summary."""
    t_now = datetime.now(timezone.utc)
    t_earlier = t_now - timedelta(seconds=20)

    # Ingest newer batch first (T2)
    batch_newer = make_valid_batch(
        batch_id="batch-t2",
        timestamp=t_now,
        ingress_bytes=20000,
        request_count=200,
    )
    r1 = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch_newer,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert r1.status_code == 200

    # Ingest older batch later (T1)
    batch_older = make_valid_batch(
        batch_id="batch-t1",
        timestamp=t_earlier,
        ingress_bytes=10000,
        request_count=100,
    )
    r2 = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch_older,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert r2.status_code == 200

    # Latest summary must remain T2
    summary_resp = await client.get("/api/v1/traffic/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["cumulative_ingress_bytes"] == 20000
    assert summary["total_requests"] == 200


@pytest.mark.asyncio
async def test_gateway_restart_and_counter_reset(client: AsyncClient):
    """Verifies gateway restarts / counter resets are handled smoothly without negative rates."""
    t0 = datetime.now(timezone.utc) - timedelta(seconds=5)
    t1 = datetime.now(timezone.utc)

    # 1. Gateway was reporting high cumulative numbers
    batch_pre = make_valid_batch(
        batch_id="batch-pre-restart",
        timestamp=t0,
        ingress_bytes=5_000_000,
        egress_bytes=15_000_000,
        request_count=50_000,
    )
    r1 = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch_pre,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert r1.status_code == 200

    # 2. Gateway restarts: cumulative numbers reset to zero baseline
    batch_post = make_valid_batch(
        batch_id="batch-post-restart",
        timestamp=t1,
        ingress_bytes=800,
        egress_bytes=2400,
        request_count=8,
    )
    r2 = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch_post,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert r2.status_code == 200

    # Summary should reflect new baseline and positive rates
    summary_resp = await client.get("/api/v1/traffic/summary")
    summary = summary_resp.json()
    assert summary["cumulative_ingress_bytes"] == 800
    assert summary["total_requests"] == 8
    assert summary["current_ingress_bytes_per_sec"] >= 0.0
    assert summary["request_rate"] >= 0.0


@pytest.mark.asyncio
async def test_traffic_summary_initial_unavailable(client: AsyncClient):
    """Verifies that prior to receiving any batch, summary reports UNAVAILABLE status."""
    resp = await client.get("/api/v1/traffic/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_available"] is False
    assert data["telemetry_freshness"] == "UNAVAILABLE"
    assert data["measurement_source"] == "none"
    assert data["total_requests"] == 0
    assert data["current_ingress_bytes_per_sec"] == 0.0


@pytest.mark.asyncio
async def test_traffic_summary_zero_traffic_distinguishable_from_unavailable(client: AsyncClient):
    """Verifies zero traffic is distinguishable from missing telemetry: is_available=True and freshness=FRESH."""
    zero_batch = make_valid_batch(
        batch_id="batch-zero",
        ingress_bytes=0,
        egress_bytes=0,
        request_count=0,
    )
    zero_batch["client_ingress_rate"] = 0.0
    zero_batch["client_egress_rate"] = 0.0
    zero_batch["request_rate"] = 0.0

    r = await client.post(
        "/internal/telemetry/traffic-batch",
        json=zero_batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert r.status_code == 200

    summary_resp = await client.get("/api/v1/traffic/summary")
    data = summary_resp.json()
    # It IS available and FRESH, but rates are 0.0!
    assert data["is_available"] is True
    assert data["telemetry_freshness"] == "FRESH"
    assert data["measurement_source"] == "gateway-1"
    assert data["current_ingress_bytes_per_sec"] == 0.0
    assert data["total_requests"] == 0


@pytest.mark.asyncio
async def test_telemetry_staleness_states(client: AsyncClient):
    """Verifies FRESH -> STALE -> UNAVAILABLE freshness transitions based on telemetry age."""
    now = datetime.now(timezone.utc)

    # 1. Fresh telemetry (1s ago)
    b_fresh = make_valid_batch(batch_id="b-fresh", timestamp=now - timedelta(seconds=1))
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=b_fresh,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    s1 = (await client.get("/api/v1/traffic/summary")).json()
    assert s1["telemetry_freshness"] == "FRESH"

    # 2. Stale telemetry (8s ago)
    traffic_service.reset()
    b_stale = make_valid_batch(batch_id="b-stale", timestamp=now - timedelta(seconds=8))
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=b_stale,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    s2 = (await client.get("/api/v1/traffic/summary")).json()
    assert s2["telemetry_freshness"] == "STALE"

    # 3. Unavailable telemetry (30s ago)
    traffic_service.reset()
    b_unavail = make_valid_batch(batch_id="b-unavail", timestamp=now - timedelta(seconds=30))
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=b_unavail,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    s3 = (await client.get("/api/v1/traffic/summary")).json()
    assert s3["telemetry_freshness"] == "UNAVAILABLE"
    assert s3["is_available"] is False


@pytest.mark.asyncio
async def test_traffic_timeseries_aggregation(client: AsyncClient):
    """Verifies timeseries query endpoint returns sampled points with rates."""
    now = datetime.now(timezone.utc)
    for i in range(3):
        b = make_valid_batch(
            batch_id=f"ts-batch-{i}",
            timestamp=now - timedelta(seconds=10 - i),
            ingress_bytes=1000 * (i + 1),
            egress_bytes=3000 * (i + 1),
            request_count=10 * (i + 1),
        )
        await client.post(
            "/internal/telemetry/traffic-batch",
            json=b,
            headers={"X-Internal-Secret": "internal-secret-token"},
        )

    resp = await client.get("/api/v1/traffic/timeseries?time_range_seconds=60&step_seconds=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["point_count"] == 3
    assert len(data["points"]) == 3
    p = data["points"][-1]
    assert p["client_ingress_bytes"] == 3000
    assert p["client_egress_bytes"] == 9000
    assert p["request_rate"] >= 0.0


@pytest.mark.asyncio
async def test_regional_traffic_aggregation(client: AsyncClient):
    """Verifies all five regions are accounted for with actual measured metrics."""
    batch = make_valid_batch(batch_id="batch-regions")
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )

    resp = await client.get("/api/v1/traffic/regions")
    assert resp.status_code == 200
    data = resp.json()
    regions = data["regions"]
    assert len(regions) == 5
    assert set(regions.keys()) == {"region-a", "region-b", "region-c", "region-d", "region-e"}

    # Region A (Mumbai)
    assert regions["region-a"]["region_name"] == "Mumbai"
    assert regions["region-a"]["cloud_zone"] == "ap-south-1"
    assert regions["region-a"]["requests_total"] == 80
    assert regions["region-a"]["upstream_request_bytes"] == 8000
    assert regions["region-a"]["upstream_response_bytes"] == 28000

    # Region C (Frankfurt)
    assert regions["region-c"]["region_name"] == "Frankfurt"
    assert regions["region-c"]["requests_total"] == 10
    assert regions["region-c"]["failed_requests"] == 1


@pytest.mark.asyncio
async def test_traffic_events_pagination(client: AsyncClient):
    """Verifies bounded traffic events endpoint pagination."""
    batch = make_valid_batch(batch_id="batch-events")
    batch["events"] = [
        {
            "id": f"evt-{i}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": "GET",
            "endpoint": f"/api/ecommerce/products/{i}",
            "client_region": "eu-central-1",
            "served_region": "region-c",
            "request_type": "eventual_read",
            "rate_limiter_decision": "accepted",
            "status_code": 200,
            "duration_ms": 15.0 + i,
            "request_payload_bytes": 0,
            "response_payload_bytes": 450,
            "traffic_source": "online_store",
        }
        for i in range(5)
    ]
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )

    # Page 1
    r1 = await client.get("/api/v1/traffic/events?page=1&page_size=2")
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["total"] == 5
    assert d1["page"] == 1
    assert len(d1["events"]) == 2

    # Page 2
    r2 = await client.get("/api/v1/traffic/events?page=2&page_size=2")
    assert r2.status_code == 200
    d2 = r2.json()
    assert len(d2["events"]) == 2
    assert d2["events"][0]["id"] != d1["events"][0]["id"]


@pytest.mark.asyncio
async def test_traffic_sse_stream_initial_metric(client: AsyncClient):
    """Verifies SSE endpoint connects, yields initial metric event, and unregisters subscriber cleanly."""
    initial_subscribers = len(traffic_service._sse_subscribers)

    resp = await client.get("/api/v1/traffic/stream?max_events=1")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "event: connect" in resp.text
    assert "connected" in resp.text

    # Verify subscriber is cleanly unsubscribed when stream completes
    assert len(traffic_service._sse_subscribers) == initial_subscribers


@pytest.mark.asyncio
async def test_traffic_sse_stream_broadcast_update(client: AsyncClient):
    """Verifies live traffic batch ingestion broadcasts update event over SSE stream."""
    q = await traffic_service.subscribe_sse()
    try:
        batch = make_valid_batch(batch_id="batch-sse-test")
        await client.post(
            "/internal/telemetry/traffic-batch",
            json=batch,
            headers={"X-Internal-Secret": "internal-secret-token"},
        )
        msg = await asyncio.wait_for(q.get(), timeout=2.0)
        assert msg["event"] == "traffic_metric"
        assert msg["data"]["cumulative_ingress_bytes"] == batch["client_ingress_bytes"]
    finally:
        await traffic_service.unsubscribe_sse(q)


@pytest.mark.asyncio
async def test_controller_persistence_and_pruning(client: AsyncClient, db_session: AsyncSession):
    """Verifies persistence of traffic samples and retention pruning of old samples."""
    now = datetime.now(timezone.utc)

    # Ingest old sample (30 hours ago)
    old_batch = make_valid_batch(batch_id="batch-old", timestamp=now - timedelta(hours=30))
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=old_batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )

    # Ingest fresh sample (1 hour ago)
    fresh_batch = make_valid_batch(batch_id="batch-fresh", timestamp=now - timedelta(hours=1))
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=fresh_batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )

    # Total in DB should be 2
    count_before = await db_session.scalar(select(func.count(TrafficSampleEntity.id)))
    assert count_before == 2

    # Prune samples older than 24 hours
    deleted = await traffic_service.prune_old_samples(db_session, retention_hours=24)
    assert deleted == 1

    # Remaining in DB should be 1
    count_after = await db_session.scalar(select(func.count(TrafficSampleEntity.id)))
    assert count_after == 1


@pytest.mark.asyncio
async def test_gateway_exporter_build_and_send(client: AsyncClient):
    """Verifies GatewayTelemetryExporter builds batch from collector and sends successfully."""
    exporter = GatewayTelemetryExporter(
        controller_url="http://testserver",
        internal_token="internal-secret-token",
        gateway_instance_id="gateway-test-1",
        interval_seconds=1.0,
        queue_capacity=10,
    )
    batch = exporter.build_batch()
    assert batch["schema_version"] == "1.0"
    assert batch["gateway_instance_id"] == "gateway-test-1"
    assert "client_ingress_bytes" in batch

    # Directly send using test client
    resp = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_gateway_exporter_retry_and_resilience():
    """Verifies GatewayTelemetryExporter retries and handles Controller unavailability gracefully."""
    # Exporter pointing to non-existent endpoint
    exporter = GatewayTelemetryExporter(
        controller_url="http://127.0.0.1:59999",  # Nothing listening here
        internal_token="internal-secret-token",
        gateway_instance_id="gateway-test-fail",
        interval_seconds=0.1,
        queue_capacity=2,
    )
    b1 = exporter.build_batch()
    b2 = exporter.build_batch()
    b3 = exporter.build_batch()

    # Test queue bounded dropping
    assert exporter.enqueue_batch(b1) is True
    assert exporter.enqueue_batch(b2) is True
    # 3rd batch should be dropped because queue capacity is 2
    assert exporter.enqueue_batch(b3) is False
    assert exporter.dropped_batches_count == 1

    # Test send_batch graceful failure (does not crash or raise uncaught error)
    success = await exporter.send_batch(b1)
    assert success is False
    assert exporter.consecutive_failures == 1
    assert exporter.last_error is not None

    status = exporter.get_status()
    assert status["is_healthy"] is False
    assert status["consecutive_failures"] == 1
    assert status["dropped_batches_count"] == 1

    # Clean shutdown
    await exporter.stop()


@pytest.mark.asyncio
async def test_summary_response_canonical_contract(client: AsyncClient):
    """Verifies all 24 required fields are present in /api/v1/traffic/summary matching canonical contract."""
    batch = make_valid_batch(batch_id="batch-summary-contract")
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    resp = await client.get("/api/v1/traffic/summary")
    assert resp.status_code == 200
    data = resp.json()

    required_fields = [
        "current_ingress_bytes_per_sec",
        "current_egress_bytes_per_sec",
        "cumulative_ingress_bytes",
        "cumulative_egress_bytes",
        "upstream_ingress_bytes_per_sec",
        "upstream_egress_bytes_per_sec",
        "request_rate",
        "total_requests",
        "status_2xx",
        "status_3xx",
        "status_4xx",
        "status_5xx",
        "rate_limited_429",
        "latency_avg_ms",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_p99_ms",
        "last_received_timestamp",
        "telemetry_freshness",
        "telemetry_age_seconds",
        "is_available",
        "measurement_source",
        "measurement_unit",
        "measurement_type",
        "note",
    ]
    for field in required_fields:
        assert field in data, f"Missing field in summary contract: {field}"

    assert data["measurement_unit"] == "bytes"
    assert data["measurement_type"] == "application_payload_bytes"
    assert data["measurement_source"] == "gateway-1"
    assert data["is_available"] is True
    assert data["telemetry_freshness"] in ("FRESH", "STALE", "UNAVAILABLE")


@pytest.mark.asyncio
async def test_timeseries_historical_merge_persisted_and_in_memory(client: AsyncClient, db_session: AsyncSession):
    """
    Verifies timeseries query merges older persisted database records with newer in-memory
    samples, ensuring older history is not omitted.
    """
    now = datetime.now(timezone.utc)
    t_old = now - timedelta(seconds=200)
    t_mid = now - timedelta(seconds=100)
    t_new = now - timedelta(seconds=2)

    # 1. Insert an older sample directly into DB (simulating persisted history before a restart)
    old_sample = TrafficSampleEntity(
        batch_id="batch-db-old",
        gateway_instance_id="gateway-1",
        timestamp=to_utc_naive(t_old),
        interval_seconds=1.0,
        client_ingress_bytes=5000,
        client_egress_bytes=10000,
        client_ingress_rate=500.0,
        client_egress_rate=1000.0,
        upstream_ingress_bytes=8000,
        upstream_egress_bytes=4000,
        upstream_ingress_rate=800.0,
        upstream_egress_rate=400.0,
        request_count=50,
        request_rate=5.0,
        status_2xx=50,
        status_3xx=0,
        status_4xx=0,
        status_5xx=0,
        rate_limited_429=0,
        latency_avg_ms=20.0,
        latency_p50_ms=18.0,
        latency_p95_ms=30.0,
        latency_p99_ms=45.0,
        regional_traffic_json={},
        traffic_sources_json={},
        dropped_telemetry_count=0,
    )
    db_session.add(old_sample)
    await db_session.commit()

    # 2. Ingest newer sample via standard endpoint (populates in-memory buffer)
    batch_new = make_valid_batch(
        batch_id="batch-mem-new",
        timestamp=t_new,
        ingress_bytes=25000,
        egress_bytes=50000,
        request_count=250,
    )
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch_new,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )

    # 3. Query timeseries spanning 300 seconds (should include both DB sample and in-memory sample)
    resp = await client.get("/api/v1/traffic/timeseries?time_range_seconds=300&step_seconds=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["point_count"] >= 2

    # Check required fields on every point
    for pt in data["points"]:
        for field in [
            "timestamp", "client_ingress_bytes", "client_egress_bytes",
            "client_ingress_rate", "client_egress_rate", "upstream_ingress_rate",
            "upstream_egress_rate", "request_rate", "error_rate", "status_2xx",
            "status_4xx", "status_5xx", "latency_p95_ms"
        ]:
            assert field in pt, f"Missing field in timeseries point: {field}"

    # Verify both the old and new points are present
    ingress_values = [p["client_ingress_bytes"] for p in data["points"]]
    assert 5000 in ingress_values, "Older DB sample was omitted from timeseries response!"
    assert 25000 in ingress_values, "Newer in-memory sample was missing from timeseries response!"


@pytest.mark.asyncio
async def test_regional_traffic_rates_and_counter_reset(client: AsyncClient):
    """
    Verifies that regional rates (request_rate, upstream_ingress_rate, upstream_egress_rate)
    are calculated accurately from consecutive batches per Gateway instance and handle counter resets.
    """
    t0 = datetime.now(timezone.utc) - timedelta(seconds=2)
    t1 = datetime.now(timezone.utc)

    # Batch 1 at T0
    b1 = make_valid_batch(batch_id="batch-reg-rate-1", timestamp=t0, interval_seconds=1.0)
    b1["regional_traffic"]["region-a"]["requests_total"] = 100
    b1["regional_traffic"]["region-a"]["request_payload_bytes"] = 10000   # upstream egress
    b1["regional_traffic"]["region-a"]["response_payload_bytes"] = 30000  # upstream ingress
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=b1,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )

    # Initial batch: rates should be 0.0 (baseline)
    r1 = (await client.get("/api/v1/traffic/regions")).json()
    assert r1["regions"]["region-a"]["requests_total"] == 100
    assert r1["regions"]["region-a"]["request_rate"] == 0.0

    # Batch 2 at T1 (elapsed ~ 2.0s)
    b2 = make_valid_batch(batch_id="batch-reg-rate-2", timestamp=t1, interval_seconds=1.0)
    b2["regional_traffic"]["region-a"]["requests_total"] = 130            # +30 requests
    b2["regional_traffic"]["region-a"]["request_payload_bytes"] = 13000   # +3000 bytes egress
    b2["regional_traffic"]["region-a"]["response_payload_bytes"] = 36000  # +6000 bytes ingress
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=b2,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )

    r2 = (await client.get("/api/v1/traffic/regions")).json()
    reg_a = r2["regions"]["region-a"]
    assert reg_a["requests_total"] == 130
    assert reg_a["upstream_request_bytes"] == 13000
    assert reg_a["upstream_response_bytes"] == 36000
    assert reg_a["request_rate"] > 0.0
    assert reg_a["upstream_egress_rate"] > 0.0
    assert reg_a["upstream_ingress_rate"] > 0.0

    # Batch 3: Counter reset (counters drop to low numbers after gateway restart)
    t2 = datetime.now(timezone.utc) + timedelta(seconds=2)
    b3 = make_valid_batch(batch_id="batch-reg-rate-3", timestamp=t2, interval_seconds=1.0)
    b3["regional_traffic"]["region-a"]["requests_total"] = 5
    b3["regional_traffic"]["region-a"]["request_payload_bytes"] = 500
    b3["regional_traffic"]["region-a"]["response_payload_bytes"] = 1200
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=b3,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )

    r3 = (await client.get("/api/v1/traffic/regions")).json()
    reg_a_reset = r3["regions"]["region-a"]
    assert reg_a_reset["requests_total"] == 5
    assert reg_a_reset["request_rate"] >= 0.0
    assert reg_a_reset["upstream_egress_rate"] >= 0.0
    assert reg_a_reset["upstream_ingress_rate"] >= 0.0


@pytest.mark.asyncio
async def test_recent_events_pagination_newest_first_and_filtering(client: AsyncClient):
    """
    Verifies /api/v1/traffic/recent-events returns newest events first, provides full schema,
    supports pagination, and filters by criteria.
    """
    t_now = datetime.now(timezone.utc)
    events = [
        {
            "id": f"evt-{i}",
            "request_id": f"req-{i}",
            "timestamp": (t_now - timedelta(seconds=10 - i)).isoformat(),
            "method": "POST" if i % 2 == 0 else "GET",
            "endpoint": f"/api/ecommerce/item/{i}",
            "client_region": "eu-central-1",
            "served_region": "region-a" if i < 3 else "region-b",
            "request_type": "write" if i % 2 == 0 else "eventual_read",
            "rate_limiter_decision": "accepted",
            "status_code": 200,
            "duration_ms": 10.0 + i,
            "request_payload_bytes": 100 * i,
            "response_payload_bytes": 200 * i,
            "request_category": "order_checkout" if i % 2 == 0 else "product_read",
            "upstream_region": "region-a" if i < 3 else "region-b",
            "upstream_request_bytes": 100 * i,
            "upstream_response_bytes": 200 * i,
            "traffic_source": "online_store" if i < 4 else "synthetic_load",
        }
        for i in range(6)
    ]
    batch = make_valid_batch(batch_id="batch-events-rich")
    batch["events"] = events
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )

    # 1. Fetch newest events (page 1, page_size 2)
    resp = await client.get("/api/v1/traffic/recent-events?page=1&page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 6
    assert len(data["events"]) == 2
    # Newest first: evt-5 must be the first item
    assert data["events"][0]["id"] == "evt-5"
    assert data["events"][0]["request_id"] == "req-5"
    assert data["events"][1]["id"] == "evt-4"

    # Verify all required event fields are present
    first_evt = data["events"][0]
    for field in [
        "id", "request_id", "timestamp", "method", "endpoint", "client_region",
        "served_region", "status_code", "request_payload_bytes", "response_payload_bytes",
        "duration_ms", "request_type", "request_category", "traffic_source",
        "upstream_region", "upstream_request_bytes", "upstream_response_bytes"
    ]:
        assert field in first_evt, f"Missing field in event model: {field}"

    # 2. Filter by served_region='region-b' (events 3, 4, 5)
    r_filtered = await client.get("/api/v1/traffic/recent-events?served_region=region-b")
    assert r_filtered.status_code == 200
    d_filtered = r_filtered.json()
    assert d_filtered["total"] == 3
    for ev in d_filtered["events"]:
        assert ev["served_region"] == "region-b"

    # 3. Filter by traffic_source='synthetic_load' (only event 4 and 5)
    r_source = await client.get("/api/v1/traffic/recent-events?traffic_source=synthetic_load")
    assert r_source.status_code == 200
    assert r_source.json()["total"] == 2


@pytest.mark.asyncio
async def test_event_deduplication_on_batch_submission(client: AsyncClient):
    """Verifies that events with duplicate IDs submitted across batches are not duplicated."""
    ev1 = {
        "id": "evt-dup-target",
        "request_id": "req-dup-target",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "GET",
        "endpoint": "/api/ecommerce/products",
        "client_region": "eu-central-1",
        "served_region": "region-a",
        "request_type": "eventual_read",
        "rate_limiter_decision": "accepted",
        "status_code": 200,
        "duration_ms": 12.0,
        "request_payload_bytes": 0,
        "response_payload_bytes": 350,
        "traffic_source": "online_store",
    }
    b1 = make_valid_batch(batch_id="batch-ev-dup-1")
    b1["events"] = [ev1]
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=b1,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )

    # Ingest a second different batch containing the same event ID
    b2 = make_valid_batch(batch_id="batch-ev-dup-2")
    b2["events"] = [ev1]
    await client.post(
        "/internal/telemetry/traffic-batch",
        json=b2,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )

    res = await client.get("/api/v1/traffic/recent-events")
    assert res.status_code == 200
    events = res.json()["events"]
    matching = [e for e in events if e["id"] == "evt-dup-target"]
    assert len(matching) == 1, "Duplicate event ID was not deduplicated!"


@pytest.mark.asyncio
async def test_controller_sse_event_and_metric_broadcasts(client: AsyncClient):
    """
    Verifies that when a batch arrives:
    1. 'traffic_metric' is broadcast.
    2. 'traffic_event' is broadcast for each newly accepted event.
    3. Duplicate batch submissions do not broadcast duplicate events.
    """
    queue = await traffic_service.subscribe_sse()
    try:
        ev = {
            "id": "evt-sse-broadcast-1",
            "request_id": "req-sse-broadcast-1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": "POST",
            "endpoint": "/api/ecommerce/cart",
            "client_region": "ap-south-1",
            "served_region": "region-a",
            "request_type": "write",
            "rate_limiter_decision": "accepted",
            "status_code": 201,
            "duration_ms": 25.0,
            "request_payload_bytes": 300,
            "response_payload_bytes": 600,
            "traffic_source": "online_store",
        }
        b = make_valid_batch(batch_id="batch-sse-broadcaster")
        b["events"] = [ev]

        await client.post(
            "/internal/telemetry/traffic-batch",
            json=b,
            headers={"X-Internal-Secret": "internal-secret-token"},
        )

        # We should receive 2 messages: 1 traffic_metric and 1 traffic_event
        received_types = []
        for _ in range(2):
            msg = await asyncio.wait_for(queue.get(), timeout=2.0)
            received_types.append(msg["event"])
            if msg["event"] == "traffic_event":
                assert msg["data"]["id"] == "evt-sse-broadcast-1"
                assert msg["data"]["request_id"] == "req-sse-broadcast-1"
                assert msg["data"]["endpoint"] == "/api/ecommerce/cart"

        assert "traffic_metric" in received_types
        assert "traffic_event" in received_types

        # Submit duplicate batch: should be rejected as duplicate and emit NO new SSE messages
        await client.post(
            "/internal/telemetry/traffic-batch",
            json=b,
            headers={"X-Internal-Secret": "internal-secret-token"},
        )
        assert queue.empty()
    finally:
        await traffic_service.unsubscribe_sse(queue)


def test_utc_naive_and_aware_helpers():
    """Verifies that to_utc_naive and to_utc_aware handle naive, UTC-aware, and offset-aware datetimes."""
    # 1. Naive datetime: treated as UTC
    naive_dt = datetime(2026, 11, 19, 20, 22, 55)
    res_naive = to_utc_naive(naive_dt)
    assert res_naive.tzinfo is None
    assert res_naive == naive_dt

    res_aware = to_utc_aware(naive_dt)
    assert res_aware.tzinfo == timezone.utc
    assert res_aware.year == 2026 and res_aware.hour == 20

    # 2. Aware UTC datetime: strips tzinfo only after conversion
    aware_utc = datetime(2026, 11, 19, 20, 22, 55, tzinfo=timezone.utc)
    res_naive = to_utc_naive(aware_utc)
    assert res_naive.tzinfo is None
    assert res_naive == datetime(2026, 11, 19, 20, 22, 55)

    res_aware = to_utc_aware(aware_utc)
    assert res_aware.tzinfo == timezone.utc
    assert res_aware == aware_utc

    # 3. Aware non-UTC offset datetime (+05:30)
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    aware_ist = datetime(2026, 11, 20, 1, 52, 55, tzinfo=ist_tz)
    res_naive = to_utc_naive(aware_ist)
    assert res_naive.tzinfo is None
    # 2026-11-20 01:52:55+05:30 is 2026-11-19 20:22:55 UTC
    assert res_naive == datetime(2026, 11, 19, 20, 22, 55)

    res_aware = to_utc_aware(aware_ist)
    assert res_aware.tzinfo == timezone.utc
    assert res_aware.day == 19 and res_aware.hour == 20 and res_aware.minute == 22

    # 4. Aware negative offset datetime (-05:00)
    est_tz = timezone(timedelta(hours=-5))
    aware_est = datetime(2026, 11, 19, 15, 22, 55, tzinfo=est_tz)
    res_naive = to_utc_naive(aware_est)
    assert res_naive.tzinfo is None
    assert res_naive == datetime(2026, 11, 19, 20, 22, 55)


@pytest.mark.asyncio
async def test_ingest_timezone_aware_utc_timestamp(client: AsyncClient, db_session: AsyncSession):
    """
    Verifies that a batch with a timezone-aware UTC timestamp is ingested properly,
    persisted as UTC-naive in PostgreSQL/SQLite, while kept aware in in-memory structures and API.
    """
    ts_aware = datetime(2026, 11, 19, 20, 22, 55, tzinfo=timezone.utc)
    batch = make_valid_batch(batch_id="batch-tz-aware-utc", timestamp=ts_aware)
    assert batch["timestamp"] == "2026-11-19T20:22:55+00:00"

    resp = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "accepted"

    # Verify DB persistence: must be UTC-naive!
    res = await db_session.execute(
        select(TrafficSampleEntity).where(TrafficSampleEntity.batch_id == "batch-tz-aware-utc")
    )
    sample = res.scalar_one_or_none()
    assert sample is not None
    assert sample.timestamp.tzinfo is None
    assert sample.timestamp == datetime(2026, 11, 19, 20, 22, 55)

    # In-memory structures must keep aware UTC
    latest = traffic_service._latest_sample
    assert latest is not None
    assert latest["timestamp"].tzinfo is not None
    assert latest["timestamp"].utcoffset() == timedelta(0)

    # API summary response must be timezone-aware
    summary_resp = await client.get("/api/v1/traffic/summary")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["last_received_timestamp"] is not None
    assert "+00:00" in summary_data["last_received_timestamp"] or "Z" in summary_data["last_received_timestamp"]


@pytest.mark.asyncio
async def test_ingest_timestamp_with_non_utc_offset(client: AsyncClient, db_session: AsyncSession):
    """
    Verifies that a batch with a non-UTC offset (e.g. +05:30) is correctly converted to UTC-naive
    upon database persistence, preventing asyncpg 'can't subtract offset-naive and offset-aware datetimes'.
    """
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    # 2026-11-20 01:52:55 +05:30 corresponds to 2026-11-19 20:22:55 UTC
    ts_ist = datetime(2026, 11, 20, 1, 52, 55, tzinfo=ist_tz)
    batch = make_valid_batch(batch_id="batch-tz-non-utc", timestamp=ts_ist)

    resp = await client.post(
        "/internal/telemetry/traffic-batch",
        json=batch,
        headers={"X-Internal-Secret": "internal-secret-token"},
    )
    assert resp.status_code == 200, resp.text

    # Verify DB persistence: must be converted to UTC and be naive
    res = await db_session.execute(
        select(TrafficSampleEntity).where(TrafficSampleEntity.batch_id == "batch-tz-non-utc")
    )
    sample = res.scalar_one_or_none()
    assert sample is not None
    assert sample.timestamp.tzinfo is None
    assert sample.timestamp == datetime(2026, 11, 19, 20, 22, 55)


@pytest.mark.asyncio
async def test_timeseries_and_retention_pruning_with_naive_timestamps(client: AsyncClient, db_session: AsyncSession):
    """
    Verifies that prune_old_samples and get_traffic_timeseries query boundaries correctly use
    UTC-naive timestamps against the database, preventing offset-naive vs offset-aware comparison errors.
    """
    now = datetime.now(timezone.utc)
    t_old_aware = now - timedelta(hours=48)
    t_recent_aware = now - timedelta(seconds=120)

    # Insert historical samples with UTC-naive timestamps as asyncpg stores them
    sample_old = TrafficSampleEntity(
        batch_id="batch-prune-old",
        gateway_instance_id="gateway-1",
        timestamp=to_utc_naive(t_old_aware),
        interval_seconds=1.0,
        client_ingress_bytes=1000,
        client_egress_bytes=2000,
        client_ingress_rate=100.0,
        client_egress_rate=200.0,
        upstream_ingress_bytes=800,
        upstream_egress_bytes=400,
        upstream_ingress_rate=80.0,
        upstream_egress_rate=40.0,
        request_count=10,
        request_rate=1.0,
        status_2xx=10,
        status_3xx=0,
        status_4xx=0,
        status_5xx=0,
        rate_limited_429=0,
        latency_avg_ms=15.0,
        latency_p50_ms=12.0,
        latency_p95_ms=25.0,
        latency_p99_ms=40.0,
        regional_traffic_json={},
        traffic_sources_json={},
        dropped_telemetry_count=0,
    )
    sample_recent = TrafficSampleEntity(
        batch_id="batch-prune-recent",
        gateway_instance_id="gateway-1",
        timestamp=to_utc_naive(t_recent_aware),
        interval_seconds=1.0,
        client_ingress_bytes=5000,
        client_egress_bytes=10000,
        client_ingress_rate=500.0,
        client_egress_rate=1000.0,
        upstream_ingress_bytes=4000,
        upstream_egress_bytes=2000,
        upstream_ingress_rate=400.0,
        upstream_egress_rate=200.0,
        request_count=50,
        request_rate=5.0,
        status_2xx=50,
        status_3xx=0,
        status_4xx=0,
        status_5xx=0,
        rate_limited_429=0,
        latency_avg_ms=15.0,
        latency_p50_ms=12.0,
        latency_p95_ms=25.0,
        latency_p99_ms=40.0,
        regional_traffic_json={},
        traffic_sources_json={},
        dropped_telemetry_count=0,
    )
    db_session.add_all([sample_old, sample_recent])
    await db_session.commit()

    # Query timeseries: database query boundaries (cutoff and oldest_mem_ts) must not fail with comparison errors
    ts_resp = await client.get("/api/v1/traffic/timeseries?time_range_seconds=300&step_seconds=1")
    assert ts_resp.status_code == 200
    ts_data = ts_resp.json()
    assert ts_data["point_count"] >= 1
    for pt in ts_data["points"]:
        # All returned points must have timezone-aware timestamps
        pt_dt = datetime.fromisoformat(pt["timestamp"])
        assert pt_dt.tzinfo is not None

    # Prune old samples: prune_old_samples must delete sample_old (> 24h) and keep sample_recent
    deleted = await traffic_service.prune_old_samples(db_session, retention_hours=24)
    assert deleted >= 1

    # Verify sample_old is gone and sample_recent remains
    res_old = await db_session.execute(
        select(TrafficSampleEntity).where(TrafficSampleEntity.batch_id == "batch-prune-old")
    )
    assert res_old.scalar_one_or_none() is None

    res_recent = await db_session.execute(
        select(TrafficSampleEntity).where(TrafficSampleEntity.batch_id == "batch-prune-recent")
    )
    assert res_recent.scalar_one_or_none() is not None
