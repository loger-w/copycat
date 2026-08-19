# verification(/mod txo-snapshot-no-redundant-push)— 2026-08-19

## Baseline(master 5036abdc,改動前)
- `pytest -q`:2755 passed / 1 failed(`test_index_routes::TestIndexState::test_ws_streams_index_payload` timing flake);
  另一次 -x 跑 `test_ws_disconnect::TestAbruptDisconnect::test_no_write_to_dead_transport` 紅、單跑綠 — 兩者皆 master 既有 flake(memory 已載)。

## 自動化 gate(HEAD 0af45d67)
| gate | 指令 | 結果 | exit |
|---|---|---|---|
| pytest | `.venv\Scripts\python -m pytest -q` | **2765 passed**, 1 warning, 148.4 s(含 10 支新測試;ws_disconnect / index_routes 本輪兩次全套皆綠) | 0 |
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed | 0 |
| pyright | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| validate | `.venv\Scripts\python -m copycat validate` | 42/42 PASS | 0 |
| tag 機驗 | `python ~/.claude/hooks/check_feat_tags.py` | flow=mod commits=8 PASS | 0 |
- frontend 未動 → npm 系 gate 不適用。

## 紅→綠實證(implementer 回報)
- SC-3 `[red]` c0eaf8b6:`1 failed`(`wait_for(task_a2, 1.0)` TimeoutError = A 卡在被 clear 的 Event)→ `[green]` c454aa94 74 passed。
- SC-1/2/3b `[red]` bd786fc5:5 新測紅(route None / 無 seed TypeError / 重複推)→ `[green]` d1c7901b 79 passed。
- C1:`test_snapshots_handover_in_place_key_change_pushes` 淺複本時 TimeoutError → dict 複本後綠。
- T1 mutation:`last = self._version` 移到比對之後 → 兩測 0.74 s `RuntimeError: snapshots() tight loop`(紅,非 hang);Edit 還原後綠。

## 真實環境
| SC | 結果 | 證據 |
|---|---|---|
| SC-4 before(prod b6d06f04,15:32 夜盤初,TXO 無新成交) | 19 msgs / 20 s、8.96 KB/s、連續 13 則相同 | `evidence/SC-4-before-prod-b6d06f04-1532.txt` |
| SC-4 on new code(`python -m copycat.server --verify`,fake TXO source、port 8722、git_sha 0af45d67) | (1) 首則 series_id=TXO.202608 ✓ (2) **1 msg / 20 s** ✓ (3) WS 仍 OPEN ✓ (4) GET == 首則 ✓ | `evidence/SC-4-verify-server-fake-source-0af45d67.txt` |
| SC-4 on prod(真 TC4) | **待 prod 重啟**載新碼後以 `evidence/sc4_measure.py 8721` 量(盤中不起第二台連 TC4 的後端 — ops-discipline) | — |
| SC-5 footer「更新 HH:MM:SS」不逐秒跳 | **待 prod 重啟 + user 過目**(兩張間隔 10 s 截圖含 footer 整列) | — |
| 白名單 W1–W9 | correctness lens 逐條 probe 全 ok;W8 單跑綠 | code-review-round-1.json |
| 未改功能抽樣 | `/api/txo/snapshot` GET(verify server 200、shape 不變)、`/api/health` | 本檔 |
- migration:無(route 回傳型別加法、payload shape 不變),可逆性 N/A。
