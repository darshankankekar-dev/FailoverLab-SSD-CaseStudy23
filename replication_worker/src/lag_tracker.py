"""
Replication Lag Measurement Tracker
Defines and calculates observable replication lag metrics per standby destination.

Per-destination observable metrics:
1. Time-Based Lag (T_lag):
   - When unreplicated events exist: (currentTime - oldestUnreplicatedEventTimestamp) + injectedDelaySec
   - When fully synchronized: nominalTransitDelaySec (0.8s) + injectedDelaySec
2. Sequence / Counter Lag (S_lag):
   - max(0, sourceHighestSequenceId - lastAppliedSequenceId)
3. Clear attribution of simulated WAN latency vs measured processing lag.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from .config import settings


@dataclass
class DestinationLagInfo:
    destination_region: str
    source_region: str = "region-a"
    source_sequence: int = 0
    applied_sequence: int = 0
    sequence_lag: int = 0
    time_lag_seconds: float = 0.8
    oldest_unreplicated_ts: Optional[datetime] = None
    injected_delay_sec: float = 0.0
    last_sync_timestamp: Optional[datetime] = None
    status: str = "SYNCED"
    retry_count: int = 0
    consecutive_failures: int = 0
    is_simulated_lag: bool = False

    def update(
        self,
        source_highest_seq: int,
        applied_seq: int,
        source_region: str = "region-a",
        oldest_unreplicated_ts: Optional[datetime] = None,
        injected_delay_sec: Optional[float] = None,
        status: Optional[str] = None,
        retry_count: Optional[int] = None,
        consecutive_failures: Optional[int] = None,
    ) -> None:
        self.source_region = source_region
        self.source_sequence = source_highest_seq
        self.applied_sequence = applied_seq
        self.sequence_lag = max(0, source_highest_seq - applied_seq)
        self.oldest_unreplicated_ts = oldest_unreplicated_ts
        if injected_delay_sec is not None:
            self.injected_delay_sec = injected_delay_sec
        self.is_simulated_lag = self.injected_delay_sec > 0.0

        if status is not None:
            self.status = status
        elif self.sequence_lag == 0:
            self.status = "SYNCED"
        else:
            self.status = "STREAMING"

        if retry_count is not None:
            self.retry_count = retry_count
        if consecutive_failures is not None:
            self.consecutive_failures = consecutive_failures

        # Compute time lag
        base_delay = settings.nominal_transit_delay_sec + self.injected_delay_sec
        if self.sequence_lag > 0 and self.oldest_unreplicated_ts is not None:
            now = datetime.now(timezone.utc)
            ts = self.oldest_unreplicated_ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta = (now - ts).total_seconds()
            self.time_lag_seconds = round(max(base_delay, delta + self.injected_delay_sec), 2)
        else:
            self.time_lag_seconds = round(base_delay, 2)

        self.last_sync_timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_region": self.source_region,
            "destination_region": self.destination_region,
            "source_sequence": self.source_sequence,
            "applied_sequence": self.applied_sequence,
            "sequence_lag": self.sequence_lag,
            "time_lag_seconds": self.time_lag_seconds,
            "status": self.status,
            "retry_count": self.retry_count,
            "consecutive_failures": self.consecutive_failures,
            "is_simulated_lag": self.is_simulated_lag,
            "injected_delay_sec": self.injected_delay_sec,
            "last_replication_time": self.last_sync_timestamp.isoformat() if self.last_sync_timestamp else None,
        }


class LagTracker:
    def __init__(self):
        self.destinations: Dict[str, DestinationLagInfo] = {}
        self.source_highest_seq: int = 0
        self.last_replicated_seq: int = 0
        self.oldest_unreplicated_ts: Optional[datetime] = None
        self.injected_delay_sec: float = settings.injected_delay_sec
        self.last_sync_timestamp: Optional[datetime] = None

    def get_or_create_destination(self, destination: str, source: str = "region-a") -> DestinationLagInfo:
        if destination not in self.destinations:
            self.destinations[destination] = DestinationLagInfo(
                destination_region=destination,
                source_region=source,
                injected_delay_sec=self.injected_delay_sec,
            )
        return self.destinations[destination]

    def update_destination_metrics(
        self,
        destination_region: str,
        source_highest_seq: int,
        applied_seq: int,
        source_region: str = "region-a",
        oldest_unreplicated_ts: Optional[datetime] = None,
        injected_delay_sec: Optional[float] = None,
        status: Optional[str] = None,
        retry_count: Optional[int] = None,
        consecutive_failures: Optional[int] = None,
    ) -> None:
        dest = self.get_or_create_destination(destination_region, source=source_region)
        dest.update(
            source_highest_seq=source_highest_seq,
            applied_seq=applied_seq,
            source_region=source_region,
            oldest_unreplicated_ts=oldest_unreplicated_ts,
            injected_delay_sec=injected_delay_sec if injected_delay_sec is not None else self.injected_delay_sec,
            status=status,
            retry_count=retry_count,
            consecutive_failures=consecutive_failures,
        )
        self.source_highest_seq = max(self.source_highest_seq, source_highest_seq)
        self.last_replicated_seq = max(self.last_replicated_seq, applied_seq)
        self.last_sync_timestamp = datetime.now(timezone.utc)

    # Legacy method compatibility
    def update_metrics(
        self,
        source_highest_seq: int,
        last_replicated_seq: int,
        oldest_unreplicated_ts: Optional[datetime] = None,
        injected_delay_sec: Optional[float] = None,
        primary_target: str = "region-b",
    ):
        self.source_highest_seq = source_highest_seq
        self.last_replicated_seq = last_replicated_seq
        self.oldest_unreplicated_ts = oldest_unreplicated_ts
        if injected_delay_sec is not None:
            self.injected_delay_sec = injected_delay_sec
        self.last_sync_timestamp = datetime.now(timezone.utc)
        self.update_destination_metrics(
            destination_region=primary_target,
            source_highest_seq=source_highest_seq,
            applied_seq=last_replicated_seq,
            oldest_unreplicated_ts=oldest_unreplicated_ts,
            injected_delay_sec=self.injected_delay_sec,
        )

    @property
    def sequence_lag(self) -> int:
        """Max sequence lag across all tracked standby destinations."""
        if not self.destinations:
            return max(0, self.source_highest_seq - self.last_replicated_seq)
        return max((d.sequence_lag for d in self.destinations.values()), default=0)

    @property
    def time_lag_seconds(self) -> float:
        """Max time-based lag in seconds across all tracked standby destinations."""
        if not self.destinations:
            base_delay = settings.nominal_transit_delay_sec + self.injected_delay_sec
            if self.sequence_lag > 0 and self.oldest_unreplicated_ts is not None:
                now = datetime.now(timezone.utc)
                ts = self.oldest_unreplicated_ts
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                delta = (now - ts).total_seconds()
                return round(max(base_delay, delta + self.injected_delay_sec), 2)
            return round(base_delay, 2)
        return max((d.time_lag_seconds for d in self.destinations.values()), default=round(settings.nominal_transit_delay_sec, 2))

    def to_dict(self) -> Dict[str, Any]:
        dest_dict = {k: v.to_dict() for k, v in self.destinations.items()}
        max_time_lag = max((d["time_lag_seconds"] for d in dest_dict.values()), default=settings.nominal_transit_delay_sec)
        max_seq_lag = max((d["sequence_lag"] for d in dest_dict.values()), default=self.sequence_lag)

        return {
            "source_highest_sequence_id": self.source_highest_seq,
            "last_replicated_sequence_id": self.last_replicated_seq,
            "sequence_lag_count": max_seq_lag,
            "measured_lag_seconds": max_time_lag,
            "injected_delay_sec": self.injected_delay_sec,
            "nominal_transit_delay_sec": settings.nominal_transit_delay_sec,
            "last_sync_timestamp": self.last_sync_timestamp.isoformat() if self.last_sync_timestamp else None,
            "destinations": dest_dict,
            "max_lag_seconds": max_time_lag,
            "max_sequence_lag": max_seq_lag,
        }


lag_tracker = LagTracker()
