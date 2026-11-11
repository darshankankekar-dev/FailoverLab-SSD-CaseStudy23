import pytest
from sqlalchemy import select
from src.services.failover_workflow import execute_failover_workflow
from src.services.failback_workflow import execute_failback_workflow
from src.schemas import ControllerState, TransitionStatus
from src.models import (
    RegionEntity,
    ControllerStateEntity,
    ReplicationEntity,
    QuorumVoterEntity,
)


@pytest.mark.asyncio
async def test_failback_blocked_without_confirmation(db_session):
    res = await execute_failback_workflow(
        db_session,
        operator_id="operator-1",
        confirmation=False,
    )
    assert res.status == TransitionStatus.BLOCKED
    assert "Missing operator confirmation" in res.blocked_reason


@pytest.mark.asyncio
async def test_failback_blocked_when_primary_still_down(db_session):
    # First failover to Region B
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    await execute_failover_workflow(db_session, force=False)

    # Keep Region A down
    res_a = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()
    region_a.health = "DOWN"

    res = await execute_failback_workflow(
        db_session,
        operator_id="operator-1",
        confirmation=True,
    )
    assert res.status == TransitionStatus.BLOCKED
    assert res.current_state == ControllerState.FAILOVER_BLOCKED
    assert "Original primary (Region A) is still DOWN" in res.blocked_reason


@pytest.mark.asyncio
async def test_failback_blocked_when_reverse_lag_high(db_session):
    # Failover to Region B
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    await execute_failover_workflow(db_session, force=False)

    # Set Region A healthy but reverse replication lag high
    res_a = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()
    region_a.health = "HEALTHY"

    res_rep = await db_session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    rep = res_rep.scalar_one()
    rep.status = "REVERSED"
    rep.lag_seconds = 7.5

    res = await execute_failback_workflow(
        db_session,
        operator_id="operator-1",
        confirmation=True,
    )
    assert res.status == TransitionStatus.BLOCKED
    assert "Reverse replication lag" in res.blocked_reason


@pytest.mark.asyncio
async def test_failback_successful(db_session):
    # 1. Failover to Region B
    res_state = await db_session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.consecutive_failures = 3

    res_voters = await db_session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_OUTAGE"

    await execute_failover_workflow(db_session, force=False)

    # 2. Reconcile Region A and reverse replication
    res_a = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()
    region_a.health = "HEALTHY"

    res_rep = await db_session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    rep = res_rep.scalar_one()
    rep.status = "SYNCED"
    rep.lag_seconds = 0.5

    # 3. Execute deliberate failback
    res = await execute_failback_workflow(
        db_session,
        operator_id="lead-sre-mumbai",
        confirmation=True,
    )

    assert res.status == TransitionStatus.COMPLETED
    assert res.current_state == ControllerState.HEALTHY
    assert res.fencing_epoch == 103

    # Region A is now primary writer, Region B is standby
    res_a = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()
    assert region_a.accepts_writes is True
    assert region_a.role == "ACTIVE"
    assert region_a.fencing_epoch == 103

    res_b = await db_session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    region_b = res_b.scalar_one()
    assert region_b.accepts_writes is False
    assert region_b.role == "STANDBY"

