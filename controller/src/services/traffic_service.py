import asyncio
import collections
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Set, OrderedDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from fastapi import HTTPException, status

from ..models.entities import TrafficSampleEntity
from ..schemas.traffic import (
    TrafficBatchSubmission,
    TrafficBatchResponse,
    TrafficSummaryResponse,
    TrafficTimeseriesPoint,
    TrafficTimeseriesResponse,
    RegionalTrafficItem,
    RegionalTrafficResponse,
    TrafficEventModel,
    TrafficEventsResponse,
)

logger = logging.getLogger("controller.traffic_service")


def to_utc_naive(dt: datetime) -> datetime:
    """
    Converts a datetime to UTC-naive:
    - If the datetime is naive, treat it as UTC.
    - If it is timezone-aware, convert it to UTC.
    - Remove tzinfo only after conversion.
    - Return the resulting UTC-naive datetime.
    """
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=None)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def to_utc_aware(dt: datetime) -> datetime:
    """
    Converts a datetime to UTC-aware:
    - If the datetime is naive, treat it as UTC.
    - If it is timezone-aware, convert it to UTC.
    - Return the resulting UTC-aware datetime.
    """
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Static region metadata for the five regions
FIVE_REGIONS_METADATA = {
    "region-a": {"name": "Mumbai", "cloud_zone": "ap-south-1"},
    "region-b": {"name": "Singapore", "cloud_zone": "ap-southeast-1"},
    "region-c": {"name": "Frankfurt", "cloud_zone": "eu-central-1"},
    "region-d": {"name": "Virginia", "cloud_zone": "us-east-1"},
    "region-e": {"name": "São Paulo", "cloud_zone": "sa-east-1"},
}


class TrafficService:
    """
    Central service for Gateway telemetry ingestion, persistence, rate calculations,
    time-series querying, regional aggregation, and real-time SSE distribution.
    """

    def __init__(self, max_cached_samples: int = 3600, max_cached_events: int = 1000):
        # In-memory circular buffer of recent samples for fast reads (1 hour at 1 sample/sec)
        self._recent_samples: collections.deque = collections.deque(maxlen=max_cached_samples)
        # Bounded event buffer for live events
        self._recent_events: collections.deque = collections.deque(maxlen=max_cached_events)
        # Known event IDs for deduplication in event buffer
        self._known_event_ids: collections.OrderedDict = collections.OrderedDict()

        # Idempotency cache: tracks recently processed batch IDs (up to 5000)
        self._processed_batch_ids: collections.OrderedDict = collections.OrderedDict()

        # Last received batch per gateway instance for rate delta calculations
        self._last_batches: Dict[str, TrafficBatchSubmission] = {}
        # Latest sample across all gateways
        self._latest_sample: Optional[Dict[str, Any]] = None

        # Regional rate tracking per gateway instance
        self._last_regional_snapshots: Dict[str, Dict[str, Any]] = {}
        self._latest_regional_rates: Dict[str, Dict[str, float]] = {}

        # SSE subscriber queues
        self._sse_subscribers: List[asyncio.Queue] = []
        self._sse_lock: Optional[asyncio.Lock] = None

        # Batch counter for retention pruning triggers
        self._ingest_counter: int = 0

    def _get_sse_lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._sse_lock is None or (loop and getattr(self._sse_lock, "_loop", None) not in (None, loop)):
            self._sse_lock = asyncio.Lock()
        return self._sse_lock

    async def subscribe_sse(self) -> asyncio.Queue:
        """Registers a new SSE listener queue."""
        async with self._get_sse_lock():
            q = asyncio.Queue(maxsize=100)
            self._sse_subscribers.append(q)
            return q

    async def unsubscribe_sse(self, q: asyncio.Queue) -> None:
        """Removes an SSE listener queue."""
        async with self._get_sse_lock():
            if q in self._sse_subscribers:
                self._sse_subscribers.remove(q)

    async def _broadcast_sse(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcasts data to active SSE subscriber queues, dropping dead queues."""
        async with self._get_sse_lock():
            dead_queues = []
            payload = {"event": event_type, "data": data}
            for q in self._sse_subscribers:
                try:
                    if q.full():
                        try:
                            q.get_nowait()
                        except Exception:
                            pass
                    q.put_nowait(payload)
                except Exception:
                    dead_queues.append(q)
            for dq in dead_queues:
                if dq in self._sse_subscribers:
                    self._sse_subscribers.remove(dq)

    async def ingest_traffic_batch(
        self, session: AsyncSession, batch: TrafficBatchSubmission
    ) -> TrafficBatchResponse:
        """
        Idempotently processes and persists an aggregated telemetry batch.
        Validates schema, handles counter resets, calculates delta rates,
        persists to PostgreSQL/SQLite, updates in-memory views, and broadcasts SSE.
        """
        now_utc = datetime.now(timezone.utc)

        # 1. Validation
        if batch.schema_version != "1.0":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported telemetry schema version: '{batch.schema_version}' (expected '1.0')",
            )
        if not batch.gateway_instance_id or not batch.gateway_instance_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="gateway_instance_id cannot be empty",
            )
        if not batch.batch_id or not batch.batch_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="batch_id cannot be empty",
            )
        if batch.reporting_interval_seconds <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="reporting_interval_seconds must be positive",
            )

        # 2. Idempotency Check
        if batch.batch_id in self._processed_batch_ids:
            logger.info("Ignoring duplicate batch_id='%s' (in-memory cache)", batch.batch_id)
            return TrafficBatchResponse(
                status="duplicate",
                batch_id=batch.batch_id,
                message="Batch already processed (idempotent submission)",
                processed_at=now_utc,
            )

        # Check DB if not found in memory
        existing = await session.execute(
            select(TrafficSampleEntity.id).where(TrafficSampleEntity.batch_id == batch.batch_id)
        )
        if existing.scalar_one_or_none() is not None:
            self._record_processed_batch_id(batch.batch_id)
            logger.info("Ignoring duplicate batch_id='%s' (persisted in DB)", batch.batch_id)
            return TrafficBatchResponse(
                status="duplicate",
                batch_id=batch.batch_id,
                message="Batch already processed (idempotent submission)",
                processed_at=now_utc,
            )

        # 3. Rate calculation & counter reset handling
        prev_batch = self._last_batches.get(batch.gateway_instance_id)
        batch_ts = to_utc_aware(batch.timestamp)

        if prev_batch is not None:
            prev_ts = to_utc_aware(prev_batch.timestamp)
            elapsed = (batch_ts - prev_ts).total_seconds()
            if elapsed <= 0.05:
                elapsed = max(0.1, batch.reporting_interval_seconds)

            # Check for gateway restart or counter reset
            if (
                batch.client_ingress_bytes < prev_batch.client_ingress_bytes
                or batch.request_count < prev_batch.request_count
            ):
                logger.info(
                    "Detected counter reset on gateway '%s' (prev_cum=%d, new_cum=%d)",
                    batch.gateway_instance_id,
                    prev_batch.client_ingress_bytes,
                    batch.client_ingress_bytes,
                )
                delta_in = batch.interval_client_ingress_bytes or batch.client_ingress_bytes
                delta_out = batch.interval_client_egress_bytes or batch.client_egress_bytes
                delta_req = batch.interval_requests or batch.request_count
                in_rate = round(float(delta_in) / max(0.1, elapsed), 2)
                out_rate = round(float(delta_out) / max(0.1, elapsed), 2)
                req_rate = round(float(delta_req) / max(0.1, elapsed), 2)
            else:
                delta_in = batch.client_ingress_bytes - prev_batch.client_ingress_bytes
                delta_out = batch.client_egress_bytes - prev_batch.client_egress_bytes
                delta_req = batch.request_count - prev_batch.request_count

                # Use batch's instantaneous rates if provided, otherwise compute from delta over elapsed
                in_rate = batch.client_ingress_rate if batch.client_ingress_rate > 0 else round(float(delta_in) / elapsed, 2)
                out_rate = batch.client_egress_rate if batch.client_egress_rate > 0 else round(float(delta_out) / elapsed, 2)
                req_rate = batch.request_rate if batch.request_rate > 0 else round(float(delta_req) / elapsed, 2)
        else:
            in_rate = batch.client_ingress_rate
            out_rate = batch.client_egress_rate
            req_rate = batch.request_rate

        # 3.1 Calculate regional interval rates based on consecutive cumulative counters per Gateway instance
        gw_id = batch.gateway_instance_id
        prev_regional = self._last_regional_snapshots.get(gw_id)
        new_regional = batch.regional_traffic or {}

        elapsed_regional = max(0.1, batch.reporting_interval_seconds)
        if prev_batch is not None:
            prev_ts = to_utc_aware(prev_batch.timestamp)
            t_diff = (batch_ts - prev_ts).total_seconds()
            if t_diff > 0.05:
                elapsed_regional = t_diff

        regional_rates: Dict[str, Dict[str, float]] = {}
        for r_id, new_r_data in new_regional.items():
            new_reqs = new_r_data.get("requests_total", 0)
            new_req_bytes = new_r_data.get("request_payload_bytes", 0)    # upstream egress: Gateway -> Region
            new_resp_bytes = new_r_data.get("response_payload_bytes", 0)  # upstream ingress: Region -> Gateway

            if prev_regional and r_id in prev_regional:
                prev_r_data = prev_regional[r_id]
                prev_reqs = prev_r_data.get("requests_total", 0)
                prev_req_bytes = prev_r_data.get("request_payload_bytes", 0)
                prev_resp_bytes = prev_r_data.get("response_payload_bytes", 0)

                # Check for counter reset
                if (
                    new_reqs < prev_reqs
                    or new_req_bytes < prev_req_bytes
                    or new_resp_bytes < prev_resp_bytes
                ):
                    delta_reqs = new_reqs
                    delta_egress = new_req_bytes
                    delta_ingress = new_resp_bytes
                else:
                    delta_reqs = max(0, new_reqs - prev_reqs)
                    delta_egress = max(0, new_req_bytes - prev_req_bytes)
                    delta_ingress = max(0, new_resp_bytes - prev_resp_bytes)

                r_req_rate = round(float(delta_reqs) / elapsed_regional, 2)
                r_egress_rate = round(float(delta_egress) / elapsed_regional, 2)
                r_ingress_rate = round(float(delta_ingress) / elapsed_regional, 2)
            else:
                r_req_rate = 0.0
                r_egress_rate = 0.0
                r_ingress_rate = 0.0

            regional_rates[r_id] = {
                "request_rate": r_req_rate,
                "upstream_egress_rate": r_egress_rate,
                "upstream_ingress_rate": r_ingress_rate,
            }

        self._last_regional_snapshots[gw_id] = new_regional
        self._latest_regional_rates = regional_rates

        # 4. Persist to Database
        entity = TrafficSampleEntity(
            batch_id=batch.batch_id,
            gateway_instance_id=batch.gateway_instance_id,
            timestamp=to_utc_naive(batch.timestamp),
            interval_seconds=batch.reporting_interval_seconds,
            client_ingress_bytes=batch.client_ingress_bytes,
            client_egress_bytes=batch.client_egress_bytes,
            client_ingress_rate=in_rate,
            client_egress_rate=out_rate,
            upstream_ingress_bytes=batch.upstream_ingress_bytes,
            upstream_egress_bytes=batch.upstream_egress_bytes,
            upstream_ingress_rate=batch.upstream_ingress_rate,
            upstream_egress_rate=batch.upstream_egress_rate,
            request_count=batch.request_count,
            request_rate=req_rate,
            status_2xx=batch.status_2xx,
            status_3xx=batch.status_3xx,
            status_4xx=batch.status_4xx,
            status_5xx=batch.status_5xx,
            rate_limited_429=batch.rate_limited_429,
            latency_avg_ms=batch.latency_avg_ms,
            latency_p50_ms=batch.latency_p50_ms,
            latency_p95_ms=batch.latency_p95_ms,
            latency_p99_ms=batch.latency_p99_ms,
            regional_traffic_json=batch.regional_traffic,
            traffic_sources_json=batch.traffic_sources,
            dropped_telemetry_count=batch.dropped_telemetry_count,
        )
        session.add(entity)
        await session.commit()

        # 5. Update In-Memory Structures
        self._record_processed_batch_id(batch.batch_id)
        self._last_batches[batch.gateway_instance_id] = batch

        sample_dict = {
            "batch_id": batch.batch_id,
            "gateway_instance_id": batch.gateway_instance_id,
            "timestamp": batch_ts,
            "client_ingress_bytes": batch.client_ingress_bytes,
            "client_egress_bytes": batch.client_egress_bytes,
            "client_ingress_rate": in_rate,
            "client_egress_rate": out_rate,
            "upstream_ingress_rate": batch.upstream_ingress_rate,
            "upstream_egress_rate": batch.upstream_egress_rate,
            "request_rate": req_rate,
            "error_rate": round(float(batch.status_4xx + batch.status_5xx), 2),
            "total_requests": batch.request_count,
            "status_2xx": batch.status_2xx,
            "status_3xx": batch.status_3xx,
            "status_4xx": batch.status_4xx,
            "status_5xx": batch.status_5xx,
            "rate_limited_429": batch.rate_limited_429,
            "latency_avg_ms": batch.latency_avg_ms,
            "latency_p50_ms": batch.latency_p50_ms,
            "latency_p95_ms": batch.latency_p95_ms,
            "latency_p99_ms": batch.latency_p99_ms,
            "regional_traffic": batch.regional_traffic,
            "traffic_sources": batch.traffic_sources,
            "received_at": now_utc,
        }

        # Check for out-of-order batches:
        # If timestamp is strictly after our latest sample or latest sample is empty, update latest
        if self._latest_sample is None or batch_ts >= to_utc_aware(self._latest_sample["timestamp"]):
            self._latest_sample = sample_dict

        self._recent_samples.append(sample_dict)

        # Ingest recent events (deduplicated)
        newly_accepted_events = []
        if batch.events:
            for ev in batch.events:
                ev_id = ev.get("id") or ev.get("request_id")
                if ev_id and ev_id not in self._known_event_ids:
                    self._known_event_ids[ev_id] = True
                    if len(self._known_event_ids) > 2000:
                        self._known_event_ids.popitem(last=False)
                    self._recent_events.append(ev)
                    newly_accepted_events.append(ev)

        # Broadcast SSE metrics
        summary_payload = self.get_traffic_summary().model_dump(mode="json")
        await self._broadcast_sse("traffic_metric", summary_payload)

        # Broadcast each newly accepted traffic event
        for ev in newly_accepted_events:
            req_id = ev.get("request_id") or ev.get("id", "")
            ev_model = TrafficEventModel(
                id=ev.get("id") or f"evt-{req_id}",
                request_id=req_id,
                timestamp=ev.get("timestamp", datetime.now(timezone.utc).isoformat()),
                method=ev.get("method", "GET"),
                endpoint=ev.get("endpoint", "/"),
                client_region=ev.get("client_region", "unknown"),
                served_region=ev.get("served_region", "unknown"),
                request_type=ev.get("request_type", "eventual_read"),
                rate_limiter_decision=ev.get("rate_limiter_decision", "accepted"),
                status_code=ev.get("status_code", 200),
                duration_ms=ev.get("duration_ms", 0.0),
                request_payload_bytes=ev.get("request_payload_bytes", 0),
                response_payload_bytes=ev.get("response_payload_bytes", 0),
                request_category=ev.get("request_category", "other"),
                upstream_region=ev.get("upstream_region"),
                upstream_request_bytes=ev.get("upstream_request_bytes", 0),
                upstream_response_bytes=ev.get("upstream_response_bytes", 0),
                upstream_duration_ms=ev.get("upstream_duration_ms", 0.0),
                traffic_source=ev.get("traffic_source", "online_store"),
                is_replay=ev.get("is_replay", False),
            )
            await self._broadcast_sse("traffic_event", ev_model.model_dump(mode="json"))

        # 6. Periodic Retention Prune (every 100 batches)
        self._ingest_counter += 1
        if self._ingest_counter % 100 == 0:
            await self.prune_old_samples(session, retention_hours=24)

        return TrafficBatchResponse(
            status="accepted",
            batch_id=batch.batch_id,
            message="Batch accepted and persisted",
            processed_at=now_utc,
        )

    def _record_processed_batch_id(self, batch_id: str) -> None:
        """Stores batch_id in bounded LRU map."""
        self._processed_batch_ids[batch_id] = True
        if len(self._processed_batch_ids) > 5000:
            self._processed_batch_ids.popitem(last=False)

    async def prune_old_samples(self, session: AsyncSession, retention_hours: int = 24) -> int:
        """Deletes telemetry samples older than configured retention period."""
        cutoff_aware = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
        cutoff_naive = to_utc_naive(cutoff_aware)
        stmt = delete(TrafficSampleEntity).where(TrafficSampleEntity.timestamp < cutoff_naive)
        result = await session.execute(stmt)
        await session.commit()
        deleted_count = result.rowcount or 0
        if deleted_count > 0:
            logger.info("Pruned %d telemetry samples older than %d hours", deleted_count, retention_hours)
        return deleted_count

    def get_traffic_summary(self) -> TrafficSummaryResponse:
        """
        Returns real-time traffic summary with freshness categorization:
        - 'FRESH': age <= 3.0s
        - 'STALE': age <= 15.0s
        - 'UNAVAILABLE': age > 15.0s or no data received yet
        """
        now = datetime.now(timezone.utc)
        if self._latest_sample is None:
            return TrafficSummaryResponse(
                current_ingress_bytes_per_sec=0.0,
                current_egress_bytes_per_sec=0.0,
                cumulative_ingress_bytes=0,
                cumulative_egress_bytes=0,
                upstream_ingress_bytes_per_sec=0.0,
                upstream_egress_bytes_per_sec=0.0,
                request_rate=0.0,
                total_requests=0,
                status_2xx=0,
                status_3xx=0,
                status_4xx=0,
                status_5xx=0,
                rate_limited_429=0,
                latency_avg_ms=0.0,
                latency_p50_ms=0.0,
                latency_p95_ms=0.0,
                latency_p99_ms=0.0,
                last_received_timestamp=None,
                telemetry_freshness="UNAVAILABLE",
                telemetry_age_seconds=None,
                is_available=False,
                measurement_source="none",
                note="No Gateway telemetry received yet. Awaiting initial batch.",
            )

        s = self._latest_sample
        ts = to_utc_aware(s["timestamp"])
        age = max(0.0, (now - ts).total_seconds())

        if age <= 3.0:
            freshness = "FRESH"
            is_avail = True
        elif age <= 15.0:
            freshness = "STALE"
            is_avail = True
        else:
            freshness = "UNAVAILABLE"
            is_avail = False

        return TrafficSummaryResponse(
            current_ingress_bytes_per_sec=s["client_ingress_rate"],
            current_egress_bytes_per_sec=s["client_egress_rate"],
            cumulative_ingress_bytes=s["client_ingress_bytes"],
            cumulative_egress_bytes=s["client_egress_bytes"],
            upstream_ingress_bytes_per_sec=s["upstream_ingress_rate"],
            upstream_egress_bytes_per_sec=s["upstream_egress_rate"],
            request_rate=s["request_rate"],
            total_requests=s["total_requests"],
            status_2xx=s["status_2xx"],
            status_3xx=s["status_3xx"],
            status_4xx=s["status_4xx"],
            status_5xx=s["status_5xx"],
            rate_limited_429=s["rate_limited_429"],
            latency_avg_ms=s["latency_avg_ms"],
            latency_p50_ms=s["latency_p50_ms"],
            latency_p95_ms=s["latency_p95_ms"],
            latency_p99_ms=s["latency_p99_ms"],
            last_received_timestamp=ts,
            telemetry_freshness=freshness,
            telemetry_age_seconds=round(age, 2),
            is_available=is_avail,
            measurement_source=s["gateway_instance_id"],
            note="Application/API payload bytes measured at Gateway proxy boundaries.",
        )

    async def get_traffic_timeseries(
        self, session: AsyncSession, time_range_seconds: int = 300, step_seconds: int = 1
    ) -> TrafficTimeseriesResponse:
        """
        Retrieves timeseries points for the requested time range and step sampling.
        Prioritizes the circular buffer for rapid responses, merging older persisted DB
        samples when in-memory history does not cover the full requested time range.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=time_range_seconds)

        # In-memory samples covering the window (kept timezone-aware)
        mem_samples = [
            s for s in self._recent_samples
            if to_utc_aware(s["timestamp"]) >= cutoff
        ]

        # Determine if we need older historical samples from the database
        oldest_mem_ts = None
        if mem_samples:
            oldest_mem_ts = min(
                to_utc_aware(s["timestamp"])
                for s in mem_samples
            )

        db_samples = []
        if oldest_mem_ts is None or oldest_mem_ts > cutoff:
            cutoff_naive = to_utc_naive(cutoff)
            stmt = select(TrafficSampleEntity).where(TrafficSampleEntity.timestamp >= cutoff_naive)
            if oldest_mem_ts is not None:
                oldest_mem_ts_naive = to_utc_naive(oldest_mem_ts)
                stmt = stmt.where(TrafficSampleEntity.timestamp < oldest_mem_ts_naive)
            stmt = stmt.order_by(TrafficSampleEntity.timestamp.asc())
            res = await session.execute(stmt)
            entities = res.scalars().all()
            db_samples = [
                {
                    "timestamp": to_utc_aware(e.timestamp),
                    "client_ingress_bytes": e.client_ingress_bytes,
                    "client_egress_bytes": e.client_egress_bytes,
                    "client_ingress_rate": e.client_ingress_rate,
                    "client_egress_rate": e.client_egress_rate,
                    "upstream_ingress_rate": e.upstream_ingress_rate,
                    "upstream_egress_rate": e.upstream_egress_rate,
                    "request_rate": e.request_rate,
                    "error_rate": round(float(e.status_4xx + e.status_5xx), 2),
                    "status_2xx": e.status_2xx,
                    "status_4xx": e.status_4xx,
                    "status_5xx": e.status_5xx,
                    "latency_p95_ms": e.latency_p95_ms,
                }
                for e in entities
            ]

        # Combine database history and in-memory history
        all_samples = db_samples + mem_samples
        all_samples.sort(
            key=lambda s: to_utc_aware(s["timestamp"])
        )

        # Downsample by step_seconds if requested and points exist
        points: List[TrafficTimeseriesPoint] = []
        if all_samples:
            step = max(1, step_seconds)
            for i, s in enumerate(all_samples):
                if i % step == 0 or i == len(all_samples) - 1:
                    ts = to_utc_aware(s["timestamp"])
                    points.append(
                        TrafficTimeseriesPoint(
                            timestamp=ts,
                            client_ingress_bytes=s["client_ingress_bytes"],
                            client_egress_bytes=s["client_egress_bytes"],
                            client_ingress_rate=s["client_ingress_rate"],
                            client_egress_rate=s["client_egress_rate"],
                            upstream_ingress_rate=s["upstream_ingress_rate"],
                            upstream_egress_rate=s["upstream_egress_rate"],
                            request_rate=s["request_rate"],
                            error_rate=s.get("error_rate", round(float(s["status_4xx"] + s["status_5xx"]), 2)),
                            status_2xx=s["status_2xx"],
                            status_4xx=s["status_4xx"],
                            status_5xx=s["status_5xx"],
                            latency_p95_ms=s["latency_p95_ms"],
                        )
                    )

        return TrafficTimeseriesResponse(
            time_range_seconds=time_range_seconds,
            step_seconds=step_seconds,
            point_count=len(points),
            points=points,
        )

    def get_regional_traffic(self) -> RegionalTrafficResponse:
        """
        Returns measured regional upstream traffic counters and throughput across all five regions.
        """
        now = datetime.now(timezone.utc)
        regions_map: Dict[str, RegionalTrafficItem] = {}

        # Default initialization for all five regions
        for r_id, meta in FIVE_REGIONS_METADATA.items():
            regions_map[r_id] = RegionalTrafficItem(
                region_id=r_id,
                region_name=meta["name"],
                cloud_zone=meta["cloud_zone"],
                requests_total=0,
                request_rate=0.0,
                upstream_request_bytes=0,
                upstream_response_bytes=0,
                upstream_ingress_rate=0.0,
                upstream_egress_rate=0.0,
                status_2xx=0,
                status_3xx=0,
                status_4xx=0,
                status_5xx=0,
                failed_requests=0,
                timeouts=0,
                latency_avg_ms=0.0,
            )

        # Populate from latest sample if available
        if self._latest_sample and "regional_traffic" in self._latest_sample:
            raw_regions = self._latest_sample["regional_traffic"]
            for r_id, r_data in raw_regions.items():
                if r_id in regions_map:
                    req_bytes = r_data.get("request_payload_bytes", 0)
                    resp_bytes = r_data.get("response_payload_bytes", 0)
                    req_total = r_data.get("requests_total", 0)
                    regions_map[r_id].requests_total = req_total
                    regions_map[r_id].upstream_request_bytes = req_bytes
                    regions_map[r_id].upstream_response_bytes = resp_bytes
                    regions_map[r_id].status_2xx = r_data.get("status_2xx", 0)
                    regions_map[r_id].status_3xx = r_data.get("status_3xx", 0)
                    regions_map[r_id].status_4xx = r_data.get("status_4xx", 0)
                    regions_map[r_id].status_5xx = r_data.get("status_5xx", 0)
                    regions_map[r_id].failed_requests = r_data.get("failed_requests", 0)
                    regions_map[r_id].timeouts = r_data.get("timeouts", 0)
                    regions_map[r_id].latency_avg_ms = r_data.get("average_latency_ms") or r_data.get("average_duration_ms", 0.0)

                    # Populate calculated interval rates
                    if r_id in self._latest_regional_rates:
                        rates = self._latest_regional_rates[r_id]
                        regions_map[r_id].request_rate = rates.get("request_rate", 0.0)
                        regions_map[r_id].upstream_ingress_rate = rates.get("upstream_ingress_rate", 0.0)
                        regions_map[r_id].upstream_egress_rate = rates.get("upstream_egress_rate", 0.0)

        return RegionalTrafficResponse(timestamp=now, regions=regions_map)

    def get_traffic_events(
        self,
        page: int = 1,
        page_size: int = 20,
        traffic_source: Optional[str] = None,
        client_region: Optional[str] = None,
        served_region: Optional[str] = None,
        status_code: Optional[int] = None,
        request_type: Optional[str] = None,
    ) -> TrafficEventsResponse:
        """
        Returns recent bounded traffic events (newest first) with pagination and optional filtering.
        """
        # Order newest first
        events_list = list(reversed(self._recent_events))

        # Filter if requested
        if traffic_source:
            events_list = [e for e in events_list if e.get("traffic_source") == traffic_source]
        if client_region:
            events_list = [e for e in events_list if e.get("client_region") == client_region]
        if served_region:
            events_list = [e for e in events_list if e.get("served_region") == served_region]
        if status_code is not None:
            events_list = [e for e in events_list if e.get("status_code") == status_code]
        if request_type:
            events_list = [e for e in events_list if e.get("request_type") == request_type]

        total = len(events_list)
        page = max(1, page)
        page_size = max(1, min(100, page_size))

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        slice_events = events_list[start_idx:end_idx]

        models: List[TrafficEventModel] = []
        for e in slice_events:
            req_id = e.get("request_id") or e.get("id", "")
            models.append(
                TrafficEventModel(
                    id=e.get("id") or f"evt-{req_id}",
                    request_id=req_id,
                    timestamp=e.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    method=e.get("method", "GET"),
                    endpoint=e.get("endpoint", "/"),
                    client_region=e.get("client_region", "unknown"),
                    served_region=e.get("served_region", "unknown"),
                    request_type=e.get("request_type", "eventual_read"),
                    rate_limiter_decision=e.get("rate_limiter_decision", "accepted"),
                    status_code=e.get("status_code", 200),
                    duration_ms=e.get("duration_ms", 0.0),
                    request_payload_bytes=e.get("request_payload_bytes", 0),
                    response_payload_bytes=e.get("response_payload_bytes", 0),
                    request_category=e.get("request_category", "other"),
                    upstream_region=e.get("upstream_region"),
                    upstream_request_bytes=e.get("upstream_request_bytes", 0),
                    upstream_response_bytes=e.get("upstream_response_bytes", 0),
                    upstream_duration_ms=e.get("upstream_duration_ms", 0.0),
                    traffic_source=e.get("traffic_source", "online_store"),
                    is_replay=e.get("is_replay", False),
                )
            )

        return TrafficEventsResponse(
            total=total,
            page=page,
            page_size=page_size,
            events=models,
        )

    def reset(self) -> None:
        """Resets all in-memory telemetry state for testing."""
        self._recent_samples.clear()
        self._recent_events.clear()
        self._known_event_ids.clear()
        self._processed_batch_ids.clear()
        self._last_batches.clear()
        self._latest_sample = None
        self._last_regional_snapshots.clear()
        self._latest_regional_rates.clear()
        self._ingest_counter = 0


# Singleton service instance
traffic_service = TrafficService()
