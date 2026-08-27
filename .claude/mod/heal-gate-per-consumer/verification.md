# mod/heal-gate-per-consumer — verification

主 tree 直做;branch 自 master `24129d75` 開。小活分流(兩檔實碼、無 API、無 migration):跳 to-spec / to-tickets,
保留 caller map + 白名單(change-spec.md)+ 紅先行。來源 = `docs/superpowers/specs/pr-126-review.md` F-01(HIGH)
+ F-02/03/04/05/06/08(Nice);F-07 user 拍板不做。

## 0. 入口證據

- pr-126 F-01(4.3b CONFIRMED,兩日 log 反查):舊閘 13:35 開著時 13:25–13:35 除整天在發的 6949 外個股零自癒
  → 個股在收盤試撮期本來就不誤判(TradeStatus=1 簿更新推播,`_note_push` 不分成交 / 簿更新)。
- #126 把三消費者共用的 `_TRADING_END` 一起關到 13:25 → 對個股零收益,純失去收盤集合競價期間 R1 / R2 / 健檢。

## 1. 紅先行(🔴 改 assertion 的合法通道)

- `103689ed` test:`TestTwsLegClock` 13:25 / 13:26 / 13:30 → True、13:35 False(`<` 鎖);`TestTradingHoursGate`
  端點 13:34:59 / 13:35:00;新 `TestIndexHealWindowGate`(10 列邊界 + 與 `index_engine._WATCH_END` 同值);
  `test_main_wiring` 兩 factory 各拿各的牆鐘 + `test_stock_and_index_heal_gates_are_two_different_clocks`。
  紅:`6 failed, 60 passed` + `tests/live/test_stock_source.py` 收集期 ImportError(`in_index_heal_window_now` 尚不存在)。
- `db3dd3c4` fix:`_TRADING_END = 13:35`、新 `_INDEX_HEAL_END = 13:25` + `in_index_heal_window_now`、
  `app._default_index_source` 換牆鐘 → `366 passed`(corr_source / stock_source / main_wiring / index_engine / stock_engine)。

## 2. 假說

單一:症狀(IX0001 收盤段 19 發)只在 index session;個股 / corr 現貨腿在 13:25–13:30 有推播,閘該留 13:35。

## 3. 修法與 commit

| commit | 類 | 內容 |
|---|---|---|
| `103689ed` | test | 紅先行(三檔) |
| `db3dd3c4` | 🔴 | per-consumer 閘 + 註解收 F-02 / F-03 / F-05 |
| `d0c06501` | chore | 本輪 change-spec;pr-126 文件收修 F-02 / F-04 / F-08(next-time、舊 artifact) |
| `8eba5271` | chore | two-axis review round 1 收修(F-S2/S4 命名條、F-S3 CLAUDE.md §4、F-S4、S2、S3、S5) |

## 4. 反向驗證(mutation 級,各撤一行;在 `db3dd3c4` 上實跑,`git checkout --` 還原)

| 突變 | 紅的測試 |
|---|---|
| M1 `_TRADING_END` 13:35 → 13:25(value-only revert) | `TestTwsLegClock[13-25/13-26/13-30-True]` ×3 + `TestTradingHoursGate` → `4 failed, 135 passed` |
| M2 `_default_index_source` 接回 `in_trading_hours_now` | `test_stock_and_index_heal_gate_ands_the_calendar[index…-True]` + `…two_different_clocks` → `2 failed, 137 passed` |
| M3 `_INDEX_HEAL_END` 13:25 → 13:35 | `TestIndexHealWindowGate::test_boundary[t4/t5/t6-False]` ×3 + `test_end_matches_index_engine_watchdog_window` → `4 failed, 135 passed` |
| M4 `_TRADING_END` 比較 `<` → `<=` | `TestTwsLegClock[13-35-False]` + `TestTradingHoursGate` → `2 failed, 101 passed` |

M4 正好只由 13:35 列擋住 = pr-126 F-06 的註解現在放對列(13:35 列鎖語意、13:25/26/30 列鎖值)。

## 5. 白名單核對(change-spec §白名單;Standards 軸逐條 6/6 PASS,主 session 復核)

1. `_TRADING_START` 08:30 含端點,兩把同起點 —— 兩函式皆 `_TRADING_START <= t`。
2. `StockQuoteSource.__init__` 簽名 / `in_trading_hours` 參數名 / `_heal_gate` —— diff 未觸及,`app.py` 只換 callable。
3. 退避 / 換窗 / `_heal_resub` / `_note_push` / 訂退時機 —— `tc4.py` 不在 diff。
4. `index_engine` 三段判定不動;index 閘 13:25 `<` 逐字 = #126。
5. 期貨 / TXO / corr 台期交段閘不動 —— grep 無其他 caller 變動。
6. `<` end-exclusive 保留 —— 兩處皆 `<`。

## 6. pr-126 finding 對帳(Spec 軸)

F-01 PASS / F-02 PASS(4 處:三份 md 改口,code comment 該句移除後 S2 補回事實半句)/ F-03 PASS / F-04 PASS(S5 尾註後)
/ F-05 PASS / F-06 PASS(S3 補 13:25 列後)/ F-07 N/A(user 不做,未誤動)/ F-08 PASS(兩條回 `[ ]`;S4 的新 `[x]` 已改回)。

## 7. 自動化 gate(`db3dd3c4`–`8eba5271`,主 tree)

```
3132 passed, 1 warning in 185.38s (0:03:05)        # 全量,db3dd3c4
139 passed                                         # 三檔受影響測試,8eba5271
All checks passed!                                 # ruff
0 errors, 0 warnings, 0 informations               # pyright
42/42 PASS                                         # copycat validate
```
前端零改動(不跑 npm gate)。

## 7a. two-axis review round 1(`code-review-round-1.json`)

Standards 5 條(P2×2:verification.md 待寫 / 命名條不該勾;P3×3)+ Spec 5 條(P2×2:同前兩題;P3×3:code comment
補事實、註解列指認、舊 caller map 尾註)。白名單 6/6 PASS、三類 commit 零混雜、零 scope creep(S4 已改回)。
增量 diff(`8eba5271`,comments / docs only)由主 agent 機械快篩:零行為改動、ruff / pyright / 139 passed。

## 8. 真實環境

- 本輪出貨在收盤後;user 拍板出貨後**今晚起 prod**(含本 PR),次一交易日(08-28)驗:
  - `grep "零推播自癒" logs/server-20260828-*.log | grep IX0001 | grep -E " 13:(2[5-9]|3[0-9]):"` → 0 筆;
  - 13:25–13:35 個股面五檔 / 現價照常跳、自癒 log 個股在該窗仍只有冷門檔(6949 型)—— 閘留 13:35 的直接證據;
  - 13:36 `curl /api/index/state` 記 twse 最後更新時戳 / minutes 最大鍵(F-03「誤判 vs 真死」反證 + 第二段閘留尾量測)。

## 9. 留尾(`docs/next-time.md` 2026-08-27 節)

命名 🔵(`in_trading_hours_now` 13:30–13:35 尾巴仍回 True,F-S2 / S4 重申)/ index 閘代價兩條綁「13:30 回來一小段」
第二段閘 / IX0001 收盤最後一筆時戳量測 / 兩條「已出貨待驗」(F-08)。
