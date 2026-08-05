/** 閃電梯部位經濟:未實現損益 + 含成本打平價(零 React 純函數)。
 *
 *  **為什麼前端自算**:群益 `CapitalPosition.pnl_*` 是名目損益(不含費稅),而閃電梯上
 *  真正要回答的問題是「現在平掉,含手續費與證交稅之後我是賺是賠」。口徑與折數都在這裡
 *  收斂,元件只負責顯示。
 *
 *  單位約定:`avgPrice` 是**元**(群益 `avg_price` 原樣),`lastMilli` / 回傳的
 *  `breakEvenMilli` 是**毫元**(本專案價格通貨)。qty 是**張**(1 張 = 1000 股),
 *  費用一律以 `|qty|` 計、方向只由 qty 符號決定。 */
import { snapDown, snapNearest, snapUp } from "@/lib/stock-tick";
import type { CapitalPosition } from "@/types";

/** 牌告手續費率(買賣各收一次)。 */
export const FEE_BASE = 0.001425;
/** 證交稅(賣出價金;user 拍板固定 0.3%,不分現股 / 當沖減半)。 */
export const SELL_TAX = 0.003;
/** 融券借券費(賣出價金 0.08%;只有 kind === "short" 計入)。 */
export const SHORT_BORROW = 0.0008;
/** 預設手續費折數(user 實答:1.8 折)。 */
export const FEE_DISCOUNT_DEFAULT = 1.8;

/** 折數 → 實際費率。1.8 折 = 牌告 ×0.18。 */
export function feeRate(discount: number): number {
  return (FEE_BASE * discount) / 10;
}

export interface PositionEcon {
  /** 未實現損益(元,四捨五入到整數);avg 或 last 缺值 → null。 */
  pnl: number | null;
  /** 含成本打平價(毫元,**未 snap**);avg 缺值 → null。 */
  breakEvenMilli: number | null;
}

/** 價格欄的 `0` 不是價格(同 `stock-tick::isMarketLevel` 與後端 `_best_limit_price`),
 *  均價欄的 0 / 負值同理視為缺值 —— 拿去算會得到「打平價 0」這種看起來像數字的假答案。 */
function px(v: number | null): number | null {
  return v !== null && v > 0 ? v : null;
}

/**
 * 部位經濟。
 *
 * f = feeRate(discount);t = SELL_TAX;b = kind === "short" ? SHORT_BORROW : 0;
 * Q = |qty| × 1000 股。
 *
 * - 多方(qty > 0,b 恆 0 — 多方無借券):
 *   pnl = (px − avg)·Q − avg·Q·f − px·Q·(f + t);BE = avg·(1 + f) / (1 − f − t)
 * - 空方(qty < 0):
 *   pnl = (avg − px)·Q − avg·Q·(f + t + b) − px·Q·f;BE = avg·(1 − f − t − b) / (1 + f)
 *
 * 已知簡化:不套低消 NT$20(聚合部位無筆數可還原)、不計融資利息。
 */
export function positionEcon(
  qty: number,
  avgPrice: number | null,
  lastMilli: number | null,
  discount: number,
  kind: string,
): PositionEcon {
  const avg = px(avgPrice);
  if (avg === null) return { pnl: null, breakEvenMilli: null };

  const f = feeRate(discount);
  const t = SELL_TAX;
  const b = kind === "short" ? SHORT_BORROW : 0;
  const long = qty > 0;
  const q = Math.abs(qty) * 1000;

  const breakEven = long ? (avg * (1 + f)) / (1 - f - t) : (avg * (1 - f - t - b)) / (1 + f);
  const breakEvenMilli = breakEven * 1000;

  const lastPrice = px(lastMilli);
  if (lastPrice === null) return { pnl: null, breakEvenMilli };
  const p = lastPrice / 1000;

  const pnl = long
    ? (p - avg) * q - avg * q * f - p * q * (f + t)
    : (avg - p) * q - avg * q * (f + t + b) - p * q * f;
  return { pnl: Math.round(pnl), breakEvenMilli };
}

/** 打平價 snap 到合法檔位:多方 snapUp(第一個真獲利的 tick)、空方 snapDown。
 *  方向刻意保守 —— 往「還沒打平」那側取,不讓標記騙人。 */
export function snapBreakEven(beMilli: number, qty: number): number {
  return qty > 0 ? snapUp(beMilli) : snapDown(beMilli);
}

/** 均價標記所在的檔位(毫元)。均價是成交均值,幾乎不會剛好落在合法檔位上 →
 *  取最近檔位。**標記 key 的單一定義處**,元件不自算(兩處各算會靜默錯位)。 */
export function avgTickOf(avgPrice: number): number {
  return snapNearest(Math.round(avgPrice * 1000));
}

/** 折數夾制:收 string(受控輸入的原始值)或 number,0 < v ≤ 10 才是合法折數。
 *  不合法回 null,由呼叫端決定沿用舊值還是套預設 —— 不在這裡替它決定。 */
export function clampDiscount(raw: string | number): number | null {
  const v = typeof raw === "number" ? raw : Number.parseFloat(raw);
  if (!Number.isFinite(v)) return null;
  if (v <= 0 || v > 10) return null;
  return v;
}

/** 顯示順序:cash → margin → short → 其餘(含 daytrade_sell 與未知字串)殿後。 */
const KIND_ORDER: Record<string, number> = { cash: 0, margin: 1, short: 2 };

/** 當前標的的證券部位列(sec / 同股號 / qty ≠ 0),依 KIND_ORDER 排序。 */
export function secPositionsOf(
  positions: CapitalPosition[] | undefined,
  code: string,
): CapitalPosition[] {
  return (positions ?? [])
    .filter((p) => p.market === "sec" && p.stock_no === code && p.qty !== 0)
    .sort((a, b) => (KIND_ORDER[a.kind] ?? 3) - (KIND_ORDER[b.kind] ?? 3));
}
