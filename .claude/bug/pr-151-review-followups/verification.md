# verification — fix/pr-151-review-followups(2026-08-30 深夜)

worktree `C:/side-project/copycat-wt-pr151-followups`,自 master 2873e004。純前端 + 文件(零 .py diff)。
來源:`/pr-review 151` 報告 `docs/superpowers/specs/pr-151-review.md` 9 條,user 拍板「全修」(F-02 採秒級量化;F-03 為文件修正,
`useMarketBars` / `useStockBars` 的 code 同病另開 /bug)。

## 自動化 gate

| gate | 指令(工作目錄) | 結果 | exit |
|---|---|---|---|
| 紅先行 | `npx vitest run src/hooks/useFuturesBars.test.ts`(frontend/)— 新 3 條 | 2 failed / 20 passed(F-07 slack 窗內 rerender:1 發;F-02 churn:49 次 setInterval);切回路徑那條現碼綠(鎖 `dataUpdatedAt` 回歸) | 1 |
| 修後 | 同上 + `src/lib/trading-calendar.test.ts` | 39 passed | 0 |
| mutation M-A 還原舊公式(`msUntilNextLocalDate(new Date(from)) + SLACK`) | 修後 / review 收修後各跑一次 | 2 failed / 20 passed ×2 | 紅(殺) |
| mutation M-B 拔掉 `Math.ceil(ms / 1000) * 1000` | 同上 | 1 failed / 21 passed ×2 | 紅(殺) |
| tsc / eslint / react-doctor | `npx tsc -b` / `npx eslint src` / `npx react-doctor@latest --scope changed --no-telemetry` | 無輸出 / 無輸出 / No issues found!(review 收修後 tsc / eslint 再跑一次 0) | 0 |
| vitest 全量(worktree) | `npx vitest run` | 2892/2896;紅 4 條 = `App.memo` railCtx + `App.test` ×3(localStorage 記住 index tab / 群組圖牆點卡片 / capital WS 唯一掛載),皆 waitFor 1 s 逾時;兩 reviewer 同時在跑 | 1 |
| 單檔重跑 | `npx vitest run src/App.test.tsx src/App.memo.test.tsx` ×2 | 61/61 ×2 → 環境 flake(next-time 08-30 節第 2 條判讀規則) | 0 |
| ruff / pyright / pytest | 主 tree venv,worktree root | All checks passed! / 0 errors / 3193 passed, 1 skipped(211.9 s) | 0 / 0 / 0 |
| copycat validate | — | 未跑(零 .py / configs diff) | skipped |

## 真實環境

原始重現 = preview 掛過午夜(需真時間),本輪不可重走。判準(取代 PR #151 那版):08-31 週一,含本 PR 的 dist 重 build、
preview 掛在期貨 tab、分頁保持可見跨 00:00:
1. DevTools Network 在 **00:01:00 ± 1 s** 出現一發 `/api/market/bars/TXF?tf=D`(PR #151 那版預期**不會**出現 —— pr-151-review F-01);
2. 08:46 後 CDP / MA 疊線基準日 = 08-28;
3. 反例:同日切個股頁再切回,Network 不多一發 `tf=D`。

F-01 的第一手證據(非 prod):主 tree vitest 拋棄式模擬四例(A 現碼 slack 窗內重繪 → 09:00 仍 1 發;B R2 重繪 → 00:01 2 發;
C `dataUpdatedAt` 版切回 → 11:02 才打;D R2 切回 → 00:01),已轉成本分支的三條正式測試。

## 未改功能抽查

- 既有 `useFuturesBars.test.ts` 19 條(含 08-30 五條跨午夜)全綠 —— 00:00:30 仍不打 / 00:01:01 打的邊界在秒級量化下仍成立。
- 分 K 路徑:`refetchInterval` 分 K 分支與 `staleTime: isMinute ? 0` 逐字等價(Spec 軸核對)。
