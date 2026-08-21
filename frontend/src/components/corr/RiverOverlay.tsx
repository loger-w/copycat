/** 重疊模式:六腿正規化成「相對窗首 %」疊在一張圖 + 十字線讀值(SC-8/SC-9)。 */
import { useMemo, useState } from "react";

import { fmtPct } from "@/lib/format";
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
/** 首筆晚於最早腿超過此分鐘數才標「自 HH:MM 起算 0%」(同場開盤的腿差 1–2 格不算) */
const LATE_START_MIN = 5;

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
  // 幾何與純 derive 自幾何的量一起包:游標在圖上滑一下是數十則 mousemove,每則都
  // setCursor → re-render,而滿窗夜盤是 840 分鐘 × 七腿。`readout` 依賴 cursor,
  // **不能**進來(進來就會被凍在 cursor === null,讀值列永遠是「—」而線照畫)。
  const { g, labelYs, lateStarts } = useMemo(() => {
    const geo = buildOverlayGeometry(entries, win, SIZE);
    // 右緣腿名防疊(real-env 截圖:六腿價位接近時標籤互相蓋住)
    const ys = spreadLabelYs(
      geo.lines.map((l) => (l.pts.length > 0 ? l.pts[l.pts.length - 1]!.y + 3 : 0)),
      11,
      SIZE.height - 14,
    );
    // 基準時點分歧註記:每腿以「本場自己的第一筆」為 0%(buildOverlayGeometry),開盤時間不同的腿
    // (小日經 OSE 夜盤台北 16:00 開,其餘腿 15:00)基準時點就不同,線的絕對高度不可比、只有
    // 斜率可比。首筆晚於最早腿超過 LATE_START_MIN 分鐘者在標頭列標示起算時刻;零改幾何。
    const firstOffsets = geo.lines.flatMap((l) => (l.pts.length > 0 ? [l.pts[0]!.offset] : []));
    const earliest = firstOffsets.length ? Math.min(...firstOffsets) : 0;
    return {
      g: geo,
      labelYs: ys,
      lateStarts: geo.lines.flatMap((l) =>
        l.pts.length > 0 && l.pts[0]!.offset - earliest > LATE_START_MIN
          ? [{ key: l.key, label: l.label, colorIndex: l.colorIndex, at: l.pts[0]!.offset }]
          : [],
      ),
    };
  }, [entries, win]);
  const span = Math.max(1, win.end_min - win.start_min);
  const toX = (offset: number): number => (offset / span) * SIZE.width;

  // 座標換算假設 svg 為 w-full 等比渲染(viewBox 比例 = 渲染盒比例;同 PnlChart 手法)
  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>): void {
    const rect = e.currentTarget.getBoundingClientRect();
    if (rect.width === 0) return;
    const px = ((e.clientX - rect.left) / rect.width) * SIZE.width;
    setCursor(offsetAtX(px, win, SIZE));
  }

  // 讀值列:唯一依賴 cursor 的量,刻意留在幾何 useMemo 之外(見上)。
  // 由 `entries`(不是 `g.lines`)產生:`buildOverlayGeometry` 會把全窗無值的腿濾掉 ——
  // 那是**圖上**的正確語意(沒有第一筆就沒有 0% 基準,畫出來會被看成一條 0% 直線),但讀值列
  // 照抄這份過濾的話,那一腿在勾選列上亮著、讀值列卻整格消失,使用者看不出是「這腿沒資料」
  // 還是自己數錯腿。改以 entries 對位(順序 = legend 順序,以 key 找幾何),空腿印「—」。
  const readout =
    cursor === null
      ? null
      : entries.map((e) => {
          const line = g.lines.find((l) => l.key === e.key);
          const hit = line?.pts.find((p) => p.offset === cursor);
          return { key: e.key, label: e.label, colorIndex: e.colorIndex, hit };
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
        {lateStarts.map(({ key, label, colorIndex, at }) => (
          <span
            key={`late-${key}`}
            className={cn("ml-auto text-ink-dim", RIVER_TEXTS[colorIndex % RIVER_TEXTS.length])}
            title="重疊圖各腿以本場首筆為 0%;開盤時間不同的腿基準時點不同,只比斜率不比高度"
          >
            {label} 自 {hhmm(win.start_min + at)} 起算 0%
          </span>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${SIZE.width} ${SIZE.height}`}
        className="mt-1 w-full"
        role="img"
        aria-label="各腿重疊走勢"
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
