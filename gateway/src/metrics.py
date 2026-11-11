import math
from collections import deque
from typing import Dict, Any, List


class GatewayMetricsTracker:
    def __init__(self, window_size: int = 1000):
        self.requests_total: int = 0
        self.client_errors_total: int = 0
        self.server_errors_total: int = 0
        self.latencies_ms: deque = deque(maxlen=window_size)

    def record_request(self, status_code: int, latency_ms: float):
        self.requests_total += 1
        self.latencies_ms.append(latency_ms)
        if 400 <= status_code < 500:
            self.client_errors_total += 1
        elif status_code >= 500:
            self.server_errors_total += 1

    def _percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_lats = sorted(self.latencies_ms)
        idx = int(math.ceil(p * len(sorted_lats))) - 1
        return round(sorted_lats[max(0, min(idx, len(sorted_lats) - 1))], 2)

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "requests_total": self.requests_total,
            "client_errors_total": self.client_errors_total,
            "server_errors_total": self.server_errors_total,
            "latency_p50_ms": self._percentile(0.50),
            "latency_p95_ms": self._percentile(0.95),
            "latency_p99_ms": self._percentile(0.99),
            "is_measured": True,
        }

    def to_prometheus(self, active_target: str, route_epoch: int) -> str:
        p95 = self._percentile(0.95)
        lines = [
            "# HELP failoverlab_gateway_requests_total Total HTTP requests handled by the ingress gateway",
            "# TYPE failoverlab_gateway_requests_total counter",
            f"failoverlab_gateway_requests_total {self.requests_total}",
            "",
            "# HELP failoverlab_gateway_client_errors_total Total 4xx responses emitted by gateway",
            "# TYPE failoverlab_gateway_client_errors_total counter",
            f"failoverlab_gateway_client_errors_total {self.client_errors_total}",
            "",
            "# HELP failoverlab_gateway_server_errors_total Total 5xx responses emitted by gateway",
            "# TYPE failoverlab_gateway_server_errors_total counter",
            f"failoverlab_gateway_server_errors_total {self.server_errors_total}",
            "",
            "# HELP failoverlab_gateway_latency_p95_ms Measured P95 request latency in milliseconds",
            "# TYPE failoverlab_gateway_latency_p95_ms gauge",
            f"failoverlab_gateway_latency_p95_ms {p95}",
            "",
            "# HELP failoverlab_gateway_active_route Current active target region in gateway table",
            "# TYPE failoverlab_gateway_active_route gauge",
            f'failoverlab_gateway_active_route{{target="region-a"}} {1 if active_target == "region-a" else 0}',
            f'failoverlab_gateway_active_route{{target="region-b"}} {1 if active_target == "region-b" else 0}',
            "",
            "# HELP failoverlab_gateway_route_epoch Monotonic route epoch in gateway",
            "# TYPE failoverlab_gateway_route_epoch gauge",
            f"failoverlab_gateway_route_epoch {route_epoch}",
            "",
        ]
        return "\n".join(lines) + "\n"


gateway_metrics = GatewayMetricsTracker()
