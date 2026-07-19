import { orderSideText, orderStatusText } from "@/lib/trade-text";
import { cn } from "@/lib/utils";
import type { OrderRow, OrdersView } from "@/types";

function shortSymbol(symbol: string): string {
  return symbol.replace(/^TC\.[FO]\.TWF\./, "");
}

function Rows({ rows, empty }: { rows: OrderRow[]; empty: string }) {
  if (rows.length === 0) {
    return <p className="py-3 text-center text-xs text-ink-dim">{empty}</p>;
  }
  return (
    <ul className="divide-y divide-line/60">
      {rows.map((row) => (
        <li
          key={row.report_id}
          className="grid grid-cols-[1fr_auto_auto_auto_auto] items-baseline gap-x-3 py-1.5 font-mono text-xs"
        >
          <span className="truncate text-ink">{shortSymbol(row.symbol)}</span>
          <span className={cn(row.side === "1" ? "text-bull" : "text-bear")}>
            {orderSideText(row.side)}
          </span>
          <span className="text-ink">{row.price}</span>
          <span className="text-ink-muted">
            {row.filled_qty || "0"}/{row.qty}
          </span>
          <span className={cn("text-right", row.err_code ? "text-loss" : "text-ink-muted")}>
            {orderStatusText(row.status_raw)}
            {row.err_code ? `(${row.err_code})` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function OrdersList({ view }: { view: OrdersView | undefined }) {
  return (
    <div className="min-w-0">
      {view?.degraded && (
        <p className="mb-2 border border-loss/40 bg-loss/10 px-2 py-1 text-xs text-loss">
          回報連線中斷,列表可能不完整
        </p>
      )}
      {view?.audit_degraded && (
        <p className="mb-2 border border-loss/40 bg-loss/10 px-2 py-1 text-xs text-loss">
          審計記錄異常,請檢查 server log
        </p>
      )}
      <div className="grid gap-4 @[560px]:grid-cols-2">
        <section>
          <h3 className="mb-1 border-b border-line pb-1 text-xs tracking-wide text-ink-dim">
            當日委託
          </h3>
          <Rows rows={view?.orders ?? []} empty="尚無委託" />
        </section>
        <section>
          <h3 className="mb-1 border-b border-line pb-1 text-xs tracking-wide text-ink-dim">
            當日成交
          </h3>
          <Rows rows={view?.fills ?? []} empty="尚無成交" />
        </section>
      </div>
    </div>
  );
}
