# tests/test_failfast/test_behavior.py
import pytest

from failsafe.failfast import failfast, FailFastOpen, FailFastListener
from failsafe.failfast.manager import FailFastManager


class FlagListener(FailFastListener):
    def __init__(self):
        self.opened = False
        self.calls = 0

    async def on_failfast_open(self, failfast: FailFastManager) -> None:
        self.calls += 1
        self.opened = True


@pytest.mark.asyncio
async def test_decorator_opens_after_threshold_and_notifies_listener():
    listener = FlagListener()
    call_counter = {"n": 0}

    @failfast(failure_threshold=1, listeners=(listener,))
    async def fn():
        call_counter["n"] += 1
        raise RuntimeError("boom")

    # First call executes the function, hits threshold, opens, and notifies
    with pytest.raises(FailFastOpen):
        await fn()
    assert listener.opened is True
    assert listener.calls == 1
    assert call_counter["n"] == 1

    # Subsequent calls are rejected immediately; function body not run again
    with pytest.raises(FailFastOpen):
        await fn()
    assert call_counter["n"] == 1  # unchanged


@pytest.mark.asyncio
async def test_context_manager_opens_and_notifies_then_rejects_on_entry():
    listener = FlagListener()
    ff = failfast(failure_threshold=1, listeners=(listener,))

    # First context raises inside; should open and notify
    with pytest.raises(FailFastOpen):
        async with ff:
            raise RuntimeError("boom")
    assert listener.opened is True
    assert listener.calls == 1

    # Second context is rejected at __aenter__ since already open
    with pytest.raises(FailFastOpen):
        async with ff:
            pass
    assert listener.calls == 2  # notified again on entry


@pytest.mark.asyncio
async def test_success_resets_failure_counter_between_calls():
    failures = {"n": 0}

    # threshold=2 -> need two consecutive failures to open
    @failfast(failure_threshold=2)
    async def sometimes_fails(step: int):
        if step in (1, 3):
            failures["n"] += 1
            raise RuntimeError("fail")
        return "ok"

    # 1st call fails (counter = 1)
    with pytest.raises(RuntimeError):
        await sometimes_fails(1)

    # Success resets failure counter
    assert await sometimes_fails(2) == "ok"

    # Another single failure should NOT open; counter should be 1 again
    with pytest.raises(RuntimeError):
        await sometimes_fails(3)

    # A final success keeps it closed and resets to 0 again
    assert await sometimes_fails(4) == "ok"


@pytest.mark.asyncio
async def test_predicate_short_circuits_without_calling_function():
    called = {"n": 0}

    def predicate(*_args, **_kwargs) -> bool:
        return True  # force open

    @failfast(predicate=predicate)
    async def fn():
        called["n"] += 1
        return 42

    with pytest.raises(FailFastOpen):
        await fn()

    assert called["n"] == 0  # body not executed


def test_sync_function_rejected():
    # When the factory is applied to a sync function, __call__ raises TypeError
    with pytest.raises(TypeError):
        @failfast()
        def not_async():
            return 1
