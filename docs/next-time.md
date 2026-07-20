
## 2026-07-07(tday-join-ga-backtest 收尾沉澱)

- [ ] config JSON 載入器樣板與 strategy_config.load_config 重複 → 抽 generic helper(review Reuse3,動既有檔屬 🔵 獨立工)
- [ ] atomic write(tmp+os.replace)全專案 5 處手刻 → 共用 helper(review Reuse5)
- [ ] simulate 完整 derived-series 預計算重構(review F2 只做了 anchor 網格限定;若 Phase B 全量變慢再做)
- [ ] neigui 種子事件池刷新管道(池截止邊界:3055 2026-06-18/24 不在池內;滾動重驗前置)
- [ ] .claude/harness.json 殘留模板修正(verify 陣列指向不存在的 backend/frontend)
- [ ] 對照組 T+1 1K 補抓 2,068 筆 + 7-8% 帶 6,509 stock-day TC4 回補(Phase B 前置,需達錢 4 開著)
- [2026-07-10] backfill_finmind:空回應日(FinMind 尚未發布 vs 真假日)一律進 manifest done_dates,當日盤後跑會永久跳過該日;應比照 backfill_daytrade 的 if data 判斷。這次手動從 manifest 移除 2026-07-10。

## 2026-07-11(fade-round-1 收尾 review P2 彙總,18 條聚類)

- [ ] fade wf 結構債(🔵 獨立工,下輪動 walk-forward 前先收斂):run_fade_arm 的 wf/單切分雙路徑重複「模擬→過濾→組特徵」邏輯;build_wf_cross_arm_table 與 build_cross_arm_table 排序/appendix 邏輯逐字複製(含 _sort_key×2);fade_report 6+ 處 `if wf_starts` 散落
- [ ] fade combo 手動欄位複製 → dataclasses.replace:fade_optimize._strip_s5/_rebuild_combo、fade_config.enumerate_fade_stop_combos 各 8 個 .get(新增 FadeStopCombo 欄位會靜默漏)
- [ ] dead code:fade_pipeline._param_hash/_samples_hash 定義後零 caller,可刪
- [ ] fade pipeline 效能候選(6h 長跑;/perf 先 profile 再動):診斷段重讀全部 1K bars(run 時已讀過)、optimize_rule_tp 重算 optimize_rule_stops 已算過的 rule mask、guard_dist_grid 每格全量重模擬、by_source O(sources×trades) 重掃
- [ ] 格式/統計 helper 各兩份:_fmt(report.py vs fade_report.py + 函式內重定義)、_quantile(search.py nearest-rank vs fade_diagnose int(p*len),場景獨立但演算法不同,共用時要先統一)

## 2026-07-14(fade-round-2 自評 review P2 彙總)

- [ ] fade 診斷效能候選(/perf 先 profile):diagnose_pool_fade 對同一 universe base+stress+lock_grid 共 5 次全量重模擬(可單迴圈多配置);evaluate_cells 每 cell×variant 各 base/stress 兩趟 + baseline ×4 = 16 趟(觸發判定可先算一次共用)
- [ ] write_pool_fade_report / write_cells_report 兩份 markdown 表建構結構相似(第三份出現時抽共用 table builder)
- [ ] fade_cells 新增 cell 需改多點(find fn / _simulate_cell_trades 分支 / specs 列表 / config):cell 數 >4 時抽 registry
- [ ] fade_cells find_cell_a_entry 的 headroom 除式無 b.close>0 防禦(實際 1K 資料恆正;若接入外部資料源先補 guard)
- [ ] backfill_brokers/label_events 對 FinMind 非數值欄位(如 'N/A')無韌性(現況未觀察到;出現時在 aggregate 層加 tolerant parse + 計數)
- [2026-07-15] backfill-tc4 的 --events-csv 預設仍指 five-tigers 種子 CSV(_DEFAULT_EVENTS_CSV)——與 round 2 已修的 backfill-brokers/label-events 同類 stale default;不帶參數跑會漏掉 scan 補全事件的 1K 回補(增量補審 P2,範圍外)

## 2026-07-15(fade-round-3 自評 review P2 彙總,8 條聚類)

- [ ] fade_cells 兩套 cell 分派機制並存(round 2 _CellSpec vs round 3 kind 字串 if-elif;_simulate_cell_trades / _simulate_r3_trades 各一套)→ round 4 動 cells 前先收斂成單一 dispatch(🔵 獨立工)
- [ ] evaluate_cells_from_universe 頂層 round gate 分岔:再加一輪會變 if-elif chain,屆時抽 evaluator factory
- [ ] tuple-unpack 樣板重複(found_x[0] if found_x is not None else None ×2;_simulate_r3_trades 三個同型 found 分支)
- [ ] D5 criteria dict 建構在 cells round2/round3 兩處重複(門檻改一邊會漏另一邊)
- [ ] _act_rows 報告閉包可升 module-level(round 4+ 報告複用)
- [ ] 底倉格 grid 對 in_w 掃 6 次(單次分桶可 O(n),n 小暫無感)
- [ ] run_cells 三次 build_fade_universe(cellb 可由 main 超集記憶體過濾,現況重讀 1K JSON)
- [ ] validate_disaster_fields 在 _simulate_core 每 call 驗一次(GA 熱迴圈微耗;可改 config frozen 後驗一次的快取)

## 2026-07-16(fade-round-4 自評 review P2 彙總,12 條聚類)

- [ ] 分位數實作三份(fade_anatomy._quantiles / fade_cells._pctl / fade_diagnose._quantile,演算法還不一致:round vs int truncate)→ 統一到共用 stats helper(🔵 獨立工;2026-07-11 節已有同類條目,合併處理)
- [ ] D5 判定三條件 + vs_baseline 計算在 _evaluate_round3 與 _evaluate_round4._variant_block 逐行重複 → 抽純函式(抽取不動 round 3 輸出,bit-for-bit 可保;改 D5 判準時兩份會分岔)
- [ ] fade_anatomy 效能候選(單次跑分鐘級,量級可接受;/perf 先 profile):flush_anatomy 每個 z 全宇宙重掃(可單趟收三個 z)、hl_anatomy 每個 k × arm 重算 entry idx(可 cache)、_evaluate_round4 消融 5 組 × 5 變體 = 25 趟全量模擬
- [ ] fade_anatomy 報表 micro 重複:inner gate 兩張 touch_rate 表同構、nested isinstance/get 鏈提取 helper、mfe_anatomy 與 _entry_idx_for 的 cell 參數抽取樣板兩份(cell registry 條目 2026-07-14 節已有,合併)
- [ ] check_flush_exit(cfg 驅動)與 _tp1(combo 驅動)結構重複但錨不同(進場後最低 vs running_low 含 trig)——已在 docstring 註明差異;若 Phase B 網格路徑退役,_tp1 可刪併

## 2026-07-17(fade-round-5 收尾 review P2 彙總,8 finder → 6 條)

- [ ] flow 狀態機雙實作收斂(🔵 獨立工):fade_vote._iter_votes 與 fade_entry_anatomy._first_flip 各寫一份「同定義」狀態機——已加一致性測試釘住等價(test_fade_vote TestFlowConsistencyWithAnatomy),真正共用實作(抽 per-bar step generator)留獨立 refactor
- [ ] _evaluate_round5._trades 尾段(locked_close/hold_pnl/_TradeRec 建構)與 _simulate_r3_trades 尾段重複 → 抽 _finalize_trade 共用(該段歷史上已修過 P1,單邊同步風險同 §8 TRADEABLE_STATUSES 教訓)
- [ ] fade_entry_anatomy 兩處 two-sample cluster-z 公式(level_stratified_duel 加權版 / level_anatomy duel 直接版)→ 抽共用 helper;run_entry_anatomy 內 _build_day_recs 被 level_anatomy 與 level_stratified_duel 各建一次 → 建一次傳入
- [ ] round5 效能候選(/perf 先 profile):stress 跑法重執行 entry_fn 全宇宙掃描(進場 idx 不依 run_cfg)、樣本預算表 4×全宇宙重掃(可單趟 _iter_votes 同時判多個 S)、消融 3 單訊號各自重跑狀態機
- [ ] levels_map 靜默空 dict:直呼 evaluate_cells_from_universe 忘傳 → 位階票全釘中性 1 分無警告(production 唯一 caller run_cells 會建;考慮 vote 臂啟用且 levels_map 空時 logger.warning)
- [ ] 敏感度區塊複製貼上(S/c/m 三塊近同)+ disaster_off 手刻出異形 dict shape + round 輪次 dispatch 鏈成長(round 6 時考慮 active_round 單點解析);flow_flip_anatomy 出現率分母含 len(bars)<2 跳過日(輕微低估,不影響判準)

## 2026-07-18(txo-aggregate-pnl Phase 4 自評 P2 彙總,10 條聚類)

- [ ] live/server simplification:aggregate.snapshot call/put 求和雙迴圈可併;ConnectionBadge STATUS_LABEL/STATUS_TONE 併單一 config;pnl-svg areaPaths 內 path 格式化與 curvePath 同構可抽 helper;engine._run_handover 內 _mark_changed 呼叫可集中;MetricsBar t 的 null 檢查可提前解構
- [x] TC4 reuse:TC4_APPID/TC4_SKEY 常數與 QryIndex 分頁迴圈在 data/backfill_tc4.py 與 live/tc4.py 兩份 → 抽共用 helper(🔵 獨立工,動到穩定 backfill 檔先補 characterization)— 已處理(refactor/tc4-shared-helper:b88f262/b1a36bb/387f8f8,tc4common.py)
- [ ] 觀測性:handover buffer 溢出僅 log 無 snapshot 計數欄位(degraded 時前端難診斷);前端 WS 無 heartbeat 判停(server 靜默時段分不出斷線 vs 無變更;考慮 server 週期 keepalive frame + client stale timer,週一盤中觀察真實需求再定)
- [ ] engine._run_handover 重試時 re-subscribe 與 activate 的 unsubscribe 不對稱,若改主動觸發自癒要先收斂這段

- [x] frontend/tsconfig.*.tsbuildinfo 是 build 產物被誤入版控(wave4),加 .gitignore 並 git rm --cached(2026-07-18)— 已處理(c26a981)

## 2026-07-19(dq4-order-phase1 Phase 4 自評 P2 彙總,15 條聚類,shortSymbol/BLOCKED_REASON 已本輪吸收)

- [ ] trade 重複 helper 候選:useTrade.ts getJson/postJson 80% 同構(可併單一 fetchJson)、trade.py _apply_restore 雙迴圈(抽 _apply_to_store)、tc4_trade.handle_sub_message exec/fill 分支(dict dispatch)、OrdersList 警示列/區塊樣板 ×2
- [ ] 錯誤碼三層對照(backend _TRADE_ERROR_MAP / frontend TRADE_ERROR_TEXT / 測試字面值)無單一 source:新增錯誤碼要動多處;若錯誤碼家族再擴,考慮 codegen 或 shared JSON(現況 frontend 未知碼原樣顯示 = 安全漂移)
- [ ] trade 效能微優化候選(手動單低頻,全部先不動;若未來策略自動下單高頻化再 /perf):orders_view 每 poll 重建 list、account_view 每呼叫 sorted、orderable_symbols 每呼叫重建 set
- [ ] parse_execution_report 的 err_code 判定含 0/"0" 白名單,真值域(design §8 #3)整合實測後回頭校正

## 2026-07-18(txo-tquote-cursor Phase 4 自評 P2)

- [ ] QuoteTable 欄定義三處手動同步(SideCells cells 陣列 + reverse() 鏡像 + thead 手寫標籤;netTone/EnergyBar 各自判 net_qty 正負色)→ T 字表要加欄(如成交價/OI)前先抽共用 column def,否則 desync 無測試可抓

## 2026-07-20(refactor/tc4-shared-helper 發現)

- [ ] `copycat validate` 在 master 已紅(12/42 PASS,SC-4/SC-6 多格超 tolerance)— golden gate(89e0041,2026-07-07)以種子事件池定錨,scan-events 補全後事件池 11048 筆,分佈漂移。與 tc4-shared-helper refactor 無關(master 與分支跑出逐字相同結果)。需決策:golden 重定錨(對補全池重拍)或 gate 降級為種子池子集比對 — 屬行為級決定,開獨立輪處理

## 2026-07-20(/bug txo-live-fixes 順手衝動收納)

- [ ] 測試裡的 `TC.F.TWF.FITX.HOT` 字面值(test_aggregate/test_live_models/test_tc4 共 5 處,行為中性的任意 TC.F.* 範例)改成 TXF 命名,免得繼續傳播已證實不存在的 symbol
- [ ] quote 端 QuoteAPI Connect 無 RCVTIMEO:app 死亡時重連迴圈阻塞在裸 recv(等 app 回來才續走,盤中實測可用但不可中斷);比照 trade 端 context 級 timeout + LINGER=0 的防護(要驗 QuoteManager 分頁大回應不會被 5s timeout 誤傷)
- [ ] 交接 buffer cap 200k:實測訂閱→回補完成 ~4.5 分鐘已 buffer ~110k,若回補拖過 ~8 分鐘會溢出→無限重跑回補;考慮 cap 動態化或回補逾時預警(驗證報告平台觀測 4)
- [ ] feat/dq4-order-phase1 收尾 rebase 時:tc4.py 會在 SPOT_SYMBOL 匯入區起衝突(master 改定義行、feat 移到 models.py)— 解法 = 保留 feat 的 models re-export 版(models.py 已是 TXF,a1ce559);_listen_loop 的 item 3 fix hunk 兩邊同文自動帶入。TestSpotSymbol + TestListenerFollowsSubPort 會在 rebase gate 驗證,紅了就是解錯
