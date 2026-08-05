# automated verification summary — futures-allday-tab

Round 1(2026-08-05,HEAD 1b95d89)全綠:

- 後端:pytest 1795 passed / ruff 0 / pyright 0
- 前端:vitest 1290 passed(87 files)/ tsc -b 0 / eslint 0
- Golden gate:replay four/five_tigers exit 0 + `copycat validate` **42/42 PASS**
  (worktree 無 data/,自主 tree 複製 697MB 後在 worktree code 上實跑;本輪 diff 未觸及
  replay/engine/data 模組,validate 綠 = 迴歸保護)

指令輸出證據:`automated-verification-round-1.json` + `evidence/replay-*.log`、
`evidence/validate.log`。
