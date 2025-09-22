# failsafe/hedge/manager.py
import asyncio
from typing import Any, Optional

from failsafe.hedge.events import HedgeListener
from failsafe.hedge.exceptions import HedgeAllFailed, HedgeTimeout
from failsafe.hedge.typing import FuncT


class HedgeManager:
    """
    Run N parallel attempts, optionally staggered by delay; return first success.
    Timeout can bound the overall wait.
    """

    def __init__(
        self,
        attempts: int = 2,
        delay: float = 0.0,
        timeout: Optional[float] = None,
        event_dispatcher: Optional[HedgeListener] = None,
        name: Optional[str] = None,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        if delay < 0:
            raise ValueError("delay must be >= 0")
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be > 0 when provided")

        self._attempts = attempts
        self._delay = delay
        self._timeout = timeout
        self._event_dispatcher = event_dispatcher
        self._name = name

        self._timeout_cm: Optional[asyncio.Timeout] = None  # for context-manager usage

    @property
    def name(self) -> Optional[str]:
        return self._name

    async def __call__(self, func: FuncT, *args: Any, **kwargs: Any) -> Any:
        tasks: list[asyncio.Task] = []

        async def _runner() -> Any:
            return await func(*args, **kwargs)

        # schedule attempts, staggering if configured
        for i in range(self._attempts):
            if i > 0 and self._delay > 0:
                await asyncio.sleep(self._delay)
            tasks.append(asyncio.create_task(_runner()))

        async def _await_first_success() -> Any:
            # iterate completions; first successful result wins
            for t in asyncio.as_completed(tasks):
                try:
                    result = await t
                except Exception as e:
                    if self._event_dispatcher:
                        await self._event_dispatcher.on_hedge_failure(self, e)
                    continue
                # success
                if self._event_dispatcher:
                    await self._event_dispatcher.on_hedge_success(self, result)
                # cancel the rest
                for p in tasks:
                    if p is not t and not p.done():
                        p.cancel()
                return result

            # all attempts finished but none succeeded
            if self._event_dispatcher:
                await self._event_dispatcher.on_hedge_all_failed(self)
            raise HedgeAllFailed()

        try:
            if self._timeout is None:
                return await _await_first_success()
            else:
                async with asyncio.timeout(self._timeout):
                    return await _await_first_success()
        except TimeoutError:
            for p in tasks:
                p.cancel()
            if self._event_dispatcher and hasattr(self._event_dispatcher, "on_hedge_timeout"):
                await self._event_dispatcher.on_hedge_timeout(self)  # type: ignore[attr-defined]
            raise HedgeTimeout()

    # ---- async context manager to apply timeout over a code block ----

    async def __aenter__(self):
        if self._timeout is None:
            return self
        self._timeout_cm = asyncio.timeout(self._timeout)
        await self._timeout_cm.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._timeout_cm is None:
            return False
        try:
            # propagate inner exceptions (including TimeoutError)
            return await self._timeout_cm.__aexit__(exc_type, exc_val, exc_tb)
        except TimeoutError:
            if self._event_dispatcher and hasattr(self._event_dispatcher, "on_hedge_timeout"):
                await self._event_dispatcher.on_hedge_timeout(self)  # type: ignore[attr-defined]
            raise HedgeTimeout()
        finally:
            self._timeout_cm = None
