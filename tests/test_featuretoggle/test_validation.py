# tests/test_featuretoggle/test_validation.py
import pytest
from failsafe.featuretoggle import featuretoggle

def test_enabled_must_be_bool():
    with pytest.raises(ValueError):
        featuretoggle(enabled=None)  # type: ignore[arg-type]

def test_sync_function_is_rejected():
    with pytest.raises(TypeError):
        @featuretoggle()
        def not_async():
            return 1
