"""
Advertiser name cleaner — strips ad copy, platform prefixes, URLs, and merges duplicates.
Runs as part of rebuild_campaigns_and_spend pipeline.

Core pattern to clean:
  "브랜드명  domain.co.kr    광고제목  광고설명1  광고설명2" → "브랜드명"
"""
import re
import logging
from database import async_session
from sqlalchemy import text

log = logging.getLogger(__name__)

# ── Domain / URL patterns ──
_DOMAIN_RE = re.compile(
    r'(?:https?://)?'
    r'([a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)*'
    r'\.(?:com|co\.kr|kr|net|org|io|shop|store|biz|info|me|xyz|tv|app|site|online))'
    r'(?:/\S*)?',
    re.IGNORECASE,
)

# Well-known domain → brand name mapping
_DOMAIN_BRAND_MAP: dict[str, str] = {
    "cowaymall.co.kr": "코웨이", "coway-mall.kr": "코웨이", "coway.co.kr": "코웨이",
    "megastudy.net": "메가스터디", "mbest.co.kr": "엠베스트",
    "11st.co.kr": "11번가", "11st.kr": "11번가",
    "kbinsure.co.kr": "KB손해보험", "kbcarinsure.co.kr": "KB손해보험",
    "directdb.co.kr": "DB손해보험",
    "greenart.co.kr": "그린컴퓨터아카데미",
    "koreaitacademy.com": "코리아IT아카데미",
    "magic-mall.co.kr": "SK매직",
    "meritzfire.com": "메리츠화재",
    "heungkukfire.co.kr": "흥국화재",
    "axakorea.com": "AXA손해보험",
    "shinhanez.co.kr": "신한EZ손해보험",
    "hd-direct.co.kr": "현대해상",
    "yoons.com": "윤선생",
    "ohou.se": "오늘의집",
    "100classics.co.kr": "100클래식",
    "bandimobility.com": "반디모빌리티",
    "shinhyup-credit.co.kr": "신협",
    "ss8282.co.kr": "SS캐피탈",
    "e-lina.co.kr": "라이나생명",
    "joongkyung.com": "중경사무실",
    "kiryn.co.kr": "기린사무실",
    "naran.co.kr": "나란인테리어",
    "thehangang.com": "더한강",
    "jr-hscook.com": "한솥요리학원",
}

# Platform prefixes/suffixes to strip
_PLATFORM_STRIPS = [
    "네이버톡톡", "네이버 톡톡", "카카오톡 상담", "카카오톡상담",
]

# Ad copy markers — if name contains these AND is long, it's likely ad copy
_AD_COPY_MARKERS = [
    # 상담/서비스 관련
    "상담이 가능한", "서비스 보기", "톡톡으로", "맞춤 상품추천",
    "상담 가능", "맡기는", "믿고 맡기",
    # 가격/할인
    "단 하루 특가", "보험료 계산", "10초 ",
    "월 요금제", "한정 최저가", "최대 90%",
    "가격비교", "가맹비 할인", "할인혜택",
    # 구독/무료
    "자유롭게 구독", "구독하기", "무료방문견적", "무료배송",
    "무료토크쇼", "무료상담",
    # 홍보 문구
    "체계적인 교육으로", "누구든지", "안정수익",
    "우수조건보장", "극찬하는", "증명,", "효과!",
    "좌우합니다", "될까?", "이유있는 선택",
    "누적 수업", "누적 수업 수",
    # 제품/서비스 설명
    "인도보장", "무상A/S", "제품무상",
    "솔루션 전문기업", "전문업체", "전문기업",
    # CTA
    "오늘 대출 바로", "24시간 무인", "24시간 반려",
    "마감", "예약가능", "바로가능",
    "돌파!", "팔로우한",
    # 공식 사이트/파트너
    "공식홈페이지", "공식몰 단독", "공식파트너", "공식대리점",
    # URL 패턴
    "service.", ".work/", ".com/", ".kr/",
    # 영문 스팸
    "Visit Instagram", "Visit Profile",
]

# Names that are entirely non-advertiser (delete candidates)
_GARBAGE_NAMES = [
    "Visit Instagram Profile",
    "AD, 광고 닫기",
    "광고 닫기",
    "4면 고정 밴드",
    "NDP_SF",
    "o.",
    "FAQ",
    "map",
]

# Pattern for [unknown-XXX] placeholder names
_UNKNOWN_PATTERN = re.compile(r"^\[unknown-\d+\]$")

# EV model names → KIA mapping
_BRAND_RENAMES = {
    "EV3": "기아 EV",
    "EV4": "기아 EV",
    "EV5": "기아 EV",
    "EV6": "기아 EV",
    "EV9": "기아 EV",
}

# Price/spec pattern — "EV3 월 15만원대!" → "EV3"
_PRICE_PATTERN = re.compile(r"\s*월\s*\d+만원대[!.]?\s*$")

# Generic ad element patterns (UI elements captured as names)
_UI_ELEMENT_PATTERNS = [
    "광고 닫기", "닫기 버튼", "더보기", "자세히보기",
    "바로가기", "지금 바로",
]

# Sentence-ending patterns (Korean verb/adjective endings)
_SENTENCE_ENDINGS = re.compile(
    r"(합니다|입니다|됩니다|습니다|세요|하세요|드립니다|가능$|보기$|확인$|바로$|"
    r"될까\??|돌파!?|효과!?|시작$|구독$|혜택!?$|전문$|전문기업$)"
)


def _extract_brand_name(name: str) -> str | None:
    """Try to extract the brand name from an ad-copy-contaminated name.

    Strategy:
    1. Handle URL/domain pattern: "브랜드  domain.co.kr  광고카피" → "브랜드"
    2. Strip platform prefixes
    3. Take the first meaningful phrase before ad copy markers
    4. If the name starts with a brand that repeats, take the first occurrence
    """
    cleaned = name.strip()

    # ── Step 0a: Handle double-space pattern ──
    # "삼성전자  samsung" → "삼성전자" (brand + bare domain/alias separated by 2+ spaces)
    if "  " in cleaned:
        dbl_parts = re.split(r'\s{2,}', cleaned)
        dbl_parts = [p.strip() for p in dbl_parts if p.strip()]
        if len(dbl_parts) >= 2 and len(dbl_parts[0]) >= 2:
            first = dbl_parts[0]
            second = dbl_parts[1]
            # If second part is mostly Latin/numeric (domain fragment or alias), take first part
            korean_ratio = len(re.findall(r'[\uac00-\ud7af\u3130-\u318f]', second)) / max(len(second), 1)
            if korean_ratio < 0.3:
                # Second part is domain/alias, first part is brand
                return first

    # ── Step 0b: Handle domain/URL in name ──
    # Pattern: "브랜드명  domain.co.kr    광고제목  광고설명"
    domain_match = _DOMAIN_RE.search(cleaned)
    if domain_match:
        domain = domain_match.group(1).lower()
        full_match = domain_match.group(0)

        # Check known brand map
        brand_from_map = None
        for known_domain, brand in _DOMAIN_BRAND_MAP.items():
            if domain == known_domain or domain.endswith("." + known_domain):
                brand_from_map = brand
                break

        # Get text before the domain
        before_domain = cleaned[:domain_match.start()].strip()
        # Clean trailing whitespace/separators
        before_domain = re.sub(r'[\s\-_/\\|,;:]+$', '', before_domain)

        if before_domain and len(before_domain) >= 2:
            # "코웨이공식몰  center.cowaymall.co.kr  ..." → "코웨이공식몰"
            # But prefer mapped brand if shorter and cleaner
            if brand_from_map and len(brand_from_map) < len(before_domain):
                return brand_from_map
            return before_domain
        elif brand_from_map:
            return brand_from_map
        else:
            # Name starts with domain: "hi-homeloan.co.kr  설명" → domain-based name
            # Derive from domain
            domain_parts = domain.replace("-", "").split(".")
            return domain_parts[0] if len(domain_parts[0]) >= 2 else None

    # ── Step 1: Split by double-space/tab (multi-field format) ──
    parts = re.split(r'\s{2,}|\t', cleaned)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 3 and len(parts[0]) >= 2:
        # Multiple fields: first part is likely brand, rest is ad copy
        return parts[0]

    # Strip price patterns (e.g., "EV3 월 15만원대!" → "EV3")
    cleaned = _PRICE_PATTERN.sub("", cleaned).strip()

    # Strip platform prefixes
    for prefix in _PLATFORM_STRIPS:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
        if cleaned.endswith(prefix):
            cleaned = cleaned[:-len(prefix)].strip()

    # If nothing left after stripping, the whole thing was a platform name
    if not cleaned or len(cleaned) < 2:
        return None

    # Split by common delimiters and take first segment
    # "한화손해보험 한화손해보험 보험 상담 10초 보험료 계산" → "한화손해보험"
    words = cleaned.split()
    if len(words) >= 2 and words[0] == words[1]:
        return words[0]

    # Check if first word/phrase appears again (duplicated brand + copy)
    # "짬뽕관 4계절 안정수익, 짬뽕관 체계적인..." → "짬뽕관"
    if len(words) >= 3:
        first = words[0]
        rest = " ".join(words[1:])
        if first in rest and len(first) >= 2:
            return first

    # "EVC1 국산 전기차 충전기 EVC1 ..." → "EVC1"
    for i, w in enumerate(words[1:], 1):
        if w == words[0] and i > 0:
            return words[0]

    # If name has ad copy markers, take everything before the first marker
    for marker in _AD_COPY_MARKERS:
        idx = cleaned.find(marker)
        if idx > 0:
            candidate = cleaned[:idx].strip().rstrip(",. ")
            if len(candidate) >= 2:
                return candidate

    # Sentence pattern: take first 1-3 words if name is sentence-like
    if _SENTENCE_ENDINGS.search(cleaned) and len(cleaned) > 15:
        # Take first word(s) as brand
        candidate = words[0]
        if len(candidate) >= 2:
            return candidate

    # Name is long but no clear brand extraction possible
    if len(cleaned) > 25:
        # Last resort: take first meaningful segment (before space or comma)
        parts = re.split(r"[,\s]+", cleaned, maxsplit=2)
        if len(parts[0]) >= 2:
            return parts[0]

    return cleaned  # Return as-is if no cleanup needed


def clean_name_for_pipeline(raw_name: str) -> str:
    """Quick name cleaning for use in the ingest pipeline.

    Called when creating/updating advertisers to prevent dirty names from entering DB.
    """
    if not raw_name or len(raw_name) < 2:
        return raw_name or ""

    # Fast path: short names are likely clean
    if len(raw_name) <= 15 and not _DOMAIN_RE.search(raw_name):
        return raw_name.strip()

    brand = _extract_brand_name(raw_name)
    return brand if brand and len(brand) >= 2 else raw_name.strip()[:30]


async def clean_advertiser_names() -> dict:
    """Clean advertiser names: strip ad copy, merge duplicates.

    Returns dict with stats: cleaned, merged, deleted.
    """
    stats = {"cleaned": 0, "merged": 0, "deleted": 0}

    async with async_session() as session:
        # Get all advertisers
        result = await session.execute(
            text("SELECT id, name FROM advertisers ORDER BY id")
        )
        advertisers = result.fetchall()

        # Build name -> id mapping (first occurrence wins)
        canonical: dict[str, int] = {}
        to_rename: list[tuple[int, str]] = []  # (id, new_name)
        to_merge: list[tuple[int, int]] = []   # (old_id, target_id)
        to_delete: list[int] = []
        to_force_delete: list[int] = []  # delete even if has campaigns

        for aid, name in advertisers:
            if not name or len(name) < 2:
                continue

            # [unknown-XXX] placeholders → force delete with campaigns
            if _UNKNOWN_PATTERN.match(name):
                to_force_delete.append(aid)
                continue

            # Known brand renames
            if name in _BRAND_RENAMES:
                new_name = _BRAND_RENAMES[name]
                if new_name in canonical:
                    to_merge.append((aid, canonical[new_name]))
                else:
                    canonical[new_name] = aid
                    to_rename.append((aid, new_name))
                continue

            # Garbage names (delete immediately)
            if name in _GARBAGE_NAMES:
                to_delete.append(aid)
                continue
            # UI elements
            is_garbage = False
            for ui in _UI_ELEMENT_PATTERNS:
                if ui in name:
                    to_delete.append(aid)
                    is_garbage = True
                    break
            if is_garbage:
                continue

            # Check if name needs cleaning
            needs_clean = False
            # Domain/URL in name (main issue: "브랜드  domain.co.kr  광고카피")
            if _DOMAIN_RE.search(name):
                needs_clean = True
            # Double-space pattern (brand  fragment)
            if not needs_clean and "  " in name:
                needs_clean = True
            # Price pattern (월 XX만원대)
            if not needs_clean and _PRICE_PATTERN.search(name):
                needs_clean = True
            # Check ad copy markers (lower threshold: 12 chars)
            if not needs_clean and len(name) > 12:
                for marker in _AD_COPY_MARKERS:
                    if marker in name:
                        needs_clean = True
                        break
            if not needs_clean:
                for prefix in _PLATFORM_STRIPS:
                    if prefix in name:
                        needs_clean = True
                        break
            if not needs_clean and _SENTENCE_ENDINGS.search(name) and len(name) > 15:
                needs_clean = True
            # Duplicated brand in name
            if not needs_clean:
                words = name.split()
                if len(words) >= 2 and words[0] == words[1]:
                    needs_clean = True
            # URL in name
            if not needs_clean and re.search(r'https?://|\.com/|\.kr/|\.work/', name):
                needs_clean = True

            if not needs_clean:
                # Register as canonical
                if name not in canonical:
                    canonical[name] = aid
                continue

            # Extract brand name
            brand = _extract_brand_name(name)

            if brand is None or len(brand) < 2:
                # Pure platform/ad text, no brand extractable
                to_delete.append(aid)
                continue

            if brand == name:
                # No change needed
                if name not in canonical:
                    canonical[name] = aid
                continue

            # Check if brand already exists
            if brand in canonical:
                # Merge into existing
                to_merge.append((aid, canonical[brand]))
            else:
                # Rename and register
                canonical[brand] = aid
                to_rename.append((aid, brand))

        # Apply renames
        for aid, new_name in to_rename:
            await session.execute(
                text("UPDATE advertisers SET name = :name WHERE id = :id"),
                {"name": new_name, "id": aid},
            )
            stats["cleaned"] += 1

        # Apply merges (move campaigns + ad_details, then delete)
        for old_id, target_id in to_merge:
            await session.execute(
                text("UPDATE campaigns SET advertiser_id = :target WHERE advertiser_id = :old"),
                {"target": target_id, "old": old_id},
            )
            await session.execute(
                text("UPDATE ad_details SET advertiser_id = :target WHERE advertiser_id = :old"),
                {"target": target_id, "old": old_id},
            )
            await session.execute(
                text("DELETE FROM advertisers WHERE id = :id"),
                {"id": old_id},
            )
            stats["merged"] += 1

        # Apply deletes (only if no campaigns)
        for aid in to_delete:
            r = await session.execute(
                text("SELECT COUNT(*) FROM campaigns WHERE advertiser_id = :id"),
                {"id": aid},
            )
            camp_count = r.scalar() or 0
            if camp_count == 0:
                await session.execute(
                    text("DELETE FROM advertisers WHERE id = :id"),
                    {"id": aid},
                )
                stats["deleted"] += 1
            else:
                # Has campaigns, rename to brand-less placeholder
                await session.execute(
                    text("UPDATE advertisers SET name = :name WHERE id = :id"),
                    {"name": f"[unknown-{aid}]", "id": aid},
                )
                stats["cleaned"] += 1

        # Force delete [unknown-XXX] and garbage with campaigns
        for aid in to_force_delete:
            await session.execute(
                text("DELETE FROM spend_estimates WHERE campaign_id IN (SELECT id FROM campaigns WHERE advertiser_id = :id)"),
                {"id": aid},
            )
            await session.execute(
                text("DELETE FROM campaigns WHERE advertiser_id = :id"),
                {"id": aid},
            )
            await session.execute(
                text("DELETE FROM ad_details WHERE advertiser_id = :id"),
                {"id": aid},
            )
            await session.execute(
                text("DELETE FROM advertisers WHERE id = :id"),
                {"id": aid},
            )
            stats["deleted"] += 1

        await session.commit()

    log.info(
        "advertiser_name_cleaner: cleaned=%d merged=%d deleted=%d",
        stats["cleaned"], stats["merged"], stats["deleted"],
    )
    return stats
