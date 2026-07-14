
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
