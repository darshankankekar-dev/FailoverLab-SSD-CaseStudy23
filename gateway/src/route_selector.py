from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field
import logging

from .client_profiles import ClientProfile, resolve_client_profile, get_simulated_wan_delay

logger = logging.getLogger("gateway.route_selector")


class RouteDecision(BaseModel):
    target_region: str
    target_url: str
    target_role: str
    consistency_level: str  # "eventual", "strong", "write"
    route_reason: str
    client_region: str
    client_display_name: str
    simulated_wan_delay_ms: float
    replication_lag_seconds: float
    candidate_ranking: List[Dict[str, Any]] = Field(default_factory=list)


class RouteSelector:
    """
    Evaluates multi-region routing requests across three classes:
    A. Eventual-consistency reads (latency-aware + replication staleness filtering).
    B. Strong-consistency reads (strictly routed to active writer).
    C. Writes (strictly routed to active writer; rejects standby writes).
    """

    def __init__(self, max_stale_seconds: float = 5.0):
        self.max_stale_seconds = max_stale_seconds

    def select_route(
        self,
        method: str,
        path: str,
        active_target: str,
        target_urls: Dict[str, str],
        target_roles: Dict[str, str],
        regional_health: Dict[str, str],
        regional_lag: Dict[str, float],
        client_region_identifier: Optional[str] = None,
        explicit_consistency: Optional[str] = None,
    ) -> RouteDecision:
        profile = resolve_client_profile(client_region_identifier)
        method_upper = method.upper().strip()
        path_lower = path.lower().strip()

        # Class C: Writes (Always route to active writer)
        if method_upper in {"POST", "PUT", "DELETE", "PATCH"}:
            active_url = target_urls.get(active_target, "")
            active_role = target_roles.get(active_target, "STANDBY")
            wan_delay = get_simulated_wan_delay(profile, active_target)
            return RouteDecision(
                target_region=active_target,
                target_url=active_url,
                target_role=active_role,
                consistency_level="write",
                route_reason="active_writer_write",
                client_region=profile.client_region_id,
                client_display_name=profile.display_name,
                simulated_wan_delay_ms=wan_delay,
                replication_lag_seconds=0.0,
            )

        # Class B: Strong-consistency reads
        # Determined by explicit header 'X-Consistency-Level: strong', or strong endpoints (inventory, order status)
        is_strong_read = False
        if explicit_consistency and explicit_consistency.lower().strip() in {"strong", "linearizable"}:
            is_strong_read = True
        elif "/inventory/" in path_lower or "/inventory" == path_lower:
            is_strong_read = True
        elif "/orders/" in path_lower:
            is_strong_read = True

        if is_strong_read:
            active_url = target_urls.get(active_target, "")
            active_role = target_roles.get(active_target, "STANDBY")
            wan_delay = get_simulated_wan_delay(profile, active_target)
            return RouteDecision(
                target_region=active_target,
                target_url=active_url,
                target_role=active_role,
                consistency_level="strong",
                route_reason="active_writer_strong_read",
                client_region=profile.client_region_id,
                client_display_name=profile.display_name,
                simulated_wan_delay_ms=wan_delay,
                replication_lag_seconds=0.0,
            )

        # Class A: Eventual-consistency reads (Product catalogue, public details, general queries)
        # Sort regions by client profile latency
        sorted_regions = sorted(
            target_urls.keys(),
            key=lambda r: profile.latencies_ms.get(r, 999.0),
        )

        nearest_region = sorted_regions[0] if sorted_regions else active_target
        candidate_evaluations: List[Dict[str, Any]] = []

        chosen_region: Optional[str] = None
        chosen_reason: str = ""

        for r_id in sorted_regions:
            health = regional_health.get(r_id, "HEALTHY")
            lag = regional_lag.get(r_id, 0.0 if r_id == active_target else 0.8)
            lat = profile.latencies_ms.get(r_id, 999.0)

            is_healthy = (health == "HEALTHY")
            is_fresh = (r_id == active_target) or (lag <= self.max_stale_seconds)
            is_eligible = is_healthy and is_fresh

            rejection_reasons = []
            if not is_healthy:
                rejection_reasons.append(f"unhealthy ({health})")
            if not is_fresh:
                rejection_reasons.append(f"stale (lag {lag:.2f}s > {self.max_stale_seconds}s)")

            candidate_evaluations.append({
                "region_id": r_id,
                "latency_ms": lat,
                "health": health,
                "lag_seconds": lag,
                "eligible": is_eligible,
                "rejection": "; ".join(rejection_reasons) if rejection_reasons else None,
            })

            if is_eligible and chosen_region is None:
                chosen_region = r_id
                if r_id == nearest_region:
                    chosen_reason = "nearest_eligible_standby" if r_id != active_target else "nearest_eligible_active"
                else:
                    nearest_eval = candidate_evaluations[0]
                    reasons_str = nearest_eval.get("rejection") or "ineligible"
                    if r_id == active_target:
                        chosen_reason = f"active_fallback (nearest '{nearest_region}' was {reasons_str})"
                    else:
                        chosen_reason = f"failover_replica_fallback (nearest '{nearest_region}' was {reasons_str})"

        # If no eligible candidate found (e.g. all standbys unhealthy/stale), fallback to active writer
        if not chosen_region:
            chosen_region = active_target
            chosen_reason = "active_fallback_all_standbys_ineligible"

        chosen_url = target_urls.get(chosen_region, "")
        chosen_role = target_roles.get(chosen_region, "STANDBY")
        chosen_lag = regional_lag.get(chosen_region, 0.0)
        wan_delay = get_simulated_wan_delay(profile, chosen_region)

        return RouteDecision(
            target_region=chosen_region,
            target_url=chosen_url,
            target_role=chosen_role,
            consistency_level="eventual",
            route_reason=chosen_reason,
            client_region=profile.client_region_id,
            client_display_name=profile.display_name,
            simulated_wan_delay_ms=wan_delay,
            replication_lag_seconds=chosen_lag,
            candidate_ranking=candidate_evaluations,
        )


route_selector = RouteSelector()
