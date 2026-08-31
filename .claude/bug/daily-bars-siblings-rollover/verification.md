# verification — fix/daily-bars-siblings-rollover(2026-08-31)

worktree `C:/side-project/copycat-wt-daily-bars-siblings`,自 master 0b744bb8。純前端(零 .py / config diff)。

## 自動化 gate(auto-verify;全部在 worktree 跑)

| gate | 指令(工作目錄) | 結果 | exit |
|---|---|---|---|
| 紅迴圈(修前) | `npx vitest run src/hooks/useMarketBars.test.ts src/hooks/useStockBars.test.tsx`(frontend/) | market 7 failed / 8 passed;stock 5 failed / 19 passed(`expected 1 to be 2` / `expected 1 to be 3` / `setInterval … 0 times`) | 1 |
| 紅迴圈(修後)+ 期指同檔 | 同上 + `src/hooks/useFuturesBars.test.ts` | 61 passed | 0 |
| 反向驗證 | `git stash push -- src/hooks/useMarketBars.ts src/hooks/useStockBars.ts src/hooks/useFuturesBars.ts` → vitest → `git stash pop` → vitest | 還原後 12 failed / 27 passed;pop 後 39 passed | 紅回來 → 綠回去 PASS |
| tsc | `npx tsc -b`(frontend/) | 無輸出 | 0 |
| eslint | `npx eslint src`(frontend/) | 無輸出 | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry`(frontend/) | `No issues found!` | 0 |
| vitest 全量 | `npm test`(frontend/) | 153 files / 2912 passed | 0 |
| pytest / ruff / pyright / validate | — | **未跑**:零 .py / configs / watchlists diff(diff 全落在 frontend/src 與 docs / artifacts;pr-159-review F-03 回校 —— 原句「只有 frontend/src/hooks 五檔」是搬家 commit 前的快照) | skipped(理由如左) |

## 突變體(`PYTHONUTF8=1 python scratchpad/mutants.py`;逐一套用 → 兩檔 hook 測試 → `git checkout --` 還原)

| 突變體 | 結果 |
|---|---|
| M1 market 日 K interval 固定 `24 * 60 * 60_000` | 5 failed(殺) |
| M2 market `staleTime` 退回 `Infinity` | 1 failed(殺;背景分頁回前景那條) |
| M3 market 拔掉 `status === "error" ? DAY_ERROR_RETRY_MS` | 1 failed(殺) |
| M4 market 午夜那發吃 `active` 閘(`active ? msUntilDayRollover(...) : false`) | 1 failed(殺;active=false 跨午夜再切回) |
| M5 market interval 改吃 `q.state.dataUpdatedAt` | 1 failed(殺) |
| M6 stock 日界搶在 `barsPollInterval` 之前(`if (!isDaily) return poll`) | 2 failed(殺;SC-4 20 s 兩條) |
| M7 stock `staleTime` 退回 `Infinity` | 1 failed(殺) |
| M8 stock 拔掉 error 60 s 重試 | 1 failed(殺) |
| M9 stock interval 改吃 `dataUpdatedAt` | 1 failed(殺) |

還原後 `git status --short` 乾淨。

## 真實環境

原始重現步驟 = 「preview 整天掛著跨過午夜」—— 本 session(08-31 白天)無法在真時間內重走;瀏覽器端無法 fast-forward TQ 的
`setInterval` / `Date.now`。真環境判準留給次一次跨午夜(以含本 PR 的 dist 重 build、preview 自 08-31 晚掛到 09-01 早上;與 #155 的
期指判準同一晚可一併驗):
1. 台股綜合 tab 或個股頁(日 K 模式)開著跨 00:00 → DevTools Network 在 **00:01:00 ± 1 s** 出現一發
   `/api/market/bars/TWSE?tf=D`(週 / 月 K 模式則 `tf=W` / `tf=M`;櫃買 / 期指鍵各一發)與 `/api/stock/bars/<code>?tf=D`;
2. 09-01 09:00 後 K 線末根 = **09-01** 那根(部分 bar),前一根 08-31 是完整 bar(修前:末根停在 08-31 早上首抓時的部分值、沒有 09-01);
3. 反例:同一日曆日內切到個股頁再切回台股綜合 tab,Network **不**多一發 `tf=D`;
4. 人在個股頁跨午夜(台股綜合 tab hidden)→ 00:01 Network 仍有那一發 `market/bars/*?tf=D`(午夜那發刻意不吃 `active`)。

## 未改功能抽查(自動化面)

- 分 K 路徑逐字不變:`useMarketBars.test.ts` 既有 8 條(非交易時段不輪詢 / 盤中 60 s / active=false 不背景輪詢)、
  `useStockBars.test.tsx` 既有 19 條(SC-4 20 s 接線三條 / days 進 key / m2–m10 走 tf=1)全綠。
- 期指那支未動行為:`useFuturesBars.test.ts` 22 條全綠(只開 export + 加 doc 一句)。
- 兩個 caller 的元件測試(`MarketChart` / `StockChart` / `MarketPane` / `IndexPage` / `App.*`)在全量 2912 內全綠。

## Review round 1 收修後(commit b0492f54;11 條中 9 條接受 / 2 條駁回 / S-F1+P-F6 留 user,見 `code-review-round-1.json`)

| gate | 結果 | exit |
|---|---|---|
| `npx vitest run src/hooks/useMarketBars.test.ts src/hooks/useStockBars.test.tsx src/hooks/useFuturesBars.test.ts` | 63 passed(新增:active=false 時午夜失敗 60 s 重試、月 K it.each) | 0 |
| 突變體 M1–M9 重跑 + **M4b**(只有 60 s 重試吃 `active` = P-F2 修前形狀) | 10/10 KILLED(M1 7 / M2 1 / M3 2 / M4 2 / M4b 1 / M5 1 / M6 2 / M7 1 / M8 1 / M9 1 failed) | 紅(殺) |
| `npm test` 全量 | 153 files / 2914 passed | 0 |
| `npx tsc -b` / `npx eslint src` / react-doctor `--scope changed` | 無輸出 / 無輸出 / `No issues found!` | 0 / 0 / 0 |
| S-F6 長行複量 | python `len()` 逐行:五檔**零行 > 120 字元**(awk / reviewer 量的是 UTF-8 bytes) | 駁回依據 |

**流程事故(記 ops-discipline)**:突變體腳本以 `git checkout -- <file>` 還原,在**未 commit 的收修**上跑會把收修洗回 HEAD(M1 跑完即發生,
全量因此紅 1 條、M3 找不到字串)。正解 = 收修先 commit 再跑突變體,或還原改走 `git stash` / 讀進記憶體再寫回。

**真環境判準補一條(P-F2 / P-F3 知情變更)**:5. 人在個股頁、後端剛好在 00:01 沒起來 → 起來後 ≤ 60 s Network 自動再打一發
`market/bars/*?tf=D`,不用切回 tab。

## Helper 搬家(🔵 490e6a2e,user 拍板 `lib/day-bars-rollover.ts`)+ docs chore(c1dab2ec)後

| gate | 結果 | exit |
|---|---|---|
| `msUntilDayRollover` 本體對照 | `git show HEAD:…useFuturesBars.ts` 函式區塊 vs 新 lib `diff` 空 → 逐字相同;`DAY_ROLLOVER_SLACK_MS` 同值;`DAY_ERROR_RETRY_MS` `= POLL_MS` → 字面 `60_000` | 0 |
| `npx vitest run` 三支 hook 測試 + `trading-calendar.test.ts` | 80 passed(測試檔零改,只改註解路徑) | 0 |
| `npm test` 全量 | 153 files / 2914 passed | 0 |
| `npx tsc -b` / `npx eslint src` / react-doctor `--scope changed`(8 files) | 無輸出 / 無輸出 / `No issues found!` | 0 / 0 / 0 |
| 增量 diff 機械快篩(review fixed point b0492f54 之後:490e6a2e 搬家 + c1dab2ec docs) | main agent 逐檔看:lib 新檔 import 只有 `msUntilNextLocalDate`、三個 export 名不變;`useFuturesBars.ts` 無 `POLL_MS` / `msUntilNextLocalDate` 殘留;docs 兩檔純文字 —— 無新 finding | — |
