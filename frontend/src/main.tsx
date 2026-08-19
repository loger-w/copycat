import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "@/App";
import "@/index.css";
import { installUserTimingGuard } from "@/lib/dev-perf-guard";

// dev-only:React dev build 每次 re-render 留下的 performance.measure 條目無上限累積
// (1.1 MB/s → 數小時後 renderer Aw Snap),定期清掉。production build 不裝。
if (import.meta.env.DEV) installUserTimingGuard({ intervalMs: 10_000 });

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
