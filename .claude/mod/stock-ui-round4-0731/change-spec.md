# Change Spec — 個股 UI round 4

分支 `mod/stock-ui-round4`。Phase 1 現況見 `current-state.md`(同目錄)。

## Phase 2 分流判定

**判定 = 已成形改法(grilling 姿態)**。命中判準:user prompt 逐項給出「現況 → 目標」的
具體改法(6 項、11 個子項),含參考實作指名(trading-king 分時圖)與落點指名
(「分時圖上方加新增按鈕」「左邊是群組右邊是股票」)。

**拍板替代來源(/auto 契約)**:user 在同一則 prompt 內**顯式預先授權**了決策路徑 ——
「如果有決策問題請開 subagent 用 /adhd 並由 fable5 決定要使用哪個決策」「如果有 UI/UX
問題請使用 /frontend-design 跟 /bencium-controlled-ux-designer」「直接一步到底」。
據此不停等,改由兩個 dispatch 拍板,結果全部落在本檔:

- `adhd` + fable5 → 資料流 / 流程四題(D1 高低標記資料源、D2 hover 價位、D3 預覽流程、D4 側欄種子)
- `frontend-design` + `bencium-controlled-ux-designer` → 視覺六題(U1..U6)

兩份拍板衝突處由主 session 收斂,收斂結果標 `[auto-default]`(見 §決策紀錄)。

---

## §1 改完的成功條件(畫面可指認)

### 項 1 — 高低標記

- **SC-1.1**(分時圖)當日最高價位置畫一個**灰色朝上三角 ▲**,**尖端(apex)正好壓在最高價的
  y 上、三角body 朝圖內(向下)延伸 6px**;三角上方 5px 有**灰色價位數字**;
  **整張分時圖不再有任何橫貫左右的高低虛線**(y 軸格線的細虛線不算)。
  最低價同款:朝下三角 ▼,尖端壓在最低價 y、body 向上延伸,數字在三角下方。
  `[amendment 2026-07-30: R8 —— 原文「尖端貼在最高價 y」與 C2 的 points(底邊在 y−1、
  尖端在 y−6)互斥。改採「apex 貼價位、body 朝圖內」,同時解掉 R1 的三角出界。]`
- **SC-1.2**(分時圖)三角的 x = **該最高價被摸到的那一分鐘**(不是最後一分鐘、不是收盤最高
  的分鐘)。數字內容 = 當日最高成交價,**與 `/api/stock/state/{code}` snapshot 的 top-level
  `high` 毫元 ÷1000 同值**。
  `[amendment 2026-07-30: R12 —— 原文對照「資訊列的當日高」,但分時圖資訊列(ChartReadout)
  只有 時間/價/漲跌%/量/外/內,沒有當日高欄,對照物不存在。]`
- **SC-1.3**(K 線圖)可視窗口最高價那根蠟燭的**影線頂端**有灰色朝上三角(apex 貼在高價 y、
  body 向下),價位數字因為頂到圖框而畫在三角**下方**;最低同款在最低那根影線底端、
  數字畫在三角**上方**(不落進下方成交量區)。**沒有橫貫左右的虛線**。
  **三角三個頂點與價位數字都必須完整落在 viewBox 內(不被裁)。**
  `[amendment 2026-07-30: R1 —— 常態(BB 關閉)下 toY(windowHigh)=PAD_Y=6、
  toY(windowLow)=434 而 priceBottom=440,原規格的三角會被裁、低標文字會壓在量柱上。]`
- **SC-1.4**(K 線圖)滾輪縮放 / 拖曳平移後,三角會跟著跳到新視窗的高低那根上,
  數字與底列 figcaption 的「高 x / 低 y」**永遠相同**。
- **SC-1.5**(邊界)漲停鎖死(當日高 = 當日低)時分時圖**只畫一個朝上三角**,不畫朝下的。

### 項 2 — 移除即時價位文字

- **SC-2.1** 分時圖走勢線末端只剩**一顆圓點**(顏色仍依漲跌紅/綠/灰),
  圓點旁邊**沒有任何價位數字**。右緣 CDP/MA 價位標不受影響。

### 項 3 — hover tooltip 加價位

- **SC-3.1** 滑鼠在分時圖上移動時,圖表**底部貼齊下緣**浮出一個深色圓角小框,
  **上行黃色 `HH:MM`、下行紅色 / 綠色 / 白色的價位數字**,兩行置中。
- **SC-3.2** 該價位數字 = 圖表左上角資訊列同一分鐘顯示的價格(同格式、同值)。
- **SC-3.3** 把游標沿走勢線掃過當日翻黑的時點,下行顏色會在紅 ↔ 綠切換,上行恆黃。
- **SC-3.4** 滑到沒有成交的分鐘(如 12:00 空窗)時,整個底部標籤**不出現**(既有行為)。

### 項 4 — 自選

- **SC-4.1**(Dialog 位置與版面)點「管理」後 dialog 出現在**視窗正中央**(不是左上角),
  寬約 896px / 高約 480px(小視窗等比縮),**左右兩欄**由一條分隔線切開。
- **SC-4.2**(Dialog 左欄)最上面固定一列「**未分組**」(沒有 ✎ / × 兩顆圖示),其下是自訂群組;
  點某一組 → 該列左緣出現**桃紅直線**且底色變深,右欄同步換成該組股票。
- **SC-4.3**(Dialog 右欄)每列 = 代號(等寬)/ 灰色股票名 / 若該檔還屬別組則有灰色小方框標示
  組名 / 最右一顆 ×;**畫面上找不到任何 checkbox**。右欄頂端有搜尋框可把股票加進本組。
- **SC-4.4**(群組整塊折疊)滑鼠移到群組標題**整條**(從 `▾` 到右邊的計數)時整條背景變亮一階;
  點標題文字或計數同樣會折疊,箭頭變 `▸`。Tab 可停在標題上、Enter / 空白鍵同樣折疊。
- **SC-4.5**(預覽流程)在側欄搜尋框輸入股號 / 名稱按 **Enter**(或點「新增」、或點提示列),
  **該檔不會出現在自選清單**,而是直接在主區顯示它的分時圖與報價。
- **SC-4.6**(加入按鈕)看的是**非自選**個股時,分時圖上方的報價 header 出現「**加入自選**」按鈕;
  點它展開群組清單(含「未分組」),選一個 → 該檔立刻出現在側欄對應群組下,按鈕消失。
- **SC-4.7**(側欄列)側欄每列變兩行:左上放大的等寬**代號**、左下灰色**股票名稱**;
  右上放大的**現價**、右下紅 / 綠**漲跌百分比**。側欄寬度不變、無橫向捲軸。
- **SC-4.8**(盤後 / 開頁種子)重新整理頁面後,側欄各列**立刻**有價位(不是全 `-`);
  當日尚無成交(盤前 / 盤後冷載入)時顯示**灰色的參考價 + 灰色「參考」二字**,
  不顯示 `0.00%`,也不把參考價印成一般價格色。

### 項 5 — 字級

- **SC-5.1** 側欄的代號與現價字級從 0.875rem 提到 **1rem**(視覺上明顯變大),
  名稱與漲幅維持 0.75rem。

### 項 6 — 分時圖左緣價位帶

- **SC-6.1** 左緣價位數字全部**右對齊成一直欄**,右緣距離最左那條垂直格線約 4px
  (改前約 19~22px)。
- **SC-6.2** 每個價位數字的**垂直中心壓在對應水平虛線上**(不再整體浮在線上方),
  最上 / 最下兩個刻度同樣對齊且沒被裁掉。
- **SC-6.3** 字級由 0.625rem 縮到 **0.5625rem**(與右緣 CDP 價位標同級)。
- **SC-6.4** hover 時左緣浮出的深色價位框**框寬與價位帶同寬**(右緣不越過第一條垂直格線),
  框內數字與上下靜態刻度**右緣對齊在同一條線上**。

### 量化條件

| 條件 | 量法 | 目標 |
|---|---|---|
| 前端測試 | `npm test -- --run`(frontend/) | 全綠,**新增測試 ≥ 20 條** |
| 後端測試 | `.venv\Scripts\python -m pytest -q` | 全綠 |
| 型別 | `npx tsc -b`(frontend/)+ `.venv\Scripts\python -m pyright` | 0 error |
| Lint | `npx eslint src`(frontend/)+ `.venv\Scripts\python -m ruff check copycat tests` | 0 error |

---

## §2 不能破壞的既有行為白名單

> Phase 5 review 的 (b) 焦點必讀本節。

- **W-1** `minuteOf` **不 snap 最近**:滑到沒資料的分鐘 → 垂直線 / 資料點 / 時間標都不畫;
  滑到左緣價位帶內(`x < Y_AXIS_W`)不對應任何分鐘(不夾制成 09:00)。
- **W-2** hover **水平線是自由量尺**(跟滑鼠 y,不鎖收盤價);左緣 `price-tag` 顯示的是
  `snapDown(priceAtY(mouseY))` = 可下單的合法檔位。**本輪不改這個語意**。
- **W-3** `ChartStatic` / `EnergySub` / K 線 `ChartStatic` 的 **memo 不可被打穿**:
  傳進去的必須是純量或 `useMemo` 穩定 identity 的陣列(每 mousemove 都會 re-render 父層)。
- **W-4** `toY` / `priceAtY` 必須共用同一組 `PAD_Y` / `X_LABEL_H`(互逆);
  `minuteToX` / `minuteOf` 必須共用 `Y_AXIS_W` / `plotWidth`。
- **W-5** 高低標記沿用「**域外不畫**」規則(y 超出 `yDomain` → 不畫)。
- **W-6** 分時圖無昨收(`hasRef === false`)時:走勢線單色 accent、不畫紅綠填色。
- **W-7** K 線圖 `showVolume === false`(指數頁櫃買 MIS)時量區印「無量資料」不畫 0 柱;
  資訊列量欄印 `—`。**`MarketChart` 的既有行為不得改變**(除了高低標記的呈現同步變)。
- **W-8** K 線圖 hover 的 `hoverIdx` 由 **viewBox 座標**每次 render 反查(不存 bar index);
  縮放錨點守恆。
- **W-9** `commit()` 的**零 PUT 早退**(內容相同不送 PUT — 會讓後端 TC4 全量 UNSUB/SUB)。
  側欄、Dialog、**以及本輪新增的 StockPage 加入入口,共三處**都要有
  `[amendment 2026-07-30: R16]`。
- **W-10** `addCode` / `assignToGroup` / `moveToGroup` / `detachFromGroups` / `removeCode` /
  `removeFromGroup` / `reorderUngrouped` 的**純函數語意與不變式**不動
  (未分組 = `codes − ∪groups` 衍生不另存)。
- **W-11** 側欄**拖曳四條落點路徑**(未分組↔群組、組內排序、拖出側欄作廢、Esc 取消)全部保留;
  拖曳中 `pointermove` **每次重算幾何**。
- **W-12** `<dialog>` 的 `open` **不進 JSX**,開關只走 `showModal()` / `close()` 那條 effect;
  jsdom 無 `showModal` 時走 `setAttribute("open")` fallback。關閉時不渲染內容。
- **W-13** Dialog 內改名輸入框 Escape **只取消改名不關 dialog**(`stopPropagation`)。
- **W-14** 群組撞名 / 空白名 → 零 PUT + `BAD_GROUP` 文案(`addGroup` / `renameGroup` 回原物件)。
- **W-15** `useStockNames` 取不到表(後端表不可用)時回空陣列,**「直接打完整股號 Enter」
  那條路徑照樣可用**。
- **W-16** 側欄搜尋框 **sticky 恆存**;Escape 清空輸入。
- **W-17** WS `watchlist_quote` 的 **1s 節流合併**語意不變(`_flush_watchlist_loop` 只推 dirty)。
- **W-18** `stream()` 的 per-client 有界 queue「滿丟最舊」不變。
- **W-19** 個股 snapshot 既有欄位形狀不變(`seq/last/vwap/high/low/cum_*/minutes/ticks/book/meta`);
  本輪只**加**欄位。
- **W-20** 前端 seq 跳號 → 全量 refetch + pending buffer 的對齊邏輯不動。
- **W-21** 刪組後側欄清折疊孤兒(`onGroupDeleted` → `dropCollapsed`)。
- **W-22** 折疊狀態 localStorage 鍵 `copycat-stock-wl-collapsed` / `copycat-stock-wl-ungrouped-collapsed`
  的**值格式不變**(舊使用者的折疊狀態要能沿用)。
- **W-23** 兩張圖的**框外 chrome 逐項對稱**(頂列 `h-[1.375rem]` + `mb-1`、底列 `mt-1` + `h-4`),
  切換模式時圖表區塊高度不跳。
- **W-24** `StockChart` 的量測 wrapper 恆存(loading / error / data 三態都掛在它底下)。

### 本輪**刻意改變**的既有行為(事前登記 = 鐵則 E 改 assertion 的合法通道)

| 代號 | 舊行為 | 新行為 | 受影響測試 |
|---|---|---|---|
| B-1 | 分時圖當日高低畫橫虛線 + 右緣 label | 三角標記 + 就地價位文字 | `StockIntradayChart.test.tsx` day-high/low 斷言 |
| B-2 | K 線圖視窗高低畫橫虛線 + 右緣 label | 三角標記(落在該根蠟燭)+ 就地文字 | **無既有測試**(grep 全 `frontend/src`,`window-high`/`window-low` 只出現在 `CandleChart.tsx` 本身)→ 先寫新版紅測試再實作 `[amendment 2026-07-30: R14]` |
| B-3 | 分時圖畫 `last-price` 文字 | **移除**(只留 `last-dot`) | `StockIntradayChart.test.tsx` |
| B-4 | `Y_AXIS_W = 46`、刻度文字 `x=2` 左對齊、baseline `t.y-2`、0.625rem | `36` / 右對齊 `x=32` / `dy=0.35em` / 0.5625rem | `StockIntradayChart.test.tsx`(符號斷言自動跟隨;`:274` 註解 + `price-tag` 寬度要動)+ **`stock-intraday-svg.test.ts:65` `expect(Y_AXIS_W).toBe(46)`** `[amendment 2026-07-30: R4]` |
| B-5 | 側欄搜尋 Enter / 新增鈕 / 點提示列 → **立刻加入自選** | → **改為預覽**(`onSelect`),不發 PUT | `WatchlistSidebar.test.tsx` 4 支 |
| B-6 | 群組 header 只有 `▸/▾` 按鈕可折疊,`aria-label="折疊 X"` | 整條 header 是 button,`aria-expanded` + 可見文字當可及名稱,**移除該 aria-label** | `WatchlistSidebar.test.tsx` 折疊斷言 |
| B-7 | 側欄列高 44(`ROW_H = 44`)、單行、無名稱 | 列高 52(`ROW_H = 52` 且由 inline style 單一來源)、兩行、有名稱 | `WatchlistSidebar.test.tsx`(含 `QUOTES` fixture 補 `ref` 欄,`[amendment 2026-07-30: R10]`) |
| B-8 | Dialog `w-96` 上下兩段 + checkbox 矩陣;股票區列 `wl.codes` **全體**、每列一顆「從自選移除」 | 置中 896×480 左右兩欄 + 右欄搜尋加入;右欄真群組列**兩顆鈕**(`−` 移出本組 / `×` 從自選移除)以保住「一步移除」入口 `[amendment 2026-07-30: R17]` | `WatchlistManagerDialog.test.tsx` 大改 |

---

## §3 Backward compat / migration

- **後端 → 前端(snapshot)**:`minutes.<key>` **加** `h` / `l` 兩個 key。
  舊前端忽略未知 key;新前端對缺 key 走 `v.h ?? v.c`(降級後等值反查通常落空 → 標記不畫,
  **不畫錯位置**)。
- **後端 → 前端(WS `watchlist_quote`)**:**加** `ref` key。舊前端 `?? null` 忽略;
  新前端收舊後端訊息時 `ref` 為 undefined → `?? null` → 顯示 `-`(= 現況)。
  **`p` 欄位語意不變** —— 參考價**絕不**寫進 `p`(否則新舊 client 都會把昨收讀成今價)。
- **WS tick 訊息**:零改動(`h` / `l` 已存在)。
- **localStorage**:零改動(折疊鍵格式不變;`stock-main-code` 語意不變)。
- **`watchlists/*.json` / `stock_watchlist.py` schema**:零改動。
- **`CandleChart` props**:零改動(`showVolume` / `height` / `initBars` / `showBb` 全留);
  高低標記是內部呈現改動,`MarketChart` 不需改一行。
- **無 migration 檔 / 無 schema 遷移** → 可逆性 = `git revert` 即可,無資料面殘留。

---

## §4 Out of scope

- ❌ 期貨 / 選擇權 / 指數 / 相關係數頁的任何功能改動(K 線圖高低標記的呈現同步變是
  **共用元件的必然外溢**,已列 W-7 保護其餘行為)。
- ❌ `docs/next-time.md` 既有待辦(TickTape / PriceLadder / localStorage key 收斂 / 效能候選)。
- ❌ 側欄 `EMPTY_WL` fallback 在載入失敗時仍可能被寫入的既有洞(本輪只在**新入口**加 gate,
  側欄既有入口不動 → 寫進 next-time)。
- ❌ 首 tick 點亮動畫 / sparkline / 月亮太陽轉場等裝飾。
- ❌ 分時圖與 1 分 K 的一鍵切換(per-minute h/l 進 MinuteAgg 後幾乎免費,但不在本輪)。
- ❌ 側欄與 header 兩處 mutation 的 last-write-wins(既有風險,非本輪新增)。

---

## §5 決策紀錄

| 編號 | 決策 | 來源 | 標記 |
|---|---|---|---|
| D1 | 分時圖高低:後端 `MinuteAgg` 加 per-minute `high_milli`/`low_milli`;**值取 top-level `accum.high`**,位置取**第一個 `minute.h === accum.high` 的分鐘**,反查不到 → 不畫 | fable5 | `[auto-default: 等值反查 \| reason: 降級時「不畫」比「畫在收盤最高的分鐘」誠實 —— 位置錯 = 資料錯]` |
| D1b | fable 建議「無漲跌停 fallback 域納入 high/low」**不採用** | 主 session 收斂 | `[auto-default: 維持現況域計算 \| reason: 有漲跌停時域恆為 [lower,upper] 必裝得下;fallback 域已有 1.1× 邊,實務不觸發。改域會動到既有 y 域測試 = 為極罕情境付 scope]` |
| D2 | hover tag 值 = 該分鐘收盤 `minutes.get(hoverMin).c`;版面 = 同框兩行往上長 | fable5 + UI 一致 | — |
| D2b | tag 尺寸取 UI 版 `{w:40, h:24}`;價位**上色**(相對昨收紅/綠/白)取 UI 版(fable 主張中性白) | 主 session 收斂 | `[auto-default: 採 UI 版上色 \| reason: 本圖每個價格輸出都已相對昨收上色,唯獨 hover 讀數白色會是唯一無漲跌語意的價格]` |
| D3 | 搜尋 → `onSelect` 預覽(零新增 state);「加入自選」按鈕放 `StockPage` header;`addCode + assignToGroup` **合成單次 PUT** | fable5 | — |
| D3b | 新入口以 `useStockWatchlist().data !== undefined` 為 gate(載入中 / 失敗不渲染按鈕) | fable5 | — |
| D4 | 側欄種子:`stream()` per-client 種子 + `set_watchlist` added 廣播 + meta/no_data 轉態補推;`last is None` 時帶獨立 `ref` 欄位 | fable5 | — |
| U1 | 高低標記 = **▲/▼ 三角 + 價位文字**,顏色 `ink-muted`(不用紅綠) | frontend-design / bencium | `[auto-default: 三角非圓點 \| reason: 圓點會與 last-dot(r=3)、hover 收盤錨(r=2.5)混淆;形狀承載方向不依賴顏色]` |
| U1b | K 線圖 figcaption「高 x / 低 y」**保留** | UI | — |
| U2 | `Y_AXIS_W` 46→36、刻度右對齊 `x=32`、`dy="0.35em"`、0.5625rem;`PRICE_TAG.w = Y_AXIS_W` **維持綁定** | UI | — |
| U4 | Dialog `m-auto`(Tailwind v4 preflight 把 `margin:0` 套到 dialog,是「不在中間」的根因)+ 896×480 兩欄;「未分組」當左欄第一列偽群組 | UI | — |
| U5 | 側欄兩行式、列高 44→52、`ROW_H` 同步 | UI | — |
| U6 | 整條 header 換成 `<button>` + `aria-expanded` + `aria-controls`;`▸/▾` 降級 `aria-hidden` | UI | — |

---

# Phase 3 — Diff 級規格

三類標記:🔴 行為改動(既有測試該紅)/ 🟢 新功能(加新測試)/ 🔵 純重構(測試不該變)。

## C1 🟢 per-minute 高低(資料地基)

### `copycat/live/stock_state.py`
- `MinuteAgg` 加 `high_milli: int | None = None` / `low_milli: int | None = None`。
  **預設必須是 `None` 不是 0** —— `min(0, x)` 會把最低價永久卡在 0。
- `_apply()`:在 `agg.close_milli = tick.price_milli` 同批
  `agg.high_milli = p if agg.high_milli is None else max(...)`,low 同理。
- `snapshot()` 的 minutes dict 每筆加 `"h": m.high_milli, "l": m.low_milli`。
- `reset()` 不需動(整個 `minutes` 重建)。

### `frontend/src/lib/stock-accum.ts`
- `MinuteAgg` 加**選填** `h?: number | null` / `l?: number | null`
  (必填會讓 `stock-intraday-svg.test.ts:16` 的 helper 與多處 fixture 整批 tsc 紅)。
- `fromSnapshot`:`{ ...v, h: v.h ?? null, l: v.l ?? null }`
  `[amendment 2026-07-30: R2 —— 原本寫 `?? v.c`。舊後端降級時每分鐘 h 都 = 收盤價,
  而 `accum.high` 是 tick 級 running max;只要日高恰等於某分鐘收盤(漲停鎖死後每分鐘都是),
  等值反查會**命中錯的分鐘**而不是落空 → 靜默畫錯位置。填 null 才真的做到「缺資料不畫」。]`
- `applyTick`:
  ```
  h: prev.h == null && prev.v > 0 ? null : Math.max(prev.h ?? msg.p, msg.p)
  l: prev.l == null && prev.v > 0 ? null : Math.min(prev.l ?? msg.p, msg.p)
  ```
  三條路徑:新建空 agg(`v === 0`)→ `msg.p`;新後端來的 agg(h 是數字)→ max/min;
  舊後端來的 agg(h 為 null 且 `v > 0` = 高低未知)→ **保持 null**
  (不可用「本次載入後看到的 tick」冒充整分鐘高低)。

**新測試**
- `tests/live/test_stock_state.py`:同分鐘三筆(中→高→低)→ `minutes[k].high_milli/low_milli`
  正確;`snapshot()["minutes"]["540"]` 含 `h`/`l`;`apply_backfill` 重放後 per-minute h/l
  與逐 tick ingest 等值(等值反查在三條路徑下恆成立的證據)。
- `frontend/src/lib/stock-accum.test.ts`:降級(snapshot minutes 無 h/l → `h === null`);
  `applyTick` 同分鐘三筆的 h/l;新分鐘首筆 h = l = p;
  **舊 agg(h=null, v>0)再吃一筆 tick → h 仍為 null**。

## C2 🔴 分時圖高低標記(B-1)+ 移除即時價位文字(B-3)

### `frontend/src/lib/stock-intraday-svg.ts`
- `Input` 加選填 `high?: number | null` / `low?: number | null`。
- `IntradayGeometry` 加 `highMark: ExtremeMark | null` / `lowMark: ExtremeMark | null`,
  `interface ExtremeMark { x: number; y: number; priceMilli: number }`。
- 建構規則(**等值反查**):
  ```
  const markFor = (target, pick /* "h" | "l" */) => {
    if (target == null) return null;
    if (target < yBottom || target > yTop) return null;   // W-5 域外不畫
    const hit = entries.find(([, m]) => (pick === "h" ? m.h : m.l) === target);
    return hit === undefined ? null : { x: toX(hit[0]), y: toY(target), priceMilli: target };
  };
  highMark = markFor(input.high, "h");
  lowMark  = input.low === input.high ? null : markFor(input.low, "l");   // SC-1.5
  ```
- **不動** `yDomain` 計算(D1b)。

### `frontend/src/components/stock/StockIntradayChart.tsx`
- `buildIntradayGeometry` 兩處呼叫加 `high: accum.high, low: accum.low`
  (deps 補 `accum.high` / `accum.low`)。
- `ChartStatic` props:**刪** `highMilli` / `lowMilli` / `highY` / `lowY` 四個,
  改吃 `highMark` / `lowMark`(來自 `g`,已在 `g` 內 → 直接用 `g.highMark`,props 淨刪 4 個)。
- 刪掉 230-261 的橫線 + 右緣 label 區塊,改畫(**共用 helper `extremeMark()`,K 線圖同一份**):
  ```
  高:<polygon data-testid="day-high" points={`${x},${y} ${x-3.5},${y+6} ${x+3.5},${y+6}`} … />
      // apex 在 (x, y) = 價位本身,body 朝圖內(向下)
  低:<polygon data-testid="day-low"  points={`${x},${y} ${x-3.5},${y-6} ${x+3.5},${y-6}`} … />
      className="fill-ink-muted stroke-surface" strokeWidth={1} paintOrder="stroke"
  文字:<text data-testid="day-high-label" x={clampTextX(x)} y={labelY} textAnchor="middle"
        className="fill-ink-muted stroke-surface" strokeWidth={2} paintOrder="stroke"
        fontSize="0.5625rem">{fmt(priceMilli)}</text>
  ```
  `[amendment 2026-07-30: R8/R1 —— 三角改「apex 貼價位、body 朝圖內」。body 永遠朝圖的內側
   延伸,兩張圖都不可能被 viewBox 裁掉,且 SC 文字與 points 一致。]`
  - `labelY`:
    - 高:預設 `y - 5`;若 `y - 5 < 9`(頂到框)→ 改畫在三角下方 `y + 15`。
    - 低:預設 `y + 12`;若 `y + 12 > bottomLimit`(頂到底)→ 改畫在三角上方 `y - 10`。
    - 分時圖 `bottomLimit = plotBottom - 2`。
  - `clampTextX(x) = clamp(x, Y_AXIS_W + 16, w - R_AXIS_W - 16)`。
- 刪 `inDomain` / `dayHighY` / `dayLowY`(移進 geometry)。
- **刪** `last-price` `<text>`(SC-2.1),保留 `last-dot` `<circle>`。

**測試**(🔴 該紅:既有 `day-high` line 屬性斷言 / `last-price` 存在斷言)
- **fixture 必須先重造**`[amendment 2026-07-30: R3]`:`StockIntradayChart.test.tsx` 的
  `ACCUM` 走 `fromSnapshot`,minutes 只有 `{c,v,i,o,u}` → C1 之後 `h` 全為 null;
  而 `withHL(2_395_000, 2_370_000)` 的兩個值不等於任何分鐘的 h/l → 標記恆不畫,
  只改斷言形狀**無法**變綠。作法:
  - 給 `ACCUM` 的 minutes 補 `h`/`l`(例 541: `h: 2_395_000, l: 2_370_000`),
    使 `withHL` 的值有等值分鐘可反查。
  - **三條 null 路徑分開測**:(a) 域外(值超出 yDomain)、(b) 域內但無等值分鐘
    (反查落空)、(c) minutes 缺 h/l(舊後端降級)—— 三者都不畫,但成因不同。
- 改寫:`day-high` 現在是 `<polygon>`,斷言 points 第一組座標 = `(x, y)`(apex 貼價位)、
  `day-high-label` 文字內容。
- 新增:高 = 低(漲停鎖死)只畫一個標記;標記 x 對應「摸到高價的那一分鐘」而非最後一分鐘;
  `last-price` 不存在;高標 y 接近頂端時文字翻到三角下方。
- `stock-intraday-svg.test.ts` 新增 `highMark` / `lowMark` 的建構測試(含域外 / 落空 / 缺欄三態)。

## C3 🔴 K 線圖視窗高低標記(B-2)

### `frontend/src/components/stock/CandleChart.tsx`
- 算 `highIdx = shown.findIndex(b => b.h === windowHigh)` / `lowIdx = findIndex(b => b.l === windowLow)`
  (取**最早出現**那根)。
- `ChartStatic` props:`highY`/`lowY`/`highText`/`lowText` 改為
  `highMark: {cx,y,text} | null` / `lowMark`(`cx` 由 `g.candles[idx]?.cx`,缺 → null)。
  **兩個物件必須 `useMemo`**(W-3 memo 紀律)。
- 畫法同 C2(apex 貼價位、body 朝圖內),尺寸放大(viewBox 1400):三角半寬 5 / 高 8、
  字級 `0.625rem`、`clampTextX = clamp(cx, 20, w - 20)`。
  - 高 label 預設 `y - 6`;`y - 6 < 11` → `y + 19`。
  - 低 label 預設 `y + 16`;`y + 16 > priceBottom - 2` → `y - 12`。
- **`buildCandleGeometry` 回傳新增 `priceBottom: number`**`[amendment 2026-07-30: R1]`
  —— K 線的價格區底 = `(dimH − X_LABEL_H) × (1 − VOL_RATIO)`(實測 578 → 440),
  **不是** `plotBottom`(564)。元件端**不可自己重算 `VOL_RATIO`**(兩處各寫一份必漂移,
  同 W-4 的教訓);退化分支(`bars` 空)也要一併回傳。
  - ⚠ 常態(BB 關閉):`toY(windowHigh) === PAD_Y === 6` → 高標文字**必然翻到三角下方**;
    `toY(windowLow) === 434`、`434 + 16 > 438` → 低標文字**必然翻到三角上方**。
    兩者都是規格內建路徑不是邊界,測試要正面覆蓋。
- `figcaption` 的「高 / 低」**保留**(U1b);`highText`/`lowText` 仍是同一個字串來源(SC-1.4)。

**測試**`[amendment 2026-07-30: R14 —— grep 全 frontend/src,`window-high`/`window-low`
只出現在 `CandleChart.tsx` 本身,**測試檔零命中**。B-2 原本登記「既有斷言該紅」是錯的:
現況零覆蓋,無既有紅可製造。改為「先寫新版紅測試 → 再實作」(鐵則 C 的等價路徑 ——
被改的行為本身就要被新測試取代,寫 characterization 再立刻刪是純浪費)。]`
- 🟢/🔴 先寫新測試(此時紅):`window-high` 是 `<polygon>` 且 apex = `(cx, toY(windowHigh))`;
  `window-high-label` 文字 = figcaption 的「高」值;標記 cx = 最高那根蠟燭的 cx;
  縮放/平移後標記換根;高標文字 y > 三角 apex y(翻到下方);低標文字 y < apex y(翻到上方);
  **不存在** `strokeDasharray="4 3"` 的橫貫虛線。
- `MarketChart` 相關既有測試(指數頁)**不該紅** —— 若紅代表打到 W-7。

## C4 🔴 分時圖左緣價位帶(B-4)

### `frontend/src/lib/stock-intraday-svg.ts`
- `Y_AXIS_W` 46 → **36**(註解同步改寫理由)。

### `frontend/src/components/stock/StockIntradayChart.tsx`
- y 刻度文字:`x={Y_AXIS_W - 4}`、`textAnchor="end"`、`y={t.y}` + `dy="0.35em"`、
  `fontSize="0.5625rem"`;**移除** `Math.min(Math.max(t.y - 2, 8), h - 16)` 夾制。
- `PRICE_TAG = { w: Y_AXIS_W, h: 14 }` **維持綁定**;標內文字改
  `x={PRICE_TAG.w - 4}` / `textAnchor="end"` / `fontSize="0.5625rem"`(y 維持 `h - 4`)。

**測試**(🔴 該紅)
- **`stock-intraday-svg.test.ts:65` `expect(Y_AXIS_W).toBe(46)` 必紅**
  `[amendment 2026-07-30: R4 —— B-4 原本只登記 `StockIntradayChart.test.tsx`,漏了這條
  硬編 46;未登記就改 assertion 等於鐵則 E 的繞過手段]`。改法不是把 46 換成 36,而是
  改成守**語意**:該支測的是「hover 價位標整格塞進價位帶」→ 移到元件測試斷言
  `PRICE_TAG 的 width attr === Y_AXIS_W`;純函數測試只留
  `expect(minuteToX(X_START_MIN, W)).toBeCloseTo(Y_AXIS_W)`。
- `StockIntradayChart.test.tsx`:既有斷言多數用符號 `Y_AXIS_W` → 自動跟隨;
  需改的是 `:274` 註解(寫死 46)與 `price-tag` 寬度斷言。
- 新增:刻度 text 的 `text-anchor === "end"`、`dy === "0.35em"`、`y === t.y`(不再有偏移)、
  `x === Y_AXIS_W - 4`。

## C5 🟢 hover tag 加價位(SC-3)

### `frontend/src/components/stock/StockIntradayChart.tsx`
- `TIME_TAG = { w: 40, h: 24 }`(常數改值 → `tagSpan` 自動變寬,`XAxisLabels` 一行不用動)。
- tag `<g transform={translate(timeTagX, mainH - TIME_TAG.h)}>`,rect `width=40 height=24`。
- 兩行 `<text>`:
  - 時間 `x={20} y={10}` `textAnchor="middle"` `fontSize="0.625rem"` `className="fill-time"`。
  - 價位 `data-testid="time-tag-price"` `x={20} y={21}` 同 anchor / 字級,判色式:
    ```
    ref == null ? "fill-ink" : c > ref ? "fill-bull" : c < ref ? "fill-bear" : "fill-ink"
    ```
    `[amendment 2026-07-30: R5 —— 原式 `c > ref ? …` 在 `ref === null` 時,JS 會把 null
    強轉 0,毫元正整數恆 `> 0` → 無昨收的商品被塗成紅色,打穿 W-6 / `hasRef` 紀律。
    **null 檢查必須放最前面。**]`
- 值 = `hoverAgg.c` 經 `fmt()`(與資訊列同源,SC-3.2)。
- 退化:`hoverMin === null` 時整個 tag 本來就不畫(W-1)→ 無需新分支。

**新測試**:hover 有資料分鐘 → `time-tag-price` 文字 = 該分鐘 `fmt(c)`;
高於昨收 → class 含 `fill-bull`;低於 → `fill-bear`;
**`meta.ref` 為 null → class 含 `fill-ink` 且不含 `fill-bull`**(R5 的回歸守衛);
rect height = 24;hover 無資料分鐘 → tag 不存在(回歸 W-1)。

## C6 🟢 側欄 quote 種子 + 參考價(SC-4.8)

### `copycat/server/stock_engine.py`
- 新增 `_quote_payload(self, code: str) -> dict`:
  ```
  state = self._states.get(code); last = state.last if state else None
  meta = state.meta if state else None
  if last is not None: p/chg_pct/vol 照現行算 ; ref = None
  else:               p = chg_pct = vol = None ; ref = meta.ref_milli if meta else None
  return {"type":"watchlist_quote","code":code,"p":p,"chg_pct":chg_pct,"vol":vol,
          "ref":ref,"no_data": code in self._no_data}
  ```
- `stream()`:`self._clients.add(queue)` 之後、回傳 `_gen()` 之前,對 `self._watchlist`
  逐檔 `queue.put_nowait(self._quote_payload(code))`。
  **不可用 `_publish`**(會打到所有 client)。同步區間無 await → 對 event loop 原子。
- `set_watchlist()`**必須先把 `self._watchlist = list(codes)` 前移**
  `[amendment 2026-07-30: R7]`:現況(`:140-153`)`_watchlist` 是在所有
  `await asyncio.to_thread(self._acquire, …)` **跑完之後**才指派,而每個 `await` 都讓出
  event loop、TC4 在 SUB 後幾乎立刻推第一則 REALTIME → `_handle_quote` 在
  `code not in self._watchlist` 的窗內執行 → meta 轉態補推**被 gate 擋掉**,
  盤後該檔卡在 `-` 直到重整。新順序:
  ```
  added / removed 先算(仍讀舊 self._watchlist)
  self._watchlist = list(codes)          # 名單是意圖,訂閱是副作用
  for code in added:   await to_thread(self._acquire, …)   # 失敗照現行 log + 續行
  for code in removed: await to_thread(self._release, …)
  for code in added:   self._publish(self._quote_payload(code))   # 種子在 acquire 之後
  ```
  最終狀態與現況等價(現況也是不論 acquire 成敗都指派),只有 await 窗內的可見性改變。
- `_handle_quote()`(meta 更新處):記 `was_meta_none`,若 `None → 有值` 且
  `code in self._watchlist` → `self._publish(self._quote_payload(code))`。
- **`no_data` 復原的配對在 `_handle_quote`(`:319` 的 `self._no_data.discard(code)`),
  不是在 `_handle_no_data`**`[amendment 2026-07-30: R11]`。寫法必須是**命中才推**:
  ```
  if code in self._no_data:
      self._no_data.discard(code)
      if code in self._watchlist:
          self._publish(self._quote_payload(code))
  ```
  寫成無條件 `discard` + `publish` 會變成**每 tick 廣播** → 直接打穿 W-17 的 1s 節流。
- `_handle_no_data`(`:289-300`)手寫的 dict **也改走 `_quote_payload`**(在
  `self._no_data.add(code)` 之後呼叫,`no_data` 自然為 True)—— 否則同一個
  `watchlist_quote` 型別會有兩種形狀(缺 `ref` key)。
- `_flush_watchlist_loop` 的 dirty 節流語意**不動**(W-17);其推播改走 `_quote_payload`
  以免多處 payload 漂移。

### `frontend/src/hooks/useStockStream.ts`
- `WatchlistQuote` 加 `ref: number | null`;handler `ref: (msg.ref as number|null) ?? null`。
- `[amendment 2026-07-30: R10]` `WatchlistSidebar.test.tsx:83-87` 的 `QUOTES` fixture
  三筆都沒有 `ref` → 必填後 `npx tsc -b` 會紅(§1 量化條件要求 0 error)。
  **登記為該動**:三筆補 `ref: null`,另加第四筆 `{ p: null, chg_pct: null, vol: null,
  ref: 995_000, no_data: false }` 供 SC-4.8 參考價態測試。

**新測試**(後端)
- watchlist 就緒後才 `stream()` → **第一則即種子**,且 `p is None` / `ref == 參考價`
  (**守門斷言:參考價不得出現在 `p`**)。
- `set_watchlist` 新增 code → 廣播一則種子。
- **`set_watchlist` 的 await 窗內注入一則 REALTIME(meta 由 None→有值)→ 該 code
  之後仍收得到帶 `ref` 的 `watchlist_quote`**(R7 的回歸守衛)。
- meta 由 None→有值 → 補推;`no_data` 復原 → 補推**且只推一次**(連續 tick 不重複推,
  R11 的 W-17 守衛)。
- `_handle_no_data` 推出的訊息含 `ref` key(形狀一致)。
- 既有 `test_stream_receives_tick_and_book`(watchlist 空)→ **零種子**,不該紅。

## C7 🔴 側欄列改版(B-7 / SC-4.7 / SC-5.1)

### `frontend/src/components/stock/WatchlistSidebar.tsx`
- `ROW_H` 44 → **52**,且**列高由 `ROW_H` 單一真值推導**:列的
  `style={{ height: ROW_H }}`(不用 `h-13`),空清單佔位列 `style={{ minHeight: ROW_H }}`。
  `[amendment 2026-07-30: R6 —— 原本打算用 `h-13` + 「靠 list-drag 既有測試守落點」。
  該覆蓋宣稱不成立:`list-drag.test.ts` 自帶 `const ROW = 44` 只是餵純函數的參數,
  與元件的 `ROW_H` 無關;`WatchlistSidebar.test.tsx` 的拖曳用 `stubRects()` 手工餵 rect,
  jsdom 無版面引擎看不到真實高度。兩者一旦漂移,W-11 的落點會靜默算錯組/錯位且零訊號。
  改成 inline style 讓 jsdom 直接讀得到,是為了讓這條不變式**可被測試指認**。]`
- `stockRow` 版面(見 §決策 U5):`gap-1.5`;
  左塊 `flex min-w-0 flex-1 flex-col justify-center leading-tight`:
  代號 `font-mono text-base text-ink`、名稱 `truncate text-xs text-ink-muted`;
  右塊 `flex shrink-0 flex-col items-end justify-center font-mono leading-tight`:
  現價 `text-base text-ink`、漲幅 `text-xs` + 紅/綠/dim。
- 名稱來源:`names.find(n => n.code === code)?.name`(`useStockNames` 已 import)。
  **`useMemo` 成 `Map`**(`names` 2401 筆 × 每列 find = O(n·m))。
  缺值 → 左塊只顯示代號(不留空行)。
- `no_data` 態:右塊單行 `text-xs text-ink-dim` 的「無資料」。
- 參考價態(`p === null && ref != null`):現價位置印 `fmtPrice(ref)` **`text-ink-dim`**,
  漲幅位置印 **灰字「參考」**(不是 `0.00%`)。分支順序:
  `no_data` → `p !== null` → `ref != null` → `-`。
- 空清單佔位列 `min-h-11` → `style={{ minHeight: ROW_H }}`(兩處)。

**測試**(🔴 該紅:列高 / 字級相關斷言若有)
- 新增:列內出現股票名稱;`p === null && ref != null` → 顯示參考價與「參考」;
  **`stockRow` 根節點的 `style.height` === `${ROW_H}px`**(R6 的不變式守衛,
  取代原本無效的「靠 list-drag 既有測試守」)。

## C8 🔴 群組整塊折疊(B-6 / SC-4.4)

### `frontend/src/components/stock/WatchlistSidebar.tsx`
- 群組與未分組的 `<header>` → `<button type="button">`,className
  `flex w-full items-center gap-1 border-b border-line px-1 py-1 text-left`
  + `focus-visible:outline-none focus-visible:border-b-accent`
  + `drag === null && "hover:bg-surface"`。
- `aria-expanded={!isCollapsed}`、`aria-controls={listId}`;`<ul>` 補對應 `id`。
  **`listId` 用 `useId()` 前綴 + 索引(`${uid}-wl-list-${i}`,未分組用 `${uid}-wl-list-ung`),
  不可用群組名拼**`[amendment 2026-07-30: R13 —— `addGroup` 只 trim 不限字元,含空白的組名
  (「主力 觀察」)會產生含空白的 id;HTML id 不得含空白,`aria-controls` 是 ID token list
  會被解析成兩個不存在的 token → a11y 關聯靜默失效;名為 `ungrouped` 的群組還會撞 id。]`
  `data-testid={`wl-list-${g.name}`}` **維持原名不動**(既有測試靠它,testid 不是 id token)。
- `▸/▾` `<span aria-hidden="true">`(**移除** 舊 `aria-label`,B-6)。
- `onClick` 開頭 `if (drag !== null) return;`(拖曳放開瞬間的時序守衛)。

**測試**(🔴 該紅:`getByLabelText("折疊 X")`)
- 改寫為 `getByRole("button", { name: /X/ })` + `aria-expanded` 斷言。
- 新增:點群組名文字 / 計數同樣折疊;拖曳中點 header 不折疊。

## C9 🔴 搜尋 → 預覽 + 加入自選(B-5 / SC-4.5 / SC-4.6)

### `frontend/src/components/stock/WatchlistSidebar.tsx`
- `add(code)` → `onSelect(code)`(清空 input);`submitAdd()` 同;
  提示列 `onClick` 改 `onSelect(s.code)`,`aria-label` 由「加入 X Y」→「**查看 X Y**」。
- **搜尋框旁的按鈕文案「新增」→「查看」**`[amendment 2026-07-30: R15 —— 行為改成預覽後,
  留著「新增」會與實際行為不符,也與 aria-label 的改法不一致]`。
- 移除 `addCode` import(若無其他用處)。

### caller 影響:`frontend/src/App.tsx:168`(`onSelect = setStockCode`)
`[amendment 2026-07-30: R15 —— Phase 1 caller map 有列,但 C9 原本沒評估]`
- C9 讓 `onSelect` 的語意從「選一檔既有自選」擴張為「也可能是預覽一檔非自選」。
- `App.tsx:88-93` 會把 `stockCode` 寫進 localStorage `stock-main-code` 並在下次開頁還原。
- **拍板:維持寫入,不改 `App.tsx`**(既有語意 = 還原上次看的檔;預覽檔本來就是
  「上次在看的檔」)。副作用:重整後仍停在該檔而側欄無對應列可反白(`active` 對不上),
  後端 `_main` 掛在非自選 code(refcount owner `"main"`,既有機制吃得下)。
  → 登記進 §7 Known Risks,不在本輪修。

### `frontend/src/components/stock/StockPage.tsx`
- 自帶 `useStockWatchlist()` + `useSaveWatchlist()`。
- header 內(價格 span 之後、`ml-auto` 總量之前)條件渲染「加入自選」按鈕:
  gate = `wl !== undefined && code !== null && !wl.codes.includes(code)`(D3b)。
- 點開 inline 面板(照抄側欄 assigning 面板慣例:裸 `div` + `button`,專案無 Radix),
  列出各群組 + 「未分組」;選定後
  `commit(assignToGroup(addCode(wl, code), code, name, group.codes.length))`
  —— **合成單次 PUT**;選「未分組」→ `commit(addCode(wl, code))`。
- **新入口必須帶零 PUT 守衛**`[amendment 2026-07-30: R16 —— W-9 要求的不變式在新入口沒落實。
  `assignToGroup` 內部 `insertAt` 恆回新陣列,內容相同也會送 PUT → 後端 TC4 全量 UNSUB/SUB。
  觸發:連點兩下群組(第一次的 invalidate 未完成前 `wl` 仍是舊值、gate 仍 true)]`:
  照抄側欄的 `commit()`(`next === wl || JSON.stringify(next) === JSON.stringify(wl)` 早退),
  並在選定後立即收面板 + `save.isPending` 時停用群組按鈕。W-9 條目改為「**三處**」。
- 錯誤文案:`errText(save.error.message)`(WATCHLIST_FULL / BAD_CODE 要看得到)。

**測試**
- 🔴 改寫 `WatchlistSidebar.test.tsx` 4 支:斷言 `onSelect` 被呼叫**且未發 PUT**。
- 🟢 新增 `StockPage.test.tsx`:非自選 code → 按鈕出現 → 點群組 →
  **PUT body 恰一筆**且 `codes` 與該 group 同時含該 code;已在自選 → 按鈕不存在;
  `wl` 未載入 → 按鈕不存在。

## C10 🔴 管理 Dialog 改版(B-8 / SC-4.1~4.3)

### `frontend/src/components/stock/WatchlistManagerDialog.tsx`
- `<dialog>` className 改
  `m-auto flex flex-col overflow-hidden h-[min(30rem,80vh)] w-[min(56rem,92vw)] rounded border border-line bg-bg p-0 text-ink backdrop:bg-black/50`。
  **`m-auto` 是「不在中間」的根因修復**(Tailwind v4 preflight 把 `margin:0` 套到 dialog,
  覆蓋 UA 的 `margin:auto`)。
- 新增 state `selected: string | null`(`null` = 未分組偽群組),
  但**右欄一律用 derived 值渲染**`[amendment 2026-07-30: R9]`:
  ```
  const activeGroup = selected === null ? null : (wl.groups.find(g => g.name === selected) ?? null);
  ```
  `selected` 只當「意圖」,不當事實。理由:改名 / 刪除都是先 `save.mutate` 再更新 UI,
  mutate 失敗(BAD_GROUP / 500)時命令式的 `setSelected(newName)` 已經跑掉 → 指向不存在的組、
  右欄空白且無說明;且本 Dialog 是**常駐掛載**(`WatchlistSidebar.tsx:470` 只切 `open`),
  `selected` 會跨「關閉→再開」殘留。
- **`open` 由 false→true 時 reset `selected` / `renaming` / `localError`**(同一批)。
- **「未分組」是保留名**:`submitAddGroup` / `submitRename` 擋掉 `name === "未分組"` →
  `BAD_GROUP` 文案(否則真的叫「未分組」的群組與 `selected === null` 的偽群組在畫面上
  無法區分,R9c)。
- 骨架見 §決策 U4:header(h-10)/ error 條 / body(左 `w-44` + 右 `flex-1 min-w-0`)。
- 左欄:「未分組」固定第一列(無 ✎ / ×,計數 = `ungroupedCodes(wl).length`)+ 群組列;
  選中態 `border-l-accent bg-bg-deep text-ink`,未選 `border-l-transparent text-ink-muted hover:bg-surface`;
  ✎ / × 在該列 hover 或選中時 visible(固定佔位不做 layout shift)。
  底部固定「新增群組」input + 鈕(邏輯不變,W-14)。
- 右欄:頂端搜尋框(`searchStocks` + `useStockNames`,同側欄)→ 點候選:
  真群組 `commit(assignToGroup(addCode(wl, code), code, group, len))`(單次 PUT);
  未分組 `commit(addCode(wl, code))`;已在本組的候選 `disabled` + 尾綴「已在此群組」。
  清單列 = 代號 / 名稱 / 其他所屬群組 chips(唯讀)/ 右側**兩顆鈕**:
  - 真群組:`−`(aria-label`從 {組名} 移出 {code}`)→ `removeFromGroup`;
    `×`(aria-label`從自選移除 {code}`,hover 紅)→ `removeCode`。
  - 未分組:只有 `×` → `removeCode`。
  `[amendment 2026-07-30: R17 —— 舊 Dialog 的股票區列 `wl.codes` **全體**,每列都能一步
  「從自選移除」。改成「左選組 / 右列該組」後,若右欄 × 對真群組只做 `removeFromGroup`,
  **已分組的股票就沒有任何一步刪除入口**(要先退組、再切未分組、一檔多組還要退每一組)
  = 未登記的功能退化。補第二顆鈕即恢復。B-8 的舊/新行為欄同步補登。]`
- **不引進 `quotes`**(每秒 re-render 會打斷改名輸入)。
- 空狀態文案見 §決策 U4 表。
- W-12 / W-13 / W-14 / W-9 全部保留。

**測試**(🔴 該紅:`WatchlistManagerDialog.test.tsx` 的 checkbox 斷言)
- 改寫為新版:選群組 → 右欄只列該組股票;點右欄 × → `removeFromGroup`;
  未分組列 × → `removeCode`;右欄搜尋加入 → **PUT 恰一筆**且 codes+group 同時含該 code;
  改名 / 刪除 / 新增群組 / BAD_GROUP 文案(W-14)不變;Escape 行為(W-13)不變。
- 新增:dialog className 含 `m-auto`(防 preflight 回歸 —— jsdom 抓不到版面,只能守 class)。

---

## §6 Commit 切分(三類分離)

> 順序偏離 `🔵→🔴→🟢` 的預設:C1 / C6 是 🔴 的**資料前提**(沒有 per-minute h/l 就畫不出
> C2 的標記、沒有 `ref` 欄位就寫不了 C7 的參考價分支)。鐵則 B 要求的是**三類不混同一個
> commit**,本輪全數遵守;僅全域先後順序依依賴關係排。

| # | Commit | 類 | 內容 |
|---|---|---|---|
| 1 | `🟢 feat(stock): MinuteAgg per-minute 高低` | 🟢 | C1 |
| 2 | `🔴 fix(stock): 分時圖當日高低改三角標記、移除即時價位文字` | 🔴 | C2 |
| 3 | `🔴 fix(stock): K 線視窗高低改三角標記` | 🔴 | C3 |
| 4 | `🔴 fix(stock): 分時圖左緣價位帶內縮對齊縮字` | 🔴 | C4 |
| 5 | `🟢 feat(stock): hover 底部標籤加該分鐘價位` | 🟢 | C5 |
| 6 | `🟢 feat(stock): 側欄 quote 連線種子 + 參考價欄位` | 🟢 | C6 |
| 7 | `🔴 fix(stock): 側欄列改兩行(名稱 + 放大代號價位)` | 🔴 | C7 |
| 8 | `🔴 fix(stock): 群組標題整條可折疊` | 🔴 | C8 |
| 9 | `🔴 fix(stock): 搜尋改預覽 + 加入自選按鈕` | 🔴 | C9 |
| 10 | `🔴 fix(stock): 管理 Dialog 置中兩欄改版` | 🔴 | C10 |

每個 commit 走 TDD:🔴 先改測試讓它紅 → 改實作綠;🟢 先寫紅測試 → 實作 → 綠。

## §7 Known Risks

Phase 3 review round 1:**P0 = 0**,P1 = 8(**全部 accepted 並就地修 spec**,見各 C 節
`[amendment 2026-07-30: R*]`),P2 = 9(處置見下)。無 P0 → 不加輪。

### P1 處置對照

| # | 標題 | 處置 |
|---|---|---|
| R1 | K 線標記用 `plotBottom` 而非 `priceBottom`,三角出界 / 文字壓量柱 | 修:三角改 apex 貼價位 body 朝圖內;`buildCandleGeometry` 回傳 `priceBottom` |
| R2 | 降級 `h ?? c` 會「反查命中錯的分鐘」而非落空 | 修:`h: v.h ?? null` + applyTick 保 null |
| R3 | `ACCUM` fixture 無 per-minute h/l,改斷言也不會綠 | 修:登記 fixture 重造 + 三條 null 路徑分開測 |
| R4 | `stock-intraday-svg.test.ts:65` 硬編 `toBe(46)` 未登記 | 修:登記 + 改成守語意的斷言 |
| R5 | `c > ref` 在 `ref === null` 時強轉 0 → 無昨收商品塗紅 | 修:null 檢查前置 + 回歸測試 |
| R6 | `ROW_H` 與 `h-13` 無任何測試守得住 | 修:列高改 inline style 由 `ROW_H` 推導 + 斷言 |
| R7 | `set_watchlist` 的 `_watchlist` 指派在 await 之後 → meta 轉態補推被 gate 擋掉 | 修:指派前移 + 回歸測試 |
| R8 | SC-1.1 文字與 C2 points 互斥 | 修:統一為 apex 貼價位 |

### P2 處置(逐條)

| # | 處置 |
|---|---|
| R9 | **修**(右欄改 derived `activeGroup`、open 轉態 reset、「未分組」設保留名) |
| R10 | **修**(`QUOTES` fixture 補 `ref`,登記進 B-7) |
| R11 | **修**(`_handle_no_data` 也走 `_quote_payload`;discard 配對寫成「命中才推」) |
| R12 | **修**(SC-1.2 對照物改成 snapshot `high`) |
| R13 | **修**(`aria-controls` id 改 `useId()` + 索引) |
| R14 | **修**(B-2 改登記「無既有測試」,C3 改先寫新版紅測試) |
| R15 | **部分修 + 入 Known Risks**(側欄按鈕文案改「查看」、caller 影響寫進 C9;localStorage 行為維持不改,風險見下 K-1) |
| R16 | **修**(新入口沿用 `commit()` 零 PUT 守衛,W-9 改三處) |
| R17 | **修**(右欄真群組列補第二顆「從自選移除」鈕) |

### Phase 7 真實環境驗證(2026-07-31)

| 項目 | 結果 |
|---|---|
| frontend production build | ✅ `vite build` 928ms,150 modules,`StockPage` chunk 45.01 kB(gzip 14.12) |
| **C1 per-minute 高低(真實市場資料)** | ✅ 用 repo 內 TC4 產出的真實 1K 落檔(`data/1k/`,1,715 檔)抽樣 **299 檔股票日** 重放進本分支的 `StockDayState`:**299/299** 滿足 `day high == max(minute.h)` 且等值反查命中(= 前端 `markFor` 定位的地基由建構保證) |
| **「摸到就算」設計驗證** | ✅ 同一批真實資料:**44.5%**(133/299)的股票日「當日高 > 所有分鐘收盤」、**54.5%**(163/299)「當日低 < 所有分鐘收盤」 —— 若沿用分鐘收盤極值(D1 候選 C),近半數交易日的標記數字會是錯的。差異不是邊際情形 |
| server 起動 | ⚠→✅ 第一次嘗試時達錢 4 未開(port 50774 由 open → closed,錯誤是 `TC4 quote connect failed: Resource temporarily unavailable`,不指向根因);**user 開啟後 10:02 盤中正常起來**,2330 回補 5,246 ticks |
| **C1 盤中真行情(SC-1.2)** | ✅ 自選 4 檔 REST 全數 `minutes` 的 `h`/`l` 齊備、`day high == max(minute.h)` 且反查命中。**2330:高 2400 落在 09:06,且高於所有分鐘收盤** —— 沿用收盤極值的話這個數字會是錯的,真環境直接複現 |
| **C6 連線種子(SC-4.8a)** | ✅ 連上 `/ws/stock` 的**瞬間**收到 4 則種子(自選各一,4989 / 2330 / 2327 / 6207),皆帶真實 `p` 與 `chg_pct` → 開頁側欄不再全 `-`。`p` 與 `ref` 同時有值的訊息 **0 則**(互斥契約成立) |
| SC-4.8b 參考價態 | ⏸ 盤中所有自選都已成交 → `ref` 恆 null(**這是正確行為**)。灰色參考價 + 「參考」二字要**盤前 / 盤後**重載才看得到 |
| **畫面對照 SC-1 ~ SC-6** | ✅ **user 於 2026-07-31 盤中對照 dev server 過目確認「沒問題」** —— 六項的可指認表述全數通過(高低三角無虛線 / 現價只留圓點 / hover 兩行標籤 / 自選四項改版 / 字級 / 左緣價位帶) |

**K-2 觀察**:本次是「當日已在線 + 盤中」路徑,冷啟動(後端當日從未在線)時 TC4 對
SUBQUOTE 是否回推 REALTIME **仍未實證**,留待盤後重啟時觀察。

### 保留風險

- **K-1**(R15)預覽一檔非自選股後,`stock-main-code` 仍會記住它 → 重整後主區停在該檔,
  但側欄沒有對應列可反白(`active` 對不上任何列),後端 `_main` 長期掛在非自選 code。
  既有 refcount 機制吃得下(owner `"main"` 與 `"watchlist"` 分離,不佔 30 檔上限),
  且語意上「還原上次看的檔」本來就成立 → **本輪不改**。
- **K-2**(D4 / fable 風險 1)盤後**冷啟動**(後端當日從未在線)時,TC4 對 SUBQUOTE 是否
  回推 REALTIME 未實證(`stock_source.py` 檔頭明載未實測)。該情境 meta 為 None →
  種子誠實給空值 → 側欄仍 `-`。**不假造**。Phase 7 真實環境驗證要記錄實測結果。
- **K-3**(既有洞,非本輪新增)側欄的 `EMPTY_WL` fallback 在自選載入失敗時仍可能被寫入,
  把整份自選清空。本輪只在**新入口**(StockPage)加 gate;側欄既有入口不動 → 寫進
  `docs/next-time.md`。
- **K-4**(既有風險)側欄 / Dialog / StockPage 三處 mutation 為 last-write-wins。

## §8 self_review_head

self_review_head: f696f5134cb43c0e76c89519de44870a2954e47e

Phase 5 自評(medium、3 lens:whitelist / correctness / test_coverage)結果:
**0 P0 / 6 P1 / 5 P2**,10 accepted 全部修畢 + 1 rejected_with_reason(F11 memo 覆蓋,
連同其餘 P2 寫進 `docs/next-time.md` 2026-07-31 節)。JSON 落檔 `code-review-round-1.json`。

**白名單對照結論**:W-1..W-24 逐條對撞 diff,只有 **W-9(零 PUT 三處)** 被抓到
—— 已修(Dialog 補深度比對 + 三處都加 `save.isPending` 停用)。其餘 23 條全數保留。
