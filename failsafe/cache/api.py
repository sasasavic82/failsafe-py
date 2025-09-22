
import functools
from typing import Any, Optional, Sequence, cast, Callable
from failsafe.events import EventDispatcher, EventManager, get_default_name
from failsafe.cache.events import _CACHE_LISTENERS, CacheListener
from failsafe.cache.manager import CacheManager
from failsafe.cache.typing import FuncT, KeyFuncT


def cache(
    *,
    maxsize: Optional[int] = None,
    key_func: Optional[KeyFuncT] = None,
    name: Optional[str] = None,
    listeners: Optional[Sequence[CacheListener]] = None,
    event_manager: Optional["EventManager"] = None,
) -> Callable[[Callable], Callable]:
    """
    The cache pattern caches results of expensive operations to avoid repeated work
    and improve reliability under load.

    **Parameters:**
        * **maxsize** - Maximum number of items to store in the cache (evicts LRU if exceeded)
        * **key_func** - Function to generate a cache key from arguments (default: args+kwargs tuple)
        * **name** - Optional name for the cache component
        * **listeners** - Optional sequence of CacheListener for event handling
        * **event_manager** - Optional EventManager for event dispatching
    """
    def _decorator(func: FuncT) -> FuncT:
        if maxsize is not None and maxsize < 1:
            raise ValueError("maxsize must be >= 1 if specified")
        event_dispatcher = EventDispatcher[CacheManager, CacheListener](
            listeners,
            _CACHE_LISTENERS,
            event_manager=event_manager,
        )
        manager = CacheManager(
            maxsize=maxsize,
            key_func=key_func,
            event_dispatcher=event_dispatcher.as_listener,
            name=name or get_default_name(func),
        )
        event_dispatcher.set_component(manager)


        @functools.wraps(func)
        async def _wrapper(*args: Any, **kwargs: Any) -> Any:
            return await manager(func, *args, **kwargs)

        _wrapper._original = func  # type: ignore[attr-defined]
        _wrapper._manager = manager  # type: ignore[attr-defined]
        return cast(FuncT, _wrapper)

    return _decorator
