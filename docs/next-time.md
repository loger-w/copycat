
## 2026-07-07(tday-join-ga-backtest 收尾沉澱)

- [ ] simulate 完整 derived-series 預計算重構(review F2 只做了 anchor 網格限定;若 Phase B 全量變慢再做)

## 2026-07-11(fade-round-1 收尾 review P2 彙總,18 條聚類)

- [ ] fade pipeline 效能候選(6h 長跑;/perf 先 profile 再動):診斷段重讀全部 1K bars(run 時已讀過)、optimize_rule_tp 重算 optimize_rule_stops 已算過的 rule mask、guard_dist_grid 每格全量重模擬、by_source O(sources×trades) 重掃

## 2026-07-14(fade-round-2 自評 review P2 彙總)

- [ ] fade 診斷效能候選(/perf 先 profile):diagnose_pool_fade 對同一 universe base+stress+lock_grid 共 5 次全量重模擬(可單迴圈多配置);evaluate_cells 每 cell×variant 各 base/stress 兩趟 + baseline ×4 = 16 趟(觸發判定可先算一次共用)
- [ ] write_pool_fade_report / write_cells_report 兩份 markdown 表建構結構相似(第三份出現時抽共用 table builder)
- [ ] fade_cells 新增 cell 需改多點(find fn / _simulate_cell_trades 分支 / specs 列表 / config):cell 數 >4 時抽 registry
- [ ] fade_cells find_cell_a_entry 的 headroom 除式無 b.close>0 防禦(實際 1K 資料恆正;若接入外部資料源先補 guard)
- [ ] backfill_brokers/label_events 對 FinMind 非數值欄位(如 'N/A')無韌性(現況未觀察到;出現時在 aggregate 層加 tolerant parse + 計數)

## 2026-07-15(fade-round-3 自評 review P2 彙總,8 條聚類)

- [ ] evaluate_cells_from_universe 頂層 round gate 分岔:再加一輪會變 if-elif chain,屆時抽 evaluator factory
- [ ] 底倉格 grid 對 in_w 掃 6 次(單次分桶可 O(n),n 小暫無感)
- [ ] run_cells 三次 build_fade_universe(cellb 可由 main 超集記憶體過濾,現況重讀 1K JSON)
- [ ] validate_disaster_fields 在 _simulate_core 每 call 驗一次(GA 熱迴圈微耗;可改 config frozen 後驗一次的快取)

## 2026-07-16(fade-round-4 自評 review P2 彙總,12 條聚類)

- [ ] fade_anatomy 效能候選(單次跑分鐘級,量級可接受;/perf 先 profile):flush_anatomy 每個 z 全宇宙重掃(可單趟收三個 z)、hl_anatomy 每個 k × arm 重算 entry idx(可 cache)、_evaluate_round4 消融 5 組 × 5 變體 = 25 趟全量模擬
- [ ] check_flush_exit(cfg 驅動)與 _tp1(combo 驅動)結構重複但錨不同(進場後最低 vs running_low 含 trig)——已在 docstring 註明差異;若 Phase B 網格路徑退役,_tp1 可刪併

## 2026-07-17(fade-round-5 收尾 review P2 彙總,8 finder → 6 條)

- [ ] round5 效能候選(/perf 先 profile):stress 跑法重執行 entry_fn 全宇宙掃描(進場 idx 不依 run_cfg)、樣本預算表 4×全宇宙重掃(可單趟 _iter_votes 同時判多個 S)、消融 3 單訊號各自重跑狀態機
- [ ] 敏感度區塊複製貼上(S/c/m 三塊近同)+ disaster_off 手刻出異形 dict shape + round 輪次 dispatch 鏈成長(round 6 時考慮 active_round 單點解析);flow_flip_anatomy 出現率分母含 len(bars)<2 跳過日(輕微低估,不影響判準)

## 2026-07-18(txo-aggregate-pnl Phase 4 自評 P2 彙總,10 條聚類)

- [ ] 觀測性:前端 WS 無 heartbeat 判停(server 靜默時段分不出斷線 vs 無變更;考慮 server 週期 keepalive frame + client stale timer,週一盤中觀察真實需求再定)
- [ ] engine._run_handover 重試時 re-subscribe 與 activate 的 unsubscribe 不對稱,若改主動觸發自癒要先收斂這段

## 2026-07-19(dq4-order-phase1 Phase 4 自評 P2 彙總,15 條聚類,shortSymbol/BLOCKED_REASON 已本輪吸收)

- [ ] 錯誤碼三層對照(backend _TRADE_ERROR_MAP / frontend TRADE_ERROR_TEXT / 測試字面值)無單一 source:新增錯誤碼要動多處;若錯誤碼家族再擴,考慮 codegen 或 shared JSON(現況 frontend 未知碼原樣顯示 = 安全漂移)
- [ ] trade 效能微優化候選(手動單低頻,全部先不動;若未來策略自動下單高頻化再 /perf):orders_view 每 poll 重建 list、account_view 每呼叫 sorted、orderable_symbols 每呼叫重建 set
- [ ] parse_execution_report 的 err_code 判定含 0/"0" 白名單,真值域(design §8 #3)整合實測後回頭校正

## 2026-07-21(stock-terminal Phase 4 自評 P2 彙總,13 條聚類)

- [ ] 個股 stream 韌性候選:hook pending 重放只驗 seq>S 不驗連續性(回補期 WS 掉訊成永久缺筆);fromSnapshot 以 vwap×cum_vol 還原 VWAP 分子與後端 Σq 分母有近似差;apply_backfill 對回補列不去重(TC4 重送列會雙算);tc4_status 只靠 on_reconnect 復位(純 REQ 失敗 banner 永久誤掛)
- [ ] 個股 UI 盤後體驗:reset() 保留 book 與 design 字面不符(rollover 後非觸發檔殘留昨日五檔);盤後重載側欄顯示 "-" 而非昨收靜態值(需 snapshot 種子側欄)
- [ ] 個股效能/清潔候選:snapshot 每次全量序列化 20k tick deque(切檔/跳號 refetch 都全量 JSON);_states 永不清除;F:xxx 建立永不使用的 StockDayState;backfill TICKS 訂閱事後不退訂
- [ ] 個股雜項:健檢 in_trading_hours 在 subscribe 時判定而非 timer 觸發時;backfill 首頁 30s 逾時靜默回空無 log;watchlist 啟動時 TC4 離線可被 30 檔 × 10s 拖慢 lifespan

## 2026-07-20(backfill 雙修 review P2)

- [ ] backfill_finmind/backfill_daytrade 空日不進 marker 後,真假日在重跑同 range 時會反覆重抓(range 約 11 個月含 100+ 週末假日);若 FinMind 配額吃緊,疊加靜態台股假日曆只重試「非假日空回應」

## 2026-07-28(stock-ui-upgrade Phase 4 review P2 彙總)

- [ ] frontend localStorage key 無統一前綴(copycat-tab / stock-main-code / copycat-chart-toggles / stock-ladder-open / stock-wl-group)— 下次新增 key 時考慮收斂 `copycat-` 前綴 + lib/constants.ts 集中
- [ ] PriceLadder 全域 rows(最壞 ~200 列)無上限 lock 測試;若低價股(tick 10 毫元、±10% = 2000 列)出現效能問題再虛擬化
- [ ] stock-ui-upgrade real-env 真截圖待補(TC4 離線 infra_fail;清單見 .claude/feat/stock-ui-upgrade/real-env-verification-round-1.json;達錢 4 開啟後跑 server + devtools 補 evidence)

## 2026-07-28(capital-order Phase 3 順手清單)

- [ ] 舊 TC4 trade 路刪除(server/trade.py、live/tc4_trade.py、fake_trade.py、frontend useTrade.ts/OrdersList.tsx/OrderConfirm.tsx + 測試;全部已標 @deprecated,/api/trade/* 恆 503)
- [ ] TXO snapshot 補推 per-contract last_price(OrderPanel 市價估價目前缺值全鎖,限價不受影響;ContractRow.last_price 前端欄位已預留)
- [ ] app.py futures source 啟動旗標借用 trade_source is DEFAULT_TRADE(sentinel 語意耦合已註解;__main__ 顯式傳 DEFAULT_FUTURES 後可解耦)
- [ ] 期貨平倉「範圍市價 P + IOC」候選:prod 實測 bstrPrice="P"/"M" 可送性後,可從限價貼漲跌停切回(docs/research/2026-07-28-skcom-typelib.md)
- [ ] 選擇權閃電梯(本輪 out of scope,TXO 表單已群益化)
- [ ] 群益回報自動重連(本輪拍板不做;做之前 store 聚合非冪等 → 必先 clear 再重播 backlog)
- [ ] OnAccount / OnOpenInterest 欄序為 prod 未實測假定(com.py `_parse_account_row`、balance.py `parse_open_interest_line` docstring 已標)— 首次 prod 登入核對後校正

## 2026-07-28(capital-order Phase 4 code review round 1 追加)

- [ ] COM 卡死 stalled 心跳偵測(review B7):寫入 timeout 連發 / 幫浦圈停擺目前只靠 log,需心跳觀測基建(status 加 last_pump_ts + watchdog 降級);監控面非正確性,本輪 deferred
- [ ] 期貨改價 `CorrectPriceBySeqNo` 末參數 nTradeType=0(ROD)對期權 IOC/FOK 單的影響 prod 首驗(review A6;test 沙盒未開通不可先驗)— 若群益端把改價後 TIF 重設為 ROD,IOC 單改價語意會變
- [ ] 部位 store `(stock_no, kind)` 鍵位改造(review A4):現況同檔多種類庫存 dedupe 只留張數大者(sec)/同契約淨額合併(fut),被捨棄種類平倉鍵不到

## 2026-07-29(trade-layout-rework 順手清單)

- [ ] `stock-ladder-open` localStorage key 已停用(閃電梯摺疊機制隨右欄 tab 取代):舊值殘留無害,未做清除 migration;若之後做 key 收斂(見 2026-07-28 條)一併清掉
- [x] ~~`/api/stock/bars` 的真實環境驗證待補~~ **(a)(b)(d) 已於 2026-07-29 18:00 盤後驗畢**(mod/stock-ui-fixes;重啟 server 後實打 2317):(a) `tf=D` → **116 根**,落在 100–120 ✅;(b) **DK 的 `Open`/`Volume` 欄位名假定成立**,`o=240000` / `v=81973` 皆真值且 `v` 與畫面表頭總量一致,server log 無「DK rows 解析略過」warning ✅;(d) 當日段耗時 `tf=D` 1.1s / `tf=1&days=5` 2.1s(810 根 / 3 交易日),遠低於 5s 門檻 ✅
  - [ ] **(c) 仍待盤中驗**:分K 停留 ≥2 分鐘看最後一根 `t` 前進(SC-10)—— 需交易時段,盤後當日段不會再前進
- [ ] `BarsCache` 三個 dict(`_hist` / `_today` / `_daily`)永不清除:watchlist 上限 30 檔 × 30 日曆日量級可接受,若之後放寬 days 上限或改多帳號再加 LRU
- [ ] 🔴 **既有 bug(本輪 real-env 截圖發現,非本輪改出來)**:`copycat/live/aggregate.py:21 _SPOT_PREFIX = "TC.F."` 是整棵期貨樹前綴,`route()` 把**任何** `TC.F.*` tick 當台指期寫進 `spot_millipts`。個股頁選一檔有個股期的股票(如 2317→DHF `TC.F.TWF.DHF.HOT`)後,IndexBar 台指顯示成該個股期價(實測 2026-07-29 盤中:台指顯示 232.5)。ZMQ SUB 訂 `""` 收全部推播,TXO runtime 的 listener 也會收到個股引擎訂的個股期 tick。**影響不只 IndexBar**:`aggregate.py:162-163 spot_pnl` 同源 → TXO 綜合損益的現貨損益點位一併錯。修法要一併決定 `route()` 與 `:102` 對個股期該算 foreign 還是丟棄 → 開 /bug 走紅測試先行
- [ ] K 線 endpoint 未做 inflight dedup(專案 `_run_once` 慣例):同 code 併發請求會各自打一輪 TC4。單人本機用量下未觀察到問題,若之後多分頁/多 client 再補
- [ ] `inTradingHours` 只擋週末,**國定假日仍會每 60s 空跑**(當日段恆空 + don't-cache-empty → 每次真打 TC4,`_collect_history` 首頁 poll deadline ≈ 30s)。要擋需要交易日曆;或改由後端對「當日段回空」做短負向快取(需與 TC4 連線失敗區分)
- [ ] `_collect_history` 對「真的沒資料」與「TC4 沒回」都等滿 `poll_wait*30` ≈ 30s。當日段這種高頻小查詢可考慮獨立較短 deadline(改動共用路徑,overlay 也吃這條,要一起評估)

## 2026-07-29(stock-ui-round2 批一 順手清單)

- [ ] **批二(user 已拍板拆兩批,本輪 out of scope)**:項 9 閃電梯跟隨置中(判定為描述現況,
  待 user 確認是否有症狀)/ 項 12 自選側欄重做(預設群組取代「全部」+ 顯示名稱 →
  **需後端 `watchlist_quote` WS 訊息加 `name` 欄位**,跨檔契約改動)/ 項 13 閃電梯部位 +
  未實現損益 + 含成本打平價(需新增手續費折數設定,user 拍板預設 6 折)
- [ ] K 線「走到 30 日前第一根」的取用路徑偏長:1 分 K × 30 日 ≈ 5,900 根、最大視窗 700 根、
  初始 240 根 → 從右端拖到最左端約需 8 次滿寬拖曳。本輪刻意不加捷徑(雙擊回最右 / Home
  跳最左屬新互動,scope 紀律)。真用起來嫌煩再開
- [ ] 拖曳平移每次 mousemove 都重算 `buildCandleGeometry` 並 diff 整個 ChartStatic;
  700 根時約 2,100 個節點。目前靠 MAX_VISIBLE=700 + memo 修復壓住,真環境拖曳掉幀再改 rAF 節流
- [ ] 分 K 首載耗時未量到(2330 走後端永久 memo)。change-spec §7 估 10–15s;
  盤中或換冷資料標的時補量,若 >20s 退回預設 10 日 + 縮放到左端自動續載
- [ ] `buildCandleGeometry` 的 `yTicks` 是 `lo + span×i/(N−1)` 等分,不 snap 合法 tick →
  日 K 左緣會出現 `2547.32` 這種非法價位。既有行為(非本輪改出),但與江波圖新的
  11 條「全合法 tick」刻度並置後對比明顯,下次碰 K 線刻度時一併收
- [ ] 布林通道填色用 `fill-ink-muted` 0.07,在 20 期低波動段會蓋成一大片灰塊;
  若嫌干擾可改只畫上下軌不填色,或降到 0.04
- [ ] **既有行為,自評 lens 抓到但本輪駁回不修(鐵則 B 不順手改)**:`candle.ts` 的
  `indexOf` guard 是 `x > size.width` 才回 null,`x` 恰等於 `size.width` 時
  `Math.floor(x/slot)` 算出 `bars.length` → 被 `i < bars.length` 擋掉一樣回 null,
  但那個像素理應對應最後一根。症狀 = 最右一個像素的 hover 失去十字線。
  本輪未動那行;要修時 `x >= size.width` 或 `Math.min(bars.length-1, …)` 擇一
- [ ] `MINUTE_INIT_BARS = 240` / `DAILY_INIT_BARS = 120` / `MAX_VISIBLE = 700` /
  `ZOOM_STEP = 1.15` 四個常數分散在 `StockChart.tsx` 與 `candle-viewport.ts`;
  若之後要做「可設定的圖表偏好」再收斂到單一 config

## 2026-07-29(stock-ui-fixes 順手清單)

- [ ] 🔴 **server 版本無可視性 —— 本輪 item 2 的真正代價**:「K 線沒有資料」的根因是 :8721 跑的是**舊版 build**(`openapi.json` 根本沒有 `/api/stock/bars` 這條 route),但前端與人都無從辨識執行中的 server 是哪一版。已做的緩解只是讓失敗態顯示錯誤碼(SC-3)。真正的修法候選:啟動 banner 印 git sha / `/api/health` 回 sha + 啟動時間 / 前端在 console 或狀態列比對。
- [ ] 自選清單「全部」群組顯示「尚無自選,輸入股號新增」但主檔 2317 有完整資料(截圖 `.claude/mod/stock-ui-fixes/` 的 stock-before.png 可見)。watchlist v2 groups 的既有行為,**非 stock-ui-fixes 範圍**,未查根因。
- [ ] 五檔垂直版式的高度預算餘裕很薄:1440×800 江波圖模式下,下半列實測 226px vs `min-h-56` 地板 224px,**只剩 2px**。字級縮放或圖表高度再長一點就會頂到地板讓 `<main>` 出現捲軸(這是設計好的退化,不是壞掉)。若之後改動圖表高度或五檔列高,重跑一次 SC-6 的兩尺寸量測。
- [ ] 盤後重啟 server 後五檔 / 閃電梯恆空(TC4 REALTIME 五檔盤後無推播;tick 明細與江波圖走 TICKS 回補所以有資料)。CLAUDE.md §8 記載「盤後 fresh subscribe 會回當日收盤 snapshot(延遲分鐘級)」—— 本次實測 1.5 小時後 `book.bids`/`book.asks` 仍為空,該記載可能只適用成交 tick 不含五檔,值得再確認後修正文件。

## 2026-07-30(realtime-correlation 收尾沉澱)

- [ ] **P1 既有 bug:`futures_engine` 會間歇性整段零推播(期貨面板時好時壞)**。〔2026-07-30 10:24 更正:原記「P0 死鎖 / 一直是壞的」下得過重〕TXO runtime 的訂閱清單含 `SPOT_SYMBOL = TC.F.TWF.TXF.HOT`(`server/engine.py:89`),`futures_engine` 訂同一 symbol 時 TC4 只推一邊(CLAUDE.md §8);其 leaf fallback 需先由推播解析契約月份才啟動 → 全零推播時啟動不了。**兩個相反的實測狀態**:(i) 2026-07-29 17:33 起跑的 server 到 00:50 為止 TXF/MXF/TMF 全 `p=null`、`seq=0`,同時段獨立訂閱 TXF.HOT 有 235 則/30 秒(MXF 324 則)、五檔俱全 → TC4 端正常;(ii) 2026-07-30 10:24 起跑的 server 六腿含 TXF 全部正常有值,realtime-correlation 的 base 腿與五對相關係數都算得出來。**故為間歇性,觸發條件未定位**(疑似啟動時序 / TC4 session 殘留 / 先前有 process 訂過同 symbol)。下輪要做的第一件事是**穩定重現**(鐵則 A:先穩定重現再談修),而不是直接動 fallback。修法候選:leaf fallback 改為可由「非推播來源」取得月份(合約清單查詢),或 runtime 與 futures_engine 共用單一 TXF 訂閱。
- [ ] `test_index_engine.py::test_rollover_two_phase` 只在真實時鐘 ≥ 08:30 才會綠:`_rollover_loop`(`index_engine.py:279`)以 `_dt.datetime.now().time()` 判 08:30 門檻,該時鐘無注入點(同建構子已注入 `today_fn` / `in_watch_window`,唯獨漏它)。決定性實驗:把模組的 `_dt` 換成固定 10:00 的 shim 後立即轉綠。修法:建構子補 `now_fn`。
- [ ] `test_tc4.py::TestConnectInterruptible` 與 `test_tc4_trade.py::TestFailedConnectGcSafety` 依賴未進版控的 `spikes/TCPY/`(`.gitignore:9`),任何乾淨 checkout 都會紅。修法:測試層 skip-if-missing,或把 wrapper 納入版控。
- [x] ~~realtime-correlation 的 SC-5 日盤補驗~~ **2026-07-30 10:24 已驗**:日盤六腿全部有中價且非 stale(TXF 40646 / TWN 3462.62 / YM 51909.5 / ES 7388.88 / NQ 27638 / SXF 10776),五對相關係數算出實值(TWN 0.590 / YM 0.147 / ES 0.336 / NQ 0.520;SXF 因整窗中價未動 → 標準差 0 正確回 null)。SC-6 同時驗過:60 秒收 61 則、間隔中位數 1.010s、seq 連續遞增。
- [ ] realtime-correlation 訂閱窗的**反向**驗證仍未做:「沿用 `session_window` 會失效」是推論不是實證 —— 台指日盤窗(UTC 00–06)+ 夜盤窗(UTC 06–22)合計涵蓋 UTC 00–22,訂閱當下海外腿幾乎不會落窗外;真正的風險是「訂閱後跨過窗結束邊界(UTC 06 / 22)推播是否停止」。驗法:在 UTC 05:5x(台北 13:5x)前訂閱並持續監聽到 UTC 06:0x 之後,看推播是否中斷。全天窗實作本身已是防禦性選擇,此項只影響「基底 source 是否也該改」的判斷。
- [ ] `corr_state.correlations()` 每腿每次重建 `leg_by_ts` dict(1800 entries)、每窗各過濾一次。實測滿窗 tick 6.43 ms(門檻 200 ms)不構成問題;若日後窗長或腿數放大再看。
## 2026-07-30(stock-ui-round3 順手清單)

- [ ] 🔴 **「有資料但 TC4 慢」會顯示肯定語氣的錯誤結論**(change-spec Known Risks 1):
  `_BARS_POLL_DEADLINE=10s` 誤判為空 + 15s 負向快取 → `CandleChart` 顯示「無 K 線資料」
  而非「還在等」。這是**既有行為**(現況等滿 60s 後顯示同一句話),本輪只讓它更快抵達。
  要真正修好必須把「逾時 / 真無資料 / TC4 斷線」沿
  `_collect_history → fetch_bars_range → bars_range → BarsFetcher` 整條型別鏈區分開
  (`stock_engine.bars_range` 連 `ConnectionError` 都吞成 `[]`),外加 response 加欄位 +
  前端文案分態 + `tests/server/test_bars.py` 20 個 call site 與 `test_stock_routes.py`
  的精確相等契約要一起改 —— round3 spec review 評估後判定為獨立一輪的工作,已撤回。
- [ ] 大螢幕明細列數不再隨視窗變高(下半列固定 224px ≈ 7 列)。1920×1080 上明細與
  1440×900 一樣多,這是「圖表吃剩餘高度 + 兩塊卡片貼底」的直接代價(Known Risks 2)。
  若之後嫌明細太短,考慮把下半列改成 `flex-1 max-h-72 min-h-56`(需重驗 SC-6)。
- [ ] 五檔卡片底部約 24px 留白:`h-full` 讓卡片撐滿 224px 而內容約 200px。這是對舊
  `self-start` 取捨的刻意推翻(user 要求貼底)。若嫌空,可讓五檔列高改為內容高並只讓
  明細貼底(但兩塊底邊就不齊平)。
- [ ] `--color-time` 與 `--color-ma5` 目前同色值(#f0b429),語意獨立是刻意的。
  若之後 MA5 改色,時間軸不受影響 —— 但也要記得兩者並置時對比度會消失。
- [ ] `_POLL_BACKOFF_START = 0.15` 與 `_BARS_POLL_DEADLINE = 10.0` 兩個常數是實測推得
  (有資料標的首頁 <1s 備妥),TC4 忙碌時的真實分布未量。若 real-env 出現誤判為空的
  頻率偏高,先量首頁備妥時間分布再調,不要盲目放大 deadline(那會把 60s 問題帶回來)。
