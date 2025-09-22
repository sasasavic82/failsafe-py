
from typing import Any, Callable, Coroutine, TypeVar, Union

FuncT = TypeVar("FuncT", bound=Callable[..., Coroutine[Any, Any, Any]])
ExceptionsT = Union[type[Exception], tuple[type[Exception], ...]]
HedgeResultT = Any
HedgePredicateT = Callable[[Any], bool]
