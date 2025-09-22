# tests/test_api.py
import asyncio
import pytest

from failsafe.hedge import hedge, HedgeListener
from failsafe.hedge.exceptions import HedgeTimeout, HedgeAllFailed
from failsafe.hedge.manager import HedgeManager


class FlagListener(HedgeListener):
    def __init__(self) -> None:
        self.success = 0
        self.failure = 0
        self.timeout = 0
        self.all_failed = 0

    async def on_hedge_success(self, hedge: HedgeManager, result):
        self.success += 1

    async def on_hedge_failure(self, hedge: HedgeManager, exception: Exception):
        self.failure += 1

    async def on_hedge_all_failed(self, hedge: HedgeManager):
        self.all_failed += 1

    async def on_hedge_timeout(self, hedge: HedgeManager):
        self.timeout += 1


@pytest.mark.asyncio
async def test_decorator_times_out_and_notifies():
    listener = FlagListener()

    @hedge(timeout=0.01, listeners=(listener,))
    async def slow():
        await asyncio.sleep(0.1)
        return 42

    with pytest.raises(HedgeTimeout):
        await slow()
    assert listener.timeout == 1
    assert listener.success == 0


@pytest.mark.asyncio
async def test_context_times_out_and_notifies():
    listener = FlagListener()
    h = hedge(timeout=0.01, listeners=(listener,))

    with pytest.raises(HedgeTimeout):
        async with h:
            await asyncio.sleep(0.1)
    assert listener.timeout == 1
    assert listener.success == 0


@pytest.mark.asyncio
async def test_first_success_wins_even_if_one_attempt_fails():
    listener = FlagListener()

    failed_once = {"v": False}

    @hedge(attempts=3, delay=0.0, listeners=(listener,))
    async def maybe():
        # cause exactly one failure across concurrent attempts
        if not failed_once["v"]:
            failed_once["v"] = True
            raise RuntimeError("first attempt fails")
        await asyncio.sleep(0.01)
        return "ok"

    assert await maybe() == "ok"
    # at least one failure reported, exactly one success event
    assert listener.success == 1
    assert listener.failure >= 1
    assert listener.all_failed == 0
    assert listener.timeout == 0


@pytest.mark.asyncio
async def test_all_failed_raises_and_notifies():
    listener = FlagListener()

    @hedge(attempts=2, listeners=(listener,))
    async def always_fails():
        raise RuntimeError("nope")

    with pytest.raises(HedgeAllFailed):
        await always_fails()
    assert listener.all_failed == 1
    assert listener.success == 0
