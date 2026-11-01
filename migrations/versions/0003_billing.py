"""Billing schema and tables (credit_wallets, credit_transactions, credit_orders).

Revision ID: 0003_billing
Revises: 0002_iam
Create Date: 2026-10-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_billing"
down_revision: str | None = "0002_iam"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS billing;")
    op.execute(
        """
        CREATE TABLE billing.credit_wallets (
            user_id            UUID PRIMARY KEY,
            free_credits       SMALLINT NOT NULL CHECK (free_credits BETWEEN 0 AND 10),
            free_credits_date  DATE NOT NULL,
            paid_credits       INTEGER NOT NULL DEFAULT 0 CHECK (paid_credits >= 0),
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE billing.credit_transactions (
            id            UUID PRIMARY KEY,
            user_id       UUID NOT NULL,
            type          VARCHAR(20) NOT NULL CHECK (type IN
                          ('SEARCH_DEBIT', 'SEARCH_REFUND', 'PURCHASE', 'PURCHASE_REVERSAL', 'ACCOUNT_DELETION')),
            free_delta    SMALLINT NOT NULL,
            paid_delta    INTEGER NOT NULL,
            reference_id  VARCHAR(64) NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT credit_tx_idempotent UNIQUE (type, reference_id)
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_credit_tx_user_created ON billing.credit_transactions (user_id, created_at DESC);"
    )
    op.execute(
        """
        CREATE TABLE billing.credit_orders (
            id                UUID PRIMARY KEY,
            user_id           UUID NOT NULL,
            package_code      VARCHAR(16) NOT NULL CHECK (package_code IN ('pack_50', 'pack_100', 'pack_250')),
            credits           INTEGER NOT NULL CHECK (credits > 0),
            amount            NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
            currency          CHAR(3) NOT NULL DEFAULT 'PEN' CHECK (currency = 'PEN'),
            status            VARCHAR(10) NOT NULL CHECK (status IN
                              ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'REVERSED')),
            expires_at        TIMESTAMPTZ NOT NULL,
            mp_preference_id  VARCHAR(64) NOT NULL,
            mp_payment_id     VARCHAR(64) UNIQUE,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_credit_orders_user_created ON billing.credit_orders (user_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX ix_credit_orders_pending ON billing.credit_orders (expires_at) WHERE status = 'PENDING';"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS billing.credit_orders;")
    op.execute("DROP TABLE IF EXISTS billing.credit_transactions;")
    op.execute("DROP TABLE IF EXISTS billing.credit_wallets;")
    op.execute("DROP SCHEMA IF EXISTS billing;")
