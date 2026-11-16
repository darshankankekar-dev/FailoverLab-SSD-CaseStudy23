import time
import asyncio
import collections
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Tuple, Optional, Any, List
import logging
import uuid
from pydantic import BaseModel, Field
from fastapi import HTTPException, status

logger = logging.getLogger("gateway.traffic")


class TrafficEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:10]}")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request_id: str
    method: str
    endpoint: str
    client_region: str
    served_region: str
    request_type: str  # "eventual_read", "strong_read", "write", "internal"
    rate_limiter_decision: str  # "accepted", "rejected", "delayed"
    status_code: int
    duration_ms: float
    simulated_wan_delay_ms: float = 0.0
    queue_wait_time_ms: float = 0.0


class LimiterMode(str, Enum):
    OFF = "OFF"
    TOKEN_BUCKET = "TOKEN_BUCKET"
    LEAKY_BUCKET = "LEAKY_BUCKET"


# =========================================================================
# Token Bucket Rate Limiter
# =========================================================================

class ClientTokenBucket:
    """
    Per-client Token Bucket.
    Guarantees concurrency safety using asyncio.Lock and monotonic time.
    """

    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self._lock: Optional[asyncio.Lock] = None
        self.accepted_requests = 0
        self.rejected_requests = 0
        self.total_refilled = 0.0

    def _get_lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._lock is None or (loop and getattr(self._lock, "_loop", None) not in (None, loop)):
            self._lock = asyncio.Lock()
        return self._lock

    async def consume(self, cost: float = 1.0) -> Tuple[bool, float, float]:
        async with self._get_lock():
            now = time.monotonic()
            elapsed = now - self.last_refill
            if elapsed > 0:
                refill_amount = elapsed * self.refill_rate
                new_tokens = min(self.capacity, self.tokens + refill_amount)
                self.total_refilled += max(0.0, new_tokens - self.tokens)
                self.tokens = new_tokens
                self.last_refill = now

            if self.tokens >= cost:
                self.tokens -= cost
                self.accepted_requests += 1
                return True, self.tokens, 0.0
            else:
                self.rejected_requests += 1
                needed = cost - self.tokens
                retry_after = round(needed / self.refill_rate, 2) if self.refill_rate > 0 else 1.0
                return False, self.tokens, retry_after

    def get_tokens(self) -> float:
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            return min(self.capacity, self.tokens + (elapsed * self.refill_rate))
        return self.tokens


class TokenBucketLimiter:
    """
    Manages Token Bucket instances per client / API key.
    Initial configuration: Capacity 10 tokens, refill 2 tokens/sec.
    """

    def __init__(self, capacity: float = 10.0, refill_rate: float = 2.0):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.buckets: Dict[str, ClientTokenBucket] = {}
        self._lock: Optional[asyncio.Lock] = None
        self.total_accepted = 0
        self.total_rejected = 0

    def _get_lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._lock is None or (loop and getattr(self._lock, "_loop", None) not in (None, loop)):
            self._lock = asyncio.Lock()
        return self._lock

    async def _get_bucket(self, client_key: str) -> ClientTokenBucket:
        async with self._get_lock():
            if client_key not in self.buckets:
                self.buckets[client_key] = ClientTokenBucket(self.capacity, self.refill_rate)
            return self.buckets[client_key]

    async def check(self, client_key: str, cost: float = 1.0) -> Tuple[bool, float, float]:
        bucket = await self._get_bucket(client_key)
        allowed, remaining, retry_after = await bucket.consume(cost)
        if allowed:
            self.total_accepted += 1
        else:
            self.total_rejected += 1
        return allowed, remaining, retry_after

    def get_stats(self, default_client: Optional[str] = None) -> Dict[str, Any]:
        bucket = None
        if default_client and default_client in self.buckets:
            bucket = self.buckets[default_client]
        elif len(self.buckets) == 1:
            bucket = next(iter(self.buckets.values()))
        elif len(self.buckets) > 1:
            # Return bucket with lowest remaining tokens for conservative visibility
            bucket = min(self.buckets.values(), key=lambda b: b.get_tokens())

        tokens_rem = bucket.get_tokens() if bucket else self.capacity
        total_refilled = sum(b.total_refilled for b in self.buckets.values())
        return {
            "capacity": self.capacity,
            "refill_rate": self.refill_rate,
            "tokens_remaining": round(tokens_rem, 2),
            "accepted_requests": self.total_accepted,
            "rejected_requests": self.total_rejected,
            "total_refilled": round(total_refilled, 2),
            "active_client_buckets": len(self.buckets),
        }

    def reset(self) -> None:
        self.buckets.clear()
        self._lock = None
        self.total_accepted = 0
        self.total_rejected = 0


# =========================================================================
# Leaky Bucket Traffic Shaper (Bounded FIFO Queue & Fixed Drain Worker)
# =========================================================================

class QueuedRequest:
    def __init__(self, request_id: str, client_key: str):
        self.request_id = request_id
        self.client_key = client_key
        self.enqueued_at = time.monotonic()
        self.future: asyncio.Future = asyncio.get_running_loop().create_future()


class LeakyBucketShaper:
    """
    Implements a bounded FIFO request queue drained by a background worker at a fixed rate.
    Initial configuration: Queue capacity 20 requests, drain rate 2 requests/sec (0.5s per release).
    """

    def __init__(self, queue_capacity: int = 20, drain_rate: float = 2.0):
        self.queue_capacity = int(queue_capacity)
        self.drain_rate = float(drain_rate)
        self._queue: Optional[asyncio.Queue] = None
        self.worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock: Optional[asyncio.Lock] = None
        self._wake_event: Optional[asyncio.Event] = None

        # Metrics
        self.processed_requests = 0
        self.overflow_requests = 0
        self.total_wait_time = 0.0
        self.last_wait_time = 0.0

    def _get_lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._lock is None or (loop and getattr(self._lock, "_loop", None) not in (None, loop)):
            self._lock = asyncio.Lock()
        return self._lock

    def _get_queue(self) -> asyncio.Queue:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._queue is None or (loop and getattr(self._queue, "_loop", None) not in (None, loop)):
            self._queue = asyncio.Queue()
        return self._queue

    def _get_wake_event(self) -> asyncio.Event:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._wake_event is None or (loop and getattr(self._wake_event, "_loop", None) not in (None, loop)):
            self._wake_event = asyncio.Event()
        return self._wake_event

    async def start(self) -> None:
        async with self._get_lock():
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None

            worker_loop = getattr(self.worker_task, "_loop", None) if self.worker_task else None

            if self._running and self.worker_task and not self.worker_task.done() and (worker_loop == current_loop or worker_loop is None):
                return

            if self.worker_task and not self.worker_task.done():
                self.worker_task.cancel()
                try:
                    await self.worker_task
                except asyncio.CancelledError:
                    pass
                self.worker_task = None

            self._running = True
            self.worker_task = asyncio.create_task(self._drain_loop())
            logger.info(
                f"Leaky Bucket Shaper started (Capacity: {self.queue_capacity}, Drain Rate: {self.drain_rate} req/s)"
            )

    async def stop(self) -> None:
        async with self._get_lock():
            self._running = False
            if self._wake_event is not None:
                self._wake_event.set()
            if self.worker_task and not self.worker_task.done():
                self.worker_task.cancel()
                try:
                    await self.worker_task
                except asyncio.CancelledError:
                    pass
                self.worker_task = None

            # Cancel remaining queued items safely
            if self._queue is not None:
                while not self._queue.empty():
                    try:
                        item: QueuedRequest = self._queue.get_nowait()
                        if not item.future.done():
                            item.future.set_exception(
                                HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Gateway traffic shaper stopped")
                            )
                    except Exception:
                        break

    async def _drain_loop(self) -> None:
        while self._running:
            try:
                queue = self._get_queue()
                item: QueuedRequest = await queue.get()
                now = time.monotonic()
                wait_time = now - item.enqueued_at
                self.total_wait_time += wait_time
                self.last_wait_time = wait_time
                self.processed_requests += 1

                # Fulfill future if not cancelled by client
                if not item.future.cancelled() and not item.future.done():
                    item.future.set_result(True)

                queue.task_done()

                interval = 1.0 / self.drain_rate if self.drain_rate > 0 else 0.5
                wake_event = self._get_wake_event()
                wake_event.clear()
                try:
                    await asyncio.wait_for(wake_event.wait(), timeout=interval)
                except (asyncio.TimeoutError, TimeoutError):
                    pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in leaky bucket drain worker: {e}", exc_info=True)
                await asyncio.sleep(0.05)

    async def enqueue(self, client_key: str, request_id: str) -> Tuple[bool, float, str]:
        """
        Pushes a request into the bounded queue.
        Returns:
            (allowed: bool, wait_time_sec: float, error_message: str)
        """
        queue = self._get_queue()

        # Reject if queue is at capacity
        if queue.qsize() >= self.queue_capacity:
            self.overflow_requests += 1
            retry_after = round(self.queue_capacity / self.drain_rate, 2) if self.drain_rate > 0 else 1.0
            return False, retry_after, "Leaky bucket queue overflow: capacity exceeded"

        # Ensure background dispatcher is running in current loop
        if not self._running or self.worker_task is None or self.worker_task.done():
            await self.start()

        item = QueuedRequest(request_id=request_id, client_key=client_key)
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            self.overflow_requests += 1
            retry_after = round(self.queue_capacity / self.drain_rate, 2) if self.drain_rate > 0 else 1.0
            return False, retry_after, "Leaky bucket queue overflow: capacity exceeded"

        try:
            await item.future
            wait_time = time.monotonic() - item.enqueued_at
            return True, wait_time, "OK"
        except asyncio.CancelledError:
            logger.info(f"Queued request '{request_id}' cancelled while waiting in leaky bucket queue")
            raise

    def get_stats(self) -> Dict[str, Any]:
        avg_wait = (self.total_wait_time / self.processed_requests) if self.processed_requests > 0 else 0.0
        depth = self._queue.qsize() if self._queue is not None else 0
        return {
            "queue_capacity": self.queue_capacity,
            "drain_rate": self.drain_rate,
            "current_queue_depth": depth,
            "processed_requests": self.processed_requests,
            "overflow_requests": self.overflow_requests,
            "average_wait_time_ms": round(avg_wait * 1000, 2),
            "last_wait_time_ms": round(self.last_wait_time * 1000, 2),
        }

    def reset(self) -> None:
        self._running = False
        if self.worker_task and not self.worker_task.done():
            self.worker_task.cancel()
            self.worker_task = None
        self._queue = None
        self._lock = None
        self._wake_event = None
        self.processed_requests = 0
        self.overflow_requests = 0
        self.total_wait_time = 0.0
        self.last_wait_time = 0.0


# =========================================================================
# Idempotency Cache Manager
# =========================================================================

class CachedResponse:
    def __init__(self, status_code: int, content: bytes, headers: Dict[str, str]):
        self.status_code = status_code
        self.content = content
        self.headers = headers
        self.cached_at = time.monotonic()


class IdempotencyManager:
    """
    Prevents duplicate operations for retried mutations bearing an Idempotency-Key.
    """

    def __init__(self, ttl_seconds: float = 3600.0):
        self.cache: Dict[str, CachedResponse] = {}
        self.key_locks: Dict[str, asyncio.Lock] = {}
        self._lock: Optional[asyncio.Lock] = None
        self.ttl_seconds = ttl_seconds

    def _get_lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._lock is None or (loop and getattr(self._lock, "_loop", None) not in (None, loop)):
            self._lock = asyncio.Lock()
        return self._lock

    async def get_lock(self, key: str) -> asyncio.Lock:
        async with self._get_lock():
            if key not in self.key_locks:
                self.key_locks[key] = asyncio.Lock()
            return self.key_locks[key]

    def get(self, key: str) -> Optional[CachedResponse]:
        item = self.cache.get(key)
        if item:
            if time.monotonic() - item.cached_at < self.ttl_seconds:
                return item
            else:
                del self.cache[key]
        return None

    def store(self, key: str, status_code: int, content: bytes, headers: Dict[str, str]) -> None:
        self.cache[key] = CachedResponse(status_code, content, headers)

    def clear(self) -> None:
        self.cache.clear()
        self.key_locks.clear()
        self._lock = None


# =========================================================================
# Unified Gateway Traffic Coordinator
# =========================================================================

class GatewayTrafficCoordinator:
    """
    Unified manager for Gateway Traffic Control:
    - Configurable Mode: OFF, TOKEN_BUCKET, LEAKY_BUCKET.
    - Token Bucket Rate Limiter (initial: capacity=10, refill=2/s).
    - Leaky Bucket Traffic Shaper (initial: capacity=20, drain=2/s).
    - Idempotency deduplication for checkout mutations.
    - Truthful metrics collection (latencies, counts, rates).
    """

    def __init__(
        self,
        initial_mode: LimiterMode = LimiterMode.TOKEN_BUCKET,
        token_capacity: float = 10.0,
        token_refill_rate: float = 2.0,
        leaky_capacity: int = 20,
        leaky_drain_rate: float = 2.0,
    ):
        self.mode = initial_mode
        self.token_limiter = TokenBucketLimiter(capacity=token_capacity, refill_rate=token_refill_rate)
        self.leaky_shaper = LeakyBucketShaper(queue_capacity=leaky_capacity, drain_rate=leaky_drain_rate)
        self.idempotency = IdempotencyManager()

        # Common metrics
        self.total_requests = 0
        self.accepted_requests = 0
        self.throttled_requests = 0
        self.server_failures = 0
        self.latency_samples: List[float] = []

        # Real-time traffic events & SSE subscriber broadcast
        self.traffic_events: collections.deque = collections.deque(maxlen=250)
        self.subscribers: List[asyncio.Queue] = []
        self._subscriber_lock: Optional[asyncio.Lock] = None

    def _get_sub_lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._subscriber_lock is None or (loop and getattr(self._subscriber_lock, "_loop", None) not in (None, loop)):
            self._subscriber_lock = asyncio.Lock()
        return self._subscriber_lock

    async def record_traffic_event(self, event: TrafficEvent) -> None:
        self.traffic_events.append(event)
        async with self._get_sub_lock():
            dead_queues = []
            for q in self.subscribers:
                try:
                    if q.full():
                        try:
                            q.get_nowait()
                        except Exception:
                            pass
                    q.put_nowait(event)
                except Exception:
                    dead_queues.append(q)
            for dq in dead_queues:
                if dq in self.subscribers:
                    self.subscribers.remove(dq)

    async def subscribe(self) -> asyncio.Queue:
        async with self._get_sub_lock():
            q = asyncio.Queue(maxsize=100)
            self.subscribers.append(q)
            return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._get_sub_lock():
            if q in self.subscribers:
                self.subscribers.remove(q)

    def get_traffic_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        evs = list(self.traffic_events)
        return [e.model_dump() for e in evs[-limit:]]

    def record_request_outcome(self, status_code: int, latency_ms: float) -> None:
        self.total_requests += 1
        if status_code < 400:
            self.accepted_requests += 1
        elif status_code == 429:
            self.throttled_requests += 1
        elif status_code >= 500:
            self.server_failures += 1

        self.latency_samples.append(latency_ms)
        if len(self.latency_samples) > 2000:
            self.latency_samples = self.latency_samples[-1000:]

    def get_latency_stats(self) -> Tuple[float, float]:
        if not self.latency_samples:
            return 0.0, 0.0
        avg_lat = sum(self.latency_samples) / len(self.latency_samples)
        sorted_samples = sorted(self.latency_samples)
        idx_p95 = int(len(sorted_samples) * 0.95)
        p95_lat = sorted_samples[min(idx_p95, len(sorted_samples) - 1)]
        return round(avg_lat, 2), round(p95_lat, 2)

    def set_mode(self, mode: LimiterMode) -> None:
        self.mode = mode
        logger.info(f"Gateway traffic limiter mode switched to: {mode.value}")

    def update_config(
        self,
        mode: Optional[str] = None,
        token_capacity: Optional[float] = None,
        token_refill_rate: Optional[float] = None,
        leaky_capacity: Optional[int] = None,
        leaky_drain_rate: Optional[float] = None,
    ) -> Dict[str, Any]:
        if mode:
            mode_upper = mode.upper().strip()
            if mode_upper in LimiterMode.__members__:
                self.set_mode(LimiterMode(mode_upper))
            else:
                raise ValueError(f"Invalid mode '{mode}'. Choose from: {[m.value for m in LimiterMode]}")

        if token_capacity is not None:
            self.token_limiter.capacity = float(token_capacity)
            for b in self.token_limiter.buckets.values():
                b.capacity = float(token_capacity)
        if token_refill_rate is not None:
            self.token_limiter.refill_rate = float(token_refill_rate)
            for b in self.token_limiter.buckets.values():
                b.refill_rate = float(token_refill_rate)

        if leaky_capacity is not None:
            self.leaky_shaper.queue_capacity = int(leaky_capacity)
        if leaky_drain_rate is not None:
            self.leaky_shaper.drain_rate = float(leaky_drain_rate)
            if self.leaky_shaper._wake_event is not None:
                self.leaky_shaper._wake_event.set()

        return self.get_full_status()

    def get_full_status(self, client_id: Optional[str] = None) -> Dict[str, Any]:
        avg_lat, p95_lat = self.get_latency_stats()
        return {
            "mode": self.mode.value,
            "token_bucket": self.token_limiter.get_stats(client_id),
            "leaky_bucket": self.leaky_shaper.get_stats(),
            "common": {
                "total_requests": self.total_requests,
                "accepted_requests": self.accepted_requests,
                "throttled_requests": self.throttled_requests,
                "server_failures": self.server_failures,
                "average_latency_ms": avg_lat,
                "p95_latency_ms": p95_lat,
            },
        }

    def reset_all(self) -> None:
        self.token_limiter.reset()
        self.leaky_shaper.reset()
        self.idempotency.clear()
        self.total_requests = 0
        self.accepted_requests = 0
        self.throttled_requests = 0
        self.server_failures = 0
        self.latency_samples.clear()
        self.traffic_events.clear()


traffic_coordinator = GatewayTrafficCoordinator()
