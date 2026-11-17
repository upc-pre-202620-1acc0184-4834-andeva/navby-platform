from typing import Any, cast
from uuid import uuid4

import pytest

from src.modules.iam.application.commands.delete_my_account import (
    DeleteMyAccountCommand,
    DeleteMyAccountHandler,
)


class _ExplodingUow:
    """Falla si el handler llega a abrir la transacción."""

    async def __aenter__(self) -> None:
        raise AssertionError("no debe abrir la UoW con una confirmación inválida")

    async def __aexit__(self, *_: object) -> None:
        return None


def _handler() -> DeleteMyAccountHandler:
    return DeleteMyAccountHandler(
        uow=cast(Any, _ExplodingUow()), user_repo=cast(Any, None), refresh_repo=cast(Any, None)
    )


@pytest.mark.parametrize("confirmation", ["eliminar", "BORRAR", "Delete", " DELETE", ""])
async def test_rejects_anything_but_eliminar_or_delete(confirmation: str) -> None:
    result = await _handler().handle(DeleteMyAccountCommand(uuid4(), confirmation))
    assert result.is_failure
    assert result.error.code == "VALIDATION_ERROR"


@pytest.mark.parametrize("confirmation", ["ELIMINAR", "DELETE"])
async def test_accepts_spanish_and_english_words(confirmation: str) -> None:
    # Pasa la validación y llega a la UoW (que aquí explota a propósito).
    with pytest.raises(AssertionError, match="no debe abrir la UoW"):
        await _handler().handle(DeleteMyAccountCommand(uuid4(), confirmation))
