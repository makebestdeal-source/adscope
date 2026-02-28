"""PortOne V2 API wrapper for payment verification."""

import os
import logging

import httpx

logger = logging.getLogger("adscope.portone")

PORTONE_API_SECRET = os.getenv("PORTONE_API_SECRET", "")
PORTONE_BASE_URL = "https://api.portone.io"


async def verify_payment(imp_uid: str) -> dict:
    """Verify a payment via PortOne V2 API.

    Returns the payment data dict from PortOne, or raises on error.
    """
    if not PORTONE_API_SECRET:
        logger.warning("PORTONE_API_SECRET not set - skipping verification")
        return {"status": "unverified", "amount": 0}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{PORTONE_BASE_URL}/payments/{imp_uid}",
            headers={"Authorization": f"PortOne {PORTONE_API_SECRET}"},
        )
        resp.raise_for_status()
        return resp.json()
