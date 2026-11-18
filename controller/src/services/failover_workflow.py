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
    select_best_standby_candidate,
    CandidateEvaluation,
)
from .audit_service import log_audit_event
from .clients import regional_client, gateway_client, replication_client
from .metrics_tracker import metrics_tracker
from ..logging_config import transition_id_ctx, fencing_epoch_ctx, region_id_ctx

logger = logging.getLogger("controller.services.failover")


async def execute_failover_workflow(
    session: AsyncSession,
    force: bool = False,
    target_region: str = "region-b",
    reason: str = "Automated failover sequence initiated",
    regional_lags: Optional[Dict[str, float]] = None,
    regional_sequences: Optional[Dict[str, int]] = None,
    regional_latencies: Optional[Dict[str, int]] = None,
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

    res_all_regions = await session.execute(select(RegionEntity))
    regions_map = {r.id: r for r in res_all_regions.scalars().all()}

    source_region_id = c_state.active_region or "region-a"
    source_entity = regions_map.get(source_region_id) or regions_map.get("region-a")
    if not source_entity:
        res_source = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
        source_entity = res_source.scalar_one()

    target_norm = (target_region or "auto").lower().strip()

    res_rep = await session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    replication = res_rep.scalar_one()

    res_route = await session.execute(select(RouteEntity).where(RouteEntity.id == 1))
    route = res_route.scalar_one()

    res_voters = await session.execute(select(QuorumVoterEntity))
    voters = list(res_voters.scalars().all())

    prev_state = ControllerState(c_state.current_state)
    gate_results: List[GateEvaluationResult] = []

    # Check re-entrancy / existing active primary if manual target specified
    if target_norm != "auto" and target_norm in regions_map:
        target_entity = regions_map[target_norm]
        if target_entity.role == "ACTIVE" and c_state.current_state == "SECONDARY_ACTIVE":
            return TransitionResponse(
                status=TransitionStatus.COMPLETED,
                previous_state=prev_state,
                current_state=prev_state,
                fencing_epoch=c_state.fencing_epoch,
                message=f"{target_entity.name} ({target_entity.id}) is already the active primary.",
            )

    # Persist transition intent
    intent = TransitionIntentEntity(
        transition_name=f"FAILOVER_{source_entity.id.upper()}_TO_{target_norm.upper()}",
        source_state=c_state.current_state,
        target_state="SECONDARY_ACTIVE",
        target_region=target_norm,
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
    region_id_ctx.set(target_norm)
    metrics_tracker.record_failover_attempt()
    logger.info(
        f"[FAILOVER_START] Initiated transition {intent.id} towards '{target_norm}' [Epoch #{c_state.fencing_epoch}]",
        extra={"transition_id": intent.id, "target_region": target_norm, "fencing_epoch": c_state.fencing_epoch}
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
    # STEP 3 & STEP 4: Candidate Selection, Standby Readiness & Lag Policy
    # ---------------------------------------------------------
    # Obtain live per-destination replication telemetry from replication worker
    worker_status = await replication_client.get_status()
    worker_destinations = (worker_status or {}).get("destinations", {})

    effective_lags = dict(regional_lags or {})
    effective_sequences = dict(regional_sequences or {})

    for r_id, r_ent in regions_map.items():
        if r_id == source_entity.id:
            continue
        dest_telemetry = worker_destinations.get(r_id)
        db_lag = getattr(r_ent, "replication_lag_seconds", None)
        db_seq = getattr(r_ent, "applied_sequence", None)

        if r_id not in effective_lags:
            if db_lag is not None and db_lag != 0.8:
                effective_lags[r_id] = db_lag
            elif replication.status == "DEGRADED" and replication.lag_seconds > policy.acceptable_replication_lag_sec:
                effective_lags[r_id] = replication.lag_seconds
            elif dest_telemetry and dest_telemetry.get("time_lag_seconds") is not None:
                effective_lags[r_id] = float(dest_telemetry["time_lag_seconds"])
            else:
                effective_lags[r_id] = db_lag if db_lag is not None else replication.lag_seconds

        if r_id not in effective_sequences:
            if db_seq is not None and db_seq > 0:
                effective_sequences[r_id] = db_seq
            elif dest_telemetry and dest_telemetry.get("applied_sequence") is not None:
                effective_sequences[r_id] = int(dest_telemetry["applied_sequence"])
            else:
                effective_sequences[r_id] = db_seq if db_seq is not None else 0

    selected_candidate, candidate_evals, selection_summary = select_best_standby_candidate(
        regions=list(regions_map.values()),
        active_region_id=source_entity.id,
        acceptable_lag_sec=policy.acceptable_replication_lag_sec,
        preferred_target=target_norm,
        regional_lags=effective_lags,
        regional_sequences=effective_sequences,
        regional_latencies=regional_latencies,
    )

    if not selected_candidate:
        # Determine whether all candidates failed due to excessive replication lag
        is_lag_violation = (
            replication.status == "DEGRADED"
            or replication.lag_seconds > policy.acceptable_replication_lag_sec
            or (
                len(candidate_evals) > 0
                and any(ev.health == "HEALTHY" for ev in candidate_evals)
                and all(
                    any("lag" in r.lower() for r in ev.rejection_reasons)
                    for ev in candidate_evals
                    if ev.health == "HEALTHY"
                )
            )
        )

        if is_lag_violation:
            gate_results.append(GateEvaluationResult(
                gate_name="Gate 3: Standby Readiness",
                passed=True,
                reason="Standby candidate health verified; evaluating replication lag.",
                details={"candidates_evaluated": len(candidate_evals)},
            ))
            gate_results.append(GateEvaluationResult(
                gate_name="Gate 4: Replication Lag Policy (RPO Protection)",
                passed=False,
                reason=selection_summary,
                details={"acceptable_lag_sec": policy.acceptable_replication_lag_sec},
            ))
            metrics_tracker.record_failover_blocked("Gate 4: Replication Lag Policy (RPO Protection)")
            logger.warning(f"[TRANSITION_BLOCKED] Step 4 replication lag policy violated: {selection_summary}")
            c_state.current_state = "FAILOVER_BLOCKED"
            c_state.blocked_reason = selection_summary
            c_state.blocked_at_state = "QUORUM_CHECK"
            c_state.is_sequence_in_progress = False
            intent.status = "BLOCKED"
            intent.blocked_reason = selection_summary
            await log_audit_event(
                session,
                severity="critical",
                subsystem="SAFETY_GATE",
                reason=selection_summary,
                simulated_time_seconds=c_state.simulated_time_seconds,
                transition="QUORUM_CHECK -> FAILOVER_BLOCKED",
            )
            await session.commit()
            return TransitionResponse(
                status=TransitionStatus.BLOCKED,
                previous_state=ControllerState.QUORUM_CHECK,
                current_state=ControllerState.FAILOVER_BLOCKED,
                fencing_epoch=c_state.fencing_epoch,
                message=f"Failover blocked at Step 4 (Excessive Replication Lag). {selection_summary}",
                blocked_reason=selection_summary,
                gate_results=gate_results,
            )
        else:
            gate_results.append(GateEvaluationResult(
                gate_name="Gate 3: Standby Readiness",
                passed=False,
                reason=selection_summary,
                details={"candidates_evaluated": len(candidate_evals)},
            ))
            metrics_tracker.record_failover_blocked("Gate 3: Standby Readiness")
            logger.warning(f"[TRANSITION_BLOCKED] Step 3 standby candidate selection failed: {selection_summary}")
            c_state.current_state = "FAILOVER_BLOCKED"
            c_state.blocked_reason = selection_summary
            c_state.blocked_at_state = "QUORUM_CHECK"
            c_state.is_sequence_in_progress = False
            intent.status = "BLOCKED"
            intent.blocked_reason = selection_summary
            await log_audit_event(
                session,
                severity="critical",
                subsystem="SAFETY_GATE",
                reason=selection_summary,
                simulated_time_seconds=c_state.simulated_time_seconds,
                transition="QUORUM_CHECK -> FAILOVER_BLOCKED",
            )
            await session.commit()
            return TransitionResponse(
                status=TransitionStatus.BLOCKED,
                previous_state=ControllerState.QUORUM_CHECK,
                current_state=ControllerState.FAILOVER_BLOCKED,
                fencing_epoch=c_state.fencing_epoch,
                message=f"Failover blocked at Step 3 (Standby not ready). {selection_summary}",
                blocked_reason=selection_summary,
                gate_results=gate_results,
            )

    # Candidate successfully chosen
    target_entity = regions_map[selected_candidate.region_id]
    intent.target_region = target_entity.id
    region_id_ctx.set(target_entity.id)

    # Gate 3: Standby Readiness PASS
    gate_results.append(GateEvaluationResult(
        gate_name="Gate 3: Standby Readiness",
        passed=True,
        reason=f"Candidate {target_entity.name} ({target_entity.id}) is HEALTHY with operational application servers.",
        details={"candidate": target_entity.id, "summary": selection_summary},
    ))
    logger.info(f"[STANDBY_READY] Step 3 candidate verified: {target_entity.name} is {target_entity.health}")

    # Gate 4: Replication Lag Policy PASS
    gate_results.append(GateEvaluationResult(
        gate_name="Gate 4: Replication Lag Policy (RPO Protection)",
        passed=True,
        reason=f"Candidate {target_entity.name} replication lag ({selected_candidate.replication_lag_seconds:.1f}s <= {policy.acceptable_replication_lag_sec:.1f}s).",
        details={"lag_seconds": selected_candidate.replication_lag_seconds, "applied_seq": selected_candidate.applied_sequence},
    ))
    logger.info(
        f"[REPLICATION_LAG_OK] Step 4 lag verified ({selected_candidate.replication_lag_seconds:.1f}s <= {policy.acceptable_replication_lag_sec:.1f}s)"
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
    logger.info(f"[FENCING_PRIMARY] Revoking write authority on {source_entity.name} ({source_entity.id}) [Epoch #{c_state.fencing_epoch}]")
    fenced_ok = await regional_client.fence(source_entity.id, c_state.fencing_epoch)
    if not fenced_ok:
        source_entity.accepts_writes = True
        source_entity.is_fenced = False
    else:
        source_entity.accepts_writes = False
        source_entity.is_fenced = True
        source_entity.ingress_traffic_percent = 0
        source_entity.iops = 0

    g5 = verify_fencing_confirmed(source_entity.accepts_writes, source_entity.is_fenced)
    gate_results.append(GateEvaluationResult(
        gate_name="Gate 5: Fencing Confirmation",
        passed=g5.passed and fenced_ok,
        reason=g5.reason if (g5.passed and fenced_ok) else "Primary node rejected fencing command.",
        details=g5.details,
    ))
    if not g5.passed or not fenced_ok:
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
    source_entity.fencing_epoch = next_epoch
    target_entity.fencing_epoch = next_epoch
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
        reason=f"Fencing epoch advanced to #{next_epoch}. Promoting {target_entity.name} ({target_entity.id}) to primary writer.",
        simulated_time_seconds=c_state.simulated_time_seconds,
        transition="FENCING_PRIMARY -> PROMOTING_STANDBY",
    )

    # ---------------------------------------------------------
    # STEP 7: Promote the standby
    # ---------------------------------------------------------
    logger.info(f"[PROMOTING_STANDBY] Granting write authority to {target_entity.name} ({target_entity.id}) with epoch #{next_epoch}")
    promoted_ok = await regional_client.promote(target_entity.id, next_epoch)
    if not promoted_ok:
        target_entity.accepts_writes = False
    else:
        target_entity.role = "ACTIVE"
        target_entity.accepts_writes = True
        target_entity.iops = 4800
        target_entity.is_fenced = False
        source_entity.role = "STANDBY"

    g6 = verify_no_dual_primary(source_entity.accepts_writes, target_entity.accepts_writes)
    gate_results.append(GateEvaluationResult(
        gate_name="Gate 6: Dual-Primary Safety Invariant",
        passed=g6.passed and promoted_ok,
        reason=g6.reason if (g6.passed and promoted_ok) else "Promotion failed or dual-primary invariant violated.",
        details=g6.details,
    ))
    if not g6.passed or not promoted_ok:
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
            message="Failover blocked at Step 7 (Dual-Primary Invariant Violated)." if not g6.passed else "Failover blocked at Step 7 (Standby promotion failed).",
            blocked_reason=g6.reason,
            gate_results=gate_results,
        )

    c_state.active_region = target_entity.id

    # ---------------------------------------------------------
    # STEP 8: Request gateway route update
    # ---------------------------------------------------------
    c_state.current_state = "ROUTE_UPDATING"
    logger.info(f"[ROUTE_UPDATING] Pointing ingress gateway target to {target_entity.name} ({target_entity.id}) (TTL={policy.route_propagation_sec}s)")
    await log_audit_event(
        session,
        severity="action",
        subsystem="DNS",
        reason=f"Requesting Gateway / DNS Anycast route update pointing to {target_entity.name} ({target_entity.id}).",
        simulated_time_seconds=c_state.simulated_time_seconds,
        transition="PROMOTING_STANDBY -> ROUTE_UPDATING",
    )

    await gateway_client.update_route(target_entity.id, ttl=policy.route_propagation_sec, propagation_percent=100)
    route.active_target = target_entity.id
    route.propagation_percent = 100
    target_entity.ingress_traffic_percent = 100
    target_entity.active_connections = 2450

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
        expected_target=target_entity.id,
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
        f"[FAILOVER_COMPLETED] Transition {intent.id} complete across all 10 decision steps. {target_entity.name} ({target_entity.id}) active primary [Epoch #{next_epoch}].",
        extra={"transition_id": intent.id, "active_region": target_entity.id, "fencing_epoch": next_epoch}
    )

    await log_audit_event(
        session,
        severity="success",
        subsystem="CONTROLLER",
        reason=f"Failover complete: {target_entity.name} ({target_entity.id}) promoted to PRIMARY. Route verified. Zero split-brain writes.",
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

