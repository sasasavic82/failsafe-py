"""
Enhanced ratelimit API with control plane integration and per-client tracking
"""

import functools
import time
from types import TracebackType
from typing import Any, Optional, Type, cast, Callable

from failsafe.events import get_default_name
from failsafe.ratelimit.managers import RateLimiter
from failsafe.ratelimit.instrumeted_managers import InstrumentedTokenBucketLimiter
from failsafe.ratelimit.retry_after import RetryAfterStrategy, RetryAfterCalculator, BackpressureCalculator
from failsafe.typing import FuncT

# Import control plane helpers
try:
    from failsafe.controller import (
        register_pattern,
        get_pattern_config,
        create_control_plane_listener,
    )
    CONTROL_PLANE_AVAILABLE = True
except ImportError:
    CONTROL_PLANE_AVAILABLE = False
    
    def register_pattern(*args, **kwargs):
        pass
    
    def get_pattern_config(*args, **kwargs):
        return {}
    
    def create_control_plane_listener(*args, **kwargs):
        return None


class ratelimiter:
    """
    Generic rate limiter wrapper that can work with any RateLimiter implementation.
    
    **Parameters:**
    
    * **limiter** - A RateLimiter instance
    * **name** *(optional)* - A component name or ID for control plane
    * **enable_control_plane** *(bool)* - Enable control plane integration (default: True)
    * **client_id_extractor** *(callable)* - Function to extract client_id from request context
    """

    def __init__(
        self,
        limiter: RateLimiter,
        name: Optional[str] = None,
        enable_control_plane: bool = True,
        client_id_extractor: Optional[Callable] = None,
    ) -> None:
        self._limiter = limiter
        self._name = name or "ratelimiter"
        self._enable_control_plane = enable_control_plane
        self._client_id_extractor = client_id_extractor
        
        # Register with control plane if available
        if CONTROL_PLANE_AVAILABLE and enable_control_plane:
            register_pattern(
                pattern_type="ratelimit",
                name=self._name,
                manager=self._limiter,
                metadata={
                    "limiter_type": limiter.__class__.__name__,
                }
            )

    async def __aenter__(self) -> "ratelimiter":
        # Check if disabled via control plane
        if hasattr(self._limiter, '_enabled') and not self._limiter._enabled:
            return self
        
        # Note: context manager doesn't have access to request args
        # For FastAPI, use decorator pattern instead
        client_id = None
        if self._client_id_extractor:
            try:
                client_id = self._client_id_extractor()
            except:
                pass
        
        await self._limiter.acquire(client_id=client_id)
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> Optional[bool]:
        return None
    
    def _extract_client_id(self, *args, **kwargs) -> Optional[str]:
        """Extract client ID from context if extractor is provided"""
        if self._client_id_extractor:
            try:
                return self._client_id_extractor()
            except:
                pass
        
        # Try to extract from FastAPI Request in args
        from fastapi import Request
        for arg in args:
            if isinstance(arg, Request):
                from failsafe.integrations.fastapi_helpers import get_client_id_from_request
                return get_client_id_from_request(arg)
        
        return None

    def __call__(self, func: FuncT) -> FuncT:
        """Apply ratelimiter as a decorator"""

        @functools.wraps(func)
        async def _wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check if disabled via control plane
            if hasattr(self._limiter, '_enabled') and not self._limiter._enabled:
                return await func(*args, **kwargs)
            
            client_id = self._extract_client_id(*args, **kwargs)
            await self._limiter.acquire(client_id=client_id)
            return await func(*args, **kwargs)

        _wrapper._original = func  # type: ignore[attr-defined]
        _wrapper._manager = self._limiter  # type: ignore[attr-defined]

        return cast(FuncT, _wrapper)


class tokenbucket:
    """
    Constant Rate Limiting based on the Token Bucket algorithm with per-client tracking support.

    **Parameters**

    * **max_executions** *(float | None)* - How many executions are permitted? 
    * **per_time_secs** *(float | None)* - Per what time span? (in seconds)
    * **bucket_size** *(None | float)* - The token bucket size
    * **name** *(None | str)* - A component name or ID
    * **retry_after_strategy** *(RetryAfterStrategy | str)* - Strategy for calculating Retry-After
    * **retry_after_calculator** *(RetryAfterCalculator | None)* - Custom calculator
    * **enable_control_plane** *(bool)* - Enable control plane integration (default: True)
    * **track_latency** *(bool)* - Enable automatic latency tracking (default: True)
    * **enable_per_client_tracking** *(bool)* - Enable per-client state tracking (default: False)
    * **client_id_extractor** *(callable)* - Function to extract client_id from context
    """

    def __init__(
        self,
        max_executions: Optional[float] = None,
        per_time_secs: Optional[float] = None,
        bucket_size: Optional[float] = None,
        name: Optional[str] = None,
        retry_after_strategy: Optional[RetryAfterStrategy] = None,
        retry_after_calculator: Optional[RetryAfterCalculator] = None,
        enable_control_plane: bool = True,
        track_latency: bool = True,
        enable_per_client_tracking: bool = False,
        client_id_extractor: Optional[Callable] = None,
        func: Optional[FuncT] = None,
        # Strategy parameters
        window_size: Optional[int] = None,
        p95_baseline: Optional[float] = None,
        min_latency: Optional[float] = None,
        min_retry_delay: Optional[float] = None,
        max_retry_penalty: Optional[float] = None,
        gradient_sensitivity: Optional[float] = None,
        aggressive_threshold: Optional[float] = None,
        warning_threshold: Optional[float] = None,
        normal_threshold: Optional[float] = None,
        jitter_range_ms: Optional[float] = None,
        backoff_factor: Optional[float] = None,
        max_backoff_ms: Optional[float] = None,
    ) -> None:
        # Store the name - will be finalized in __call__ if not provided
        self._component_name = name
        self._enable_control_plane = enable_control_plane
        self._track_latency = track_latency
        self._enable_per_client_tracking = enable_per_client_tracking
        self._client_id_extractor = client_id_extractor
        
        # Check for configuration from control plane
        config = {}
        if CONTROL_PLANE_AVAILABLE and enable_control_plane and name:
            config = get_pattern_config("ratelimit", name)
        
        # Use explicit parameters, fallback to config, then defaults
        final_max_executions = (
            max_executions if max_executions is not None 
            else config.get("max_executions", 100)
        )
        final_per_time_secs = (
            per_time_secs if per_time_secs is not None 
            else config.get("per_time_secs", 60)
        )
        final_bucket_size = (
            bucket_size if bucket_size is not None 
            else config.get("bucket_size", None)
        )
        
        # Retry-After strategy configuration (default to BACKPRESSURE)
        final_strategy = (
            retry_after_strategy if retry_after_strategy is not None
            else config.get("retry_after_strategy", RetryAfterStrategy.BACKPRESSURE)
        )
        
        # Build calculator-specific kwargs
        calculator_kwargs = {}
        
        # Backpressure parameters
        if window_size is not None:
            calculator_kwargs['window_size'] = window_size
        if p95_baseline is not None:
            calculator_kwargs['p95_baseline'] = p95_baseline
        if min_latency is not None:
            calculator_kwargs['min_latency'] = min_latency
        if min_retry_delay is not None:
            calculator_kwargs['min_retry_delay'] = min_retry_delay
        if max_retry_penalty is not None:
            calculator_kwargs['max_retry_penalty'] = max_retry_penalty
        if gradient_sensitivity is not None:
            calculator_kwargs['gradient_sensitivity'] = gradient_sensitivity
        
        # Utilization parameters
        if aggressive_threshold is not None:
            calculator_kwargs['aggressive_threshold'] = aggressive_threshold
        if warning_threshold is not None:
            calculator_kwargs['warning_threshold'] = warning_threshold
        if normal_threshold is not None:
            calculator_kwargs['normal_threshold'] = normal_threshold
        
        # Other parameters
        if jitter_range_ms is not None:
            calculator_kwargs['jitter_range_ms'] = jitter_range_ms
        if backoff_factor is not None:
            calculator_kwargs['backoff_factor'] = backoff_factor
        if max_backoff_ms is not None:
            calculator_kwargs['max_backoff_ms'] = max_backoff_ms

        # Store config for later use when we know the function name
        self._final_max_executions = final_max_executions
        self._final_per_time_secs = final_per_time_secs
        self._final_bucket_size = final_bucket_size
        self._final_strategy = final_strategy
        self._retry_after_calculator = retry_after_calculator
        self._calculator_kwargs = calculator_kwargs
        
        # Create limiter - pattern_name will be set properly
        # Use provided name or a temporary one (will be updated in __call__)
        pattern_name = name or "tokenbucket"
        
        self._limiter = InstrumentedTokenBucketLimiter(
            max_executions=final_max_executions,
            per_time_secs=final_per_time_secs,
            bucket_size=final_bucket_size,
            pattern_name=pattern_name,  # THIS WAS MISSING!
            retry_after_strategy=final_strategy,
            retry_after_calculator=retry_after_calculator,
            enable_per_client_tracking=enable_per_client_tracking,
            **calculator_kwargs,
        )

        # Register with control plane
        if CONTROL_PLANE_AVAILABLE and enable_control_plane and name:
            create_control_plane_listener("tokenbucket", name)
            register_pattern(
                pattern_type="ratelimit",
                name=name,
                manager=self._limiter,
                metadata={
                    "max_executions": final_max_executions,
                    "per_time_secs": final_per_time_secs,
                    "bucket_size": final_bucket_size or final_max_executions,
                    "function": func.__qualname__ if func and hasattr(func, '__qualname__') else None,
                    "retry_after_strategy": str(final_strategy),
                    "per_client_tracking": enable_per_client_tracking,
                }
            )

    def _extract_client_id(self, *args, **kwargs) -> Optional[str]:
        """Extract client ID from context if extractor is provided"""
        if self._client_id_extractor:
            try:
                return self._client_id_extractor()
            except:
                pass
        
        # Try to extract from FastAPI Request in args
        try:
            from fastapi import Request
            for arg in args:
                if isinstance(arg, Request):
                    from failsafe.integrations.fastapi_helpers import get_client_id_from_request
                    return get_client_id_from_request(arg)
        except ImportError:
            pass
        
        return None

    async def __aenter__(self) -> "tokenbucket":
        # Check if disabled via control plane
        if hasattr(self._limiter, '_enabled') and not self._limiter._enabled:
            return self
        
        # Note: context manager doesn't have access to request args
        # For FastAPI with per-client tracking, use decorator pattern instead
        client_id = None
        if self._client_id_extractor:
            try:
                client_id = self._client_id_extractor()
            except:
                pass
        
        await self._limiter.acquire(client_id=client_id)
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> Optional[bool]:
        return None

    def __call__(self, func: FuncT) -> FuncT:
        """Apply ratelimiter as a decorator with automatic latency tracking"""
        
        # If name wasn't provided in __init__, use function name
        if self._component_name is None:
            self._component_name = get_default_name(func)
            
            # Recreate limiter with proper pattern name
            self._limiter = InstrumentedTokenBucketLimiter(
                max_executions=self._final_max_executions,
                per_time_secs=self._final_per_time_secs,
                bucket_size=self._final_bucket_size,
                pattern_name=self._component_name,  # Now with correct name!
                retry_after_strategy=self._final_strategy,
                retry_after_calculator=self._retry_after_calculator,
                enable_per_client_tracking=self._enable_per_client_tracking,
                **self._calculator_kwargs,
            )
            
            # Register with proper name
            if CONTROL_PLANE_AVAILABLE and self._enable_control_plane:
                register_pattern(
                    pattern_type="ratelimit",
                    name=self._component_name,
                    manager=self._limiter,
                    metadata={
                        "function": func.__qualname__ if hasattr(func, '__qualname__') else func.__name__,
                    }
                )

        @functools.wraps(func)
        async def _wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check if disabled via control plane
            if hasattr(self._limiter, '_enabled') and not self._limiter._enabled:
                return await func(*args, **kwargs)
            
            # Extract client ID from request args
            client_id = self._extract_client_id(*args, **kwargs)
            
            # Store limiter in request state for middleware/exception handlers
            try:
                from fastapi import Request
                for arg in args:
                    if isinstance(arg, Request):
                        arg.state.endpoint_limiter = self
                        arg.state.client_id = client_id
                        break
            except ImportError:
                pass
            
            # Acquire rate limit
            await self._limiter.acquire(client_id=client_id)
            
            # Track latency if enabled
            if self._track_latency:
                start_time = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    # Record latency in the limiter (which handles backpressure calc)
                    latency_seconds = time.perf_counter() - start_time
                    self._limiter.record_latency(latency_seconds, client_id=client_id)
            else:
                return await func(*args, **kwargs)

        _wrapper._original = func  # type: ignore[attr-defined]
        _wrapper._manager = self._limiter  # type: ignore[attr-defined]

        return cast(FuncT, _wrapper)
    
    def get_backpressure(self, client_id: Optional[str] = None) -> Optional[float]:
        """
        Get current backpressure score (0.0 to 1.0)
        
        Returns None if not using backpressure strategy.
        Use this to populate X-Backpressure header.
        """
        calc = self._limiter.retry_after_calculator
        if isinstance(calc, BackpressureCalculator):
            return calc.get_backpressure_header(client_id=client_id)
        return None