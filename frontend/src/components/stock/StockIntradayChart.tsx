import { memo, useId, useMemo, useState } from "react";

import { ChartReadout, type ReadoutField } from "@/components/chart/ChartReadout";
import { clampLabelX, INTRADAY_MARK, markCenterX, markLabelY, markTone } from "@/lib/chart-extreme";
import { useChartToggles, type ChartToggles } from "@/hooks/useChartToggles";
import { clampTagX, clampTagY, overlaps, toSvgPoint } from "@/lib/chart-crosshair";
import {
  EMPTY_FILLS,
  EMPTY_MARKS,
  FILL_MARK,
  fillLabel,
  fillsAtMinute,
  fillTrianglePoints,
  projectFills,
  type FillMark,
  type FillPoint,
} from "@/lib/fill-marks";
import { chgPct, fmt, fmtIndexPts, fmtPct } from "@/lib/format";
// index 態限定:對稱域讓 CDP 常態落在域外,線畫不出來 → 右緣掛牌是唯一訊號(KR-1)。
// 判定與 `overlayLines` 互補(同一組 yDomain,一個值只會進其中一邊),所以共用那支。
import { outOfDomainLevels } from "@/lib/index-chart-svg";
import { fmtTickPrice, snapDown } from "@/lib/stock-tick";
import { pts } from "@/lib/svg-points";
import { hhmm, hourTicksOf, type HourTick } from "@/lib/time-labels";
import { useStockOverlay } from "@/hooks/useStockOverlay";
import { isInstrumentKey } from "@/lib/stkfut";
import type { StockAccum } from "@/lib/stock-accum";
import {
  buildEnergyBars,
  buildIntradayGeometry,
  edgePriceLabels,
  lastPoint,
  LEVEL_FILL,
  LEVEL_STROKE,
  LOW_DECIDED_PCT,
  minuteToX,
  overlayLines,
  pegLabels,
  plotWidth,
  R_AXIS_W,
  sideSummary,
  SPOT_WINDOW,
  STKFUT_WINDOW,
  X_LABEL_H,
  SUB_TOP_PAD,
  Y_AXIS_W,
  type EnergyBar,
  type IntradayGeometry,
  type OverlayLevel,
  type OverlayLine,
  type PegInput,
  type StockOverlay,
  type XWindow,
} from "@/lib/stock-intraday-svg";
import {
  buildVpBars,
  VP_FILL_OPACITY,
  VP_POC_FILL_OPACITY,
  type VpBar,
} from "@/lib/volume-profile";
import { cn, safeIdToken } from "@/lib/utils";

/** viewBox 寬的預設(單檔頁)。**主圖與副圖共用同一個值**,由 `width` prop 覆寫 ——
 *  兩張圖各持一個常數的話,x 對位只是靠「兩個數字碰巧相等」在維持(見副圖 hover 線)。 */
const DEFAULT_W = 800;
const MAIN = { height: 260 };
const SUB = { height: 70 };
/** 軸標籤尺寸;time tag 的 y = mainH − boxH,底邊恰貼 viewBox 底不被裁。
 *  寬度**直接取 `Y_AXIS_W`** 不另寫一份數字:兩份靠註解維持相等的話,任一方改動就讓
 *  「hover 價位標壓在走勢線上」這個本輪要修的症狀復發,而且沒有測試會發現。 */
const PRICE_TAG = { w: Y_AXIS_W, h: 14 };
/** 底部 hover 標籤(round4 項 3:時間 + 該分鐘成交價兩行)。
 *  高度**往上長**不往下溢出 —— 盒子底邊已貼死 viewBox 底,而圖高由 StockChart 量測後
 *  指派,不能為了標籤加高。寬度 40 是常數不是 JSX 硬編:`XAxisLabels` 的「與 tag 重疊
 *  就不畫」靠 `tagSpan` 判定,寫死在 JSX 會讓遮蔽判定與實際寬度脫鉤。 */
const TIME_TAG = { w: 40, h: 24 };

/** 量柱寬 = 一分鐘的水平間距減去柱間縫。**分母必須是當前窗的分鐘數**,不是現貨窗的常數
 *  —— 換窗時漏改這裡的樣態是「柱子照畫、只是與走勢線的分鐘節點對不上」,沒有 assertion
 *  會紅(同 `minuteToX` / `minuteOf` 共用 `plotWidth` 的理由)。 */
function barW(width: number, xw: XWindow = SPOT_WINDOW): number {
  return Math.max(1, plotWidth(width) / (xw.end - xw.start) - 0.4);
}

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

/** 右緣文字:CDP 五線印價位 + `*`(一眼分出是 CDP 不是 MA);MA 維持名稱。
 *
 *  價位口徑由 `priceText` 注入(stock = `fmtTickPrice` 可下單檔位、index = `fmtIndexPts`,
 *  見 lib/format)—— 指數沒有 tick 表,snap 出來的點位是憑空捏造的。**注入而不是就地判 mode**:
 *  同一份口徑在 MA 價位標(`edge-price-*`)也要用,兩處各判各的話會出現「CDP snap 了、
 *  MA 沒 snap」這種同圖兩套口徑,沒有任何錯誤訊號。 */
function levelText(
  level: OverlayLevel,
  priceMilli: number,
  priceText: (milli: number) => string,
): string {
  return level === "ma5" || level === "ma20"
    ? level.toUpperCase()
    : `${priceText(priceMilli)}*`;
}

/** 域外掛牌的空集合。**模組層常數**(identity 穩定)—— 行內 `[]` 會打穿 ChartStatic 的
 *  memo,而症狀只是 hover 掉幀,沒有任何測試會紅(同 `EMPTY_MARKS` 的理由)。 */
const EMPTY_PEGS: readonly PegInput[] = [];

/** index 態的成交量副圖不 render,但 hook 不可條件化 → 回這顆常數而不是每 render 新物件。 */
const EMPTY_ENERGY: { bars: EnergyBar[]; maxTotal: number } = { bars: [], maxTotal: 1 };

/** 極值標記文字的 baseline 上界(字高 0.5625rem ≈ 9px,再留 1px 呼吸) */
const MARK_LABEL_TOP = 9;

/** `fmtTickPrice` 口徑價位文字的寬度估值 @0.5625rem(最寬內容「1005.0」≈ 34px,
 *  同 `R_AXIS_W` 的推導)。MA 標籤與極值文字都是這個口徑;避讓判準的水平相交也由它
 *  組合(半寬 = `EDGE_LABEL_W / 2`,見 `maObstacles`),不另設孤立常數(review A-2/A-3)。 */
const EDGE_LABEL_W = 34;
/** VWAP 標籤的寬度估值。**與 `EDGE_LABEL_W` 分開**(review B-4):VWAP 走 `fmt` 口徑,
 *  統計量幾乎必帶兩位小數,千元帶最長 7 字(「1405.67」)≈ 40px;拿 fmtTickPrice 的 34
 *  當上界,盤末 clamp 後字尾仍會溢進右緣帶。 */
const VWAP_LABEL_W = 40;
/** SVG `<text>` 無 `dy` 時 y 是 baseline;視覺中心 ≈ baseline − 0.35em(9px 字 ≈ 3px)。
 *  避讓幾何一律以**中心**為單位(`EDGE_LABEL_H` 是中心距),極值文字的 baseline 進
 *  obstacle 集前要先扣掉這一段(review B-1)—— 不扣的話向上讓位那側的實際字框間距
 *  只剩半 px,兩層 halo 直接相疊,而數字上「距離夠」。 */
const BASELINE_TO_CENTER = 3;

/** 漲跌停亮燈色塊的高度(項 5)。
 *
 *  **必須 ≤ 2 × PAD_Y(8)**(Phase 5 review P2):最上格的 `t.y = PAD_Y = 4`,色塊置中後
 *  上緣落在 `t.y − h/2`;h 大於 8 就得夾制成 0,而文字仍畫在 `t.y` → 字在色塊裡偏上,
 *  最下格則反過來把色塊擠進底部時間標籤帶。取 8 讓兩端都不必夾制,兩格自然與文字同心。
 *  字高 ≈ 9px 略高於 8,視覺上是「底線比字略窄」的 highlight 而不是滿框,可接受。 */
const TICK_LAMP_H = 8;

/** 靜態圖層 memo:hover 每 mousemove re-render 父層,線層不可每次重建(SC-1)。 */
const ChartStatic = memo(function ChartStatic({
  g,
  w,
  h,
  refMilli,
  showVwap,
  vwapMilli,
  oLines,
  vpBars,
  clipAbove,
  clipBelow,
  plotBottom,
  xw,
  hourTicks,
  fillMarks,
  priceText,
  tickText = fmt,
  pegs = EMPTY_PEGS,
}: {
  g: IntradayGeometry;
  /** viewBox 寬 / 高。**必須是純量不是物件** —— 物件每次 render 新 identity 會打穿本 memo */
  w: number;
  h: number;
  /** x 軸分鐘窗。**必經模組層常數或 useMemo**(identity 穩定),行內字面值會打穿本 memo */
  xw: XWindow;
  /** 整點刻度;同上,必經 useMemo */
  hourTicks: readonly HourTick[];
  /** 參考價(左緣刻度判色用);純量,memo 安全 */
  refMilli: number | null;
  showVwap: boolean;
  /** 後端逐筆 VWAP(毫元;`accum.vwap`)。標籤**文字**的唯一來源(review A-1)——
   *  說明列印的是同一份,兩處各取各的來源時失效樣態是同圖兩個矛盾的 VWAP 數字
   *  (前端分鐘近似 2381.67 vs 後端 2380),沒有任何錯誤訊號。純量,memo 安全。 */
  vwapMilli: number | null;
  oLines: OverlayLine[];
  /** 價位別成交量長條;關掉 toggle 時為空陣列。**必經呼叫端 useMemo**(identity 穩定) */
  vpBars: VpBar[];
  clipAbove: string;
  clipBelow: string;
  /** 繪圖區底(極值文字翻面判定用);純量,memo 安全 */
  plotBottom: number;
  /** 當日成交點的 SVG 座標(SC-3);toggle 關 / 零筆時是模組層 `EMPTY_MARKS`。
   *  **必經呼叫端 useMemo 或模組常數**(identity 穩定)—— 行內字面值會打穿本 memo,
   *  而症狀只是 hover 掉幀,沒有任何測試會紅(SC-9 就是補這道機械閘)。 */
  fillMarks: readonly FillMark[];
  /** 價位文字口徑(見 `levelText`;CDP `價位*` / MA 價位標 / 掛牌三處同源)。
   *  **必經模組層函式**(`fmtTickPrice` / `fmtIndexPts`)—— 行內箭頭函式每次 render 新
   *  identity,會打穿本 memo。 */
  priceText: (milli: number) => string;
  /** 左緣 y 刻度的文字口徑。stock 態預設 `fmt`(既有:不 snap、最多兩位小數,個股價位
   *  裝得下);index 態 `fmtIndexPts`(見該常數的 why)。與 `priceText` 分開:stock 態的
   *  刻度本來就不是 `fmtTickPrice` 口徑,合成一個 prop 會改到個股頁(W-1)。 */
  tickText?: (milli: number) => string;
  /** 域外疊線掛牌(index 態限定;stock 態恆為 `EMPTY_PEGS` → 零渲染、obstacles 不變)。
   *  **必經呼叫端 useMemo 或模組常數**(identity 穩定),同 `fillMarks`。 */
  pegs?: readonly PegInput[];
}) {
  // 極值標記的兩份幾何在下面的渲染分支與這裡各要用一次 —— 就地各算一次的話,
  // 「MA 標籤該讓開哪條 y」與「極值文字實際畫在哪」會各自漂,而漂掉的樣態是
  // 兩段文字疊在一起,沒有任何測試會紅。
  const markLabels = ([
    ["day-high", g.highMark, "up"],
    ["day-low", g.lowMark, "down"],
  ] as const).flatMap(([id, mark, dir]) =>
    mark === null
      ? []
      : [{
          id,
          mark,
          y: markLabelY(mark.y, dir, INTRADAY_MARK, { top: MARK_LABEL_TOP, bottom: plotBottom }),
        }],
  );
  // MA 價位標籤的固定 obstacle = **與 MA 標籤水平相交的**極值標記(D3/review F2)。
  // 判準是顯式的區間相交(review A-2):極值文字右緣(clamp 後的 x + 半寬)伸過 MA
  // 標籤左緣(anchor=end 在 w − R_AXIS_W − 2,向左佔 EDGE_LABEL_W)才算 —— 只比
  // mark.x 一個點會留下一條「疊了卻不進避讓集」的窄帶。x 用 clamp 後的值與實際畫的
  // 同源;左半場的極值納入避讓只會讓標籤無故位移。
  // 命中的每個極值給**兩個** obstacle(review B-1/B-3):文字(baseline 正規化成中心)
  // 與標記圓(圓心即中心)—— 只避文字的話,「讓開文字」的動作恰好把標籤推到圓上
  // (日高側文字在圓上方 7px,往下讓 EDGE_LABEL_H 後正落在圓心 +3)。
  const maLabelLeft = w - R_AXIS_W - 2 - EDGE_LABEL_W;
  // 界與極值文字同一組(review F4):兩份界各寫一次的話,兩種文字會在同一個角落
  // 各自夾制到不同的位置。底部再收 5px 是給字的下半身,`plotBottom` 是 baseline 上限。
  const edgeBounds = { top: MARK_LABEL_TOP, bottom: plotBottom - 5 };
  // 掛牌**先定位**:它是「CDP 在域外」的唯一訊號(KR-1),不能被 MA 標籤推開。
  // 兩者同一條走廊(x = w − R_AXIS_W − 2、anchor=end)、同一組界。
  const pegList = pegLabels(pegs, edgeBounds);
  const maObstacles = markLabels
    .flatMap((m) =>
      clampLabelX(m.mark.x, Y_AXIS_W + 16, w - R_AXIS_W - 16) + EDGE_LABEL_W / 2 > maLabelLeft
        ? [m.y - BASELINE_TO_CENTER, m.mark.y]
        : [],
    )
    // 掛牌的 y 併入 obstacles → MA 讓位。stock 態 pegList 恆空,這一段是 no-op。
    .concat(pegList.map((p) => p.y));
  const maLabels = edgePriceLabels(oLines, maObstacles, edgeBounds);
  // VWAP 就地標示在末點右側(D2/review F1):VWAP 不是橫貫全寬的水平線,盤中末點在
  // 畫面中段,右緣釘標籤會與線脫節 600 多 px。toggle 關 / 尚無成交 / 後端 VWAP
  // 不可得(vwapMilli null,與說明列的「-」同步)→ 不畫。**不退回前端近似值**:
  // 那正是 review A-1 要消滅的第二來源。
  const vwapEnd = g.vwapLine[g.vwapLine.length - 1] ?? null;
  const vwapLabel =
    showVwap && vwapMilli !== null && vwapEnd !== null
      ? { x: vwapEnd.x, y: vwapEnd.y, text: fmt(vwapMilli) }
      : null;
  // POC(域內量最大的價位);vp toggle 關 → vpBars 空 → 自然沒有
  const pocBar = vpBars.find((b) => b.poc) ?? null;
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
      {hourTicks.map(({ minute }) => (
        <line
          key={minute}
          x1={minuteToX(minute, w, xw)}
          x2={minuteToX(minute, w, xw)}
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
          {/* 漲停 / 跌停亮燈(round6 項 5)。恆亮 —— 與今天有沒有真的漲跌停無關,
              作用是讓「今天最多能到哪」一眼可見。
              y 要夾制:最上那格的 t.y = PAD_Y(4),色塊置中後上緣會落到 −2 被 viewBox 裁掉。
              寬度收在 `Y_AXIS_W − 2` 不碰繪圖區(SC-5.6);底部時間標籤最左一個畫在
              x = Y_AXIS_W + 2,所以左緣這條帶在標籤列是空的,下緣不必再夾。 */}
          {t.kind !== undefined ? (
            <rect
              data-testid={`y-tick-lamp-${t.kind}`}
              x={0}
              y={Math.min(Math.max(t.y - TICK_LAMP_H / 2, 0), h - TICK_LAMP_H)}
              width={Y_AXIS_W - 2}
              height={TICK_LAMP_H}
              rx={2}
              className={t.kind === "upper" ? "fill-bull" : "fill-bear"}
            />
          ) : null}
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
          {/* 價位文字**右對齊**貼著繪圖區左界(round4 項 6):左對齊時數字長度不同會讓
              右緣參差、且兩位數的刻度離走勢圖特別遠。
              垂直用 `dy="0.35em"` 讓數字中心壓在格線上,不用 `dominantBaseline` ——
              em 相對自身 font-size,root font-size media query 放大時偏移自動等比;
              而各引擎對 `middle`(x-height 中點)/ `central`(em-box 中點)取值不同,
              純數字會有 0.5~1px 的引擎差(本專案對「幾何自己算」已有明確立場)。
              原本的 `clamp(t.y − 2, 8, h − 16)` 夾制整條移除:`toY` 值域恰為
              `[PAD_Y, PAD_Y + plotH]`,置中後兩端都不會被裁,夾制反而讓最上 / 最下
              兩根刻度「字沒對到線」= 本項要修的症狀本身。 */}
          <text
            data-testid="y-tick-price"
            x={Y_AXIS_W - 4}
            y={t.y}
            dy="0.35em"
            textAnchor="end"
            // 亮燈那兩格一律白字:紅底紅字 / 綠底綠字看不見,`tickTone` 的漲跌色在這裡
            // 也已由底色講完了(W-27 只護中間各格)
            className={t.kind !== undefined ? "fill-white" : tickTone(t.priceMilli, refMilli)}
            fontSize="0.5625rem"
          >
            {tickText(t.priceMilli)}
          </text>
        </g>
      ))}
      {/* 價位別成交量(SC-3)。水平長條自繪圖區左緣向右,長度 = 該價位當日成交張數比例。
          **位置在 y 格線之後、平盤填色之前**:svg 沒有 z-index,圖層完全由文件順序決定,
          而這組長條是背景參考 —— 排到紅綠填色或走勢線之後就把主資訊蓋掉,畫面上卻照樣
          「有東西」,沒有任何錯誤訊號。
          `x` 恆為 `Y_AXIS_W`(幾何層只出 y/h/w,左界屬版面決策留在元件端);顏色與量副圖
          同一個 `fill-ink-muted` token,透明度收在 lib 常數不在這裡寫 magic number。 */}
      <g data-testid="vp-bars">
        {vpBars.map((b) => (
          // POC(域內量最大的價位,SC-4)換 accent + 更高透明度。**同一種 testid** ——
          // 另開節點的話,既有的「bar 數 / z-order / toggle 關掉整組消失」諸條都會漏算它。
          <rect
            key={b.priceMilli}
            data-testid="vp-bar"
            x={Y_AXIS_W}
            y={b.y}
            width={b.w}
            height={b.h}
            className={b.poc ? "fill-accent" : "fill-ink-muted"}
            fillOpacity={b.poc ? VP_POC_FILL_OPACITY : VP_FILL_OPACITY}
          />
        ))}
      </g>
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
            {levelText(l.level, l.priceMilli, priceText)}
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
      {/* 當日高低(round4 項 1;round6 項 1 改圓環並上移圖層)。
          橫貫左右的虛線已移除 —— 它把整條價位軸都染上「今天的高」這個語意,而使用者要的
          只是「最高點在哪、多少錢」。標在**摸到極值的那一分鐘**上 + 就地價位文字。

          **必須畫在主價線之後**:舊版夾在疊線與 VWAP 之間,strokeWidth 1.6 的價線直接壓過
          標記(user 回報「在走勢圖的圖層下」)。極值標記的整個作用就是指認價線上的一點,
          被價線蓋住等於沒畫。

          空心環不用實心點:防混淆改由**填滿與否**承擔 —— 現價圈(r=3)與 hover 收盤錨
          (r=2.5)都是實心且帶漲跌色,這裡是空心且恆為中性灰。空心另有一個好處:
          移到價線之上後,實心會把線在極值那一點截斷,空心則是套在線上。
          顏色取中性 ink-muted 不取紅綠:紅綠在本圖已被「相對昨收」佔用,整天下跌的股票
          其日高仍低於昨收,塗紅等於假陳述。 */}
      {markLabels.map(({ id, mark, y }) => {
        // 夾制界取 **viewBox** 不是繪圖區:這條夾制是為了防止圓被裁,不是把它趕出價位帶
        // —— 取繪圖區的話 09:00 附近的極值會被推開,而標記的 x 承載的是「哪一分鐘」
        // 的語意(SC-1.2),位移比稍微壓到帶緣嚴重。
        const cx = markCenterX(mark.x, INTRADAY_MARK, { min: 0, max: w });
        // round6b:圖案與文字**同色**,依相對平盤判紅 / 綠 / 灰(見 `markTone`)
        const tone = markTone(mark.priceMilli, refMilli);
        return (
          <g key={id}>
            <circle
              data-testid={id}
              cx={cx}
              cy={mark.y}
              r={INTRADAY_MARK.dot!.radius}
              className={cn(tone, "stroke-surface")}
              // paintOrder="stroke":描邊先畫、填色蓋上去 → 只露出外側半條,
              // 圓在走勢線 / 紅綠填色 / 格線上都讀得出來而不會胖一圈
              strokeWidth={INTRADAY_MARK.dot!.halo}
              paintOrder="stroke"
            />
            <text
              data-testid={`${id}-label`}
              x={clampLabelX(mark.x, Y_AXIS_W + 16, w - R_AXIS_W - 16)}
              y={y}
              textAnchor="middle"
              className={cn(tone, "stroke-surface")}
              strokeWidth={2}
              paintOrder="stroke"
              fontSize="0.5625rem"
            >
              {fmt(mark.priceMilli)}
            </text>
          </g>
        );
      })}
      {/* MA 即時價位數值(SC-1)。名稱 "MA5"/"MA20" 仍在右緣帶內(白名單 2),數值畫在
          **繪圖區內側右緣** —— R_AXIS_W=40 的帶裝不下「2330」再加名稱兩份內容。
          口徑 `fmtTickPrice`(可下單價位,round3 B4)且**不帶 `*`**:`*` 是 CDP 的記號,
          兩者靠色(黃 / 紫 vs 紅綠金)與後綴分辨(review F3)。 */}
      {maLabels.map((l) => (
        <text
          key={`ep-${l.level}`}
          data-testid={`edge-price-${l.level}`}
          x={w - R_AXIS_W - 2}
          y={l.y}
          dy="0.35em"
          textAnchor="end"
          className={cn(LEVEL_FILL[l.level], "stroke-surface")}
          strokeWidth={2}
          paintOrder="stroke"
          fontSize="0.5625rem"
        >
          {priceText(l.priceMilli)}
        </text>
      ))}
      {/* 域外疊線掛牌(index 態限定)。與 MA 價位標同一條走廊、同一組界,但**先定位**
          (見上面 `pegList`):對稱域下 CDP 常態整組域外,線體畫不出來時這行字是唯一
          的訊號 —— 被 MA 推開就等於指著錯的位置。
          文字 = `名稱 點位↑/↓`(↑ = 在域上方、↓ = 在域下方),與現版 `MarketChart` 的
          `labelText` peg 分支逐字相同(換元件不換語彙)。 */}
      {pegList.map((p) => (
        <text
          key={`peg-${p.level}`}
          data-testid={`overlay-peg-${p.level}`}
          x={w - R_AXIS_W - 2}
          y={p.y}
          dy="0.35em"
          textAnchor="end"
          className={cn(LEVEL_FILL[p.level], "stroke-surface")}
          strokeWidth={2}
          paintOrder="stroke"
          fontSize="0.5625rem"
        >
          {`${p.level.toUpperCase()} ${priceText(p.priceMilli)}${p.dir === "up" ? "↑" : "↓"}`}
        </text>
      ))}
      {/* VWAP 即時數值(SC-2)。就地畫在末點右側;值 = `vwapMilli`(後端逐筆,與說明列
          同源同值,review A-1),`fmt` 不 snap tick —— VWAP 是統計量不是可掛單價
          (review F3)。x 的上界留 `VWAP_LABEL_W`:盤末末點恰在繪圖區右界上,`+4` 會把
          整塊字推進右緣疊線標籤帶甚至出畫布,而那是「畫了但看不到」的靜默失敗。 */}
      {vwapLabel !== null ? (
        <text
          data-testid="edge-price-vwap"
          x={Math.min(vwapLabel.x + 4, w - R_AXIS_W - VWAP_LABEL_W)}
          y={vwapLabel.y}
          dy="0.35em"
          textAnchor="start"
          className="fill-ink stroke-surface"
          strokeWidth={2}
          paintOrder="stroke"
          fontSize="0.5625rem"
        >
          {vwapLabel.text}
        </text>
      ) : null}
      {/* POC 價位數值(SC-4)。畫在長條**尖端右側**:尖端的 x 隨量比例走,標籤跟著它
          才指認得出「變色那根是哪個價位」;釘左緣或塞進 yTicks 都會與長條脫節。
          與 highlight 同一個 accent 色,halo 一律描邊(白名單 10:不得用底色 rect)。 */}
      {pocBar !== null ? (
        <text
          data-testid="vp-poc-label"
          x={Y_AXIS_W + pocBar.w + 3}
          y={pocBar.y + pocBar.h / 2}
          dy="0.35em"
          className="fill-accent stroke-surface"
          strokeWidth={2}
          paintOrder="stroke"
          fontSize="0.5625rem"
        >
          {fmt(pocBar.priceMilli)}
        </text>
      ) : null}
      {/* 當日成交點(R2 SC-3):我的委託在哪一分鐘、什麼價位成交。買 ▲ 紅 / 賣 ▼ 綠,
          尖端指在成交價上(`projectFills` 已把窗外 / 域外的濾掉)。

          **必須是本層最後一組**:svg 沒有 z-index,圖層完全由文件順序決定 —— 排在極值
          標記 / MA 價位標 / VWAP / POC 之前的話,那些帶 2px halo 的文字會把三角吃掉,
          而畫面上照樣「有東西」,零錯誤訊號(同極值標記要畫在主價線之後的理由)。
          現價圈與 hover 十字仍在 ChartStatic 之外、圖層更上,那兩者是即時態游標語彙,
          蓋住某一個成交點可接受。

          群組 `<g>` **恆 render**(空集合時內容為空):條件 render 的話「層不見了」與
          「今天沒成交」在測試裡是同一個答案。testid 刻意不與 `fill-` 前綴共用 ——
          per-card 計數一律 `polygon[data-testid^="fill-"]`,群組不得混進計數。
          `pointerEvents="none"`:三角壓在價線上,不可攔掉 svg 的 hover。 */}
      <g data-testid="fills-layer" pointerEvents="none">
        {fillMarks.map((m) => (
          <polygon
            // key 與 testid 同字串:同分鐘同向已在 `fillPoints` 合併成一點,
            // 所以 `分鐘 × 側` 在同一張圖上唯一
            key={`fill-${m.side}-${m.minute}`}
            data-testid={`fill-${m.side}-${m.minute}`}
            points={fillTrianglePoints(m.x, m.y, m.side)}
            className={cn(m.side === "B" ? "fill-bull" : "fill-bear", "stroke-surface")}
            strokeWidth={FILL_MARK.halo}
            paintOrder="stroke"
          />
        ))}
      </g>
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
  xw,
  hourTicks,
}: {
  w: number;
  h: number;
  tagSpan: [number, number] | null;
  xw: XWindow;
  hourTicks: readonly HourTick[];
}) {
  return (
    <g>
      {hourTicks.map(({ minute, label }) => {
        const x = minuteToX(minute, w, xw) + 2;
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

/** 成交量副圖的 bar 層。
 *
 *  演變:內外盤並排 → 總量堆疊(round5 E)→ 灰段改斜線紋理(round6)→
 *  **單色單根,不分內外盤(round6c,user 拍板)**。
 *
 *  灰段是 user 連兩輪反映的痛點:它在圖表語彙裡看起來像「第三種方向」,而它其實是
 *  「判不出方向」。修完後端判定的根因、又改成紋理之後 user 仍覺得多餘 ——
 *  拍板「不要分顏色,單純顯示量」。內外盤統計沒有消失,只是移出圖形語彙由說明列承載。
 *
 *  **必須 memo**:hover 每個 mousemove 都 re-render 父層,這層最多 270 個 `<rect>`,
 *  不可每次重建(對齊 ChartStatic 的慣例)。
 *  hover 垂直線刻意畫在本元件之外(同一個 `<svg>` 內的獨立 `<g>`),不進 memo props。 */
const EnergySub = memo(function EnergySub({
  bars,
  maxTotal,
  w,
  h,
  xw,
}: {
  bars: EnergyBar[];
  /** 歸一分母 = 全日最大**總量**,即頂端刻度值 */
  maxTotal: number;
  w: number;
  h: number;
  /** 柱寬分母的來源(見 `barW`);模組層常數,memo 安全 */
  xw: XWindow;
}) {
  const bw = barW(w, xw);
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
      {/* 單色量柱(round6c)。整根以 `b.x` 為**中心** —— `b.x` 是走勢線頂點與十字線的 x,
          舊版把 bar 畫在 `[b.x, b.x+bw]` 讓 `b.x` 變成左緣,十字線因此落在那根的左邊
          (round5 A,user 截圖指認)。 */}
      {bars.map((b) => (
        <rect
          key={`e-${b.x}`}
          data-testid="energy-bar"
          x={b.x - bw / 2}
          y={h - b.h}
          width={bw}
          height={b.h}
          className="fill-ink-muted"
        />
      ))}
    </g>
  );
});

interface Props {
  accum: StockAccum;
  /** 主圖 / 副圖的 viewBox 高度(SC-6)。**純量不是物件** —— memo 子元件吃純量才不會
   *  每次 render 因 identity 改變而重建(W-5)。未傳 = 量測未就緒 / jsdom,沿用固定常數。 */
  mainHeight?: number;
  subHeight?: number;
  /** 期貨態(個股期合約主圖,SC-5/D10):x 窗換成 08:45–13:45,且 overlay / VP 全停。
   *
   *  **顯式 prop,不從 `accum.code` 猜**(R6):code 的形狀(`F:<prod>:<ym>`)是資料層
   *  契約,拿它當渲染分支的判準會讓兩層耦合 —— 後端哪天改 key 形狀,前端就靜默退回
   *  現貨窗(圖照畫、只是窗錯了),而沒有任何錯誤訊號。 */
  stkfut?: boolean;
  /** 使用者當日有成交的委託(R2 SC-3)。**由 caller 折好傳入**,core 不掛
   *  `useCapitalOrders`(白名單 W-7:core 不沾 capital / TQ;既有測試的 fetch stub
   *  不必為此加路由)。identity 必須穩定(caller 的 useMemo,零筆一律 `EMPTY_FILLS`)
   *  —— 每 render 新陣列會打穿 `ChartStatic` 與 `GroupCard` 兩層 memo。 */
  fills?: readonly FillPoint[];
}

export type ChartVariant = "page" | "card";

interface CoreProps extends Props {
  /** toggles **受控**:單檔頁由 `useChartToggles` 餵、群組圖牆由圖牆頂那一份餵。
   *  core 自己不持有 storage 狀態 —— 卡片各持一份的話,同一張圖牆上 50 張卡會各自
   *  讀寫同一個 localStorage key(W-7)。 */
  toggles: ChartToggles;
  /** 未傳 = 唯讀(card 變體:toggle 鈕在圖牆頂,卡片內不得有 button) */
  onToggle?: (key: keyof ChartToggles, value: boolean) => void;
  /** `"page"` = 單檔頁完整 chrome(figure + toggle 鈕列 + 說明列 + readout 六欄);
   *  `"card"` = 群組卡片(div + readout 前四欄),圖形語彙完全相同。 */
  variant: ChartVariant;
  /** viewBox 寬(主副圖共用)。未傳 = `DEFAULT_W`。 */
  width?: number;
  /** `"index"` = 指數分時(台股綜合):副圖 / VP / 成交點 / 說明列一律關,readout 三欄,
   *  疊線由 caller 注入(**不打 `/api/stock/overlay`** —— `IX:TWSE` 不是股號),
   *  右緣與 hover 的價位文字走 `fmt` 不 snap tick(指數沒有可下單檔位)。預設 `"stock"`。 */
  mode?: "stock" | "index";
  /** index 態注入的疊線;stock 態忽略(仍走內建 `useStockOverlay`)。 */
  overlay?: StockOverlay | null;
  /** 疊線查詢失敗**且該查詢當前有效**(語意同 `MarketChart.overlayError`:閘關時不鎖鈕)。 */
  overlayError?: boolean;
  /** 該標的有沒有疊線資料源(櫃買無日 K → false,CDP/MA 恆反灰)。預設 true。 */
  overlaySupported?: boolean;
  /** 反灰時的 tooltip(index 態);預設 `"無日線資料"`。 */
  overlayOffTitle?: string;
  /** svg aria-label;預設 `"分時走勢圖"`(index 態 caller 傳 `${name}分時走勢`,
   *  兩個 pane 同頁時要指認得出是哪一檔)。 */
  ariaLabel?: string;
}

export function IntradayChartCore({
  accum,
  toggles,
  onToggle,
  variant,
  width,
  mainHeight,
  subHeight,
  stkfut = false,
  fills = EMPTY_FILLS,
  mode = "stock",
  overlay: overlayProp = null,
  overlayError = false,
  overlaySupported = true,
  overlayOffTitle = "無日線資料",
  ariaLabel,
}: CoreProps) {
  const card = variant === "card";
  // index 態的**唯一**判別子。一處求值、下面各分支共用 —— 各處各寫一次 `mode === "index"`
  // 的話,漏改一處的樣態是「指數圖只有某一半換了語彙」(例如 readout 三欄了、副圖卻還在)。
  const index = mode === "index";
  // 主副圖共用同一個 viewBox 寬:分開兩份的話,副圖 hover 線的 x 換算與主圖會各自漂
  const w = width ?? DEFAULT_W;
  const mainH = mainHeight ?? MAIN.height;
  const subH = subHeight ?? SUB.height;
  // 模組層常數 → identity 穩定,直接進 memo 子元件的 props 不會打穿 memo
  const xw = stkfut ? STKFUT_WINDOW : SPOT_WINDOW;
  const hourTicks = useMemo(() => hourTicksOf(xw), [xw]);
  // 期貨態不打 overlay:CDP/MA 是**現股日線**衍生的(/api/stock/overlay 吃股號),
  // 對合約既取不到也不該套 —— 拿標的現股的 CDP 疊在期貨價上是假陳述。
  //
  // 第二道閘 `isInstrumentKey`:合約→現貨切換的**那一個 render**,prop 先翻 false 而
  // WS 推來的 `accum` 晚一拍還是合約 snapshot,只靠 `stkfut` 會拿 `F:CDF:202608` 當
  // 股號打進路徑段吃 400(Phase 6 real-env finding,實測 2/2 必現)。兩個判準不重複:
  // prop 管「模式」、code 形狀管「這個字串能不能當股號送出去」。
  //
  // 第三道閘 `index`:指數的 code 是 `IX:TWSE` / `IX:OTC`,既不是股號也取不到現股日線
  // —— 疊線由 caller(`MarketChart`)從 `/api/index/overlay` 注入。
  const overlayQ = useStockOverlay(
    index ? null : accum.code || null,
    !index && !stkfut && !isInstrumentKey(accum.code) && (toggles.cdp || toggles.ma),
  );
  // hover 帶 y:水平線是「自由量尺」(跟滑鼠),不再鎖該分鐘收盤價 —— 鎖收盤價的水平線
  // 與價格線重合、資訊冗餘,且量不到「現價到 CDP 線差幾%」這種盤中最常做的事。
  const [hover, setHover] = useState<{ min: number | null; y: number } | null>(null);
  // useId 產出含非識別字元(React 19 為 «r0»),過濾後才拼進 url(#…)
  const uid = safeIdToken(useId());
  const clipAbove = `${uid}-above`;
  const clipBelow = `${uid}-below`;

  const g = useMemo(
    () =>
      buildIntradayGeometry(
        { minutes: accum.minutes, meta: accum.meta, high: accum.high, low: accum.low },
        { width: w, height: mainH },
        xw,
      ),
    // w / mainH 必入 deps:少了高度,viewBox 會換成新高而 toY / 刻度仍是舊高算的,
    // 畫面錯位且不報錯(專案 eslint 沒裝 react-hooks,exhaustive-deps 抓不到)。
    // `xw` 同理 —— 漏了它,現貨↔期貨切換時幾何會停在舊窗上。
    [accum.minutes, accum.meta, accum.high, accum.low, w, mainH, xw],
  );

  // 成交點 → SVG 座標(SC-3)。**必經 useMemo**,理由同 `vpBars`:hover 每個 mousemove
  // 都 re-render 本元件,每輪新陣列會打穿 ChartStatic 的 memo(SC-9 的機械閘)。
  // toggle 關時回**模組層常數**而不是新的 `[]` —— 關著的圖每秒仍隨報價 re-render,
  // 回新陣列一樣打穿 memo,而症狀只是掉幀、沒有測試會紅。
  // 位置必須在 `g` 之後、`priceLine.length === 0` 早退**之前**:hook 不可條件化
  // (本 repo 沒裝 react-hooks lint,漏了不會被擋)。
  const fillMarks = useMemo(
    () => (toggles.fills ? projectFills(fills, g, w, xw) : EMPTY_MARKS),
    [fills, g, w, xw, toggles.fills],
  );

  // 副圖只需要 bar 與歸一分母 —— 原本整份跑一次 buildIntradayGeometry(L-1),
  // 價線 / 刻度 / 反演算完即丟。`meta` 不影響量的幾何,故不入 deps。
  // index 態不 render 副圖(指數無量),但 hook 不可條件化 → 回模組層常數而不是新物件。
  const subEnergy = useMemo(
    () => (index ? EMPTY_ENERGY : buildEnergyBars(accum.minutes, { width: w, height: subH }, xw)),
    [index, accum.minutes, w, subH, xw],
  );

  // 價位別成交量(SC-3)。**必經 useMemo**:hover 每個 mousemove 都 re-render 本元件,
  // 陣列每次新 identity 會打穿 ChartStatic 的 memo,整層線圖跟著重建。
  // 關掉時回**同一個空陣列語意**的重算即可 —— 依賴沒變就不會重算,不需要另設常數。
  // `w` 直接沿用傳給 `buildIntradayGeometry` 的同一個值:寬度另寫一份字面值的話,
  // 幾何與長條會各自依據不同的畫布寬算,bar 的滿寬比例靜默漂掉。
  // 期貨態不畫 VP:`accum.vp` 由 `foldVp` 折出,而 foldVp 的分鐘窗仍是現貨窗
  // (本輪不參數化 —— 期貨態既然不畫,參數化只是加一條沒人走的分支)。
  // 直方圖若照畫,08:45–08:59 與 13:31–13:45 的成交會整段缺席而畫面看不出來。
  // index 態同樣不畫:`accum.vp` 是空 Map(指數沒有逐筆量),畫出來是一片空白的假圖層。
  const vpEnabled = toggles.vp && !stkfut && !index;
  const vpBars = useMemo(
    () => (vpEnabled ? buildVpBars(accum.vp, g, w) : []),
    [accum.vp, g, vpEnabled, w],
  );

  // index 態:資料源與失敗旗標都換一邊(caller 注入),**判準本身逐字相同** ——
  // 兩態各寫一份 available 判定的話,「未回前視為可用」這條紀律會在其中一態靜默漂掉。
  const overlay = index ? overlayProp : (overlayQ.data ?? null);
  const overlayFailed = index ? overlayError : overlayQ.isError;
  // index 態多一道資料源閘:櫃買沒有日 K 來源(已拍板跳過),CDP/MA 恆反灰。
  const supported = !index || overlaySupported;
  // 可用性:資料未回前視為可用(不預先反灰);回了但該類 null / 請求失敗 → 反灰 + 顯示 off
  const cdpAvailable =
    supported && (overlayFailed ? false : overlay ? overlay.cdp !== null : true);
  const maAvailable =
    supported &&
    (overlayFailed ? false : overlay ? overlay.ma5 !== null || overlay.ma20 !== null : true);

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

  // 域外掛牌(index 態限定)。與 `oLines` 互補:同一個值只會進其中一邊。
  // 位置必須在 `g` 之後、`priceLine.length === 0` 早退**之前**:hook 不可條件化
  // (本 repo 沒裝 react-hooks lint,漏了不會被擋)—— 同 `fillMarks` 的理由。
  // stock 態回**模組層常數**而不是新的 `[]`(打穿 ChartStatic 的 memo 只會掉幀,沒有測試會紅)。
  const pegs = useMemo(
    () =>
      index && overlay
        ? outOfDomainLevels(overlay, g, {
            cdp: toggles.cdp && cdpAvailable,
            ma: toggles.ma && maAvailable,
          })
        : EMPTY_PEGS,
    [index, overlay, g, toggles.cdp, toggles.ma, cdpAvailable, maAvailable],
  );

  if (g.priceLine.length === 0) {
    return (
      // index 態**去框**:MarketPane 的 figure 已經是外框,再套一層就是盤前每個 pane
      // 框中框(同 card 變體的理由)。
      <div
        className={cn(
          "flex min-h-0 flex-1 items-center justify-center",
          !index && "rounded-md border border-line bg-surface",
        )}
      >
        <p className="text-sm text-ink-muted">{index ? "等待指數資料…" : "尚無成交"}</p>
      </div>
    );
  }

  // card 變體整條說明列都不 render(AD-4)→ 這份聚合沒有讀者(review B4)。
  // `sideSummary` 走一遍當日最多 271 格,而圖牆最多 50 張卡、每秒隨報價 re-render 各跑
  // 一次;算完直接丟掉。page 變體逐值不變。
  // index 態同樣不 render 說明列:指數沒有內外盤可言,印出來的四個數字全是 0(假陳述)。
  const side = card || index ? null : sideSummary(accum.minutes, xw);
  const lowDecided = side !== null && side.decidedPct !== null && side.decidedPct < LOW_DECIDED_PCT;

  const hoverMin = hover?.min ?? null;
  const hoverAgg = hoverMin !== null ? accum.minutes.get(hoverMin) : undefined;
  // **一次歸一,三處共用**(lastTone / hover 時間標籤 / shownChg)。TC4 送 "0" 時後端
  // 原樣轉 0 不轉 null,而毫元恆 > 0 → 拿 0 當平盤比較永遠是「高於」,三處會一起
  // 靜默塗成紅色。歸一在這裡而不是各判色點各補一次 `> 0`,是為了不讓三處各漂各的。
  const ref = (accum.meta?.ref ?? 0) > 0 ? accum.meta!.ref : null;
  const plotBottom = mainH - X_LABEL_H;

  // 資訊列:沒 hover 顯示最新分鐘(即時態),不是空白
  const lastPt = lastPoint(g);

  // 當日高低標記已下沉進 geometry(`g.highMark` / `g.lowMark`):域外、等值反查落空、
  // 舊後端缺 per-minute h/l 三種成因都收斂成 null = 不畫。
  // 現價圈(SC-2):值每 tick 都變 → 畫在 ChartStatic 之外,不打穿 memo
  const lastPrice = accum.last?.p ?? null;
  // 判色與極值標記同一份規則(`markTone`:高於平盤紅 / 低於綠 / 平盤與無參考價灰)——
  // 就地再寫一次三元式的話,兩處會各自漂
  const lastTone = lastPrice === null ? "fill-ink-dim" : markTone(lastPrice, ref);
  const shownMin = hoverAgg !== undefined ? hoverMin! : (lastPt?.minute ?? null);
  // hover 態的 shownMin 恆等於 hoverMin → 重用已取好的那一格,不再查第二次(L-3)
  const shownAgg = hoverAgg ?? (shownMin !== null ? accum.minutes.get(shownMin) : undefined);
  const shownChg =
    shownAgg !== undefined && ref ? chgPct(shownAgg.c, ref) : null;
  const allFields: ReadoutField[] =
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
            value: shownChg === null ? "-" : fmtPct(shownChg),
            tone: shownChg === null ? "muted" : shownChg > 0 ? "bull" : shownChg < 0 ? "bear" : "muted",
          },
          { label: "量", value: String(shownAgg.v) },
          { label: "外", value: String(shownAgg.o), tone: "bull" },
          { label: "內", value: String(shownAgg.i), tone: "bear" },
        ];
  // 「成交」欄(R2 SC-4):shown 分鐘上有我的成交時**尾端追加**一欄。
  //
  // **page 變體限定**:card 的 readout 只有 246px 寬且 `overflow-hidden`,追加第五欄
  // 必被裁 = 靜默失敗(與 card 砍外 / 內兩欄同理)。標記本身已承載「這裡成交了」,
  // 卡片上少的只是數字。
  // tone:單側跟該側漲跌色,雙側不判色 —— 一欄兩個方向塗成任一色都是假陳述。
  //
  // 吃的是 **`fillMarks` 而不是 `fills`**(cr1 A-2):readout 與三角必須同一把尺。
  // 吃未過濾的 `fills` 時,價格落在 `g.yDomain` 外(autofit 域 / card 較窄域)或分鐘落在
  // x 窗外的那一筆,圖上一個三角都沒有而 readout 照樣報「成交 賣 1@9999」——
  // 使用者在圖上找不到那一筆,兩邊都不會有錯誤訊號。`FillMark extends FillPoint`,
  // 所以 `fillsAtMinute` / `fillLabel` 直接吃得下。
  // `toggles.fills` 不必再判一次:關著時 `fillMarks` 已是 `EMPTY_MARKS`(同一把尺的意思
  // 就是只留一個判準;再寫一次的話兩處哪天漂掉,症狀是「圖關了 readout 還在報」)。
  const fillPts =
    !card && shownMin !== null ? fillsAtMinute(fillMarks, shownMin) : EMPTY_FILLS;
  const fillField: ReadoutField | null =
    fillPts.length === 0
      ? null
      : {
          label: "成交",
          value: fillLabel(fillPts, fmt),
          tone: fillPts.every((p) => p.side === "B")
            ? "bull"
            : fillPts.every((p) => p.side === "S")
              ? "bear"
              : undefined,
        };
  // 卡片只有 ~250px 寬,六欄會擠成一團 —— 砍的是**外 / 內**兩欄(說明列已同時省略,
  // 內外盤在卡片上完全不出現,語意一致),留下時間 / 價 / % / 量(AD-4)。
  // index 態切**前三欄**(時間 / 點位 / 漲跌%):量 / 外 / 內在指數上恆為 0,
  // 印出來是三個假數字而不是「沒有這項資訊」。
  const fields = (card || index ? allFields.slice(0, index ? 3 : 4) : allFields).concat(
    fillField === null ? [] : [fillField],
  );

  // index 態不 snap tick:tick 表是個股的可下單檔位,指數的價位量尺是連續的 ——
  // snap 出來的點位是憑空捏造的(同右緣 `priceText` 的口徑分權)。文字口徑走 `fmtIndexPts`
  // (加權 8 字會溢出 36px 價標盒 → 收整數點;櫃買 6 字保留小數),見 lib/format。
  const hoverPrice =
    hover === null ? null : index ? g.priceAtY(hover.y) : snapDown(g.priceAtY(hover.y));
  const hoverPriceText =
    hoverPrice === null ? "" : index ? fmtIndexPts(hoverPrice) : fmt(hoverPrice);
  const timeTagX =
    hoverMin !== null ? clampTagX(minuteToX(hoverMin, w, xw), TIME_TAG.w, w) : null;
  const timeTagSpan: [number, number] | null =
    timeTagX === null ? null : [timeTagX, timeTagX + TIME_TAG.w];

  function onMove(e: React.MouseEvent<SVGSVGElement>): void {
    const rect = e.currentTarget.getBoundingClientRect();
    const { x, y } = toSvgPoint(e, rect, { width: w, height: mainH });
    const min = g.minuteOf(x);
    const ry = Math.round(y);
    // 值相同就回 prev 讓 React bail out:亞像素抖動不該觸發 re-render
    setHover((p) => (p !== null && p.min === min && p.y === ry ? p : { min, y: ry }));
  }

  // 期貨態三顆一律反灰(D10):CDP/MA 是現股日線衍生、VP 的折入窗仍是現貨窗。
  // 「按得下去但沒反應」比「按不下去」難懂 —— 反灰 + tooltip 才講得出為什麼。
  //
  // index 態只三顆:量分佈 / 成交點都需要逐筆量或委託,指數兩者皆無。
  // 均價鈕帶 `hint`(可用時仍顯示的 tooltip):指數的「均價」是**分鐘收盤算術平均**
  // 不是 VWAP,不講清楚會被當成加權均價讀。
  const toggleDefs: {
    key: "vwap" | "cdp" | "ma" | "vp" | "fills";
    label: string;
    available: boolean;
    hint?: string;
  }[] = index
    ? [
        { key: "vwap", label: "均價", available: true, hint: "分鐘收盤均價(指數無成交量)" },
        { key: "cdp", label: "CDP", available: cdpAvailable },
        { key: "ma", label: "MA", available: maAvailable },
      ]
    : [
        { key: "vwap", label: "均價", available: true },
        { key: "cdp", label: "CDP", available: !stkfut && cdpAvailable },
        { key: "ma", label: "MA", available: !stkfut && maAvailable },
        // 價位別成交量沒有外部資料依賴(全由手上的 tick 折出來),現貨態恆可用
        { key: "vp", label: "量分佈", available: !stkfut },
        // 成交點同樣零外部資料依賴(orders 已在手上),**期貨態也不反灰**(AD-5):
        // 個股期的委託本來就標得到(比對鍵是契約碼),反灰沒有理由。
        { key: "fills", label: "成交點", available: true },
      ];

  const body = (
    <>
      {/* 頂列:左資訊條、右 toggle。高度以 rem 固定,與 K 線頂列逐項對稱(SC-6.7) */}
      <div className="mb-1 flex h-[1.375rem] items-center justify-between gap-2">
        <ChartReadout fields={fields} hovering={hoverAgg !== undefined} />
        {/* card 變體**不得有 button**:卡片外層自己是 role=button(點卡片切主檔),
            內層再放按鈕會讓點 toggle 同時切主檔,而且巢狀互動元素不合法 */}
        {card ? null : (
        <div className="flex shrink-0 gap-1">
        {toggleDefs.map(({ key, label, available, hint }) => (
          <button
            key={key}
            type="button"
            aria-pressed={toggles[key] && available}
            disabled={!available}
            title={
              available
                ? hint
                : index
                  ? overlayOffTitle
                  : stkfut
                    ? "期貨合約本輪不提供"
                    : "無日線資料"
            }
            onClick={() => onToggle?.(key, !toggles[key])}
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
        )}
      </div>
      <svg
        viewBox={`0 0 ${w} ${mainH}`}
        className="w-full"
        style={{ touchAction: "pan-y" }}
        role="img"
        aria-label={ariaLabel ?? "分時走勢圖"}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        <ChartStatic
          g={g}
          w={w}
          h={mainH}
          refMilli={ref}
          showVwap={toggles.vwap}
          vwapMilli={accum.vwap ?? null}
          oLines={oLines}
          vpBars={vpBars}
          clipAbove={clipAbove}
          clipBelow={clipBelow}
          plotBottom={plotBottom}
          xw={xw}
          hourTicks={hourTicks}
          fillMarks={fillMarks}
          // 模組層函式 → identity 穩定,不打穿 memo(行內箭頭函式會)
          priceText={index ? fmtIndexPts : fmtTickPrice}
          tickText={index ? fmtIndexPts : undefined}
          pegs={pegs}
        />
        <XAxisLabels w={w} h={mainH} tagSpan={timeTagSpan} xw={xw} hourTicks={hourTicks} />
        {/* 現價圈(round4 項 2:價位文字已移除)。文字畫在圓點右上,走勢走到右側時
            會與右緣疊線價位標(R_AXIS_W 帶)重疊;現價本來就在資訊列與報價 header
            各有一份,圈的作用是「線走到哪」而不是再報一次價。 */}
        {lastPt !== null && lastPrice !== null ? (
          <g pointerEvents="none">
            <circle data-testid="last-dot" cx={lastPt.x} cy={lastPt.y} r={3} className={lastTone} />
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
                  x1={minuteToX(hoverMin, w, xw)}
                  x2={minuteToX(hoverMin, w, xw)}
                  y1={0}
                  y2={plotBottom}
                  className="stroke-ink-muted"
                  strokeDasharray="2 2"
                  strokeWidth={0.7}
                />
                {/* 該分鐘收盤的視覺錨 —— 水平線變量尺後,收盤位置改由這顆點承接 */}
                <circle
                  cx={minuteToX(hoverMin, w, xw)}
                  cy={g.toY(hoverAgg.c)}
                  r={2.5}
                  className="fill-ink"
                />
              </>
            ) : null}
            <line
              data-testid="crosshair-h"
              x1={Y_AXIS_W}
              x2={w - R_AXIS_W}
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
              {/* 與靜態刻度同一條右對齊基準線(round4 項 6):視覺上像「價位軸在游標那一格
                  亮起來」,而不是另一個飄出來的框 */}
              <text
                data-testid="price-tag-text"
                x={PRICE_TAG.w - 4}
                y={PRICE_TAG.h - 4}
                textAnchor="end"
                className="fill-ink"
                fontSize="0.5625rem"
              >
                {hoverPriceText}
              </text>
            </g>
            {/* 底部標籤:上行時間、下行該分鐘成交價(round4 項 3)。
                價位取 `hoverAgg.c` 與資訊列同源 —— 左緣 price-tag 是「自由量尺」(滑鼠 y),
                兩者語意分權:左緣 = 我想量的價,底部 = 該分鐘真實成交。
                時間黃(與 x 軸標籤同色)、價位紅綠(與圖上每個價格輸出同規則),
                一眼分辨上行是時間語意、下行是價格語意。 */}
            {timeTagX !== null && hoverMin !== null && hoverAgg !== undefined ? (
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
                  y={10}
                  textAnchor="middle"
                  className="fill-time"
                  fontSize="0.625rem"
                >
                  {hhmm(hoverMin)}
                </text>
                <text
                  data-testid="time-tag-price"
                  x={TIME_TAG.w / 2}
                  y={21}
                  textAnchor="middle"
                  // `ref` 的 null 檢查必須在最前面:`c > null` 會把 null 強轉 0,
                  // 毫元恆 > 0 → 無昨收的商品被塗成紅色,打穿 hasRef 紀律(W-6)
                  className={
                    ref === null
                      ? "fill-ink"
                      : hoverAgg.c > ref
                        ? "fill-bull"
                        : hoverAgg.c < ref
                          ? "fill-bear"
                          : "fill-ink"
                  }
                  fontSize="0.625rem"
                >
                  {fmt(hoverAgg.c)}
                </text>
              </g>
            ) : null}
          </g>
        ) : null}
      </svg>
      {/* 內外盤能量副圖。**不加 mt-1**:兩張圖的 svg 佔容器寬比例要相同(SC-6.7),
          多出的固定 4px 會讓比例隨容器寬漂移。
          index 態整張不 render(不是畫一張空的):指數沒有成交量,空副圖佔著版面又
          讓人以為「今天沒量」,而不是「這個商品沒有這項資料」。 */}
      {index ? null : (
      <svg viewBox={`0 0 ${w} ${subH}`} className="w-full" role="img" aria-label="成交量">
        <EnergySub bars={subEnergy.bars} maxTotal={subEnergy.maxTotal} w={w} h={subH} xw={xw} />
        {/* 垂直線延伸進副圖,讓該分鐘的內外盤 bar 可對位;畫在 memo 之外 */}
        {hoverMin !== null ? (
          // 這條線畫在副圖的 viewBox 裡 → x 必須用副圖的寬換算(L-19)。主副圖現在共用
          // **同一個 `w`**(不再是兩個「碰巧相等」的常數),對位由建構保證。
          <line
            x1={minuteToX(hoverMin, w, xw)}
            x2={minuteToX(hoverMin, w, xw)}
            y1={0}
            y2={subH}
            className="stroke-ink-muted"
            strokeDasharray="2 2"
            strokeWidth={0.7}
            pointerEvents="none"
          />
        ) : null}
      </svg>
      )}
      {/* 說明列(round6 項 2)。四個數字全部同源走 `sideSummary(accum.minutes)` ——
          舊版的外 / 內取自後端 running 值而未分類根本沒印,補印未分類就必須從分鐘聚合算,
          那時混用兩個來源的失效樣態是純數字不一致,沒有任何測試會紅。

          「判定率」是本輪的關鍵資訊:外盤比的分母**排除**未分類,而這件事以前完全沒揭露。
          判定率一低就代表那個百分比是用不到一半的資料算出來的 —— 低於門檻時把外盤比
          降對比,讓失真的數字自己承認。 */}
      {/* `h-4` 是固定 16px,任何換行都會直接溢出壓到下方元素(Phase 5 review P2)——
          左段本輪從 ~33 字元長到 ~46 字元,窄容器時會換行。兩段各自 nowrap,
          左段可截斷、右段不縮。
          card 變體整列省略(AD-4):卡片寬度裝不下,且 `<figcaption>` 在 `<div>` 下無語意。 */}
      {/* 閘用 `side === null`(= card 或 index 態)而不是再讀一次 `card || index`:兩個判準各寫一次時
          TS 也 narrow 不出 `side` 非空,而 `side!` 會把「哪天忘了算」變成 runtime 崩潰 */}
      {side === null ? null : (
      <figcaption className="mt-1 flex h-4 items-center justify-between gap-2 font-mono text-xs text-ink-dim">
        <span className="min-w-0 truncate whitespace-nowrap">
          外盤 <span className="text-bull">{side.outer}</span> · 內盤{" "}
          <span className="text-bear">{side.inner}</span> · 未分類{" "}
          <span data-testid="unch-total">{side.unch}</span> · 外盤比{" "}
          <span data-testid="outer-pct">
            {side.outerPct === null ? "-" : `${side.outerPct.toFixed(1)}%`}
          </span>{" "}
          {/* 警示掛在**判定率**上,不暗化外盤比(2026-07-31 user 拍板):降對比在 UI
              語彙裡是「不重要 / 停用」,而外盤比是「重要但失真」——讀者該看到它、
              同時知道它的分母縮水了。判定率本來就印在旁邊,暗化外盤比沒有增加任何
              資訊位元,只增加一個門檻懸崖(判定率會隨盤中累積漂移,跨過就整個翻面)。 */}
          <span
            data-testid="decided-pct"
            className={cn(lowDecided && "text-warn")}
            title={lowDecided ? "判定率偏低:外盤比的分母排除了未分類量" : undefined}
          >
            (判定率 {side.decidedPct === null ? "-" : `${side.decidedPct.toFixed(0)}%`})
          </span>
        </span>
        <span className="shrink-0 whitespace-nowrap">
          {overlay?.date && (toggles.cdp || toggles.ma) ? `疊線基準 ${overlay.date} · ` : ""}
          VWAP {accum.vwap != null ? fmt(accum.vwap) : "-"}
        </span>
      </figcaption>
      )}
    </>
  );

  // select-none:SVG 的 <text>(時間軸 / 價位 / % / 疊線 label)與下方內外盤 figcaption
  // 預設可選,在圖上拖曳會整片反白(SC-4)。不影響 hover(W-10)。
  // card 變體外層是 `<div>` 且無 border / bg / padding(AD-4):卡片自己已經有框,
  // 再套一層就是框中框;`<figure>` 也失去語意(說明列已省略)。
  // index 態同款:MarketPane 的 figure 已是外框,說明列同樣省略。
  return card || index ? (
    <div className="flex min-h-0 flex-1 flex-col select-none">{body}</div>
  ) : (
    <figure className="flex min-h-0 flex-1 flex-col select-none rounded-md border border-line bg-surface p-4">
      {body}
    </figure>
  );
}

/** 單檔頁分時圖(非受控:toggles 自持)。**簽名不變**(W-1/SC-4)—— 圖牆的卡片走
 *  `IntradayChartCore` 的 card 變體,兩者是同一份渲染碼。 */
export function StockIntradayChart({
  accum,
  mainHeight,
  subHeight,
  stkfut = false,
  fills,
}: Props) {
  const { toggles, set } = useChartToggles();
  return (
    <IntradayChartCore
      accum={accum}
      toggles={toggles}
      onToggle={set}
      variant="page"
      mainHeight={mainHeight}
      subHeight={subHeight}
      stkfut={stkfut}
      fills={fills}
    />
  );
}
