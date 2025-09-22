
import asyncio
from typing import Any, Callable, Optional
from collections import OrderedDict
from failsafe.cache.events import CacheListener

from failsafe.cache.typing import FuncT, KeyFuncT

class CacheManager:
    """
    CacheManager caches results of expensive operations to avoid repeated work
    and improve reliability.
    """
    def __init__(
        self,
        maxsize: Optional[int] = None,
        key_func: Optional[KeyFuncT] = None,
        event_dispatcher: Optional[CacheListener] = None,
        name: Optional[str] = None,
    ) -> None:
        if maxsize is not None and maxsize < 1:
            raise ValueError("maxsize must be >= 1 if specified")
        self._maxsize = maxsize
        self._cache: "OrderedDict[Any, Any]" = OrderedDict()
        self._key_func = key_func
        self._event_dispatcher = event_dispatcher
        self._name = name

    @property
    def name(self) -> Optional[str]:
        return self._name

    def _make_key(self, *args: Any, **kwargs: Any) -> Any:
        if self._key_func:
            return self._key_func(*args, **kwargs)
        # Default: use args and kwargs as a tuple
        return (args, frozenset(kwargs.items()))

    async def __call__(self, func: FuncT, *args: Any, **kwargs: Any) -> Any:
        key = self._make_key(*args, **kwargs)
        if key in self._cache:
            self._cache.move_to_end(key)
            if self._event_dispatcher:
                await self._event_dispatcher.on_cache_hit(
                    self, key, self._cache[key]
                )
            return self._cache[key]
        if self._event_dispatcher:
            await self._event_dispatcher.on_cache_miss(self, key)
        result = await func(*args, **kwargs)
        self._cache[key] = result
        if self._maxsize is not None and self._maxsize > 0:
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)
        if self._event_dispatcher:
            await self._event_dispatcher.on_cache_set(self, key, result)
        return result
