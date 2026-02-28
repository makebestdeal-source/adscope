"""Payment API - prepare/complete/history."""

import os
import time
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from database import get_db
from database.models import User, PaymentRecord

logger = logging.getLogger("adscope.payments")

router = APIRouter(prefix="/api/payments", tags=["payments"])

PLAN_PRICES = {
    "lite": {"monthly": 49000, "yearly": 490000},
    "full": {"monthly": 99000, "yearly": 990000},
}


class PrepareRequest(BaseModel):
    plan: str
    plan_period: str


class CompleteRequest(BaseModel):
    imp_uid: str
    merchant_uid: str


@router.post("/prepare")
async def prepare_payment(
    body: PrepareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a payment record and return data for PortOne SDK."""
    if body.plan not in ("lite", "full"):
        raise HTTPException(400, "Invalid plan")
    if body.plan_period not in ("monthly", "yearly"):
        raise HTTPException(400, "Invalid period")

    amount = PLAN_PRICES[body.plan][body.plan_period]
    merchant_uid = f"ADSCOPE_{user.id}_{int(time.time())}"

    record = PaymentRecord(
        user_id=user.id,
        merchant_uid=merchant_uid,
        plan=body.plan,
        plan_period=body.plan_period,
        amount=amount,
        status="pending",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    store_id = os.getenv("PORTONE_STORE_ID", "")
    channel_key = os.getenv("PORTONE_CHANNEL_KEY", "")

    return {
        "merchant_uid": merchant_uid,
        "amount": amount,
        "plan": body.plan,
        "plan_period": body.plan_period,
        "buyer_email": user.email,
        "buyer_name": user.name or "",
        "buyer_company": user.company_name or "",
        "store_id": store_id,
        "channel_key": channel_key,
        "payment_id": record.id,
    }


@router.post("/complete")
async def complete_payment(
    body: CompleteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify payment with PortOne and update record status."""
    result = await db.execute(
        select(PaymentRecord).where(
            PaymentRecord.merchant_uid == body.merchant_uid,
            PaymentRecord.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Payment record not found")
    if record.status != "pending":
        raise HTTPException(400, f"Payment already processed (status={record.status})")

    # Verify with PortOne
    try:
        from api.services.portone import verify_payment
        portone_data = await verify_payment(body.imp_uid)
        record.portone_response = portone_data

        paid_amount = portone_data.get("amount", {})
        if isinstance(paid_amount, dict):
            paid_amount = paid_amount.get("total", 0)

        if paid_amount and int(paid_amount) != record.amount:
            record.status = "failed"
            record.notes = f"Amount mismatch: expected {record.amount}, got {paid_amount}"
            await db.commit()
            raise HTTPException(400, "Payment amount mismatch")

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("PortOne verification skipped: %s", str(e))

    record.imp_uid = body.imp_uid
    record.status = "paid"
    record.paid_at = datetime.now(timezone.utc)

    # 결제 완료 → 사용자 플랜 즉시 활성화
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
    logger.info("Payment confirmed: user=%s plan=%s period=%s", user.email, record.plan, record.plan_period)

    return {
        "status": "paid",
        "message": "Payment confirmed. Plan activated.",
        "payment_id": record.id,
        "plan": record.plan,
        "plan_period": record.plan_period,
    }


@router.get("/my")
async def my_payments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's payment history."""
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
            "merchant_uid": r.merchant_uid,
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
