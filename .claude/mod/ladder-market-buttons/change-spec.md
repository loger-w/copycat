# change-spec — 三座閃電梯梯頂「市價買 / 市價賣」(mod/ladder-market-buttons)

> 現況表:`.claude/mod/ladder-market-buttons/current-state.md`(reviewer 先讀)。
> 拍板來源:`docs/superpowers/specs/2026-08-17-user-feedback-batch3-rounds.md` §1 D1–D6(user 已拍板,不重問)。
> 分流判定:**已成形方案**(prompt 指名落點檔案 / UI 位置 / wire 形狀 / 三類切分)→ grilling 姿態,決策點逐條列 `[auto-default]` 於 §7。
> 規模:L(≥ 5 檔、跨前後端、碰下單安全面)→ spec review 1 輪 + P0 限縮加輪;實作 dispatch(opus)。

## 0. 目標一句話
三座閃電梯(現股 / 個股期 / 期貨)價格梯第一列之上,固定並排兩顆「市價買」「市價賣」;武裝態一鍵送市價單、不加確認框;無成交價鎖鈕。現股走群益真市價映射;個股期與期貨的「市價」= 限價貼漲跌停 + IOC。

## 1. 成功條件(SC;UI 用畫面可指認表述)

| # | 成功條件 | 驗證方式 |
|---|---|---|
| SC-1 | 三座梯的武裝列之下、價格列之上,恆常渲染一列 `data-testid="ladder-market-buttons"`:左「市價買」(bull 外框字色)、右「市價賣」(bear 外框字色),各佔一半寬;捲動價格梯時該列**不動**(在 scroll 容器之外) | vitest:三梯各 render 一次查 testid + 兩顆 button 文字;DOM 順序:該列在 scroll 容器(`overflow-y-auto`)之前;截圖對照 |
| SC-2 | 現股:武裝後按「市價買」→ 送 `POST /api/capital/order/stock` body `{stock_no, buy_sell:"buy", price: last.p/1000, qty, price_type:"market", time_in_force:"ROD", trade_kind, source:"flash"}`;hint「已送 <股號> 市價買 × N」(帶標的,review R5);`send_ok` 計入武裝 reducer;防抖用**市價鈕獨立 ref**(review R9) | vitest `PriceLadder.test.tsx` 新 describe「市價鈕」:fetch mock 斷言 payload 逐欄 |
| SC-3 | 個股期:武裝後按「市價賣」→ 送 `POST /api/capital/order/future` body `{tc4_symbol, buy_sell:"sell", price: snapUp(meta.lower)/1000, qty, price_type:"limit", time_in_force:"IOC", day_trade, source:"flash"}`;「市價買」→ `price: snapDown(meta.upper)/1000`;hint「已送 <期交所契約碼> 市價賣 × N 口」(review R5) | vitest `StkfutLadder.test.tsx` 新案例斷言 payload;`lib/stkfut.test.ts` 純函式案例 |
| SC-4 | 期貨:武裝後按「市價買」→ `{tc4_symbol:"TC.F.TWF.<prod>.HOT", buy_sell:"buy", price: floor(state.upper/FUT_TICK)*FUT_TICK/1000, qty, price_type:"limit", time_in_force:"IOC", day_trade, source:"flash"}`;賣 → `ceil(state.lower/FUT_TICK)*FUT_TICK/1000`(review R8,與 buildFuturesLadder 同口徑);hint「已送 <契約碼> 市價買 × N 口」 | vitest `FuturesLadder.test.tsx` 新案例 |
| SC-5 | 未武裝按任一顆 → 零請求 + hint「未武裝 — 市價不送單」(3s 自清) | vitest 三梯各一案例(fetch 零呼叫) |
| SC-6 | 估價缺 → 兩顆 `disabled` + `title="無成交價,市價鈕鎖定"`:現股 `last===null`;個股期 `last===null` **或** `meta.upper/lower` 缺(null/0);期貨 `state.p ?? state.ref` 為 null 或 `upper/lower` 缺或合約未解析 | vitest 三梯各一案例(disabled + title) |
| SC-7 | 無券(`tradeKind==="daytrade_sell"`)→ 現股「市價買」disabled(賣可用);個股期 blocked 契約 → 兩顆 disabled + title 同 `BLOCKED_TEXT`;即使呼叫 handler 也零請求(雙保險) | vitest |
| SC-8 | 個股期 / 期貨兩顆鈕可用時 `title="市價 = 限價貼漲/跌停 + IOC:掃對手方至成交完(簿薄時可能以漲/跌停價成交),餘量取消"`;現股可用時 `title="以市價送出:掃對手方(簿薄時可能以漲/跌停價成交);估價 = 最近成交價"`(review R4) | vitest 斷言 title |
| SC-9 | 同一顆鈕 500ms 內連按只送一次;**交錯**「市價買 → 點價 → 市價買」(500ms 內)仍只送一次市價(市價鈕獨立防抖 ref,不與點價共用單槽 `lastClick`;review R9) | vitest fake timers(連按 + 交錯兩案例) |
| SC-10 | 委託列表:`order.price_type === "market"` 的列價格欄前綴緊湊「市價」標籤(`data-testid="order-market-tag"`,`text-[0.625rem]` + `title="市價單"`),price 仍印回報價(缺 → —);limit / null 不出現標籤;**且**只對 `date` 與記錄日相符的單套用(review R7);288px 右欄下標的名仍可辨識(review R12) | vitest `CapitalOrdersList.test.tsx`;pytest `test_store.py`(note_price_type 先到 / 後到兩序)、`test_client.py`(送單成功後 store 記到 price_type;失敗不記) |
| SC-11 | 白名單全保留(§2)— 既有測試零改動即綠;**react-doctor 無新增 finding**(PriceLadder 主體已在 no-giant-component 門檻上,review R6)| `npm test` / `pytest -q` 既有案例全綠;`npx react-doctor@latest --scope changed --no-telemetry` 新增 finding = 0 |
| SC-12 | 真實環境(驗證窗口:交易日盤中;窗口外降級 = 假資料側車 + user 過目):(a) `CAPITAL_ORDER_ENABLED=false` 下三梯武裝按市價鈕 → 403 ORDER_BLOCKED,audit blocked 行帶 `price_type`(現股 market / 個股期 limit+IOC 邊價);(b) **D4 安全首單由 user 盤中執行**:低價股 1 張市價單(有庫存賣或買),群益 APP 核對成交型別 + 委託列表出現「市價」標籤 → 截圖落 `verification.md`。(b) 未做前本輪只到「自動化 + (a)」 | (a) 側車 curl / 截圖;(b) user 截圖 |

## 2. 不能破壞的既有行為白名單(reviewer / finder 逐條對照)

- W1 限價點價路徑逐 byte 不變:三梯 `clickPrice` payload(`PriceLadder.test.tsx:305-314`、`StkfutLadder.test.tsx:177-201`、`FuturesLadder.test.tsx:~150-160`)測試**不動**。
- W2 武裝 / 鎖定 / Esc / idle / 連敗 / 換標的解除語意不變(PR #58;`useFlashArm`、三梯 arm effects 不動);市價鈕成功 `send_ok`(aliveRef 守門)/ 失敗 `send_fail`(無條件)與點價**同一套守門**。
- W3 五檔市價佇列列(`LadderView.tsx:272-286/408-418`,testid `ladder-market-bid/ask`)不可點、不進 rowRefs、文案「市價」不變(`PriceLadder.test.tsx:142-193` 不動);新鈕**不在**那兩列 DOM 內。
- W4 無券鎖買側對市價買同樣生效(SC-7);交易別 pill / qty / 當沖 checkbox / 折數框 / 部位條不動。
- W5 後端 safety 三閘、mapping(`test_mapping.py:76-103, 146-158`)、`_stkfut_gates`、close.py、`source="flash"` 稽核**零改動**;audit 已帶 price_type。
- W6 `rowRefs` 置中捲動與 `centerRequest` 行為不變:新列在 scroll 容器**外**,不影響 `scrollIntoView` 目標;第一列價格不被遮蔽。
- W7 `OrderPanel`(TXO 表單)市價流程不動(fut market → `"M"`)。
- W8 `futCloseEstimate` 對外簽名與回傳值逐案不變:錨點 `FuturesPage.test.tsx:150-168`(20_520 / 25_080 / null 五案例)+ `RightRail.test.tsx:384,519`(經 closePriceOf 間接)不動;`FuturesPage.tsx:19` re-export 不動(review R2)。
- W9 `LadderView` 既有 caller / 裸 render 測試零改(新 prop 選配)。
- W10 `OrderRecord` 既有欄位與 `orders()` 排序不變;`clear()` 語意(清 agg,不清部位)不變。

## 3. Backward compat / migration
- `OrderRecord.price_type: str | None = None` 新欄:`dataclasses.asdict` 自動出 wire;舊前端忽略;`tests` 建構 `OrderRecord(` 有 default 不破。
- 前端 `CapitalOrder.price_type: "limit" | "market" | null` **必填**(契約:後端恆帶)→ 9 檔 29 處 fixture 補 `price_type: null`(機械)。
- 無 migration、無 cache version。可逆:revert commit 即回。

## 4. Out of scope
- 三梯合一 / FuturesLadder 改走 LadderView(仍 out of scope,只共用 `MarketOrderButtons`)。
- 真市價 literal `"M"` 給個股期(D3b,next-time);範圍市價 `"P"`。
- 非本 app 送出(群益 APP)的市價單辨識(回報無價格別欄)。
- 市價鈕確認框(D6 不加)、快捷鍵。
- 現股市價的估價時效標示(next-time TXO 同類坑)。

## 5. 風險節(安全敏感;reviewer 帶 security lens)

| 風險 | 分析 | 處置 |
|---|---|---|
| R-A 市價誤觸 | 兩顆鈕恆常可見、位置固定在梯頂,比點價格更容易「順手」;D6 不加確認框 | (1) 唯一閘仍是武裝態(未武裝 → hint 不送);(2) 同鈕 500ms 防抖;(3) 兩顆用**外框**樣式、不填色,與武裝鈕(填色 loss)區隔;(4) hint 明寫「<標的> 市價買 × N」(帶標的,review R5)讓誤送到哪一檔當下可見;(5) 送出後 orders 立即 invalidate → 紅方格 / 列表可刪(現股 ROD 市價可刪;IOC 邊價單即刻終態,無需刪) |
| R-B 鎖停 / 薄簿下市價成交在極端價 | 現股鎖漲停:市價買排在市價佇列後、開板才成交,成交價可達漲停(= 使用者按「市價買」的語意);個股期 / 期貨:IOC 邊價單**有對手就一路吃穿各檔位、以最壞價成交**(簿薄的個股期 / 小型期貨常態),無對手才即刻取消;現股市價在薄簿上同理(review R4)—— 這是市價語意的固有成本不是異常 | title 明寫「簿薄時可能以漲/跌停價成交」(SC-8);鎖停日五檔市價佇列列仍顯示(W3);§7 列 known-limit 讓 user 收尾看到;不另加擋 |
| R-C 估價過舊 | 現股 `last.p` 無時效標記;reset 窗會 null(→ 鎖鈕,fail-safe);若 last.p 舊而市價已跳,名目金額閘估算偏低,但成交價 = 對手價、與估價無關(D5 user 確認) | 鎖鈕 + title;金額閘偏差記 known limit;個股期 / 期貨用邊價估算恆偏保守 |
| R-D 邊價 tick 非法 | 個股期 `meta.upper` 若非法檔位 → 後端 400 BAD_TICK,錢沒動 | 前端 `snapDown/snapUp` 貼合法檔(= 梯頂 / 梯底那格);缺界 → 鎖鈕不用假想界 |
| R-E 名目金額閘的估算基準 | 個股期 / 期貨:買 = 漲停價 × 口 × 乘數,偏高 ≤ 10%(保守側);**現股:閘用估價 = `last.p`,掃單成交價高於估價時金額閘零保護**(review R4) | 個股期 / 期貨保守側;現股記 known-limit(D5 user 已確認估價只餵金額閘) |
| R-F 現股市價映射端到端未實測 | `nSpecialTradeType=1` + `bstrPrice=估價` 從未 prod 驗 | SC-12(b) user 安全首單;失敗樣態 = 群益拒單 400 BROKER_REJECTED(錢沒動)或以估價當限價成交(可接受) |
| R-G price_type 記憶與回報競態 / 跨日殘留 | 送單結果與 N 回報到達序不定;server 長跑跨日,seq 若跨日重用會把今日限價單誤標「市價」(review R7) | store 用獨立 dict(seq → (price_type, date)),`_to_record` 只在 `a.date == 記錄日` 才帶出;兩序 + 跨日不套用 pytest 各一 |
| R-H 鎖定態 × 固定位置的誤觸放大(review R5) | `flash-arm.ts:60-64` locked 時 `symbol_changed / idle_timeout / left_view` 皆不解除武裝 → 「A 檔鎖定 → 切到 B 檔 → 順手點梯頂」= 對 B 檔直送市價單,無確認(D6) | 不推翻 D6;hint 帶標的(SC-2/3/4);兩顆鈕外框樣式與武裝鈕填色區隔;§7 列出讓 user 看到此乘積效應;鎖定態語意本身是 PR #58 user 拍板 |
| R-I 既有遠價防線在新路徑不適用(review R10) | 三梯 ±5% 外價位反灰不可點(`stock-tick.ts:155` / `futures-ladder.ts` CLICK_BAND)、唯一送貼漲跌停價的既有路徑 = 平倉且**一律過確認框**;市價鈕是「遠價 + 無確認框」的第一個組合 | 市價 / IOC 語意下可接受(使用者按的就是「掃到成交」);§7 列出;不加擋 |

## 6. Diff 級章節(逐檔;三類標記)

### 🔵 純重構(先做,行為零變)
1. `frontend/src/lib/futures-ladder.ts`:新增 `export function edgeMilli(side: "buy"|"sell", upper: number|null, lower: number|null): number|null`(buy→upper、sell→lower、缺→null);`futCloseEstimate` 改為 `edgeMilli(pos.qty > 0 ? "sell" : "buy", prod.upper, prod.lower)`,其餘判定不變。測試:`futures-ladder.test.ts` 加 `edgeMilli` 案例;既有 futCloseEstimate 案例(`FuturesPage.test.tsx:150-168`)不動 → 綠。
   `frontend/src/lib/flash-send.ts::settleFlashSend`(定義見 🟢-2)抽出後,**三梯 `clickPrice` 的 then/catch 改呼叫它**(語意逐字沿 PriceLadder.tsx:292-311;既有守門 / failStreak / hint 測試不動即綠)— 同屬 🔵 commit 1。

### 🟢 新功能 `[amendment 2026-08-17: review R5/R6/R7/R8/R9/R11/R12]`
2. `frontend/src/lib/flash-send.ts`(新;純函式,review R6 — 三梯主體不再各長一份 then/catch):
   ```ts
   export interface FlashSendCtx {
     alive: () => boolean;                       // aliveRef.current
     dispatch: (a: { type: "send_ok" | "send_fail" }) => void;
     showHint: (text: string) => void;
     okText: string;                             // 成功 hint
   }
   /** mutateAsync 尾段的唯一守門:成功 → alive 才 send_ok+hint;失敗(ok:false / throw)→ 無條件 send_fail + hint。 */
   export function settleFlashSend(p: Promise<{ ok: boolean; message: string }>, ctx: FlashSendCtx): void
   ```
   語意逐字沿 PriceLadder.tsx:292-311 現行守門(W2)。**本輪三梯的 `clickPrice` 也改呼叫它**(🔵 行為零變 — 這是 R6 壓 react-doctor 門檻的手段;既有 payload / 守門測試不動即綠)。
   ```ts
   export type MarketBtnState = { buyDisabled: boolean; sellDisabled: boolean; buyTitle: string; sellTitle: string };
   export function marketButtonState(input: {
     kind: "stock" | "stkfut" | "futures";
     estimateMissing: boolean;   // 現股 last===null;個股期 last===null || edge===null;期貨 centerMilli===null || edge===null || contract===null
     buyLocked?: boolean;        // 現股無券
     blocked?: boolean;          // 個股期 BLOCKED
   }): MarketBtnState
   ```
   title 三態:blocked → `BLOCKED_TEXT`(常數搬進本檔 export,StkfutLadder 改 import);estimateMissing → 「無成交價,市價鈕鎖定」;buyLocked → 買鈕「無券當沖不可買進」;可用 → SC-8 文案(stock / 非 stock 各一)。測試 `lib/flash-send.test.ts`。
3. `frontend/src/components/stock/MarketOrderButtons.tsx`(新):
   ```ts
   interface Props { onMarket: (side: "buy" | "sell") => void; state: MarketBtnState }
   ```
   render:`<div data-testid="ladder-market-buttons" className="flex items-stretch gap-1 border-b border-line px-1 py-1">` + 兩顆 `button type="button"`(文字「市價買」「市價賣」,`title` 來自 state),class:`flex-1 rounded border py-1 text-xs font-bold` + 買 `border-bull text-bull hover:bg-bull/10` / 賣 `border-bear text-bear hover:bg-bear/10` + `disabled:cursor-not-allowed disabled:opacity-40`。**只用 bull / bear / line token**,無新色、無動效;外框不填色(與武裝鈕填色 loss 區隔,R-A/R-H)。
4. `frontend/src/components/stock/LadderView.tsx`:Props 加 `ladderTop?: ReactNode`;渲染於武裝列 `</div>`(:261)之後、`rows.length === 0 ? … : scroll` 之前(rows 為空時仍渲染 → 「無資料」上方也有鈕,鈕自身由 container 鎖)。
5. `frontend/src/lib/stkfut.ts`:新增 `export function stkfutMarketEdgeMilli(side, meta: {upper: number|null; lower: number|null} | null): number | null`:upper/lower null 或 ≤ 0 → null;buy → `snapDown(upper)`、sell → `snapUp(lower)`(import 自 `stock-tick`)。測試 `lib/stkfut.test.ts`。
   `frontend/src/lib/futures-ladder.ts`:另加 `export function futMarketEdgeMilli(side, upper, lower): number | null` = `edgeMilli` 後 buy `Math.floor(e/FUT_TICK_MILLI)*FUT_TICK_MILLI` / sell `Math.ceil(...)`(review R8;與 buildFuturesLadder :132-133 同口徑)。測試 `futures-ladder.test.ts`。
6. `frontend/src/components/stock/PriceLadder.tsx`:
   - `marketOrder(side)`:`touchIdle()`;無券且 buy → return;未武裝 → hint「未武裝 — 市價不送單」(自清);`last === null` → return(雙保險);防抖用**獨立** `lastMarketClick` ref(key = side;review R9);`settleFlashSend(submitStock.mutateAsync({stock_no: code, buy_sell: side, price: last.p/1000, qty, price_type:"market", time_in_force:"ROD", trade_kind: tradeKind, source:"flash"}), {..., okText: `已送 ${code} 市價${side==="buy"?"買":"賣"} × ${qty}`})`。
   - `ladderTop={<MarketOrderButtons onMarket={marketOrder} state={marketButtonState({kind:"stock", estimateMissing: last===null, buyLocked: tradeKind==="daytrade_sell"})} />}`。
   - `clickPrice` 的 then/catch 改 `settleFlashSend`(🔵,語意不變)。
7. `frontend/src/components/stock/StkfutLadder.tsx`:同上模式;`edgeFor = (side) => stkfutMarketEdgeMilli(side, meta)`;`estimateMissing = last===null || edgeFor("buy")===null || edgeFor("sell")===null`;`marketButtonState({kind:"stkfut", estimateMissing, blocked})`;payload `{tc4_symbol: stkfutTc4Symbol(contract), buy_sell, price: edge/1000, qty, price_type:"limit", time_in_force:"IOC", day_trade: dayTrade, source:"flash"}`;okText `已送 ${exchangeContract ?? code} 市價賣 × N 口`(契約碼缺時退回股號)。
8. `frontend/src/components/futures/FuturesLadder.tsx`:`edgeFor = (side) => futMarketEdgeMilli(side, state?.upper ?? null, state?.lower ?? null)`;`estimateMissing = contract===null || centerMilli===null || edgeFor("buy")===null || edgeFor("sell")===null`;payload `{tc4_symbol: `TC.F.TWF.${product}.HOT`, buy_sell, price: edge/1000, qty, price_type:"limit", time_in_force:"IOC", day_trade, source:"flash"}`;okText `已送 ${contract} 市價買 × N 口`;JSX:`<MarketOrderButtons …/>` 放武裝列區塊 `</div>`(:409)之後、`rows.length === 0 ? …` 之前;`clickPrice` 亦改 `settleFlashSend`(🔵)。
9. 後端 `copycat/capital/models.py`:`OrderRecord.price_type: str | None = None`(註:本 app 送出才知道;回報無此欄;跨日不套用)。
10. 後端 `copycat/capital/store.py`:`self._price_types: dict[str, tuple[str, str]] = {}`(seq → (price_type, date YYYYMMDD));`note_price_type(seq_no: str, price_type: str, date: str) -> None`(加鎖);`_to_record` 帶 `price_type` 僅當 `_price_types[a.seq_no][1] == a.date`(a.date 為 None 亦不帶;review R7);`clear()` **不清** `_price_types`(重播回報時 agg 重建、intent 仍有效)。
11. 後端 `copycat/capital/client.py`:`submit_stock_order` / `submit_future_order` 拿到 result 後 `if result.ok and result.seq_no: self.store.note_price_type(result.seq_no, req.price_type, _today_ymd())`(`_today_ymd` = 本機 `time.strftime("%Y%m%d")`;平倉路徑同樣經過此處 → 現股平倉 market 也標)。測試 `test_client.py`(成功記錄 / 拒單不記)、`test_store.py`(note 先於 N / N 先於 note / 跨日不套用 / clear 後重播仍套用)。
12. `frontend/src/types.ts`:`CapitalOrder.price_type: "limit" | "market" | null`;fixture 補欄。

### 🔴 行為改動(既有測試先紅)
13. `frontend/src/components/capital/CapitalOrdersList.tsx`:`order.price_type === "market"` → 價格欄渲染 `<span data-testid="order-market-tag" title="市價單" className="mr-0.5 text-[0.625rem] leading-none text-ink-muted">市價</span>{priceText}`(緊湊,review R12);改價 input placeholder / 確認框「原委託」沿用 `priceText`(不加標籤)。既有測試:`CapitalOrdersList.test.tsx` 新增「市價單列顯示標籤 / limit 與 null 不顯示」案例先紅;既有價格欄斷言若用 exact text 需檢查(預期不動 — 現有 fixture 無 market)。

### 測試清單
- 該紅(新增):SC-1~SC-10 對應案例(vitest 三梯 + OrdersList + lib 三支 flash-send / stkfut / futures-ladder;pytest store 四案例 + client 兩案例)。
- 不該紅:§2 W1–W10 對應既有測試全部(含 `FuturesPage.test.tsx:150-168`、`RightRail.test.tsx`);`test_mapping` / `test_safety` / `test_close` / `test_client` 既有案例;`OrderPanel.test.tsx`。
- 若既有測試紅 → 打到白名單,回 spec。
- gate 另含 `npx react-doctor@latest --scope changed --no-telemetry`(新增 finding = 0)。

### Commit 切分(實際順序:🔵 → 🟢 後端欄位 → 🔴 前端標籤 → 🟢 三梯鈕;review R11 修標題)
1. 🔵 refactor(frontend): edgeMilli 抽出、futCloseEstimate 改呼叫;settleFlashSend 抽出、三梯 clickPrice 改呼叫 [refactor](行為零變,既有測試不動即綠)
2. 🟢 test(capital): store/client price_type 記憶 [red] → 🟢 feat(capital) [green]
3. 🔴 test(frontend): OrdersList 市價標籤 [red] → 🔴 fix(frontend) [green](含 types.ts 欄位 + fixture 補欄)
4. 🟢 test(frontend): flash-send/marketButtonState + stkfut/futures edge helpers + MarketOrderButtons + LadderView 插槽 + 三梯市價鈕 [red] → 🟢 feat [green](可依三梯拆 2-3 對)
(🔴 在 🟢 4 前的原因:OrdersList 標籤依賴 types.ts 欄位;三梯鈕不依賴列表。)

## 7. `[auto-default]` 與 known-limit 清單(收尾回報列出)
- AD-1 個股期/期貨市價 = 前端直送 `limit/IOC/邊價`,後端零改(理由 current-state §3)| reason: 後端「market → 邊價」會改 OrderPanel `"M"` 語意且要反查漲跌停;**平倉驗收不覆蓋此新鏈路**(不同路由/閘/倉別),首驗點 = SC-12。
- AD-2 個股期邊價 snap 到現股 tick 表(梯頂/梯底那格);期貨邊價 floor/ceil 到 FUT_TICK(與 buildFuturesLadder 同口徑)| reason: 避免 BAD_TICK / 券商退單。**known-limit**:個股期平倉(RightRail:256)用未 snap 邊價,兩者可能差一檔 → next-time 收斂 snap 口徑。
- AD-3 期貨鎖鈕條件含 `contract===null`(合約未解析)| reason: 與武裝鈕同閘,送單層本就拒。
- AD-4 未武裝 hint 文案「未武裝 — 市價不送單」;成功 hint 帶標的(股號 / 契約碼)。
- AD-5 委託列表「市價」標籤只對本 app 送出、且 `date` 相符的單(store 記憶);個股期/期貨邊價單顯示為一般限價 | reason: 回報無價格別欄;不偽造。
- AD-6 `CapitalOrder.price_type` 前端型別必填(null 合法)| reason: 契約後端恆帶。
- AD-7 MarketOrderButtons 落 `components/stock/`;送單守門 / 鈕三態抽 `lib/flash-send.ts` 純函式(react-doctor 門檻)。
- AD-8 兩顆鈕未武裝時**可按**(按 → hint),不 disabled | reason: 與價格格一致、SC-5 原文。
- AD-9 現股市價 payload 維持 `market + ROD`(review R1 REFUTED:TWSE 逐筆交易市價 ROD 合法,鎖停日 15966 張留存簿中的「市價佇列」即為證;skill 記載的「市價限 IOC/FOK」是期交所規則)。端到端仍以 D4 首單為準。
- **KL-1(review R4)**:市價 / IOC 邊價在薄簿上會掃至極端價成交,是市價語意的固有成本;現股方向金額閘用 `last.p` 對掃單零保護。
- **KL-2(review R5)**:鎖定態下換標的武裝不解除 × 梯頂固定位置 → 誤觸半徑最大;本輪以 hint 帶標的 + 外框樣式緩解,不加確認框(D6)。
- **KL-4(code review IMPL-5/F6)**:委託列表「市價」標籤的日期比對用本機日曆日 vs 回報委託建立日,夜盤跨午夜 / 盤後預約單的 `date` 語意未實證 → 不符時只缺標籤不誤標(fail-safe);交易日口徑收斂留 next-time。
- **KL-3(review R10)**:市價鈕是三梯上第一個「遠價 + 無確認框」路徑(±5% 反灰、平倉確認框兩道既有防線在此不適用)。

## 8. Edge cases(≥ 3)
- E1 現股 `last` 有值但 `meta` 缺 → 現股市價鈕**可用**(現股不需邊價);個股期同況 → 鎖(需邊價)。
- E2 送單中切標的:promise 晚到,`send_ok` 受 aliveRef 守門、`send_fail` 無條件(與點價同)。
- E3 rows 為空(無資料)但 last 有值(理論上不可能,buildLadder anchor 有值即有 rows)→ 鈕仍依 last 判定;不特判。
- E4 個股期 `meta.upper` 為 0(後端缺值以 0 給)→ 視同缺 → 鎖。
- E5 note_price_type 先於 N 回報到達 → `_to_record` 仍能帶出(dict 獨立於 agg)。
- E6 群益拒單(BROKER_REJECTED)→ `catch` 分支 `send_fail` + hint 繁中文案(tradeErrorText),不記 price_type。

---
self_review_head: 5dacee8f  (code review r1 兩 lens + fix 波 4 commits 後;收尾增量 review 依此判)
