# Change spec:futures 廣播 per-product coalesce + 自癒閘看盤別(/mod futures-broadcast-coalesce-leaf-unsub)

> **2026-08-19 user 拍板(spec review round-2 後):leaf 備胎訂閱本輪不退**(R2-3:退訂後 HOT 再被 TXO session 搶走推播時無再武裝路徑 →
> 凍結零訊號;coalesce 已讓雙流在 WS 層歸零)。commit B / SC-5 / SC-6 / D2c / D2g / D2h 全數撤下,記 next-time。slug 保留。

日期 2026-08-19。分流判定:**已成形方案**(handoff R2 指名落點與做法;D2 可逐分支)→ grilling 姿態;
規格來自 user 拍板 handoff → 預核准,非方向性抉擇標 `[auto-default]`。

## 拍板紀錄

- **D2 futures 廣播節流:保留 event-driven 但 per-product coalesce,flush 週期 0.1 s**
  `[auto-default: coalesce 0.1 s | reason: handoff 建議;五檔盤中要即時,1 s 週期會讓閃電梯五檔慢一秒;選項互換不改對外契約
  (WS shape / seq 連續 / GET state 同源皆保持),屬實作選擇]`
- **D2a seq 在 flush 時每則 +1(不在 quote 時)** `[auto-default | reason: 前端 useFuturesStream 以 seq 連續判跳號 → refetch;
  若 quote 遞增而廣播合併,每次合併都觸發 REST refetch 風暴]`
- **D2b 同一輪 flush 內多 product 各自一則(按 dirty 插入順序)**,不合併成一則多 product 訊息 `[auto-default | reason: 保持 shape]`
- ~~D2c leaf 退訂時機~~(**撤下,user 拍板不退**)
- **D2d 自癒閘盤別 = 日盤 08:40–13:50、夜盤 14:55–24:00 + 00:00–05:05(各寬 5 分)** `[auto-default | reason: 寬限避免邊界誤關自癒;
  handoff 附帶項]`。**實作 = 擴充既有 `copycat/live/session.py::in_txo_session(now, pad=timedelta(0))`**(TXO 與期貨同時段,
  檔頭自承;不另建第二張時段表)`[amendment 2026-08-19: review R6]`;`futures_source.in_futures_session_now()` =
  `in_txo_session(pad=timedelta(minutes=5))`;TXO source 仍呼叫預設 pad=0,行為不變。
- **D2e `flush_interval_secs` 建構子預設 0.1**(prod `app.py:803` 不傳即 0.1;測試 `_make` 顯式傳 0.0 = 下一輪 loop 立刻 flush,
  仍走同一條 flush 路徑)`[amendment 2026-08-19: review R2]`。
- **D2f seq 在 flush 時每個 dirty product 一律 `_seq += 1`,`_broadcast is None` 只是不送**(與現況 :426-427 同語意)
  `[amendment 2026-08-19: review R11]`。
- ~~D2g~~(撤下)
- ~~D2h~~(撤下;round-2 R2-3 指出 source 層 UNSUB→SUB 救不回同 symbol 衝突樣態,是 user 拍板不退的主因)

## 成功條件(SC)

- **SC-0 flush 不變式**(`[amendment 2026-08-19: review R8]`):進入 `_flush` 第一件事 `self._flush_timer = None`;逐 product
  `pop` dirty 後才廣播;單 product 廣播例外 `try/except Exception: logger.exception` 續行下一個,不中斷整輪、不留 timer 殘骸。
  驗證 `TestCoalesce::test_broadcast_exception_does_not_stall_stream`(broadcast 第一次 raise → 下一輪 quote 仍廣播、seq 續增)。
  `test_default_flush_interval_is_100ms`(`FuturesEngine(lambda: src)._flush_interval_secs == 0.1`)鎖 D2e。
  **close 不變式 `[amendment 2026-08-19: review R2-5]`**:`close()` 內 flush timer 的 cancel 緊接 `self._loop = None` 之後、任何
  await 之前;`_flush` 首行 `self._flush_timer = None` 後 `if self._loop is None: return`。驗證 `test_close_with_pending_flush_
  timer_does_not_broadcast`(interval 0.5:推 quote 標 dirty、不等 flush 直接 `await engine.close()` → `events` 不增、seq 不變)。
- **SC-1 同 product 連發 N 則 quote 在 flush 週期內 → 1 則廣播、payload 為最新 state、seq +1**:
  驗證 `tests/server/test_futures_engine.py::TestCoalesce::test_burst_same_product_coalesced`(`flush_interval_secs=0.05`,
  連推 5 則價不同 → sleep 0.2 → `len(events)==1`、`events[0]["state"]["p"]` = 最後一則、`seq==1`、`engine.state()["seq"]==1`)。
- **SC-2 不同 product 各自一則、seq 連續、GET state seq 同源**:`test_burst_two_products_two_messages_seq_contiguous`
  (TXF×3 + MXF×2 → 2 則、seq [1,2]、`state()["seq"]==2`)。
- **SC-3 flush 後新 quote 再推、兩輪 seq 連續**:`test_second_wave_after_flush`(第一波 → sleep → 第二波 → 共 2 則,seq [1,2])。
- **SC-4 latency 上限 = flush 週期**:`test_single_quote_delivered_within_interval`(interval 0.05,單 quote 在 0.1 s 內收到)。
- ~~SC-5 / SC-6(leaf 退訂)~~ 撤下(user 拍板)。
- **SC-7 自癒閘盤別**(`[amendment 2026-08-19: review R6/R1]`):`tests/live/test_session.py::test_in_txo_session_pad`
  鎖寬限邊界:08:39 F / 08:40 T / 13:50 T / 13:51 F / 14:54 F / 14:55 T / 05:05 T / 05:06 F(pad=5 分)+ pad=0 既有案例不變;
  `tests/live/test_futures_source.py::test_in_futures_session_now_uses_pad5`;**既有 `tests/server/test_main_wiring.py::
  test_futures_heal_gate_ands_the_calendar` 該紅 / 該改**:改為 monkeypatch `futures_mod.in_futures_session_now` 固定 True/False,
  驗週六 → False / 交易日+clock False → False / 交易日+clock True → True(不依賴真牆鐘)。
- **SC-8 真環境**(`[amendment 2026-08-19: review R2-1]`):prod 重啟後 `/ws/futures` 20 s(與 before 同盤別,夜盤對夜盤):
  (a) **同 product 相鄰兩則 WS 訊息最小間隔 ≥ 95 ms**(0.1 s 週期的直接指紋;no-op 下 before 量到 per-product 叢發 <10 ms 必紅);
  (b) seq 連續無跳號;(c) 20 s 總則數對 before 312 則的下降比例記錄(夜盤 per-product 本就 <10/s,收益主要在叢發合併,
  預期下降幅度以實測為準,不設門檻);(d) 前端期貨 tab 五檔仍跳動。before:prod b6d06f04 16:25 夜盤 312 則/20 s、5.89 KB/s、
  TMF 116/MXF 102/TXF 94、seq gaps 0、全域 inter-msg gap p50 0.9 ms(`evidence/SC-8-before-prod-b6d06f04-1625.txt`)。
  量法 `evidence/sc8_measure.py <port>`(已補 per-product gap min/p50)。
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
- W5 leaf fallback 既有語意**全部不動**(本輪不退訂):寬限期零推播補訂、once per (product, ym)、失敗下輪重試、close 後不補、
  換月重武裝、重連不清 `_leaf_fed`、HOT 成交回來撤 `_leaf_fed`(`TestLeafFallbackSubscribe` / `TestRetrySuccessLeafBookkeeping` /
  `TestReconnectReconciliation::test_reconnect_does_not_clear_leaf_fed` 既有測試全不該紅)`[amendment 2026-08-19: review R2-4]`。
- W6 自癒閘在日盤 / 夜盤**內**行為與現況相同(閘開);`calendar=None` 仍純牆鐘;其他 source(stock / corr / index / TXO)閘不動。
- W7 `bars_range` / `fetch_day_1k` / `resolved_contract` / reconnect 對帳 / `_resub_loop` 不動。
- W8 `FakeFuturesSource`(tests/helpers)既有 caller(capital / market routes 測試)不受影響。
- W9 `tests/server/test_capital_api.py::TestWebSockets::test_ws_futures_streams_quote`(推一筆後 blocking receive,0.1 s 延遲仍綠)
  與 `tests/server/test_ws_disconnect.py` `/ws/futures` case(`want=4` 批 / 15 s timeout 仍過)不該紅;後者註解的「75 次寫入」
  論證在 futures 一路的**寫入次數**降為 ~15 次(pump 次數不受影響),實作時在該註解(:614 附近)加註仍遠超 5 次門檻;
  不改 `create_app` 簽名 `[amendment 2026-08-19: review R10/R2-6]`。
- W10 `FuturesQuoteSource.__init__` docstring(:58-60)與 `tests/live/test_futures_source.py::TestHealDefaults` 說明文字隨 commit C
  更新口徑(prod = 日曆 AND 盤別)`[amendment 2026-08-19: review R13]`。

## Out of scope
- **leaf 備胎退訂整組**(user 拍板不退;含 `unsubscribe_leaf` Protocol / source 實作 / 靜默再武裝設計 → next-time)、
  HOT/leaf 同 product 解析層改動(`futures_models`)、WS 心跳(R3)、corr/index/stock 引擎節流、前端改動。
- `_heal_gate` 跨午夜段日曆歸屬仍以當日日期判:週六凌晨 00:00–05:00 假關(既有已知)、**週一 / 長假後首交易日凌晨 00:00–05:05
  假開**(對稱破口,同源;真修法 = 凌晨段改查前一日 `is_trading_day`,記 next-time)`[amendment 2026-08-19: review R2-7]`。

## Edge cases
1. flush timer pending 時 close():取消 timer、不廣播(W4)。
2. 同 product 在一輪 flush 內先 HOT 後 leaf quote(雙流):合併成一則最新 → 雙流 WS 流量歸零(leaf 不退,engine 仍收兩流)。
3. `_loop is None`(close 中)時 `_handle_quote` 不排 timer。
4. leaf 退訂 to_thread 在途中 close():沿 `_leaf_tasks` gather 收尾(同 subscribe 路徑)。
5. ~~退訂失敗~~(撤下)
6. 盤別閘 05:00–05:05 / 13:45–13:50 clamp 段仍開(寬 5 分)。
7. flush 中 broadcast 拋例外 → 該 product 記 log 續行,timer 已歸 None,下一筆 quote 照排(SC-0)。
8. ~~leaf in-flight 交錯~~(撤下)

## Diff 級章節(三類)
- 🔴 commit A `futures 廣播 per-product coalesce(flush 0.1 s,seq 每則 +1)`:`futures_engine.py`(`flush_interval_secs: float = 0.1`
  建構參數、`_dirty: dict[str, None]`、`_flush_timer`、`_flush()`(SC-0 不變式)、close 取消);`app.py:803` 不動(吃預設 0.1);
  既有測試 `_make` 加 `flush_interval_secs=0.0`(test-infra,body 註 `test-infra-fix`),`TestState` 既有 assert **不該紅**;
  新 `TestCoalesce` SC-0~4 先紅。W9 兩測試不該紅。
- ~~🔴 commit B(leaf 退訂)~~ 撤下(user 拍板)。
- 🔴 commit C `期貨自癒閘看盤別`:`live/session.py::in_txo_session(now, pad=timedelta(0))` 加 pad;`live/futures_source.py` 新增
  `in_futures_session_now()`(= pad 5 分)+ docstring 口徑更新;`app.py:_default_futures_source` 改 `_heal_gate(calendar,
  in_futures_session_now)`;`tests/live/test_futures_source.py::TestHealDefaults` 說明文字更新;SC-7 先紅;
  **既有 `test_main_wiring.py::test_futures_heal_gate_ands_the_calendar` 該紅 → 改寫**(見 SC-7)。
- 🔵 無;🟢 無。既有測試「該紅」:僅上列一條。

## Known risks / P2 註記(spec review round-1:P0×2 / P1×6 / P2×6 全 accepted;round-2:P1×3 / P2×4 — R2-2/R2-3 因撤下 leaf
退訂而 moot,其餘 accepted)
- leaf 退訂撤下後雙訂閱續存:engine 仍處理 HOT+leaf 兩流(CPU 微量),WS 層由 coalesce 合併。
- R10:`test_ws_disconnect` futures 一路寫入次數論證裕度變薄(~15 次 vs 5 次門檻),實作加註。
