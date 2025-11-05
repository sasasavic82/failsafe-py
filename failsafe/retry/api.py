"""
Enhanced retry API with control plane integration
"""

import functools
from typing import Any, Callable, Optional, Sequence, cast

from failsafe.events import EventDispatcher, EventManager, get_default_name
from failsafe.ratelimit.buckets import TokenBucket
from failsafe.retry.events import _RETRY_LISTENERS, RetryListener
from failsafe.retry.manager import RetryManager
from failsafe.retry.typing import AttemptsT, BackoffsT, BucketRetryT
from failsafe.typing import ExceptionsT, FuncT

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


def retry(
    *,
    on: ExceptionsT = Exception,
    attempts: Optional[AttemptsT] = None,
    backoff: Optional[BackoffsT] = None,
    name: Optional[str] = None,
    listeners: Optional[Sequence[RetryListener]] = None,
    event_manager: Optional["EventManager"] = None,
    enable_control_plane: bool = True,
) -> Callable[[Callable], Callable]:
    """
    `@retry()` decorator retries the function `on` exceptions for the given number of `attempts`.
    Delays after each retry is defined by `backoff` strategy.

    **Parameters:**

    * **on** - Exception or tuple of Exceptions we need to retry on.
    * **attempts** - How many times do we need to retry. If `None`, will use config or default to 3.
    * **backoff** - Backoff Strategy that defines delays on each retry.
        Takes `float` numbers (delay in secs), `list[floats]` (delays on each retry attempt), or `Iterator[float]`
    * **name** *(None | str)* - A component name or ID (will be passed to listeners and mention in metrics)
    * **listeners** *(None | Sequence[RetryListener])* - List of listeners of this concrete component state
    * **enable_control_plane** *(bool)* - Enable control plane integration (default: True)
    """

    def _decorator(func: FuncT) -> FuncT:
        component_name = name or get_default_name(func)
        
        # Check for configuration from control plane
        config = {}
        if CONTROL_PLANE_AVAILABLE and enable_control_plane:
            config = get_pattern_config("retry", component_name)
        
        # Use explicit parameters, fallback to config, then defaults
        final_attempts = attempts if attempts is not None else config.get("attempts", 3)
        final_backoff = backoff if backoff is not None else config.get("backoff", 0.5)
        
        # Add control plane listener if available
        local_listeners = list(listeners) if listeners else []
        if CONTROL_PLANE_AVAILABLE and enable_control_plane:
            cp_listener = create_control_plane_listener("retry", component_name)
            if cp_listener:
                local_listeners.append(cp_listener)
        
        event_dispatcher = EventDispatcher[RetryManager, RetryListener](
            local_listeners,
            _RETRY_LISTENERS,
            event_manager=event_manager,
        )

        manager = RetryManager(
            name=component_name,
            exceptions=on,
            attempts=final_attempts,
            backoff=final_backoff,
            event_dispatcher=event_dispatcher.as_listener,
        )

        event_dispatcher.set_component(manager)
        
        # Register with control plane
        if CONTROL_PLANE_AVAILABLE and enable_control_plane:
            register_pattern(
                pattern_type="retry",
                name=component_name,
                manager=manager,
                metadata={
                    "on": str(on),
                    "attempts": final_attempts,
                    "backoff": str(final_backoff),
                    "function": func.__qualname__ if hasattr(func, '__qualname__') else func.__name__,
                }
            )

        @functools.wraps(func)
        async def _wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check if pattern is disabled via control plane
            if hasattr(manager, '_enabled') and not manager._enabled:
                # If disabled, just call the function directly without retry
                return await func(*args, **kwargs)
            
            return await manager(cast(FuncT, functools.partial(func, *args, **kwargs)))

        _wrapper._original = func  # type: ignore[attr-defined]
        _wrapper._manager = manager  # type: ignore[attr-defined]

        return cast(FuncT, _wrapper)

    return _decorator


def bucket_retry(
    *,
    on: ExceptionsT = Exception,
    attempts: Optional[AttemptsT] = None,
    backoff: Optional[BackoffsT] = None,
    name: Optional[str] = None,
    per_time_secs: Optional[BucketRetryT] = None,
    bucket_size: Optional[BucketRetryT] = None,
    listeners: Optional[Sequence[RetryListener]] = None,
    event_manager: Optional["EventManager"] = None,
    enable_control_plane: bool = True,
) -> Callable[[Callable], Callable]:
    """
    `@bucket_retry()` decorator retries until we have tokens in the bucket and at most that number of times per request.
    """

    def _decorator(func: FuncT) -> FuncT:
        component_name = name or get_default_name(func)
        
        # Check for configuration from control plane
        config = {}
        if CONTROL_PLANE_AVAILABLE and enable_control_plane:
            config = get_pattern_config("bucket_retry", component_name)
        
        # Use explicit parameters, fallback to config, then defaults
        final_attempts = attempts if attempts is not None else config.get("attempts", 3)
        final_backoff = backoff if backoff is not None else config.get("backoff", 0.5)
        final_per_time_secs = per_time_secs if per_time_secs is not None else config.get("per_time_secs", 1)
        final_bucket_size = bucket_size if bucket_size is not None else config.get("bucket_size", 3)
        
        limiter = TokenBucket(final_attempts, final_per_time_secs, final_bucket_size) if final_attempts and final_per_time_secs else None
        
        # Add control plane listener if available
        local_listeners = list(listeners) if listeners else []
        if CONTROL_PLANE_AVAILABLE and enable_control_plane:
            cp_listener = create_control_plane_listener("bucket_retry", component_name)
            if cp_listener:
                local_listeners.append(cp_listener)
        
        event_dispatcher = EventDispatcher[RetryManager, RetryListener](
            local_listeners,
            _RETRY_LISTENERS,
            event_manager=event_manager,
        )

        manager = RetryManager(
            name=component_name,
            exceptions=on,
            attempts=final_attempts,
            backoff=final_backoff,
            event_dispatcher=event_dispatcher.as_listener,
            limiter=limiter,
        )

        event_dispatcher.set_component(manager)
        
        # Register with control plane
        if CONTROL_PLANE_AVAILABLE and enable_control_plane:
            register_pattern(
                pattern_type="bucket_retry",
                name=component_name,
                manager=manager,
                metadata={
                    "on": str(on),
                    "attempts": final_attempts,
                    "backoff": str(final_backoff),
                    "per_time_secs": final_per_time_secs,
                    "bucket_size": final_bucket_size,
                    "function": func.__qualname__ if hasattr(func, '__qualname__') else func.__name__,
                }
            )

        @functools.wraps(func)
        async def _wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check if pattern is disabled via control plane
            if hasattr(manager, '_enabled') and not manager._enabled:
                return await func(*args, **kwargs)
            
            return await manager(cast(FuncT, functools.partial(func, *args, **kwargs)))

        _wrapper._original = func  # type: ignore[attr-defined]
        _wrapper._manager = manager  # type: ignore[attr-defined]

        return cast(FuncT, _wrapper)

    return _decorator