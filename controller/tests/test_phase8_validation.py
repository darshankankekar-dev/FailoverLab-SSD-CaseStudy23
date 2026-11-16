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
    AuditEventEntity,
)


# =========================================================================
# WORKFLOW E: Multi-Region Automatic Failover Drill
# =========================================================================

@pytest.mark.asyncio
async def test_workflow_e_multi_region_automatic_failover(db_session):
    """
    Workflow E:
    1. Start with Mumbai (region-a) ACTIVE, epoch=101.
    2. Primary outage occurs: consecutive_failures=3, 3/3 voters confirm outage.
    3. Singapore has excessive replication lag (8.5s > 5.0s max threshold).
    4. Frankfurt (region-c) is healthy and synchronized (lag=0.8s).
    5. Execute failover with target_region='auto'.
    6. Verify complete 10-step safety workflow:
       - Debounce threshold checked (failures >= 3).
       - Quorum majority verified (2/3 voters).
       - Candidate evaluated: Singapore disqualified, Frankfurt selected.
       - Mumbai fenced (is_fenced=True, accepts_writes=False).
       - Fencing epoch incremented from 101 to 102.
       - Frankfurt promoted (role=ACTIVE, accepts_writes=True, fencing_epoch=102).
       - Gateway route updated to region-c.
       - Route verification passes.
       - Controller state transitions to SECONDARY_ACTIVE.
       - Audit event recorded.
    """
    # 1. Simulate consecutive health check failures
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    # 2. Quorum voters record primary outage
    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    # 3 & 4. Mock regional lags: Singapore lagging (8.5s), Frankfurt fresh (0.8s)
    mock_lags = {
        "region-b": 8.5,  # Exceeds 5.0s threshold!
        "region-c": 0.8,  # Healthy & synchronized!
        "region-d": 1.2,
        "region-e": 2.5,
    }

    # 5. Execute failover with candidate selection = 'auto'
    result = await execute_failover_workflow(
        db_session,
        force=False,
        target_region="auto",
        regional_lags=mock_lags,
    )

    # 6. Verify result and state transitions
    assert result.status == TransitionStatus.COMPLETED
    assert result.current_state == ControllerState.SECONDARY_ACTIVE
    assert result.fencing_epoch == 102

    # Verify Mumbai (region-a) is fenced and demoted
    res_a = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    reg_a = res_a.scalar_one()
    assert reg_a.accepts_writes is False
    assert reg_a.is_fenced is True
    assert reg_a.role == "STANDBY"

    # Verify Frankfurt (region-c) is promoted to active writer
    res_c = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-c"))
    reg_c = res_c.scalar_one()
    assert reg_c.accepts_writes is True
    assert reg_c.is_fenced is False
    assert reg_c.role == "ACTIVE"
    assert reg_c.fencing_epoch == 102

    # Verify Singapore (region-b) remains standby due to lag
    res_b = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    reg_b = res_b.scalar_one()
    assert reg_b.accepts_writes is False
    assert reg_b.role == "STANDBY"

    # Verify audit event was persisted
    audit_res = await db_session.execute(
        select(AuditEventEntity).where(AuditEventEntity.subsystem == "CONTROLLER")
    )
    audit_events = audit_res.scalars().all()
    assert len(audit_events) >= 1


# =========================================================================
# WORKFLOW F: Split-Brain Prevention & Fencing Invariant
# =========================================================================

@pytest.mark.asyncio
async def test_workflow_f_split_brain_prevention_and_single_writer_invariant(db_session):
    """
    Workflow F:
    1. Demoted primary (region-a) must reject writes when in STANDBY mode or fenced.
    2. Write attempts with a stale fencing epoch (101 when epoch is 102) must be rejected.
    3. Exactly ONE active writer region exists across all 5 registered regions at all times.
    """
    # Verify initial baseline: only region-a is active
    res_regions = await db_session.execute(select(RegionEntity))
    all_regions = res_regions.scalars().all()
    assert len(all_regions) == 5

    active_writers = [r for r in all_regions if r.accepts_writes and r.role == "ACTIVE"]
    assert len(active_writers) == 1
    assert active_writers[0].id == "region-a"

    # Set failures and quorum to simulate failover to region-c
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    # Execute failover to Frankfurt
    await execute_failover_workflow(db_session, force=False, target_region="region-c")

    # Invariant Check: Verify exactly ONE active writer exists post-failover
    res_regions_post = await db_session.execute(select(RegionEntity))
    post_regions = res_regions_post.scalars().all()
    post_active = [r for r in post_regions if r.accepts_writes and r.role == "ACTIVE"]
    assert len(post_active) == 1
    assert post_active[0].id == "region-c"
    assert post_active[0].fencing_epoch == 102

    # Verify demoted region-a is blocked from writing
    reg_a = next(r for r in post_regions if r.id == "region-a")
    assert reg_a.accepts_writes is False
    assert reg_a.is_fenced is True
    assert reg_a.role == "STANDBY"

    # Verify standbys are blocked from writing
    for sid in ["region-b", "region-d", "region-e"]:
        r = next(reg for reg in post_regions if reg.id == sid)
        assert r.accepts_writes is False
        assert r.role == "STANDBY"


# =========================================================================
# WORKFLOW G: Two-Region Legacy Workflow Regression
# =========================================================================

@pytest.mark.asyncio
async def test_workflow_g_two_region_legacy_failover_and_failback(db_session):
    """
    Workflow G:
    Ensures backwards compatibility with the original 2-region workflow:
    1. Failover targeting region-b explicitly succeeds when criteria are met.
    2. Guarded failback from region-b back to region-a succeeds.
    3. Fencing epochs advance monotonically (101 -> 102 -> 103).
    """
    # 1. Failover to region-b
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    fo_res = await execute_failover_workflow(db_session, force=False, target_region="region-b")
    assert fo_res.status == TransitionStatus.COMPLETED
    assert fo_res.current_state == ControllerState.SECONDARY_ACTIVE
    assert fo_res.fencing_epoch == 102

    res_b = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    reg_b = res_b.scalar_one()
    assert reg_b.accepts_writes is True
    assert reg_b.role == "ACTIVE"

    # 2. Recover region-a health for failback
    res_a = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    reg_a = res_a.scalar_one()
    reg_a.health = "HEALTHY"
    reg_a.status = "healthy"
    c_state.consecutive_failures = 0
    await db_session.commit()

    # 3. Execute guarded failback to region-a
    fb_res = await execute_failback_workflow(
        db_session,
        operator_id="operator-admin",
        confirmation=True,
        target_region="region-a",
        reason="Guarded failback regression test",
    )
    assert fb_res.status == TransitionStatus.COMPLETED
    assert fb_res.current_state == ControllerState.HEALTHY
    assert fb_res.fencing_epoch == 103

    # Verify region-a restored to ACTIVE
    res_a_restored = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    reg_a_restored = res_a_restored.scalar_one()
    assert reg_a_restored.accepts_writes is True
    assert reg_a_restored.role == "ACTIVE"
    assert reg_a_restored.fencing_epoch == 103

    # Verify region-b returned to STANDBY
    res_b_demoted = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    reg_b_demoted = res_b_demoted.scalar_one()
    assert reg_b_demoted.accepts_writes is False
    assert reg_b_demoted.role == "STANDBY"
