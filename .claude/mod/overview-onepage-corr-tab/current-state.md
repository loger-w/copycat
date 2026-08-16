# current-state:台股綜合一頁總覽 + 相關係數升頂層 tab + 家數帶停板實心色

> /mod Phase 1 產物(2026-08-16)。來源 prompt:`docs/superpowers/specs/2026-08-15-user-feedback-batch2-rounds.md` §2 R2;
> 拍板 D6(A + 騰落線紅綠)/ D7(相關係數放最後一顆)/ D8(up/down 桶字色不動)。
> 前置 R1(mod/remove-sector-timeline,PR #54)已 merge:subtab 只剩 limit / corr。

## 1. 現況(逐檔;行號 = 分支起點 `e18f61c5`)

### 1.1 頂層 tab — `frontend/src/App.tsx`
| 位置 | 現況 |
|---|---|
| :35 `type Tab = "txo" \| "stock" \| "futures" \| "index"` | 無 corr |
| :44-52 `initialTab()` | 白名單 stock/futures/txo,其餘(含舊值 `corr`)fallback `index`;檔頭註解載明 corr 於 R1 移出 |
| :99-104 `visited` | index/txo 恆 true、stock/futures 首訪才 mount(lazy) |
| :198-204 nav 陣列 | `index / stock / txo / futures` |
| :230-293 各 tab `hidden` 分支 | txo 直 render;stock/futures/index 走 `visited` + Suspense;index 收 `active={tab==="index"}` |
| :177-193 `railCtx` | stock/futures 有標的;其餘 `{kind:"none"}`(RightRail 顯「此頁無可下單標的」) |
| 歷史 | R1 前(commit `0d22f78a`)corr 是頂層 tab:`visited.corr` + `hidden` + `lazy(CorrPage)`,即 **首訪後 DOM 保留、WS 常駐** |

### 1.2 台股綜合頁 — `frontend/src/components/index/IndexPage.tsx`(222 行)
| 位置 | 現況 |
|---|---|
| :36-56 `SUBTABS` = limit/corr、`initialSubTab()` 讀 `INDEX_SUBTAB_KEY`(try/catch) | subtab 機制 |
| :137-146 `useState(subtab)` + `selectSubtab` 寫 localStorage | |
| :149 root `flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto` | **整頁捲動**,無單螢幕約束 |
| :150 `<BasisRow>` | 白名單 |
| :152-175 雙圖 `grid gap-3 grid-cols-[repeat(auto-fit,minmax(480px,1fr))]` | 寬 ≥ 960 才並排 |
| :178-181 `<section>` 家數帶 + 騰落線 | |
| :185-217 subtab 容器(`role=tablist` aria-label「台股綜合分頁」)+ 條件 render `LimitListSection` / `CorrSection` | `active` 直接下傳 LimitListSection |
| 檔頭 :1-12 註解 | 描述 subtab 掛載閘語意 |

### 1.3 相關係數 — `frontend/src/components/corr/`
- `CorrSection.tsx`(25 行):subtab panel 殼 = `px-4 pt-2 pb-4` + `lazy(CorrPage)` + Suspense fallback「相關係數載入中…」。**唯一 caller = IndexPage.tsx:15,216**。
- `CorrPage.tsx`(21 行):`useCorrelation` + `useRiver` 兩條 WS 在此建立;root `flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto`(RiverPanel + CorrPanel)。**可獨立掛頂層**(R1 前就是這樣掛的)。檔頭註解寫「CorrSection 收合區塊的 lazy body」→ 要改。
- 測試:`CorrSection.test.tsx`(殼 mount/unmount 計數 ×2)、`CorrSection.lazy.test.tsx`(真身建線 + unmount 斷線 ×2)、`CorrPage.test.tsx`(×2,不動)。

### 1.4 圖高 — `MarketPane.tsx` / `MarketChart.tsx`
- `MarketPane.tsx:21` `SIZE = 640×220` 固定 viewBox;`:358-360` 註解「不 flex-1 撐滿頁高」;figure `flex flex-col rounded-md border border-line bg-surface p-4`;`:109` `OverlayCard` 亦用 SIZE。pane root `:318` `flex min-w-0 flex-col gap-3`(無 min-h-0)。
- `MarketChart.tsx:28` `SIZE = 640×220`;`:69` `LABEL_BOUNDS` 依 SIZE.height;`:93` `buildIndexGeometry(input, SIZE)`(lib 已收 size 參數);`:128` toggle 列 `h-[1.375rem] mb-1`(26px);`:148-149` svg `viewBox` + `className="w-full"`(高度 = 寬 × 220/640);`:321` `CandleChart`(**已支援 `height` viewBox prop**,StockChart 已在用)+ `:329` meta 列 `mt-1 text-xs`。
- 既有可複用機制:`hooks/useContainerSize.ts`(callback ref、jsdom 回 0×0)、`lib/chart-frame.ts::svgBox()`(wrapper 尺寸 → viewBox 高;`CHART_FRAME` 常數是 StockChart figure 專用,MarketPane figure 的 chrome 不同)。樣板:`components/stock/StockChart.tsx:118-186`。
- 量測 lock 樣板:**本 repo 無**(`frontend-testing` skill :15 引用的 `MarketColdLoad.test.tsx` 是 neigui 遺留);`hooks/useContainerSize.test.tsx` 只鎖 jsdom fallback。要鎖量測態需 fake ResizeObserver(observe 時同步 callback 餵 contentRect)。[r1: CS-5]

### 1.5 家數帶 — `BreadthBand.tsx`
- `:23-34` BUCKETS:limit_up tone `border-bull/40 bg-bull/15`、limit_down `border-bear/40 bg-bear/15`,valueTone null(數字 `text-ink`);label `text-ink-dim`。檔頭 `:6-13`「染色與底色互斥」註解。
- 個股期實心樣板:`WatchlistSidebar.tsx:405-406` / `StockPage.tsx:276-277` = `rounded bg-bull px-1.5 text-white` / `bg-bear ... text-white`。
- 測試 `BreadthBand.test.tsx`:(f) 停板格含 bg-bull/bg-bear(仍成立);**(g) 漲停數字含 `text-ink`、(o) 跌停數字含 `text-ink`(該紅)**;(l)(m)(n)(p) up/down/flat 字色與無底色(不動)。

### 1.6 騰落線 — `AdvanceDeclineChart.tsx`(151 行)
- `:17` `SIZE = 640×150` 固定 viewBox,svg `w-full`(高 = 寬 × 150/640;左欄 930px 寬時 218px);`:131` 單條 `polyline.stroke-accent`;無面積填色;`:98-101` `toY` 對稱域、`zeroY`。
- 分時圖同款填色手法:`StockIntradayChart.tsx:201-211` 兩個 `clipPath`(refY 上下)+ `:306-319` `areaPolygon` 兩份分別 `fill-bull/fill-bear fillOpacity 0.15` + `:349-367` 主線兩份 `stroke-bull/stroke-bear` 各 clip。
- 測試 `AdvanceDeclineChart.test.tsx`:(b) 末值染色、(f) 以 `adl-line` 的 points 驗固定域、(h)(i) 無 `adl-line`、(g) `adl-zero`。**沒有斷言 stroke-accent**;但 `adl-line` 單一 testid 會因拆兩段而需重定義(該紅:見 change-spec)。

### 1.7 漲跌停列表 — `LimitListSection.tsx`(495 行)
- `:479-493` `LimitListSection` 殼 `pt-2` → `LimitListBody`;body root `:335` `flex flex-col gap-2 px-4 pb-4`;`:389` 表格容器 `overflow-x-auto`(**無 max-h / 無內捲**);`active` prop 是輪詢 gate(:121-126 說明)。
- 檔頭 :1-6 註解「非 active subtab = unmount」→ 要改(改版後恆掛載於右欄,unmount 只剩主 tab hidden 不算)。

### 1.8 localStorage — `lib/constants.ts`
- `:30-37` `ORPHAN_STORAGE_KEYS`(6 支)+ `purgeOrphanKeys()`;`:76-86` `INDEX_SUBTAB_KEY = "copycat-index-subtab"`(caller:IndexPage.tsx ×3、IndexPage.test.tsx)。
- 測試 `App.test.tsx:447-462`:purge 六支 + **「新鍵是活的」用 `copycat-index-subtab` 當對照(該紅)**。

### 1.9 既有測試盤點(直接受影響)
| 檔 | 測試 | 判定 |
|---|---|---|
| App.test.tsx:152-165「台股綜合 tab 整併」 | 舊值 corr → 落台股綜合;nav 無相關係數 | **該紅**(語意反轉) |
| App.test.tsx:287-296 | nav 順序 4 顆 | **該紅**(5 顆,corr 最後) |
| App.test.tsx:356-363 | nav 4 顆 / 右欄 3 顆 | **該紅**(nav 5) |
| App.test.tsx:447-462 | purge + 對照鍵 `copycat-index-subtab` | **該紅**(該鍵入 orphan) |
| App.test.tsx 其餘(index 預設頁、active gate、跳轉)| — | 不該紅 |
| IndexPage.test.tsx (f2)、(s1)-(s7)、`subtabs()` helper、`INDEX_SUBTAB_KEY` import、CorrPage vi.mock | subtab 列 | **該紅 / 刪除**(subtab 機制退役) |
| IndexPage.test.tsx (a)(b)(b2)(d)(d2)(d3)(c)-(c4)(f)(f3) | 雙 pane / 基差 / 家數帶 | 不該紅 |
| IndexPage.corr-lazy.test.tsx | 非 corr subtab 零 WS | **搬到 App 層改寫**(檔刪) |
| CorrSection.test.tsx / CorrSection.lazy.test.tsx | 殼 | **隨 CorrSection 刪除**(語意由 App 層新測試接手) |
| BreadthBand.test.tsx (g)(o) | 停板數字 text-ink | **該紅** |
| AdvanceDeclineChart.test.tsx (d)(e)(f) 經 `pointCount()`/points 取 `adl-line` | 單 polyline | **該紅**(testid 拆 up/down → helper 換錨);(h)(i) `queryByTestId("adl-line")===null` 改名後恆 null → **不紅但 vacuous,必改寫**;(a)(b)(c)(g)(j) 不該紅 [r1: CS-3] |
| MarketPane.test.tsx / MarketChart.test.tsx | 未斷言 viewBox / 高度 | 不該紅(jsdom 量測 0×0 → 退回固定 SIZE) |
| LimitListSection.test.tsx | 篩選 / 文案 / 輪詢 | 不該紅(只動容器 class) |

Baseline:`npm test` 全綠(執行中,見 verification.md 記錄);後端不動。

## 2. 現況 vs 目標

| 面向 | 現況 | 目標 | caller 影響 | backward compat |
|---|---|---|---|---|
| 頂層 tab | 4 顆,corr 在台股綜合 subtab | 5 顆:台股綜合 \| 個股(期) \| 選擇權 \| 期貨 \| 相關係數(D7) | App.tsx nav / initialTab / visited / hidden 分支;RightRail ctx none 自然涵蓋 | `copycat-tab` 值域 **放寬回** `corr`(R1 前舊值又能還原;無遷移碼) |
| subtab 機制 | limit/corr 兩顆 + `INDEX_SUBTAB_KEY` | **退役**:漲跌停恆掛右欄,無 tablist | IndexPage / LimitListSection `active` 改直吃 App `tab==="index"`(現已如此,只是不再經 subtab 條件) | `copycat-index-subtab` 進 ORPHAN 清除;首訪零遷移 |
| CorrSection | subtab 殼 | 刪除(App 直接 lazy CorrPage,同 R1 前) | IndexPage 唯一 caller 同時移除 | 無 |
| 佈局 | 上下堆疊整頁捲 | 兩欄:左(基差 / 雙圖 / 家數帶+騰落線)右(漲跌停列表整高內捲),≥ 斷點單螢幕不捲;< 斷點退回堆疊 | IndexPage / MarketPane / MarketChart / AdvanceDeclineChart / LimitListSection 容器 class | 純 CSS,無資料格式 |
| 圖高 | 固定 viewBox 比例(寬決定高) | 依容器剩餘高(useContainerSize → viewBox 高);量測不可用退回固定 SIZE | MarketChart 新 optional prop `height`;OverlayCard 同 | jsdom / 舊路徑行為不變 |
| 家數帶停板桶 | 淡底 + ink 數字 | 實心 `bg-bull`/`bg-bear` + 白字(D8:up/down 字色不動) | 無 | 無 |
| 騰落線 | 單色 accent 線 | net>0 段紅、<0 段綠(線 + 面積,clip 手法) | 無 | 無 |
| 高度 | — | 騰落線 svg 改固定 CSS 高 + 量測 viewBox 高(不再寬決定高) | 無 | 無 |

## 3. Caller map(grep 結果)
- `CorrSection`:IndexPage.tsx:15,216;CorrSection.test.tsx;CorrSection.lazy.test.tsx → 全部一起處理。
- `INDEX_SUBTAB_KEY`:constants.ts:86;IndexPage.tsx:24,50,142;IndexPage.test.tsx:10,(s3)(s7)。
- `"台股綜合分頁"` / `index-subtabs`:IndexPage.tsx:190-192;IndexPage.test.tsx `subtabs()`/`subtab()`;IndexPage.corr-lazy.test.tsx。
- `LimitListSection`:IndexPage.tsx:18,214;LimitListSection.test.tsx;App.test.tsx(經 IndexPage 真鏈)。
- `AdvanceDeclineChart`:IndexPage.tsx:16,180;自身測試。
- `MarketChart` caller:MarketPane.tsx 唯一(+ 自身測試)。`OverlayCard`:MarketPane 內部。
- 動態用法:localStorage 字面值 `"copycat-index-subtab"` 出現於 App.test.tsx:460;無其他字串拼接讀寫。
- 後端 / e2e:無引用(`tests/` 下僅 corr 後端測試,與 UI 無關)。
