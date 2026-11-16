import time
import asyncio
from typing import Dict, Tuple, Optional, Any
import logging

logger = logging.getLogger("gateway.ratelimit")


class TokenBucket:
    """
    Standard Token Bucket rate limiter algorithm.
    Allows bursts up to capacity, refills tokens monotonically at refill_rate (tokens/sec).
    """

    def __init__(self, capacity: float = 60.0, refill_rate: float = 20.0):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_refill = time.perf_counter()

    def _refill(self, now: float) -> None:
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + (elapsed * self.refill_rate))
            self.last_refill = now

    def consume(self, cost: float = 1.0) -> Tuple[bool, float, float]:
        """
        Attempts to consume tokens.
        Returns:
            (allowed: bool, remaining_tokens: float, retry_after_sec: float)
        """
        now = time.perf_counter()
        self._refill(now)

        if self.tokens >= cost:
            self.tokens -= cost
            retry_after = 0.0
            return True, self.tokens, retry_after
        else:
            needed = cost - self.tokens
            retry_after = round(needed / self.refill_rate, 2) if self.refill_rate > 0 else 1.0
            return False, self.tokens, retry_after


class LeakyBucket:
    """
    Leaky Bucket traffic shaper algorithm.
    Smooths bursty traffic into a steady egress rate.
    Rejects requests when queue depth exceeds max_queue_depth.
    """

    def __init__(self, leak_rate: float = 25.0, max_queue_depth: int = 15):
        self.leak_rate = float(leak_rate)  # requests per second
        self.max_queue_depth = int(max_queue_depth)
        self.current_water_level = 0.0
        self.last_leak = time.perf_counter()

    def _leak(self, now: float) -> None:
        elapsed = now - self.last_leak
        if elapsed > 0:
            leaked = elapsed * self.leak_rate
            self.current_water_level = max(0.0, self.current_water_level - leaked)
            self.last_leak = now

    def push(self) -> Tuple[bool, float, float]:
        """
        Attempts to add a request to the leaky bucket.
        Returns:
            (allowed: bool, current_level: float, queue_delay_sec: float)
        """
        now = time.perf_counter()
        self._leak(now)

        if self.current_water_level + 1.0 <= self.max_queue_depth:
            # Accepted
            self.current_water_level += 1.0
            queue_delay = round(self.current_water_level / self.leak_rate, 3)
            return True, self.current_water_level, queue_delay
        else:
            # Overflow
            queue_delay = round((self.current_water_level - self.max_queue_depth + 1.0) / self.leak_rate, 3)
            return False, self.current_water_level, queue_delay


class GatewayTrafficController:
    """
    Coordinates Token Bucket rate limiting and Leaky Bucket traffic shaping
    for the FailoverLab Gateway across clients and routes.
    """

    def __init__(
        self,
        token_bucket_capacity: float = 50.0,
        token_refill_rate: float = 25.0,
        enable_leaky_shaper: bool = False,
        leaky_bucket_capacity: int = 20,
        leaky_leak_rate: float = 30.0,
    ):
        self.token_capacity = token_bucket_capacity
        self.refill_rate = token_refill_rate
        self.enable_shaper = enable_leaky_shaper
        self.leaky_capacity = leaky_bucket_capacity
        self.leak_rate = leaky_leak_rate

        self.buckets: Dict[str, TokenBucket] = {}
        self.shapers: Dict[str, LeakyBucket] = {}
        self.total_throttled_count = 0
        self.total_shaped_count = 0

    def _get_bucket(self, client_key: str) -> TokenBucket:
        if client_key not in self.buckets:
            self.buckets[client_key] = TokenBucket(
                capacity=self.token_capacity,
                refill_rate=self.refill_rate,
            )
        return self.buckets[client_key]

    def _get_shaper(self, client_key: str) -> LeakyBucket:
        if client_key not in self.shapers:
            self.shapers[client_key] = LeakyBucket(
                leak_rate=self.leak_rate,
                max_queue_depth=self.leaky_capacity,
            )
        return self.shapers[client_key]

    def check_rate_limit(self, client_key: str = "global") -> Tuple[bool, float, float]:
        """
        Evaluates Token Bucket rate limit for a client key.
        Returns: (allowed, remaining_tokens, retry_after_sec)
        """
        bucket = self._get_bucket(client_key)
        allowed, remaining, retry_after = bucket.consume(1.0)
        if not allowed:
            self.total_throttled_count += 1
            logger.warning(
                f"[RATE_LIMITED] Client '{client_key}' exceeded Token Bucket rate limit. Retry-After: {retry_after}s"
            )
        return allowed, remaining, retry_after

    async def shape_traffic(self, client_key: str = "global") -> Tuple[bool, float]:
        """
        Evaluates Leaky Bucket traffic shaping.
        If enabled and queued, sleeps briefly to shape traffic into smooth egress.
        Returns: (allowed, delay_applied_sec)
        """
        if not self.enable_shaper:
            return True, 0.0

        shaper = self._get_shaper(client_key)
        allowed, level, queue_delay = shaper.push()
        if not allowed:
            self.total_throttled_count += 1
            return False, 0.0

        if queue_delay > 0:
            self.total_shaped_count += 1
            await asyncio.sleep(min(queue_delay, 0.1))  # Cap smoothing delay to 100ms in simulation
        return True, queue_delay

    def update_config(
        self,
        token_capacity: Optional[float] = None,
        refill_rate: Optional[float] = None,
        enable_shaper: Optional[bool] = None,
        leaky_capacity: Optional[int] = None,
        leak_rate: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Dynamically reconfigures rate limiter and shaper parameters."""
        if token_capacity is not None:
            self.token_capacity = token_capacity
            for b in self.buckets.values():
                b.capacity = token_capacity
        if refill_rate is not None:
            self.refill_rate = refill_rate
            for b in self.buckets.values():
                b.refill_rate = refill_rate
        if enable_shaper is not None:
            self.enable_shaper = enable_shaper
        if leaky_capacity is not None:
            self.leaky_capacity = leaky_capacity
            for s in self.shapers.values():
                s.max_queue_depth = leaky_capacity
        if leak_rate is not None:
            self.leak_rate = leak_rate
            for s in self.shapers.values():
                s.leak_rate = leak_rate

        return self.get_stats()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "token_capacity": self.token_capacity,
            "refill_rate_rps": self.refill_rate,
            "enable_shaper": self.enable_shaper,
            "leaky_capacity": self.leaky_capacity,
            "leak_rate_rps": self.leak_rate,
            "total_throttled_requests": self.total_throttled_count,
            "total_shaped_requests": self.total_shaped_count,
            "active_client_buckets": len(self.buckets),
        }


gateway_traffic_controller = GatewayTrafficController()
