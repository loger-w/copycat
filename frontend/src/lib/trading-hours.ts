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
