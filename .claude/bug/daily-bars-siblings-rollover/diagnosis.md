# useMarketBars / useStockBars 日 K 跨日不重抓 —— 診斷紀錄(diagnosing-bugs 六 phase)

分支 `fix/daily-bars-siblings-rollover`(worktree `../copycat-wt-daily-bars-siblings`,自 master 0b744bb8)。
來源:next-time 08-30 節第 3 條 / pr-151-review F-03;handoff `%TEMP%\copycat-handoff-2026-08-31-daily-bars-siblings.md` §1。
期指那支(`useFuturesBars`)已於 PR #151 / #155 修完,本案 = 逐字同病的兩支兄弟 hook。

## Phase 1 迴圈

`cd frontend && npx vitest run src/hooks/useMarketBars.test.ts src/hooks/useStockBars.test.tsx`(hook seam,jsdom + fake timers,
每條 1–60 ms,確定性)。紅測試先於任何修法寫入(沿 `useFuturesBars.test.ts` 最後兩個 describe 的樣板):
首條 `日 K:人一直在 tab 上跨過午夜 → 00:01 重抓一次,cache 不停在昨天的快照` —— D 09:00 掛載抓到「D 部分 bar」快照,推到
D+1 00:01:01,斷言 `tf=D` 恰 2 發且 `data.bars` 換成「D 完成 + D+1 部分」。修前輸出:`expected 1 to be 2`
(market 7 failed / 8 passed;stock 5 failed / 19 passed —— 新加 12 條中 11 條紅,「空 + timeout 20 s 優先於日界」是白名單鎖,修前即綠)。

## Phase 2 最小配方

單 hook、單 query(`useMarketBars("TWSE","day")` / `useStockBars("2330","day",30)`)、牆鐘推過 00:01。三者拿掉任一條就不紅:
分 K 路徑本來就 60 s 輪詢;同日曆日內不重抓是預期;00:00:30 仍不打是 slack 的定義。

## Phase 3 假說(排序;由紅測試而非讀 code 產生)

1. **H1(證實)**:非分 K 路徑 `staleTime: Infinity` + `refetchInterval` 恆 `false` → TQ 零觸發點跨日曆日重抓。
   預測:兩處換成 `msUntilDayRollover` → 一直在 tab / 週 K / 背景回前景 / slack 窗內重繪 / setInterval 零重排 五條變綠。命中。
2. **H2(證實)**:午夜那發失敗(`retry: 1` 用完)後 interval 又回「下一個午夜」→ 整個交易日停在昨天 —— 與期指 pr-151-review F-05
   同款。預測:不加 error 分支則「午夜那一發失敗 → 60 s 後再試」仍紅。命中(突變體 M3 / M8 各殺 1)。
3. **H3(證實,市場面獨有)**:`useMarketBars` 的 `active` 閘若把午夜那發也擋掉,台股綜合 tab(App 以 `hidden` 保留不 unmount)
   在人於個股頁跨午夜後切回,只會把 interval 重排到**下一個**午夜 —— 切回當下不會打。預測:日 K 分支吃 `active` 則
   「active=false 跨過午夜再切回」仍紅。命中(突變體 M4 殺 1)。
4. **H4(證實,個股面獨有)**:`useStockBars` 的 `barsPollInterval` 對日 K 恆回 `false` 且是 refetchInterval 的整個回值 → 新分支必須
   排在它**之後**(它回 20 s 空態重試時要讓路)。預測:日界搶先 → SC-4 兩條 20 s 測試紅。命中(突變體 M6 殺 2)。
5. **H5(否決,沿 #151 結論)**:queryKey 帶日期 —— key 只在 render 時重算,單靠它沒有觸發點;且期指那支已證明無日期鍵也能修。

## Phase 4 儀器

無需額外 log:TQ 行為(`useBaseQuery` 每 render `setOptions` → `QueryObserver` 回值一變就 clear + 重排計時器;interval 只在
`focusManager.isFocused()` 時打;staleTime 以 `dataUpdatedAt` 起算)已於 #151 / #155 讀過 `@tanstack/query-core 5.101.2` 原始碼並記在
`lib/day-bars-rollover.ts::msUntilDayRollover` doc(pr-159-review F-03 回校:doc 隨搬家在 lib,原句指舊址)。本案只驗「兩支兄弟走同一條路」:反向驗證 stash 三支 hook → 12 紅 / 27 綠;pop → 39 綠。

## Phase 5 修法

- `useFuturesBars.ts`:`DAY_ERROR_RETRY_MS` 開 export(三支同源);`msUntilDayRollover` doc 加「讀者三支」一句。helper 搬家
  先問 user(handoff 指明 grilling 一輪再動)→ **08-31 拍板新開 `lib/day-bars-rollover.ts`**(三顆常數 / 函式逐字搬,三支 hook 平行 import;
  不併 `lib/trading-calendar.ts`:那邊純日曆算術、這邊 TQ 新鮮度政策;🔵 commit 490e6a2e)。
- review round 1(11 條)收修 commit b0492f54:`useMarketBars` 日 K 分支改**整段**不吃 `active`(P-F2:午夜失敗恰發生在人不在時,60 s 重試若
  吃閘就整晚凍結)—— H3 的結論修正為「日 K 這條與 `active` 正交」。
- `useMarketBars.ts`:`staleTime: isMinute ? 0 : (q) => msUntilDayRollover(q.state.dataUpdatedAt)`;`refetchInterval` 非分 K 分支
  `error → 60 s`、否則 `msUntilDayRollover(Date.now())`;**整段不吃 `active`**(理由 H3 + P-F2;一天一發、每把 key 一發,error 只在
  HTTP 非 2xx,不是 XR-4 擋的每 60 s SubHistory 成本)。分 K 分支逐字不變。
- `useStockBars.ts`:`staleTime: isDaily ? (q) => msUntilDayRollover(...) : 0`;`refetchInterval` 先 `barsPollInterval`,`!isDaily || poll !== false`
  原樣回傳,日 K 才 `error → 60 s`、否則到下一個午夜。分 K 分支經 `barsPollInterval` 原樣回傳。
- (追記,pr-159-followups Std S-F2)以上兩支 hook 的 staleTime / refetchInterval 內聯運算式為**當時實作快照** ——
  fix/pr-159-review-followups(F-02)後已收進 `lib/day-bars-rollover.ts::dayBarsStaleTime / dayBarsRefetchInterval`,
  並加 F-01 空態閘(`retryEmpty`)。
- 測試:market 8 條(round-1 後含月 K it.each)/ stock 6 條(pr-159-review F-03 回校;含 slack 窗內每 100 ms 重繪 40 s 那條、同一秒重繪 setInterval 零重排、午夜失敗 60 s 重試、
  背景分頁回前景;market 另有週 K 同分支 + active=false 跨午夜再切回;stock 另有 20 s 空態重試優先於日界)。

## Phase 6 清理

無 `[DEBUG-…]` 儀器、無拋棄式原型(突變體腳本在 scratchpad,還原後 `git status` 乾淨)。Blast radius:`useMarketBars` 唯一 caller
`MarketChart.tsx:66`(IndexPage / MarketPane 轉 `active`);`useStockBars` 唯一 caller `StockChart.tsx:68`;`DAY_ERROR_RETRY_MS` 新 export
讀者三支(含 useFuturesBars 自己;pr-159-review F-03 回校);`msUntilDayRollover` 讀者由 1 → 3(followups 後政策函式收 lib、常數與它全降私有)。全量 vitest 2912/2912 含兩個 caller 的既有元件測試。
同類結構:`useIndexOverlay` / `useStockOverlay` 有日期鍵(render 時翻鍵),#155 已記 next-time 知情不動;後端 `build_period` 夜盤段
快照為 handoff §2 另案。
