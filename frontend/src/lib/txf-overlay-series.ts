import type { IndexSeries } from "@/hooks/useIndexStream";
import { anchorDateOf } from "@/lib/allday";
import type { Bar } from "@/lib/candle";

/** 個股分時圖疊「台指期」當日走勢(feat/txf-intraday-overlay,spec §3)。
 *
 *  把期貨 tab 那份 allday 1K bars(`useFuturesBars("TXF")`,5 日近全時段)+ 期貨 WS 現價,
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
  /** 毫點;null / 0 = 不可得 */
  p: number | null;
  /** 台北 `HH:MM:SS.fff`(期貨 WS `FuturesProductState.t`) */
  t: string | null;
  /** `YYYY-MM-DD`(`FuturesProductState.date`) */
  date: string | null;
}

/** 日盤段的**起點**分鐘域:bar 標記 0846–1345 → 0845–1344;WS 補尾允許到 1345(收盤撮合那一分鐘,
 *  個股期窗到 13:45)。 */
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
  let high: number | null = null;
  let low: number | null = null;
  let lastMinute = -1;
  const last = bars[bars.length - 1];
  const anchor = last === undefined ? null : anchorDateOf(last.t);
  if (anchor !== null) {
    for (const b of bars) {
      const st = splitStamp(b.t);
      if (st === null || st[0] !== anchor) continue;
      const minute = st[1] - 1; // 終點標記 → 起點分鐘
      if (minute < DAY_FIRST_MIN || minute > DAY_LAST_BAR_MIN) continue;
      // `c <= 0`:TC4 偶發送 "0",後端原樣轉 0 不轉 null;毫點價恆 > 0 → 0 = 不可得(同 futures-overlay usable)
      if (!(b.c > 0)) continue;
      minutes[hhmm(minute)] = b.c;
      p = b.c;
      high = high === null ? b.c : Math.max(high, b.c);
      low = low === null ? b.c : Math.min(low, b.c);
      if (minute > lastMinute) lastMinute = minute;
    }
    // WS 補尾:同錨定日、在最後一根之後、落在日盤段、價可得
    if (quote !== null && quote.date === anchor && quote.t !== null && quote.p !== null && quote.p > 0) {
      const qm = Number(quote.t.slice(0, 2)) * 60 + Number(quote.t.slice(3, 5));
      if (Number.isFinite(qm) && qm > lastMinute && qm >= DAY_FIRST_MIN && qm <= DAY_LAST_TAIL_MIN) {
        minutes[hhmm(qm)] = quote.p;
        p = quote.p;
        high = high === null ? quote.p : Math.max(high, quote.p);
        low = low === null ? quote.p : Math.min(low, quote.p);
      }
    }
  }
  return { p, ref, high, low, stale: wsStale, minutes };
}
