# change-spec — mod/trading-calendar

來源:`docs/superpowers/specs/2026-08-15-user-feedback-batch2-rounds.md` §2 R3(user 已拍板文件 → 預核准;
D9 default)。現況:`current-state.md`。規模:**L**(≥ 5 檔、跨前後端、新對外端點)。
分流判定:已成形方案(指名模組 / 資料流 / 落點)+ 有可追問決策點 → grilling 姿態,逐題 `[auto-default]`。

## 0. 拍板題(全部 auto-default;無方向性抉擇)

- Q1 日曆注入方式:`create_app(trading_calendar=None)` 預設 None = 牆鐘(現行);`__main__` prod 顯式傳
  `load_trading_calendar()`;verify 模式不傳(fake 資料綁牆鐘 today)。
  `[auto-default: 可選注入 | reason: 39 個測試呼叫點以 date.today() 對照,預設載真日曆會在週末全紅;
  對齊 DEFAULT_STOCK / DEFAULT_BREADTH「prod 顯式、測試預設關」慣例]`
- Q2 驗證端點:新 `GET /api/calendar` 而非改 `/api/health`。
  `[auto-default: 新端點 | reason: health docstring 明訂「刻意不含引擎健康度、只答版本」;前端也要吃假日集合,
  一個端點兩用]`
- Q3 交易日盤前(00:00–08:30)是否回前一日:**不動**。`[amendment 2026-08-16 R8: 事實更正]` 「盤前顯示昨日」
  只對**長跑中**的 server 成立(兩段式 rollover stage2 前不清狀態);**交易日盤前冷啟動**仍是空圖到 09:00
  (source 日窗 = 今天)。本輪維持不做:origin prompt 明寫「盤前不動、只處理今天非交易日」,納入會改動三引擎
  的時序(stage1 08:00 / index 08:30 / streak 06:00 都要重對齊)屬方向性擴張 → 入 Out of scope + KR-4 +
  next-time,收尾回報請 user 決定是否開 R3b。`[auto-default: 只處理「今天非交易日」]`
- Q4 index rollover 日曆錯標(真交易日被標假日)自癒:**不加 tick 回退**,以 (a) 官方 JSON 來源、(b) 缺年
  只擋週末(永不多擋)、(c) boot DK 交叉檢查 WARNING、(d) 手動 `TXO_BACKFILL_DATE` 通道 兜底。
  `[auto-default: 不加 | reason: TC4 訂閱首則快照會帶前一交易日 FilledTime,拿「收到推播」當證據會在每個
  週末誤報;stock 側本就有 tick 快路徑自癒]`
- Q5 config 形狀:`{"_source","_updated","years":{"2026":{"holidays":[...],"extra_trading_days":[]}}}`。
  `extra_trading_days` 供未來補班交易日(2026 無;純模組零成本支援)。`[auto-default]`
- Q6 壞檔處置:檔缺 → 只擋週末 + WARNING;JSON 壞 / 形狀錯 → raise(對齊 signals_config「檔缺=預設、壞檔 raise」)。`[auto-default]`
- Q7 前端注入:`lib/trading-calendar.ts` 模組級假日集合(`setHolidays` / `isTradingDay`),三支 hours 函式改讀它;
  App 掛一支 `useTradingCalendar` query(staleTime ∞)成功即 `setHolidays`。未載入 = 空集合 = 現行只擋週末。
  `[auto-default: 模組級集合 | reason: 5 個 refetchInterval callback 呼叫點零改動;測試 beforeEach 清空]`
- Q8 breadth 非交易日:`_in_window` 加 `is_trading_day(now.date())`;首圈仍無條件跑(counts 要有數字)。`[auto-default]`
  `[amendment 2026-08-16 R4]` `_in_window` 有兩個呼叫端(`_poll_loop:349` / `_stale:594`),**兩者都吃**交易日 gate:
  非交易日「沒有新資料是正常態」與 docstring 窗外語意同款;若 `_stale` 保留純時間窗,週六窗內首圈成功後
  `_last_success` 老化會亮假「延遲」膠囊。舊的「假日 adopt_date=False → stale=True」訊號在新 today_fn 下不再
  發生(restore 日 = 快照日 = 最近交易日,走同日路徑)。
- Q9 `[amendment 2026-08-16 R6]` app 層兩支日期函式,**逐一標注消費端**:
  - `_today() -> date`:牆鐘。消費端:`/api/calendar.today`、K 線 / market bars(不動)、index overlay 的
    `build_period`(bars 抓取,不動)。
  - `_resolve_trade_date() -> str`:`env TXO_BACKFILL_DATE or resolve_trade_date(_today(), cal).isoformat()`
    (cal None → `_today()`;`[amendment R2-2]` **必經 `copycat.trading_calendar.resolve_trade_date`**,缺年
    WARNING 的節流入口就在那裡)。消費端:stock / index `trade_date`、hub fallback `_wall_clock_trade_date`
    (每次求值)、`/api/stock/overlay/{code}` 的 `build_overlay` today 與 `OverlayCache` 鍵、`/api/index/overlay`
    **只改 `build_overlay` 的 today(維持不經 overlay_cache,`[amendment R2-5]`)**、`/api/calendar.trade_date`。
  - breadth `today_fn = lambda: resolve_trade_date(_today(), cal)`(**純日曆、不吃 env** —— breadth 現行本就不讀
    env,W2 的 env 優先域不含 breadth;`[amendment R2-2]` 同樣經 `resolve_trade_date`);`is_trading_day = cal.is_trading_day`。

## 1. 成功條件

- **SC-1** 純模組:`is_trading_day` / `last_trading_day` / `load_trading_calendar`(檔缺 → weekend-only + WARNING;
  壞檔 raise;extra_trading_days 生效);缺當年 WARNING **在 resolve 時每個年份節流一次**(長跑跨年也會提醒;
  `[amendment R11]`)。**資料測**(`[amendment R11]`):載入版控 `configs/trading_holidays.json` 後 2026 假日數 = 18、
  清單內無週末日期、抽驗 01-01 / 02-16 / 10-09 為非交易日、08-14 為交易日、`last_trading_day(2026-08-16) == 08-14`、
  `last_trading_day(2026-02-22) == 02-11`。
  驗證:`tests/test_trading_calendar.py` 全綠。
- **SC-2** 引擎假日冷啟動:`create_app(trading_calendar=cal, ...)` 且 `_today()` = 週六(2026-08-15)→ stock / index
  `trade_date == "2026-08-14"`;env `TXO_BACKFILL_DATE` 有值時 **stock / index / hub fallback** 以 env 為準,
  breadth 仍走純日曆(`[amendment R2-1]`;breadth 現行本就不讀 env,見 KR-5)。`[amendment R10]` 另斷言
  fake index source(`fetch_day_minutes` 依 `set_trade_date` 值回不同資料)冷啟動後 `/api/index/state` 的
  `twse.minutes` 非空且為 08-14 那份;fake stock source 收到的 `set_trade_date` == "2026-08-14"。
  驗證:`tests/server/test_calendar_wiring.py`(monkeypatch app 模組的 `_today` 取樣點)。
- **SC-3** index:非交易日 `_rollover_loop` 不設 pending、不 `set_trade_date`、不 `fetch_day_minutes`;交易日語意不變。
  驗證:test_index_engine 新增 `test_rollover_skips_non_trading_day`;既有三條 rollover 測試不紅。
- **SC-4** stock:`_checkpoint_loop` 以注入的 `is_trading_day` 判定(預設 = weekday<5 逐字不變);假日不 stage1。
  驗證:test_stock_engine 新增 checkpoint 測(注入 now_fn + is_trading_day)。
- **SC-5** breadth:today_fn = 最近交易日時,週六冷啟動 `_restore` 讀 `breadth-2026-08-14.json` 還原週五序列;
  `_in_window` 在非交易日恆 False(首圈仍跑一輪);**假日 poll 次數下降**(assert 窗內第二輪起 fetch 不被呼叫);
  `[amendment R4]` 週六窗內首圈成功後 `state()["stale"] is False`(非交易日不亮延遲);
  `[amendment R5]` streak 回歸:today_fn=週五(08-14)、restore `streaks-2026-08-14.json`(data_end=08-13)、
  rows_date=08-14 → 某檔 `streak` 值與「週五盤中(today=08-14、同一份快取)即時算出」逐字相同(走 `>` 分支 +1);
  `rows_state` docstring 「盤前 / 假日開站」段同步改寫。
  驗證:test_breadth_engine 新增 4 測。
- **SC-6** `GET /api/calendar` `[amendment R7]` →
  `{"today": <牆鐘 ISO>, "trade_date": <env or 日曆推導 = 引擎實際採用>, "calendar_trade_date": <純日曆推導>,
  "backfill_env": <env 原值或 null>, "holidays": [...ISO], "years_loaded": [int], "calendar_loaded": bool}`;
  無日曆(tests 預設)→ `holidays=[]`, `years_loaded=[]`, `calendar_loaded=false`, `calendar_trade_date == today`。
  `[amendment R2-6]` payload docstring 明寫:`trade_date` = stock / index / signals hub 實際採用;**breadth 一律採
  `calendar_trade_date`**。
  驗證:test_calendar_wiring 路由測(含 env 設定時 `trade_date == env` 且 `calendar_trade_date` 仍為日曆值,
  且 breadth `rows_state()["trade_date"]` / today_fn 為日曆值的對照);
  真實環境 `curl localhost:8721/api/calendar`(斷言含 `backfill_env: null`)。
- **SC-7** boot 交叉檢查 `[amendment R9: 雙向]`:index 啟動後(有日曆時)取 IX0001 DK 最後一根日期 `d`:
  `d > last_trading_day(today)` → WARNING「交易日曆可能過期(DK 有 %s 但日曆判非交易日)」;
  `expected = last_trading_day(today)` 若(today 非交易日 或 now ≥ 14:00)否則 `last_trading_day(today − 1)`
  (交易日盤前 / 盤中今天的 DK 尚未存在,不可拿今天當期望);`d < expected` → WARNING「最近交易日 %s 無 DK
  資料(臨時休市?請設 TXO_BACKFILL_DATE 或更新日曆)」;bars 空 / fetch 失敗只 log 不影響 index 啟動。
  實作落點 `[amendment R2-7]`:`app.py` `_start_index` wrapper 內、`await o.start()` 之後,
  `asyncio.create_task(_calendar_crosscheck(o))` **背景跑、不擋序列 boot 鏈**(task 參照存 `booted` 或
  app.state,關機時 cancel);probe **直呼 `o.bars_range("D", (today−14d).isoformat(), today.isoformat())`**
  不經 `bars_cache`(避免用 boot 當下結果污染共用格);自吞一切 Exception 只 log(`_boot` 的傘不得因它把
  index 收掉)。
  驗證:test_calendar_wiring(三情境:DK=today 而日曆標假日 → 過期 WARNING;DK 停在更早一天 → 臨時休市
  WARNING;fetch raise → index 仍在 app.state 且無 WARNING 之外的例外)。
- **SC-8** `__main__` prod 傳 `trading_calendar=load_trading_calendar()`;verify 不傳。驗證:test_main_wiring 更新
  (🔴 該紅)。
- **SC-9** 前端:`isTradingDay(d)` = 非週末 且 不在假日集合;`inTradingHours` / `inFuturesTradingHours` 與
  `inFuturesAllDayHours` 的 08:40–13:50 / 14:55+ 分支 → `isTradingDay(now)`;`[amendment R1]`
  `inFuturesAllDayHours` 的 **00:00–05:05 分支 → `isTradingDay(now − 1 天)`**(該段屬前一日夜盤;現行
  `day >= 2 && day <= 6` 的等價週末語意保留,只疊加假日否決)。週末語意不變;`useTradingCalendar` 成功後 set。
  驗證:vitest 新增 trading-calendar.test.ts(含:週六 01:00 → true;假日(平日)當天 10:00 → false;假日
  次日 01:00 → false;假日前一日 01:00 → true 若前一日的前一日為交易日)+ trading-hours 既有測不紅。
- **SC-10** LimitList `[amendment R3/R12]`:(a) `data.trade_date` ≠ 本機今日 → 標題列 `as_of` 旁顯示日期膠囊
  「`MM-DD` 收盤」(畫面可指認:漲跌停列表標題列 stale 膠囊同排、灰底小字;`[amendment R2-8]` testid
  **`limit-list-asof-date`,不得沿用 `limit-list-stale`**;新測同時斷言 `limit-list-stale` 為 null);等於今日 → 不顯示;
  (b) `pool === 0` 空態:非今日 → 「`MM-DD` 尚無漲跌停」,今日 → 「今日尚無漲跌停」。
  驗證:LimitListSection.test 新增 2 條(非今日膠囊 + 非今日空態文案);既有 :234 **該紅**(fixture
  `trade_date: "2026-08-06"` ≠ 本機今日)→ 修法:`mkState` 的 `trade_date` 改為動態本機今日 ISO(fixture
  語意「今日資料」不變),原斷言文字不改。
- **SC-11** 真實環境(**驗證窗口:今天 2026-08-16 週日即可**):重啟 prod server 不帶 env →
  `curl /api/calendar` `trade_date == "2026-08-14"`;個股單檔分時、群組圖牆、台股綜合加權/櫃買分時 + 家數帶
  三頁非空截圖 → `evidence/`;user 過目。窗口外降級:不適用(週末 = 窗內)。
- **SC-12** 文件:CLAUDE.md §1 表格 TXO 看盤 server 一列改寫(非交易日自動;env 為手動覆寫;TXO 面與**交易日
  盤前冷啟動**仍需 env;`/api/calendar.years_loaded` 不含當年 = 日曆過期要更新 config);
  `docs/next-time.md:537` 勾銷 + 新增 TXO 面 / 試撮(緩)badge / 交易日盤前冷啟動(R8)三條留尾。
- **SC-13** `[amendment R2]` overlay 基準日 = 顯示中的交易日:週六 `_today()`=08-15 時 `/api/stock/overlay/2330`
  的 `date == "2026-08-13"`(基準 = 08-14 之前最後一根)且 `OverlayCache` 鍵為 08-14;加權 overlay
  (`/api/index/overlay`,app.py:1211-1238;`build_period` 的 today 仍牆鐘、只換 `build_overlay` 的 today、
  維持不經 overlay_cache)同款;`[amendment R2-9]` **env 未設**的交易日逐字不變(`_resolve_trade_date()` == today);
  env 設定時 overlay 基準日一併切到 env 日(與 stock / index trade_date 同源,本輪刻意對齊)。
  驗證:test_calendar_wiring 兩條路由測 + env 設定日一條。

## 2. 不能破壞的既有行為白名單(§5 自評 finder 必附此節)

- W1 交易日盤中一切不變:trade_date 仍是今天;stock 兩段式 rollover(stage1 08:00 / 快路徑 / stage2 首筆)、
  index 08:30 門檻 + pending buffer + swap 語意逐字不變。
- W2 `TXO_BACKFILL_DATE` 手動模式仍可用且**最高優先**(stock / index / hub fallback / TXO runtime);
  `checkpoint=env is None`、`rollover=env is None`、`session_rollover=env is None` 不變。
- W3 `[amendment R2]` K 線 endpoint(`/api/stock/bars`、`/api/market/bars`、index overlay 的 `build_period`
  bars 抓取)日期邏輯不動(牆鐘 today)。**overlay 的 `build_overlay` today 是 CDP/MA 基準日選擇器,不在
  W3 內** → 走 SC-13(交易日逐字不變)。
- W4 `[amendment R5]` breadth streak 的**演算法**不動(`_compute_streaks_once` 空回應 skipped、gap 檢查、memo、
  `_restore_streaks` 自洽檢查);但 today 基準改為最近交易日 → 假日開站時 `rows_state` 由 `rows_date == end`
  分支改走 `rows_date > end` 分支(prev 少一天 + 1,數值相同,由 SC-5 回歸測鎖住)。
- W5 FinMind 配額不增(假日 poll 下降;交易日 poll 節奏不變)。
- W6 create_app 39 個既有呼叫點零改動且語意不變(預設無日曆 = 牆鐘)。
- W7 `/api/health` payload 不變。
- W8 前端週末判定不變;未載入日曆時三支函式行為逐字同今日。
- W9 engine 直接建構(不傳新 kwarg)行為逐字不變(index 預設 is_trading_day=None → 純日曆日,同現行;
  stock 預設 → weekday<5,同現行)。

## 3. Out of scope

- TXO 面(`_default_source` backfill_date / `session_rollover` / tc4.py:404):TXO 有夜盤 session 語意,自動填
  固定日會把 rollover 關掉跨到週一 → 需獨立設計(留尾 next-time)。
- 試撮(緩)badge 假日純時間照標(next-time:97;第二段消除)。
- 交易日盤前(00:00–08:30)**冷啟動**顯示前一交易日(Q3 / R8):現況空圖到開盤;長跑 server 不受影響。
  留尾 next-time,收尾回報請 user 決定是否開 R3b(需對齊 stock stage1 08:00 / index 08:30 / breadth streak 06:00)。
- 補班交易日資料(2026 無;config 欄位已備)。
- 日曆自動更新 / 抓 TWSE(手動維護 config;缺年 WARNING 提醒)。

## 4. Edge cases

- E1 連假(2026-02-12 四 ~ 02-22 日)任一天冷啟動 → trade_date = 02-11。
- E2 週一 00:00–08:30 交易日盤前 → trade_date = 週一(不動,Q3);stock 08:00 checkpoint 才 stage1(現行)。
- E3 缺當年(2027-01-01 起未更新 config)→ 只擋週末 + WARNING 一次;元旦(四)冷啟動 trade_date = 01-01(空圖,
  與今日相同)但不崩。
- E4 `TXO_BACKFILL_DATE=2026-08-10` 在週日啟動 → stock / index / hub 08-10、checkpoint/rollover 關(現行);
  breadth 走純日曆 = 08-14(`[amendment R2-1]`;env 模式下畫面日別不一致為已知殘留 KR-5)。
- E5 週五 server 長跑到週六:stock checkpoint 週六不 stage1(現行 weekday 已如此)、index rollover 週六不
  pending(新;原本 pending 空轉)、breadth 週六窗內不 poll(新)。週一恢復照舊。
- E6 日曆錯標真交易日為假日:boot DK 交叉檢查 WARNING;stock 由 tick 快路徑自癒;index 當天不換日(Known Risk KR-1)。
- E7 `/api/calendar` 在 boot 窗內(引擎未起)也答得出來(純 config,不依賴 app.state 引擎)。

## 5. Diff 級(逐檔;🟢 新功能 / 🔴 行為改動 / 🔵 純重構;實作順序 🔵 → 🔴 → 🟢,但本案 🔴 依賴 🟢 模組,
故 🟢 純模組 + config 先落、再 🔴、最後 🟢 端點 / 前端 / 文案)

### 🟢 新增
- `copycat/trading_calendar.py`:`TradingCalendar`(frozen dataclass:holidays / extra_trading_days / years_loaded;
  `is_trading_day(d)`、`last_trading_day(d)`(往回走,含 d)、`has_year(y)`)、`WEEKEND_ONLY` 常數實例、
  `load_trading_calendar(path=DEFAULT_PATH) -> TradingCalendar`(檔缺 WARNING → WEEKEND_ONLY;壞檔 raise
  ValueError)、`warn_if_year_missing(cal, today)`(模組層 `_warned_years` 每年一次節流,`_reset_year_warnings()`
  供測試;`[amendment R2-2/R2-4]`)、`resolve_trade_date(today, cal) -> date`(先 warn 再 last_trading_day;
  **app 層與 breadth today_fn 唯一入口**)。零 IO 除 load。**Pkg1 已落地(983b058 / a2937dd)。**
- `configs/trading_holidays.json`:2026 平日休市 18 天(TWSE 官方 JSON 2026-08-16 抓取):01-01, 02-12, 02-13,
  02-16~02-20, 02-27, 04-03, 04-06, 05-01, 06-19, 09-25, 09-28, 10-09, 10-26, 12-25。
- `tests/test_trading_calendar.py`。
- `GET /api/calendar`(app.py)+ `tests/server/test_calendar_wiring.py`。
- 前端 `src/lib/trading-calendar.ts` + `src/hooks/useTradingCalendar.ts` + 測試;App.tsx 掛 hook。

### 🔴 行為改動(既有測試該紅 → 改實作綠)
- `copycat/server/app.py` `[amendment R2/R6/R7/R9]`:`create_app(trading_calendar: TradingCalendar | None = None)`;
  模組層 `_today() -> date`(牆鐘;測試 monkeypatch 點)+ create_app 內閉包 `_resolve_trade_date() -> str`
  (Q9 定義);hub fallback `_wall_clock_trade_date` 改為該閉包(每次求值、env 優先);`_make_stock` /
  `_make_index` trade_date = `_resolve_trade_date()`,傳 `is_trading_day=cal.is_trading_day if cal else None`;
  `_make_breadth` 傳 `today_fn` / `is_trading_day`(cal None 時不傳,保留預設);`_start_index` wrapper 加
  雙向 DK 交叉檢查(自吞例外);`/api/stock/overlay/{code}` 與 `/api/index/overlay` 的 `build_overlay` today
  與 `OverlayCache` 鍵改 `_resolve_trade_date()`(bars 抓取仍 `_today()`);新 `GET /api/calendar`(SC-6 payload)。
- `copycat/server/stock_engine.py`:`__init__(..., is_trading_day: Callable[[date], bool] | None = None,
  now_fn: Callable[[], datetime] | None = None)`;`_checkpoint_loop` 用注入。預設值 = 現行。
- `copycat/server/index_engine.py`:`__init__(..., is_trading_day=None)`;`_rollover_loop` 非交易日 continue。
- `copycat/server/breadth_engine.py`:`__init__(..., is_trading_day: Callable[[date], bool] | None = None)`;
  `_in_window` 加判定(**兩個呼叫端都吃**,R4);`rows_state` docstring 假日開站段改寫(R5)。
- `copycat/server/__main__.py`:prod 傳 `trading_calendar=load_trading_calendar()`。
- 前端 `src/lib/trading-hours.ts` 三支改用 `isTradingDay`(R1:AllDay 00:00–05:05 分支用 `now − 1 天`);
  `LimitListSection.tsx` 日期膠囊 + 空態文案(R3/R12)。
- 既有測試處置:
  - **該紅**:`tests/server/test_main_wiring.py::test_main_passes_explicit_default_sources`(kwargs dict 多一鍵);
    `frontend/src/components/index/LimitListSection.test.tsx:234`(fixture trade_date 固定 2026-08-06 ≠ 本機今日;
    修法 = `mkState` trade_date 改動態今日,斷言文字不改)。
  - **不該紅**:test_stock_engine / test_index_engine / test_breadth_engine / test_signal_routes / test_index_routes /
    test_breadth_routes / test_market_routes 全部(預設值保留);前端 trading-hours.test / useStockBars.test。
- 新測試:見 §1 各 SC。

### 🔵 純文案 / 文件
- CLAUDE.md §1 表格一列;`docs/next-time.md`。

## 6. Known Risks
- KR-1 日曆錯標真交易日 → index 當日不換日(WARNING 由 DK 交叉檢查在 boot 提示;盤中修 config 重啟即復原)。
  **影響面(review S5 補寫)**:不只 index 一項 ——(a) breadth 那天 `_in_window` 恆 False → **全天不取數**,
  且 `_stale` 共用同一把尺 → stale 被壓成 False(家數帶凍在首圈那一則,誠實旗標不亮);(b) 前端三支時段
  函式 `isTradingDay(今天)` 全 false → 5 個 `refetchInterval` 一起回 false = **全站輪詢停擺**(畫面看起來
  正常,只是不動);(c) 唯一的提示是 SC-7 的 boot WARNING —— 沒重啟就完全沒有訊號。可見訊號的補強
  (前端拿 `/api/calendar.holidays` 命中今天 → 標頭膠囊)列入 next-time。
- KR-2 2027 官方尚未公布 → 2027-01-01 起只擋週末,WARNING(每年一次節流)提醒更新 config;
  `/api/calendar.years_loaded` 可監看。
- KR-3 `[amendment R9 / R2-3]` 臨時休市(颱風假)靜態 config 無法預知 → 當天 trade_date 落在無資料日、畫面退回
  改動前症狀;boot 交叉檢查(SC-7)**只有 14:00 之後重啟**才 WARNING 提示改設 `TXO_BACKFILL_DATE`(上午重啟
  expected = 前一交易日,兩方向都不觸發;長跑不重啟亦無提示)→ 上午只能靠畫面空圖 + 手動 env。
- KR-4 `[amendment R8]` 交易日盤前冷啟動仍空圖到 09:00(需 env);見 Out of scope。
- KR-5 `[amendment R2-1]` env 模式(`TXO_BACKFILL_DATE`)下 stock / index / hub 用 env 日,breadth 用日曆最近交易日,
  畫面日別不一致 —— breadth 現行本就不讀 env,env 是 TXO 回補用的 ops 通道,不擴張其語意。
