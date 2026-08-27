# /mod stock-heal-gate-end-1325 — change spec

小活分流(單檔一個常數、無對外 API、無 migration):跳 to-spec / to-tickets,保留 caller map + 白名單 + 紅先行。

## 現況 vs 目標

| | 現況 | 目標 |
|---|---|---|
| `stock_source._TRADING_END` | 13:35(docstring「收盤補正止」,啟發式) | **13:25**(收盤試撮起點,含該分) |
| `in_trading_hours_now(13:26 … 13:35)` | True | False |
| IX0001 收盤段看門狗 | 13:25:46–13:34:51 每 30 s 一發,19 發 / 交易日 | 0 發 |

## 為什麼(user 2026-08-27 拍板)

交易所 13:25–13:30 收盤試撮只收單不撮合、指數不更新;13:30 統一撮合後也只剩收盤那一筆。看門狗「30 s 零推播 =
訂閱死了 → 退訂重訂」在這 10 分鐘全是誤判(19/19 attempt 1),每發白付一對 UNSUB+SUB。閘只管看門狗與健檢、**不退訂**,
13:30 收盤推播照收。唯一代價:訂閱若剛好在試撮 5 分鐘內死掉,收盤那筆 REALTIME 收不到 —— 分時由 1K 回補兜底
(`index_engine._HEAL_TAIL_END` 13:40 尾段回補、個股 60 s 輪詢自癒)。

## Caller map(`in_trading_hours_now` / `_TRADING_END`)

| 讀者 | 用途 | 影響 |
|---|---|---|
| `stock_source.py:482` `heal_active=in_trading_hours` | 個股 session R1/R2 看門狗 | 13:26 起不再重掛 |
| `stock_source.py:583` / `:639` `_in_trading_hours()` | 個股健檢(R3 no-data 階梯)武裝 / 續排 | 13:26 起不再武裝 / 續排 |
| `app.py:365` `_default_stock_source` | 個股 session(日曆 AND 牆鐘) | 同上 |
| `app.py:374` index session | IX0001 / OTC 看門狗 | 19 發歸零(本案主症狀) |
| `app.py:413` `segment_leg_gate(tws=)` | corr 台積電現貨腿 | 13:26 起不進 R2 母體 |
| `index_engine._WATCH_END` 13:25 | 分時 watchdog(**另一把**,已是 13:25) | 不動;本改動使兩把對齊 |

## 既有行為白名單(不得變)

1. `_TRADING_START` 08:30 與「含端點」語意;08:30–13:25 內所有判定逐字同前。
2. 看門狗 / 健檢的退避階梯、換窗、`_heal_resub`、`_note_push` 逐字不動;訂閱與退訂時機不動(收工才 UNSUB)。
3. `index_engine` 的 `_WATCH_END` / `_HEAL_TAIL_END` / 交易日曆三段判定不動。
4. 期貨 session `in_futures_session_now`、TXO `in_txo_session` 不動(不同市場不同表)。
5. 交易日曆 AND(`app._heal_gate`)不動。

## 驗證 seam

- `tests/live/test_corr_source.py::TestTwsLegClock`(邊界表,紅先行 c10918fc:13:26 / 13:30 / 13:35 轉 False)。
- 真實環境:次一交易日 `grep "零推播自癒" logs/server-*.log | grep IX0001 | grep -E " 13:(2[5-9]|3[0-9]):"` 應 0 筆;
  同日 13:36 `curl /api/index/state` 看 twse 分時最後一鍵仍是 1330(1K 尾段回補照補)+ 記收盤資料到達時戳(留尾)。

## 留尾(next-time)

- 收盤資料到達時戳未量(1K 有 13:33 的 row → 收盤補正可能 13:3x 才落地):量到若是 13:30:0x 即到,可再加
  「13:30 回來一小段」的第二段閘;若 13:33,加了也是誤判,維持本案。
