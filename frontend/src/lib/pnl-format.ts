/** 損益顯示格式(自 `components/stock/LadderView.tsx` 搬出,**行為零變更**)。
 *
 *  閃電梯部位列以外,自選列 / 單檔 header / 群組卡也要印同一組數字 —— 顯示規則
 *  (缺值破折號、正號、千分位、賺紅賠綠)只能有一份定義,不然三處會各自漂。
 *  `LadderView` 仍 re-export 這三個名字,既有 import 路徑不變。
 */

/** 缺值顯示。部位條上「沒有這個數字」與「這個數字是 0」必須看得出差別。 */
export const DASH = "—";

export function pnlText(pnl: number | null): string {
  if (pnl === null) return DASH;
  return `${pnl > 0 ? "+" : ""}${pnl.toLocaleString("en-US")}`;
}

/** 台股慣例:賺紅賠綠。 */
export function pnlTone(pnl: number | null): string {
  if (pnl === null) return "text-ink-dim";
  return pnl > 0 ? "text-bull" : pnl < 0 ? "text-bear" : "text-ink";
}
