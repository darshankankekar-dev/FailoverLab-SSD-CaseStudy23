import logging
import httpx
from typing import Dict, Any, Optional
from ...config import settings

logger = logging.getLogger("controller.clients.replication")


class ReplicationClient:
    def __init__(self, replication_worker_url: str = settings.replication_worker_url):
        self.worker_url = replication_worker_url
        self.timeout = httpx.Timeout(0.05, connect=0.02) if settings.simulation_mode else httpx.Timeout(1.5)

    async def get_status(self) -> Optional[Dict[str, Any]]:
        """Queries replication worker for per-destination operational telemetry."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.worker_url}/status")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            logger.debug(f"Could not reach replication worker at {self.worker_url}: {e}")
        return None

    async def set_delay(self, delay_seconds: float, destination: Optional[str] = None) -> bool:
        """Injects or adjusts replication throttling delay globally or per target."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload = {"delay_seconds": delay_seconds, "destination": destination}
                resp = await client.post(f"{self.worker_url}/controls/delay", json=payload)
                return resp.status_code == 200
        except Exception as e:
            logger.debug(f"Failed to set replication delay at {self.worker_url}: {e}")
            return False

    async def pause(self, destination: Optional[str] = None) -> bool:
        """Pauses replication globally or for a specific destination."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = f"{self.worker_url}/controls/pause"
                if destination:
                    url = f"{url}?destination={destination}"
                resp = await client.post(url)
                return resp.status_code == 200
        except Exception as e:
            logger.debug(f"Failed to pause replication at {self.worker_url}: {e}")
            return False

    async def resume(self, destination: Optional[str] = None) -> bool:
        """Resumes replication globally or for a specific destination."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = f"{self.worker_url}/controls/resume"
                if destination:
                    url = f"{url}?destination={destination}"
                resp = await client.post(url)
                return resp.status_code == 200
        except Exception as e:
            logger.debug(f"Failed to resume replication at {self.worker_url}: {e}")
            return False


replication_client = ReplicationClient()
