/** 指數分時幾何純函數(index-board SC-2/3;零 React 依賴)。
 *
 * 指數無漲跌停 → autofit 域(上下 0.3% pad);無量圖無 VWAP(Volume=0)。
 * minutes 鍵 = "HHMM"(bar 終點標記,後端契約)。
 */

export const X_START_MIN = 9 * 60;
export const X_END_MIN = 13 * 60 + 30;

interface SeriesInput {
  minutes: Record<string, number>;
  ref: number | null;
  high?: number | null;
  low?: number | null;
}

interface Size {
  width: number;
  height: number;
}

export interface IndexPt {
  x: number;
  y: number;
  minute: string;
  p: number;
}

export interface IndexGeometry {
  line: IndexPt[];
  refY: number;
  yDomain: [number, number];
  yTicks: { y: number; priceMilli: number }[];
}

function sortedEntries(minutes: Record<string, number>): [string, number][] {
  return Object.entries(minutes)
    .filter(([k]) => k >= "0900" && k <= "1330")
    .sort(([a], [b]) => (a < b ? -1 : 1));
}

function toX(key: string, width: number): number {
  const m = Number(key.slice(0, 2)) * 60 + Number(key.slice(2, 4));
  return ((m - X_START_MIN) / (X_END_MIN - X_START_MIN)) * width;
}

export function buildIndexGeometry(input: SeriesInput, size: Size): IndexGeometry {
  const entries = sortedEntries(input.minutes);
  const closes = entries.map(([, p]) => p);
  const ref =
    input.ref ?? (closes.length ? closes.reduce((s, p) => s + p, 0) / closes.length : 0);
  const hi = Math.max(ref, input.high ?? -Infinity, ...closes);
  const lo = Math.min(ref, input.low ?? Infinity, ...closes);
  const yTop = (Number.isFinite(hi) ? hi : ref) * 1.003 || 1;
  const yBottom = (Number.isFinite(lo) ? lo : ref) * 0.997;
  const span = yTop - yBottom || 1;
  const toY = (p: number): number => ((yTop - p) / span) * size.height;

  const line = entries.map(([minute, p]) => ({ minute, p, x: toX(minute, size.width), y: toY(p) }));
  const yTicks = [yBottom, ref, yTop].map((p) => ({ y: toY(p), priceMilli: Math.round(p) }));
  return { line, refY: toY(ref), yDomain: [yBottom, yTop], yTicks };
}

export interface OverlayLinePts {
  pts: { x: number; y: number; pct: number }[];
}

export interface IndexOverlayGeometry {
  lines: OverlayLinePts[];
  zeroY: number;
  pctDomain: [number, number];
}

export function buildOverlayGeometry(
  series: { minutes: Record<string, number>; ref: number | null }[],
  size: Size,
): IndexOverlayGeometry {
  const pctSeries = series
    .filter((s) => s.ref !== null && s.ref > 0)
    .map((s) =>
      sortedEntries(s.minutes).map(([minute, p]) => ({
        minute,
        pct: ((p - s.ref!) / s.ref!) * 100,
      })),
    );
  const all = pctSeries.flat().map((p) => p.pct);
  const lo = Math.min(0, ...all) - 0.3;
  const hi = Math.max(0, ...all) + 0.3;
  const span = hi - lo || 1;
  const toY = (pct: number): number => ((hi - pct) / span) * size.height;
  return {
    lines: pctSeries.map((pts) => ({
      pts: pts.map(({ minute, pct }) => ({ x: toX(minute, size.width), y: toY(pct), pct })),
    })),
    zeroY: toY(0),
    pctDomain: [lo, hi],
  };
}
