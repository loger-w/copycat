# refactor-plan — housekeeping 八條(refactor/housekeeping-batch-2026-08-21,R10 / C,鏈尾)

來源:rounds.md §R10(預核准)。**Why / 為什麼是現在**:next-time 散落的 🔵 條目(08-11 ~ 08-18 各輪留尾)已累積八條,皆為「兩份會漂」或「死碼 / 過期註解誤導」類;
鏈尾一次收、每條獨立 commit、行為零差異。baseline:pytest 2895 / vitest 2528 全綠(2026-08-21 23:3x)。

## 步驟(每步單獨保持綠、單獨 commit;順序無依賴,可依此序)

| # | 條目 | 檔案 | 做法 | 測試保護 | 類別 |
|---|---|---|---|---|---|
| C1 | `localYmd()` 兩份 | `hooks/useStockOverlay.ts:5`、`hooks/useIndexOverlay.ts:5` | 抽 `lib/format.ts::localYmd()`(或 `lib/trading-calendar.ts::isoLocalDate(new Date())` 若語意逐字相同 —— 先比對兩份實作,相同才合;不同則抽新函式保留差異並註明),兩 hook 改 import | 兩 hook 既有測試(queryKey 含日期);新增 lib 單元測試 1 案(固定 Date)🟢 先行 | 🔵(+🟢 測試) |
| C2 | 「六腿」字樣 22 處 | `grep -rn 六腿 copycat frontend/src`(非測試) | 改腿數無關文案(「各腿」/「多腿」/「江波圖」),**不動任何識別字 / 測試 id / 文案測試所鎖字串**;若某處字串被測試鎖住 → 該處測試同步(🔵,同 commit,body 註明是文案鎖) | 全套 | 🔵 |
| C3 | `lib/index-chart-svg.ts` 死碼 cluster | `buildIndexGeometry` / `rightEdgeLabels` / `IndexPt` / `RightEdgeLabel` / `RightEdgeInput`(R1 已確認未用)+ `index-chart-svg.test.ts` 對應 describe;`MarketPane.memo.test.tsx:28` 註解改寫;`MarketPane.size.test` 硬寫 26 / 272 → import `INTRADAY_CHROME_Y`(`lib/pane-frame.ts`) | **刪前 grep 動態用法**(`grep -rn "buildIndexGeometry\|rightEdgeLabels" frontend/src docs` 含字串形式);`outOfDomainLevels` / `IndexGeometry` / `buildOverlayGeometry` 保留 | tsc + 全套 | 🔵 |
| C4 | 主副圖比例三份 / `EMPTY_HLINES` 兩份 | `FuturesChart.tsx:48-49 MAIN_RATIO_*`、`chart-frame.ts:42 CARD_MAIN_RATIO`、StockChart 行內(grep `260` `330`);`CandleChart.tsx:70` / `StockIntradayChart.tsx:128 EMPTY_HLINES` | `chart-frame.ts` export `MAIN_RATIO = 260 / 330`(或 NUM/DEN 兩常數)三處改 import;`EMPTY_HLINES` 搬 `lib/chart-hlines.ts`(或 ChartHLine 型別所在檔)export,兩處改 import(**identity 穩定語意不變**:仍是模組級常數) | 既有幾何測試(字面量期望不變)| 🔵 |
| C5 | 三梯武裝列 JSX 合一 | `stock/LadderView.tsx`、`futures/FuturesLadder.tsx`(+ `StkfutLadder` 若自有一份) | 抽 `components/ladder/ArmRow.tsx`(props:armed / locked / follow / 回呼 / 文案差異);**DOM 結構、class、aria-pressed、testid 逐字不變**(R2 已把這些 toggle 維持 aria-pressed) | 三梯既有測試(武裝 / 鎖定 / 跟隨)| 🔵 |
| C6 | 測試 deadline-poll helper 6 份 | `tests/server/test_breadth_engine.py:245`、`test_corr_engine.py:352`、`test_corr_engine_river.py:156`、`test_futures_engine.py:622`、`test_index_engine.py:32`、`test_stock_engine.py`(`_wait_until`)+ 同步式 `deadline = time.monotonic()+…` 四處(boot.py / breadth_routes / calendar_wiring / capital_api) | async `_wait_until` 六份收 `tests/helpers/wait.py::wait_until`;同步式若簽名一致亦收 `wait_until_sync`,不一致者保留並註明 | pytest 全套 | 🔵(測試 infra) |
| C7 | 四處註解舊根因 | `futures_engine.py`(grep「跨 session 只推一邊」)、`corr_engine.py` 兩處、`corr_config.py:7`、`app.py`(grep 同句) | 改口:真因 = 08-18 refcount(reap 殺 key),「同 symbol 跨 session 只推一邊」非事實;保留「base 腿必須 source=futures_engine」的架構約束(那是設計選擇,理由改寫為「避免兩 session 重複訂閱同 symbol 的 churn / refcount 殭屍」) | 無行為 | 🔵 |
| C8 | 四處裸 `localStorage.getItem` | `RightRail.tsx:39 initialTab()`、`MarketPane.tsx:323/327/336-337/347` | 包 try/catch 回預設(照 `initialSubTab()` 慣例 —— 先 grep 該慣例實際所在,已不存在則照 `StockPage.initialView` 的 try/catch 形) | **行為改動(Safari 隱私模式 throw → 不白屏)** → 紅測試先行(`localStorage.getItem` throw → render 不炸、用預設)| 🔴(非 🔵,三類分離) |

## 禁止 / 守則
- 每步 commit 前跑觸及測試 + tsc/ruff;全部完成後主 session 跑全套 + validate。
- 紅 → 預設 refactor 改錯;不改既有斷言(C2 文案鎖例外:同 commit 同步並註明)。
- C3 刪碼前必 grep 動態用法(字串 / docs 引用只更新文件)。
- 任何一條做不到零行為差異 → 停、記 next-time,不硬做。

## 可量化改進(收尾核)
duplication:localYmd 2→1、EMPTY_HLINES 2→1、比例常數 3→1、武裝列 JSX 3→1、wait helper 6→1;死碼 −5 符號 −3 describe;過期註解 0 殘留;裸 getItem 0 殘留。

---
## Plan review round 1 amendments(`refactor-plan-review-round-1.json`,14 條全 accepted;以本節為準)
- **C1(R8)**:兩份 `localYmd` body 逐字相同且 = `lib/trading-calendar.ts::isoLocalDate(new Date())` → 直接改用 `isoLocalDate`,**不新開** `lib/format.ts::localYmd`;既有 hook 測試無日期保護,安全性來自 body 同;新增 🟢 測試沿 `trading-calendar.test.ts:27` 23:30 案(鎖非 toISOString)可省(已有)。
- **C2(R11)**:`corr_config.py:93-104` logger.warning 的**執行期字串**排除(或改「預設腿組」並 body 標明 log 文字改動);只動註解 / docstring。
- **C3(R1 / R2 / R3 / R14)**:`index-chart-svg.test.ts:215` outOfDomainLevels describe 的 `g` 改字面量 `{ yDomain: [lo, hi] }`(數值照現行 hi*1.003 / lo*0.997 拆解註解);`IndexGeometry` 瘦身只留 `yDomain`(或 `outOfDomainLevels` 參數改本地 `{ yDomain: [number, number] }` 後連 `IndexGeometry` / `IndexPt` 一起刪);
  **不動 `MarketPane.size.test` 字面量**(frontend-testing skill:期望值不由同源常數算回;mutation 實證);拆兩 commit:(a) 死碼刪除 + test describe,(b) `MarketPane.memo.test.tsx:28` 註解。commit body 記「R1 採 edgePriceLabels 路線,index 側 rightEdgeLabels 確為死碼(master HEAD 重跑 grep)」。
- **C4(R9 / R10)**:`MAIN_RATIO_NUM` / `MAIN_RATIO_DEN` 兩常數 export 自 `chart-frame.ts`,三處算式**逐字不變**(`Math.round((h * NUM) / DEN)`;`CARD_MAIN_RATIO = NUM / DEN` derived);`EMPTY_HLINES` 由 `CandleChart.tsx` export(`ChartHLine` 型別所在),StockIntradayChart 改 import,零新檔。
- **C5(R4 / R13)**:實為 **2 份**(PriceLadder / StkfutLadder 已委派 LadderView;FuturesLadder 自帶);`components/ladder/ArmRow.tsx` module-level 具名 export,props:`gap`/`className`、`lockTitle`、`lock?`(未給不渲染)、`children`(期貨「當沖」checkbox / `armControls` slot);驗收 = 兩梯渲染 `outerHTML` 與改前逐字相同(測試以 snapshot 字串比對)+ 武裝鈕 focus 後 rerender `activeElement` 不變。
- **C6(R12)**:async `_wait_until` 六份 + `test_watchlist_service.py:57`、`test_signal_hub.py:426/438`、`test_signal_routes.py:255/275`、`test_ws_disconnect.py:298` 同型者一併收 `tests/helpers/wait.py::wait_until`(簽名 `(pred, timeout=2.0)`,語意相同者才收);同步式四處(boot / breadth_routes / calendar_wiring / capital_api)**不收**(簽名不相容),收尾核如實寫 N→1。
- **C7(R7)**:站點 = `grep -rln "跨 session 只推一邊" copycat configs tests spikes` 完整清單(app / futures_engine / corr_engine / corr_config / index_engine / futures_source / river_backfill / verify / models + configs/correlation.json 註解欄 + tests ×5 + spikes ×2);口徑統一指 `.claude/skills/tc4-market-facts/SKILL.md`;`ops-discipline/SKILL.md:12` 理由改 refcount(結論不變)。
- **C8 移出本批(R5 / R6)**:先例 `lib/fut-chart-mode.ts`(非 initialSubTab);真白屏層在 App.tsx 四處 + 全站 ~14 處 setItem → 獨立 /mod(`lib/storage.ts::readLocal/writeLocal` 全站收),記 next-time。

## 實作偏離回填(code review Z5)
- C4:react-doctor `only-export-components` 逼出 `lib/chart-hlines.ts` 新檔(零新檔目標放棄;`ChartHLine` 由 CandleChart re-export,既有 import 路徑與 identity 不變)→ 8 個 🔵 commit(七條 + C4 收尾)。
- C5 實為 2 份;C6 為 6→1(四個同步式 + 三個專屬 predicate helper 不收,理由見 commit body)。
