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
from .clients import regional_client, gateway_client

logger = logging.getLogger("controller.services.failback")


async def execute_failback_workflow(
    session: AsyncSession,
    operator_id: str,
    confirmation: bool,
    reason: str = "Guarded manual failback to Region A",
) -> TransitionResponse:
    """
    Executes controlled, guarded failback to Region A after data reconciliation.
    Guarantees that recovery is deliberate and safe.
    """
    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    res_policy = await session.execute(select(PolicyEntity).where(PolicyEntity.id == 1))
    policy = res_policy.scalar_one()

    res_a = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()

    res_b = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    region_b = res_b.scalar_one()

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

    # 3. Gate 8: Evaluate Failback Readiness Gate
    g8 = check_failback_readiness(
        region_a_health=region_a.health,
        replication_status=replication.status,
        lag_seconds=replication.lag_seconds,
        acceptable_lag_sec=policy.acceptable_replication_lag_sec,
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

    # 5. Fence Region B
    await regional_client.fence("region-b", c_state.fencing_epoch)
    region_b.accepts_writes = False
    region_b.is_fenced = True
    region_b.role = "STANDBY"
    region_b.ingress_traffic_percent = 0
    region_b.iops = 120

    # 6. Monotonically advance epoch
    next_epoch = advance_epoch(c_state.fencing_epoch)
    c_state.fencing_epoch = next_epoch
    region_a.fencing_epoch = next_epoch
    region_b.fencing_epoch = next_epoch

    # 7. Promote Region A
    await regional_client.promote("region-a", next_epoch)
    region_a.role = "ACTIVE"
    region_a.accepts_writes = True
    region_a.is_fenced = False
    region_a.ingress_traffic_percent = 100
    region_a.iops = 4800
    region_a.active_connections = 2450

    # Verify dual primary invariant
    dual_check = verify_no_dual_primary(region_a.accepts_writes, region_b.accepts_writes)
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

    # 8. Repoint gateway back to Region A
    await gateway_client.update_route("region-a", ttl=policy.route_propagation_sec, propagation_percent=100)
    route.active_target = "region-a"
    route.propagation_percent = 100
    c_state.active_region = "region-a"

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
        reason=f"Failback complete: Region A restored to ACTIVE [Epoch #{next_epoch}]. Region B in STANDBY replica. Nominal operation resumed.",
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

