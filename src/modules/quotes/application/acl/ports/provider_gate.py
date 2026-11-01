from contextlib import AbstractAsyncContextManager
from typing import Protocol


class ProviderGate(Protocol):
    def slot(self) -> AbstractAsyncContextManager[None]: ...
