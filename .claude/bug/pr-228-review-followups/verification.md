# fix/pr-228-review-followups — verification(pr-review #228 收修;報告 `docs/superpowers/specs/pr-228-review.md`)

寫於 2026-09-14(worktree `.claude/worktrees/fix-pr-228-review-followups`,merge-base `e60024cd`;handoff
`%TEMP%\copycat-handoff-2026-09-14-pr228-review-fixes.md`)。

user 拍板:F-09(`_fmt_secs` 上移)/ F-10(bool 守門兩半各一案)「兩個都做」;其餘 9 條 auto-fix、F-12 不動。

## 1. 紅先行 / 突變體(每顆套上 → 只跑目標測試 → 版控還原)

| finding | 突變體 | 結果 |
|---|---|---|
| F-02 | 現行 runtime(尾根收盤 = 0)對新案 `test_zero_last_close_is_bad_data_warning_not_below_threshold` | **紅**(INFO「前 5 日累計 -100.00%」,期望 WARNING)→ 41ffb98a 後綠 |
| F-04 | `reset_day` 不清 `_big_hits` | KILLED(1 failed) |
| F-05 | `_BREAKOUT_MIN_MINUTES` = 3 / = 5 | KILLED / KILLED(各紅一案) |
| F-06 | 後端 fallback 三元反轉 / 前端 `signal-model.ts` 同反轉 | KILLED / KILLED(vitest 1 failed, 53 passed) |
| F-07 | `_BIG_LOT_MEDIAN_TICKS` = 299 / = 301 | KILLED / KILLED |
| F-08 | INFO 需求根數少 1 | KILLED |
| F-10 | `_emit_policies` 拿掉 `not isinstance(bool)` / `format_policy_group_text` 同 | KILLED / KILLED |
| F-11 | v4→v5 `skip_note` 清空 | KILLED |

11/11 KILLED;還原後 runtime 零差異(autocrlf 行尾差以 checkout 抹平)。Spec 軸 sub-agent 獨立重跑同一組突變體,結論相同。

## 2. Two-axis review → `code-review-round-1.json`(本目錄)

Standards 1 硬違反(S-01 CLAUDE.md §4「CDP 列閘」條沒跟 41ffb98a 同步)+ 5 判斷題;Spec 零缺漏、F-12 未動、
1 條 LOW(P-01 F-08 斷言丟了「日 K」)。S-01 / S-02 / S-03 / S-04 / P-01 收修於 b94def4a(test)+ 94bded56(docs);
S-05 / S-06 不動;scope creep 三件判 in-intent / 知情接受(`_card_head` 抽取混進 test commit)。

## 3. 最終輪(HEAD = 94bded56 + 本 artifacts commit;worktree 無 .venv,用主樹 venv)

| 指令 | 結果 | exit |
|---|---|---|
| `pytest -q`(全量) | **3632 passed**, 3 skipped(§4 的 3626 + 6:F-05 ×2 / F-07 / F-02 / F-10 ×2) | 0 |
| `npx vitest run`(全量) | 156 files / **3074 passed**(F-06 前端案加在既有 `it` 內,數不變) | 0 |
| `ruff check copycat tests` | All checks passed | 0 |
| `ruff format --diff` hunk 數 | 與 master 逐檔相等(state 2 / hub 4 / policy 0 / rules 1 / signal_hub.py 3):無既有區段重排 | — |
| `pyright` | 0 errors | 0 |
| `npx tsc -b` / `npx eslint src` | 無輸出 | 0 / 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | No issues found | 0 |
| `copycat validate --run-five … --run-four …`(主樹 out/) | 42/42 PASS | 0 |

真實環境:本批唯一 runtime 改動 F-02 只改 log 分桶(閘結果不變,Spec 軸核實),不需重啟驗;下次重啟後盤後
`grep "CDP 列閘" logs/server-*.log` 可能多一種 WARNING「首尾日 K 收盤 ≤ 0(壞資料)」文案。
