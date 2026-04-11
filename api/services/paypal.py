"""PayPal REST API v2 wrapper for payment processing."""
import logging
import os

import httpx

logger = logging.getLogger("adscope.paypal")

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # "sandbox" or "live"

PAYPAL_API_BASE = (
    "https://api-m.paypal.com"
    if PAYPAL_MODE == "live"
    else "https://api-m.sandbox.paypal.com"
)


async def _get_access_token() -> str:
    """OAuth2 client credentials grant."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{PAYPAL_API_BASE}/v1/oauth2/token",
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def create_order(amount_usd: int, reference_id: str, description: str) -> dict:
    """Create a PayPal CAPTURE order.

    Args:
        amount_usd: Amount in USD (integer dollars, e.g. 35 for $35.00)
        reference_id: Idempotency/reference key
        description: Human-readable description

    Returns the PayPal order object (contains ``id`` field as the order ID).
    """
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{PAYPAL_API_BASE}/v2/checkout/orders",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": reference_id[:64],  # idempotency key
            },
            json={
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "reference_id": reference_id,
                        "description": description,
                        "amount": {
                            "currency_code": "USD",
                            "value": f"{amount_usd}.00",
                        },
                    }
                ],
            },
        )
        data = resp.json()
        if resp.status_code not in (200, 201):
            logger.error(
                "PayPal create_order failed: status=%d name=%s message=%s",
                resp.status_code,
                data.get("name", ""),
                data.get("message", ""),
            )
            raise PayPalError(
                code=data.get("name", "UNKNOWN"),
                message=data.get("message", "Order creation failed"),
                status_code=resp.status_code,
            )
        return data


async def capture_order(paypal_order_id: str) -> dict:
    """Capture an approved PayPal order.

    Returns the capture result (``status`` should be ``COMPLETED``).
    """
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{PAYPAL_API_BASE}/v2/checkout/orders/{paypal_order_id}/capture",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        data = resp.json()
        if resp.status_code not in (200, 201):
            logger.error(
                "PayPal capture_order failed: status=%d name=%s message=%s",
                resp.status_code,
                data.get("name", ""),
                data.get("message", ""),
            )
            raise PayPalError(
                code=data.get("name", "UNKNOWN"),
                message=data.get("message", "Order capture failed"),
                status_code=resp.status_code,
            )
        return data


class PayPalError(Exception):
    """PayPal API error."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(f"[{code}] {message}")
