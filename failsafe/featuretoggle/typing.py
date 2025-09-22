# failsafe/featuretoggle/typing.py
from typing import Any, Callable, Coroutine, TypeVar, Union, Awaitable

FuncT = TypeVar("FuncT", bound=Callable[..., Coroutine[Any, Any, Any]])
TogglePredicateT = Callable[..., Union[bool, Awaitable[bool]]]
ExceptionsT = Union[type[Exception], tuple[type[Exception], ...]]
