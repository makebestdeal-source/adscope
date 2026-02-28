"""
Reclassify advertisers currently in the "기타" (Other / industry_id=1) category
into proper industry categories using keyword-based matching on:
  - advertiser name
  - website domain
  - brand_name

Industry IDs:
  1: 기타              2: IT/통신           3: 자동차
  4: 금융/보험          5: 식품/음료          6: 뷰티/화장품
  7: 패션/의류          8: 유통/이커머스       9: 제약/헬스케어
 10: 가전/전자         11: 건설/부동산        12: 게임
 13: 엔터테인먼트       14: 여행/항공         15: 교육
 16: 스포츠/아웃도어     17: 가구/인테리어      18: 주류
 19: 공공기관          20: 반려동물          21: 생활용품
 22: mobile_web
"""
import sqlite3
import sys
import os
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'adscope.db')

# ── Keyword rules: (industry_id, [name_keywords], [domain_keywords]) ──
# Order matters: more specific rules first, broader rules later.
# Each advertiser is matched against ALL rules; first match wins.

RULES = [
    # ─── 20: 반려동물 ───
    (20, [
        '반려동물', '강아지', '애견', '펫', '도그', '냥', '견생', '퍼피',
        '동물병원', '동물장례', '동물암', '사랑애견', '해피펫', '스타펫',
        '프론투라인',  # 동물 의약품
        'LG유니참',  # 펫케어
        '레인보우엔젤', '하늘사랑', '이별공간',
    ], ['pet', 'dog', 'cat']),

    # ─── 4: 금융/보험 ───
    (4, [
        '은행', '카드', '보험', '증권', '캐피탈', '저축은행', '투자',
        '대출', '금융', '자산운용', '신협', '펀드', '리스', '화재',
        '현대카드', 'KB국민카드', '우리카드', '신한카드', '카드고릴라',
        '키움증권', '나무증권', '미래에셋', '유진투자', '대신증권', 'SK증권',
        '우리투자', '삼성액티브자산', '삼성자산운용', '워렌증권',
        '삼성생명', '삼성화재', 'KB손해보험', '신한EZ손해보험',
        '흥국화재', '메리츠화재', '롯데손해보험', '다보험',
        '굿리치', '보험클리닉', '바로비교', '플렉스머니', '월급쟁이부자',
        '삼쩜삼', 'Samsung card', '현대캐피탈', 'hyundaicapital',
        'SS캐피탈', '넥스트홀딩스', '신한금융', '서민플랜',
        '마이아멕스', '신용카드 사회공헌',
        'SBI저축은행',
    ], ['bank', 'card', 'insure', 'insurance', 'securities', 'capital',
        'kbinsure', 'bohumclinic', 'shinhanez', 'shinhyup', 'hyundaicapital',
        'digitalwooriib', 'meritzfire', 'lotteins', 'sbiapt']),

    # ─── 11: 건설/부동산 ───
    (11, [
        '부동산', '분양', '아파트', '건설', '시티', '자이', '푸르지오',
        '힐스테이트', '더플래티넘', '포레', '그라시움', '센트럴',
        '빌라드', '위브', '스테이트', '한다움건설', '빌딩매매',
        '원룸', '쉐어하우스', '셰어하우스', '빌라', '하우스',
        '1stvilla', '1st빌라', '수지자이', '도룡자이', '상주자이',
        '검증된매물', '골든스테', '한내들', '스타포레',
        '가이드현대중개', '피터팬하우스', '배방88부동산',
        '다온하우스', '공간실록', '우주셰어', '동거동락',
        '렌탈', '위브리빙', '모바일포레', '두산위브',
    ], ['villa', 'apt', 'realestate', 'b4786800', 'gonggan-record',
        '1stvilla', 'weave-living']),

    # ─── 9: 제약/헬스케어 ───
    (9, [
        '제약', '의원', '병원', '한의원', '치과', '성형', '클리닉',
        '헬스케어', '글락소스미스클라인', '동국제약', '익수제약',
        '존슨앤드존슨', '세라젬', '닥터', '오스템임플란트',
        '탈모', '모발이식', '리프팅', '다이어트', '체형', '체중',
        '관절', '약손명가', '펜트라민', '결이고운', '에스테리브',
        '밴스의원', '세바른병원', '삼성본병원', '세예의원',
        '다올린의원', '나인의원', '리버스의원', '미랩',
        'vandsclinic', '유산균', '루테인', '다이트한의원',
        '코비한의원', '여진주한의원', '에톤성형', '모아이의원',
        '러블리안성형', '원더풀성형', '아이디병원', '하이봄성형',
        '디에이성형', '뷰성형', '쥬얼리성형', '센스성형',
        '닥터송포유', '우리성형', '미다스의원', '페이스필터의원',
        '모모성형', '나나성형', '서울진이치과', '탑석센트럴치과',
        '똑똑플란트치과', '달리아에스테틱', '가인미가',
        '일맥한의원', '인애한의원', '드림헤어라인',
        '압구정더모', '건강한 탈모', '모발',
    ], ['clinic', 'hospital', 'medical', 'health', 'vandsclinic',
        'jewelryps', 'dampick']),

    # ─── 6: 뷰티/화장품 ───
    (6, [
        '화장품', '뷰티', '코스메틱', '스킨', '고혼진', 'KOHONJIN',
        '올리브영', '꿀피부', 'GONGSKIN', '네오팜',
        '하루두피', '헤이미니', '피그먼트', '염색',
    ], ['beauty', 'cosmetic', 'oliveyoung', 'skin']),

    # ─── 15: 교육 ───
    (15, [
        '교육', '학원', '학습', '어학', '공무원', '수능', '기숙학원',
        '아카데미', '밀크T', '엘리하이', '윤선생', '에듀윌', '해커스',
        '박문각', '눈높이', '크레버스', '웅진씽크빅', '윙크',
        '정철어학', '파고다', '메가스터디', 'G스쿨', '교원',
        '그린컴퓨터', '뇌새김', '위더스', '원격평생교육',
        '코딩교육', 'KOSTA', '일본어', 'khacademy',
        '진성기숙', '대방고시', '독한공무원', '넥스트공무원',
        '충남인력개발', '빨간펜', '러닝스푼즈', '밀리의 서재',
        'DT당톡스피치', '메가엑스퍼트', '이지수능', '쎈엄마',
        'IT국비', '에이콘아카데미', '더위크 일본어',
        '진주한국공무원', '공단기', 'MBC아카데미',
        '네이버 커넥트재단', '합격까지',
    ], ['edu', 'academy', 'school', 'learn', 'g-school', 'milkt',
        'mbest', 'wjthinkbig', 'wink', 'khacademy', 'jungchul',
        'koreaitacademy', 'creverse']),

    # ─── 7: 패션/의류 ───
    (7, [
        '패션', '의류', '옷', '브룩스브라더스', 'LOW CLASSIC', '듀베티카',
        '르무통', '아키클래식', '디스커버리 익스페디션', '삼성물산패션',
        'COS', '아디다스', '코오롱인더스트리FnC', '코오롱인더스트리 FnC',
        '안다르', '젝시믹스', '지그재그', '모어아웃', '아던트소울',
        '마르스마크', 'SLEEK', 'BERMAN', '에이치닷', 'ALO',
        '빌라코스타', '100classic', 'rovera', 'crassiang',
    ], ['fashion', 'clothing', 'wear', 'andar', 'zigzag', 'aloyoga',
        'ssfshop', 'moreout', 'ardentsoul', 'villacosta']),

    # ─── 5: 식품/음료 ───
    (5, [
        '식품', '음료', '밥상', '음식', '치킨', '피자', '맥도날드',
        '유업', '인삼공사', '웰빙푸드', '대상웰라이프', '네슬레',
        '노랑통닭', '유가네', '짬뽕관', '샤브올데이', '샤브보트',
        '핵밥', '본가네국밥', '죽이야기', '진이찬방', '본도시락',
        '장스푸드', '쌍계명차', '갯벌의조개', '누구나홀딱반한닭',
        '본아이에프', '참이맛감자탕', '쿡익스프레스', '오초오늘의초밥',
        '한국피앤지', 'JW생활건강', '담가화로구이', '뿌리공스',
        '배민입점', '요기요', '배달의민족',
    ], ['food', 'meal', 'cook', 'chicken', 'pizza', 'chamimat',
        'todaysushi', 'damga']),

    # ─── 10: 가전/전자 ───
    (10, [
        '가전', '전자', '삼성전자', '삼성닷컴', '삼성스토어', '삼성패키지',
        'Samsung', '필립스', 'LG베스트샵', 'LG디스플레이', 'LG에너지',
        'LGECOM', '현대전자', '현성전자', '위닉스', '코웨이', '하이마트',
        '쿠쿠전자', '쿠쿠렌탈', '쿠쿠공식', '쿠쿠본사',
        'SK매직', '교원웰스', '아이리버', '리퍼연구소',
        '앱스토리몰', '이어폰', '소닉케어', 'Temu 가전',
        'GN렌탈', '웅진프라자', '또또렌탈', '렌트리',
        'coway', 'skmagic',
    ], ['samsung.com', 'lge.co', 'coway', 'skmagic', 'cuckoo',
        'homestyle', 'rentre']),

    # ─── 3: 자동차 ───
    (3, [
        '자동차', '렌터카', '렌트', '렌탈카', '오토', '모비스',
        'SK렌터카', '현대모비스', '오토카', '렌트앤카', '기아 EV',
        '한국신차장기렌터카', '국민다이렉트카', '케이오토뱅크',
        'HD현대', '현대위아', '현대스틸', '두산산업차량',
    ], ['car', 'rental', 'auto', 'mobis', 'skcarrental', 'kukmincar']),

    # ─── 2: IT/통신 ───
    (2, [
        'IT', '통신', 'KT', 'SKT', '알뜰폰', '직폰', '국대폰',
        'adobe', 'KT알파', 'KT&G', 'ktHCN', 'KT ENA', 'ktMINE',
        'kt M모바일', 'KTB', '유플러스', '인포벨', '네오텍',
        '아이디스', 'MBCSOFT', '다래비젼', '카카오모빌리티',
    ], ['telecom', 'mobile', 'kt.com', 'skt', 'lguplus']),

    # ─── 8: 유통/이커머스 ───
    (8, [
        '유통', '이커머스', '쇼핑', '스토아', '마켓', '몰', '장터',
        'SK스토아', 'TEMU', '롯데쇼핑', 'CJ온스타일',
        '현대백화점', '현대Hmall', '번개장터', '무인양품',
        '쿠팡풀필먼트', '마켓비', '한일공식몰', '온리원',
        '마이핀티켓', '오피스콘', '리싸이클오피스',
    ], ['shop', 'mall', 'store', 'temu', 'market', 'bunjang',
        'hmall', 'cjonstyle', 'only1']),

    # ─── 14: 여행/항공 ───
    (14, [
        '항공', '여행', '투어', '케이블카', '관광',
        '에어아시아', '파라타항공', '대한항공', '마이리얼트립',
        '제부도해상케이블카', '하동케이블카', '요트',
        '부산요트투어', '구해줘버스',
    ], ['air', 'travel', 'tour', 'flight']),

    # ─── 12: 게임 ───
    (12, [
        '게임', '드래곤 퀘스트', '컴투스', 'LCK',
    ], ['game']),

    # ─── 13: 엔터테인먼트 ───
    (13, [
        '엔터테인먼트', '미디어', '웹툰', '네이버웹툰', 'MBC America',
        '두산매거진', '볼미디어', '미디어로', '핀미디어', '메조미디어',
        '나스미디어', '더블미디어', '미디어윌', '치지직',
        '웨딩', '결혼정보', '듀오', '노블리', '가연', '바로연',
        '엔노블', '르매리', '아망떼',
    ], ['media', 'wedding', 'entertainment']),

    # ─── 17: 가구/인테리어 ───
    (17, [
        '가구', '인테리어', '한샘', '시몬스', 'THOME', '노블리에',
        '에스노블', '디노블',
    ], ['furniture', 'interior', 'simmons', 'thome']),

    # ─── 18: 주류 ───
    (18, [
        '주류', '맥주', '소주', '와인', '하이트진로', '오비맥주',
        '소주물',
    ], ['beer', 'wine', 'soju', 'liquor']),

    # ─── 19: 공공기관 ───
    (19, [
        '경찰청', '군청', '공공', '시청', '구청', '도청', '적십자',
        '초록우산', '월드비전', '대전경찰청', '의성군청',
        'NCC 소상공인', 'SPRINT Program', '강원알리미',
        '3\u00b71절', '대한적십자사',
    ], ['.go.kr', 'childfund']),

    # ─── 16: 스포츠/아웃도어 ───
    (16, [
        '스포츠', '아웃도어', '라테스민턴', '배드민턴',
    ], ['sport', 'outdoor']),

    # ─── 21: 생활용품 ───
    (21, [
        '생활용품', '클린휴', '꽃배달', '플라워', '이사',
        '용달', '택시', '배달서비스', '세이볼프',
        '홍반장이사', '영구이사', '로젠이사', '착한이사',
        '이사몰', '24번가', '국민트랜스', '삼성용달',
        '용달이사', '부가부', '팸퍼스', '보아르', '로라스타',
        '다치워드림', '전국꽃배달', '일일구플라워',
    ], ['flower', 'moving', 'delivery']),

    # ─── 20: 반려동물 (already above, this catches more) ───

    # ─── Broad corporate group matches ───
    # 한화 -> 건설/부동산 (한화비전 is IT but 한화 group is diverse)
    # 두산 -> mostly industrial

    # ─── Services / Misc that can be categorized ───
    # 법무법인 -> no specific industry, keep as 기타 unless we create one
    # 창업 -> could be 유통 or 기타
]

# Additional explicit ID mappings for tricky cases
EXPLICIT_MAP = {
    # 법률 서비스 -> 기타 (no legal industry, keep)
    # 미용실/헤어 -> 뷰티/화장품
    'gemmahair': 6,
    '닥터포헤어': 6,

    # 숨고 = 서비스 플랫폼
    '숨고': 2,  # IT/통신 (플랫폼)

    # 네이버 계열
    '네이버': 2,
    '네이버지회': 2,
    '네이버 멤버십': 2,
    'Meta 광고 라이브러리': 2,
    '광고 라이브러리 보고서': 2,
    '광고 라이브러리 API': 2,
    '브랜디드 콘텐츠': 13,  # 엔터

    # 삼성 그룹 (삼성전자/가전이 아닌 것)
    '삼성': 10,  # 가전/전자 (대표)
    '삼성 배터리 전기자전거 V6': 10,

    # 한화
    '한화': 4,  # 금융/보험 (한화그룹 금융 중심)
    '한화비전': 2,  # IT/통신

    # 두산 -> 건설/부동산 (두산건설 계열)
    '(재)두산연강재단': 19,  # 공공
    '두산로보틱스': 2,  # IT

    # 프랜차이즈/창업
    '프창사': 5,  # 식품 프랜차이즈
    '창업이건물주다': 11,  # 부동산
    '쿠팜창업연구원': 8,  # 유통
    '이플러스창업경영연구소': 15,  # 교육
    '카페24창업센터 성수점': 8,
    '카페24창업센터 신논현점': 8,
    '카페24창업센터 신도림점': 8,
    '한국창업벤처투자': 4,  # 금융

    # 워킹/운동
    '워킹보감': 9,  # 헬스케어

    # 원티드/구인
    '원티드랩': 2,  # IT 플랫폼
    '리멤버채용솔루션': 2,

    # 기타 매핑
    '티반': 13,  # 엔터테인먼트 (OTT)
    '개인택시': 14,  # 여행/항공 -> 교통
    '장거리택시': 14,
    '점보택시연합': 14,
    '인천공항대형택시': 14,
    '스탬프링': 2,  # IT
    '바나나포스': 2,  # IT (POS)
    '컨설팅매니아': 2,  # IT/서비스

    # 헤어
    '피그먼트 고온 염색': 6,
    '은은한 빈티지 무드': 6,
    '가볍고 산뜻하게': 7,  # 패션

    # 특정 제품 광고 (설명형 이름)
    '부드러운 프리미엄 감촉': 21,  # 생활용품
    '깔끔한 무봉제 디자인': 7,  # 패션
    '광폭 원단 사용': 17,  # 가구/인테리어
    '봄맞이 분위기 체인지': 17,

    # 식품 보충제
    '리더뮨': 9,
    '락토몰': 9,
    '체지방 감소 다이어트 유산균': 9,
    '관절보궁': 9,
    '관절보공': 9,
    '99VITAL': 9,
    '하루 두 알 ! 9,900원 !': 9,
    '초소형 정제!': 9,
    '루테인 20mg!': 9,
    '네오프로틴': 9,
    '슬립웰리': 9,  # 수면 보조
    '한국인삼공사': 5,

    # 남양유업
    '남양유업': 5,

    # 한국피자헛
    '한국피자헛': 5,

    # 운세다방
    '운세다방': 13,  # 엔터

    # 알래스카큐브 (냉동고?)
    '알래스카큐브': 10,

    # 헤임타 -> 가구
    '헤임타': 17,

    # 농업
    '농업회사법인보령스마트팜': 5,  # 식품

    # JW PEI -> 패션 (가방)
    'JW PEI INC.': 7,

    # 모자이크 -> 여행 (별장 회원권)
    '모자이크': 14,
    '프라이빗 별장 회원권, 모자이크': 14,
    '초호화 별장 회원권, 모자이크': 14,

    # 철구PC -> 게임/PC방
    '철구PC망미점': 12,

    # 겨울 가전 클리어런스 세일
    '겨울 가전 클리어런스 세일': 10,

    # 소비자리포트
    '소비자리포트': 13,

    # 비아지오 -> 가구
    '비아지오': 17,

    # 오프레임 -> 가구/인테리어
    '오프레임': 17,

    # 르위켄 -> 패션
    '르위켄': 7,

    # 에어아시아 -> 여행/항공
    '에어아시아': 14,

    # 법무법인 계열 -> keep 기타 (no legal category)
    # but let's at least not re-match them

    # 초이코퍼레이션 -> 뷰티
    '초이코퍼레이션': 6,

    # 인스파이어 리조트
    'Inspire Korea': 14,

    # 고혼진 -> 뷰티
    '고혼진': 6,
    '비싸서 못산 고혼진 이렇게 싸다고?': 6,

    # 아정당 -> 가전 렌탈
    '아정당': 10,

    # 엑스원 -> IT
    '엑스원': 2,

    # 레삐 -> 생활용품 (아기용품)
    '레삐': 21,
    '나어릴때': 21,

    # 페이쏨땀 -> 식품 (태국 식당)
    '페이쏨땀': 5,

    # 코오롱
    '코오롱인더스트리FnC': 7,
    '코오롱인더스트리 FnC부문': 7,
    '코오롱인더스트리 FnC 부문': 7,

    # 프코치 -> 교육
    '프코치': 15,

    # 조블핀 -> IT 서비스
    '조블핀': 2,

    # 핀가게 -> 유통
    '핀가게': 8,

    # 사라바 -> 패션
    '사라바': 7,

    # 독립생활 -> 생활용품
    '독립생활': 21,

    # 산이좋은사람들 -> 스포츠/아웃도어
    '산이좋은사람들': 16,

    # 스마트리블로그 -> IT
    '스마트리블로그': 2,

    # 과천펜타원기숙사 -> 교육
    '과천펜타원기숙사': 15,

    # 캐시로 -> 금융
    '캐시로  delionquick': 8,  # 배달 서비스

    # 바로24 -> 서비스
    '바로24': 21,

    # 음소거 -> 기타 (keep)

    # 한결같이 -> 식품
    '한결같이': 5,

    # 오렌지씨 -> 뷰티
    '오렌지씨': 6,

    # 닥터바이 -> 제약/헬스케어
    '닥터바이': 9,

    # 어댑트 -> IT
    '어댑트': 2,

    # 하이트진로음료 -> 음료
    '하이트진로음료': 5,

    # 에스티엘 -> 뷰티
    '에스티엘  beststl': 6,

    # 마이노멀 -> 뷰티
    '마이노멀': 6,

    # 쓱싹마녀 -> 생활용품 (청소)
    '쓱싹마녀': 21,

    # 삼성물산패션몰
    '삼성물산패션몰': 7,

    # 양현대 -> 유통 (중고차?)
    '양현대': 3,
    '현대화': 3,

    # 광진종합기계상사 -> 기타 (산업)
    # J&H -> 기타

    # NOONEE -> 패션
    'NOONEE': 7,

    # ap7.kr -> IT
    'ap7.kr': 2,

    # 데이터 -> IT
    '요트다타자': 2,

    # 도그마루 -> 반려동물
    '도그마루': 20,
    '견생냥품의정부중앙역': 20,
    '퍼피에몽': 20,

    # 더포에버 -> 반려동물 (장례)
    '더포에버': 20,

    # Tislo -> IT
    'Tislo': 2,

    # 오늘의이벤트꿀팁 -> 유통
    '오늘의이벤트꿀팁': 8,

    # 문장군 -> 교육 (글쓰기)
    '문장군': 15,

    # 더 알아보기 -> 기타 (광고주 아님)
    # 검색해보세요 -> 기타

    # 웰빙푸드 -> 식품
    '웰빙푸드': 5,

    # 프리즘x몬스터 -> 뷰티 (렌즈)
    '프리즘x몬스터': 6,

    # VOVO -> 가전 (비데)
    'VOVO': 10,

    # 병원꿀팁정보 -> 제약/헬스케어
    '병원꿀팁정보': 9,

    # 애니워터 -> 가전 (정수기)
    '애니워터': 10,
    '위킹': 10,

    # 한국맥도날드
    '한국맥도날드': 5,

    # 참여 누르고 쇼핑하면 -> 유통
    '참여 누르고 쇼핑하면': 8,
    '15시 이전 주문하면': 8,

    # 더파인 프리미엄 -> 생활용품 (화장지)
    '더파인 프리미엄': 21,
    '더파인프리미엄': 21,
    'THE PINE PREMIUM': 21,

    # 케어팟 -> 제약/헬스케어
    '케어팟': 9,

    # 우산브로 -> 생활용품
    '우산브로': 21,

    # e성경 -> 교육/기타
    'e성경익스프레스': 15,

    # 창업몰 -> 유통
    '창업몰': 8,

    # Curiosis -> IT
    'Curiosis': 2,

    # 지하철 4d 광고 -> 기타 (광고 매체)

    # 화면은 선명한데... -> 가전
    '화면은 선명한데...': 10,

    # 핫셀블라드 -> 가전 (카메라)
    '핫셀블라드': 10,

    # KT&G -> 기타 (담배) or 식품? Let's keep specific
    'KT&G': 5,  # 식품/음료 (담배+음료사업)

    # 두산매거진 -> 엔터
    '두산매거진': 13,

    # 한정세, 세미코 etc -> 기타 (unclear)
    # 세모네, 정모세, 세이션, 세리마, 세레비 -> 기타

    # 네오 계열 (unclear) -> IT
    '네오플랫': 2,
    '네오클립': 2,
    '네오브랜딩': 2,
    '지에스네오텍': 2,

    # 쿠쿠 -> 가전
    '쿠쿠공식인증점휴본': 10,

    # 대한항공씨앤디서비스 -> 여행
    '대한항공씨앤디서비스': 14,

    # JWK, JWServeis, jwan saleh, ES JWay, JW Family, JWD Art Space -> 기타 (foreign/unclear)

    # cura1, Cumulo9, Cun Liu, Cutcorn, cuiyuhua, CUI LONG -> 기타 (foreign)

    # 다사자, 다된다, 캐리다, 지화다, 아일다, 이린다, 다크레이지 -> 기타

    # 천정대, 백성대, 최규대, 최옥대 -> 기타 (인명?)

    # 한정세, 세미코, 세모네, 정모세 -> 기타

    # Temu -> 유통
    'Temu  temu': 8,

    # 삼성닷컴  samsung -> 가전
    '삼성닷컴  samsung': 10,

    # 웨딩북 -> 엔터테인먼트 (결혼)
    '웨딩북': 13,
    '웨딩북  weddingbook': 13,
    '웨딩스타': 13,

    # 법무법인/법률 -> 기타 (no legal category exists)
    # Keep them as 기타

    # 수현 -> 기타 (unclear)
    # 다 -> 기타 (too short)

    # A'ZAM TEMUROV -> 기타 (foreign person)
}


def classify_advertiser(adv_id, name, website, brand_name):
    """Return industry_id for this advertiser, or None to keep as 기타."""

    combined = f"{name or ''} {brand_name or ''} {website or ''}".lower()

    # 1) Check explicit map first (exact name match)
    if name in EXPLICIT_MAP:
        return EXPLICIT_MAP[name]

    # 2) Check rules
    for industry_id, name_keywords, domain_keywords in RULES:
        # Check name keywords
        for kw in name_keywords:
            if kw.lower() in combined:
                return industry_id

        # Check domain keywords (website only)
        if website:
            site_lower = website.lower()
            for dkw in domain_keywords:
                if dkw.lower() in site_lower:
                    return industry_id

    return None  # keep as 기타


def main():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # Load all 기타 advertisers
    cur.execute("""
        SELECT id, name, website, brand_name
        FROM advertisers
        WHERE industry_id = 1
        ORDER BY id
    """)
    advertisers = cur.fetchall()
    print(f"Total advertisers in 기타: {len(advertisers)}")

    # Load industry names for reporting
    cur.execute("SELECT id, name FROM industries")
    industry_names = dict(cur.fetchall())

    # Classify
    updates = {}  # id -> new_industry_id
    remaining = []

    for adv_id, name, website, brand_name in advertisers:
        new_id = classify_advertiser(adv_id, name, website, brand_name)
        if new_id and new_id != 1:
            updates[adv_id] = new_id
        else:
            remaining.append((adv_id, name))

    print(f"\nWill reclassify: {len(updates)}")
    print(f"Remaining in 기타: {len(remaining)}")

    # Count per industry
    counts = {}
    for adv_id, new_id in updates.items():
        counts[new_id] = counts.get(new_id, 0) + 1

    print(f"\n{'='*60}")
    print(f"{'Industry':<30} {'Count':>6}")
    print(f"{'='*60}")
    for iid in sorted(counts.keys()):
        print(f"  {industry_names.get(iid, f'ID={iid}'):<28} {counts[iid]:>6}")
    print(f"{'='*60}")
    print(f"  {'TOTAL reclassified':<28} {len(updates):>6}")
    print(f"  {'Remaining in 기타':<28} {len(remaining):>6}")

    # Apply updates
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    for adv_id, new_id in updates.items():
        cur.execute(
            "UPDATE advertisers SET industry_id = ?, updated_at = ? WHERE id = ?",
            (new_id, now, adv_id)
        )

    conn.commit()
    print(f"\nAll {len(updates)} updates committed to database.")

    # Show remaining
    print(f"\n--- Remaining in 기타 ({len(remaining)}) ---")
    for adv_id, name in remaining:
        print(f"  ID={adv_id}: {name}")

    # Verify
    cur.execute("SELECT COUNT(*) FROM advertisers WHERE industry_id = 1")
    final = cur.fetchone()[0]
    print(f"\nFinal count in 기타: {final}")

    conn.close()


if __name__ == '__main__':
    main()
