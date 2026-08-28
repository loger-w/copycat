# mod/tc4-disconnected-log-flood — change spec

來源:`docs/next-time.md` 08-28 A7 節「TC4 斷線期間 log 洪水」;user 08-28 拍板「可以現在做」。
真環境樣本:`logs/server-20260828-1509.log` 15:12–15:24(斷達錢 4 11.5 分鐘,6764 行 / 585 KB)。

## 0. 現況 vs 目標

| 來源 | 現況(11.5 分) | 目標 |
|---|---|---|
| `_check_stale` 失敗 `logger.exception` | 70 發 × ~58 行巢狀 traceback ≈ 4100 行,內容每發相同 | 同一段斷線第 1 發全 traceback;之後每發一行 `reconnect attempt failed (#n): <Type>: <msg>, backoff Ns`(D3) |
| `_heal_tick` → `_heal` 逐 symbol「零推播自癒 … → 重掛」 | 1206 行;重掛送不出去卻記帳 +1(退避推到 300 s、換窗) | quote 未連線 → 整輪跳過、不記帳(D1) |
| `_heal_resub` 逐 symbol「自癒重掛失敗 …: quote not connected」 | 1206 行 | 同上,不會走到 |
| 「等連線」提示 | 無 | 進入未連線狀態印一次 WARNING `TC4 REALTIME 自癒:quote 未連線,N 腿待重連後接手(略過巡檢,不記帳)`;接回不另印(已有 `TC4 reconnected`)(D2) |

「未連線」的判準 = `_connection()` 同一把尺:`_api_lock` 下 `_api is None or _session is None`(`_dispose` 清、`_ensure_connected` 發布)。

## 1. 既有行為白名單(不可破壞;優先於新行為)

- 連線正常時自癒兩句字面與節奏不變:`TC4 REALTIME 零推播自癒:%s 靜默 %.0fs → 重掛(attempt %d, window_variant=%d)` /
  `TC4 自癒重掛失敗 %s: %s(下輪退避重試)` —— SXF sparse 判準(next-time:224)、IX0001 13:25 判準(CLAUDE.md §4)、
  `tests/live/test_tc4.py::TestHealResilience` 都 grep 這些字。
- `_heal` 的記帳(attempts / `_heal_next` 退避 base·2^(n-1) 封頂 300 / `HEAL_VARIANT_AFTER` 換窗)在連線中一如既往;
  REQ 例外(連線中 api 壞)仍記帳 + 印「重掛失敗」(TestHealResilience)。
- `_check_stale`:退避 1 → 2 → … → 60 s 封頂節奏、`_stop` 可中斷(`test_check_stale_reconnect_loop_stoppable_when_app_dead`)、
  `TC4 stale >30.0s, reconnecting...` 每發一行、`TC4 reconnect resubscribe %s failed`、`TC4 reconnected (total=%d)`、
  `on_reconnect` 通知全部不變。
- 第 1 發失敗仍是 `logger.exception`(完整 traceback;鐵則 E「不懂的 error 不要吞」)。
- 接回後的自癒從乾淨帳本起算(這是 D1 的結果面,不是新功能)。

## 2. Seam(測試只寫在這裡)

`TC4QuoteSource._heal_tick(now)`(可注入 now + caplog;TestHealResilience 已用)與 `_check_stale()`(monkeypatch
`_ensure_connected`;TestReconnectResubWarning 已用)。本案新增 patch `_stop.wait` 讓退避不真睡 —— 這是新做法,既有測試
用真 thread + `_stop.set()`(review S-8 回校)。

## 3. 不做

- `TC4 stale >30s` 每發一行保留(75 行 / 11 分,是 `_check_stale` 進入判準)。
- engine 層 `history proxy miss` / index `proxy miss` WARNING(各 ~10 行)不動。
- 個股 R3 健檢路徑斷線時零 log(樣本中沒出現),不動。

## 4. 事前標該變(既有斷言;鐵則 E 唯一合法通道)

- `tests/live/test_tc4.py::TestHealResilience::test_heal_thread_survives_failing_requests` 的
  `assert src._heal_attempts.get(HEAL_A, 0) >= 2, "watchdog 未持續重試"`:該案第一發 ZMQError 經 `_req` → `_dispose`
  把 api 清掉,之後每輪都是「quote 未連線」—— 舊斷言要求未連線也持續 +1,正是 D1 拍板拿掉的行為(洪水 + 錯檔位)。
  改為:第一發記帳 1 → 未連線期間停在 1 且 watchdog 活著 → 連線裝回來後恢復 ≥ 2。測試意圖(REQ 例外不得殺 watchdog)不變。

## 5. Review round 1 處置(two-axis,opus)

| # | 嚴重度 | 處置 |
|---|---|---|
| P-1 / S-1 旗標在 heal 窗外接回不復位 | P2 | **修**:連線狀態在兩道早退前先取、看到連線即復位;印仍在 subs 後(S-1 提醒的休市段每 poll 印不會發生)。紅測試 `test_flag_resets_even_when_reconnect_lands_outside_the_heal_window` |
| P-2 同段換例外形狀吃不到 traceback | P3 | **修**:`(type, str)` 與上次印過 traceback 的形狀不同再印一次。紅測試 |
| P-3 關機期間假承諾 | P3 | **修**:`_stop` 已設靜默 return。紅測試 |
| P-4 / S-2 判準第二份字面 | nit / P3 | **修**:`_is_connected` = `_connection()` 的不拋版 |
| S-3 一行版失去內層類別 | P3 | **修**:帶 `(cause <Type>)` |
| S-4 多 source `#n` 交錯難讀 | P3 | **部分**:首發也標 `(#1)`(grep 不必 +1);不加 source 前綴 —— 五條 source 同 port、斷線時 session 為 None,沒有既有身分可用,新增 label 參數超出本案 |
| S-5 sleep 弱測試 | nit | **修**:以 `_is_connected` 呼叫計數等 ≥ 10 輪 |
| S-6 第三份 `_src` builder | nit | **不做**:合併既有兩個測試類的 builder 是無關重構 |
| S-7 行長 / S-8 §2 文件 / P-5 「乾淨帳本」口徑 / 執行緒歸屬註解 | nit | **修**(文字) |
