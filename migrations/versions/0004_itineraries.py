"""Itineraries schema and saved_itineraries table.

Revision ID: 0004_itineraries
Revises: 0003_billing
Create Date: 2026-10-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_itineraries"
down_revision: str | None = "0003_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS itineraries;")
    op.execute(
        """
        CREATE TABLE itineraries.saved_itineraries (
            id              UUID PRIMARY KEY,
            user_id         UUID NOT NULL,
            offer_id        VARCHAR(40) NOT NULL,
            name            VARCHAR(80) NOT NULL,
            trip_type       VARCHAR(10) NOT NULL CHECK (trip_type IN ('ONE_WAY', 'ROUND_TRIP')),
            origin          CHAR(3) NOT NULL,
            destination     CHAR(3) NOT NULL,
            departure_date  DATE NOT NULL,
            return_date     DATE,
            offer_snapshot  JSONB NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT return_matches_trip CHECK ((trip_type = 'ROUND_TRIP') = (return_date IS NOT NULL)),
            CONSTRAINT one_save_per_offer UNIQUE (user_id, offer_id)
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_saved_itineraries_user_created ON itineraries.saved_itineraries (user_id, created_at DESC);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS itineraries.saved_itineraries;")
    op.execute("DROP SCHEMA IF EXISTS itineraries;")
