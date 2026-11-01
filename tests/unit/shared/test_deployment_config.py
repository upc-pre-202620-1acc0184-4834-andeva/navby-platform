from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text

from src.shared.infrastructure.database import get_engine

ROOT_DIR = Path(__file__).resolve().parents[3]


def test_ts38_docker_compose_and_caddy_and_single_worker() -> None:
    compose_path = ROOT_DIR / "docker-compose.yml"
    dockerfile_path = ROOT_DIR / "Dockerfile"
    caddyfile_path = ROOT_DIR / "Caddyfile"
    alembic_ini_path = ROOT_DIR / "alembic.ini"

    assert compose_path.exists()
    assert dockerfile_path.exists()
    assert caddyfile_path.exists()
    assert alembic_ini_path.exists()

    compose_data: dict[str, Any] = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose_data["services"]
    assert set(services.keys()) == {"platform", "postgres", "redis", "caddy"}

    assert "ports" not in services["platform"]
    assert "ports" not in services["postgres"]
    assert "ports" not in services["redis"]
    caddy_ports = services["caddy"]["ports"]
    assert "80:80" in caddy_ports
    assert "443:443" in caddy_ports

    dockerfile_text = dockerfile_path.read_text(encoding="utf-8")
    assert "--workers 1" in dockerfile_text or '"--workers", "1"' in dockerfile_text
    assert "alembic upgrade head" in dockerfile_text

    caddy_text = caddyfile_path.read_text(encoding="utf-8")
    assert "reverse_proxy platform:8000" in caddy_text


async def test_ts38_alembic_shared_schema_exists_after_upgrade() -> None:
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'shared' AND table_name = 'outbox_events'"
            )
        )
        row = res.first()
        assert row is not None
        assert row[0] == "outbox_events"
