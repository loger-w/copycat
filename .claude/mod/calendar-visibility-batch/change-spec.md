# change-spec — 日曆可見性小批:錯標膠囊 + SignalRail 標題帶日期 + 試撮 badge 接日曆(mod/calendar-visibility-batch,R6 / B12)

分流判定:已成形方案(rounds.md §R6 三件事指名做法;預核准)。Scope:**M/L**(前端 4 檔 + 後端 1 檔 + 測試;無對外契約變更)。

## 現況
- 日曆單一來源 `GET /api/calendar` → `CalendarState {today, trade_date, calendar_trade_date, holidays[], years_loaded, calendar_loaded}`;前端 `hooks/useTradingCalendar.ts`
  (App.tsx:152 唯一掛載,queryKey `["calendar"]`,staleTime ∞、6h refetch)只把 holidays 灌進 `lib/trading-calendar`;`query.data` 無其他讀者。
- 1. 錯標:日曆把真交易日標成假日 → 後端 `_resolve_trade_date` 取最近交易日、輪詢停擺,前端零提示(僅 boot WARNING)。App header 區:`VersionDriftBadge` + `IndexBar`(App.tsx:286-287)。
- 2. `SignalRail.tsx:118/122` 固定「今日訊號」(aria-label 同);訊號 baseline = `/api/stock/signals/today`(hub 當日 = trade_date 的 jsonl);假日開站掛的是上一交易日訊號。
  LimitListSection.tsx:265 `monthDay(iso)` = `YYYY-MM-DD → MM-DD` 口徑(私有函式)。
- 3. 試撮 `(緩)`:後端 `stock_engine._spot_trial_now()`(L83,模組級,flush loop 翻轉偵測 L325/1303)與 `StockEngine._trial_now(code)`(L521,snapshot/payload L540/1269)皆**純時間窗**;
  `StockEngine` 已注入 `self._is_trading_day`(L213-225,預設 weekday<5,app 接日曆)。休市日 / 週末窗內仍標(緩)。
- Caller:`useTradingCalendar` 只 App;`SignalRail` 只 StockPage:185;`_spot_trial_now` 只 engine 內兩處;`_trial_now` 兩處;測試 `tests/server/test_stock_engine*.py`(trial 相關)、`SignalRail.test.tsx`、`StockPage.test.tsx`、`App.test.tsx`。

## 拍板(auto-default)
- **D1 共用 query options**:`useTradingCalendar.ts` export `calendarQueryOptions`(queryKey/queryFn/staleTime/retry/refetchInterval);App 的掛載不變;新讀者用 `useQuery(calendarQueryOptions)` 共享同一 cache(不多打端點)。
- **D2 錯標膠囊**:新元件 `components/CalendarHolidayBadge.tsx`:`useQuery(calendarQueryOptions)`;條件 = `data.calendar_loaded && data.holidays.includes(isoLocalDate(new Date()))`
  (本機今日命中假日清單;週末不在 holidays 清單內 → 不顯示,避免每週末常駐)→ 膠囊 `日曆判今日休市`(`data-testid="calendar-holiday-badge"`,`title` 說明「輪詢已停;若今天實際有開盤,請更新 configs/trading_holidays.json 並重啟」),
  色 `border-warn text-warn` pill 樣式沿 VersionDriftBadge;掛 App.tsx:286 `VersionDriftBadge` 旁。未載入 / 失敗 → 不顯示。
  `[auto-default: 命中 holidays 即顯示(非只錯標) | reason: 前端無法判「錯標」,能判的只有「日曆說今天休市」;真假日也該讓人知道為何靜默]`
- **D3 SignalRail 標題**:`SignalRail` 新 prop `tradeDate: string | null`(StockPage 經 `useQuery(calendarQueryOptions)` 傳 `data?.trade_date ?? null`);
  標題 = `tradeDate !== null && tradeDate !== isoLocalDate(new Date()) ? \`${monthDay(tradeDate)} 訊號\` : "今日訊號"`;aria-label 同步。`monthDay` 從 LimitListSection 抽到 `lib/format.ts`(🔵,LimitList 改 import)。
- **D4 試撮接日曆(後端)**:`StockEngine._trial_now(code)` = `self._is_trading_day(today_taipei) and is_trial_window(...)`;`_spot_trial_now()` 改為 `StockEngine._spot_trial_now()` 方法(同 AND);
  today 取 `_dt.datetime.now(TAIPEI).date()`(與 `_now_taipei_time` 同時鐘;engine 既有 L863 用 `now.date()`,沿同源)。假日 / 週末 → `trial` 恆 False、翻轉偵測不觸發。
  `[auto-default | reason: is_trading_day 已注入 engine,單一來源;前端 trial 旗標讀者零改動]`

## 成功條件
- SC-1 膠囊:`App.test` stub `/api/calendar` holidays 含本機今日 → 出現 `calendar-holiday-badge` 文字「日曆判今日休市」;不含 / calendar_loaded=false / fetch 失敗 → 不出現。
- SC-2 標題:`SignalRail` `tradeDate` = 今日 → 「今日訊號」;= 昨日 `2026-08-20` → 「08-20 訊號」(aria-label 同);null → 「今日訊號」。StockPage.test:calendar stub trade_date 非今日 → rail 標題帶日期。
- SC-3 試撮:engine 測試 `is_trading_day=lambda d: False` + 窗內時間 → `snapshot(code)["trial"] is False`、payload `trial` False、flush loop 不因窗翻轉而 flush;`is_trading_day=True` → 既有行為(既有 trial 測試不該紅)。
- SC-4 UI:膠囊以假 calendar(holidays 含今日)截圖;SignalRail 標題 08-20 截圖(盤後本機今日 = trade_date,需 stub);+ user 過目。

## 白名單
- W1 `useTradingCalendar` 行為不變(掛載點、setHolidays、6h refetch、retry 1);`/api/calendar` 契約不變。
- W2 SignalRail 其餘(合併列 / 規則 / 音效鈕)不變;`今日訊號` 在 trade_date = 今日時逐字不變。
- W3 `StockEngine` 在交易日的 trial 行為位元不變(既有 trial / trade-status-observe 測試全綠);`_is_trading_day` 預設 weekday<5 不變。
- W4 LimitList 日期文案不變(`monthDay` 搬家純 🔵)。
- W5 App header 其餘(IndexBar / VersionDriftBadge)不變。

## Out of scope
R3b 交易日盤前冷啟動(待 user 拍板);後端 boot WARNING 文案;週末顯示膠囊。

## Edge cases
1. 跨午夜長跑分頁:膠囊 / 標題每次 render 讀 `new Date()`,6h refetch 後自動更新。2. calendar 失敗 → 兩者降級為現況。3. 補班日(extra_trading_days)不在 holidays → 不顯示膠囊(正確)。
4. trade_date 格式異常 → `monthDay` 原樣印。5. engine `is_trading_day` 注入 None → 預設 weekday<5(週末 trial False = 新行為但合理)。

## 既有測試
該紅:無預期(新 prop 有預設 / 新元件)。若 SignalRail.test 以 `getByText("今日訊號")` 查詢,tradeDate 預設 null 仍綠。不該紅:engine 既有 trial 測試(注入 True 或預設平日 → 需確認測試當日為平日?**不**:測試注入 `is_trading_day` 或固定時間;若既有測試在週末跑會因預設 weekday<5 轉紅 → 既有測試須顯式注入 `lambda d: True`,此為測試 fixture 補強,body 註 `test-infra-fix`)。

## Diff 級
- 🔵 `monthDay` 抽 `lib/format.ts`(LimitList 改 import;測試不動)。
- 🟢 `calendarQueryOptions` export + `CalendarHolidayBadge`(測試先紅)+ App 掛載。
- 🔴 SignalRail `tradeDate` prop + StockPage 接線(測試先紅)。
- 🔴 後端 `_trial_now` / `_spot_trial_now` AND 日曆(測試先紅)。

---
## Spec review round 1 amendments(`change-spec-review-round-1.json`,12 條全 accepted;以本節為準)
- **D3' 標題日期來源改資料自帶(R6 / R4 / R5 / R12)**:後端 `/api/stock/signals/today` 回傳體 **additive** 加 `trade_date`(hub `trade_date_fn()` = engine 日別)與 `today`(`_today()` 牆鐘);
  前端 `useSignalFeed` 回傳加 `tradeDate: string | null` / `today: string | null`(payload 缺欄 → null);StockPage 傳 `SignalRail` 新 **optional** prop `dateLabel?: string | null`,
  由 StockPage 算:`tradeDate !== null && today !== null && tradeDate !== today ? \`${monthDay(tradeDate)} 訊號\` : "今日訊號"`(或直接傳兩個日期,由 rail 算;擇 rail 算 `tradeDate?` / `today?` 兩 optional prop)。
  **不用 `/api/calendar` 也不用瀏覽器時鐘**;StockPage 不新增 calendar query(R12 免 stub);`SignalRail.test renderRail` 不傳 → 「今日訊號」不紅(R5)。
  已知落差明記:hub `today_signals()` 為 {engine 日, 牆鐘日} 聯集,rollover stage2 前標題 = engine 日(與列一致),聯集時以 engine 日為標題 —— 接受並註解。
  useSignalFeed.test stub 補兩欄(optional,不補亦綠)。
- **D2' 膠囊條件改後端同源(R4 / R8 / R7)**:`data.calendar_loaded && data.holidays.includes(data.today) && !isWeekend(data.today)`(weekday 由 `today` 字串推,週末守門寫進程式);
  title = `日曆判今日休市,後端資料日 = ${data.trade_date};若今天實際有開盤,更新 configs/trading_holidays.json 並重啟`。SC-1 改固定 payload(App.test 既有 stub `today: 2026-08-16` 可直接加 holidays 含它 / 不含)。
- **D4' 後端試撮(R1 / R2 / R11)**:保留模組級純窗函式改名 `_spot_trial_window_now()`(既有 `_spot_trial_now` 更名;L2798-2821 `TestObserveClockContract` 改呼叫它 = test-infra-fix,斷言不變);
  `StockEngine._spot_trial_now()` 方法 = `self._is_trading_day(self._now_fn().date()) and _spot_trial_window_now()`;`_trial_now(code)` = `self._is_trading_day(self._now_fn().date()) and is_trial_window(_now_taipei_time(), trial_windows_for(code))`。
  **不用 TAIPEI 常數**(不存在),時鐘同 L857-863 `now_fn`。`_observe_window_now` / `trade-status-observe` 的 `trial_window=` 維持純時間窗(蒐證看窗本身),docstring 補一句兩者可不同值。
- **既有測試逐條(R3)**:fixture 補強(body 註 `test-infra-fix`):`_make_with_clock`(L2289-2303)加 `is_trading_day=lambda _d: True`;`TestTrialWindowFlipPush` 三處 inline 建構同步;`TestObserveClockContract` 改呼叫純窗函式。
  行為斷言該紅 0 條;新增正向鎖 SC-3(`is_trading_day=lambda d: False` + 窗內 → trial False、flush 不翻轉)。App.test / StockPage.test / SignalRail.test / useSignalFeed.test:不該紅(新欄 optional)。
- **R9 Out of scope 明列**:週末真開盤(補班)而 `extra_trading_days` 漏設 → 後端判休市但膠囊不顯示(週末守門排除),本輪不覆蓋。
- **R10 SC-4 通道**:側車 server(另 port,ops-discipline)—— 標題:`TXO_BACKFILL_DATE=2026-08-20` 使 trade_date ≠ today;膠囊:tmp holidays config 含今日起同一支側車(環境變數或複製 configs 到 tmp 並指向);prod 8721 不動。

---
## Spec review round 2 amendments(限縮輪,`change-spec-review-round-2.json`,9 條全 accepted;收斂)
- **AR1 後端契約擴張該紅**:Caller / Diff 級補 `copycat/server/app.py`(route 🟢 additive)、`copycat/server/signal_hub.py`(🟢 additive property)、`tests/server/test_signal_routes.py`;
  既有 **L423 / L433 / L457 / L496** 四條整 dict 全等 → 該紅(契約 additive 擴張,test-infra-fix):改 `body["signals"] == ...`,另立新案鎖 `trade_date` / `today` 兩欄。
- **AR6 / AR7 hub 公開 API + 同一時鐘**:`SignalHub` 加唯讀 `@property trade_date -> str`(`self._trade_date_fn()`)與 `@property today -> str`(`self._now_fn().date().isoformat()`,與 `today_signals()` 聯集日同時鐘);
  route 回 `{"signals", "trade_date": hub.trade_date, "today": hub.today}`(**不**用 `_today()`);取樣錯位一拍在 stage2 瞬間可接受,註解記。
- **AR5 唯一 prop 形 + SC-2 重寫**:`SignalRail` 兩 optional prop `tradeDate?: string | null` / `today?: string | null`,rail 內算標題;
  SC-2:tradeDate=today → 「今日訊號」;tradeDate=`2026-08-20`、today=`2026-08-21` → 「08-20 訊號」(aria-label 同);任一 undefined/null → 「今日訊號」。
  StockPage.test:stub `/api/stock/signals/today` 回 `{signals:[], trade_date:"2026-08-20", today:"2026-08-21"}` → rail 標題「08-20 訊號」。
- **AR4 新鮮度**:`useSignalFeed` baseline query 加 `refetchInterval: 5 min`(自癒 baseline 本就可重取;WS open 重抓不變)→ 跨午夜 / stage2 rollover 後 ≤5 分更新標題。原 Edge case 1 作廢改寫。
- **AR2 SC-1 固定平日假日 payload**:正向 `today: "2026-10-09"`(週五、版控 config 內國定假日)+ `holidays: ["2026-10-09"]` → 膠囊;反向 holidays 不含;週末守門案 `today: "2026-08-16"`(週日)+ holidays 含它 → 不顯示。
  **在該 it 內覆寫 appFetch**,不改共用 stub。
- **AR8 週末判定**:`new Date(today + "T00:00:00Z").getUTCDay()`(或 split 組 UTC),明寫不用本機 `getDay()`。
- **AR3 SC-4 通道修正**:膠囊 = 前端測試(SC-1)為自動化證據,真環境截圖**不開側車**(verify 側車 calendar_loaded=false 無法顯示;改 prod config 不允許)→ `browser_unavailable: verify 側車無日曆` + user 過目說明。
  標題 = verify 側車 `TXO_SERVER_PORT=8722 TXO_BACKFILL_DATE=2026-08-20 python -m copycat.server --verify`(fake TXO,其餘引擎不啟)—— 但 signals route 需 hub;若 verify 模式無 hub → 以 StockPage.test 為證據 + 同樣標 browser_unavailable。
- **AR9 Out of scope**:tick 層 `stock_models.is_trial`(丟棄語意)維持純時間窗不接日曆;R9 補班漏設情境症狀 = 報價凍住 + 無 (緩),記 next-time。

---
## Code review round 1 amendments(`code-review-round-1.json`)
- **D2'' 膠囊條件(C-2 / C-3)**:`data.calendar_loaded && data.calendar_trade_date !== data.today && !isWeekendIso(data.today) && data.today === isoLocalDate(new Date())`
  (後端同源「今天非交易日」判定涵蓋補班日;最後一項為 stale 保險絲:payload 跨日未更新 → 寧可不亮)。
- **route 取樣順序(C-1)**:`trade_date` / `today` 在 `await to_thread(today_signals)` **之前**取樣(錯位只錯向舊日)。
- C-5 / C-4:docstring 註明窗的時鐘不吃 `now_fn`;useSignalFeed 註明 ≤5 分前提為分頁可見、與 daily_bars 同 executor。C-6:`stale = Boolean(tradeDate) && Boolean(today) && tradeDate !== today`。
