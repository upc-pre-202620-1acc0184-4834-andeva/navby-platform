"""Shared schema and outbox_events table.

Revision ID: 0001_shared
Revises: None
Create Date: 2026-10-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_shared"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS shared;")
    op.execute(
        """
        CREATE TABLE shared.outbox_events (
            id            UUID PRIMARY KEY,
            event_type    VARCHAR(100) NOT NULL,
            payload       JSONB NOT NULL,
            occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            processed_at  TIMESTAMPTZ,
            attempts      SMALLINT NOT NULL DEFAULT 0,
            failed_at     TIMESTAMPTZ,
            last_error    TEXT
        );
        """
    )
    op.execute(
        """
        CREATE INDEX ix_outbox_pending ON shared.outbox_events (occurred_at)
            WHERE processed_at IS NULL AND failed_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shared.outbox_events;")
    op.execute("DROP SCHEMA IF EXISTS shared;")
