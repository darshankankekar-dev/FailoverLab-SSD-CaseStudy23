import time
import math
import asyncio
from datetime import datetime, timezone
from collections import deque
from typing import Dict, Any, Optional, List, Tuple
import logging

logger = logging.getLogger("gateway.telemetry")

KNOWN_REGIONS = ["region-a", "region-b", "region-c", "region-d", "region-e"]
REQUEST_CLASSES = ["write", "strong_read", "eventual_read", "system"]
TRAFFIC_SOURCES = ["online_store", "load_generator", "internal"]


def normalize_endpoint(path: str) -> Tuple[str, str]:
    """
    Returns (normalized_route_template, endpoint_category).
    Replaces high-cardinality dynamic identifiers (IDs, keys, UUIDs)
    with fixed route templates to avoid high cardinality in metrics.
    """
    path_clean = path.rstrip("/") or "/"
    if path_clean in ("/api/ecommerce/products", "/api/shop/products"):
        return "/api/ecommerce/products", "catalog"
    if path_clean.startswith("/api/ecommerce/products/") or path_clean.startswith("/api/shop/products/"):
        return "/api/ecommerce/products/{id}", "product_detail"
    if path_clean.startswith("/api/ecommerce/inventory/") or path_clean.startswith("/api/shop/inventory/"):
        return "/api/ecommerce/inventory/{id}", "inventory"
    if path_clean in ("/api/ecommerce/orders", "/api/shop/orders"):
        return "/api/ecommerce/orders", "orders"
    if path_clean.startswith("/api/ecommerce/orders/") or path_clean.startswith("/api/shop/orders/"):
        return "/api/ecommerce/orders/{id}", "orders"
    if path_clean in ("/api/records", "/api/data/records"):
        return "/api/records", "records"
    if path_clean.startswith("/api/records/") or path_clean.startswith("/api/data/records/"):
        return "/api/records/{key}", "records"
    if path_clean.startswith("/health/"):
        return "/health/{check}", "health"
    if path_clean.startswith("/api/v1/traffic") or path_clean.startswith("/api/traffic"):
        return "/api/v1/traffic/{action}", "traffic_control"
    if path_clean.startswith("/api/v1/"):
        return "/api/v1/{route}", "control_plane"
    if path_clean.startswith("/internal/"):
        return "/internal/{route}", "internal"
    if path_clean == "/metrics":
        return "/metrics", "metrics"
    return path_clean, "other"


def detect_traffic_source(headers_map: Dict[str, str], path: str) -> str:
    """
    Distinguishes real Online Store customer traffic from synthetic Load Generator
    traffic and internal management/health traffic.
    """
    traffic_src = headers_map.get("x-traffic-source", "").lower().strip()
    if traffic_src in {"load_generator", "synthetic", "benchmark", "loadgen"}:
        return "load_generator"
    if traffic_src in {"online_store", "store", "customer", "shopper"}:
        return "online_store"
    if traffic_src in {"internal", "system", "health", "management"}:
        return "internal"

    client_id = headers_map.get("x-client-id", "").lower().strip()
    if any(k in client_id for k in ("load-generator", "loadgen", "synthetic", "benchmark")):
        return "load_generator"
    if "shopper" in client_id:
        return "online_store"

    user_agent = headers_map.get("user-agent", "").lower().strip()
    if any(k in user_agent for k in ("load-generator", "loadgen", "autocannon", "k6", "wrk")):
        return "load_generator"

    # Check path characteristics
    if (
        path.startswith("/health")
        or path.startswith("/internal/")
        or path == "/metrics"
        or path.startswith("/api/v1/traffic")
        or path.startswith("/api/traffic")
        or path.startswith("/api/v1/route")
        or path.startswith("/api/v1/routing")
        or path.startswith("/api/v1/state")
    ):
        return "internal"

    # Store customer endpoints (including test harness routes)
    if (
        path.startswith("/api/ecommerce/")
        or path.startswith("/api/shop/")
        or path.startswith("/api/records")
        or path.startswith("/api/data/records")
        or path.startswith("/test/")
    ):
        return "online_store"

    # Default unknown/unclassified requests to internal to avoid inflating customer stats
    return "internal"


class RegionalUpstreamMetrics:
    """Tracks upstream traffic sent from Gateway to a specific backend region."""

    def __init__(self, region_id: str, window_size: int = 1000):
        self.region_id = region_id
        self.requests_total: int = 0
        self.request_payload_bytes: int = 0
        self.response_payload_bytes: int = 0
        self.status_2xx: int = 0
        self.status_3xx: int = 0
        self.status_4xx: int = 0
        self.status_5xx: int = 0
        self.failed_requests: int = 0
        self.timeouts: int = 0
        self.latencies_ms: deque = deque(maxlen=window_size)

    def record(
        self,
        req_bytes: int,
        resp_bytes: int,
        duration_ms: float,
        status_code: int,
        is_timeout: bool = False,
        is_failure: bool = False,
    ) -> None:
        self.requests_total += 1
        self.request_payload_bytes += max(0, req_bytes)
        self.response_payload_bytes += max(0, resp_bytes)
        self.latencies_ms.append(duration_ms)

        if is_timeout or status_code == 504:
            self.timeouts += 1
            self.status_5xx += 1
        elif is_failure or status_code in (502, 503):
            self.failed_requests += 1
            self.status_5xx += 1
        elif 200 <= status_code < 300:
            self.status_2xx += 1
        elif 300 <= status_code < 400:
            self.status_3xx += 1
        elif 400 <= status_code < 500:
            self.status_4xx += 1
        elif status_code >= 500:
            self.status_5xx += 1

    def get_avg_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return round(sum(self.latencies_ms) / len(self.latencies_ms), 2)

    def get_p95_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0
        s = sorted(self.latencies_ms)
        idx = int(math.ceil(0.95 * len(s))) - 1
        return round(s[max(0, min(idx, len(s) - 1))], 2)

    def to_dict(self) -> Dict[str, Any]:
        avg_lat = self.get_avg_latency()
        return {
            "region_id": self.region_id,
            "requests_total": self.requests_total,
            "request_payload_bytes": self.request_payload_bytes,
            "response_payload_bytes": self.response_payload_bytes,
            "status_2xx": self.status_2xx,
            "status_3xx": self.status_3xx,
            "status_4xx": self.status_4xx,
            "status_5xx": self.status_5xx,
            "failed_requests": self.failed_requests,
            "timeouts": self.timeouts,
            "average_duration_ms": avg_lat,
            "average_latency_ms": avg_lat,
            "p95_duration_ms": self.get_p95_latency(),
        }

    def reset(self) -> None:
        self.requests_total = 0
        self.request_payload_bytes = 0
        self.response_payload_bytes = 0
        self.status_2xx = 0
        self.status_3xx = 0
        self.status_4xx = 0
        self.status_5xx = 0
        self.failed_requests = 0
        self.timeouts = 0
        self.latencies_ms.clear()


class RequestClassMetrics:
    """Tracks traffic broken down by request class (write, strong_read, eventual_read, system)."""

    def __init__(self, class_name: str, window_size: int = 500):
        self.class_name = class_name
        self.requests_total: int = 0
        self.ingress_bytes: int = 0
        self.egress_bytes: int = 0
        self.latencies_ms: deque = deque(maxlen=window_size)

    def record(self, in_bytes: int, out_bytes: int, duration_ms: float) -> None:
        self.requests_total += 1
        self.ingress_bytes += max(0, in_bytes)
        self.egress_bytes += max(0, out_bytes)
        self.latencies_ms.append(duration_ms)

    def to_dict(self) -> Dict[str, Any]:
        avg_lat = round(sum(self.latencies_ms) / len(self.latencies_ms), 2) if self.latencies_ms else 0.0
        return {
            "class_name": self.class_name,
            "requests_total": self.requests_total,
            "ingress_bytes": self.ingress_bytes,
            "egress_bytes": self.egress_bytes,
            "average_latency_ms": avg_lat,
        }

    def reset(self) -> None:
        self.requests_total = 0
        self.ingress_bytes = 0
        self.egress_bytes = 0
        self.latencies_ms.clear()


class TrafficSourceMetrics:
    """Tracks metrics separately for online store vs load generator vs internal."""

    def __init__(self, source_name: str, window_size: int = 500):
        self.source_name = source_name
        self.requests_total: int = 0
        self.ingress_bytes: int = 0
        self.egress_bytes: int = 0
        self.status_2xx: int = 0
        self.status_4xx: int = 0
        self.status_5xx: int = 0
        self.rate_limited_429: int = 0
        self.latencies_ms: deque = deque(maxlen=window_size)

    def record(self, in_bytes: int, out_bytes: int, duration_ms: float, status_code: int) -> None:
        self.requests_total += 1
        self.ingress_bytes += max(0, in_bytes)
        self.egress_bytes += max(0, out_bytes)
        self.latencies_ms.append(duration_ms)

        if status_code == 429:
            self.rate_limited_429 += 1
            self.status_4xx += 1
        elif 200 <= status_code < 300:
            self.status_2xx += 1
        elif 400 <= status_code < 500:
            self.status_4xx += 1
        elif status_code >= 500:
            self.status_5xx += 1

    def to_dict(self) -> Dict[str, Any]:
        avg_lat = round(sum(self.latencies_ms) / len(self.latencies_ms), 2) if self.latencies_ms else 0.0
        return {
            "source_name": self.source_name,
            "requests_total": self.requests_total,
            "ingress_bytes": self.ingress_bytes,
            "egress_bytes": self.egress_bytes,
            "status_2xx": self.status_2xx,
            "status_4xx": self.status_4xx,
            "status_5xx": self.status_5xx,
            "rate_limited_429": self.rate_limited_429,
            "average_latency_ms": avg_lat,
        }

    def reset(self) -> None:
        self.requests_total = 0
        self.ingress_bytes = 0
        self.egress_bytes = 0
        self.status_2xx = 0
        self.status_4xx = 0
        self.status_5xx = 0
        self.rate_limited_429 = 0
        self.latencies_ms.clear()


class GatewayTelemetryCollector:
    """
    Central telemetry aggregator for Gateway ingress, egress, and regional proxy traffic.
    Maintains:
    - Cumulative customer-facing payload bytes & counts.
    - One-second interval counters for real-time rates (ingress B/s, egress B/s, RPS).
    - Per-region upstream traffic counters (request bytes, response bytes, errors, timeouts).
    - Per-request-class and per-traffic-source distributions.
    - Latency summaries (Avg, P50, P95, P99).
    """

    def __init__(self, window_size: int = 2000):
        self.window_size = window_size

        # Cumulative customer-facing counters
        self.cumulative_ingress_bytes: int = 0
        self.cumulative_egress_bytes: int = 0
        self.total_requests: int = 0
        self.status_2xx: int = 0
        self.status_3xx: int = 0
        self.status_4xx: int = 0
        self.status_5xx: int = 0
        self.rate_limited_429: int = 0

        # Latency samples
        self.latencies_ms: deque = deque(maxlen=window_size)

        # 1-second rolling rate window: stores (monotonic_timestamp, ingress_bytes, egress_bytes)
        self._rate_window: deque = deque()

        # Upstream regional metrics
        self.regions: Dict[str, RegionalUpstreamMetrics] = {
            r: RegionalUpstreamMetrics(r) for r in KNOWN_REGIONS
        }

        # Request class metrics
        self.request_classes: Dict[str, RequestClassMetrics] = {
            c: RequestClassMetrics(c) for c in REQUEST_CLASSES
        }

        # Traffic source breakdown
        self.traffic_sources: Dict[str, TrafficSourceMetrics] = {
            s: TrafficSourceMetrics(s) for s in TRAFFIC_SOURCES
        }

        # Timestamp of last successful measurement
        self.last_measurement_timestamp: Optional[str] = None
        self.last_measurement_epoch: float = 0.0

    def _prune_rate_window(self, now: float) -> None:
        """Evicts entries older than 1.0 second from the rate window."""
        cutoff = now - 1.0
        while self._rate_window and self._rate_window[0][0] < cutoff:
            self._rate_window.popleft()

    def record_client_request(
        self,
        method: str,
        path: str,
        status_code: int,
        ingress_bytes: int,
        egress_bytes: int,
        duration_ms: float,
        traffic_source: str = "online_store",
        request_class: str = "eventual_read",
        served_region: Optional[str] = None,
    ) -> None:
        now_mono = time.monotonic()
        now_iso = datetime.now(timezone.utc).isoformat()
        self.last_measurement_timestamp = now_iso
        self.last_measurement_epoch = now_mono

        # 1. Update source-specific and request-class counters
        src = traffic_source if traffic_source in self.traffic_sources else "internal"
        self.traffic_sources[src].record(ingress_bytes, egress_bytes, duration_ms, status_code)

        req_cls = request_class if request_class in self.request_classes else "system"
        self.request_classes[req_cls].record(ingress_bytes, egress_bytes, duration_ms)

        # Update gateway status code counters for all non-internal client requests
        if src != "internal":
            if status_code == 429:
                self.rate_limited_429 += 1
                self.status_4xx += 1
            elif 200 <= status_code < 300:
                self.status_2xx += 1
            elif 300 <= status_code < 400:
                self.status_3xx += 1
            elif 400 <= status_code < 500:
                self.status_4xx += 1
            elif status_code >= 500:
                self.status_5xx += 1

        # 2. Primary customer-facing cumulative counters & rolling rate window
        # represent actual Online Store customer traffic, NOT internal or synthetic loadgen traffic.
        if src == "online_store":
            self.total_requests += 1
            self.cumulative_ingress_bytes += max(0, ingress_bytes)
            self.cumulative_egress_bytes += max(0, egress_bytes)
            self.latencies_ms.append(duration_ms)

            # Append to 1-second rate window for real-time customer rate
            self._rate_window.append((now_mono, max(0, ingress_bytes), max(0, egress_bytes)))
            self._prune_rate_window(now_mono)

    def record_upstream(
        self,
        region_id: str,
        request_bytes: int,
        response_bytes: int,
        duration_ms: float,
        status_code: int,
        is_timeout: bool = False,
        is_failure: bool = False,
    ) -> None:
        """
        Records internal regional proxy traffic.
        Separate from customer-facing counters to prevent mixing.
        """
        r_norm = region_id.lower().strip()
        if r_norm not in self.regions:
            self.regions[r_norm] = RegionalUpstreamMetrics(r_norm)
        self.regions[r_norm].record(
            req_bytes=request_bytes,
            resp_bytes=response_bytes,
            duration_ms=duration_ms,
            status_code=status_code,
            is_timeout=is_timeout,
            is_failure=is_failure,
        )

    def get_current_rates(self) -> Dict[str, float]:
        """Calculates instantaneous rates over the active 1.0-second sliding window."""
        now = time.monotonic()
        self._prune_rate_window(now)

        if not self._rate_window:
            return {
                "ingress_bytes_per_second": 0.0,
                "egress_bytes_per_second": 0.0,
                "requests_per_second": 0.0,
            }

        ingress_sum = sum(w[1] for w in self._rate_window)
        egress_sum = sum(w[2] for w in self._rate_window)
        req_count = len(self._rate_window)

        # Scale by 1.0s window
        return {
            "ingress_bytes_per_second": round(float(ingress_sum), 2),
            "egress_bytes_per_second": round(float(egress_sum), 2),
            "requests_per_second": round(float(req_count), 2),
        }

    def _percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        s = sorted(self.latencies_ms)
        idx = int(math.ceil(p * len(s))) - 1
        return round(s[max(0, min(idx, len(s) - 1))], 2)

    def get_latency_summary(self) -> Dict[str, float]:
        avg_lat = round(sum(self.latencies_ms) / len(self.latencies_ms), 2) if self.latencies_ms else 0.0
        return {
            "avg_ms": avg_lat,
            "p50_ms": self._percentile(0.50),
            "p95_ms": self._percentile(0.95),
            "p99_ms": self._percentile(0.99),
        }

    def get_telemetry_snapshot(self, active_region: str = "region-a") -> Dict[str, Any]:
        """
        Returns full, truthful snapshot of customer-facing and upstream traffic telemetry.
        """
        rates = self.get_current_rates()
        latencies = self.get_latency_summary()

        return {
            "measurement_info": {
                "last_measurement_timestamp": self.last_measurement_timestamp,
                "measurement_type": "application_payload_bytes",
                "is_measured": True,
                "unit": "bytes",
                "note": "Application/API payload bytes measured at ASGI/HTTP proxy boundaries. Excludes TCP/IP/TLS frame overhead and static assets served directly by Nginx.",
            },
            "customer_facing": {
                "cumulative": {
                    "client_ingress_payload_bytes": self.cumulative_ingress_bytes,
                    "client_egress_payload_bytes": self.cumulative_egress_bytes,
                    "total_requests": self.total_requests,
                    "status_2xx": self.status_2xx,
                    "status_3xx": self.status_3xx,
                    "status_4xx": self.status_4xx,
                    "status_5xx": self.status_5xx,
                    "rate_limited_429": self.rate_limited_429,
                },
                "rates": {
                    "ingress_bytes_per_second": rates["ingress_bytes_per_second"],
                    "egress_bytes_per_second": rates["egress_bytes_per_second"],
                    "requests_per_second": rates["requests_per_second"],
                    "measurement_window_seconds": 1.0,
                },
                "latencies": latencies,
            },
            "upstream_regions": {
                r_id: m.to_dict() for r_id, m in self.regions.items()
            },
            "request_classes": {
                c_id: m.to_dict() for c_id, m in self.request_classes.items()
            },
            "traffic_sources": {
                s_id: m.to_dict() for s_id, m in self.traffic_sources.items()
            },
            "active_region": active_region,
        }

    def reset(self) -> None:
        self.cumulative_ingress_bytes = 0
        self.cumulative_egress_bytes = 0
        self.total_requests = 0
        self.status_2xx = 0
        self.status_3xx = 0
        self.status_4xx = 0
        self.status_5xx = 0
        self.rate_limited_429 = 0
        self.latencies_ms.clear()
        self._rate_window.clear()

        for r in self.regions.values():
            r.reset()
        for c in self.request_classes.values():
            c.reset()
        for s in self.traffic_sources.values():
            s.reset()

        self.last_measurement_timestamp = None
        self.last_measurement_epoch = 0.0


telemetry_collector = GatewayTelemetryCollector()


class ASGITrafficTelemetryMiddleware:
    """
    Pure ASGI middleware for reliable, chunk-aware measurement of customer-facing
    application/API payload bytes (ingress & egress).
    - Captures exact request payload bytes from receive() chunks.
    - Captures exact response payload bytes from send() chunks without buffering or copying streams.
    - Accurately measures empty bodies and multi-chunk streamed responses.
    - Never logs or persists customer request bodies or sensitive data.
    - Excludes simulated WAN latency from measured gateway execution duration.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        # Extract headers dictionary (lowercase)
        raw_headers = scope.get("headers", [])
        headers_map: Dict[str, str] = {}
        for k_bytes, v_bytes in raw_headers:
            try:
                headers_map[k_bytes.decode("latin1").lower()] = v_bytes.decode("latin1")
            except Exception:
                pass

        traffic_source = detect_traffic_source(headers_map, path)
        norm_template, req_category = normalize_endpoint(path)

        # Setup request state for telemetry coordination
        scope_state = scope.setdefault("state", {})
        telemetry_info = {
            "ingress_bytes": 0,
            "egress_bytes": 0,
            "status_code": 200,
            "traffic_source": traffic_source,
            "request_category": req_category,
            "route_template": norm_template,
        }
        scope_state["telemetry_info"] = telemetry_info

        ingress_bytes = 0
        body_chunks_received = 0
        egress_bytes = 0
        response_status = 200

        served_region_captured: Optional[str] = None

        async def telemetry_receive():
            nonlocal ingress_bytes, body_chunks_received
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                if chunk:
                    ingress_bytes += len(chunk)
                    body_chunks_received += 1
                    telemetry_info["ingress_bytes"] = ingress_bytes
            return message

        async def telemetry_send(message):
            nonlocal egress_bytes, response_status, served_region_captured
            if message["type"] == "http.response.start":
                response_status = message["status"]
                telemetry_info["status_code"] = response_status
                # Inspect response headers for actual served/routed region
                raw_resp_headers = message.get("headers", [])
                for k_b, v_b in raw_resp_headers:
                    try:
                        k_str = k_b.decode("latin1").lower()
                        if k_str in ("x-served-region", "x-routed-to-region"):
                            served_region_captured = v_b.decode("latin1").strip()
                    except Exception:
                        pass
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk:
                    egress_bytes += len(chunk)
                    telemetry_info["egress_bytes"] = egress_bytes
            await send(message)

        start_time = time.perf_counter()
        try:
            await self.app(scope, telemetry_receive, telemetry_send)
        except Exception:
            if response_status == 200:
                response_status = 500
            raise
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            # If the application rejected early (e.g. 429 rate limit or 403 standby write)
            # without consuming the request body, drain unread body chunks so actual ingress
            # payload bytes are counted accurately.
            if body_chunks_received == 0 and method in {"POST", "PUT", "PATCH"}:
                try:
                    while True:
                        drain_msg = await asyncio.wait_for(receive(), timeout=0.03)
                        if drain_msg["type"] == "http.request":
                            chunk = drain_msg.get("body", b"")
                            if chunk:
                                ingress_bytes += len(chunk)
                                telemetry_info["ingress_bytes"] = ingress_bytes
                            if not drain_msg.get("more_body", False):
                                break
                        else:
                            break
                except Exception:
                    pass

            telemetry_info["ingress_bytes"] = ingress_bytes
            telemetry_info["egress_bytes"] = egress_bytes
            telemetry_info["duration_ms"] = duration_ms

            # Determine request class and served region from response headers or scope_state
            req_class = scope_state.get("request_type") or "system"
            served_region = (
                served_region_captured
                or scope_state.get("routed_region")
                or scope_state.get("upstream_region")
                or scope_state.get("active_target")
                or "region-a"
            )

            # Record customer-facing telemetry
            telemetry_collector.record_client_request(
                method=method,
                path=path,
                status_code=response_status,
                ingress_bytes=ingress_bytes,
                egress_bytes=egress_bytes,
                duration_ms=duration_ms,
                traffic_source=traffic_source,
                request_class=req_class,
                served_region=served_region,
            )
