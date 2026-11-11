import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import httpx
from .config import settings
from .lag_tracker import lag_tracker

logger = logging.getLogger("replication.engine")


class ReplicationEngine:
    def __init__(self):
        self.active_region: str = "region-a"
        self.is_paused: bool = settings.is_paused
        self.injected_delay_sec: float = settings.injected_delay_sec
        self.last_replicated_seq: int = 0
        self.reversal_count: int = 0
        self.total_applied_events: int = 0
        self.consecutive_errors: int = 0

    @property
    def source_region(self) -> str:
        return self.active_region

    @property
    def target_region(self) -> str:
        return "region-b" if self.active_region == "region-a" else "region-a"

    def get_region_url(self, region_id: str) -> str:
        return settings.region_a_url if region_id == "region-a" else settings.region_b_url

    async def fetch_controller_active_region(self) -> Optional[str]:
        """Queries the Controller service to determine the authoritative active writer."""
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                resp = await client.get(f"{settings.controller_url}/api/v1/state")
                if resp.status_code == 200:
                    data = resp.json()
                    new_active = data.get("active_region", "region-a")
                    if new_active != self.active_region:
                        logger.info(
                            f"Failover detected by replication worker! Reversing replication: "
                            f"{self.active_region} -> {new_active}"
                        )
                        self.active_region = new_active
                        self.reversal_count += 1
                        # Reset sequence cursor for the new source database
                        self.last_replicated_seq = 0
                    return self.active_region
        except Exception as e:
            logger.debug(f"Controller state check skipped: {e}")
        return self.active_region

    async def sync_iteration(self) -> Dict[str, Any]:
        """
        Executes one replication synchronization iteration:
        1. Check Controller active writer (detect failover and reverse direction).
        2. Read unreplicated events from active source outbox.
        3. Deliver batch to standby target via /internal/replication/apply.
        4. Handle deduplication and update tracking cursor.
        """
        if self.is_paused:
            return {
                "status": "PAUSED",
                "message": "Replication is currently paused (simulated WAN partition/severed link).",
                "lag_metrics": lag_tracker.to_dict(),
            }

        # Step 1: Discover authoritative active region
        await self.fetch_controller_active_region()

        source_url = self.get_region_url(self.source_region)
        target_url = self.get_region_url(self.target_region)

        headers = {}
        if settings.internal_api_secret:
            headers["X-Internal-Secret"] = settings.internal_api_secret

        # Step 2: Fetch outbox events from active source
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                outbox_resp = await client.get(
                    f"{source_url}/internal/replication/outbox",
                    params={"since_sequence_id": self.last_replicated_seq, "limit": settings.batch_size},
                    headers=headers,
                )
                if outbox_resp.status_code != 200:
                    self.consecutive_errors += 1
                    return {"status": "SOURCE_ERROR", "error": f"HTTP {outbox_resp.status_code} from {self.source_region}"}

                batch_data = outbox_resp.json()
        except Exception as e:
            self.consecutive_errors += 1
            logger.debug(f"Outbox fetch from {self.source_region} failed: {e}")
            return {"status": "SOURCE_UNREACHABLE", "error": str(e)}

        events = batch_data.get("events", [])
        highest_seq = batch_data.get("highest_sequence_id", 0)
        oldest_ts_str = batch_data.get("oldest_unreplicated_created_at")
        oldest_ts = datetime.fromisoformat(oldest_ts_str) if oldest_ts_str else None

        # Update lag measurements
        lag_tracker.update_metrics(
            source_highest_seq=highest_seq,
            last_replicated_seq=self.last_replicated_seq,
            oldest_unreplicated_ts=oldest_ts,
            injected_delay_sec=self.injected_delay_sec,
        )

        if not events:
            self.consecutive_errors = 0
            return {
                "status": "CAUGHT_UP",
                "source_region": self.source_region,
                "target_region": self.target_region,
                "last_sequence_id": self.last_replicated_seq,
                "lag_metrics": lag_tracker.to_dict(),
            }

        # Step 3: Inject artificial latency if configured (e.g. Scenario F lag testing)
        if self.injected_delay_sec > 0:
            await asyncio.sleep(min(self.injected_delay_sec, 2.0))

        # Step 4: Deliver replication batch to target standby
        apply_payload = {
            "source_region": self.source_region,
            "events": [
                {
                    "event_id": ev["event_id"],
                    "source_sequence_id": ev["sequence_id"],
                    "record_key": ev["record_key"],
                    "operation": ev["operation"],
                    "payload": ev["payload"],
                    "version": ev["version"],
                    "fencing_epoch": ev["fencing_epoch"],
                    "source_region": self.source_region,
                    "created_at": ev["created_at"],
                }
                for ev in events
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                apply_resp = await client.post(
                    f"{target_url}/internal/replication/apply",
                    json=apply_payload,
                    headers=headers,
                )
                if apply_resp.status_code != 200:
                    self.consecutive_errors += 1
                    return {
                        "status": "TARGET_APPLY_FAILED",
                        "error": f"Target {self.target_region} returned HTTP {apply_resp.status_code}: {apply_resp.text}",
                    }

                apply_result = apply_resp.json()
        except Exception as e:
            self.consecutive_errors += 1
            logger.warning(f"Replication delivery to {self.target_region} failed: {e}")
            return {"status": "TARGET_UNREACHABLE", "error": str(e)}

        # Step 5: Update replication progress cursor and acknowledge source
        new_highest = apply_result.get("highest_sequence_id", self.last_replicated_seq)
        self.last_replicated_seq = new_highest
        self.total_applied_events += apply_result.get("applied_count", 0)
        self.consecutive_errors = 0
        logger.info(
            f"[REPLICATION_DELIVERY_SUCCESS] source={self.source_region} target={self.target_region} count={len(events)} applied={apply_result.get('applied_count')} cursor={self.last_replicated_seq}"
        )

        # Update lag tracker
        lag_tracker.update_metrics(
            source_highest_seq=highest_seq,
            last_replicated_seq=self.last_replicated_seq,
            oldest_unreplicated_ts=None if self.last_replicated_seq >= highest_seq else oldest_ts,
            injected_delay_sec=self.injected_delay_sec,
        )

        # Acknowledge source region
        try:
            event_ids = [ev["event_id"] for ev in events]
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(
                    f"{source_url}/internal/replication/ack",
                    json=event_ids,
                    headers=headers,
                )
        except Exception as e:
            logger.debug(f"Source ack skipped: {e}")

        return {
            "status": "SYNCED",
            "source_region": self.source_region,
            "target_region": self.target_region,
            "applied_count": apply_result.get("applied_count", 0),
            "skipped_duplicates": apply_result.get("skipped_duplicates", 0),
            "highest_sequence_id": self.last_replicated_seq,
            "lag_metrics": lag_tracker.to_dict(),
        }


engine = ReplicationEngine()

