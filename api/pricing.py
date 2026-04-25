"""Central pricing and plan policy for AdScope."""

from __future__ import annotations

from copy import deepcopy


BILLING_PERIODS = ("monthly", "yearly")
BILLABLE_PLAN_IDS = ("lite", "full")

PLAN_CATALOG = {
    "lite": {
        "id": "lite",
        "name": "Lite",
        "description": "소규모 마케터와 단일 광고주 모니터링용",
        "monthly_price": 49000,
        "yearly_price": 490000,
        "vat_excluded": True,
        "checkout_enabled": True,
        "usage_limits": {
            "users": 1,
            "tracked_advertisers": 30,
            "monthly_report_exports": 20,
            "monthly_creative_downloads": 100,
            "monthly_api_calls": 0,
            "history_months": 12,
        },
        "features": [
            "국내 주요 디지털 광고 소재 열람",
            "광고주별 캠페인/소재/랜딩 모니터링",
            "광고비 추정 및 업종/경쟁사 비교",
            "키워드/시장 분석",
            "PDF/CSV 리포트 생성",
        ],
    },
    "full": {
        "id": "full",
        "name": "Full",
        "description": "대행사와 미디어렙의 다중 광고주 분석용",
        "monthly_price": 99000,
        "yearly_price": 990000,
        "vat_excluded": True,
        "checkout_enabled": True,
        "usage_limits": {
            "users": 3,
            "tracked_advertisers": 150,
            "monthly_report_exports": 100,
            "monthly_creative_downloads": 1000,
            "monthly_api_calls": 0,
            "history_months": 24,
        },
        "features": [
            "Lite 전체 기능",
            "소셜 소재 갤러리 및 소셜 인사이트",
            "브랜드 채널/버즈/캠페인 효과 분석",
            "다중 광고주 비교 리포트",
            "우선 데이터 보강 요청",
        ],
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise",
        "description": "대행사/미디어렙/브랜드 본사용 맞춤 계약",
        "monthly_price": None,
        "yearly_price": None,
        "vat_excluded": True,
        "checkout_enabled": False,
        "payment_flow": "견적서 발행 후 세금계산서/계좌이체",
        "usage_limits": {
            "users": "custom",
            "tracked_advertisers": "custom",
            "monthly_report_exports": "custom",
            "monthly_creative_downloads": "custom",
            "monthly_api_calls": "custom",
            "history_months": "custom",
        },
        "features": [
            "맞춤 광고주/업종 커버리지 보강",
            "전용 API/대량 Export",
            "팀 계정 및 권한 관리",
            "세금계산서/계약서/월 정산",
            "전담 온보딩 및 SLA 협의",
        ],
    },
}

PLAN_PRICES = {
    plan_id: {
        "monthly": plan["monthly_price"],
        "yearly": plan["yearly_price"],
    }
    for plan_id, plan in PLAN_CATALOG.items()
    if plan_id in BILLABLE_PLAN_IDS
}

# PayPal USD prices (PayPal does not support KRW).
PLAN_PRICES_USD = {
    "lite": {"monthly": 35, "yearly": 350},
    "full": {"monthly": 70, "yearly": 700},
}


def public_plan_catalog() -> list[dict]:
    """Return a JSON-safe copy of the public plan catalog."""
    return [deepcopy(PLAN_CATALOG[plan_id]) for plan_id in ("lite", "full", "enterprise")]


def validate_billable_plan(plan: str, period: str) -> None:
    if plan not in BILLABLE_PLAN_IDS:
        raise ValueError("Only lite and full can be purchased online")
    if period not in BILLING_PERIODS:
        raise ValueError("Invalid billing period")
