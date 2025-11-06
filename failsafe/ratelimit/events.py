from typing import TYPE_CHECKING, Union

from failsafe.events import ListenerFactoryT, ListenerRegistry

if TYPE_CHECKING:
    from failsafe.ratelimit.managers import TokenBucketLimiter


_RATELIMIT_LISTENERS: ListenerRegistry[TokenBucketLimiter, "RateLimitListener"] = ListenerRegistry()


class RateLimitListener:
    async def on_request(self, limiter: TokenBucketLimiter) -> None:
        ...

    async def on_success(self, limiter: TokenBucketLimiter) -> None:
        ...

    async def on_failure(self, limiter: TokenBucketLimiter) -> None:
        ...


def register_rate_limit_listener(listener: Union[RateLimitListener, ListenerFactoryT]) -> None:
    """
    Register a listener that will dispatch on all rate limit components in the system
    """
    global _RATELIMIT_LISTENERS

    _RATELIMIT_LISTENERS.register(listener)
