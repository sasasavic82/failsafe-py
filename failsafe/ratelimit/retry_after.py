"""
Retry-After calculation strategies for rate limiting

Implements various strategies for calculating how long a client should wait
before retrying when rate limited.
"""

import math
import random
import statistics
import time
from abc import ABC, abstractmethod
from collections import deque
from enum import Enum
from typing import Optional, Dict


class RetryAfterStrategy(str, Enum):
    """Available retry-after calculation strategies"""
    BACKPRESSURE = "backpressure"      # Hybrid P95 + Gradient backpressure (DEFAULT)
    FIXED = "fixed"                    # Wait until next token available
    ADAPTIVE = "adaptive"              # Alias for utilization
    UTILIZATION = "utilization"        # Based on bucket fill level (prevents depletion)
    JITTERED = "jittered"              # Fixed + random jitter (prevents thundering herd)
    EXPONENTIAL = "exponential"        # Exponential backoff for repeated violations
    PROPORTIONAL = "proportional"      # Proportional to remaining capacity


class RetryAfterCalculator(ABC):
    """Base class for retry-after calculators"""
    
    @abstractmethod
    def calculate(
        self,
        current_tokens: float,
        bucket_size: float,
        token_rate: float,  # tokens per second
        time_until_next: float,  # seconds until next token
        rejection_count: int = 0,  # how many times this client was rejected
        client_id: Optional[str] = None,  # optional client identifier
    ) -> float:
        """
        Calculate retry-after time
        
        Returns:
            Milliseconds to wait before retrying
        """
        pass


class ClientBackpressureState:
    """Per-client backpressure tracking state"""
    
    def __init__(self, window_size: int = 100):
        self.recent_latencies = deque(maxlen=window_size)
        self.historical_latencies = deque(maxlen=5000)
        self.last_access = time.time()
    
    def record_latency(self, latency: float):
        """Record a latency measurement for this client"""
        self.recent_latencies.append(latency)
        self.historical_latencies.append(latency)
        self.last_access = time.time()
    
    def is_stale(self, max_age: float = 3600) -> bool:
        """Check if this client state is stale (unused for max_age seconds)"""
        return (time.time() - self.last_access) > max_age


class BackpressureCalculator(RetryAfterCalculator):
    """
    Hybrid Backpressure strategy: Combines P95 violation detection with latency gradient
    
    This is an adaptive system that calculates backpressure from two independent dimensions:
    1. Service Quality (P95 Violation): Ensures service never normalizes poor performance
    2. Queue Congestion (Latency Gradient): Leading indicator of resource saturation
    
    Final backpressure = max(BP_P95, BP_Gradient)
    
    The backpressure score (0.0 to 1.0) is then used to calculate Retry-After with jitter.
    
    Supports per-client tracking when client_id is provided.
    """
    
    def __init__(
        self,
        window_size: int = 100,
        p95_baseline: float = 1.0,  # 200ms healthy P95 SLO
        min_latency: float = 0.05,  # 50ms minimum processing time
        min_retry_delay: float = 0.001,  # Base retry delay in seconds
        max_retry_penalty: float = 2.0,  # Max additional penalty in seconds
        gradient_sensitivity: float = 10.0,  # How quickly gradient responds (excess_ratio divisor)
    ):
        self.window_size = window_size
        self.p95_baseline = p95_baseline
        self.min_latency = min_latency
        self.min_retry_delay = min_retry_delay
        self.max_retry_penalty = max_retry_penalty
        self.gradient_sensitivity = gradient_sensitivity
        
        # Global sliding window for recent latencies (used when no client_id)
        self.recent_latencies = deque(maxlen=window_size)
        
        # Historical data for slow baseline updates
        self.historical_latencies = deque(maxlen=5000)
        
        # Per-client state tracking (automatically used when client_id is provided)
        self._client_states: Dict[str, ClientBackpressureState] = {}
        self._last_cleanup = time.time()
        
        # Pre-computed exponential curve for P95 violations
        self.stress_lookup = self._generate_exponential_curve(window_size)
    
    def _generate_exponential_curve(self, size: int) -> list:
        """Pre-compute exponential (cubic) curve for P95 backpressure"""
        curve = []
        for i in range(size + 1):
            x = i / size
            # y = x^3: Gentle rise, then steep escalation near saturation
            y = math.pow(x, 3)
            curve.append(min(y, 1.0))
        return curve
    
    def _cleanup_stale_clients(self):
        """Remove stale client states to prevent memory leaks"""
        now = time.time()
        if now - self._last_cleanup < 300:  # Cleanup every 5 minutes
            return
        
        stale_clients = [
            client_id for client_id, state in self._client_states.items()
            if state.is_stale()
        ]
        for client_id in stale_clients:
            del self._client_states[client_id]
        
        self._last_cleanup = now
    
    def _get_client_state(self, client_id: Optional[str]) -> Optional[ClientBackpressureState]:
        """Get or create client state if client_id is provided"""
        if client_id is None:
            return None
        
        if client_id not in self._client_states:
            self._client_states[client_id] = ClientBackpressureState(self.window_size)
        
        return self._client_states[client_id]
    
    def _update_baseline(self):
        """Recalculate baseline P95 infrequently to prevent adaptation during stress"""
        if len(self.historical_latencies) > 50 and random.random() < 0.1:
            try:
                # Update P95 only 10% of the time to keep baseline frozen
                p95 = statistics.quantiles(self.historical_latencies, n=20)[18]
                # Only allow baseline to increase slowly, clamped
                # self.p95_baseline = min(p95, self.p95_baseline * 1.05)
                self.p95_baseline = self.p95_baseline * 0.95 + p95 * 0.05
            except (statistics.StatisticsError, IndexError):
                pass
    
    def _calculate_bp_p95(self, latencies: deque) -> float:
        """Component A: Backpressure from P95 Violation"""
        if not latencies:
            return 0.0
        
        # Count requests exceeding the healthy P95 baseline
        outlier_count = sum(1 for t in latencies if t > self.p95_baseline)
        
        # Map to exponential curve
        return self.stress_lookup[min(outlier_count, len(self.stress_lookup) - 1)]
    
    def _calculate_bp_gradient(self, latencies: deque) -> float:
        """Component B: Backpressure from Latency Gradient (Queue Congestion)"""
        if len(latencies) < 5:
            return 0.0
        
        # Short-term average latency
        st_avg = statistics.mean(latencies)
        lt_min = self.min_latency
        
        # No queuing if current average <= minimum
        if st_avg <= lt_min:
            return 0.0
        
        # Calculate excess ratio: how much current avg exceeds bare minimum
        excess_ratio = (st_avg - lt_min) / lt_min
        
        # Map to backpressure (tunable sensitivity)
        bp_gradient = min(excess_ratio / self.gradient_sensitivity, 1.0)
        
        return bp_gradient
    
    def record_latency(self, latency_seconds: float, client_id: Optional[str] = None):
        """
        Record a request latency for backpressure calculation
        
        Call this after each request completes with its duration in seconds.
        """
        # Record in global state
        self.recent_latencies.append(latency_seconds)
        self.historical_latencies.append(latency_seconds)
        self._update_baseline()
        
        # Record in per-client state if enabled
        client_state = self._get_client_state(client_id)
        if client_state:
            client_state.record_latency(latency_seconds)
        
        # Periodic cleanup
        self._cleanup_stale_clients()
    
    def calculate(
        self,
        current_tokens: float,
        bucket_size: float,
        token_rate: float,
        time_until_next: float,
        rejection_count: int = 0,
        client_id: Optional[str] = None,
    ) -> float:
        """
        Calculate retry-after based on hybrid backpressure
        
        Returns: milliseconds to wait
        """
        # Get appropriate latency data (per-client or global)
        client_state = self._get_client_state(client_id)
        latencies = client_state.recent_latencies if client_state else self.recent_latencies
        
        # Calculate both backpressure components
        bp_p95 = self._calculate_bp_p95(latencies)
        bp_gradient = self._calculate_bp_gradient(latencies)
        
        # Final backpressure is the maximum (worst case)
        bp_final = max(bp_p95, bp_gradient)

        if bp_final < 0.01:  # Essentially zero
            return max(time_until_next * 1000, 10)  # At least 10ms, or time to next token
        
        # Calculate retry delay with jitter
        retry_base = self.min_retry_delay
        added_penalty = self.max_retry_penalty * bp_final
        
        # Add jitter to prevent thundering herd
        jitter = random.uniform(0.8, 1.2)
        retry_seconds = (retry_base + added_penalty) * jitter
        
        return retry_seconds * 1000  # Convert to milliseconds
    
    def get_backpressure_header(self, client_id: Optional[str] = None) -> float:
        """
        Get current backpressure score for X-Backpressure header
        
        Returns: Backpressure score from 0.0 to 1.0
        """
        client_state = self._get_client_state(client_id)
        latencies = client_state.recent_latencies if client_state else self.recent_latencies
        
        bp_p95 = self._calculate_bp_p95(latencies)
        bp_gradient = self._calculate_bp_gradient(latencies)
        return max(bp_p95, bp_gradient)


class FixedCalculator(RetryAfterCalculator):
    """
    Fixed strategy: Wait exactly until next token becomes available
    """
    
    def calculate(
        self,
        current_tokens: float,
        bucket_size: float,
        token_rate: float,
        time_until_next: float,
        rejection_count: int = 0,
        client_id: Optional[str] = None,
    ) -> float:
        return time_until_next * 1000


class UtilizationCalculator(RetryAfterCalculator):
    """
    Utilization/Adaptive strategy: Adjust wait time based on bucket fill level
    """
    
    def __init__(
        self,
        aggressive_threshold: float = 0.2,
        warning_threshold: float = 0.5,
        normal_threshold: float = 0.8,
        aggressive_multiplier: float = 4.0,
        warning_multiplier: float = 2.0,
    ):
        self.aggressive_threshold = aggressive_threshold
        self.warning_threshold = warning_threshold
        self.normal_threshold = normal_threshold
        self.aggressive_multiplier = aggressive_multiplier
        self.warning_multiplier = warning_multiplier
    
    def calculate(
        self,
        current_tokens: float,
        bucket_size: float,
        token_rate: float,
        time_until_next: float,
        rejection_count: int = 0,
        client_id: Optional[str] = None,
    ) -> float:
        if bucket_size <= 0:
            return time_until_next * 1000
        
        utilization = current_tokens / bucket_size
        base_wait_ms = time_until_next * 1000
        
        if utilization >= self.normal_threshold:
            return 0
        elif utilization >= self.warning_threshold:
            return base_wait_ms
        elif utilization >= self.aggressive_threshold:
            return base_wait_ms * self.warning_multiplier
        else:
            return base_wait_ms * self.aggressive_multiplier


class JitteredCalculator(RetryAfterCalculator):
    """
    Jittered strategy: Add random jitter to prevent thundering herd
    """
    
    def __init__(
        self,
        jitter_range_ms: float = 1000,
        jitter_type: str = "full",
    ):
        self.jitter_range_ms = jitter_range_ms
        self.jitter_type = jitter_type
    
    def calculate(
        self,
        current_tokens: float,
        bucket_size: float,
        token_rate: float,
        time_until_next: float,
        rejection_count: int = 0,
        client_id: Optional[str] = None,
    ) -> float:
        base_wait_ms = time_until_next * 1000
        
        if self.jitter_type == "full":
            jitter = random.uniform(0, self.jitter_range_ms)
        else:
            jitter = (self.jitter_range_ms / 2) + random.uniform(0, self.jitter_range_ms / 2)
        
        return base_wait_ms + jitter


class ExponentialCalculator(RetryAfterCalculator):
    """
    Exponential backoff: Increase wait time for repeated violations
    """
    
    def __init__(
        self,
        backoff_factor: float = 2.0,
        max_backoff_ms: float = 60000,
    ):
        self.backoff_factor = backoff_factor
        self.max_backoff_ms = max_backoff_ms
        # Per-client rejection tracking
        self._client_rejections: Dict[str, int] = {}
        self._last_cleanup = time.time()
    
    def _cleanup_stale_clients(self):
        """Cleanup old client rejection counts"""
        now = time.time()
        if now - self._last_cleanup > 300:  # Every 5 minutes
            self._client_rejections.clear()
            self._last_cleanup = now
    
    def calculate(
        self,
        current_tokens: float,
        bucket_size: float,
        token_rate: float,
        time_until_next: float,
        rejection_count: int = 0,
        client_id: Optional[str] = None,
    ) -> float:
        base_wait_ms = time_until_next * 1000
        
        # Use per-client rejection count if available
        if client_id:
            self._client_rejections[client_id] = self._client_rejections.get(client_id, 0) + 1
            rejection_count = self._client_rejections[client_id]
            self._cleanup_stale_clients()
        
        # Apply exponential backoff
        multiplier = self.backoff_factor ** rejection_count
        wait_ms = base_wait_ms * multiplier
        
        return min(wait_ms, self.max_backoff_ms)


class ProportionalCalculator(RetryAfterCalculator):
    """
    Proportional strategy: Scale wait time based on remaining capacity
    """
    
    def __init__(
        self,
        max_multiplier: float = 3.0,
    ):
        self.max_multiplier = max_multiplier
    
    def calculate(
        self,
        current_tokens: float,
        bucket_size: float,
        token_rate: float,
        time_until_next: float,
        rejection_count: int = 0,
        client_id: Optional[str] = None,
    ) -> float:
        base_wait_ms = time_until_next * 1000
        
        if bucket_size <= 0:
            return base_wait_ms
        
        utilization = current_tokens / bucket_size
        multiplier = 1.0 + ((1.0 - utilization) * (self.max_multiplier - 1.0))
        
        return base_wait_ms * multiplier


def create_calculator(strategy: RetryAfterStrategy, **kwargs) -> RetryAfterCalculator:
    """
    Factory function to create retry-after calculators
    
    Note: enable_per_client_tracking is not needed here - calculators automatically
    use per-client state when client_id is provided to calculate()
    """
    
    # Remove enable_per_client_tracking if present (it's not used by calculators)
    kwargs_filtered = {k: v for k, v in kwargs.items() if k != 'enable_per_client_tracking'}
    
    if strategy == RetryAfterStrategy.BACKPRESSURE:
        return BackpressureCalculator(**kwargs_filtered)
    
    elif strategy in (RetryAfterStrategy.ADAPTIVE, RetryAfterStrategy.UTILIZATION):
        return UtilizationCalculator(**kwargs_filtered)
    
    elif strategy == RetryAfterStrategy.FIXED:
        return FixedCalculator()
    
    elif strategy == RetryAfterStrategy.JITTERED:
        return JitteredCalculator(**kwargs_filtered)
    
    elif strategy == RetryAfterStrategy.EXPONENTIAL:
        return ExponentialCalculator(**kwargs_filtered)
    
    elif strategy == RetryAfterStrategy.PROPORTIONAL:
        return ProportionalCalculator(**kwargs_filtered)
    
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


# Default recommended strategy
DEFAULT_CALCULATOR = BackpressureCalculator()