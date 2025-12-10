"""
Adaptive Client - Self-regulating HTTP client that respects server backpressure.

Provides:
    - AdaptiveClient base class for building resilient API clients
    - @adaptive decorator for wrapping individual methods/functions
    - Automatic retry with Retry-After header respect
    - Backpressure-aware request throttling

Usage:
    # As a base class
    class ProductClient(AdaptiveClient):
        def get_product(self, product_id: str) -> dict:
            return self.send_request("GET", f"/products/{product_id}")
    
    # With @adaptive decorator
    class ProductClient(AdaptiveClient):
        @adaptive(strategy="queue", max_retries=3)
        def create_product(self, data: dict) -> dict:
            return self.send_request("POST", "/products", **data)
    
    # Standalone decorator on any function
    @adaptive(strategy="queue", max_retries=3)
    async def call_external_api():
        async with httpx.AsyncClient() as client:
            return await client.get("https://api.example.com/data")
"""

import logging
import httpx
import asyncio
import functools
from time import time, sleep
from typing import Optional, Literal, Callable, TypeVar, ParamSpec, Any, Union
from threading import Lock as ThreadingLock
from dataclasses import dataclass

from .base_client import ClientInterface, ClientError
from .auth import AuthBase

_logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# ============================================================================
# Exceptions
# ============================================================================

class RateLimitedError(ClientError):
    """Raised when a request is rejected due to rate limiting."""
    
    def __init__(self, retry_after: float, backpressure: Optional[float] = None):
        self.retry_after = retry_after
        self.backpressure = backpressure
        super().__init__(f"Rate limited. Retry after {retry_after:.2f} seconds.")


class MaxRetriesExceeded(ClientError):
    """Raised when max retries have been exhausted."""
    
    def __init__(self, attempts: int, last_retry_after: float):
        self.attempts = attempts
        self.last_retry_after = last_retry_after
        super().__init__(f"Max retries ({attempts}) exceeded. Last Retry-After: {last_retry_after:.2f}s")


# ============================================================================
# Rate Limit State Tracker
# ============================================================================

@dataclass
class RateLimitState:
    """Tracks rate limit state for a client or endpoint."""
    retry_after_timestamp: float = 0.0
    backpressure: float = 0.0
    last_remaining: Optional[int] = None
    
    @property
    def retry_after_seconds(self) -> float:
        """Returns remaining seconds until requests are allowed."""
        remaining = self.retry_after_timestamp - time()
        return max(0, remaining)
    
    @property
    def is_rate_limited(self) -> bool:
        """Check if we're currently in a rate-limited state."""
        return self.retry_after_seconds > 0
    
    def update_from_response(self, response: httpx.Response) -> float:
        """
        Update state from response headers.
        Returns wait time in seconds (0 if not rate limited).
        """
        # Update backpressure from header (available on all responses)
        if backpressure := response.headers.get("X-Backpressure"):
            try:
                self.backpressure = float(backpressure)
            except ValueError:
                pass
        
        # Update remaining tokens
        if remaining := response.headers.get("RateLimit-Remaining"):
            try:
                self.last_remaining = int(remaining)
            except ValueError:
                pass
        
        # Only update retry timestamp on 429
        if response.status_code != 429:
            return 0.0
        
        # Parse Retry-After header
        retry_after = response.headers.get("Retry-After", "1")
        try:
            wait_seconds = float(retry_after)
        except ValueError:
            _logger.warning(f"Could not parse Retry-After: {retry_after}, defaulting to 1s")
            wait_seconds = 1.0
        
        # Also check X-RateLimit-Retry-After-Ms for precision
        if retry_ms := response.headers.get("X-RateLimit-Retry-After-Ms"):
            try:
                wait_seconds = float(retry_ms) / 1000.0
            except ValueError:
                pass
        
        self.retry_after_timestamp = time() + wait_seconds
        _logger.warning(f"Rate limited for {wait_seconds:.2f}s")
        
        return wait_seconds


# Global state tracker for standalone decorator usage
_global_rate_limit_states: dict[str, RateLimitState] = {}
_global_state_lock = ThreadingLock()


def _get_global_state(key: str) -> RateLimitState:
    """Get or create a global rate limit state for a key."""
    with _global_state_lock:
        if key not in _global_rate_limit_states:
            _global_rate_limit_states[key] = RateLimitState()
        return _global_rate_limit_states[key]


# ============================================================================
# @adaptive Decorator
# ============================================================================

def adaptive(
    strategy: Literal["queue", "reject"] = "queue",
    max_retries: int = 3,
    *,
    name: Optional[str] = None,
    backoff_multiplier: float = 1.0,
    max_wait: float = 60.0,
    respect_backpressure: bool = True,
    backpressure_threshold: float = 0.8,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator that makes a function adaptive to server rate limiting.
    
    Works with:
        - Methods on AdaptiveClient subclasses (uses client's state)
        - Standalone functions (uses global state keyed by function name)
        - Both sync and async functions
    
    Args:
        strategy: How to handle rate limits
            - "queue": Wait for Retry-After duration, then retry
            - "reject": Immediately raise RateLimitedError
        max_retries: Maximum retry attempts for "queue" strategy
        name: Identifier for rate limit state (defaults to function name)
        backoff_multiplier: Multiply Retry-After by this on each retry
        max_wait: Maximum wait time per retry
        respect_backpressure: If True, proactively slow down when backpressure is high
        backpressure_threshold: Slow down when backpressure exceeds this (0.0-1.0)
    
    Example:
        class ProductClient(AdaptiveClient):
            @adaptive(strategy="queue", max_retries=3)
            def create_product(self, data: dict) -> dict:
                return self.send_request("POST", "/products", **data)
        
        # Or standalone
        @adaptive(strategy="queue", max_retries=5)
        async def fetch_data():
            async with httpx.AsyncClient() as client:
                return await client.get("https://api.example.com/data")
    """
    
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        state_key = name or f"{func.__module__}.{func.__qualname__}"
        
        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Check if this is a method on AdaptiveClient
            client_state: Optional[RateLimitState] = None
            if args and isinstance(args[0], AdaptiveClient):
                client = args[0]
                client_state = client._rate_limit_state
            else:
                client_state = _get_global_state(state_key)
            
            attempts = 0
            last_wait = 0.0
            
            while True:
                # Check proactive backpressure slowdown
                if respect_backpressure and client_state.backpressure >= backpressure_threshold:
                    slowdown = client_state.backpressure * 0.5  # Max 0.5s slowdown
                    _logger.debug(f"Backpressure {client_state.backpressure:.2f}, slowing down {slowdown:.2f}s")
                    sleep(slowdown)
                
                # Check if currently rate limited
                remaining = client_state.retry_after_seconds
                if remaining > 0:
                    if strategy == "reject":
                        raise RateLimitedError(remaining, client_state.backpressure)
                    
                    # Queue strategy: wait
                    wait_time = min(remaining, max_wait)
                    _logger.info(f"Rate limited, waiting {wait_time:.2f}s before request")
                    sleep(wait_time)
                
                try:
                    result = func(*args, **kwargs)
                    
                    # If result is an httpx.Response, update state
                    if isinstance(result, httpx.Response):
                        client_state.update_from_response(result)
                        if result.status_code == 429:
                            raise _create_rate_limit_exception(client_state, strategy)
                    
                    return result
                    
                except RateLimitedError:
                    raise  # Re-raise our own exceptions
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        attempts += 1
                        last_wait = client_state.update_from_response(e.response)
                        
                        if strategy == "reject":
                            raise RateLimitedError(last_wait, client_state.backpressure)
                        
                        if attempts >= max_retries:
                            raise MaxRetriesExceeded(attempts, last_wait)
                        
                        # Apply backoff
                        wait_time = min(last_wait * (backoff_multiplier ** (attempts - 1)), max_wait)
                        _logger.info(f"Retry {attempts}/{max_retries} after {wait_time:.2f}s")
                        sleep(wait_time)
                        continue
                    raise
                
                except ClientError as e:
                    # Check if it's a 429 wrapped in ClientError
                    if "429" in str(e):
                        attempts += 1
                        if attempts >= max_retries:
                            raise MaxRetriesExceeded(attempts, last_wait)
                        
                        wait_time = min(client_state.retry_after_seconds or 1.0, max_wait)
                        _logger.info(f"Retry {attempts}/{max_retries} after {wait_time:.2f}s")
                        sleep(wait_time)
                        continue
                    raise
        
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Check if this is a method on AdaptiveClient
            client_state: Optional[RateLimitState] = None
            if args and isinstance(args[0], AdaptiveClient):
                client = args[0]
                client_state = client._rate_limit_state
            else:
                client_state = _get_global_state(state_key)
            
            attempts = 0
            last_wait = 0.0
            
            while True:
                # Check proactive backpressure slowdown
                if respect_backpressure and client_state.backpressure >= backpressure_threshold:
                    slowdown = client_state.backpressure * 0.5
                    _logger.debug(f"Backpressure {client_state.backpressure:.2f}, slowing down {slowdown:.2f}s")
                    await asyncio.sleep(slowdown)
                
                # Check if currently rate limited
                remaining = client_state.retry_after_seconds
                if remaining > 0:
                    if strategy == "reject":
                        raise RateLimitedError(remaining, client_state.backpressure)
                    
                    wait_time = min(remaining, max_wait)
                    _logger.info(f"Rate limited, waiting {wait_time:.2f}s before request")
                    await asyncio.sleep(wait_time)
                
                try:
                    result = await func(*args, **kwargs)
                    
                    if isinstance(result, httpx.Response):
                        client_state.update_from_response(result)
                        if result.status_code == 429:
                            raise _create_rate_limit_exception(client_state, strategy)
                    
                    return result
                    
                except RateLimitedError:
                    raise
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        attempts += 1
                        last_wait = client_state.update_from_response(e.response)
                        
                        if strategy == "reject":
                            raise RateLimitedError(last_wait, client_state.backpressure)
                        
                        if attempts >= max_retries:
                            raise MaxRetriesExceeded(attempts, last_wait)
                        
                        wait_time = min(last_wait * (backoff_multiplier ** (attempts - 1)), max_wait)
                        _logger.info(f"Retry {attempts}/{max_retries} after {wait_time:.2f}s")
                        await asyncio.sleep(wait_time)
                        continue
                    raise
                
                except ClientError as e:
                    if "429" in str(e):
                        attempts += 1
                        if attempts >= max_retries:
                            raise MaxRetriesExceeded(attempts, last_wait)
                        
                        wait_time = min(client_state.retry_after_seconds or 1.0, max_wait)
                        _logger.info(f"Retry {attempts}/{max_retries} after {wait_time:.2f}s")
                        await asyncio.sleep(wait_time)
                        continue
                    raise
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def _create_rate_limit_exception(state: RateLimitState, strategy: str) -> Exception:
    """Create appropriate exception based on strategy."""
    if strategy == "reject":
        return RateLimitedError(state.retry_after_seconds, state.backpressure)
    return ClientError(f"Rate limited. Retry after {state.retry_after_seconds:.2f}s")


# ============================================================================
# AdaptiveClient Base Class
# ============================================================================

class AdaptiveClient(ClientInterface):
    """
    Base HTTP client that adapts to server rate limiting signals.
    
    Features:
        - Respects Retry-After headers on 429 responses
        - Reads X-Backpressure header for proactive slowdown
        - Supports "queue" (wait and retry) or "reject" (fail fast) strategies
        - Thread-safe and async-safe
    
    Usage:
        class ProductClient(AdaptiveClient):
            def get_product(self, product_id: str) -> dict:
                return self.send_request("GET", f"/products/{product_id}")
            
            @adaptive(strategy="queue", max_retries=3)
            def create_product(self, data: dict) -> dict:
                return self.send_request("POST", "/products", **data)
        
        client = ProductClient(base_url="http://api.example.com", adaptive=True)
        product = client.get_product("123")
    """

    def __init__(
        self,
        client_name: Optional[str] = None,
        *,
        base_url: str,
        auth: Optional[AuthBase] = None,
        adaptive: bool = True,
        strategy: Literal["reject", "queue"] = "queue",
        max_retries: int = 3,
        respect_backpressure: bool = True,
        backpressure_threshold: float = 0.8,
    ) -> None:
        """
        Initialize an adaptive client.
        
        Args:
            client_name: Name for logging
            base_url: Base URL for all requests
            auth: Authentication provider
            adaptive: Enable adaptive rate limit handling
            strategy: "queue" to wait and retry, "reject" to fail immediately
            max_retries: Maximum retries for queue strategy
            respect_backpressure: Proactively slow down on high backpressure
            backpressure_threshold: Backpressure level to trigger slowdown (0.0-1.0)
        """
        super().__init__(client_name)
        self.base_url = base_url
        self.auth = auth or AuthBase()
        self._adaptive = adaptive
        self._strategy = strategy
        self._max_retries = max_retries
        self._respect_backpressure = respect_backpressure
        self._backpressure_threshold = backpressure_threshold
        
        # Rate limit state
        self._rate_limit_state = RateLimitState()
        
        # Locks for thread/async safety
        self._async_lock = asyncio.Lock()
        self._sync_lock = ThreadingLock()

        _logger.info(
            f"Creating {self.client_name} client: base_url={self.base_url}, "
            f"adaptive={self._adaptive}, strategy={self._strategy}, max_retries={self._max_retries}"
        )

    @property
    def _headers(self) -> dict[str, str]:
        return self.auth.get_headers() if self.auth else {}

    @property
    def retry_after_seconds(self) -> float:
        """Returns remaining seconds until requests are allowed."""
        return self._rate_limit_state.retry_after_seconds

    @property
    def is_rate_limited(self) -> bool:
        """Check if currently rate limited."""
        return self._rate_limit_state.is_rate_limited

    @property
    def backpressure(self) -> float:
        """Current backpressure level from server (0.0-1.0)."""
        return self._rate_limit_state.backpressure

    @property
    def remaining_tokens(self) -> Optional[int]:
        """Remaining rate limit tokens, if known."""
        return self._rate_limit_state.last_remaining

    def _should_slow_down(self) -> bool:
        """Check if we should proactively slow down due to backpressure."""
        return (
            self._respect_backpressure and 
            self._rate_limit_state.backpressure >= self._backpressure_threshold
        )

    def _proactive_slowdown(self) -> float:
        """Calculate proactive slowdown based on backpressure."""
        if not self._should_slow_down():
            return 0.0
        return self._rate_limit_state.backpressure * 0.5  # Max 0.5s

    def send_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """
        Send an HTTP request with adaptive rate limit handling.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: URL endpoint (appended to base_url)
            **kwargs: Passed to httpx as JSON body
        
        Returns:
            Parsed JSON response
        
        Raises:
            RateLimitedError: If adaptive=True, strategy="reject", and rate limited
            MaxRetriesExceeded: If max retries exhausted
            ClientError: For other HTTP errors
        """
        if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
            raise ValueError("Invalid HTTP method provided.")

        url = f"{self.base_url}{endpoint}"
        _logger.info(f"Sending {method} request to {url}")

        client_kwargs = {}
        if self.auth:
            client_kwargs.update(self.auth.get_client_kwargs())

        attempts = 0
        
        with httpx.Client(**client_kwargs) as client:
            while True:
                with self._sync_lock:
                    # Proactive slowdown based on backpressure
                    slowdown = self._proactive_slowdown()
                    if slowdown > 0:
                        _logger.debug(f"Backpressure slowdown: {slowdown:.2f}s")
                        sleep(slowdown)
                    
                    # Check if rate limited
                    remaining = self.retry_after_seconds
                    if remaining > 0:
                        if not self._adaptive:
                            pass  # Let request proceed, will fail with 429
                        elif self._strategy == "reject":
                            raise RateLimitedError(remaining, self.backpressure)
                        else:
                            _logger.info(f"Waiting {remaining:.2f}s (rate limited)")
                            sleep(remaining)

                response = client.request(
                    method,
                    url,
                    headers=self._headers,
                    json=kwargs if kwargs else None,
                )

                _logger.debug(f"Response: {response.status_code}")

                # Update state from response headers
                wait_seconds = self._rate_limit_state.update_from_response(response)

                if response.status_code == 429:
                    if not self._adaptive:
                        raise ClientError(f"HTTP error 429: {response.text}")
                    
                    if self._strategy == "reject":
                        raise RateLimitedError(wait_seconds, self.backpressure)
                    
                    attempts += 1
                    if attempts >= self._max_retries:
                        raise MaxRetriesExceeded(attempts, wait_seconds)
                    
                    _logger.info(f"429 received, retry {attempts}/{self._max_retries} after {wait_seconds:.2f}s")
                    sleep(wait_seconds)
                    continue

                try:
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError as http_err:
                    raise ClientError(
                        f"HTTP error {http_err.response.status_code}: {http_err.response.text}"
                    )

    async def send_request_async(self, method: str, endpoint: str, **kwargs) -> Any:
        """Async version of send_request."""
        if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
            raise ValueError("Invalid HTTP method provided.")

        url = f"{self.base_url}{endpoint}"
        _logger.info(f"Sending {method} request to {url} (async)")

        client_kwargs = {}
        if self.auth:
            client_kwargs.update(self.auth.get_client_kwargs())

        attempts = 0

        async with httpx.AsyncClient(**client_kwargs) as client:
            while True:
                async with self._async_lock:
                    slowdown = self._proactive_slowdown()
                    if slowdown > 0:
                        _logger.debug(f"Backpressure slowdown: {slowdown:.2f}s")
                        await asyncio.sleep(slowdown)
                    
                    remaining = self.retry_after_seconds
                    if remaining > 0:
                        if not self._adaptive:
                            pass
                        elif self._strategy == "reject":
                            raise RateLimitedError(remaining, self.backpressure)
                        else:
                            _logger.info(f"Waiting {remaining:.2f}s (rate limited)")
                            await asyncio.sleep(remaining)

                response = await client.request(
                    method,
                    url,
                    headers=self._headers,
                    json=kwargs if kwargs else None,
                )

                _logger.debug(f"Response: {response.status_code}")

                wait_seconds = self._rate_limit_state.update_from_response(response)

                if response.status_code == 429:
                    if not self._adaptive:
                        raise ClientError(f"HTTP error 429: {response.text}")
                    
                    if self._strategy == "reject":
                        raise RateLimitedError(wait_seconds, self.backpressure)
                    
                    attempts += 1
                    if attempts >= self._max_retries:
                        raise MaxRetriesExceeded(attempts, wait_seconds)
                    
                    _logger.info(f"429 received, retry {attempts}/{self._max_retries} after {wait_seconds:.2f}s")
                    await asyncio.sleep(wait_seconds)
                    continue

                try:
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError as http_err:
                    raise ClientError(
                        f"HTTP error {http_err.response.status_code}: {http_err.response.text}"
                    )

    def health_check(self) -> dict:
        """Perform a health check."""
        return self.send_request("GET", "/health")

    async def health_check_async(self) -> dict:
        """Async health check."""
        return await self.send_request_async("GET", "/health")

    # ========================================================================
    # Configuration Methods
    # ========================================================================

    def set_adaptive(self, adaptive: bool) -> None:
        """Enable or disable adaptive mode."""
        self._adaptive = adaptive
        _logger.info(f"Adaptive mode set to {adaptive}")

    def set_strategy(self, strategy: Literal["reject", "queue"]) -> None:
        """Set the rate limit handling strategy."""
        if strategy not in ("reject", "queue"):
            raise ValueError("Strategy must be 'reject' or 'queue'")
        self._strategy = strategy
        _logger.info(f"Strategy set to {strategy}")

    def set_max_retries(self, max_retries: int) -> None:
        """Set maximum retries for queue strategy."""
        self._max_retries = max_retries
        _logger.info(f"Max retries set to {max_retries}")

    @property
    def is_adaptive(self) -> bool:
        return self._adaptive

    @property
    def strategy(self) -> str:
        return self._strategy

__all__ = [
    "AdaptiveClient",
    "adaptive",
    "RateLimitedError",
    "MaxRetriesExceeded",
    "RateLimitState",
]