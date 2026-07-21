import { useMemo } from "react";

import type { StockAccum } from "@/lib/stock-accum";
import { buildIntradayGeometry, X_END_MIN, X_START_MIN } from "@/lib/stock-intraday-svg";

const MAIN = { width: 800, height: 260 };
const SUB = { width: 800, height: 70 };

function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

function pts(line: { x: number; y: number }[]): string {
  return line.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

const X_LABELS = [540, 600, 660, 720, 780].map((m) => ({
  minute: m,
  label: `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`,
}));

export function StockIntradayChart({ accum }: { accum: StockAccum }) {
  const g = useMemo(
    () => buildIntradayGeometry({ minutes: accum.minutes, meta: accum.meta }, MAIN),
    [accum.minutes, accum.meta],
  );

  const subGeo = useMemo(
    () => buildIntradayGeometry({ minutes: accum.minutes, meta: accum.meta }, SUB),
    [accum.minutes, accum.meta],
  );

  if (g.priceLine.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-line bg-surface">
        <p className="text-sm text-ink-muted">尚無成交</p>
      </div>
    );
  }

  const toX = (minute: number): number =>
    ((minute - X_START_MIN) / (X_END_MIN - X_START_MIN)) * MAIN.width;
  const barW = Math.max(1, MAIN.width / (X_END_MIN - X_START_MIN) - 0.4);
  const total = accum.cumInner + accum.cumOuter;
  const outerPct = total > 0 ? ((accum.cumOuter / total) * 100).toFixed(1) : "-";

  return (
    <figure className="rounded-md border border-line bg-surface p-4">
      <svg viewBox={`0 0 ${MAIN.width} ${MAIN.height}`} className="w-full" role="img" aria-label="分時走勢圖">
        {/* 漲跌停界 / 昨收基準 */}
        {g.upperY !== null ? (
          <line x1={0} x2={MAIN.width} y1={g.upperY} y2={g.upperY} className="stroke-bull" strokeDasharray="4 3" strokeWidth={0.8} />
        ) : null}
        {g.lowerY !== null ? (
          <line x1={0} x2={MAIN.width} y1={g.lowerY} y2={g.lowerY} className="stroke-bear" strokeDasharray="4 3" strokeWidth={0.8} />
        ) : null}
        <line x1={0} x2={MAIN.width} y1={g.refY} y2={g.refY} className="stroke-line" strokeDasharray="2 3" strokeWidth={1} />
        {X_LABELS.map(({ minute, label }) => (
          <g key={minute}>
            <line x1={toX(minute)} x2={toX(minute)} y1={0} y2={MAIN.height - 14} className="stroke-line" strokeWidth={0.4} />
            <text x={toX(minute) + 2} y={MAIN.height - 3} className="fill-ink-dim" fontSize="0.625rem">
              {label}
            </text>
          </g>
        ))}
        {/* 量 bar(底部 1/4 高) */}
        {g.volumeBars.map((b) => (
          <rect
            key={`v-${b.x}`}
            x={b.x}
            y={MAIN.height - 14 - (b.h / MAIN.height) * (MAIN.height / 4)}
            width={barW}
            height={(b.h / MAIN.height) * (MAIN.height / 4)}
            className="fill-ink-dim/40"
          />
        ))}
        <polyline points={pts(g.vwapLine)} fill="none" className="stroke-profit" strokeWidth={1.2} />
        <polyline points={pts(g.priceLine)} fill="none" className="stroke-accent" strokeWidth={1.6} />
      </svg>
      {/* 內外盤能量副圖 */}
      <svg viewBox={`0 0 ${SUB.width} ${SUB.height}`} className="mt-1 w-full" role="img" aria-label="內外盤能量">
        {subGeo.energyBars.map((b) => (
          <g key={`e-${b.x}`}>
            <rect x={b.x} y={SUB.height - b.outerH} width={barW / 2} height={b.outerH} className="fill-bull" />
            <rect x={b.x + barW / 2} y={SUB.height - b.innerH} width={barW / 2} height={b.innerH} className="fill-bear" />
          </g>
        ))}
      </svg>
      <figcaption className="mt-1 flex justify-between font-mono text-xs text-ink-dim">
        <span>
          累積外盤 <span className="text-bull">{accum.cumOuter}</span> · 內盤{" "}
          <span className="text-bear">{accum.cumInner}</span> · 外盤比 {outerPct}%
        </span>
        <span>VWAP {accum.vwap != null ? fmt(accum.vwap) : "-"}</span>
      </figcaption>
    </figure>
  );
}
