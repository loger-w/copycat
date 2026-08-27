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

/** 後端給的 `YYYY-MM-DD` 是不是週末。
 *
 *  **以 UTC 午夜解讀,不用本機 `getDay()`**(AR8):`new Date("2026-08-17")` 是 UTC
 *  午夜,在 UTC−n 的機器上讀回本機日期會退成前一天 —— 週一會被算成週日。這裡比的是
 *  「後端那個日期字串是星期幾」,與看盤機的時區無關。
 *
 *  形狀不合(空字串 / 亂字串)→ `NaN` → false:失效方向是「少擋一次」(照常顯示),
 *  不是拿 NaN 去當星期幾。 */
export function isWeekendIso(iso: string): boolean {
  const day = new Date(`${iso}T00:00:00Z`).getUTCDay();
  return day === 0 || day === 6;
}

/** 非週末且不在假日集合。 */
export function isTradingDay(d: Date): boolean {
  const day = d.getDay(); // 0 = 週日
  if (day === 0 || day === 6) return false;
  return !holidaySet.has(isoLocalDate(d));
}

/** `YYYY-MM-DD` 是不是交易日(非週末且不在假日集合)。
 *
 *  `holidays` 可顯式帶入:元件把 `/api/calendar` 的 query data 當 memo dep 時要用**那一份**
 *  算,不然日曆載入後 memo 不知道要重算(模組級集合的變動對 React 不可見)。
 *  未帶 = 讀模組集合(純函式 / `refetchInterval` callback 那條路)。 */
function isTradingDayIso(iso: string, holidays: ReadonlySet<string> = holidaySet): boolean {
  return !isWeekendIso(iso) && !holidays.has(iso);
}

/** `YYYY-MM-DD` ± n 天,以 **UTC 日曆**進位(同 `isWeekendIso`:比的是日期字串本身,與看盤機時區無關)。
 *  `lib/allday.ts::anchorDateOf` 的「凌晨 → 前一日」也吃這一支(不各留一份日期位移)。 */
export function shiftIso(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  // 壞字串(後端 bar `t` 形狀不合)→ Invalid Date,`toISOString` 會 RangeError 炸掉整個 render;
  // 原樣回傳讓失效方向留在「錨定日是個怪字串、那根 bar 被切掉」(review round 1 Spec 6)。
  if (Number.isNaN(d.getTime())) return iso;
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** 上界:連續非交易日最長是春節 ~10 天;30 是「絕不無限迴圈」的護欄,不是業務常數。 */
const NEXT_TRADING_DAY_MAX_STEPS = 30;

/** `iso` 之後的**第一個交易日**(嚴格大於 `iso`)。
 *
 *  期指夜盤的錨定日用它:D 15:00 開的夜盤屬 D 的次一交易日(期交所口徑;`lib/allday.ts`)。
 *  未載日曆 = 只跳週末 —— 週五夜盤仍正確歸週一,只有假日前夜盤會暫時歸到假日
 *  (與 `inFuturesAllDayHours` 的退化同向;日曆載入後 caller 以 query data 當 dep 重算)。
 *  30 步內全非交易日 → 回第 31 天(有界)。 */
export function nextTradingDayIso(iso: string, holidays: ReadonlySet<string> = holidaySet): string {
  let cur = iso;
  for (let i = 0; i < NEXT_TRADING_DAY_MAX_STEPS; i += 1) {
    cur = shiftIso(cur, 1);
    if (isTradingDayIso(cur, holidays)) return cur;
  }
  return shiftIso(cur, 1);
}
