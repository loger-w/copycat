# repro — WatchlistManagerDialog 連續操作吞 callback

分流判定:規格來自 user 拍板文件(`docs/next-time.md` 2026-08-11「mod/react-doctor-p1
review 發現」節第一條)→ 預核准,方向性抉擇無;修法兩案擇一屬實作選擇(見下)。

## 症狀(spec 依據)

Dialog 只有一顆 `useSaveWatchlist` mutation observer;`commit()`
(`WatchlistManagerDialog.tsx:82-89`)用 `save.mutate(next, { onSuccess: onDone })` 傳
**per-call callbacks**。TanStack Query v5 契約:per-call callbacks 只對「該 observer 最新
一次 mutate」執行 —— 第二發 `mutate` 覆蓋之,第一發的 `onSuccess` 不執行。

後果(連刪兩組,第二刪在第一發 PUT 未回前發出):
- (a) 只有第二發的 `onGroupDeleted` 執行 → 第一組組名殘留側欄 `WL_COLLAPSED_KEY`
  (W-20 復發:日後建同名群組意外呈折疊)。
- (b) 第二發 `commit` 以 render 閉包的 stale `wl`(cache 未更新)計算
  `deleteGroup(wl, 第二組)` → PUT body 仍含第一組 → 後端 last-write-wins 把第一組還原。

## 最小重現(loop)

紅測試:`WatchlistManagerDialog.test.tsx` →
`describe("連續操作(pre-existing 吞 callback bug)")`,PUT 以 deferred gate 卡住模擬
在途視窗,連點「刪除群組 觀察」「刪除群組 主力」:

- 斷言 1(a):`onGroupDeleted` 兩發皆執行(順序 觀察 → 主力)。
- 斷言 2(b):最後一發 PUT 的 groups 為 `[]`(不得把「觀察」還原回去)。

實跑紅證據(2026-08-11,修復前):
- (b) `AssertionError: expected [ { name: '觀察', codes: [ '2330' ] } ] to deeply equal []`
  — 第二發 PUT body 把已刪的「觀察」原樣還原。
- (a) `expect(onGroupDeleted).toHaveBeenCalledTimes(2)` waitFor timeout — 實際只有 1 次
  (第二發的「主力」;第一發 per-call callback 被覆蓋)。
- 同檔既有 32 條全綠(症狀只在連續操作窗內,單發行為不受影響)。

## Root cause

單一 mutation observer + per-call callbacks + stale 閉包基底,兩個獨立缺陷同一觸發窗:

1. callback 吞沒:TQ v5 documented behavior(per-call callbacks 只 fire 最新 mutate)。
2. stale 基底:`commit` 的 next 一律由 render 閉包 `wl` 計算;PUT 在途時 cache 未更新,
   第二個動作以「不含第一個動作結果」的基底計算。

證據:`WatchlistSidebar.dropcollapsed.test.tsx` 檔頭註解(2026-08-11 實測:真實 UI 連刪
兩組只走到一次 `dropCollapsed`,該 lock test 因此以 stub 打契約)。

## 修法

[auto-default: per-action `mutateAsync` + 串行佇列(transform 以最新基底重算)
| reason: 兩案(per-action mutateAsync / mutation callbacks 去 per-call 化)中,後者只解
(a) callback 吞沒,(b) stale 基底仍需另補序列化;前者以一條 promise chain 同時解掉兩者:
每個動作改傳 `(base) => next` transform,輪到時以「最新已知內容」(上一發 PUT 回應)重算,
`mutateAsync` 的 per-call promise 不受後續呼叫覆蓋 → onDone 逐發執行。且不犧牲 UX
(不必為序列化把所有動作鈕 disable)。]

範圍:僅 `WatchlistManagerDialog.tsx` 的 `commit()` 與其 6 個呼叫點(全在同檔)。
`useSaveWatchlist` 本體不動。

## Blast radius(useSaveWatchlist 所有 caller)

- `WatchlistManagerDialog.tsx` — 本次修改目標。
- `WatchlistSidebar.tsx:112-115` — `commit` 不帶 per-call callback、單發事件路徑
  (拖曳 / 移除),無同 tick 連發來源;不動。
- `StockPage.tsx:84,111-116` — 同上,且已以 `save.isPending` disable 防重複;不動。
- `useStockWatchlist.test.tsx` / 既有 Dialog 測試 — 行為白名單,見下。

## 不能破壞的既有行為白名單(既有測試為合約)

- W-9 零 PUT 早退:內容相同不送 PUT(深度比對)。
- F1:PUT pending 期間建議列 `save.isPending` 停用、重複點擊只送一筆。
- W-3:PUT 失敗 → 錯誤文案、不呼叫 `onGroupDeleted`、UI 不先跳。
- 單發刪組:PUT 不含該組、成員留 codes、`onGroupDeleted(name)`。
- BAD_GROUP 前端擋(撞名 / 保留名 / 空白)零 PUT + 文案。
- 開關重置、derived selected、m-auto / display class 契約(同檔其他 describe)。

驗證方式:`npm test`(整檔既有測試全綠)+ `npx tsc -b` + `npx eslint src` +
react-doctor --scope changed 零新增。

## 驗證結果(2026-08-11)

- 紅測試轉綠:Dialog 測試檔 34/34(新增 2 + 既有 32)。
- 全量:`npm test` 110 檔 / **1724 passed**(baseline 1722 + 2);`npx tsc -b` exit 0;
  `npx eslint src` exit 0。
- react-doctor `--scope changed`:第一輪 1 新增 finding(`rerender-lazy-ref-init`,
  chainRef 每 render 配置 promise)→ 真 finding,改 lazy init 修掉 → 第二輪 **No issues
  found**(零新增)。
- **反向驗證**:`git revert --no-commit aa1156d2 8b71ab8d` → 兩條新測試紅回來
  (2 failed)→ `git reset --hard HEAD` 還原 → 34/34 綠。測試確實抓得住 bug。

## Commits

- `d318650f` 🔴 test [red] — 紅測試兩條
- `8b71ab8d` 🔴 fix [green] — commit() 串行佇列(red→green for d318650f)
- `aa1156d2` 🔵 refactor — chainRef lazy init(doctor finding 修掉)
