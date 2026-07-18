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
