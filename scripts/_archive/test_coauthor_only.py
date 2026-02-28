"""Quick test: coauthor extraction only."""
import asyncio
import io
import os
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")
os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="DEBUG")

from crawler.instagram_mobile import InstagramMobileCrawler
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import DEFAULT_MOBILE


async def main():
    async with InstagramMobileCrawler() as crawler:
        persona = PERSONAS.get("M30", list(PERSONAS.values())[0])
        device = DEFAULT_MOBILE
        context = await crawler._create_context(persona, device)
        try:
            t0 = time.time()
            ads = await crawler._extract_profile_coauthors(context)
            elapsed = time.time() - t0
            print(f"\nCoauthor result: {len(ads)} ads in {elapsed:.1f}s")
            for ad in ads:
                print(f"  [{ad.get('position')}] {ad.get('advertiser_name')}: "
                      f"{ad.get('ad_text', '')[:60]}...")
                extra = ad.get("extra_data", {})
                print(f"      coauthors={extra.get('coauthor_usernames')}")
        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
