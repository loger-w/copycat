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
