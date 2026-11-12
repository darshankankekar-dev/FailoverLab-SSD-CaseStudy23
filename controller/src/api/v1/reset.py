import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...database import get_db_session
from ...schemas import ResetRequest, StateResponse
from ...models import (
    RegionEntity,
    PolicyEntity,
    ControllerStateEntity,
    ReplicationEntity,
    RouteEntity,
    QuorumVoterEntity,
)
from ...services import log_audit_event, get_full_state
from ...services.metrics_tracker import metrics_tracker
from ...services.clients import regional_client, gateway_client
from ...security import verify_admin_access

logger = logging.getLogger("controller.api.v1.reset")
router = APIRouter(tags=["Reset"])


@router.post("/reset", response_model=StateResponse, dependencies=[Depends(verify_admin_access)])
async def reset_simulation(
    payload: ResetRequest,
    session: AsyncSession = Depends(get_db_session),
) -> StateResponse:
    """Resets all entities, metrics, epochs, and routes back to the initial baseline."""
    # 1. Reset Region A
    res_a = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()
    region_a.role = "ACTIVE"
    region_a.health = "HEALTHY"
    region_a.status = "healthy"
    region_a.accepts_writes = True
    region_a.ingress_traffic_percent = 100
    region_a.ingress_rps = 2450
    region_a.active_connections = 2450
    region_a.iops = 4800
    region_a.fencing_epoch = 101
    region_a.is_fenced = False

    # 2. Reset Region B
    res_b = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    region_b = res_b.scalar_one()
    region_b.role = "STANDBY"
    region_b.health = "HEALTHY"
    region_b.status = "healthy"
    region_b.accepts_writes = False
    region_b.ingress_traffic_percent = 0
    region_b.ingress_rps = 0
    region_b.active_connections = 0
    region_b.iops = 120
    region_b.fencing_epoch = 101
    region_b.is_fenced = False

    # 3. Reset Replication
    res_rep = await session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    replication = res_rep.scalar_one()
    replication.status = "STREAMING"
    replication.lag_seconds = 0.8
    replication.lag_ms = 800
    replication.packet_loss_percent = 0.0
    replication.pending_bytes = 12400

    # 4. Reset Route
    res_route = await session.execute(select(RouteEntity).where(RouteEntity.id == 1))
    route = res_route.scalar_one()
    route.active_target = "region-a"
    route.propagation_percent = 100
    route.verification_status = "VERIFIED"

    # 5. Reset Voters
    res_voters = await session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        v.vote = "PRIMARY_HEALTHY"

    # 6. Reset Controller State
    metrics_tracker.reset_outage_marker()
    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    c_state.current_state = "HEALTHY"
    c_state.active_region = "region-a"
    c_state.fencing_epoch = 101
    c_state.consecutive_failures = 0
    c_state.simulated_time_seconds = 0.0
    c_state.last_health_check_sim_time = 0.0
    c_state.blocked_reason = None
    c_state.blocked_at_state = None
    c_state.is_sequence_in_progress = False
    c_state.route_retry_count = 0
    c_state.persisted_intent = None
    c_state.is_paused_interrupted = False

    # 7. Optionally reset policy
    if not payload.preserve_policy:
        res_p = await session.execute(select(PolicyEntity).where(PolicyEntity.id == 1))
        policy = res_p.scalar_one()
        policy.health_check_interval_sec = 2
        policy.failure_threshold_consecutive = 3
        policy.majority_required = 2
        policy.acceptable_replication_lag_sec = 5.0
        policy.auto_failover_enabled = True

    # 8. Synchronize regional services and gateway
    try:
        await regional_client.promote("region-a", epoch=101)
        await regional_client.demote("region-b", epoch=101)
        await gateway_client.update_route(
            target_region="region-a",
            ttl=2,
            propagation_percent=100,
        )
    except Exception as e:
        logger.warning(f"Could not synchronize regional services on reset: {e}")

    await log_audit_event(
        session,
        severity="info",
        subsystem="CONTROLLER",
        reason="Virtual Lab Reset: Baseline configuration, regions, routing, counters, and epochs restored.",
        simulated_time_seconds=0.0,
        transition="RESET -> HEALTHY",
    )

    await session.commit()
    return await get_full_state(session)

