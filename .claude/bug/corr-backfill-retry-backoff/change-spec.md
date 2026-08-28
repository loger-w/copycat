# bug/corr-backfill-retry-backoff — river 1K 回補逾時重試改遞增退避 8 輪

日期:2026-08-28。來源:`copycat-handoff-2026-08-27-discussion.md` §1-2 / `copycat-handoff-2026-08-28-q4-q5.md` §1.2
(「corr 台積電腿 1K 開機三輪 timeout 就放棄 … 修法候選 = 退避到成功(上限拉長或改『開盤後仍缺 seed 就再排』)」);
08-28 user 拍板題 4「順帶」。真事件:`logs/server-20260826-0851.log` 08:52 TSMC 腿首輪逾時 → 08:53:17 / 08:53:57 / 08:54:37 三輪重試 → 放棄,整天無 seed。

## 1. 現況 vs 目標

| 項 | 現況 | 目標 |
|---|---|---|
| 退避 | 固定 `_BACKFILL_RETRY_SECS` 30 s | 遞增:30 → 60 → 120 → 240 → 480 → 600 封頂(`_retry_delay_secs`) |
| 輪數上限 | 3(合計 90 s) | 8(合計 2730 s ≈ 45.5 分) |

取「上限拉長 + 退避遞增」而非「開盤後仍缺 seed 就再排」:後者要新增一個時段驅動的排程器與「缺 seed」判準,
本案的目標只是蓋過開盤 TC4 忙碌窗(幾分鐘級),8 輪 45 分已足;且仍有界,不違反檔頭「沒有輪數上限則整天重打必敗請求」的取捨。

## 2. Caller map

`_BACKFILL_RETRY_SECS` 讀者只有 `_backfill_retry`(改讀 `_retry_delay_secs`);`_BACKFILL_RETRY_MAX_ROUNDS` 讀者只有 `_backfill_river` 放棄分支。
tests:`tests/server/test_corr_engine_river.py` 六條 monkeypatch `_BACKFILL_RETRY_SECS`。無其他 caller。

## 3. 既有行為白名單

1. single-flight / `_merge_into_inflight_round` 語意不變(reconnect 整輪併回歸零輪數;重試腿併回不動輪數)。
2. 放棄那一刻歸零、重試 task 非預期例外歸零 不變。
3. `close()` 取消所有 `_backfill_retry_tasks` 不變(600 s 睡眠中的 task 一樣被 cancel)。
4. 首輪退避 30 s 逐字同(第 1 輪 = `_BACKFILL_RETRY_SECS`)。
5. `apply_backfill` 以 session 比對丟棄過期回補 不變(跨場次晚到的重試由它擋)。

## 4. 行為改動(🔴 一筆)

退避階梯 + 上限 8。**事前標該變**:`test_retry_rounds_are_capped`(4 → 9 發)與 `test_giving_up_resets_the_round_for_the_next_episode`(4/8 → 9/18 發)。

## 5. Seams

- `test_retry_delay_ladder_doubles_from_30s_and_caps_at_10min`(純函式階梯)
- `test_retry_rounds_are_capped`、`test_giving_up_resets_the_round_for_the_next_episode`(改口的既有測試,紅先行)
