import { useMemo, useState } from "react";

import { formatNtd, formatPts } from "@/lib/format";
import { areaPaths, buildScales, curvePath, interpCurve, invertX } from "@/lib/pnl-svg";
import type { Snapshot } from "@/types";

const BOX = { width: 960, height: 420, pad: 24 };

export function PnlChart({ snapshot }: { snapshot: Snapshot }) {
  const curve = snapshot.curve;
  // CR-1:state 只存游標指數位置;pnl 每次 render 由當前 curve 派生,
  // WS 推新 snapshot 時 readout 自動重算(超出新 domain 則隱藏)
  const [cursorX, setCursorX] = useState<number | null>(null);
  const parts = useMemo(() => {
    if (curve.length < 2) return null;
    const scales = buildScales(curve, BOX);
    return {
      scales,
      line: curvePath(curve, scales),
      areas: areaPaths(curve, scales),
    };
  }, [curve]);

  // SC-3 游標試算:座標換算假設 svg 為 w-full 等比渲染(viewBox 比例 = 渲染盒比例,DR-3)
  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    if (rect.width === 0) return;
    const px = ((e.clientX - rect.left) / rect.width) * BOX.width;
    setCursorX(invertX(px, curve, BOX));
  }

  const cursorPnl = cursorX !== null ? interpCurve(curve, cursorX) : null;

  if (parts === null) {
    return (
      <div className="flex h-105 items-center justify-center rounded-md border border-line bg-surface">
        <p className="text-sm text-ink-muted">尚無成交累積</p>
      </div>
    );
  }

  const { scales } = parts;
  const zeroY = scales.y(0);
  const spotPrice = snapshot.spot?.price ?? null;
  const spotX = spotPrice != null ? scales.x(spotPrice * 1000) : null;
  const firstX = curve[0]?.[0] ?? 0;
  const lastX = curve[curve.length - 1]?.[0] ?? 0;
  const yMax = Math.max(...curve.map(([, y]) => Math.abs(y)), 1);

  return (
    <figure className="rounded-md border border-line bg-surface p-4">
      <figcaption className="mb-2 flex items-baseline justify-between">
        <span className="text-sm font-medium text-ink">
          全市場綜合到期損益曲線
          <span className="ml-2 text-xs text-ink-muted">
            自 {snapshot.accumulated_from ?? "-"} 起累積
          </span>
        </span>
        <span className="font-mono text-xs text-ink-muted">
          極值為圖表範圍內 · 縱軸 {formatNtd(yMax)}
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${BOX.width} ${BOX.height}`}
        role="img"
        aria-label="綜合到期損益曲線"
        className="w-full"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setCursorX(null)}
      >
        {/* 零線 */}
        <line
          x1={BOX.pad}
          x2={BOX.width - BOX.pad}
          y1={zeroY}
          y2={zeroY}
          className="stroke-line"
          strokeWidth={1}
        />
        {/* 獲利 / 虧損分區 */}
        <path d={parts.areas.profit} className="fill-profit/25" />
        <path d={parts.areas.loss} className="fill-loss/25" />
        {/* 主曲線 */}
        <path
          d={parts.line}
          fill="none"
          className="stroke-ink"
          strokeWidth={2}
          strokeLinejoin="round"
        />
        {/* 現價虛線 */}
        {spotX != null && spotX >= BOX.pad && spotX <= BOX.width - BOX.pad && (
          <line
            x1={spotX}
            x2={spotX}
            y1={BOX.pad}
            y2={BOX.height - BOX.pad}
            className="stroke-accent"
            strokeWidth={1.5}
            strokeDasharray="4 4"
          />
        )}
        {/* BEP 標記 */}
        {(snapshot.beps ?? []).map((bep) => (
          <circle
            key={bep}
            cx={scales.x(bep * 1000)}
            cy={zeroY}
            r={5}
            className="fill-profit stroke-bg"
            strokeWidth={1.5}
          />
        ))}
        {/* X 軸端點標籤 */}
        <text
          x={BOX.pad}
          y={BOX.height - 6}
          className="fill-ink-muted font-mono text-[11px]"
        >
          {formatPts(firstX / 1000)}
        </text>
        <text
          x={BOX.width - BOX.pad}
          y={BOX.height - 6}
          textAnchor="end"
          className="fill-ink-muted font-mono text-[11px]"
        >
          {formatPts(lastX / 1000)}
        </text>
        {spotX != null && (
          <text
            x={spotX}
            y={16}
            textAnchor="middle"
            className="fill-accent font-mono text-[11px]"
          >
            現價 {spotPrice != null ? formatPts(spotPrice) : ""}
          </text>
        )}
        {/* SC-3 游標 crosshair + 右上角 readout(DR-6:固定位,與現價標籤空間分離) */}
        {cursorX !== null && cursorPnl !== null && (
          <g className="pointer-events-none">
            <line
              x1={scales.x(cursorX)}
              x2={scales.x(cursorX)}
              y1={BOX.pad}
              y2={BOX.height - BOX.pad}
              className="stroke-ink-muted"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
            <circle
              cx={scales.x(cursorX)}
              cy={scales.y(cursorPnl)}
              r={3.5}
              className="fill-ink stroke-bg"
              strokeWidth={1.5}
            />
            <text
              x={BOX.width - BOX.pad}
              y={16}
              textAnchor="end"
              className="fill-ink font-mono text-[11px]"
            >
              {formatPts(cursorX / 1000)} ▸ {formatNtd(cursorPnl)}
            </text>
          </g>
        )}
      </svg>
      <div className="mt-2 flex gap-4 text-xs text-ink-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-3 bg-profit/50" aria-hidden />
          綜合到期獲利區間
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-3 bg-loss/50" aria-hidden />
          綜合到期虧損區間
        </span>
        {(snapshot.beps ?? []).length > 0 && (
          <span className="font-mono">
            BEP:{(snapshot.beps ?? []).map(formatPts).join(" / ")}
          </span>
        )}
      </div>
    </figure>
  );
}
