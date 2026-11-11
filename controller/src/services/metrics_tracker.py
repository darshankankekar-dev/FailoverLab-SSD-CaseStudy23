import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone


class ControllerMetricsTracker:
    """
    In-memory metrics tracker for truthful operational observability.
    Maintains counters for failover transitions, route updates, gate rejections,
    and wall-clock lab recovery timing.
    """
    def __init__(self):
        self.failover_attempts_total: int = 0
        self.failover_successes_total: int = 0
        self.failover_blocked_total: int = 0
        self.failover_blocked_by_gate: Dict[str, int] = {}

        self.route_update_attempts_total: int = 0
        self.route_update_successes_total: int = 0
        self.route_update_errors_total: int = 0

        self.outage_confirmed_monotonic: Optional[float] = None
        self.last_lab_recovery_seconds: Optional[float] = None
        self.lab_recovery_measurements_count: int = 0

    def record_outage_detected(self):
        """Marks the start of confirmed primary outage."""
        if self.outage_confirmed_monotonic is None:
            self.outage_confirmed_monotonic = time.monotonic()

    def record_failover_attempt(self):
        self.failover_attempts_total += 1
        if self.outage_confirmed_monotonic is None:
            self.outage_confirmed_monotonic = time.monotonic()

    def record_failover_success(self):
        self.failover_successes_total += 1
        if self.outage_confirmed_monotonic is not None:
            duration = time.monotonic() - self.outage_confirmed_monotonic
            self.last_lab_recovery_seconds = round(duration, 3)
            self.lab_recovery_measurements_count += 1
            self.outage_confirmed_monotonic = None

    def record_failover_blocked(self, gate_name: str):
        self.failover_blocked_total += 1
        self.failover_blocked_by_gate[gate_name] = self.failover_blocked_by_gate.get(gate_name, 0) + 1

    def record_route_update_attempt(self):
        self.route_update_attempts_total += 1

    def record_route_update_success(self):
        self.route_update_successes_total += 1

    def record_route_update_error(self):
        self.route_update_errors_total += 1

    def reset_outage_marker(self):
        self.outage_confirmed_monotonic = None

    def get_summary(self) -> Dict[str, Any]:
        return {
            "failover_attempts_total": self.failover_attempts_total,
            "failover_successes_total": self.failover_successes_total,
            "failover_blocked_total": self.failover_blocked_total,
            "failover_blocked_by_gate": self.failover_blocked_by_gate,
            "route_update_attempts_total": self.route_update_attempts_total,
            "route_update_successes_total": self.route_update_successes_total,
            "route_update_errors_total": self.route_update_errors_total,
            "last_lab_recovery_seconds": self.last_lab_recovery_seconds,
            "is_simulated_lab_metric": True,
            "metric_caveat": "Measured wall-clock duration in simulated lab test environment. Does not represent production enterprise RTO.",
        }


metrics_tracker = ControllerMetricsTracker()
