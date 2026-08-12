# XR-3 verification — mod/signal-hub-decouple

日期:2026-08-12。HEAD:4544b0f7(6 commits on master 1adf9ee9)。
spec:change-spec.md;review:code-review-round-1.json(3 lens + fix 波,無未解 P0/P1)。

## 自動化 gate(全部 exit 0)

| 指令 | 結果 |
|---|---|
| `.venv\Scripts\python -m pytest -q` | **2605 passed**(baseline 2595;+4 包 1 淨增、+6 fix 波 lock 測試) |
| `.venv\Scripts\python -m ruff check copycat tests` | All checks passed |
| `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings |
| `copycat replay four_tigers / five_tigers` | 完成(n_events 11048 兩份) |
| `.venv\Scripts\python -m copycat validate` | **42/42 PASS** |

## 真實環境(verify server = TC4-off 場景;port 8722,盤中零 ZMQ 安全)

health 確認跑的是 HEAD:`{"git_sha":"4544b0f7","git_dirty":true(僅 untracked artifact)}`。

| 項 | 證據 | 結果 |
|---|---|---|
| happy:SC-2 today 端點 | `GET /api/stock/signals/today` → **200**,含 2 則 fake 廣度事件(1101 up / 6488 down,trade_date=2026-08-12=牆鐘日)— 廣度鏈端到端(breadth poll → hub → jsonl → today)無 stock engine 下全活 | PASS |
| happy:SC-3 rules | `GET /api/stock/signals/rules` → 200,4 條預設規則 | PASS |
| edge:SC-4 WS 存活 + seed | websockets client 連 `ws://:8722/ws/stock` → 首則 `{"type":"status","tc4":"down","backfilling":null}`,連線未 close(scratchpad ws_smoke.py PASS) | PASS |
| edge:SC-8 落點隔離 | fake 事件僅落 `data/market-verify/signals/20260812.jsonl`(554B)+ `market-verify/signal_rules.json`;prod `data/signal_rules.json`/`stock_watchlist.json` mtime 停 08-06 不變;prod `data/signals/20260812.jsonl` 唯一 `breadth-6488` 命中經內容鑑別為 prod 真實事件(10:23:39/933000/up vs fake 11:09:32/9000/down)— **零汙染** | PASS |
| 未改功能抽 1 | `GET /api/txo/series` → 200 | PASS |
| 未改功能抽 2 | `GET /api/market/breadth` → 200(enabled:true、當日 counts) | PASS |

## 既有測試紅綠對照 spec

- 該紅 4 條:全部按 §5 預告改寫,[red] commit 6abd3e22 有紅證據(8 failed/78 passed)。
- 不該紅:全套 2605 綠,無預告外紅 — SC-5 白名單成立。

## Migration 可逆性

無持久化格式改動(spec §3),回退 = revert commits。N/A 核銷。

## SC 總表(Phase 7 對照用)

| SC | 測試錨點 | real-env 證據 |
|---|---|---|
| SC-1 | test_no_stock_still_builds_hub | health + today 200(hub 在) |
| SC-2 | test_today_carries_market_events(portal 驅動) | today 200 含 2 fake 事件 |
| SC-3 | test_rule_crud_available_without_stock | rules 200 |
| SC-4 | test_ws_stock_stays_open_and_carries_market_events | ws_smoke.py PASS |
| SC-5 | 全套 2605 passed | 未改功能抽查 2/2 |
| SC-6 | test_stock_absent_still_attaches_hub | today 含 breadth 事件(attach 生效的行為證據) |
| SC-7 | test_bad_rules_file_degrades / test_hub_start_failure…(未改寫,綠) | —(測試層足) |
| SC-8 | conftest 自鎖 + test_main_wiring 兩斷言 | 快照對照 + 內容鑑別零汙染 |
