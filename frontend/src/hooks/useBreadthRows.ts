import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import { inTradingHours } from "@/lib/trading-hours";
import type { BreadthRowsState } from "@/types";

/** 漲跌停列表資料流(market-overview R3 SC-1;design §5.2)。
 *
 * **REST on-demand 不進 WS**(brainstorm Q2):payload 是全市場 ~2800 列 × 15 欄,
 * 掛上 `/ws/breadth` 等於所有開站的人都吃這份頻寬,而它只有列表展開時才有人看。
 * 消費端(`LimitListSection`)收合即 unmount,query 隨之消失 —— 頻寬跟著消費者走。
 *
 * `refetchInterval` 用**函式形式**(R10,`useMarketBars` 同慣例):TQ 每次 interval
 * 到期都重新求值,開盤 / 收盤的開關不依賴外部 re-render 才會生效。收盤後回 false
 * = 完全停輪詢(家數引擎自己也只在盤中窗取數,盤後輪詢只是白打)。
 *
 * `retry: 1` 而非預設的 3:這條路的失敗多半是後端引擎不在 / FinMind 掛了,
 * 重試三輪只是把「載入中」拖得更長。
 */

const POLL_MS = 10_000;

async function fetchBreadthRows(): Promise<BreadthRowsState> {
  const res = await fetch("/api/market/breadth/rows");
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as BreadthRowsState;
}

export function useBreadthRows() {
  return useQuery({
    queryKey: ["breadth-rows"],
    queryFn: fetchBreadthRows,
    retry: 1,
    refetchInterval: () => (inTradingHours() ? POLL_MS : false),
  });
}
