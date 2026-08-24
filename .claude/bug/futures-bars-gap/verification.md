# 驗證證據 — 期貨 K 線非交易日歷史段永久重探測(2026-08-24)

分支 `fix/futures-bars-gap`。root cause 與蒐證見 `repro.md`。

## 1. 紅測試先行

新檔 `tests/server/test_bars_gap.py`(5 條),先跑、後修:

```
$ .venv/Scripts/python -m pytest tests/server/test_bars_gap.py -q
4 failed, 1 passed in 0.84s
FAILED tests/server/test_bars_gap.py::TestNonTradingDayNotRefetched::test_pure_non_trading_gap_sends_no_history_fetch
FAILED tests/server/test_bars_gap.py::TestNonTradingDayNotRefetched::test_status_not_polluted_by_impossible_day
FAILED tests/server/test_bars_gap.py::TestNonTradingDayNotRefetched::test_real_trading_day_gap_still_fetched_with_filtered_endpoints
FAILED tests/server/test_bars_gap.py::TestNonTradingDayNotRefetched::test_day_session_filters_saturday_too
```

唯一綠的第 5 條 `test_no_calendar_keeps_old_behavior` = **現行行為的合約**:
today=2026-08-24(一)、days=5、session=allday、memo 已有 08-20..08-22 時,
現行 code 對 `2026-08-23..2026-08-23`(週日)發一次歷史 fetch,整體 status
被汙染成 `timeout` —— 與全日 log 的 28/28/28 樣態逐字相同。

## 2. 修後綠

```
$ .venv/Scripts/python -m pytest tests/server/test_bars_gap.py -q
5 passed in 0.05s
```

## 3. Blast radius(全套)

`build_minute` 的 caller:`copycat/server/app.py:1314`(stock)/ `:1624`(market),
以及 `tests/server/test_bars.py` 內 30+ 處(全部不傳 `calendar` → `None` → 舊行為)。

```
$ .venv/Scripts/python -m pytest tests/server -q -p no:randomly
1211 passed, 1 warning in 145.40s

$ .venv/Scripts/python -m pytest -q
2909 passed, 1 warning in 166.50s

$ .venv/Scripts/python -m ruff check copycat tests
All checks passed!

$ .venv/Scripts/python -m pyright
0 errors, 0 warnings, 0 informations
```

既有測試零紅、零改動。

## 4. 反向驗證

```
$ git stash push -m revfix copycat/server/bars.py copycat/server/app.py   # 測試檔留著
$ .venv/Scripts/python -m pytest tests/server/test_bars_gap.py -q
4 failed, 1 passed in 0.32s
$ git stash pop
$ .venv/Scripts/python -m pytest tests/server/test_bars_gap.py -q
5 passed in 0.28s
```

stash 態的紅是簽名層(`TypeError: build_minute() got an unexpected keyword
argument 'calendar'`),所以另補**行為層**紅:保留新簽名,只把 `_possible_data_days`
的過濾短路成 `return days`(MUTANT):

```
4 failed, 1 passed in 0.58s
E   At index 0 diff: ('1', '2026-08-21', '2026-08-23') != ('1', '2026-08-21', '2026-08-21')
```

MUTANT 已還原(`grep -c MUTANT copycat/server/bars.py` → 0;`git diff --stat` 只剩
app.py +17-2 / bars.py +41-1)。

## 5. 修的內容(最小)

- `copycat/server/bars.py`:新增純函式 `_possible_data_days(days, session, calendar)`
  —— session=day 保留 `is_trading_day(d)`;session=allday 再加 `is_trading_day(d-1)`
  (夜盤跨午夜到 05:00,週五夜盤尾落在週六);`calendar is None` 不過濾。
  `build_minute` 加 keyword-only `calendar: TradingCalendar | None = None`,
  `cache.hist_missing(...)` 的結果先過濾再判斷要不要發 fetch。
- `copycat/server/app.py`:兩個呼叫點傳入 `create_app` 既有的 `trading_calendar`
  閉包變數(prod 由 `__main__` 傳 `load_trading_calendar()`;測試預設 `None`)。

**沒動**:`put_hist_range` 的負向快取語意(只寫到有證據掃過的最後一天,防分頁截斷,
review P1-2)、重試策略、log 文案以外的任何東西。

## 6. 待真實環境驗(下次 prod 重啟後)

盤前冷啟動 / 週一開站時看 `logs/server-*.log`:
`bars ... 歷史段 YYYY-MM-DD..YYYY-MM-DD 回空,不入 memo` 的**純非交易日**範圍
(如 `2026-08-23..2026-08-23`)應歸零;前端切期貨商品不再空白 10s。

## 7. 已知取捨(記 next-time)

日曆錯標「真交易日為假日」時該日 bars 不再回補(零訊號)。偵測面已有休市膠囊(#91),
且日曆缺年時 `is_trading_day` 退化成只擋週末 —— 最壞回到本修之前的行為,不會多擋。
