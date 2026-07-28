import { memo, useMemo, useState } from "react";

import { useChartToggles } from "@/hooks/useChartToggles";
import { useStockOverlay } from "@/hooks/useStockOverlay";
import type { StockAccum } from "@/lib/stock-accum";
import {
  buildIntradayGeometry,
  overlayLines,
  X_END_MIN,
  X_START_MIN,
  type IntradayGeometry,
  type OverlayLine,
} from "@/lib/stock-intraday-svg";
import { cn } from "@/lib/utils";

const MAIN = { width: 800, height: 260 };
const SUB = { width: 800, height: 70 };

function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

function fmtPct(pct: number): string {
  if (pct === 0) return "0%";
  return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

function pts(line: { x: number; y: number }[]): string {
  return line.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

const X_LABELS = [540, 600, 660, 720, 780].map((m) => ({
  minute: m,
  label: `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`,
}));

function toX(minute: number): number {
  return ((minute - X_START_MIN) / (X_END_MIN - X_START_MIN)) * MAIN.width;
}

const BAR_W = Math.max(1, MAIN.width / (X_END_MIN - X_START_MIN) - 0.4);

const DIR_CLASS = {
  up: "fill-bull/50",
  down: "fill-bear/50",
  flat: "fill-ink-dim/40",
} as const;

/** 靜態圖層 memo:hover 每 mousemove re-render 父層,量 bar/線層不可每次重建(SC-1)。 */
const ChartStatic = memo(function ChartStatic({
  g,
  showVwap,
  oLines,
}: {
  g: IntradayGeometry;
  showVwap: boolean;
  oLines: OverlayLine[];
}) {
  return (
    <g>
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
      {/* Y 軸刻度:左價位、右 %(SC-2) */}
      {g.yTicks.map((t) => (
        <g key={`yt-${t.priceMilli}`}>
          <text x={2} y={Math.min(Math.max(t.y - 2, 8), MAIN.height - 16)} className="fill-ink-dim" fontSize="0.625rem">
            {fmt(t.priceMilli)}
          </text>
          {t.pct !== null ? (
            <text
              x={MAIN.width - 2}
              y={Math.min(Math.max(t.y - 2, 8), MAIN.height - 16)}
              textAnchor="end"
              className={cn(t.pct > 0 ? "fill-bull" : t.pct < 0 ? "fill-bear" : "fill-ink-dim")}
              fontSize="0.625rem"
            >
              {fmtPct(t.pct)}
            </text>
          ) : null}
        </g>
      ))}
      {/* 量 bar(底部 1/4 高;依分鐘漲跌著色 — SC-3) */}
      {g.volumeBars.map((b) => (
        <rect
          key={`v-${b.x}`}
          x={b.x}
          y={MAIN.height - 14 - (b.h / MAIN.height) * (MAIN.height / 4)}
          width={BAR_W}
          height={(b.h / MAIN.height) * (MAIN.height / 4)}
          className={DIR_CLASS[b.dir]}
        />
      ))}
      {/* 疊線(CDP/MA)+ 右緣 label(SC-4) */}
      {oLines.map((l) => (
        <g key={`o-${l.label}`}>
          <line
            x1={0}
            x2={MAIN.width - 34}
            y1={l.y}
            y2={l.y}
            className={
              l.kind === "cdp" ? "stroke-ink-dim" : l.label === "MA20" ? "stroke-ma20" : "stroke-ma5"
            }
            strokeDasharray="3 2"
            strokeWidth={0.8}
          />
          <text x={MAIN.width - 32} y={l.y + 3} className="fill-ink-dim" fontSize="0.5625rem">
            {l.label}
          </text>
        </g>
      ))}
      {showVwap ? (
        <polyline points={pts(g.vwapLine)} fill="none" className="stroke-profit" strokeWidth={1.2} />
      ) : null}
      <polyline points={pts(g.priceLine)} fill="none" className="stroke-accent" strokeWidth={1.6} />
    </g>
  );
});

export function StockIntradayChart({ accum }: { accum: StockAccum }) {
  const { toggles, set } = useChartToggles();
  const overlayQ = useStockOverlay(accum.code || null, toggles.cdp || toggles.ma);
  const [hoverMin, setHoverMin] = useState<number | null>(null);

  const g = useMemo(
    () => buildIntradayGeometry({ minutes: accum.minutes, meta: accum.meta }, MAIN),
    [accum.minutes, accum.meta],
  );

  const subGeo = useMemo(
    () => buildIntradayGeometry({ minutes: accum.minutes, meta: accum.meta }, SUB),
    [accum.minutes, accum.meta],
  );

  const overlay = overlayQ.data ?? null;
  // 可用性:資料未回前視為可用(不預先反灰);回了但該類 null / 請求失敗 → 反灰 + 顯示 off
  const cdpAvailable = overlayQ.isError ? false : overlay ? overlay.cdp !== null : true;
  const maAvailable = overlayQ.isError
    ? false
    : overlay
      ? overlay.ma5 !== null || overlay.ma20 !== null
      : true;

  const oLines = useMemo(
    () =>
      overlay
        ? overlayLines(overlay, g, {
            cdp: toggles.cdp && cdpAvailable,
            ma: toggles.ma && maAvailable,
          })
        : [],
    [overlay, g, toggles.cdp, toggles.ma, cdpAvailable, maAvailable],
  );

  if (g.priceLine.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-line bg-surface">
        <p className="text-sm text-ink-muted">尚無成交</p>
      </div>
    );
  }

  const total = accum.cumInner + accum.cumOuter;
  const outerPct = total > 0 ? ((accum.cumOuter / total) * 100).toFixed(1) : "-";

  const hoverAgg = hoverMin !== null ? accum.minutes.get(hoverMin) : undefined;
  const ref = accum.meta?.ref ?? null;
  const hoverChg =
    hoverAgg && ref ? (((hoverAgg.c - ref) / ref) * 100).toFixed(2) : null;
  const hoverLabel =
    hoverMin !== null
      ? `${String(Math.floor(hoverMin / 60)).padStart(2, "0")}:${String(hoverMin % 60).padStart(2, "0")}`
      : "";

  function onMove(e: React.MouseEvent<SVGSVGElement>): void {
    const rect = e.currentTarget.getBoundingClientRect();
    if (rect.width <= 0) return;
    const x = ((e.clientX - rect.left) / rect.width) * MAIN.width;
    setHoverMin(g.minuteOf(x));
  }

  const toggleDefs: { key: "vwap" | "cdp" | "ma"; label: string; available: boolean }[] = [
    { key: "vwap", label: "均價", available: true },
    { key: "cdp", label: "CDP", available: cdpAvailable },
    { key: "ma", label: "MA", available: maAvailable },
  ];

  return (
    <figure className="rounded-md border border-line bg-surface p-4">
      <div className="mb-1 flex justify-end gap-1">
        {toggleDefs.map(({ key, label, available }) => (
          <button
            key={key}
            type="button"
            aria-pressed={toggles[key] && available}
            disabled={!available}
            title={available ? undefined : "無日線資料"}
            onClick={() => set(key, !toggles[key])}
            className={cn(
              "rounded border px-2 py-0.5 text-xs",
              toggles[key] && available
                ? "border-accent text-accent"
                : "border-line text-ink-dim",
              !available && "opacity-40",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${MAIN.width} ${MAIN.height}`}
        className="w-full"
        role="img"
        aria-label="分時走勢圖"
        onMouseMove={onMove}
        onMouseLeave={() => setHoverMin(null)}
      >
        <ChartStatic g={g} showVwap={toggles.vwap} oLines={oLines} />
        {/* hover 十字 + tooltip(SC-1) */}
        {hoverMin !== null && hoverAgg ? (
          <g pointerEvents="none">
            <line
              x1={toX(hoverMin)}
              x2={toX(hoverMin)}
              y1={0}
              y2={MAIN.height - 14}
              className="stroke-ink-muted"
              strokeDasharray="2 2"
              strokeWidth={0.7}
            />
            <line
              x1={0}
              x2={MAIN.width}
              y1={g.toY(hoverAgg.c)}
              y2={g.toY(hoverAgg.c)}
              className="stroke-ink-muted"
              strokeDasharray="2 2"
              strokeWidth={0.7}
            />
            <g transform={`translate(${Math.min(toX(hoverMin) + 8, MAIN.width - 130)}, 10)`}>
              <rect width={122} height={34} rx={3} className="fill-bg-deep/90 stroke-line" />
              <text x={6} y={13} className="fill-ink" fontSize="0.625rem">
                {hoverLabel} · {fmt(hoverAgg.c)}
              </text>
              <text x={6} y={27} className="fill-ink-dim" fontSize="0.625rem">
                {hoverChg !== null ? `${Number(hoverChg) > 0 ? "+" : ""}${hoverChg}%` : "-"} · 量{" "}
                {hoverAgg.v}
              </text>
            </g>
          </g>
        ) : null}
      </svg>
      {/* 內外盤能量副圖 */}
      <svg viewBox={`0 0 ${SUB.width} ${SUB.height}`} className="mt-1 w-full" role="img" aria-label="內外盤能量">
        {subGeo.energyBars.map((b) => (
          <g key={`e-${b.x}`}>
            <rect x={b.x} y={SUB.height - b.outerH} width={BAR_W / 2} height={b.outerH} className="fill-bull" />
            <rect x={b.x + BAR_W / 2} y={SUB.height - b.innerH} width={BAR_W / 2} height={b.innerH} className="fill-bear" />
          </g>
        ))}
      </svg>
      <figcaption className="mt-1 flex justify-between font-mono text-xs text-ink-dim">
        <span>
          累積外盤 <span className="text-bull">{accum.cumOuter}</span> · 內盤{" "}
          <span className="text-bear">{accum.cumInner}</span> · 外盤比 {outerPct}%
        </span>
        <span>
          {overlay?.date && (toggles.cdp || toggles.ma) ? `疊線基準 ${overlay.date} · ` : ""}
          VWAP {accum.vwap != null ? fmt(accum.vwap) : "-"}
        </span>
      </figcaption>
    </figure>
  );
}
