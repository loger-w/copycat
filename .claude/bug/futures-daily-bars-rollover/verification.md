# verification — fix/futures-daily-bars-rollover(2026-08-30)

worktree `C:/side-project/copycat-wt-futures-daily-rollover`,自 master 09cc3e63。純前端(零 .py / config diff)。

## 自動化 gate(auto-verify;全部在 worktree 跑)

| gate | 指令(工作目錄) | 結果 | exit |
|---|---|---|---|
| 紅迴圈(修前) | `npx vitest run src/hooks/useFuturesBars.test.ts`(frontend/) | 4 failed / 14 passed(`expected 1 to be greater than or equal to 2` 等) | 1 |
| 紅迴圈(修後) | 同上 + `src/lib/trading-calendar.test.ts` | 35 passed | 0 |
| 反向驗證 | `git stash push -- src/hooks/useFuturesBars.ts` → vitest → `git stash pop` → vitest | 還原後 4 failed / 14 passed;pop 後 18 passed | 紅回來 → 綠回去 PASS |
| tsc | `npx tsc -b`(frontend/) | 無輸出 | 0 |
| eslint | `npx eslint src`(frontend/) | 無輸出 | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry`(frontend/) | `No issues found!` | 0 |
| vitest 全量(worktree) | `npx vitest run`(frontend/) | 3 次:2889/2890、2888/2890、2889/2890 —— 紅的全是 App 級 lazy + waitFor 1 s 逾時(`App.memo` railCtx ×3 / `App.corr-tab` ×1),每次不同 | 1 |
| vitest 全量(**差分**:worktree 內 `git stash push` 全部改動 = master code) | 同上 | 2884/2885,同一條 `App.memo` railCtx 紅 → **環境 flake,非本改動**(記 next-time 08-30 節) | 1 |
| vitest 全量(主 tree master 09cc3e63) | `npx vitest run`(C:/side-project/copycat/frontend) | 2885/2885 | 0 |
| 單檔重跑 | `npx vitest run src/App.memo.test.tsx` ×3(worktree) | 8/8 ×3 | 0 |
| ruff | `.venv\Scripts\python -m ruff check copycat tests`(worktree root,主 tree venv) | All checks passed! | 0 |
| pyright | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| pytest | `.venv\Scripts\python -m pytest -q -p no:cacheprovider` | 3171 passed, 1 skipped(202.9 s) | 0 |
| copycat validate | — | **未跑**:零 .py / configs / watchlists diff,replay 產物與 master 同一份;跑了只是重付 two replays 的時間 | skipped(理由如左) |

## 真實環境

> **pr-151-review F-09(08-30 晚)**:下面第 1 條判準在 PR #151 那版**會失敗** —— 期貨 tab 開著 = 00:00–00:01 那 60 秒有重繪 =
> `refetchInterval` 被重排到隔天(F-01)。fix/pr-151-review-followups 修後判準才成立;下方 mutation 表的 M1 / M2 / M3 三個突變體
> 都在「render 這一維」之外(測試 seam `renderHook` 推進期間不重繪),全殺 ≠ 界已釘牢 —— 修後另有「slack 窗內 rerender」紅測試釘住。

原始重現步驟 = 「preview 整天掛著跨過午夜」—— 本 session(08-30 晚)無法在真時間內重走;瀏覽器端無法 fast-forward TQ 的
`setInterval` / `Date.now`(prod 8721 亦關著)。真環境判準留給次一次跨午夜(08-31 週一早上,以含本 PR 的 dist 重 build 並讓 preview
自週日晚掛到週一):
1. 期貨 tab 開著跨 00:00 → DevTools Network 在 **00:01:00 ± 數秒**出現一發 `/api/market/bars/TXF?tf=D`(其他兩商品若 tab 內
   換過商品也各一發);
2. 08:46 日盤開後,CDP / MA 疊線的基準日(core readout / tooltip 的 `date`)= **08-28(五)**,不是 08-27;
3. 反例:同一日曆日內切到個股頁再切回,Network **不**多一發 `tf=D`(既有測試「離開超過 5 分鐘再切回 → 日 K 不重抓」的真環境面)。

## 未改功能抽查(自動化面)

- 分 K 路徑逐字不變:既有 `useFuturesBars.test.ts` 11 條(輪詢窗 / 切回立即重抓 / gcTime / timeout signal / 慢請求 warn)全綠。
- `trading-calendar.test.ts` 既有 nextTradingDayIso / shiftIso 等案全綠(新 helper 純新增,未動既有 export)。

## Review round 1 收修後(11 條全接受,見 `code-review-round-1.json`)

| gate | 結果 | exit |
|---|---|---|
| `npx vitest run src/hooks/useFuturesBars.test.ts src/lib/trading-calendar.test.ts` | 36 passed(新增:00:00:30 / 00:01:01 精確界 + 午夜失敗 60 s 重試) | 0 |
| mutation M1 固定 24 h(`: 24 * 60 * 60_000`) | 2 failed / 17 passed | 紅(殺)—— ⚠ M1–M3 共用 render 盲區,見「真實環境」節 F-09 註 |
| mutation M2 `DAY_ROLLOVER_SLACK_MS = 0` | 2 failed / 17 passed | 紅(殺) |
| mutation M3 拔掉 `status === "error" ? DAY_ERROR_RETRY_MS` | 1 failed / 18 passed | 紅(殺) |
| `npx tsc -b` / `npx eslint src` / `npx react-doctor@latest --scope changed --no-telemetry` | 無輸出 / 無輸出 / No issues found! | 0 / 0 / 0 |
| `npx vitest run`(worktree 全量) | 2888/2891;紅 = `App.memo` railCtx + `App.test` ×2(localStorage 記住 index tab / capital WS 唯一掛載),皆 waitFor 1 s 逾時 | 1 |
| `npx vitest run src/App.test.tsx src/App.memo.test.tsx` ×3 | 61/61 ×3 → 負載型環境 flake(同前段差分結論;handoff §3f L68 同族) | 0 |
