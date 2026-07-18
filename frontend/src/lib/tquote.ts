/** T 字報價籌碼表純計算(無 React 依賴;design.md §3.2)。 */
import type { ContractRow } from "@/types";

export interface TQuoteRow {
  strike: number;
  call: ContractRow | null;
  put: ContractRow | null;
}

/** 依 strike 配對 C/P;任一側 volume > 0 才入列;降冪排列(高履約價在上)。 */
export function buildTQuoteRows(contracts: ContractRow[]): TQuoteRow[] {
  const byStrike = new Map<number, { call: ContractRow | null; put: ContractRow | null }>();
  for (const c of contracts) {
    const entry = byStrike.get(c.strike) ?? { call: null, put: null };
    if (c.cp === "C") entry.call = c;
    else entry.put = c;
    byStrike.set(c.strike, entry);
  }
  return [...byStrike.entries()]
    .filter(([, e]) => (e.call?.volume ?? 0) > 0 || (e.put?.volume ?? 0) > 0)
    .sort(([a], [b]) => b - a)
    .map(([strike, e]) => ({ strike, call: e.call, put: e.put }));
}

/** 外盤 /(外盤+內盤);分母 0 → null(全未分類,顯示 —)。 */
export function outerRatio(row: ContractRow): number | null {
  const classified = row.outer_qty + row.inner_qty;
  if (classified === 0) return null;
  return row.outer_qty / classified;
}

/** 全表兩側 |net_qty| 最大值(能量條正規化分母);全空 → 0。 */
export function maxAbsNetQty(rows: TQuoteRow[]): number {
  let max = 0;
  for (const r of rows) {
    for (const side of [r.call, r.put]) {
      if (side !== null) max = Math.max(max, Math.abs(side.net_qty));
    }
  }
  return max;
}

/** |netQty|/maxAbs ∈ [0,1];maxAbs === 0 → null(不畫條)。 */
export function energyWidth(netQty: number, maxAbs: number): number | null {
  if (maxAbs === 0) return null;
  return Math.abs(netQty) / maxAbs;
}

/**
 * ATM 分隔線位置:rows 降冪,spot 介於 rows[i].strike 與 rows[i+1].strike
 * 之間的第一個 i(邊界含);spot null / 範圍外 / 列數不足 → null(DR-8)。
 */
export function atmBoundaryIndex(rows: TQuoteRow[], spotPts: number | null): number | null {
  if (spotPts === null || rows.length < 2) return null;
  for (let i = 0; i < rows.length - 1; i++) {
    const upper = rows[i];
    const lower = rows[i + 1];
    if (upper !== undefined && lower !== undefined) {
      if (upper.strike >= spotPts && spotPts >= lower.strike) return i;
    }
  }
  return null;
}
