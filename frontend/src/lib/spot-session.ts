/** 台股現貨時段判定(SC-5 期現價差 gate;design §6.1)。
 *
 * **為什麼不能只看 `twse.stale`**:`index_engine` 的 watchdog 只在 09:00–13:25 維護
 * stale,收盤後 `p` 保留當日收盤值且 `stale` 恆 false —— 單靠 stale,夜盤整晚都會拿
 * 「今天的收盤指數」去減「夜盤期指」,顯示出一個看起來很像真的假價差。
 *
 * 13:33 而非 13:30:盤後撮合成交價會晚幾分鐘才進來。
 */
export function inTwseSessionNow(now: Date = new Date()): boolean {
  const day = now.getDay();
  if (day === 0 || day === 6) return false;
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= 9 * 60 && mins <= 13 * 60 + 33;
}
