from typing import Any, Optional
from failsafe.failfast.events import FailFastListener
from failsafe.failfast.exceptions import FailFastOpen
from failsafe.failfast.typing import FuncT, PredicateT


class FailFastManager:
    """
    Async-only fail-fast manager.
    Tracks consecutive failures; opens once threshold reached.
    """

    def __init__(
        self,
        failure_threshold: Optional[int] = None,
        predicate: Optional[PredicateT] = None,
        event_dispatcher: Optional[FailFastListener] = None,
        name: Optional[str] = None,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._predicate = predicate
        self._event_dispatcher = event_dispatcher
        self._name = name
        self._open = False
        self._failure_count = 0

    @property
    def name(self) -> Optional[str]:
        return self._name

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False
        self._failure_count = 0

    async def __call__(self, func: FuncT, *args: Any, **kwargs: Any) -> Any:
        if self._open or (self._predicate and self._predicate(*args, **kwargs)):
            if self._event_dispatcher:
                await self._event_dispatcher.on_failfast_open(self)
            raise FailFastOpen()

        try:
            result = await func(*args, **kwargs)
        except Exception:
            self._failure_count += 1
            if (
                self._failure_threshold is not None
                and self._failure_count >= self._failure_threshold
            ):
                self.open()
                if self._event_dispatcher:
                    await self._event_dispatcher.on_failfast_open(self)
                raise FailFastOpen()
            raise
        else:
            if self._failure_count:
                self._failure_count = 0
            return result

    async def __aenter__(self):
        if self._open or (self._predicate and self._predicate()):
            if self._event_dispatcher:
                await self._event_dispatcher.on_failfast_open(self)
            raise FailFastOpen()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._failure_count += 1
            if (
                self._failure_threshold is not None
                and self._failure_count >= self._failure_threshold
            ):
                self.open()
                if self._event_dispatcher:
                    await self._event_dispatcher.on_failfast_open(self)
                raise FailFastOpen()
        else:
            if self._failure_count:
                self._failure_count = 0
        return False
