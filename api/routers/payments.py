"""Payment API -- Toss Payments 결제 연동.

Flow:
  1. 프론트엔드에서 /api/payments/ready 호출 -> orderId, amount 등 반환
  2. 프론트에서 토스 결제 위젯으로 결제 진행
  3. 성공 시 토스가 successUrl로 리다이렉트 (paymentKey, orderId, amount 포함)
  4. 프론트 success 페이지에서 /api/payments/confirm 호출 -> 서버가 토스 API로 결제 승인
  5. 승인 완료 시 유저 플랜 활성화
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from api.pricing import PLAN_PRICES, PLAN_PRICES_USD, validate_billable_plan
from database import get_db
from database.models import User, PaymentRecord

logger = logging.getLogger("adscope.payments")

router = APIRouter(prefix="/api/payments", tags=["payments"])

# 토스 클라이언트 키 (프론트에서 필요)
TOSS_CLIENT_KEY = os.getenv(
    "TOSS_CLIENT_KEY",
    "test_ck_D5GePWvyJnrK0W0k6q8gLzN97Eoq",
)


# ─── Request/Response Schemas ───────────────────────

class ReadyRequest(BaseModel):
    plan: str
    plan_period: str  # monthly / yearly


class ConfirmRequest(BaseModel):
    payment_key: str  # paymentKey from Toss
    order_id: str     # orderId
    amount: int       # amount


class EnterpriseInquiryRequest(BaseModel):
    company_name: str
    contact_name: str
    email: str
    phone: str | None = None
    expected_users: str | None = None
    expected_advertisers: str | None = None
    message: str | None = None


# ─── 1. 결제 준비 ───────────────────────────────────

@router.post("/ready")
async def payment_ready(
    body: ReadyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """결제 준비: orderId 생성 및 PaymentRecord 생성."""
    try:
        validate_billable_plan(body.plan, body.plan_period)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    amount = PLAN_PRICES[body.plan][body.plan_period]
    order_id = f"ADSCOPE_{user.id}_{int(time.time())}"

    record = PaymentRecord(
        user_id=user.id,
        merchant_uid=order_id,
        plan=body.plan,
        plan_period=body.plan_period,
        amount=amount,
        status="pending",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    plan_label = "Lite" if body.plan == "lite" else "Full"
    period_label = "Monthly" if body.plan_period == "monthly" else "Yearly"

    return {
        "order_id": order_id,
        "order_name": f"AdScope {plan_label} ({period_label})",
        "amount": amount,
        "plan": body.plan,
        "plan_period": body.plan_period,
        "customer_email": user.email,
        "customer_name": user.name or user.email.split("@")[0],
        "client_key": TOSS_CLIENT_KEY,
        "payment_id": record.id,
    }


# ─── 2. 결제 승인 ───────────────────────────────────

@router.post("/confirm")
async def payment_confirm(
    body: ConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """토스페이먼츠 결제 승인: paymentKey + orderId + amount 검증 후 토스 API 호출."""
    # DB에서 해당 주문 조회
    result = await db.execute(
        select(PaymentRecord).where(
            PaymentRecord.merchant_uid == body.order_id,
            PaymentRecord.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Payment record not found")
    if record.status != "pending":
        raise HTTPException(400, f"Payment already processed (status={record.status})")

    # 금액 검증
    if body.amount != record.amount:
        record.status = "failed"
        record.notes = f"Amount mismatch: expected {record.amount}, got {body.amount}"
        await db.commit()
        raise HTTPException(400, "Payment amount mismatch")

    # 토스 API로 결제 승인
    try:
        from api.services.toss_payments import confirm_payment, TossPaymentError

        toss_data = await confirm_payment(
            payment_key=body.payment_key,
            order_id=body.order_id,
            amount=body.amount,
        )
        record.payment_key = body.payment_key
        record.toss_response = toss_data
        record.pay_method = toss_data.get("method", "")

    except TossPaymentError as e:
        record.status = "failed"
        record.notes = f"Toss API error: [{e.code}] {e.message}"
        await db.commit()
        logger.error("Toss confirm failed for order %s: %s", body.order_id, str(e))
        raise HTTPException(e.status_code, f"Payment failed: {e.message}")
    except Exception as e:
        record.status = "failed"
        record.notes = f"Unexpected error: {str(e)}"
        await db.commit()
        logger.exception("Unexpected error during payment confirm for order %s", body.order_id)
        raise HTTPException(500, "Payment confirmation failed")

    # 결제 완료 처리
    record.status = "paid"
    record.paid_at = datetime.now(timezone.utc)

    # 유저 플랜 활성화
    now = datetime.now(timezone.utc)
    user.plan = record.plan
    user.plan_period = record.plan_period
    user.payment_confirmed = True
    user.plan_started_at = now
    if record.plan_period == "yearly":
        user.plan_expires_at = now + timedelta(days=365)
    else:
        user.plan_expires_at = now + timedelta(days=30)

    await db.commit()
    logger.info(
        "Payment confirmed: user=%s plan=%s period=%s amount=%d",
        user.email, record.plan, record.plan_period, record.amount,
    )

    return {
        "status": "paid",
        "message": "Payment confirmed. Plan activated.",
        "payment_id": record.id,
        "plan": record.plan,
        "plan_period": record.plan_period,
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
    }


# ─── 3. 결제 성공 콜백 (프론트에서 확인용) ──────────

@router.get("/success")
async def payment_success(
    paymentKey: str,
    orderId: str,
    amount: int,
):
    """토스 결제 성공 리다이렉트 콜백.

    프론트엔드의 successUrl이 이 엔드포인트를 가리키는 대신,
    프론트 success 페이지에서 직접 /confirm 을 호출합니다.
    이 엔드포인트는 정보 확인용으로만 제공됩니다.
    """
    return {
        "status": "success",
        "payment_key": paymentKey,
        "order_id": orderId,
        "amount": amount,
    }


# ─── 4. 결제 실패 콜백 ──────────────────────────────

@router.get("/fail")
async def payment_fail(
    code: str = "",
    message: str = "",
    orderId: str = "",
):
    """토스 결제 실패 리다이렉트 콜백."""
    return {
        "status": "fail",
        "code": code,
        "message": message,
        "order_id": orderId,
    }


# ─── 5. 토스 웹훅 ───────────────────────────────────

def _verify_toss_webhook_signature(raw_body: bytes, signature: str, secret_key: str) -> bool:
    """Toss 웹훅 HMAC-SHA256 서명 검증."""
    import hashlib
    import hmac
    import base64
    expected = base64.b64encode(
        hmac.new(secret_key.encode(), raw_body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """토스페이먼츠 웹훅 처리 (결제 상태 변경 알림).

    토스에서 POST로 결제 상태 변경 시 호출됩니다.
    """
    raw_body = await request.body()

    # 웹훅 서명 검증 (TOSS_WEBHOOK_SECRET 설정 시)
    toss_webhook_secret = os.getenv("TOSS_WEBHOOK_SECRET", "")
    if toss_webhook_secret:
        signature = request.headers.get("Toss-Signature", "")
        if not signature or not _verify_toss_webhook_signature(raw_body, signature, toss_webhook_secret):
            logger.warning("Toss webhook: invalid signature from %s", request.client)
            raise HTTPException(401, "Invalid webhook signature")

    try:
        import json
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    event_type = body.get("eventType", "")
    data = body.get("data", {})
    order_id = data.get("orderId", "")
    payment_key = data.get("paymentKey", "")

    logger.info("Toss webhook received: event=%s orderId=%s", event_type, order_id)

    if not order_id:
        return {"status": "ignored", "reason": "no orderId"}

    result = await db.execute(
        select(PaymentRecord).where(PaymentRecord.merchant_uid == order_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        logger.warning("Webhook: payment record not found for orderId=%s", order_id)
        return {"status": "ignored", "reason": "record not found"}

    # 이벤트 타입별 처리
    if event_type == "PAYMENT_STATUS_CHANGED":
        status = data.get("status", "")
        if status == "CANCELED":
            record.status = "cancelled"
            record.notes = (record.notes or "") + f"\nWebhook: cancelled at {datetime.now(timezone.utc).isoformat()}"
        elif status == "PARTIAL_CANCELED":
            record.status = "refunded"
            record.notes = (record.notes or "") + f"\nWebhook: partial cancel at {datetime.now(timezone.utc).isoformat()}"

        if payment_key and not record.payment_key:
            record.payment_key = payment_key

        await db.commit()

    return {"status": "ok"}


# ─── 6. 내 결제 내역 ────────────────────────────────

@router.get("/my")
async def my_payments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 결제 내역 조회."""
    result = await db.execute(
        select(PaymentRecord)
        .where(PaymentRecord.user_id == user.id)
        .order_by(PaymentRecord.created_at.desc())
        .limit(50)
    )
    records = result.scalars().all()
    return [
        {
            "id": r.id,
            "order_id": r.merchant_uid,
            "payment_key": r.payment_key,
            "plan": r.plan,
            "plan_period": r.plan_period,
            "amount": r.amount,
            "pay_method": r.pay_method,
            "status": r.status,
            "paid_at": r.paid_at.isoformat() if r.paid_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


# ─── 8. PayPal 설정 ─────────────────────────────────

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")


@router.get("/paypal/config")
async def paypal_config():
    """PayPal 클라이언트 설정 반환 (프론트엔드용)."""
    if not PAYPAL_CLIENT_ID:
        raise HTTPException(503, "PayPal is not configured")
    return {"client_id": PAYPAL_CLIENT_ID, "mode": PAYPAL_MODE}


# ─── 9. PayPal 주문 생성 ──────────────────────────

class PayPalCreateOrderRequest(BaseModel):
    plan: str
    plan_period: str


@router.post("/paypal/create-order")
async def paypal_create_order(
    body: PayPalCreateOrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """PayPal 주문 생성: DB에 pending 레코드 생성 후 PayPal order ID 반환."""
    try:
        validate_billable_plan(body.plan, body.plan_period)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    amount_krw = PLAN_PRICES[body.plan][body.plan_period]
    amount_usd = PLAN_PRICES_USD[body.plan][body.plan_period]
    order_id = f"ADSCOPE_{user.id}_{int(time.time())}"

    record = PaymentRecord(
        user_id=user.id,
        merchant_uid=order_id,
        plan=body.plan,
        plan_period=body.plan_period,
        amount=amount_usd,   # USD amount stored (not KRW)
        pay_method="paypal",
        status="pending",
        notes=f"KRW equivalent: {amount_krw}",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    plan_label = "Lite" if body.plan == "lite" else "Full"
    period_label = "Monthly" if body.plan_period == "monthly" else "Yearly"

    try:
        from api.services.paypal import create_order as paypal_create, PayPalError

        paypal_data = await paypal_create(
            amount_usd=amount_usd,
            reference_id=order_id,
            description=f"AdScope {plan_label} ({period_label})",
        )
        paypal_order_id = paypal_data["id"]
        record.payment_key = paypal_order_id
        record.toss_response = paypal_data  # JSON 필드 재사용
        await db.commit()

    except Exception as e:
        record.status = "failed"
        record.notes = f"PayPal order creation error: {str(e)}"
        await db.commit()
        logger.error("PayPal create_order error for user=%s: %s", user.email, str(e))
        raise HTTPException(500, "PayPal order creation failed")

    return {
        "paypal_order_id": paypal_order_id,
        "payment_record_id": record.id,
        "amount_usd": amount_usd,
        "order_id": order_id,
    }


# ─── 10. PayPal 주문 캡처 ─────────────────────────

@router.post("/enterprise-inquiry")
async def enterprise_inquiry(body: EnterpriseInquiryRequest):
    """Receive an enterprise payment inquiry.

    Enterprise is handled by quotation, invoice, and bank transfer rather than
    the online checkout flow used for Lite/Full.
    """
    logger.info(
        "Enterprise inquiry: company=%s contact=%s email=%s users=%s advertisers=%s",
        body.company_name,
        body.contact_name,
        body.email,
        body.expected_users,
        body.expected_advertisers,
    )
    return {
        "status": "received",
        "plan": "enterprise",
        "payment_flow": "quotation_invoice_bank_transfer",
        "next_steps": [
            "담당자가 사용 규모를 확인합니다.",
            "견적서와 계약 조건을 협의합니다.",
            "세금계산서 발행 후 계좌이체 또는 월 정산으로 진행합니다.",
        ],
    }


class PayPalCaptureRequest(BaseModel):
    paypal_order_id: str


@router.post("/paypal/capture-order")
async def paypal_capture_order(
    body: PayPalCaptureRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """PayPal 결제 캡처 및 플랜 활성화."""
    result = await db.execute(
        select(PaymentRecord).where(
            PaymentRecord.payment_key == body.paypal_order_id,
            PaymentRecord.user_id == user.id,
            PaymentRecord.pay_method == "paypal",
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Payment record not found")
    if record.status == "paid":
        # 중복 요청 - 멱등성 보장
        return {
            "status": "paid",
            "message": "Payment already confirmed.",
            "plan": record.plan,
            "plan_period": record.plan_period,
            "amount": record.amount,
            "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
        }
    if record.status != "pending":
        raise HTTPException(400, f"Payment cannot be captured (status={record.status})")

    try:
        from api.services.paypal import capture_order as paypal_capture, PayPalError

        capture_data = await paypal_capture(body.paypal_order_id)
        capture_status = capture_data.get("status", "")
        if capture_status != "COMPLETED":
            raise Exception(f"Unexpected capture status: {capture_status}")

        record.toss_response = capture_data
        record.status = "paid"
        record.paid_at = datetime.now(timezone.utc)

    except Exception as e:
        record.status = "failed"
        record.notes = f"PayPal capture error: {str(e)}"
        await db.commit()
        logger.error("PayPal capture failed for order %s: %s", body.paypal_order_id, str(e))
        raise HTTPException(500, f"PayPal capture failed: {str(e)}")

    # 유저 플랜 활성화
    now = datetime.now(timezone.utc)
    user.plan = record.plan
    user.plan_period = record.plan_period
    user.payment_confirmed = True
    user.plan_started_at = now
    if record.plan_period == "yearly":
        user.plan_expires_at = now + timedelta(days=365)
    else:
        user.plan_expires_at = now + timedelta(days=30)

    await db.commit()
    logger.info(
        "PayPal payment confirmed: user=%s plan=%s period=%s amount=%d",
        user.email, record.plan, record.plan_period, record.amount,
    )

    return {
        "status": "paid",
        "message": "Payment confirmed. Plan activated.",
        "payment_id": record.id,
        "plan": record.plan,
        "plan_period": record.plan_period,
        "amount": record.amount,
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
    }


# ─── 7. 결제 준비 (레거시 호환) ─────────────────────

@router.post("/prepare")
async def prepare_payment_legacy(
    body: ReadyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """레거시 호환 -- /ready 와 동일한 동작."""
    return await payment_ready(body, user, db)
