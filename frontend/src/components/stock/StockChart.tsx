import { useMemo, useState } from "react";

import { CandleChart } from "@/components/stock/CandleChart";
import { StockIntradayChart } from "@/components/stock/StockIntradayChart";
import { RadioPills } from "@/components/ui/RadioPills";
import { useCapitalFills } from "@/hooks/useCapital";
import { useChartToggles } from "@/hooks/useChartToggles";
import { MINUTE_DAYS, minutesOf, useStockBars, type ChartMode } from "@/hooks/useStockBars";
import { useContainerSize } from "@/hooks/useContainerSize";
import { aggregateBars } from "@/lib/candle";
import { CHART_MODE_KEY } from "@/lib/constants";
import { MAIN_RATIO_DEN, MAIN_RATIO_NUM, svgBox } from "@/lib/chart-frame";
import { fillPoints, stkfutFillKey } from "@/lib/fill-marks";
import { ymdOf } from "@/lib/ladder-lots";
import type { IndexOverlaySeries } from "@/lib/index-overlay-lines";
import type { StockAccum } from "@/lib/stock-accum";
import { readLocal, writeLocal } from "@/lib/storage";
import { cn } from "@/lib/utils";

/** 圖表模式切換容器(SC-6):江波圖 / 1–10 分K / 日K。
 *  江波圖走既有即時 accum;K 線走 /api/stock/bars。2–10 分 K 全由 1 分前端聚合(D-8)。 */

// 初始可視根數(之後由滾輪縮放/拖曳平移控制)。分 K 240 ≈ 一個交易日的 1 分 K 全長 ——
// 切進去先看今天,再往左縮放/平移看更早。可視上限的 ≥2px 保護移交
// candle-viewport 的 MAX_VISIBLE(700 = viewBox 寬 1400 ÷ 2px)。
const DAILY_INIT_BARS = 120;
const MINUTE_INIT_BARS = 240;
/** 兩張圖的 viewBox 寬(固定);高度才是隨可用空間變的那一維(SC-6) */
const INTRADAY_VB_W = 800;
const CANDLE_VB_W = 1400;

const MODE_LABELS: [ChartMode, string][] = [
  ["intraday", "江波圖"],
  ...(Array.from({ length: 10 }, (_, i) => [`m${i + 1}`, `${i + 1}分K`]) as [ChartMode, string][]),
  ["day", "日K"],
];

const VALID_MODE = /^(intraday|day|m([1-9]|10))$/;

function initialMode(): ChartMode {
  const saved = readLocal(CHART_MODE_KEY);
  return saved !== null && VALID_MODE.test(saved) ? (saved as ChartMode) : "intraday";
}

/** 期貨態的模式鈕 tooltip;也是「為什麼按不下去」的唯一說明 */
const FUT_MODE_HINT = "期貨合約本輪僅提供分時";

export function StockChart({
  accum,
  code,
  contract = null,
  indexSeries = null,
}: {
  accum: StockAccum;
  /** 恆為**股號**(期貨態也一樣)—— K 線 endpoint 與 CandleChart 的 key 都吃它 */
  code: string;
  /** 選中的個股期合約;null = 現貨態(既有行為逐項不變) */
  contract?: { prod: string; ym: string } | null;
  /** 加權 / 櫃買即時序列(F1);分時態往下傳,K 線態不吃 */
  indexSeries?: IndexOverlaySeries | null;
}) {
  const [mode, setMode] = useState<ChartMode>(initialMode);
  const isFut = contract !== null;
  // 期貨態一發都不打(R5):endpoint 查的是現貨股號,K 線與畫面上的合約無關。
  // 收斂雖然改成同一個 render pass 內完成,但這一行在收斂分支**之前**執行(hook 呼叫
  // 順序不可調),「殘留日K + 切進合約」的第一次求值時 mode 仍是 day ——
  // 外部否決(第四參數)仍是唯一保證,不能改成靠 mode 自己擋。
  const { data, isPending, isError, error } = useStockBars(code, mode, MINUTE_DAYS, !isFut);
  // bb 的狀態持有者(R16/R21):CandleChart 不自呼叫這個 hook,否則按鈕與圖各管各的
  const { toggles, set } = useChartToggles();

  // 當日成交點(R2 SC-7)。比對鍵分兩態:
  //   現貨 = 股號 + `excludeUnit="股"`(與現股梯同口徑 AD-3,張梯混零股量級差千倍);
  //   個股期 = **選定契約**的期交所契約碼(群益回報的期貨單 `stock_no` 放的就是它),
  //   不排除單位「口」。契約 ym 非法時 `stkfutFillKey` 回 null → `fillPoints` 走 guard
  //   回零筆(圖比成交點重要,不白屏)。
  // 判準用 `contract !== null` 而不是 `isFut`:兩者等值,但前者讓 TS 直接窄化出 `prod`/`ym`。
  // deps **不放 `contract` 物件**:它是 StockPage 每 render 現造的字面值,放進去等於每輪重算;
  // `key` 是字串,值一樣就不重算。`today` 每 render 現算,跨午夜時字串一變自然失效(AD-9)。
  const capFills = useCapitalFills().data?.fills;
  const today = ymdOf(new Date());
  const key = contract !== null ? stkfutFillKey(contract.prod, contract.ym) : code;
  const fills = useMemo(
    () => fillPoints(capFills, key, today, isFut ? undefined : "股"),
    [capFills, key, today, isFut],
  );

  // 進期貨態前的現貨模式;null = 沒有待還原的偏好(code review A6)。
  //
  // **prod 沒有讀者,刻意保留**(N121,2026-08-24 覆查):`StockPage` 的主圖掛在
  // `{accum ? …}` 底下,而 `useStockStream` 換合約時第一件事就是 `setAccum(null)`
  // → StockChart **卸載重掛**,本 state 歸零,`initialMode()` 直接從 localStorage 讀回
  // 使用者的現貨偏好(下面的收斂刻意不寫 localStorage,A6 因此在 prod 由它兌現)。
  // 唯一走得到本分支的是**同一個元件實例**內 `contract` 由非 null 變 null 的路徑 =
  // `StockChart.futconverge.test.tsx` / `StockChart.test.tsx` A6 節。
  // 判定:**不刪**。它是「圖表哪天脫離 accum gate(常駐掛載)」時唯一還撐得住 A6 的
  // 東西,而那個前提由 `StockPage.test.tsx` 的「主圖 accum gate(N121 前提)」釘住 ——
  // 那條紅了就回來重新決定要刪它還是真驗 A6。
  const [spotMode, setSpotMode] = useState<ChartMode | null>(null);

  // 期貨態只提供江波圖(D10)。模式是**持久化狀態** —— 使用者上次停在日 K 時,切進
  // 合約的第一次 render 就已經是 day,不收斂會掛著一張與合約無關的現貨 K 線。
  // **不寫回 localStorage**:那是使用者對現貨的偏好,切回現貨時要原樣回來 —— 而「原樣
  // 回來」需要 `spotMode` 記著(code review A6):只靠 localStorage 不夠,收斂發生在同一個
  // session 內、`mode` state 已經被改成 intraday,切回現貨時沒有人會把它讀回來,使用者
  // 看到的是「進了一次合約,我的日 K 偏好就沒了」。
  //
  // 收斂用**render 期間調整 state**(官方 adjust-state-on-prop-change;repo 樣板
  // `WatchlistManagerDialog` 的 prevOpen),不用 effect:effect 要下一個 render 才生效,
  // 回現貨時 `isFut` 已 false 而 `mode` 還停在 intraday → 會先 commit 一次「現貨態的
  // 分時圖」再換成還原後的 K 線(閃一格)。React 在本函式 return 後、渲染子元件前就會
  // 用新 state 重跑一次,所以那一格根本不會 commit(StockChart.futconverge.test.tsx 釘住)。
  // 兩個分支各自收斂,不需要顯式的 prevIsFut:期貨態存偏好並收斂到 intraday(也涵蓋原
  // effect deps 含 mode 的「期貨態內 mode 漂移」保險);回現貨還原一次並清掉待還原標記,
  // 之後手動改模式不會被舊值再蓋一次。
  if (isFut) {
    if (mode !== "intraday") {
      setSpotMode(mode);
      setMode("intraday");
    }
  } else if (spotMode !== null) {
    setSpotMode(null);
    setMode(spotMode);
  }

  function selectMode(next: ChartMode): void {
    setMode(next);
    writeLocal(CHART_MODE_KEY, next);
  }

  // n=1 時 aggregateBars 原樣回傳,不必特判
  const bars = useMemo(() => aggregateBars(data?.bars ?? [], minutesOf(mode)), [data, mode]);

  const isMinute = mode !== "intraday" && mode !== "day";
  // 畫面分支直接認 isFut,不只看 mode:收斂雖已在同一個 render pass 完成(理論上
  // 走到這裡 mode 必為 intraday),但這是防禦 —— 收斂分支若被改壞,認 mode 會讓期貨態
  // 掛出一張與合約無關的現貨 K 線 / 閃一格「載入中…」(query 被 enabled:false 擋住,
  // isPending 恆真),而那是無錯誤訊號的假資料。
  const showIntraday = isFut || mode === "intraday";

  // 空 bars 且非 ok 時的替代句(null = 照舊掛 CandleChart)。bars 非空一律不分態:
  // 有資料就照常畫,某段降級不在本輪 scope。
  const emptyNote =
    data !== undefined && data.bars.length === 0
      ? data.status === "timeout"
        ? { text: "等待 TC4 回應中…(自動重試)", tone: "text-ink-muted" }
        : data.status === "disconnected"
          ? { text: "TC4 連線中斷,K 線暫不可用(自動重試中)", tone: "text-bear" }
          : null
      : null;

  // 量測 wrapper 的可用空間 → 圖表 viewBox 高度(round3 SC-6)。
  // 量的是「剩下多少」不是「圖表現在多高」—— 被量元素的高度必須由外層 flex 指派
  // (useContainerSize 的呼叫端契約),否則會形成「圖表高 → 量測值 → 圖表高」的迴圈。
  const [sizeRef, size] = useContainerSize<HTMLDivElement>();
  const box = svgBox(size, showIntraday ? INTRADAY_VB_W : CANDLE_VB_W);
  // 江波圖兩張 svg 上下相接:總 viewBox 高度按現行 260:70 拆分,且用減法讓兩者相加
  // 恰等於總高(各自 round 會多出 1px 誤差)。
  const mainH = box.usable
    ? Math.round((box.viewBoxHeight * MAIN_RATIO_NUM) / MAIN_RATIO_DEN)
    : undefined;
  const subH = box.usable ? box.viewBoxHeight - (mainH ?? 0) : undefined;

  return (
    // flex-1 min-h-0:圖表吃掉下半列以外的剩餘高度(SC-6)。原本是 shrink-0 的
    // 「寬度決定高度」固定比例,不隨剩餘空間縮,那正是 <main> 會頂出捲軸的原因。
    <div className="flex min-h-0 flex-1 flex-col">
      {/* a11y 批:模式列是單選 —— 12 顆 `aria-pressed` button 讓 AT 聽成 12 個互不相干的
          開關、鍵盤要按 12 次 Tab 才穿得過。改 RadioPills 後一個 tab stop + 方向鍵切換。
          期貨態的 `disabled` + tooltip 語意逐字保留(title 掛 label,W8)。 */}
      <RadioPills<ChartMode>
        ariaLabel="圖表模式"
        className="mb-1 flex flex-wrap items-center gap-1"
        value={mode}
        onChange={selectMode}
        items={MODE_LABELS.map(([id, label]) => {
          const blocked = isFut && id !== "intraday";
          return { value: id, label, disabled: blocked, title: blocked ? FUT_MODE_HINT : undefined };
        })}
        // 停用態這裡只給 `opacity-40`:游標(`cursor-not-allowed`)由 `RadioPills` 統一補。
        // 那是 R2 a11y 批相對「視覺零變」的一個**已接受偏差**(N012,2026-08-24 覆查:
        // 原 `<button disabled>` 沒有 not-allowed 游標)—— 判定保留,因為停用態的正確
        // 游標本來就該有,而且兩處各寫一份的失效樣態是「只有其中一組 pill 的游標漂掉」。
        pillClass={(item, checked) =>
          cn(
            "rounded border px-2 py-0.5 text-xs",
            checked ? "border-accent text-accent" : "border-line text-ink-dim hover:text-ink",
            item.disabled && "opacity-40",
          )
        }
      />
      {/* 量測用的恆存 wrapper:loading / error / data 三態都掛在它底下(useContainerSize
          的呼叫端契約 —— ref 只掛 data 分支的話,冷載入會量到 0×0 而 hook 不再重跑)。 */}
      <div ref={sizeRef} className="flex min-h-0 flex-1 flex-col">
      {showIntraday ? (
        <StockIntradayChart
          accum={accum}
          mainHeight={mainH}
          subHeight={subH}
          stkfut={isFut}
          fills={fills}
          indexSeries={indexSeries}
        />
      ) : isPending ? (
        <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-line bg-surface">
          <p className="text-sm text-ink-muted">載入中…</p>
        </div>
      ) : isError ? (
        // 失敗態必須與「真的沒資料」分得開:2026-07-29 舊 build 佔 port 讓 endpoint 回 404,
        // 當時兩者共用「無 K 線資料」一句 → 被誤讀成「這檔沒 K 線」(SC-3)。
        // 錯誤碼取值鏈見 useStockBars.ts:35-44(detail.error 優先 → HTTP_<status>)。
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 rounded-md border border-line bg-surface">
          <p className="text-sm text-bear">K 線載入失敗</p>
          <p className="font-mono text-xs text-ink-dim">{(error as Error | null)?.message ?? ""}</p>
        </div>
      ) : emptyNote !== null ? (
        // 空 bars 的三種來源不再共用「無 K 線資料」一句肯定語氣:timeout =「還在等」
        // (TC4 協定下「慢」與「查無」不可分,故用進行式不下結論)、disconnected =
        // 「斷線」。ok + 空才是「真的沒有」,交給 CandleChart 內的既有句子。
        <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-line bg-surface">
          <p className={cn("text-sm", emptyNote.tone)}>{emptyNote.text}</p>
        </div>
      ) : (
        // key:換股或換模式時強制重掛,viewport 回到初始式。換模式會讓 total 由
        // ~5,900 變 ~590,沿用舊 index 沒有意義(onTotalChange 只處理同序列的延伸)。
        <CandleChart
          key={`${code}-${mode}`}
          bars={bars}
          initBars={isMinute ? MINUTE_INIT_BARS : DAILY_INIT_BARS}
          showBb={toggles.bb}
          onToggleBb={(v) => set("bb", v)}
          height={box.usable ? box.viewBoxHeight : undefined}
        />
      )}
      </div>
    </div>
  );
}
