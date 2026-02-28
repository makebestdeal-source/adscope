"""Seed ad_product_master table with 60+ digital ad products.

Sources: navercorp.com, Google Ads Help, Meta for Business,
kakaobusiness.gitbook.io, TikTok for Business

Usage:
    python scripts/seed_ad_products.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_db, async_session
from database.models import AdProductMaster
from sqlalchemy import select


AD_PRODUCTS = [
    # ── 네이버 검색광고 ──
    ("naver_search", "naver_powerlink", "파워링크", "Powerlink", "search", "CPC",
     "키워드 검색 시 상단 노출되는 기본 검색광고"),
    ("naver_search", "naver_shopping_search", "쇼핑검색", "Shopping Search Ad", "shopping", "CPC",
     "쇼핑탭 상품 검색 광고"),
    ("naver_search", "naver_brand_search", "브랜드검색", "Brand Search", "search", "CPT",
     "브랜드 키워드 검색결과 단독 노출 프리미엄 상품"),
    ("naver_search", "naver_new_product_search", "신제품검색광고", "New Product Search", "search", "CPT",
     "일반 명사 키워드 검색결과 상단 노출 신규 출시용"),
    ("naver_search", "naver_content_search", "콘텐츠검색", "Content Search Ad", "search", "CPC",
     "제품/서비스 관련 정보 제공에 특화된 검색광고"),
    ("naver_search", "naver_place", "플레이스", "Place Ad", "search", "CPC",
     "지역성 키워드와 업체/매장 자동 매칭 지역 기반 광고"),
    ("naver_search", "naver_bizsite", "비즈사이트", "Biz Site", "search", "CPC",
     "검색결과 내 비즈사이트 영역 노출"),
    ("naver_search", "naver_searching_view", "서칭뷰", "Searching View", "search", "CPT",
     "키워드와 연관된 브랜딩 콘텐츠 독점 노출"),

    # ── 네이버 성과형 DA (GFA) ──
    ("naver_da", "naver_gfa_traffic", "성과형DA 인지도/트래픽", "GFA Traffic", "display", "CPM/CPC",
     "브랜드 인지도 제고 및 사이트 유입 극대화"),
    ("naver_da", "naver_gfa_conversion", "성과형DA 웹사이트전환", "GFA Conversion", "display", "CPA",
     "잠재고객의 제품 구매 유도에 효과적"),
    ("naver_da", "naver_gfa_app", "성과형DA 앱전환", "GFA App Install", "display", "CPI",
     "앱 설치 및 앱 내 행동 유도"),
    ("naver_da", "naver_gfa_shopping_dynamic", "쇼핑 다이내믹", "Shopping Dynamic", "shopping", "CPC",
     "유저 행동 데이터 기반 자동 소재 구성"),
    ("naver_da", "naver_gfa_shopping_news", "쇼핑 소식", "Shopping News", "shopping", "CPC",
     "직관적 프로모션 정보 노출로 구매 전환율 상승"),
    ("naver_da", "naver_gfa_video", "동영상 조회", "GFA Video View", "video", "CPV",
     "동영상을 통한 브랜드 메시지 전달"),
    ("naver_da", "naver_advoost_shopping", "ADVoost 쇼핑", "ADVoost Shopping", "shopping", "CPA",
     "AI가 광고 집행 프로세스 전반을 완전 자동화"),

    # ── 네이버 보장형 DA ──
    ("naver_da", "naver_home_premium", "홈 프리미엄", "Home Premium", "display", "CPT",
     "네이버 메인 최상단 타임보드/롤링보드 프리미엄 배치"),
    ("naver_da", "naver_fullscreen", "전면광고", "Fullscreen Ad", "display", "CPT",
     "화면 전체를 활용한 높은 주목도와 브랜딩"),
    ("naver_da", "naver_banner", "배너광고", "Banner Ad", "display", "CPM/CPT",
     "이미지, 동영상 등 다양한 소재로 서비스 전반 노출"),
    ("naver_da", "naver_video_guaranteed", "동영상광고(보장형)", "Guaranteed Video", "video", "CPM",
     "영상 소재 노출로 높은 주목도 확보"),
    ("naver_da", "naver_vertical", "버티컬 서비스광고", "Vertical Service", "display", "CPT",
     "특정 버티컬 서비스 지면에 집중 노출"),
    ("naver_da", "naver_family", "네이버 패밀리", "Naver Family", "display", "CPM",
     "웹툰, 스노우, 밴드, 페이 등 패밀리 서비스 노출"),
    ("naver_da", "naver_smart_channel", "스마트채널", "Smart Channel", "display", "CPC",
     "오디언스 타겟팅 피드 콘텐츠 광고"),

    # ── 유튜브/구글 ──
    ("youtube_ads", "youtube_trueview_instream", "트루뷰 인스트림", "TrueView In-Stream", "video", "CPV",
     "5초 후 스킵 가능, 30초 이상 시청 시 과금"),
    ("youtube_ads", "youtube_nonskip_instream", "논스킵 인스트림", "Non-Skippable In-Stream", "video", "CPM",
     "15초 이하 건너뛸 수 없는 동영상 광고"),
    ("youtube_ads", "youtube_bumper", "범퍼광고", "Bumper Ad", "video", "CPM",
     "6초 비스킵 브랜드 인지도용 광고"),
    ("youtube_ads", "youtube_infeed", "인피드 동영상", "In-Feed Video", "video", "CPC",
     "검색결과/관련 동영상 옆에 노출"),
    ("youtube_ads", "youtube_shorts", "쇼츠 광고", "Shorts Ad", "video", "CPV/CPM",
     "유튜브 쇼츠 피드 내 숏폼 광고"),
    ("youtube_ads", "youtube_masthead", "마스트헤드", "Masthead", "video", "CPH/CPM",
     "유튜브 메인 홈 최상단 프리미엄 광고"),
    ("youtube_ads", "youtube_outstream", "아웃스트림", "Outstream", "video", "vCPM",
     "제3자 사이트/앱에서 노출되는 동영상 광고"),
    ("youtube_ads", "youtube_demand_gen", "디맨드젠", "Demand Gen", "video", "CPA/CPC",
     "구 디스커버리, Gmail/YouTube/Google.com 프리미엄 배치"),
    ("google_gdn", "google_gdn_responsive", "GDN 반응형 디스플레이", "GDN Responsive Display", "display", "CPC/CPM",
     "ML 기반 이미지/텍스트 자동 조합 반응형 광고"),
    ("google_gdn", "google_gdn_standard", "GDN 표준 이미지", "GDN Standard Image", "display", "CPC/CPM",
     "고정 사이즈 이미지 배너 광고"),
    ("google_gdn", "google_search", "구글 검색광고", "Google Search Ad", "search", "CPC",
     "구글 검색결과 상단 텍스트 광고"),
    ("google_gdn", "google_demand_gen", "구글 디맨드젠", "Google Demand Gen", "display", "CPA",
     "Gmail, YouTube, Google.com 크로스 플랫폼 광고"),

    # ── 메타 (Facebook/Instagram) ──
    ("facebook", "meta_feed_image", "피드 이미지 광고", "Feed Image Ad", "social", "CPC/CPM",
     "Facebook/Instagram 피드 단일 이미지 광고"),
    ("facebook", "meta_feed_video", "피드 동영상 광고", "Feed Video Ad", "social", "CPV/CPM",
     "Facebook/Instagram 피드 동영상 광고"),
    ("facebook", "meta_feed_carousel", "캐러셀(슬라이드)", "Carousel Ad", "social", "CPC/CPM",
     "최대 10장 이미지/동영상 슬라이드 광고"),
    ("facebook", "meta_stories", "스토리 광고", "Stories Ad", "social", "CPM",
     "Facebook/Instagram 스토리 풀스크린 광고"),
    ("facebook", "meta_reels", "릴스 광고", "Reels Ad", "social", "CPV/CPM",
     "Instagram/Facebook 릴스 숏폼 광고"),
    ("facebook", "meta_collection", "컬렉션 광고", "Collection Ad", "social", "CPC",
     "메인 이미지+제품 카탈로그 조합 쇼핑 광고"),
    ("facebook", "meta_lead", "리드 광고", "Lead Ad", "social", "CPL",
     "앱/웹 이탈 없이 직접 리드 수집 폼"),
    ("facebook", "meta_instant_experience", "인스턴트 체험", "Instant Experience", "social", "CPM",
     "클릭 후 풀스크린 리치 미디어 경험"),
    ("instagram", "meta_explore", "탐색탭 광고", "Explore Ad", "social", "CPM",
     "Instagram 탐색(Explore) 탭 노출 광고"),
    ("instagram", "meta_shopping", "쇼핑 광고", "Shopping Ad", "social", "CPC",
     "Instagram 쇼핑탭 내 상품 카탈로그 광고"),
    ("instagram", "meta_branded_content", "브랜디드 콘텐츠", "Branded Content", "social", "CPM",
     "크리에이터 협업 브랜디드 콘텐츠 광고"),

    # ── 카카오 ──
    ("kakao_da", "kakao_bizboard", "비즈보드", "Bizboard", "display", "CPC/CPM",
     "카카오톡 네이티브 피드 광고 (오브젝트/썸네일/마스킹/텍스트형)"),
    ("kakao_da", "kakao_display_native", "디스플레이 네이티브", "Display Native", "display", "CPC/CPM",
     "카카오 서비스 내 네이티브 이미지 광고"),
    ("kakao_da", "kakao_display_video", "디스플레이 동영상", "Display Video", "video", "CPV",
     "카카오 서비스 내 동영상 광고"),
    ("kakao_da", "kakao_message", "카카오톡 메시지", "KakaoTalk Message", "message", "CPC",
     "카카오톡 채널 친구 대상 1:1 메시지 광고"),
    ("kakao_da", "kakao_channel", "카카오톡 채널", "KakaoTalk Channel", "display", "CPC",
     "카카오톡 채널 홍보 광고"),
    ("kakao_da", "kakao_keyword", "다음 키워드광고", "Daum Keyword Ad", "search", "CPC",
     "다음 검색결과 내 키워드 광고"),
    ("kakao_da", "kakao_brand_search", "다음 브랜드검색", "Daum Brand Search", "search", "CPT",
     "다음 브랜드 키워드 검색결과 단독 노출"),

    # ── 틱톡 ──
    ("tiktok_ads", "tiktok_topview", "TopView", "TopView", "social", "CPT",
     "앱 실행 시 풀스크린 5-60초 프리미엄 광고"),
    ("tiktok_ads", "tiktok_infeed", "인피드", "In-Feed Ad", "social", "CPC/CPM",
     "For You 피드 네이티브 동영상 광고"),
    ("tiktok_ads", "tiktok_spark", "Spark Ads", "Spark Ads", "social", "CPC/CPM",
     "기존 오가닉/크리에이터 콘텐츠 프로모션"),
    ("tiktok_ads", "tiktok_brand_takeover", "브랜드 테이크오버", "Brand Takeover", "social", "CPT",
     "앱 실행 시 3-5초 풀스크린 즉시 노출"),
    ("tiktok_ads", "tiktok_hashtag_challenge", "해시태그 챌린지", "Hashtag Challenge", "social", "Fixed",
     "UGC 기반 캠페인, Discover탭 랜딩"),
    ("tiktok_ads", "tiktok_branded_effect", "브랜디드 이펙트", "Branded Effect", "social", "Fixed",
     "커스텀 필터/AR 효과 스폰서십"),
    ("tiktok_ads", "tiktok_collection", "컬렉션", "Collection Ad", "social", "CPC",
     "제품 카탈로그 쇼케이스 광고"),

    # ── 네이버 쇼핑 ──
    ("naver_shopping", "naver_shopping_powerlink", "쇼핑검색 파워링크", "Shopping Powerlink", "shopping", "CPC",
     "네이버 쇼핑탭 검색결과 내 파워링크 광고"),
    ("naver_shopping", "naver_shopping_brand", "쇼핑 브랜드형", "Shopping Brand", "shopping", "CPT",
     "네이버 쇼핑 브랜드 전용 프리미엄 노출"),
]


async def main():
    await init_db()

    async with async_session() as s:
        # Check existing count
        result = await s.execute(select(AdProductMaster.id))
        existing = len(result.scalars().all())
        print(f"Existing ad products: {existing}")

        inserted = 0
        for row in AD_PRODUCTS:
            channel, code, name_ko, name_en, fmt, billing, desc = row
            # Check if exists
            exists = (await s.execute(
                select(AdProductMaster.id).where(
                    AdProductMaster.channel == channel,
                    AdProductMaster.product_code == code,
                )
            )).scalar_one_or_none()

            if exists:
                continue

            product = AdProductMaster(
                channel=channel,
                product_code=code,
                product_name_ko=name_ko,
                product_name_en=name_en,
                format_type=fmt,
                billing_type=billing,
                description=desc,
            )
            s.add(product)
            inserted += 1

        await s.commit()
        print(f"Inserted {inserted} new ad products (total: {existing + inserted})")


if __name__ == "__main__":
    asyncio.run(main())
