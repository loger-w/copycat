# Test Inventory — refactor/stock-page-dedupe-deadcode(2026-08-03)

## Phase 1|Why

User 直接指定(/auto + /refactor):個股頁面歷經六輪迭代(自選/江波圖/五檔/明細/內外盤/
極值標記/市價列),累積重複碼與死碼;下一輪開工前的清理窗口。三個子目標:

1. 前端與後端各自去重(TS ↔ Python 跨語言不共 code,「去重」指各自層內)
2. 刪除死碼(鐵則:必查動態用法後才可刪)
3. 檢查不符合邏輯的寫法 — **會改行為的只記錄不修**(/refactor 行為絕對不變;
   [auto-default: 記錄至 docs/next-time.md 供另開 /mod | reason: refactor 核心紀律])

[auto-default: 退出條件 = 既有測試前後皆全綠 + 全 gate PASS | reason: auto.md /refactor 行建議]

## Phase 2|Baseline(refactor 前,master==origin/master @ 739ed2a)

| Gate | 結果 |
|---|---|
| `.venv\Scripts\python -m pytest -q` | **1481 passed**, 1 warning, 59.98s |
| `npm test`(frontend/) | **898 passed**(65 files), 9.74s |
| ruff / pyright | All checks passed! / 0 errors, 0 warnings |
| tsc -b / eslint src | exit 0 / exit 0 |

## 覆蓋盤點(個股頁面範圍)

前端:components/stock/ 9 個元件全部有對應 .test.tsx;stock 相關 hooks
(useStockBars/useStockOverlay/useStockNames/useStockStream/useStockWatchlist/
useChartToggles/useMarketBars/useContainerSize)全部有 .test;lib(stock-*、candle*、
chart-*、bollinger、timeframe(無獨立 test,由 caller test 覆蓋)、trading-hours(同)、
list-drag、watchlist-model)絕大多數有直接 test。

後端:tests/ 覆蓋 live/stock_models、stock_state、stock_source、server/stock_engine、
overlay、stock_watchlist、stock_names、app routes(1481 條全套)。

判定:**覆蓋足夠,不需補 characterization test**;純去重/死碼刪除若動到無直接 test 的
timeframe/trading-hours,以 caller 測試 + tsc 保護,萬一步驟中發現裸區再補。
