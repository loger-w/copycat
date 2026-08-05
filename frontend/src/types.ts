export type SnapshotStatus =
  | "connecting"
  | "backfilling"
  | "live"
  | "reconnecting"
  | "disconnected"
  | "degraded"
  | "replay";

export interface SnapshotTotals {
  call_net_qty: number;
  put_net_qty: number;
  contracts_active: number;
  ticks: number;
  unclassified_ticks: number;
  unclassified_qty: number;
  overlap_risk_ticks: number;
  dropped_foreign_ticks: number;
  queue_dropped: number;
}

export interface ContractRow {
  symbol: string;
  cp: "C" | "P";
  strike: number;
  net_qty: number;
  volume: number;
  outer_qty: number;
  inner_qty: number;
  /** 最近成交價(點;snapshot 契約只加不改)。缺值時 OrderPanel 鎖市價選項。 */
  last_price?: number | null;
}

export interface Snapshot {
  series_id: string | null;
  series_name?: string;
  status: SnapshotStatus | string;
  accumulated_from?: string;
  generated_at?: string;
  spot?: { symbol: string; price: number | null };
  curve: [number, number][];
  beps?: number[];
  max_profit?: { x: number; y: number } | null;
  max_loss?: { x: number; y: number } | null;
  spot_pnl?: number | null;
  contracts?: ContractRow[];
  totals?: SnapshotTotals;
}

export interface SeriesItem {
  series_id: string;
  name: string;
  expiry: string;
}

// ---- capital(群益;對應 backend copycat/capital/models.py + client.status_view)----

/** GET /api/capital/status;未啟用時只有 {status:"disabled"},其餘欄位 optional。 */
export interface CapitalStatus {
  status: "starting" | "ok" | "degraded" | "error" | "disabled" | (string & {});
  env?: string;
  account_masked?: string | null;
  futures_account_masked?: string | null;
  order_enabled?: boolean;
}

/** OrderRecord asdict(委託清單一列;qty 已換算顯示單位)。 */
export interface CapitalOrder {
  seq_no: string;
  stock_no: string | null;
  name: string;
  market: string | null;
  buy_sell: string | null; // "B"/"S"
  flag_label: string | null;
  book_no: string | null;
  status_raw: string | null;
  status_label: string | null;
  price: number | null;
  avg_fill_price: number | null;
  order_qty: number;
  filled_qty: number;
  unit: string;
  date: string | null; // YYYYMMDD
  time: string | null; // HH:MM:SS
  pre_order: boolean;
  error_msg: string | null;
  actionable: boolean; // store 算好;前端不要自己抄狀態表
  raw: string;
}

/** 即時庫存種類(平倉可指定的值域)。後端 PositionKind 同字彙。 */
export type PositionKind = "cash" | "margin" | "short";

/** Position asdict(sec=股號;fut=期交所契約碼;空方 qty 為負)。 */
export interface CapitalPosition {
  market: string; // sec/fut
  stock_no: string;
  qty: number;
  name: string;
  avg_price: number | null;
  // 後端 Position.kind 值域是 TradeKind(另含 daytrade_sell 無券空單),比 PositionKind 寬
  kind: string;
  pnl_base: number | null;
  pnl_base_price: number | null;
  pnl_cost: number | null;
}

/** OrderResult asdict(寫入動作共同回傳形)。 */
export interface OrderResult {
  ok: boolean;
  code: number;
  message: string;
  seq_no: string | null;
}

export type CapitalMarket = "sec" | "fut";

export interface CapitalStockOrderBody {
  stock_no: string;
  buy_sell: "buy" | "sell";
  price: number;
  qty: number; // 張
  price_type?: "limit" | "market";
  time_in_force?: "ROD" | "IOC" | "FOK";
  trade_kind?: "cash" | "margin" | "short" | "daytrade_sell";
  source?: string;
}

export interface CapitalFutureOrderBody {
  tc4_symbol: string;
  buy_sell: "buy" | "sell";
  price: number;
  qty: number; // 口
  price_type?: "limit" | "market";
  time_in_force?: "ROD" | "IOC" | "FOK";
  day_trade?: boolean;
  source?: string;
}

export interface CapitalCancelBody {
  seq_no: string;
  market: CapitalMarket;
}

export interface CapitalCorrectPriceBody {
  seq_no: string;
  market: CapitalMarket;
  price: number;
}

export interface CapitalDecreaseBody {
  seq_no: string;
  market: CapitalMarket;
  qty: number;
}

export interface CapitalCloseBody {
  market: CapitalMarket;
  key: string;
  price: number; // 市價單也必帶(閘用估價)
  qty?: number | null; // null=全部
  price_type?: "limit" | "market";
  source?: string;
  /** sec 庫存種類 — 同檔資+集保並存時的第二把鍵(未帶且多列 → 後端阻擋);fut 不送。 */
  kind?: PositionKind;
}

// ---- futures 行情(對應 copycat/server/futures_engine.py state())----

export interface FuturesProductState {
  product: string; // TXF/MXF/TMF
  name: string;
  p: number | null; // 毫點
  q: number | null;
  cum_vol: number | null;
  t: string | null;
  date: string | null;
  bids: [number, number][]; // [price_milli, qty] 最佳在前
  asks: [number, number][];
  ref: number | null;
  upper: number | null;
  lower: number | null;
  resolved_contract: string | null; // HOT → YYYYMM;null=未解析(送單層拒單)
}

export interface FuturesState {
  seq: number;
  products: Record<string, FuturesProductState>;
}

/** 相關係數面板(realtime-correlation SC-6/7)。 */
export interface CorrLegState {
  label: string; // 繁中顯示名(後端帶,前端不寫死對照表)
  mid: number | null; // 毫點中價;stale 或無報價 → null
  stale: boolean;
}

/** 一條腿對 base 的各窗結果:`w<秒>` = 相關係數(樣本不足/常數序列 → null)、`n<秒>` = 樣本數。 */
export type CorrPairState = Record<string, number | null>;

export interface CorrState {
  type: string; // "corr"
  seq: number;
  session: string; // "day" | "night"
  base: string; // 基準腿 key(其餘各腿與它配對)
  windows: number[]; // 秒;前端據此產欄,後端改設定時自動跟上
  legs: Record<string, CorrLegState>;
  pairs: Record<string, CorrPairState>;
}

// ---- 六腿江波圖(對應 copycat/live/river_state.py;index-river-chart)----

/** 當場盤別的 x 軸窗(台北 minute-of-day;夜盤 end_min > 1440 = 跨午夜展開)。 */
export interface RiverWindow {
  start_min: number;
  end_min: number;
}

/** 一條腿的分鐘序列。`minutes` 鍵是窗內 offset,但 **JSON 物件鍵恆為字串** → 幾何層 Number(k)。 */
export interface RiverLeg {
  label: string; // 繁中顯示名(後端帶)
  minutes: Record<string, number>; // offset → 該分鐘收盤毫點
  last: number | null; // 最大 offset 的價;本場無資料 → null
  last_minute: number | null;
}

export interface RiverState {
  type: string; // "river"
  seq: number;
  session: string; // "day" | "night"
  base: string; // 基準腿 key(重疊圖畫粗線)
  window: RiverWindow;
  legs: Record<string, RiverLeg>;
}

/** 每秒增量:各腿最後寫入的那一分鐘;該腿本場尚無 live 點 → null。 */
export interface RiverDelta {
  type: string; // "river_delta"
  seq: number;
  session: string;
  window: RiverWindow;
  legs: Record<string, { m: number; p: number } | null>;
}
