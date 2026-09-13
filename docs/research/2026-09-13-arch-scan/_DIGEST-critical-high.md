# 校正後 critical / high findings 全文(49 條)

## [CRITICAL] B11-03 · 回測與實盤是兩套完全獨立的實作,零共用程式碼、零 parity fixture
- 區塊: B11-backtest-fade — 回測 fade 家族(批次計算,最明確的 numpy/polars 候選)
- 位置: copycat/backtest/ vs copycat/live/signal_state.py + copycat/server/signal_policy.py | 類別: architecture | 熱路徑: False | 工作量: XL
- 驗證: **CONFIRMED**

**驗證理由**
三條 grep 我全部重跑,結果一致:`from copycat.backtest` 在 copycat/ 下只命中 cli.py 的 11 行;`grep backtest copycat/live/ copycat/server/` **零命中**;`copycat/live/signal_state.py` 855 行,含 `_eval_cdp`(382)/`_eval_surge`(514)/`_eval_pullback`(556)/`_eval_volume`(637)/`_eval_sweep`(686)/`_eval_limit_tick`(783,他漏列這支)。成本模型的部分**他還低估了** —— 不是三份而是**四份**:`backtest/fade_simulate.py:81 _round_trip_cost`、`backtest/simulate.py:81 _round_trip_cost`(tday 另一份,多 overnight_tax)、`frontend/src/lib/ladder-position.ts`、群益實扣。而且兩邊「折數」的**慣例相反**且數值不一致(詳見 missed M3)。

**校正後影響**
正確性 / 架構債,**不在效能軸上**(on_hot_path 標 false 是對的)。對「要下實單」這個目標,這是全報告最重要的一條;但它不該進效能改造批,混批會讓 golden 驗證同時要顧向量化與語意兩個變因。

**證據**
```
$ grep -rn "from copycat.backtest" copycat/ --include=*.py | grep -v "^copycat/backtest/"
copycat/cli.py:204,277,278,293,294,308,309,323,324,338,339   ← 只有 CLI

$ grep -rn "backtest" copycat/live/ copycat/server/ --include=*.py
(零命中)
```

**原建議修法**
抽出 strategy kernel 層:輸入 = 欄狀 bar/tick 陣列 + frozen params,輸出 = (entry_idx, exit_idx, exit_reason, pnl);回測批次餵歷史、實盤逐 tick 餵增量版。最低限度(不動架構):新增 replay parity gate —— 同一天的 tick jsonl(data/signals/YYYYMMDD.jsonl,實盤真相源)與 1K(回測路徑)各跑一次同組進場條件,斷言事件集合對稱差 ≤ 白名單;並把 capital/store.py 的真實 fills 成交價 vs entry = trig.close − slippage_ticks × tick_size 做分佈對照,用實測校準寫死的 slippage_ticks(現為 1 / 2)。專案已有 copycat/replay/ + `copycat validate` golden gate 可延伸。

**修法可行性查核**
「抽 strategy kernel」是 XL 且會同時碰 CLAUDE.md §4 的訊號列 notify 欄、政策列形狀、掃單簇 golden 等多條契約 —— 他自己也說「不建議與效能重構同批做」,這個判斷正確。**低成本半邊反而最該先做**:(a) 用 `capital/store.py` 的真實 fills 成交價對照 `entry = trig.close − slippage_ticks × tick_size` 校準寫死的 slippage(現為 1 / 2),這是純離線對帳、零契約風險;(b) 先補一條**四份成本模型的跨語言 parity 測試**(照 CLAUDE.md §4 既有 `test_avg_source_parity_with_frontend` 的形狀:後端直讀 TS 字面),成本 S、立刻擋住 M3 那種靜默漂移。`copycat/replay/` 與 `copycat validate` 確實存在可延伸。

**風險**
最大一項,會同時觸碰 CLAUDE.md §4 的訊號列 notify 欄、政策列形狀、掃單簇 golden fixture 等多條契約。不建議與效能重構同批做。但若目標是「要下實單」,這是最高優先的架構債 —— 效能快 10 倍也救不了算錯的邊。

---

## [CRITICAL] B11-09 · 全庫零平行化 —— 17 臂 / 4,660 combo / P² 對全是完美 embarrassingly parallel
- 區塊: B11-backtest-fade — 回測 fade 家族(批次計算,最明確的 numpy/polars 候選)
- 位置: copycat/backtest/fade_pipeline.py:674-688(全庫 grep 零命中) | 類別: concurrency | 熱路徑: True | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
`grep -rn "multiprocessing|concurrent.futures|ProcessPool|ThreadPool|joblib" copycat/` **零命中**,逐字複現。fade_pipeline.py:674-688 的 `for arm in ALL_ARMS: for params in arm.anchor_params:` 屬實,17 個 job(3+3+3+3+1+1+3)也對,且共用的 samples / daily / cfg 確實唯讀。這是全報告在效能軸上唯一我認為 severity critical 站得住的一條。

**校正後影響**
以我實測的成本模型(非 wf 路徑今日資料 ≈ 13 h / 17 臂),8 核 6x → 約 2 小時。**零數值風險**(每臂結果彼此獨立、byte-identical),不需要任何演算法改寫,stdlib 即可 —— ROI 遠高於 numpy/numba 路線。應該排第一個做。

**證據**
```
$ grep -rn "multiprocessing|concurrent.futures|ProcessPool|ThreadPool|joblib" copycat/
(零命中)

# fade_pipeline.py:674
for arm in ALL_ARMS:
    for params in arm.anchor_params:
        result = run_fade_arm(data_dir, out_dir, cfg, arm, params, default_window,
                              samples, daily, mkt_daily_rows, is_anchor=True)
        all_results.append(result)
```

**原建議修法**
concurrent.futures.ProcessPoolExecutor(stdlib,零新相依)。Windows 專屬約束:spawn 下子行程要重新 import 並 pickle 參數 —— samples(5,586 個 frozen dataclass,~5 MB)可 pickle,但 bars(955 MB)絕對不能。正確做法:worker 只收 (arm_name, param_id, data_dir, cfg),自己從 memmap/npz 載 bars(需先做 B11-07/B11-08)。ArmSpec 含 callable,只傳 arm.name 由 worker 查表。建議把 job 切到 combo 層級而非臂層級(17 不整除 8,尾巴會浪費)。

**修法可行性查核**
可行,但有兩處要更正。(a) **「ArmSpec 含 callable,不宜整個 pickle」是錯的**:`find_trigger_pullback` 等都是 module-level def,dataclass 持有它們在 spawn 下以限定名 pickle 完全正常。真正的 spawn 阻擋物是**記憶體**(每 worker 自己的 bars ~1 GB),不是 callable。(b) **「必須先做 B11-07/B11-08,否則每個 worker 重讀 21,254 個 JSON」也過慮**:每 worker 只需重讀它那一臂的 5,586 檔 = 5,586 × 636µs = **3.6 秒**,對一個 46 分鐘的臂是 0.13% —— 讀檔完全不是前置條件,**記憶體才是**(所以真正的前置是 B11-05 + missed M2 的 2.5 GB,以及 B11-08)。(c) 他對的部分:logging 在 spawn 不繼承 handler 要接 QueueHandler、結果順序要 executor.map 保序、atomic_write_text 不可多行程寫同檔 —— 三條都正確。(d) 「切到 combo 層級而非臂層級」的建議很好,理由比他寫的更強:實測各臂 n_tradeable 差 7.7 倍(out/fade_round1 內 467 vs 3,595),負載不均比 17/8 餘數嚴重得多。

**風險**
logging 在 spawn 下不繼承 handler,現有 logger.info 進度輸出會消失 → 要接 QueueHandler。結果順序必須穩定(all_results 進報告排序)→ 用 executor.map 保序或回傳帶 index 再 sort。atomic_write_text 不要多行程同時寫同一檔。

---

## [CRITICAL] F1-02 · App 是六條流的共同 setState 落點,且上游沒有任何 memo 邊界
- 區塊: F1-stream-hotpath — 前端:即時資料流熱路徑(WS → state → render)
- 位置: frontend/src/App.tsx:154-183 | 類別: architecture | 熱路徑: True | 工作量: L
- 驗證: **CONFIRMED**

**驗證理由**
`App.tsx:152-183` 逐字查核:useTradingCalendar / useIndexStream / useBreadth / useCapitalStream / useSignalAlerts / useStockStream / useFuturesStream 連續掛載,全部 deps `[]`;`:172-177` 的自承註解一字不差。App 無上游 memo 邊界、四個 panel 用 `hidden={tab !== …}`(`:338/:349/:371/:398`)屬實。**兩處要校正**:(a)只有 txo 與 index 恆掛(`visited` 初值 `index: true, txo: true`),stock/futures/corr 走 `{visited.x ? … : null}` 才 mount——「四棵 hidden 子樹」只有在使用者造訪過才成立;(b)190–200/s 這個和其實**低估**了:掃描自己的表把 `book` 記成「逐則(活躍股數次/秒)」卻沒追到產生點——`stock_engine.py:1359 if code == self._main: self._publish({"type": "book", …})` 在 `_handle_quote` 尾端、**每則 TC4 quote 都發、無節流無去重**,對活躍主圖可能是全部訊息裡最高頻的一條(見 missed M1)。

**校正後影響**
維持 critical。盤中 App commit 率 = watchlist(30–120)+ book(未節流,活躍股 5–30)+ futures(≤30)+ ticks(≤10)+ index/signal/status,合計約 80–200/s,每一則都重建 App 的整棵 element tree。

**證據**
```
App.tsx:154-183 連續掛 useIndexStream / useBreadth / useCapitalStream / useSignalAlerts / useStockStream / useFuturesStream。App.tsx:172-177 註解自承:「watchlist_quote 的 setState 現在落在 App 層 → 每秒一批側欄報價會重繪整棵樹。判定可接受:…(b) App 層本來就會因 useIndexStream 每則指數推播重繪…若日後量測到掉幀,先做的是讓 useStockStream 吃 enabled 參數」。四個 tab panel 是 hidden 保留(App.tsx:334-438),render 照跑。
```

**原建議修法**
把高頻資料從 React state 移到 module 級外部 store,元件以 per-code selector 訂閱 —— 本 repo 已有四處 useSyncExternalStore 先例(useCapital.ts:81 / useChartToggles.ts:137 / useSignalSound.ts:43 / fee-discount.ts:68),不是新範式。新建 `lib/quote-store.ts`(就地寫 + 只通知變動的 code)+ `useQuote(code)` hook;WatchlistRow / GroupCard 各自訂閱 → 一檔報價變只重繪那一列/那一張卡,App 完全不動。約 80 行自寫 store 即可,不必引 zustand/valtio。

**修法可行性查核**
方向正確,但「約 80 行自寫 store」過於樂觀。四處 `useSyncExternalStore` 先例查核屬實(useCapital.ts:81 / useChartToggles.ts:137 / useSignalSound.ts:43 / fee-discount.ts:68),**但四處全是低頻設定型 store**(wsStatus / toggle / 音效 / 折數),per-code 150 Hz 的細粒度 store 在本 repo 是新東西。三個實作暗礁 finding 沒提:① `WatchlistSidebar.tsx:802 avg: groupAvgPct(g.codes, quotes)` 需要整份 map,per-code 訂閱救不了群組表頭,要另做 derived store;② `useGroupLiveAccums` 以 `quotesRef` 播種(:61)是刻意的「不進 deps」設計,搬 store 時這條時序保證要原樣保留;③ getSnapshot 必須對「沒變的 code」回同一個物件參照,否則 useSyncExternalStore 會無限重繪。effort L 合理,實際落在 150–250 行 + 測試改寫。

**風險**
最大風險是「兩份真相」:必須讓 store 成為唯一持有者、useStockStream 回傳的 watchlist 欄位同時退役,否則就是 §4 那種兩邊各漂各的失效樣態。既有 App.memo.test.tsx(計次 + 內容斷言)是護欄,要沿用並加嚴。不動任何 §4 wire 契約。

---

## [HIGH] B01-01 · 同一則訊息被五條 session 各自完整解碼並各自跨執行緒交接,四次是純浪費
- 區塊: B01-tc4-ingress — TC4/ZMQ 行情入口(最熱路徑)
- 位置: copycat/live/tc4.py:1239-1241(SUBSCRIBE "")、tc4.py:1226-1253、live/models.py:16-19、live/aggregate.py:46-48 | 類別: architecture | 熱路徑: True | 工作量: L
- 驗證: **CONFIRMED**

**驗證理由**
前提三重獨立佐證,不是推論:(1) `copycat/live/models.py:16-19` 逐字「TXO runtime 的 ZMQ SUB 訂 `""`,會收到同 process 其他引擎訂的所有期貨推播」;(2) `copycat/live/aggregate.py:46-48` 同義;(3) 掃描 agent 沒引的最強一條 —— `docs/research/2026-07-20-txo-live-verification.md:114` 真環境實證「TC4 SubPort 推播不分 session:任一 session 訂的 symbol,所有 SubPort listener(空 topic filter)都收得到」,以及 `.claude/skills/tc4-market-facts/SKILL.md:62`「所有 session 收得到所有 symbol」。所以 risk 裡「建議先加一行 log 印 sub_port 做一次確認」是多餘的,這件事 2026-07-20 已經驗過。

程式路徑逐字查核:`tc4.py:1239-1241` `sock.setsockopt_string(zmq.SUBSCRIBE, "")` 屬實;`tc4.py:1245` `raw = (sock.recv()[:-1]).decode("utf-8")`、`1250` `self.handle_raw(raw)` 屬實;四個子類 `handle_raw` 全部是「`_realtime_msg` → 無條件 `_on_message(quote)`」(`stock_source.py:925-936`、`futures_source.py:222-228`、`corr_source.py:164-169`),沒有任何 symbol 早退。

我用 py-spy dump 對跑著的 prod(pid 20776,`-m copycat.server`,started 2026-09-11T09:05)直接驗過執行緒盤點:23 條 Python thread = **5× ThreadProcess + 5× _listen_loop + 5× _heal_loop** + 5 asyncio executor + capital-com + discord + MainThread,而且五條 `_listen_loop` **全部停在 `copycat\live\tc4.py:1245`**(就是 recv 那一行)。區塊地圖的 15 執行緒宣稱逐字成立。

**校正後影響**
量級要下修約 20%,但比例宣稱站得住。我在本機(Python 3.13.13 / Windows 11 / ProactorEventLoop)以 876 byte 真實形狀電文重測:listener decode+find+json.loads **6.31 µs**(掃描說 6.48–7.67,吻合)、`_note_push` **0.53 µs**(說 0.734)、KeepAlive decode+re.search **1.10 µs**(說 1.78)、call_soon_threadsafe **7.3–8.2 µs**(說 8.112,吻合)、`parse_stock_realtime` **19.8–23.6 µs**(說 29.8,**高估約 30–50%**)、`parse_realtime`(TXO)**2.05 µs**(說 3.16)。

重算每則行程總成本 ≈ 31.6(decode×5)+ 2.7(note_push×5)+ 5.5(KeepAlive×5)+ 32–40(交接×4~5)+ ~4(loop 端四次空派發)+ 2~20(真 parse,一條)≈ **97–105 µs/則**(掃描說 124)。其中四條「不關我的事」的 session 付掉 ≈ 62–68 µs = **約 65%**(掃描說 69%,吻合)。

**頻率是整份報告最弱的一環**:掃描的「日均 ~200 則/s、開盤 1500+/s」是推估。`dropped_foreign_ticks=3,089,555` 屬實(`docs/superpowers/specs/2026-08-19-browser-crash-scan-handoff.md:44`),但那是**兩次 rollover 之間**的計數不是日累計 —— `ChainAggregator.reset()` 會 `self.totals = Totals()`,而 `_maybe_self_heal` 每次 rollover 都 reset(09-11 那份 log 有兩次:15:00 與 05:00)。我對跑著的 server 抓 `/api/txo/snapshot` 得 `dropped_foreign_ticks=4111`(週末 20 小時,全球休市,合理)。所以真實盤中速率**未證實**。按 200/s 算 = 2% 單核;按 1500/s 算 = 15% 單核。這是「值得做但不是燒起來」的量級,`critical` 應降 `high`。

**證據**
```
# tc4.py:1239-1241 —— 五條 session 的 listener 逐字同形\nsock = ctx.socket(zmq.SUB)\nsock.connect(f"tcp://127.0.0.1:{self._sub_port}")\nsock.setsockopt_string(zmq.SUBSCRIBE, "")\n\n# live/models.py:16-19(repo 自己的註解,不是我的推論)\n#: **不可放寬成 `"TC.F."`**:TXO runtime 的 ZMQ SUB 訂 `""`,會收到同 process 其他引擎訂的\n#: 所有期貨推播 —— 個股期(`TC.F.TWF.DHF.HOT`)、海外腿(`TC.F.CME.YM.HOT` 等)…\n\n# docs/research/2026-08-19-browser-crash-scan.md:41 —— 規模實測\n實測 dropped_foreign_ticks 309 萬 vs 真 TXO tick 2300
```

**原建議修法**
改成**一條 reader thread**:只負責 recv → 解碼一次 → 依 symbol 查路由表分派給對應 engine,並每 N 則或每 1 ms 做**一次**批次 call_soon_threadsafe(見 B01-02)。`_note_push` 改成只餵「有訂這個 symbol」的 session。KeepAlive 的 PING 也由這條 reader 代管(B01-05),五條 KeepAlive 執行緒與其 zmq.Context 直接不起。不需要任何新相依。

**修法可行性查核**
方向對、可行、不碰任何 CLAUDE.md §4 跨檔契約(全在 wire 之前),`handle_raw(raw: str)` 要留薄轉接也對(tests/ 底下 29 處引用,分佈在 test_tc4 / test_stock_source / test_futures_source / test_corr_source 四檔)。

**但 risk 段漏了會靜默炸的那一條**:`tc4.py:1249` `self._last_msg = time.monotonic()` 在 `handle_raw` **之外**、每則訊息(含 PING、含外來 tick)都更新,而 `_check_stale`(`tc4.py:1257`)以 `_STALE_THRESHOLD_SECS = 30.0` 判斷「TC4 整條死了」。單 reader 若只把「自己訂的 symbol」分派回各 session,五條 session 的 `_last_msg` 就得**在 reader 端每則無條件推進**,否則 TXO 夜間、corr 週末這種本來就沒有自家推播的 session 會每 30 秒判一次 stale → 進 `_check_stale` 重連迴圈(而 `_check_stale` 會清空並重掛全部訂閱)。risk 只列了 `_last_push` / `_sub_at` / `_heal_*`。

第二個沒提的:PING 的歸屬(見 B01-05)。第三個小的:`_note_push` 只餵自家 symbol 是安全的 —— `_heal_tick`(`tc4.py:706-722`)確實只讀 `subs` 裡的鍵,查核過。

**風險**
前提是五條 session 的 SubPort 相同 —— 跨 session 可見性已被兩段註解 + 309 萬 foreign ticks 實證,但**建議先在 `_ensure_connected` 加一行 log 印 sub_port 做一次確認**(TC4 若改成 per-session port,單 reader 會靜默只收一條流)。每條 session 的 `_last_push`/`_sub_at`/`_heal_*` 記帳必須由 reader 分派後照舊呼叫,漏掉 = 自癒 watchdog 誤判零推播、整批 UNSUB→SUB churn 且零錯誤訊號。`handle_raw(raw: str)` 是四個子類的覆寫點與數十處測試的注入點,必須保留成薄轉接層。**不動任何 CLAUDE.md §4 跨檔契約**(全在 wire 之前)。

---

## [HIGH] B01-02 · call_soon_threadsafe 每則 8.1 µs(Windows 自喚醒 socket write)且被 5 倍放大
- 區塊: B01-tc4-ingress — TC4/ZMQ 行情入口(最熱路徑)
- 位置: copycat/server/stock_engine.py:1147-1150(engine.py:361、futures_engine.py:562、index_engine.py:417、corr_engine.py:259 同形) | 類別: concurrency | 熱路徑: True | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
五個呼叫點逐字查對全中:`stock_engine.py:1147-1150`、`engine.py:361`(是 `on_tick` 不是 `_on_raw_threadsafe`,形狀同)、`futures_engine.py:562`、`index_engine.py:417`、`corr_engine.py:259`。`server/__main__.py` 的 uvicorn.run 未指定 loop,py-spy 直接顯示 MainThread 在 `asyncio\windows_events.py:775 _poll` → **ProactorEventLoop** 屬實。

我獨立重測:單 producer thread `call_soon_threadsafe` = **7.27–8.18 µs/call**,與掃描的 8.112 µs 吻合。這確實是本區塊單一動作最貴的一項(比 decode 的 6.31 µs 還貴)。

**校正後影響**
兩處要修正:

(1)**不是每則都 ×5**。TXO 那一條有閘:`tc4.py:1222` 的 `parse_realtime` 對「無成交(qty 空或 0)」回 None(`models.py:104-107`,只有 `SPOT_PREFIX` 台指期例外),所以純簿更新訊息不會走到 `engine.on_tick`。實際是 **4 條無條件 + 1 條有條件**。

(2)**「單 producer 吞吐上限 123,000 msg/s」會誤導成容量問題**。我用 5 條 producer thread 重測:producer 端每 call 漲到 15.6 µs(爭鎖),但**端到端聚合 3.15 µs/則 ≈ 317,000 交接/s**。以 1500 則/s × 5 = 7500 交接/s 算,只用掉容量的 2.4% —— 這不是吞吐瓶頸,是**純 CPU / GIL 佔用**。按 1500 則/s 算 ≈ 60 ms/s 純交接 ≈ 6% 單核。severity 維持 high(它是單點最貴),但不要用「逼近吞吐上限」當論據。

**證據**
```
def _on_raw_threadsafe(self, quote: dict) -> None:\n    loop = self._loop\n    if loop is not None:\n        loop.call_soon_threadsafe(self._handle_quote, quote)
```

**原建議修法**
批次化:reader thread 用 collections.deque(append 在 GIL 下原子)累積,配一個 `_scheduled` 旗標,只在旗標為 False 時發一次 `call_soon_threadsafe(self._drain)`;loop 端 `_drain` 一次 popleft 掃完整批。批量 20 則時交接成本從 8.1 µs/則降到約 0.4 µs/則,延遲代價 ≤ 一次 loop 週轉(實測 p50 1.8 µs)。

**修法可行性查核**
可行且收益實測驚人:我照 fix 寫的 deque + `_scheduled` 旗標版本測得 **0.040 µs/call**(對 8.1 µs 是 200×)。FIFO 保序的要求抓得對(`stock_engine._handle_quote` 的 rollover stage1/stage2 快路徑吃先後次序)。不動 wire 形狀、不動 `seq` 兩口徑、不動 §4「個股逐筆 = ticks 打包」契約 —— 這些判斷都成立,ingress 批次確實在 `_flush_ticks` 之前。

補一點掃描沒說的:**若先做 B01-01,producer 就只剩一條 thread**,deque + 旗標是最單純的安全形狀;若不做 B01-01 而先做 B01-02,是五條 deque 五個旗標,一樣安全(`deque.append` 與旗標寫在 GIL 下原子),但省的只是交接、decode 仍然五份 —— 所以掃描「先 01 再 02」的排序是對的,雖然 02 可以獨立先落地。

**風險**
`stock_engine._flush_ticks` 已在 loop 端做 0.1 s 的 `ticks` 打包(CLAUDE.md §4「個股逐筆 = ticks 打包訊息」契約),ingress 批次在它**之前**,不改 wire 形狀、不動 `seq` 兩口徑。但 `_handle_quote` 內的 rollover 快路徑(stage1/stage2)依賴同一則的先後次序,批次必須嚴格 FIFO 保序,不得改用 set/dict 去重。

---

## [HIGH] B01-03 · _taipei_time 每 tick 一次 datetime.strptime,佔個股 parse 的 34%
- 區塊: B01-tc4-ingress — TC4/ZMQ 行情入口(最熱路徑)
- 位置: copycat/live/stock_models.py:89-95 | 類別: algorithmic | 熱路徑: True | 工作量: S
- 驗證: **CONFIRMED**

**驗證理由**
`copycat/live/stock_models.py:89-95` 逐字如引用,`_TAIPEI_OFFSET = _dt.timedelta(hours=8)` 在 :24。

我不但重測還**自己把手刻版寫出來驗等值**:現況 `_taipei_time` = **7.48–7.69 µs**,手刻整數切片版 = **0.517 µs**。等值驗證跑了 4000 組隨機 (年 2020–2030 / 月 1–12 / 日 1–28 / 時分秒 / 6 位 frac) 加上月末年末閏日邊界(20260131 / 20261231 / 20240229 / 20230228 / 20261130 × UTC 時 15/16/17/23/00,涵蓋跨午夜分支),**mismatches = 0**。所以掃描「已本機驗過逐字等值」的宣稱我獨立重現了。

**校正後影響**
絕對數字下修、相對結論不變,而且**這仍是 stock parse 內單點 CP 值最高的一條**:7.2 µs / 19.8 µs ≈ **36%**(掃描算 34%,吻合;它的 10.205 → 1.477 我測到 7.69 → 0.52,幅度更大)。

**但頻率宣稱要加閘,掃描沒講**:`_taipei_time` 在 `parse_stock_realtime` 裡是在 `if price is None or qty is None or qty <= 0: return None, book, meta` **之後**才呼叫(stock_models.py:228 附近)—— 也就是**只有帶成交的訊息才跑**,純簿更新整條跳過。我實測:有成交 23.6 µs vs 純簿更新 13.6 µs,差的 10 µs 就是 `_taipei_time` + `StockTick` 建構 + `_best_limit_price`。所以「每 tick」要讀成「每**成交**」,而個股 REALTIME 裡簿更新佔多少比例本專案沒量過 —— 分母比 B01-04 小。

**證據**
```
def _taipei_time(precise_utc: str, date_utc: str) -> tuple[str, str]:\n    s = precise_utc.zfill(12)\n    hh, mm, ss, frac = int(s[:2]), int(s[2:4]), int(s[4:6]), s[6:9]\n    base = _dt.datetime.strptime(date_utc, "%Y%m%d")\n    local = base + _dt.timedelta(hours=hh, minutes=mm, seconds=ss) + _TAIPEI_OFFSET\n    return f"{local:%H:%M:%S}.{frac}", f"{local:%Y-%m-%d}"
```

**原建議修法**
改成純字串/整數運算:hh = int(s[:2]) + 8,只有 hh >= 24 才走 `_dt.date(...) + timedelta(days=1)`(台股日盤永遠不走,個股期夜盤會走)。日期字串用 f"{date[0:4]}-{date[4:6]}-{date[6:8]}" 直接切。`stock_source.py:288 _taipei_dt_key` 同款問題但在回補路徑(離線),優先度低。

**修法可行性查核**
可行,而且不需要任何新相依、不碰跨檔契約的**值**。risk 段抓得準:`tick.time` / `tick.trade_date` 是 `is_trial_window`、rollover stage2 的 `tick.trade_date > self._trade_date`、以及 §4「個股頁即時末根的分鐘鍵 = accum 起點分 +1」的上游,characterization 先行是對的。

兩點補強:(a) 跨午夜分支在**台股日盤永遠走不到**(UTC 16:00 之後才會 hh ≥ 24),真正會走的是個股期夜盤 / 海外腿,所以 property 測試要**刻意造** UTC ≥ 16:00 的輸入,不能只用真實日盤樣本;(b) `parse_futures_realtime = parse_stock_realtime`(`futures_models.py:35` 就是同一顆函式),改這裡期貨面也一起吃到,characterization 母體要含期貨。`stock_source.py:288 _taipei_dt_key` 同款但在回補路徑,優先度低 —— 這個判斷對。

**風險**
`tick.time` / `tick.trade_date` 是整條個股鏈的語意骨幹(試撮窗判定 is_trial_window、rollover stage2 的 `tick.trade_date > self._trade_date`、前端分鐘鍵與 CLAUDE.md §4「個股頁即時末根的分鐘鍵」契約的上游)。必須以 tests/live/test_stock_models.py 做 characterization,再補一支跨午夜/跨月/跨年的 property 對照測試。不改任何跨檔契約的**值**,只改算法。

---

## [HIGH] B01-06 · 整條行情入口依賴一個 gitignored 的第三方檔案,靠 sys.path.insert 在 runtime 載入,且內含已知毒鎖
- 區塊: B01-tc4-ingress — TC4/ZMQ 行情入口(最熱路徑)
- 位置: copycat/live/tc4.py:452-462;spikes/TCPY/tcoreapi_mq.py(全檔);.gitignore:9 | 類別: architecture | 熱路徑: False | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
逐條驗過:`git check-ignore -v spikes/TCPY/tcoreapi_mq.py` → `.gitignore:9:spikes/TCPY/`;`tc4.py:457-462` 的 `sys.path.insert` + `from tcoreapi_mq import QuoteAPI` 逐字如引用;wrapper 全檔每支方法都是 `self.lock.acquire()` … `self.lock.release()` **無 try/finally**(`Connect` :15-29、`Logout` :51-56、`QueryInstrumentInfo` :58-66、`QueryAllInstrumentInfo` :71-79、`Pong` :82-90);`ThreadProcess` 只 `except zmq.ZMQError`。

**repo 自己已經把後果寫下來了,掃描沒引**:`tc4.py:137-162 close_worst_secs()` 的「不計的段」逐字寫「wrapper 的 `ThreadProcess` 只 catch ZMQError,decode 類例外殺掉執行緒時 socket 永不關 → `term()` 無界」。這是 in-repo 佐證,比掃描的第一性原理論證強。

**校正後影響**
維持 high,而且我找到一條**掃描漏掉、會讓它更嚴重**的事實:這份 vendored 檔**已經被本專案改過了** —— `KeepAliveHelper.__init__` 自持 `self._ctx = zmq.Context()`(原版沒有)、`threading.Thread(..., daemon=True)`、`Close()` 用 `_ctx.term()` 強制中斷卡住的 recv、`Disconnect()` 上方那段 2026-07-06 中文註解(「5 支抓取腳本因此掛了數小時未退出」)。也就是說它不是「第三方原始碼」,是**本專案自己寫的、住在版控外的程式碼**。任何人照 GitHub TOUCHANCE/TCPY 重裝一次,這些修正全部靜默回滾,失效樣態是孤兒 process 與關機卡死。

`on_hot_path: false` 標對了,但它 gate 住 B01-02(部分)/ B01-05 / B01-15 / B01-16 的落地空間,排序上應該非常前面。

**證據**
```
# tc4.py:457-462\nsys.path.insert(\n    0, str(Path(__file__).resolve().parent.parent.parent / "spikes" / "TCPY")\n)\nfrom tcoreapi_mq import QuoteAPI  # type: ignore[import-untyped]\napi = QuoteAPI(TC4_APPID, TC4_SKEY)\n\n$ git check-ignore -v spikes/TCPY/tcoreapi_mq.py\n.gitignore:9:spikes/TCPY/\tspikes/TCPY/tcoreapi_mq.py\n\n# tcoreapi_mq.py:83-90 —— 每支方法都是這個形狀,無 try/finally\ndef Pong(self, sessionKey, id = ""):\n    self.lock.acquire()\n    ...\n    message = self.socket.recv()[:-1]\n    data = json.loads(message)\n    self.lock.release()
```

**原建議修法**
fork 成 `copycat/live/tc4_transport.py` 進版控,只保留 QuoteAPI 需要的那幾支,全部補 try/finally,ThreadProcess 改 `except Exception` + logger.exception + 計數,PING 判定改 bytes。刪掉 `sys.path.insert` 整段。

**修法可行性查核**
**fix 的關鍵判斷我實證了,而且比掃描說的更樂觀**:grep `copycat/live/*.py` 對 wrapper 的全部觸點只有 `api.context`(tc4.py:466-468)、`api.socket`(:570-571、:1163)、`api.lock`(:514-520、:562-575)、`api.Connect`(:470)、`api.Disconnect`(:516)。`_req` 的註解(:548-553)「一律不直呼 wrapper,REQ 全走這裡」屬實 —— `SubQuote` / `GetHistory` / `SubHistory` / `QueryAllInstrumentInfo` **一次都沒被呼叫**。

所以 fork 表面積 = `TCoreZMQ.__init__` + `Connect` + `CreatePingPong` + `Disconnect` + `Pong` + `KeepAliveHelper` ≈ **60 行**。但要注意 `Connect()` 內部會 `CreatePingPong()` 起 KeepAlive(:27-28),fork 不能只搬 socket 那半。

risk 段說「補 try/finally 會讓毒鎖路徑消失,`lock_timeout_secs=12.0` 取捨(tc4.py:366-374)與 `close_worst_secs` 推導要同步改寫,而後者是 §4 三方同源契約」—— 這一條完全成立,`tests/server/test_shutdown_budget.py` 有 run.ps1 字面 parity + UTF-8 BOM 斷言,是硬 gate。建議:**先 fork 進版控、行為逐字不變**(純 🔵),把 try/finally 與 `except Exception` 當**第二筆**(🔴)分開走,否則一次改動同時動行為與契約,characterization 沒得對照。

**風險**
是行為改動,要走完整 characterization。好消息:`_req` 目前**刻意不呼叫 wrapper 方法**(tc4.py:548-553 有明文理由),只用 api.socket / api.lock / api.Connect / api.Disconnect,fork 的表面積比看起來小很多。補 try/finally 會讓「毒鎖」這條路徑消失,`lock_timeout_secs=12.0` 的取捨註解(tc4.py:366-374)與 close_worst_secs 的推導要同步改寫,而後者是 CLAUDE.md §4 三方同源契約。

---

## [HIGH] B01-12 · handle_raw 在 _listen_loop 的 try 之外 —— 任何例外 = listener 執行緒靜默死亡 = 整條 session 零推播
- 區塊: B01-tc4-ingress — TC4/ZMQ 行情入口(最熱路徑)
- 位置: copycat/live/tc4.py:1244-1250 | 類別: architecture | 熱路徑: True | 工作量: S
- 驗證: **CONFIRMED**

**驗證理由**
`tc4.py:1244-1250` 逐字查對,分毫不差:
```
1244:            try:
1245:                raw = (sock.recv()[:-1]).decode("utf-8")
1246:            except zmq.ZMQError:
1247:                self._check_stale()
1248:                continue
1249:            self._last_msg = time.monotonic()
1250:            self.handle_raw(raw)
```
`handle_raw` 在 try **之外**成立;`.decode("utf-8")` 雖在 try 內但 `except` 只抓 `zmq.ZMQError`,`UnicodeDecodeError` 一樣逃得出去 —— 兩點都對。

**這不是理論風險,repo 有事故紀錄**:`tc4.py:798-800`(`_note_push` 內)逐字「…而 handle_raw 在 `_listen_loop` 的 try 之外 —— KeyError 逃出去 = listener thread 死、整條 session 零推播(pr-145 F-03)」。也就是說已經被撞過一次,當時的修法是**在呼叫端繞開**(一次取值不裸索引),沒有補上守門。

py-spy 在 prod 確認五條 listener 全部正常停在 1245,現在是活的。

**校正後影響**
效能影響 = 0(掃描自己也這麼說,誠實)。可用性影響:失效樣態是**整條 session 零推播、畫面停住、零錯誤訊號**,而且兩個 watchdog 都救不到 —— `_heal_tick` 判的是「TC4 沒推」(這裡是「我們沒在收」)、`_check_stale` 只從死掉的迴圈內部被呼叫。這兩點我對著 `tc4.py:706-722` 與 `:1246-1257` 核過,成立。

**我把 severity 從 medium 升到 high**:這是一個要走向實單的系統裡唯一一條「已經發生過、修法只繞了呼叫端、守門至今沒補、失效完全無聲」的路徑,而 effort 是 S。以「錯誤的改造決策代價很高」的標準看,它比 B01-04 / B01-07 / B01-11 加起來都該先做。

**證據**
```
try:\n    raw = (sock.recv()[:-1]).decode("utf-8")\nexcept zmq.ZMQError:\n    self._check_stale()\n    continue\nself._last_msg = time.monotonic()\nself.handle_raw(raw)              # ← try 之外\n\n# tc4.py:798-800 —— repo 自己記了一次撞上這個的事故\n# 一次取值不裸索引:_unsub(別的執行緒)會在中間 pop 同一鍵,而 handle_raw 在 _listen_loop\n# 的 try 之外 —— KeyError 逃出去 = listener thread 死、整條 session 零推播(pr-145 F-03)
```

**原建議修法**
handle_raw 包 try/except Exception + logger.exception + 錯誤計數器(不是純 log 吞掉:計數器讓 healer 看得到);`_start_listener` 保留 thread 物件,由 healer 每輪檢查 `self._listener.is_alive()`,死掉就重起 + 告警。decode 移進同一個 try。

**修法可行性查核**
修法正確且有**in-repo 先例可以直接照抄**,掃描沒引:`_heal_loop`(tc4.py:648-653)已經是完全同形的守門 ——
```
except Exception:  # noqa: BLE001 - watchdog 邊界:漏接一次 = 自癒從此消失
    logger.exception("TC4 自癒 watchdog 巡檢例外(續行)")
```
連理由都一模一樣(「它守的正是『零推播且零錯誤訊號』那條路」)。所以這不是新引進一個 broad-except,是把已經存在的慣例補到對稱的另一條 thread 上 —— 這是最省事的辯護,比掃描的第一性原理論證有力得多。

對鐵則 E「不懂的 error 不要 catch / catch 後要有具體處理」的自我檢查是對的:計數器 + 續行 + healer 重起 = 具體處理,不是純 log。

補兩點:(a) `decode` 移進同一個 try 時要注意 `except zmq.ZMQError` 那一支現在是「**逾時**才走 `_check_stale`」的語意,新的 `except Exception` 不能共用那條路(decode 壞掉不該觸發重連);(b) healer 檢查 `self._listener.is_alive()` 要小心 `_start_listener` 的重入 —— `tc4.py:1185` 建好就覆寫 `self._listener`,重起邏輯得確認舊 socket / ctx 的收拾,否則修一個洩漏出另一個。

**風險**
無跨檔契約影響。要注意鐵則「不懂的 error 不要 catch」:這裡 catch 後的具體處理是「記帳 + 續行 + 讓 healer 重起」,不是靜默吞掉,符合。

---

## [HIGH] B02-01 · 下單路徑與 TC4 歷史取數共用同一個預設 ThreadPoolExecutor(20 workers)
- 區塊: B02-server-core — FastAPI server core 與 HTTP 層
- 位置: copycat/capital/client.py:885（+ 全庫 126 個 asyncio.to_thread 呼叫點） | 類別: concurrency | 熱路徑: True | 工作量: M
- 驗證: **OVERSTATED**

**驗證理由**
結構性事實全部查證屬實:`copycat/capital/client.py:885` 逐字為 `await asyncio.to_thread(self._audit, self._record(action, req))`,在 `self._cmd_q.put((com_call, fut))` 之前;全庫 grep `set_default_executor|ThreadPoolExecutor|run_in_executor` **零命中**(我自己跑過),所以 65 個 to_thread 呼叫點(不是報告說的 126;報告自己的分項加總是 63)確實全落在 loop 預設 executor。TC4 最壞 20 s 也有原始碼背書(`app.py:123-136`「兩段 deadline 各 BARS_POLL_DEADLINE = 10s … 最壞 20s」),`copycat/live/tc4.py:562` `api.lock.acquire(timeout=self._lock_timeout)`(DEFAULT_LOCK_TIMEOUT_SECS = 12.0)也讓等鎖的執行緒真的佔著 worker。**被誇大的是觸發條件**:要讓審計排隊必須 20 條 worker 全滿,而我追過所有 fan-out 點,能同時阻塞的有硬上限 —— overlay `Semaphore(4)`、`_backfill_worker` 是**單工**(`stock_engine.py:1540` 「單工 worker」,批次只是一次 prepare 之後仍 `for … await self._run_backfill_job`)、river 回補是 `for` 迴圈逐腿(`corr_engine.py:366`)、futures leaf fallback 只在 HOT 零推播時每商品一條。剩下的是 /api/stock/bars、/api/market/bars 這類「一個 HTTP 請求一條」—— 要湊到 20 需要 TC4 半死 + 使用者連開幾個分頁重整。另外報告說「_WRITE_TIMEOUT_S 的保護還沒開始計時」是對的,但延遲的上界不是無限:被佔的 worker 最多 10–20 s 就回來,所以最壞是送單多等一輪 ~20 s,不是永久卡死。

**校正後影響**
非常態:需要 TC4 半死 + ≥20 條並發阻塞工作才會發生;真發生時送單前置審計最壞多等一個 TC4 deadline(~10–20 s),前端表現為「按了沒反應」。以『下實單』的風險權重看仍值得優先處理(便宜的保險),但不是每天都在流血的 critical。

**證據**
```
# capital/client.py:884-891 —— 送單前置審計走預設 executor
        await asyncio.to_thread(self._audit, self._record(action, req))
        fut: asyncio.Future[tuple[str, int]] = self._loop.create_future()
        self._cmd_q.put((com_call, fut))
        message, code = await asyncio.wait_for(asyncio.shield(fut), timeout=_WRITE_TIMEOUT_S)

# app.py:1568-1572 —— 專案自己已經寫下的警語
        # to_thread 走 loop 預設 executor,與 daily_bars / capital close 同池且工作
        # 執行緒不可中斷 —— TC4 半死的殭屍執行緒堆積時這條會跟著排隊(review C-1);

# app.py:123-136 —— TC4 歷史單次最壞 20 s（已實測）
#: `fetch_daily_bars` 內部兩段 deadline 各 `BARS_POLL_DEADLINE` = **10s** … 最壞 **20s**

# 實測：os.cpu_count()=16 → to_thread 預設 executor max_workers = min(32, 16+4) = 20
# 全庫 grep set_default_executor / ThreadPoolExecutor → 零命中
```

**原建議修法**
新增 copycat/server/pools.py 當單一定義點，切具名 lane：tc4_pool=ThreadPoolExecutor(6, 'tc4-hist')、fileio_pool=ThreadPoolExecutor(2,'fileio')、order_pool=ThreadPoolExecutor(2,'order-audit')，呼叫端改 loop.run_in_executor(pool, fn, ...)。**第一步只搬兩處就有 80% 收益**：capital/client.py 的三個 to_thread（審計）與 signal_hub 的 jsonl 路徑移出預設池，讓預設池只剩 TC4。

**修法可行性查核**
方向對,但 effort 被高估、且不需要 B02-10 當前置。最小可行版是 **3 個呼叫點**:`capital/client.py:347 / 353 / 885` 三處 `asyncio.to_thread(self._audit, …)` 改成 `loop.run_in_executor(order_pool, …)`,其餘一律不動 —— 因為 `asyncio.to_thread` 走的就是 loop 預設 executor,只要把下單那條拉出來,預設池是不是純 TC4 都無所謂。所以 effort = S 不是 M,也推翻 B02-10 說的「要改五次」。**報告漏掉的真風險**:`concurrent.futures.ThreadPoolExecutor` 的 worker 是 non-daemon,直譯器退出時 `_python_exit` 會 join 它們,而 `shutdown(wait=False, cancel_futures=True)` **只丟得掉排隊中的**、丟不掉正在跑的 —— 一條卡死的 TC4 執行緒會讓 process 在 run.ps1 的 graceful 窗之後才被 taskkill 硬殺。新池請只放「保證會回來」的工作(審計落檔),TC4 那種不可中斷的留在預設池。關機預算契約(`shutdown_budget.run_grace_secs()`)本身不受影響,因為新池不進 TC4 lane。

**風險**
關機預算契約（CLAUDE.md §4「關機預算三方同源」run_grace_secs()=83 s、TC4_LANE_DEPTH）沒把 executor 排空納入；新增具名池要在關機路徑 shutdown(wait=False, cancel_futures=True)，並確認 tests/server/test_shutdown_budget.py 的不等式與 run.ps1 字面 parity 不破。不動任何前後端 wire 契約。

---

## [HIGH] B02-04 · corr.state() 每秒在 event loop 上燒 13 ms 的純 Python 數值迴圈
- 區塊: B02-server-core — FastAPI server core 與 HTTP 層
- 位置: copycat/server/app.py:1981-1986 / :1997（route 與 WS seed）；每秒呼叫在 corr_engine.py:223-229；算式在 copycat/live/corr_state.py:113-126 | 類別: algorithmic | 熱路徑: True | 工作量: S
- 驗證: **CONFIRMED**

**驗證理由**
這是全批唯一我親自重跑並**完全重現**的量級。`corr_state.py:113-126` 的算式逐字如報告所引(每腿 `dict(leg_series)` 1800 項 + 全掃,再每窗兩次 list comprehension 過濾);`corr_engine.py:223-226` `while True: await asyncio.sleep(self._tick_secs)` 且 `tick_secs: float = 1.0`;`configs/correlation.json` 確認 11 腿、base=TXF(→ self._legs = 10)。我的實測:**correlations() = 13.66 ms**(其中 `_paired_returns` × 10 腿 = 6.94 ms,`statistics.correlation(1800)` 單發只有 0.162 ms)。順帶一提,`corr_state.py` 檔頭自己寫的「整輪 tick 外推不到 1 ms」這句**現在是假話**(那是寫的時候腿數少、窗口未滿的數字),這是本批最值得記一筆的實錯。

**校正後影響**
盤中每秒固定 13.7 ms loop 佔用(1.37% duty)。更關鍵的是我另外查到的一件報告沒說的事:`corr_engine.py:325-327` 是 `if self._broadcast is not None: self._broadcast(self.state())` —— **沒有任何瀏覽器連著也照算**,`_broadcast` 在 boot 就綁上去了。所以這 13.7 ms 是 24 小時無條件成本,不是「有人在看才付」。

**證據**
```
# live/corr_state.py:113-126
    def correlations(self, now: float) -> dict[str, dict[str, float | int | None]]:
        for leg in self._legs:                       # 11 腿
            paired = self._paired_returns(leg, now)  # 重建 dict(1800 項) + 全掃
            for window in self._windows:             # (60, 300, 1800)
                cutoff = now - window
                xs = [rb for ts, rb, _ in paired if ts >= cutoff]   # 每窗各掃一次
                ys = [rl for ts, _, rl in paired if ts >= cutoff]   # 再掃一次
                row[f"w{window}"] = self._corr(xs, ys, self._min_samples.get(window, 0))

# corr_engine.py:223-226
    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._tick_secs)   # tick_secs = 1.0
            self.tick_once()

# 實測 config：windows=(60,300,1800) legs=11 base=TXF
# 實測：10 腿 × 3 窗 × 1800 樣本 = 12.99 ms/call
```

**原建議修法**
零相依短期版：_paired_returns 回已排序 list 後，三個窗改用 bisect.bisect_left 找 cutoff 切片（不要三次全掃）；statistics.correlation 換成一次走訪算 Σx/Σy/Σxy/Σx²/Σy² → 預估降到 2–3 ms。正解：引 numpy，序列用 np.empty(cap) ring buffer，相關係數 vectorized（1800 點約 20–50 µs，50–100×）。兩者都不做至少把 tick_once 丟 to_thread（但要先過 B02-01 的 lane 切分）。

**修法可行性查核**
優先序建議反過來。(1) **最便宜且零數值風險**:`WsBroadcaster` 已經有 `self._clients` 集合,加一個 client 數判斷,零訂閱時跳過 `correlations()`(`_state.push` 取樣仍要每秒做,不可跳)。這一步就把常態成本歸零。(2) 次便宜:`_paired_returns` 的 `dict(leg_series)` 其實**不需要** —— base 與 leg 兩條 deque 在 `push()` 裡是同一迴圈同時 append、同一個 ts,索引天然對齊,直接 `zip(base_series, leg_series)` 就能拿掉整個 dict 重建;再把三個窗合成一次反向走訪累加 Σx/Σy/Σxy/Σx²/Σy²。這兩步合起來估可到 2–4 ms,且**不動數值輸出**(每對 return 仍由同一組輸入算一次,沒有增量浮點漂移問題,檔頭那條「不維護增量統計量」的設計理由不被違反)。(3) bisect 那條收益有限:三個窗的過濾只佔 ~6.7 ms,`_paired_returns` 的 6.9 ms 它碰不到,所以報告估的「降到 2–3 ms」偏樂觀。(4) **numpy 不需要**:上面兩步已經吃掉大部分倍率,為了這一處破 `dependencies = []` 並多 30 MB wheel 不划算。想引 numpy 應該是回測 / breadth 那邊的獨立決策,不要拿這條當理由。

**風險**
改算式會動數值輸出，tests/ 內 corr 測試會釘住。log return 的 None 語意（常數序列 → None 而非 0/NaN）必須保留。CLAUDE.md §4「江波圖調色盤色數 ≥ 相關係數腿數」契約不受影響（那是腿數不是算式）。引 numpy 破 pyproject dependencies=[] 的 stdlib-only 哲學 —— 建議放 [live] extras 並在 CLAUDE.md 記一筆破例理由。

---

## [HIGH] B02-12 · 完全沒有 request timing / event-loop lag / metrics(實測 app.user_middleware == [])
- 區塊: B02-server-core — FastAPI server core 與 HTTP 層
- 位置: copycat/server/app.py:1266-1274（只有條件式 CORS） | 類別: observability | 熱路徑: False | 工作量: S
- 驗證: **CONFIRMED**

**驗證理由**
我自己在 runtime 驗過:`create_app(FakeTxoSource())` 之後 `app.user_middleware == []`、`APIRoute` 28 條、**28 條全部是 async def**(sync routes 空集合),只有 `/api/stock/signals/rules/{rule_id}` 沒有 response_field。`app.py:1266-1274` 確認 CORS 是唯一且條件式的 middleware。整個系統確實答不出任何一條 route 的 p50/p95。

**校正後影響**
這是本區塊**唯一應該最先做**的一條:上面每一條 finding 的量級目前都是合成推估(包括我這次的重跑),沒有它,任何改造都沒有驗收判準,也無法回答『開盤那三秒是誰卡住 loop』。成本近零、風險近零、純新增。

**證據**
```
    app = FastAPI(lifespan=lifespan)
    origin = os.environ.get("FRONTEND_ORIGIN")
    if origin:
        app.add_middleware(CORSMiddleware, allow_origins=[origin],
                           allow_methods=["*"], allow_headers=["*"])

# 實測：create_app() 之後 app.user_middleware == []（本機無 FRONTEND_ORIGIN）
# 實測框架固定開銷：/api/ready 0.405 ms/req、/api/calendar 0.473 ms/req（含 httpx client）
```

**原建議修法**
新增 copycat/server/timing.py：純 ASGI class middleware（**不要用 BaseHTTPMiddleware**，那個會多包一層 anyio task group 反而變慢）記 per-route perf_counter，加 /api/metrics 吐 count/p50/p95/max。另加一條 event-loop lag 探針背景 task（await sleep(0.05) 量實際超出量，> 20 ms 印 WARNING，成本 < 0.01% CPU）—— 這一條單獨就能抓到 B02-02 / B02-04 的每一次發作。

**修法可行性查核**
方向對,但**貼出來的實作有兩個會咬人的缺陷**。(1) `self.samples[scope.get("route_path") or scope["path"]].append(...)`:starlette/FastAPI 的 scope 沒有 `route_path` 這個鍵(路由後有的是 `scope["route"]` 與 `scope["path_params"]`),所以它會 fallback 到帶路徑參數的 `scope["path"]` —— `/api/stock/state/2330`、`/2317`… 每個股號一把鍵,再配上無上限的 `list.append`,跑一天就是一條穩定成長的記憶體洩漏。要用 `scope.get("route").path_format`(在 `await self.app(...)` **之後**讀)當鍵,樣本存固定長度 ring buffer 或直接存桶計數。(2) lag 探針的門檻要重訂:我在這台機器實測**閒置** loop 的 `asyncio.sleep(0.05)` 超出量就有 min 9.11 / p50 12.43 / p95 14.11 ms(ProactorEventLoop + Windows 預設 15.6 ms timer 精度),所以「> 20 ms 印 WARNING」會整天誤鳴,「> 50 ms」才勉強可用 —— 除非先做 missed #1。用純 ASGI class 而不是 BaseHTTPMiddleware 這點是對的。

**風險**
純新增（🟢），不進 CLAUDE.md §4 任何契約。/api/metrics 刻意與 /api/health 分開（後者的職責邊界「刻意不含引擎健康度」有明文理由）。ws.py 的 WsBroadcaster.dropped / window_dropped 也順帶接進 /api/metrics（目前只能盤後 grep「佇列滿」）。

---

## [HIGH] B04-17 · 完全沒有 per-tick 端到端延遲儀器,也沒有 event loop 阻塞探針
- 區塊: B04-stock-engine — 個股引擎:訂閱池、rollover、回補 worker
- 位置: copycat/server/ws.py:56-63(唯一的可觀測性 = dropped/window_dropped) | 類別: observability | 熱路徑: False | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
實查成立且應該**升級**。`grep perf_counter|time.monotonic copycat/server/*.py` 的命中全部與行情路徑無關:app.py 只有 boot 計時(:694/:715)與關機分段計時(:1183-1258)、engine.py:286-310 是 TXO 的 backfill_secs、index_engine 是 stale watchdog、ws.py 是丟包節流窗。行情熱路徑(stock_engine._handle_quote / stock_source.handle_raw / _flush_ticks)零計時。`/api/health`(app.py:1289-1296)docstring 明寫「刻意不含引擎健康度」,`/api/ready` 同款。唯一的可觀測性就是 `ws.dropped` / `window_dropped`(ws.py:56-62),而它只答「有沒有丟」不答「卡了多久」。

**校正後影響**
這是本區塊**唯一應該升級**的 finding,而且應該排第一。理由:本報告 20 條 finding 的每一個量級、加上我這次查核的每一個量級,全部是**離線微量測 + 推估**,沒有一個是在跑著 TC4 的 prod 上量到的 —— 而我在複查中已經發現 agent 的絕對值系統性高估 1.5–2×(parse 28.8 vs 21.97、light_snapshot 168 vs 82、group 150 檔 103 vs 54、apply_backfill 25 vs 11.3)。在這種誤差下做 XL 級改造決策(B04-06/B04-11/B04-13)是把 user 的錢押在沒對過帳的數字上。對「要下實單、速度夠快夠順暢」這個目標,先裝儀器再改造是唯一正確的順序。

**證據**
```
#: 累計丟掉的訊息數(所有 client 合計)。唯讀給測試 / 診斷;不重置。
self.dropped = 0
self.window_dropped = 0
# 全庫無 loop-lag / tick-latency 探針;/api/health 刻意不含引擎健康度
```

**原建議修法**
(1) 加 loop-lag 探針常駐 task(sleep 0.05 s 量實際延遲,>50 ms 印 WARNING,env 開關 prod 預設關);(2) 在 stock_source.handle_raw 記 perf_counter 進 quote,在 _flush_ticks 出口算 p50/p95/p99 每分鐘印一行;(3) 導入 py-spy 做唯讀取樣 profile(不改 code,可對跑著的 prod server dump)

**修法可行性查核**
三條建議都可行,優先序我會調成:① **py-spy 先做**(唯讀、不改 code、可對跑著的 prod attach,盤中 09:00-09:02 與 10:30 各錄 120 s)—— 這條零風險零 effort,應該在任何 code 改動之前做完;② loop-lag 探針(`asyncio.sleep(0.05)` 迴圈量實際延遲,>50 ms WARNING)—— 一支背景 task,env 開關,是唯一能直接回答「B04-04 的 60 s 尖峰有沒有真的打到使用者」的儀器;③ per-tick 延遲 p50/p95/p99 最後做(要在 handle_raw 塞 perf_counter,risk 段擔心的「quote dict 多一鍵影響 parse」是多慮 —— parse 只 get 具名欄,不迭代 —— 但它確實會動到 `_note_push` 的指紋與 `_seen` 路徑,要小心)。risk 段「/api/health 刻意不含引擎健康度是既有決定,不要順手塞進去」正確。

**風險**
(1)(2) 都會在熱路徑加成本 —— perf_counter 0.05 µs 可忽略,但 quote dict 多一個鍵會影響 parse 的 dict.get 行為(不會,parse 只 get 具名欄)。探針必須可關,且 log 量要節流(否則自己變成 IO 瓶頸)。/api/health 刻意不含引擎健康度是既有決定,不要順手塞進去

---

## [HIGH] B05-03 · CorrState.correlations 每秒重算 18,000 次 math.log;docstring 效能宣稱錯 14 倍
- 區塊: B05-live-state — 即時狀態機:每 tick 的計算核心
- 位置: copycat/live/corr_state.py:82-126(錯誤宣稱在 corr_state.py:6) | 類別: algorithmic | 熱路徑: True | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
corr_state.py:91 `leg_by_ts = dict(leg_series)` 每次呼叫重建、96-107 每次全掃 base_series 逐筆 `log_return` ×2,證據逐字成立。頻率宣稱也查核通過且比它說的更硬:corr_engine.py:95 `tick_secs: float = 1.0`、224-226 `while True: await asyncio.sleep(self._tick_secs); self.tick_once()`,而 tick_once 322-323 `if self._broadcast is not None: self._broadcast(self.state())` → state() 543 `"pairs": self._state.correlations(now)` —— **state() 在 publish 之前就算完了,有沒有 WS 客戶端都照算**,且迴圈無交易時段閘(海外腿跨夜,等於全天)。本機實測(11 腿 × 1800 樣本):correlations() = **12.68 ms**、_paired_returns 單腿 833 µs ×11 = 9.2 ms(72%,其宣稱 83% 略高)、statistics.correlation(1800) = 190 µs(其宣稱 7% 偏低,實際約 17%)。腿數 11 與 configs/correlation.json 相符。

**校正後影響**
每 1 秒一次、全天不停的 ~12.7 ms event loop 同步停頓 —— 這是本區塊**最頻繁**的單次停頓(1.3% 一顆核 + 每秒一次 12.7 ms 的抖動)。對「要下實單」的系統,這比群組 batch 每 60 s 一次重要得多;排序應該在 B05-02 之上。

**證據**
```
leg_by_ts = dict(leg_series)              # corr_state.py:91,每次重建 1800 筆
for ts, base_mid in base_series:          # 每次掃 1800 筆
    rb = log_return(prev_base, base_mid)  # math.log ×2

cProfile(30 次呼叫):
  300     0.477 tot / 0.912 cum  corr_state.py:82(_paired_returns)   ← 83%
  1079400 0.171                  corr_models.py:31(log_return)
  900     0.036 / 0.078          statistics.py:1311(correlation)     ← 只有 7%

docstring 寫「statistics.correlation 對 1800 樣本實測 0.15 ms,整輪 tick 外推不到 1 ms」,實測 14.43 ms/次。
```

**原建議修法**
把 paired returns 也做成增量:維護 self._paired: dict[str, deque[(ts, rb, rl)]],push() 時只算「最新這筆與前一筆」並 append、同時按 now - max_window 逐出。correlations() 只剩按窗切片 + statistics.correlation,估 < 1 ms。順手把 docstring 的數字改對。docstring 的「整批重算讓浮點一致性恆真」論點不受損 —— 增量的是報酬序列(每筆各自獨立算出,不是累加量),correlation 仍吃整批。

**修法可行性查核**
增量化方向正確且可行,但它漏了一個會讓「增量 == 整批」測試紅的邊界:現況 `_paired_returns` 走的是**已被 `_evict` 修剪過**的 base_series,窗最舊那一筆沒有 prev 因此**不產生報酬**;增量版在 push 當下就用當時的 prev 算出那一筆並存下來,窗滑動後它仍留在 `_paired` → 增量會比整批**多一筆**邊界報酬。修時 `_paired` 的逐出界必須是 `ts <= now - max_window + sample_secs`(或等價),否則 property test 會在窗邊界隨機紅而看起來像 flake。其餘正確:跨洞不接合的容差判定(104 行 `abs((ts - prev_ts) - self._sample_secs) <= self._adjacent_tol`)逐條可搬到 push;`push` 的換場清空(68-70)要同步清 `_paired`。docstring 的「整批重算讓浮點一致性恆真」論點確實不受損(報酬是逐筆獨立算出的,不是累加量)—— 這點它判對了。不需要任何新套件;numpy 在這裡確實是負價值(它的評估正確)。

**風險**
中。_paired_returns 有「跨洞不接合」語意(abs((ts-prev_ts) - sample_secs) <= tol),增量版要逐條對齊;push 的換場清空要同步清 _paired。用既有測試 + 一條「增量 == 整批」property test 釘住。

---

## [HIGH] B06-02 · 每條規則跑全部六個狀態機,其中五個在結構上永遠發不出事件(7 規則 = 42 個狀態機/tick)
- 區塊: B06-signals — 訊號引擎:偵測、政策、推播、回填
- 位置: copycat/live/signal_state.py:311,326-331 + copycat/server/signal_hub.py:459-463,607 | 類別: architecture | 熱路徑: True | 工作量: L
- 驗證: **CONFIRMED**

**驗證理由**
核心事實成立,但「35 個死工」的框架要修正。

屬實的部分(逐字查核):
- `_make_slot`(`signal_hub.py:459-463`)確為 `detector=SignalDetector(rule_config(rule, self._cfg), ...)`、`enabled=frozenset({rule["kind"]})`,一規則一顆完整 detector。
- prod 規則數 = 7 已證實:`data/signal_rules.json` 是 `_cache_version: 1` 的 4 條 → `load_rules` 的 `if version != _CACHE_VERSION` 遷移鏈(`signal_rules.py:548-553`)補 2 張 surge_pullback 種子卡 + 1 張掃單簇種子卡 = 7。
- `311` 的 `sweep_events = self._eval_sweep(...)` 確在「首 tick 只初始化」gate(312)之前無條件跑,`enabled` 檢查確在 `754`。
- `319` 窗 append、`328` pullback、`330` limit 皆無條件。

要修正的部分:
- **`_eval_cdp` 不是死工** —— `391-393` `basis = self._basis.get(code); if not basis: return []`,而 `_distribute`(`985-988`)只對 `kind == "cdp_cross"` 的 slot 呼 `set_basis`,所以其餘 6 顆 detector 的 `_basis` 恆空、當場返回。
- **`_eval_surge`(523)與 `_eval_volume`(647)的 enabled 檢查在第一行**,對非擁有者也是當場返回。
- 所以真正無條件推進的只有 4 樣:sweep(deque 全套)、窗 append/trim、pullback 的 O(1) 判式、limit 的兩次比較。「42 個狀態機、35 個死工」是修辭,實際死工量約每顆 3.1 us。

我的實測(同機):非擁有者單顆 = 3.07–3.46 us;7 顆 prod 形 = 78.51 us;**單顆 detector / enabled 全開 = 52.52 us**(它報 79.60)。也就是單顆全開比 7 顆各開一個快 **33%**(它保守報 16%)—— 方向與結論它是對的,幅度還更大。
死工佔比隨窗長**反向**放大:窗長 1501 時 6 × 3.1 / 78.5 = 24%;窗長 61 時 7 顆合計約 20.7 us 而死工約 15 us = **72%**。多數自選股是後者,所以這條在真實負載下比它寫的更成立。
記憶體我實測 125 B/筆(它估 144 B):7 × 80 檔 × 1500 筆 = **100 MB**(它報最壞 120 MB);窗長 100 筆的常態 = **6.7 MB**(它報 ~12 MB)。數量級對。
最後一處小錯:熱路徑表裡寫「`_eval_sweep` … 實測單顆 5.20 us/tick」,對照它自己的報告 line 120 那是「**單顆 sweep_cluster detector**」的總成本,不是 `_eval_sweep` 本身;`_eval_sweep` 實際約 1–1.5 us(單顆 detector 全程才 3.07 us)。

**校正後影響**
CPU:去重後 7 顆 → 1–2 份共享狀態,tick 路從 78.5 us(窗 1501)/ 20.7 us(窗 61)降到約 10 us / 6 us。記憶體:峰值 100 MB → ~14 MB。真正的價值在**規則數的邊際成本趨零** —— MAX_RULES=30 目前是一張空頭支票(30 條規則 = 30 份完整市場狀態),去重後才名副其實。

**證據**
```
# signal_hub._make_slot:每條規則一顆 detector,enabled 恆為單一 kind
return _RuleSlot(rule=rule, detector=SignalDetector(rule_config(rule, self._cfg), now_fn=self._now_fn),
                 enabled=frozenset({rule["kind"]}) if rule["enabled"] else frozenset())
# signal_state.evaluate:掃單簇 / 窗 / pullback / limit 全部無條件推進
sweep_events = self._eval_sweep(...)          # 311 無條件(enabled 檢查遲至 754)
window.append((mono, price, tick.qty))        # 319 無條件
events.extend(self._eval_pullback(...))       # 328 無條件(enabled 檢查遲至 615)
events.extend(self._eval_limit_tick(...))     # 330 無條件(enabled 檢查在 _limit_event 835)
```

**原建議修法**
detector 拆兩層:(a) per-code 市場狀態(窗 + running sum + lookback + sweep group + prev + side),每 tick 每檔算**一次**;(b) per-rule 只做門檻比較 + cooldown/touch/latch。實務上 7 條規則只有**兩種窗長**(surge 300 / sweep lookback 60),去重率 7→2。這同時解掉 B06-01(running sum 只維護一份)與 B06-05/B06-13。

**修法可行性查核**
方向對,但它把難度低估了一層,必須在 spec 階段講清楚才不會做壞。

**per-code 狀態不是「一份」而是「每個參數 tuple 一份」**:窗長來自 per-rule `surge_window_secs`;`_lookback` 的剪裁界來自 per-rule `sweep_up_window_secs`;`_sweeps` 的簇窗來自 `sweep_cluster_window_secs`;`_side`/`_suppressed` 的 gap 來自 `cdp_rearm_ticks` + `cdp_rearm_dwell_secs`;`_pullback` 的 armed/peak 轉移吃 `surge_pct`。它寫「7 條規則只有兩種窗長,去重率 7→2」對 prod 現況成立(兩張 pullback 卡 surge_pct 相同,`_pullback` 可共用),但一旦 user 在規則視窗調出第三種窗長就退化。設計要以「參數 tuple → 狀態桶」為鍵,不是硬寫「一份」。

必守的三條:(1) design R2「狀態推進無條件、`enabled` 只 gate 事件產出」—— 停用期間 latch 照轉、重開不補發,新結構要保留;(2) 掃單簇定義被 `tests/fixtures/sweep_cluster_golden.json` 的 `expected_prefix` 集合相等釘住(CLAUDE.md §4);(3) `_make_slot` 是建 detector 的唯一入口(R5,漏帶 `now_fn` 會偷用真實時鐘),新結構不能把這個單一入口拆掉。

「要 user 拍板」它說對了 —— 這會推翻 `signal_rules.py` 開頭那句設計宣言「一條規則 = 一顆未改動的 SignalDetector … 調參數永遠只是換一份 config」。**建議順序:先做 B06-13(計量)+ B06-01 + M1(on_book latch 短路),量到真實 prod 數字之後再決定這條要不要做**;不要把 L 級重構排在沒有計量的前面。

**風險**
會改掉 signal-rules design 的核心決定(「一規則 = 一顆未改動的 detector,調參數永遠只是換一份 config」)—— 方向性抉擇,要 user 拍板。掃單簇定義被 golden fixture tests/fixtures/sweep_cluster_golden.json 釘住(expected_prefix 集合相等),重構後必須仍綠。「狀態推進無條件、enabled 只 gate 事件產出」的 design R2 語意(停用期間 latch 照轉、重開不補發)必須在新結構保留。

---

## [HIGH] B07-01 · corr 三窗 Pearson 每秒整批重算 14–19 ms,佔住 event loop;檔頭 rationale 是錯的
- 區塊: B07-other-engines — 指數/期貨/相關係數/江波圖引擎
- 位置: copycat/live/corr_state.py:82-126(呼叫點 copycat/server/corr_engine.py:320-323, 543) | 類別: algorithmic | 熱路徑: True | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
逐行對過 corr_state.py:82-126 與呼叫點 corr_engine.py:320-323 / 543,evidence 全部逐字存在:`leg_by_ts = dict(leg_series)`(L91)、`return [row for row in out if row[0] >= now - self._max_window]`(L111)、`xs = [...]` / `ys = [...]`(L121-122)。tick 節奏也成立:`_run` 是 `while True: await asyncio.sleep(self._tick_secs)` → `tick_once()`(L223-230),app.py:984-1021 確認 prod 建了真引擎(__main__.py:182 傳 DEFAULT_CORR),corr_config.DEFAULT_CONFIG 11 腿 / 10 條非 base,無任何盤別閘 → 24 小時每秒都跑。

我自己重跑(.venv Python 3.13.13,用 repo 的 DEFAULT_CONFIG 建 CorrState、餵 2000 拍):correlations() = 11.609 ms / 12.209 ms(兩次),_paired_returns ×10 = 6.528 ms,statistics.correlation(1800) = 0.179 ms,push() = 0.0027 ms。12 ms 與掃描的 14.122 ms 同量級(機器差異),**機制與量級都成立**。

檔頭 L5-7「statistics.correlation 對 1800 樣本實測 0.15 ms,整輪 tick 外推不到 1 ms」確實是錯的 —— 光是 30 次呼叫(10 腿 × 3 窗)依它自己的數字就是 4.5 ms,更別說 _paired_returns 的 6.5 ms。

**但兩處數字要打回**:(1)`self._cap = 3600`(L54)在 prod 不可達 —— `_evict`(L74-78)以 `now - max_window` 逐拍清,我的 bench 印出 `series len base: 1801`,所以「滿 cap 3600 樣本 18.791 ms」不是任何真實狀態;(2)「全天 14–19 ms、每天 27 分鐘」高估:我實測全腿 stale(週末 / 死盤)= 1.302 ms、只有 5 腿活(夜盤)= 6.633 ms,以日盤 4.75 h × 12 ms + 夜盤 14 h × 7 ms + 其餘 × 2 ms 推算 ≈ 590 s/day ≈ 10 分鐘,不是 27 分鐘。「佔本區塊 95% 以上 CPU」大致成立(corr 12 ms vs 全部 parse 約 0.6–1 ms/s → 約 92%)。

**校正後影響**
日盤穩態每秒一次、在 event loop 上**不可搶佔**地佔用 11.6–12.2 ms(夜盤約 6.6 ms、死盤 1.3 ms);全日 CPU 約 10 分鐘/天(非 27 分鐘)。對現況(人操作的看盤 + HTTP 觸發的群益下單)12 ms 抖動實務上看不見,所以不是 critical;但它確實是本區塊唯一有數量級意義的成本(≈ 90% 以上),也是「改造成自動化量化系統」時第一個必須拿掉的固定 jitter 源。

**證據**
```
# corr_state.py:91  每次呼叫把整條 deque 倒成 dict
        leg_by_ts = dict(leg_series)
# corr_state.py:111 再整份掃一次過濾
        return [row for row in out if row[0] >= now - self._max_window]
# corr_state.py:121-122 每窗各掃兩次同一份 paired
                xs = [rb for ts, rb, _ in paired if ts >= cutoff]
                ys = [rl for ts, _, rl in paired if ts >= cutoff]
# 檔頭 corr_state.py:4-7 的 rationale(錯的):
#   「statistics.correlation 對 1800 樣本實測 0.15 ms,整輪 tick 外推不到 1 ms」
```

**原建議修法**
改成滾動矩累加 + 週期 fsum 精確重播,**不需要 numpy**。每筆新配對報酬 (rb, rl) 對每個窗更新 6 個累加量 (n, Sx, Sy, Sxx, Syy, Sxy),逐出時反向扣除;r = (n·Sxy − Sx·Sy)/(√(n·Sxx − Sx²)·√(n·Syy − Sy²))。純 stdlib 原型實測:correlations() 18.791 → 0.0198 ms(950×),push() 0.0061 → 0.0419 ms,淨每秒 18.80 → 0.062 ms(300×)。檔頭「增量誤差會累積」的顧慮以每 60 s 用 math.fsum 對當前窗精確重播矩來釘死(實測重播 10 腿 × 1800 窗 = 3.834 ms,攤提 0.064 ms/s),合計 ~0.13 ms/秒(約 145×),而且「增量=整批」從靠論證升級成每分鐘機械驗證一次。序列同時換成 stdlib array('d')/array('q') ring buffer(39,600 個 tuple → 630 KB)。

**修法可行性查核**
方向對、零新相依、不碰 wire(pairs 的 {wN,nN} 形狀不變 → 不打破任何 CLAUDE.md §4 契約)。三點修正:(1)**不要只做低風險版** —— 我實作了『便宜整批』對照(zip 取代 dict、bisect 取代六趟 comp,parity 全過)只到 7.144 ms,證明非得走增量矩才到亞毫秒;(2)`correlations(now)` 的 `now` 不一定等於最後一次 push 的 ts(REST / WS seed 那兩條路),增量矩的窗界只能釘在 push 時點 → 必須與 B07-03 的「上一拍快取」綁成同一個設計,否則語意悄悄改變;(3)characterization test 至少要蓋:報酬不跨洞(L104 的相鄰容差)、時間戳逐出、全 None 腿、換場清空(push L64-67)、min_samples per-window 門檻。數值面可接受:log return 均值近 0,`n·Sxy − Sx·Sy` 的抵消不劇烈,每 60 s fsum 重播足夠。

**風險**
CorrState 是零 IO 純狀態機,pairs 的 wire 形狀 {wN, nN} 逐字不變 → 不碰任何跨檔契約。但必須完整保留兩條刻意的統計語意:「報酬不跨洞接合」(只取相鄰取樣秒且兩腿皆有中價)與「時間戳逐出而非固定長度」(event loop 漏拍時窗語意不失真)。做法:先寫 characterization test(同一串 mids 餵進去、比對 correlations() 完整 dict)再換實作。tests/live/test_corr_state.py + tests/server/test_corr_engine*.py 有既有覆蓋。

---

## [HIGH] B09-03 · stdlib urllib 不送 Accept-Encoding:所有 FinMind / MIS 回應未壓縮傳輸
- 區塊: B09-external-io — 外部 IO:FinMind / MIS / 廣度 / 盤前篩選(阻塞風險最高)
- 位置: copycat/server/breadth_fetch.py:66 + copycat/server/mis.py:44 + copycat/server/oi_levels.py:154 | 類別: blocking-io | 熱路徑: True | 工作量: S
- 驗證: **CONFIRMED**

**驗證理由**
我把報告 §9 的 open question #1(「FinMind 是否支援 gzip?B09-03 的收益全押在這上面」)**實測解決了,而且答案比報告估的更好**。零配額探測(未帶 token 的公開回應):
```
/data?dataset=TaiwanStockInfo  AE=None            status 200  CE=None  len=596776
/data?dataset=TaiwanStockInfo  AE=gzip,deflate,br status 200  CE=gzip  len= 57192
Server: uvicorn
```
→ **壓縮比 10.4×**(報告估 5.5–6.0×,偏保守)。且同一支請求的 wall time 實測 **425 ms → 266 ms**(小 payload 就已經 −37%,大 payload 只會更多)。

同時反證了「urllib 不送 Accept-Encoding」:不帶 header 那一發拿回的就是未壓縮 596 KB,CPython 沒有自己補。`breadth_fetch.py:66` `Request(url, headers={"Authorization": f"Bearer {token}"})` 逐字屬實,`oi_levels.py:151` 同款。

這是本區**唯一**證據完整、量級真實、零新相依、零回退風險的一條。

**校正後影響**
傳輸量降 ~10×:breadth snapshot ~924 MB/日 → ~92 MB;screen 21 份 + streak 10 份約 280 MB/日 → ~28 MB。更重要的是 **wall time**:screen 那 50 s 網路段與 streak 那 39 s 大部分是在拉未壓縮 bytes,壓縮後預期降到 ~10 s / ~8 s —— 這一條就吃掉 B09-01 與 B09-07 想解的同一塊,而成本是它們的 1/5。

**證據**
```
req = Request(url, headers={"Authorization": f"Bearer {token}"})   # 只有 Authorization

# CPython 3.13 urllib.request.AbstractHTTPHandler.do_request_ 原始碼(本機 inspect 確認)
# 只補 Host / Content-type / Content-length / Transfer-encoding,外加 opener 的
# addheaders = [('User-agent', 'Python-urllib/3.13')] —— 沒有 Accept-Encoding。
# HTTP 預設語意 = 不送就別壓。

# 實測壓縮比:
EOD      raw 9.36 MB → gzip 1.72 MB   ratio 5.5   (gzip.decompress 15.4 ms,不凍 loop)
snapshot raw 0.544 MB → gzip 0.091 MB  ratio 6.0
```

**原建議修法**
最小改動(零新相依,~15 行):`Request(url, headers={..., "Accept-Encoding": "gzip"})` + 依 `resp.headers.get("Content-Encoding")` 決定要不要 `gzip.decompress`。改動範圍 = breadth_fetch._get_rows 一個函式 + oi_levels 一處。正規改動:換 httpx(預設就送並透明解碼,見 B09-05)。

**修法可行性查核**
~15 行、零新相依、伺服器端已證實支援、不支援時 `Content-Encoding` 不存在就退回現況 —— 修法本身沒問題。但報告漏了**兩個實作陷阱,不補會把可重試錯誤變成炸穿**:

(1)`json.load(resp)` 吃不了 gzip 串流,必須改成 `body = resp.read()` → 判 `Content-Encoding` → `gzip.decompress(body)` → `json.loads(...)`。
(2)改完之後,**截斷的 gzip 會丟 `gzip.BadGzipFile` / `EOFError`,兩者都不在 `_get_rows` 現有的 except 元組裡**。而那個元組的 `http.client.HTTPException` 註解明寫是為了 2026-09-02「4.5MB 全市場回應截斷」實錄才加的 —— 同一個失效樣態換了個例外型別就從「重試一次」變成「炸穿整輪」。上 gzip **必須同時**把 `gzip.BadGzipFile`(是 `OSError` 子類,恰好會被現有 `OSError` 接住)與 `EOFError`(**不是** OSError,會漏)一起處理。

順序建議:與 B09-10 綁在同一筆做 —— 兩者都要把 `json.load(resp)` 拆成 read + loads,分兩次改同一行是白工。MIS 不動(非契約公開端點、payload 微小)報告說對了。

**風險**
需先確認 FinMind 支援 gzip(未驗證,探法見報告 §7.2 (a),花 1 個配額請求)。不支援時伺服器照回未壓縮、Content-Encoding 不存在 → fallback 就是現況,零回退風險。MIS 是非契約公開端點(mis.py:3 明寫「可能無預警壞」)且 payload 本來就微小 —— 建議 MIS 不要動。

---

## [HIGH] B10-01 · 送單前置審計走共享預設 executor,可被 TC4 / FinMind 執行緒無上界卡住
- 區塊: B10-capital-order — 群益 Capital 下單鏈(延遲最敏感)
- 位置: copycat/capital/client.py:884-885(另 344-347) | 類別: blocking-io | 熱路徑: True | 工作量: S
- 驗證: **OVERSTATED**

**驗證理由**
程式事實全部屬實。`client.py:884-885` 逐字為「# 前置:寫不進去 → AuditWriteError,錢沒動(to_thread 不卡 loop,review B6)」+ `await asyncio.to_thread(self._audit, self._record(action, req))`,下一行才 `self._cmd_q.put((com_call, fut))` —— 確實擋在真錢送出之前。全庫 grep 零 `set_default_executor`;`to_thread` 共 20+ 個呼叫點與它同池(engine.py:284/287 TC4 subscribe/fetch_backfill、corr_engine.py:465/469、breadth_engine.py:399/451/486/750 FinMind、app.py:1581 signals jsonl)。app.py:1570 的自承註解逐字存在。`os.cpu_count()=16` → 預設池 20 workers 正確。殭屍執行緒可超額累積也有硬證據:app.py:1507 註解「放掉的是 semaphore 名額 —— `to_thread` 的工作執行緒中斷不了」,`overlay_sem = asyncio.Semaphore(4)`(app.py:547)+ `OVERLAY_FETCH_TIMEOUT_S = 15.0` 表示 wait_for 逾時後名額釋放、執行緒還在跑;logs 裡 `daily_bars 逾時` 實際命中過(server-20260909-2248.log 10 次)、`REQ 逾時` 5 次。**但 critical 的量級站不住**:(a) 送單頻率是人手驅動 —— data/audit/capital-*.jsonl 全史 511 筆 pre/post 配對、單日最多 154 行(= 77 次寫入動作,2026-08-21);(b) 全部 logs grep `結果未知` / `寫入結果晚到` / audit grep `"late": true` / `"code": -1` **全為 0**,511 筆送單沒有任何一筆卡到逾時;(c) 我實測 `append_audit` p50 0.275 ms / p95 0.371 ms(與掃描的 0.383 ms 同量級),正常態佔整鏈 <1%(見 missed M3 的 ~70 ms 端到端估計)。

**校正後影響**
正常態零影響(0.38 ms / 每天約 77 次)。真正的價值是砍掉尾部:共享池被 TC4 半死執行緒佔滿時,前置審計會在「錢還沒動」的位置排隊,而 executor 工作執行緒不可中斷、沒有上界、HTTP 端零錯誤訊號。目前 prod 從未發生(511/511 乾淨),但目標態(自動化下單、送單頻率上升)下這是唯一能把送單延遲推到秒級以上的共享資源。定位是「便宜的尾部保險」,不是吞吐優化。

**證據**
```
# _execute_write,擋在真錢送出之前
await asyncio.to_thread(self._audit, self._record(action, req))
fut: asyncio.Future[tuple[str, int]] = self._loop.create_future()
self._cmd_q.put((com_call, fut))

# app.py:1568-1572 自承同池風險(同一個池)
# to_thread 走 loop 預設 executor,與 daily_bars / capital close 同池且工作
# 執行緒不可中斷 —— TC4 半死的殭屍執行緒堆積時這條會跟著排隊(review C-1)
```

**原建議修法**
改用專用池:client.__init__ 建 ThreadPoolExecutor(max_workers=1, thread_name_prefix="capital-audit"),_execute_write 用 loop.run_in_executor(self._audit_pool, ...)。或搭配 B10-05 直接 inline 在 loop 上同步寫(實測 persistent handle + fsync 僅 0.34 ms,比現在的 to_thread p50 還快)。兩者都保住 design §3「審計前置失敗 = 錢沒動整筆失敗」。

**修法可行性查核**
可行且便宜。專用 `ThreadPoolExecutor(max_workers=1, thread_name_prefix="capital-audit")` + `loop.run_in_executor` 零新相依、零跨語言契約。**但它列的 risk 是錯的**:`run_grace_secs()` 是 `WS_DRAIN_SECS + TC4_LANE_DEPTH*close_worst_secs() + COM_JOIN_TIMEOUT_SECS + LIFESPAN_SLACK_SECS` 的公式(實算 5 + 2*34 + 5 + 5 = 83),新池的 `shutdown(wait=True)` 不會自動進這個式子;一條 max_workers=1、工作是 0.3 ms 檔案寫入的池,關機等待是次毫秒級,不必動 `TC4_LANE_DEPTH`,`tests/server/test_shutdown_budget.py` 也不會紅。更簡單的做法見 missed M5:直接 inline 在 loop 上同步寫(0.275 ms),同時砍掉兩次 event loop yield —— 專用池與 inline 二選一,不要兩個都做。

**風險**
新池的 shutdown(wait=True) 會進 shutdown_budget.run_grace_secs() 的關機預算(現值 83 s),要同步評估 —— 該預算由 tests/server/test_shutdown_budget.py 釘住(含 run.ps1 字面 parity)。不改 lane 形狀就不必改 TC4_LANE_DEPTH。零跨語言契約影響。

---

## [HIGH] B10-10 · 整條鏈零延遲量測;審計時戳只有秒解析度
- 區塊: B10-capital-order — 群益 Capital 下單鏈(延遲最敏感)
- 位置: copycat/capital/client.py:336 | 類別: observability | 熱路徑: True | 工作量: S
- 驗證: **CONFIRMED**

**驗證理由**
`client.py:336` 逐字 `"ts": datetime.now().astimezone().isoformat(timespec="seconds")`,確實只有秒。`_log_chain_stage`(client.py:696-707)量的是回流方向(自成交回報到達起 N ms),不是送單方向 —— 屬實。`/api/health` 不含 capital 指標 —— 屬實。**而且我用它現有的資料把它自己的論點做強了**:511 組 pre/post 配對中 473 組落在同一秒、36 組跨 1 秒、1 組 2 秒、1 組 4 秒 → 粗估端到端平均 ≈ 70 ms、p99 ≈ 2 s。這個數字直接推翻了同批其他 finding 的優先序:它們提議優化的 0.25–2.6 ms 加總佔不到整鏈 5%,剩下的 ~70 ms 全在未量測的 `SendStockOrder`(bAsync=0 同步)那一段。所以『零量測』略誇(秒解析度其實給得出粗分布),但『黑盒在哪裡』判斷完全正確。

**校正後影響**
這是唯一一條應該先做的。它決定 B10-01/03/04/05/15/18/20 到底要不要做 —— 現在沒有它,那七條都是盲改。

**證據**
```
"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
```

**原建議修法**
stdlib 零相依:_execute_write 打五個 time.perf_counter_ns(),把差值(µs)寫進後置審計行 "lat_us": {gate, audit_pre, enqueue_to_com, com, audit_post, total}。com 那一段在 COM 執行緒的 _run 裡量(fn() 前後),隨結果一起回傳。盤後 jq/python 出 p50/p95/p99。

**修法可行性查核**
完全可行:`time.perf_counter_ns()` 五個打點 + 後置審計行加 `lat_us` 物件,stdlib 零相依,零跨語言契約(前端不讀審計檔)。要注意兩件它沒講清楚的:(a) COM 段量測要改 `_ComCall` 回傳型別,連帶 `tests/capital/fake_com.py` 與五個 com_call 閉包 —— 與 B10-02 的 dict 方案二選一時,選「一起改 `_ComCall`」比較划算;(b) `_on_late_result` 那條路也要帶得出分段,否則逾時案例(最需要資料的那種)反而沒數字;(c) 它自己提醒的「審計行格式改變影響離線對帳腳本」對 —— 加鍵不改既有鍵、不改鍵序,與 CLAUDE.md 記的 `backfill_policy_outcomes` byte 比對慣例同款紀律。

**風險**
低,但這是一切後續優化的前提 —— 沒有它,B10-01~08 每一條改動都是盲改。com 分段要改 _ComCall 回傳型別(與 B10-02 同一處改動,建議一起做)。

---

## [HIGH] B11-02 · 4,660 combo × 4,000 sample 的逐 combo 重跑 = 推估 5.7 小時純重算
- 區塊: B11-backtest-fade — 回測 fade 家族(批次計算,最明確的 numpy/polars 候選)
- 位置: copycat/backtest/fade_pipeline.py:549-560 | 類別: algorithmic | 熱路徑: True | 工作量: L
- 驗證: **OVERSTATED**

**驗證理由**
程式碼與網格規模屬實:fade_pipeline.py:549-560 逐字如引,`enumerate_fade_stop_combos` 我實跑回 **4,660** 組(baseline 128、TP 1,927 也都對),17 個 anchor 臂(3+3+3+3+1+1+3)也對。但兩件事推翻他的量級:(1) **這條路徑在 walk-forward 下根本跑不到** —— `run_fade_arm` 在 fade_pipeline.py 的 `if cfg.wf_test_starts:` 分支直接 `return`(早於 549 行的網格)。只有 `configs/fade_uc_round1.json` 設了 `wf_test_starts`,而**最新的 fade-search 產物 `out/fade_round1/rules_final.json` 17 臂全部帶 `wf`、`rules: []`、零 mask** —— 那一次 run 從未執行這段網格。所以 B11-02 與 B11-17(每 fold 重建 predicates)是**互斥路徑**,報告把兩者當同時成立。(2) 單次 simulate 均價錯了:他用 65µs(從 no-stop 111.5 / S4 64.8 手挑平均)。我從 4,660 組**隨機抽 40 組**跑真 bar,實測**網格平均 22.4µs** —— 因為絕大多數 combo 帶停損會提早出場,no-stop(101µs)只是 4,660 分之一。實測:4,660 × 5,031 = 23.4M calls/臂 × 22.4µs = **8.75 分鐘/臂 → 17 臂 2.5 小時**,不是 5.7 小時。

**校正後影響**
僅在非 wf 路徑成立:2.5 h / 17 臂,佔該路徑全 run 約 19%,是第 3 大成本(不是第 1)。wf 路徑為 0。

**證據**
```
for combo in all_combos:                     # 實測 4,660
    ...
    for sample, bars, trig_idx in triggered: # ~4,000
        out_r = simulate_fade_sample(bars, trig_idx, sample, combo, cfg, cfg.slippage_ticks)
```

**原建議修法**
兩層。(1) 演算法層:S4(固定 x)/ S5(目標 x)/ S3(跟蹤)的出場 bar 都是單調穿越,對 cummax(high)/cummin(low) 做一次 np.searchsorted 就能一次算出整個 x 網格的出場點;而且 s5(10 值)× t1300(2 值)是純笛卡兒積 —— 同一次掃描可同時產出 20 種組合,光這步砍掉 ~20x 重複掃描。(2) 實作層:_simulate_core 的 bars 從 list[Bar1K] 換成 numpy SoA(9 個 1-D array)+ numba.njit,逐 bar 240–430 ns → 預期 5–20 ns(~30x)。

**修法可行性查核**
演算法層可行、實作層要降溫。(a) 「S4/S5/S3 出場都是單調穿越 → 對 cummax(high)/cummin(low) 做一次 searchsorted」方向正確,但 `_simulate_core` 的出場不是單一條件取最早,而是同 bar 內 `worst = max(stop_fills + forced_fills)` 再與 target/tp/time 取 max、並用 `_REASON_RANK` 做同價 tie-break(fade_simulate.py:318-330),所以「一次掃描產出整個 x 網格」要連 tie-break 一起重現,不是純 searchsorted。(b) 「s5(10 值)× t1300(2 值)是純笛卡兒積」在 `enumerate_fade_stop_combos` 的結構上成立(2 × 10 × 233),但 t1300 會改 `t1300_consumed` 的迴圈狀態,共用一次掃描要小心 —— 可行但不是免費的 20x。(c) numba:**.venv 沒有,且會是第一個帶 LLVM 的相依**;在一個 2.5 h 的離線批次上引入它,ROI 遠低於先做 B11-09 的行程平行。(d) golden 錨點他說對了:`out/fade_cells_r4/cells_2026-07-16-round4.json`(71 KB)存在,可逐欄 float 比對。

**風險**
高。_simulate_core 是唯一模擬器,五個 CLI 全走它,語意極細(同價 tie-break _REASON_RANK、stress_guard_fill_high、鎖死凍結 bar 仍餵累計量、excluded_* 前綴)。必須先建 byte-level golden:對既有 out/fade_cells_r4/cells_*.json 逐欄 float 比對。numba 的浮點運算順序可能與 CPython 不同 → 建議 numba 版只用在純比較的停損判定,累加(cum_pv / cum_delta)保持原順序。

---

## [HIGH] B12-01 · bit_indices 吃掉 exhaustive_scan 的 63% —— 可用三個 matmul 整段消滅
- 區塊: B12-backtest-core-replay — 回測核心 + replay + 評分引擎
- 位置: copycat/backtest/search.py:81-88, 94-111, 143-168, 186-190 | 類別: algorithmic | 熱路徑: True | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
實跑重現。search.py:81-88 逐字如報告所引。用 out/tday_ga 真實資料(regime=all, train=3179, n_preds=366, popcount 平均 1628.4 —— 三個數字與報告完全一致)跑 cProfile:`67161  25.679  34.823  search.py:81(bit_indices)` / `56173966  4.650  {method 'bit_length'}` / `56238727  4.500  {method 'append'}` —— bit_length 呼叫數 56,173,966 與報告逐位相同,不是估的。tottime 佔比 25.679/40.520 = 63.4%,連 cumtime 算(bit_length + append 都在它裡面)是 34.823/40.520 = 86%。無 profiler 實跑 exhaustive_scan 19.9 s、ga_search 2.92 s/seed。唯一要校正的是絕對值:報告說「三個 regime ≈ 145 s」,我把三個 regime 都跑完實測 = all 34.5 s + momentum 29.9 s + low_base 15.5 s ≈ 80 s。方向與佔比成立,倍率被放大約 1.8x。

**校正後影響**
單次 tday-search 的搜索段實測 ~80 s(非 145 s),是這支 CLI 最大單一成本(cache 命中時全長約 120 s)。**但這是離線批次、不在實盤路徑上** —— 它買的是研究迭代速度,不是交易延遲,所以 critical 不成立。

**證據**
```
cProfile(真實 out/tday_ga 資料,3,179 train 列 / 366 謂詞):
  67161  29.765s  search.py:81(bit_indices)   ← tottime 63%
  56173966  5.406s  {method 'bit_length' of 'int'}
  56238727  5.244s  {method 'append' of 'list'}
  67161   5.887s  search.py:94(_evaluate)
無 profiler 實跑:exhaustive_scan 27.3 s、ga_search 4.2 s/seed × 5 = 21 s。謂詞 mask 平均 popcount 1,628 / 3,179 列。
```

**原建議修法**
謂詞改存 np.ndarray[bool](366 × 3,179 = 1.16 MB)。exhaustive 1-2 條件全掃改成三個 matmul:M = preds.astype(float64);ACC = (M*pw) @ M.T;WSUM = (M*w) @ M.T;RAW = (M*nz) @ M.T;EXP = np.where((RAW>=raw_min)&(WSUM>=w_min), ACC/WSUM, PENALTY+RAW)。對角線即單條件結果。4.26 億 FLOP × 3 → BLAS < 0.5 s。GA 的 _fit 改 np.logical_and.reduce + 兩個 dot ≈ 5 µs/次。numpy 放 [backtest] extras,live runtime 的 dependencies=[] 不變。

**修法可行性查核**
matmul 方案數學上正確(ACC/WSUM/RAW 三個 M·Mᵀ 對角線即單條件,off-diagonal 即兩條件 AND;_evaluate 的 raw 只數 w>0、penalty 分支都可向量化),但**報告漏掉一個更好的第一步**:把 bit_indices 換成 byte-table 展開(`mask.to_bytes(...,'little')` + 256 項預算表),我實測 3.7x–6.4x(兩組不同 mask 樣本:1.671→0.450 s / 1.069→0.168 s per 4000 次),**輸出 bit-exact、零新相依、零浮點順序改動、docs/evidence 完全不必重拍**。exhaustive_scan 19.9 s → 約 5–6 s。numpy 版(~40x)才需要付 determinism 代價。另外兩點要提醒:(a) venv 裡 numpy 目前**沒裝**(我驗過,numpy/msgspec/pyarrow/polars/orjson 全無),所以「放 [backtest] extras」是從零裝起;(b) 報告說會衝到 copycat validate 42 條 golden —— 實際上 validate.py 是**帶容差**的(_TOL_N 0.05 相對、_TOL_GAP 0.005、_TOL_AGAIN 0.01),ulp 級漂移不會讓它紅;真正會逐字紅的是 rules_final.json 與 docs/evidence 報告。這一點報告寫得比實際嚴。建議順序:byte-table(S,零風險)→ 量完再決定要不要 numpy。

**風險**
浮點加總順序改變 → design D11 determinism(同 seed byte-identical)與 docs/evidence 既有報告數字會有 1e-15 級漂移,rule_sort_key 的 tie-break 在極端 tie 下可能換序。必須先做 parity 腳本(top-200 conditions 集合 + fitness 在 1e-12 內相等),或 user 拍板允許重拍 evidence。bit_indices 的 docstring 寫明「pipeline 共用,勿另行實作」,pipeline.py:423/433 兩處呼叫端要同動。tests/backtest/test_search.py 是行為鎖。numpy 化屬行為改動,不可混進 🔵 純重構 commit。

---

## [HIGH] B12-04 · 實盤/回測不一致:engine/ 只有 replay 在用,實盤是另一份鎖板定義
- 區塊: B12-backtest-core-replay — 回測核心 + replay + 評分引擎
- 位置: copycat/engine/lock_quality.py:74-75 vs copycat/live/signal_state.py:813-818 | 類別: architecture | 熱路徑: False | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
兩邊 code 逐字核過,都對。`grep -rn copycat.engine` 全庫命中只有 engine 內部互引、replay/runner.py:14-15、以及 tests/engine 兩支 —— server/ 與 live/ 零引用,屬實。lock_quality.py:71-72 `def _at_limit(self, b): return b.close >= self._limit - self._cfg.limit_eps`(float、1 分 K 收盤價);signal_state.py:813-818 `_locked_up` 三項複合簽名(price == upper_milli 且 not ask_limit_available 且 (bids0_is_market or best_bid_limit_milli == upper_milli)),連 docstring「第三項排除『首攻吃光賣盤』」都在。兩個定義在「觸停但賣壓仍在」的 bar 上確實會給相反答案。這是本區塊唯一一條與「要拿回測結論下實單」直接相關的實質風險,而且目前**沒有任何量化數字**描述這個落差。

**校正後影響**
非效能問題,是回測效力(validity)問題。CLAUDE.md §0a 的核心資產就是鎖板品質分層(vol_after_lock_share / n_reopens / tier),而這三個欄位在回測與實盤是兩個定義下的東西。

**證據**
```
grep "from copycat.engine" 的唯一命中是 replay/runner.py:14-15,server/live 全鏈零引用。
回測:
  def _at_limit(self, b: Bar1K) -> bool:
      return b.close >= self._limit - self._cfg.limit_eps   # float、1 分 K 收盤價
實盤:
  def _locked_up(self, price: int, ctx: TickContext) -> bool:
      if ctx.upper_milli is None or price != ctx.upper_milli or ctx.ask_limit_available:
          return False
      return ctx.bids0_is_market or ctx.best_bid_limit_milli == ctx.upper_milli
```

**原建議修法**
選項 A(建議先做,零風險):在 engine/lock_quality.py docstring 與 docs/strategy.md 標註「本定義是簿深不可得下的代理,與 live _locked_up 不等價」,並用 TC4 tick(有成交當下一檔 Bid/Ask)在同一批 stock-day 上量化「bar-close 代理 vs tick 近似簽名」的一致率——這個數字是所有回測結論的信心上界。選項 B:抽 LockPredicate Protocol,回測注入 BarCloseLockPredicate、實盤注入 BookSignatureLockPredicate,狀態機轉移邏輯(_first_touch/_n_reopens/_run_start)共用一份。選項 C(不建議):把 live 改成 bar-close 判定,會丟掉 _locked_up 第三項刻意排除的「首攻吃光賣盤」誤判。

**修法可行性查核**
選項 A(docstring + docs/strategy.md 標註「bar-close 代理」,並用 TC4 tick 量化一致率)確實零風險且是正解 —— 那個一致率就是所有回測結論的信心上界,應該當成前置。選項 B(抽 LockPredicate Protocol)技術上可行但要注意:動 engine/ 會讓 copycat validate 的 golden 重拍 —— 不過 validate.py 是帶容差的(相對 5% / 0.5pp / 1pp),只要轉移邏輯不變就未必會紅,報告把這個風險寫得偏高。選項 C 正確地被標為不建議。另外動 live/signal_state.py 會踩 CLAUDE.md §4 的訊號 kind 值域與 signal_rules PARAM_SPECS golden fixture parity —— 這條 risk 寫得對。

**風險**
CLAUDE.md §0a 明載「硬限制:五檔委買賣深度不可回測(TC4 tick 僅成交當下一檔 Bid/Ask)」→ 兩份實作在資料層無法直接合併。動 live/signal_state.py 會踩 CLAUDE.md §4 的訊號列契約(kind 值域 limit_lock/limit_open 前後端同表、signal_rules.py PARAM_SPECS 與前端 signal-params.ts 的 golden fixture parity)。動 engine/ 會讓 copycat validate 的 42 條 golden 全面重拍。選項 A 零風險。

---

## [HIGH] B12-15 · 量化缺口:回測沒有成交/延遲模型,slippage_ticks 是常數
- 區塊: B12-backtest-core-replay — 回測核心 + replay + 評分引擎
- 位置: copycat/backtest/simulate.py:105-110;copycat/backtest/config.py:41-42 | 類別: quant-gap | 熱路徑: False | 工作量: L
- 驗證: **CONFIRMED**

**驗證理由**
code 描述完全正確。simulate.py:107 `entry = min(trig.close + slippage_ticks * tick_size(trig.close), limit)`;config.py:41-42 `slippage_ticks: int = 1` / `stress_slippage_ticks: int = 2`;唯一的成交可行性判定就是 :105-106 與 :109-110 兩條 `excluded_unfillable`。確實沒有委託延遲、部分成交、排隊位置、taker/maker、量對簿的衝擊。對一個要下實單的系統,這是真實的模型風險。

**校正後影響**
非效能。這與 B12-04 是同一類:它們決定「回測結論能不能拿來下單」,而本區塊其他 17 條只決定「跑多久」。若要排序整份報告,這兩條該排最前面。

**證據**
```
entry = min(trig.close + slippage_ticks * tick_size(trig.close), limit)
# config:slippage_ticks: int = 1 / stress_slippage_ticks: int = 2
唯一的成交可行性判定:
if trig.low >= limit - eps:  return TradeOutcome("excluded_unfillable", None, None)
if entry >= limit - eps and all(b.low >= limit - eps for b in post): return ...("excluded_unfillable")
沒有:委託延遲、部分成交、排隊位置、taker/maker、下單量對簿的衝擊。
```

**原建議修法**
排隊位置在現有資料下無解(CLAUDE.md §0a 五檔不可回測),但延遲與部分成交可以建模:群益 audit jsonl(data/audit/capital-YYYYMMDD.jsonl,已在寫)有真實送單→回報的往返時間,capital/reply.py 有成交回報。短期把 slippage_ticks 常數換成依觸發當下量能(max_minvol_x)分桶的查表;中期在 docs/evidence 補一份「實單成交 vs 回測假設」對照。

**修法可行性查核**
**提議的資料源有實質問題**:報告說「群益 audit jsonl 有真實送單→回報的往返時間」—— 我開了最新的 data/audit/capital-*.jsonl,`ts` 是 **秒級** ISO 字串(`"2026-09-11T09:02:14+08:00"`),而且同一筆 cancel 的 req 行與 result 行**時間戳完全相同**。以這個解析度抽不出往返延遲,除非先改 audit 的 ts 精度(那是動 capital 審計格式,另一個 blast radius)。「依觸發當下量能(max_minvol_x)分桶查表」那半是可行的,但報告自己的 risk 寫對了:動 slippage_ticks 語意 = 動 _SIM_FIELDS = 全 outcome cache 作廢 + docs/evidence 重拍,而且「必須先有真實對照資料才動,否則是用猜的換掉另一個猜的」—— 這句是全份報告裡最該被採納的一句。結論:問題成立,**建議的第一步(audit 抽延遲)不可行,要先修 audit 時間精度或改用其他來源**。

**風險**
動 slippage_ticks 語意 = 動 _SIM_FIELDS = 全 outcome cache 作廢 + docs/evidence 重拍。必須先有真實對照資料才動,否則是用猜的換掉另一個猜的。

---

## [HIGH] B13-04 · 系統完全不持久化 tick,量化系統資料層第一號缺口
- 區塊: B13-data-io — 資料層與 IO 原語(atomic write / cache / CLI)
- 位置: 全庫(copycat/live/ 與 copycat/server/ 的所有寫檔點已 grep:只有 signal_hub.py:1416、audit.py:34、breadth_engine.py:873/970 與快取類,零 tick 寫入) | 類別: architecture | 熱路徑: False | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
事實面查證通過:我 grep `copycat/live/` 與 `copycat/server/` 的所有寫檔站點,只有 `breadth_engine.py:873/970`、`screen_engine.py:445`、`signal_hub.py:1381/1416`、`__main__.py:126`(log sink)、`audit.py:34`(builtin open 形式,grep pattern 漏了但存在)—— **零 tick 寫入**,與 CLAUDE.md §5 明文一致。但因果宣稱有錯:報告說『strategy.md 的硬限制「五檔深度不可回測」正是本決定的直接產物』—— 不是。`live/stock_models.py:116` 逐字寫著「歷史 TICKS row 只有單一 `Bid`/`Ask` 欄(**不像 REALTIME 有五檔**可以…)」,而 :65-66 的 `bids/asks` 是 `L0..L4` 的完整五檔。所以歷史不可回測是 **TC4 歷史 TICKS 格式**造成的,與持不持久化無關;真正的損失是『線上 REALTIME 已經有五檔,收完就丟,所以從今天起也累積不出深度樣本』—— 結論方向不變,但理由要改對,否則會讓 user 以為錄了就能回測既有歷史。

**校正後影響**
量級估算(150 檔 × ~2,000 筆/日 × 32 B ≈ 9.6 MB/日、含五檔約 25 MB/日、一年 2.3 GB)合理,本機完全負擔得起。這是本區塊唯一一條「不做就永遠補不回來」的條目 —— 每個交易日都在單向流失。

**證據**
```
# CLAUDE.md §5:「沒有 DB:… ZMQ tick 流 in-memory 不持久化」
# CLAUDE.md §0a:「硬限制:五檔委買賣深度不可回測(TC4 tick 僅成交當下一檔 Bid/Ask)」
# 但 copycat/live/stock_models.py 盤中正在收「五檔位移歸一 / 試撮窗」—— 收完就丟
# grep 結果:live/ 與 server/ 下所有 open("a") / write_text / write_bytes 站點共 5 處,無一寫 tick
```

**原建議修法**
在 live/tc4.py 的 tick 回呼**下游**(不是回呼裡)掛 recorder:`collections.deque(maxlen=N)` + 一條 writer 執行緒,每 1–2 s 批次 flush;格式用 `struct.pack` 定長 append 到 `data/ticks/<YYYYMMDD>/<code>.bin`,或一張 sqlite3 表(WAL + 批次 commit)。**絕不可走 atomic_write_text(全檔重寫),也絕不可每筆 open/close**。政策抄已驗證的 `ws.py::WsBroadcaster.dropped`:佇列滿丟最舊 + 60 s 節流 WARNING,盤後 grep 應為 0。

**修法可行性查核**
技術方向對:deque + writer 執行緒 + `struct.pack` 定長 append 或 sqlite WAL 批次 commit;『絕不可走 atomic_write_text、絕不可每筆 open/close』是對的(atomic 12 KB 實測 0.539 ms,每筆一次會直接打死)。兩條硬要求也對:fire-and-forget 不可反壓 ZMQ 回呼、以及碰到 CLAUDE.md §4「關機預算三方同源」要同步改 `shutdown_budget.py::TC4_LANE_DEPTH`。**但這不是效能 finding,是推翻 CLAUDE.md §5 明文決定的方向性抉擇**,依 user 全域鐵則(事實自查、決策問人)必須停等拍板,不能當成一條「改造項目」逕行排入。建議先做最小版:只錄成交 tick(不含五檔)到定長 bin,證明磁碟/關機/丟包政策都穩,再談五檔。

**風險**
這是**新增**,不動既有契約。兩條硬要求:(1) 必須 fire-and-forget —— recorder 慢 / 磁碟滿絕不可反壓到 tick 回呼(回呼跑在 ZMQ 執行緒上);(2) **會碰到 CLAUDE.md §4『關機預算三方同源』**:新增的 flush 執行緒若要保證收尾落盤,就是 lifespan 多一條 lane,必須同步改 shutdown_budget.py 的 TC4_LANE_DEPTH / run_grace_secs(),否則 run.ps1 的 83 s 預算會在它還在 flush 時硬殺。或明確標為 daemon thread、放棄未 flush 的最後 1–2 s。方向性抉擇(推翻 CLAUDE.md §5 明文決定)需 user 拍板。

---

## [HIGH] F1-01 · watchlist_quote 每檔一則廣播 → App 全樹每秒重繪 150 次
- 區塊: F1-stream-hotpath — 前端:即時資料流熱路徑(WS → state → render)
- 位置: copycat/server/stock_engine.py:1827-1832 + frontend/src/hooks/useStockStream.ts:425 | 類別: render | 熱路徑: True | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
逐字查核:`copycat/server/stock_engine.py:1827` `dirty, self._dirty_watchlist = self._dirty_watchlist, set()` / `:1828` `for code in dirty:` / `:1832` `self._publish(self._quote_payload(code))` 屬實;節流值在 `:247` `throttle_secs: float = 1.0` → `:263 self._throttle = throttle_secs`(finding 寫 `:248` 差一行,不影響結論)。`copycat/server/ws.py::WsBroadcaster.publish` 無任何合併,一則 publish = 每個 client 一個 frame。前端 `frontend/src/hooks/useStockStream.ts:425` `setWatchlist((prev) => ({ ...prev, [msg.code as string]: q }));` 逐字屬實,hook 掛在 App(`App.tsx:178`)→ 每則 = 一次 App render。**但頻率宣稱要打折**:`:1348 self._dirty_watchlist.add(code)` 在 `if tick is not None and state.ingest(tick):` 之內,dirty = 「該秒真的有成交且通過去重」的自選碼,150 是上界不是穩態;盤前/盤後接近 0。另一個被誇大的是物件複製:我實測 `{...obj}` 150 鍵 = 25.2 µs,150 則/秒 = 3.75 ms/s(0.4% CPU)——真正貴的是 App 子樹,不是那份複製。側欄列數還受摺疊影響(`WatchlistSidebar.tsx:804 {isCollapsed ? null : (<ul>…)}`),摺起來的群組整批不 render。

**校正後影響**
機制成立:每則 watchlist_quote = 一次 App 全樹 element 重建 + WatchlistSidebar 展開列全部重跑 render 本體(每列約 25 個節點)。量級修正為 **30–120 則/秒(上界 150)**,而非「穩態 150」;物件複製那一項只有 ~3.8 ms/s,主成本在側欄列的 reconciliation。仍是本區單一最大的可消除浪費。

**證據**
```
後端 stock_engine.py:1827-1832 `dirty, self._dirty_watchlist = self._dirty_watchlist, set()` / `for code in dirty:` / `self._publish(self._quote_payload(code))` —— `_throttle = 1.0`(:248),自選上限 150(CLAUDE.md §4)。前端 useStockStream.ts:425 `setWatchlist((prev) => ({ ...prev, [msg.code as string]: q }));`。每則 = 一個 WS frame = 一次 App 全樹 render。
```

**原建議修法**
後端把迴圈收成一則打包(沿用 ticks 打包已驗證的形狀):`items = [self._quote_payload(c) for c in dirty if ...]` 再 `self._publish({"type":"watchlist_quotes","items":items})`。前端加 `case "watchlist_quotes"` 一次 setWatchlist 套整批。**舊 watchlist_quote 分支必須保留**(_handle_no_data 與 trial 翻轉補推是單則路徑,stock_engine.py:1355/:1802),是新增不是取代。

**修法可行性查核**
可行。`watchlist_quotes` 打包沿用 ticks 打包已驗證形狀,additive;「舊 watchlist_quote 分支必須保留」的理由查核屬實(`stock_engine.py:1357-1358` 的 recovered/meta 補推、`:1826` 試撮翻轉補推都是單則路徑)。兩點要補:(a) 這條與 F1-02 是**替代關係不是互補**——把 watchlist 搬進 module store 後,150 則/秒只會重繪 150 個獨立列,收益相同且零 wire 風險、零前後端同版部署要求;先做哪一條要拿 effort 比,不是照 finding 的「批 2 第一條」照抄。(b) 打包只降 frame 數,payload 與 JSON.parse 總量不變(而 parse 本來就不是瓶頸)。

**風險**
新增 wire 訊息型別 = CLAUDE.md §4 的 additive 跨檔契約:舊前端遇到新型別走 `default: return` 靜默丟棄 → 側欄整排停在 `-`、零錯誤訊號 → **部署必須前後端同版**(同 §4「政策列形狀」那條的部署紀律:版本落差膠囊亮起先 npm run build)。要加 parity 測試(後端 test_stock_engine.py 斷言打包形狀 + 前端 useStockStream.test.ts 斷言一則多檔)。不動 WATCHLIST_LIMIT 與 seq 兩口徑契約。

---

## [HIGH] F2-02 · EnergySub 每卡 271 個 <rect>(近全軸 1140),每 tick 全部重建
- 區塊: F2-svg-lib — 前端:SVG 繪圖計算層(純函式)
- 位置: frontend/src/components/stock/StockIntradayChart.tsx:882-892 | 類別: render | 熱路徑: True | 工作量: S
- 驗證: **CONFIRMED**

**驗證理由**
逐字核對 `StockIntradayChart.tsx:882-892` 與檔內 `:812-817` 的自述註解,引用完全屬實。觸發鏈補實:`lib/stock-accum.ts:427 const minutes = new Map(acc.minutes)` —— 每筆 tick 必造新 Map → `subEnergy` 的 dep `accum.minutes` 換 identity → 重算 → 本層全建。card 變體**確實會 render**(`:1621` 的閘只有 `index ? null :`,card 不在其中)。節點數 271 屬實(`windowedEntries` 只留窗內有資料的 key,滿窗 = 當日分鐘數)。查核中另補一條 finding 沒抓到、但讓這條更站得住的事實:`barW = Math.max(1, plotWidth(width)/(xw.end-xw.start) - 0.4)`(`:101-103`),卡片寬 ~246 → plotWidth 170 → 170/270 = 0.63,減 0.4 後被 clamp 成 **1px**,而相鄰柱間距只有 0.63px —— 271 個 1px 寬的 rect 互相重疊塞在 170px 內,卡片上根本分不出單根柱。

**校正後影響**
降一級的唯一理由是 repo 自己的量測結論:`:812-817` 明記 jsdom 滿窗一輪 ~15 ms,而「真瀏覽器的 diff 快一個量級」→ 約 1.5 ms/卡/更新,且只有**當拍收到成交**的卡才重建(不是所有 50 張)。09:00–09:05 尖峰可能 10–30 張同時 → 3–15 ms/100 ms,午後趨近零。靜態成本(50 卡 13,550 個 rect 常駐 DOM 的記憶體與 style 表)是真的、與更新率無關。稱 critical 與 repo 既有實測(『不值得為它換寫法』)直接牴觸,但它確實是節點數第一大來源、且修法便宜,high 合理。

**證據**
```
{bars.map((b) => (
  <rect key={`e-${b.x}`} data-testid="energy-bar"
        x={b.x - bw / 2} y={h - b.h} width={bw} height={b.h} className="fill-ink-muted" />
))}

// 同檔 :812-817 自己的量測紀錄:
//「memo 擋得住 hover,但擋不住報價 —— 每則 tick 讓 accum.minutes 換 identity →
//  subEnergy 重算 → 本層 1140 個 rect 全部重建;jsdom 量到滿窗一輪 ~15 ms …
//  真正安全的是 EnergySub 改單一 <path>(節點數 1140 → 1),留 next-time。」
```

**原建議修法**
改成單一 <path>:量柱是等寬矩形,最省的寫法是一條 path 配 strokeWidth={bw},d = 各分鐘的 `M x h V (h-bh)` 串接,節點 271 → 1,屬性字串總量也降一個量級。或用 `M (x-bw/2) h H (x+bw/2) V (h-bh) H (x-bw/2) Z` 串接填色版。

**修法可行性查核**
單一 `<path>` 可行且零依賴。兩點提醒:(a) 填色版 `M (x-bw/2) h H (x+bw/2) V (h-bh) H (x-bw/2) Z` 串接後 `d` 字串約 271×30 ≈ 8 KB,每 tick 重建 —— 節點省掉了,字串格式化成本(同 F2-06 的病)搬到這裡,別把它講成零成本;仍是淨賺(1 節點 vs 271 節點 + 271×~90 字元屬性)。(b) 風險段『絕對不可用總量當 memo key』**完全正確且有 repo 出處**(1K 回補可在總量不變下改寫某分鐘的量),這條不可放寬。額外建議一條 finding 沒提的更省做法:card 變體把柱降採樣到 ≤ plotWidth 個桶(每桶取 max),畫面逐像素相同(反正 0.63px 間距已經看不出來)、`energy-bar` testid 與 4 處斷言全保留、不必改成 path;page 變體再走 path。

**風險**
energy-bar 有 4 處測試斷言(2 檔)要改成 path d 的斷言。**絕對不可**用「當日總量當 memo key」的捷徑 —— next-time 明記:1K 回補可以在總量不變下改寫某一分鐘的量,那種 memo key 會讓副圖靜默停在舊值(用錯誤換效能)。

---

## [HIGH] F3-01 · 圖牆同步十字線把 mousemove 放大成 50 張卡的 re-render
- 區塊: F3-chart-components — 前端:圖表元件與重繪行為
- 位置: frontend/src/components/stock/GroupGridView.tsx:310,464-465 + components/stock/StockIntradayChart.tsx:1327-1335 + hooks/useChartToggles.ts:60 | 類別: render | 熱路徑: True | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
逐行查核全數成立。GroupGridView.tsx:310 `const [syncMin, setSyncMin] = useState<number | null>(null);`;464-465 `syncHoverMin={toggles.syncHover ? syncMin : null}` / `onHoverMinute={toggles.syncHover ? setSyncMin : NOOP_HOVER}` 確實是同一個值送進 `codes.map` 的每一張卡;useChartToggles.ts:60 `syncHover: true,` 預設開。節流那半也查了:StockIntradayChart.tsx:1047-1055 `emitHoverMinute` 只在 `emittedMinRef.current !== min` 時外報 —— 但 `minuteOf`(stock-intraday-svg.ts:452-472)是 `Math.round(((xPx - Y_AXIS_W) / plotWidth(size.width)) * (xw.end - xw.start)) + xw.start`,而 `plotWidth = width - 36 - 40`。實際卡寬:gridShape 在 ≤16 檔走 grid-cols-2/3/4,主區約 900-1200px → 卡片 ~220-290px → 扣 p-2 與 76px 軸帶後繪圖區 ~130-200px 對 271 分鐘 = 0.48-0.74 px/分鐘,「只在分鐘變化時回報」在卡片尺寸下確實近乎 no-op。掃描漏講一件加分的事實:非 hover 卡重繪時 DOM 變更是**兩處**不是一處(主圖十字線 + StockIntradayChart.tsx:1626-1641 副圖 svg 內那條垂直線,同樣畫在 EnergySub memo 之外)。但重繪成本要修正:卡片內 `g` / `subEnergy` / `vpBars` / `fillMarks` / `ChartStatic` / `EnergySub` 六個 memo 的 deps 都沒變 → **全部命中**,每卡真正重跑的只有 core body(含一個 `useStockOverlay` 的 useQuery 訂閱檢查、toggleDefs 8 個物件、allFields/fields、XAxisLabels)+ 兩層十字線 DOM,約 30-100 µs/卡而不是 0.31 ms/卡。

**校正後影響**
50 卡 × 30-100 µs ≈ 1.5-5 ms/次事件;滑鼠**移動中**約 60-125 Hz → 90-600 ms/s,量級與掃描的 120-300 ms/s 同一個數量級,成立。但兩點降級:(a) 只在游標實際在圖牆上移動時發生,閒置時零成本,不影響 tick → 畫面的資料路徑;(b) 報告把它斷言為「使用者『在圖牆上移動滑鼠時很鈍』的直接來源」—— 專案 memory 與 next-time 裡查不到任何這樣的 user 回報,那是掃描自己加的歸因,不可當拍板依據。

**證據**
```
GroupGridView.tsx:310 `const [syncMin, setSyncMin] = useState<number | null>(null);`；464-465 `syncHoverMin={toggles.syncHover ? syncMin : null}` / `onHoverMinute={toggles.syncHover ? setSyncMin : NOOP_HOVER}`(同一個值傳給每一張卡)；StockIntradayChart.tsx:1334 `emitHoverMinute(min);`；useChartToggles.ts:60 `syncHover: true`(預設開)
```

**原建議修法**
三段:(1) syncMin 從 useState 改成模組層 external store —— 沿用本專案已有的 lib/tick-stream.ts EventTarget 模式 + useSyncExternalStore,卡片各自訂閱,只有要畫十字線的卡重繪,零新相依;(2) onMove 加 requestAnimationFrame 節流(先寫 ref,rAF 內才 commit);(3) 更進一步把十字線改成不經 React —— core 內以 useRef 抓常駐 <g>,直接 setAttribute。十字線是純視覺游標,無任何跨檔契約

**修法可行性查核**
方向對,但第一步的敘述**寫錯了**:`useSyncExternalStore` 的訂閱者在 snapshot 值變時一律 re-render,50 張卡各自訂閱 syncMin 的話還是 50 次 re-render,「只有要畫十字線的卡重繪」不成立。真正省下來的是第三步 —— 把訂閱收進卡片內一個只畫十字線的 leaf 子元件(或直接 ref + setAttribute),core body 才不用重跑。注意十字線的 y 是 `g.toY(syncAgg.c)`(StockIntradayChart.tsx:1212-1214,每卡用自己的 accum 錨),leaf 仍需要 `g` 與 `accum.minutes`,不是純視覺常數。零新相依可行:lib/tick-stream.ts 已是 module-level EventTarget 薄殼,同一套模式照抄即可。守門測試指認正確(StockIntradayChart.synchover.test.tsx / GroupGridView.memo.test.tsx),不觸及 CLAUDE.md §4 任何契約。rAF 節流那一步無爭議。

**風險**
StockIntradayChart.synchover.test.tsx 與 GroupGridView.memo.test.tsx 需改判準(那兩支正是釘 memo 計次的守門)。不觸及 CLAUDE.md §4 任何契約

---

## [HIGH] F3-03 · EnergySub 以每分鐘一個 <rect> 畫量柱
- 區塊: F3-chart-components — 前端:圖表元件與重繪行為
- 位置: frontend/src/components/stock/StockIntradayChart.tsx:818-895(渲染於 882-892) | 類別: render | 熱路徑: True | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
StockIntradayChart.tsx:884-893 逐字如報告所引;`EnergyBar`(stock-intraday-svg.ts:97-102)確實只有 `{x, h}`。節點數核過:卡片變體**確實**渲染副圖(CardIntradayChart 傳 subHeight,core 在 :1624-1641 掛第二張 svg),50 卡 × 271 ≈ 13,550 個 rect 成立;再加每卡 VP 長條(buildVpBars 一價位一根,實務 30-150 根)+ 刻度/標籤,「圖牆 ~20,000 節點」是可信的。兩處要修正:(a) key 在**寬度不變時是穩定的**(x 由 minuteToX 決定),所以每次 accum 變動付的是 vdom 建立 + diff,**不是**「DOM 屬性寫入」—— 沒變的 rect React 不會碰 DOM;(b) 每卡的重建頻率 = 該卡自己的成交打包頻率(applyTick 才換 accum identity),不是一律 10 Hz × 50 卡。另外掃描引了元件 doc 的「留 next-time」卻沒引同一段的結論句「與原記載『真環境 hover 目視未見掉幀』一致,不值得為它換寫法」—— 這是專案已量測後的既有拍板,不是新發現。

**校正後影響**
圖牆情境 high(節點量級論證本身站得住);單檔頁 / 期貨 tab 降為 medium(1140 或 271 個 rect,一張圖)。絕對 ms 數未知:N047 的 ~15 ms 是 jsdom,doc 自己說真瀏覽器快一個量級 → 1140 格約 1.5 ms、271 格約 0.35 ms,乘上「有成交的卡數 × 該卡打包頻率」。

**證據**
```
`{bars.map((b) => (<rect key={`e-${b.x}`} data-testid="energy-bar" x={b.x - bw / 2} y={h - b.h} width={bw} height={b.h} className="fill-ink-muted" />))}`;元件自己的 doc(N047)已寫:「每則 tick 讓 accum.minutes 換 identity → subEnergy 重算 → 本層 1140 個 rect 全部重建 … 真正安全的是 EnergySub 改單一 <path>(節點數 1140 → 1),留 next-time」
```

**原建議修法**
量柱改單一 <path>(每根 `M x,y h w v h z`,或用 stroke-width = bw 的直線串),節點 1140 → 1,diff 降成一次字串比較。同法可套用到 buildVpBars 的水平長條與 CandleChart 的量柱

**修法可行性查核**
量柱併成單一 `<path>` 完全可行且零相依,`className="fill-ink-muted"` 原樣可用。但「同法可套用到 buildVpBars」要打折:VP 每根帶 `poc: boolean` 走不同 class(volume-profile.ts:105-107),併成一條會吃掉 POC highlight,至少要拆 poc / 非 poc 兩條 path。測試衝擊指認正確且我核過位置:StockIntradayChart.test.tsx:641 / 657 / 1510-1577、StockIntradayChart.variant.test.tsx:132 都是 `[data-testid="energy-bar"]` 的計數 / 取 width 型斷言,要改成驗 `d`。

**風險**
data-testid="energy-bar" 的計數型測試(StockIntradayChart.test.tsx、GroupGridView.geometry.test.tsx)會全紅,需改成驗 path 的 d。順帶修掉 F3-19 的 key 問題

---

## [HIGH] F4-01 · 後端 book WS 訊息零 coalesce 零去重
- 區塊: F4-ladder-highfreq — 前端:閃電梯/五檔/逐筆等高頻更新元件
- 位置: copycat/server/stock_engine.py:1359-1360 | 類別: render | 熱路徑: True | 工作量: M
- 驗證: **OVERSTATED**

**驗證理由**
**機制成立**:`copycat/server/stock_engine.py:1359-1360` 逐字為 `if code == self._main:` / `self._publish({"type": "book", "code": code, "bids": book.bids, "asks": book.asks})`,前面唯一的早退是期貨鍵夜盤那段(`_in_futures_session`),現貨主圖恆執行;`parse_stock_realtime`(live/stock_models.py:197)確實無條件回一個 StockBook。同函式的另兩路確有節流(:1341-1342 `call_later(self._tick_flush_secs=0.1, self._flush_ticks)`;:1348 + :1816 `await asyncio.sleep(self._throttle)`)。前端 `useStockStream.ts` `case "book"` 也無內容去重,逐則 `{...acc, book}` → `setAccum`。
**但三處誇大**:(a) **「把 #180 的收益整個抵銷」不成立** —— #180 壓的是「50 檔開盤每秒數百筆」(CLAUDE.md §4 逐字),book 只對 `self._main` **一檔**發,母體差 50 倍;(b) **頻率是推測值**,報告自己寫「推測熱門股開盤數十 Hz」。我翻遍 repo 只找到 `docs/research/2026-08-19-browser-crash-scan.md`「8 條 WS 實測 10 秒:futures 17.9 msg/s、**stock 3.6**」——那是 19:07 盤後、且是 dev build;`docs/next-time.md:816-818` 的 0.32–0.4 則/s 是 TXO 不是 stock。**盤中個股 book 則數/s 全 repo 零量測**;(c) **「按下單鍵有延遲的真正機制 = click 排在 long task 後面」被既有證據反駁**:`.claude/mod/group-grid-ticks/verification.md:120-121` 記載 09-03 開盤 09:01–09:03 prod build trace 93 s、「RunTask 148,274 個、**>50 ms = 0**(最大 36.7 ms)」——沒有 long task,click 最多晚 ~18-36 ms。

**校正後影響**
以我實測的單則成本推算(見 F4-02/F4-09):每則 book 觸發的整棵樹重繪約 1–1.5 ms。10 則/s ≈ 1–1.5% CPU、40 則/s ≈ 4–6%、要到 100+ 則/s 才逼近「主執行緒被佔滿」。**它是最划算的一根槓桿(改一處、上游砍掉全部下游成本),但不是已證實的 critical 瓶頸**——先量 book 則數/s 再定窗。

**證據**
```
        if code == self._main:
            self._publish({"type": "book", "code": code, "bids": book.bids, "asks": book.asks})

# 同一函式裡另外兩條都有節流:
#   tick → self._pending_ticks.append(...) ; call_later(self._tick_flush_secs=0.1, self._flush_ticks)   (:1340-1342)
#   watchlist_quote → self._dirty_watchlist.add(code) ; await asyncio.sleep(self._throttle)≈1s          (:1348, :1816)
# parse_stock_realtime 恆回一個 StockBook(live/stock_models.py:197)→ 這條是無條件執行
```

**原建議修法**
沿用同檔既有的 _tick_flush_timer 樣板:book 標 dirty → call_later(0.05~0.1)flush 一次最新簿;flush 前比對 (bids, asks) 與上次送出值,相同即不送。WS 訊息型別與欄位逐字不變,前端 case "book" 一行不改。

**修法可行性查核**
修法可行且風險低,但**建議的做法不是最好的**:報告要另起一支 `_book_flush_timer`,而更好的是**併進既有 `_flush_ticks`**(:1782)——同一顆 timer、同一個 0.1 s 窗,一次解掉「零節流」與我在 missed #2 指出的「每筆成交重繪兩次」。兩點注意:(a) `snapshot()` / `group_snapshot()` 進場會先 `_flush_ticks()`(:721 / :838),併進去後要確認 pending book 不會在快照落地**之後**才送出而把新簿蓋回舊簿(前端有 `pendingBookRef` 擋 refetch 期間,但那條路只在 refetching 為真時武裝);(b) 新 timer 要跟著 close 路徑收(`_loop is None` 早退樣板照抄即可),不影響 CLAUDE.md §4 關機預算三方同源(那條算的是 TC4 lane,不是 ws timer)。內容去重安全:book 形狀不變、前端 `case "book"` 一行不改。**窗大小要 user 拍板這點正確**——`futures_engine.py:183-184` 註解逐字為「五檔盤中要即時 → 週期取 0.1 s(1 s 會讓閃電梯五檔慢一秒)」,確實存在。

**風險**
不動任何 CLAUDE.md §4 契約(book 訊息形狀不變)。**唯一風險是五檔延遲**:futures_engine.py:183-184 的註解白紙黑字「五檔盤中要即時 → 週期取 0.1 s(1 s 會讓閃電梯五檔慢一秒)」,代表 user 對此敏感 → coalesce 窗(50 vs 100 ms)必須 user 拍板,不可自己定。

---

## [HIGH] F4-02 · LadderView 130 列無列級 memo
- 區塊: F4-ladder-highfreq — 前端:閃電梯/五檔/逐筆等高頻更新元件
- 位置: frontend/src/components/stock/LadderView.tsx:256-376 | 類別: render | 熱路徑: True | 工作量: L
- 驗證: **CONFIRMED**

**驗證理由**
逐字核對 `LadderView.tsx:256` `{rows.map((r) => {` 到 :376,證據句逐字吻合。**列數我自己重跑過 buildLadder 原式**(台股 tick 表 + `snapDown(ref*1.1)`/`snapUp(ref*0.9)`),結果與報告**逐一相等**:9.9=127 / 15=61 / 25=101 / 49.9=150 / 52=137 / 99=127 / 105=87 / 180=73 / 330=133 / 520=137 / 990=127 / 1200=49。每列 cn 次數我逐個數過 = **6 次**(row 容器 / buy flex / buy button / price span / sell flex / sell button),`fmt(r.priceMilli)` **3 次**(兩個 aria-label + 價格欄),均如報告所述。props 確實全是每 render 新 identity:`buildLadder` 回新陣列、`aggregateLots` 與 `markMap` 回新 Map。真正變值的列:book 改 ≤10 列的 bidQty/askQty、`isCenter` 搬 2 列、`dimmed` 只在 ±5% 邊界那一兩列翻轉(`stock-tick.ts` 的 `dimmed: Math.abs(p - anchor) / anchor > 0.05`),1–12 列的說法成立。測試行數也核對無誤(PriceLadder 1631 / FuturesLadder 1078 / StkfutLadder 850)。

**校正後影響**
每則約 780–900 個 React element 重建。我實測 cn 那一段 = 95.6 µs/render(見 F4-09);加上 element 建立與 reconcile,prod build 下整支 LadderView 估 0.5–0.7 ms/則。**是本區塊最大的單項**,但「critical」要看 F4-01 的則數才成立——10 則/s 下它只有 0.6% CPU。

**證據**
```
{rows.map((r) => {
  const buyLot = buyLots?.get(r.priceMilli);
  const sellLot = sellLots?.get(r.priceMilli);
  ...
  return (
    <div key={r.priceMilli} ... className={cn("relative grid h-6 grid-cols-[1fr_64px_1fr] …", r.isCenter && "bg-bg-deep", r.dimmed ? "border-line/20" : "border-line/50")}>
      ... <button className={cn("min-w-0 flex-1 pr-1 text-right", buyDisabled ? "text-ink-dim/50" : "text-bull hover:bg-bull/10")}>{r.bidQty > 0 ? r.bidQty : ""}</button>

# 列數實測(以 buildLadder 原式在 Node 重跑):9.9元=127 / 25元=101 / 49.9元=150 / 99元=127 / 330元=133 / 1200元=49
# props 全是每 render 新 identity 的物件:rows: LadderRow[]、buyLots/sellLots: Map、beMarks/avgMarks: Map
```

**原建議修法**
抽 LadderRow = memo(function LadderRow(...)),props 全 primitive:priceMilli / priceText(預先格式化)/ bidQty / askQty / isCenter / dimmed / buyLotText / buyLotCancelable / sellLotText / sellLotCancelable / beMark / avgMark / markTitle + 穩定 callback。fmt(r.priceMilli) 目前一列被呼叫 3 次(兩個 aria-label + 價格欄),應在 buildLadder 階段就算好 priceText 放進 LadderRow —— 價格文字只在列集合變(換股 / 換界)時才變,可整份快取。

**修法可行性查核**
方向對,但**有一條更簡單、風險更低的路徑報告沒提**:列上**已經有 `data-price={r.priceMilli}`**(:276),因此可以走**事件委派**——把 onClick 收到 scroll 容器一顆 handler、由 `e.target.closest('[data-price]')` 取價,列元件就完全不必收 callback。這樣可以**整個避開**報告自己列為主要風險的那件事(「callback 要走 ref 讀最新 tradeKind / qty / arm」——那是真錢送單時序,`clickPrice` 目前閉包讀 `tradeKind` / `qtyState.qty` / `arm.state.armed`,改 ref 等於把三個值的讀取時點挪位)。另外報告說的「DOM 被 outerHTML characterization 逐字鎖住」要更正:我 grep 全 repo,`outerHTML` **只出現在 `components/ladder/ArmRow.characterization.test.tsx`**,檔位列沒有逐字鎖 → 抽 memo 列(DOM 輸出不變)不會撞到它。`priceText` 預算進 `LadderRow` 可行,但那是跨檔型別,`stock-tick.test.ts` 會跟著動。

**風險**
onClickPrice / onCancelLot 必須 useCallback 且不依賴每 render 變的閉包(tradeKind / qtyState.qty / arm.state 要走 ref 讀最新值),否則 memo 全破 —— 但這牽動送單語意:「按快捷 3 張後點價送 3 張」的時序必須逐字不變,PriceLadder.test.tsx(1631 行)/ StkfutLadder.test.tsx(850)/ FuturesLadder.test.tsx(1078)有大量相關斷言。

---

## [HIGH] F5-01 · watchlist_quote per-code 推播讓 App 整棵樹每秒重繪 80–150 次
- 區塊: F5-app-shell-query — 前端:App shell、路由、TanStack Query 與輪詢層
- 位置: copycat/server/stock_engine.py:1827-1832(產生)+ frontend/src/hooks/useStockStream.ts:425(消費) | 類別: render | 熱路徑: True | 工作量: M
- 驗證: **OVERSTATED**

**驗證理由**
結構全部屬實,逐字核過:`copycat/server/stock_engine.py:1827-1832` 確為 `dirty, self._dirty_watchlist = ...; for code in dirty: ... self._publish(self._quote_payload(code))`,節流常數 `throttle_secs: float = 1.0`(:248),`_publish` 就是 `self._ws.publish(msg)`(:1759)—— 1 s 合併的確只合併同一檔,跨檔是 N 則獨立 frame。前端 `useStockStream.ts:425` 亦逐字為 `setWatchlist((prev) => ({ ...prev, [msg.code as string]: q }));`,而 `useStockStream` 掛在 App(App.tsx:181),所以 setState 確實重繪整棵樹;App.tsx 自己的註解(:176-182)也承認「watchlist_quote 的 setState 現在落在 App 層 → 每秒一批側欄報價會重繪整棵樹」。

**但頻率與量級都被放大了**,我用 repo 內既有的開盤實錄 trace 打假:`.claude/mod/group-grid-ticks/evidence/trace_2026-09-03_0902.json.json.gz`(09-03 09:01–09:03、prod preview 4173、92.9 s)解出 app renderer main thread 的數字 —— (a) 所有 WebSocket `onmessage` 合計 **7,897 次 / 92.9 s = 85 則/秒**(不是 110–180),handler 自身 avg 0.038 ms;(b) React 工作迴圈(`rt`,vendor chunk:26)**6,794 次 = 73 次/秒**,avg **2.28 ms**,合計 15.47 s = wall 的 16.6%;(c) 主執行緒 RunTask 總忙 23.11 s = **24.9%**,>50 ms long task = 0,最大 36.71 ms;(d) CPU profile 自身時間:idle 74.8%、JS self 合計 14.2 s = 15.3%。

另 `data/stock_watchlist.json` 實測 codes = **80**,所以上界是 80 則/秒,「80–150」的 150 是 WATCHLIST_LIMIT 不是現況。「盤中 CPU 幾乎全被這條路吃掉」與實測 25% busy / 零 long task 不符。

**校正後影響**
這是全站最大的單一 render 驅動源,但量級是「主執行緒 ~17% 花在 React 全樹重繪、整機 24.9% busy、零 long task」,不是 CPU 被吃光。修掉後預期把 73 Hz 全樹重繪降到 ~15 Hz,回收約 10–13% 的一顆核心。對「閃電梯點價延遲」的影響是間接的(最大單一任務 36.7 ms = 掉兩幀),不是每秒卡住。

**證據**
```
# stock_engine.py:1827-1832 —— 「1s 節流合併」合併的是同一檔的多筆 tick,不是跨檔
dirty, self._dirty_watchlist = self._dirty_watchlist, set()
for code in dirty:
    state = self._states.get(code)
    if state is None or state.last is None:
        continue
    self._publish(self._quote_payload(code))   # ← 每檔一則獨立 WS frame

// useStockStream.ts:425
setWatchlist((prev) => ({ ...prev, [msg.code as string]: q }));
```

**原建議修法**
兩段。(1) 後端合併成一則,比照 #180 `ticks` 打包的既有先例:`items = [self._quote_payload(c) for c in dirty if ...]; self._publish({"type":"watchlist_quotes","items":items})` —— 80 則降成 1 則。(2) 前端把 `watchlist` 搬出 React state,改 module-level store + useSyncExternalStore 的 per-code selector(subscribeQuote(code)/getQuote(code)),側欄一列與圖牆一張卡各訂閱自己那一檔。repo 內已有兩份現成範例可抄:lib/tick-stream.ts(EventTarget 匯流排)與 hooks/useCapital.ts:59-82(useSyncExternalStore wsStatus store)。

**修法可行性查核**
方向正確,但**兩段的性價比差很多,掃描把它們綁在一起賣是誤導**。後端打包那半(80 則 → 1 則/秒)是 S 級三行改動,單獨做就拿到約 80% 的收益(73 Hz → ~15 Hz),而且不動任何前端;前端 module store + per-code selector 是第二段,拿的是「側欄 80 列全重算 → 只重算那一列」那一層(6,400 列-render/秒 → 80),M 級且要改測試 stub。建議拆成兩票、後端先行。

風險敘述查核屬實且完整:`_quote_payload` 確為唯一 payload builder(:1759 上方 `stream()` 也用它);trial 翻轉補推(:1819-1826)與 `recovered / was_meta_none` 轉態補推(:1355-1357)都走 `_publish` 且**繞過 dirty 路徑**,打包時必須一併處理或明確排除,掃描有抓到前者、漏了後者。新訊息型別要進 CLAUDE.md §4 並兩側釘測試也是本 repo 的既定規矩(§4「ticks 打包」那條就是前例),舊型別保留一版的建議正確(#187 dist 舊 build 事故是同款)。

**風險**
新增 WS 訊息型別 = 新增跨檔契約,要比照 CLAUDE.md §4「個股逐筆 = ticks 打包訊息」那條寫進 §4 並在 tests/server/test_stock_engine.py + useStockStream.test.ts 兩側各釘一條。舊型別 watchlist_quote 建議保留一版(前端 default 分支對未知型別靜默丟棄 → 單邊部署讓側欄整片變 `-`,零錯誤訊號;#187 dist 舊 build 事故的同款)。_quote_payload 是 N101 記的唯一 payload builder,不可動其產出形狀,只改外層信封。trial 翻轉補推路徑(:1819-1826)也走 _publish,要一併進打包或明確排除。CLAUDE.md「WATCHLIST_LIMIT 效能預算註解」的最壞值要重算。

---

## [HIGH] F6-06 · 前端完全沒有效能量測探針 —— 無法證明「快不快」
- 區塊: F6-lib-build — 前端:其餘 lib、型別、build 設定與 bundle
- 位置: frontend/src/lib/dev-perf-guard.ts(全庫唯一碰 Performance API 的檔,而它是清除者不是量測者) | 類別: quant-gap | 熱路徑: False | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
grep 逐字確認:全 `src` 非測試檔中 `performance.mark|performance.measure|PerformanceObserver` 只命中 `lib/dev-perf-guard.ts`(而它檔頭 :15 自述「app 自身不用 performance.mark/measure,清除不影響邏輯」—— 它是清除者)、`requestAnimationFrame` 只有 FuturesLadder.tsx:333 / LadderView.tsx:162 兩處且都是捲動定位用。`main.tsx:11-14` 逐字 `if (import.meta.env.DEV) { const disposeGuard = installUserTimingGuard({ maxEntries: 5_000 }); ... }` —— 連清除者也只在 DEV。後端有 `ws.py::WsBroadcaster.dropped` + 60 s 節流「佇列滿」WARNING(CLAUDE.md §4 明載),前端確實沒有對稱的「我來不及畫」指標。

這是本區塊唯一一條我完全沒有打回去的 finding,而且它是其他每一條的前提:F6-01 的「最大單筆」、F6-02 的「最貴架構決定」、F6-03 的「thrash」、掃描全篇的「~10 commit/s」基準,全部沒有一個是量到的。

**校正後影響**
以「改造成高效能量化系統」為目標,這是本區塊(乃至 F2/F4/F5)的**根結**:沒有端到端數字,所有改造都只能用推測驗收,而推測在本次查核裡已經被打掉一半以上。先裝探針,其餘 12 條的排序才有意義。

**證據**
```
grep -rn "performance.mark|performance.measure" src → 除 dev-perf-guard 外零命中
// main.tsx:11-14:if (import.meta.env.DEV) { installUserTimingGuard({ maxEntries: 5_000 }); }  ← 連這支也只在 DEV
// 後端有 ws.py::WsBroadcaster.dropped + 60 s 節流「佇列滿」WARNING,前端沒有對應的「我來不及畫」指標
```

**原建議修法**
加 lib/perf-probe.ts(prod 也裝,localStorage 開關):WS onmessage 打 performance.mark、該批 commit 的 useEffect 收尾打 measure;另用 requestAnimationFrame 差值計 long frame(>50 ms),每 60 s 印 p50/p95/max —— 與後端「佇列滿」的 60 s 節流同節奏,方便對帳。或直接走既有 chrome-devtools-mcp skill 的 performance_start_trace 盤中取證流程。

**修法可行性查核**
方向對,但建議改一處實作:**不要用 User Timing API 當常駐 prod 探針**。`performance.mark/measure` 的條目進的正是 dev-perf-guard 在清的那個無上限 buffer(該檔 :4-8 實測 632 筆/秒 ≈ 1.1 MB/s 就是這個機制爆掉的);為了裝探針而把 guard 也搬進 prod,等於自己製造一個新的洩漏面再去堵它。改用 `performance.now()` + 固定長度 ring buffer(純 number,零 GC 壓力、零 buffer 依賴),每 60 s 算 p50/p95/max 印一行 —— 與後端「佇列滿」同節奏對帳的目標一樣達成,且不必動 dev-perf-guard 的 DEV 閘。long frame 用 `requestAnimationFrame` 差值或 `PerformanceObserver({type:'longtask'})`(後者不進 User Timing buffer)。另:harness 已有 chrome-devtools-mcp 的 `performance_start_trace`,那是**一次性取證**;常駐探針是**連續記帳**,兩者不互斥、要在票裡講清楚分工。

**風險**
prod 裝探針要注意不要自己變成負擔:mark/measure 本身會進 User Timing buffer,必須把 dev-perf-guard 的清除邏輯改成 prod 也生效(現在只在 DEV 裝)。

---

## [HIGH] F7-01 · 五顆 tab 用 hidden 保留 DOM 且全部沒有 memo
- 區塊: F7-render-audit — 前端:跨切 render 稽核(主執行緒預算)
- 位置: frontend/src/App.tsx:300-470(五個 tabpanel) | 類別: render | 熱路徑: True | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
機制屬實。App.tsx 的 tabpanel 在 **335 / 345 / 368 / 394 / 426 行**(finding 寫 302-311 / 300-470,行號整體偏移約 33 行),逐字 `hidden={tab !== "txo"}` ✓;`hidden` 對 reconciliation 無意義 ✓。memo 邊界 grep 實際是 **6 個**不是 7 個(RiverCards.tsx:31 / RightRail.tsx:121 / CandleChart.tsx:88 / GroupGridView.tsx:132 / StockIntradayChart.tsx:171 / :818),五個頁面元件確實一個都沒有 ✓。

**但兩個重要限縮 finding 沒講**:(a) stock / futures / corr 三個 panel 被 `visited` 閘門包住(`{visited.stock ? <div…> : null}`),`visited` 是 `useState` **不持久化** —— 開站當下只有 index + txo 真的掛著,「四個看不見的頁面」是使用者在該 session 逐一點過之後才成立的上界;(b) 「估計佔單次 render 工作量的 40 %」沒有任何量測,是猜的。

**校正後影響**
機制成立且範圍不小,但量級未量測。可確定恆成立的只有 TxoPage 那一份(F7-10);其餘三頁要使用者點過才掛。真正的成本是「每則 WS 訊息 × (已 mount 頁數)」,而那個乘數在 session 初期是 1–2、整天用下來才會是 4。

**證據**
```
App.tsx:302-311 `<div role="tabpanel" id={panelId("txo")} hidden={tab !== "txo"} …><TxoPage /></div>`;stock/futures/index/corr 同型(外加 visited 閘門,但 App.tsx:117-124 註解明寫「之後 hidden 保留 DOM(§3 慣例)」、index/txo 恆 true)。全庫 memo grep 只有 7 個命中,五個頁面元件一個都沒有:`grep -rn "= memo(|memo(function" src` → RiverCards.tsx:31 / RightRail.tsx:121 / CandleChart.tsx:88 / GroupGridView.tsx:132 / StockIntradayChart.tsx:171 / StockIntradayChart.tsx:818
```

**原建議修法**
首選:改用 React 19.2 的 `<Activity mode={tab==="stock"?"visible":"hidden"}>` 包住每個 tabpanel —— 它保留 state 與 DOM 但跳過更新,正是為這個場景設計的。保守替代:`export default memo(StockPage)` 等五個頁面元件全部 memo 化,並把 App 傳下去的 props 全部 useMemo(App 已經對 railCtx 做過這件事,樣板現成)。裝了 React Compiler 之後 memo 化是自動的,但 `<Activity>` 仍然值得 —— compiler 擋不掉「props 真的變了」的那些。

**修法可行性查核**
`<Activity>` **可用** —— 實測 `node -e "require('react').Activity"` 在 lock 到的 **19.2.7** 有導出(symbol)✓。但 finding 的 risk 漏了最關鍵一條:**`<Activity mode="hidden">` 會 destroy effects,不只是「跳過更新」**。TxoPage 的 `useTxoSnapshot`(WS)與 CorrPage 的 WS 都住在頁面內 —— 切走即斷線、切回重連,這正是 App.tsx:120-123 註解明文要避免的「改成按需會連帶改變 TXO WS 的建立時機(白名單 W-2)」。同時它會與既有的 `active` prop(FuturesPage / IndexPage 的輪詢閘)語意重疊。

比較安全的順序:先做保守路線(五個頁面元件 memo 化 + props useMemo,App 已有 railCtx 兩腿樣板),守門用既有 `src/App.memo.test.tsx`;`<Activity>` 當第二步、且要逐頁確認「effect 被拆掉」可不可接受。

**風險**
`<Activity>` 需確認實際 React 版本(package.json 是 ^19.0.0,要 19.2+)與穩定度;切 tab 時的首幀行為要驗(現在是零延遲,因為 DOM 一直在)。memo 化路線的風險是 props identity 要人工維護,而本 repo **沒裝 eslint-plugin-react-hooks**,漏掉不會被擋。守門用既有的 `App.memo.test.tsx` render 計次測試。不動任何 wire 契約。

---

## [HIGH] F7-03 · 主圖 book 訊息零節流
- 區塊: F7-render-audit — 前端:跨切 render 稽核(主執行緒預算)
- 位置: copycat/server/stock_engine.py:1359-1360 | 類別: render | 熱路徑: True | 工作量: S
- 驗證: **CONFIRMED**

**驗證理由**
`stock_engine.py:1360` 逐字 `self._publish({"type": "book", "code": code, "bids": book.bids, "asks": book.asks})`,就在 `_handle_quote` 尾端、與上方 0.1 s 打包(:1340-1343)並排 ✓;`futures_engine.py:173 flush_interval_secs: float = 0.1` 與「五檔盤中要即時 → 週期取 0.1 s」註解 ✓。前端 `case "book"` 逐字 `const next = { ...acc, book }; setAccum(next)` ✓。

**頻率「20–60/s」未量測**(finding 自己標了,誠實)。同一份 crash-scan 文件量到 stock WS 總計 3.6 msg/s(收盤後,不代表開盤)。

**校正後影響**
機制無疑義:這是 `/ws/stock` 上唯一完全沒有節流的訊息型別,而它的下游(`accum` identity → `stockCtx` → RightRail memo → PriceLadder)是全站最重的 subtree。量級待測,但這條在「該量哪一個數字」的排序上排第一是對的。

**證據**
```
stock_engine.py:1359-1360 `if code == self._main:\n    self._publish({"type": "book", "code": code, "bids": book.bids, "asks": book.asks})` —— 直接在 `_handle_quote` 尾端 publish,與上方 `_pending_ticks` + `call_later(self._tick_flush_secs, self._flush_ticks)`(0.1 s 打包,stock_engine.py:1340-1343)並排,book 完全沒進打包。期貨引擎有 coalesce(futures_engine.py:173 `flush_interval_secs: float = 0.1`,註解「五檔盤中要即時 → 週期取 0.1 s」),個股 book 沒有。
```

**原建議修法**
沿期貨引擎既有樣板:`_handle_quote` 改成標 `_dirty_book`,另開 `_flush_book` 由 `call_later(0.1, …)` 帶出最新一份(book 是全量快照,coalesce 天然安全 —— last-write-wins,不像 tick 不能丟)。**不併進 `ticks` 打包**,保持訊息型別不變 = 前端零改動。

**修法可行性查核**
後端 coalesce 的樣板現成、不動 wire 型別,可行。

**但掃描漏了一個更便宜、零延遲代價的修法**:現在的 publish 是**無條件**的 —— 純成交 quote(簿沒變)照樣重送一份一模一樣的五檔。先做「與上次送出的 bids/asks 相同就不送」的去重,成本是一次比較,**五檔延遲 0 ms**,而 coalesce 要付 +100 ms。在真錢閃電梯上,先做去重、量完再決定要不要 coalesce,比直接吞 100 ms 合理。

另:finding 對 `pendingBookRef`(F-2 交錯緩衝)的判斷正確 —— 它守的是 refetch 期間的簿覆蓋,與節奏無關。

**風險**
五檔延遲最多 +100 ms。閃電梯的點價目標是使用者自己點的價格列,不是 book 即時值,所以不影響下單正確性;但 `PriceLadder` 的「跟隨置中」與五檔量顯示會晚 0.1 s —— 與期貨梯現況同級,可接受。**不改 wire 型別 = 不動 CLAUDE.md §4 任何契約**;但要確認 `useStockStream` 的 `pendingBookRef`(F-2 交錯緩衝)在 book 變慢後的語意仍成立(它守的是 refetch 期間的簿覆蓋,與節奏無關,應無影響)。

---

## [HIGH] Q1-01 · 訊號邏輯三份獨立實作,真正決定線上政策的那份在 repo 外且無版本控制
- 區塊: Q1-quant-gap — 量化系統落差分析(這套系統離「量化交易系統」還缺什麼)
- 位置: copycat/engine/__init__.py:1 / copycat/replay/runner.py:14-15 / copycat/live/signal_state.py:1 / tests/fixtures/record_sweep_cluster_golden.py:9-12 | 類別: quant-gap | 熱路徑: False | 工作量: XL
- 驗證: **OVERSTATED**

**驗證理由**
外部事實全部覆驗成立:`grep -rn "copycat.engine|LockTracker|T1Tracker"` 在 `copycat/` 只命中 `replay/runner.py:14-15`(server/ 零命中);`cd C:/Users/USER/Documents/copycat-trading-review && git rev-parse --is-inside-work-tree` → `fatal: not a git repository`;`ls scripts/*.py | wc -l` = 48、`wc -l` = 7306、`du -sh data` = 971M;`tests/fixtures/sweep_cluster_golden.json` 實測 cases = 3(2026-08-17/6715、08-05/1727、08-19/8103);檔案大小 38,600 B / 86,889 B 逐字吻合。

但「三份**獨立實作**」的框架不成立:`copycat/engine/` 全部只有 296 LOC(lock_quality 132 + t1_open 161 + __init__ 3),做的是 **Phase 2 鎖板品質 + Phase 3 T+1 開盤路徑分類**,與線上六種即時訊號**沒有任何一種重疊**。真正重疊的只有兩份(研究 `combo_events.py` ↔ 線上 `signal_state._eval_sweep`),而那一份**正好是唯一有 golden oracle 的那一種**。所以正確敘述是「一份重疊且已有 oracle + 一份互不重疊的小型離線引擎」,不是「三份同一套邏輯各寫一遍」。

「其餘五種零回測、零一致性驗證」也要拆開:零「與研究口徑的一致性驗證」成立;但不是零測試 —— `tests/live/test_signal_state.py` 86 條、`tests/server/test_signal_hub.py` 109 條、`tests/server/test_signal_policy.py` 35 條。

**校正後影響**
真正 critical 的只有一句:**四週影子期結束要拿來對照的研究基準,是一份無版控、隨時可就地改掉的 7,306 行腳本 + 971 MB 資料**。這條成立、後果如述(「我當初測到 +X 元/筆」不可驗證),而且修法是 `git init` + 一次 commit(資料檔另 LFS 或 gitignore + 記 sha256),成本 S。其餘部分(engine/ 是死碼、五種 kind 無研究 parity)是中度技術債,不是單點失效。

**證據**
```
$ grep -rn "copycat.engine|LockTracker|T1Tracker" --include=*.py .
./copycat/replay/runner.py:14:from copycat.engine.lock_quality import LockTracker
./copycat/replay/runner.py:15:from copycat.engine.t1_open import EventContext, T1Tracker, gap_bucket_label
(server/ 零命中)

# record_sweep_cluster_golden.py:
- **研究真值**(逐字沿 `C:\\Users\\USER\\Documents\\copycat-trading-review\\scripts\\combo_events.py`
  的 `find_sweeps` + 主迴圈 sweepc 段)
TICKS_ROOT = Path(r"C:/Users/USER/Documents/copycat-trading-review/data/ticks")

$ cd /c/Users/USER/Documents/copycat-trading-review && git rev-parse --is-inside-work-tree
fatal: not a git repository
$ ls scripts/*.py | wc -l → 48 ; wc -l → 7306 total ; du -sh data → 971M
```

**原建議修法**
新建 `copycat/strategy/` 套件作為 live/backtest/research 唯一核心:strategy/policy.py(signal_policy.py 整檔搬,零行為改動,現有測試即驗證)→ strategy/detectors/{sweep,surge,volburst,cdp,limitlock}.py(從 signal_state.py 的六個 _eval_* 抽純函式,狀態以 dataclass 顯式傳入傳出,SignalDetector 降為薄組合層)→ strategy/replay.py(離線 harness,吃 tape 跑同一組 detector)。再為 cdp_cross / surge / vol_burst 各補一份雙 oracle golden fixture(沿 record_sweep_cluster_golden.py 格式)。最後把研究 scripts/ 收斂為 copycat.strategy 的呼叫端或至少 git init。

**修法可行性查核**
**步驟順序是反的,照做會很危險。** 提案是「1-2 先做 XL 重構(整檔搬 signal_policy + 從 signal_state 抽六個純函式)→ 3-4 才補 golden」。但這段 code 的特徵正好是:唯一的機械 oracle 只覆蓋 1/6 種 kind、其餘五種只有釘住「現況行為」的單元測試。在 oracle 缺席時重構最危險的那一段,等於用單元測試當安全網去改一個「單元測試本身可能就釘錯了」的東西。正確順序 = (a) `git init` 研究目錄(1 指令,拿走 90% 價值)→ (b) 先照 `record_sweep_cluster_golden.py` 的格式補 cdp_cross / surge / vol_burst 的雙 oracle fixture → (c) 才談抽 `strategy/`。

另外兩個提案沒提的具體撞點:(1) 搬 `copycat/server/signal_policy.py` 會動到 CLAUDE.md §4「族群 = 自選群組扣…」那條契約逐字記載的產生點路徑 `copycat/server/signal_policy.py::resolve_groups`,要同步改文件(不是 runtime 破壞,但契約文件漂掉正是該檔在防的事)。(2) 把 `_eval_*` 抽成「狀態顯式傳入傳出」的純函式,必須保留 design R2 的「`_window` / `_prev` / `_latch` 跨 kind 共用且無條件推進」語意 —— 那正是 `evaluate` 裡最容易在重構中被抹平的部分(docstring 明寫「關掉爆拉不影響共用同一個窗的爆量」)。

**風險**
步驟 1-2 是 🔵 純重構(公開簽名不變);步驟 3-4 是 🟢。會撞 CLAUDE.md §4「掃單簇參數 parity 走既有 fixture」—— 但 PARAM_SPECS 產生點仍在 signal_rules.py,不動,fixture 照舊釘得住。步驟 5(收斂研究碼)要 user 拍板。整批半徑大,必須 expand–contract 逐步單獨綠、單獨 commit。

---

## [HIGH] Q1-03 · 盤中重啟 = 訊號狀態全失,而回補 tick 被刻意設計成不重放進 detector
- 區塊: Q1-quant-gap — 量化系統落差分析(這套系統離「量化交易系統」還缺什麼)
- 位置: copycat/server/stock_engine.py:1349-1352 / :1688;copycat/live/signal_state.py:260-273;copycat/server/signal_hub.py:367,672 | 類別: quant-gap | 熱路徑: False | 工作量: L
- 驗證: **CONFIRMED**

**驗證理由**
五條子宣稱逐條回查全部成立:
- `stock_engine.py:1349-1352` 逐字為註解「掛在 `ingest` 為真的分支內…(回補重放走 `apply_backfill`,不經過這裡 — SC-5)」+ `self._signal_hub.on_tick(...)`;`:1688` 逐字 `state.apply_backfill([t for t in ticks if t.trade_date == self._trade_date])`,全段不碰 hub。
- `signal_state.py:260-273` `reset_day()` 清 `_basis/_window/_cooldown/_touch/_sweeps/_lookback` 等九份,全為純記憶體 dict/deque。
- (c) 我另外逐行驗過:`_eval_sweep` 的 `base = lookback[0]`、`up_pct = (...) if base[0] <= cutoff else 0.0`;`lookback` 的修剪條件是 `while len(lookback) >= 2 and lookback[1][0] <= cutoff`。重啟後 `lookback` 只有新進的 tick,不存在 `secs ≤ s − 60` 的項 → `up_pct = 0.0`,而 `cfg.sweep_up_pct` 預設 0.3 > 0 → **重啟後 60 秒內掃單簇必不發**。成立。
- (e) `signal_hub.py:367` `self._policy_touch: dict[tuple[str,str], int] = {}` 純記憶體,只在 `on_rollover()` 清;`_emit_policies` 的 `first = count == 1`、`notify = first and not late`、列上 `"first_of_day": first`。重啟 → 同檔同政策再推一次 Discord 且兩列都 `first_of_day: true`。成立,且這正是影子期 notify 閘的一半。

**校正後影響**
降一級的理由:後果是**影子期資料品質降級**(重啟後約 5 分鐘窗值偏低 + 60 秒內掃單簇不發 + 政策首筆重推一次),不是線上錯單或資金損失。子宣稱 (a)「jsonl 無任何『這段沒判』記號」要收窄 —— server 啟動 banner 有 `git_sha` + `started_at`(`build_info.banner()`),log 裡查得到重啟時刻;缺的只是「訊號 jsonl 這一份真相源裡沒有斷點」。

**證據**
```
# stock_engine.py:1349-1352
if self._signal_hub is not None:
    # 掛在 `ingest` 為真的分支內:…(回補重放走 `apply_backfill`,不經過這裡 — SC-5)
    self._signal_hub.on_tick(code, tick, state)

# stock_engine.py:1688(回補路徑,不碰 hub)
state.apply_backfill([t for t in ticks if t.trade_date == self._trade_date])

# signal_state.py:260-273 全部狀態純記憶體
def reset_day(self):
    self._basis.clear(); self._window.clear(); self._cooldown.clear()
    self._touch.clear(); self._sweeps.clear(); self._lookback.clear() …

# signal_hub.py:367
self._policy_touch: dict[tuple[str, str], int] = {}
```

**原建議修法**
(1) 🔴 新增 `SignalDetector.warmup(code, ticks)`:逐筆跑 evaluate 的狀態推進段但丟棄回傳事件,掛在 stock_engine.py:1688 apply_backfill 之後。一次修好窗冷啟與斷線洞。(2) 🟢 `SignalHub.start()`(:533)從當日 jsonl 重建 `_policy_touch` 與 `_cooldown` —— `today_signals()`(:1421)已能讀到全部列,而 id 是決定性鍵、資訊全在。(3) 🟢 session 斷點記到**另一個檔** `data/signals/_sessions.jsonl`。

**修法可行性查核**
**(1) 直接掛在 `apply_backfill` 之後會卡死 event loop —— 這是提案最大的問題。** `apply_backfill` 拿到的是該檔**當日全量** tick(`backfill(code)` 回整天),而 `_handle_quote` / 回補完成回呼都跑在 asyncio loop 上。以我實測的 `evaluate` 成本(窗長 3,001 時 cdp_cross/surge ≈ 5.7–6.5 μs、vol_burst ≈ 105 μs)× 7 條規則,單檔 30,000 筆 tick 的 warmup 就是**秒級**,150 檔開機補回就是**分鐘級**,整段期間 WS 心跳、廣播、rollover 全停擺。可行的形狀只有兩種:只重放「最近 N 分鐘」的尾段(N = max(surge_window_secs, sweep_up_window_secs) ≈ 5 分鐘,實測約 36 ms/檔),或丟 thread 跑完再原子換上。提案照字面做會製造比它要修的問題更嚴重的問題。

(2) 從 jsonl 重建 `_policy_touch`:可行(`today_signals()` 在 :1421、政策列有 `code` / `policy`)。但重建 `_cooldown` **半不可行** —— cooldown 值是牆鐘 `mono` 的絕對截止點,jsonl 列上只有台北 `HH:MM:SS`,要換算就等於把 Q1-02 的兩軸問題搬進來一次。建議只重建 `_policy_touch` 與 `touch_count`,cooldown 明確放棄並記在 session 列上。

(3) 另落 `data/signals/_sessions.jsonl`:正確,`_SIGNAL_DIR` 的 glob 只吃 `len(stem)==8 and stem.isdigit()`(回填 worker :1300 那段),底線開頭的檔天然被濾掉 → 不會撞回填的 byte 保留契約,也不撞「不新增列型」。這一條零風險,可以先做。

**風險**
(1) 是行為改動(窗值會變 → 事件集合會變),不能在影子期中途上,走 /mod。(3) **不可**寫進當日 signals jsonl —— 會撞 CLAUDE.md §4「研究目錄離線讀者逐列讀 s['kind'] 無防禦 → 不新增列型」,故改落獨立檔。(2) 需注意 jsonl 讀取是 O(當日列數),放在 start() 一次性可接受。

---

## [HIGH] Q1-05 · 風控只有單筆閘且預設「不限」,缺帳戶級上限、單日虧損熔斷與異常行情擋單
- 區塊: Q1-quant-gap — 量化系統落差分析(這套系統離「量化交易系統」還缺什麼)
- 位置: copycat/capital/safety.py 全檔(SafetyConfig:26-30);copycat/capital/client.py:876-885 | 類別: quant-gap | 熱路徑: False | 工作量: L
- 驗證: **CONFIRMED**

**驗證理由**
逐字覆驗全中:`safety.py` 全檔 105 行只有 `check_master` / `check_stock_order` / `check_future_order` / `check_cancel` / `check_correct_price` / `check_decrease` 六支**無狀態純函式**,`SafetyConfig` 三欄 `order_enabled: bool = False` / `max_qty: int | None = None  # None = 不限` / `max_amount: float | None = None`,檔頭 docstring 自承「與 treading-king 的 fail-closed(未設=拒單)**相反**」。`_execute_write`(client.py:865-885)只掛 `if not gate.allowed` 這一層。`_observe_trade_status`(stock_engine.py:1370)docstring 逐字「本輪**不據此判定任何狀態**…這裡只留可 grep 的紀錄」—— 異常行情確實只觀測不擋單。

**校正後影響**
維持 high,但要標明是**條件式**:現況是人工下單(一天個位數)+ `CAPITAL_ORDER_ENABLED` 總開關,裸奔風險有限;它是「接訊號自動下單」這一步的 blocker,不是今天的缺陷。掃描自己在 impact 裡有寫這句,severity 欄位沒反映出來。

**證據**
```
@dataclass(frozen=True)
class SafetyConfig:
    order_enabled: bool = False
    max_qty: int | None = None      # None = 不限(單筆張/口)
    max_amount: float | None = None # None = 不限(單筆名目金額)

# 四支閘全是單筆、無狀態純函式;_execute_write 只掛這一層:
if not gate.allowed:
    await self._audit_blocked(action, req, reason)
    raise CapitalGateBlockedError(reason)
```

**原建議修法**
新增 `copycat/capital/portfolio_gate.py`:PortfolioLimits(max_position_value / max_symbol_value / max_daily_loss / max_orders_per_minute / halt_on_daily_loss)+ `check_portfolio(req, *, positions, today_pnl, recent_order_ts, limits)`。掛點 = client.py:876 `_execute_write` 第一段,接在 check_stock_order 之後、_audit_blocked 之前。所需資料 store 全有:`store.positions()` 給曝險、`Position.pnl_base` 給損益基底、FillRecord 給今日成交。異常行情擋單靠 `_observe_trade_status` 第二段做出的 per-code 緩撮 set。

**修法可行性查核**
方向對(新開一支、不污染 safety.py 的純函式性質),但「所需資料 store 全有」這句過樂觀,兩個資料源都有陷阱:

(1) `store.positions()` 是**延遲快照** —— `_close_dup_reason` 的 docstring 自己寫「部位快取要等成交回報→debounce→重查回來才更新,窗口內(數秒)第二次平倉仍看得到原始全量持倉」。帳戶級曝險閘讀它會吃到同一個數秒窗,連下兩筆一樣過。要嘛沿用 `_close_inflight` 那套 in-flight 記帳把「在途未成交」算進曝險,要嘛接受這個窗並寫進契約。

(2) `Position.pnl_base` 只有**證券**列有。CLAUDE.md §4「部位均價語意」明寫 fut 列走 OI 快照、不經損益回填(`avg_source` 恆 null)。拿 `pnl_base` 當單日虧損口徑會**漏掉期貨那一半**,而失效樣態是靜默的(熔斷永遠不觸發)。單日虧損口徑要 user 拍板這點提案說對了,但要補上「期貨腿怎麼算」這個前置。

(3)「異常行情擋單是新契約,要寫進 CLAUDE.md §4」正確。

**風險**
safety.py 目前是純函式(好設計),加帳戶閘會讓它吃 store 快照 —— 建議**新開一支**而不是污染 safety.py,保持「單筆閘純函式」與「帳戶閘吃狀態」兩層分離。單日虧損口徑(已實現 vs 含未實現)要 user 拍板,因為 avg_source 兩種語意會讓兩個口徑差一筆手續費。異常行情擋單是**新契約**,要寫進 CLAUDE.md §4。

---

## [HIGH] Q1-06 · 新單零冪等防護(只有平倉有 inflight 去重),審計記錄無 request_id
- 區塊: Q1-quant-gap — 量化系統落差分析(這套系統離「量化交易系統」還缺什麼)
- 位置: copycat/capital/client.py:978-990(submit_stock_order)/ :1122-1163(_close_inflight,僅平倉)/ :335-342(_record 無 request_id) | 類別: quant-gap | 熱路徑: False | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
逐字覆驗:`submit_stock_order`(client.py:978-990)只有 `_execute_write(action=action, req=req, gate=check_stock_order(...), com_call=_do)`,零 dedup;`_close_dup_reason` / `_close_inflight` / `_submit_close_locked`(:1121-1163)確實只服務平倉;`_record`(:327-342)回傳 dict 逐字為 `{"ts","env","action","req","blocked","result"}`,無 request_id / client_order_id。超時處置(:892-898「結果未知,勿重送」+ `shield` 不 cancel + `add_done_callback` 補 late 審計)也如描述寫得很嚴謹。

**校正後影響**
這條**在現況就成立**,不像 Q1-05 是條件式:前端雙擊 / route 重試 / 網路重送現在就會產生重複新單,而三道閘一條都擋不住(平倉有、新單沒有,這個不對稱本身就是訊號)。維持 high。

**證據**
```
# 只有平倉有:
def _close_dup_reason(self, inflight_key: str, scan_key: str, side: BuySell) -> str | None:
    deadline = self._close_inflight.get(inflight_key)
self._close_inflight[inflight_key] = time.monotonic() + _CLOSE_INFLIGHT_S

# 新單:零 dedup
async def submit_stock_order(self, req, *, action="order") -> OrderResult:
    result = await self._execute_write(action=action, req=req,
        gate=check_stock_order(req, self._safety), com_call=_do)

# 審計記錄全欄(client.py:335-342):
return {"ts":…, "env":…, "action":…, "req":…, "blocked":…, "result":…}
# ← 沒有 request_id / client_order_id
```

**原建議修法**
(1) `StockOrderBody` / `FutureOrderBody`(server/capital_api.py:294/:310)加選配欄 `client_order_id: str | None`;(2) client 以當日 `dict[str, OrderResult]` 記已送出 id(換日清),重放同 id 直接回上次結果並審計一行 `action="order_replay"`;(3) `_record()` 把 client_order_id 與(未來的)signal_id 一併落審計。

**修法可行性查核**
可行度比提案寫的還高一級,因為**已有現成前例**:`StockOrderRequest` / `FutureOrderRequest` / `PositionCloseRequest` 都已經有 `source: str = "panel"  # 稽核分流:panel/flash`(models.py:60/72/102),而 `_record` 的 `"req": dataclasses.asdict(req)` 會把它整包落審計。也就是說「body 加選配欄 → request dataclass 加欄 → 自動進審計」這條鏈已經跑過一次,加 `client_order_id` 是同一條路,不需要動 `_record` 的形狀。

要補的兩點:(a)「當日 dict 記已送出 id,換日清」要注意夜盤跨午夜 —— `_note_price_type` 已經為了同一個問題記**兩個**日候選(本機日 + 交易日,N075),換日鍵要沿用同一把尺,不要自己再推一次。(b) 重放同 id 回上次結果時,「上次是 timeout(結果未知)」這一類不能當成功回放,否則會把「不知道有沒有出去」冒充成「已經出去了」。

**風險**
動 body schema → 前端同動(現有 close-order.ts 系列送 body 的形狀要加欄,選配欄不破相容)。這是新的跨檔契約,要寫進 CLAUDE.md §4。

---

## [HIGH] Q2-02 · 圖牆 50 卡的 SVG 是 React 元素 per 點;先改單一 <path d> 再談換圖表庫
- 區塊: Q2-tooling-landscape — 工具與套件選型調研(對外查證)
- 位置: frontend/src/components/stock/CandleChart.tsx:221;CardIntradayChart.tsx(71 LOC)→ StockIntradayChart.tsx(1724 LOC) | 類別: render | 熱路徑: True | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
結論成立,但**引用的證據是錯的檔**,且 repo 已自己提出同一個修法。

(1) 誤植:`CandleChart.tsx:221  {g.candles.map((c, i) => (` 逐字存在,但 CandleChart **不在圖牆路徑上**。grep 消費端只有 `FuturesChart.tsx:419`、`MarketChart.tsx:144`、`StockChart.tsx`。圖牆走的是 `GroupGridView.tsx:3 → CardIntradayChart.tsx → IntradayChartCore`(`CardIntradayChart.tsx:1  import { IntradayChartCore } from "@/components/stock/StockIntradayChart"`)。

(2) 走勢線其實**早就是單一 polyline**:`StockIntradayChart.tsx:545  <polyline points={pts(g.priceLine)} …>`、:523 vwapLine 同形。所以「每個分時點一個 DOM node」不成立。

(3) 真正的 per-point 節點來源是 `EnergySub`(量柱)與 `vpBars`:`:882  {bars.map((b) => (<rect data-testid="energy-bar" …>`、`:451  {vpBars.map((b) => (<rect data-testid="vp-bar" …>`,而且 card 變體**照畫**(`:1625  <EnergySub …>` 只被 `index ? null :` 擋)。

(4) **repo 自己已經寫下同一個修法與量測**:`StockIntradayChart.tsx:808-817`「這層最多 270 個 `<rect>`(近全軸 1140 個)…N047(2026-08-24 量測後留原樣):memo 擋得住 hover,但擋不住報價 —— 每則 tick 讓 `accum.minutes` 換 identity → `subEnergy` 重算 → 本層 1140 個 rect 全部重建。jsdom 量到滿窗一輪 ~15 ms…真正安全的是 EnergySub 改單一 `<path>`(節點數 1140 → 1),留 next-time。」

(5) CandleChart 本身有視窗上限:`candle-viewport.ts:14  export const MAX_VISIBLE = 700`,所以單檔頁最壞 700 根 × 2 節點,不是無界。

**校正後影響**
現貨窗每卡最多 270 個 `<rect>`(近全軸窗 1140);50 卡全量約 13,500 節點,量級與 finding 說的「上萬」相符。但重繪不是全體同步:`useGroupLiveAccums` per-code identity,只有收到成交的卡才重建。以 repo 自己量到的「jsdom 滿窗一輪 ~15 ms、真瀏覽器快一個量級」推,單卡約 1.5 ms;開盤 0.1 s 窗內若 20 張卡有成交 = 約 30 ms / 100 ms,約主執行緒 30%。這是前端唯一有實際量級的候選,排第一是對的。

**證據**
```
frontend/src/components/stock/CandleChart.tsx:221
  {g.candles.map((c, i) => (
:176  g.volBars.map((b, i) => {
:203  g.volBars.map((b, i) => (
:300  hlines.map((ln, i) => {
:353  shown.map((b, i) => {
:18   import { pts } from "@/lib/svg-points";   ← path 串接的基礎設施已存在

CLAUDE.md §1:「dev build 的 React Component Performance Track 已由 dev-perf-guard 堵住洩漏,但 props-diff 開銷仍在 —— 整天掛著一律用 prod build(2026-08-20)」
```

**原建議修法**
第一步(零新相依、最高投報):把 points.map(p => <circle/>) / candles.map(...) 這類 O(點數) 的 React 元素,改成用已存在的 lib/svg-points.ts::pts 串成單一 <path d="..."> 字串 —— DOM 節點數從 O(n) 降到 O(1),幾何層完全不動。第二步(量測後再做):主圖換 lightweight-charts 5.2.1(Canvas 2D、35 KB base、官方建議即時流用 update() 增量重繪、v5 已修掉 series markers pane 每次 mousemove clone 整份資料集的問題)。圖牆 50 卡**不要**開 50 個庫實例(50 canvas + 50 套事件 + 50 份內部資料,可能比現況更糟),改用單一 <canvas> 分格畫 50 個 viewport。

**修法可行性查核**
第一步(EnergySub 改單一 `<path>`)可行、零相依、與 repo 既有 next-time 完全一致,而且已經有 baseline 數字可以回歸對照 —— 這是本區投報最高的一條。但要注意兩點:①改的是 `EnergySub` / `vpBars`,不是 finding 寫的 CandleChart;②第二步「主圖換 lightweight-charts」列的風險③(江波圖調色盤 `test_river_palette_covers_every_leg` 鎖 `RIVER_STROKES`)**套錯對象** —— 江波圖在 `frontend/src/components/corr/`(RiverPanel / river-colors.ts)自成一棵樹,換 CandleChart/StockIntradayChart 碰不到它。風險①(紅漲綠跌必須顯式設)與②(CDP/MA 不可用庫內建、`overlay_parity.json` 兩邊各一條)則完全正確且必須保留。

**風險**
換圖表庫時的三條硬紀律:①**紅漲綠跌必須顯式設 upColor/downColor** —— lightweight-charts 預設是歐美的綠漲紅跌,CandleChart.tsx:35-39 的 BODY_CLASS 已註明台股慣例,看錯漲跌方向 = 下錯單,這是後果最嚴重的一條;②CDP/MA 仍須由 lib/futures-overlay.ts 算完再餵給圖表庫,**絕不可用庫內建 indicator**(tests/fixtures/overlay_parity.json 兩邊各一條 parity 測試,CLAUDE.md 明文「兩張圖都畫得出來、兩組數字都看起來對,零錯誤訊號」);③江波圖調色盤那條「tests/test_corr_config.py::test_river_palette_covers_every_leg 以原始碼字面鎖 RIVER_STROKES/FILLS/TEXTS class」的後端測試,顏色從 Tailwind class 變成 canvas fillStyle 字串後讀法要先改。另 Apache-2.0 需 TradingView 署名(用 attributionLogo chart option)。第一步(path 字串)不碰上述任何一條。

---

## [HIGH] Q2-12 · stdlib-only 的 dependencies=[] 是資產;新套件一律進 extras
- 區塊: Q2-tooling-landscape — 工具與套件選型調研(對外查證)
- 位置: pyproject.toml:6,8-12 | 類別: architecture | 熱路徑: False | 工作量: S
- 驗證: **CONFIRMED**

**驗證理由**
`pyproject.toml:6  dependencies = []` 與 :9–:12 四個 extras 逐字核對通過。「golden gate 能當行為合約的前提是這條離線鏈不需要任何 binary wheel」這個論述成立:`copycat/data/store.py` 只 import `json` / `pathlib` / `copycat.data.models` / `copycat.fileio`;`backtest/search.py` 只 import `json` / `logging` / `math` / `random` / `dataclasses`;`backtest/pipeline.py` 加 `csv`。整條 replay / validate / import-neigui 鏈確實是 stdlib-only。

「而且是無聲消失(本機裝得起來,所以沒人會發現)」這個失效模式描述精準 —— 這是本區唯一一條在**修法還沒開始前**就有價值的結論。

**校正後影響**
這條不是效能項目,而是決定「後續所有導入是可逆還是一去不回」的架構護欄。維持 high 是合理的 —— 它的價值在於約束其他每一條 finding 的執行方式。

**證據**
```
pyproject.toml:6   dependencies = []
pyproject.toml:9   live = ["fastapi>=0.115", "uvicorn[standard]>=0.30", "pyzmq>=26"]
pyproject.toml:10  capital = ["comtypes>=1.4", "pywin32>=306"]
pyproject.toml:11  discord = ["discord.py>=2.4"]
pyproject.toml:12  dev = ["pytest>=8", "ruff>=0.5", "pyright>=1.1", "httpx>=0.27", "pytest-asyncio>=0.24"]

CLAUDE.md §1 完成前 gate:pytest -q + ruff check + pyright + `copycat validate`(golden 驗證,需先跑過 four/five 兩份 replay)全 PASS
```

**原建議修法**
所有新相依一律進 extras,並依路徑分組:
  live = [..., "httpx>=0.28", "msgspec>=0.21"]      # server 即時路徑
  research = ["duckdb>=1.5", "polars>=1.44"]          # 離線回測路徑(新增)
讓 replay / validate 這條 golden gate 路徑維持 stdlib-only。這是本區最重要的架構建議之一 —— 它決定了後續所有導入是「可逆的」還是「一去不回」。

**修法可行性查核**
完全可行,零成本。risk 段那條補充尤其重要且正確:「若某個熱路徑的 msgspec.Struct 被 engine/ 共用,replay 就會需要 msgspec 而失去可攜性 —— Struct 的使用範圍要明確劃在 live/ + server/ 的 wire 邊界,engine/ 與 replay/ 維持純 stdlib 型別」。這條應該直接寫進 CLAUDE.md,不論後面導不導 msgspec。

**風險**
若某個熱路徑的 msgspec.Struct 被 engine/(零 IO 狀態機)共用,replay 就會需要 msgspec 而失去可攜性。所以 Struct 的使用範圍要明確劃在 live/ + server/ 的 wire 邊界,engine/ 與 replay/ 維持純 stdlib 型別。

---

## [HIGH] X1-01 · CorrState.correlations() 每秒在 event loop 上整批重算 —— 抖動地板
- 區塊: X1-blocking-io — 跨切:阻塞 IO 全庫稽核(「不能塞住」的核心)
- 位置: copycat/live/corr_state.py:82-126(呼叫點 copycat/server/corr_engine.py:300,543;app.py:1986,1997) | 類別: algorithmic | 熱路徑: True | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
程式碼屬實:corr_state.py:82-110 `leg_by_ts = dict(leg_series)` + `for ts, base_mid in base_series` 每腿一次;:113-126 `for leg in self._legs` × `for window in self._windows` 各兩條 list comprehension;corr_engine.py:223-225 `_run` 是 `while True: await asyncio.sleep(self._tick_secs)` 無任何盤別 / 交易日閘,tick_secs=1.0;:300 `tick_once` 內 `self._broadcast(self.state())`,而 `state()`(:565)最後一行就是 `self._state.correlations(now)`;app.py:1986 與 :1997(/ws/corr seed)各是一條額外的全額呼叫。腿數實查 configs/correlation.json = 11 腿(base TXF 扣掉 = 10 腿),windows=(60,300,1800)。**但兩個數字要修**:(1) 序列長度不是 3600。`_cap = 2*1800/1.0 = 3600` 只是保險上界,`_evict` 以 `now - max_window` 逐出,穩態實測 `len(series) = 1801`、`paired = 1800` —— evidence 寫「3600 項 dict / 3600 次迴圈」是拿 cap 當實際值,放大一倍。(2) 我在本機以真實 CorrState + DEFAULT_CONFIG 量到 **12.385 ms**(不是 16.043),`_paired_returns` 佔 **73%**(不是 83%),`push()` 4.0 µs。

**校正後影響**
12–16 ms 的連續 loop 佔用,每 1 s 一次,開盤約 30 分鐘後窗滿即維持整場(盤別翻轉會清空序列、重新累積 30 分鐘)。CPU duty ≈ 1.2–1.6%,真正的代價是「每秒一次、最長 16 ms 的全站停拍」—— 期間 WS 不推、tick 不處理、下單 route 不推進。降 critical 為 high 的理由:它是週期性 jitter 不是吞吐牆,而且我實測 Windows 上**閒置** ProactorEventLoop 的 `sleep(0.05)` 本來就 p50 overshoot 12.3 ms(見 missed #3)—— 也就是說對「靠 timer 驅動」的路徑,平台本身的地板已經同一量級;真正被它多傷到的是 IOCP 直接喚醒的那半(WS 送出、下單 route)。

**證據**
```
# corr_state.py:82
def _paired_returns(self, leg, now):
    leg_by_ts = dict(leg_series)            # 每腿每次建 3600 項 dict
    for ts, base_mid in base_series:        # 3600 次迴圈
        rb = log_return(prev_base, base_mid)
        rl = log_return(prev_leg, leg_mid)
    return [row for row in out if row[0] >= now - self._max_window]
# corr_state.py:113
for leg in self._legs:                      # 10 腿
    paired = self._paired_returns(leg, now) # 整批重算
    for window in self._windows:            # (60,300,1800)
        xs = [rb for ts, rb, _ in paired if ts >= cutoff]
        ys = [rl for ts, _, rl in paired if ts >= cutoff]
# corr_engine.py:300 tick_once(每 tick_secs=1s)
    self._broadcast(self.state())           # state() 內含 correlations()
```

**原建議修法**
stdlib 即可:把「配對報酬序列」快取成 deque,push() 時只 append 最新一筆(O(腿數)),correlations() 用 bisect 切窗後仍交給 statistics.correlation 整批算 —— 浮點結果逐位元不變(docstring 反對的是增量『相關係數』,不是增量『報酬序列』)。預期 16 ms → <1 ms。若量完仍不夠,再評估 numpy np.corrcoef 對預配置 ring buffer(16 ms → ~0.15 ms),但那會破壞 runtime stdlib-only 分界。

**修法可行性查核**
可行。增量化的是「配對報酬序列」不是「相關係數」,`statistics.correlation` 仍整批算 → 浮點逐位元不變,module docstring 反對的那條不適用(建議同時改 docstring,否則下一個人會再誤讀一次)。實作要盯三個點,掃描 agent 只寫了兩個:(a) `push()` 在 `session != self._session` 時 `series.clear()`,快取的報酬 deque 必須同時清;(b) `_evict` 要同步逐出;(c) `_paired_returns` 尾端用 **caller 的 `now`** 過濾(`row[0] >= now - max_window`),而 `_evict` 用的是 push 的 ts —— 兩者可能差一拍,增量版要用 bisect 在讀出時切窗才能逐位元等值。**另一個更省事、掃描 agent 漏掉的半**:`state()` 目前對每個 /api/corr/state 與每條 /ws/corr 連線都重算一次完整 correlations,而 `_seq` 每 tick 才 +1 —— 只要以 `_seq` 為 key 快取 `state()` 的 `pairs`,seed 路徑的成本立刻歸零,約 5 行、零演算法風險,可先做這半再評估要不要動 `_paired_returns`。不碰任何跨檔契約(腿數 / 調色盤 / payload 形狀全不變)確認屬實。

**風險**
CorrState 是零 IO 純狀態機,tests/live/test_corr_state.py 有覆蓋;**不碰任何跨檔契約**(configs/correlation.json 腿數、river-colors.ts 調色盤、/api/corr/state payload 形狀全不變)。必須保住兩條不變式:「報酬不跨洞接合」(相鄰取樣秒且兩腿皆有中價才產生)與「時間戳逐出」——增量版要在 push() 當下用同一組判準決定追加、在 _evict 時同步逐出報酬序列。建議先以現有測試當 characterization,再加一條「增量 vs 整批逐位元相等」的 property 測試。

---

## [HIGH] X1-02 · 下單審計與全庫 TC4 歷史取數共用同一個 20-thread 預設 executor
- 區塊: X1-blocking-io — 跨切:阻塞 IO 全庫稽核(「不能塞住」的核心)
- 位置: copycat/capital/client.py:885,353(審計);共用池的其餘 60 處 to_thread 見報告 §5.3 | 類別: blocking-io | 熱路徑: True | 工作量: S
- 驗證: **CONFIRMED**

**驗證理由**
機制屬實且 codebase 自己已記錄:client.py:885 `await asyncio.to_thread(self._audit, self._record(action, req))` 走 loop 預設 executor;app.py:1568-1572 的註解逐字寫著「to_thread 走 loop 預設 executor,與 daily_bars / capital close 同池且工作執行緒不可中斷 —— TC4 半死的殭屍執行緒堆積時這條會跟著排隊(review C-1)」。池大小:本機 `os.cpu_count()` 實查 = 16 → `min(32, 16+4) = 20`,正確。全庫 to_thread 實查 104 處(含 .pyc;去掉 pycache 後 13 個模組),不是 60,但那是低估不是高估。20 s 上界也對:tc4.py:51 `BARS_POLL_DEADLINE = 10.0`,stock_source.py:853-869 tf=D 路徑是 DK 一段 + 1K fallback 一段,`_collect_history` 的退避 `time.sleep` **不持 `api.lock`** → 多條 worker 真的能同時卡在輪詢裡。`_WRITE_TIMEOUT_S` 在審計之後才起算也對(client.py:885 → :888 才 `wait_for`)。**要降級的是發生機率**:build_minute(bars.py:630-720)有 15 s 當日 TTL + 永久歷史 memo + 15 s 負向快取,build_daily(:405-433)有整日 memo + 負向快取,前端分 K 輪詢是 60 s/key 且 key 只有幾把(useMarketBars),overlay 另有 `Semaphore(4)` —— 要湊滿 20 條在飛的不可中斷工作,需要「TC4 半死 + 多分頁同時冷載入」這種疊加,不是日常態。

**校正後影響**
常態下審計 to_thread ≈ 0.3 ms,完全無感;真正的問題是**真錢路徑上有一段無上界的排隊**,而它的鄰居是最壞 20 s 且不可中斷的 TC4 歷史取數。維持 high(不是 critical):機率低但後果是「使用者看到 route 整條掛住」而非「結果未知」,且修法極便宜。

**證據**
```
# capital/client.py:885  _execute_write
await asyncio.to_thread(self._audit, self._record(action, req))   # 預設 executor
fut = self._loop.create_future()
self._cmd_q.put((com_call, fut))

# app.py:1568-1572 —— codebase 自己已辨識出這個問題
# to_thread 走 loop 預設 executor,與 daily_bars / capital close 同池且工作
# 執行緒不可中斷 —— TC4 半死的殭屍執行緒堆積時這條會跟著排隊(review C-1);

# bars.py:441
#   ... 界前唯一走得到「有 stale 可比」的是同 key 併發首抓(build_* 無 inflight
```

**原建議修法**
(1) 給 capital 一條專屬 ThreadPoolExecutor(max_workers=2, thread_name_prefix='capital-audit'),審計改走 loop.run_in_executor(self._audit_pool, ...) —— 審計只是 200 µs 的 append,永不被行情查詢排隊。(2) 給 TC4 歷史取數一條有上限的專屬 executor(建議 max_workers=6),同時把「TC4 殭屍執行緒」的爆炸半徑框住。(3) build_daily/build_minute/build_period 加 per-(code,tf,window) 的 inflight dedup(dict[key, asyncio.Future]),把併發數從「前端有幾個 hook」降到「有幾個不同的 K 線」。

**修法可行性查核**
(1) capital 專屬 `ThreadPoolExecutor(max_workers=2)` —— 正確、便宜、零契約風險;要記得 lifespan 收尾 shutdown。它對 `shutdown_budget.py` 的判斷也對:沒改 lane 形狀就不必動 `TC4_LANE_DEPTH`(該檔的預算式是 WS_DRAIN + LANE_DEPTH×close_worst + COM_JOIN + slack,新增一個 2 條的審計池不進那條不等式)。(2) TC4 歷史專屬池 max_workers=6 —— 方向對,但要講清楚它把「池飽和」換成「TC4 取數之間的 head-of-line」:TC4 半死時第 7 條之後的 K 線請求會排在 20 s 後面,而目前是各自去撞。對看盤體感其實更好(至少下單與 WS 不受影響),但屬行為改變,值得寫進 spec 讓 user 拍板。(3) inflight dedup 收益比 semaphore 大(同時砍掉重複的 TC4 往返),bars.py:441 的註解確實描述了「同 key 併發首抓是界前唯一走得到有 stale 可比的路」—— 但 `_warn_if_not_advanced` 開頭就 `if _now_time() < DAILY_FINAL_TIME: return`,所以 dedup 不會讓那條 tripwire 誤鳴,受影響的是 tests/server/test_bars.py 的既有案而非正確性。**建議切成兩筆 PR**:(1) 單獨先上(3 行、可立刻驗收),(2)(3) 另案。

**風險**
(1) 近乎零風險;要新增「審計池不受預設池飽和影響」的整合測試。(2) 新 pool 要在 lifespan 收尾 shutdown(wait=False),否則多一條不退的執行緒;不改 lane 形狀就**不必**動 shutdown_budget 的 TC4_LANE_DEPTH(CLAUDE.md §4「關機預算三方同源」,tests/server/test_shutdown_budget.py 以 run.ps1 字面 parity 守著)。(3) 會改變 bars.py:441 註解描述的「同 key 併發首抓」路徑,與 DAILY_FINAL_TIME 定稿界契約(前後端同值 14:00)交織,改前要先讀 tests/server/test_bars.py。

---

## [HIGH] X3-02 · 所有 TC4 取數序列化在「一 session 一顆 REQ socket + 一把 api.lock」上
- 區塊: X3-concurrency — 跨切:併發模型、GIL、鎖競爭全庫稽核
- 位置: copycat/live/tc4.py:333-360(+ spikes/TCPY/tcoreapi_mq.py:11) | 類別: serialization | 熱路徑: False | 工作量: L
- 驗證: **CONFIRMED**

**驗證理由**
**核心事實完全成立**,但引用位置要更正:`_req` 實際在 `copycat/live/tc4.py:547-580`(不是 finding 寫的 333-360,那個範圍是 `_stkfut_catalog` 的 `_walk_strings`)。引用的程式碼逐字在 562-575:`if not api.lock.acquire(timeout=self._lock_timeout): self._dispose(api); raise ConnectionError("TC4 quote api.lock timeout")` → `api.socket.send_string(...)` / `api.socket.recv()[:-1]` → `finally: api.lock.release()`。`_REQ_TIMEOUT_MS = 10_000`(tc4.py:120)、`DEFAULT_LOCK_TIMEOUT_SECS = 12.0` 也都對得上。

三處自陳註解我逐一查證都存在,只是行號有漂:`app.py:127` 那段「配上 route 層 Semaphore(4),四檔這種股號就足以把整個端點凍住(head-of-line)」逐字在;「秒級同步呼叫且全程持 session 鎖…期間這條 session 上的其他 REQ 全部排隊」實際在 `tc4.py:840`(Fut2 docstring,配 `tc4.py:118` 的「實測最重呼叫 QUERYALLINSTRUMENT(Opt) 1.93s」);「三個 REQ 生產者在 boot 必然重疊,級聯是常態」在 `tc4.py:372`。`overlay_sem = asyncio.Semaphore(4)` 在 `app.py:547`、使用點 `app.py:1495`,且 cache 命中不進 semaphore(`app.py:1493-1495`)—— 這點 finding 沒提,是既有的減壓。

少數數字要按真資料縮:CDP 基準 sweep 是 **80 檔 × 0.2 s ≈ 16 s**(`data/stock_watchlist.json` 實際 80 碼,不是 150);回補的「150 檔最壞 25 分鐘」忽略了 `_backfill_worker` 的批次抽乾 + `prepare_backfill` 整批先 SubHistory(perf/opening-backfill-parallel,實測 40 檔 40.7→0.87 s)。

這是本份報告唯一一條「真正的結構天花板」:它不是 CPU 問題,換 uvloop / 多 worker / free-threading 全部零幫助,這個判斷正確。

**校正後影響**
不降為 critical 的理由:它是**延遲 / UX 上界**,不是吞吐崩潰,且 codebase 已有三道減壓(overlay cache 命中不進 semaphore、`OVERLAY_FETCH_TIMEOUT_S=15` 早放名額、backfill 批次 prepare)。症狀是「進群組時疊線慢慢浮出來」與 boot 前一兩分鐘的級聯,不是盤中持續劣化。但若目標是「改造成高效能量化系統」,這條是**第一個要先解的**:在它之上做的任何平行化都是假的。

**證據**
```
if not api.lock.acquire(timeout=self._lock_timeout):   # DEFAULT_LOCK_TIMEOUT_SECS = 12.0
    self._dispose(api); raise ConnectionError("TC4 quote api.lock timeout")
try:
    api.socket.send_string(json.dumps(obj))
    message = api.socket.recv()[:-1]                    # RCVTIMEO = _REQ_TIMEOUT_MS = 10_000
finally:
    api.lock.release()

# app.py:127 自陳:「配上 route 層 Semaphore(4),四檔這種股號就足以把整個端點凍住(head-of-line)」
# tc4.py:1136 自陳:「秒級同步呼叫且全程持 session 鎖…期間這條 session 上的其他 REQ 全部排隊」
# tc4.py:407 自陳:「三個 REQ 生產者在 boot 必然重疊,級聯是常態」
```

**原建議修法**
方案 A(低風險,建議先做):把 REQ 收成一條 asyncio.PriorityQueue + 單一 REQ worker(REQ 本來就只能一發一發送),使用者互動優先、背景 sweep 最低;不動 TC4 協定,只改 _req 入口與 caller 的 await 形狀。方案 B(高收益高風險):多開一條「歷史專用」session —— 歷史(SubHistory/GETHISDATA)與 REALTIME 是不同 DataType 的兩把 refcount key(tc4.py::_apply_variant docstring 明說),理論上不互搶 feed,但必須先跑受控 probe 驗證。

**修法可行性查核**
方案 A/B 的風險評估都誠實,但**掃描漏了一個成本低一個量級的第三條路**:不必重寫 `_req` 的所有 caller,只要把 `api.lock` 換成一個 `threading.Condition` + 等待者優先權堆疊做的「票號互斥鎖」,對外仍只暴露 `acquire(timeout=)` / `release()`,`_req` 只多傳一個 priority 參數,caller 的 await 形狀零改動。這條路**必須**保留 `acquire/release` 介面,因為 wrapper 的 `KeepAliveHelper` → `Pong()` 會直接取同一把 `api.lock`(`spikes/TCPY/tcoreapi_mq.py`),換成 asyncio 原語就直接壞掉 —— 這個約束 finding 沒寫出來,是方案 A 真正的地雷。

方案 B 的風險描述我查證屬實:`_apply_variant`(tc4.py:594-601)docstring 明寫「TC4 的訂閱 refcount 鍵是 `symbol|DataType|StartTime|EndTime`」,所以「歷史與 REALTIME 是兩把 key」的推論有原始碼支撐,但也正因為鍵含 Start/EndTime,多開 session 會撞到既有的 `SPOT_WINDOW_OFFSET` / heal variant 階梯(tc4.py:103-111 已經為了雙持同一把 key 吃過一次苦),`TC4_LANE_DEPTH` 同動的提醒也正確。**先 probe 再談**是對的。

**風險**
方案 B 直接踩 CLAUDE.md §8 / tc4-market-facts 兩條硬事實(同 symbol 跨 session 只推一邊;session reap 會把 refcount key 歸零、帶走 symbol 上游 feed),且要同步改跨檔契約「關機預算三方同源」的 shutdown_budget.TC4_LANE_DEPTH(run.ps1 / __main__.py / app.py lifespan 三方,由 tests/server/test_shutdown_budget.py 與 test_boot_window.py::TestShutdownLanes 釘住)。方案 A 要重寫 _req 的所有 caller。

---

## [HIGH] X4-01 · _eval_volume 每 tick 對 300 秒滾動窗做 sum()
- 區塊: X4-numeric — 跨切:數值計算與資料結構稽核(numpy/polars 落點盤點)
- 位置: copycat/live/signal_state.py:658 | 類別: algorithmic | 熱路徑: True | 工作量: S
- 驗證: **CONFIRMED**

**驗證理由**
逐字查核 signal_state.py:657-659 `window_vol = sum(qty for _ts, _price, qty in window)`,逐出在 :320-322 `cutoff = mono - self._cfg.surge_window_secs` / `while window and window[0][0] < cutoff: window.popleft()`。prod `data/signal_rules.json` 確有 `kind: vol_burst` / `enabled: true` / `window_secs: 300.0`。

我用專案 .venv 獨立重現(非採信掃描數字):以 SignalsConfig 預設建 4 個 slot、餵滿 3000 筆窗後量每 tick 成本 —— **vol_burst slot 101.03 µs/tick,其餘三個 slot 各 6.14 / 6.38 / 6.45 µs**,合計 115.55 µs/tick,其中 87% 是這一個 sum()。同時量 `sum(window)`:n=50 → 2.01 µs、300 → 9.93、1000 → 34.64、3000 → 99.15 µs,線性成立。對照 parse_stock_realtime(帶成交)23.12 µs —— 這一個 sum 在熱股上比整支解析還貴 4 倍。

頻率鏈追完(掃描沒追,但結論對它有利也有不利):`_handle_quote` → `if ingest:` 內 → `signal_hub.on_tick` → `if code not in self._watch: return`(set,150 檔)→ `for slot in self._slots.values()` 4 圈。但 `_make_slot` 的 `enabled = frozenset({rule["kind"]})`(signal_hub.py:455-462),所以 **_eval_volume 的 sum 每 tick 只跑 1 次,不是 4 次**。另有三道早退在 sum 之前:`"vol_burst" not in enabled`、`elapsed_min < vol_min_elapsed_min`(15 分 → 09:15 前不跑)、`avg_per_min <= 0`。

**校正後影響**
機制與 per-call 成本完全成立,但「critical」誇大了系統級負載。窗長 = 該檔過去 300 s 成交筆數;窗 3000 需要該檔持續 10 筆/s,只有最熱那一檔做得到,該檔成本 101 µs × 10/s = 1.01 ms/s。150 檔整體 = Σ(rate_c² × 300 × 33 ns),以「一檔 20/s + 149 檔各 2/s」的現實分布算約 10 ms/s ≈ 單核 1%。真正該在意的不是 CPU 百分比,而是**每 tick 處理成本在行情最熱時從 ~30 µs 膨脹到 ~130 µs**,而那正是訊號最該即時的時刻 —— 對「要改成高效能量化系統」這個目標,這是 p99 延遲問題不是吞吐問題。以 S 級工時換 O(n)→O(1),本區塊投報率最高的一條。

**證據**
```
# signal_state.py:657-659
window_min = self._cfg.surge_window_secs / 60
window_vol = sum(qty for _ts, _price, qty in window)   # O(len(window)),每 tick
ratio = window_vol / (avg_per_min * window_min)

# window 由 evaluate() 以時間逐出(signal_state.py:320-322):
cutoff = mono - self._cfg.surge_window_secs      # signals_config.py:29 預設 300.0 秒
while window and window[0][0] < cutoff:
    window.popleft()
```

**原建議修法**
在 SignalDetector 加 self._window_qty: dict[str, int],evaluate() append 時 += qty、popleft 時 -= qty,_eval_volume 改讀該值 → O(1)。qty 是 int,不會有浮點漂移。_window_qty 與 _window 同生命週期(reset_day / drop_code 同批清)。不需要任何套件。

**修法可行性查核**
可行,零套件,零跨檔契約。`_window` 全部參照只有 signal_state.py:192(宣告)/264(reset_day clear)/279(drop_code pop)/314(首 tick 建)/318(setdefault)/320-322(evict)/525、588(`_window_change_pct` 只讀 window[0]/[-1])/657(本體)—— 沒有任何外部寫入點,running sum 的生命週期綁得住。qty 是 int,累加精確無漂移,不需要誤差測試,但掃描建議的不變式測試(任意 push/pop 序列後 running_sum == sum(window))仍該寫,因為 314 那條首 tick 分支是**另一個建立點**,漏改就會讓 running sum 從第二筆起永久差一筆。PARAM_SPECS['vol_burst'] 與 tests/fixtures/signal_param_specs.json 不動,契約無風險。

更好的做法:這條與我下面 missed M1 一起做 —— 把 4 個 slot 共用一顆 detector(或至少共用 `_window`),running sum 就只需要維護一份,同時順手砍掉 M1 的 4× 重複。

**風險**
_eval_surge / _eval_pullback 也讀同一個 window 但只讀 window[0]/window[-1],不受影響。不動任何跨檔契約(PARAM_SPECS['vol_burst'] 的值域與 tests/fixtures/signal_param_specs.json 不變)。需補一條不變式測試:running_sum == sum(window) 在任意 push/pop 序列後恆成立。

---

## [HIGH] X4-02 · CorrState.correlations() 每秒在 event loop 上停 13.6 ms
- 區塊: X4-numeric — 跨切:數值計算與資料結構稽核(numpy/polars 落點盤點)
- 位置: copycat/live/corr_state.py:82-126(呼叫點 copycat/server/corr_engine.py:543 → tick_once corr_engine.py:322) | 類別: blocking-io | 熱路徑: True | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
檔頭宣稱逐字核對:corr_state.py:5-7 確實寫著「`statistics.correlation` 對 1800 樣本實測 0.15 ms,整輪 tick 外推不到 1 ms」。我在專案 .venv 用 configs/correlation.json 的真實 11 腿建 CorrState、推 2000 筆滿窗後量:**correlations() = 11.85 ms**(稀疏腿版 9.32 ms)。檔頭宣稱錯約 12 倍,成立。

「無條件呼叫」也成立:corr_engine.py:322 `tick_once` 尾端 `if self._broadcast is not None: self._broadcast(self.state())`,而 app.py:1003 注入 `broadcast=corr_ws.publish`(bound method,永不為 None),所以有沒有 WS client 都照算。`_run` 迴圈 `await asyncio.sleep(self._tick_secs)`,tick_secs 預設 1.0。

程式碼證據逐行核對無誤:`leg_by_ts = dict(leg_series)`(:91)、`for ts, base_mid in base_series`(:95)、`return [row for row in out if row[0] >= now - self._max_window]`(:110)、三窗各兩次 list comp(:119-121)。

兩處小誤:base 在 `self._legs = [k for k in leg_keys if k != base]` 被排除,所以是 **10 腿不是 11**、**30 次 correlation 不是 33**(我的執行結果 `len(result) == 10`)。不影響結論。

**校正後影響**
11.9 ms/s = event loop 1.2% duty,不是「全系統最大 CPU 消耗」;但它是**最大的單一同步停頓**(對照 apply_backfill 10 ms 但一天一檔一次、breadth 每 10 s、payoff ~2 ms/s),而且停的正是同一條要收 tick / 做 WS fanout / 回 HTTP 的 loop。每秒固定 12 ms 的 jitter 對看盤無感,對「高效能量化」的下單延遲有感。降為 high(理由:CPU 量級不到 critical,但它是唯一一個「每秒都準時發生、且完全免費就能砍掉大半」的停頓)。

**證據**
```
# corr_state.py 檔頭 5-7 行的宣稱:
# 「statistics.correlation 對 1800 樣本實測 0.15 ms,整輪 tick 外推不到 1 ms」
# 但那只量了 correlation 一次,沒量整支 correlations()。實際:
leg_by_ts = dict(leg_series)                        # 每腿重建 1800-entry dict
for ts, base_mid in base_series:                    # 每腿重掃 1800 筆,math.log x2/樣本
    rb = log_return(prev_base, base_mid); rl = log_return(prev_leg, leg_mid)
return [row for row in out if row[0] >= now - self._max_window]   # 又掃一次
...
for window in self._windows:                        # 3 窗
    xs = [rb for ts, rb, _ in paired if ts >= cutoff]
    ys = [rl for ts, _, rl in paired if ts >= cutoff]
```

**原建議修法**
三段:(1) 零依賴 —— push() 時就把新一筆 (ts, rb, rl) 算好 append 進 per-leg deque,_evict 同步逐出,correlations() 只剩切窗+算 r,預期 13.6→~7 ms;(2) paired 已按 ts 升冪 → bisect_left 找 cutoff 切片取代三次全掃,再省 ~1 ms;(3) numpy 全向量化(base 與 10 腿存 ndarray ring buffer,一次算 10 腿×3 窗),**實測 0.090 ms = 151x**。另外無論選哪段,都該讓 state() 在 WsBroadcaster 無 client 時跳過 correlations()。

**修法可行性查核**
三段都查過:
(1) 增量報酬 —— **不違反檔頭理由**,判讀正確:檔頭禁的是增量維護 Σx/Σx²/Σxy(統計量),本案增量的是「報酬」這個原始樣本,相關係數本身仍每次整批重算。但有兩個實作陷阱掃描沒說:push() 在 session 變更時只 `series.clear()`(corr_state.py:66-68),新加的 returns deque 必須在**同一個分支**清,漏了就是跨場汙染;且 `_adjacent_tol` 的相鄰判定要照搬,不能簡化成「上一筆」。
(2) bisect_left 切窗 —— paired 依 ts 升冪成立(由 base_series 順序產生),Python 3.10+ 的 `bisect(key=)` 可用。安全。
(3) numpy 全向量化 —— **這一段我不建議現在做**:numpy 未裝在專案 .venv(我確認過),而 corr_state 在 `copycat/live/` = live server import 路徑上,拉進去等於把 `dependencies = []` 這件事從「離線可選」變成「runtime 必要」。且 statistics.correlation 用 fsum、numpy 用 pairwise,1e-15 差異雖然前端看不到,卻會讓既有測試若有逐值斷言就紅。

**最便宜且我認為該先做的一刀掃描擺在附註**:`state()` 在無 client 時跳過 correlations。查過 `corr.state()` 還有兩個呼叫端(app.py:1986 REST `/api/corr`、:1997 WS seed),兩者都是 on-demand,跳過週期計算不影響它們。WsBroadcaster 目前沒有公開的 client 數 API(只在 log 用 `len(self._clients)`),要加一個三行的 `has_clients()`。這一刀是 S 級、零數值風險,且在沒開 corr 分頁時直接歸零 —— 應排在 (1)(2) 之前。

**風險**
檔頭的設計理由是「增量滑動窗的浮點誤差會隨執行時間累積」。修法 1/2 **不違反**它 —— 逐出的是『報酬』不是『統計量』,相關係數本身仍每次整批重算;被禁的是增量維護 Σx/Σx²/Σxy,本提案不碰。修法 3 把 statistics.correlation(fsum 高精度)換成 numpy 兩趟累加,結果在 1e-15 量級有差(前端顯示到小數第 2 位,實務不可見),且要拉進 numpy 依賴。CLAUDE.md §4 的「江波圖調色盤色數 ≥ 腿數」與「sparse 旗標」只約束腿集合,不動。

---

## [HIGH] X4-06 · 21,254 個 1K JSON 小檔:全掃 18 s,55% 花在建 Bar1K;fade_pipeline 同批重讀 2–3 遍
- 區塊: X4-numeric — 跨切:數值計算與資料結構稽核(numpy/polars 落點盤點)
- 位置: copycat/data/store.py:41-60(呼叫端 copycat/backtest/fade_pipeline.py:97、:444、:703) | 類別: data-structure | 熱路徑: False | 工作量: L
- 驗證: **CONFIRMED**

**驗證理由**
檔案事實全部親自數過:`find data/1k -name '*.json' | wc -l` = **21,254**,`du -sh data/1k` = **294M**。實跑 400 個隨機檔的 `read_bars`:**0.589 ms/檔、平均 269 bar**,外推全量 **12.5 s**(熱 cache;掃描報 18 s 冷讀,同量級)。store.py:41-60 逐行核對無誤。`Bar1K` 是 `frozen=True, slots=True`(data/models.py:8),所以 55% 花在建構的說法合理(slots 版建構反而稍慢,見 X4-14)。

**但「2–3 遍」嚴重低估,實際是 ~19 遍 —— 這是掃描自己的 fix 最有價值的那一項,而它把價值講小了 6 倍。** 我追了呼叫鏈:fade_pipeline.py:674 `for arm in ALL_ARMS:` → :675 `for params in arm.anchor_params:` → `run_fade_arm(...)`,而 **:444 的 `read_bars` 就在 `run_fade_arm` 內、對每個 sample 各讀一次**。我實際載入 `ALL_ARMS` 數過:7 臂,anchor_params 各 3/3/3/3/1/1/3 = **17 組**。所以 :444 那一趟會對整個 sample 集重跑 17 次,再加 :97(universe 建立)與 :703(diagnose)= **約 19 次全量重讀**。

**校正後影響**
維持 high 並上修:以 N 個 sample、0.589 ms/檔算,19 遍 = 19 × N × 0.589 ms。N=3,000 時 ≈ 34 s、N=10,000 時 ≈ 112 s,純 IO/解析,每次調參都重付。這是離線層**單一最大、且最便宜可消**的成本 —— 比 X4-05 的 3.3 s 大一個量級。

**證據**
```
def read_bars(data_dir, stock_id, date):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Bar1K(m=int(r[0]), open=r[1], high=r[2], low=r[3], close=r[4],
                  volume=r[5], up_volume=r[6], down_volume=r[7], unch_volume=r[8])
            for r in payload["bars"]]

# fade_pipeline 三處各讀一趟,無 cache:
#   :97   t1_bars = read_bars(data_dir, stock_id, t1_date)
#   :444  bars = read_bars(data_dir, sample.stock_id, sample.t1_date)
#   :703  (s, read_bars(data_dir, s.stock_id, s.t1_date) or []) for s in samples
```

**原建議修法**
(1) **立刻可做、零依賴**:fade_pipeline 內 memo read_bars 結果({(sid,date): bars}),消掉 2–3 倍重讀;(2) json.loads → orjson.loads;(3) 結構性解:把 21,254 個 JSON 併成按月分割的 parquet(data/1k/YYYY-MM.parquet,欄 = stock_id,date,m,o,h,l,c,v,up,down,unch),polars 讀 parquet 實測 1M 列 22 ms,全量 1K ≈ 5.7M 列 → 預期 <1 s(vs 現況 18 s),磁碟 294 MB → 估 30–50 MB;(4) 模擬層改吃 per-sample numpy 欄(與 X4-07 同批做)。

**修法可行性查核**
(1) **memo `read_bars` —— 這是全報告最該先做的一條,零依賴、S 級、~19x。** 但掃描沒算記憶體:key = (stock_id, t1_date),N=5,000 sample → 5,000 × 270 bar × Bar1K(slots,約 112 B)≈ 150 MB,再加 list 本體。可接受,但要有上限或明確記在 design(別無腦 `@lru_cache(None)`)。實作點建議放在 `run_fade_pipeline` 層做一次 prefetch dict 往下傳,而不是包在 `read_bars` 上 —— 後者會把 `replay/runner.py`、`data/import_neigui.py` 這些不該 cache 的呼叫端一起吃進去。
(2) orjson.loads:只值 2.3x 的 45% 那一段,且要新依賴;做完 (1) 之後這一項基本無感,建議跳過。
(3) 月度 parquet:結構上對,但 L 級且會牽動 `simulate_fade_sample` 等所有 `b.close` 存取點。`write_bars` 的不變式檢查(store.py:18-19「bars 未按分鐘索引遞增」)要保留 —— 掃描說得對。**先做 (1),量完再決定要不要 (3)。**

**風險**
write_bars 有不變式檢查(store.py:18-19「bars 未按分鐘索引遞增」),parquet 版要保留。Bar1K 是 frozen+slots dataclass,全庫大量 b.close 屬性存取 —— 改欄式會牽動 simulate_fade_sample 等所有使用點(L 級)。data/ 是 gitignored 本機產物,轉檔**不動版控、不動任何跨檔契約**,可保留 JSON 寫入路徑當 fallback。

---

## [HIGH] X4-07 · fade_* 逐 bar 模擬不可向量化;真正槓桿是全庫零 multiprocessing,16 核只用 1 核
- 區塊: X4-numeric — 跨切:數值計算與資料結構稽核(numpy/polars 落點盤點)
- 位置: copycat/backtest/fade_simulate.py:163-260(simulate_fade_sample 主迴圈)、copycat/backtest/fade_cells.py:213-241(_simulate_cell_trades) | 類別: concurrency | 熱路徑: False | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
兩個事實親自驗過:`grep -rn 'multiprocessing|ProcessPool|concurrent.futures' copycat` **零命中**;`os.cpu_count()` = **16**;Python 3.13.13。

fade_simulate.py:163 起的主迴圈逐行讀過:`locked = b.low >= t1_limit - eps` → `continue`、`if b.low < running_low: ... else: stall += 1`、`outer_win.append(...)`、`cum_delta += ...`,之後 forced_fills / stop_fills / target_fill / tp 多條**早退 return**。這確實是路徑相依狀態機,numpy/polars 沒有對應原語,掃描判斷正確。fade_cells.py 的 `for b in cfg.struct_stop_buffers: for kind, variant, param, uni, base_key in specs:` 雙層迴圈也確認存在(:650-651)。

**校正後影響**
「16 核只用 1 核」是硬事實,離線層最大的結構性槓桿。但 **8–12x 是推估不是量測**,而且有一個掃描沒處理的 Windows 具體障礙(見下),實際可能落在 4–8x。維持 high,但驗收前不要把 10x 寫進 spec。

**證據**
```
# fade_simulate.py:163 起 —— 狀態機 + 早退,numpy/polars 沒有對應原語
for b in post:
    locked = b.low >= t1_limit - eps
    if locked: ...; continue
    if b.low < running_low: running_low = b.low; stall = 0
    else: stall += 1
    running_high = max(running_high, b.high)
    outer_win.append((b.up_volume, b.down_volume))
    cum_delta += b.up_volume - b.down_volume
    ...   # 之後是多條停損/停利的早退 return

# fade_cells.py:650-651 —— 雙層迴圈把工作量乘上去
for b in cfg.struct_stop_buffers:
    for kind, variant, param, uni, base_key in specs:
```

**原建議修法**
**🥇 最高 CP 值、零依賴:concurrent.futures.ProcessPoolExecutor 切 universe**,預期 8–12x,不引入任何第三方套件、不改數值語意。Windows 上 spawn 成本高 → 用粗 chunksize(每 worker 一整個 spec 或一大塊 universe);FadeSample / Bar1K 都是 slots dataclass,可 pickle。第二選項 numba @njit 把主迴圈改吃 6 個 float64 array,預期 20–50x —— 但 LLVM ~200 MB + 首次 JIT 數秒 + 對 Python 3.13 的支援時程要先驗證,**建議先拿 multiprocessing 的 10x,不夠再評估**。Cython/mypyc 在 Windows 要 MSVC,維護成本高;PyPy 與 pyzmq/comtypes/pywin32 不相容,明確排除。

**修法可行性查核**
方向對,但**掃描漏了 Windows spawn 的最大障礙,這會直接決定切法**:`run_fade_arm` 的參數裡帶著 `daily`(= `DailyIndex`,我實測 3.27 s 載入、百萬個 `_DayRow` 物件)。Windows 沒有 fork,ProcessPoolExecutor 走 spawn,每個 worker 要嘛 **pickle 這顆百 MB 索引一次**(16 個 worker × 上百 MB 傳輸與反序列化),要嘛在 worker 內**重載 3.27 s × 16**。掃描說「FadeSample / Bar1K 都是 slots dataclass,可 pickle,OK」——但 pickle 得動的不是它們,是 DailyIndex。
可行解:用 `ProcessPoolExecutor(initializer=...)` 讓每個 worker 起手載一次 DailyIndex(一次性 3.3 s × 16 並行 ≈ 3.3 s 牆鐘),然後只傳 sample 切片;或乾脆在 **arm × params 這一層切 17 份**(天然 17 個獨立工作單元,粒度粗、payload 小),那是最自然的切法,且剛好對上 X4-06 的 19 次重讀 —— 兩條一起做時要注意 memo 在 process 間不共享,反而變成每 worker 各自一份 cache(記憶體 × worker 數),這一點必須先量。
numba 判斷同意(先拿 multiprocessing);PyPy 與 pyzmq/comtypes 不相容的排除同意;Cython/mypyc 排除同意。
**驗收判準用 `python -m copycat compare out/before out/after` 逐字相同 —— 這條我查過確實是專案既有 CLI(CLAUDE.md §1 有列),是很好的機驗,採納。**

**風險**
平行化**不改任何數值**,但要確認 logger 與 dataclasses.replace(cfg, ...) 在 worker 內行為一致(fade_cells.py:302 的 stress_cfg 要在 worker 內重建或一起 pickle)。**驗收判準 = 平行化前後跑 `python -m copycat compare out/before out/after` 逐字相同** —— 這是本專案既有工具,剛好當「重構不改數字」的機驗。

---

## [HIGH] X5-01 · tick tape 用 Python 物件存:76 萬個 instance 把 full GC 推到 105 ms 全 process 停頓
- 區塊: X5-memory — 跨切:記憶體、配置與長跑穩定性
- 位置: copycat/live/stock_state.py:47,148;copycat/live/stock_models.py:46-61 | 類別: allocation | 熱路徑: True | 工作量: L
- 驗證: **CONFIRMED**

**驗證理由**
行號逐字對上:`stock_state.py:19 _TICKS_MAXLEN = 20_000`、`:47 ticks: deque[StockTick] = field(...)`、`:148 self.ticks.append(tick)`;`stock_models.py:46 @dataclass(frozen=True) class StockTick` 確實沒有 slots。我自己重跑 bench(150 state × 600k ingest):gen0×292 / gen1×26 / **gen2×2、in-run max 78.2 ms**、強制 `gc.collect(2)` **108.6 ms**、tracked 654,533 —— 與報告的 292/26/3、104.6 ms 幾乎逐項吻合。

**而且前提比報告自己以為的更硬**:報告說「所有數字都是離線 bench,沒有一個是 prod 實錄」,這句話是錯的 —— prod log 裡就有。`grep 'backfill .*ticks' logs/server-20260911-0036.log` 聚合(per code 取最大值):**90 檔、381,107 筆、median 2,502、max 30,598(2303)**。以自選上限 150 檔外推 ≈ 63 萬筆/日,報告的 60 萬估值幾乎是實測值。

另補一條把前提釘死的呼叫鏈:`stock_engine.py:1316 if tick is not None and state.ingest(tick)` **不受 `_tick_targets` / view 契約約束**(view 只 gate 下面的 `_pending_ticks`),而 `:1300-1310` 的首筆成交入列 + `:1688 state.apply_backfill(...)` 會把**當日全量** tick 灌進每一檔訂閱碼的 deque。所以「150 檔各一份全日 tape」不是最壞情境,是常態。

**校正後影響**
實測留存:201 B/tick(非 254 B)× 61 萬 ≈ 123 MiB;tracked 61 萬物件 → full GC 71–108 ms,**一天 2–3 次**、時點由配置節奏決定不可預測。以現況(唯讀看盤 + 人工下單)是 high 不是 critical:2–3 次/日的 100 ms 停頓不會讓看盤失效。報告把它寫成 critical 是**建立在「要下實單」這個未來前提**上的 —— 那個前提成立時它才是紅線,現在還不是。結構上界 762 MiB 幾乎不可能到(prod 只有 2 檔破 20k)。

**證據**
```
# live/stock_state.py:19,47
_TICKS_MAXLEN = 20_000
ticks: deque[StockTick] = field(default_factory=lambda: deque(maxlen=_TICKS_MAXLEN))
# live/stock_state.py:148
def _apply(self, tick: StockTick) -> None:
    self.ticks.append(tick)
# live/stock_models.py:46  ← 注意沒有 slots
@dataclass(frozen=True)
class StockTick:
    code: str; price_milli: int; qty: int; cum_vol: int; time: str; ...

# 對照:copycat/backtest/ copycat/engine/ copycat/data/ 的離線 dataclass 全帶 slots=True(18 處),
# 線上熱路徑的三個 model 一個都沒有 —— 這是反過來的。
```

**原建議修法**
把 ticks 從物件序列改成欄式 tape。實測對照(bench_columnar.py,stdlib-only 零新相依):現況 600k StockTick = 145 MiB / gen2 79–105 ms / tracked 613,401;array.array 欄式 = 12.8 MiB / gen2 0.4 ms / tracked 9,416 —— 記憶體 11×、GC 停頓 200× 改善。形狀:class ColumnTape 用 __slots__ 裝 6 條 array（t/p/q 用 'i'、side 用 'b'、b/a 用 'i'）。進階版用 numpy 預配置 ring buffer,連 append 攤提都省,且 VWAP/VP/minutes 可向量化。三個 model(StockTick/StockBook/StockMeta)一併加 slots=True(實測省 19%)。

**修法可行性查核**
方向對,但**分期錯了**。我實測三種形態(600k 筆):no-slots 201 B / 114.9 MiB / gc 71.8 ms;`slots=True` 153 B / 87.4 MiB / **gc 45.9 ms**;array 欄式 51 B / 29.4 MiB / **gc 0.8 ms**。

(a) 報告把 slots 只記在 X5-06 且只說「省 19%」—— 實測是**省 24% 記憶體 + 砍 36% GC 停頓**,一行 decorator 參數、零契約風險(全庫對 StockTick 無 `asdict` / `__dict__` / `vars()`,`dataclasses.replace` 與 slots 相容)。**應該先做 slots + 量測,再決定要不要做 L 級欄式重寫**。
(b) 報告宣稱欄式「記憶體 11×」是樂觀的:那是把欄位壓成 int32 才算得出來。要保住 wire 六欄(t/p/q/side/b/a)**加上 dedup 必需的 cum_vol**,實測是 29.4 MiB vs 114.9 MiB = **4×**;GC 停頓 90× 才是真賣點。
(c) risk 段列的契約(§4「seq 兩口徑」、`apply_backfill` 兩迴圈不對稱、vp_parity golden)都查證屬實,而且它漏了一個:`ticks` 的外部讀者只有 `stock_state` 自己三處(`last` / survivors / `snapshot`),`state.last` 才是跨檔介面(`stock_engine.py:781,1471,1720,1830`)—— 欄式化要多留一支「重建單筆 StockTick」的出口,那支本身不貴(每次呼叫一筆)。
(d) numpy 路線在此不必要:`.venv` 目前**沒有** numpy(只有系統 Python 有 2.4.4),而 array.array 已把 GC 停頓打到 0.8 ms,再引相依買不到什麼。

**風險**
snapshot() 的 ticks wire 形狀不可變 —— CLAUDE.md §4「個股 seq 的兩個口徑」:前端 lib/stock-accum.ts::fromSnapshot 靠 snap.seq 由尾回推指派 React key,漂掉的症狀是成交明細 tbody 靜默整片重掛。欄式只換內部儲存、出口才展開成現有 dict 列表 → wire 零改動。apply_backfill(stock_state.py:98-139)的 survivor 篩選要改欄式掃描,而它那段「兩個迴圈去重不對稱是刻意保留」的語意必須逐字保留(改了會動張數與內外盤累積值)。signal_hub.on_tick 收的仍是 StockTick 物件(短命,不進 GC 統計)。vp_parity.json golden 要重跑。

---

## [HIGH] X5-04 · StockEngine._states 與 BarsCache._hist 沒有 code 維度的淘汰;bars.py 的註解前提已失效
- 區塊: X5-memory — 跨切:記憶體、配置與長跑穩定性
- 位置: copycat/server/stock_engine.py:293,297-299,461,472;copycat/server/bars.py:237,336-359 | 類別: data-structure | 熱路徑: False | 工作量: M
- 驗證: **CONFIRMED**

**驗證理由**
三項事實全部查證屬實,而且**規模比報告估的更大**。
(1) `_states`:`stock_engine.py:293` 宣告,`:461` / `:472` 兩處 `setdefault`,全庫 `grep _states` **沒有任何 pop / del**;`:297-299` 的註解自陳「只增不減」。而且每一檔被畫過圖的碼都會經 `:1688 state.apply_backfill(...)` 灌進**當日全量** tick —— 所以「點過就留一份全日 tape」不是推測。
(2) `bars.py:339` 的註解逐字是「(股號受 watchlist 50 檔上限約束)」—— 兩個前提都假:上限已是 150(§4),而 `_hist` 的鍵是 `ck = f"{code}:{session}"`(`:665`),來源是**任何被請求過 bars 的碼**,與 watchlist 無關。
(3) `prune` 只有 `:344-346` 的日期 floor(DAYS_MAX*2 = 60 日),code 維度零剪除 —— 屬實。
**但報告把 `_daily` 一起列進來是不對的**:`:347-348 for key in [k for k in self._daily if k[1] != today_iso]: del self._daily[key]` 是每日一刀清光,`_daily` 沒有這個問題。

**校正後影響**
**報告低估了 `_hist`**:它假設 5 日窗,但前端 `useStockBars.ts:30 export const MINUTE_DAYS = 30` —— 每開一檔圖就永久 memo **30 天的 1 分 K**。實測 338 B/bar × 20 交易日 × 270 根 = **1.74 MiB/檔**,150 檔 = **261 MiB**(報告說 175 MiB),期貨 allday 每檔 7.3 MiB。
**但報告也高估了它的 GC 影響**:我實測 324,000 個 Bar dict 進記憶體後 `len(gc.get_objects())` 從 13,201 **降到** 12,723、`gc.collect(2)` 只花 6.5 ms —— CPython 的 dict-untracking 會把「值全是 str/int」的 dict 移出 GC 追蹤。所以 `_hist` 是純 **RSS 問題,不是停頓問題**;報告寫的「每個死掉的 StockDayState 裡的 tick 都還在被 gen2 掃描」只對 `_states` 成立(StockTick 是 user class,恆被追蹤),對 `_hist` 不成立。
`_states` 側:每檔被開過圖的碼帶一份全日 tape,實測 median 2,502 筆 × 201 B ≈ 0.5 MiB/檔,重度瀏覽一天 100–400 檔 = 50–200 MiB,且**這些是 tracked 物件**,會直接疊進 X5-01 的 gen2 掃描成本。報告的 400 MiB 是上緣但同一個數量級。

**證據**
```
# server/stock_engine.py:297-299(註解自陳)
# 只增不減(同 `_states`):退訂後殘留的鍵指向仍存在的 state …
self._symbol_to_key: dict[str, str] = {}
# :461,472 每次 _acquire / set_main 都 setdefault,全庫無對應的 pop
self._states.setdefault(code, StockDayState())

# server/bars.py:339-346 prune 只按日期,code 維度無剪除
floor = (today - _dt.timedelta(days=DAYS_MAX * 2)).isoformat()
for key in [k for k in self._hist if k[1] < floor]:
    del self._hist[key]
# bars.py:339 註解:「`_hist` / `_daily` 的成長來自**日期維度**(股號受 watchlist 50 檔上限約束)」
```

**原建議修法**
_states 改 LRU:保留 = 自選全員 ∪ 主圖 ∪ 各連線 _views 聯集 ∪ 最近 N 個,其餘 evict;淘汰點掛既有的 _flush_watchlist_loop(1 s)或 _checkpoint_loop(60 s),不新增 task。BarsCache._hist 加 per-code LRU(記最後存取時刻,超過 N 分鐘未查就整組刪)。順手把 bars.py:339 的註解改成引用 WATCHLIST_LIMIT 與實測值。

**修法可行性查核**
可行,但要補兩點。
(a) 「只 evict 不在任何持有者集合裡的 code,讓下一次請求走 `_EMPTY_LIGHT` + `_backfill_wanted` 自然重建」—— 這條路查證是存在且測過的(`group_snapshot` docstring 列的四道 guard + `_backfill_wanted`),**但重建成本不是零**:重建 = 一次 SubHistory 全日回補,而 `_BACKFILL_MAX_FAILS=3` / `_backfill_gave_up` 冷卻會讓「剛被 evict 又馬上被點開」的檔落進失敗計數。LRU 的保留集合必須含「最近 N 分鐘看過的」,不能只含當下持有者。
(b) risk 段列的三個不可碰點(`put_hist_range` 負向快取只寫到掃過的最後一天 `:275`、`MIDNIGHT_BUFFER_END` `:685-695`、`_today_ttl`)查證都在、都對。
(c) **優先序建議與報告不同**:既然 `_hist` 不進 GC 追蹤,它的 per-code LRU 是純省 RSS,可以晚做;先做的應該是 `_states` 的 LRU(那才會回饋到 X5-01 的停頓),或更便宜的 —— 把 `MINUTE_DAYS` 從 30 調小(前端一行),對 261 MiB 是線性削減,零後端改動。這條報告完全沒提。
(d) 順手改 `bars.py:339` 註解那條,對(而且是必要的:它現在是會誤導下一個人的假前提)。

**風險**
evict 掉還在用的 state = 該檔前端 accum 與後端 seq 斷掉。安全做法是只 evict 不在任何持有者集合裡的 code,讓下一次請求走 _EMPTY_LIGHT + _backfill_wanted 自然重建(那條路已存在且測過)。加 code 維度 LRU 時絕不可碰 put_hist_range 的「負向快取只寫到有證據掃過的最後一天」(bars.py:266,review P1-2)、MIDNIGHT_BUFFER_END 午夜緩衝(bars.py:685-695,TZ-2)、_today_ttl 的單一定義。CLAUDE.md §4 的 WATCHLIST_LIMIT「效能預算註解」第二類讀者要同步更新。

---

## [HIGH] X5-05 · 全庫零 GC 調參、零記憶體可觀測性
- 區塊: X5-memory — 跨切:記憶體、配置與長跑穩定性
- 位置: 全庫(grep -rn "import gc" copycat/ 零命中);copycat/server/app.py health endpoint | 類別: observability | 熱路徑: False | 工作量: S
- 驗證: **CONFIRMED**

**驗證理由**
三項 evidence 全部重跑驗證:`grep -rn 'import gc|gc.(freeze|disable|collect|set_threshold)' copycat/` **零命中**;`app.py:1290-1296 health()` 逐字只有 `return request.app.state.build.as_dict()`,docstring 逐字「刻意不含引擎健康度」;`ws.py:56-62` 的 `dropped` / `window_dropped` 註解逐字「`/api/health` 刻意不含引擎健康度…prod 無讀者」。`gc.get_threshold()` 在本機 3.13.13 上確為 `(2000, 10, 10)` 未調。

**校正後影響**
論斷成立且是本區塊優先序第一。但報告自己那句「本報告所有數字都是離線 bench,**沒有一個是 prod 實錄**」是錯的,而且錯得可惜 —— logs/ 裡就有現成的 prod 實錄可以驗它自己的核心前提(見我 missed 的 M3)。把這句留著會讓 user 以為整份報告懸空,實際上最關鍵的那個前提(60 萬筆/日)已經有 prod 佐證。

**證據**
```
$ grep -rn "import gc|gc.(freeze|disable|collect|set_threshold)" copycat/
(無輸出)
$ python -c "import gc; print(gc.get_threshold())"
(2000, 10, 10)      # 3.13 預設,未調

# server/app.py health() 的全部內容
return request.app.state.build.as_dict()   # 只有 git_sha 等建置身分
# docstring:「刻意不含引擎健康度」

# 全庫唯一的壓力指標,而且刻意不進 /api/health:
# server/ws.py:56-62  self.dropped / self.window_dropped
```

**原建議修法**
(1) gc.callbacks 記 full GC 停頓(phase=="start" 記時刻、"stop" 算差),超過 50 ms 印固定字串 WARNING,錨「GC 停頓」—— 一天約 300 次 callback,開銷完全可忽略;盤後 grep 判準:現況必然命中(gen2 約 105 ms),改完 X5-01 後應歸零,這就是修法生效的機驗判準。(2) 掛既有 _checkpoint_loop(60 s 拍,每 5 拍印一次,不新增 task)印一行:RSS(ctypes 呼 K32GetProcessMemoryInfo,零相依)、len(gc.get_objects())、len(engine._states)、Σlen(state.ticks)、BarsCache 三個 dict 條目數、各 broadcaster max qsize。(3) boot 完成後 gc.freeze()(凍住 import 出來的約 13k 物件,收益小但零風險零成本)。(4) 在 tc4._listen_loop 加每 60 s 一行「收 n 則/分、峰值 n 則/秒」—— 沒有這個數字,所有 MB/s 都是推算。

**修法可行性查核**
四條修法都可行、風險確實極低,但有兩處要校正。
(a) **(1) 的 grep 判準「改完 X5-01 後應歸零」是錯的**。我實測:把 600k StockTick 釋放後,剩下的長駐結構 `gc.collect(2)` 仍有 7.4 ms(324k Bar dict 那批)。歸零的是「> 50 ms」那條門檻,不是 GC 停頓本身。把判準寫成「歸零」會在第一次沒歸零時被當成修法失敗。正確寫法:記**分佈**(p50/p99/max),改前 max 71–108 ms、改後 max 應 < 10 ms。
(b) **(4) 的 tc4 收訊率計數器是四條裡最有價值的一條**,因為整份報告的「300–1,000 則/秒」全是推估;掛在 `_listen_loop` 的 `self._last_msg = time.monotonic()` 那一行旁邊即可,零額外分支。
(c) (2) 的落點選 `_checkpoint_loop`(`stock_engine.py:1129-1145`,`_checkpoint_secs = 60.0`)確實不新增 task,對。RSS 走 ctypes `K32GetProcessMemoryInfo` 在 Windows 上可行、零相依。但 `len(gc.get_objects())` **本身會配置一個含全部物件的 list**(61 萬筆時是一次 5 MB 級的配置 + 一次 stop-the-world 走訪)—— 每 5 分鐘一次可接受,但別誤用到更高頻;更便宜的替代是 `sum(gc.get_count())` + `gc.get_stats()` 的 collections 累計。
(d) (3) `gc.freeze()` 的定位對(零風險、收益小、絕不可當 X5-01 替代)。
(e) 另開 `/api/health/mem` 不動既有 health 的拍板 —— 對,那條 docstring 是明文契約。

**風險**
極低。/api/health 「刻意不含引擎健康度」是既有拍板,所以另開 /api/health/mem,不動那條。gc.freeze() 只影響 boot 時已存在的物件,不改任何行為。

---

