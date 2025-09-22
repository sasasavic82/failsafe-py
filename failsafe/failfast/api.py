import asyncio
import functools
from typing import Any, Optional, Sequence, cast, Callable

from failsafe.failfast.events import FailFastListener
from failsafe.failfast.manager import FailFastManager
from failsafe.failfast.typing import FuncT, PredicateT


class _CompositeListener(FailFastListener):
    """
    Async-only, in-process dispatcher that awaits each listener inline.
    Eliminates fire-and-forget tasks and pending-teardown warnings.
    """

    def __init__(self, listeners: Optional[Sequence[FailFastListener]] = None) -> None:
        self._listeners: tuple[FailFastListener, ...] = tuple(listeners or ())

    async def on_failfast_open(self, failfast: "FailFastManager") -> None:
        for listener in self._listeners:
            await listener.on_failfast_open(failfast)

    async def on_failfast_close(self, failfast: "FailFastManager") -> None:
        for listener in self._listeners:
            await listener.on_failfast_close(failfast)


class _FailfastFactory:
    """
    Async-only dual mode:
      • Decorator for async callables
      • Async context manager
    """

    def __init__(
        self,
        *,
        failure_threshold: Optional[int],
        predicate: Optional[PredicateT],
        name: Optional[str],
        listeners: Optional[Sequence[FailFastListener]],
        event_manager: Optional[object],  # accepted for API parity; unused
    ) -> None:
        self._manager = FailFastManager(
            failure_threshold=failure_threshold,
            predicate=predicate,
            event_dispatcher=_CompositeListener(listeners),
            name=name,
        )

    def __call__(self, func: FuncT) -> FuncT:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("@failfast requires an async function")

        @functools.wraps(func)
        async def _wrapper(*args: Any, **kwargs: Any) -> Any:
            return await self._manager(func, *args, **kwargs)

        # Expose async context manager on the wrapped function (same manager instance)
        _wrapper.__aenter__ = self._manager.__aenter__  # type: ignore[attr-defined]
        _wrapper.__aexit__ = self._manager.__aexit__    # type: ignore[attr-defined]
        _wrapper._original = func  # type: ignore[attr-defined]
        _wrapper._manager = self._manager  # type: ignore[attr-defined]
        return cast(FuncT, _wrapper)

    async def __aenter__(self):
        return await self._manager.__aenter__()

    async def __aexit__(self, exc_type, exc, tb):
        return await self._manager.__aexit__(exc_type, exc, tb)


def failfast(
    *,
    failure_threshold: Optional[int] = None,
    predicate: Optional[PredicateT] = None,
    name: Optional[str] = None,
    listeners: Optional[Sequence[FailFastListener]] = None,
    event_manager: Optional[object] = None,
) -> Callable[[Callable], Callable]:
    if failure_threshold is not None and failure_threshold < 1:
        raise ValueError("failure_threshold must be >= 1 if specified")

    return _FailfastFactory(
        failure_threshold=failure_threshold,
        predicate=predicate,
        name=name,
        listeners=listeners,
        event_manager=event_manager,
    )
