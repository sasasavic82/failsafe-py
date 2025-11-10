"""
Enhanced RateLimiter managers with dynamic configuration support
"""

from typing import Optional

from failsafe.ratelimit.buckets import TokenBucket
from failsafe.ratelimit.exceptions import EmptyBucket, RateLimitExceeded
from failsafe.ratelimit.retry_after import (
    RetryAfterStrategy,
    RetryAfterCalculator,
    create_calculator,
    DEFAULT_CALCULATOR
)


class RateLimiter:
    """Base rate limiter with control plane support"""
    
    def __init__(self):
        # Control plane support
        self._enabled = True
    
    @property
    def enabled(self) -> bool:
        """Check if this rate limiter is enabled"""
        return self._enabled
    
    def enable(self):
        """Enable this rate limiter"""
        self._enabled = True
    
    def disable(self):
        """Disable this rate limiter"""
        self._enabled = False
    
    async def acquire(self) -> None:
        raise NotImplementedError
    
    def get_config(self) -> dict:
        """Get current configuration"""
        return {
            "enabled": self._enabled,
        }


class TokenBucketLimiter(RateLimiter):
    """
    Token Bucket Rate Limiter with dynamic configuration support and Retry-After calculation.
    Replenish tokens as time passes on. If tokens are available, executions can be allowed.
    Otherwise, it's going to be rejected with RateLimitExceeded including Retry-After guidance.
    """

    def __init__(
        self,
        max_executions: float,
        per_time_secs: float,
        bucket_size: Optional[float] = None,
        retry_after_strategy: RetryAfterStrategy = RetryAfterStrategy.UTILIZATION,
        retry_after_calculator: Optional[RetryAfterCalculator] = None,
        **calculator_kwargs,
    ) -> None:
        super().__init__()
        
        self._max_executions = max_executions
        self._per_time_secs = per_time_secs
        self._bucket_size = bucket_size if bucket_size else max_executions
        
        # Retry-After calculation strategy
        self._retry_after_calculator = (
            retry_after_calculator or 
            create_calculator(retry_after_strategy, **calculator_kwargs)
        )
        
        # Track rejections for exponential backoff (if using that strategy)
        self._rejection_count = 0
        
        # Lazy initialization - create bucket when first accessed
        self._token_bucket: Optional[TokenBucket] = None

    @property
    def bucket(self) -> TokenBucket:
        """Lazy initialization of token bucket"""
        if self._token_bucket is None:
            self._token_bucket = TokenBucket(
                max_executions=self._max_executions,
                per_time_secs=self._per_time_secs,
                bucket_size=self._bucket_size
            )
        return self._token_bucket

    @property
    def max_executions(self) -> float:
        """Get current max executions rate"""
        return self._max_executions
    
    @property
    def per_time_secs(self) -> float:
        """Get current time window"""
        return self._per_time_secs
    
    @property
    def bucket_size(self) -> float:
        """Get current bucket size"""
        return self._bucket_size
    
    @property
    def current_tokens(self) -> float:
        """Get current available tokens (lazy init)"""
        return self.bucket.tokens
    
    def update_max_executions(self, max_executions: float):
        """
        Dynamically update the maximum executions rate.
        Note: This creates a new token bucket with the updated rate.
        """
        self._max_executions = max_executions
        # Force recreation on next access
        self._token_bucket = None
    
    def update_per_time_secs(self, per_time_secs: float):
        """
        Dynamically update the time window.
        Note: This creates a new token bucket with the updated window.
        """
        self._per_time_secs = per_time_secs
        # Force recreation on next access
        self._token_bucket = None
    
    def update_bucket_size(self, bucket_size: float):
        """
        Dynamically update the bucket size.
        Note: This creates a new token bucket with the updated size.
        """
        self._bucket_size = bucket_size
        # Force recreation on next access
        self._token_bucket = None
    
    def update_config(
        self,
        max_executions: Optional[float] = None,
        per_time_secs: Optional[float] = None,
        bucket_size: Optional[float] = None
    ):
        """
        Update multiple configuration parameters at once.
        More efficient than calling individual update methods.
        """
        if max_executions is not None:
            self._max_executions = max_executions
        
        if per_time_secs is not None:
            self._per_time_secs = per_time_secs
        
        if bucket_size is not None:
            self._bucket_size = bucket_size
        
        # Force recreation on next access
        self._token_bucket = None
    
    def get_config(self) -> dict:
        """Get current configuration"""
        return {
            "enabled": self._enabled,
            "max_executions": self._max_executions,
            "per_time_secs": self._per_time_secs,
            "bucket_size": self._bucket_size,
            "current_tokens": self.current_tokens,
        }

    async def acquire(self) -> None:
        """
        Acquire a token from the bucket.
        Raises RateLimitExceeded with Retry-After if bucket is empty.
        """
        # If disabled, allow through without rate limiting
        if not self._enabled:
            return
        
        try:
            await self.bucket.take()
            # Success - reset rejection count
            self._rejection_count = 0
        
        except EmptyBucket as e:
            # Calculate retry-after based on strategy
            retry_after_ms = self._calculate_retry_after()
            
            # Increment rejection count for exponential backoff
            self._rejection_count += 1
            
            # Raise with retry-after guidance
            raise RateLimitExceeded(
                retry_after_ms=retry_after_ms,
                message=f"Rate limit exceeded. Retry after {retry_after_ms:.0f}ms"
            ) from e
    
    def _calculate_retry_after(self) -> float:
        """Calculate retry-after time in milliseconds"""
        bucket = self.bucket
        
        # Get current state
        current_tokens = bucket.tokens
        token_rate = self._max_executions / self._per_time_secs  # tokens per second
        
        # Calculate time until next token
        import asyncio
        loop = asyncio.get_running_loop()
        now = loop.time()
        time_until_next = max(0, bucket._next_replenish_at - now)
        
        # Use calculator to determine wait time
        retry_after_ms = self._retry_after_calculator.calculate(
            current_tokens=current_tokens,
            bucket_size=self._bucket_size,
            token_rate=token_rate,
            time_until_next=time_until_next,
            rejection_count=self._rejection_count,
        )
        
        return retry_after_ms


class LeakyTokenBucketLimiter(RateLimiter):
    """
    Leaky Token Bucket Rate Limiter (placeholder for future implementation)
    """
    
    def __init__(self) -> None:
        super().__init__()
        # TODO: Implement leaky bucket algorithm

    async def acquire(self) -> None:
        # TODO: Implement acquisition logic
        if not self._enabled:
            return
        
        raise NotImplementedError("LeakyTokenBucketLimiter not yet implemented")