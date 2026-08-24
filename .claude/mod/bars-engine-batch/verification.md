# R7 bars/引擎後端批 — verification

分支 `mod/bars-engine-batch`(自 master `979cb511` 切)。本 session **零 TC4 / 零 ZMQ**
(ops-discipline 盤中驗證通道節):沒有起過任何連 TC4 的程序,測試一律 fake source。

---

## §1 commits

| commit | 類 | 內容 |
|---|---|---|
| `6992358e` | chore | change-spec §0–§3(白名單 / caller map / 逐條處置 / 事前標「該變」清單) |
| `fadaa1c2` | 🟢 | 後端紅先行(23 條紅) |
| `495ab456` | 🟢 | 前端紅先行(FuturesChart 4 案 + CalendarHolidayBadge 新檔 9 案) |
| `635a8c2e` | 🔴 | 後端十一條實作 |
| `fc48e60e` | 🔵 | `_quote_payload` docstring(N101,零行為) |
| `9ec08a4b` | 🔴 | 前端四條實作(N104 / N016 / N090 / N091) |
| `500a503d` | chore | CLAUDE.md §4 登錄 `meta.status` 契約 |

## §2 紅態證據

### 後端(`.venv\Scripts\python -m pytest -q`,commit `fadaa1c2` 當下)
`23 failed, 2949 passed in 169.75s`。逐條:

```
tests/live/test_river_state.py::TestCloseClampPush::test_smaller_rank_wins_over_a_farther_stale_sample
tests/live/test_river_state.py::TestApplyBackfill::test_backfill_overwrites_a_clamp_approximation_in_the_end_slot
tests/live/test_river_state.py::TestApplyBackfill::test_backfill_overwrites_the_end_slot_only_once
tests/live/test_stock_source.py::TestFetchDailyBars::test_dk_ready_but_empty_plus_1k_timeout_raises
tests/live/test_stock_source.py::TestFetchDailyBars::test_window_shrinks_with_small_n_but_is_verbatim_at_25
tests/server/test_calendar_wiring.py::TestCalendarRoute::test_payload_with_calendar_on_saturday
tests/server/test_calendar_wiring.py::TestCalendarRoute::test_extra_trading_days_are_exposed
tests/server/test_engine.py::test_handover_buffer_vanished_still_reports_phase_degraded
tests/server/test_futures_engine.py::TestBarsRangeProxy::test_source_absent_returns_empty_with_fixed_log
tests/server/test_futures_engine.py::TestBarsRangeProxy::test_history_timeout_degrades_here_with_its_own_log
tests/server/test_futures_engine.py::TestBarsRangeProxy::test_connection_error_returns_empty_with_fixed_log
tests/server/test_futures_engine.py::TestBarsRangeProxy::test_healthy_path_reports_ok
tests/server/test_index_engine.py::test_heal_runs_after_hours_on_a_trading_day
tests/server/test_index_engine.py::test_heal_never_runs_on_a_non_trading_day
tests/server/test_index_engine.py::test_pending_retry_keeps_new_day_minutes_out_of_state
tests/server/test_market_routes.py::TestMinutePath::test_futures_minute_timeout_reaches_meta_status
tests/server/test_market_routes.py::TestMinutePath::test_futures_minute_disconnected_reaches_meta_status
tests/server/test_market_routes.py::TestMinutePath::test_healthy_futures_minute_is_ok
tests/server/test_market_routes.py::TestMarketPayloadUnaffectedByBarsStatus::test_status_lives_in_meta_only_and_never_at_top_level
tests/server/test_signal_hub.py::TestNoDailyBarsSource::test_request_basis_is_a_noop_without_source
tests/test_corr_config.py::TestDefaultConfig::test_has_seven_legs_matching_the_repo_config
tests/test_corr_config.py::TestDefaultConfig::test_non_base_legs_are_tc4_subscriptions
tests/test_corr_config.py::TestRepoConfigFile::test_repo_config_matches_default_leg_for_leg
```

代表性紅訊息:

- N024 `assert ['2026071600','2026071600'] == ['2026080500','2026080500']`(n=5 仍用 40 日窗)
- N020 `AssertionError: assert 'backfilling' == 'degraded'`
- N104 engine `AttributeError: 'list' object has no attribute 'status'`
- N104 route `KeyError` / `assert 'ok' == 'timeout'`
- N110 `TypeError: 'NoneType' object is not callable` ×3(逐檔走完例外 → 重試 → 那正是條文
  說的「50 檔 50 行」的形狀)
- N107 `assert {'0901': 9, '0902': 99} == {'0901': 1}`(新日 1K merge 進舊日 dict)
- N058 `assert 40700000 == 40646000`(真收盤補不進 end 格)
- N090 `KeyError: 'extra_trading_days'`

### 前端(`npx vitest run`,commit `495ab456` 當下)
- `FuturesChart.test.tsx`:`2 failed | 2 passed`(timeout / disconnected 兩句話不存在;
  `ok` 與「gate 5 並存」兩案在紅態即綠 —— 它們鎖的是**不得回歸**的既有行為)。
- `CalendarHolidayBadge.test.tsx`:整檔 import 失敗(`CalendarBadges` 尚未存在)。

### 紅態不足的兩處(誠實標註)
- `tests/server/test_main_wiring.py::TestHealGateAcrossMidnight::test_cross_midnight_table`
  (N015 跨午夜表四格)**一開始就綠** —— 條文要的是「補表」= 補覆蓋,不是修 bug。
  teeth 已用推理釘住並寫進 docstring:現存三格全落在 `hour == 1`,把 `hour < 6` 改成
  `hour < 24` 三格照樣全綠,而新加的「週一 08:50」會退成週日 → 該救不救。
- `TestNoDailyBarsSource::test_ticks_still_flow_without_a_daily_bars_source` 亦一開始就綠
  (鎖 XR-3 的既有語意不得回退)。

### 前端 mutation 實測(negative case 有沒有牙齒)
`CalendarHolidayBadge.tsx` 同時注入兩個 mutant(拿掉 `!years_loaded.includes(year)`、
週末守門改 `return true`)→ `4 failed | 5 passed`;還原後 `9 passed`。
即「健康態零 DOM」「years_loaded 含今年不亮」「普通週末靜音」「舊 payload 退回靜音」
四條都真的擋得住。

## §3 完成前 gate(全綠)

| gate | 指令 | 結果 |
|---|---|---|
| 後端測試 | `.venv\Scripts\python -m pytest -q` | **2972 passed**(master 2951;+21 淨新增)`171.23s` |
| Lint | `.venv\Scripts\python -m ruff check copycat tests` | `All checks passed!` |
| 型別 | `.venv\Scripts\python -m pyright` | `0 errors, 0 warnings, 0 informations` |
| golden | `.venv\Scripts\python -m copycat validate` | **42/42 PASS** |
| 前端型別 | `frontend/ npx tsc -b` | 無輸出(通過) |
| 前端測試 | `frontend/ npx vitest run` | **145 files / 2758 tests passed**(master 144 / 2745) |
| 前端 lint | `frontend/ npx eslint src` | 無輸出(通過) |
| react-doctor | `frontend/ npx react-doctor@latest --scope changed --no-telemetry` | `Scanned 7 files` → **No issues found**(零新增 finding) |

## §4 白名單逐條核對(對 diff)

| # | 白名單條目 | 核對 |
|---|---|---|
| 1 | `bars.py` 三層 cache 全數不動 | `git diff master..HEAD -- copycat/server/bars.py` **空**(零 diff) |
| 2 | `fetch_bars_range_tagged` 逐字不動 | diff 只動 `fetch_daily_bars` 與新增 `_daily_window_days`;90 日 fallback 窗與 `dk_timed_out or fb_timed_out` 未被觸及 |
| 3 | `fetch_daily_bars` 在 n=25 時窗逐字 40 日 | `_daily_window_days(25) = min(40, max(20, 40)) = 40`;測試 `test_window_shrinks_with_small_n_but_is_verbatim_at_25` 對 `n=25` 斷言 `today-40` 兩段同窗 |
| 4 | `futures_source.fetch_bars_range` raise 語意不動 | `git diff -- copycat/live/futures_source.py` **空** |
| 5 | index watchdog 窗 09:00–13:25 不動 | diff 只改 heal 那個 `if`;watchdog 的 `self._in_watch_window()` 分支與 `_WATCH_START/_WATCH_END` 值未動 |
| 6 | `_swap_day` 覆寫順序不動 | `_swap_day` 零 diff;N107 的新分支刻意用同方向 `{**minutes, **self._pending_minutes}` |
| 7 | RiverState 換場清空 / 同分鐘 last-write-wins / 非 end 格「只補空缺」 | 換場清空多清一個名次帳(同語意);`test_non_clamp_minutes_keep_last_write_wins` / `test_fills_only_missing_offsets` / 新增 `test_backfill_does_not_overwrite_a_plain_live_minute` 全綠 |
| 8 | SignalHub 既有重試 / `_stale` 尺 / cache 收斂點不變 | diff 只加 `request_basis` 早退 + 一個 assert;`_resolve_basis` / `_basis_failed` / `_schedule_basis_retry` 本體零改 |
| 9 | market route 值域檢查 / OTC / 分派 / cache 後綴 | diff 只重排兩個閉包的定義位置 + 接第二元素;`MARKET_KEYS` / `BAD_*` / OTC 分支 / `IX0001\|M`·`\|L` 未動 |
| 10 | `/api/calendar` 既有欄位語意不變 | 新增一鍵;既有六鍵的斷言(`trade_date` vs `calendar_trade_date` 分帳、18 個 holidays)全部原封通過 |
| 11 | `CalendarHolidayBadge` 三道既有否決不變 | `shouldShowHoliday` 前三行逐字沿用;`App.test.tsx` 既有六案零改動且全綠 |

**另一組零 diff 核對**(本輪沒碰、review 可直接跳過):`copycat/server/bars.py`、
`copycat/live/futures_source.py`、`copycat/server/overlay.py`、`copycat/trading_calendar.py`、
`copycat/live/river_models.py`。

## §5 未做 / 判定型決定

| 條 | 判定 | 理由 |
|---|---|---|
| **N024 的 `n=25` 那半** | **不縮窗** | 不是「沒量所以不動」,是**可證不安全**:`build_overlay` 的 ma20 要 20 根已完成日 bar,40 日曆日 ≈ 25–28 個交易日、遇春節連假只剩 ~23 根,餘裕本就個位數;再縮的失效樣態是 ma20 靜默變 null。**做的那半** = 窗隨 `n` 縮(地板 20),直接砍掉 basis sweep(`n=5`)那條路一半的收割量,而 `n=25` 逐字不變 |
| **N015 封關夜近似誤差** | **不做** | 條文自己寫「獨立開條」;要做需引入「下一交易日」判定(`_session_date` 目前刻意不做,近似方向安全 = 空 churn 而非該救不救) |
| **N090 的偵測面(補班日漏設)** | **做不到** | 漏設時 payload 與普通週末**完全同形**(後端判非交易日 + 該日不在 `extra_trading_days`),前端沒有第二個獨立訊號。已做的是 additive 欄位 + 「設了卻沒生效」那條真不變式 |
| **N104 的 `tf != "1"` 與 TWSE/OTC** | **固定 `ok`** | `build_period` 回 `TaggedBars` 沒有 status 欄、`index.bars_range` 回 `(bars, tag)` —— 要一起三態化得動 `bars.py` 的 cache 型別(白名單 §0.2-1) |
| **N020 `attempts_max` write-only** | **保留欄位** | 它是 `/api/txo/state` 的診斷欄(值班用),不是 dead code;修的是「註解拿不存在的 UI 症狀當理由」+ 補上 `phase` 在迴圈盡頭的降級 |
| **N110 用 `None` 而非「hub 加模式分支」** | 改採更淺的表達 | 條文候選是加模式分支;`daily_bars=None` 表達「沒有這個能力」比一個恆回空的假 callable 淺,且順帶刪掉為它而生的 `basis_gap_secs=0` hack |

## §6 留尾(下次處理)

1. **N094 `_twse.minutes` 跨執行緒無鎖**:本輪 N107 的 pending 分流仍在 worker thread 內
   寫 dict(既有姿態未變)。正解是「worker 只回傳 dict、event loop 端合併」,要動
   `_retry_loop` / `_subscribe_and_backfill` 簽名 —— 獨立小輪(R8 已有此條)。
2. **N015 封關夜**:見 §5。
3. **N090 漏設偵測**:需要一個獨立於日曆的「今天有沒有在成交」訊號才做得到。
4. **`build_period` 三態化**:`TaggedBars` 沒有 status 欄,日 / 週 / 月 K 與加權的
   `meta.status` 恆 `ok`。要收得動 `bars.py` 的 `_hist` / `daily_tag` 型別。
5. **index 盤後 heal 的上限**:交易日晚間若 TC4 整晚拿不到當日 1K,退避封頂 900 s
   → 到隔日約 40 發 UNSUB→SUB。目前判斷可接受(換的是「線整晚空著」),若 prod log
   噪音過大,候選 = 盤後段另設更長的 base interval。

## §7 需 user 過目 / 盤中量測(本 session 做不到的部分)

**共同前提:prod 8721 尚未重啟**(後端改動需重啟才生效;前端需 `npm run build`)。

| # | 項目 | 怎麼看 |
|---|---|---|
| SC-1 | **N024 真實列數量測**(條文要求「要動之前先量一次真實列數」) | 理論上界已寫進 change-spec:個股 1K ≤275 列/交易日;40 日窗 ≤ ~7,700 列、20 日窗 ≤ ~3,850 列。盤中對一檔 **DK 不支援**的股號量實際列數:`GET /api/stock/overlay/{code}` 前後各記一次 server log 的耗時,或側車直呼 `StockQuoteSource.fetch_daily_bars(code, n=5)` 並在 `_collect_history` 加暫時計數。量到之後回填 change-spec §1 N024 |
| SC-2 | **N105 盤外啟動自癒** | 交易日 13:45 之後重啟 8721,`grep "index 分時自癒" logs/server-*.log` 應看得到晚間發出的 heal(改動前該時段零筆);休市日整天應**零筆**(交易日閘) |
| SC-3 | **N107 混日線窗口** | 換日 08:30–09:0x 之間、`_pending_date` 還沒 swap 時重整加權分時頁 → 線不得出現昨日+今日混在一起的形狀。窗極窄(≤60 s),屬機會觀察 |
| SC-4 | **N104 期貨空態三句話** | 期貨 tab 分時模式,TC4 忙 / 未連線時分別應看到「回補中…(TC4 忙,稍後自動重試)」與「暫無資料(TC4 未連線)」;有 bars 時 gate 5 的「分時資料落後 N 根(TC4 回補中)」照舊在模式列右側,兩者不得同時出現 |
| SC-5 | **三顆日曆膠囊** | 平常 nav 右側應**完全看不到**它們(健康態零 DOM)。要看樣子:暫時設 `TXO_BACKFILL_DATE=2026-08-24` 重啟 → 應亮「TXO 回補日鎖定 2026-08-24」;把 `configs/trading_holidays.json` 的 `years` 只留 2025 重啟 → 應亮「交易日曆過期」。**看完記得還原**(前者會把 TXO 面鎖住) |
| SC-6 | **N110 開機 log** | 無 stock engine 的情境(TC4 沒開就起 server)boot 後 `grep "CDP 停用" logs/…` 應**零筆**,改為一行 `CDP 基準:無日 K 來源,N 檔一律不排 job` |
| SC-7 | **N021 降級腿數** | 把 `configs/correlation.json` 改壞(例如刪掉 `legs`)重啟 → 江波圖 / 相關係數應仍是**七腿**(改動前會少一腿)。看完還原 |
