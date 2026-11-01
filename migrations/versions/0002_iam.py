"""IAM schema and tables (users, refresh_tokens).

Revision ID: 0002_iam
Revises: 0001_shared
Create Date: 2026-10-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_iam"
down_revision: str | None = "0001_shared"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS iam;")
    op.execute(
        """
        CREATE TABLE iam.users (
            id                 UUID PRIMARY KEY,
            email              VARCHAR(254) NOT NULL UNIQUE,
            full_name          VARCHAR(100) NOT NULL,
            password_hash      VARCHAR(60),
            google_sub         VARCHAR(255) UNIQUE,
            email_verified     BOOLEAN NOT NULL DEFAULT FALSE,
            terms_version      VARCHAR(20) NOT NULL,
            terms_accepted_at  TIMESTAMPTZ NOT NULL,
            deleted_at         TIMESTAMPTZ,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT users_has_login_method CHECK (
                deleted_at IS NOT NULL OR password_hash IS NOT NULL OR google_sub IS NOT NULL)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE iam.refresh_tokens (
            id                UUID PRIMARY KEY,
            user_id           UUID NOT NULL REFERENCES iam.users(id) ON DELETE CASCADE,
            token_hash        CHAR(64) NOT NULL UNIQUE,
            replaced_by_hash  CHAR(64),
            expires_at        TIMESTAMPTZ NOT NULL,
            revoked_at        TIMESTAMPTZ,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX ix_refresh_tokens_user ON iam.refresh_tokens (user_id);")
    op.execute("CREATE INDEX ix_refresh_tokens_expires ON iam.refresh_tokens (expires_at);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS iam.refresh_tokens;")
    op.execute("DROP TABLE IF EXISTS iam.users;")
    op.execute("DROP SCHEMA IF EXISTS iam;")
