# Dispatch — implementer 包 1(🔵 上提 useFlashArm)+ 包 2(🟢 lock)— 同一 implementer 序列做

## 你的任務
在 worktree `C:/side-project/copycat/.claude/worktrees/flash-arm-lock`(branch `mod/flash-arm-lock`,**所有 git 操作只在此目錄**;主 tree `C:/side-project/copycat` 被另一 session 佔用,絕不可 cd 過去 commit / switch)實作 R5「閃電下單鎖定武裝」。

先讀(單一 message 平行 Read):
1. spec:`C:/side-project/copycat/.claude/mod/flash-arm-lock/change-spec.md`(§2 設計逐檔、§3 白名單、§5 測試標記、§6 commit 順序、§7 風險)
2. 現況:`C:/side-project/copycat/.claude/mod/flash-arm-lock/current-state.md`
3. review findings 與處置:`C:/side-project/copycat/.claude/mod/flash-arm-lock/change-spec-review-round-1.json`(spec 已含 `[amendment]` 修正;以 spec 為準)
4. 專案 skill:`C:/side-project/copycat/.claude/skills/frontend-conventions/SKILL.md`、`C:/side-project/copycat/.claude/skills/frontend-testing/SKILL.md`
5. 源檔:`frontend/src/lib/flash-arm.ts`、`hooks/useCapital.ts`(`useCapitalWsStatus` / `setCapitalWsStatus`)、`components/stock/PriceLadder.tsx`、`components/stock/StkfutLadder.tsx`、`components/futures/FuturesLadder.tsx`、`components/stock/LadderView.tsx`、`components/rail/RightRail.tsx` 及各自 `*.test.tsx`、`lib/flash-arm.test.ts`

## 包 1(🔵 refactor,行為零變)
- 新 `frontend/src/hooks/useFlashArm.ts`(spec §2.2);三梯改接 `armCtl?: FlashArmControl` props + 本地備援;刪三梯各自的 reducer / idleTimer / Esc / conn_lost(移入 hook);加 `left_view` 卸載 effect;RightRail 持有 `useFlashArm()` 並傳給三梯;flash-arm.ts 加 `left_view` 事件(此階段 = `initialArm()`)。
- Gate:`npx vitest run src/lib/flash-arm.test.ts src/hooks src/components/stock src/components/futures src/components/rail` 全綠(**既有測試零改動**)+ `npx tsc -b` + `npx eslint src`。
- 一個 commit:`🔵 refactor(frontend): 閃電武裝狀態上提為 useFlashArm 共用 hook(RightRail 持有,三梯 props 接) [refactor]`
- 若包 1 需要新測試(useFlashArm hook 本身的 characterization:Esc / conn_lost / idle / inactive 不掛監聽),用 `[lock]` tag + body `mutation-verified`(先 Edit 改壞 → 紅 → Edit 還原 → 綠;禁 git checkout/restore)。

## 包 2(🟢 lock 功能,TDD 紅→綠)
- 紅 commit:`🟢 test(frontend): add failing test for SC-1..SC-9 鎖定武裝 [red]` — 只加/改測試檔:
  flash-arm.test.ts(新增案例 + 型別字面值補 `locked:false`,見 spec §5「該變」)、useFlashArm.test.tsx、
  PriceLadder / StkfutLadder / FuturesLadder / RightRail 各新增案例(spec §5 清單;StkfutLadder 補 Esc / idle / 連 3 敗)。
  紅 commit 前用 `npx vitest run <檔>` 確認新案例紅、舊案例仍綠(tsc 可暫紅)。
- 綠 commit:`🟢 feat(frontend): 閃電梯鎖定武裝 — locked 旗標 + 鎖定鈕 + RightRail 跨梯保留 [green]`,body 註 `red→green for <red-sha>`。
  實作:flash-arm.ts lock/unlock/locked 分支;LadderView 鎖定鈕(spec §2.4 視覺案 A,accent token);FuturesLadder 自帶 JSX 加同款;三梯 `onToggleLock`;RightRail 檔頭 D-13 註解改寫。
- 可有 `[refactor]` 收尾 commit(若需要),不混類。

## 全域約束
- **鐵則 E**:不 skip / 不改既有 assertion(spec §5 明列「該變」的字面值除外)/ 不 mock 真依賴 / 不 catch 吞錯。
- 既有測試紅但不在「該變」清單 → 停下回報,不硬改。
- 三類分離:🔵 / 🟢 不混 commit;tag 規則:紅 `[red]` 只動測試檔;綠 `[green]` body 註 red sha;`[lock]` 需 mutation-verified;同步產物(eslint 修)不掛 TDD tag。
- 測試慣例:無 jest-dom / user-event;`fireEvent`;`vi.useFakeTimers()` 用完 `vi.useRealTimers()`;wsStatus 用 `setCapitalWsStatus`;RTL selector 精確(`getByRole("button", {name: "鎖定"})` 與「鎖定中」區分)。
- 不動後端;不動 CapitalConfirmDialog;不改 RightRail 條件 render 為 hidden。
- react-doctor:`npx react-doctor@latest --scope changed --no-telemetry`(在 frontend/)只有**新增** finding 算 FAIL。
- 完成後跑一次全套 `npx vitest run`(worktree frontend/)+ `npx tsc -b` + `npx eslint src`,回報數字。
- 回報格式:每包 commit sha + `git log --format="%h %s" master..HEAD` 全文自檢 tag;gate 指令與 exit code;任何偏離 spec 之處逐條列出(含理由);未做/受阻項目明列。回報是資料,不寫給 user 看。
