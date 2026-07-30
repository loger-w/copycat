import { memo, useId, useMemo, useState } from "react";

import { ChartReadout, type ReadoutField } from "@/components/chart/ChartReadout";
import { useChartToggles } from "@/hooks/useChartToggles";
import { clampTagX, clampTagY, overlaps, toSvgPoint } from "@/lib/chart-crosshair";
import { fmtTickPrice, snapDown } from "@/lib/stock-tick";
import { useStockOverlay } from "@/hooks/useStockOverlay";
import type { StockAccum } from "@/lib/stock-accum";
import {
  buildIntradayGeometry,
  lastPoint,
  minuteToX,
  overlayLines,
  plotWidth,
  R_AXIS_W,
  X_END_MIN,
  X_LABEL_H,
  SUB_TOP_PAD,
  X_START_MIN,
  Y_AXIS_W,
  type EnergyBar,
  type IntradayGeometry,
  type OverlayLevel,
  type OverlayLine,
} from "@/lib/stock-intraday-svg";
import { cn } from "@/lib/utils";

const MAIN = { width: 800, height: 260 };
const SUB = { width: 800, height: 70 };
/** 軸標籤尺寸;time tag 的 y = mainH − boxH,底邊恰貼 viewBox 底不被裁。
 *  寬度**直接取 `Y_AXIS_W`** 不另寫一份數字:兩份靠註解維持相等的話,任一方改動就讓
 *  「hover 價位標壓在走勢線上」這個本輪要修的症狀復發,而且沒有測試會發現。 */
const PRICE_TAG = { w: Y_AXIS_W, h: 14 };
const TIME_TAG = { w: 34, h: 13 };

function hhmm(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}

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

function barW(width: number): number {
  return Math.max(1, plotWidth(width) / (X_END_MIN - X_START_MIN) - 0.4);
}

/** 疊線配色(SC-2)。名稱從右緣移除後,五條 CDP 只剩顏色可分辨 ——
 *  上方壓力位紅、下方支撐位綠(台股紅漲綠跌),中軸取琥珀金不與紅綠系混淆。 */
const LEVEL_STROKE: Record<OverlayLevel, string> = {
  ah: "stroke-bull",
  nh: "stroke-bull/55",
  cdp: "stroke-profit",
  nl: "stroke-bear/55",
  al: "stroke-bear",
  ma5: "stroke-ma5",
  ma20: "stroke-ma20",
};

const LEVEL_FILL: Record<OverlayLevel, string> = {
  ah: "fill-bull",
  nh: "fill-bull/70",
  cdp: "fill-profit",
  nl: "fill-bear/70",
  al: "fill-bear",
  ma5: "fill-ma5",
  ma20: "fill-ma20",
};

/** 左緣價位刻度的配色(round5 C):高於平盤紅、低於平盤綠、平盤白。
 *  刻度值本身不變 —— 它們本來就是 ±10/8/6/4/2/0% 對應的價位,user 要的是「對應百分比的
 *  數字」而不是顯示百分比字樣。`ref` 不可得(無昨收)時全部退回中性灰:那時沒有「平盤」
 *  可言,硬分紅綠等於憑首筆成交價編一個基準出來(同 `hasRef` 的既有紀律)。 */
function tickTone(priceMilli: number, refMilli: number | null): string {
  if (refMilli === null || refMilli <= 0) return "fill-ink-dim";
  if (priceMilli > refMilli) return "fill-bull";
  if (priceMilli < refMilli) return "fill-bear";
  return "fill-ink";
}

/** 右緣文字:CDP 五線印合法價位 + `*`(一眼分出是 CDP 不是 MA);MA 維持名稱 */
function levelText(level: OverlayLevel, priceMilli: number): string {
  return level === "ma5" || level === "ma20"
    ? level.toUpperCase()
    : `${fmtTickPrice(priceMilli)}*`;
}

/** 靜態圖層 memo:hover 每 mousemove re-render 父層,線層不可每次重建(SC-1)。 */
const ChartStatic = memo(function ChartStatic({
  g,
  w,
  h,
  refMilli,
  showVwap,
  oLines,
  clipAbove,
  clipBelow,
  highMilli,
  lowMilli,
  highY,
  lowY,
}: {
  g: IntradayGeometry;
  /** viewBox 寬 / 高。**必須是純量不是物件** —— 物件每次 render 新 identity 會打穿本 memo */
  w: number;
  h: number;
  /** 參考價(左緣刻度判色用);純量,memo 安全 */
  refMilli: number | null;
  showVwap: boolean;
  oLines: OverlayLine[];
  clipAbove: string;
  clipBelow: string;
  /** 當日高低(毫元)與其 y;**域外 / 缺值時 y 為 null → 不畫**。純量,memo 安全 */
  highMilli: number | null;
  lowMilli: number | null;
  highY: number | null;
  lowY: number | null;
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
      {/* 漲跌停虛線已移除(round3 項 4):Y 域恰為 [lower, upper],兩條線本來就貼死在
          上下緣、與最外側刻度重合,是純粹的視覺噪音。左緣的漲跌停價位文字仍在。 */}
      <line x1={Y_AXIS_W} x2={w - R_AXIS_W} y1={g.refY} y2={g.refY} className="stroke-line" strokeDasharray="2 3" strokeWidth={1} />
      {X_LABELS.map(({ minute }) => (
        <line
          key={minute}
          x1={minuteToX(minute, w)}
          x2={minuteToX(minute, w)}
          y1={0}
          y2={h - X_LABEL_H}
          className="stroke-line"
          strokeWidth={0.4}
        />
      ))}
      {/* Y 軸刻度:左緣價位(round3 SC-1:右緣 % 欄移除,讓位給 CDP 價位標)
          + 對應水平格線(round4 項 4)。線起於價位帶右緣,不穿過價位文字;
          風格與 K 線圖的 y 軸格線一致(stroke-line / 2 3 / 0.5)。 */}
      {g.yTicks.map((t) => (
        <g key={`yt-${t.priceMilli}`}>
          <line
            data-testid="y-grid"
            x1={Y_AXIS_W}
            x2={w - R_AXIS_W}
            y1={t.y}
            y2={t.y}
            className="stroke-line"
            strokeDasharray="2 3"
            strokeWidth={0.5}
          />
          <text
            data-testid="y-tick-price"
            x={2}
            y={Math.min(Math.max(t.y - 2, 8), h - 16)}
            className={tickTone(t.priceMilli, refMilli)}
            fontSize="0.625rem"
          >
            {fmt(t.priceMilli)}
          </text>
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
      {/* 疊線(CDP/MA)+ 右緣價位標(round3 SC-2) */}
      {oLines.map((l) => (
        // key 用 level 不用文字:文字現在是價位,兩條線同價時會撞 key
        <g key={`o-${l.level}`}>
          <line
            x1={Y_AXIS_W}
            x2={w - R_AXIS_W}
            y1={l.y}
            y2={l.y}
            className={LEVEL_STROKE[l.level]}
            strokeDasharray="3 2"
            strokeWidth={0.8}
          />
          <text
            x={w - R_AXIS_W + 2}
            y={l.y + 3}
            className={LEVEL_FILL[l.level]}
            fontSize="0.5625rem"
          >
            {levelText(l.level, l.priceMilli)}
          </text>
        </g>
      ))}
      {/* 當日高低(SC-1)。虛線節奏 4 3 / 0.8 與 y 軸格線(2 3 / 0.5)刻意不同,
          肉眼可區分「這是今天的高低」而不是又一條格線 */}
      {([
        ["day-high", highY, highMilli],
        ["day-low", lowY, lowMilli],
      ] as const).map(([id, y, milli]) =>
        y === null || milli === null ? null : (
          <g key={id}>
            <line
              data-testid={id}
              x1={Y_AXIS_W}
              x2={w - R_AXIS_W}
              y1={y}
              y2={y}
              className="stroke-ink-muted"
              strokeDasharray="4 3"
              strokeWidth={0.8}
            />
            <text
              data-testid={`${id}-label`}
              x={w - R_AXIS_W + 2}
              y={y - 2}
              className="fill-ink-muted stroke-surface"
              strokeWidth={2}
              paintOrder="stroke"
              fontSize="0.5625rem"
            >
              {fmt(milli)}
            </text>
          </g>
        ),
      )}
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
        const x = minuteToX(minute, w) + 2;
        if (tagSpan !== null && overlaps(x, x + 30, tagSpan[0], tagSpan[1])) return null;
        return (
          <text key={minute} x={x} y={h - 3} className="fill-time" fontSize="0.625rem">
            {label}
          </text>
        );
      })}
    </g>
  );
}

/** 成交量副圖的 bar 層(round5 E:由「內外盤並排」改為「總量堆疊」)。
 *  **必須 memo**:hover 每個 mousemove 都 re-render 父層,這層最多 270 組 × 3 個
 *  `<rect>`,不可每次重建(對齊 ChartStatic 的慣例)。
 *  hover 垂直線刻意畫在本元件之外(同一個 `<svg>` 內的獨立 `<g>`),不進 memo props。 */
const EnergySub = memo(function EnergySub({
  bars,
  maxTotal,
  w,
  h,
}: {
  bars: EnergyBar[];
  /** 歸一分母 = 全日最大**總量**,即頂端刻度值 */
  maxTotal: number;
  w: number;
  h: number;
}) {
  const bw = barW(w);
  const midY = h - (h - SUB_TOP_PAD) / 2;
  return (
    <g>
      {/* 量刻度:中線淡橫線 + 兩個值。bar 的高度分母已扣掉 SUB_TOP_PAD,
          頂端那根不會蓋住頂端的刻度文字。
          刻度值 = 全日最大**總量**(round5 E)—— 舊的「單邊最大」讓資訊列的「量」
          在副圖上找不到對應高度:未分類(開盤集合競價無 Bid/Ask 可比)整批不畫,
          而刻度又只算單邊。實測 09:00 量 269 = 外 127 + 內 20 + 未分類 122,
          舊刻度顯示 164。
          兩個值靠右緣(textAnchor="end")—— 左緣讓給主圖的價位帶,兩張圖左界對齊。
          ⚠ bar 畫到右緣帶左界為止,但中線數字仍可能與 bar 同區域,所以都要描邊。 */}
      <line
        x1={Y_AXIS_W}
        x2={w - R_AXIS_W}
        y1={midY}
        y2={midY}
        className="stroke-line"
        strokeWidth={0.4}
      />
      {/* 兩個數字都加同底色描邊(paintOrder="stroke" 讓描邊畫在字下面)。頂端那個有
          SUB_TOP_PAD 清出的空白可靠,**中線那個沒有**,不加對比會被 bar 蓋掉。 */}
      <text
        data-testid="vol-tick-top"
        x={w - 2}
        y={SUB_TOP_PAD - 2}
        textAnchor="end"
        className="fill-ink-dim stroke-surface"
        strokeWidth={2.5}
        paintOrder="stroke"
        fontSize="0.5rem"
      >
        {maxTotal}
      </text>
      <text
        data-testid="vol-tick-mid"
        x={w - 2}
        y={midY - 2}
        textAnchor="end"
        className="fill-ink-dim stroke-surface"
        strokeWidth={2.5}
        paintOrder="stroke"
        fontSize="0.5rem"
      >
        {Math.round(maxTotal / 2)}
      </text>
      {/* 堆疊(由下而上):外盤紅 → 內盤綠 → 未分類灰。整根以 `b.x` 為**中心** ——
          `b.x` 是走勢線頂點與十字線的 x,舊版把 bar 畫在 `[b.x, b.x+bw]` 讓 `b.x`
          變成左緣,十字線因此落在那根的左邊(round5 A,user 截圖指認)。 */}
      {bars.map((b) => {
        const x = b.x - bw / 2;
        const outerY = h - b.outerH;
        const innerY = outerY - b.innerH;
        const unchY = innerY - b.unchH;
        return (
          <g key={`e-${b.x}`}>
            <rect x={x} y={outerY} width={bw} height={b.outerH} className="fill-bull" />
            <rect x={x} y={innerY} width={bw} height={b.innerH} className="fill-bear" />
            <rect x={x} y={unchY} width={bw} height={b.unchH} className="fill-ink-dim" />
          </g>
        );
      })}
    </g>
  );
});

interface Props {
  accum: StockAccum;
  /** 主圖 / 副圖的 viewBox 高度(SC-6)。**純量不是物件** —— memo 子元件吃純量才不會
   *  每次 render 因 identity 改變而重建(W-5)。未傳 = 量測未就緒 / jsdom,沿用固定常數。 */
  mainHeight?: number;
  subHeight?: number;
}

export function StockIntradayChart({ accum, mainHeight, subHeight }: Props) {
  const { toggles, set } = useChartToggles();
  const mainW = MAIN.width;
  const mainH = mainHeight ?? MAIN.height;
  const subW = SUB.width;
  const subH = subHeight ?? SUB.height;
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
    // mainW / mainH 必入 deps:少了高度,viewBox 會換成新高而 toY / 刻度仍是舊高算的,
    // 畫面錯位且不報錯(專案 eslint 沒裝 react-hooks,exhaustive-deps 抓不到)
    [accum.minutes, accum.meta, mainW, mainH],
  );

  const subGeo = useMemo(
    () => buildIntradayGeometry({ minutes: accum.minutes, meta: accum.meta }, { width: subW, height: subH }),
    [accum.minutes, accum.meta, subW, subH],
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
      <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-line bg-surface">
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
  const lastPt = lastPoint(g);

  // 當日高低(SC-1)。**域外不畫** —— 沿用 overlayLines 的規則:無漲跌停時 y 域由
  // 分鐘收盤極值決定,裝不下逐筆極值,線會畫到時間軸上。
  const inDomain = (p: number | null): number | null =>
    p === null || p < g.yDomain[0] || p > g.yDomain[1] ? null : g.toY(p);
  const dayHighY = inDomain(accum.high);
  const dayLowY = inDomain(accum.low);
  // 現價圈(SC-2):值每 tick 都變 → 畫在 ChartStatic 之外,不打穿 memo
  const lastPrice = accum.last?.p ?? null;
  const lastTone =
    lastPrice === null || ref === null
      ? "fill-ink-dim"
      : lastPrice > ref
        ? "fill-bull"
        : lastPrice < ref
          ? "fill-bear"
          : "fill-ink-dim";
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
  const timeTagX = hoverMin !== null ? clampTagX(minuteToX(hoverMin, mainW), TIME_TAG.w, mainW) : null;
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
    <figure className="flex min-h-0 flex-1 flex-col select-none rounded-md border border-line bg-surface p-4">
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
          refMilli={ref}
          showVwap={toggles.vwap}
          oLines={oLines}
          clipAbove={clipAbove}
          clipBelow={clipBelow}
          highMilli={accum.high}
          lowMilli={accum.low}
          highY={dayHighY}
          lowY={dayLowY}
        />
        <XAxisLabels w={mainW} h={mainH} tagSpan={timeTagSpan} />
        {lastPt !== null && lastPrice !== null ? (
          <g pointerEvents="none">
            <circle data-testid="last-dot" cx={lastPt.x} cy={lastPt.y} r={3} className={lastTone} />
            <text
              data-testid="last-price"
              x={lastPt.x + 5}
              y={lastPt.y - 4}
              className={cn(lastTone, "stroke-surface")}
              strokeWidth={2}
              paintOrder="stroke"
              fontSize="0.5625rem"
            >
              {fmt(lastPrice)}
            </text>
          </g>
        ) : null}
        {/* hover 十字 + 軸標籤(SC-7)。
            分解退化:水平線 / 左價標 / 右 % 標只依賴滑鼠 y,無成交分鐘照畫;
            垂直線與資料點需要資料,缺就不畫(白名單 2:minuteOf 不 snap 最近)。 */}
        {hover !== null ? (
          <g pointerEvents="none">
            {hoverMin !== null && hoverAgg ? (
              <>
                <line
                  data-testid="crosshair-v"
                  x1={minuteToX(hoverMin, mainW)}
                  x2={minuteToX(hoverMin, mainW)}
                  y1={0}
                  y2={plotBottom}
                  className="stroke-ink-muted"
                  strokeDasharray="2 2"
                  strokeWidth={0.7}
                />
                {/* 該分鐘收盤的視覺錨 —— 水平線變量尺後,收盤位置改由這顆點承接 */}
                <circle cx={minuteToX(hoverMin, mainW)} cy={g.toY(hoverAgg.c)} r={2.5} className="fill-ink" />
              </>
            ) : null}
            <line
              data-testid="crosshair-h"
              x1={Y_AXIS_W}
              x2={mainW - R_AXIS_W}
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
                  className="fill-time"
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
        <EnergySub bars={subGeo.energyBars} maxTotal={subGeo.maxTotal} w={subW} h={subH} />
        {/* 垂直線延伸進副圖,讓該分鐘的內外盤 bar 可對位;畫在 memo 之外 */}
        {hoverMin !== null ? (
          <line
            x1={minuteToX(hoverMin, mainW)}
            x2={minuteToX(hoverMin, mainW)}
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
