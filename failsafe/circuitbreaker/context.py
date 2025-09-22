import dataclasses
from typing import TYPE_CHECKING, Optional

from failsafe.circuitbreaker.typing import DelayT
from failsafe.typing import ExceptionsT

if TYPE_CHECKING:
    from failsafe.circuitbreaker import BreakerListener


@dataclasses.dataclass
class BreakerContext:
    breaker_name: Optional[str]
    exceptions: ExceptionsT
    failure_threshold: int
    recovery_time_secs: DelayT
    recovery_threshold: int
    event_dispatcher: "BreakerListener"
