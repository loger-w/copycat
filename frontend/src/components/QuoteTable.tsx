import { useMemo } from "react";
import type { ReactElement } from "react";

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

/** net_qty 正負 → 多空色單一判定(text/bg 兩用;Bull=紅/Bear=綠 台股慣例)。 */
function netTone(netQty: number, kind: "text" | "bg"): string {
  if (netQty > 0) return kind === "text" ? "text-bull" : "bg-bull";
  if (netQty < 0) return kind === "text" ? "text-bear" : "bg-bear";
  return kind === "text" ? "text-ink-muted" : "";
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
        className={cn("h-full rounded-xs", netTone(netQty, "bg"))}
        style={{ width: `${Math.max(width * 100, 4)}%` }}
      />
    </div>
  );
}

type SideCellCtx = {
  row: ContractRow;
  maxAbs: number;
  side: "call" | "put";
  td: string;
};

/** T 字表單側欄定義(順序 = Call 側靠外 → 靠履約價;Put 側 reverse 鏡像)。
 *  thead 標籤與 SideCells 儲存格同源於此 — 加欄(如成交價/OI)只改這裡。 */
const QUOTE_COLUMNS: {
  key: string;
  label: string;
  cell: (ctx: SideCellCtx) => ReactElement;
}[] = [
  {
    key: "energy",
    label: "能量",
    cell: ({ row, maxAbs, side, td }) => (
      <td key="energy" className={cn(td, "w-24 min-w-16 align-middle")}>
        <EnergyBar
          netQty={row.net_qty}
          maxAbs={maxAbs}
          align={side === "call" ? "right" : "left"}
        />
      </td>
    ),
  },
  {
    key: "ratio",
    label: "內外盤比",
    cell: ({ row, td }) => (
      <td key="ratio" className={cn(td, "text-right", ratioTone(row))}>
        {ratioText(row)}
      </td>
    ),
  },
  {
    key: "volume",
    label: "成交量",
    cell: ({ row, td }) => (
      <td key="volume" className={cn(td, "text-right text-ink")}>
        {formatPts(row.volume)}
      </td>
    ),
  },
  {
    key: "net",
    label: "淨部位",
    cell: ({ row, td }) => (
      <td key="net" className={cn(td, "text-right font-medium", netTone(row.net_qty, "text"))}>
        {formatPts(row.net_qty)}
      </td>
    ),
  },
];

/** 單側欄序:Call 照定義、Put 鏡像(靠履約價欄相鄰)。 */
function sideColumns(side: "call" | "put") {
  return side === "call" ? QUOTE_COLUMNS : [...QUOTE_COLUMNS].reverse();
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
        {QUOTE_COLUMNS.map((col) => (
          <td key={col.key} className={cn(td, "text-center text-ink-dim")}>
            {DASH}
          </td>
        ))}
      </>
    );
  }
  return <>{sideColumns(side).map((col) => col.cell({ row, maxAbs, side, td }))}</>;
}

function HeadCells({ side }: { side: "call" | "put" }) {
  return (
    <>
      {sideColumns(side).map((col) => (
        <th
          key={col.key}
          className={cn(
            "px-2 py-1 font-normal",
            col.key === "energy" && side === "call" ? "text-left" : "text-right",
          )}
        >
          {col.label}
        </th>
      ))}
    </>
  );
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
              <HeadCells side="call" />
              <th className="px-2 py-1 text-center font-normal">履約價</th>
              <HeadCells side="put" />
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
