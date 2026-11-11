import pytest
from datetime import datetime, timezone, timedelta
from src.lag_tracker import LagTracker


def test_lag_tracker_nominal_synchronization():
    tracker = LagTracker()
    # Source has 10 events, last replicated is 10 -> 0 sequence lag
    tracker.update_metrics(
        source_highest_seq=10,
        last_replicated_seq=10,
        oldest_unreplicated_ts=None,
        injected_delay_sec=0.0,
    )
    assert tracker.sequence_lag == 0
    # Nominal lag should be nominal_transit_delay_sec (0.8s)
    assert tracker.time_lag_seconds == 0.8


def test_lag_tracker_with_unreplicated_delta():
    tracker = LagTracker()
    # 5 seconds ago an event was created at source
    five_sec_ago = datetime.now(timezone.utc) - timedelta(seconds=5.0)

    tracker.update_metrics(
        source_highest_seq=15,
        last_replicated_seq=10,
        oldest_unreplicated_ts=five_sec_ago,
        injected_delay_sec=0.0,
    )

    assert tracker.sequence_lag == 5
    assert tracker.time_lag_seconds >= 5.0


def test_lag_tracker_with_injected_delay():
    tracker = LagTracker()
    # Injected throttling delay of 8.4 seconds (Scenario F)
    tracker.update_metrics(
        source_highest_seq=10,
        last_replicated_seq=10,
        oldest_unreplicated_ts=None,
        injected_delay_sec=8.4,
    )

    assert tracker.time_lag_seconds == round(0.8 + 8.4, 2)
    assert tracker.to_dict()["injected_delay_sec"] == 8.4

