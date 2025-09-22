
from failsafe.exceptions import FailsafeError

class FailFastOpen(FailsafeError):
	"""
	Raised when fail fast is open and operation is rejected immediately.
	"""
