# 現況(/mod trial-pause-badge)— 個股試撮/暫緩撮合狀態鏈路

日期:2026-08-13(17:40 收盤後開工 → 本輪走降級路線:時間窗版 + TradeStatus 觀測 log,
盤中蒐證延緩撮合行為後才開第二段)。

## 1. 試撮判定現況(parse 層)

| 項目 | 位置 | 現況 |
|---|---|---|
| 試撮窗常數 | `copycat/live/stock_models.py:28` `TRIAL_WINDOWS` | `[08:30,09:00)` + `[13:25,13:30)`(台北,端點不含右界) |
| 窗判定函式 | `stock_models.py:98` `is_trial_window(time_taipei, windows)` | 純函式,字串比對 `HH:MM:SS.fff`;空窗恆 False |
| per-instrument 窗對映 | `copycat/live/stock_source.py:387` `trial_windows_for(key)` | **唯一** key→窗對映:期貨鍵(`F:` 前綴)→ `()`,現貨 → `TRIAL_WINDOWS` |
| tick 上的旗標 | `StockTick.is_trial`(stock_models.py:55) | parse 時以 tick 時刻對窗算出 |
| TradeStatus | `stock_models.py:211-215` | 已知值域 {0=正常, 1=試撮期簿更新}(2026-07-21 實測);值域外**僅 warning 觀測不丟棄**(design r2-F5:丟棄的失效模式 = 處置股整檔靜默消失) |

關鍵市場事實(tc4-market-facts「個股 REALTIME 實測事實」節):**試撮期 TC4 不推成交
tick**(時間窗過濾為雙保險),試撮期間收到的是 `TradeStatus=1` 的**簿更新**(2026-07-21
實測 13:25–13:30 共 213 筆)。→ 「盤中延緩撮合」期間 TradeStatus 行為(值域/起訖/恢復)
**未實測**,是本任務 (a) 要蒐證的對象。

## 2. 丟棄行為(不能動)

`copycat/live/stock_state.py:72-81` `StockDayState.ingest`:
```python
if tick.is_trial:
    return False  # dedup 前短路,不觸 _last_cum
```
`apply_backfill`(stock_state.py:115)同款 `if tick.is_trial: continue`。
兩處**行為不變**(XR-5 是大盤廣度拍板,與本條個股標示語意獨立)。
→ 試撮期間主圖 tick / watchlist dirty / signal_hub 全部天然不動(掛在 ingest 為真分支內)。

## 3. Engine 層(server/stock_engine.py)

- `_handle_quote`(:783):raw `quote` dict 在手 → **TradeStatus 可直接從 raw msg 讀,
  不必動 parse 層簽名**。parse 呼叫點 :800 帶 `trial_windows_for(code)`。
- 期貨鍵夜盤整則早退(:801-815);純簿更新無 tick 時刻 → 退本機時鐘 `_now_taipei_hhmm()`
  (:58,格式 `HH:MM`,部署綁本機 = 台北)。
- `_quote_payload`(:1030)= `watchlist_quote` 的**唯一** payload builder。
  [amendment 2026-08-13: review R5] 產出點實為 **7 處**(docstring「四個」已漂移,記
  next-time 不順手改)::373(set_watchlist 新增)、:457(`quotes()` → Discord 同群摘要,
  只取 `chg_pct`)、:647(`_retry_subscribe_loop` 重掛成功種子)、:767(`_handle_no_data`,
  任意 code 含合約鍵)、:919(轉態補推,gate `code in _watchlist`)、:1077(連線 seed)、
  :1091(1s flush)。全部消費端逐鍵取值 → additive 加鍵零破壞;Discord 路徑(:457)會
  多觸發 trial 現算(讀系統時鐘),per-call 開銷微秒級可忽略。
  既有契約:`no_data=True` 時**所有值欄位一律 None**;`p`/`ref` 互斥;`upper`/`lower` 亮燈用。
- `_handle_no_data`(:764):對**任何** code(含合約鍵)publish `_quote_payload(code)` —
  前端主圖也收 watchlist_quote 的先例(useStockStream.ts:314-325 靠它把 noData 帶進 accum)。
- `_flush_watchlist_loop`(:1082):1s 節流;**只 publish `state.last is not None` 的 dirty
  碼** — 盤前無成交的檔不會經過這條路。
- `snapshot(code)`(:424):`state.snapshot()` + engine 層附加 `code` / `no_data`;
  tc4 / backfilling 刻意**不進** snapshot(真相源在 WS status)。
- `group_snapshot`(:460):群組卡片輕量 batch,走 `light_snapshot()`(minutes/meta)+
  no_data/backfilling 兩旗標。

## 4. Wire → 前端

| 通道 | 型別 | 消費端 |
|---|---|---|
| WS `watchlist_quote` | `useStockStream.ts:18` `WatchlistQuote`(p/chg_pct/vol/ref/upper/lower/no_data) | 側欄 `WatchlistSidebar.stockRow`(quotes prop);主圖 noData 補寫(:318) |
| REST `/api/stock/state/{code}` | `stock-accum.ts:138` `SnapshotShape` → `fromSnapshot` → `StockAccum`(含 `noData`) | StockPage 經 accum |
| WS `tick`/`book`/`status`/`stkfut` | 主圖增量 | StockPage |

- 側欄列(WatchlistSidebar.tsx:291 `stockRow`):兩行式,第一行 `code`(font-mono
  text-base)+ 右側價格塊;`q?.no_data` → 顯示「無資料」取代報價塊;漲跌停亮燈
  `limitState`。
- 單檔頁 header(StockPage.tsx:230):`<h2>` 名稱 + code;後接合約下拉、`page-quote`
  大字報價、`accum?.noData` →「無資料」、`backfilling` →「回補中…」小字。期貨態 =
  `contract !== null`。
- 舊前端對未知 key 忽略;新前端對缺 key 用 `?? null` / `Boolean()` 降級 — additive
  欄位雙向相容是既成慣例(`h`/`l`/`vwap_vol`/`ref` 全走過這條路)。

## 5. Caller map(動態用法已 grep)

`parse_stock_realtime` callers:`stock_engine.py:800`(帶窗)、`corr_engine.py:228`
(相關係數腿,不看 is_trial)、`futures_models.py:35`(**別名** `parse_futures_realtime`,
期貨引擎層忽略 is_trial 旗標)。`parse_hist_tick` callers:`stock_source.py:513`(回補,
帶窗)。`is_trial` 消費點:`stock_state.py:74,115`(丟棄)、tests。
`TradeStatus` 讀取點:只有 `stock_models.py:211`(觀測 warning)。
→ **無動態用法**(getattr/字串拼接呼叫皆無)。

## 6. 現況 vs 目標

| 面向 | 現況 | 目標(本輪) |
|---|---|---|
| 「緩撮中」狀態 | 不存在(is_trial 只掛在被丟棄的 tick 上) | engine 層以「本機時鐘 × trial_windows_for」現算 per-instrument `trial` bool |
| wire | watchlist_quote / snapshot 無此欄 | 兩通道 additive 加 `trial: bool` |
| 窗轉態 | 無人推播(試撮期無 tick → flush loop 不動) | flush loop 偵測窗翻轉,對自選碼 + 現貨主圖補推 payload |
| UI | 無標示 | 側欄列 code 旁 +「(緩)」;單檔頁 header code 旁 +「(緩)」;期貨態不標 |
| TradeStatus | 值域外 warning(parse 層,無 per-code 前值) | engine 層 per-code 轉態觀測 log(蒐證通道,為第二段鋪路) |
| 盤中延緩撮合偵測 | 無 | **不在本輪**(待蒐證,第二段) |
| backward compat | — | 全 additive,無 migration;舊前端忽略、新前端缺 key → false |
