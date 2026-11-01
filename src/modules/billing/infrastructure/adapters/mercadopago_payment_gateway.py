import asyncio
import hashlib
import hmac
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import mercadopago

from src.modules.billing.application.acl.ports.payment_gateway import PaymentGateway
from src.modules.billing.domain.model.aggregates.credit_order import CreditOrder
from src.modules.billing.domain.model.value_objects.payment_info import PaymentInfo

logger = logging.getLogger(__name__)


def verify_mp_webhook_signature(
    x_signature: str,
    x_request_id: str,
    data_id: str,
    secret: str,
    now_ts: int | None = None,
) -> bool:
    if not secret or not x_signature or not data_id:
        return False

    parts: dict[str, str] = {}
    for item in x_signature.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts[k.strip()] = v.strip()

    ts_str = parts.get("ts")
    v1_sig = parts.get("v1")
    if not ts_str or not v1_sig:
        return False

    try:
        ts_val = int(ts_str)
    except ValueError:
        return False

    current_ts = now_ts if now_ts is not None else int(datetime.now(UTC).timestamp())
    if abs(current_ts - ts_val) > 300:
        return False

    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts_val};"
    computed = hmac.new(
        secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, v1_sig)


class MercadoPagoPaymentGateway(PaymentGateway):
    def __init__(
        self,
        access_token: str,
        webhook_secret: str,
        webapp_url: str,
        api_public_url: str,
    ) -> None:
        self._access_token = access_token
        self._webhook_secret = webhook_secret
        self._webapp_url = webapp_url.rstrip("/")
        self._api_public_url = api_public_url.rstrip("/")

    def _create_pref_sync(self, order: CreditOrder) -> tuple[str, str]:
        sdk = mercadopago.SDK(self._access_token)
        result_url = f"{self._webapp_url}/billing/result"
        preference_data: dict[str, Any] = {
            "items": [
                {
                    "id": order.package.code,
                    "title": (
                        f"Navby - Paquete {order.package.name} ({order.package.credits} créditos)"
                    ),
                    "quantity": 1,
                    "currency_id": "PEN",
                    "unit_price": float(order.amount),
                }
            ],
            "external_reference": str(order.id),
            "expires": True,
            "expiration_date_to": order.expires_at.isoformat(),
            "back_urls": {
                "success": result_url,
                "failure": result_url,
                "pending": result_url,
            },
            "auto_return": "approved",
        }
        if self._api_public_url:
            preference_data["notification_url"] = (
                f"{self._api_public_url}/api/v1/billing/webhooks/mercadopago"
            )

        resp = sdk.preference().create(preference_data)
        body = resp.get("response") or {}
        pref_id = str(body.get("id") or f"pref_{order.id}")
        checkout_url = str(
            body.get("sandbox_init_point")
            or body.get("init_point")
            or f"https://www.mercadopago.com.pe/checkout/v1/redirect?pref_id={pref_id}"
        )
        return pref_id, checkout_url

    async def create_preference(self, order: CreditOrder) -> tuple[str, str]:
        if not self._access_token:
            pref_id = f"sandbox_pref_{order.id}"
            url = f"https://www.mercadopago.com.pe/checkout/v1/redirect?pref_id={pref_id}"
            return pref_id, url
        return await asyncio.to_thread(self._create_pref_sync, order)

    def _get_payment_sync(self, payment_id: str) -> PaymentInfo | None:
        if not self._access_token:
            return None
        sdk = mercadopago.SDK(self._access_token)
        resp = sdk.payment().get(payment_id)
        if resp.get("status") != 200:
            return None
        body = resp.get("response") or {}
        return PaymentInfo(
            payment_id=str(body.get("id") or payment_id),
            status=str(body.get("status") or ""),
            external_reference=str(body.get("external_reference") or ""),
            amount=Decimal(str(body.get("transaction_amount") or "0.00")),
            currency=str(body.get("currency_id") or "PEN"),
        )

    async def get_payment(self, payment_id: str) -> PaymentInfo | None:
        return await asyncio.to_thread(self._get_payment_sync, payment_id)

    def verify_signature(self, x_signature: str, x_request_id: str, data_id: str) -> bool:
        return verify_mp_webhook_signature(
            x_signature=x_signature,
            x_request_id=x_request_id,
            data_id=data_id,
            secret=self._webhook_secret,
        )
