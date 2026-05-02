"""
광고주 업종 분류 정정 스크립트.

실행: python scripts/fix_industry_classifications.py [--db adscope.db]

작업 내용:
1. 쓰레기 광고주 삭제 (라이브러리 ID, 랜덤 코드 등)
2. 도메인/이름 기반 규칙으로 업종 재분류
3. 분류 불가 광고주는 기타(1)로 유지
"""

import re
import sqlite3
import argparse

INDUSTRY_MAP = {
    1: "기타",
    2: "IT/통신",
    3: "자동차",
    4: "금융/보험",
    5: "식품/음료",
    6: "뷰티/화장품",
    7: "패션/의류",
    8: "유통/이커머스",
    9: "제약/헬스케어",
    10: "가전/전자",
    11: "건설/부동산",
    12: "게임",
    13: "엔터테인먼트",
    14: "여행/항공",
    15: "교육",
    16: "스포츠/아웃도어",
    17: "가구/인테리어",
    18: "주류",
    19: "공공기관",
    20: "반려동물",
    21: "생활용품",
    22: "럭셔리/명품",
    23: "핀테크/금융서비스",
    24: "플랫폼/O2O",
}

# ── 도메인 → 업종 ID ─────────────────────────────────────────────────────────
DOMAIN_RULES: list[tuple[list[str], int]] = [
    # 유통/이커머스
    (["coupang.com", "coopang.com"], 8),
    (["gmarket.co.kr", "gmarket.com"], 8),
    (["11st.co.kr", "eleventh.co.kr"], 8),
    (["auction.co.kr"], 8),
    (["lotteon.com", "lottemart.com", "lotteoff.com"], 8),
    (["ssg.com", "emart.com", "shinsegae.com"], 8),
    (["kurly.com", "marktcurly.com"], 8),
    (["oliflex.com", "oliveyoung.co.kr"], 8),  # 올리브영
    (["cjonstyle.com", "cjmall.com"], 8),
    (["hmall.com", "hyundaihmall.com"], 8),
    (["tmon.co.kr", "timon.co.kr"], 8),
    (["wemakeprice.com"], 8),
    (["interpark.com", "interpark.co.kr"], 8),
    (["gsshop.com", "gsretail.com"], 8),
    (["ably.me", "ably.com"], 8),
    (["musinsa.com"], 7),  # 무신사 → 패션
    (["29cm.co.kr"], 7),
    (["wconcept.co.kr"], 7),

    # 금융/보험
    (["toss.im", "tossbankcard.com", "tossbank.com", "tossplace.com"], 4),
    (["kakaopay.com", "kakaocorp.com"], 4),
    (["naverpay.naver.com"], 4),
    (["shinhan.com", "shinhancard.com", "shinhansec.com"], 4),
    (["kbcard.com", "kbsec.com", "kbfg.com", "kb.co.kr"], 4),
    (["hanacard.co.kr", "hanafinancial.com", "hana.com"], 4),
    (["ibk.co.kr", "ibkcard.com"], 4),
    (["nonghyup.com", "nonghyupcard.com"], 4),
    (["wooricard.com", "woorifg.com", "wooribank.com"], 4),
    (["kakaobank.com"], 4),
    (["bankofkorea.or.kr", "fss.or.kr"], 4),
    (["samsung-card.com", "samsungsecurities.com"], 4),
    (["lottefinance.co.kr", "lottecard.co.kr"], 4),
    (["hyundaicard.com", "hyundaicapital.com", "hcs.com"], 4),
    (["bccard.com"], 4),
    (["koreaexim.go.kr", "nhis.or.kr", "nps.or.kr"], 4),
    (["stockplus.com", "kiwoom.com", "daishin.co.kr"], 4),
    (["mirae-asset.com", "miraeasset.com"], 4),
    (["samsunglife.com", "samsungfire.com"], 4),
    (["hanwhalife.com", "hanwha.com"], 4),
    (["kyobolife.co.kr", "kyobo.co.kr"], 4),
    (["lina.co.kr", "cigna.co.kr"], 4),
    (["db-insurance.com", "meritzfire.com", "hyundai-marine.com"], 4),
    (["fintechkorea.or.kr"], 4),

    # IT/통신
    (["skt.co.kr", "tworld.co.kr", "sk.co.kr", "skbroadband.com"], 2),
    (["kt.com", "olleh.com", "ktds.com"], 2),
    (["lguplus.co.kr", "uplus.co.kr"], 2),
    (["microsoft.com", "office.com", "azure.com"], 2),
    (["google.co.kr"], 2),
    (["samsung.com", "sec.com"], 2),
    (["zoom.us", "zoominfo.com"], 2),
    (["notion.so", "atlassian.com", "slack.com"], 2),
    (["aws.amazon.com", "amazon.com"], 2),
    (["cloudflare.com"], 2),
    (["gabia.com", "cafe24.com", "hosting.kr"], 2),
    (["nhn.com", "nhncloud.com"], 2),
    (["kakaocorp.com"], 2),

    # 건설/부동산
    (["zigbang.com", "zigbang.net"], 11),
    (["dabangapp.com", "peterpanz.com"], 11),
    (["naver-land.com", "land.naver.com"], 11),
    (["realestate.daum.net", "land.daum.net"], 11),
    (["hogangnono.com"], 11),
    (["apartmentrental.com"], 11),
    (["hdenc.co.kr", "hyundai-enc.com"], 11),
    (["daewooenc.com"], 11),
    (["posco-e.com", "poscoenc.com"], 11),
    (["sk-ecoplant.com", "skecoplant.com"], 11),
    (["lottec.co.kr", "lottecastle.co.kr"], 11),
    (["gjenc.com", "gjenc.co.kr"], 11),
    (["ggc.co.kr", "gs-enc.com", "gsenc.com"], 11),
    (["taeyoung-enc.com"], 11),
    (["samsung-cni.com", "samsungcni.com"], 11),
    (["rautecap.co.kr"], 11),
    (["nemoapp.co.kr"], 11),

    # 자동차
    (["hyundai.com", "hyundaimotors.com"], 3),
    (["kia.com", "kiamotors.com"], 3),
    (["genesis.com"], 3),
    (["chevrolet.co.kr", "gm.com"], 3),
    (["bmw.co.kr", "bmw.com"], 3),
    (["mercedes-benz.co.kr", "mercedes-benz.com"], 3),
    (["audi.co.kr", "audikorea.com"], 3),
    (["toyota.co.kr", "lexus.co.kr"], 3),
    (["volkswagen.co.kr"], 3),
    (["volvocar.co.kr"], 3),
    (["renaultkorea.com", "renaultsamsungm.com"], 3),
    (["tesla.com"], 3),
    (["rivian.com"], 3),
    (["ssangyong.co.kr", "kg-mobility.com"], 3),
    (["encar.com", "chachacar.co.kr", "kb-car.co.kr"], 3),

    # 여행/항공
    (["yanolja.com", "ya.com"], 14),
    (["yeogi.com", "yeogibutton.com"], 14),
    (["expedia.co.kr", "expedia.com"], 14),
    (["booking.com"], 14),
    (["airbnb.com", "airbnb.co.kr"], 14),
    (["koreanair.com"], 14),
    (["asiana.com", "flyasiana.com"], 14),
    (["jejuair.net"], 14),
    (["jinair.com"], 14),
    (["twayair.com"], 14),
    (["airseoul.com"], 14),
    (["tripadvisor.co.kr", "tripadvisor.com"], 14),
    (["klook.com"], 14),
    (["interpark.com"], 14),
    (["hanatour.com", "modutour.com"], 14),

    # 게임
    (["nexon.com", "nexon.co.kr"], 12),
    (["ncsoft.com", "nc.com"], 12),
    (["netmarble.com"], 12),
    (["krafton.com", "pubg.com"], 12),
    (["smilegate.com"], 12),
    (["com2us.com"], 12),
    (["gamevil.com"], 12),
    (["wemade.com"], 12),
    (["kakaogames.com"], 12),
    (["pearlabyss.com"], 12),
    (["blizzard.com"], 12),
    (["riot.com", "riotgames.com", "leagueoflegends.com"], 12),
    (["steam.com", "steampowered.com"], 12),
    (["nintendo.co.kr", "playstation.com", "xbox.com"], 12),

    # 뷰티/화장품
    (["laneige.com", "innisfree.com", "etude.com", "sulwhasoo.com", "hera.co.kr"], 6),
    (["amorepacific.com"], 6),
    (["lghaus.com", "ohui.com", "su:m37.com", "vdl.co.kr"], 6),
    (["missha.com"], 6),
    (["clio.co.kr", "clio-cosmetics.com"], 6),
    (["banilaco.com"], 6),
    (["romand.com"], 6),
    (["tirtir.com"], 6),
    (["cosrx.com"], 6),
    (["skinfood.com"], 6),
    (["espoir.com"], 6),

    # 식품/음료
    (["cjcheiljedang.com", "cj.net"], 5),
    (["ottogi.co.kr"], 5),
    (["nongshim.com"], 5),
    (["lottechilsung.co.kr"], 5),
    (["haitai.co.kr"], 5),
    (["orion.co.kr"], 5),
    (["maeil.com", "maeilmilk.com"], 5),
    (["namyang.com"], 5),
    (["coffeebay.co.kr", "hollys.co.kr", "twosome.co.kr", "ediya.com"], 5),
    (["starbucks.co.kr", "starbucks.com"], 5),
    (["mcdonalds.co.kr", "bk.com", "burgerking.co.kr"], 5),
    (["baemin.com", "baemin.co.kr"], 5),
    (["coupangeats.com"], 5),
    (["yogiyo.co.kr"], 5),

    # 제약/헬스케어
    (["jw.co.kr", "jw-holding.co.kr"], 9),
    (["yuhan.co.kr"], 9),
    (["daewoong.co.kr"], 9),
    (["celltrion.com"], 9),
    (["samsung-bioepis.com", "samsungbiologics.com"], 9),
    (["boryung.co.kr"], 9),
    (["hanmi.co.kr", "hanmipharm.com"], 9),
    (["ildongsyndrome.co.kr", "ildong.com"], 9),
    (["goodoc.io", "gangnam.com"], 9),
    (["mobidoc.com", "nmd.co.kr"], 9),
    (["kakaohealth.com"], 9),
    (["mediplex.com"], 9),

    # 가전/전자
    (["samsung.com", "samsung.co.kr"], 10),
    (["lg.com", "lgekt.co.kr"], 10),
    (["apple.com"], 10),
    (["dyson.co.kr", "dyson.com"], 10),
    (["cuckoo.co.kr", "coway.co.kr"], 10),
    (["winix.com", "winix.co.kr"], 10),
    (["haier.co.kr", "haier.com"], 10),
    (["philips.co.kr", "philips.com"], 10),

    # 교육
    (["megastudy.net", "megapass.net"], 15),
    (["etoos.com"], 15),
    (["ebsi.co.kr"], 15),
    (["eduwill.net"], 15),
    (["classin.co.kr", "class101.net"], 15),
    (["ringle.com"], 15),
    (["srtmax.com"], 15),
    (["kangcom.com", "inflearn.com"], 15),
    (["yanadoo.co.kr", "yanadoo.com"], 15),

    # 스포츠/아웃도어
    (["nike.com", "adidas.co.kr", "adidas.com"], 16),
    (["puma.com", "reebok.co.kr"], 16),
    (["newbalance.co.kr"], 16),
    (["underarmour.com"], 16),
    (["columbia.co.kr", "columbia.com"], 16),
    (["thenorthface.co.kr", "thenorthface.com"], 16),
    (["blackyak.com", "kolon.com", "k2.co.kr"], 16),
    (["fila.co.kr", "fila.com"], 16),
    (["mizuno.co.kr", "asics.co.kr"], 16),

    # 가구/인테리어
    (["ikea.com", "ikea.co.kr"], 17),
    (["hanssem.com"], 17),
    (["iloom.com"], 17),
    (["hyundailiving.co.kr"], 17),
    (["livart.co.kr"], 17),
    (["ohouse.kr", "bucketplace.com"], 17),
    (["lottehomeshopping.com"], 17),
    (["homechoice.co.kr"], 17),

    # 주류
    (["hite.com", "hitejinro.com", "jinro.com"], 18),
    (["ob.co.kr", "obbeer.com"], 18),
    (["lottechilsung.co.kr"], 18),
    (["muhak.co.kr", "chumchoreom.co.kr"], 18),

    # 공공기관
    (["korea.go.kr", "gov.kr", "go.kr"], 19),
    (["kotra.or.kr", "kipo.go.kr", "kised.or.kr"], 19),

    # 럭셔리/명품
    (["lv.com", "louisvuitton.com"], 22),
    (["chanel.com"], 22),
    (["hermes.com"], 22),
    (["gucci.com"], 22),
    (["prada.com"], 22),
    (["balenciaga.com"], 22),
    (["dior.com"], 22),
    (["burberry.com"], 22),
    (["givenchy.com"], 22),
    (["fendi.com"], 22),
    (["bvlgari.com"], 22),
    (["rolex.com"], 22),

    # 핀테크/금융서비스
    (["viva-republica.com", "toss.im", "tossbank.com", "tosssecurities.com"], 23),
    (["rainist.com", "banksalad.com"], 23),
    (["8percent.kr", "peoplefund.io"], 23),
    (["kakaopay.com"], 23),
    (["naver-pay.com"], 23),
    (["payco.com", "payco.net"], 23),
    (["samsungpay.com"], 23),
    (["zeropay.or.kr"], 23),

    # 플랫폼/O2O
    (["kakaomap.com", "map.kakao.com"], 24),
    (["baemin.com", "baemin.co.kr"], 24),
    (["coupangeats.com"], 24),
    (["yogiyo.co.kr"], 24),
    (["krafton.com"], 24),
    (["kraftonjungle.com"], 24),
    (["kmong.com", "freelancr.co.kr"], 24),
    (["rocketpunch.com", "wanted.co.kr", "jumpit.co.kr", "saramin.co.kr", "jobkorea.co.kr"], 24),
    (["당근마켓.com", "daangn.com"], 24),
    (["joongna.com"], 24),
    (["bunjang.co.kr"], 24),
    (["ohou.se", "ohouse.kr", "bucketplace.com"], 24),

    # 엔터테인먼트
    (["hybe.com", "bighit.com", "bighitentertainment.com"], 13),
    (["smtown.com", "sment.com", "smentertainment.com"], 13),
    (["jype.com", "jyp.com"], 13),
    (["ygfamily.com", "ygentertainment.com"], 13),
    (["kakaoent.com", "kakaoentertainment.com"], 13),
    (["cjenm.com", "tvn.com"], 13),
    (["wavve.com", "waave.com"], 13),
    (["laftel.net", "watcha.com"], 13),
    (["netflix.com", "netflix.net"], 13),
    (["disneyplus.com"], 13),
    (["youtube.com"], 13),
    (["melon.com", "bugs.co.kr", "genie.co.kr"], 13),
    (["ticketlink.co.kr", "yes24.com", "interpark.com"], 13),
]

# ── 이름 패턴 → 업종 ID ──────────────────────────────────────────────────────
NAME_RULES: list[tuple[list[str], int]] = [
    # 유통/이커머스
    (["쿠팡", "지마켓", "G마켓", "11번가", "옥션", "위메프", "티몬", "마켓컬리", "SSG", "롯데온", "GS샵",
      "CJ온스타일", "홈앤쇼핑", "NS홈쇼핑", "공영홈쇼핑", "에이블리", "지그재그", "브랜디", "카카오쇼핑"], 8),
    (["네이버쇼핑", "스마트스토어"], 8),

    # 금융/보험
    (["토스", "카카오페이", "네이버페이", "삼성페이", "제로페이"], 4),
    (["삼성카드", "현대카드", "신한카드", "KB카드", "국민카드", "롯데카드", "하나카드", "우리카드", "씨티카드", "IBK기업은행카드", "BC카드", "농협카드"], 4),
    (["삼성생명", "한화생명", "교보생명", "신한생명", "흥국생명", "DB생명"], 4),
    (["삼성화재", "DB손해보험", "메리츠화재", "현대해상", "KB손해보험", "롯데손해보험", "한화손해보험"], 4),
    (["신한은행", "국민은행", "하나은행", "우리은행", "기업은행", "농협은행", "SC제일은행", "씨티은행", "카카오뱅크", "케이뱅크", "토스뱅크"], 4),
    (["미래에셋", "한국투자증권", "NH투자증권", "KB증권", "삼성증권", "키움증권", "대신증권", "하나증권"], 4),
    (["핀테크", "인슈어테크", "P2P금융", "크라우드펀딩"], 4),

    # IT/통신
    (["SK텔레콤", "KT", "LG유플러스", "SKT", "LG U+", "알뜰폰"], 2),
    (["네이버", "카카오", "라인", "밴드", "다음"], 2),
    (["삼성SDS", "LG CNS", "SK C&C", "포스코ICT", "롯데정보통신"], 2),
    (["클라우드", "SaaS", "솔루션", "플랫폼", "ERP", "CRM", "협업툴"], 2),

    # 건설/부동산
    (["직방", "다방", "피터팬", "호갱노노", "부동산114", "아파트너", "네모", "호라이즌"],  11),
    (["현대건설", "삼성물산건설", "대우건설", "GS건설", "포스코건설", "DL이앤씨", "SK에코플랜트",
      "롯데건설", "태영건설", "HDC현대산업개발", "코오롱글로벌"], 11),

    # 자동차
    (["현대자동차", "기아자동차", "기아", "현대차", "제네시스", "쌍용차", "KG모빌리티", "르노삼성", "한국GM"], 3),
    (["BMW", "벤츠", "아우디", "폭스바겐", "토요타", "렉서스", "혼다", "볼보", "포르쉐", "람보르기니", "페라리"], 3),

    # 여행/항공
    (["야놀자", "여기어때", "에어비앤비", "대한항공", "아시아나", "제주항공", "진에어", "티웨이", "에어서울",
      "하나투어", "모두투어", "참좋은여행", "노랑풍선"], 14),

    # 게임
    (["넥슨", "엔씨소프트", "넷마블", "크래프톤", "스마일게이트", "컴투스", "웹젠", "카카오게임즈",
      "펄어비스", "위메이드", "조이시티", "넷게임즈"], 12),

    # 뷰티/화장품
    (["아모레퍼시픽", "LG생활건강", "설화수", "라네즈", "이니스프리", "에뛰드", "미샤", "클리오",
      "롬앤", "달바", "조선미녀", "비플레인", "티르티르", "어퓨"], 6),

    # 식품/음료
    (["배달의민족", "배민", "쿠팡이츠", "요기요"], 5),
    (["스타벅스", "투썸플레이스", "이디야", "할리스", "커피빈", "폴바셋", "메가커피", "컴포즈커피"], 5),
    (["CJ제일제당", "오뚜기", "농심", "롯데칠성", "해태제과", "오리온", "매일유업", "남양유업"], 5),
    (["맥도날드", "버거킹", "롯데리아", "KFC", "써브웨이", "파파이스"], 5),

    # 제약/헬스케어
    (["유한양행", "대웅제약", "셀트리온", "종근당", "동아제약", "보령", "한미약품", "일동제약"], 9),
    (["굿닥", "강남언니", "의사결정플랫폼", "헬스케어", "모바일닥터"], 9),

    # 스포츠/아웃도어
    (["나이키", "아디다스", "뉴발란스", "푸마", "리복", "언더아머", "노스페이스", "블랙야크", "K2",
      "코오롱스포츠", "밀레", "네파", "살로몬", "아식스", "미즈노", "필라", "컬럼비아"], 16),

    # 가구/인테리어
    (["이케아", "한샘", "일룸", "현대리바트", "까사미아", "오늘의집", "인테리어", "리모델링"], 17),
    (["더예쁜가구", "리빙"], 17),

    # 럭셔리/명품
    (["루이비통", "샤넬", "에르메스", "구찌", "프라다", "발렌시아가", "디올", "버버리", "지방시",
      "펜디", "불가리", "롤렉스", "까르띠에", "티파니", "보테가베네타", "생로랑", "셀린느", "몽클레어"], 22),

    # 핀테크/금융서비스
    (["토스", "뱅크샐러드", "카카오페이", "네이버페이", "페이코", "삼성페이", "제로페이", "핀테크",
      "간편결제", "크라우드펀딩", "P2P금융", "인터넷은행"], 23),

    # 플랫폼/O2O
    (["당근마켓", "당근", "번개장터", "중고나라", "크몽", "탈잉", "숨고", "원티드", "사람인", "잡코리아", "점핏"], 24),

    # 주류
    (["하이트진로", "오비맥주", "롯데주류", "무학", "참이슬", "진로", "클라우드", "카스"], 18),

    # 공공기관
    (["국가", "정부", "행정", "공단", "공사", "청", "부처", "위원회"], 19),

    # 엔터테인먼트
    (["하이브", "SM엔터", "JYP엔터", "YG엔터", "카카오엔터", "CJ ENM"], 13),
    (["넷플릭스", "웨이브", "왓챠", "티빙", "시즌", "라프텔", "시즌"], 13),
    (["멜론", "지니", "벅스", "플로", "스포티파이"], 13),

    # 반려동물
    (["펫프렌즈", "핏펫", "어바웃펫", "야옹이", "마이강아지"], 20),
]

# ── 삭제 대상 패턴 ─────────────────────────────────────────────────────────
GARBAGE_PATTERNS = [
    r"^라이브러리 ID:",
    r"^Library ID:",
    r"^Learn More$",
    r"^Shop Now$",
    r"^자세히 알아보기$",
    r"^지금 쇼핑하기$",
    r"^더 보기$",
    r"^See More$",
    r"^Get Started$",
    r"^Sign Up$",
    r"^Download$",
    r"^[A-Za-z0-9]{8,}[0-9]{6,}$",  # Morning386944 같은 랜덤 코드
    r"^[A-Za-z0-9\-_]{5,}\d{4,}$",  # riz990606code 같은 패턴
    r"^\d{7,}$",                      # 순수 숫자 ID
    r"^\d+-\d+$",                     # 6-5929000037199 같은 패턴
]

# 글자수 초과 = 광고 카피가 광고주명으로 저장된 것
_GARBAGE_MAX_LEN = 80


# 이 도메인들은 플랫폼(스토어/채널) URL이라서 광고주 업종과 무관 — 도메인 분류에서 제외
PLATFORM_DOMAINS = {
    "brand.naver.com",
    "smartstore.naver.com",
    "m.brand.naver.com",
    "m.smartstore.naver.com",
    "store.naver.com",
    "shopping.naver.com",
    "link.coupang.com",
    "play.google.com",
    "apps.apple.com",
    "bit.ly",
    "t.co",
    "linktr.ee",
    "fb.me",
    "instagr.am",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "youtu.be",
    "forms.gle",
    "docs.google.com",
    "m.site.naver.com",
    "blog.naver.com",
    "post.naver.com",
    "in.naver.com",
    # 광고 투명성 / 앱스토어 인프라 URL (광고주 업종과 무관)
    "adstransparency.google.com",
    "itunes.apple.com",
    "apps.apple.com",
    "play.google.com",
    "app.adjust.com",
    "go.onelink.me",
    "link.coupang.com",
    "bit.ly",
    "tinyurl.com",
    "t.co",
}


def get_domain(url: str | None) -> str:
    """URL에서 도메인 추출 (www./m. 제거). 플랫폼 URL이면 빈 문자열 반환."""
    if not url:
        return ""
    url_orig = url.lower().strip()
    url = url_orig
    # 프로토콜 제거
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
    # 경로 제거
    domain = url.split("/")[0].split("?")[0].split("#")[0]
    # www. 제거
    if domain.startswith("www."):
        domain = domain[4:]
    # 플랫폼 도메인이면 스킵 (광고주 업종과 무관)
    if domain in PLATFORM_DOMAINS:
        return ""
    # 서브도메인이 플랫폼인지 확인 (brand.naver.com 등)
    for pf in PLATFORM_DOMAINS:
        if domain == pf or domain.endswith("." + pf):
            return ""
    return domain


def classify_by_domain(domain: str) -> int | None:
    for domains, industry_id in DOMAIN_RULES:
        for d in domains:
            if domain == d or domain.endswith("." + d):
                return industry_id
    return None


def classify_by_name(name: str) -> int | None:
    name_lower = name.lower()
    for names, industry_id in NAME_RULES:
        for n in names:
            if n.lower() in name_lower or name_lower in n.lower():
                return industry_id
    return None


def is_garbage(name: str) -> bool:
    if not name:
        return True
    # 길이 초과 = 광고 카피가 광고주명으로 저장된 것
    if len(name) > _GARBAGE_MAX_LEN:
        return True
    for pattern in GARBAGE_PATTERNS:
        if re.match(pattern, name, re.IGNORECASE):
            return True
    return False


def main(db_path: str, dry_run: bool = False):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. 쓰레기 광고주 삭제
    cur.execute("SELECT id, name FROM advertisers")
    all_adv = cur.fetchall()

    garbage_ids = []
    for row in all_adv:
        if is_garbage(row["name"]):
            garbage_ids.append(row["id"])

    print(f"\n[쓰레기 광고주] {len(garbage_ids)}개 삭제 대상")
    if not dry_run and garbage_ids:
        # 관련 데이터도 함께 정리
        placeholders = ",".join("?" * len(garbage_ids))
        cur.execute(f"UPDATE ad_details SET advertiser_id = NULL WHERE advertiser_id IN ({placeholders})", garbage_ids)
        cur.execute(f"DELETE FROM advertiser_favorites WHERE advertiser_id IN ({placeholders})", garbage_ids)
        cur.execute(f"DELETE FROM campaigns WHERE advertiser_id IN ({placeholders})", garbage_ids)
        cur.execute(f"DELETE FROM spend_estimates WHERE campaign_id IN (SELECT id FROM campaigns WHERE advertiser_id IN ({placeholders}))", garbage_ids)
        cur.execute(f"DELETE FROM advertisers WHERE id IN ({placeholders})", garbage_ids)
        print(f"  → {len(garbage_ids)}개 삭제 완료")

    # 2. 업종 재분류
    cur.execute("SELECT id, name, website, industry_id FROM advertisers")
    advertisers = cur.fetchall()

    updates: list[tuple[int, int, str]] = []  # (new_industry_id, adv_id, reason)
    skipped = 0

    for adv in advertisers:
        adv_id = adv["id"]
        name = adv["name"] or ""
        website = adv["website"] or ""
        current = adv["industry_id"]

        domain = get_domain(website)

        new_id = classify_by_domain(domain) or classify_by_name(name)

        if new_id and new_id != current:
            reason = f"domain={domain}" if classify_by_domain(domain) else f"name={name}"
            updates.append((new_id, adv_id, reason))
        else:
            skipped += 1

    print(f"\n[업종 재분류] {len(updates)}개 변경 / {skipped}개 변경 없음")

    # 변경 샘플 출력
    for new_id, adv_id, reason in updates[:30]:
        old_row = next(a for a in advertisers if a["id"] == adv_id)
        old_name = INDUSTRY_MAP.get(old_row["industry_id"], "?")
        new_name = INDUSTRY_MAP.get(new_id, "?")
        print(f"  [{old_row['name']}] {old_name} → {new_name}  ({reason})")

    if len(updates) > 30:
        print(f"  ... 외 {len(updates) - 30}개")

    if not dry_run and updates:
        for new_id, adv_id, _ in updates:
            cur.execute("UPDATE advertisers SET industry_id = ? WHERE id = ?", (new_id, adv_id))
        print(f"  → {len(updates)}개 업데이트 완료")

    if not dry_run:
        conn.commit()
        print("\nDB saved OK")
    else:
        print("\n(dry-run mode - no DB changes)")

    conn.close()

    # 업종별 통계 출력
    if not dry_run:
        conn2 = sqlite3.connect(db_path)
        conn2.row_factory = sqlite3.Row
        cur2 = conn2.cursor()
        cur2.execute("""
            SELECT i.name, COUNT(a.id) as cnt
            FROM industries i
            LEFT JOIN advertisers a ON a.industry_id = i.id
            GROUP BY i.id ORDER BY cnt DESC
        """)
        print("\n── 업종별 광고주 수 ──────────────────────")
        for row in cur2.fetchall():
            print(f"  {row['name']:20s}  {row['cnt']:4d}개")
        conn2.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="광고주 업종 분류 정정")
    parser.add_argument("--db", default="adscope.db", help="DB 파일 경로")
    parser.add_argument("--dry-run", action="store_true", help="실제 변경 없이 미리보기")
    args = parser.parse_args()

    main(args.db, dry_run=args.dry_run)
