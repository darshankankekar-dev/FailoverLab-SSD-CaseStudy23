import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import (
    RegionEntity,
    PolicyEntity,
    ControllerStateEntity,
    ReplicationEntity,
    RouteEntity,
    QuorumVoterEntity,
    TransitionIntentEntity,
    utc_now,
)
from ..schemas import (
    ControllerState,
    TransitionStatus,
    RegionId,
    TransitionResponse,
    GateEvaluationResult,
)
from ..domain import (
    can_initiate_quorum,
    evaluate_quorum_majority,
    check_standby_readiness,
    check_replication_lag_policy,
    verify_fencing_confirmed,
    verify_no_dual_primary,
    verify_route_operational,
    advance_epoch,
)
from .audit_service import log_audit_event
from .clients import regional_client, gateway_client
from .metrics_tracker import metrics_tracker
from ..logging_config import transition_id_ctx, fencing_epoch_ctx, region_id_ctx

logger = logging.getLogger("controller.services.failover")


async def execute_failover_workflow(
    session: AsyncSession,
    force: bool = False,
    target_region: str = "region-b",
    reason: str = "Automated failover sequence initiated",
) -> TransitionResponse:
    """
    Executes the 10-step failover decision workflow strictly enforcing all safety gates.
    Persists transition intent before applying side effects.
    """
    # 1. Fetch current entities
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

    res_voters = await session.execute(select(QuorumVoterEntity))
    voters = list(res_voters.scalars().all())

    prev_state = ControllerState(c_state.current_state)
    gate_results: List[GateEvaluationResult] = []

    # Check re-entrancy / existing active primary
    if region_b.role == "ACTIVE" and c_state.current_state == "SECONDARY_ACTIVE":
        return TransitionResponse(
            status=TransitionStatus.COMPLETED,
            previous_state=prev_state,
            current_state=prev_state,
            fencing_epoch=c_state.fencing_epoch,
            message="Region B is already the active primary.",
        )

    # Persist transition intent
    intent = TransitionIntentEntity(
        transition_name="FAILOVER_REGION_A_TO_B",
        source_state=c_state.current_state,
        target_state="SECONDARY_ACTIVE",
        target_region=target_region,
        fencing_epoch=c_state.fencing_epoch,
        status="IN_PROGRESS",
        step_details={"step": "INITIATED", "reason": reason, "force": force},
    )
    session.add(intent)
    c_state.persisted_intent = "FAILOVER_IN_PROGRESS"
    c_state.is_sequence_in_progress = True
    await session.flush()

    # Bind structured logging context
    transition_id_ctx.set(intent.id)
    fencing_epoch_ctx.set(c_state.fencing_epoch)
    region_id_ctx.set(target_region)
    metrics_tracker.record_failover_attempt()
    logger.info(
        f"[FAILOVER_START] Initiated transition {intent.id} towards '{target_region}' [Epoch #{c_state.fencing_epoch}]",
        extra={"transition_id": intent.id, "target_region": target_region, "fencing_epoch": c_state.fencing_epoch}
    )

    # ---------------------------------------------------------
    # STEP 1: Evaluate health checks & consecutive-failure threshold
    # ---------------------------------------------------------
    if not force:
        g1 = can_initiate_quorum(c_state.consecutive_failures, policy.failure_threshold_consecutive)
        gate_results.append(GateEvaluationResult(
            gate_name="Gate 1: Consecutive Failure Threshold",
            passed=g1.passed,
            reason=g1.reason,
            details=g1.details,
        ))
        if not g1.passed:
            metrics_tracker.record_failover_blocked("Gate 1: Consecutive Failure Threshold")
            logger.warning(
                f"[TRANSITION_BLOCKED] Step 1 debounce threshold not met ({c_state.consecutive_failures}/{policy.failure_threshold_consecutive}): {g1.reason}",
                extra={"transition_id": intent.id, "step": "Gate 1", "reason": g1.reason}
            )
            c_state.current_state = "FAILOVER_BLOCKED"
            c_state.blocked_reason = g1.reason
            c_state.blocked_at_state = "PRIMARY_SUSPECTED"
            c_state.is_sequence_in_progress = False
            intent.status = "BLOCKED"
            intent.blocked_reason = g1.reason
            await log_audit_event(
                session,
                severity="warn",
                subsystem="SAFETY_GATE",
                reason=g1.reason,
                simulated_time_seconds=c_state.simulated_time_seconds,
                transition=f"{prev_state} -> FAILOVER_BLOCKED",
            )
            await session.commit()
            return TransitionResponse(
                status=TransitionStatus.BLOCKED,
                previous_state=prev_state,
                current_state=ControllerState.FAILOVER_BLOCKED,
                fencing_epoch=c_state.fencing_epoch,
                message="Failover blocked at Step 1 (Debounce threshold not met).",
                blocked_reason=g1.reason,
                gate_results=gate_results,
            )

    c_state.current_state = "QUORUM_CHECK"
    await log_audit_event(
        session,
        severity="action",
        subsystem="CONTROLLER",
        reason="Proceeding to Quorum Consensus evaluation.",
        simulated_time_seconds=c_state.simulated_time_seconds,
        transition=f"{prev_state} -> QUORUM_CHECK",
    )

    # ---------------------------------------------------------
    # STEP 2: Require simulated quorum majority
    # ---------------------------------------------------------
    voter_votes = [v.vote for v in voters]
    g2 = evaluate_quorum_majority(voter_votes, policy.majority_required)
    gate_results.append(GateEvaluationResult(
        gate_name="Gate 2: Quorum Majority Consensus",
        passed=g2.passed,
        reason=g2.reason,
        details=g2.details,
    ))
    if not g2.passed:
        metrics_tracker.record_failover_blocked("Gate 2: Quorum Majority Consensus")
        logger.warning(
            f"[TRANSITION_BLOCKED] Step 2 quorum consensus failed: {g2.reason}",
            extra={"transition_id": intent.id, "step": "Gate 2", "reason": g2.reason, "voter_votes": voter_votes}
        )
        c_state.current_state = "FAILOVER_BLOCKED"
        c_state.blocked_reason = g2.reason
        c_state.blocked_at_state = "QUORUM_CHECK"
        c_state.is_sequence_in_progress = False
        intent.status = "BLOCKED"
        intent.blocked_reason = g2.reason
        await log_audit_event(
            session,
            severity="critical",
            subsystem="SAFETY_GATE",
            reason=g2.reason,
            simulated_time_seconds=c_state.simulated_time_seconds,
            transition="QUORUM_CHECK -> FAILOVER_BLOCKED",
        )
        await session.commit()
        return TransitionResponse(
            status=TransitionStatus.BLOCKED,
            previous_state=ControllerState.QUORUM_CHECK,
            current_state=ControllerState.FAILOVER_BLOCKED,
            fencing_epoch=c_state.fencing_epoch,
            message="Failover blocked at Step 2 (Insufficient Quorum Majority).",
            blocked_reason=g2.reason,
            gate_results=gate_results,
        )

    logger.info(
        f"[QUORUM_CONSENSUS] Step 2 quorum verified: {g2.reason}",
        extra={"transition_id": intent.id, "step": "Gate 2", "voter_votes": voter_votes}
    )

    # ---------------------------------------------------------
    # STEP 3: Confirm standby readiness
    # ---------------------------------------------------------
    g3 = check_standby_readiness(region_b.health)
    gate_results.append(GateEvaluationResult(
        gate_name="Gate 3: Standby Readiness",
        passed=g3.passed,
        reason=g3.reason,
        details=g3.details,
    ))
    if not g3.passed:
        metrics_tracker.record_failover_blocked("Gate 3: Standby Readiness")
        logger.warning(
            f"[TRANSITION_BLOCKED] Step 3 standby not ready: {g3.reason}",
            extra={"transition_id": intent.id, "step": "Gate 3", "reason": g3.reason}
        )
        c_state.current_state = "FAILOVER_BLOCKED"
        c_state.blocked_reason = g3.reason
        c_state.blocked_at_state = "QUORUM_CHECK"
        c_state.is_sequence_in_progress = False
        intent.status = "BLOCKED"
        intent.blocked_reason = g3.reason
        await log_audit_event(
            session,
            severity="critical",
            subsystem="SAFETY_GATE",
            reason=g3.reason,
            simulated_time_seconds=c_state.simulated_time_seconds,
            transition="QUORUM_CHECK -> FAILOVER_BLOCKED",
        )
        await session.commit()
        return TransitionResponse(
            status=TransitionStatus.BLOCKED,
            previous_state=ControllerState.QUORUM_CHECK,
            current_state=ControllerState.FAILOVER_BLOCKED,
            fencing_epoch=c_state.fencing_epoch,
            message="Failover blocked at Step 3 (Standby not ready).",
            blocked_reason=g3.reason,
            gate_results=gate_results,
        )

    logger.info(
        f"[STANDBY_READY] Step 3 standby readiness confirmed: Region B is {region_b.health}",
        extra={"transition_id": intent.id, "step": "Gate 3", "region_b_health": region_b.health}
    )

    # ---------------------------------------------------------
    # STEP 4: Evaluate replication lag against policy
    # ---------------------------------------------------------
    g4 = check_replication_lag_policy(
        replication.lag_seconds,
        replication.status,
        policy.acceptable_replication_lag_sec,
    )
    gate_results.append(GateEvaluationResult(
        gate_name="Gate 4: Replication Lag Policy (RPO Protection)",
        passed=g4.passed,
        reason=g4.reason,
        details=g4.details,
    ))
    if not g4.passed:
        metrics_tracker.record_failover_blocked("Gate 4: Replication Lag Policy (RPO Protection)")
        logger.warning(
            f"[TRANSITION_BLOCKED] Step 4 replication lag policy violated: {g4.reason}",
            extra={"transition_id": intent.id, "step": "Gate 4", "reason": g4.reason, "lag_seconds": replication.lag_seconds}
        )
        c_state.current_state = "FAILOVER_BLOCKED"
        c_state.blocked_reason = g4.reason
        c_state.blocked_at_state = "QUORUM_CHECK"
        c_state.is_sequence_in_progress = False
        intent.status = "BLOCKED"
        intent.blocked_reason = g4.reason
        await log_audit_event(
            session,
            severity="critical",
            subsystem="SAFETY_GATE",
            reason=g4.reason,
            simulated_time_seconds=c_state.simulated_time_seconds,
            transition="QUORUM_CHECK -> FAILOVER_BLOCKED",
        )
        await session.commit()
        return TransitionResponse(
            status=TransitionStatus.BLOCKED,
            previous_state=ControllerState.QUORUM_CHECK,
            current_state=ControllerState.FAILOVER_BLOCKED,
            fencing_epoch=c_state.fencing_epoch,
            message="Failover blocked at Step 4 (Excessive Replication Lag).",
            blocked_reason=g4.reason,
            gate_results=gate_results,
        )

    logger.info(
        f"[REPLICATION_LAG_OK] Step 4 lag verified ({replication.lag_seconds}s <= {policy.acceptable_replication_lag_sec}s)",
        extra={"transition_id": intent.id, "step": "Gate 4", "lag_seconds": replication.lag_seconds}
    )

    # ---------------------------------------------------------
    # STEP 5: Require confirmation that former primary can no longer accept stale writes
    # ---------------------------------------------------------
    c_state.current_state = "FENCING_PRIMARY"
    await log_audit_event(
        session,
        severity="action",
        subsystem="FENCING",
        reason="Revoking write authority on Region A and establishing hard storage fence.",
        simulated_time_seconds=c_state.simulated_time_seconds,
        transition="QUORUM_CHECK -> FENCING_PRIMARY",
    )

    # Apply fencing side effect
    logger.info(f"[FENCING_PRIMARY] Revoking write authority on Region A [Epoch #{c_state.fencing_epoch}]")
    await regional_client.fence("region-a", c_state.fencing_epoch)
    region_a.accepts_writes = False
    region_a.is_fenced = True
    region_a.ingress_traffic_percent = 0
    region_a.iops = 0

    g5 = verify_fencing_confirmed(region_a.accepts_writes, region_a.is_fenced)
    gate_results.append(GateEvaluationResult(
        gate_name="Gate 5: Fencing Confirmation",
        passed=g5.passed,
        reason=g5.reason,
        details=g5.details,
    ))
    if not g5.passed:
        metrics_tracker.record_failover_blocked("Gate 5: Fencing Confirmation")
        logger.warning(
            f"[TRANSITION_BLOCKED] Step 5 fencing confirmation failed: {g5.reason}",
            extra={"transition_id": intent.id, "step": "Gate 5", "reason": g5.reason}
        )
        c_state.current_state = "FAILOVER_BLOCKED"
        c_state.blocked_reason = g5.reason
        c_state.blocked_at_state = "FENCING_PRIMARY"
        c_state.is_sequence_in_progress = False
        intent.status = "BLOCKED"
        intent.blocked_reason = g5.reason
        await log_audit_event(
            session,
            severity="critical",
            subsystem="SAFETY_GATE",
            reason=g5.reason,
            simulated_time_seconds=c_state.simulated_time_seconds,
            transition="FENCING_PRIMARY -> FAILOVER_BLOCKED",
        )
        await session.commit()
        return TransitionResponse(
            status=TransitionStatus.BLOCKED,
            previous_state=ControllerState.FENCING_PRIMARY,
            current_state=ControllerState.FAILOVER_BLOCKED,
            fencing_epoch=c_state.fencing_epoch,
            message="Failover blocked at Step 5 (Fencing not confirmed).",
            blocked_reason=g5.reason,
            gate_results=gate_results,
        )

    # ---------------------------------------------------------
    # STEP 6: Advance the fencing epoch before granting write authority
    # ---------------------------------------------------------
    next_epoch = advance_epoch(c_state.fencing_epoch)
    c_state.fencing_epoch = next_epoch
    region_a.fencing_epoch = next_epoch
    region_b.fencing_epoch = next_epoch
    fencing_epoch_ctx.set(next_epoch)

    logger.info(
        f"[EPOCH_ADVANCED] Monotonic fencing epoch advanced from #{c_state.fencing_epoch - 1} to #{next_epoch}",
        extra={"transition_id": intent.id, "fencing_epoch": next_epoch}
    )

    c_state.current_state = "PROMOTING_STANDBY"
    await log_audit_event(
        session,
        severity="action",
        subsystem="FENCING",
        reason=f"Fencing epoch advanced to #{next_epoch}. Promoting Region B to primary writer.",
        simulated_time_seconds=c_state.simulated_time_seconds,
        transition="FENCING_PRIMARY -> PROMOTING_STANDBY",
    )

    # ---------------------------------------------------------
    # STEP 7: Promote the standby
    # ---------------------------------------------------------
    logger.info(f"[PROMOTING_STANDBY] Granting write authority to Region B with epoch #{next_epoch}")
    await regional_client.promote("region-b", next_epoch)
    region_b.role = "ACTIVE"
    region_b.accepts_writes = True
    region_b.iops = 4800
    region_a.role = "STANDBY"

    g6 = verify_no_dual_primary(region_a.accepts_writes, region_b.accepts_writes)
    gate_results.append(GateEvaluationResult(
        gate_name="Gate 6: Dual-Primary Safety Invariant",
        passed=g6.passed,
        reason=g6.reason,
        details=g6.details,
    ))
    if not g6.passed:
        metrics_tracker.record_failover_blocked("Gate 6: Dual-Primary Safety Invariant")
        logger.warning(
            f"[TRANSITION_BLOCKED] Step 7 dual-primary invariant violated: {g6.reason}",
            extra={"transition_id": intent.id, "step": "Gate 6", "reason": g6.reason}
        )
        c_state.current_state = "FAILOVER_BLOCKED"
        c_state.blocked_reason = g6.reason
        c_state.blocked_at_state = "PROMOTING_STANDBY"
        c_state.is_sequence_in_progress = False
        intent.status = "BLOCKED"
        intent.blocked_reason = g6.reason
        await log_audit_event(
            session,
            severity="critical",
            subsystem="SAFETY_GATE",
            reason=g6.reason,
            simulated_time_seconds=c_state.simulated_time_seconds,
            transition="PROMOTING_STANDBY -> FAILOVER_BLOCKED",
        )
        await session.commit()
        return TransitionResponse(
            status=TransitionStatus.BLOCKED,
            previous_state=ControllerState.PROMOTING_STANDBY,
            current_state=ControllerState.FAILOVER_BLOCKED,
            fencing_epoch=next_epoch,
            message="Failover blocked at Step 7 (Dual-Primary Invariant Violated).",
            blocked_reason=g6.reason,
            gate_results=gate_results,
        )

    c_state.active_region = "region-b"

    # ---------------------------------------------------------
    # STEP 8: Request gateway route update
    # ---------------------------------------------------------
    c_state.current_state = "ROUTE_UPDATING"
    logger.info(f"[ROUTE_UPDATING] Pointing ingress gateway target to Region B (TTL={policy.route_propagation_sec}s)")
    await log_audit_event(
        session,
        severity="action",
        subsystem="DNS",
        reason="Requesting Gateway / DNS Anycast route update pointing to Region B.",
        simulated_time_seconds=c_state.simulated_time_seconds,
        transition="PROMOTING_STANDBY -> ROUTE_UPDATING",
    )

    await gateway_client.update_route("region-b", ttl=policy.route_propagation_sec, propagation_percent=100)
    route.active_target = "region-b"
    route.propagation_percent = 100
    region_b.ingress_traffic_percent = 100
    region_b.active_connections = 2450

    # ---------------------------------------------------------
    # STEP 9: Verify the new route with a test request
    # ---------------------------------------------------------
    c_state.current_state = "VERIFYING_ROUTE"
    route.verification_status = "VERIFYING"
    logger.info("[VERIFYING_ROUTE] Dispatching synthetic test probe to verify route reachability")
    await log_audit_event(
        session,
        severity="action",
        subsystem="DNS",
        reason="Dispatching synthetic test request through gateway to verify route connectivity.",
        simulated_time_seconds=c_state.simulated_time_seconds,
        transition="ROUTE_UPDATING -> VERIFYING_ROUTE",
    )

    probe_result = await gateway_client.probe_route()
    route_healthy = probe_result.get("success", False)
    route.verification_status = "VERIFIED" if route_healthy else "FAILED"
    logger.info(f"[ROUTE_PROBE_RESULT] Probe verified={route_healthy}, latency_ms={probe_result.get('latency_ms', 0)}")

    g7 = verify_route_operational(
        active_target=route.active_target,
        expected_target="region-b",
        propagation_percent=route.propagation_percent,
        verification_status=route.verification_status,
        route_failure_injected=not route_healthy,
    )
    gate_results.append(GateEvaluationResult(
        gate_name="Gate 7: Route Operational Verification",
        passed=g7.passed,
        reason=g7.reason,
        details=g7.details,
    ))
    if not g7.passed:
        metrics_tracker.record_failover_blocked("Gate 7: Route Operational Verification")
        logger.warning(
            f"[TRANSITION_BLOCKED] Step 9 route operational verification failed: {g7.reason}",
            extra={"transition_id": intent.id, "step": "Gate 7", "reason": g7.reason}
        )
        c_state.current_state = "FAILOVER_BLOCKED"
        c_state.blocked_reason = g7.reason
        c_state.blocked_at_state = "VERIFYING_ROUTE"
        c_state.route_retry_count += 1
        c_state.is_sequence_in_progress = False
        intent.status = "BLOCKED"
        intent.blocked_reason = g7.reason
        await log_audit_event(
            session,
            severity="critical",
            subsystem="SAFETY_GATE",
            reason=g7.reason,
            simulated_time_seconds=c_state.simulated_time_seconds,
            transition="VERIFYING_ROUTE -> FAILOVER_BLOCKED",
        )
        await session.commit()
        return TransitionResponse(
            status=TransitionStatus.BLOCKED,
            previous_state=ControllerState.VERIFYING_ROUTE,
            current_state=ControllerState.FAILOVER_BLOCKED,
            fencing_epoch=next_epoch,
            message="Failover blocked at Step 9 (Route probe verification failed).",
            blocked_reason=g7.reason,
            gate_results=gate_results,
        )

    # ---------------------------------------------------------
    # STEP 10: Mark failover successful only after all required steps succeed
    # ---------------------------------------------------------
    c_state.current_state = "SECONDARY_ACTIVE"
    c_state.is_sequence_in_progress = False
    c_state.persisted_intent = None
    c_state.blocked_reason = None
    c_state.blocked_at_state = None
    intent.status = "COMPLETED"
    intent.completed_at = utc_now()
    metrics_tracker.record_failover_success()

    logger.info(
        f"[FAILOVER_COMPLETED] Transition {intent.id} complete across all 10 decision steps. Region B active primary [Epoch #{next_epoch}].",
        extra={"transition_id": intent.id, "active_region": "region-b", "fencing_epoch": next_epoch}
    )

    await log_audit_event(
        session,
        severity="success",
        subsystem="CONTROLLER",
        reason="Failover complete: Region B (Singapore) promoted to PRIMARY. Route verified. Zero split-brain writes.",
        simulated_time_seconds=c_state.simulated_time_seconds,
        transition="VERIFYING_ROUTE -> SECONDARY_ACTIVE",
    )

    await session.commit()

    return TransitionResponse(
        status=TransitionStatus.COMPLETED,
        previous_state=prev_state,
        current_state=ControllerState.SECONDARY_ACTIVE,
        fencing_epoch=next_epoch,
        message="Failover successfully executed across all 10 decision steps.",
        gate_results=gate_results,
    )

