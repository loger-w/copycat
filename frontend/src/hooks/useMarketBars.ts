import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import type { Bar } from "@/lib/candle";
import { type MarketKey, type MarketMode, tfOf } from "@/lib/timeframe";
import { inFuturesTradingHours, inTradingHours } from "@/lib/trading-hours";

/** 大盤 K 線(index-board N-7)。
 *
 * 新鮮度策略沿用個股 K 線的兩檔(D-9/D-15):
 * - `D` / `W` / `M`:當日內不過期(已完成日 bar 不會變),query key **不含 days**
 * - `1`:交易時段每 60s 重取;成本控制在後端(歷史段永久 memo,只有當日段真打 TC4)
 *
 * 30/60/90 分與 2–10 分**共用同一份 `tf=1` 原料**,由前端 `aggregateBars` 聚合。
 */

export const MARKET_MINUTE_DAYS = 30;
const POLL_MS = 60_000;

export interface BarsMeta {
  source: string;
  coverage_from: string | null;
  coverage_to: string | null;
  partial_last: boolean;
  volume: boolean;
  refusal: string | null;
  synth_since: string | null;
}

export interface MarketBars {
  bars: Bar[];
  meta: BarsMeta;
}

async function fetchMarketBars(key: MarketKey, tf: string): Promise<MarketBars> {
  const qs = tf === "1" ? `tf=1&days=${MARKET_MINUTE_DAYS}` : `tf=${tf}`;
  const res = await fetch(`/api/market/bars/${key}?${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as MarketBars;
}

export function useMarketBars(key: MarketKey, mode: MarketMode) {
  const tf = tfOf(mode);
  const isMinute = tf === "1";
  // 期指日盤 08:45–13:45,個股那把尺會讓開盤前 15 分與 13:36–13:45 不自動更新(P2-5)
  const inHours = key === "TWSE" || key === "OTC" ? inTradingHours : inFuturesTradingHours;
  return useQuery({
    // 非分 K 不含 days:忽略的參數進 key 會產生多份等價 cache(D-15)
    queryKey: isMinute
      ? ["market-bars", key, "1", MARKET_MINUTE_DAYS]
      : ["market-bars", key, tf],
    queryFn: () => fetchMarketBars(key, tf as string),
    enabled: tf !== null,
    retry: 1,
    staleTime: isMinute ? 0 : Infinity,
    // 函式形式:TQ 每次 interval 到期都重新求值 → 開盤/收盤的開關不依賴外部 re-render
    refetchInterval: () => (isMinute && inHours() ? POLL_MS : false),
  });
}
