"""이미지 유틸리티 — 매직 바이트 기반 검증/확장자 추출 + 병렬 다운로드.

여러 크롤러에서 중복으로 구현되던 로직을 단일 모듈로 통합.
"""
from __future__ import annotations

import asyncio
from pathlib import Path


def is_valid_image(data: bytes) -> bool:
    """매직 바이트로 유효한 이미지 파일인지 검증."""
    if len(data) < 8:
        return False
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    if data[:2] == b"BM":
        return True
    if b"<svg" in data[:500]:
        return True
    return False


def detect_image_ext(data: bytes) -> str:
    """매직 바이트 기반으로 이미지 확장자 결정."""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"\x89PNG":
        return ".png"
    return ".png"


# ── 병렬 다운로드 ──

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
}


async def _dl_one(
    session,
    url: str,
    save_path: Path,
    min_size: int = 200,
    retries: int = 3,
) -> bool:
    """단일 이미지 URL 다운로드 (재시도 포함). aiohttp.ClientSession 재사용."""
    for attempt in range(retries):
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return False
                content = await resp.read()
                if len(content) < min_size or not is_valid_image(content):
                    return False
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(content)
                return True
        except Exception:
            if attempt < retries - 1:
                await asyncio.sleep(0.3 * (attempt + 1))
    return False


async def batch_download(
    url_to_path: dict[str, Path],
    extra_headers: dict | None = None,
    concurrency: int = 8,
    timeout: int = 10,
    retries: int = 3,
    min_size: int = 200,
) -> dict[str, bool]:
    """여러 이미지 URL을 병렬로 다운로드.

    Args:
        url_to_path: {다운로드 URL: 저장 경로}
        extra_headers: 추가 HTTP 헤더 (User-Agent 등 덮어쓰기 가능)
        concurrency: 동시 다운로드 최대 수
        timeout: 개별 요청 타임아웃(초)
        retries: 실패 시 재시도 횟수
        min_size: 유효 이미지 최소 바이트 크기

    Returns:
        {url: 성공여부(bool)}
    """
    if not url_to_path:
        return {}

    try:
        import aiohttp
    except ImportError:
        # aiohttp 없으면 httpx로 순차 fallback
        return await _batch_download_httpx_fallback(url_to_path, timeout, retries, min_size)

    headers = dict(_DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)

    sem = asyncio.Semaphore(concurrency)
    client_timeout = aiohttp.ClientTimeout(total=timeout)

    async def _bounded(url: str, path: Path):
        async with sem:
            return url, await _dl_one(session, url, path, min_size, retries)

    async with aiohttp.ClientSession(headers=headers, timeout=client_timeout) as session:
        results = await asyncio.gather(
            *[_bounded(url, path) for url, path in url_to_path.items()],
            return_exceptions=True,
        )

    out: dict[str, bool] = {}
    for r in results:
        if isinstance(r, Exception):
            continue
        url, success = r
        out[url] = success
    return out


async def _batch_download_httpx_fallback(
    url_to_path: dict[str, Path],
    timeout: int,
    retries: int,
    min_size: int,
) -> dict[str, bool]:
    """aiohttp 없을 때 httpx로 순차 다운로드."""
    import httpx
    out: dict[str, bool] = {}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=_DEFAULT_HEADERS) as client:
        for url, path in url_to_path.items():
            for attempt in range(retries):
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        content = resp.content
                        if len(content) >= min_size and is_valid_image(content):
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(content)
                            out[url] = True
                            break
                except Exception:
                    if attempt < retries - 1:
                        await asyncio.sleep(0.3)
            else:
                out[url] = False
    return out
