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

/** 我方同價位聚合(splitMyLots 產物)。`qty` = 活單殘量、`filled` = 已成交量、
 *  `seqNos` = **活單** seq(全撤與點刪的唯一來源;filled-only 條目恆空)。
 *
 *  qty / filled 算式與 seq 收集規則和 `lib/ladder-lots.ts::aggregateLots` 一致 ——
 *  改一邊要改另一邊 —— 但有兩處刻意的差異:aggregateLots 分買賣側輸出兩張 map 且
 *  對 `buy_sell` 非 B/S 的單整筆跳過(連 seq 都不收);本函式不分側、也不看
 *  `buy_sell`(期貨梯是單一紅方格,spec auto-default 第 4 條)。 */
export interface MyFutLot {
  priceMilli: number;
  qty: number;
  filled: number;
  seqNos: string[];
}

export interface FutLadderRow {
  priceMilli: number;
  bidQty: number;
  askQty: number;
  myQty: number;
  myFilled: number;
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
  date: string | null; // 委託建立日 YYYYMMDD(已成交量的日期界)
}

/** 該契約的單按價位聚合(不分買賣側);價 float → 毫點 round。
 *
 *  `filledDates`:終態單的 `date` 落在集合內才計已成交量(store 跨日不清 → 無日期界
 *  會長出昨日幽靈徽章);**活單的成交恆計**。失敗 / 退單 filled_qty 恆 0 → 零痕跡。
 *  `seqNos` 只收 actionable 單 —— 全撤與點刪都靠它,filled 貢獻不得產生 seq。 */
export function splitMyLots(
  orders: ReadonlyArray<FutOrderSource>,
  contract: string,
  filledDates: ReadonlySet<string>,
): MyFutLot[] {
  const byPrice = new Map<number, { qty: number; filled: number; seqNos: string[] }>();
  for (const o of orders) {
    if (o.stock_no !== contract || o.price == null) continue;
    // 殘量 ≤ 0 不進 qty,但 seq 仍要收:actionable 且殘 0(N 未到)刪得掉
    const addQty = o.actionable ? Math.max(0, o.order_qty - o.filled_qty) : 0;
    const countFilled = o.actionable || (o.date !== null && filledDates.has(o.date));
    const addFilled = countFilled ? o.filled_qty : 0;
    if (!o.actionable && addFilled === 0) continue; // 不產生 entry
    const priceMilli = Math.round(o.price * 1000);
    const cur = byPrice.get(priceMilli) ?? { qty: 0, filled: 0, seqNos: [] };
    cur.qty += addQty;
    cur.filled += addFilled;
    if (o.actionable) cur.seqNos.push(o.seq_no);
    byPrice.set(priceMilli, cur);
  }
  return [...byPrice.entries()]
    .map(([priceMilli, v]) => ({
      priceMilli,
      qty: v.qty,
      filled: v.filled,
      seqNos: v.seqNos,
    }))
    .sort((a, b) => b.priceMilli - a.priceMilli);
}

/** 商品碼 + 解析月份 YYYYMM → 期交所契約碼(期貨月碼 A..L + 年末碼;backend mapping 同款)。 */
export function futExchangeContract(product: string, ym: string): string {
  const year = Number(ym.slice(0, 4));
  const month = Number(ym.slice(4, 6));
  if (!/^\d{6}$/.test(ym) || month < 1 || month > 12) {
    throw new Error(`invalid YYYYMM: ${ym}`);
  }
  return product + String.fromCharCode(65 + month - 1) + String(year % 10);
}

/** CapitalPosition 的結構子集(同 FutOrderSource,lib 不 import api 型別) */
export interface FutClosePos {
  stock_no: string;
  qty: number;
}

/** FuturesProductState 的結構子集(漲跌停) */
export interface FutCloseQuote {
  upper: number | null;
  lower: number | null;
}

/** 「貼漲跌停」的選邊(raw,不 snap 檔位):買 → 漲停、賣 → 跌停;缺界 → null。
 *  平倉估價與市價鈕邊價共用同一條選邊規則 —— 兩處各寫一次時,改一邊漏另一邊
 *  的症狀是「送到反方向的極端價」。snap 到合法檔位是各路徑自己的事(期貨 FUT_TICK /
 *  個股期現股 tick 表口徑不同),本函式只回原始界值。
 *
 *  **`≤ 0` 是缺值哨符,不是價**:後端界不可得時以 0 給,而 0 一路傳下去會變成
 *  「用 0 元送真錢單」——`null` / `0` / 負值三者一律回 null(與 `stkfutMarketEdgeMilli`
 *  同口徑),讓市價鈕與平倉鍵鎖住。 */
export function edgeMilli(
  side: "buy" | "sell",
  upper: number | null,
  lower: number | null,
): number | null {
  const raw = side === "buy" ? upper : lower;
  return raw === null || raw <= 0 ? null : raw;
}

/** 期貨「市價」鈕的送單價(毫點)—— 貼漲跌停 + IOC(D3a),不是真市價單。
 *
 *  邊價 floor / ceil 到 `FUT_TICK_MILLI`,與 `buildFuturesLadder` 的界截斷同口徑
 *  (:144-145):`state.upper` 不保證落在合法檔位,而期貨路徑後端**沒有** tick 閘 ——
 *  未對齊只會被券商退單,而那時使用者已經按下去了。兩側都往簿內收。
 *
 *  **snap 後再守一次 `≤ 0`**(review round-1 F1):`edgeMilli` 的哨符守門在 snap 之前,
 *  買側 floor 會把 `0 < upper < FUT_TICK` 的界壓成 0 —— 送出去就是「用 0 元下真錢單」。
 *  `futCloseEstimate` 回傳前本來就守 ≤0 → null,這裡不守的話同一份行情會出現
 *  「平倉鍵鎖住、市價鈕照樣可按」兩個矛盾的答案。 */
export function futMarketEdgeMilli(
  side: "buy" | "sell",
  upper: number | null,
  lower: number | null,
): number | null {
  const e = edgeMilli(side, upper, lower);
  if (e === null) return null;
  const s =
    side === "buy"
      ? Math.floor(e / FUT_TICK_MILLI) * FUT_TICK_MILLI
      : Math.ceil(e / FUT_TICK_MILLI) * FUT_TICK_MILLI;
  return s <= 0 ? null : s;
}

/** 平倉閘用估價(design amendment:期貨平倉限價貼漲跌停)——
 *  多單平倉(賣)用跌停價、空單平倉(買)用漲停價;單位元 = Milli/1000。
 *  只對「當前商品的 resolved 契約」有行情可估,其餘 null = 平倉鍵鎖住。
 *
 *  `edgeOf` = 該路徑的**邊價口徑**,預設期貨 FUT_TICK。注入而不是各寫一支:同一個
 *  標的的市價鈕與平倉估價必須同值,而個股期走的是股票 tick 表(RightRail 傳
 *  `stkfutMarketEdgeMilli`)—— raw 界未對齊檔位時後端 `_require_legal_tick` 直接 400。
 *  回傳前**自己再守一次 ≤ 0**:注入者是呼叫端寫的,不能假設它守門。 */
export function futCloseEstimate(
  pos: FutClosePos,
  contract: string | null,
  prod: FutCloseQuote | null,
  edgeOf: (side: "buy" | "sell", upper: number | null, lower: number | null) => number | null =
    futMarketEdgeMilli,
): number | null {
  if (contract === null || prod === null || pos.stock_no !== contract) return null;
  const edge = edgeOf(pos.qty > 0 ? "sell" : "buy", prod.upper, prod.lower);
  return edge === null || edge <= 0 ? null : edge / 1000;
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
    myFilled: lotMap.get(priceMilli)?.filled ?? 0,
    mySeqNos: lotMap.get(priceMilli)?.seqNos ?? [],
    isCenter: priceMilli === c,
    clickable: Math.abs(priceMilli - opts.centerMilli) <= opts.centerMilli * CLICK_BAND + 1e-9,
  }));
}
