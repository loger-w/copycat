# 架構債盤點(2026-08-24)

**性質**:唯讀盤點,不動任何 code。行號基準 = `e48314a5`(master,2026-08-24);引用格式
`檔案:行號`,日後行號漂移以符號名重找。

## 0. 緣起與使用方式

- 08-24 user 提「前後端都要抽象化 / 共用模組 / 系統設計 / 系統模式」走 `/refactor`。
  Why gate 第一輪拍板 = **(d) 沒有具體被卡住** → 依鐵則(refactor 沒理由就是 churn、
  一次 20+ 檔大爆炸禁止、不為「未來可能」加 abstraction)**不開 refactor 分支**,改做本盤點。
- 「系統模式」拍板指 **(i) 後端每個市場面一支 engine 的統一骨架** + **(iii) 前端三座梯收成
  一份**;兩條寫細(§2、§3),其餘寫概要(§4)。
- **取用時機**:下次任何 `/feat` `/mod` `/bug` 撞到某條的「觸發條件」時,直接拿該條的
  半徑 / 覆蓋 / 步數開工;沒撞到就不動。每條都標了觸發條件,避免拿本檔當 churn 的理由。

## 1. 總覽

| # | 候選 | 規模(證據) | 性質 | 觸發條件 | 詳見 |
|---|---|---|---|---|---|
| A | 後端 engine 家族無共同骨架 | 6 支 engine 共 4,040 行;5 個 `*Source(Protocol)` 對同一概念 3–4 種簽名 | 🔵,半徑最大 | 要加第 7 支市場面 engine(權證 Phase 2)或第 4 次修同一種 bug 跨 engine 抄修 | §2 |
| B | `server/app.py` god-file | 1,8xx 行;33 條 route 全在 `create_app` 內;`lifespan` 單函式 542–1068 行 | 🔵,拆 router / boot 模組 | 找 endpoint 翻不到、或 route 測試要 mock 整個 lifespan | §4.B |
| C | 前端三座梯 | `PriceLadder` 469 / `FuturesLadder` 514 / `StkfutLadder` 348;container 內約 350–400 行同構 | 🔵,有 `IntradayChartCore` 前例 | 第四座梯(權證)要出現、或 `clickPrice`/`marketOrder` 要改一次三處 | §3 |
| D | `StockIntradayChart.tsx` 1,518 行 | 只 7 個 hook 呼叫,肥在 JSX;`IntradayChartCore` 就定義在此檔 :914 | 🔵,拆 renderer;J1 mode 四態分歧已記 next-time | 動 core 任一 mode 打壞另一 mode(已發生過:08-24 J1) | §4.D |
| E | `localStorage` 45 處散落 14 檔 | **已出貨 PR #106**(`lib/storage.ts`) | — | — | §4.E(勾銷) |
| F | `WsStatus` 7 份同值型別 | `useCapital/useCorrelation/useFuturesStream/useIndexStream/useRiver/useStockStream/useTxoSnapshot` 各宣告一次 | 🔵 微,順手批 | 下次動任一 stream hook | §4.F |
| G | backtest `fade_*` 家族 | `fade_cells.py` 1,824 行;registry / evaluator factory 已記 next-time 08-0x | 🔵,研究碼不影響看盤 | 下次動 fade 回測 | §4.G |
| H | 每個 Source Protocol 活著兩份 fake | engine-seam 各檔自刻 `FakeSource` + `tests/helpers/fake_sources.py` 共用四支;只 index 一份 | 🔵 測試層 | 做 A 之前**必先**收成一份(否則骨架改動要改兩套 fake) | §2.4 |

**已經共用、不要再抽的**(避免重工):前端 WS 重連層(8 支 hook 全走
`lib/ws-reconnect.ts::connectWithRetry`)、閃電武裝狀態機(`useFlashArm` + `flash-arm.ts`)、
`ArmRow` / `MarketOrderButtons` / `qty-quick.ts` / `settleFlashSend`、後端 `_boot()` 兩段式
啟動樣板(`app.py:232-279`)、分時圖 `IntradayChartCore` 三 mode。

## 2. (i) 後端 engine 家族:統一 lifecycle 骨架

### 2.1 六支生命週期對照(壓縮版)

| 步驟 | TXO `EngineRuntime` | `StockEngine` | `IndexEngine` | `FuturesEngine` | `CorrelationEngine` | `BreadthEngine` |
|---|---|---|---|---|---|---|
| 啟動 | `start` :173-181,`activate(首檔)` | `start` :351-366,起 4 條 task | `start` :216-231,起 3 條 task | `start` :149-161,**最後**才掛 on_reconnect | `start` :130-144 | `start` :249-258,零網路 IO |
| 每 tick | `_consume` 佇列 :356-373 | `_handle_quote` :973-1120(含 rollover 快路徑) | `_handle_quote` :329-351 | `_handle_quote` :413-461 | `_handle_quote` :242-264(**pull 型**,取樣在 `tick_once`) | 無 tick;10s `_run_cycle` :376-394 |
| 換日 | 無日期概念,有 handover :222-336 | **兩段式** stage1 :733-751 / stage2 :885-917(首筆新日 tick 觸發) | **兩段式** `_rollover_loop` :436-472 / `_swap_day` :478-494(poll 或推播觸發) | **無**(design :11 out of scope) | 無 | 單段 `_apply` 三分支 :530-547 |
| 自癒 | `_maybe_self_heal` 三判準 :381-417 | `_retry_subscribe_loop` :779-857(對帳**動態**名單)+ `_handle_reconnect` :959-971 | watchdog :501-508 + minutes 落後換 window_variant :509-540 | leaf fallback :331-361 + `_handle_reconnect` :395-411 | `_resub_loop` :159-198(對帳**固定** pending;自承照抄 futures) | 指數退避 :587-601 |
| 回補 | handover 三次重試 :241-334 | 單工 worker queue :1209-1370 | 同步 `fetch_day_minutes` :249-261 | passthrough :312-327 | `_backfill_river` single-flight :324-411 | 無;`_compute_streaks_loop` :664-706 另類 |
| 廣播節流單位 | **per-consumer** diff :141-169 | 只 `watchlist_quote` 1s 合併 :1444-1463;tick/book 不節流 | engine 級 dirty flag :498-554 | **per-product** timer 0.1s :463-502 | 每秒**無條件** :277-301 | 每輪成敗皆廣播 :393-394 |
| 關閉 | :183-190 | :368-387 | :233-247 | :224-257 | :209-232 | :260-264 |
| 併發原語 | `_handover_running` bool | **唯一** `asyncio.Lock`(`_pool_lock` :307)+ `_generation` | 無;`_pending_date` 旗標 | `_resub_epoch` 世代 | `_backfill_inflight` bool | task.done() |

### 2.2 Source Protocol 分歧(同概念、不同簽名)

| 概念 | 出現的簽名 |
|---|---|
| 訂閱一檔 | `subscribe(series: SeriesInfo, on_tick)`(TXO)/ `subscribe_symbol(code: str)`(Stock/Index/Futures)/ `subscribe_raw(symbol)`(Corr)/ `subscribe_leaf(product, ym)`(Futures 另一支) |
| 回補 | `fetch_backfill(series) -> list[Tick]`(TXO)/ `backfill(code) -> list[StockTick]`(Stock) |
| 當日分 K | `fetch_day_minutes(code, *, window_variant=0) -> dict[str, int]`(Index)/ `fetch_day_1k(x) -> list[tuple[int, int]]`(Futures/Corr)— 一邊 dict 一邊 list[tuple],鍵值語意也不同 |
| 全域 callback | `set_on_message(cb)` 四支相同;TXO 沒有(改在 `subscribe` 帶 per-series callback) |
| 交易日 | `set_trade_date` 只 Stock/Index 有 |
| **on_reconnect** | **不在任何 Protocol 內**;五支全用 `if hasattr(self._source, "on_reconnect")` 側門掛(`engine.py:175` / `stock_engine.py:360` / `index_engine.py:220` / `futures_engine.py:156` / `corr_engine.py:142`,已 grep 實證五處) |
| K 線歷史 | Stock 在 Protocol 內 `fetch_bars_range`;Futures 用 `getattr(source, "fetch_bars_range", None)` :288 簽名多 `session=`;Index 用 `getattr(..., "fetch_bars_range_tagged")` :421 回三元組 — 三支各自繞過 Protocol |
| Breadth | 根本不是訂閱協定:四個獨立 `Callable`(:107-110)pull HTTP |

### 2.3 真同構 vs 表面像(抽骨架前的邊界)

**真同構(可抽)**:
1. `close()` 骨架:「先 `self._loop = None` 斷 threadsafe 入口 → cancel task → `to_thread(source.close)`」五支同構,四支互相引用同一條 review A1 註解(`stock_engine.py:371` / `index_engine.py:234` / `futures_engine.py:225` / `corr_engine.py:210`)。
2. `on_reconnect` 掛載五處逐字相同(上表)。
3. `is_trading_day` / `now_fn` 注入包裝(W9):`stock_engine.py:244-249` / `index_engine.py:171-177` / `breadth_engine.py:184-188` 同措辭,但**預設值不同**(stock `weekday()<5`、index/breadth `lambda _d: True`)。
4. `_resub_loop` / `_resub_round`:`futures_engine.py:174-209` 與 `corr_engine.py:159-198` 幾乎一致(corr :122 自承照抄),差在 corr 多「重訂成功後補跑江波圖回補」。

**表面像但語意不同(抽了會錯)**:
1. **廣播節流的單位**六支不一致(per-consumer / engine-level dirty / per-product timer / 單一 message-type / 無條件)。抽共用 broadcaster 前要先拍板「節流單位是 client、engine 還是 message-type」— 這是行為決策(/mod),不是 refactor。
2. **訂閱重試**:stock 對帳動態自選名單 vs futures/corr 固定 pending 集合;docstring 互相點名不可互換(`stock_engine.py:780-785`)。
3. **兩段式 rollover** 只 stock/index 有,stage2 觸發源不同(tick vs poll/推播);futures/corr 無此概念、breadth 單段 — 抽成骨架對三支是空模板或語意不合。
4. **heal** 判準:index = minutes 落後量 + 換 window_variant;futures = per-product 零推播 grace 後補 leaf;TXO = session_key / queue_dropped。名字都叫 heal,判準無交集。
5. 三處「單項卡住 → 排 grace timer 重試 → guard 防孤兒」(`futures_engine.py:331-361` / `stock_engine.py:1232-1264` / `corr_engine.py:391-411`)結構同構但 guard 型別、上限、退避節奏各異 — 非文字複製,是獨立實作。
6. Source Protocol 的「回補」與「當日分 K」資料形狀不同,統一 Protocol 前要先決定資料形狀(牽動 route 層 payload → 前端),非純改名。

### 2.4 測試覆蓋(seam 現況)

| engine | 單元測試(直接 new engine 餵 fake) | fake 來源 | route 層(TestClient) |
|---|---|---|---|
| TXO | `test_engine.py` 32 | 檔內 `FakeQuoteSource` :37-61(**第三份**:另有 `server/verify.py::FakeTxoSource` :98-118) | 多檔 |
| Stock | `test_stock_engine.py` 154 | 檔內 `FakeSource` | `test_stock_routes.py` 等用 `helpers/fake_sources.py::FakeStockSource` :211 |
| Index | `test_index_engine.py` 40 | **共用** `FakeIndexSource` :33(唯一一份) | 同上 |
| Futures | `test_futures_engine.py` 57 | 檔內 `FakeSource` :42-75 | `FakeFuturesSource` :124 |
| Corr | `test_corr_engine.py` 20 + `_river.py` 23 | 檔內 `_FakeSource` :27-51 | `FakeCorrSource` :185 |
| Breadth | `test_breadth_engine.py` 85 | `FakeFetch/FakeDaily/FakeMono` | `test_breadth_routes.py` |
| source 層 | `tests/live/test_tc4.py` 53 / `test_stock_source.py` 54 / `test_futures_source.py` 12 / `test_corr_source.py` 10 | — | — |

沒有任何跨 engine 共用的「生命週期測試骨架」(on_reconnect 觸發自癒 / close 收尾 task);
每支從零寫。**這是 A 動工前的第一步(H)**:先把 engine-seam fake 收成 `helpers/fake_sources.py`
一份(index 已是範本),否則骨架改動要同時改兩套 fake。

### 2.5 組裝與依賴(`app.py`)

`lifespan` :541-1047;`_boot_engines` :608-968 走共用 `_boot()` 樣板 :232-279(任一失敗只降級自己)。
建構順序即依賴(:993-997):runtime(TXO)→ stock → WatchlistService → signals(stock 在場時
`attach_signal_hub` :729)→ index(吃 `runtime.spot_millipts` :769)→ capital → futures →
**corr(必在 futures 後,吃 `futures_engine.state()` / `fetch_day_1k` :858-874)**→ breadth(刻意最後,
唯一外部 HTTP)。關機反序 :993-1047,corr 先於 futures、signals 先於 stock。
`StkfutCatalog` 用 `getattr(source, "list_stock_futures")` :659-661,也不在 Protocol 內。

### 2.6 若動工:半徑 / 步數 / 順序

- **半徑**:`copycat/server/{engine,stock_engine,index_engine,futures_engine,corr_engine}.py` +
  `live/{tc4,stock_source,futures_source,corr_source}.py` + `tests/server/test_*_engine.py` ×5 +
  `tests/helpers/fake_sources.py`。breadth **不納入**(非訂閱協定,硬套是語意不合)。
- **測試 seam**:engine 單元層(直接 new engine 餵 fake)— 五支已有 303 條在這個 seam,
  是現成的 characterization;不必另寫。
- **expand–contract 步驟草案**(每步單獨綠、單獨 commit):
  1. H:engine-seam 五份自刻 fake → `helpers/fake_sources.py` 一份(index 為範本)。純測試層。
  2. `on_reconnect` 進 Protocol(五個 Protocol 各加 `on_reconnect: Callable | None` 屬性),
     五處 `hasattr` 側門改直接賦值。expand 期兩者並存。
  3. `close()` 骨架抽 `server/engine_base.py::close_engine(loop_slot, tasks, source)` 之類的
     **函式**(不是基底類別 — 五支的 task 清單與收尾順序不同,函式注入比繼承窄)。
  4. `_resub_loop` 兩份(futures/corr)合一,stock 版**不合**(語意不同,2.3 第 2 條)。
  5. W9 注入包裝合一,預設值以參數傳(不是統一預設值 — 那是行為改動)。
  - **不在草案內**:廣播 broadcaster、rollover、heal、Protocol 資料形狀統一 — 四者都要先過
    /mod 拍板行為,見 2.3。
- **可量化改進**:`hasattr` 側門 5→0;fake 實作 9→5;`close()` 骨架 5→1;resub 2→1。

## 3. (iii) 前端三座梯:收成一份 core

### 3.1 職責對照

| 子功能 | PriceLadder(現股) | FuturesLadder(期貨) | StkfutLadder(個股期) |
|---|---|---|---|
| 檔位列渲染 | 委外 `LadderView.tsx:256-376` | **自家實作** :452-517(不走 LadderView) | 委外 LadderView |
| tick 對齊 | `buildLadder`(`stock-tick.ts:120-160`,分級 `TICK_TABLE`) | `buildFuturesLadder`(`futures-ladder.ts:170-210`,固定 1000 毫元) | 同現股 `buildLadder`(檔頭註解:個股期用現股 tick 表) |
| 點價掛單 `clickPrice` | :263-302 | :161-198 | :157-195 |
| 梯頂市價 `marketOrder` | :316-354,群益真市價 `nSpecialTradeType=1` + ROD | :203-242,**限價貼漲跌停 + IOC** | :202-245,同期貨 |
| 未成交/已成交徽章 | LadderView :310-323,`aggregateLots`(`ladder-lots.ts:70-98`) | 自家 :464-482,`splitMyLots`(`futures-ladder.ts:57-85`),不分買賣側 | LadderView,`aggregateLots` |
| 部位/均價/打平線 | 有:`positionRows`/`markMap` :140-176 → `beMarks`/`avgMarks` + `PositionBar` :90-123 | **無** | 半:純文字部位列 :341-366 印群益 `pnl_base`;不算 marks |
| 武裝 `useFlashArm` | :212-213 + effect :366-389 | :69-70 + effect :286-304,多「合約失解析自動解除」:296-299 | :89-90 + effect :254-267 |
| 數量輸入 | LadderView :206-224 | **自家 JSX** :386-411 | LadderView |
| 零股閘 `unit==="股"` | 有 :236 | 不適用(`splitMyLots` 無此參數) | **未傳** :126-130 |
| 跟隨置中 / `centerRequest` | LadderView :140-165 | 自家一半 :66,81-82,316-323,447-449;**無 `centerRequest`** | LadderView |
| 二次確認 dialog | 無(閃電武裝取代) | 只平倉 `CapitalConfirmDialog` :521-535 | 無 |

### 3.2 Props

- 三座逐字相同:`qtyState?: QtyState` / `onQtyState?` / `armCtl?: FlashArmControl`。
- 同義異名:`code`(股號)vs `product`(商品碼);`name?` vs `contractLabel?`;`book`+`last`+`meta`
  三欄 vs `state: FuturesProductState` 單物件。
- 獨有:PriceLadder `tradeKind`/`onTradeKind`;StkfutLadder `contract: StkfutSelection`(必填);
  `centerRequest` 只 Price/Stkfut 有。

### 3.3 重複段(估算)

| 段 | 三邊位置 | 差異 |
|---|---|---|
| `showHint` | :256-261 / :154-159 / :150-155 | 逐字相同 |
| `clickPrice` | :263-302 / :161-198 / :157-195 | 骨架逐字同構(touchIdle → 前置閘 → arm 檢查 → 500ms 防抖 → `settleFlashSend`);差在前置閘(現股 `daytrade_sell` / 個股期 `blocked` / 期貨無)與 payload 欄名(`stock_no`+`trade_kind` vs `tc4_symbol`+`day_trade`) |
| `marketOrder` | :316-354 / :203-242 / :202-245 | 骨架同構;差在 ROD+market vs IOC+`marketEdge()` |
| `cancelLot` + 四段 effect | :357-389 / :245-313 / :247-276 | 核心四 effect 同構;期貨 `cancelLot` 收 `seqNos: string[]` 而非 `LadderLot` |
| 武裝列 + qty + hint 容器 | LadderView :192-229 vs FuturesLadder :354-439 | 期貨把共用 `ArmRow` 包在自家重寫的容器 JSX 裡(第三份複本) |
| 檔位列 | LadderView :256-376 vs FuturesLadder :452-517 | 期貨版少 marks、單一紅方格、dimmed 判準用 `r.clickable` |
| 跟隨置中 | LadderView :140-165 vs FuturesLadder 四處 | 期貨缺 `centerRequest`/`rowRefs` 那一半 |

粗估 container 內同構 **350–400 行**;FuturesLadder 因不走 LadderView 另多約 190 行本可省。

### 3.4 資料源

三座都各自 `useCapitalOrders` / `useCapitalPositions` / `useCancelOrder`;送單:現股
`useSubmitStock` → `POST /api/capital/order/stock`(`CapitalStockOrderBody`,qty 張);期貨與個股期
**同一支** `useSubmitFuture` → `POST /api/capital/order/future`(`CapitalFutureOrderBody`,qty 口),
差在 `tc4_symbol`(HOT vs 月份 leaf `stkfutTc4Symbol`)。個股期借用**現股**分時/五檔資料流
(`RightRail.tsx:176-195`)。

### 3.5 測試覆蓋

| 檔 | 案數 | 層 |
|---|---|---|
| `PriceLadder.test.tsx` | 77 | RTL |
| `FuturesLadder.test.tsx` | 45 | RTL(無 Escape 直接案例) |
| `StkfutLadder.test.tsx` | 36 | RTL |
| `LadderView.test.tsx` | 6 | RTL 裸 prop 契約 |
| `ladder-lots.test.ts` 18 / `ladder-position.test.ts` 28 / `futures-ladder.test.ts` 33 | 79 | 純函式 |
| `useFlashArm.test.tsx` | 9 | hook |

三座 RTL 共 158 案 = 現成 characterization。無測試的子功能都是「功能本身缺席」(期貨 marks /
`centerRequest`、個股期 marks),不是覆蓋洞。

### 3.6 前例 `IntradayChartCore` 的切法(可比對)

定義在 `StockIntradayChart.tsx:914`(非獨立檔);`mode?: "stock"|"index"|"futures"` :886,兩個判別子
一處求值 :938,942;`CoreProps extends Props` :866-912 —— toggles 受控、`variant`、x 軸口徑覆寫、
疊線三元組注入、`hlines`/`fills` caller 折好傳入。**沒有具名 adapter interface**,而是「輸入一律
先折成 `StockAccum`」的資料層慣例(`indexSeriesToAccum` / `futuresBarsToAccum`)。測試分檔鎖
mode:`.test` 137 / `.variant.test` 11 / `.index.test` 20 / `.futures.test` 39 = 207 案。
注意 08-24 J1 留尾:mode 四態分歧散在五處,候選 per-mode capability 表 — 三座梯抽 core 時
**一開始就用 capability 表**,不要重蹈。

### 3.7 真同構 vs 表面像

**真同構、仍各寫一份(可抽)**:`clickPrice` / `marketOrder` / `cancelLot` / 四段 effect 骨架、
`showHint`;FuturesLadder 的容器 / 檔位列 / 跟隨置中三段可回歸 `LadderView`(補 marks 與
`centerRequest` 為可選 prop)。

**表面像但語意不同(不可直接合,要以 capability / adapter 表達)**:
1. 市價鈕:現股真市價 vs 期貨/個股期限價貼漲跌停+IOC(`flash-send.ts:66-69` 文案已分)— UI 共用,
   送單 builder 是兩件事。
2. 零股閘只現股有意義。
3. 均價/打平:現股 `positionEcon`(手續費折數+證交稅+借券費)vs 個股期刻意只印群益 `pnl_base`
   (`StkfutLadder.tsx:343-345` 註解:套現股稅費口徑是錯的)— 刻意不同源,不是少做一半。
4. 解除武裝判準粒度:`code` vs `product` vs `instrumentKey = code+contract`(:111)。
5. 期貨無 `centerRequest` 是呼叫鏈無觸發源(`RightRail.tsx:156-173` 只比對 `stockCode`),
   不是實作差異。

### 3.8 若動工:半徑 / 步數 / 順序

- **半徑**:`components/stock/{PriceLadder,StkfutLadder,LadderView}.tsx`、
  `components/futures/FuturesLadder.tsx`、`components/ladder/*`、`lib/{ladder-lots,ladder-position,
  futures-ladder,flash-send}.ts`、對應 6 個測試檔。後端零改動。
- **測試 seam**:三座 RTL(158 案)= 行為合約,一條都不改;core 抽出後三座的測試照跑即是
  「行為不變」證據。user 可在畫面上直接對照。
- **步驟草案**:
  1. FuturesLadder 回歸 `LadderView`(補 `marks?` / `centerRequest?` 可選、`dimmed` 判準以 prop 注入)。
     只動期貨一座,45 案綠。
  2. 抽 `useLadderOrders({ buildLimit, buildMarket, cancel, arm })` hook:`clickPrice` / `marketOrder`
     / `cancelLot` / 四段 effect 進 hook,三座各傳自己的 payload builder(現股 ROD+market、
     期貨 IOC+edge)。三座一次一座遷,每座自成一步。
  3. `showHint` 併入該 hook。
  4. contract:三座只剩 props 折疊 + builder + 各自獨有段(現股 tradeKind、期貨平倉、個股期部位列)。
  - **不在草案內**:統一 `code`/`product` 命名(同義異名但語意粒度不同,改了是 mod)、
    補期貨 marks / `centerRequest`(新功能)、零股閘推廣到個股期(行為改動)。
- **可量化改進**:同構行數 350–400 → ~0;FuturesLadder 514 → 約 300;第四座梯(權證)成本
  = 一個 builder + 獨有段。

## 4. 概要條

### 4.B `server/app.py`

33 條 route 全在 `create_app` 內(:1072-1794);`lifespan` :542-1068 單函式 526 行(`_boot_engines`
:608-968 佔大半);另有 `_default_*_source` ×5、`_market_payload`、`_session_date`/`_today`/`_now`
時鐘工廠。route 已依面分群(txo / stock / signals / stkfut / index / market / breadth / corr / river /
ws),自然切點 = 每群一個 `APIRouter` 檔 + `request.app.state` 取 engine 的 `_stock()`/`_index()`
等 getter 移到共用 deps 模組;`_boot_engines` 拆成每 engine 一支 `boot_xxx(app, calendar)`。
測試 seam = route 層 TestClient(既有)。觸發:找 endpoint 翻不到、或加第 34 條 route 時。
半徑只 `app.py` + 新檔,行為零改。

### 4.D `StockIntradayChart.tsx`

1,518 行只 7 個 hook,肥在 JSX 與 `IntradayChartCore` 同檔;`stock-intraday-svg.ts` 847 行是
renderer 純函式。切點 = `IntradayChartCore` 移獨立檔 + J1 的 capability 表。J1/J2 已在
`next-time.md` 08-24 節,動 core 時一併。測試 207 案分四檔已鎖三 mode。

### 4.E `localStorage` 45 處 14 檔 — **已出貨(PR #106,2026-08-25 R9a `mod/storage-consolidation`)**

新出口 `frontend/src/lib/storage.ts`(讀拋退預設 / 寫拋不炸;grep 裸 `localStorage.` 判準 0 要維持)。
本條勾銷,不再是候選;原 `next-time.md` 08-21 R10 條同步已刪。

### 4.F `WsStatus` 7 份

七支 hook 各宣告 `export type WsStatus = "connecting" | "open" | "closed"`,`types.ts` 另一份。
順手批:全部改 `import type { WsStatus } from "@/types"`,原 export 保留 re-export 一輪再刪。
`useFlashArm.ts:16` 從 `useCapital` import,是唯一跨檔消費者。

### 4.G backtest `fade_*`

`fade_cells.py` 1,824 行;`next-time.md` 已記:cell >4 抽 registry、evaluator 四段 if-elif 抽
factory、兩份 markdown 表 builder 第三份出現才抽。研究碼,不進看盤 blast radius。

## 5. 建議順序(真的被卡住時)

1. **F**(WsStatus)— 順手批,任何前端 PR 可帶。
2. **H → A 的步驟 1–3**(fake 收一份 / on_reconnect 進 Protocol / close 骨架)— 三步都是零行為改動
   且有 303 條 engine-seam 測試保護;A 的其餘步驟等權證 engine 真的要寫時再開。
3. **C**(三座梯)— 第四座梯或 `clickPrice` 要三處齊改時開;有 158 案保護、畫面可對照。
4. **B**(app.py)— 加 route 翻不到時開。
5. **D**(分時圖)— 與 J1 一起,下次動 core 任一 mode 時開。
6. **E** 走 /mod;**G** 下次動 fade。

**沒被卡住就不動**:本檔存在的目的是讓下次開工不用重新調研,不是開工的理由。
