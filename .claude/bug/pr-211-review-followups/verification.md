# pr-211 review 收修(`fix/pr-211-review-followups`)— verification

分支自 master `ded1f93b` 切出(worktree)。spec = `docs/superpowers/specs/pr-211-review.md` 18 條:
F-01–F-14 修(含兩條 `ask-user`,user 2026-09-08 本 session 拍板 —— F-02 (a) fail-fast、F-04 prior 由呼叫端傳入)、
F-15–F-18 參考用不動。另兩條 handoff 順手核到的文件項(`breadth_fetch.py` 402 分家 / `_REQ_GAP_SECS` doc)併 chore(docs)。

## 1. commits(round-1 後 soft reset 重切,三類分開;std F-06)

| sha | 類 | 內容 |
|---|---|---|
| `35030896` | test(server) | 紅先行六條:F-02 (a) 三道閘在任何 EOD 取數前擋下(空集合 / 相對閘 + 健康對照組)、F-04 `compute()` 不吃 server 前值、F-05 閘不自印 + 放棄路徑 / 10 分鐘重試路徑各只一行 WARNING(S-04)、F-07 `screen --date` 非交易日 exit 2;§6 判準整句 caplog 釘住(S-03);`_write_prior` module 級 / `_gate_engine(now_fn=)` / `TestScreenCommand` / 檔頭口徑(std F-03 / F-04 / F-05 / F-10) |
| `7b69c319` | 🔴 fix(server) | F-02 (a) 當沖名單三道閘搬到 21 次 EOD 之前 / F-04·F-06 `prior` 呼叫端傳入、`_run_once` 只讀一次 / F-05 閘內 `logger.warning` 刪、刪鍵提示併進 exception / F-07 CLI 取數前 `is_trading_day` 擋 / `_RETRY_UNTIL`、`_REQ_GAP_SECS` 註解改事實;round-1 std F-08 / F-09 / F-11、S-05 記帳 |
| `1a863f37` | 🔴 fix(frontend) | F-11 `useMarketBars` / `useBreadthRows` / `useFuturesBars` 各取一次 `now`(理由一份在 `lib/trading-hours.ts::offHoursInterval` doc,std F-02;界值校正 08:40 / 14:55,std F-01 / S-01)/ F-12 「退訂語意」註解改口 |
| `9db0f0f4` | chore(docs) | F-01 / F-03 / F-07 docstring / F-08 / F-09(數字 + S-02 校正 + 三處括號)/ F-10 / F-13 / F-14 / breadth_fetch doc;review 雙檔入 `docs/superpowers/specs/`;std F-02 / F-07 🔵 候選入 next-time |

## 2. 紅 → 綠 / 反向驗證 / 突變體

- 紅先行:第一版測試 commit(`227fc599`,重切前)當下 `pytest tests/server/test_screen_engine.py tests/test_cli.py` → **6 failed, 25 passed**,六條各紅在自己的行為上。
- 反向驗證:`git revert --no-commit <fix(server)>` → 同組 **6 failed, 25 passed**(六條全紅回來)→ `git revert --abort` → 綠。
- 突變體(scratchpad `mutcheck.py`,套用 → 跑 → 還原 → 還原後綠 31 passed):

| 突變體 | 紅的測試 |
|---|---|
| A F-04 `compute()` 改傳 `self._cached_daytrade_rows()` | `test_compute_cli_preview_ignores_server_prior`(1 failed) |
| B F-02 閘前多插一發 EOD fetch(= 閘回到 EOD 之後的形狀) | `TestDayTradeFailFast` 三條 + `test_non_trading_day_morning…`(4 failed) |
| C F-05 閘內加回 `logger.warning` | `test_below_80_percent…` + `test_gate_failure_is_logged_exactly_once…`(2 failed) |

## 3. 完成前 gate(round-1 收修 + 重切後全套重跑,worktree `9db0f0f4`)

| 指令 | 結果 | exit |
|---|---|---|
| `C:/side-project/copycat/.venv/Scripts/python -m pytest -q`(worktree 全量) | 3555 passed, 3 skipped, 2 warnings(213.29 s) | 0 |
| `… -m ruff check copycat tests` | All checks passed | 0 |
| `… -m pyright` | 0 errors, 0 warnings, 0 informations | 0 |
| `… -m copycat validate --run-five <主樹 out/five_tigers> --run-four <主樹 out/four_tigers>` | 42/42 PASS(重切前跑;重切後 replay / validate 相關檔零改動) | 0 |
| `npx vitest run`(worktree frontend,`npm ci` 後) | 154 files passed(第一輪 3046 tests;重切後前端只動註解 / doc,集合不變) | 0 |
| `npx tsc -b` / `npx eslint src` | 0 / 0 | 0 |
| `npx react-doctor@latest --scope changed --base ded1f93b --no-telemetry` | No issues found | 0 |

ruff format:自己新增的 hunk 全部手修;`cli.py` fade 段與 `screen_engine.py` 兩個 would-reformat 為 merge-base 既有舊 hunk,
不整檔重排(handoff §4 紀律)。

判準字面對得上:W2 verification §6 的「當沖名單 n 列(前值 無(用絕對下限))」由 `test_no_prior_uses_absolute_floor_1000`
以 caplog 釘住整句(原始碼裡沒有連續字面,格式字串 + `_prior_text` 兩段組出來 —— `grep "前值 無"` 只會命中註解,不是 parity;
two-axis S-03 校正)。

## 4. two-axis round-1(`code-review-round-1.json`)

標準軸 11 條:修 9、修一半 1(F-02 理由收成一份,helper 抽取入 next-time)、知情不修 1(F-07 入 next-time);spec 軸 5 條:修 3、
note 2 各修其可修半邊(S-04 補重試路徑測試、S-05 記帳)。零否決。

## 5. 真實環境

- CLI(worktree code,`copycat.__file__` 指向 worktree):`python -m copycat screen --date 2026-09-05`(週六)→
  stderr「盤前篩選:2026-09-05 是非交易日,--date 須為目標交易日(名單服務的交易日)」、exit 2、零網路請求。
- runtime 行為改動四處:(1) 盤前篩選失敗路徑順序 —— 下一交易日 08:00 若 FinMind 當沖名單未出齊,log 每 10 分鐘那行
  WARNING「第 n 次取數失敗:盤前篩選 <日> 當沖名單 …;HH:MM:SS 再試」**只一行**(不再先出閘內那行),且該次 attempt 不會先抓
  21 個 EOD(可由 attempt 間隔接近整 600 s 觀察;成功路徑不變);(2) 手動 `screen --date <過去交易日>` 不再被 server 前值擋;
  (3) `screen --date <週末>` 印「非交易日」exit 2(上列已實跑);(4) 前端三支輪詢 hook 跨開點那一毫秒的兩把鐘(不可觀測,
  姿態一致化)。其餘零行為 / 文件。
- prod 未重啟(仍在 #211 之前版本);下次重啟前主樹 `cd frontend && npm run build`。W2 §6 判準沿用,只換 F-01 那句字串。
