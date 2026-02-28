"""광고주 데이터 정제 v2 -- 가비지 삭제 + 중복 합치기 + 캠페인 리빌드.

Usage:
    python scripts/clean_advertisers.py --report-only  # 현황만 출력
    python scripts/clean_advertisers.py --dry-run      # 변경 미리보기
    python scripts/clean_advertisers.py                # 실행
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from sqlalchemy import delete, select, update

from database import async_session, init_db
from database.models import AdDetail, Advertiser, Campaign, SpendEstimate
from processor.advertiser_verifier import NameQuality, verify_advertiser_name

# -------------------------------------------------------
# 영문/한글 중복 합치기 매핑 (keep_id: 살릴 한글명 ID, merge_ids: 흡수할 영문명 ID들)
# ID는 실행 시 name으로 조회하므로, name 기반으로 정의
# -------------------------------------------------------
MERGE_RULES: list[dict] = [
    # Samsung
    {"keep": "삼성전자", "merge": ["Samsung Electronics America"]},
    {"keep": "삼성카드", "merge": ["Samsung card"]},
    # Shinhan
    {"keep": "신한은행", "merge": ["신한은행 (Shinhan Bank)", "Shinhan Bank / Jinok-dong"]},
    {"keep": "신한카드", "merge": ["Shinhan Card"]},
    # Lotte
    {"keep": "롯데쇼핑", "merge": ["Lotte Card", "Lotte Hotel Seattle"]},
    # CJ
    {"keep": "CJ올리브영", "merge": ["올리브영"]},
    # Kakao
    {"keep": "카카오", "merge": ["Kakao Games", "Kakao piccoma Corp.", "kakao mobility"]},
    # 한샘
    {"keep": "한샘", "merge": ["한샘mall"]},
    # 메디큐브
    {"keep": "메디큐브 에이지알", "merge": ["메디큐브 - Medicube"]},
    # CJCGV -> CGV
    {"keep": "CGV", "merge": ["CJCGV"]},
]


async def _analyze(session) -> dict:
    """전체 광고주 검증 분석."""
    advertisers = (await session.execute(select(Advertiser))).scalars().all()

    valid, garbage = [], []
    for adv in advertisers:
        result = verify_advertiser_name(adv.name)
        entry = {"id": adv.id, "name": adv.name, "obj": adv}
        if result.quality == NameQuality.REJECTED:
            entry["reason"] = result.rejection_reason
            garbage.append(entry)
        else:
            entry["cleaned"] = result.cleaned_name
            valid.append(entry)

    return {"valid": valid, "garbage": garbage, "all": advertisers}


async def _remove_garbage(session, garbage_ids: list[int]) -> dict:
    """가비지 광고주 삭제: ad_details unlink -> campaigns/spend 삭제 -> advertisers 삭제."""
    stats = {"details_unlinked": 0, "campaigns_deleted": 0, "advertisers_deleted": 0}

    if not garbage_ids:
        return stats

    # 1) ad_details advertiser_id 해제
    result = await session.execute(
        update(AdDetail)
        .where(AdDetail.advertiser_id.in_(garbage_ids))
        .values(
            advertiser_id=None,
            verification_status="rejected",
            verification_source="cleanup:name_quality_v2",
        )
    )
    stats["details_unlinked"] = result.rowcount

    # 2) campaigns -> spend_estimates 삭제
    campaign_rows = await session.execute(
        select(Campaign.id).where(Campaign.advertiser_id.in_(garbage_ids))
    )
    campaign_ids = [r[0] for r in campaign_rows.all()]
    if campaign_ids:
        await session.execute(
            delete(SpendEstimate).where(SpendEstimate.campaign_id.in_(campaign_ids))
        )
        await session.execute(
            delete(Campaign).where(Campaign.id.in_(campaign_ids))
        )
        stats["campaigns_deleted"] = len(campaign_ids)

    # 3) advertisers 삭제
    await session.execute(
        delete(Advertiser).where(Advertiser.id.in_(garbage_ids))
    )
    stats["advertisers_deleted"] = len(garbage_ids)

    return stats


async def _merge_duplicates(session, dry_run: bool = False) -> int:
    """영문/한글 중복 광고주 합치기 -- keep으로 ad_details 이전 후 merge 삭제."""
    # name -> Advertiser 매핑
    all_advs = (await session.execute(select(Advertiser))).scalars().all()
    name_map = {adv.name: adv for adv in all_advs}

    merged_count = 0
    for rule in MERGE_RULES:
        keep_name = rule["keep"]
        keep_adv = name_map.get(keep_name)
        if keep_adv is None:
            continue

        for merge_name in rule["merge"]:
            merge_adv = name_map.get(merge_name)
            if merge_adv is None:
                continue

            logger.info(
                f"  MERGE [{merge_adv.id}] '{merge_name}' -> [{keep_adv.id}] '{keep_name}'"
            )

            if dry_run:
                merged_count += 1
                continue

            # ad_details: advertiser_id 이전
            await session.execute(
                update(AdDetail)
                .where(AdDetail.advertiser_id == merge_adv.id)
                .values(advertiser_id=keep_adv.id)
            )

            # campaigns: spend_estimates 먼저 삭제 후 campaigns 삭제
            # (리빌드에서 다시 생성되므로 삭제가 안전)
            merge_campaign_ids = [
                r[0] for r in (
                    await session.execute(
                        select(Campaign.id).where(Campaign.advertiser_id == merge_adv.id)
                    )
                ).all()
            ]
            if merge_campaign_ids:
                await session.execute(
                    delete(SpendEstimate).where(
                        SpendEstimate.campaign_id.in_(merge_campaign_ids)
                    )
                )
                await session.execute(
                    delete(Campaign).where(Campaign.id.in_(merge_campaign_ids))
                )

            # aliases 업데이트
            keep_aliases = keep_adv.aliases or []
            if merge_name not in keep_aliases:
                keep_aliases.append(merge_name)
            keep_adv.aliases = keep_aliases

            # flush -> merge 광고주 삭제 (FK 정합성 보장)
            await session.flush()
            await session.execute(
                delete(Advertiser).where(Advertiser.id == merge_adv.id)
            )
            merged_count += 1

    return merged_count


async def _normalize_names(session, valid_items: list[dict]) -> int:
    """유효 광고주명 정제 (법인접미사 제거 등)."""
    updated = 0
    for item in valid_items:
        cleaned = item.get("cleaned")
        if cleaned and cleaned != item["name"]:
            await session.execute(
                update(Advertiser)
                .where(Advertiser.id == item["id"])
                .values(name=cleaned)
            )
            logger.info(f"  RENAME [{item['id']}] '{item['name']}' -> '{cleaned}'")
            updated += 1
    return updated


async def main():
    parser = argparse.ArgumentParser(description="광고주 데이터 정제 v2")
    parser.add_argument("--dry-run", action="store_true", help="변경 없이 미리보기")
    parser.add_argument("--report-only", action="store_true", help="통계만 출력")
    parser.add_argument("--skip-rebuild", action="store_true", help="캠페인 리빌드 생략")
    args = parser.parse_args()

    await init_db()

    async with async_session() as session:
        analysis = await _analyze(session)
        total = len(analysis["valid"]) + len(analysis["garbage"])

        logger.info(f"== 광고주 현황 ==")
        logger.info(f"  전체: {total}")
        logger.info(f"  유효: {len(analysis['valid'])}")
        logger.info(f"  가비지: {len(analysis['garbage'])}")

        # 가비지 목록 출력
        if analysis["garbage"]:
            logger.info(f"== 가비지 목록 ({len(analysis['garbage'])}) ==")
            for item in analysis["garbage"]:
                logger.info(f"  [{item['id']}] {item['reason']:30s} | {item['name'][:70]}")

        if args.report_only:
            return

        # 1) 가비지 삭제
        garbage_ids = [item["id"] for item in analysis["garbage"]]
        if garbage_ids:
            if args.dry_run:
                logger.info(f"[DRY-RUN] {len(garbage_ids)}개 가비지 광고주 삭제 예정")
            else:
                stats = await _remove_garbage(session, garbage_ids)
                logger.info(
                    f"가비지 삭제: advertisers={stats['advertisers_deleted']}, "
                    f"details_unlinked={stats['details_unlinked']}, "
                    f"campaigns={stats['campaigns_deleted']}"
                )

        # 2) 중복 합치기
        logger.info(f"== 중복 합치기 ==")
        merged = await _merge_duplicates(session, dry_run=args.dry_run)
        if merged:
            logger.info(f"중복 합침: {merged}건")
        else:
            logger.info("합칠 중복 없음")

        # 3) 이름 정제
        logger.info(f"== 이름 정제 ==")
        renamed = await _normalize_names(session, analysis["valid"])
        if renamed:
            logger.info(f"이름 정제: {renamed}건")
        else:
            logger.info("정제할 이름 없음")

        if not args.dry_run:
            await session.commit()
            logger.info("DB 커밋 완료")

            # 최종 현황
            remaining = (
                await session.execute(select(Advertiser))
            ).scalars().all()
            logger.info(f"== 최종 광고주 수: {len(remaining)} ==")

    # 4) 캠페인 리빌드
    if not args.dry_run and not args.skip_rebuild:
        logger.info("== 캠페인 리빌드 ==")
        from processor.campaign_builder import rebuild_campaigns_and_spend
        rebuild_stats = await rebuild_campaigns_and_spend(active_days=7)
        logger.info(
            f"리빌드 완료: linked={rebuild_stats['linked_details']}, "
            f"created={rebuild_stats['created_advertisers']}, "
            f"campaigns={rebuild_stats['campaigns_total']}, "
            f"spend_estimates={rebuild_stats['spend_estimates_total']}"
        )


if __name__ == "__main__":
    asyncio.run(main())
