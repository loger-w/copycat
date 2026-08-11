# react-doctor 首掃 triage(2026-08-11)

掃描:v0.9.11,232 檔,85 findings(Bugs 21E+22W / Perf 13 / Maint 20 / A11y 9)。
Triage:3 個 opus reviewer 平行逐條開檔判定(stream hooks / updater+a11y / perf+maint),
本檔為裁決彙總。**總計:TP 42 / FP 33 / needs-human 10**(FP 率 39%,集中在特定 rule)。

## 一、確認的真問題(按價值排序)

### P1 — 值得開一輪 /mod 修(行為保持的正確性修復)

1. **useRiver.ts:115 impure updater(error)**:onDelta 的 setState updater 內換場分支
   `void load()` 發 REST fetch — fetch 真的在 render 期間發出;StrictMode 換場打雙份。
   修法:加 sessionRef,換場判斷搬到 setState 之前(正解先例 useStockStream.ts:119-124
   statusRef pattern)。連帶收斂 useRiver:94/95/100 三條 warning。
2. **WatchlistSidebar.tsx:115 impure updater(error)**:updater 內寫 localStorage;
   併發 rebase 下持久化值與最終 state 可分歧(重整後折疊狀態錯)。修法:持久化移出
   updater。連帶收斂 :51/:117 兩條 warning(persistCollapsed 兩個呼叫點同型)。
3. **TickTape.tsx:57 index-as-key(本批唯一真的會重排的)**:newestFirst 前插使全部
   key 位移,每筆成交整個 tbody 卸載重掛(30-200 列 DOM churn)。修法:key 改
   `${t.t}-${ticks.length-1-i}`(尾端回推索引)或後端序號。
4. **StockChart.tsx:78 adjust-state-on-prop-change**:isFut 轉換走 effect 收斂,檔內
   註解自承「閃一格載入中」— 有可見症狀。修法:改 render 期間調整(prevIsFut pattern,
   repo 已有 WatchlistManagerDialog prevOpen 樣板)。
5. **冗餘 render ref 寫入 ×2(直接刪一行)**:useFuturesStream.ts:61、useStockStream.ts:136
   — 全部 setState 點已有 imperative 配對寫入,render 這次是重覆賦值。
6. **ref 同步搬 useLayoutEffect ×5**:useBreadth:61、useIndexStream:71-73、
   useSignalAlerts:82(後者更優解 = drop 改 useCallback([]) 刪 ref)。與 WS 時序有關,
   跟 P1 批同輪走流程。

### /chore 快修批(一行零風險)

- **format.ts:18 js-hoist-intl**:formatPts 每呼叫 new Intl.NumberFormat,期權鏈每列
  ×3 + 每 push 重繪都在打 — 本批最有熱度的 perf 修復。同檔第 1 行 nf 即樣板。
- **limitOnly/marketOnly 去重**:DepthBar.tsx:76 與 OrderBook.tsx:150/151 逐字重複、
  註解明言口徑必須一致 → 收進 lib/stock-tick.ts 共用。
- **aria-label ×3**:WatchlistManagerDialog:154(改名 input 零可及名稱)、:303、
  WatchlistSidebar:425(搜尋框);順手補未被報的 Dialog:327。
- **拖拉握把 aria 修正**(收斂 291/292 兩條):span role="button" 無 tabIndex =
  「宣告了做不到的能力」;正解是拿掉 role/aria-label 改 aria-hidden,不是換 tag。
- **module-scope hoist ×3 + NumberField 真元件化**:MarketPane:108-109、DepthBar:93、
  SignalRulesDialog:275(函式回傳帶 key JSX,假元件比效能更值得修)。

### 中價值,單獨拍板

- **CapitalConfirmDialog.tsx:27 手刻 modal**:真錢下單確認窗,無 focus trap / Esc 取消。
  換 `<dialog>` + showModal 有實際操作價值,但要照 WatchlistManagerDialog 樣板
  (display class 由 open prop 選、onClose 拉回 prop、`m-auto` 抵 preflight)。

## 二、needs-human(10 條,排期項)

- **no-giant-component ×7**:全部附了具體拆分建議(FuturesLadder→useFuturesArm、
  CandleChart→useCandleViewport/Hover、SignalRulesDialog→useRuleForm+RuleRow、
  StockIntradayChart→useIntradayHover/Geometry、StockPage→Header/Body、
  WatchlistManagerDialog→GroupColumn/StockColumn、WatchlistSidebar→useWatchlistDnd)。
  架構級 /refactor 素材,不急。
- **useStockStream:126/128/135 render ref 寫入**:切檔核心鍵,render 寫入 =「commit
  當下即生效」的刻意時序;搬 effect 有 tick 讀舊鍵的競態窗,動之前要人拍板。

## 三、誤報(33 條)與 rule 處置建議

| Rule | FP/總數 | 原因 | 建議 |
|---|---|---|---|
| effect-needs-cleanup | 9/9 | cleanup 全部存在,工具沒追到 return 路徑 | **disable** |
| no-fetch-in-effect | 6/6 | WS 推播流全量對齊腿是刻意架構(conventions 明載) | **disable** |
| js-set-map-lookups | 5/5 | 母體全部個位數~30 上限 | **disable** |
| no-array-index-as-key | 4/5 | SVG 幾何陣列位置式 key 是正確行為 | 降級/保留(抓到 TickTape) |
| js-combine-iterations | 4/6 | 母體太小無熱度 | 降級/保留 |
| 其他零星 | 5 | exhaustive-deps 刻意 deps、unguarded parse 下游已 clamp 等 | 個案 |

技術上 TP 但**單人桌面看盤價值低,建議 wontfix**:tr 鍵盤路徑 ×2(LimitList/Sector)、
自選列 div onClick(修復成本 > 收益,巢狀 button 問題)、only-export-components ×6
(dev HMR 粒度,prod 零影響 — 可趁 refactor 順手)、rerender-state-only-in-handlers
(省不到 render)。

## 四、接 gate 前置(若要進 auto-verify)

先在 doctor.config 把上表 disable 三條關掉、降級兩條,再接
`react-doctor --scope changed`(只擋新增)進 auto-verify 前端 gate;不先調 rules
會被誤報煩死。是否接 gate 待 user 拍板。

## 五、原始裁決

三份逐條 JSON(rule/file/line/verdict/confidence/reason/fix)見本次 session 派工紀錄;
掃描原始輸出 `npx react-doctor@latest --verbose` 可隨時重現(85 條清單穩定)。
