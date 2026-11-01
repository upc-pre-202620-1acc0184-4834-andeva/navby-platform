import asyncio
import sys
from uuid import UUID

from src.shared.infrastructure.database import close_database, get_session_factory
from src.shared.infrastructure.outbox_relay import OutboxRelay


async def _run_retry(event_id: UUID) -> int:
    try:
        session_factory = get_session_factory()
        updated = await OutboxRelay.retry_event(session_factory, event_id)
        return 0 if updated else 1
    finally:
        await close_database()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2 or args[0] != "retry":
        sys.stderr.write("Usage: python -m src.shared.outbox retry <event_id>\n")
        return 2
    try:
        event_id = UUID(args[1])
    except ValueError:
        sys.stderr.write("Invalid UUID for event_id\n")
        return 2
    return asyncio.run(_run_retry(event_id))


if __name__ == "__main__":
    raise SystemExit(main())
