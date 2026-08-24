/** 期貨分時的 CDP / MA 疊線(N042)—— 由**期貨日 K** 前端現算,零 React。
 *
 *  為什麼不走後端 `/api/stock/overlay`:那支吃的是**股號**(現股日線),期指既取不到
 *  也不該套 —— 拿標的現股的 CDP 疊在期貨價上是假陳述(core 第四道閘的既有理由)。
 *  期貨日 K 前端手上本來就有(`useFuturesBars(product, "day")` 是日 K 模式的同一份
 *  query),多一支後端 endpoint 只是把同一份算式搬到另一邊。
 *
 *  **算式與 `copycat/server/overlay.py::compute_cdp / compute_ma` 逐式相同**(整數毫元、
 *  除法一律 floor):同一組疊線在個股頁與期貨頁長不一樣是純數字不一致,沒有任何錯誤
 *  訊號。改一邊要改另一邊 —— 這裡是第二份實作,不是第二套規則。
 *
 *  **基準 = 前一交易日**(2026-08-24 user 拍板):取日 K 最後一根**已完成** bar 的
 *  H/L/C。「已完成」的判準走後端給的 `meta.partial_last`(`bars.is_partial_last`:
 *  末根日期 = 今天)—— 前端自己比日期要再造一套「今天是幾號」的口徑,而那正是
 *  跨午夜 / 夜盤時最容易漂的東西。
 */

import type { Bar } from "@/lib/candle";
import type { StockOverlay } from "@/lib/stock-intraday-svg";

/** 全 null = 「沒有可用的基準日」→ core 的 `cdpAvailable` / `maAvailable` 判 false 而反灰。
 *  **模組層常數**:每次回新物件會打穿 `ChartStatic` 的 memo(症狀只是掉幀,零測試會紅)。 */
const EMPTY_OVERLAY: StockOverlay = { cdp: null, ma5: null, ma20: null, date: null };

/** 毫元價恆 > 0 —— TC4 送 "0" 時後端原樣轉 0 不轉 null(同 `futuresBarsToAccum` 的收口)。
 *  0 進了 CDP 就會憑空長出一條貼在圖底的「支撐位」,而它是完全靜默的假陳述。 */
function usable(b: Bar): boolean {
  return b.c > 0 && b.h > 0 && b.l > 0;
}

function computeCdp(h: number, low: number, c: number): NonNullable<StockOverlay["cdp"]> {
  // (h + l + 2c + 2) // 4:round-half-up 的整數寫法(impl-spec R1,無 float)
  const cdp = Math.floor((h + low + 2 * c + 2) / 4);
  const spread = h - low;
  return { cdp, ah: cdp + spread, nh: 2 * cdp - low, nl: 2 * cdp - h, al: cdp - spread };
}

function computeMa(closes: readonly number[], n: number): number | null {
  if (closes.length < n) return null;
  let sum = 0;
  for (const c of closes.slice(-n)) sum += c;
  return Math.floor(sum / n);
}

/** 日 K(升冪)→ 疊線。`partialLast` = `MarketBars.meta.partial_last`。
 *
 *  空 / 全壞 → 全 null(**不猜**:退而求其次拿更早的一天當「昨日」會讓基準日靜默漂掉,
 *  而畫面上只是幾條位置不對的線)。日 K 尚未回時 caller 傳 null 而不是呼叫本函式 ——
 *  「還沒回」與「回了但沒有」在 core 是兩種可用性(前者不預先反灰)。 */
export function buildFuturesOverlay(bars: readonly Bar[], partialLast: boolean): StockOverlay {
  const raw = partialLast ? bars.slice(0, -1) : bars;
  const done = raw.filter(usable);
  const last = done[done.length - 1];
  if (last === undefined) return EMPTY_OVERLAY;
  const closes = done.map((b) => b.c);
  return {
    cdp: computeCdp(last.h, last.l, last.c),
    ma5: computeMa(closes, 5),
    ma20: computeMa(closes, 20),
    // 日 K 的 `t` 就是 `YYYY-MM-DD`(分 K 才帶空格 + HH:MM)
    date: last.t,
  };
}
