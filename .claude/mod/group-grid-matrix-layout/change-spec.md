# Change Spec — 群組圖牆矩陣佈局(mod/group-grid-matrix-layout)

分流判定:**已成形**(user backlog 拍板文件,指名落點檔案 + 矩陣規則 + pill 樣式對齊對象;
無方向性抉擇,依 auto.md 預核准條件走,細節以 `[auto-default]` 記錄)。
[amendment 2026-08-14: spec review P1-4 駁回佐證 — SC-1 的 per-n 對照表
「≤4:2×2、≤6:3×2、≤9:3×3、≤12:4×3、≤16:4×4,不足留空格;>16 檔維持 4 欄往下加列
並允許捲動」為本次 user 需求**原文逐字**(2026-08-14 session 首則訊息第 (1) 點),
非 spec 推導;memory 條目只是摘要。]

## 成功條件

- **SC-1 矩陣佈局**:群組檢視格線依當前群組檔數 n 選最小可容納矩陣 —
  n≤4:2×2、n≤6:3×2、n≤9:3×3、n≤12:4×3、n≤16:4×4(不足留空格,卡片從左上
  依序填);n>16:固定 4 欄、列高維持基準(圖 80px 起)、格線內垂直捲動。
  - 驗證:vitest — 純函式 `gridShape(n)` 邊界值全表斷言(0,1,4,5,6,7,9,10,12,13,16,17;
    n=0 回傳與 n≤4 同 — 元件層由空群組空態擋住不會呼叫,函式仍須有定義行為,
    [amendment 2026-08-14: P2-2]);元件級斷言 grid 容器 className 含對應
    `grid-cols-*` / `grid-template-rows` 任意值且不含 auto-fill。
  - 畫面可指認:2 檔群組 → 中區呈 2 欄,兩張卡片各佔約半寬、上下兩列各佔約半高
    (下列為空);17 檔群組 → 4 欄多列、右側出捲軸
    [amendment 2026-08-14: P2-4 — 17 檔取得方式:自選臨時建一個 17 檔群組 →
    截圖 → 隨即刪除(watchlist PUT 可逆,收尾核對已刪);休市日 mock/舊快照亦可]。
- **SC-2 卡片高度均分佔滿中區**:n≤16 時 grid 佔滿 main 剩餘高度(不捲動),列高均分,
  mini 圖(與「回補中…/無資料」佔位)吃卡片標題列以外的剩餘高度;n>16 維持
  現行基準高(圖 80px)往下捲。
  [amendment 2026-08-14: P1-3 — 高度機制統一為「**保留 `h-20` 並加 `grow`**」:
  `grow` = flex-grow:1、flex-basis auto → 以 height 80px 為基準,矩陣模式(格高固定)
  下長高吃滿剩餘,捲動模式(列高 auto)下維持 80px;h-20 由唯一高度來源**降為基準高**,
  不移除。先前「flex-1 / flex-basis 80px」措辭錯誤(flex-1 的 basis 是 0%),廢棄。]
  [amendment 2026-08-14: P1-5 — 卡片變高後 y 向縮放 ~3×,`preserveAspectRatio="none"`
  原註解「尺度差 <5% 線寬失真不可見」被證偽:polyline / ref line 加
  `vectorEffect="non-scaling-stroke"(React SVG camelCase prop,DOM 屬性 vector-effect)`(線寬固定螢幕像素,幾何函式零觸碰),
  並同步更新 MiniIntradayChart.tsx:100-102 過時註解;y 向斜率視覺放大是「圖吃滿卡片」
  的本意,接受。]
  - 驗證:vitest — grid 容器 className 含 `flex-1`;svg(以 `getAttribute("class")` 取,
    SVG 的 className 是 SVGAnimatedString,[amendment 2026-08-14: P2-1])與佔位 class
    含 `grow` 且仍含 `h-20`;svg polyline 帶 `vector-effect`;MiniIntradayChart 幾何測試
    (viewBox/points)不變。
  - 畫面可指認:4 檔群組時卡片高 ≈ 中區高的一半(圖明顯高於現行 80px),無警示條時
    頁面無捲軸([amendment 2026-08-14: P2-4 — TC4 down / WS closed 警示條出現時
    main 多一列,不在此 SC 保證範圍]);線寬不隨卡片變高而變粗。
- **SC-3 群組切換 pill**:`<select>` 移除,改為「群組」前置字 + 一排 pill 按鈕(每群組
  一顆,flex-wrap 可換行);樣式對齊 StockPage view pills(`rounded border px-2 py-0.5
  text-xs`,選中 `border-accent text-accent`,未選 `border-line text-ink-dim
  hover:text-ink`,`aria-pressed`);點擊切換群組並寫入 localStorage `STOCK_GROUP_KEY`。
  [amendment 2026-08-14: P0-1/P1-1 — pill 列容器保留 `role="group"` +
  `aria-label="選擇群組"` 作為**刻意保留的可及名稱契約**:StockPage.test.tsx:671/713
  (`queryByLabelText("選擇群組")).toBeNull()` 鎖「單檔檢視不渲染群組檢視」)與
  :746/750(`getByLabelText` 鎖「重掛後還原群組檢視」)四處斷言全數續有效且不 vacuous,
  StockPage.test.tsx 因此**維持不該紅**。]
  - 驗證:vitest — 改寫「群組下拉」4 條測試為 pill 語意(預設第一組選中 /
    點 pill 改打新群組 codes / 記住的群組被刪 fallback 第一組 / 記住的群組仍在則沿用)。
  - 畫面可指認:格線上方一排小圓角框按鈕,各印群組名,當前群組亮 accent 邊框字色;
    與 main 頂部「單檔/群組」pill 同視覺語彙。

驗證窗口:vitest 無窗口;畫面截圖休市日也可驗(佈局不依賴盤中資料,mock/舊快照即可),
盤中活數據截圖為加分非必要。

## 不能破壞的既有行為白名單

1. 空態三分文案:`載入群組…` / `自選載入失敗` / `尚無群組 — 到自選欄建立群組`;
   有 cache 時 wlError 不遮卡片。
2. `這個群組還沒有成員` 空群組態;isPending 首載不畫卡片(`載入群組…`);
   零群組 / 空群組 → **不打 `/api/stock/group-state`(零請求,R17 gate)**
   [amendment 2026-08-14: P2-5]。
3. 卡片三態優先序:回補中(且無分鐘資料)→ 無資料 → 常態圖;batch 整批失敗全卡「無資料」。
4. QuoteCell:p+chg%(紅漲綠跌)/ ref+「參考」中性 / 全缺整格 `-`。
5. 現價延伸接線:`quotes[code].p` 餵 `MiniIntradayChart.liveP`,盤中多一個延伸點。
6. 點卡片 = button + aria-label `查看 <code> <name>`,回呼 onPick。
7. localStorage `STOCK_GROUP_KEY`:同 key 同值;記住的群組被刪 fallback 第一組;
   仍在則沿用(SC-3 內以 pill 語意重驗)。
   [amendment 2026-08-14: code review A-3 — **寫入時機刻意改變**:舊 select 的 change
   事件在 value 未變時不發火,stale 舊名永留;pill click 無條件回寫 = stale-key 清理,
   方向為改善,已補 lock 測試釘住新語意(點已選中 pill → localStorage 回寫)。]
8. GroupCard memo 化(每秒 quotes 更新只重畫變動卡片)— `GroupGridView.memo.test.tsx` 不該紅。
9. `MiniIntradayChart` 幾何:viewBox / 延伸 / 紅綠切半語意 — `MiniIntradayChart.test.tsx`
   幾何節不該紅。
10. StockPage 的「單檔/群組」view pill 與其餘 main 內容零觸碰。

## Backward compat / migration

無:props 介面不變、localStorage key/值不變、無 API 變更。migration 可逆性:N/A。

## Edge cases(≥3)

1. n=1:仍 2×2,右格與下列留空(依拍板「不足留空格」,不特化)。
2. localStorage 記住的群組已被刪:pill fallback 第一組亮起(既有行為,改寫測試沿用)。
3. n=17+:4 欄捲動,卡片不被壓扁 —— 圖高有 80px flex-basis 底。
4. 群組數量多:pill 列 flex-wrap 換行,不橫向溢出。
5. 視窗過矮 + 16 檔:[amendment 2026-08-14: P1-2 — 原「min-height:auto 自然出捲軸」
   機制描述錯誤:Tailwind `grid-rows-N` = `repeat(N,minmax(0,1fr))`,列軌可壓到低於
   內容,item 溢軌會與下一列**重疊**而非乾淨捲動。改為矩陣模式列軌帶下限的靜態任意值
   class `[grid-template-rows:repeat(N,minmax(8rem,1fr))]`(8rem ≈ 標題列 + 圖 80px +
   padding),過矮視窗時 grid 內容高 > 容器高 → `overflow-y-auto` 真捲軸降級],
   不硬性保證「任何高度都不捲」。
6. 窄視窗:固定 4 欄後失去 auto-fill 的「卡片 ≥15rem」保底,卡片可能窄於 15rem ——
   name 已 `truncate`、svg `w-full` 非等比拉伸,接受([auto-default] 見下)
   [amendment 2026-08-14: P2-3]。

## Out of scope

- 卡片內容(標題列 / QuoteCell / 三態)與 MiniIntradayChart 幾何、y 域、紅綠語意。
- StockPage 的 view pill、mobile 特化佈局(矩陣規則不分裝置)。
- 自選欄 / 訊號欄 / 單檔檢視。
- 卡片排序、群組管理功能。

## 執行約束(前輪慣例掃描)

- group-grid 前輪 design 慣例:卡片只留代碼/名稱/現價/一條分時線(頂部註解)— 不動。
- `frontend-conventions`:新 class 禁 px-literal 字級(本輪只動 layout class,無新字級);
  `cn()` 拼 class;UI 文字繁中;jsdom 測試 pragma 既有。
- Tailwind JIT:矩陣 class 必須是**靜態字串字面值**(lookup 函式回傳字面值,不得模板拼接
  `grid-cols-${n}`)。

## Diff 級變更(三類標記)

### `frontend/src/components/stock/GroupGridView.tsx`

- 🔴 `gridShape(n): string` 純函式(module scope,export 供測試):回傳靜態 class
  字面值 —— n≤4:`"grid-cols-2 [grid-template-rows:repeat(2,minmax(8rem,1fr))]"`、
  n≤6:`"grid-cols-3 [grid-template-rows:repeat(2,minmax(8rem,1fr))]"`、
  n≤9:`"grid-cols-3 [grid-template-rows:repeat(3,minmax(8rem,1fr))]"`、
  n≤12:`"grid-cols-4 [grid-template-rows:repeat(3,minmax(8rem,1fr))]"`、
  n≤16:`"grid-cols-4 [grid-template-rows:repeat(4,minmax(8rem,1fr))]"`、
  n>16:`"grid-cols-4"`(列高 auto,無 rows)[amendment 2026-08-14: P1-2]。
- 🔴 格線容器(現 194 行):`grid-cols-[repeat(auto-fill,minmax(15rem,1fr))]` →
  `cn("grid min-h-0 flex-1 gap-2 overflow-y-auto", gridShape(codes.length))`。
- 🔴 佔位 span(118/120 行):`h-20` → `h-20 grow`(兩處)[amendment 2026-08-14: P1-3]。
- 🔴 群組切換(162-178 行):`<select>` 整段換 pill 列(「群組」前置字保留;容器
  `role="group" aria-label="選擇群組"` [amendment 2026-08-14: P0-1];button
  `aria-pressed`、onClick = setPicked + persistGroupName;樣式同 SC-3)。
  同步改寫 160-161 行既有註解(原「不用 label 包」取捨已不符新結構):說明 aria-label
  掛在 role=group 容器(非表單控制項,不觸 label-in-name),且為 StockPage 四處既有
  斷言的可及名稱契約 [amendment 2026-08-14: R2 P2-9]。

### `frontend/src/components/stock/MiniIntradayChart.tsx`

- 🔴 svg className(106 行):`block h-20 w-full` → `block h-20 w-full grow`
  (基準 80px、矩陣模式下長高;其餘不動)[amendment 2026-08-14: P1-3]。
- 🔴 polyline(價線 × 3 分支)與 ref line 加 `vectorEffect="non-scaling-stroke"(React SVG camelCase prop,DOM 屬性 vector-effect)`;
  更新 100-102 行「尺度差 <5%」過時註解 [amendment 2026-08-14: P1-5]。

### `frontend/src/components/stock/GroupGridView.test.tsx`

- 🔴 「群組下拉」describe 4 條:select 語意 → pill 語意(**先改紅再實作**,
  鐵則 E 合法通道);describe 更名「群組切換 pill」。
- 🔴 新增:矩陣 mapping 測試(gridShape 全表 + 元件級 grid class 斷言,先紅)。
- 🔴 新增:高度 class 測試(grid flex-1 / 佔位與 svg `grow`+`h-20`(svg 用
  `getAttribute("class")`)/ polyline `vector-effect`,先紅)。

### 既有測試紅名單

- 該紅:`GroupGridView.test.tsx` 122-156(select 4 條,cast HTMLSelectElement +
  fireEvent.change 語意必改)。
- 不該紅:其餘全部(含 memo / MiniIntradayChart / **StockPage** — 其 671/713/746/750
  四處 `ByLabelText("選擇群組")` 斷言由 pill 列容器的 `role="group" aria-label`
  接住,續綠且不 vacuous [amendment 2026-08-14: P0-1/P1-1])。

## `[auto-default]` 清單

- [auto-default: 「群組」前置字保留於 pill 列左側 | reason: 與相鄰「單檔/群組」view pill
  列並排出現,無前置字兩排 pill 語意混淆]
- [auto-default: n>16 的列高 = 現行基準(圖 80px flex-basis)而非 auto-rows-fr |
  reason: 拍板文字「維持 4 欄往下加列並允許捲動」,對齊現行捲動視覺]
- [auto-default: mini 圖吃高用純 CSS(svg preserveAspectRatio="none" 非等比拉伸 +
  `grow`,flex-basis auto = h-20 為基準高),不引入 useContainerSize;另加
  vectorEffect="non-scaling-stroke" 抵銷非等比拉伸的線寬失真(P1-5)| reason:
  svg 本就固定 viewBox 拉伸渲染,「外層 flex 決定高」契約自動成立,零 hook、
  幾何計算零變更(R2 P2-6 修訂,廢 flex-1 措辭)]
- [auto-default: 過矮視窗降級 = 外層捲軸(edge 5,列軌下限 8rem)| reason:
  「≤16 不捲動」以合理視窗為前提,壓到 0 高 / 卡片重疊比捲軸更糟]
- [auto-default: 窄視窗接受卡片窄於 15rem(edge 6)| reason: 本工具為桌面看盤場景,
  固定矩陣是拍板本體;name truncate + svg 非等比拉伸已有degradation,responsive
  降欄會破壞「同群同屏」目的]
- [auto-default: pill 列容器保留 role="group" aria-label="選擇群組" | reason:
  select 移除後不失可及名稱,且 StockPage 四處既有斷言續有效(P0-1 修法 (b))]

---
self_review_head: c43c2532(code-review round 1:A/B 雙 lens,P1×2 P2×6 全處置,fix 波 5d5fed19/84ab013d/c43c2532)

