import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "@/App";
import "@/index.css";
import { installUserTimingGuard } from "@/lib/dev-perf-guard";
import { createQueryClient } from "@/lib/query-client";

// dev-only:React dev build 每次 re-render 留下的 performance.measure 條目無上限累積
// (1.1 MB/s → 數小時後 renderer Aw Snap),條目數到閾值就清(observer 驅動,背景分頁不受 timer 節流)。production build 不裝。
if (import.meta.env.DEV) {
  const disposeGuard = installUserTimingGuard({ maxEntries: 5_000 });
  import.meta.hot?.dispose(disposeGuard);
}

// 送單 mutation 的 networkMode 等全站預設在 `lib/query-client.ts`(#237),這裡不另設
const queryClient = createQueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
