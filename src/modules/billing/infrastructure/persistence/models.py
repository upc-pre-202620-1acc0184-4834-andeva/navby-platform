from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.infrastructure.database import Base


class CreditWalletModel(Base):
    __tablename__ = "credit_wallets"
    __table_args__ = ({"schema": "billing"},)

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    free_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    free_credits_date: Mapped[date] = mapped_column(Date, nullable=False)
    paid_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CreditTransactionModel(Base):
    __tablename__ = "credit_transactions"
    __table_args__ = ({"schema": "billing"},)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    free_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paid_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CreditOrderModel(Base):
    __tablename__ = "credit_orders"
    __table_args__ = ({"schema": "billing"},)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    package_code: Mapped[str] = mapped_column(String(20), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PEN")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mp_preference_id: Mapped[str] = mapped_column(Text, nullable=False)
    mp_payment_id: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
