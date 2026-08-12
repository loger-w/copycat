# XR-3 現況調查:SignalHub ↔ stock engine 耦合

日期:2026-08-12。來源:docs/next-time.md 2026-08-06 節 XR-3;R4 round-2 復審遺留。
前置檢查:fix/tc4-lock-p2s(PR #41)已 rebase-merge 進 master(2026-08-11),
signal_hub / stock_engine 測試以 merge 後版本為基準。

## 1. 四處耦合明細(app.py `_make_signals`,line 484-504)

| # | 綁定 | 供應者 | hub 內用途 | 無 engine 時的必要性 |
|---|------|--------|-----------|---------------------|
| C1 | `publish=engine._publish` | StockEngine 私有 `_ws`(WsBroadcaster,engine 建構子自持,line 185) | `_emit` WS 同步送出;`publish_market_events` WS 後送 | **必要**(廣度事件要進前端時間軸);且 `/ws/stock`(app.py 1468)在 engine None 時直接 close,整條 WS 通道死 |
| C2 | `daily_bars=engine.daily_bars` | StockEngine → TC4 REQ 日 K | `_resolve_basis` 抓 CDP 基準 | **不必要**(CDP 只服務 tick 驅動的 cdp_cross 規則;無 TC4 = 無 tick = 無評估) |
| C3 | `trade_date_fn=lambda: engine.trade_date` | StockEngine `_trade_date`(兩段式 rollover stage2 才前進) | `_emit` 事件日別、`today_signals` 讀取集、`_stale`/`_distribute`/`_seed_slot` 日別尺、`on_rollover` expected、`publish_market_events` 日別不符 warning | **必要**(today_signals 讀取集、market 事件 warning 比對) |
| C4 | `quotes_fn=engine.quotes` | StockEngine 現值快照 | Discord 同群摘要(裝飾) | 不必要(hub 已容忍 None → 摘要空字串) |

註:`groups_fn` 讀自選檔(`load_watchlist`),與 engine 無關,不在耦合清單。

## 2. 結構性耦合(同根,不在建構子參數)

- **S1 建構 gate**:`_make_signals` 對 `stock is None` 早退回 None(line 485-486)
  → TC4 沒開 = hub 不存在。這是整條失效鏈的根。
- **S2 route gate**:`_signals`(line 939-946)先 `_stock(request)` 再查 hub
  → stock None 時所有 signals route(today / rules CRUD)503,**先於** hub 判定。
- **S3 啟動接線**:`_start_signals` 內 `create_bot(service, hub)` + `stock.attach_signal_hub(hub)`
  (CC-2:attach 必須是最後一行);`service` = WatchlistService,stock None 時為 None
  (bot 各 handler 已容忍 service None,回 fallback 文案 — discord_bot.py 216 起)。
- **S4 breadth 接線**:`breadth.attach_signal_hub(signals)` 只在
  `breadth is not None and signals is not None`(line 732-733);hub None →
  `_diff_limit_events` 對 hub None 早退(breadth_engine.py 725-728),
  全市場鎖板**狀態機不推進、事件不產生、jsonl 無紀錄**。
- **S5 關機順序**:反序 close = breadth(先 detach)→ signals(`_close_signals`:
  bot → detach stock → hub.close)→ … → stock。hub 晚於 breadth、早於 stock 收,
  兩端的 use-after-close 窗都靠這個順序封住。

## 3. TC4 down 的完整失效鏈(現況)

stock=None ⇒ signals=None ⇒
(a) breadth 鎖板事件鏈整條靜默消失(S4);
(b) `/api/stock/signals/today` 503(S2)— FE-1 只把 503 顯示成「訊號服務未就緒」;
(c) `/ws/stock` 立即 close(C1)— 前端時間軸無即時流;
(d) 規則 CRUD 503(S2)— 規則其實是純檔案操作,與 TC4 無關;
(e) Discord bot 不建(`app.state.discord_bot = None`)— 廣度事件本來就硬性不進
    Discord,但 bot 的 `/watch` 也一併消失(service 亦 None,屬 stock 依賴,合理)。

R4 已做的單向隔離(反向的既有保護,白名單候選):
- `publish_market_events` 的 `trade_date` 由 breadth 傳入(R7),不綁 engine 日別;
- FinMind 掛 → TC4 系零波及。

## 4. SignalHub 全 caller map(含動態)

| Caller | 方法 / 屬性 | 位置 |
|--------|------------|------|
| app.py 建構 | `SignalHub(...)` | `_make_signals` 488 |
| app.py 啟動 | `start` / `on_watchlist`(種子)/ `attach_discord` | `_start_signals` 506-519 |
| app.py 收攤 | `close` | `_close_signals` 521-530 |
| app.py routes | `today_signals` / `rules` / `upsert_rule` / `delete_rule` | 1037-1080 |
| app.py state | `app.state.signal_hub`(動態屬性) | 379 / 539 / 943 |
| StockEngine(SignalSink Protocol) | `on_watchlist` 372 / `on_rollover_pending` 565 / `on_rollover` 724 / `on_tick` 909 / `on_book` 923;掛點 `attach_signal_hub`/`detach_signal_hub`/`_signal_hub` 208-225 | stock_engine.py |
| BreadthEngine(MarketSignalSink Protocol) | `market_event_state` 731 / `publish_market_events` 799;掛點 attach/detach 312-317 | breadth_engine.py |
| discord_bot.Bot | 只存不讀(`self._hub`,成對生命週期用) | discord_bot.py 470 |
| 測試(動態) | `app.state.signal_hub`、`app.state.stock._signal_hub`、monkeypatch `SignalHub.start` | tests/server/test_signal_routes.py 等 7 檔 |

grep 佐證:`_make_signals|SignalHub|signal_hub` 命中僅 copycat/{signals_config,server/{stock_engine,signal_hub,breadth_engine,app},live/signal_state}.py + tests 7 檔;無其他動態用法。

## 5. 現況 vs 目標

| 面向 | 現況 | 目標 |
|------|------|------|
| hub 存在性 | stock None → hub None | TC4 不在時 hub 照建照啟(壞規則檔 → hub None 的既有降級**不變**) |
| WS bus | engine 自持 `_ws`,hub 借道 | 待拍板(候選:app 層共用 WsBroadcaster,先例 = capital_ws/futures_ws/corr_ws/river_ws) |
| trade_date | engine 單一權威 | 待拍板(engine 在 → engine;不在 → 替代來源) |
| daily_bars | engine 直供 | 待拍板(無 engine 時 stub 語意:資料面空 vs 例外) |
| quotes | engine 直供 | 無 engine → None(hub 既有容忍) |
| route gate | 先 `_stock` 再 hub | 待拍板(gate 掉 stock 依賴的範圍) |
| breadth attach | 需 signals 非 None | hub 獨立後自然恆掛(breadth 亦非 None 時) |

## 6. 既有測試盤點(該紅 / 不該紅)

- **該紅**:`test_signal_routes.py::TestSignalRoutesNotReady::test_all_signal_routes_return_503`
  (with_stock=False → 全 503)— 新行為下 hub 應獨立存活,此測試是行為預告的主錨點。
- **不該紅**:
  - `test_hub_start_failure_isolates_signals_only`(hub 自身 start 炸 → 503):
    hub 單獨降級語意不變;
  - `test_bad_rules_file_degrades`(壞規則檔 → hub None → 503):R9 大聲降級不變;
  - `test_shutdown_detaches_hub_from_engine`(CC-2 摘掛點):stock 在場時行為不變;
  - `test_signal_hub.py` 全部(hub 內部行為,建構子注入 fake,不動語意就不紅);
  - `test_breadth_engine.py` / `test_breadth_routes.py`(hub 是注入的 fake sink);
  - `test_stock_engine.py`(SignalSink protocol 不動)。
- 邊界未定(依拍板結果):`/ws/stock` 相關測試(test_stock_routes.py)、
  `helpers/boot.py`(BootedClient 是否假設 signals 依賴 stock)。

## 7. 既有行為白名單(初稿,change-spec 收斂)

1. TC4 在場時:訊號鏈全行為逐字不變(tick 評估、CDP 基準、rollover 兩段式、
   Discord 節流、同群摘要、jsonl 決定性 id)。
2. 壞規則檔 → hub None + 四條 rules route 503(R9 大聲降級)。
3. hub start 失敗 → 訊號單獨停用,其他引擎照常(TQ-7 隔離)。
4. CC-2:attach 必須在 `_start_signals` 尾;關機先 detach 再 close(S5 順序)。
5. `publish_market_events` 的 R7 語意:以傳入 trade_date 落檔,日別不符每日別 warn 一次。
6. today_signals 讀取集 = {engine 日別, 牆鐘日} 的雙日聯集語意(R2-3)。
7. 同內容 PUT watchlist no-op、`/api/stock/names` 不過 stock 閘等鄰近 route 行為不動。
