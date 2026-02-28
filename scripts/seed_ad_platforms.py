"""Seed ad_platforms table with Korean digital advertising platforms.

Usage: python scripts/seed_ad_platforms.py
"""
import asyncio
import json
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from database import async_session
from sqlalchemy import text

PLATFORMS = [
    # ── Major Search ──
    {"operator_name": "네이버(주)", "platform_name": "네이버", "service_name": "네이버 검색광고(SA)", "platform_type": "search", "url": "https://searchad.naver.com", "billing_types": ["CPC"], "is_self_serve": True, "monthly_reach": "MAU 4,600만", "data_source": "manual"},
    {"operator_name": "네이버(주)", "platform_name": "네이버", "service_name": "네이버 GFA(성과형 DA)", "platform_type": "display", "url": "https://gfa.naver.com", "billing_types": ["CPC", "CPM"], "is_self_serve": True, "monthly_reach": "MAU 4,600만", "data_source": "manual"},
    {"operator_name": "네이버(주)", "platform_name": "네이버", "service_name": "네이버 보장형 DA", "platform_type": "display", "url": "https://displayad.naver.com", "billing_types": ["CPT", "CPM"], "is_self_serve": False, "monthly_reach": "MAU 4,600만", "data_source": "manual"},
    {"operator_name": "네이버(주)", "platform_name": "네이버", "service_name": "네이버 쇼핑광고", "platform_type": "commerce", "url": "https://shopping.naver.com", "billing_types": ["CPC"], "is_self_serve": True, "data_source": "manual"},
    {"operator_name": "네이버(주)", "platform_name": "네이버", "service_name": "네이버 스마트플레이스", "platform_type": "local", "url": "https://new.smartplace.naver.com", "billing_types": ["CPC"], "is_self_serve": True, "data_source": "manual"},
    {"operator_name": "네이버(주)", "platform_name": "네이버", "service_name": "네이버 브랜드검색", "platform_type": "search", "url": "https://searchad.naver.com", "billing_types": ["CPT"], "is_self_serve": False, "data_source": "manual"},

    {"operator_name": "Google", "platform_name": "구글", "service_name": "구글 검색광고", "platform_type": "search", "url": "https://ads.google.com", "billing_types": ["CPC"], "is_self_serve": True, "monthly_reach": "점유율 35%", "data_source": "manual"},
    {"operator_name": "Google", "platform_name": "구글", "service_name": "구글 GDN(디스플레이 네트워크)", "platform_type": "display", "sub_type": "ad_network", "url": "https://ads.google.com", "billing_types": ["CPC", "CPM", "CPA"], "is_self_serve": True, "data_source": "manual"},
    {"operator_name": "Google", "platform_name": "유튜브", "service_name": "유튜브 광고(TrueView/Bumper)", "platform_type": "video", "url": "https://ads.google.com", "billing_types": ["CPV", "CPM"], "is_self_serve": True, "monthly_reach": "MAU 4,500만", "data_source": "manual"},
    {"operator_name": "Google", "platform_name": "구글", "service_name": "구글 AdMob", "platform_type": "mobile", "sub_type": "ad_network", "url": "https://admob.google.com", "billing_types": ["CPC", "CPM"], "is_self_serve": True, "data_source": "manual"},
    {"operator_name": "Google", "platform_name": "구글", "service_name": "구글 앱캠페인(UAC)", "platform_type": "mobile", "url": "https://ads.google.com", "billing_types": ["CPI", "CPA"], "is_self_serve": True, "data_source": "manual"},

    {"operator_name": "Meta", "platform_name": "메타", "service_name": "페이스북 광고", "platform_type": "social", "url": "https://business.facebook.com", "billing_types": ["CPC", "CPM", "CPA"], "is_self_serve": True, "monthly_reach": "MAU 1,100만", "data_source": "manual"},
    {"operator_name": "Meta", "platform_name": "메타", "service_name": "인스타그램 광고", "platform_type": "social", "url": "https://business.facebook.com", "billing_types": ["CPC", "CPM", "CPA"], "is_self_serve": True, "monthly_reach": "MAU 2,200만", "data_source": "manual"},
    {"operator_name": "Meta", "platform_name": "메타", "service_name": "메타 Audience Network", "platform_type": "display", "sub_type": "ad_network", "url": "https://business.facebook.com", "billing_types": ["CPM", "CPC"], "is_self_serve": True, "data_source": "manual"},

    {"operator_name": "카카오(주)", "platform_name": "카카오", "service_name": "카카오모먼트(비즈보드)", "platform_type": "display", "url": "https://moment.kakao.com", "billing_types": ["CPC", "CPM"], "is_self_serve": True, "monthly_reach": "MAU 4,800만", "data_source": "manual"},
    {"operator_name": "카카오(주)", "platform_name": "카카오", "service_name": "카카오 키워드광고", "platform_type": "search", "url": "https://keywordad.kakao.com", "billing_types": ["CPC"], "is_self_serve": True, "data_source": "manual"},
    {"operator_name": "카카오(주)", "platform_name": "카카오", "service_name": "카카오톡 채널 메시지", "platform_type": "messaging", "url": "https://business.kakao.com", "billing_types": ["CPS"], "is_self_serve": True, "data_source": "manual"},
    {"operator_name": "카카오(주)", "platform_name": "다음", "service_name": "다음 DA", "platform_type": "display", "url": "https://moment.kakao.com", "billing_types": ["CPM", "CPC"], "is_self_serve": True, "data_source": "manual"},

    {"operator_name": "ByteDance", "platform_name": "틱톡", "service_name": "틱톡 광고", "platform_type": "video", "url": "https://business.tiktok.com", "billing_types": ["CPC", "CPM", "CPV"], "is_self_serve": True, "monthly_reach": "MAU 1,000만", "data_source": "manual"},
    {"operator_name": "X Corp", "platform_name": "X(트위터)", "service_name": "X 광고", "platform_type": "social", "url": "https://ads.x.com", "billing_types": ["CPC", "CPM", "CPE"], "is_self_serve": True, "monthly_reach": "MAU 600만", "data_source": "manual"},
    {"operator_name": "Microsoft", "platform_name": "빙", "service_name": "Microsoft Advertising", "platform_type": "search", "url": "https://ads.microsoft.com", "billing_types": ["CPC"], "is_self_serve": True, "data_source": "manual"},
    {"operator_name": "Apple", "platform_name": "Apple", "service_name": "Apple Search Ads", "platform_type": "search", "sub_type": "app_store", "url": "https://searchads.apple.com", "billing_types": ["CPT"], "is_self_serve": True, "data_source": "openads"},
    {"operator_name": "LinkedIn", "platform_name": "링크드인", "service_name": "링크드인 광고", "platform_type": "social", "sub_type": "b2b", "url": "https://business.linkedin.com", "billing_types": ["CPC", "CPM"], "is_self_serve": True, "monthly_reach": "500만+", "data_source": "web_search"},
    {"operator_name": "Pinterest", "platform_name": "핀터레스트", "service_name": "핀터레스트 광고", "platform_type": "social", "url": "https://business.pinterest.com", "billing_types": ["CPC", "CPM"], "is_self_serve": True, "monthly_reach": "MAU 550만", "data_source": "web_search"},
    {"operator_name": "Snapchat", "platform_name": "스냅챗", "service_name": "스냅챗 광고", "platform_type": "social", "url": "https://forbusiness.snapchat.com", "billing_types": ["CPM"], "is_self_serve": True, "data_source": "web_search"},

    # ── Fintech / Super App ──
    {"operator_name": "비바리퍼블리카", "platform_name": "토스", "service_name": "토스애즈", "platform_type": "display", "sub_type": "fintech", "url": "https://tossads.toss.im", "billing_types": ["CPC", "CPM"], "is_self_serve": True, "monthly_reach": "MAU 2,100만", "data_source": "web_search"},

    # ── Hyper-local ──
    {"operator_name": "당근마켓(주)", "platform_name": "당근", "service_name": "당근 광고", "platform_type": "local", "url": "https://business.daangn.com", "billing_types": ["CPC", "CPM"], "is_self_serve": True, "monthly_reach": "MAU 1,800만", "data_source": "web_search"},

    # ── Commerce / Retail Media ──
    {"operator_name": "쿠팡(주)", "platform_name": "쿠팡", "service_name": "쿠팡애즈", "platform_type": "commerce", "url": "https://ads.coupang.com", "billing_types": ["CPC"], "is_self_serve": True, "monthly_reach": "MAU 3,100만", "data_source": "web_search"},
    {"operator_name": "쿠팡(주)", "platform_name": "쿠팡플레이", "service_name": "쿠팡플레이 광고", "platform_type": "ott", "url": "https://ads.coupang.com", "billing_types": ["CPM", "CPV"], "data_source": "web_search"},
    {"operator_name": "우아한형제들", "platform_name": "배달의민족", "service_name": "배민 광고", "platform_type": "commerce", "sub_type": "delivery", "url": "https://ceo.baemin.com", "billing_types": ["CPC", "CPT"], "is_self_serve": True, "data_source": "web_search"},
    {"operator_name": "위메프(주)", "platform_name": "위메프", "service_name": "위메프 광고", "platform_type": "commerce", "url": "https://wemakeprice.com", "billing_types": ["CPC", "CPM"], "data_source": "openads"},
    {"operator_name": "GS리테일", "platform_name": "GS SHOP", "service_name": "GS미디어믹스", "platform_type": "commerce", "url": "https://gsshop.com", "billing_types": ["CPM"], "data_source": "openads"},
    {"operator_name": "(주)무신사", "platform_name": "무신사", "service_name": "무신사 광고", "platform_type": "commerce", "sub_type": "fashion", "url": "https://musinsa.com", "billing_types": ["CPC", "CPM"], "is_self_serve": True, "monthly_reach": "MAU 1,000만+", "data_source": "web_search"},
    {"operator_name": "에이블리코퍼레이션", "platform_name": "에이블리", "service_name": "에이블리 광고", "platform_type": "commerce", "sub_type": "fashion", "url": "https://a-bly.com", "billing_types": ["CPC"], "is_self_serve": True, "monthly_reach": "MAU 918만", "data_source": "web_search"},
    {"operator_name": "카카오스타일", "platform_name": "지그재그", "service_name": "지그재그 광고", "platform_type": "commerce", "sub_type": "fashion", "url": "https://zigzag.kr", "billing_types": ["CPC"], "is_self_serve": True, "monthly_reach": "MAU 480만", "data_source": "web_search"},
    {"operator_name": "CJ올리브영", "platform_name": "올리브영", "service_name": "올리브영 광고", "platform_type": "commerce", "sub_type": "beauty", "url": "https://oliveyoung.co.kr", "billing_types": ["CPC", "CPM"], "monthly_reach": "MAU 905만", "data_source": "web_search"},
    {"operator_name": "컬리(주)", "platform_name": "마켓컬리", "service_name": "컬리 광고", "platform_type": "commerce", "sub_type": "grocery", "url": "https://kurly.com", "billing_types": ["CPM"], "data_source": "web_search"},
    {"operator_name": "버킷플레이스", "platform_name": "오늘의집", "service_name": "오늘의집 광고", "platform_type": "commerce", "sub_type": "interior", "url": "https://ohou.se", "billing_types": ["CPC", "CPM"], "data_source": "web_search"},
    {"operator_name": "SK플래닛", "platform_name": "11번가", "service_name": "11번가 광고", "platform_type": "commerce", "url": "https://ads.11st.co.kr", "billing_types": ["CPC"], "is_self_serve": True, "data_source": "web_search"},
    {"operator_name": "이베이코리아", "platform_name": "지마켓/옥션", "service_name": "G마켓 광고", "platform_type": "commerce", "url": "https://gmarket.co.kr", "billing_types": ["CPC", "CPM"], "is_self_serve": True, "data_source": "web_search"},
    {"operator_name": "야놀자(주)", "platform_name": "야놀자", "service_name": "야놀자 광고", "platform_type": "commerce", "sub_type": "travel", "url": "https://yanolja.com", "billing_types": ["CPC"], "data_source": "web_search"},
    {"operator_name": "여기어때컴퍼니", "platform_name": "여기어때", "service_name": "여기어때 광고", "platform_type": "commerce", "sub_type": "travel", "url": "https://goodchoice.kr", "billing_types": ["CPC"], "data_source": "web_search"},
    {"operator_name": "딜리버리히어로", "platform_name": "요기요", "service_name": "요기요 광고", "platform_type": "commerce", "sub_type": "delivery", "url": "https://ceo.yogiyo.co.kr", "billing_types": ["CPC", "CPT"], "data_source": "web_search"},
    {"operator_name": "SSG.COM", "platform_name": "SSG닷컴", "service_name": "SSG 광고", "platform_type": "commerce", "url": "https://ssg.com", "billing_types": ["CPC", "CPM"], "data_source": "web_search"},

    # ── Media Rep ──
    {"operator_name": "나스미디어(KT)", "platform_name": "나스미디어", "service_name": "NAP(나스애드플랫폼)", "platform_type": "programmatic", "sub_type": "media_rep", "url": "https://nasadplatform.com", "billing_types": ["CPM", "CPC"], "monthly_reach": "13,000+ 매체", "data_source": "web_search", "description": "국내 점유율 44% 미디어렙"},
    {"operator_name": "메조미디어(CJ)", "platform_name": "메조미디어", "service_name": "메조미디어", "platform_type": "programmatic", "sub_type": "media_rep", "url": "https://mezzomedia.co.kr", "billing_types": ["CPM", "CPC"], "data_source": "web_search", "description": "국내 점유율 27% 미디어렙"},
    {"operator_name": "인크로스(SK)", "platform_name": "인크로스", "service_name": "인크로스", "platform_type": "programmatic", "sub_type": "media_rep", "url": "https://incross.com", "billing_types": ["CPM", "CPC"], "data_source": "web_search", "description": "국내 점유율 18% 미디어렙"},
    {"operator_name": "DMC미디어(SBS)", "platform_name": "DMC미디어", "service_name": "DMC미디어", "platform_type": "programmatic", "sub_type": "media_rep", "url": "https://dmcreport.co.kr", "billing_types": ["CPM"], "data_source": "web_search", "description": "국내 점유율 11% 미디어렙"},
    {"operator_name": "모비데이즈(주)", "platform_name": "모비데이즈", "service_name": "모비데이즈", "platform_type": "programmatic", "sub_type": "media_rep", "url": "https://mobidays.com", "data_source": "web_search"},
    {"operator_name": "KT그룹", "platform_name": "플레이디", "service_name": "플레이디", "platform_type": "programmatic", "sub_type": "media_rep", "url": "https://playd.com", "data_source": "web_search", "description": "틱톡 공식 리셀러"},

    # ── Programmatic DSP ──
    {"operator_name": "NHN(주)", "platform_name": "NHN AD", "service_name": "에이스트레이더(ACE Trader)", "platform_type": "programmatic", "sub_type": "dsp", "url": "https://acetrader.co.kr", "billing_types": ["CPC", "CPM"], "is_self_serve": True, "data_source": "web_search"},
    {"operator_name": "엔서치마케팅", "platform_name": "모비온", "service_name": "모비온", "platform_type": "programmatic", "sub_type": "dsp", "url": "https://mobon.net", "billing_types": ["CPC"], "is_self_serve": True, "monthly_reach": "200+ 매체", "data_source": "web_search"},
    {"operator_name": "와이더플래닛", "platform_name": "타겟팅게이츠", "service_name": "타겟팅게이츠", "platform_type": "programmatic", "sub_type": "dsp", "url": "https://targetinggates.com", "billing_types": ["CPC", "CPM"], "data_source": "web_search", "description": "카드사 결제 데이터 결합"},
    {"operator_name": "Criteo", "platform_name": "크리테오", "service_name": "크리테오", "platform_type": "programmatic", "sub_type": "dsp", "url": "https://criteo.com/kr", "billing_types": ["CPC"], "data_source": "web_search", "description": "글로벌 커머스 DSP/리타겟팅"},
    {"operator_name": "The Trade Desk", "platform_name": "더트레이드데스크", "service_name": "TTD", "platform_type": "programmatic", "sub_type": "dsp", "url": "https://thetradedesk.com", "billing_types": ["CPM"], "data_source": "web_search"},
    {"operator_name": "Amazon", "platform_name": "아마존", "service_name": "Amazon DSP", "platform_type": "programmatic", "sub_type": "dsp", "url": "https://advertising.amazon.com", "billing_types": ["CPM"], "data_source": "web_search"},

    # ── Ad Network ──
    {"operator_name": "클릭몬(주)", "platform_name": "클릭몬", "service_name": "클릭몬", "platform_type": "display", "sub_type": "ad_network", "url": "https://clickmon.co.kr", "billing_types": ["CPC"], "data_source": "web_search", "description": "국내 최대 네트워크 배너"},
    {"operator_name": "NHN(주)", "platform_name": "NHN AD", "service_name": "NHN AD 네트워크", "platform_type": "display", "sub_type": "ad_network", "url": "https://nhn-ad.com", "billing_types": ["CPC", "CPM"], "data_source": "openads"},
    {"operator_name": "NHN(주)", "platform_name": "NHN AD", "service_name": "크로스타겟", "platform_type": "display", "sub_type": "retargeting", "url": "https://nhn-ad.com", "billing_types": ["CPC", "CPM"], "data_source": "openads", "description": "리타겟팅 광고"},
    {"operator_name": "카울리(FSN)", "platform_name": "카울리", "service_name": "카울리", "platform_type": "mobile", "sub_type": "ad_network", "url": "https://cauly.net", "billing_types": ["CPC", "CPM"], "data_source": "web_search"},

    # ── SSP ──
    {"operator_name": "ADOP", "platform_name": "ADOP", "service_name": "COMPASS", "platform_type": "programmatic", "sub_type": "ssp", "url": "https://adop.cc", "billing_types": ["CPM"], "data_source": "web_search", "description": "Google Certified Partner"},
    {"operator_name": "TPMN", "platform_name": "TPMN", "service_name": "TPMN", "platform_type": "programmatic", "sub_type": "ssp", "url": "https://tpmn.co.kr", "billing_types": ["CPM"], "data_source": "web_search", "description": "AI 기반 모바일 SSP"},
    {"operator_name": "리얼클릭", "platform_name": "리얼클릭", "service_name": "Real SSP", "platform_type": "programmatic", "sub_type": "ssp", "url": "https://realclick.co.kr", "billing_types": ["CPM"], "data_source": "web_search"},
    {"operator_name": "PubMatic", "platform_name": "PubMatic", "service_name": "PubMatic", "platform_type": "programmatic", "sub_type": "ssp", "url": "https://pubmatic.com", "billing_types": ["CPM"], "data_source": "web_search", "description": "19개 한국 언론사 연동"},
    {"operator_name": "Magnite", "platform_name": "Magnite", "service_name": "Magnite(구 Rubicon)", "platform_type": "programmatic", "sub_type": "ssp", "url": "https://magnite.com", "billing_types": ["CPM"], "data_source": "web_search"},
    {"operator_name": "Teads", "platform_name": "Teads", "service_name": "Teads 인리드 비디오", "platform_type": "video", "sub_type": "ssp", "url": "https://teads.com", "billing_types": ["CPM", "CPV"], "data_source": "web_search"},

    # ── Reward / Offerwall ──
    {"operator_name": "엔비티(주)", "platform_name": "캐시슬라이드", "service_name": "캐시슬라이드", "platform_type": "reward", "sub_type": "offerwall", "url": "https://cashslide.co", "billing_types": ["CPI", "CPA"], "monthly_reach": "2,700만 누적", "data_source": "web_search"},
    {"operator_name": "엔비티(주)", "platform_name": "애디슨", "service_name": "애디슨 오퍼월", "platform_type": "reward", "sub_type": "offerwall", "url": "https://adison.co", "billing_types": ["CPI", "CPA"], "data_source": "web_search", "description": "No.1 오퍼월 네트워크"},
    {"operator_name": "버즈빌(주)", "platform_name": "버즈빌", "service_name": "버즈빌", "platform_type": "reward", "sub_type": "offerwall", "url": "https://buzzvil.com", "billing_types": ["CPC", "CPI"], "data_source": "web_search"},
    {"operator_name": "IGAWorks", "platform_name": "애드팝콘", "service_name": "애드팝콘", "platform_type": "reward", "sub_type": "offerwall", "url": "https://adpopcorn.com", "billing_types": ["CPI", "CPE"], "monthly_reach": "12,000+ 파트너", "data_source": "web_search"},

    # ── OTT ──
    {"operator_name": "넷플릭스서비시스코리아", "platform_name": "넷플릭스", "service_name": "넷플릭스 광고 요금제", "platform_type": "ott", "url": "https://netflix.com", "billing_types": ["CPM"], "monthly_reach": "MAU 1,200만+", "data_source": "web_search"},
    {"operator_name": "티빙(주)", "platform_name": "티빙", "service_name": "티빙 광고", "platform_type": "ott", "url": "https://tving.com", "billing_types": ["CPM", "CPV"], "data_source": "web_search"},
    {"operator_name": "콘텐츠웨이브", "platform_name": "웨이브", "service_name": "웨이브 광고", "platform_type": "ott", "url": "https://wavve.com", "billing_types": ["CPM", "CPV"], "data_source": "web_search"},

    # ── Video / Streaming ──
    {"operator_name": "SOOP(주)", "platform_name": "SOOP(아프리카TV)", "service_name": "SOOP 광고", "platform_type": "video", "sub_type": "streaming", "url": "https://adv.afreecatv.com", "billing_types": ["CPM", "CPV"], "data_source": "web_search"},
    {"operator_name": "Twitch(Amazon)", "platform_name": "트위치", "service_name": "트위치 광고", "platform_type": "video", "sub_type": "streaming", "url": "https://twitchadvertising.tv", "billing_types": ["CPM", "CPV"], "data_source": "openads"},

    # ── Audio ──
    {"operator_name": "카카오(주)", "platform_name": "멜론", "service_name": "멜론 광고", "platform_type": "audio", "url": "https://melon.com", "billing_types": ["CPM"], "data_source": "web_search", "description": "국내 음원 1위"},
    {"operator_name": "Spotify", "platform_name": "스포티파이", "service_name": "스포티파이 광고", "platform_type": "audio", "url": "https://ads.spotify.com", "billing_types": ["CPM"], "data_source": "web_search"},
    {"operator_name": "팟빵(주)", "platform_name": "팟빵", "service_name": "팟빵 오디오 광고", "platform_type": "audio", "url": "https://podbbang.com", "billing_types": ["CPL"], "data_source": "openads"},
    {"operator_name": "딜로(주)", "platform_name": "딜로", "service_name": "딜로 프로그래매틱 오디오", "platform_type": "audio", "sub_type": "programmatic", "url": "https://dilo.co.kr", "billing_types": ["CPM"], "data_source": "web_search"},
    {"operator_name": "지니뮤직", "platform_name": "지니", "service_name": "지니뮤직 광고", "platform_type": "audio", "url": "https://genie.co.kr", "billing_types": ["CPM"], "data_source": "web_search"},
    {"operator_name": "NHN벅스", "platform_name": "벅스", "service_name": "벅스 광고", "platform_type": "audio", "url": "https://bugs.co.kr", "billing_types": ["CPM"], "data_source": "web_search"},
    {"operator_name": "플로(SKT)", "platform_name": "FLO", "service_name": "FLO 광고", "platform_type": "audio", "url": "https://floimusic.com", "billing_types": ["CPM"], "data_source": "web_search"},

    # ── Mobile Game ──
    {"operator_name": "Unity Technologies", "platform_name": "유니티", "service_name": "Unity Ads", "platform_type": "mobile", "sub_type": "game", "url": "https://unity.com", "billing_types": ["CPV", "CPI"], "data_source": "web_search"},
    {"operator_name": "AppLovin", "platform_name": "앱러빈", "service_name": "AppLovin MAX", "platform_type": "mobile", "sub_type": "game", "url": "https://applovin.com", "billing_types": ["CPI", "CPM"], "data_source": "web_search"},
    {"operator_name": "Unity(ironSource)", "platform_name": "아이언소스", "service_name": "LevelPlay", "platform_type": "mobile", "sub_type": "game", "url": "https://ironsource.com", "billing_types": ["CPI"], "data_source": "web_search"},

    # ── IPTV / CTV ──
    {"operator_name": "LG유플러스", "platform_name": "U+tv", "service_name": "U+AD", "platform_type": "display", "sub_type": "iptv", "url": "https://uplus.co.kr", "billing_types": ["CPM"], "data_source": "web_search"},
    {"operator_name": "SK브로드밴드", "platform_name": "Btv", "service_name": "Btv 광고", "platform_type": "display", "sub_type": "iptv", "url": "https://skbroadband.com", "billing_types": ["CPM"], "data_source": "web_search"},
    {"operator_name": "KT", "platform_name": "올레tv", "service_name": "올레tv 광고", "platform_type": "display", "sub_type": "iptv", "url": "https://kt.com", "billing_types": ["CPM"], "data_source": "web_search"},
    {"operator_name": "삼성전자", "platform_name": "Samsung TV Plus", "service_name": "삼성 Ads", "platform_type": "display", "sub_type": "ctv", "url": "https://samsung.com", "billing_types": ["CPM"], "data_source": "web_search"},

    # ── Map / Local ──
    {"operator_name": "SKT", "platform_name": "T맵", "service_name": "T맵 광고", "platform_type": "local", "url": "https://tmap.co.kr", "billing_types": ["CPM", "CPC"], "monthly_reach": "점유율 35%", "data_source": "web_search"},
    {"operator_name": "카카오(주)", "platform_name": "카카오맵", "service_name": "카카오맵 광고", "platform_type": "local", "url": "https://map.kakao.com", "billing_types": ["CPC"], "data_source": "web_search"},

    # ── Affiliate ──
    {"operator_name": "링크프라이스(주)", "platform_name": "링크프라이스", "service_name": "링크프라이스", "platform_type": "affiliate", "url": "https://linkprice.com", "billing_types": ["CPS", "CPA"], "data_source": "web_search", "description": "국내 제휴마케팅 선두"},
    {"operator_name": "쿠팡(주)", "platform_name": "쿠팡", "service_name": "쿠팡파트너스", "platform_type": "affiliate", "url": "https://partners.coupang.com", "billing_types": ["CPS"], "data_source": "web_search"},
    {"operator_name": "텐핑(주)", "platform_name": "텐핑", "service_name": "텐핑", "platform_type": "affiliate", "url": "https://tenping.kr", "billing_types": ["CPS", "CPA"], "data_source": "web_search"},
    {"operator_name": "오드엠(주)", "platform_name": "애드픽", "service_name": "애드픽", "platform_type": "affiliate", "url": "https://adpick.co.kr", "billing_types": ["CPS", "CPI"], "data_source": "web_search"},

    # ── Influencer ──
    {"operator_name": "레뷰코퍼레이션", "platform_name": "레뷰", "service_name": "레뷰", "platform_type": "social", "sub_type": "influencer", "url": "https://revu.net", "billing_types": ["CPA"], "monthly_reach": "110만 인플루언서", "data_source": "web_search"},

    # ── Portal ──
    {"operator_name": "SK커뮤니케이션즈", "platform_name": "네이트", "service_name": "네이트 브랜드탭", "platform_type": "display", "sub_type": "portal", "url": "https://nate.com", "billing_types": ["CPM", "CPT"], "data_source": "openads"},
    {"operator_name": "드림위즈(주)", "platform_name": "드림위즈", "service_name": "드림위즈 광고", "platform_type": "display", "sub_type": "portal", "url": "https://dreamwiz.com", "billing_types": ["CPM"], "data_source": "openads"},

    # ── Community / Content ──
    {"operator_name": "VCNC(NHN)", "platform_name": "비트윈", "service_name": "비트윈 광고", "platform_type": "display", "sub_type": "app", "url": "https://between.us", "billing_types": ["CPC", "CPM"], "data_source": "openads"},
    {"operator_name": "글로우픽(주)", "platform_name": "글로우픽", "service_name": "글로우픽 광고", "platform_type": "display", "sub_type": "beauty", "url": "https://glowpick.com", "billing_types": ["CPC", "CPM"], "data_source": "openads"},
    {"operator_name": "버드뷰(주)", "platform_name": "화해", "service_name": "화해 광고", "platform_type": "display", "sub_type": "beauty", "url": "https://hwahae.co.kr", "billing_types": ["CPC", "CPM"], "data_source": "openads"},
    {"operator_name": "(주)캐시워크", "platform_name": "캐시워크", "service_name": "캐시워크 광고", "platform_type": "reward", "url": "https://cashwalk.co", "billing_types": ["CPC", "CPI"], "data_source": "openads"},

    # ── DOOH ──
    {"operator_name": "이노션(현대)", "platform_name": "이노션 DOOH", "service_name": "코엑스 K-POP스퀘어 등", "platform_type": "dooh", "url": "https://innocean.com", "billing_types": ["CPT"], "data_source": "web_search"},
    {"operator_name": "제일기획(삼성)", "platform_name": "제일기획 DOOH", "service_name": "삼성동 미디어파사드 등", "platform_type": "dooh", "url": "https://cheil.com", "billing_types": ["CPT"], "data_source": "web_search"},
    {"operator_name": "옥쇼(주)", "platform_name": "옥쇼", "service_name": "옥쇼 셀프서비스 OOH", "platform_type": "dooh", "url": "https://oksho.com", "billing_types": ["CPT"], "is_self_serve": True, "data_source": "web_search"},

    # ── App Store ──
    {"operator_name": "원스토어(주)", "platform_name": "원스토어", "service_name": "원스토어 광고", "platform_type": "mobile", "sub_type": "app_store", "url": "https://onestore.co.kr", "billing_types": ["CPC", "CPI"], "data_source": "web_search", "description": "통신3사 합작 앱스토어"},

    # ── Line ──
    {"operator_name": "LY Corp", "platform_name": "LINE", "service_name": "LINE 공식계정 광고", "platform_type": "messaging", "url": "https://linebiz.com", "billing_types": ["CPC", "CPM"], "data_source": "openads"},

    # ── AdTech Solutions ──
    {"operator_name": "에코마케팅", "platform_name": "에코마케팅", "service_name": "에코마케팅", "platform_type": "programmatic", "sub_type": "agency", "url": "https://ecomkt.com", "data_source": "web_search"},
    {"operator_name": "매드업(주)", "platform_name": "매드업", "service_name": "Lever", "platform_type": "programmatic", "sub_type": "adtech", "url": "https://madup.com", "billing_types": ["CPM"], "data_source": "web_search"},
    {"operator_name": "와이즈버즈(주)", "platform_name": "와이즈버즈", "service_name": "와이즈버즈", "platform_type": "programmatic", "sub_type": "adtech", "url": "https://wisebirds.ai", "billing_types": ["CPC", "CPM"], "data_source": "web_search"},
    {"operator_name": "이엠넷(주)", "platform_name": "이엠넷", "service_name": "이엠넷", "platform_type": "programmatic", "sub_type": "agency", "url": "https://emnet.co.kr", "data_source": "web_search"},

    # ── NHN additional ──
    {"operator_name": "NHN(주)", "platform_name": "NHN AD", "service_name": "타겟픽 비디오", "platform_type": "video", "sub_type": "programmatic", "url": "https://nhn-ad.com", "billing_types": ["CPV", "CPM"], "data_source": "openads"},
    {"operator_name": "NHN(주)", "platform_name": "NHN AD", "service_name": "링크ADX", "platform_type": "programmatic", "sub_type": "ad_exchange", "url": "https://nhn-ad.com", "billing_types": ["CPM"], "data_source": "openads"},
    {"operator_name": "NHN(주)", "platform_name": "페이코", "service_name": "페이코 쿠폰 캠페인", "platform_type": "reward", "sub_type": "fintech", "url": "https://payco.com", "billing_types": ["CPA"], "data_source": "openads"},

    # ── InMobi ──
    {"operator_name": "InMobi", "platform_name": "인모비", "service_name": "인모비", "platform_type": "mobile", "sub_type": "ad_network", "url": "https://inmobi.com", "billing_types": ["CPC", "CPM"], "data_source": "openads"},

    # ── Naver Band ──
    {"operator_name": "네이버(주)", "platform_name": "밴드", "service_name": "밴드 광고", "platform_type": "social", "url": "https://band.us", "billing_types": ["CPC", "CPM"], "data_source": "web_search"},

    # ── Software / Utility ──
    {"operator_name": "곰앤컴퍼니", "platform_name": "곰플레이어", "service_name": "곰플레이어 광고", "platform_type": "display", "sub_type": "software", "url": "https://gomlab.com", "billing_types": ["CPM"], "data_source": "openads"},
    {"operator_name": "안랩(주)", "platform_name": "V3", "service_name": "V3 광고", "platform_type": "display", "sub_type": "software", "url": "https://ahnlab.com", "billing_types": ["CPM"], "data_source": "openads"},
]


async def main():
    inserted = 0
    skipped = 0

    async with async_session() as session:
        for p in PLATFORMS:
            # Check existing
            result = await session.execute(text("""
                SELECT id FROM ad_platforms
                WHERE operator_name = :op AND platform_name = :pn AND COALESCE(service_name, '') = COALESCE(:sn, '')
            """), {"op": p["operator_name"], "pn": p["platform_name"], "sn": p.get("service_name", "")})

            if result.fetchone():
                skipped += 1
                continue

            billing_json = json.dumps(p.get("billing_types", []), ensure_ascii=False) if p.get("billing_types") else None

            await session.execute(text("""
                INSERT INTO ad_platforms (operator_name, platform_name, service_name, platform_type, sub_type,
                    url, description, billing_types, is_self_serve, is_active, country, monthly_reach, data_source, notes)
                VALUES (:op, :pn, :sn, :pt, :st, :url, :desc, :bt, :ss, 1, 'KR', :mr, :ds, :notes)
            """), {
                "op": p["operator_name"],
                "pn": p["platform_name"],
                "sn": p.get("service_name"),
                "pt": p.get("platform_type"),
                "st": p.get("sub_type"),
                "url": p.get("url"),
                "desc": p.get("description"),
                "bt": billing_json,
                "ss": 1 if p.get("is_self_serve", True) else 0,
                "mr": p.get("monthly_reach"),
                "ds": p.get("data_source", "manual"),
                "notes": p.get("notes"),
            })
            inserted += 1
            if inserted <= 20:
                print(f"  + {p['platform_name']} - {p.get('service_name', '')}")

        await session.commit()

    print(f"\nDone: inserted={inserted}, skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(main())
