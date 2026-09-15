# diagnosis — 群益回報線斷線後不自動重連(fix/capital-reply-reconnect,2026-09-15)

## 症狀(prod 實錄,`logs/server-20260914-2359.log`)

- 05:50:57 `copycat.capital.com WARNING Capital Solace reply disconnect (user=…, code=3033)`
- 05:50:59 `copycat.capital.client WARNING 群益回報線 IsConnectedByID=0(上一值 1)`
- 同一分鐘:MIS `getaddrinfo failed` 11001 / Discord gateway 斷(05:52:58 自動重連)/ TC4 海外八腿靜默 123 s
  (05:52 自癒重掛)/ 群益 OI 查詢 12007 —— 本機網路中斷約兩分鐘。
- 05:51 → 08:14:30(user 為批 B 重啟):零 `Solace reply connection` 事件、零 `ConnectByID`、探針值停在 0,
  `/api/capital/status` 的 status 仍 `ok`(舊 `OnDisconnect` 沒響、Solace 那對只 log、探針不翻 status)。
- 若無重啟,09:00 首筆成交(6706)的回報收不到:委託列表 / 部位 / 閃電梯成交點全凍。

## Phase 1 — feedback loop

`tests/capital/test_reply_reconnect.py`(CapitalClient + RecordingCom seam,走真 `_init_com` 讓 sink 回呼接到 client):
- 05:50 場景逐字重播:`com.on_reply_disconnect(3033)` → 探針 0 → `_reply_reconnect_next = 0` → `_pump_once()` →
  斷言 COM 新呼叫 == `["connect_reply"]` → 探針 1 → status ok。
- 探針單路(事件不響)、R7(`_ReplayingCom` 在 connect_reply 重播 backlog,斷 fills 仍 1)、失敗退避(rc 3001,
  同一窗只試一次)。

修前:`PYTHONUTF8=1 …/python -m pytest -q tests/capital/test_reply_reconnect.py` → **5 failed**(其中 R7 案補上
「必須真的重連」斷言後才紅;com seam 案後併入 test_com),紅在 `assert [] == ['connect_reply']` —— 正是症狀。
0.08 s、確定性。

## Phase 2 — 重現 + 最小化

重現 = 上節。最小化:事件路 / 探針路各自單獨就能紅(兩條測試),load-bearing 元素 = 「degraded 之後幫浦圈沒有任何
出手 connect_reply 的路徑」。

## Phase 3 — 假說

只有一條可證偽:**code 裡沒有重連路徑**(`client.py` 檔頭第 14 行「不自動重連」、`_handle_reply_disconnect`
docstring、`com.py` Solace 那對註解「只 log;響了再談翻 status / 重連」三處明寫 —— #235 辨識批刻意留白,等第一個
交易日 log 拍板)。預測:加上路徑,loop 綠;revert 路徑,loop 紅。不需排序,直接進 Phase 5。
次要事實(不是假說):舊 `OnConnect` / `OnDisconnect` 22 天零觸發、Solace 那對 09-15 三次開機 + 一次斷線都響
→ 這版 SKCOM 回報線走 Solace 事件,兩對同語意接。

## Phase 4 — 儀器

不需要:log 已把兩個訊號(事件 / 探針)的時序全部留下。

## Phase 5 — fix + regression

- `com.py::_ReplyEvents`:新 `on_connect` 回呼;`OnSolaceReplyDisconnect` / `OnDisconnect` → `on_disconnect`,
  `OnSolaceReplyConnection` / `OnConnect` **code 0** → `on_connect`(≠ 0 只 WARNING)。`CapitalCom.setup` 多
  `on_reply_connect`(Protocol / Skcom / FakeCom / RecordingCom / test_com `_StubCom` 五處同步)。
- `client.py`:`REPLY_RECONNECT_BACKOFF_SECS = (5, 10, 20, 40, 60)`;`_handle_reply_disconnect` 翻 degraded 後
  `_schedule_reply_reconnect`(next 非 inf 不重排);`_probe_reply` 0 且 ok → degraded + 排、1 且 degraded →
  `_reply_recovered`;新 `_handle_reply_connect`(degraded 時才翻 ok);幫浦圈新 `_maybe_reconnect_reply`:
  degraded 且到期 → **`store.clear()` 先於 `connect_reply`**、rc=0 標 balance dirty、下一格退避。
- 既有兩案 pre-marked 該變(spec #232 白名單「不新增自動重連」是辨識批的暫定):`test_reply_watch` 值翻 0 改斷
  degraded + 同一圈零 COM 啟動呼叫;`test_com` Solace 案改斷轉發 + 三行 log。
- 反向驗證:`git revert --no-commit 838a9a19` → test_reply_reconnect **4 failed**;`git revert --abort` →
  23 passed(reconnect / watch / com 三檔)。

## 已知不救 / 留尾

- `IsConnectedByID` 值 2(23:59:56 首值,10 s 後翻 1)當「連線中」不動狀態;若群益某版把「斷」報成 2,探針路救不到,
  事件路仍在。
- 重連只重連回報線(ConnectByID),不重跑登入 / 憑證;若 3033 之後 SKCOM 要求整段重登,`connect_reply` 會持續
  rc≠0 → 每 60 s 一行 WARNING 留在 degraded —— 那是下一個 /bug 的紅燈,不是本批。
- 真環境無法在 worktree 重現網路中斷;判準 = prod 重啟後下一次斷線的 log 四行(verification §3)。
- **rc≠0 那格的 `store.clear()` 是白清**(two-axis Spec S-03):ConnectByID 沒連上就沒有重播來重建,斷線期間委託列表 /
  閃電梯成交點空到某次連上為止。寧空勿雙計,知情接受;要「連不上就別清」得先證明 SKCOM 不會在 ConnectByID 同步回傳
  前就開始 dispatch 重播事件,本批不證。
- `_fill_evt_raw` 在 test_client / test_fill_latency / test_reply_reconnect 三份逐字重複(two-axis S-07):既有債,
  併 next-time F-18 那條 test-hygiene 批收 conftest。

## two-axis review round-1 收修(本分支內)

- S-01 / Spec S-01(hard):探針 0 在 degraded 下也排重連(排程去重)+ `_init_com` ConnectByID rc≠0 立即排。
- S-02:`_schedule_reply_reconnect` 只在 degraded 排。S-03:哨兵改 `float | None`。S-04:`_reconnect_delay` helper +
  退避表 / 逐步到期兩條測試。S-05:恢復清 `last_error`,測試改斷 `is None`。S-06 / Spec S-03:契約措辭補「首次退避到期即清、
  失敗也清、寧空勿雙計」。Spec S-02:`_reply_recovered` 補 `_mark_balance_dirty()`。S-07 / Spec S-04:記帳(上節 + next-time)。
