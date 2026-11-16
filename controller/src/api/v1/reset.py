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
from ...domain.registry import REGION_REGISTRY
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
    # 1. Reset All Configured Regions
    res_regions = await session.execute(select(RegionEntity))
    for region in res_regions.scalars().all():
        is_active = (region.id == "region-a")
        region.role = "ACTIVE" if is_active else "STANDBY"
        region.health = "HEALTHY"
        region.status = "healthy"
        region.accepts_writes = is_active
        region.ingress_traffic_percent = 100 if is_active else 0
        region.ingress_rps = 2450 if is_active else 0
        region.active_connections = 2450 if is_active else 0
        r_def = REGION_REGISTRY.get(region.id)
        region.iops = r_def.baseline_iops if r_def else (4800 if is_active else 120)
        region.fencing_epoch = 101
        region.is_fenced = False

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
        for rid in ["region-b", "region-c", "region-d", "region-e"]:
            await regional_client.demote(rid, epoch=101)
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

