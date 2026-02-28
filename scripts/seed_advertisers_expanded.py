"""Seed 229 mid-small Korean advertisers into the advertisers table.

Idempotent: skips any advertiser whose name already exists.
Usage: python scripts/seed_advertisers_expanded.py
"""
import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from database import async_session
from sqlalchemy import text

ADVERTISERS = [
    # ── 화장품/인디뷰티 (industry_id=6) ──
    {"name": "조선미녀", "website": "beautyofjoseon.co.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "아누아", "website": "anua.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "스킨1004", "website": "skin1004korea.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "달바", "website": "dalba.co.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "라운드랩", "website": "roundlab.co.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "메디큐브", "website": "medicube.co.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "코스알엑스", "website": "cosrx.co.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "마녀공장", "website": "manyo.co.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "닥터지", "website": "dr-g.co.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "메디힐", "website": "mediheal.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "바이오던스", "website": "biodance.co.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "성분에디터", "website": "sungboon.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "3CE", "website": "3cecosmetics.co.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "롬앤", "website": "romand.co.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "VT코스메틱", "website": "vt-cosmetics.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "에이프릴스킨", "website": "aprilskin.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "넘버즈인", "website": "numbuzin.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "퓨리토", "website": "purito.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "티르티르", "website": "tirtir.co.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "페리페라", "website": "peripera.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "토니모리", "website": "tonymoly.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "미샤", "website": "missha.co.kr", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "이니스프리", "website": "innisfree.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "일리윤", "website": "illiyoon.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "클리오", "website": "cliocosmetic.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "에뛰드", "website": "etude.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "닥터자르트", "website": "drjart.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "아이소이", "website": "isoi.co.kr", "industry_id": 6, "advertiser_type": "brand"},

    # ── 패션/의류 (industry_id=7) ──
    {"name": "마뗑킴", "website": "matinkim.com", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "젝시믹스", "website": "xexymix.com", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "안다르", "website": "andar.co.kr", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "뮬라웨어", "website": "mulawear.com", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "W컨셉", "website": "wconcept.co.kr", "industry_id": 8, "advertiser_type": "company"},
    {"name": "브랜디", "website": "brandi.co.kr", "industry_id": 8, "advertiser_type": "company"},
    {"name": "캔마트", "website": "canmart.co.kr", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "난닝구", "website": "naning9.com", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "리리앤코", "website": "ririnco.com", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "소녀나라", "website": "sonyunara.com", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "아뜨랑스", "website": "attrangs.co.kr", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "임블리", "website": "imvely.com", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "앤더슨벨", "website": "anderssonbell.com", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "이미스", "website": "emis.kr", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "디스이즈네버댓", "website": "thisisneverthat.com", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "커버낫", "website": "covernat.net", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "퀸잇", "website": "queenit.kr", "industry_id": 8, "advertiser_type": "company"},
    {"name": "크림", "website": "kream.co.kr", "industry_id": 8, "advertiser_type": "company"},
    {"name": "바디럽", "website": "bodyluv.kr", "industry_id": 7, "advertiser_type": "brand"},

    # ── 건강기능식품/다이어트 (industry_id=9) ──
    {"name": "종근당건강", "website": "ckdhcmall.co.kr", "industry_id": 9, "advertiser_type": "company"},
    {"name": "고려은단", "website": "eundan.com", "industry_id": 9, "advertiser_type": "company"},
    {"name": "뉴트리원", "website": "nutrione.co.kr", "industry_id": 9, "advertiser_type": "company"},
    {"name": "안국건강", "website": "shopagh.com", "industry_id": 9, "advertiser_type": "company"},
    {"name": "GNM자연의품격", "website": "gnmart.co.kr", "industry_id": 9, "advertiser_type": "brand"},
    {"name": "푸드올로지", "website": "food-ology.co.kr", "industry_id": 9, "advertiser_type": "brand"},
    {"name": "대웅제약", "website": "dwhcmall.com", "industry_id": 9, "advertiser_type": "company"},
    {"name": "동국제약", "website": "dknutrition.co.kr", "industry_id": 9, "advertiser_type": "company"},
    {"name": "모어네이처", "website": "morenature.co.kr", "industry_id": 9, "advertiser_type": "brand"},
    {"name": "휴럼", "website": "hurumshop.com", "industry_id": 9, "advertiser_type": "brand"},
    {"name": "랭킹닭컴", "website": "rankingdak.com", "industry_id": 5, "advertiser_type": "brand"},
    {"name": "허닭", "website": "heodak.com", "industry_id": 5, "advertiser_type": "brand"},
    {"name": "프롬바이오", "website": "frombio.com", "industry_id": 9, "advertiser_type": "company"},
    {"name": "함소아", "website": "hamsoa.com", "industry_id": 9, "advertiser_type": "company"},
    {"name": "일동후디스", "website": "ildongfoodis.co.kr", "industry_id": 5, "advertiser_type": "company"},
    {"name": "마이프로틴코리아", "website": "myprotein.co.kr", "industry_id": 9, "advertiser_type": "brand"},

    # ── 성형외과/피부과 (industry_id=9) ──
    {"name": "바노바기성형외과", "website": "banobagi.com", "industry_id": 9, "advertiser_type": "company"},
    {"name": "아이디병원", "website": "idhospital.com", "industry_id": 9, "advertiser_type": "company"},
    {"name": "JW정원성형외과", "website": "jwbeauty.com", "industry_id": 9, "advertiser_type": "company"},
    {"name": "강남언니", "website": "gangnamunni.com", "industry_id": 9, "advertiser_type": "company"},
    {"name": "모두닥", "website": "modoodoc.com", "industry_id": 9, "advertiser_type": "company"},
    {"name": "원진성형외과", "website": "wonjin.com", "industry_id": 9, "advertiser_type": "company"},

    # ── 인테리어/리빙 (industry_id=17) ──
    {"name": "집닥", "website": "zipdoc.co.kr", "industry_id": 17, "advertiser_type": "company"},
    {"name": "아파트멘터리", "website": "apartmentary.com", "industry_id": 17, "advertiser_type": "company"},
    {"name": "KCC", "website": "kccworld.co.kr", "industry_id": 17, "advertiser_type": "company"},
    {"name": "까사미아", "website": "casamia.co.kr", "industry_id": 17, "advertiser_type": "brand"},
    {"name": "일룸", "website": "iloom.com", "industry_id": 17, "advertiser_type": "brand"},
    {"name": "데코뷰", "website": "decoview.co.kr", "industry_id": 17, "advertiser_type": "brand"},
    {"name": "집꾸미기", "website": "ggumim.co.kr", "industry_id": 17, "advertiser_type": "company"},

    # ── 교육/에듀테크 (industry_id=15) ──
    {"name": "클래스101", "website": "class101.net", "industry_id": 15, "advertiser_type": "company"},
    {"name": "패스트캠퍼스", "website": "fastcampus.co.kr", "industry_id": 15, "advertiser_type": "company"},
    {"name": "인프런", "website": "inflearn.com", "industry_id": 15, "advertiser_type": "company"},
    {"name": "코드스테이츠", "website": "codestates.com", "industry_id": 15, "advertiser_type": "company"},
    {"name": "스파르타코딩클럽", "website": "spartacodingclub.kr", "industry_id": 15, "advertiser_type": "company"},
    {"name": "콜로소", "website": "coloso.co.kr", "industry_id": 15, "advertiser_type": "company"},
    {"name": "탈잉", "website": "taling.me", "industry_id": 15, "advertiser_type": "company"},
    {"name": "프립", "website": "frip.co.kr", "industry_id": 15, "advertiser_type": "company"},
    {"name": "윌라", "website": "welaaa.com", "industry_id": 15, "advertiser_type": "company"},

    # ── 반려동물 (industry_id=20) ──
    {"name": "펫프렌즈", "website": "pet-friends.co.kr", "industry_id": 20, "advertiser_type": "company"},
    {"name": "바잇미", "website": "biteme.co.kr", "industry_id": 20, "advertiser_type": "brand"},
    {"name": "페스룸", "website": "pethroom.com", "industry_id": 20, "advertiser_type": "brand"},
    {"name": "하림펫푸드", "website": "harimpetfood.com", "industry_id": 20, "advertiser_type": "brand"},
    {"name": "네츄럴코어", "website": "naturalcore.co.kr", "industry_id": 20, "advertiser_type": "brand"},

    # ── IT/스타트업 (industry_id=2) ──
    {"name": "리디", "website": "ridibooks.com", "industry_id": 2, "advertiser_type": "company"},
    {"name": "두나무", "website": "dunamu.com", "industry_id": 4, "advertiser_type": "company"},
    {"name": "센드버드", "website": "sendbird.com", "industry_id": 2, "advertiser_type": "company"},
    {"name": "오아시스마켓", "website": "oasis.co.kr", "industry_id": 8, "advertiser_type": "company"},
    {"name": "한국신용데이터", "website": "kcd.co.kr", "industry_id": 2, "advertiser_type": "company"},
    {"name": "메가존클라우드", "website": "megazone.com", "industry_id": 2, "advertiser_type": "company"},
    {"name": "왓챠", "website": "watcha.com", "industry_id": 13, "advertiser_type": "company"},
    {"name": "리멤버", "website": "rememberapp.co.kr", "industry_id": 2, "advertiser_type": "company"},
    {"name": "소카", "website": "socar.kr", "industry_id": 3, "advertiser_type": "company"},
    {"name": "마이리얼트립", "website": "myrealtrip.com", "industry_id": 14, "advertiser_type": "company"},
    {"name": "스푼라디오", "website": "spooncast.net", "industry_id": 13, "advertiser_type": "company"},
    {"name": "클래스팅", "website": "classting.com", "industry_id": 15, "advertiser_type": "company"},

    # ── 부동산 (industry_id=11) ──
    {"name": "다방", "website": "dabangapp.com", "industry_id": 11, "advertiser_type": "company"},
    {"name": "호갱노노", "website": "hogangnono.com", "industry_id": 11, "advertiser_type": "company"},
    {"name": "집토스", "website": "ziptoss.com", "industry_id": 11, "advertiser_type": "company"},
    {"name": "알스퀘어", "website": "rsquare.co.kr", "industry_id": 11, "advertiser_type": "company"},
    {"name": "피터팬의좋은방구하기", "website": "peterpanz.com", "industry_id": 11, "advertiser_type": "company"},

    # ── 보험 (industry_id=4) ──
    {"name": "캐롯손해보험", "website": "carrotins.com", "industry_id": 4, "advertiser_type": "company"},
    {"name": "보맵", "website": "bomapp.co.kr", "industry_id": 4, "advertiser_type": "company"},
    {"name": "카카오페이손해보험", "website": "insurance.kakaopay.com", "industry_id": 4, "advertiser_type": "company"},
    {"name": "토스손해보험", "website": "tossinsurance.co.kr", "industry_id": 4, "advertiser_type": "company"},

    # ── 가전 (industry_id=10) ──
    {"name": "쿠쿠전자", "website": "cuckoo.co.kr", "industry_id": 10, "advertiser_type": "company"},
    {"name": "바디프렌드", "website": "bodyfriend.co.kr", "industry_id": 10, "advertiser_type": "company"},
    {"name": "위닉스", "website": "winix.com", "industry_id": 10, "advertiser_type": "company"},
    {"name": "쿠첸", "website": "cuchen.com", "industry_id": 10, "advertiser_type": "company"},
    {"name": "발뮤다코리아", "website": "balmuda.co.kr", "industry_id": 10, "advertiser_type": "company"},

    # ── 주류 (industry_id=18) ──
    {"name": "하이트진로", "website": "hitejinro.com", "industry_id": 18, "advertiser_type": "company"},
    {"name": "오비맥주", "website": "ob.co.kr", "industry_id": 18, "advertiser_type": "company"},
    {"name": "제주맥주", "website": "jejubeer.co.kr", "industry_id": 18, "advertiser_type": "brand"},
    {"name": "배상면주가", "website": "bsmjg.co.kr", "industry_id": 18, "advertiser_type": "company"},
    {"name": "보해양조", "website": "bohae.co.kr", "industry_id": 18, "advertiser_type": "company"},

    # ── 자동차 부품 (industry_id=3) ──
    {"name": "HL만도", "website": "hlmando.com", "industry_id": 3, "advertiser_type": "company"},
    {"name": "한온시스템", "website": "hanonsystems.com", "industry_id": 3, "advertiser_type": "company"},

    # ── D2C/기타 ──
    {"name": "블랭크코퍼레이션", "website": "blankcorp.com", "industry_id": 8, "advertiser_type": "company"},
    {"name": "링티", "website": "ringti.com", "industry_id": 5, "advertiser_type": "brand"},
    {"name": "닥터나우", "website": "drnow.co.kr", "industry_id": 9, "advertiser_type": "company"},
    {"name": "필라이즈", "website": "pillyze.com", "industry_id": 9, "advertiser_type": "company"},

    # ── 식품/음료 (industry_id=5) ──
    {"name": "정관장", "website": "kgc.co.kr", "industry_id": 5, "advertiser_type": "brand"},
    {"name": "비비고", "website": "bibigo.co.kr", "industry_id": 5, "advertiser_type": "brand"},
    {"name": "농심", "website": "nongshim.com", "industry_id": 5, "advertiser_type": "company"},
    {"name": "오뚜기", "website": "ottogi.co.kr", "industry_id": 5, "advertiser_type": "company"},
    {"name": "풀무원", "website": "pulmuone.co.kr", "industry_id": 5, "advertiser_type": "company"},
    {"name": "삼양식품", "website": "samyangfoods.com", "industry_id": 5, "advertiser_type": "company"},
    {"name": "매일유업", "website": "maeil.com", "industry_id": 5, "advertiser_type": "company"},
    {"name": "빙그레", "website": "bing.co.kr", "industry_id": 5, "advertiser_type": "company"},
    {"name": "하이트진로음료", "website": "hitejinrobeverage.com", "industry_id": 5, "advertiser_type": "company"},
    {"name": "동원F&B", "website": "dongwonfnb.com", "industry_id": 5, "advertiser_type": "company"},
    {"name": "남양유업", "website": "namyangi.com", "industry_id": 5, "advertiser_type": "company"},
    {"name": "서울우유", "website": "seoulmilk.co.kr", "industry_id": 5, "advertiser_type": "company"},
    {"name": "롯데칠성음료", "website": "lottechilsung.co.kr", "industry_id": 5, "advertiser_type": "company"},
    {"name": "코카콜라코리아", "website": "cocacolakorea.com", "industry_id": 5, "advertiser_type": "company"},
    {"name": "청정원", "website": "chungjungone.com", "industry_id": 5, "advertiser_type": "brand"},

    # ── 게임 (industry_id=12) ──
    {"name": "크래프톤", "website": "krafton.com", "industry_id": 12, "advertiser_type": "company"},
    {"name": "펄어비스", "website": "pearlabyss.com", "industry_id": 12, "advertiser_type": "company"},
    {"name": "넷마블", "website": "netmarble.com", "industry_id": 12, "advertiser_type": "company"},
    {"name": "카카오게임즈", "website": "kakaogames.com", "industry_id": 12, "advertiser_type": "company"},
    {"name": "스마일게이트", "website": "smilegate.com", "industry_id": 12, "advertiser_type": "company"},
    {"name": "위메이드", "website": "wemade.com", "industry_id": 12, "advertiser_type": "company"},
    {"name": "컴투스", "website": "com2us.com", "industry_id": 12, "advertiser_type": "company"},
    {"name": "데브시스터즈", "website": "devsisters.com", "industry_id": 12, "advertiser_type": "company"},
    {"name": "슈퍼셀", "website": "supercell.com", "industry_id": 12, "advertiser_type": "company"},
    {"name": "시프트업", "website": "shiftup.co.kr", "industry_id": 12, "advertiser_type": "company"},

    # ── 엔터테인먼트 (industry_id=13) ──
    {"name": "하이브", "website": "hybecorp.com", "industry_id": 13, "advertiser_type": "company"},
    {"name": "SM엔터테인먼트", "website": "smentertainment.com", "industry_id": 13, "advertiser_type": "company"},
    {"name": "JYP엔터테인먼트", "website": "jype.com", "industry_id": 13, "advertiser_type": "company"},
    {"name": "YG엔터테인먼트", "website": "ygfamily.com", "industry_id": 13, "advertiser_type": "company"},
    {"name": "CJ ENM", "website": "cjenm.com", "industry_id": 13, "advertiser_type": "company"},
    {"name": "에스엠씨앤씨", "website": "smcnc.com", "industry_id": 13, "advertiser_type": "company"},

    # ── 여행/항공 (industry_id=14) ──
    {"name": "여기어때", "website": "goodchoice.kr", "industry_id": 14, "advertiser_type": "company"},
    {"name": "야놀자", "website": "yanolja.com", "industry_id": 14, "advertiser_type": "company"},
    {"name": "트리플", "website": "triple.guide", "industry_id": 14, "advertiser_type": "company"},
    {"name": "클룩", "website": "klook.com", "industry_id": 14, "advertiser_type": "company"},
    {"name": "에어프레미아", "website": "airpremia.com", "industry_id": 14, "advertiser_type": "company"},
    {"name": "인터파크트리플", "website": "interpark.com", "industry_id": 14, "advertiser_type": "company"},

    # ── 스포츠/아웃도어 (industry_id=16) ──
    {"name": "블랙야크", "website": "blackyak.com", "industry_id": 16, "advertiser_type": "brand"},
    {"name": "K2", "website": "k2group.co.kr", "industry_id": 16, "advertiser_type": "brand"},
    {"name": "아이더", "website": "eider.co.kr", "industry_id": 16, "advertiser_type": "brand"},
    {"name": "네파", "website": "nepa.co.kr", "industry_id": 16, "advertiser_type": "brand"},
    {"name": "뉴발란스코리아", "website": "nbkorea.com", "industry_id": 16, "advertiser_type": "brand"},
    {"name": "데상트코리아", "website": "descentekorea.co.kr", "industry_id": 16, "advertiser_type": "brand"},

    # ── 유통/이커머스 (industry_id=8) ──
    {"name": "마켓컬리", "website": "kurly.com", "industry_id": 8, "advertiser_type": "company"},
    {"name": "에이블리", "website": "a-bly.com", "industry_id": 8, "advertiser_type": "company"},
    {"name": "지그재그", "website": "zigzag.kr", "industry_id": 8, "advertiser_type": "company"},
    {"name": "오늘의집", "website": "ohou.se", "industry_id": 8, "advertiser_type": "company"},
    {"name": "무신사", "website": "musinsa.com", "industry_id": 8, "advertiser_type": "company"},
    {"name": "발란", "website": "balaan.co.kr", "industry_id": 8, "advertiser_type": "company"},
    {"name": "트렌비", "website": "trenbe.com", "industry_id": 8, "advertiser_type": "company"},
    {"name": "머스트잇", "website": "mustit.co.kr", "industry_id": 8, "advertiser_type": "company"},

    # ── 금융/핀테크 (industry_id=4) ──
    {"name": "뱅크샐러드", "website": "banksalad.com", "industry_id": 4, "advertiser_type": "company"},
    {"name": "핀다", "website": "finda.co.kr", "industry_id": 4, "advertiser_type": "company"},
    {"name": "8퍼센트", "website": "8percent.kr", "industry_id": 4, "advertiser_type": "company"},
    {"name": "피플펀드", "website": "peoplefund.co.kr", "industry_id": 4, "advertiser_type": "company"},

    # ── 공공기관 (industry_id=19) ──
    {"name": "한국관광공사", "website": "visitkorea.or.kr", "industry_id": 19, "advertiser_type": "company"},
    {"name": "한국콘텐츠진흥원", "website": "kocca.kr", "industry_id": 19, "advertiser_type": "company"},
    {"name": "국민건강보험공단", "website": "nhis.or.kr", "industry_id": 19, "advertiser_type": "company"},
    {"name": "한국무역협회", "website": "kita.net", "industry_id": 19, "advertiser_type": "company"},
    {"name": "중소벤처기업부", "website": "mss.go.kr", "industry_id": 19, "advertiser_type": "company"},

    # ── 건설/부동산 (industry_id=11) ──
    {"name": "직방", "website": "zigbang.com", "industry_id": 11, "advertiser_type": "company"},
    {"name": "현대건설", "website": "hdec.kr", "industry_id": 11, "advertiser_type": "company"},
    {"name": "대우건설", "website": "daewooenc.com", "industry_id": 11, "advertiser_type": "company"},
    {"name": "GS건설", "website": "gsconst.co.kr", "industry_id": 11, "advertiser_type": "company"},

    # ── IT/통신 추가 (industry_id=2) ──
    {"name": "채널톡", "website": "channel.io", "industry_id": 2, "advertiser_type": "company"},
    {"name": "드라마앤컴퍼니", "website": "dramancompany.com", "industry_id": 2, "advertiser_type": "company"},
    {"name": "버즈빌", "website": "buzzvil.com", "industry_id": 2, "advertiser_type": "company"},
    {"name": "플렉스", "website": "flex.team", "industry_id": 2, "advertiser_type": "company"},
    {"name": "알리오", "website": "alio.ai", "industry_id": 2, "advertiser_type": "company"},
    {"name": "엘리스", "website": "elice.io", "industry_id": 15, "advertiser_type": "company"},

    # ── 뷰티/화장품 추가 (industry_id=6) ──
    {"name": "헤라", "website": "hera.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "라네즈", "website": "laneige.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "설화수", "website": "sulwhasoo.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "바닐라코", "website": "banilaco.com", "industry_id": 6, "advertiser_type": "brand"},
    {"name": "더페이스샵", "website": "thefaceshop.com", "industry_id": 6, "advertiser_type": "brand"},

    # ── 패션 추가 (industry_id=7) ──
    {"name": "스타일난다", "website": "stylenanda.com", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "미쏘", "website": "mixxo.com", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "스파오", "website": "spao.com", "industry_id": 7, "advertiser_type": "brand"},
    {"name": "탑텐", "website": "topten10.co.kr", "industry_id": 7, "advertiser_type": "brand"},

    # ── 식품/음료 추가 (industry_id=5) ──
    {"name": "하림", "website": "harim.com", "industry_id": 5, "advertiser_type": "company"},
    {"name": "CJ제일제당", "website": "cj.co.kr", "industry_id": 5, "advertiser_type": "company"},
    {"name": "SPC삼립", "website": "spc.co.kr", "industry_id": 5, "advertiser_type": "company"},
    {"name": "해태제과", "website": "ht.co.kr", "industry_id": 5, "advertiser_type": "company"},
    {"name": "크라운해태", "website": "crownconfectionery.com", "industry_id": 5, "advertiser_type": "company"},
    {"name": "일화", "website": "ilhwa.com", "industry_id": 5, "advertiser_type": "company"},

    # ── 제약/헬스케어 추가 (industry_id=9) ──
    {"name": "유한양행", "website": "yuhan.co.kr", "industry_id": 9, "advertiser_type": "company"},
    {"name": "한미약품", "website": "hanmi.co.kr", "industry_id": 9, "advertiser_type": "company"},
    {"name": "녹십자", "website": "gccorp.com", "industry_id": 9, "advertiser_type": "company"},
    {"name": "JW중외제약", "website": "jw-pharma.co.kr", "industry_id": 9, "advertiser_type": "company"},

    # ── 가전/전자 추가 (industry_id=10) ──
    {"name": "코웨이", "website": "coway.co.kr", "industry_id": 10, "advertiser_type": "company"},
    {"name": "청호나이스", "website": "chungho.co.kr", "industry_id": 10, "advertiser_type": "company"},
    {"name": "파세코", "website": "paseco.co.kr", "industry_id": 10, "advertiser_type": "company"},

    # ── 반려동물 추가 (industry_id=20) ──
    {"name": "로얄캐닌코리아", "website": "royalcanin.com", "industry_id": 20, "advertiser_type": "brand"},
    {"name": "인터펫", "website": "interpet.co.kr", "industry_id": 20, "advertiser_type": "company"},
    {"name": "도그마스터", "website": "dogmaster.co.kr", "industry_id": 20, "advertiser_type": "brand"},

    # ── 교육 추가 (industry_id=15) ──
    {"name": "메가스터디", "website": "megastudy.net", "industry_id": 15, "advertiser_type": "company"},
    {"name": "에듀윌", "website": "eduwill.net", "industry_id": 15, "advertiser_type": "company"},
    {"name": "대성마이맥", "website": "mimacstudy.com", "industry_id": 15, "advertiser_type": "company"},

    # ── 가구/인테리어 추가 (industry_id=17) ──
    {"name": "한샘", "website": "hanssem.com", "industry_id": 17, "advertiser_type": "company"},
    {"name": "리바트", "website": "livart.com", "industry_id": 17, "advertiser_type": "brand"},

    # ── 여행 추가 (industry_id=14) ──
    {"name": "스카이스캐너코리아", "website": "skyscanner.co.kr", "industry_id": 14, "advertiser_type": "company"},
    {"name": "교원투어", "website": "kyowontour.com", "industry_id": 14, "advertiser_type": "company"},
]

# Total count check
assert len(ADVERTISERS) == 229, f"Expected 229, got {len(ADVERTISERS)}"


async def main():
    inserted = 0
    skipped = 0

    async with async_session() as session:
        # Pre-load existing advertiser names for fast lookup
        result = await session.execute(text("SELECT name FROM advertisers"))
        existing_names = {row[0] for row in result.fetchall()}

        for adv in ADVERTISERS:
            name = adv["name"]
            if name in existing_names:
                skipped += 1
                continue

            website = adv["website"]
            if not website.startswith("http"):
                website = "https://" + website

            await session.execute(text("""
                INSERT INTO advertisers (name, industry_id, advertiser_type, website, data_source, created_at, updated_at)
                VALUES (:name, :industry_id, :advertiser_type, :website, 'seed_expanded', datetime('now'), datetime('now'))
            """), {
                "name": name,
                "industry_id": adv["industry_id"],
                "advertiser_type": adv["advertiser_type"],
                "website": website,
            })
            existing_names.add(name)
            inserted += 1

        await session.commit()

    print(f"Done: inserted={inserted}, skipped={skipped}, total_in_list={len(ADVERTISERS)}")


if __name__ == "__main__":
    asyncio.run(main())
