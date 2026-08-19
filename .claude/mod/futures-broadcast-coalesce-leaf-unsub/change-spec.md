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
  handoff 附帶項]`。**實作 = 擴充既有 `copycat/live/session.py::in_txo_session(now, pad=timedelta(0))`**(TXO 與期貨同時段,
  檔頭自承;不另建第二張時段表)`[amendment 2026-08-19: review R6]`;`futures_source.in_futures_session_now()` =
  `in_txo_session(pad=timedelta(minutes=5))`;TXO source 仍呼叫預設 pad=0,行為不變。
- **D2e `flush_interval_secs` 建構子預設 0.1**(prod `app.py:803` 不傳即 0.1;測試 `_make` 顯式傳 0.0 = 下一輪 loop 立刻 flush,
  仍走同一條 flush 路徑)`[amendment 2026-08-19: review R2]`。
- **D2f seq 在 flush 時每個 dirty product 一律 `_seq += 1`,`_broadcast is None` 只是不送**(與現況 :426-427 同語意)
  `[amendment 2026-08-19: review R11]`。
- **D2g 退訂涵蓋該 product 全部 `_leaf_done` ym(含跨日累積的舊月)**;Out of scope 改寫為「不另建到期偵測機制」
  `[amendment 2026-08-19: review R5]`。
- **D2h 退訂後 HOT 二度靜默的復原 = source 層 per-symbol 自癒**(`FuturesQuoteSource(heal_symbol_silence_secs=60)` +
  tc4 窗口 variant 逃逸 + 08-18 refcount 修正)— 不另建 engine 層再武裝(既有 pending 判準 `st.p is None` 只冷啟動一次、
  跨日重武裝只掃 `_leaf_fed`,兩者在退訂後都不會再武裝 leaf)。失效樣態若發生 = 該品凍結在最後一筆價;記 Known risks 與
  next-time 觀察項 `[amendment 2026-08-19: review R4 — 選 (a)]`。

## 成功條件(SC)

- **SC-0 flush 不變式**(`[amendment 2026-08-19: review R8]`):進入 `_flush` 第一件事 `self._flush_timer = None`;逐 product
  `pop` dirty 後才廣播;單 product 廣播例外 `try/except Exception: logger.exception` 續行下一個,不中斷整輪、不留 timer 殘骸。
  驗證 `TestCoalesce::test_broadcast_exception_does_not_stall_stream`(broadcast 第一次 raise → 下一輪 quote 仍廣播、seq 續增)。
  `test_default_flush_interval_is_100ms`(`FuturesEngine(lambda: src)._flush_interval_secs == 0.1`)鎖 D2e。
- **SC-1 同 product 連發 N 則 quote 在 flush 週期內 → 1 則廣播、payload 為最新 state、seq +1**:
  驗證 `tests/server/test_futures_engine.py::TestCoalesce::test_burst_same_product_coalesced`(`flush_interval_secs=0.05`,
  連推 5 則價不同 → sleep 0.2 → `len(events)==1`、`events[0]["state"]["p"]` = 最後一則、`seq==1`、`engine.state()["seq"]==1`)。
- **SC-2 不同 product 各自一則、seq 連續、GET state seq 同源**:`test_burst_two_products_two_messages_seq_contiguous`
  (TXF×3 + MXF×2 → 2 則、seq [1,2]、`state()["seq"]==2`)。
- **SC-3 flush 後新 quote 再推、兩輪 seq 連續**:`test_second_wave_after_flush`(第一波 → sleep → 第二波 → 共 2 則,seq [1,2])。
- **SC-4 latency 上限 = flush 週期**:`test_single_quote_delivered_within_interval`(interval 0.05,單 quote 在 0.1 s 內收到)。
- **SC-5 HOT 成交回來 → 該 product 已訂 leaf 全退**(`[amendment 2026-08-19: review R5/R9/R12/R14]`;既有類名 =
  `TestLeafFallbackSubscribe` / `TestRetrySuccessLeafBookkeeping` / `TestReconnectReconciliation`):
  `TestLeafUnsubscribe::test_hot_tick_unsubscribes_leaf`(leaf 補訂後推 `TC.F.TWF.TXF.HOT` 成交 → `src.leaf_unsubscribed ==
  [("TXF","202608")]`、`("TXF","202608") not in engine._leaf_done`);`test_hot_tick_unsubscribes_all_ym`(`_leaf_done` 有
  202608 + 202609 → 兩筆都退、該 product 清空);`test_leaf_unsubscribe_failure_warns_and_retries_after_backoff`(`fail_leaf_unsub`
  → 不炸、留 `_leaf_done`;**退避**:同 key 失敗後 `leaf_unsub_backoff_secs`(預設 30,測試傳 0.05)內的 HOT 成交不再發,
  過後再試;in-flight 期間不重複發);`test_leaf_not_resubscribed_after_hot_return`(退訂後再推 leaf quote / 新 ym →
  `src.leaf_subscribed.count(("TXF", ym))` 不增加、key 不回 `_leaf_done`)。Edge:leaf subscribe in-flight 時 HOT 回來 →
  本輪掃不到、**靠下一筆 HOT 成交 tick 收掉,不在 `_leaf_finish` 加分支**。
- **SC-6 `FuturesQuoteSource.unsubscribe_leaf` 走 `_unsub`,不呼叫 `_ensure_connected` / `_start_listener`**
  (`[amendment 2026-08-19: review R7]`;close 後 executor 工作項不得重建連線 — review I1 / KeepAlive 洩漏教訓):
  `tests/live/test_futures_source.py` 新增(已訂 → 送 UNSUBQUOTE 且移出 `_subscribed`;未訂 → no-op 不送;api 未連線
  呼叫不觸發 Connect — FakeApi Connect 次數 0)。
- **SC-7 自癒閘盤別**(`[amendment 2026-08-19: review R6/R1]`):`tests/live/test_session.py::test_in_txo_session_pad`
  鎖寬限邊界:08:39 F / 08:40 T / 13:50 T / 13:51 F / 14:54 F / 14:55 T / 05:05 T / 05:06 F(pad=5 分)+ pad=0 既有案例不變;
  `tests/live/test_futures_source.py::test_in_futures_session_now_uses_pad5`;**既有 `tests/server/test_main_wiring.py::
  test_futures_heal_gate_ands_the_calendar` 該紅 / 該改**:改為 monkeypatch `futures_mod.in_futures_session_now` 固定 True/False,
  驗週六 → False / 交易日+clock False → False / 交易日+clock True → True(不依賴真牆鐘)。
- **SC-8 真環境**:prod 重啟後 `/ws/futures` 夜盤 20 s:訊息率 ≤ 10 則/s/商品(0.1 s 週期上限)、seq 連續無跳號、前端期貨 tab
  五檔仍跳動;對照 before(已量:prod b6d06f04 16:25 夜盤 312 則/20 s、5.89 KB/s、TMF 116/MXF 102/TXF 94、seq gaps 0、
  inter-msg gap p50 0.9 ms → 叢發;`evidence/SC-8-before-prod-b6d06f04-1625.txt`)。量法 `evidence/sc8_measure.py <port>`。
  **驗證窗口**:日盤 / 夜盤有行情時;窗口外降級 `[amendment 2026-08-19: review R3]` = sidecar(照
  `.claude/mod/ladder-pills-avgpct/evidence/fake_server.py::PushingFuturesSource` 樣板改成高頻推 quote,`create_app(...,
  futures_source=...)` 非 canonical port、`neutralize_external_env()`)驗 (1) 同 product 每 0.1 s 至多一則 (2) seq 連續 (3) shape 不變。
  ⚠ prod 真 TC4 層需 prod 重啟(盤中不起第二台連 TC4)。
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
- W9 `tests/server/test_capital_api.py::TestWebSockets::test_ws_futures_streams_quote`(推一筆後 blocking receive,0.1 s 延遲仍綠)
  與 `tests/server/test_ws_disconnect.py` `/ws/futures` case(`want=4` 批 / 15 s timeout 仍過)不該紅;後者註解的「75 次寫入」
  論證在 futures 一路降為 ~15 次,實作時在該註解加註(或該 case 顯式傳小 flush 值)`[amendment 2026-08-19: review R10]`。
- W10 `FuturesQuoteSource.__init__` docstring(:58-60)與 `tests/live/test_futures_source.py::TestHealDefaults` 說明文字隨 commit C
  更新口徑(prod = 日曆 AND 盤別)`[amendment 2026-08-19: review R13]`。

## Out of scope
- 不另建舊月到期偵測機制(到期 leaf 隨 HOT 回魂的全 ym 退訂一併退;未回魂則留)、HOT/leaf 同 product 解析層改動
  (`futures_models`)、WS 心跳(R3)、corr/index/stock 引擎節流、前端改動、`_heal_gate` 跨午夜週六邊界(既有已知)、
  engine 層 leaf 再武裝(D2h)。

## Edge cases
1. flush timer pending 時 close():取消 timer、不廣播(W4)。
2. 同 product 在一輪 flush 內先 HOT 後 leaf quote(雙流):合併成一則最新 → 雙流流量歸零;退訂 leaf 後單流。
3. `_loop is None`(close 中)時 `_handle_quote` 不排 timer。
4. leaf 退訂 to_thread 在途中 close():沿 `_leaf_tasks` gather 收尾(同 subscribe 路徑)。
5. 退訂失敗(ConnectionError)→ warning、`_leaf_done` 保留 → 退避 `leaf_unsub_backoff_secs`(30)後的下一筆 HOT 成交再試;
   in-flight 期間不重複發(`_leaf_unsub_inflight`;`_leaf_unsub_next: dict[key, monotonic]`)。
6. 盤別閘 05:00–05:05 / 13:45–13:50 clamp 段仍開(寬 5 分)。
7. flush 中 broadcast 拋例外 → 該 product 記 log 續行,timer 已歸 None,下一筆 quote 照排(SC-0)。
8. leaf subscribe in-flight 時 HOT 成交回來 → 本輪退訂掃不到;`_leaf_finish` 之後寫入 `_leaf_done`,下一筆 HOT 成交收掉(不加分支)。

## Diff 級章節(三類)
- 🔴 commit A `futures 廣播 per-product coalesce(flush 0.1 s,seq 每則 +1)`:`futures_engine.py`(`flush_interval_secs: float = 0.1`
  建構參數、`_dirty: dict[str, None]`、`_flush_timer`、`_flush()`(SC-0 不變式)、close 取消);`app.py:803` 不動(吃預設 0.1);
  既有測試 `_make` 加 `flush_interval_secs=0.0`(test-infra,body 註 `test-infra-fix`),`TestState` 既有 assert **不該紅**;
  新 `TestCoalesce` SC-0~4 先紅。W9 兩測試不該紅。
- 🔴 commit B `HOT 成交回來退訂 leaf`:`futures_engine.py`(`_leaf_unsubscribe_blocking` / `_leaf_unsub_finish` / `_leaf_unsub_inflight` /
  `_leaf_unsub_next` / `leaf_unsub_backoff_secs=30.0`)、Protocol 加 `unsubscribe_leaf`、`live/futures_source.py` 實作(不 ensure_connected)、
  `tests/server/test_futures_engine.py::FakeSource` + `tests/helpers/fake_sources.py::FakeFuturesSource` 補 `unsubscribe_leaf`
  (記錄 `leaf_unsubscribed` + `fail_leaf_unsub`);SC-5/SC-6 先紅。既有 leaf 測試不該紅。
- 🔴 commit C `期貨自癒閘看盤別`:`live/session.py::in_txo_session(now, pad=timedelta(0))` 加 pad;`live/futures_source.py` 新增
  `in_futures_session_now()`(= pad 5 分)+ docstring 口徑更新;`app.py:_default_futures_source` 改 `_heal_gate(calendar,
  in_futures_session_now)`;`tests/live/test_futures_source.py::TestHealDefaults` 說明文字更新;SC-7 先紅;
  **既有 `test_main_wiring.py::test_futures_heal_gate_ands_the_calendar` 該紅 → 改寫**(見 SC-7)。
- 🔵 無;🟢 無。既有測試「該紅」:僅上列一條。

## Known risks / P2 註記(spec review round-1:P0×2 / P1×6 / P2×6,全 accepted)
- R4(D2h):退訂 leaf 後 HOT 二度靜默靠 source 層 per-symbol 自癒;若真環境出現「期貨某檔凍結在最後一筆價」→ 回頭做 engine 層
  再武裝(next-time 記錄)。
- R10:`test_ws_disconnect` futures 一路寫入次數論證裕度變薄(~15 次 vs 5 次門檻),實作加註。
