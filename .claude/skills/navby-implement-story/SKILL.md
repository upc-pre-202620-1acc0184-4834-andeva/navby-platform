---
name: navby-implement-story
description: Use when implementing a Navby technical story (TS-xx) from docs/backlog/technical-stories.md — reads the story and its bounded context, turns every Gherkin scenario into failing tests, implements layer by layer and verifies the definition of done. Triggers on "implementa TS-", "historia técnica", "implement TS-".
argument-hint: TS-xx
---

# Implementar una historia técnica de Navby

Argumento: el ID de la historia (por ejemplo `TS-14`).

## 1. Reunir el contexto (no escribas código todavía)

1. Lee la historia `$ARGUMENTS` en `docs/backlog/technical-stories.md`, incluida su lista de componentes y sus escenarios.
2. Lee las historias de usuario que cubre (tabla «Mapa con las historias de usuario»).
3. Lee el documento del bounded context en `docs/backend-documentation/extended-bounded-contexts-description/`.
4. Si es un endpoint, lee su contrato en `docs/backend-documentation/navby-endpoints.md` y los «Errores comunes».
5. Lee las reglas `RN-xx` / `RL-xx` citadas en `docs/navby-documentation.md`.
6. Revisa qué existe ya en `src/` para no duplicar piezas, sobre todo `src/shared/`.

Si falta información o hay contradicciones entre documentos, **detente y pregunta**, citando archivo y línea. No inventes comportamiento.

## 2. Preparar el trabajo

- Usa `superpowers:using-git-worktrees` con la rama `feature/TS-xx-<descripcion-corta>`.
- Usa `superpowers:writing-plans`. El plan debe tener:
  - una tarea por capa (dominio, aplicación, infraestructura e interfaces);
  - la lista de pruebas, una o más por escenario Gherkin, con su nombre de archivo en `tests/`.

## 3. Implementar con TDD

Usa `superpowers:test-driven-development` y `superpowers:executing-plans`.

- **Dominio primero** (`tests/unit/<contexto>/`): value objects, agregados y servicios. Sin I/O.
- **Aplicación**: handlers con repositorios en memoria y puertos simulados. Verifica cada `Result.failure` con su código del catálogo.
- **Infraestructura**: repositorios SQLAlchemy y Redis, probados en `tests/integration/` contra los contenedores de `docker-compose.dev.yml`.
- **Interfaces**: router y schemas Pydantic. Una prueba de endpoint con `httpx.AsyncClient` por escenario.
- Nunca llames a FlightAPI, Mercado Pago, Google ni Resend reales: usa mocks, fixtures o `respx`.

## 4. Verificar

Usa `superpowers:verification-before-completion` y muestra la salida real de:

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy src
```

Comprueba la definición de terminado de `AGENTS.md`, sección 7. Si un comportamiento quedó distinto a lo documentado, aplica la skill `navby-docs-sync`.

## 5. Cerrar

Usa `superpowers:requesting-code-review` y luego `superpowers:finishing-a-development-branch`. El PR se titula `TS-xx: <título de la historia>` y su descripción lista los escenarios cubiertos con el archivo de prueba de cada uno.
