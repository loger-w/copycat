# next-time W1 批(`mod/next-time-batch-w1`)— verification

分支 `worktree-mod-next-time-batch-w1`(worktree,自 master `556f4972` 切出)。無 spec issue:spec = `docs/next-time.md`
2026-09-07 盤點節的 W1 六條(user 2026-09-07 逐條拍板)+ 對話中的追加要求(新增群組列搬到左欄最上方)。

## 1. commits(test 紅先行 → fix;🔴 / 🟢 / chore 分開)

| sha | 類 | 內容 |
|---|---|---|
| `9ba64bc8` | chore(docs) | next-time 盤點處置(結案 13 條 / W1 / W2 / W3 / 保留) |
| `39445de2` | test | C17 三案 + route 級 / B3 `send_seed` 四案 / B11 prune 兩案 / B15 parity / B2 四案 + 引導文案斷言事前改 |
| `4cd19b4d` | 🔴 fix | C17 `is_partial_last` tf=D 吃 `DAILY_FINAL_TIME` / B3 `ws.send_seed` + 三處 seed 接線 / B2 成功才清 + 新增列置頂 |
| `4778e48f` | chore(lint) | B14 ruff `[tool.ruff.lint] select` + PLE1205 / PLE1206 |
| `1f21a603` | chore(docs) | next-time W1 六條勾銷 + 出貨要點 |
| `e084e6cc` | test(round-1) | S-01 墊背仍未收盤(route + 單元 ×2)/ F-03 在途新字不被吃 / S-02 守門 / S-03 重開清空 / F-05 gate 共用;N115 #1 改釘守門(事前標為該變) |
| `a5cbf559` | 🔴 fix(round-1) | `period_bars_pre_final` + `is_partial_last(pre_final=)` / 成功回呼只清送出的名字 / `addInFlight` + 鈕 disabled / 重開清 groupInput |
| `0aeabb0a` | chore(docs) | F-01 / F-02 / F-04 註解與 docstring |

## 2. 紅 → 綠

- C17:`TestIsPartialLast::test_today_daily_bar_at_final_time_is_not_partial` 先紅(修前日曆日判準恆 True)→ 綠。
- B3:`TestSendSeed` 四案 ImportError 紅 → 實作後綠。
- B2:四案中三案紅(撞名保留 / 4xx 保留 / 第一區塊是新增列;「成功才清」修前即綠)→ 綠;`尚無群組,可在上方新增` 斷言事前標為該變。
- B11 / B15 守門型(釘現行正確行為),紅先行證據改由突變體提供(§4)。
- round-1:S-01 route 案 `test_stale_fallback_after_final_time_stays_partial` 先紅(墊背路徑標 False)→ 綠;F-03 在途新字案先紅
  (無條件清空吃掉「隔日沖」)→ 綠;S-02 守門案先紅(第二發排隊 → 假 BAD_GROUP 文案)→ 綠;S-03 重開案先紅(groupInput 殘留)→ 綠;
  既有 N115 #1 依留尾原文預告改釘守門(事前標為該變),其餘 56 條 dialog 測試不動全綠。

## 3. 完成前 gate(worktree `0aeabb0a`,round-1 收修後全套重跑)

| 指令 | 結果 | exit |
|---|---|---|
| `C:/side-project/copycat/.venv/Scripts/python -m pytest -q`(worktree root,先清 `__pycache__`) | **3531 passed, 3 skipped**(230 s) | 0 |
| `… -m ruff check copycat tests`(含新規則 PLE1205 / PLE1206) | All checks passed | 0 |
| `… -m pyright` | 0 errors, 0 warnings, 0 informations | 0 |
| `… -m copycat validate --run-five C:/side-project/copycat/out/five_tigers --run-four …/four_tigers` | 42/42 PASS | 0 |
| `npx vitest run`(frontend/) | **154 files / 3021 tests passed** | 0 |
| `npx tsc -b`(frontend/) | PASS | 0 |
| `npx eslint src`(frontend/) | PASS | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry`(frontend/) | 1 條 `no-high-complexity-react-function` `WatchlistManagerDialog.tsx:42` —— master `--scope all` 同函式同行已在基準,零新增 | 0 |

ruff format:`tests/server/test_ws_disconnect.py`(910 / 1001 / 1019 行三個舊 hunk)與 `copycat/server/app.py`(389 / 959 / 1053 / 1258 行四個舊 hunk)
的「would reformat」都是 merge-base 版本本來就未 format(`git show <base>:… > tmp && ruff format --check tmp` 同樣 would reformat),新增段落乾淨;
依 backend-conventions 不整檔重排。其餘觸及檔已 format。

**一次 gate 假紅(記帳)**:round-1 前的全量 pytest 曾 2 failed(`test_verify.py` 兩條)—— 根因是 §4 的 B15 突變體(`25_000` → `24_000`,
同長度、同一秒內套用 / 還原)留下 pyc 被 Python 當有效(ops-discipline「同秒 pycache 陷阱」,本來就記著、這次沒先套);
清 `__pycache__` 後單檔 16/16、全量 3528/3528 綠(round-1 前)。突變腳本已改成還原後順手刪該檔 pyc。

## 4. 突變體(scratchpad `mutcheck.py`,逐個套用 → 跑對應測試 → 還原;全部 KILLED)

| 突變體 | 紅的測試 |
|---|---|
| B11 刪 `prune` 的 `_daily_tag` 清理段 | `test_prune_drops_stale_daily_tag` |
| B11 刪 `prune` 的 `_daily_pre_final` 清理段 | `test_prune_drops_stale_pre_final_marker` |
| B15 `_DAILY_PAD_ROWS` 25_000 → 24_000 | `test_daily_pad_rows_parity_with_breadth` |
| C17 tf=D 分支拿掉 `_now_time() < DAILY_FINAL_TIME` | `TestIsPartialLast` 1 + `TestPartialLast` 1(2 failed) |
| B3 `send_seed` 只 catch `WebSocketDisconnect` | `test_close_sent_runtime_error_returns_false_without_warning` |
| round-1 S-01 tf=D 分支拿掉 `pre_final or` | `TestIsPartialLast` 1 + `TestPartialLast::test_stale_fallback…`(2 failed) |
| round-1 S-01 route 硬傳 `pre_final=False` | `test_stale_fallback_after_final_time_stays_partial` |
| round-1 S-01 helper 讀錯鍵(無 `\|L`) | 單元 `test_period_bars_pre_final…` + route 案(2 failed) |

## 5. 真實環境

盤後(2026-09-07 晚)prod 關著;本批不動 TC4 / 群益路徑。
- **UI 驗收點(user 過目)**:自選側欄「管理」→ 視窗左欄**第一個區塊**就是「群組名稱」輸入框 + 「新增」鈕,群組清單在它下方捲動;
  輸入既有組名按 Enter → 上方紅字「群組名稱不合法」、輸入框文字**還在**;輸入新名按 Enter → 「新增」鈕短暫變淡(在途)、
  群組出現、輸入框清空;關窗再開輸入框是空的。
- **C17 判準(review S-04 校正措辭)**:交易日 **14:00 後重新載入**台股綜合 tab 日 K,標題不再帶「· 最後一根未收盤」;14:00 前照舊有。
  常開不重整的頁面那份 body 到午夜才換,不用它驗。TC4 盤後關著時(墊背路徑)標題**仍應**帶「未收盤」(S-01)。
- **B3 判準**:`grep -c "once a close message has been sent" logs/server-*.log` 與 `grep -c "after sending 'websocket.close'"`
  在 corr / river / txo-pnl 握手時應為 0(修前偶發於瀏覽器 F5 瞬間)。
- 未改功能抽驗(user 過目):改名群組撞名仍保留編輯框;刪除群組照舊。

## 6. 回頭核 goal(W1 六條)

| 條 | 實作位置 | 測試 |
|---|---|---|
| C17 | `bars.py::is_partial_last` | `TestIsPartialLast` ×3、`TestPartialLast::test_today_daily_bar_after_final_time_is_not_partial` |
| B3 | `ws.py::send_seed`、`app.py` 三處 | `TestSendSeed` ×4 |
| B2 | `WatchlistManagerDialog.tsx::submitAddGroup` + 左欄 JSX | dialog 新 describe ×4 + 引導文案案 |
| B11 | (測試)`test_bars.py::TestPhase5Hardening` | 兩案 + 突變體 |
| B14 | `pyproject.toml` | ruff check 全綠(存量 0) |
| B15 | (測試)`test_verify.py` | `test_daily_pad_rows_parity_with_breadth` + 突變體 |

留尾:B3 原留尾寫「四處」,實際 seed send 只有三處(stock 的 seed 走 `stream(seed=)` 在 relay 內),已在 next-time 註記。
