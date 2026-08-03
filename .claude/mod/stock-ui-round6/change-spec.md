# change-spec — 個股 UI 第六輪(/mod ×5)+ 管理 Dialog 卡畫面(/bug ×1)

分支 `mod/stock-ui-round6`,base master `2f8c188`。現況表見同目錄 `current-state.md`。

## Phase 2 提問姿態分流

**判定:user 帶已成形改法**(6 項逐條列明位置 / 元素 / 期望外觀),命中「已成形方案」判準。
→ 採 `grilling` 姿態,不提 2-3 方案。實際停等三次:

1. `/auto` 退出條件不可解析 → user 選「6 項全改完 + 全 gate 綠」。
2. 項 5「左邊價位」落點歧義 → user 選「分時圖左緣的價位刻度軸」(附 ASCII 預覽確認)。
3. 項 2 實測推翻原題設(灰色大半是判定失準而非集合競價)= **scope 變更,/auto 必停**
   → user 選「修鎖停根因 + 呼應層」。

其餘實作級選擇一律 `[auto-default]` 標記推進。

## 項 2 的決策來源

`/adhd` 4 frames(對抗者 / 反轉 / 3am on-call / 10 歲小孩)× 6 構想 = 24 個,
我做評分分群後交 **fable subagent 拍板** → 採 **A2(斜線紋理)+ D1(未分類數字)+ D3(判定率)**。

⚠ **fable 拍板時我餵的前提有一條是錯的**:我寫「`derive_side` 是回測與盤中共用口徑」,
實際 grep 證明它只存在 `live/stock_models.py`,回測走 `Bar1K.UpVolume/DownVolume` 獨立鏈路。
fable 因此把 F1(改判定規則)判成 confirmed_trap。**該 trap 判定的理由不成立**,
但結論仍保留 —— 改成 tick rule 是換一整套演算法且本輪無對照驗證窗,由 user 拍板「不動」。
fable 的呈現層方案(A2+D1+D3)不受此錯誤前提影響,原樣採用。

---

# 成功條件(SC)—— 全部寫成畫面可指認表述,驗收由 user 對照過目

## 項 1|極值標記

- **SC-1.1** 分時圖上「當日最高」的標記是一個**空心圓環**(不是三角形),圓心壓在該價位上,
  顏色為中性灰(`ink-muted`),環外有一圈與底色同色的描邊使其在走勢線 / 紅綠填色上都看得清。
- **SC-1.2** 該圓環畫在**走勢線之上** —— 走勢線經過圓心時,線被圓環蓋住而不是蓋過圓環。
- **SC-1.3** 圓環旁的價位數字維持原本規則(高標在上、低標在下,撞到圖框翻面),文字未被裁切。
- **SC-1.4** K 線圖的視窗高 / 低標記同樣改成空心圓環(兩張圖視覺語彙一致)。
- **SC-1.5** 圓環與「現價圈」可一眼區分:現價圈是**實心**且帶紅 / 綠 / 灰漲跌色,
  極值圓環是**空心**且恆為中性灰。

## 項 2|內外盤副圖的灰色

- **SC-2.1** 內外盤能量副圖中,未分類量那一段由**實心灰**改為**斜線紋理**;
  外盤(紅)內盤(綠)兩段維持實心。肉眼可辨「紋理段不是第三種顏色」。
- **SC-2.2** 副圖下方說明列在「內盤 Y」之後出現「**未分類 N**」,N 等於該日各分鐘 `u` 加總。
- **SC-2.3** 說明列外盤比後方出現「**判定率 W%**」,W = (外+內) / 總量 × 100。
- **SC-2.4** 判定率低於 60% 時,「外盤比 Z%」文字轉為暗色(`ink-dim`)以示不可信;
  ≥ 60% 時維持原色。
- **SC-2.5**(後端根因)開一檔**鎖漲停**的股票,五檔委賣掛空、委買第一檔價格為 0 時,
  內外盤能量副圖**不再整片灰**,說明列的累積外盤 / 內盤**不再雙 0**,外盤比**算得出數字**。
  (2026-07-31 的 2327 國巨是現成樣本:改動前 外 0 / 內 0 / 未分類 5450、外盤比 `-`。)
- **SC-2.6** 柱高語意不變:全日最高那根柱仍頂到副圖頂端刻度,量刻度分母仍是**總量**
  (round5 E 決策保留)。

## 項 3|漲跌停亮燈

- **SC-3.1** 成交價 === 漲停價時,個股頁最上方 header 的「價格 + 漲跌%」整塊變成
  **紅底白字**(不只是紅色文字)。
- **SC-3.2** 成交價 === 跌停價時同一塊變成**綠底白字**。
- **SC-3.3** 五檔卡片標題列右側的「成交價 + %」在漲 / 跌停時同樣紅底 / 綠底白字。
- **SC-3.4** 未漲跌停時兩處維持現況(紅 / 綠 / 白文字,無背景)。
- **SC-3.5** 鎖漲停時五檔標題列的「鎖漲停」badge **確實出現**
  (現況因市價偽檔位打穿判定而不出現 —— 實測 2327 無 badge)。

## 項 4|`0` → 「市價」

- **SC-4.1** 五檔中價格欄為 0 的檔位,價格顯示「**市價**」而不是「0」;量照常顯示。
- **SC-4.2** 該「市價」列**不可點**(游標非 pointer、點了不發置中事件),
  其餘檔位點價行為不變。
- **SC-4.3** 閃電下單梯在有市價買單時,於階梯**最上方**多一列標「市價」並顯示市價買量;
  有市價賣單時於**最下方**多一列標「市價」顯示市價賣量。無市價單時兩列都不出現。
- **SC-4.4** 閃電梯的「市價」列**不可送單、不可點價**(即使已武裝),
  與既有「五檔不送單」紀律一致。
- **SC-4.5** 螢幕閱讀器標籤同步:`買1 市價` 而非 `買1 0`。

## 項 5|左緣價位軸漲跌停亮燈

- **SC-5.1** 分時圖左緣價位刻度軸**最上面那格**(漲停價)有**紅色背景、白色文字**。
- **SC-5.2** 分時圖左緣價位刻度軸**最下面那格**(跌停價)有**綠色背景、白色文字**。
- **SC-5.3** 中間各格(±8/6/4/2%、平盤)維持現況:無背景,文字色照 `tickTone` 規則。
- **SC-5.4** 恆亮 —— 不論今天有沒有真的漲跌停都要亮。
- **SC-5.5** 無漲跌幅資料的商品(`upper`/`lower` 為 null,走對稱 autofit 分支)兩格都**不亮**。
- **SC-5.6** 亮燈色塊不得蓋住繪圖區:整塊限制在左緣價位帶(`Y_AXIS_W = 36`)之內。

## Bug|管理 Dialog

- **SC-B.1** 進入個股頁、**沒有**點「管理」時,畫面上**沒有**任何空白大方框;
  分時圖 / K 線圖完整可見不被遮擋。
- **SC-B.2** 點「管理」後 Dialog 正常開啟、置中、內容完整(左群組右股票兩欄)。
- **SC-B.3** 按 `×` 或 `Esc` 關閉後,方框**完全消失**不留殘影。
- **SC-B.4** 關閉狀態下該 `<dialog>` 元素的 computed `display` 為 `none`(可用 devtools 驗)。

---

# 不能破壞的既有行為白名單(比新行為更重要)

- **W-1** 副圖量刻度分母 = 全日最大**總量**(外+內+未分類),round5 E 決策。不得改回單邊最大。
- **W-2** 堆疊順序(由下而上:外盤 → 內盤 → 未分類)不變;整根柱以 `b.x` 為**中心**(round5 A)。
- **W-3** 分時圖 Y 域**恰為** `[lower, upper]`,上下呼吸由 `PAD_Y` 出,不是價格域放寬(SC-4 舊)。
- **W-4** `toY` / `priceAtY` 共用同一組 `PAD_Y` / `X_LABEL_H`,互為逆函數。
- **W-5** `minuteToX` 與元件共用同一份 x 幾何;`minuteOf` 不 snap 最近,無資料回 null。
- **W-6** 極值標記的**等值反查**語意:反查落空(域外 / 無等值分鐘 / 缺 per-minute h,l)一律不畫,
  不退而求其次挑最接近的分鐘。
- **W-7** 極值標記的 x 承載「哪一分鐘」語意,夾制界取 **viewBox** 不取繪圖區;文字才做水平夾制。
- **W-8** 高 === 低(一字盤)時只留高標,不畫低標。
- **W-9** `hasRef` 紀律:沒有真昨收就不畫紅綠填色 / 不套漲跌色,不拿首筆成交價冒充平盤。
- **W-10** `ChartStatic` / `EnergySub` 的 `memo` 有效性:props 必須是純量或穩定 identity,
  不得因本輪改動而每次 render 重建(hover 每個 mousemove 都會 re-render 父層)。
- **W-11** SVG `clipPath` / `pattern` 的 id 必須過濾 `useId()` 的非識別字元後再拼進 `url(#…)`。
- **W-12** 五檔**不送單**(誤觸面大,送單集中在閃電梯);點價只發 `stock-price-click` CustomEvent。
- **W-13** 五檔檔位不足補「—」不塌陷,維持 5 列。
- **W-14** 五檔量 bar 歸一的 `Math.max(1, …)` 防除零不得移除。
- **W-15** `buildLadder` 固定界錨定:rows = 上界..下界全域合法 tick,center 只影響 `isCenter`/`dimmed`。
- **W-16** 閃電梯武裝紀律:換股 / 斷線 / idle / Esc / 連 3 次失敗 / 離開畫面一律自動解除。
- **W-17** 閃電梯點價 500ms 同格防抖 + `mutateAsync` 自行 then/catch(逐次計數)。
- **W-18** 閃電梯「跟隨置中」與手動捲動暫停跟隨的互動。
- **W-19** `<dialog>` 的 `open` **不進 JSX**;開關只走 effect + `showModal()` feature-detect
  (React commit 階段寫入 open 屬性會讓後續 `showModal()` 依標準拋 `InvalidStateError`)。
- **W-20** Dialog 關閉時**不渲染內容**(RTL 的 `getAllBy*` 不過濾隱藏元素,常駐渲染會讓側欄計數型斷言漂移)。
- **W-21** Dialog 的 `m-auto` 不可移除(Tailwind preflight 覆蓋 UA 的 `margin:auto` → 會貼左上角)。
- **W-22** 零 PUT 早退(三處:側欄 / Dialog / StockPage 加自選):內容相同的 PUT 會讓後端
  重設整個訂閱池(TC4 全量 UNSUB/SUB)。
- **W-23** 後端 `book.bids` / `book.asks` 仍**原樣保留** price=0 的市價檔位(項 4 要顯示它)。
- **W-24** `_parse_levels` 的「空價位跳過」語意(`price is None` 才跳)不變。
- **W-25** WS / REST payload 的欄位形狀不變(`u` / `book` / `cum_outer` / `cum_inner` 都在)。
- **W-26** 回測鏈路(`Bar1K.up_volume/down_volume/unch_volume`)零改動。
- **W-27** `tickTone` 對中間刻度的紅 / 綠 / 白 / 灰規則不變。
- **W-28** 分時圖左緣價位文字**右對齊**貼繪圖區左界(round4 項 6),垂直用 `dy="0.35em"`。

---

# Backward compat / migration

- 前端純顯示改動,無 localStorage / API 契約變更。
- 後端 `derive_side` 輸入取值改動:**payload shape 不變**,只有 `side` 值的分佈改變。
  live 狀態不持久化(重啟重建),無 migration。
- `buildLadder` 回傳型別改變 → 前端內部純函數,唯一 caller 同步改。
- `YTick` 加選填欄位 → additive。

# Out of scope

- **側欄自選列的漲跌停亮燈** —— `WatchlistQuote` 無 `upper`/`lower`,要動後端 WS payload。
  用 `chg_pct ≈ ±10%` 猜會誤判(ETF ±20%、無漲跌幅商品)。→ `docs/next-time.md`。
- **價差內成交(成因 B)的判定規則** —— 換 tick rule 是另一套演算法,本輪無對照驗證窗。user 拍板不動。
- **後端把 neutral 拆成四種成因** —— 要改 tick schema + `MinuteAgg`,超出本輪。
- **副圖圖例** —— 70px 高塞不下;先用 D1 的「未分類 N」文字承擔命名功能,驗證是否足夠。
- **資料劣化告警 / 監控細線**(E1/E2)—— 與「灰是什麼」正交,且門檻無統計依據。
- **09:00 / 13:30 柱的「集」字標記** —— 2.5px 柱寬無處放文字,且 09:00 柱的 neutral 混有盤中成分。

---

# Phase 3 — Diff 級(三類分開標記)

## 🔴 R-1 後端:`derive_side` 的輸入跳過市價偽檔位

`copycat/live/stock_models.py`
- 新增私有 `_best_price(levels) -> int | None`:回傳第一個 `price > 0` 的檔位價格,無則 None。
- `parse_stock_realtime`:`bid0 = _best_price(book.bids)`、`ask0 = _best_price(book.asks)`
  (原本是 `book.bids[0][0] if book.bids else None`)。
- `_parse_levels` **不動**(W-24),`book` 原樣保留 0 檔位(W-23)。
- 歷史 row 的 `derive_side(price, bid, ask)` 呼叫點:歷史 1K row 的 bid/ask 來源不同,
  逐一確認是否也會出現 0;若會,同樣套 `_best_price` 語意。

**既有測試**:`tests/live/test_stock_models.py` —— 不該紅(既有案例的 bid0 都 > 0)。
**新測試(紅先行)**:
- 鎖漲停簿 `bids=[(0,15966),(502000,9385)]` / `asks=[]`、成交 502000 → `side == "inner"`。
- 鎖跌停簿 `asks=[(0,N),(411000,M)]` / `bids=[]`、成交 411000 → `side == "outer"`。
- 正常簿不受影響(回歸鎖)。
- `book` 本身仍含 0 檔位(W-23 鎖)。

## 🔴 R-2 前端:極值標記三角 → 空心圓環 + 圖層上移

`frontend/src/lib/chart-extreme.ts`
- `ExtremeMarkStyle`:`half` / `height` → `radius`;`labelUp` / `labelDown` 依 radius 重算。
- 新增 `markCenterX(x, style, bounds?)`(整個圓一起平移的夾制,沿用三角的理由)。
- **移除 `trianglePoints`**(改完無 caller,已 grep 確認無動態用法)。
- `INTRADAY_MARK.radius = 3.5`、`CANDLE_MARK.radius = 4.5`。

`frontend/src/components/stock/StockIntradayChart.tsx`
- 極值標記 `<polygon>` → 兩個同心 `<circle fill="none">`:
  底環 `stroke-surface` strokeWidth 3.5、面環 `stroke-ink-muted` strokeWidth 1.5。
  `[auto-default: 空心雙環 | reason: 空心才不與實心現價圈 / hover 錨混淆(SC-1.5),
   底環提供任意底色上的對比,且不遮住穿過的走勢線]`
- **整個標記 `<g>` 移到主價線 polyline 之後**(SC-1.2)。
- `data-testid` 維持 `day-high` / `day-low`(既有測試選擇器),tag 由 polygon 變 circle。

`frontend/src/components/stock/CandleChart.tsx`
- 同步改圓環 + 確認圖層在蠟燭 / 線之上。
  `[auto-default: K 線圖一併改 | reason: chart-extreme.ts 檔頭明訂「共用的是規則」,
   只改一邊等於分岔;兩張圖極值語意相同,視覺語彙不該分裂(SC-1.4)]`

**既有測試**:`chart-extreme.test.ts` 的 `trianglePoints` 案例 → **該紅**(行為真的變了),
改寫為圓環幾何斷言。`StockIntradayChart.test.tsx` / `CandleChart.test.tsx` 若斷言 polygon → 該紅。

## 🔴 R-3 前端:灰段改斜線紋理 + 說明列補未分類 / 判定率

`frontend/src/lib/stock-intraday-svg.ts`
- 新增純函數 `sideSummary(minutes) -> { outer, inner, unch, total, outerPct, decidedPct }`。
  `[auto-default: 判定率門檻 60% | reason: 實測 2330=100% / 2317=83.7% / 6207=52% /
   4989=50.8% / 2327=0%;60% 恰好把「近漲停判定失準」與「正常」分開]`

`frontend/src/components/stock/StockIntradayChart.tsx`
- `EnergySub` 內 `<defs>` 定義一次 45° hatch `<pattern patternUnits="userSpaceOnUse">`
  (**必須 userSpaceOnUse** —— objectBoundingBox 會被每根 rect 各自拉伸)。
  id 走 `useId()` 過濾後的 uid(W-11)。
- 未分類 rect 的 `className="fill-ink-dim"` → `fill={url(#hatch)}`。
- `figcaption` 改印:`累積外盤 X · 內盤 Y · 未分類 U · 外盤比 Z%(判定率 W%)`;
  判定率 < 60% 時外盤比文字加 `text-ink-dim`。

**注意 W-10**:`EnergySub` 是 memo,新增的 pattern id 必須是穩定純量 prop,不可每次 render 新建物件。

## 🔴 R-4 前端:漲跌停亮燈(header + 五檔標題列)+ 修 badge 判定

`frontend/src/lib/stock-tick.ts`(或就近共用檔)
- 新增純函數 `limitState(lastMilli, upper, lower) -> "upper" | "lower" | null`。

`frontend/src/components/stock/StockPage.tsx`
- header 的價格 + % 區塊:`limitState` 非 null 時套 `bg-bull text-white` / `bg-bear text-white`
  + `rounded px-1.5`。
`frontend/src/components/stock/OrderBook.tsx`
- 標題列 `depth-last` + chg% 同樣處理。
- `lockedUp` 判定:`b[0]?.[0] === upper` → `b.some(([p]) => p === upper)`
  (市價偽檔位不再打穿;鎖跌停對稱)。

**既有測試**:`OrderBook.test.tsx` 的鎖停 badge 案例 → 不該紅(正常簿 b[0] 就是 upper)。

## 🔴 R-5 前端:五檔 `0` → 「市價」

`frontend/src/components/stock/OrderBook.tsx`
- `BookSide`:`price <= 0` → 價格欄印「市價」、`aria-label` 用「市價」、
  該列改渲染成不可點的 `<div>`(不是 disabled button —— 不需要 focus 進去)。

## 🟢 R-6 前端:閃電梯的市價列

`frontend/src/lib/stock-tick.ts`
- `buildLadder` 回傳 `{ rows, marketBidQty, marketAskQty }`(唯一 caller 同步改)。
`frontend/src/components/stock/PriceLadder.tsx`
- 階梯最上 / 最下條件渲染「市價」列(SC-4.3/4.4),不可點、不送單。

## 🟢 R-7 前端:左緣漲跌停刻度亮燈

`frontend/src/lib/stock-intraday-svg.ts`
- `YTick` 加 `kind?: "upper" | "lower"`;只有走 `upper !== null && lower !== null && ref > 0`
  那條分支時,±10% 端點標 kind(fallback 分支不標,SC-5.5)。
`frontend/src/components/stock/StockIntradayChart.tsx`
- `kind` 非空時,在該刻度文字後方畫 `<rect>` 底(限制在 `[0, Y_AXIS_W]` 內,SC-5.6),
  文字改白色;`kind` 為空維持 `tickTone`(W-27)。

## 🔴 R-8 Bug:Dialog 關閉時不佔版面

`frontend/src/components/stock/WatchlistManagerDialog.tsx`
- className 由固定字串改為 `cn(open ? "flex" : "hidden", "m-auto h-… w-… flex-col …")`。
  `[auto-default: 用 open prop 驅動 class,不用 Tailwind open: variant | reason:
   prop 是 showModal()/close() 的同一個真值來源,且 class 會隨 prop 變化 → jsdom 測得到;
   `open:` variant 產出的 class 字串恆定,測試只能斷言「有這個 class」抓不到回歸]`
- `open` 仍**不進 JSX 的 open 屬性**(W-19),只用來選 class。

**新測試(紅先行)**:`open={false}` 時 dialog 的 className 含 `hidden` 不含 `flex`;
`open={true}` 時相反。

---

# Phase 3 review 處置(change-spec-reviewer round 1:1×P0 / 6×P1 / 7×P2)

輸出檔 `change-spec-review-round-1.json`(本目錄)。逐條處置:

| # | 嚴重度 | 處置 |
|---|---|---|
| R1 | **P0** | **accepted** → 見 `[amendment 2026-07-31: R-1a]`。真環境已證實 spec 原樣不可達 |
| R2 | P1 | accepted → `[amendment: R-3a]` 四個數字全部同源 `sideSummary`,外盤比公式不變 |
| R3 | P1 | accepted → 實作時逐檔確認「該紅/不該紅」,共 13 條既有測試該紅並改寫,x 語意守門原樣保留 |
| R4 | P1 | accepted → `<dialog>` 補 `onClose` 拉回 prop 同步 |
| R5 | P1 | accepted(部分先行)→ 盤中已抓到 live 截圖 + `fixture-2327-limitup.json`(107KB) |
| R6 | P1 | accepted → hatch tile 內先鋪低透明度底色再疊斜線 |
| R7 | P1 | accepted → R-7 由 🟢 改標 🔴(端點 tickTone 被取代 = 既有輸出的行為改動) |
| R8 | P2 | accepted → 亮燈 rect 的 y 加夾制 |
| R9 | P2 | accepted → `kind` 改統一後處理,與 y 域分支條件天然對齊 |
| R10 | P2 | **已預先避開** → 測試用 `classList.contains` 不用 `toContain`(`flex-col` 不會誤命中) |
| R11 | P2 | accepted → 未分類 rect 走 `style={{fill:url(#…)}}` 且不掛 `fill-*` class |
| R12 | P2 | accepted → 兩處早退回完整形狀、`rows.length` 守衛續用、市價列不進 rowRefs |
| R13 | P2 | accepted(修正後採納)→ 夾制量改 `radius + ring/2`,**刻意不含 halo**(理由見下) |
| R14 | P2 | accepted → 明訂**維持既有計算**(市價量照算進 maxQty / 總量列),不在本輪改 |

## `[amendment 2026-07-31: R-1a]` 歷史 row 路徑(P0 修復)

原 R-1 只處理 `parse_stock_realtime`,歷史側寫成「逐一確認」= 未定案。真環境實測證實
spec 原樣**達不到 SC-2.5**:`apply_backfill` 先 `reset()` 再用回補重放,而歷史 TICKS row
只有單一 `Bid`/`Ask` 欄、鎖停時該欄就是 `0`,`_best_limit_price` 無從施力
(它吃 list,歷史側是純量)→ 每次切檔都把 live 判好的洗掉。
實測:2327 切檔後 `cum_outer = cum_inner = 0` 回到原點。

**修法**:新增 `relabel_locked_side(tick, upper, lower)`,由 `apply_backfill` 呼叫
(`reset()` 刻意保留 meta,依據就在手上;`parse_hist_tick` 的 caller `stock_source` 拿不到)。
規則是漲跌停制度下的恆等式而非猜測:鎖漲停時漲停價之上沒有更高價可掛,主動買方只能排隊,
唯一能促成成交的是主動賣方 → 內盤;鎖跌停對稱 → 外盤。四道閘見函式 docstring。

## `[amendment 2026-07-31: R-3a]` 說明列的統計來源

四個數字(外 / 內 / 未分類 / 判定率)**全部**走 `sideSummary(accum.minutes)`,不再混用
後端 running 值。外盤比公式**維持** `outer/(outer+inner)`(併入白名單語意)。
窗與副圖一致 `[09:00, 13:30]`。分母為 0 → `null` 顯示 `-`,不是 `0%`。

## `[amendment 2026-07-31: R-13a]` 標記夾制不含 halo

review R13 建議夾制量含底環線寬。**部分採納**:改用 `radius + ring/2`(墨色外緣),
**刻意不含 halo** —— 底環是與底色同色的墊片,溢出 viewBox 沒有視覺後果;把 halo 算進去
會讓分時圖為滿足「外緣 ≤ PAD_Y(4)」把環壓到 radius 2.5 = hover 收盤錨同尺寸,
反而製造本輪要避免的混淆。實作時另發現一條 spec 沒寫到的硬約束並用測試釘住:
**兩張圖的極值都會落在 y 域端點且是常態**(分時圖漲停 / K 線視窗高恆在 `PAD_Y`),
舊的三角靠「body 朝圖內」迴避裁切,圓環沒有方向可躲,只能靠尺寸。

---

# Known Risks

1. **hatch 在真實尺度的可辨性**:viewBox 800×70 縮放後,2.5px 柱寬內的斜線可能糊成淺灰。
   tile 已加底色(review R6)保證不會整段透明,但「紋理」意圖在極窄柱上仍可能弱化。
   jsdom 測不到,待 user 在有大量未分類的檔上過目。
2. **判定率門檻 60% 的吵雜度**:近漲停股常態落在 50%,會常顯示暗色外盤比。
   這是誠實的(那個數字確實不可信),但可能被感知為「壞掉」。留待 user 過目後調。
3. **鎖跌停分支無盤中樣本**:R-1 / R-1a 的鎖跌停路徑只有單元測試,無真環境實證。
4. **價差內成交(成因 B)未修**:4989 / 6207 之類近漲停股仍有約半數成交判不出來,
   現在會誠實顯示為低判定率。user 拍板本輪不動判定規則。
5. **市價量仍計入五檔的 `maxQty` 與總量列**(review R14 明訂維持):
   2327 實測市價 14167 vs 最佳限價 11877,量 bar 會被市價那列壓縮,總量列 26,216 混著兩者。
   本輪刻意不改 —— 要改需另立 SC 與白名單條目。

---

# 驗證證據(Phase 6 / 7)

## 自動化 gate(2026-07-31 12:5x 實跑,全綠)

| 指令 | 結果 |
|---|---|
| `npm test`(frontend) | **65 檔 / 874 tests passed**(baseline 828 → +46) |
| `npx tsc -b` | exit 0 |
| `npx eslint src` | exit 0 |
| `pytest -q` | **1471 passed** |
| `ruff check copycat tests` | All checks passed |
| `pyright` | 0 errors, 0 warnings |
| `copycat validate` | **42/42 PASS** |

## 真實環境(達錢 4 開啟,2327 國巨鎖漲停 502 是天然樣本)

**盤中 12:3x**(五檔 / 亮燈 / badge,DOM 實測值):
- `depth-head` 含「鎖漲停」badge(改前不出現 —— 判定被市價偽檔位打穿)
- `depth-quote` 背景 `rgb(240,82,79)` / 文字 `rgb(255,255,255)`
- 買1 `aria-label` = 「買1 市價」,量 14874;`ladder-market-bid` = 「14874 市價」
- 截圖 `after-2327-limitup-live.png`

**收盤後 12:5x**(後端根因,回補重放路徑):
- 改前 `cum_outer = 0 / cum_inner = 0`、未分類 5450(100%)、外盤比 `-`
- 改後 `cum_outer = 0 / cum_inner = 5804`、**未分類 0**、**判定率 100%**
- `book.bids[0] = (0, 14182)` 仍保留(W-23)
- tick 樣本 `b=502000 a= side=inner`

**全六項同框**(`after-all-six.png`,DOM 實測):
`dialogDisplay=none` / `page-quote` 紅底 `rgb(240,82,79)` / `y-tick-lamp-upper=fill-bull` /
`y-tick-lamp-lower=fill-bear` / `day-high` tag = `circle` / 未分類 0 / 判定率 100%

**Bug 的完整開關循環**(dev server 5174):
關閉 `display:none` rect 0×0 → 點「管理」`display:flex` 896×480 @(512,300) 內容完整
→ 點 × 關閉 `display:none` rect 0×0

## 待 user 過目(畫面類,SC gate)

SC-1.1~1.5 / 2.1 / 2.6 / 3.x / 4.x / 5.x / B.1~B.3 的**視覺**判定。
數值型的 SC-2.2~2.5 已由 DOM 實測值確認。

---

# Phase 5 自評 review 處置(round 1:0×P0 / 1×P1 / 9×P2)

輸出檔 `code-review-round-1.json`(本目錄)。白名單 **W-1 ~ W-28 逐條核過,28 條全數守住**。

| # | 嚴重度 | 處置 |
|---|---|---|
| 補判依據與 tick 不同源 | **P1** | **accepted 並修** —— 見下 |
| 首攻漲停那筆被反向誤標 | P2 | accepted 並修:補第 5 道閘(兩側都不可得才算鎖死) |
| survivors 不補判 | P2 | **rejected**:survivors 走 REALTIME 路徑,`_best_limit_price` 有五檔可退已判得出來;docstring 補說明為何兩者可以不同 |
| hatch 線畫在 tile 邊界只剩一半墨量 | P2 | accepted 並修:移到 tile 中心 |
| 亮燈色塊與文字不同心 / 下緣越界 | P2 | accepted 並修:`TICK_LAMP_H` 12 → 8(≤ 2×PAD_Y,兩端都不必夾制) |
| 市價列 `aria-label` 掛在 generic role 上 | P2 | accepted 並修:補 `role="group"`(這是本輪造成的可及性回歸) |
| figcaption 窄容器換行溢出 | P2 | accepted 並修:兩段各自 nowrap |
| buildLadder 早退測試理由不成立 | P2 | accepted:改寫測試名與註解成它真正守的東西(lib 層契約),不改行為 |
| 總量列含市價量的誤讀 | P2 | accepted(維持計算,補提示):有市價量時掛 `title` |
| chart-extreme 檔頭與函式註解矛盾 | P2 | accepted 並修:檔頭改寫成與 `markOuterRadius` 一致 |

## P1|補判依據與 tick 不同源

`relabel_locked_side` 拿 `self.meta` 當依據,兩條路徑會讓它**靜默**失效:

- **(a) meta 尚未到**:`set_main` 訂閱後立刻把回補入列,而 meta 只有收到 REALTIME 才由
  `_handle_quote` 寫入。server 冷啟動後第一次開一檔鎖停股時回補可能先跑完 →
  補判整段跳過,**且沒有任何重跑點**。本輪真環境驗到的成功其實有運氣成分(meta 剛好先到)。
- **(b) meta 是昨日的**:`_rollover_stage2` 對每個 state `reset()` 而 `reset()` 刻意保留 meta。
  主檔若不是觸發 rollover 的那一檔,會拿昨日的漲跌停比對今日 tick。

**修法**:`stock_engine._handle_quote` 偵測「漲跌停值變化」就把主檔回補重新入列 ——
冷啟動是 `None → 有值`、跨日是 `舊值 → 新值`,一次涵蓋兩者;值沒變不重跑,
避免每則 REALTIME 都排隊。另外 `apply_backfill` 在 meta 缺席且有 neutral tick 時
`logger.warning`,不再靜默。

## 收斂後的驗證

`pytest -q` **1472 passed** / `npm test` **874 passed** / `ruff` / `pyright` / `tsc` / `eslint` 全綠。
真瀏覽器複驗:亮燈色塊中心與文字 y 完全重合(上 4/4、下 282/282)、下緣 286 恰貼繪圖區底
(不侵入時間標籤帶)、hatch 線 `x1=x2=1.5`(tile 中心)。

self_review_head: 14ea35db3e0f6a7cc48ca697da3eae71b8933cef

---

# round6b / round6c —— user 過目後的兩次修正(已 merge)

畫面交付後 user 過目,推翻三條先前的取捨。兩次都只動**視覺語彙**,後端與統計口徑零改動。

## round6b(`7aa7ddb`)極值標記

| 先前 | 現在 | 被推翻的理由 |
|---|---|---|
| 空心環 | **實心圓**(r 3 → 2.5) | 「空心才不與實心現價圈混淆」→ 改靠**位置**區分:現價圈永遠在走勢線末端 |
| 中性灰 | **相對平盤判色**(高紅 / 低綠 / 平盤灰),圖案與文字同色 | round4 就寫著「整天下跌的股票其日高塗紅等於假陳述」—— **這條顧慮從一開始就不成立**:判色基準是平盤不是「高低」,那種股票的日高本來就判綠。已加測試釘住此案例 |
| K 線圖同樣畫圖案 | **只留文字**,最高紅字 / 最低綠字 | 蠟燭圖本身已把「哪一根最高」講清楚,再加一顆點只是在影線端點多一塊遮蔽物 |

新增 `markTone()`。與 `tickTone` 差一處:平盤是灰不是白(user 指定,語意是「這個極值沒有
方向可言」而不是「這是基準」)。`ExtremeMarkStyle.dot` 改成可為 null 表達「這張圖不畫圖案」。

分時圖的 `radius + ring/2 ≤ PAD_Y(4)` 約束仍在 —— 漲停時標記恰在 y 域頂端且**是常態
不是邊角**,舊的三角靠「body 朝圖內」迴避裁切,圓沒有方向可躲只能靠尺寸。

## round6c(`dfbc795`)成交量副圖

user:「交易量還是有灰色的部分,乾脆不要分顏色,就單純顯示量即可」。

副圖演變到此:內外盤並排 → 總量堆疊(round5 E)→ 灰段斜線紋理(round6)→ **單色單根**。

`EnergyBar` 由 `{outer, inner, unch, outerH, innerH, unchH}` 收斂成 `{total, h}`;
斜線 pattern 與 `hatchId` prop 移除;svg aria-label 由「內外盤能量」改「成交量」。

**內外盤統計沒有消失,只是移出圖形語彙** —— 說明列仍印 外盤 / 內盤 / 未分類 / 外盤比 /
判定率,判定率 < 60% 時外盤比照樣降對比。W-1(柱高分母 = 全日最大總量)保留,
另加一條元件級測試釘住 269:100 的高度比,分母若退回單邊最大這個比例會跑掉。

## 這三輪的教訓

前三次改動(並排 → 堆疊 → 紋理)全都在處理「灰色長什麼樣」。user 最後一句話點出真正的
問題是**量柱本來就不該承載方向**。同一個視覺元素被連續反映時,先問「這個元素該不該存在」
再問「它該長什麼樣」。

## 收尾狀態(2026-07-31)

master `dfbc795`,離線 `--ff-only` merge(repo 無 remote),本輪共 14 個 commit。

`pytest` 1472 passed · `ruff` clean · `pyright` 0 errors · `copycat validate` 42/42 PASS ·
`npm test` **880** passed / 65 檔 · `tsc -b` exit 0 · `eslint src` exit 0 · `check_feat_tags` PASS。

user 已過目確認「沒問題」→ SC 驗收 gate 通過。
