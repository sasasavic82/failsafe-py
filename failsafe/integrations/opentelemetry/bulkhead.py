# integrations/opentelemetry/bulkhead.py
from failsafe.bulkhead.manager import BulkheadManager
from failsafe.bulkhead.events import BulkheadListener

from opentelemetry.metrics import get_meter
from failsafe.integrations.opentelemetry.__version__ import __version__


class BulkheadMetricListener(BulkheadListener):
    def __init__(self, component: BulkheadManager, namespace: str, meter=None, meter_provider=None) -> None:
        meter = meter or get_meter(__name__, __version__, meter_provider)
        name = getattr(component, "name", None) or getattr(component, "_name", None)
        prefix = f"{namespace}.{name}.bulkhead" if name else f"{namespace}.bulkhead"

        self._full = meter.create_counter(f"{prefix}.full")

    async def on_bulkhead_full(self, bulkhead: "BulkheadManager") -> None:
        self._full.add(1)
