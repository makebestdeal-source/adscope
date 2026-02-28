"""OpenAds.co.kr 광고상품 504개 + 마케팅솔루션 90개 전체 스크래핑.

결과: database/seed_data/openads_products.json
용도: 매체 확장 계획 수립, 광고상품 DB 구축
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

BASE = "https://www.openads.co.kr"
LIST_URL = f"{BASE}/item/findAnyItemList"
DETAIL_URL = f"{BASE}/item/itemDetail/loadItemWithLikeSubscribe"
OUTPUT = Path(__file__).resolve().parent.parent / "database" / "seed_data" / "openads_products.json"


async def fetch_list(client: httpx.AsyncClient) -> list[dict]:
    """전체 광고상품 목록 가져오기 (최대 600개)."""
    items = []
    offset = 0
    limit = 100
    while True:
        resp = await client.get(LIST_URL, params={
            "offset": offset,
            "limit": limit,
            "sorter": "REG_TIME",
        })
        data = resp.json()
        # 응답 구조: {"success": true, "message": {"totalCount": 594, "items": [...]}}
        msg = data.get("message", {})
        batch = msg.get("items", [])
        if not batch:
            break
        items.extend(batch)
        total = msg.get("totalCount", "?")
        print(f"  list: offset={offset}, got={len(batch)}, total_so_far={len(items)}/{total}")
        if len(batch) < limit:
            break
        offset += limit
    return items


async def fetch_detail(client: httpx.AsyncClient, item_id: int) -> dict | None:
    """개별 광고상품 상세 정보. 응답: {success, message: {itemData: {item, adp, doc, link}}}"""
    try:
        resp = await client.get(DETAIL_URL, params={"itemId": item_id}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            msg = data.get("message", {})
            item_data = msg.get("itemData", {})
            item_info = item_data.get("item", {})
            adp = item_data.get("adp", {})
            return {
                "itemName": item_info.get("itemName"),
                "itemUrl": item_info.get("itemUrl"),
                "questionEmail": item_info.get("questionEmail"),
                "devices": [d.get("deviceName") for d in (adp.get("devices") or [])],
                "creations": [c.get("creationTypeName") for c in (adp.get("creations") or [])],
                "billings": [b.get("billingName") for b in (adp.get("billings") or [])],
                "targetPossible": (adp.get("itemAdItem") or {}).get("tgtPossYn") == "Y",
            }
    except Exception as e:
        print(f"  detail error {item_id}: {e}")
    return None


async def main():
    print("=== OpenAds 광고상품 스크래핑 시작 ===")

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        follow_redirects=True,
        timeout=30,
    ) as client:
        # 1. 목록 수집
        items = await fetch_list(client)
        print(f"\n총 {len(items)}개 상품 목록 수집")

        # 2. 광고상품만 필터 (sectionName == '광고상품')
        ad_items = [i for i in items if i.get("sectionName") == "광고상품"]
        sol_items = [i for i in items if i.get("sectionName") != "광고상품"]
        print(f"  광고상품: {len(ad_items)}개, 마케팅솔루션: {len(sol_items)}개")

        # 3. 상세 정보 수집 (광고상품 우선, 병렬 5개씩)
        results = []
        sem = asyncio.Semaphore(5)

        async def fetch_with_sem(item):
            async with sem:
                item_id = item.get("itemId")
                detail = await fetch_detail(client, item_id)
                return {
                    "item_id": item_id,
                    "item_name": item.get("itemName"),
                    "section": item.get("sectionName"),
                    "description": item.get("itemTypeDesc"),
                    "reg_date": item.get("regDtime"),
                    "target_possible": item.get("tgtPossYn") == "Y",
                    "detail": detail,
                }

        # 광고상품 상세 수집
        print(f"\n광고상품 {len(ad_items)}개 상세 수집 중...")
        tasks = [fetch_with_sem(i) for i in ad_items]
        for i in range(0, len(tasks), 20):
            batch = await asyncio.gather(*tasks[i:i+20])
            results.extend(batch)
            ok = sum(1 for r in batch if r["detail"])
            print(f"  batch {i//20+1}: {ok}/{len(batch)} success")

        # 마케팅솔루션 상세 (선택)
        print(f"\n마케팅솔루션 {len(sol_items)}개 상세 수집 중...")
        tasks2 = [fetch_with_sem(i) for i in sol_items]
        for i in range(0, len(tasks2), 20):
            batch = await asyncio.gather(*tasks2[i:i+20])
            results.extend(batch)

        # 4. 저장
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        ok_count = sum(1 for r in results if r["detail"])
        print(f"\n=== 완료: {len(results)}개 상품, 상세 {ok_count}개 ===")
        print(f"저장: {OUTPUT}")

        # 5. 매체/지면 요약
        devices = set()
        billings = set()
        creations = set()
        for r in results:
            d = r.get("detail")
            if not d:
                continue
            for dev in (d.get("devices") or []):
                devices.add(dev)
            for b in (d.get("billings") or []):
                billings.add(b)
            for c in (d.get("creations") or []):
                creations.add(c)

        print(f"\n기기: {sorted(devices)}")
        print(f"과금: {sorted(billings)}")
        print(f"소재유형: {sorted(creations)}")

        # 광고상품 이름 목록
        ad_names = [r["item_name"] for r in results if r["section"] == "광고상품" and r["item_name"]]
        print(f"\n광고상품 {len(ad_names)}개:")
        for name in ad_names[:30]:
            print(f"  - {name}")


if __name__ == "__main__":
    asyncio.run(main())
