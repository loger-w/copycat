import { useMemo } from "react";

import { formatPts } from "@/lib/format";
import {
  atmBoundaryIndex,
  buildTQuoteRows,
  energyWidth,
  maxAbsNetQty,
  outerRatio,
} from "@/lib/tquote";
import type { ContractRow } from "@/types";
import { cn } from "@/lib/utils";

const DASH = "—";

function ratioText(row: ContractRow): string {
  const r = outerRatio(row);
  return r === null ? DASH : `${Math.round(r * 100)}%`;
}

/** 內外盤比方向色:外盤佔優(≥60%)紅、內盤佔優(≤40%)綠,中性 muted。 */
function ratioTone(row: ContractRow): string {
  const r = outerRatio(row);
  if (r === null) return "text-ink-dim";
  if (r >= 0.6) return "text-bull";
  if (r <= 0.4) return "text-bear";
  return "text-ink-muted";
}

function EnergyBar({
  netQty,
  maxAbs,
  align,
}: {
  netQty: number;
  maxAbs: number;
  align: "left" | "right";
}) {
  const width = energyWidth(netQty, maxAbs);
  if (width === null || netQty === 0) return null;
  return (
    <div className={cn("flex h-2 w-full", align === "right" && "justify-end")} aria-hidden>
      <div
        className={cn("h-full rounded-xs", netQty > 0 ? "bg-bull" : "bg-bear")}
        style={{ width: `${Math.max(width * 100, 4)}%` }}
      />
    </div>
  );
}

/** 單側四欄:能量 / 內外盤比 / 成交量 / 淨部位(Call 側)或鏡像(Put 側)。 */
function SideCells({
  row,
  maxAbs,
  side,
  atm,
}: {
  row: ContractRow | null;
  maxAbs: number;
  side: "call" | "put";
  atm: boolean;
}) {
  const td = cn("px-2 py-1 font-mono text-xs", atm && "border-b border-accent");
  if (row === null) {
    return (
      <>
        {[0, 1, 2, 3].map((i) => (
          <td key={i} className={cn(td, "text-center text-ink-dim")}>
            {DASH}
          </td>
        ))}
      </>
    );
  }
  const netTone = row.net_qty > 0 ? "text-bull" : row.net_qty < 0 ? "text-bear" : "text-ink-muted";
  const cells = [
    <td key="energy" className={cn(td, "w-24 min-w-16 align-middle")}>
      <EnergyBar netQty={row.net_qty} maxAbs={maxAbs} align={side === "call" ? "right" : "left"} />
    </td>,
    <td key="ratio" className={cn(td, "text-right", ratioTone(row))}>
      {ratioText(row)}
    </td>,
    <td key="volume" className={cn(td, "text-right text-ink")}>
      {formatPts(row.volume)}
    </td>,
    <td key="net" className={cn(td, "text-right font-medium", netTone)}>
      {formatPts(row.net_qty)}
    </td>,
  ];
  // Call 側:能量|比|量|淨(靠履約價);Put 側鏡像:淨|量|比|能量
  return <>{side === "call" ? cells : [...cells].reverse()}</>;
}

export function QuoteTable({
  contracts,
  spotPrice,
}: {
  contracts: ContractRow[] | undefined;
  spotPrice: number | null;
}) {
  const rows = useMemo(() => buildTQuoteRows(contracts ?? []), [contracts]);

  if (rows.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center rounded-md border border-line bg-surface">
        <p className="text-sm text-ink-muted">尚無成交累積</p>
      </div>
    );
  }

  const maxAbs = maxAbsNetQty(rows);
  const atmIdx = atmBoundaryIndex(rows, spotPrice);

  return (
    <section className="rounded-md border border-line bg-surface p-4">
      <header className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-medium text-ink">T 字報價籌碼表</h2>
        <span className="font-mono text-xs text-ink-muted">
          Call 買權 ⟵ 履約價 ⟶ Put 賣權
        </span>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="text-ink-muted">
              <th className="px-2 py-1 text-left font-normal">能量</th>
              <th className="px-2 py-1 text-right font-normal">內外盤比</th>
              <th className="px-2 py-1 text-right font-normal">成交量</th>
              <th className="px-2 py-1 text-right font-normal">淨部位</th>
              <th className="px-2 py-1 text-center font-normal">履約價</th>
              <th className="px-2 py-1 text-right font-normal">淨部位</th>
              <th className="px-2 py-1 text-right font-normal">成交量</th>
              <th className="px-2 py-1 text-right font-normal">內外盤比</th>
              <th className="px-2 py-1 text-right font-normal">能量</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const atm = atmIdx === i;
              return (
                <tr key={row.strike} className="hover:bg-bg-deep/60">
                  <SideCells row={row.call} maxAbs={maxAbs} side="call" atm={atm} />
                  <td
                    className={cn(
                      "border-x border-x-line bg-bg-deep/50 px-3 py-1 text-center font-mono font-bold text-ink",
                      // side-specific 色避開 twMerge 全側 border-color conflict group(收尾 review P1)
                      atm && "border-b border-b-accent",
                    )}
                  >
                    {formatPts(row.strike)}
                  </td>
                  <SideCells row={row.put} maxAbs={maxAbs} side="put" atm={atm} />
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
