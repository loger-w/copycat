# verification — fix/futures-resub-recovery

## 自動化 gate(2026-08-12)

| step | command | 結果 | exit |
|---|---|---|---|
| 測試 | `.venv\Scripts\python -m pytest -q` | **2595 passed**(baseline 2580,+15;review fix 波後終值)| 0 |
| Lint | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! | 0 |
| 型別 | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| Golden gate | `.venv\Scripts\python -m copycat validate` | 42/42 PASS | 0 |

tag 機驗:`check_feat_tags.py` flow=bug commits=12 → PASS。

frontend 未動 → 不跑 npm test / tsc / eslint / react-doctor。

## 真實環境節

修復標的是「TC4 故障/重連下的復原路徑」,真實觸發需 TC4 斷線 — 不可主動製造
(prod 紀律)。依 /bug 特有項「重走重現步驟」:本輪重現 loop 即 fake-source 紅測試
(repro.md 表),全數綠;真環境判準沿用 grep 字串,下次真實斷線時驗:
- `futures subscribe %s failed` → `futures %s subscribe retry ok`(首輪失敗自癒)
- `TC4 reconnect resubscribe %s failed`(重連掉訂,新增)→ 10s 內對帳重掛
- `futures 訂閱重試輪失敗(續行)`(壞電文不再殺迴圈,新增)

Regression 抽樣(未改功能):
- `tests/server/test_stock_engine.py` + `test_corr_engine.py` + `test_index_engine.py`
  (共用 tc4.py 的三姊妹引擎)— 全量 suite 內全綠(2588 含)。
- `tests/live/test_tc4.py` 既有 28 條(_check_stale/重連/backfill)全綠。

## Code review(收尾 C 節,round 1)

見 `code-review-round-1.json`(2 lens:concurrency-correctness / test-efficacy,
opus dispatch)。處置記錄同檔 `_disposition`。

## 反向驗證

(見 repro.md 反向驗證節)
