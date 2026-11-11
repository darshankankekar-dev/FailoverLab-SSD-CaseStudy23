import pytest
import httpx
from unittest.mock import patch
from src.replicator import ReplicationEngine


@pytest.mark.asyncio
async def test_worker_health_and_metrics_endpoints(client):
    # Health probe
    h_resp = await client.get("/health")
    assert h_resp.status_code == 200
    assert h_resp.json()["status"] == "alive"

    # Status / Metrics probe
    s_resp = await client.get("/status")
    assert s_resp.status_code == 200
    data = s_resp.json()
    assert "source_region" in data
    assert "target_region" in data
    assert "lag_metrics" in data


@pytest.mark.asyncio
async def test_worker_pause_resume_controls(client):
    # Pause replication
    p_resp = await client.post("/controls/pause")
    assert p_resp.status_code == 200
    assert p_resp.json()["is_paused"] is True

    # Health reflects paused
    h_resp = await client.get("/health")
    assert h_resp.json()["is_paused"] is True

    # Resume replication
    r_resp = await client.post("/controls/resume")
    assert r_resp.status_code == 200
    assert r_resp.json()["is_paused"] is False


@pytest.mark.asyncio
async def test_worker_delay_control(client):
    d_resp = await client.post("/controls/delay", json={"delay_seconds": 8.4})
    assert d_resp.status_code == 200
    assert d_resp.json()["injected_delay_sec"] == 8.4

    # Verify metrics reflects delay
    s_resp = await client.get("/status")
    assert s_resp.json()["injected_delay_sec"] == 8.4


@pytest.mark.asyncio
async def test_replication_reversal_on_failover():
    worker = ReplicationEngine()
    assert worker.source_region == "region-a"
    assert worker.target_region == "region-b"

    # Real httpx.Response returning active_region == 'region-b'
    mock_resp = httpx.Response(
        status_code=200,
        json={"active_region": "region-b"},
        request=httpx.Request("GET", "http://localhost:8000/api/v1/state"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        new_active = await worker.fetch_controller_active_region()
        assert new_active == "region-b"
        assert worker.source_region == "region-b"
        assert worker.target_region == "region-a"
        assert worker.reversal_count == 1
        assert worker.last_replicated_seq == 0


@pytest.mark.asyncio
async def test_replication_delivery_failure_preserves_cursor():
    worker = ReplicationEngine()
    worker.last_replicated_seq = 5

    # Outbox returns 1 new event (highest_seq=6)
    outbox_resp = httpx.Response(
        status_code=200,
        json={
            "events": [
                {
                    "event_id": "e-6",
                    "sequence_id": 6,
                    "record_key": "k-6",
                    "operation": "INSERT",
                    "payload": {},
                    "version": 1,
                    "fencing_epoch": 101,
                    "created_at": "2026-11-01T15:00:00Z",
                }
            ],
            "highest_sequence_id": 6,
            "unreplicated_count": 1,
        },
        request=httpx.Request("GET", "http://localhost:8001/internal/replication/outbox"),
    )

    # Controller state returns region-a
    controller_resp = httpx.Response(
        status_code=200,
        json={"active_region": "region-a"},
        request=httpx.Request("GET", "http://localhost:8000/api/v1/state"),
    )

    async def mock_get(self, url, **kwargs):
        if "state" in str(url):
            return controller_resp
        return outbox_resp

    # Target delivery failure (HTTP 500)
    target_resp = httpx.Response(
        status_code=500,
        text="Database disk full",
        request=httpx.Request("POST", "http://localhost:8002/internal/replication/apply"),
    )

    with patch("httpx.AsyncClient.get", new=mock_get), \
         patch("httpx.AsyncClient.post", return_value=target_resp):
        result = await worker.sync_iteration()
        assert result["status"] == "TARGET_APPLY_FAILED"
        # Cursor MUST NOT be updated on failure!
        assert worker.last_replicated_seq == 5
