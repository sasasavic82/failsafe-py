# integrations/opentelemetry/featuretoggle.py
from failsafe.featuretoggle.events import FeatureToggleListener
from failsafe.featuretoggle.manager import FeatureToggleManager

from opentelemetry.metrics import get_meter
from integrations.opentelemetry.__version__ import __version__


class FeatureToggleMetricListener(FeatureToggleListener):
    def __init__(self, component: FeatureToggleManager, namespace: str, meter=None, meter_provider=None) -> None:
        if meter is None:
            meter = get_meter(__name__, __version__, meter_provider)

        self._meter = meter
        prefix = f"{namespace}.{component.name}.featuretoggle"

        self._enabled = meter.create_counter(name=f"{prefix}.enabled")
        self._disabled = meter.create_counter(name=f"{prefix}.disabled")

    async def on_feature_enabled(self, toggle: "FeatureToggleManager") -> None:
        self._enabled.add(1)

    async def on_feature_disabled(self, toggle: "FeatureToggleManager") -> None:
        self._disabled.add(1)
