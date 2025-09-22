# failsafe/featuretoggle/api.py
import asyncio
import functools
from typing import Any, Optional, Sequence, cast, Callable

from failsafe.featuretoggle.events import FeatureToggleListener
from failsafe.featuretoggle.manager import FeatureToggleManager
from failsafe.featuretoggle.typing import FuncT, TogglePredicateT


class _CompositeListener(FeatureToggleListener):
    """Await listeners inline; no background tasks."""

    def __init__(self, listeners: Optional[Sequence[FeatureToggleListener]] = None) -> None:
        self._listeners = tuple(listeners or ())

    async def on_feature_enabled(self, toggle: "FeatureToggleManager") -> None:
        for l in self._listeners:
            await l.on_feature_enabled(toggle)

    async def on_feature_disabled(self, toggle: "FeatureToggleManager") -> None:
        for l in self._listeners:
            await l.on_feature_disabled(toggle)


class _WrappedToggle:
    """
    Instance is both:
      • awaitable callable (via __call__)
      • async context manager (via __aenter__/__aexit__)
    Special methods must live on the class, not be set on a function object.
    """

    def __init__(self, func: FuncT, manager: FeatureToggleManager) -> None:
        self._original = func
        self._manager = manager
        # propagate metadata for introspection
        functools.update_wrapper(self, func)  # sets __name__, __doc__, __wrapped__, etc.

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self._manager(self._original, *args, **kwargs)

    async def __aenter__(self):
        return await self._manager.__aenter__()

    async def __aexit__(self, exc_type, exc, tb):
        return await self._manager.__aexit__(exc_type, exc, tb)


class _FeatureToggleFactory:
    """Async-only decorator + async context manager backed by a single manager instance."""

    def __init__(
        self,
        *,
        enabled: bool,
        predicate: Optional[TogglePredicateT],
        name: Optional[str],
        listeners: Optional[Sequence[FeatureToggleListener]],
        event_manager: Optional[object],  # accepted for API parity; unused
    ) -> None:
        self._manager = FeatureToggleManager(
            enabled=enabled,
            predicate=predicate,
            event_dispatcher=_CompositeListener(listeners),
            name=name,
        )

    def __call__(self, func: FuncT) -> _WrappedToggle:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("@featuretoggle requires an async function")
        return _WrappedToggle(func, self._manager)

    async def __aenter__(self):
        return await self._manager.__aenter__()

    async def __aexit__(self, exc_type, exc, tb):
        return await self._manager.__aexit__(exc_type, exc, tb)


def featuretoggle(
    *,
    enabled: bool = True,
    predicate: Optional[TogglePredicateT] = None,
    name: Optional[str] = None,
    listeners: Optional[Sequence[FeatureToggleListener]] = None,
    event_manager: Optional[object] = None,
) -> Callable[[Callable], _WrappedToggle]:
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a bool")
    return _FeatureToggleFactory(
        enabled=enabled,
        predicate=predicate,
        name=name,
        listeners=listeners,
        event_manager=event_manager,
    )
