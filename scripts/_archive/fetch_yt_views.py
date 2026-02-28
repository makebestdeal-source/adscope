"""YouTube 채널 영상별 실제 조회수 수집 → 광고 소재 매칭 → CPV 기반 광고비 계산.

흐름:
1. DB에서 youtube_ads 채널 광고주 목록 로드
2. channel_stats에서 채널 URL 로드 (없으면 yt-dlp 검색으로 찾기)
3. yt-dlp로 채널 최근 영상 목록 + 조회수 수집
4. 광고 소재(ad_details)와 영상 제목 매칭
5. ad_details.extra_data에 view_count 저장
6. campaign rebuild 실행

Usage:
    python scripts/fetch_yt_views.py [--rebuild]
"""

import asyncio
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

import yt_dlp
from database import async_session
from sqlalchemy import text


# --- yt-dlp helpers ---

def _ydl_opts_flat():
    return {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "playlist_items": "1-50",
        "skip_download": True,
        "ignoreerrors": True,
    }


def _ydl_opts_full():
    return {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "playlist_items": "1-50",
        "skip_download": True,
        "ignoreerrors": True,
    }


def get_channel_videos(channel_url: str, max_videos: int = 50) -> list[dict]:
    """채널 URL에서 최근 영상 목록 + 조회수를 가져온다."""
    videos_url = channel_url.rstrip("/") + "/videos"
    opts = _ydl_opts_full()
    opts["playlist_items"] = f"1-{max_videos}"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(videos_url, download=False)
            if not info:
                return []
            entries = info.get("entries", []) or []
            result = []
            for e in entries:
                if e is None:
                    continue
                vid_id = e.get("id", "")
                # 썸네일: maxresdefault > hqdefault
                thumbnail = e.get("thumbnail") or ""
                if not thumbnail and vid_id:
                    thumbnail = f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"
                result.append({
                    "video_id": vid_id,
                    "title": e.get("title", ""),
                    "view_count": e.get("view_count") or 0,
                    "duration": e.get("duration") or 0,
                    "upload_date": e.get("upload_date", ""),
                    "like_count": e.get("like_count") or 0,
                    "thumbnail": thumbnail,
                    "channel_name": e.get("channel") or e.get("uploader") or "",
                })
            return result
    except Exception as exc:
        print(f"  [ERROR] {channel_url}: {exc}")
        return []


def search_channel_url(company_name: str) -> str | None:
    """회사 이름으로 YouTube 채널 검색."""
    search_queries = [
        f"ytsearch5:{company_name} 공식",
        f"ytsearch5:{company_name}",
    ]
    for query in search_queries:
        try:
            opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "skip_download": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)
                entries = info.get("entries", []) or []
                for e in entries:
                    if e is None:
                        continue
                    channel_url = e.get("channel_url") or e.get("uploader_url")
                    channel_name = (e.get("channel") or e.get("uploader") or "").lower()
                    company_lower = company_name.lower().replace(" ", "")
                    channel_clean = channel_name.replace(" ", "")
                    # 이름이 포함되면 채널로 판단
                    if company_lower in channel_clean or channel_clean in company_lower:
                        if channel_url:
                            return channel_url
                # 첫 번째 결과의 채널 URL 사용 (최선의 추정)
                if entries and entries[0]:
                    return entries[0].get("channel_url") or entries[0].get("uploader_url")
        except Exception:
            continue
    return None


def _normalize_text(text_str: str) -> str:
    """텍스트 정규화: 소문자 + 공백/특수문자 제거."""
    if not text_str:
        return ""
    return re.sub(r"[^가-힣a-z0-9]", "", text_str.lower())


def match_ads_to_videos(
    ad_texts: list[tuple[int, str]],  # (ad_detail_id, ad_text)
    videos: list[dict],
) -> dict[int, dict]:
    """광고 소재 텍스트와 영상 제목 매칭.

    Returns: {ad_detail_id: video_info} 매칭 결과
    """
    matched: dict[int, dict] = {}
    normalized_videos = []
    for v in videos:
        norm_title = _normalize_text(v["title"])
        normalized_videos.append((norm_title, v))

    for ad_id, ad_text in ad_texts:
        if not ad_text:
            continue
        norm_ad = _normalize_text(ad_text)
        if not norm_ad:
            continue

        best_score = 0
        best_video = None
        for norm_title, video in normalized_videos:
            if not norm_title:
                continue
            # 공통 부분문자열 비율로 매칭
            shorter = min(len(norm_ad), len(norm_title))
            if shorter < 3:
                continue
            # 한쪽이 다른쪽에 포함되면 높은 점수
            if norm_ad in norm_title or norm_title in norm_ad:
                score = shorter / max(len(norm_ad), len(norm_title))
                score = max(score, 0.6)  # 포함관계면 최소 0.6
            else:
                # 단어 단위 겹침
                ad_words = set(re.findall(r"[가-힣]{2,}|[a-z]{2,}|[0-9]+", norm_ad))
                title_words = set(re.findall(r"[가-힣]{2,}|[a-z]{2,}|[0-9]+", norm_title))
                if not ad_words or not title_words:
                    continue
                overlap = len(ad_words & title_words)
                score = overlap / max(len(ad_words), len(title_words))

            if score > best_score and score >= 0.3:
                best_score = score
                best_video = video

        if best_video:
            matched[ad_id] = {**best_video, "match_score": round(best_score, 3)}

    return matched


MIN_VIEWS_FOR_AD = 100_000  # 조회수 10만 이상 = 광고 소재로 간주


async def _download_thumbnail(url: str, video_id: str) -> str | None:
    """썸네일 다운로드 → WebP 저장, 경로 반환."""
    import aiohttp
    from pathlib import Path

    save_dir = Path("stored_images/youtube_channel")
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{video_id}.webp"

    if save_path.exists():
        return str(save_path)

    try:
        async with aiohttp.ClientSession() as client:
            async with client.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                img_bytes = await resp.read()

        # WebP 변환
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(img_bytes))
            img.save(str(save_path), "WEBP", quality=80)
        except Exception:
            # PIL 실패 시 원본 저장
            save_path = save_path.with_suffix(".jpg")
            save_path.write_bytes(img_bytes)

        return str(save_path)
    except Exception:
        return None


async def register_high_view_videos(session, adv_id: int, adv_name: str,
                                     videos: list[dict]) -> int:
    """조회수 10만+ 영상을 ad_details에 광고 소재로 등록.

    이미 등록된 video_id는 스킵 (중복 방지).
    Returns: 신규 등록 건수.
    """
    high_view_videos = [v for v in videos if v["view_count"] >= MIN_VIEWS_FOR_AD]
    if not high_view_videos:
        return 0

    # 이미 등록된 video_id 조회 (video_id + matched_video_id 모두 체크)
    existing = set()
    for col in ("$.video_id", "$.matched_video_id"):
        rows = (await session.execute(text(f"""
            SELECT json_extract(extra_data, '{col}') as vid
            FROM ad_details
            WHERE advertiser_id = :aid
            AND json_extract(extra_data, '{col}') IS NOT NULL
        """), {"aid": adv_id})).fetchall()
        for r in rows:
            if r[0]:
                existing.add(r[0])

    registered = 0
    for video in high_view_videos:
        vid = video["video_id"]
        if vid in existing:
            continue

        # 썸네일 다운로드
        img_path = await _download_thumbnail(video["thumbnail"], vid)

        # Persona M30 (기본)
        persona_row = (await session.execute(text(
            "SELECT id FROM personas WHERE code = 'M30'"
        ))).fetchone()
        persona_id = persona_row[0] if persona_row else 1

        # Keyword: 'youtube_channel'
        kw_row = (await session.execute(text(
            "SELECT id FROM keywords WHERE keyword = 'youtube_channel'"
        ))).fetchone()
        if not kw_row:
            await session.execute(text("""
                INSERT INTO keywords (keyword, industry_id, is_active)
                VALUES ('youtube_channel', 1, 1)
            """))
            kw_row = (await session.execute(text(
                "SELECT id FROM keywords WHERE keyword = 'youtube_channel'"
            ))).fetchone()
        kw_id = kw_row[0]

        # ad_snapshot 생성
        await session.execute(text("""
            INSERT INTO ad_snapshots
            (keyword_id, persona_id, device, channel, captured_at,
             page_url, screenshot_path, raw_html_path, ad_count, crawl_duration_ms)
            VALUES (:kw_id, :pid, 'pc', 'youtube_ads', datetime('now'),
                    :page_url, '', '', 1, 0)
        """), {
            "kw_id": kw_id,
            "pid": persona_id,
            "page_url": f"https://www.youtube.com/watch?v={vid}",
        })
        snap_id = (await session.execute(text("SELECT last_insert_rowid()"))).fetchone()[0]

        # extra_data
        extra = {
            "video_id": vid,
            "view_count": video["view_count"],
            "like_count": video["like_count"],
            "duration": video["duration"],
            "upload_date": video["upload_date"],
            "view_source": "youtube_channel_direct",
            "channel_name": video.get("channel_name", ""),
        }

        # ad_detail 생성
        await session.execute(text("""
            INSERT INTO ad_details
            (snapshot_id, advertiser_id, advertiser_name_raw, brand,
             ad_text, ad_description, position, url, display_url,
             ad_type, creative_image_path, extra_data,
             is_contact, persona_id, ad_format_type)
            VALUES (:snap_id, :adv_id, :name, :brand,
                    :title, :desc, 0, :url, :display_url,
                    'video', :img, :extra,
                    0, :pid, 'video')
        """), {
            "snap_id": snap_id,
            "adv_id": adv_id,
            "name": adv_name,
            "brand": adv_name,
            "title": video["title"],
            "desc": f"YouTube {adv_name} - {video['view_count']:,} views",
            "url": f"https://www.youtube.com/watch?v={vid}",
            "display_url": f"youtube.com/watch?v={vid}",
            "img": img_path or "",
            "extra": json.dumps(extra, ensure_ascii=False),
            "pid": persona_id,
        })

        registered += 1

    return registered


async def fetch_and_store():
    """메인: YouTube 조회수 수집 + 고조회수 영상 소재 등록 → DB 저장."""
    async with async_session() as session:
        # 1. YouTube 광고주 목록
        yt_advs = (await session.execute(text("""
            SELECT DISTINCT ad.advertiser_id, a.name
            FROM ad_details ad
            JOIN ad_snapshots snap ON snap.id = ad.snapshot_id
            JOIN advertisers a ON a.id = ad.advertiser_id
            WHERE snap.channel = 'youtube_ads'
            ORDER BY a.name
        """))).fetchall()
        print(f"YouTube advertisers: {len(yt_advs)}")

        # 2. channel_stats에서 채널 URL 로드
        channel_urls: dict[int, str] = {}
        for adv_id, name in yt_advs:
            cs = (await session.execute(text("""
                SELECT channel_url FROM channel_stats
                WHERE advertiser_id = :aid AND platform = 'youtube'
                AND channel_url IS NOT NULL AND channel_url != ''
            """), {"aid": adv_id})).fetchone()
            if cs:
                channel_urls[adv_id] = cs[0]

        print(f"Channels from DB: {len(channel_urls)}")

        # 3. 채널 URL 없는 광고주는 YouTube 검색
        for adv_id, name in yt_advs:
            if adv_id in channel_urls:
                continue
            print(f"  Searching channel for: {name}...", end=" ")
            url = search_channel_url(name)
            if url:
                channel_urls[adv_id] = url
                print(f"Found: {url}")
                # DB에도 저장
                await session.execute(text("""
                    INSERT OR IGNORE INTO channel_stats
                    (advertiser_id, platform, channel_url, subscribers, followers,
                     total_posts, total_views, avg_likes, avg_views, engagement_rate, collected_at)
                    VALUES (:aid, 'youtube', :url, 0, 0, 0, 0, 0, 0, 0, datetime('now'))
                """), {"aid": adv_id, "url": url})
            else:
                print("Not found")

        await session.commit()
        print(f"Total channels: {len(channel_urls)}")

        # 4. 각 채널에서 영상 조회수 수집
        all_videos: dict[int, list[dict]] = {}  # advertiser_id -> videos
        name_map = {adv_id: name for adv_id, name in yt_advs}

        for adv_id, channel_url in channel_urls.items():
            name = name_map.get(adv_id, "?")
            print(f"\nFetching videos: {name} ({channel_url})")
            videos = get_channel_videos(channel_url, max_videos=30)
            if videos:
                all_videos[adv_id] = videos
                total_views = sum(v["view_count"] for v in videos)
                short_vids = [v for v in videos if v["duration"] <= 120]
                short_views = sum(v["view_count"] for v in short_vids)
                print(f"  {len(videos)} videos | total={total_views:,} views")
                print(f"  Short (<=120s): {len(short_vids)} videos | {short_views:,} views")
            else:
                print("  No videos found")

        # 4.5. 조회수 10만+ 영상을 광고 소재로 직접 등록
        print("\n--- Registering high-view videos as ad creatives ---")
        total_registered = 0
        for adv_id, videos in all_videos.items():
            name = name_map.get(adv_id, "?")
            count = await register_high_view_videos(session, adv_id, name, videos)
            if count > 0:
                total_registered += count
                print(f"  {name}: {count} new creatives registered")
        await session.commit()
        print(f"  Total new creatives from channels: {total_registered}")

        # 5. 광고 소재와 영상 매칭
        print("\n--- Matching ads to videos ---")
        total_matched = 0
        total_unmatched = 0
        total_updated = 0

        for adv_id, name in yt_advs:
            # 해당 광고주의 ad_details 조회
            ads = (await session.execute(text("""
                SELECT ad.id, ad.ad_text, ad.extra_data
                FROM ad_details ad
                JOIN ad_snapshots snap ON snap.id = ad.snapshot_id
                WHERE snap.channel = 'youtube_ads'
                AND ad.advertiser_id = :aid
            """), {"aid": adv_id})).fetchall()

            if not ads:
                continue

            videos = all_videos.get(adv_id, [])

            if videos:
                # 매칭 시도
                ad_texts = [(r[0], r[1] or "") for r in ads]
                matched = match_ads_to_videos(ad_texts, videos)

                # 매칭 안 된 소재: 채널 짧은 영상 총 조회수를 전체 소재 수로 배분
                # (avg 사용 시 과대추정 문제 해소)
                short_vids = [v for v in videos if v["duration"] <= 120]
                if short_vids:
                    total_short_views = sum(v["view_count"] for v in short_vids)
                    # 매칭된 소재의 조회수 제외
                    matched_views = sum(matched[aid]["view_count"] for aid in matched)
                    remaining_views = max(0, total_short_views - matched_views)
                    unmatched_count = len(ads) - len(matched)
                    fallback_views = remaining_views // max(1, unmatched_count) if unmatched_count > 0 else 0
                else:
                    fallback_views = 0

                for ad_id, ad_text, extra_data_raw in ads:
                    extra = {}
                    if extra_data_raw:
                        if isinstance(extra_data_raw, str):
                            try:
                                extra = json.loads(extra_data_raw)
                            except Exception:
                                extra = {}
                        elif isinstance(extra_data_raw, dict):
                            extra = extra_data_raw

                    if ad_id in matched:
                        video = matched[ad_id]
                        extra["view_count"] = video["view_count"]
                        extra["matched_video_id"] = video["video_id"]
                        extra["matched_video_title"] = video["title"]
                        extra["match_score"] = video["match_score"]
                        extra["view_source"] = "youtube_channel_matched"
                        total_matched += 1
                    else:
                        # 매칭 안 됨 → 채널 짧은영상 총 조회수에서 배분
                        extra["view_count"] = fallback_views
                        extra["view_source"] = "youtube_channel_distributed"
                        total_unmatched += 1

                    await session.execute(text("""
                        UPDATE ad_details SET extra_data = :ed WHERE id = :aid
                    """), {"ed": json.dumps(extra, ensure_ascii=False), "aid": ad_id})
                    total_updated += 1

                matched_names = [matched[aid]["title"][:40] for aid in matched if aid in matched]
                print(f"  {name}: {len(ads)} ads | matched={len(matched)} unmatched={len(ads)-len(matched)} fallback={fallback_views:,}/creative")
                for ad_id in list(matched.keys())[:3]:
                    v = matched[ad_id]
                    print(f"    -> {v['title'][:50]} ({v['view_count']:,} views, score={v['match_score']})")
            else:
                # 채널 영상 없음 → view_count = 0 유지
                print(f"  {name}: {len(ads)} ads | no channel videos")
                total_unmatched += len(ads)

        await session.commit()
        print(f"\n=== Summary ===")
        print(f"  Matched: {total_matched} | Unmatched (avg used): {total_unmatched}")
        print(f"  Total updated: {total_updated}")

        # 6. 결과 확인: 광고주별 총 조회수 × CPV
        print(f"\n=== Estimated YouTube Ad Spend (CPV=50won) ===")
        for adv_id, name in yt_advs:
            rows = (await session.execute(text("""
                SELECT ad.extra_data
                FROM ad_details ad
                JOIN ad_snapshots snap ON snap.id = ad.snapshot_id
                WHERE snap.channel = 'youtube_ads'
                AND ad.advertiser_id = :aid
            """), {"aid": adv_id})).fetchall()

            total_views = 0
            creative_count = 0
            for r in rows:
                ed = r[0]
                if isinstance(ed, str):
                    try:
                        ed = json.loads(ed)
                    except Exception:
                        ed = {}
                elif not isinstance(ed, dict):
                    ed = {}
                vc = ed.get("view_count", 0)
                if vc:
                    total_views += vc
                    creative_count += 1

            if total_views > 0:
                # 조회수 × CPV (50원) = 총 광고비
                total_spend = total_views * 50
                monthly_spend = total_spend  # 이미 누적 조회수 기반
                print(f"  {name}: {creative_count} creatives | {total_views:,} total views | {total_spend/10000:,.0f}만원")


async def main():
    await fetch_and_store()

    # --rebuild 옵션 시 campaign rebuild
    if "--rebuild" in sys.argv:
        print("\n--- Rebuilding campaigns ---")
        from processor.campaign_builder import rebuild_campaigns_and_spend
        result = await rebuild_campaigns_and_spend(active_days=30)
        for k, v in result.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
