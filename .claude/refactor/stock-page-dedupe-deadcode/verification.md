# Verification — stock-page-dedupe-deadcode(2026-08-03)

## Phase 6|自動化(refactor 完成後最終跑,全部主 session 親跑)

| Gate | Baseline(refactor 前) | 最終 | 結果 |
|---|---|---|---|
| `pytest -q` | 1481 passed | **1481 passed**(+3 characterization −3 死碼測試,淨零) | PASS |
| `npm test` | 898 passed / 65 files | **889 passed / 65 files**(−9 條全為死碼能力測試,逐條圈定於計畫) | PASS |
| `ruff check copycat tests` | pass | **All checks passed!** | PASS |
| `pyright` | 0 errors | **0 errors, 0 warnings** | PASS |
| `npx tsc -b` | exit 0 | **exit 0** | PASS |
| `npx eslint src` | exit 0 | **exit 0** | PASS |
| `copycat validate` | —(本輪首跑) | **42/42 PASS** | PASS |
| `npm run build` | — | ✓ built in 966ms | PASS |

## Phase 5|Blast radius(主 session 親跑 grep)

- 毫元 `fmt` 只剩 `lib/format.ts` 一份;指數版 `fmt(millipts)` 三份原地未動(R-12)
- `pts` 只剩 `lib/svg-points.ts` 一份
- `stock-suggest` testid 僅側欄 + 其測試(R-7 驗收)
- 已刪名(watchlist_codes / StockEngineLike / AnyDict / buy_sell_flag / ungrouped( /
  parse_isin_html / upperY / setMembership / FUT_KEYS / insertIndexFromPointer / stkfutProd /
  cumInner(活碼)/ drag.index)在 copycat/ + frontend/src 零殘留(僅 .claude artifacts 文件引用)
- 動態用法 `hasattr(self._source, "on_reconnect")` 4 處原封未動
- OrderBook 的 onPriceClick 為活碼(stock-price-click 事件鏈)確認未誤刪 — 死碼是 DepthBar 那條

## Phase 7|真實環境

1. **後端 HTTP 層**(fake source + uvicorn port 8899,零 ZMQ — 遵守「盤中不起第二台連 TC4」):
   smoke 6/6 PASS(health shape / names 2401 / watchlist / BAD_CODE 400 / index 未配置
   NOT_READY 503 / stock state 200 含 cum_inner·cum_outer = 後端 payload 契約未動)。
   附帶實證 C7 `_boot` 失敗降級:capital 登入失敗(SK_ERROR_TELNET_LOGINSERVER_FAIL)→
   其餘引擎照起、API 全正常 — 與 refactor 前行為一致。
2. **前端畫面**(vite dev 5175 → 跑著的 8721 server 真資料,未動該 server):
   個股頁 2330 完整渲染 — 江波圖 + CDP 疊線(2485*/2465*/2405*/2385*/2325*)+ VWAP 線 +
   量副圖 + 內外盤說明列(外盤 20491 · 內盤 12763 · 未分類 1017 · 外盤比 61.6% ·
   判定率 97%)+ 五檔量 bar + 成交明細 + 側欄漲停紅底(4989/2327)+ 閃電梯。
   截圖:`screenshots/stock-page-live-post-refactor.png`。
   Console:僅 StrictMode 雙掛載 WS 警告 + favicon 404(均既有);API 請求全 200。
   **User 過目待補**(/auto 自主模式,盤後態截圖已存證)。

## Phase 8|回頭核

- 動機:三個子目標全數處理 — 去重(前端 9 步 + 後端 9 步 + 測試層 3 步)、死碼
  (後端 5 項 + 前端 17 項,連同僅測試引用之測試)、邏輯疑點(safe 類 13 項修畢,
  behavior 類 8 項記 docs/next-time.md)。
- 行為差異:無 — 兩輪 plan review(4 P0 全數在計畫期擋下)+ per-step 測試 + 全套 gate +
  真環境對照;Track A6/A4-useStockNames 兩處實作期發現「收斂即改行為」→ 依紀律跳過轉記。
- 量化:diff 約 -700/+520(死碼淨刪 > 新增 helper);逐字重複具名 helper 由 9+6+4+3 份
  收斂至各 1 份;後端 ZMQ listener / 訂閱核心 / WS fanout / lifespan 樣板各由 3-5 份收斂至
  基底/共用 1 份。
