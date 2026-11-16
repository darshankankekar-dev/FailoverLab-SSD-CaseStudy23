from datetime import datetime, timezone
from typing import Dict, Any, Optional
import logging

from .route_selector import RouteSelector, RouteDecision

logger = logging.getLogger("gateway.routing")


class RouteTable:
    """
    Maintains dynamic routing targets, regional roles, health status, replication lag,
    and DNS propagation state.
    Provides latency-aware routing for eventual reads while strictly guaranteeing
    single-writer consistency for strong reads and writes.
    """

    def __init__(
        self,
        default_target: str,
        region_a_url: str,
        region_b_url: str,
        region_c_url: Optional[str] = None,
        region_d_url: Optional[str] = None,
        region_e_url: Optional[str] = None,
        dns_ttl_seconds: int = 2,
        propagation_percent: int = 100,
        extra_targets: Optional[Dict[str, str]] = None,
        max_stale_seconds: float = 5.0,
    ):
        self.active_target = default_target
        self.target_urls: Dict[str, str] = {
            "region-a": region_a_url.rstrip("/"),
            "region-b": region_b_url.rstrip("/"),
        }
        if region_c_url:
            self.target_urls["region-c"] = region_c_url.rstrip("/")
        if region_d_url:
            self.target_urls["region-d"] = region_d_url.rstrip("/")
        if region_e_url:
            self.target_urls["region-e"] = region_e_url.rstrip("/")
        if extra_targets:
            for k, v in extra_targets.items():
                self.target_urls[k] = v.rstrip("/")

        self.target_roles: Dict[str, str] = {
            r: ("ACTIVE" if default_target == r else "STANDBY")
            for r in self.target_urls
        }
        self.regional_health: Dict[str, str] = {
            r: "HEALTHY" for r in self.target_urls
        }
        self.regional_lag: Dict[str, float] = {
            r: (0.0 if r == default_target else 0.8) for r in self.target_urls
        }
        self.regional_measured_latency: Dict[str, float] = {
            r: 0.0 for r in self.target_urls
        }

        self.dns_ttl_seconds = dns_ttl_seconds
        self.propagation_percent = propagation_percent
        self.route_epoch = 1
        self.max_stale_seconds = max_stale_seconds
        self.route_selector = RouteSelector(max_stale_seconds=max_stale_seconds)
        self.last_updated_at = datetime.now(timezone.utc).isoformat()

    def set_target(
        self,
        target_region: str,
        target_role: str = "ACTIVE",
        dns_ttl_seconds: Optional[int] = None,
        propagation_percent: Optional[int] = None,
    ) -> Dict[str, Any]:
        target_norm = target_region.lower().strip()
        if target_norm not in self.target_urls:
            raise ValueError(f"Unknown region '{target_region}'. Known regions: {list(self.target_urls.keys())}")

        if target_norm != self.active_target:
            self.route_epoch += 1

        self.active_target = target_norm
        # Update regional roles
        for r in self.target_roles:
            self.target_roles[r] = target_role if r == target_norm else "STANDBY"

        if dns_ttl_seconds is not None:
            self.dns_ttl_seconds = dns_ttl_seconds
        if propagation_percent is not None:
            self.propagation_percent = max(0, min(100, propagation_percent))

        self.last_updated_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            f"Gateway route shifted to active_target='{self.active_target}' (role={target_role}), "
            f"epoch={self.route_epoch}, ttl={self.dns_ttl_seconds}s, "
            f"propagation={self.propagation_percent}%"
        )
        return self.get_route_state()

    def set_region_role(self, region_id: str, role: str) -> None:
        reg_norm = region_id.lower().strip()
        if reg_norm in self.target_roles:
            self.target_roles[reg_norm] = role.upper()

    def set_region_health(self, region_id: str, health: str) -> None:
        reg_norm = region_id.lower().strip()
        if reg_norm in self.regional_health:
            self.regional_health[reg_norm] = health.upper()

    def set_region_lag(self, region_id: str, lag_seconds: float) -> None:
        reg_norm = region_id.lower().strip()
        if reg_norm in self.regional_lag:
            self.regional_lag[reg_norm] = max(0.0, float(lag_seconds))

    def update_telemetry(
        self,
        regional_health: Optional[Dict[str, str]] = None,
        regional_lag: Optional[Dict[str, float]] = None,
        max_stale_seconds: Optional[float] = None,
    ) -> None:
        if regional_health:
            for r, h in regional_health.items():
                self.set_region_health(r, h)
        if regional_lag:
            for r, l in regional_lag.items():
                self.set_region_lag(r, l)
        if max_stale_seconds is not None:
            self.max_stale_seconds = max_stale_seconds
            self.route_selector.max_stale_seconds = max_stale_seconds

    def record_measured_latency(self, region_id: str, latency_ms: float) -> None:
        reg_norm = region_id.lower().strip()
        if reg_norm in self.regional_measured_latency:
            # Simple exponential moving average
            prev = self.regional_measured_latency[reg_norm]
            if prev <= 0:
                self.regional_measured_latency[reg_norm] = round(latency_ms, 2)
            else:
                self.regional_measured_latency[reg_norm] = round(0.7 * prev + 0.3 * latency_ms, 2)

    def is_write_allowed(self) -> bool:
        """Safety invariant: ordinary writes are only allowed if the active target is ACTIVE."""
        return self.target_roles.get(self.active_target, "STANDBY") == "ACTIVE"

    def get_active_url(self) -> str:
        url = self.target_urls.get(self.active_target)
        if not url:
            raise RuntimeError(f"No backend URL configured for target region '{self.active_target}'")
        return url

    def evaluate_route(
        self,
        method: str,
        path: str,
        client_region_identifier: Optional[str] = None,
        explicit_consistency: Optional[str] = None,
    ) -> RouteDecision:
        """
        Calculates the routing decision across the 3 explicit classes:
        - Writes (Always to active writer)
        - Strong reads (Always to active writer)
        - Eventual reads (Lowest latency eligible standby/active)
        """
        return self.route_selector.select_route(
            method=method,
            path=path,
            active_target=self.active_target,
            target_urls=self.target_urls,
            target_roles=self.target_roles,
            regional_health=self.regional_health,
            regional_lag=self.regional_lag,
            client_region_identifier=client_region_identifier,
            explicit_consistency=explicit_consistency,
        )

    def get_route_state(self) -> Dict[str, Any]:
        return {
            "active_target": self.active_target,
            "target_role": self.target_roles.get(self.active_target, "STANDBY"),
            "target_url": self.get_active_url(),
            "target_urls": dict(self.target_urls),
            "target_roles": dict(self.target_roles),
            "regional_health": dict(self.regional_health),
            "regional_lag": dict(self.regional_lag),
            "regional_measured_latency": dict(self.regional_measured_latency),
            "max_stale_seconds": self.max_stale_seconds,
            "dns_ttl_seconds": self.dns_ttl_seconds,
            "propagation_percent": self.propagation_percent,
            "route_epoch": self.route_epoch,
            "last_updated_at": self.last_updated_at,
        }
