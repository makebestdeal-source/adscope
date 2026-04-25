"""모바일 스크린샷 → 광고 영역 감지 + OCR 텍스트 추출.

전략:
  1. 전체 화면 EasyOCR (bounding box 포함) → "AD" / "광고" 레이블 위치 탐지
  2. 레이블 주변 Y 범위 내 텍스트를 하나의 광고 카드로 묶음
  3. 네이버 DA 배너: 고정 위치 crop (상단 140~400px)

의존: opencv-python, easyocr, Pillow
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np
from loguru import logger
from PIL import Image

try:
    import easyocr
    _EASYOCR_OK = True
except ImportError:
    _EASYOCR_OK = False
    logger.warning("easyocr 미설치 — pip install easyocr")

# ── 광고 레이블 패턴 ──────────────────────────────────────────────
_AD_LABEL = re.compile(r"^(AD|광고|스폰서|Sponsored)$", re.I)
_AD_CONTEXT = re.compile(r"광\s*고|[Aa][Dd]\b|스폰서|[Ss]ponsored|파워링크|비즈보드")

_BRAND_SUFFIX = re.compile(r"(주식회사|㈜|\(주\)|corp\.?|inc\.?|co\.?ltd?)$", re.I)

# 카드 그룹핑 Y 반경 (픽셀)
_CARD_Y_RADIUS = 400

_reader: Optional["easyocr.Reader"] = None


def _get_reader() -> "easyocr.Reader":
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
    return _reader


def _bbox_center(bbox) -> tuple[float, float]:
    """EasyOCR bbox [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] → (cx, cy)"""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return sum(xs) / 4, sum(ys) / 4


class MobileAdDetector:
    """스크린샷에서 광고 소재를 감지하고 브랜드/카피를 추출합니다."""

    def __init__(self, use_ocr: bool = True):
        self.use_ocr = use_ocr and _EASYOCR_OK

    # ── 공개 API ────────────────────────────────────────────────

    def analyze(self, image_path: Path, crop: Optional[tuple] = None) -> list[dict]:
        """
        이미지 분석 → 광고 소재 목록.
        반환: [{"brand", "copy", "full_text", "is_ad", "region", "confidence"}]
        """
        img = Image.open(image_path).convert("RGB")
        offset_x, offset_y = 0, 0
        if crop:
            x0, y0, x1, y1 = crop
            img = img.crop((x0, y0, x1, y1))
            offset_x, offset_y = x0, y0

        results = []

        if not self.use_ocr:
            return results

        # 전체 화면 OCR (bounding box 포함)
        ocr_items = self._full_ocr(img)  # [(bbox, text, conf)]

        # 1. AD/광고 레이블 위치 기반 카드 추출
        ad_cards = self._extract_ad_cards(ocr_items, img.size)
        results.extend(ad_cards)

        # 2. 레이블 없어도 컨텍스트상 광고인 텍스트 보완
        if not results:
            all_text = " ".join(t for _, t, _ in ocr_items)
            if _AD_CONTEXT.search(all_text):
                brand = self._pick_brand(ocr_items)
                copy = self._pick_copy(ocr_items)
                results.append({
                    "brand": brand,
                    "copy": copy,
                    "full_text": all_text[:400],
                    "is_ad": True,
                    "region": (offset_x, offset_y,
                               offset_x + img.size[0], offset_y + img.size[1]),
                    "confidence": 0.6,
                })

        # offset 보정
        for r in results:
            if r.get("region"):
                rx0, ry0, rx1, ry1 = r["region"]
                r["region"] = (rx0 + offset_x, ry0 + offset_y,
                               rx1 + offset_x, ry1 + offset_y)

        return results

    def analyze_naver_banner(self, image_path: Path) -> list[dict]:
        """네이버 DA 상단 배너 전용: 고정 위치 crop.

        네이버 앱 레이아웃 (1080x2220 기준):
          - 상태바+네이버 로고: 0~430px
          - DA 배너 영역:      430~930px (약 19~42%)
          - 날씨 위젯:         930px~

        배너에는 'AD' 레이블이 없으므로 OCR 텍스트를 직접 파싱합니다.
        """
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        y_start = int(h * 0.19)
        y_end = int(h * 0.42)
        crop = img.crop((0, y_start, w, y_end))

        items = self._full_ocr(crop)
        if not items:
            return []

        # 신뢰도 0.3 이상 텍스트만 사용
        filtered = [(b, t, c) for b, t, c in items if c >= 0.3 and len(t.strip()) >= 2]
        if not filtered:
            return []

        all_texts = [t for _, t, _ in filtered]
        full_text = " ".join(all_texts)

        # 브랜드: 한글/영문 포함, 가장 짧고 신뢰도 높은 텍스트
        brand_candidates = [
            (c, len(t), t.strip()) for _, t, c in filtered
            if re.search(r"[가-힣A-Za-z]", t)
            and 2 <= len(t.strip()) <= 20
        ]
        brand_candidates.sort(key=lambda x: (-x[0], x[1]))  # 신뢰도↓, 길이↑
        brand = _BRAND_SUFFIX.sub("", brand_candidates[0][2]).strip() if brand_candidates else ""

        # 카피: 신뢰도 0.5 이상 텍스트 중 가장 긴 것
        copy_candidates = [t for _, t, c in filtered if c >= 0.5]
        copy = max(copy_candidates, key=len) if copy_candidates else ""

        return [{
            "brand": brand,
            "copy": copy,
            "full_text": full_text[:400],
            "is_ad": True,
            "region": (0, y_start, w, y_end),
            "confidence": 0.75,
        }]

    # ── 내부 ────────────────────────────────────────────────────

    def _full_ocr(self, img: Image.Image) -> list:
        """EasyOCR detail=1 전체 화면 인식."""
        try:
            arr = np.array(img)
            reader = _get_reader()
            return reader.readtext(arr, detail=1)
        except Exception as e:
            logger.debug(f"OCR 실패: {e}")
            return []

    def _extract_ad_cards(self, items: list, img_size: tuple) -> list[dict]:
        """AD/광고 레이블이 있는 카드 영역 추출."""
        w, h = img_size
        cards = []

        for bbox, text, conf in items:
            text_stripped = text.strip()
            if not _AD_LABEL.match(text_stripped):
                continue

            label_cx, label_cy = _bbox_center(bbox)

            # 같은 카드 내 텍스트 (Y 범위 내)
            card_items = [
                (b, t, c) for b, t, c in items
                if abs(_bbox_center(b)[1] - label_cy) <= _CARD_Y_RADIUS
                and not _AD_LABEL.match(t.strip())
            ]

            # 브랜드: AD 레이블과 같은 줄 (Y 차이 50px 이내) 텍스트를 합쳐서 사용
            same_row = sorted(
                [(b, t, c) for b, t, c in card_items
                 if abs(_bbox_center(b)[1] - label_cy) <= 50],
                key=lambda x: _bbox_center(x[0])[0]  # X 순 정렬
            )
            if same_row:
                # 같은 줄 텍스트를 X 순서로 이어붙임 → 브랜드명 복원
                brand_raw = " ".join(t for _, t, _ in same_row).strip()
                brand = _BRAND_SUFFIX.sub("", brand_raw).strip()
            else:
                brand = self._pick_brand(card_items)

            all_texts = [t for _, t, _ in card_items]
            full_text = " ".join(all_texts)
            copy = self._pick_copy(card_items)

            # 카드 bounding box
            all_bboxes = [b for b, _, _ in card_items]
            if all_bboxes:
                all_xs = [p[0] for bb in all_bboxes for p in bb]
                all_ys = [p[1] for bb in all_bboxes for p in bb]
                region = (max(0, int(min(all_xs))),
                          max(0, int(min(all_ys))),
                          min(w, int(max(all_xs))),
                          min(h, int(max(all_ys))))
            else:
                region = (0, int(cy - _CARD_Y_RADIUS), w, int(cy + _CARD_Y_RADIUS))

            cards.append({
                "brand": brand,
                "copy": copy,
                "full_text": full_text[:400],
                "is_ad": True,
                "region": region,
                "confidence": 0.9,
            })

        return cards

    def _pick_brand(self, items: list) -> str:
        """가장 짧고 의미 있는 텍스트를 브랜드명으로."""
        candidates = []
        for _, text, conf in items:
            t = text.strip()
            if len(t) < 2 or len(t) > 30:
                continue
            if _AD_LABEL.match(t):
                continue
            if re.search(r"[가-힣A-Za-z]", t):
                t = _BRAND_SUFFIX.sub("", t).strip()
                candidates.append((len(t), conf, t))
        if not candidates:
            return ""
        # 짧고 신뢰도 높은 것
        candidates.sort(key=lambda x: (x[0], -x[1]))
        return candidates[0][2]

    def _pick_copy(self, items: list) -> str:
        """가장 긴 텍스트를 광고 카피로."""
        texts = [t.strip() for _, t, _ in items if t.strip() and not _AD_LABEL.match(t.strip())]
        if not texts:
            return ""
        return max(texts, key=len)
