"""Backfill advertiser.website from ad landing URLs and known brand→domain mapping.

Usage: python scripts/backfill_advertiser_website.py [--dry-run]
"""
import asyncio
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from database import async_session
from sqlalchemy import text

# ── Known brand → official website mapping ──
KNOWN_BRANDS: dict[str, str] = {
    "삼성전자": "samsung.com",
    "삼성전자판매": "samsung.com",
    "삼성": "samsung.com",
    "삼성화재": "samsungfire.com",
    "삼성생명": "samsunglife.com",
    "삼성자산운용": "samsungfund.com",
    "삼성물산패션부문": "ssfshop.com",
    "삼성카드": "samsungcard.com",
    "LG전자": "lge.co.kr",
    "LG유플러스": "uplus.co.kr",
    "LG생활건강": "lgcare.com",
    "SK텔레콤": "sktelecom.com",
    "SKT": "sktelecom.com",
    "SK하이닉스": "skhynix.com",
    "SK이노베이션": "skinnovation.com",
    "현대자동차": "hyundai.com",
    "기아": "kia.com",
    "기아 EV": "kia.com",
    "대한항공": "koreanair.com",
    "아시아나항공": "flyasiana.com",
    "네이버웹툰": "webtoon.com",
    "카카오게임즈": "kakaogames.com",
    "넷플릭스서비시스코리아": "netflix.com",
    "쿠팡": "coupang.com",
    "무신사": "musinsa.com",
    "29CM": "29cm.co.kr",
    "G마켓": "gmarket.co.kr",
    "11번가": "11st.co.kr",
    "SSG닷컴": "ssg.com",
    "마켓컬리": "kurly.com",
    "배달의민족": "baemin.com",
    "토스": "toss.im",
    "직방": "zigbang.com",
    "야놀자": "yanolja.com",
    "여기어때": "goodchoice.kr",
    "한화": "hanwha.com",
    "한화생명": "hanwhalife.com",
    "한화손해보험": "hanwhadamage.co.kr",
    "코오롱인더스트리 FnC부문": "kolonmall.com",
    "롯데쇼핑": "lotteshopping.com",
    "롯데": "lotte.co.kr",
    "신세계": "shinsegae.com",
    "이마트": "emart.com",
    "CJ제일제당": "cj.co.kr",
    "CJ ENM": "cjenm.com",
    "오뚜기": "ottogi.co.kr",
    "농심": "nongshim.com",
    "풀무원": "pulmuone.co.kr",
    "아모레퍼시픽": "amorepacific.com",
    "LG생활건강": "lgcare.com",
    "올리브영": "oliveyoung.co.kr",
    "하이브": "hybecorp.com",
    "JYP": "jype.com",
    "SM엔터테인먼트": "smentertainment.com",
    "KB손해보험": "kbinsure.co.kr",
    "DB손해보험": "directdb.co.kr",
    "현대해상": "hi.co.kr",
    "메가스터디교육": "megastudy.net",
    "해커스어학연구소": "hackers.com",
    "코웨이": "coway.co.kr",
    "한국인삼공사": "kgc.co.kr",
    "한국존슨앤드존슨판매": "jnj.co.kr",
    "한국피앤지판매": "pg.co.kr",
    "밀리의 서재": "millie.co.kr",
    "비상교육": "visang.com",
    "오늘의집": "ohou.se",
    "초이코퍼레이션": "choisolution.com",
    "삼성액티브자산운용": "samsungfund.com",
    "삼성본병원": "samsungbonn.com",
    "오케이저축은행": "oksavingsbank.com",
    "천정대": "cjd.co.kr",
    "J&H": "jnh.co.kr",
    "나스미디어": "nasmedia.co.kr",
    "신용카드 사회공헌재단": "cardcsr.or.kr",
}

# ── Tracking/redirect URL patterns to skip ──
TRACKING_PATTERNS = [
    "adstransparency.google.com",
    "g.tivan.naver.com", "tivan.naver.com",
    "ader.naver.com", "adcr.naver.com",
    "searchad.naver.com", "ad.naver.com",
    "m.ad.search.naver.com", "siape.veta.naver.com",
    "ssl.pstatic.net",
    "ad.daum.net", "v.daum.net", "m.cafe.daum.net",
    "track.tiara.kakao.com",
    "facebook.com/ads", "business.facebook.com",
    "ads.tiktok.com",
    "googleads.g.doubleclick.net", "pagead2.googlesyndication.com",
    "play.google.com", "apps.apple.com",
]


def extract_domain(url: str) -> str | None:
    """Extract clean domain from URL, skipping tracking URLs."""
    if not url or not url.startswith("http"):
        return None
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Skip tracking domains
        for pattern in TRACKING_PATTERNS:
            if pattern in domain:
                return None
        # Remove www.
        if domain.startswith("www."):
            domain = domain[4:]
        # Skip empty or very short domains
        if not domain or len(domain) < 4:
            return None
        return domain
    except Exception:
        return None


async def main():
    dry_run = "--dry-run" in sys.argv
    updated = 0
    already_set = 0

    async with async_session() as session:
        # Get advertisers without website
        result = await session.execute(text("""
            SELECT id, name FROM advertisers
            WHERE website IS NULL OR website = ''
            ORDER BY id
        """))
        advertisers = result.fetchall()
        print(f"Advertisers without website: {len(advertisers)}")

        for aid, name in advertisers:
            website = None

            # 1. Check known brand mapping
            if name in KNOWN_BRANDS:
                website = KNOWN_BRANDS[name]

            # 2. Try to extract from ad URLs (most common direct URL)
            if not website:
                url_result = await session.execute(text("""
                    SELECT d.url, COUNT(*) as cnt
                    FROM ad_details d
                    WHERE d.advertiser_id = :aid
                      AND d.url IS NOT NULL AND d.url != ''
                      AND d.url LIKE 'http%'
                    GROUP BY d.url
                    ORDER BY cnt DESC
                    LIMIT 5
                """), {"aid": aid})

                domain_counts: dict[str, int] = {}
                for url_row in url_result.fetchall():
                    domain = extract_domain(url_row[0])
                    if domain:
                        domain_counts[domain] = domain_counts.get(domain, 0) + url_row[1]

                if domain_counts:
                    # Use the most common domain
                    best_domain = max(domain_counts, key=domain_counts.get)
                    website = best_domain

            # 3. Try facebook/meta page URL
            if not website:
                fb_result = await session.execute(text("""
                    SELECT d.url FROM ad_details d
                    JOIN ad_snapshots s ON s.id = d.snapshot_id
                    WHERE d.advertiser_id = :aid
                      AND s.channel = 'meta'
                      AND d.url LIKE '%facebook.com%'
                    LIMIT 1
                """), {"aid": aid})
                fb_row = fb_result.fetchone()
                if fb_row and fb_row[0]:
                    # Extract facebook page name
                    parsed = urlparse(fb_row[0])
                    path = parsed.path.strip("/")
                    if path and "/" not in path and len(path) > 2:
                        website = f"facebook.com/{path}"

            if website:
                if not dry_run:
                    await session.execute(
                        text("UPDATE advertisers SET website = :website WHERE id = :id"),
                        {"website": website, "id": aid}
                    )
                updated += 1
                if updated <= 30:
                    print(f"  [{aid}] {name} -> {website}")
            else:
                already_set += 1

        if not dry_run:
            await session.commit()

    print(f"\n{'=== DRY RUN ===' if dry_run else '=== DONE ==='}")
    print(f"  Updated: {updated}")
    print(f"  No URL found: {already_set}")


if __name__ == "__main__":
    asyncio.run(main())
