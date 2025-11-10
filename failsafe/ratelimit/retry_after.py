"""
Retry-After calculation strategies for rate limiting

Implements various strategies for calculating how long a client should wait
before retrying when rate limited.
"""

import random
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional


class RetryAfterStrategy(str, Enum):
    """Available retry-after calculation strategies"""
    FIXED = "fixed"                    # Wait until next token available
    ADAPTIVE = "adaptive"              # Alias for utilization
    UTILIZATION = "utilization"        # Based on bucket fill level (prevents depletion)
    JITTERED = "jittered"             # Fixed + random jitter (prevents thundering herd)
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
        ...     RetryAfterStrategy.UTILIZATION,
        ...     aggressive_threshold=0.3,
        ...     warning_threshold=0.6
        ... )
    """
    
    if strategy in (RetryAfterStrategy.ADAPTIVE, RetryAfterStrategy.UTILIZATION):
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


# Default recommended strategy
DEFAULT_CALCULATOR = UtilizationCalculator()