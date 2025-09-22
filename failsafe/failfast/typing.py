
from typing import Any, Callable, Coroutine, TypeVar, Union

FuncT = TypeVar("FuncT", bound=Callable[..., Coroutine[Any, Any, Any]])
PredicateT = Callable[..., bool]
ExceptionsT = Union[type[Exception], tuple[type[Exception], ...]]
