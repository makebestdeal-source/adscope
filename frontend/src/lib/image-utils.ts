/**
 * AdScope 이미지 유틸리티 -- 아틀라스(스프라이트시트) 지원.
 *
 * creative_image_path 형식:
 *   일반: "stored_images/facebook/20260220/element/meta_card_0.webp"
 *   아틀라스: "stored_images/facebook/20260220/element/atlas_element_0.webp#0,0,200,150"
 *
 * 아틀라스 경로에는 '#' 뒤에 x,y,w,h 좌표가 붙음.
 */

export interface AtlasCoords {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ParsedImagePath {
  /** 서버에서 접근 가능한 이미지 URL */
  url: string;
  candidates: string[];
  /** 아틀라스인 경우 좌표 정보, 아닌 경우 null */
  atlas: AtlasCoords | null;
  /** 아틀라스 여부 */
  isAtlas: boolean;
}

function encodePath(path: string): string {
  return path.split("/").map((part) => encodeURIComponent(part)).join("/");
}

/** Unicode replacement char (U+FFFD): DB에서 한글 파일명이 깨져 저장될 때 나타남 */
const REPLACEMENT_CHAR_CODE = 0xfffd;

function hasCorruptedChars(s: string): boolean {
  for (let i = 0; i < s.length; i++) {
    if (s.charCodeAt(i) === REPLACEMENT_CHAR_CODE) return true;
  }
  return false;
}

export function imageUrlCandidates(path: string | null | undefined): string[] {
  if (!path) return [];

  const normalized = path.replace(/\\/g, "/");
  const cleanPath = normalized.split("#", 1)[0].replace(/^\/+/, "");
  const r2Base = process.env.NEXT_PUBLIC_IMAGE_BASE_URL || "https://pub-212e20fe661343f2816c81f3ebc9b26b.r2.dev";
  const urls: string[] = [];

  if (cleanPath.startsWith("http://") || cleanPath.startsWith("https://")) {
    urls.push(cleanPath);
  } else if (cleanPath.startsWith("stored_images/")) {
    const inner = cleanPath.slice("stored_images/".length);
    const corrupted = hasCorruptedChars(inner);
    if (!corrupted) {
      // 정상 경로: R2 우선, 백엔드 fallback
      if (r2Base) urls.push(`${r2Base.replace(/\/$/, "")}/${encodePath(inner)}`);
      urls.push(`/images/${encodePath(inner)}`);
    } else {
      // 한글 파일명 깨짐: 백엔드 우선(Railway 볼륨), R2는 마지막 시도
      urls.push(`/images/${encodePath(inner)}`);
      if (r2Base) urls.push(`${r2Base.replace(/\/$/, "")}/${encodePath(inner)}`);
    }
  } else if (cleanPath.startsWith("images/") || cleanPath.startsWith("screenshots/")) {
    urls.push(`/${encodePath(cleanPath)}`);
  } else {
    if (r2Base) urls.push(`${r2Base.replace(/\/$/, "")}/${encodePath(cleanPath)}`);
    urls.push(`/images/${encodePath(cleanPath)}`);
  }

  return Array.from(new Set(urls));
}

/**
 * creative_image_path를 파싱하여 URL과 아틀라스 좌표를 반환.
 */
export function parseImagePath(path: string | null | undefined): ParsedImagePath | null {
  if (!path) return null;

  const normalized = path.replace(/\\/g, "/");
  let atlasCoords: AtlasCoords | null = null;
  let cleanPath = normalized;

  // '#' 뒤에 좌표가 있으면 아틀라스
  const hashIdx = normalized.indexOf("#");
  if (hashIdx !== -1) {
    cleanPath = normalized.slice(0, hashIdx);
    const coordStr = normalized.slice(hashIdx + 1);
    const parts = coordStr.split(",").map(Number);
    if (parts.length === 4 && parts.every((n) => !isNaN(n))) {
      atlasCoords = { x: parts[0], y: parts[1], w: parts[2], h: parts[3] };
    }
  }

  const candidates = imageUrlCandidates(cleanPath);

  return {
    url: candidates[0] ?? "",
    candidates,
    atlas: atlasCoords,
    isAtlas: atlasCoords !== null,
  };
}

/**
 * 기존 toImageUrl과 동일한 인터페이스 (하위 호환).
 * 아틀라스 경로인 경우에도 이미지 URL만 반환 (좌표 무시).
 */
export function toImageUrl(path: string | null | undefined): string | null {
  const parsed = parseImagePath(path);
  return parsed?.url ?? null;
}

