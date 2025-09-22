
from failsafe.exceptions import FailsafeError

class CacheMiss(FailsafeError):
	"""
	Raised when a cache miss occurs and no fallback is provided.
	"""
