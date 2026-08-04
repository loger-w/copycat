# repro:自選載入失敗時 WatchlistManagerDialog 以 EMPTY_WL 為基底整份 PUT,清空真實自選

## Phase 1|重現 + 蒐證

### 最小重現步驟(對應 unit test;真實場景 = server 短暫不可用後恢復)

1. `GET /api/stock/watchlist` 失敗(500 / 網路錯,retry 1 次後 query 進 error 態,`data === undefined`)。
2. `WatchlistSidebar` 以 `wl = data ?? EMPTY_WL`(`WatchlistSidebar.tsx:73`)渲染:
   顯示「自選清單載入失敗」,但**「管理」鈕照樣渲染**(:552-559)且把 `EMPTY_WL` 傳進
   `WatchlistManagerDialog`(:560-565)。
3. 使用者開 Dialog → 輸入群組名 → 「新增群組」:
   `addGroup(EMPTY_WL, name)` → `commit(next)`(`WatchlistManagerDialog.tsx:98,104`)→
   守衛 `isSameWatchlist(next, wl)` 比的是 EMPTY_WL 自身 → 不等 → `save.mutate` →
   **`PUT {codes: [], groups: [{name, codes: []}]}`**。
4. 後端 `PUT /api/stock/watchlist` 為**整份取代、無樂觀鎖**(`app.py:618-630`)→
   真實自選(最多 30 檔 + 全部群組)被空清單覆蓋。此時 server 已恢復,PUT 成功。
   另一路:「加入股票」(:136-144)→ PUT 成只剩單檔,同樣清掉其餘全部。

### 蒐證(2026-08-04 逐行核對)

- 原記載(next-time K-3)說破口在側欄三入口(拖曳 / × / 加入群組)—— **不成立**:
  三者都渲染自 `wl` 派生的列,EMPTY_WL 下零列,入口實際不可達。
- 真破口 = Dialog 的「新增群組」與「加入股票」:兩者**不依賴既有列**,空清單上也能操作。
- 同類問題 StockPage 已修過(`StockPage.tsx:68` `canAdd = wl !== undefined && …`;
  測試 `StockPage.test.tsx:407`「自選尚未載入 → 按鈕不渲染」)—— 側欄的「管理」入口漏掉同款 gate。

### 影響範圍 / 嚴重度

- 資料遺失(watchlist 檔整份覆蓋),且**靜默**:使用者以為在新增群組,實際清掉全部自選。
- 訂閱池連帶重設(整份名單 UNSUB/SUB)。
- 觸發條件窄(載入失敗後、未重整前於 Dialog 內 mutation)但後果不可逆 → P1。

## Phase 2|Root cause

`EMPTY_WL` fallback 把「尚未載入 / 載入失敗」與「真的是空自選」兩個狀態混為同一個值,
而「管理」入口未依載入狀態 gate → Dialog 拿 fallback 當真實狀態做整份取代的 PUT。
commit 守衛 `isSameWatchlist(next, wl)` 的比較基準就是 fallback 自身,對此無保護力。

- 驗證方式:紅測試鎖**入口**(query error / pending 兩態,斷言「管理」鈕與 Dialog 元素
  皆不渲染 → 重現鏈第 3 步「開 Dialog」不可達)。一次一變數:僅 stub GET 失敗,其餘與
  正常流程相同。清空 PUT 的行為本身**無獨立行為級測試** — gate 後 Dialog 於危險窗根本
  不掛載,行為級測試無可達路徑(收尾 review round-1 F2 處置:修正本段敘述以符實際)。
- 非根因排除:後端無樂觀鎖(K-4 域)是**放大器**不是根因 —— 即使有樂觀鎖,前端拿
  fallback 當基底本身就是錯的意圖。
- TanStack Query 特性:query 一旦成功過,之後 refetch 失敗 `data` 仍保留舊值 →
  `data === undefined` 只發生在「從未成功載入」,gate 在入口即可涵蓋整個危險窗。

### 修法(對準根因,最小)

沿用 StockPage 既有 pattern:`data === undefined` 時**不渲染「管理」鈕**
(Dialog 因此開不了,mutation 無從發生)。不動後端、不動 Dialog 內部。

### K-4 評估(同輪指示)

K-4(三處 mutation 整份 PUT last-write-wins、Sidebar 入口零 `save.isPending` 防護)
= 並發競態,與本 bug(fallback 狀態混淆)**非同根因**;修法也不同(pending 防護 /
後端版本戳 vs 入口 gate)。不擴 scope,維持 next-time 既有條目(:323)。

## Phase 8|反向驗證(2026-08-04 執行)

fix commit(b670a45)為 test + fix 同 commit,故以等價方式還原 source:gate 條件
`data === undefined` 暫改 `false`(= 管理鈕恆渲染,修前行為)→ 跑
`npx vitest run src/components/stock/WatchlistSidebar.test.tsx`:

- 還原後:**2 failed | 53 passed**(紅的恰是兩條新測試:「載入失敗 → 管理鈕不渲染」
  「pending → 管理鈕不渲染」,失敗訊息 = 找到了管理鈕,與 bug 症狀一致),exit 1。
- 復原修復後:55 passed,exit 0。

結論:紅測試確實鎖住 bug,修復是讓它綠的原因。

## Phase 7|真實環境重走重現步驟(摘要,詳 verification.md)

臨時 vite 實例(proxy → 死 port)重現「GET /api/stock/watchlist 500」:側欄顯示
「自選清單載入失敗」且**無「管理」鈕** → 重現步驟第 3 步(開 Dialog)已不可達,
bug 無法再發生。happy path(真 server)管理入口與 Dialog 功能不變。
