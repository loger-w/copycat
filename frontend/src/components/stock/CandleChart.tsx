import { memo, useMemo, useState } from "react";

import {
  buildCandleGeometry,
  movingAverage,
  type Bar,
  type CandleGeometry,
} from "@/lib/candle";
import { cn } from "@/lib/utils";

/** K 線圖(SC-7)。幾何全在 lib/candle.ts,本檔只掛 DOM。
 *  台股慣例:紅漲(bull)/ 綠跌(bear)。 */

const DIMS = { width: 1400, height: 320 };
const X_LABEL_H = 14;

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

/** 穩定 identity 的空線:`showMa` 關閉時若回 `[]` 字面量,每次 render 都是新 array,
 *  `ChartStatic` 的 memo 會被打穿(見下方 maLine 的說明)。 */
const EMPTY_LINE: { x: number; y: number }[] = [];

/** MA 值序列 → 折線點。**必須在元件外**且結果包 useMemo:
 *  hover 每個 mousemove 都會 re-render 父層,若 ma5Line/ma20Line 每次都是新 array identity,
 *  memo 過的 ChartStatic 仍會每次重建(最多 700 根蠟燭 × 3 個節點)。 */
function maLine(values: readonly (number | null)[], g: CandleGeometry): { x: number; y: number }[] {
  const line: { x: number; y: number }[] = [];
  values.forEach((v, i) => {
    const c = g.candles[i];
    if (v !== null && c !== undefined) line.push({ x: c.cx, y: g.toY(v) });
  });
  return line;
}


/** 靜態圖層 memo:hover 每 mousemove re-render 父層,蠟燭/量/標籤層不可每次重建
 *  (分 K 可達數千根;對齊 StockIntradayChart 的 ChartStatic 慣例 — review P1-1)。 */
const ChartStatic = memo(function ChartStatic({
  g,
  shown,
  ma5Line,
  ma20Line,
  labelStep,
}: {
  g: CandleGeometry;
  shown: Bar[];
  ma5Line: { x: number; y: number }[];
  ma20Line: { x: number; y: number }[];
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
  /** 只畫最後 N 根(SC-7 日K 上限);未給 = 全畫 */
  maxBars?: number;
  showMa?: boolean;
}

export function CandleChart({ bars, maxBars, showMa = false }: Props) {
  const [hover, setHover] = useState<number | null>(null);

  const { shown, g, ma5, ma20 } = useMemo(() => {
    const start = maxBars !== undefined && bars.length > maxBars ? bars.length - maxBars : 0;
    const shownBars = bars.slice(start);
    const geo = buildCandleGeometry(shownBars, DIMS);
    // MA 以完整序列計算後再裁切,左緣才不會斷頭
    const m5 = movingAverage(bars, 5).slice(start);
    const m20 = movingAverage(bars, 20).slice(start);
    return { shown: shownBars, g: geo, ma5: m5, ma20: m20 };
  }, [bars, maxBars]);

  // useMemo 必須在 early return 之前(hooks 規則);空資料時 g.candles 為空、maLine 回空陣列
  const ma5Line = useMemo(() => (showMa ? maLine(ma5, g) : EMPTY_LINE), [showMa, ma5, g]);
  const ma20Line = useMemo(() => (showMa ? maLine(ma20, g) : EMPTY_LINE), [showMa, ma20, g]);

  if (shown.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-line bg-surface">
        <p className="text-sm text-ink-muted">無 K 線資料</p>
      </div>
    );
  }

  // x 軸標籤:等距取至多 6 個
  const labelStep = Math.max(1, Math.ceil(shown.length / 6));
  const hoverBar = hover !== null ? shown[hover] : undefined;
  const hoverCandle = hover !== null ? g.candles[hover] : undefined;

  function onMove(e: React.MouseEvent<SVGSVGElement>): void {
    const rect = e.currentTarget.getBoundingClientRect();
    // jsdom / 未佈局時 rect.width = 0 → scale 1(不 early-return,測試與真環境同路徑)
    const scale = rect.width > 0 ? DIMS.width / rect.width : 1;
    setHover(g.indexOf((e.clientX - rect.left) * scale));
  }

  return (
    // select-none:SVG 的 <text>(價位刻度 / 日期標籤)預設可選,在圖上拖曳會整片反白(SC-4)。
    // 不影響 hover — user-select 只管選取,mouse 事件照舊(W-10)。
    <figure className="select-none rounded-md border border-line bg-surface p-4">
      <svg
        viewBox={`0 0 ${DIMS.width} ${DIMS.height}`}
        className="w-full"
        role="img"
        aria-label="K 線圖"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        <ChartStatic g={g} shown={shown} ma5Line={ma5Line} ma20Line={ma20Line} labelStep={labelStep} />
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
