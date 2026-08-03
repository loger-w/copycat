# change-spec — 個股 UI 第五輪(stock-ui-round5)

Phase 1 現況表:`./current-state.md`(caller map / baseline / 逐項現況)。
規模分流:**L**(後端資料模型 + 對外 API shape + 4 個前端元件 + 1 個新 Dialog)
→ Phase 3 預設 1 輪 review,accepted P0 觸發限縮加輪 1 次。

Review round 1:`./change-spec-review-round-1.json`(P0×5 / P1×8 / P2×5,**全數 accepted**)。
本檔已就地修復,修復處標 `[amendment 2026-07-30: review RN — 原因]`。

## 分流判定

**已成形改法** — user 兩次訊息各自指名 UI 形式與操作序列(「頂部搜尋框」/「Enter 之後代號旁
一個 +」/「沒有群組就不能新增」/「點擊群組可以縮小或展開」/「一個按鈕開 Dialog 統一管理」/
「量的顏色對應內外盤」/「當日高低加在江波圖」),命中 `feat-phase0-2.md` 判準 1 與判準 2
→ 提問走 `grilling` 姿態,user 已拍板 6 項決策(下表)。

## User 拍板紀錄(2026-07-30)

| 決策 | 選擇 |
|---|---|
| round 4 處置 | **先 merge 進 master 再開 round 5**(已執行:master `ed6d2d1` → `f1677bc`) |
| 最外層語意 | **未分組桶**:只放不屬任何群組的股票;拖進群組 = 移動,從最外層消失 |
| Enter 後落點 | **存進未分組層並持久化**(重載還在),不是暫存列 |
| 管理 Dialog 範圍 | **完整管理台,取代側欄的 `⊞` 面板**(一檔多組改在 Dialog 內做) |
| 項 1 現價小圈 | **只做江波圖**;K 線圖只加高低標記,不加小圈 |
| 項 2 症狀 | 「垂直線沒有穿進量區 / 位置偏掉」— **但與靜態幾何量測矛盾,證據未到,見 §項 2** |

**round 4 沿用不得推翻的拍板**:跨群組拖曳 = **移動**(來源組移除)。
**[amendment 2026-07-30: review R2 — 原 `assignToGroup` 定義「來源不動」把它靜默改成複製]**

## Auto-default 決策(未問 user,可事後 audit)

- `[auto-default: 自選 schema v3 用「codes(全體) + groups(成員關係)」,未分組**衍生不另存** | reason: 另存一份 `ungrouped` 陣列會產生「同一檔同時在 ungrouped 與某群組」的可違反不變式,而那個違反在畫面上是「同一檔出現兩次」= 靜默資料錯。改成 `未分組 = codes − ∪groups.codes` 後不變式由建構保證;附帶好處:`codes` 直接就是訂閱池]`
- `[auto-default: PUT body 的 `codes` 設為**選填**,缺省時 = union(groups) | reason: 舊 client(只送 groups)行為與現在逐字元相同,是真的 backward compatible 而不是「應該相容」]`
- `[auto-default: 群組內出現不在 `codes` 的代碼 → **補進 codes 尾端**,不報錯 | reason: 「加進群組」本來就蘊含「加進自選」;報錯會讓一個語意上沒有矛盾的請求失敗]`
- `[auto-default: v1 `{"codes":[…]}` 遷移改成「全部落未分組」(原本是包成單一「自選」組) | reason: v1 的 codes 從來就沒有群組概念,包成一個叫「自選」的假群組是 v2 時代沒有未分組桶的權宜。**這是 🔴 行為改動,既有測試該紅**]`
- `[auto-default: 當日高低由**後端 `StockDayState` 逐 tick 維護 running max/min**,不取 TC4 `HighPrice`/`LowPrice`,也不用「分鐘收盤極值」近似 | reason: (a) 分鐘收盤極值會漏掉「盤中摸到但沒收在那分鐘」的影線,對看盤工具那正是最該看到的;(b) **TC4 個股 REALTIME 帶不帶 `HighPrice`/`LowPrice` 沒有實證** —— 2026-07-21 盤中 probe 的真實樣本(`tests/live/test_stock_models.py:13-55`,33 個欄位)**沒有這兩個欄位**;`index_engine.py:231-232` 用它是在 `IX0001` 指數上,不能外推到個股;(c) `StockDayState.ticks` 存當日**全部** tick(deque maxlen 20,000)且 `apply_backfill` 會把回補資料重放過 `_apply` → 在 `_apply` 維護 running max/min 是**建構保證正確**、天然單調、不依賴任何未驗證的上游欄位]` **[amendment 2026-07-30: 寫紅測試前查證 probe 樣本,推翻原資料源決策。連帶:S6 的「保留語意」與 W-23 失去存在理由(running max/min 單調,不可能被打成 null);S7 的 `acc.meta === null` 分支也消失(高低不再掛在 meta 上)]**
- `[auto-default: 當日高低放 snapshot / accum 的 **top-level**(與 `vwap` / `cum_inner` 同層),**不放 `meta`** | reason: `meta` 是 TC4 來的靜態盤別資料(名稱 / 參考價 / 漲跌停),把「由成交推導的當日狀態」塞進去語意錯位;放 top-level 之後前端 `acc.meta` 為 null(只跑過回補、未收 REALTIME)時高低照樣有值]` **[amendment 2026-07-30: 同上]**
- `[auto-default: `meta.high/low` 為 null 或**落在 y 域外** → 不畫該條線 | reason: (a) null 不畫:running max/min fallback 只涵蓋「本次連線收到的 tick」,重載後數字會變小而畫面不會說它變小了;(b) 域外不畫:沿用同檔 `overlayLines`(`stock-intraday-svg.ts:260-262`)與 `yTicks`(`:192-195`)既有慣例,否則無漲跌停的 autofit 域下線會畫到時間軸上]` **[amendment 2026-07-30: review R12 — 補域外分支]**
- `[auto-default: 拖進未分組區塊 = **從所有群組移除**(不是只從來源組移除) | reason: 未分組的定義就是「不屬任何群組」。只移除來源組的話,一檔多組的股票拖進未分組後會從來源組消失卻不出現在未分組(它仍屬別組)= 畫面上像資料被吃掉。「拖到哪就出現在哪」是拖曳唯一不會騙人的語意]` **[amendment 2026-07-30: review R18]**
- `[auto-default: 未分組層**內部也支援拖曳排序** | reason: 未分組列有拖拉握把卻只能拖出去不能排序,是使用者無法預期的死互動]`
- `[auto-default: 明細漲跌基準 = `meta.ref`(參考價) | reason: 專案其餘所有漲跌色(header / 側欄 / 江波圖資訊列)一律以 `meta.ref` 為基準,明細另立基準會出現「同一個價在兩處顏色不同」]`
- `[auto-default: Dialog 用 `<dialog>` 元素,開關**只由 effect 單一路徑驅動**(feature-detect:有 `showModal` 走原生、沒有走 `open` 屬性),**絕不把 `open` 當 JSX prop 傳給 `<dialog>`**;Escape 自寫 handler | reason: jsdom 26.1.0 的 `HTMLDialogElement-impl.js` 是**空 class**(無 `showModal`/`close`/Esc 行為),直呼會 TypeError;專案 vitest 無 `setupFiles`(`vite.config.ts:20-23`)]` **[amendment 2026-07-30: review R1]** **[amendment 2026-07-30: review S1(P0)— 原寫「`open` 屬性驅動 + feature-detect 呼叫 `showModal()`」,兩者並用在真瀏覽器**必然拋 InvalidStateError**:React 在 commit 階段先寫入 `open=""`,effect 才跑,而 HTML 標準的 `showModal()` 步驟 2 就是「已有 open 屬性 → throw InvalidStateError」;反向也壞 —— `showModal()` 成功後把 `open` 設回 false,React 只移除屬性,依標準**不會**把元素移出 top layer,`::backdrop` 會留著擋住整頁。而 jsdom 因為沒有 `showModal` 會跳過 feature-detect → **測試全綠、真瀏覽器第一次點「管理」就白畫面**,正是自動化守門看不到的那一種]`
- `[auto-default: Dialog **關閉時不渲染內容**(`{open && <>…</>}`,只留 `<dialog>` 殼給 ref) | reason: RTL 的 `getAllByText` / `getAllByLabelText` 不過濾隱藏元素,且 jsdom 沒有 `dialog:not([open]){display:none}`;常駐渲染會讓既有的計數型斷言(`WatchlistSidebar.test.tsx:94` 的「2330 出現 2 次」、`:114` 的「握把 4 個」)變成 3 / 6]` **[amendment 2026-07-30: review R13]**
- `[auto-default: 前端 `TickRow.b/a` 與 `StockMeta.high/low` 宣告為**選填**(`b?: number \| null`) | reason: 宣告必填會讓 10 個既有測試 fixture 的物件字面量型別失敗(`RightRail.test.tsx:15`、`PriceLadder.test.tsx:16` 等與本輪無關的檔),`npm test` 綠但 `tsc -b` 紅;選填與「舊 snapshot 缺欄位」的相容策略同一件事,消費端一律 `?? null`]` **[amendment 2026-07-30: review R8]**
- `[auto-default: 側欄捲動容器維持 `<aside>`;頂部搜尋框 `sticky top-0` | reason: 群組多起來時搜尋框必須恆在視野內(user 明說「位置位在上面」),但捲動容器已在 aside(round 4 決策),sticky 是不改捲動架構的最小做法]`

---

## 0. 第二輪追加需求(2026-07-30,user 看畫面後提出)

截圖佐證:`docs/specs/stock-ui-round5/screenshots/`(江波圖全景,ref=55.5、hover 09:00)。
**原「項 2 待證據」就此結案** —— 症狀不在 K 線圖而在**江波圖的內外盤副圖**,根因兩條都已定位。

| # | 需求 | 根因 / 現況 | 判定 |
|---|---|---|---|
| A | 十字線要對到量 bar 的**中心**不是左緣 | `energyBars[i].x = toX(minute)` 與走勢線頂點、十字線同 x,但副圖把該分鐘畫成 `[b.x, b.x+bw/2]`(外)+ `[b.x+bw/2, b.x+bw]`(內)→ **整對佔 `[b.x, b.x+bw]`,`b.x` 是左緣**(`stock-intraday-svg.ts:176-182`、`StockIntradayChart.tsx:313-323`) | 🔴 |
| B | 自選搜尋列常駐 | 已在本 spec §🔴-9(頂部 `sticky` 恆存),無需追加 | — |
| C | 左軸價位數字**依漲跌上色**(高於平盤紅 / 低於綠 / 平盤白) | 現在 11 個刻度值**已經**就是 ±10/8/6/4/2/0% 對應的價(截圖 ref=55.5 逐條吻合),只差全部是 `fill-ink-dim` 灰 | 🔴 |
| D | 右緣 CDP/MA 價位標不得壓到走勢圖 | 現在疊線畫到 `w-34`、文字放 `x={w-32}` 直接疊在繪圖區上(`StockIntradayChart.tsx:183-204`);round 4 曾把它列 out of scope,本輪納入 | 🔴 |
| E | 副圖刻度跟「量」對不上 | `maxSide = 全日單邊最大`(`:173`),而資訊列的「量」是**總量含 neutral**。截圖 09:00:量 269 / 外 127 / 內 20 → **差的 122 張 neutral(開盤集合競價無 Bid/Ask 可比)根本沒畫**,刻度 164 又是單邊最大 → 畫面上沒有任何高度對應得到 269 | 🔴 |

**User 拍板(2026-07-30 第二輪)**

| 決策 | 選擇 |
|---|---|
| E 的修法 | **堆疊成一根總量**:每分鐘一根,總高 = 該分鐘總量(外+內+未分類),刻度 = 全日最大總量;內部分段上色 外盤紅 / 內盤綠 / 未分類灰 |
| C 的形式 | **價位數字照舊**(不改成顯示 `+2%` 字樣),只加漲跌配色 |

## 一、改完的成功條件(可驗收;UI 類為畫面可指認表述)

| SC | 條件(畫面可指認) |
|---|---|
| **SC-1** | 江波圖上出現**兩條水平線**,右緣標籤分別為當日最高價與當日最低價。線的顏色與虛線節奏與 y 軸格線可區分。**量法**:標籤數字 === `GET /api/stock/state/<code>` 回傳的 **top-level `high / 1000`**(毫元轉元,同 `fmtPrice` 慣例;**不是 `meta.high`** — 見資料源 amendment);**盤中出現新高後線會上移**(不需重載頁面)。 **[amendment 2026-07-30: review R5 — 原「與 header 同源」驗不到,header 根本沒有高低數字]** **[amendment 2026-07-30: review S8 — 原量法漏了毫元→元換算,240 元會被記成 240000,照字面驗必 FAIL]** |
| **SC-2** | 江波圖走勢線的**最右端**有一顆實心小圓點;現價高於**參考價 `meta.ref`** 時圓點為紅(`fill-bull`)、低於為綠(`fill-bear`)、相等為灰。圓點緊鄰處顯示現價數字,顏色同圓點。 **[amendment 2026-07-30: review R17 — 原寫「昨收」,與實作判準 `meta.ref` 及 auto-default 不一致(除權息日兩者不同)]** |
| **SC-3** | K 線圖(日K 與任一分K)上出現**兩條水平線 + 價位標**,數字等於底部 figcaption 既有的「高 X / 低 Y」;滾輪縮放改變可視範圍後,兩條線與 figcaption 的數字**同步改變且始終相等**。 |
| **SC-4** | 明細表頭為 **時間 / 買價 / 賣價 / 成交 / 量** 五欄。 |
| **SC-5** | 明細的**買價 / 賣價 / 成交**三欄:數值 > 參考價為紅、< 為綠、= 為灰。同一列三個價可以不同色。買價或賣價缺值 → 顯示 `-` 且為灰。 |
| **SC-6** | 明細的**量**欄:該筆為外盤為**紅**、內盤為**綠**、無法判定為灰。 |
| **SC-7** | 側欄**最上方**有一個恆存的搜尋框(placeholder `股號或名稱`)與一顆「新增」鈕。輸入 `2` → 下方提示列出現多筆 `2` 開頭的代碼;輸入完 `2330` → 提示列出現一列文字含 `2330` 與 `台積電`。 |
| **SC-8** | 在該搜尋框按 Enter(或點「新增」、或點提示列)→ `2330` 出現在**「未分組」區塊**;**重新載入頁面後 `2330` 仍在未分組**。 |
| **SC-9** | 未分組區塊的每一列右側有一顆 `+`。**一個群組都沒有時**該 `+` 為停用態(`disabled`,反灰且點了沒有反應)。 |
| **SC-10** | 有群組時點該列的 `+` → 出現群組名稱清單;點其中一個群組 → 該股票**從未分組消失**、出現在該群組的股票列中。 |
| **SC-11** | 側欄由上而下 = 搜尋框 → 未分組區塊 → 各群組區塊**依序往下疊**。每個群組標題列可點擊折疊 / 展開,折疊後該組股票列隱藏、標題列仍在,其他組不受影響,**重新載入後折疊狀態維持**。 |
| **SC-12** | 拖曳三條路徑各自可指認:(a) 未分組某列 → 某群組股票列範圍內放開 → 該檔從未分組消失、出現在該群組放開的位置;(b) 群組 A 某列 → 群組 B → **從 A 消失**、出現在 B(移動語意);(c) 群組某列 → 未分組區塊 → 該檔從**所有**群組消失、出現在未分組。拖到側欄水平範圍外放開、或拖曳中按 Esc → **什麼都不發生**。 **[amendment 2026-07-30: review R2/R18 — 原只寫未分組→群組一條,漏掉移動語意與未分組落點]** |
| **SC-13** | 側欄有一顆 `aria-label="管理群組與股票"` 的按鈕;點下去開啟一個 Dialog,標題為「管理群組與股票」。Esc 可關閉。 |
| **SC-14** | Dialog 內可完成:新增群組、群組改名、刪除群組、**用 checkbox 勾選某檔股票同屬哪些群組**(一檔可勾多組)、把某檔股票從自選整個移除。關閉 Dialog 後側欄立即反映這些變更。 |
| **SC-15** | 側欄的股票列上**不再有 `⊞` 按鈕**;群組標題列上**不再有 `+` 與 `×`**。 |
| **SC-16** | 量化 gate:`npm test`(frontend/)+ `npx tsc -b` + `npx eslint src` 全綠;`pytest -q` + `ruff check copycat tests` + `pyright` + `copycat validate` 全綠。單位 = 測試通過數 / exit code。 |
| **SC-17** | 舊資料相容(量法 = 直接餵檔案給 `load_watchlist`):v2 檔 `{"groups":[{"name":"主力","codes":["2330"]}]}` → `2330` 仍在「主力」組、未分組為空;v1 檔 `{"codes":["2330"]}` → `2330` 在未分組、零群組。 |
| **SC-18** | 未分組的股票**有報價**(價格與漲跌%欄不是 `-`),證明它們有進訂閱池。 |
| **SC-19**(A) | 江波圖 hover 任一分鐘,副圖那一分鐘的量 bar **左右各有一半落在十字虛線兩側**(線穿過外盤紅塊與內盤綠塊的交界),不再整根落在線的右邊。 |
| **SC-20**(C) | 江波圖左緣的 11 個價位數字:**高於平盤那幾個為紅、低於平盤為綠、平盤那一個為白**。數值本身不變(仍是 ±10/8/6/4/2/0% 對應的價,例:ref 55.5 → 61 / 59.9 / 58.8 / 57.7 / 56.6 / **55.5** / 54.3 / 53.2 / 52.1 / 51 / 49.95)。 |
| **SC-21**(D) | 江波圖右緣 CDP/MA 的價位標(`58.9*` / `56.2*` / `52.1*` / `MA5` / `MA20`)**全部落在走勢線右側的空白帶內**;走勢線、紅綠填色、格線、疊線的右端一律止於該帶左緣。 |
| **SC-22**(E) | 副圖每分鐘**一根** bar(不再左右並排兩根),由下而上分段:外盤紅 → 內盤綠 → 未分類灰。hover 某分鐘時,**該根 bar 的總高度 ÷ 副圖可用高度 ≈ 資訊列的「量」÷ 右上角刻度數字**。量法:hover 09:00(量 269),右上刻度顯示的是**全日最大總量**而不是 164(單邊最大)。 |

---

## 二、不能破壞的既有行為白名單(**優先於新行為**)

| W | 行為 | 現況出處 |
|---|---|---|
| W-1 | **一檔可同屬多組**(能力不得消失,只換操作入口:側欄 `⊞` → Dialog checkbox) | `WatchlistSidebar.tsx:139-148,395-413` + 測試 `:94`(2330 出現兩次)、`:165-180` |
| W-2 | 上限 **30 檔**、群組內去重保序、`BAD_CODE`/`BAD_GROUP`/`WATCHLIST_FULL` 三個錯誤碼與其中文文案不變;群組名空白 / 重名 → `BAD_GROUP` | `stock_watchlist.py:62-89`、`WatchlistSidebar.tsx:23-28`(`errText`) |
| W-3 | 群組刪除 PUT 失敗(4xx)→ 顯示錯誤文案、**沒有發第二次 PUT**、UI 不先跳(mutation 成功才收斂衍生狀態) | `WatchlistSidebar.tsx:119-137` + 測試 `:236` |
| W-4 | **兩條**直接加入路徑都在:輸入完整股號 → **Enter** 或 **點「新增」鈕**,不強制先選提示列(提示列無命中時用 `input.trim().toUpperCase()` 原樣加) | `WatchlistSidebar.tsx:86-103,228-234` + 測試 `:179`(點「新增」)、`:186`(Enter 無命中) |
| W-5 | 點股票列觸發 `onSelect(code)` 換股;拖拉握把 / 折疊鈕 / `+` / `×` / 提示列的點擊**不得**冒泡成換股 | `WatchlistSidebar.tsx:336,343,373-374,384-385` |
| W-6 | 拖曳落點幾何**每次 `pointermove` 重算**;落點高亮**只用不改盒模型的樣式**;拖到側欄外 / Esc → 零 PUT | `WatchlistSidebar.tsx:150-208,278-281` |
| W-7 | `PUT /api/stock/watchlist` 成功後**重設訂閱池** | `app.py:452` |
| W-8 | 江波圖 hover:垂直線與資料點**只在該分鐘有成交時**畫;水平線與左緣價位標**恆畫** | `StockIntradayChart.tsx:506-531` |
| W-9 | `ChartStatic` / `EnergySub` 維持 `memo`,尺寸 props 維持**純量** | `StockIntradayChart.tsx:86-104,265-276`、`CandleChart.tsx:84-99` |
| W-10 | 江波圖主副圖同一分鐘 x 對位;`toX`↔`minuteOf`、`toY`↔`priceAtY` 互逆 | `stock-intraday-svg.ts`、`StockIntradayChart.tsx:581-592` |
| W-11 | K 線 MA/BB **以完整序列算完再裁切**;y 域不被視窗外極值撐開 | `CandleChart.tsx:315-334` |
| W-12 | K 線圖既有互動:滾輪縮放、拖曳平移、`key={code}-{mode}` 換股重掛 | `CandleChart.tsx:349-402`、`StockChart.tsx:106` |
| W-13 | 明細「載入更多」分頁(每次 +30)與空態「尚無成交」文案;根節點 `h-full` + `overflow-y-auto` | `TickTape.tsx:14,17-24,58-66`。⚠ **分頁目前零測試覆蓋**(見 §🔴-11) |
| W-14 | 明細列序 = **最新在最上** | `TickTape.tsx:15` + 測試 `:10`(與顏色斷言混在同一支) |
| W-15 | `StockPage` → `WatchlistSidebar` 的 `active`/`onSelect`/`quotes` 三個 props 語意與型別**不變** | `StockPage.tsx:31` |
| W-16 | 冷啟動(零群組零股票)時側欄**仍有新增股票的入口** | `WatchlistSidebar.tsx:430-435` |
| W-17 | 江波圖 y 域恰為 `[lower, upper]`、無漲跌停時對稱 autofit、退化域 `flat` 特判;y-tick 域外跳過 | `stock-intraday-svg.ts:135-142,192-195` |
| W-18 | 個股 tick 的內外盤判定(`derive_side`)結果不變;`MinuteAgg` 的 `i`/`o`/`u` 累加語意不變 | `stock_models.py:92-98`、`stock_state.py:105-111` |
| W-19 | **同組內拖曳 = 排序**,且插入位置有 off-by-one 補償(`[A,B,C,D]` 拖 A 到槽 3 → `BCAD` 不是 `BCDA`) | `list-drag.ts:70-92` + 測試 `list-drag.test.ts:103-149`(5 支)、`WatchlistSidebar.test.tsx:444` **[amendment 2026-07-30: review R3 — 原白名單漏列,而 spec 又要刪掉守門測試]** |
| W-20 | 刪除群組成功後,`copycat-stock-wl-collapsed` **不留該組名**(否則日後建同名群組會意外呈折疊) | `WatchlistSidebar.tsx:125-133` + 測試 `:251` **[amendment 2026-07-30: review R4 — 刪群組搬進 Dialog 後這條沒有新家]** |
| W-21 | 「該組已有的股票再加一次 → 零 PUT」、「搜尋框按 Esc → 收起且零 PUT」、「名稱表為空時仍可直接輸入股號加入」 | `WatchlistSidebar.tsx:92-93,220-223`;測試「已在該組的代碼不重複加入」/「搜尋框 Esc 收起」/「名稱表為空仍可加入」 **[amendment 2026-07-30: review R4 — 這三條語意原本只活在被判該紅的測試裡]** |
| W-22 | **拖曳落點結果與現況相同 → 零 PUT**(不重設訂閱池) | `WatchlistSidebar.tsx:198` 的早退 **[amendment 2026-07-30: review S5 — 原白名單與拖曳分支表都漏了它,且既有測試也沒釘住(`:444` 那支不落在早退條件內)]** |
| W-23 | ~~當日高低在推播缺欄位時保留前值~~ **作廢** —— 資料源改成後端 running max/min 後,單調性由建構保證,不存在「被推播打成 null」的路徑 **[amendment 2026-07-30: 資料源改動,S6 的前提消失]** |
| W-24 | `StockDayState.reset()` 清空當日衍生狀態(seq / minutes / ticks / cum_* / vwap / `_last_cum` / `_amount_milli` / `_volume`),**但保留 book / meta**(盤外顯示昨收靜態值依賴 meta)。**新增的 high/low 屬當日衍生 → 必須跟著清** | `stock_state.py:46-56` |

---

## 三、Backward compat / migration 策略

| 面 | 策略 |
|---|---|
| 自選 JSON schema | **v2 → v3**:新增 top-level `codes`。讀時遷移:v3 直接用;**v2**(有 `groups` 無 `codes`)→ `codes = union(groups)`(**畫面零差異**);**v1**(只有 `codes`)→ `codes` 原樣 + `groups = []`(🔴 行為改) |
| `GET /api/stock/watchlist` | 回傳加 `codes` → `{"codes":[…], "groups":[…]}` |
| `PUT /api/stock/watchlist` — **body** | `codes` **選填**;缺省 → `union(groups)`。舊 client 只送 `groups` 時存檔結果與現在逐字元相同 |
| `PUT /api/stock/watchlist` — **回應** | **加 `codes`,與 GET 同形** `{"codes":…, "groups":…}`。⚠ 現行是 `{"groups": saved}`(`app.py:453`)且前端 `useStockWatchlist.ts:38-42` 直接把回應寫進 query cache —— 不改回應的話,每次存檔成功後 cache 的 `codes` 變 `undefined`,下一次 render 就 `wl.codes.map` 崩(且是「成功之後」才炸,最難察覺) **[amendment 2026-07-30: review R9]** |
| 訂閱池 | `app.py:188,452` 改取 `wl["codes"]` |
| WS `tick` 訊息 | 加 `b` / `a`(買賣價毫元 or null)**與 `h` / `l`(當日高低毫元 or null)**。⚠ `h`/`l` 必須走 WS —— engine **不發 meta 型別訊息**(`useStockStream.ts:5` 檔頭、`stock_engine.py:337-352`),snapshot 只在換檔 / seq 跳號 / 回補完成 / 重連時重抓,盤中不會發生 **[amendment 2026-07-30: review R5]** |
| REST snapshot `ticks[]` | 加 `b`/`a`;前端 `fromSnapshot` 對缺欄位填 `null` |
| REST snapshot **top-level** | 加 `high`/`low`(毫元 or null,與 `vwap` 同層)。**`meta` 不動** **[amendment 2026-07-30: 資料源改動]** |
| `StockPage` → `TickTape` props | 加 **`ref_`**(參考價,`number \| null`)。**不可命名 `ref`** —— React 19 的 ref-as-prop 會把它解析成 `Ref<T>`;專案既有慣例正是 `ref_`(`StockPage.tsx:100` 的 `OrderBook`) **[amendment 2026-07-30: review R14]** |
| 前端型別 `TickRow` / `StockMeta` | 新欄位一律**選填**(`b?`/`a?`/`high?`/`low?`),見 auto-default |
| localStorage `copycat-stock-wl-collapsed` | **沿用不動**;未分組折疊另用 `copycat-stock-wl-ungrouped-collapsed`(`"1"` = 折疊) |

---

## 四、Out of scope

- 項 2 的實際修改(證據未到;本輪**不動** `candle.ts` / `CandleChart` 的既有幾何)
- 江波圖 / K 線圖的配色與字級全面重排(只加本輪指定的元素)
- 明細加「筆數統計 / 大單濾網 / 逐筆回放」
- 群組顏色標記、自選匯入匯出、雲端同步、30 檔上限調整
- 觸控裝置的拖曳手感調校
- 期貨 / 指數 / TXO / 相關係數 / 下單面板任何改動
- `futures_engine` 間歇性零推播(CLAUDE.md §8 既有 P1)

---

# Phase 3 — Diff 級 spec(逐檔)

> **順序說明**:本輪**無 🔵**(鐵則 B:不順手重構)。🔴 與 🟢 的相對順序在項 1/3 內部被
> 依賴關係反轉:明細五欄(🔴)的紅測試需要後端欄位(🟢)先存在,否則紅測試不是「該紅」
> 而是「無法轉綠」。**三類不混 commit 的鐵則不變**。

## 🟢-1 `copycat/live/stock_models.py` — tick 帶買賣價

**[amendment 2026-07-30: 資料源改動 — `StockMeta` 不再加 high/low,當日高低移到 §🟢-2 的
`StockDayState`]**

```python
@dataclass(frozen=True)
class StockTick:
    ...
    bid_milli: int | None = None   # 成交當下最佳買價(= derive_side 的輸入)
    ask_milli: int | None = None   # 成交當下最佳賣價
```

**[amendment 2026-07-30: review R7 — 原無 default,關鍵字建構一樣會 `TypeError: missing arguments`]**
`= None` 是必要的:既有建構點 `tests/live/test_stock_state.py:16-26`、
`tests/server/test_stock_engine.py:143-146,160-163` 都以關鍵字建構且不會有新欄位。

- `parse_stock_realtime`(`:113`):`bid0`/`ask0` 目前是區域變數餵給 `derive_side`(`:148`),
  改成同時存進 tick。**`StockMeta` 完全不動。**
- **`parse_hist_tick`**(歷史,`:155-177`;**不叫 `parse_stock_ticks`**)同樣把
  `to_milli(row.get("Bid"/"Ask"))` 存進 tick。 **[amendment 2026-07-30: review R16 — 函式名寫錯]**
- **不改 `derive_side`**(W-18)。

**~~當日高低的保留語意(W-23)~~ 整段作廢** **[amendment 2026-07-30: 資料源改成後端 running
max/min,不再經 `update_meta`,S6 指出的覆蓋路徑不存在。以下保留原文供追溯]**

`parse_stock_realtime` **每則推播都重建整個 `StockMeta`**(`:119-128`),而
`StockDayState.update_meta`(`stock_state.py:92-93`)是**無條件覆蓋** `self.meta = meta`,
`stock_engine.py:325` 每則都呼叫它。所以只要有**一則**推播不帶 `HighPrice`/`LowPrice`,
當日高低就被打成 `None` → 配合 auto-default「null → 不畫」,SC-1 的線會在盤中閃掉,
連 REST snapshot 也跟著回 null(重載後線不見)——**比 R5 原本要修的「線停在舊高」更難察覺**。

同 repo 唯一另一個 `HighPrice` 消費者 `index_engine.py:231-232` 正是刻意寫
`s.high = _millipt(...) or s.high` 保留舊值,證明既有實作**不假設每則推播都帶得到**。

**做法(擇 a)**:`parse_stock_realtime` 缺值照回 `None`(parse 層保持無狀態),
由 `StockDayState.update_meta` 做欄位級保留:

```python
def update_meta(self, meta: StockMeta) -> None:
    old = self.meta
    if old is not None:
        meta = replace(
            meta,
            high_milli=meta.high_milli if meta.high_milli is not None else old.high_milli,
            low_milli=meta.low_milli if meta.low_milli is not None else old.low_milli,
        )
    self.meta = meta
```
放在 state 而不是 parse 層:parse 是純函數(單則進單則出),保留語意需要跨則狀態。

**新測試**(`tests/live/test_stock_state.py`):第一則帶 `HighPrice` → snapshot `meta.high` 有值;
第二則**不帶** → `meta.high` **維持前值**(不是 None);其餘 meta 欄位(name/ref/upper/lower)
仍以新值覆蓋(**只有 high/low 有保留語意**,別的欄位照舊)。

**新測試** `tests/live/test_stock_models.py`:REALTIME 含 Bid/Ask → `tick.bid_milli`/`ask_milli`;
Bid/Ask 缺 → `None` 且 `side` 判定不變(W-18);含 `HighPrice`/`LowPrice` → `meta.high_milli`/`low_milli`;
缺 → `None`。

**既有測試判定**:有 default 之後**全部不該紅**。若紅 → 代表某處以位置引數建構或斷言了
dataclass 整包,屬「該紅(建構式擴充)」,補欄位、**斷言內容一字不改**。

## 🟢-2 `copycat/live/stock_state.py` — 當日高低 running max/min + snapshot 帶出新欄位

**[amendment 2026-07-30: 資料源改動 — 當日高低改由本檔維護]**

```python
@dataclass
class StockDayState:
    ...
    high_milli: int | None = None   # 當日最高成交價(running max)
    low_milli: int | None = None    # 當日最低成交價(running min)
```

- `_apply(tick)` 內更新(**在既有累加之後,與 `MinuteAgg` 同一處**):
  `if self.high_milli is None or tick.price_milli > self.high_milli: self.high_milli = tick.price_milli`(low 同理取小)。
  ⚠ **只改高低,不動既有的 vwap / minutes / cum_* 累加**(W-18)。
- `reset()` 把兩者清回 `None`(**W-24**:它們是當日衍生狀態,不是 book/meta 那種盤外靜態值)。
  `apply_backfill` 走 `reset()` + 重放 `_apply` → 自動正確,不需另外處理。
- `snapshot()` **top-level** 加 `"high": self.high_milli, "low": self.low_milli`
  (與 `vwap` / `cum_inner` 同層,**不放進 `meta`**)。
- `snapshot()["ticks"]` 每筆加 `"b": t.bid_milli, "a": t.ask_milli`。
- **`update_meta` 不動**;`StockMeta` 不動。

**既有測試判定**:斷言 `snapshot()` 或 `snapshot()["ticks"]` **整包 `==`** 者 →
**🔴 該紅(僅多鍵)**,補鍵即可,**語意不變**;斷言個別鍵者 → 不該紅。
⚠ 誤判成「打到不該動的東西」而回頭拿掉欄位 = 讓項 1 與項 3 失去資料源。

**新測試**:三筆 tick(2380 / 2395 / 2370)→ `high_milli == 2395`、`low_milli == 2370`;
`reset()` 後兩者回 `None` 而 `meta` 保留(W-24);`apply_backfill` 重放後高低正確;
被 dedup / 試撮丟棄的 tick **不影響**高低(`ingest` 回 False 的路徑不進 `_apply`);
snapshot 的 `high`/`low` 在 top-level 且無成交時為 `None`。

## 🟢-3 `copycat/server/stock_engine.py` — WS tick payload 帶買賣價 + 當日高低

`:341-349` 的 `_publish` payload 加:

```python
"b": tick.bid_milli, "a": tick.ask_milli,
"h": state.high_milli, "l": state.low_milli,   # [amendment R5 + 資料源改動:取 state 不取 meta]
```
`_publish` 只在 `state.ingest(tick)` 為真時發,而 `ingest` 為真必然已跑過 `_apply` →
`state.high_milli` **必不為 None**,不需要 None 守衛(與原本掛 meta 時要寫 `if state.meta else None`
的差別)。

**[amendment 2026-07-30: review R5]** `h`/`l` 掛在 tick 訊息而不是另立 meta 訊息型別:
engine 現行只發 `tick` / `book` / `watchlist_quote` 三種,新增第四種型別要動前端的
訊息 dispatch 與所有相關測試;掛在 tick 上的成本是每則多兩個整數,而**當日高低本來就
只在成交時才會變**,語意上與 tick 同步天然正確。

**既有測試判定**:斷言 payload 整包者 → 🔴 該紅(補鍵);斷言個別鍵者 → 不該紅。
**新測試**:連續兩則 tick,第二則刷新高 → payload 的 `h` 跟著變。

## 🔴-4 `copycat/stock_watchlist.py` — schema v3(codes + 群組成員關係)

```python
_CACHE_VERSION = 3

class Watchlist(TypedDict):
    codes: list[str]           # 自選全體(有序)= 訂閱池
    groups: list[Group]

def load_watchlist(path: Path = DEFAULT_PATH) -> Watchlist
def save_watchlist(path: Path, wl: Watchlist) -> Watchlist
def ungrouped(wl: Watchlist) -> list[str]   # codes − ∪groups.codes,保 codes 序
def union(groups: list[Group]) -> list[str] # **保留不動**
```

**[amendment 2026-07-30: review R10 — 原寫「`union` 移除」與 §🔴-5 / §三 的兩處呼叫自相矛盾]**
`union` **保留**:v2 讀時遷移與 PUT `codes` 缺省是兩個**真 caller**,不是「未來可能」。
只移除 `load_watchlist_groups` / `save_watchlist_groups`(唯一 caller `app.py` 同輪改掉)。

- 遷移(讀時,不就地寫檔):

  | 檔案形態 | 判準 | 結果 |
  |---|---|---|
  | v3 | 有 `codes` **且**有 `groups` | 原樣 |
  | v2 | 有 `groups`、無 `codes` | `codes = union(groups)`、groups 原樣 |
  | v1 | 有 `codes`、無 `groups` | `codes` 原樣、`groups = []`(🔴 改) |
  | 空 / 檔不存在 | — | `{"codes": [], "groups": []}` |

- `save_watchlist` 驗證順序(錯誤碼與現行一致,W-2):
  1. 群組名 `strip()` 後為空 或 重名 → `BAD_GROUP`
  2. 所有 code(`codes` 與各群組)`validate_code` 為假 → `BAD_CODE`
  3. 群組內去重保序;`codes` 去重保序
  4. **正規化**:群組內出現不在 `codes` 的 code → append 進 `codes` 尾端
  5. `len(codes) > 30` → `WATCHLIST_FULL`
  6. atomic 寫 `{"_cache_version": 3, "codes": [...], "groups": [...]}`

**既有測試逐一標**(`tests/test_stock_watchlist.py`)
**[amendment 2026-07-30: review R6 — 原表只列 4 類且把上限那支標成不該紅,實際上 `:8-16`
的 top-level import 就含被移除的兩個名字 → ImportError 讓整檔 collect 失敗]**

| 測試 | 判定 |
|---|---|
| **全檔(11 支)** | **🔴 該紅(import 期即失敗)** —— `:8-16` 匯入 `load_watchlist_groups` / `save_watchlist_groups`。逐支改呼叫 `load_watchlist` / `save_watchlist`,**斷言的行為語意一字不改** |
| `test_v1_file_migrates_to_single_group` | 上述唯一**語意也要改**者 → 改寫為「v1 → codes 原樣、groups 為空」 |
| `test_saved_file_is_v2:56`(`_cache_version == 2`) | **事前標為「該變」**(鐵則 E 的合法通道)→ 改斷言 3,函式名改 `test_saved_file_is_v3` |
| `test_round_trip:37` / `test_missing_file_returns_empty:46` / `test_codes_deduped_within_group_keeping_order:91` / `test_shared_code_counts_once_toward_limit:72` | 🔴 該紅(僅因函式名),**斷言語意不動** |
| `TestValidateCode`(2 支) | 🔴 該紅(僅受 import 牽連),**斷言完全不動** |
| `union` 的既有測試 | **不該紅**(`union` 保留) |

**新測試**:`ungrouped()` 正確扣除且保序;群組含不在 codes 的 code → codes 自動補尾端;
v3 round-trip;30 檔上限以 `codes` 計。

## 🔴-5 `copycat/server/app.py` — API shape + 訂閱池

```python
class GroupsBody(BaseModel):          # 既有類別(:79),**不新開 WatchlistBody**
    groups: list[GroupBody]
    codes: list[str] | None = None    # 新增,選填

@app.get("/api/stock/watchlist")   → {"codes": wl["codes"], "groups": wl["groups"]}
@app.put("/api/stock/watchlist"):
    codes = body.codes if body.codes is not None else union(groups)
    saved = save_watchlist(wl_path, {"codes": codes, "groups": groups})
    await stock.set_watchlist(saved["codes"])                       # W-7
    return {"codes": saved["codes"], "groups": saved["groups"]}     # [amendment R9]
```
**[amendment 2026-07-30: review R16 — 原寫 `class WatchlistBody`,實碼是 `GroupsBody`(`app.py:448`)]**

`:188` 啟動時訂閱池:`persisted = load_watchlist(wl_path)["codes"]`。

**既有測試逐一標**(`tests/server/test_stock_routes.py`)

| 測試 | 判定 |
|---|---|
| GET 回傳整包斷言 | 🔴 該紅(多 `codes` 鍵) |
| **`test_get_empty_then_put_round_trip:140`**(`assert r.json() == {"groups": groups}`) | **🔴 該紅** —— PUT 回應加 `codes` **[amendment 2026-07-30: review R9 — 原表漏列]** |
| PUT 只送 `groups` 的測試 | **不該紅**(選填欄位的相容性正是靠它守住) |
| 斷言 `set_watchlist` 引數 | 不該紅(值等價) |

**新測試**:PUT 送 `{groups, codes}` → 存檔含 codes;PUT 只送 `groups` → codes = union;
GET / PUT 回應都含 `codes`;**未分組的 code 有進 `set_watchlist` 的引數**(SC-18 的機械守門)。

## 🔴-6 `frontend/src/hooks/useStockWatchlist.ts` — 型別與 mutation payload

```ts
export interface Watchlist { codes: string[]; groups: Group[] }
export function useStockWatchlist()  // → Watchlist
export function useSaveWatchlist()   // mutate(wl: Watchlist) → PUT {codes, groups}
export function errText(message: string): string   // [amendment R17:從側欄抽出共用]
```

- GET / PUT 回應解析:`{codes, groups}`;**缺 `codes` 的舊回應 → `codes = union(groups)`**
  (前端側的同名純函數,與後端規則一致) **[amendment 2026-07-30: review R9]**
- `errText`(三個錯誤碼的中文文案,W-2 釘住的契約)從 `WatchlistSidebar.tsx:23-28` 抽到本檔
  並 `export`,側欄與 Dialog **共用同一份**;複製兩份會漂而 W-2 只釘了「文案不變」。
  **[amendment 2026-07-30: review R17]**

**既有測試逐一標**(`useStockWatchlist.test.tsx` — **實檔只有 2 支,沒有錯誤解析測試**)
**[amendment 2026-07-30: review S10 — 原判定只涵蓋「回傳型別」,漏了同檔對 **request body**
的斷言,而 PUT body 從 `{groups}` 變 `{codes, groups}` 是契約改動,不事前標為「該變」就會以
「順手改 assertion」的形式被改掉(鐵則 E 的灰區)]**

| 測試 | 判定 |
|---|---|
| `:38` 讀取群組 | **🔴 該紅** —— `data` 由 `Group[]` 變 `Watchlist` |
| `:45` PUT 並回寫 cache(`:57` `toEqual({ groups: next })`) | **🔴 該紅**;**body 斷言事前標為「該變」** → `{codes: […], groups: next}`;**cache 回寫的斷言語意不變** |

## 🟢-7 `frontend/src/lib/watchlist-model.ts`(新檔)— 未分組模型純函數

```ts
export interface Watchlist { codes: string[]; groups: Group[] }
export function ungroupedCodes(wl: Watchlist): string[]
export function addCode(wl: Watchlist, code: string): Watchlist
export function removeCode(wl: Watchlist, code: string): Watchlist
export function assignToGroup(wl: Watchlist, code: string, group: string, slot: number): Watchlist
export function moveToGroup(wl: Watchlist, code: string, from: string, to: string, slot: number): Watchlist
export function detachFromGroups(wl: Watchlist, code: string, slot: number): Watchlist
export function removeFromGroup(wl: Watchlist, code: string, group: string): Watchlist
export function setMembership(wl: Watchlist, code: string, group: string, on: boolean): Watchlist
export function reorderUngrouped(wl: Watchlist, code: string, slot: number): Watchlist
export function renameGroup(wl: Watchlist, from: string, to: string): Watchlist
export function addGroup(wl: Watchlist, name: string): Watchlist
export function deleteGroup(wl: Watchlist, name: string): Watchlist
```

**[amendment 2026-07-30: review R2/R3 — 原只有 `assignToGroup` 且定義為「來源不動、只插入」,
(a) 把 round 4 拍板的跨組**移動**語意靜默改成複製,(b) 沒有承接 `moveCode` 的 off-by-one
補償 → 同組排序會退化成 no-op 或重複項]**

**`slot` 的語意(**四個**吃 slot 的函數共用,W-19)**:`slot` 是**相對目標清單「移除前」的
渲染索引**(含被拖那一列)。**[amendment 2026-07-30: review S2 — 原寫「三個插入型函數」
卻有四個吃 slot,且共用公式對 `detachFromGroups` 不成立]**

**兩種索引空間**(關鍵:目標清單與被改寫的陣列不見得是同一個):

| 目標 | 被改寫的陣列 | `at` | `slot` → 絕對 index |
|---|---|---|---|
| 群組(`assignToGroup` / `moveToGroup`) | `group.codes` | `group.codes.indexOf(code)` | slot 本身(同一個索引空間) |
| 未分組(`detachFromGroups` / `reorderUngrouped`) | **`wl.codes`** | `wl.codes.indexOf(code)` | `slot < ung.length ? wl.codes.indexOf(ung[slot]) : wl.codes.length` |

換算完之後兩者套**同一條**補償:

```
const index = at >= 0 && absSlot > at ? absSlot - 1 : absSlot;   // off-by-one 補償
arr = arr.filter(c => c !== code);
arr.splice(clamp(index, 0, arr.length), 0, code);
```

少了 `- 1` 這步,`[A,B,C,D]` 拖 A 到槽 3 會得到 `BCDA` 而不是 `BCAD`,且會靜默寫進後端
(`list-drag.ts:70-75` 的既有註解已記載這個失效樣態)。

**未分組那條為什麼不能直接用 slot**:未分組是 `wl.codes` 的**子序列**,而被改寫的是 `wl.codes`。
反例 —— `codes=[X,C,Y]`、`C` 屬某群組(所以未分組 = `[X,Y]`),把 `C` 拖到未分組槽 1
(X 與 Y 之間):不換算的話 `at = -1`(C 不在未分組清單裡)→ 不補償 → filter 後
`[X,Y]` 插在 index 1... 但真正該改的是 `codes`,正解是 `absSlot = codes.indexOf(Y) = 2`、
`at = codes.indexOf(C) = 1`、`2 > 1 → index = 1` → `[X,C,Y]`(維持中間)。

- `assignToGroup`(來源 = 未分組):目標組插入;**來源不需移除** —— 未分組是衍生集合,
  該 code 一旦屬某組就自動離開未分組。
- `moveToGroup`(來源 = 群組 A、目標 = 群組 B):**A 移除 + B 插入**(round 4 移動語意)。
  `from === to` 時退化為同組排序(W-19)。
- `detachFromGroups`(目標 = 未分組):**從所有群組移除** + 把 code 移到 `codes` 的對應位置
  (auto-default R18)。
- `reorderUngrouped`:未分組是 `codes` 的**子序列**;`slot` 是未分組清單內的槽,
  換算成 `codes` 的絕對 index 後套同一組 off-by-one 補償,群組成員在 `codes` 的相對位置不動。
- `deleteGroup`:只刪群組,**成員的 code 留在 `codes`** → 自動回到未分組。
- 全部純函數、回傳新物件。

**新測試**(`watchlist-model.test.ts`)。**W-19 的 5 個 case 逐條從 `list-drag.test.ts:103-149`
抄過來**(這是 §🔴-8 刪掉那些測試的前提條件,不是「砍測試」):
`A→槽3 = BCAD`、`A→槽4 = BCDA`、`D→槽0 = DABC`、一檔多組跨組 `X→槽3 = ABXC`、
目標無該檔 `X→槽2 = ABXC`。另加:`assignToGroup` 後該 code 不再出現在 `ungroupedCodes`;
`moveToGroup` 來源組確實少掉該 code;`moveToGroup(from === to)` 退化為同組排序且補償仍正確;
`detachFromGroups` 後所有群組都沒有它且它在未分組,**且位置正確** ——
`codes=[X,C,Y]`、C 屬某組、拖到未分組槽 1 → `codes` 仍為 `[X,C,Y]`(**位置斷言,不只是集合斷言**;
review S2:少了它,`detachFromGroups` 會重演 R3 的失效樣態而沒有測試會紅);
`deleteGroup` 後成員掉回未分組;`reorderUngrouped` 不動群組成員相對序 + 同款 off-by-one;
`renameGroup` 撞名 → 原樣不動;`removeCode` 從 codes 與所有群組移除;index 溢出 clamp。

## 🔴-8 `frontend/src/lib/list-drag.ts` — 未分組成為一個 drop zone

- `DropZone.group` 型別放寬為 `string | null`(`null` = 未分組區塊)。
- `dropTargetFromPointer` 回傳 `{ group: string | null; index: number } | null`。
- x 護欄 / 折疊 zone → `index = count` / 縫隙取最近 zone **全部不動**(W-6)。
- `moveCode` **移除**(語意搬進 `watchlist-model.ts`,W-19 的 5 支測試已逐條在新檔有對應)。

**既有測試逐一標**

| 測試 | 判定 |
|---|---|
| `dropTargetFromPointer` 的 6 支(`list-drag.test.ts:50-97`) | **不該紅** —— `group: string` 可賦值給 `string \| null`,是型別**擴充**;`ZONES`(`:44-48`)與 `toEqual({group:"主力",…})` 全數照常通過。 **[amendment 2026-07-30: review R15 — 原標「該紅」會誘使實作者去動通過中的行為斷言(鐵則 E)]** |
| `moveCode` 的 5 支(`:103-149`) | **🔴 該紅** → 刪除,由 `watchlist-model.test.ts` 的逐條等價測試取代 |

**新測試**:zone 的 `group` 為 `null` 時 `dropTargetFromPointer` 回 `{group: null, index}`。

## 🔴-9 `frontend/src/components/stock/WatchlistSidebar.tsx` — 側欄改版(SC-7~12, 15)

**移除**:群組標題列的 `+` 與 `×`、底部「+ 群組」按鈕、每列的 `⊞` 與其 checkbox 面板、
零群組 fallback 區塊(頂部搜尋框恆存後由它承接 W-16)。

**新增結構**:

```
<aside aria-label="自選清單" ref={asideRef}>
  <div className="sticky top-0 z-10 bg-bg">     ← 頂部搜尋框(恆存)
    <input placeholder="股號或名稱" /><button>新增</button>   ← 「新增」鈕保留(W-4)
    {suggestions.length > 0 && <ul data-testid="stock-suggest">…</ul>}
  </div>
  {error / save.error 文案}

  <section data-testid="wl-ungrouped">
    <header>[▾/▸] 未分組 <span>{n}</span></header>
    <ul data-testid="wl-list-ungrouped">{未分組逐列}</ul>   ← ⋮⋮ / code / 價+漲跌% / + / ×
  </section>

  {groups.map(g => <section data-testid={`wl-group-${g.name}`}> … </section>)}   ← ⋮⋮ / code / 價 / ×

  <button aria-label="管理群組與股票">管理</button>
  <WatchlistManagerDialog open={dlgOpen} … onGroupDeleted={dropCollapsed} />
</aside>
```

- **搜尋框**:`searchStocks(input, names, 8)`(round 4 既有純函數,不動)。
  三條加入路徑:**Enter** / 點**「新增」鈕** / 點提示列 —— 前兩條在提示列有命中時取第一筆、
  無命中時用 `input.trim().toUpperCase()` 原樣(**W-4 兩條路徑都要在**)。
  已在自選 → `addCode` 早退,**零 PUT**(W-21);Esc → 清空並收起提示列,**零 PUT**(W-21);
  名稱表為空 → 提示列不出現但直接輸入照常可加(W-21)。
- **未分組列的 `+`**:`aria-label={\`加入群組 ${code}\`}`;`groups.length === 0` → `disabled`(SC-9)。
  點開 → **該列正下方**渲染群組名清單(`<button aria-label={\`加入 ${code} 到 ${name}\`}>`);
  點一個 → `assignToGroup(wl, code, name, 該組長度)`(SC-10)。
- **`×`**:群組列 = `removeFromGroup`(該檔若因此不屬任何組 → 自動回未分組);
  未分組列 = `removeCode`(從自選整個移除)。
- **折疊**:群組沿用 `copycat-stock-wl-collapsed`;未分組用 `copycat-stock-wl-ungrouped-collapsed`。
- **折疊孤兒清理(W-20)**:`collapsed` state 住在側欄,而刪群組搬進 Dialog →
  Dialog 刪群組**成功後**回呼 `onGroupDeleted(name)`,側欄據此把該名字從 `collapsed` 與
  localStorage 移除。**[amendment 2026-07-30: review R4 — 原 spec 只說「W-3 的紀律搬過去」,
  漏了這條;沒有接線就會靜默失去,而重建同名群組會意外呈折疊]**
- **拖曳分支(SC-12)**:
  | 來源 → 落點 | 動作 |
  |---|---|
  | 未分組 → 群組 | `assignToGroup` |
  | 群組 A → 群組 B | **`moveToGroup`(移動:A 移除)** |
  | 群組 → 同一組 | `moveToGroup(from === to)` = 排序(W-19) |
  | 未分組 → 未分組 | `reorderUngrouped` |
  | 群組 → 未分組 | **`detachFromGroups`(從所有群組移除)** |
  | 側欄外 / Esc | **零 PUT**(W-6) |
  | **落點結果與現況相同** | **零 PUT**(早退,W-22) |

  **[amendment 2026-07-30: review S5]** 最後一列是既有行為(`WatchlistSidebar.tsx:198`
  `if (target.group === group && (target.index === at || target.index === at + 1)) return;`),
  原分支表五列全部直通 model 函數,把它弄丟了。丟掉的後果:把列拖起來再放回原位 → 送出
  **內容完全相同**的 PUT → `app.py:452` `set_watchlist` 重設整個訂閱池(W-7),TC4 全量
  UNSUB/SUB,**無錯誤訊號、無測試會紅**。新結構下改判「算出的 next 與現況深度相等 → 不 mutate」
  比逐分支寫早退條件穩(model 函數都是純函數,比對成本可忽略)。
  teardown 沿用 round 4 的單一 `teardown()`(移三個 listener),**不重新引入已被 mutation test
  證明不可達的 `cancelled` 旗標**。
- **`onSelect` 冒泡防護**(W-5):握把 / 折疊鈕 / `+` / `×` / 群組清單按鈕全部 `stopPropagation`。

**既有測試逐一標**(`WatchlistSidebar.test.tsx`,**round 4 版 466 行 / 30 支 `it(`**)
**[amendment 2026-07-30: review R4/R16 — 原表誤寫 427 行、只列 15 條,漏了 8 支必紅]**
**[amendment 2026-07-30: review S3 — 重掃後仍不是窮舉:實為 **30** 支(不是 29),過半行號指向
別的測試,且 3 支完全沒列到。本表改以**測試描述**為主鍵、行號僅供定位 —— 行號在 `[red]`
commit 改完測試後立刻失效,以它當主鍵是設計錯誤]**

| 測試(描述為主鍵;行號 = round 4 版定位用) | 判定 |
|---|---|
| aside `border-r` / `border-line`(`:77`) | 不該紅 |
| 所有群組 section 同時可見(`:86`) | 不該紅 |
| 點列觸發 `onSelect`(`:105`,W-5) | 不該紅 |
| 一檔多組 → 2330 出現 2 次(`:94`,W-1) | **不該紅** —— 前提是 Dialog **關閉時不渲染內容**且未分組為空(auto-default R13) |
| 拖拉握把 4 個(`:114`) | **不該紅** —— 同上前提;另 Dialog 內群組列的握把 `aria-label` **不得用「拖拉」前綴**(會撞 `/拖拉/` 查詢) |
| 折疊 → 列隱藏 + localStorage + 重 mount 維持(`:122` / `:132`) | 不該紅 |
| 提示列:名稱命中 / 代碼命中(`:151` / `:159`) | **🔴 該紅** —— 走 `openAdd(group)` 點 `新增到 主力`,該鈕已移除 → `getByLabelText` throw。改由**頂部搜尋框**觸發,斷言內容不變 |
| 群組 `+` → 該組搜尋框 → 加入該組(`:165`) | **🔴 該紅** → 改寫為「頂部搜尋框 → Enter → 進未分組」(SC-8) |
| 點「新增」鈕加入(`:179`,W-4 第二條路徑) | **🔴 該紅** → 改走頂部「新增」鈕;**這條路徑不得刪除** |
| Enter + 提示列無命中 → 原樣當股號(`:186`,W-4) | **🔴 該紅** → 改走頂部搜尋框,語意不變 |
| 已有的股票再加一次 → 零 PUT(`:196`,W-21) | **🔴 該紅** → 改走頂部搜尋框,**零 PUT 的斷言不變** |
| 搜尋框 Esc → 收起且零 PUT(`:205`,W-21) | **🔴 該紅** → 同上 |
| 名稱表為空仍可加入(`:214`,W-21) | **🔴 該紅** → 同上 |
| 新增群組(`:235`)/ 刪除群組(`:244`)/ 刪除失敗不跳 UI(`:262`,W-3)/ 折疊孤兒清理(`:251`,W-20) | **🔴 該紅** → **搬進** `WatchlistManagerDialog.test.tsx`(W-20 那支例外,見下方新測試) |
| 該組 `×` 只從該組移除(`:280`) | **🔴 該紅(語意擴充)** → 追加「該檔若不屬任何組則出現在未分組」 |
| `⊞` checkbox 切換所屬群組(`:294`,W-1) | **🔴 該紅** → 搬進 Dialog 測試,PUT body 語意不變 |
| 零群組 → PUT 建「自選」組(`:324`) | **🔴 該紅** → 改寫為「零群組 → PUT `{codes:["2317"], groups:[]}`」(W-16 的新實體) |
| 跨組拖曳 → 從來源組移除(`:372`,**移動語意**) | **🔴 該紅(僅 PUT body 多 `codes`)** —— **移動語意的斷言不可退讓**(W-19 / round 4 拍板) |
| **貼著側欄右緣(寬容內)放開 → 照樣搬組(`:390`)** | **不該紅** —— **前提**:`fetchMock` 的 PUT 分支仍以 `body.groups` 推進 `putBodies`。該支讀 `putBodies[0]?.[1]?.codes`,mock 形狀一改就無預警紅 **[amendment S3:原表把 `:390` 誤標成「拖到側欄外」]** |
| **剛超出側欄右緣寬容 → 零 PUT(`:397`)** | **不該紅**(W-6) **[amendment S3:原表漏列]** |
| 拖進折疊群組(`:407`) | **🔴 該紅(僅 body 形狀)** |
| 拖到側欄外 → 零 PUT(`:427`)/ 拖曳中 Esc → 零 PUT(`:435`) | **不該紅**(W-6);零 PUT 的斷言不變 |
| 同組拖曳 = 排序(`:444`,W-19) | **🔴 該紅(僅 body 形狀)** —— **排序語意與 off-by-one 不可退讓** |
| **空群組顯示「拖曳股票到此」(`:458`)** | **不該紅** —— **空組 placeholder 明訂保留**(新結構草圖未畫它不代表移除) **[amendment S3:原表漏列,兩種實作都合 spec,其中一種會讓它紅]** |
| `fetchMock`(`:32` GET 回 `{groups}`;`:42` PUT 回 `{groups: body.groups}`) | **🔴 該紅** → 兩者都改回 `{codes, groups}`;`putBodies` 同步改推整包 body(連帶影響 `:390`);**另留一支只回 `{groups}` 的測試**守住「舊回應 → codes 由 union 補」 |
| rect stub | **🔴 該紅** → 要多 stub `wl-ungrouped` section,否則未分組 zone 的 rect 全 0,SC-12 的正向拖曳測不出目標 |

**新測試**:頂部搜尋框恆存(零群組零股票時也在,W-16);未分組列 `+` 在零群組時 `disabled`(SC-9);
`+` → 群組清單 → 點擊 → PUT body 正確且該檔離開未分組(SC-10);未分組內拖曳排序;
**群組 → 未分組拖曳 → 該檔從所有群組消失**(SC-12c);群組列 `×` 後該檔回到未分組;
未分組折疊獨立於群組折疊;
**拖起來放回原位 → `putBodies` 為空**(W-22) **[amendment 2026-07-30: review S5]**;
**折疊孤兒清理必須在「側欄層」驗**(W-20) **[amendment 2026-07-30: review S4 — 原本把 `:251`
整支搬進 Dialog 測試,但 `collapsed` state 與 localStorage 住在側欄,Dialog 測試根本觀察不到;
Dialog 那邊只驗得到「`onGroupDeleted` 被呼叫」,接錯線或忘了寫 localStorage 那半仍全綠 ——
與 R4 指出的洞是同一個,只是從「沒寫」變成「寫了但沒人驗」]**:
預置 `localStorage[COLLAPSED_KEY] = ["觀察","主力"]` → 開 Dialog → 刪「觀察」→ 斷言
`JSON.parse(localStorage.getItem(COLLAPSED_KEY))` === `["主力"]`。

## 🟢-10 `frontend/src/components/stock/WatchlistManagerDialog.tsx`(新檔)— 管理台(SC-13/14)

**jsdom 事實(實測確認)**:jsdom **26.1.0** 的 `HTMLDialogElement-impl.js` 是空 class,
**沒有 `showModal()` / `close()`,也沒有 Esc→close 行為**;專案 vitest 無 `setupFiles`。
**[amendment 2026-07-30: review R1]**

```tsx
{/* ⚠ 不傳 open prop —— 見 auto-default 的 S1 說明 */}
<dialog ref={dlgRef} aria-label="管理群組與股票" onKeyDown={onEsc}>
  {open ? (   // ← 關閉時不渲染內容(auto-default R13)
    <>
      <h2>管理群組與股票</h2>
      <section aria-label="群組">…</section>
      <section aria-label="股票">…</section>
    </>
  ) : null}
</dialog>
```

- 開關:**只在 `useEffect` 內走單一路徑**,`open` 不進 JSX
  **[amendment 2026-07-30: review S1]**:

  ```ts
  const el = dlgRef.current;
  if (el === null) return;
  if (typeof el.showModal === "function") {
    if (open) { if (!el.open) el.showModal(); } else { el.close(); }   // 真瀏覽器:原生 modal
  } else {
    if (open) el.setAttribute("open", ""); else el.removeAttribute("open"); // jsdom:純屬性
  }
  ```
  `!el.open` 的守衛是必要的:重複 `showModal()` 在已 open 的元素上同樣 throw。
  真瀏覽器拿到原生 modal + focus trap + `::backdrop`;jsdom 走屬性路徑不炸。
- **Esc 自寫**:`onKeyDown` 攔 `Escape` → `onClose()`(不依賴原生行為)。
- 群組欄:每列 `⋮⋮`(`aria-label={\`排序 ${name}\`}` —— **不用「拖拉」前綴**,避免撞側欄的
  `/拖拉/` 查詢)/ 名稱 / `✎` 改名 / `×` 刪除;底部「+ 新增群組」輸入框。
- 股票欄:`wl.codes` 逐列 → 代碼 + 名稱 + 每個群組一個 checkbox
  (`aria-label={\`${code} 屬於 ${g.name}\`}`,W-1)+ `×`(`aria-label={\`從自選移除 ${code}\`}`)。
- 所有變更**即時 PUT**(與側欄共用 `useSaveWatchlist`),不做「按確定才存」。
- **W-3 紀律**:刪群組 / 改名 mutation 失敗 → 顯示 `errText(...)` 文案、不發第二次 PUT、
  不先跳 UI。**W-20**:刪群組成功 → 呼叫 `onGroupDeleted(name)` 讓側欄清折疊孤兒。
- 改名撞既有名 → `renameGroup` 原樣不動 + 顯示 `BAD_GROUP` 文案,**零 PUT**。
- `errText` 從 `useStockWatchlist.ts` import(**不複製一份**,W-2)。

**新測試** `WatchlistManagerDialog.test.tsx`:開啟後標題可見、關閉時內容不在 DOM;
新增群組 → PUT body;改名 → PUT body;改名撞名 → 零 PUT + 錯誤文案;
刪群組 → PUT body 且成員留在 `codes`;**刪群組 PUT 失敗 → 錯誤文案 + 無第二次 PUT(W-3)**;
**刪群組成功 → `onGroupDeleted` 被呼叫(W-20)**;checkbox 勾選 → PUT body(W-1,可勾兩組);
`×` → PUT body 的 `codes` 與所有群組都少掉它;Esc → `onClose` 被呼叫。

## 🔴-11 `frontend/src/lib/stock-accum.ts` + `TickTape.tsx` — 明細五欄(SC-4/5/6)

`stock-accum.ts`(新欄位一律**選填**,auto-default R8):

```ts
export interface TickRow { t: string; p: number; q: number; side: string;
                           b?: number | null; a?: number | null }
export interface StockTickMsg { …; b?: number | null; a?: number | null;
                                    h?: number | null; l?: number | null }
export interface StockAccum { …; high: number | null; low: number | null }  // top-level,不在 meta
```
**[amendment 2026-07-30: 資料源改動 — 高低掛 `StockAccum` top-level(與 `vwap` 同層),
不掛 `StockMeta`。連帶:review S7 的「`acc.meta === null` 分支」問題消失
(高低不再需要 meta 存在);review R8 列的 9 個 `StockMeta` fixture 也不必動,
只剩 `TickRow` 的 2 個檔要補 `b`/`a`(而它們是選填 → 也不必動)]**

`applyTick`:把 `msg.b ?? null` / `msg.a ?? null` 帶進 `ticks`;
`high: msg.h ?? acc.high`、`low: msg.l ?? acc.low`(缺欄位 → 保留原值)。
`fromSnapshot`:讀 top-level `snap.high` / `snap.low`,缺欄位 → `null`。

**同輪更正 `useStockStream.ts:5` 的檔頭註解** **[amendment 2026-07-30: review S9]**:
現寫「meta 走 snapshot(**engine 不發 meta WS 型別**,book 每則自足)」——
那正是 §🟢-3 用來論證 h/l 該掛 tick 的證據,改完之後它就地變成假的。
改為「meta 基底走 snapshot;**當日高低由 tick 的 `h`/`l` 增量更新**」。
(本 repo 剛因同類問題出過 `3ea8dca 🔴 fix(frontend): 更正 EnergySub 內自相矛盾的註解`。)

`TickTape.tsx`:props 加 `ref_: number | null`;表頭改五欄;

| 欄 | 內容 | 顏色 |
|---|---|---|
| 時間 | `t.slice(0,8)` | `text-ink-muted`(不變) |
| 買價 | `fmt(t.b)` / `-` | `priceTone(t.b, ref_)` |
| 賣價 | `fmt(t.a)` / `-` | `priceTone(t.a, ref_)` |
| 成交 | `fmt(t.p)` | `priceTone(t.p, ref_)` |
| 量 | `t.q` | `outer→text-bull` / `inner→text-bear` / 其他 `text-ink-dim` |

`priceTone(v, ref)`:`v == null || ref == null` → `text-ink-dim`;`>` → `text-bull`;
`<` → `text-bear`;`=` → `text-ink-dim`。**抽成模組級純函數並單測**(四個呼叫點共用一份)。

`StockPage.tsx:106`:`<TickTape ticks={accum.ticks} ref_={meta?.ref ?? null} />`。

**既有測試逐一標**(`TickTape.test.tsx` — **實檔只有 3 支**)
**[amendment 2026-07-30: review R11 — 原表 4 列有 3 列與實檔對不上;「載入更多分頁」的測試
根本不存在,而我把它標成「不該紅」= 以為 W-13 有守門]**

| 測試 | 判定 |
|---|---|
| `:10`「最新在上,外盤紅內盤綠」(**列序與顏色混在同一支**) | **🔴 該紅** → **拆成兩支**:「量依內外盤上色」(新語意)與「最新在最上」(W-14,`rows[0].textContent` 斷言**一字不改**) |
| `:27` 空態「尚無成交」 | 不該紅(W-13) |
| `:35` root `h-full` / `overflow-y-auto` | 不該紅(W-13) |

**新測試**:五個表頭文字;買 / 賣 / 成交三欄各自的三態顏色;買賣價 `null` → `-` 且灰;
量的內外盤三態顏色;`ref_` 為 `null` 時三個價都灰;
**點「載入更多」後列數 +30**(W-13 的分頁,**現況零守門**,本輪補上)。

## 🟢-12 `stock-intraday-svg.ts` + `StockIntradayChart.tsx` — 當日高低 + 現價圈(SC-1/2)

- 幾何:**不動** `yDomain`/`toY`/`priceAtY`/`yTicks`/`minuteToX`/`minuteOf`(W-10/W-17)。
  新增 `export function lastPoint(g: IntradayGeometry): { x: number; y: number } | null`
  = `priceLine` 末點(空線 → `null`)。
- 資料源 = **`accum.high` / `accum.low`**(top-level,不是 `accum.meta.high`)
  **[amendment 2026-07-30: 資料源改動]**。
- **域外不畫**:`highY`/`lowY` 依同檔 `overlayLines`(`:260-262`)同款規則 ——
  `p == null || p < yDomain[0] || p > yDomain[1]` → `null`。
  **[amendment 2026-07-30: review R12 — 原無域檢查,無漲跌停的 autofit 域(半幅由**分鐘收盤**
  極值 ×1.1 決定)裝不下**逐筆**極值,線會畫到時間軸上;而原新測試 `y === g.toY(high)`
  用同一個 `toY` 對答案 = 在任何實作下都綠的空斷言]**
- `ChartStatic`(memo)props 加**純量** `highY`/`lowY`(`number | null`,W-9):
  兩條 `<line data-testid="day-high" / "day-low" x1={Y_AXIS_W} x2={w}>`,
  樣式 `stroke-ink-muted` `strokeDasharray="4 3"` `strokeWidth={0.8}`
  ——與 y 軸格線(`stroke-line` `2 3` `0.5`)在色與節奏都不同(SC-1 可指認要求)。
  價位文字靠右緣 `textAnchor="end"` + `paintOrder="stroke"` + `stroke-surface` 描邊。
- 現價圈畫在 **memo 之外**(值每 tick 都變):
  `<circle data-testid="last-dot" r={3}>` + `data-testid="last-price"` 文字;
  tone 由 `accum.last.p` vs `meta.ref` 決定。

**既有測試判定**:全部**不該紅**(純新增元素)。若 `y-tick-price` / `crosshair-*` 相關紅
→ 代表打到不該動的東西。

**新測試**:`accum.high/low` 在域內 → 兩條線存在且 `y === g.toY(high/low)`;
**`accum.high` 高於 `yDomain[1]`(無漲跌停 autofit 情境)→ `day-high` 不渲染**;
`null` → 不渲染;`last-dot` 的 `cx/cy` 等於 `lastPoint`;三態 tone;
`priceLine` 為空 → 不渲染圓點且不崩;`ChartStatic` props 仍為純量(W-9)。

## 🟢-13 `frontend/src/components/stock/CandleChart.tsx` — 視窗高低標(SC-3)

- 複用既有 `windowHigh`/`windowLow`(`:416-417`)—— 這正是 SC-3「線與 figcaption 數字始終相等」
  可驗證的原因(同一個變數)。
- `ChartStatic` props 加純量 `highY`/`lowY`,畫兩條線 + 右緣標籤,樣式與江波圖同款,
  `data-testid="window-high"/"window-low"`。
- `shown.length === 0` → 不渲染。

**既有測試判定**:全部**不該紅**。
**新測試**:兩條線的 y 等於 `g.toY(windowHigh/Low)`;標籤文字等於 figcaption 數字;
滾輪縮放後兩者仍相等(SC-3 的機械守門)。

## 🔴-14 江波圖第二輪修正(SC-19~22 + 原項 1)—— `stock-intraday-svg.ts` + `StockIntradayChart.tsx`

**與 §🟢-12 合併實作**(同兩個檔、同一批幾何常數,拆開做會讓 x/y 映射改兩次)。

### 幾何(`stock-intraday-svg.ts`)

```ts
export const Y_AXIS_W = 46;        // 既有:左緣價位帶
export const R_AXIS_W = 40;        // 新增:右緣疊線標籤帶(SC-21)
export function plotWidth(w: number): number { return Math.max(1, w - Y_AXIS_W - R_AXIS_W); }
```
- `minuteToX` / `minuteOf` **共用同一個 `plotWidth`**(W-10 的互逆由建構保證);
  `minuteOf` 的界從 `x > width` 改為 `x > width - R_AXIS_W` → 右緣帶內不對應任何分鐘。
- **energyBars 改總量堆疊**(SC-22):
  ```ts
  maxTotal = Math.max(1, ...entries.map(([, m]) => m.o + m.i + m.u));
  energyBars = entries.map(([minute, m]) => ({
    x: toX(minute), outer: m.o, inner: m.i, unch: m.u,
    outerH: (m.o / maxTotal) * energyH,
    innerH: (m.i / maxTotal) * energyH,
    unchH:  (m.u / maxTotal) * energyH,
  }));
  ```
  `maxSide` **改名 `maxTotal`** 並改語意(**不是**保留舊名換算法 —— 舊名會讓「單邊」的誤解留在
  程式碼裡)。`SUB_TOP_PAD` 的留邊理由不變(頂端刻度文字要站的地方)。

### DOM(`StockIntradayChart.tsx`)

| 位置 | 改為 |
|---|---|
| `EnergySub` 的 bar | **一根堆疊**:外盤 `y = h - outerH`、內盤 `y = h - outerH - innerH`、未分類再往上;**`x = b.x - bw/2`、寬 `bw`**(置中於該分鐘,SC-19) |
| `EnergySub` 的刻度文字 | 值改 `maxTotal` 與 `maxTotal/2`;位置維持右緣 `textAnchor="end"` + 描邊(round 4 既有) |
| y-tick 文字(`:154-162`) | 依 `t.priceMilli` vs `ref` 上色:`>` → `fill-bull`、`<` → `fill-bear`、`=` → `fill-ink`(白)(SC-20) |
| 疊線 `<line>`(`:183-194`) | `x2={w - R_AXIS_W}`(原 `w - 34`) |
| 疊線 `<text>`(`:195-203`) | `x={w - R_AXIS_W + 2}`(落在右緣帶內) |
| 平盤虛線 / y-grid / crosshair-h | `x2={w - R_AXIS_W}`(原 `w`) |
| `X_LABELS` 垂直線、hover 垂直線、走勢線、填色 | 走 `minuteToX` → 自動內縮,不必逐處改 |
| 當日高低線(§🟢-12) | `x1={Y_AXIS_W} x2={w - R_AXIS_W}`;標籤放**右緣帶內** |

**既有測試逐一標**(`stock-intraday-svg.test.ts` / `StockIntradayChart.test.tsx`)

| 測試 | 判定 |
|---|---|
| 斷言 `priceLine[i].x` / `energyBars[i].x` / `minuteOf(x)` 具體數值、或以字串比對座標(`areaPolygon` / `pts()`) | **🔴 該紅(座標平移)** → 改期望為含 `R_AXIS_W` 的新值;fixture width 若要維持 1px/分需改成 `Y_AXIS_W + 270 + R_AXIS_W` |
| `minuteToX(X_END_MIN, w) === w` 一類的端點斷言 | **🔴 該紅** → 期望改 `w - R_AXIS_W` |
| **往返一致 `minuteOf(minuteToX(m,w)) === m`** | **不該紅** —— 互逆由共用 `plotWidth` 保證(W-10);若紅代表兩處常數沒共用 |
| `maxSide` 相關斷言 | **🔴 該紅(語意改)** → 改測 `maxTotal`,並**事前標為該變** |
| `energyBars[i].outerH/innerH` 的比例斷言 | **🔴 該紅(分母由單邊最大改總量最大)** |
| y-tick **文字內容 / 數量** | **不該紅**(只改顏色不改值,SC-20) |
| `toY`/`priceAtY`/`yTicks`/`refY`/`outerH` 之外的 y 相關 | **不該紅**;若紅 → 打到不該動的東西 |
| hover 以 `clientX` 觸發的那幾支 | **🔴 該紅(座標平移)** → 重算落點,**斷言內容一字不改** |

**新測試**:`energyBars` 的三段高度和 === `(o+i+u)/maxTotal*energyH`(SC-22);
`maxTotal` 取全日最大**總量**而非單邊;bar 的 `x - bw/2` 與 `minuteToX` 差 `bw/2`(SC-19);
`minuteOf(w - R_AXIS_W + 1) === null`(右緣帶不對應分鐘);
y-tick 文字的 class 依 `priceMilli` vs `ref` 三態(SC-20);
疊線 `x2 === w - R_AXIS_W` 且文字 `x >= w - R_AXIS_W`(SC-21)。

## ~~項 2 — 交易量對不到十字軸(待證據)~~ **已結案**

**[2026-07-30 user 補截圖後結案]** 症狀不在 K 線圖而在**江波圖內外盤副圖**,
兩條根因(bar 左緣 vs 中心、刻度單邊 vs 總量)已定位並落成 §🔴-14 的 SC-19 / SC-22。
以下保留原始的「找不到根因」記錄供追溯 —— 它本身是個教訓:
**我依 user 在選項題裡勾的症狀去找 K 線圖的幾何,找了很久都對得上;真正該做的是先要一張截圖。**

### (原記錄)

現況量測見 `current-state.md` §項 2:蠟燭與量 bar 共用同一組 `x`/`w`,十字線在 slot 中心,
垂直線下端 `plotBottom` 恰等於量 bar 基線,`svgBox`/`toSvgPoint` 的縮放映射也對得上
—— **靜態讀 code 找不到根因,與 user 指認的症狀矛盾**。

蒐證阻塞:chrome-devtools MCP 的 browser profile 被並行 session 佔用、
claude-in-chrome 擴充功能未連線 → 無法自行開瀏覽器複現。已備妥:vite dev server 在 **5180**
(proxy → 8721 的既有後端,`tc4: "up"`),一旦瀏覽器可用即可直接複現。

**處置**:鐵則 A(bug 要穩定重現 + 蒐證)與鐵則 E(不在 caller 加 `if` 規避 root cause)之下,
**不憑猜測改幾何**。等 user 補截圖 / 操作步驟(或瀏覽器可用)後補寫 SC-19 → 補 Phase 1 現況
→ 紅測試先行。若本輪拿不到證據,**列入下一輪並寫進 `docs/next-time.md`**。

## 檢附:🔴 / 🟢 commit 切分

| commit | 範圍 | 類 |
|---|---|---|
| 1 | 🟢-1、🟢-2、🟢-3(後端 tick 買賣價 + 當日高低,含 snapshot / WS payload) | 🟢 |
| 2 | 🔴-4、🔴-5(schema v3 + API + 訂閱池) | 🔴 |
| 3 | 🟢-7(`watchlist-model.ts` 純函數) | 🟢 |
| 4 | 🔴-6、🔴-8、🔴-9(hook 型別 + list-drag + 側欄改版) | 🔴 |
| 5 | 🟢-10(管理 Dialog) | 🟢 |
| 6 | 🔴-11(明細五欄 + 配色) | 🔴 |
| 7 | 🟢-12、🟢-13(江波圖當日高低 + 現價圈;K 線視窗高低標) | 🟢 |

每個 🔴 commit 內部再拆 `[red]`(先改測試轉紅)/ `[green]`(改實作轉綠)兩個 commit。
