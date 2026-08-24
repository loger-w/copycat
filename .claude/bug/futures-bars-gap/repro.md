# 期貨 K 線偶發落空 — repro / root cause(2026-08-24)

## 症狀(user 回報)
期貨分時/K 線偶爾落空;user 貼 17:16:05 log:TXF 1K「10.0s 內首頁未備妥,回空(timeout,非無資料)」
→ bars「歷史段 2026-08-23..2026-08-23 回空,不入 memo」→ `GET /api/market/bars/TXF?tf=1&days=5&session=allday` 200。

## 蒐證(logs/server-20260824-0854.log,全日)
- `copycat.live.tc4 INFO history TC.F...首頁未備妥` 28 次 = `futures_engine WARNING 期貨 K 線 timeout` 28 次
  = `bars ... 歷史段 ... 回空,不入 memo` 28 次 —— **三者逐事件同毫秒配對,28/28/28**。
- 28 次歷史段範圍**全部**是 `2026-08-23..2026-08-23`(週日,TXF/TMF/MXF 輪流)。
- **零今日段 timeout**(今日段 fetch 無對應事件)。個股側全日零逾時(排除 TC4 整體異常)。

## Root cause(實驗證實,一次一假說)
1. `bars.py::hist_missing`(:161)迭代**日曆日**,無交易日曆概念 → 2026-08-24(一)的
   days=5 窗含 08-23(日)。
2. `put_hist_range`(:164)負向快取「只寫到最後一個有資料的日子」(防 TC4 分頁截斷,review P1-2)
   → 窗尾的非交易日永遠不入 memo。allday 序列中 08-22(六)有資料(週五夜盤尾 00:00-05:00,
   已被 memo),08-23(日)真無資料 → **永久 missing**。
3. 每次 build_minute 都對 TC4 重發「週日單日」1K 歷史查詢;TC4 對無資料日**不回首頁**(掛滿
   10s deadline;log 印「timeout,非無資料」但實為「無資料所以永無首頁」——兩態在 TC4 協議上
   不可分)→ 每次請求白付 10s。
4. 使用者可見面:frontend `useFuturesBars` days=5&session=allday;切商品/切週期 → query key 換
   → 無 previous data → **圖空白等滿 10s** =「偶爾落空」(週一與連假後日必現);futures 路徑
   `app.py:1624` `bars, _ = await build_minute(...)` **丟棄 status** → 零錯誤訊號。
   另:status 被歷史段 timeout 汙染(stock 路徑會外洩該 status;futures 路徑丟棄)。

## 紅 loop
`tests/server/test_bars_gap.py`(新):fake fetch 記錄呼叫;memo 先種 08-20..08-22;
today=08-24(一)、days=5、session=allday。斷言:(a) 不對「純非交易日」範圍發 fetch;
(b) status 不被不可能有資料的日子汙染(today ok → 整體 ok)。現行 code 兩者皆紅。

## 修法(最小)
`build_minute` 收 optional 交易日曆 predicate,`missing` 過濾掉「不可能有資料的日子」:
- session=day:`is_trading_day(d)`
- session=allday:`is_trading_day(d) or is_trading_day(d-1)`(前一交易日夜盤尾 00:00-05:00 落在 d)
兩個 caller(app.py:1314 stock、:1624 market)接上 app 既有 calendar。日曆缺年 → is_trading_day
退化成「只擋週末」(既有語意),安全。

## 已知取捨(記 next-time)
日曆錯標「真交易日為假日」時該日 bars 不再回補(零訊號);偵測面已有休市膠囊(#91)。

## 反向驗證(2026-08-24)

修完後把 `copycat/` 下的兩檔改動 stash 掉、測試檔留著:

```
$ git stash push -m revfix copycat/server/bars.py copycat/server/app.py
$ .venv/Scripts/python -m pytest tests/server/test_bars_gap.py -q
4 failed, 1 passed
  FAILED ...::test_pure_non_trading_gap_sends_no_history_fetch
  FAILED ...::test_status_not_polluted_by_impossible_day
  FAILED ...::test_real_trading_day_gap_still_fetched_with_filtered_endpoints
  FAILED ...::test_day_session_filters_saturday_too
$ git stash pop
$ .venv/Scripts/python -m pytest tests/server/test_bars_gap.py -q
5 passed
```

stash 態的紅是 `TypeError: build_minute() got an unexpected keyword argument 'calendar'`
(簽名層),所以另補一次**行為層**紅:保留新簽名、只把 `_possible_data_days` 的過濾
短路成 `return days`(MUTANT)→ 同樣 4 failed / 1 passed,且紅在斷言而非型別:

```
E   At index 0 diff: ('1', '2026-08-21', '2026-08-23') != ('1', '2026-08-21', '2026-08-21')
```

第 5 條 `test_no_calendar_keeps_old_behavior` 在三種狀態下都綠 —— 它鎖的正是舊行為
(對 08-23 發歷史 fetch、status=timeout),等於把「`calendar=None` 逐字不變」寫成合約。

## review round-1 後補(0 P0/P1;C1/C2/C6 文件化)
- **C1 當日段刻意不套過濾(不對稱是設計)**:週日/假日的「今日段」查詢仍會白付 10s(15s TTL 節流)——
  因為日曆錯標時,歷史段少補一天是小傷,當日段被過濾掉是**盤中主圖永久空白**,風險不對稱。
- **C2 連假首日若無夜盤且為窗尾唯一可能日,仍會重複探測**(2026-02 春節形狀);要收得動
  put_hist_range last_seen 防護,不划算,相對修前(整段連假全探)已嚴格改善。
- **C6 日曆只載 2026**:2027 起國定假日效益靜默退化成只擋週末 —— 續 `years_loaded` 過期警示既有機制。
