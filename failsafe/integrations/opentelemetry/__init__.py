from typing import Optional, Generic, Type, TypeVar

from opentelemetry.metrics import Meter, MeterProvider

# Retry
from failsafe.retry import register_retry_listener
from failsafe.retry.manager import RetryManager
from failsafe.integrations.opentelemetry.retry import RetryMetricListener

# FailFast
from failsafe.failfast import register_failfast_listener
from failsafe.failfast.manager import FailFastManager
from failsafe.integrations.opentelemetry.failfast import FailFastMetricListener

# FeatureToggle
from failsafe.featuretoggle import register_featuretoggle_listener
from failsafe.featuretoggle.manager import FeatureToggleManager
from failsafe.integrations.opentelemetry.featuretoggle import FeatureToggleMetricListener

# Hedge
from failsafe.hedge import register_hedge_listener
from failsafe.hedge.manager import HedgeManager
from failsafe.integrations.opentelemetry.hedge import HedgeMetricListener

# Cache
from failsafe.cache.events import register_cache_listener
from failsafe.cache.manager import CacheManager
from failsafe.integrations.opentelemetry.cache import CacheMetricListener

# Bulkhead
from failsafe.bulkhead.events import register_bulkhead_listener
from failsafe.bulkhead.manager import BulkheadManager
from failsafe.integrations.opentelemetry.bulkhead import BulkheadMetricListener

# Circuit Breaker
from failsafe.circuitbreaker.events import register_breaker_listener
from failsafe.circuitbreaker.managers import ConsecutiveCircuitBreaker
from failsafe.integrations.opentelemetry.circuitbreaker import CircuitBreakerMetricListener

# Fallback  (events file names the registrar incorrectly; alias it here)
from failsafe.fallback.events import register_timeout_listener as register_fallback_listener  # noqa: N811
from failsafe.fallback.manager import FallbackManager
from failsafe.integrations.opentelemetry.fallback import FallbackMetricListener

# Timeout
from failsafe.timeout.events import register_timeout_listener
from failsafe.timeout.manager import TimeoutManager
from failsafe.integrations.opentelemetry.timeout import TimeoutMetricListener

ComponentT = TypeVar("ComponentT")
ListenerT = TypeVar("ListenerT")


class Factory(Generic[ComponentT, ListenerT]):
    def __init__(self, listener_class: Type[ListenerT], *args, **kwargs) -> None:
        self.listener_class = listener_class
        self.args = args
        self.kwargs = kwargs

    async def __call__(self, component: ComponentT) -> ListenerT:
        # All resiliency components are async-only; listeners are async-aware instances
        return self.listener_class(component, *self.args, **self.kwargs)


class FailsafeOtelInstrumentor:
    def instrument(
        self,
        *,
        namespace: str = "failsafe.service",
        meter: Optional[Meter] = None,
        meter_provider: Optional[MeterProvider] = None,
    ) -> None:

        register_retry_listener(
            Factory[RetryManager, RetryMetricListener](
                RetryMetricListener,
                namespace=namespace,
                meter=meter,
                meter_provider=meter_provider,
            )
        )

        register_failfast_listener(
            Factory[FailFastManager, FailFastMetricListener](
                FailFastMetricListener,
                namespace=namespace,
                meter=meter,
                meter_provider=meter_provider,
            )
        )

        register_featuretoggle_listener(
            Factory[FeatureToggleManager, FeatureToggleMetricListener](
                FeatureToggleMetricListener,
                namespace=namespace,
                meter=meter,
                meter_provider=meter_provider,
            )
        )

        register_hedge_listener(
            Factory[HedgeManager, HedgeMetricListener](
                HedgeMetricListener,
                namespace=namespace,
                meter=meter,
                meter_provider=meter_provider,
            )
        )

        register_cache_listener(
            Factory[CacheManager, CacheMetricListener](
                CacheMetricListener,
                namespace=namespace,
                meter=meter,
                meter_provider=meter_provider,
            )
        )

        register_bulkhead_listener(
            Factory[BulkheadManager, BulkheadMetricListener](
                BulkheadMetricListener,
                namespace=namespace,
                meter=meter,
                meter_provider=meter_provider,
            )
        )

        register_breaker_listener(
            Factory[ConsecutiveCircuitBreaker, CircuitBreakerMetricListener](
                CircuitBreakerMetricListener,
                namespace=namespace,
                meter=meter,
                meter_provider=meter_provider,
            )
        )

        register_fallback_listener(
            Factory[FallbackManager, FallbackMetricListener](
                FallbackMetricListener,
                namespace=namespace,
                meter=meter,
                meter_provider=meter_provider,
            )
        )

        register_timeout_listener(
            Factory[TimeoutManager, TimeoutMetricListener](
                TimeoutMetricListener,
                namespace=namespace,
                meter=meter,
                meter_provider=meter_provider,
            )
        )
