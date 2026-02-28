"""Seed demo data for AdScope dashboard testing."""

import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

# Fix path for running from scripts/
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import async_session, init_db
from database.models import (
    Industry, Keyword, Persona, Advertiser, AdSnapshot, AdDetail,
    Campaign, SpendEstimate, BrandChannelContent,
)

# ---- seed data ----

INDUSTRIES = [
    {"name": "IT/Tech", "avg_cpc_min": 800, "avg_cpc_max": 3000},
    {"name": "Finance", "avg_cpc_min": 1500, "avg_cpc_max": 5000},
    {"name": "Beauty", "avg_cpc_min": 500, "avg_cpc_max": 2500},
    {"name": "Food/Beverage", "avg_cpc_min": 400, "avg_cpc_max": 2000},
    {"name": "Automotive", "avg_cpc_min": 2000, "avg_cpc_max": 8000},
    {"name": "E-commerce", "avg_cpc_min": 600, "avg_cpc_max": 3500},
    {"name": "Education", "avg_cpc_min": 700, "avg_cpc_max": 3000},
    {"name": "Others", "avg_cpc_min": 300, "avg_cpc_max": 1500},
]

KEYWORDS_BY_INDUSTRY = {
    "IT/Tech": ["smartphone", "laptop", "cloud service", "AI solution"],
    "Finance": ["credit card", "insurance", "investment", "loan"],
    "Beauty": ["skincare", "makeup", "hair care", "perfume"],
    "Food/Beverage": ["delivery app", "coffee", "health food", "snack"],
    "Automotive": ["SUV", "electric vehicle", "car insurance", "tire"],
    "E-commerce": ["online shopping", "coupon", "sale event", "free shipping"],
    "Education": ["online class", "language learning", "coding bootcamp"],
    "Others": ["general keyword"],
}

PERSONAS = [
    {"code": "M20", "age_group": "20s", "gender": "male", "login_type": "google", "description": "20s male"},
    {"code": "F20", "age_group": "20s", "gender": "female", "login_type": "google", "description": "20s female"},
    {"code": "M30", "age_group": "30s", "gender": "male", "login_type": "naver", "description": "30s male"},
    {"code": "F30", "age_group": "30s", "gender": "female", "login_type": "naver", "description": "30s female"},
    {"code": "M40", "age_group": "40s", "gender": "male", "login_type": "kakao", "description": "40s male"},
    {"code": "F40", "age_group": "40s", "gender": "female", "login_type": "kakao", "description": "40s female"},
]

ADVERTISERS = [
    {"name": "Samsung Electronics", "industry": "IT/Tech", "brand": "Samsung", "website": "https://samsung.com", "revenue": 302e12, "employees": 267000, "founded": 1969, "public": True, "hq": "Suwon"},
    {"name": "Hyundai Motor", "industry": "Automotive", "brand": "Hyundai", "website": "https://hyundai.com", "revenue": 162e12, "employees": 75000, "founded": 1967, "public": True, "hq": "Seoul"},
    {"name": "LG Electronics", "industry": "IT/Tech", "brand": "LG", "website": "https://lge.co.kr", "revenue": 82e12, "employees": 40000, "founded": 1958, "public": True, "hq": "Seoul"},
    {"name": "Naver Corp", "industry": "IT/Tech", "brand": "Naver", "website": "https://naver.com", "revenue": 9.6e12, "employees": 6200, "founded": 1999, "public": True, "hq": "Seongnam"},
    {"name": "Kakao Corp", "industry": "IT/Tech", "brand": "Kakao", "website": "https://kakao.com", "revenue": 7.1e12, "employees": 4500, "founded": 2010, "public": True, "hq": "Jeju"},
    {"name": "Amorepacific", "industry": "Beauty", "brand": "Amorepacific", "website": "https://amorepacific.com", "revenue": 4.2e12, "employees": 8000, "founded": 1945, "public": True, "hq": "Seoul"},
    {"name": "KB Financial", "industry": "Finance", "brand": "KB Kookmin", "website": "https://kbfg.com", "revenue": 13e12, "employees": 28000, "founded": 2008, "public": True, "hq": "Seoul"},
    {"name": "Shinhan Financial", "industry": "Finance", "brand": "Shinhan", "website": "https://shinhan.com", "revenue": 11e12, "employees": 23000, "founded": 2001, "public": True, "hq": "Seoul"},
    {"name": "Coupang", "industry": "E-commerce", "brand": "Coupang", "website": "https://coupang.com", "revenue": 26e12, "employees": 58000, "founded": 2010, "public": True, "hq": "Seoul"},
    {"name": "Baemin (Woowa)", "industry": "Food/Beverage", "brand": "Baemin", "website": "https://baemin.com", "revenue": 2.8e12, "employees": 4000, "founded": 2011, "public": False, "hq": "Seoul"},
    {"name": "SK Telecom", "industry": "IT/Tech", "brand": "SKT", "website": "https://skt.co.kr", "revenue": 17e12, "employees": 5800, "founded": 1984, "public": True, "hq": "Seoul"},
    {"name": "Kia Corp", "industry": "Automotive", "brand": "Kia", "website": "https://kia.com", "revenue": 86e12, "employees": 52000, "founded": 1944, "public": True, "hq": "Seoul"},
    {"name": "Olive Young (CJ)", "industry": "Beauty", "brand": "Olive Young", "website": "https://oliveyoung.co.kr", "revenue": 3.5e12, "employees": 6000, "founded": 1999, "public": False, "hq": "Seoul"},
    {"name": "Toss (Viva Republica)", "industry": "Finance", "brand": "Toss", "website": "https://toss.im", "revenue": 1.2e12, "employees": 2500, "founded": 2013, "public": False, "hq": "Seoul"},
    {"name": "Class101", "industry": "Education", "brand": "Class101", "website": "https://class101.net", "revenue": 80e9, "employees": 400, "founded": 2018, "public": False, "hq": "Seoul"},
    {"name": "Market Kurly", "industry": "E-commerce", "brand": "Kurly", "website": "https://kurly.com", "revenue": 2.1e12, "employees": 3500, "founded": 2015, "public": False, "hq": "Seoul"},
    {"name": "Innisfree", "industry": "Beauty", "brand": "Innisfree", "website": "https://innisfree.com", "revenue": 500e9, "employees": 1200, "founded": 2000, "public": False, "hq": "Seoul"},
    {"name": "Genesis (Hyundai)", "industry": "Automotive", "brand": "Genesis", "website": "https://genesis.com", "revenue": 12e12, "employees": 3000, "founded": 2015, "public": False, "hq": "Seoul"},
]

CHANNELS = ["naver_search", "naver_da", "google_gdn", "youtube_ads", "kakao_da", "instagram", "facebook"]

AD_TEXTS = {
    "IT/Tech": [
        "Galaxy S25 Ultra - AI with Galaxy",
        "LG OLED TV - Perfect Black",
        "Naver Cloud - Enterprise AI Solution",
        "KT 5G Unlimited Plan",
        "SK T1 membership benefits",
    ],
    "Finance": [
        "KB Star Card - 5% cashback",
        "Shinhan Sol - Simple investment",
        "Toss - Send money in 3 seconds",
        "Samsung Life Insurance",
    ],
    "Beauty": [
        "Sulwhasoo First Care Serum",
        "Olive Young SALE - Up to 70% off",
        "Innisfree Green Tea Moisturizer",
        "Laneige Water Sleeping Mask",
    ],
    "Food/Beverage": [
        "Baemin - Free delivery this week",
        "Starbucks Spring Edition",
        "CJ Bibigo Mandu - New flavor",
    ],
    "Automotive": [
        "Hyundai IONIQ 6 - Electric sedan",
        "Kia EV9 - Family SUV",
        "Genesis G90 - Luxury redefined",
    ],
    "E-commerce": [
        "Coupang Rocket Delivery - Order now",
        "Kurly - Fresh groceries at dawn",
        "SSG.COM - Department store online",
    ],
    "Education": [
        "Class101 - Learn anything creative",
        "Megastudy - University prep",
    ],
    "Others": [
        "General advertisement",
    ],
}

POSITION_ZONES = ["top", "middle", "bottom"]
AD_TYPES = ["search_text", "display_banner", "video_preroll", "native_feed", "carousel", "shopping"]


async def seed():
    await init_db()

    async with async_session() as db:
        # Check if data already exists
        result = await db.execute(select(Industry))
        if result.scalars().first():
            print("Data already exists, skipping seed.")
            return

        # 1. Industries
        industry_map = {}
        for ind in INDUSTRIES:
            obj = Industry(name=ind["name"], avg_cpc_min=ind["avg_cpc_min"], avg_cpc_max=ind["avg_cpc_max"])
            db.add(obj)
            await db.flush()
            industry_map[ind["name"]] = obj.id
        print(f"  Industries: {len(industry_map)}")

        # 2. Keywords
        keyword_ids = []
        for ind_name, kws in KEYWORDS_BY_INDUSTRY.items():
            for kw in kws:
                obj = Keyword(
                    industry_id=industry_map[ind_name],
                    keyword=kw,
                    naver_cpc=random.randint(300, 5000),
                    monthly_search_vol=random.randint(1000, 500000),
                )
                db.add(obj)
                await db.flush()
                keyword_ids.append(obj.id)
        print(f"  Keywords: {len(keyword_ids)}")

        # 3. Personas
        persona_ids = []
        for p in PERSONAS:
            obj = Persona(**p)
            db.add(obj)
            await db.flush()
            persona_ids.append(obj.id)
        print(f"  Personas: {len(persona_ids)}")

        # 4. Advertisers
        adv_map = {}  # name -> (id, industry_name)
        for a in ADVERTISERS:
            obj = Advertiser(
                name=a["name"],
                industry_id=industry_map.get(a["industry"]),
                brand_name=a["brand"],
                website=a["website"],
                annual_revenue=a["revenue"],
                employee_count=a["employees"],
                founded_year=a["founded"],
                is_public=a["public"],
                headquarters=a["hq"],
                advertiser_type="company",
                data_source="seed",
                profile_updated_at=datetime.now(timezone.utc),
            )
            db.add(obj)
            await db.flush()
            adv_map[a["name"]] = (obj.id, a["industry"])
        print(f"  Advertisers: {len(adv_map)}")

        # 5. Snapshots + Details (14 days of data, 3-5 snapshots per day)
        now = datetime.now(timezone.utc)
        snapshot_count = 0
        detail_count = 0
        adv_list = list(adv_map.items())

        for day_offset in range(14, 0, -1):
            day = now - timedelta(days=day_offset)
            sessions_per_day = random.randint(3, 6)

            for _ in range(sessions_per_day):
                channel = random.choice(CHANNELS)
                persona_id = random.choice(persona_ids)
                keyword_id = random.choice(keyword_ids)
                hour = random.randint(6, 23)
                captured_at = day.replace(hour=hour, minute=random.randint(0, 59))

                snap = AdSnapshot(
                    keyword_id=keyword_id,
                    persona_id=persona_id,
                    device=random.choice(["pc", "mobile"]),
                    channel=channel,
                    captured_at=captured_at,
                    ad_count=0,
                )
                db.add(snap)
                await db.flush()
                snapshot_count += 1

                # 3-8 ads per snapshot
                num_ads = random.randint(3, 8)
                for pos in range(1, num_ads + 1):
                    adv_name, (adv_id, ind_name) = random.choice(adv_list)
                    texts = AD_TEXTS.get(ind_name, AD_TEXTS["Others"])
                    ad_text = random.choice(texts)

                    detail = AdDetail(
                        snapshot_id=snap.id,
                        advertiser_id=adv_id,
                        advertiser_name_raw=adv_name,
                        brand=adv_map[adv_name][0],  # just use id as placeholder
                        ad_text=ad_text,
                        ad_description=f"Ad by {adv_name}",
                        position=pos,
                        url=f"https://example.com/ad/{adv_id}/{pos}",
                        ad_type=random.choice(AD_TYPES),
                        position_zone=random.choice(POSITION_ZONES),
                        verification_status=random.choice(["verified", "unverified", "likely_verified"]),
                    )
                    db.add(detail)
                    detail_count += 1

                snap.ad_count = num_ads

        print(f"  Snapshots: {snapshot_count}")
        print(f"  Ad Details: {detail_count}")

        # 6. Campaigns + Spend Estimates
        campaign_count = 0
        spend_count = 0
        for adv_name, (adv_id, ind_name) in adv_list:
            num_campaigns = random.randint(1, 3)
            for _ in range(num_campaigns):
                ch = random.choice(CHANNELS)
                first = now - timedelta(days=random.randint(7, 30))
                last = now - timedelta(days=random.randint(0, 3))

                camp = Campaign(
                    advertiser_id=adv_id,
                    channel=ch,
                    first_seen=first,
                    last_seen=last,
                    is_active=random.random() > 0.2,
                    total_est_spend=0,
                    snapshot_count=random.randint(5, 30),
                )
                db.add(camp)
                await db.flush()
                campaign_count += 1

                total_spend = 0
                for d in range(14):
                    date = now - timedelta(days=d)
                    daily = round(random.uniform(50000, 5000000), 0)
                    total_spend += daily
                    se = SpendEstimate(
                        campaign_id=camp.id,
                        date=date,
                        channel=ch,
                        est_daily_spend=daily,
                        confidence=round(random.uniform(0.3, 0.95), 2),
                        calculation_method="cpc_position",
                    )
                    db.add(se)
                    spend_count += 1

                camp.total_est_spend = total_spend

        print(f"  Campaigns: {campaign_count}")
        print(f"  Spend Estimates: {spend_count}")

        await db.commit()
        print("Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
