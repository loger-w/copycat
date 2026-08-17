# 2026-08-17 使用者回饋第三批:分類 + 五輪 /mod 執行 prompt

> 來源:2026-08-17 user 實戰回饋 6 條(個股(期) 3 條 + 台股綜合 2 條 + 相關係數 1 問)。
> 四路 sonnet 調研已落事實(檔案:行號內嵌各輪 prompt,快照 = master `de44d49b`)。
> **尚未實作**;拍板項(§1)有 user 回答以回答為準,沒回答走 `[auto-default]`。
> UI 輪一律載入 `frontend-design` + `bencium-controlled-ux-designer`(前者管細節精緻度,後者管
> 「設計決策先問再做」;**本專案為既有看盤 UI,一致性優先於「大膽新美學」** — 不換字體/不加
> 動效/不引入新色票,只在既有 token 內做選擇;bencium 的「先問」= 本檔 §1 拍板表)。

## 0. 分類總表

| # | 回饋 | 類型 | 輪 | 級 | 判定依據 |
|---|---|---|---|---|---|
| 個1 | 閃電下單加「市價買 / 市價賣」 | 🟢 新功能 + 🔴(/mod,**安全敏感**) | R1 | M | 型別/後端 `price_type:"market"` 全鏈已存在,三梯 `clickPrice` 寫死 `"limit"`;缺 UI 觸發點 + 閘用估價;期貨/個股期市價 literal 從未實測 |
| 個2 | 分時圖標出使用者買賣成交點 | 🟢 新功能(/mod) | R2 | M | `CapitalStore._Agg` 把逐筆 D 回報聚合掉,只剩 `avg_fill_price`+最新事件時間 → 精確版要後端新增逐筆成交列;圖層幾何工具現成(`minuteKey`/`minuteToX`/`toY`、高低點標記範式) |
| 個3 | 自選清單 / 單檔 / 群組卡顯示倉位與損益 | 🟢 新功能(/mod) | R3 | M | 部位資料與 `positionEcon()`(含費稅損益)已在閃電梯內;三處 UI 目前零倉位資訊;sec 用股號 / 個股期用契約碼兩套鍵 |
| 綜1 | 加權/櫃買分時圖直接改用個股分時圖 | 🔴 UI 換元件(/mod) | R4 | L | `MarketChart.IntradayChart` 是獨立自繪(無 hover/readout/副圖),`IndexSeries.minutes` 只有 HHMM→收盤價、**無量** → 需 adapter + core 可注入 overlay;PANE_FRAMES 常數重算 |
| 綜2 | 左欄雙圖縮小、騰落線增高 | 🔴 UI 佈局(/mod) | R4 | S | 騰落線是固定 `h-24` 不參與 flex 分配;雙圖 `min-h-80`/`min-h-48` 地板算式連動 → 與綜1 同輪(換元件後 chrome 高度才定,避免地板算兩次) |
| 相1 | 達錢有沒有韓指 / 日經即時資料 | 事實問答 → 🟢 config 加腿(/mod) | R5 | S | **日經有**(TC4 Fut 樹 OSE `NK225`/`NK225M`/`NK225MC`/`NK400` + SGX `NK` + CME `NKD`);**韓指無**(2026-06-30 全量 dump 17 個交易所段無 KRX、三檔 catalog 零命中 KOSPI);加腿只改 `configs/correlation.json`(SC-8 契約已鎖) |

沒有一條是「線上 bug」(全是行為新增/改動),故全走 `/mod`;user 若指某條實為 bug(例如綜1
背後是加權圖畫錯),請點名,該輪改走 `/bug`(紅測試先行)。順序:**R1 → R2 串行**(同動
`capital/store.py`、`useCapital.ts`、`CapitalOrdersList`),R3 / R4 / R5 互不相依可並行 worktree
(ops-discipline 三險照過)。R1 是安全敏感輪:reviewer 帶 security lens、change-spec 必含
「市價單誤觸 / 鎖停市價成交在極端價」風險節。

## 1. 拍板清單(bencium 協定:設計決策先問;沒回答走 `[auto-default]`)

| # | 決策 | 選項 | `[auto-default]` | 拍板結果 |
|---|---|---|---|---|
| D1 | 市價鈕位置 | (a) 放武裝列 `armControls` 插槽,交易別 pill 右側「市價買」「市價賣」兩顆並列(買 bull / 賣 bear outline,武裝態才可按,未武裝 disabled+hint);(b) 梯頂一顆「市價賣」、梯底一顆「市價買」貼近各自方向 | **(a)**(與現有 pill/武裝列同語法,不新增視覺區塊;(b) 會與五檔「市價佇列列」`marketBidQty/marketAskQty` 在空間上撞在一起造成語意混淆) | |
| D2 | 市價鈕涵蓋哪幾座梯 | (a) 現股 `PriceLadder` + 個股期 `StkfutLadder`(user 說的是個股(期)頁);期貨梯 `FuturesLadder` 記 next-time;(b) 三梯一起 | **(a)** | |
| D3 | 個股期市價送法(期交所市價 literal `bstrPrice="M"` 從未在 test/prod 實測,`docs/research/2026-07-28-skcom-typelib.md:45-47`) | (a) 個股期「市價」= **限價貼漲跌停 + IOC**(沿 `close.py:58-86` 期貨平倉既有 amendment 手法,不新增未實測 COM 路徑;鈕文案仍叫市價,tooltip 註明實作);(b) 真市價 literal `"M"`(mapping 現成 `mapping.py:215-219`),首單由 user 盤中以 1 口低價個股期真送驗 | **(a)**(零新未驗路徑;(b) 留 next-time,prod 驗過 `"M"` 可送後切回) | |
| D4 | 現股市價映射(`nSpecialTradeType=1` + `bstrPrice` 仍塞估價,`mapping.py:186-199`;端到端未實測) | 照映射送;R1 verification 節列「prod 安全首單」步驟:盤中挑低價股 1 張市價賣(有庫存)或買,APP 核對成交型別 | 照此 | |
| D5 | 市價單閘用估價與擋單 | 估價 = 梯面最近成交價 `last?.p`(個股期同);`p==null`(尚無成交/斷線 reset 窗)→ 兩顆鈕 disabled + title「無成交價,市價鈕鎖定」(同 `OrderPanel.tsx:216-228` 模式);payload `price=估價, price_type="market"`,後端 `safety._bad_price`/max_amount 沿用估價 | 照此 | |
| D6 | 市價鈕要不要多一層確認 | (a) 與限價同:武裝態一鍵送(閃電語意);(b) 市價多一個 confirm | **(a)**(鎖定/武裝已是唯一閘;確認框破壞閃電) | |
| D7 | 買賣點精度 | (a) 近似:每張委託 `avg_fill_price @ time`(最新事件時間)一個點,不動後端;(b) 精確:後端 store 保留每筆 D 型成交事件 `(seq_no, time, price, qty, buy_sell, stock_no)`,新增 `GET /api/capital/fills`(當日),WS `capital_order` 事件已可 invalidate,前端每筆一個標記 | **(b)**(分批成交是常態,近似版會把多筆疊在同一時間點失真;store 只留當日、記憶體結構小) | |
| D8 | 買賣點樣式 | 主圖上 ▲(買,bull 色)/▼(賣,bear 色)實心小三角,尖端指向成交價,x=成交分鐘;同分鐘同向多筆合併一個標記,hover readout 加「成交 買 n@價」欄;新增 `useChartToggles` 鍵 `fills`(預設開,新鍵免 bump 規則 `useChartToggles.ts:22-26`);群組卡 `variant="card"` 同畫(小尺寸)| 照此;若 user 偏好圓點/橫線,改樣式不改資料流 | |
| D9 | 倉位/損益顯示位置與內容 | (a) 自選列:有倉位才顯示,第二行右緣「n張 ±x.x%」(色隨損益正負,tooltip 帶均價/損益元);單檔 header(`StockPage.tsx:65-100`):新一格「持股 n張 · 均價 X · 損益 ±元(±%)」;群組卡 `QuoteCell` 下加一行同款;(b) 自選列只加色點(有倉),細節放 tooltip;單檔/群組同 (a) | **(a)**(240px 側欄第二行已是妥協,只在有倉列多一段,零倉零視覺負擔) | |
| D10 | 損益口徑 | (a) 含費稅(`ladder-position.ts::positionEcon`,與閃電梯部位列一致);(b) 名目 `pnl_base` | **(a)**(同一數字不能兩處不同);`discount` 來源沿閃電梯現用值(spec 要 grep 出實際來源,若是 hardcode 常數則三處共用同一常數) | |
| D11 | 綜合頁分時圖換元件範圍 | (a) 完整 `IntradayChartCore`:寫 `indexSeriesToAccum()` adapter + core 加 `overlay` 注入 prop(取代內建 `useStockOverlay`)+ `mode:"index"`(關 VP/外內盤/試撮/漲跌停亮燈文案),保留 hover 十字線 + readout(時間/點位/漲跌%)+ 昨收線 + 均價線 + CDP/MA(加權)+ 高低點 + 現價圈;量能副圖依 R4 前置 probe(IX0001 push 有 `TradeQuantity/TradeVolume` 鍵但值未驗)決定開或關;(b) 只把 hover/readout 與樣式移植進 `MarketChart` | **(a)**(user 原話「直接使用個股的分時圖」) | |
| D12 | 左欄高度分配 | (a) 雙圖 `min-h-80`→約 `min-h-56`(chrome 依新元件重算)、騰落線 `h-24 shrink-0`→`flex-1 min-h-40` 參與 flex 分配(`useContainerSize` 已在內,只是 wrapper 鎖死);(b) 兩者皆固定值:雙圖 `min-h-56`、騰落線 `h-40` | **(a)**(騰落線隨螢幕吃剩餘高,1080p / 864p 都不再是 96px 一條) | |
| D13 | 日經腿合約 | (a) `TC.F.OSE.NK225M.HOT` 小日經(流動性佳、秒級取樣穩);(b) `TC.F.OSE.NK225.HOT` 大日經;(c) `TC.F.SGX.NK.HOT` SGX 版 | **(a)**;label「小日經」;river 調色盤補第 7 組色 | |
| D14 | 韓指 | TC4 目前無 KRX 段 → **做不到**;是否要記 next-time「TC4 上架 KOSPI200 追蹤」(比照 TSM CME SSF 先例 `tc4-market-facts:155-159`) | 記 next-time,不做替代品 | |

## 2. 五輪 prompt 全文

---
### R1 `/mod 閃電下單(現股 + 個股期)加「市價買 / 市價賣」兩顆鈕`

```
/mod 個股(期)頁閃電下單加「市價買」「市價賣」:現股 PriceLadder 與個股期 StkfutLadder 的武裝列
各加兩顆鈕(D1 a),武裝態一鍵送市價單(D6 a),估價 = 梯面最近成交價、無成交價鎖鈕(D5)。
期貨梯 FuturesLadder 不在本輪(D2 a,記 next-time)。**安全敏感**:change-spec 必含「市價誤觸 /
鎖停下市價成交在極端價 / 估價過舊」風險節,reviewer 帶 security lens;三類分 commit。
UI 輪:載入 frontend-design + bencium-controlled-ux-designer;沿既有 pill / 武裝列樣式,鈕色只用
bull/bear token,不新增色。

已調研事實(重 grep 驗證行號):
【型別/後端已支援】frontend/src/types.ts:118-127 CapitalStockOrderBody.price_type?:"limit"|"market"
(:123)、:129- CapitalFutureOrderBody(:134);copycat/capital/models.py:14 PriceType、:50/:62 預設
"limit";server/capital_api.py:66/:77 `price: float` **必填**(市價也要帶閘用估價)、:68/:79
price_type、:159-174 _stkfut_gates 已對 market 跳過 tick 檔位檢查(:163-164,172-174);
safety.py:40-45 _bad_price「market 單 price 是閘用估價,必須 >0」、:48-57 名目金額閘一視同仁;
mapping.py:50 _SPECIAL{market:1,limit:2}、:186-199 現股市價 = nSpecialTradeType=1 且 bstrPrice 仍
塞估價字串(:192)、:202-232 期貨市價 = bstrPrice="M"(:216)+ ROD 靜默升 IOC(:217-219,
client.py:716-720 訊息前綴);close.py:58-86 build_future_close_order 強制 limit 貼漲跌停+IOC(:83)
= 個股期「市價」D3(a) 要沿用的手法(抽共用 helper 給送單路徑,不複製);store.py:158-186
_to_record price 來自回報;CapitalOrdersList.tsx:103 priceText 無「市價」標籤。
【三梯送單入口】PriceLadder.tsx:261-312 clickPrice(payload :282-291 `price_type:"limit"` 寫死;
武裝守門 :264-267;qty :215/219;TradeKindPills :64-93 經 armControls 塞 LadderView :430-438;
buyLocked :377 無券鎖買側 → 市價買同樣要鎖);StkfutLadder.tsx:148-193 clickPrice(payload
:169-176;blocked=isOrderBlocked :121 雙保險 :150;armControls 是當沖 checkbox :273-287);
LadderView.tsx:93,236 armControls 插槽、:277-286/:408-418 是五檔「市價佇列」顯示列(不可點,
:274-276)— **與使用者下市價單是兩件事,文案要區隔**(佇列列保持「市」小標,新鈕文案「市價買」
「市價賣」);:355-389 買賣鈕綁 onClickPrice(priceMilli, side) 簽名 → 市價走新 prop
`onMarketOrder(side)`,不塞假價格。
【估價來源】現股 last?.p / 個股期同(StkfutLadder 用的五檔/分時現價變數 spec 要指名);reset 窗
風險見 docs/next-time.md:489-496(TXO 估價消失數分鐘的同類坑)。可抄樣板:OrderPanel.tsx:45,
57-58,72,216-228,291(kind/marketEstimate/disabled/確認文案)。
【測試該紅】PriceLadder.test.tsx:305-314(payload 鎖 limit — 不該變,新增市價案例另寫)、:142-193
「市價單列(round6 項4)」describe 鎖的是佇列列不可點(:188)— **不能被新鈕誤破**;
StkfutLadder.test.tsx:195;OrderPanel.test.tsx:153,192-216,270-283 是市價 UI 測試樣板;
後端 tests/capital/test_mapping.py:76-103,146-158、test_safety.py:139-144、
test_client.py:425-446 全保留;個股期 D3(a) 新增 mapping/gate 測試:market 進來 → 送出
limit@漲跌停+IOC(現股漲跌停價來源 = 五檔 meta upper/lower,個股期 = 契約 upper/lower)。
【文件】docs/next-time.md:184-191/:586-588 群益市價事實(範圍市價 "P" 候選、TXO 估價舊價
風險)、tc4-market-facts SKILL.md:54-69 鎖停市價佇列語意。

白名單:限價點價路徑逐 byte 不變(三梯 payload 測試不動);武裝/鎖定/Esc/idle/連敗語意不變
(PR #58);無券鎖買側對市價買同樣生效;交易別 pill、qty、當沖 checkbox 不動;後端 safety
三閘不動、source="flash" 稽核不變(市價單 audit 帶 price_type 已有);期貨梯不動。
成功條件(畫面可指認):武裝後「市價買」一鍵送出 → 委託列表出現該單且 price_type=market
(現股 nSpecialTradeType=1;個股期送出 limit@漲跌停+IOC 並在 audit 看到);無成交價時兩顆鈕
灰且 title 說明;未武裝按下只出 hint 不送;pytest/vitest 新增案例。真實環境:
CAPITAL_ORDER_ENABLED=false 先驗 UI 與 payload(被總開關擋),再由 user 盤中做 D4 安全首單
(低價股 1 張)— 首單結果與 APP 截圖落 verification。
三類:🔵 抽 close.py 貼漲跌停+IOC helper 給送單共用(行為不變)→ 🟢 兩梯市價鈕 + payload
分流 → 🔴 CapitalOrdersList 市價單顯示「市價」標籤(price 仍印回報價)。
```

---
### R2 `/mod 個股(期)分時圖疊「當日買賣成交點」(後端逐筆成交列 + 前端標記 + toggle)`

```
/mod 個股(期)單檔與群組圖牆分時圖上標出使用者當日成交點:後端保留逐筆成交事件並開
GET /api/capital/fills(D7 b),前端主圖畫 ▲/▼ 標記(D8),useChartToggles 加 `fills` 鍵預設開。
**前置:R1 已 merge**(同動 store.py / useCapital.ts)。UI 輪:載入 frontend-design +
bencium-controlled-ux-designer;標記只用 bull/bear token,尺寸沿 chart-extreme.ts INTRADAY_MARK。

已調研事實:
【後端】models.py:110-132 OrderRecord 只有 avg_fill_price + 最新事件 time(秒、非逐筆);
reply.py:41-60 ReplyRecord 單筆回報有 price(idx11)/time(idx24)/qty(idx20,Type=D 為成交量);
store.py:51-69 _Agg 累加吃掉逐筆、:95-156 apply_reply(:128-134 D 事件累加)、:158-186 _to_record;
client.py:295-316 _handle_reply 是唯一逐筆入口;capital_api.py:212-221 GET orders/positions
(無 fills);audit.py:22-25 是動作審計非成交。設計:store 加 `_fills: list[FillRecord]`
(seq_no/stock_no/buy_sell/price/qty/time/date/market;只留當日,rollover 清)、
`fills()`、GET /api/capital/fills → {fills:[...]};WS 既有 capital_order 事件足以 invalidate
(useCapital.ts:119,131-141 200ms debounce);複合鍵/契約碼語意沿 ladder-lots.ts:43-56
(現股=股號、個股期=期交所契約碼 CDFI6 → 前端要用 exchange_product 反查對到 code,
capital_api.py:192-201 有反查示範;spec 決定反查放後端 fills 回傳附 `code` 欄位,前端零映射)。
【前端】useCapital.ts:157-173 useCapitalOrders(30s)/Positions(15s)樣板 → 新 useCapitalFills;
時間→x:stock-accum.ts:102-104 minuteKey("HH:MM:SS")+ stock-intraday-svg.ts:79-81 minuteToX;
價→y:buildIntradayGeometry(:320-488)toY;標記範式:StockIntradayChart.tsx:387-421 高低點
(chart-extreme.ts INTRADAY_MARK/markCenterX/markLabelY/markTone);IntradayChartCore props
:634-643(page/card 共用,寫一次兩處生效;CardIntradayChart.tsx:26-53 群組卡)、ChartStatic
memo :112-480(標記進 memo 要把 fills 納入 deps)、readout :762-787 加欄;
useChartToggles.ts:5-13,32 鍵表、:17-31 版本規則(新鍵免 bump);stkfut 同元件(StockChart.tsx:157
stkfut=true);**期貨 tab FuturesChart.tsx 是另一套幾何,不在本輪**(記 next-time)。
【測試】StockIntradayChart.test.tsx / .variant.test.tsx、stock-intraday-svg.test.ts、
chart-extreme.test.ts、useChartToggles.test.ts、GroupGridView.toggle/memo.test.tsx(memo 不可破);
後端 tests/capital/test_store.py、test_reply.py、tests/server/test_capital_api.py。

白名單:orders/positions 端點 shape 不變;ladder-lots 聚合(三梯掛單/已成交徽章 PR #46)不變;
既有 overlay(VWAP/CDP/MA/VP/POC/高低點/現價圈)與 toggle 值不變;群組卡 memo 契約
(GroupGridView.tsx:107 每秒 re-render 警示)不破 — fills 以穩定 identity 傳入。
成功條件(畫面可指認):盤中成交一筆後 ≤1s 圖上出現 ▲/▼ 於正確分鐘與價位,hover 顯示
「成交 買 2@123.5」;同分鐘同向多筆合併顯示總量;toggle 關閉即消失;群組卡同步;個股期
成交對到正確卡片。真實環境:CAPITAL_ORDER_ENABLED=false 下用 store 注入 fake reply
(tests/capital fixture 樣板)驗前端;盤中 user 真成交後截圖過目。
三類:🟢 後端 fills 列 + endpoint → 🟢 前端標記 + toggle → 🔵 readout 欄整理(若需)。
```

---
### R3 `/mod 自選清單 / 單檔 header / 群組卡顯示使用者倉位與含費稅損益`

```
/mod 個股(期)三處顯示使用者倉位與損益:自選列(有倉才顯示「n張 ±x.x%」,tooltip 均價/損益元)、
單檔 header 新一格「持股 n張 · 均價 X · 損益 ±元(±%)」、群組卡 QuoteCell 下一行同款(D9 a);
損益口徑 = 含費稅 positionEcon,與閃電梯部位列同一數字(D10 a)。UI 輪:載入 frontend-design +
bencium-controlled-ux-designer;色只用 bull/bear 三態規則(GroupGridView.tsx:69-76 同構)。

已調研事實:
【資料】useCapital.ts:166-173 useCapitalPositions(15s + WS capital_position 200ms debounce,
全域單一份 query,TanStack 去重);models.py:135-148 Position{market,stock_no,qty(空方負),
avg_price(可能 None,靠損益試算回填),kind,pnl_base(快照非即時),pnl_base_price,pnl_cost};
balance.py:1-18 三段鏈、:70-90 merge_fut_positions;client.py:378-455 鏈 + :338-339
_mark_balance_dirty(0.5s)+ :355-368 in-flight 守門(PR #46);store.py:223-250 set_positions
複合鍵 (stock_no, kind)。
【計算】ladder-position.ts:54-84 positionEcon(qty, avgPrice, lastMilli, discount, kind)
含手續費 0.1425%×折數 + 證交稅 0.3% + 借券費;:111-118 secPositionsOf;PriceLadder.tsx:139-150,
196,231-238 positionRows(avg_price 單位元 ×1000)、StkfutLadder.tsx:53-57 contractPositions
(契約碼比對!)、:290-300;**discount 來源 spec 要 grep 出**(常數 or UI 輸入),三處共用同源。
【顯示點】WatchlistSidebar.tsx stockRow :362-(quotes 只有 WatchlistQuote{p,chg_pct,vol,ref,upper,
lower,no_data,trial} useStockStream.ts:18-29;240px 兩行式 :393-397 註解);群組標題 avgPct
(watchlist-avg.ts:20-38,純報價平均,不動);StockPage.tsx:65-100 header;GroupGridView.tsx:74-103
QuoteCell、:112-203 GroupCard(:107 每秒 re-render 警示 → 損益算式 useMemo 依 positions
identity + quotes[code].p,不逐卡 new object)。
【鍵映射】自選 code 是股號;個股期部位 stock_no 是契約碼 → 純前端做「契約碼 → 股號」需要
產品對照;現有反查只在後端 mapping.py exchange_product_of。設計選項:(a) 後端
/api/capital/positions 回傳每列附 `code`(股號;sec=stock_no,fut=解析契約碼)— 與 R2 fills 附
code 同一手法、同一 helper;(b) 前端自建對照。**建議 (a)**,寫進 change-spec。個股期倉位顯示在
自選列/群組卡:同一股號的現股倉與個股期倉分兩段「現 n張 / 期 n口」。
【測試】ladder-position.test.ts、useCapital.test.tsx、WatchlistSidebar.test.tsx(+dropcollapsed)、
GroupGridView.test.tsx(+geometry/memo/toggle)、StockPage.test.tsx;後端 test_capital_api.py。

白名單:閃電梯部位列與數字不變(同函式);自選列既有欄位/亮燈/群組平均漲幅/拖曳/上限 50 不變;
群組卡 memo 契約不破;無倉位時三處零視覺變化(不佔位);positions 輪詢頻率不變。
成功條件(畫面可指認):有庫存的自選列右緣出現「3張 +1.2%」紅字、hover 出均價/損益元;單檔
header 新格數字與右欄閃電梯部位列一致(截圖並排);群組卡同款;個股期倉位以「期 n口」顯示於
對應股號;無倉列無變化。真實環境:user 有真倉位時截圖;測試以 positions fixture + quotes fixture
鎖數字(含 avg_price=None 降級顯示「—」)。
三類:🔵 positions 附 code helper(與 R2 共用,若 R2 先 merge 則沿用)→ 🟢 三處 UI。
```

---
### R4 `/mod 台股綜合:加權/櫃買分時圖改用個股 IntradayChartCore + 左欄雙圖縮小/騰落線增高`

```
/mod 台股綜合左欄:(a) 加權/櫃買分時圖改用個股同一份 IntradayChartCore(hover 十字線/readout/
昨收線/均價線/CDP+MA(加權)/高低點/現價圈;D11 a),(b) 雙圖高度縮小、騰落線改吃 flex 剩餘高
(D12 a)。同輪、分 commit,(a) 先 (b) 後(chrome 高度定了才算地板)。UI 輪:載入 frontend-design +
bencium-controlled-ux-designer;既有 token 內做。

前置 probe(spec 第一步,結果決定量能副圖開關):TC4 IX0001 push payload 有 TradeQuantity /
TradeVolume / YTradeVolume 鍵(spikes/out/index_symbol_probe.json pushed_detail),但 index_engine
:329-351 _handle_quote 只解析價 → 盤中用 --verify 側車或 spikes 腳本記錄 IX0001 quote 三鍵實值
(是否為累計成交金額/量、單位);櫃買 MIS 5s poll 欄位(mis.py)有無成交金額。有量 → adapter 帶
v(金額換算)開量能副圖;無量 → mode:"index" 關副圖與 VP。

已調研事實:
【現況指數圖】MarketChart.tsx:29 SIZE 640×220、:92-252 IntradayChart 自繪(無 hover/readout/副圖)、
:106 buildIndexGeometry(lib/index-chart-svg.ts:62-83 yTop=hi*1.003/yBottom=lo*0.997)、:122 均價
= 分鐘收盤算術平均(指數無量)、:82-83/:301-323 overlay 只做加權(櫃買無日 K 已拍板)、
:136-141 rightEdgeLabels(與個股 edgePriceLabels 兩套,next-time:104-107 合一待辦);
MarketPane.tsx:23 SIZE、:110-134 OverlayCard(加權 vs 櫃買相對昨收疊線 — **保留不動**)、
:341-350 PANE_FRAMES(pane-frame.ts:36-40 intraday chromeY=26/overlay 62/candle 100)+
paneSvgHeight/paneUnitScale、:403-411 figure min-h-48 flex-1 算式。
【資料 shape】useIndexStream.ts:13-20 IndexSeries{p,ref,high,low,stale,minutes:Record<"HHMM",
milli>} 無量;index_engine.py:120-133 _Series、:366-385 _apply_otc(5s 合成 OHLC 只給 K 線)、
:594-618 payload;個股 stock-accum.ts:71-98 StockAccum{minutes:Map<min,MinuteAgg{c,v,i,o,u,h?,l?}>,
vwap,vp,meta{ref,upper,lower},...};buildIntradayGeometry(:320-323)入參。
【個股 core】StockIntradayChart.tsx:604-643 Props/CoreProps(accum,toggles,variant,width,
mainHeight,subHeight,stkfut)、:659-662 內建 useStockOverlay(需改為可注入 overlay prop;指數已有
useIndexOverlay.ts:29-45 打 /api/index/overlay,app.py:1402-1424 + overlay.py:32-44 共用
build_overlay)、:684-703 副圖/VP 需量、:707-815 available/offTitle(期貨態文案 → 加 index 態
文案「櫃買無日 K」沿 MarketChart:114)、:762-787 readout 六欄(index 態縮為 時間/點位/漲跌%)、
:809-815 toggle disabled。設計:lib/index-accum-adapter.ts `indexSeriesToAccum(series, key)`
(minutes HHMM→分鐘數、c=value、v=0 或金額、meta.ref=ref、upper/lower=null → 幾何走對稱
autofit fallback,截圖前後對照觀感差異寫進 change-spec)+ core 新 prop
`mode?: "stock"|"index"` + `overlay?: StockOverlay|null`。
【佈局】IndexPage.tsx:124-127 主 grid、:131 左欄 flex-col、:140 雙圖 grid `flex-1 min-h-80`
(:137-139 算式)、:164-171 家數帶+騰落線 section `shrink-0`;AdvanceDeclineChart.tsx:82 wrapper
`h-24 shrink-0`(:69-73 useContainerSize 已在、:25 fallback 150);MarketPane.tsx:411 figure
`min-h-48 flex-1`。改法 D12(a):騰落線 wrapper → `flex-1 min-h-40 min-h-0` 契約(照
useContainerSize.ts:7-12 恆存 wrapper),section 去 shrink-0 改 `flex-1 min-h-0`,雙圖 min-h 依新
chrome 重算(推導寫進 spec,沿 MarketPane.tsx:358-366 收斂推導)。
【測試該紅/該改】MarketPane.test.tsx:318-431(自繪 SVG 假設)、MarketPane.size.test.tsx:137-269
(PANE_FRAMES 三態 + :256-270 可縮鏈)、IndexPage.test.tsx:322-332(y3 min-h-80)、:337-347(y4
不動)、AdvanceDeclineChart.test.tsx:196-241(TD-6 h-24 固定 → 改為 flex 契約);個股側
StockIntradayChart.test/.variant.test、stock-intraday-svg.test 不該變(mode 預設 stock)。
【既有債】next-time.md:72-80(K 線態窄 pane 字級、EDGE_LABEL_H 未隨 unitScale)— 縮圖更易命中,
本輪不修,verification 截圖標註是否惡化。

白名單:個股頁/群組圖牆分時圖零變化(mode 預設);OverlayCard 與 K 線態不動;/api/index/*
契約不動(除非 probe 決定加量欄位 → 🔴 獨立 commit + WS payload 版本);家數帶/漲跌停列表/
右欄不動;1050px 兩欄斷點與單欄退化不動;可縮鏈(min-h-0 節點)不動。
成功條件(畫面可指認):加權圖 hover 出十字線與 readout、均價線/昨收線/CDP+MA 標籤與個股頁同款
外觀;櫃買圖同款但 CDP/MA toggle 灰且 title 說明;1920×1080 與 1536×864 整頁無捲軸,騰落線
高度 ≥ 雙圖高度的 60%(數字寫進 spec);截圖走 claude-in-chrome 既有 session。
三類:🔵 core 加 mode/overlay 注入(個股頁截圖前後對照零差)→ 🔴 換元件 + adapter → 🔴 佈局
高度(獨立 commit)→ 🟢 若 probe 有量:index_engine 解析量 + adapter 開副圖。
```

---
### R5 `/mod 相關係數加「小日經」第七腿(config 加腿 + river 第 7 色)`

```
/mod 相關係數 tab 加日經 225 腿:configs/correlation.json legs 加
{"key":"NK225M","label":"小日經","symbol":"TC.F.OSE.NK225M.HOT","source":"tc4"}(D13 a),
river-colors.ts 補第 7 組色;韓指(KOSPI)TC4 無 KRX 段做不到 → 記 next-time 追蹤(D14)。

前置 live 探測(spec 第一步,盤中或海外盤時段):(1) 重跑 QueryAllInstrumentInfo Fut 全量 dump
(spikes/TCPY tcoreapi_mq.py:74,比照 spikes/catalog_dump 手法)確認 OSE NK225M 仍在、KRX 仍無;
(2) QueryInstrumentInfo("TC.F.OSE.NK225M.HOT") 存在性 oracle(SUBQUOTE 對不存在 symbol 也回 OK,
tc4-market-facts:13-17);(3) 比照 spikes/index_symbol_probe.py:99-100 UNSUB→SUB 監聽 60s 推播計數,
比較 NK225 / NK225M / SGX NK 三者流動性,選定寫進 spec;(4) 全天窗跨 UTC 06 邊界推播是否中斷
(next-time:689 既有未驗項)順帶觀察。**探測腳本一律 Disconnect() 收工**(CLAUDE.md §0a)。

已調研事實:corr_config.py:23-25/:54-64 六腿預設、:81-106 load_config never-raise;
configs/correlation.json:2 「新增一腿只需 legs 加一筆(SC-8)」、:3 _todo_tsm 佔位先例;
corr_source.py:5-6,31-34,54-56 全天窗不限交易所段;corr_engine.py:132-143/:164-184 訂閱與重試
依 config、:224-246 路由依 symbol、:104/:319/:361-363 river 與 corr 共用 config.legs;
tests/test_corr_config.py:43-59 第七腿契約測試樣板、:11-36 六腿數量鎖(該變:預設 config 是否
也加?→ **只改 configs/correlation.json 不動 DEFAULT_CONFIG**,預設六腿測試不動);前端
CorrPanel.tsx:46-87 / RiverCards.tsx:96-112 動態腿數零改、river-colors.ts:1-17 六色取模撞色
(補 stroke-river-7/fill/text 三常數,class 字面值 Tailwind v4 靜態掃描 :7);catalog 事實
spikes/catalog_dump/catalog_Fut.json:12542-12750 OSE HOT 節點、:11272-11304 SGX NK、summary.json
17 段無 KRX。

白名單:六腿現有 key/label/symbol 不動;base=TXF 不動;river 前六色不動;無 TC4 時降級行為
不動。成功條件:海外盤時段 corr 表與江波圖出現「小日經」列且有數字;pytest test_corr_config 新增
七腿 config 檔案讀取案例;探測記錄(dump diff + 推播計數)落 verification 與 tc4-market-facts
SKILL 海外節新增「日經有 / 韓指無(KRX 段不存在)」事實。
三類:🟢 config + 第 7 色 → 🔵 SKILL/next-time 文件。
```

## 3. 執行備忘

- 每輪開跑前重 grep 一次行號(本檔行號為 2026-08-17 master `de44d49b` 快照)。
- R1 → R2 串行(store.py / useCapital.ts / CapitalOrdersList 同動);R3 若晚於 R2 則沿用 R2 的
  「回傳附 code」helper;R4 / R5 可並行 worktree(記憶 mutation-reviewers-serial 與 ops-discipline
  三險照過)。
- R1 D4 現股市價安全首單、R2 真成交截圖、R3 真倉位截圖、R5 海外盤探測:皆需 user 盤中在場,
  自動化綠燈不算 Done。
- 完成一輪:勾銷本檔 §0 對應列 + memory `user-feedback-batch-2026-08-17` 對應條。
