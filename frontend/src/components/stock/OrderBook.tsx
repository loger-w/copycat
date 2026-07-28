import { cn } from "@/lib/utils";

interface Props {
  book: { bids: [number, number][]; asks: [number, number][] } | null;
  last: { p: number; t: string; cum_vol: number } | null;
  ref_: number | null; // 參考價(漲跌色基準)
  upper?: number | null; // 漲停價(鎖停 badge 判定;SC-5)
  lower?: number | null;
}

const DEPTH = 5;

function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

function emitPriceClick(priceMilli: number): void {
  // 下一輪下單匣接點(design §3:本輪 no-op 監聽者)
  window.dispatchEvent(new CustomEvent("stock-price-click", { detail: { priceMilli } }));
}

export function OrderBook({ book, last, ref_, upper = null, lower = null }: Props) {
  const asks = [...(book?.asks ?? [])].slice(0, DEPTH);
  const bids = (book?.bids ?? []).slice(0, DEPTH);
  const maxVol = Math.max(1, ...asks.map(([, v]) => v), ...bids.map(([, v]) => v));
  const chg = last && ref_ ? ((last.p - ref_) / ref_) * 100 : null;
  const bidTotal = bids.reduce((s, [, v]) => s + v, 0);
  const askTotal = asks.reduce((s, [, v]) => s + v, 0);
  const lockedUp = upper !== null && bids[0]?.[0] === upper;
  const lockedDown = lower !== null && asks[0]?.[0] === lower;

  function row(side: "ask" | "bid", level: number) {
    const entry = side === "ask" ? asks[level] : bids[level];
    return (
      <tr key={`${side}-${level}`} className="h-7">
        <td className="w-8 pr-1 text-right font-mono text-xs text-ink-dim">
          {side === "ask" ? `賣${level + 1}` : `買${level + 1}`}
        </td>
        <td className="relative w-20 text-right font-mono text-sm">
          {entry ? (
            <button
              type="button"
              className={cn("w-full text-right", side === "ask" ? "text-bear" : "text-bull")}
              onClick={() => emitPriceClick(entry[0])}
            >
              {fmt(entry[0])}
            </button>
          ) : (
            <span className="text-ink-dim">—</span>
          )}
        </td>
        <td className="relative w-24 pl-2">
          {entry ? (
            <>
              <span
                className={cn(
                  "absolute inset-y-1 rounded-sm",
                  // 買側靠右往左長、賣側靠左往右長(SC-5,treading-king 方向慣例)
                  side === "ask" ? "left-0 bg-bear/20" : "right-0 bg-bull/20",
                )}
                style={{ width: `${(entry[1] / maxVol) * 100}%` }}
              />
              <span className="relative font-mono text-xs text-ink">{entry[1]}</span>
            </>
          ) : (
            <span className="text-ink-dim">—</span>
          )}
        </td>
      </tr>
    );
  }

  return (
    <div className="rounded-md border border-line bg-surface p-3">
      <div className="mb-1 flex justify-between border-b border-line pb-1 font-mono text-xs">
        <span className="text-bull">委買 {bidTotal}</span>
        <span className="text-bear">委賣 {askTotal}</span>
      </div>
      <table className="w-full border-collapse">
        <tbody>
          {[...Array(DEPTH).keys()].reverse().map((i) => row("ask", i))}
          <tr className="h-9 border-y border-line">
            <td colSpan={3} className="text-center font-mono">
              {last ? (
                <span className={cn("text-base", chg != null && chg > 0 ? "text-bull" : chg != null && chg < 0 ? "text-bear" : "text-ink")}>
                  {fmt(last.p)}
                  {chg != null ? (
                    <span className="ml-2 text-xs">{`${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`}</span>
                  ) : null}
                </span>
              ) : (
                <span className="text-sm text-ink-dim">—</span>
              )}
              {lockedUp ? (
                <span className="ml-2 rounded bg-bull/15 px-1.5 py-0.5 text-xs text-bull">鎖漲停</span>
              ) : null}
              {lockedDown ? (
                <span className="ml-2 rounded bg-bear/15 px-1.5 py-0.5 text-xs text-bear">鎖跌停</span>
              ) : null}
            </td>
          </tr>
          {[...Array(DEPTH).keys()].map((i) => row("bid", i))}
        </tbody>
      </table>
    </div>
  );
}
