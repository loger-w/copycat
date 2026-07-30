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
import { clampTagX, clampTagY, overlaps, toSvgPoint } from "@/lib/chart-crosshair";
import {
  CANDLE_MARK,
  clampLabelX,
  markLabelY,
  trianglePoints,
} from "@/lib/chart-extreme";
import { fmtTickPrice, snapDown } from "@/lib/stock-tick";
import { cn } from "@/lib/utils";
import { ChartReadout, type ReadoutField } from "@/components/chart/ChartReadout";

/** K 線圖(SC-6/SC-7)。幾何全在 lib/candle.ts + lib/candle-viewport.ts,本檔只掛 DOM。
 *  台股慣例:紅漲(bull)/ 綠跌(bear)。 */

/** height 578 = 1400 × (江波圖 260+70)/800 —— 讓兩張圖的 svg 佔容器寬比例相同。
 *  再加上兩個 figure 的框外 chrome 逐項對稱(頂列 h-[1.375rem]+mb-1、底列 mt-1+h-4),
 *  切換模式時圖表區塊高度才不會跳(SC-6.7)。殘差 0.5px @ 容器寬 1400。 */
const DIMS = { width: 1400, height: 578 };
const X_LABEL_H = 14;
/** 滾輪每一格的縮放倍率 */
const ZOOM_STEP = 1.15;
/** 軸標籤尺寸;time tag 的 y = height − boxH,底邊恰貼 viewBox 底不被裁 */
const PRICE_TAG = { w: 56, h: 16 };
const TIME_TAG = { w: 48, h: 14 };

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

/** 視窗高低標記(round4 項 1)。`cx` = 造成該極值那根蠟燭的中心 x。 */
interface WindowMark {
  cx: number;
  y: number;
  text: string;
}

/** 極值文字的 baseline 上界(字級 0.625rem ≈ 10px,再留 1px)與左右夾制留邊 */
const MARK_LABEL_TOP = 11;
const MARK_LABEL_PAD_X = 20;

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
  w,
  ma5Line,
  ma20Line,
  bbUpperLine,
  bbLowerLine,
  highMark,
  lowMark,
  showVolume,
}: {
  g: CandleGeometry;
  /** viewBox 寬。**純量不是物件** —— 物件每次 render 新 identity 會打穿本 memo */
  w: number;
  ma5Line: { x: number; y: number }[];
  ma20Line: { x: number; y: number }[];
  bbUpperLine: { x: number; y: number }[];
  bbLowerLine: { x: number; y: number }[];
  /** 可視視窗的最高 / 最低標記(落在造成該極值的那根蠟燭上)。
   *  **文字與 figcaption 是同一個字串**(SC-3 由建構保證);
   *  物件必須由呼叫端 useMemo 穩定 identity,否則打穿本 memo(W-3) */
  highMark: WindowMark | null;
  lowMark: WindowMark | null;
  /** false = 該資料源沒有量(如櫃買 MIS 取樣合成)→ 量區改印說明,不畫一排 0 柱 */
  showVolume: boolean;
}) {
  return (
    <g>
      {/* 視窗高低(round4 項 1)。橫貫左右的虛線已移除 —— 它把整條價位軸都染上
          「這個視窗的高」這個語意,而使用者要的只是「最高那根在哪、多少錢」。
          改成標在造成該極值的那根蠟燭影線端點上的三角 + 就地價位文字(與分時圖同語言,
          幾何規則共用 lib/chart-extreme,尺寸依 viewBox 各帶一份)。 */}
      {([
        ["window-high", highMark, "up"],
        ["window-low", lowMark, "down"],
      ] as const).map(([id, mark, dir]) =>
        mark === null ? null : (
          <g key={id}>
            <polygon
              data-testid={id}
              points={trianglePoints(mark.cx, mark.y, dir, CANDLE_MARK)}
              className="fill-ink-muted stroke-surface"
              strokeWidth={1}
              paintOrder="stroke"
            />
            <text
              data-testid={`${id}-label`}
              x={clampLabelX(mark.cx, MARK_LABEL_PAD_X, w - MARK_LABEL_PAD_X)}
              y={markLabelY(mark.y, dir, CANDLE_MARK, {
                top: MARK_LABEL_TOP,
                // 文字翻面以**價格區**底為界,不是整張圖底 —— 用圖底的話低標文字永遠
                // 不會翻面、直接落進成交量柱上(常態路徑)
                bottom: g.priceBottom - 2,
              })}
              textAnchor="middle"
              className="fill-ink-muted stroke-surface"
              strokeWidth={2}
              paintOrder="stroke"
              fontSize="0.625rem"
            >
              {mark.text}
            </text>
          </g>
        ),
      )}
        {/* y 軸格線 + 價位刻度 */}
      {g.yTicks.map((t) => (
        <g key={`yt-${t.priceMilli}`}>
          <line
            x1={0}
            x2={w}
            y1={t.y}
            y2={t.y}
            className="stroke-line"
            strokeDasharray="2 3"
            strokeWidth={0.5}
          />
          <text x={2} y={t.y - 2} className="fill-ink-dim" fontSize="0.625rem">
            {/* fmtTickPrice 而非 fmt:小數位由該價位帶的 tick 級距決定,
                1000 元以上顯示整數、100-500 元一位(round3 項 10) */}
            {fmtTickPrice(t.priceMilli)}
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
      {/* 量 bar。無量資料時不畫 0 柱 —— 一排貼底的 0 高柱與「真的零成交」
          在畫面上無法區分,正是本輪要避免的假造零(index-board SC-6)。 */}
      {showVolume ? (
        g.volBars.map((b, i) => (
          <rect
            key={`v-${i}`}
            x={b.x}
            y={b.y}
            width={b.w}
            height={b.h}
            className={VOL_CLASS[b.dir]}
          />
        ))
      ) : (
        <text x={4} y={g.volBars[0]?.y ?? DIMS.height * 0.85} className="fill-ink-muted" fontSize="0.625rem">
          無量資料
        </text>
      )}
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
    </g>
  );
});

/** X 軸時間文字層。**刻意不在 ChartStatic 內**:hover 時間標會蓋住鄰近的靜態標籤,
 *  只蓋一半會露出殘字(實測:hover 05/18 時「05/19」被蓋掉前半只剩一個 9),
 *  所以重疊的要直接不畫 —— 那需要 hover 位置。至多 6 個 text 節點,每次 mousemove
 *  重建的成本可忽略;真正重的蠟燭/量/線層仍在 memo 內(白名單 3)。 */
function XAxisLabels({
  g,
  h,
  shown,
  labelStep,
  tagSpan,
}: {
  g: CandleGeometry;
  h: number;
  shown: Bar[];
  labelStep: number;
  tagSpan: [number, number] | null;
}) {
  return (
    <g>
      {shown.map((b, i) => {
        if (i % labelStep !== 0) return null;
        const cx = g.candles[i]?.cx;
        if (cx === undefined) return null;
        if (tagSpan !== null && overlaps(cx - 15, cx + 15, tagSpan[0], tagSpan[1])) return null;
        return (
          <text
            key={`x-${i}`}
            x={cx}
            y={h - 3}
            textAnchor="middle"
            className="fill-ink-dim"
            fontSize="0.625rem"
          >
            {shortStamp(b.t)}
          </text>
        );
      })}
    </g>
  );
}

interface Props {
  bars: Bar[];
  /** 初始可視根數(日 K 120 / 分 K 240);之後由滾輪縮放與拖曳平移控制 */
  initBars?: number;
  /** 布林通道開關。狀態由 StockChart 持有(useChartToggles 是每 instance 各一份,
   *  本元件不自呼叫該 hook,否則按鈕與圖會各管各的) */
  showBb?: boolean;
  onToggleBb?: (value: boolean) => void;
  /** viewBox 高度(SC-6)。純量不是物件 —— memo 子元件吃純量才不會因 identity 重建
   *  (W-5)。未傳 = 量測未就緒 / jsdom,沿用固定常數。 */
  height?: number;
  /** 資料源有無成交量。預設 `true` = 既有行為(個股頁零變化);`false` 時量區印
   *  「無量資料」、資訊列的量欄顯示 `—`(index-board SC-6)。 */
  showVolume?: boolean;
}

/** 一根 bar → 資訊列欄位。`prev` 用來算漲跌%(K 線跨多日,沒有「昨收」可比)。 */
function readoutFields(
  b: Bar | undefined,
  prev: Bar | undefined,
  showVolume: boolean,
): ReadoutField[] {
  if (b === undefined) {
    return [
      { label: "", value: "-" },
      { label: "開", value: "-" },
      { label: "高", value: "-" },
      { label: "低", value: "-" },
      { label: "收", value: "-" },
      { label: "漲跌", value: "-" },
      { label: "量", value: "-" },
    ];
  }
  const tone = b.c > b.o ? "bull" : b.c < b.o ? "bear" : undefined;
  const pct = prev !== undefined && prev.c > 0 ? ((b.c - prev.c) / prev.c) * 100 : null;
  return [
    { label: "", value: b.t },
    { label: "開", value: fmt(b.o) },
    { label: "高", value: fmt(b.h) },
    { label: "低", value: fmt(b.l) },
    { label: "收", value: fmt(b.c), tone },
    {
      label: "漲跌",
      value: pct === null ? "-" : `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`,
      tone: pct === null ? "muted" : pct > 0 ? "bull" : pct < 0 ? "bear" : "muted",
    },
    { label: "量", value: showVolume ? String(b.v) : "—" },
  ];
}

export function CandleChart({
  bars,
  initBars = 120,
  showBb = false,
  onToggleBb,
  height,
  showVolume = true,
}: Props) {
  const dimW = DIMS.width;
  const dimH = height ?? DIMS.height;
  // hover 存的是 **viewBox 座標**不是 bar index:index 是對可視窗口 shown 的,
  // 一旦滾輪縮放或資料延伸讓 viewport.start 改變,同一個索引就指到別根 bar —— 十字線與
  // 資訊列會一起指錯,而且要等下次滑鼠移動才修正(實測游標在 x=700、十字線飄到 807)。
  // 存座標則每次 render 都用當下的 g 重新反查,錨點守恆的縮放天然維持「指著同一根」。
  // y 同時是水平線位置:水平線是「自由量尺」(跟滑鼠),不鎖收盤價 —— 盤中最常做的事是
  // 量距離(現價到某價位差幾%),鎖收盤價的水平線與蠟燭重合、資訊冗餘。
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null);
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
      g: buildCandleGeometry(shownBars, { width: dimW, height: dimH }, extra),
      ma5: m5,
      ma20: m20,
      bands: bb,
    };
    // dimW / dimH 必入 deps:少了高度,viewBox 換新高而 toY / 刻度仍舊高算(T-10b)
  }, [bars, viewport, showBb, dimW, dimH]);

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
      const { x } = toSvgPoint(e, rect, { width: dimW, height: dimH });
      const ratio = dimW > 0 ? x / dimW : 0.5;
      const factor = e.deltaY > 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      setViewport((v) => zoomAt(v, total, factor, ratio));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [total]);

  function onMove(e: React.MouseEvent<SVGSVGElement>): void {
    const rect = e.currentTarget.getBoundingClientRect();
    const { x, y } = toSvgPoint(e, rect, { width: dimW, height: dimH });
    const rx = Math.round(x);
    const ry = Math.round(y);
    // 值相同就回 prev 讓 React bail out:亞像素抖動不該觸發 re-render
    setHover((p) => (p !== null && p.x === rx && p.y === ry ? p : { x: rx, y: ry }));
  }

  /** 拖曳平移:mousedown 記起點,mousemove/mouseup 掛 window(拖出圖外仍跟手)。
   *  維持 mouse 事件模型 —— 專案慣例是觸控靠 tap 的 synthetic mousemove,改 pointer 會破。 */
  function onDragStart(e: React.MouseEvent<SVGSVGElement>): void {
    if (e.button !== 0) return;
    const el = svgRef.current;
    if (el === null) return;
    const rect = el.getBoundingClientRect();
    const scale = rect.width > 0 ? dimW / rect.width : 1;
    const startX = e.clientX;
    // 起始窗口直接取 closure 的 viewport —— 這個 handler 來自最近一次 render,值即為當下。
    // 不要用 `setViewport(v => { startVp = v; return v; })` 的 side effect 去讀:React 不保證
    // updater 同步執行(只是常常如此),讀到 null 就得 fallback,等於多一條沒必要的路徑。
    const startVp = viewport;
    const slot = dimW / Math.max(1, startVp.count);
    const move = (ev: MouseEvent): void => {
      // 往右拖 = 看更早的資料 → start 往左。以「拖曳起點」為基準算絕對位移,
      // 不是逐次累加 —— 累加會因為 clamp 而在端點附近漂移。
      const deltaBars = -Math.round(((ev.clientX - startX) * scale) / slot);
      setViewport(panBy(startVp, total, deltaBars));
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
  // 每次 render 以當下的 g 反查索引 —— viewport 一變就自動重新對位
  const hoverIdx = hover !== null ? g.indexOf(hover.x) : null;
  const hoverBar = hoverIdx !== null ? shown[hoverIdx] : undefined;
  const hoverCandle = hoverIdx !== null ? g.candles[hoverIdx] : undefined;
  // 資訊列:沒 hover 顯示最後一根(即時態),不是空白
  const shownIdx = hoverBar !== undefined ? hoverIdx! : shown.length - 1;
  // prev 從**完整序列**取,不是視窗切片:視窗最左那根在切片裡沒有前一根,漲跌% 會恆顯示
  // "-" 即使 bars 裡真的有前一根(MA/BB 已經是「完整序列算完再切」以免斷頭,這裡同源)
  const fields = readoutFields(shown[shownIdx], bars[viewport.start + shownIdx - 1], showVolume);
  const plotBottom = dimH - X_LABEL_H;
  const hoverPrice = hover !== null ? snapDown(g.priceAtY(hover.y)) : null;
  const windowHigh = shown.length > 0 ? Math.max(...shown.map((b) => b.h)) : 0;
  const windowLow = shown.length > 0 ? Math.min(...shown.map((b) => b.l)) : 0;
  // 圖上的價位標與 figcaption 用**同一個字串**:SC-3 的「兩者始終相等」由建構保證,
  // 不靠兩處各自格式化後恰好一樣
  const highText = fmt(windowHigh);
  const lowText = fmt(windowLow);
  // 標記落在造成該極值的那根蠟燭上(**取最早出現的** —— 先到者才是「當時創的高」)。
  // useMemo:物件 identity 每次 render 變會打穿 ChartStatic 的 memo(W-3)。
  const highMark = useMemo<WindowMark | null>(() => {
    if (shown.length === 0) return null;
    const cx = g.candles[shown.findIndex((b) => b.h === windowHigh)]?.cx;
    return cx === undefined ? null : { cx, y: g.toY(windowHigh), text: highText };
  }, [shown, g, windowHigh, highText]);
  const lowMark = useMemo<WindowMark | null>(() => {
    if (shown.length === 0) return null;
    const cx = g.candles[shown.findIndex((b) => b.l === windowLow)]?.cx;
    return cx === undefined ? null : { cx, y: g.toY(windowLow), text: lowText };
  }, [shown, g, windowLow, lowText]);
  const windowPct =
    shown.length > 1 && shown[0]!.c > 0
      ? ((shown[shown.length - 1]!.c - shown[0]!.c) / shown[0]!.c) * 100
      : null;
  const timeTagX =
    hoverCandle !== undefined ? clampTagX(hoverCandle.cx, TIME_TAG.w, dimW) : null;
  const timeTagSpan: [number, number] | null =
    timeTagX === null ? null : [timeTagX, timeTagX + TIME_TAG.w];

  return (
    // select-none:SVG 的 <text>(價位刻度 / 日期標籤)預設可選,在圖上拖曳會整片反白(SC-4)。
    // 不影響 hover — user-select 只管選取,mouse 事件照舊(W-10)。
    <figure
      data-testid="candle-figure"
      data-first={shown[0]?.t ?? ""}
      data-count={shown.length}
      className="flex min-h-0 flex-1 flex-col select-none rounded-md border border-line bg-surface p-4"
    >
      {/* 頂列:左側留給資訊條、右側指標 toggle。高度以 rem 固定(root font-size 縮放才等比) */}
      <div className="mb-1 flex h-[1.375rem] items-center justify-between gap-2">
        <ChartReadout fields={fields} hovering={hoverBar !== undefined} />
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
        <div className="flex min-h-0 flex-1 items-center justify-center">
          <p className="text-sm text-ink-muted">無 K 線資料</p>
        </div>
      ) : (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${dimW} ${dimH}`}
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
            w={dimW}
            ma5Line={ma5Line}
            ma20Line={ma20Line}
            bbUpperLine={bbUpperLine}
            bbLowerLine={bbLowerLine}
            highMark={highMark}
            lowMark={lowMark}
            showVolume={showVolume}
          />
          <XAxisLabels g={g} h={dimH} shown={shown} labelStep={labelStep} tagSpan={timeTagSpan} />
          {/* hover 十字 + 軸標籤(SC-7)。垂直線 snap 蠟燭(資料錨)、水平線跟滑鼠(量尺)。 */}
          {hover !== null ? (
            <g pointerEvents="none">
              {hoverCandle !== undefined ? (
                <line
                  data-testid="crosshair-v"
                  x1={hoverCandle.cx}
                  x2={hoverCandle.cx}
                  y1={0}
                  y2={plotBottom}
                  className="stroke-ink-muted"
                  strokeDasharray="2 2"
                  strokeWidth={0.7}
                />
              ) : null}
              <line
                data-testid="crosshair-h"
                x1={0}
                x2={dimW}
                y1={hover.y}
                y2={hover.y}
                className="stroke-ink-muted"
                strokeDasharray="2 2"
                strokeWidth={0.7}
              />
              {/* 左緣價位標籤:滑鼠所在價位 snap 到合法 tick(顯示的價位要「可下單」) */}
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
                  y={PRICE_TAG.h - 5}
                  className="fill-ink"
                  fontSize="0.625rem"
                >
                  {hoverPrice !== null ? fmt(hoverPrice) : ""}
                </text>
              </g>
              {/* 底部時間標籤:x 軸標籤是每 labelStep 根才一個,hover 讀不到精確時間 */}
              {hoverCandle !== undefined && hoverBar !== undefined ? (
                <g
                  transform={`translate(${clampTagX(hoverCandle.cx, TIME_TAG.w, dimW)}, ${
                    dimH - TIME_TAG.h
                  })`}
                >
                  <rect
                    data-testid="time-tag"
                    y={0}
                    width={TIME_TAG.w}
                    height={TIME_TAG.h}
                    rx={2}
                    className="fill-bg-deep stroke-line"
                  />
                  <text
                    data-testid="time-tag-text"
                    x={TIME_TAG.w / 2}
                    y={TIME_TAG.h - 4}
                    textAnchor="middle"
                    className="fill-ink"
                    fontSize="0.625rem"
                  >
                    {shortStamp(hoverBar.t)}
                  </text>
                </g>
              ) : null}
            </g>
          ) : null}
        </svg>
      )}
      {/* 底列:視窗摘要。與江波圖底部 figcaption 同結構同高度 —— 兩個 figure 的框外
          chrome 逐項對稱,SC-6.7 的「切模式不跳高」才成立。 */}
      <figcaption className="mt-1 flex h-4 items-center gap-x-3 font-mono text-xs text-ink-dim">
        <span>{shown.length} 根</span>
        <span>高 {highText}</span>
        <span>低 {lowText}</span>
        <span
          className={cn(
            windowPct === null ? "" : windowPct > 0 ? "text-bull" : windowPct < 0 ? "text-bear" : "",
          )}
        >
          期間 {windowPct === null ? "-" : `${windowPct > 0 ? "+" : ""}${windowPct.toFixed(2)}%`}
        </span>
      </figcaption>
    </figure>
  );
}
