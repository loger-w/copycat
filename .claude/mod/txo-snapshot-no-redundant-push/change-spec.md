# Change spec:TXO `/ws/txo-pnl` 只在內容有變時推播(/mod txo-snapshot-no-redundant-push)

日期 2026-08-19。分流判定:**已成形方案**(handoff R1 指名落點 `engine.py:295-297` / `:127-137`
與做法「外來 tick 不標 changed + 內容不變不推」;決策點 D1 可逐分支)→ grilling 姿態,
規格來自 user 拍板的 handoff 檔 → 預核准,非方向性抉擇標 `[auto-default]`。

## 拍板紀錄

- **D1 TXO 快照推播:兩者皆做**(route 早退不標 changed + snapshots() 內容比對短路)
  `[auto-default: 兩者皆做 | reason: handoff 建議即為兩者;單做 route 判定擋不住「TC4 重推同 cum
  的 stale tick」與「spot 同價 tick」以外的未來新來源,單做內容比對每 tick 仍要建 22 KB 快照
  再丟;選項互換不改 SC 集合 / 對外契約(payload shape 不變),屬實作選擇]`
- **D1a 判定粒度放在 `ChainAggregator.route` 回 bool**(不在 engine 端 hash 比對)
  `[auto-default: route 回 bool | reason: 三條早退(foreign / stale-drop / spot 同價)全在 aggregate 內部,
  engine 沒有可觀測訊號;bool 回傳是加法,舊 caller 忽略回傳值不破]`
- **D1b 內容比對排除 `generated_at`**;`更新 HH:MM:SS` 前端標籤語意變成「最後內容變動時間」
  `[auto-default: 排除 generated_at | reason: 不排除等於沒比;時戳只在 App.tsx:357 顯示、無邏輯依賴]`
- **D1c 附帶 `WS-TXO-SHARED-EVENT` 同輪修**:`_changed` 改「換代 Event」(set 舊、換新),consumer
  先比 version 再等當下 Event,不再 `clear()`
  `[auto-default: 換代 Event | reason: 修法最小、無鎖;handoff 點名可同輪]`

## 成功條件(SC)

- **SC-1 外來 / stale / spot 同價 tick 不觸發推播**:`ChainAggregator.route()` 回 `bool`;foreign 早退、
  `_ingest` stale-drop、spot 價未變 → `False`;`_consume` 只在 `True` 時 `_mark_changed()`。
  驗證:`tests/live/test_aggregate.py` 新增 `test_route_returns_change_flag`(四種 tick 的回傳值);
  `tests/server/test_engine.py::test_snapshots_ignores_foreign_and_stale_ticks`。
  **「沒推」判法 `[amendment 2026-08-19: review R1]`**:不得對 `agen.__anext__()` 用 `wait_for` 逾時
  (cancel 會終結 async generator,之後只剩 StopAsyncIteration)— 一律
  `task = asyncio.ensure_future(agen.__anext__()); await asyncio.sleep(0.3); assert not task.done()`,
  再餵真 tick → `await asyncio.wait_for(task, 1.0)` 取同一則。收尾規約 `[amendment 2026-08-19: review R15]`:
  task 仍 pending 的分支一律 `task.cancel()` + `suppress(CancelledError, StopAsyncIteration)` await;取消過的
  generator 視為終結不得再迭代(要續驗重建 `rt.snapshots()`);只有 task 已完成的路徑才 `agen.aclose()`。
- **SC-2 內容不變不推**:`snapshots()` 與上一則 yield 的 payload(排除 `generated_at`)相同 → 不 yield。
  比對**以複本比較,不得改動送出的 dict**(`{k: v for k, v in snap.items() if k != "generated_at"}`);
  比對範圍 = 整個 payload 減 `generated_at`,**不得再縮**(`totals.ticks` / per-contract volume 都算)
  `[amendment 2026-08-19: review R7/R9]`。
  驗證:`tests/server/test_engine.py::test_snapshots_skips_identical_payload`(**先餵一筆真 tick 取到第一則**
  (建立 `prev` 基準),再 `rt._mark_changed()` 兩次且中間無狀態改動 → pending task 0.3 s 不完成、
  且 `await asyncio.sleep(0.3)` 正常返回(= 迴圈在等待非空轉);`_set_status("degraded")` 後 → 同一 task
  取到,且 payload 仍含 `generated_at` 為 `HH:MM:SS` 字串)。
  **`prev` 初值與迴圈不變式 `[amendment 2026-08-19: review R12/R13]`**:
  - `seed=None` → `prev = None`(第一次 version 變動一律 yield = 舊語意,`test_snapshots_throttled_stream_yields_on_change` 不變);
    `seed` 給 → `prev = strip(seed)`、`last = -1`。
  - 迴圈每輪:(a) `if self._version == last: ev = self._changed(每輪重讀不快取); await ev.wait(); continue`;
    (b) **`last = self._version` 必在內容比對之前**;內容相同 → 只 `continue`(不重設 last、不 sleep);
    (c) 只有 yield 之後才 `await asyncio.sleep(self._throttle)`。違反 (b) = 換代 Event 永遠 set → 無 await
    tight loop 餓死 event loop。
- **SC-3 多 client 不漏版本**(`WS-TXO-SHARED-EVENT`,驗的是 Event 換代 / 先比 version,不是內容比對):
  兩個 `snapshots()` 併行迭代,client A 取第一則後停在 throttle sleep;此時以**內容真的會變**的方式 bump
  (餵一筆新 cum 的合約 tick)`[amendment 2026-08-19: review R2]`;client B 取到;client A 下一次
  `__anext__` 在 1.0 s 內取到(現況卡在已被 B `clear()` 的 Event → 紅)。bare `_mark_changed()` 在此情境
  被內容比對吃掉不算漏版本。驗證:`test_snapshots_two_clients_no_lost_wakeup`(throttle 0.05)。
- **SC-3b 首則與串流同源** `[amendment 2026-08-19: review R3]`:`snapshots(seed=<首則 payload>)`;
  app.py 把已送的首則傳入,generator 首次迭代對 seed 做內容比對 —— 首則送出後、迭代開始前發生的
  tick 仍會在下一則推出;無變動則不重推首則。驗證:`test_snapshots_seed_pushes_only_if_changed`
  (seed = `latest_snapshot()`,不動 → pending 0.3 s;先餵 tick 再建 `snapshots(seed=舊 snap)` →
  首次迭代立即取到新內容)。`seed=None` 保留舊語意(`last = self._version`、`prev = None`,測試 / 舊 caller 相容)。
  **app.py 接線 `[amendment 2026-08-19: review R16]`**:seed 必須是傳給 `send_json` 的**同一個 dict 物件**,不得
  二次呼叫 `latest_snapshot()`;驗證 `tests/server/test_app.py::TestWebSocket::test_ws_seed_is_first_sent_snapshot`
  (monkeypatch `app.state.runtime.latest_snapshot` 記錄回傳物件、`snapshots` 記錄 `seed`;連線後 assert
  `latest_snapshot` 恰被叫一次且 `seed is` 該物件)。
- **SC-4 真環境流量** `[amendment 2026-08-19: review R6]`:盤後(TXO 無成交)`/ws/txo-pnl` 20 s 窗:
  (1) 首則必收且 `series_id` 非 null;(2) 20 s 內訊息數 ≤ 1;(3) 窗結束 WS 仍 open、無 close;
  (4) 反向對照:窗後 `GET /api/txo/snapshot` 與首則比對,排除集合 = `{generated_at, totals.dropped_foreign_ticks,
  totals.queue_dropped}`(W7 允許這兩個診斷計數 WS 落後 GET;其增量反而是 SC-1 正向佐證,一併記錄)
  `[amendment 2026-08-19: review R14]`。量法:scratchpad `websockets`
  腳本(對照 handoff 量測 20 則)。**驗證窗口**:盤後 / 夜盤外(無 TXO 成交);窗口外(盤中)降級 =
  「連續兩則內容(排除 generated_at)不得相同」+ (1)(3)。⚠ 需 prod 重啟載新碼;重啟前只能記
  「待 prod 重啟後量」。
- **SC-5 UI 可指認** `[amendment 2026-08-19: review R8]`:TXO 頁 **footer**(`App.tsx:352-358`,同列有
  tick 數 / 未分類 / 佇列丟棄)「更新 HH:MM:SS」在無成交時**不再逐秒跳動**,有成交才變;驗證:prod
  重啟後盤後截圖兩張間隔 10 s(含 footer 整列),時戳相同(user 過目)。

## 不能破壞的既有行為白名單

- W1 `/ws/txo-pnl` accept 後**立即送首則** `latest_snapshot()`(app.py:1142;`test_ws_disconnect` 依此)。
- W2 真 TXO tick(新 cum)→ 1 則推播且仍受 `throttle_secs` 節流(`test_snapshots_throttled_stream_yields_on_change`、
  `TestWebSocket::test_first_message_then_push`)。
- W3 status 轉換(backfilling / degraded / live)一律推播(`_set_status` 不動;內容含 status 必不同)。
- W4 spot(TXF)價**變動**→ 推播(`spot_pnl` / `spot.price` 依賴)。
- W5 `dropped_foreign_ticks` / `ticks` / `unclassified_*` 計數語意不變、payload shape 不變
  (`test_aggregate.py` 既有 assert 全部不該紅)。
- W6 self-heal / rollover / handover 流程不動(`_consume` 只改 `_mark_changed` 的條件)。
- W7 `dropped_foreign_ticks` 計數仍在 payload,但**在下一次真變動前不會單獨推出**(可接受:診斷計數,
  `/api/txo/snapshot` 隨查隨新)。
- W8 `tests/server/test_ws_disconnect.py::TestAbruptDisconnect::test_no_write_to_dead_transport` 不該紅:
  其 `_tick(cum)` 只有 cum / precise_time 遞增、價量五檔全同,`batches >= 3` 靠 `totals.ticks` /
  per-contract volume 每筆都動 → 內容比對範圍不得縮(見 SC-2)。⚠ 此測試在 master 整檔跑本就間歇紅
  (baseline 實證,memory 已載),單跑綠;判讀以單跑為準 `[amendment 2026-08-19: review R9]`。
- W9 `copycat/live/handover.py:63` flush 路徑逐筆 `agg.route(tick)` **忽略回傳值**;交接結束由
  `_set_status("live")` 統一 `_mark_changed`,不需在 `run_handover` 累加旗標 `[amendment 2026-08-19: review R4]`。

## Out of scope

- 應用層心跳 / 靜默 watchdog(R3)、futures 廣播節流(R2)、前端 `useTxoSnapshot` 任何改動、
  `TXO-ROLLOVER-FULL-HANDOVER`、TXO/futures 雙持 `TXF.HOT`(next-time 既有條)。
- 不動 `relay()`、不動 `latest_snapshot()`、不做 delta 推播。

## Edge cases

1. 第一個 client 連上時 `_version` 已 > 0:`snapshots()` 起手 `last = self._version`,不會重播舊版(現況相同;
   首則由 route 直送)。
2. `_mark_changed` 在 consumer sleep 期間連續多次:consumer 醒來比 version 不等 → 取一則(合併),不會逐則補推。
3. 內容相同但 `_set_status` 同值重設(如 degraded → degraded):內容比對短路不推(現況會推一則重複)。
4. handover 期間 `_buffer` 收 tick 不走 `_consume`,flush 走 `run_handover`(內部逐筆 `route`,忽略回傳值)
   → 之後 `_set_status("live")` 推;不變 `[amendment 2026-08-19: review R4]`。
6. 首則與 generator 起手之間的空窗(app.py `send_json` 是真 await):由 SC-3b seed 機制補齊。
5. Event 換代:`_mark_changed` 只在 loop thread 呼叫(`_enqueue` 經 `call_soon_threadsafe`、`_set_status` 在
   coroutine 內)— 無跨執行緒建 Event 問題。

## Diff 級章節(三類標記)`[amendment 2026-08-19: review R5 — Event 換代是 bug fix 非 refactor]`

- 🔵 無純重構。
- 🔴 commit A `fix(backend): /ws/txo-pnl 多 client 共用 Event 漏版本`:`engine.py` `_mark_changed` 改
  「set 舊 Event、換新 Event」;`snapshots()` 先比 version 再等當下 Event、不再 `clear()`。
  紅測試 SC-3 `[red]` → 綠 `[green]`。既有 `test_snapshots_throttled_stream_yields_on_change` 不該紅。
- 🔴 commit B `fix(backend): TXO 快照只在內容有變才推`:`aggregate.py` `route()` 回 `bool`;`engine.py`
  `_consume` 條件 `_mark_changed`、`snapshots(seed=None)` 內容比對(複本);`app.py:1143` 傳 seed。
  紅測試 SC-1(aggregate + engine)/ SC-2 / SC-3b `[red]` → `[green]`。既有測試:全部不該紅。
- 🟢 無新功能。
- 既有測試「該紅」:無。

## Known risks / P2 註記(spec review round-1 11 條 + round-2 5 條,全部 accepted)

- R10:有行情時(spot 每次價變)仍每 throttle 週期推整包 ~22 KB;本輪省的是無成交空窗與 stale/foreign
  tick 造成的流量;delta / 分欄推播 out of scope。SC-4 量測順帶記夜盤 / 盤中 20 s 訊息數與 KB/s 前後對照
  (觀測型,非 gate)。
- R11:改後 `/ws/txo-pnl` 可長時間零訊息;保活靠 uvicorn ws ping(已查:venv 裝 `websockets 16.1.1`、
  無 `wsproto` → `ws="auto"` 選 websockets,預設 ping 20 s)。SC-4 (3) 順帶驗 20 s 靜默後仍 open。
  應用層心跳仍留 R3。
