from failsafe.exceptions import FailsafeError


class RateLimitExceeded(FailsafeError):
    """
    Occurs when requester have exceeded the rate limit
    """


class EmptyBucket(FailsafeError):
    """
    Occurs when requester have exceeded the rate limit
    """
