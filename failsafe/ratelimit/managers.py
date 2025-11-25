"""
Enhanced RateLimiter managers with dynamic configuration support and per-client tracking
"""

import time
from typing import Optional, Dict

from failsafe.ratelimit.buckets import TokenBucket
from failsafe.ratelimit.exceptions import EmptyBucket, RateLimitExceeded
from failsafe.ratelimit.retry_after import (
    RetryAfterStrategy,
    RetryAfterCalculator,
    create_calculator,
    DEFAULT_CALCULATOR
)


class ClientRateLimitState:
    """Per-client rate limiting state"""
    
    def __init__(self):
        self.rejection_count = 0
        self.last_rejection = 0.0
        self.last_success = 0.0
    
    def record_rejection(self):
        """Record a rate limit rejection"""
        self.rejection_count += 1
        self.last_rejection = time.time()
    
    def record_success(self):
        """Record a successful request"""
        self.rejection_count = 0
        self.last_success = time.time()
    
    def is_stale(self, max_age: float = 3600) -> bool:
        """Check if this state is stale"""
        now = time.time()
        last_activity = max(self.last_rejection, self.last_success)
        return (now - last_activity) > max_age


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
    
    async def acquire(self, client_id: Optional[str] = None) -> None:
        raise NotImplementedError
    
    def get_config(self) -> dict:
        """Get current configuration"""
        return {
            "enabled": self._enabled,
        }


class TokenBucketLimiter(RateLimiter):
    """
    Token Bucket Rate Limiter with dynamic configuration support and per-client tracking.
    """

    def __init__(
        self,
        max_executions: float,
        per_time_secs: float,
        bucket_size: Optional[float] = None,
        retry_after_strategy: RetryAfterStrategy = RetryAfterStrategy.BACKPRESSURE,
        retry_after_calculator: Optional[RetryAfterCalculator] = None,
        enable_per_client_tracking: bool = False,
        **calculator_kwargs,
    ) -> None:
        super().__init__()
        
        self._max_executions = max_executions
        self._per_time_secs = per_time_secs
        self._bucket_size = bucket_size if bucket_size else max_executions
        self._enable_per_client_tracking = enable_per_client_tracking
        
        # Pass per-client tracking flag to calculator
        if 'enable_per_client_tracking' not in calculator_kwargs:
            calculator_kwargs['enable_per_client_tracking'] = enable_per_client_tracking
        
        # Retry-After calculation strategy
        self._retry_after_calculator = (
            retry_after_calculator or 
            create_calculator(retry_after_strategy, **calculator_kwargs)
        )
        
        # Per-client state tracking
        self._client_states: Dict[str, ClientRateLimitState] = {}
        self._last_cleanup = time.time()
        
        # Lazy initialization - create bucket when first accessed
        self._token_bucket: Optional[TokenBucket] = None

    def _cleanup_stale_clients(self):
        """Remove stale client states periodically"""
        now = time.time()
        if now - self._last_cleanup < 300:  # Every 5 minutes
            return
        
        stale_clients = [
            client_id for client_id, state in self._client_states.items()
            if state.is_stale()
        ]
        for client_id in stale_clients:
            del self._client_states[client_id]
        
        self._last_cleanup = now
    
    def _get_client_state(self, client_id: Optional[str]) -> Optional[ClientRateLimitState]:
        """Get or create client state"""
        if not self._enable_per_client_tracking or client_id is None:
            return None
        
        if client_id not in self._client_states:
            self._client_states[client_id] = ClientRateLimitState()
        
        return self._client_states[client_id]

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
    
    @property
    def retry_after_calculator(self) -> RetryAfterCalculator:
        """Get the retry-after calculator (for latency recording, etc.)"""
        return self._retry_after_calculator
    
    def update_max_executions(self, max_executions: float):
        """Dynamically update the maximum executions rate"""
        self._max_executions = max_executions
        self._token_bucket = None
    
    def update_per_time_secs(self, per_time_secs: float):
        """Dynamically update the time window"""
        self._per_time_secs = per_time_secs
        self._token_bucket = None
    
    def update_bucket_size(self, bucket_size: float):
        """Dynamically update the bucket size"""
        self._bucket_size = bucket_size
        self._token_bucket = None
    
    def update_config(
        self,
        max_executions: Optional[float] = None,
        per_time_secs: Optional[float] = None,
        bucket_size: Optional[float] = None
    ):
        """Update multiple configuration parameters at once"""
        if max_executions is not None:
            self._max_executions = max_executions
        
        if per_time_secs is not None:
            self._per_time_secs = per_time_secs
        
        if bucket_size is not None:
            self._bucket_size = bucket_size
        
        self._token_bucket = None
    
    def get_config(self) -> dict:
        """Get current configuration"""
        return {
            "enabled": self._enabled,
            "max_executions": self._max_executions,
            "per_time_secs": self._per_time_secs,
            "bucket_size": self._bucket_size,
            "current_tokens": self.current_tokens,
            "retry_after_strategy": self._retry_after_calculator.__class__.__name__,
            "per_client_tracking": self._enable_per_client_tracking,
            "active_clients": len(self._client_states) if self._enable_per_client_tracking else 0,
        }

    async def acquire(self, client_id: Optional[str] = None) -> None:
        """
        Acquire a token from the bucket.
        Raises RateLimitExceeded with Retry-After if bucket is empty.
        
        Args:
            client_id: Optional client identifier for per-client tracking
        """
        # If disabled, allow through without rate limiting
        if not self._enabled:
            return
        
        # Get client state
        client_state = self._get_client_state(client_id)
        
        try:
            await self.bucket.take()
            
            # Success - reset rejection count
            if client_state:
                client_state.record_success()
            
            # Periodic cleanup
            self._cleanup_stale_clients()
        
        except EmptyBucket as e:
            # Record rejection
            if client_state:
                client_state.record_rejection()
            
            # Calculate retry-after based on strategy
            retry_after_ms = self._calculate_retry_after(client_id, client_state)
            
            # Raise with retry-after guidance
            raise RateLimitExceeded(
                retry_after_ms=retry_after_ms,
                message=f"Rate limit exceeded. Retry after {retry_after_ms:.0f}ms"
            ) from e
    
    def _calculate_retry_after(
        self,
        client_id: Optional[str],
        client_state: Optional[ClientRateLimitState]
    ) -> float:
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
        
        # Get rejection count
        rejection_count = client_state.rejection_count if client_state else 0
        
        # Use calculator to determine wait time
        retry_after_ms = self._retry_after_calculator.calculate(
            current_tokens=current_tokens,
            bucket_size=self._bucket_size,
            token_rate=token_rate,
            time_until_next=time_until_next,
            rejection_count=rejection_count,
            client_id=client_id,
        )
        
        return retry_after_ms


class LeakyTokenBucketLimiter(RateLimiter):
    """
    Leaky Token Bucket Rate Limiter (placeholder for future implementation)
    """
    
    def __init__(self) -> None:
        super().__init__()

    async def acquire(self, client_id: Optional[str] = None) -> None:
        if not self._enabled:
            return
        
        raise NotImplementedError("LeakyTokenBucketLimiter not yet implemented")