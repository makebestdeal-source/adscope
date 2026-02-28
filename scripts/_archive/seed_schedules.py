"""페르소나 14명 + crawl_schedules 84슬롯 시드 적재.

Phase 3B: 12명 인구통계 + 2명 제어그룹 = 14명.
14명 × 3회 × 2(평일/주말) = 84슬롯.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://adscope:adscope@localhost:5433/adscope"

from sqlalchemy import delete, select

from crawler.personas.profiles import PERSONAS
from database import async_session, init_db
from database.models import CrawlSchedule, Persona
from scheduler.schedules import WEEKDAY_SCHEDULE, WEEKEND_SCHEDULE


async def seed_personas(session) -> dict[str, int]:
    """14명 페르소나 시딩. 기존 P1~P4 제거 후 신규 적재."""
    # 기존 페르소나 조회
    result = await session.execute(select(Persona))
    existing = {p.code: p for p in result.scalars()}
    old_codes = {"P1", "P2", "P3", "P4"}

    created = 0
    updated = 0

    for code, profile in PERSONAS.items():
        if code in existing:
            # 기존 페르소나 업데이트
            p = existing[code]
            p.age_group = profile.age_group
            p.gender = profile.gender
            p.login_type = profile.login_type
            p.description = profile.description
            p.targeting_category = profile.targeting_category
            p.is_clean = profile.is_clean
            p.primary_device = profile.primary_device
            updated += 1
        else:
            # 신규 페르소나 생성
            session.add(
                Persona(
                    code=code,
                    age_group=profile.age_group,
                    gender=profile.gender,
                    login_type=profile.login_type,
                    description=profile.description,
                    targeting_category=profile.targeting_category,
                    is_clean=profile.is_clean,
                    primary_device=profile.primary_device,
                )
            )
            created += 1

    await session.flush()

    # 최종 매핑
    result = await session.execute(select(Persona))
    persona_map = {p.code: p.id for p in result.scalars()}

    print(f"페르소나: {created}명 생성, {updated}명 업데이트 (총 {len(persona_map)}명)")
    return persona_map


async def seed_schedules(session, persona_map: dict[str, int]):
    """84슬롯 스케줄 시딩. 기존 스케줄 전체 교체."""
    # 기존 스케줄 삭제
    await session.execute(delete(CrawlSchedule))

    count = 0
    for slot in WEEKDAY_SCHEDULE:
        pid = persona_map.get(slot.persona_code)
        if not pid:
            print(f"  Warning: persona {slot.persona_code} not found")
            continue
        session.add(
            CrawlSchedule(
                persona_id=pid,
                day_type="weekday",
                time_slot=slot.time,
                device_type=slot.device,
                label=slot.label,
            )
        )
        count += 1

    for slot in WEEKEND_SCHEDULE:
        pid = persona_map.get(slot.persona_code)
        if not pid:
            continue
        session.add(
            CrawlSchedule(
                persona_id=pid,
                day_type="weekend",
                time_slot=slot.time,
                device_type=slot.device,
                label=slot.label,
            )
        )
        count += 1

    print(f"crawl_schedules {count}건 적재 완료")


async def main():
    await init_db()

    async with async_session() as session:
        persona_map = await seed_personas(session)
        await seed_schedules(session, persona_map)
        await session.commit()

    print("\n시딩 완료:")
    print(f"  페르소나: {len(PERSONAS)}명")
    print(f"  평일 스케줄: {len(WEEKDAY_SCHEDULE)}슬롯")
    print(f"  주말 스케줄: {len(WEEKEND_SCHEDULE)}슬롯")
    print(f"  총 스케줄: {len(WEEKDAY_SCHEDULE) + len(WEEKEND_SCHEDULE)}슬롯")


if __name__ == "__main__":
    asyncio.run(main())
