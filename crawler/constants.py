"""공통 상수 — 광고 인프라/네트워크 도메인 블록리스트.

각 크롤러에서 중복 정의되던 도메인 셋을 단일 모듈로 통합.
"""
from __future__ import annotations

# ── 광고 네트워크 응답 인터셉트 대상 도메인 ──────────────────────────
# 언론사 서핑 시 이 도메인에서 오는 응답을 파싱해 광고를 추출한다.
AD_NETWORK_DOMAINS: tuple[str, ...] = (
    # Google
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "pagead2.googlesyndication.com", "adservice.google.com",
    # Criteo
    "criteo.com", "criteo.net",
    # Taboola / Outbrain
    "taboola.com", "cdn.taboola.com", "outbrain.com",
    # 데이블
    "dable.io", "api.dable.io",
    # 버즈빌
    "buzzvil.com", "ad.buzzvil.com",
    # 모비온
    "mobon.net", "ad.mobon.net",
    # 카카오 ADfit
    "adfit.kakao.com", "ad.daum.net", "track.kakao.com",
    # 네이버 NAM/GFP
    "nam.veta.naver.com", "gfp.naver.com", "siape.veta.naver.com",
    # ADX / 기타
    "adroll.com", "rtbhouse.com",
    # 인모비
    "ads.inmobi.com",
)

# ── 광고주 도메인으로 사용할 수 없는 인프라 도메인 ────────────────────
# 광고주 URL 검증 시 이 도메인이 나오면 무효 처리한다.
INFRA_DOMAINS: frozenset[str] = frozenset({
    # Google
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "pagead2.googlesyndication.com", "adservice.google.com",
    "google.com",
    # Criteo / RTB
    "criteo.com", "criteo.net", "adroll.com", "rtbhouse.com",
    # Taboola / Outbrain / Dable
    "taboola.com", "outbrain.com", "dable.io",
    # 버즈빌 / 모비온
    "buzzvil.com", "mobon.net",
    # 카카오/다음
    "adfit.kakao.com", "ad.daum.net", "track.kakao.com",
    "kakaoad.com", "t1.daumcdn.net", "t1.kakaocdn.net",
    # 네이버 광고 인프라
    "adcr.naver.com", "ader.naver.com",
    "nam.veta.naver.com", "gfp.naver.com", "siape.veta.naver.com",
    # 인모비
    "ads.inmobi.com",
    # Meta
    "facebook.com", "instagram.com", "fb.com", "fbcdn.net",
    "meta.com", "facebook.net", "fbsbx.com",
    # 매체 도메인 (광고주 아님)
    "www.daum.net", "m.daum.net", "news.daum.net",
    "finance.daum.net", "sports.daum.net", "entertain.daum.net",
    "www.naver.com", "m.naver.com",
})


def is_infra_domain(domain: str | None) -> bool:
    """도메인이 광고 인프라/매체인지 확인 — True면 광고주로 사용 불가."""
    if not domain:
        return True
    d = domain.lower().strip()
    # 정확 일치 먼저 (빠름)
    if d in INFRA_DOMAINS:
        return True
    # 서브도메인 포함 확인
    for infra in INFRA_DOMAINS:
        if d.endswith("." + infra):
            return True
    return False
