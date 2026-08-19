# 現況(/mod futures-broadcast-coalesce-leaf-unsub)— 2026-08-19

來源:handoff `docs/superpowers/specs/2026-08-19-browser-crash-scan-handoff.md` R2。

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| `FuturesEngine._handle_quote`(`futures_engine.py:381-435`) | 每則 REALTIME quote 更新 state 後**無條件** `_seq += 1` + `_broadcast({type,seq,product,state})`(含五檔全量);全檔無 throttle;對照 index/stock/corr 引擎皆有 1s 閘 | quote 只更新 state + 標該 product dirty;以 `flush_interval_secs`(prod 0.1 s)週期 flush:每個 dirty product 各推**一則最新 payload**,`_seq` 在 flush 時才遞增(每則 WS 訊息 +1,維持前端 seq 連續契約) |
| `state()["seq"]`(`:245-249`) | = 每 quote 遞增的 `_seq` | = 最後一則已廣播的 seq(flush 時遞增);GET 全量永遠是最新內容、seq ≤ 下一則 WS seq−1 |
| leaf fallback(`:299-351`) | `_leaf_fallback` → `subscribe_leaf` 只訂不退;`_leaf_done` 永久、`_leaf_fed.discard`(:406,HOT 成交回來)只是記帳;HOT 與 leaf(`futures_models.product_from_symbol` 解析同 product)雙流各推一次;tc4 重連 `_subscribed` 全量重訂把 leaf 復原 | HOT 真的推成交回來(現有 `_leaf_fed.discard` 判準點)→ 對該 product 所有 `_leaf_done` 的 (product, ym) 呼叫新 `source.unsubscribe_leaf(product, ym)`(to_thread,失敗 warning 不炸、下次 HOT 成交再試),成功後 `_leaf_done.discard` → tc4 `_unsub` 同時移出 `_subscribed`,重連不再復原 |
| `FuturesSource` Protocol(`:36-49`) | 無 `unsubscribe_leaf` | 新增 `unsubscribe_leaf(product, ym) -> None` |
| `FuturesQuoteSource`(`live/futures_source.py:87-95`) | `subscribe_leaf` 走 `_resub(f"TC.F.TWF.{p}.{ym}")` | 新增 `unsubscribe_leaf` 走 `_unsub(...)`(已訂才退、清自癒帳) |
| 自癒閘(`app.py:351-359` `_default_futures_source`) | `heal_active=_heal_gate(calendar, always_active)` → 交易日整天閘開,13:45–15:00 / 05:00–08:45 盤外持續 UNSUB/SUB churn | `heal_active=_heal_gate(calendar, in_futures_session_now)`:日盤 08:40–13:50、夜盤 14:55–24:00 與 00:00–05:05(寬 5 分)|
| 換月(`:407-420`) | 跨日把 leaf-fed 商品 p 清 None 重武裝;「舊月 leaf 不退訂」註解明寫 | 不動(到期契約零推播;本輪只退「HOT 已回」的 leaf) |

## Caller map(含動態用法)

- `_broadcast`:建構子注入;prod `app.py:803` `FuturesEngine(lambda: fut_src, broadcast=futures_ws.publish)`(`WsBroadcaster.publish`,loop 上同步);測試 `events.append`。
- `/ws/futures`(`capital_api.py:346-355`)relay `broadcaster.stream()`;前端 `useFuturesStream.ts` **依賴 seq 連續**(`msg.seq !== prev.seq+1` → REST refetch 全量)與每則帶該 product 全量 state(last-write-wins)→ seq 必須每則 WS 訊息 +1、`/api/futures/state` seq 同源。
- `state()`:`capital_api.py:343`(GET)、`corr_engine._futures_leg_book`(pull 讀 bids/asks/p,不經推播)— 不受 flush 時序影響(state 即時更新)。
- `resolved_contract` / `bars_range` / `fetch_day_1k`:不動。
- `subscribe_leaf` 實作者:`live/futures_source.py:87`、測試 `tests/server/test_futures_engine.py::FakeSource`、`tests/helpers/fake_sources.py::FakeFuturesSource`(需同步加 `unsubscribe_leaf`);corr_engine 不用 futures source 的 leaf。
- `always_active`:`live/tc4.py`;`app.py:353,358`;其他 source 各自的 clock gate(stock `in_trading_hours_now`)。
- 動態用法:`bars_range` 以 getattr 取 `fetch_bars_range`(不動);無其他反射。

## Backward compat / migration

- WS 訊息 shape 不變;seq 語意由「每 quote」變「每則廣播」,前端契約(連續 +1)仍成立;GET state seq 與 WS 同源。
- `FuturesSource` Protocol 加方法 = 所有 fake 要補(測試 3 處);prod 實作 1 處。無資料格式 / migration。

## Baseline
`pytest tests/server/test_futures_engine.py tests/live/test_futures_source.py tests/server/test_capital_api.py tests/server/test_corr_engine.py` → 140 passed(改動前)。
