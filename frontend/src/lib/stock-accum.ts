/** 個股前端累算:snapshot 為基底 + tick 增量(design v4 §4;與後端 StockDayState 等值)。 */

export interface StockTickMsg {
  type: "tick";
  code: string;
  t: string; // 台北 HH:MM:SS.fff
  p: number; // 毫元
  q: number;
  side: "outer" | "inner" | "neutral";
  seq: number;
  /** 成交當下最佳買賣價;缺欄位(舊後端)一律當 null */
  b?: number | null;
  a?: number | null;
  /** 當日高低(毫元)。掛在 tick 而不是另立 meta 訊息型別:engine 只發
   *  tick / book / watchlist_quote 三種,而當日高低本來就只在成交時才會變 */
  h?: number | null;
  l?: number | null;
}

export interface MinuteAgg {
  c: number;
  v: number;
  i: number;
  o: number;
  u: number;
  /** 分鐘內高 / 低(round4 項 1;與後端 `MinuteAgg.high_milli/low_milli` 等值)。
   *
   *  **選填且 `null` 有意義** —— `null` = 「這一分鐘的高低不可知」(舊後端 snapshot 沒給),
   *  不是「等於收盤價」。拿 `c` 頂替會讓分時圖的等值反查(`minute.h === accum.high`)
   *  命中錯的分鐘 → 標記畫在錯的時間點,而且完全靜默。 */
  h?: number | null;
  l?: number | null;
}

export interface TickRow {
  t: string;
  p: number;
  q: number;
  side: string;
  /** 成交當下最佳買 / 賣價(毫元);**選填** —— 舊 snapshot 與既有測試 fixture 都沒有 */
  b?: number | null;
  a?: number | null;
}

export interface StockMeta {
  name: string;
  ref: number | null;
  upper: number | null;
  lower: number | null;
  y_close: number | null;
  y_vol: number | null;
}

export interface StockBook {
  bids: [number, number][];
  asks: [number, number][];
}

export interface StockAccum {
  code: string;
  seq: number;
  last: { p: number; t: string; cum_vol: number } | null;
  vwap: number | null;
  minutes: Map<number, MinuteAgg>;
  ticks: TickRow[];
  book: StockBook | null;
  meta: StockMeta | null;
  noData: boolean;
  tc4: string;
  backfilling: string | null;
  stkfutProd: string | null;
  /** 當日最高 / 最低成交價(毫元,後端 running max/min)。**top-level 不掛 meta** ——
   *  meta 是 TC4 來的靜態盤別資料,把「由成交推導的當日狀態」塞進去語意錯位,
   *  而且只跑過回補、未收 REALTIME 時 meta 為 null,高低照樣要有值 */
  high: number | null;
  low: number | null;
  /** VWAP 內部分子(毫元 × 張);由 vwap × 總量還原後續算 */
  amountMilli: number;
  volume: number;
}

const TAPE_MAX = 200;

export function minuteKey(t: string): number {
  return Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
}

interface SnapshotShape {
  code?: string;
  seq: number;
  last: { p: number; t: string; cum_vol: number } | null;
  vwap: number | null;
  minutes: Record<string, MinuteAgg>;
  ticks: TickRow[];
  book: StockBook | null;
  meta: StockMeta | null;
  high?: number | null;
  low?: number | null;
  no_data?: boolean;
  tc4?: string;
  backfilling?: string | null;
  stkfut_prod?: string | null;
}

export function fromSnapshot(snap: SnapshotShape): StockAccum {
  const minutes = new Map<number, MinuteAgg>();
  for (const [k, v] of Object.entries(snap.minutes ?? {})) {
    minutes.set(Number(k), { ...v, h: v.h ?? null, l: v.l ?? null });
  }
  const volume = snap.last?.cum_vol ?? 0;
  return {
    code: snap.code ?? "",
    seq: snap.seq,
    last: snap.last,
    vwap: snap.vwap,
    minutes,
    ticks: [...(snap.ticks ?? [])].slice(-TAPE_MAX),
    book: snap.book,
    meta: snap.meta,
    high: snap.high ?? null,
    low: snap.low ?? null,
    noData: snap.no_data ?? false,
    tc4: snap.tc4 ?? "up",
    backfilling: snap.backfilling ?? null,
    stkfutProd: snap.stkfut_prod ?? null,
    amountMilli: snap.vwap != null ? snap.vwap * volume : 0,
    volume,
  };
}

export function applyTick(acc: StockAccum, msg: StockTickMsg): StockAccum {
  const key = minuteKey(msg.t);
  const minutes = new Map(acc.minutes);
  const prev = minutes.get(key) ?? { c: 0, v: 0, i: 0, o: 0, u: 0 };
  // 分鐘高低三條路徑:新分鐘(v=0)→ 本筆;已知高低 → max/min;
  // **高低不可知(舊 snapshot:h 為 null 但已有量)→ 維持 null** ——
  // 只用「本次載入後看到的 tick」算出來的極值不是整分鐘的極值,不可冒充。
  const unknown = prev.v > 0 && prev.h == null;
  const agg: MinuteAgg = {
    c: msg.p,
    v: prev.v + msg.q,
    i: prev.i + (msg.side === "inner" ? msg.q : 0),
    o: prev.o + (msg.side === "outer" ? msg.q : 0),
    u: prev.u + (msg.side === "neutral" ? msg.q : 0),
    h: unknown ? null : Math.max(prev.h ?? msg.p, msg.p),
    l: unknown ? null : Math.min(prev.l ?? msg.p, msg.p),
  };
  minutes.set(key, agg);
  const amountMilli = acc.amountMilli + msg.p * msg.q;
  const volume = acc.volume + msg.q;
  const ticks = [
    ...acc.ticks,
    { t: msg.t, p: msg.p, q: msg.q, side: msg.side, b: msg.b ?? null, a: msg.a ?? null },
  ].slice(-TAPE_MAX);
  return {
    ...acc,
    seq: msg.seq,
    last: { p: msg.p, t: msg.t, cum_vol: (acc.last?.cum_vol ?? acc.volume) + msg.q },
    vwap: volume > 0 ? Math.round(amountMilli / volume) : null,
    minutes,
    ticks,
    // 缺欄位 → 保留原值(舊後端不發 h/l 時,線不該閃掉)
    high: msg.h ?? acc.high,
    low: msg.l ?? acc.low,
    amountMilli,
    volume,
  };
}
