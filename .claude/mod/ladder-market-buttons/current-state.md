# current-state — 三座閃電梯梯頂「市價買 / 市價賣」(mod/ladder-market-buttons)

> 對應 prompt:`docs/superpowers/specs/2026-08-17-user-feedback-batch3-rounds.md` §2 R1;拍板 D1–D6(同檔 §1)。
> 行號快照 = 本分支起點 master `8cc9f524`(2026-08-17 重 grep 驗過)。
> Baseline:pytest 2638 passed / vitest 119 files 1971 passed(分支起點,兩者全綠)。

## 1. 現況 caller map(三座梯 + 表現層 + 後端鏈)

| 層 | 檔 | 現況 | 本輪 |
|---|---|---|---|
| 現股容器 | `frontend/src/components/stock/PriceLadder.tsx` | `clickPrice(priceMilli, side)` :261-312,payload :282-291 `price_type:"limit"` / `time_in_force:"ROD"` 寫死;武裝守門 :264-267(未武裝 → hint「未武裝 — 點價不送單」);同格 500ms 防抖 :268-277;無券鎖買側 :263 + `buyLocked` :377;`last?.p` 是梯面最近成交價(:239 部位口徑、:247 buildLadder center) | 新增 `marketOrder(side)`(送 `price_type:"market"`、`price=last.p/1000`)+ 把 `MarketOrderButtons` 塞 LadderView 新插槽 |
| 個股期容器 | `frontend/src/components/stock/StkfutLadder.tsx` | `clickPrice` :148-193,payload :168-177 limit/ROD 寫死;`blocked = isOrderBlocked(code, contract.unit)` :121,雙保險 :150;`last?.p` :134;`meta.upper/lower` :136-137(契約漲跌停,餵 buildLadder);armControls = 當沖 checkbox :273-287;`dayTrade` :98 進 payload :175 | 新增 `marketOrder(side)`:送 **limit@貼漲跌停 + IOC**(D3a),估價鎖鈕 = `last?.p` 缺 **或** 漲跌停缺 |
| 期貨容器 | `frontend/src/components/futures/FuturesLadder.tsx` | `clickPrice` :144-188,payload :163-172 limit/ROD 寫死;`centerMilli = state.p ?? state.ref` :120;`state.upper/lower` :122 是 rows 前置;**自建 UI 不經 LadderView** :271-505(鎖定鈕是「第三份複本」:322 註明三梯合一 out of scope);平倉 `confirmClose` :208-228 → `closeBodyOf(pos, futCloseEstimate(...))` → `/api/capital/position/close` | 新增 `marketOrder(side)` 同 D3a;梯頂鈕列單獨放一份(引用同一 `MarketOrderButtons`) |
| 表現層 | `frontend/src/components/stock/LadderView.tsx` | Props :65-109;`armControls` 插槽 :92-93/:236;五檔**市價佇列列** :272-286(bid)/:408-418(ask)—— 顯示「市價」小標、不可點、不進 rowRefs;檔位列買賣鈕 :355-366/:378-389 綁 `onClickPrice(priceMilli, side)`;scroll 區 :265-419;footer :424 | 新增 `ladderTop?: ReactNode` 插槽,渲染於武裝列之後、scroll 區之前(不隨捲動、不進 rowRefs) |
| 平倉貼邊 helper | `frontend/src/lib/futures-ladder.ts::futCloseEstimate` :112-120 | **貼漲跌停的實際選邊在前端**:多倉平(=賣)→ `prod.lower`,空倉平(=買)→ `prod.upper`,`edge/1000`;null 判定只看 `edge !== null` | 🔵 抽 `edgeMilli(side, upper, lower)`,futCloseEstimate 改呼叫(行為零變) |
| 平倉 body | `frontend/src/lib/close-order.ts::closeBodyOf` :36-46 | 平倉 body 唯一產生處(`price_type` 不帶 → 後端預設 market → `build_future_close_order` 強制 limit+IOC) | 不動 |
| 後端 close | `copycat/capital/close.py::build_future_close_order` :58-86 | 只做「強制 `price_type="limit"` + `time_in_force="IOC"`」(:83-84),**價格是 caller 帶的貼邊價**;不含選邊邏輯 | 不動(見 §3 判定) |
| 後端 mapping | `copycat/capital/mapping.py` | `_SPECIAL{market:1, limit:2}` :50;現股 :186-199 `nSpecialTradeType=_SPECIAL[price_type]`、`bstrPrice=f"{price:.2f}"`(市價仍塞估價字串);期貨 :202-232 market → `bstrPrice="M"` + ROD 升 IOC(:216-219) | 不動(OrderPanel TXO 市價仍走 "M";tests test_mapping :90-103 / :146-158 全保留) |
| 後端 safety | `copycat/capital/safety.py` :40-57 | `_bad_price`(market 估價必 >0 且有限)、名目金額閘一視同仁 | 不動 |
| 後端 route | `copycat/server/capital_api.py` | `StockOrderBody.price: float` 必填 :66;`FutureOrderBody` :74-82;`_stkfut_gates` :159-174 limit 才驗 tick(market 跳過);route :224-267 | 不動 |
| 後端 client | `copycat/capital/client.py::submit_stock_order/submit_future_order` :687-731;`_execute_write` 回 `OrderResult(seq_no)` :672-682 | 送單成功後 store **不知道** price_type(回報無此欄) | 新增:成功且有 seq_no → `store.note_price_type(seq_no, req.price_type)` |
| 後端 store | `copycat/capital/store.py` `_Agg` :50-70、`_to_record` :158-186、`clear()` :217 | `OrderRecord` 無 `price_type`;`apply_reply` 與送單結果到達序**不保證**(COM 執行緒 vs async) | 新增 `_price_types: dict[seq_no, PriceType]`(獨立於 `_Agg`;`clear()` 不清)、`OrderRecord.price_type: str | None = None` |
| 回報解析 | `copycat/capital/reply.py` | `ReplyRecord` 無價格別欄(官方回報 idx11 只有 price) | 不動 |
| 委託列表 | `frontend/src/components/capital/CapitalOrdersList.tsx` :103 `priceText = price ?? "—"`、:134 顯示、:172 placeholder、:213 確認框「原委託」 | 🔴 `price_type === "market"` → 價格欄前綴「市價」標籤(price 仍印回報價 / 缺印 —) |
| 型別 | `frontend/src/types.ts` `CapitalOrder` :68-89(無 price_type);`CapitalStockOrderBody` :118-127 / `CapitalFutureOrderBody` :129-138 已含 `price_type`/`time_in_force` | `CapitalOrder` 加 `price_type: "limit" \| "market" \| null` |
| Rail caller | `frontend/src/components/rail/RightRail.tsx` :156-198 | 三梯的唯一 prod caller;`last`/`meta`/`state` 由 ctx 下傳 | 不動(props 只加不改) |
| 樣板 | `frontend/src/components/OrderPanel.tsx` :57-58 `marketEstimate`、:216-228 市價鈕 disabled+title | 抄鎖鈕文案模式 |

動態用法 grep:`onClickPrice` 只有 LadderView 內部與三容器;`LadderView` caller = PriceLadder / StkfutLadder(+ 測試裸 render);`futCloseEstimate` caller `[amendment 2026-08-17: review R2 補齊]` = `FuturesLadder.tsx:106`、`RightRail.tsx:256`(個股期部位平倉估價,**未 snap** 的 `meta.upper/lower`)、`RightRail.tsx:275`(期貨部位)、`FuturesPage.tsx:19`(對外 re-export);值斷言測試在 `FuturesPage.test.tsx:150-168`(20_520 / 25_080 / null 三種)+ `RightRail.test.tsx:384,519`(經 closePriceOf 間接);`futures-ladder.test.ts` **沒有** futCloseEstimate 案例;`OrderRecord(` 建構點 = store `_to_record` + tests 2 處(有 default 不破);前端 `CapitalOrder` 物件字面值 fixture 9 檔 29 處(加必填欄要同步補)。

## 2. 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 行為 | 三梯只能點價送**限價 ROD**;市價無 UI 觸發點 | 梯頂固定兩顆「市價買」「市價賣」:武裝態一鍵送、未武裝 hint、無估價 disabled |
| 送單 wire | 現股/個股期/期貨皆 `limit/ROD/priceMilli` | 現股:`market/ROD/price=last.p`(閘用估價,群益 nSpecialTradeType=1);個股期 & 期貨:`limit/IOC/price=貼漲跌停邊價`(D3a,同平倉路徑 wire 形狀) |
| Signature | `LadderView` 無梯頂插槽;`futCloseEstimate(pos, contract, prod)` | `LadderView` +`ladderTop?: ReactNode`;新 `edgeMilli(side, upper, lower)`;`futCloseEstimate` 簽名不變 |
| 委託列表 | 市價單價格欄印回報價或 — ,無法辨識 | 本 app 送出的市價單標「市價」;非本 app 送出(APP 下單)無法辨識 → 維持現況(known limit) |
| Caller 影響 | — | LadderView 新 prop 選配 → 既有裸 render / 測試零改;`CapitalOrder` 加必填欄 → 前端 fixture 補欄 |
| Backward compat | — | 後端 `OrderRecord.price_type` 有 default,舊 client 讀多一欄無害;無 migration |

## 3. 判定:D3(a) 的「沿 close.py helper」落點在**前端** `[amendment 2026-08-17: review R3/R8 改寫為事實]`

close 路徑的分工:`futCloseEstimate`(前端)選邊 → body.price=邊價 → `POST /api/capital/position/close`(**不經** `_stkfut_gates` / 符號解析)→ `build_future_close_order`(後端)把 price_type/tif 釘成 limit/IOC → `to_futureorder_fields(new_close=1)`(倉別=平倉)。
新市價鈕走 `POST /api/capital/order/future`:經 `product_of/multiplier_of/to_exchange_symbol` 解析 + `_stkfut_gates`(PRODUCT_NOT_ALLOWED / limit 單 `_require_legal_tick` → BAD_TICK)→ `new_close=2`(自動)。**兩條是不同路由、不同閘、不同倉別,平倉的驗收不覆蓋新鏈路**;新鏈路首次驗證點 = SC-12(a) 403 audit + D4 安全首單。
後端 fut `price_type=market` 的映射是 `"M"` literal(OrderPanel TXO 市價在用,tests 鎖住,白名單全保留),**不能**改成「market 進來 → 後端轉 limit@邊價」(會改 OrderPanel 行為,且後端要反查 stkfut/期貨漲跌停 = 新耦合)。因此:
- 市價鈕(個股期/期貨)由**前端**直接送 `limit/IOC/邊價`;
- 🔵 抽的共用 helper = 前端 `edgeMilli(side, upper, lower)`(raw 選邊:buy→upper / sell→lower),`futCloseEstimate` 改呼叫它、回傳值逐案不變;
- 後端 mapping / gate / close.py **零改動**;唯一後端改動是 §1 的 store/client「本 app 送出市價單的 price_type 記憶」(供 🔴 委託列表標籤)。
- 個股期市價邊價 = `snapDown(upper)` / `snapUp(lower)`(現股 tick 表,= buildLadder rows 頂/底那格)否則 `_stkfut_gates` 400 BAD_TICK;期貨市價邊價 = `floor(upper/FUT_TICK)*FUT_TICK` / `ceil(lower/FUT_TICK)*FUT_TICK`(與 `buildFuturesLadder` :132-133 同口徑;`state.upper` 不保證落在合法檔位,期貨路徑後端無 tick 閘、只能靠券商退單)。
- **known-limit(next-time)**:個股期平倉 `RightRail.tsx:256` 用未 snap 的 `meta.upper/lower`(平倉路徑無 tick 閘、從未報錯),與市價鈕 snap 後的邊價可能差一檔;本輪不動平倉路徑(out of scope),「貼漲跌停」的 snap 口徑收斂記 next-time。

## 4. 邊界事實(影響 spec 的)
- 現股 `meta.upper/lower` 缺值時 buildLadder 用假想界 ±10%(stock-tick.ts:134-135)→ 個股期市價鈕**不得**用假想界送單:漲跌停缺 → 鎖鈕。
- `last?.p` 在 reset 窗(rollover / self-heal)會空數分鐘(next-time.md:489-496 TXO 同類坑)→ 鈕鎖回、title 說明,不送。
- 鎖漲停日 bids[0] 是價格 0 的市價佇列(tc4-market-facts §鎖漲跌停):現股市價買會排在該佇列之後,開板才成交、成交價可達漲停;個股期/期貨 IOC 邊價單無對手即刻取消,不排隊。
- 名目金額閘用邊價(買=漲停)估算 → 比實際成交偏高 ≤10%,可能較限價早觸 max_amount(保守側,可接受)。
- 現股市價 `nSpecialTradeType=1` 端到端未實測(D4:上線後 user 盤中低價股 1 張安全首單)。
