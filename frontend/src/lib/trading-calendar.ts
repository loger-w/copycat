/** 前端交易日曆(mod/trading-calendar Q7 / SC-9)。
 *
 *  **模組級可變集合,不是 context / hook 回傳值**:消費端是 `lib/trading-hours.ts` 的
 *  三支純函式,而它們被 5 個 `refetchInterval` callback(useBreadthRows / useMarketBars /
 *  useStockBars / useFuturesBars / useIndexOverlay 一路下去)以「零參數、非 React 情境」
 *  求值 —— 要把假日集合送到那裡,不是把整條鏈改成吃 props(每個呼叫點都要改、且
 *  callback 內拿不到 hook),就是放一顆模組級狀態。取後者:寫入點唯一
 *  (`useTradingCalendar` 取數成功),讀取點是純函式。
 *
 *  **未載入 = 空集合 = 只擋週末 = 改動前逐字相同**(白名單 W8):`/api/calendar` 還沒回、
 *  後端沒載日曆、或這支 hook 根本沒掛(元件級測試)時,判定退回純週末 —— 失效方向
 *  永遠是「少擋」(照現行空跑),不會「多擋」把真交易日的輪詢關掉。
 *
 *  日期一律 **本機時區** ISO(`isoLocalDate`),不用 `toISOString()`:那是 UTC,台北
 *  08:00 前會退成前一天,整個早盤的假日比對錯位一天。 */

let holidaySet: ReadonlySet<string> = new Set();

/** 覆寫(不是累加)假日集合;`useTradingCalendar` 每次取數成功後呼叫。
 *  覆寫語意讓「日曆更新後移除某天」也能生效。 */
export function setHolidays(dates: readonly string[]): void {
  holidaySet = new Set(dates);
}

/** 清回空集合。測試 `beforeEach` 用 —— 模組級狀態會跨 it / 跨 describe 外溢。 */
export function clearHolidays(): void {
  holidaySet = new Set();
}

/** 本機時區的 `YYYY-MM-DD`(月 / 日補零)。 */
export function isoLocalDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** 非週末且不在假日集合。 */
export function isTradingDay(d: Date): boolean {
  const day = d.getDay(); // 0 = 週日
  if (day === 0 || day === 6) return false;
  return !holidaySet.has(isoLocalDate(d));
}
