"""기타 업종 광고주 AI 자동 분류 스크립트 (DeepSeek).

업종이 '기타'(id=1)인 광고주를 이름+웹사이트 기반으로 DeepSeek 배치 분류.
광고 수가 많은 순서로 처리.

Usage:
    python scripts/classify_industries.py           # 전체 실행
    python scripts/classify_industries.py --limit 500  # 500개만
    python scripts/classify_industries.py --dry-run    # DB 업데이트 안 함
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sqlite3
from openai import AsyncOpenAI

DB_PATH = ROOT / "adscope.db"
API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-70891bb3f55644d2a5c168e22908a274")
MODEL = "deepseek-chat"
BATCH_SIZE = 60  # 1회 요청당 광고주 수
SLEEP_BETWEEN = 1.5  # 요청 간 딜레이(초)

# 현재 DB industry id → name 매핑
INDUSTRY_ID_MAP = {
    "기타": 1,
    "IT/통신": 2,
    "자동차": 3,
    "금융/보험": 4,
    "식품/음료": 5,
    "뷰티/화장품": 6,
    "패션/의류": 7,
    "유통/이커머스": 8,
    "제약/헬스케어": 9,
    "가전/전자": 10,
    "건설/부동산": 11,
    "게임": 12,
    "엔터테인먼트": 13,
    "여행/항공": 14,
    "교육": 15,
    "스포츠/아웃도어": 16,
    "가구/인테리어": 17,
    "주류": 18,
    "공공기관": 19,
    "반려동물": 20,
    "생활용품": 21,
}

INDUSTRY_LIST_STR = ", ".join(INDUSTRY_ID_MAP.keys())

SYSTEM_PROMPT = f"""당신은 한국 디지털 광고 업종 분류 전문가입니다.
광고주 이름과 웹사이트를 보고 아래 업종 목록 중 하나를 선택하세요.

업종 목록:
{INDUSTRY_LIST_STR}

분류 기준:
- IT/통신: 통신사, IT서비스, SaaS, 앱/플랫폼
- 자동차: 자동차 제조/판매/부품/렌트
- 금융/보험: 은행, 증권, 보험, 카드, 대출
- 식품/음료: 식품 제조/유통, 음료, 커피, 배달
- 뷰티/화장품: 화장품, 스킨케어, 헤어케어
- 패션/의류: 의류, 신발, 가방, 패션잡화
- 유통/이커머스: 쇼핑몰, 소매/대형마트, 오픈마켓
- 제약/헬스케어: 제약, 의료기기, 병원, 건강기능식품
- 가전/전자: 가전, 전자제품, 반도체
- 건설/부동산: 건설사, 부동산, 분양, 인테리어(건설)
- 게임: 게임 개발/퍼블리싱
- 엔터테인먼트: 방송, 영화, 음악, OTT, 공연
- 여행/항공: 항공사, 여행사, 숙박, 호텔
- 교육: 학원, 교육기관, 에듀테크, 어학
- 스포츠/아웃도어: 스포츠용품, 피트니스, 레저
- 가구/인테리어: 가구, 홈데코, 생활인테리어
- 주류: 주류 제조/유통
- 공공기관: 정부기관, 지자체, 공기업
- 반려동물: 펫푸드, 펫케어, 동물병원
- 생활용품: 생활소비재, 세제, 위생용품, 문구
- 기타: 위 어디에도 해당 없음

반드시 JSON 배열로만 응답:
[{{"id": 1, "industry": "업종명"}}, ...]
id는 입력받은 광고주 번호, industry는 위 목록 중 정확히 하나."""


async def classify_batch(
    client: AsyncOpenAI,
    batch: list[tuple[int, str, str | None]],  # (adv_id, name, website)
) -> dict[int, str]:
    """배치 분류 → {adv_id: industry_name}"""
    items = []
    for i, (adv_id, name, website) in enumerate(batch, 1):
        site = website or ""
        items.append(f'{i}. ID={adv_id} | 광고주명: {name} | 웹사이트: {site}')
    user_msg = "\n".join(items)

    # adv_id → 순번 역매핑 (1-indexed)
    seq_to_id = {i: adv_id for i, (adv_id, _, _) in enumerate(batch, 1)}
    id_set = {adv_id for adv_id, _, _ in batch}

    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=1500,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        # JSON 추출 (```json 블록 처리)
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        result = {}
        for item in data:
            raw_id = item["id"]
            # DeepSeek이 실제 adv_id를 그대로 반환하는 경우
            if raw_id in id_set:
                result[raw_id] = item["industry"]
            # 1-indexed 순번으로 반환하는 경우
            elif raw_id in seq_to_id:
                result[seq_to_id[raw_id]] = item["industry"]
        return result
    except Exception as e:
        print(f"  [ERROR] 배치 분류 실패: {e}")
        return {}


async def main(limit: int, dry_run: bool, db_path: str = None):
    path = db_path or str(DB_PATH)
    conn = sqlite3.connect(path)
    conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
    cur = conn.cursor()

    # 기타(id=1)인 광고주 중 광고 수가 많은 순으로 조회
    cur.execute("""
        SELECT a.id, a.name, a.website, COUNT(d.id) as ad_cnt
        FROM advertisers a
        LEFT JOIN ad_details d ON d.advertiser_id = a.id
        WHERE a.industry_id = 1
        GROUP BY a.id
        ORDER BY ad_cnt DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    print(f"분류 대상: {len(rows)}개 광고주 (광고 많은 순)")

    client = AsyncOpenAI(
        api_key=API_KEY,
        base_url="https://api.deepseek.com",
    )

    total_updated = 0
    total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        batch_rows = rows[batch_idx * BATCH_SIZE:(batch_idx + 1) * BATCH_SIZE]
        batch = [(r[0], r[1], r[2]) for r in batch_rows]

        print(f"\n[{batch_idx + 1}/{total_batches}] {len(batch)}개 분류 중...")
        results = await classify_batch(client, batch)

        for adv_id, industry_name in results.items():
            new_id = INDUSTRY_ID_MAP.get(industry_name, 1)
            if new_id != 1:  # 기타가 아닌 경우만 업데이트
                adv_name = next(r[1] for r in batch if r[0] == adv_id)
                if not dry_run:
                    cur.execute(
                        "UPDATE advertisers SET industry_id = ? WHERE id = ?",
                        (new_id, adv_id)
                    )
                    total_updated += 1
                else:
                    print(f"  [DRY] {adv_name} → {industry_name}(id={new_id})")
                    total_updated += 1

        if not dry_run:
            conn.commit()

        print(f"  → 이번 배치 업데이트: {sum(1 for v in results.values() if INDUSTRY_ID_MAP.get(v, 1) != 1)}개")

        if batch_idx < total_batches - 1:
            await asyncio.sleep(SLEEP_BETWEEN)

    conn.close()
    print(f"\n완료: 총 {total_updated}개 업데이트{'(DRY RUN)' if dry_run else ''}")

    if not dry_run:
        # 결과 확인
        conn2 = sqlite3.connect(path)
        conn2.text_factory = lambda b: b.decode("utf-8", errors="replace")
        cur2 = conn2.cursor()
        cur2.execute("""
            SELECT i.industry_large, i.name, COUNT(a.id) as cnt
            FROM industries i
            LEFT JOIN advertisers a ON a.industry_id = i.id
            GROUP BY i.id
            ORDER BY cnt DESC
        """)
        print("\n[업종별 광고주 수 (업데이트 후)]")
        for r in cur2.fetchall():
            if r[2] > 0:
                sys.stdout.buffer.write(
                    f"  {r[0]:<15} > {r[1]:<20} : {r[2]}개\n".encode("utf-8")
                )
        conn2.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db", type=str, default=None, help="DB 경로 (기본: adscope.db)")
    args = parser.parse_args()

    # .env 로드
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    asyncio.run(main(args.limit, args.dry_run, args.db))
