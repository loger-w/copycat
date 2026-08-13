# Verification — mod/trial-pause-badge(2026-08-13)

## 自動化 gate(harness.json verify 陣列 + CLAUDE.md 前端組 + validate)

| 指令 | exit | 結果 |
|---|---|---|
| `.venv\Scripts\python -m pytest -q`(root) | 0 | **2659 passed**(baseline 2631 + 本輪 28) |
| `.venv\Scripts\python -m ruff check copycat tests` | 0 | All checks passed |
| `.venv\Scripts\python -m pyright` | 0 | 0 errors, 0 warnings |
| `npm test`(frontend/) | 0 | **1797 passed / 112 files**(見下 flake 註記) |
| `npx tsc -b`(frontend/) | 0 | clean |
| `npx eslint src`(frontend/) | 0 | clean |
| `npx react-doctor@latest --scope changed --no-telemetry` | 0 | 無新增 finding |
| `copycat replay` four_tigers / five_tigers | 0 / 0 | 完成 |
| `copycat validate`(golden gate) | 0 | **42/42 PASS** |

**flake 註記**:19:16 的第一次全量 vitest 出現 1 failed / 1796 passed(輸出截尾未留測試名,
疑既有 ws_disconnect flake 家族 — memory 已有「重現率升高待排查」記錄);緊接兩次全量
重跑(其一乾淨無管線、exit code 直讀)均 **1797/1797 exit 0**。判定 flake 非本輪迴歸。

## 真實環境節(側車 fake server,port 8899;證據 `evidence/SC-3_http-snapshot-trial.txt`)

- happy:`GET /api/stock/state/2330`(19:22 窗外)→ `trial` 鍵存在、值 `false`、
  `no_data=false`、`seq=11`(回補 + live 推播均活)。
- edge1:`GET /api/stock/group-state?codes=2330` → **不含** `trial`(白名單 6:
  group_snapshot 形狀零改動)。
- edge2:`GET /api/stock/state/ZZZZZZ99` → HTTP 400 `{"detail":{"error":"BAD_CODE"}}`
  (error contract 未變)。
- regression ×2:`/api/health`(200,git_sha=94382944)、`/api/stock/watchlist`
  (v3 形狀正常)。
- `trial=true` 態:窗外無法以真時鐘產生 → 依 spec SC-1 amendment R11 以 pytest 假時鐘
  證據結案(`test_quote_payload_trial_in_window` 等 + flush 翻轉六案);盤中截圖列
  memory 待辦(次一交易日 08:30–09:00 窗)。
- 官方 `--verify` server(8722):`/api/health` 正常;`/api/stock/*` 為 NOT_READY —
  **設計如此**(verify 模式不啟 stock engine,XR-3/R4 既知),非本輪迴歸;故 stock
  HTTP 證據走側車。

## 白名單逐條(spec §3,對照 lens A 全項核對 + gate)

1. ingest/apply_backfill 試撮丟棄 — 三檔零改動(git diff --stat 證實)✓
2. watchlist_quote 既有欄位語意 — builder 既有段一字未動,additive `trial` ✓
3. 1s 節流 — dirty 路徑不動;翻轉補推每日 4 次邊界事件,SC-4 否定側測試鎖 ✓
4. 期貨空窗 + 夜盤早退 — 不動;觀測落點在早退之後(測試鎖)✓
5. parse 層 TradeStatus warning — 原文原位(lens A 核對)✓
6. snapshot additive-only;group_snapshot 零改動 — edge1 實測 + lens A ✓
7. tick/book/status/stkfut 形狀 — 未觸及 ✓
8. 側欄版面/亮燈/拖曳 — 未動,既有 60 測綠 + min-w-0 lock ✓
9. corr/futures caller — 未動 ✓

## 事故記錄(誠實記帳)

側車首版照抄 group-grid 樣板**漏了憑證中和** → 以 .env 真憑證登入群益正式環境一次
(唯讀:回報/餘額查詢;無任何下單路徑觸及,零狀態改變)。已補
`neutralize_external_env()`(auto-verify 2026-08-06 紀律),修正版樣板留
`evidence/fake_server.py` 供後續沿用。教訓沉澱見收尾 8.5。

## Migration 可逆性

無資料格式落盤、無 migration;wire 全 additive → revert 即回,可逆性成立。
