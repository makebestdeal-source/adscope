"""Display helpers for advertiser names parsed from ad platforms."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse


NON_ADVERTISER_NAMES = frozenset(
    {
        "ader",
        "blog",
        "map",
        "keywordad",
        "textad",
        "powerlink",
        "shopping",
        "banner",
        "text",
        "video",
        "display_banner",
        "gdn_display",
        "google_search_text",
        "kakao_banner",
        "kakao_native",
        "naver_shopping_ad",
        "social_library",
        "tiktok_creative_center",
        "youtube_transparency",
        "phone_da",
        "naver",
        "daum",
        "kakao",
    }
)

JUNK_EXTRACTED_NAMES = frozenset(
    {
        "be",
        "bold",
        "con",
        "cooling",
        "for",
        "get",
        "in",
        "library",
        "launch",
        "queries",
        "see",
        "source",
        "unlock",
        "라이브러리",
    }
)

PLACEHOLDER_NAME_RE = re.compile(
    r"(?:라이브러리\s*ID|library\s*id|라이브러리|library)\s*:?\s*\d+|^\d{8,}$",
    re.IGNORECASE,
)

CAMPAIGN_SUFFIX_RE = re.compile(
    r"\s*(?:\d{4}[.-]\d{1,2}|[1-9]\d?\s*\uc6d4)\s*\ucea0\ud398\uc778\s*$",
    re.IGNORECASE,
)
GREEK_TEXT_RE = re.compile(r"[\u0370-\u03ff]")
AD_COPY_TEXT_RE = re.compile(
    r"(\d+\s*%|-\d+\s*%|discount|sale|offer|coupon|event|"
    r"\ud560\uc778|\ud2b9\uac00|\ubb34\ub8cc|\ucfe0\ud3f0|\uc774\ubca4\ud2b8|"
    r"\u03bc\u03b7\u03bd\s+\u03c7\u03ac\u03c3\u03b5\u03c4\u03b5|"
    r"\u03c0\u03c1\u03bf\u03c3\u03c6\u03bf\u03c1|\u03ad\u03ba\u03c0\u03c4\u03c9\u03c3)",
    re.IGNORECASE,
)
COMMON_KOREAN_SURNAMES = frozenset(
    "김이박최정강조윤장임한오서신권황안송전홍유고문양손배백허남심노하곽성차주우구민류진지엄채원천방공현함변염여추도소석선설모명마"
)
KNOWN_BRAND_NAMES = frozenset(
    {
        "마켓비",
        "메디큐브",
        "리리브",
        "리쏘",
        "올리브영",
    }
)
DOMAIN_SUBJECTS = {
    "oliveyoung.co.kr": "올리브영 상품",
    "themedicube.co.kr": "메디큐브",
    "medicube.co.kr": "메디큐브",
    "reliv.co.kr": "리리브",
}
DOMAIN_TOKEN_SUBJECTS = {
    "marketb": "마켓비",
    "medicube": "메디큐브",
    "oliveyoung": "올리브영 상품",
    "reliv": "리리브",
}
SERVICE_PATTERNS = (
    (re.compile(r"분양|초역세권|아파트|오피스텔|모델하우스|롯데캐슬|부동산|상가|입주", re.IGNORECASE), "부동산 분양"),
    (re.compile(r"올리브영|olive\s*young|oliveyoung", re.IGNORECASE), "올리브영 상품"),
    (re.compile(r"메디큐브|medicube|themedicube", re.IGNORECASE), "메디큐브"),
    (re.compile(r"\breliv\b|리리브", re.IGNORECASE), "리리브"),
    (re.compile(r"신용|저금리|대출|보험|카드|금융|지원금", re.IGNORECASE), "금융 서비스"),
    (re.compile(r"기침|가래|관절|영양제|건강|다이어트|마사지|손목터널|건초염", re.IGNORECASE), "건강/생활 상품"),
    (re.compile(r"화장품|뷰티|피부|앰플|크림|마스크팩|세럼|선크림|클렌징", re.IGNORECASE), "뷰티/화장품"),
    (re.compile(r"주름|탄력|리프팅|미백|모공|두피|탈모", re.IGNORECASE), "뷰티/화장품"),
    (re.compile(r"동물병원|동물메디컬|펫|외과수술|고난도\s*수술", re.IGNORECASE), "동물병원/의료 서비스"),
    (re.compile(r"치과|병원|의원|클리닉|시술|성형|피부과", re.IGNORECASE), "병원/의료 서비스"),
    (re.compile(r"학원|강의|교육|수강|입시|영어|수학", re.IGNORECASE), "교육 서비스"),
    (re.compile(r"공식스토어|스마트스토어|쇼핑몰|브랜드스토어", re.IGNORECASE), "온라인 스토어"),
)


def _campaign_base_name(value: object | None) -> str:
    return CAMPAIGN_SUFFIX_RE.sub("", normalize_advertiser_name(value)).strip()


def is_noisy_campaign_name(
    campaign_name: object | None,
    advertiser_name: object | None = None,
) -> bool:
    name = normalize_advertiser_name(campaign_name)
    if not name:
        return True

    base = _campaign_base_name(name)
    if is_placeholder_advertiser_name(base):
        return True
    if is_person_or_handle_advertiser_name(base):
        return True
    if is_low_confidence_campaign_source_name(base):
        return True
    if advertiser_name and is_placeholder_advertiser_name(advertiser_name):
        return True
    if advertiser_name and is_person_or_handle_advertiser_name(advertiser_name):
        return True
    if advertiser_name and is_low_confidence_campaign_source_name(advertiser_name):
        return True
    if GREEK_TEXT_RE.search(base) and len(base) >= 12:
        return True
    if len(base) >= 40 and (AD_COPY_TEXT_RE.search(base) or "!" in base or "?" in base):
        return True
    if len(base) >= 70 and len(base.split()) >= 4:
        return True
    return False


def normalize_advertiser_name(value: object | None) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -_/.|")


def is_korean_person_name(value: object | None) -> bool:
    name = normalize_advertiser_name(value)
    if not re.fullmatch(r"[가-힣]{2,4}", name):
        return False
    return name[0] in COMMON_KOREAN_SURNAMES


def is_handle_like_name(value: object | None) -> bool:
    name = normalize_advertiser_name(value)
    if not name:
        return False
    if re.search(r"[_@]", name):
        return True
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,30}", name)) and any(ch.isdigit() or ch in "._-" for ch in name)


def is_person_or_handle_advertiser_name(value: object | None) -> bool:
    name = normalize_advertiser_name(value)
    if name in KNOWN_BRAND_NAMES:
        return False
    return is_korean_person_name(name) or is_handle_like_name(name)


def is_low_confidence_campaign_source_name(value: object | None) -> bool:
    name = normalize_advertiser_name(value)
    if not name or name in KNOWN_BRAND_NAMES:
        return False
    if is_person_or_handle_advertiser_name(name) or is_placeholder_advertiser_name(name):
        return True
    if re.fullmatch(r"[가-힣]{2,4}", name):
        return True
    if re.search(r"\d", name):
        return True
    if AD_COPY_TEXT_RE.search(name):
        return True
    if len(name) >= 7 and re.search(r"\s", name) and re.search(r"[가-힣]", name):
        return True
    if len(name) >= 12 and re.search(r"[\s\[\]|!?.,]", name):
        return True
    # 영어 단독 단어(브랜드명)는 low confidence 아님 — 공백 포함 다단어 구문만 해당
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,30}", name) and " " in name)


def _loads_extra(extra_data: object | None) -> dict:
    if isinstance(extra_data, dict):
        return extra_data
    if isinstance(extra_data, str) and extra_data.strip():
        try:
            parsed = json.loads(extra_data)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _decoded_host(url: object | None) -> str:
    raw = normalize_advertiser_name(url)
    if not raw:
        return ""
    try:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        host = (parsed.hostname or "").lower()
    except Exception:
        host = raw.lower()
    if not host:
        return ""
    try:
        return host.encode("ascii").decode("idna").lower()
    except Exception:
        return host


def _subject_from_text(value: object | None, *, allow_plain: bool = False) -> str | None:
    text = normalize_advertiser_name(value)
    if not text:
        return None
    if re.fullmatch(r"\d{1,2}:\d{2}(?:\s*/\s*\d{1,2}:\d{2})?", text):
        return None
    if re.fullmatch(r"[\d\s:./,-]+", text):
        return None
    for pattern, label in SERVICE_PATTERNS:
        if pattern.search(text):
            return label
    if allow_plain and len(text) <= 32 and not AD_COPY_TEXT_RE.search(text) and not is_person_or_handle_advertiser_name(text) and not is_placeholder_advertiser_name(text):
        return text
    return None


def _subject_from_url(value: object | None) -> str | None:
    host = _decoded_host(value)
    if not host:
        return None
    for domain, label in DOMAIN_SUBJECTS.items():
        if host == domain or host.endswith(f".{domain}"):
            return label
    for token, label in DOMAIN_TOKEN_SUBJECTS.items():
        if token in host:
            return label
    return _subject_from_text(host)


def infer_advertised_subject(
    *values: object | None,
    website: object | None = None,
    url: object | None = None,
    extra_data: object | None = None,
) -> str | None:
    extra = _loads_extra(extra_data)
    structured_values = [
        values[0] if len(values) > 0 else None,
        values[1] if len(values) > 1 else None,
        values[4] if len(values) > 4 else None,
    ]
    landing = extra.get("landing_analysis", {})
    landing_values = [
        landing.get("brand_name") if isinstance(landing, dict) else None,
        landing.get("business_name") if isinstance(landing, dict) else None,
        landing.get("page_title") if isinstance(landing, dict) else None,
    ]
    for value in values:
        subject = _subject_from_text(value)
        if subject:
            return subject
    for value in [*structured_values, *landing_values]:
        subject = _subject_from_text(value, allow_plain=True)
        if subject:
            return subject
    for value in (url, website):
        subject = _subject_from_url(value)
        if subject:
            return subject
    return None


def is_placeholder_advertiser_name(value: object | None) -> bool:
    name = normalize_advertiser_name(value)
    if not name:
        return True

    lower = name.lower()
    if lower in NON_ADVERTISER_NAMES or lower in JUNK_EXTRACTED_NAMES:
        return True
    if PLACEHOLDER_NAME_RE.search(name):
        return True
    if GREEK_TEXT_RE.search(name) and len(name) >= 12:
        return True
    if len(name) >= 40 and (AD_COPY_TEXT_RE.search(name) or "!" in name or "?" in name):
        return True
    return False


def display_advertiser_name(
    name: object | None,
    brand_name: object | None = None,
    fallback: str | None = "광고주 확인 필요",
) -> str | None:
    for candidate in (brand_name, name):
        normalized = normalize_advertiser_name(candidate)
        if (
            normalized
            and not is_placeholder_advertiser_name(normalized)
            and (normalized in KNOWN_BRAND_NAMES or not is_person_or_handle_advertiser_name(normalized))
        ):
            return normalized
    return fallback


def display_market_advertiser_name(
    name: object | None,
    brand_name: object | None = None,
    fallback: str | None = None,
) -> str | None:
    """Return an advertiser label safe enough for market/competitor surfaces."""
    display = display_advertiser_name(name, brand_name, fallback=None)
    if not display:
        return fallback
    if is_placeholder_advertiser_name(display):
        return fallback
    return display


def display_campaign_advertiser_name(
    name: object | None,
    brand_name: object | None = None,
    *,
    website: object | None = None,
    url: object | None = None,
    ad_text: object | None = None,
    product_service: object | None = None,
    model_info: object | None = None,
    promotion_copy: object | None = None,
    extra_data: object | None = None,
    fallback: str | None = "광고주 확인 필요",
) -> str | None:
    subject = infer_advertised_subject(
        product_service,
        brand_name,
        ad_text,
        promotion_copy,
        model_info,
        website=website,
        url=url,
        extra_data=extra_data,
    )
    if is_low_confidence_campaign_source_name(name):
        return subject or fallback
    return display_advertiser_name(name, brand_name, fallback=fallback)


def campaign_display_fields(
    *,
    campaign_name: object | None = None,
    advertiser_name: object | None = None,
    brand_name: object | None = None,
    website: object | None = None,
    url: object | None = None,
    ad_text: object | None = None,
    product_service: object | None = None,
    model_info: object | None = None,
    promotion_copy: object | None = None,
    extra_data: object | None = None,
    campaign_id: int | None = None,
) -> dict[str, str | None]:
    subject = infer_advertised_subject(
        product_service,
        brand_name,
        ad_text,
        promotion_copy,
        model_info,
        website=website,
        url=url,
        extra_data=extra_data,
    )
    advertiser = display_campaign_advertiser_name(
        advertiser_name,
        brand_name,
        website=website,
        url=url,
        ad_text=ad_text,
        product_service=product_service,
        model_info=model_info,
        promotion_copy=promotion_copy,
        extra_data=extra_data,
        fallback=None,
    )
    if not advertiser:
        advertiser = subject or "광고주 확인 필요"
    cleaned_campaign = clean_campaign_name(
        campaign_name,
        advertiser,
        campaign_id,
        subject=subject,
    )
    return {
        "advertiser_name": advertiser,
        "campaign_name": cleaned_campaign,
        "subject": subject,
    }


def clean_raw_advertiser_name(
    name: object | None,
    brand_name: object | None = None,
) -> str | None:
    return display_advertiser_name(name, brand_name, fallback=None)


def clean_campaign_name(
    campaign_name: object | None,
    advertiser_name: object | None = None,
    campaign_id: int | None = None,
    subject: object | None = None,
) -> str:
    name = normalize_advertiser_name(campaign_name)
    subject_name = normalize_advertiser_name(subject)
    if name and not is_noisy_campaign_name(name, advertiser_name):
        return name

    advertiser = display_advertiser_name(advertiser_name, fallback=None)
    if subject_name:
        return f"{subject_name} 캠페인"
    if advertiser:
        return f"{advertiser} 캠페인"
    if campaign_id:
        return f"캠페인 #{campaign_id}"
    return "캠페인"
