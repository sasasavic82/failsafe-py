# failsafe/hedge/events.py
from typing import TYPE_CHECKING, Any, Union
from failsafe.events import ListenerFactoryT, ListenerRegistry

if TYPE_CHECKING:
    from failsafe.hedge.manager import HedgeManager

_HEDGE_LISTENERS: ListenerRegistry["HedgeManager", "HedgeListener"] = ListenerRegistry()


class HedgeListener:
    async def on_hedge_success(self, hedge: "HedgeManager", result: Any) -> None:
        ...

    async def on_hedge_failure(self, hedge: "HedgeManager", exception: Exception) -> None:
        ...

    async def on_hedge_all_failed(self, hedge: "HedgeManager") -> None:
        ...

    # new optional hook for timeouts
    async def on_hedge_timeout(self, hedge: "HedgeManager") -> None:
        ...


def register_hedge_listener(listener: Union["HedgeListener", ListenerFactoryT]) -> None:
    global _HEDGE_LISTENERS
    _HEDGE_LISTENERS.register(listener)
