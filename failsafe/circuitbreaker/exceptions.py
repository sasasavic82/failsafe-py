from failsafe.exceptions import FailsafeError


class BreakerFailing(FailsafeError):
    """
    Occurs when you try to execute actions that was identified as failing by the circuit breaker
    """
