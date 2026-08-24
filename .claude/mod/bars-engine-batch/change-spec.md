# R7 bars/引擎後端批 — change-spec

需求真相源:`docs/superpowers/specs/2026-08-24-do-batch-rounds.md` §R7(15 條,user 全勾「做」、無附註)。
分支 `mod/bars-engine-batch`。本 session **零 TC4 / 零 ZMQ**(ops-discipline 盤中驗證通道節),
所有測試一律 fake source。

---

## §0 既有行為白名單(caller map + 不得因本輪變鬆的取捨)

### 0.1 caller map(grep 實據)

| 動到的產生點 | caller(含動態用法) | 本輪處置 |
|---|---|---|
| `stock_source.fetch_daily_bars` | `server/stock_engine.py:682 daily_bars`(→ route `/api/stock/overlay/{code}` n=25、`signal_hub._resolve_basis` n=5)、Protocol `stock_engine.py:188`、fake `tests/helpers/fake_sources.py:244`、`tests/server/test_calendar_wiring.py:76`、`tests/server/test_stock_engine.py:131`、`tests/server/test_stock_routes.py:342/405` | 簽名不動,只動內部視窗與 raise 判準 |
| `futures_engine.bars_range` | 唯一 caller `server/app.py:1616`(market route);測試 `tests/server/test_futures_engine.py`(3 處)、`tests/server/test_market_routes.py`(經 route) | 回傳型別 `list[Bar]` → `BarsResult`(N104) |
| `_market_payload` | `app.py:1592 / 1594 / 1640 / 1648`(全部在 `market_bars` route 內) | 新增 keyword-only `status`,預設 `"ok"` |
| `build_minute` | `app.py:1631`(market)、`app.py:1317`(stock bars route,已接第二元素) | 只有 market 那處改成接第二元素 |
| `IndexEngine._subscribe_and_backfill` | 同檔 `_retry_loop:275`(唯一) | 加 pending 分流(N107) |
| `SignalHub(daily_bars=...)` | `app.py:697`(prod 與 `_empty_daily_bars` 替身)、`tests/server/test_signal_hub.py` 多處 | 型別放寬成 `... | None`(N110) |
| `corr_config.DEFAULT_CONFIG` | `corr_config.load_config` 四條降級路徑、`server/corr_engine.py` 經 `load_config`;測試 `tests/test_corr_config.py` | legs 補 NK225M(N021) |
| `/api/calendar` payload | 前端 `hooks/useTradingCalendar.ts`(→ `lib/trading-calendar.setHolidays`)、`components/CalendarHolidayBadge.tsx`、型別 `types.ts::CalendarState` | additive 加 `extra_trading_days`(N090) |
| `RiverState.push / apply_backfill` | `server/corr_engine.py`(江波圖同一報價流)、`live/river_backfill.py` 結果 apply | 內部加 end 格名次帳 |

### 0.2 既有取捨(本輪一律不變,review 請對 diff 核)

1. **`bars.py` 三層 cache 全數不動**:歷史段 memo 「回空不入 memo」(`build_minute:521-523`)、
   負向快取 `_empty` 只在兩段皆空時標且 15 s TTL、`put_hist_range` 只寫到有證據掃過的最後一天、
   午夜緩衝 `MIDNIGHT_BUFFER_END`、複合鍵 `f"{code}:{session}"`、`_possible_data_days` 過濾。
   本輪對 `bars.py` **零 diff**(只在 route 端多接一個既有回傳值)。
2. **`fetch_bars_range_tagged` 逐字不動**:90 日 fallback 窗、`dk_timed_out or fb_timed_out` 取最壞。
3. **`fetch_daily_bars` 在 `n=25`(所有既有生產 caller 的預設)時視窗逐字 40 日**。
4. **`futures_source.fetch_bars_range` 的 raise 語意不動** —— 降級仍只發生在 engine 層。
5. **index watchdog 窗 09:00–13:25 不動**(`_in_watch_window` 只服務 watchdog / stale);本輪只動 heal 窗。
6. **`_swap_day` 的 `{**backfill, **_pending_minutes}` 覆寫順序不動**(live pending 勝過回補)。
7. **RiverState**:換場清空、同分鐘 last-write-wins、「回補只補空缺」對**非 end 格**逐字不變。
8. **SignalHub** 既有 basis 有限重試 / `_stale` 日別尺 / cache 經由 `_basis_cache` 的收斂點不變。
9. **market route** 的 `BAD_KEY / BAD_TF / INVALID_SESSION / BAD_DAYS` 值域檢查、OTC 合成分支、
   TWSE↔futures 分派、cache code 的 `|M` / `|L` 後綴不變。
10. **`/api/calendar` 既有欄位語意不變**(`trade_date` vs `calendar_trade_date` 的分帳、`years_loaded`
    語意、`holidays` 升冪),新增欄位純 additive。
11. **`CalendarHolidayBadge` 既有三道否決不變**:`!calendar_loaded` / `calendar_trade_date === today` /
    本機日保險絲(`data.today !== isoLocalDate(new Date())`)。

### 0.3 事前標「該變」的既有 assertion(只有這幾條可以改)

| 測試 | 為何該變 |
|---|---|
| `tests/live/test_stock_source.py::test_dk_ready_but_empty_plus_1k_timeout_returns_empty` | N019 條文已標:它鎖的是窄路徑錯誤行為 |
| `tests/live/test_river_state.py::test_clamp_approximation_blocks_the_real_close_bar` | N058 條文已標:characterization,改時該紅 |
| `tests/server/test_futures_engine.py::TestBarsRangeProxy` 三案的 `got == []` | N104 改的正是 `bars_range` 的回傳形狀;這三條斷言的是舊形狀本身 |
| `tests/server/test_market_routes.py::TestMarketPayloadUnaffectedByBarsStatus::test_market_payload_has_no_status_field` 的 `"status" not in body["meta"]` | N104 加的正是 `meta.status`;該案的另一半守門(`meta.source` 不得變成 status 字)由同 class 的 `test_meta_source_is_never_a_status_word` 完整保留,**那條一字不動** |

| `tests/server/test_calendar_wiring.py::TestCalendarRoute::test_payload_with_calendar_on_saturday` 的 `set(body) == {...}` | N090 additive 加 `extra_trading_days`;鍵集合鎖正是 additive 改動要動的那一格(其餘欄位斷言一字不動) |
| `tests/test_corr_config.py` 的 `test_has_six_legs` / `test_non_base_legs_are_tc4_subscriptions`(`len(others) == 5`)/ `test_repo_config_first_six_legs_match_default` / `test_seventh_leg_added_without_engine_change`(`len == 7` 改成相對長度)/ `TestRepoConfigFile` docstring 的「仍六腿」 | N021 條文明寫 DEFAULT_CONFIG 要補 NK225M;這五處全部是「預設有幾腿」的直接函數 |

其餘既有測試一律不得改。

---

## §1 逐條處置

### N019 🔴 `fetch_daily_bars` AND → 只看 `fb_timed_out`
`stock_source.py:753` 的 `if dk_timed_out and fb_timed_out: raise` → `if fb_timed_out: raise`。

判定:`dk_timed_out` 在生產上幾乎恆為 True(DK 首頁空即 `timed_out=True`),AND 的另一半
只在「DK 首頁非空但整批解析不出 bar」時為 False —— 那是**解析面**的失敗,不是「資料面就是
沒有」,回空會讓 SignalHub 讀成「無已完成日 K,CDP 停用」且整天不重試。1K 首頁未備妥是 TC4
協定側唯一的暫時性訊號,拿它當唯一判準即可。既有 `test_dk_timeout_still_falls_back_to_1k`
(1K 首頁非空 → `fb_timed_out=False`)不受影響,DK 逾時仍走 fallback 不 raise。

### N024 🔴 `fetch_daily_bars` 視窗改成隨 `n` 縮(overlay 的 n=25 逐字不變)
`_DAILY_WINDOW_DAYS` 保留為**上限**,新增地板 `_DAILY_WINDOW_MIN_DAYS = 20` 與
`_daily_window_days(n) = min(40, max(20, ceil(n*1.6)))`。DK 段與 1K fallback 段共用同一個窗
(兩段本來就同窗,分開只會讓「DK 有 / 1K 沒有」在不同期間裡各說各話)。

**沒有真實列數量測就不動的那一半**(條文要求「要動之前先量一次真實列數」;本 session 零 TC4):
`n=25` 那條路(`/api/stock/overlay/{code}` 與 `stock_engine.daily_bars` 預設)**維持 40 日**。
理由不是「沒量」而是**可證不安全**:消費端 `overlay.build_overlay` 要 `ma20`,需要 20 根
**已完成**日 bar;40 日曆日 ≈ 25–28 個交易日,遇春節(連假 ~9 天)只剩 ~23 根,餘裕本來就只有
個位數。再縮窗的失效樣態是「ma20 靜默變 null」——畫面上只是少一條線,零錯誤訊號。

真正吃收割量的是 `n=5` 的 basis sweep(自選 50 檔每個交易日至少一輪 + 有限重試),而 CDP 只要
最後一根已完成 bar → 20 日窗綽綽有餘(春節 20 日 − 9 = 7–8 個平日仍 ≥ 5)。

理論列數上界(供 verification 的盤中量測對照):個股 1K 域 09:01–13:30 = 270 分 + 13:31–13:35
收盤補正 ≈ **≤275 列/交易日**。40 日窗 ≈ 25–28 交易日 → **≤ ~7,700 列**;20 日窗 ≈ 12–14 交易日
→ **≤ ~3,850 列**(−50%)。空結果依 `overlay.py` 規則不進 cache,DK 不支援的股號每次請求都重付。

### N104 🔴 期貨 K 線三態 status 通道(**前後端新契約**)
四層一起改:

1. `futures_source.fetch_bars_range` **不動**(仍 raise `HistoryTimeoutError`)。
2. `futures_engine.bars_range` 回傳 `list[Bar]` → `BarsResult(bars, status)`:
   `HistoryTimeoutError` → `("timeout")`、其餘 `ConnectionError` → `("disconnected")`、
   source 未建/不支援(proxy miss)→ `("disconnected")`、正常 → `("ok")`。
   既有兩條固定 log 字串逐字保留(3am 判準不變)。
3. `app.market_bars`:futures 分支的 `plain_with_status` 改成直接吃 engine 的 status(不再硬寫 "ok");
   `tf == "1"` 那條改成 `bars, status = await build_minute(...)`(第二元素不再丟棄),
   `_market_payload(..., status=status)`。
4. `_market_payload` 新增 keyword-only `status: BarsStatus = "ok"` → `meta.status`。
5. 前端 `BarsMeta.status?: "ok" | "timeout" | "disconnected"`(**optional**,舊 payload 不炸);
   `FuturesChart` 的 `source === "unavailable"` 空態依 status 分三句話。

**scope 界**:`tf != "1"`(D/W/M,走 `build_period`)仍固定 `"ok"` —— `build_period` 回的是
`TaggedBars` 沒有 status 欄,把它一起三態化要動 `bars.py` 的 cache 型別(白名單 §0.2-1)。
TWSE / OTC 兩鍵同理固定 `"ok"`(`index.bars_range` 回的是 `(bars, tag)`)。

**與 2026-08-25 出貨的 gate 5 分工(兩者並存不合併)**:
- `meta.status` = **這一次回補請求的結果**(TC4 首頁備妥了沒 / 連線在不在)。來源 = 後端這一趟
  `fetch_bars_range` 的協定側訊號;空序列時才被讀出來(空態文案)。
- gate 5「分時資料落後 N 根(TC4 回補中)」= **資料尾 vs WS 最後成交**的落差。來源 = 前端把
  已到手的 bars 尾端跟 `state.t` 比;bars **非空**時才可能成立。
兩者的定義域幾乎互斥(一個講「這趟沒拿到」、一個講「拿到的不夠新」),合併成一個旗標會讓
「TC4 忙」與「回補缺尾」共用一句話,而它們的處置不同(前者等重試、後者看資料完整性)。

**CLAUDE.md §4 登錄**(產生點 / 讀者 / 漂掉症狀)一併寫入。

### N020 🔵+🟢 `phase` / `attempts_max` write-only + `buffer is None` 路徑無測
- 🔵 `engine.py:278-282` 的註解引用了不存在的 UI 症狀(「badge 掛著回補中(第 n 次)」)——
  badge(`ConnectionBadge.tsx`)只在 `status === 'backfilling'` 時印,`phase` 沒有任何前端讀者。
  改寫成事實:`phase` / `attempts_max` 是 **`/api/txo/state` 的診斷欄**(值班用),
  唯一前端讀者是 `attempt`(CLAUDE.md §4 已登錄)。
- 🔴 尾段 `_set_status("degraded")`(`engine.py:335`)同時把 `phase` 降成 `"degraded"`:
  `buffer is None` 那條防禦性路徑走到迴圈盡頭時 `phase` 會停在 `"backfilling"` 而 status 已
  `degraded` —— 「phase 與 status 同義」這條 SC-1 不變式在唯一沒被測到的路徑上不成立。
- 🟢 補該路徑的測試(monkeypatch 讓 buffer 被吞掉)。

### N105 🔴 盤外時段啟動踩 timeout 無自癒
heal 窗 `_in_watch_window() or _WATCH_END <= now < _HEAL_TAIL_END` →
`(_in_watch_window() or now >= _WATCH_END) and _is_trading_day(_today_fn())`。

- 尾窗上界 13:40 拿掉 = 盤後 / 晚間啟動踩到 1K timeout 時當晚就自癒,不必等次日 09:06。
- `_minutes_lag_exceeded` 的 `min(now, _HEAL_TARGET_MIN)` 封頂**已經**是條文要的
  「窗外以 min(now, 13:30) 為期望覆蓋終點」,detector 一行不改。
- **休市日恆空的輪詢噪音**(條文明寫)由新增的 `_is_trading_day` 閘處理:假日 / 週末
  minutes 恆空 → 舊碼在 09:04 之後整個 watch 窗每 60s→900s 空打,新碼一發都不打。
- 09:00 之前不觸發:空 minutes 以 09:00 起算,`now_min - 540 > 3` 在 09:04 之前恆偽,
  gate 那半邊也還沒開(`now >= 13:25` 偽、`_in_watch_window()` 偽)。
- 代價:交易日晚間若 TC4 整晚拿不到當日 1K,heal 會以退避(60s 起、封頂 900s)持續到隔日
  00:00 ≈ 40 發 UNSUB→SUB。舊碼是 0 發但線整晚空著 —— 這正是本條要換的東西。

### N107 🔴 pending 期間 retry 把新日 1K merge 進舊日 dict
`_subscribe_and_backfill` 依 `_pending_date` 分流:pending 時寫 `_pending_minutes`
(`{**minutes, **self._pending_minutes}` —— 與 `_swap_day` 的 `{**backfill, **pending}` **同一個
覆寫方向**:live pending 勝過回補),進展判定也改比 `_pending_minutes` 的鍵集合。
非 pending 逐字不變。既有 `test_pending_retry_does_not_broadcast_minutes`(廣播面 T-1 修復)
不受影響,本條補的是 **`state()` 面**:swap 前 ≤60s 內重整頁面不再拿到混日 minutes。

### N110 🔵/🔴 無 engine 時 basis job 的 50 行「CDP 停用」warning
`SignalHub` 的 `daily_bars` 型別放寬成 `... | None`,`None` = **沒有日 K 來源**:
`request_basis` 整批早退(一行 INFO,固定字串 `CDP 基準:無日 K 來源`)。
→ `app._empty_daily_bars` 與它配套的 `basis_gap_secs=0.0` hack 一併刪除(那個 hack 的存在
理由就是「假的取數路徑會回 True 讓 worker 付 gap」)。

判定理由:條文候選是「hub 加模式分支」,但用 `None` 表達「沒有這個能力」比用一個恆回空的
假 callable 淺 —— 恆回空的替身讓 hub 把「配置上沒有」讀成「這檔資料面沒有」,50 行 WARNING
正是那個誤讀的外顯。行為淨變化:無 engine 時不再逐檔 warning、不再排 job;有 engine 時零變。

### N101 🔵 `_quote_payload` docstring「四個產出點」漂移
現況 grep 實得 **8 處**:`stock_engine.py:505`(set_watchlist 新增種子)/ `:622`(quotes() Discord
摘要,取 `chg_pct`)/ `:829`(retry 重掛後補種子)/ `:957`(`_handle_no_data`)/ `:1112`(轉態補推)/
`:1425`(連線 seed)/ `:1457`(試撮窗翻轉補推)/ `:1463`(1s flush)。docstring 改成「**唯一** builder;
產生點以 grep 為準(現況 8 處)」+ 列出判準,不再寫死一個會漂的數字。

### N058 🔴 江波圖 end 格 clamp 近似值擋掉真收盤 bar
`RiverState` 新增 per-leg `_end_rank`(end 格內容的收盤補正名次;0 = 真值 / 非 clamp 來源)。
`apply_backfill` 對 **end 格且 `_end_rank >= 2`**(= 13:46 以後的殘留近似)覆寫一次,寫完把
名次歸 0(第二次回補就不再覆寫,「覆寫一次」)。
`rank == 1` 刻意**不覆寫** —— 那是收盤撮合那一分鐘的真成交(`push` 的既有註解:必須寫得進來),
不是近似。

### N015 🔴+🟢 clamp 守門改「名次小者贏」+ 跨午夜表補四格
- 🔴 `river_state.push` 的守門 `rank >= 2 and offset in minutes` →
  `rank >= 2 and offset in minutes and rank >= self._end_rank[key]`:名次小者(較接近收盤)贏。
  現況一旦 13:48 先寫進去,13:46 那筆(更接近真收盤)就永遠擠不進來。
- 🟢 `tests/server/test_main_wiring.py::TestHealGateAcrossMidnight` 補四格:
  週五 23:00 / 週六 23:00 / 週日 01:00 / 週一 08:50。
- **未做**:「R5 封關夜近似誤差(次一營業日休市的夜仍空 churn)」條文自己寫的是「獨立開條」,
  且要引入「下一交易日」判定(`_session_date` 目前刻意不做,方向安全)—— 不在本輪,見 §留尾。

### N016 / N090 / N091 🔴 三顆膠囊(前端)+ 一個 additive 欄位(後端)
- 後端 `/api/calendar` additive 加 `extra_trading_days`(N090 條文明列的候選)。
- 前端 `CalendarHolidayBadge.tsx` 改成同一份 payload 餵三顆獨立膠囊:
  1. **既有**「日曆判今日休市」——**唯一改動** = 週末守門從「週末一律靜音」改成
     「週末且**今日不在 `extra_trading_days`** 才靜音」。設對的補班日後端會判交易日(不亮),
     所以這條只會在「補班日已設定卻沒生效」時亮 —— 那是真的不變式違反。
  2. **新**「交易日曆過期」(N016):`calendar_loaded && !years_loaded.includes(today 的年份)`。
     日曆缺當年 = 此後只擋週末,現況零提示。
  3. **新**「TXO 回補日鎖定」(N091):`backfill_env !== null`。忘了清 env 會整盤凍結,payload
     早就有這個欄位只是沒人讀。
- **未做(N090 的偵測面)**:「補班日**漏設**」在前端無法與「普通週末」區分 —— 兩者的
  payload 完全相同(後端判非交易日、該日不在 `extra_trading_days`)。要偵測需要一個獨立於
  日曆的「今天有沒有在成交」訊號,不在本輪 scope,見 §留尾。

### N021 🔴+🔵 corr 預設腿缺 NK225M + 四條 logger 文案
`DEFAULT_CONFIG.legs` 補 `Leg("NK225M", "小日經", "TC.F.OSE.NK225M.HOT", SOURCE_TC4)`
(與 `configs/correlation.json` 對齊 —— 設定檔壞掉退回預設時江波圖 / 相關係數不再真的少一腿);
`:97/100/104/108` 四條 logger「改用預設六腿」→「改用預設腿」。

---

## §2 backward compat

| 改動 | 相容性 |
|---|---|
| `meta.status`(N104) | **additive**。舊前端讀不到 `status` → `data.meta.status === undefined` → 走既有 `unavailable` 文案,逐字退回現況 |
| `/api/calendar.extra_trading_days`(N090) | **additive**。既有讀者(`useTradingCalendar` 只讀 `holidays`)零影響 |
| `futures_engine.bars_range` 回傳型別 | **內部**(唯一 caller 在同 repo);`BarsResult` 是 NamedTuple,`bars` 仍是第一元素 |
| `SignalHub(daily_bars=None)` | 型別放寬,既有呼叫點全部照舊傳 callable |
| `fetch_daily_bars` 視窗 | `n=25` 逐字不變;`n<=12` 才縮 —— 唯一走小 n 的是 `_BASIS_BARS=5` |
| `RiverState` end 格名次帳 | 純內部欄位;`snapshot` / `delta` 形狀零變 |

## §3 seams(測試落點,與 §0 caller map 對齊)

| 條 | seam | 檔 |
|---|---|---|
| N019 / N024 | `StockQuoteSource.fetch_daily_bars`(FakeApi 電文層) | `tests/live/test_stock_source.py` |
| N104 engine | `FuturesEngine.bars_range` | `tests/server/test_futures_engine.py` |
| N104 route | `GET /api/market/bars/{key}?tf=1`(TestClient) | `tests/server/test_market_routes.py` |
| N104 前端 | `FuturesChart` 渲染(RTL) | `frontend/src/components/futures/FuturesChart.test.tsx` |
| N020 | `EngineRuntime` 交接(fake source) | `tests/server/test_engine.py` |
| N105 / N107 | `IndexEngine`(FakeIndexSource + 注入時鐘) | `tests/server/test_index_engine.py` |
| N110 | `SignalHub`(daily_bars=None) | `tests/server/test_signal_hub.py` |
| N058 / N015 clamp | `RiverState` 純狀態機 | `tests/live/test_river_state.py` |
| N015 跨午夜表 | `app._heal_gate` | `tests/server/test_main_wiring.py` |
| N090 後端 | `GET /api/calendar` | `tests/server/test_calendar_wiring.py` |
| N016/N090/N091 前端 | `CalendarHolidayBadge` 渲染(RTL) | `frontend/src/components/CalendarHolidayBadge.test.tsx`(新檔) |
| N021 | `corr_config.load_config` / `DEFAULT_CONFIG` | `tests/test_corr_config.py` |
| N101 | 純 docstring,無 seam | — |
