
import pytest
from failsafe.failfast import failfast, FailFastOpen, FailFastListener
from failsafe.failfast.manager import FailFastManager
from failsafe.events import EventManager


class Listener(FailFastListener):
    def __init__(self):
        self.opened = False
    async def on_failfast_open(self, failfast: FailFastManager):
        self.opened = True



@pytest.mark.asyncio
async def test__failfast__decorator():
    event_manager = EventManager()
    listener = Listener()

    @failfast(failure_threshold=1, listeners=(listener,), event_manager=event_manager)
    async def f():
        raise RuntimeError()
    with pytest.raises(FailFastOpen):
        await f()
    assert listener.opened




@pytest.mark.asyncio
async def test__failfast__context():
    event_manager = EventManager()
    listener = Listener()
    ff = failfast(failure_threshold=1, listeners=(listener,), event_manager=event_manager)
    with pytest.raises(FailFastOpen):
        async with ff:
            raise RuntimeError()
    assert listener.opened
