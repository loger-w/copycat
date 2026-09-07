# pr-202 review 收修(`fix/pr-202-review-followups`)— verification

分支自 master `e75837da` 切出(worktree)。spec = `docs/superpowers/specs/pr-202-review.md` 五條(user 09-08:「那五條 review 結果直接做掉」,含 REFUTED 的 F-05 兩讀合一重構)。

## 1. commits(round-1 後 soft reset 重切,三類分開;std F-08)

| sha | 類 | 內容 |
|---|---|---|
| `3aef9ca5` | test(frontend) | F-03 紅先行:A 在途 → 關窗再開送 B → A settle 不放掉 B 的守門;`renderReopenable()` 收三處重開骨架(std F-07) |
| `2ef59347` | test(server) | `build_period(...).pre_final` 四態(注入時鐘推過 TTL,`_make_mutable_clock`;std F-02 / F-03) |
| `8e3f6f33` | 🔴 fix(frontend) | F-03 `addInFlight` 改送出序號 + keyed 解除(spec S-01 / std F-06);F-04 守門與註解順序 |
| `d6939d87` | 🔵 refactor(server) | F-05 `PeriodBars(bars, tag, pre_final)`、`_period_pre_final` 唯一算式(含空態,S-03)、刪 `period_bars_pre_final`、overlay `.bars`(S-05)、docstring / 註解(S-04 / std F-01);零行為 |
| `82b1cbf7` | chore | F-01 next-time 留尾(前提改寫,S-02 / std F-05);F-02 `extend-select` |
| `e5404e04` | chore(docs) | pr-202 review 報告雙檔入 docs |

## 2. 紅 → 綠 / 突變體(scratchpad `mutcheck3.py`,套用 → 跑 → 還原 → 清 pyc;全 KILLED)

| 突變體 | 紅的測試 |
|---|---|
| F-05 `_period_pre_final` 恆 False | `TestIsPartialLast` + `TestPartialLast`(2 failed) |
| F-05 墊背路徑硬寫 `pre_final=False` | 同上(2 failed) |
| F-03 onSettled 無條件歸零 | 「A 在途 → 關窗再開送 B …」1 failed |

## 3. 完成前 gate(round-1 收修後全套重跑,worktree `e5404e04`)

| 指令 | 結果 | exit |
|---|---|---|
| `… -m pytest -q`(先清 `__pycache__`) | 3531 passed, 3 skipped(225 s) | 0 |
| `… -m ruff check copycat tests` | All checks passed(`extend-select` 後 enabled 集合與 `--isolated --select E4,E7,E9,F,PLE1205,PLE1206` 逐字相同,spec 軸實測) | 0 |
| `… -m pyright` | 0 errors, 0 warnings, 0 informations | 0 |
| `… -m copycat validate --run-five … --run-four …` | 42/42 PASS | 0 |
| `npx vitest run` | 154 files / 3022 tests passed | 0 |
| `npx tsc -b` / `npx eslint src` | 0 / 0 | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | 只有 master 基準既有的 `WatchlistManagerDialog.tsx:42` 複雜度一條 | 0 |

ruff format:`app.py` 的 would-reformat 為 merge-base 既有四個舊 hunk(pr-202 verification 已記),觸及檔 `bars.py` / `test_bars.py` 已 format。

## 4. two-axis round-1(`code-review-round-1.json`):標準軸 8 條全修、spec 軸 5 條全修,零否決。

## 5. 真實環境

runtime 行為改動只有 F-03 的守門 key(閃回情境:PUT 在途中關窗再開、再送不同組名 → 第三發不會排進佇列);其餘零行為 / 文件 / 設定。
prod 未重啟(仍在 #201 之前的版本);下次重啟前主樹 `cd frontend && npm run build`。UI 判準沿 pr-202 verification §5,不新增。
