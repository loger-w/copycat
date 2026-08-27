import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import type { FutChartMode } from "@/lib/fut-chart-mode";
import type { MarketKey } from "@/lib/timeframe";
import { inFuturesAllDayHours } from "@/lib/trading-hours";
import type { MarketBars } from "@/hooks/useMarketBars";

/** 期貨 tab 的 K 線資料源(futures-allday SC-1/2/3;design §4.1)。
 *
 * 與 `useMarketBars` 刻意分成兩支:
 * - 後端 `session=allday`(近全時段分鐘域)只有期指鍵吃得下,大盤 tab 的 `TXF`(day)
 *   與這裡的 `TXF:allday` 是**兩份後端 cache**(D10 記錄的取捨:同 symbol 歷史抓兩遍,
 *   換取大盤頁零改動)。
 * - 輪詢窗是近全時段(`inFuturesAllDayHours`),日盤那把尺會讓夜盤整段不自動更新。
 *
 * **分時與分 K 共用同一份 `tf=1` 原料**(分時圖的幾何在 `lib/allday.ts`,聚合在
 * `lib/candle.ts`)—— 一份原料餵所有分鐘級模式,切模式不重打。
 */

/** 分 K 取數天數。**5 不是 30**:近全時段一天 1140 根,30 日窗會是 34,000 根 ≈ 3 MB
 *  JSON 且冷啟動要 TC4 收割同量級的列(D10 payload 預算)。 */
export const FUTURES_MINUTE_DAYS = 5;

const POLL_MS = 60_000;
const SESSION = "allday";

/** 支援 `session=allday` 的標的 = 期指三兄弟。取自 `MarketKey` 而不是另寫一份 union:
 *  後端 `MARKET_KEYS` 是同一份值域,兩處各留一份必漂移。 */
export type FuturesBarsKey = Extract<MarketKey, "TXF" | "MXF" | "TMF">;

async function fetchFuturesBars(key: FuturesBarsKey, tf: "1" | "D"): Promise<MarketBars> {
  const qs =
    tf === "1" ? `tf=1&days=${FUTURES_MINUTE_DAYS}&session=${SESSION}` : `tf=${tf}`;
  const res = await fetch(`/api/market/bars/${key}?${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as MarketBars;
}

/** 空態 / 壞態由**消費端**判(`data.meta.source === "unavailable"` → 圖表區印進行式
 *  文案)—— hook 只負責把後端講的話原樣帶回來,不在這裡把降級翻譯成 error。 */
/** @param active 使用者是否正看著期貨 tab。期貨 tab 的 DOM 由 App 以 `hidden` 保留
 *  (不 unmount),沒有這道 gate 的話輪詢會在背景整晚跑(review LF-2)。
 *
 *  **只停 `refetchInterval`,不關 `enabled`**:輪詢是這支 query 唯一的背景請求來源,
 *  停掉即達成目的;而 `enabled: false` 會讓切回 tab 時 query 退回 pending 態 →
 *  圖表閃一次「載入中」而不是留著舊圖等新料(`staleTime: 0` 本來就會立刻重抓)。
 *
 *  預設 `true`:獨立使用與既有呼叫路徑不因這道 gate 靜默停更(同 FuturesLadder 的
 *  `qtyState` 慣例)。 */
/** @param enabled **是否要這份資料**(與 `active` 不同尺:`active` 只管輪詢節奏)。預設 true。
 *  個股頁的台指期疊線(feat/txf-intraday-overlay)在鈕關著時傳 false —— 那是「沒人要看」,
 *  不是「先抓著等人看」:`enabled: false` 才擋得住掛載即抓與 `refetchOnWindowFocus`,只停
 *  `refetchInterval` 擋不住。期貨 tab 自己不傳(理由見上:切回不閃 pending)。 */
export function useFuturesBars(
  key: FuturesBarsKey,
  mode: FutChartMode,
  active = true,
  enabled = true,
) {
  const isMinute = mode !== "day";
  const tf: "1" | "D" = isMinute ? "1" : "D";
  return useQuery({
    // 日 K 不含 days / session:忽略的參數進 key 會產生多份等價 cache(D-15)
    queryKey: isMinute
      ? ["futures-bars", key, "1", FUTURES_MINUTE_DAYS, SESSION]
      : ["futures-bars", key, "D"],
    queryFn: () => fetchFuturesBars(key, tf),
    enabled,
    retry: 1,
    staleTime: isMinute ? 0 : Infinity,
    // 函式形式:TQ 每次 interval 到期都重新求值 → 日盤收 / 夜盤開的開關不依賴外部 re-render
    refetchInterval: () => (active && isMinute && inFuturesAllDayHours() ? POLL_MS : false),
  });
}
