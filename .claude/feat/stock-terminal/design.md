# Design — stock-terminal(個股看盤,第一輪)v4(定稿)

Changelog:
- v4.2(2026-07-21,Phase 6 收斂):R1/R5 以盤中 probe 實測關閉 — 試撮期(13:25–13:30)TC4 對個股不推成交 tick(觀測 0 筆),TradeStatus 值域 {0=正常, 1=試撮期簿更新};時間窗過濾降為雙保險。盤後 fresh subscribe 回當日收盤 snapshot(延遲分鐘級),SC-2 降級路徑成立。證據:evidence/trial_close_summary.json + EDGE-2 截圖。
- v4.1(2026-07-21,Phase 2 對齊):stkfut 對映檔路徑 `data/stkfut_map.json` → **`copycat/stkfut_map.json`**(原路徑撞 `data/` gitignore;package data 與 watchlist.py 同層),模組 `copycat/stkfut_map.py`(impl-spec review r1-F2)。
- v4(2026-07-21):review round 3 全 5 條 accepted 就地修入 — F1 rollover 保守順序(先重掛後 reset,免假日表;§2.4)、F2 回補套用 seq bump + 前端 tick 增量累算契約(§2.2/§4)、F3 stkfut 輕量 parser 註明(§2.6)、F4/F5 註記。round 3 verdict:0 P0 / 2 P1 / 3 P2,達退出門檻。
- v3(2026-07-21):review round 2 全 6 條 accepted — F1 回補 day-generation guard(§2.3/§2.4)、F2 StockTick.trade_date + 欄名統一(§2.1)、F3 seq 判定與 refetch 交錯規則(§2.2/§4)、F4 REQ 全域互斥(§2.3)、F5 TradeStatus 降觀測(§2.1/§7)、F6 非交易日不 rollover(§2.4)。
- v2(2026-07-21):review round 1 全 9 條 accepted 修入 — F1 跨日 rollover(§2.4)、F2 回補序列化+取消(§2.3)、F3 原生拖拉排序(§3)、F4 試撮窗界明定(§2.1)、F5 seq gap 復原+刪 delta(§2.2/§4)、F6 股號驗證放寬(§2.5)、F7 契約時間台北化(§4)、F8 deque/status/欄名(§2.2/§2.4)、F9 盤後健檢保守化(§2.3)。
- v1(2026-07-21):初版。基於 brainstorm.md(案 A)+ 2026-07-21 盤中兩輪 spike 事實。

## 0. Spike 事實(設計依據,今日盤中實測)

- 個股 REALTIME push 完整五檔 + ReferencePrice/UpperLimitPrice/LowerLimitPrice/開高低/昨收昨量/FlagOfBuySell/TradeStatus/TradeVolume(累積)。樣本:scratchpad `stock_realtime_sample.json`。
- **上櫃股直接掛 TWS 段**:`TC.S.TWS.5483`(中美晶,上櫃)推播成功;TWO/TPE/OTC 段全無推播。→ SC-8 無需特殊處理,全部 `TC.S.TWS.<code>`。
- **個股期可訂閱但不在商品樹**:`TC.F.TWF.CDF.HOT` 推播成功(price 2398,`SecurityName`=「台積電(2330)」自帶 underlying 股號);QUERYALLINSTRUMENT Type="Fut" 只回 40 個指數/商品期產品碼,無任何個股期。→ 期現對照需外部對映表(§6)。
- 股票類 QUERYALLINSTRUMENT 無有效 Type → 股號存在性靠訂閱後推播健檢。

## 1. 總覽與資料流

```
達錢4 (ZMQ 50774, 獨立 session #2)
   │ REALTIME push(SUB)+ 當日 TICKS 回補(REQ)
   ▼
StockQuoteSource(copycat/live/stock_source.py)──唯一碰 ZMQ
   │ StockTick / StockBook(dataclass)
   ▼
StockDayState(copycat/live/stock_state.py)──零 IO 狀態機,per symbol
   │ 明細環形窗 / 分鐘聚合(價量+內外盤)/ VWAP / 最新五檔快照
   ▼
StockEngine(copycat/server/stock_engine.py)──訂閱池 + 交接 + WS 廣播
   │ REST(snapshot/watchlist)+ WS /ws/stock(增量)
   ▼
React「個股」頁(WatchlistSidebar / IntradayChart / OrderBook / TickTape)
```

與 TXO 完全平行:不動 `tc4.py`/`engine.py`;共用 `tc4common`(APPID/SKEY/iter_qry_pages)、`build_rt_request`(自 `tc4.py` import,純函數)、`market.py`(毫元運算)。TC4 平台原生支援多 session 並存(今日 log 3 session 實證)。

## 2. Backend 模組

### 2.1 `copycat/live/stock_models.py`(SC-4/5 對映層)

- `StockTick`:`code, price_milli, qty, cum_vol, time(台北 HH:MM:SS.fff,parse 層已 +8), trade_date(台北 YYYY-MM-DD,由 TradeDate/Date 欄轉), buy_sell_flag(int|None), is_trial(bool)`。
- `StockBook`:`bids: list[tuple[int, int]], asks: list[tuple[int, int]]`(毫元價, 張數;**位移命名歸一**:`Bid`→level0、`Bid1`→level1…;空字串價位跳過)。
- `StockMeta`:`ref_price_milli, upper_milli, lower_milli, y_close_milli, y_volume, open_time, close_time, name`。
- `parse_stock_realtime(msg: dict) -> tuple[StockTick | None, StockBook, StockMeta]`:一則 REALTIME 拆三件;`TradeQuantity`/`TradingPrice` 空或 0 → tick=None(純簿更新,07-20 實證 ~95% 是 equal 重送,簿更新照收、tick 不重複)。
- `parse_hist_tick(row: dict) -> StockTick`:歷史 TICKS 列(`FilledTime` zfill/UTC、`TradeVolume` 盤中回補有值)。
- 試撮判定 `is_trial`:**只以時間窗為準** — 時間(台北)落在 **[08:30, 09:00) 或 [13:25, 13:30),端點不含**:09:00:00.000 起為開盤撮合、13:30:00.000 起為收盤撮合,皆為真成交必收。`TradeStatus != "0"` **不丟棄**,僅 `logger.warning`(帶值 + code)觀測 — 旗標值域未實測,放丟棄路徑的失效模式是「處置股/恢復交易等正常情境整檔靜默消失」(round 2 F5);13:25–13:30 實測收斂值域後才可升級為丟棄條件。`is_trial` 在 dedup **之前**短路,且**不觸碰 `_last_cum`**(試撮期 TradeVolume 為模擬值,記入 max 會讓真開盤 tick 被 stale-drop)。測試端點案例:08:59:59.9 丟、09:00:01 收、13:29:59 丟、13:30:00 收。
- parse 層即完成 UTC→台北轉換(+8):`StockTick.time`/`trade_date` 已是台北值,state / WS 契約層不再出現 UTC。
- `StockTick` 原始買賣旗標欄名 `buy_sell_flag`(int);內外盤衍生判定(對照 Bid/Ask)產出字串 `side ∈ {"outer","inner","neutral"}`,兩者不共用名字。

### 2.2 `copycat/live/stock_state.py`(SC-3/5/6 狀態機,零 IO)

- `StockDayState.ingest(tick) -> bool`:`cum_vol` 去重(≤ 已見最大值即丟,TXO handover 同款);試撮 tick 在 dedup 前丟棄(§2.1),不進任何聚合、不更新 `_last_cum`。
- `reset()`:清空全部狀態(`_last_cum`/minutes/vwap/deque/book)— 跨日 rollover 用(§2.4)。
- 產出:
  - `ticks`:deque(maxlen=20000;熱門股單日 6.2k、漲停攻防股可更高,20k ≈ <3MB 記憶體;明細 UI 只取尾 N)。
  - `minutes: dict[int, MinuteAgg]`:`close_milli, volume, inner, outer, unch`(內外盤:price≥ask→outer、≤bid→inner,用 tick 內附 Bid/Ask;1K 語意同源)。
  - `vwap_milli`(累積金額/量)、`cum_inner/cum_outer`。
  - `book`(最新五檔)、`last`(現價/漲跌)。
- `snapshot() -> dict`(REST 全量;含 `seq`)。WS 掉訊息復原:前端偵測 seq 跳號 → refetch 全量 snapshot(§4);**不做 delta(since_seq)**(YAGNI,復原一律全量)。
- **回補套用(r3-F2)**:backfill 結果套用 = **原子重建 state 並將 seq 一次跳增**(例如 +回補筆數)— 前端靠跳號規則(§4)自然觸發全量 refetch,無需額外通知型別。hooks 測試:backfilling 完成 → 主圖筆數變全日。

### 2.3 `copycat/live/stock_source.py`(SC-2~5 資料源)

- `StockQuoteSource`:獨立 LOGIN session + SubPort listener(**generation-following**,07-20 修法同款)、`subscribe(symbol)`/`unsubscribe(symbol)`(REALTIME 帶當日 UTC 窗)、`backfill(symbol, date) -> list[StockTick]`(SubHistory TICKS + QryIndex 收割,序列單筆)。
- 回補↔live 交接:沿用 `handover.py` 模式 — 先開 SUB 緩衝、回補收割、`cum_vol` 去重銜接(個股 TradeVolume 單調不減,TXO 已驗證同機制)。
- **REQ 全域互斥(r2-F4)**:StockQuoteSource 內**所有** REQ(SUB/UNSUB/SubHistory/收割分頁)過單一 lock(`tc4.py _session_req` 同款,lock timeout);回補收割中收到 SUB/UNSUB 請求 → 排隊於**頁間**插入執行,不中斷收割。
- **回補序列化 + day-generation(r1-F2 / r2-F1)**:所有 backfill 走**單一 asyncio worker queue,一次一檔**;每個 job 攜帶 `(symbol, day_generation)`。作廢條件:主圖切換 **或 rollover(generation bump)** → 取消/作廢 in-flight job 與其交接緩衝;回補完成**套用前檢查「仍為 main owner ∧ generation 一致」**,不合則丟棄。fake-source 測試:(a) A 回補中切 B → A 結果不落地、REQ 序列不交錯;(b) 回補中觸發 rollover → 舊日結果不落地、今日 live cum 小值不被 stale-drop。
- **多 symbol 回補**:只在主圖切換時回補單檔(07-06 實測全日 124 頁 ≈ 40s,首次進頁可接受);側欄不回補只吃 live。背景預回補自選全部不做(YAGNI,Known Risk R2)。
- 無效股號健檢:subscribe 後 10s 無任何推播(含簿更新)→ callback 通知 engine 標 `no_data`。**僅交易時段(台北 08:30–13:35)生效**;盤外不判 no_data,側欄顯示昨收靜態值(F9:個股休市 snapshot 行為未實測,今日收盤後補 probe,若證實必回 snapshot 再放寬)。

### 2.4 `copycat/server/stock_engine.py`(訂閱池 + 廣播)

- refcount 訂閱池(treading-king `WSPool` 模型):`_refs: dict[symbol, set[owner]]`;owner ∈ {"watchlist", "main", "stkfut"}。0→1 真訂、last 退真退;真訂失敗回滾 bookkeeping 並 raise。
- WS 廣播:單一有界 asyncio.Queue(maxsize 1000)+ 常駐 consumer,滿了丟最舊(treading-king `Broadcaster` 模型);訊息帶 `type`(`tick`/`book`/`meta`/`watchlist_quote`/`stkfut`/`status`)。
- 側欄降頻:watchlist-only 檔的推播節流為 1s 合併一則(現價/漲跌%/總量),主圖檔全量轉發。
- 生命週期:FastAPI lifespan 掛載,與 TXO EngineRuntime 並存;TC4 斷線 → status 事件推前端 + 自癒回補(交接重跑)。
- **跨日 rollover(r1-F1 / r2-F1 / r2-F6 / r3-F1,保守兩段式)**:
  - **階段一(重掛,不清狀態)**:台北 08:00 檢查點且為候選交易日(週一~週五;不引入假日表,YAGNI)→ `day_generation += 1`(作廢 in-flight 回補,§2.3)+ 全部訂閱以**新日 UTC 窗**重掛(UNSUB+SUB;07-20 教訓:窗過期後推播行為不可信)。**此階段不 reset** — 舊日狀態與 meta 保留顯示。
  - **階段二(確認後 reset)**:收到首筆 `trade_date` = 新日的推播(tick 或簿更新)→ 全部 `StockDayState.reset()`(含 seq 歸零)+ 主圖檔以當前 generation 重跑回補交接;**觸發的那筆 tick 於 reset 後重新 ingest**(不漏第一筆)。國定假日/颱風假無新日推播 → 永不進階段二,天然不清空(r2-F6 免疫,無需日曆)。
  - 快路徑:未到 08:00 就收到新日 tick(理論不發生,防禦性)→ 直接依序執行兩階段。
  - 測試:昨日 cum=12000 → 新日首筆 cum=50:reset 後該筆被 ingest 不被 stale-drop;假日(無新日推播)狀態不清空。TXO engine 時段切換重跑(e2c7359)同款思路,個股僅日盤故一天一次。

### 2.5 `copycat/server/app.py` routes(SC-1)

- `GET/PUT /api/stock/watchlist`:讀/全量寫(前端排序後整份 PUT,≤30 檔驗證,超限 400 `{"detail":{"error":"WATCHLIST_FULL"}}`;代碼格式 = **4-6 位英數且至少一位數字**(涵蓋 00637L 等字母尾碼 ETF),不合 400 `BAD_CODE`;存在性不在此驗,交給推播健檢)。
- `GET /api/stock/state/{code}`:主圖全量 snapshot(進頁/切檔用;含回補觸發)。
- `WS /ws/stock`:增量流。
- watchlist 持久化:`data/stock_watchlist.json`(`atomic_write_json` + `_cache_version` 慣例)。

### 2.6 期現對照(SC-7)

- `copycat/stkfut_map.json`(v4.1 路徑定案):`{"2330": {"prod": "CDF", "name": "台積電期"}, ...}`,版本化入 repo(來源:期交所「股票期貨契約」公開表,~200 檔)。
- CLI `python -m copycat refresh-stkfut-map`:urllib 抓期交所 CSV 重生對映(stdlib-only;失敗保留舊檔)。初版對映隨 PR 內建一份靜態產物。
- StockEngine:主圖檔在對映表中 → 加訂 `TC.F.TWF.<prod>.HOT`(owner="stkfut"),推 `stkfut` 訊息(期價/漲跌);前端主圖 header 顯示期價 + 價差(期−現,毫元整數運算)。不在表中 → 不顯示。
- **stkfut 訊息路徑(r3-F3)**:個股期推播**繞過 StockDayState**,輕量 parser 只取 `TradingPrice`/`Change` 直送 WS(spike 樣本證實與個股 REALTIME 欄位同構);期貨時段 08:45–13:45 超出個股窗屬正常,個股未開盤時段的 stkfut 訊息照推(價差欄前端以現股最後價計)。
- 驗證彩蛋:個股期推播 `SecurityName` 含「(股號)」,engine 收到後與對映表交叉核對,不符 log warning(防對映表過期)。

## 3. Frontend(SC-1~7 UI)

- Tab 切換沿用 `hidden` attribute 慣例;新增「個股」tab 與 TXO 並存;重元件 `React.lazy`。
- 元件/檔案:
  - `components/stock/WatchlistSidebar.tsx`:TQ 讀 watchlist + WS `watchlist_quote` 即時價;**拖拉排序用原生 pointer events 手寫**(30 列單清單成本低,不引 dnd-kit;`lib/list-drag.ts` 純函數算插入位置,vitest 可測),放開後整份 PUT。
  - `components/stock/StockIntradayChart.tsx` + `lib/stock-intraday-svg.tsx`(純函數 geometry):分時價線(毫元)、VWAP、昨收基準線(ReferencePrice)、漲跌停上下界、量 bar;下方副圖 = 每分鐘內外盤 bar(外紅內綠,台股慣例 Bull=紅)+ 累積內外盤比數字。x 軸 09:00–13:30 固定域。
  - `components/stock/OrderBook.tsx`:五檔 DOM 表格(非 SVG;量 bar 用背景寬度),中軸現價/漲跌;空側(漲跌停鎖死)顯示「—」。點價 dispatch `stock-price-click` CustomEvent(下一輪下單匣接點,本輪 no-op)。
  - `components/stock/TickTape.tsx`:明細列表(時間/價/單量,外盤紅/內盤綠/中性灰),虛擬化不引庫 — 只渲染尾 200 筆 + 「載入更多」。
  - `hooks/useStockStream.ts`:WS 連線 + 訊息分派(TQ cache 更新);`hooks/useStockWatchlist.ts`:TQ + PUT mutation;`lib/stock-accum.ts`:§4「snapshot 基底 + tick 累算」契約的純函數實作(分鐘聚合/VWAP/累積內外盤,vitest 對照後端等值)。
- 狀態:server state 全走 TanStack Query;WS 增量寫入 query cache(`setQueryData`),無手寫 seqRef。
- 繁中 UI 文字;semantic tokens;`@/` alias。

## 4. WS / REST 契約(§跨檔契約)

```jsonc
// WS 下行(type 區分;時間一律台北時區,parse 層已 +8)
{"type":"tick","code":"2330","t":"09:57:51.000","p":2380000,"q":1,"side":"outer","seq":123}
{"type":"book","code":"2330","bids":[[2380000,125],...],"asks":[[2385000,461],...]}
{"type":"meta","code":"2330","name":"台積電","ref":2320000,"upper":2550000,"lower":2090000,"y_vol":45197}
{"type":"watchlist_quote","code":"5483","p":216500,"chg_pct":-1.2,"vol":28186,"no_data":false}
{"type":"stkfut","code":"2330","prod":"CDF","p":2398000,"basis":18000}
{"type":"status","tc4":"up|down","backfilling":"2330"|null}
```
- 價格一律毫元 int(`market.py` 慣例);時間台北時區字串 `HH:MM:SS.fff`。
- **seq gap 復原(r1-F5 / r2-F3 / r3-F2)**:前端每 code 追蹤 last seq;跳號判定 = **`next != last + 1`**(含回退——rollover 歸零與回補跳增都走此路)→ invalidate 該檔 query 並 refetch `GET /api/stock/state/{code}`。**對齊規則**:snapshot(帶 `seq=S`)為**基底** — 套用後丟棄 seq ≤ S 的 in-flight WS 訊息,只 append seq > S;**之後前端從 tick 增量累算**分鐘聚合/VWAP/累積內外盤(tick 已帶 `p/q/side`,資訊充分)— 即「snapshot 基底 + tick 累算」,兩次 refetch 之間江波圖/副圖靠 tick 即時動(SC-3/SC-6)。hooks 測試:(a) 跳號觸發 refetch;(b) refetch 期間交錯 WS 訊息 → 無重複無漏筆;(c) snapshot 基底 + 後續 tick 累算 = 後端 state 等值(對照案例)。
- book/meta 訊息無 seq:每則自足(全量替換),掉失由下一則自癒 — 刻意設計(r3-F4)。watchlist PUT 為 last-write-wins,多 tab 併發覆寫可接受(單人工具,r3-F5)。
- REST error:`{"detail":{"error":"WATCHLIST_FULL"|"BAD_CODE"|"TC4_DOWN"}}`。

## 5. Edge cases 對映(brainstorm §Edge cases)

| Edge | 設計 |
|---|---|
| 無效股號 | §2.3 健檢 → `watchlist_quote.no_data=true`,側欄灰顯「無資料」 |
| 試撮 | §2.1 雙保險過濾;不進明細/江波圖/聚合 |
| 漲跌停空側 | §2.1 空字串跳過 → §3 OrderBook 顯示「—」;basis 計算容 None |
| 斷線/重啟 | §2.3 generation listener + §2.4 status 推播 + 自癒交接 |
| 除權息 | 昨收基準 = ReferencePrice(§2.1 StockMeta),不自算 |
| 30 上限/重複加檔 | §2.5 驗證(重複 = 冪等 200) |

## 6. 測試策略

- 純函數層(models/state/svg geometry)單元測試為主力:位移命名對映、去重、試撮過濾、分鐘聚合、VWAP、內外盤判定、payoff-style geometry。
- 訂閱池 refcount:注入 fake source(`*_for_test` 慣例)驗 0→1/last-out/失敗回滾。
- 交接:歷史+live 混合序列去重(TXO 測試同款形狀)。
- routes:pytest + fake engine;watchlist 持久化 round-trip。
- 前端:vitest svg lib 純函數 + hooks(mock WS);RTL 元件冒煙。
- 盤中真實驗證:SC-2~7 截圖(Phase 6);降級路徑見 brainstorm SC 表。

## 7. Known Risks

- R1 TradeStatus 值域未實測:丟棄只用時間窗,旗標僅 warning 觀測(r2-F5);13:25–13:30 實測收斂後才升級。殘留風險 = 時間窗外若有非正規撮合型態(處置股分盤)混入聚合,靠觀測 log 發現。
- R2 側欄自選不回補歷史(只吃 live):中途開啟時側欄總量/漲跌正確(REALTIME snapshot 帶當日累積),但點進主圖才有完整圖;可接受。
- R3 期交所對映表格式變動:refresh CLI 失敗保留舊檔 + SecurityName 交叉核對 warning 兜底。
- R4 個股期 HOT 月轉倉語意(HOT 自動指到熱門月)假設與台指期同;首次盤中驗證。
- R5 個股盤後/休市 subscribe 是否必回 snapshot 未實測(07-20 snapshot 實證是期貨):健檢已限交易時段(§2.3),今日收盤後補 probe 收斂;SC-2 降級路徑若證實不成立,改用「回補模式畫上一交易日」為唯一降級。
- R6 過期 UTC 窗的訂閱跨日後是否仍推播未實測(r3-F1):rollover 已設計為不依賴它(階段一重掛在先);盤前 probe 可順帶收斂,結果補進 §0。
