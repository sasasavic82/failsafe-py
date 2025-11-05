"""
Instrumented rate limiter managers that track metrics for control plane
"""

from typing import Optional

from failsafe.ratelimit.managers import TokenBucketLimiter
from failsafe.ratelimit.exceptions import RateLimitExceeded

# Try to import metrics collector
try:
    from failsafe.controller import _METRICS
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    _METRICS = None


class InstrumentedTokenBucketLimiter(TokenBucketLimiter):
    """
    TokenBucketLimiter with automatic metrics tracking.
    This is an optional wrapper - the base TokenBucketLimiter works fine without it.
    """
    
    def __init__(
        self,
        max_executions: float,
        per_time_secs: float,
        bucket_size: Optional[float] = None,
        pattern_name: Optional[str] = None,
    ) -> None:
        super().__init__(max_executions, per_time_secs, bucket_size)
        self._pattern_name = pattern_name or "ratelimit"
    
    async def acquire(self) -> None:
        """
        Acquire a token and track metrics
        """
        try:
            await super().acquire()
            
            # Track successful acquisition
            if METRICS_AVAILABLE and _METRICS:
                await _METRICS.increment("ratelimit", self._pattern_name, "requests")
                await _METRICS.set_gauge(
                    "ratelimit",
                    self._pattern_name,
                    "tokens_available",
                    self.current_tokens
                )
        
        except RateLimitExceeded:
            # Track throttling
            if METRICS_AVAILABLE and _METRICS:
                await _METRICS.increment("ratelimit", self._pattern_name, "throttled")
                await _METRICS.increment("ratelimit", self._pattern_name, "rejections")
            
            raise