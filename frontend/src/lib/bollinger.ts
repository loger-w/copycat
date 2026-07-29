/** 布林通道純函式(毫元整數運算;無 React 依賴,元件只負責掛 DOM)。
 *
 * 中軌刻意用 `Math.floor(mean)` 而非 `Math.round` —— 要與 `candle.ts::movingAverage`
 * 逐根相等,圖上「中軌 = MA20」才是同一條線而不是差一毫元的兩條(change-spec SC-6.6)。
 *
 * 標準差走「先算均值再逐根取差」的直算法,不用 Σx²−(Σx)²/n 的一趟法:視窗只有 20 根、
 * 成本可忽略,而毫元價位平方後量級到 1e11,一趟法在低波動盤整段會有災難性抵銷。 */

import type { Bar } from "@/lib/candle";

export interface Band {
  /** 中軌 = n 期收盤簡單均線(與 movingAverage 同值) */
  mid: number;
  upper: number;
  lower: number;
}

/** 前 n−1 根為 null(樣本不足)。 */
export function bollinger(bars: readonly Bar[], n = 20, k = 2): (Band | null)[] {
  const out: (Band | null)[] = [];
  for (let i = 0; i < bars.length; i += 1) {
    if (i < n - 1) {
      out.push(null);
      continue;
    }
    let sum = 0;
    for (let j = i - n + 1; j <= i; j += 1) sum += bars[j]!.c;
    const mean = sum / n;
    let sq = 0;
    for (let j = i - n + 1; j <= i; j += 1) {
      const d = bars[j]!.c - mean;
      sq += d * d;
    }
    const sd = Math.sqrt(sq / n);
    out.push({
      mid: Math.floor(mean),
      upper: Math.round(mean + k * sd),
      lower: Math.round(mean - k * sd),
    });
  }
  return out;
}

/** Band 序列 → 單一數列(給 buildCandleGeometry 的 extraSeries 用)。 */
export function bandSeries(bands: readonly (Band | null)[], key: keyof Band): (number | null)[] {
  return bands.map((b) => (b === null ? null : b[key]));
}
