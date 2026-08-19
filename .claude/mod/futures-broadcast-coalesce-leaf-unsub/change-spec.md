# Change spec:futures 廣播 per-product coalesce + HOT 回魂退訂 leaf + 自癒閘看盤別(/mod futures-broadcast-coalesce-leaf-unsub)

日期 2026-08-19。分流判定:**已成形方案**(handoff R2 指名落點與做法;D2 可逐分支)→ grilling 姿態;
規格來自 user 拍板 handoff → 預核准,非方向性抉擇標 `[auto-default]`。

## 拍板紀錄

- **D2 futures 廣播節流:保留 event-driven 但 per-product coalesce,flush 週期 0.1 s**
  `[auto-default: coalesce 0.1 s | reason: handoff 建議;五檔盤中要即時,1 s 週期會讓閃電梯五檔慢一秒;選項互換不改對外契約
  (WS shape / seq 連續 / GET state 同源皆保持),屬實作選擇]`
- **D2a seq 在 flush 時每則 +1(不在 quote 時)** `[auto-default | reason: 前端 useFuturesStream 以 seq 連續判跳號 → refetch;
  若 quote 遞增而廣播合併,每次合併都觸發 REST refetch 風暴]`
- **D2b 同一輪 flush 內多 product 各自一則(按 dirty 插入順序)**,不合併成一則多 product 訊息 `[auto-default | reason: 保持 shape]`
- **D2c leaf 退訂時機 = 現有「HOT 真的推成交」判準點**(`_leaf_fed.discard` 處),對該 product 全部 `_leaf_done` 的 ym 退訂;
  舊月到期 leaf 不在此輪(換月註解既有語意不動)`[auto-default | reason: handoff R2 指名;到期契約零推播、退訂無流量收益]`
- **D2d 自癒閘盤別 = 日盤 08:40–13:50、夜盤 14:55–24:00 + 00:00–05:05(各寬 5 分)** `[auto-default | reason: 寬限避免邊界誤關自癒;
  handoff 附帶項]`

## 成功條件(SC)

- **SC-1 同 product 連發 N 則 quote 在 flush 週期內 → 1 則廣播、payload 為最新 state、seq +1**:
  驗證 `tests/server/test_futures_engine.py::TestCoalesce::test_burst_same_product_coalesced`(`flush_interval_secs=0.05`,
  連推 5 則價不同 → sleep 0.2 → `len(events)==1`、`events[0]["state"]["p"]` = 最後一則、`seq==1`、`engine.state()["seq"]==1`)。
- **SC-2 不同 product 各自一則、seq 連續、GET state seq 同源**:`test_burst_two_products_two_messages_seq_contiguous`
  (TXF×3 + MXF×2 → 2 則、seq [1,2]、`state()["seq"]==2`)。
- **SC-3 flush 後新 quote 再推、兩輪 seq 連續**:`test_second_wave_after_flush`(第一波 → sleep → 第二波 → 共 2 則,seq [1,2])。
- **SC-4 latency 上限 = flush 週期**:`test_single_quote_delivered_within_interval`(interval 0.05,單 quote 在 0.1 s 內收到)。
- **SC-5 HOT 成交回來 → 該 product 已訂 leaf 全退**:`TestLeafFallback::test_hot_tick_unsubscribes_leaf`(leaf 補訂後推
  `TC.F.TWF.TXF.HOT` 成交 → `src.leaf_unsubscribed == [("TXF","202608")]`、`("TXF","202608") not in engine._leaf_done`);
  `test_leaf_unsubscribe_failure_warns_and_retries_on_next_hot_tick`(`fail_leaf_unsub` → 不炸、留 `_leaf_done`、下一筆 HOT 再試);
  `test_leaf_quote_after_hot_return_does_not_resubscribe`(退訂後 leaf 不再被補訂:p 非 None)。
- **SC-6 `FuturesQuoteSource.unsubscribe_leaf` 走 `_unsub`**:`tests/live/test_futures_source.py` 新增(已訂 → 送 UNSUBQUOTE 且移出
  `_subscribed`;未訂 → no-op 不送)。
- **SC-7 自癒閘盤別**:`tests/live/test_futures_source.py::test_in_futures_session_now`(monkeypatch 時鐘:08:30 F / 08:45 T /
  13:45 T / 14:00 F / 15:00 T / 23:59 T / 02:00 T / 05:00 T / 06:00 F)+ `tests/server/test_app.py`(或 test_main_wiring)
  `_default_futures_source` 的 `heal_active` 組合 = 日曆 AND 盤別(monkeypatch `in_futures_session_now`)。
- **SC-8 真環境**:prod 重啟後 `/ws/futures` 夜盤 20 s:訊息率 ≤ 10 則/s/商品(0.1 s 週期上限)、seq 連續無跳號、前端期貨 tab
  五檔仍跳動;對照 before(本輪開工量 `/ws/futures` 20 s 則數 / KB/s)。量法:scratchpad `websockets` 腳本(沿 R1 `sc4_measure.py`
  改 `/ws/futures`,統計 per-product 則數、seq gap 數、bytes)。**驗證窗口**:日盤 / 夜盤有行情時;窗口外降級 = `--verify` fake
  source 驗 shape + seq 連續。⚠ 需 prod 重啟(盤中不起第二台連 TC4)。
- **SC-9 UI 可指認**:期貨 tab 五檔 / 現價盤中仍即時跳動(肉眼無「卡一秒」感);閃電梯五檔同;user 過目。

## 不能破壞的既有行為白名單

- W1 WS 訊息 shape `{type:"futures", seq, product, state}` 不變;每則帶該 product 全量 state。
- W2 seq 嚴格連續 +1(前端跳號即 refetch);`/api/futures/state` 的 seq = 最後一則已廣播 seq、內容最新。
- W3 state 本身仍**每 quote 即時更新**(`corr_engine._futures_leg_book` pull 讀、`/api/futures/state` 即查即新)— 只有廣播被合併。
- W4 `test_push_after_close_no_broadcast_no_seq_no_error`:close 後推播不炸、seq 不變、無新廣播(flush timer 在 close 取消、`_loop` 斷後不再 flush)。
- W5 leaf fallback 既有語意:寬限期零推播補訂、once per (product, ym)、失敗下輪重試、close 後不補、換月重武裝、重連不清 `_leaf_fed`、
  HOT 成交回來撤 `_leaf_fed`(`TestLeafFallback` / `TestLeafFedDiscard` / `TestReconnect` 既有測試全不該紅)。
- W6 自癒閘在日盤 / 夜盤**內**行為與現況相同(閘開);`calendar=None` 仍純牆鐘;其他 source(stock / corr / index / TXO)閘不動。
- W7 `bars_range` / `fetch_day_1k` / `resolved_contract` / reconnect 對帳 / `_resub_loop` 不動。
- W8 `FakeFuturesSource`(tests/helpers)既有 caller(capital / market routes 測試)不受影響。

## Out of scope
- 舊月到期 leaf 退訂、HOT/leaf 同 product 解析層改動(`futures_models`)、WS 心跳(R3)、corr/index/stock 引擎節流、前端改動、
  `_heal_gate` 跨午夜週六邊界(既有已知)。

## Edge cases
1. flush timer pending 時 close():取消 timer、不廣播(W4)。
2. 同 product 在一輪 flush 內先 HOT 後 leaf quote(雙流):合併成一則最新 → 雙流流量歸零;退訂 leaf 後單流。
3. `_loop is None`(close 中)時 `_handle_quote` 不排 timer。
4. leaf 退訂 to_thread 在途中 close():沿 `_leaf_tasks` gather 收尾(同 subscribe 路徑)。
5. 退訂失敗(ConnectionError)→ warning、`_leaf_done` 保留 → 下一筆 HOT 成交再試(不無限重試:每筆 HOT 成交最多一次)。
   退訂 in-flight 期間再來 HOT 成交不得重複發 → 用 `_leaf_unsub_inflight` 集合擋。
6. 盤別閘 05:00–05:05 / 13:45–13:50 clamp 段仍開(寬 5 分)。

## Diff 級章節(三類)
- 🔴 commit A `futures 廣播 per-product coalesce(flush 0.1 s,seq 每則 +1)`:`futures_engine.py`(`flush_interval_secs` 建構參數、
  `_dirty: dict[str, None]`、`_flush_timer`、`_flush()`、close 取消);既有測試 `_make` 加 `flush_interval_secs=0.0`(test-infra,
  body 註 `test-infra-fix`),`TestState` 既有 assert **不該紅**;新 `TestCoalesce` SC-1~4 先紅。
- 🔴 commit B `HOT 成交回來退訂 leaf`:`futures_engine.py`(`_leaf_unsubscribe_blocking` / `_leaf_unsub_finish` / `_leaf_unsub_inflight`)、
  Protocol 加 `unsubscribe_leaf`、`live/futures_source.py` 實作、`tests/server/test_futures_engine.py::FakeSource` + `tests/helpers/
  fake_sources.py::FakeFuturesSource` 補 `unsubscribe_leaf`(記錄 + `fail_leaf_unsub`);SC-5/SC-6 先紅。既有 leaf 測試不該紅。
- 🔴 commit C `期貨自癒閘看盤別`:`live/futures_source.py` 新增 `in_futures_session_now()`(純時鐘函式,注入 `now` 便測);
  `app.py:_default_futures_source` 改 `_heal_gate(calendar, in_futures_session_now)`;SC-7 先紅。
- 🔵 無;🟢 無。既有測試「該紅」:無(`_make` 參數為 infra 調整非 assertion)。

## Known risks / P2 註記
(spec review 後補)
