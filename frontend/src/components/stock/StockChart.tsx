import { useMemo, useState } from "react";

import { CandleChart } from "@/components/stock/CandleChart";
import { StockIntradayChart } from "@/components/stock/StockIntradayChart";
import { useChartToggles } from "@/hooks/useChartToggles";
import { MINUTE_DAYS, minutesOf, useStockBars, type ChartMode } from "@/hooks/useStockBars";
import { useContainerSize } from "@/hooks/useContainerSize";
import { aggregateBars } from "@/lib/candle";
import { CHART_MODE_KEY } from "@/lib/constants";
import { svgBox } from "@/lib/chart-frame";
import type { StockAccum } from "@/lib/stock-accum";
import { cn } from "@/lib/utils";

/** 圖表模式切換容器(SC-6):江波圖 / 1–10 分K / 日K。
 *  江波圖走既有即時 accum;K 線走 /api/stock/bars。2–10 分 K 全由 1 分前端聚合(D-8)。 */

// 初始可視根數(之後由滾輪縮放/拖曳平移控制)。分 K 240 ≈ 一個交易日的 1 分 K 全長 ——
// 切進去先看今天,再往左縮放/平移看更早。可視上限的 ≥2px 保護移交
// candle-viewport 的 MAX_VISIBLE(700 = viewBox 寬 1400 ÷ 2px)。
const DAILY_INIT_BARS = 120;
const MINUTE_INIT_BARS = 240;
/** 兩張圖的 viewBox 寬(固定);高度才是隨可用空間變的那一維(SC-6) */
const INTRADAY_VB_W = 800;
const CANDLE_VB_W = 1400;

const MODE_LABELS: [ChartMode, string][] = [
  ["intraday", "江波圖"],
  ...(Array.from({ length: 10 }, (_, i) => [`m${i + 1}`, `${i + 1}分K`]) as [ChartMode, string][]),
  ["day", "日K"],
];

const VALID_MODE = /^(intraday|day|m([1-9]|10))$/;

function initialMode(): ChartMode {
  const saved = window.localStorage.getItem(CHART_MODE_KEY);
  return saved !== null && VALID_MODE.test(saved) ? (saved as ChartMode) : "intraday";
}

export function StockChart({ accum, code }: { accum: StockAccum; code: string }) {
  const [mode, setMode] = useState<ChartMode>(initialMode);
  const { data, isPending, isError, error } = useStockBars(code, mode, MINUTE_DAYS);
  // bb 的狀態持有者(R16/R21):CandleChart 不自呼叫這個 hook,否則按鈕與圖各管各的
  const { toggles, set } = useChartToggles();

  function selectMode(next: ChartMode): void {
    setMode(next);
    window.localStorage.setItem(CHART_MODE_KEY, next);
  }

  // n=1 時 aggregateBars 原樣回傳,不必特判
  const bars = useMemo(() => aggregateBars(data ?? [], minutesOf(mode)), [data, mode]);

  const isMinute = mode !== "intraday" && mode !== "day";

  // 量測 wrapper 的可用空間 → 圖表 viewBox 高度(round3 SC-6)。
  // 量的是「剩下多少」不是「圖表現在多高」—— 被量元素的高度必須由外層 flex 指派
  // (useContainerSize 的呼叫端契約),否則會形成「圖表高 → 量測值 → 圖表高」的迴圈。
  const [sizeRef, size] = useContainerSize<HTMLDivElement>();
  const box = svgBox(size, mode === "intraday" ? INTRADAY_VB_W : CANDLE_VB_W);
  // 江波圖兩張 svg 上下相接:總 viewBox 高度按現行 260:70 拆分,且用減法讓兩者相加
  // 恰等於總高(各自 round 會多出 1px 誤差)。
  const mainH = box.usable ? Math.round((box.viewBoxHeight * 260) / 330) : undefined;
  const subH = box.usable ? box.viewBoxHeight - (mainH ?? 0) : undefined;

  return (
    // flex-1 min-h-0:圖表吃掉下半列以外的剩餘高度(SC-6)。原本是 shrink-0 的
    // 「寬度決定高度」固定比例,不隨剩餘空間縮,那正是 <main> 會頂出捲軸的原因。
    <div className="flex min-h-0 flex-1 flex-col">
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
      {/* 量測用的恆存 wrapper:loading / error / data 三態都掛在它底下(useContainerSize
          的呼叫端契約 —— ref 只掛 data 分支的話,冷載入會量到 0×0 而 hook 不再重跑)。 */}
      <div ref={sizeRef} className="flex min-h-0 flex-1 flex-col">
      {mode === "intraday" ? (
        <StockIntradayChart accum={accum} mainHeight={mainH} subHeight={subH} />
      ) : isPending ? (
        <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-line bg-surface">
          <p className="text-sm text-ink-muted">載入中…</p>
        </div>
      ) : isError ? (
        // 失敗態必須與「真的沒資料」分得開:2026-07-29 舊 build 佔 port 讓 endpoint 回 404,
        // 當時兩者共用「無 K 線資料」一句 → 被誤讀成「這檔沒 K 線」(SC-3)。
        // 錯誤碼取值鏈見 useStockBars.ts:35-44(detail.error 優先 → HTTP_<status>)。
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 rounded-md border border-line bg-surface">
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
          height={box.usable ? box.viewBoxHeight : undefined}
        />
      )}
      </div>
    </div>
  );
}
