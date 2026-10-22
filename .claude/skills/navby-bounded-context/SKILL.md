---
name: navby-bounded-context
description: Use when creating the folder skeleton of a Navby bounded context (iam, routing, quotes, billing, itineraries) or adding a new layer component — creates the canonical structure under src/modules/<context>/ and the matching tests folders. Triggers on "crear contexto", "scaffold", "nuevo bounded context", "estructura del módulo".
argument-hint: <context>
---

# Estructura de un bounded context de Navby

Argumento: el nombre del contexto en minúsculas (`iam`, `routing`, `quotes`, `billing` o `itineraries`). No crees contextos que no estén en `docs/backend-documentation/navby-platform-documentation.md`, sección 3.

## Estructura a crear

```text
src/modules/<context>/
├── __init__.py
├── domain/
│   ├── model/
│   │   ├── aggregates/
│   │   ├── entities/
│   │   ├── value_objects/
│   │   └── events/
│   ├── services/
│   ├── repositories/
│   └── exceptions.py
├── application/
│   ├── commands/
│   ├── queries/
│   ├── event_handlers/
│   └── acl/ports/
├── infrastructure/
│   ├── persistence/
│   ├── adapters/
│   └── cache/
└── interfaces/
    ├── rest/
    │   ├── router.py
    │   ├── schemas.py
    │   └── assemblers.py
    └── acl/facade/

tests/unit/<context>/
tests/integration/<context>/
```

Cada carpeta lleva un `__init__.py` vacío. No crees archivos de clases vacíos «por si acaso»: las clases se agregan cuando una historia técnica las necesita.

## Reglas de cada capa

| Capa | Puede importar | No puede importar |
| :--- | :--- | :--- |
| `domain/` | `src/shared/domain`, biblioteca estándar | FastAPI, Pydantic, SQLAlchemy, Redis, `httpx`, otras capas |
| `application/` | `domain/`, `src/shared/application` | `infrastructure/`, `interfaces/` de cualquier contexto |
| `infrastructure/` | `domain/`, `application/` (para implementar puertos), librerías técnicas | `interfaces/` |
| `interfaces/` | `application/`, `src/shared/interfaces`, FastAPI, Pydantic | `infrastructure/` directamente (se inyecta por dependencias) |

Otro contexto solo se usa desde `application/acl/ports/`, con un adaptador que llama a su `interfaces/acl/facade/`.

## Después de crear la estructura

1. Registra el router en `src/main.py` con el prefijo `/api/v1`.
2. Si el contexto tiene tablas, crea su esquema PostgreSQL en una migración Alembic, copiando el DDL de `docs/backend-documentation/navby-database-schema.md`.
3. Verifica con `uv run ruff check .` y `uv run mypy src`.
