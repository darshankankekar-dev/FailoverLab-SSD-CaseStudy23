from typing import List, Dict, Any, NamedTuple


class GateResult(NamedTuple):
    passed: bool
    reason: str
    details: Dict[str, Any] = {}


def can_initiate_quorum(consecutive_failures: int, threshold: int) -> GateResult:
    """Gate 1: Consecutive failure debounce check."""
    if consecutive_failures >= threshold:
        return GateResult(
            passed=True,
            reason=f"Consecutive probe failure threshold reached ({consecutive_failures}/{threshold}). Proceeding to independent quorum evaluation.",
            details={"consecutive_failures": consecutive_failures, "threshold": threshold},
        )
    return GateResult(
        passed=False,
        reason=f"Consecutive failures ({consecutive_failures}) below required threshold ({threshold}). Primary suspected but failover suppressed to avoid false positives.",
        details={"consecutive_failures": consecutive_failures, "threshold": threshold},
    )


def evaluate_quorum_majority(
    voter_votes: List[str], majority_required: int
) -> GateResult:
    """Gate 2: Simulated Quorum Majority Gate."""
    outage_votes = [v for v in voter_votes if v == "PRIMARY_OUTAGE"]
    count = len(outage_votes)
    total = len(voter_votes)

    if count >= majority_required:
        return GateResult(
            passed=True,
            reason=f"Quorum consensus achieved: {count} of {total} independent voters confirmed primary outage (required: {majority_required}).",
            details={"outage_votes": count, "total_voters": total, "majority_required": majority_required},
        )
    return GateResult(
        passed=False,
        reason=f"Insufficient quorum consensus: Only {count} of {total} voters confirmed outage (required: {majority_required}). Transition blocked to prevent false partition failover.",
        details={"outage_votes": count, "total_voters": total, "majority_required": majority_required},
    )


def check_standby_readiness(region_b_health: str) -> GateResult:
    """Gate 3: Standby Readiness Gate."""
    if region_b_health != "HEALTHY":
        return GateResult(
            passed=False,
            reason=f"Standby readiness check failed: Region B is currently {region_b_health}. Promoting an unhealthy standby would cause total service outage.",
            details={"health": region_b_health},
        )
    return GateResult(
        passed=True,
        reason="Standby readiness verified: Region B is HEALTHY and capable of assuming write authority.",
        details={"health": region_b_health},
    )


def check_replication_lag_policy(
    lag_seconds: float,
    replication_status: str,
    acceptable_lag_sec: float,
) -> GateResult:
    """Gate 4: Replication Lag Policy Gate (RPO Protection)."""
    if replication_status == "SEVERED":
        return GateResult(
            passed=False,
            reason="Replication policy check failed: Replication link is SEVERED. Unsynchronized WAL delta cannot be verified.",
            details={"status": replication_status, "lag_seconds": lag_seconds},
        )
    if lag_seconds > acceptable_lag_sec:
        return GateResult(
            passed=False,
            reason=f"Replication lag gate failed: Current replication lag ({lag_seconds:.1f}s) exceeds acceptable threshold ({acceptable_lag_sec:.1f}s). Promotion blocked to protect against catastrophic RPO data loss.",
            details={"lag_seconds": lag_seconds, "acceptable_lag_sec": acceptable_lag_sec},
        )
    return GateResult(
        passed=True,
        reason=f"Replication lag satisfies policy: Current lag ({lag_seconds:.1f}s) is within acceptable limit ({acceptable_lag_sec:.1f}s).",
        details={"lag_seconds": lag_seconds, "acceptable_lag_sec": acceptable_lag_sec},
    )


def verify_fencing_confirmed(accepts_writes: bool, is_fenced: bool) -> GateResult:
    """Gate 5: Fencing Confirmation Gate."""
    if accepts_writes:
        return GateResult(
            passed=False,
            reason="Fencing safety gate violated: Old primary is still marked as accepting writes. Promoting standby now would create a catastrophic SPLIT-BRAIN.",
            details={"accepts_writes": accepts_writes, "is_fenced": is_fenced},
        )
    if not is_fenced:
        return GateResult(
            passed=False,
            reason="Fencing safety gate violated: Storage fence for old primary has not been acknowledged by coordinator.",
            details={"accepts_writes": accepts_writes, "is_fenced": is_fenced},
        )
    return GateResult(
        passed=True,
        reason="Fencing confirmed: Old primary is hard-fenced and revoked of all write authorization. Epoch advanced safely.",
        details={"accepts_writes": accepts_writes, "is_fenced": is_fenced},
    )


def verify_no_dual_primary(region_a_writes: bool, region_b_writes: bool) -> GateResult:
    """Gate 6: Universal Dual-Primary Safety Invariant."""
    if region_a_writes and region_b_writes:
        return GateResult(
            passed=False,
            reason="CRITICAL SAFETY INVARIANT VIOLATED: Both Region A and Region B are marked as accepting writes simultaneously (Split-Brain).",
            details={"region_a_writes": region_a_writes, "region_b_writes": region_b_writes},
        )
    return GateResult(
        passed=True,
        reason="Dual-primary invariant satisfied: Exactly one (or zero) writable region authorized.",
        details={"region_a_writes": region_a_writes, "region_b_writes": region_b_writes},
    )


def verify_route_operational(
    active_target: str,
    expected_target: str,
    propagation_percent: int,
    verification_status: str,
    route_failure_injected: bool = False,
) -> GateResult:
    """Gate 7: Route Switching & Verification Gate."""
    if route_failure_injected or verification_status == "FAILED":
        return GateResult(
            passed=False,
            reason=f"Route verification failed: Synthetic test requests to {expected_target.upper()} timed out or failed to resolve. Failover marked unverified.",
            details={"active_target": active_target, "verification_status": verification_status},
        )
    if active_target != expected_target:
        return GateResult(
            passed=False,
            reason=f"Route verification failed: Active routing target ({active_target}) does not match promoted region ({expected_target}).",
            details={"active_target": active_target, "expected_target": expected_target},
        )
    if propagation_percent < 100:
        return GateResult(
            passed=False,
            reason=f"Route verification in progress: DNS propagation at {propagation_percent}%. Test probe pending complete convergence.",
            details={"propagation_percent": propagation_percent},
        )
    return GateResult(
        passed=True,
        reason=f"Route operational: 100% traffic successfully routed and synthetic test probe verified on {expected_target.upper()}.",
        details={"active_target": active_target, "propagation_percent": propagation_percent},
    )


def check_failback_readiness(
    region_a_health: str,
    replication_status: str,
    lag_seconds: float,
    acceptable_lag_sec: float,
) -> GateResult:
    """Gate 8: Guarded Failback Readiness Gate."""
    if region_a_health != "HEALTHY":
        return GateResult(
            passed=False,
            reason=f"Failback blocked: Original primary (Region A) is still {region_a_health}.",
            details={"health": region_a_health},
        )
    if replication_status != "SYNCED" and lag_seconds > acceptable_lag_sec:
        return GateResult(
            passed=False,
            reason=f"Failback blocked: Reverse replication lag ({lag_seconds:.1f}s) has not yet reconciled with active secondary.",
            details={"status": replication_status, "lag_seconds": lag_seconds, "acceptable_lag": acceptable_lag_sec},
        )
    return GateResult(
        passed=True,
        reason="Failback readiness verified: Region A is HEALTHY and reverse replication is reconciled. Awaiting deliberate operator authorization.",
        details={"health": region_a_health, "lag_seconds": lag_seconds},
    )

