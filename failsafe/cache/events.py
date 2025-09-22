
from typing import TYPE_CHECKING, Any, Union
from failsafe.events import ListenerFactoryT, ListenerRegistry

if TYPE_CHECKING:
	from failsafe.cache.manager import CacheManager

_CACHE_LISTENERS: ListenerRegistry["CacheManager", "CacheListener"] = ListenerRegistry()

class CacheListener:
	async def on_cache_hit(self, cache: "CacheManager", key: Any, value: Any) -> None:
		pass

	async def on_cache_miss(self, cache: "CacheManager", key: Any) -> None:
		pass

	async def on_cache_set(self, cache: "CacheManager", key: Any, value: Any) -> None:
		pass

def register_cache_listener(listener: Union[CacheListener, ListenerFactoryT]) -> None:
	global _CACHE_LISTENERS
	_CACHE_LISTENERS.register(listener)
