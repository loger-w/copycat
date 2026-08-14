# 現況盤點 — 群組圖牆矩陣佈局(mod/group-grid-matrix-layout)

Scope 判定:**M**(code 2 檔 + 測試 2 檔;無對外 API、無 migration)。

## Caller map(grep 全查,含動態用法)

| 符號 | 定義處 | Caller | 動態用法 |
|---|---|---|---|
| `GroupGridView` | `frontend/src/components/stock/GroupGridView.tsx` | `StockPage.tsx:213`(唯一)+ 自身兩支測試 + **StockPage.test.tsx 671/713/746/750 經 `ByLabelText("選擇群組")` 間接綁 select**(spec review P0-1 補)| 無 |
| `MiniIntradayChart` | `frontend/src/components/stock/MiniIntradayChart.tsx` | `GroupGridView.tsx:122`(唯一)+ `MiniIntradayChart.test.tsx` | 無 |
| `MINI_W` / `MINI_H` / `extendMinutes` | 同上 | 僅 `MiniIntradayChart.test.tsx` | 無 |
| `STOCK_GROUP_KEY` | `lib/constants.ts:109` | GroupGridView(讀寫)+ GroupGridView.test.tsx | 無 |

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 格線 | `GroupGridView.tsx:194`:`grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-2 overflow-y-auto`,欄數由容器寬 ÷ 15rem 決定,列高 = 內容高 | 依檔數選最小可容納矩陣:≤4:2×2、≤6:3×2、≤9:3×3、≤12:4×3、≤16:4×4(不足留空格);>16:4 欄自然列高 + 捲動 |
| 格線高度 | grid 無 `flex-1`,高度 = 內容,靠 flex shrink 被容器截斷後內捲 | ≤16 檔:grid `flex-1` 佔滿 main 剩餘高,列軌 `[grid-template-rows:repeat(N,minmax(8rem,1fr))]`(靜態字面值,下限擋壓縮重疊)均分列高,不捲動(過矮視窗降級為真捲軸)[R2 P1-6 同步] |
| mini 圖高 | `MiniIntradayChart.tsx:106`:svg `block h-20 w-full` 固定 80px;佔位(回補中/無資料)也 `h-20`(GroupGridView.tsx:118,120) | 圖與佔位改 `h-20 grow`(flex-basis auto → 80px 為基準高):矩陣模式吃卡片剩餘高;>16 捲動模式維持 80px [R2 P1-6 同步] |
| 群組切換 | `GroupGridView.tsx:164-178`:`<select aria-label="選擇群組">` | 一排 pill 按鈕,樣式對齊 StockPage view pills(`StockPage.tsx:193-207`:`rounded border px-2 py-0.5 text-xs`,選中 `border-accent text-accent`,未選 `border-line text-ink-dim hover:text-ink`,`aria-pressed`) |

## 關鍵既有機制(不動)

- `MiniIntradayChart` svg 固定 viewBox(`Y_AXIS_W 0 MINI_W MINI_H`)+ `preserveAspectRatio="none"` 非等比拉伸 → **改吃剩餘高度不需 useContainerSize**;「外層 flex 決定容器高」契約(StockChart.tsx:117-119)自動成立。除 className 外另加 `vectorEffect="non-scaling-stroke"` 表現屬性(P1-5,抵銷變高後線寬失真),幾何**計算**(buildIntradayGeometry / viewBox / points)仍零觸碰 [R2 P1-6 同步]。
- `selected` 派生規則(localStorage picked → 找不到 fallback `groups[0]`)、`persistGroupName`、卡片三態、QuoteCell、現價延伸接線、memo 化 — 全保留。
- StockPage `<main>` 是 `flex flex-col overflow-y-auto`,GroupGridView 已是 `flex-1 min-h-0 flex-col` → 佔滿 main 的前提已在。

## 既有測試影響

- `GroupGridView.test.tsx` 「群組下拉」describe(4 條,122-156 行)綁 `getByLabelText("選擇群組")` + HTMLSelectElement → **該紅**,改寫為 pill 語意(aria-pressed / click)。
- 其餘 GroupGridView 測試(空態三分 / 卡片三態 / 價格 / 延伸接線 / 點卡片)不綁 select 與 layout class → **不該紅**。
- `StockPage.test.tsx` 671/713/746/750(`ByLabelText("選擇群組")`)由 pill 列容器 `role="group"` + `aria-label` 接住 → **不該紅**(spec P0-1 修法 (b))[R2 P1-6 同步]。
- `GroupGridView.memo.test.tsx`、`MiniIntradayChart.test.tsx` 不綁 `h-20` / grid class → **不該紅**。

## Backward compat

- localStorage `STOCK_GROUP_KEY` 讀寫語意不變(同 key、同值 = 群組名),無 migration。
- 無對外 API / props 變更(GroupGridView Props 不動)。
