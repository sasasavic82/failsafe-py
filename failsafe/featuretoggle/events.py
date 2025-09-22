
from typing import TYPE_CHECKING, Union
from failsafe.events import ListenerFactoryT, ListenerRegistry

if TYPE_CHECKING:
	from failsafe.featuretoggle.manager import FeatureToggleManager


_FEATURETOGGLE_LISTENERS: ListenerRegistry[
	"FeatureToggleManager", "FeatureToggleListener"
] = ListenerRegistry()


class FeatureToggleListener:
	async def on_feature_enabled(self, toggle: "FeatureToggleManager") -> None:
		pass

	async def on_feature_disabled(self, toggle: "FeatureToggleManager") -> None:
		pass


def register_featuretoggle_listener(
	listener: Union[FeatureToggleListener, ListenerFactoryT]
) -> None:
	global _FEATURETOGGLE_LISTENERS
	_FEATURETOGGLE_LISTENERS.register(listener)
