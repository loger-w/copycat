# progress ledger — group-grid

plan: .claude/feat/group-grid/implementation/PLAN.md(v2)
branch: feat/group-grid(start 2bb87a1)

| task | 狀態 | commits | review |
|---|---|---|---|
| T1 engine(quotes/group_snapshot/guard 🔴+🟢 兩對) | done | 71daf85[red]→cc1731d 🔴[green]→b3a9941[red]→04e6f9f[green] | main gate PASS(67 檔級/全案 2060、pyright 0 親驗;偏離 5 條合理 — amend 為紅證據更正且未推;ws_disconnect flake 既有記錄) |
| T2 hub 摘要 + route + 接線 | done | 8bdc5c9[red]→58ac45d 🟢[green] | 檔級 79+40 綠;全案 2081 passed/1 skipped、ruff PASS、pyright 0 |
| T3 前端(🔵 抽共用 + 🟢 UI) | done | cdd21b6 🔵 → 6cfa0a8 [red] → 1402089 [green](中斷續跑兩棒) | 全前端 1414/95 檔綠、tsc/eslint 0;測試檔零改動;isPending 不畫卡片為合理語意修 |
| T4 Phase4 fix(A1/A2/A3/A4/A5/A6/B1/B2/B3) | done | fc5110e [red]→b5e3bcd 🔴[green]→620a944 [red]→cfd2f86 🔴[green] | 2096+1423 綠、pyright 0 親驗;偏離 7 條合理;deviation 2(reconnect 不清 _backfill_failed)記 next-time |
