/** 台股綜合頁的薄容器 —— **一頁總覽兩欄**:左欄基差列 + 兩張並排指數圖 + 家數帶 +
 *  騰落線,右欄漲跌停列表**恆掛**。
 *
 *  單圖的狀態邏輯與版面全在 `MarketPane`(本檔只決定「哪個 pane 用哪組 localStorage key、
 *  預設看哪個標的」)—— 兩張圖除了 key 組與預設標的以外完全同構,邏輯留在這裡就會變成
 *  「同一段程式碼寫兩遍」。
 *
 *  **沒有 subtab**(2026-08-16 退役,相關係數升為頂層 tab):改版前下半部是一列 subtab
 *  + 一次只掛載一個 panel,現在漲跌停列表與左欄同屏常駐,省輪詢的責任整條落到
 *  `active` —— 本頁的 DOM 由 App 以 `hidden` 保留,主 tab 切離時 `active` 轉 false,
 *  列表輪詢與兩張圖的分 K 一起停(原「非 active subtab = unmount」的等價轉移)。 */
import { AdvanceDeclineChart } from "@/components/index/AdvanceDeclineChart";
import { BreadthBand } from "@/components/index/BreadthBand";
import { LimitListSection } from "@/components/index/LimitListSection";
import { MarketPane, type PaneFutState, type PaneStores } from "@/components/index/MarketPane";
import { useChartToggles } from "@/hooks/useChartToggles";
import type { IndexSeries, TxfQuote } from "@/hooks/useIndexStream";
import {
  INDEX_OVERLAY_STORE,
  MARKET2_FUT_STORE,
  MARKET2_KEY_STORE,
  MARKET2_MODE_STORE,
  MARKET_FUT_STORE,
  MARKET_KEY_STORE,
  MARKET_MODE_STORE,
} from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { BreadthState } from "@/types";

/** 左圖沿用改版前那四支 key —— 舊使用者的標的 / 週期 / 期指商品 / 重疊開關零丟失。 */
const LEFT_STORES: PaneStores = {
  key: MARKET_KEY_STORE,
  mode: MARKET_MODE_STORE,
  fut: MARKET_FUT_STORE,
  overlay: INDEX_OVERLAY_STORE,
};
/** 右圖三支新 key,**沒有 overlay** —— 重疊圖畫的固定是加權 vs 櫃買,右圖也開會出現
 *  兩張一模一樣的圖(`MarketPane` 靠 `stores.overlay === undefined` 收掉那顆鈕)。 */
const RIGHT_STORES: PaneStores = {
  key: MARKET2_KEY_STORE,
  mode: MARKET2_MODE_STORE,
  fut: MARKET2_FUT_STORE,
};

/** `MarketPane` 內有同名的一份。刻意複製而不抽 `@/lib/format`:MarketChart / CandleChart
 *  本來就各留一份,這是既有慣例。 */
function fmt(millipts: number): string {
  const v = millipts / 1000;
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

/** 台指期 vs 加權的基差。**不在 pane 內**:它與 pane 選什麼標的無關,放進去等於兩張圖
 *  各印一份相同數字。計算與呈現與改版前逐字相同(正紅 / 負綠 / 缺值「價差 -」)。 */
function BasisRow({ txf, twse }: { txf: TxfQuote | null; twse: IndexSeries | null }) {
  const basis = txf !== null && twse?.p != null ? (txf.p - twse.p) / 1000 : null;
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span data-testid="basis-row" className="font-mono text-xs text-ink-dim">
        台指期 <span className="text-ink">{txf !== null ? fmt(txf.p) : "-"}</span>{" "}
        <span
          className={cn(
            basis !== null && basis > 0
              ? "text-bull"
              : basis !== null && basis < 0
                ? "text-bear"
                : "text-ink-dim",
          )}
        >
          {basis !== null ? `價差 ${basis > 0 ? "+" : ""}${basis.toFixed(2)}` : "價差 -"}
        </span>
        {txf?.time ? <span className="ml-2 text-ink-dim">至 {txf.time.slice(0, 5)}</span> : null}
      </span>
    </div>
  );
}

interface Props {
  twse: IndexSeries | null;
  otc: IndexSeries | null;
  txf: TxfQuote | null;
  /** 期貨三檔即時狀態(App 層 `useFuturesStream` 下傳;review P1-6)。 */
  futures?: Record<string, PaneFutState> | null;
  /** 全市場家數 / 騰落序列(App 層 `useBreadth` 下傳;design R8 —— 本頁維持純展示,
   *  既有測試不必 stub WS)。 */
  breadth?: BreadthState | null;
  /** 漲跌停列表點列 → 開個股(期)頁(R3 SC-5)。狀態(主檔 / 當前 tab)在 App 層,
   *  本頁只把回呼往下傳 —— 頁內自己記一份主檔會與右欄 / 個股頁分岔。 */
  onOpenStock?: (code: string) => void;
  /** 使用者是否正看著本 tab(App 的 `tab === "index"`)。本頁的 DOM 由 App 以 `hidden`
   *  保留 → 頁內所有背景輪詢都要靠這道 gate 停(review FE-2;FuturesPage 同慣例):
   *  漲跌停列表,以及**兩張指數圖的分 K**
   *  —— 最後那條路在當日段每次都真走 TC4 SubHistory,與 REALTIME 搶同一把
   *  `api.lock`(review round-2 XR-4)。未給時預設 true(既有呼叫路徑不靜默停更)。 */
  active?: boolean;
}

export function IndexPage({
  twse,
  otc,
  txf,
  futures,
  breadth = null,
  onOpenStock,
  active = true,
}: Props) {
  // 上提到容器層:兩 pane 共用同一份 bb 開關(與改版前的全域單開關行為一致),
  // 各 pane 自己呼叫會變成兩份獨立狀態寫同一支 localStorage key。
  const { toggles, set } = useChartToggles();

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
      <BasisRow txf={txf} twse={twse} />
      {/* auto-fit + minmax:寬視窗並排,窄視窗自動疊成單欄,不必 JS 判斷斷點 */}
      <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(480px,1fr))]">
        <MarketPane
          paneId="left"
          twse={twse}
          otc={otc}
          futures={futures}
          stores={LEFT_STORES}
          defaultKey="TWSE"
          toggles={toggles}
          onToggle={set}
          active={active}
        />
        <MarketPane
          paneId="right"
          twse={twse}
          otc={otc}
          futures={futures}
          stores={RIGHT_STORES}
          defaultKey="OTC"
          toggles={toggles}
          onToggle={set}
          active={active}
        />
      </div>
      {/* 中段:家數帶 + 其下騰落線(SC-4)。兩者同一個資料源(`breadth`),放同一個
          section 讓「當下十個數字」與「一整天的走向」在版面上是同一塊。 */}
      <section className="flex flex-col gap-2">
        <BreadthBand breadth={breadth} />
        <AdvanceDeclineChart series={breadth?.series ?? []} />
      </section>
      {/* 漲跌停列表恆掛(2026-08-16 subtab 退役),沿用改版前那個外框盒。
          廣度發現 → 深度盯盤的銜接點 —— 家數帶說「今天有幾檔鎖住」,列表說「是哪
          幾檔」,點下去就跳到個股(期)頁看那一檔的五檔與分時。
          `active` 直傳:輪詢的唯一 gate 現在是主 tab,不再經 subtab 條件。 */}
      <section className="rounded-md border border-line bg-surface">
        <LimitListSection onOpenStock={onOpenStock} active={active} />
      </section>
    </div>
  );
}

export default IndexPage;
