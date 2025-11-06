# integrations/opentelemetry/failfast.py
from failsafe.failfast.events import FailFastListener
from failsafe.failfast.manager import FailFastManager

from opentelemetry.metrics import get_meter
from failsafe.integrations.opentelemetry.__version__ import __version__


class FailFastMetricListener(FailFastListener):
    def __init__(self, component: FailFastManager, namespace: str, meter=None, meter_provider=None) -> None:
        if meter is None:
            meter = get_meter(__name__, __version__, meter_provider)

        self._meter = meter
        prefix = f"{namespace}.{component.name}.failfast"

        self._opened = meter.create_counter(name=f"{prefix}.opened")
        self._closed = meter.create_counter(name=f"{prefix}.closed")

    async def on_failfast_open(self, failfast: "FailFastManager") -> None:
        self._opened.add(1)

    async def on_failfast_close(self, failfast: "FailFastManager") -> None:
        self._closed.add(1)
