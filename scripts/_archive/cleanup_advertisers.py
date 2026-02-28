"""기존 광고주 데이터 정리 — 가비지 광고주 제거 + verification_status 보정.

Usage:
    python scripts/cleanup_advertisers.py --report-only  # 현황만 출력
    python scripts/cleanup_advertisers.py --dry-run      # 삭제 대상 미리보기
    python scripts/cleanup_advertisers.py                # 실행
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from sqlalchemy import delete, func, select, update

from database import async_session, init_db
from database.models import AdDetail, Advertiser, Campaign, SpendEstimate
from processor.advertiser_verifier import NameQuality, verify_advertiser_name


async def analyze(session) -> dict:
    """전체 광고주 검증 분석."""
    advertisers = (await session.execute(select(Advertiser))).scalars().all()

    valid, garbage = [], []
    for adv in advertisers:
        result = verify_advertiser_name(adv.name)
        entry = {"id": adv.id, "name": adv.name}
        if result.quality == NameQuality.REJECTED:
            entry["reason"] = result.rejection_reason
            garbage.append(entry)
        else:
            entry["cleaned"] = result.cleaned_name
            valid.append(entry)

    return {"valid": valid, "garbage": garbage}


async def main():
    parser = argparse.ArgumentParser(description="광고주 데이터 정리")
    parser.add_argument("--dry-run", action="store_true", help="삭제 대상만 표시")
    parser.add_argument("--report-only", action="store_true", help="통계만 출력")
    args = parser.parse_args()

    await init_db()

    async with async_session() as session:
        analysis = await analyze(session)
        total = len(analysis["valid"]) + len(analysis["garbage"])

        logger.info(f"전체 광고주: {total}")
        logger.info(f"  유효: {len(analysis['valid'])}")
        logger.info(f"  가비지: {len(analysis['garbage'])}")

        if args.report_only:
            for item in analysis["garbage"]:
                logger.info(f"  GARBAGE [{item['id']}] '{item['name']}' -- {item['reason']}")
            return

        garbage_ids = [item["id"] for item in analysis["garbage"]]
        if not garbage_ids:
            logger.info("가비지 광고주 없음. DB 상태 양호.")
            return

        for item in analysis["garbage"]:
            logger.info(f"  REMOVE [{item['id']}] '{item['name']}' -- {item['reason']}")

        if args.dry_run:
            logger.info(f"[DRY-RUN] {len(garbage_ids)}개 광고주 삭제 예정")
            return

        # 1) ad_details의 advertiser_id 해제 + rejected 마킹
        nullified = await session.execute(
            update(AdDetail)
            .where(AdDetail.advertiser_id.in_(garbage_ids))
            .values(
                advertiser_id=None,
                verification_status="rejected",
                verification_source="cleanup:name_quality",
            )
        )
        logger.info(f"ad_details {nullified.rowcount}건 advertiser_id 해제")

        # 2) 연관 campaigns → spend_estimates 삭제
        campaign_ids_result = await session.execute(
            select(Campaign.id).where(Campaign.advertiser_id.in_(garbage_ids))
        )
        campaign_ids = [r[0] for r in campaign_ids_result.all()]
        if campaign_ids:
            await session.execute(
                delete(SpendEstimate).where(SpendEstimate.campaign_id.in_(campaign_ids))
            )
            await session.execute(
                delete(Campaign).where(Campaign.id.in_(campaign_ids))
            )
            logger.info(f"campaigns {len(campaign_ids)}건 삭제")

        # 3) 가비지 광고주 삭제
        await session.execute(
            delete(Advertiser).where(Advertiser.id.in_(garbage_ids))
        )
        logger.info(f"advertisers {len(garbage_ids)}건 삭제")

        # 4) 유효 광고주 이름 정제
        name_updated = 0
        for item in analysis["valid"]:
            if item["cleaned"] and item["cleaned"] != item["name"]:
                await session.execute(
                    update(Advertiser)
                    .where(Advertiser.id == item["id"])
                    .values(name=item["cleaned"])
                )
                name_updated += 1
        if name_updated:
            logger.info(f"광고주명 정제: {name_updated}건")

        await session.flush()

        # 5) 중복 광고주 병합 (정제 후 동일명)
        all_advs = (await session.execute(
            select(Advertiser).order_by(Advertiser.id)
        )).scalars().all()

        name_to_canonical: dict[str, int] = {}
        merge_count = 0
        for adv in all_advs:
            norm = adv.name.lower().replace(" ", "").strip()
            if norm in name_to_canonical:
                keep_id = name_to_canonical[norm]
                # Reassign ad_details and campaigns
                await session.execute(
                    update(AdDetail)
                    .where(AdDetail.advertiser_id == adv.id)
                    .values(advertiser_id=keep_id)
                )
                await session.execute(
                    update(Campaign)
                    .where(Campaign.advertiser_id == adv.id)
                    .values(advertiser_id=keep_id)
                )
                await session.execute(
                    delete(Advertiser).where(Advertiser.id == adv.id)
                )
                merge_count += 1
            else:
                name_to_canonical[norm] = adv.id

        if merge_count:
            logger.info(f"중복 광고주 병합: {merge_count}건")

        await session.commit()
        logger.info("정리 완료!")


if __name__ == "__main__":
    asyncio.run(main())
