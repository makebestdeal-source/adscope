"""Authentication router - login, register, me, refresh, sessions."""

import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import bcrypt
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import create_access_token, get_current_user, require_admin, JWT_EXPIRE_HOURS
from database import get_db
from database.models import User, UserSession, LoginHistory, PasswordResetToken

logger = logging.getLogger("adscope.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ── Request / Response schemas ──

class LoginRequest(BaseModel):
    email: str
    password: str
    device_fingerprint: str | None = None


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str | None = None
    role: str = "viewer"


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str
    company_name: str
    phone: str | None = None
    plan: str = "lite"  # "lite" or "full"
    plan_period: str = "monthly"  # "monthly" or "yearly"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: int
    email: str
    name: str | None
    role: str
    is_active: bool
    created_at: datetime | None
    plan: str | None = None
    company_name: str | None = None
    plan_period: str | None = None
    plan_expires_at: datetime | None = None


class SessionInfo(BaseModel):
    id: int
    user_id: int
    email: str | None
    ip_address: str | None
    user_agent: str | None
    device_fingerprint: str | None
    is_active: bool
    created_at: datetime | None
    revoked_at: datetime | None
    revoke_reason: str | None


# ── Endpoints ──

@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with email + password and return JWT.

    Non-admin: revokes all previous sessions (single device only).
    Admin: no session tracking.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    ua = request.headers.get("User-Agent", "")[:500]

    if user is None or not _verify_password(body.password, user.hashed_password):
        # Log failed attempt
        if user:
            db.add(LoginHistory(
                user_id=user.id, email=body.email, ip_address=ip,
                user_agent=ua, device_fingerprint=body.device_fingerprint,
                success=False, failure_reason="invalid_credentials",
            ))
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        db.add(LoginHistory(
            user_id=user.id, email=body.email, ip_address=ip,
            user_agent=ua, device_fingerprint=body.device_fingerprint,
            success=False, failure_reason="account_deactivated",
        ))
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    session_id = None

    # Non-admin: enforce single session
    if user.role != "admin":
        # Revoke all existing active sessions
        await db.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.is_active == True,
            )
            .values(
                is_active=False,
                revoked_at=datetime.now(timezone.utc),
                revoke_reason="new_login",
            )
        )

        # Create new session
        session_id = secrets.token_urlsafe(32)
        db.add(UserSession(
            user_id=user.id,
            session_token=session_id,
            device_fingerprint=body.device_fingerprint,
            ip_address=ip,
            user_agent=ua,
            is_active=True,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        ))

    # Log success
    db.add(LoginHistory(
        user_id=user.id, email=body.email, ip_address=ip,
        user_agent=ua, device_fingerprint=body.device_fingerprint,
        success=True,
    ))
    await db.commit()

    token = create_access_token(user.id, user.email, user.role, user.plan or "lite", session_id, paid=bool(getattr(user, "payment_confirmed", False)))
    return TokenResponse(
        access_token=token,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "plan": user.plan or ("admin" if user.role == "admin" else "lite"),
            "paid": bool(getattr(user, "payment_confirmed", False)) or user.role == "admin",
            "company_name": user.company_name,
            "plan_period": user.plan_period,
            "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
        },
    )


@router.post("/logout")
async def logout_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Explicitly logout - revoke current session."""
    if user.role == "admin":
        return {"status": "ok"}

    from jose import jwt as jose_jwt
    from api.deps import JWT_SECRET_KEY, JWT_ALGORITHM
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jose_jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            sid = payload.get("sid")
            if sid:
                await db.execute(
                    update(UserSession)
                    .where(UserSession.session_token == sid)
                    .values(
                        is_active=False,
                        revoked_at=datetime.now(timezone.utc),
                        revoke_reason="logout",
                    )
                )
                await db.commit()
        except Exception:
            pass

    return {"status": "ok"}


@router.post("/register", response_model=UserResponse)
async def register(
    body: RegisterRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Register a new user (admin only)."""
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    if body.role not in ("admin", "viewer"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'admin' or 'viewer'",
        )

    user = User(
        email=body.email,
        hashed_password=_hash_password(body.password),
        name=body.name,
        role=body.role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserResponse(
        id=user.id, email=user.email, name=user.name,
        role=user.role, is_active=user.is_active, created_at=user.created_at,
    )


# ── 기업회원 공개 가입 ──

PLAN_PRICES = {
    "lite": {"monthly": 49000, "yearly": 490000},
    "full": {"monthly": 99000, "yearly": 990000},
}


@router.get("/plans")
async def get_plans():
    """공개 요금제 정보."""
    return {
        "plans": [
            {
                "id": "lite",
                "name": "Lite",
                "description": "광고 정보 열람 (광고 소재/소셜 소재 미포함)",
                "monthly_price": 49000,
                "yearly_price": 490000,
                "vat_excluded": True,
                "features": [
                    "광고주 리포트",
                    "광고비 분석",
                    "산업별 현황",
                    "제품/서비스별 분석",
                    "경쟁사 비교",
                    "보고서 생성",
                ],
            },
            {
                "id": "full",
                "name": "Full",
                "description": "전체 기능 (광고 소재 + 소셜 소재 포함)",
                "monthly_price": 99000,
                "yearly_price": 990000,
                "vat_excluded": True,
                "features": [
                    "Lite 전체 기능 포함",
                    "광고 소재 갤러리",
                    "소셜 소재 갤러리",
                    "소셜 채널 분석",
                    "보고서 (소셜 포함)",
                ],
            },
        ],
    }


@router.post("/signup")
async def signup(
    body: SignupRequest,
    db: AsyncSession = Depends(get_db),
):
    """기업회원 공개 가입 (로그인 불필요)."""
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 이메일입니다",
        )

    # 비밀번호 정책 검증
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 최소 8자 이상이어야 합니다.")
    if not any(c.isalpha() for c in body.password) or not any(c.isdigit() for c in body.password):
        raise HTTPException(status_code=400, detail="비밀번호는 영문과 숫자를 모두 포함해야 합니다.")

    if body.plan not in ("lite", "full"):
        raise HTTPException(status_code=400, detail="플랜은 lite 또는 full만 가능합니다")
    if body.plan_period not in ("monthly", "yearly"):
        raise HTTPException(status_code=400, detail="결제 주기는 monthly 또는 yearly만 가능합니다")

    trial_days = int(os.getenv("FREE_TRIAL_DAYS", "7"))
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=trial_days)

    user = User(
        email=body.email,
        hashed_password=_hash_password(body.password),
        name=body.name,
        role="viewer",
        is_active=True,
        created_at=now,
        company_name=body.company_name,
        phone=body.phone,
        plan=body.plan,
        plan_period=body.plan_period,
        plan_started_at=now,
        plan_expires_at=expires,
        trial_started_at=now,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {
        "status": "ok",
        "message": f"{trial_days}일 무료체험이 시작되었습니다. 로그인 후 결제를 진행해주세요.",
        "user_id": user.id,
        "plan": user.plan,
        "plan_period": user.plan_period,
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
    }


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    """Return the currently authenticated user's info."""
    return UserResponse(
        id=user.id, email=user.email, name=user.name,
        role=user.role, is_active=user.is_active, created_at=user.created_at,
        plan=user.plan or ("admin" if user.role == "admin" else "lite"),
        company_name=user.company_name,
        plan_period=user.plan_period,
        plan_expires_at=user.plan_expires_at,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Issue a fresh JWT for the current user, preserving session binding."""
    # Extract existing session_id from current token to preserve session enforcement
    session_id = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from jose import jwt
            from api.deps import JWT_SECRET_KEY, JWT_ALGORITHM
            payload = jwt.decode(
                auth_header[7:], JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
            )
            session_id = payload.get("sid")
        except Exception:
            pass

    token = create_access_token(user.id, user.email, user.role, user.plan or "lite", session_id, paid=bool(getattr(user, "payment_confirmed", False)))
    return TokenResponse(
        access_token=token,
        user={
            "id": user.id, "email": user.email,
            "name": user.name, "role": user.role,
        },
    )


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin: list recent sessions across all users."""
    result = await db.execute(
        select(UserSession, User.email)
        .join(User, UserSession.user_id == User.id)
        .order_by(UserSession.created_at.desc())
        .limit(100)
    )
    rows = result.all()
    return [
        SessionInfo(
            id=s.id, user_id=s.user_id, email=email,
            ip_address=s.ip_address, user_agent=s.user_agent,
            device_fingerprint=s.device_fingerprint,
            is_active=s.is_active, created_at=s.created_at,
            revoked_at=s.revoked_at, revoke_reason=s.revoke_reason,
        )
        for s, email in rows
    ]


@router.post("/sessions/{session_id}/revoke")
async def revoke_session(
    session_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin: force-revoke a user's session."""
    await db.execute(
        update(UserSession)
        .where(UserSession.id == session_id)
        .values(
            is_active=False,
            revoked_at=datetime.now(timezone.utc),
            revoke_reason="admin_revoke",
        )
    )
    await db.commit()
    return {"status": "revoked", "session_id": session_id}


@router.get("/login-history")
async def get_login_history(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin: view recent login attempts."""
    result = await db.execute(
        select(LoginHistory)
        .order_by(LoginHistory.created_at.desc())
        .limit(200)
    )
    rows = result.scalars().all()
    return [
        {
            "id": h.id, "user_id": h.user_id, "email": h.email,
            "ip_address": h.ip_address, "device_fingerprint": h.device_fingerprint,
            "success": h.success, "failure_reason": h.failure_reason,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in rows
    ]


# ── Request schemas (password / profile) ──

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    company_name: str | None = None
    phone: str | None = None


def _validate_password_strength(password: str):
    """Validate password: 8+ chars, must contain letter and digit."""
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not re.search(r"[a-zA-Z]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one letter")
    if not re.search(r"[0-9]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one digit")


# ── Change Password ──

@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change password for the currently authenticated user."""
    if not _verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    _validate_password_strength(body.new_password)

    user.hashed_password = _hash_password(body.new_password)
    await db.commit()
    return {"status": "ok", "message": "Password changed successfully"}


# ── Forgot Password (token generation) ──

@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate a password reset token for the given email.

    The token is logged server-side only. In production, it would be sent via email.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None:
        # Do not reveal whether the email exists
        return {"status": "ok", "message": "If the email is registered, a reset token has been generated."}

    # Invalidate any existing unused tokens for this user
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used == False,
        )
        .values(used=True)
    )

    token_value = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(hours=1)

    reset_token = PasswordResetToken(
        user_id=user.id,
        token=token_value,
        expires_at=expires,
        used=False,
    )
    db.add(reset_token)
    await db.commit()

    # Log the token server-side only (never expose in response)
    logger.info("Password reset token for %s: %s", body.email, token_value)

    return {
        "status": "ok",
        "message": "If the email is registered, a reset token has been generated.",
        "note": "토큰이 이메일로 발송되었습니다 (개발환경: 서버 로그 확인)",
        "expires_in_minutes": 60,
    }


# ── Reset Password (with token) ──

@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset password using a valid reset token."""
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == body.token)
    )
    reset_token = result.scalar_one_or_none()

    if reset_token is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if reset_token.used:
        raise HTTPException(status_code=400, detail="This reset token has already been used")

    if reset_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset token has expired")

    _validate_password_strength(body.new_password)

    # Update password
    user_result = await db.execute(select(User).where(User.id == reset_token.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=400, detail="User not found")

    user.hashed_password = _hash_password(body.new_password)
    reset_token.used = True
    await db.commit()

    return {"status": "ok", "message": "Password has been reset successfully"}


# ── Profile endpoints ──

@router.get("/profile")
async def get_profile(
    user: User = Depends(get_current_user),
):
    """Return the current user profile information."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "company_name": user.company_name,
        "phone": user.phone,
        "plan": user.plan or ("admin" if user.role == "admin" else "lite"),
        "plan_period": user.plan_period,
        "plan_started_at": user.plan_started_at.isoformat() if user.plan_started_at else None,
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile (name, company_name, phone)."""
    updated_fields = []

    if body.name is not None:
        user.name = body.name
        updated_fields.append("name")

    if body.company_name is not None:
        user.company_name = body.company_name
        updated_fields.append("company_name")

    if body.phone is not None:
        user.phone = body.phone
        updated_fields.append("phone")

    if not updated_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    await db.commit()

    return {
        "status": "ok",
        "message": "Profile updated successfully",
        "updated_fields": updated_fields,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "company_name": user.company_name,
            "phone": user.phone,
        },
    }


# ── Login history for current user ──

@router.get("/my-login-history")
async def get_my_login_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return login history for the currently authenticated user."""
    result = await db.execute(
        select(LoginHistory)
        .where(LoginHistory.user_id == user.id)
        .order_by(LoginHistory.created_at.desc())
        .limit(50)
    )
    rows = result.scalars().all()
    return [
        {
            "id": h.id,
            "email": h.email,
            "ip_address": h.ip_address,
            "success": h.success,
            "failure_reason": h.failure_reason,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in rows
    ]


# ── OAuth Social Login ──

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
KAKAO_CLIENT_ID = os.getenv("KAKAO_CLIENT_ID", "")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
OAUTH_REDIRECT_BASE = os.getenv("OAUTH_REDIRECT_BASE", "https://adscope.kr")


async def _oauth_login_or_register(
    db: AsyncSession, request: Request,
    provider: str, oauth_id: str, email: str, name: str | None,
) -> dict:
    """Find or create user from OAuth, return JWT token."""
    result = await db.execute(
        select(User).where(User.oauth_provider == provider, User.oauth_id == oauth_id)
    )
    user = result.scalar_one_or_none()

    if user is None and email:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            user.oauth_provider = provider
            user.oauth_id = oauth_id

    if user is None:
        trial_days = int(os.getenv("FREE_TRIAL_DAYS", "7"))
        now = datetime.now(timezone.utc)
        user = User(
            email=email, hashed_password="", name=name or email.split("@")[0],
            role="viewer", is_active=True, created_at=now,
            oauth_provider=provider, oauth_id=oauth_id,
            plan="lite", plan_period="monthly",
            plan_started_at=now, plan_expires_at=now + timedelta(days=trial_days),
            trial_started_at=now,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"OAuth new user: {email} via {provider}")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    ua = request.headers.get("User-Agent", "")[:500]
    session_id = None
    if user.role != "admin":
        await db.execute(
            update(UserSession).where(
                UserSession.user_id == user.id, UserSession.is_active == True,
            ).values(is_active=False, revoked_at=datetime.now(timezone.utc), revoke_reason="oauth_login")
        )
        session_id = secrets.token_urlsafe(32)
        db.add(UserSession(
            user_id=user.id, session_token=session_id,
            device_fingerprint=None, ip_address=ip, user_agent=ua,
            is_active=True, expires_at=datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        ))
    db.add(LoginHistory(
        user_id=user.id, email=user.email, ip_address=ip,
        user_agent=ua, device_fingerprint=None, success=True,
    ))
    await db.commit()
    token = create_access_token(user.id, user.email, user.role, user.plan or "lite", session_id, paid=bool(getattr(user, "payment_confirmed", False)))
    return {"access_token": token, "user": {
        "id": user.id, "email": user.email, "name": user.name,
        "role": user.role, "plan": user.plan or "lite",
        "company_name": user.company_name, "plan_period": user.plan_period,
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
    }}


@router.get("/oauth/google")
async def google_oauth_redirect():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{OAUTH_REDIRECT_BASE}/api/auth/oauth/google/callback",
        "response_type": "code", "scope": "openid email profile",
        "access_type": "offline", "prompt": "select_account",
    }
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@router.get("/oauth/google/callback")
async def google_oauth_callback(code: str, request: Request, db: AsyncSession = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        tok = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": f"{OAUTH_REDIRECT_BASE}/api/auth/oauth/google/callback",
            "grant_type": "authorization_code",
        })
        if tok.status_code != 200:
            raise HTTPException(status_code=400, detail="Google token exchange failed")
        ui = await client.get("https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
        if ui.status_code != 200:
            raise HTTPException(status_code=400, detail="Google userinfo failed")
        info = ui.json()
    r = await _oauth_login_or_register(db, request, "google", str(info["id"]), info.get("email", ""), info.get("name"))
    return RedirectResponse(f"{OAUTH_REDIRECT_BASE}/login?oauth_token={r['access_token']}")


@router.get("/oauth/kakao")
async def kakao_oauth_redirect():
    if not KAKAO_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Kakao OAuth not configured")
    params = {"client_id": KAKAO_CLIENT_ID,
        "redirect_uri": f"{OAUTH_REDIRECT_BASE}/api/auth/oauth/kakao/callback", "response_type": "code"}
    return RedirectResponse(f"https://kauth.kakao.com/oauth/authorize?{urlencode(params)}")


@router.get("/oauth/kakao/callback")
async def kakao_oauth_callback(code: str, request: Request, db: AsyncSession = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        token_data = {
            "grant_type": "authorization_code", "client_id": KAKAO_CLIENT_ID,
            "redirect_uri": f"{OAUTH_REDIRECT_BASE}/api/auth/oauth/kakao/callback", "code": code,
        }
        if KAKAO_CLIENT_SECRET:
            token_data["client_secret"] = KAKAO_CLIENT_SECRET
        tok = await client.post("https://kauth.kakao.com/oauth/token", data=token_data)
        if tok.status_code != 200:
            raise HTTPException(status_code=400, detail="Kakao token exchange failed")
        ui = await client.get("https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
        if ui.status_code != 200:
            raise HTTPException(status_code=400, detail="Kakao userinfo failed")
        info = ui.json()
    acct = info.get("kakao_account", {})
    email = acct.get("email", f"kakao_{info['id']}@kakao.user")
    name = acct.get("profile", {}).get("nickname")
    r = await _oauth_login_or_register(db, request, "kakao", str(info["id"]), email, name)
    return RedirectResponse(f"{OAUTH_REDIRECT_BASE}/login?oauth_token={r['access_token']}")


@router.get("/oauth/naver")
async def naver_oauth_redirect():
    if not NAVER_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Naver OAuth not configured")
    state = secrets.token_urlsafe(16)
    params = {"client_id": NAVER_CLIENT_ID,
        "redirect_uri": f"{OAUTH_REDIRECT_BASE}/api/auth/oauth/naver/callback",
        "response_type": "code", "state": state}
    return RedirectResponse(f"https://nid.naver.com/oauth2.0/authorize?{urlencode(params)}")


@router.get("/oauth/naver/callback")
async def naver_oauth_callback(code: str, state: str, request: Request, db: AsyncSession = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        tok = await client.post("https://nid.naver.com/oauth2.0/token", data={
            "grant_type": "authorization_code", "client_id": NAVER_CLIENT_ID,
            "client_secret": NAVER_CLIENT_SECRET, "code": code, "state": state,
        })
        if tok.status_code != 200:
            raise HTTPException(status_code=400, detail="Naver token exchange failed")
        ui = await client.get("https://openapi.naver.com/v1/nid/me",
            headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
        if ui.status_code != 200:
            raise HTTPException(status_code=400, detail="Naver userinfo failed")
        info = ui.json().get("response", {})
    email = info.get("email", f"naver_{info.get('id', 'unknown')}@naver.user")
    name = info.get("name") or info.get("nickname")
    r = await _oauth_login_or_register(db, request, "naver", str(info.get("id", "")), email, name)
    return RedirectResponse(f"{OAUTH_REDIRECT_BASE}/login?oauth_token={r['access_token']}")
