"""
Enhanced ratelimit API with control plane integration
"""

import functools
from types import TracebackType
from typing import Any, Optional, Type, cast
from failsafe.events import get_default_name
from failsafe.ratelimit.managers import RateLimiter
from failsafe.ratelimit.instrumeted_managers import InstrumentedTokenBucketLimiter
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
    
    # Fallback stubs
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
    """

    def __init__(
        self,
        limiter: RateLimiter,
        name: Optional[str] = None,
        enable_control_plane: bool = True,
    ) -> None:
        self._limiter = limiter
        self._name = name or "ratelimiter"
        self._enable_control_plane = enable_control_plane
        
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
        
        await self._limiter.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> Optional[bool]:
        return None

    def __call__(self, func: FuncT) -> FuncT:
        """
        Apply ratelimiter as a decorator
        """

        @functools.wraps(func)
        async def _wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check if disabled via control plane
            if hasattr(self._limiter, '_enabled') and not self._limiter._enabled:
                return await func(*args, **kwargs)
            
            await self._limiter.acquire()
            return await func(*args, **kwargs)

        _wrapper._original = func  # type: ignore[attr-defined]
        _wrapper._manager = self._limiter  # type: ignore[attr-defined]

        return cast(FuncT, _wrapper)


class tokenbucket:
    """
    Constant Rate Limiting based on the Token Bucket algorithm.

    **Parameters**

    * **max_executions** *(float | None)* - How many executions are permitted? 
        If None, will use config from failsafe.yaml or default to 100.
    * **per_time_secs** *(float | None)* - Per what time span? (in seconds)
        If None, will use config from failsafe.yaml or default to 60.
    * **bucket_size** *(None | float)* - The token bucket size. Defines the max number of executions
        that are permitted to happen during bursts.
        The burst is when no executions have happened for a long time, and then you are receiving a
        bunch of them at the same time. Equal to *max_executions* by default.
    * **name** *(None | str)* - A component name or ID (will be passed to listeners and metrics)
    * **enable_control_plane** *(bool)* - Enable control plane integration (default: True)
    """

    def __init__(
        self,
        max_executions: Optional[float] = None,
        per_time_secs: Optional[float] = None,
        bucket_size: Optional[float] = None,
        name: Optional[str] = None,
        enable_control_plane: bool = True,
        func: Optional[FuncT] = None,  # For internal use when used as decorator
    ) -> None:
        # Determine component name
        self._component_name = name or get_default_name(func) if func else "tokenbucket"
        self._enable_control_plane = enable_control_plane
        
        # Check for configuration from control plane
        config = {}
        if CONTROL_PLANE_AVAILABLE and enable_control_plane:
            config = get_pattern_config("ratelimit", self._component_name)
        
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

        self._limiter = InstrumentedTokenBucketLimiter(
            max_executions=final_max_executions,
            per_time_secs=final_per_time_secs,
            bucket_size=final_bucket_size,
        )

        # Register with control plane
        if CONTROL_PLANE_AVAILABLE and enable_control_plane:
            register_pattern(
                pattern_type="ratelimit",
                name=self._component_name,
                manager=self._limiter,
                metadata={
                    "max_executions": final_max_executions,
                    "per_time_secs": final_per_time_secs,
                    "bucket_size": final_bucket_size or final_max_executions,
                    "function": func.__qualname__ if func and hasattr(func, '__qualname__') else None,
                }
            )

    async def __aenter__(self) -> "tokenbucket":
        # Check if disabled via control plane
        if hasattr(self._limiter, '_enabled') and not self._limiter._enabled:
            return self
        
        await self._limiter.acquire()  # Uses lazy bucket property internally
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> Optional[bool]:
        return None

    def __call__(self, func: FuncT) -> FuncT:
        """
        Apply ratelimiter as a decorator
        """
        
        # If name wasn't provided in __init__, use function name
        if self._component_name == "tokenbucket":
            self._component_name = get_default_name(func)
            
            # Re-register with proper name
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
            
            await self._limiter.acquire()
            return await func(*args, **kwargs)

        _wrapper._original = func  # type: ignore[attr-defined]
        _wrapper._manager = self._limiter  # type: ignore[attr-defined]

        return cast(FuncT, _wrapper)