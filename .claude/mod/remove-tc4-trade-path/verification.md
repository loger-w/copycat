# Verification:remove-tc4-trade-path(Phase 6/7/8)

日期:2026-08-04 17:3x。HEAD:b20356f(自評修復後)。

## Phase 6 自動化 gate(主 session 親跑,全在最終樹)

| 指令 | 結果 | exit |
|---|---|---|
| `.venv\Scripts\python -m pytest -q` | **1626 passed**, 1 warning(既有 Starlette deprecation), 66.84s | 0 |
| `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! | 0 |
| `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| `.venv\Scripts\python -m copycat validate` | 42/42 PASS | 0 |
| `npm test`(frontend/) | **72 files / 985 tests passed** | 0 |
| `npx tsc -b`(frontend/) | 零輸出 | 0 |
| `npx eslint src`(frontend/) | 零輸出 | 0 |

數字對賬(spec R9):backend 1664(baseline)− 44(刪 3 檔)+ 1(test_main_wiring)
+ 5(自評補強)= **1626** ✓;frontend 994 − 9 = **985** ✓。

既有測試紅榜對照 Phase 3 spec:唯一該紅 = test_capital_api 503 斷言(已依 spec 合法改
404,[red] commit cccd4a0 有紅證據:2 failed)。不該紅的零紅。
注:`test_ws_disconnect::test_no_write_to_dead_transport` 為既有 timing flake(0.5s 窗,
全套負載下間歇;lens B 雙跑對照 1 failed/1620 → 1621 passed、單檔 6 passed,與本輪零
因果);本輪三次全套跑皆綠。已記 next-time。

## Phase 7 真實環境

- 契約面(404 / capital 錯誤契約)由 HTTP 層測試 + lens B 實證 probe 覆蓋
  (AuditWriteError → `500 {"detail":{"error":"AUDIT_WRITE_FAILED"}}`、
  BrokerRejected → `400` 含 err_code/err_msg,逐字一致)。
- **正式啟動接線不做 real-env 重啟驗證**(spec SC-3 amendment 拍板:夜盤時段不重啟跑著的
  server,CLAUDE.md §8 紀律;跑著的 prod server 是舊 code,本來就不受本改動影響)。
  由 `test_main_wiring.py`(kwargs 整份相等)守著;**下次自然重啟時目視 futures / corr /
  river 三面板有值**(已記 next-time)。

## Phase 8 回頭核

- 目標行為證據:4 條 `/api/trade/*` route 已自 app.py 移除(commit 2fd6691),
  `TestTradeRoutesRemoved` parametrize 四路 404 + `/api/capital/status` 非 404 對照錨
  (commit b20356f);`__main__.py:22-28` 顯式四 sentinel;grep `DEFAULT_TRADE|trade_source`
  production 零命中(僅 test_main_wiring 負向斷言)。
- 白名單逐條:WL-1~WL-6 全 PASS(lens B 逐條打勾 + 證據,見 code-review-round-1.json 的
  `whitelist_check` 陣列 — 增量 review AC-2 後補齊落檔;WL-1 另補自動化探針測試堵缺口)。
- Migration 可逆性:純刪除 + 接線改寫,`git revert` 四 commit 即整段還原;無資料 migration。
- 三類 commit:cccd4a0 🟢[red] / 2fd6691 🔴[green] / 9195e74 🔵 / b20356f 🟢[lock],無混類
  (lens A 逐 commit 核過)。
