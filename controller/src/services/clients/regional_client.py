import logging
import httpx
from typing import Dict, Any, Optional
from ...config import settings
from ...logging_config import correlation_id_ctx, transition_id_ctx, fencing_epoch_ctx

logger = logging.getLogger("controller.clients.regional")


class RegionalClient:
    def __init__(self, region_a_url: str = settings.region_a_url, region_b_url: str = settings.region_b_url):
        self.region_urls = {
            "region-a": region_a_url,
            "region-b": region_b_url,
        }
        self.timeout = httpx.Timeout(0.2, connect=0.05) if settings.simulation_mode else httpx.Timeout(3.0)

    def _get_headers(self, epoch: Optional[int] = None) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "X-Internal-Secret": settings.internal_api_secret,
        }
        corr_id = correlation_id_ctx.get()
        if corr_id:
            headers["X-Correlation-ID"] = corr_id
            headers["X-Request-ID"] = corr_id
        trans_id = transition_id_ctx.get()
        if trans_id:
            headers["X-Transition-ID"] = trans_id
        current_epoch = epoch if epoch is not None else fencing_epoch_ctx.get()
        if current_epoch is not None:
            headers["X-Fencing-Epoch"] = str(current_epoch)
        return headers

    async def get_health(self, region_id: str) -> Dict[str, Any]:
        """Probes the regional service health endpoint."""
        base_url = self.region_urls.get(region_id)
        if not base_url:
            return {"status": "DOWN", "error": f"Unknown region {region_id}"}

        try:
            headers = self._get_headers()
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{base_url}/health", headers=headers)
                if resp.status_code == 200:
                    return resp.json()
                return {"status": "DOWN", "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.debug(f"Health probe to {region_id} failed: {e}")
            if settings.simulation_mode:
                return {"status": "HEALTHY", "simulated": True}
            return {"status": "DOWN", "error": str(e)}

    async def fence(self, region_id: str, epoch: int) -> bool:
        """Invokes regional fence endpoint to revoke write authority."""
        base_url = self.region_urls.get(region_id)
        if not base_url:
            return False

        try:
            headers = self._get_headers(epoch=epoch)
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{base_url}/admin/fence",
                    json={"region_id": region_id, "fencing_epoch": epoch, "revoke_write_lease": True},
                    headers=headers,
                )
                return resp.status_code == 200
        except Exception as e:
            logger.debug(f"Fence command to {region_id} failed: {e}")
            return settings.simulation_mode

    async def promote(self, region_id: str, epoch: int) -> bool:
        """Invokes regional promote endpoint to grant write authority with new epoch."""
        base_url = self.region_urls.get(region_id)
        if not base_url:
            return False

        try:
            headers = self._get_headers(epoch=epoch)
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{base_url}/admin/promote",
                    json={"region_id": region_id, "fencing_epoch": epoch, "grant_write_authority": True},
                    headers=headers,
                )
                return resp.status_code == 200
        except Exception as e:
            logger.debug(f"Promote command to {region_id} failed: {e}")
            return settings.simulation_mode

    async def demote(self, region_id: str, epoch: int) -> bool:
        """Invokes regional demote endpoint to return node to standby mode."""
        base_url = self.region_urls.get(region_id)
        if not base_url:
            return False

        try:
            headers = self._get_headers(epoch=epoch)
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{base_url}/admin/demote",
                    json={"region_id": region_id, "fencing_epoch": epoch},
                    headers=headers,
                )
                return resp.status_code == 200
        except Exception as e:
            logger.debug(f"Demote command to {region_id} failed: {e}")
            return settings.simulation_mode


regional_client = RegionalClient()
