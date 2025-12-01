"""
Instrumented rate limiter managers that track metrics for control plane and Prometheus.

Provides comprehensive observability for rate limiting behavior including:
- Request success/failure rates
- Latency distributions (P50, P95, P99)
- Token bucket utilization
- Backpressure scores and components
- Retry-after distributions
- Client-level tracking
"""

import time
from typing import Optional

from failsafe.ratelimit.managers import TokenBucketLimiter
from failsafe.ratelimit.exceptions import RateLimitExceeded
from failsafe.ratelimit.retry_after import (
    RetryAfterStrategy,
    RetryAfterCalculator,
    BackpressureCalculator,
)

from prometheus_client import Counter, Gauge, Histogram, Summary, Info

# Try to import metrics collector
try:
    from failsafe.controller import _METRICS
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    _METRICS = None


# =============================================================================
# PROMETHEUS METRICS DEFINITIONS
# =============================================================================

# --- Info Metric ---
RATELIMIT_INFO = Info(
    "failsafe_ratelimit",
    "Rate limiter configuration information",
    labelnames=["pattern"],
)

# --- Counters ---
REQUESTS_TOTAL = Counter(
    "failsafe_ratelimit_requests_total",
    "Total requests processed by the rate limiter",
    labelnames=["pattern", "client", "status"],  # status: allowed, rejected
)

TOKENS_CONSUMED_TOTAL = Counter(
    "failsafe_ratelimit_tokens_consumed_total",
    "Total tokens consumed from the bucket",
    labelnames=["pattern"],
)

REJECTIONS_TOTAL = Counter(
    "failsafe_ratelimit_rejections_total",
    "Total requests rejected due to rate limiting",
    labelnames=["pattern", "client", "reason"],  # reason: empty_bucket, backpressure
)

RETRIES_TOTAL = Counter(
    "failsafe_ratelimit_client_retries_total",
    "Total retry attempts by clients (tracked via rejection_count)",
    labelnames=["pattern", "client"],
)

# --- Gauges ---
TOKENS_AVAILABLE = Gauge(
    "failsafe_ratelimit_tokens_available",
    "Current tokens available in the bucket",
    labelnames=["pattern"],
)

TOKENS_MAX = Gauge(
    "failsafe_ratelimit_tokens_max",
    "Maximum bucket size (capacity)",
    labelnames=["pattern"],
)

TOKEN_REFILL_RATE = Gauge(
    "failsafe_ratelimit_token_refill_rate",
    "Token refill rate (tokens per second)",
    labelnames=["pattern"],
)

BUCKET_UTILIZATION = Gauge(
    "failsafe_ratelimit_bucket_utilization_ratio",
    "Bucket utilization ratio (0.0 = empty, 1.0 = full)",
    labelnames=["pattern"],
)

BACKPRESSURE_SCORE = Gauge(
    "failsafe_ratelimit_backpressure_score",
    "Current combined backpressure score (0.0 to 1.0)",
    labelnames=["pattern", "client"],
)

BACKPRESSURE_P95 = Gauge(
    "failsafe_ratelimit_backpressure_p95",
    "P95 violation component of backpressure",
    labelnames=["pattern", "client"],
)

BACKPRESSURE_GRADIENT = Gauge(
    "failsafe_ratelimit_backpressure_gradient",
    "Latency gradient component of backpressure",
    labelnames=["pattern", "client"],
)

ACTIVE_CLIENTS = Gauge(
    "failsafe_ratelimit_active_clients",
    "Number of active clients being tracked",
    labelnames=["pattern"],
)

LIMITER_ENABLED = Gauge(
    "failsafe_ratelimit_enabled",
    "Whether the rate limiter is enabled (1) or disabled (0)",
    labelnames=["pattern"],
)

# --- Histograms ---
# Latency buckets optimized for API responses (in seconds)
LATENCY_BUCKETS = (
    0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5,
    0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0
)

REQUEST_LATENCY = Histogram(
    "failsafe_ratelimit_request_latency_seconds",
    "Request latency in seconds (for successful requests)",
    labelnames=["pattern", "client"],
    buckets=LATENCY_BUCKETS,
)

# Retry-after buckets (in seconds)
RETRY_AFTER_BUCKETS = (
    0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0, 60.0
)

RETRY_AFTER_SECONDS = Histogram(
    "failsafe_ratelimit_retry_after_seconds",
    "Retry-After values returned to clients (in seconds)",
    labelnames=["pattern", "client"],
    buckets=RETRY_AFTER_BUCKETS,
)

TIME_UNTIL_TOKEN = Histogram(
    "failsafe_ratelimit_time_until_token_seconds",
    "Time until next token becomes available when bucket is empty",
    labelnames=["pattern"],
    buckets=RETRY_AFTER_BUCKETS,
)

# --- Summaries (for precise percentiles) ---
LATENCY_SUMMARY = Summary(
    "failsafe_ratelimit_latency_summary_seconds",
    "Request latency summary with quantiles",
    labelnames=["pattern", "client"],
)

BACKPRESSURE_LATENCY_RECORDED = Histogram(
    "failsafe_ratelimit_recorded_latency_seconds",
    "Latencies recorded by the backpressure calculator",
    labelnames=["pattern", "client"],
    buckets=LATENCY_BUCKETS,
)


# =============================================================================
# INSTRUMENTED TOKEN BUCKET LIMITER
# =============================================================================

class InstrumentedTokenBucketLimiter(TokenBucketLimiter):
    """
    TokenBucketLimiter with comprehensive Prometheus metrics.
    
    Tracks:
    - Request success/rejection rates
    - Token bucket state and utilization
    - Latency distributions
    - Backpressure scores and components
    - Retry-after distributions
    - Per-client metrics when enabled
    """
    
    def __init__(
        self,
        max_executions: float,
        per_time_secs: float,
        bucket_size: Optional[float] = None,
        pattern_name: Optional[str] = None,
        retry_after_strategy: RetryAfterStrategy = RetryAfterStrategy.BACKPRESSURE,
        retry_after_calculator: Optional[RetryAfterCalculator] = None,
        enable_per_client_tracking: bool = False,
        **calculator_kwargs,
    ) -> None:
        super().__init__(
            max_executions=max_executions,
            per_time_secs=per_time_secs,
            bucket_size=bucket_size,
            retry_after_strategy=retry_after_strategy,
            retry_after_calculator=retry_after_calculator,
            enable_per_client_tracking=enable_per_client_tracking,
            **calculator_kwargs,
        )
        self._pattern_name = pattern_name or "default"
        
        # Set static configuration metrics
        self._init_config_metrics()
    
    def _init_config_metrics(self):
        """Initialize configuration-based metrics"""
        # Set info metric
        RATELIMIT_INFO.labels(pattern=self._pattern_name).info({
            "max_executions": str(self._max_executions),
            "per_time_secs": str(self._per_time_secs),
            "bucket_size": str(self._bucket_size),
            "strategy": self._retry_after_calculator.__class__.__name__,
            "per_client_tracking": str(self._enable_per_client_tracking),
        })
        
        # Set capacity gauges
        TOKENS_MAX.labels(pattern=self._pattern_name).set(self._bucket_size)
        TOKEN_REFILL_RATE.labels(pattern=self._pattern_name).set(
            self._max_executions / self._per_time_secs
        )
        LIMITER_ENABLED.labels(pattern=self._pattern_name).set(1 if self._enabled else 0)
    
    def _get_client_label(self, client_id: Optional[str]) -> str:
        """Get client label for metrics"""
        if client_id:
            return client_id
        return "global" if not self._enable_per_client_tracking else "unknown"
    
    def _update_bucket_metrics(self):
        """Update token bucket state metrics"""
        tokens = self.current_tokens
        TOKENS_AVAILABLE.labels(pattern=self._pattern_name).set(tokens)
        BUCKET_UTILIZATION.labels(pattern=self._pattern_name).set(
            tokens / self._bucket_size if self._bucket_size > 0 else 0
        )
    
    def _update_backpressure_metrics(self, client_id: Optional[str]):
        """Update backpressure-related metrics"""
        client_label = self._get_client_label(client_id)
        
        if isinstance(self._retry_after_calculator, BackpressureCalculator):
            calc = self._retry_after_calculator
            
            # Get client or global latencies
            client_state = calc._get_client_state(client_id)
            latencies = client_state.recent_latencies if client_state else calc.recent_latencies
            
            # Calculate components
            bp_p95 = calc._calculate_bp_p95(latencies)
            bp_gradient = calc._calculate_bp_gradient(latencies)
            bp_combined = max(bp_p95, bp_gradient)
            
            # Set metrics
            BACKPRESSURE_P95.labels(
                pattern=self._pattern_name, client=client_label
            ).set(bp_p95)
            BACKPRESSURE_GRADIENT.labels(
                pattern=self._pattern_name, client=client_label
            ).set(bp_gradient)
            BACKPRESSURE_SCORE.labels(
                pattern=self._pattern_name, client=client_label
            ).set(bp_combined)
        
        # Update active clients count
        if self._enable_per_client_tracking:
            ACTIVE_CLIENTS.labels(pattern=self._pattern_name).set(
                len(self._client_states)
            )
    
    async def acquire(self, client_id: Optional[str] = None) -> None:
        """
        Acquire a token with comprehensive metrics tracking.
        
        Args:
            client_id: Optional client identifier for per-client tracking
        """
        client_label = self._get_client_label(client_id)
        
        # Update enabled status
        LIMITER_ENABLED.labels(pattern=self._pattern_name).set(
            1 if self._enabled else 0
        )
        
        # If disabled, allow through without metrics
        if not self._enabled:
            REQUESTS_TOTAL.labels(
                pattern=self._pattern_name, client=client_label, status="bypassed"
            ).inc()
            return
        
        try:
            await super().acquire(client_id=client_id)
            
            # === SUCCESS METRICS ===
            REQUESTS_TOTAL.labels(
                pattern=self._pattern_name, client=client_label, status="allowed"
            ).inc()
            TOKENS_CONSUMED_TOTAL.labels(pattern=self._pattern_name).inc()
            
            # Update bucket state
            self._update_bucket_metrics()
            
            # Update backpressure metrics
            self._update_backpressure_metrics(client_id)
            
            # Controller metrics
            if METRICS_AVAILABLE and _METRICS:
                await _METRICS.increment("ratelimit", self._pattern_name, "requests")
                await _METRICS.set_gauge(
                    "ratelimit", self._pattern_name, "tokens_available",
                    self.current_tokens
                )
        
        except RateLimitExceeded as exc:
            # === REJECTION METRICS ===
            REQUESTS_TOTAL.labels(
                pattern=self._pattern_name, client=client_label, status="rejected"
            ).inc()
            REJECTIONS_TOTAL.labels(
                pattern=self._pattern_name, client=client_label, reason="empty_bucket"
            ).inc()
            
            # Track retry-after value
            if exc.retry_after_seconds is not None:
                RETRY_AFTER_SECONDS.labels(
                    pattern=self._pattern_name, client=client_label
                ).observe(exc.retry_after_seconds)
            
            # Track time until next token
            import asyncio
            loop = asyncio.get_running_loop()
            now = loop.time()
            time_until_next = max(0, self.bucket._next_replenish_at - now)
            TIME_UNTIL_TOKEN.labels(pattern=self._pattern_name).observe(time_until_next)
            
            # Track client retries
            client_state = self._get_client_state(client_id)
            if client_state and client_state.rejection_count > 1:
                RETRIES_TOTAL.labels(
                    pattern=self._pattern_name, client=client_label
                ).inc()
            
            # Update bucket and backpressure metrics
            self._update_bucket_metrics()
            self._update_backpressure_metrics(client_id)
            
            # Controller metrics
            if METRICS_AVAILABLE and _METRICS:
                await _METRICS.increment("ratelimit", self._pattern_name, "throttled")
                await _METRICS.increment("ratelimit", self._pattern_name, "rejections")
            
            raise
    
    def record_latency(self, latency_seconds: float, client_id: Optional[str] = None):
        """
        Record request latency for metrics and backpressure calculation.
        
        Call this after a successful request completes.
        
        Args:
            latency_seconds: Request duration in seconds
            client_id: Optional client identifier
        """
        client_label = self._get_client_label(client_id)
        
        # Record in Prometheus histograms
        REQUEST_LATENCY.labels(
            pattern=self._pattern_name, client=client_label
        ).observe(latency_seconds)
        
        LATENCY_SUMMARY.labels(
            pattern=self._pattern_name, client=client_label
        ).observe(latency_seconds)
        
        BACKPRESSURE_LATENCY_RECORDED.labels(
            pattern=self._pattern_name, client=client_label
        ).observe(latency_seconds)
        
        # Record in backpressure calculator
        if isinstance(self._retry_after_calculator, BackpressureCalculator):
            self._retry_after_calculator.record_latency(latency_seconds, client_id)
            
            # Update backpressure metrics after recording
            self._update_backpressure_metrics(client_id)
    
    def enable(self):
        """Enable the rate limiter"""
        super().enable()
        LIMITER_ENABLED.labels(pattern=self._pattern_name).set(1)
    
    def disable(self):
        """Disable the rate limiter"""
        super().disable()
        LIMITER_ENABLED.labels(pattern=self._pattern_name).set(0)
    
    def update_config(
        self,
        max_executions: Optional[float] = None,
        per_time_secs: Optional[float] = None,
        bucket_size: Optional[float] = None
    ):
        """Update configuration and refresh metrics"""
        super().update_config(max_executions, per_time_secs, bucket_size)
        self._init_config_metrics()


# =============================================================================
# DECORATOR HELPER FOR LATENCY TRACKING
# =============================================================================

class LatencyTracker:
    """
    Context manager for tracking request latency.
    
    Usage:
        limiter = InstrumentedTokenBucketLimiter(...)
        
        async with LatencyTracker(limiter, client_id="user123"):
            result = await some_operation()
    """
    
    def __init__(
        self,
        limiter: InstrumentedTokenBucketLimiter,
        client_id: Optional[str] = None
    ):
        self.limiter = limiter
        self.client_id = client_id
        self.start_time: Optional[float] = None
    
    async def __aenter__(self):
        self.start_time = time.perf_counter()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            latency = time.perf_counter() - self.start_time
            self.limiter.record_latency(latency, self.client_id)
        return False