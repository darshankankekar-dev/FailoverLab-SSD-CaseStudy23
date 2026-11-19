import asyncio
import logging
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import httpx

from .config import settings
from .telemetry import telemetry_collector
from .traffic_manager import traffic_coordinator

logger = logging.getLogger("gateway.telemetry_exporter")


class GatewayTelemetryExporter:
    """
    Asynchronous background telemetry exporter that collects aggregated traffic
    metrics from GatewayTelemetryCollector and sends 1-second metric batches directly
    to the Controller's internal ingestion endpoint via the Docker internal network.

    Key capabilities:
    - Approximately 1-second batch aggregation.
    - Protected via internal service-to-service authentication (X-Internal-Secret).
    - Bounded queue prevents unbounded memory growth.
    - Non-blocking: never degrades or blocks customer traffic paths.
    - Reliable bounded retry mechanism with exponential backoff.
    - Truthful health reporting: not healthy until a successful export has occurred.
    - Graceful cancellation and clean shutdown.
    - Full health and dropped telemetry counters.
    - Counter reset handling for client, upstream, and per-region counters.
    """

    def __init__(
        self,
        controller_url: Optional[str] = None,
        internal_token: Optional[str] = None,
        gateway_instance_id: Optional[str] = None,
        interval_seconds: Optional[float] = None,
        queue_capacity: Optional[int] = None,
        max_retries: Optional[int] = None,
        backoff_base: float = 0.5,
        backoff_max: float = 10.0,
    ):
        self.controller_url = (controller_url or settings.controller_url).rstrip("/")
        self.internal_token = internal_token or settings.internal_token
        self.gateway_instance_id = gateway_instance_id or settings.gateway_instance_id
        self.interval_seconds = interval_seconds or settings.telemetry_export_interval_seconds
        self.queue_capacity = queue_capacity or settings.telemetry_queue_capacity
        self.max_retries = max_retries if max_retries is not None else getattr(settings, "telemetry_max_retries", 5)
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

        self._queue: Optional[asyncio.Queue] = None
        self._running: bool = False
        self._sampler_task: Optional[asyncio.Task] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None

        # Exporter health and telemetry metrics
        self.last_successful_export: Optional[str] = None
        self.consecutive_failures: int = 0
        self.total_exported_batches: int = 0
        self.dropped_batches_count: int = 0
        self.last_error: Optional[str] = None

        # Delta calculation baselines
        self._prev_client_ingress_bytes: int = 0
        self._prev_client_egress_bytes: int = 0
        self._prev_total_requests: int = 0
        self._prev_upstream_ingress_bytes: int = 0
        self._prev_upstream_egress_bytes: int = 0
        self._prev_regional: Dict[str, Dict[str, int]] = {}
        self._prev_timestamp: Optional[datetime] = None

    def _get_queue(self) -> asyncio.Queue:
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self.queue_capacity)
        return self._queue

    def build_batch(self) -> Dict[str, Any]:
        """
        Constructs an aggregated one-second metric batch from the live telemetry collector.
        Calculates interval deltas using actual elapsed time and detects counter resets.
        """
        now_dt = datetime.now(timezone.utc)
        snapshot = telemetry_collector.get_telemetry_snapshot()

        # Compute actual elapsed time between consecutive batch builds
        if self._prev_timestamp is not None:
            elapsed = (now_dt - self._prev_timestamp).total_seconds()
            if elapsed <= 0.05:
                elapsed = max(0.1, self.interval_seconds)
        else:
            elapsed = max(0.1, self.interval_seconds)

        cum_ingress = snapshot["customer_facing"]["cumulative"]["client_ingress_payload_bytes"]
        cum_egress = snapshot["customer_facing"]["cumulative"]["client_egress_payload_bytes"]
        cum_reqs = snapshot["customer_facing"]["cumulative"]["total_requests"]

        # Sum upstream cumulative payload bytes across regions
        up_egress_cum = sum(
            r.get("request_payload_bytes", 0) for r in snapshot.get("upstream_regions", {}).values()
        )
        up_ingress_cum = sum(
            r.get("response_payload_bytes", 0) for r in snapshot.get("upstream_regions", {}).values()
        )

        # Detect counter resets (e.g. gateway reset_all or restart)
        is_reset = (
            cum_ingress < self._prev_client_ingress_bytes
            or cum_egress < self._prev_client_egress_bytes
            or cum_reqs < self._prev_total_requests
            or up_ingress_cum < self._prev_upstream_ingress_bytes
            or up_egress_cum < self._prev_upstream_egress_bytes
        )

        if is_reset:
            logger.info("Gateway telemetry counter reset detected; resetting baseline deltas.")
            delta_ingress = cum_ingress
            delta_egress = cum_egress
            delta_reqs = cum_reqs
            delta_up_in = up_ingress_cum
            delta_up_out = up_egress_cum
        else:
            delta_ingress = max(0, cum_ingress - self._prev_client_ingress_bytes)
            delta_egress = max(0, cum_egress - self._prev_client_egress_bytes)
            delta_reqs = max(0, cum_reqs - self._prev_total_requests)
            delta_up_in = max(0, up_ingress_cum - self._prev_upstream_ingress_bytes)
            delta_up_out = max(0, up_egress_cum - self._prev_upstream_egress_bytes)

        # Per-region counter reset handling & deltas
        regional_payload: Dict[str, Any] = {}
        for r_id, r_data in snapshot.get("upstream_regions", {}).items():
            r_reqs = r_data.get("requests_total", 0)
            r_req_bytes = r_data.get("request_payload_bytes", 0)
            r_resp_bytes = r_data.get("response_payload_bytes", 0)

            prev_r = self._prev_regional.get(r_id, {})
            prev_r_reqs = prev_r.get("requests_total", 0)
            prev_r_req_bytes = prev_r.get("request_payload_bytes", 0)
            prev_r_resp_bytes = prev_r.get("response_payload_bytes", 0)

            if (
                is_reset
                or r_reqs < prev_r_reqs
                or r_req_bytes < prev_r_req_bytes
                or r_resp_bytes < prev_r_resp_bytes
            ):
                d_r_reqs = r_reqs
                d_r_req_bytes = r_req_bytes
                d_r_resp_bytes = r_resp_bytes
            else:
                d_r_reqs = max(0, r_reqs - prev_r_reqs)
                d_r_req_bytes = max(0, r_req_bytes - prev_r_req_bytes)
                d_r_resp_bytes = max(0, r_resp_bytes - prev_r_resp_bytes)

            r_copy = dict(r_data)
            r_copy["interval_requests"] = d_r_reqs
            r_copy["interval_request_bytes"] = d_r_req_bytes
            r_copy["interval_response_bytes"] = d_r_resp_bytes
            r_copy["request_rate"] = round(float(d_r_reqs) / elapsed, 2)
            r_copy["upstream_egress_rate"] = round(float(d_r_req_bytes) / elapsed, 2)
            r_copy["upstream_ingress_rate"] = round(float(d_r_resp_bytes) / elapsed, 2)
            regional_payload[r_id] = r_copy

            self._prev_regional[r_id] = {
                "requests_total": r_reqs,
                "request_payload_bytes": r_req_bytes,
                "response_payload_bytes": r_resp_bytes,
            }

        # Update baselines
        self._prev_client_ingress_bytes = cum_ingress
        self._prev_client_egress_bytes = cum_egress
        self._prev_total_requests = cum_reqs
        self._prev_upstream_ingress_bytes = up_ingress_cum
        self._prev_upstream_egress_bytes = up_egress_cum
        self._prev_timestamp = now_dt

        # Recent events from traffic manager (up to 50)
        recent_events = traffic_coordinator.get_traffic_history(limit=50)

        # Derived rates using actual elapsed time
        client_in_rate = round(float(delta_ingress) / elapsed, 2)
        client_out_rate = round(float(delta_egress) / elapsed, 2)
        up_in_rate = round(float(delta_up_in) / elapsed, 2)
        up_out_rate = round(float(delta_up_out) / elapsed, 2)
        req_rate = round(float(delta_reqs) / elapsed, 2)

        batch = {
            "schema_version": "1.0",
            "gateway_instance_id": self.gateway_instance_id,
            "batch_id": f"batch-{uuid.uuid4().hex[:16]}",
            "timestamp": now_dt.isoformat(),
            "reporting_interval_seconds": round(elapsed, 3),
            "client_ingress_bytes": cum_ingress,
            "client_egress_bytes": cum_egress,
            "interval_client_ingress_bytes": delta_ingress,
            "interval_client_egress_bytes": delta_egress,
            "upstream_ingress_bytes": up_ingress_cum,
            "upstream_egress_bytes": up_egress_cum,
            "interval_upstream_ingress_bytes": delta_up_in,
            "interval_upstream_egress_bytes": delta_up_out,
            "client_ingress_rate": client_in_rate,
            "client_egress_rate": client_out_rate,
            "upstream_ingress_rate": up_in_rate,
            "upstream_egress_rate": up_out_rate,
            "request_count": cum_reqs,
            "interval_requests": delta_reqs,
            "request_rate": req_rate,
            "status_2xx": snapshot["customer_facing"]["cumulative"]["status_2xx"],
            "status_3xx": snapshot["customer_facing"]["cumulative"]["status_3xx"],
            "status_4xx": snapshot["customer_facing"]["cumulative"]["status_4xx"],
            "status_5xx": snapshot["customer_facing"]["cumulative"]["status_5xx"],
            "rate_limited_429": snapshot["customer_facing"]["cumulative"]["rate_limited_429"],
            "latency_avg_ms": snapshot["customer_facing"]["latencies"]["avg_ms"],
            "latency_p50_ms": snapshot["customer_facing"]["latencies"]["p50_ms"],
            "latency_p95_ms": snapshot["customer_facing"]["latencies"]["p95_ms"],
            "latency_p99_ms": snapshot["customer_facing"]["latencies"]["p99_ms"],
            "regional_traffic": regional_payload,
            "traffic_sources": snapshot.get("traffic_sources", {}),
            "dropped_telemetry_count": self.dropped_batches_count,
            "events": recent_events,
        }
        return batch

    def enqueue_batch(self, batch: Dict[str, Any]) -> bool:
        """
        Pushes batch into bounded queue without blocking.
        If queue is full, drops the batch and increments dropped_batches_count.
        """
        queue = self._get_queue()
        try:
            queue.put_nowait(batch)
            return True
        except asyncio.QueueFull:
            self.dropped_batches_count += 1
            logger.warning(
                "Telemetry export queue is full (%d items); dropping batch %s",
                self.queue_capacity,
                batch.get("batch_id"),
            )
            return False

    async def send_batch(self, batch: Dict[str, Any]) -> bool:
        """
        Directly sends a metric batch to Controller /internal/telemetry/traffic-batch.
        Returns True on success (HTTP 200/201/202), False otherwise.
        """
        url = f"{self.controller_url}/internal/telemetry/traffic-batch"
        headers = {
            "X-Internal-Secret": self.internal_token,
            "Content-Type": "application/json",
            "User-Agent": f"FailoverLab-Gateway/{self.gateway_instance_id}",
        }

        # Clean payload: strip internal helper keys and report latest dropped_telemetry_count
        payload = {k: v for k, v in batch.items() if not k.startswith("_")}
        payload["dropped_telemetry_count"] = self.dropped_batches_count

        client = self._client
        owns_client = False
        if client is None or client.is_closed:
            client = httpx.AsyncClient(timeout=3.0)
            owns_client = True

        try:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201, 202):
                self.last_successful_export = datetime.now(timezone.utc).isoformat()
                self.consecutive_failures = 0
                self.total_exported_batches += 1
                self.last_error = None
                return True
            else:
                self.consecutive_failures += 1
                self.last_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
                logger.warning(
                    "Controller rejected telemetry batch %s with status %d: %s",
                    batch.get("batch_id"),
                    resp.status_code,
                    resp.text[:120],
                )
                return False
        except Exception as e:
            self.consecutive_failures += 1
            self.last_error = str(e)
            logger.debug("Failed to export telemetry batch to Controller at %s: %s", url, e)
            return False
        finally:
            if owns_client:
                await client.aclose()

    async def _sampler_loop(self) -> None:
        """Periodically samples telemetry and enqueues batches."""
        logger.info("Started Gateway telemetry sampler loop (interval=%.1fs)", self.interval_seconds)
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                if not self._running:
                    break
                batch = self.build_batch()
                self.enqueue_batch(batch)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in telemetry sampler loop: %s", e, exc_info=True)
                await asyncio.sleep(0.5)

    async def _worker_loop(self) -> None:
        """Worker loop that dequeues batches and exports them with exponential backoff on failure."""
        logger.info("Started Gateway telemetry export worker loop")
        queue = self._get_queue()

        while self._running:
            try:
                # Wait for next batch
                try:
                    batch = await asyncio.wait_for(queue.get(), timeout=1.0)
                except (asyncio.TimeoutError, TimeoutError):
                    continue

                try:
                    success = await self.send_batch(batch)
                    if not success:
                        for attempt in range(1, self.max_retries + 1):
                            if not self._running:
                                break
                            backoff = min(
                                self.backoff_max,
                                self.backoff_base * (2 ** min(self.consecutive_failures - 1, 4)),
                            )
                            logger.warning(
                                "Telemetry batch %s send failed (attempt %d/%d). Backing off %.2fs.",
                                batch.get("batch_id"),
                                attempt,
                                self.max_retries,
                                backoff,
                            )
                            try:
                                await asyncio.sleep(backoff)
                            except asyncio.CancelledError:
                                break

                            if not self._running:
                                break

                            success = await self.send_batch(batch)
                            if success:
                                break

                        if not success:
                            self.dropped_batches_count += 1
                            logger.error(
                                "Telemetry batch %s dropped after exhausting %d retries.",
                                batch.get("batch_id"),
                                self.max_retries,
                            )
                finally:
                    queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in telemetry worker loop: %s", e, exc_info=True)
                await asyncio.sleep(0.5)

    async def start(self) -> None:
        """Starts the background sampler and exporter loops."""
        if self._running:
            return
        self._running = True
        self._client = httpx.AsyncClient(timeout=3.0)
        self._sampler_task = asyncio.create_task(self._sampler_loop())
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info(
            "Gateway telemetry exporter started (target: %s, instance: %s)",
            self.controller_url,
            self.gateway_instance_id,
        )

    async def stop(self) -> None:
        """Stops background tasks and cleanly closes resources."""
        self._running = False

        if self._sampler_task and not self._sampler_task.done():
            self._sampler_task.cancel()
            try:
                await asyncio.wait_for(self._sampler_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, TimeoutError):
                pass
            self._sampler_task = None

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await asyncio.wait_for(self._worker_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, TimeoutError):
                pass
            self._worker_task = None

        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

        logger.info("Gateway telemetry exporter stopped cleanly.")

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic health and counter status of the exporter."""
        queue_size = self._queue.qsize() if self._queue is not None else 0
        return {
            "is_running": self._running,
            "gateway_instance_id": self.gateway_instance_id,
            "controller_url": self.controller_url,
            "reporting_interval_seconds": self.interval_seconds,
            "queue_capacity": self.queue_capacity,
            "current_queue_size": queue_size,
            "total_exported_batches": self.total_exported_batches,
            "dropped_batches_count": self.dropped_batches_count,
            "consecutive_failures": self.consecutive_failures,
            "last_successful_export": self.last_successful_export,
            "last_error": self.last_error,
            "is_healthy": bool(self.last_successful_export is not None and self.consecutive_failures == 0),
        }

    def reset(self) -> None:
        """Resets counters and deltas for testing."""
        self.last_successful_export = None
        self.consecutive_failures = 0
        self.total_exported_batches = 0
        self.dropped_batches_count = 0
        self.last_error = None
        self._prev_client_ingress_bytes = 0
        self._prev_client_egress_bytes = 0
        self._prev_total_requests = 0
        self._prev_upstream_ingress_bytes = 0
        self._prev_upstream_egress_bytes = 0
        self._prev_regional.clear()
        self._prev_timestamp = None
        if self._queue is not None:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except Exception:
                    break


# Singleton exporter instance
telemetry_exporter = GatewayTelemetryExporter()
