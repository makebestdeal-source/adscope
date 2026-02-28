"""WebP 이미지 아틀라스(스프라이트시트) 빌더.

stored_images/ 내 소형 WebP 이미지를 채널/날짜별 아틀라스로 결합.
용량 절감 + HTTP 요청 감소.

사용법:
    python scripts/build_image_atlas.py                 # 전체 실행
    python scripts/build_image_atlas.py --dry-run       # 미리보기 (DB/파일 변경 없음)
    python scripts/build_image_atlas.py --channel facebook  # 특정 채널만
"""
import asyncio
import io
import json
import os
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PIL import Image
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")

from database import async_session
from database.models import AdDetail
from sqlalchemy import select, update

# ─── 설정 ────────────────────────────────────────────
ATLAS_MAX_W = 4096
ATLAS_MAX_H = 4096
MIN_IMAGES_FOR_ATLAS = 5   # 최소 이미지 수 (이하일 경우 아틀라스 생성 안 함)
MAX_SINGLE_IMAGE_KB = 100  # 100KB 이하만 대상
ATLAS_QUALITY = 80         # WebP 출력 품질
STORED_IMAGES_DIR = Path("stored_images")


# ─── 스캔 ────────────────────────────────────────────
async def scan_image_groups(channel_filter: str | None = None) -> dict[str, list[dict]]:
    """stored_images/ 내 소형 WebP 파일을 채널/날짜/카테고리별로 그룹화.

    Returns:
        {
            "facebook/20260220/element": [
                {"path": Path(...), "size_kb": 17.4, "rel": "stored_images/facebook/..."},
                ...
            ]
        }
    """
    groups: dict[str, list[dict]] = {}

    if not STORED_IMAGES_DIR.exists():
        logger.warning("stored_images/ 디렉토리가 없습니다")
        return groups

    for channel_dir in sorted(STORED_IMAGES_DIR.iterdir()):
        if not channel_dir.is_dir():
            continue
        channel_name = channel_dir.name
        if channel_filter and channel_name != channel_filter:
            continue

        for date_dir in sorted(channel_dir.iterdir()):
            if not date_dir.is_dir():
                continue

            for category_dir in sorted(date_dir.iterdir()):
                if not category_dir.is_dir():
                    continue
                category_name = category_dir.name

                group_key = f"{channel_name}/{date_dir.name}/{category_name}"
                files = []

                for fpath in sorted(category_dir.iterdir()):
                    if not fpath.is_file():
                        continue
                    if fpath.suffix.lower() != ".webp":
                        continue
                    # 아틀라스 파일 자체는 제외
                    if fpath.name.startswith("atlas_"):
                        continue

                    size_kb = fpath.stat().st_size / 1024
                    if size_kb > MAX_SINGLE_IMAGE_KB:
                        continue

                    rel_path = str(fpath.relative_to(Path("."))).replace("\\", "/")
                    files.append({
                        "path": fpath,
                        "size_kb": round(size_kb, 2),
                        "rel": rel_path,
                    })

                if len(files) >= MIN_IMAGES_FOR_ATLAS:
                    groups[group_key] = files

    return groups


# ─── 아틀라스 빌드 ──────────────────────────────────
def build_atlas(images: list[dict], output_path: Path) -> dict | None:
    """이미지 리스트로 아틀라스를 빌드. 메타데이터 dict 반환.

    Row-packing 알고리즘:
    - 왼쪽에서 오른쪽으로 배치, 폭 초과 시 다음 줄
    - 각 줄 높이 = 해당 줄 이미지 중 최대 높이

    Args:
        images: [{"path": Path, "rel": str, "size_kb": float}, ...]
        output_path: 아틀라스 출력 파일 경로

    Returns:
        {
            "stored_images/fb/.../file.webp": {
                "atlas": "stored_images/fb/.../atlas_element_0.webp",
                "x": 0, "y": 0, "w": 200, "h": 150
            }
        }
        None if atlas exceeds max dimensions or has no valid images.
    """
    # 1단계: 모든 이미지를 열어서 크기 파악
    loaded: list[tuple[dict, Image.Image]] = []
    for img_info in images:
        try:
            im = Image.open(img_info["path"])
            im.load()  # 실제 디코딩
            loaded.append((img_info, im))
        except Exception as e:
            logger.warning(f"이미지 열기 실패 (건너뜀): {img_info['path']} -- {e}")
            continue

    if len(loaded) < MIN_IMAGES_FOR_ATLAS:
        logger.debug(f"유효 이미지 {len(loaded)}개 < {MIN_IMAGES_FOR_ATLAS} -- 건너뜀")
        return None

    # 2단계: Row-packing 레이아웃 계산
    placements: list[tuple[dict, Image.Image, int, int]] = []  # (info, im, x, y)
    cursor_x = 0
    cursor_y = 0
    row_max_h = 0

    for img_info, im in loaded:
        w, h = im.size

        # 이미지 하나가 아틀라스 최대 크기를 초과하면 건너뜀
        if w > ATLAS_MAX_W or h > ATLAS_MAX_H:
            logger.warning(f"이미지 크기 초과 (건너뜀): {img_info['path']} ({w}x{h})")
            im.close()
            continue

        # 줄바꿈 필요
        if cursor_x + w > ATLAS_MAX_W:
            cursor_y += row_max_h
            cursor_x = 0
            row_max_h = 0

        # 세로 오버플로 체크
        if cursor_y + h > ATLAS_MAX_H:
            logger.warning(f"아틀라스 세로 한계 도달 -- 이후 이미지 건너뜀 ({len(placements)}개 배치됨)")
            im.close()
            # 나머지 이미지도 닫기
            for remaining_info, remaining_im in loaded[loaded.index((img_info, im)) + 1:]:
                remaining_im.close()
            break

        placements.append((img_info, im, cursor_x, cursor_y))
        cursor_x += w
        row_max_h = max(row_max_h, h)

    if len(placements) < MIN_IMAGES_FOR_ATLAS:
        for _, im, _, _ in placements:
            im.close()
        return None

    # 3단계: 아틀라스 캔버스 생성
    atlas_w = max(x + im.size[0] for _, im, x, _ in placements)
    atlas_h = max(y + im.size[1] for _, im, _, y in placements)

    atlas = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))
    metadata: dict[str, dict] = {}
    atlas_rel = str(output_path.relative_to(Path("."))).replace("\\", "/")

    for img_info, im, x, y in placements:
        # RGBA 변환 (일부 WebP가 RGB/P 모드일 수 있음)
        if im.mode != "RGBA":
            im = im.convert("RGBA")
        atlas.paste(im, (x, y))

        metadata[img_info["rel"]] = {
            "atlas": atlas_rel,
            "x": x,
            "y": y,
            "w": im.size[0],
            "h": im.size[1],
        }
        im.close()

    # 4단계: 아틀라스 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(str(output_path), "WEBP", quality=ATLAS_QUALITY)
    atlas_size_kb = output_path.stat().st_size / 1024
    atlas.close()

    logger.info(
        f"아틀라스 생성: {output_path.name} "
        f"({atlas_w}x{atlas_h}, {len(metadata)}개 이미지, {atlas_size_kb:.1f}KB)"
    )
    return metadata


def build_atlases_for_group(group_key: str, images: list[dict]) -> dict:
    """그룹 내 이미지들을 하나 이상의 아틀라스로 빌드.

    아틀라스가 4096x4096을 초과할 경우 여러 개로 분할.

    Returns:
        전체 메타데이터 dict (original_rel -> atlas info)
    """
    parts = group_key.split("/")
    if len(parts) >= 3:
        channel, date, category = parts[0], parts[1], parts[2]
    else:
        channel, date, category = parts[0], "unknown", "misc"

    all_metadata: dict = {}
    batch_idx = 0
    batch_start = 0

    while batch_start < len(images):
        # 이미지를 나눠서 배치 시도
        batch = images[batch_start:]
        output_dir = STORED_IMAGES_DIR / channel / date / category
        output_path = output_dir / f"atlas_{category}_{batch_idx}.webp"

        result = build_atlas(batch, output_path)
        if result is None:
            # 남은 이미지로 아틀라스를 만들 수 없음
            break

        all_metadata.update(result)
        # 배치된 이미지 수만큼 전진
        batch_start += len(result)
        batch_idx += 1

    return all_metadata


# ─── DB 업데이트 ─────────────────────────────────────
async def update_db_paths(metadata: dict) -> int:
    """ad_details의 creative_image_path를 아틀라스 형식으로 업데이트.

    기존: "stored_images/facebook/20260220/element/meta_card_0.webp"
    변경: "stored_images/facebook/20260220/element/atlas_element_0.webp#0,0,200,150"

    Returns:
        업데이트된 row 수
    """
    if not metadata:
        return 0

    updated = 0
    async with async_session() as session:
        for original_rel, atlas_info in metadata.items():
            # creative_image_path는 다양한 형식으로 저장될 수 있음
            # 1) stored_images/... (정방향 슬래시)
            # 2) stored_images\\... (역방향 슬래시 -- Windows)
            atlas_path_with_coords = (
                f"{atlas_info['atlas']}#{atlas_info['x']},{atlas_info['y']},"
                f"{atlas_info['w']},{atlas_info['h']}"
            )

            # 정방향 슬래시 기준 검색
            stmt = (
                update(AdDetail)
                .where(AdDetail.creative_image_path == original_rel)
                .values(creative_image_path=atlas_path_with_coords)
            )
            result = await session.execute(stmt)
            updated += result.rowcount

            # 역슬래시 버전도 체크
            backslash_rel = original_rel.replace("/", "\\")
            if backslash_rel != original_rel:
                stmt2 = (
                    update(AdDetail)
                    .where(AdDetail.creative_image_path == backslash_rel)
                    .values(creative_image_path=atlas_path_with_coords)
                )
                result2 = await session.execute(stmt2)
                updated += result2.rowcount

        await session.commit()

    return updated


# ─── 원본 삭제 ───────────────────────────────────────
def delete_originals(metadata: dict) -> int:
    """아틀라스에 포함된 원본 이미지 파일 삭제.

    Returns:
        삭제된 파일 수
    """
    deleted = 0
    for original_rel in metadata:
        fpath = Path(original_rel)
        if fpath.exists():
            try:
                fpath.unlink()
                deleted += 1
            except OSError as e:
                logger.warning(f"파일 삭제 실패: {fpath} -- {e}")
    return deleted


# ─── 메타데이터 JSON 저장 ──────────────────────────────
def save_metadata_json(group_key: str, metadata: dict):
    """그룹별 메타데이터를 JSON으로 저장.

    Output: stored_images/{channel}/{date}/atlas_{category}_meta.json
    """
    parts = group_key.split("/")
    if len(parts) >= 3:
        channel, date, category = parts[0], parts[1], parts[2]
    else:
        channel, date, category = parts[0], "unknown", "misc"

    json_path = STORED_IMAGES_DIR / channel / date / f"atlas_{category}_meta.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    logger.info(f"메타데이터 저장: {json_path}")


# ─── 메인 ────────────────────────────────────────────
async def main():
    import argparse
    parser = argparse.ArgumentParser(description="WebP 이미지 아틀라스 빌더")
    parser.add_argument("--dry-run", action="store_true", help="미리보기 모드 (변경 없음)")
    parser.add_argument("--channel", type=str, default=None, help="특정 채널만 처리")
    parser.add_argument("--no-delete", action="store_true", help="원본 파일 삭제하지 않음")
    args = parser.parse_args()

    logger.info("=== AdScope 이미지 아틀라스 빌더 시작 ===")

    # 1. 이미지 그룹 스캔
    groups = await scan_image_groups(channel_filter=args.channel)
    if not groups:
        logger.info("아틀라스 대상 이미지 그룹이 없습니다")
        return

    total_images = sum(len(files) for files in groups.values())
    total_size_kb = sum(f["size_kb"] for files in groups.values() for f in files)
    logger.info(
        f"스캔 완료: {len(groups)}개 그룹, "
        f"{total_images}개 이미지, "
        f"총 {total_size_kb:.1f}KB"
    )

    if args.dry_run:
        logger.info("[DRY-RUN] 변경 없이 종료합니다")
        for gk, files in groups.items():
            logger.info(f"  {gk}: {len(files)}개 이미지 ({sum(f['size_kb'] for f in files):.1f}KB)")
        return

    # 2. 그룹별 아틀라스 빌드
    total_atlased = 0
    total_db_updated = 0
    total_deleted = 0
    all_metadata: dict = {}

    for group_key, files in groups.items():
        logger.info(f"--- 그룹: {group_key} ({len(files)}개) ---")
        metadata = build_atlases_for_group(group_key, files)

        if not metadata:
            logger.warning(f"  아틀라스 생성 실패 (건너뜀)")
            continue

        total_atlased += len(metadata)
        all_metadata.update(metadata)

        # 3. 메타데이터 JSON 저장
        save_metadata_json(group_key, metadata)

        # 4. DB 경로 업데이트
        db_updated = await update_db_paths(metadata)
        total_db_updated += db_updated
        logger.info(f"  DB 업데이트: {db_updated}건")

        # 5. 원본 삭제
        if not args.no_delete:
            deleted = delete_originals(metadata)
            total_deleted += deleted
            logger.info(f"  원본 삭제: {deleted}개")

    # 6. 결과 요약
    logger.info("=== 완료 ===")
    logger.info(f"  아틀라스 포함 이미지: {total_atlased}개")
    logger.info(f"  DB 업데이트: {total_db_updated}건")
    logger.info(f"  원본 삭제: {total_deleted}개")

    # 전체 메타데이터도 루트에 저장
    if all_metadata:
        root_meta_path = STORED_IMAGES_DIR / "atlas_manifest.json"
        with open(root_meta_path, "w", encoding="utf-8") as f:
            json.dump(all_metadata, f, ensure_ascii=False, indent=2)
        logger.info(f"  전체 매니페스트: {root_meta_path}")


if __name__ == "__main__":
    asyncio.run(main())
