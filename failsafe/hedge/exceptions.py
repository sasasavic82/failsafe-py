
from failsafe.exceptions import FailsafeError

class HedgeTimeout(FailsafeError):
    """
    Raised when a hedged attempt times out.
    """

class HedgeAllFailed(FailsafeError):
    """
    Raised when all hedged attempts fail.
    """
