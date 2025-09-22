# tests/test_featuretoggle/test_wrapped_context.py
import pytest
from failsafe.featuretoggle import featuretoggle, FeatureDisabled

@pytest.mark.asyncio
async def test_wrapped_function_exposes_async_context_manager():
    @featuretoggle(enabled=False)
    async def f():
        return 1

    with pytest.raises(FeatureDisabled):
        async with f:
            pass
