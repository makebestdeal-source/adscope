"""Mobile Panel API -- AI 가상 디바이스 + 실제 디바이스 광고 노출 수집."""

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from database import get_db
from database.models import (
    Advertiser,
    MobilePanelDevice,
    MobilePanelExposure,
    PanelObservation,
    Persona,
    User,
)
from database.schemas import (
    MobileDeviceOut,
    MobileDeviceRegisterIn,
    MobileExposureBatchIn,
    MobileExposureIn,
    MobileExposureOut,
    MobilePanelStatsOut,
)

router = APIRouter(prefix="/api/mobile-panel", tags=["mobile-panel"])

# 앱→채널 매핑
_APP_TO_CHANNEL = {
    "youtube": "youtube_surf",
    "instagram": "instagram",
    "facebook": "facebook",
    "tiktok": "tiktok_ads",
    "naver": "naver_da",
    "kakao": "kakao_da",
    "chrome": "google_gdn",
    "samsung internet": "google_gdn",
}


def _resolve_channel(app_name: str) -> str | None:
    """앱 이름을 채널명으로 매핑."""
    lower = (app_name or "").lower().strip()
    for key, channel in _APP_TO_CHANNEL.items():
        if key in lower:
            return channel
    return None


def _generate_device_id(data: MobileDeviceRegisterIn) -> str:
    """디바이스 핑거프린트 생성 (SHA-256)."""
    raw = f"{data.device_type}:{data.os_type}:{data.device_model}:{data.carrier}:{data.age_group}:{data.gender}:{data.persona_code or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


@router.post("/devices/register", response_model=MobileDeviceOut)
async def register_device(
    data: MobileDeviceRegisterIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """디바이스 등록 (AI 가상 또는 실제)."""
    device_id = _generate_device_id(data)

    # 기존 디바이스 확인
    existing = (
        await db.execute(
            select(MobilePanelDevice).where(MobilePanelDevice.device_id == device_id)
        )
    ).scalar_one_or_none()

    if existing:
        existing.is_active = True
        existing.last_seen = datetime.utcnow()
        await db.commit()
        await db.refresh(existing)
        return MobileDeviceOut(
            id=existing.id,
            device_id=existing.device_id,
            device_type=existing.device_type,
            os_type=existing.os_type,
            os_version=existing.os_version,
            device_model=existing.device_model,
            carrier=existing.carrier,
            age_group=existing.age_group,
            gender=existing.gender,
            region=existing.region,
            is_active=existing.is_active,
            last_seen=existing.last_seen,
            created_at=existing.created_at,
        )

    # 페르소나 연결
    persona_id = None
    if data.persona_code:
        persona = (
            await db.execute(
                select(Persona).where(Persona.code == data.persona_code)
            )
        ).scalar_one_or_none()
        if persona:
            persona_id = persona.id

    device = MobilePanelDevice(
        device_id=device_id,
        device_type=data.device_type,
        persona_id=persona_id,
        os_type=data.os_type,
        os_version=data.os_version,
        device_model=data.device_model,
        carrier=data.carrier,
        screen_res=data.screen_res,
        app_list=data.app_list,
        age_group=data.age_group,
        gender=data.gender,
        region=data.region,
        is_active=True,
        last_seen=datetime.utcnow(),
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)

    return MobileDeviceOut(
        id=device.id,
        device_id=device.device_id,
        device_type=device.device_type,
        os_type=device.os_type,
        os_version=device.os_version,
        device_model=device.device_model,
        carrier=device.carrier,
        age_group=device.age_group,
        gender=device.gender,
        region=device.region,
        is_active=device.is_active,
        last_seen=device.last_seen,
        created_at=device.created_at,
    )


@router.post("/exposures/report")
async def report_exposure(
    data: MobileExposureIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """단건 광고 노출 보고."""
    device = (
        await db.execute(
            select(MobilePanelDevice).where(MobilePanelDevice.device_id == data.device_id)
        )
    ).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not registered")

    # 광고주 매칭
    advertiser_id = None
    if data.advertiser_name:
        adv = (
            await db.execute(
                select(Advertiser).where(Advertiser.name == data.advertiser_name).limit(1)
            )
        ).scalar_one_or_none()
        if adv:
            advertiser_id = adv.id

    channel = _resolve_channel(data.app_name)

    exposure = MobilePanelExposure(
        device_id=data.device_id,
        app_name=data.app_name,
        channel=channel,
        advertiser_id=advertiser_id,
        advertiser_name_raw=data.advertiser_name,
        ad_text=data.ad_text,
        ad_type=data.ad_type,
        creative_url=data.creative_url,
        click_url=data.click_url,
        duration_ms=data.duration_ms,
        was_clicked=data.was_clicked,
        was_skipped=data.was_skipped,
        screen_position=data.screen_position,
        observed_at=data.observed_at or datetime.utcnow(),
        extra_data=data.extra_data,
    )
    db.add(exposure)

    # PanelObservation에도 기록 (메타시그널 연동)
    panel_obs = PanelObservation(
        panel_type=device.device_type,
        panel_id=data.device_id,
        advertiser_id=advertiser_id,
        channel=channel or data.app_name,
        device=f"{device.os_type}_{device.device_model or 'unknown'}",
        location=device.region,
        is_verified=device.device_type == "real",
        extra_data={"source": "mobile_panel", "app": data.app_name},
    )
    db.add(panel_obs)

    # 디바이스 last_seen 갱신
    device.last_seen = datetime.utcnow()
    await db.commit()

    return {"status": "ok", "exposure_id": exposure.id}


@router.post("/exposures/batch")
async def report_exposure_batch(
    data: MobileExposureBatchIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """배치 광고 노출 보고 (모바일 SDK용)."""
    device = (
        await db.execute(
            select(MobilePanelDevice).where(MobilePanelDevice.device_id == data.device_id)
        )
    ).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not registered")

    saved = 0
    for exp in data.exposures:
        advertiser_id = None
        if exp.advertiser_name:
            adv = (
                await db.execute(
                    select(Advertiser).where(Advertiser.name == exp.advertiser_name).limit(1)
                )
            ).scalar_one_or_none()
            if adv:
                advertiser_id = adv.id

        channel = _resolve_channel(exp.app_name)

        exposure = MobilePanelExposure(
            device_id=data.device_id,
            app_name=exp.app_name,
            channel=channel,
            advertiser_id=advertiser_id,
            advertiser_name_raw=exp.advertiser_name,
            ad_text=exp.ad_text,
            ad_type=exp.ad_type,
            creative_url=exp.creative_url,
            click_url=exp.click_url,
            duration_ms=exp.duration_ms,
            was_clicked=exp.was_clicked,
            was_skipped=exp.was_skipped,
            screen_position=exp.screen_position,
            observed_at=exp.observed_at or datetime.utcnow(),
            extra_data=exp.extra_data,
        )
        db.add(exposure)

        # PanelObservation 연동
        panel_obs = PanelObservation(
            panel_type=device.device_type,
            panel_id=data.device_id,
            advertiser_id=advertiser_id,
            channel=channel or exp.app_name,
            device=f"{device.os_type}_{device.device_model or 'unknown'}",
            location=device.region,
            is_verified=device.device_type == "real",
            extra_data={"source": "mobile_panel_batch", "app": exp.app_name},
        )
        db.add(panel_obs)
        saved += 1

    device.last_seen = datetime.utcnow()
    await db.commit()

    return {"status": "ok", "saved": saved, "total": len(data.exposures)}


@router.get("/devices", response_model=list[MobileDeviceOut])
async def list_devices(
    device_type: str | None = None,
    active_only: bool = True,
    limit: int = Query(100, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """등록된 디바이스 목록."""
    q = select(MobilePanelDevice)
    if device_type:
        q = q.where(MobilePanelDevice.device_type == device_type)
    if active_only:
        q = q.where(MobilePanelDevice.is_active == True)
    q = q.order_by(MobilePanelDevice.last_seen.desc()).limit(limit)

    rows = (await db.execute(q)).scalars().all()

    result = []
    for d in rows:
        exp_count = (
            await db.execute(
                select(func.count(MobilePanelExposure.id)).where(
                    MobilePanelExposure.device_id == d.device_id
                )
            )
        ).scalar_one() or 0

        result.append(MobileDeviceOut(
            id=d.id,
            device_id=d.device_id,
            device_type=d.device_type,
            os_type=d.os_type,
            os_version=d.os_version,
            device_model=d.device_model,
            carrier=d.carrier,
            age_group=d.age_group,
            gender=d.gender,
            region=d.region,
            is_active=d.is_active,
            last_seen=d.last_seen,
            created_at=d.created_at,
            exposure_count=exp_count,
        ))
    return result


@router.get("/stats", response_model=MobilePanelStatsOut)
async def get_panel_stats(
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """패널 전체 통계."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    total = (await db.execute(select(func.count(MobilePanelDevice.id)))).scalar_one() or 0
    ai_count = (await db.execute(
        select(func.count(MobilePanelDevice.id)).where(MobilePanelDevice.device_type == "ai")
    )).scalar_one() or 0
    real_count = (await db.execute(
        select(func.count(MobilePanelDevice.id)).where(MobilePanelDevice.device_type == "real")
    )).scalar_one() or 0
    active_count = (await db.execute(
        select(func.count(MobilePanelDevice.id)).where(
            and_(MobilePanelDevice.is_active == True, MobilePanelDevice.last_seen >= cutoff)
        )
    )).scalar_one() or 0

    total_exp = (await db.execute(
        select(func.count(MobilePanelExposure.id)).where(MobilePanelExposure.observed_at >= cutoff)
    )).scalar_one() or 0
    today_exp = (await db.execute(
        select(func.count(MobilePanelExposure.id)).where(MobilePanelExposure.observed_at >= today_start)
    )).scalar_one() or 0

    # Top apps
    app_rows = (await db.execute(
        select(MobilePanelExposure.app_name, func.count(MobilePanelExposure.id).label("cnt"))
        .where(MobilePanelExposure.observed_at >= cutoff)
        .group_by(MobilePanelExposure.app_name)
        .order_by(func.count(MobilePanelExposure.id).desc())
        .limit(10)
    )).fetchall()
    top_apps = [{"app": r[0], "count": r[1]} for r in app_rows]

    # Top advertisers
    adv_rows = (await db.execute(
        select(MobilePanelExposure.advertiser_name_raw, func.count(MobilePanelExposure.id).label("cnt"))
        .where(and_(
            MobilePanelExposure.observed_at >= cutoff,
            MobilePanelExposure.advertiser_name_raw.isnot(None),
        ))
        .group_by(MobilePanelExposure.advertiser_name_raw)
        .order_by(func.count(MobilePanelExposure.id).desc())
        .limit(10)
    )).fetchall()
    top_advertisers = [{"advertiser": r[0], "count": r[1]} for r in adv_rows]

    return MobilePanelStatsOut(
        total_devices=total,
        ai_devices=ai_count,
        real_devices=real_count,
        active_devices=active_count,
        total_exposures=total_exp,
        exposures_today=today_exp,
        top_apps=top_apps,
        top_advertisers=top_advertisers,
    )


@router.get("/exposures", response_model=list[MobileExposureOut])
async def list_exposures(
    device_id: str | None = None,
    channel: str | None = None,
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(100, le=1000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """노출 이벤트 조회."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    q = select(MobilePanelExposure).where(MobilePanelExposure.observed_at >= cutoff)
    if device_id:
        q = q.where(MobilePanelExposure.device_id == device_id)
    if channel:
        q = q.where(MobilePanelExposure.channel == channel)
    q = q.order_by(MobilePanelExposure.observed_at.desc()).limit(limit)

    rows = (await db.execute(q)).scalars().all()
    return rows
