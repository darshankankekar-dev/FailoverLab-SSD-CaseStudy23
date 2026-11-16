"""
FailoverLab Candidate Selection Engine
Evaluates all registered standby regions to select the safest, most eligible failover target.
Enforces multi-criteria filtering and ranking:
1. Freshness: Prefers the candidate with the highest applied replication sequence.
2. Latency: Uses measured/simulated latency as a subsequent ranking factor.
3. Capacity: Uses configured IOPS capacity as a tie-breaker.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from .registry import get_region_definition


@dataclass
class CandidateEvaluation:
    region_id: str
    name: str
    cloud_zone: str
    is_eligible: bool
    rejection_reasons: List[str] = field(default_factory=list)
    health: str = "HEALTHY"
    role: str = "STANDBY"
    is_fenced: bool = False
    app_servers_healthy: int = 12
    app_servers_total: int = 12
    applied_sequence: int = 0
    replication_lag_seconds: float = 0.8
    latency_ms: int = 34
    capacity_iops: int = 4800

    def summary(self) -> str:
        if self.is_eligible:
            return (
                f"{self.name} ({self.region_id}) [ELIGIBLE]: "
                f"seq={self.applied_sequence}, lag={self.replication_lag_seconds:.1f}s, "
                f"latency={self.latency_ms}ms, iops={self.capacity_iops}"
            )
        reasons = "; ".join(self.rejection_reasons)
        return f"{self.name} ({self.region_id}) [INELIGIBLE]: {reasons}"


def evaluate_candidate(
    region_entity: Any,
    acceptable_lag_sec: float = 5.0,
    override_lag: Optional[float] = None,
    override_sequence: Optional[int] = None,
    override_latency: Optional[int] = None,
    active_region_id: str = "region-a",
) -> CandidateEvaluation:
    """Evaluates a single region entity against safety policy requirements."""
    reg_def = get_region_definition(region_entity.id)
    name = region_entity.name if hasattr(region_entity, "name") else (reg_def.name if reg_def else region_entity.id)
    cloud_zone = region_entity.cloud_zone if hasattr(region_entity, "cloud_zone") else (reg_def.cloud_zone if reg_def else "unknown")
    latency = override_latency if override_latency is not None else (reg_def.nominal_latency_ms if reg_def else 50)
    capacity = reg_def.default_iops if reg_def else getattr(region_entity, "iops", 4800)
    seq = override_sequence if override_sequence is not None else getattr(region_entity, "applied_sequence", 0)
    lag = override_lag if override_lag is not None else getattr(region_entity, "replication_lag_seconds", 0.8)

    rejection_reasons: List[str] = []

    # 1. Active region check (cannot failover to current active primary)
    if region_entity.id == active_region_id:
        rejection_reasons.append(f"Region is currently the active primary ({active_region_id})")

    # 2. Health status check
    health = getattr(region_entity, "health", "HEALTHY").upper()
    if health != "HEALTHY":
        rejection_reasons.append(f"Health status is {health} (expected HEALTHY)")

    # 3. Application service readiness
    app_healthy = getattr(region_entity, "app_servers_healthy", 12)
    app_total = getattr(region_entity, "app_servers_total", 12)
    if app_healthy <= 0:
        rejection_reasons.append(f"Application servers unavailable ({app_healthy}/{app_total})")

    # 4. Storage fencing status
    is_fenced = getattr(region_entity, "is_fenced", False)
    if is_fenced:
        rejection_reasons.append("Storage node is currently fenced")

    # 5. Standby role invariant
    role = getattr(region_entity, "role", "STANDBY").upper()
    if role != "STANDBY" and region_entity.id != active_region_id:
        rejection_reasons.append(f"Role is {role} (expected STANDBY)")

    # 6. Replication lag policy (RPO protection)
    if lag > acceptable_lag_sec:
        rejection_reasons.append(
            f"Replication lag ({lag:.1f}s) exceeds policy threshold ({acceptable_lag_sec:.1f}s)"
        )

    is_eligible = len(rejection_reasons) == 0

    return CandidateEvaluation(
        region_id=region_entity.id,
        name=name,
        cloud_zone=cloud_zone,
        is_eligible=is_eligible,
        rejection_reasons=rejection_reasons,
        health=health,
        role=role,
        is_fenced=is_fenced,
        app_servers_healthy=app_healthy,
        app_servers_total=app_total,
        applied_sequence=seq,
        replication_lag_seconds=lag,
        latency_ms=latency,
        capacity_iops=capacity,
    )


def select_best_standby_candidate(
    regions: List[Any],
    active_region_id: str,
    acceptable_lag_sec: float = 5.0,
    preferred_target: Optional[str] = "auto",
    regional_lags: Optional[Dict[str, float]] = None,
    regional_sequences: Optional[Dict[str, int]] = None,
    regional_latencies: Optional[Dict[str, int]] = None,
) -> Tuple[Optional[CandidateEvaluation], List[CandidateEvaluation], str]:
    """
    Selects the optimal failover target candidate among all registered standbys.
    If preferred_target is a specific region ID (not 'auto'), validates that region specifically.
    If preferred_target is 'auto' (or None), dynamically filters and ranks eligible candidates:
      1. Freshest applied sequence (highest applied_sequence).
      2. Lowest latency (latency_ms).
      3. Highest capacity (capacity_iops).
    """
    if regional_lags is None:
        regional_lags = {}
    if regional_sequences is None:
        regional_sequences = {}
    if regional_latencies is None:
        regional_latencies = {}

    evaluations: List[CandidateEvaluation] = []
    # Filter out the currently active region
    standby_regions = [r for r in regions if r.id != active_region_id]

    for r in standby_regions:
        ev = evaluate_candidate(
            region_entity=r,
            acceptable_lag_sec=acceptable_lag_sec,
            override_lag=regional_lags.get(r.id),
            override_sequence=regional_sequences.get(r.id),
            override_latency=regional_latencies.get(r.id),
            active_region_id=active_region_id,
        )
        evaluations.append(ev)

    target_norm = (preferred_target or "auto").lower().strip()

    # Manual specific target requested
    if target_norm != "auto":
        match = next((ev for ev in evaluations if ev.region_id == target_norm), None)
        if not match:
            return None, evaluations, f"Target region '{preferred_target}' is not a registered standby candidate."
        if not match.is_eligible:
            return None, evaluations, f"Target region '{match.name}' ({match.region_id}) is not eligible: {'; '.join(match.rejection_reasons)}."
        return match, evaluations, f"Selected manually targeted candidate {match.name} ({match.region_id})."

    # Automatic selection among eligible standbys
    eligible = [ev for ev in evaluations if ev.is_eligible]
    if not eligible:
        details = "; ".join(f"{ev.name} ({ev.region_id}): {', '.join(ev.rejection_reasons)}" for ev in evaluations)
        return None, evaluations, f"No eligible standby candidate found. Candidate evaluations: {details}"

    # Ranking:
    # 1. Highest applied_sequence (-c.applied_sequence)
    # 2. Lowest latency (c.latency_ms)
    # 3. Highest capacity (-c.capacity_iops)
    # 4. Region ID (c.region_id)
    eligible.sort(
        key=lambda c: (
            -c.applied_sequence,
            c.latency_ms,
            -c.capacity_iops,
            c.region_id,
        )
    )

    selected = eligible[0]
    reason = (
        f"Selected optimal candidate {selected.name} ({selected.region_id}) "
        f"[seq={selected.applied_sequence}, latency={selected.latency_ms}ms, iops={selected.capacity_iops}] "
        f"from {len(eligible)} eligible candidate(s)."
    )
    return selected, evaluations, reason
