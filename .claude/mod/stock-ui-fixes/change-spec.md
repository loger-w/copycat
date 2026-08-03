# change-spec — 個股頁 5 項修改(stock-ui-fixes)

現況表:`.claude/mod/stock-ui-fixes/current-state.md`(Phase 1,含 baseline 與 caller map)

## 分流判定

**提問姿態 = `grilling`**(user 帶已成形改法)。命中判準:5 項需求逐條指名了目標物件與期望結果
(「5 檔請參照 trading-king」/「K 線沒有資料」/「拖曳時不要選字」/「拖曳條改成專案樣式」/
「最外圍不要拖曳」),不是開放式「幫我改好看一點」。
→ 提問縮成「確認 + counter-proposal」,已於 2026-07-29 16:50 由 user 拍板(下方 Q1/Q2/Q4)。

---

## 0. 拍板紀錄(2026-07-29,user 直接回答)

| # | 問題 | 拍板 |
|---|---|---|
| Q1 | 五檔改垂直版式,但 DepthBar 個股/期貨共用,期貨怎麼辦? | **只改個股,期貨維持原樣** |
| Q2 | 「拖曳條」= 捲軸,這個判讀對嗎? | **對,就是捲軸** |
| Q3 | 版面高度分配 | **未答** → `[auto-default: 圖表維持自然高度,下半列吃剩餘高度 \| reason: 見下方 amendment]` |
| Q4 | 重啟 :8721 驗 K 線 | **可以重啟,由我執行** — 已於 16:47 完成,見 §2 |
| Q5 | SC-3(K 線錯誤態文案)非 user 5 項需求之一 | `[auto-default: 納入本輪 \| reason: 本輪 item 2 的全部誤判成本來自「請求失敗」與「真的沒資料」共用同一句文案 —— 根因(舊 build)已修,但同一個症狀下次還會被同樣誤讀。改動極小(1 個分支 + 1 條既有斷言)。**未經 user 拍板,可否決**]`(R5) |

> `[amendment 2026-07-29: R1(P0)—— 原 Q3 做法「SVG 改 flex-1 + preserveAspectRatio 預設 meet」
> 會破壞 hover 座標換算]`
> 原做法讓 `<svg>` 元素盒高度由 flex 決定,盒比一旦大於 viewBox 比(江波圖主圖 800/260 = 3.077、
> K 線 1400/320 = 4.375)就變成**高度受限 → 內容水平置中留白**,而
> `CandleChart.tsx:196-199`(`scale = DIMS.width / rect.width`)與
> `StockIntradayChart.tsx:190-193`(`x = (clientX - rect.left) / rect.width * MAIN.width`)
> 都假設「元素盒寬 == viewBox 寬」→ 十字線與 tooltip 指到錯的 K 棒 / 分鐘,直接違反 W-10。
> 實算 1440×800(SC-6 自己指定的驗收尺寸之一)江波圖主圖盒比 ≈ 4.14 > 3.077,**必然踩到**。
>
> **改採做法(Option Z)—— 完全不動兩張圖的 SVG,因此 hover 幾何零風險**:
> 1. 圖表維持現在的 `w-full` + 自然高度(高度 = 寬 ÷ viewBox 比,與今天完全相同)。
> 2. 改讓**下半列(五檔 | 明細)吃剩餘高度**:明細本來就有自己的內層捲軸,撐高只是多顯示幾列。
> 3. `<main>` **保留 `overflow-y-auto`**(不改 `overflow-hidden`)—— 版面配平後正常尺寸下
>    捲軸不會出現(SC-6 量法 `scrollHeight <= clientHeight` 成立),而極端矮視窗時退化成
>    出現捲軸而**不是靜默裁掉內容**(同時解掉 R3:硬裁沒有逃生口)。
>
> 附帶效益:現況截圖 `stock-before.png` 可見下半列底下有一大片死白;改後明細會撐滿到視窗底,
> 可視成交列數大幅增加。
>
> `[amendment 2026-07-29: R13 —— `flex-1` 單獨用會在負剩餘空間時把下半列算成 0 高]`
> `flex-1` = `flex: 1 1 0%`(basis 0)。當 header + 圖表自然高 ≥ main 可視高時 free space 為負,
> **收縮額度按 `shrink × basis` 分配 → basis 0 的下半列分到 0**,整塊被壓成 0 高;明細與
> W-8 的「載入更多」鈕連同消失,而 `<main>` 的捲軸救不到(明細是「被壓縮」不是「撐出捲軸」)。
> 這等於用另一個形態重造 R3 要防的症狀。
> **解法:下半列給高度地板 `min-h-56`(224px)取代 `min-h-0`**,並讓圖表容器 `shrink-0`
> (否則負空間時圖表 div 被壓縮、其內固定高度的 svg 溢出與下半列重疊)。
> 地板一旦頂到,`<main>` 就真的被撐出捲軸 —— 逃生口這才成立。

---

## 1. 改完的成功條件(SC,畫面可指認)

> UI 類條件一律寫成 user 可對照過目的表述(位置 / 文字 / 顏色 / 元素)。

### SC-1(item 1)個股五檔改成 treading-king 垂直雙欄

個股頁下半左側的五檔區塊,由現在的「水平 10 格」改成:

- **標題列**:左側文字「委買賣 五檔」;鎖漲停時其右出現紅字外框 badge「鎖漲停」、鎖跌停時綠字外框 badge「鎖跌停」;**最右側**顯示成交價 + 漲跌%(紅漲綠跌)。
- **總量列**:左側大字紅色委買總量 + 小字「張」;右側大字綠色委賣總量 + 小字「張」。四位數以上有千分位逗號(例:`1,085 張`)。
- **本體**:左右兩欄各 5 列。
  - 左欄(買):每列左邊是量、右邊是紅色價;列背景有一條**淡紅水平量 bar,從該列右緣往左延伸**。
  - 右欄(賣):每列左邊是綠色價、右邊是量;列背景有一條**淡綠水平量 bar,從該列左緣往右延伸**。
  - bar 長度 = 該檔量 ÷ 買賣兩側共用最大量 × 100%。
- 檔位不足 5 檔時,缺的列顯示「—」,**區塊高度不塌陷**(仍是 5 列)。
- 點任一列 → 右欄自動切到「閃電」tab 且閃電梯捲到該價位(行為與現在完全相同)。
- **期貨頁五檔外觀完全不變**(仍是水平 10 格)。

### SC-2(item 2)K 線出現資料

個股頁選 2317、按「日K」→ 圖表區出現蠟燭圖(非「無 K 線資料」字樣),含 MA5 黃線 / MA20 紫線 / 下方量 bar / 左側價位刻度 / 底部日期標籤。按「1分K」「5分K」同樣出現蠟燭。

- **量法**:`GET /api/stock/bars/2317?tf=D` 回傳 `bars.length` 落在 **100–120**(單位:根)。
- **已於 2026-07-29 16:47 達成,無需改任何程式碼**(根因 = 執行中的是舊版 build,見 §2)。

### SC-3(item 2 附帶)K 線請求失敗時看得出是失敗

K 線請求失敗(HTTP 非 2xx / 網路錯)時,圖表區顯示「**K 線載入失敗**」+ 灰色小字錯誤碼,
**不再**顯示與「真的沒資料」同一句的「無 K 線資料」。真的取到空陣列時才顯示「無 K 線資料」。

> `[amendment 2026-07-29: R11 —— 錯誤碼來源寫錯]`
> **錯誤碼取值鏈**(`useStockBars.ts:35-44` 實際邏輯,非「一律 HTTP_<status>」):
> 1. 回應 body 可解析且有 `detail.error` → **用 `detail.error`**(如 `NOT_READY` / `BAD_CODE`)
> 2. 否則 → `HTTP_<status>`(如舊 build 那次的 `HTTP_404`)
> 3. fetch 本身 reject(網路層)→ 瀏覽器原生訊息(如 `Failed to fetch`),照原樣顯示
>
> 因此既有測試 `StockChart.test.tsx:135`(mock 503 + `{detail:{error:"NOT_READY"}}`)改寫後
> 的新斷言字串是 **`NOT_READY`**,不是 `HTTP_503`。

### SC-4(item 3)圖表拖曳不選字

在江波圖或任一 K 線圖上按住左鍵拖曳 → **不出現藍色反白選取**(座標軸數字、時間標籤、
圖下方「累積外盤 / 內盤 / 外盤比」「開高低收量」等文字都不被選取)。
拖曳中與拖曳後,hover 十字線與 tooltip 仍正常跟著游標走。

### SC-5(item 4)捲軸符合專案暗色樣式

所有捲軸不再是 Chrome 預設的**白底淺灰**,改為:軌道透明(融入底色)、滑塊為專案灰藍
(`--color-ink-dim` #55617a)、寬度細版(`scrollbar-width: thin`)。

- **量法** `[amendment 2026-07-29: R9 —— 截圖取色在 thin 捲軸上不是穩定 oracle]`:
  主證走 computed style ——
  `getComputedStyle(document.querySelector("main")).scrollbarColor === "rgb(85, 97, 122) transparent"`
  且 `.scrollbarWidth === "thin"`;對明細容器再取一次(驗 `html` 繼承真的到得了內層,
  這是 §5.1 G auto-default 的核心假設)。**截圖只當佐證,不當判準。**
- **量測時機**:SC-5 與 SC-6 必須在**全部 commit 落地後一次量**——`scrollbar-width: thin`
  會改變捲軸佔用的版面寬度(約 7–9px),分批量會拿到與最終狀態不同的數字。

### SC-6(item 5)個股頁最外圍不出現捲軸

個股頁在**江波圖模式**(現在會溢出的那個模式)下,主區最外圍(圖表 + 五檔 + 明細 的容器)
**不出現捲軸**;圖表維持自然高度,五檔與明細撐滿其下方的剩餘空間(明細因此可見列數變多)。

仍該有捲軸的是**四處** `[amendment 2026-07-29: R8 —— 原文「三處」與量法的四項集合自相矛盾]`:
**明細**(內層)、**閃電下單**(右欄)、**自選股票清單**(左欄)、
**右欄「委託 / 部位」tab**(§5 Out of scope,本來就該捲,不動)。

- **量法**:`document.querySelector("main")` 的 `scrollHeight <= clientHeight`(單位:px);
  且全頁掃描 computed `overflow-y: auto|scroll` 且 `scrollHeight > clientHeight` 的元素集合
  ⊆ {明細、閃電梯、自選清單、右欄委託/部位 tab}。視窗 1920×1080 與 1440×800 兩個尺寸都要成立。
- **極端矮視窗的規定行為** `[amendment 2026-07-29: R3 —— 原做法 overflow-hidden 會靜默裁掉
  明細「載入更多」鈕且無逃生口]`:`<main>` 保留 `overflow-y-auto`。內容真的塞不下時
  (例如 1280×720 以下)**退化成出現捲軸**,而不是把內容裁掉看不到。SC-6 只要求
  1920×1080 / 1440×800 兩個尺寸下捲軸不出現。

---

## 2. item 2 根因與處置(已完成,不需程式碼改動)

**根因**:執行中的 backend(:8721, pid 3328)是**舊版 build**,`openapi.json` 的 paths 不含
`/api/stock/bars/{code}` → 前端請求回 **HTTP 404** → `useStockBars` 進 `isError`
→ `StockChart.tsx:83` 渲染「無 K 線資料」。

**處置**:2026-07-29 16:47 以當前程式碼重啟 server(kill pid 3328/2856 →
`.venv\Scripts\python -m copycat.server`)。

**驗證證據**(重啟後實打,盤後 TC4 常駐):

| 請求 | 結果 | 耗時 |
|---|---|---|
| `openapi.json` | `/api/stock/bars/{code}` **present** | — |
| `/api/stock/bars/2317?tf=D` | **116 根**(SC-2 期望 100–120 ✅) | 1.1s |
| ↑ 首根 | `{"t":"2026-01-30","o":223500,"h":223500,"l":218500,"c":220500,"v":68955}` | |
| ↑ 末根 | `{"t":"2026-07-29","o":240000,"h":246500,"l":231000,"c":237000,"v":81973}` | |
| `/api/stock/bars/2317?tf=1&days=5` | **810 根** / 3 個交易日(07-27, 28, 29) | 2.1s |
| ↑ 末根 | `{"t":"2026-07-29 13:30","o":237000,...,"v":7222}` | |
| 前端畫面 | 116 根蠟燭 + MA5/MA20 + 量 bar 全渲染(`kline-after-restart.png`) | |

**順帶解掉的 next-time.md 未決項**:
- `tf=D` → 116 根,落在 SC-7 期望的 100–120 ✅
- **DK 的 `Open` / `Volume` 欄位名假定成立** —— `o=240000`(240 元)與 `v=81973` 皆為真值,
  且 `v` 與畫面表頭「總量 81973」完全一致。CLAUDE.md §8「只實證 H/L/C」可更新。
- 當日段耗時 1.1s / 2.1s,遠低於 change-spec 原訂的「>5s 就回頭改設計」門檻 ✅
- 解析略過計數 log:server.log 無 `DK rows 解析略過` warning。

→ **item 2 本身零程式碼改動**。SC-3(讓失敗看得出來)是為了防止同一個症狀再次被誤讀成
「沒資料」而做的最小改動,獨立於根因。

---

## 3. 不能破壞的既有行為白名單

> **這比新行為更重要。** Phase 5 review 與 Phase 7 真實環境驗證都要逐條對照。

| # | 行為 | 位置 | 為何脆弱 |
|---|---|---|---|
| W-1 | 五檔點價 → 發 `stock-price-click` CustomEvent(detail 含 priceMilli/side/code) | `OrderBook.tsx:15-20` | 重寫五檔版式時最容易掉的接線 |
| W-2 | 右欄收到該事件 → 切「閃電」tab + ladder 捲到該價位置中 | `RightRail.tsx:82-99` | 依賴 W-1 的 detail 欄位名 |
| W-3 | 五檔**不送單**(design §11:誤觸面大,送單集中在閃電梯) | `DepthBar.tsx:7` 註解 | 新版式若把列做成送單鈕 = 真錢風險 |
| W-4 | 檔位不足時補「—」不塌陷 | `DepthBar.tsx:39-45` | 版式重寫易改成 `.map` 直接省略 |
| W-5 | 鎖漲停 / 鎖跌停 badge 判定 = 買1價 === upper / 賣1價 === lower | `DepthBar.tsx:82-83` | |
| W-6 | **期貨頁五檔維持水平 10 格,外觀與行為零變化**(含無 `onPriceClick` 時渲染成 `div` 不是 `button`) | `FuturesPage.tsx:78`、`DepthBar.tsx:48` | Q1 拍板的核心約束 |
| W-7 | 閃電梯手動捲動自動暫停跟隨現價 | `PriceLadder.tsx:337-342` `onScroll` | 改捲軸樣式不得影響 scroll 事件 |
| W-8 | 明細「載入更多」分頁鈕(每次 +30 筆) | `TickTape.tsx:52-60` | 版面改動易讓它被裁掉看不到 |
| W-9 | 自選清單拖拉重排把手 `⋮⋮`(已有 `select-none`) | `WatchlistSidebar.tsx:255-266` | 全域 user-select 若加錯層級會擋掉別的地方的正常選字 |
| W-10 | 圖表 hover 十字 + tooltip(江波圖 / K 線) | `StockIntradayChart.tsx:230`、`CandleChart.tsx:209` | `user-select:none` 不得誤加成 `pointer-events:none` |
| W-11 | 江波圖 CDP / MA / 均價 toggle + 無日線資料時反灰 | `StockIntradayChart.tsx:204-223` | |
| W-12 | K 線模式切換持久化(`copycat-chart-mode`)+ 分 K「往前」載入天數(5→30) | `StockChart.tsx:36-39,65-75` | |
| W-13 | 江波圖 / K 線的**空資料**狀態文案:「尚無成交」/「無 K 線資料」 | `StockIntradayChart.tsx:171`、`CandleChart.tsx:173` | SC-3 只改**錯誤**態,空資料態文案不動 |
| W-14 | TXO / 期貨 / 指數三頁的版面與捲動範圍 | `App.tsx:199`、`FuturesPage.tsx:36` 等 | item 5 只動個股頁 `<main>` |
| W-15 | 圖表靜態層 `memo`(hover 時不重建蠟燭 / 量 bar 層) | `CandleChart.tsx:48`、`StockIntradayChart.tsx:51` | 加 class 時若把 props 改成新物件會破 memo |
| W-16 | 五檔每格 `aria-label` 格式 = `買N <價>` / `賣N <價>`(如 `買1 2375`),且列維持 `role=button` | 改前 `DepthBar.tsx:54`;**改後 = 新版 `OrderBook.tsx`(真正的風險點)**。測試側耦合:`OrderBook.test.tsx:55,60` + **`StockPage.test.tsx:106`** | 三處都用 `getByRole("button", {name})` 定位,格式一變會以「找不到元素」而非「版式變了」的形式紅,誤導 triage |
| W-17 | 兩張圖 hover 的座標換算前提:**viewBox 在水平方向完整填滿 `<svg>` 元素盒內容區(無水平 letterbox、無 svg 內距),即元素盒長寬比必須 = viewBox 長寬比** | `CandleChart.tsx:196-199`(`DIMS.width / rect.width`)、`StockIntradayChart.tsx:190-193`(`(clientX-left)/rect.width*MAIN.width`) | 任何讓盒比 ≠ viewBox 比的改動(flex 撐高 / aspect 覆寫 / letterbox)都會讓十字線指錯 K 棒,**且畫面看起來完全正常**。本輪 Option Z 後不動 svg,此條為 regression 護欄 |

> `[amendment 2026-07-29: R1/R2 —— 補 W-16 / W-17]`
> `[amendment 2026-07-29: R19 —— W-16 位置欄原本只指 DepthBar(依 W-6 保證不變,對著它打勾等於
> 空轉),補上改後的真實實作點與第三個測試耦合點;W-17 原敘述「盒寬 == viewBox 寬」字面上
> 永不成立(px vs viewBox user unit),改寫為可驗證的前提]`

---

## 4. Backward compat / migration

- **無資料格式變更、無 API 契約變更、無 localStorage schema 變更** → 不需 migration。
- 唯一跨元件契約 = `stock-price-click` CustomEvent 的 detail shape(`{priceMilli, side, code}`),
  **維持不變**(W-1/W-2)。
- `DepthBar` 的 props 介面**不動**(期貨頁繼續用),個股改用新元件 → 對 caller 是新增不是破壞。
- 捲軸樣式是全域 CSS **新增**,不覆寫任何既有規則。

---

## 5. Out of scope

- 期貨頁 / TXO 頁 / 指數頁的五檔與版面(Q1 拍板:只改個股)。
- 右欄「委託 / 部位」tab 的捲動範圍(user 未提;它們是內層容器,本來就該捲)。
- 自選清單「全部」群組顯示空清單的問題(截圖可見 `尚無自選,輸入股號新增`,但主檔 2317 有資料)
  —— 這是 watchlist v2 groups 的既有行為,**非本輪需求**,列入 next-time。
- 圖表隨視窗高度縮放 —— **圖表不隨視窗高度變化**,維持 `w-full` + viewBox 自然高度
  (高度只隨**寬度**變,見 W-17)。版面配平一律由下半列吸收剩餘高度,**圖表本身沒有防溢出機制**。
  `[amendment 2026-07-29: R18 —— 原文「letterbox 只保證不溢出」是 round 1 做法的殘留敘述,
  Option Z 已把 letterbox 整個撤銷,留著會讓實作者以為 svg 那邊還有高度保護]`
- K 線 endpoint 的 inflight dedup、國定假日輪詢(next-time.md 既有條目)。
- 盤後重啟 server 後五檔 / 閃電梯短暫空白(等 TC4 snapshot,CLAUDE.md §8 既有已知行為)。

---

# Phase 3|Diff 級 spec

三類標記:🔴 行為改動(既有測試預期會紅)/ 🟢 新功能(加新測試)/ 🔵 純重構(測試不該變)

## 5.1 檔案逐項

### A. `frontend/src/components/stock/OrderBook.tsx` — 🔴 改寫為垂直雙欄五檔

現況:34 行,純接線(把 props 轉給共用 `DepthBar` + 點價事件)。
改後:自持版式(不再 import DepthBar),約 130 行。

結構:

```tsx
<section className="rounded-md border border-line bg-surface p-3">
  {/* 標題列 */}
  <div className="mb-2 flex items-center gap-2 border-b border-line pb-2">
    <h3 className="text-sm font-bold text-ink">委買賣 五檔</h3>
    {lockedUp  ? <span className="rounded border border-bull/40 px-1.5 py-0.5 text-xs text-bull">鎖漲停</span> : null}
    {lockedDown? <span className="rounded border border-bear/40 px-1.5 py-0.5 text-xs text-bear">鎖跌停</span> : null}
    <span className="ml-auto font-mono text-sm ...">{fmt(last)} {chg%}</span>   {/* [auto-default] 見下 */}
  </div>
  {/* 總量列 */}
  <div className="mb-3 flex items-baseline justify-between font-mono">
    <span className="text-xl font-bold text-bull">{bidTotal.toLocaleString()}<span className="ml-1 text-xs font-normal text-bull/70">張</span></span>
    <span className="text-xl font-bold text-bear">{askTotal.toLocaleString()}<span className="ml-1 text-xs font-normal text-bear/70">張</span></span>
  </div>
  {/* 本體 */}
  <div className="grid grid-cols-2 gap-6">
    <BookSide side="bid" .../>
    <BookSide side="ask" .../>
  </div>
</section>
```

`BookSide`(單一函式涵蓋買賣兩側,規則只寫一次 — 沿用 treading-king 的收斂理由):

```tsx
{[0,1,2,3,4].map((i) => {
  const entry = levels[i];                        // undefined = 該檔不存在
  if (entry === undefined) return <缺檔列 key>—</缺檔列>;   // W-4:不塌陷
  const [priceMilli, qty] = entry;
  return (
    <button type="button" key={i}
      onClick={() => onPriceClick(priceMilli, side)}   // W-1/W-2/W-3:置中,不送單
      aria-label={`${isBid ? "買" : "賣"}${i+1} ${fmt(priceMilli)}`}   // W-16:格式不可變
      className="relative grid w-full grid-cols-2 gap-2 border-b border-line px-2 py-1.5 font-mono text-sm hover:bg-bg-deep/60">
      <span className={cn("pointer-events-none absolute inset-y-0", isBid ? "right-0 bg-bull/15" : "left-0 bg-bear/15")}
            style={{ width: `${Math.round((qty / maxQty) * 100)}%` }} data-testid="depth-vol-bar" />
      {/* 買:量 | 價(價靠右、紅);賣:價 | 量(價靠左、綠) */}
    </button>
  );
})}
```

**防禦性常數** `[amendment 2026-07-29: R7 + R15 —— 重寫時最容易掉的就是原元件的除零保護與
null 處理;R7 只補到三分之一,`last` / `ref_` 的 null 才是踩最多既有測試的那個]`:

```tsx
const b = (book?.bids ?? []).slice(0, 5);          // book 可為 null(StockPage 傳 accum.book)
const a = (book?.asks ?? []).slice(0, 5);
const maxQty = Math.max(1, ...b.map(([, v]) => v), ...a.map(([, v]) => v));  // ← 對齊 DepthBar.tsx:78
// 標題列成交價:注意本元件的 last 是物件 {p,t,cum_vol} | null(DepthBar 收的是 number | null)
const lastMilli = last?.p ?? null;
const chg = lastMilli !== null && ref_ ? ((lastMilli - ref_) / ref_) * 100 : null;   // ← DepthBar.tsx:81
// 渲染:lastMilli !== null ? fmt(lastMilli) : "—";chg === null 時整個百分比 span 不渲染
```

- `Math.max(1, ...)` 的 `1` 不可省:五檔全 0 量(盤前 / 剛重啟未收 snapshot)時 `maxQty = 0`
  → `width: "NaN%"`,React 會靜默產生無效 style,只有盤中才看得到。
- **`last` / `ref_` 的 null 防禦不可省**:`OrderBook.test.tsx` 8 個 case 裡有 **6 個傳
  `last={null}`**(25/35/46/53/67/87/101 行),其中 4 個同時 `ref_={null}`。少了這段,
  §5.2 標成「⚪ 不該紅」的 case 會以 TypeError 集體變紅,green commit 拿到一片看不懂的紅。
- **千分位固定 `toLocaleString("en-US")`**(R16):不指定 locale 時分隔符取決於執行環境 ICU
  預設,非 en-US 環境會拿到 `1.033`,讓 SC-1 斷言變成環境相依。

新增測試鎖住(§5.3)。

**高度預算(≤ 210px)** `[amendment 2026-07-29: R14 —— 1440×800 江波圖下半列只有 228px]`:

| 區塊 | 樣式 | 高度 |
|---|---|---|
| 外框 padding | `p-2.5` | 20 |
| 標題列 | `text-sm` + `pb-1.5 mb-1.5` + border | 32 |
| 總量列 | `text-base`(非 `text-xl`)+ `mb-1.5` | 30 |
| 5 × 價量列 | `text-sm` + `py-0.5` + border | 5 × 25 = 125 |
| **合計** | | **207** ✅ |

實作時若因字級縮放超過 210,先收 `py` 再收總量列字級,**不要動列數**(W-4:恆 5 列)。

決策標記:
- `[auto-default: 標題列右側保留成交價 + 漲跌% | reason: 現況 DepthBar 中央格**在這個位置**就有,拿掉 = 本輪靜默減功能。`StockPage.tsx:44-60` 的報價 header 雖有同一組數字,但在頁面最上方、距五檔約 700px,不能替代。此為刻意的資訊重複,讓五檔區自足]` `[amendment 2026-07-29: R10 —— 原 reason 說「拿掉等於減功能」與 header 已有同資訊的事實牴觸,改寫為精確版]`
- `[auto-default: 量單位標「張」| reason: backend stock_models.py:57 明註 bids 是 (價毫元, 張數),單位為事實不是猜測]`
- `[auto-default: 列渲染成 <button> | reason: 個股側恆有 onPriceClick,是真 affordance;DepthBar 的 div/button 分岔是為了期貨側無回呼的情境,個股不需要。**且 W-16 要求維持 role=button**]`

**既有測試處置**:`OrderBook.test.tsx` 實際有 **8 個 case**,逐條分類見 §5.2(已按實際讀檔校正)。

### B. `frontend/src/components/quote/DepthBar.tsx` — 🚫 不動(W-6)

一個字都不改。`DepthBar.test.tsx` / `FuturesPage.test.tsx` **不該紅**;若紅 = 打到不該打的。
檔頭註解目前寫「個股與期貨共用」→ 已不再共用,**只改註解**(🔵,不影響行為)。

### C. `frontend/src/components/stock/StockChart.tsx` — 🔴 錯誤態文案

1. 🔴 **SC-3**:`isError` 分支文案「無 K 線資料」→「K 線載入失敗」+ 第二行灰色小字錯誤碼
   (`error.message`,取值鏈見 SC-3 amendment:`detail.error` 優先)。
   空資料態(`CandleChart` 內的 `shown.length === 0`)**不動**(W-13)。
2. `[amendment 2026-07-29: R1 —— 原本要改的高度鏈全部撤銷]` root `<div className="flex flex-col">`
   與三個狀態盒的 `h-64` **一律不動**。圖表區維持自然高度,SC-6 改由 F 的下半列吸收剩餘空間。

### D. `frontend/src/components/stock/CandleChart.tsx` — 🔴 只加 select-none

1. 🔴 **SC-4**:`<figure>` 加 `select-none`。**檔案其餘部分零改動。**
2. `[amendment 2026-07-29: R1]` 原訂的 `<figure>` flex 化、`<svg>` 改 `flex-1`、空資料盒改
   `flex-1` **全部撤銷** —— svg 元素盒比一旦 ≠ viewBox 比(1400/320)就踩 W-17,hover 十字線
   指錯 K 棒且畫面看起來正常。**`viewBox` / `className="w-full"` / `onMouseMove` 一個字不動。**

### E. `frontend/src/components/stock/StockIntradayChart.tsx` — 🔴 只加 select-none

1. 🔴 **SC-4**:`<figure>` 加 `select-none`。**檔案其餘部分零改動**(理由同 D-2;
   江波圖主圖 viewBox 比 800/260 = 3.077,更容易踩到)。

### F. `frontend/src/components/stock/StockPage.tsx` — 🔴 SC-6 版面(唯一動版面的檔)

`[amendment 2026-07-29: R1 + R3 —— 改採 Option Z,見 §0 Q3 amendment]`

1. `<main ... overflow-y-auto>` **保留 `overflow-y-auto`**(R3:極端矮視窗的逃生口)。
2. `<StockChart>` root(`StockChart.tsx:49`)加 **`shrink-0`**(R13:避免負空間時容器被壓縮、
   內部固定高度的 svg 溢出重疊)。
3. 下半列 `<div className="flex min-w-0 gap-3">` →
   `"flex min-h-56 min-w-0 flex-1 gap-3"` + `data-testid="stock-lower-row"`(R17 的 lock 選擇器)。
   - `flex-1`:吃掉圖表下方全部剩餘空間(現況那片死白)。
   - **`min-h-56`(224px)取代 `min-h-0`**:高度地板,見 §0 Q3 的 R13 amendment。
   - **維持預設 `items-stretch`**(不用 `items-start`),改在五檔 wrapper 上加 `self-start`
     —— 這樣明細 wrapper 自然被拉滿列高,不必依賴百分比高度解析。
4. 五檔 wrapper `<div className="min-w-0 flex-[3]">` → 加 `self-start`(五檔維持內容自然高度,
   不被拉長成一個內部留白的空盒)。
5. 明細 wrapper `<div className="min-w-0 flex-[2]">` 不動(預設 stretch 即撐滿列高)。

### F2. `frontend/src/components/stock/TickTape.tsx` — 🔴 明細撐滿剩餘高度

root `max-h-80`(固定 320px 上限)→ **`h-full`**(由 F 的下半列決定高度),
並加 `data-testid="tick-tape"`(R17 的 lock 選擇器)。
內層 `overflow-y-auto` 不動(W-8 的「載入更多」鈕仍在捲動內容末端可達)。
空狀態盒 `h-40` 不動(它是獨立的 early-return 分支,不吃 `h-full`)。

> **算術驗證** `[amendment 2026-07-29: R14 —— 原表只驗 1920×1080,漏了 SC-6 量法自己指定的
> 1440×800,也沒把本輪讓五檔變高這件事算進去。下表全部改為 devtools 實測值]`
>
> | 視窗 | 模式 | main clientH | header | 圖表(實測) | gap | 下半列預算 | 判定 |
> |---|---|---|---|---|---|---|---|
> | 1920×1080 | 江波圖 | 1002 | 28 | 640 | 24 | **310** | ✅ 寬鬆 |
> | 1920×1080 | 日K | 1002 | 28 | 336 | 24 | **614** | ✅ 明細可見列數約 ×2 |
> | 1440×800 | 江波圖 | 722 | 30 | **440** | 24 | **228** | ⚠ **最緊**;現況此組合溢出 92px |
> | 1440×800 | 日K | 722 | 30 | 246 | 24 | **422** | ✅ |
>
> → **新五檔的高度預算 = ≤ 210px**(留 18px 餘裕給字級縮放),見 §5.1 A 高度預算節。
> 地板 `min-h-56` = 224px ≤ 228px(最緊格)→ 兩個驗收尺寸都不會頂到地板,SC-6 成立;
> 1280×720 以下才會頂到地板並讓 `<main>` 出現捲軸(SC-6 明訂的退化行為)。

### G. `frontend/src/index.css` — 🟢 全域捲軸樣式(SC-5)

```css
html {
  scrollbar-width: thin;
  scrollbar-color: var(--color-ink-dim) transparent;
}
```

- `[auto-default: 用標準屬性 scrollbar-width/scrollbar-color,不用 ::-webkit-scrollbar |
  reason: Chrome 121+ 兩者並存時標準屬性優先、webkit 規則會被忽略;標準屬性一條規則同時涵蓋
  Chrome/Firefox,且會被子元素繼承,不必逐容器掛 class]`
- 掛在 `html` 靠繼承生效於全站(含 TXO/期貨/指數頁)—— **這是期望效果**(統一視覺),
  但屬 §5「只改個股」的**刻意外溢**,在此標明。純視覺,不改任何行為(W-7 的 scroll 事件不受影響)。

### H. `docs/next-time.md` — 🟢 順手清單

Commit 前追加:
- next-time.md 既有 3 條 K 線待驗項可**劃掉**(本輪已驗:bars 116 根 / DK Open+Volume 欄位名成立 / 耗時 1.1–2.1s)。
- 新增:自選清單「全部」群組顯示空但主檔有資料(截圖 `stock-before.png` 可見)。
- 新增:server 版本可視性 —— 舊 build 佔 port 時前端無從辨識(本輪 K 線誤判的真正代價);
  候選做法 = 啟動 banner / `/api/health` 帶 git sha。
- 新增:CLAUDE.md §8 的「DK 只實證 H/L/C」可更新為「o/h/l/c/v 全實證(2026-07-29, 2317)」。

## 5.2 既有測試逐一分類

`[amendment 2026-07-29: R2/R6/R12 —— 原表漏列 3 個必紅 case、把 2 個不會紅的誤標成該紅。
下表已逐行對照實際測試檔重寫]`

### `OrderBook.test.tsx`(實際 8 個 case,全部列出)

| 行 | 案例 | 實際斷言 | 該紅? | 處置 |
|---|---|---|---|---|
| 15 | 渲染五檔價量(毫元 → 元) | `getByText("2385")` / `("461")` / `("2375")` | ⚪ **不該紅** — 新版式這些仍是各自獨立文字節點 | **保留原樣**;若紅 = 打到不該打的 |
| 24 | 漲停鎖死空側顯示 — | `getAllByText("—").length > 0` | ⚪ 不該紅(W-4) | 保留原樣 |
| 29 | 點價 dispatch `stock-price-click` | `fireEvent.click(getByText("2385"))` → detail 陣列 | ⚪ **不該紅**(W-1;點文字節點會冒泡到 `<button>`) | 保留原樣 |
| 45 | 總量列五檔加總 | `getByText(/委買 382/)` / `(/委賣 1033/)` | 🔴 **該紅** — 新版無「委買」前綴,且 1033 經 `toLocaleString("en-US")` 變 `1,033` | 改斷言為 **`getByText(/^382\s*張$/)` / `getByText(/^1,033\s*張$/)`**(R16:markup 是 `{n}<span>張</span>` 中間**無空白**,`getByText("382 張")` 會 miss;RTL 只正規化空白不會補) |
| 52 | 量 bar 依最大量歸一 | `[data-testid='depth-vol-bar']` 的 **`style.height`** = `100%` / `22%` | 🔴 **該紅** — 水平 bar 改用 `style.width` | 斷言 `height` → `width`(值 `100%` / `22%` 不變) |
| 66 | 排列順序 | `getAllByRole("button")` label 順序 `["買2 2375","買1 2380","賣1 2385","賣2 2390"]` | 🔴 **該紅** — 垂直雙欄是買1→買5 由上而下 | 改為 `["買1 2380","買2 2375","賣1 2385","賣2 2390"]` |
| 72 | 鎖漲停 / 鎖跌停 badge | `getByText("鎖漲停")` / `queryByText("鎖跌停")` | ⚪ **不該紅** — 純文字斷言,與 badge 在中央格或標題列無關 | **保留原樣**(要驗新位置另開 🟢 案例,不動這條) |
| 99 | 無鎖停時不顯示 badge | `queryByText(...)` 皆 null | ⚪ 不該紅 | 保留原樣 |

> ⚠ 第 55/60 行用 `getByRole("button", { name: "賣2 2390" })` 定位 → **W-16 的 aria-label
> 格式必須原封不動**,否則這條會以「找不到元素」而非「版式變了」的形式紅。

### 其餘測試檔

| 測試檔 | 案例 | 該紅? | 處置 |
|---|---|---|---|
| `DepthBar.test.tsx` | 全部 | ⚪ **不該紅**(W-6,檔案不動) | 零改動 |
| `FuturesPage.test.tsx:139` | 「渲染水平五檔(與個股共用 DepthBar)」 | ⚪ **不該紅**(W-6) | 只改測試**名稱**去掉「與個股共用」(🔵,不動斷言) |
| `StockChart.test.tsx:135` | 取數失敗顯示「無 K 線資料」 | 🔴 **該紅**(SC-3) | 改斷言為「K 線載入失敗」+ **`NOT_READY`**(非 `HTTP_503`,見 SC-3 amendment) |
| `StockChart.test.tsx` 其他 | 模式切換 / 往前 / 5分K 聚合 | ⚪ 不該紅(W-12) | 保留 |
| `CandleChart.test.tsx` | 蠟燭 / MA / **hover tooltip**(69 行)/ 空資料 | ⚪ **不該紅**(W-10/W-13/W-17;本輪只加 `select-none`) | 保留;**hover 案例紅 = 踩到 W-17,回頭看動到什麼** |
| `StockIntradayChart.test.tsx` | 走勢 / toggle / **hover**(129,140 行) | ⚪ **不該紅**(同上;該檔 `beforeEach` 把 `getBoundingClientRect` mock 成 width 800) | 保留;同上 |
| `StockPage.test.tsx:100` | 「選檔後中間主區 = 圖表切換 + **水平五檔** + 明細」;`getByRole("button",{name:"買1 2375"})` | ⚪ **不該紅**(W-16 保住 aria-label + role) | **斷言不動**;僅同步過期的測試**名稱**與 106 行 `// 水平五檔` 註解(🔵,併 commit 1) |
| `StockPage.test.tsx` 其他 | 狀態列 / 空狀態 / 右欄已移出 | ⚪ 不該紅 | 保留(class 變動不在斷言內) |
| `TickTape.test.tsx` | 全部既有 case | ⚪ **不該紅** — 斷言查列內容與「載入更多」鈕,不查 `max-h-80` | 既有零改動;**另加 1 條 🟢 護欄**(§5.3,R17) |
| `WatchlistSidebar.test.tsx` / `PriceLadder.test.tsx` | 全部 | ⚪ 不該紅(W-7/W-9) | 零改動 |
| backend `pytest`(1188) | 全部 | ⚪ **不該紅**(本輪零後端改動) | 零改動 |

## 5.3 新測試清單(🟢)

| 檔案 | 案例 | 對應 |
|---|---|---|
| `OrderBook.test.tsx` | 總量列顯示買賣總量 + 「張」+ 千分位(1085 → `1,085`) | SC-1 |
| `OrderBook.test.tsx` | 量 bar 寬度 = qty/maxQty(買側最大檔 100%、半量檔 50%) | SC-1 |
| `OrderBook.test.tsx` | 買側 bar 靠右(`right-0`)、賣側靠左(`left-0`) | SC-1 |
| `OrderBook.test.tsx` | 標題列右側顯示成交價 + 漲跌% | SC-1 |
| `OrderBook.test.tsx` | 鎖漲停 badge 出現在**標題列容器內**(不動既有 72 行文字斷言) | SC-1 / R6 |
| `OrderBook.test.tsx` | `book={null}` 與五檔全 0 量:不崩、bar 寬不含 `NaN` | R7 |
| `OrderBook.test.tsx` | `last={null}` + `ref_={null}`:不崩、成交價顯示 `—`、不出現 `NaN%` | R15 |
| `TickTape.test.tsx` | root class 含 `h-full` 且**不含** `max-h-80`(Option Z 另一半機制的護欄) | SC-6 / R17 |
| `StockChart.test.tsx` | `isError` 顯示「K 線載入失敗」且含 `NOT_READY` | SC-3 |
| `StockChart.test.tsx` | 取到空陣列 → 仍顯示「無 K 線資料」(不誤報失敗) | SC-3 / W-13 |
| `CandleChart.test.tsx` | `<figure>` class 含 `select-none` | SC-4 |
| `StockIntradayChart.test.tsx` | `<figure>` class 含 `select-none` | SC-4 |
| `StockPage.test.tsx` | `getByTestId("stock-lower-row")` 的 class 含 `flex-1` + `min-h-56`(SC-6 版面 regression lock) | SC-6 / R17 |

> `[amendment 2026-07-29: R1 —— 原訂「`<main>` 不含 `overflow-y-auto`」的 regression lock 撤銷]`
> Option Z 刻意保留 `overflow-y-auto` 當逃生口,鎖那條會鎖錯方向。改鎖「下半列吃剩餘高度」
> 這個真正的機制。
>
> SC-5(捲軸顏色)與 SC-6 的「實際不溢出」屬 CSS 佈局效果,jsdom 無版面引擎 → **不寫單元測試**,
> 走 Phase 7 真實環境 computed style + `scrollHeight/clientHeight` 量測驗收(量法見 SC-5 / SC-6)。

## 5.4 Commit 切分(鐵則 B 三類分離)

`[amendment 2026-07-29: R4 —— 原 commit 7 把 SC-1 新行為測試排在實作(commit 3)之後 = test-after,
違反鐵則 C 紅先行。新測試已全部前移併入 red commit]`

| # | 類 | 內容 |
|---|---|---|
| 1 | 🔵 | `DepthBar.tsx` 檔頭註解去掉「與個股共用」;`FuturesPage.test.tsx:139` 測試名同步;`StockPage.test.tsx:100/106` 名稱與註解去掉「水平五檔」(**皆不動斷言**) |
| 2 | 🔴 red | `OrderBook.test.tsx`:改 3 條該紅斷言(45/52/66 行)**+ 新增全部 SC-1 案例**(總量張數千分位 / bar 寬與方向 / 標題列成交價 / badge 在標題列 / `book=null` 與全 0 量);`StockChart.test.tsx:135` 改錯誤文案斷言 + 新增「空陣列仍顯示無 K 線資料」 |
| 3 | 🔴 green | `OrderBook.tsx` 垂直雙欄改寫(含 `Math.max(1,...)` 除零保護 + `book?.bids ?? []`)+ `StockChart.tsx` 錯誤態文案 |
| 4 | 🔴 red→green | SC-4 `select-none`:兩份圖表測試先紅 → `CandleChart.tsx` / `StockIntradayChart.tsx` 各加一個 class |
| 5 | 🔴 red→green | SC-6 版面:`StockPage.test.tsx`(`stock-lower-row` 含 `flex-1`+`min-h-56`)與 `TickTape.test.tsx`(root 含 `h-full` 不含 `max-h-80`)兩條 lock 先紅 → `StockPage.tsx`(下半列 `flex-1 min-h-56` + testid、五檔 wrapper `self-start`、`StockChart` root `shrink-0`)+ `TickTape.tsx`(`max-h-80`→`h-full` + testid) |
| 6 | 🟢 | `index.css` 全域捲軸樣式 |
| 7 | chore | `docs/next-time.md` |

> 每個 🔴 commit 都是完整的 red→green 對(2+3 因跨兩檔實作而拆成兩個 commit,
> commit 2 落地時測試是紅的 —— 這是 TDD 的預期狀態,不是壞掉)。

## 5.5 Known Risks

(Phase 3 review 後填;目前無)

self_review_head: 6e6c6b4e6207e2d661e3763a9b8059c203172da9
