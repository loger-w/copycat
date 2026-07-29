import { useMemo, useState } from "react";

import { CandleChart } from "@/components/stock/CandleChart";
import { StockIntradayChart } from "@/components/stock/StockIntradayChart";
import { DAYS_MAX, DAYS_STEP, useStockBars, type ChartMode } from "@/hooks/useStockBars";
import { aggregateBars } from "@/lib/candle";
import type { StockAccum } from "@/lib/stock-accum";
import { cn } from "@/lib/utils";

/** 圖表模式切換容器(SC-7):江波圖 / 1分K / 5分K / 日K。
 *  江波圖走既有即時 accum;K 線走 /api/stock/bars。5 分 K 由 1 分前端聚合(D-8)。 */

const MODE_KEY = "copycat-chart-mode";
const DAILY_MAX_BARS = 120;

const MODES = [
  ["intraday", "江波圖"],
  ["m1", "1分K"],
  ["m5", "5分K"],
  ["day", "日K"],
] as const;

function initialMode(): ChartMode {
  const saved = window.localStorage.getItem(MODE_KEY);
  return saved === "m1" || saved === "m5" || saved === "day" ? saved : "intraday";
}

export function StockChart({ accum, code }: { accum: StockAccum; code: string }) {
  const [mode, setMode] = useState<ChartMode>(initialMode);
  const [days, setDays] = useState(DAYS_STEP);
  const { data, isPending, isError } = useStockBars(code, mode, days);

  function selectMode(next: ChartMode): void {
    setMode(next);
    window.localStorage.setItem(MODE_KEY, next);
  }

  const bars = useMemo(
    () => (mode === "m5" ? aggregateBars(data ?? [], 5) : (data ?? [])),
    [data, mode],
  );

  const isMinute = mode === "m1" || mode === "m5";

  return (
    <div className="flex flex-col">
      <div className="mb-1 flex items-center gap-1">
        {MODES.map(([id, label]) => (
          <button
            key={id}
            type="button"
            aria-pressed={mode === id}
            onClick={() => selectMode(id)}
            className={cn(
              "rounded border px-2 py-0.5 text-xs",
              mode === id ? "border-accent text-accent" : "border-line text-ink-dim hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
        {isMinute ? (
          <button
            type="button"
            disabled={days >= DAYS_MAX}
            onClick={() => setDays((d) => Math.min(DAYS_MAX, d + DAYS_STEP))}
            className="ml-2 rounded border border-line px-2 py-0.5 text-xs text-ink-dim hover:text-ink disabled:opacity-40"
          >
            往前
          </button>
        ) : null}
        {isMinute ? <span className="text-xs text-ink-dim">近 {days} 日</span> : null}
      </div>
      {mode === "intraday" ? (
        <StockIntradayChart accum={accum} />
      ) : isPending ? (
        <div className="flex h-64 items-center justify-center rounded-md border border-line bg-surface">
          <p className="text-sm text-ink-muted">載入中…</p>
        </div>
      ) : isError ? (
        <div className="flex h-64 items-center justify-center rounded-md border border-line bg-surface">
          <p className="text-sm text-ink-muted">無 K 線資料</p>
        </div>
      ) : (
        <CandleChart
          bars={bars}
          maxBars={mode === "day" ? DAILY_MAX_BARS : undefined}
          showMa={mode === "day"}
        />
      )}
    </div>
  );
}
