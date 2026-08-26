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
import type { AvgSource, CapitalPosition } from "@/types";

/** 牌告手續費率(買賣各收一次)。 */
export const FEE_BASE = 0.001425;
/** 證交稅(賣出價金 0.3%)。 */
export const SELL_TAX = 0.003;
/** 現股當沖證交稅(減半 0.15%;2026-08-26 user 拍板:今天成交進來的張數用這個,過往庫存 0.3%)。 */
export const SELL_TAX_DAYTRADE = 0.0015;
/** 融券借券費(賣出價金 0.08%;只有 kind === "short" 計入)。 */
export const SHORT_BORROW = 0.0008;
/** 預設手續費折數(user 實答:1.8 折)。 */
export const FEE_DISCOUNT_DEFAULT = 1.8;

/** 折數 → 實際費率。1.8 折 = 牌告 ×0.18。 */
export function feeRate(discount: number): number {
  return (FEE_BASE * discount) / 10;
}

export interface PositionEconInput {
  /** broker = 均價已含買進手續費(群益損益試算口徑);fill = 純成交價,要再加買費;
   *  null = 來源未知 → 走修前口徑(當純價加買費),明確分支不吞進 else。 */
  avgSource: AvgSource | null;
  /** 今天成交淨進來的張數;現股(kind === "cash")這一段賣出稅用 `SELL_TAX_DAYTRADE`。
   *  後端已 clamp 到 [0, |qty|],這裡**再 clamp 一次是刻意的防禦**:wire 漂了(或缺欄)也不能
   *  把有效稅率壓成負 / NaN —— 兩側都留,別把任一側當贅碼刪掉。 */
  todayQty: number;
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
 * f = feeRate(discount);b = kind === "short" ? SHORT_BORROW : 0;Q = |qty| × 1000 股。
 * t = 有效賣出稅率:現股今天進來的 T 張用 SELL_TAX_DAYTRADE、其餘 SELL_TAX,按張數加權
 *   t = (T·0.0015 + (|qty| − T)·0.003) / |qty|(T clamp 到 [0, |qty|];非現股 T 視為 0;現股**空方**
 *   (無券當沖先賣後買)T = 今日淨賣出,同樣減半 —— 法規上也是現股當沖)。
 * cost = 含買進手續費的每股成本:avgSource === "broker" 時 avg 本身就是(群益損益試算
 *   「平均買進成本」含買費,2026-08-26 prod 實證);"fill" 時 = avg·(1 + f)。
 *
 * - 多方(qty > 0,b 恆 0 — 多方無借券):
 *   pnl = (px − cost)·Q − px·Q·(f + t);BE = cost / (1 − f − t)
 *   ("fill" 展開即舊式 avg·(1 + f) / (1 − f − t);"broker" 少乘一次 (1 + f) —— 舊寫法把券商
 *   均價當純價再加買費,損益比群益 APP 少一筆買費、打平線在快照落地時跳一格)
 * - 空方(qty < 0):
 *   pnl = (avg − px)·Q − avg·Q·(f + t + b) − px·Q·f;BE = avg·(1 − f − t − b) / (1 + f)
 *   (空方均價語意無真樣本,沿舊式當純價;融券 kind 恆 0.3%)
 *
 * qty = 0 → 全 null(不是部位)。已知簡化:不套低消 NT$20(聚合部位無筆數可還原)、
 * 不計融資利息;群益 APP 損益試算**不做**當沖減半,今天進來的張數我們會比 APP 多顯示減半的稅。
 */
export function positionEcon(
  qty: number,
  avgPrice: number | null,
  lastMilli: number | null,
  discount: number,
  kind: string,
  input: PositionEconInput,
): PositionEcon {
  // 「0 不是部位」—— 與 px() 的歸一同一條精神。零張的部位算出來的 pnl 是 -0、
  // 打平價卻是個像模像樣的數字,兩者都在騙人
  if (qty === 0) return { pnl: null, breakEvenMilli: null };
  const avg = px(avgPrice);
  if (avg === null) return { pnl: null, breakEvenMilli: null };

  const f = feeRate(discount);
  const lots = Math.abs(qty);
  // 後端未重啟的窗口 payload 沒有 today_qty → undefined 進 Math.max 變 NaN,整條算式毒化印「NaN」;
  // 缺欄退成 0(= 舊口徑 0.3%),與 avg_source 缺欄退成 fill 同一個方向:退回修前行為,不退成假數字
  const todayRaw = Number.isFinite(input.todayQty) ? input.todayQty : 0;
  const todayLots = kind === "cash" ? Math.min(lots, Math.max(0, todayRaw)) : 0;
  const t = (todayLots * SELL_TAX_DAYTRADE + (lots - todayLots) * SELL_TAX) / lots;
  const b = kind === "short" ? SHORT_BORROW : 0;
  const long = qty > 0;
  const q = lots * 1000;
  // 含買進手續費的每股成本:券商均價已含;純成交價要加;來源未知(null)明確走修前口徑
  let cost: number;
  switch (input.avgSource) {
    case "broker":
      cost = avg;
      break;
    case "fill":
    case null:
      cost = avg * (1 + f);
      break;
  }

  const breakEven = long ? cost / (1 - f - t) : (avg * (1 - f - t - b)) / (1 + f);
  const breakEvenMilli = breakEven * 1000;

  const lastPrice = px(lastMilli);
  if (lastPrice === null) return { pnl: null, breakEvenMilli };
  const p = lastPrice / 1000;

  const pnl = long
    ? (p - cost) * q - p * q * (f + t)
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
