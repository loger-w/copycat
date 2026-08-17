import { useMemo } from "react";

import { CandleChart } from "@/components/stock/CandleChart";
import { IntradayChartCore } from "@/components/stock/StockIntradayChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import { useIndexOverlay } from "@/hooks/useIndexOverlay";
import { useMarketBars } from "@/hooks/useMarketBars";
import type { IndexSeries } from "@/hooks/useIndexStream";
import { aggregateBars } from "@/lib/candle";
import { indexSeriesToAccum } from "@/lib/index-accum-adapter";
import { type MarketKey, type MarketMode, marketMinutesOf } from "@/lib/timeframe";

/** 資料源代碼 → 畫面文字。**必須逐一列舉**:未知碼原樣顯示(安全漂移),
 *  不要 fallback 成「TC4」之類的漂亮字 —— 那等於替沒把握的來源背書。 */
const SOURCE_TEXT: Record<string, string> = {
  tc4_dk: "達錢 4 日K",
  tc4_1k: "達錢 4 1分K",
  tc4_dk_1k_agg: "達錢 4 1分K 聚合(日K 無資料)",
  mis_poll_synth: "本機合成(MIS 5秒取樣)",
  unavailable: "取不到資料",
  none: "無資料源",
};

interface Props {
  /** **不能叫 `key`** —— React 會把它抽走當 reconciliation key,元件永遠收到 undefined
   *  且 TS 不報錯(review P0-3)。 */
  marketKey: MarketKey;
  mode: MarketMode;
  name: string;
  /** 分時模式的資料源(加權 / 櫃買);期指不支援分時,傳 null 即可。 */
  series: IndexSeries | null;
  /** 整包下傳而不是拆成 `showBb`/`onToggleBb`:分時態接下來要用到 vwap/cdp/ma 三個鍵,
   *  逐鍵開 props 等於每加一條疊線就改一次 caller 簽名。單一 caller(MarketPane)。 */
  toggles: ChartToggles;
  onToggle: (key: keyof ChartToggles, value: boolean) => void;
  /** 使用者是否正看著本頁 tab(App 的 `tab === "index"`)。分 K 的背景輪詢要靠這道
   *  gate 停(review round-2 XR-4);未給時預設 true。 */
  active?: boolean;
  /** 圖高,單位是 **viewBox 單位**不是 px(§4.1 CS-1 口徑):caller(`MarketPane`)
   *  已經扣掉 figure / K 線頂列的 chrome,並用「viewBox 寬 ÷ 容器寬」把 px 反解成
   *  viewBox 單位。**K 線態專用,intraday 不讀**(分時走 1:1 的 `intradayBox`)——
   *  同一個 prop 不帶兩種單位。**刻意無預設值**:未給 → 直接透傳 undefined 讓
   *  `CandleChart` 用它自己的 578,在這裡給預設就等於替它決定了它的高。 */
  height?: number;
  /** 分時圖的 viewBox 尺寸,單位是 **px(1:1)**,由 `paneIntradayBox` 量出來。
   *  **分時態限定**;未給(jsdom / 量不到)→ core 走它自己的 800×260 預設。
   *  1:1 之後 svg 的縮放比恆 1,字級與 pane 寬無關 —— 舊的 `unitScale` 補償隨自繪版
   *  一起退場(K 線態本來就不吃它)。 */
  intradayBox?: { width: number; height: number };
}

/** 大盤主圖:分時走勢 or 蠟燭圖 + 一行來源/涵蓋期間 meta(SC-4/5/6)。 */
export function MarketChart({
  marketKey,
  mode,
  name,
  series,
  toggles,
  onToggle,
  active = true,
  height,
  intradayBox,
}: Props) {
  const { data, isPending, isError, error } = useMarketBars(marketKey, mode, active);
  const minutes = marketMinutesOf(mode);
  const bars = useMemo(
    () => aggregateBars(data?.bars ?? [], minutes),
    [data?.bars, minutes],
  );
  // **無條件呼叫**(rules of hooks):閘全收在 enabled 裡 —— 只有加權分時、且至少一種
  // 疊線開著才打端點。櫃買無日 K 來源(已拍板跳過),K 線模式不畫疊線。
  const overlayGate = mode === "intraday" && marketKey === "TWSE" && (toggles.cdp || toggles.ma);
  const overlayQ = useIndexOverlay(overlayGate);
  // 指數序列 → core 吃的 `StockAccum`。**hook 不可條件化**(本 repo 沒裝 react-hooks
  // lint,漏了不會被擋),所以擺在 `mode === "intraday"` 早退之前;K 線態 series 恆 null
  // → 這裡是常數 null,不折。
  // deps 帶 `series` identity:`useIndexStream` 每個 tick 給新物件,271 格 O(n) 折一次
  // 與群組卡片同量級(KR-2)。
  const accum = useMemo(
    () => (series === null ? null : indexSeriesToAccum(series, `IX:${marketKey}`, name)),
    [series, marketKey, name],
  );

  if (mode === "intraday") {
    if (accum === null) {
      return <p className="py-10 text-center text-sm text-ink-muted">等待指數資料…</p>;
    }
    return (
      // 個股頁 / 群組圖牆同一份 core(mode="index":副圖 / VP / 成交點 / 說明列全關,
      // readout 三欄,右緣文字走 `fmt` 不 snap tick)。疊線由這裡注入 ——
      // `IX:TWSE` 不是股號,core 內建的 `/api/stock/overlay` 那條路打不得。
      <IntradayChartCore
        accum={accum}
        toggles={toggles}
        onToggle={onToggle}
        variant="page"
        mode="index"
        width={intradayBox?.width}
        mainHeight={intradayBox?.height}
        overlay={overlayQ.data ?? null}
        // **error 判定必須跟著 enabled 閘走**:TanStack 在 `enabled` 轉 false 時
        // 既不清 status 也不跑 refetchInterval —— 直接吃 `isError` 的話,「503 一次
        // + 使用者把 CDP/MA 都關掉」會讓兩顆鈕永遠 disabled(自己再也開不回來,
        // 只有重新整理解得開)。閘關著時本來就沒在請求,自然也沒有失敗可言。
        overlayError={overlayGate && overlayQ.isError}
        // 櫃買沒有日 K 來源(已拍板跳過)→ CDP/MA 恆反灰,文案講得出為什麼
        overlaySupported={marketKey === "TWSE"}
        overlayOffTitle={marketKey === "TWSE" ? "無日線資料" : "櫃買無日 K 資料源"}
        // 兩個 pane 可能同時選加權 —— aria-label 帶標的名才指認得出是哪一張
        ariaLabel={`${name}分時走勢`}
      />
    );
  }

  if (data?.meta.refusal === "NO_HISTORICAL_SOURCE") {
    return (
      <div className="flex flex-1 items-center justify-center py-10">
        <p className="text-center text-sm text-ink-muted">
          達錢 4 未提供櫃買指數,無歷史 K 線資料源
        </p>
      </div>
    );
  }
  if (isError) {
    return (
      <p className="py-10 text-center text-sm text-bear">
        K 線載入失敗:{(error as Error | undefined)?.message ?? "UNKNOWN"}
      </p>
    );
  }
  if (isPending) {
    return <p className="py-10 text-center text-sm text-ink-muted">載入 K 線…</p>;
  }

  const meta = data.meta;
  const coverage =
    meta.coverage_from !== null && meta.coverage_to !== null
      ? `${meta.coverage_from} ~ ${meta.coverage_to}`
      : "無資料";
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <CandleChart
        key={`${marketKey}-${mode}`}
        bars={bars}
        initBars={minutes > 1 ? 240 : 120}
        showBb={toggles.bb}
        onToggleBb={(v) => onToggle("bb", v)}
        showVolume={meta.volume}
        height={height}
      />
      {/* `h-4 truncate` 是**契約不是裝飾**:`PANE_FRAMES.candle` 的 chromeY 把這一列
          算成固定 20px(h-4 16 + mt-1 4)。窄 pane 下最長的來源字串超過欄寬,不限高就
          折成兩行 → chromeY 少算一行 → svg 溢出 figure(WL-2)。 */}
      <p data-testid="market-meta" className="mt-1 h-4 truncate font-mono text-xs text-ink-dim">
        {SOURCE_TEXT[meta.source] ?? meta.source} · {coverage}
        {meta.synth_since !== null ? ` · 自 ${meta.synth_since} 起` : ""}
        {meta.partial_last ? " · 最後一根未收盤" : ""}
      </p>
    </div>
  );
}
