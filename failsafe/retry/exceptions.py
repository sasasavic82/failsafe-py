from failsafe.exceptions import FailsafeError


class AttemptsExceeded(FailsafeError):
    """
    Occurs when all attempts were exceeded with no success
    """
