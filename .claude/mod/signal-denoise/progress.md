# progress ledger — mod/signal-denoise
spec: .claude/mod/signal-denoise/change-spec.md(round-1/2 review 已修入)
baseline: pytest 2652 passed / vitest 2200 passed(2026-08-17 晚)

包切分(L 級,dispatch opus):
- Pkg A 後端 detector:signals_config.py(🟢)/ signal_state.py(🔵+🔴)/ tests/live/test_signal_state.py / tests/test_signals_config.py — 主 tree
- Pkg B 規則+migration:signal_rules.py / tests/test_signal_rules.py / tests/server/test_signal_routes.py / tests/server/test_signal_hub.py `_RULE_PARAMS` — 主 tree(A 之後)
- Pkg C hub Discord 合併:signal_hub.py / tests/server/test_signal_hub.py — 主 tree(B 之後)
- Pkg D 前端:signal-model.ts / SignalRail.tsx / SignalRulesDialog.tsx + tests — worktree .claude/worktrees/signal-denoise-fe(branch mod/signal-denoise-fe),完成後 cherry-pick 回 mod/signal-denoise

| 包 | 狀態 | commit 範圍 | review |
|---|---|---|---|
| Pkg D 前端 | done(worktree) | mod/signal-denoise-fe 3c580358..HEAD 8 commits(🟢 groupSignals red/green、🟢 Dialog 欄位 red/green、🔴 摘要 red/green、🔴 SignalRail 合併列 red/green) | vitest 2217 passed / tsc / eslint / react-doctor 0 新增;待 cherry-pick + 主 session review gate |
| Pkg A 後端 detector | done | 3c580358..HEAD 5 commits(🔵 set→dict / 🟢 config red+green / 🔴 SC-1..3 red+green) | pytest 全案 2663 passed / ruff / pyright 0;replay 127→89(−29.9%)PASS;待 §5 自評 |
- Pkg D 已 cherry-pick 回 mod/signal-denoise(05b3ff2c..ab7abd3c);[green] body 的 red sha 指向 worktree 原 sha(2f22b721 等),對應關係:2f22b721→05b3ff2c、86f7b1ad→74bfd75d、535a8949→ee016d00、c1ee4e1f→6419651f
| Pkg B 規則+migration | done | 2 commits(🔴 red/green,HEAD~1..HEAD) | 316 passed(觸及)/ ruff / pyright 0;真檔 v1 載入 sha 前後同;超範圍:test_signal_hub `test_upsert_preserves_other_rules_state` fixture 補 dwell 0(斷言未改) |
| Pkg C hub Discord 合併 | done | 2 commits(🔴 red/green) | signal_hub 97 passed;全案 2687 passed / ruff / pyright 0 |
波尾:進 §5 自評(2 lens finder opus) → §6 驗證
| §5 自評 | done | code-review-round-1.json(P1×2 / P2×15);fix 波後端 8 commits + 前端 3 commits | self_review_head=9f6171a6f17dba5cc9d96ce171908fbba688c790;全案 pytest 2696 |
- 記錄:T-8(0d81d670 [green] 夾 fixture 補鍵,斷言未動)/ T-9(commit 序以包為單位,偏離 §6 宣告序,三類未混)/ T-10 rejected(step 1 沿 window_secs 慣例,記 next-time)/ groupRuleNames 段序仍新在前(前端 fix 波留尾,記 next-time)
- 尾修:groupRuleNames 段序 → 到達序(4ceee425 / 1bc20707 / 9cfb4a55);前端全套 2221 passed / tsc / eslint OK
## §7 回頭核 goal(對照 change-spec SC-1..8 + 白名單)
| SC | 實作 | 測試 | 真實環境 |
|---|---|---|---|
| SC-1 dwell | signal_state._advance_rearm | test_signal_state SC-1 ×5 | 回放 −29.9%(窗口外降級) |
| SC-2 側別 | _advance_sides + set_basis 清 _side | SC-2 ×5 + C-1/C-2 ×3 | 同上 |
| SC-3 共用冷卻 | 冷卻鍵 (code,"surge_crash","") | ×2 | 同上 |
| SC-4 Discord 合併 | _discord_worker pending / _send_discord(rows) / 分批 | TestDiscordMerge 6 + lock 4 + C-3/C-5 | verify 無 Discord(降級:測試);prod 待過目 |
| SC-5 前端合併列 | groupSignals / SignalRail | 32 + 24 | 192→178 列、13 組;截圖 ×3 |
| SC-6 回放 | replay_cdp.py | — | 127→89 PASS;jsonl 120 旁證 |
| SC-7 規則 UI | Dialog 欄位/摘要;PARAM_SPECS | Dialog 22 / routes | 截圖 ×2 |
| SC-8 migration | _migrate_v1 / v2 | TestMigrationV1ToV2 ×9 | 真檔載入 sha 不變;UI upsert 落 v2 |
白名單 W1–W10:correctness lens 逐條 ok;無預告外紅。migration 可逆:見 verification.md。
