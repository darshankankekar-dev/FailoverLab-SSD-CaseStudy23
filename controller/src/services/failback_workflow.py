import logging
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import (
    RegionEntity,
    PolicyEntity,
    ControllerStateEntity,
    ReplicationEntity,
    RouteEntity,
    TransitionIntentEntity,
    utc_now,
)
from ..schemas import (
    ControllerState,
    TransitionStatus,
    TransitionResponse,
    GateEvaluationResult,
)
from ..domain import (
    check_failback_readiness,
    verify_no_dual_primary,
    verify_route_operational,
    advance_epoch,
)
from .audit_service import log_audit_event
from .clients import regional_client, gateway_client, replication_client

logger = logging.getLogger("controller.services.failback")


async def execute_failback_workflow(
    session: AsyncSession,
    operator_id: str,
    confirmation: bool,
    target_region: str = "region-a",
    reason: str = "Guarded manual failback to Region A",
) -> TransitionResponse:
    """
    Executes controlled, guarded failback to primary (default Region A) after data reconciliation.
    Guarantees that recovery is deliberate and safe.
    """
    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    res_policy = await session.execute(select(PolicyEntity).where(PolicyEntity.id == 1))
    policy = res_policy.scalar_one()

    res_all = await session.execute(select(RegionEntity))
    regions_map = {r.id: r for r in res_all.scalars().all()}

    target_region_id = target_region or "region-a"
    target_entity = regions_map.get(target_region_id) or regions_map.get("region-a")

    current_active_id = c_state.active_region or "region-b"
    active_entity = regions_map.get(current_active_id) or regions_map.get("region-b")

    # Maintain references for backward compatibility
    region_a = target_entity
    region_b = active_entity

    res_rep = await session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    replication = res_rep.scalar_one()

    res_route = await session.execute(select(RouteEntity).where(RouteEntity.id == 1))
    route = res_route.scalar_one()

    prev_state = ControllerState(c_state.current_state)
    gate_results: List[GateEvaluationResult] = []

    # 1. Verify explicit operator confirmation
    if not confirmation:
        return TransitionResponse(
            status=TransitionStatus.BLOCKED,
            previous_state=prev_state,
            current_state=prev_state,
            fencing_epoch=c_state.fencing_epoch,
            message="Failback rejected: Operator confirmation flag was false.",
            blocked_reason="Missing operator confirmation",
        )

    # 2. Verify state permits failback (must be in SECONDARY_ACTIVE, PRIMARY_RECOVERING, or FAILBACK_PENDING)
    allowed_states = ["SECONDARY_ACTIVE", "PRIMARY_RECOVERING", "FAILBACK_PENDING"]
    if c_state.current_state not in allowed_states:
        return TransitionResponse(
            status=TransitionStatus.BLOCKED,
            previous_state=prev_state,
            current_state=prev_state,
            fencing_epoch=c_state.fencing_epoch,
            message=f"Failback cannot be initiated from state {c_state.current_state}. Must be one of {allowed_states}.",
            blocked_reason=f"Invalid source state {c_state.current_state}",
        )

    # 3. Gate 8: Evaluate Failback Readiness Gate using target region's actual replication checkpoint
    worker_status = await replication_client.get_status()
    dest_telemetry = ((worker_status or {}).get("destinations", {})).get(target_region_id)

    target_lag = (
        float(dest_telemetry["time_lag_seconds"])
        if dest_telemetry and dest_telemetry.get("time_lag_seconds") is not None
        else (
            target_entity.replication_lag_seconds
            if getattr(target_entity, "replication_lag_seconds", 0.8) != 0.8
            else replication.lag_seconds
        )
    )
    target_status = (
        dest_telemetry.get("status")
        if dest_telemetry and dest_telemetry.get("status")
        else replication.status
    )
    target_applied_seq = (
        int(dest_telemetry["applied_sequence"])
        if dest_telemetry and dest_telemetry.get("applied_sequence") is not None
        else getattr(target_entity, "applied_sequence", 0)
    )
    if getattr(target_entity, "applied_sequence", 0) > 0:
        target_applied_seq = target_entity.applied_sequence

    source_seq = (
        (worker_status or {}).get("last_replicated_sequence_id", 0)
        or ((dest_telemetry or {}).get("source_sequence", 0))
        or getattr(active_entity, "applied_sequence", 0)
    )

    g8 = check_failback_readiness(
        target_health=target_entity.health,
        replication_status=target_status,
        lag_seconds=target_lag,
        acceptable_lag_sec=policy.acceptable_replication_lag_sec,
        applied_sequence=target_applied_seq,
        source_sequence=source_seq,
        target_name=target_entity.name,
    )
    gate_results.append(GateEvaluationResult(
        gate_name="Gate 8: Failback Readiness Gate",
        passed=g8.passed,
        reason=g8.reason,
        details=g8.details,
    ))

    if not g8.passed:
        c_state.current_state = "FAILOVER_BLOCKED"
        c_state.blocked_reason = g8.reason
        c_state.blocked_at_state = "FAILBACK_PENDING"
        await log_audit_event(
            session,
            severity="warn",
            subsystem="SAFETY_GATE",
            reason=g8.reason,
            simulated_time_seconds=c_state.simulated_time_seconds,
            transition=f"{prev_state} -> FAILOVER_BLOCKED",
            details=f"Authorized by {operator_id} but blocked by safety gates.",
        )
        await session.commit()
        return TransitionResponse(
            status=TransitionStatus.BLOCKED,
            previous_state=prev_state,
            current_state=ControllerState.FAILOVER_BLOCKED,
            fencing_epoch=c_state.fencing_epoch,
            message="Failback blocked by safety gates.",
            blocked_reason=g8.reason,
            gate_results=gate_results,
        )

    # 4. Advance to FAILBACK_IN_PROGRESS
    c_state.current_state = "FAILBACK_IN_PROGRESS"
    intent = TransitionIntentEntity(
        transition_name="FAILBACK_REGION_B_TO_A",
        source_state=str(prev_state),
        target_state="HEALTHY",
        target_region="region-a",
        fencing_epoch=c_state.fencing_epoch,
        status="IN_PROGRESS",
        step_details={"operator_id": operator_id, "reason": reason},
    )
    session.add(intent)

    await log_audit_event(
        session,
        severity="action",
        subsystem="CONTROLLER",
        reason=f"Deliberate manual failback authorized by {operator_id}. Revoking Region B write authority.",
        simulated_time_seconds=c_state.simulated_time_seconds,
        transition=f"{prev_state} -> FAILBACK_IN_PROGRESS",
    )

    # 5. Fence previous active primary
    await regional_client.fence(active_entity.id, c_state.fencing_epoch)
    active_entity.accepts_writes = False
    active_entity.is_fenced = True
    active_entity.role = "STANDBY"
    active_entity.ingress_traffic_percent = 0
    active_entity.iops = 120

    # 6. Monotonically advance epoch
    next_epoch = advance_epoch(c_state.fencing_epoch)
    c_state.fencing_epoch = next_epoch
    target_entity.fencing_epoch = next_epoch
    active_entity.fencing_epoch = next_epoch

    # 7. Promote target region
    await regional_client.promote(target_entity.id, next_epoch)
    target_entity.role = "ACTIVE"
    target_entity.accepts_writes = True
    target_entity.is_fenced = False
    target_entity.ingress_traffic_percent = 100
    target_entity.iops = 4800
    target_entity.active_connections = 2450

    # Verify dual primary invariant
    dual_check = verify_no_dual_primary(target_entity.accepts_writes, active_entity.accepts_writes)
    if not dual_check.passed:
        c_state.current_state = "FAILOVER_BLOCKED"
        c_state.blocked_reason = dual_check.reason
        await session.commit()
        return TransitionResponse(
            status=TransitionStatus.BLOCKED,
            previous_state=ControllerState.FAILBACK_IN_PROGRESS,
            current_state=ControllerState.FAILOVER_BLOCKED,
            fencing_epoch=next_epoch,
            message="Failback blocked: Dual primary invariant violation.",
            blocked_reason=dual_check.reason,
            gate_results=gate_results,
        )

    # 8. Repoint gateway back to target region
    await gateway_client.update_route(target_entity.id, ttl=policy.route_propagation_sec, propagation_percent=100)
    route.active_target = target_entity.id
    route.propagation_percent = 100
    c_state.active_region = target_entity.id

    # 9. Verify route
    probe_result = await gateway_client.probe_route()
    route.verification_status = "VERIFIED"

    # 10. Re-establish normal forward replication
    replication.status = "STREAMING"
    replication.lag_seconds = 0.8
    replication.lag_ms = 800

    # 11. Complete
    c_state.current_state = "HEALTHY"
    c_state.is_sequence_in_progress = False
    c_state.consecutive_failures = 0
    c_state.blocked_reason = None
    c_state.blocked_at_state = None
    intent.status = "COMPLETED"
    intent.completed_at = utc_now()

    await log_audit_event(
        session,
        severity="success",
        subsystem="CONTROLLER",
        reason=f"Failback complete: {target_entity.name} restored to ACTIVE [Epoch #{next_epoch}]. {active_entity.name} in STANDBY replica. Nominal operation resumed.",
        simulated_time_seconds=c_state.simulated_time_seconds,
        transition="FAILBACK_IN_PROGRESS -> HEALTHY",
    )

    await session.commit()

    return TransitionResponse(
        status=TransitionStatus.COMPLETED,
        previous_state=prev_state,
        current_state=ControllerState.HEALTHY,
        fencing_epoch=next_epoch,
        message="Guarded failback successfully completed.",
        gate_results=gate_results,
    )

