
from typing import Any, Callable, Coroutine, TypeVar, Union, Hashable

FuncT = TypeVar("FuncT", bound=Callable[..., Coroutine[Any, Any, Any]])
KeyFuncT = Callable[..., Hashable]
ExceptionsT = Union[type[Exception], tuple[type[Exception], ...]]
