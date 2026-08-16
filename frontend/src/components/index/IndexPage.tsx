/** 台股綜合頁的薄容器:常駐區(基差列 + 兩張並排指數圖 + 家數帶 + 騰落線)
 *  + 其下一列 subtab(漲跌停 / 相關係數)。
 *
 *  單圖的狀態邏輯與版面全在 `MarketPane`(本檔只決定「哪個 pane 用哪組 localStorage key、
 *  預設看哪個標的」)—— 兩張圖除了 key 組與預設標的以外完全同構,邏輯留在這裡就會變成
 *  「同一段程式碼寫兩遍」。
 *
 *  **subtab 是掛載閘,不是 `hidden`**(2026-08-14 改版;2026-08-16 收成兩個 panel):
 *  panel 原本各自有收合殼、可同時展開多個,現在是「恆有一顆 active、一次只掛載一個」。
 *  專案慣例是「`hidden` > 條件 render」保留 DOM,**這裡刻意違反** —— 兩個 panel 分別是
 *  全市場 2800 列 / 10 秒、corr + river 兩條 WS,保 DOM 等於兩份成本同時常駐。切走即
 *  unmount,輪詢與連線跟著消費者走(原「收合 = unmount」設計的等價轉移)。 */
import { useState } from "react";

import { CorrSection } from "@/components/corr/CorrSection";
import { AdvanceDeclineChart } from "@/components/index/AdvanceDeclineChart";
import { BreadthBand } from "@/components/index/BreadthBand";
import { LimitListSection } from "@/components/index/LimitListSection";
import { MarketPane, type PaneFutState, type PaneStores } from "@/components/index/MarketPane";
import { useChartToggles } from "@/hooks/useChartToggles";
import type { IndexSeries, TxfQuote } from "@/hooks/useIndexStream";
import {
  INDEX_OVERLAY_STORE,
  INDEX_SUBTAB_KEY,
  MARKET2_FUT_STORE,
  MARKET2_KEY_STORE,
  MARKET2_MODE_STORE,
  MARKET_FUT_STORE,
  MARKET_KEY_STORE,
  MARKET_MODE_STORE,
} from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { BreadthState } from "@/types";

/** subtab 值域與標籤的單一來源。順序 = 畫面順序,也是改版前各區塊的上下順序。 */
const SUBTABS = [
  ["limit", "漲跌停"],
  ["corr", "相關係數"],
] as const;
type SubTab = (typeof SUBTABS)[number][0];

/** 白名單還原:非法值(改版前的 "1"、2026-08-16 刪掉的兩顆 subtab 殘值、亂碼)一律回
 *  預設「漲跌停」—— 這道白名單就是值域縮減時的**唯一**遷移機制,零遷移碼。
 *
 *  **整段包 try/catch**:getItem 在 Safari 私密視窗 / storage 被政策鎖時光是存取就會拋,
 *  而這裡是 `useState` 的 initializer —— 拋出去就是整頁白屏。降回預設 subtab 遠好過白屏
 *  (改版前四個殼與 `useChartToggles` 同慣例)。 */
function initialSubTab(): SubTab {
  try {
    const saved = window.localStorage.getItem(INDEX_SUBTAB_KEY);
    if (SUBTABS.some(([id]) => id === saved)) return saved as SubTab;
  } catch {
    // 讀不到就用預設 —— 偏好還原不了遠好於白屏
  }
  return "limit";
}

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
  const [subtab, setSubtab] = useState<SubTab>(initialSubTab);

  function selectSubtab(next: SubTab): void {
    setSubtab(next);
    try {
      window.localStorage.setItem(INDEX_SUBTAB_KEY, next);
    } catch {
      // 存不進去就算了 —— 偏好不落檔遠好於畫面崩掉
    }
  }

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
      {/* 下半部:一列 subtab + 當前 panel,共用**一個**外框盒(AD-4)——
          兩個 panel 是同一個問題的兩種切面(廣度發現 → 深度盯盤),各自一個框
          會讓它們看起來像兩個彼此無關的區塊。 */}
      <section className="rounded-md border border-line bg-surface">
        {/* aria-label 必帶:全站已有「主要分頁」「交易面板分頁」兩個具名 tablist,
            無名 tablist 會讓全域 `getAllByRole("tab")` 撞名(App.test.tsx 的教訓)。
            造型與 role/aria 沿 `RightRail.tsx` 的右欄分頁樣板 —— repo 內唯一既例。 */}
        <div
          data-testid="index-subtabs"
          role="tablist"
          aria-label="台股綜合分頁"
          className="flex items-center gap-1 border-b border-line px-2 py-1.5"
        >
          {SUBTABS.map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={subtab === id}
              onClick={() => selectSubtab(id)}
              className={cn(
                "rounded px-3 py-1 text-sm",
                subtab === id ? "bg-bg-deep text-ink" : "text-ink-dim hover:text-ink",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        {/* 廣度發現 → 深度盯盤的銜接點:家數帶說「今天有幾檔鎖住」,列表說「是哪幾檔」,
            點下去就跳到個股(期)頁看那一檔的五檔與分時(總 spec §4 下方區塊帶)。 */}
        {subtab === "limit" ? (
          <LimitListSection onOpenStock={onOpenStock} active={active} />
        ) : null}
        {subtab === "corr" ? <CorrSection /> : null}
      </section>
    </div>
  );
}

export default IndexPage;
