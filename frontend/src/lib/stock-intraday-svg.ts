/** 江波圖幾何純函數(零 React 依賴;design v4 §3 + stock-ui-upgrade SC-1..4)。

Y 域:有漲跌停 → 漲跌停域(上下緣 = upper×1.02 / lower×0.98,僅作縮放允許非整數);
缺 → 對稱 autofit(以參考價置中,無漲跌幅商品 fallback)。
VWAP 線由分鐘序列 running 近似(Σ close×vol / Σ vol),與後端逐筆 VWAP 誤差
在分鐘粒度內可忽略。 */

import type { MinuteAgg, StockMeta } from "@/lib/stock-accum";
import { snapDown } from "@/lib/stock-tick";

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
  dir: "up" | "down" | "flat";
}

export interface EnergyBar {
  x: number;
  outer: number;
  inner: number;
  outerH: number;
  innerH: number;
}

export interface YTick {
  y: number;
  priceMilli: number;
  /** 相對昨收 %;無漲跌停(或無 ref)時 null = 不顯示 % 欄(SC-2) */
  pct: number | null;
}

export interface IntradayGeometry {
  priceLine: (Pt & { minute: number })[];
  vwapLine: (Pt & { vwap: number })[];
  refY: number;
  upperY: number | null;
  lowerY: number | null;
  yDomain: [number, number]; // 毫元
  yTicks: YTick[];
  volumeBars: VolumeBar[];
  energyBars: EnergyBar[];
  /** 價格 → y 座標(overlay 線共用同一縮放) */
  toY: (priceMilli: number) => number;
  /** X 座標反演到分鐘 bucket;bucket 無資料 → null(SC-1/R6,不 snap 最近) */
  minuteOf: (xPx: number) => number | null;
}

export interface StockOverlay {
  cdp: { cdp: number; ah: number; nh: number; nl: number; al: number } | null;
  ma5: number | null;
  ma20: number | null;
  date: string | null;
}

export interface OverlayLine {
  y: number;
  priceMilli: number;
  label: string;
  kind: "cdp" | "ma";
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
  const upper = input.meta?.upper ?? null;
  const lower = input.meta?.lower ?? null;

  let yTop: number;
  let yBottom: number;
  if (upper !== null && lower !== null) {
    // 漲跌停域(SC-2):上下緣貼近漲跌停;僅縮放用,允許非整數(design R7)
    yTop = upper * 1.02;
    yBottom = lower * 0.98;
  } else {
    // 對稱域 fallback:以 ref 為中心,半幅 = max 偏離 × 1.1(最少 1% 防平線貼邊)
    const hi = Math.max(ref, ...prices);
    const lo = Math.min(ref, ...prices);
    const half = Math.max(hi - ref, ref - lo, ref * 0.01) * 1.1 || 1;
    yTop = ref + half;
    yBottom = ref - half;
  }
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
  let prevC = 0;
  const volumeBars: VolumeBar[] = entries.map(([minute, m]) => {
    let dir: VolumeBar["dir"] = "flat";
    if (m.c > 0 && prevC > 0) dir = m.c > prevC ? "up" : m.c < prevC ? "down" : "flat";
    if (m.c > 0) prevC = m.c;
    return { x: toX(minute), h: (m.v / maxVol) * size.height, v: m.v, dir };
  });
  const maxSide = Math.max(1, ...entries.map(([, m]) => Math.max(m.o, m.i)));
  const energyBars = entries.map(([minute, m]) => ({
    x: toX(minute),
    outer: m.o,
    inner: m.i,
    outerH: (m.o / maxSide) * size.height,
    innerH: (m.i / maxSide) * size.height,
  }));

  const yTicks: YTick[] = [];
  const pctOf = (p: number): number | null =>
    ref > 0 ? (p === ref ? 0 : ((p - ref) / ref) * 100) : null;
  if (upper !== null && lower !== null && ref > 0) {
    const midLow = snapDown(Math.round((lower + ref) / 2));
    const midHigh = snapDown(Math.round((ref + upper) / 2));
    for (const p of [lower, midLow, ref, midHigh, upper]) {
      yTicks.push({ y: toY(p), priceMilli: p, pct: pctOf(p) });
    }
  } else {
    for (const p of [yBottom, ref, yTop]) {
      yTicks.push({ y: toY(p), priceMilli: Math.round(p), pct: null });
    }
  }

  const haveMinutes = new Set(entries.map(([k]) => k));
  const minuteOf = (xPx: number): number | null => {
    if (xPx < 0 || xPx > size.width) return null;
    const m = Math.round((xPx / size.width) * (X_END_MIN - X_START_MIN)) + X_START_MIN;
    return haveMinutes.has(m) ? m : null;
  };

  return {
    priceLine,
    vwapLine,
    refY: toY(ref),
    upperY: upper != null && upper <= yTop ? toY(upper) : null,
    lowerY: lower != null && lower >= yBottom ? toY(lower) : null,
    yDomain: [yBottom, yTop],
    yTicks,
    volumeBars,
    energyBars,
    toY,
    minuteOf,
  };
}

/** overlay(CDP/MA)→ 域內水平線;toggle 關的類別不給(SC-4)。 */
export function overlayLines(
  overlay: StockOverlay,
  g: IntradayGeometry,
  toggles: { cdp: boolean; ma: boolean },
): OverlayLine[] {
  const [yBottom, yTop] = g.yDomain;
  const lines: OverlayLine[] = [];
  const push = (p: number | null | undefined, label: string, kind: OverlayLine["kind"]): void => {
    if (p == null || p < yBottom || p > yTop) return;
    lines.push({ y: g.toY(p), priceMilli: p, label, kind });
  };
  if (toggles.cdp && overlay.cdp) {
    push(overlay.cdp.ah, "AH", "cdp");
    push(overlay.cdp.nh, "NH", "cdp");
    push(overlay.cdp.cdp, "CDP", "cdp");
    push(overlay.cdp.nl, "NL", "cdp");
    push(overlay.cdp.al, "AL", "cdp");
  }
  if (toggles.ma) {
    push(overlay.ma5, "MA5", "ma");
    push(overlay.ma20, "MA20", "ma");
  }
  return lines;
}
