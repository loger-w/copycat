import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";

/**
 * QueryClientProvider 包裝過的 render:每次呼叫給一個全新、關掉 retry 的 client。
 *
 * 全新是重點 —— 共用 client 會讓上一個 it 的 query cache 洩到下一個;retry 關掉則是
 * 錯誤路徑測試不必等重試退避。個股頁五個元件測試各抄一份逐字相同的定義,任何一處
 * 想調 defaultOptions 都會變成「這檔的 wrap 跟別檔不一樣」。
 */
export function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
