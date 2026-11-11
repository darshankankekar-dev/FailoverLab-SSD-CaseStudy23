from datetime import datetime, timezone
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger("gateway.routing")


class RouteTable:
    """
    Maintains dynamic routing targets, regional roles, and DNS propagation state.
    Guarantees writer safety by verifying that ordinary write requests are never
    forwarded to a region designated STANDBY.
    """

    def __init__(
        self,
        default_target: str,
        region_a_url: str,
        region_b_url: str,
        dns_ttl_seconds: int = 2,
        propagation_percent: int = 100,
    ):
        self.active_target = default_target
        self.target_urls: Dict[str, str] = {
            "region-a": region_a_url.rstrip("/"),
            "region-b": region_b_url.rstrip("/"),
        }
        self.target_roles: Dict[str, str] = {
            "region-a": "ACTIVE" if default_target == "region-a" else "STANDBY",
            "region-b": "ACTIVE" if default_target == "region-b" else "STANDBY",
        }
        self.dns_ttl_seconds = dns_ttl_seconds
        self.propagation_percent = propagation_percent
        self.route_epoch = 1
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

    def is_write_allowed(self) -> bool:
        """Safety invariant: ordinary writes are only allowed if the active target is ACTIVE."""
        return self.target_roles.get(self.active_target, "STANDBY") == "ACTIVE"

    def get_active_url(self) -> str:
        url = self.target_urls.get(self.active_target)
        if not url:
            raise RuntimeError(f"No backend URL configured for target region '{self.active_target}'")
        return url

    def get_route_state(self) -> Dict[str, Any]:
        return {
            "active_target": self.active_target,
            "target_role": self.target_roles.get(self.active_target, "STANDBY"),
            "target_url": self.get_active_url(),
            "target_urls": dict(self.target_urls),
            "target_roles": dict(self.target_roles),
            "dns_ttl_seconds": self.dns_ttl_seconds,
            "propagation_percent": self.propagation_percent,
            "route_epoch": self.route_epoch,
            "last_updated_at": self.last_updated_at,
        }
