
from failsafe.exceptions import FailsafeError



class FeatureDisabled(FailsafeError):
    """
    Raised when a feature is disabled and operation is not allowed.
    """
