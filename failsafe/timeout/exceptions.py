from failsafe.exceptions import FailsafeError


class MaxDurationExceeded(FailsafeError):
    """
    Occurs if some task took more time than it was given
    """
