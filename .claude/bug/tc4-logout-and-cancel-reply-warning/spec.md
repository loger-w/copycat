# /bug tc4-logout-and-cancel-reply-warning — spec(originating bug description)

兩個根因已知的行為缺陷,同分支、分 commit 修。

## A. 收工時 server 對達錢 4(TC4)只退訂不送 LOGOUT

- 症狀(2026-08-25 17:15:29 Ctrl+C 實證):`copycat/live/tc4.py::close()` 對 TC4 送 708 筆 UNSUBQUOTE 貼秒,
  但五個 session 的 `RemoveLoginInfo` 全在 17:16:31 由 TC4 端 `ExecuteCheckPingTime` reap(62 s 後)。
- 根因:`close()` 只呼叫 wrapper `tcoreapi_mq.Disconnect()`(只關 KeepAlive 執行緒 + socket),
  送 LOGOUT 電文的是 wrapper `Logout(sessionKey)`,全 repo 零呼叫。
- 要求:
  1. `close()` 在 UNSUB 全部之後、Disconnect 之前,對 TC4 送 `{"Request":"LOGOUT","SessionKey":<session>}`。
  2. TC4 回 `{"Reply":"LOGOUT","Success":"OK"}`(2026-08-26 00:56 零訂閱 probe 實證)→ 走既有 `_req`(send+recv、
     lock timeout、失敗棄連線)不直呼 wrapper(既有紀律:wrapper 方法 blocking acquire 無 timeout)。
  3. best-effort:LOGOUT 失敗(ConnectionError / Success≠OK)只 log,後續 `_dispose` 照走;`_api` 已被 dispose
     (UNSUB 失敗路徑)時不得為了 LOGOUT 重建連線。
  4. 三個子類 source(stock/futures/corr)沿繼承路徑一併生效;`stock_source.close()` 呼叫 `super().close()` 不變。
  5. 既有行為白名單:UNSUB 迴圈、失敗即 break、`_dispose` 的 lock-timeout 分支,逐字不動。
- 驗證 seam:`tests/live/test_tc4.py::TestCloseLogout`(FakeApi 記錄全 REQ 序)。真環境:下次 prod Ctrl+C 後
  `grep RemoveLoginInfo QuoteZMQService-*.log` 時戳貼著 Ctrl+C。

## B. `capital/client.py::_handle_reply` 對刪單回報誤印「預約單?」WARNING

- 症狀:2026-08-25 16 筆 `Capital reply: KeyNo=… 尾欄序號=… 不同(預約單?)` 全是盤中單的刪單回報(Type=C),零筆預約單。
- 根因:條件 `alt_seq_no != seq_no` 不看回報類型;刪單回報的 idx47 尾欄是刪單自己的序號、idx0 KeyNo 是原委託,必定不同。
- 要求:
  1. `status_raw == "C"` 的回報不印該 WARNING。
  2. 其他類型(N 委託等)KeyNo≠尾欄 的 WARNING 照舊(預約單線索保留)。
  3. 回報本身照常入 store / 推 WS / 成交排程重查 —— 只動 log 條件。
- 驗證 seam:`tests/capital/test_client.py::test_cancel_reply_tail_seq_differs_is_not_flagged_as_preorder` +
  白名單 `test_preorder_new_reply_tail_seq_differs_still_warns`。

## 非目標

- 不改 wrapper `spikes/TCPY/tcoreapi_mq.py`(gitignored 官方檔)。
- 不改 `run.ps1` graceful 15 s 判準。
- 不處理 next-time 08-26 節的加權分鐘 / 期貨 K 棒量測兩條。
