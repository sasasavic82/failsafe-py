# integrations/opentelemetry/fallback.py
from typing import Any

from failsafe.fallback.manager import FallbackManager
from failsafe.fallback.events import FallbackListener

from opentelemetry.metrics import get_meter
from failsafe.integrations.opentelemetry.__version__ import __version__


class FallbackMetricListener(FallbackListener):
    def __init__(self, component: FallbackManager, namespace: str, meter=None, meter_provider=None) -> None:
        meter = meter or get_meter(__name__, __version__, meter_provider)
        name = getattr(component, "name", None) or getattr(component, "_name", None)
        prefix = f"{namespace}.{name}.fallback" if name else f"{namespace}.fallback"

        self._invoked = meter.create_counter(f"{prefix}.invoked")

    async def on_fallback(self, fallback: "FallbackManager", result: Any, *args: Any, **kwargs: Any) -> None:
        self._invoked.add(1)
