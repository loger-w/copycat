# change-spec:台股綜合一頁總覽 + 相關係數升頂層 tab + 家數帶停板實心色 + 騰落線紅綠

> /mod Phase 2 產物(2026-08-16)。現況表見同目錄 `current-state.md`。
> **分流判定**:已成形方案(prompt 指名落點檔案 / UI 形式 / 三案佈局;D6/D7/D8 已由 user 拍板)
> → grilling 姿態、事實自查、決策點逐題 `[auto-default]`,不再重問拍板項。
> 規模:**L**(≥ 8 檔前端;無後端、無 API、無資料 migration)→ spec review 1 輪 + P0 限縮加輪。
> UI 輪約束(batch2 spec 檔頭):**一致性優先** —— 只用既有 token(`bull/bear/line/surface/ink*`),
> 不加字體 / 動效 / 新色;`frontend-design` / `bencium` 兩支 skill 已載入,其「先問再做」條款由
> 本檔 `[auto-default]` 停等規則(core-flow §2)覆寫。
>
> **Changelog**:round 1 review 15 findings 全 accepted(`change-spec-review-round-1.json`);round 2 限縮輪 12 findings
> (P0 0 / P1 3 / P2 9)全 accepted(`change-spec-review-round-2.json`),無新 P0 → 不加輪。修改段落標 `[amendment ... r1|r2: ID]`。

## 0. 目標一句話
台股綜合頁在 1920×1080 / 1536×864 常見視窗下**單螢幕不捲動**:左欄壓縮(基差 / 雙圖 / 家數帶 /
騰落線),右欄漲跌停列表整高內捲;相關係數自 subtab 升為第 5 顆頂層 tab;家數帶停板兩桶實心;
騰落線改紅綠雙色。

## 1. 成功條件(SC gate:每條附驗證方式;UI 條寫「畫面可指認」)

| # | 成功條件(畫面可指認) | 驗證方式 |
|---|---|---|
| SC-1 | 頂層 nav 由左至右 = `台股綜合 \| 個股(期) \| 選擇權 \| 期貨 \| 相關係數`(5 顆,相關係數最後);點「相關係數」顯示六腿江波圖 + 相關係數表(RiverPanel 在上、CorrPanel 在下);右欄顯「此頁無可下單標的」 | vitest `App.test.tsx`「nav tab 順序」改為 5 顆;截圖 `evidence/SC-1-corr-tab.png` |
| SC-2 | 台股綜合頁**沒有** subtab 列(無「台股綜合分頁」tablist);漲跌停列表恆在右欄;`copycat-index-subtab` 啟動即被清除;主 tab 切離時列表 / 分 K 輪詢仍停(active gate 全鏈不變) | vitest `IndexPage.test.tsx` 新 (l1)(l2);`App.test.tsx` purge 測試 + 既有 active gate 測試綠 |
| SC-3 `[amendment 2026-08-16 r1: CS-2]` | 1920×1080 與 1536×864 兩種視窗、台股綜合 tab、預設偏好下:**整頁無垂直捲軸且主 grid 自身也不捲**,漲跌停列表在右欄框內自帶捲軸;左欄自上而下 = 基差列 → 雙圖並排 → 家數帶 → 騰落線 | claude-in-chrome 兩種視窗各一張截圖 `evidence/SC-3-1920.png` / `evidence/SC-3-1536.png` + **三段 JS 量測記入 verification.md**:(1) `document.scrollingElement.scrollHeight === clientHeight`;(2) `[data-testid=index-main-grid]` 的 `scrollHeight <= clientHeight + 1`;(3) 右欄**恆存**捲動容器 `[data-testid=limit-list-scroll]`(message 與 table 兩分支都包在其中,`[amendment r2: R2-5]`)的 `scrollHeight > clientHeight`(內捲真的發生在該處;列數不足時記數值並以 SC-3(2) 為準)。截圖另加 `evidence/SC-3-sticky.png`:右欄列表捲到中段,表頭九欄仍可見且與內容有分隔 `[amendment r2: R2-6]`;截圖同時核「騰落線 0 軸與 ±span 標籤不重疊可辨識」`[amendment r2: R2-11]`(不合格時備案:H < 90 只留 0 軸標籤,寫入 spec 再實作)。vitest 鎖 class:主 grid 含 `overflow-y-auto` 且 root 無;`limit-list-scroll` 含 `overflow-auto` + `min-h-0`(兩態皆在);th sticky lock 帶 rows fixture |
| SC-4 `[amendment 2026-08-16 r1: CS-1 / CS-5]` | 兩張指數圖高度**隨容器剩餘高**(不是寬 × 220/640):同一視窗下把瀏覽器高度縮 200px,圖跟著矮而頁面仍不捲(量測不可用時退回固定 640×220 — jsdom 與既有測試路徑不變) | 截圖 `evidence/SC-4-short.png`(視窗高 −200);vitest `MarketChart.test.tsx` 新增「傳入 `height={H}`(viewBox 單位)→ intraday svg `viewBox="0 0 640 H"`;candle 態 `candle-figure` 內 svg viewBox 第 4 欄 = H(寬 1400)」;未給 height:intraday 220、candle 578 `[amendment r2: R2-1 / R2-2]`;`MarketPane` 量測 lock:**只在該 it 內** `vi.stubGlobal("ResizeObserver", Fake)` + `afterEach(() => vi.unstubAllGlobals())`,Fake 在 `observe(node)` 時同步呼叫 callback 餵 `[{contentRect:{width:430,height:300}}]` → 左 pane svg viewBox 高 = `paneSvgHeight` 期望值(≠ 220);對照案不 stub → 仍 220(W-10)`[amendment r2: R2-8]` |
| SC-5 | 家數帶「漲停」桶 = 實心 `bg-bull` 紅底 + 白字(標籤與數字皆白)、「跌停」桶 = 實心 `bg-bear` 綠底 + 白字;上漲紅字 / 下跌綠字 / 平盤 ink 且三桶無底色(D8,PR #53 不動) | vitest `BreadthBand.test.tsx` (g)(o) 改寫為 `text-white`,(f)(l)(m)(n)(p) 不動;截圖 SC-3 兩張同時可指認 |
| SC-6 `[amendment 2026-08-16 r1: CS-3 / CS-7]` | 騰落線:net>0 區段線與面積為 `bull` 紅、net<0 區段為 `bear` 綠(以 0 軸裁切,同 StockIntradayChart 昨收上下手法),面積 `fillOpacity 0.15`;末值標籤色不變;0 軸 / 刻度 / 固定域不變 | vitest `AdvanceDeclineChart.test.tsx`:新增 (k) 兩段線 testid `adl-line-up` / `adl-line-down` 各帶 `stroke-bull` / `stroke-bear` + `clipPath="url(#<id>-above|-below)"`,且 `<defs>` 內有同 id 的 `<clipPath>`、id 只含 `[A-Za-z0-9_-]`;(l) 面積 `adl-area-up/down` 各 fill-bull/fill-bear;(d)(e)(f) 錨改 `adl-line-up`;(h)(i) 改寫為 up/down 皆 null;截圖 SC-3 可指認 |
| SC-7 `[amendment 2026-08-16 r1: CS-10 / CS-12]` | IndexPage 容器寬 < 1050px(≈ 視窗 < 1400px;容器寬 = 視窗 − 349:rail w-72 288 + pl-3 12 + border 1 + 外層 px-4 32 + gap-4 16)時退回上下堆疊:左欄內容在上、列表在下,整頁可捲(舊行為);左欄寬 < 700px 時雙圖再退回上下堆疊(既有 auto-fit 語意的顯式化,W-12) | vitest 鎖 class 字串(主 grid `@[1050px]:grid-cols-[...]`;雙圖 grid `grid-cols-1 @[700px]:grid-cols-2`);截圖 `evidence/SC-7-1280.png`(視窗 1280:堆疊)與 `evidence/SC-7-1440.png`(視窗 1440×900:兩欄邊界證據) |

**驗證窗口**:所有 SC 皆可用側車 / fake 資料在盤外驗(截圖需 breadth 有值 → 用 `--verify` 側車或既有 fixture 路徑;無法取得真資料時 SC-3 允許以「載入中」文案版面截圖,佈局判定不受資料影響)。

## 2. 不能破壞的既有行為白名單(reviewer / 自評 finder 對照節;行號 = current-state.md 引用)
- W-1 `BasisRow` 文案 / 顏色 / 位置(雙圖之上)逐字不變。
- W-2 雙圖內容與 overlay(PR #52):標的列 / 週期列 / 重疊鈕只在左圖 / 兩 pane 各自 localStorage key(`copycat-market*`)/ 均價 / CDP / MA / 昨收標籤 / K 線模式與 meta 列 / 重疊圖外觀(巢狀 figure + 標題列)。
- W-3 家數帶十個數字、戳記、stale 徽章、up/down 字色(text-bull / text-bear)、平盤 ink、桶序。
- W-4 騰落線 net 定義、對稱域、0 軸、刻度、末值標籤染色、固定 x 域、空態文案。
- W-5 漲跌停列表所有欄 / 篩選 / localStorage filter / 文案三態 / `onOpenStock` 跳個股(期)/ 10 秒輪詢 / `active` gate(切離 index tab 停輪詢)。
- W-6 相關係數頁功能只搬家:RiverPanel + CorrPanel、兩支 hook、`copycat-river-*` key、lazy chunk 邊界(`CorrPage` 仍 `React.lazy`)。
- W-7 其他三個頂層 tab(個股(期)/ 選擇權 / 期貨)順序、內容、`visited` lazy 語意、右欄常駐與 railCtx。
- W-8 `copycat-tab` 舊值 stock/futures/txo 還原不變;無值 fallback `index` 不變。
- W-9 視窗窄時主 grid 退回上下堆疊(SC-7 明訂容器斷點 1050px)。
- W-10 `[amendment r1: CS-6]` useContainerSize 量測不可用(jsdom / ResizeObserver 缺席 / 首幀)時圖表退回固定 SIZE 且**不溢出容器**(騰落線 fallback 態由 svg `h-full w-full` + 預設 preserveAspectRatio meet 縮放置中承接;雙圖 fallback 態高度 = 寬 × 220/640,由 figure `min-h-60` 與主 grid 逃生口承接),既有 MarketPane / MarketChart 測試零改動即綠。
- W-11 大盤分 K 的 active gate(App.test「切離台股綜合 tab → 大盤分 K 停止背景輪詢」)。
- W-12 `[amendment r1: CS-12]` 雙圖在窄容器自動堆疊(舊 `auto-fit minmax(480px)` → 新 `@[700px]` 顯式斷點;語意保留)。

## 3. Backward compat / migration `[amendment 2026-08-16 r1: CS-4]`
- `copycat-tab`:值域**放寬**加回 `corr`(R1 前曾合法)。舊瀏覽器留的 `corr` 重新還原到相關係數 tab — 預期行為(D7)。零遷移碼。
- `copycat-index-subtab`:進 `ORPHAN_STORAGE_KEYS`,App 啟動 purge。**行為改動**:R1 後把 subtab 停在「相關係數」的使用者,升版後台股綜合頁看到的是漲跌停列表(恆掛、10 秒輪詢),相關係數改由頂層 tab 取回 —— 這是 D7 的直接結果,歸 🔴。**可逆**:git revert(無資料破壞)。
- 無後端 / API / 檔案格式改動。

## 4. 畫面章節(D6 拍板 A;B / C 列為對照,不實作)

```
A(拍板)                                     B(左欄雙圖上下)              C(三欄)
┌────────────────────┬─────────────┬─rail─┐   ┌────────┬────────┐        ┌───┬───┬─────┐
│ 台指期 42142 價差…  │ 漲跌停列表    │      │   │ 基差   │ 列表    │        │加權│櫃買│列表  │
│ ┌────────┬────────┐│ 上市 上櫃 …  │      │   │ 加權圖  │        │        │    │    │      │
│ │ 加權   │ 櫃買   ││ ─────────── │      │   │ 櫃買圖  │        │        ├────┴────┤      │
│ │  圖    │  圖    ││ 2330 台積電…│      │   │ 家數帶  │        │        │ 家數帶   │      │
│ └────────┴────────┘│ 2454 聯發科…│      │   │ 騰落線  │        │        │ 騰落線   │      │
│ 漲跌家數 上市 …    │   (內捲)    │      │   └────────┴────────┘        └─────────┴─────┘
│ 騰落線 ~~~~~~~~   │             │      │
└────────────────────┴─────────────┴──────┘
```

### 4.1 版面規格 `[amendment 2026-08-16 r1: CS-2 / CS-6 / CS-9 / CS-10 / CS-11 / CS-12 / CS-15]`
- IndexPage root:`@container flex min-h-0 flex-1 flex-col`(**移除 `overflow-y-auto`**)。
- 主 grid(`data-testid="index-main-grid"`):`grid min-h-0 flex-1 gap-3 grid-cols-1 overflow-y-auto @[1050px]:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]`
  (兩欄態不覆寫 overflow:正常尺寸內容恰填滿不出捲軸,極矮視窗當逃生口 — §7 edge 2;SC-3(2) 直接量此元素證明沒捲)。兩欄 3:2。`[auto-default: 3fr/2fr | reason: 列表 9 欄約 520px 即可讀;左欄雙圖各 ≥ 350px 才不至於週期列折三行]`
- 左欄:`@container flex min-h-0 flex-col gap-3`(自身也是 container,供雙圖斷點量左欄寬)= BasisRow(shrink-0)→ 雙圖 grid `grid grid-cols-1 gap-3 min-h-0 flex-1 @[700px]:grid-cols-2`(W-12)→ `<section className="flex shrink-0 flex-col gap-2">` 家數帶 + 騰落線。
- 右欄:`flex min-h-0 flex-col rounded-md border border-line bg-surface`(沿舊 subtab 外框盒);`LimitListSection` root 改 `flex min-h-0 flex-1 flex-col pt-2`;`LimitListBody` root 改 `flex min-h-0 flex-1 flex-col gap-2 px-4 pb-4`,標題列 / 篩選列 shrink-0,恆存捲動容器(`data-testid="limit-list-scroll"`,**同時包住 message 文案與 table 兩分支**)`min-h-0 flex-1 overflow-auto`;表頭:**每個 `<th>`** 掛 `sticky top-0 z-10 bg-surface border-b border-line`,`<tr>` 的 `border-b border-line` 移除(border-collapse 下 tr border 不隨 sticky 黏)。`[auto-default: th sticky | reason: 內捲後表頭捲走則欄義不可讀;零新 token]`
- MarketPane:root 加 `min-h-0`;figure 加 `min-h-60 flex-1`(**只此一條 min-height,不同時掛 min-h-0** — `[amendment r2: R2-3]`;`min-h-60` = 15rem:堆疊 / 內容決定高的模式下 figure 有地板,量測 → 內容 → 量測收斂,不形成回饋迴圈);figure 內 chart wrapper(`mt-2 flex min-h-0 flex-1 flex-col`;可縮的 `min-h-0` 只在 pane root 與此 wrapper)掛 `useContainerSize` ref。**口徑(CS-1 釘死)**:`MarketChart` / `OverlayCard` 的 `height` prop = **viewBox 單位**高度(未給 → 220);px→viewBox 反解與 chrome 扣除**全部**由 MarketPane 內 `paneSvgHeight(size, frame)` 完成 `[amendment 2026-08-16 r2: R2-1 / R2-2 / R2-4]`:`frame = { chromeY, insetX, vbW }` per-mode 常數表 `PANE_FRAMES`:
  - intraday `{ chromeY: 26, insetX: 0, vbW: 640 }`(toggle 列 h-[1.375rem] 22 + mb-1 4;svg 直接在 wrapper 內)
  - overlay `{ chromeY: 62, insetX: 34, vbW: 640 }`(OverlayCard 巢狀 figure border 2 + p-4 32 + 標題列 20 + svg mt-2 8;水平 border 2 + p-4 32)
  - candle `{ chromeY: 100, insetX: 34, vbW: 1400 }`(CandleChart 自身 figure border 2 + p-4 32 + 頂列 26 + 底列 figcaption 20 = 80;再加 MarketChart meta 列 text-xs 16 + mt-1 4 = 20;水平 34;**viewBox 寬是 CandleChart 的 `DIMS.width = 1400`**)
  `svgW = size.width − insetX`,`renderPx = max(96, floor(size.height − chromeY) − 2)`,`vbH = round(renderPx × vbW / svgW)`;`size` 任一 ≤ 0 或 svgW ≤ 0 → 回 `undefined`(呼叫端走各自 fallback)。MarketPane 依 `mode` / `overlay` 選 frame 後把 vbH 下傳。**`MarketChart.height` prop 無預設值**:intraday 分支 `height ?? 220`;candle 分支 `CandleChart height={height}` 透傳 undefined → CandleChart 自有 `DIMS.height`(578)。
- 騰落線:svg 外包固定高**恆存** wrapper `h-24 shrink-0 flex items-center justify-center`(空態文案也在其中,ref 掛此 wrapper)掛 useContainerSize;svg `className="h-full w-full"`(不再只 `w-full`);viewBox `0 0 640 H`,H = round(640 × h / w),量測不可用時 H = 150(舊值,fallback 由 preserveAspectRatio meet 縮放置中,不溢出)。`[auto-default: h-24 | reason: 1536×864 高度預算下騰落線 96px 仍讀得出多空側;寬決定高會吃掉 170-220px]`
- 家數帶:不改版面,只改停板桶配色(§5.5)。

### 4.2 高度預算(1536×864,Chrome 內容區 ≈ 760px;root font 16px,`index.css` 無 root font 覆寫)`[amendment r1: CS-15]`
nav+padding ≈ 80 → 主 grid ≈ 680:BasisRow 20 + gap 12 + **雙圖 ≈ 394** + gap 12 + 家數帶 ≈ 118 + gap 8 + 騰落線 116(20 標題 + 96)。雙圖內:標的列 28 + 週期列 28~56(折行)+ 兩個 gap 24 + figure chrome(border 2 + p 32 + caption 20 + mt-2 8 + toggle 列 26)= 88 → svg ≈ 198~226px;figure = svg + 88 ≈ 286~314 > min-h-60(240),地板不吃到 `[amendment r2: R2-9]`。1920×1080:root 同 16px,可用高多 ~216px → svg ≈ 410~440px(figure ≈ 500);寬 1548 → 左欄 ≈ 929,pane ≈ 458。

### 4.3 < 1050px 容器寬(SC-7)
主 grid 單欄 + `overflow-y-auto`(整頁捲,舊行為);雙圖 figure 因 `min-h-60` 至少 240px 高,量測仍有意義(量到 = min-h − chrome,內容依此設高 → 收斂)。左欄 < 700px 時雙圖再堆疊(W-12)。

## 5. Diff 級章節(逐檔;🔵 → 🔴 → 🟢 順序 commit)`[amendment 2026-08-16 r1: CS-4 全節重排]`

### 5.1 🔵 純註解 / 等價重構(行為零改動)
- `LimitListSection.tsx` 檔頭 :1-6 註解:改「恆掛台股綜合右欄;主 tab 以 hidden 保留 DOM 時靠 `active` gate 停輪詢」(subtab 語句移除)。
- `IndexPage.tsx` 檔頭 :1-12 註解:改寫為一頁總覽 + 兩欄說明(subtab 段落刪)。**與 LimitListSection 檔頭註解同一顆 🔵 commit(純註解 diff),不併入 🔴** `[amendment r2: R2-10]`。
- `docs/next-time.md:261-265`:改寫為不依賴單一樣板檔:「要修就抽 `@/lib/storage`(readKey/writeKey,讀寫兩側都包 try/catch),既有同型 try/catch(App.tsx::initialStockCode 的 setItem/removeItem、hooks/useChartToggles.ts::persist、LimitListSection::loadFilter/persistFilter)一併收斂」`[amendment r2: R2-12]`(CS-14;CorrSection 將於 5.2 刪除)。
- (無其他等價重構;subtab 退役是行為改動,見 5.2。)

### 5.2 🔴 subtab 退役 + 佈局 / 圖高 / 配色(先改既有測試紅 → 改實作綠)
**5.2a subtab 退役 + CorrSection 刪除**
- `IndexPage.tsx`:刪 `SUBTABS` / `SubTab` / `initialSubTab` / `useState(subtab)` / `selectSubtab` / tablist 區塊 / `CorrSection` import;`LimitListSection` 恆 render 於右欄,`active` 直傳。
- `lib/constants.ts`:刪 `INDEX_SUBTAB_KEY` 宣告;`ORPHAN_STORAGE_KEYS` 加 `"copycat-index-subtab"` + 註解(2026-08-16 subtab 機制退役,相關係數升頂層 tab)。
- `components/corr/CorrSection.tsx` + `CorrSection.test.tsx` + `CorrSection.lazy.test.tsx`:**刪除**(唯一 caller 消失;零 WS 鎖由 5.3 `App.corr-tab.test.tsx` 接手 —— 5.2 → 5.3 之間相關係數暫不可達,屬同一 PR 內的中間態,可接受)。
- `IndexPage.corr-lazy.test.tsx`:**刪除**。
- 測試 `IndexPage.test.tsx`:刪除整個「IndexPage subtab 列」describe(s1 / s2 / s2b / s2c / s3 / s4 / s5 / s5b / s6 / s7 十支)+ `subtabs()` / `subtab()` helper + CorrPage `vi.mock` + `INDEX_SUBTAB_KEY` import;(f2) 改「家數帶位於雙 pane 之後」(去 subtab 錨);新增 (l1) 無「台股綜合分頁」tablist 且 `limit-list` 恆在、(l2) `Storage.prototype.setItem` spy 不含 `copycat-index-subtab`。
- 測試 `App.test.tsx:447-462`:orphan 清單加 `copycat-index-subtab`;「活鍵」對照改 `copycat-limit-list-filter`。
**5.2b 佈局 / 圖高**
- `IndexPage.tsx`:§4.1 class(root / 主 grid `index-main-grid` / 左欄 / 右欄);測試新增 (y1) root 無 `overflow-y-auto`、主 grid 含 `overflow-y-auto` + `@[1050px]:grid-cols-`、(y2) DOM 序 `adl-chart` 在 `limit-list` 之前、(y3) 雙圖 grid class 含 `grid-cols-1` + `@[700px]:grid-cols-2`(取代舊 auto-fit;既有 (a) 只驗兩 pane 同屏仍綠)。
- `MarketPane.tsx`:§4.1(min-h-0 / figure / wrapper ref / `paneSvgHeight(size, frame)` + `PANE_FRAMES` 三態表 / `OverlayCard height`);`:358-360` 註解改寫。`paneSvgHeight` 放 MarketPane 檔內(export 供測試),**不動 `lib/chart-frame.ts::svgBox` / `CHART_FRAME`**(StockChart 契約)。
- `MarketChart.tsx`:新 optional prop `height?: number`(**viewBox 單位、無預設值**,JSDoc 寫明「caller 已扣 chrome、已反解;intraday 未給 → 220、candle 未給 → CandleChart 自有預設」`[amendment r2: R2-2]`);`IntradayChart` 用 `{width:640, height: height ?? 220}` 建 geometry、`LABEL_BOUNDS` 改函式 `labelBounds(height)`;svg viewBox 用該高;`CandleChart height={height}` 透傳(W-10)。
- `AdvanceDeclineChart.tsx`:§4.1 wrapper + useContainerSize;線 / 面積拆兩段(`clipPath` above/below zeroY;id = `safeIdToken(useId())` + `-above` / `-below`,`<defs>` 內宣告);testid `adl-line-up` / `adl-line-down` / `adl-area-up` / `adl-area-down`;**兩段線與兩塊面積恆 render**(可見範圍由 clip 決定,錨點不隨資料正負消失);`stroke-accent` 移除。
- `LimitListSection.tsx`:§4.1 容器 class + `limit-list-scroll` testid + th sticky。
**5.2c 配色**
- `BreadthBand.tsx`:BUCKETS 加 `labelTone` 欄;limit_up `{tone:"border-bull bg-bull", labelTone:"text-white", valueTone:"text-white"}`,limit_down 同 bear;label span 改 `cn("text-xs", b.labelTone ?? "text-ink-dim")`;BUCKETS jsdoc :22-23 與檔頭 :6-13 改寫(停板桶實心白字與個股期漲跌停燈同款;上漲 / 下跌無底色由字色承擔;「兩欄不同時有值」句刪)。
**測試判定(5.2 全體)**
- 該紅 → 改:`BreadthBand.test.tsx` (g)(o) → `text-white` 且不含 text-bull/text-bear;`AdvanceDeclineChart.test.tsx` (d)(e)(f)(經 `pointCount()` 與 points 斷言,helper 錨改 `adl-line-up`);`App.test.tsx` purge 測試;`IndexPage.test.tsx` subtab describe(刪)與 (f2)。
- 不紅但必改(避免 vacuous):`AdvanceDeclineChart.test.tsx` (h)(i) → `adl-line-up` 與 `adl-line-down` 皆 null。
- 新增:`AdvanceDeclineChart.test.tsx` (k)(l);`MarketChart.test.tsx` height prop 兩態;`MarketPane.test.tsx`(或新檔)fake ResizeObserver 量測 lock + 未 stub 對照;`IndexPage.test.tsx` (l1)(l2)(y1)(y2)(y3);`LimitListSection.test.tsx` 容器 / th sticky class lock(mutation 驗)。
- 不該紅:`AdvanceDeclineChart.test.tsx` (a)(b)(c)(g)(j);`LimitListSection.test.tsx` 既有;`MarketPane.test.tsx` / `MarketChart.test.tsx` 既有;`IndexPage.test.tsx` (a)-(d3)(c)-(c4)(f)(f3);`BreadthBand.test.tsx` (f)(l)(m)(n)(p)。

### 5.3 🟢 相關係數頂層 tab
- `App.tsx`:`type Tab` 加 `"corr"`;`initialTab()` 白名單加 corr(檔頭註解改寫:值域加回);`visited.corr = tab === "corr"`;nav 陣列尾加 `["corr","相關係數"]`;`hidden` 分支 `visited.corr ? <div hidden={tab!=="corr"} className={tab==="corr" ? "flex min-h-0 flex-1 flex-col" : ""}><Suspense fallback「載入中…」><CorrPage/></Suspense></div>`;`const CorrPage = lazy(...)`。`railCtx` 不動(落 none)。
  - `[auto-default: 首訪後 hidden 保留 DOM(WS 常駐),不 unmount | reason: 與其他三 lazy tab 同慣例、與 R1 前 corr 頂層 tab 行為逐字相同;subtab 時代的「切走即斷線」是因台股綜合是預設落地頁而做的特例,頂層 tab 是主動點進去的]`
- `CorrPage.tsx` 檔頭註解:改回「頂層相關係數 tab 的 lazy body」。
- 測試(該紅 → 改 / 新):`App.test.tsx:152-165` describe 改為「corr 升回頂層(R2)」:舊值 corr → 還原到相關係數;nav **有**相關係數且在最後;`:287-296` 5 顆順序;`:356-363` nav 5 顆;新檔 `App.corr-tab.test.tsx`(接手 IndexPage.corr-lazy 語意;不 mock CorrPage):`corrWs = () => FakeWS.instances.filter(w => /\/ws\/(corr|river)$/.test(w.url))`;未點相關係數 → `corrWs().length === 0`;點後 → 長度 2 且 `findByText("等待六腿資料…")`(**錨點只用此句;不得以「載入中…」有無做反向斷言** — App Suspense fallback 與 CorrPanel 空態同字 `[amendment r2: R2-7]`);切回台股綜合 → 兩條 `closed === false`(hidden 保留)。

## 6. 新測試清單
1. `IndexPage.test.tsx` (l1)(l2)(y1)(y2)(y3)。
2. `MarketChart.test.tsx`「height prop → svg viewBox 高」(intraday + candle 兩態)。
3. `MarketPane.test.tsx`(或 `MarketPane.size.test.tsx`)fake ResizeObserver 量測 lock + 未 stub 對照。
4. `AdvanceDeclineChart.test.tsx` (k)(l) + 換錨 + (h)(i) 改寫。
5. `BreadthBand.test.tsx` (g)(o) 改寫。
6. `App.test.tsx` 三處改寫 + purge;`App.corr-tab.test.tsx` 新檔。
7. `LimitListSection.test.tsx` `limit-list-scroll` 容器 `overflow-auto`+`min-h-0`(message 態與 rows 態各一)與 th `sticky`(帶 rows fixture)class lock(mutation 驗)。

## 7. Edge cases `[amendment r1: CS-6 / CS-15]`
1. 量測不可用(jsdom / 舊瀏覽器無 ResizeObserver / 首幀)→ 圖表退回固定 SIZE,不白屏、不溢出(W-10)。
2. 極矮視窗(內容高 < ~600px):圖高有地板(renderPx ≥ 96;figure min-h-60),左欄超出時由主 grid 的單一 `overflow-y-auto` 接住(§4.1 已採此結論;正常尺寸內容恰填滿不出捲軸)。
3. 舊 `copycat-tab=corr` 殘值 → 開站直達相關係數 tab(D7 預期)。
4. 週期列在窄 pane 折成 2-3 行 → 圖高自動吸收(量測在 figure 內)。
5. breadth 為 null / FinMind 未設 → 家數帶「載入中 / 未設定」單行(該塊變矮);騰落線 wrapper 固定 h-24 顯佔位文案;雙圖吃剩餘高(不空白、不捲)。
6. 漲跌停列表 0 列 / 載入中 → 右欄框內只有篩選列 + 文案,不影響左欄。
7. `copycat-index-subtab` 殘值 `corr` → 被 purge,不會讓任何東西掛載 corr(subtab 已無)。
8. 開著「重疊」的使用者(localStorage `copycat-index-mode=overlay`)→ OverlayCard 走 overlay chrome(62)不溢出。

## 8. Out of scope
- 列表虛擬捲動 / 欄寬固定;家數帶 up/down 配色(D8 不動);騰落線改用 breadth 以外資料源;
  MarketPane localStorage try/catch(next-time 既有條);tablist ARIA roving(next-time 既有條);
  相關係數頁自身版面;RightRail 對 corr 顯示閃電(維持 none)。
- 主 grid 斷點以外的響應式細調(手機版面本專案不做)。

## 9. 執行約束(延續前輪 user 指示)
- 前端不加 emoji / 不加新色 token / UI 文字繁中。
- 三類 commit 順序 🔵 5.1 → 🔴 5.2 → 🟢 5.3;🔴 先讓既有測試紅(`[red]`)再改實作(`[green]`)。
- 截圖用 claude-in-chrome 既有 session(memory `ui-testing-claude-in-chrome`)。

## Amendment r3(2026-08-16,Phase 6 real-env finding:截圖 SC-4/SC-7 FAIL)`[amendment 2026-08-16 r3: real-env]`
**根因**:左欄鏈 `min-h-0` 一路到雙圖 grid → 可用高不足時 pane 被壓到低於自身內容,`overflow: visible` 讓圖卡溢出壓在家數帶上,而主 grid 的 `scrollHeight` 恆 = `clientHeight`,§7 edge 2 的逃生口永遠不啟動(1280 單欄 / 1440 兩欄 / 1536×664 皆現形;1920×1080 與 1536×864 正常)。figure `min-h-60` 只是 pane 內一段的地板,pane / 雙圖 grid 本身沒有地板。
**修法**(取代 §4.1 對應句;含 code review WL-1 單欄態根因:主 grid 兩條 auto 列把自由空間**等分**給 min-h-0 的左右欄,列高與內容無關):
- 主 grid:單欄態改 **flex-col**、兩欄態才 grid:`flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto @[1050px]:grid @[1050px]:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]`;左欄 / MarketPane root 的 `min-h-0` 條件化為 `@[1050px]:min-h-0`(單欄態讓內容決定高 → overflow-y-auto 真的捲成舊行為;右欄框同樣 `@[1050px]:min-h-0`)。
- 雙圖 grid:`grid grid-cols-1 gap-3 flex-1 min-h-80 @[640px]:grid-cols-2`(**去 `min-h-0`,改顯式地板 20rem** = 標的列 28 + 週期列折 2 行 56 + gap 24 + figure 192;斷點 700 → 640:1440×900 兩欄態左欄 655px 也並排,不落入「兩圖直排 + 捲動」)。
- MarketPane figure:`min-h-48 flex-1`(12rem;wrapper 130 → svg render 102 ≥ 96 地板);pane root 維持 `min-h-0`(grid item 可縮到軌高;軌高由 grid 的顯式 min-h 保底)。
- 逃生口語意不變:雙圖 grid 到地板後左欄內容 > 主 grid 高 → 主 grid `overflow-y-auto` 出捲軸(左欄 grid item `min-h-0` 讓內容溢出到主 grid 可捲區)。
- **SC-4 改寫**:1536×864 下把 innerHeight 縮 **60px** → 圖跟著矮、頁面仍不捲(量測 (1)(2));縮 200px → 進入逃生口:**主 grid 可捲(scrollHeight > clientHeight)、圖卡與家數帶不重疊**(截圖 `SC-4-short.png` 改為此判準)。原「縮 200 仍不捲」與地板互斥,屬 SC 寫法錯誤(失敗四分流 (4) goal 互斥 → 改寫 SC;rollback 記 progress.md)。
- **SC-7 1280**:單欄且**整頁可捲**(主 grid scrollHeight > clientHeight)、圖卡不與家數帶重疊。
- vitest lock:IndexPage (y3) 改斷雙圖 grid 含 `min-h-80` + `@[640px]:grid-cols-2` 且不含 `min-h-0`;MarketPane.size.test 斷 figure 含 `min-h-48` 不含 `min-h-0`。
- 順手(截圖觀察,P2 → 一併修):th 與狀態徽章加 `whitespace-nowrap`(1536 寬右欄 475px 表頭折行 / 徽章直排截字);仍可能出現水平捲軸,列 next-time 觀察。

## Known Risks
- KR-1 5.2 → 5.3 之間相關係數暫不可達(同 PR 內中間態)。
- KR-2 `frontend-testing/SKILL.md:15` 引用的 `MarketColdLoad.test.tsx` 在本 repo 不存在(neigui 遺留),收尾沉澱時修正該 skill 條目(同批修 TD-3 的 CorrSection 樣板引用)。
- KR-3(code review WL-3 partial)K 線態在窄 pane 下 CandleChart 文字 ≈ 2.2–3.9px 不可讀:CandleChart 是共用元件(vbW 1400 寫死),改版前 pane 也已 3.9px,本輪只補 intraday / overlay 的 unitScale 字級補償;CandleChart 補償列 next-time。

---
self_review_head: 5a111c68(自評 round 1 → fix 波 16 commits 由 main session 機械快篩 + 截圖補驗;收尾 C 節增量為空則不重跑)
