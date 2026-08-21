/** 並排模式:每腿一張小卡,各自的絕對價走勢(SC-7)。
 *
 * 每腿 y 域各自 autofit —— 各腿價格量級差 15 倍(富台 3462 vs 道瓊 51909),共用域會讓
 * 低價腿壓成一條直線。跨腿比較走「重疊」模式(那邊才正規化成 %)。
 */
import { memo, useMemo } from "react";

import { fmtPct } from "@/lib/format";
import { buildLegGeometry, timeTicks, type RiverSize } from "@/lib/river-chart-svg";
import { pts } from "@/lib/svg-points";
import { cn } from "@/lib/utils";
import type { RiverLeg, RiverWindow } from "@/types";

import { RIVER_STROKES, RIVER_TEXTS } from "./river-colors";

const SIZE: RiverSize = { width: 320, height: 120 };

function fmtPrice(millipts: number): string {
  return (millipts / 1000).toFixed(2);
}

interface CardProps {
  legKey: string;
  leg: RiverLeg;
  window: RiverWindow;
  colorIndex: number;
}

/** 具名 memo:每秒的 delta 通常只動一兩腿(`useRiver.applyDelta` 對沒收到點的腿保留同參照,
 *  `window` 也隨 `{...prev}` 保持 identity),沒動的卡不必跟著重算全窗幾何。 */
const RiverCard = memo(function RiverCard({ legKey, leg, window: win, colorIndex }: CardProps) {
  const g = useMemo(() => buildLegGeometry(leg, win, SIZE), [leg, win]);
  const stroke = RIVER_STROKES[colorIndex % RIVER_STROKES.length]!;
  // 腿名文字色用 RIVER_TEXTS 常數,不用 stroke 字串 replace —— Tailwind 只產生
  // 原始碼裡出現過的 class,動態拼出來的 `text-river-N` 不會被生成
  const text = RIVER_TEXTS[colorIndex % RIVER_TEXTS.length]!;
  const ticks = timeTicks(win);
  return (
    <figure className="rounded-md border border-line bg-surface p-3" data-leg={legKey}>
      <div className="flex items-baseline gap-2">
        <h4 className={cn("text-xs font-bold", text)}>{leg.label}</h4>
        <span className="font-mono text-base text-ink">
          {leg.last !== null ? fmtPrice(leg.last) : "-"}
        </span>
        {g.pct !== null ? (
          <span
            className={cn(
              "font-mono text-xs",
              g.pct > 0 ? "text-bull" : g.pct < 0 ? "text-bear" : "text-ink-dim",
            )}
          >
            {fmtPct(g.pct)}
          </span>
        ) : (
          <span className="text-xs text-ink-dim">無資料</span>
        )}
      </div>
      <svg
        viewBox={`0 0 ${SIZE.width} ${SIZE.height}`}
        className="mt-1 w-full"
        role="img"
        aria-label={`${leg.label}分時走勢`}
      >
        {ticks.map(({ offset, label }) => {
          const x = (offset / Math.max(1, win.end_min - win.start_min)) * SIZE.width;
          return (
            <g key={offset}>
              <line
                x1={x}
                x2={x}
                y1={0}
                y2={SIZE.height - 12}
                className="stroke-line"
                strokeWidth={0.4}
              />
              <text x={x + 2} y={SIZE.height - 2} className="fill-ink-dim" fontSize="0.5rem">
                {label}
              </text>
            </g>
          );
        })}
        {/* 平盤 = 窗內第一筆(不是昨收:海外腿的參考價欄位未實測,design §2 決策) */}
        <line
          x1={0}
          x2={SIZE.width}
          y1={g.baseY}
          y2={g.baseY}
          className="stroke-line"
          strokeDasharray="2 3"
          strokeWidth={1}
        />
        {g.line.length > 0 ? (
          <polyline points={pts(g.line)} fill="none" className={stroke} strokeWidth={1.4} />
        ) : null}
      </svg>
    </figure>
  );
});

interface Props {
  order: string[];
  legs: Record<string, RiverLeg>;
  window: RiverWindow;
}

export function RiverCards({ order, legs, window: win }: Props) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {order.map((key, i) => {
        const leg = legs[key];
        if (leg === undefined) return null;
        return <RiverCard key={key} legKey={key} leg={leg} window={win} colorIndex={i} />;
      })}
    </div>
  );
}

export default RiverCards;
