"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { useSSE } from "@/hooks/useSSE";

function SSEConnector() {
  useSSE();
  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30 * 1000,          // 30초 (이전 60초)
            refetchOnWindowFocus: true,     // 탭 복귀 시 자동 갱신
            refetchOnReconnect: true,       // 네트워크 복구 시 자동 갱신
            retry: 2,
            retryDelay: 1000,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <SSEConnector />
      {children}
    </QueryClientProvider>
  );
}
