"""
Enhanced RateLimiter managers with dynamic configuration support
"""

from typing import Optional

from failsafe.ratelimit.buckets import TokenBucket
from failsafe.ratelimit.exceptions import EmptyBucket, RateLimitExceeded
from failsafe.ratelimit.events import RateLimitListener

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
    Token Bucket Rate Limiter with dynamic configuration support.
    Replenish tokens as time passes on. If tokens are available, executions can be allowed.
    Otherwise, it's going to be rejected with RateLimitExceeded
    """

    def __init__(
        self,
        max_executions: float,
        per_time_secs: float,
        event_dispatcher: RateLimitListener,
        bucket_size: Optional[float] = None
    ) -> None:
        super().__init__()
        
        self._max_executions = max_executions
        self._per_time_secs = per_time_secs
        self._bucket_size = bucket_size if bucket_size else max_executions
        self._event_dispatcher = event_dispatcher
        
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
        Raises RateLimitExceeded if bucket is empty and not enough time has passed.
        """
        # If disabled, allow through without rate limiting
        if not self._enabled:
            return
        
        try:
            await self._event_dispatcher.on_request(self)
            await self.bucket.take()  # Use lazy property instead of _token_bucket directly
            await self._event_dispatcher.on_success(self)
        except EmptyBucket as e:
            await self._event_dispatcher.on_failure(self)
            raise RateLimitExceeded from e


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