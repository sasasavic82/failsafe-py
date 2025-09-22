# tests/test_featuretoggle/test_api.py
import pytest
from failsafe.featuretoggle import featuretoggle, FeatureDisabled, FeatureToggleListener
from failsafe.featuretoggle.manager import FeatureToggleManager

class FlagListener(FeatureToggleListener):
    def __init__(self) -> None:
        self.enabled_calls = 0
        self.disabled_calls = 0

    async def on_feature_enabled(self, toggle: FeatureToggleManager) -> None:
        self.enabled_calls += 1

    async def on_feature_disabled(self, toggle: FeatureToggleManager) -> None:
        self.disabled_calls += 1


@pytest.mark.asyncio
async def test_decorator_disabled_raises_and_notifies():
    listener = FlagListener()

    @featuretoggle(enabled=False, listeners=(listener,))
    async def f():
        return 42

    with pytest.raises(FeatureDisabled):
        await f()
    assert listener.disabled_calls == 1
    assert listener.enabled_calls == 0


@pytest.mark.asyncio
async def test_context_manager_disabled_on_entry():
    listener = FlagListener()
    ft = featuretoggle(enabled=False, listeners=(listener,))

    with pytest.raises(FeatureDisabled):
        async with ft:
            pass
    assert listener.disabled_calls == 1
    assert listener.enabled_calls == 0


@pytest.mark.asyncio
async def test_enabled_executes_and_emits_enabled():
    listener = FlagListener()

    @featuretoggle(enabled=True, listeners=(listener,))
    async def f():
        return 99

    assert await f() == 99
    assert listener.enabled_calls == 1
    assert listener.disabled_calls == 0


@pytest.mark.asyncio
async def test_async_predicate_blocks_without_running_body():
    called = {"n": 0}

    async def predicate() -> bool:
        return False

    @featuretoggle(predicate=predicate)
    async def f():
        called["n"] += 1
        return 1

    with pytest.raises(FeatureDisabled):
        await f()
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_runtime_toggle_via_manager_disable_enable():
    listener = FlagListener()

    @featuretoggle(enabled=True, listeners=(listener,))
    async def f():
        return "ok"

    # initial OK
    assert await f() == "ok"
    assert listener.enabled_calls == 1

    # disable -> raises
    await f._manager.disable()
    with pytest.raises(FeatureDisabled):
        await f()
    assert listener.disabled_calls == 2  # one from disable(), one from call short-circuit

    # enable -> OK again
    await f._manager.enable()
    assert await f() == "ok"
    assert listener.enabled_calls >= 2  # one from enable(), one from call
