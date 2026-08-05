/** 期貨 tab 的圖表模式值域(SC-2;design §4.4)。
 *
 * **刻意不共用 `lib/timeframe.ts`** —— 那是大盤頁專用,動它的 union 會讓大盤頁長出
 * 一排用不到的按鈕(W-1 同型教訓)。期貨的檔位(1/5/15/30/60)也與個股(1–10 連續)
 * 不同,兩邊各自定義比硬湊一個超集清楚。
 */

import { FUT_CHART_MODE_KEY } from "@/lib/constants";

export type FutChartMode = "intraday" | "m1" | "m5" | "m15" | "m30" | "m60" | "day";

/** 模式列(值 + 繁中標籤);**渲染順序與值域的唯一來源**。 */
export const FUT_CHART_MODES: readonly (readonly [FutChartMode, string])[] = [
  ["intraday", "分時"],
  ["m1", "1分"],
  ["m5", "5分"],
  ["m15", "15分"],
  ["m30", "30分"],
  ["m60", "60分"],
  ["day", "日K"],
] as const;

/** 白名單驗證。值域直接由 `FUT_CHART_MODES` 推導 —— 另寫一條 regex 就是第二份值域,
 *  加模式時漏改的那一份會靜默把新模式擋在 localStorage 還原之外。 */
export function isFutChartMode(v: string): v is FutChartMode {
  return FUT_CHART_MODES.some(([m]) => m === v);
}

/** `m30` → 30;分時與日 K 回 1(不聚合)。 */
export function futMinutesOf(mode: FutChartMode): number {
  if (mode === "intraday" || mode === "day") return 1;
  const n = Number(mode.slice(1));
  return Number.isFinite(n) && n >= 1 ? n : 1;
}

/** localStorage 還原:壞值 / 別頁的值一律退回 `intraday`。
 *
 *  整段包 try/catch 的理由同 `constants.purgeOrphanKeys`:Safari 私密視窗下光是存取
 *  localStorage 就會拋,而這支是在 `useState` 初始器裡跑 —— 拋出去就是整頁白屏。 */
export function initialFutChartMode(): FutChartMode {
  try {
    const saved = window.localStorage.getItem(FUT_CHART_MODE_KEY);
    return saved !== null && isFutChartMode(saved) ? saved : "intraday";
  } catch {
    return "intraday";
  }
}

export function persistFutChartMode(mode: FutChartMode): void {
  try {
    window.localStorage.setItem(FUT_CHART_MODE_KEY, mode);
  } catch {
    // 寫不進去就是這次不記住,不值得為此讓切模式這個動作失敗
  }
}
