# integrations/opentelemetry/hedge.py
from typing import Any

from failsafe.hedge.events import HedgeListener
from failsafe.hedge.manager import HedgeManager

from opentelemetry.metrics import get_meter
from failsafe.integrations.opentelemetry.__version__ import __version__


class HedgeMetricListener(HedgeListener):
    def __init__(self, component: HedgeManager, namespace: str, meter=None, meter_provider=None) -> None:
        if meter is None:
            meter = get_meter(__name__, __version__, meter_provider)

        self._meter = meter
        prefix = f"{namespace}.{component.name}.hedge"

        self._success = meter.create_counter(name=f"{prefix}.success")
        self._failure = meter.create_counter(name=f"{prefix}.failure")
        self._all_failed = meter.create_counter(name=f"{prefix}.all_failed")
        self._timeout = meter.create_counter(name=f"{prefix}.timeout")

    async def on_hedge_success(self, hedge: "HedgeManager", result: Any) -> None:
        self._success.add(1)

    async def on_hedge_failure(self, hedge: "HedgeManager", exception: Exception) -> None:
        self._failure.add(1)

    async def on_hedge_all_failed(self, hedge: "HedgeManager") -> None:
        self._all_failed.add(1)

    async def on_hedge_timeout(self, hedge: "HedgeManager") -> None:
        self._timeout.add(1)
