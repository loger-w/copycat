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
    <div className="flex shrink-0 flex-wrap items-center gap-3">
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
    // root 是 container 但**自己不捲**:整頁唯一的垂直捲軸落在主 grid 上(§4.1)。
    // 兩處都能捲的話,極矮視窗會出現兩層捲軸、且 SC-3 量到的「主 grid 沒捲」是假的。
    <div className="@container flex min-h-0 flex-1 flex-col">
      {/* 1050px 是**容器寬**不是視窗寬(容器 = 視窗 − 349:右欄 rail 288 + pl-3 12 +
          border 1 + 外層 px-4 32 + gap-4 16)。窄於此退回單欄堆疊 = 改版前的整頁捲
          行為(SC-7);兩欄態不覆寫 overflow —— 正常尺寸內容恰填滿不出捲軸,極矮
          視窗時這道 overflow 就是逃生口(§7 edge 2)。

          **單欄態是 flex-col 不是 grid-cols-1**(amendment r3):grid 的兩條 auto 列會把
          自由空間**等分**給左右欄,列高與內容完全無關 —— 左欄內容再多也只拿到一半高、
          溢出的部分由 overflow visible 直接壓在下一列上,而主 grid 的 scrollHeight 恆
          等於 clientHeight,這道逃生口永遠不啟動(截圖 SC-7 1280 實測 642/642)。
          flex-col 的列高由內容決定,溢出才真的捲得起來。 */}
      <div
        data-testid="index-main-grid"
        className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto @[1050px]:grid @[1050px]:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]"
      >
        {/* 左欄自己也是 container:雙圖的 640px 斷點量的是**左欄寬**,掛在 root 上量到的
            會是整頁寬(右欄佔掉的 2fr 也算進去)→ 兩張圖在真正塞不下時仍硬並排。
            `min-h-0` **只在兩欄態**:單欄態下它會讓左欄再也撐不高主 grid(同上)。

            **四個 `--idx-*` 變數就是「兩欄態 3:2」的發點**:雙圖 grid / 家數帶 section /
            騰落線 wrapper 的最近 `@container` 祖先正是左欄自己(見上一句),兩欄態左欄
            只有 630–930px → 直接寫在它們身上的 `@[1050px]:flex-[3]` 永遠不成立
            (frontend-conventions「巢狀 container」陷阱,與 pane 層 min-h-0 同一個教訓)。
            量得到 root 寬的只有左欄本身,所以由左欄設變數、子節點讀變數;**每個變數的
            預設值 = 改動前那個 class 的展開值**,單欄態逐值不變由建構保證(W-4)。
            比例 3:2 = 兩張指數圖比一條騰落線資訊密度高;1080p 左欄約 900px 時騰落線
            約 270px(現 96px 的 2.8 倍),仍滿足 SC-6「≥ 0.6 × figure 高」。 */}
        <div className="@container flex flex-col gap-3 @[1050px]:min-h-0 @[1050px]:[--idx-chart-flex:3_1_0%] @[1050px]:[--idx-adl-flex:2_1_0%] @[1050px]:[--idx-adl-wrap-flex:1_1_0%] @[1050px]:[--idx-adl-min:10rem]">
          <BasisRow txf={txf} twse={twse} />
          {/* 顯式斷點取代舊 auto-fit minmax(480px):auto-fit 量的是這個 grid 自己的寬,
              與左欄 container 同寬故語意等價,但斷點值得寫在看得見的地方(W-12)。
              640 而非 700:1440×900 兩欄態左欄 655px 也要並排,否則兩圖直排 + 捲動。

              `[flex:var(--idx-chart-flex,1_1_0%)]` 取代原本的 `flex-1`:**預設值就是
              `flex-1` 的展開值**,單欄態(左欄沒設變數)逐值不變;兩欄態左欄把它設成
              `3 1 0%`,與家數帶 section 的 `2 1 0%` 湊成 3:2。不寫成 `@[1050px]:flex-[3]`
              的理由見左欄那段註解(最近 container 是左欄,那個變體永不成立)。
              **不能同時留獨立的 `flex-1` token**:兩支 flex utility 誰蓋誰由 Tailwind 產出
              順序決定,留著就有一半機率把 shorthand 蓋掉、3:2 靜默失效。

              `min-h-80` 而非 `min-h-0`(amendment r3):min-h-0 的軌可以被壓到低於內容高,
              圖卡溢出壓在家數帶上;20rem 地板 = 標的列 28 + 週期列折 2 行 56 + gap 24 +
              figure 192,到地板後左欄總高超過主 grid → 逃生口才接得住。 */}
          <div className="grid grid-cols-1 gap-3 min-h-80 [flex:var(--idx-chart-flex,1_1_0%)] @[640px]:grid-cols-2">
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
              section 讓「當下十個數字」與「一整天的走向」在版面上是同一塊。

              `[flex:var(--idx-adl-flex,0_0_auto)]` 取代原本的 `shrink-0`:**預設值 `0 0 auto`
              就是 `shrink-0` 的展開值**,單欄態逐值不變(高度仍由內容決定 = 家數帶 + 固定
              96px 騰落線)。兩欄態左欄把它設成 `2 1 0%`,這塊改吃「左欄剩餘高的 2/5」,
              騰落線才不再被鎖在 96px。
              `min-h-0` 無條件加:兩欄態要讓 basis 0% 的軌真的縮得下去(可縮鏈少一段就
              退回 min-content 鎖死);單欄態 flex 不縮,min-height 不作用 → 安全。 */}
          <section className="flex min-h-0 flex-col gap-2 [flex:var(--idx-adl-flex,0_0_auto)]">
            <BreadthBand breadth={breadth} />
            <AdvanceDeclineChart series={breadth?.series ?? []} />
          </section>
        </div>
        {/* 右欄漲跌停列表恆掛(2026-08-16 subtab 退役),沿用改版前那個外框盒。
            廣度發現 → 深度盯盤的銜接點 —— 家數帶說「今天有幾檔鎖住」,列表說「是哪
            幾檔」,點下去就跳到個股(期)頁看那一檔的五檔與分時。
            `@[1050px]:min-h-0 flex-col`:兩欄態整高交給列表自己內捲(表頭 sticky),列表
            長度不再把左欄推出視窗;單欄態(堆疊)不可縮 —— 那時右欄在左欄下面,壓成
            0 高等於列表消失,舊行為是整頁捲著看完。
            `active` 直傳:輪詢的唯一 gate 是主 tab,不再經 subtab 條件。 */}
        <div className="flex flex-col rounded-md border border-line bg-surface @[1050px]:min-h-0">
          <LimitListSection onOpenStock={onOpenStock} active={active} />
        </div>
      </div>
    </div>
  );
}

export default IndexPage;
