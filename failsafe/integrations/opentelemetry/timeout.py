# integrations/opentelemetry/timeout.py
from failsafe.timeout.manager import TimeoutManager
from failsafe.timeout.events import TimeoutListener

from opentelemetry.metrics import get_meter
from failsafe.integrations.opentelemetry.__version__ import __version__


class TimeoutMetricListener(TimeoutListener):
    def __init__(self, component: TimeoutManager, namespace: str, meter=None, meter_provider=None) -> None:
        meter = meter or get_meter(__name__, __version__, meter_provider)
        name = getattr(component, "name", None) or getattr(component, "_name", None)
        prefix = f"{namespace}.{name}.timeout" if name else f"{namespace}.timeout"

        self._timeout = meter.create_counter(f"{prefix}.fired")

    async def on_timeout(self, timeout: "TimeoutManager") -> None:
        self._timeout.add(1)
