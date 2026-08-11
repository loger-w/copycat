# current-state — useStockNames 錯誤態輪詢收斂

2026-08-11 /mod(S 級:單 hook 檔 + colocated 測試檔,無對外 API、無 migration)。
來源:`docs/next-time.md` 2026-08-10 節兩條 P2(useStockNames.ts:37 輪詢不退避;測試不鎖節奏/停止條件)。

## Caller map(grep `useStockNames`,含動態用法檢查)

| Caller | 用法 | error 態消費 |
|---|---|---|
| `frontend/src/components/stock/WatchlistSidebar.tsx:73` | `const { data: names = [] } = useStockNames()` | 無 |
| `frontend/src/components/stock/WatchlistManagerDialog.tsx:35` | 同上(`:35`) | 無 |
| `frontend/src/hooks/useStockNames.test.tsx` | 測試 | — |

無動態用法(字串拼 hook 名 / re-export 皆無)。**兩個 caller 都只讀 `data`(預設 `[]`),
無人讀 `error` / `isError`** — 證實 next-time P2「error 態無 consumer 在讀,註解與現實不符」
(useStockNames.ts:35 註解「error 態要能浮現(404 / 舊 build 的錯誤碼契約靠它)」與現實不符)。

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 輪詢條件 | `data === undefined` → 3s 輪詢,**含 error 終態 → 永久失敗時無限輪詢**(useStockNames.ts:37-38) | 連續失敗達上限後停止(拍板:停止,不是退避) |
| 啟動窗復原 | error 終態下 3s 輪詢 → server 起來後自動復原(測試 :58 鎖住) | **保留**(上限內行為不變) |
| 成功後停止 | `data !== undefined` → false | 不變 |
| 註解 | :35「error 態要能浮現…契約靠它」— 無 consumer,與現實不符 | 與現實對齊 |
| 測試 | interval 改 1ms / 停止條件拿掉皆全綠 | 白盒鎖 3000ms + 停止條件;fake-timer 整合鎖「停止後 fetch 次數不增」 |
| signature | `useStockNames(): UseQueryResult<StockName[]>` | 不變(新增具名 export 供白盒測試) |
| backward compat | — | caller 零影響(只動輪詢終止條件;無 migration) |

## 機制事實(TanStack Query v5)

- `query.state.errorUpdateCount`:每一輪 fetch cycle(含 retry:1 的兩次嘗試)以 error 收場時 +1,
  success 不重置(本 hook 用不到重置:一旦 success 即 data 永存,gcTime Infinity)。
  `fetchFailureCount` 不可用 — 每輪 refetch 由 retryer 以該輪次數覆寫,不跨輪累積。
- 停止輪詢後 `refetchOnWindowFocus`(預設 true、無資料的 query 恆 stale)仍是 refocus 復原後門 —
  即原註解描述的舊行為,作為停止後的 backstop 保留。
- 啟動窗背景:PR #20(2026-08-05 startup-http-window)後 uvicorn bind ≈ 0.037s,原「數十秒~分鐘級」
  連線被拒窗口已大幅縮小;3s 輪詢主要涵蓋「先開前端、後起 server」的本機流程。
