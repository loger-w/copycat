import { useQuery } from "@tanstack/react-query";

import type { Bar } from "@/lib/candle";

/** K 線資料(SC-7)。日 K 與分 K 的新鮮度策略不同:
 *  - `D`:當日內不過期(已完成日 bar 不會變);query key **不含 days**(D-15)。
 *  - `1`:交易時段每 60s 重取(D-9)。成本控制在後端 —— 歷史日走永久 memo,
 *    只有當日段會真的打 TC4(change-spec R2-2/R2-3)。 */

export type ChartMode = "intraday" | "m1" | "m5" | "day";

export const DAYS_STEP = 5;
export const DAYS_MAX = 30;
const POLL_MS = 60_000;

/** 台北交易時段(本機時區 = 台北,部署綁本機;含盤前試撮到收盤後緩衝)。 */
export function inTradingHours(now: Date = new Date()): boolean {
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= 8 * 60 + 45 && mins <= 13 * 60 + 35;
}

async function fetchBars(code: string, tf: string, days: number): Promise<Bar[]> {
  const qs = tf === "D" ? `tf=D` : `tf=1&days=${days}`;
  const res = await fetch(`/api/stock/bars/${code}?${qs}`);
  if (!res.ok) {
    let code_ = `HTTP_${res.status}`;
    try {
      const body = (await res.json()) as { detail?: { error?: string } };
      code_ = body.detail?.error ?? code_;
    } catch {
      /* 非 JSON body:保留 HTTP_ 前綴碼 */
    }
    throw new Error(code_);
  }
  return ((await res.json()) as { bars: Bar[] }).bars;
}

export function useStockBars(code: string | null, mode: ChartMode, days: number) {
  const isDaily = mode === "day";
  const enabled = code !== null && mode !== "intraday";
  const tf = isDaily ? "D" : "1";
  return useQuery({
    // tf=D 不含 days:忽略該參數卻進 key 會產生多份等價 cache(D-15)
    queryKey: isDaily ? ["stock-bars", code, "D"] : ["stock-bars", code, "1", days],
    queryFn: () => fetchBars(code as string, tf, days),
    enabled,
    retry: 1,
    staleTime: isDaily ? Infinity : 0,
    refetchInterval: !isDaily && enabled && inTradingHours() ? POLL_MS : false,
  });
}
