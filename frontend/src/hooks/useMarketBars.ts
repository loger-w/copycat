import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import type { Bar } from "@/lib/candle";
import { dayBarsRefetchInterval, dayBarsStaleTime } from "@/lib/day-bars-rollover";
import { type MarketKey, type MarketMode, tfOf } from "@/lib/timeframe";
import { inFuturesTradingHours, inTradingHours } from "@/lib/trading-hours";

/** 大盤 K 線(index-board N-7)。
 *
 * 新鮮度策略沿用個股 K 線的兩檔(D-9/D-15):
 * - `D` / `W` / `M`:**同一個本機日曆日內**不過期(已完成日 bar 不會變),query key **不含 days**。
 *   界 = 日曆午夜 + slack,與期指日 K 同一把尺 —— 症狀與由來見 `lib/day-bars-rollover.ts::msUntilDayRollover`
 *   (bug/daily-bars-siblings-rollover)。當週 / 當月那根每個交易日都會變,W / M 與 D 同一條分支。
 * - `1`:交易時段每 60s 重取;成本控制在後端(歷史段永久 memo,只有當日段真打 TC4)
 *
 * 30/60/90 分與 2–10 分**共用同一份 `tf=1` 原料**,由前端 `aggregateBars` 聚合。
 */

export const MARKET_MINUTE_DAYS = 30;
const POLL_MS = 60_000;

/** 這一趟取數的結果(N104;後端 `copycat/live/stock_source.py::BarsStatus`)。
 *
 *  與 `BarsMeta.source` 是**兩把不同的尺**:`source` 答「這份 bar 從哪來」,
 *  `status` 答「這一趟問到了沒」。同為字串,不可互換。 */
export type BarsStatus = "ok" | "timeout" | "disconnected";

export interface BarsMeta {
  source: string;
  coverage_from: string | null;
  coverage_to: string | null;
  partial_last: boolean;
  volume: boolean;
  refusal: string | null;
  synth_since: string | null;
  /** **optional**:後端 2026-08-25 才 additive 加上,且目前只有期指分 K 那條路會給出
   *  非 `"ok"` 的值(加權 / 櫃買 / 日週月 K 的來源層沒有三態訊號)。讀取端遇 undefined
   *  一律退回改動前的單一空態文案。 */
  status?: BarsStatus;
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

/** @param active 使用者是否正看著這張圖所在的 tab。**預設 true**(保守:既有呼叫路徑
 *  不因為新參數而靜默停更)。**只作用於分 K**:日 / 週 / 月 K 的午夜重抓與失敗重試整段不吃
 *  這道閘(理由見 `refetchInterval` 內註;pr-159-review F-05)。分 K 那條路在當日段每次都真走
 *  TC4 SubHistory,與 REALTIME 搶同一把 `api.lock` —— tab 切走後還每 60 秒打一發是看不見的
 *  成本(review round-2 XR-4;`FuturesPage` / `LimitListSection` 同慣例)。 */
export function useMarketBars(key: MarketKey, mode: MarketMode, active = true) {
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
    // 日 / 週 / 月 K 的新鮮度政策整組在 `lib/day-bars-rollover.ts`(三支日 K hook 同動,改政策只改那裡)
    staleTime: isMinute ? 0 : dayBarsStaleTime,
    // 函式形式:TQ 每次 interval 到期**與每次 render** 都重新求值 → 開盤/收盤的開關、日 K 的下一個
    // 午夜都不依賴外部 re-render;回值一變 TQ 就重排計時器,所以日 K 那條回整秒值。
    refetchInterval: (q) => {
      if (!isMinute) {
        // 日 / 週 / 月 K 這條**整段不吃 `active`**(與 `useFuturesBars` 的 `subscribed: active` 形狀
        // 不同,知情):台股綜合 tab 是 hidden 保留不 unmount,人在個股頁跨過午夜、早上切回時 K 線
        // 必須已是今天的 —— 切回那次 render 重算 interval 只會排到「下一個」午夜,拿不到「立刻打」。
        // 午夜那發一天一次、每把 key 一發;失敗後的 60 s 重試也不閘(否則午夜失敗恰發生在人不在時,
        // 就整晚凍結、切回還得再等 60 s),且 error 只在 HTTP 非 2xx(量級見 lib 的
        // `DAY_ERROR_RETRY_MS` doc),都不是 XR-4 擋的那種每 60 s 打 TC4 SubHistory 的成本。
        return dayBarsRefetchInterval(q);
      }
      return active && inHours() ? POLL_MS : false;
    },
  });
}
