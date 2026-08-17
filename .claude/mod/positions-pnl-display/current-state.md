# current-state — mod/positions-pnl-display(batch3 R3)

> 快照:master `cdaee027`(2026-08-17)。來源 prompt:`docs/superpowers/specs/2026-08-17-user-feedback-batch3-rounds.md` §2 R3。
> baseline:`pytest tests/server/test_capital_api.py tests/capital` 390 passed;`vitest run` 121 files / 2100 passed。

## 1. 資料流(現況)

| 環節 | 檔:行 | 事實 |
|---|---|---|
| 後端部位模型 | `copycat/capital/models.py:137-148` `Position{market("sec"/"fut"), stock_no(sec=股號;fut=期交所契約碼), qty(張/口,空方負), name, avg_price(元;可 None), kind(TradeKind;fut 恆 "cash"), pnl_base(含費稅息淨損益,報告時點快照), pnl_base_price, pnl_cost}` | **沒有 `code`(股號)欄** |
| 部位 API | `copycat/server/capital_api.py:218-221` `GET /api/capital/positions` → `{"positions":[asdict(p)...]}`;`_capital()`(:121-125)capital 未啟用 raise `CapitalDisabledError` | 純 asdict 轉發,無衍生欄 |
| 契約碼→產品碼 | `copycat/capital/mapping.py:89-106` `exchange_product_of("CDFI6")→"CDF"`(已知產品最長前綴 → 去尾 2 碼全字母 → 開頭字母段;解不出 raise ValueError) | 反查唯一入口 |
| 產品碼→股號 | `copycat/stkfut_map.py:164-174` `lookup_product(prod)` → `{unit, kind:"std"/"mini", code}` 或 None(版控 `copycat/stkfut_map.json`,process 級 cache) | 已被 mapping.multiplier_of / capital_api._stkfut_gates 共用 |
| 前端型別 | `frontend/src/types.ts:97-108` `CapitalPosition` 與後端同形 | 無 `code` |
| 前端 query | `frontend/src/hooks/useCapital.ts:166-173` `useCapitalPositions()` queryKey `["capital-positions"]`,15s 輪詢 + WS `capital_position` 200ms debounce invalidate(:124);mutation 成功 invalidate(:180-187) | 查詢結果全域共用;但 `refetchInterval` 是 per-observer 計時器 → 新增 observer 會增加輪詢次數(上界待側車量測;`[amendment 2026-08-17: R23]`) |
| 後端 API 測試 | `tests/server/test_capital_api.py:211-260` positions 讀路(空 / 反映 store / 同股號兩 kind 並存) | 斷言只看 `stock_no` / `market` / kind,不做整包相等 → 加欄不紅 |

## 2. 損益計算(現況)

| 環節 | 檔:行 | 事實 |
|---|---|---|
| 含費稅口徑 | `frontend/src/lib/ladder-position.ts:54-84` `positionEcon(qty, avgPrice(元), lastMilli(毫元), discount, kind)` → `{pnl(元,四捨五入)|null, breakEvenMilli}`;`qty===0`/avg 缺 → 全 null;last 缺 → pnl null | **只適用證券(sec)**;fut 不套(StkfutLadder 註解 :343-345 明說) |
| 折數來源 | `PriceLadder.tsx:143-167` `loadDiscount()`(localStorage `FEE_DISCOUNT_KEY="copycat-fee-discount"`,`constants.ts:114`;缺/壞 → `FEE_DISCOUNT_DEFAULT=1.8`)+ `persistDiscount()`;state 在 PriceLadder 元件內(:263),輸入框 :494-514;`clampDiscount` 在 lib | **折數 = localStorage 單源;元件內私有 loader,其他元件目前無法同源讀取** |
| 現股梯部位列 | `PriceLadder.tsx:177-197` `positionRows()`(每列 `positionEcon` + `kindLabel` + `@均價`)、`:99-132` `PositionBar`(`pnlText/pnlTone`)、`:275-283` 接線(`secPositionsOf(positions, code)` + `last?.p` + `discount.value`) | 每 tick 重算不 memo |
| sec 過濾 | `ladder-position.ts:111-118` `secPositionsOf(positions, code)`:market==="sec" && stock_no===code && qty≠0,KIND_ORDER 排序 | 可重用 |
| kind 標籤 | `PriceLadder.tsx:40-55` `TRADE_KINDS`(export)+ `kindLabel()`(**非 export**;現股/融資/融券/無券) | 需 export 或搬 lib |
| 個股期梯部位列 | `StkfutLadder.tsx:50-58` `contractPositions(positions, exchangeContract)`(market==="fut" && stock_no===契約碼);`:338-366` 顯示 `多/空 n 口 @avg` + **`pnlText(p.pnl_base)`(群益名目損益快照)** | **個股期「與閃電梯同一數字」= `pnl_base`,不是 positionEcon** |
| pnl 文字/色 | `LadderView.tsx:52-63` `DASH="—"`、`pnlText`(+號、千分位)、`pnlTone`(>0 bull / <0 bear / 0 ink / null ink-dim) | 三態規則同構,可重用 |
| 契約碼組法(前端) | `lib/futures-ladder.ts:88-95` `futExchangeContract(prod, ym)` = prod + 月碼字母 + 年尾碼 | 前端只會「股號+選月 → 契約碼」,**沒有反向(契約碼→股號)**;產品→股號對照只在後端 `stkfut_map` |

## 3. 三個顯示點(現況:零倉位資訊)

| 顯示點 | 檔:行 | 現況 |
|---|---|---|
| 自選列 | `WatchlistSidebar.tsx:362-470` `stockRow(code, group)`:`ROW_H=52` 兩行式(:32),左欄 flex-col(代號+緩撮 / 名稱 truncate),右欄 `wl-quote-{code}` flex-col items-end(價 / 漲跌%;亮燈整塊底色 :404-407);`quotes[code]` = `WatchlistQuote{p(毫元),chg_pct,vol,ref,upper,lower,no_data,trial}`;元件不掛 useCapital*;測試 `WatchlistSidebar.test.tsx`(fetch stub 只接 watchlist / names)+ `.dropcollapsed.test.tsx` | 無倉位 |
| 單檔 header | `StockPage.tsx:255-340` `<header class="flex flex-wrap items-baseline gap-3">`:名稱+代號(+緩)、合約 select、`page-quote`(價+%)、無資料/回補中、期現價差、加入自選;`last = accum.last`(毫元)、`contract`(null=現貨態;非 null = 個股期態,`futExchangeContract(contract.prod, contract.ym)` 可得契約碼);測試 `StockPage.test.tsx`(fetch stub 未接 capital → 404) | 無倉位 |
| 群組卡 | `GroupGridView.tsx:74-103` `QuoteCell({code,q})`(tone 三態 :75-82;p / ref 參考 / -);`:112-203` `GroupCard = memo(...)` props `{code,snap,quote,active,toggles,fills,sizeClass,onPick}`(`fills` 走 `EMPTY_FILLS` 穩定 identity 範式 :139-141,`fillsMap` 圖牆層 useMemo :247-249);圖牆層已掛 `useCapitalOrders`;測試 `GroupGridView.test.tsx`(fetch stub 接 overlay / capital/orders / group-state)+ geometry / memo / toggle 三檔 | 無倉位;每秒 re-render 警示 :107-111 |

## 4. 現況 vs 目標

| 面向 | 現況 | 目標 | caller 影響 | backward compat |
|---|---|---|---|---|
| positions API 形狀 | 無 `code` | 每列附 `code: str|null`(sec=stock_no;fut=`lookup_product(exchange_product_of(stock_no)).code`,解不出 → null) | 讀者:`useCapitalPositions` 全部消費者(PriceLadder / StkfutLadder / FuturesLadder / FuturesChart / CapitalPositionsList)只讀既有欄,**加欄零影響**;測試 `test_capital_api.py` 斷言不做整包相等 | 純加欄,舊前端忽略;無 migration |
| 折數讀取 | PriceLadder 私有 `loadDiscount` | lib 化(`lib/fee-discount.ts`),PriceLadder 改 import,行為不變 | PriceLadder 唯一 caller | 無 |
| kindLabel | PriceLadder 私有 | export(或搬 lib)供三處共用 | PriceLadder 唯一 caller | 無 |
| 三處 UI | 零倉位資訊 | 有倉才顯示(D9 a);sec 含費稅 positionEcon;fut 用 pnl_base | 新增 observer,不改既有欄位 | 無倉時 DOM 零變化 |

## 5. 動態用法 grep 結果

- `useCapitalPositions` caller(非測試):PriceLadder / StkfutLadder / FuturesLadder / FuturesChart / CapitalPositionsList / useCapital.ts 內部 —— 全部只讀 `market/stock_no/qty/avg_price/kind/pnl_base`,無 `Object.keys` / spread 相等比對。
- `asdict(p)`(Position)僅 `capital_api.py:221`;`Position(` 建構點 `balance.py:134,182`、`store.py`、tests —— 加 dataclass 欄需給預設值否則建構點全紅 → **決定不動 dataclass,在 API 邊界附欄**(見 change-spec)。
- 前端無任何 `contract → code` 反查;`fill-marks.ts:198-203` 同樣只做正向(群組卡個股期委託不標,留尾)。

## 6. `[amendment 2026-08-17: spec review R1]` TradeKind / pnl-format caller
- `PriceLadder.tsx:46` `export type TradeKind` 的非測試 caller:`components/rail/RightRail.tsx:7`(`import { PriceLadder, type TradeKind }`);測試 `PriceLadder.test.tsx:6`。搬家必 re-export type。
- `LadderView.tsx:52-63` caller:`pnlText`/`pnlTone` → PriceLadder / StkfutLadder(+ 各測試);`DASH` → StkfutLadder(PriceLadder 另有 local 一份 `:49`,搬家時改 import;`[amendment 2026-08-17: R21]`)。
