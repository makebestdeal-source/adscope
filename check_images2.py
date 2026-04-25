import sqlite3, os

conn = sqlite3.connect('adscope.db')
c = conn.cursor()

# 전체 경로 패턴 분석
c.execute('SELECT creative_image_path FROM ad_details WHERE creative_image_path IS NOT NULL AND creative_image_path <> ""')
rows = c.fetchall()

patterns = {}
abs_paths = 0
rel_stored = 0
rel_screenshots = 0
missing_count = 0

for r in rows:
    path = r[0]
    fpath = path.replace('\\', '/')

    if path.startswith('C:') or path.startswith('c:'):
        abs_paths += 1
    elif 'stored_images' in path:
        rel_stored += 1
    elif 'screenshots' in path:
        rel_screenshots += 1

    if not os.path.exists(fpath):
        missing_count += 1

print(f'전체: {len(rows)}건')
print(f'  절대경로(C:\\...): {abs_paths}건 -> 서버에서 깨짐')
print(f'  stored_images/...: {rel_stored}건')
print(f'  screenshots/...: {rel_screenshots}건')
print(f'실제 파일 없음: {missing_count}건')

# extra_data에 image_url 있는지 확인
c.execute('SELECT extra_data FROM ad_details WHERE extra_data IS NOT NULL AND extra_data <> "" AND creative_image_path IS NULL LIMIT 5')
for r in c.fetchall():
    print('extra_data 샘플:', str(r[0])[:200])

conn.close()
