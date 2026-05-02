"""stored_images/ → Cloudflare R2 bulk upload (멀티스레드)"""
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import boto3
from botocore.config import Config

R2_ACCOUNT_ID = "7b2a462d79a10923b3ae2b9c0770d067"
R2_ACCESS_KEY  = "16802dc229e662587d9885046a8c53b9"
R2_SECRET_KEY  = "a6acddb36fd754f12d7d9d3d60750cc13cf62919d2d8b9fc73038ad7832f511d"
R2_BUCKET      = "adscope-images"
R2_ENDPOINT    = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
BASE_DIR       = Path("stored_images")
WORKERS        = 64
CHECKPOINT     = Path(".r2_upload_checkpoint.txt")

def make_client():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
        config=Config(retries={"max_attempts": 3}),
    )

def upload_file(key: str, path: Path) -> str:
    ext = path.suffix.lower()
    ct = "image/webp" if ext == ".webp" else "image/png" if ext == ".png" else "image/jpeg"
    client = make_client()
    client.upload_file(str(path), R2_BUCKET, key, ExtraArgs={"ContentType": ct})
    return key

def main():
    all_files = [(str(f.relative_to(BASE_DIR)).replace("\\", "/"), f)
                 for f in BASE_DIR.rglob("*") if f.is_file()]
    total = len(all_files)
    print(f"총 {total:,}개 파일 업로드 시작 (workers={WORKERS})")

    # 체크포인트: 이미 올린 파일 건너뜀
    done = set()
    if CHECKPOINT.exists():
        done = set(CHECKPOINT.read_text(encoding="utf-8", errors="ignore").splitlines())
        print(f"체크포인트: {len(done):,}개 이미 완료, {total - len(done):,}개 남음")

    todo = [(k, p) for k, p in all_files if k not in done]
    cp_file = CHECKPOINT.open("a", encoding="utf-8")

    success = len(done)
    failed = []

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(upload_file, k, p): k for k, p in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            key = futures[fut]
            try:
                fut.result()
                cp_file.write(key + "\n")
                cp_file.flush()
                success += 1
            except Exception as e:
                failed.append((key, str(e)))
            if i % 500 == 0 or i == len(todo):
                pct = (success / total) * 100
                print(f"  {success:,}/{total:,} ({pct:.1f}%) | 실패 {len(failed)}건", flush=True)

    cp_file.close()
    print(f"\n완료: {success:,}개 업로드, {len(failed)}개 실패")
    if failed:
        print("실패 목록 (최대 20개):")
        for k, e in failed[:20]:
            print(f"  {k}: {e}")

if __name__ == "__main__":
    os.chdir(Path(__file__).parent.parent)
    main()
