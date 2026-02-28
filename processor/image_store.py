"""이미지 스토리지 추상화 — 로컬/S3 스토리지 팩토리.

크롤러 스크린샷을 WebP 변환 후 저장.
IMAGE_STORE_TYPE 환경변수로 백엔드 선택 (local/s3).
"""

from __future__ import annotations

import asyncio
import os
import shutil
from abc import ABC, abstractmethod
from datetime import datetime
from io import BytesIO
from pathlib import Path

from loguru import logger
from PIL import Image


class ImageStore(ABC):
    """이미지 저장소 인터페이스."""

    @abstractmethod
    async def save(self, source_path: str, channel: str, category: str = "screenshot") -> str:
        """이미지를 WebP 변환 후 저장.

        Args:
            source_path: 원본 PNG 경로
            channel: 채널명 (naver_search, google_gdn 등)
            category: 분류 (screenshot, element, creative)

        Returns:
            저장된 이미지의 접근 경로/URL
        """

    @abstractmethod
    async def get_url(self, stored_path: str) -> str:
        """저장된 이미지의 접근 URL 반환."""

    @abstractmethod
    async def delete(self, stored_path: str) -> bool:
        """이미지 삭제."""

    @abstractmethod
    async def cleanup(self, older_than_days: int = 90) -> int:
        """오래된 이미지 정리. 삭제 건수 반환."""


_IMAGE_MAGIC = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpeg",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"BM": "bmp",
}


def _is_valid_image_file(source_path: str) -> bool:
    """파일이 실제 이미지 바이너리인지 매직 바이트로 확인.

    PNG 확장자이지만 JS/HTML 텍스트인 경우를 걸러낸다.
    """
    try:
        with open(source_path, "rb") as f:
            header = f.read(12)
        if len(header) < 4:
            return False
        # RIFF...WEBP
        if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
            return True
        for magic in _IMAGE_MAGIC:
            if header[:len(magic)] == magic:
                return True
        return False
    except Exception:
        return False


def _convert_to_webp(source_path: str, quality: int = 80) -> bytes:
    """PNG -> WebP 변환 (평균 60% 용량 절감).

    WebP 최대 16383px 제한을 초과하면 리사이즈.
    """
    with Image.open(source_path) as img:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        # WebP 최대 크기 제한 (16383px)
        max_dim = 16383
        if img.width > max_dim or img.height > max_dim:
            ratio = min(max_dim / img.width, max_dim / img.height)
            new_w = int(img.width * ratio)
            new_h = int(img.height * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="WebP", quality=quality, method=4)
        return buf.getvalue()


def _generate_key(channel: str, category: str, source_name: str) -> str:
    """저장 경로 키 생성: channel/YYYYMMDD/category/filename.webp"""
    date_str = datetime.now().strftime("%Y%m%d")
    stem = Path(source_name).stem
    return f"{channel}/{date_str}/{category}/{stem}.webp"


class LocalImageStore(ImageStore):
    """로컬 파일시스템 스토리지 (개발용)."""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or os.getenv("IMAGE_STORE_DIR", "stored_images"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, source_path: str, channel: str, category: str = "screenshot") -> str:
        if not os.path.exists(source_path):
            logger.warning(f"[image_store] 원본 파일 없음: {source_path}")
            return source_path

        # 매직 바이트로 실제 이미지인지 검증 (JS/HTML이 PNG 확장자로 저장된 경우 방지)
        if not _is_valid_image_file(source_path):
            logger.warning(
                f"[image_store] 유효하지 않은 이미지 파일 (JS/HTML 등): "
                f"{os.path.basename(source_path)}"
            )
            return source_path

        key = _generate_key(channel, category, os.path.basename(source_path))
        dest = self.base_dir / key
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            loop = asyncio.get_event_loop()
            webp_data = await loop.run_in_executor(None, _convert_to_webp, source_path)
            dest.write_bytes(webp_data)

            orig_size = os.path.getsize(source_path)
            new_size = len(webp_data)
            ratio = (1 - new_size / max(orig_size, 1)) * 100
            logger.debug(
                f"[image_store] WebP 변환: {os.path.basename(source_path)} "
                f"({orig_size:,}B -> {new_size:,}B, -{ratio:.0f}%)"
            )
            return str(dest)
        except Exception as e:
            logger.warning(f"[image_store] WebP 변환 실패, 원본 복사: {e}")
            # 원본 확장자 유지
            orig_ext = Path(source_path).suffix or ".png"
            fallback_dest = dest.with_suffix(orig_ext)
            shutil.copy2(source_path, fallback_dest)
            return str(fallback_dest)

    async def get_url(self, stored_path: str) -> str:
        return f"/images/{Path(stored_path).relative_to(self.base_dir)}"

    async def delete(self, stored_path: str) -> bool:
        try:
            Path(stored_path).unlink(missing_ok=True)
            return True
        except Exception:
            return False

    async def cleanup(self, older_than_days: int = 90) -> int:
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=older_than_days)
        deleted = 0
        for f in self.base_dir.rglob("*"):
            if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                deleted += 1

        # 빈 디렉토리 정리
        for d in sorted(self.base_dir.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()

        logger.info(f"[image_store] cleanup: {deleted}건 삭제 (>{older_than_days}일)")
        return deleted

    def __repr__(self):
        return f"LocalImageStore({self.base_dir})"


class S3ImageStore(ImageStore):
    """AWS S3 스토리지 (프로덕션용).

    환경변수:
        AWS_S3_BUCKET: S3 버킷명
        AWS_S3_PREFIX: 키 접두사 (기본: "adscope/images")
        AWS_S3_REGION: 리전 (기본: "ap-northeast-2")
    """

    def __init__(self):
        try:
            import boto3
        except ImportError:
            raise ImportError("S3 스토리지를 사용하려면 boto3를 설치하세요: pip install boto3")

        self.bucket = os.environ["AWS_S3_BUCKET"]
        self.prefix = os.getenv("AWS_S3_PREFIX", "adscope/images")
        self.region = os.getenv("AWS_S3_REGION", "ap-northeast-2")
        self.s3 = boto3.client("s3", region_name=self.region)

    async def save(self, source_path: str, channel: str, category: str = "screenshot") -> str:
        key = f"{self.prefix}/{_generate_key(channel, category, os.path.basename(source_path))}"

        try:
            webp_data = _convert_to_webp(source_path)
        except Exception:
            with open(source_path, "rb") as f:
                webp_data = f.read()
            key = key.replace(".webp", ".png")

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=webp_data,
            ContentType="image/webp" if key.endswith(".webp") else "image/png",
        )
        logger.debug(f"[image_store] S3 업로드: s3://{self.bucket}/{key}")
        return key

    async def get_url(self, stored_path: str) -> str:
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": stored_path},
            ExpiresIn=3600,
        )

    async def delete(self, stored_path: str) -> bool:
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=stored_path)
            return True
        except Exception:
            return False

    async def cleanup(self, older_than_days: int = 90) -> int:
        from datetime import timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        deleted = 0

        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                if obj["LastModified"].replace(tzinfo=timezone.utc) < cutoff:
                    self.s3.delete_object(Bucket=self.bucket, Key=obj["Key"])
                    deleted += 1

        logger.info(f"[image_store] S3 cleanup: {deleted}건 삭제 (>{older_than_days}일)")
        return deleted

    def __repr__(self):
        return f"S3ImageStore(s3://{self.bucket}/{self.prefix})"


def get_image_store() -> ImageStore:
    """환경변수 기반 이미지 스토리지 팩토리.

    IMAGE_STORE_TYPE:
        - "local" (기본): 로컬 파일시스템
        - "s3": AWS S3
    """
    store_type = os.getenv("IMAGE_STORE_TYPE", "local").lower()

    if store_type == "s3":
        return S3ImageStore()
    return LocalImageStore()
