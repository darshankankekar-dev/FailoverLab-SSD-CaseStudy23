import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import select
from src.services.failover_workflow import execute_failover_workflow
from src.services.failback_workflow import execute_failback_workflow
from src.schemas import ControllerState, TransitionStatus
from src.models import (
    RegionEntity,
    PolicyEntity,
    ControllerStateEntity,
    ReplicationEntity,
    QuorumVoterEntity,
)


@pytest.mark.asyncio
async def test_1_mumbai_down_singapore_eligible_auto(db_session):
    """Scenario 1: Primary Mumbai down, all standbys healthy -> auto-selector picks Singapore (lowest latency)."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    res = await execute_failover_workflow(db_session, force=False, target_region="auto")

    assert res.status == TransitionStatus.COMPLETED
    assert res.current_state == ControllerState.SECONDARY_ACTIVE
    assert res.fencing_epoch == 102

    # Verify Mumbai fenced and Singapore promoted
    res_a = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    reg_a = res_a.scalar_one()
    assert reg_a.accepts_writes is False
    assert reg_a.is_fenced is True
    assert reg_a.role == "STANDBY"

    res_b = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    reg_b = res_b.scalar_one()
    assert reg_b.accepts_writes is True
    assert reg_b.is_fenced is False
    assert reg_b.role == "ACTIVE"
    assert reg_b.fencing_epoch == 102


@pytest.mark.asyncio
async def test_2_mumbai_down_singapore_lagging_frankfurt_eligible(db_session):
    """Scenario 2: Mumbai down, Singapore lagging (>5.0s) -> auto-selector selects healthy Frankfurt."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    # Singapore has excessive lag (8.4s), Frankfurt is fresh (0.8s)
    res = await execute_failover_workflow(
        db_session,
        force=False,
        target_region="auto",
        regional_lags={"region-b": 8.4, "region-c": 0.8, "region-d": 0.8, "region-e": 0.8},
    )

    assert res.status == TransitionStatus.COMPLETED
    assert res.current_state == ControllerState.SECONDARY_ACTIVE

    # Frankfurt promoted as active
    res_c = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-c"))
    reg_c = res_c.scalar_one()
    assert reg_c.accepts_writes is True
    assert reg_c.role == "ACTIVE"

    # Singapore remains standby
    res_b = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    reg_b = res_b.scalar_one()
    assert reg_b.accepts_writes is False
    assert reg_b.role == "STANDBY"


@pytest.mark.asyncio
async def test_3_singapore_down_virginia_eligible(db_session):
    """Scenario 3: Mumbai down, Singapore and Frankfurt DOWN -> auto-selector selects Virginia."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    # Break Singapore & Frankfurt
    res_b = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    res_b.scalar_one().health = "DOWN"
    res_c = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-c"))
    res_c.scalar_one().health = "DOWN"
    await db_session.commit()

    res = await execute_failover_workflow(db_session, force=False, target_region="auto")

    assert res.status == TransitionStatus.COMPLETED
    assert res.current_state == ControllerState.SECONDARY_ACTIVE

    # Virginia promoted
    res_d = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-d"))
    reg_d = res_d.scalar_one()
    assert reg_d.accepts_writes is True
    assert reg_d.role == "ACTIVE"


@pytest.mark.asyncio
async def test_4a_two_healthy_candidates_equal_sequence_latency_ranking(db_session):
    """Scenario 4a: Equal applied sequence -> lowest nominal latency candidate (Singapore, 34ms) wins over Frankfurt (115ms)."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    res_eq = await execute_failover_workflow(
        db_session,
        force=False,
        target_region="auto",
        regional_sequences={"region-b": 1000, "region-c": 1000, "region-d": 1000, "region-e": 1000},
    )
    assert res_eq.status == TransitionStatus.COMPLETED
    res_b = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    reg_b = res_b.scalar_one()
    assert reg_b.role == "ACTIVE"


@pytest.mark.asyncio
async def test_4b_candidate_ranking_freshness_overrides_latency(db_session):
    """Scenario 4b: Freshness overrides latency! Frankfurt has higher sequence (1500 > 1200) despite higher latency (115ms vs 34ms)."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    res_fresh = await execute_failover_workflow(
        db_session,
        force=False,
        target_region="auto",
        regional_sequences={"region-b": 1200, "region-c": 1500, "region-d": 1100, "region-e": 1000},
    )
    assert res_fresh.status == TransitionStatus.COMPLETED
    res_c = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-c"))
    reg_c = res_c.scalar_one()
    # Frankfurt was chosen due to freshness priority!
    assert reg_c.role == "ACTIVE"



@pytest.mark.asyncio
async def test_5_all_standby_candidates_unhealthy(db_session):
    """Scenario 5: All standby candidates unhealthy -> BLOCKED at Gate 3."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    # Mark all standbys DOWN
    for r_id in ["region-b", "region-c", "region-d", "region-e"]:
        res_r = await db_session.execute(select(RegionEntity).where(RegionEntity.id == r_id))
        res_r.scalar_one().health = "DOWN"
    await db_session.commit()

    res = await execute_failover_workflow(db_session, force=False, target_region="auto")
    assert res.status == TransitionStatus.BLOCKED
    assert res.current_state == ControllerState.FAILOVER_BLOCKED
    assert "Standby not ready" in res.message


@pytest.mark.asyncio
async def test_6_all_standby_candidates_exceeding_lag_threshold(db_session):
    """Scenario 6: All standbys exceed 5.0s acceptable lag threshold -> BLOCKED at Gate 4."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    res = await execute_failover_workflow(
        db_session,
        force=False,
        target_region="auto",
        regional_lags={"region-b": 8.5, "region-c": 9.2, "region-d": 12.0, "region-e": 15.0},
    )
    assert res.status == TransitionStatus.BLOCKED
    assert res.current_state == ControllerState.FAILOVER_BLOCKED
    assert "Excessive Replication Lag" in res.message


@pytest.mark.asyncio
async def test_7_insufficient_quorum(db_session):
    """Scenario 7: Only 1 voter reports outage (needs 2 of 3) -> BLOCKED at Gate 2."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    voters = res_voters.scalars().all()
    voters[0].vote = "PRIMARY_OUTAGE"
    voters[1].vote = "PRIMARY_HEALTHY"
    voters[2].vote = "PRIMARY_HEALTHY"
    await db_session.commit()

    res = await execute_failover_workflow(db_session, force=False, target_region="auto")
    assert res.status == TransitionStatus.BLOCKED
    assert res.current_state == ControllerState.FAILOVER_BLOCKED
    assert "Insufficient Quorum Majority" in res.message


@pytest.mark.asyncio
async def test_8_fencing_failure(db_session):
    """Scenario 8: Primary fencing fails -> BLOCKED at Gate 5."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    with patch("src.services.failover_workflow.regional_client.fence", new_callable=AsyncMock) as mock_fence:
        mock_fence.return_value = False
        res = await execute_failover_workflow(db_session, force=False, target_region="auto")

    assert res.status == TransitionStatus.BLOCKED
    assert res.current_state == ControllerState.FAILOVER_BLOCKED
    assert "Fencing not confirmed" in res.message


@pytest.mark.asyncio
async def test_9_promotion_failure(db_session):
    """Scenario 9: Standby promotion fails -> BLOCKED at Step 7."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    with patch("src.services.failover_workflow.regional_client.promote", new_callable=AsyncMock) as mock_promote:
        mock_promote.return_value = False
        res = await execute_failover_workflow(db_session, force=False, target_region="auto")

    assert res.status == TransitionStatus.BLOCKED
    assert res.current_state == ControllerState.FAILOVER_BLOCKED
    assert "Standby promotion failed" in res.message


@pytest.mark.asyncio
async def test_10_gateway_route_verification_failure(db_session):
    """Scenario 10: Synthetic gateway route verification probe fails -> BLOCKED at Gate 7."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    with patch("src.services.failover_workflow.gateway_client.probe_route", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = {"success": False, "message": "Gateway route probe failed: timeout"}
        res = await execute_failover_workflow(db_session, force=False, target_region="auto")

    assert res.status == TransitionStatus.BLOCKED
    assert res.current_state == ControllerState.FAILOVER_BLOCKED
    assert "Route probe verification failed" in res.message


@pytest.mark.asyncio
async def test_11_recovery_and_guarded_failback(db_session):
    """Scenario 11: Failover to Singapore -> Mumbai recovers -> deliberate guarded failback restores Mumbai."""
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    # Step A: Failover to Singapore
    res_fo = await execute_failover_workflow(db_session, force=False, target_region="region-b")
    assert res_fo.status == TransitionStatus.COMPLETED
    assert res_fo.current_state == ControllerState.SECONDARY_ACTIVE
    assert c_state.active_region == "region-b"

    # Step B: Mumbai recovers and is healthy as a standby
    res_a = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    reg_a = res_a.scalar_one()
    reg_a.health = "HEALTHY"
    reg_a.is_fenced = False
    reg_a.accepts_writes = False
    reg_a.role = "STANDBY"
    await db_session.commit()

    # Step C: Guarded failback without confirmation is BLOCKED
    res_fb_unconf = await execute_failback_workflow(
        db_session, operator_id="lead-sre", confirmation=False, target_region="region-a"
    )
    assert res_fb_unconf.status == TransitionStatus.BLOCKED

    # Step D: Guarded failback with confirmed operator authorization succeeds
    res_fb_conf = await execute_failback_workflow(
        db_session, operator_id="lead-sre", confirmation=True, target_region="region-a"
    )
    assert res_fb_conf.status == TransitionStatus.COMPLETED
    assert res_fb_conf.current_state == ControllerState.HEALTHY
    assert res_fb_conf.fencing_epoch == 103

    # Mumbai is active primary once again
    await db_session.refresh(reg_a)
    assert reg_a.accepts_writes is True
    assert reg_a.role == "ACTIVE"
    assert reg_a.fencing_epoch == 103

    # Singapore is safely fenced and standby
    res_b = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    reg_b = res_b.scalar_one()
    assert reg_b.accepts_writes is False
    assert reg_b.is_fenced is True
    assert reg_b.role == "STANDBY"
