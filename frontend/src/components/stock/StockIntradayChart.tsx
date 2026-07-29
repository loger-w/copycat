import { memo, useId, useMemo, useState } from "react";

import { ChartReadout, type ReadoutField } from "@/components/chart/ChartReadout";
import { useChartToggles } from "@/hooks/useChartToggles";
import { clampTagX, clampTagY, overlaps, toSvgPoint } from "@/lib/chart-crosshair";
import { snapDown } from "@/lib/stock-tick";
import { useStockOverlay } from "@/hooks/useStockOverlay";
import type { StockAccum } from "@/lib/stock-accum";
import {
  buildIntradayGeometry,
  overlayLines,
  X_END_MIN,
  X_LABEL_H,
  X_START_MIN,
  type EnergyBar,
  type IntradayGeometry,
  type OverlayLine,
} from "@/lib/stock-intraday-svg";
import { cn } from "@/lib/utils";

const MAIN = { width: 800, height: 260 };
const SUB = { width: 800, height: 70 };
/** 軸標籤尺寸;time tag 的 y = mainH − boxH,底邊恰貼 viewBox 底不被裁 */
const PRICE_TAG = { w: 46, h: 14 };
const PCT_TAG = { w: 46, h: 14 };
const TIME_TAG = { w: 34, h: 13 };

function hhmm(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}

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

/** 分鐘 → x 座標。**吃 width 參數**(不再閉包模組常數):viewBox 高度改為可變後,
 *  memo 子元件必須經 props 拿尺寸,模組級純函數也一併參數化以免兩套來源漂移。 */
function toX(minute: number, width: number): number {
  return ((minute - X_START_MIN) / (X_END_MIN - X_START_MIN)) * width;
}

function barW(width: number): number {
  return Math.max(1, width / (X_END_MIN - X_START_MIN) - 0.4);
}

/** 靜態圖層 memo:hover 每 mousemove re-render 父層,線層不可每次重建(SC-1)。 */
const ChartStatic = memo(function ChartStatic({
  g,
  w,
  h,
  showVwap,
  oLines,
  clipAbove,
  clipBelow,
}: {
  g: IntradayGeometry;
  /** viewBox 寬 / 高。**必須是純量不是物件** —— 物件每次 render 新 identity 會打穿本 memo */
  w: number;
  h: number;
  showVwap: boolean;
  oLines: OverlayLine[];
  clipAbove: string;
  clipBelow: string;
}) {
  return (
    <g>
      {/* 平盤上下的填色與雙色價線共用這兩個 clip(SC-2)。
          id 必須全域唯一(SVG id 是 document 範圍),且只含識別字元 ——
          React 19 的 useId 產出 «r0» 形態,直接拼進 url(#…) 的解析行為未實測,
          解析失敗時 SVG 規範下該元素**不會被繪製**,是完全靜默的失敗。 */}
      {g.hasRef ? (
        <defs>
          <clipPath id={clipAbove}>
            <rect x={0} y={0} width={w} height={Math.max(0, g.refY)} />
          </clipPath>
          <clipPath id={clipBelow}>
            <rect
              x={0}
              y={g.refY}
              width={w}
              height={Math.max(0, h - X_LABEL_H - g.refY)}
            />
          </clipPath>
        </defs>
      ) : null}
      {g.upperY !== null ? (
        <line x1={0} x2={w} y1={g.upperY} y2={g.upperY} className="stroke-bull" strokeDasharray="4 3" strokeWidth={0.8} />
      ) : null}
      {g.lowerY !== null ? (
        <line x1={0} x2={w} y1={g.lowerY} y2={g.lowerY} className="stroke-bear" strokeDasharray="4 3" strokeWidth={0.8} />
      ) : null}
      <line x1={0} x2={w} y1={g.refY} y2={g.refY} className="stroke-line" strokeDasharray="2 3" strokeWidth={1} />
      {X_LABELS.map(({ minute }) => (
        <line
          key={minute}
          x1={toX(minute, w)}
          x2={toX(minute, w)}
          y1={0}
          y2={h - X_LABEL_H}
          className="stroke-line"
          strokeWidth={0.4}
        />
      ))}
      {/* Y 軸刻度:左價位、右 %(SC-2) */}
      {g.yTicks.map((t) => (
        <g key={`yt-${t.priceMilli}`}>
          <text
            data-testid="y-tick-price"
            x={2}
            y={Math.min(Math.max(t.y - 2, 8), h - 16)}
            className="fill-ink-dim"
            fontSize="0.625rem"
          >
            {fmt(t.priceMilli)}
          </text>
          {t.pct !== null ? (
            <text
              x={w - 2}
              y={Math.min(Math.max(t.y - 2, 8), h - 16)}
              textAnchor="end"
              className={cn(t.pct > 0 ? "fill-bull" : t.pct < 0 ? "fill-bear" : "fill-ink-dim")}
              fontSize="0.625rem"
            >
              {fmtPct(t.pct)}
            </text>
          ) : null}
        </g>
      ))}
      {/* 平盤與走勢線之間的填色(SC-3):同一個封閉多邊形,用 clip 切上下兩半分別塗色 */}
      {g.hasRef && g.areaPolygon !== "" ? (
        <>
          <polygon
            points={g.areaPolygon}
            className="fill-bull"
            fillOpacity="0.15"
            clipPath={`url(#${clipAbove})`}
          />
          <polygon
            points={g.areaPolygon}
            className="fill-bear"
            fillOpacity="0.15"
            clipPath={`url(#${clipBelow})`}
          />
        </>
      ) : null}
      {/* 疊線(CDP/MA)+ 右緣 label(SC-4) */}
      {oLines.map((l) => (
        <g key={`o-${l.label}`}>
          <line
            x1={0}
            x2={w - 34}
            y1={l.y}
            y2={l.y}
            className={
              l.kind === "cdp" ? "stroke-ink-dim" : l.label === "MA20" ? "stroke-ma20" : "stroke-ma5"
            }
            strokeDasharray="3 2"
            strokeWidth={0.8}
          />
          <text x={w - 32} y={l.y + 3} className="fill-ink-dim" fontSize="0.5625rem">
            {l.label}
          </text>
        </g>
      ))}
      {showVwap ? (
        // 均價線白色(SC-2.3);原本是琥珀金 profit,與新的紅綠雙色價線對比不足
        <polyline points={pts(g.vwapLine)} fill="none" className="stroke-ink" strokeWidth={1.2} />
      ) : null}
      {/* 主價線(SC-2):有昨收 → clip 切上下兩段,平盤上紅、平盤下綠;
          無昨收 → 沒有「平盤」可言,退回單條 accent 桃紅(不是白 —— 會跟 VWAP 同色) */}
      {g.hasRef ? (
        <>
          <polyline
            points={pts(g.priceLine)}
            fill="none"
            className="stroke-bull"
            strokeWidth={1.6}
            clipPath={`url(#${clipAbove})`}
          />
          <polyline
            points={pts(g.priceLine)}
            fill="none"
            className="stroke-bear"
            strokeWidth={1.6}
            clipPath={`url(#${clipBelow})`}
          />
        </>
      ) : (
        <polyline points={pts(g.priceLine)} fill="none" className="stroke-accent" strokeWidth={1.6} />
      )}
    </g>
  );
});

/** X 軸時間文字層。**刻意不在 ChartStatic 內**:hover 時間標會蓋住鄰近的靜態標籤,
 *  只蓋一半會露出殘字,所以重疊的要直接不畫 —— 那需要 hover 位置。至多 5 個 text 節點,
 *  每次 mousemove 重建的成本可忽略;真正重的蠟燭/量/線層仍在 memo 內(白名單 3)。 */
function XAxisLabels({
  w,
  h,
  tagSpan,
}: {
  w: number;
  h: number;
  tagSpan: [number, number] | null;
}) {
  return (
    <g>
      {X_LABELS.map(({ minute, label }) => {
        const x = toX(minute, w) + 2;
        if (tagSpan !== null && overlaps(x, x + 30, tagSpan[0], tagSpan[1])) return null;
        return (
          <text key={minute} x={x} y={h - 3} className="fill-ink-dim" fontSize="0.625rem">
            {label}
          </text>
        );
      })}
    </g>
  );
}

/** 內外盤能量副圖的 bar 層。**必須 memo**:hover 每個 mousemove 都 re-render 父層,
 *  這層最多 270 組 × 2 = 540 個 `<rect>`,不可每次重建(對齊 ChartStatic 的慣例)。
 *  hover 垂直線刻意畫在本元件之外(同一個 `<svg>` 內的獨立 `<g>`),不進 memo props。 */
const EnergySub = memo(function EnergySub({
  bars,
  w,
  h,
}: {
  bars: EnergyBar[];
  w: number;
  h: number;
}) {
  const bw = barW(w);
  return (
    <g>
      {bars.map((b) => (
        <g key={`e-${b.x}`}>
          <rect x={b.x} y={h - b.outerH} width={bw / 2} height={b.outerH} className="fill-bull" />
          <rect
            x={b.x + bw / 2}
            y={h - b.innerH}
            width={bw / 2}
            height={b.innerH}
            className="fill-bear"
          />
        </g>
      ))}
    </g>
  );
});

export function StockIntradayChart({ accum }: { accum: StockAccum }) {
  const { toggles, set } = useChartToggles();
  // 尺寸取模組常數(本 commit 值不變);之後改為隨可用高度變動的 props。
  // 純量而非物件:memo 子元件吃純量才不會每次 render 因 identity 改變而重建(W-5)。
  const mainW = MAIN.width;
  const mainH = MAIN.height;
  const subW = SUB.width;
  const subH = SUB.height;
  const overlayQ = useStockOverlay(accum.code || null, toggles.cdp || toggles.ma);
  // hover 帶 y:水平線是「自由量尺」(跟滑鼠),不再鎖該分鐘收盤價 —— 鎖收盤價的水平線
  // 與價格線重合、資訊冗餘,且量不到「現價到 CDP 線差幾%」這種盤中最常做的事。
  const [hover, setHover] = useState<{ min: number | null; y: number } | null>(null);
  // useId 產出含非識別字元(React 19 為 «r0»),過濾後才拼進 url(#…)
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const clipAbove = `${uid}-above`;
  const clipBelow = `${uid}-below`;

  const g = useMemo(
    () => buildIntradayGeometry({ minutes: accum.minutes, meta: accum.meta }, { width: mainW, height: mainH }),
    [accum.minutes, accum.meta],
  );

  const subGeo = useMemo(
    () => buildIntradayGeometry({ minutes: accum.minutes, meta: accum.meta }, { width: subW, height: subH }),
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

  const hoverMin = hover?.min ?? null;
  const hoverAgg = hoverMin !== null ? accum.minutes.get(hoverMin) : undefined;
  const ref = accum.meta?.ref ?? null;
  const plotBottom = mainH - X_LABEL_H;

  // 資訊列:沒 hover 顯示最新分鐘(即時態),不是空白
  const lastPt = g.priceLine[g.priceLine.length - 1];
  const shownMin = hoverAgg !== undefined ? hoverMin! : (lastPt?.minute ?? null);
  const shownAgg = shownMin !== null ? accum.minutes.get(shownMin) : undefined;
  const shownChg =
    shownAgg !== undefined && ref ? ((shownAgg.c - ref) / ref) * 100 : null;
  const fields: ReadoutField[] =
    shownAgg === undefined || shownMin === null
      ? [
          { label: "", value: "-" },
          { label: "", value: "-" },
          { label: "", value: "-" },
          { label: "量", value: "-" },
          { label: "外", value: "-" },
          { label: "內", value: "-" },
        ]
      : [
          { label: "", value: hhmm(shownMin) },
          {
            label: "",
            value: fmt(shownAgg.c),
            tone: shownChg === null ? undefined : shownChg > 0 ? "bull" : shownChg < 0 ? "bear" : undefined,
          },
          {
            label: "",
            value: shownChg === null ? "-" : `${shownChg > 0 ? "+" : ""}${shownChg.toFixed(2)}%`,
            tone: shownChg === null ? "muted" : shownChg > 0 ? "bull" : shownChg < 0 ? "bear" : "muted",
          },
          { label: "量", value: String(shownAgg.v) },
          { label: "外", value: String(shownAgg.o), tone: "bull" },
          { label: "內", value: String(shownAgg.i), tone: "bear" },
        ];

  const hoverPrice = hover !== null ? snapDown(g.priceAtY(hover.y)) : null;
  const hoverPct = hoverPrice !== null && ref ? ((hoverPrice - ref) / ref) * 100 : null;
  const timeTagX = hoverMin !== null ? clampTagX(toX(hoverMin, mainW), TIME_TAG.w, mainW) : null;
  const timeTagSpan: [number, number] | null =
    timeTagX === null ? null : [timeTagX, timeTagX + TIME_TAG.w];

  function onMove(e: React.MouseEvent<SVGSVGElement>): void {
    const rect = e.currentTarget.getBoundingClientRect();
    const { x, y } = toSvgPoint(e, rect, { width: mainW, height: mainH });
    const min = g.minuteOf(x);
    const ry = Math.round(y);
    // 值相同就回 prev 讓 React bail out:亞像素抖動不該觸發 re-render
    setHover((p) => (p !== null && p.min === min && p.y === ry ? p : { min, y: ry }));
  }

  const toggleDefs: { key: "vwap" | "cdp" | "ma"; label: string; available: boolean }[] = [
    { key: "vwap", label: "均價", available: true },
    { key: "cdp", label: "CDP", available: cdpAvailable },
    { key: "ma", label: "MA", available: maAvailable },
  ];

  return (
    // select-none:SVG 的 <text>(時間軸 / 價位 / % / 疊線 label)與下方內外盤 figcaption
    // 預設可選,在圖上拖曳會整片反白(SC-4)。不影響 hover(W-10)。
    <figure className="select-none rounded-md border border-line bg-surface p-4">
      {/* 頂列:左資訊條、右 toggle。高度以 rem 固定,與 K 線頂列逐項對稱(SC-6.7) */}
      <div className="mb-1 flex h-[1.375rem] items-center justify-between gap-2">
        <ChartReadout fields={fields} hovering={hoverAgg !== undefined} />
        <div className="flex shrink-0 gap-1">
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
      </div>
      <svg
        viewBox={`0 0 ${mainW} ${mainH}`}
        className="w-full"
        style={{ touchAction: "pan-y" }}
        role="img"
        aria-label="分時走勢圖"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        <ChartStatic
          g={g}
          w={mainW}
          h={mainH}
          showVwap={toggles.vwap}
          oLines={oLines}
          clipAbove={clipAbove}
          clipBelow={clipBelow}
        />
        <XAxisLabels w={mainW} h={mainH} tagSpan={timeTagSpan} />
        {/* hover 十字 + 軸標籤(SC-7)。
            分解退化:水平線 / 左價標 / 右 % 標只依賴滑鼠 y,無成交分鐘照畫;
            垂直線與資料點需要資料,缺就不畫(白名單 2:minuteOf 不 snap 最近)。 */}
        {hover !== null ? (
          <g pointerEvents="none">
            {hoverMin !== null && hoverAgg ? (
              <>
                <line
                  data-testid="crosshair-v"
                  x1={toX(hoverMin, mainW)}
                  x2={toX(hoverMin, mainW)}
                  y1={0}
                  y2={plotBottom}
                  className="stroke-ink-muted"
                  strokeDasharray="2 2"
                  strokeWidth={0.7}
                />
                {/* 該分鐘收盤的視覺錨 —— 水平線變量尺後,收盤位置改由這顆點承接 */}
                <circle cx={toX(hoverMin, mainW)} cy={g.toY(hoverAgg.c)} r={2.5} className="fill-ink" />
              </>
            ) : null}
            <line
              data-testid="crosshair-h"
              x1={0}
              x2={mainW}
              y1={hover.y}
              y2={hover.y}
              className="stroke-ink-muted"
              strokeDasharray="2 2"
              strokeWidth={0.7}
            />
            {/* 左緣價位標籤(snap 到合法 tick:顯示的價位要「可下單」) */}
            <g transform={`translate(0, ${clampTagY(hover.y, PRICE_TAG.h, plotBottom)})`}>
              <rect
                data-testid="price-tag"
                width={PRICE_TAG.w}
                height={PRICE_TAG.h}
                rx={2}
                className="fill-bg-deep stroke-line"
              />
              <text
                data-testid="price-tag-text"
                x={4}
                y={PRICE_TAG.h - 4}
                className="fill-ink"
                fontSize="0.625rem"
              >
                {hoverPrice !== null ? fmt(hoverPrice) : ""}
              </text>
            </g>
            {/* 右緣 % 標籤(江波圖獨有:K 線跨多日沒有「相對昨收」語意) */}
            {hoverPct !== null ? (
              <g
                transform={`translate(${mainW - PCT_TAG.w}, ${clampTagY(hover.y, PCT_TAG.h, plotBottom)})`}
              >
                <rect
                  data-testid="pct-tag"
                  width={PCT_TAG.w}
                  height={PCT_TAG.h}
                  rx={2}
                  className="fill-bg-deep stroke-line"
                />
                <text
                  data-testid="pct-tag-text"
                  x={PCT_TAG.w - 4}
                  y={PCT_TAG.h - 4}
                  textAnchor="end"
                  className={cn(
                    hoverPct > 0 ? "fill-bull" : hoverPct < 0 ? "fill-bear" : "fill-ink-dim",
                  )}
                  fontSize="0.625rem"
                >
                  {`${hoverPct > 0 ? "+" : ""}${hoverPct.toFixed(1)}%`}
                </text>
              </g>
            ) : null}
            {/* 底部時間標籤 */}
            {timeTagX !== null && hoverMin !== null ? (
              <g transform={`translate(${timeTagX}, ${mainH - TIME_TAG.h})`}>
                <rect
                  data-testid="time-tag"
                  width={TIME_TAG.w}
                  height={TIME_TAG.h}
                  rx={2}
                  className="fill-bg-deep stroke-line"
                />
                <text
                  data-testid="time-tag-text"
                  x={TIME_TAG.w / 2}
                  y={TIME_TAG.h - 3.5}
                  textAnchor="middle"
                  className="fill-ink"
                  fontSize="0.625rem"
                >
                  {hhmm(hoverMin)}
                </text>
              </g>
            ) : null}
          </g>
        ) : null}
      </svg>
      {/* 內外盤能量副圖。**不加 mt-1**:兩張圖的 svg 佔容器寬比例要相同(SC-6.7),
          多出的固定 4px 會讓比例隨容器寬漂移。 */}
      <svg viewBox={`0 0 ${subW} ${subH}`} className="w-full" role="img" aria-label="內外盤能量">
        <EnergySub bars={subGeo.energyBars} w={subW} h={subH} />
        {/* 垂直線延伸進副圖,讓該分鐘的內外盤 bar 可對位;畫在 memo 之外 */}
        {hoverMin !== null ? (
          <line
            x1={toX(hoverMin, mainW)}
            x2={toX(hoverMin, mainW)}
            y1={0}
            y2={subH}
            className="stroke-ink-muted"
            strokeDasharray="2 2"
            strokeWidth={0.7}
            pointerEvents="none"
          />
        ) : null}
      </svg>
      <figcaption className="mt-1 flex h-4 items-center justify-between font-mono text-xs text-ink-dim">
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
