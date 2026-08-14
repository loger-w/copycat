# verification:fix/index-line-vanish

## 自動化 gate(2026-08-14,fix 波後 HEAD 5b3ae2c3)

| step | command | exit | 結果 |
|---|---|---|---|
| 測試 | `.venv\Scripts\python -m pytest -q` | 0 | `2673 passed, 1 warning in 141.22s`(baseline 2662 + 本輪淨增 11) |
| lint | `.venv\Scripts\python -m ruff check copycat tests` | 0 | `All checks passed!` |
| 型別 | `.venv\Scripts\python -m pyright` | 0 | `0 errors, 0 warnings, 0 informations` |

frontend 未動(零 frontend diff)→ 前端 gate 不適用。`copycat validate`(先跑
four/five 兩份 replay)→ **42/42 PASS,exit 0**。

## SC 對照

- SC-1(heal 無進展不宣告成功):`test_heal_no_progress_is_not_claimed_as_success` PASS。
- SC-2(variant 遞增逃逸 + 成功帶 minutes 全量):`test_heal_escalates_window_variant_until_data_returns` PASS(終態 variant=1,L1-P1-3 修訂後契約)。
- SC-3′(stub 簽名 log):`TestFetchDayMinutesStubSignature` 2 條 PASS。
- SC-4(variant 窗口字串):`TestFetchDayMinutesWindowVariant` 3 條 PASS。
- SC-6(差量進展/部分進展送達/variant 黏住/封頂 log):`test_heal_partial_progress_still_reaches_clients` / `test_frozen_stub_value_drift_is_not_progress` / `test_lag_recovery_keeps_variant_and_swap_day_resets_it` / `test_window_variant_cap_logs_separately` PASS。
- SC-5(真實環境):TC4 語意層已由活體實驗取證(evidence/,盤中 12:16–13:02 真 TC4);
  prod 形狀層 = **待 prod 重啟 + 次一交易日早晨盤中觀察**(若再踩 boot timeout,
  09:04 首發 heal 應 log「無進展」+「疑似凍結 stub」,09:06 第二發換窗後分時線回來)。

## 白名單逐條(fix-spec 六條)

1. boot/rollover/reconnect retry 語意:`test_start_connection_error_sets_stale_then_retry_recovers` / `test_schedule_retry_single_flight` PASS。
2. heal 節流/退避/不清 stale/尾窗/封頂停止/開盤豁免:T-2/T-5/T-4/T-3 + `test_heal_stops_when_day_complete` + `test_minutes_lag_heal_grace_at_open` PASS。
3. 成功 heal 帶 minutes 全量一次(#45):`test_heal_backfill_reaches_connected_clients_via_broadcast` PASS(治具改為真追上牆鐘的回補,契約斷言未動 — implementer deviation 已審核接受)。
4. fetch_day_minutes 解析規則:`TestFetchDayMinutes` 全 PASS。
5. bars 三態契約:`TestBarsStatus` + `tests/live/test_stock_bars.py` + `test_futures_bars.py` 全 PASS(tc4.py 對 master 零 diff → bars 路徑行為與 master 全等)。
6. rollover pending/swap(T-1):`test_pending_retry_does_not_broadcast_minutes` PASS。

## 反向驗證(/bug 專屬 gate)

- 核心波:`git revert --no-commit`(兩個 [green])→ 8/9 新測試紅、紅在症狀
  (stub 偽造完整日 / variant 參數不存在 / 無進展照樣廣播 / variant 恆 0)→
  `git reset --hard` 還原 → 71/71 綠。詳 repro.md。
- fix 波:implementer 於 red commit(4ab993d0)實跑 4 failed / 33 passed(紅在
  SC-3′/SC-6 症狀),green commit 後全綠。

## 回歸抽樣(未改功能)

pytest 全量 2673 綠即涵蓋;另 targeted:`test_stock_bars.py + test_futures_bars.py +
test_river_backfill.py + test_index_engine.py + test_stock_source.py` 162 passed
(fix 波 implementer 實跑)。

## Blast radius

- `fetch_day_minutes` caller:僅 index_engine(boot/rollover/heal)— grep 證實。
- `_collect_history` caller(stock/futures bars 路徑):tc4.py 已 revert 至 master
  逐字節相等,零波及。
- Protocol 簽名新增 keyword(預設值向後相容):FakeIndexSource 已同步;--verify 模式
  index engine 為 None 不受影響;prod `_default_index_source()` = StockQuoteSource 已實作。
