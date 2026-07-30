/** 六腿江波圖幾何純函數(零 React 依賴;design v2 §5)。
 *
 * 與既有 `index-chart-svg.ts` / `stock-intraday-svg.ts` 的差別:那兩支把 x 軸寫死在
 * 09:00–13:30(台股日盤),本圖的窗**跟盤別走**(日盤 08:45–13:45 / 夜盤 15:00–次日 05:00),
 * 由後端 payload 的 `window` 給。既有兩支已上線且有測試,不動它們(共用化條件記 next-time)。
 *
 * 兩種呈現:
 * - 並排(`buildLegGeometry`):單腿絕對價 + 「窗內第一筆」的平盤基準線 → autofit 域。
 *   指數期貨沒有漲跌停可當域邊界,只能 autofit。
 * - 重疊(`buildOverlayGeometry`):各腿一律以窗內第一筆為 0%,y 為百分比 —— 六腿價格量級
 *   差 15 倍(富台 3462 vs 道瓊 51909),不正規化根本疊不起來。
 */

import type { RiverLeg, RiverWindow } from "@/types";

export interface RiverSize {
  width: number;
  height: number;
}

/** 上下留邊(像素,不是價格域放寬):讓貼邊的線不被裁掉半條 stroke。 */
export const PAD_Y = 4;

/** 並排卡片的 autofit 上下外推(比例);單點退化時用 SINGLE_PAD 撐開域。 */
const FIT_PAD = 0.0005;
const SINGLE_PAD = 0.001;
/** 重疊圖的 % 域外推(百分點) */
const PCT_PAD = 0.05;

export interface LegPoint {
  x: number;
  y: number;
  offset: number;
  p: number;
}

export interface LegGeometry {
  line: LegPoint[];
  /** 平盤(窗內第一筆)基準線 y */
  baseY: number;
  yDomain: [number, number];
  yTicks: { y: number; priceMilli: number }[];
  first: number | null;
  last: number | null;
  /** 相對窗首的漲跌百分比;無資料 → null */
  pct: number | null;
}

export interface OverlayPoint {
  x: number;
  y: number;
  offset: number;
  pct: number;
}

export interface OverlayLine {
  key: string;
  label: string;
  colorIndex: number;
  pts: OverlayPoint[];
}

export interface OverlayGeometry {
  lines: OverlayLine[];
  zeroY: number;
  pctDomain: [number, number];
}

export interface OverlayEntry {
  key: string;
  label: string;
  colorIndex: number;
  leg: RiverLeg;
}

/** 字串鍵 → 數值鍵並依數值排序。字典序會把 "100" 排在 "9" 前面(真的會畫錯圖)。 */
function sortedPoints(leg: RiverLeg): [number, number][] {
  return Object.entries(leg.minutes)
    .map(([k, v]): [number, number] => [Number(k), v])
    .filter(([offset]) => Number.isFinite(offset))
    .sort((a, b) => a[0] - b[0]);
}

function span(window: RiverWindow): number {
  return Math.max(1, window.end_min - window.start_min);
}

function toX(offset: number, window: RiverWindow, size: RiverSize): number {
  return (offset / span(window)) * size.width;
}

/** 繪圖區高度(扣掉上下留邊);至少 1 避免除以零。 */
function plotHeight(size: RiverSize): number {
  return Math.max(1, size.height - PAD_Y * 2);
}

export function buildLegGeometry(
  leg: RiverLeg,
  window: RiverWindow,
  size: RiverSize,
): LegGeometry {
  const points = sortedPoints(leg);
  const prices = points.map(([, p]) => p);
  const first = prices.length ? prices[0]! : null;
  const last = prices.length ? prices[prices.length - 1]! : null;

  const base = first ?? 0;
  const hi = prices.length ? Math.max(...prices) : base;
  const lo = prices.length ? Math.min(...prices) : base;
  // 單點(或全平)時 hi === lo → 域寬 0,toY 會變無界線性函數;用 SINGLE_PAD 撐開
  const pad = hi > lo ? (hi - lo) * FIT_PAD : Math.max(Math.abs(base) * SINGLE_PAD, 1);
  const yTop = hi + pad;
  const yBottom = lo - pad;
  const ySpan = Math.max(1e-9, yTop - yBottom);
  const toY = (p: number): number => PAD_Y + ((yTop - p) / ySpan) * plotHeight(size);

  return {
    line: points.map(([offset, p]) => ({
      offset,
      p,
      x: toX(offset, window, size),
      y: toY(p),
    })),
    baseY: toY(base),
    yDomain: [yBottom, yTop],
    yTicks: [yTop, base, yBottom].map((p) => ({ y: toY(p), priceMilli: Math.round(p) })),
    first,
    last,
    pct: first !== null && first > 0 && last !== null ? (last / first - 1) * 100 : null,
  };
}

export function buildOverlayGeometry(
  entries: OverlayEntry[],
  window: RiverWindow,
  size: RiverSize,
): OverlayGeometry {
  const series = entries
    .map((entry) => {
      const points = sortedPoints(entry.leg);
      const first = points.length ? points[0]![1] : null;
      if (first === null || first <= 0) return null; // 全窗無值的腿不畫(不是 0% 直線)
      return {
        entry,
        pcts: points.map(([offset, p]): [number, number] => [offset, (p / first - 1) * 100]),
      };
    })
    .filter((s): s is NonNullable<typeof s> => s !== null);

  const all = series.flatMap((s) => s.pcts.map(([, pct]) => pct));
  const lo = Math.min(0, ...all) - PCT_PAD;
  const hi = Math.max(0, ...all) + PCT_PAD;
  const pctSpan = Math.max(1e-9, hi - lo);
  const toY = (pct: number): number => PAD_Y + ((hi - pct) / pctSpan) * plotHeight(size);

  return {
    lines: series.map((s) => ({
      key: s.entry.key,
      label: s.entry.label,
      colorIndex: s.entry.colorIndex,
      pts: s.pcts.map(([offset, pct]) => ({
        offset,
        pct,
        x: toX(offset, window, size),
        y: toY(pct),
      })),
    })),
    zeroY: toY(0),
    pctDomain: [lo, hi],
  };
}

function hhmm(minuteOfDay: number): string {
  const m = ((minuteOfDay % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

/** x 軸時間刻度:窗長 > 400 分(夜盤)每 3 小時、否則每小時。label 由窗現算,不寫死字面表。 */
export function timeTicks(window: RiverWindow): { offset: number; label: string }[] {
  const step = span(window) > 400 ? 180 : 60;
  const ticks: { offset: number; label: string }[] = [];
  for (let offset = 0; offset <= span(window); offset += 1) {
    const minute = window.start_min + offset;
    if (minute % step === 0) ticks.push({ offset, label: hhmm(minute) });
  }
  return ticks;
}

/** 右緣腿名的防疊:把靠太近的 y 往下推開至 `minGap`,推到底再往上回折。
 *
 * 六腿收盤價位接近時(real-env 截圖實見),原位標籤會互相疊住 —— 既有 `IndexPage` 只有
 * 兩條線所以沒踩到。回傳陣列與**輸入順序**對應(呼叫端依 index 取用)。
 */
export function spreadLabelYs(ys: number[], minGap: number, maxY: number): number[] {
  const order = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
  let prev = -Infinity;
  for (const item of order) {
    item.y = Math.max(item.y, prev + minGap);
    prev = item.y;
  }
  // 超出下緣 → 整串往上平移(仍保持彼此間距)
  const overflow = prev - maxY;
  if (overflow > 0) {
    for (const item of order) item.y -= overflow;
  }
  const out = new Array<number>(ys.length);
  for (const item of order) out[item.i] = item.y;
  return out;
}

/** 游標 x(viewBox 座標)→ 最近的分鐘 offset;域外 null(不 clamp 成端點)。 */
export function offsetAtX(
  xPx: number,
  window: RiverWindow,
  size: RiverSize,
): number | null {
  if (xPx < 0 || xPx > size.width || size.width <= 0) return null;
  return Math.round((xPx / size.width) * span(window));
}
