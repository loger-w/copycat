import { useQuery } from "@tanstack/react-query";

import type { StockOverlay } from "@/lib/stock-intraday-svg";
import { isoLocalDate } from "@/lib/trading-calendar";

async function fetchIndexOverlay(): Promise<StockOverlay> {
  const res = await fetch("/api/index/overlay");
  if (!res.ok) throw new Error(`HTTP_${res.status}`);
  return (await res.json()) as StockOverlay;
}

/** 加權指數的 CDP / 日均線(決策 10)。形狀與 `/api/stock/overlay/{code}` 同,
 *  故直接重用 `StockOverlay` 型別 —— 另立一份同欄位的型別,兩邊漂掉時是靜默的。
 *
 *  **回復用的 60s 輪詢**:資料是「昨日以前的日 K 衍生量」,常態下一天只需一份
 *  (staleTime Infinity)。但兩種可回復的失效會讓首抓拿到空手 ——
 *  TC4 沒開(200 但三欄全 null)與 index engine 未就緒(503)。兩者都會在使用者
 *  什麼都不做的情況下自行恢復,沒有這道輪詢就得手動重新整理才看得到疊線。
 *
 *  **error 態必須查 `status` 不能查 `data`**:失敗時 `data` 是 undefined,
 *  只寫 `data != null && 全 null` 的條件會讓 503 那條路永遠不輪詢。
 *
 *  **這裡的 `false` 不是時段閘,W2 T3(#208)刻意不動**:四支輪詢 hook 盤外回 false 的病是「開盤前開著、
 *  開點不自醒」;本 hook 的 false 意思是「資料健康、今天不必再抓」,跨日由 queryKey 帶日期自然換
 *  (render 時重算),沒有「該醒卻沒醒」的時刻可言。改成距開點 ms 只會每天多打一發無意義的請求。 */
export function useIndexOverlay(enabled: boolean) {
  return useQuery({
    // 本機日界 = 台北(部署綁本機);跨日換 queryKey 自然失效(同 useStockOverlay)
    queryKey: ["index-overlay", isoLocalDate(new Date())],
    queryFn: fetchIndexOverlay,
    enabled,
    staleTime: Infinity,
    retry: 1,
    refetchInterval: (q) =>
      q.state.status === "error" ||
      (q.state.data != null &&
        q.state.data.cdp === null &&
        q.state.data.ma5 === null &&
        q.state.data.ma20 === null)
        ? 60_000
        : false,
  });
}
