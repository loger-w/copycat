/** 指數分時幾何純函數(index-board SC-2/3;零 React 依賴)。
 *
 * 指數無漲跌停 → autofit 域(上下 0.3% pad);無量圖無 VWAP(Volume=0)。
 * minutes 鍵 = "HHMM"(bar 終點標記,後端契約)。
 */

import { type OverlayLevel, type StockOverlay } from "@/lib/stock-intraday-svg";

export const X_START_MIN = 9 * 60;
export const X_END_MIN = 13 * 60 + 30;

interface Size {
  width: number;
  height: number;
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

/** 落在 y 域外的疊線(SC-7)。`dir` = 在域上方 / 下方 —— 線體不畫,改在右緣掛牌。 */
export interface OutOfDomainLevel {
  level: OverlayLevel;
  priceMilli: number;
  dir: "up" | "down";
}

/** overlay 各值的域外分類。**與 `overlayLines` 互補且共用同一組域判定**:
 *  同一個值只會落進其中一邊(域內 → 畫線,域外 → 掛牌),兩邊各判各的話會出現
 *  「線也畫了、又掛一次牌」或「兩邊都不要」的靜默漏畫。
 *  push 次序刻意與 `overlayLines` 逐行對齊(ah→nh→cdp→nl→al→ma5→ma20)。 */
export function outOfDomainLevels(
  overlay: StockOverlay,
  g: { yDomain: [number, number] },
  toggles: { cdp: boolean; ma: boolean },
): OutOfDomainLevel[] {
  const [yBottom, yTop] = g.yDomain;
  const out: OutOfDomainLevel[] = [];
  const push = (p: number | null | undefined, level: OverlayLevel): void => {
    if (p == null) return;
    if (p > yTop) out.push({ level, priceMilli: p, dir: "up" });
    else if (p < yBottom) out.push({ level, priceMilli: p, dir: "down" });
  };
  if (toggles.cdp && overlay.cdp) {
    push(overlay.cdp.ah, "ah");
    push(overlay.cdp.nh, "nh");
    push(overlay.cdp.cdp, "cdp");
    push(overlay.cdp.nl, "nl");
    push(overlay.cdp.al, "al");
  }
  if (toggles.ma) {
    push(overlay.ma5, "ma5");
    push(overlay.ma20, "ma20");
  }
  return out;
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
