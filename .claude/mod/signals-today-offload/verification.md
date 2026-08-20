# Verification(mod/signals-today-offload,2026-08-20)

## 自動化 gate(全 PASS,exit 0)

| Gate | 指令(repo root) | 結果 |
|---|---|---|
| 後端測試 | `.venv\Scripts\python -m pytest -q` | **2792 passed**(baseline 2791 + probe 紅測試;lock 補強後檔內 54/54,全套綠) |
| Lint | `ruff check copycat tests` | PASS |
| 型別 | `pyright` | 0 errors / 0 warnings |
| Replay(four/five) | `copycat replay --watchlist watchlists/{four,five}_tigers.json` | 完成(n_events 11048 兩份) |
| Golden gate | `copycat validate` | **42/42 PASS** |
| Frontend | — | N/A:diff 零 frontend 檔 |

## Mutation 抽驗(lock,已還原)

- route 改 `try/except Exception: return {"signals": []}`(吞例外靜默降級)→
  `test_unexpected_error_propagates_as_502` 紅(1 failed)→ 還原綠。

## SC 逐條

| SC | 結果 | 證據 |
|---|---|---|
| SC-1 讀檔不在 event loop | PASS | `test_reads_jsonl_off_event_loop`(紅先行:改前 `True is False` 紅,改後綠;dict 全等鑑別) |
| SC-2 既有測試不紅 | PASS | 2792/2792 全套(既有 2791 全保留) |

## 白名單逐條(correctness lens 機核 5/5 PASS)

1. 回傳形狀 / 聯集語意 — PASS(hub 零改動)
2. hub 缺席 503 NOT_READY — PASS(`_signals` 在 to_thread 前同步 raise;`test_hub_start_failure_isolates_signals_only` 續綠)
3. legacy `?market=` 忽略 — PASS(簽名未動)
4. 壞行跳過 / errors=replace — PASS(read_signals 未動;交錯窗口放寬已記 spec amendment C-2)
5. hub 同步 API + 動態替換手法 — PASS(bound method 進 thread,實例屬性替換照樣生效,新測試即為實證)

## 真實環境層

阻塞消除為負向效應(不卡),無畫面元素;prod 重啟後 `curl /api/stock/signals/today`
形狀不變即正確(端點契約由 54 條 route 測試鎖)。migration:無 → 可逆性 N/A。
