"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { imageUrlCandidates } from "@/lib/image-utils";

interface CreativeImageProps {
  path: string | null | undefined;
  alt?: string;
  className?: string;
  fallback?: ReactNode;
}

export function CreativeImage({ path, alt = "ad creative", className = "", fallback }: CreativeImageProps) {
  const urls = useMemo(() => imageUrlCandidates(path), [path]);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    setIndex(0);
  }, [path]);

  if (!urls.length || index >= urls.length) {
    return fallback ? (
      <>{fallback}</>
    ) : (
      <div className="w-full h-full flex items-center justify-center bg-gray-100 text-gray-400 text-xs">
        이미지 없음
      </div>
    );
  }

  return (
    <img
      src={urls[index]}
      alt={alt}
      className={className}
      referrerPolicy="no-referrer"
      loading="lazy"
      onError={() => setIndex((value) => value + 1)}
    />
  );
}
