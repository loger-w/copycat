# R5 前端狀態/對話框/自選批(`mod/frontend-state-batch`)— change spec

來源:`docs/superpowers/specs/2026-08-24-do-batch-rounds.md` §R5(13 條:N055 / N030 / N064 /
N067 / N068 / N083 / N097 / N115 / N117 / N114 / N116 / N118 / N266)。user 對 13 條全部勾「做」、無附註。

## 0. 既有行為白名單(不可破壞;優先於本輪新行為)

前置 grep 結論(caller map,含動態用法):

| 對象 | caller / 讀者 |
|---|---|
| `useSaveWatchlist`(自選 PUT) | **3 個寫者**:`WatchlistManagerDialog`、`WatchlistSidebar`、`StockPage`(N117 的「三個 caller」) |
| `useCapitalPositions` | 6 處:`WatchlistSidebar` / `StockPage` / `GroupGridView` / `PriceLadder` / `StkfutLadder` / `FuturesLadder` / `FuturesChart` / `CapitalPositionsList` |
| `futExchangeContract` | 5 處:`App.tsx`(有 try)/ `FuturesChart`(有 try)/ `StkfutLadder`(有 try)/ `RightRail`(有 try)/ **`FuturesLadder`(無 try ← N083)** |
| `CapitalConfirmDialog` | 4 caller:`CapitalOrdersList` / `CapitalPositionsList` / `FuturesLadder` / `OrderPanel`(四者的 onConfirm/onCancel 皆同步 setState 卸載,已逐一讀過) |
| `dropTargetFromPointer` | 唯一 caller `WatchlistSidebar`(move / up 各一次)+ 單元測試 |
| `useFeeDiscount` | 4 讀者:`WatchlistSidebar` / `StockPage` / `GroupGridView` /(新)`PriceLadder`(原本自持 state) |
| `PARAM_FIELDS`(訊號規則參數表) | `SignalRulesDialog` 內部(本輪搬到 `lib/signal-params.ts`,新增 parity 測試讀者) |
| `timeTicks`(river) | `RiverOverlay` + `RiverCards`;**同時是 `RiverPanel.memo.test.tsx` 的計次探針**(兩種模式各讀一半) |

| # | 既有行為 | 守住的方式 |
|---|---|---|
| W1 | `dropTargetFromPointer` 五參數以下的行為**位元不變**(x 界 / 最近 zone / 折疊 append / sticky 作廢帶) | 既有 9 案不改,新增「未傳 voidAboveY → 位元不變」一案 |
| W2 | 自選寫入的**零 PUT 早退**(深度比對):內容相同的 PUT 會讓後端重設整個訂閱池(TC4 全量 UNSUB/SUB) | 判定搬進 hook,`isSameWatchlist` 邏輯逐字不變;既有 dedup 測試(連點兩次刪除)不改 |
| W3 | 佇列既有四條契約:序列化 / 逐發 `onDone` 不被吞 / 失敗世代短路 / chain 尾恆 fulfilled | 既有「連續操作」四案不改,全綠 |
| W4 | 「自選未載入成功 → 不以空殼為基底 PUT」(側欄 `wlReady` gate + StockPage `canAdd` gate) | gate 保留,佇列再加一道 `base === null → 早退` |
| W5 | `CapitalConfirmDialog`:unmount 零 callback、Esc/close 只發一次 onCancel、StrictMode showModal 恰一次 | 既有 16 案不改;N114 只加 dev-only 警告,不動任何 callback 次序 |
| W6 | 折數:非法值只更新 raw、計算沿用上一個合法值、localStorage 字面 key、多讀者同 tick 同數字 | 既有 6 案不改;raw 的本地 state 語意保留(只多一條「外部改動才覆寫」) |
| W7 | 個股期 / 期貨梯的送單 payload、武裝解除鍵、活單徽章、平倉對象比對 | 不碰;N083 只把 throw 換成既有的 `contract = null` 安全態 |
| W8 | 訊號規則 params 鍵集必須與後端 `PARAM_SPECS` **完全相同**(多鍵 / 缺鍵 = INVALID_RULE) | 鍵集零改;只加 `min`/`max` 兩個顯示 / 檢查用欄位 |
| W9 | 江波圖重疊模式的畫面輸出(七腿線 / 腿名避讓 / 刻度 / 讀值列 / 十字線)逐值不變 | N030 是純搬家(render body → 既有 useMemo),`RiverPanel.test.tsx` 幾何數字案不改 |
| W10 | `capital-positions` 的 WS 事件 invalidate(200 ms trailing debounce、多處掛載單發) | 既有 5 案不改;N068 只動 `refetchInterval` 的擁有者 |

## 1. 逐條處置

### N055 — 規則參數值域前端也擋(🔴 前端 + 🟢 後端測試)
`ParamField` 加 `min`/`max`(值取自後端 `PARAM_SPECS`),input 帶 `min`/`max`,送出前逐欄檢查
閉區間並給**指名文案**(`${label}須在 ${min}–${max} 之間`,沿冷卻秒數既有句型)。
「連 rearm_ticks / window_secs 一起加」是條文的拍板方向,故四個 kind 全表補齊。
**重抄一份會漂**是既有註解拒做的理由 —— 本輪以**共用 fixture** 消化:
`tests/fixtures/signal_param_specs.json` 為唯一真相,pytest
(`test_param_specs_parity_with_frontend`)與前端(`lib/signal-param-parity.test.ts`)各自對它斷言。
表同時自 `SignalRulesDialog.tsx` 搬到 `lib/signal-params.ts`(元件檔只放元件;parity 測試也不必掛載 Dialog)。
事前標「該變」:無(既有 assertion 全不動)。

### N030 — RiverOverlay hover 收斂(🔵 前端)
`timeTicks(win)` 與七條 polyline 的 `points` 字串移入既有的幾何 `useMemo`(deps 同為
`[entries, win]`);`strokeWidth` 依賴 `baseKey` 故留在 JSX(一次字串比對 << 一輪幾何)。
`toX` 留在外面只服務十字線(唯一依賴 cursor 的座標)。**零畫面差異**。
**探針換手**(條文明列):`timeTicks` 原本是「重疊圖 render body 跑幾次」的計次探針,收進 memo 後
那個位置沒有東西可數 → 改用 `vi.mock` 包住 `RiverOverlay` **元件本體**計 render 次數
(直呼 `actual.RiverOverlay(props)` 而非 `<actual.RiverOverlay/>` —— 後者的 cursor state 住在子 fiber,
mousemove 不會讓 wrapper 重繪,計次會假 0)。
事前標「該變」:`RiverPanel.memo.test.tsx`「重疊圖:游標滑過三個分鐘」的
`expect(hoisted.ticks - beforeRender).toBe(3)` → 探針換成 `overlayRenders` 的 `toBe(3)`,
並新增 `ticks`/`pts` 的 `toBe(0)`(收斂目標)+ 掛載自檢 `toBeGreaterThan(0)`(防 vacuous)。

### N064 — 個股期均價字面統一 `fmt`(🔴 前端)
`StkfutLadder` 部位列 `p.avg_price.toFixed(2)` → `fmt(Math.round(p.avg_price * 1000))`,與 header /
自選 chip / `PriceLadder` 部位條同一個口徑(條文建議「ladder 改 fmt」)。
`CapitalPositionsList` 的 `toFixed(2)` **不動** —— 那是表格欄位(對齊靠固定小數位),不是同一畫面上的同一筆數字。
事前標「該變」:`StkfutLadder.test.tsx`「只收本合約的期貨部位」的 `@100.00` → `@100`(值斷言,條文已標紅)。

### N067 — 折數跨分頁(🟢 驗收 + 🔴 前端)
(a) `subscribe` 的 `storage` listener 補一條 lock(`fee-discount.test.ts`),mutation 驗過。
(b) `PriceLadder` 折數框自持 `useState(loadDiscount)`(只在掛載讀一次)→ 改吃共用 store。
輸入框的 `raw` 仍是本地 state(store 只存得下合法 number),同步**單向**:外部值變了才覆寫 raw,
判別子 `lastWrite`。邏輯收在 `lib/fee-discount.ts::useFeeDiscountField`(順帶讓 PriceLadder 主體
不越過 react-doctor `no-giant-component` 門檻)。
事前標「該變」:無(既有 6 案全綠)。

### N068 — 部位輪詢單一 provider(🔴 前端)
`useCapitalPositions` 的 `refetchInterval` 移除(改 `false`),節奏移到 `useCapitalStream`
(App 層掛一次的既有唯一擁有者)內的同 key query。
**代價(明示)**:provider 不在場時 `useCapitalPositions` 只有掛載那一發 + WS invalidate,不再輪詢
—— prod 由 App 保證在場;元件級測試不依賴輪詢。
事前標「該變」:無。

### N083 — FuturesLadder `futExchangeContract` 補 try/catch(🔴 前端)
render body 上的 throw = 整個期貨頁白屏(另外三處 caller 早已各自 try)。`contract = null` 是既有安全態。
`let` 宣告與首個賦值同一次 Edit 帶齊(formatter prefer-const 陷阱)。

### N097 — 側欄下緣作廢帶(🔴 前端)
`dropTargetFromPointer` 增第六參數 `voidAboveY`(`y > voidAboveY` → null);`zonesNow` 以
「最後一個 section 的 bottom + 一列 `ROW_H` 容差」算界。容差是刻意的:貼著最後一列下緣放開
= append 到該組尾,那是既有且要保留的落點。S 級,與 `voidBelowY` 完全鏡像。

### N115 — 撞名判定搬進 transform(🔴 前端)
`WatchlistTransform` 回傳 `Watchlist | null`,`null` = 套用當下被拒 → 佇列回報 `BAD_GROUP`。
`submitAddGroup` / `submitRename` 的 eager 檢查**降級為純 UX**(決定「要不要清輸入框」與即時回饋),
權威判定在 transform。偽陰性(佇列視窗內交錯)現在有文案,不再是「零 PUT + 輸入框已清空 = 看似成功」。
**注意**:`null` 只保留給撞名;「無事可做」(排序按到界上 / 組已被刪)一律回 `base` 自身走既有零 PUT 早退,
否則排序按到底會噴出「群組名稱不合法」。

### N117 — 佇列上提到 hook(🔴 前端)
新檔 `hooks/useWatchlistCommit.ts`:module 層單例佇列(chain / base / pending / gen),三個 caller 共用。
- 基底同步沿用既有 `useLayoutEffect + pending 守門`(review C-2 的結論不變),多一個 `seed`(Dialog 的 `wl` prop)
  當「query data 尚未到」的後備。
- **實例數 0 → 1 時整份重置**(換整個物件,飛在半空的舊動作只改舊物件):沒有寫入者在場時繼承殘餘沒有意義,
  在測試環境裡繼承它就是跨檔互污。宣告順序上重置排在基底同步之前(否則首個動作靜默零 PUT)。
- **錯誤文案歸呼叫端**(`onError(code | null)`):三個 caller 的錯誤長在不同位置,且各有自己的 eager 錯誤要共用同一個槽。
- 側欄 `applyDrop` / 加入群組 / 移除,與 StockPage `addTo` 全部改吃 transform 的 `base` 參數(不再是 render 閉包的 `wl`)。
事前標「該變」:無(既有 100 + 45 + StockPage 案全綠)。

### N114 — CapitalConfirmDialog caller 契約機械防護(🔴 前端,dev-only)
形式判定與理由:**dev-only `console.error` + macrotask 檢查**,不 throw、不重置 `closedRef`。
- 不 throw:把一個 UI 契約瑕疵升級成真錢流程中斷,代價不對等。
- 不重置 `closedRef`:那正是「settled 之後不再補發 onCancel」的安全語意本體(堵「送單後按 Esc → UI 誤導成已取消」)。
- 檢查點在 macrotask:React 由事件處理器觸發的卸載在同一 task 內 flush 完,正確的 caller 到期前已 unmount,
  effect cleanup 順手清掉計時器 → 零誤報(四個 caller 逐一讀過,皆同步 setState 卸載)。

### N116 — unmount-after-PUT 仍清 `WL_COLLAPSED_KEY`(🟢 純測試)
條文已拍板採「不漏清」語意,故本條只補 lock:PUT 在途時卸載側欄 → 回應到達後折疊孤兒仍被清掉。
與 `CapitalConfirmDialog` 的「unmount 零 callback」語意刻意相反(真錢下單 vs 冪等 localStorage 清理),
兩條 lock 並存,註解互相指名,誰也不許被「統一」。

### N118 — 佇列交錯覆蓋其餘兩類(🟢 純測試)
補三條:刪組+改名交錯、刪組+移除股交錯、失敗短路後新動作以未推進基底重算(換動作型別,避免與既有案同義反覆)。
「加股 + 刪組交錯」走不到:建議列在 `isPending` 期間停用(review F1),已在測試註解申報。

### N266 — 管理 Dialog 內上移 / 下移(🟢 前端新功能)
user 顯式勾選的 a11y 例外(其餘 a11y 通則不做)。右欄每列加 ▲/▼,界上停用。
`slot` 用 `insertAt` 的既有契約:上移 `i−1`、下移 `i+2`(補償後落 `i+1`);群組走
`moveToGroup(base, code, g, g, slot)`(`from === to` 退化為同組排序,W-19),未分組走 `reorderUngrouped`。

## 2. Backward compat / migration
- 無資料格式改動、無持久化格式改動、無 API 契約改動;`.py` 只動測試(新增一條 parity 斷言)。
- 新增跨檔契約一條:`tests/fixtures/signal_param_specs.json`(前後端各自斷言,改壞任一邊只有那一邊紅)。
- 可逆 = revert 本分支;`useWatchlistCommit` 是新檔,三個 caller 的舊寫法在 git 歷史內。

## 3. 測試 seams(皆為真 caller 走的 seam)
- 純函式:`lib/list-drag.test.ts`(N097)、`lib/signal-param-parity.test.ts`(N055 parity)。
- hook:`hooks/useCapital.test.tsx`(N068)、`lib/fee-discount.test.ts`(N067a)。
- 元件:`WatchlistManagerDialog.test.tsx`(N115 / N118 / N266)、`WatchlistSidebar.test.tsx`(N097 元件層 / N116 / N117)、
  `PriceLadder.test.tsx`(N067b)、`StkfutLadder.test.tsx`(N064)、`FuturesLadder.test.tsx`(N083)、
  `SignalRulesDialog.test.tsx`(N055)、`CapitalConfirmDialog.test.tsx`(N114)、`RiverPanel.memo.test.tsx`(N030)。
- 後端:`tests/test_signal_rules.py::TestConstants`(N055 parity)。
