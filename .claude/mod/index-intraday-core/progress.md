# progress — mod/index-intraday-core

| 步驟 | 狀態 | 備註 |
|---|---|---|
| §0 開工:分支 mod/index-intraday-core(基準 c958b141) | done | 主 tree,無 worktree |
| §1 baseline:frontend 123 檔 / 2152 tests 全綠 | done | 2026-08-17 18:36 |
| §1 current-state.md | done | |
| §2 change-spec.md | done | L 級 |
| §3 change-spec review round 1(opus) | done:P1×5 / P2×8 全 accepted(R3 改 CSS 變數方案),spec 13 處 [amendment] | 無 P0 → 不加輪 |
| adapter `lib/index-accum-adapter.ts` + test(S 級主 session 直做,紅→綠;R6 窗過濾) | done(未 commit,入 🔴 換元件 wave) | 9 tests |
| 🟢 core mode="index" 注入(pkg A) | dispatched opus | 與 pkg D 平行 |
| 🔴 換元件(MarketChart / pane-frame / MarketPane)+ 測試改紅→綠 | pending | |
| 🔴 佈局(pkg D)| dispatched opus | CSS 變數方案 |
| §5 code review | pending | |
| §6 verification(自動化 + 截圖) | pending | |
