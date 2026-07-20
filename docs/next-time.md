
## 2026-07-07(tday-join-ga-backtest 收尾沉澱)

- [x] ~~config JSON 載入器樣板與 strategy_config.load_config 重複 → 抽 generic helper(review Reuse3,動既有檔屬 🔵 獨立工)~~(2026-07-20 refactor/shared-infra-helpers:copycat/configio.load_dataclass_json)
- [x] ~~atomic write(tmp+os.replace)全專案 5 處手刻 → 共用 helper(review Reuse5)~~(2026-07-20 同輪:實際 27 處 13 檔,收斂 copycat/fileio;spikes/ 一次性腳本不在範圍)
- [ ] simulate 完整 derived-series 預計算重構(review F2 只做了 anchor 網格限定;若 Phase B 全量變慢再做)
- [x] ~~對照組 T+1 1K 補抓 2,068 筆 + 7-8% 帶 6,509 stock-day TC4 回補(Phase B 前置,需達錢 4 開著)~~(2026-07-20 spikes/backfill_phaseb_1k.py:fetched 5,015 / no_data 225 / failed 0,8.7 分鐘;殘缺 232 筆經長等待重試確認 TC4 真無資料(下市/創新板),帶宇宙有效覆蓋 97.5%;筆數對照與設計值差異解釋見 docs/evidence/tc4_1k_phaseb_backfill_2026-07-20.md)

## 2026-07-11(fade-round-1 收尾 review P2 彙總,18 條聚類)

- [x] ~~fade wf 結構債(🔵 獨立工,下輪動 walk-forward 前先收斂):run_fade_arm 的 wf/單切分雙路徑重複「模擬→過濾→組特徵」邏輯;build_wf_cross_arm_table 與 build_cross_arm_table 排序/appendix 邏輯逐字複製(含 _sort_key×2);fade_report 6+ 處 `if wf_starts` 散落~~(2026-07-20 refactor/next-time-unconditional-batch:前兩腿已於後續輪收斂(_simulate_default/_collect_tradeable、_rank_and_split),殘餘 GA 候選塊抽 _ga_candidates;fade_report 殘餘 5 處 wf 條件為同函式內展示分岔,判定不再抽)
- [x] ~~fade combo 手動欄位複製 → dataclasses.replace:fade_optimize._strip_s5/_rebuild_combo、fade_config.enumerate_fade_stop_combos 各 8 個 .get(新增 FadeStopCombo 欄位會靜默漏)~~(2026-07-20 驗證已於後續輪收斂:_combo_from_base/_rebuild_combo 皆 fields() 驅動、_strip_s5 已用 replace,僅勾銷)
- [ ] fade pipeline 效能候選(6h 長跑;/perf 先 profile 再動):診斷段重讀全部 1K bars(run 時已讀過)、optimize_rule_tp 重算 optimize_rule_stops 已算過的 rule mask、guard_dist_grid 每格全量重模擬、by_source O(sources×trades) 重掃
- [x] ~~格式/統計 helper 各兩份:_fmt(report.py vs fade_report.py + 函式內重定義)~~(2026-07-20 同輪:report_fmt.fmt_cell / fmt_num 並存不合併,語意不同)、search.py _quantile **維持獨立**(nearest-rank、吃已排序輸入、GA 熱路徑,契約與 quantiles.py 兩版皆不同;若要收斂屬行為輪,需先驗 GA 謂詞庫不變)

## 2026-07-14(fade-round-2 自評 review P2 彙總)

- [ ] fade 診斷效能候選(/perf 先 profile):diagnose_pool_fade 對同一 universe base+stress+lock_grid 共 5 次全量重模擬(可單迴圈多配置);evaluate_cells 每 cell×variant 各 base/stress 兩趟 + baseline ×4 = 16 趟(觸發判定可先算一次共用)
- [ ] write_pool_fade_report / write_cells_report 兩份 markdown 表建構結構相似(第三份出現時抽共用 table builder)
- [ ] fade_cells 新增 cell 需改多點(find fn / _simulate_cell_trades 分支 / specs 列表 / config):cell 數 >4 時抽 registry
- [ ] fade_cells find_cell_a_entry 的 headroom 除式無 b.close>0 防禦(實際 1K 資料恆正;若接入外部資料源先補 guard)
- [ ] backfill_brokers/label_events 對 FinMind 非數值欄位(如 'N/A')無韌性(現況未觀察到;出現時在 aggregate 層加 tolerant parse + 計數)

## 2026-07-15(fade-round-3 自評 review P2 彙總,8 條聚類)

- [x] ~~fade_cells 兩套 cell 分派機制並存(round 2 _CellSpec vs round 3 kind 字串 if-elif;_simulate_cell_trades / _simulate_r3_trades 各一套)→ round 4 動 cells 前先收斂成單一 dispatch(🔵 獨立工)~~(2026-07-20 同輪:進場分派收斂 _find_cell_entry,兩套 simulate 保留(輸出形狀不同屬行為輪)但 dispatch 單一來源;fade_anatomy._entry_idx_for 也改走同一分派)
- [ ] evaluate_cells_from_universe 頂層 round gate 分岔:再加一輪會變 if-elif chain,屆時抽 evaluator factory
- [x] ~~tuple-unpack 樣板重複(found_x[0] if found_x is not None else None ×2;_simulate_r3_trades 三個同型 found 分支)~~(2026-07-20 同輪:隨 _find_cell_entry 收斂消失)
- [x] ~~D5 criteria dict 建構在 cells round2/round3 兩處重複(門檻改一邊會漏另一邊)~~(2026-07-20 同輪:實際已長到 4 份(r2/r3/r4/r5),收斂 _d5_criteria + _vs_baseline_mean 單一定義)
- [x] ~~_act_rows 報告閉包可升 module-level(round 4+ 報告複用)~~(2026-07-20 同輪:r3/r4 兩份同構收斂 _actuarial_rows(reasons 參數化);r5 版語意不同保留)
- [ ] 底倉格 grid 對 in_w 掃 6 次(單次分桶可 O(n),n 小暫無感)
- [ ] run_cells 三次 build_fade_universe(cellb 可由 main 超集記憶體過濾,現況重讀 1K JSON)
- [ ] validate_disaster_fields 在 _simulate_core 每 call 驗一次(GA 熱迴圈微耗;可改 config frozen 後驗一次的快取)

## 2026-07-16(fade-round-4 自評 review P2 彙總,12 條聚類)

- [x] ~~分位數實作三份(fade_anatomy._quantiles / fade_cells._pctl / fade_diagnose._quantile,演算法還不一致:round vs int truncate)→ 統一到共用 stats helper~~(2026-07-20 refactor/shared-infra-helpers:backtest/quantiles.py 收斂單一模組、round 與 truncate 兩演算法**保留並存**(統一即改報告數字 = 行為輪,user 拍板不做);characterization 鎖住 n=6 p=0.5 分歧點)
- [x] ~~D5 判定三條件 + vs_baseline 計算在 _evaluate_round3 與 _evaluate_round4._variant_block 逐行重複 → 抽純函式(抽取不動 round 3 輸出,bit-for-bit 可保;改 D5 判準時兩份會分岔)~~(2026-07-20 同輪:併入 _d5_criteria/_vs_baseline_mean 收斂,見 2026-07-14 節)
- [ ] fade_anatomy 效能候選(單次跑分鐘級,量級可接受;/perf 先 profile):flush_anatomy 每個 z 全宇宙重掃(可單趟收三個 z)、hl_anatomy 每個 k × arm 重算 entry idx(可 cache)、_evaluate_round4 消融 5 組 × 5 變體 = 25 趟全量模擬
- [x] ~~fade_anatomy 報表 micro 重複:inner gate 兩張 touch_rate 表同構、nested isinstance/get 鏈提取 helper、mfe_anatomy 與 _entry_idx_for 的 cell 參數抽取樣板兩份(cell registry 條目 2026-07-14 節已有,合併)~~(2026-07-20 同輪:_touch_rate_row / _nested_float / _cell_param 三 helper 收斂,_entry_idx_for 改走 _find_cell_entry)
- [ ] check_flush_exit(cfg 驅動)與 _tp1(combo 驅動)結構重複但錨不同(進場後最低 vs running_low 含 trig)——已在 docstring 註明差異;若 Phase B 網格路徑退役,_tp1 可刪併

## 2026-07-17(fade-round-5 收尾 review P2 彙總,8 finder → 6 條)

- [x] ~~flow 狀態機雙實作收斂(🔵 獨立工):fade_vote._iter_votes 與 fade_entry_anatomy._first_flip 各寫一份「同定義」狀態機——已加一致性測試釘住等價(test_fade_vote TestFlowConsistencyWithAnatomy),真正共用實作(抽 per-bar step generator)留獨立 refactor~~(2026-07-20 同輪:抽 fade_vote.iter_flow_flip,兩端委派;rho ≥ 1 逐 bar 等價、凍結網格皆 ≥ 1)
- [x] ~~_evaluate_round5._trades 尾段(locked_close/hold_pnl/_TradeRec 建構)與 _simulate_r3_trades 尾段重複 → 抽 _finalize_trade 共用(該段歷史上已修過 P1,單邊同步風險同 §8 TRADEABLE_STATUSES 教訓)~~(2026-07-20 同輪:_finalize_trade 收斂)
- [x] ~~fade_entry_anatomy 兩處 two-sample cluster-z 公式(level_stratified_duel 加權版 / level_anatomy duel 直接版)→ 抽共用 helper;run_entry_anatomy 內 _build_day_recs 被 level_anatomy 與 level_stratified_duel 各建一次 → 建一次傳入~~(2026-07-20 同輪:_two_sample_cluster + prebuilt/day_recs 參數)
- [ ] round5 效能候選(/perf 先 profile):stress 跑法重執行 entry_fn 全宇宙掃描(進場 idx 不依 run_cfg)、樣本預算表 4×全宇宙重掃(可單趟 _iter_votes 同時判多個 S)、消融 3 單訊號各自重跑狀態機
- [ ] 敏感度區塊複製貼上(S/c/m 三塊近同)+ disaster_off 手刻出異形 dict shape + round 輪次 dispatch 鏈成長(round 6 時考慮 active_round 單點解析);flow_flip_anatomy 出現率分母含 len(bars)<2 跳過日(輕微低估,不影響判準)

## 2026-07-18(txo-aggregate-pnl Phase 4 自評 P2 彙總,10 條聚類)

- [ ] 觀測性:~~handover buffer 溢出僅 log 無 snapshot 計數欄位(degraded 時前端難診斷)~~(2026-07-20 fix/txo-quote-resilience:snapshot handover 欄位含 overflows 計數已覆蓋);前端 WS 無 heartbeat 判停(server 靜默時段分不出斷線 vs 無變更;考慮 server 週期 keepalive frame + client stale timer,週一盤中觀察真實需求再定)
- [ ] engine._run_handover 重試時 re-subscribe 與 activate 的 unsubscribe 不對稱,若改主動觸發自癒要先收斂這段

## 2026-07-19(dq4-order-phase1 Phase 4 自評 P2 彙總,15 條聚類,shortSymbol/BLOCKED_REASON 已本輪吸收)

- [x] ~~trade 重複 helper 候選:useTrade.ts getJson/postJson 80% 同構(可併單一 fetchJson)、trade.py _apply_restore 雙迴圈(抽 _apply_to_store)、tc4_trade.handle_sub_message exec/fill 分支(dict dispatch)、OrdersList 警示列/區塊樣板 ×2~~(2026-07-20 refactor/next-time-unconditional-batch:四項全數收斂 — fetchJson / _apply_to_store / _REPORT_PARSERS / Warning+Section)
- [ ] 錯誤碼三層對照(backend _TRADE_ERROR_MAP / frontend TRADE_ERROR_TEXT / 測試字面值)無單一 source:新增錯誤碼要動多處;若錯誤碼家族再擴,考慮 codegen 或 shared JSON(現況 frontend 未知碼原樣顯示 = 安全漂移)
- [ ] trade 效能微優化候選(手動單低頻,全部先不動;若未來策略自動下單高頻化再 /perf):orders_view 每 poll 重建 list、account_view 每呼叫 sorted、orderable_symbols 每呼叫重建 set
- [ ] parse_execution_report 的 err_code 判定含 0/"0" 白名單,真值域(design §8 #3)整合實測後回頭校正

## 2026-07-18(txo-tquote-cursor Phase 4 自評 P2)

- [x] ~~QuoteTable 欄定義三處手動同步(SideCells cells 陣列 + reverse() 鏡像 + thead 手寫標籤;netTone/EnergyBar 各自判 net_qty 正負色)→ T 字表要加欄(如成交價/OI)前先抽共用 column def,否則 desync 無測試可抓~~(2026-07-20 同輪:QUOTE_COLUMNS 單一來源(thead/儲存格/鏡像同源)+ netTone(text/bg) 單一判定)

## 2026-07-20(/bug txo-live-fixes 順手衝動收納)

- [x] ~~quote 端 QuoteAPI Connect 無 RCVTIMEO:app 死亡時重連迴圈阻塞在裸 recv;比照 trade 端 context 級 timeout + LINGER=0 的防護(要驗 QuoteManager 分頁大回應不會被 5s timeout 誤傷)~~(2026-07-20 fix/txo-quote-resilience:context 級 10s timeout(實測 QUERYALLINSTRUMENT(Opt) 1.93s ×5 裕度;GetHistory 分頁 3,482 次 max 1.1ms 不受影響)+ LINGER=0 + _rt_request lock timeout;死 port 實測重連可中斷、app 回來可恢復)
- [x] ~~交接 buffer cap 200k:回補拖過 ~8 分鐘會溢出→無限重跑回補;考慮 cap 動態化或回補逾時預警~~(2026-07-20 同輪:只做預警(user 拍板)— 80% 閾值一次性 warning + snapshot handover 欄位(backfill_secs/buffer_used/buffer_cap/buffer_warned/overflows);cap 動態化未做,溢出仍會重跑,預警先給觀測點)

## 2026-07-20(txo-quote-resilience 收尾 review P2)

- [x] ~~tc4.py `_check_stale` 用 `self._lock` 保護重連期的 `_api/_session` 寫入,但 `_rt_request`/`close()` 讀寫同狀態不持鎖(pre-existing,觸發窗口 = 毫秒級重連瞬間撞併發請求;裸 `assert` 會拋 AssertionError 不在 except 收斂內)→ 若要處理,讓讀側也持鎖或把 assert 換明確 ConnectionError~~(2026-07-20 refactor/next-time-unconditional-batch:_connection() 同鎖快照 (api, session) 消錯配對、帶 session 的 REQ 全走 _session_req、close() 補鎖、_start_listener 裸 assert 換 ConnectionError)

## 2026-07-20(backfill 雙修 review P2)

- [ ] backfill_finmind/backfill_daytrade 空日不進 marker 後,真假日在重跑同 range 時會反覆重抓(range 約 11 個月含 100+ 週末假日);若 FinMind 配額吃緊,疊加靜態台股假日曆只重試「非假日空回應」
