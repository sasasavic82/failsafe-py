from failsafe.circuitbreaker.api import consecutive_breaker
from failsafe.circuitbreaker.events import BreakerListener, register_breaker_listener

__all__ = ("consecutive_breaker", "BreakerListener", "register_breaker_listener")
