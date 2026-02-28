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
  /** 아틀라스인 경우 좌표 정보, 아닌 경우 null */
  atlas: AtlasCoords | null;
  /** 아틀라스 여부 */
  isAtlas: boolean;
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

  let url: string;
  if (cleanPath.startsWith("stored_images/")) {
    url = "/images/" + cleanPath.slice("stored_images/".length);
  } else if (cleanPath.startsWith("screenshots/")) {
    url = "/" + cleanPath;
  } else {
    url = "/images/" + cleanPath;
  }

  return {
    url,
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

