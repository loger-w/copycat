# current-state — mod/trading-calendar(2026-08-16,週日)

Baseline:`pytest -q` 2563 passed(146s)。branch `mod/trading-calendar`。

## 1. 根因:全庫沒有交易日曆

日期來源全是「`TXO_BACKFILL_DATE` or 牆鐘 today」,非交易日冷啟動 → 各引擎抓「今天」的空窗。

| 讀取點 | 現行 | 非交易日冷啟動症狀 |
|---|---|---|
| `app.py:289` `_default_source` | `backfill_date=env` → TC4QuoteSource(TXO)| TXO 面(**本輪不動**,見 out of scope) |
| `app.py:336` `_wall_clock_trade_date` | `env or today`(hub 無 engine 時的 fallback)| jsonl 檔名 / today_signals 用假日日期 |
| `app.py:381` `session_rollover=env is None` | TXO runtime | 不動 |
| `app.py:455-460` `_make_stock` | `StockEngine(trade_date=env or today, checkpoint=env is None)` | source 日窗 = 假日 → 主圖 / 群組回補全空 |
| `app.py:589-596` `_make_index` | `IndexEngine(trade_date=env or today, rollover=env is None)` | IX0001 1K 回補空 → 加權分時空圖 |
| `app.py:736-748` `_make_breadth` | `BreadthEngine(...)`(today_fn 預設 `date.today`)| counts 對(FinMind 回上一交易日快照)但 `_restore` 讀 `breadth-<今天>.json` 不存在、`_append` 要 `trade_date == today` → 分鐘序列空 |
| `stock_engine.py:838-851` `_checkpoint_loop` | `datetime.now()` 直讀;`weekday()<5 and hour>=8 and today != trade_date` → `rollover_stage1(today)` | 國定假日(平日)08:00 仍 stage1 → source 日窗切到假日,stage2 永不來(狀態不清,但之後換主圖回補走假日窗 → 空)|
| `index_engine.py:431-462` `_rollover_loop` | 每 60s:`new_date > trade_date and now >= 08:30` → set pending + `set_trade_date` + resubscribe + `fetch_day_minutes` | 週末 / 假日整天每 60s 打 TC4 1K(恆空、不 swap = 凍在上一交易日,副作用非設計)|
| `breadth_engine.py:583-585` `_in_window` | 純時間窗(09:00–13:40 config)| 假日窗內每 10s 打 FinMind(配額浪費) |
| `breadth_engine.py:552` `_append` | `trade_date != today_fn()` → 不 append | 見上 |
| `breadth_engine.py:934-940` `_restore` | 讀 `breadth-<today_fn()>.json` | 假日檔不存在 → 空序列 |
| `breadth_engine.py:602-632/678-810` streak | `today_fn()` 為基準往回掃,空回應跳假日 | 已自帶假日跳過(白名單:不動) |
| `app.py:1016/1032` overlay / bars | 牆鐘 today | K 線不受影響(**白名單:不動**) |
| `live/tc4.py:404-410` `fetch_backfill` | env 有值 → 固定日盤窗 | TXO,不動 |
| `frontend/src/lib/trading-hours.ts:14-47` 三支 | 只擋週末(:12/:24/:39 註解已預留日曆)| 國定假日每 60s 空打 bars endpoint(next-time:537) |
| `LimitListSection.tsx:343` | `pool === 0` → 「今日尚無漲跌停」 | 假日看的是上一交易日 rows,文案說「今日」 |

**已存在的自癒**:stock_engine `:961-969` 快路徑(現貨 tick `trade_date > _trade_date` → stage1),日曆錯標「假日」時真交易日仍會被 tick 拉回;index 無同款。

## 2. Caller map(引擎建構 / 注入點)

- `StockEngine(...)`:app.py `_make_stock`;tests/server/test_stock_engine.py 多處(皆 `checkpoint=False`,不跑 checkpoint loop);tests/helpers/fake_sources.py 提供 source。
- `IndexEngine(...)`:app.py `_make_index`;tests/server/test_index_engine.py `make_engine`(`today_fn` 注入,日期 2026-07-28/29 皆平日;`test_rollover_two_phase` / `test_rollover_gate_opens_at_0830` / `test_rollover_disabled_does_nothing` 直接測 rollover loop)。
- `BreadthEngine(...)`:app.py `_make_breadth`;tests/server/test_breadth_engine.py(`today_fn` / `now_fn` 注入 `_Clock`);tests/server/test_breadth_routes.py(`_TODAY = date.today()`)。
- `create_app(...)`:39 處(15 個測試檔)+ `__main__.py` prod / verify 兩路;`tests/server/test_main_wiring.py::test_main_passes_explicit_default_sources` **斷言 prod kwargs 的完整 dict**(新增 kwarg = 該紅)。
- `_wall_clock_trade_date`:test_signal_routes.py:712-810(牆鐘 fallback + env 優先;測試以 `date.today()` 對照)。
- 前端 `inTradingHours`:useBreadthRows/useGroupSnapshots/useStockBars/useMarketBars;`inFuturesTradingHours`:useMarketBars;`inFuturesAllDayHours`:useFuturesBars。測試 useStockBars.test.tsx:36-50、trading-hours.test.ts。
- 牆鐘 today 的測試依賴(**若 create_app 預設載入真日曆,週末跑會全紅**):test_index_routes:114、test_signal_routes:723/749/781/810、test_market_routes:22、test_breadth_routes:36、fake_sources:112/172、test_verify:154-222。→ 設計上 create_app 的日曆必須是**可選注入、預設 None = 牆鐘不變**(對齊 DEFAULT_STOCK / DEFAULT_BREADTH 的「prod 顯式傳、測試預設關」慣例)。

## 3. 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 交易日判定 | 無;stock 只 `weekday<5`,index 純日曆日 | `copycat/trading_calendar.py` 純模組 + `configs/trading_holidays.json`(TWSE 官方 JSON 2026 已抓齊;2027 官方尚未公布 → 缺年只擋週末 + WARNING 一次)|
| 引擎 trade_date 初始化 | `env or today` | `env or calendar.last_trading_day(today)`(env 仍最高優先)|
| stock checkpoint / index rollover 新日判定 | weekday / 日曆日 | `is_trading_day(today)` 注入(預設值保留現行語意)|
| breadth today_fn / `_in_window` | 牆鐘 / 純時間 | today_fn = 最近交易日;`_in_window` 加 `is_trading_day`;首圈仍無條件跑 |
| 對外 | 無 | 新 `GET /api/calendar`(trade_date / holidays / years_loaded);health 不動(docstring 契約「只含建置身分」)|
| 前端 | 週末 | 三支接 `/api/calendar` 假日集合;LimitList 文案帶日期 |
| TXO_BACKFILL_DATE | 唯一手段 | 手動覆寫通道保留(TXO 面仍需要,見 out of scope)|

## 4. Backward compat / migration

- 無資料格式變更、無 migration。`create_app` 新 kwarg 預設 None(39 個測試呼叫點零改動)。engine 新 kwarg 預設 None → 現行語意逐字不變。
- 對外 API 只新增 `/api/calendar`;既有端點 payload 不變。`/api/stock/signals/today` 在非交易日 hub 的 trade_date 隨 engine 變為最近交易日(= 顯示最近交易日訊號,與圖表一致 —— 這是目標行為,不是回歸)。
