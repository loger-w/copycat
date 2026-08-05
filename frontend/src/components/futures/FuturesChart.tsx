import { useMemo, useState, type ReactNode } from "react";

import { CandleChart, type ChartHLine } from "@/components/stock/CandleChart";
import { useCapitalPositions } from "@/hooks/useCapital";
import { useFuturesBars, type FuturesBarsKey } from "@/hooks/useFuturesBars";
import { useOiLevels } from "@/hooks/useOiLevels";
import { ALLDAY_LEN, ALLDAY_TICKS, alldayIndexOf, anchorDateOf, sliceCurrentAllday } from "@/lib/allday";
import { aggregateBars, type Bar } from "@/lib/candle";
import { fmt } from "@/lib/format";
import {
  FUT_CHART_MODES,
  futMinutesOf,
  initialFutChartMode,
  persistFutChartMode,
  type FutChartMode,
} from "@/lib/fut-chart-mode";
import { futExchangeContract } from "@/lib/futures-ladder";
import { pickOiLines } from "@/lib/oi-levels";
import { pts } from "@/lib/svg-points";
import { cn } from "@/lib/utils";
import type { FuturesProductState } from "@/types";

/** 期貨 tab 主圖(SC-1/2/4/7/8/11)。
 *
 * 一份 `tf=1&session=allday` 原料餵所有分鐘級模式:分時走本檔的近全軸 SVG、
 * 分 K 走 `aggregateBars` → `CandleChart`、日 K 另走 `tf=D`。
 *
 * **overlays(均價線 / OI 撐壓)兩種模式都畫**,幾何各自算但語意同一套:
 * 超出當前 y 視窗的線一律不畫(clamp 到邊緣會把「圖外的價位」講成「圖緣的價位」)。
 */

/** 分時 viewBox 寬。**刻意 = `ALLDAY_LEN`** —— 一分鐘一像素,x 幾何就是索引本身,
 *  軸標籤與折線不可能各算一份比例而漂移。export 供測試算期望 x。 */
export const INTRADAY_VB_W = ALLDAY_LEN;
const INTRADAY_VB_H = 340;
/** y 域上下 pad(指數 / 期指皆無漲跌停以外的自然邊界,沿用大盤分時的 0.3%) */
const Y_PAD = 0.003;
/** 底部時間標籤帶 */
const X_LABEL_H = 12;

const DAILY_INIT_BARS = 120;
const MINUTE_INIT_BARS = 240;

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** `YYYY-MM-DD HH:MM` → 近全軸索引;非分 K 時戳 / 死區 → null。 */
function indexOfBar(t: string): number | null {
  const sp = t.indexOf(" ");
  if (sp < 0) return null;
  const hhmm = t.slice(sp + 1);
  return alldayIndexOf(`${hhmm.slice(0, 2)}${hhmm.slice(3, 5)}`);
}

interface IntradayPoint {
  index: number;
  c: number;
}

/** 牆上時鐘 → live 點的落點。
 *
 *  **終點標記 + 1 分**:1K 的 `t` 是 bar 的**終點**,10:00:30 這一刻的成交屬於標記
 *  10:01 的那根(design §3.2;與 §1.1 的「1K row 不加 1」是不同語意的兩件事 ——
 *  那邊的來源已經是終點標記,這邊的來源是牆上時鐘)。
 *
 *  回傳的 `anchor` 供錨定日 gate 用:開盤瞬間(08:45–08:46,今日首根未回)slice 仍
 *  錨在前一交易日,live 點若照畫會落在 x=0 拉出一條橫貫整圖的假線。 */
function liveSlotOf(now: Date): { index: number; anchor: string } | null {
  const t = new Date(now.getTime() + 60_000);
  const hh = pad2(t.getHours());
  const mm = pad2(t.getMinutes());
  const index = alldayIndexOf(`${hh}${mm}`);
  if (index === null) return null; // 死區(13:46–15:00 / 05:01–08:45)
  const date = `${t.getFullYear()}-${pad2(t.getMonth() + 1)}-${pad2(t.getDate())}`;
  return { index, anchor: anchorDateOf(`${date} ${hh}:${mm}`) };
}

interface IntradayGeometry {
  line: { x: number; y: number }[];
  refY: number;
  yTicks: { y: number; priceMilli: number }[];
  /** 毫點 → y;**超出 y 域回 null**(overlay 線不畫,同 `hlineYOf` 的判定語意) */
  hlineY: (priceMilli: number) => number | null;
}

function toX(index: number): number {
  return (index / ALLDAY_LEN) * INTRADAY_VB_W;
}

function buildIntradayGeometry(
  series: readonly IntradayPoint[],
  refMilli: number | null,
  height: number,
): IntradayGeometry {
  const closes = series.map((p) => p.c);
  const base =
    refMilli ?? (closes.length > 0 ? closes.reduce((s, c) => s + c, 0) / closes.length : 0);
  const hi = Math.max(base, ...closes);
  const lo = Math.min(base, ...closes);
  const yTop = hi * (1 + Y_PAD) || 1;
  const yBottom = lo * (1 - Y_PAD);
  const span = yTop - yBottom || 1;
  const toY = (p: number): number => ((yTop - p) / span) * height;
  return {
    line: series.map((p) => ({ x: toX(p.index), y: toY(p.c) })),
    refY: toY(base),
    yTicks: [yBottom, base, yTop].map((p) => ({ y: toY(p), priceMilli: Math.round(p) })),
    hlineY: (priceMilli) =>
      priceMilli >= yBottom && priceMilli <= yTop ? toY(priceMilli) : null,
  };
}

function IntradayChart({
  series,
  refMilli,
  live,
  hlines,
}: {
  series: readonly IntradayPoint[];
  refMilli: number | null;
  /** live 點的軸索引(已過死區與錨定日 gate);無 live 點 → null */
  live: number | null;
  hlines: readonly ChartHLine[];
}) {
  const g = buildIntradayGeometry(series, refMilli, INTRADAY_VB_H - X_LABEL_H);
  const lastPt = g.line[g.line.length - 1];
  return (
    <svg
      viewBox={`0 0 ${INTRADAY_VB_W} ${INTRADAY_VB_H}`}
      className="w-full"
      role="img"
      aria-label="期貨近全時段分時走勢"
    >
      {ALLDAY_TICKS.map(({ index, label }) => (
        <g key={label}>
          <line
            x1={toX(index)}
            x2={toX(index)}
            y1={0}
            y2={INTRADAY_VB_H - X_LABEL_H}
            className="stroke-line"
            strokeWidth={0.4}
          />
          <text
            x={toX(index) + 2}
            y={INTRADAY_VB_H - 2}
            className="fill-ink-dim"
            fontSize="0.625rem"
          >
            {label}
          </text>
        </g>
      ))}
      <line
        x1={0}
        x2={INTRADAY_VB_W}
        y1={g.refY}
        y2={g.refY}
        className="stroke-line"
        strokeDasharray="2 3"
        strokeWidth={1}
      />
      {g.yTicks.map((t) => (
        <text
          key={t.priceMilli}
          x={2}
          y={Math.min(Math.max(t.y - 2, 8), INTRADAY_VB_H - X_LABEL_H - 2)}
          className="fill-ink-dim"
          fontSize="0.625rem"
        >
          {fmt(t.priceMilli)}
        </text>
      ))}
      {g.line.length > 0 ? (
        <polyline
          data-testid="allday-line"
          points={pts(g.line)}
          fill="none"
          className="stroke-accent"
          strokeWidth={1.4}
        />
      ) : null}
      {/* live 現價點:只在渲染層 merge(不寫 query cache),所以它就是序列尾那一點 */}
      {live !== null && lastPt !== undefined ? (
        <circle
          data-testid="allday-live"
          cx={toX(live).toFixed(1)}
          cy={lastPt.y.toFixed(1)}
          r={2.5}
          className="fill-accent"
        />
      ) : null}
      {/* 水平 overlay:與 CandleChart 同一套語意(超窗不畫、`<title>` 承載證據) */}
      {hlines.map((ln, i) => {
        const y = g.hlineY(ln.priceMilli);
        if (y === null) return null;
        return (
          <g key={`hl-${i}-${ln.priceMilli}`} data-testid="chart-hline">
            {ln.title === undefined ? null : <title>{ln.title}</title>}
            <line
              x1={0}
              x2={INTRADAY_VB_W}
              y1={y}
              y2={y}
              className={ln.className}
              strokeWidth={1}
              strokeDasharray="5 3"
            />
            <text
              x={INTRADAY_VB_W - 4}
              y={y - 3}
              textAnchor="end"
              className="fill-ink stroke-surface"
              strokeWidth={2}
              paintOrder="stroke"
              fontSize="0.625rem"
            >
              {ln.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

interface Props {
  product: FuturesBarsKey;
  /** WS 現價(live 點與 OI 帶中心);未就緒 → 不畫 live 點、OI 以 `ref` 為中心 */
  state: FuturesProductState | null;
  /** HOT → YYYYMM;null = 合約未解析 → 均價線不畫(不做前綴猜測) */
  resolvedYm: string | null;
  /** 使用者是否正看著期貨 tab(App 的 `tab === "futures"`)。false → 停背景輪詢;
   *  未給時預設 true(獨立使用與既有呼叫路徑不靜默停更)。review LF-2。 */
  active?: boolean;
}

export function FuturesChart({ product, state, resolvedYm, active = true }: Props) {
  const [mode, setMode] = useState<FutChartMode>(initialFutChartMode);
  const { data, isPending, isError, error } = useFuturesBars(product, mode, active);
  const { data: oi } = useOiLevels();
  const { data: positionsData } = useCapitalPositions();

  function selectMode(next: FutChartMode): void {
    setMode(next);
    persistFutChartMode(next);
  }

  const bars: readonly Bar[] = useMemo(() => data?.bars ?? [], [data?.bars]);

  /** 當前商品的期交所契約碼。`futExchangeContract` 對壞 YYYYMM 會拋 —— 這裡在 render
   *  path 上,拋出去就是整個期貨頁白屏(App.tsx 同款處置)。 */
  const contract = useMemo<string | null>(() => {
    if (resolvedYm === null) return null;
    try {
      return futExchangeContract(product, resolvedYm);
    } catch {
      return null;
    }
  }, [product, resolvedYm]);

  const spotMilli = state?.p ?? state?.ref ?? null;
  const positions = positionsData?.positions;
  const oiStrikes = oi?.strikes;
  const oiDate = oi?.date ?? null;

  /** overlay 線。**必須 useMemo**:每次 render 給新 array 會打穿 CandleChart 內
   *  ChartStatic 的 memo(最多 700 根蠟燭跟著重建)。 */
  const hlines = useMemo<ChartHLine[]>(() => {
    const out: ChartHLine[] = [];
    for (const pos of positions ?? []) {
      // 契約**完整字串相等**:rollover 後舊月部位不匹配新月圖表 → 不畫,正確
      if (pos.market !== "fut" || contract === null || pos.stock_no !== contract) continue;
      if (pos.avg_price === null) continue;
      const priceMilli = Math.round(pos.avg_price * 1000);
      const side = pos.qty > 0 ? "多" : "空";
      const lots = Math.abs(pos.qty);
      out.push({
        priceMilli,
        label: `均 ${fmt(priceMilli)} ${side}${lots}口`,
        className: "stroke-accent",
        title: `持倉均價 ${fmt(priceMilli)}・${side}${lots}口・${pos.stock_no}`,
      });
    }
    const { call, put } = pickOiLines(oiStrikes ?? [], spotMilli, oiDate);
    if (call !== null) out.push(call);
    if (put !== null) out.push(put);
    return out;
  }, [positions, contract, oiStrikes, oiDate, spotMilli]);

  // ---- 分時序列(近全軸)-------------------------------------------------
  const slice = useMemo(() => sliceCurrentAllday(bars), [bars]);
  const basePoints = useMemo<IntradayPoint[]>(() => {
    const out: IntradayPoint[] = [];
    for (const b of slice) {
      const index = indexOfBar(b.t);
      if (index === null) continue;
      out.push({ index, c: b.c });
    }
    return out;
  }, [slice]);

  // live 點吃牆上時鐘 → **刻意不進 useMemo**(memo 的 deps 表達不了「現在幾點」;
  // 重算成本是一次 Date 運算)。WS 每則推播都會讓本元件 re-render,自然跟著走。
  const { series, liveIndex } = ((): { series: IntradayPoint[]; liveIndex: number | null } => {
    const none = { series: basePoints, liveIndex: null };
    const last = slice[slice.length - 1];
    const p = state?.p ?? null;
    if (p === null || last === undefined) return none;
    const live = liveSlotOf(new Date());
    if (live === null) return none; // 死區
    if (live.anchor !== anchorDateOf(last.t)) return none; // 錨定日 gate(§3.2)
    const tail = basePoints[basePoints.length - 1];
    if (tail !== undefined && tail.index > live.index) return none; // 時鐘落後資料
    const out = [...basePoints];
    if (tail !== undefined && tail.index === live.index) {
      out[out.length - 1] = { index: live.index, c: p };
    } else {
      out.push({ index: live.index, c: p });
    }
    return { series: out, liveIndex: live.index };
  })();

  // ---- 分 K / 日 K -------------------------------------------------------
  const minutes = futMinutesOf(mode);
  const candleBars = useMemo(() => aggregateBars(bars, minutes), [bars, minutes]);

  const modeRow = (
    <div className="mb-1 flex flex-wrap items-center gap-1">
      {FUT_CHART_MODES.map(([id, label]) => (
        <button
          key={id}
          type="button"
          aria-pressed={mode === id}
          onClick={() => selectMode(id)}
          className={cn(
            "rounded border px-2 py-0.5 text-xs",
            mode === id ? "border-accent text-accent" : "border-line text-ink-dim hover:text-ink",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );

  function body(): ReactNode {
    if (isPending) {
      return (
        <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-line bg-surface">
          <p className="text-sm text-ink-muted">載入中…</p>
        </div>
      );
    }
    if (isError) {
      return (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 rounded-md border border-line bg-surface">
          <p className="text-sm text-bear">K 線載入失敗</p>
          <p className="font-mono text-xs text-ink-dim">{(error as Error | null)?.message ?? ""}</p>
        </div>
      );
    }
    // 空態文案用**進行式**:market bars 路徑無三態,`unavailable` 涵蓋「TC4 慢」與
    // 「真的沒有」兩件事,不可下「這個商品沒有資料」的結論(design §1.4 D8)
    if (data.meta.source === "unavailable") {
      return (
        <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-line bg-surface">
          <p className="text-sm text-ink-muted">暫無資料(TC4 未回應)</p>
        </div>
      );
    }
    if (mode === "intraday") {
      if (series.length === 0) {
        return (
          <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-line bg-surface">
            <p className="text-sm text-ink-muted">無分時資料</p>
          </div>
        );
      }
      return (
        <div className="rounded-md border border-line bg-surface p-2">
          <IntradayChart
            series={series}
            refMilli={state?.ref ?? null}
            live={liveIndex}
            hlines={hlines}
          />
        </div>
      );
    }
    return (
      <CandleChart
        // 換商品 / 換模式強制重掛:viewport 是 CandleChart 的內部 state,
        // 不重掛的話新序列會沿用舊窗口(SC-4 的「圖表跟隨」會只換資料不換視野)
        key={`${product}-${mode}`}
        bars={candleBars}
        initBars={mode === "day" ? DAILY_INIT_BARS : MINUTE_INIT_BARS}
        hlines={hlines}
        // 恆傳 true:日 K(DK 路徑)無 uv/dv,幾何層自動回退主量柱(不畫一排 0 高雙柱)
        volumeDelta
      />
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {modeRow}
      {body()}
    </div>
  );
}

export default FuturesChart;
