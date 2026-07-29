import { memo, useEffect, useMemo, useRef, useState } from "react";

import { bandSeries, bollinger, type Band } from "@/lib/bollinger";
import {
  buildCandleGeometry,
  movingAverage,
  type Bar,
  type CandleGeometry,
} from "@/lib/candle";
import {
  initialViewport,
  onTotalChange,
  panBy,
  zoomAt,
  type Viewport,
} from "@/lib/candle-viewport";
import { toSvgPoint } from "@/lib/chart-crosshair";
import { cn } from "@/lib/utils";

/** K 線圖(SC-6/SC-7)。幾何全在 lib/candle.ts + lib/candle-viewport.ts,本檔只掛 DOM。
 *  台股慣例:紅漲(bull)/ 綠跌(bear)。 */

const DIMS = { width: 1400, height: 320 };
const X_LABEL_H = 14;
/** 滾輪每一格的縮放倍率 */
const ZOOM_STEP = 1.15;

const BODY_CLASS = {
  up: "fill-bull stroke-bull",
  down: "fill-bear stroke-bear",
  flat: "fill-ink-dim stroke-ink-dim",
} as const;

const VOL_CLASS = {
  up: "fill-bull/40",
  down: "fill-bear/40",
  flat: "fill-ink-dim/30",
} as const;

function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

/** `YYYY-MM-DD` → `MM/DD`;`YYYY-MM-DD HH:MM` → `HH:MM` */
function shortStamp(t: string): string {
  const sp = t.indexOf(" ");
  if (sp >= 0) return t.slice(sp + 1);
  return t.slice(5).replace("-", "/");
}

function pts(line: { x: number; y: number }[]): string {
  return line.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

/** 穩定 identity 的空線:`[]` 字面量每次 render 都是新 array,會打穿 ChartStatic 的 memo。 */
const EMPTY_LINE: { x: number; y: number }[] = [];

/** 值序列 → 折線點。**必須在元件外**且結果包 useMemo:
 *  hover 每個 mousemove 都會 re-render 父層,若線的 array identity 每次都變,
 *  memo 過的 ChartStatic 仍會每次重建(最多 700 根蠟燭 × 3 個節點)。 */
function seriesLine(
  values: readonly (number | null)[],
  g: CandleGeometry,
): { x: number; y: number }[] {
  const line: { x: number; y: number }[] = [];
  values.forEach((v, i) => {
    const c = g.candles[i];
    if (v !== null && c !== undefined) line.push({ x: c.cx, y: g.toY(v) });
  });
  return line;
}

/** 靜態圖層 memo:hover 每 mousemove re-render 父層,蠟燭/量/標籤層不可每次重建
 *  (分 K 可達數百根;對齊 StockIntradayChart 的 ChartStatic 慣例 — review P1-1)。 */
const ChartStatic = memo(function ChartStatic({
  g,
  shown,
  ma5Line,
  ma20Line,
  bbUpperLine,
  bbLowerLine,
  labelStep,
}: {
  g: CandleGeometry;
  shown: Bar[];
  ma5Line: { x: number; y: number }[];
  ma20Line: { x: number; y: number }[];
  bbUpperLine: { x: number; y: number }[];
  bbLowerLine: { x: number; y: number }[];
  labelStep: number;
}) {
  return (
    <g>
        {/* y 軸格線 + 價位刻度 */}
      {g.yTicks.map((t) => (
        <g key={`yt-${t.priceMilli}`}>
          <line
            x1={0}
            x2={DIMS.width}
            y1={t.y}
            y2={t.y}
            className="stroke-line"
            strokeDasharray="2 3"
            strokeWidth={0.5}
          />
          <text x={2} y={t.y - 2} className="fill-ink-dim" fontSize="0.625rem">
            {fmt(t.priceMilli)}
          </text>
        </g>
      ))}
      {/* 布林通道:先畫帶狀填色再畫上下軌,才不會蓋掉蠟燭 */}
      {bbUpperLine.length > 1 && bbLowerLine.length > 1 ? (
        <>
          <polygon
            data-testid="bb-band"
            points={pts([...bbUpperLine, ...[...bbLowerLine].reverse()])}
            className="fill-ink-muted"
            fillOpacity="0.07"
          />
          <polyline
            data-testid="bb-upper"
            points={pts(bbUpperLine)}
            fill="none"
            className="stroke-ink-muted"
            strokeWidth={0.8}
            strokeDasharray="3 2"
          />
          <polyline
            data-testid="bb-lower"
            points={pts(bbLowerLine)}
            fill="none"
            className="stroke-ink-muted"
            strokeWidth={0.8}
            strokeDasharray="3 2"
          />
        </>
      ) : null}
      {/* 量 bar */}
      {g.volBars.map((b, i) => (
        <rect
          key={`v-${i}`}
          x={b.x}
          y={b.y}
          width={b.w}
          height={b.h}
          className={VOL_CLASS[b.dir]}
        />
      ))}
      {/* 蠟燭:影線 + 實體 */}
      {g.candles.map((c, i) => (
        <g key={`c-${i}`}>
          <line
            x1={c.cx}
            x2={c.cx}
            y1={c.wickTop}
            y2={c.wickBottom}
            className={BODY_CLASS[c.dir]}
            strokeWidth={1}
          />
          <rect
            data-testid="candle-body"
            x={c.x}
            y={c.bodyTop}
            width={c.w}
            height={c.bodyH}
            className={BODY_CLASS[c.dir]}
          />
        </g>
      ))}
      {/* MA 疊線 */}
      {ma5Line.length > 1 ? (
        <polyline
          data-testid="ma-5"
          points={pts(ma5Line)}
          fill="none"
          className="stroke-ma5"
          strokeWidth={1.2}
        />
      ) : null}
      {ma20Line.length > 1 ? (
        <polyline
          data-testid="ma-20"
          points={pts(ma20Line)}
          fill="none"
          className="stroke-ma20"
          strokeWidth={1.2}
        />
      ) : null}
      {/* x 軸標籤 */}
      {shown.map((b, i) =>
        i % labelStep === 0 ? (
          <text
            key={`x-${i}`}
            x={g.candles[i]!.cx}
            y={DIMS.height - 3}
            textAnchor="middle"
            className="fill-ink-dim"
            fontSize="0.625rem"
          >
            {shortStamp(b.t)}
          </text>
        ) : null,
      )}
    </g>
  );
});

interface Props {
  bars: Bar[];
  /** 初始可視根數(日 K 120 / 分 K 240);之後由滾輪縮放與拖曳平移控制 */
  initBars?: number;
  /** 布林通道開關。狀態由 StockChart 持有(useChartToggles 是每 instance 各一份,
   *  本元件不自呼叫該 hook,否則按鈕與圖會各管各的) */
  showBb?: boolean;
  onToggleBb?: (value: boolean) => void;
}

export function CandleChart({ bars, initBars = 120, showBb = false, onToggleBb }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const [viewport, setViewport] = useState<Viewport>(() => initialViewport(bars.length, initBars));
  const [prevTotal, setPrevTotal] = useState(bars.length);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // 序列延伸(分 K 每 60s refetch 追加新 bar)時調整窗口。用 render 期間調整 state 的
  // 官方 pattern,不用 effect —— 專案有 react-you-might-not-need-an-effect lint。
  // ⚠ 只處理「同一 code+mode 的延伸」;換股/換模式由 StockChart 給的 key 強制重掛。
  if (prevTotal !== bars.length) {
    setPrevTotal(bars.length);
    setViewport((v) => onTotalChange(v, prevTotal, bars.length));
  }

  const { shown, g, ma5, ma20, bands } = useMemo(() => {
    const start = viewport.start;
    const shownBars = bars.slice(start, start + viewport.count);
    // MA / BB 以完整序列計算後再裁切,左緣才不會斷頭;裁切區間必須與 shown 對齊,
    // 否則 y 域會被視窗外的極值撐開、圖被壓扁而且不會報錯。
    const m5 = movingAverage(bars, 5).slice(start, start + viewport.count);
    const m20 = movingAverage(bars, 20).slice(start, start + viewport.count);
    const bb: (Band | null)[] = showBb
      ? bollinger(bars, 20).slice(start, start + viewport.count)
      : [];
    const extra = showBb ? [bandSeries(bb, "upper"), bandSeries(bb, "lower")] : undefined;
    return {
      shown: shownBars,
      g: buildCandleGeometry(shownBars, DIMS, extra),
      ma5: m5,
      ma20: m20,
      bands: bb,
    };
  }, [bars, viewport, showBb]);

  const ma5Line = useMemo(() => seriesLine(ma5, g), [ma5, g]);
  const ma20Line = useMemo(() => seriesLine(ma20, g), [ma20, g]);
  const bbUpperLine = useMemo(
    () => (showBb ? seriesLine(bandSeries(bands, "upper"), g) : EMPTY_LINE),
    [showBb, bands, g],
  );
  const bbLowerLine = useMemo(
    () => (showBb ? seriesLine(bandSeries(bands, "lower"), g) : EMPTY_LINE),
    [showBb, bands, g],
  );

  const total = bars.length;

  // 滾輪縮放。**必須掛原生 listener 且 passive: false** —— React 的 onWheel 綁在 root
  // 且為 passive,preventDefault() 無效,頁面會跟著一起捲。
  useEffect(() => {
    const el = svgRef.current;
    if (el === null) return;
    const onWheel = (e: WheelEvent): void => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const { x } = toSvgPoint(e, rect, DIMS);
      const ratio = DIMS.width > 0 ? x / DIMS.width : 0.5;
      const factor = e.deltaY > 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      setViewport((v) => zoomAt(v, total, factor, ratio));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [total]);

  function onMove(e: React.MouseEvent<SVGSVGElement>): void {
    const rect = e.currentTarget.getBoundingClientRect();
    const { x } = toSvgPoint(e, rect, DIMS);
    setHover(g.indexOf(x));
  }

  /** 拖曳平移:mousedown 記起點,mousemove/mouseup 掛 window(拖出圖外仍跟手)。
   *  維持 mouse 事件模型 —— 專案慣例是觸控靠 tap 的 synthetic mousemove,改 pointer 會破。 */
  function onDragStart(e: React.MouseEvent<SVGSVGElement>): void {
    if (e.button !== 0) return;
    const el = svgRef.current;
    if (el === null) return;
    const rect = el.getBoundingClientRect();
    const scale = rect.width > 0 ? DIMS.width / rect.width : 1;
    const startX = e.clientX;
    let startVp: Viewport | null = null;
    setViewport((v) => {
      startVp = v;
      return v;
    });
    const move = (ev: MouseEvent): void => {
      const slot = DIMS.width / Math.max(1, startVp?.count ?? viewport.count);
      // 往右拖 = 看更早的資料 → start 往左
      const deltaBars = -Math.round(((ev.clientX - startX) * scale) / slot);
      const base = startVp ?? viewport;
      setViewport(panBy(base, total, deltaBars));
      setHover(null); // 拖曳中不更新十字線,避免抖動
    };
    const up = (): void => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  const labelStep = Math.max(1, Math.ceil(Math.max(1, shown.length) / 6));
  const hoverBar = hover !== null ? shown[hover] : undefined;
  const hoverCandle = hover !== null ? g.candles[hover] : undefined;

  return (
    // select-none:SVG 的 <text>(價位刻度 / 日期標籤)預設可選,在圖上拖曳會整片反白(SC-4)。
    // 不影響 hover — user-select 只管選取,mouse 事件照舊(W-10)。
    <figure
      data-testid="candle-figure"
      data-first={shown[0]?.t ?? ""}
      data-count={shown.length}
      className="select-none rounded-md border border-line bg-surface p-4"
    >
      {/* 頂列:左側留給資訊條、右側指標 toggle。高度以 rem 固定(root font-size 縮放才等比) */}
      <div className="mb-1 flex h-[1.375rem] items-center justify-between gap-2">
        <span />
        <button
          type="button"
          aria-pressed={showBb}
          onClick={() => onToggleBb?.(!showBb)}
          className={cn(
            "rounded border px-2 py-0.5 text-xs",
            showBb ? "border-accent text-accent" : "border-line text-ink-dim hover:text-ink",
          )}
        >
          BB
        </button>
      </div>
      {shown.length === 0 ? (
        <div className="flex h-64 items-center justify-center">
          <p className="text-sm text-ink-muted">無 K 線資料</p>
        </div>
      ) : (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${DIMS.width} ${DIMS.height}`}
          className="w-full"
          style={{ touchAction: "pan-y" }}
          role="img"
          aria-label="K 線圖"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
          onMouseDown={onDragStart}
        >
          <ChartStatic
            g={g}
            shown={shown}
            ma5Line={ma5Line}
            ma20Line={ma20Line}
            bbUpperLine={bbUpperLine}
            bbLowerLine={bbLowerLine}
            labelStep={labelStep}
          />
          {/* hover 十字 */}
          {hoverCandle !== undefined ? (
            <line
              x1={hoverCandle.cx}
              x2={hoverCandle.cx}
              y1={0}
              y2={DIMS.height - X_LABEL_H}
              className="stroke-ink-muted"
              strokeDasharray="2 2"
              strokeWidth={0.7}
              pointerEvents="none"
            />
          ) : null}
        </svg>
      )}
      {hoverBar !== undefined ? (
        <figcaption
          data-testid="candle-tooltip"
          className="mt-1 flex flex-wrap gap-x-3 font-mono text-xs text-ink-dim"
        >
          <span className="text-ink">{hoverBar.t}</span>
          <span>開 {fmt(hoverBar.o)}</span>
          <span>高 {fmt(hoverBar.h)}</span>
          <span>低 {fmt(hoverBar.l)}</span>
          <span
            className={cn(
              hoverBar.c > hoverBar.o ? "text-bull" : hoverBar.c < hoverBar.o ? "text-bear" : "",
            )}
          >
            收 {fmt(hoverBar.c)}
          </span>
          <span>量 {hoverBar.v}</span>
        </figcaption>
      ) : null}
    </figure>
  );
}
