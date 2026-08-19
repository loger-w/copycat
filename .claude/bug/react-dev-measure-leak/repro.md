# repro.md — dev 看盤數小時後 renderer Aw Snap

## 1. 症狀與重現(真環境,2026-08-19)

- user:`npm run dev` 看盤數小時 → Chrome renderer crash 畫面(Aw Snap);F12 觸發重整後恢復。
- 實證兩次:renderer PID 10572 14:11:27 生 → 19:07 死(Private 15.3 GB、一核 100% 全程);
  19:09 重載後新 renderer 16404 2 分鐘內重現(+70 MB/分、CPU 75%)。V8 heap 全程 ≤ 169 MB。
- 分頁內:`performance.getEntriesByType('measure').length` 載入 1 分鐘 21,746 → 632 筆/秒;
  `performance.clearMeasures()` 清 75,179 筆 → renderer Private 762 → 624 MB(1.8 KB/筆 × 632/s ≈ 1.1 MB/s ≈ 15 GB/4.5h)。
- 完整量測與時序:`docs/research/2026-08-19-browser-crash-scan.md`。

## 2. Loop(能變紅的指令)

- 真環境:MCP 分頁 `performance.getEntriesByType('measure').length` 每 10 秒取樣 → 修前單調上升(632/s)。
- 測試層(vitest jsdom,已實跑):補 `console.timeStamp` stub(vitest console 缺此函式,React 據此關 user timing)
  後,render 同一元件 50 次新 props → `performance.getEntriesByType('measure').length` 0 → 102
  (名稱 `​Leaf` / `Update`)。→ 紅測試 = 裝 guard 後推進 fake timer,條目數應歸零。

## 3. Root cause(systematic-debugging:一次一假說,皆已實驗)

| 假說 | 實驗 | 結果 |
|---|---|---|
| JS heap 洩漏(tick 陣列 / 訊號 feed 無上限) | 分頁 sampler 4 小時 | V8 heap 谷底 30→115 MB,與 15 GB 不符 → 否 |
| WS 推播風暴 / IO 執行緒 | 8 條 WS 實測 10 s | futures 17.9 msg/s、txo 23 KB/s → 否 |
| user 分頁 vs 本分頁 | 分頁內配 300 MB → 哪個 process 跳 | 16404 = 本分頁;導去靜態頁 CPU 歸 0 → app 頁本身 |
| 主執行緒忙(短任務) | MessageChannel 2 s 迭代 200k(靜態)vs 68k(app) | 66% 忙,全 <50 ms → Long Task 看不到 |
| Blink 側 User Timing 累積 | `getEntriesByType('measure')` + `clearMeasures()` 前後量 process 記憶體 | **632/s、−138 MB/75k 筆 → 成立** |

定位:`react-dom@19.2.7` `cjs/react-dom-client.development.js:4104-4180` `logComponentRender`:
`alternate.memoizedProps !== props` → `performance.measure("​"+name, {detail:{devtools:{properties:[Changed Props diff…]}}})`,
否則 `console.timeStamp`(不留條目)。`supportsUserTiming` = `console.timeStamp && performance.measure`(Chrome 恆 true);
root mode 在 DEV 恆帶 ProfileMode(:23441)。Chrome User Timing buffer 無上限、不在 V8 heap、不自動回收。
本 app 每則 WS 訊息 App 根 setState → 全樹 re-render、子元件 props 新 identity → 每則訊息數十~數百筆。

**只影響 development build**;production build 無此段。

## 4. 修法(最小)

`frontend/src/lib/dev-perf-guard.ts`:`installUserTimingGuard({ maxEntries })` 以 PerformanceObserver 觀察 measure,
增量計數達閾值即 `performance.clearMeasures()` + `clearMarks()`,回傳 dispose(模組層單例、缺能力 / observe 拋錯
一律 no-op);`main.tsx` 僅 `import.meta.env.DEV` 時安裝並接 `import.meta.hot?.dispose`。不碰 React、不碰放大因子(R2/R6 另輪)。

[amendment 2026-08-19 Phase 6 real-env finding] 第一版 `intervalMs` setInterval 定期清除在隱藏分頁被 Chrome intensive
throttling 壓到每分鐘一次(20 s 實測 interval 7 次 vs observer 回呼 256 次 / 13,195 筆),改為 observer 閾值版。
[amendment 2026-08-19 code review round-1] C-1 增量計數(不全表掃描)/ C-3 observe 拋錯降級 / C-4 冪等 + hot.dispose。

## SC

- SC-1 dev 下 React 留下的 measure / mark 條目在達閾值時被清空,且**不依賴 timer**(背景分頁 timer 被節流)——
  驗證:`dev-perf-guard.test.tsx`(凍結 setInterval 下 render 20 次 → flush observer → 條目 < 閾值;
  邊界 N-1 不清 / N 清;手動 mark 一併清)。
- SC-2 guard 可 dispose 且冪等(HMR / 多入口不疊 observer)—— 驗證:同測試檔 dispose 後再 render 條目回升;install 兩次 dispose 一次即解除。
- SC-3 真環境:MCP 分頁裝上修後版本,`measure` 條目數 30 分鐘內不單調上升;renderer Private 記憶體(scratchpad
  `renderer-mem.csv`)30 分鐘增幅 < 100 MB(修前 +2,100 MB/30 min)。驗證窗口:任何時段(夜盤即可)。

## Edge cases

- production build:guard 不安裝(`import.meta.env.DEV` false)→ 不影響任何使用 User Timing 的工具。
- 無 `performance.clearMeasures`(極舊環境)→ guard 以 `typeof` 檢查後 no-op。
- HMR 重載 main.tsx → 舊 timer 隨舊 module 失效?main.tsx 不是 HMR boundary 會整頁 reload,timer 隨頁消失;仍提供 dispose 以防萬一。

## 不能破壞的既有行為

- app 自身不使用 performance.mark/measure(grep 零命中)→ 清除不影響 app 邏輯。
- DevTools Performance 錄製:trace 在 measure 發出當下擷取,之後清 buffer 不影響錄到的 track。
