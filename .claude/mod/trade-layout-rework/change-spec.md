# change-spec — 交易版面重構(右欄常駐 / 五檔水平 / K 線)

分支 `mod/trade-layout-rework`;Phase 1 現況表見同目錄 `current-state.md`。
規模判定 **L 級**(跨前後端、~18 檔、含新 endpoint)。

## Phase 2 分流判定

**判定:user 帶已成形改法 → grilling 姿態**(命中判準「已指定具體版面配置與元件位置」)。
依 /mod Phase 2 + auto.md「仍必停」條款,已停下做兩輪拍板(2026-07-29),**非** auto-default。

### user 拍板紀錄(2026-07-29)

| # | 議題 | 拍板 |
|---|---|---|
| D1 | 右欄結構 | **三 tab 平行:閃電 / 委託 / 部位**(一次顯示一個) |
| D2 | 切 tab 時右欄標的 | **跟隨當前 tab 標的,版面位置固定**(個股→該股、期貨→該期貨) |
| D3 | 五檔水平版式 | **買左賣右、價量疊放**,中間夾成交價 |
| D4 | K 線範圍 | **日 K 120 根 + 分 K(1分/5分)含歷史數日** |
| D5 | 期貨 tab 中間 | **報價 + 水平五檔**(零後端改動;不做期貨江波圖/明細) |
| D6 | TXO / 指數 tab 右欄 | **常駐,閃電 tab 顯空狀態並強制解除武裝**;委託/部位照顯示 |
| D7 | /auto 退出條件 | 標準 gate 全綠 + 白名單逐條保留(見下) |

---

## 1. 改完的成功條件(畫面可指認,由 user 對照過目)

### SC-1 三欄版面 + 寬度放寬
- 個股 tab 畫面由左到右三欄:**左 = 自選清單**、**中 = 主區**、**右 = 右欄**。
- 瀏覽器視窗拉到 1920 寬時,**內容左右邊緣距視窗邊 ≤ 32px**(現況 `max-w-6xl` 會在兩側留大片空白)。
- 三欄不重疊、不出現水平捲軸(視窗 ≥ 1280 寬)。

### SC-2 右欄三 tab
- 右欄頂端有三顆 tab:文字依序 **「閃電」「委託」「部位」**,同時只有一個 tab 內容可見。
- 被選中的 tab `aria-selected="true"` 且底色為 `bg-bg-deep`。
- 右欄寬度固定(不隨 tab 內容伸縮),重新整理後回到上次選的 tab。

### SC-3 右欄跨 tab 位置固定、內容跟隨
- 在「個股 / 期貨 / TXO 綜合損益 / 指數」四個 tab 之間切換,**右欄一直在畫面最右側、寬度不變、三顆 tab 不變**。
- 個股 tab:閃電 tab 內是**該股**閃電梯(標題列顯示股號 + 股名);委託/部位顯示證券單。
- 期貨 tab:閃電 tab 內是**該期貨商品**閃電梯(標題列顯示 `TXF` 等 + 解析後月份);委託/部位顯示期貨單。
- TXO / 指數 tab:閃電 tab 顯示文字 **「此頁無可下單標的」**;委託/部位顯示**證券 + 期貨全部**委託/部位。

> `[amendment 2026-07-29: review P0-2 — CapitalMarket 型別只有 "sec"|"fut",無法表達「全部」]`
> **TXO / 指數 tab 的「委託」/「部位」tab 內容 = 上下兩段並排**:上段小標 **「證券」**、
> 下段小標 **「期貨」**,各自渲染一份**未改動**的 `CapitalOrdersList` / `CapitalPositionsList`
> (`market="sec"` 與 `market="fut"`)。兩支真錢元件本體零改動 → 刪單/改價/減量/平倉的
> `market` 恆正確(W-A8/A9/A10 不受影響)。
> 此段的部位 `closePriceOf` **一律不傳**(無行情語境)→ 平倉鍵 disabled(W-A10)。

> `[amendment 2026-07-29: review P0-1 / P1-6 — 右欄常駐會打掉「切分頁 unmount 自動解除武裝」]`
> **右欄閃電 tab 的 ladder 一律條件 render(非 `hidden`)**:非當前 context 的 ladder
> **必須 unmount**。切 tab / 標的來源切換 / 切到非閃電 tab,ladder 都真正卸載,
> arm state 隨之消滅 —— 這是 `flash-arm.ts:2` 明文倚賴的解除路徑
> (「切分頁=unmount,state 自然消失」)。
> 本處**刻意違反** `frontend-conventions` 的「`hidden` > 條件 render」慣例,
> 理由 = 下單安全,實作時必須在該檔加註此理由。

### SC-4 五檔水平化(個股)
- 個股中間下半左側的五檔,由現在的**直式**改為**水平**:
  - 一列買量(左)/ 一列買價(左),中央成交價 + 漲跌%,右側對稱一列賣價 / 一列賣量。
  - 買側由中央往左依序 買1→買5;賣側由中央往右依序 賣1→賣5。
  - 每格量下方有比例底色 bar(高度或寬度表示相對量)。
  - 買側文字 `text-bull`(紅)、賣側 `text-bear`(綠)。
- 表頭仍顯示 **「委買 <總量>」/「委賣 <總量>」**。
- 鎖漲停 / 鎖跌停 badge 保留(文字「鎖漲停」「鎖跌停」)。

### SC-5 期貨中間 = 報價 + 水平五檔
- 期貨 tab 中間由上到下:商品切換鈕(大台/小台/微台)→ 報價列 → **與 SC-4 同款的水平五檔**。
- 期貨頁中間**不再有閃電梯、委託、部位**(全部移到右欄)。

### SC-6 個股中間版面
- 個股 tab 中間由上到下:報價 header → **圖表區** → 下半左「五檔」/ 右「明細」並排。
- 個股中間**不再有閃電梯、委託、部位**。

### SC-7 圖表可切 K 線
- 圖表區左上有四顆切換鈕,文字依序 **「江波圖」「1分K」「5分K」「日K」**,選中者外框 `border-accent`。
- 選「日K」→ 顯示蠟燭圖,紅漲(實心/空心皆可)綠跌,可疊 MA5 / MA20。
  `[amendment 2026-07-29: review P1-8 — 原寫「至多 120 根」驗不出 _DAILY_WINDOW_DAYS=40 只給 ~27 根]`
  **可驗收表述改為**:TC4 有資料時,devtools Network 面板中 `/api/stock/bars/2330?tf=D`
  的回應 `bars.length` **≥ 100 且 ≤ 120**。
- 選「1分K」/「5分K」→ 顯示當日起算的分鐘蠟燭;有「往前」鈕可多載前幾日。
- 切回「江波圖」→ 與現況完全相同的分時走勢圖(含 VWAP / CDP / MA 切換與內外盤副圖)。
- 無資料時顯示 **「無 K 線資料」**,不是空白或崩潰。

### SC-8 自選群組(已存在,本輪僅驗收不改)
- 左欄自選仍可:`+` 新增群組、切換群組 tab、`⊞` 把個股加入 / 移出多個群組、群組內拖拉排序。

### SC-9 武裝不跨 tab 殘留 `[amendment 2026-07-29: review P0-1 新增]`
- 在個股 tab 右欄按「武裝」(鈕轉紅底、文字變「解除」)→ 切到期貨 tab → **立刻切回**個股 tab
  (不等 5 分鐘 idle):閃電 tab 的鈕**必須顯示「武裝」**(`aria-pressed="false"`,非紅底)。
- 同樣操作換成:武裝後在右欄切到「委託」tab 再切回「閃電」tab → 鈕同樣回到「武裝」。

### SC-10 分 K 盤中會前進 `[amendment 2026-07-29: review P1-7 新增]`
- 交易時段選「1分K」,停在畫面上不操作,**60 秒內最後一根蠟燭的時間標記會往前推進**
  (證據:devtools Network 面板兩次 `/api/stock/bars/...?tf=1` 回應的最後一筆 `t` 不同)。
- 非交易時段不應出現週期性 `/api/stock/bars` 請求。

---

## 2. 不能破壞的既有行為白名單(**優先於所有新行為**)

> 這節是 Phase 5 code review 的必讀對照物(review-protocol B 節 finder prompt 必附本節行號)。

### W-A 下單安全(真錢,最高優先)
- **W-A1** 武裝(arm)是唯一繞過確認彈窗的路徑;未武裝點價**不送單**,只顯示「未武裝 — 點價不送單」。
- **W-A2** 自動解除武裝的全部觸發不得減少:換標的(`symbol_changed`)/ capital WS 斷線(`conn_lost`)/
  idle 逾時(`ARM_IDLE_MS`)/ `Esc` 鍵 / 連續 3 次送單失敗。
  `[amendment 2026-07-29 round2: review R2-4 — 撤回前一版把第 6 條寫成「既有行為」的錯誤]`
  **第 6 條(ladder 離開畫面即解除)是本輪新增的行為改動 🔴,不是白名單保留項。**
  事實更正:`App.tsx:76-84` 是 `visited ? <div hidden={...}>`,頁面**訪問過就永不 unmount**
  → `PriceLadder` 的 `useReducer(reduceArm)` **現況就會跨主 tab 存活**(直到 5 分鐘 idle)。
  `flash-arm.ts:2` 的「切分頁=unmount,state 自然消失」是**過時註解**,不是現況佐證。
  → 對應 🔴 條目見 §6 🔴-9;`flash-arm.ts:2` 註解需一併更正。
  SC-9 因此是**新行為驗收**,不列入本節白名單。
- **W-A3** 同格 500ms 點價防抖(`CLICK_DEBOUNCE_MS`)。
- **W-A4** `mutateAsync` + 自行 `then/catch` 逐次計數 `send_ok` / `send_fail`(**不可**改回 `mutate` 的
  callback — 連發點價會漏算,武裝連 3 敗自動解除依賴逐次計數)。
- **W-A5** `aliveRef` 守衛:unmount 後不再 setState / 設 timer。
- **W-A6** 期貨 `resolved_contract` 未解析(`contract === null`)時武裝鈕 disabled + 強制解除。
- **W-A7** 交易別 `daytrade_sell`(無券)時買側格子 disabled + `clickPrice` 內雙保險 early-return。
- **W-A8** 委託列表的刪單 / 改價 / 減量、部位平倉,**一律經 `CapitalConfirmDialog` 確認**;
  `env === "prod"` 時 dialog 帶 `danger`。
- **W-A9** 閃電梯紅方格點刪(`cancelLot`)走閃電規則**直刪無彈窗**,逐 `seq_no` 送 cancel,
  market 正確(個股 `sec` / 期貨 `fut`)。
- **W-A10** 平倉閘用估價:個股 = 主檔最新成交價且 `pos.stock_no === code` 才有值;
  期貨 = `futCloseEstimate`(多單用跌停、空單用漲停,且 `pos.stock_no === contract`)。
  **估價 null → 平倉鍵 disabled**。
- **W-A11** 送單 payload 欄位與現況逐欄相同(`price_type:"limit"` / `time_in_force:"ROD"` /
  個股 `trade_kind` / 期貨 `day_trade` + `tc4_symbol: TC.F.TWF.<prod>.HOT` / `source:"flash"`)。
- **W-A12** 張數/口數快捷:同鍵連按累加(`pressQuick`)、手動輸入重置(`manualQty`)。

### W-B 連線 / 資料完整性
- **W-B1** `useCapitalStream()` 全 app **唯一一條** `/ws/capital`(review B2/B4)。
- **W-B2** `useStockStream` 的 seq gap 復原:跳號 → 全量 refetch + pending buffer 重放;
  `refetch` in-flight 合併不丟棄(CR1)。
- **W-B3** WS 重連 exponential backoff(1s → 30s cap)。
- **W-B4** `/ws/index` 指數流常駐 App 層,IndexBar 跨 tab 可見。
- **W-B5** TC4 斷線 / server 斷線告警列文案不變(「達錢 4 連線中斷,恢復後自動回補」/「伺服器連線中斷,重連中…」)。

### W-C 既有互動
- **W-C1** 五檔點價 → 閃電梯該價**置中且不送單**(`stock-price-click` CustomEvent 契約)。
- **W-C2** 閃電梯「跟隨置中」:center 價變更才捲;手動捲動自動暫停跟隨。
- **W-C3** 自選:群組 tab / 新增 / 刪除群組 / `⊞` 多群組歸屬 / `×` 移除 / 群組內拖拉排序;
  「全部」下停用拖拉、新增進「自選」群組、移除 = 從所有群組移除。
- **W-C4** 群組刪除**成功後**才切走 active tab(review A2)。
- **W-C5** 江波圖:hover 十字 + tooltip、VWAP / CDP / MA 切換、疊線不可用時反灰、內外盤副圖、
  `ChartStatic` memo(hover 不重建靜態層)。
- **W-C6** localStorage 既有 key 全部沿用且語意不變:`copycat-tab` / `stock-main-code` /
  `stock-wl-group` / `copycat-fut-product` / `chart-toggles`。
- **W-C7** 個股 tab 未選檔時顯示「從自選清單選擇一檔開始看盤」。

### W-D 後端
- **W-D1** `/api/stock/overlay/{code}` 回傳 shape 與「已完成 bar」剔除規則不變;
  `OverlayCache` don't-cache-empty 不變。
- **W-D2** `fetch_daily_bars()` / `DailyBar` / `build_overlay()` **完全不動**(新 K 線走新函式)。
- **W-D3** API error shape `{"detail":{"error":"<code>"}}` 不變。
- **W-D4** watchlist 30 檔上限(聯集計)+ schema v2 groups + v1 讀時遷移不變。

---

## 3. Backward compat / migration

| 項目 | 策略 |
|---|---|
| localStorage 既有 key | **全部沿用**,語意不變(W-C6) |
| `stock-ladder-open` | 閃電梯摺疊鈕消失(tab 本身即顯隱)→ **此 key 停用**。停用 = 不再讀寫,舊值殘留無害,不做清除 migration |
| 新 key | `copycat-rail-tab`(右欄 tab)、`copycat-chart-mode`(圖表模式)。首次讀不到 → 預設 `"閃電"` / `"江波"`。`[amendment 2026-07-29 phase5: review P2-1 — 原寫 stock-chart-mode;實作統一用 `copycat-` 前綴,對齊 docs/next-time.md 2026-07-28 的 key 收斂方向]` |
| `/api/stock/overlay` | 不動,舊 caller(江波圖疊線)照常 |
| 新 endpoint `/api/stock/bars/{code}` | 純新增,無既有 caller |
| `futCloseEstimate` | 從 `FuturesPage.tsx` 移到 `lib/futures-ladder.ts`,**保留 `FuturesPage` re-export**,既有測試 import 路徑不破 |
| `StockPage` / `FuturesPage` 由自持 state 改吃 props | 內部元件,唯一 caller 是 `App.tsx`;測試需同步改(🔴) |

---

## 4. Out of scope(本輪不做)

- 期貨江波圖 / 期貨明細 / 期貨 tick 歷史(需後端 futures engine 新增分鐘聚合 + tick 緩衝 — D5 已排除)。
- TXO 綜合損益頁與指數頁的**內部**版面(只受 SC-1 寬度放寬影響,不重排)。
- 自選群組功能新增(現況已滿足,SC-8 僅驗收)。
- K 線的縮放 / 拖曳平移 / 畫線工具。
- 分 K 的即時 tick 級更新(採 60s 輪詢,見 §5 D-9)。
- 已停用的 TC4 `TradeRuntime`(`/api/trade/*` 恆 503)清理 — 留原輪次處理。

---

## 5. 實作級決策(`[auto-default]`,可逆、不改對外契約)

| # | 決策 | 理由 |
|---|---|---|
| D-1 | App root 由 `max-w-6xl` 改 `w-full`(不設上限) | user 明示「充分利用網頁空間」;`mx-auto` 一併移除 |
| D-2 | 右欄寬 `w-72`(18rem);左欄維持 `w-60` | 期貨閃電梯現況 `w-64` + 左右 padding,18rem 剛好容納不擠 |
| D-3 | **`useStockStream` / `useFuturesStream` 提升到 `App.tsx`**,`code` / `product` state 一併上提,以 props 下傳頁面與右欄 | D2 要求右欄跟隨當前 tab 標的;資料在頁面內就無法餵右欄。`useCapitalStream` / `useIndexStream` 已是同樣的 App 層常駐先例。**副作用:WS 於 app 載入即建立(不再等首次進 tab)** — 見 §7 🔴-4 |
| D-4 | 頁面 lazy(`React.lazy` + `visited`)保留,只是不再兼管 WS 建立時機 | 重元件延後載入的價值仍在 |
| D-5 | 水平五檔抽成共用元件 `components/quote/DepthBar.tsx`,個股與期貨共用 | SC-4 / SC-5 明文同款;避免兩份實作漂移 |
| D-6 | 江波圖 viewBox 由 `800×260` 改 `1400×320`(副圖 `1400×80`) | `w-full` + viewBox 等比放大,寬度放寬後原比例會過高(1850px 寬 → 600px 高) |
| D-7 | 新後端函式 `StockQuoteSource.fetch_ohlc_bars(code, tf, days)` 與新 `Bar` TypedDict,**不改** `fetch_daily_bars` / `DailyBar` | W-D2:overlay 是實盤路徑,零風險原則 |
| D-8 | 5分K 由前端從 1分K 聚合(純函式 `lib/candle.ts::aggregateBars`) | 後端只需一種分鐘粒度;聚合是零 IO 純邏輯,好單測 |
| D-9 | 分 K 盤中新鮮度靠 TanStack Query `refetchInterval: 60_000`(僅分K模式 + 交易時段);日K `staleTime` 當日不過期 | 走 tick 級即時需擴充 `stock-accum` 的分鐘 OHLC(前後端都要改),CP 值不符 |
| D-10 | `days` 參數預設 5、上限 30;「往前」鈕每次 +5 | TC4 1K 單次拉取量與 SubHistory 往返成本 |
| D-11 | 右欄「委託 / 部位」在 TXO / 指數 tab 顯示**全部**(不過濾 market) | D6 拍板「委託/部位照顯示」;此時無 market 語境 |
| D-12 | 閃電梯標題列加「標的」顯示(個股:`2330 台積電`;期貨:`TXF 2026/08`) | D2 讓右欄內容會切換,標的必須畫面可指認,降誤送風險 |

> `[amendment 2026-07-29: review P1-7 / P1-11 — D-9/D-10 原設計會讓分K被日級 cache 釘死,且 60s×30天全量重抓搶 TC4 全域鎖]`
>
> **D-9(改)兩段式資料 + 只輪詢當日**:
> - `tf=1` 的請求在後端拆兩段組裝:**歷史段**(`< today` 的交易日)+ **當日段**。
> - 歷史段:一次 `_collect_history(sym,"1K", 窗首, 昨日)` → 依 Date 切分 → **per (code, date) 永久 memo**
>   (已完成交易日不會再變);memo 命中的日子不重抓。
> - 當日段:`_collect_history(sym,"1K", today, today)` → **TTL 30s cache**(短於 60s 輪詢間隔)。
> - 前端 `refetchInterval: 60_000` **只在分K模式 + 交易時段**啟用;`days` **不進輪詢的 query key**
>   —— 「往前」是一次性請求,拉回來的歷史段進 memo,之後的輪詢只會打當日段。
> - 效果:穩態每分鐘只有「當日 1K」一次 SubHistory,不隨 `days` 放大。
>
> **D-13(新)非當前 context 的 ladder 條件 render(unmount),不用 `hidden`**:
> 理由 = W-A2 第 6 條(下單安全)。**刻意違反** `frontend-conventions` 的 hidden 慣例,
> 實作時必須在 `RightRail.tsx` 就地加註理由,避免後人「順手優化」成 hidden。
>
> **D-14(新)`fetch_ohlc_bars(tf="D")` 使用專屬視窗常數** `_OHLC_DAILY_WINDOW_DAYS = 180`
> (日曆日 ≈ 120 交易日),**不共用** `_DAILY_WINDOW_DAYS = 40` —— 後者是 overlay(實盤路徑)
> 在用的,W-D2 要求零風險。
>
> **D-15(新)`tf=D` 的 cache key 與前端 query key 不含 `days`**(路由層先規範化為 `None`);
> `days` 僅對 `tf=1` 生效。避免同內容多份 cache 與無謂重抓(review P2-15)。
>
> **D-16(新)App 層 `useStockStream` 的 `code` 閘**:`tab !== "stock"` 且 `visited.stock === false`
> 時傳 `code = null`,不打 `/api/stock/state/{code}`。理由 = 該 endpoint 內含 `set_main` →
> 訂閱池變更 + **當日 tick 全量回補**(`app.py:391-397`),不該在使用者只看 TXO/指數 時發生
> (review P1-10)。WS 與 watchlist 推播照常建立。
>
> **D-11(改)** TXO / 指數 tab 的委託/部位改為**兩段並排**(證券 / 期貨),
> 各自渲染未改動的既有清單元件 —— 見 §1 SC-3 的 amendment(review P0-2)。

---

## 6. 逐檔 diff(三類動作分開標記)

> 順序依 /mod Phase 4:**🔵 → 🔴 → 🟢**

### 🔵 純重構(測試不該變)

| 檔 | 動作 |
|---|---|
| `frontend/src/lib/futures-ladder.ts` | **新增** `futCloseEstimate`(自 `FuturesPage.tsx` 原封搬入);`FuturesPage.tsx` 改為 re-export,既有 import 路徑不破 |

> `[amendment 2026-07-29: review P2-12 — 刪除原 🔵 的 DepthBar 條目]`
> 原設計「🔵 先抽出直式 DepthBar → 🔴-2 改水平 → 🟢-2 再做水平正式版」三步互相抵銷:
> 🔵 的產物在同一輪內即成死碼,且無 consumer 可證明「行為零差異」。
> **改為**:水平 `DepthBar` 一次做在 🟢-2;`OrderBook` 在 🔴-2 改成 `DepthBar` 的薄 wrapper
> (保留 `stock-price-click` 發射與鎖停 badge 判定),水平五檔全庫只有一份實作。

### 🔴 行為改動(預期讓既有測試紅)

| # | 檔 | 動作 | 既有測試 |
|---|---|---|---|
| 🔴-1 | `frontend/src/App.tsx` | root `mx-auto max-w-6xl` → `w-full`;版面改三欄 grid;新增右欄 `<RightRail>` + rail tab state(`copycat-rail-tab`) | `App.test.tsx` **不該紅**(未斷言寬度/版面);紅了代表打到 tab 或 WS 數量 |
| 🔴-2 | `frontend/src/components/stock/OrderBook.tsx` | 直式 table → **水平**(SC-4);保留表頭總量、鎖停 badge、`stock-price-click` 契約 | `OrderBook.test.tsx` **該紅**(DOM 結構斷言);逐條改為水平版可指認斷言 |
| 🔴-3 | `frontend/src/components/stock/StockPage.tsx` | 拆走 `PriceLadder` / `CapitalOrdersList` / `CapitalPositionsList`;`code` 改吃 props;中間重排為 圖表 / 五檔+明細 | `StockPage.test.tsx` **該紅**(「選檔後下方渲染委託/部位」一則)→ 改斷言「不再渲染」 |
| 🔴-4 | `frontend/src/App.tsx`(續) | `useStockStream` / `useFuturesStream` 上提(D-3);`visited` 不再兼管 WS 建立 | `App.test.tsx` 「capital WS 唯一掛載」**不該紅**;新增 stock/futures WS 於載入即建立的斷言(🟢) |
| 🔴-5 | `frontend/src/components/futures/FuturesPage.tsx` | 拆走 `FuturesLadder` / 委託 / 部位;中間改 報價 + `DepthBar`;`product` 改吃 props | `FuturesPage.test.tsx` **該紅**(渲染斷言)→ 改;`futCloseEstimate` 單元測試 **不該紅** |
| 🔴-6 | `frontend/src/components/stock/PriceLadder.tsx` | 移除摺疊鈕與 `stock-ladder-open`;標題列加標的(D-12);寬度改吃滿右欄 | `PriceLadder.test.tsx` 摺疊相關**該紅**;**武裝/送單 17 則全部不該紅** |
| 🔴-7 | `frontend/src/components/futures/FuturesLadder.tsx` | 標題列加標的(D-12);寬度改吃滿右欄 | `FuturesLadder.test.tsx` **不該紅**(除標題文字) |
| 🔴-8 | `frontend/src/components/stock/StockIntradayChart.tsx` | `MAIN`/`SUB` viewBox 改 `1400×320` / `1400×80`(D-6) | `StockIntradayChart.test.tsx` 若斷言座標數值**該紅**;斷言文字/toggle 的**不該紅** |

> `[amendment 2026-07-29: review P1-3 / P1-4 / P1-5 — 既有測試「該紅範圍」低估,且真錢測試覆蓋有蒸發風險]`
>
> **🔴-2(補)**:`OrderBook.tsx` 改為 `DepthBar` 薄 wrapper(見 🔵 節 amendment)。
>
> **🔴-3(改)`StockPage.test.tsx` 三則全該紅**(原寫「一則」係低估)。三則都 `wrap(<StockPage />)`
> 無 props,`code` props 化後失效;第二則(`:79-85`)靠 StockPage 內建的 WS 驗 W-B5 告警文案,
> D-3 上提後該 WS 不再由此元件建立。逐則改法:
> - `:74-77` / `:87-93` 版面斷言 → 改傳 props。
> - `:79-85` **W-B5 唯一覆蓋** → **搬到** App 層整合測試(以 App 的 FakeWS 驅動),
>   **告警文案字串逐字不得變**(「達錢 4 連線中斷,恢復後自動回補」)。
> - `:87-93`(委託/部位渲染)→ **搬到** `RightRail.test.tsx`,不是刪除。
>
> **🔴-5(補)`FuturesPage.test.tsx:184-190`「部位平倉:多單估價貼跌停,確認彈窗顯示閘用估價」
> 是 W-A8 + W-A10 的唯一整合覆蓋** → **逐條搬入 `RightRail.test.tsx`**,估價數值 / 彈窗欄位文字 /
> disabled 條件的斷言**不得放寬**。`futCloseEstimate` 純函式單元測試(`:126-142`)不該紅。
>
> **🔴-6(改)`PriceLadder.test.tsx` 整檔該紅,不是「摺疊相關」**:`:85` 的 `expand()` helper
> 被呼叫 **18 次**,涵蓋全部武裝/送單 case;移除摺疊鈕後 `getByRole({name:"閃電梯"})` 直接 throw。
> **唯一允許的修改**:
> 1. 刪除 `expand()` helper 定義與其 18 處呼叫;
> 2. 「預設收合」該則整則刪除或改寫為右欄 tab 行為。
>
> **以下逐字不得動**:`mockFetch` route、payload 斷言、hint 文案、API call 次數斷言、
> `aria-label` 選取字串。Phase 5 必須用 `git diff -- src/components/stock/PriceLadder.test.tsx`
> 逐行核對這條約束並附進 review 輸出。

### 🟢 新功能(先寫紅測試)

| # | 檔 | 動作 | 新測試 |
|---|---|---|---|
| 🟢-1 | `frontend/src/components/rail/RightRail.tsx` | 三 tab 容器(閃電/委託/部位)+ `copycat-rail-tab` persist + 依 context 決定內容;TXO/指數顯空狀態並派發強制解除武裝 | tab 切換、persist、空狀態文案、跨 tab 位置固定 |
| 🟢-2 | `frontend/src/components/quote/DepthBar.tsx` | 水平五檔正式版(SC-4/D-5),個股 + 期貨共用 | 買左賣右順序、量 bar 比例、鎖停 badge、點價事件 |
| 🟢-3 | `copycat/live/stock_source.py` | `Bar` TypedDict + `fetch_ohlc_bars(code, tf, days)`(DK / 1K);欄位缺漏防禦解析 + 略過計數 log | 解析(含缺 Open / 缺 Volume)、1K→分鐘 bar、台北時區 +8、空回傳 |
| 🟢-4 | `copycat/server/bars.py` | `BarsCache`(key = code/tf/days/today,don't-cache-empty)+ 回應組裝 | cache 命中/失效、空不 cache |
| 🟢-5 | `copycat/server/stock_engine.py` | `async def ohlc_bars(code, tf, days)`(`asyncio.to_thread`,TC4 不可用降級空 + warning) | 降級路徑 |
| 🟢-6 | `copycat/server/app.py` | `GET /api/stock/bars/{code}?tf=D\|1&days=N`;`validate_code` 400 `BAD_CODE`;`tf` 非法 400 `BAD_TF`;`days` 夾在 1..30 | 200 shape、400 兩種、503 NOT_READY |
| 🟢-7 | `frontend/src/hooks/useStockBars.ts` | TQ query(D-9 的 staleTime / refetchInterval) | query key、分K 輪詢、日K 不輪詢 |
| 🟢-8 | `frontend/src/lib/candle.ts` | `aggregateBars(bars, n)`(1分→5分)+ `buildCandleGeometry(bars, dims)`(純函式,無 React) | 聚合邊界(不足 n 根的尾巴)、幾何座標、空輸入 |
| 🟢-9 | `frontend/src/components/stock/CandleChart.tsx` | 蠟燭渲染 + MA5/MA20 疊線 + 無資料文案 | 紅漲綠跌、根數上限、無資料 |
| 🟢-10 | `frontend/src/components/stock/StockChart.tsx` | 圖表模式切換容器(江波圖/1分K/5分K/日K)+ `stock-chart-mode` persist + 「往前」鈕 | 四鈕文字與順序、切換、persist、往前鈕 +5 天 |

> `[amendment 2026-07-29: review P0-1 / P1-6 / P1-9 / P1-7 / P1-8 / P2-13 / P2-14 / P2-16]`
>
> **🟢-1(補)`RightRail.tsx`**:
> - ladder **條件 render(D-13)**,非當前 context 一律 unmount;檔內加註「刻意不用 hidden,理由=下單安全」。
> - `code === null`(個股未選檔)→ 閃電 tab 顯示與 TXO/指數**同款空狀態**,
>   **不掛載 `PriceLadder`**(其 `code: string` 為必填,傳 `""` 會讓 payload 帶空股號 — review P2-16)。
> - TXO/指數 的委託/部位走**兩段並排**(§1 SC-3 amendment)。
> - **新測試補**:(a) SC-9 兩條武裝殘留斷言;(b) 未選檔 → 閃電 tab 無武裝鈕;
>   (c) 部位 tab `closePriceOf` 未提供時平倉鍵 disabled;(d) 自 `FuturesPage.test` / `StockPage.test` 搬入的真錢覆蓋。
>
> **🟢-3(補)`stock_source.py`**:
> - 用**專屬**視窗常數 `_OHLC_DAILY_WINDOW_DAYS = 180`(D-14),不動 `_DAILY_WINDOW_DAYS`。
> - `DailyBar` 只有 date/high/low/close(**無 open/volume**,review P2-13)→ 新 `Bar` TypedDict
>   自行解析:DK 缺 `Open` → 用 `Close`、缺量 → `0`,略過計數 `logger.warning`;
>   1K fallback 聚合的 `open` = 當日第一根 Close、`volume` = 各根 Volume 加總(缺 → 0 + warning)。
> - **`t` 沿用既有 1K 終點標記語意**(第一根 = 09:01;`1331–1335` clamp `1330`),
>   與 `fetch_day_minutes:245-272` 一致 —— 否則江波圖與 1分K 會差一分鐘、5分聚合邊界飄移(review P2-14)。
>
> **🟢-5(補)caller 連帶**:`stock_engine.py` 的 **`class StockSource(Protocol)`(:28-45)必須擴充**,
> 且兩個測試 fake 要補同名方法,否則 pyright gate 紅:
> - `tests/server/test_stock_engine.py:78`
> - `tests/server/test_stock_routes.py:42`
>
> fake 補方法屬 🟢 附帶,**既有斷言不動**(review P1-9)。
>
> **🟢-4(改)`bars.py` 兩段式 cache**(D-9 amendment):
> - `_HistCache`:key `(code, date)` → 該日 `list[Bar]`,**永久 memo**(只收 `date < today`)。
> - `_TodayCache`:key `code` → `(monotonic_ts, list[Bar])`,**TTL 30s**。
> - 組裝:缺哪些歷史日就拉一次區間 1K 補 memo;當日段獨立拉。空結果不 cache(don't-cache-empty)。
> - **測試補**:歷史 memo 命中不重拉、當日 TTL 到期會重拉、TTL 內不重拉。
>
> **🟢-8(補)`aggregateBars` 測試邊界**:`09:01–09:05` 併為一根且標記 `09:05`(終點標記語意)。

### API 契約(新增)

```
GET /api/stock/bars/{code}?tf=D|1&days=5
200 → { "tf": "D", "code": "2330", "bars": [
          { "t": "2026-07-28", "o": 2380000, "h": 2395000,
            "l": 2375000, "c": 2390000, "v": 28451 }, ... ] }
400 → { "detail": { "error": "BAD_CODE" } } | { "detail": { "error": "BAD_TF" } }
503 → { "detail": { "error": "NOT_READY" } }
```
- `t`:`tf=D` → `YYYY-MM-DD`;`tf=1` → `YYYY-MM-DD HH:MM`(**台北時間**,TC4 1K 的 UTC 需 +8)。
- `o/h/l/c` 毫元整數;`v` 股數。
- `days` 夾 1..30;`tf=D` 時忽略 `days`,固定回近 120 根。
- 空資料 → `bars: []`(不 cache,可重試 — 同 `OverlayCache` 慣例)。

> `[amendment 2026-07-29: review P2-14 / P2-15 / P1-8]`
> - **`t` 的分鐘語意 = 終點標記**(沿用 `fetch_day_minutes` 慣例):當日第一根為 `09:01`,
>   `1331–1335` clamp 為 `1330`,域外丟棄。前端 5 分聚合以終點標記分組(`09:01–09:05` → `09:05`)。
> - **`tf=D` 的 cache key 與前端 query key 不含 `days`**(路由層先規範化為 `None`);
>   `days` 僅對 `tf=1` 生效(D-15)。
> - **`tf=D` 走專屬 180 日曆日視窗**(D-14),實測回應應落在 100–120 根(SC-7 amendment)。

---

## 7. 風險與對應

| 風險 | 對應 |
|---|---|
| **右欄跟隨 tab 切換 → 誤送單** | `[amendment 2026-07-29: review P0-1 — 原寫「走 symbol_changed 同一路徑」是事實錯誤]` 切 tab 時 `code`/`product` **並未改變**,`symbol_changed` 的 deps(`PriceLadder:177 [code]` / `FuturesLadder:143 [product]`)不會觸發。真正的對應 = **D-13 條件 render 讓 ladder unmount** + W-A2 第 6 條 + D-12 標題列標的顯示,並由 SC-9 驗收 |
| TC4 `DK` 的 `Open` / `Volume` 欄位名**未實測**(CLAUDE.md 只實證 High/Low/Close) | 防禦解析(🟢-3 amendment):缺 `Open` → 用 `Close`;缺量 → `0`;略過計數 `logger.warning`。Phase 7 真實環境驗一次 |
| WS 上提後 app 載入即連 4 條 WS | `[amendment 2026-07-29: review P1-10 — 原評估漏了真正有成本的那條]` 真正的成本不是 WS,是 `useStockStream` 一載入就打 `/api/stock/state/{code}` → **`set_main` 觸發訂閱池變更 + 當日 tick 全量回補**(`app.py:391-397`、`stock_engine.py:153-162`)。對應 = **D-16 的 `code` 閘**(未訪問過個股 tab 時傳 `null`)。Phase 7 用 server log 佐證回補不在非個股 tab 發生 |
| 分 K 60s 輪詢打 TC4 SubHistory 往返,搶 `tc4.py:132 _api_lock` 全域鎖 | `[amendment 2026-07-29: review P1-11]` D-9 兩段式:輪詢**只重抓當日**(`days` 不進輪詢 key),穩態每分鐘僅一次當日 1K。Phase 7 **量測一次當日段耗時,>5s 即回頭改設計** |
| viewBox 改動打到 `stock-intraday-svg` 既有測試 | 該 lib 以 dims 為參數,測試自帶 dims;打到代表測試寫死 MAIN — 屬 🔴-8 預期 |
| `RightRail` 的 ladder unmount 後,後人「順手優化」成 `hidden` 會靜默恢復 P0-1 | D-13 要求就地註解理由;SC-9 的兩條測試是 regression lock |

---

## 8. Round 2 限縮輪修復 `[amendment 2026-07-29 round2]`

限縮輪(只審 round 1 的 amendment)回 **P0×0 / P1×5 / P2×5**,逐條驗證後全數 accepted。
以下修復**取代**round 1 對應段落的敘述。

### R2-1 資料源需要 range 型介面(P1)

round 1 的兩段式組裝(D-9)要「歷史區間」與「當日」分開取,但我宣告的介面全是 days 型,
`_collect_history` 又是私有方法且不在 Protocol 上 → 實作第一步就卡住,或被迫破層直呼(fake 沒有 → pyright 紅)。

**改為**:新增 **range 型** source 方法(取代原 `fetch_ohlc_bars(code, tf, days)`):

```python
def fetch_bars_range(self, code: str, tf: str, start_date: str, end_date: str) -> list[Bar]: ...
#   tf: "D" | "1";start/end = YYYY-MM-DD(含端點)
```

- 同步擴充 `stock_engine.py::StockSource` Protocol + **兩個 fake**
  (`tests/server/test_stock_engine.py:78`、`tests/server/test_stock_routes.py:42`)。
- engine:`async def bars_range(code, tf, start_date, end_date)`(`asyncio.to_thread`,
  TC4 不可用降級空 + warning)。
- `server/bars.py` **只做組裝與 cache**,不碰 TC4。

### R2-2 歷史 memo 需要負向快取(P1)

窗內必有週末/假日(days 上限 30 → ≥8 個非交易日),這些日子永遠取不到 rows、永遠不進 memo
→「缺哪些日」恆非空 → 每次輪詢都重拉整段歷史,P1-11 等於沒修掉。

**改為**:一次 range 抓取成功後,對區間內**所有 `< today` 的日曆日**寫 memo
(**無 rows 者寫空 list = 負向快取**)。`don't-cache-empty` **只適用於**「當日段」與
「整體回應為空(TC4 失敗)」兩種情況。
測試補:「含週末的區間抓一次後,第二次請求不再呼叫 source」。

### R2-3 `days` 必須留在 query key(P1)

round 1 把 `days` 排除在 query key 外會讓 D-10 的「往前」鈕**按了完全沒反應**
(TQ 只有 key 變才重取),且輪詢閉包仍帶最新 days 打完整區間 —— 兩頭落空。

**改為**:`days` **放回** query key(往前鈕天然觸發取數);成本控制**全部交給後端 memo**
(R2-2 修好後成立:歷史段命中 memo 零 TC4 往返,只有當日段打 TC4)。
D-15 仍成立(`tf=D` 不含 days)。

### R2-5 `stock-price-click` 在非閃電 tab 會被丟棄(P1)

D-13 讓 ladder unmount → `PriceLadder.tsx:195-206` 的 window listener 一併消失
→ 停在「委託」/「部位」tab 時點中間五檔,事件靜默丟棄,**W-C1 白名單失效**。

**改為**:`stock-price-click` 的**訂閱者上移到 `RightRail`**(唯一 listener):
收到 → `setRailTab("flash")` + `setCenterRequest({priceMilli, nonce})` →
以 prop 傳給 `PriceLadder`,ladder 依 **nonce 變化**捲動置中(mount 後也生效)。
`PriceLadder` 移除自己的 window listener(**🔴**,見 §6 🔴-10)。
測試補:「rail 停在委託 tab → 點五檔 → 自動切回閃電 tab 且該價置中」。

### R2-6 clamp 1331–1335 會產生同 `t` 多筆(P2)

`fetch_day_minutes` 回 `dict` 靠 key 覆寫;新 `Bar` 是 `list` → 直接照抄 clamp 會產出
多筆 `t="…13:30"` 的 bar(React key 重複、5 分聚合多算一根)。

**改為**:🟢-3 補合併規則 —— 同 `t` 多列合併為一根(`o` 取第一、`h`=max、`l`=min、
`c`=最後一、`v` 加總)。測試補「1331–1335 多列 clamp 合併為單一 1330 bar」。

### R2-7 `tf=D` 的 1K fallback 成本放大 4.5×(P2)

D-14 把視窗拉到 180 日曆日,DK 空時 fallback 走 1K ≈ 4.8 萬列分頁收割。

**改為**:fallback 路徑**另用較小視窗 90 日曆日**(接受根數不足 120,`logger.info` 記明),
且 §7 的 Phase 7 量測門檻(>5s 回頭改設計)**同時套用**到 `tf=D` 首次請求含 fallback。

### R2-9 SC-10 驗收表述在邊界不可達(P2)

輪詢間隔正好 60s,「60 秒內」對照兩次回應邊界上不可達;且該分鐘無成交時 `t` 不前進 → 假紅。

**SC-10 改為**:交易時段停留 **≥ 2 分鐘**,devtools 觀察到 **≥ 2 次** `/api/stock/bars/...?tf=1`
請求,且**至少一組相鄰回應的最後一筆 `t` 不同**(以成交熱絡標的如 2330 驗)。

### R2-10 unmount 會靜默重置交易別 / 數量(P2,真錢相關)

D-13 讓切右欄 tab 也 unmount ladder → `tradeKind`(現股/融資/**融券**/無券)、`qtyState`、
`follow` 全部靜默回預設。融券操作者切去看部位再切回會**變回現股**。

**改為**:`tradeKind` 與 `qtyState` **上提到 `RightRail`**,以 props 下傳
(個股/期貨各自一份);**`arm` 仍留在 ladder 內**,隨 unmount 消滅(這正是 D-13 的目的)。
`follow` 可接受重置(無真錢後果)。
另明文:切走時 in-flight 送單**照樣送出**(`aliveRef` 只擋 UI 尾段),結果只能在委託列表確認 —— 
此為預期行為,RightRail 空狀態文案不得暗示「已取消」。

### §6 新增 🔴 條目

| # | 檔 | 動作 | 既有測試 |
|---|---|---|---|
| 🔴-9 | `frontend/src/lib/flash-arm.ts` + ladder 生命週期 | **新增**「離開畫面即解除武裝」行為(R2-4:此為新行為,非既有);更正 `flash-arm.ts:2` 過時註解 | `flash-arm.test.ts` **不該紅**(reducer 本身沒變);行為由 `RightRail.test.tsx` 新測試(SC-9)覆蓋 |
| 🔴-10 | `frontend/src/components/stock/PriceLadder.tsx` | 移除自有 `stock-price-click` window listener(改吃 `centerRequest` prop,R2-5);`tradeKind`/`qtyState` 改吃 props(R2-10) | `PriceLadder.test.tsx` 相關則**該紅**;送單 payload 斷言仍逐字不得動 |

## Known Risks
無(round 1 的 P0×2 / P1×9 / P2×5 與 round 2 的 P1×5 / P2×5 全數修復,無裁決保留項)。

self_review_head: 2039076d64e0871ad7715bca2cfab197584fa5ed
