# R3 個股串流/顯示雜項批(`mod/stream-ui-misc`)— change spec

來源:`docs/superpowers/specs/2026-08-24-do-batch-rounds.md` §R3(十條)。
User 附註:**N008 顯示載入中時 UI 不得跑版,排版要固定**;**N013 拍板不改合併行為,只補註解 / 標記 / clamp**。

## 0. 既有行為白名單(不可破壞;優先於本輪新行為)

| # | 既有行為 | 守住的方式 |
|---|---|---|
| W1 | TickTape 前插時既有列 DOM node 恆等(不卸載重掛) | `TickTape.test.tsx` 既有恆等案不改,新增滿載案 |
| W2 | `fromSnapshot` 的 `ticks` 上限 200、VP 折**全量**(不受 200 影響) | `stock-accum.test.ts` 既有案不改 |
| W3 | RadioPills 點已選中項也發 `onInteract`;停用項不發;`onChange` 語意不變 | 既有案不改,只把 `toHaveBeenCalled` 收緊成 `toHaveBeenCalledTimes(1)` |
| W4 | 重疊圖兩腿都有 ref 時的線色 / 標籤 / 幾何逐值不變 | `index-chart-svg.test.ts` 既有案不改 |
| W5 | `useBreadth` / `useIndexStream` 的 merge 契約(scalar 覆寫 / last_minute upsert / 換日清空 + refetch) | 既有案全數不改 |
| W6 | TXO / 個股 / 期貨 / 指數四態分時圖的 toggle 列版面(高度、顆數、class) | N008 只換 label 文字,class 逐字不變 |
| W7 | toast 文案內容與 5s TTL / 合併行為 | N013 只加 clamp class,不動 hook 邏輯 |
| W8 | StockPage「伺服器連線中斷,重連中…」(wsStatus closed)文案 | 只改 `tc4 === "down"` 那一支 |

## 1. 逐條處置

### N008 — VP 佔位(🔴 顯示)
`accum.tapeOmitted`(群組 `?tape=0` → 切回單檔、全量補打中)時,分時圖 toggle 列的
**「量分佈」鈕改印「載入中」**(spec 原文:「讓 VP toggle 區印載入中」)。
- **不跑版**:同一顆 button、class 逐字不變、`disabled`/`aria-pressed` 不變,兩個 label
  同為 3 個全形字 → box 尺寸不變。測試鎖「兩態 className 相同」。
- 只在現貨 / 期貨(有 VP)態成立;`tapeOmitted` 在 index / futures / group adapter 恆 false。

### N120 — TickTape key 穩定序號(🔴 內部資料形狀)
`TickRow` 新增 `n`(單調序號),兩入口一致產生:
- `fromSnapshot`:自 `snap.seq` **由尾回推**(`n = seq - (len-1-i)`)
- `applyTick`:新列取 `msg.seq`
key 改 `t.n`。滿載(`TAPE_MAX=200`)丟頭時既有列 `n` 不變 → DOM node 恆等。
線上形狀拆出 `WireTickRow`(後端不發 `n`),`TickRow = WireTickRow + n`。

### N121 — StockChart `spotMode`(🔵 記錄性)
確認:`StockPage` 的 `{accum ? …}` gate 仍在,換合約時 `useStockStream` 先 `setAccum(null)`
→ StockChart **卸載重掛** → `spotMode` 歸零、`initialMode()` 由 localStorage 還原。
**判定:不刪**(記載自己的前提是「先看 StockChart 是否已脫離 accum gate」,現在沒有)。
處置 = 註解寫清楚「prod 由 localStorage 兌現 / spotMode 只在 same-instance 路徑有讀者」
+ 在 `StockPage.test.tsx` 鎖住前提(accum null → 圖表不掛)。

### N119 — 兩支 hook 的 ref 同 tick 回寫(🔴 自癒型)
`useIndexStream` / `useBreadth` 的 handler 改 **imperative 配對**(同 `useFuturesStream`):
自 ref 讀基底 → 算出 next → **當場寫 ref** → `setState(next)`。`refetch` 成功路徑同步寫 ref。
`useLayoutEffect` 保留為 commit 後的 backstop(涵蓋未來新增的 setState 路徑)。

### N109 — tc4 down 文案(🔴 文案)
`status.tc4 === "down"` 有兩個來源:engine 在但 TC4 斷(會自癒)/ XR-3 後**無 engine**
(TC4 從未開,恢復不自癒,要重啟 server)。前端**沒有可分辨的訊號**(seed 兩者同形,
`/api/health` 刻意不含引擎健康度),而後端加欄位屬 R3 外檔 → 本輪走「單句對兩態都誠實」:
「達錢 4 未連線 —— 連線後自動回補;若 server 啟動時未開,需重啟 server」。

### N108 — 櫃買(MIS)源中斷(🔴 文案)
MIS 從開盤即死透 → `otc.p/ref` 恆 null、`minutes` 恆空,且 otc **不吃 `stale`**(只有 twse 有
watchdog)→ 畫面靜默。前端自足判別子:**加權已有 ≥2 個分鐘格而櫃買一格都沒有 + `p === null`**
(盤前兩者皆空 → 不誤報;開盤前 2 分鐘給 MIS 5s poll 寬限)。櫃買 pane 的 figcaption 印
「櫃買快照源中斷」。不做後端回補來源。

### N262 — 重疊圖單邊 ref 缺值錯位(🔴 bug)
`buildOverlayGeometry` 的 `lines` 每筆帶回**原始 index**;`OverlayCard` 改用 `l.index` 取
`OVERLAY_LINES` → twse.ref 缺時僅存的櫃買線畫成櫃買色 / 標「櫃買」。

### N265 — RadioPills `onInteract` 雙觸發(🔴 bug)
label activation 會把 click 轉發到內層 input 再冒泡 → label 的 onClick 每次點擊跑兩次。
處置:handler **從 label 移到 input**(轉發 / 直接點 / 鍵盤選取皆恰一次),`disabled` guard 保留。

### N012 — 停用 pill 的 `cursor-not-allowed`(🔵 零行為)
判定:**保留** RadioPills 的 `cursor-not-allowed`(停用態的正確游標),StockChart 的
`pillClass` 不再另寫一份(視覺一致由共用元件提供)—— 於 StockChart 註解登記這條偏差已被接受,
並把 `RadioPills.test.tsx` 兩處 `onInteract` 斷言收緊為 `toHaveBeenCalledTimes(1)`(= N265 紅測)。

### N013 — toast 合併(🔵 註解 + 🔴 clamp)
user 拍板**不改合併行為**。處置:
1. `useSignalAlerts` 註解寫明「`groupIndexRef` 是 `code|time` 全索引,與 rail 的
   `groupSignals`(只看相鄰)不等價」及為何不改;
2. `signal-model.ts::formatToastText` 標明「prod 無讀者,只剩測試在用(與
   `formatGroupToastText` 的單則組輸出逐字相同的 lock)」;
3. `ToastStack.tsx` toast 文字比照 B3 加 `line-clamp-2 break-words`(合併文案過長時不無限撐高)。

## 2. Backward compat

- `TickRow.n` 是**前端指派**的欄位,線上形狀(`WireTickRow`)不變 → 後端零改動、舊 snapshot 照吃。
- `buildOverlayGeometry` 的回傳型別加欄位(`index`),既有欄位語意不變。
- 其餘皆為文案 / class / handler 掛點,無資料格式變更。

## 3. 不做(不擴 scope)

- 後端 status seed 加欄位(N109 的真分態)、MIS 回補來源(N108)、toast 合併改與 rail 一致(N013,user 拍板)。
- a11y 專項(user 2026-08-24 拍板不做)。
