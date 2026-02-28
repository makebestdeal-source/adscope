"""광고주 자동 매칭 — 이름/도메인/별칭 기반 기존 광고주 식별."""

import re
from urllib.parse import urlparse

from rapidfuzz import fuzz, process


# 이름 정규화: 법인격 표기 제거 패턴
_CORP_SUFFIX_RE = re.compile(
    r"\s*[\(\(]?\s*(?:주|株|㈜|유|사단|재단|합자|합명)\s*[\)\)]?\s*$"
)


class AdvertiserMatcher:
    """크롤링된 광고주명을 기존 광고주 DB와 매칭."""

    MATCH_THRESHOLD = 80  # 유사도 80% 이상이면 동일 광고주로 판단

    def __init__(self):
        self._known_advertisers: dict[int, str] = {}  # id -> name
        self._name_to_id: dict[str, int] = {}
        self._norm_to_id: dict[str, int] = {}
        self._domain_to_id: dict[str, int] = {}  # "samsung.com" -> id

    @staticmethod
    def _normalize(name: str) -> str:
        """매칭용 이름 정규화: 소문자 + 공백 + 법인격 표기 제거."""
        name = _CORP_SUFFIX_RE.sub("", name)
        return name.lower().replace(" ", "").strip()

    @staticmethod
    def _extract_root_domain(url_or_domain: str) -> str | None:
        """URL이나 도메인에서 루트 도메인 추출 (e.g. 'www.samsung.com' → 'samsung.com')."""
        if not url_or_domain:
            return None
        try:
            if "://" not in url_or_domain:
                url_or_domain = f"https://{url_or_domain}"
            host = urlparse(url_or_domain).netloc.lower()
            if not host:
                return None
            # www. 제거 + 서브도메인 제거 (2단계 도메인만 유지)
            parts = host.split(".")
            if len(parts) >= 2:
                return ".".join(parts[-2:])
            return host
        except Exception:
            return None

    def load_advertisers(self, advertisers: list[dict]):
        """DB에서 로드한 광고주 목록을 캐싱.

        Args:
            advertisers: [{"id": 1, "name": "삼성전자", "website": "https://samsung.com",
                           "aliases": ["samsung", "삼성"]}, ...]
        """
        self._known_advertisers.clear()
        self._name_to_id.clear()
        self._norm_to_id.clear()
        self._domain_to_id.clear()

        for adv in advertisers:
            adv_id = adv["id"]
            name = adv["name"]
            self._known_advertisers[adv_id] = name
            self._name_to_id[name] = adv_id
            self._norm_to_id[self._normalize(name)] = adv_id

            # 별칭 등록
            for alias in adv.get("aliases", []) or []:
                self._name_to_id[alias] = adv_id
                self._norm_to_id[self._normalize(alias)] = adv_id

            # 도메인 등록
            website = adv.get("website")
            if website:
                domain = self._extract_root_domain(website)
                if domain:
                    self._domain_to_id[domain] = adv_id

    def match(self, raw_name: str, url: str | None = None) -> tuple[int | None, float]:
        """광고주명(+URL)으로 기존 광고주 매칭 시도.

        Returns:
            (advertiser_id, 유사도 점수) — 매칭 실패 시 (None, 0.0)
        """
        if not raw_name and not url:
            return None, 0.0

        # 0) 도메인 매칭 (URL 기반, 가장 신뢰도 높음)
        if url:
            domain = self._extract_root_domain(url)
            if domain and domain in self._domain_to_id:
                return self._domain_to_id[domain], 100.0

        if not raw_name or not self._name_to_id:
            return None, 0.0

        # 1) 정확 매칭
        if raw_name in self._name_to_id:
            return self._name_to_id[raw_name], 100.0

        # 2) 정규화 후 정확 매칭 (대소문자/공백/법인격 표기 무시)
        norm = self._normalize(raw_name)
        if norm in self._norm_to_id:
            return self._norm_to_id[norm], 100.0

        # 3) 퍼지 매칭
        result = process.extractOne(
            raw_name,
            self._name_to_id.keys(),
            scorer=fuzz.token_sort_ratio,
        )

        if result and result[1] >= self.MATCH_THRESHOLD:
            matched_name = result[0]
            return self._name_to_id[matched_name], result[1]

        return None, 0.0
