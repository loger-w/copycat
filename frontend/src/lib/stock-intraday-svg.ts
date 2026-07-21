/** 江波圖幾何純函數(零 React 依賴;design v4 §3)。

價格 y 軸以參考價置中、對稱涵蓋當日高低(台股分時圖慣例);漲跌停在域內才給座標。
VWAP 線由分鐘序列 running 近似(Σ close×vol / Σ vol),與後端逐筆 VWAP 誤差
在分鐘粒度內可忽略。 */

import type { MinuteAgg, StockMeta } from "@/lib/stock-accum";

export const X_START_MIN = 9 * 60; // 09:00
export const X_END_MIN = 13 * 60 + 30; // 13:30

export interface Pt {
  x: number;
  y: number;
}

export interface VolumeBar {
  x: number;
  h: number;
  v: number;
}

export interface EnergyBar {
  x: number;
  outer: number;
  inner: number;
  outerH: number;
  innerH: number;
}

export interface IntradayGeometry {
  priceLine: (Pt & { minute: number })[];
  vwapLine: (Pt & { vwap: number })[];
  refY: number;
  upperY: number | null;
  lowerY: number | null;
  yDomain: [number, number]; // 毫元
  volumeBars: VolumeBar[];
  energyBars: EnergyBar[];
}

interface Input {
  minutes: Map<number, MinuteAgg>;
  meta: StockMeta | null;
}

interface Size {
  width: number;
  height: number;
}

export function buildIntradayGeometry(input: Input, size: Size): IntradayGeometry {
  const entries = [...input.minutes.entries()]
    .filter(([k]) => k >= X_START_MIN && k <= X_END_MIN)
    .sort(([a], [b]) => a - b);
  const prices = entries.map(([, m]) => m.c).filter((p) => p > 0);
  const ref = input.meta?.ref ?? (prices.length ? prices[0]! : 0);
  const hi = Math.max(ref, ...prices);
  const lo = Math.min(ref, ...prices);
  // 對稱域:以 ref 為中心,半幅 = max 偏離 × 1.1(最少 1% 防平線貼邊)
  const half = Math.max(hi - ref, ref - lo, ref * 0.01) * 1.1 || 1;
  const yTop = ref + half;
  const yBottom = ref - half;
  const toY = (p: number): number => ((yTop - p) / (yTop - yBottom)) * size.height;
  const toX = (minute: number): number =>
    ((minute - X_START_MIN) / (X_END_MIN - X_START_MIN)) * size.width;

  const priceLine = entries.map(([minute, m]) => ({ minute, x: toX(minute), y: toY(m.c) }));

  const vwapLine: (Pt & { vwap: number })[] = [];
  let amount = 0;
  let volume = 0;
  for (const [minute, m] of entries) {
    amount += m.c * m.v;
    volume += m.v;
    if (volume > 0) {
      const vwap = Math.round(amount / volume);
      vwapLine.push({ x: toX(minute), y: toY(vwap), vwap });
    }
  }

  const maxVol = Math.max(1, ...entries.map(([, m]) => m.v));
  const volumeBars = entries.map(([minute, m]) => ({
    x: toX(minute),
    h: (m.v / maxVol) * size.height,
    v: m.v,
  }));
  const maxSide = Math.max(1, ...entries.map(([, m]) => Math.max(m.o, m.i)));
  const energyBars = entries.map(([minute, m]) => ({
    x: toX(minute),
    outer: m.o,
    inner: m.i,
    outerH: (m.o / maxSide) * size.height,
    innerH: (m.i / maxSide) * size.height,
  }));

  const upper = input.meta?.upper ?? null;
  const lower = input.meta?.lower ?? null;
  return {
    priceLine,
    vwapLine,
    refY: toY(ref),
    upperY: upper != null && upper <= yTop ? toY(upper) : null,
    lowerY: lower != null && lower >= yBottom ? toY(lower) : null,
    yDomain: [yBottom, yTop],
    volumeBars,
    energyBars,
  };
}
