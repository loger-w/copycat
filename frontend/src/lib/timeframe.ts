/** 大盤頁的標的 × 週期值域(index-board SC-2/SC-3)。
 *
 * **刻意與個股的 `ChartMode` 分開**:個股的模式列是由 `ChartMode` 驅動的,把 30/60/90
 * 分與週/月塞進同一個 union,個股頁會憑空長出按鈕(白名單 W-1「個股頁零改動」)。
 */

/** 大盤標的鍵;與後端 `/api/market/bars/{key}` 的 `MARKET_KEYS` 同值域。 */
export type MarketKey = "TWSE" | "OTC" | "TXF" | "MXF" | "TMF";

export const FUT_KEYS = ["TXF", "MXF", "TMF"] as const satisfies readonly MarketKey[];

export type MarketMode =
  | "intraday"
  | "m1" | "m2" | "m3" | "m4" | "m5"
  | "m6" | "m7" | "m8" | "m9" | "m10"
  | "m30" | "m60" | "m90"
  | "day" | "week" | "month";

/** 週期鈕列(SC-3 的順序與標籤;單一 source of truth)。 */
export const MARKET_MODES: readonly (readonly [MarketMode, string])[] = [
  ["intraday", "分時"],
  ["m1", "1分"], ["m2", "2分"], ["m3", "3分"], ["m4", "4分"], ["m5", "5分"],
  ["m6", "6分"], ["m7", "7分"], ["m8", "8分"], ["m9", "9分"], ["m10", "10分"],
  ["m30", "30分"], ["m60", "60分"], ["m90", "90分"],
  ["day", "日K"], ["week", "週K"], ["month", "月K"],
] as const;

const DAILY_MODES = new Set<MarketMode>(["day", "week", "month"]);

/** `m30` → 30;非分 K 回 1(不聚合)。 */
export function marketMinutesOf(mode: MarketMode): number {
  if (!mode.startsWith("m")) return 1;
  const n = Number(mode.slice(1));
  return Number.isFinite(n) && n >= 1 ? n : 1;
}

/** 模式 → 後端 `tf`;`intraday` 不打 bars API(走 index state 的即時分鐘序列)→ `null`。 */
export function tfOf(mode: MarketMode): "1" | "D" | "W" | "M" | null {
  if (mode === "intraday") return null;
  if (mode === "day") return "D";
  if (mode === "week") return "W";
  if (mode === "month") return "M";
  return "1";
}

/** 該標的是否支援此模式。
 *
 * - 櫃買:達錢 4 沒有這個 symbol → **沒有任何歷史來源**,日/週/月不可能有
 *   (分 K 是本機由 MIS 5 秒快照合成的當日資料)
 * - 期指:分時走勢需要即時分鐘序列,那條管線目前只餵加權 / 櫃買 → 期指用 1 分 K 代替
 */
export function isModeAvailable(key: MarketKey, mode: MarketMode): boolean {
  if (key === "OTC") return !DAILY_MODES.has(mode);
  if (key === "TWSE") return true;
  return mode !== "intraday";
}

/** 每個標的的預設模式。切標的與初始化都經過 `coerceMode`,兩處必須是同一支
 *  —— 各判各的會出現「落回一個 disabled 的模式」這種停在空白畫面的組合(review P1-5)。 */
export function defaultMode(key: MarketKey): MarketMode {
  return key === "TXF" || key === "MXF" || key === "TMF" ? "m1" : "intraday";
}

/** 把 (標的, 模式) 夾到合法組合;已合法則原樣回。 */
export function coerceMode(key: MarketKey, mode: MarketMode): MarketMode {
  return isModeAvailable(key, mode) ? mode : defaultMode(key);
}

export function isMarketKey(v: string | null): v is MarketKey {
  return v === "TWSE" || v === "OTC" || v === "TXF" || v === "MXF" || v === "TMF";
}

export function isMarketMode(v: string | null): v is MarketMode {
  return MARKET_MODES.some(([id]) => id === v);
}
