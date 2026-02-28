"""정크 광고주 정리 스크립트.

4가지 패턴 처리:
1. 도메인 광고주 (siape.veta.naver.com 등) -> ad_details 삭제, advertiser 삭제
2. '함께합니다' 패턴 -> 실제 광고주로 재매핑
3. UI 텍스트 (Visit Instagram Profile 등) -> ad_details 삭제, advertiser 삭제
4. 외국어 광고주 (베트남어/조지아어 등 비한국 외국어) -> 관련 데이터 삭제
"""

import io
import re
import sqlite3
import sys
from pathlib import Path

# Windows cp949 방지: UTF-8 출력 강제
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

DB_PATH = Path(__file__).resolve().parent.parent / "adscope.db"

# 도메인 패턴 (네이버/카카오 트래킹 도메인 등)
DOMAIN_PATTERNS = [".com", ".kr", ".net", ".co."]

# UI 텍스트 정크
UI_JUNK_NAMES = {
    "Visit Instagram Profile",
    "Learn More",
    "Video Downloader",
}
UI_JUNK_PREFIXES = ["DramaBox", "WonderGame"]

# 외국어 감지용 정규식 (한국시장과 무관한 외국어 문자)
_VIETNAMESE_RE = re.compile(r'[\u00C0-\u024F\u1E00-\u1EFF]')
_GEORGIAN_RE = re.compile(r'[\u10A0-\u10FF]')
_ARABIC_RE = re.compile(r'[\u0600-\u06FF]')
_THAI_RE = re.compile(r'[\u0E00-\u0E7F]')
_CYRILLIC_RE = re.compile(r'[\u0400-\u04FF]')
_DEVANAGARI_RE = re.compile(r'[\u0900-\u097F]')
_HANGUL_RE = re.compile(r'[가-힣ㄱ-ㅎㅏ-ㅣ]')
_ZWSP_RE = re.compile(r'[\u200B\u200C\u200D\uFEFF]')
_EMOJI_RE = re.compile(
    r'[\U0001F000-\U0001FAFF\U00002702-\U000027B0'
    r'\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
    r'\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF]'
)
_FULLWIDTH_RE = re.compile(r'[\uFF01-\uFF5E]')


def _has_foreign_script(name: str) -> str | None:
    """Return foreign script name if detected, else None."""
    for regex, label in [
        (_VIETNAMESE_RE, 'vietnamese'),
        (_GEORGIAN_RE, 'georgian'),
        (_ARABIC_RE, 'arabic'),
        (_THAI_RE, 'thai'),
        (_CYRILLIC_RE, 'cyrillic'),
        (_DEVANAGARI_RE, 'devanagari'),
    ]:
        if regex.search(name):
            return label
    return None


def _clean_advertiser_name(name: str) -> str:
    """Strip zero-width chars, emoji, fullwidth -> halfwidth from name."""
    # Remove zero-width characters
    cleaned = _ZWSP_RE.sub('', name)
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
    return cleaned


def _delete_advertiser_cascade(c, adv_id: int) -> dict:
    """Delete advertiser and all related rows. Returns counts."""
    counts = {}
    for table in ['ad_details', 'campaigns', 'spend_estimates',
                   'activity_scores', 'meta_signal_composites',
                   'channel_stats', 'brand_channel_content']:
        try:
            if table == 'spend_estimates':
                # spend_estimates references campaign_id, not advertiser_id
                deleted = c.execute(
                    "DELETE FROM spend_estimates WHERE campaign_id IN "
                    "(SELECT id FROM campaigns WHERE advertiser_id = ?)",
                    (adv_id,),
                ).rowcount
            else:
                deleted = c.execute(
                    f"DELETE FROM {table} WHERE advertiser_id = ?", (adv_id,)
                ).rowcount
            if deleted:
                counts[table] = deleted
        except Exception:
            pass  # table may not exist
    c.execute("DELETE FROM advertisers WHERE id = ?", (adv_id,))
    return counts


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()

    stats = {
        "domain_deleted": 0, "together_remapped": 0,
        "ui_deleted": 0, "foreign_deleted": 0, "name_cleaned": 0,
        "ads_moved": 0, "ads_deleted": 0,
    }

    # ── 1) '함께합니다' 패턴 처리 ──
    together_rows = c.execute(
        "SELECT id, name FROM advertisers WHERE name LIKE '%함께합니다%' OR name LIKE '%과(와) 함께%'"
    ).fetchall()

    for junk_id, junk_name in together_rows:
        m = re.search(r"페이지는\s+(.+?)과\(와\)\s+함께합니다", junk_name)
        if not m:
            continue
        real_name = m.group(1).strip()

        # 기존 광고주 찾기
        existing = c.execute(
            "SELECT id FROM advertisers WHERE name = ? LIMIT 1", (real_name,)
        ).fetchone()

        if existing:
            real_id = existing[0]
        else:
            # 새 광고주 생성
            c.execute("INSERT INTO advertisers (name) VALUES (?)", (real_name,))
            real_id = c.lastrowid

        # ad_details 재매핑
        moved = c.execute(
            "UPDATE ad_details SET advertiser_id = ? WHERE advertiser_id = ?",
            (real_id, junk_id),
        ).rowcount
        stats["ads_moved"] += moved

        # 정크 광고주 삭제
        c.execute("DELETE FROM advertisers WHERE id = ?", (junk_id,))
        stats["together_remapped"] += 1

    # ── 2) 도메인 광고주 삭제 ──
    domain_rows = c.execute(
        """SELECT id, name FROM advertisers
           WHERE name LIKE '%.com%' OR name LIKE '%.kr%'
                 OR name LIKE '%.net%' OR name LIKE '%.co.%'"""
    ).fetchall()

    for junk_id, junk_name in domain_rows:
        # 실제 브랜드 도메인은 보존 (예: coupang.com이 이름인 경우)
        # 순수 도메인만 삭제 (이름이 URL 형태인 경우)
        if not re.match(r"^[a-zA-Z0-9._-]+\.(com|kr|net|co\.\w+)", junk_name):
            continue
        ads_deleted = c.execute(
            "DELETE FROM ad_details WHERE advertiser_id = ?", (junk_id,)
        ).rowcount
        c.execute("DELETE FROM advertisers WHERE id = ?", (junk_id,))
        stats["domain_deleted"] += 1
        stats["ads_deleted"] += ads_deleted

    # ── 3) UI 텍스트 정크 삭제 ──
    for junk_name in UI_JUNK_NAMES:
        row = c.execute("SELECT id FROM advertisers WHERE name = ?", (junk_name,)).fetchone()
        if row:
            ads_deleted = c.execute(
                "DELETE FROM ad_details WHERE advertiser_id = ?", (row[0],)
            ).rowcount
            c.execute("DELETE FROM advertisers WHERE id = ?", (row[0],))
            stats["ui_deleted"] += 1
            stats["ads_deleted"] += ads_deleted

    for prefix in UI_JUNK_PREFIXES:
        rows = c.execute(
            "SELECT id FROM advertisers WHERE name LIKE ?", (f"{prefix}%",)
        ).fetchall()
        for (junk_id,) in rows:
            ads_deleted = c.execute(
                "DELETE FROM ad_details WHERE advertiser_id = ?", (junk_id,)
            ).rowcount
            c.execute("DELETE FROM advertisers WHERE id = ?", (junk_id,))
            stats["ui_deleted"] += 1
            stats["ads_deleted"] += ads_deleted

    # ── 4) 외국어 광고주 삭제 (베트남어/조지아어 등) ──
    all_advs = c.execute("SELECT id, name FROM advertisers").fetchall()
    for adv_id, adv_name in all_advs:
        if not adv_name:
            continue

        # 4a) 외국어 스크립트 감지 -> 캐스케이드 삭제
        foreign_script = _has_foreign_script(adv_name)
        if foreign_script:
            counts = _delete_advertiser_cascade(c, adv_id)
            total_deleted = sum(counts.values())
            stats["foreign_deleted"] += 1
            stats["ads_deleted"] += counts.get("ad_details", 0)
            print(f"  [foreign:{foreign_script}] deleted ID={adv_id} name={adv_name[:60]} cascade={counts}")
            continue

        # 4b) 이름 정제 (zero-width, emoji, fullwidth)
        cleaned = _clean_advertiser_name(adv_name)
        if cleaned != adv_name and cleaned:
            c.execute(
                "UPDATE advertisers SET name = ? WHERE id = ?",
                (cleaned, adv_id),
            )
            stats["name_cleaned"] += 1
            print(f"  [clean] ID={adv_id}: '{adv_name}' -> '{cleaned}'")
        elif not cleaned:
            # Name becomes empty after cleaning -> delete
            counts = _delete_advertiser_cascade(c, adv_id)
            stats["foreign_deleted"] += 1
            stats["ads_deleted"] += counts.get("ad_details", 0)

    conn.commit()
    conn.close()

    print("=== Junk Advertiser Cleanup Complete ===")
    print(f"  Together remapped: {stats['together_remapped']} (ads moved: {stats['ads_moved']})")
    print(f"  Domain deleted: {stats['domain_deleted']}")
    print(f"  UI junk deleted: {stats['ui_deleted']}")
    print(f"  Foreign deleted: {stats['foreign_deleted']}")
    print(f"  Names cleaned: {stats['name_cleaned']}")
    print(f"  Total ads deleted: {stats['ads_deleted']}")
    print(f"  Remaining advertisers: ", end="")

    conn2 = sqlite3.connect(str(DB_PATH))
    cnt = conn2.execute("SELECT COUNT(*) FROM advertisers").fetchone()[0]
    print(cnt)
    conn2.close()


if __name__ == "__main__":
    main()
