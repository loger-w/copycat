/** 重疊模式:六腿正規化成「相對窗首 %」疊在一張圖 + 十字線讀值(SC-8/SC-9)。 */
import { useState } from "react";

import {
  buildOverlayGeometry,
  offsetAtX,
  spreadLabelYs,
  timeTicks,
  type OverlayEntry,
  type RiverSize,
} from "@/lib/river-chart-svg";
import { pts } from "@/lib/svg-points";
import { cn } from "@/lib/utils";
import type { RiverWindow } from "@/types";

import { RIVER_FILLS, RIVER_STROKES, RIVER_TEXTS } from "./river-colors";

const SIZE: RiverSize = { width: 960, height: 340 };
/** base 腿(序位 0)畫粗線,其餘細線 */
const BASE_STROKE_W = 2;
const LEG_STROKE_W = 1.2;

function fmtPct(pct: number): string {
  return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function hhmm(minuteOfDay: number): string {
  const m = ((minuteOfDay % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

interface Props {
  entries: OverlayEntry[];
  window: RiverWindow;
  baseKey: string;
}

export function RiverOverlay({ entries, window: win, baseKey }: Props) {
  const [cursor, setCursor] = useState<number | null>(null);
  const g = buildOverlayGeometry(entries, win, SIZE);
  const span = Math.max(1, win.end_min - win.start_min);
  const toX = (offset: number): number => (offset / span) * SIZE.width;

  // 座標換算假設 svg 為 w-full 等比渲染(viewBox 比例 = 渲染盒比例;同 PnlChart 手法)
  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>): void {
    const rect = e.currentTarget.getBoundingClientRect();
    if (rect.width === 0) return;
    const px = ((e.clientX - rect.left) / rect.width) * SIZE.width;
    setCursor(offsetAtX(px, win, SIZE));
  }

  // 右緣腿名防疊(real-env 截圖:六腿價位接近時標籤互相蓋住)
  const labelYs = spreadLabelYs(
    g.lines.map((l) => (l.pts.length > 0 ? l.pts[l.pts.length - 1]!.y + 3 : 0)),
    11,
    SIZE.height - 14,
  );

  const readout =
    cursor === null
      ? null
      : g.lines.map((line) => {
          const hit = line.pts.find((p) => p.offset === cursor);
          return { key: line.key, label: line.label, colorIndex: line.colorIndex, hit };
        });

  return (
    <figure className="rounded-md border border-line bg-surface p-3">
      <div className="flex flex-wrap items-baseline gap-3 text-xs">
        <span className="text-ink-dim">
          {cursor === null ? "游標移入圖內看各腿讀值" : hhmm(win.start_min + cursor)}
        </span>
        {readout?.map(({ key, label, colorIndex, hit }) => (
          <span key={key} className={cn("font-mono", RIVER_TEXTS[colorIndex % RIVER_TEXTS.length])}>
            {label} {hit ? fmtPct(hit.pct) : "—"}
          </span>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${SIZE.width} ${SIZE.height}`}
        className="mt-1 w-full"
        role="img"
        aria-label="六腿重疊走勢"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setCursor(null)}
      >
        {timeTicks(win).map(({ offset, label }) => (
          <g key={offset}>
            <line
              x1={toX(offset)}
              x2={toX(offset)}
              y1={0}
              y2={SIZE.height - 12}
              className="stroke-line"
              strokeWidth={0.4}
            />
            <text
              x={toX(offset) + 2}
              y={SIZE.height - 2}
              className="fill-ink-dim"
              fontSize="0.625rem"
            >
              {label}
            </text>
          </g>
        ))}
        {/* 0%(= 各腿窗首)基準線 */}
        <line
          x1={0}
          x2={SIZE.width}
          y1={g.zeroY}
          y2={g.zeroY}
          className="stroke-line"
          strokeDasharray="2 3"
          strokeWidth={1}
        />
        <text x={2} y={g.zeroY - 3} className="fill-ink-dim" fontSize="0.625rem">
          0%
        </text>
        <text x={2} y={11} className="fill-ink-dim" fontSize="0.625rem">
          {fmtPct(g.pctDomain[1])}
        </text>
        <text x={2} y={SIZE.height - 16} className="fill-ink-dim" fontSize="0.625rem">
          {fmtPct(g.pctDomain[0])}
        </text>
        {g.lines.map((line, i) => (
          <g key={line.key}>
            <polyline
              points={pts(line.pts)}
              fill="none"
              className={RIVER_STROKES[line.colorIndex % RIVER_STROKES.length]}
              strokeWidth={line.key === baseKey ? BASE_STROKE_W : LEG_STROKE_W}
            />
            {line.pts.length > 0 ? (
              <text
                x={Math.min(line.pts[line.pts.length - 1]!.x + 4, SIZE.width - 30)}
                y={labelYs[i]}
                className={RIVER_FILLS[line.colorIndex % RIVER_FILLS.length]}
                fontSize="0.625rem"
              >
                {line.label}
              </text>
            ) : null}
          </g>
        ))}
        {cursor !== null ? (
          <line
            x1={toX(cursor)}
            x2={toX(cursor)}
            y1={0}
            y2={SIZE.height - 12}
            className="stroke-ink-dim"
            strokeWidth={0.8}
          />
        ) : null}
      </svg>
    </figure>
  );
}

export default RiverOverlay;
