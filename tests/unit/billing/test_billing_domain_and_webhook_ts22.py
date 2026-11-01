import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.billing.domain.model.aggregates.credit_order import (
    CreditOrder,
    OrderStatus,
)
from src.modules.billing.domain.model.value_objects.credit_package import (
    CreditPackage,
    get_package_by_code,
)
from src.modules.billing.domain.model.value_objects.payment_info import PaymentInfo
from src.modules.billing.infrastructure.adapters.mercadopago_payment_gateway import (
    verify_mp_webhook_signature,
)
from src.shared.domain.domain_error import DomainError


def test_credit_order_transitions_and_payment_mismatch() -> None:
    pkg = get_package_by_code("pack_100")
    assert pkg is not None
    assert pkg.credits == 100
    assert pkg.price_pen == Decimal("16.90")

    now = datetime.now(UTC)
    order = CreditOrder.create(
        user_id=uuid4(),
        package=pkg,
        mp_preference_id="pref_123",
        now=now,
    )
    assert order.status == OrderStatus.PENDING
    assert order.expires_at == now + timedelta(hours=24)

    # Mismatched amount -> raises DomainError("PAYMENT_MISMATCH") and stays PENDING
    bad_payment = PaymentInfo(
        payment_id="pay_bad",
        status="approved",
        external_reference=str(order.id),
        amount=Decimal("1.00"),
        currency="PEN",
    )
    with pytest.raises(DomainError) as exc:
        order.approve(bad_payment, now=now)
    assert exc.value.code == "PAYMENT_MISMATCH"
    assert order.status == OrderStatus.PENDING

    # Valid payment -> APPROVED
    good_payment = PaymentInfo(
        payment_id="pay_ok",
        status="approved",
        external_reference=str(order.id),
        amount=Decimal("16.90"),
        currency="PEN",
    )
    approved_changed = order.approve(good_payment, now=now)
    assert approved_changed is True
    assert order.status == OrderStatus.APPROVED
    assert order.mp_payment_id == "pay_ok"

    # Second approve is idempotent no-op
    assert order.approve(good_payment, now=now) is False

    # Reverse from APPROVED -> REVERSED
    rev_changed = order.reverse("pay_ok", now=now)
    assert rev_changed is True
    assert order.status == OrderStatus.REVERSED
    _ = CreditPackage


def test_webhook_hmac_signature_and_timestamp_window() -> None:
    secret = "mp_webhook_test_secret"
    data_id = "99887766"
    request_id = "req-abc-123"
    ts_now = int(datetime.now(UTC).timestamp())
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts_now};"
    sig = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    x_signature = f"ts={ts_now},v1={sig}"

    assert (
        verify_mp_webhook_signature(
            x_signature=x_signature,
            x_request_id=request_id,
            data_id=data_id,
            secret=secret,
            now_ts=ts_now,
        )
        is True
    )

    # Expired timestamp (> 300s) -> False
    assert (
        verify_mp_webhook_signature(
            x_signature=x_signature,
            x_request_id=request_id,
            data_id=data_id,
            secret=secret,
            now_ts=ts_now + 305,
        )
        is False
    )

    # Wrong signature -> False
    assert (
        verify_mp_webhook_signature(
            x_signature=f"ts={ts_now},v1=deadbeef",
            x_request_id=request_id,
            data_id=data_id,
            secret=secret,
            now_ts=ts_now,
        )
        is False
    )
