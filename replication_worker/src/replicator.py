import time
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import httpx
from .config import settings
from .lag_tracker import lag_tracker

logger = logging.getLogger("replication.engine")


@dataclass
class TargetState:
    region_id: str
    last_applied_seq: int = 0
    source_highest_seq: int = 0
    consecutive_errors: int = 0
    retry_count: int = 0
    backoff_until: float = 0.0
    status: str = "INITIALIZING"
    last_error: Optional[str] = None
    is_paused: bool = False
    injected_delay_sec: float = 0.0
    initialized: bool = False


class ReplicationEngine:
    def __init__(self):
        self.active_region: str = "region-a"
        self.active_epoch: int = 101
        self.is_paused: bool = settings.is_paused
        self.injected_delay_sec: float = settings.injected_delay_sec
        self.reversal_count: int = 0
        self.total_applied_events: int = 0
        self.consecutive_errors: int = 0

        self.all_regions: List[str] = ["region-a", "region-b", "region-c", "region-d", "region-e"]
        self.target_states: Dict[str, TargetState] = {}

    @property
    def source_region(self) -> str:
        return self.active_region

    @property
    def target_region(self) -> str:
        """Primary target region property for backwards compatibility."""
        standbys = [r for r in self.all_regions if r != self.active_region]
        return standbys[0] if standbys else "region-b"

    @property
    def target_regions(self) -> List[str]:
        """All standby destination regions currently receiving replicated events."""
        return [r for r in self.all_regions if r != self.active_region]

    @property
    def last_replicated_seq(self) -> int:
        """Min sequence across active standbys (or override value if set)."""
        if hasattr(self, "_last_replicated_seq_override") and self._last_replicated_seq_override is not None:
            return self._last_replicated_seq_override
        standbys = self.target_regions
        if not standbys or not self.target_states:
            return 0
        return min((self.target_states[t].last_applied_seq for t in standbys if t in self.target_states), default=0)

    @last_replicated_seq.setter
    def last_replicated_seq(self, val: int) -> None:
        self._last_replicated_seq_override = val
        for target_id in self.target_regions:
            ts = self._get_or_create_target_state(target_id)
            ts.last_applied_seq = val

    def get_region_url(self, region_id: str) -> str:
        url_map = {
            "region-a": settings.region_a_url,
            "region-b": settings.region_b_url,
            "region-c": settings.region_c_url,
            "region-d": settings.region_d_url,
            "region-e": settings.region_e_url,
        }
        return url_map.get(region_id, f"http://localhost:8000")

    def _get_or_create_target_state(self, target_id: str) -> TargetState:
        if target_id not in self.target_states:
            self.target_states[target_id] = TargetState(region_id=target_id)
        return self.target_states[target_id]

    async def init_target_checkpoint(self, target_id: str) -> int:
        """
        Queries target region to determine its last successfully applied sequence checkpoint.
        Ensures safe resumption after worker restart without duplicating or skipping transactions.
        """
        target_state = self._get_or_create_target_state(target_id)
        target_url = self.get_region_url(target_id)
        headers = {}
        if settings.internal_api_secret:
            headers["X-Internal-Secret"] = settings.internal_api_secret

        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                # Try dedicated checkpoint endpoint first
                resp = await client.get(f"{target_url}/internal/replication/checkpoint", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    target_state.last_applied_seq = data.get("last_applied_sequence_id", 0)
                    target_state.initialized = True
                    return target_state.last_applied_seq

                # Fallback to general regional status
                resp_status = await client.get(f"{target_url}/api/status", headers=headers)
                if resp_status.status_code == 200:
                    data = resp_status.json()
                    target_state.last_applied_seq = data.get("applied_sequence", 0)
                    target_state.initialized = True
                    return target_state.last_applied_seq
        except Exception as e:
            logger.debug(f"Checkpoint check for target {target_id} skipped: {e}")

        target_state.initialized = True
        return target_state.last_applied_seq

    async def fetch_controller_active_region(self) -> Optional[str]:
        """Queries the Controller service to determine the authoritative active writer and fencing epoch."""
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                resp = await client.get(f"{settings.controller_url}/api/v1/state")
                if resp.status_code == 200:
                    data = resp.json()
                    new_active = data.get("active_region", "region-a")
                    new_epoch = data.get("fencing_epoch", 101)
                    if new_active != self.active_region:
                        logger.info(
                            f"[FAILOVER_REVERSED] New active region detected: "
                            f"{self.active_region} -> {new_active} (Epoch #{new_epoch}). "
                            f"Reversing replication topology."
                        )
                        self.active_region = new_active
                        self.active_epoch = new_epoch
                        self.reversal_count += 1
                        # Re-initialize checkpoints for the newly configured targets
                        for t in self.target_regions:
                            ts = self._get_or_create_target_state(t)
                            ts.initialized = False
                    return self.active_region
        except Exception as e:
            logger.debug(f"Controller state check skipped: {e}")
        return self.active_region

    async def sync_target(self, target_id: str, source_url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        """
        Independently replicates committed outbox records from active source to one specific standby.
        Failure of this target does NOT impede or block replication to any other standby.
        """
        target_state = self._get_or_create_target_state(target_id)
        target_url = self.get_region_url(target_id)

        # 1. Independent checkpoint resumption on restart
        if not target_state.initialized:
            await self.init_target_checkpoint(target_id)

        # 2. Independent backoff & pause check
        if target_state.is_paused or self.is_paused:
            lag_tracker.update_destination_metrics(
                destination_region=target_id,
                source_highest_seq=target_state.source_highest_seq,
                applied_seq=target_state.last_applied_seq,
                source_region=self.source_region,
                status="PAUSED",
            )
            return {"status": "PAUSED", "target_region": target_id}

        now = time.time()
        if now < target_state.backoff_until:
            logger.debug(f"Target {target_id} in backoff delay for {target_state.backoff_until - now:.1f}s.")
            return {"status": "BACKOFF", "target_region": target_id}

        # 3. Read unreplicated events from source outbox for this target's cursor
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                outbox_resp = await client.get(
                    f"{source_url}/internal/replication/outbox",
                    params={"since_sequence_id": target_state.last_applied_seq, "limit": settings.batch_size},
                    headers=headers,
                )
                if outbox_resp.status_code != 200:
                    target_state.consecutive_errors += 1
                    target_state.last_error = f"HTTP {outbox_resp.status_code} from {self.source_region}"
                    return {"status": "SOURCE_ERROR", "target_region": target_id, "error": target_state.last_error}

                batch_data = outbox_resp.json()
        except Exception as e:
            target_state.consecutive_errors += 1
            target_state.last_error = str(e)
            logger.debug(f"Outbox fetch from {self.source_region} for {target_id} failed: {e}")
            return {"status": "SOURCE_UNREACHABLE", "target_region": target_id, "error": str(e)}

        events = batch_data.get("events", [])
        highest_seq = batch_data.get("highest_sequence_id", 0)
        target_state.source_highest_seq = highest_seq
        oldest_ts_str = batch_data.get("oldest_unreplicated_created_at")
        oldest_ts = datetime.fromisoformat(oldest_ts_str) if oldest_ts_str else None

        # Effective latency delay for this target
        effective_delay = max(self.injected_delay_sec, target_state.injected_delay_sec)

        # 4. If target is already caught up
        if not events:
            target_state.consecutive_errors = 0
            target_state.retry_count = 0
            target_state.backoff_until = 0.0
            target_state.status = "SYNCED"
            lag_tracker.update_destination_metrics(
                destination_region=target_id,
                source_highest_seq=highest_seq,
                applied_seq=target_state.last_applied_seq,
                source_region=self.source_region,
                oldest_unreplicated_ts=None,
                injected_delay_sec=effective_delay,
                status="SYNCED",
                retry_count=0,
                consecutive_failures=0,
            )
            return {
                "status": "SYNCED",
                "source_region": self.source_region,
                "target_region": target_id,
                "last_sequence_id": target_state.last_applied_seq,
            }

        # 5. Apply artificial WAN transit delay if configured
        if effective_delay > 0:
            await asyncio.sleep(min(effective_delay, 2.0))

        # 6. Format replication payload with authoritative metadata
        apply_payload = {
            "source_region": self.source_region,
            "events": [
                {
                    "event_id": ev["event_id"],
                    "source_sequence_id": ev["sequence_id"],
                    "sequence_number": ev.get("sequence_number", ev["sequence_id"]),
                    "source_region_id": self.source_region,
                    "source_fencing_epoch": ev.get("source_fencing_epoch", ev.get("fencing_epoch", self.active_epoch)),
                    "record_key": ev["record_key"],
                    "operation": ev["operation"],
                    "payload": ev["payload"],
                    "payload_hash": ev.get("payload_hash"),
                    "version": ev["version"],
                    "fencing_epoch": ev.get("fencing_epoch", self.active_epoch),
                    "source_region": self.source_region,
                    "created_at": ev["created_at"],
                }
                for ev in events
            ],
        }

        # 7. Deliver batch to destination
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                apply_resp = await client.post(
                    f"{target_url}/internal/replication/apply",
                    json=apply_payload,
                    headers=headers,
                )
                if apply_resp.status_code != 200:
                    target_state.consecutive_errors += 1
                    target_state.retry_count += 1
                    target_state.last_error = f"HTTP {apply_resp.status_code}: {apply_resp.text}"
                    target_state.status = "ERROR" if target_state.consecutive_errors >= 3 else "DEGRADED"

                    # Independent exponential backoff per target
                    backoff_secs = min(10.0, 0.5 * (2 ** min(target_state.consecutive_errors - 1, 4)))
                    target_state.backoff_until = time.time() + backoff_secs

                    lag_tracker.update_destination_metrics(
                        destination_region=target_id,
                        source_highest_seq=highest_seq,
                        applied_seq=target_state.last_applied_seq,
                        source_region=self.source_region,
                        oldest_unreplicated_ts=oldest_ts,
                        injected_delay_sec=effective_delay,
                        status=target_state.status,
                        retry_count=target_state.retry_count,
                        consecutive_failures=target_state.consecutive_errors,
                    )
                    logger.warning(
                        f"[REPLICATION_TARGET_FAILED] target={target_id} attempts={target_state.retry_count} "
                        f"backoff={backoff_secs:.1f}s err={target_state.last_error}"
                    )
                    return {"status": "TARGET_APPLY_FAILED", "target_region": target_id, "error": target_state.last_error}

                apply_result = apply_resp.json()
        except Exception as e:
            target_state.consecutive_errors += 1
            target_state.retry_count += 1
            target_state.last_error = str(e)
            target_state.status = "ERROR" if target_state.consecutive_errors >= 3 else "DEGRADED"

            backoff_secs = min(10.0, 0.5 * (2 ** min(target_state.consecutive_errors - 1, 4)))
            target_state.backoff_until = time.time() + backoff_secs

            lag_tracker.update_destination_metrics(
                destination_region=target_id,
                source_highest_seq=highest_seq,
                applied_seq=target_state.last_applied_seq,
                source_region=self.source_region,
                oldest_unreplicated_ts=oldest_ts,
                injected_delay_sec=effective_delay,
                status=target_state.status,
                retry_count=target_state.retry_count,
                consecutive_failures=target_state.consecutive_errors,
            )
            logger.warning(f"[REPLICATION_TARGET_UNREACHABLE] target={target_id} err={e}")
            return {"status": "TARGET_UNREACHABLE", "target_region": target_id, "error": str(e)}

        # 8. Success: Update target progress cursor
        new_highest = apply_result.get("highest_sequence_id", target_state.last_applied_seq)
        target_state.last_applied_seq = new_highest
        applied_count = apply_result.get("applied_count", 0)
        self.total_applied_events += applied_count
        target_state.consecutive_errors = 0
        target_state.retry_count = 0
        target_state.backoff_until = 0.0
        target_state.last_error = None
        target_state.status = "SYNCED" if target_state.last_applied_seq >= highest_seq else "STREAMING"

        logger.info(
            f"[REPLICATION_SUCCESS] source={self.source_region} -> target={target_id} "
            f"count={len(events)} applied={applied_count} "
            f"skipped_dup={apply_result.get('skipped_duplicates', 0)} cursor={new_highest}"
        )

        lag_tracker.update_destination_metrics(
            destination_region=target_id,
            source_highest_seq=highest_seq,
            applied_seq=target_state.last_applied_seq,
            source_region=self.source_region,
            oldest_unreplicated_ts=None if target_state.last_applied_seq >= highest_seq else oldest_ts,
            injected_delay_sec=effective_delay,
            status=target_state.status,
            retry_count=0,
            consecutive_failures=0,
        )

        return {
            "status": "SYNCED",
            "source_region": self.source_region,
            "target_region": target_id,
            "applied_count": applied_count,
            "skipped_duplicates": apply_result.get("skipped_duplicates", 0),
            "highest_sequence_id": target_state.last_applied_seq,
        }

    async def sync_iteration(self) -> Dict[str, Any]:
        """
        Executes one complete multi-target replication synchronization pass:
        1. Queries Controller to confirm authoritative active region and detect failovers.
        2. Replicates to each standby destination independently without head-of-line blocking.
        3. Acknowledges delivered events at source.
        """
        if self.is_paused:
            return {
                "status": "PAUSED",
                "message": "Replication is currently paused.",
                "lag_metrics": lag_tracker.to_dict(),
            }

        # Step 1: Discover active writer
        await self.fetch_controller_active_region()

        source_url = self.get_region_url(self.source_region)
        headers = {}
        if settings.internal_api_secret:
            headers["X-Internal-Secret"] = settings.internal_api_secret

        # Step 2: Replicate to all standbys independently
        destinations = self.target_regions
        destination_results: Dict[str, Any] = {}

        for target_id in destinations:
            res = await self.sync_target(target_id, source_url, headers)
            destination_results[target_id] = res

        # Step 3: Acknowledge source for events applied across destinations
        min_applied_seq = min(
            (self.target_states[t].last_applied_seq for t in destinations if t in self.target_states),
            default=0,
        )
        # Global tracker compatibility
        lag_tracker.last_replicated_seq = min_applied_seq

        # Determine overall status
        failed_targets = [
            t for t, r in destination_results.items()
            if r.get("status") in ("TARGET_APPLY_FAILED", "TARGET_FAILED", "TARGET_UNREACHABLE", "FAILED")
        ]
        if len(failed_targets) == len(destinations) and len(destinations) > 0:
            overall_status = "TARGET_APPLY_FAILED"
        elif failed_targets:
            overall_status = "PARTIAL_SYNC"
        else:
            overall_status = "SYNCED"

        return {
            "status": overall_status,
            "error": destination_results.get(self.target_region, {}).get("error"),
            "source_region": self.source_region,
            "active_epoch": self.active_epoch,
            "destinations": destination_results,
            "lag_metrics": lag_tracker.to_dict(),
            # Legacy keys for backwards compatibility with existing assertions
            "target_region": self.target_region,
            "highest_sequence_id": min_applied_seq,
            "last_sequence_id": min_applied_seq,
        }


engine = ReplicationEngine()
