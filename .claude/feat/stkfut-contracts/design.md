# design — 個股期合約選擇 v2

changelog:
- v1(2026-08-06):初版。
- v2(2026-08-06):design review round 1 十八條全修 — D1 推播路由(_symbol_to_key);
  D2 試撮窗參數化(期貨空窗);D3 個股期梯改現股 tick 表(期交所規格實證:升降單位
  與現股同級距;ETF 標的本輪禁下單)+ 後端合法檔位閘;D4 回補走既有 TICKS 路徑
  (probe 實證 CDF.202608 TICKS 2381 rows/1K 224 rows 首根 0846);D5 contract state
  上移 App;D6 instrumentKey 單點組 URL;D7 BAD_CONTRACT 白名單驗證;D8 健檢改
  symbol 鍵;D9 窗參數化全清單;D10 期貨態僅江波圖;D11 乘數三道閘;D12 送單 props
  規格(隨 D3 改向);D13 Fut2 dump 自主 tree 尋回 + fixture 落檔;D14 夜盤雙保險
  (rollover 排除 F: + ingest 日盤窗);D15 槽位轉移表;D16 _dirty_watchlist 排除;
  D17 取證通道 = fake server 慣例;D18 裁決保留 SC-6(user 拍板一輪,
  `[auto-default]` 記錄)。
- v2.1(2026-08-06,限縮輪 R2-1..R2-8 全修):R2-1(P0)parser 白名單
  ENG==StockFutures + SYMBOL 欄 + 四段形 + 價差反例 fixture;R2-2 symbol 對映
  單一定義 + 先寫後訂;R2-3 no-data timer 僅三段形合約鍵;R2-4 下單面改
  presentation + 雙 container;R2-5 武裝解除 key = instrumentKey;R2-6 版本閘
  下沉 multiplier_of(load_map 降級不炸 server);R2-7 REST URL 恆帶 code 路徑;
  R2-8 BAD_TICK / PRODUCT_NOT_ALLOWED 分碼 + market 單跳過檔位驗證。

**Goal**:個股頁選期貨合約 → 分時/五檔切換 + 下單直通(brainstorm SC-1..7)。

**架構總綱**:同 v1(instrument 推廣 + StockDayState 重用);v2 把差異面收斂為
**七個明確接點**:推播路由、試撮窗、回補 symbol、前端 x 窗、tick 級距、rollover
隔離、下單 props。

## 檔案組織

| 檔 | 變更 | SC |
|---|---|---|
| `copycat/live/tc4.py` | `list_stock_futures()`(Type="Fut2";parser 規格見 SC-1,以 fixture 定稿) | SC-1 |
| `tests/fixtures/catalog_fut2_sample.json`(新) | 自 `spikes/catalog_dump/catalog_Fut2.json`(主 tree 尋回,已複製入 worktree)裁 3-5 檔含小型/HOT 節點 | SC-1 |
| `copycat/server/stkfut_catalog.py`(新) | 當日 in-memory cache + 單飛;`contains(code, prod, ym)` 白名單查詢(D7 用) | SC-1 |
| `copycat/stkfut_map.py` + `.json` | v2:`unit` + `mini`;refresh 對壞列**跳過 + 彙總 warn(全滅才 raise)**(R2-6);`load_map` 版本不符 → **log + 回 {}(降級不炸 server** — 唯一 runtime 呼叫點是 StockEngine.__init__,raise 會讓整個個股 tab 掛)(R2-6);v2 json 重生與版本判定同 commit | SC-2 |
| `copycat/capital/mapping.py` | `multiplier_of` fallback 查 stkfut 表(std/mini);**安全閘收此**:版本不符 / 查到但 unit 缺/≤0 → ValueError(→400)(D11c/R2-6) | SC-2/6 |
| `copycat/capital/…(capital_api)` | 個股期送單:**價格合法檔位閘**(股票 tick 表;不合法 400 INVALID_ORDER);**非股票單位(std≠2000 或 mini≠100,如 ETF 10000)→ 拒單 INVALID_ORDER(本輪不開放)** | SC-6 |
| `copycat/live/stock_models.py` | `parse_stock_realtime` / `parse_hist_tick` 加 keyword-only `trial_windows=_TRIAL_WINDOWS`(D2;期貨傳 `()`) | SC-3 |
| `copycat/live/stock_source.py` | key `F:<prod>:<ym>` → symbol;`backfill`/REALTIME 對該 key 換 symbol + 空試撮窗;健檢 `_seen` 改以 **symbol** 記(D8) | SC-3 |
| `copycat/server/stock_engine.py` | `_symbol_to_key` 路由(D1);`set_main_contract` 槽位轉移表(D15);rollover 排除 `F:` tick(D14a);ingest 日盤窗 gate(D14b);`_dirty_watchlist` 排除 `F:`(D16) | SC-3 |
| `copycat/server/app.py` | contracts route;`/api/stock/state/{code}?contract=` 驗證(D7);snapshot 帶 `underlying` | SC-1/3 |
| `frontend/src/lib/stock-intraday-svg.ts` + `lib/time-labels.ts` | `XWindow` 參數化(D9 全清單:geometry/energy/sideSummary/minuteToX/minuteOf/barW/hourTicksOf) | SC-5 |
| `frontend/src/App.tsx` | **contract state 在 App**(D5):與 stockCode 同層、換股重置 null;餵 useStockStream 與 railCtx | SC-4/5/6 |
| `frontend/src/hooks/useStockStream.ts` | `(code, contract)` → 內部唯一 `instrumentKey` 單點組 URL + WS gate(D6);deps 含 contract | SC-5 |
| `frontend/src/components/stock/StockPage.tsx` / `StockChart.tsx` / `StockIntradayChart.tsx` | 下拉(header)、期貨態僅江波圖(D10:其餘模式 disabled + overlay/VP enabled:false)、窗 prop | SC-4/5 |
| `frontend/src/hooks/useStkfutContracts.ts`(新) | contracts query | SC-4 |
| `frontend/src/components/…(個股期下單)` | 期貨態下單面(D3/D12 新規格見 SC-6 節) | SC-6 |

## SC-1 合約發現(D13 已定錨)

- fixture 來源:`spikes/catalog_dump/catalog_Fut2.json`(873KB,2026-06-30 dump)。
  **樹形實讀(R2-1)**:`Instruments.Node` 有兩支 — `ENG="StockFutures"`(真合約:
  節點帶 `SYMBOL="CDF"`、`InstrumentID` 非 null、Contracts = `TC.F.TWF.CDF` +
  `.202607/...`)與 `ENG="StockFutures(F2)"`(**個股期貨價差** — 節點名逐字同名、
  無 SYMBOL、Contracts 為 `TC.F.TWF.QFF.202607.QFF.202608` 六段跨月形)。
  **parser 規格**:只走 `ENG == "StockFutures"` 支(顯式排除 F2);prod 取節點
  `SYMBOL` 欄(不從 Contracts 推);月份只收恰四段 + 尾 YYYYMM 形
  `TC.F.TWF.<SYMBOL>.<YYYYMM>`(自然排除裸 `TC.F.TWF.CDF` 與價差六段形);
  `InstrumentID` 非 null 為第二判準。fixture 裁 3-5 檔**必含一個價差節點當反例**,
  測試斷言其不出現於輸出。活樹與 dump 形不符 → 實跑 502 可觀察,非靜默。
- `StkfutCatalog.get(code)`(當日 cache/單飛/失敗 raise 不留舊日)+
  `contains(code, prod, ym) -> bool`(D7 白名單)。
- route `GET /api/stock/stkfut/contracts/{code}`:404 NO_STKFUT / 200 / 502。

## SC-2 乘數(D11 三道閘)

v1 形 + 三道閘(檔案表列明)。ETF 註記:契約單位 10,000 股者為 ETF 期貨 —
**乘數表照落**(行情/顯示可用),下單層拒(SC-6)。「標準 2000/小型 100」不寫入
程式常數(D11 註),判定「股票標的」= `std.unit == 2000`(期交所股票期貨規格)。

## SC-3 期貨主圖

- **推播路由(D1/R2-2)**:engine 維護 `_symbol_to_key: dict[str, str]` — 鍵由
  **`StockSource.symbol_of(key)`**(Protocol 新增,實作 = 既有 `stock_symbol`
  唯一定義;fake source 同 Protocol)產,engine 不自組第二份對映。
  **寫入先於訂閱**:`_acquire` 在呼叫 `subscribe_symbol` **之前**寫 map(訂閱
  失敗回滾 pop)— SUB 回來後首則推播毫秒級抵達(§8 實證),後寫必漏首則
  (冷門股唯一那則 meta 推播被丟 = round4 項 4 同款)。map miss → debug log +
  丟棄(顯式分支)。測試鎖「先寫後訂」順序(fake source 在 subscribe 當下回推)。
  `_handle_quote`:先查 map — 命中且非 HOT 腿 → 一般 stock 路徑(全用 key);
  `_handle_stkfut` 判定改「Symbol endswith '.HOT'」。`StockTick.code`(=Security)
  與 WS `code`(=key)分離,hub/_dirty 一律吃 key。
- **試撮窗(D2)**:`parse_stock_realtime(..., trial_windows=())`(期貨 key);
  `parse_hist_tick` 同。測試:期貨 08:50 / 13:27 tick ingest 成功入 minutes;
  現貨同時刻照丟。
- **回補(D4,probe 實證)**:沿既有 TICKS 路徑 — `backfill()` 對 `F:<prod>:<ym>`
  只換 symbol(+空試撮窗);`stock_window`(UTC 00–06 = 台北 08–14)已涵蓋
  08:45–13:45,**無域改動**。1K/域那條路本輪不碰。
- **槽位轉移表(D15)**:

  | 轉移 | 動作 |
  |---|---|
  | 現貨→期貨 | acquire(F:key, main) → release(old, main) → **release_stkfut(old)** → enqueue_backfill(F:key);不 acquire_stkfut |
  | 期貨→現貨 | acquire(code, main) → release(F:old, main) → release_stkfut(F:old)(map 查無 → 無害早退)→ acquire_stkfut(code) → enqueue |
  | 期貨→期貨 / 現貨→現貨 | 同構類推 |
  測試:四轉移後 `_refs` 零洩漏(逐 owner 斷言)。
- **夜盤雙保險(D14)**:rollover 判定 `if key.startswith("F:"): 不觸發換日`;
  期貨 key 的 ingest 前加日盤窗 gate(tick 時刻 ∉ [08:45, 13:45] 丟棄);
  REALTIME 訂閱窗沿個股日盤窗(UTC 00–06 涵蓋期貨日盤,**刻意選擇**;
  真實環境驗證清單加「08:45–09:00 有推播」觀察項)。
- **健檢(D8/R2-3)**:`_seen` 的**鍵**改以 symbol 記(回呼 `on_no_data` 仍傳
  key,engine `_no_data` 以 key 記);no-data timer **只掛三段形合約鍵**
  (`F:<prod>:<ym>`)與現貨 — **HOT 價差腿(`F:<prod>` 兩段形)維持現行排除**
  (放開會讓 `_handle_no_data` 廣播 `code="F:CDF"` 的 watchlist_quote,與 D16
  打架且 SC-7 驗證必紅)。測試:合約鍵訂閱後 N 秒零推播 → `no_data=true`;
  HOT 腿零推播 → 無廣播。
- **切換 API(D6/D7)**:`GET /api/stock/state/{code}?contract=CDF:202609` —
  contract regex `^[A-Z0-9]{2,4}:20\d{2}(0[1-9]|1[0-2])$` + **catalog.contains
  白名單**(prod 屬該 code 且 ym 在列;否則 400 BAD_CONTRACT;catalog 不可用 →
  502 拒絕不放行);snapshot 回應帶 `code`(instrument key)+ `underlying`(股號)。
- `_dirty_watchlist` 只收 `code in self._watchlist`(D16);SC-7 驗證加
  「期貨態 watchlist_quote code 集合 ⊆ 自選」。

## SC-4/5 前端

- **contract state 在 App**(D5/R2-5):`stkfutContract: {prod, ym, mini} | null`,
  換 stockCode 重置;下傳 StockPage(下拉)+ `useStockStream(code, contract)` +
  railCtx。**railCtx 口徑寫死**:`code` 恆為股號(RightRail 點價置中 gate 依賴)、
  `contract` 獨立欄、`name`/meta 沿現行來源。
- **useStockStream(D6/R2-7)**:`instrumentKey = contract ? \`F:${prod}:${ym}\` : code`
  — **僅用於** WS tick/book/status/stkfut 的 code 比對與 effect deps;
  **REST 恆為 `/api/stock/state/${code}${contract ? \`?contract=${prod}:${ym}\` : ""}`**
  (單一 helper 產,五個 refetch 觸發共用;key 不可當路徑段 — `_valid_code`
  會 400 且 D7 白名單失去 code)。vitest:URL 形斷言 + WS 重連後仍帶 contract。
- **窗參數化(D9 全清單)**:`type XWindow = { start: number; end: number }`;
  `SPOT_WINDOW = {540, 810}`、`STKFUT_WINDOW = {525, 825}`。貫穿:
  `buildIntradayGeometry` / `buildEnergyBars` / `sideSummary` / `minuteToX` /
  `minuteOf` / 元件 `barW` 分母 / `time-labels.hourTicksOf(window)`(index 頁沿
  既有常數呼叫零改)。**foldVp 不參數化** — 期貨態 VP 停用(toggle 反灰 +
  vpBars 空,測試鎖)。lock 測試:期貨窗 `minuteToX(525)=Y_AXIS_W`、
  `minuteToX(825)=W−R_AXIS_W`、minuteOf 互逆、barW 分母 300。
- **期貨態模式集合(D10)**:僅江波圖;1-10 分 K / 日 K 模式鈕 disabled
  (tooltip「期貨合約本輪僅提供分時」);`useStockOverlay` / VP / CDP/MA toggle
  期貨態 `enabled:false` 不打請求。
- 下拉(SC-4 可指認):header 股名旁 `<select>` — `現貨` + std(`2026/09`)+
  mini(`小型 2026/09`);無期貨 → 不渲染;`useStkfutContracts` 404 → null。
- 期現價差列:期貨態清空不顯示(D15 前端側)。

## SC-6 下單(D3/D12/R2-4/R2-5 定稿)

- **個股期檔位幾何 = 現股 tick 表**(期交所實證同級距;`stock-tick.ts` 直接正確)。
- **結構(R2-4)**:抽共用「價格梯 presentation」(檔位列/量 bar/點價/武裝視覺,
  自 PriceLadder 抽,零行為變更)+ 兩個薄 container:
  - `PriceLadder`(現股,既有行為零變)
  - `StkfutLadder`(新):逐項規格 —
    submit = `useSubmitFuture`(body `tc4_symbol: "TC.F.TWF.<prod>.<ym>"`、
    `day_trade` checkbox);cancel = `{seq_no, market: "fut"}`;活單方格比對鍵 =
    `exchangeContract`(`futExchangeContract(prod, ym)` 產,CDFI6 形)+
    `market === "fut"`;部位條 = fut positions 過濾 + `futCloseEstimate`
    (upper/lower 自 accum.meta)口徑,**不用**現股稅費;交易別列(現股/融資/融券)
    **隱藏**;數量標籤「口數」;`daytrade_sell` 邏輯不適用(隱藏)。
  - **武裝解除 key = instrumentKey**(R2-5):dispatchArm symbol_changed 的 effect
    deps 用 instrumentKey — 現貨↔合約切換不 unmount 同實例,code 不變時武裝
    跨標的殘留 = 繞過確認直送。vitest:切 contract → `aria-pressed=false`。
- FuturesLadder(台指)零改。
- **後端閘(D3/R2-8)**:capital_api 期貨送單對 TWF 非 known-products 合約:
  - 非股票單位(std.unit≠2000 且 mini.unit≠100,如 ETF 10000)→ 400
    `PRODUCT_NOT_ALLOWED`(本輪不開放;前端該類下單鈕 disabled +
    「ETF 期貨下單暫未開放」)
  - **limit 單**驗價格為股票表合法檔位,不合法 → 400 `BAD_TICK`;
    **market 單跳過檔位驗證**(price 欄無意義)
  - 兩新碼入 `{detail:{error}}` 契約與前端文案表。

## SC-6 補記(B6,Phase 4 對帳)

實作落點與 v2.1 文字的三處差異(行為正確,補記載):RightRail 於 contract≠null 時
`market="fut"` 貫穿**委託/部位兩個 tab**(R4);`futCloseEstimate` 落點在 RightRail
部位 tab(平倉鍵所在),StkfutLadder footer 只顯示群益名目損益;`stkfutQty` 與台指
`futQty` 分開存(Phase 4 fix 後進一步以 instrumentKey 分槽 — A5)。

## SC-7 零退化 + 取證通道(D17)

- 既有測試面必跑:`stock-intraday-svg.test.ts` 窗常數斷言、MiniIntradayChart、
  index 分時(共用 hourTicks)、期貨 tab 三檔、現貨個股頁全家。
- Phase 6 取證 = **自建 fake server**(本 session 慣例,`.claude/feat/*/evidence/
  fake_server.py` 樣板 ×2 輪):SeededStockSource 擴充可種期貨 instrument
  (08:45–13:45 分鐘 + 五檔 + meta);vite 暫改 proxy。不動 verify.py。
- SC-6 真送單 = user 過目層(prod 安全首單:遠價 1 口 → APP 核對 → 刪單,
  §7 紀律),不入自動化。

## Known Risks

- **除權息調整契約會被下單閘誤拒(R13,已 characterize)**:SC-6 的
  `PRODUCT_NOT_ALLOWED` 判準是「std.unit == 2000 / mini.unit == 100」,而個股遇
  除權息時期交所會發調整後契約(契約單位變 2,157 之類,TC4 產品碼另掛如 EE1)——
  它落在與 ETF 同一側,一併被擋。行情/選單不受影響(catalog 只收原始契約 EEF),
  只有送單被拒。放寬需要「哪些單位算股票期貨」的權威來源,不是把閘拿掉。
  另:catalog parser 對同股號的調整契約(SYMBOL 尾非 "F")一律讓位給原始契約,
  下拉因此看不到調整契約 — 同一件事的另一半。
- 個股期 leaf 盤後 fresh subscribe 僅收盤 snapshot(§8)→ 盤後切合約看到單點,
  與現貨同表現。
- catalog 當日 cache 在到期日盤中 stale(近月消失)→ 選單殘留 → 訂閱零推播 →
  D8 健檢 no_data 可見;接受。
- 夜盤 ingest gate 依賴本機時刻窗;REALTIME 訂閱窗涵蓋性為刻意選擇 + prod 觀察項。
