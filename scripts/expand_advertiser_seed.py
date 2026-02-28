"""
광고주 시드 데이터 대규모 확장 스크립트
========================================
웹 리서치 기반으로 기존 217개 → 500+ 광고주로 확장

카테고리:
1. ADIC 100대 광고주 (4대매체 기준)
2. 대기업 그룹사 계열사
3. 글로벌 브랜드 한국법인
4. D2C/스타트업/유니콘
5. 게임/엔터/뷰티/식품/제약/교육/금융 등 카테고리별

실행: python scripts/expand_advertiser_seed.py
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT / "data" / "advertiser_seed.json"
BACKUP_PATH = ROOT / "data" / "advertiser_seed_backup_217.json"

# ──────────────────────────────────────────────
# 추가할 광고주 목록 (기존 217개에 없는 것만)
# ──────────────────────────────────────────────

NEW_ADVERTISERS = [
    # ═══════════════════════════════════════════
    # ADIC 100대 광고주 (기존에 없는 것)
    # ═══════════════════════════════════════════
    {"name": "삼성물산", "industry": "건설/부동산", "type": "company", "brand": "래미안", "website": "samsungcnt.com", "aliases": ["Samsung C&T", "래미안"], "channels": {"youtube": "https://www.youtube.com/@raemian"}},
    {"name": "현대건설", "industry": "건설/부동산", "type": "company", "brand": "힐스테이트", "website": "hdec.kr", "aliases": ["Hyundai E&C", "현대엔지니어링"], "channels": {}},
    {"name": "포스코건설", "industry": "건설/부동산", "type": "company", "brand": "더샵", "website": "poscoenc.com", "aliases": ["POSCO E&C", "포스코이앤씨"], "channels": {}},
    {"name": "호반건설", "industry": "건설/부동산", "type": "company", "brand": "호반써밋", "website": "hoban.co.kr", "aliases": ["Hoban"], "channels": {}},
    {"name": "HDC현대산업개발", "industry": "건설/부동산", "type": "company", "brand": "아이파크", "website": "hdc-dvp.com", "aliases": ["HDC", "아이파크"], "channels": {}},

    {"name": "SK이노베이션", "industry": "기타", "type": "company", "brand": "SK에너지", "website": "skinnovation.com", "aliases": ["SK Innovation", "SK에너지"], "channels": {"youtube": "https://www.youtube.com/@SKInnovation"}},
    {"name": "포스코", "industry": "기타", "type": "company", "brand": "POSCO", "website": "posco.com", "aliases": ["POSCO", "포스코홀딩스"], "channels": {}},
    {"name": "두산", "industry": "기타", "type": "company", "brand": "Doosan", "website": "doosan.com", "aliases": ["Doosan"], "channels": {}},
    {"name": "SK(주)", "industry": "기타", "type": "company", "brand": "SK", "website": "sk.com", "aliases": ["SK Inc"], "channels": {}},
    {"name": "한화", "industry": "기타", "type": "company", "brand": "Hanwha", "website": "hanwha.co.kr", "aliases": ["Hanwha Group"], "channels": {}},
    {"name": "GS", "industry": "기타", "type": "company", "brand": "GS", "website": "gs.co.kr", "aliases": ["GS Group"], "channels": {}},

    # ═══════════════════════════════════════════
    # 금융/보험 추가
    # ═══════════════════════════════════════════
    {"name": "현대해상화재보험", "industry": "금융/보험", "type": "company", "brand": "현대해상", "website": "hi.co.kr", "aliases": ["현대해상", "Hyundai Marine"], "channels": {"youtube": "https://www.youtube.com/@hyundaimarine"}},
    {"name": "KB손해보험", "industry": "금융/보험", "type": "company", "brand": "KB손보", "website": "kbinsure.co.kr", "aliases": ["KB Insurance"], "channels": {}},
    {"name": "메리츠화재", "industry": "금융/보험", "type": "company", "brand": "메리츠화재", "website": "meritzfire.com", "aliases": ["Meritz Fire"], "channels": {}},
    {"name": "삼성생명", "industry": "금융/보험", "type": "company", "brand": "삼성생명", "website": "samsunglife.com", "aliases": ["Samsung Life"], "channels": {"youtube": "https://www.youtube.com/@samsunglife"}},
    {"name": "한화생명보험", "industry": "금융/보험", "type": "company", "brand": "한화생명", "website": "hanwhalife.com", "aliases": ["Hanwha Life"], "channels": {}},
    {"name": "라이나생명보험", "industry": "금융/보험", "type": "company", "brand": "라이나생명", "website": "lina.co.kr", "aliases": ["LINA Life"], "channels": {}},
    {"name": "AIA생명보험", "industry": "금융/보험", "type": "company", "brand": "AIA생명", "website": "aia.co.kr", "aliases": ["AIA Life"], "channels": {}},
    {"name": "푸르덴셜생명보험", "industry": "금융/보험", "type": "company", "brand": "푸르덴셜", "website": "prudential.co.kr", "aliases": ["Prudential"], "channels": {}},
    {"name": "카카오페이", "industry": "금융/보험", "type": "company", "brand": "카카오페이", "website": "kakaopay.com", "aliases": ["Kakao Pay"], "channels": {}},
    {"name": "네이버파이낸셜", "industry": "금융/보험", "type": "company", "brand": "네이버페이", "website": "naverfincorp.com", "aliases": ["Naver Pay", "네이버페이"], "channels": {}},
    {"name": "토스증권", "industry": "금융/보험", "type": "company", "brand": "토스증권", "website": "tossinvest.com", "aliases": ["Toss Securities"], "channels": {}},
    {"name": "핀다", "industry": "금융/보험", "type": "company", "brand": "핀다", "website": "finda.co.kr", "aliases": ["Finda"], "channels": {}},
    {"name": "뱅크샐러드", "industry": "금융/보험", "type": "company", "brand": "뱅크샐러드", "website": "banksalad.com", "aliases": ["Banksalad"], "channels": {}},
    {"name": "새마을금고중앙회", "industry": "금융/보험", "type": "company", "brand": "새마을금고", "website": "kfcc.co.kr", "aliases": ["KFCC"], "channels": {}},
    {"name": "NH농협은행", "industry": "금융/보험", "type": "company", "brand": "NH농협", "website": "nhbank.com", "aliases": ["NH Bank", "농협은행"], "channels": {}},
    {"name": "KB금융지주", "industry": "금융/보험", "type": "company", "brand": "KB금융", "website": "kbfg.com", "aliases": ["KB Financial Group"], "channels": {}},
    {"name": "신한금융지주", "industry": "금융/보험", "type": "company", "brand": "신한금융", "website": "shinhangroup.com", "aliases": ["Shinhan Financial"], "channels": {}},
    {"name": "하나금융지주", "industry": "금융/보험", "type": "company", "brand": "하나금융", "website": "hanafn.com", "aliases": ["Hana Financial"], "channels": {}},
    {"name": "우리금융지주", "industry": "금융/보험", "type": "company", "brand": "우리금융", "website": "woorifg.com", "aliases": ["Woori Financial"], "channels": {}},
    {"name": "DGB금융지주", "industry": "금융/보험", "type": "company", "brand": "DGB", "website": "dgbfn.com", "aliases": ["DGB Financial"], "channels": {}},
    {"name": "BNK금융지주", "industry": "금융/보험", "type": "company", "brand": "BNK", "website": "bnkfg.com", "aliases": ["BNK Financial"], "channels": {}},

    # ═══════════════════════════════════════════
    # 식품/음료 추가
    # ═══════════════════════════════════════════
    {"name": "CJ푸드빌", "industry": "식품/음료", "type": "company", "brand": "빕스/뚜레쥬르", "website": "cjfoodville.co.kr", "aliases": ["CJ Foodville", "빕스", "뚜레쥬르"], "channels": {}},
    {"name": "하림", "industry": "식품/음료", "type": "company", "brand": "하림", "website": "harim.com", "aliases": ["Harim"], "channels": {}},
    {"name": "동원F&B", "industry": "식품/음료", "type": "company", "brand": "동원참치", "website": "dongwonfnb.com", "aliases": ["Dongwon"], "channels": {}},
    {"name": "정관장", "industry": "식품/음료", "type": "company", "brand": "정관장", "website": "kgc.co.kr", "aliases": ["CheongKwanJang", "한국인삼공사"], "channels": {"youtube": "https://www.youtube.com/@cheongkwanjang"}},
    {"name": "매일유업", "industry": "식품/음료", "type": "company", "brand": "매일유업", "website": "maeil.com", "aliases": ["Maeil Dairies", "상하목장"], "channels": {}},
    {"name": "남양유업", "industry": "식품/음료", "type": "company", "brand": "남양유업", "website": "namyangi.com", "aliases": ["Namyang"], "channels": {}},
    {"name": "한국야쿠르트", "industry": "식품/음료", "type": "company", "brand": "HY", "website": "hy.co.kr", "aliases": ["HY", "Yakult Korea"], "channels": {}},
    {"name": "파리크라상", "industry": "식품/음료", "type": "company", "brand": "파리바게뜨", "website": "paris.co.kr", "aliases": ["Paris Baguette", "파리바게뜨", "SPC그룹"], "channels": {}},
    {"name": "네슬레코리아", "industry": "식품/음료", "type": "company", "brand": "네스카페/네슬레", "website": "nestle.co.kr", "aliases": ["Nestle Korea"], "channels": {}},
    {"name": "롯데네슬레코리아", "industry": "식품/음료", "type": "company", "brand": "네스카페", "website": "nescafe.co.kr", "aliases": ["Lotte Nestle"], "channels": {}},
    {"name": "한국피앤지", "industry": "식품/음료", "type": "company", "brand": "P&G", "website": "pg.com/ko-kr", "aliases": ["P&G Korea", "피앤지"], "channels": {}},
    {"name": "샘표식품", "industry": "식품/음료", "type": "company", "brand": "샘표", "website": "sempio.com", "aliases": ["Sempio"], "channels": {}},
    {"name": "대상", "industry": "식품/음료", "type": "company", "brand": "청정원/종가", "website": "daesang.com", "aliases": ["Daesang", "청정원", "종가"], "channels": {}},
    {"name": "SPC그룹", "industry": "식품/음료", "type": "company", "brand": "파리바게뜨/던킨/배스킨라빈스", "website": "spc.co.kr", "aliases": ["SPC Group", "배스킨라빈스", "던킨도너츠"], "channels": {}},
    {"name": "GS리테일", "industry": "유통/이커머스", "type": "company", "brand": "GS25/GS더프레시", "website": "gsretail.com", "aliases": ["GS Retail", "GS25"], "channels": {}},
    {"name": "BGF리테일", "industry": "유통/이커머스", "type": "company", "brand": "CU", "website": "bgfretail.com", "aliases": ["BGF Retail", "CU편의점"], "channels": {}},
    {"name": "피자헛", "industry": "식품/음료", "type": "company", "brand": "피자헛", "website": "pizzahut.co.kr", "aliases": ["Pizza Hut Korea"], "channels": {}},
    {"name": "비알코리아", "industry": "식품/음료", "type": "company", "brand": "던킨/배스킨라빈스", "website": "brkorea.co.kr", "aliases": ["BR Korea", "배스킨라빈스"], "channels": {}},
    {"name": "한국마즈", "industry": "식품/음료", "type": "company", "brand": "엠앤엠즈/스니커즈", "website": "mars.com/ko-kr", "aliases": ["Mars Korea", "엠앤엠즈"], "channels": {}},
    {"name": "페레로아시아", "industry": "식품/음료", "type": "company", "brand": "페레로/누텔라/킨더", "website": "ferrero.com", "aliases": ["Ferrero", "누텔라", "킨더"], "channels": {}},
    {"name": "서브웨이코리아", "industry": "식품/음료", "type": "company", "brand": "서브웨이", "website": "subway.co.kr", "aliases": ["Subway Korea"], "channels": {}},

    # ═══════════════════════════════════════════
    # 뷰티/화장품 추가
    # ═══════════════════════════════════════════
    {"name": "한국콜마", "industry": "뷰티/화장품", "type": "company", "brand": "한국콜마", "website": "kolmar.co.kr", "aliases": ["Kolmar Korea"], "channels": {}},
    {"name": "코스맥스", "industry": "뷰티/화장품", "type": "company", "brand": "코스맥스", "website": "cosmax.com", "aliases": ["Cosmax"], "channels": {}},
    {"name": "애경산업", "industry": "뷰티/화장품", "type": "company", "brand": "AGE20's/루나", "website": "aekyung.co.kr", "aliases": ["Aekyung", "에이지투웨니스"], "channels": {}},
    {"name": "에이피알", "industry": "뷰티/화장품", "type": "company", "brand": "메디큐브/에이프릴스킨", "website": "apr.co.kr", "aliases": ["APR", "메디큐브", "에이프릴스킨"], "channels": {}},
    {"name": "달바글로벌", "industry": "뷰티/화장품", "type": "company", "brand": "d'Alba", "website": "dalba.co.kr", "aliases": ["d'Alba"], "channels": {}},
    {"name": "토리든", "industry": "뷰티/화장품", "type": "company", "brand": "토리든", "website": "torriden.com", "aliases": ["Torriden"], "channels": {}},
    {"name": "로레알코리아", "industry": "뷰티/화장품", "type": "company", "brand": "로레알/랑콤/키엘", "website": "loreal.co.kr", "aliases": ["L'Oreal Korea", "랑콤", "키엘"], "channels": {}},
    {"name": "유니레버코리아", "industry": "뷰티/화장품", "type": "company", "brand": "도브/바세린", "website": "unilever.co.kr", "aliases": ["Unilever Korea", "도브"], "channels": {}},
    {"name": "옥시레킷벤키저", "industry": "뷰티/화장품", "type": "company", "brand": "옥시/듀렉스/에어윅", "website": "reckitt.com/kr", "aliases": ["Reckitt Korea", "옥시"], "channels": {}},
    {"name": "유한킴벌리", "industry": "뷰티/화장품", "type": "company", "brand": "크리넥스/좋은느낌", "website": "yuhan-kimberly.co.kr", "aliases": ["Yuhan-Kimberly", "크리넥스"], "channels": {}},
    {"name": "아이소이", "industry": "뷰티/화장품", "type": "company", "brand": "아이소이", "website": "isoi.co.kr", "aliases": ["ISOI"], "channels": {}},
    {"name": "스킨푸드", "industry": "뷰티/화장품", "type": "company", "brand": "스킨푸드", "website": "theskinfood.com", "aliases": ["Skinfood"], "channels": {}},
    {"name": "AHC", "industry": "뷰티/화장품", "type": "company", "brand": "AHC", "website": "ahc.co.kr", "aliases": ["AHC"], "channels": {}},
    {"name": "바닐라코", "industry": "뷰티/화장품", "type": "company", "brand": "바닐라코", "website": "banilaco.com", "aliases": ["Banila Co"], "channels": {}},
    {"name": "네이처리퍼블릭", "industry": "뷰티/화장품", "type": "company", "brand": "네이처리퍼블릭", "website": "naturerepublic.com", "aliases": ["Nature Republic"], "channels": {}},
    {"name": "홀리카홀리카", "industry": "뷰티/화장품", "type": "company", "brand": "홀리카홀리카", "website": "holikaholika.co.kr", "aliases": ["Holika Holika"], "channels": {}},
    {"name": "엘앤피코스메틱", "industry": "뷰티/화장품", "type": "company", "brand": "메디힐", "website": "mediheal.com", "aliases": ["L&P Cosmetic", "메디힐"], "channels": {}},
    {"name": "에스트라", "industry": "뷰티/화장품", "type": "company", "brand": "에스트라/아토배리어", "website": "aestura.com", "aliases": ["Aestura", "아토배리어"], "channels": {}},

    # ═══════════════════════════════════════════
    # 패션/의류 추가
    # ═══════════════════════════════════════════
    {"name": "삼성물산패션", "industry": "패션/의류", "type": "company", "brand": "빈폴/구호/준지", "website": "samsungfashion.com", "aliases": ["Samsung Fashion", "빈폴"], "channels": {}},
    {"name": "한섬", "industry": "패션/의류", "type": "company", "brand": "타임/마인/시스템", "website": "thehandsome.com", "aliases": ["Handsome Corp", "타임", "마인"], "channels": {}},
    {"name": "코오롱인더스트리FnC", "industry": "패션/의류", "type": "company", "brand": "코오롱스포츠/캠브리지", "website": "kolonmall.com", "aliases": ["Kolon FnC", "코오롱스포츠"], "channels": {}},
    {"name": "F&F", "industry": "패션/의류", "type": "company", "brand": "MLB/디스커버리", "website": "fnf.co.kr", "aliases": ["F&F", "MLB", "디스커버리"], "channels": {}},
    {"name": "LF", "industry": "패션/의류", "type": "company", "brand": "닥스/헤지스/질스튜어트", "website": "lfcorp.com", "aliases": ["LF Corp", "닥스", "헤지스"], "channels": {}},
    {"name": "신세계인터내셔날", "industry": "패션/의류", "type": "company", "brand": "자주/스튜디오톰보이", "website": "sikorea.co.kr", "aliases": ["SI", "자주"], "channels": {}},
    {"name": "에이블리코퍼레이션", "industry": "패션/의류", "type": "company", "brand": "에이블리", "website": "ably.team", "aliases": ["Ably"], "channels": {}},
    {"name": "지그재그", "industry": "패션/의류", "type": "company", "brand": "지그재그", "website": "zigzag.kr", "aliases": ["Zigzag", "카카오스타일"], "channels": {}},
    {"name": "브랜디", "industry": "패션/의류", "type": "company", "brand": "브랜디/하이버", "website": "brandi.co.kr", "aliases": ["Brandi"], "channels": {}},
    {"name": "구찌코리아", "industry": "패션/의류", "type": "company", "brand": "구찌", "website": "gucci.com/kr", "aliases": ["Gucci Korea"], "channels": {}},
    {"name": "루이비통코리아", "industry": "패션/의류", "type": "company", "brand": "루이비통", "website": "louisvuitton.com/kor-kr", "aliases": ["Louis Vuitton Korea", "LV"], "channels": {}},
    {"name": "샤넬코리아", "industry": "패션/의류", "type": "company", "brand": "샤넬", "website": "chanel.com/kr", "aliases": ["Chanel Korea"], "channels": {}},
    {"name": "에르메스코리아", "industry": "패션/의류", "type": "company", "brand": "에르메스", "website": "hermes.com/kr", "aliases": ["Hermes Korea"], "channels": {}},
    {"name": "디올코리아", "industry": "패션/의류", "type": "company", "brand": "디올", "website": "dior.com/ko_kr", "aliases": ["Dior Korea"], "channels": {}},
    {"name": "프라다코리아", "industry": "패션/의류", "type": "company", "brand": "프라다", "website": "prada.com/kr", "aliases": ["Prada Korea"], "channels": {}},
    {"name": "발렌시아가코리아", "industry": "패션/의류", "type": "company", "brand": "발렌시아가", "website": "balenciaga.com/kr", "aliases": ["Balenciaga Korea"], "channels": {}},
    {"name": "리바이스코리아", "industry": "패션/의류", "type": "company", "brand": "리바이스", "website": "levi.co.kr", "aliases": ["Levi's Korea"], "channels": {}},
    {"name": "H&M코리아", "industry": "패션/의류", "type": "company", "brand": "H&M", "website": "hm.com/ko_kr", "aliases": ["H&M Korea"], "channels": {}},
    {"name": "스파오", "industry": "패션/의류", "type": "company", "brand": "스파오/탑텐", "website": "spao.com", "aliases": ["SPAO", "이랜드"], "channels": {}},
    {"name": "탑텐", "industry": "패션/의류", "type": "company", "brand": "탑텐", "website": "topten10.co.kr", "aliases": ["TOPTEN", "신성통상"], "channels": {}},

    # ═══════════════════════════════════════════
    # 자동차 추가
    # ═══════════════════════════════════════════
    {"name": "한국토요타자동차", "industry": "자동차", "type": "company", "brand": "토요타/렉서스", "website": "toyota.co.kr", "aliases": ["Toyota Korea", "렉서스"], "channels": {}},
    {"name": "포드코리아", "industry": "자동차", "type": "company", "brand": "포드/링컨", "website": "ford.co.kr", "aliases": ["Ford Korea", "링컨"], "channels": {}},
    {"name": "재규어랜드로버코리아", "industry": "자동차", "type": "company", "brand": "재규어/랜드로버", "website": "jaguar.co.kr", "aliases": ["JLR Korea", "랜드로버"], "channels": {}},
    {"name": "포르쉐코리아", "industry": "자동차", "type": "company", "brand": "포르쉐", "website": "porsche.com/korea", "aliases": ["Porsche Korea"], "channels": {}},
    {"name": "혼다코리아", "industry": "자동차", "type": "company", "brand": "혼다", "website": "honda.co.kr", "aliases": ["Honda Korea"], "channels": {}},
    {"name": "미니코리아", "industry": "자동차", "type": "company", "brand": "미니", "website": "mini.co.kr", "aliases": ["MINI Korea"], "channels": {}},
    {"name": "한국GM", "industry": "자동차", "type": "company", "brand": "쉐보레", "website": "gm-korea.co.kr", "aliases": ["GM Korea", "쉐보레"], "channels": {}},

    # ═══════════════════════════════════════════
    # 가전/전자 추가
    # ═══════════════════════════════════════════
    {"name": "SK매직", "industry": "가전/전자", "type": "company", "brand": "SK매직", "website": "skmagic.com", "aliases": ["SK Magic"], "channels": {}},
    {"name": "청호나이스", "industry": "가전/전자", "type": "company", "brand": "청호나이스", "website": "chungho.co.kr", "aliases": ["Chungho Nais"], "channels": {}},
    {"name": "경동나비엔", "industry": "가전/전자", "type": "company", "brand": "나비엔", "website": "kdnavien.co.kr", "aliases": ["KD Navien", "나비엔"], "channels": {}},
    {"name": "바디프랜드", "industry": "가전/전자", "type": "company", "brand": "바디프랜드", "website": "bodyfriend.co.kr", "aliases": ["Bodyfriend"], "channels": {}},
    {"name": "LG시그니처", "industry": "가전/전자", "type": "company", "brand": "LG시그니처", "website": "lg.com/signature", "aliases": ["LG Signature"], "channels": {}},
    {"name": "보쉬코리아", "industry": "가전/전자", "type": "company", "brand": "보쉬", "website": "bosch-home.co.kr", "aliases": ["Bosch Korea"], "channels": {}},
    {"name": "밀레코리아", "industry": "가전/전자", "type": "company", "brand": "밀레", "website": "miele.co.kr", "aliases": ["Miele Korea"], "channels": {}},
    {"name": "귀뚜라미보일러", "industry": "가전/전자", "type": "company", "brand": "귀뚜라미", "website": "kiturami.co.kr", "aliases": ["Kiturami"], "channels": {}},
    {"name": "대성산업", "industry": "가전/전자", "type": "company", "brand": "대성셀틱", "website": "daesung.co.kr", "aliases": ["Daesung"], "channels": {}},

    # ═══════════════════════════════════════════
    # 게임 추가
    # ═══════════════════════════════════════════
    {"name": "슈퍼셀", "industry": "게임", "type": "company", "brand": "클래시로얄/브롤스타즈", "website": "supercell.com", "aliases": ["Supercell"], "channels": {}},
    {"name": "위메이드", "industry": "게임", "type": "company", "brand": "미르4", "website": "wemade.com", "aliases": ["Wemade"], "channels": {}},
    {"name": "엔씨소프트", "industry": "게임", "type": "company", "brand": "리니지/블레이드앤소울", "website": "ncsoft.com", "aliases": ["NCsoft", "리니지"], "channels": {"youtube": "https://www.youtube.com/@NCsoft"}},
    {"name": "넥슨게임즈", "industry": "게임", "type": "company", "brand": "블루아카이브", "website": "nexongames.co.kr", "aliases": ["Nexon Games"], "channels": {}},
    {"name": "호요버스", "industry": "게임", "type": "company", "brand": "원신/붕괴스타레일", "website": "hoyoverse.com", "aliases": ["HoYoverse", "미호요"], "channels": {}},
    {"name": "라이엇게임즈코리아", "industry": "게임", "type": "company", "brand": "리그오브레전드/발로란트", "website": "riotgames.com/ko-kr", "aliases": ["Riot Games Korea", "LoL"], "channels": {}},
    {"name": "블리자드엔터테인먼트코리아", "industry": "게임", "type": "company", "brand": "오버워치/디아블로", "website": "blizzard.com/ko-kr", "aliases": ["Blizzard Korea"], "channels": {}},
    {"name": "엔드림", "industry": "게임", "type": "company", "brand": "세븐나이츠", "website": "netmarble.com", "aliases": ["Ndream"], "channels": {}},
    {"name": "시프트업", "industry": "게임", "type": "company", "brand": "니케/스텔라블레이드", "website": "shiftup.co.kr", "aliases": ["SHIFT UP", "니케"], "channels": {}},

    # ═══════════════════════════════════════════
    # 엔터테인먼트 추가
    # ═══════════════════════════════════════════
    {"name": "카카오엔터테인먼트", "industry": "엔터테인먼트", "type": "company", "brand": "카카오엔터/멜론", "website": "kakaoent.com", "aliases": ["Kakao Ent", "멜론"], "channels": {}},
    {"name": "스튜디오드래곤", "industry": "엔터테인먼트", "type": "company", "brand": "스튜디오드래곤", "website": "studiodragon.net", "aliases": ["Studio Dragon"], "channels": {}},
    {"name": "빅히트뮤직", "industry": "엔터테인먼트", "type": "company", "brand": "빅히트/방탄소년단", "website": "bighitmusic.com", "aliases": ["BigHit Music", "BTS"], "channels": {}},
    {"name": "쿠팡플레이", "industry": "엔터테인먼트", "type": "company", "brand": "쿠팡플레이", "website": "coupangplay.com", "aliases": ["Coupang Play"], "channels": {}},
    {"name": "애플TV플러스", "industry": "엔터테인먼트", "type": "company", "brand": "Apple TV+", "website": "tv.apple.com/kr", "aliases": ["Apple TV+"], "channels": {}},
    {"name": "아마존프라임비디오", "industry": "엔터테인먼트", "type": "company", "brand": "프라임비디오", "website": "primevideo.com", "aliases": ["Amazon Prime Video"], "channels": {}},
    {"name": "스포티파이코리아", "industry": "엔터테인먼트", "type": "company", "brand": "스포티파이", "website": "spotify.com/kr", "aliases": ["Spotify Korea"], "channels": {}},

    # ═══════════════════════════════════════════
    # 제약/헬스케어 추가
    # ═══════════════════════════════════════════
    {"name": "종근당건강", "industry": "제약/헬스케어", "type": "company", "brand": "락토핏/아이클리어", "website": "ckdhc.com", "aliases": ["CKD Health", "락토핏"], "channels": {}},
    {"name": "한미약품", "industry": "제약/헬스케어", "type": "company", "brand": "한미약품", "website": "hanmi.co.kr", "aliases": ["Hanmi Pharm"], "channels": {}},
    {"name": "동국제약", "industry": "제약/헬스케어", "type": "company", "brand": "마데카솔/센시아", "website": "dkpharm.co.kr", "aliases": ["Dongkook Pharm", "마데카솔"], "channels": {}},
    {"name": "명인제약", "industry": "제약/헬스케어", "type": "company", "brand": "명인제약", "website": "myungin.com", "aliases": ["Myungin Pharm"], "channels": {}},
    {"name": "삼진제약", "industry": "제약/헬스케어", "type": "company", "brand": "삼진제약/게보린", "website": "samjinpharm.co.kr", "aliases": ["Samjin Pharm", "게보린"], "channels": {}},
    {"name": "GC녹십자", "industry": "제약/헬스케어", "type": "company", "brand": "GC녹십자", "website": "greencross.com", "aliases": ["Green Cross"], "channels": {}},
    {"name": "종근당", "industry": "제약/헬스케어", "type": "company", "brand": "종근당", "website": "ckdpharm.com", "aliases": ["CKD Pharm"], "channels": {}},
    {"name": "글락소스미스클라인", "industry": "제약/헬스케어", "type": "company", "brand": "GSK/센소다인/볼타렌", "website": "gsk.com/ko-kr", "aliases": ["GSK Korea", "센소다인"], "channels": {}},
    {"name": "화이자코리아", "industry": "제약/헬스케어", "type": "company", "brand": "화이자/센트룸", "website": "pfizer.co.kr", "aliases": ["Pfizer Korea", "센트룸"], "channels": {}},
    {"name": "사노피코리아", "industry": "제약/헬스케어", "type": "company", "brand": "사노피/둘코락스", "website": "sanofi.co.kr", "aliases": ["Sanofi Korea"], "channels": {}},
    {"name": "대한보청기", "industry": "제약/헬스케어", "type": "company", "brand": "대한보청기", "website": "hear.co.kr", "aliases": ["Daehan Hearing"], "channels": {}},
    {"name": "하이모", "industry": "제약/헬스케어", "type": "company", "brand": "하이모", "website": "himo.co.kr", "aliases": ["Himo"], "channels": {}},
    {"name": "안국건강", "industry": "제약/헬스케어", "type": "company", "brand": "안국건강", "website": "ankook.com", "aliases": ["Ankook"], "channels": {}},
    {"name": "일동후디스", "industry": "제약/헬스케어", "type": "company", "brand": "후디스/하이뮨", "website": "ildongfoodis.com", "aliases": ["Ildong Foodis", "하이뮨"], "channels": {}},
    {"name": "뉴트리원", "industry": "제약/헬스케어", "type": "company", "brand": "뉴트리원/BBLab", "website": "nutrione.co.kr", "aliases": ["Nutrione"], "channels": {}},
    {"name": "휴젤", "industry": "제약/헬스케어", "type": "company", "brand": "보톡스/필러", "website": "hugel.co.kr", "aliases": ["Hugel"], "channels": {}},

    # ═══════════════════════════════════════════
    # 교육 추가
    # ═══════════════════════════════════════════
    {"name": "대성마이맥", "industry": "교육", "type": "company", "brand": "대성/마이맥", "website": "mimacstudy.com", "aliases": ["Daesung Mimac"], "channels": {}},
    {"name": "비상교육", "industry": "교육", "type": "company", "brand": "비상/와이즈캠프", "website": "visang.com", "aliases": ["Visang", "와이즈캠프"], "channels": {}},
    {"name": "웅진씽크빅", "industry": "교육", "type": "company", "brand": "웅진스마트올", "website": "wjthinkbig.com", "aliases": ["Woongjin Thinkbig", "스마트올"], "channels": {}},
    {"name": "천재교과서", "industry": "교육", "type": "company", "brand": "밀크T", "website": "milkt.co.kr", "aliases": ["Chunjae", "밀크T"], "channels": {}},
    {"name": "대교", "industry": "교육", "type": "company", "brand": "눈높이", "website": "daekyo.com", "aliases": ["Daekyo", "눈높이"], "channels": {}},
    {"name": "해커스어학원", "industry": "교육", "type": "company", "brand": "해커스", "website": "hackers.ac", "aliases": ["Hackers"], "channels": {}},
    {"name": "야나두", "industry": "교육", "type": "company", "brand": "야나두", "website": "yanadoo.co.kr", "aliases": ["Yanadoo"], "channels": {}},
    {"name": "엘리하이", "industry": "교육", "type": "company", "brand": "엘리하이/엠베스트", "website": "elhi.co.kr", "aliases": ["Eli High", "엠베스트"], "channels": {}},
    {"name": "아이스크림에듀", "industry": "교육", "type": "company", "brand": "아이스크림홈런", "website": "home-learn.co.kr", "aliases": ["i-Scream Edu", "홈런"], "channels": {}},
    {"name": "윌비스", "industry": "교육", "type": "company", "brand": "에듀윌", "website": "eduwill.net", "aliases": ["Eduwill"], "channels": {}},

    # ═══════════════════════════════════════════
    # 여행/항공 추가
    # ═══════════════════════════════════════════
    {"name": "여기어때", "industry": "여행/항공", "type": "company", "brand": "여기어때", "website": "yeogi.com", "aliases": ["Goodchoice", "여기어때컴퍼니"], "channels": {}},
    {"name": "에어부산", "industry": "여행/항공", "type": "company", "brand": "에어부산", "website": "airbusan.com", "aliases": ["Air Busan"], "channels": {}},
    {"name": "티웨이항공", "industry": "여행/항공", "type": "company", "brand": "티웨이항공", "website": "twayair.com", "aliases": ["T'way Air"], "channels": {}},
    {"name": "노랑풍선", "industry": "여행/항공", "type": "company", "brand": "노랑풍선", "website": "ybtour.co.kr", "aliases": ["Yellow Balloon"], "channels": {}},
    {"name": "모두투어", "industry": "여행/항공", "type": "company", "brand": "모두투어", "website": "modetour.com", "aliases": ["Modetour"], "channels": {}},
    {"name": "마이리얼트립", "industry": "여행/항공", "type": "company", "brand": "마이리얼트립", "website": "myrealtrip.com", "aliases": ["My Real Trip"], "channels": {}},
    {"name": "클룩", "industry": "여행/항공", "type": "company", "brand": "클룩", "website": "klook.com/ko", "aliases": ["Klook Korea"], "channels": {}},

    # ═══════════════════════════════════════════
    # 이커머스/플랫폼 추가
    # ═══════════════════════════════════════════
    {"name": "알리익스프레스", "industry": "유통/이커머스", "type": "company", "brand": "알리익스프레스", "website": "aliexpress.com", "aliases": ["AliExpress", "알리"], "channels": {}},
    {"name": "테무", "industry": "유통/이커머스", "type": "company", "brand": "테무", "website": "temu.com", "aliases": ["Temu"], "channels": {}},
    {"name": "쉬인", "industry": "유통/이커머스", "type": "company", "brand": "쉬인", "website": "shein.com", "aliases": ["SHEIN"], "channels": {}},
    {"name": "아마존코리아", "industry": "유통/이커머스", "type": "company", "brand": "아마존", "website": "amazon.co.kr", "aliases": ["Amazon Korea"], "channels": {}},
    {"name": "NS홈쇼핑", "industry": "유통/이커머스", "type": "company", "brand": "NS홈쇼핑", "website": "nsmall.com", "aliases": ["NS Home Shopping"], "channels": {}},
    {"name": "홈앤쇼핑", "industry": "유통/이커머스", "type": "company", "brand": "홈앤쇼핑", "website": "hnsmall.com", "aliases": ["Home and Shopping"], "channels": {}},
    {"name": "롯데ON", "industry": "유통/이커머스", "type": "company", "brand": "롯데ON", "website": "lotteon.com", "aliases": ["Lotte ON"], "channels": {}},
    {"name": "오늘의집", "industry": "가구/인테리어", "type": "company", "brand": "오늘의집", "website": "ohou.se", "aliases": ["Today's House", "버킷플레이스"], "channels": {}},
    {"name": "당근", "industry": "유통/이커머스", "type": "company", "brand": "당근", "website": "daangn.com", "aliases": ["Daangn", "당근마켓"], "channels": {}},

    # ═══════════════════════════════════════════
    # 배달/O2O 추가
    # ═══════════════════════════════════════════
    {"name": "요기요", "industry": "유통/이커머스", "type": "company", "brand": "요기요", "website": "yogiyo.co.kr", "aliases": ["Yogiyo"], "channels": {}},
    {"name": "쿠팡이츠", "industry": "유통/이커머스", "type": "company", "brand": "쿠팡이츠", "website": "coupangeats.com", "aliases": ["Coupang Eats"], "channels": {}},
    {"name": "땡겨요", "industry": "유통/이커머스", "type": "company", "brand": "땡겨요", "website": "ttang.co.kr", "aliases": ["Ttangyeyo"], "channels": {}},

    # ═══════════════════════════════════════════
    # IT/통신 추가
    # ═══════════════════════════════════════════
    {"name": "구글코리아", "industry": "IT/통신", "type": "company", "brand": "구글/유튜브", "website": "google.co.kr", "aliases": ["Google Korea", "유튜브"], "channels": {}},
    {"name": "메타코리아", "industry": "IT/통신", "type": "company", "brand": "메타/인스타그램/페이스북", "website": "about.meta.com", "aliases": ["Meta Korea", "페이스북코리아"], "channels": {}},
    {"name": "마이크로소프트코리아", "industry": "IT/통신", "type": "company", "brand": "마이크로소프트", "website": "microsoft.com/ko-kr", "aliases": ["Microsoft Korea", "MS코리아"], "channels": {}},
    {"name": "SK브로드밴드", "industry": "IT/통신", "type": "company", "brand": "Btv/SKB", "website": "skbroadband.com", "aliases": ["SK Broadband", "B tv"], "channels": {}},
    {"name": "SK플래닛", "industry": "IT/통신", "type": "company", "brand": "시럽/OK캐쉬백", "website": "skplanet.com", "aliases": ["SK Planet", "시럽"], "channels": {}},
    {"name": "두나무", "industry": "IT/통신", "type": "company", "brand": "업비트", "website": "dunamu.com", "aliases": ["Dunamu", "업비트"], "channels": {}},
    {"name": "빗썸코리아", "industry": "IT/통신", "type": "company", "brand": "빗썸", "website": "bithumb.com", "aliases": ["Bithumb"], "channels": {}},
    {"name": "크래프톤", "industry": "게임", "type": "company", "brand": "배틀그라운드/배그", "website": "krafton.com", "aliases": ["Krafton", "배그", "PUBG"], "channels": {"youtube": "https://www.youtube.com/@PUBG"}},

    # ═══════════════════════════════════════════
    # 주류 추가
    # ═══════════════════════════════════════════
    {"name": "국순당", "industry": "주류", "type": "company", "brand": "국순당막걸리", "website": "ksdb.co.kr", "aliases": ["Kooksoondang"], "channels": {}},
    {"name": "보해양조", "industry": "주류", "type": "company", "brand": "보해", "website": "bohae.co.kr", "aliases": ["Bohae"], "channels": {}},
    {"name": "디아지오코리아", "industry": "주류", "type": "company", "brand": "조니워커/기네스/윈저", "website": "diageo.com", "aliases": ["Diageo Korea", "윈저", "조니워커"], "channels": {}},
    {"name": "페르노리카코리아", "industry": "주류", "type": "company", "brand": "앱솔루트/발렌타인", "website": "pernod-ricard.com", "aliases": ["Pernod Ricard Korea", "앱솔루트"], "channels": {}},

    # ═══════════════════════════════════════════
    # 스포츠/아웃도어 추가
    # ═══════════════════════════════════════════
    {"name": "휠라코리아", "industry": "스포츠/아웃도어", "type": "company", "brand": "휠라", "website": "fila.co.kr", "aliases": ["FILA Korea"], "channels": {}},
    {"name": "아식스코리아", "industry": "스포츠/아웃도어", "type": "company", "brand": "아식스/오니츠카타이거", "website": "asics.com/kr", "aliases": ["ASICS Korea"], "channels": {}},
    {"name": "리닝코리아", "industry": "스포츠/아웃도어", "type": "company", "brand": "리닝", "website": "lining.com", "aliases": ["Li-Ning Korea"], "channels": {}},
    {"name": "살로몬코리아", "industry": "스포츠/아웃도어", "type": "company", "brand": "살로몬", "website": "salomon.com/ko-kr", "aliases": ["Salomon Korea"], "channels": {}},
    {"name": "호카", "industry": "스포츠/아웃도어", "type": "company", "brand": "호카", "website": "hoka.com/ko", "aliases": ["HOKA"], "channels": {}},
    {"name": "레드페이스", "industry": "스포츠/아웃도어", "type": "company", "brand": "레드페이스", "website": "theredface.com", "aliases": ["The Redface"], "channels": {}},
    {"name": "블랙야크", "industry": "스포츠/아웃도어", "type": "company", "brand": "블랙야크", "website": "blackyak.com", "aliases": ["Blackyak"], "channels": {}},
    {"name": "아이더", "industry": "스포츠/아웃도어", "type": "company", "brand": "아이더", "website": "eider.co.kr", "aliases": ["Eider"], "channels": {}},
    {"name": "컬럼비아코리아", "industry": "스포츠/아웃도어", "type": "company", "brand": "컬럼비아", "website": "columbia.co.kr", "aliases": ["Columbia Korea"], "channels": {}},
    {"name": "나이키골프", "industry": "스포츠/아웃도어", "type": "company", "brand": "나이키골프", "website": "nike.com/kr", "aliases": ["Nike Golf"], "channels": {}},
    {"name": "타이틀리스트코리아", "industry": "스포츠/아웃도어", "type": "company", "brand": "타이틀리스트", "website": "titleist.co.kr", "aliases": ["Titleist Korea"], "channels": {}},

    # ═══════════════════════════════════════════
    # 공공기관/정부 추가
    # ═══════════════════════════════════════════
    {"name": "한국토지주택공사", "industry": "공공기관", "type": "government", "brand": "LH", "website": "lh.or.kr", "aliases": ["LH", "한국토지주택공사"], "channels": {}},
    {"name": "우정사업본부", "industry": "공공기관", "type": "government", "brand": "우체국", "website": "koreapost.go.kr", "aliases": ["Korea Post", "우체국"], "channels": {}},
    {"name": "소상공인시장진흥공단", "industry": "공공기관", "type": "government", "brand": "소진공", "website": "semas.or.kr", "aliases": ["SEMAS"], "channels": {}},
    {"name": "국민건강보험공단", "industry": "공공기관", "type": "government", "brand": "건보공단", "website": "nhis.or.kr", "aliases": ["NHIS"], "channels": {}},
    {"name": "한국관광공사", "industry": "공공기관", "type": "government", "brand": "한국관광", "website": "visitkorea.or.kr", "aliases": ["KTO"], "channels": {}},
    {"name": "방위사업청", "industry": "공공기관", "type": "government", "brand": "DAPA", "website": "dapa.go.kr", "aliases": ["DAPA"], "channels": {}},
    {"name": "KBS", "industry": "공공기관", "type": "government", "brand": "KBS", "website": "kbs.co.kr", "aliases": ["한국방송"], "channels": {"youtube": "https://www.youtube.com/@KBS"}},

    # ═══════════════════════════════════════════
    # 가구/인테리어 추가
    # ═══════════════════════════════════════════
    {"name": "시디즈", "industry": "가구/인테리어", "type": "company", "brand": "시디즈", "website": "sidiz.com", "aliases": ["SIDIZ"], "channels": {}},
    {"name": "일룸", "industry": "가구/인테리어", "type": "company", "brand": "일룸", "website": "iloom.com", "aliases": ["iloom"], "channels": {}},
    {"name": "에이스침대", "industry": "가구/인테리어", "type": "company", "brand": "에이스침대", "website": "acebed.co.kr", "aliases": ["ACE Bed"], "channels": {}},
    {"name": "시몬스", "industry": "가구/인테리어", "type": "company", "brand": "시몬스", "website": "simmons.co.kr", "aliases": ["Simmons Korea"], "channels": {}},

    # ═══════════════════════════════════════════
    # 반려동물 추가
    # ═══════════════════════════════════════════
    {"name": "하림펫푸드", "industry": "반려동물", "type": "company", "brand": "밥이보약/더리얼", "website": "harimpetfood.com", "aliases": ["Harim Pet Food"], "channels": {}},
    {"name": "인터파크펫", "industry": "반려동물", "type": "company", "brand": "인터파크펫", "website": "pet.interpark.com", "aliases": ["Interpark Pet"], "channels": {}},
    {"name": "네슬레퓨리나코리아", "industry": "반려동물", "type": "company", "brand": "퓨리나/프로플랜", "website": "purina.co.kr", "aliases": ["Purina Korea", "프로플랜"], "channels": {}},

    # ═══════════════════════════════════════════
    # 중국 이커머스 / 해외 광고주
    # ═══════════════════════════════════════════
    {"name": "바이트댄스코리아", "industry": "IT/통신", "type": "company", "brand": "틱톡", "website": "tiktok.com", "aliases": ["TikTok Korea", "ByteDance Korea", "틱톡"], "channels": {}},
    {"name": "트위터코리아", "industry": "IT/통신", "type": "company", "brand": "X(트위터)", "website": "x.com", "aliases": ["X Korea", "Twitter Korea"], "channels": {}},
    {"name": "라인플러스", "industry": "IT/통신", "type": "company", "brand": "라인", "website": "linepluscorp.com", "aliases": ["LINE Plus"], "channels": {}},
    {"name": "쿠팡", "industry": "유통/이커머스", "type": "company", "brand": "쿠팡/로켓배송", "website": "coupang.com", "aliases": ["Coupang", "로켓배송"], "channels": {"youtube": "https://www.youtube.com/@coupang"}},

    # ═══════════════════════════════════════════
    # 기타 주요 광고주
    # ═══════════════════════════════════════════
    {"name": "리치몬드코리아", "industry": "패션/의류", "type": "company", "brand": "까르띠에/몽블랑/IWC", "website": "richemont.com", "aliases": ["Richemont Korea", "까르띠에", "몽블랑"], "channels": {}},
    {"name": "스와치코리아", "industry": "패션/의류", "type": "company", "brand": "오메가/스와치/롱진", "website": "swatchgroup.com", "aliases": ["Swatch Korea", "오메가"], "channels": {}},
    {"name": "한국암웨이", "industry": "기타", "type": "company", "brand": "암웨이/뉴트리라이트", "website": "amway.co.kr", "aliases": ["Amway Korea"], "channels": {}},
    {"name": "옐로모바일", "industry": "IT/통신", "type": "company", "brand": "옐로모바일", "website": "yello-digital.com", "aliases": ["Yello Mobile", "옐로디지털마케팅"], "channels": {}},
    {"name": "문영그룹", "industry": "기타", "type": "company", "brand": "문영", "website": "moonyoung.co.kr", "aliases": ["Moonyoung Group"], "channels": {}},
    {"name": "이랜드그룹", "industry": "유통/이커머스", "type": "company", "brand": "이랜드/뉴발란스(한국)/스파오", "website": "eland.co.kr", "aliases": ["E-Land", "이랜드"], "channels": {}},
    {"name": "로레알코리아", "industry": "뷰티/화장품", "type": "company", "brand": "로레알파리/랑콤/키엘/메이블린", "website": "loreal.co.kr", "aliases": ["L'Oreal Korea"], "channels": {}},
]


def load_existing():
    """기존 시드 파일 로드"""
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_existing_names(data):
    """기존 광고주 이름 set"""
    names = set()
    for a in data.get("advertisers", []):
        names.add(a["name"])
        for alias in a.get("aliases", []):
            names.add(alias)
    return names


def main():
    # 백업
    data = load_existing()
    with open(BACKUP_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Backup saved: {BACKUP_PATH}")

    existing_names = get_existing_names(data)
    existing_lower = {n.lower() for n in existing_names}

    added = 0
    skipped = 0
    skipped_names = []

    for new_adv in NEW_ADVERTISERS:
        name = new_adv["name"]
        # 중복 체크 (이름/aliases)
        if name.lower() in existing_lower:
            skipped += 1
            skipped_names.append(name)
            continue
        # aliases 중복 체크
        dup = False
        for alias in new_adv.get("aliases", []):
            if alias.lower() in existing_lower:
                dup = True
                skipped += 1
                skipped_names.append(f"{name} (alias: {alias})")
                break
        if dup:
            continue

        data["advertisers"].append(new_adv)
        existing_lower.add(name.lower())
        for alias in new_adv.get("aliases", []):
            existing_lower.add(alias.lower())
        added += 1

    # 산업 카테고리에 '럭셔리/명품' 추가 (없으면)
    industry_names = {ind["name"] for ind in data.get("industries", [])}
    new_industries = [
        {"name": "럭셔리/명품", "avg_cpc_min": 600, "avg_cpc_max": 5000},
        {"name": "핀테크/금융서비스", "avg_cpc_min": 800, "avg_cpc_max": 6000},
        {"name": "플랫폼/O2O", "avg_cpc_min": 400, "avg_cpc_max": 3000},
    ]
    for ind in new_industries:
        if ind["name"] not in industry_names:
            data["industries"].append(ind)
            print(f"  + Industry: {ind['name']}")

    # 저장
    with open(SEED_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    total = len(data["advertisers"])
    print(f"\n=== Results ===")
    print(f"  Before: {total - added}")
    print(f"  Added:  {added}")
    print(f"  Skipped (duplicates): {skipped}")
    print(f"  Total:  {total}")
    print(f"\nSaved: {SEED_PATH}")

    if skipped_names:
        print(f"\nSkipped names (already exist):")
        for n in skipped_names[:20]:
            print(f"  - {n}")
        if len(skipped_names) > 20:
            print(f"  ... and {len(skipped_names) - 20} more")


if __name__ == "__main__":
    main()
