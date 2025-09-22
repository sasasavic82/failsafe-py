import pytest
from failsafe.cache import cache


def test__cache__validate__maxsize_positive():
    with pytest.raises(ValueError):
        @cache(maxsize=0)
        def foo():
            pass
    with pytest.raises(ValueError):
        @cache(maxsize=-1)
        def bar():
            pass
