# /mod heal-gate-per-consumer — change spec

來源:`docs/superpowers/specs/pr-126-review.md` F-01(HIGH,Should Fix)+ F-02 / F-03 / F-04 / F-05 / F-06 / F-08
(Nice,auto-fix)。F-07(兩份邊界表合併)user 拍板**不做**。小活分流(兩檔實碼、無對外 API、無 migration):
跳 to-spec / to-tickets,保留 caller map + 白名單 + 紅先行。

## 現況 vs 目標

| | 現況(PR #126 後) | 目標 |
|---|---|---|
| `stock_source._TRADING_END` | 13:25(三消費者共用,`<`) | **13:35**(`<` 語意保留;個股 / corr 台積電腿) |
| index session 牆鐘 | `in_trading_hours_now`(共用) | **新 `in_index_heal_window_now`**(`_INDEX_HEAL_END` 13:25,`<`;與 `index_engine._WATCH_END` 同值同語意) |
| `app._default_index_source` | `_heal_gate(calendar, in_trading_hours_now)` | `_heal_gate(calendar, in_index_heal_window_now)`(簽名不動,只換牆鐘) |
| 個股 13:25–13:35 R1 / R2 / 健檢 | 關(PR #126 副作用) | **開**(逐字回到 #126 前,只差 13:35:00 那一秒 end-exclusive) |
| IX0001 收盤段看門狗 | 0 發(#126 主症狀) | 0 發(不變) |

## 為什麼(pr-126 F-01)

「13:25 起交易所不更新 → 零推播全是誤判」只量了 IX0001。個股在收盤試撮 13:25–13:30 **有** REALTIME 簿更新推播
(tc4-market-facts:TradeStatus=1、`_note_push` 不分成交 / 簿更新),08-26 / 08-27 兩日 log 反查:舊閘 13:35 開著時
該窗除整天在發的 6949 外個股零自癒 —— 個股本來就不誤判。所以 #126 對個股零收益,只剩代價:收盤集合競價期間
訂閱被 TC4 reap 掉,R1 / R2 / 健檢三條救援路全下班,五檔 / 現價停到重啟、零訊號。拆 per-consumer:index 13:25、
個股 / corr 現貨腿 13:35。

新閘落點 = `stock_source.py`(與 `in_trading_hours_now` 同檔同起點 08:30,只差上界常數),不放 `index_engine.py`:
後者的 `in_watch_window_now` 起點 09:00 是分時 watchdog 的域,REALTIME 自癒要從 08:30 試撮起救;跨模組拿
`_TRADING_START` 私有常數更糟。兩把 13:25 的同值由 `TestIndexHealWindowGate::test_end_matches_index_engine_watchdog_window` 鎖。

## Caller map

| 讀者 | 用途 | 本次 |
|---|---|---|
| `stock_source.py:~500` `heal_active=in_trading_hours` / `:~611` `:~667` `_in_trading_hours()` | 個股 session R1/R2 看門狗、健檢武裝 / 續排 | 經 `app._default_stock_source` 拿 `in_trading_hours_now` → 13:35(回舊) |
| `app.py:_default_stock_source` | 個股 session | 不動(仍 `in_trading_hours_now`) |
| `app.py:_default_index_source` | IX0001 / 櫃買 session | **改拿 `in_index_heal_window_now`**(唯一實碼 caller 改動) |
| `app.py:_default_corr_source` `segment_leg_gate(tws=)` | corr 台積電現貨腿 | 不動(仍 `in_trading_hours_now` → 13:35;2330 留在 R1 / R2 母體到 13:35) |
| `index_engine._WATCH_END` 13:25 | 分時 watchdog(另一把) | 不動;新閘與它同值(測試鎖) |
| `tests/live/test_corr_source.py::TestTwsLegClock` | 邊界表 | 13:25 / 13:26 / 13:30 → True;13:35 False 註解改口(F-06) |
| `tests/live/test_stock_source.py::TestTradingHoursGate` | 端點 | 13:34:59 / 13:35:00;新增 `TestIndexHealWindowGate` |
| `tests/server/test_main_wiring.py` | 佈線 | 兩 factory 各拿各的牆鐘 + 兩把互不牽動 |
| 動態用法 | `grep -rn "in_trading_hours_now\|_TRADING_END"` 全 repo | 只有上列 + docs;無字串反射 |

## 既有行為白名單(不得變)

1. `_TRADING_START` 08:30 含端點;兩把閘起點同值。
2. `StockQuoteSource.__init__` 簽名、`in_trading_hours` 注入參數名不動;`_heal_gate` 日曆 AND 不動。
3. 看門狗 / 健檢退避階梯、換窗、`_heal_resub`、`_note_push`、訂退時機逐字不動(`tc4.py` 不在 diff)。
4. `index_engine` 三段判定(`_WATCH_END` / `_HEAL_TAIL_END` / 日曆)不動;index session 的閘語意逐字 = #126(13:25 `<`)。
5. 期貨 / TXO 閘、corr 台期交段閘不動。
6. `_TRADING_END` 的 `<` end-exclusive 語意保留(#126 第二輪 review 拍板;13:35:00 那一秒與 #126 前的 `<=` 差異已知)。

## 驗證 seam

- 紅先行 `103689ed`:`6 failed, 60 passed` + `test_stock_source` ImportError → 🔴 `db3dd3c4` 綠 366 passed。
- mutation 級反向驗證(各撤一行)見 verification.md §4。
- 真實環境:次一交易日 `grep 零推播自癒 logs/server-<次日>.log | grep IX0001` 13:25 後 0 筆;同日 13:25–13:35 個股面
  五檔 / 現價照常跳;13:36 `curl /api/index/state` 記 twse 最後更新時戳(F-03 反證)。
