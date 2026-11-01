from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, ConfigDict

from src.modules.billing.application.acl.ports.payment_gateway import PaymentGateway
from src.modules.billing.application.commands.create_order import (
    CreateOrderCommand,
    CreateOrderHandler,
)
from src.modules.billing.application.commands.handle_payment_notification import (
    HandlePaymentNotificationCommand,
    HandlePaymentNotificationHandler,
)
from src.modules.billing.application.queries.get_order import (
    GetOrderHandler,
    GetOrderQuery,
)
from src.modules.billing.application.queries.get_wallet import (
    GetWalletHandler,
    GetWalletQuery,
)
from src.modules.billing.application.queries.list_packages import ListPackagesHandler
from src.modules.billing.application.queries.list_transactions import (
    ListTransactionsHandler,
    ListTransactionsQuery,
)
from src.modules.billing.infrastructure.adapters.mercadopago_payment_gateway import (
    MercadoPagoPaymentGateway,
)
from src.modules.billing.infrastructure.persistence.sqlalchemy_credit_order_repository import (
    SqlAlchemyCreditOrderRepository,
)
from src.modules.billing.infrastructure.persistence.sqlalchemy_credit_transaction_repository import (  # noqa: E501
    SqlAlchemyCreditTransactionRepository,
)
from src.modules.billing.infrastructure.persistence.sqlalchemy_credit_wallet_repository import (
    SqlAlchemyCreditWalletRepository,
)
from src.shared.application.current_user import CurrentUser
from src.shared.infrastructure.database import get_session_factory
from src.shared.infrastructure.settings import Settings, get_settings
from src.shared.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.shared.interfaces.auth import get_current_user, get_verified_user
from src.shared.interfaces.http_errors import raise_for_error
from src.shared.interfaces.page import Page
from src.shared.interfaces.problem_details import ProblemDetails

router = APIRouter(tags=["billing"])


class WalletResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    free_credits: int
    paid_credits: int
    total_credits: int
    searches_available: int
    free_credits_reset_at: str


class TransactionItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    type: str
    free_delta: int
    paid_delta: int
    reference_id: str | None
    created_at: datetime


class PackageItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    credits: int
    searches: int
    price: str
    usd_reference: str


class PackagesListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str
    packages: list[PackageItemResponse]


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_code: str


class OrderCreatedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID
    package_code: str
    credits: int
    amount: str
    currency: str
    status: str
    expires_at: str
    checkout_url: str


class OrderDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID
    package_code: str
    credits: int
    amount: str
    currency: str
    status: str
    expires_at: str


def get_uow() -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(get_session_factory())


def get_payment_gateway(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PaymentGateway:
    return MercadoPagoPaymentGateway(
        access_token=settings.mercadopago_access_token,
        webhook_secret=settings.mercadopago_webhook_secret,
        webapp_url=settings.webapp_url,
        api_public_url=settings.api_public_url,
    )


@router.get(
    "/billing/wallet",
    response_model=WalletResponse,
    responses={
        401: {"model": ProblemDetails},
    },
)
async def get_wallet(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
) -> WalletResponse:
    handler = GetWalletHandler(
        uow=uow,
        wallet_repo=SqlAlchemyCreditWalletRepository(uow),
    )
    res = await handler.handle(GetWalletQuery(user_id=current_user.user_id))
    if res.is_failure:
        raise_for_error(res.error)
    dto = res.value
    reset_str = dto.free_credits_reset_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return WalletResponse(
        free_credits=dto.free_credits,
        paid_credits=dto.paid_credits,
        total_credits=dto.total_credits,
        searches_available=dto.searches_available,
        free_credits_reset_at=reset_str,
    )


@router.get(
    "/billing/transactions",
    response_model=Page[TransactionItemResponse],
    responses={
        401: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
)
async def list_transactions(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    page: Annotated[int, Query()] = 1,
    page_size: Annotated[int, Query()] = 20,
) -> Page[TransactionItemResponse]:
    handler = ListTransactionsHandler(
        uow=uow,
        tx_repo=SqlAlchemyCreditTransactionRepository(uow),
    )
    res = await handler.handle(
        ListTransactionsQuery(
            user_id=current_user.user_id,
            page=page,
            page_size=page_size,
        )
    )
    if res.is_failure:
        raise_for_error(res.error)
    dto = res.value
    return Page(
        items=[
            TransactionItemResponse(
                id=tx.id,
                type=tx.type.value,
                free_delta=tx.free_delta,
                paid_delta=tx.paid_delta,
                reference_id=tx.reference_id,
                created_at=tx.created_at,
            )
            for tx in dto.items
        ],
        page=dto.page,
        page_size=dto.page_size,
        total=dto.total,
    )


@router.get(
    "/billing/packages",
    response_model=PackagesListResponse,
    responses={
        500: {"model": ProblemDetails},
    },
)
async def list_packages() -> PackagesListResponse:
    handler = ListPackagesHandler()
    res = handler.handle()
    return PackagesListResponse(
        currency="PEN",
        packages=[
            PackageItemResponse(
                code=p.code,
                name=p.name,
                credits=p.credits,
                searches=p.searches,
                price=f"{p.price_pen:.2f}",
                usd_reference=f"{p.usd_reference:.2f}",
            )
            for p in res.value
        ],
    )


@router.post(
    "/billing/orders",
    response_model=OrderCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_verified_user)],
    responses={
        401: {"model": ProblemDetails},
        403: {"model": ProblemDetails},
        404: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
)
async def create_order(
    body: CreateOrderRequest,
    current_user: Annotated[CurrentUser, Depends(get_verified_user)],
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
) -> OrderCreatedResponse:
    handler = CreateOrderHandler(
        uow=uow,
        order_repo=SqlAlchemyCreditOrderRepository(uow),
        payment_gateway=gateway,
    )
    res = await handler.handle(
        CreateOrderCommand(
            user_id=current_user.user_id,
            package_code=body.package_code,
        )
    )
    if res.is_failure:
        raise_for_error(res.error)
    order = res.value.order
    return OrderCreatedResponse(
        order_id=order.id,
        package_code=order.package.code,
        credits=order.package.credits,
        amount=f"{order.amount:.2f}",
        currency=order.currency,
        status=order.status.value,
        expires_at=order.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        checkout_url=res.value.checkout_url,
    )


@router.get(
    "/billing/orders/{order_id}",
    response_model=OrderDetailResponse,
    responses={
        401: {"model": ProblemDetails},
        404: {"model": ProblemDetails},
    },
)
async def get_order(
    order_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
) -> OrderDetailResponse:
    handler = GetOrderHandler(
        uow=uow,
        order_repo=SqlAlchemyCreditOrderRepository(uow),
    )
    res = await handler.handle(GetOrderQuery(user_id=current_user.user_id, order_id=order_id))
    if res.is_failure:
        raise_for_error(res.error)
    order = res.value
    return OrderDetailResponse(
        order_id=order.id,
        package_code=order.package.code,
        credits=order.package.credits,
        amount=f"{order.amount:.2f}",
        currency=order.currency,
        status=order.status.value,
        expires_at=order.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


@router.post(
    "/billing/webhooks/mercadopago",
    responses={
        401: {"model": ProblemDetails},
    },
)
async def mercadopago_webhook(
    body: dict[str, Any],
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
    x_signature: Annotated[str, Header()] = "",
    x_request_id: Annotated[str, Header()] = "",
) -> dict[str, str]:
    event_type = str(body.get("type") or body.get("topic") or "")
    data_obj = body.get("data") or {}
    data_id = str(data_obj.get("id") or "") if isinstance(data_obj, dict) else ""

    handler = HandlePaymentNotificationHandler(
        uow=uow,
        order_repo=SqlAlchemyCreditOrderRepository(uow),
        wallet_repo=SqlAlchemyCreditWalletRepository(uow),
        tx_repo=SqlAlchemyCreditTransactionRepository(uow),
        payment_gateway=gateway,
    )
    res = await handler.handle(
        HandlePaymentNotificationCommand(
            event_type=event_type,
            data_id=data_id,
            x_signature=x_signature,
            x_request_id=x_request_id,
        )
    )
    if res.is_failure:
        raise_for_error(res.error)
    return {"status": "ok"}
