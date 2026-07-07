---
name: auto-verify
description: 跑「自動化驗證指令(tsc / vitest / pytest / ruff / build)」與「真實環境驗證(dev server + DevTools MCP + 截圖 / curl / CLI)」。在 /feat /bug /mod /refactor /perf 流程的「完成前 gate」階段呼叫,確認改動沒打壞既有測試與 build。先檢查專案形狀再選對應驗證指令來源,不硬跑 `cd frontend/` 撞牆。本 skill 是形狀偵測表與驗證方式表的唯一 source of truth(command 檔不重抄)。
metadata:
  author: user
  version: "2.2.0"
---

# Auto-Verify

完成前 gate:自動化驗證 + 真實環境驗證,雙層證據才算 Done。
**本 skill 是「專案形狀 → 驗證指令」與「feature shape → 真實環境驗證方式」兩張表的唯一 source of truth** — /feat 等 command 只寫「呼叫 auto-verify」,不重抄表格(2026-07-06 去除雙源 drift)。

## 自動化驗證五步驟(monorepo / frontend+backend 預設)

| # | 指令 | 工作目錄 | 必須 |
|---|------|---------|------|
| 1 | `npx tsc -b` | `frontend/` | 0 errors |
| 2 | `npx vitest run` | `frontend/` | 全綠 |
| 3 | `python -m pytest -v` | `backend/` | 全綠 |
| 4 | `ruff check .` | `backend/` | 0 issues |
| 5 | `npm run build` | `frontend/` | 成功 |

**指令組來源優先序**:專案有 `.claude/harness.json` → 自動化驗證以其 `verify` 陣列為準(與 git pre-push hook 共用,單一 source of truth);沒有 → 用本 skill 的形狀對應表。

**E2E 是 harness.json 之外的條件 gate**(刻意不入 verify 陣列 — 太慢,pre-push 不跑):有 Playwright e2e 的專案,verify 陣列全綠**不等於自動化驗證完成** — 還要依專案 e2e 判準(neigui:skill `e2e-conventions` 判準表)判定本次改動是否必跑 e2e;屬豁免類型 → commit message 註明(如 `[no-e2e: internal refactor]`)。

任一步紅 → 停下修,套鐵則 F「失敗處理 3 次上限」(見 `~/.claude/CLAUDE.md`)。

## 非 monorepo 專案形狀對應

當專案沒有 `frontend/` / `backend/` 分層,**先檢查專案形狀再選指令來源**:

| Shape | 指令來源 |
|---|---|
| frontend-only | `package.json` scripts(tsc / vitest / build) |
| backend-only | `pyproject.toml` / `Makefile`(pytest / ruff) |
| fullstack | 上方五步驟 |
| CLI / library | 專案 README / Makefile / `package.json` |
| worker / monorepo(workspace) | 專案 CLAUDE.md > 根 `package.json` workspace > Makefile |

**偵測不到驗證指令 → 停下來問 user**,不硬跑不存在的目錄。

可並行步驟(frontend tsc/vitest/build 與 backend pytest/ruff)用 `superpowers:dispatching-parallel-agents` 同時跑,合併單一報告。

## 真實環境驗證(依 feature shape 分流)

| Shape | 真實環境驗證方式 |
|---|---|
| web | `/run` 啟動 → Chrome DevTools MCP 操作 → Console 0 errors / 0 red warnings + 截圖 |
| 純後端 API | `curl` / `httpie` 跑 happy + ≥ 2 edge,貼 request / response 當證據 |
| CLI | 真實 argv × 3 + exit code + stdout / stderr 對照 |
| library | 一個獨立 consumer script 跑公開 API |
| worker / queue | 真實 message + retry + DLQ 驗證 |
| TUI | terminal recording(asciinema 或等價) |
| Electron / desktop | 真實啟動 + 三場景 + 截圖 |

至少測:Happy path、≥ 2 個 edge case(空輸入 / 錯誤輸入 / 邊界值)、抽 2 個沒改的相關功能確認 regression 沒打壞。

**Subsumed 判定**(web):該情境已有 Playwright e2e 覆蓋(spec 跑過真 backend + 真 browser)→ 標 `subsumed by e2e`,不重複 DevTools MCP 截圖。

**Infra 失敗 fallback**(token 過期 / browser MCP 斷線 / 外部 503):不硬撞 — 標 `infra_fail: <reason>` 回報呼叫方流程(/feat 記 `state.json.phase_6_blocked_reason`),browser MCP 斷線先試 `--isolated` profile,再退 curl + 元件測試替代覆蓋。

證據(截圖 / log / req-res 對照)放當前 task 的 artifact 目錄(例:`.claude/feat/<slug>/evidence/`),**檔名含 SC-N 或情境標籤**(例:`SC-2_login-empty-input.png`)。

## 何時呼叫

- /feat 的 Phase 5(自動化)+ Phase 6(真實環境)
- /bug 的 Phase 6(自動化)+ Phase 7(真實環境)
- /mod 的 Phase 6(自動化)+ Phase 7(真實環境)
- /refactor 的 Phase 6(自動化)+ Phase 7(真實環境)
- /perf 的 Phase 1 baseline 量測前 + Phase 6 行為驗證
- 任何「我覺得改完了,該驗證」的場景(對應鐵則 D『完成 ≠ 自動化綠燈』)

## 與 verification-before-completion 的職責邊界

- **auto-verify(本 skill)= 跑指令拿證據**:自動化綠燈 + 真實環境行為證據。
- **superpowers:verification-before-completion = 回頭核對動機**:重讀 brainstorm.md / SC-N / metric 目標,確認證據真的對應當初要的東西。
- 順序:auto-verify 全綠 → 才進 verification-before-completion。兩者都過才是 Done。

## 紀律邊界

- 專案層 `<project>/CLAUDE.md` 可覆寫本 skill 的預設指令(就近原則)
- **不允許「應該可以」收尾**(鐵則 D)
