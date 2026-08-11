# 現況盤點 — CapitalConfirmDialog 換原生 dialog

來源:`docs/research/2026-08-11-react-doctor-triage.md` §一「中價值,單獨拍板」(user 已拍板執行)。

## 現有實作(frontend/src/components/capital/CapitalConfirmDialog.tsx,78 行)

- `div role="dialog" aria-modal="true" aria-label={title}` 手刻 modal:
  外層 `fixed inset-0 z-50 flex items-center justify-center bg-bg/85 p-4` 當遮罩 + 置中,
  內層 `w-full max-w-sm border border-line bg-bg-deep` 當盒子。
- Props:`{ title, rows: ReadonlyArray<ConfirmRow>, danger?, onConfirm, onCancel }` —
  **沒有 `open` prop**。
- 標題列:danger 時 `bg-loss` 紅底 + 「正式」字樣;rows 走 `<dl>`;按鈕列 = 取消(左)+
  確認(右,danger 紅框 / 平常 accent 框)。
- **缺**:focus trap、初始 focus、Esc 取消、背景 inert(react-doctor
  prefer-html-dialog finding,triage 判 TP)。

## Caller map(grep `CapitalConfirmDialog`,含測試共 6 檔;無動態用法 — 元件名僅
JSX 直呼,無字串引用 / lazy import)

| Caller | 掛載條件 | onCancel 行為 |
|---|---|---|
| `OrderPanel.tsx:283` | `confirming && premium != null` | `setConfirming(false)` |
| `CapitalOrdersList.tsx:208`(**每列 li 內**) | `pending !== null` | `setPending(null)` |
| `CapitalPositionsList.tsx:110` | `closing !== undefined && estimate !== null` | `setClosingKey(null)` |
| `FuturesLadder.tsx:458` | `closeOpen && !closeDisabled`(含**自動收窗**:行情斷 → 條件轉假 unmount) | `setCloseOpen(false)` |

**共同契約:條件掛載 = 開啟,unmount = 關閉;4 個 onCancel 全是冪等 setState。**
另 next-time 2026-08-05 節已記:OrderPanel 的 `premium != null` gate 會讓已開確認框
靜默卸載(Known Risk,獨立輪處理)— 本輪維持條件掛載即不碰該行為。

## 既有測試(CapitalConfirmDialog.test.tsx,2 支 = 行為白名單)

1. 渲染標題/明細列/確認/取消 + 點擊觸發 callbacks(`getByRole("dialog")`)
2. danger 標題列紅底 bg-loss,預設無

## repo 樣板(WatchlistManagerDialog.tsx:33-78、236-268;SignalRulesDialog 同款)

- showModal 只走 effect,`open` **不進 JSX**(commit 的 open 屬性讓 showModal 拋
  InvalidStateError;jsdom 無 showModal → feature-detect fallback 手動 set/remove
  `open` attribute)。
- 原生 close 事件必拉回 prop(`onClose={() => { if (open) onClose(); }}`)。
- `m-auto` 抵 Tailwind preflight `margin:0`;display class 由 open 狀態選,
  不寫死(UA 的 `dialog:not([open]){display:none}` 是瀏覽器層,author 層 `flex` 會勝出
  → 關閉的 dialog 佔版面,2026-07-31 實證)。
- Esc 走 onKeyDown 顯式處理(jsdom 無原生 Esc 行為,測得到)。

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 元素 | `div role="dialog"` | `<dialog>` + `showModal()` |
| focus trap | 無(Tab 可跑到背景) | 原生 modal 提供 |
| 初始 focus | 無(停留在觸發鈕) | 落在「取消」鈕 |
| Esc | 無反應 | = 取消(觸發 onCancel,絕不可能送單) |
| 背景 | 只有視覺遮罩,仍可 focus | 原生 inert(不可點不可 focus) |
| 遮罩 | 外層 div `bg-bg/85` | `backdrop:bg-bg/85` |
| Props/caller 契約 | 條件掛載、無 open prop | **不變**(caller 零改動) |
| backward compat | — | props 介面不變 → 無 migration;可逆 = revert 單檔 |
