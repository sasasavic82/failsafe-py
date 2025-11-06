# integrations/opentelemetry/cache.py
from typing import Any

from failsafe.cache.manager import CacheManager
from failsafe.cache.events import CacheListener

from opentelemetry.metrics import get_meter
from failsafe.integrations.opentelemetry.__version__ import __version__


class CacheMetricListener(CacheListener):
    def __init__(self, component: CacheManager, namespace: str, meter=None, meter_provider=None) -> None:
        meter = meter or get_meter(__name__, __version__, meter_provider)
        name = getattr(component, "name", None)
        prefix = f"{namespace}.{name}.cache" if name else f"{namespace}.cache"

        self._hit = meter.create_counter(f"{prefix}.hit")
        self._miss = meter.create_counter(f"{prefix}.miss")
        self._set = meter.create_counter(f"{prefix}.set")

    async def on_cache_hit(self, cache: "CacheManager", key: Any, value: Any) -> None:
        self._hit.add(1)

    async def on_cache_miss(self, cache: "CacheManager", key: Any) -> None:
        self._miss.add(1)

    async def on_cache_set(self, cache: "CacheManager", key: Any, value: Any) -> None:
        self._set.add(1)
