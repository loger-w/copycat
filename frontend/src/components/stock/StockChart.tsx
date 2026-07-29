import { useMemo, useState } from "react";

import { CandleChart } from "@/components/stock/CandleChart";
import { StockIntradayChart } from "@/components/stock/StockIntradayChart";
import { useChartToggles } from "@/hooks/useChartToggles";
import { MINUTE_DAYS, minutesOf, useStockBars, type ChartMode } from "@/hooks/useStockBars";
import { aggregateBars } from "@/lib/candle";
import type { StockAccum } from "@/lib/stock-accum";
import { cn } from "@/lib/utils";

/** 圖表模式切換容器(SC-6):江波圖 / 1–10 分K / 日K。
 *  江波圖走既有即時 accum;K 線走 /api/stock/bars。2–10 分 K 全由 1 分前端聚合(D-8)。 */

const MODE_KEY = "copycat-chart-mode";
// 初始可視根數(之後由滾輪縮放/拖曳平移控制)。分 K 240 ≈ 一個交易日的 1 分 K 全長 ——
// 切進去先看今天,再往左縮放/平移看更早。可視上限的 ≥2px 保護移交
// candle-viewport 的 MAX_VISIBLE(700 = viewBox 寬 1400 ÷ 2px)。
const DAILY_INIT_BARS = 120;
const MINUTE_INIT_BARS = 240;

const MODE_LABELS: [ChartMode, string][] = [
  ["intraday", "江波圖"],
  ...(Array.from({ length: 10 }, (_, i) => [`m${i + 1}`, `${i + 1}分K`]) as [ChartMode, string][]),
  ["day", "日K"],
];

const VALID_MODE = /^(intraday|day|m([1-9]|10))$/;

function initialMode(): ChartMode {
  const saved = window.localStorage.getItem(MODE_KEY);
  return saved !== null && VALID_MODE.test(saved) ? (saved as ChartMode) : "intraday";
}

export function StockChart({ accum, code }: { accum: StockAccum; code: string }) {
  const [mode, setMode] = useState<ChartMode>(initialMode);
  const { data, isPending, isError, error } = useStockBars(code, mode, MINUTE_DAYS);
  // bb 的狀態持有者(R16/R21):CandleChart 不自呼叫這個 hook,否則按鈕與圖各管各的
  const { toggles, set } = useChartToggles();

  function selectMode(next: ChartMode): void {
    setMode(next);
    window.localStorage.setItem(MODE_KEY, next);
  }

  // n=1 時 aggregateBars 原樣回傳,不必特判
  const bars = useMemo(() => aggregateBars(data ?? [], minutesOf(mode)), [data, mode]);

  const isMinute = mode !== "intraday" && mode !== "day";

  return (
    // shrink-0:圖表維持 viewBox 決定的自然高度。少了它,負剩餘空間時本容器會被壓縮,
    // 而內部固定高度的 svg 不跟著縮 → 溢出並與下半列重疊(SC-6 / W-17)。
    <div className="flex shrink-0 flex-col">
      <div className="mb-1 flex flex-wrap items-center gap-1">
        {MODE_LABELS.map(([id, label]) => (
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
      </div>
      {mode === "intraday" ? (
        <StockIntradayChart accum={accum} />
      ) : isPending ? (
        <div className="flex h-64 items-center justify-center rounded-md border border-line bg-surface">
          <p className="text-sm text-ink-muted">載入中…</p>
        </div>
      ) : isError ? (
        // 失敗態必須與「真的沒資料」分得開:2026-07-29 舊 build 佔 port 讓 endpoint 回 404,
        // 當時兩者共用「無 K 線資料」一句 → 被誤讀成「這檔沒 K 線」(SC-3)。
        // 錯誤碼取值鏈見 useStockBars.ts:35-44(detail.error 優先 → HTTP_<status>)。
        <div className="flex h-64 flex-col items-center justify-center gap-1 rounded-md border border-line bg-surface">
          <p className="text-sm text-bear">K 線載入失敗</p>
          <p className="font-mono text-xs text-ink-dim">{(error as Error | null)?.message ?? ""}</p>
        </div>
      ) : (
        // key:換股或換模式時強制重掛,viewport 回到初始式。換模式會讓 total 由
        // ~5,900 變 ~590,沿用舊 index 沒有意義(onTotalChange 只處理同序列的延伸)。
        <CandleChart
          key={`${code}-${mode}`}
          bars={bars}
          initBars={isMinute ? MINUTE_INIT_BARS : DAILY_INIT_BARS}
          showBb={toggles.bb}
          onToggleBb={(v) => set("bb", v)}
        />
      )}
    </div>
  );
}
