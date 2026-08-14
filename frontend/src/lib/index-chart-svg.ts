/** 指數分時幾何純函數(index-board SC-2/3;零 React 依賴)。
 *
 * 指數無漲跌停 → autofit 域(上下 0.3% pad);無量圖無 VWAP(Volume=0)。
 * minutes 鍵 = "HHMM"(bar 終點標記,後端契約)。
 */

import {
  EDGE_LABEL_H,
  type OverlayLevel,
  type OverlayLine,
  type StockOverlay,
} from "@/lib/stock-intraday-svg";

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
  /** 分鐘收盤的**累計算術平均**線(SC-1;指數無成交量 → 不是 VWAP)。
   *
   *  第 k 點 = 前 k 個**已有**分鐘收盤的平均。缺分鐘不補值 —— 補了就等於替沒發生的
   *  分鐘捏造一筆收盤,而分母被灌水的失效樣態是「均價線在午盤缺報價時緩慢偏向昨收」,
   *  目視完全看不出來。點的 x 與 `line` 逐點同源。 */
  avgLine: IndexPt[];
  refY: number;
  yDomain: [number, number];
  yTicks: { y: number; priceMilli: number }[];
  /** 價格 → y(疊線 / 標籤共用同一縮放;內部閉包直接掛出,不讓呼叫端自行重算) */
  toY: (p: number) => number;
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
  let sum = 0;
  const avgLine = entries.map(([minute, p], i) => {
    sum += p;
    const avg = sum / (i + 1);
    return { minute, p: avg, x: toX(minute, size.width), y: toY(avg) };
  });
  const yTicks = [yBottom, ref, yTop].map((p) => ({ y: toY(p), priceMilli: Math.round(p) }));
  return { line, avgLine, refY: toY(ref), yDomain: [yBottom, yTop], yTicks, toY };
}

/** 疊線層級的固定次序(由上而下)。右緣標籤同 y 時的決勝鍵 —— 少了它,兩條同 y 的線
 *  誰被推開會由 `Array#sort` 對相等鍵的處理決定,兩次 render 之間可能互換上下。 */
const LEVEL_ORDER: readonly OverlayLevel[] = ["ah", "nh", "cdp", "nl", "al", "ma5", "ma20"];

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
  g: Pick<IndexGeometry, "yDomain">,
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

/** 右緣標籤(決策 6)。`kind` 決定文字組法與配色,y 一律由 `rightEdgeLabels` 給。 */
export type RightEdgeLabel =
  | { kind: "ref"; y: number; text: string }
  | { kind: "line"; y: number; level: OverlayLevel; priceMilli: number }
  | { kind: "peg"; y: number; level: OverlayLevel; priceMilli: number; dir: "up" | "down" };

export interface RightEdgeInput {
  /** 昨收標籤。**fixed** —— y 恆為 refY,其餘標籤對它讓位(它與昨收虛線是同一條資訊,
   *  被推開就等於指著錯的價位)。缺 ref → null = 不畫。 */
  ref: { y: number; text: string } | null;
  /** 域內疊線(`overlayLines` 的結果);初始 y = 線 y */
  oLines: readonly OverlayLine[];
  /** 域外掛牌(`outOfDomainLevels` 的結果);初始 y = 上緣 / 下緣 */
  outOfDomain: readonly OutOfDomainLevel[];
  bounds: { top: number; bottom: number };
}

/** 指數分時圖**所有**右緣文字的唯一佈局來源(決策 6)。
 *
 *  刻意不重用個股的 `edgePriceLabels`:那支只收 ma5/ma20,且 `obstacles` 是「極值標記
 *  圓 + 文字」語意,與這裡的「昨收 fixed 標籤」不同 —— 硬套會讓昨收既不在輸入也不在
 *  輸出,而它正是最容易與 cdp 疊字的那一顆。
 *
 *  三段式(與 `edgePriceLabels` 同精神,逐段可測):
 *  (a) 容量截斷 —— 根本裝不下的,依排序末端優先丟(疊印比少畫一顆更不可讀);
 *  (b) 由上而下 10px 最小距下推,撞到 fixed 昨收一律往下讓(方向固定才決定性);
 *  (c) 由下而上回推 —— (b) 只會往下推,推出界就等於沒畫;
 *  (d) clamp 進界後仍相距 <10px 者丟棄。 */
export function rightEdgeLabels(input: RightEdgeInput): RightEdgeLabel[] {
  const { bounds } = input;
  // 界退化(容器被壓到極矮)→ 任何 y 都在界外,clamp 會把全部標籤壓成一坨,不如不畫
  if (bounds.top > bounds.bottom) {
    return input.ref !== null ? [{ kind: "ref", y: input.ref.y, text: input.ref.text }] : [];
  }
  interface Movable {
    y: number;
    rank: number;
    label: RightEdgeLabel;
  }
  const movable: Movable[] = [];
  for (const l of input.oLines) {
    movable.push({
      y: l.y,
      rank: LEVEL_ORDER.indexOf(l.level),
      label: { kind: "line", y: l.y, level: l.level, priceMilli: l.priceMilli },
    });
  }
  for (const o of input.outOfDomain) {
    const y = o.dir === "up" ? bounds.top : bounds.bottom;
    movable.push({
      y,
      rank: LEVEL_ORDER.indexOf(o.level),
      label: { kind: "peg", y, level: o.level, priceMilli: o.priceMilli, dir: o.dir },
    });
  }
  movable.sort((a, b) => a.y - b.y || a.rank - b.rank);

  // (a) 容量
  const capacity = Math.floor((bounds.bottom - bounds.top) / EDGE_LABEL_H) + 1;
  if (movable.length > capacity) movable.length = capacity;

  const fixed = input.ref !== null ? [input.ref.y] : [];

  // (b) 由上而下
  let floor = bounds.top;
  for (const m of movable) {
    let y = Math.max(m.y, floor);
    for (const o of fixed) if (Math.abs(y - o) < EDGE_LABEL_H) y = o + EDGE_LABEL_H;
    m.y = y;
    floor = y + EDGE_LABEL_H;
  }

  // (c) 由下而上回推
  let ceil = bounds.bottom;
  for (let i = movable.length - 1; i >= 0; i -= 1) {
    const m = movable[i]!;
    let y = Math.min(m.y, ceil);
    for (let k = fixed.length - 1; k >= 0; k -= 1) {
      const o = fixed[k]!;
      if (Math.abs(y - o) < EDGE_LABEL_H) y = o - EDGE_LABEL_H;
    }
    m.y = y;
    ceil = y - EDGE_LABEL_H;
  }

  // (d) clamp + 殘餘重疊丟棄
  const out: RightEdgeLabel[] = [];
  if (input.ref !== null) out.push({ kind: "ref", y: input.ref.y, text: input.ref.text });
  let prevY: number | null = null;
  for (const m of movable) {
    const y = Math.min(Math.max(m.y, bounds.top), bounds.bottom);
    if (prevY !== null && y - prevY < EDGE_LABEL_H) continue;
    prevY = y;
    out.push({ ...m.label, y });
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
