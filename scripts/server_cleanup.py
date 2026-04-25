import sqlite3
import os

db_path = os.environ.get("DB_PATH", "/data/adscope.db")
print(f"Using DB: {db_path}")

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check before
c.execute("SELECT COUNT(*) FROM advertisers")
print(f"Before - advertisers: {c.fetchone()[0]}")
c.execute("SELECT COUNT(*) FROM ad_details")
print(f"Before - ad_details: {c.fetchone()[0]}")

# Delete ad_details for advertisers without website
c.execute("DELETE FROM ad_details WHERE advertiser_id IN (SELECT id FROM advertisers WHERE website IS NULL OR website = '')")
print(f"Deleted ad_details: {c.rowcount}")

# Delete advertisers without website
c.execute("DELETE FROM advertisers WHERE website IS NULL OR website = ''")
print(f"Deleted advertisers: {c.rowcount}")

# Delete orphan ad_details
c.execute("DELETE FROM ad_details WHERE advertiser_id IS NULL")
print(f"Deleted orphans: {c.rowcount}")

conn.commit()

# Check after
c.execute("SELECT COUNT(*) FROM advertisers")
print(f"After - advertisers: {c.fetchone()[0]}")
c.execute("SELECT COUNT(*) FROM ad_details")
print(f"After - ad_details: {c.fetchone()[0]}")

conn.close()
print("Done")
