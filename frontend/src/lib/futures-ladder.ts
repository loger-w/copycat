/** 期貨閃電梯列建構(毫點整數運算;台指期 tick 固定 1 點 = 1000 毫點)。
 *
 * 純函式無 React — 元件只負責渲染(對齊 stock-tick.ts / treading-king flash-ladder 慣例)。
 * 與個股 buildLadder(固定界全域 rows)不同:期貨漲跌停帶 ±10% 全鋪是數千列,
 * 改以 center 置中、上下各 rows 檔、漲跌停夾界截斷。
 */
export const FUT_TICK_MILLI = 1_000;
const CLICK_BAND = 0.05; // 離現價 ±5% 內才可點(fat-finger 灰區,treading-king 同值)

export interface FutDepthLevel {
  priceMilli: number;
  qty: number;
}

/** 我方同價位活單聚合(splitMyLots 產物) */
export interface MyFutLot {
  priceMilli: number;
  qty: number;
  seqNos: string[];
}

export interface FutLadderRow {
  priceMilli: number;
  bidQty: number;
  askQty: number;
  myQty: number;
  mySeqNos: string[];
  isCenter: boolean;
  clickable: boolean;
}

/** CapitalOrder 的結構子集 — lib 不 import api 型別,保持零依賴可測 */
export interface FutOrderSource {
  seq_no: string;
  stock_no: string | null; // 期貨回報放期交所契約碼(如 TXFI6)
  buy_sell: string | null;
  price: number | null; // 點(float);市價單無價不上階梯
  order_qty: number;
  filled_qty: number;
  actionable: boolean;
}

/** 該契約 actionable 活單(殘量 > 0)按價位聚合;價 float → 毫點 round。 */
export function splitMyLots(
  orders: ReadonlyArray<FutOrderSource>,
  contract: string,
): MyFutLot[] {
  const byPrice = new Map<number, { qty: number; seqNos: string[] }>();
  for (const o of orders) {
    if (o.stock_no !== contract || !o.actionable || o.price == null) continue;
    const remaining = o.order_qty - o.filled_qty;
    if (remaining <= 0) continue;
    const priceMilli = Math.round(o.price * 1000);
    const cur = byPrice.get(priceMilli);
    if (cur) {
      cur.qty += remaining;
      cur.seqNos.push(o.seq_no);
    } else {
      byPrice.set(priceMilli, { qty: remaining, seqNos: [o.seq_no] });
    }
  }
  return [...byPrice.entries()]
    .map(([priceMilli, v]) => ({ priceMilli, qty: v.qty, seqNos: v.seqNos }))
    .sort((a, b) => b.priceMilli - a.priceMilli);
}

export function buildFuturesLadder(opts: {
  centerMilli: number;
  upperMilli: number;
  lowerMilli: number;
  bids: ReadonlyArray<FutDepthLevel>;
  asks: ReadonlyArray<FutDepthLevel>;
  myLots: ReadonlyArray<MyFutLot>;
  rows?: number;
}): FutLadderRow[] {
  const half = opts.rows ?? 60;
  const upper = Math.floor(opts.upperMilli / FUT_TICK_MILLI) * FUT_TICK_MILLI;
  const lower = Math.ceil(opts.lowerMilli / FUT_TICK_MILLI) * FUT_TICK_MILLI;
  if (upper < lower) return [];

  // center snap down 到合法檔位、clamp 進界內
  const snapped = Math.floor(opts.centerMilli / FUT_TICK_MILLI) * FUT_TICK_MILLI;
  const c = Math.min(Math.max(snapped, lower), upper);

  const prices: number[] = [c];
  for (let p = c + FUT_TICK_MILLI, i = 0; i < half && p <= upper; i++, p += FUT_TICK_MILLI) {
    prices.unshift(p);
  }
  for (let p = c - FUT_TICK_MILLI, i = 0; i < half && p >= lower; i++, p -= FUT_TICK_MILLI) {
    prices.push(p);
  }

  const bidMap = new Map(opts.bids.map((b) => [b.priceMilli, b.qty]));
  const askMap = new Map(opts.asks.map((a) => [a.priceMilli, a.qty]));
  const lotMap = new Map(opts.myLots.map((l) => [l.priceMilli, l]));

  return prices.map((priceMilli) => ({
    priceMilli,
    bidQty: bidMap.get(priceMilli) ?? 0,
    askQty: askMap.get(priceMilli) ?? 0,
    myQty: lotMap.get(priceMilli)?.qty ?? 0,
    mySeqNos: lotMap.get(priceMilli)?.seqNos ?? [],
    isCenter: priceMilli === c,
    clickable: Math.abs(priceMilli - opts.centerMilli) <= opts.centerMilli * CLICK_BAND + 1e-9,
  }));
}
