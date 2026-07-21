
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
