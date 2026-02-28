"use client";

import { useEffect, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

/** SSE 이벤트 타입별 무효화할 React Query 키 매핑 */
const EVENT_QUERY_MAP: Record<string, string[][]> = {
  crawl_complete: [
    ["dailyStats"],
    ["dailyTrend"],
    ["topAdvertisers"],
    ["gallery"],
    ["spendSummary"],
  ],
  ai_enrich_done: [
    ["gallery"],
    ["dailyStats"],
  ],
  campaign_rebuilt: [
    ["spendSummary"],
    ["dailyStats"],
    ["topAdvertisers"],
  ],
  data_updated: [
    ["dailyStats"],
    ["dailyTrend"],
    ["gallery"],
    ["spendSummary"],
    ["topAdvertisers"],
  ],
};

interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

/**
 * SSE 스트림 구독 훅 — 이벤트 수신 시 관련 React Query 캐시를 자동 무효화.
 *
 * 사용법: Providers 내부에서 한 번만 호출
 *   useSSE();
 */
export function useSSE(onEvent?: (evt: SSEEvent) => void) {
  const queryClient = useQueryClient();
  const lastTsRef = useRef(0);
  const retryCountRef = useRef(0);
  const maxRetries = 10;

  const connect = useCallback(() => {
    if (typeof window === "undefined") return null;

    const url = `/api/events/stream?last_event_ts=${lastTsRef.current}`;
    const es = new EventSource(url);

    es.onopen = () => {
      retryCountRef.current = 0; // 연결 성공 시 재시도 카운트 리셋
    };

    // 각 이벤트 타입별 리스너 등록
    const eventTypes = Object.keys(EVENT_QUERY_MAP);
    for (const evtType of eventTypes) {
      es.addEventListener(evtType, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          const ts = data._ts || Date.now() / 1000;
          lastTsRef.current = ts;

          // 관련 쿼리 무효화
          const queryKeys = EVENT_QUERY_MAP[evtType];
          if (queryKeys) {
            for (const key of queryKeys) {
              queryClient.invalidateQueries({ queryKey: key });
            }
          }

          onEvent?.({ event: evtType, data });
        } catch {
          // JSON 파싱 실패 무시
        }
      });
    }

    // heartbeat은 무시 (연결 유지용)
    es.addEventListener("heartbeat", () => {
      // no-op: 연결 유지 확인
    });

    es.onerror = () => {
      es.close();

      // 지수 백오프 재연결 (최대 ~5분)
      if (retryCountRef.current < maxRetries) {
        const delay = Math.min(1000 * 2 ** retryCountRef.current, 300_000);
        retryCountRef.current += 1;
        setTimeout(() => connect(), delay);
      }
    };

    return es;
  }, [queryClient, onEvent]);

  useEffect(() => {
    const es = connect();
    return () => {
      es?.close();
    };
  }, [connect]);
}
