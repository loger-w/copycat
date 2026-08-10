# change-spec:訂閱失敗零重試三處復原路徑(mod/subscribe-retry-recovery)

分流判定:user 帶已成形改法(next-time 查證註記逐處指定形狀與約束)→ grilling 縮成確認,
無 counter-proposal — 三處分開處理、勿硬抽共用 helper 的判斷與 Phase 1 現況一致,採納。

## 成功條件(可驗收)

- SC-1(corr):腿訂閱失敗後由背景重試至成功(測試 `resub_interval_secs=0.01`,
  `_wait_until` ≤ 2s 內觀察到成功);成功後該腿推播可正常進 `_books`(quote → mid 有值)。
  全成功時不留 retry task(`asyncio.all_tasks()` 數量不變)。`close()` 後重試停止。
- SC-2(stock watchlist):失敗檔在下一輪重試成功 → 真訂(source.subscribed 出現該檔)+
  種子推播(`watchlist_quote` 訊息可觀察);該檔已被移出 watchlist → 不再重試;
  同名單重送先修復後,重試輪不重複真訂(`subscribed.count(code) == 1`)。
- SC-3(stkfut):失敗後重試成功 → `F:<prod>` 掛上 owner `stkfut:<code>`;重試前
  `_main` 已切走 → 不掛腿、`_refs` 無 `stkfut:<舊碼>` 殘留。
- SC-4(零擾動):三處訂閱全成功路徑,subscribe 呼叫序列與現況完全一致(每檔恰一次)。
- SC-5(gate):pytest/ruff/pyright/validate 全綠;既有 1651 測試零紅。

## 不能破壞的既有行為白名單

1. corr:base 腿(`source == futures_engine`)**永不** `subscribe_raw`
   (test_does_not_subscribe_base_leg_symbol)。
2. corr:單腿失敗不殺引擎、其餘腿照訂(test_single_leg_subscribe_failure_does_not_kill_engine
   斷言 `src.subscribed == ["TC.F.TWF.SXF.HOT"]` — 重試 task 起動後**首輪內**不得多訂;
   該測試在 close 前無 sleep,預設 10s 間隔天然不觸發)。
3. corr:close() 收尾順序(先斷 _loop → cancel tasks → source.close);close 後 source 不再被呼叫。
4. stock:`_acquire` 真訂失敗回滾語意不變(test_subscribe_failure_rolls_back_refs)。
5. stock:refcount 池語意(test_two_owners_one_real_subscribe);set_watchlist 的
   added/removed 判準、名單先指派再訂閱的順序、seed 推播、signal_hub on_watchlist 呼叫點。
6. stock:兩段式 rollover、backfill guard、close() 經 `_tasks` 快照 cancel+gather 全收
   (tests/server/test_stock_engine.py:577 附近的 task 收尾測試)。
7. futures_engine 完全不動(參照樣板,非本輪 scope)。
8. 對外 API / WS 訊息形狀零改動(全部是引擎內部背景行為)。

## Backward compat / migration

無 wire 契約、無持久化格式改動。新建構子參數 `resub_interval_secs` 帶預設值,
既有建構點(app.py、測試)不需改。無 migration。

## Out of scope

- futures_engine 的任何改動(已有 pending-resub)。
- index_engine `_schedule_retry` backoff 的收斂統一。
- 「lifespan 阻塞」root 條件(next-time 另條)。
- 訂閱失敗的前端可視化(status 訊息)。
- [amendment 2026-08-04: review P2-4]`set_main` 主圖真訂失敗(`ConnectionError` 不 catch,
  例外穿出到 route → caller/UI 收到錯誤自行重試)不在本輪涵蓋 — 該路徑有顯式錯誤訊號,
  與「靜默失效」的三處本質不同。

## Known Risks

1. [amendment 2026-08-04: review P1-2 裁決]cancel 一個 awaiting `to_thread` 的 task 時
   asyncio 側立即回(executor future 無法中斷),orphan thread 可能跨過 `source.close()`
   再呼叫 subscribe → TC4 重連 session 洩漏。此暴露與**已出貨的 futures `_resub_loop` 同款
   且該輪已顯式接受**(test_close_stops_retry_loop 註解「至多一個 in-flight thread」);
   本輪以 `_retry_acquire` 開頭的 `_loop is None` 檢查縮窗(corr 側每輪重讀 `self._source`
   同款),不加 close 等待機制 — 視窗僅在「close 恰逢重試 in-flight」,且發生於關機路徑,
   最壞為 log warning + process 退出前的 session 殘留。

---

# Diff 級 spec(Phase 3)

## 🟢 copycat/server/corr_engine.py(照抄 futures 形狀)

- ctor 加 `resub_interval_secs: float = 10.0`;新欄位 `_pending_subs: set[str]`、
  `_resub_task: asyncio.Task | None`。
- `_subscribe_all`:except 分支改為 `self._pending_subs.add(leg.symbol)` + warning
  (字串沿用「corr subscribe %s(%s)失敗」,語尾「該腿停用」改「進重試佇列」—
  無測試斷言此字串)。start() await to_thread 期間無並發,寫入安全(同 futures 註解)。
- `start()`:`await asyncio.to_thread(self._subscribe_all)` 後,
  `if self._pending_subs: self._resub_task = loop.create_task(self._resub_loop())`。
- 新 `_resub_loop()`:`while self._pending_subs: sleep(interval)`;每輪重讀 `self._source`
  (close 中變 None → return);逐 symbol `to_thread(subscribe_raw)`,失敗 warning 留隊,
  成功 discard + info「corr %s subscribe retry ok」;**該輪有任一成功 → 呼叫
  `self._schedule_backfill()` 一次**(補回失敗窗內漏掉的江波圖分鐘;single-flight 已有 guard)。
  symbol → leg.key 的 log 對映:迭代 `self._config.tc4_legs()` 過濾 pending。
  [amendment 2026-08-04: review P2-3 — 首輪與重試輪**共用同一 format string**
  「corr subscribe %s(%s)失敗,進重試佇列」(單一 grep 判準,futures 慣例);
  成功 `logger.info("corr %s subscribe retry ok", key)`]
  [amendment 2026-08-04: review P2-1 — `_schedule_backfill` 在 inflight 時是**丟棄**不是
  排隊(corr_engine.py:298-302),重試成功撞上 start() 回補未完時補分鐘動作被靜默吃掉 —
  本輪定調 **best-effort**:被 inflight 擋下時 log info 一行留痕;`_backfill_task` 覆寫
  孤兒問題為既有 next-time 條目(docs/next-time.md「_schedule_backfill 覆寫 _backfill_task
  參照」),不在本輪擴]
- `close()`:在 cancel `_task`/`_backfill_task` 的既有迴圈**之前**,先 cancel + await
  `_resub_task`(同 futures「重試迴圈先收掉」理由);實作上直接把 `_resub_task` 加進
  既有 `for task in (tick_task, backfill_task)` 收尾迴圈即可(該迴圈已 cancel+await+吞
  CancelledError,語意相同;順序放最前)。

## 🟢 copycat/server/stock_engine.py(單一對帳式重試迴圈,涵蓋 (b)+(c))

[amendment 2026-08-04: review P0-1 — 原設計「整輪一鎖」在 TC4 斷線時(tc4.py `_REQ_TIMEOUT_MS`
= 10s,單檔最壞 ~20s × N 檔)會讓 `_pool_lock` 佔用率趨近 100%,set_main / PUT watchlist
卡死 — 改為「快照判準短鎖 + 逐檔重拿鎖重驗 + 首個 ConnectionError 段級早停」
(早停粒度由 round 級改段級,見下方 P1-3 amendment)]
[amendment 2026-08-04: review P1-1 — 對帳判準只看 `_refs` owner 接不到 rollover
`_resubscribe_all` 的失敗(該路失敗不動 `_refs`)— 加 `_failed_resubs: set[str]` 納入重試]

- ctor 加 `resub_interval_secs: float = 10.0`;新欄位 `self._failed_resubs: set[str] = set()`。
- `_resubscribe_all` 的 `_do`:失敗 code 收集回傳(list),await 後在 loop context
  `self._failed_resubs |= set(failed)`(loop 內無 await 的同步合併,無競態;不在 `_do`
  thread 內直寫)。[amendment 2026-08-04: review P2-5a — `_do` **只收集 `ConnectionError`**,
  其他例外照舊往外拋(test_close_completes_even_if_a_task_died_with_exception 的行為契約,
  白名單 6)]
- `start()`:`self._tasks.append(asyncio.create_task(self._retry_subscribe_loop()))`
  (常駐迴圈,與 `_flush_watchlist_loop` 同款;close() 既有 cancel+gather 自然涵蓋)。
- 新 `async def _retry_subscribe_loop()`:每輪 `sleep(resub_interval_secs)` 後呼叫
  `await self._retry_round()`,round 整包 try/except Exception + logger.exception 續行
  (同 corr `_run` 的既有 rationale:迴圈死掉 = 復原路徑靜默失效)。
- `_retry_round()` 四段(1 = 快照,2-4 = 重試),**每段逐項短鎖**。
  [amendment 2026-08-04: review P1-3 — 早停從 round 級 `return` 改為**段級 `break`**:
  段 2/3 各自 break 出自己的迴圈後繼續下一段、段 4 照跑。理由:`tc4._resub` 對單一
  symbol 可穩定 raise ConnectionError(SUBQUOTE Success != OK,與連線健康無關),
  round 級早停會讓一檔壞碼永久餓死 failed_resubs 與 stkfut 兩段;段級 break 的持鎖
  上界 = 每輪至多 3 次失敗 subscribe,仍與 N 檔無關]
  [amendment 2026-08-04: review P2-6b — 關機早退不得用 `ConnectionError("engine closing")`
  (會被 except 接住打出與 TC4 訂閱失敗同字串的 warning,汙染 grep 判準):模組層自訂
  `class _EngineClosing(Exception)`,`_retry_acquire` 與段 3 wrapper 開頭
  `if self._loop is None: raise _EngineClosing` — `_retry_round` catch 它後**靜默 return
  結束該輪**,不打 warning]
  1. **快照**(短鎖):`async with self._pool_lock:` 取
     `pending_wl = [c for c in self._watchlist if "watchlist" not in self._refs.get(c, set())]`、
     `self._failed_resubs &= set(self._refs)`(prune:已退訂的不再重試)後取
     `pending_resubs = sorted(self._failed_resubs)`、`main = self._main` + stkfut 判準
     (entry 存在且 owner `stkfut:<main>` 不在 `_refs.get(f"F:{prod}")`)。
  2. **watchlist 重試**:逐檔 `async with self._pool_lock:` **鎖內重驗判準**(快照後
     user 可能已移除該檔 / 重送名單已修復)→ `await asyncio.to_thread(self._retry_acquire,
     code, "watchlist")`;成功 → `self._publish(self._quote_payload(code))`(對齊
     set_watchlist added 種子);`ConnectionError` → warning「watchlist subscribe %s failed」
    (與首輪**同 format string** — 單一 grep 判準)+ **break 出本段**(續跑段 3/4;P1-3)。
     不重呼 `signal_hub.on_watchlist`(membership 在 set_watchlist 已全量設定)。
  3. **failed_resubs 重試**:逐檔短鎖重驗 `code in self._refs and code in
     self._failed_resubs`(P2-5c — 後者防同輪內新 rollover 失敗被成功 discard 抹掉)→
     `to_thread` 走帶 closing 檢查的 wrapper 呼叫 `self._source.subscribe_symbol(code)`
     (P2-5b — 縮窗涵蓋全部呼叫點;owner 已在,只需重掛 SUB;UNSUB→SUB 冪等)
     → 成功 discard,`ConnectionError` → warning「rollover resubscribe %s failed」
     (與 `_resubscribe_all` 同字串)+ break 出本段(續跑段 4)。
  4. **stkfut 重試**:短鎖重驗 `self._main` 仍 == main 且 owner 仍缺(鎖內重讀 →「驗
     _main 仍同檔」成立)→ `to_thread(self._retry_acquire, f"F:{prod}", f"stkfut:{main}")`,
     except ConnectionError → warning(同 `_acquire_stkfut` 字串)。
- 新 `def _retry_acquire(self, code, owner)`(thread 內跑):`if self._loop is None:
  raise _EngineClosing` 後呼叫既有 `self._acquire` — close 期間的 orphan thread 早退,
  縮小「close 後 source 再被呼叫」的窗(見 Known Risks 1)。`_EngineClosing` 由
  `_retry_round` catch 後靜默結束該輪(P2-6b:不得偽裝成 TC4 訂閱失敗 warning)。
- per-code 只 catch `ConnectionError`(預期路徑);非預期例外升級到 per-round catch。

## 既有測試標記

- 該紅的:**無**(全部是 additive 背景行為;白名單 2 的 corr 測試靠預設 10s 間隔不觸發,
  不需改)。
- 不該紅的:全部 1651。
- 風險點(已查證解除):stock 測試 `test_close_cancels_pending_resubscribe_task`
  (:575-581)用 **相對計數** `len(engine._tasks) == n_before + 1` 且 `n_before` 在
  start() 之後取 → 常駐 retry loop 多一項不影響;`_tasks[-1]` 取的是 rollover 剛 append
  的 task,retry loop 在 start() 時就已入列,不佔 `[-1]`。

## 新測試清單

[amendment 2026-08-04: review P2-2 — 補全成功零重訂實鎖、修 corr 測試 3 斷言寫法、
否定斷言明訂等待輪數]

- tests/server/test_corr_engine.py::TestPendingResubscribe(仿 futures 樣板):
  1. flaky source(前 N 次 fail)→ 重試至成功,attempts 計數正確、成功品不重訂(SC-1、SC-4)。
  2. 重試成功後 quote 進得來(mid 有值)(SC-1)。
  3. 全成功 → `eng._resub_task is None`(SC-4;不用 `asyncio.all_tasks()` 數量 —
     start() 本就建 `_task`/`_backfill_task`)。
  4. close() 停止重試(等 ≥5 倍 interval 後 attempts 至多 +1 — in-flight 容忍與 futures 同)(SC-1)。
  5. base 腿永不因重試被訂(白名單 1;pending 只收 tc4_legs):任一 **tc4 腿**失敗並
     重試 ≥5 輪後,base 的 symbol 仍不得出現在 `src.subscribed`
     [amendment 2026-08-04: review P2-6a — base 腿本就不進 `_subscribe_all` 迭代,
     「失敗腿含 base」場景不可構造,措辭修正]。
- tests/server/test_stock_engine.py::TestWatchlistRetry:
  1. fail_subscribe → 下輪重試成功 → subscribed 出現 + watchlist_quote 種子推出(SC-2)。
  2. 失敗後 user set_watchlist([]) 移除 → 等 ≥5 倍 interval,subscribe 不再被呼叫(SC-2)。
  3. 失敗後同名單重送修復 → 再等 ≥5 輪,`subscribed.count(code) == 1`(SC-2 + 白名單 4)。
  4. **全成功 + 小 interval 跑 ≥5 輪 → watchlist 各檔與 stkfut 腿 `subscribed.count == 1`**
     (SC-4 stock 側實鎖:判準寫錯最典型的失效 =「每輪重複真訂」)。
  5. rollover `_resubscribe_all` 失敗檔進 `_failed_resubs` → 重試成功後 discard;
     該檔已退訂(不在 `_refs`)→ prune 不重掛(P1-1)。
- tests/server/test_stock_engine.py::TestStkfutRetry:
  1. stkfut 腿 fail → 重試成功掛 owner(SC-3)。
  2. fail 後切走 main(map 無 entry 的檔)→ 等 ≥5 輪,不掛、`_refs` 無 `stkfut:<舊碼>`(SC-3)。
- TC4 斷線鎖飢餓回歸(P0-1):pending 多檔 + subscribe 全 fail(每次呼叫 sleep 模擬慢)
  → `set_main` 在單檔量級 timeout 內完成(不被整輪持鎖卡住)。
- 段級 break 反餓死回歸(P1-3):段 2 有一檔恆失敗(fail_subscribe 常駐)時,
  stkfut 腿與 `_failed_resubs` 檔仍在 ≥5 輪內完成重試。

## Commit 計畫(三類分離)

- 🟢 test+impl corr resub(TDD:紅 → 綠)
- 🟢 test+impl stock retry loop(TDD:紅 → 綠)
- (無 🔴 / 🔵)[amendment 2026-08-04: review P2-4 — 常駐 retry loop 歸 🟢 的理由:
  對外 API / 訊息形狀零改動、訂閱全成功路徑 subscribe 序列與現況完全一致(SC-4 有測試鎖),
  新增的只是背景復原能力;無既有測試該紅 → 非 🔴]

self_review_head: 382d2a54bad06cc9dcd3bd3b35f82dcb718a48f4
