"""
Enhanced rate limit exceptions with Retry-After support
"""

from typing import Optional
from failsafe.exceptions import FailsafeError


class RateLimitExceeded(FailsafeError):
    """
    Occurs when requester has exceeded the rate limit
    
    Includes Retry-After guidance to help clients know when to retry.
    """
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after_ms: Optional[float] = None,
        retry_after_seconds: Optional[float] = None,
    ):
        """
        Initialize rate limit exception
        
        Args:
            message: Error message
            retry_after_ms: Milliseconds to wait before retrying
            retry_after_seconds: Seconds to wait before retrying
                               (if both provided, ms takes precedence)
        """
        super().__init__(message)
        
        # Store retry-after in both formats
        if retry_after_ms is not None:
            self.retry_after_ms = retry_after_ms
            self.retry_after_seconds = retry_after_ms / 1000
        elif retry_after_seconds is not None:
            self.retry_after_seconds = retry_after_seconds
            self.retry_after_ms = retry_after_seconds * 1000
        else:
            self.retry_after_ms = None
            self.retry_after_seconds = None
    
    def get_retry_after_header(self) -> str:
        """
        Get Retry-After header value in HTTP standard format
        
        Returns:
            String value for Retry-After header (seconds as integer)
            
        Example:
            >>> exc = RateLimitExceeded(retry_after_ms=5500)
            >>> exc.get_retry_after_header()
            '6'  # Rounded up
        """
        if self.retry_after_seconds is None:
            return "60"  # Default to 60 seconds if not specified
        
        # Round up to nearest second (HTTP standard uses integer seconds)
        import math
        return str(math.ceil(self.retry_after_seconds))
    
    def __str__(self) -> str:
        """String representation including retry-after info"""
        base_msg = super().__str__()
        if self.retry_after_seconds is not None:
            return f"{base_msg} (Retry after {self.retry_after_seconds:.2f}s)"
        return base_msg


class EmptyBucket(FailsafeError):
    """
    Internal exception: Token bucket is empty
    
    This is caught internally and converted to RateLimitExceeded with Retry-After.
    Should not be exposed to end users.
    """
    pass