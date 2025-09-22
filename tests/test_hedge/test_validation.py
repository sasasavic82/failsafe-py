# tests/test_validation.py
import pytest
from failsafe.hedge import hedge

def test_timeout_must_be_positive_if_provided():
    with pytest.raises(ValueError):
        hedge(timeout=0)
    with pytest.raises(ValueError):
        hedge(timeout=-1)

def test_attempts_and_delay_validation():
    with pytest.raises(ValueError):
        hedge(attempts=0)
    with pytest.raises(ValueError):
        hedge(delay=-0.1)

def test_sync_function_is_rejected():
    with pytest.raises(TypeError):
        @hedge()
        def not_async():
            return 1
