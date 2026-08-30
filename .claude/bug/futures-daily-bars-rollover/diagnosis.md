# 期貨日 K 跨日不重抓 —— 診斷紀錄(diagnosing-bugs 六 phase)

分支 `fix/futures-daily-bars-rollover`(worktree `../copycat-wt-futures-daily-rollover`,自 master 09cc3e63)。
來源:next-time 08-24 L408 → 08-28 triage 升 `/bug`;handoff `%TEMP%\copycat-handoff-2026-08-29-work-queue.md` §1c。

## Phase 1 迴圈

`cd frontend && npx vitest run src/hooks/useFuturesBars.test.ts`(hook seam,jsdom + fake timers,6 ms / 條,確定性)。
首條:`人一直在期貨 tab 上跨過午夜 → 次一日曆日重抓一次,cache 不停在昨天的快照` —— 掛載 D 09:00 抓到「D 部分 bar」快照,
推 24 h 到 D+1 09:00,斷言 `tf=D` ≥ 2 發且 `data.bars` 換成「D 完成 + D+1 部分」。修前輸出:
`expected 1 to be greater than or equal to 2`(1 failed | 14 passed)。

## Phase 2 最小配方

單 hook、單 query(`useFuturesBars("TXF","day")`)、牆鐘推 24 h;三者拿掉任一條就不紅。

## Phase 3 假說(排序)

1. **H1(證實)**:日 K `staleTime: Infinity` + `refetchInterval: false` → TQ 沒有任何觸發點跨日曆日重抓。預測:兩者都改成「到下一個
   日曆日的毫秒數」→ 三情境全綠;只改一個留一種情境紅(staleTime 本身不觸發 fetch;interval 在背景分頁 / 退訂 observer 不跑)。
   反向驗證:只 stash `useFuturesBars.ts` → 4 條紅回來;pop → 18/18 綠。
2. **H2(後端,本次不修,入 next-time 08-30 節)**:`server/bars.py::build_period` daily cache 鍵 = `(code|L, date.today())` 無 TTL →
   15:01 錨定日翻頁到午夜之間,前端再問都是早上那份 → 界必須取午夜,不取 15:00。
3. **H3(否決)**:queryKey 帶交易日 —— key 只在 re-render 時重算,週末無輪詢 = 無 re-render;行為靠別的 query 推動。

## Phase 4 儀器

無需額外 log:TQ observer 原始碼(`queryObserver.js` `#computeRefetchInterval` / `#updateStaleTimeout` / `resolveStaleTime`)確認
`staleTime` 與 `refetchInterval` 皆支援函式形式、interval 只在 `focusManager.isFocused()` 時打、staleTime 以 `dataUpdatedAt` 起算。

## Phase 5 修法

- `lib/trading-calendar.ts::msUntilNextLocalDate(from)`:到下一個本機日曆日 00:00 的毫秒數(純函式,三例測試)。
- `hooks/useFuturesBars.ts`:`DAY_ROLLOVER_SLACK_MS = 60_000`、`msUntilDayRollover(from)`;日 K
  `staleTime: (q) => msUntilDayRollover(q.state.dataUpdatedAt)`、`refetchInterval` 日 K 分支回 `msUntilDayRollover(Date.now())`。
  分 K 分支逐字不變。
- 四條 hook 測試:一直在 tab / 切走跨午夜再切回 / 背景分頁跨午夜回前景 / 同日內不重抓 + 兩個午夜恰兩發。
- `FuturesChart.tsx` 只改註解(「一天只打一次」→「同一日曆日只打一次、跨午夜重抓一次」)。

## Phase 6 清理

無 `[DEBUG-…]` 儀器、無拋棄式原型。Blast radius:`"day"` 模式唯一 caller = `FuturesChart.tsx:170`;App 只用 intraday;
新 helper 只有 hook 一個讀者。同構 `useIndexOverlay` / `useStockOverlay`(render 時翻鍵)記 next-time 不動。
