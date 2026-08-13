/** localStorage key 的唯一宣告處。
 *
 *  **為什麼集中**:key 原本散在 8 個元件 / hook 各自 `const`,每輪 UI 功能都在長新 key,
 *  沒有單一清單可對照 —— 停用功能留下的孤兒鍵(`stock-ladder-open` / `stock-wl-group`)
 *  就是這樣漏掉的。新增偏好設定一律先在這裡宣告,不在元件內寫字面值。
 *
 *  命名前綴一律 `copycat-`:localStorage 是 origin 級共用空間,無前綴的 key 與他站撞名
 *  且清 site data 時難對照。 */

/** 主 tab(txo / stock / futures / index)— App.tsx */
export const TAB_KEY = "copycat-tab";
/** 主圖個股代號 — App.tsx */
export const MAIN_CODE_KEY = "copycat-stock-main-code";
/** `MAIN_CODE_KEY` 的舊名(唯一漏前綴的 key)。App 初始化時一次性搬遷後刪除,
 *  搬遷邏輯不可拿掉 —— 拿掉的代價是使用者的主圖標的在改版後靜默回到未選狀態。 */
export const LEGACY_MAIN_CODE_KEY = "stock-main-code";

/** 已停用功能留下的孤兒鍵:`stock-ladder-open`(2026-07-29 閃電梯改條件 render 後零讀寫)、
 *  `stock-wl-group`(2026-07-30 自選分組改後端 schema v2 後零讀寫)。App 啟動時清除,
 *  避免使用者瀏覽器裡永久留著再也沒人讀的殘值。 */
export const ORPHAN_STORAGE_KEYS = ["stock-ladder-open", "stock-wl-group"] as const;

/** 清除孤兒鍵。冪等(removeItem 對不存在的 key 是 no-op),由 App.tsx 的 module scope
 *  呼叫一次 —— 它與元件生命週期無關,也不該隨 re-render 重跑。
 *
 *  **整段包 try/catch**:呼叫點在 App module 的頂層求值期,localStorage 在 Safari 私密
 *  視窗 / storage 被政策鎖時光是存取就會拋 —— 拋出去就是整個 App chunk 求值失敗 = 白屏。
 *  清不掉遠好於白屏(同 `hooks/useChartToggles.ts` 的 `persist()` 慣例)。 */
export function purgeOrphanKeys(): void {
  try {
    for (const key of ORPHAN_STORAGE_KEYS) window.localStorage.removeItem(key);
  } catch {
    // 清不掉就算了 —— 殘值只是佔位,沒人讀
  }
}

/** 期貨 tab 的商品(TXF / MXF / TMF)— App.tsx */
export const PRODUCT_KEY = "copycat-fut-product";
/** 期貨 tab 的圖表模式(分時 / 1–60 分K / 日K)— lib/fut-chart-mode.ts 持有值域與還原。
 *  **與個股的 `CHART_MODE_KEY` 刻意分開**:兩邊檔位值域不同(個股 m1–m10、期貨
 *  m1/5/15/30/60),共用一把鍵會讓其中一頁的合法值在另一頁被白名單擋掉、靜默重設。 */
export const FUT_CHART_MODE_KEY = "copycat-fut-chart-mode";

/** 台股綜合**左圖**選中的指數(TWSE / OTC / TXF …)— components/index/IndexPage.tsx */
export const MARKET_KEY_STORE = "copycat-market-key";
/** 台股綜合**左圖**的週期 / 模式(分時 / 日K …)— components/index/IndexPage.tsx */
export const MARKET_MODE_STORE = "copycat-market-tf";
/** 台股綜合**左圖**的期現疊圖開關(舊值 "overlay" / "side")— components/index/IndexPage.tsx。
 *  重疊圖畫的固定是加權 vs 櫃買,右圖開它會出現兩張相同的圖 → 右圖不給重疊鈕,
 *  因此**沒有** `MARKET2_OVERLAY_STORE` 這支 key。 */
export const INDEX_OVERLAY_STORE = "copycat-index-mode";
/** 台股綜合**左圖**的期貨商品,**刻意不與 `PRODUCT_KEY` 共用**:共用會讓大盤頁選微台時,
 *  期貨 tab 與右欄閃電梯的武裝語境一起被換掉 — components/index/IndexPage.tsx */
export const MARKET_FUT_STORE = "copycat-market-fut";

/** 台股綜合**右圖**選中的指數(左圖沿用 `MARKET_KEY_STORE`,舊使用者狀態零丟失)
 *  — components/index/IndexPage.tsx */
export const MARKET2_KEY_STORE = "copycat-market2-key";
/** 台股綜合**右圖**的週期 / 模式 — components/index/IndexPage.tsx */
export const MARKET2_MODE_STORE = "copycat-market2-tf";
/** 台股綜合**右圖**的期貨商品 — components/index/IndexPage.tsx */
export const MARKET2_FUT_STORE = "copycat-market2-fut";

/** 相關係數收合區塊的展開狀態("1" = 展開)— components/corr/CorrSection.tsx */
export const CORR_OPEN_KEY = "copycat-corr-open";

/** 漲跌停列表收合區塊的展開狀態("1" = 展開)— components/index/LimitListSection.tsx。
 *  **收合 = unmount**,所以這把鍵同時決定「今天要不要每 10 秒抓一份全市場 rows」。 */
export const LIMIT_LIST_OPEN_KEY = "copycat-limit-list-open";
/** 漲跌停列表的篩選條件(JSON:市場 / 狀態三旗標 + 金額 / 股價門檻字串)
 *  — components/index/LimitListSection.tsx */
export const LIMIT_LIST_FILTER_KEY = "copycat-limit-list-filter";

/** 類股強弱收合區塊的展開狀態("1" = 展開)— components/index/SectorSection.tsx。
 *  **收合 = unmount**,所以這把鍵同時決定「今天要不要每 10 秒抓一份類股輪動」。 */
export const SECTOR_OPEN_KEY = "copycat-sector-open";

/** 訊號時間軸收合區塊的展開狀態("1" = 展開)— components/index/SignalTimelineSection.tsx。
 *  **收合 = unmount**,所以這把鍵同時決定「要不要抓一份含全市場廣度事件的當日訊號」
 *  (自選那份由個股頁的 rail 各自抓,兩者 queryKey 不同族)。 */
export const SIGNAL_TIMELINE_OPEN_KEY = "copycat-signal-timeline-open";

/** 右欄 tab(閃電 / 委託 / 部位)— components/rail/RightRail.tsx */
export const RAIL_TAB_KEY = "copycat-rail-tab";

/** 個股圖表模式(江波圖 / 分K / 日K)— components/stock/StockChart.tsx */
export const CHART_MODE_KEY = "copycat-chart-mode";
/** 疊線開關(vwap / cdp / ma / bb,JSON)— hooks/useChartToggles.ts */
export const CHART_TOGGLES_KEY = "copycat-chart-toggles";

/** 自選側欄折疊中的群組名(JSON 陣列)— components/stock/WatchlistSidebar.tsx */
export const WL_COLLAPSED_KEY = "copycat-stock-wl-collapsed";
/** 自選側欄未分組區塊的折疊("1" = 折疊)— components/stock/WatchlistSidebar.tsx */
export const WL_UNGROUPED_KEY = "copycat-stock-wl-ungrouped-collapsed";

/** 自選檔數上限。**跨檔契約**:與後端 `copycat/stock_watchlist.py::WATCHLIST_LIMIT`
 *  同值,改一邊必須同步另一邊 —— 這裡只餵 `hooks/useStockWatchlist.ts::errText` 的文案,
 *  真正擋下超限的是後端(`WATCHLIST_FULL`)。兩邊漂掉的症狀是使用者看到「已達 N 檔上限」
 *  而 N 不是實際擋人的那個數字,零錯誤訊號。
 *
 *  (不是 localStorage key,放這裡是因為本檔是既有跨元件常數的聚集地,且契約註解需要
 *  一個可 grep 的錨點。) */
export const WATCHLIST_LIMIT = 50;

/** 個股頁檢視("single" / "group")— components/stock/StockPage.tsx */
export const STOCK_VIEW_KEY = "copycat-stock-view";
/** 群組檢視選中的群組名 — components/stock/GroupGridView.tsx。
 *  **與 `WL_COLLAPSED_KEY` 無關**:那支記的是側欄折疊,兩者同時存在且語意不同。 */
export const STOCK_GROUP_KEY = "copycat-stock-group";

/** 訊號提示音開關("on" / "off")— hooks/useSignalSound.ts */
export const SOUND_KEY = "copycat-signal-sound";

/** 手續費折數 — components/stock/PriceLadder.tsx */
export const FEE_DISCOUNT_KEY = "copycat-fee-discount";

/** 江波圖呈現模式(side / overlay)— components/corr/RiverPanel.tsx */
export const RIVER_MODE_KEY = "copycat-river-mode";
/** 江波圖**關掉**哪些腿(JSON 陣列)— components/corr/RiverPanel.tsx */
export const RIVER_OFF_KEY = "copycat-river-legs";
