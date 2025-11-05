"""
Enhanced RetryManager with dynamic configuration support
"""

import asyncio
from typing import Any, Optional

from failsafe.ratelimit.buckets import TokenBucket
from failsafe.retry.backoffs import create_backoff
from failsafe.retry.counters import create_counter
from failsafe.retry.events import RetryListener
from failsafe.retry.exceptions import AttemptsExceeded
from failsafe.retry.typing import AttemptsT, BackoffsT
from failsafe.typing import ExceptionsT, FuncT


class RetryManager:
    """
    Enhanced RetryManager with support for dynamic configuration updates
    """

    def __init__(
        self,
        name: str,
        exceptions: ExceptionsT,
        attempts: AttemptsT,
        backoff: BackoffsT,
        event_dispatcher: RetryListener,
        limiter: Optional[TokenBucket] = None,
    ) -> None:
        self._name = name
        self._exceptions = exceptions
        self._attempts = attempts
        self._backoff = create_backoff(backoff)
        self._event_dispatcher = event_dispatcher
        self._limiter = limiter
        
        # Control plane support
        self._enabled = True
        self._original_attempts = attempts
        self._original_backoff_config = backoff

    @property
    def name(self) -> str:
        return self._name
    
    @property
    def enabled(self) -> bool:
        """Check if this retry pattern is enabled"""
        return self._enabled
    
    def enable(self):
        """Enable this retry pattern"""
        self._enabled = True
    
    def disable(self):
        """Disable this retry pattern"""
        self._enabled = False
    
    def update_attempts(self, attempts: AttemptsT):
        """Dynamically update the number of attempts"""
        self._attempts = attempts
    
    def update_backoff(self, backoff: BackoffsT):
        """Dynamically update the backoff strategy"""
        self._backoff = create_backoff(backoff)
        self._original_backoff_config = backoff
    
    def get_config(self) -> dict:
        """Get current configuration"""
        return {
            "name": self._name,
            "enabled": self._enabled,
            "attempts": self._attempts,
            "backoff": self._original_backoff_config,
            "exceptions": str(self._exceptions),
        }

    async def __call__(self, func: FuncT) -> Any:
        # If disabled, just execute once
        if not self._enabled:
            return await func()
        
        counter = create_counter(self._attempts)
        backoff_generator = iter(self._backoff)

        try:
            while bool(counter):
                try:
                    if self._limiter is not None:
                        await self._limiter.take()

                    result = await func()

                    await self._event_dispatcher.on_success(self, counter)

                    return result
                except self._exceptions as e:
                    counter += 1
                    backoff = next(backoff_generator)

                    await self._event_dispatcher.on_retry(self, e, counter, backoff)
                    await asyncio.sleep(backoff)

        except AttemptsExceeded:
            await self._event_dispatcher.on_attempts_exceeded(self)
            raise