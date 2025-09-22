# failsafe/featuretoggle/manager.py
import inspect
from typing import Any, Optional

from failsafe.featuretoggle.events import FeatureToggleListener
from failsafe.featuretoggle.exceptions import FeatureDisabled
from failsafe.featuretoggle.typing import FuncT, TogglePredicateT


class FeatureToggleManager:
    """Async-only feature toggle manager."""

    def __init__(
        self,
        enabled: bool = True,
        predicate: Optional[TogglePredicateT] = None,
        event_dispatcher: Optional[FeatureToggleListener] = None,
        name: Optional[str] = None,
    ) -> None:
        self._enabled = enabled
        self._predicate = predicate
        self._event_dispatcher = event_dispatcher
        self._name = name

    @property
    def name(self) -> Optional[str]:
        return self._name

    async def enable(self) -> None:
        self._enabled = True
        if self._event_dispatcher:
            await self._event_dispatcher.on_feature_enabled(self)

    async def disable(self) -> None:
        self._enabled = False
        if self._event_dispatcher:
            await self._event_dispatcher.on_feature_disabled(self)

    async def _predicate_allows(self, *args: Any, **kwargs: Any) -> bool:
        if self._predicate is None:
            return True
        rv = self._predicate(*args, **kwargs)
        if inspect.isawaitable(rv):
            rv = await rv
        return bool(rv)

    async def _is_enabled(self, *args: Any, **kwargs: Any) -> bool:
        if not self._enabled:
            return False
        return await self._predicate_allows(*args, **kwargs)

    async def __call__(self, func: FuncT, *args: Any, **kwargs: Any) -> Any:
        if not await self._is_enabled(*args, **kwargs):
            if self._event_dispatcher:
                await self._event_dispatcher.on_feature_disabled(self)
            raise FeatureDisabled()
        if self._event_dispatcher:
            await self._event_dispatcher.on_feature_enabled(self)
        return await func(*args, **kwargs)

    # async context manager: guard on entry
    async def __aenter__(self):
        if not await self._is_enabled():
            if self._event_dispatcher:
                await self._event_dispatcher.on_feature_disabled(self)
            raise FeatureDisabled()
        if self._event_dispatcher:
            await self._event_dispatcher.on_feature_enabled(self)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False
