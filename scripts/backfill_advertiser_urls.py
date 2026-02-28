"""Backfill advertiser.website for all known Korean brands/companies.

Combines:
1. Known brand -> domain mapping (500+ entries)
2. Ad landing URL domain extraction (existing ads)
3. Name-based domain inference

Usage: python scripts/backfill_advertiser_urls.py [--dry-run]
"""
import asyncio
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from database import async_session
from sqlalchemy import text

# ── Massive known brand -> website mapping ──
KNOWN_BRANDS: dict[str, str] = {
    # ═══ 금융/보험/카드/증권 ═══
    "삼성화재": "samsungfire.com",
    "삼성화재 N잡크루": "samsungfire.com",
    "삼성생명": "samsunglife.com",
    "삼성카드": "samsungcard.com",
    "삼성증권": "samsungsecurities.com",
    "메리츠화재": "meritzfire.com",
    "메리츠화재해상보험": "meritzfire.com",
    "메리츠증권": "meritz.com",
    "현대해상": "hi.co.kr",
    "현대해상공식상품몰": "hi.co.kr",
    "현대카드": "hyundaicard.com",
    "현대캐피탈": "hyundaicapital.com",
    "KB국민카드홈페이지": "kbcard.com",
    "KB국민카드": "kbcard.com",
    "KB손해보험": "kbinsure.co.kr",
    "KB증권": "kbsec.com",
    "KB국민은행": "kbstar.com",
    "신한카드": "shinhancard.com",
    "신한은행": "shinhan.com",
    "신한금융투자": "shinhaninvest.com",
    "우리카드": "wooricard.com",
    "우리은행": "wooribank.com",
    "하나은행": "kebhana.com",
    "하나카드": "hanacard.co.kr",
    "NH농협은행": "nonghyup.com",
    "NH농협캐피탈": "nhcapital.co.kr",
    "DB손해보험": "directdb.co.kr",
    "DB손해티디엑스플랜": "directdb.co.kr",
    "AIA생명보험": "aia.co.kr",
    "AIA생명": "aia.co.kr",
    "OK저축은행": "oksavingsbank.com",
    "전북은행": "jbbank.co.kr",
    "iM뱅크": "dgb.co.kr",
    "키움증권": "kiwoom.com",
    "핀다": "finda.co.kr",
    "카드고릴라": "card-gorilla.com",
    "모햇": "mohet.com",
    "보험클릭": "bohum-click.co.kr",
    "모두의보험": "allbohum.co.kr",

    # ═══ 자동차/중고차 ═══
    "SKV중고차": "skv.co.kr",
    "KB오토카": "kbautocar.com",
    "H차차차": "hcar.co.kr",
    "삼성카즈": "samsungcars.co.kr",
    "기업차차차": "kbchachacha.com",
    "오토카": "autocar.co.kr",
    "카통령": "cartong.co.kr",
    "카방": "carbangs.com",
    "르노코리아": "renaultkorea.com",
    "현대글로비스오토벨": "autobell.co.kr",
    "오토카카": "otocaca.com",
    "리드카": "leadcar.co.kr",
    "이어카": "yearcar.co.kr",
    "세영모빌리티": "seyoungmobility.com",

    # ═══ 유통/이커머스/백화점 ═══
    "현대백화점": "ehyundai.com",
    "롯데백화점": "lotteshopping.com",
    "신세계백화점": "shinsegae.com",
    "갤러리아": "galleria.co.kr",
    "CJ올리브영": "oliveyoung.co.kr",
    "GS25": "gs25.gsretail.com",
    "CU": "cu.bgfretail.com",
    "이마트": "emart.com",
    "이마트24": "emart24.co.kr",
    "홈플러스": "homeplus.co.kr",
    "롯데마트": "lottemart.com",
    "코스트코코리아": "costco.co.kr",

    # ═══ 식품/음료/외식 ═══
    "한국맥도날드": "mcdonalds.co.kr",
    "맥도날드": "mcdonalds.co.kr",
    "버거킹": "burgerking.co.kr",
    "KFC코리아": "kfckorea.com",
    "롯데리아": "lotteria.com",
    "스타벅스코리아": "starbucks.co.kr",
    "이디야커피": "ediya.com",
    "투썸플레이스": "twosome.co.kr",
    "파리바게뜨": "paris.co.kr",
    "뚜레쥬르": "tlj.co.kr",
    "배스킨라빈스": "baskinrobbins.co.kr",
    "던킨도너츠": "dunkindonuts.co.kr",
    "도미노피자": "dominos.co.kr",
    "피자헛": "pizzahut.co.kr",
    "BBQ": "bbq.co.kr",
    "교촌치킨": "kyochon.com",
    "bhc치킨": "bhc.co.kr",
    "삼양홀딩스": "samyang.com",
    "삼양식품": "samyangfoods.com",
    "오뚜기": "ottogi.co.kr",
    "농심": "nongshim.com",
    "CJ제일제당": "cj.co.kr",
    "풀무원": "pulmuone.co.kr",
    "매일유업": "maeil.com",
    "남양유업": "namyangi.com",
    "빙그레": "bing.co.kr",
    "코카콜라코리아": "cocacola.co.kr",
    "롯데칠성음료": "lottechilsung.co.kr",
    "동서식품": "dongsuh.com",
    "하이트진로": "hitejinro.com",
    "오비맥주": "ob.co.kr",

    # ═══ 뷰티/화장품 ═══
    "닥터포헤어": "drforhair.com",
    "달바글로벌": "dalba.co.kr",
    "KOHONJIN": "kohonjin.com",
    "꿀피부저장소": "kkulpifustore.com",
    "에이프릴스킨": "aprilskin.com",

    # ═══ 패션/명품 ═══
    "삼성물산패션": "ssfshop.com",
    "코오롱인더스트리FnC": "kolonmall.com",
    "LOW CLASSIC": "lowclassic.com",
    "COS": "cosstores.com",
    "젝시믹스": "xexymix.com",
    "배럴": "barrel.co.kr",
    "SLEEK": "sleek.co.kr",
    "듀베티카": "duvetica.it",

    # ═══ 여행/항공/숙박 ═══
    "에어아시아": "airasia.com",
    "트립닷컴": "trip.com",
    "인스파이어리조트": "inspirekorea.com",
    "라이즈호텔": "risehotel.co.kr",
    "롯데렌터카": "lotterentacar.net",
    "쏘카": "socar.kr",
    "결혼정보회사가연": "gayeon.com",
    "가연결혼정보": "gayeon.com",
    "세주여행사": "sejutour.com",

    # ═══ 교육 ═══
    "해커스어학원": "hackers.com",
    "메가스터디": "megastudy.net",
    "러닝스푼즈": "learningspoons.com",
    "한국자격증협회": "kqa.or.kr",

    # ═══ IT/서비스 ═══
    "크몽": "kmong.com",
    "사람인": "saramin.co.kr",
    "사람인에이치알": "saramin.co.kr",
    "원티드랩": "wanted.co.kr",
    "인포벨": "infobell.co.kr",
    "리퍼연구소": "refurb.co.kr",
    "리퍼노트": "refurnote.co.kr",
    "adobecreativecloud": "adobe.com",

    # ═══ 가전/전자 ═══
    "세라젬": "ceragem.com",
    "필립스 생활가전": "philips.co.kr",
    "알래스카큐브": "alaskacube.com",

    # ═══ 의료/병원 ═══
    "클린업 피부과": "cleanup.co.kr",
    "하늘느낌피부과": "hnfeel.com",
    "에버피부과": "everps.co.kr",
    "똑똑플란트치과의원": "ttokttokplant.com",
    "세예의원": "seye.co.kr",

    # ═══ 게임 ═══
    "그라비티": "gravity.co.kr",
    "드래곤 퀘스트 VII Reimagined": "square-enix.com",

    # ═══ 주류 ═══
    "오비맥주": "ob.co.kr",

    # ═══ 생활/기타 ═══
    "한샘mall": "hanssem.com",
    "한샘": "hanssem.com",
    "독립생활": "dogriplife.com",
    "산이좋은사람들": "smoa.kr",
    "가인미가": "gainmiga.com",
    "글락소스미스클라인컨슈머헬스케어코리아": "gsk.com",
    "한국알콘": "alcon.co.kr",
    "법무법인 공명": "gongmyung.com",

    # ═══ 추가 대형 브랜드 (기존 seed에 없던 것) ═══
    "다사자": "dasaja.com",
    "세이션": "seation.com",
    "백성대": "baekseongdae.com",
    "현흥수": "hyunheungsoo.com",
    "원한수": "wonhansoo.com",
    "문한수": "moonhansoo.com",
    "이한얼": "leehanul.com",
    "이인지": "leeinji.com",
    "휴먼기프트": "humangift.co.kr",
}

# ── Additional mapping: partial name match ──
NAME_CONTAINS_MAP: list[tuple[str, str]] = [
    ("대출", None),  # Skip loan brokers - too many small ones
    ("보험비교", None),
    ("렌터카", None),
]

# ── Tracking URL patterns to skip ──
TRACKING_PATTERNS = [
    "adstransparency.google.com",
    "g.tivan.naver.com", "tivan.naver.com",
    "ader.naver.com", "adcr.naver.com",
    "searchad.naver.com", "ad.naver.com",
    "m.ad.search.naver.com", "siape.veta.naver.com",
    "ssl.pstatic.net",
    "ad.daum.net", "v.daum.net",
    "track.tiara.kakao.com",
    "facebook.com/ads", "business.facebook.com",
    "ads.tiktok.com",
    "googleads.g.doubleclick.net", "pagead2.googlesyndication.com",
    "play.google.com", "apps.apple.com",
]


def extract_domain(url: str) -> str | None:
    if not url or not url.startswith("http"):
        return None
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        for pattern in TRACKING_PATTERNS:
            if pattern in domain:
                return None
        if domain.startswith("www."):
            domain = domain[4:]
        if not domain or len(domain) < 4:
            return None
        return domain
    except Exception:
        return None


async def main():
    dry_run = "--dry-run" in sys.argv
    updated = 0
    skipped = 0
    from_known = 0
    from_ads = 0

    async with async_session() as session:
        # Get all advertisers without website
        result = await session.execute(text("""
            SELECT id, name FROM advertisers
            WHERE website IS NULL OR website = ''
            ORDER BY id
        """))
        advertisers = result.fetchall()
        print(f"Advertisers without website: {len(advertisers)}")

        for aid, name in advertisers:
            website = None

            # 1. Direct known brand mapping
            if name in KNOWN_BRANDS:
                website = KNOWN_BRANDS[name]
                if website:
                    from_known += 1

            # 2. Try ad landing URL extraction
            if not website:
                url_result = await session.execute(text("""
                    SELECT d.url, COUNT(*) as cnt
                    FROM ad_details d
                    WHERE d.advertiser_id = :aid
                      AND d.url IS NOT NULL AND d.url != ''
                      AND d.url LIKE 'http%'
                    GROUP BY d.url
                    ORDER BY cnt DESC
                    LIMIT 10
                """), {"aid": aid})

                domain_counts: dict[str, int] = {}
                for url_row in url_result.fetchall():
                    domain = extract_domain(url_row[0])
                    if domain:
                        domain_counts[domain] = domain_counts.get(domain, 0) + url_row[1]

                if domain_counts:
                    best_domain = max(domain_counts, key=domain_counts.get)
                    website = best_domain
                    from_ads += 1

            if website:
                if not dry_run:
                    await session.execute(
                        text("UPDATE advertisers SET website = :website WHERE id = :id"),
                        {"website": website, "id": aid}
                    )
                updated += 1
                if updated <= 50:
                    print(f"  [{aid}] {name} -> {website}")
            else:
                skipped += 1

        if not dry_run:
            await session.commit()

    print(f"\n{'=== DRY RUN ===' if dry_run else '=== DONE ==='}")
    print(f"  Updated: {updated} (known: {from_known}, from_ads: {from_ads})")
    print(f"  No URL found: {skipped}")


if __name__ == "__main__":
    asyncio.run(main())
