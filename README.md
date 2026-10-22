# Navby Platform

Backend de **Navby**: recomienda los 3 mejores vuelos entre dos ciudades combinando precio, duración y escalas en un único puntaje.

- **Producción**: `https://navby.andeva.tech/api/v1`, a través del proxy de Vercel hacia la VM de Azure.
- **Documentación**: [docs/README.md](docs/README.md). Empieza por ahí.
- **Reglas para personas y agentes**: [AGENTS.md](AGENTS.md).

## Arranque local

Requisitos: Python 3.12+, [`uv`](https://docs.astral.sh/uv/) y Docker.

```bash
uv sync
cp .env.example .env
docker compose -f docker-compose.dev.yml up -d
uv run alembic upgrade head
uv run uvicorn src.main:app --reload
```

- API: <http://localhost:8000/api/v1>
- OpenAPI: <http://localhost:8000/docs>
- Salud: <http://localhost:8000/api/v1/health>

Con el `.env.example` tal cual no necesitas ninguna clave: FlightAPI responde con datos simulados y los códigos de verificación aparecen en la consola del servidor.

## Qué construir

El backlog está en [docs/backlog/technical-stories.md](docs/backlog/technical-stories.md): 37 historias técnicas ordenadas en 5 sprints. Con Claude Code: `/navby-implement-story TS-33` (ver [CLAUDE.md](CLAUDE.md)).
