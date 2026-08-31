# verification — fix/pr-165-review-followups

pr-165-review 收修(user 拍板「全修」)。worktree `C:\side-project\copycat-wt-pr165-followups`,
自 origin/master `6e642ed3` 開分支。範圍 = 七條 Nice(#1–#7)全做 + #9 順手一條界上測試;
#8 依內部複查結論不單獨動(要補就連 `_daily_tag` 整段 → next-time 併 test-hygiene 批);
#3 第三處(review JSON)為歷史處置紀錄刻意不竄改,改 bars.py doc + diagnosis 追記(劃線保留原句)。

## 逐條對照

| # | 處置 | 落點 |
|---|---|---|
| #1 | 交叉註記 ×2 | bars.py `DAILY_FINAL_TIME` doc + app.py `_calendar_crosscheck` 旁(語意不同刻意分家,不 import 同動) |
| #2 | 固定字串 INFO ×2(唯一行為改動) | `_daily_stale_or_empty` / `_period_stale_or_empty`,格式沿 `bars %s: ...` 慣例 |
| #3 | 口徑改寫 | bars.py doc(重試由下一個請求驅動)+ diagnosis.md 追記;review JSON 不動 |
| #4 | 新測試 | `test_period_stale_fallback_keeps_wm_shape`(ISO 週 2 桶 vs 3 根日 bar) |
| #5 | docstring 註記 + next-time | `is_partial_last` 兩口徑段 + next-time /mod 條 |
| #6 | docstring 校正 | app.py index_overlay「至多兩次(界前一次、界後定稿一次)」 |
| #7 | artifact 回校 | verification.md 六條→八條 + 反向驗證母體加註(追記式) |
| #9 | 新測試 | `test_boundary_instant_is_final_side`(界上 = 定稿側) |
| #8 | 不做 → next-time | 併 test-hygiene 批(與 `_daily_tag` 同構兩行一起補觀測點) |
| 報告 | 雙檔入 docs/superpowers/specs | pr-165-review.md + .audit.md(pr-159 前例) |

## Gate(全部 exit 0)

| gate | 結果 |
|---|---|
| pytest 全量 | **3244 passed, 1 skipped**(209 s) |
| test_bars.py | 63 passed(61 既有 + 2 新) |
| ruff | All checks passed! |
| pyright | 0 errors, 0 warnings |
| replay four/five + validate | **42/42 PASS**(data junction 借主 tree、用畢即拆、主 tree data 完好) |
| 前端 gate | 免(本輪零 frontend 檔) |

## 突變體驗證(3/3 殺;每輪清 __pycache__ 防同秒陷阱)

- M1 `return TaggedBars(_shaped(stale, period), tag)` → `TaggedBars(stale, tag)`:1 failed(#4 新測試紅) |
- M2 `daily_get` `>=` → `>`:1 failed(#9 紅)
- M3 `daily_put` `<` → `<=`:1 failed(#9 紅)
- 還原後 63 綠。

## round-1 two-axis review 收修

Standards 4 條全收:S-1 兩行 INFO 統一形狀(鍵、括號欄、根數;grep 錨點 =「墊背舊快照」,
雙行共用)/ S-2 test docstring「四個呼叫點」→「三個」(**pr-165 報告 #4 原句「四個」為誤**,
實測 `grep "_shaped("` 3 個呼叫點;已發布報告不回改,以本檔為勘誤)/ S-3 刪 W 測試死 clock
鷹架 / S-4 next-time 節名去歧義。Spec 軸:九項全落地、零 creep、突變體三殺三(reviewer
獨立重注入複驗)、報告雙檔與 root 版 byte-identical(`cmp` 零差);其「驗證證據未落檔」
指的是本檔尚未 cp 進 worktree,證據本已在此。收修後 63 綠 + ruff + pyright 零項。

## 真實環境判準(#165 判準之外新增一條)

6. **墊背可觀測**:盤後 TC4 關著時發一次日 K 請求(F5 大盤/期貨 tab),
   `grep "墊背舊快照" logs/server-*.log` 應命中(兩行 INFO 共用此錨點;修前零命中)。
