# Implementation PLAN:stock-signals(condensed)

對應 design.md v3。實作順序 = 下列編號(依依賴序;TDD 紅先行,每節列對應 SC 紅測試)。
測試檔慣例:後端 `tests/...`,前端 co-located `X.test.tsx`;純邏輯抽 lib 單測。

## 後端

### 1. `copycat/market.py`(修改,共用 util — 高風險面,完整 signature)

```python
def tick_size_milli(price_milli: int) -> int:
    """毫元版 tick(R4):tick_size_milli(23_450) == 50(23.45 元 → 0.05 元檔)、
    tick_size_milli(123_450) == 500(123.45 元 → 0.5 元檔)。"""
    return _tick_milli(price_milli)
```
- 紅測試(`tests/test_market.py` 追加):`tick_size_milli(9_990)==10`、`(23_450)==50`、
  `(123_450)==500`、`(1_500_000)==5_000`,與 `tick_size(price/1000)*1000` 一致性
  property 抽 3 點。(impl-review R1:123.45 元落 100–500 元段 = 0.5 元檔。)

### 2. `copycat/signals_config.py`(新增)

- frozen dataclass `SignalsConfig`:`cdp_rearm_ticks=5`、`cdp_cooldown_secs=600`、
  `surge_pct=2.0`、`surge_window_secs=300`、`surge_cooldown_secs=1800`、
  `vol_ratio=3.0`、`vol_min_elapsed_min=15`、`vol_min_window_lots=100`、
  `vol_min_day_lots=500`、`vol_cooldown_secs=1800`、`limit_cooldown_secs=600`、
  `discord_per_min=30`、`basis_gap_secs=0.2`。
- `load_signals_config(path: Path = CONFIG_PATH) -> SignalsConfig`:仿
  `strategy_config.py` 的 configs/signals.json 逐鍵覆寫 + 未知鍵報錯。
- 紅測試(`tests/test_signals_config.py`):預設值、JSON 覆寫、未知鍵 raise。

### 3. `copycat/live/signal_state.py`(新增 — 核心狀態機,高風險面)

- 依 design §3 全文:`SignalEvent`(含 `time_key`)、`TickContext`(含對稱欄位)、
  `SignalDetector(cfg, *, now_fn)`。公開:`set_basis / clear_all_basis / stage_basis /
  swap_staged_basis / evaluate / evaluate_book / reset_day / drop_code`。
  (staged basis 兩式支援 §4.2 的 stage1 預抓;`swap_staged_basis` 無暫存 → 回 False
  讓 hub 走 fallback。)
- `evaluate(code, tick, ctx, enabled: frozenset[str]) -> list[SignalEvent]` 與
  `evaluate_book(code, ctx, enabled) -> list[SignalEvent]`(impl-review R13:簿路
  同樣吃 enabled — 停用 limit_lock 時簿路回空、latch 仍照常轉移):
  gate 順序 = 時窗(`now_fn`,09:00≤t<13:30,無 weekday)→ trade_date → 首 tick
  初始化;狀態推進無條件,事件產出受 `enabled` 濾。
- 紅測試(`tests/live/test_signal_state.py`,SC-1/2/3/4/6 全在此檔):
  - SC-1:from_below 穿 AH 發 1 則(levels/direction/touch_count)、橫盤不發、
    rearm 內重觸不發(真實價位不跨 tick 段邊界,impl-review R2:AH=80.00 元
    → tick 0.1 元、rearm 門檻 0.5 元;79.95 不解除、79.50 解除;註記門檻取
    當下價的 tick 段)、
    cooldown 內不發、同 tick 跨 NH+AH 合併單則(levels 固定序)、無基準跳過;
  - SC-2:300s 窗 +2.1% 發 surge、−2.1% 發 crash、+1.9% 不發、cooldown second 不發;
  - SC-3:ratio≥3 且過地板發、開盤 <15 分不發、低量股(day_volume=10)不發、
    關 surge_crash 後 vol_burst 照發(R2 分離);
  - SC-4:鎖上複合簽名發 limit_lock、首攻反例不發、成交路/簿路 limit_open、
    同日重複鎖 latch 不重發、跌停對稱、簿路 time_key=now_fn、
    **重啟語意表態測試**(impl-review R15,採 design §9:fresh detector 對已鎖停股
    首 tick 初始化不發、第二筆鎖停 tick **會**發 limit_lock = 重啟後重發一次是
    已接受代價);
  - SC-6:盤外不發不推進、舊 trade_date tick 不發不推進、首 tick 不發。

### 4. `copycat/server/signal_hub.py`(新增)

- 依 design §4:`__init__(cfg, *, publish, daily_bars, notify_fallback, data_dir,
  trade_date_fn, now_fn)`(trade_date_fn = engine 當前日別 getter;
  **無 pending_fn** — 換日 pending 由 engine 掛點位置單一保證,impl-review R9)。
  `on_tick / on_book / on_rollover_pending / on_rollover / on_watchlist /
  request_basis / enabled / set_enabled / attach_discord / start / close`。
- **CDP 基準 worker(design §4.2,impl-review R6)**:job = `(code, basis_date,
  staged)`;`await daily_bars(code, n=5)` → 取 `date < basis_date` 最後一根 →
  `compute_cdp` → `set_basis`/`stage_basis`;失敗或空 → `set_basis(code, None)`
  不 raise 不重試;每檔間隔 `basis_gap_secs`(測試注入 0);觸發點 = boot /
  `on_rollover_pending`(staged)/ `on_rollover` fallback(swap 失敗 → 清空重抓)/
  `on_watchlist` 新增(移除 → `drop_code`)。
- fanout:WS 同步 publish → 單一 asyncio.Queue(100) worker(jsonl to_thread +
  Discord;Discord 每分鐘 30 上限只擋 Discord)。**滿載策略(impl-review R14)**:
  `put_nowait` → `QueueFull` 時 `get_nowait()` 丟最舊再放入,`dropped` 計數 +
  節流 log(不 await put — 熱路徑零反壓;不 except-pass)。id 決定性鍵。
  enabled 持久化 `data/signals_enabled.json`。
- membership gate;`on_tick` 全包 try/except log。
- 紅測試(`tests/server/test_signal_hub.py`):
  - **SC-1 整合層(impl-review R7)**:餵穿越 tick → publish 收到的 dict 鍵集合
    完全等於 design §7 契約(id/kind/code/name/price/time/levels/direction/pct/
    touch_count;name 取自 state.meta、無 meta 為 ""),jsonl row 同形 +
    trade_date,notify/bot sender 各一次;
  - SC-5(live 觸發一次 → apply_backfill 重放不經 hub → 次數不變)、
    SC-7 jsonl + id 跨重啟不碰撞(新 hub 讀同檔)、enabled 關閉不產事件
    (SC-12 後端半)、非自選 code 零訊號、Discord 節流 31 則第 31 不送但 jsonl 有、
    bot sender 失敗 fallback webhook;
  - 基準 worker:staged 預抓 → swap 後 CDP 即用、fallback 清空重抓、
    daily_bars 拋錯 → basis None 且其他 kind 照常、佇列滿丟最舊 dropped=3
    (maxsize=2 放 5)。

### 5. `copycat/stock_watchlist.py`(修改)+ 6. `copycat/server/watchlist_service.py`(新增)

- 5:抽 `normalize(wl: Watchlist) -> Watchlist` 純函數(save_watchlist 內部改用,
  行為不變 — 🔵);紅測試:normalize 冪等、去重、群組成員補進 codes。
- 6:`WatchlistService(path, engine)`,`apply/add/remove` 皆持單一 asyncio.Lock;
  canonical 零寫早退(🔴 行為改動:同內容 PUT 變 no-op,回現況 canonical 形);
  變更成功 → `engine.set_watchlist` → `engine._publish({"type":"watchlist_changed"})`。
- 紅測試(`tests/server/test_watchlist_service.py`):add 入群組落檔 + set_watchlist
  被喚 + 廣播(SC-8 後端半)、remove 反向、超上限/非法碼 raise WatchlistError 不落檔、
  同內容 apply 兩次第二次零副作用且回傳 body 相同(R18/R2-10)、並發 add 序列化。

### 7. `copycat/server/discord_bot.py`(新增)

- **模組層不 import discord**(impl-review R4 — 否則 dev venv 沒裝 extras 時 SC-8
  測試整檔 skip = vacuous gate):handler 邏輯為純 async fn,吃 duck-typed
  interaction(protocol:`response.defer(thinking=True)` / `followup.send(text)`);
  `create_bot(service, hub) -> Bot | None` **函式內** lazy import discord,
  ImportError / token 未設(env → .env utf-8-sig,新語意)→ None。
  `Bot.start_bg()/close()/send_signal(text)->bool`。
- slash `/watch add|remove|list`:handler 先 `defer(thinking=True)` 再 followup
  (R17);on_ready 對 signals channel 的 guild sync;僅該 guild。
- **conftest 中和(impl-review R5,CAPITAL_* 同型事故前科)**:`tests/conftest.py`
  autouse 補 delenv `DISCORD_BOT_TOKEN` / `SIGNALS_DISCORD_CHANNEL_ID` + 中和本模組
  .env reader(仿 `_neutralize_capital_env`);需要值的測試自行 monkeypatch。
- 紅測試(`tests/server/test_discord_bot.py`)**無 extras 全跑,不 skip**:
  fake interaction 驗 add 成功文案含名稱與群組 + defer 先於 followup、
  WatchlistError 文案、service None 回未就緒、token 未設 create_bot 回 None
  (SC-8 降級)。僅「真 discord 型別接線」一小測 `skipif discord 缺席`。
  收尾證據附本檔 passed 數(非 skipped)。

### 8. `copycat/server/stock_engine.py`(修改 — hot path,高風險面)

- `attach_signal_hub(hub)`(存 `self._signal_hub = hub`);新增 `trade_date`
  存取器(property 或 `current_trade_date()`,impl-review R9 — hub 的
  `trade_date_fn` 不摸私有欄位);
  `_handle_quote` ingest 為真分支尾呼叫
  `hub.on_tick(code, tick, state)`;`_handle_quote` **尾端**(既有 main book publish
  同位置之後)呼叫 `hub.on_book(code, state)`,`self._pending_date is not None`
  (欄位名已證實)時跳過(R2-2);皆 `if hub is None` 跳過、包 try/except。
- rollover stage1 尾呼叫 `hub.on_rollover_pending(new_date)`;stage2 尾呼叫
  `hub.on_rollover()`;`set_watchlist` 尾呼叫 `hub.on_watchlist(codes)`。
- **`apply_backfill` 路徑零接觸**。
- 紅測試(`tests/server/test_stock_engine.py` 追加):SC-5(回補重放不觸發 hub —
  fake hub 計數)、**試撮 tick(is_trial)→ on_tick 0 次且 on_book 照常**
  (impl-review R8,SC-6 後半)、on_book 在 pending 期間不被喚、rollover 兩段
  呼叫順序、set_watchlist 通知 hub。

### 9. `copycat/server/app.py`(修改 — 對外 API,高風險面)

- lifespan **順序(impl-review R3)**:stock `_boot` 後**先**
  `service = WatchlistService(wl_path, stock) if stock else None` 掛
  `app.state.watchlist_service`,**再**跑 signals `_boot`(§4.5 v3;make 建 hub、
  start 做 attach + on_watchlist + create_bot(service, hub) + attach_discord;
  close 反序)— service 是 start closure 的自由變數,順序反了會 NameError 被
  _boot 吞成靜默降級。關機 finally 最前補 bot/hub close。
- 補測試:fake source 起 app → stock 就緒時 `app.state.signal_hub is not None`
  (釘住靜默降級)。
- Routes:
  - `GET /api/stock/signals/today` → `{"signals":[...]}`(hub 讀當日 jsonl,壞行跳過)
  - `GET /api/stock/signals/enabled` → `{"enabled":{...}}`;`PUT` 同形,非法鍵/值
    400 `INVALID_SIGNALS_ENABLED`
  - 三條先過 `_stock()` 閘 + hub None → 503 NOT_READY
  - `PUT /api/stock/watchlist` 改呼叫 `service.apply`(外部形狀不變)
- `pyproject.toml`:`[project.optional-dependencies] discord = ["discord.py>=2.4"]`。
- 紅測試(`tests/server/test_signal_routes.py`):today 回 jsonl 內容、enabled
  GET/PUT 往返 + 重啟保留(SC-12)、非法 PUT 400、hub None 503、PUT watchlist
  經 service(廣播可觀測)。

## 前端

### 10. `frontend/src/lib/signal-model.ts`(新增)+ 11. `frontend/src/lib/signal-bus.ts`(新增)

- 10:`SignalMsg` 型別(§7 形狀)、`kindLabel(kind, levels, direction)` 中文、
  `formatToast(sig)`、`mergeSignals(baseline, live, cap=200)`(id 去重、新在前)、
  `filterKinds(sigs, enabled)`。紅測試:合併去重排序、cap、kindLabel 全 kind
  (cdp 顯示「中軸」、多線 `AH+NH`)。
- 11:module-level EventTarget:`emitSignal/onSignal`、`emitWatchlistChanged/on...`、
  `emitWsOpen/on...`(typed CustomEvent 薄殼)。紅測試:訂閱/退訂/多訂閱者。

### 12. `frontend/src/hooks/useStockStream.ts`(修改)

- `handle` switch 加 `case "signal"`(→ `emitSignal(msg)`)與
  `case "watchlist_changed"`(→ **hook 內 `useQueryClient()` 直接
  `invalidateQueries({ queryKey: ["stock-watchlist"] })`**,單一註冊點,
  impl-review R10 — 不經 bus,免除 App/useSignalFeed 兩處註冊的矛盾);
  `ws.onopen` 內加 `emitWsOpen()`。不動既有 case。
- 紅測試(既有 **`useStockStream.test.ts`** 追加,impl-review R12 — 沿用該檔
  fake WebSocket harness,不新建 .tsx):signal 訊息轉發 bus、watchlist_changed
  → invalidate 被喚一次、onopen 發 ws-open。

### 13. `frontend/src/hooks/useSignalFeed.ts` + 14. `useSignalsConfig.ts` + 15. `useSignalAlerts.ts`(新增)

- 13:TQ query `["stock-signals-today"]` GET today + bus onSignal prepend
  (mergeSignals)+ onWsOpen → invalidate refetch(自癒)。
  (SC-11 的 watchlist invalidate 在 useStockStream 內,見第 12 節 — 此處不重複。)
- 14:TQ query `["stock-signals-enabled"]` + mutation PUT(setQueryData)。
- 15:`useSignalAlerts()` → `{toasts, dismiss}`;onSignal → push toast(上限 4 +
  overflow 計數,5s 自動移除)、`document.hidden && Notification.permission==="granted"`
  → new Notification、音效(Web Audio oscillator,`copycat-signal-sound` 預設開)。
- 紅測試:13 合併與自癒 refetch、SC-11 invalidate 被喚;14 PUT 樂觀更新;
  15 toast 上限 4 + 溢出計數(SC-10 amendment)、hidden 才 Notification、
  靜音時不出聲(Audio/Notification mock,`frontend-testing` 慣例)。

### 16. `frontend/src/components/ToastStack.tsx` + 17. `frontend/src/components/stock/SignalRail.tsx`(新增)

- 16:fixed 右上 z-50;props `{toasts, overflow, onDismiss}`;每則 kind 中文 +
  代號名稱 + 價格。紅測試:渲染 4 則 + 「+N」、點擊 dismiss。
- 17:w-52 shrink-0 左欄;上半「今日訊號」列表(`HH:MM 代號 名稱 訊號名 價格`,
  點擊 `onSelect(code)`)+ 停用 kind 過濾;下半「監聽訊號」四 toggle
  (useSignalsConfig)+ Notification 權限鈕(permission==="default" 時);
  音效 toggle。紅測試:列渲染格式、點擊切檔、toggle 呼叫 mutation、
  停用類型不入列(SC-9)。

### 18. `frontend/src/components/stock/StockPage.tsx`(修改)+ 19. `frontend/src/App.tsx`(修改)

- 18:版面 `[SignalRail][WatchlistSidebar w-60][main]`;SignalRail 的 onSelect 接
  既有 `onSelect`。紅測試:SignalRail 存在於最左(DOM 序)。
- 19:掛 `<ToastStack>`(tab 無關常駐)+ `useSignalAlerts`(watchlist invalidate
  不在此 — 見第 12 節)。紅測試:signal bus 事件 → toast 出現在任一 tab。

## 驗證 gate(每節完成後跑)

`pytest -q` + `ruff check copycat tests` + `pyright`;動 frontend 後另
`npm test` + `npx tsc -b` + `npx eslint src`(frontend/)。收尾前
`copycat validate`(需先跑 four/five replay — 本輪未動 replay 引擎,預期直過)。
