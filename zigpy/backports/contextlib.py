from types import TracebackType
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class nullcontext(Generic[T]):
    """Context manager that does no additional processing.

    Used as a stand-in for a normal context manager, when a particular
    block of code is only sometimes used with a normal context manager:

    cm = optional_cm if condition else nullcontext()
    with cm:
        # Perform operation, using optional_cm if condition is True
    """

    def __init__(self, enter_result: T | None = None) -> None:
        self.enter_result = enter_result

    def __enter__(self) -> T:
        return self.enter_result

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        pass

    async def __aenter__(self) -> T:
        return self.enter_result

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        pass
