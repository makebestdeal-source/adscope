"""배너 이미지 시각적 광고 마크 탐지기.

Vision AI로 배너 이미지 내 i마크/AD뱃지/x마크/"광고" 텍스트 등을 탐지하여:
1. 광고 여부 이중 검증 (네트워크 인터셉트 + 시각적 마크)
2. 광고 플랫폼 식별 (i마크→구글, "광고"→네이버/카카오)
3. 신규 매체 발굴 (미분류 마크 → unknown_ad_marks 테이블)

Usage:
  python -m processor.visual_mark_detector                    # 기본 200건
  python -m processor.visual_mark_detector --limit 50         # 50건
  python -m processor.visual_mark_detector --channel google_gdn  # 채널 필터
  python -m processor.visual_mark_detector --force            # 재분석
"""
import asyncio
import base64
import json
import os
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)

# .env 로드 (모듈 직접 실행 시에도 동작)
from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

from loguru import logger

# ── Vision AI 설정 ──
_VISION_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
_VISION_MODEL = os.getenv("AI_VISION_MODEL", "google/gemma-3-27b-it:free")
_VISION_BASE_URL = "https://openrouter.ai/api/v1"

BATCH_SIZE = 30
CONCURRENCY = 3
MIN_IMAGE_SIZE = 1000  # 1KB 미만 스킵

# ── 시각적 마크 → 네트워크 추정 ──
MARK_TO_NETWORK = {
    "i_mark": ("google", 0.95),
    "ad_badge": (None, 0.5),
    "x_mark": (None, 0.3),
    "ad_text_ko": (None, 0.6),
    "sponsored_text": ("meta", 0.85),
    "naver_powerlink": ("naver", 0.99),
    "kakao_bizboard": ("kakao", 0.99),
    "privacy_icon": (None, 0.2),
    "dable_mark": ("dable", 0.9),
    "taboola_mark": ("taboola", 0.9),
    "criteo_mark": ("criteo", 0.9),
    "mobon_mark": ("mobon", 0.9),
    "cauly_mark": ("cauly", 0.9),
}

SYSTEM_PROMPT = """당신은 한국 디지털 광고 배너 이미지의 광고 표시(ad mark) 감지 전문가입니다.

배너 이미지를 분석하여 광고임을 나타내는 시각적 마커를 찾아주세요.

감지 대상 마커:
1. **i_mark** (AdChoices 아이콘): 파란색/회색 삼각형 또는 원 안에 "i" 또는 "ⓘ" 표시. 주로 우측 상단. 구글 GDN/AdSense 대표 표시.
2. **ad_badge**: "AD", "광고", "Sponsored", "스폰서" 텍스트가 있는 뱃지/라벨. 배경색 있는 작은 박스.
3. **x_mark** (닫기 버튼): 광고 닫기용 X 버튼. 주로 우측 상단. 광고 전용 닫기 버튼만 해당.
4. **ad_text_ko**: 이미지 내 "광고" 한글 텍스트 표시. 네이버/카카오 광고에 흔함.
5. **sponsored_text**: "Sponsored", "스폰서", "Paid" 텍스트. 메타/인스타 광고.
6. **naver_powerlink**: "파워링크" 텍스트 표시.
7. **kakao_bizboard**: "비즈보드" 또는 카카오 광고 고유 마크.
8. **privacy_icon**: 개인정보 아이콘 (shield/lock 등).
9. **dable_mark**: "dable" 로고 또는 "데이블" 텍스트. 네이티브 광고 플랫폼.
10. **taboola_mark**: "Taboola" 로고/텍스트. 콘텐츠 추천 광고.
11. **criteo_mark**: "Criteo" 로고/텍스트. 리타겟팅 광고.
12. **mobon_mark**: "모비온" 또는 "Mobon" 텍스트. 국내 DSP.
13. **cauly_mark**: "카울리" 또는 "Cauly" 텍스트. 모바일 광고.
14. **unknown_mark**: 위 카테고리에 해당하지 않는 새로운 광고 표시.

반드시 JSON으로 응답:
{
  "marks_found": ["i_mark", "x_mark"],
  "mark_details": [
    {"type": "i_mark", "location": "top_right", "confidence": 0.95, "description": "파란 삼각형 i 아이콘"}
  ],
  "inferred_network": "google",
  "network_confidence": 0.9,
  "is_ad_image": true,
  "unknown_marks": []
}

네트워크 추정 규칙:
- i_mark → google (GDN/AdSense)
- "광고" + 네이버 스타일 UI → naver
- "광고" + 카카오 스타일 UI → kakao
- "Sponsored"/"스폰서" → meta
- dable/taboola/criteo/mobon/cauly 로고 → 해당 네트워크
- 알 수 없는 마크 → unknown (unknown_marks에 상세 기록)

마커가 전혀 없으면 marks_found를 빈 배열로 응답.
광고 콘텐츠 자체가 아닌 광고 '표시' 마크만 찾아주세요."""


def _encode_image(path: str) -> str | None:
    """이미지 파일을 base64로 인코딩."""
    try:
        full_path = Path(_root) / path if not Path(path).is_absolute() else Path(path)
        if not full_path.exists():
            return None
        size = full_path.stat().st_size
        if size < MIN_IMAGE_SIZE:
            return None
        with open(full_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return None


def _detect_mime(path: str) -> str:
    """파일 확장자로 MIME 타입 추정."""
    ext = Path(path).suffix.lower()
    return {
        ".webp": "image/webp",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
    }.get(ext, "image/webp")


def _infer_network_from_marks(marks: list[str], channel: str) -> tuple[str, float]:
    """발견된 마크 조합 + 채널 정보로 네트워크 추정."""
    if not marks:
        return ("none", 0.0)

    best_network = None
    best_conf = 0.0

    for mark in marks:
        entry = MARK_TO_NETWORK.get(mark)
        if not entry:
            continue
        network, conf = entry

        # 채널 컨텍스트로 ad_text_ko("광고") 보정
        if mark == "ad_text_ko" and network is None:
            if "naver" in channel:
                network, conf = "naver", 0.9
            elif "kakao" in channel:
                network, conf = "kakao", 0.9
            else:
                network, conf = "unknown", 0.5

        if network and conf > best_conf:
            best_network = network
            best_conf = conf

    return (best_network or "unknown", best_conf)


def _parse_vision_response(text: str) -> dict | None:
    """Vision API 응답에서 JSON 추출."""
    # 먼저 직접 파싱 시도
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # markdown 코드블록에서 추출
    import re
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 첫 번째 { ... } 블록 추출
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


async def _analyze_single_image(
    client, image_path: str, channel: str
) -> dict | None:
    """단일 이미지를 Vision API로 분석."""
    b64 = _encode_image(image_path)
    if not b64:
        return None

    mime = _detect_mime(image_path)

    try:
        resp = await client.chat.completions.create(
            model=_VISION_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                        {
                            "type": "text",
                            "text": f"이 배너 이미지에서 광고 마크를 찾아주세요. 수집 채널: {channel}",
                        },
                    ],
                },
            ],
            max_tokens=500,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content
        return _parse_vision_response(raw)
    except Exception as e:
        logger.warning("[visual_mark] API error for {}: {}", image_path, str(e)[:100])
        return None


async def detect_visual_marks(
    limit: int = 200,
    channel_filter: str | None = None,
    force: bool = False,
) -> dict:
    """메인 배치 처리. ad_details의 이미지를 Vision AI로 분석.

    Returns: {"analyzed": N, "marks_found": N, "unknown_marks": N, "errors": N}
    """
    if not _VISION_API_KEY:
        logger.warning("[visual_mark] OPENROUTER_API_KEY not set, skipping")
        return {"analyzed": 0, "marks_found": 0, "unknown_marks": 0, "errors": 0}

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=_VISION_API_KEY, base_url=_VISION_BASE_URL)

    from database import async_session
    from sqlalchemy import text

    # 분석 대상 조회
    where_clauses = ["d.creative_image_path IS NOT NULL"]
    if not force:
        where_clauses.append("(d.visual_mark_analyzed IS NULL OR d.visual_mark_analyzed = 0)")
    if channel_filter:
        where_clauses.append(f"s.channel = '{channel_filter}'")

    where_sql = " AND ".join(where_clauses)

    async with async_session() as session:
        rows = (
            await session.execute(
                text(
                    f"""SELECT d.id, d.creative_image_path, s.channel
                    FROM ad_details d
                    JOIN ad_snapshots s ON d.snapshot_id = s.id
                    WHERE {where_sql}
                    ORDER BY
                        CASE s.channel
                            WHEN 'google_gdn' THEN 1
                            WHEN 'kakao_da' THEN 2
                            WHEN 'naver_da' THEN 3
                            WHEN 'facebook' THEN 4
                            WHEN 'instagram' THEN 5
                            ELSE 6
                        END
                    LIMIT :lim"""
                ),
                {"lim": limit},
            )
        ).fetchall()

    logger.info("[visual_mark] Found {} images to analyze", len(rows))

    if not rows:
        return {"analyzed": 0, "marks_found": 0, "unknown_marks": 0, "errors": 0}

    stats = {"analyzed": 0, "marks_found": 0, "unknown_marks": 0, "errors": 0}
    sem = asyncio.Semaphore(CONCURRENCY)

    async def process_one(detail_id, img_path, channel):
        async with sem:
            result = await _analyze_single_image(client, img_path, channel)
            return (detail_id, img_path, channel, result)

    # 배치 처리
    for batch_start in range(0, len(rows), BATCH_SIZE):
        batch = rows[batch_start : batch_start + BATCH_SIZE]
        tasks = [process_one(r[0], r[1], r[2]) for r in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        async with async_session() as session:
            for res in results:
                if isinstance(res, Exception):
                    stats["errors"] += 1
                    continue

                detail_id, img_path, channel, vision_result = res
                stats["analyzed"] += 1

                if vision_result is None:
                    # API 실패 또는 이미지 인코딩 실패 → 분석완료 표시
                    await session.execute(
                        text(
                            "UPDATE ad_details SET visual_mark_analyzed = 1 WHERE id = :id"
                        ),
                        {"id": detail_id},
                    )
                    stats["errors"] += 1
                    continue

                marks_found = vision_result.get("marks_found", [])
                mark_details = vision_result.get("mark_details", [])
                inferred_network = vision_result.get("inferred_network", "")
                network_confidence = vision_result.get("network_confidence", 0.0)
                unknown_marks = vision_result.get("unknown_marks", [])

                # 마크 발견 시 룰 기반 보정
                if marks_found:
                    rule_network, rule_conf = _infer_network_from_marks(
                        marks_found, channel
                    )
                    # Vision API 추정보다 룰 기반이 더 신뢰 높으면 대체
                    if rule_conf > network_confidence:
                        inferred_network = rule_network
                        network_confidence = rule_conf

                    stats["marks_found"] += 1

                # ad_details 업데이트
                await session.execute(
                    text(
                        """UPDATE ad_details SET
                            visual_mark_detected = :marks,
                            visual_mark_network = :network,
                            visual_mark_confidence = :conf,
                            visual_mark_analyzed = 1,
                            visual_mark_result = :result
                        WHERE id = :id"""
                    ),
                    {
                        "id": detail_id,
                        "marks": ",".join(marks_found) if marks_found else None,
                        "network": inferred_network or None,
                        "conf": network_confidence,
                        "result": json.dumps(vision_result, ensure_ascii=False),
                    },
                )

                # 미지 마크 저장
                for um in unknown_marks:
                    if isinstance(um, str):
                        um = {"description": um, "location": "", "possible_network": ""}
                    elif not isinstance(um, dict):
                        continue
                    await session.execute(
                        text(
                            """INSERT INTO unknown_ad_marks
                            (ad_detail_id, mark_description, mark_location, suggested_network)
                            VALUES (:did, :desc, :loc, :net)"""
                        ),
                        {
                            "did": detail_id,
                            "desc": um.get("description", "unknown"),
                            "loc": um.get("location", ""),
                            "net": um.get("possible_network", ""),
                        },
                    )
                    stats["unknown_marks"] += 1

            await session.commit()

        logger.info(
            "[visual_mark] Batch {}-{}/{}: marks={}, unknown={}, errors={}",
            batch_start,
            batch_start + len(batch),
            len(rows),
            stats["marks_found"],
            stats["unknown_marks"],
            stats["errors"],
        )
        # API 속도 제한 대비
        await asyncio.sleep(1)

    # 신규 매체 발굴 경고
    await _check_new_networks()

    logger.info("[visual_mark] Done: {}", stats)
    return stats


async def _check_new_networks():
    """unknown_ad_marks에서 반복되는 네트워크 패턴 경고."""
    from database import async_session
    from sqlalchemy import text

    async with async_session() as session:
        rows = (
            await session.execute(
                text(
                    """SELECT suggested_network, COUNT(*) as cnt
                    FROM unknown_ad_marks
                    WHERE status = 'new'
                      AND suggested_network IS NOT NULL
                      AND suggested_network != ''
                    GROUP BY suggested_network
                    HAVING cnt >= 3
                    ORDER BY cnt DESC"""
                )
            )
        ).fetchall()

        for network, count in rows:
            logger.warning(
                "[visual_mark] Potential new ad network detected: '{}' (seen {} times)",
                network,
                count,
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Visual ad mark detector")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--channel", type=str, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    async def main():
        from database import init_db
        await init_db()
        result = await detect_visual_marks(
            limit=args.limit,
            channel_filter=args.channel,
            force=args.force,
        )
        print(f"Result: {result}")

    asyncio.run(main())
