import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from src.models import (
    RegionEntity,
    PolicyEntity,
    ControllerStateEntity,
    ReplicationEntity,
    QuorumVoterEntity,
)
from src.schemas import ControllerState, TransitionStatus
from src.domain.safety_gates import check_failback_readiness
from src.domain.candidate_selector import select_best_standby_candidate
from src.services.health_monitor import evaluate_primary_health_probes
from src.services.failback_workflow import execute_failback_workflow
from src.services.failover_workflow import execute_failover_workflow
from src.services.state_service import get_full_state


@pytest.mark.asyncio
async def test_failback_readiness_target_checkpoint_evaluation():
    """Requirement 5: Failback readiness check uses target region's actual replication checkpoint/freshness."""
    # 1. Target region healthy and synced -> Passes
    g_pass = check_failback_readiness(
        target_health="HEALTHY",
        replication_status="SYNCED",
        lag_seconds=0.4,
        acceptable_lag_sec=5.0,
        applied_sequence=1200,
        source_sequence=1200,
        target_name="Mumbai",
    )
    assert g_pass.passed is True
    assert "Failback readiness verified" in g_pass.reason

    # 2. Target region has excessive replication lag -> Blocked
    g_lag = check_failback_readiness(
        target_health="HEALTHY",
        replication_status="DEGRADED",
        lag_seconds=8.5,
        acceptable_lag_sec=5.0,
        applied_sequence=1100,
        source_sequence=1200,
        target_name="Mumbai",
    )
    assert g_lag.passed is False
    assert "Reverse replication lag (8.5s)" in g_lag.reason

    # 3. Target region has unapplied sequence gap under high lag -> Blocked
    g_gap = check_failback_readiness(
        target_health="HEALTHY",
        replication_status="STREAMING",
        lag_seconds=6.0,
        acceptable_lag_sec=5.0,
        applied_sequence=1000,
        source_sequence=1050,
        target_name="Mumbai",
    )
    assert g_gap.passed is False
    assert "sequence gap" in g_gap.reason or "Reverse replication lag" in g_gap.reason


@pytest.mark.asyncio
async def test_failback_workflow_with_target_specific_checkpoint(db_session):
    """Requirement 5: End-to-end failback workflow validates target region's actual checkpoint."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.current_state = "SECONDARY_ACTIVE"
    c_state.active_region = "region-b"

    # Region A is recovering
    res_a = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()
    region_a.health = "HEALTHY"
    # Inject target-specific lag of 9.2s (> 5.0s limit) into Region A
    region_a.replication_lag_seconds = 9.2

    # Global replication row says 0.8s
    res_rep = await db_session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    rep = res_rep.scalar_one()
    rep.lag_seconds = 0.8
    rep.status = "SYNCED"

    res = await execute_failback_workflow(
        db_session,
        operator_id="operator-admin",
        confirmation=True,
        target_region="region-a",
    )
    # Must be BLOCKED because target Region A's actual lag is 9.2s!
    assert res.status == TransitionStatus.BLOCKED
    assert res.current_state == ControllerState.FAILOVER_BLOCKED
    assert "Reverse replication lag (9.2s)" in res.blocked_reason


@pytest.mark.asyncio
async def test_candidate_selection_ranks_by_authoritative_sequence():
    """Requirement 4: Candidate eligibility and failover use authoritative freshness information."""
    class DummyRegion:
        def __init__(self, rid, name, latency):
            self.id = rid
            self.name = name
            self.health = "HEALTHY"
            self.role = "STANDBY"
            self.is_fenced = False
            self.app_servers_healthy = 8
            self.app_servers_total = 8
            self.iops = 100
            self.applied_sequence = 0
            self.replication_lag_seconds = 0.8

    candidates = [
        DummyRegion("region-b", "Singapore", 42),
        DummyRegion("region-c", "Frankfurt", 110),
        DummyRegion("region-d", "Virginia", 180),
    ]

    # Frankfurt has highest applied sequence (1050 vs 1000 and 900)
    worker_sequences = {
        "region-b": 1000,
        "region-c": 1050,
        "region-d": 900,
    }
    worker_lags = {
        "region-b": 1.2,
        "region-c": 0.8,
        "region-d": 2.5,
    }

    selected, evals, summary = select_best_standby_candidate(
        regions=candidates,
        active_region_id="region-a",
        acceptable_lag_sec=5.0,
        preferred_target="auto",
        regional_lags=worker_lags,
        regional_sequences=worker_sequences,
    )

    assert selected is not None
    assert selected.region_id == "region-c"
    assert selected.applied_sequence == 1050


@pytest.mark.asyncio
async def test_health_monitoring_generalized_to_promoted_primary(db_session):
    """Requirement 9: Primary health monitoring generalized to currently active region."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    # Simulate that region-c is now the promoted active primary
    c_state.active_region = "region-c"
    c_state.current_state = "HEALTHY"
    c_state.consecutive_failures = 0

    res_c = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-c"))
    region_c = res_c.scalar_one()
    region_c.health = "DOWN"

    with patch("src.services.health_monitor.regional_client.get_health", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = {"status": "DOWN"}

        # Run health check pass
        await evaluate_primary_health_probes(db_session, simulated_time_delta=2.0)

        # Probed target must be region-c!
        mock_probe.assert_called_with("region-c")
        assert c_state.current_state == "PRIMARY_SUSPECTED"
        assert c_state.consecutive_failures == 1

        # Second failing probe
        await evaluate_primary_health_probes(db_session, simulated_time_delta=2.0)
        assert c_state.consecutive_failures == 2

        # Third failing probe triggers Quorum check on region-c
        await evaluate_primary_health_probes(db_session, simulated_time_delta=2.0)
        assert c_state.consecutive_failures == 3
        assert c_state.current_state == "QUORUM_CHECK"


@pytest.mark.asyncio
async def test_state_service_incorporates_replication_worker_telemetry(db_session):
    """Requirement 4: State service aggregates per-destination replication telemetry."""
    fake_worker_status = {
        "source_region": "region-a",
        "last_replicated_sequence_id": 550,
        "destinations": {
            "region-b": {
                "source_region": "region-a",
                "destination_region": "region-b",
                "source_sequence": 550,
                "applied_sequence": 550,
                "sequence_lag": 0,
                "time_lag_seconds": 0.45,
                "status": "SYNCED",
                "is_simulated_lag": False,
                "injected_delay_sec": 0.0,
                "retry_count": 0,
                "consecutive_failures": 0,
            },
            "region-c": {
                "source_region": "region-a",
                "destination_region": "region-c",
                "source_sequence": 550,
                "applied_sequence": 548,
                "sequence_lag": 2,
                "time_lag_seconds": 1.15,
                "status": "STREAMING",
                "is_simulated_lag": False,
                "injected_delay_sec": 0.0,
                "retry_count": 0,
                "consecutive_failures": 0,
            },
        },
    }

    with patch("src.services.state_service.replication_client.get_status", new_callable=AsyncMock) as mock_get_status:
        mock_get_status.return_value = fake_worker_status

        state = await get_full_state(db_session)
        destinations = state.replication.destinations

        assert "region-b" in destinations
        assert destinations["region-b"].applied_sequence == 550
        assert destinations["region-b"].sequence_lag == 0
        assert destinations["region-b"].time_lag_seconds == 0.45
        assert destinations["region-b"].status == "SYNCED"

        assert "region-c" in destinations
        assert destinations["region-c"].applied_sequence == 548
        assert destinations["region-c"].sequence_lag == 2
        assert destinations["region-c"].time_lag_seconds == 1.15
        assert destinations["region-c"].status == "STREAMING"
