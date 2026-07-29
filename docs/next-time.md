
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
- [ ] `/api/stock/bars` 的真實環境驗證待補:本輪出貨時 8721 已被舊版 server 佔用且盤中(2026-07-29 11:57),不自行重啟搶 TC4 推播。重啟 server 後要驗:(a) `tf=D` 回應 `bars.length` 落在 100–120(SC-7);(b) DK 的 `Open`/`Volume` 欄位名(CLAUDE.md §8 只實證 H/L/C,現為防禦解析 + 略過計數 log);(c) 分K 停留 ≥2 分鐘看最後一根 `t` 前進(SC-10);(d) 一次當日段耗時 >5s 就回頭改設計(change-spec §7)
- [ ] `BarsCache` 三個 dict(`_hist` / `_today` / `_daily`)永不清除:watchlist 上限 30 檔 × 30 日曆日量級可接受,若之後放寬 days 上限或改多帳號再加 LRU
