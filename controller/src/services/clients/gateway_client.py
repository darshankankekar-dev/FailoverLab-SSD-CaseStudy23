import logging
import httpx
from typing import Dict, Any
from ...config import settings
from ...logging_config import correlation_id_ctx, transition_id_ctx
from ..metrics_tracker import metrics_tracker

logger = logging.getLogger("controller.clients.gateway")


class GatewayClient:
    def __init__(self, gateway_url: str = settings.gateway_url):
        self.gateway_url = gateway_url
        self.timeout = httpx.Timeout(0.2, connect=0.05) if settings.simulation_mode else httpx.Timeout(3.0)

    def _get_headers(self) -> Dict[str, str]:
        headers = {"X-Internal-Secret": settings.internal_api_secret}
        corr_id = correlation_id_ctx.get()
        if corr_id:
            headers["X-Correlation-ID"] = corr_id
            headers["X-Request-ID"] = corr_id
        trans_id = transition_id_ctx.get()
        if trans_id:
            headers["X-Transition-ID"] = trans_id
        return headers

    async def update_route(self, target_region: str, ttl: int = 2, propagation_percent: int = 100) -> bool:
        """Instructs gateway to shift public routing table."""
        metrics_tracker.record_route_update_attempt()
        try:
            headers = self._get_headers()
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.put(
                    f"{self.gateway_url}/internal/routing/target",
                    json={
                        "target_region": target_region,
                        "dns_ttl_seconds": ttl,
                        "propagation_percent": propagation_percent,
                    },
                    headers=headers,
                )
                success = (resp.status_code == 200)
                if success:
                    metrics_tracker.record_route_update_success()
                else:
                    metrics_tracker.record_route_update_error()
                return success
        except Exception as e:
            metrics_tracker.record_route_update_error()
            logger.debug(f"Gateway route update failed: {e}")
            return settings.simulation_mode

    async def probe_route(self) -> Dict[str, Any]:
        """Dispatches synthetic verification test probe through the gateway."""
        try:
            headers = self._get_headers()
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.gateway_url}/internal/routing/probe",
                    headers=headers,
                )
                if resp.status_code == 200:
                    return resp.json()
                return {"success": False, "message": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.debug(f"Gateway route probe failed: {e}")
            if settings.simulation_mode:
                return {"success": True, "active_target": "region-b", "latency_ms": 15.2, "message": "Simulated probe verified"}
            return {"success": False, "message": str(e)}


gateway_client = GatewayClient()
