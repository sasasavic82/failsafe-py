from failsafe.exceptions import FailsafeError


class BulkheadFull(FailsafeError):
    """
    Occurs when execution requests has exceeded allowed amount
    """
