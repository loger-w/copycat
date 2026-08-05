# progress ledger — discord-watchlist

plan: .claude/feat/discord-watchlist/implementation/PLAN.md(v2)
worktree: C:\side-project\copycat\.claude\worktrees\feat-discord-watchlist
branch: feat/discord-watchlist(start_sha a858dec)

| task | 狀態 | commits | review |
|---|---|---|---|
| T1 stock_watchlist(SC-6) | done | 8277335 [red] → 6563239 [green] | main gate PASS(diff 逐項符 PLAN;26 passed + 相關 106 passed 零退化;偏離 2 條皆合理:lock test 綠起步、docstring 補句) |
| T2 watchlist_service(SC-2/3/7 + R9) | done | e901426 [red] → 8044495 對齊(無 TDD tag)→ 05d8a5a [green] | main gate PASS(diff 符 design;pyright 全案 0 err 親驗;偏離 4 條合理 — R9 改用檔內 FakeSource 因 helpers 版 unsubscribe 無記錄) |
| T3 discord_bot(SC-1..5/7) | done | ce74d51 [red] → 15b759c [green] | main gate PASS(全案 1792 passed、pyright 0 親驗;偏離 4 條合理;AllowedMentions eq 測試修正入 green body) |
| T4 Phase4 fix(A1/B1、A2、A3、F4) | done | 6b8e979 [red] → 342f7a7 [green] | 全案 1822 passed、ruff/pyright 綠;偏離 5 條合理(_require_current helper、create_group 存名 strip 摺入) |
