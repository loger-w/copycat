# 台股綜合 Tab — 總 spec(分段開發計畫)

日期:2026-08-05
狀態:草案(討論輪拍板事項已收攏;各段細節留給各輪 /feat Phase 0/1)
性質:總 spec —— 只定 tab 架構、資料源分工、分段邊界與各段 scope;
不取代各輪的 brainstorm.md / design.md。

---

## 1. 目的與範圍

把現有的大盤(index)、相關係數(corr)兩顆 tab 統整為一顆「台股綜合」tab,
並新增全市場廣度功能(漲跌家數 / 漲跌停家數 / 漲跌停列表 / 類股強弱 / 訊號事件流)。

**Non-goals**:
- 期貨 tab 不併入(user 拍板:期貨另外放)。
- 個股 tab 零改動(列表點擊只是「跳轉 + 設主圖標的」,走既有路徑)。
- 下單無關。
- 大盤級衍生訊號(騰落背離、basis 突變)不在本計畫 —— 記 next-time。

---

## 2. 已拍板決策(2026-08-05 討論輪)

| # | 決策 | 理由 |
|---|------|------|
| D-1 | **copycat 引入 FinMind**,與 TC4 並用;CLAUDE.md §0「純 FinMind 歸 neigui」在實作輪補記例外 | 全市場家數 TC4 做不到(逐 symbol 訂閱模式 + 跨 session 只推一邊地雷);FinMind 是唯一解不是次佳解 |
| D-2 | **搬移 neigui 既有大盤管線**,不重新發明 | `finmind_realtime.py`(universe 5s TTL)+ `market_today.py`(零 IO 純函式:compute_breadth 五桶 / 強弱卡 / 市值分層 / 族群輪動)已是產線驗證 code;原規劃的「FinMind probe 輪」因此取消 |
| D-3 | **類股強弱用 neigui sector_rotation,不接 TC4 類股指數** | 同一份 universe snapshot 免費算出、涵蓋上櫃(TC4 無櫃買類股指數) |
| D-4 | **一顆 tab**:改造既有 index tab 為「台股綜合」,corr tab 移除併入 | user 拍板 |
| D-5 | 漲跌停列表點擊 = **跳轉個股 tab + 設主圖標的**(等同手動輸入股號);迷你預覽記 next-time | 第一版零成本;用過再決定要不要就地預覽 |
| D-6 | 訊號事件流**不新建系統**:signal_hub jsonl 為唯一真相源,事件流是讀取視圖;鎖板/開板全市場事件由 breadth diff 產生、餵同一 hub,預設只進時間軸不進 Discord | 單一匯流排;Discord 防吵 |
| D-7 | 全案分 **4 段**,每段一輪 /feat、各自獨立 SC、各自可出貨 | L 級整案拆 M 級數輪,依賴順序天然成立 |

---

## 3. 資料源架構(分工表)

原則:**FinMind = 廣度掃描(慢變量聚合),TC4 = 深度即時(tick 級)**。
發現(FinMind)→ 盯盤(TC4)以一次點擊銜接。

| 功能 | 資料源 | 粒度 | 管線狀態 |
|------|--------|------|---------|
| 加權分時/K | TC4 IX0001 push + 1K/DK 回補 | tick | 既有(index_engine) |
| 櫃買分時/當日分K | TPEx MIS 5s poll | 5s | 既有(mis.py;無日K,TC4 無此 symbol) |
| 期指圖 / basis | TC4 futures_engine + index stream spot | tick | 既有;basis = 前端減法 |
| 相關係數 | TC4 corr_engine | 秒級 | 既有,純搬遷 |
| 漲跌家數 / 騰落線 | FinMind snapshot poll | 5–10s | **新增**(搬 neigui) |
| 漲跌停列表 | 同上(compute_breadth 全量 rows) | 5–10s | **新增** |
| 類股強弱 | 同上(sector_rotation) | 5–10s | **新增** |
| 鎖板後五檔/市價佇列/內外盤 | TC4 個股訂閱池 | tick | 既有(個股頁),零新開發 |
| 訊號事件流 | signal_hub jsonl + WS | 即時 | **新增讀取視圖** + breadth diff 事件源 |

**配額**:Sponsor 6000 req/hr;snapshot 一個 request 回全市場。10s poll = 360 req/hr
(5s = 720);copycat + neigui 同時跑合計仍 <25% 配額。poll 間隔進 config 可調。

**降級**(沿 mis.py 慣例):poll 失敗 → None、保留前值 + stale 標記。
失效域隔離:FinMind 掛掉只影響家數/列表/類股三塊(變舊不變錯),
TC4 系(指數圖/corr/個股/既有訊號)完全不受影響。

**FinMind token 共用**:兩專案同一顆 token,配額同池 —— round 2 實作時
在 .env 段補記,並確認 neigui 盤中實際用量後再定 copycat 預設 poll 間隔。

---

## 4. Tab 資訊架構(layout 草案)

「台股綜合」單顆 tab,由上而下分區(各段落地後逐步填入):

```
┌─────────────────────────────────────────────────────┐
│ [上] 雙指數並排圖:加權 | 櫃買(各自獨立 分時/K 切換) │
│      + basis 標示(TXF − 加權現貨價差)               │  ← Round 1
├─────────────────────────────────────────────────────┤
│ [中] 家數帶:上市/上櫃 × 漲停/上漲/平盤/下跌/跌停     │
│      + 騰落線(當日家數差時間序列)                    │  ← Round 2
├─────────────────────────────────────────────────────┤
│ [下] 區塊切換:漲跌停列表 | 類股強弱 | 相關係數 |      │  ← R1(corr)/
│      訊號時間軸                                       │     R3/R4
└─────────────────────────────────────────────────────┘
```

- 既有 index tab 的單圖 + 標的選擇器由雙圖取代;期指圖 3 檔仍可從圖內選擇器切
  (細節留 round 1 Phase 0)。
- corr 舊 tab 移除:`Tab` union 縮減、localStorage `TAB_KEY` 舊值 `corr` 遷移到
  綜合 tab(App.tsx 既有遷移慣例)。

---

## 5. 分段計畫(每段 = 一輪 /feat)

依賴鏈:R1 獨立;R2 是 R3/R4 的管線前置;R3、R4 之間無依賴(可對調)。

### Round 1 — Tab 整併 + 雙圖 + basis(規模 M,純前端)

**Scope**:
- index tab 改名/改造為「台股綜合」;`MarketChart` 掛兩份(加權/櫃買預設),
  各自獨立 key/mode 狀態與 localStorage 持久化。
- basis 顯示:TXF spot − 加權,兩者皆在 `useIndexStream`,前端純減法;
  正逆價差以顏色/符號可指認。
- corr 頁併入為下方區塊,corr tab 移除 + TAB_KEY 遷移。
- **零後端改動**。

**SC 草案**(各輪 Phase 0 正式化,含畫面可指認表述 + 驗證窗口):
- SC:tab 列不再出現「相關係數」,綜合 tab 內可見 corr 區塊,舊 localStorage
  值 `corr` 開頁落在綜合 tab(驗證窗口:anytime,vitest + 截圖)。
- SC:並排兩張圖同屏可見,各自模式鈕獨立作用(anytime,截圖)。
- SC:basis 數值 = 期指價 − 加權價,誤差 0(盤中驗證;窗口外用 fixture)。

**工作分派**(dispatch 單位):
1. Tab union/遷移 + layout 骨架(含測試)
2. 雙圖狀態拆分(useChartToggles 的 store key 分家)
3. basis 元件 + corr 區塊搬遷
每項一個 opus dispatch,TDD 紅先行;frontend-conventions / frontend-testing 先讀。

### Round 2 — FinMind 管線搬移 + 家數帶 + 騰落線(規模 M~L)

**Scope**:
- 後端:
  - FinMind client 落地(參照 neigui `finmind_realtime.py`;HTTP 層適配 copycat
    慣例 —— stdlib urllib vs 引依賴,round 2 Phase 1 拍板)。
  - `market_today.py` 純函式搬移(compute_breadth 五桶互斥 + 漲停價 tick 判定)
    + fixture 測試一起搬。
  - breadth poller(預設 10s,config 可調;盤中窗口 gate)。
  - 當日家數序列:in-memory + **當日 JSON 落檔**(防重啟歸零 —— 記取櫃買序列教訓)。
  - REST `/api/market/breadth` + WS 廣播(併入既有 index WS 或獨立,Phase 1 定;
    新 WS 一律走 relay helper —— ws-zombie 教訓)。
- 前端:家數帶(上市/上櫃五桶,漲停/跌停數醒目)+ 騰落線圖(dataviz skill 過)。
- CLAUDE.md:§0 補 FinMind 例外記載;§1 .env 補 FINMIND_TOKEN 啟用說明。

**SC 草案**:
- SC:盤中家數帶十個數字與 neigui MarketBreadthPanel 同時刻對照一致(盤中;
  窗口外以錄製 fixture 驗 compute 層)。
- SC:server 重啟後騰落線當日序列不歸零(anytime,重啟實測 —— 注意盤中不重啟紀律,
  排盤後驗)。
- SC:FinMind 失敗時家數帶顯示 stale 標記且指數圖不受影響(anytime,fake 注入)。

**工作分派**:
1. 純函式層搬移 + 測試(獨立、零風險,先行)
2. FinMind client + poller + 序列落檔
3. API/WS 接線
4. 前端家數帶 + 騰落線
1↔2 可並行 dispatch;3 依賴 1+2;4 依賴 3 的契約(可先以 fixture 並行)。

### Round 3 — 漲跌停列表 + 個股跳轉(規模 M)

**Scope**:
- 後端:breadth 全量 rows 已由 R2 產出;本輪只補列表所需欄位(若缺)。
  篩選採 **neigui 同款「全量給前端、前端門檻自理」**;條件持久化 localStorage
  (是否需後端 config 檔,Phase 0 再議)。
- 前端:列表元件 + 篩選 UI(上市/上櫃、漲停/跌停/觸及未鎖、成交金額門檻、
  股價區間;連板數欄位視資料可得性 —— copycat daily store 覆蓋範圍是 watchlist
  universe,全市場連板要 FinMind EOD 補,Phase 0 決定進不進本輪)。
- 點擊列 → `setTab("stock")` + `setStockCode(code)`(App.tsx 既有狀態,零新機制)。

**SC 草案**:
- SC:盤中點擊列表任一檔,畫面切個股 tab、主圖為該檔、五檔開始跳動(盤中;
  窗口外驗跳轉與 set_main 呼叫)。
- SC:篩選條件改動即時生效且重整頁面後保留(anytime)。

**工作分派**:
1. 列表 + 篩選(前端為主)
2. 跳轉接線 + 測試
3. (若納入)連板數資料補齊(後端)

### Round 4 — 類股強弱 + 訊號事件流(規模 M)

**Scope**:
- sector_rotation 搬移(依賴 R2 管線;含 industry override 表與幽靈 sector 教訓)。
- 訊號事件流:
  - 後端:`GET /api/signals/today`(讀當日 jsonl);breadth diff 產生鎖板/開板
    事件(新 signal 類型,dedup 鍵設計對齊 SignalDetector 三層去重;
    **預設不進 Discord**,enabled 機制沿用)。
  - 前端:時間軸欄(時間倒序、類型篩選、點擊跳個股);事件標注來源精度
    (FinMind 5–10s vs TC4 tick 級)。

**SC 草案**:
- SC:自選池訊號與全市場鎖板事件出現在同一時間軸,類型可篩(盤中;
  窗口外以 jsonl fixture 驗)。
- SC:全市場鎖板事件不出現在 Discord(anytime,signal_hub 測試)。
- SC:類股強弱排序與 neigui 同時刻對照一致(盤中)。

**工作分派**:
1. sector_rotation 搬移 + 測試
2. signals/today API + breadth diff 事件源
3. 前端時間軸 + 類股強弱面板
1 與 2 並行;3 依賴 1+2 契約。

---

## 6. 跨段共用約束

- **盤中不起第二台連 TC4 的後端**(§8 紀律):前端驗證只起 vite dev;
  後端 HTTP 層驗證用 fake source + 另 port。FinMind poller 不碰 ZMQ,
  但它活在同一個 server process,盤中一樣不重啟。
- 每輪各自過完整 gate(pytest/ruff/pyright/validate + npm test/tsc/eslint)。
- neigui 搬移的檔案:**搬邏輯與測試,適配 copycat 慣例**(backend-conventions
  先讀);不整檔複製貼上(neigui 是 httpx/async + 自家 cache utils)。
- 驗證窗口:家數/列表/類股/事件流的真值對照都是盤中限定 —— 各輪 Phase 0
  必須寫窗口外降級(fixture / 錄製快照),排程時優先讓真實驗證落在交易日盤中。
- UI SC 一律「畫面可指認」表述 + AI 截圖(claude-in-chrome)+ user 過目雙層。

## 7. Open questions(留給各輪 Phase 0/1)

1. R1:雙圖之下期指 3 檔的入口形式(圖內選擇器保留?第三張小圖?)。
2. R2:FinMind HTTP 層用 stdlib urllib(copycat runtime 慣例)還是隨 server
   extras 引 httpx;poll 間隔預設值(5s vs 10s,看 neigui 實際配額用量)。
3. R2:breadth WS 併入 index WS 還是獨立 endpoint。
4. R3:連板數欄位的資料路徑(daily store 只涵蓋 watchlist universe)。
   〔2026-08-06 R3 Phase 0 拍板:FinMind TaiwanStockPrice EOD 回看 10 交易日,
   每日一次快取落檔;連板算術在後端 rows 端點(streak/streak_capped)。〕
5. R4:鎖板/開板事件的 dedup 鍵與「觸及未鎖」是否也算事件。
6. next-time 既有候選:列表迷你預覽(D-5)、大盤級衍生訊號(§1 non-goal)、
   創 20 日新高/新低家數。
