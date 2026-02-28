"""PC / 모바일 디바이스 설정."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceConfig:
    name: str
    device_type: str  # "pc" | "mobile"
    viewport_width: int
    viewport_height: int
    user_agent: str
    is_mobile: bool
    has_touch: bool
    device_scale_factor: float


PC_DEVICE = DeviceConfig(
    name="Desktop Chrome",
    device_type="pc",
    viewport_width=1920,
    viewport_height=1080,
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    is_mobile=False,
    has_touch=False,
    device_scale_factor=1.0,
)

MOBILE_IPHONE = DeviceConfig(
    name="iPhone 15 Pro",
    device_type="mobile",
    viewport_width=393,
    viewport_height=852,
    user_agent=(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    is_mobile=True,
    has_touch=True,
    device_scale_factor=3.0,
)

MOBILE_GALAXY = DeviceConfig(
    name="Galaxy S24",
    device_type="mobile",
    viewport_width=360,
    viewport_height=780,
    user_agent=(
        "Mozilla/5.0 (Linux; Android 14; SM-S926B) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Mobile Safari/537.36"
    ),
    is_mobile=True,
    has_touch=True,
    device_scale_factor=3.0,
)

# 디바이스 매핑
DEVICES: dict[str, DeviceConfig] = {
    "pc": PC_DEVICE,
    "mobile": MOBILE_GALAXY,  # "mobile" shorthand → 갤럭시 기본
    "mobile_iphone": MOBILE_IPHONE,
    "mobile_galaxy": MOBILE_GALAXY,
}

# 기본 모바일 디바이스 (갤럭시 — 한국 시장 점유율 기준)
DEFAULT_MOBILE = MOBILE_GALAXY

# ── Phase 3B: 연령대별 대표 디바이스 매핑 ──
AGE_DEVICE_MAP: dict[str, DeviceConfig] = {
    "10대": MOBILE_IPHONE,   # 아이폰 비중 52~58%
    "20대": MOBILE_IPHONE,   # 아이폰 비중 55~60%
    "30대": MOBILE_GALAXY,   # 갤럭시 비중 60~65%
    "40대": MOBILE_GALAXY,   # 갤럭시 비중 72~75%
    "50대": PC_DEVICE,       # PC 비중 50%, 모바일은 갤럭시
    "60대": PC_DEVICE,       # PC 비중 60%
}


def get_device_for_persona(persona) -> DeviceConfig:
    """페르소나의 primary_device 또는 연령대 기반 디바이스 반환.

    Args:
        persona: PersonaProfile 인스턴스

    Returns:
        적절한 DeviceConfig
    """
    # 1순위: primary_device 필드
    if hasattr(persona, "primary_device") and persona.primary_device:
        device = DEVICES.get(persona.primary_device)
        if device:
            return device

    # 2순위: 연령대 기반 매핑
    if hasattr(persona, "age_group") and persona.age_group:
        device = AGE_DEVICE_MAP.get(persona.age_group)
        if device:
            return device

    return DEFAULT_MOBILE
