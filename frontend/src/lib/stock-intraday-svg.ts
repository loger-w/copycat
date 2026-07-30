/** 江波圖幾何純函數(零 React 依賴;design v4 §3 + stock-ui-upgrade SC-1..4)。

Y 域(stock-ui-round2 SC-4):有漲跌停 → **域恰為 [lower, upper]**(不再多留 2% 邊);
缺 → 對稱 autofit(以參考價置中,無漲跌幅商品 fallback,白名單 11 不動)。
上下不被裁掉半條 stroke 靠的是 `PAD_Y` 幾何留邊 —— 那是**像素留邊不是價格域放寬**,
所以漲停時走勢線確實貼在最上面那條刻度上。

`toY` 與 `priceAtY` 必須共用同一組 `PAD_Y` / `X_LABEL_H`:兩者各自硬編過一次的話,
反演在域中央仍剛好正確、只在兩端偏移(實測 ±0.3% / ±1.4%),目視幾乎抓不到。

VWAP 線由分鐘序列 running 近似(Σ close×vol / Σ vol),與後端逐筆 VWAP 誤差
在分鐘粒度內可忽略。 */

import type { MinuteAgg, StockMeta } from "@/lib/stock-accum";
import { snapDown } from "@/lib/stock-tick";

export const X_START_MIN = 9 * 60; // 09:00
export const X_END_MIN = 13 * 60 + 30; // 13:30

/** 底部時間標籤帶;繪圖區 = [PAD_Y, height − X_LABEL_H − PAD_Y] */
export const X_LABEL_H = 14;
export const PAD_Y = 4;

/** 內外盤副圖頂端預留(SC-8):量刻度文字畫在這裡。不留的話最大那根 bar 高度恰等於
 *  副圖全高,頂端刻度必被蓋住。 */
export const SUB_TOP_PAD = 10;

/** 左緣刻度的百分比階(SC-4:由上而下)。±10 直接用 upper/lower 原值、0 用 ref 原值。 */
const TICK_PCTS = [10, 8, 6, 4, 2, 0, -2, -4, -6, -8, -10] as const;

/** 左緣價位帶寬度(round4 項 3)。價位文字原本畫在 `x=2` 而繪圖區從 `x=0` 起,
 *  文字直接壓在走勢線與紅綠填色上。讓出這條帶後繪圖區改為 `[Y_AXIS_W, width]`。
 *
 *  取 46 = 元件的 `PRICE_TAG.w`:hover 價位標(左上角固定在 x=0)恰好整格塞進帶內,
 *  不必再為它另留空間;價位文字本身只需 ~24px。 */
export const Y_AXIS_W = 46;

/** 繪圖區寬度(扣掉左緣價位帶);至少 1 避免除以零。 */
export function plotWidth(width: number): number {
  return Math.max(1, width - Y_AXIS_W);
}

/** 分鐘 → x 座標。**幾何與元件共用這一份** —— 兩邊各寫一次的話,任何 x 軸幾何改動
 *  都得同時改對兩處,而漂移的症狀是「線與刻度差幾 px」,目視幾乎抓不到
 *  (同 `toY` / `priceAtY` 必須共用 `PAD_Y` 的理由)。 */
export function minuteToX(minute: number, width: number): number {
  return Y_AXIS_W + ((minute - X_START_MIN) / (X_END_MIN - X_START_MIN)) * plotWidth(width);
}

export interface Pt {
  x: number;
  y: number;
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
}

export interface IntradayGeometry {
  priceLine: (Pt & { minute: number })[];
  vwapLine: (Pt & { vwap: number })[];
  refY: number;
  /** meta 真的有昨收(不是拿首筆成交當 fallback)。false → 無「平盤」可言,
   *  走勢線走單色、不填色(SC-2.4) */
  hasRef: boolean;
  /** 走勢線與平盤之間的封閉多邊形點串;`hasRef` 為 false 或無資料時為空字串 */
  areaPolygon: string;
  upperY: number | null;
  lowerY: number | null;
  yDomain: [number, number]; // 毫元
  yTicks: YTick[];
  energyBars: EnergyBar[];
  /** 內外盤能量的歸一分母 = 該日單邊最大張數(SC-8 量刻度的頂端值) */
  maxSide: number;
  /** 價格 → y 座標(overlay 線共用同一縮放) */
  toY: (priceMilli: number) => number;
  /** y 座標 → 價格(`toY` 的逆函數);回傳前夾制進 yDomain */
  priceAtY: (y: number) => number;
  /** X 座標反演到分鐘 bucket;bucket 無資料 → null(SC-1/R6,不 snap 最近) */
  minuteOf: (xPx: number) => number | null;
}

export interface StockOverlay {
  cdp: { cdp: number; ah: number; nh: number; nl: number; al: number } | null;
  ma5: number | null;
  ma20: number | null;
  date: string | null;
}

/** 疊線種類。`label` 字串已移除(round3 SC-2:右緣改印價位)—— 名稱語意留在 `level`,
 *  顯示文字由元件用 `priceMilli` 現算,判色 / React key 也一律走 `level` 不走文字。 */
export type OverlayLevel = "ah" | "nh" | "cdp" | "nl" | "al" | "ma5" | "ma20";

export interface OverlayLine {
  y: number;
  priceMilli: number;
  level: OverlayLevel;
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
    // 漲跌停域(SC-4):域**恰為**漲跌停,不留 2% 邊。上下緣的呼吸空間改由 PAD_Y 出。
    yTop = upper;
    yBottom = lower;
  } else {
    // 對稱域 fallback:以 ref 為中心,半幅 = max 偏離 × 1.1(最少 1% 防平線貼邊)
    const hi = Math.max(ref, ...prices);
    const lo = Math.min(ref, ...prices);
    const half = Math.max(hi - ref, ref - lo, ref * 0.01) * 1.1 || 1;
    yTop = ref + half;
    yBottom = ref - half;
  }
  // 繪圖區高度(扣掉底部時間帶與上下留邊);至少 1 避免除以零
  const plotH = Math.max(1, size.height - X_LABEL_H - PAD_Y * 2);
  // 退化域(upper === lower)必須把 toY 也特判成常數,不能只靠 `|| 1` 擋除以零 ——
  // 那只讓分母合法,toY 仍是無界線性函數:域寬 1 毫元時差 10 毫元就算出 10×plotH 的座標,
  // 直接飛出畫布數百 px;而 priceAtY 有 clamp 會收斂成常數,兩者就不再互逆。
  const ySpan = yTop - yBottom;
  const flat = ySpan <= 0;
  const toY = (p: number): number =>
    flat ? PAD_Y + plotH / 2 : PAD_Y + ((yTop - p) / ySpan) * plotH;
  const priceAtY = (y: number): number => {
    if (flat) return yTop;
    const raw = yTop - ((y - PAD_Y) / plotH) * ySpan;
    return Math.min(yTop, Math.max(yBottom, Math.round(raw)));
  };
  const toX = (minute: number): number => minuteToX(minute, size.width);

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

  const maxSide = Math.max(1, ...entries.map(([, m]) => Math.max(m.o, m.i)));
  // 分母扣掉 SUB_TOP_PAD:滿格那根不再頂到副圖上緣,頂端量刻度文字才有地方站(SC-8)
  const energyH = Math.max(1, size.height - SUB_TOP_PAD);
  const energyBars = entries.map(([minute, m]) => ({
    x: toX(minute),
    outer: m.o,
    inner: m.i,
    outerH: (m.o / maxSide) * energyH,
    innerH: (m.i / maxSide) * energyH,
  }));

  const yTicks: YTick[] = [];
  if (upper !== null && lower !== null && ref > 0) {
    // SC-4:由上而下 +10/+8/…/0/…/−8/−10%。端點與中央用原值,其餘 snap 到合法 tick。
    // 去重:低價股 tick 粗時相鄰檔位會 snap 到同價,重複的 priceMilli 會撞 React key。
    const seen = new Set<number>();
    for (const pct of TICK_PCTS) {
      const p =
        pct === 10 ? upper : pct === -10 ? lower : pct === 0 ? ref : snapDown(Math.round(ref * (1 + pct / 100)));
      // 域外的中間刻度直接跳過:±10% 取的是 upper/lower 原值,±2/4/6/8% 卻是拿 ref 獨立
      // 算的,兩者沒互相校驗。漲跌幅不是 ±10% 的商品(槓桿型 ETF ±20%,或任何比 ±10% 窄的)
      // 會讓公式算出的刻度落在 [lower, upper] 之外 → toY 變負、刻度視覺次序反轉。
      if (p < yBottom || p > yTop) continue;
      if (seen.has(p)) continue;
      seen.add(p);
      yTicks.push({ y: toY(p), priceMilli: p });
    }
  } else {
    for (const p of [yTop, ref, yBottom]) {
      yTicks.push({ y: toY(p), priceMilli: Math.round(p) });
    }
  }

  const haveMinutes = new Set(entries.map(([k]) => k));
  const minuteOf = (xPx: number): number | null => {
    // 價位帶內(x < Y_AXIS_W)不對應任何分鐘 —— 不夾制成 09:00,否則滑過左緣價位文字時
    // 十字線會憑空指到開盤那一分鐘。必須與 `minuteToX` 共用 Y_AXIS_W / plotWidth,
    // 各自硬編會讓反演只在兩端偏移(同 toY / priceAtY 的教訓)。
    // 上界用 `Y_AXIS_W + plotWidth(width)` 不是 `width`:正常寬度下兩者相等,但退化寬度
    // (width ≤ Y_AXIS_W,plotWidth 被 clamp 成 1)時 minuteToX 最大會回 Y_AXIS_W + 1
    // 而超過 width,用 width 當上界就會把自己算出來的座標判成域外 → 兩者不再互逆。
    if (xPx < Y_AXIS_W || xPx > Y_AXIS_W + plotWidth(size.width)) return null;
    const m =
      Math.round(((xPx - Y_AXIS_W) / plotWidth(size.width)) * (X_END_MIN - X_START_MIN)) +
      X_START_MIN;
    return haveMinutes.has(m) ? m : null;
  };

  // 「真的有昨收」才有平盤可言 —— ref 的 fallback 是首筆成交價,拿它當平盤畫紅綠填色
  // 會把「開盤後漲跌」誤指為「相對昨收漲跌」(SC-2.4)。
  const hasRef = (input.meta?.ref ?? 0) > 0;
  const refY = toY(ref);
  const areaPolygon =
    hasRef && priceLine.length > 0
      ? [
          `${priceLine[0]!.x.toFixed(1)},${refY.toFixed(1)}`,
          ...priceLine.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`),
          `${priceLine[priceLine.length - 1]!.x.toFixed(1)},${refY.toFixed(1)}`,
        ].join(" ")
      : "";

  return {
    priceLine,
    vwapLine,
    refY,
    hasRef,
    areaPolygon,
    upperY: upper != null && upper <= yTop ? toY(upper) : null,
    lowerY: lower != null && lower >= yBottom ? toY(lower) : null,
    yDomain: [yBottom, yTop],
    yTicks,
    energyBars,
    maxSide,
    toY,
    priceAtY,
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
  const push = (p: number | null | undefined, level: OverlayLevel, kind: OverlayLine["kind"]): void => {
    if (p == null || p < yBottom || p > yTop) return;
    lines.push({ y: g.toY(p), priceMilli: p, level, kind });
  };
  if (toggles.cdp && overlay.cdp) {
    // 順序 = 由上而下,元件的配色表依賴這個語意(SC-2:名稱移除後靠顏色區分)
    push(overlay.cdp.ah, "ah", "cdp");
    push(overlay.cdp.nh, "nh", "cdp");
    push(overlay.cdp.cdp, "cdp", "cdp");
    push(overlay.cdp.nl, "nl", "cdp");
    push(overlay.cdp.al, "al", "cdp");
  }
  if (toggles.ma) {
    push(overlay.ma5, "ma5", "ma");
    push(overlay.ma20, "ma20", "ma");
  }
  return lines;
}
