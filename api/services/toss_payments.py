"""Toss Payments API wrapper for payment confirmation and management."""

import base64
import logging
import os

import httpx

logger = logging.getLogger("adscope.toss_payments")

# 환경변수에서 키 로드 (테스트 키 기본값)
TOSS_SECRET_KEY = os.getenv(
    "TOSS_SECRET_KEY",
    "test_sk_zXLkKEypNArWmo50nX3lmeaxYG5R",  # 토스 테스트 시크릿 키
)
TOSS_CLIENT_KEY = os.getenv(
    "TOSS_CLIENT_KEY",
    "test_ck_D5GePWvyJnrK0W0k6q8gLzN97Eoq",  # 토스 테스트 클라이언트 키
)

TOSS_API_BASE = "https://api.tosspayments.com/v1"


def _make_auth_header() -> str:
    """Base64 인코딩된 Authorization 헤더 생성 (시크릿키 + ':')."""
    encoded = base64.b64encode(f"{TOSS_SECRET_KEY}:".encode()).decode()
    return f"Basic {encoded}"


async def confirm_payment(payment_key: str, order_id: str, amount: int) -> dict:
    """토스페이먼츠 결제 승인 API 호출.

    POST https://api.tosspayments.com/v1/payments/confirm
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{TOSS_API_BASE}/payments/confirm",
            headers={
                "Authorization": _make_auth_header(),
                "Content-Type": "application/json",
            },
            json={
                "paymentKey": payment_key,
                "orderId": order_id,
                "amount": amount,
            },
        )
        data = resp.json()
        if resp.status_code != 200:
            logger.error(
                "Toss confirm failed: status=%d code=%s message=%s",
                resp.status_code,
                data.get("code", ""),
                data.get("message", ""),
            )
            raise TossPaymentError(
                code=data.get("code", "UNKNOWN"),
                message=data.get("message", "Payment confirmation failed"),
                status_code=resp.status_code,
            )
        return data


async def get_payment(payment_key: str) -> dict:
    """토스페이먼츠 결제 조회 API 호출.

    GET https://api.tosspayments.com/v1/payments/{paymentKey}
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{TOSS_API_BASE}/payments/{payment_key}",
            headers={"Authorization": _make_auth_header()},
        )
        data = resp.json()
        if resp.status_code != 200:
            raise TossPaymentError(
                code=data.get("code", "UNKNOWN"),
                message=data.get("message", "Payment lookup failed"),
                status_code=resp.status_code,
            )
        return data


async def cancel_payment(payment_key: str, cancel_reason: str) -> dict:
    """토스페이먼츠 결제 취소 API 호출.

    POST https://api.tosspayments.com/v1/payments/{paymentKey}/cancel
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{TOSS_API_BASE}/payments/{payment_key}/cancel",
            headers={
                "Authorization": _make_auth_header(),
                "Content-Type": "application/json",
            },
            json={"cancelReason": cancel_reason},
        )
        data = resp.json()
        if resp.status_code != 200:
            raise TossPaymentError(
                code=data.get("code", "UNKNOWN"),
                message=data.get("message", "Payment cancellation failed"),
                status_code=resp.status_code,
            )
        return data


class TossPaymentError(Exception):
    """토스페이먼츠 API 오류."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(f"[{code}] {message}")
