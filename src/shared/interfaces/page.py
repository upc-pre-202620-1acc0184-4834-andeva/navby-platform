from pydantic import BaseModel, ConfigDict


class Page[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[T]
    page: int
    page_size: int
    total: int
