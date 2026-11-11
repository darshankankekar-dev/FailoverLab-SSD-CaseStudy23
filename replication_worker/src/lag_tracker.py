"""
Replication Lag Measurement Tracker
Defines and calculates observable replication lag metrics.

Definitions:
1. Time-Based Lag (T_lag):
   - When unreplicated events exist: (currentTime - oldestUnreplicatedEventTimestamp) + injectedDelaySec
   - When fully synchronized: nominalTransitDelaySec (e.g. 0.8s) + injectedDelaySec
2. Sequence / Counter Lag (S_lag):
   - max(0, sourceHighestSequenceId - lastReplicatedSequenceId)
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from .config import settings


class LagTracker:
    def __init__(self):
        self.source_highest_seq: int = 0
        self.last_replicated_seq: int = 0
        self.oldest_unreplicated_ts: Optional[datetime] = None
        self.injected_delay_sec: float = settings.injected_delay_sec
        self.last_sync_timestamp: Optional[datetime] = None

    def update_metrics(
        self,
        source_highest_seq: int,
        last_replicated_seq: int,
        oldest_unreplicated_ts: Optional[datetime] = None,
        injected_delay_sec: Optional[float] = None,
    ):
        self.source_highest_seq = source_highest_seq
        self.last_replicated_seq = last_replicated_seq
        self.oldest_unreplicated_ts = oldest_unreplicated_ts
        if injected_delay_sec is not None:
            self.injected_delay_sec = injected_delay_sec
        self.last_sync_timestamp = datetime.now(timezone.utc)

    @property
    def sequence_lag(self) -> int:
        """Sequence difference between source and standby."""
        return max(0, self.source_highest_seq - self.last_replicated_seq)

    @property
    def time_lag_seconds(self) -> float:
        """Measured lag in seconds."""
        base_delay = settings.nominal_transit_delay_sec + self.injected_delay_sec
        if self.sequence_lag > 0 and self.oldest_unreplicated_ts is not None:
            now = datetime.now(timezone.utc)
            ts = self.oldest_unreplicated_ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta = (now - ts).total_seconds()
            return round(max(base_delay, delta + self.injected_delay_sec), 2)
        return round(base_delay, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_highest_sequence_id": self.source_highest_seq,
            "last_replicated_sequence_id": self.last_replicated_seq,
            "sequence_lag_count": self.sequence_lag,
            "measured_lag_seconds": self.time_lag_seconds,
            "injected_delay_sec": self.injected_delay_sec,
            "nominal_transit_delay_sec": settings.nominal_transit_delay_sec,
            "last_sync_timestamp": self.last_sync_timestamp.isoformat() if self.last_sync_timestamp else None,
        }


lag_tracker = LagTracker()

