import math
from collections import deque
from typing import Dict, Any, List

from .telemetry import telemetry_collector, KNOWN_REGIONS


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
        rates = telemetry_collector.get_current_rates()
        snapshot = telemetry_collector.get_telemetry_snapshot()
        return {
            "requests_total": self.requests_total,
            "client_errors_total": self.client_errors_total,
            "server_errors_total": self.server_errors_total,
            "latency_p50_ms": self._percentile(0.50),
            "latency_p95_ms": self._percentile(0.95),
            "latency_p99_ms": self._percentile(0.99),
            "is_measured": True,
            # Extended application/API payload measurements
            "client_ingress_payload_bytes": telemetry_collector.cumulative_ingress_bytes,
            "client_egress_payload_bytes": telemetry_collector.cumulative_egress_bytes,
            "ingress_bytes_per_second": rates["ingress_bytes_per_second"],
            "egress_bytes_per_second": rates["egress_bytes_per_second"],
            "requests_per_second": rates["requests_per_second"],
            "rate_limited_429_total": telemetry_collector.rate_limited_429,
            "last_measurement_timestamp": telemetry_collector.last_measurement_timestamp,
            "telemetry_type": "application_payload_bytes",
            "traffic_telemetry": snapshot,
        }

    def to_prometheus(self, active_target: str, route_epoch: int) -> str:
        p95 = self._percentile(0.95)
        rates = telemetry_collector.get_current_rates()
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
            "# HELP failoverlab_gateway_rate_limited_total Total 429 rate limited requests",
            "# TYPE failoverlab_gateway_rate_limited_total counter",
            f"failoverlab_gateway_rate_limited_total {telemetry_collector.rate_limited_429}",
            "",
            "# HELP failoverlab_gateway_ingress_payload_bytes_total Total customer request payload bytes received",
            "# TYPE failoverlab_gateway_ingress_payload_bytes_total counter",
            f"failoverlab_gateway_ingress_payload_bytes_total {telemetry_collector.cumulative_ingress_bytes}",
            "",
            "# HELP failoverlab_gateway_egress_payload_bytes_total Total customer response payload bytes returned",
            "# TYPE failoverlab_gateway_egress_payload_bytes_total counter",
            f"failoverlab_gateway_egress_payload_bytes_total {telemetry_collector.cumulative_egress_bytes}",
            "",
            "# HELP failoverlab_gateway_ingress_bytes_per_second Current ingress payload bytes per second",
            "# TYPE failoverlab_gateway_ingress_bytes_per_second gauge",
            f"failoverlab_gateway_ingress_bytes_per_second {rates['ingress_bytes_per_second']}",
            "",
            "# HELP failoverlab_gateway_egress_bytes_per_second Current egress payload bytes per second",
            "# TYPE failoverlab_gateway_egress_bytes_per_second gauge",
            f"failoverlab_gateway_egress_bytes_per_second {rates['egress_bytes_per_second']}",
            "",
            "# HELP failoverlab_gateway_latency_p95_ms Measured P95 request latency in milliseconds",
            "# TYPE failoverlab_gateway_latency_p95_ms gauge",
            f"failoverlab_gateway_latency_p95_ms {p95}",
            "",
            "# HELP failoverlab_gateway_active_route Current active target region in gateway table",
            "# TYPE failoverlab_gateway_active_route gauge",
        ]

        for reg in KNOWN_REGIONS:
            val = 1 if active_target == reg else 0
            lines.append(f'failoverlab_gateway_active_route{{target="{reg}"}} {val}')

        lines.extend([
            "",
            "# HELP failoverlab_gateway_route_epoch Monotonic route epoch in gateway",
            "# TYPE failoverlab_gateway_route_epoch gauge",
            f"failoverlab_gateway_route_epoch {route_epoch}",
            "",
            "# HELP failoverlab_gateway_upstream_requests_total Total upstream requests forwarded to region",
            "# TYPE failoverlab_gateway_upstream_requests_total counter",
        ])

        for reg in KNOWN_REGIONS:
            reg_m = telemetry_collector.regions.get(reg)
            count = reg_m.requests_total if reg_m else 0
            lines.append(f'failoverlab_gateway_upstream_requests_total{{region="{reg}"}} {count}')

        lines.extend([
            "",
            "# HELP failoverlab_gateway_upstream_request_payload_bytes_total Upstream request payload bytes sent to region",
            "# TYPE failoverlab_gateway_upstream_request_payload_bytes_total counter",
        ])
        for reg in KNOWN_REGIONS:
            reg_m = telemetry_collector.regions.get(reg)
            bytes_val = reg_m.request_payload_bytes if reg_m else 0
            lines.append(f'failoverlab_gateway_upstream_request_payload_bytes_total{{region="{reg}"}} {bytes_val}')

        lines.extend([
            "",
            "# HELP failoverlab_gateway_upstream_response_payload_bytes_total Upstream response payload bytes received from region",
            "# TYPE failoverlab_gateway_upstream_response_payload_bytes_total counter",
        ])
        for reg in KNOWN_REGIONS:
            reg_m = telemetry_collector.regions.get(reg)
            bytes_val = reg_m.response_payload_bytes if reg_m else 0
            lines.append(f'failoverlab_gateway_upstream_response_payload_bytes_total{{region="{reg}"}} {bytes_val}')

        lines.append("")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        self.requests_total = 0
        self.client_errors_total = 0
        self.server_errors_total = 0
        self.latencies_ms.clear()


gateway_metrics = GatewayMetricsTracker()
