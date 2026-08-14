# current-state — 指數分時圖 overlay(mod/index-overlay)

日期:2026-08-14。目標:台股綜合頁兩張指數分時圖補(1)分時均價線(加權+櫃買)、
(2)加權 CDP + MA5/MA20 疊線(3)昨收虛線價位標籤。已拍板:CDP/MA 只做加權,
櫃買無日 K 來源跳過。

## 現況(逐層)

### 後端

- **overlay 純函式** `copycat/server/overlay.py`:`compute_cdp` / `compute_ma` /
  `build_overlay(bars: list[DailyBar], today) -> {cdp, ma5, ma20, date}`。吃
  `DailyBar`(`copycat/live/stock_source.py:48`,TypedDict:date/high/low/close,毫元),
  **與個股解耦**(只吃形狀)。「已完成 bar」規則:`date < today` 才入計算;空 → 全 null。
  `OverlayCache`:key `(code, today)`,**空結果不 cache**(don't-cache-empty,斷線恢復可重試)。
- **caller**:`app.py:57` import;`app.py:373` `overlay_cache = OverlayCache()`(per-app);
  `app.py:1040-1051` `GET /api/stock/overlay/{code}` = 唯一消費端(`stock.daily_bars(code)`
  → build_overlay → cache)。tests:`tests/server/test_overlay.py`、`test_stock_routes.py`。
- **加權日 K 來源**:`IndexEngine.bars_range(tf, start, end)`(`index_engine.py:405-427`)
  → `(list[Bar], source_tag)`;**必須從 index engine 的 session 問**(W-12:IX0001 的
  REALTIME 訂閱在這條 session,跨 session 問同 symbol 會搶推播)。TC4 不可用 →
  `([], "unavailable")` 不 raise。`Bar.t` 日 K = `"YYYY-MM-DD"`。
  現有 caller:`app.py:1301-1302`(market bars endpoint,TWSE 分支)。
- **cache key 衝突風險(本輪新發現)**:`_CODE_RE = ^(?=.*\d)[A-Za-z0-9]{4,6}$`
  (`stock_watchlist.py:41`)→ **`IX0001` 能通過 `_valid_code`**,
  `/api/stock/overlay/IX0001` 會從 **stock session** 取數並寫 overlay_cache 鍵
  `("IX0001", today)`。新 endpoint 若用裸 `IX0001` 當鍵會被汙染 → 需帶後綴隔離
  (慣例:bars cache 用 `IX0001|M` / `|L` 後綴,`app.py:1319-1323`)。
- **日 K 視窗慣例**:`stock_source._DAILY_WINDOW_DAYS = 40`(25 交易日 + 假日餘裕);
  `bars.DAILY_WINDOW_DAYS = 180`。MA20 需 ≥ 20 根已完成 bar → 40 日曆日足夠。
- 個股引擎 `daily_bars` 慣例(`stock_engine.py:613-619`):ConnectionError → log + 回空
  (best-effort 降級)。

### 前端

- **IntradayChart**(`MarketChart.tsx:34-83`,module-private):吃 `IndexSeries`
  (`useIndexStream.ts:13`:p/ref/high/low/stale/minutes;minutes 鍵 `"HHMM"`、值毫點),
  畫:小時格線、**昨收虛線(58-66 行,無數值標)**、yTicks(**三格 = [yBottom, ref, yTop]**,
  左緣 x=2 —— 昨收價其實已在左緣中格出現,但無「昨收」語意標示)、單色 accent 走勢線。
  無 toggle、無均價線、無疊線。
- **幾何**:`lib/index-chart-svg.ts::buildIndexGeometry` → `{line, refY, yDomain, yTicks}`;
  autofit 域(±0.3% pad),**不回傳 toY**(內部閉包)。callers:MarketChart.tsx:35 +
  `index-chart-svg.test.ts`。同檔 `buildOverlayGeometry`(加權 vs 櫃買 % 重疊圖)與本輪無關。
- **個股疊線樣板**(要仿的對象):
  - hook `useStockOverlay.ts`:TanStack Query,queryKey 含 `localYmd()`(跨日自動失效),
    staleTime Infinity、retry 1;enabled = code 非空 + (cdp||ma) toggle 開。
  - `stock-intraday-svg.ts::overlayLines(overlay, g, toggles)`:**只用 `g.yDomain` +
    `g.toY`**(域外 clip 不畫);`StockOverlay` / `OverlayLevel` / `OverlayLine` 型別同檔。
  - 配色表 `LEVEL_STROKE` / `LEVEL_FILL` 定義在 **StockIntradayChart.tsx:65-83**(元件層,
    未共用);右緣文字 `levelText`(CDP 印價位+`*`、MA 印名稱)。
  - 可用性:`cdpAvailable` / `maAvailable`(資料未回=可用;回了 null / error → 反灰
    toggle + title 說明,StockIntradayChart.tsx:697-704、795-801)。
- **toggles**:`useChartToggles`(全域單 localStorage key,欄位 vwap/cdp/ma/bb/vp;
  DEFAULTS:vwap=true, cdp=true, ma=false)。IndexPage.tsx:105 已上提並下傳
  `toggles`/`onToggle` 給兩個 MarketPane;MarketPane 目前只消費 `toggles.bb`
  (轉成 `showBb`/`onToggleBb` 傳 MarketChart)。
- **MarketChart Props**:marketKey/mode/name/series/showBb/onToggleBb/active。
  caller = MarketPane.tsx:379 唯一(+ App.test.tsx 綜合測試)。
- tests:`MarketPane.test.tsx`、`IndexPage.test.tsx`、`App.test.tsx`、
  `index-chart-svg.test.ts`;**無 MarketChart 專屬 test 檔**。

## 現況 vs 目標表

| 面向 | 現況 | 目標 | caller 影響 | backward compat |
|---|---|---|---|---|
| 均價線 | 無 | 加權+櫃買分時圖各加當日累計算術平均線(仿個股 VWAP 畫法;指數無量) | buildIndexGeometry 回傳型擴欄 | 加欄不改舊欄,既有 caller 不受影響 |
| CDP/MA 疊線(加權) | 無 | 重用 overlay.py 純函式;新 `GET /api/index/overlay`;前端仿 oLines + toggle | app.py 加 endpoint;MarketChart Props 改(toggles 下傳) | 新 endpoint 純增;MarketChart props 變更僅 MarketPane 一個 caller |
| 昨收標籤 | 虛線存在;左緣中格有數值但無語意標 | 昨收虛線可指認的價位數值標籤 | 無 | 純增 SVG 元素 |
| 配色表 | LEVEL_STROKE/FILL 在 StockIntradayChart 元件內 | 上移共用處供 MarketChart 重用(🔵) | StockIntradayChart import 路徑改 | 行為零差異 |
| OverlayCache 鍵 | 個股 code | 指數用 `IX0001\|OVL` 後綴隔離(IX0001 過 _CODE_RE 會撞) | 無 | 無 |

## Baseline

- 後端 pytest / 前端 vitest baseline:背景執行中(結果記入 change-spec 前確認全綠)。
- root `node_modules/` untracked(既有噪音,與本輪無關,不動)。
