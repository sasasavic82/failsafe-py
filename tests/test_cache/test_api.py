import pytest
from failsafe.cache import cache


@pytest.mark.asyncio
async def test__cache__basic_usage():
    @cache(maxsize=2)
    async def add(a, b):
        return a + b

    assert await add(1, 2) == 3
    assert await add(1, 2) == 3  # Cached
    assert await add(2, 3) == 5
    assert await add(3, 4) == 7
    # The (1,2) result may be evicted if LRU


def test__cache__invalid_maxsize():
    with pytest.raises(ValueError):
        @cache(maxsize=0)
        def foo():
            pass
