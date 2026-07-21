import { useRef, useState } from "react";

import { useSaveWatchlist, useStockWatchlist } from "@/hooks/useStockWatchlist";
import type { WatchlistQuote } from "@/hooks/useStockStream";
import { insertIndexFromPointer, reorder } from "@/lib/list-drag";
import { cn } from "@/lib/utils";

const ROW_H = 44;

function fmtPrice(milli: number | null): string {
  if (milli === null) return "-";
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

interface Props {
  active: string | null;
  onSelect: (code: string) => void;
  quotes: Record<string, WatchlistQuote>;
}

export function WatchlistSidebar({ active, onSelect, quotes }: Props) {
  const { data: codes = [], error } = useStockWatchlist();
  const save = useSaveWatchlist();
  const [input, setInput] = useState("");
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dragTo, setDragTo] = useState<number | null>(null);
  const listRef = useRef<HTMLUListElement | null>(null);

  const displayed = dragFrom !== null && dragTo !== null ? reorder(codes, dragFrom, dragTo) : codes;

  function add(): void {
    const code = input.trim().toUpperCase();
    if (!code || codes.includes(code)) return;
    save.mutate([...codes, code]);
    setInput("");
  }

  function remove(code: string): void {
    save.mutate(codes.filter((c) => c !== code));
  }

  function onHandleDown(index: number, e: React.PointerEvent): void {
    e.preventDefault();
    setDragFrom(index);
    setDragTo(index);
    const list = listRef.current;
    const move = (ev: PointerEvent): void => {
      const top = list?.getBoundingClientRect().top ?? 0;
      setDragTo(insertIndexFromPointer(ev.clientY - top, ROW_H, codes.length));
    };
    const up = (ev: PointerEvent): void => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      const top = list?.getBoundingClientRect().top ?? 0;
      const to = insertIndexFromPointer(ev.clientY - top, ROW_H, codes.length);
      setDragFrom(null);
      setDragTo(null);
      if (to !== index) save.mutate(reorder(codes, index, to));
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col gap-2">
      <div className="flex gap-1">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="輸入股號"
          className="w-full rounded border border-line bg-bg px-2 py-1 font-mono text-sm text-ink outline-none focus:border-accent"
        />
        <button
          type="button"
          onClick={add}
          className="shrink-0 rounded border border-line px-2 py-1 text-sm text-ink hover:border-accent"
        >
          新增
        </button>
      </div>
      {save.error ? (
        <p className="text-xs text-bear">{save.error.message === "WATCHLIST_FULL" ? "自選已達 30 檔上限" : save.error.message === "BAD_CODE" ? "股號格式不正確" : "儲存失敗"}</p>
      ) : null}
      {error ? <p className="text-xs text-bear">自選清單載入失敗</p> : null}
      <ul ref={listRef} className="flex flex-col overflow-y-auto">
        {displayed.map((code) => {
          const q = quotes[code];
          const index = codes.indexOf(code);
          return (
            <li
              key={code}
              className={cn(
                "group flex h-11 cursor-pointer items-center gap-2 border-b border-line px-1",
                active === code && "bg-bg-deep",
                dragFrom !== null && displayed[dragTo ?? -1] === code && "border-accent",
              )}
              onClick={() => onSelect(code)}
            >
              <span
                role="button"
                aria-label={`拖拉 ${code}`}
                className="cursor-grab select-none text-ink-dim"
                onPointerDown={(e) => onHandleDown(index, e)}
                onClick={(e) => e.stopPropagation()}
              >
                ⋮⋮
              </span>
              <span className="w-14 font-mono text-sm text-ink">{code}</span>
              {q?.no_data ? (
                <span className="flex-1 text-right text-xs text-ink-dim">無資料</span>
              ) : (
                <span className="flex flex-1 items-baseline justify-end gap-2 font-mono text-xs">
                  <span className="text-sm text-ink">{fmtPrice(q?.p ?? null)}</span>
                  <span
                    className={cn(
                      "w-14 text-right",
                      (q?.chg_pct ?? 0) > 0 ? "text-bull" : (q?.chg_pct ?? 0) < 0 ? "text-bear" : "text-ink-dim",
                    )}
                  >
                    {q?.chg_pct != null ? `${q.chg_pct > 0 ? "+" : ""}${q.chg_pct.toFixed(2)}%` : "-"}
                  </span>
                </span>
              )}
              <button
                type="button"
                aria-label={`移除 ${code}`}
                className="invisible text-ink-dim hover:text-bear group-hover:visible"
                onClick={(e) => {
                  e.stopPropagation();
                  remove(code);
                }}
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>
      {displayed.length === 0 ? <p className="text-xs text-ink-dim">尚無自選,輸入股號新增</p> : null}
    </aside>
  );
}
