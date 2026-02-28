"""Korean text filter -- reject ads with no Korean (hangul) content.

Used in pipeline and fast_crawl to ensure only Korean-market ads are stored.
Also provides advertiser name sanitization (foreign script rejection, cleanup).
"""

import re

# Hangul syllables: AC00-D7A3
_HANGUL_RE = re.compile(r'[가-힣]')

# Foreign script detection (non-Korean, non-ASCII, non-CJK)
_FOREIGN_SCRIPT_RE = re.compile(
    r'[\u00C0-\u024F'   # Latin Extended (Vietnamese/French diacritics)
    r'\u1E00-\u1EFF'    # Latin Extended Additional (Vietnamese)
    r'\u10A0-\u10FF'    # Georgian
    r'\u0600-\u06FF'    # Arabic
    r'\u0E00-\u0E7F'    # Thai
    r'\u0400-\u04FF'    # Cyrillic
    r'\u0900-\u097F]'   # Devanagari
)

# Zero-width characters
_ZWSP_RE = re.compile(r'[\u200B\u200C\u200D\uFEFF]')

# Emoji ranges
_EMOJI_RE = re.compile(
    r'[\U0001F000-\U0001FAFF\U00002702-\U000027B0'
    r'\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
    r'\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF]'
)

# Fullwidth ASCII
_FULLWIDTH_RE = re.compile(r'[\uFF01-\uFF5E]')


def contains_korean(text: str) -> bool:
    """Return True if text contains at least one hangul character."""
    if not text:
        return False
    return bool(_HANGUL_RE.search(text))


def has_foreign_script(text: str) -> bool:
    """Return True if text contains foreign script characters
    (Vietnamese, Georgian, Arabic, Thai, Cyrillic, Devanagari).
    """
    if not text:
        return False
    return bool(_FOREIGN_SCRIPT_RE.search(text))


_URL_RE = re.compile(
    r'https?://[^\s]+|'                                      # full URL
    r'(?:m\.)?'                                              # optional m. prefix
    r'(?:[a-zA-Z0-9가-힣][-a-zA-Z0-9가-힣]*\.)+?'           # subdomains (Korean or ASCII)
    r'(?:com|co\.kr|kr|net|org|io|me|shop|store'              # TLDs
    r'|co|biz|info|xyz|online|site|app|dev|se'
    r'|co\.jp|co\.uk)'
    r'(?:/[^\s]*)?',                                         # optional path
    re.IGNORECASE,
)
# Leftover fragments after URL removal (e.g., "m.", "kr.", "mbanking.")
_URL_FRAGMENT_RE = re.compile(r'\b[a-zA-Z0-9가-힣]{1,20}\.\s*$|\s+[a-zA-Z0-9가-힣]{1,20}\.$')

# URL-only names that should be rejected entirely
_INFRA_KEYWORDS = {
    'siape', 'veta', 'adcr', 'adsun', 'displayad',
    'ader.naver', 'ad.search', 'doubleclick', 'googlesyndication',
}

# Prefix noise from naver landing pages
_NAVER_PREFIX_RE = re.compile(
    r'^(?:네이버로그인|네이버페이|네이버파이낸셜)\s*',
)


def clean_advertiser_name(name: str | None) -> str | None:
    """Sanitize advertiser name: strip zero-width, emoji, fullwidth->halfwidth, URLs.

    Rules:
    - Remove URLs (domain.com, http://...) from advertiser names
    - Remove naver login/pay prefixes
    - Reject names that are purely URLs or ad infra domains
    - Reject foreign scripts (Vietnamese etc.)
    - Returns None if name becomes empty after cleaning.
    """
    if not name:
        return None

    # Reject foreign scripts entirely
    if has_foreign_script(name):
        return None

    # Reject ad infrastructure names
    name_lower = name.lower()
    if any(kw in name_lower for kw in _INFRA_KEYWORDS):
        return None

    # Remove naver login/pay prefixes
    cleaned = _NAVER_PREFIX_RE.sub('', name).strip()

    # Remove URL patterns from name
    cleaned = _URL_RE.sub('', cleaned).strip()
    # Remove leftover URL fragments (e.g., "m.", "kr.", "mbanking.")
    cleaned = _URL_FRAGMENT_RE.sub('', cleaned).strip()

    # If name was purely a URL, reject
    if not cleaned:
        return None

    # Remove zero-width characters
    cleaned = _ZWSP_RE.sub('', cleaned)
    # Remove emoji
    cleaned = _EMOJI_RE.sub('', cleaned)
    # Fullwidth -> halfwidth conversion
    result = []
    for ch in cleaned:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        else:
            result.append(ch)
    cleaned = ''.join(result)
    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned if cleaned else None


def is_korean_ad(ad_text: str | None = None,
                 advertiser_name: str | None = None,
                 brand: str | None = None,
                 ad_description: str | None = None,
                 channel: str | None = None) -> bool:
    """Check if an ad is relevant to the Korean market.

    Logic (relaxed):
    1. Contact channels → always True
    2. Any field contains Korean → True
    3. ad_text / ad_description / advertiser_name has foreign script
       (Cyrillic, Arabic, Thai etc.) → False (확실히 비한국 광고)
    4. Otherwise (English-only etc.) → True (한국 브랜드가 영문 사용 가능)
    """
    # Contact channels: captured on Korean user devices → inherently Korean
    if channel:
        from processor.channel_utils import is_contact_channel
        if is_contact_channel(channel):
            return True

    # Korean text found → definitely Korean
    for field in (ad_text, advertiser_name, brand, ad_description):
        if field and contains_korean(field):
            return True

    # Foreign script in text fields → not Korean
    for field in (ad_text, ad_description, advertiser_name):
        if field and has_foreign_script(field):
            return False

    # English-only or empty → accept (Korean brands often use English)
    return True
