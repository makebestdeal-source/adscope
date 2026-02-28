"""Comprehensive advertiser cleanup v2.

Rules:
1. Remove in-house platform self-promotions (Naver Place, Naver Map, etc.)
2. Strip URLs from advertiser names
3. Strip ad-format prefixes (네이버파워링크, 네이버플러스) from names
4. Remove unverifiable entries (no website, no smartstore, no official channels)
5. Remove blog-only entries
6. Merge duplicates after name cleanup
"""

import io
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DB_PATH = Path(__file__).resolve().parent.parent / "adscope.db"
conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
c = conn.cursor()

DRY_RUN = "--dry-run" in sys.argv

deleted_ids = set()
renamed = {}
stats = defaultdict(int)

# ── Step 1: In-house platform self-promotions ──
INHOUSE_PATTERNS = [
    # Naver self-services
    r"^네이버$",
    r"^네이버 해피빈",
    r"네이버플레이스",
    r"네이버지도",
    r"네이버맵",
    r"네이버페이",
    r"^네이버쇼핑$",
    r"m\.place\.naver\.com",
    r"map\.naver\.com",
]

print("=== Step 1: In-house platform entries ===")
c.execute("SELECT id, name, website FROM advertisers")
all_rows = c.fetchall()

for row in all_rows:
    aid, name, website = row["id"], row["name"], row["website"]
    for pat in INHOUSE_PATTERNS:
        if re.search(pat, name or ""):
            print(f"  [DELETE] id={aid} | {name}")
            deleted_ids.add(aid)
            stats["inhouse"] += 1
            break

# ── Step 2: Strip URL from names + prefixes ──
print("\n=== Step 2: Clean advertiser names ===")

# Prefixes to strip (ad format names, not the real advertiser)
PREFIXES = ["네이버파워링크 ", "네이버플러스 ", "네이버로그인 "]

# URL/domain patterns to strip from end of names
_URL_PATTERNS = [
    # Full URLs
    re.compile(r'\s+https?://\S+$'),
    # naver subdomains
    re.compile(r'\s*(?:https?://)?(?:smartstore|brand|m|map|place)\.naver\.com/\S*$'),
    # Subdomain URLs (m.xxx.com, direct.xxx.com, etc.)
    re.compile(r'\s+[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.(?:com|co\.kr|kr|net|org|io)\S*$'),
    # Simple domain URLs
    re.compile(r'\s+(?:https?://)?[a-zA-Z0-9가-힣_-]+\.(?:com|co\.kr|kr|net|org|io|me|ai|app|store|shop)\S*$'),
    # Korean domain URLs (한글.com)
    re.compile(r'\s+[가-힣]+\.(?:com|kr|net)\S*$'),
    # Residual partial URLs (ending with dot + fragment)
    re.compile(r'\s+[a-zA-Z0-9._-]+\.(?:com|co\.kr|kr|net|org|io)\S*$'),
    # cafe24/other hosting
    re.compile(r'\s+\S+\.cafe24\.com\S*$'),
]

c.execute("SELECT id, name FROM advertisers")
for row in c.fetchall():
    aid, name = row["id"], row["name"]
    if aid in deleted_ids:
        continue

    original = name

    # Strip prefixes
    for prefix in PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]

    # Strip trailing URLs (apply all patterns repeatedly)
    for _ in range(3):
        prev = name
        for url_pat in _URL_PATTERNS:
            name = url_pat.sub("", name)
        name = name.strip()
        if name == prev:
            break

    # Remove residual partial domain fragments (e.g. "brand.", "direct.", "mstore.")
    name = re.sub(r'\s+[a-zA-Z0-9._-]*\.$', '', name)
    name = name.rstrip(". ")

    name = name.strip()

    if name != original and name:
        print(f"  [RENAME] id={aid} | {original} -> {name}")
        renamed[aid] = name
        stats["renamed"] += 1
    elif not name:
        print(f"  [DELETE] id={aid} | {original} (empty after cleanup)")
        deleted_ids.add(aid)
        stats["empty_name"] += 1

# ── Step 3: Blog-only entries ──
print("\n=== Step 3: Blog-only entries ===")
c.execute("SELECT id, name, website FROM advertisers")
for row in c.fetchall():
    aid, name, website = row["id"], row["name"], row["website"]
    if aid in deleted_ids:
        continue

    effective_name = renamed.get(aid, name)

    # Check if name or website is blog-based only
    is_blog = False
    if "blog.naver.com" in (effective_name or ""):
        is_blog = True
    if "blog.naver.com" in (website or "") and not any(
        x in (website or "") for x in ["smartstore", "brand.naver"]
    ):
        is_blog = True

    if is_blog:
        print(f"  [DELETE] id={aid} | {name}")
        deleted_ids.add(aid)
        stats["blog_only"] += 1

# ── Step 4: URL-only names (name is just a URL) ──
print("\n=== Step 4: URL-only names ===")
c.execute("SELECT id, name FROM advertisers")
for row in c.fetchall():
    aid, name = row["id"], row["name"]
    if aid in deleted_ids:
        continue

    effective_name = renamed.get(aid, name)

    # Name is purely a URL or domain
    if re.match(r'^(?:https?://)?[a-zA-Z0-9._-]+\.(com|co\.kr|kr|net|org|io)(?:/\S*)?$', effective_name or ""):
        print(f"  [DELETE] id={aid} | {name} (URL-only name)")
        deleted_ids.add(aid)
        stats["url_only_name"] += 1

# ── Step 5: No verifiable presence ──
print("\n=== Step 5: Unverifiable advertisers (no website, no channels, no ads) ===")
c.execute("""
    SELECT a.id, a.name, a.website, a.official_channels,
           (SELECT COUNT(*) FROM ad_details WHERE advertiser_id = a.id) as ad_count
    FROM advertisers a
""")
for row in c.fetchall():
    aid = row["id"]
    if aid in deleted_ids:
        continue

    name = renamed.get(aid, row["name"])
    website = row["website"]
    channels = row["official_channels"]
    ad_count = row["ad_count"]

    has_web = bool(website and len(website) > 5 and "." in website)
    has_channels = bool(channels and channels != "{}" and channels != "null")

    # If no web presence AND no ads, delete
    if not has_web and not has_channels and ad_count == 0:
        print(f"  [DELETE] id={aid} | {name} (no website, no channels, no ads)")
        deleted_ids.add(aid)
        stats["no_presence"] += 1

# ── Step 6: Merge duplicates after rename ──
print("\n=== Step 6: Duplicate detection after cleanup ===")
name_to_ids = defaultdict(list)
c.execute("SELECT id, name FROM advertisers")
for row in c.fetchall():
    aid, name = row["id"], row["name"]
    if aid in deleted_ids:
        continue
    effective_name = renamed.get(aid, name)
    name_to_ids[effective_name.strip().lower()].append(aid)

for name, ids in name_to_ids.items():
    if len(ids) <= 1:
        continue
    # Keep the one with most ads
    best_id = None
    best_count = -1
    for aid in ids:
        c.execute("SELECT COUNT(*) FROM ad_details WHERE advertiser_id = ?", (aid,))
        cnt = c.fetchone()[0]
        if cnt > best_count:
            best_count = cnt
            best_id = aid

    for aid in ids:
        if aid != best_id:
            print(f"  [MERGE] id={aid} -> id={best_id} | {name}")
            # Reassign ads and campaigns
            if not DRY_RUN:
                c.execute("UPDATE ad_details SET advertiser_id = ? WHERE advertiser_id = ?",
                          (best_id, aid))
                c.execute("UPDATE campaigns SET advertiser_id = ? WHERE advertiser_id = ?",
                          (best_id, aid))
            deleted_ids.add(aid)
            stats["merged"] += 1

# ── Execute ──
if not DRY_RUN:
    print(f"\n=== Executing: {len(deleted_ids)} deletes, {len(renamed)} renames ===")

    # Renames first
    for aid, new_name in renamed.items():
        if aid not in deleted_ids:
            c.execute("UPDATE advertisers SET name = ? WHERE id = ?", (new_name, aid))

    # Cascade deletes
    for aid in deleted_ids:
        c.execute("DELETE FROM ad_details WHERE advertiser_id = ?", (aid,))
        c.execute("DELETE FROM campaigns WHERE advertiser_id = ?", (aid,))
        c.execute("DELETE FROM advertisers WHERE id = ?", (aid,))

    conn.commit()

    c.execute("SELECT COUNT(*) FROM advertisers")
    print(f"Remaining advertisers: {c.fetchone()[0]}")
else:
    print(f"\n=== DRY RUN: would delete {len(deleted_ids)}, rename {len(renamed)} ===")

print(f"\n=== Stats ===")
for k, v in sorted(stats.items()):
    print(f"  {k}: {v}")

conn.close()
