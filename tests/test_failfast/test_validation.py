import pytest
from failsafe.failfast import failfast

def test__failfast__validate__threshold_positive():
    with pytest.raises(ValueError):
        @failfast(failure_threshold=0)
        def foo():
            pass
    with pytest.raises(ValueError):
        @failfast(failure_threshold=-1)
        def bar():
            pass
