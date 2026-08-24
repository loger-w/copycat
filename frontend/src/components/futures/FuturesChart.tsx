import { useMemo, useState, type ReactNode } from "react";

import { CandleChart, type ChartHLine } from "@/components/stock/CandleChart";
import { IntradayChartCore } from "@/components/stock/StockIntradayChart";
import { RadioPills } from "@/components/ui/RadioPills";
import { useCapitalOrders, useCapitalPositions } from "@/hooks/useCapital";
import { useChartToggles } from "@/hooks/useChartToggles";
import { useContainerSize } from "@/hooks/useContainerSize";
import { useFuturesBars, type FuturesBarsKey } from "@/hooks/useFuturesBars";
import type { BarsStatus } from "@/hooks/useMarketBars";
import { useOiLevels } from "@/hooks/useOiLevels";
import {
  ALLDAY_HOUR_TICKS,
  ALLDAY_WINDOW,
  alldayHhmmOf,
  alldayIndexOf,
  alldayIndexOfStamp,
  anchorDateOf,
  sliceCurrentAllday,
} from "@/lib/allday";
import { aggregateBars, type Bar } from "@/lib/candle";
import { alldayFillPoints, EMPTY_FILLS } from "@/lib/fill-marks";
import { MAIN_RATIO_DEN, MAIN_RATIO_NUM, svgBox } from "@/lib/chart-frame";
import { fmt } from "@/lib/format";
import {
  FUT_CHART_MODES,
  futMinutesOf,
  initialFutChartMode,
  persistFutChartMode,
  type FutChartMode,
} from "@/lib/fut-chart-mode";
import { futuresBarsToAccum } from "@/lib/futures-accum-adapter";
import { buildFuturesOverlay } from "@/lib/futures-overlay";
import { futExchangeContract } from "@/lib/futures-ladder";
import { pickOiLines } from "@/lib/oi-levels";
import { cn } from "@/lib/utils";
import type { FuturesProductState } from "@/types";

/** 期貨 tab 主圖(SC-1/2/4/7/8/11)。
 *
 * 一份 `tf=1&session=allday` 原料餵所有分鐘級模式:分時走個股同一份
 * `IntradayChartCore`(mode="futures";近全軸由本檔注入)、分 K 走 `aggregateBars`
 * → `CandleChart`、日 K 另走 `tf=D`。
 *
 * **overlays(均價線 / OI 撐壓)兩種模式都畫**:同一份 `hlines` 分別交給 core 與
 * `CandleChart`,兩邊語意同一套 —— 超出當前 y 視窗的線一律不畫
 * (clamp 到邊緣會把「圖外的價位」講成「圖緣的價位」)。
 */

/** 分時 viewBox 寬 = core 的 `DEFAULT_W`;`svgBox` 反解要用同一個值。 */
const INTRADAY_VB_W = 800;

const DAILY_INIT_BARS = 120;
const MINUTE_INIT_BARS = 240;

/** live 點允許的「資料尾 → 最後成交落點」最大索引差(gate 5;bug/futures-intraday-lag-bridge)。
 *
 *  常態落後 = 60 s 輪詢 + 後端 `_today` 30 s 快取 + 終點標記 → ≤ 3 格(輪詢 20 s 實測
 *  `lag_min` 0.2–2.8)。**3 不是 5**:2026-08-25 02:41–02:46 prod 真事件(TXF 夜盤)尾根卡在
 *  02:42 而該五分鐘確有成交,02:46 一口氣補五根 —— 峰值恰 5 格,門檻 5 抓不到;3 從第 4 格起擋。
 *  超過就是當日段回補不完整(TC4 首頁 timeout / 分頁靜默截斷,快取窗內都回
 *  同一份),此時再追加 live 點,core 的單條 polyline 會從資料尾直線拉到現在 —— 一段橫貫
 *  數十分鐘的假直線,而畫面上零錯誤訊號。
 *
 *  判準吃 **WS 最後成交時刻**(`state.t`)不吃牆上時鐘:TMF 夜盤數分鐘零成交是常態,
 *  那種空檔 bars 本來就沒東西可補,拿牆鐘比會把「沒人交易」講成「回補中」。
 *  索引差 = 近全軸上缺的 1K 根數(跨死區時不等於牆鐘分鐘),文案因此講「根」。 */
const FUT_LIVE_LAG_MAX = 3;

/** 空序列時的文案,依 `meta.status`(N104)。
 *
 *  與上面那條 gate 5 的「分時資料落後 N 根」**並存不合併**,兩者定義域幾乎互斥:
 *  這裡答「這一趟根本沒拿到」(bars 空),gate 5 答「拿到的不夠新」(bars 非空)。
 *  合成一句話會讓「TC4 忙」與「回補缺尾」共用同一個提示,而處置不同(等重試 vs
 *  看資料完整性)。
 *
 *  `ok` 那句刻意仍是**進行式**:後端說「這一趟問完了、就是空」,但那既可能是這個
 *  商品今天真沒 K 線、也可能是 TC4 那頭還沒寫出來 —— 不下結論。 */
const EMPTY_TEXT: Record<BarsStatus, string> = {
  timeout: "回補中…(TC4 忙,稍後自動重試)",
  disconnected: "暫無資料(TC4 未連線)",
  ok: "暫無資料(TC4 未回應)",
};

/** WS 最後成交(台北 `YYYY-MM-DD` + `HH:MM:SS.fff`)→ 它所屬 1K bar 的近全軸索引與錨定日。
 *
 *  終點標記:`HH:MM:00.000` 整分成交屬 HH:MM 那根,其餘屬 HH:MM+1(review SP4)。
 *  壞格式 / 死區 → null(gate 5 不參與)。回傳 anchor 讓 caller 擋掉「`state.t` 停在前一
 *  場次」(盤前未成交 / WS 零推播時 t 還是昨夜 04:59)—— 那不是回補落後,是 WS 沒新成交,
 *  拿它比索引會把「WS 靜默」講成「TC4 回補中」(review SP2)。 */
function tradeSlotOf(date: string, t: string): { index: number; anchor: string } | null {
  const m = /^(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?/.exec(t);
  if (m === null || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  const onBoundary = Number(m[3]) === 0 && Number(m[4] ?? "0") === 0;
  const total = (Number(m[1]) * 60 + Number(m[2]) + (onBoundary ? 0 : 1)) % (24 * 60);
  const hhmm = hhmmOf(total);
  const index = alldayIndexOf(hhmm);
  if (index === null) return null;
  // 跨午夜(23:59:30 → 00:00)的日期進位:終點標記落到次日
  const carry = total === 0 && !onBoundary ? 1 : 0;
  const base = new Date(`${date}T00:00:00`);
  base.setDate(base.getDate() + carry);
  const d = `${base.getFullYear()}-${pad2(base.getMonth() + 1)}-${pad2(base.getDate())}`;
  return { index, anchor: anchorDateOf(`${d} ${hhmm.slice(0, 2)}:${hhmm.slice(2)}`) };
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** 一日內的分鐘數(0–1439)→ 近全軸的 `HHMM` 鍵(`liveSlotOf` / `tradeSlotOf` 共用)。 */
function hhmmOf(totalMinutes: number): string {
  return `${pad2(Math.floor(totalMinutes / 60))}${pad2(totalMinutes % 60)}`;
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
  const hhmm = hhmmOf(t.getHours() * 60 + t.getMinutes());
  const index = alldayIndexOf(hhmm);
  if (index === null) return null; // 死區(13:46–15:00 / 05:01–08:45)
  const date = `${t.getFullYear()}-${pad2(t.getMonth() + 1)}-${pad2(t.getDate())}`;
  return { index, anchor: anchorDateOf(`${date} ${hhmm.slice(0, 2)}:${hhmm.slice(2)}`) };
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
  // 疊線(CDP/MA)的資料源 = **期貨日 K**(N042)。與日 K 模式**同一個 queryKey** →
  // TQ 自然去重(兩個 observer 一份 cache、一發請求),`staleTime: Infinity` 讓它一天只打一次。
  // 不掛 `enabled: toggles.cdp || toggles.ma`:那會讓「按下 CDP 才開始抓」多一次空窗閃動,
  // 而這支的成本是每商品每日一發(日 K 模式本來就要抓)。
  const dayQ = useFuturesBars(product, "day", active);
  const { data: oi } = useOiLevels();
  const { data: positionsData } = useCapitalPositions();
  const orders = useCapitalOrders().data?.orders;
  // 全站單一份 toggle 存檔(與個股頁 / 群組圖牆 / 台股綜合共用同一把 localStorage 鍵)
  const { toggles, set } = useChartToggles();

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
  /** 這張圖的交易日(= 最後一根 bar 的錨定日)。成交點的日期界吃它 —— 近全軸橫跨兩個
   *  日曆日,拿本機「今天」當界的話夜盤 00:00–05:00 的成交會被判成別天(N043)。 */
  const anchorDate = useMemo<string | null>(() => {
    const last = slice[slice.length - 1];
    return last === undefined ? null : anchorDateOf(last.t);
  }, [slice]);
  /** CDP / MA(N042)。**日 K 尚未回 / 錨定日還推不出來 → null**(core 的「未回視為可用」
   *  不預先反灰);回了但無已完成 bar → 全 null 的 overlay → 兩鈕反灰。兩者不可混為一談。
   *
   *  基準日的界吃**這張圖的錨定日**,與 slice / live gate / 成交點同一支 `anchorDateOf`
   *  —— 不吃 `meta.partial_last`(日曆日口徑,夜盤兩頭破窗且缺欄時失效在不安全側;
   *  理由全文見 `lib/futures-overlay.ts` 檔頭)。 */
  const overlay = useMemo(
    () =>
      dayQ.data === undefined || anchorDate === null
        ? null
        : buildFuturesOverlay(dayQ.data.bars, anchorDate),
    [dayQ.data, anchorDate],
  );
  /** 當日成交點(N043/N070)。比對鍵 = 期交所契約碼(群益回報的期貨單 `stock_no` 放的
   *  就是它,與 `hlines` 的持倉比對同一把尺);ym 解不出 → `contract` null → 零標記。 */
  const fills = useMemo(
    () => (anchorDate === null ? EMPTY_FILLS : alldayFillPoints(orders, contract, anchorDate)),
    [orders, contract, anchorDate],
  );
  /** slice 尾往前**第一個索引可解**的 bar 的軸索引(= 舊 `basePoints` 末點的定義)。
   *
   *  不是「最後一根 bar」:尾巴若是死區分鐘 / 日 K 時戳,那根本來就不進圖,拿它當
   *  「資料走到哪」會讓時鐘落後守衛比對到一個畫面上不存在的點。 */
  const tailIndex = useMemo<number | null>(() => {
    for (let i = slice.length - 1; i >= 0; i--) {
      const index = alldayIndexOfStamp(slice[i]!.t);
      if (index !== null) return index;
    }
    return null;
  }, [slice]);

  // live 點吃牆上時鐘 → **刻意不進 useMemo**(memo 的 deps 表達不了「現在幾點」;
  // 重算成本是一次 Date 運算)。WS 每則推播都會讓本元件 re-render,自然跟著走。
  // 四道 gate 的判準逐字不動(白名單 W-4);同索引覆寫 / 新索引補格的分派下沉到 adapter。
  // gate 5(資料落後時鐘)另帶回落後格數給回補提示用。
  const { liveIndex, lagBehind } = ((): { liveIndex: number | null; lagBehind: number | null } => {
    const none = { liveIndex: null, lagBehind: null };
    const last = slice[slice.length - 1];
    const p = state?.p ?? null;
    if (p === null || last === undefined) return none;
    const live = liveSlotOf(new Date());
    if (live === null) return none; // 死區
    if (live.anchor !== anchorDateOf(last.t)) return none; // 錨定日 gate(§3.2)
    if (tailIndex !== null && tailIndex > live.index) return none; // 時鐘落後資料
    // gate 5:bars 落後**最後成交**超過輪詢節奏 → 當日段回補不完整,不架橋。
    // 成交要與末根同錨定日(SP2):t 停在前一場次 = WS 沒新成交,不是資料落後。
    const trade = state?.t == null || state.date == null ? null : tradeSlotOf(state.date, state.t);
    if (
      tailIndex !== null &&
      trade !== null &&
      trade.anchor === anchorDateOf(last.t) &&
      trade.index - tailIndex > FUT_LIVE_LAG_MAX
    ) {
      return { liveIndex: null, lagBehind: trade.index - tailIndex };
    }
    return { liveIndex: live.index, lagBehind: null };
  })();
  const liveP = state?.p ?? null;

  /** 分時圖的資料模型 = 個股同一份 `StockAccum`(近全軸索引當 key)。
   *
   *  deps 全是純量或 `slice` 的 identity —— live 落點是每 render 現算的兩個數字,
   *  同一分鐘同一價就命中 memo(價變才重折 1140 格)。 */
  const accum = useMemo(
    () =>
      futuresBarsToAccum({
        bars: slice,
        live: liveIndex === null || liveP === null ? null : { index: liveIndex, p: liveP },
        ref: state?.ref ?? null,
        name: state?.name ?? product,
        code: product,
      }),
    [slice, liveIndex, liveP, state?.ref, state?.name, product],
  );

  // ---- 分時圖尺寸(同個股頁:量測 → viewBox 高)---------------------------
  // 量的是「剩下多少」不是「圖表現在多高」→ ref 掛在**恆存 wrapper**(loading /
  // error / data 三態都 mount),且該 wrapper 的高由外層 flex 指派。
  const [sizeRef, size] = useContainerSize<HTMLDivElement>();
  const box = svgBox(size, INTRADAY_VB_W);
  // 主副圖上下相接:總高按 260:70 拆,且用減法讓兩者相加恰等於總高(各自 round 會多 1px)
  const mainH = box.usable
    ? Math.round((box.viewBoxHeight * MAIN_RATIO_NUM) / MAIN_RATIO_DEN)
    : undefined;
  const subH = box.usable ? box.viewBoxHeight - (mainH ?? 0) : undefined;

  // ---- 分 K / 日 K -------------------------------------------------------
  const minutes = futMinutesOf(mode);
  const candleBars = useMemo(() => aggregateBars(bars, minutes), [bars, minutes]);

  // a11y 批:模式列是單選 —— 15 顆 `aria-pressed` button 讓 AT 聽成 15 個互不相干的開關、
  // 鍵盤要按 15 次 Tab 才穿得過。改 RadioPills 後一個 tab stop + 方向鍵切換(class 逐字沿用)。
  const modeRow = (
    <RadioPills<FutChartMode>
      ariaLabel="圖表模式"
      className="flex flex-wrap items-center gap-1"
      value={mode}
      onChange={selectMode}
      items={FUT_CHART_MODES.map(([id, label]) => ({ value: id, label }))}
      pillClass={(_item, checked) =>
        cn(
          "rounded border px-2 py-0.5 text-xs",
          checked ? "border-accent text-accent" : "border-line text-ink-dim hover:text-ink",
        )
      }
    />
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
    // 空態依 `meta.status` 分三句話(N104)。改動前只有最後那一句,而 `unavailable`
    // 同時涵蓋「TC4 忙(等下一輪輪詢就有)」「TC4 斷線(要去看連線)」「真的沒有這段
    // K 線」—— 三件事的處置完全不同。舊 payload(無 status)逐字退回原句(design §1.4 D8)。
    if (data.meta.source === "unavailable") {
      return (
        <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-line bg-surface">
          <p className="text-sm text-ink-muted">{EMPTY_TEXT[data.meta.status ?? "ok"]}</p>
        </div>
      );
    }
    if (mode === "intraday") {
      // 空序列的「無分時資料」與外框(figure)都由 core 承接 —— 換元件不換語彙
      return (
        <IntradayChartCore
          accum={accum}
          toggles={toggles}
          onToggle={set}
          variant="page"
          mode="futures"
          mainHeight={mainH}
          subHeight={subH}
          xWindow={ALLDAY_WINDOW}
          hourTicks={ALLDAY_HOUR_TICKS}
          timeText={alldayHhmmOf}
          hlines={hlines}
          fills={fills}
          // 疊線走**注入**管道(同 index 態):core 不打 `/api/stock/overlay`(那支吃股號)。
          // `overlaySupported` 用預設 true —— 期貨有日 K 資料源,「這一天算不出來」由
          // 全 null 的 overlay 表達(反灰 + 預設 tooltip「無日線資料」),兩件事不合成一個旗標。
          overlay={overlay}
          overlayError={dayQ.isError}
          ariaLabel="期貨近全時段分時走勢"
        />
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
      {/* 提示與模式列同一行(review ST4):放成 sibling 會在出現 / 消失時把圖高抽掉一行,回補期間圖表跳動 */}
      <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1">
        {modeRow}
        {mode === "intraday" && lagBehind !== null ? (
          // gate 5 擋下 live 點時把原因講出來:圖停在資料尾不是「沒在動」,是當日段還沒補齊。
          // 「根」= 近全軸缺的 1K 根數(跨死區不等於牆鐘分鐘)
          <span className="text-xs text-ink-muted">分時資料落後 {lagBehind} 根(TC4 回補中)</span>
        ) : null}
      </div>
      {/* 量測 wrapper **恆存**(loading / error / data 三態都在內):只包 data 分支的話
          冷載入量到 0×0,而 `useContainerSize` 的 callback ref 不會為此再跑一次 */}
      <div ref={sizeRef} className="flex min-h-0 flex-1 flex-col">
        {body()}
      </div>
    </div>
  );
}

export default FuturesChart;
