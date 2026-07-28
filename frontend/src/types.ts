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

// ---- trade(對應 backend copycat/server/trade.py 視圖) ----

export interface TradeAccount {
  status: "ready" | "touchance_down" | "no_account" | "live_blocked" | (string & {});
  mode: "sim" | "live" | null;
  account_masked: string | null;
  broker_id: string | null;
  audit_degraded: boolean;
  orderable_symbols: string[];
}

export interface OrderPreviewBody {
  symbol: string;
  side: "buy" | "sell";
  kind: "limit" | "market";
  qty: number;
  price: string | null;
}

export interface OrderPreviewResult {
  preview_id: string;
  request_id: string;
  param: Record<string, string>;
  account_masked: string;
  mode: "sim" | "live";
}

export interface SubmitResult {
  request_id: string;
  result: Record<string, unknown>;
}

export interface OrderRow {
  report_id: string;
  symbol: string;
  side: string;
  status_raw: string;
  price: string;
  qty: string;
  filled_qty: string;
  err_code: string | null;
  err_msg: string | null;
}

export interface OrdersView {
  orders: OrderRow[];
  fills: OrderRow[];
  degraded: boolean;
  audit_degraded: boolean;
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

/** Position asdict(sec=股號;fut=期交所契約碼;空方 qty 為負)。 */
export interface CapitalPosition {
  market: string; // sec/fut
  stock_no: string;
  qty: number;
  name: string;
  avg_price: number | null;
  kind: string; // cash/margin/short
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
