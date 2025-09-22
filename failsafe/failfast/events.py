
from typing import TYPE_CHECKING, Any, Union
from failsafe.events import ListenerFactoryT, ListenerRegistry

if TYPE_CHECKING:
	from failsafe.failfast.manager import FailFastManager

_FAILFAST_LISTENERS: ListenerRegistry["FailFastManager", "FailFastListener"] = ListenerRegistry()

class FailFastListener:
	async def on_failfast_open(self, failfast: "FailFastManager") -> None:
		pass

	async def on_failfast_close(self, failfast: "FailFastManager") -> None:
		pass

def register_failfast_listener(listener: Union[FailFastListener, ListenerFactoryT]) -> None:
	global _FAILFAST_LISTENERS
	_FAILFAST_LISTENERS.register(listener)
