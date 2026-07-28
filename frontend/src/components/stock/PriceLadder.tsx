import { useEffect, useRef, useState } from "react";

import type { StockBook, StockMeta } from "@/lib/stock-accum";
import { buildLadder } from "@/lib/stock-tick";
import { cn } from "@/lib/utils";

const OPEN_KEY = "stock-ladder-open";

function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

function emitPriceClick(priceMilli: number): void {
  // 下單接點:與 OrderBook 同一 no-op event(群益接入輪掛單)
  window.dispatchEvent(new CustomEvent("stock-price-click", { detail: { priceMilli } }));
}

interface Props {
  book: StockBook | null;
  last: { p: number; t: string; cum_vol: number } | null;
  meta: StockMeta | null;
}

export function PriceLadder({ book, last, meta }: Props) {
  const [open, setOpen] = useState<boolean>(
    () => window.localStorage.getItem(OPEN_KEY) === "1",
  );
  const [follow, setFollow] = useState(true);
  const centerRef = useRef<HTMLButtonElement | null>(null);
  const progScroll = useRef(false);

  const rows = buildLadder({
    center: last?.p ?? null,
    ref: meta?.ref ?? null,
    upper: meta?.upper ?? null,
    lower: meta?.lower ?? null,
    book,
  });
  const centerPrice = rows.find((r) => r.isCenter)?.priceMilli ?? null;

  function toggleOpen(): void {
    const next = !open;
    setOpen(next);
    window.localStorage.setItem(OPEN_KEY, next ? "1" : "0");
  }

  // 跟隨置中:center 價變更才捲(rows identity 每 tick 變,依 centerPrice 值 — R5)
  useEffect(() => {
    if (!open || !follow || centerPrice === null) return;
    progScroll.current = true;
    centerRef.current?.scrollIntoView({ block: "center" });
    requestAnimationFrame(() => {
      progScroll.current = false;
    });
  }, [open, follow, centerPrice]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={toggleOpen}
        className="self-start rounded border border-line px-2 py-1 text-sm text-ink-dim hover:border-accent hover:text-ink"
      >
        閃電梯
      </button>
    );
  }

  return (
    <div className="flex w-52 shrink-0 flex-col rounded-md border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-2 py-1">
        <button type="button" onClick={toggleOpen} className="text-sm text-ink hover:text-accent">
          閃電梯
        </button>
        <button
          type="button"
          aria-pressed={follow}
          onClick={() => setFollow((f) => !f)}
          className={cn(
            "rounded border px-1.5 py-0.5 text-xs",
            follow ? "border-accent text-accent" : "border-line text-ink-dim",
          )}
        >
          跟隨置中
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="px-2 py-4 text-center text-xs text-ink-dim">無資料</p>
      ) : (
        <div
          className="max-h-96 overflow-y-auto"
          onScroll={() => {
            // 手動捲動(非程式捲)自動暫停跟隨(design R5)
            if (!progScroll.current && follow) setFollow(false);
          }}
        >
          {rows.map((r) => (
            <button
              key={r.priceMilli}
              type="button"
              ref={r.isCenter ? centerRef : undefined}
              disabled={r.dimmed}
              onClick={() => emitPriceClick(r.priceMilli)}
              className={cn(
                "grid h-6 w-full grid-cols-[1fr_64px_1fr] items-center border-b border-line/50 font-mono text-xs",
                r.isCenter && "bg-bg-deep",
                r.dimmed && "opacity-35",
              )}
            >
              <span className="pr-1 text-right text-bull">{r.bidQty > 0 ? r.bidQty : ""}</span>
              <span
                className={cn(
                  "text-center",
                  r.isCenter ? "text-accent" : r.dimmed ? "text-ink-dim" : "text-ink",
                )}
              >
                {fmt(r.priceMilli)}
              </span>
              <span className="pl-1 text-left text-bear">{r.askQty > 0 ? r.askQty : ""}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
