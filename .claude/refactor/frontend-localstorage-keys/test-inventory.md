# test-inventory — refactor/frontend-localstorage-keys(2026-08-04)

Baseline:`npm test` 72 files / **996 passed**(前一輪 frontend-dedupe-format merge 後)。

## Key 盤點(source 定義 14 個 + 孤兒 2 個)

| key | 定義處 | 測試字面值斷言(現成 characterization) |
|---|---|---|
| copycat-tab | App.tsx:27 | App.test.tsx:73,91,143,223 |
| **stock-main-code**(無前綴,本輪改名) | App.tsx:28 | App.test.tsx:202,211(舊字面值 setItem → 改名後靠 migration 仍須綠 = 遷移保護網) |
| copycat-fut-product | App.tsx:29 | App.test.tsx:242、IndexPage.test:133 |
| copycat-market-key / -tf / -fut | IndexPage.tsx:21-26 | IndexPage.test:131-132,169,225-226 |
| copycat-index-mode | IndexPage.tsx:23 | IndexPage.test:246,250,256 |
| copycat-signal-sound | useSignalSound.ts:14 | useSignalSound.test:21、useSignalAlerts.test:187 |
| copycat-chart-toggles | useChartToggles.ts:3 | useChartToggles.test(自持字面值 const)、StockIntradayChart.test:23 |
| copycat-rail-tab | RightRail.tsx:23 | RightRail.test:141 |
| copycat-chart-mode | StockChart.tsx:16 | StockChart.test:72,106 |
| copycat-river-mode / -legs | RiverPanel.tsx:16,18 | RiverPanel.test:80,90,110-111,122-123 |
| copycat-stock-wl-collapsed / -ungrouped-collapsed | WatchlistSidebar.tsx:32,34 | WatchlistSidebar.test(自持字面值 const:30-31) |
| stock-ladder-open(孤兒) | 零讀寫(僅 PriceLadder.test:159 註解提及) | 無(清除行為本輪補測試) |
| stock-wl-group(孤兒) | 零讀寫 | 無(同上) |

**結論**:每個活 key 的字面值都已被至少一處測試釘死(測試側字面值**保留不改** —— 它們
就是「集中到 constants.ts 不得改到 key 值」的守護網)。缺口只有兩塊,隨改動補 🟢 測試:
(1) stock-main-code 遷移(新 key 優先 / 舊值搬遷 + 移除);(2) 孤兒鍵啟動清除。

## 誤收禁區(查證確認)

- `stock-price-click` = CustomEvent 名,非 storage key。
- `stock-bars` / `stock-watchlist` / `stock-names` 等 = react-query queryKey。
- `copycat-river-*` 測試字面值在 RiverPanel.test — 是 storage key 沒錯,已列上表。
