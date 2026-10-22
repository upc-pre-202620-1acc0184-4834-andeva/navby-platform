# AGENTS.md — Navby Platform (backend)

Instrucciones para cualquier persona o agente de IA que trabaje en este repositorio.

## 1. Qué es este proyecto

Backend de **Navby**: recomienda los 3 mejores vuelos entre dos ciudades combinando precio, duración y escalas en un único puntaje. Es un monolito modular en Python que mantiene en memoria el grafo de OpenFlights (BFS y A\*), cotiza ofertas reales en FlightAPI y las ordena con un motor multicriterio sobre la frontera de Pareto.

**La documentación en `docs/` es el contrato.** Empieza por [docs/README.md](docs/README.md). La fuente de verdad del producto es [docs/navby-documentation.md](docs/navby-documentation.md): cualquier número, regla (`RN-xx`, `RL-xx`) o algoritmo debe coincidir con ese documento.

## 2. Stack

Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic, PostgreSQL 16, Redis 7, `httpx`, `bcrypt`, `PyJWT`, `google-auth`, SDK `mercadopago`, SDK `resend`. Herramientas: **`uv`** (obligatorio), Ruff, Mypy, pytest, `pytest-asyncio` y `respx`. Despliegue con Docker Compose y Caddy 2 en una VM de Azure.

## 3. Estructura del repositorio

```text
backend-navby/
├── src/
│   ├── main.py                   # App FastAPI, routers y lifespan (grafo, pools, outbox, tareas periódicas)
│   ├── shared/                   # Shared Kernel (ver bounded-context-shared.md)
│   └── modules/
│       ├── iam/  routing/  quotes/  billing/  itineraries/
│       │   ├── domain/           # Python puro: agregados, VOs, servicios, eventos, repositorios (Protocol)
│       │   ├── application/      # commands/, queries/, event_handlers/, acl/ports/
│       │   ├── infrastructure/   # persistence/, adapters/ (reales y mocks), cache/
│       │   └── interfaces/       # rest/ (router, schemas, assemblers) y acl/facade/
├── tests/
│   ├── unit/<contexto>/          # Dominio y handlers, sin I/O
│   ├── integration/<contexto>/   # Endpoints y repositorios contra PostgreSQL y Redis reales
│   └── contract/                 # Adaptadores contra fixtures de FlightAPI y Mercado Pago
├── fixtures/flightapi/           # Respuestas JSON grabadas (también las usa el mock)
├── migrations/                   # Alembic
├── data/                         # Datasets del grafo (no editar airports ni routes a mano)
├── benchmarks/run.py             # Benchmark de BFS, A* y motor multicriterio
├── scripts/smoke_test.py         # Pruebas de humo post-despliegue
├── docs/                         # Contrato del sistema
├── Dockerfile  docker-compose.yml  docker-compose.dev.yml  Caddyfile
├── pyproject.toml  uv.lock  .env.example
└── .github/workflows/            # ci.yml (pruebas) y deploy.yml (producción)
```

## 4. Comandos

```bash
uv sync                                            # instalar dependencias
docker compose -f docker-compose.dev.yml up -d     # PostgreSQL y Redis locales
cp .env.example .env                               # luego completar lo necesario
uv run alembic upgrade head                        # migraciones
uv run uvicorn src.main:app --reload               # servidor en http://localhost:8000 (docs en /docs)
uv run pytest                                      # todas las pruebas
uv run pytest tests/unit                           # solo unitarias (rápidas)
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run python -m benchmarks.run --pairs 1000 --seed 42
```

Nunca uses `pip`, `poetry` ni `python -m venv`: siempre `uv`. Si hace falta Node.js para algo, usa `pnpm` y `pnpm dlx`, nunca `npm` ni `npx`.

## 5. Cómo se trabaja

1. **Una historia técnica a la vez**, siguiendo el orden de sprints de [technical-stories.md](docs/backlog/technical-stories.md). La rama se llama `feature/TS-14-quotes-search`.
2. **Primero las pruebas.** Cada escenario Gherkin de la historia se convierte en al menos una prueba, que debe fallar antes de escribir el código.
3. **Implementa por capas**, de adentro hacia afuera: dominio → aplicación → infraestructura → interfaces.
4. **Verifica la definición de terminado** (sección 7) antes de abrir el PR.
5. **Si la documentación no alcanza o es contradictoria, no improvises.** Detente, explica la duda y propón el cambio al documento. Si se aprueba, se actualiza `docs/` en el mismo PR.

Commits en formato Conventional Commits, en inglés: `feat(quotes): add pareto filter`.

## 6. Reglas que no se rompen

- **Solo tres algoritmos:** BFS, A\* y el motor multicriterio (Pareto + puntaje ponderado). No agregues Dijkstra, DFS, backtracking ni otros.
- **El podio sale de un único puntaje.** Nunca crees categorías como «el más barato» o «el más rápido».
- **Dominio puro:** `domain/` no importa FastAPI, Pydantic, SQLAlchemy, Redis ni `httpx`.
- **Errores de negocio con `Result`**, nunca con excepciones. Los códigos de error son solo los del [catálogo](docs/backend-documentation/navby-backend-tactical-specification.md#catálogo-de-códigos-de-error); si necesitas uno nuevo, se agrega primero al catálogo.
- **Sin claves foráneas entre contextos.** Un contexto solo usa a otro mediante su fachada en `interfaces/acl/facade/` o eventos del outbox.
- **Los créditos se mueven solo en PostgreSQL**, con bloqueo de fila. Redis nunca guarda saldos.
- **Un solo worker de Uvicorn** (`--workers 1`): el grafo, el semáforo de FlightAPI y las tareas periódicas viven en un proceso.
- **Secretos:** nunca en el código, en los commits, en los logs ni en los mensajes de error. Solo `.env` (ignorado por git) y `.env.example` con valores de ejemplo.
- **FlightAPI cuesta dinero:** las pruebas nunca llaman a la API real; usan `MockFlightOffersProvider`, fixtures o `respx`.

## 7. Definición de terminado

1. Todos los escenarios de la historia tienen prueba y pasan.
2. `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` y `uv run mypy src` pasan sin errores.
3. El endpoint aparece en `/docs` con ejemplos y respuestas de error RFC 7807.
4. Si cambió algún comportamiento, `docs/` está actualizado en el mismo PR.
5. No hay secretos, `print` de depuración ni código comentado.

## 8. Entornos

`APP_ENV=local` funciona sin ningún secreto de producción: FlightAPI usa mocks, el correo se escribe en el log y Mercado Pago usa credenciales sandbox propias. Los secretos de producción los administra solo el responsable del proyecto en la VM y en GitHub. Detalle en [navby-environments-and-deployment.md](docs/backend-documentation/navby-environments-and-deployment.md).
