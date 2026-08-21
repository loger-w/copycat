# repro — `_collect_history` timed_out 旗標六處 caller 無視(bug/history-timeout-propagation,R8 / A2)

來源:rounds.md §R8(預核准);next-time 08-13 index-chart-empty-minutes 節(2026-08-20 caller 盤點)。

## 症狀
TC4 冷啟動忙碌窗口 `_collect_history` 等滿 deadline 首頁仍未備妥 → `HistoryResult(rows=[], timed_out=True)`;**只有** `stock_source.fetch_bars_range_tagged`(L691-709)讀旗標。
其餘五處 `.rows` 直取 → timeout 被讀成「資料面就是沒有」,無重試:
- `stock_source.backfill`(L643 → `fetch_day_minutes`):index/stock 分時回補空 → 引擎以為當日無 1K(index 側已用產出面 lag 偵測繞開)。
- `stock_source.fetch_daily_bars`(L721 DK / L724 1K fallback):overlay / SignalHub daily_bars 空 → hub 讀成「無已完成日 K,CDP 停用」**永不重試**(app.py:369-375 明寫:空清單 = 資料面沒有;拋例外 = 暫時性 → X-2b 有限重試)。
- `futures_source.fetch_bars_range`(L187 1K / L192 DK):futures K 線空 → route tag `"unavailable"`、status 恆 `"ok"`。
- `river_backfill.collect_1k_minutes`(corr_source / futures_source 腿):自有迴圈「首頁未備妥 → 回 []」;真實事故 08:23 TXF/TWN/SXF 三腿同秒 timeout 回空無重試;
  且 `minute_end_from_1k` 只讀 Time 不讀 Date(凍結 stub 列會變今日分鐘)。

## 最小重現(loop,紅測試)
Fake source 注入 `_collect_history` 回 `HistoryResult([], timed_out=True)`:
1. `backfill` / `fetch_day_minutes` → 現況回 `{}`(紅:應拋 `HistoryTimeoutError`)。
2. `fetch_daily_bars` DK timed_out → 現況走 1K fallback 再空 → `[]`(紅:應拋);DK 首頁備妥但 0 rows → 1K fallback(不變)。
3. futures `fetch_bars_range` timed_out → 現況 `[]`(紅:應拋)。
4. `collect_1k_minutes` 首頁逾時 → 現況 `[]`(紅:應拋 `HistoryTimeoutError`);首頁備妥 0 rows → `[]` 不拋(契約:「首頁備妥但 0 rows」仍是空)。
5. 引擎層:`stock_engine.daily_bars` 遇 `HistoryTimeoutError` **不得吞成 []**(現況 `except ConnectionError → []`,紅);`corr_engine._fetch_leg_minutes` 遇 timeout → 該腿排重試(現況回 [] 無重試,紅);
   futures route `tagged_source` 遇 timeout → `BarsResult([], "timeout")`(現況 "ok",紅)。

## Root cause
`HistoryResult.timed_out` 在 08-05 只為 stock bars 三態加入,其餘 caller 仍沿用旗標前的 `.rows` 語意;river 另長一套迴圈。timeout 與「真空」在 TC4 協定上只有 `timed_out` 一個正面訊號,丟掉它就無從重試。

## 修法(逐 caller 語意,`[auto-default]`)
- 新 `class HistoryTimeoutError(ConnectionError)`(`copycat/live/tc4.py`):**子類 ConnectionError** → 既有 `except ConnectionError` 重試網(stock_engine backfill 重排 / index_engine `_schedule_retry` / futures_engine / corr 訂閱重試)自動接手;需要區分的地方 `except HistoryTimeoutError` 先於 `except ConnectionError`。
  `[auto-default: 例外而非三態回傳 | reason: 五處 caller 的上游都已有 ConnectionError 重試路徑;三態要改五個簽名 + 所有 fake]`
- `stock_source.backfill` / `fetch_day_minutes`:`timed_out` → raise。上游 `stock_engine` 回補 worker 與 `index_engine` rollover / heal 既有 `except ConnectionError` → 重排(驗證:測試注入 timeout 一次後成功 → 第二次取到資料)。
- `stock_source.fetch_daily_bars`:DK `timed_out` → raise(不走 1K fallback:fallback 是給「DK 不支援」的,timeout 時 1K 多半也忙);DK 備妥 0 rows → 1K fallback;1K `timed_out` → raise。
  `stock_engine.daily_bars`:`except HistoryTimeoutError: raise`(hub X-2b 有限重試)、其餘 ConnectionError 照舊 `[]`。app.py `/api/stock/overlay` 既有 `OVERLAY_FETCH_TIMEOUT_S` 路徑對 `HistoryTimeoutError` 降級全 null(與 asyncio timeout 同語意)。
- `futures_source.fetch_bars_range`:`timed_out` → raise;`futures_engine.bars_range` `except HistoryTimeoutError: raise`(其餘 ConnectionError 照舊 []);app.py `tagged_source` `except HistoryTimeoutError → ` 狀態 `"timeout"`(沿 `BarsResult` 三態;`plain_with_status` 改帶真 status)。
- `river_backfill.collect_1k_minutes`:首頁逾時 → raise `HistoryTimeoutError`(首頁備妥 0 rows → `[]`);`minute_end_from_1k` 加 `Date` 判定:row `Date` 存在且 ≠ 窗口日(UTC→台北換算沿 `all_day_utc_window` 口徑)→ 丟棄(凍結 stub)。
  `corr_engine._fetch_leg_minutes`:`except HistoryTimeoutError` → 該腿記入 `_backfill_retry`(腿 → 次數),`_backfill_river` 結束後若有待重試腿 → 排 `asyncio` 延遲重跑(30s 退避、上限 3 次、single-flight 沿用),只重補那些腿;其餘 ConnectionError 照舊降級。
- **不動** `TC4QuoteSource._collect_history` 本體(blast radius:`grep -rn _collect_history copycat` 六處皆本輪 caller)。

## Blast radius
`HistoryTimeoutError` 是 ConnectionError 子類 → 所有 `except ConnectionError` 行為不變(變的只是原本回空的路徑改為走該分支)。受影響功能:個股/指數分時回補、overlay CDP/MA、SignalHub 日 K、期貨 K 線、江波圖六腿回補。各跑 sanity:tests/server/test_stock_engine / test_index_engine / test_overlay / test_signal_hub / test_futures_engine / test_corr_engine / test_bars*。

## 反向驗證
修復 commit `git revert --no-commit` → 紅測試該紅回來 → 還原 → 綠。

## Plan review(`plan-review-round-1.json`,13 條全 accepted)→ 修法收窄(以本節為準)
- 事實更正(P1-5):`stock_source.backfill`(L587-613)自有迴圈不經 `_collect_history`;`_collect_history` 呼叫點 = futures 187/192、stock 643/691/694/704/721/724(8 點 4 函式)。
- **index `fetch_day_minutes`(L643)不改語意**(P0-3):raise 會把 `_retry_loop` 釘成無限退避、`_heal_variant` 永不遞增,比回空更糟;既有 window-variant 逃逸 + 產出面 lag 偵測已覆蓋。只改 tc4.py:715 log 文案「…回空(timeout,非無資料)」。
- **`fetch_daily_bars`**(P0-1 / P2-13):DK timed_out **仍走 1K fallback**;兩段都 timed_out 才 raise `HistoryTimeoutError(ConnectionError)`;兩段顯式傳 `BARS_POLL_DEADLINE`(10s,原預設 ≈30s×2 → 最壞 20s,避免 hub 重試佔滿 executor)。
  `stock_engine.daily_bars`:`except HistoryTimeoutError: raise`(hub X-2b:`except Exception` → 2 次 × 30s);其餘 ConnectionError 照舊 `[]`。
  **app.py overlay route**(P0-2):`except (TimeoutError, HistoryTimeoutError)` 同分支降級全 null、不寫 cache。
- **stock `backfill`**(P1-4):自有迴圈逾時 → raise `HistoryTimeoutError`;`_backfill_worker` 加 `except HistoryTimeoutError`(**先於** ConnectionError):不動 `tc4_status`、不計 `_backfill_failed`,
  per-code 重試計數 ≤ 2,`loop.call_later(15s, 再入列)`;超限 → warning 放棄(與今日相同)。
- **futures `fetch_bars_range`**(P1-6 / P1-7 / P2-10):timed_out → raise `HistoryTimeoutError`;`futures_engine.bars_range` **在 engine 內**吃掉:`except HistoryTimeoutError` → warning「期貨 K 線 timeout(非 TC4 down)」→ `[]`(payload / 前端零變;例外不得進 build_*)。
  期貨三態 status 通道(payload + 前端)記 next-time。
- **river**(P1-8 / P2-9):`collect_1k_minutes` 首頁逾時 → raise `HistoryTimeoutError`(首頁備妥 0 rows → `[]`);Date 判定**用 UTC 比對** `row["Date"] != window_start[:8] → 丟棄`(docstring 釘死不做台北換算);
  另加 stub 簽名 warning「rows 非空但 minutes 全空(疑似凍結 stub)」(沿 stock_source:658)。
  `corr_engine`:`_fetch_leg_minutes` `except HistoryTimeoutError` → 記入 `self._backfill_pending_legs`;`_backfill_river(legs: set[str] | None = None)` 子集參數;迴圈後若有 pending 且 `_backfill_retry_round < 3` →
  沿 `_schedule_backfill` 語意排 30s 延遲 task(存 `self._backfill_retry_tasks` 集合,`close()` 一併 cancel),只補 pending 腿;其餘 ConnectionError 照舊降級。
- log 文案三處(P2-11):tc4.py:715、river_backfill.py:57、index_engine.py:510 註解改寫。
- **該紅(預告)**:`tests/live/test_river_backfill.py::test_empty_first_page_returns_empty_without_blocking`(首頁逾時 → 改斷言 raises);**不該紅**:`test_dk_empty_falls_back_to_1k_aggregation`(fallback 保留)、`TestFetchDayMinutes*`(index 不改)、`test_stock_bars` 三態、`test_index_engine` heal 系列。

## 反向驗證結果

`git revert --no-commit d73477ba`(修復 commit)→ 跑七個受影響測試檔:

```
20 failed, 347 passed, 1 warning in 89.04s
FAILED tests/live/test_stock_source.py::TestBackfill::test_first_page_timeout_raises_history_timeout
FAILED tests/live/test_stock_source.py::TestFetchDailyBars::test_both_segments_timeout_raises_history_timeout
FAILED tests/live/test_stock_source.py::TestFetchDailyBars::test_both_segments_get_the_short_bars_deadline
FAILED tests/live/test_futures_bars.py::TestFetchBarsRange::test_product_routing
FAILED tests/live/test_futures_bars.py::TestFetchBarsRange::test_first_page_timeout_raises_history_timeout
FAILED tests/live/test_futures_bars.py::TestAlldaySession::test_window_start_shifts_back_one_day
FAILED tests/live/test_futures_bars.py::TestAlldaySession::test_window_shift_crosses_month
FAILED tests/live/test_futures_bars.py::TestAlldaySession::test_window_shift_crosses_year
FAILED tests/live/test_futures_bars.py::TestAlldaySession::test_day_session_window_unchanged
FAILED tests/live/test_futures_bars.py::TestAlldaySession::test_daily_ignores_session
FAILED tests/live/test_river_backfill.py::TestCorrSourceFetchDay1k::test_empty_first_page_raises_without_blocking
FAILED tests/live/test_river_backfill.py::TestCorrSourceFetchDay1k::test_rows_from_another_utc_day_are_dropped
FAILED tests/live/test_river_backfill.py::TestCorrSourceFetchDay1k::test_all_rows_dropped_warns_frozen_stub
FAILED tests/server/test_stock_engine.py::TestDailyBarsTimeout::test_history_timeout_propagates
FAILED tests/server/test_stock_engine.py::TestBackfillTimeoutRetry::test_timeout_reenqueues_without_touching_tc4_status
FAILED tests/server/test_stock_engine.py::TestBackfillTimeoutRetry::test_retry_is_bounded_then_gives_up
FAILED tests/server/test_futures_engine.py::TestBarsRangeProxy::test_history_timeout_degrades_here_with_its_own_log
FAILED tests/server/test_corr_engine_river.py::TestBackfillTimeoutRetry::test_timed_out_leg_is_retried_and_only_that_leg
FAILED tests/server/test_corr_engine_river.py::TestBackfillTimeoutRetry::test_retry_rounds_are_capped
FAILED tests/server/test_corr_engine_river.py::TestBackfillTimeoutRetry::test_close_cancels_pending_retry_task
```

紅回來的 20 條 = 紅測試 commit(`dde98f95`)當初的同一組 20 條,逐條同名。
還原(`git revert --quit` + `git checkout HEAD -- <11 檔>`)後 `tests/live tests/server`
**1724 passed**。

### Gate(修復後,repo root)
- `pytest -q` → **2870 passed, 1 warning in 183.75s**
- `ruff check copycat tests` → **All checks passed!**
- `pyright` → **0 errors, 0 warnings, 0 informations**
- `copycat validate` 未跑:engine / replay 未被本輪碰到。

### 與 plan 的偏差(逐條)
1. **預告外的該紅**:`tests/live/test_futures_bars.py` 另有 5 條空頁治具測試
   (`test_product_routing` / allday 四條窗)一起變紅 —— `_source([])` 在 `poll_wait=0`
   下本來就是「首頁未備妥」,所以任何「timed_out → raise」都會打到它們。改成
   `pytest.raises` 包住取數,**窗與 routing 的斷言本身一字未改**。
2. **治具更正**:`tests/live/test_river_backfill.py::_row` 的 `Date` 由寫死的
   `"20260730"` 改成窗口 UTC 日 —— 新增的 Date 閘會把寫死舊日期的列整批丟掉,
   不改的話鎖「分頁收割 / 解析」的那兩條會變成假紅。
3. **紅 commit 含型別宣告**:`HistoryTimeoutError` 的**類別定義**放在紅 commit
   (無人 raise)。不放的話七個測試檔全停在 collection ImportError,紅的內容只剩
   「型別不存在」,看不出行為契約有沒有被違反。
4. **一條中途斷言在綠 commit 被移除**:
   `test_timed_out_leg_is_retried_and_only_that_leg` 原本先斷言「首輪後 SXF minutes
   為空」,但退避被 monkeypatch 成 0.01s 後,重試在 `_drain()`(30×1ms)期間就跑完了
   —— 那是**時序相依**的斷言,不是行為斷言。改以 fetch 次數(SXF 2 次 / NQ 1 次)
   + 終態鎖同一件事,證據更強而非更弱。
5. **`_backfill_timeouts` 為新增記帳**:與 `_backfill_failed` 分帳(逾時不該吃掉
   「三次就冷卻」給真失敗用的額度),日別語意,在 rollover stage2 一併清空。
