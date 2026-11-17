import json

import pytest

from src.main import app

# Textos que contradicen docs/navby-documentation.md o exponen credenciales.
FORBIDDEN = [
    "demo.azure",
    "BUDGET",
    "`DIRECT`",
    "mensual",
    "monthly",
    "2 créditos",
    "20 itinerarios",
    "pack_20",
    "pack_120",
    "SEARCH_SESSION_EXPIRED",
    "15 min (",
    "Público y gratuito",
    "Catálogo público",
]


@pytest.mark.parametrize("text", FORBIDDEN)
def test_openapi_does_not_contradict_the_product_spec(text: str) -> None:
    assert text not in json.dumps(app.openapi(), ensure_ascii=False)
