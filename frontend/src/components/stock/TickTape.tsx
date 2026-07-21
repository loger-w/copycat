import { useState } from "react";

import type { TickRow } from "@/lib/stock-accum";
import { cn } from "@/lib/utils";

const PAGE = 30;

function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

export function TickTape({ ticks }: { ticks: TickRow[] }) {
  const [limit, setLimit] = useState(PAGE);
  const rows = [...ticks].reverse().slice(0, limit);

  if (rows.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-line bg-surface">
        <p className="text-sm text-ink-muted">尚無成交</p>
      </div>
    );
  }

  return (
    <div className="flex max-h-80 flex-col overflow-y-auto rounded-md border border-line bg-surface p-3">
      <table className="w-full border-collapse font-mono text-xs">
        <thead>
          <tr className="text-ink-dim">
            <th className="pb-1 text-left font-normal">時間</th>
            <th className="pb-1 text-right font-normal">成交價</th>
            <th className="pb-1 text-right font-normal">單量</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t, i) => (
            <tr key={`${t.t}-${i}`} className="h-6">
              <td className="text-ink-muted">{t.t.slice(0, 8)}</td>
              <td
                className={cn(
                  "text-right",
                  t.side === "outer" ? "text-bull" : t.side === "inner" ? "text-bear" : "text-ink-dim",
                )}
              >
                {fmt(t.p)}
              </td>
              <td className="text-right text-ink">{t.q}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {ticks.length > limit ? (
        <button
          type="button"
          className="mt-2 text-xs text-ink-dim hover:text-ink"
          onClick={() => setLimit((n) => n + PAGE)}
        >
          載入更多
        </button>
      ) : null}
    </div>
  );
}
