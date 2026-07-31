import { memo, useId, useMemo, useState } from "react";

import { ChartReadout, type ReadoutField } from "@/components/chart/ChartReadout";
import { clampLabelX, INTRADAY_MARK, markCenterX, markLabelY, markTone } from "@/lib/chart-extreme";
import { useChartToggles } from "@/hooks/useChartToggles";
import { clampTagX, clampTagY, overlaps, toSvgPoint } from "@/lib/chart-crosshair";
import { fmtTickPrice, snapDown } from "@/lib/stock-tick";
import { useStockOverlay } from "@/hooks/useStockOverlay";
import type { StockAccum } from "@/lib/stock-accum";
import {
  buildIntradayGeometry,
  lastPoint,
  LOW_DECIDED_PCT,
  minuteToX,
  overlayLines,
  plotWidth,
  R_AXIS_W,
  sideSummary,
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
/** 底部 hover 標籤(round4 項 3:時間 + 該分鐘成交價兩行)。
 *  高度**往上長**不往下溢出 —— 盒子底邊已貼死 viewBox 底,而圖高由 StockChart 量測後
 *  指派,不能為了標籤加高。寬度 40 是常數不是 JSX 硬編:`XAxisLabels` 的「與 tag 重疊
 *  就不畫」靠 `tagSpan` 判定,寫死在 JSX 會讓遮蔽判定與實際寬度脫鉤。 */
const TIME_TAG = { w: 40, h: 24 };

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

/** 極值標記文字的 baseline 上界(字高 0.5625rem ≈ 9px,再留 1px 呼吸) */
const MARK_LABEL_TOP = 9;

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
  oLines,
  clipAbove,
  clipBelow,
  plotBottom,
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
  /** 繪圖區底(極值文字翻面判定用);純量,memo 安全 */
  plotBottom: number;
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
      {([
        ["day-high", g.highMark, "up"],
        ["day-low", g.lowMark, "down"],
      ] as const).map(([id, mark, dir]) => {
        if (mark === null) return null;
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
              y={markLabelY(mark.y, dir, INTRADAY_MARK, { top: MARK_LABEL_TOP, bottom: plotBottom })}
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
  hatchId,
}: {
  bars: EnergyBar[];
  /** 歸一分母 = 全日最大**總量**,即頂端刻度值 */
  maxTotal: number;
  w: number;
  h: number;
  /** 未分類段的斜線 pattern id;**純量** prop,不打穿 memo(W-10) */
  hatchId: string;
}) {
  const bw = barW(w);
  const midY = h - (h - SUB_TOP_PAD) / 2;
  return (
    <g>
      {/* 未分類量的斜線紋理(round6 項 2)。
          灰色原本是實心的第三個顏色,而顏色在圖表語彙裡等於「一個類別」——
          使用者問「灰色代表甚麼」其實是在問「這是第三種盤嗎」。它不是:它是**方向未知**。
          紋理不是顏色,讀起來是「這段有不確定性」,顏色維度就只留給紅 / 綠兩個方向。

          `patternUnits="userSpaceOnUse"` 不可改成 objectBoundingBox —— 後者會讓 tile
          被每根 rect 各自拉伸,270 根不同高度的柱子會長出 270 種紋理密度。

          tile 內**先鋪一層低透明度底色再疊斜線**(review R6):柱寬只有約 2.5px,
          純斜線的 tile 有機會整根落在空白帶上 → 該段被畫成透明 = 看起來「這根沒有量」,
          而量刻度分母仍含未分類(W-1)→ 柱高與頂端刻度對不上,比原本的實心灰更難讀。 */}
      <defs>
        <pattern
          id={hatchId}
          patternUnits="userSpaceOnUse"
          width={3}
          height={3}
          patternTransform="rotate(45)"
        >
          <rect width={3} height={3} className="fill-ink-dim" fillOpacity={0.3} />
          {/* 線畫在 tile **中心**不是左邊界(Phase 5 review P2):pattern 會把 tile 外的
              內容裁掉且不 wrap 到對邊,畫在 x=0 時左半 [−0.7, 0) 直接消失 →
              實際只有設計值一半的墨量,而 2.5px 柱寬本來就吃緊。 */}
          <line x1={1.5} y1={0} x2={1.5} y2={3} className="stroke-ink-dim" strokeWidth={1.4} />
        </pattern>
      </defs>
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
            {/* 填色**只能有一個來源**(review R11):`fill` 是 presentation attribute,
                優先權低於任何 CSS 宣告 —— 留著 `fill-*` class 當「保險」的話 Tailwind 會
                蓋掉 pattern,畫面退回實心灰而零錯誤訊號。故走 style 且不掛 fill class。 */}
            <rect
              data-testid="energy-unch"
              x={x}
              y={unchY}
              width={bw}
              height={b.unchH}
              style={{ fill: `url(#${hatchId})` }}
            />
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
  const hatchId = `${uid}-hatch`;

  const g = useMemo(
    () =>
      buildIntradayGeometry(
        { minutes: accum.minutes, meta: accum.meta, high: accum.high, low: accum.low },
        { width: mainW, height: mainH },
      ),
    // mainW / mainH 必入 deps:少了高度,viewBox 會換成新高而 toY / 刻度仍是舊高算的,
    // 畫面錯位且不報錯(專案 eslint 沒裝 react-hooks,exhaustive-deps 抓不到)
    [accum.minutes, accum.meta, accum.high, accum.low, mainW, mainH],
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

  const side = sideSummary(accum.minutes);
  const lowDecided = side.decidedPct !== null && side.decidedPct < LOW_DECIDED_PCT;

  const hoverMin = hover?.min ?? null;
  const hoverAgg = hoverMin !== null ? accum.minutes.get(hoverMin) : undefined;
  const ref = accum.meta?.ref ?? null;
  const plotBottom = mainH - X_LABEL_H;

  // 資訊列:沒 hover 顯示最新分鐘(即時態),不是空白
  const lastPt = lastPoint(g);

  // 當日高低標記已下沉進 geometry(`g.highMark` / `g.lowMark`):域外、等值反查落空、
  // 舊後端缺 per-minute h/l 三種成因都收斂成 null = 不畫。
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
          plotBottom={plotBottom}
        />
        <XAxisLabels w={mainW} h={mainH} tagSpan={timeTagSpan} />
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
                {hoverPrice !== null ? fmt(hoverPrice) : ""}
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
          多出的固定 4px 會讓比例隨容器寬漂移。 */}
      <svg viewBox={`0 0 ${subW} ${subH}`} className="w-full" role="img" aria-label="內外盤能量">
        <EnergySub
          bars={subGeo.energyBars}
          maxTotal={subGeo.maxTotal}
          w={subW}
          h={subH}
          hatchId={hatchId}
        />
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
      {/* 說明列(round6 項 2)。四個數字全部同源走 `sideSummary(accum.minutes)` ——
          舊版的外 / 內取自後端 running 值而未分類根本沒印,補印未分類就必須從分鐘聚合算,
          那時混用兩個來源的失效樣態是純數字不一致,沒有任何測試會紅。

          「判定率」是本輪的關鍵資訊:外盤比的分母**排除**未分類,而這件事以前完全沒揭露。
          判定率一低就代表那個百分比是用不到一半的資料算出來的 —— 低於門檻時把外盤比
          降對比,讓失真的數字自己承認。 */}
      {/* `h-4` 是固定 16px,任何換行都會直接溢出壓到下方元素(Phase 5 review P2)——
          左段本輪從 ~33 字元長到 ~46 字元,窄容器時會換行。兩段各自 nowrap,
          左段可截斷、右段不縮。 */}
      <figcaption className="mt-1 flex h-4 items-center justify-between gap-2 font-mono text-xs text-ink-dim">
        <span className="min-w-0 truncate whitespace-nowrap">
          外盤 <span className="text-bull">{side.outer}</span> · 內盤{" "}
          <span className="text-bear">{side.inner}</span> · 未分類{" "}
          <span data-testid="unch-total">{side.unch}</span> · 外盤比{" "}
          <span
            data-testid="outer-pct"
            className={cn(lowDecided && "text-ink-dim/50")}
            title={lowDecided ? "判定率偏低,外盤比的分母排除了未分類量" : undefined}
          >
            {side.outerPct === null ? "-" : `${side.outerPct.toFixed(1)}%`}
          </span>{" "}
          <span data-testid="decided-pct">
            (判定率 {side.decidedPct === null ? "-" : `${side.decidedPct.toFixed(0)}%`})
          </span>
        </span>
        <span className="shrink-0 whitespace-nowrap">
          {overlay?.date && (toggles.cdp || toggles.ma) ? `疊線基準 ${overlay.date} · ` : ""}
          VWAP {accum.vwap != null ? fmt(accum.vwap) : "-"}
        </span>
      </figcaption>
    </figure>
  );
}
