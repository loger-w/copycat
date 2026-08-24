/** 期貨分時的 CDP / MA 疊線(N042)—— 由**期貨日 K** 前端現算,零 React。
 *
 *  為什麼不走後端 `/api/stock/overlay`:那支吃的是**股號**(現股日線),期指既取不到
 *  也不該套 —— 拿標的現股的 CDP 疊在期貨價上是假陳述(core 第四道閘的既有理由)。
 *  期貨日 K 前端手上本來就有(`useFuturesBars(product, "day")` 是日 K 模式的同一份
 *  query),多一支後端 endpoint 只是把同一份算式搬到另一邊。
 *
 *  **算式與 `copycat/server/overlay.py::compute_cdp / compute_ma` 同式**(整數毫元、
 *  除法一律 floor),差異只有一條白名單:本檔多一道 `usable()` 0 價閘(TC4 期貨特有)。
 *  白名單的連帶後果:**MA 母體可能與後端不同** —— 壞 bar 被剔掉後視窗會往前挪一根
 *  (後端沒有這道閘,同一組輸入會把 0 當價算進平均)。跨語言 parity 由共用 fixture
 *  `tests/fixtures/overlay_parity.json` 釘住(兩邊各一條測試),契約登記在 CLAUDE.md §4。
 *  改一邊要改另一邊 —— 這裡是第二份實作,不是第二套規則。
 *
 *  **基準 = 圖上錨定日的前一個交易日**(2026-08-24 user 拍板 + review P1):以 caller
 *  給的 `anchorDate`(與 slice / live gate / 成交點同源的 `anchorDateOf`)為界,只收
 *  `t < anchorDate` 的 bar —— 逐字對齊後端 `overlay.py::build_overlay` 的 `date < today`。
 *
 *  **不信 `meta.partial_last`**:那是**日曆日**判準(末根日期 == 今天),而近全軸一張圖
 *  橫跨兩個日曆日,兩頭都破窗 —— (a) 22:00 時 TC4 已把夜盤成形的 bar 標成次一交易日,
 *  末根日期 ≠ 今天 → 不剔,基準落在**尚未發生的交易日**;(b) 00:00–05:00 時日曆日已翻頁
 *  而圖仍錨在前一日,末根日期 ≠ 今天 → 不剔,基準變成**當前這一節自己的未完成 bar**。
 *  再者 meta 缺欄位時 falsy = 不剔末根,失效方向落在不安全側(寧可少算一天,不可拿
 *  未完成 / 未來的 bar 當昨日基準)。
 */

import type { Bar } from "@/lib/candle";
import type { StockOverlay } from "@/lib/stock-intraday-svg";

/** 全 null = 「沒有可用的基準日」→ core 的 `cdpAvailable` / `maAvailable` 判 false 而反灰。
 *  **模組層常數**:每次回新物件會打穿 `ChartStatic` 的 memo(症狀只是掉幀,零測試會紅)。 */
const EMPTY_OVERLAY: StockOverlay = { cdp: null, ma5: null, ma20: null, date: null };

/** 毫元價恆 > 0 —— TC4 送 "0" 時後端原樣轉 0 不轉 null(同 `futuresBarsToAccum` 的收口)。
 *  0 進了 CDP 就會憑空長出一條貼在圖底的「支撐位」,而它是完全靜默的假陳述。
 *  ⚠ 這是與後端算式的**唯一**差異(白名單,見檔頭)。 */
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

/** 日 K(升冪)→ 疊線。`anchorDate` = **這張圖的交易錨定日**(`YYYY-MM-DD`),由 caller
 *  以 `anchorDateOf(sliceCurrentAllday(bars) 末根)` 取得(三處各算一份必漂移)。
 *
 *  空 / 全壞 → 全 null(**不猜**:退而求其次拿更早的一天當「昨日」會讓基準日靜默漂掉,
 *  而畫面上只是幾條位置不對的線)。日 K 尚未回、或錨定日還推不出來(分時 bars 未到)時
 *  caller 傳 null 而不是呼叫本函式 —— 「還沒回」與「回了但沒有」在 core 是兩種可用性
 *  (前者不預先反灰)。 */
export function buildFuturesOverlay(bars: readonly Bar[], anchorDate: string): StockOverlay {
  // 日 K 的 `t` 就是 `YYYY-MM-DD`(分 K 才帶空格 + HH:MM),`slice(0, 10)` 兩種形狀都取得到
  // 日期段 —— 直接字串比大小(ISO 日期的字典序 == 時序)。
  const done = bars.filter((b) => b.t.slice(0, 10) < anchorDate && usable(b));
  const last = done[done.length - 1];
  if (last === undefined) return EMPTY_OVERLAY;
  const closes = done.map((b) => b.c);
  return {
    cdp: computeCdp(last.h, last.l, last.c),
    ma5: computeMa(closes, 5),
    ma20: computeMa(closes, 20),
    date: last.t,
  };
}
