"""DB 테이블 생성 + 시드 데이터 적재 스크립트."""

import asyncio
import json
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from database import async_session, init_db
from database.models import Industry, Keyword, Persona


async def seed():
    # 1) 테이블 생성
    print("[1/4] 테이블 생성 중...")
    await init_db()
    print("      10개 테이블 생성 완료")

    async with async_session() as session:
        # 이미 데이터가 있으면 스킵
        existing = await session.execute(select(Industry).limit(1))
        if existing.scalar_one_or_none():
            print("[SKIP] 시드 데이터가 이미 존재합니다.")
            return

        # 2) 업종 시드
        print("[2/4] 업종 데이터 적재 중...")
        seed_dir = Path(__file__).resolve().parent.parent / "database" / "seed_data"

        with open(seed_dir / "industries.json", encoding="utf-8") as f:
            industries_data = json.load(f)

        for item in industries_data:
            session.add(Industry(
                id=item["id"],
                name=item["name"],
                avg_cpc_min=item["avg_cpc_min"],
                avg_cpc_max=item["avg_cpc_max"],
            ))
        await session.flush()
        print(f"      {len(industries_data)}개 업종 적재 완료")

        # 3) 키워드 시드
        print("[3/4] 키워드 데이터 적재 중...")
        with open(seed_dir / "keywords.json", encoding="utf-8") as f:
            keywords_data = json.load(f)

        for item in keywords_data:
            session.add(Keyword(
                industry_id=item["industry_id"],
                keyword=item["keyword"],
                naver_cpc=item.get("naver_cpc"),
                monthly_search_vol=item.get("monthly_search_vol"),
            ))
        await session.flush()
        print(f"      {len(keywords_data)}개 키워드 적재 완료")

        # 4) 페르소나 시드
        print("[4/4] 페르소나 데이터 적재 중...")
        personas = [
            Persona(code="P1", age_group="20대", gender="여성", login_type="naver",
                    description="20대 여성 — 인스타 릴스 > 유튜브, 퇴근후 피크"),
            Persona(code="P2", age_group="30대", gender="남성", login_type="naver",
                    description="30대 남성 — OTT 최다 이용, 출퇴근+점심 분산"),
            Persona(code="P3", age_group="50대", gender="여성", login_type="naver",
                    description="50대 여성 — 오전/오후 활발, 20시 이후 최대 피크"),
            Persona(code="P4", age_group=None, gender=None, login_type="none",
                    description="비로그인 — 타겟팅 없는 기본 광고 노출 기준선"),
        ]
        for p in personas:
            session.add(p)
        await session.flush()
        print(f"      {len(personas)}개 페르소나 적재 완료")

        await session.commit()

    print("\n=== 시드 데이터 적재 완료 ===")
    print(f"  업종: {len(industries_data)}개")
    print(f"  키워드: {len(keywords_data)}개")
    print(f"  페르소나: {len(personas)}개")


if __name__ == "__main__":
    asyncio.run(seed())
