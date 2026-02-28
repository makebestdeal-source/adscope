"""크로스체킹 실행 스크립트 — 미검증 광고의 Meta/Google 일괄 검증.

사용법:
    python scripts/run_cross_verification.py --days 7 --limit 50
"""

import argparse
import asyncio
import io
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://adscope:adscope@localhost:5433/adscope"


async def main():
    parser = argparse.ArgumentParser(description="Cross-verify unverified ads")
    parser.add_argument("--days", type=int, default=7, help="Check ads from last N days")
    parser.add_argument("--limit", type=int, default=50, help="Max advertisers to verify")
    parser.add_argument("--concurrent", type=int, default=3, help="Max concurrent browser tabs")
    parser.add_argument("--timeout", type=int, default=15000, help="Page timeout in ms")
    args = parser.parse_args()

    # 동시성/타임아웃 환경변수 설정
    os.environ["CROSS_VERIFY_CONCURRENT"] = str(args.concurrent)
    os.environ["CROSS_VERIFY_TIMEOUT_MS"] = str(args.timeout)

    from processor.cross_verifier import batch_verify_unverified

    print("=" * 60)
    print("  AdScope 크로스체킹 (Meta + Google)")
    print("=" * 60)
    print(f"  기간: 최근 {args.days}일")
    print(f"  최대 검증 수: {args.limit}명")
    print(f"  동시 탭: {args.concurrent}개")
    print(f"  타임아웃: {args.timeout}ms")
    print("=" * 60)

    stats = await batch_verify_unverified(days=args.days, limit=args.limit)

    print(f"\n{'=' * 60}")
    print("  크로스체킹 결과")
    print(f"{'=' * 60}")
    print(f"  검증 완료: {stats['total_checked']}명")
    print(f"  확인됨: {stats['verified']}명")
    print(f"  미확인: {stats['unverified']}명")
    print(f"  오류: {stats['errors']}건")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
