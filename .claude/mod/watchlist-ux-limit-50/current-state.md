# 現況盤點 — 自選清單 UX + 上限 50(mod/watchlist-ux-limit-50)

日期:2026-08-13。來源:user feedback backlog 第 4、7 條(memory `user-feedback-batch-2026-08-13`),
上限 50 已由 user 拍板。

## A. 三個子改動的現況

### A-1. 群組標題列 vs 個股列視覺(WatchlistSidebar.tsx)

- `sectionHeader()`(`frontend/src/components/stock/WatchlistSidebar.tsx:255-289`):
  整條是原生 `<button>`,class = `flex w-full items-center gap-1 border-b border-line px-1
  py-1 text-left` + `drag === null && "hover:bg-surface"` + focus-visible 底線。
  內容 = `▸/▾`(aria-hidden,`w-3 text-xs text-ink-dim`)+ 組名(`text-xs text-ink`,
  truncate)+ 計數(`font-mono text-[0.625rem] text-ink-dim`)。
- 個股列 `stockRow()`(291-454 行):`border-b border-line px-1` + 代號 `font-mono
  text-base text-ink` + 名稱 `text-xs text-ink-muted`。
- 問題:標題列與個股列同樣是 `border-b border-line` 白底(透明底),組名字級
  (text-xs)甚至比代號(text-base)小,掃視時混在一起。
- 可用 design token(`frontend/src/index.css` @theme):`bg` #0a0e14 / `bg-deep` #060910 /
  `surface` #10161f / `line` #1e2735 / `ink` / `ink-muted` / `ink-dim` / `accent` 等。
  `hover:bg-surface` 是全站「透明底可點項」的 hover 慣例;`bg-line` 目前僅用於分隔線
  (`h-3 w-px bg-line`),沒有當底色的先例。
- 既有測試:`WatchlistSidebar.test.tsx` 對 header 有 aria-expanded / aria-controls /
  StrictMode 持久化 / 拖曳中不觸發 toggle 等行為測試;**無 class 樣式斷言**。
  `WatchlistSidebar.dropcollapsed.test.tsx` 鎖刪組清折疊。

### A-2. 全部展開/收合(WatchlistSidebar.tsx)

- 逐群組折疊:`collapsed: Set<string>`(state)+ `collapsedRef`(imperative 影子)。
  **單一寫入點 `applyCollapsed(next)`**(119-126 行):同步 ref → `persistCollapsed`
  (localStorage `WL_COLLAPSED_KEY` = JSON string[])→ setState,三步成對是既有不變式
  (review TC-4;StrictMode double-invoke / mutation 回呼同批連發的防線)。
- 未分組獨立 boolean:`ungroupedCollapsed` state,`toggleUngroupedCollapsed()`(137-141)
  直接寫 localStorage `WL_UNGROUPED_KEY`("1"/"0")+ setState;**無 ref 影子**(僅純點擊
  路徑,宣告處註解已說明為何不需要)。
- 兩把 key 都在 `frontend/src/lib/constants.ts:92-94`。
- 現況**沒有任何**「全部展開/收合」入口;`dropCollapsed(name)` 是刪組回呼(走 ref)。
- 折疊狀態的讀者:render(526、547 行)+ `zonesNow()` 拖曳幾何(180 行,讀 render 閉包
  的 `collapsed` / `ungroupedCollapsed`)。

### A-3. 上限 30 的分佈(caller map)

**常數定義(單一來源)**:`copycat/stock_watchlist.py:37` `WATCHLIST_LIMIT = 30`。

**引用(import,改常數即生效)**:
- `copycat/stock_watchlist.py:118` `normalize()` 超限 raise `WatchlistError("WATCHLIST_FULL")`
  —— PUT /api/stock/watchlist、Discord bot、WatchlistService 全走這裡。
- `copycat/server/app.py:65,1227` `/api/stock/group-state` 數量閘(超限 → 400 `BAD_CODES`)。
- 測試(參數化,自動跟隨):`tests/test_stock_watchlist.py`、`tests/server/test_watchlist_service.py`。

**硬編字面值(改常數不會跟著動)**:
- `copycat/server/discord_bot.py:58` `_ERROR_TEXT["WATCHLIST_FULL"] = "自選已達 30 檔上限"`。
- `frontend/src/hooks/useStockWatchlist.ts:27` `errText`:`"自選已達 30 檔上限"`(側欄與
  管理 Dialog 共用單一份 — 檔內註解明言跨檔契約 W-2)。前端**沒有** WATCHLIST_LIMIT 常數。
- 測試硬編(改 50 後**該紅**):
  - `tests/server/test_stock_routes.py:201`(PUT 31 檔期望 400)
  - `tests/server/test_stock_routes.py:508,545`(group-state 31 碼期望 400)
  - `tests/server/test_discord_bot.py:173`(文案 "30 檔上限")
  - `frontend/src/components/stock/WatchlistSidebar.test.tsx:574`、
    `frontend/src/components/stock/StockPage.test.tsx:489`(文案)
- 測試硬編但**不受影響(不紅)、然而上限 50 下 vacuous 化**:`test_stock_routes.py:535`
  (31 個重複碼去重後 1 檔,恆 200 — 但 31 < 51 使「先驗後去重」的迴歸不再被抓)→
  參數化 `WATCHLIST_LIMIT + 1` 恢復鑑別力 [amendment 2026-08-13: R3]。
- 註解硬編(敘述性,同步更新):`frontend/src/hooks/useGroupSnapshots.ts:10,13,52`、
  `frontend/src/components/stock/GroupGridView.tsx:80,187`、
  `tests/server/test_stock_routes.py:508` 行尾註解 [amendment 2026-08-13: R5]。

**動態用法**:grep `WATCHLIST_LIMIT` / `30 檔` / `上限 30` 全庫掃過,無字串拼 key、無
反射取值。`tests/server/test_signal_hub.py:727-740` 的「30/分」是 **Discord 節流常數**
(`_MAX_PER_MIN`,signal hub),與自選上限無關,**不動**。

## B. 以 30 為前提的效能假設盤點(50 檔安全性)

| # | 位置 | 假設 | 50 檔評估 |
|---|---|---|---|
| B-1 | `stock_engine.py:1255-1261` `stream()` + `ws.py` per-client 佇列 | (a) 連線種子一次送全自選 payload,「30 檔對 queue maxsize(_CLIENT_QUEUE_MAX=1000)安全」;(b) 穩態:HR-6(next-time.md:1033)明文「佇列 1000 按 30 檔自選推的」,flush loop 每秒最多 N 則 + 試撮翻轉補推 N 則 + 廣度/signal 事件共用同一顆 stock_ws | (a) 種子 50 << 1000,安全;(b) 滿速 50 則/s 下 1000 槽 ≈ 20s 緩衝(30 檔時 ≈ 33s),慢連線 drop-oldest 風險略升但仍屬 HR-6 既有議題範圍,不調參;next-time:1033 數字重述 [amendment 2026-08-13: R6] |
| B-2 | `stock_engine.py:559-611` `group_snapshot` | 每 60s × N 檔 light_snapshot(minutes ≤271 + meta,無 ticks) | 50 × light payload 仍輕;docstring 數字更新 |
| B-3 | `stock_state.py:202`、`bars.py:243`、`app.py:1208` | 同 B-2 的敘述性引用 / cache 成長受上限約束 | 上限仍有界(50),註解數字更新 |
| B-4 | `app.py:483-485` boot 還原 `set_watchlist` | TC4 離線時每檔 SUBQUOTE 等 `_REQ_TIMEOUT_MS` 10s 才失敗:30×10s=300s → **50×10s=500s**,拖慢背景 boot 序列(stock 之後的 signals/index/capital/futures/corr/breadth 順序啟動,尤其 breadth 純 FinMind 卻被排在後面) | 既有已知缺口(`docs/next-time.md:408` 已記)。PR #20 後 boot 在背景 task,HTTP 0.037s 可用不受影響;`_retry_subscribe_loop` 會自癒。**不在本輪修結構**,更新 next-time 數字並保留為 known risk |
| B-5 | `app.py:520-529` engine 缺席時 signal worker | `basis_gap_secs` 已設 0.0(註解:否則 30 檔 6s 空轉) | engine 缺席分支 gap=0 已根治,50 檔只是註解數字(6s→10s)更新;engine 在場分支見 B-9 |
| B-9 | `signal_hub.py:566-589` `_basis_worker`(engine 在場) | 自選變更 / 啟動 / rollover 逐檔一次 TC4 日 K 往返 + `basis_gap_secs` 0.2s(與主圖回補 / K 線 route 共用 stock session) | 50 檔一批 ≈ 50 ×(往返 + 0.2s)≈ 15-30s,較 30 檔 ×1.67;觸發是低頻事件(非輪詢),gap 存在的目的就是讓位,批次拉長不阻塞主圖(逐檔 sleep 間讓出)→ 0.2s 不調 [amendment 2026-08-13: R4] |
| B-6 | `set_watchlist` PUT 路徑(`stock_engine.py:397-420`) | TC4 故障時單次 set_watchlist 最壞 N×10s 佔 `_pool_lock`(service 鎖已移出,X-3) | 300s→500s,同 B-4 同構的既有降級路徑,`_retry_round` 每段短鎖已是解;known risk 數字更新 |
| B-7 | 前端 `GroupGridView` / `MiniIntradayChart` | 幾何 271 分鐘 × 最多 N 卡,已 memo | 50 卡仍輕(註解為敘述,不動行為) |
| B-8 | TC4 訂閱檔數 | 無已知官方上限;`spikes/txo_chain_probe.py` 整鏈訂閱 ≥30 檔已有先例 | 風險低;真實環境驗證時觀察 |

## C. Backward compat / migration

- 30→50 是**放寬**:所有既存自選檔(≤30 檔)天然合法,零 migration。
- 可逆性:若回退 50→30,已存 >30 檔的檔案會在下次 PUT 時 `WATCHLIST_FULL`(讀路徑
  `load_watchlist` 不驗上限,仍可讀可看)—— 與 discord-watchlist design.md:190 記載的
  「可讀但不可 normalize」既有語意一致,非新風險。
- localStorage 兩把 key 語意不變(全部展開/收合只是批次寫既有結構),零 migration。
