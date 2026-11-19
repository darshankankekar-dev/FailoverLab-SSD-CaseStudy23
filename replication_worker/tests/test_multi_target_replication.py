import pytest
import httpx
from unittest.mock import patch
from src.replicator import ReplicationEngine
from src.lag_tracker import lag_tracker


@pytest.mark.asyncio
async def test_multi_target_replication_all_standbys_success():
    """
    Verifies that the replication engine reads outbox from the active primary (region-a)
    and successfully replicates to all 4 standby destinations:
    region-b (Singapore), region-c (Frankfurt), region-d (Virginia), region-e (São Paulo).
    """
    worker = ReplicationEngine()
    assert worker.source_region == "region-a"
    assert set(worker.target_regions) == {"region-b", "region-c", "region-d", "region-e"}

    # Mock controller state: region-a is active
    controller_resp = httpx.Response(
        status_code=200,
        json={"active_region": "region-a", "fencing_epoch": 101},
        request=httpx.Request("GET", "http://localhost:8000/api/v1/state"),
    )

    # Mock outbox with 3 ordered events
    outbox_events = [
        {
            "event_id": f"evt-{i}",
            "sequence_id": i,
            "sequence_number": i,
            "record_key": f"order-{i}",
            "operation": "INSERT",
            "payload": {"item": f"SKU-{i}", "qty": 1},
            "version": 1,
            "fencing_epoch": 101,
            "created_at": f"2026-11-01T15:00:0{i}Z",
        }
        for i in range(1, 4)
    ]
    outbox_resp = httpx.Response(
        status_code=200,
        json={
            "events": outbox_events,
            "highest_sequence_id": 3,
            "unreplicated_count": 3,
        },
        request=httpx.Request("GET", "http://localhost:8001/internal/replication/outbox"),
    )

    # Mock apply response for any target standby
    apply_resp = httpx.Response(
        status_code=200,
        json={
            "applied_count": 3,
            "skipped_duplicates": 0,
            "highest_sequence_id": 3,
        },
        request=httpx.Request("POST", "http://target/internal/replication/apply"),
    )

    async def mock_get(self, url, **kwargs):
        if "state" in str(url):
            return controller_resp
        return outbox_resp

    async def mock_post(self, url, **kwargs):
        return apply_resp

    with patch("httpx.AsyncClient.get", new=mock_get), patch("httpx.AsyncClient.post", new=mock_post):
        result = await worker.sync_iteration()

    assert result["status"] == "SYNCED"
    assert result["source_region"] == "region-a"

    # All 4 destinations must have independently received and applied events
    for dest in ["region-b", "region-c", "region-d", "region-e"]:
        assert dest in result["destinations"]
        assert result["destinations"][dest]["status"] == "SYNCED"
        assert result["destinations"][dest]["applied_count"] == 3
        assert worker.target_states[dest].last_applied_seq == 3

    assert worker.last_replicated_seq == 3


@pytest.mark.asyncio
async def test_multi_target_independent_failure_and_partial_sync():
    """
    Verifies that failure of one destination (Frankfurt / region-c)
    does NOT halt or block replication to the other three standbys.
    """
    worker = ReplicationEngine()

    controller_resp = httpx.Response(
        status_code=200,
        json={"active_region": "region-a", "fencing_epoch": 101},
        request=httpx.Request("GET", "http://localhost:8000/api/v1/state"),
    )

    outbox_resp = httpx.Response(
        status_code=200,
        json={
            "events": [
                {
                    "event_id": "evt-10",
                    "sequence_id": 10,
                    "sequence_number": 10,
                    "record_key": "order-10",
                    "operation": "INSERT",
                    "payload": {"cart_id": "c1"},
                    "version": 1,
                    "fencing_epoch": 101,
                    "created_at": "2026-11-01T15:00:10Z",
                }
            ],
            "highest_sequence_id": 10,
            "unreplicated_count": 1,
        },
        request=httpx.Request("GET", "http://localhost:8001/internal/replication/outbox"),
    )

    # Success response for regions B, D, E
    success_apply_resp = httpx.Response(
        status_code=200,
        json={"applied_count": 1, "skipped_duplicates": 0, "highest_sequence_id": 10},
        request=httpx.Request("POST", "http://target/internal/replication/apply"),
    )

    # Failure response specifically for region-c (Frankfurt HTTP 500)
    fail_apply_resp = httpx.Response(
        status_code=500,
        text="Region C database volume full",
        request=httpx.Request("POST", "http://localhost:8004/internal/replication/apply"),
    )

    async def mock_get(self, url, **kwargs):
        if "state" in str(url):
            return controller_resp
        return outbox_resp

    async def mock_post(self, url, **kwargs):
        # Fail only region-c (port 8004)
        if "8004" in str(url) or "region-c" in str(url):
            return fail_apply_resp
        return success_apply_resp

    with patch("httpx.AsyncClient.get", new=mock_get), patch("httpx.AsyncClient.post", new=mock_post):
        result = await worker.sync_iteration()

    # Overall status is PARTIAL_SYNC because 3 succeeded and 1 failed
    assert result["status"] == "PARTIAL_SYNC"

    # Region C failed independently
    assert result["destinations"]["region-c"]["status"] == "TARGET_APPLY_FAILED"
    assert worker.target_states["region-c"].last_applied_seq == 0
    assert worker.target_states["region-c"].retry_count == 1
    assert worker.target_states["region-c"].consecutive_errors == 1

    # Regions B, D, and E succeeded completely
    for dest in ["region-b", "region-d", "region-e"]:
        assert result["destinations"][dest]["status"] == "SYNCED"
        assert worker.target_states[dest].last_applied_seq == 10
        assert worker.target_states[dest].consecutive_errors == 0


@pytest.mark.asyncio
async def test_failed_destination_catchup_after_recovery():
    """
    Verifies that after Region C recovers, a subsequent synchronization pass
    re-attempts replication to Region C and safely catches it up.
    """
    worker = ReplicationEngine()
    # Pre-set: Regions B, D, E are already at seq 10, C is at 0
    for dest in ["region-b", "region-d", "region-e"]:
        ts = worker._get_or_create_target_state(dest)
        ts.last_applied_seq = 10
    ts_c = worker._get_or_create_target_state("region-c")
    ts_c.last_applied_seq = 0
    ts_c.consecutive_errors = 1
    ts_c.backoff_until = 0.0  # Expired backoff for immediate retry

    controller_resp = httpx.Response(
        status_code=200,
        json={"active_region": "region-a", "fencing_epoch": 101},
        request=httpx.Request("GET", "http://localhost:8000/api/v1/state"),
    )

    outbox_resp = httpx.Response(
        status_code=200,
        json={
            "events": [
                {
                    "event_id": "evt-10",
                    "sequence_id": 10,
                    "sequence_number": 10,
                    "record_key": "order-10",
                    "operation": "INSERT",
                    "payload": {"cart_id": "c1"},
                    "version": 1,
                    "fencing_epoch": 101,
                    "created_at": "2026-11-01T15:00:10Z",
                }
            ],
            "highest_sequence_id": 10,
            "unreplicated_count": 0,
        },
        request=httpx.Request("GET", "http://localhost:8001/internal/replication/outbox"),
    )

    # Now Region C succeeds
    apply_resp = httpx.Response(
        status_code=200,
        json={"applied_count": 1, "skipped_duplicates": 0, "highest_sequence_id": 10},
        request=httpx.Request("POST", "http://localhost:8004/internal/replication/apply"),
    )

    async def mock_get(self, url, **kwargs):
        if "state" in str(url):
            return controller_resp
        return outbox_resp

    with patch("httpx.AsyncClient.get", new=mock_get), patch("httpx.AsyncClient.post", return_value=apply_resp):
        result = await worker.sync_iteration()

    # Region C has now caught up
    assert worker.target_states["region-c"].last_applied_seq == 10
    assert worker.target_states["region-c"].consecutive_errors == 0
    assert worker.last_replicated_seq == 10


@pytest.mark.asyncio
async def test_checkpoint_initialization_on_worker_startup():
    """
    Verifies that calling init_target_checkpoint queries the target standby
    and initializes its cursor to the last applied sequence, preventing replay from 0.
    """
    worker = ReplicationEngine()

    chk_resp = httpx.Response(
        status_code=200,
        json={
            "region_id": "region-b",
            "last_applied_sequence_id": 42,
            "last_applied_at": "2026-11-01T16:00:00Z",
        },
        request=httpx.Request("GET", "http://localhost:8002/internal/replication/checkpoint"),
    )

    with patch("httpx.AsyncClient.get", return_value=chk_resp):
        seq = await worker.init_target_checkpoint("region-b")

    assert seq == 42
    assert worker.target_states["region-b"].last_applied_seq == 42
    assert worker.target_states["region-b"].initialized is True


@pytest.mark.asyncio
async def test_failover_reverses_replication_direction_to_all_standbys():
    """
    Verifies that upon failover to Frankfurt (region-c), the worker dynamically
    reconfigures its source to region-c and replicates to all remaining 4 regions:
    region-a (Mumbai), region-b (Singapore), region-d (Virginia), region-e (São Paulo).
    """
    worker = ReplicationEngine()
    assert worker.source_region == "region-a"

    # Controller announces region-c has been promoted to ACTIVE with epoch 102
    failover_state_resp = httpx.Response(
        status_code=200,
        json={"active_region": "region-c", "fencing_epoch": 102},
        request=httpx.Request("GET", "http://localhost:8000/api/v1/state"),
    )

    with patch("httpx.AsyncClient.get", return_value=failover_state_resp):
        active = await worker.fetch_controller_active_region()

    assert active == "region-c"
    assert worker.source_region == "region-c"
    assert worker.active_epoch == 102
    assert worker.reversal_count == 1

    # Remaining 4 regions must be the targets
    expected_targets = {"region-a", "region-b", "region-d", "region-e"}
    assert set(worker.target_regions) == expected_targets
