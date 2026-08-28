# verification — mod/n075-price-type-label-window(2026-08-28)

分支 commit(= PR #134 的 7 筆,`gh pr view 134` 順序;依 08-28 拍板 (b) 引「PR #134 第 n 筆 + subject」,不引 rebase 前 SHA):
第 1 筆 `test(capital): 紅先行 —— 交易日推算保險絲(RuntimeError)不得吞掉晚到結果的 late 審計行…` → 第 2 筆 `fix(capital): 交易日推算保險絲炸掉時價格別標籤退回只記本機日…` →
第 3 筆 `chore(capital/docs): N075 文件改口…` → 第 4 筆 `refactor(tests): review round 1 收修 —— 保險絲替身改名…` → 第 5 筆 `chore(capital/docs): review round 1 收修 —— _Agg.date 欄位宣告…` →
第 6 筆 `chore(docs): next-time 記 08-28 prod 觀察…` → 第 7 筆 artifacts。(原第 3 筆之後一筆重複 characterization 測試依 review Spec F-04 rebase 掉。)

## 1. 自動化 gate(worktree `.worktrees/mod-n075`,借主 tree `.venv`)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| 紅先行 | `pytest tests/capital/test_client.py -k trade_day_fuse`(fix 前,第 1 筆 test 紅先行) | **2 failed**(RuntimeError 直接穿出 `_note_price_type`) | 1 |
| 綠 | 同上(第 2 筆 fix 後) | 2 passed | 0 |
| capital 子集 | `pytest -q tests/capital`(收修後) | 405 passed | 0 |
| 全量(收修前) | `pytest -q -p no:cacheprovider` | 3135 passed, 3 skipped(192 s) | 0 |
| 全量(收修後) | 同上 | **3134 passed, 3 skipped**(187 s;−1 = 撤掉重複測試) | 0 |
| lint | `ruff check copycat tests` | All checks passed | 0 |
| 型別 | `pyright` | 0 errors, 0 warnings | 0 |
| golden | `copycat validate`(主 tree,out/ 在那) | 42/42 PASS | 0 |
| frontend | 未動 `frontend/` → 不跑 | — | — |

## 2. 反向驗證(mutation)

撤掉 `_note_price_type` 的 `try/except RuntimeError`(`trade_date = _trade_ymd()` 直呼)→
`pytest tests/capital/test_client.py -k "trade_day_fuse or price_type"`:**2 failed / 5 passed**,只有兩條新測試紅;
`git checkout -- copycat/capital/client.py` 還原,`grep -c MUTANT` = 0。

## 3. 白名單逐條(change-spec §3)

| # | 既有行為 | 證據 |
|---|---|---|
| 1 | 送單成功記兩個候選日 + 標的 + 方向;拒單 / timeout 不記 | `test_note_price_type_records_trade_date` / `test_broker_reject_does_not_note_price_type` 綠;兩軸 review 核 `if not (...): return` 與原布林式等價 |
| 2 | 晚到結果補記標籤 + late 審計行,順序不變 | `test_late_result_notes_price_type` / `test_timeout_then_late_result_appends_late_line` 綠;`_on_late_result` 零 diff |
| 3 | 改價 → `forget_price_type` | `test_correct_price_forgets_price_type` 綠 |
| 4 | 日曆壞檔 → WEEKEND_ONLY 降級 | `test_broken_calendar_degrades_to_weekend_only` 綠;`_calendar()` 零 diff |
| 5 | store 比對 / prune 規則逐字不變;同檔同方向撞同 seq 仍誤標 | `store.py` diff 全為 docstring / 註解(`git diff master...HEAD -- copycat/capital/store.py` 無程式行);s3 案綠 |
| 6 | 三道下單閘零改動 | `safety.py` / `capital_api.py` / 審計 append-only 零 diff |

## 4. 唯一行為改動

`_trade_ymd()` 拋 RuntimeError → WARNING「價格別標籤只記本機日(seq=…):交易日推算失敗」+ `trade_date=None` → store 記 `(本機日,)`;
late 審計行照寫、送單結果照回。兩條新測試釘住(`test_late_result_audit_survives_trade_day_fuse` /
`test_submit_result_survives_trade_day_fuse`)。

## 5. 真實環境

- 本改動的觸發條件 = 交易日曆資料錯到 60 天內找不到交易日;prod 不可無害地觸發(要改壞 `configs/trading_holidays.json`),
  **不做真環境觸發**。健康路徑逐 bit 不變由 §3 白名單 + 全量測試覆蓋。
- prod 8721 現跑 master `1ce0c500`(00:44 起),不含本分支。08-28 01:xx `curl /api/capital/orders`:08-27 17 筆現股列
  `price_type` 全 null —— 這是**既有**行為(`_price_types` in-memory、重播不重建,store.py 註解明載),與本分支無關,
  作為基線記錄;同一筆 payload 得到 seq 格式觀察(13 位、同日前綴同、不單調)已入 next-time 08-28。
- 白名單真環境過目點(留給 user,prod 重啟含本分支後):下一筆 copycat 送出的市價單,委託列表要帶「市價」標籤(白名單 1);
  沒有 WARNING「價格別標籤只記本機日」出現在 log(健康日曆不該走到降級)。

## 6. 回頭核 goal(08-28 拍板題 1 + review §5 A2)

| 要求 | 落點 |
|---|---|
| 程式不封洞 | store 比對規則零 diff(§3-5) |
| 文件改口:`_Agg.date` = 最新事件日 | `store.py:82` 欄位註解、`note_price_type` / `_price_type_of` / `_today_net_lots_locked` docstring、`client.py::_trade_ymd` / `_note_price_type` docstring、`test_client.py::_dated` / `test_store.py` 兩條 docstring |
| 窗未封 + 期貨路徑更寬 + 關窗條件句 | `store.note_price_type` docstring;s3 案 docstring;review §5 A2;next-time 08-28 |
| 保險絲不吞審計行(§2.4 Spec 7) | 第 2 筆 fix + 兩條測試 + mutation |
| review §5 A2 / A3 / A5 / A7 / C 類回填 | `2026-08-25-do-batch-review.md` §5 |
| N099 spec 改「維持鎖」 | `2026-08-24-do-batch-rounds.md` N099 `[x]` |
| 夜盤實驗 user 親做 | next-time 08-28 第一條(含 seq 口徑一起核) |

## 7. 留給 user

- 過目:§5 兩個過目點(prod 重啟後)。
- 親做:夜盤遠價市價單實驗(next-time 08-28);下一交易日比對 seq 前 6 位有沒有變。
