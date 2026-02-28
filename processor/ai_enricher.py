"""AI-based ad data enrichment using DeepSeek Vision (daily batch).

Analyzes creative screenshots and ad text to extract:
- Advertiser name / brand
- Product / service
- Industry classification
- Ad type (brand awareness, performance, retargeting, etc.)

Usage:
    python -m processor.ai_enricher          # enrich all unresolved
    python -m processor.ai_enricher --limit 50  # limit batch size
    python -m processor.ai_enricher --channel google_gdn  # specific channel

Env:
    DEEPSEEK_API_KEY  -- required
    AI_ENRICH_MODEL   -- default: deepseek-chat
    AI_ENRICH_BATCH   -- max per run (default: 200)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path

from loguru import logger
from openai import AsyncOpenAI
from sqlalchemy import select

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from database import async_session
from database.models import AdDetail, AdSnapshot, Advertiser, Industry, ProductCategory
from processor.advertiser_link_collector import extract_website_from_url
from processor.advertiser_name_cleaner import clean_name_for_pipeline as clean_name_pipeline
from processor.korean_filter import clean_advertiser_name

# Text AI (DeepSeek)
_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
_MODEL = os.getenv("AI_ENRICH_MODEL", "deepseek-chat")
_BASE_URL = os.getenv("AI_ENRICH_BASE_URL", "https://api.deepseek.com")
_MAX_BATCH = int(os.getenv("AI_ENRICH_BATCH", "200"))

# Vision AI (OpenRouter - free vision models)
_VISION_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
_VISION_MODEL = os.getenv("AI_VISION_MODEL", "google/gemma-3-27b-it:free")
_VISION_BASE_URL = "https://openrouter.ai/api/v1"

SYSTEM_PROMPT = """당신은 한국 디지털 광고 분석 전문가입니다.
주어진 광고 정보(이미지, 텍스트, URL 등)를 분석하여 정확한 광고주 정보를 추출하세요.

반드시 JSON으로 응답하세요:
{
  "advertiser_name": "광고주/브랜드 한글명 (확실한 경우만)",
  "advertiser_name_en": "영문명 (있을 경우)",
  "product": "제품/서비스명",
  "product_category": "제품/서비스 카테고리 (아래 소분류 중 택1)",
  "industry": "업종 (아래 중 택1)",
  "ad_type": "광고유형 (brand/performance/retargeting/catalog)",
  "confidence": 0.0~1.0
}

업종 목록: 뷰티/화장품, 패션/의류, 식품/음료, 건강/의료, 금융/보험, 부동산, 교육, IT/테크, 게임, 자동차, 여행/항공, 가전/전자, 생활용품, 유통/이커머스, 엔터테인먼트, 반려동물, 스포츠, 기타

제품/서비스 카테고리 (소분류):
- 가전/전자: TV, 냉장고, 세탁기, 에어컨, 헤어드라이어, 공기청정기, 로봇청소기
- 모바일/IT: 스마트폰, 태블릿, 노트북, 이어폰/헤드폰, 스마트워치
- 소프트웨어/SaaS: 업무툴, 클라우드, 보안솔루션, ERP, CRM, 디자인툴
- 게임: 모바일게임, PC게임, 콘솔게임, 게임플랫폼, e스포츠
- 뷰티/화장품: 스킨케어, 메이크업, 향수, 헤어케어, 남성화장품
- 패션: 의류, 신발, 가방, 액세서리, 스포츠웨어
- 식품/음료: 간편식, 건강식품, 음료, 커피, 주류
- 금융서비스: 대출, 보험, 카드, 투자, 저축
- 자동차: 승용차, SUV, 전기차, 중고차, 수입차
- 여행/레저: 항공권, 호텔, 패키지여행, 렌터카, 레저/체험
- 교육: 어학, 자격증, 온라인강의, 학원, 코딩교육
- 생활서비스: 배달, 이사, 청소, 인테리어, 수리
- 앱서비스: 배달앱, 커머스앱, 금융앱, 유틸리티앱, SNS
- 엔터테인먼트: 영화, OTT, 음악, 공연, 웹툰
- 건강/의료: 병원, 약국, 건강검진, 다이어트, 영양제
- 부동산: 아파트분양, 오피스텔, 전월세, 상가, 토지
- 유통/쇼핑: 종합몰, 전문몰, 중고거래, 직구, 오프라인매장
- 통신/인터넷: 이동통신, 인터넷, IPTV, IoT, 알뜰폰

광고주를 확실히 파악할 수 없으면 confidence를 0.3 이하로 설정하세요."""


def _encode_image(path: str) -> str | None:
    """이미지 파일을 base64로 인코딩."""
    try:
        full_path = Path(_root) / path if not Path(path).is_absolute() else Path(path)
        if not full_path.exists():
            return None
        with open(full_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return None


_GARBAGE_NAMES = {
    "keywordad", "keyword_ad", "keyword ad", "gdn_display_ad",
    "naver_search_ad", "naver_da", "kakao_da", "google_gdn",
    "unknown", "none", "null", "n/a", "광고", "ad",
}
_GARBAGE_DOMAINS = {
    "veta.naver.com", "siape.veta.naver.com", "nam.veta.naver.com",
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "adservice.google.com", "googleads.g.doubleclick.net",
    "facebook.com", "facebook.net", "fbcdn.net",
    "criteo.com", "criteo.net", "taboola.com", "outbrain.com",
}


def _is_garbage_name(name: str) -> bool:
    """AI가 잘못 식별한 가비지 광고주명인지 판별."""
    if not name:
        return True
    n = name.lower().strip()
    if n in _GARBAGE_NAMES:
        return True
    if any(d in n for d in _GARBAGE_DOMAINS):
        return True
    if n.startswith("gdn-") and n[4:].isdigit():
        return True
    return False


def _build_user_message(ad: dict, snapshot: dict, use_vision: bool = False) -> list[dict]:
    """광고 데이터로 AI 분석 요청 메시지 구성."""
    parts: list[dict] = []

    text_info = []
    if ad.get("advertiser_name_raw"):
        text_info.append(f"현재 광고주명: {ad['advertiser_name_raw']}")
    if ad.get("ad_text"):
        text_info.append(f"광고 텍스트: {ad['ad_text'][:200]}")
    if ad.get("ad_description"):
        text_info.append(f"설명: {ad['ad_description'][:200]}")
    if ad.get("url"):
        text_info.append(f"랜딩URL: {ad['url']}")
    if ad.get("display_url"):
        text_info.append(f"표시URL: {ad['display_url']}")
    if snapshot.get("channel"):
        text_info.append(f"채널: {snapshot['channel']}")
    if ad.get("ad_placement"):
        text_info.append(f"게재위치: {ad['ad_placement']}")

    extra = ad.get("extra_data") or {}
    if extra.get("gpt_advertiser_id"):
        text_info.append(f"GDN advertiser ID: {extra['gpt_advertiser_id']}")
    if extra.get("network_landing_url"):
        text_info.append(f"네트워크 랜딩URL: {extra['network_landing_url']}")
    if extra.get("advertiser_source"):
        text_info.append(f"광고주 출처: {extra['advertiser_source']}")

    parts.append({
        "type": "text",
        "text": "이 광고의 광고주/브랜드를 정확히 파악해주세요.\n\n" + "\n".join(text_info),
    })

    # Vision 모델일 때만 이미지 첨부
    if use_vision:
        img_path = ad.get("creative_image_path")
        if img_path:
            b64 = _encode_image(img_path)
            if b64:
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                })

    return parts


async def _call_ai(client: AsyncOpenAI, messages: list[dict], model: str | None = None) -> dict | None:
    """AI API 호출 (DeepSeek or OpenRouter)."""
    text = ""
    try:
        kwargs = {
            "model": model or _MODEL,
            "messages": messages,
            "max_tokens": 300,
            "temperature": 0.1,
        }
        # response_format은 일부 모델에서 미지원 — 텍스트 모델만 사용
        if model is None or "deepseek" in (model or ""):
            kwargs["response_format"] = {"type": "json_object"}
        resp = await client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content.strip()
        # JSON 블록 추출 (마크다운 코드블록 포함 대응)
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(json_lines).strip()
        # { } 추출
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("[ai_enrich] JSON parse failed: {}", text[:200] if text else "empty")
        return None
    except Exception as exc:
        logger.warning("[ai_enrich] API call failed: {}", str(exc)[:200])
        return None


async def _load_industry_map() -> dict[str, int]:
    """업종명 -> industry_id 매핑."""
    async with async_session() as s:
        rows = await s.execute(select(Industry.id, Industry.name))
        return {name: iid for iid, name in rows.all()}


async def _load_product_category_map() -> dict[str, int]:
    """제품 카테고리명 -> product_category_id 매핑."""
    async with async_session() as s:
        rows = await s.execute(select(ProductCategory.id, ProductCategory.name))
        return {name: cid for cid, name in rows.all()}


async def enrich_ads(
    limit: int = _MAX_BATCH,
    channel_filter: str | None = None,
    force: bool = False,
) -> dict[str, int]:
    """미식별 광고를 AI로 분석하여 광고주 정보 보강.

    Returns: {"analyzed": N, "updated": N, "skipped": N, "errors": N}
    """
    if not _API_KEY and not _VISION_API_KEY:
        logger.error("[ai_enrich] No API keys set (DEEPSEEK_API_KEY or OPENROUTER_API_KEY)")
        return {"analyzed": 0, "updated": 0, "skipped": 0, "errors": 1}

    text_client = AsyncOpenAI(
        api_key=_API_KEY, base_url=_BASE_URL, timeout=60.0,
    ) if _API_KEY else None
    vision_client = AsyncOpenAI(
        api_key=_VISION_API_KEY, base_url=_VISION_BASE_URL, timeout=60.0,
    ) if _VISION_API_KEY else None
    industry_map = await _load_industry_map()
    product_category_map = await _load_product_category_map()

    stats = {"analyzed": 0, "updated": 0, "skipped": 0, "errors": 0, "vision_upgraded": 0}

    async with async_session() as session:
        # 대상: advertiser_id가 없거나, GDN-xxx 이름이거나, 스크린샷 있는데 이름 없는 것
        query = (
            select(AdDetail, AdSnapshot)
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
        )

        if not force:
            # AI 보강 안 된 것만
            query = query.where(
                AdDetail.advertiser_id.is_(None)
                | AdDetail.advertiser_name_raw.like("GDN-%")
            )

        if channel_filter:
            query = query.where(AdSnapshot.channel == channel_filter)

        # 스크린샷 있는 것 우선
        query = query.order_by(
            AdDetail.creative_image_path.is_(None).asc(),
        ).limit(limit)

        rows = (await session.execute(query)).all()
        if not rows:
            logger.info("[ai_enrich] no ads to enrich")
            return stats

        logger.info("[ai_enrich] {} ads to analyze", len(rows))

        # 기존 광고주 캐시
        advertisers = (await session.execute(select(Advertiser))).scalars().all()
        name_to_id = {a.name: a.id for a in advertisers}
        norm_to_id = {a.name.lower().replace(" ", ""): a.id for a in advertisers}

        # ── 배치 처리 (50건씩, 텍스트만 5건 동시) ──
        BATCH_SIZE = 50
        CONCURRENCY = 5

        all_items = []
        for detail, snapshot in rows:
            ad_data = {
                "advertiser_name_raw": detail.advertiser_name_raw,
                "ad_text": detail.ad_text,
                "ad_description": detail.ad_description,
                "url": detail.url,
                "display_url": detail.display_url,
                "ad_placement": detail.ad_placement,
                "creative_image_path": detail.creative_image_path,
                "extra_data": detail.extra_data,
            }
            snap_data = {"channel": snapshot.channel}
            all_items.append((detail, snapshot, ad_data, snap_data))

        sem = asyncio.Semaphore(CONCURRENCY)

        async def _text_analyze(ad_data: dict, snap_data: dict) -> dict | None:
            async with sem:
                if not text_client:
                    return None
                text_content = _build_user_message(ad_data, snap_data, use_vision=False)
                text_str = "\n".join(p["text"] for p in text_content if p.get("type") == "text")
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text_str},
                ]
                return await _call_ai(text_client, messages)

        for batch_start in range(0, len(all_items), BATCH_SIZE):
            batch = all_items[batch_start:batch_start + BATCH_SIZE]
            logger.info("[ai_enrich] batch {}-{}/{}", batch_start, batch_start + len(batch), len(all_items))

            # 텍스트 API 병렬 호출
            text_tasks = [_text_analyze(ad_data, snap_data) for _, _, ad_data, snap_data in batch]
            text_results = await asyncio.gather(*text_tasks, return_exceptions=True)

            # 결과 처리 (순차)
            for idx, (detail, snapshot, ad_data, snap_data) in enumerate(batch):
                result = text_results[idx] if not isinstance(text_results[idx], Exception) else None

                confidence = float(result.get("confidence", 0)) if result else 0
                adv_name = (result.get("advertiser_name") or "").strip() if result else ""
                if _is_garbage_name(adv_name):
                    adv_name = ""
                    confidence = 0

                # Vision fallback 생략 (속도 우선) — confidence 낮으면 skip 처리
                stats["analyzed"] += 1

                if not result:
                    stats["errors"] += 1
                    continue

                if confidence < 0.5 or not adv_name:
                    stats["skipped"] += 1
                    extra = dict(detail.extra_data or {})
                    extra["ai_analysis"] = result
                    detail.extra_data = extra
                    continue

                adv_name = clean_advertiser_name(adv_name) or adv_name
                adv_name = clean_name_pipeline(adv_name)

                adv_id = name_to_id.get(adv_name)
                if not adv_id:
                    adv_id = norm_to_id.get(adv_name.lower().replace(" ", ""))

                if not adv_id:
                    ind_name = (result.get("industry") or "").strip()
                    ind_id = industry_map.get(ind_name)
                    website = extract_website_from_url(detail.url, detail.display_url)
                    adv = Advertiser(name=adv_name, industry_id=ind_id, aliases=[], website=website)
                    session.add(adv)
                    await session.flush()
                    adv_id = adv.id
                    name_to_id[adv_name] = adv_id
                    norm_to_id[adv_name.lower().replace(" ", "")] = adv_id

                detail.advertiser_id = adv_id
                detail.advertiser_name_raw = adv_name

                product_name = (result.get("product") or "").strip()
                if product_name and not _is_garbage_name(product_name):
                    detail.product_name = product_name

                pc_name = (result.get("product_category") or "").strip()
                if pc_name:
                    detail.product_category = pc_name
                    pc_id = product_category_map.get(pc_name)
                    if pc_id:
                        detail.product_category_id = pc_id

                extra = dict(detail.extra_data or {})
                extra["ai_analysis"] = result
                extra["ai_enriched"] = True
                detail.extra_data = extra

                stats["updated"] += 1

            # 배치마다 커밋
            await session.commit()
            logger.info("[ai_enrich] batch done: {}/{} analyzed, {} updated so far",
                        stats["analyzed"], len(all_items), stats["updated"])

    logger.info(
        "[ai_enrich] done: analyzed={}, updated={}, skipped={}, errors={}",
        stats["analyzed"], stats["updated"], stats["skipped"], stats["errors"],
    )

    # SSE 이벤트 발행
    if stats["updated"] > 0:
        try:
            from api.event_bus import event_bus
            await event_bus.publish("ai_enrich_done", {
                "updated": stats["updated"],
                "analyzed": stats["analyzed"],
            })
        except Exception:
            pass

    return stats


async def main():
    import argparse
    from dotenv import load_dotenv
    load_dotenv(Path(_root) / ".env")

    # .env 로드 후 모듈 레벨 변수 갱신
    global _API_KEY, _MODEL, _BASE_URL, _MAX_BATCH, _VISION_API_KEY, _VISION_MODEL
    _API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    _MODEL = os.getenv("AI_ENRICH_MODEL", "deepseek-chat")
    _BASE_URL = os.getenv("AI_ENRICH_BASE_URL", "https://api.deepseek.com")
    _MAX_BATCH = int(os.getenv("AI_ENRICH_BATCH", "200"))
    _VISION_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    _VISION_MODEL = os.getenv("AI_VISION_MODEL", "google/gemma-3-27b-it:free")

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=_MAX_BATCH)
    parser.add_argument("--channel", type=str, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    from database import init_db
    await init_db()

    result = await enrich_ads(
        limit=args.limit,
        channel_filter=args.channel,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
