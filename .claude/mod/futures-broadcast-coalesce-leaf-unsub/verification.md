# verification(/mod futures-broadcast-coalesce-leaf-unsub)— 2026-08-19

## Baseline(master 8798fbab)
futures 相關四檔 140 passed;全套 2765(R1 收尾時)。

## 自動化 gate(HEAD 301fdfcd)
| gate | 結果 | exit |
|---|---|---|
| `pytest -q` | **2781 passed**, 1 warning, 148.2 s(+16 新測;兩支已知 flake 本輪皆綠) | 0 |
| `ruff check copycat tests` | All checks passed | 0 |
| `pyright` | 0 errors | 0 |
| `copycat validate` | 42/42 PASS | 0 |
| `check_feat_tags.py` | flow=mod commits=11 PASS | 0 |
- frontend 未動 → npm gate 不適用。

## 紅→綠實證(implementer 回報)
- SC-0~4 `[red]` 4bfae2d3:`TypeError ... 'flush_interval_secs'`(22 failed)→ `[green]` d9572711 187 passed。
- SC-7 `[red]` 1fb61ad3:`in_txo_session() ... 'pad'` + ImportError + main_wiring 3 failed → `[green]` a8ff852a 190 passed。
- 既有該紅測試:`test_main_wiring::test_futures_heal_gate_ands_the_calendar` 改寫(spec 預告)。
- code review fix 波:cf6ee247(C1/T9 失敗重排,`test_broadcast_exception_does_not_stall_stream` 斷言 [2]→[2,3] 為 review C1 該變)/ 1e81ee61 🔵 docs / 301fdfcd 🟢 測試補強;T1 mutation(刪 close cancel)新測試紅、還原綠。

## 真實環境
| SC | 結果 | 證據 |
|---|---|---|
| SC-8 before(prod b6d06f04,16:25 夜盤) | 312 則/20 s、5.89 KB/s、TMF 116/MXF 102/TXF 94、seq gaps 0;**per-product 最小間隔 0.0 ms**(叢發) | `evidence/SC-8-before-prod-b6d06f04-1625.txt`、`-perproduct.txt` |
| SC-8 降級(sidecar fake source 每 20 ms×3 品叢發,port 8723,HEAD 301fdfcd) | 10 s:189 則(63/品 = 6.3/s vs 注入 50/s)、**per-product 最小間隔 122.7 ms ≥ 95 ms** ✓、seq gaps 0 ✓、GET state seq ≥ WS ✓、shape 不變 ✓、WS OPEN | `evidence/SC-8-sidecar-burst-after-301fdfcd.txt`(另 a8ff852a 時一份) |
| SC-8 prod(真 TC4) | **待 prod 重啟**後 `evidence/sc8_measure.py 8721`(夜盤對夜盤比 before) | — |
| SC-9 UI | 期貨 tab / 閃電梯五檔仍即時跳動 — **待 prod 重啟 user 過目** | — |
| 白名單 W1–W10 | correctness lens 逐條 probe ok;W3/W4 flush 面測試缺口由 T1/T2 補 | code-review-round-1.json |
| 未改功能抽樣 | `/api/futures/state`(sidecar 200、shape 同)、`/api/health` | 本檔 |
- migration:無;`FuturesSource` Protocol 未變(leaf 退訂撤下)。
- 註:branch 內含另一 session 的 docs commit 84472fc1(崩潰根因定位 docs),隨 PR 一併進 master。
