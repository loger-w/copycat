# refactor/w3-b2-test-scaffolds — verification

分支 base = master `bebdcd3d`;worktree `.claude/worktrees/w3-b2-test-scaffolds`,後端用主樹 venv 絕對路徑、前端 `npm ci`。
純測試改動(runtime 零觸碰;`git diff bebdcd3d --stat -- copycat/` 為空),真實環境節 = 「改動範圍行為跟 refactor 前完全一樣」以測試名 / 斷言零改動 + 突變體對照證明。

## 1. Baseline(改動前,同 worktree)

| 指令 | 結果 |
|---|---|
| `python -m pytest -q -p no:cacheprovider` | 3562 passed, 3 skipped, 2 warnings(257 s) |
| `npx vitest run` | 3065 passed / **4 failed**(156 檔,`StockChart.test.tsx` 四條「無 K 線資料」timeout 5 s;主樹 master 同檔單跑同紅 4 條,見 §5) |

## 2. 自動化 gate(改動後)

| 指令 | exit | 結果 |
|---|---|---|
| `python -m pytest -q -p no:cacheprovider`(全量) | 0 | 3562 passed, 3 skipped, **1 warning**(249 s;baseline 2 warnings → 1,剩 Starlette httpx deprecation) |
| `python -m ruff check copycat tests` | 0 | All checks passed |
| `python -m pyright`(全量) | 0 | 0 errors, 0 warnings, 0 informations |
| `python -m copycat validate --run-five <主樹 out/five_tigers> --run-four <主樹 out/four_tigers>` | 0 | 42/42 PASS |
| `npx vitest run`(全量) | 0 | 3065 passed / 4 failed(與 baseline **同四條**,同檔同名;三支目標檔 74/74) |
| `npx tsc -b` | 0 | 無輸出 |
| `npx eslint src` | 0 | 無輸出 |
| `npx react-doctor@latest --scope changed --no-telemetry` | 0 | No issues found |

## 2b. two-axis round-1 收修後全量重跑(HEAD = f9ef069c;收修 commit bd959f64)

| 指令 | exit | 結果 |
|---|---|---|
| `python -m pytest -q -p no:cacheprovider`(全量) | 0 | **3565 passed**, 3 skipped, 1 warning(246 s;3562 + 守門自檢 3 條) |
| touched-file 子集(`tests/test_conftest_guards.py` + `TestWsBroadcasterBackpressure` + `tests/live/test_stock_source.py`) | 0 | 90 passed |
| `python -m ruff check copycat tests` | 0 | All checks passed |
| `python -m pyright`(全量) | 0 | 0 errors, 0 warnings |
| `npx vitest run`(全量) | 0 | 3065 passed / 4 failed(仍是 §5 那四條;三支目標檔 74/74) |
| `npx tsc -b` / `npx eslint src` / `npx react-doctor@latest --scope changed --no-telemetry` | 0 / 0 / 0 | 無輸出 / 無輸出 / Scanned 4 files, No issues found |
| 前端突變體重跑(`DAILY_FINAL_TIME` 14 → 15) | — | 仍 **3 failed / 71 passed**,還原後 `git status` 乾淨 |
| 守門生效自檢 `tests/test_conftest_guards.py` | 0 | 3 passed(正向 / 負向 / tc4.py 字面 parity) |

## 3. 行為不變 / 測試強度證據

- **前端三檔測試名與斷言零改動**:`git diff bebdcd3d -- frontend/src/hooks/*.test.ts*` 只動 import、stub 內部取料、`D_FINAL` → `D_FINAL_SNAPSHOT` 字面;三檔 74/74 綠。
- **前端突變體**(`scratchpad/mutant_fe.py`,讀進記憶體 → 寫回還原):`lib/day-bars-rollover.ts::DAILY_FINAL_TIME` `[14, 0]` → `[15, 0]`
  → 三檔各紅一條(「跨過 14:00 定稿界 → 14:01 重抓」×3),**3 failed / 71 passed**;還原後 `git status` 乾淨。
  fixture 化後三檔仍各自守住 14:00 界(不是抽成 fixture 後靠同一份料把界抽空)。
- **後端 backpressure 八條斷言零改動**:只換「誰開 stream / 誰 aclose」;該 class 8/8 綠。
- **後端突變體**:`copycat/server/ws.py::_settle_drop_window` 的 `> 1` → `> 0`(pr-188 F-04 明寫的目標突變體)
  → `test_single_drop_window_settles_without_second_warning` 紅,**1 failed / 7 passed**(`scratchpad/mutant_be.py`,還原 + 清 `__pycache__`,`git status` 乾淨)。
  fixture 化後那條仍是唯一守住 `> 1` 的測試(與 pr-188 F-04 記錄一致)。
- **conftest 守門紅先行**(改 test_stock_source 前先跑 `tests/live`):

  ```
  AssertionError: TC4 背景執行緒活過測試(漏 close() / _stop.set()):['Thread-2 (_listen_loop)', 'Thread-3 (_heal_loop)']
  ERROR tests/live/test_stock_source.py::TestSubscribe::test_subscribe_starts_listener_when_sub_port_known
  687 passed, 2 skipped, 1 error in 14.66s
  ```

  唯一洩漏源(listener + healer 兩條);補 `_stop.set()` + join 後 `tests/live/test_stock_source.py` 79/79、全量見 §2。

## 4. 動機核對(refactor why gate → 可量化)

| 動機 | 改前 | 改後 |
|---|---|---|
| 日 K 跨日鷹架逐字份數 | 3 檔各一份(常數 + 判定 + 計數器 + rerenderBurst ≈ 40 行 ×3) | fixture 一份;三檔 −118 / +62 行(`git diff --stat` 5aa1c08c) |
| backpressure 骨架 | 8 份 `try/finally aclose` + 5 份 caplog 過濾 | fixture 一份 + helper 一支 |
| `_listen_loop` 活過測試 | 靠人記得 close;pr-160 review 實證洩漏、`test_ws_disconnect.py:1058` 收窄斷言 | root conftest 每條測試後守門,洩漏 = 該測試紅並點名 |

## 5. 已知不在本批(baseline 同紅)

`frontend/src/components/stock/StockChart.test.tsx` 四條(SC-7「取到空 bars 仍顯示無 K 線資料」+ N-7 三條)在主樹 master `bebdcd3d`
單跑同紅(4 failed / 28 passed),與本分支無關;症狀 = 日 K 模式空 bars 時等不到「無 K 線資料」文案(5 s timeout)。
本次跑在交易日盤中(09-09 11:49 / 12:xx),疑與 #214 即時末根「牆鐘同日 09:00 起 + 交易日」閘有關(空 bars 仍併進 accum 末根?),
未診斷;記 next-time 另開 `/bug`。
