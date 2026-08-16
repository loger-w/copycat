# Dispatch — fix 波 round 1(code review 處置)

Worktree `C:/side-project/copycat/.claude/worktrees/flash-arm-lock`(branch mod/flash-arm-lock,**只在此目錄動檔 / git**;主 tree 另一 session 使用中不可碰)。
先 Read:`C:/side-project/copycat/.claude/mod/flash-arm-lock/code-review-round-1.json`(全部 finding + 處置)、`change-spec.md`(§2/§3/§7)、`C:/side-project/copycat/.claude/skills/frontend-testing/SKILL.md`,再開相關源檔與測試。

## 要做(依 json 的 disposition=accepted 者;doc 類由 main session 處理,你不用動 spec)
1. **S1**(🔴 安全):三梯 then 分支的 `send_ok` 恢復 `if (!aliveRef.current) return;` 守門(遲到的成功不計入);catch / `r.ok===false` 的 `send_fail` 維持無條件 dispatch。RightRail 測試:鎖定 → 現股梯點價 A(pending)→ 切到期貨 ctx → 點價兩次 fail(streak 2)→ resolve A ok → 再 fail 一次 → 解除且清鎖定(即 A 的 ok 沒把 streak 歸零)。
2. **S2**(🔴 安全,`[auto-default]`):RightRail 在 **`armCtl.state.locked` 為 true** 時,`instrumentKey` 改變(現股換 code)→ `setStockQty(initialQtyState())`;期貨 `ctx.product` 改變 → `setFutQty(initialQtyState())`(沿既有 render 期間 `prevInstrument` 調整 state 的 pattern,或同 pattern 加 prevProduct)。**未鎖定時不重置**(W-7 / R2-10 不變)。tradeKind 不動。測試:鎖定 + 張數按 5 → 換 code → 張數輸入框回 1;未鎖定同流程 → 仍 5;期貨同款。
3. **S3**:三梯 `lockDisabled` 整條 `&& !arm.state.locked`(即 `((armDisabled) || wsStatus !== "open") && !locked`);測試:PriceLadder locked 下 `setCapitalWsStatus("connecting")` → 「鎖定中」鈕不 disabled(且仍鎖定,connecting 不清)。
4. **T1**:useFlashArm.test:lock → touch → advance 6 min → state 仍 `{armed:true,locked:true,failStreak:0}`。
5. **T2**:useFlashArm.test 或 PriceLadder.test:lock → advance 6 min(仍武裝)→ unlock(元件層點「鎖定中」)→ advance ARM_IDLE_MS+1 → armed false。
6. **T3**:RightRail SC-6 案:`setCapitalWsStatus("closed")` 之後、rerender 回 STOCK 之前補 `act(() => setCapitalWsStatus("open"))`。
7. **T4**:RightRail SC-12(b) 案:fireEvent.click(買 100)後才斷 orderCalls===0;fireEvent.click(「鎖定中」)→ 鈕轉「鎖定」且「解除」仍在。
8. **T5**:三梯 SC-1 案補 `expect(lock.getAttribute("title")).toBe(LOCK_TITLE)`(import 常數)。
9. **T6**:LadderView.test 補:未給 onToggleLock → `queryByRole("button",{name:"鎖定"})` null;給了才出現。
10. **T7**:PriceLadder.test R4 案註解標明真鎖是 useFlashArm.test identity 案。
11. **T8**:PriceLadder SC-1 案補 DOM 次序(鎖定鈕在武裝鈕之後、交易別 select 之前)+ 未鎖態 className 含 `border-line`。
12. **T9(E-2)**:RightRail:SC-12(b) 之後 rerender 回可交易合約 → 仍「解除/鎖定中」且點價送出 1 call。

## Commit 規則
- S1 + S3:同一 🔴 commit?**不行** — S1/S3 是對本分支尚未 merge 的新功能修正,分類仍屬 🟢 功能範圍內修正:用 `🟢 fix(frontend): 鎖定武裝 review r1 修正 — send_ok 守門 / lockDisabled 不變式 [green]`(body 註 `code review r1: S1 S3`),先 commit 測試紅(`🟢 test(frontend): add failing test for review S1/S3 [red]`)再綠。
- S2 同上獨立一對 red/green(`🟢 feat(frontend): 鎖定態換標的 qty 回初值(review S2)`),body 註 `[auto-default: 鎖定態 instrument 變更 qty 回初值 | reason: 名目放大無訊號,S2]`。
- 純測試補強(T1..T9)一顆 `🟢 test(frontend): 鎖定武裝 review r1 測試補強(T1-T9)[lock]`,body `mutation-verified`:至少對 T1(timer 事件改 disarm)與 T2(刪 touchIdle)各做一次 Edit 改壞→紅→Edit 還原→綠,回報貼結果;禁 git checkout/restore。
- 鐵則 E;既有測試不改 assertion。
- Gate:`npx vitest run`(全套)+ `npx tsc -b` + `npx eslint src` + `npx react-doctor@latest --scope changed --no-telemetry`(新增 finding = FAIL);回報數字、`git log --format="%h %s" master..HEAD`、每 finding 的處置結果、偏離處。
