# current-state:訂閱失敗零重試三處(2026-08-04)

Baseline:`pytest -q` → **1651 passed**(75.6s),working tree 乾淨,分支 `mod/subscribe-retry-recovery`。

## 三處現況

### (a) corr_engine._subscribe_all(copycat/server/corr_engine.py:123-130)

- `start()` → `to_thread(_subscribe_all)`:逐腿(僅 `source == tc4` 的腿)`subscribe_raw`,
  `ConnectionError` 只 log「該腿停用」。
- `_on_reconnect_threadsafe`(:293-296)→ `_schedule_backfill` 只重跑江波圖回補,**不重訂閱**。
- → 失敗腿整天無相關係數 + 無江波圖 live 點,無自癒路徑。
- 同構參照:`futures_engine.py:121-167` 的 `_pending_subs` + `_resub_loop`:
  - `_subscribe_all` 失敗品進 `_pending_subs`(start() await 期間無並發,寫入安全)
  - start() 末:`if self._pending_subs: create_task(_resub_loop())`
  - `_resub_loop`:`while self._pending_subs: sleep(interval); to_thread(subscribe)`,
    成功出列 + info log,失敗留隊(warning 字串與首輪一致 = 單一 grep 判準)
  - `close()` 先 cancel resub task 再關 source(否則 close 後 subscribe → 重連 TC4)
- corr 的差異:訂的是 `leg.symbol`(字串),失敗單位是「腿」;無鎖、集合一次性(config 固定),
  可照抄 futures 形狀。close() 現況已 cancel `_task`/`_backfill_task`(:141-157),resub task 加入同款收尾。

### (b) stock_engine watchlist subscribe(copycat/server/stock_engine.py:199-203)

- `set_watchlist`(:188-214,持 `_pool_lock`):added 逐檔 `to_thread(_acquire, code, "watchlist")`,
  `ConnectionError` 只 warning。
- `_acquire`(:159-172):真訂失敗**回滾** — `_refs.pop(code)` 後 raise。
- 後果鏈:失敗檔不在 `_refs` → rollover 的 `_resubscribe_all`(:292-304,迭代 `_refs`)接不到、
  `_flush_watchlist_loop` 無 state 可推 → 該檔畫面永遠 `-`,直到下次 set_watchlist(且 added
  判準是 `"watchlist" not in _refs.get(c)`,同名單重送可重試 — 這是現況唯一的手動復原路)。
- 約束(與 futures 不同,勿硬抽 helper):
  - 重試 task 必須進 `self._tasks`(close() 唯一取消點;:98-101 註解)
  - 必須拿 `_pool_lock`(否則與 set_watchlist / set_main / _resubscribe_all 打架;CR2)
  - 項目是**動態集合**:每輪重試前對帳「code 仍在 `_watchlist` 且 `"watchlist"` owner 不在
    `_refs.get(code)`」(使用者可能已移除該檔、或已由重送名單修復)
- 現有測試:`test_subscribe_failure_rolls_back_refs`(tests/server/test_stock_engine.py:136-144)
  斷言回滾後重送同名單會真訂 — 新重試機制不得破壞(重試成功後再重送不得重複真訂)。

### (c) stkfut 腿(copycat/server/stock_engine.py:260-268)

- `_acquire_stkfut` 只在 `set_main`(:226)呼叫;失敗只 warning。
- `set_main` 開頭 `old == code → return`(:219-220)→ 同檔重掛被擋,唯一復原 = 切走再切回。
- 重試約束:每輪重試前驗 `self._main` 仍是同一檔(否則替已不看的股票掛腿 + owner
  `stkfut:<code>` refcount 洩漏);同樣需 `_pool_lock` + 進 `_tasks`。
- 註:`_release_stkfut` 在 set_main 切走時呼叫(:225),重試中途切主圖 → 對帳判準自然失效停止。

## Caller map(grep 完整,含動態用法查無)

- `CorrelationEngine`:唯一建構點 `app.py:427`(`_make_corr`);`_subscribe_all` 僅 `start()` 內部;
  `close()` 僅 lifespan 關機鏈(app.py:462-466)。無其他 caller、無動態用法。
- `StockEngine.set_watchlist`:`app.py:268`(啟動還原 persisted)、`watchlist_service.py:101`
  (PUT/bot 共用)。`set_main`:app.py routes。`_acquire`/`_release`/`_acquire_stkfut`/
  `_release_stkfut`:皆 engine 內部,無外部 caller。
- `_resubscribe_all`:僅 `rollover_stage1`(:286)。
- 測試 fake:`tests/server/test_corr_engine.py::_FakeSource`(subscribe_raw 有 fail_on)、
  `tests/server/test_stock_engine.py::FakeSource`(fail_subscribe set,可動態增減 → 適合寫
  flaky 重試測試)、`tests/server/test_futures_engine.py::_FlakySource` + `_wait_until`(樣板)。

## 現有實作意圖

- corr `_subscribe_all` docstring 自稱「沿用 futures_engine 慣例」= 當時 futures 也只降級;
  futures 已在 fix/startup-names-futures-resub 補了 pending-resub,corr 未跟上。
- stock `_acquire` 回滾是 design §2.4 刻意行為(不留空 owner set)— 重試機制不改回滾語意,
  只在回滾後補一條背景重試路。
- next-time 條目(docs/next-time.md:512-523)明示:勿硬泛化,三處分別處理。

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| corr 腿訂閱失敗 | log 後該腿永久停用 | pending + 背景重試至成功(futures 形狀) |
| stock watchlist 檔訂閱失敗 | 回滾出 _refs,等下次 set_watchlist | 背景重試(對帳 _watchlist/_refs),成功後補種子推播 |
| stkfut 腿訂閱失敗 | 等切走再切回 | 背景重試(驗 _main 同檔) |
| 對 caller 影響 | — | 零:全部是引擎內部背景行為,對外 API/訊息形狀不變 |
| backward compat | — | 訂閱全成功路徑行為完全不變(不起 task 或 task 立即結束) |
