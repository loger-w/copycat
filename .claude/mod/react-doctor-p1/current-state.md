# current-state — react-doctor P1 批修復(2026-08-11)

Spec 來源:`docs/research/2026-08-11-react-doctor-triage.md` §一 P1 節(user 撰寫並拍板,
修法已逐項裁決)→ /auto 預核准替代條件成立,免 grilling。分流判定:已成形方案
(指名落點檔案 + 修法),決策點已由 triage 裁決收斂。

Baseline:master 7fa18d46,`npm test` 108 檔 / 1698 tests 全綠(2026-08-11 12:07)。

## 現況 vs 目標(逐項)

| # | 檔:行 | 現況 | 目標 | 行為差異 |
|---|---|---|---|---|
| 1 | `hooks/useRiver.ts:115-122` | `onDelta` 的 setState updater 內換場分支 `void load()` 發 REST fetch(updater 不純);StrictMode 換場打雙份 `/api/river/state` | sessionRef pattern:換場判定與 `load()` 搬到 setState 之前,updater 回歸純函式(先例 `useStockStream.ts:119-124` statusRef / F-1 註解) | dev(StrictMode)換場由 2 次 fetch 收斂為 1 次;prod 行為不變 |
| 2 | `components/stock/WatchlistSidebar.tsx:104-131` | `toggleCollapsed`(:109)/ `dropCollapsed`(:128)在 updater 內呼叫 `persistCollapsed` 寫 localStorage;`toggleUngroupedCollapsed`(:117)同型直寫 | 持久化移出 updater(handler 內以 render 閉包值算 next → persist → set) | 併發 rebase 下持久化值與最終 state 不再可分歧;StrictMode 下每次 toggle 寫 localStorage 1 次(原 2 次,值相同) |
| 3 | `components/stock/TickTape.tsx:57` | `key={t.t + '-' + i}`,newestFirst 前插使全部 key 位移 → 每筆成交整個 tbody 卸載重掛(30-200 列) | key 改尾端回推索引 `${t.t}-${ticks.length - 1 - i}`(前插時既有列 key 不變) | 既有列 DOM node 保留;滿 200 筆環形丟頭時仍會位移(與現況同,不惡化) |
| 4 | `components/stock/StockChart.tsx:74-89` | isFut 收斂走 `useEffect`(下個 render 才生效),:100 註解自承回現貨切換閃一格;`spotModeRef` 記還原值 | render 期間調整(官方 adjust-state-on-prop-change;repo 樣板 `WatchlistManagerDialog.tsx:69-78` prevOpen);spotModeRef 改 state(render 期間寫 ref 會產生新 doctor finding) | 進出合約的收斂在同一 commit 完成,消除中間 frame;對外可見終態不變(既有 D10/A6 測試全綠) |
| 5a | `hooks/useFuturesStream.ts:61` | `stateRef.current = state` render 期間寫入;全部 `setState` 點(:76-77、:108-109)已有 imperative 配對寫入 | 刪除該行 | 零(冗餘賦值) |
| 5b | `hooks/useStockStream.ts:136` | `accumRef.current = accum` render 期間寫入;全部 `setAccum` 點(:217、:246-247、:281-283、:299-301、:322-324)已配對 | 刪除該行 | 零(冗餘賦值) |
| 6a | `hooks/useBreadth.ts:61` | `stateRef.current = state` render 期間寫入(無 imperative 配對,靠 render 同步) | 搬 `useLayoutEffect`(deps `[state]`),宣告於 WS effect 之前 | 同步時點由 render 期移到 commit 期;WS handler 讀取皆為非同步,無觀察差異 |
| 6b | `hooks/useIndexStream.ts:71-73` | `twseRef/otcRef/tradeDateRef` 三行 render 期間寫入 | 併一個 `useLayoutEffect`(deps `[twse, otc, tradeDate]`),宣告於 WS effect 之前 | 同上 |
| 6c | `hooks/useSignalAlerts.ts:81-82` | `drop` 每 render 重建,`dropRef` render 期間同步 | 優解(triage 裁決):`drop` 改 `useCallback([], …)`(只碰 `timersRef` 與 `setQueue`,皆穩定)→ 刪 `dropRef`;:96 timer 與 :117 `dismiss` 直接用 `drop` | 零(dropRef 原本就是為了拿最新 drop,穩定化後恆同一顆) |

## Caller map(grep 全量,無動態用法 — React hook/元件無字串 dispatch)

全部改動**不動任何 export signature**,caller 零波及:

- `useRiver` → `CorrPage.tsx`(runtime)
- `useFuturesStream` / `useBreadth` / `useIndexStream` / `useSignalAlerts` → `App.tsx`(runtime);
  `FuturesPage` / `IndexPage` / `IndexBar` / `MarketChart` / `MarketPane` / `ToastStack` 皆
  type-only import(`WsStatus` / `IndexSeries` / `TxfQuote` / `SignalToast`,不變)
- `TickTape` / `StockChart` / `WatchlistSidebar` → `StockPage.tsx`(runtime)
- `useStockStream` → `StockPage.tsx`(runtime;本輪只刪 :136 一行,:126/128/135 明確 out of scope)

## Backward compat / migration

無:無 API shape、無持久化格式變更(localStorage key 與值格式不變),無 migration。

## 既有測試覆蓋(行為合約,均不改 assertion)

九檔各有 colocated 測試:`useRiver.test.ts`(8)/ `WatchlistSidebar.test.tsx` /
`TickTape.test.tsx`(9)/ `StockChart.test.tsx`(24,含期貨態 D10 + 還原 A6 兩節)/
`useFuturesStream.test.ts` / `useStockStream.test.ts` / `useBreadth.test.ts` /
`useIndexStream.test.ts` / `useSignalAlerts.test.tsx`;另 `StockPage.test.tsx` / `App.test.tsx`
吃整合面。既有測試無 StrictMode wrapper → 項 1/2 的 bug 現況無紅測試,紅先行要新增
StrictMode 案例。
