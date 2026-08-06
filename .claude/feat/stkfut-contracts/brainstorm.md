# brainstorm — 個股期合約選擇(題 3,stkfut-contracts)

規格來源:`.claude/feat/stock-quintet-discussion/brainstorm.md` 題 3(user 2026-08-05
拍板:**一輪做完;切換後分時與五檔也切換為該月期貨合約;小型個股期納入;UI 放個股頁**)
→ /auto 預核准。分流判定:**已成形方案**(資料路徑與 UI 落點皆於討論輪指名)。

## 目標

個股頁選定「有期貨的個股」後,可下拉選擇合約(現貨/標準近月/次月/季月/小型系列);
選中期貨合約時**分時圖與五檔整體切換**為該合約行情,並可經群益直接下單該合約。

## 現況關鍵事實(探查輪 + 實讀)

- **個股期 REALTIME 與個股同構**:`futures_models.parse_futures_realtime =
  parse_stock_realtime`(檔頭明載 stkfut 同欄位)→ StockDayState/分時聚合/五檔可整套重用
- 合約發現:`QUERYALLINSTRUMENT Type="Fut2"` → StockFutures 樹(節點名帶股號如
  「台積電(2330)」、Contracts = 全月份 leaf 5-6 口;小型獨立節點);現行 code 零覆蓋;
  `tc4.py list_series()`(Type="Opt")骨架可改
- leaf symbol(`TC.F.TWF.CDF.202609`)與既有 stkfut HOT 腿字串不同 → 無同 symbol 衝突;
  歷史回補必須從持有該 symbol REALTIME 的 session 發(§8 通則)
- 期貨日盤分鐘域 = 08:45–13:45(`FUTURES_MINUTE_DOMAIN`);前端分時窗常數
  `X_START_MIN/X_END_MIN` 為現貨 0900/1330 寫死 — **需參數化**
- 下單:`mapping.to_exchange_symbol('CDF','202609') → CDFI6` 已可用;**硬卡點 =
  `MULTIPLIERS` 無個股期乘數**(標準 2000/小型 100;`stkfut_map._contract_unit`
  刮得到未落檔);前端 `FuturesLadder` 寫死 `.HOT` 需參數化;YYYYMM 直送繞開
  resolved_contract
- `stkfut_map.json` 現 268 檔標準檔(v1:prod/name;無 unit、無小型碼)

## 成功條件(SC)

- **SC-1 合約發現**:`tc4.py` 新 `list_stock_futures()`(Type="Fut2")+ 解析
  `{股號: {std: {prod, unit?, contracts: [ym…]}, mini: {prod, contracts} | null}}`;
  server 內 in-memory 當日 cache(合約每月換,不可 hardcode);
  route `GET /api/stock/stkfut/contracts/{code}` → 404 無期貨 / 200 上述形。
  驗證:pytest(parser 用 spike catalog fixture;route 形)(anytime)
- **SC-2 乘數落檔**:`stkfut_map.json` bump v2 — 每檔加 `unit`(標準股數)與
  `mini: {prod, unit} | null`;`refresh-stkfut-map` 同步刮;
  `capital/mapping.multiplier_of` 對未知產品 fallback 查 stkfut 表(標準與小型碼皆中),
  仍未知才 raise。驗證:pytest(mapping fallback;safety 金額閘用對乘數)(anytime)
- **SC-3 期貨主圖**:stock_engine 主圖 slot 支援期貨合約 instrument
  (`set_main_contract(prod, ym)` 或等價):訂 leaf REALTIME(stock session)、
  StockDayState ingest、當日 1K 回補(同 session;期貨域)、WS tick/book 照發;
  切回現貨零殘留。驗證:pytest(fake source;訂閱 symbol 正確、分鐘聚合、切換清態)
  (anytime)
- **SC-4 前端合約下拉(可指認)**:個股頁 header 區、主圖股票有期貨時出現「合約」
  下拉 — 選項:`現貨`、`{近月 YYYYMM}`、`{次月}`、…、小型系列(標題「小型」分組或
  前綴);無期貨的股票不顯示下拉。驗證:vitest + 截圖 + user 過目
- **SC-5 分時/五檔切換(可指認)**:選期貨合約後 — 分時圖 x 軸變 08:45–13:45
  (格線與時間標同步)、走勢/VWAP/量副圖照畫;五檔(OrderBook)顯示該合約簿;
  資訊列現價/漲跌幅為該合約;切回現貨還原。驗證:vitest(窗參數化幾何 lock)+
  截圖 + user 過目
- **SC-6 下單直通**:選中期貨合約時,閃電梯/下單面切為期貨模式送
  `TC.F.TWF.{prod}.{ym}`(YYYYMM 直送);乘數經 SC-2 表;口數單位。
  驗證:pytest(capital_api 對個股期合約 400 消失、欄位轉換)+ vitest(ladder 參數化);
  真送單 = user 過目層(prod 安全首單,不在本輪自動化)
- **SC-7 零退化**:六 gate 全綠;既有 TXF/MXF/TMF 期貨面板與現貨個股頁行為不變。

## Edge cases

1. 股票無期貨(map/Fut2 查無)→ 下拉不顯示;直接打 contracts route → 404
2. 合約到期月消失(第三週三後)→ contracts cache 當日內可能 stale;選單以 cache 為準,
   訂閱失敗(零推播)走既有 no_data 表現;cache 為當日 TTL
3. 小型與標準同月並存 → 選項分開列(prod 不同)
4. 期貨合約盤後 fresh subscribe 只回收盤 snapshot(§8 實證)→ 與現貨同表現,可接受
5. 夜盤時段選期貨合約:分時窗僅日盤(08:45–13:45)— 夜盤 tick 落窗外不畫
   (夜盤分時不在本輪 scope;閃電梯照常可用)
6. 切合約期間 WS tick 混流(舊 instrument 殘包)→ 沿既有 seq/code gate 語意,
   instrument 標識要能區分
7. Fut2 查詢失敗(TC4 斷)→ contracts route 503/502;下拉降級不顯示

## 決策記錄

- `[auto-default: 期貨主圖重用 StockDayState 整套(同構 REALTIME)而非泛化
  FuturesEngine | reason: user 要的是「分時+五檔」= stock 頁既有能力;FuturesEngine
  無分鐘序列;同構解析零新 parser]`
- `[auto-default: 前端分時窗參數化(geometry 收 window 參數,預設現貨窗)| reason:
  期貨 08:45–13:45 是硬需求;參數化最小侵入,現貨路徑預設值零變]`
- `[auto-default: 合約發現走 server 端 Fut2 查詢 + 當日 in-memory cache,不落檔 |
  reason: 合約每月換、TC4 是唯一權威;檔案 cache 增加 stale 面]`
- `[auto-default: stkfut_map v2 加 unit/mini(版控檔隨 refresh CLI 更新)| reason:
  乘數屬安全邊界(safety 金額閘),要版控可稽核;Fut2 樹無契約單位資訊]`
- `[auto-default: 訊號/群組/自選對期貨合約不啟用(僅主圖行情+下單)| reason:
  自選池是現貨股號;期貨合約入自選是另一題]`
- `[auto-default: 夜盤分時不做(閃電梯照常)| reason: 現貨個股頁本無夜盤;
  期貨 tab 已有 allday K 線可看]`

## Out of scope

- 期貨合約入自選/訊號/群組;夜盤分時;期現價差圖表化(既有一行價差保留);
  resolved_contract 對個股期(前端 YYYYMM 直送);合約選擇持久化跨 session
  (每次回到現貨為預設)

## 規模分流

**L**(後端 tc4/stkfut_map/mapping/stock_engine/app + 前端 header/圖表窗/OrderBook/
ladder;跨前後端 + 下單安全面)→ 完整流程,L 級把關。

## 驗證窗口

SC-1..5/7 anytime(fixture/fake);SC-4/5 截圖 anytime(fake server 可種);
SC-6 真送單 = user 過目(prod 安全首單);盤中實看 = user 過目層。
