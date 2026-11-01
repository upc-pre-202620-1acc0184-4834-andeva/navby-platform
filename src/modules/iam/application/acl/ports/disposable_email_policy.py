from typing import Protocol


class DisposableEmailPolicy(Protocol):
    def is_disposable(self, domain: str) -> bool: ...
