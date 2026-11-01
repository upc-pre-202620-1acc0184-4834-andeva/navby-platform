from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ApplicationError:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
