"""
Retry-After calculation strategies for rate limiting

Implements various strategies for calculating how long a client should wait
before retrying when rate limited.
"""

import math
import random
import statistics
from abc import ABC, abstractmethod
from collections import deque
from enum import Enum
from typing import Optional


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
    ) -> float:
        """
        Calculate retry-after time
        
        Returns:
            Milliseconds to wait before retrying
        """
        pass


class BackpressureCalculator(RetryAfterCalculator):
    """
    Hybrid Backpressure strategy: Combines P95 violation detection with latency gradient
    
    This is an adaptive system that calculates backpressure from two independent dimensions:
    1. Service Quality (P95 Violation): Ensures service never normalizes poor performance
    2. Queue Congestion (Latency Gradient): Leading indicator of resource saturation
    
    Final backpressure = max(BP_P95, BP_Gradient)
    
    The backpressure score (0.0 to 1.0) is then used to calculate Retry-After with jitter.
    
    Pros:
    - Proactive queue congestion detection (leading indicator)
    - Maintains SLO compliance (never normalizes degradation)
    - Self-regulating under load
    - Prevents thundering herd via jitter
    
    Cons:
    - Requires latency tracking overhead
    - More complex than simple strategies
    """
    
    def __init__(
        self,
        window_size: int = 100,
        p95_baseline: float = 0.2,  # 200ms healthy P95 SLO
        min_latency: float = 0.05,  # 50ms minimum processing time
        min_retry_delay: float = 1.0,  # Base retry delay in seconds
        max_retry_penalty: float = 15.0,  # Max additional penalty in seconds
        gradient_sensitivity: float = 2.0,  # How quickly gradient responds (excess_ratio divisor)
    ):
        self.window_size = window_size
        self.p95_baseline = p95_baseline
        self.min_latency = min_latency
        self.min_retry_delay = min_retry_delay
        self.max_retry_penalty = max_retry_penalty
        self.gradient_sensitivity = gradient_sensitivity
        
        # Sliding window for recent latencies
        self.recent_latencies = deque(maxlen=window_size)
        
        # Historical data for slow baseline updates
        self.historical_latencies = deque(maxlen=5000)
        
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
    
    def _update_baseline(self):
        """Recalculate baseline P95 infrequently to prevent adaptation during stress"""
        if len(self.historical_latencies) > 50 and random.random() < 0.1:
            try:
                # Update P95 only 10% of the time to keep baseline frozen
                p95 = statistics.quantiles(self.historical_latencies, n=20)[18]
                # Only allow baseline to increase slowly, clamped
                self.p95_baseline = min(p95, self.p95_baseline * 1.05)
            except (statistics.StatisticsError, IndexError):
                pass
    
    def _calculate_bp_p95(self) -> float:
        """Component A: Backpressure from P95 Violation"""
        if not self.recent_latencies:
            return 0.0
        
        # Count requests exceeding the healthy P95 baseline
        outlier_count = sum(1 for t in self.recent_latencies if t > self.p95_baseline)
        
        # Map to exponential curve
        return self.stress_lookup[outlier_count]
    
    def _calculate_bp_gradient(self) -> float:
        """Component B: Backpressure from Latency Gradient (Queue Congestion)"""
        if len(self.recent_latencies) < 5:
            return 0.0
        
        # Short-term average latency
        st_avg = statistics.mean(self.recent_latencies)
        lt_min = self.min_latency
        
        # No queuing if current average <= minimum
        if st_avg <= lt_min:
            return 0.0
        
        # Calculate excess ratio: how much current avg exceeds bare minimum
        excess_ratio = (st_avg - lt_min) / lt_min
        
        # Map to backpressure (tunable sensitivity)
        # Default: 200% increase (ratio=2.0) indicates max congestion
        bp_gradient = min(excess_ratio / self.gradient_sensitivity, 1.0)
        
        return bp_gradient
    
    def record_latency(self, latency_seconds: float):
        """
        Record a request latency for backpressure calculation
        
        Call this after each request completes with its duration in seconds.
        """
        self.recent_latencies.append(latency_seconds)
        self.historical_latencies.append(latency_seconds)
        self._update_baseline()
    
    def calculate(
        self,
        current_tokens: float,
        bucket_size: float,
        token_rate: float,
        time_until_next: float,
        rejection_count: int = 0,
    ) -> float:
        """
        Calculate retry-after based on hybrid backpressure
        
        Returns: milliseconds to wait
        """
        # Calculate both backpressure components
        bp_p95 = self._calculate_bp_p95()
        bp_gradient = self._calculate_bp_gradient()
        
        # Final backpressure is the maximum (worst case)
        bp_final = max(bp_p95, bp_gradient)
        
        # Calculate retry delay with jitter
        retry_base = self.min_retry_delay
        added_penalty = self.max_retry_penalty * bp_final
        
        # Add jitter to prevent thundering herd
        jitter = random.uniform(0.8, 1.2)
        retry_seconds = (retry_base + added_penalty) * jitter
        
        return retry_seconds * 1000  # Convert to milliseconds
    
    def get_backpressure_header(self) -> float:
        """
        Get current backpressure score for X-Backpressure header
        
        Returns: Backpressure score from 0.0 to 1.0
        """
        bp_p95 = self._calculate_bp_p95()
        bp_gradient = self._calculate_bp_gradient()
        return max(bp_p95, bp_gradient)


class FixedCalculator(RetryAfterCalculator):
    """
    Fixed strategy: Wait exactly until next token becomes available
    
    Retry-After = time_until_next_token
    
    Pros:
    - Simple and predictable
    - Efficient (no wasted capacity)
    
    Cons:
    - Can cause thundering herd (all clients retry at same time)
    - Allows bucket to be completely emptied
    """
    
    def calculate(
        self,
        current_tokens: float,
        bucket_size: float,
        token_rate: float,
        time_until_next: float,
        rejection_count: int = 0,
    ) -> float:
        # Convert to milliseconds
        return time_until_next * 1000


class UtilizationCalculator(RetryAfterCalculator):
    """
    Utilization/Adaptive strategy: Adjust wait time based on bucket fill level
    
    This prevents the bucket from being depleted by slowing clients down
    progressively as the bucket empties.
    
    Strategy:
    - 80-100% full: No wait (allow through)
    - 50-80% full: Normal wait (time until next token)
    - 20-50% full: 2x wait (slow down traffic)
    - 0-20% full: 4x wait (aggressive backoff to prevent depletion)
    
    Pros:
    - Prevents bucket depletion
    - Smooth traffic shaping
    - Self-regulating under load
    
    Cons:
    - Clients experience slowdown before hard limit
    - More complex to understand
    """
    
    def __init__(
        self,
        aggressive_threshold: float = 0.2,  # Below 20% triggers aggressive backoff
        warning_threshold: float = 0.5,     # Below 50% triggers slow down
        normal_threshold: float = 0.8,      # Below 80% triggers normal wait
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
    ) -> float:
        """
        Calculate adaptive retry-after based on bucket utilization
        
        Returns: milliseconds to wait
        """
        if bucket_size <= 0:
            return time_until_next * 1000
        
        utilization = current_tokens / bucket_size
        base_wait_ms = time_until_next * 1000
        
        if utilization >= self.normal_threshold:
            # 80-100% full: Bucket is healthy, allow through
            # Return 0 to indicate no throttling needed (yet)
            return 0
        
        elif utilization >= self.warning_threshold:
            # 50-80% full: Normal rate limiting
            # Wait for next token at normal rate
            return base_wait_ms
        
        elif utilization >= self.aggressive_threshold:
            # 20-50% full: Bucket is draining, slow down
            # Double the wait time to reduce pressure
            return base_wait_ms * self.warning_multiplier
        
        else:
            # 0-20% full: Critical - bucket nearly empty
            # Aggressive backoff to prevent complete depletion
            return base_wait_ms * self.aggressive_multiplier


class JitteredCalculator(RetryAfterCalculator):
    """
    Jittered strategy: Add random jitter to prevent thundering herd
    
    Retry-After = time_until_next_token + random(0, jitter_range)
    
    Pros:
    - Prevents thundering herd (clients retry at different times)
    - Simple to implement
    
    Cons:
    - Less predictable for clients
    - May slightly increase average wait time
    """
    
    def __init__(
        self,
        jitter_range_ms: float = 1000,  # Max jitter in milliseconds
        jitter_type: str = "full",  # "full" or "equal"
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
    ) -> float:
        base_wait_ms = time_until_next * 1000
        
        if self.jitter_type == "full":
            # Full jitter: random between 0 and jitter_range
            jitter = random.uniform(0, self.jitter_range_ms)
        else:
            # Equal jitter: half fixed, half random
            jitter = (self.jitter_range_ms / 2) + random.uniform(0, self.jitter_range_ms / 2)
        
        return base_wait_ms + jitter


class ExponentialCalculator(RetryAfterCalculator):
    """
    Exponential backoff: Increase wait time for repeated violations
    
    Retry-After = base_wait * (backoff_factor ^ rejection_count)
    
    Useful for penalizing aggressive clients who ignore rate limits.
    
    Pros:
    - Penalizes repeated violations
    - Helps identify misbehaving clients
    
    Cons:
    - Requires tracking per-client rejection count
    - Can be punitive for legitimate clients with bursty traffic
    """
    
    def __init__(
        self,
        backoff_factor: float = 2.0,
        max_backoff_ms: float = 60000,  # Cap at 60 seconds
    ):
        self.backoff_factor = backoff_factor
        self.max_backoff_ms = max_backoff_ms
    
    def calculate(
        self,
        current_tokens: float,
        bucket_size: float,
        token_rate: float,
        time_until_next: float,
        rejection_count: int = 0,
    ) -> float:
        base_wait_ms = time_until_next * 1000
        
        # Apply exponential backoff based on rejection count
        multiplier = self.backoff_factor ** rejection_count
        wait_ms = base_wait_ms * multiplier
        
        # Cap at maximum
        return min(wait_ms, self.max_backoff_ms)


class ProportionalCalculator(RetryAfterCalculator):
    """
    Proportional strategy: Scale wait time based on remaining capacity
    
    Retry-After = base_wait * (1 + (1 - utilization))
    
    The less capacity available, the longer the wait.
    
    Pros:
    - Smooth scaling with load
    - Easy to understand
    
    Cons:
    - May not prevent complete depletion under heavy load
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
    ) -> float:
        base_wait_ms = time_until_next * 1000
        
        if bucket_size <= 0:
            return base_wait_ms
        
        utilization = current_tokens / bucket_size
        
        # Inverse utilization: as bucket empties, multiplier increases
        # utilization = 1.0 → multiplier = 1.0 (full bucket)
        # utilization = 0.0 → multiplier = max_multiplier (empty bucket)
        multiplier = 1.0 + ((1.0 - utilization) * (self.max_multiplier - 1.0))
        
        return base_wait_ms * multiplier


def create_calculator(strategy: RetryAfterStrategy, **kwargs) -> RetryAfterCalculator:
    """
    Factory function to create retry-after calculators
    
    Args:
        strategy: The calculation strategy to use
        **kwargs: Strategy-specific parameters
    
    Returns:
        Configured calculator instance
    
    Example:
        >>> calc = create_calculator(
        ...     RetryAfterStrategy.BACKPRESSURE,
        ...     p95_baseline=0.15,
        ...     min_latency=0.03
        ... )
    """
    
    if strategy == RetryAfterStrategy.BACKPRESSURE:
        return BackpressureCalculator(**kwargs)
    
    elif strategy in (RetryAfterStrategy.ADAPTIVE, RetryAfterStrategy.UTILIZATION):
        return UtilizationCalculator(**kwargs)
    
    elif strategy == RetryAfterStrategy.FIXED:
        return FixedCalculator()
    
    elif strategy == RetryAfterStrategy.JITTERED:
        return JitteredCalculator(**kwargs)
    
    elif strategy == RetryAfterStrategy.EXPONENTIAL:
        return ExponentialCalculator(**kwargs)
    
    elif strategy == RetryAfterStrategy.PROPORTIONAL:
        return ProportionalCalculator(**kwargs)
    
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


# Default recommended strategy: Hybrid Backpressure
DEFAULT_CALCULATOR = BackpressureCalculator()