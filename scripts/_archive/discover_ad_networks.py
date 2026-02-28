"""퍼블리셔 ads.txt 파싱 → 광고 네트워크 발견 + i마크 패턴 검출."""
import io
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests

# ── 한국 주요 퍼블리셔 20개 ──────────────────────────────────────────
PUBLISHERS = [
    # 종합일간지
    "chosun.com",
    "joongang.co.kr",
    "donga.com",
    "hani.co.kr",
    "khan.co.kr",
    "kmib.co.kr",           # 국민일보
    "munhwa.com",           # 문화일보
    # 경제지
    "mk.co.kr",             # 매일경제
    "hankyung.com",         # 한국경제
    "sedaily.com",          # 서울경제
    "mt.co.kr",             # 머니투데이
    "edaily.co.kr",         # 이데일리
    # 방송사
    "sbs.co.kr",
    "imbc.com",
    "kbs.co.kr",
    # IT/포털
    "zdnet.co.kr",
    "bloter.net",
    # 스포츠/연예
    "sports.chosun.com",
    "sportsdonga.com",
    "insight.co.kr",
]

# ── 현재 AdScope 수집 중인 매체 도메인 매핑 ──────────────────────────
COLLECTING_DOMAINS = {
    # Google (GDN + Search)
    "google.com": "google",
    "googleads.g.doubleclick.net": "google",
    "googlesyndication.com": "google",
    "googleadservices.com": "google",
    # Naver
    "naver.com": "naver",
    "adsun.naver.com": "naver",
    # Kakao
    "kakao.com": "kakao",
    "daum.net": "kakao",
    # Meta (FB/IG)
    "facebook.com": "meta",
    "instagram.com": "meta",
    "audiencenetwork.com": "meta",
    # YouTube (Google 계열이지만 별도)
    "youtube.com": "youtube",
    # TikTok
    "tiktok.com": "tiktok",
    "bytedance.com": "tiktok",
}

# ── i마크(인터넷광고심의기구) 관련 URL 패턴 ──────────────────────────
IMARK_PATTERNS = [
    "adchoices",
    "aboutads.info",
    "youradchoices",
    "optout.aboutads",
    "youronlinechoices",
    "iabkorea",
    "kism.or.kr",           # 한국인터넷자율정책기구
    "admark",
    "ad-mark",
    "i-mark",
    "imark",
    "internet-ad",
    "onlinead",
]


def fetch_ads_txt(domain: str, timeout: int = 10) -> str | None:
    """도메인의 /ads.txt를 다운로드. 실패 시 None 반환."""
    urls_to_try = [
        f"https://{domain}/ads.txt",
        f"https://www.{domain}/ads.txt",
        f"http://{domain}/ads.txt",
    ]
    for url in urls_to_try:
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AdScope/1.0)"},
                allow_redirects=True,
            )
            if resp.status_code == 200 and len(resp.text) > 10:
                # ads.txt는 텍스트여야 함 (HTML 응답 필터)
                ct = resp.headers.get("content-type", "")
                if "html" in ct.lower() and "<html" in resp.text[:500].lower():
                    continue
                return resp.text
        except Exception:
            continue
    return None


def parse_ads_txt(content: str) -> list[dict]:
    """ads.txt 텍스트를 파싱하여 엔트리 리스트 반환.

    형식: domain, publisher_id, relationship, cert_authority_id (optional)
    """
    entries = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        # 주석/빈 줄/변수 선언(CONTACT=, SUBDOMAIN= 등) 건너뜀
        if not line or line.startswith("#") or "=" in line.split(",")[0]:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        domain = parts[0].lower()
        pub_id = parts[1].strip()
        relationship = parts[2].upper().strip()
        cert_id = parts[3].strip() if len(parts) >= 4 else ""

        if relationship not in ("DIRECT", "RESELLER"):
            continue

        entries.append({
            "domain": domain,
            "publisher_id": pub_id,
            "relationship": relationship,
            "cert_authority_id": cert_id,
        })
    return entries


def detect_imark_patterns(content: str) -> list[str]:
    """ads.txt 내용에서 i마크 관련 패턴을 감지."""
    found = []
    lower = content.lower()
    for pat in IMARK_PATTERNS:
        if pat.lower() in lower:
            found.append(pat)
    return found


def classify_network(domain: str) -> str:
    """도메인이 수집 중인 매체인지 판별."""
    # 직접 매칭
    if domain in COLLECTING_DOMAINS:
        return "collecting"
    # 부분 매칭 (google 계열 등)
    for known, _ in COLLECTING_DOMAINS.items():
        if known in domain or domain in known:
            return "collecting"
    # Google 계열 추가 체크
    if "google" in domain or "doubleclick" in domain:
        return "collecting"
    if "naver" in domain:
        return "collecting"
    if "kakao" in domain or "daum" in domain:
        return "collecting"
    if "facebook" in domain or "meta" in domain or "instagram" in domain:
        return "collecting"
    if "youtube" in domain:
        return "collecting"
    if "tiktok" in domain or "bytedance" in domain:
        return "collecting"
    return "not_collecting"


def main():
    print("[ads.txt Discovery] Starting...")
    start = time.time()

    all_entries: list[dict] = []
    network_entry_counter: Counter = Counter()   # 총 엔트리 수 (DIRECT+RESELLER 각각)
    network_publishers: dict[str, set] = defaultdict(set)  # 퍼블리셔 집합
    publisher_results: list[dict] = []
    imark_findings: list[dict] = []
    errors: list[str] = []

    for i, pub in enumerate(PUBLISHERS, 1):
        print(f"  [{i}/{len(PUBLISHERS)}] {pub} ...", end=" ", flush=True)
        content = fetch_ads_txt(pub)
        if content is None:
            print("FAIL (unreachable or no ads.txt)")
            errors.append(pub)
            publisher_results.append({
                "domain": pub,
                "status": "error",
                "entry_count": 0,
            })
            continue

        entries = parse_ads_txt(content)
        print(f"OK ({len(entries)} entries)")

        publisher_results.append({
            "domain": pub,
            "status": "ok",
            "entry_count": len(entries),
        })

        for e in entries:
            nd = e["domain"]
            network_entry_counter[nd] += 1
            network_publishers[nd].add(pub)
        all_entries.extend(entries)

        # i마크 패턴 검출
        imark = detect_imark_patterns(content)
        if imark:
            imark_findings.append({
                "publisher": pub,
                "patterns_found": imark,
            })

    # ── 집계 ──────────────────────────────────────────────────────────
    checked = len(PUBLISHERS)
    ok_count = checked - len(errors)

    # 퍼블리셔 수 기준 정렬 (높은 순)
    ad_networks = []
    for domain in network_publishers:
        pub_count = len(network_publishers[domain])
        status = classify_network(domain)
        ad_networks.append({
            "domain": domain,
            "count": pub_count,           # 이 네트워크가 등장한 퍼블리셔 수
            "entries_total": network_entry_counter[domain],  # 총 엔트리(줄) 수
            "publishers": sorted(network_publishers[domain]),
            "relationship_types": list(set(
                e["relationship"] for e in all_entries if e["domain"] == domain
            )),
            "status": status,
        })
    ad_networks.sort(key=lambda x: (-x["count"], -x["entries_total"]))

    # ── 미수집 매체 추천 ──────────────────────────────────────────────
    recommendations = []
    not_collecting = [
        n for n in ad_networks
        if n["status"] == "not_collecting" and n["count"] >= 3
    ]
    not_collecting.sort(key=lambda x: -x["count"])

    for n in not_collecting[:15]:
        recommendations.append(
            f"{n['domain']} 수집 추가 권장 ({n['count']}/{ok_count} 퍼블리셔에서 발견)"
        )

    # ── i마크 검증 결과 ───────────────────────────────────────────────
    imark_summary = {
        "total_publishers_with_imark": len(imark_findings),
        "details": imark_findings,
        "note": "ads.txt 내 adchoices/aboutads 등 자율규제 패턴 포함 여부",
    }

    # ── 통계 ──────────────────────────────────────────────────────────
    collecting_count = sum(1 for n in ad_networks if n["status"] == "collecting")
    not_collecting_count = sum(1 for n in ad_networks if n["status"] == "not_collecting")

    result = {
        "discovery_date": datetime.now().strftime("%Y-%m-%d"),
        "publishers_checked": checked,
        "publishers_ok": ok_count,
        "publishers_failed": errors,
        "total_unique_networks": len(ad_networks),
        "collecting_networks": collecting_count,
        "not_collecting_networks": not_collecting_count,
        "total_entries_parsed": len(all_entries),
        "ad_networks": ad_networks,
        "recommendations": recommendations,
        "imark_verification": imark_summary,
        "publisher_details": publisher_results,
    }

    # ── 저장 ──────────────────────────────────────────────────────────
    out_dir = Path(_root) / "data"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "ad_networks_discovery.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start

    # ── 콘솔 리포트 ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"[ads.txt Discovery] Complete in {elapsed:.1f}s")
    print(f"  Publishers: {ok_count}/{checked} OK")
    print(f"  Total entries parsed: {len(all_entries)}")
    print(f"  Unique ad networks: {len(ad_networks)}")
    print(f"    - Collecting: {collecting_count}")
    print(f"    - Not collecting: {not_collecting_count}")

    print(f"\n-- Top 20 Ad Networks (by publisher count) --")
    for n in ad_networks[:20]:
        tag = "[O]" if n["status"] == "collecting" else "[X]"
        print(f"  {tag} {n['domain']:40s} {n['count']:2d}/{ok_count} publishers  ({n['entries_total']:5d} entries)")

    if recommendations:
        print(f"\n-- Recommendations ({len(recommendations)}) --")
        for r in recommendations:
            print(f"  * {r}")

    if imark_findings:
        print(f"\n-- i-Mark Patterns Found ({len(imark_findings)} publishers) --")
        for item in imark_findings:
            print(f"  {item['publisher']}: {', '.join(item['patterns_found'])}")

    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
