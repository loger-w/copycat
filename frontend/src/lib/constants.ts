/** localStorage key 的唯一宣告處。
 *
 *  **為什麼集中**:key 原本散在 8 個元件 / hook 各自 `const`,每輪 UI 功能都在長新 key,
 *  沒有單一清單可對照 —— 停用功能留下的孤兒鍵(`stock-ladder-open` / `stock-wl-group`)
 *  就是這樣漏掉的。新增偏好設定一律先在這裡宣告,不在元件內寫字面值。
 *
 *  命名前綴一律 `copycat-`:localStorage 是 origin 級共用空間,無前綴的 key 與他站撞名
 *  且清 site data 時難對照。 */

/** 主 tab(txo / stock / futures / index / corr)— App.tsx */
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
/** 期貨 tab 的商品(TXF / MXF / TMF)— App.tsx */
export const PRODUCT_KEY = "copycat-fut-product";

/** 大盤頁選中的指數(TWSE / OTC / TXF …)— components/index/IndexPage.tsx */
export const MARKET_KEY_STORE = "copycat-market-key";
/** 大盤頁的週期 / 模式(分時 / 日K …)— components/index/IndexPage.tsx */
export const MARKET_MODE_STORE = "copycat-market-tf";
/** 大盤頁的期現疊圖開關(舊值 "overlay" / "side")— components/index/IndexPage.tsx */
export const INDEX_OVERLAY_STORE = "copycat-index-mode";
/** 大盤頁的期貨商品,**刻意不與 `PRODUCT_KEY` 共用**:共用會讓大盤頁選微台時,期貨 tab
 *  與右欄閃電梯的武裝語境一起被換掉 — components/index/IndexPage.tsx */
export const MARKET_FUT_STORE = "copycat-market-fut";

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

/** 訊號提示音開關("on" / "off")— hooks/useSignalSound.ts */
export const SOUND_KEY = "copycat-signal-sound";

/** 江波圖呈現模式(side / overlay)— components/corr/RiverPanel.tsx */
export const RIVER_MODE_KEY = "copycat-river-mode";
/** 江波圖**關掉**哪些腿(JSON 陣列)— components/corr/RiverPanel.tsx */
export const RIVER_OFF_KEY = "copycat-river-legs";
