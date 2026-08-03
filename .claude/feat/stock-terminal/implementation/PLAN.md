# Implementation PLAN — stock-terminal(condensed;對照 design.md v4)

> Wave 建議:W1 = backend 純函數層(1-2)、W2 = source/engine/routes(3-6)、W3 = frontend lib/hooks(7-11)、W4 = frontend 元件 + 整合(12-16)。W1/W3 內部各檔獨立可並行;W2 依賴 W1;W4 依賴 W3。

## Backend

### 1. `copycat/live/stock_models.py`(SC-4/5;design §2.1)+ `tests/live/test_stock_models.py`
- 新增 `StockTick`(code/price_milli/qty/cum_vol/time/trade_date/buy_sell_flag/is_trial)、`StockBook`(bids/asks: list[tuple[int,int]])、`StockMeta`(ref/upper/lower/y_close 毫元、y_volume、name、open_time、close_time)。
- `parse_stock_realtime(msg: dict) -> tuple[StockTick | None, StockBook, StockMeta]`(design §2.1 原版;book/meta 必回,僅 tick 可 None):TradeQuantity 空/0 → tick=None;位移命名歸一(Bid→L0、Bid1→L1);空字串價位跳過;UTC→台北(+8)含跨日進位;`derive_side(price, book) -> str`。
- `parse_hist_tick(row: dict) -> StockTick`(FilledTime zfill/UTC、TradeVolume)。
- `is_trial_window(time_taipei: str) -> bool`:[08:30,09:00)/[13:25,13:30) 端點不含。
- 失敗測試:位移對映、端點四案例(08:59:59.9/09:00:01/13:29:59/13:30:00)、UTC+8 跨日、空 Ask 側(漲停)、TradeStatus!=0 不丟只 warning(caplog)。

### 2. `copycat/live/stock_state.py`(SC-3/5/6;design §2.2)+ `tests/live/test_stock_state.py`
- `MinuteAgg`(close_milli/volume/inner/outer/unch)、`StockDayState`:`ingest(tick) -> bool`(cum_vol 去重;is_trial 在 dedup 前丟棄且不觸 `_last_cum`)、`reset()`、`snapshot() -> dict`(含 seq)、`apply_backfill(ticks: list[StockTick])`(原子重建 + seq 跳增)。
- 內部:ticks deque(maxlen=20000)、minutes、vwap、cum_inner/outer、book、last、seq。
- 失敗測試:去重(cum 回退丟)、試撮不動 `_last_cum`、reset 後小 cum 可 ingest、apply_backfill seq 跳增、VWAP/分鐘聚合數值、snapshot shape。

### 3. `copycat/live/stock_source.py`(SC-2~5;design §2.3)+ `tests/live/test_stock_source.py`
- [phase-3 補註] StockQuoteSource **繼承 TC4QuoteSource**(連線/REQ 互斥/_dispose/stale 重連全複用,不動 tc4.py);覆寫 `_rt_request`(個股日窗)/`_listen_loop`(原始 Quote dict 分派 `handle_raw`)/逐檔 `subscribe_symbol`/`backfill(code)`;StockTick 增 `side` 欄(parse 時對照 Bid/Ask 算好,state 不需 book 上下文)。
- `StockQuoteSource(port, *, api/session/sub_port 可注入)`:`subscribe/unsubscribe(symbol)`(REALTIME 帶日窗)、`backfill(symbol, date) -> list[StockTick]`(SubHistory+收割)、`set_on_message(cb)`、listener(generation-following,tc4.py 同款)、**全 REQ 過單一 lock**(`_session_req` 同款);收割中 SUB 排隊頁間插入。**無推播健檢在 source 層**(design §2.3):subscribe 後 10s(僅交易時段)無任何推播 → `on_no_data(symbol)` callback 通知 engine 標狀態。
- 失敗測試(fake api 注入):REQ 序列不交錯(收割中 subscribe 延到頁間)、listener 跟隨 generation、訂閱失敗 raise、健檢盤外不觸發/盤中 10s 觸發。

### 4. `copycat/server/stock_engine.py`(design §2.4)+ `tests/server/test_stock_engine.py`
- `StockEngine`:refcount 池(`_refs: dict[str, set[str]]`,0→1 真訂/last-out 真退/失敗回滾)、有界 asyncio.Queue(1000,滿丟最舊)+ 常駐 consumer、側欄 1s 節流合併、主圖全量轉發、backfill worker queue(單工,job 帶 (symbol, day_generation),套用 guard = main owner ∧ generation;**worker queue 與 guard 由 engine 持有,source 只提供同步 backfill()** — r2-1 定案)、兩段式 rollover(08:00 重掛 → 首筆新日推播才 reset+重回補;觸發 tick 重 ingest)、接收 source `on_no_data` 標 no_data、stkfut 加訂(對映表命中,輕量直送;推播 SecurityName 與對映表交叉核對,不符 logger.warning)、**TC4 斷線/恢復:status 事件推 WS(`tc4: up|down`、`backfilling` 欄)+ 恢復後自癒重掛訂閱與主圖交接重跑**。
- 失敗測試:refcount 三案例、A 回補中切 B 不落地、回補中 rollover 舊結果作廢、假日不清空、**新日首筆 cum=50 reset 後 ingest 成功(不被 stale-drop)**、queue 滿丟最舊、斷線 status down→up 推播 + 自癒重跑、SecurityName 不符 warning(caplog)。

### 5. `copycat/stock_watchlist.py`(SC-1;design §2.5)+ `tests/test_stock_watchlist.py`
- `load() -> list[str]` / `save(codes: list[str])`:`data/stock_watchlist.json`,atomic_write + `_cache_version`;`validate_code(code) -> bool`(4-6 位英數且至少一位數字)。上限 30。
- 失敗測試:round-trip、超限、壞碼、重複冪等。

### 6. `copycat/server/app.py` 修改 + `tests/server/test_stock_routes.py`
- lifespan 掛 StockEngine(與 TXO EngineRuntime 並存);`GET/PUT /api/stock/watchlist`、`GET /api/stock/state/{code}`、`WS /ws/stock`。error codes:`WATCHLIST_FULL`/`BAD_CODE`/`TC4_DOWN`(全域 handler,route 只 raise)。
- 失敗測試(fake engine 注入):watchlist CRUD + 400 兩碼、state snapshot、WS 訊息流冒煙。

### 7. `copycat/stkfut_map.py`(SC-7;design §2.6)+ `copycat/cli.py` 修改 + `tests/test_stkfut_map.py`
- `load_map() -> dict[str, dict]`(讀 **`copycat/stkfut_map.json`** — package data 與 watchlist.py/market.py 同層;路徑定案取代 design 原 `data/`(撞 gitignore),已記 design changelog)、`refresh(url=期交所股票期貨契約 CSV) -> dict`(urllib + 失敗保留舊檔);CLI 子命令 `refresh-stkfut-map`。初版靜態 JSON 隨 PR 內建(含 CDF=2330 等)。
- 失敗測試:load/refresh 解析、失敗保舊。

## Frontend(frontend/src;皆繁中 UI、semantic token、`@/` alias)

### 8. `lib/stock-accum.ts` + `lib/stock-accum.test.ts`(SC-3/6;design §4 tick 累算)
- 純函數:`applyTick(state, tick)` 累算 minutes/vwap/cumInner/cumOuter;`fromSnapshot(snap)` 建基底。等值測試:snapshot 基底 + tick 序列 = 後端 state 等值(fixture 對照)。

### 9. `lib/stock-intraday-svg.tsx` + 測試(SC-3/6)
- 純函數 geometry:價線 path、VWAP path、昨收/漲跌停水平線、量 bar、內外盤副圖 bar(外紅內綠)、x 域 09:00–13:30 固定。測試:座標數值案例。

### 10. `lib/list-drag.ts` + 測試(SC-1)
- 純函數:pointer y → 插入 index;`reorder(list, from, to)`。測試:邊界(頂/底/自身)。

### 11. `hooks/useStockStream.ts` + `hooks/useStockWatchlist.ts` + hooks 測試
- `useStockStream`:WS 連線 + 訊息分派入 TQ cache(`setQueryData`);seq 跳號(`next != last+1`)→ invalidate + refetch;snapshot 對齊(丟 seq ≤ S);重連 backoff;**status 訊息處理(tc4 down → 頁頂告警列、backfilling → 主圖 loading 標示)**。`useStockWatchlist`:TQ query + PUT mutation。
- 失敗測試(mock WS):跳號觸發 refetch、refetch 交錯無重複無漏、backfill 完成(seq 跳增)→ 筆數變全日、status tc4:down → 告警列出現 / up → 消失。

### 12. `components/stock/WatchlistSidebar.tsx` + 測試(SC-1/2)
- 清單列(代碼/名/現價/漲跌%/總量,no_data 灰顯)、輸入框新增、pointer 拖拉(用 lib/list-drag)、刪除;PUT 整份。RTL 冒煙 + 拖拉呼叫 reorder。

### 13. `components/stock/StockIntradayChart.tsx`(SC-3/6)
- 掛 stock-accum 資料 → intraday-svg 渲染;容器尺寸 hook 沿用專案慣例。RTL 冒煙(jsdom pragma)。

### 14. `components/stock/OrderBook.tsx` + `components/stock/TickTape.tsx` + 測試(SC-4/5)
- OrderBook:五檔 DOM 表格 + 量背景 bar + 空側「—」+ 點價 CustomEvent(no-op 接點)。TickTape:尾 200 筆 + 載入更多;side 上色。RTL:對映渲染、空側、上色 class。

### 15. `components/stock/StockPage.tsx` + `App.tsx` 修改(tab)(SC-7 UI 含 header 期現價差)
- 版面組裝:側欄 + 主圖(chart/五檔/明細)+ header(名稱/現價/漲跌/期現價差);`hidden` tab 切換 + `React.lazy`。RTL 冒煙。

### 16. 整合尾工
- `python -m copycat.server` 啟動含 stock engine;`docs/` 不動;`npm run build` + 全 gate。

## 全域約束(每節隱含)
- design.md v4 §契約為準;毫元 int;時間台北;`from __future__ import annotations`;pyright/ruff/eslint/tsc 零新錯。
- TDD:每節紅先行([red]→[green] tag);goal_efficiency_mode 未啟用。
