from typing import Any

from pydantic import BaseModel, ConfigDict


class ProblemDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    invalid_params: list[dict[str, Any]] | None = None
