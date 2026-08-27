# /mod stock-heal-gate-end-1325 — change spec

> **2026-08-27 pr-126 review 收修(mod/heal-gate-per-consumer)**:F-01 HIGH —— 本檔「三消費者共用的閘一起改 13:25」
> 已被推翻,現況 = **只有 index session** 吃 `in_index_heal_window_now` 13:25,`_TRADING_END` 改回 13:35(個股 / corr
> 台積電腿)。見 `.claude/mod/heal-gate-per-consumer/change-spec.md`。下列 F-02(代價 b)/ F-04(caller map 2330 列 +
> 代價第四條)文字已在本檔改對,其餘段落保留當時決策原貌。

小活分流(單檔一個常數、無對外 API、無 migration):跳 to-spec / to-tickets,保留 caller map + 白名單 + 紅先行。

## 現況 vs 目標

| | 現況 | 目標 |
|---|---|---|
| `stock_source._TRADING_END` | 13:35(docstring「收盤補正止」,啟發式;`<=` 含端點) | **13:25**(收盤試撮起點,**end-exclusive** `<`,與 `index_engine._WATCH_END` 同語意) |
| `in_trading_hours_now(13:25:00 … 13:35)` | True | False |
| IX0001 收盤段看門狗 | 13:25:46–13:34:51 每 30 s 一發,19 發 / 交易日 | 0 發 |

## 為什麼(user 2026-08-27 拍板)

交易所 13:25–13:30 收盤試撮只收單不撮合、指數不更新;13:30 統一撮合後也只剩收盤那一筆。看門狗「30 s 零推播 =
訂閱死了 → 退訂重訂」在這 10 分鐘全是誤判(19/19 attempt 1),每發白付一對 UNSUB+SUB。閘只管看門狗與健檢、**不退訂**,
13:30 收盤推播照收。代價(review Spec P2-2 / P2-3 / P2-4 校正後,user 知情):訂閱若剛好在 13:25–13:30 死掉 ——
(a) 加權分時由 `index_engine._HEAL_TAIL_END` 13:40 尾段回補補齊,**現價欄不會**(`_merge_backfill` 只寫 minutes);
(b) **在收盤試撮期訂閱死掉這個情境下**,個股側當日重補只剩 `set_main_contract`(手動切主圖)與 `_handle_reconnect`(斷線重連)會出手
(「漲跌停值變」與逾時重排兩個入列點該情境下不觸發 —— pr-128 F-04);群組成員 60 s 輪詢被
`_backfilled` 擋住,不切主圖補不回來(pr-126 F-02 校正:原句「沒有當日重補路徑」只證了輪詢那條,放大成「無路徑」是錯的);
(c) 13:25–13:35 新加自選不再武裝健檢、不發 `_on_no_data`(舊上界 13:35 亦然,提早 10 分鐘)。
(d)(pr-126 F-04 補)corr session 在 13:25–13:30 整條被 reap 時,R1 整批重掛清單裡沒有 2330,要到隔天 08:30 才有人救;
反向,2330 是該窗少數仍在推的腿,移出母體等於拿掉它對 R1「有腿在流」的抑制,corr 的 R1 在該段更容易成立。
這幾條正是 user 提的「13:30 回來一小段」第二段閘的價值所在,留尾等收盤資料到達時戳量到再決定。
(per-consumer 收修後 (b)(c)(d) 對個股 / 2330 不再成立 —— 閘留 13:35;只剩 (a) 與「13:25 後新加**指數**訂閱不武裝健檢」。)

## Caller map(`in_trading_hours_now` / `_TRADING_END`)

| 讀者 | 用途 | 影響 |
|---|---|---|
| `stock_source.py:482` `heal_active=in_trading_hours` | 個股 session R1/R2 看門狗 | 13:26 起不再重掛(per-consumer 收修後不再成立,閘留 13:35) |
| `stock_source.py:583` / `:639` `_in_trading_hours()` | 個股健檢(R3 no-data 階梯)武裝 / 續排 | 13:26 起不再武裝 / 續排(同上,不再成立) |
| `app.py:365` `_default_stock_source` | 個股 session(日曆 AND 牆鐘) | 同上(不再成立) |
| `app.py:374` index session | IX0001 / OTC 看門狗 | 19 發歸零(本案主症狀) |
| `app.py:413` `segment_leg_gate(tws=)` | corr 台積電現貨腿 | 13:25 起退出 R1 **與** R2 母體(逐 symbol 閘扣在 `tc4._heal_tick:624` 母體形成處,不是 R2 迴圈 `continue`;pr-126 F-04 校正;per-consumer 收修後不再成立,2330 留 13:35) |
| `index_engine._WATCH_END` 13:25 | 分時 watchdog(**另一把**,已是 13:25,`<`) | 不動;本改動改 `<` 後兩把同值同語意 |
| `signal_state._SESSION_END` / `verify._DOMAIN_END` 13:30、`stock_models` 試撮窗 | 訊號域 / 驗證域 / 標示用 | **刻意不對齊**,不動 |

## 既有行為白名單(不得變)

1. `_TRADING_START` 08:30 與「含端點」語意;08:30–13:25 內所有判定逐字同前。
2. 看門狗 / 健檢的退避階梯、換窗、`_heal_resub`、`_note_push` 逐字不動;訂閱與退訂時機不動(收工才 UNSUB)。
   **已知行為變更(非白名單)**:`subscribe_symbol` 的健檢武裝 `and self._in_trading_hours()` 隨閘提早到 13:25 關。
3. `index_engine` 的 `_WATCH_END` / `_HEAL_TAIL_END` / 交易日曆三段判定不動。
4. 期貨 session `in_futures_session_now`、TXO `in_txo_session` 不動(不同市場不同表)。
5. 交易日曆 AND(`app._heal_gate`)不動。

## 驗證 seam

- `tests/live/test_corr_source.py::TestTwsLegClock`(邊界表,紅先行 c10918fc:13:26 / 13:30 / 13:35 轉 False;review 後
  13:25 轉 False、13:24 True)+ `tests/live/test_stock_source.py::TestTradingHoursGate`(本檔端點鏡像,秒級)。
- 真實環境:次一交易日 `grep "零推播自癒" logs/server-*.log | grep IX0001 | grep -E " 13:(2[5-9]|3[0-9]):"` 應 0 筆;
  同日 13:36 `curl /api/index/state` 看 twse 分時最後一鍵仍是 1330(1K 尾段回補照補)+ 記收盤資料到達時戳(留尾)。

## 留尾(next-time)

- 收盤資料到達時戳未量(1K 有 13:33 的 row → 收盤補正可能 13:3x 才落地):量到若是 13:30:0x 即到,可再加
  「13:30 回來一小段」的第二段閘;若 13:33,加了也是誤判,維持本案。
