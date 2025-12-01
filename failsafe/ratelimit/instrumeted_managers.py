"""
Instrumented rate limiter managers that track metrics for control plane
"""

from typing import Optional

from failsafe.ratelimit.managers import TokenBucketLimiter
from failsafe.ratelimit.exceptions import RateLimitExceeded
from failsafe.ratelimit.retry_after import (
    RetryAfterStrategy,
    RetryAfterCalculator,
)

from prometheus_client import Counter, Gauge

# Try to import metrics collector
try:
    from failsafe.controller import _METRICS
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    _METRICS = None

# Prometheus metrics (do not replace controller metrics; add alongside)
_PR_REQUESTS = Counter(
    "failsafe_ratelimit_requests_total",
    "Total successful rate-limited requests",
    labelnames=["pattern", "client"],
)

_PR_THROTTLED = Counter(
    "failsafe_ratelimit_throttled_total",
    "Total throttled (RateLimitExceeded) events",
    labelnames=["pattern", "client"],
)

_PR_REJECTIONS = Counter(
    "failsafe_ratelimit_rejections_total",
    "Total rejections due to rate limiting",
    labelnames=["pattern", "client"],
)

_PR_TOKENS_AVAILABLE = Gauge(
    "failsafe_ratelimit_tokens_available",
    "Current tokens available in the bucket",
    labelnames=["pattern"],
)

_PR_BACKPRESSURE = Gauge(
    "failsafe_ratelimit_backpressure",
    "Current backpressure score (if available)",
    labelnames=["pattern", "client"],
)

class InstrumentedTokenBucketLimiter(TokenBucketLimiter):
    """
    TokenBucketLimiter with automatic metrics tracking.
    This is an optional wrapper - the base TokenBucketLimiter
    works fine without it.
    """
    
    def __init__(
        self,
        max_executions: float,
        per_time_secs: float,
        bucket_size: Optional[float] = None,
        pattern_name: Optional[str] = None,
        retry_after_strategy: RetryAfterStrategy = (
            RetryAfterStrategy.BACKPRESSURE
        ),
        retry_after_calculator: Optional[RetryAfterCalculator] = None,
        enable_per_client_tracking: bool = False,
        **calculator_kwargs,
    ) -> None:
        # Pass all parameters to parent (handles calculator_kwargs properly)
        super().__init__(
            max_executions=max_executions,
            per_time_secs=per_time_secs,
            bucket_size=bucket_size,
            retry_after_strategy=retry_after_strategy,
            retry_after_calculator=retry_after_calculator,
            enable_per_client_tracking=enable_per_client_tracking,
            **calculator_kwargs,
        )
        self._pattern_name = pattern_name or "ratelimit"
    
    async def acquire(self, client_id: Optional[str] = None) -> None:
        """
        Acquire a token and track metrics
        
        Args:
            client_id: Optional client identifier for per-client tracking
        """
        try:
            await super().acquire(client_id=client_id)
            
            # Track successful acquisition
            if METRICS_AVAILABLE and _METRICS:
                await _METRICS.increment(
                    "ratelimit", self._pattern_name, "requests"
                )
                await _METRICS.set_gauge(
                    "ratelimit",
                    self._pattern_name,
                    "tokens_available",
                    self.current_tokens
                )
                
                # Track backpressure if available
                from failsafe.ratelimit.retry_after import (
                    BackpressureCalculator,
                )
                if isinstance(
                    self.retry_after_calculator, BackpressureCalculator
                ):
                    bp_score = (
                        self.retry_after_calculator.get_backpressure_header(
                            client_id=client_id
                        )
                    )
                    await _METRICS.set_gauge(
                        "ratelimit",
                        self._pattern_name,
                        "backpressure",
                        bp_score
                    )

            # Prometheus metrics in parallel to controller metrics
            client_label = client_id or (
                "client" if self._enable_per_client_tracking else "global"
            )
            _PR_REQUESTS.labels(self._pattern_name, client_label).inc()
            _PR_TOKENS_AVAILABLE.labels(self._pattern_name).set(
                self.current_tokens
            )
            from failsafe.ratelimit.retry_after import (
                BackpressureCalculator as _BP,
            )
            if isinstance(self.retry_after_calculator, _BP):
                bp_score = self.retry_after_calculator.get_backpressure_header(
                    client_id=client_id
                )
                _PR_BACKPRESSURE.labels(
                    self._pattern_name, client_label
                ).set(bp_score)
        
        except RateLimitExceeded:
            # Track throttling
            if METRICS_AVAILABLE and _METRICS:
                await _METRICS.increment(
                    "ratelimit", self._pattern_name, "throttled"
                )
                await _METRICS.increment(
                    "ratelimit", self._pattern_name, "rejections"
                )
                
                # Track backpressure on rejections
                from failsafe.ratelimit.retry_after import (
                    BackpressureCalculator,
                )
                if isinstance(
                    self.retry_after_calculator, BackpressureCalculator
                ):
                    bp_score = (
                        self.retry_after_calculator.get_backpressure_header(
                            client_id=client_id
                        )
                    )
                    await _METRICS.set_gauge(
                        "ratelimit",
                        self._pattern_name,
                        "backpressure",
                        bp_score
                    )

            # Prometheus metrics in parallel to controller metrics
            client_label = client_id or (
                "client" if self._enable_per_client_tracking else "global"
            )
            _PR_THROTTLED.labels(self._pattern_name, client_label).inc()
            _PR_REJECTIONS.labels(self._pattern_name, client_label).inc()
            from failsafe.ratelimit.retry_after import (
                BackpressureCalculator as _BP2,
            )
            if isinstance(self.retry_after_calculator, _BP2):
                bp_score = self.retry_after_calculator.get_backpressure_header(
                    client_id=client_id
                )
                _PR_BACKPRESSURE.labels(
                    self._pattern_name, client_label
                ).set(bp_score)
            
            raise
