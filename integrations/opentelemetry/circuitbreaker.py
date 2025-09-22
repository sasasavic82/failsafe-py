# integrations/opentelemetry/circuitbreaker.py
from failsafe.circuitbreaker.managers import ConsecutiveCircuitBreaker
from failsafe.circuitbreaker.events import BreakerListener
from failsafe.circuitbreaker.context import BreakerContext
from failsafe.circuitbreaker.states import BreakerState, WorkingState, RecoveringState, FailingState  # type: ignore

from opentelemetry.metrics import get_meter
from integrations.opentelemetry.__version__ import __version__


class CircuitBreakerMetricListener(BreakerListener):
    def __init__(self, component: ConsecutiveCircuitBreaker, namespace: str, meter=None, meter_provider=None) -> None:
        meter = meter or get_meter(__name__, __version__, meter_provider)
        # component may not expose a public .name; fall back safely
        name = getattr(component, "name", None) or getattr(component, "_name", None)
        base = f"{namespace}.{name}.circuitbreaker" if name else f"{namespace}.circuitbreaker"

        self._to_working = meter.create_counter(f"{base}.transition.working")
        self._to_recovering = meter.create_counter(f"{base}.transition.recovering")
        self._to_failing = meter.create_counter(f"{base}.transition.failing")
        self._success = meter.create_counter(f"{base}.success")

    async def on_working(self, context: BreakerContext, current_state: BreakerState, next_state: WorkingState) -> None:
        self._to_working.add(1)

    async def on_recovering(self, context: BreakerContext, current_state: BreakerState, next_state: RecoveringState) -> None:
        self._to_recovering.add(1)

    async def on_failing(self, context: BreakerContext, current_state: BreakerState, next_state: FailingState) -> None:
        self._to_failing.add(1)

    async def on_success(self, context: BreakerContext, state: BreakerState) -> None:
        self._success.add(1)
