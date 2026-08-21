# current-state — a11y 批(R2 / D)

來源:`docs/superpowers/specs/2026-08-21-daytime-chain-rounds.md` §R2(user 拍板 → 預核准)。
證據:`docs/next-time.md` L276-281(review A3/A6)、L367-371(review A-4)、L1583-1588(doctor 側欄)。

## 1. `aria-pressed` 單選 pill 群(`grep -rn aria-pressed frontend/src/components`,不含 test)

| 檔 | 行 | 語意 | 處置 |
|---|---|---|---|
| `stock/PriceLadder.tsx` | 67 | 交易別 cash/margin/short…(`role=group` + button) | **單選 → radiogroup** |
| `stock/StockPage.tsx` | 220 | 檢視 single/group | 單選 → radiogroup |
| `stock/GroupGridView.tsx` | 332 | 群組選擇(`role=group` 選擇群組;檔數矩陣由群組推導) | 單選 → radiogroup |
| `OrderPanel.tsx` | 173/186、202/215 | 買賣別、委託類型(兩組 `role=group`) | 單選 → radiogroup ×2 |
| `futures/FuturesPage.tsx` | 83 | 商品 product | 單選 → radiogroup(同構) |
| `stock/StockChart.tsx` | 157 | 圖表模式(江波圖 / N 分 K / 日 K) | 單選 → radiogroup(同構) |
| `futures/FuturesChart.tsx` | 210 | 圖表模式 | 單選 → radiogroup(同構) |
| `index/MarketPane.tsx` | 92(`PeriodButton`,三列:標的 / 週期 / 模式) | 標的鍵、週期、模式各為單選 | 單選 → radiogroup(同構;`disabled` / `aria-disabled` 與 `@max-[26.5rem]:px-1` compact class 必保留) |
| `stock/GroupGridView.tsx` | 189(卡片 `role=button` active) | 「目前選取的標的」— 單選但卡片是複合元件 | **不動**(radio 包整張卡片會改語意與 focus 模型;out of scope) |
| `futures/FuturesLadder.tsx` 336/357/378、`stock/LadderView.tsx` 178/195/215、`stock/CandleChart.tsx` 575、`stock/StockIntradayChart.tsx` 1196、`GroupGridView.tsx` 357 | follow / armed / locked / showBb / overlay toggles | **真開關,保留 aria-pressed** |

既有測試讀 `aria-pressed` 的檔:PriceLadder.test(13)、StockChart.test(7)、FuturesChart.test(6)、FuturesPage.test(2)、
MarketPane.test(18)、MarketChart.test(2)、IndexPage.test(4)、GroupGridView.test(11)、GroupGridView.toggle.test(2)、
StockIntradayChart.test(11,toggles)、StkfutLadder.test(5)、LadderView.test(1)、FuturesLadder.test(3)、RightRail.test(8)、CandleChart.test(1)。
單選 pill 的斷言 = **該紅**(🔴 預告:改為 `getByRole("radio", { name })` + `.checked`);toggle 斷言 = 不該紅。

## 2. tablist 半套
- `rail/RightRail.tsx:291-306`:`role=tablist` + `role=tab` + `aria-selected`,**無** `aria-controls` / `id` / panel `role=tabpanel` + `aria-labelledby` / roving tabindex / 方向鍵。
  panel 是條件 render(`tab === "flash" ? flashContent() : null`,D-13 檔頭說明 —— 不可改 hidden)。
- IndexPage 的 subtab 列 **2026-08-16 已退役**(`IndexPage.tsx:8` 註解),grep 無 tablist → 本輪只有 RightRail 一處。
- `WatchlistSidebar.tsx:348` 群組收合鈕已有 `aria-expanded` + `aria-controls`(非 tablist,不動)。

## 3. 零態對比(`text-ink-dim` #55617a 對 `bg-surface` 2.92:1;`text-ink-muted` #8b96a8 6.06:1)
- `WatchlistSidebar.tsx:94` 群組平均漲幅 `shown === 0`;`WatchlistSidebar.tsx:498` stockRow 漲跌 0 → `text-ink-dim`;
  `GroupGridView.tsx:91` QuoteCell `q?.p == null`(無成交,參考價)。三處同口徑 → `text-ink-muted`。
  其他 `text-ink-dim`(鈕未選態、說明文字、無資料)不在此批。

## 4. 側欄自選列鍵盤路徑
- `WatchlistSidebar.tsx:393-402` `wl-row-*` 是 `div onClick`,無 role / tabIndex / key handler(doctor no-static-element-interactions)。
  組內排序(拖曳握把 aria-hidden)仍無鍵盤路徑 → **本輪只做 row 可 focus + Enter/Space 選取**,排序留 next-time(§R2 明寫「至少」)。

## 現況 vs 目標
| 面向 | 現況 | 目標 |
|---|---|---|
| 單選 pill | N 個 tab stop、AT 聽成 N 個互不相干開關 | 1 個 tab stop、方向鍵切換、AT 聽成 radiogroup(sr-only `<input type=radio>` + `<label>`) |
| RightRail tab | 只有 selected 狀態 | tab ↔ tabpanel 互連、方向鍵 + roving tabindex |
| 零態色 | 2.92:1 | 6.06:1(三處) |
| 自選列 | 滑鼠 only | Tab 可達、Enter/Space 選取 |
| 視覺 | — | **零變**(class 原樣搬到 label;focus ring 用 `peer-focus-visible`) |
| 對外契約 / migration | 無 | 無 |


## 更正(spec review round 1)
- tablist 第二處:`frontend/src/App.tsx:230-253`(`aria-label="主要分頁"`,5 tab,panel 為 hidden div 264-283)—— 本輪納入。
- MarketPane 實為兩列(標的列含 isFut 子群 / 週期列含「重疊」toggle),非三列。
- 單選但無 aria-pressed:`corr/RiverPanel.tsx:86-100`(並排 / 重疊)→ out of scope 記 next-time。
- 既有測試以 `getByRole("button")` 定位 pill 的檔(該紅):App.test / StockPage.test / StockChart.futconverge.test / RightRail.test / IndexPage.test / MarketPane.test / FuturesChart.test / StockChart.test。
- WatchlistSidebar row 內含兩顆真 button(518 加入群組 / 532 移除)→ row 不能 role=button(nested-interactive)。
