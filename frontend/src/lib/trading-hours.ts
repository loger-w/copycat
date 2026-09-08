/** 台北交易時段判定(本機時區 = 台北,部署綁本機)。
 *
 * 從 `hooks/useStockBars.ts` 搬來(index-board 🔵):大盤頁的 K 線輪詢要用同一條規則,
 * 而 `lib/` 才是純函式的落點 —— 讓新 hook 去 import 一個 hooks 模組只為拿一個 helper
 * 是反向依賴。`useStockBars` 仍 re-export,個股側 import 路徑不變。
 *
 * 非交易日必須擋掉:少了這一維,週末與國定假日整個上午都會每 60s 打一次當日段,
 * 而當日段恆空 → `today_put` don't-cache-empty → 每次都真的走 TC4 SubHistory
 * (首頁 poll deadline ≈ 30s、約 30 個 REQ,搶同一個 source 的 `api.lock`)。
 *
 * 起點取 09:01 而非 08:45:當日第一根 1K 就是 09:01,更早輪詢必定空手而回。
 * (國定假日自 mod/trading-calendar 起由 `isTradingDay` 一併擋掉 —— 假日集合來自
 * `/api/calendar`;未載入時退回只擋週末 = 改動前行為。)
 */
import { isTradingDay } from "@/lib/trading-calendar";

export function inTradingHours(now: Date = new Date()): boolean {
  if (!isTradingDay(now)) return false;
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= 9 * 60 + 1 && mins <= 13 * 60 + 35;
}

/** 一天內的「開點」(小時, 分),`msUntilNextOpen` 的候選表。 */
type OpenAt = readonly [hh: number, mm: number];

/** 距**下一個開點**的毫秒數:掃今天起 14 個日曆日,逐日取 `opens` 中第一個嚴格在 `now` 之後、
 *  且該日是交易日的候選。假日集合與 `in*Hours` 同源(`isTradingDay`);14 天內找不到(日曆異常)
 *  → 退回一天後再評估,失效方向是「多等」不是空轉輪詢。三把時段閘各自的開點表在下面三支公開函式,
 *  **開點分鐘必須與對應 `in*Hours` 的起點同尺**(測試以「前一分鐘 in=false 且距開點 60 s」釘住);
 *  **`opens` 必須遞增**(內層迴圈回第一個未過的候選,倒序會靜默回較晚的那個;round-1 std F-05)。 */
function msUntilNextOpen(now: Date, opens: readonly OpenAt[]): number {
  for (let d = 0; d <= 14; d++) {
    const day = new Date(now);
    day.setDate(day.getDate() + d);
    if (!isTradingDay(day)) continue;
    for (const [hh, mm] of opens) {
      const open = new Date(day);
      open.setHours(hh, mm, 0, 0);
      if (open.getTime() <= now.getTime()) continue; // 這個開點已過 → 看下一個
      return open.getTime() - now.getTime();
    }
  }
  return 24 * 60 * 60 * 1000;
}

/** 距下一個現股交易窗開點(09:01,`inTradingHours` 同一把尺)的毫秒數。
 *
 * `refetchInterval` 的盤外值(next-time L71):TQ 對 `false` 不排 timer、之後再也不會
 * 重新求值 —— 盤外回「距開點的 ms」讓 query 在窗開瞬間醒來打第一發,之後每次落地
 * 重新求值回盤中節奏。回值請經 `offHoursInterval` 整形再交給 TQ。 */
export function msUntilTradingOpen(now: Date = new Date()): number {
  return msUntilNextOpen(now, [[9, 1]]);
}

/** 距下一個期指日盤開點(08:46 = 首根 1K,`inFuturesTradingHours` 同一把尺)的毫秒數(#205)。
 *  市場頁期指鍵(TXF / MXF / TMF)的分 K 輪詢盤外值。 */
export function msUntilFuturesTradingOpen(now: Date = new Date()): number {
  return msUntilNextOpen(now, [[8, 46]]);
}

/** 距下一個期指**近全時段**開點的毫秒數(#205;`inFuturesAllDayHours` 同一把尺)。開點只有兩個:
 *  08:40(清晨停輪詢窗 05:06–08:39 結束)與 14:55(日盤收→夜盤開 13:51–14:54 結束);00:00–05:05
 *  是前一日 14:55 窗跨午夜的延續、不是新開點,所以非交易日只要跳過該日兩個候選即可(週六凌晨仍在
 *  窗內,本函式不會被求值)。 */
export function msUntilFuturesAllDayOpen(now: Date = new Date()): number {
  return msUntilNextOpen(now, [[8, 40], [14, 55]]);
}

/** 盤外 `refetchInterval` 回值的唯一整形:ceil 到整秒 + 1 s 下限(#205;`groupPollInterval` 08-31
 *  起的算式收成一支,四支輪詢 hook 同用)。
 *  秒級量化(day-bars-rollover 鐵律 (c),全 repo 函式形 refetchInterval 同款):毫秒精度會讓每次
 *  render 求出不同值 → TQ 白做一組 clearInterval/setInterval(盤外仍有 orders 10 s 輪詢驅動 render)。
 *  1_000 下限 = 開點前最後一秒的重排護欄(09:00:59.x 求出 <1 s 的值,不設下限會排出 0ms 級 timer
 *  連環重排)。 */
export function offHoursInterval(msUntilOpen: number): number {
  return Math.max(Math.ceil(msUntilOpen / 1000) * 1000, 1_000);
}

/** 台指期日盤時段(08:45 開盤 → 首根 1K 是 08:46;13:45 收盤 + 一分鐘餘裕)。
 *
 * 個股那把尺(09:01–13:35)套在期指上,開盤前 15 分與 13:36–13:45 的分 K 不會自動
 * 更新,要手動切模式才重取(review P2-5)。夜盤不在本輪 scope(期指 K 線只取日盤窗)。 */
export function inFuturesTradingHours(now: Date = new Date()): boolean {
  if (!isTradingDay(now)) return false;
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= 8 * 60 + 46 && mins <= 13 * 60 + 46;
}

/** 前一日(本機時區)。00:00–05:05 那段夜盤屬前一交易日,判的是它。 */
function prevDay(now: Date): Date {
  const d = new Date(now);
  d.setDate(d.getDate() - 1);
  return d;
}

/** 台指期**近全時段**(日盤 + 夜盤)輪詢窗(SC-12;design §4.2)。
 *
 * **日別是必要的一維,不是加分項**:夜盤後半(00:00–05:00)屬**前一交易日**,所以
 * 「週六凌晨 = 週五夜盤」要開、「週一凌晨 = 週日無夜盤」要關。少了這一維,週末兩天
 * 會整夜每 60s 空打當日段(當日段恆空 → don't-cache-empty → 每次都真的走 TC4)。
 *
 * 該段改判 `isTradingDay(前一日)`(mod/trading-calendar R1):對純週末與原本的
 * `day >= 2 && day <= 6` **完全等價**(週二〜週六的前一日恰是週一〜週五),
 * 只是多疊一層假日否決 —— 假日次日凌晨沒有夜盤可收,而假日**當天**凌晨照收前一
 * 交易日的夜盤。
 *
 * 兩段停輪詢窗:13:51–14:54(日盤收→夜盤開,含收尾餘裕)與 05:06–08:39。 */
export function inFuturesAllDayHours(now: Date = new Date()): boolean {
  const mins = now.getHours() * 60 + now.getMinutes();
  // 00:00–05:05 先判:這段屬前一日的夜盤,所以看的是前一天是不是交易日
  if (mins <= 5 * 60 + 5) return isTradingDay(prevDay(now));
  if (!isTradingDay(now)) return false;
  return (mins >= 8 * 60 + 40 && mins <= 13 * 60 + 50) || mins >= 14 * 60 + 55;
}
