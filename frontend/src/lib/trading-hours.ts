/** 台北交易時段判定(本機時區 = 台北,部署綁本機)。
 *
 * 從 `hooks/useStockBars.ts` 搬來(index-board 🔵):大盤頁的 K 線輪詢要用同一條規則,
 * 而 `lib/` 才是純函式的落點 —— 讓新 hook 去 import 一個 hooks 模組只為拿一個 helper
 * 是反向依賴。`useStockBars` 仍 re-export,個股側 import 路徑不變。
 *
 * 週末必須擋掉:少了星期判定,週六日整個上午都會每 60s 打一次當日段,而當日段恆空
 * → `today_put` don't-cache-empty → 每次都真的走 TC4 SubHistory(首頁 poll deadline
 * ≈ 30s、約 30 個 REQ,搶同一個 source 的 `api.lock`)。
 *
 * 起點取 09:01 而非 08:45:當日第一根 1K 就是 09:01,更早輪詢必定空手而回。
 * (國定假日仍會空跑 —— 需要交易日曆才擋得掉,列入 docs/next-time.md。)
 */
export function inTradingHours(now: Date = new Date()): boolean {
  const day = now.getDay();
  if (day === 0 || day === 6) return false;
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= 9 * 60 + 1 && mins <= 13 * 60 + 35;
}

/** 台指期日盤時段(08:45 開盤 → 首根 1K 是 08:46;13:45 收盤 + 一分鐘餘裕)。
 *
 * 個股那把尺(09:01–13:35)套在期指上,開盤前 15 分與 13:36–13:45 的分 K 不會自動
 * 更新,要手動切模式才重取(review P2-5)。夜盤不在本輪 scope(期指 K 線只取日盤窗)。 */
export function inFuturesTradingHours(now: Date = new Date()): boolean {
  const day = now.getDay();
  if (day === 0 || day === 6) return false;
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= 8 * 60 + 46 && mins <= 13 * 60 + 46;
}

/** 台指期**近全時段**(日盤 + 夜盤)輪詢窗(SC-12;design §4.2)。
 *
 * **星期是必要的一維,不是加分項**:夜盤後半(00:00–05:00)屬**前一交易日**,所以
 * 「週六凌晨 = 週五夜盤」要開、「週一凌晨 = 週日無夜盤」要關。少了這一維,週末兩天
 * 會整夜每 60s 空打當日段(當日段恆空 → don't-cache-empty → 每次都真的走 TC4)。
 *
 * 兩段停輪詢窗:13:51–14:54(日盤收→夜盤開,含收尾餘裕)與 05:06–08:39。
 * 國定假日不處理(既有兩支同;需要交易日曆才擋得掉)。 */
export function inFuturesAllDayHours(now: Date = new Date()): boolean {
  const day = now.getDay(); // 0 = 週日
  const mins = now.getHours() * 60 + now.getMinutes();
  // 00:00–05:05 先判:這段屬前一日的夜盤,所以放行的是週二〜週六(週一凌晨要關)
  if (mins <= 5 * 60 + 5) return day >= 2 && day <= 6;
  if (day === 0 || day === 6) return false;
  return (mins >= 8 * 60 + 40 && mins <= 13 * 60 + 50) || mins >= 14 * 60 + 55;
}
