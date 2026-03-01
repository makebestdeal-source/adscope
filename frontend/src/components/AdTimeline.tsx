"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type AdSnapshot, type AdDetail } from "@/lib/api";
import { toImageUrl } from "@/lib/image-utils";

const CHANNEL_BADGE: Record<string, { label: string; color: string }> = {
  naver_search: { label: "네이버 검색", color: "bg-green-100 text-green-700" },
  naver_da: { label: "네이버 DA", color: "bg-emerald-100 text-emerald-700" },
  youtube_ads: { label: "유튜브 카탈로그", color: "bg-red-100 text-red-700" },
  youtube_surf: { label: "유튜브 접촉", color: "bg-red-50 text-red-600" },
  google_gdn: { label: "Google GDN", color: "bg-sky-100 text-sky-700" },
  kakao_da: { label: "카카오 DA", color: "bg-yellow-100 text-yellow-700" },
  meta: { label: "Meta", color: "bg-blue-100 text-blue-700" },
};

export function AdTimeline() {
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data: snapshots, isLoading } = useQuery({
    queryKey: ["recentSnapshots"],
    queryFn: () => api.getSnapshots({ limit: "20" }),
  });

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["snapshot", selectedId],
    queryFn: () => api.getSnapshot(selectedId!),
    enabled: selectedId !== null,
  });

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
      <h2 className="text-base font-semibold text-gray-900 mb-5">
        최근 수집 타임라인
      </h2>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex items-center justify-between py-2">
              <div className="flex items-center gap-3">
                <div className="skeleton h-5 w-16 rounded-full" />
                <div className="skeleton h-4 w-6" />
              </div>
              <div className="flex items-center gap-4">
                <div className="skeleton h-4 w-16" />
                <div className="skeleton h-3 w-20" />
              </div>
            </div>
          ))}
        </div>
      ) : snapshots && snapshots.length > 0 ? (
        <div className="space-y-0">
          {snapshots.map((snap) => (
            <div key={snap.id}>
              <SnapshotRow
                snapshot={snap}
                isSelected={snap.id === selectedId}
                onClick={() =>
                  setSelectedId(snap.id === selectedId ? null : snap.id)
                }
              />
              {snap.id === selectedId && (
                <SnapshotDetail
                  snapshot={snap}
                  detail={detail}
                  isLoading={detailLoading}
                />
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-8 text-gray-400">
          <p className="text-sm">수집된 스냅샷이 없습니다</p>
        </div>
      )}
    </div>
  );
}

function SnapshotRow({
  snapshot,
  isSelected,
  onClick,
}: {
  snapshot: AdSnapshot;
  isSelected: boolean;
  onClick: () => void;
}) {
  const badge = CHANNEL_BADGE[snapshot.channel] ?? {
    label: snapshot.channel,
    color: "bg-gray-100 text-gray-700",
  };

  const time = new Date(snapshot.captured_at).toLocaleString("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  const thumbUrl = toImageUrl(snapshot.screenshot_path);

  return (
    <div
      className={`flex items-center gap-3 py-2 border-b border-gray-50 last:border-0 cursor-pointer hover:bg-gray-50 rounded px-2 transition-colors ${
        isSelected ? "bg-adscope-50 ring-1 ring-adscope-200" : ""
      }`}
      onClick={onClick}
    >
      <ThumbImage url={thumbUrl} alt="캡처" size="w-12 h-12" />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-0.5 rounded text-xs font-medium ${badge.color}`}
          >
            {badge.label}
          </span>
          <span className="text-xs text-gray-500">
            {snapshot.device === "mobile" ? "M" : "PC"}
          </span>
        </div>
        <div className="flex items-center gap-3 mt-0.5">
          <span className="text-sm font-medium text-gray-900">
            광고 {snapshot.ad_count}건
          </span>
          <span className="text-xs text-gray-400">{time}</span>
        </div>
      </div>

      <span className="text-gray-300 text-sm flex-shrink-0">
        {isSelected ? "▲" : "▼"}
      </span>
    </div>
  );
}

function SnapshotDetail({
  snapshot,
  detail,
  isLoading,
}: {
  snapshot: AdSnapshot;
  detail: (AdSnapshot & { details: AdDetail[] }) | undefined;
  isLoading: boolean;
}) {
  const snapshotImgUrl = toImageUrl(snapshot.screenshot_path);

  if (isLoading) {
    return (
      <div className="px-2 py-4 border-b border-gray-100">
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span className="animate-spin">&#x27F3;</span> 로딩 중...
        </div>
      </div>
    );
  }

  const ads = detail?.details ?? [];

  return (
    <div className="px-2 py-3 border-b border-gray-100 bg-gray-50/50">
      {/* 전체 페이지 스크린샷 */}
      {snapshotImgUrl && (
        <div className="mb-3">
          <p className="text-xs font-medium text-gray-500 mb-1">
            페이지 캡처
          </p>
          <img
            src={snapshotImgUrl}
            alt="페이지 캡처"
            className="w-full max-h-64 object-contain rounded border border-gray-200 bg-white"
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={(e) => {
              (e.currentTarget.parentElement as HTMLElement).style.display = "none";
            }}
          />
        </div>
      )}

      {/* 광고 목록 */}
      {ads.length > 0 ? (
        <div>
          <p className="text-xs font-medium text-gray-500 mb-2">
            광고 상세 ({ads.length}건)
          </p>
          <div className="space-y-2 max-h-[500px] overflow-y-auto">
            {ads.map((ad: AdDetail) => (
              <AdRow key={ad.id} ad={ad} />
            ))}
          </div>
        </div>
      ) : !snapshotImgUrl ? (
        <p className="text-xs text-gray-400 py-2">수집된 데이터 없음</p>
      ) : null}
    </div>
  );
}

function AdRow({ ad }: { ad: AdDetail }) {
  const imgUrl = toImageUrl(ad.creative_image_path);
  const ssUrl = toImageUrl(ad.screenshot_path);
  const displayImg = imgUrl || ssUrl;

  return (
    <div className="flex gap-3 p-2 bg-white rounded-lg border border-gray-100">
      {/* 이미지 영역 */}
      <ThumbImage url={displayImg} alt={ad.advertiser_name_raw || "광고"} size="w-20 h-20" />

      {/* 텍스트 정보 */}
      <div className="flex-1 min-w-0 space-y-0.5">
        {/* 광고주 이름 */}
        <p className="text-xs font-semibold text-gray-900 truncate">
          {ad.advertiser_name_raw || "광고주 미상"}
        </p>

        {/* 광고 문구 */}
        {ad.ad_text && (
          <p className="text-xs text-gray-700 line-clamp-2">{ad.ad_text}</p>
        )}

        {/* 광고 설명 */}
        {ad.ad_description && (
          <p className="text-xs text-gray-500 line-clamp-1">
            {ad.ad_description}
          </p>
        )}

        {/* 하단 메타 정보 */}
        <div className="flex items-center gap-2 flex-wrap pt-0.5">
          {ad.ad_type && (
            <span className="text-[10px] px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">
              {ad.ad_type}
            </span>
          )}
          {ad.position && (
            <span className="text-[10px] text-gray-400">
              #{ad.position}
            </span>
          )}
          {ad.verification_status && (
            <span className="text-[10px] px-1.5 py-0.5 bg-green-50 text-green-600 rounded">
              {ad.verification_status}
            </span>
          )}
        </div>

        {/* URL */}
        {(ad.url || ad.display_url) && (
          <p className="text-[10px] text-blue-500 truncate">
            {ad.display_url || ad.url}
          </p>
        )}
      </div>
    </div>
  );
}

/** 이미지 썸네일 (onError 시 아이콘 플레이스홀더로 대체) */
function ThumbImage({
  url,
  alt,
  size,
}: {
  url: string | null;
  alt: string;
  size: string;
}) {
  const [imgError, setImgError] = useState(false);
  const showImg = url && !imgError;

  return showImg ? (
    <img
      src={url}
      alt={alt}
      className={`${size} rounded object-cover border border-gray-200 flex-shrink-0`}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setImgError(true)}
    />
  ) : (
    <div className={`${size} rounded bg-gray-100 flex items-center justify-center flex-shrink-0`}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5 text-gray-300">
        <path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}
