# Change spec:signals/today 讀檔移出 event loop(mod/signals-today-offload)

> S 級(單一 production 行 / 對外 API 零變更 / 無 migration)→ 0 輪 spec review。
> 分流判定一行:已成形(handoff R5 指名行號 + 修法)。

## 成功條件

- **SC-1** `GET /api/stock/signals/today` 的 `today_signals()` 不在 event loop 執行緒執行
  (probe:替換後的 `today_signals` 內 `asyncio.get_running_loop()` 必須 raise RuntimeError)。
  驗證:pytest `TestSignalsTodayRoute::test_reads_jsonl_off_event_loop`(紅先行)。
- **SC-2** 既有測試不紅(白名單全保留)。驗證:`pytest -q` 全綠。

真實環境層:阻塞消除是負向效應(不卡),無畫面可指認元素;真環境 = prod 重啟後
`curl /api/stock/signals/today` 200 形狀不變(user 端無感即正確)。

## 不能破壞的既有行為白名單

1. 回傳形狀 `{"signals":[...]}`、jsonl 舊在前順序、兩日聯集 / 同日單檔讀語意(hub 未動)。
2. hub 缺席 → 503 `NOT_READY`(`_signals` 在 to_thread 之前同步 raise)。
3. legacy `?market=exclude` 忽略照樣 200 同結果。
4. 壞行跳過 / `errors="replace"`(read_signals 未動)。
5. hub 方法保持同步 API(測試同步直呼 + `read_signals` 動態替換手法照舊)。

## Out of scope

- signals/today 加 meta(dropped 計數,next-time 既有條目)。
- 其他 route 的同步 IO 盤點(本輪只修 handoff 指名這條)。

## 拍板(auto-default,無方向性抉擇)

- [auto-default: route 層 `asyncio.to_thread` 而非 hub 改 async / aiofiles | reason: hub API
  動了要改 5 處測試呼叫 + 動態替換手法;aiofiles 新依賴違反 stdlib-only runtime;寫入路徑
  先例就是 to_thread(signal_hub.py:885)]

## Edge cases

1. hub 缺席:503 在 to_thread 之前,不進 thread。
2. 讀取中 flush worker 併發 append(半寫入尾行):read_signals 既有壞行跳過處理。
   [amendment 2026-08-20: review C-2 — 非「等價」:route 在 await 讓出 loop 後 worker 可
   於讀取進行中 dispatch append,交錯窗口放寬;但失效模式不變(壞行跳過 + 跳過計數
   WARNING 可觀測 + 前端 id 去重),非新種類風險]
3. `today_signals` 內部丟非預期例外:to_thread 重拋回 await 處 → 全域 handler 收 502,
   與原同步呼叫一致。

## Diff 級章節

### 🔴 `copycat/server/app.py`(行為改動:執行緒語意)

- `stock_signals_today`:`return {"signals": _signals(request).today_signals()}` →
  `return {"signals": await asyncio.to_thread(_signals(request).today_signals)}`
  (`_signals(request)` 先在 loop 內求值,503 路徑不變)。

### 🔴 `tests/server/test_signal_routes.py`

- **該紅(新增,red 先行)**:`test_reads_jsonl_off_event_loop`(probe 替換
  `hub.today_signals`,斷言不在 running loop 內)。
- **不該紅**:`TestSignalsTodayRoute` 既有 3 條與全檔其餘測試。

## 三類 commit 計畫

1. `🔴 test(backend): signals/today 讀檔不得在 event loop 的紅測試 [red]`
2. `🔴 fix(backend): signals/today 的 jsonl 讀取移到 asyncio.to_thread [green]`
3. `chore(mod-signals-today-offload): artifacts`

無 🔵 / 🟢;migration 無。
(實際多一筆 `🟢 test … [lock]`:review 補強測試 + route 註解,見 code-review-round-1.json)

self_review_head: 97c08d3a
