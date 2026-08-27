import type { IndexSeries } from "@/hooks/useIndexStream";
import { anchorDateOf } from "@/lib/allday";
import type { Bar } from "@/lib/candle";

/** 個股分時圖疊「台指期」當日走勢(feat/txf-intraday-overlay,spec §3)。
 *
 *  把期貨 tab 那份 allday 1K bars(`useFuturesBars("TXF")`,5 日近全時段)+ index engine 每拍轉供的
 *  台指期現價(`useIndexStream().txf`,~1 s;不用期貨 WS 0.1 s coalesce 流,免圖牆 memo 被打穿),
 *  轉成與加權 / 櫃買**同形**的 `IndexSeries`(分鐘鍵 = 起點 HHMM,毫點價)→ 既有
 *  `buildIndexOverlayLines` 零改動吃得下第三條線。純函式、零 React 依賴;caller 以 useMemo 折。
 *
 *  三個容易靜默錯的口徑,全部在這裡收:
 *  - **只取錨定日的日盤段**(08:46–13:45 的 bar 標記):錨定日 = `anchorDateOf(最後一根)`
 *    (`lib/allday.ts`;凌晨 ≤05:00 屬前一日)。夜盤不疊(現貨無盤);前一日日盤不疊。
 *  - **分鐘鍵 = bar 終點標記 − 1 分**:期指 1K 是終點標記(08:45 開盤首根標 0846;tc4-market-facts
 *    期指節 (d)),而個股 / 指數的分鐘鍵是起點(09:01 那分鐘的價鍵 `0901`)。不減一,整條線右移
 *    一格 —— 兩張圖都畫得出來、零訊號。
 *  - **WS 補尾不覆寫**:bars 每 60 s 才更新,沒有補尾線尾恆落後最多一分鐘;但 bar 是分鐘收盤價、
 *    WS 是瞬時價,兩把尺不混 → 只追加「最後一根之後」的分鐘。 */

export interface TxfQuoteInput {
  /** 毫點;null / 0 = 不可得(`TxfQuote.p`) */
  p: number | null;
  /** 台北 `HH:MM:SS`(`TxfQuote.time`,index engine 於價變動時自記牆鐘);只讀前 5 字 */
  t: string | null;
  /** `YYYY-MM-DD` = 個股頁正在看的交易日(`useIndexStream().tradeDate`);與 bars 錨定日不同 → 整條不疊 */
  date: string | null;
}

/** 日盤段的**起點**分鐘域:bar 標記 0846–1345 → 0845–1344;WS 補尾允許到 1345(收盤撮合那一分鐘,
 *  個股期窗到 13:45)。
 *
 *  `high` / `low` 一律 null:`IndexSeries.high/low` 的口徑是後端「當日最高 / 最低成交」,這裡手上只有
 *  分鐘收盤價,算出來的極值是另一把尺;`buildIndexOverlayLines` 也不讀它 —— 填一個看起來對的數字
 *  只會讓日後的讀者拿到靜默錯值(review round 1 S7 / Spec 3)。 */
const DAY_FIRST_MIN = 8 * 60 + 45;
const DAY_LAST_BAR_MIN = 13 * 60 + 44;
const DAY_LAST_TAIL_MIN = 13 * 60 + 45;

function hhmm(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}${String(minute % 60).padStart(2, "0")}`;
}

/** `YYYY-MM-DD HH:MM` → [date, 分鐘數];日 K(無時間)或壞值 → null */
function splitStamp(t: string): [string, number] | null {
  const sp = t.indexOf(" ");
  if (sp < 0) return null;
  const m = Number(t.slice(sp + 1, sp + 3)) * 60 + Number(t.slice(sp + 4, sp + 6));
  return Number.isFinite(m) ? [t.slice(0, sp), m] : null;
}

export function txfBarsToSeries(
  bars: readonly Bar[],
  quote: TxfQuoteInput | null,
  ref: number | null,
  wsStale: boolean,
): IndexSeries | null {
  // 判定寫成保留條件的否定(NaN 兩個比較都 false 會把壞 ref 留下,同 buildOverlayGeometry)
  if (!(ref !== null && ref > 0)) return null;
  const minutes: Record<string, number> = {};
  let p: number | null = null;
  let lastMinute = -1;
  const last = bars[bars.length - 1];
  let anchor = last === undefined ? null : anchorDateOf(last.t);
  // 錨定日必須與個股頁正在看的交易日一致(quote.date = index engine 的 trade_date):交易日凌晨
  // 05:00–08:46 之間 bars 的最後一根還是昨夜的 0500,錨定會落到前一日 —— 個股頁已是今天,
  // 疊前一日的日盤段是假陳述(review round 1 Spec 5)。quote 沒給日期(WS 未就緒)時不擋。
  if (anchor !== null && quote !== null && quote.date !== null && quote.date !== anchor) anchor = null;
  if (anchor !== null) {
    for (const b of bars) {
      const st = splitStamp(b.t);
      if (st === null || st[0] !== anchor) continue;
      const minute = st[1] - 1; // 終點標記 → 起點分鐘
      if (minute < DAY_FIRST_MIN || minute > DAY_LAST_BAR_MIN) continue;
      // `c <= 0`:TC4 偶發送 "0",後端原樣轉 0 不轉 null;毫點價恆 > 0 → 0 = 不可得(同 futures-overlay usable)
      if (!(b.c > 0)) continue;
      minutes[hhmm(minute)] = b.c;
      // `p` 與 `lastMinute` 同一把尺(依分鐘最大者),不是「陣列最後一個命中者」——
      // 輸入亂序時兩者才不會分家(review round 1 S6)
      if (minute > lastMinute) {
        lastMinute = minute;
        p = b.c;
      }
    }
    // WS 補尾:同錨定日、在最後一根之後、落在日盤段、價可得
    if (quote !== null && quote.date === anchor && quote.t !== null && quote.p !== null && quote.p > 0) {
      const qm = Number(quote.t.slice(0, 2)) * 60 + Number(quote.t.slice(3, 5));
      if (Number.isFinite(qm) && qm > lastMinute && qm >= DAY_FIRST_MIN && qm <= DAY_LAST_TAIL_MIN) {
        minutes[hhmm(qm)] = quote.p;
        p = quote.p;
      }
    }
  }
  return { p, ref, high: null, low: null, stale: wsStale, minutes };
}
