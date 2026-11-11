import pytest
from sqlalchemy import select
from src.services.failover_workflow import execute_failover_workflow
from src.schemas import ControllerState, TransitionStatus
from src.models import (
    RegionEntity,
    PolicyEntity,
    ControllerStateEntity,
    ReplicationEntity,
    QuorumVoterEntity,
)


@pytest.mark.asyncio
async def test_failover_blocked_debounce_threshold(db_session):
    # consecutive_failures is 0, threshold is 3 -> blocked at Step 1
    res = await execute_failover_workflow(db_session, force=False)
    assert res.status == TransitionStatus.BLOCKED
    assert res.current_state == ControllerState.FAILOVER_BLOCKED
    assert "Debounce threshold not met" in res.message


@pytest.mark.asyncio
async def test_failover_blocked_insufficient_quorum(db_session):
    # Set failures = 3 to pass Gate 1
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    # All voters are PRIMARY_HEALTHY (0 outage votes) -> blocked at Step 2
    res = await execute_failover_workflow(db_session, force=False)
    assert res.status == TransitionStatus.BLOCKED
    assert res.current_state == ControllerState.FAILOVER_BLOCKED
    assert "Insufficient Quorum Majority" in res.message


@pytest.mark.asyncio
async def test_failover_blocked_standby_unready(db_session):
    # Pass Gate 1 & 2
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    # Break Region B health
    res_b = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    region_b = res_b.scalar_one()
    region_b.health = "DOWN"

    res = await execute_failover_workflow(db_session, force=False)
    assert res.status == TransitionStatus.BLOCKED
    assert res.current_state == ControllerState.FAILOVER_BLOCKED
    assert "Standby not ready" in res.message


@pytest.mark.asyncio
async def test_failover_blocked_excessive_replication_lag(db_session):
    # Pass Gate 1, 2, 3
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    # Set replication lag to 8.4s (> 5.0s limit)
    res_rep = await db_session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    rep = res_rep.scalar_one()
    rep.status = "DEGRADED"
    rep.lag_seconds = 8.4

    res = await execute_failover_workflow(db_session, force=False)
    assert res.status == TransitionStatus.BLOCKED
    assert res.current_state == ControllerState.FAILOVER_BLOCKED
    assert "Excessive Replication Lag" in res.message


@pytest.mark.asyncio
async def test_failover_successful_10_steps(db_session):
    # Pass all conditions: failures=3, quorum voters=3 outage, standby=HEALTHY, lag=0.8s
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    # Execute workflow
    res = await execute_failover_workflow(db_session, force=False)

    assert res.status == TransitionStatus.COMPLETED
    assert res.current_state == ControllerState.SECONDARY_ACTIVE
    assert res.fencing_epoch == 102

    # Verify database side effects
    res_a = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()
    assert region_a.accepts_writes is False
    assert region_a.is_fenced is True
    assert region_a.role == "STANDBY"

    res_b = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    region_b = res_b.scalar_one()
    assert region_b.accepts_writes is True
    assert region_b.role == "ACTIVE"
    assert region_b.fencing_epoch == 102

    # Invariant: exactly one writer
    assert region_a.accepts_writes is False
    assert region_b.accepts_writes is True

