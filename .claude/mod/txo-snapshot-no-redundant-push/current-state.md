# 現況(/mod txo-snapshot-no-redundant-push)— 2026-08-19

來源:handoff `docs/superpowers/specs/2026-08-19-browser-crash-scan-handoff.md` R1;
量測 `docs/research/2026-08-19-browser-crash-scan.md`(14:22 盤後 `/ws/txo-pnl` 1 msg/s、23.2 KB/s、
內容去掉 `generated_at` 逐字相同;`dropped_foreign_ticks=3,089,555` vs `ticks=2300`)。

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| `EngineRuntime._consume`(`copycat/server/engine.py:295-297`) | `self._agg.route(tick)` 後**無條件** `_mark_changed()`(version+1、Event set) | 只有 route 真的改到 snapshot 相關狀態才 `_mark_changed()` |
| `ChainAggregator.route`(`copycat/live/aggregate.py:70-77`) | 回 `None`;三條路:spot 前綴 → 覆寫 `spot_millipts`;非本鏈 symbol → `dropped_foreign_ticks += 1` 早退;否則 `_ingest`(內含 stale-drop:`cum_volume <= last` 早退) | 回 `bool`:foreign 早退 → False;stale-drop → False;spot 價未變 → False;其餘 True(`_ingest` 有寫入 pos / totals) |
| `EngineRuntime.snapshots()`(`engine.py:127-137`) | 版本比對後 yield `latest_snapshot()`,再 sleep throttle;**無內容比對**;多 client 共用單一 `asyncio.Event`,任一 client `clear()` 後其他還在 sleep 的 client 回來 `wait()` 會卡住(漏一次版本,`WS-TXO-SHARED-EVENT`) | (a) 內容比對:與上次 yield 的 payload(排除 `generated_at`)相同 → 不 yield;(b) Event 換代:`_mark_changed` set 舊 Event 並換新 Event,consumer 先比 version 再等當下 Event,不再有 clear 競爭 |
| `_mark_changed` 其他 caller | `_set_status`(engine.py:347-350;backfilling / degraded / live 轉換) | 不變 |
| 對外契約 | `/ws/txo-pnl` 首則 = `latest_snapshot()`(app.py:1142),後續 relay `snapshots()`;payload shape 不變 | shape 不變;只是頻率由「有 tick 就 1 Hz」變「內容有變才推(仍 ≥ throttle 間隔)」 |
| 前端 `useTxoSnapshot.ts` | 只 `setData(JSON.parse)`;無 staleness watchdog;`App.tsx:357` 顯示 `更新 {generated_at}` | 不動;`更新` 時戳語意由「最後推播時間」變「最後內容變動時間」(可指認差異,列 SC) |

## Caller map(含動態用法)

- `ChainAggregator.route`:生產呼叫兩處 — `engine.py:296`(_consume)與 `copycat/live/handover.py:63`
  (`run_handover` flush buffer 逐筆 route,忽略回傳值;交接結束由 `_set_status("live")` 統一標 changed)
  `[amendment 2026-08-19: review R4]`;測試 `tests/live/test_aggregate.py` 多處(皆忽略回傳值,回傳 bool 向後相容)。
- `EngineRuntime.snapshots()`:`app.py:1143`(relay);`tests/server/test_engine.py:413` 直接迭代;
  `tests/server/test_app.py:117` / `tests/server/test_ws_disconnect.py` 經 WS。
- `_mark_changed`:`engine.py:297`(_consume)、`:350`(_set_status)。`_changed` / `_version` 無外部讀者(grep tests/ copycat/ 零命中)。
- `latest_snapshot()`:`app.py:1120/1132/1142` + `snapshots()`;不改。
- 動態用法:無 getattr / 字串反射;`_source.on_reconnect` 是另一機制。

## Backward compat / migration

- 無資料格式 / API shape 變更;無 migration。`route` 回傳型別 `None → bool` 是加法,舊 caller 忽略回傳值不受影響。
- 行為差異只在推播**頻率**;前端無依賴 1 Hz 的邏輯(grep `generated_at` 只在顯示)。

## Baseline

pytest 全套結果見 verification.md(開工時跑)。
