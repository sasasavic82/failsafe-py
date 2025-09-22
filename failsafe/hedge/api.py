# failsafe/hedge/api.py
import asyncio
import functools
from typing import Any, Optional, Sequence, Callable, cast

from failsafe.hedge.events import HedgeListener
from failsafe.hedge.manager import HedgeManager
from failsafe.hedge.typing import FuncT


class _CompositeListener(HedgeListener):
    """Await listeners inline; no background tasks."""

    def __init__(self, listeners: Optional[Sequence[HedgeListener]] = None) -> None:
        self._listeners = tuple(listeners or ())

    async def on_hedge_success(self, hedge: "HedgeManager", result: Any) -> None:
        for l in self._listeners:
            await l.on_hedge_success(hedge, result)

    async def on_hedge_failure(self, hedge: "HedgeManager", exception: Exception) -> None:
        for l in self._listeners:
            await l.on_hedge_failure(hedge, exception)

    async def on_hedge_all_failed(self, hedge: "HedgeManager") -> None:
        for l in self._listeners:
            await l.on_hedge_all_failed(hedge)

    async def on_hedge_timeout(self, hedge: "HedgeManager") -> None:
        for l in self._listeners:
            # Optional hook; listeners may not implement it explicitly
            if hasattr(l, "on_hedge_timeout"):
                await l.on_hedge_timeout(hedge)  # type: ignore[attr-defined]


class _WrappedHedge:
    """
    Callable (awaitable) wrapper and async context manager using the same manager.
    """

    def __init__(self, func: FuncT, manager: HedgeManager) -> None:
        self._original = func
        self._manager = manager
        functools.update_wrapper(self, func)

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self._manager(self._original, *args, **kwargs)

    async def __aenter__(self):
        return await self._manager.__aenter__()

    async def __aexit__(self, exc_type, exc, tb):
        return await self._manager.__aexit__(exc_type, exc, tb)


class _HedgeFactory:
    """
    Async-only decorator + async context manager backed by a single HedgeManager.
    """

    def __init__(
        self,
        *,
        attempts: int,
        delay: float,
        timeout: Optional[float],
        name: Optional[str],
        listeners: Optional[Sequence[HedgeListener]],
        event_manager: Optional[object],  # accepted for API parity; unused
    ) -> None:
        self._manager = HedgeManager(
            attempts=attempts,
            delay=delay,
            timeout=timeout,
            event_dispatcher=_CompositeListener(listeners),
            name=name,
        )

    def __call__(self, func: FuncT) -> _WrappedHedge:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("@hedge requires an async function")
        return _WrappedHedge(func, self._manager)

    async def __aenter__(self):
        return await self._manager.__aenter__()

    async def __aexit__(self, exc_type, exc, tb):
        return await self._manager.__aexit__(exc_type, exc, tb)


def hedge(
    *,
    attempts: int = 2,
    delay: float = 0.0,
    timeout: Optional[float] = None,
    name: Optional[str] = None,
    listeners: Optional[Sequence[HedgeListener]] = None,
    event_manager: Optional[object] = None,
) -> Callable[[Callable], _WrappedHedge]:
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    if delay < 0:
        raise ValueError("delay must be >= 0")
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be > 0 when provided")

    return _HedgeFactory(
        attempts=attempts,
        delay=delay,
        timeout=timeout,
        name=name,
        listeners=listeners,
        event_manager=event_manager,
    )
