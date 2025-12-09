import importlib
from typing import TYPE_CHECKING

__version__ = "0.1.0"

# 1. DEFINE EXPORTS: Map the public name to (module_path, internal_name)
_IMPORT_MAP = {
    "FailsafeController": ("failsafe.controller.failsafe_controller", "FailsafeController"),
    "Telemetry": ("failsafe.controller.failsafe_controller", "Telemetry"),
    "Protection": ("failsafe.controller.failsafe_controller", "Protection"),
    "Strategy": ("failsafe.ratelimit.retry_after", "RetryAfterStrategy"),
}

# 2. TYPE HINTS: This ensures IDEs (VS Code/PyCharm) still give you autocomplete
if TYPE_CHECKING:
    from failsafe.controller.failsafe_controller import (
        FailsafeController,
        Telemetry,
        Protection,
    )
    from failsafe.ratelimit.retry_after import RetryAfterStrategy as Strategy

# 3. LAZY LOADER: This only runs when someone actually tries to use the import
def __getattr__(name: str):
    if name in _IMPORT_MAP:
        module_path, attr_name = _IMPORT_MAP[name]
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# 4. EXPORT LIST: Defines what happens on 'from failsafe import *'
__all__ = list(_IMPORT_MAP.keys())

# # failsafe/__init__.py
# """
# Failsafe - Fault tolerance and resiliency patterns for Python microservices.

# Usage:
#     from fastapi import FastAPI
#     from failsafe import FailsafeController, Telemetry, Protection

#     app = FastAPI()

#     FailsafeController(app) \\
#         .with_telemetry(Telemetry.OTEL) \\
#         .with_protection(Protection.INGRESS) \\
#         .with_controlplane()
# """

# from failsafe.controller.failsafe_controller import (
#     FailsafeController,
#     Telemetry,
#     Protection,
# )

# # Re-export Strategy enum for convenience
# from failsafe.ratelimit.retry_after import RetryAfterStrategy as Strategy


# __all__ = [
#     # Main controller
#     "FailsafeController",
    
#     # Enums
#     "Telemetry",
#     "Protection",
#     "Strategy",
# ]

# __version__ = "0.1.0"