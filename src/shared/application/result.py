from src.shared.application.application_error import ApplicationError


class Result[T]:
    __slots__ = ("_error", "_is_success", "_value")

    def __init__(self, is_success: bool, value: T | None, error: ApplicationError | None) -> None:
        self._is_success = is_success
        self._value = value
        self._error = error

    @staticmethod
    def success(value: T) -> "Result[T]":
        return Result(is_success=True, value=value, error=None)

    @staticmethod
    def failure(error: ApplicationError) -> "Result[T]":
        return Result(is_success=False, value=None, error=error)

    @property
    def is_success(self) -> bool:
        return self._is_success

    @property
    def is_failure(self) -> bool:
        return not self._is_success

    @property
    def value(self) -> T:
        if not self._is_success:
            raise ValueError("Cannot access value of a failed Result.")
        return self._value  # type: ignore[return-value]

    @property
    def error(self) -> ApplicationError:
        if self._is_success or self._error is None:
            raise ValueError("Cannot access error of a successful Result.")
        return self._error
