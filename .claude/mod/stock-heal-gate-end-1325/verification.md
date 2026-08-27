# mod/stock-heal-gate-end-1325 — verification

主 tree 直做;branch 自 master `59b70213` 開。小活分流(單常數、無 API、無 migration):跳 to-spec / to-tickets,
保留 caller map + 白名單(change-spec.md)+ 紅先行。

## 0. 入口證據(2026-08-27,prod `51b93006` 日盤 log)

```
grep "零推播自癒" logs/server-20260827-0814.log | grep IX0001 | grep -E " 13:(2[5-9]|3[0-9]):" | wc -l → 19
13:25:46 … 13:34:51 每 30 s 一發,attempt 全 1(重掛 snapshot 清 attempts,見 tc4-market-facts)
```
閘 = `stock_source.in_trading_hours_now`(`_TRADING_END` 13:35);交易所 13:25 起收盤試撮不更新指數。

## 1. 紅先行(🔴 改 assertion 的合法通道)

- `c10918fc` test:`TestTwsLegClock` 邊界表 13:26 / 13:30 / 13:35 → False → `3 failed, 6 passed`(常數仍 13:35)。
- `320639c2` fix:`_TRADING_END = 13:25` → 351 passed(corr_source / stock_source / main_wiring / index_engine / stock_engine)。
- review 後第二輪:`test` 邊界表 13:25 → False、13:24 → True + `TestTradingHoursGate` 鏡像;stash 實作 → `2 failed, 9 passed`;
  `fix` 改 `<` end-exclusive → 126 passed。

## 2. 假說

單一:看門狗閘窗涵蓋交易所不更新的 13:25–13:35;19 發全落在 13:25:46 之後。

## 3. 修法與 commit

| commit | 類 | 內容 |
|---|---|---|
| `c10918fc` | test | 邊界表紅先行 |
| `320639c2` | 🔴 | `_TRADING_END` 13:35 → 13:25 + 註解 / docstring |
| `cc731a1d` | chore | change-spec(caller map + 白名單)、next-time 勾銷 IX0001 兩條 |
| `58d680ae` | test | 13:25 → False、13:24 → True;`test_stock_source::TestTradingHoursGate` 端點鏡像 |
| `f8b494d0` | 🔴 | `<=` → `<` end-exclusive(與 `index_engine._WATCH_END` 同語意);註解改口三條代價、三把不對齊時窗 |
| `200597c5` | chore | change-spec 代價 / caller map / 白名單改口、next-time 命名 🔵 + 三條代價留尾、review JSON |

## 4. 反向驗證(PASS)

```
git stash push copycat/live/stock_source.py → TestTwsLegClock 13:25 列 + TestTradingHoursGate 2 failed
git stash pop                                → 126 passed
```

## 5. 白名單核對(review Standards 逐條 PASS 5/5;主 session 復核)

1. `_TRADING_START` 08:30 含端點 —— `<=` 左側未動,`TestTradingHoursGate` 釘 08:29:59 False / 08:30:00 True。
2. 退避 / 換窗 / `_heal_resub` / `_note_push` / 訂退時機 —— diff 未觸及(`tc4.py` 不在 diff)。
   已知行為變更(非白名單):`subscribe_symbol` 健檢武裝隨閘提早到 13:25 關。
3. `index_engine._WATCH_END` / `_HEAL_TAIL_END` / 日曆三段 —— 檔案不在 diff。
4. `in_futures_session_now` / `in_txo_session` —— 不在 diff。
5. `app._heal_gate` —— app.py 不在 diff。

## 6. 真實環境

- 本輪無法當日驗(改動在收盤後出貨,prod 15:20 起的 59b70213 不含)。次一交易日 prod 重啟含本 PR 後:
  `grep "零推播自癒" logs/server-<次日>.log | grep IX0001 | grep -E " 13:(2[5-9]|3[0-9]):"` → 0 筆;
  同日 13:36 `curl /api/index/state`:twse minutes 最大鍵仍 1330(尾段回補照補)+ 記收盤資料到達時戳(留尾用)。
- 未改功能抽查(自動化代):個股 session 看門狗 / 健檢 20+ 條、index_engine watchdog 三段、corr 時段閘三條全綠。

## 7. 自動化 gate(最終 HEAD 200597c5,主 tree)

```
3119 passed, 1 warning in 185.17s (0:03:05)
All checks passed!
0 errors, 0 warnings, 0 informations
42/42 PASS
 Test Files  151 passed (151)
      Tests  2829 passed (2829)
tsc exit=0
eslint exit=0
```
前端零改動(react-doctor --scope changed 無檔可掃)。

## 7a. two-axis review round 1(`code-review-round-1.json`)

Standards 4 條(P2 命名 → next-time、P2 端點語意 → 收修、P3 ×2)+ Spec 6 條(4 P2:含端點假、個股兜底不成立、
現價欄不更新、新訂閱不武裝健檢 → 收修 / 改口;2 P3 → 收修)。白名單 5/5 PASS,零 creep。

## 8. 需 user 過目 / 拍板

- 無 UI 變更。三條代價 user 已知情(對話中「訂閱死在試撮 5 分鐘內」的取捨),review 補的兩條事實(個股側無當日重補、
  現價欄不更新)在收尾回報中告知。

## 9. 留尾(`docs/next-time.md` 2026-08-27 節)

命名 🔵(`in_trading_hours_now` 名不符實)/ 三條代價綁「13:30 回來一小段」第二段閘 / 收盤資料到達時戳量測。
