# XR-3 change-spec:SignalHub 與 stock engine 解耦

日期:2026-08-12。現況調查:同目錄 `current-state.md`(引用其編號 C1-C4 / S1-S5)。
分流判定:**已成形方案** — XR-3 遺留項指名解法方向(hub 的 bus/trade_date 與 stock
engine 解耦),四個方向性決策 2026-08-12 由 user 逐題拍板,無方向性 auto-default。

## 0. 拍板紀錄(user 逐題,2026-08-12)

1. **解耦邊界 = bus 抽到 app 層**:create_app 建 `stock_ws = WsBroadcaster`,注入
   StockEngine(🔵 先重構掉自持 `_ws`)與 SignalHub;`/ws/stock` 改 relay 這顆
   broadcaster,engine 在場才附 quote seed。與 capital_ws/futures_ws/corr_ws/river_ws
   慣例一致。
2. **trade_date:engine 在用 engine、不在用牆鐘**:boot 時依 stock 是否在場擇一注入;
   engine 在場語意逐字不變;不在場 → 本機牆鐘日。engine 不會盤中才出現(boot 序列
   固定),不需動態切換。
3. **daily_bars 替代供應 = stub 回空清單**:async 恆回 `[]` → hub 既有路徑判成
   「資料面就是沒有」:不重試、逐檔一次 CDP 停用 warning、cache 落 None。零 hub
   內部改動。
4. **生命週期全解:hub/bot 恆啟,`_signals` gate 只看 hub**:`_make_signals` 去掉
   stock gate(壞規則檔 → hub None 的 R9 降級不變);route gate 去掉 `_stock()`
   前置;TC4 沒開時 today + 規則 CRUD 全可用;bot 照建(service=None 時 `/watch`
   回 fallback 文案)。

## 1. 成功條件(SC gate)

- **SC-1 hub 獨立存活**:`stock_source=None`(TC4 不在)boot 後
  `app.state.signal_hub is not None`,jsonl / 規則檔落點不變(`wl_path.parent`)。
  驗證:`pytest tests/server/test_signal_routes.py -q`(改寫後的
  `test_no_stock_leaves_hub_none` 後繼測試)。
- **SC-2 廣度事件鏈照活(REST)**:TC4 不在時 `GET /api/stock/signals/today` 200
  (空 → `{"signals": []}`);經 `hub.publish_market_events` 發布的事件出現在
  today 回應,`trade_date` = 牆鐘日。
  驗證:新測試(with_stock=False → publish → GET 斷言)。
- **SC-3 規則 CRUD 照活**:TC4 不在時 GET rules 200(預設規則)/ POST 201 /
  PUT 200 / DELETE 204。
  驗證:改寫後的 `TestSignalRoutesNotReady`(更名)逐 route 斷言。
- **SC-4 廣度事件鏈照活(WS)**:TC4 不在時 `websocket_connect("/ws/stock")` 不被
  立即 close;`hub.publish_market_events` 後 client 收到 `type=signal` payload。
  驗證:新 WS 測試(TestClient websocket)。
- **SC-5 TC4 在場行為逐字不變**:白名單(§3)全保留。
  [amendment 2026-08-12: review R2-2]驗證:`pytest -q` 全綠(baseline 2595 passed;
  僅 §5「該紅」清單(現 4 條)+ test-infra 落點隔離批次按預告改寫,其餘不得紅;
  test-infra 批次不是行為紅測試,commit body 標 `test-infra-fix`)。
- **SC-6 breadth 掛 hub 在 TC4 不在時成立**:`breadth is not None and signals is
  not None` 條件在 stock None 時如今成立(app.py 732 條件式本身不動)。
  [amendment 2026-08-12: review P0-1]驗證:改寫既有
  `test_breadth_routes.py::TestSignalHubWiring::test_no_hub_leaves_breadth_unattached`
  (它現斷言 stock 缺席 → hub None → breadth 不掛,正是本 SC 的反面錨點,**該紅**;
  改為斷言 hub 非 None 且 `breadth._signal_hub is app.state.signal_hub`,類名 /
  docstring 同步改寫)+ 既有 `test_hub_attached_after_breadth_boot` 不紅。
  刪除原「Phase 4 判定、擇一落地」條款(`_ok_fetchers` 基建已存在)。
- **SC-7 降級語意保留**:壞規則檔 → hub None → 全 signals route 503;
  `SignalHub.start` 炸 → 同上;兩者與 stock 在否無關。
  驗證:既有 `test_bad_rules_file_degrades` / `test_hub_start_failure_isolates_signals_only`
  不紅。
- **SC-8 落點零汙染**[amendment 2026-08-12: review P0-2/P0-3]:全量 pytest 跑完
  repo `data/` 零新增 / 零變更;`--verify` server 起停後 `data/signals/` 與
  `data/signal_rules.json` 零變更(hub 落點隔離到 VERIFY_DATA_DIR)。
  [amendment 2026-08-12: review R2-3]驗證:`/data/` 被 .gitignore,git status 恆空
  (vacuous)—— 改用前後快照 diff:跑 pytest / verify 冒煙前後各做
  `Get-ChildItem -Recurse data | Select-Object FullName,Length,LastWriteTime` 快照,
  hub 所屬路徑(`data/signal_rules.json`、`data/signals/**`、`data/stock_watchlist.json`)
  出現新增 / 變更即 FAIL;驗證時段避開 prod 進程寫入窗(盤後或 prod 未跑時執行,
  否則以內容鑑別 fake 事件)。verify 側另加正向斷言:產物落在 VERIFY_DATA_DIR。

UI 層:**無 frontend 改動**。TC4-off 時 today 從 503 → 200 空清單,前端既有分支
自然顯示「今日尚無訊號」;FE-1 的 503 顯示分支保留(hub 自身降級仍會觸發)。
[amendment 2026-08-12: review P1-2]`/ws/stock` 不再立即 close 的可見副作用:
個股頁「連線異常」提示靠 `status.tc4 === "down" || wsStatus === "closed"` 觸發,
而 `status` 初值 `{tc4: "up"}` —— 掛著的空流會讓 TC4-off 完全無提示。補償(仍屬
後端):無 engine 的 relay 分支在首則 seed 送 `{"type":"status","tc4":"down",
"backfilling":null}`(與 engine 發的 status 形狀一致),前端既有分支自然顯示
TC4 斷線提示;此 seed 納入 SC-4 斷言。
[amendment 2026-08-12: review R2-6]文案語意落差:前端對 `tc4="down"` 顯示
「達錢 4 連線中斷,恢復後自動回補」,而無 engine 模式下 TC4 恢復**不會**自癒
(stock engine 只在 boot 建,需重啟 server)。判定:**接受文案偏差**
[auto-default: 接受 + 前端文案分態記 next-time | reason: 主訊息「達錢 4 連線中斷」
正確;改回 close 會回到 P1-2 原問題;frontend 本輪 out of scope]。SC-4 斷言
只保證「有 status down seed」,不保證前端文案逐字準確。
驗證窗口:無外部時效窗(全部可在測試環境 + 任意時間的真實環境驗:TC4 關著起
server 打 today / 連 WS)。

## 2. 不能破壞的既有行為白名單

1. TC4 在場時訊號鏈全行為逐字不變:tick 評估、CDP 基準(X-2b 重試梯)、兩段式
   rollover、Discord 節流、同群摘要、jsonl 決定性 id、`today_signals` 雙日聯集(R2-3)。
2. 壞規則檔 → hub None + signals route 全 503(R9 大聲降級)。
3. hub start 失敗 → 訊號單獨停用,其他引擎照常(TQ-7)。
4. CC-2:`stock.attach_signal_hub(hub)` 是 `_start_signals` 最後一行;關機先
   detach 再 close;S5 反序順序(breadth → signals → … → stock)不動。
5. `publish_market_events` R7:以傳入 trade_date 落檔,日別不符每日別 warn 一次。
6. `/ws/stock` 在 stock 在場時:連線即收 quote seed、斷線偵測(test_ws_disconnect
   `_WsCase`)行為不變。
7. 鄰近 route 行為不動:同內容 PUT watchlist no-op、`/api/stock/names` 不過 stock
   閘、`_valid_code` 的 503 優先序(在仍有 `_stock` 前置的 route)。
8. StockEngine 直接建構(不帶注入)之既有測試零波及(`ws` 參數預設 None → 自建)。
9. [amendment 2026-08-12: review P0-3]prod 的 `data/signals/*.jsonl` 只能由 prod
   進程寫入 —— 它是 breadth 對帳 seed(`market_event_state`),verify / 測試進程
   寫入假事件會讓 prod 真鎖板事件被 seed 判成已發布而**靜默不發**。

## 3. Backward compat / migration

- API 形狀零改動;today 503 → 200 是**放寬**,無 client 需遷移。
- `StockEngine.__init__` 新增可選 keyword `ws`(預設 None → 自建
  `WsBroadcaster(maxsize=_CLIENT_QUEUE_MAX)`),既有 caller 不動。
- `SignalHub` 建構子簽名不變(改的是 app.py 注入端)。
- 無持久化格式改動 → **migration:N/A,可逆性:N/A**(回退 = revert commits)。

## 4. Out of scope

- HR-6(WS 事件丟包 seq 回補)、HR-3(close 順序倒置)、HR-5(dropped 觀測性)。
- frontend 任何改動(含時間軸 503 分支調整)。
- hub fanout 佇列 / Discord 架構。
- stock engine 其他職責(status/book payload、回補 worker)。
- `/ws/stock` 之外各 WS 端點的 None 分支(index/corr/river 維持 close)。

## 5. 既有測試:該紅 / 不該紅

**該紅(行為預告,🔴 先改測試紅再改實作綠)**:
- `test_signal_routes.py::TestLifespanWiring::test_no_stock_leaves_hub_none`
  [amendment 2026-08-12: review P2-1 類名更正]
  → 改斷言:hub **非** None、watchlist_service 仍 None。
- `test_signal_routes.py::TestSignalRoutesNotReady::test_all_signal_routes_return_503`
  → 整組改寫為「TC4 不在時全可用」(SC-2/3 斷言;類名同步更名)。
- [amendment 2026-08-12: review P0-1]
  `test_breadth_routes.py::TestSignalHubWiring::test_no_hub_leaves_breadth_unattached`
  → 改寫為「stock 缺席 → hub 仍在 → breadth 照掛」(SC-6 錨點;docstring 同步)。
- [amendment 2026-08-12: review R2-1]
  `test_main_wiring.py::test_verify_mode_fake_source_and_neutralize`
  → verify 分支 kwargs **集合恆等**斷言(115-119)加入 `stock_watchlist_path`,
  並加正向斷言 `cap.create_kwargs["stock_watchlist_path"] ==
  main_mod.VERIFY_DATA_DIR / "stock_watchlist.json"`(把 SC-8 隔離契約鎖進測試,
  與既有 `breadth_data_dir` 斷言同款)。同檔
  `test_verify_fail_injection_uses_isolated_dir_and_clears_chain` 只斷言
  `breadth_data_dir`,不受影響 —— 但 fail 變體分支的 `stock_watchlist_path` 應同步
  指向 fail data_dir,順手納入該測試斷言與否由 Phase 4 判(不擴 scope)。

**不該紅**(節錄,全集見 current-state §6):`test_hub_start_failure_isolates_signals_only`、
`test_bad_rules_file_degrades`、`test_shutdown_detaches_hub_from_engine`、
`test_signal_hub.py` 全部、`test_breadth_*` 其餘(含 `test_hub_attached_after_breadth_boot`
/ `test_detach_happens_before_close`)、`test_stock_engine.py`、
`test_stock_routes.py` 既有 WS 測試、`test_ws_disconnect.py`。

**必須跟著改的測試基建(test-infra,非行為紅測試;SC-8 的落點隔離)**
[amendment 2026-08-12: review P0-2]:所有建 app 而未傳 `stock_watchlist_path` 的
基建,改動後會建出真 hub、落點打到 repo 真 `data/`(寫 `signal_rules.json`;
test_breadth_routes 系列更會經 attach 把 fake 鎖板事件寫進 prod jsonl)。
[amendment 2026-08-12: post-round-2 改良]全量 grep 實測共 **19 個站點 / 12 檔**
(test_app 56、test_boot_window 163/233/262、test_breadth_routes `_make_app` 預設、
test_capital_api 135、test_corr_routes 14、test_health 20、test_index_routes 22、
test_market_routes 51、test_oi_levels 375、test_river_routes 14、test_stock_routes
132/314/517、test_ws_disconnect 141/329/446/451/462/485)—— 逐站點補傳散且未來
新測試會靜默回歸,改採 **conftest 層一次隔離**:新增 `tests/server/conftest.py`,
autouse fixture monkeypatch `copycat.server.app.WATCHLIST_DEFAULT_PATH` →
`tmp_path / "stock_watchlist.json"`(app.py:72 模組級名、create_app 於 call time
讀取(348),可 patch;顯式傳路徑的測試不受影響;沿 tests/conftest.py 既有
「外部 IO 同型隔離」autouse 慣例)。19 站點**零改動**;`create_app(` 全量 grep
已複核無 tests/server 之外的呼叫點(helpers/boot.py 只是 wrapper)。
commit 歸 🔴 波、body 註 `test-infra-fix: hub 落點隔離(SC-8)`。

**新測試清單**(全 🔴 波,對應 SC):
- T1(SC-1):with_stock=False → hub 非 None;規則檔生成於 tmp data dir。
- T2(SC-2):with_stock=False → today 200 空;`publish_market_events` 後 today 含
  該事件且 `trade_date` = 牆鐘日(兼驗 trade_date fallback)。
- T3(SC-3):with_stock=False → rules GET/POST/PUT/DELETE 全通。
- T4(SC-4):with_stock=False → `/ws/stock` 連線存活,首則收到
  `{"type":"status","tc4":"down",...}` seed(review P1-2),publish 後收到 signal。
- T5(daily_bars stub):with_stock=False + 自選檔含碼 → boot 完成不炸,
  hub `_basis_cache` 該碼落 `(牆鐘日, None)`(stub 空清單 → CDP 停用、無重試)。
- T6(bot):with_stock=False → `create_bot` 以 `(None, hub)` 被呼叫
  (monkeypatch 記參數;沿既有 `_boom` patch 模式)。

## 6. Diff 級章節(逐檔,🔴🟢🔵 三類)

### 🔵 copycat/server/stock_engine.py(先行,行為零差異)
- `__init__` 加 keyword `ws: WsBroadcaster | None = None`;
  `self._ws = ws if ws is not None else WsBroadcaster(maxsize=_CLIENT_QUEUE_MAX)`。
- 其餘零改動(`stream`/`_publish` 照舊讀 `self._ws`)。
- 既有測試:不紅。

### 🔴 copycat/server/app.py(行為改動主體)
- create_app 區塊變數:`stock_ws = WsBroadcaster(maxsize=_CLIENT_QUEUE_MAX)`
  [amendment 2026-08-12: review P2-2 常數名統一],import
  `from copycat.server.stock_engine import _CLIENT_QUEUE_MAX`(= 1000,同 repo
  私名跨模組慣例 `_best_limit_price` 先例)
  [auto-default: 私名直 import 不改公開 | reason: 兩份上限值必然漂移,共用同一常數;
  ws.py 已有同名公開 `CLIENT_QUEUE_MAX`(=500),改名公開必撞]。
  [amendment 2026-08-12: review R2-4]掛載點更正:另四顆是在 **create_app body**
  (lifespan 之外,app.py 820-823)掛 `app.state` 的 —— `app.state.stock_ws =
  stock_ws` 緊接該組同位置,不是 lifespan 內。
- `_make_stock`:建構時傳 `ws=stock_ws`。
- `_make_signals`:去掉 `if stock is None: return None`;四注入改為:
  `publish=stock_ws.publish`;`daily_bars=stock.daily_bars if stock else _empty_daily_bars`
  (模組級 async stub 恆回 `[]`);`trade_date_fn=(lambda: stock.trade_date) if stock
  else _wall_clock_trade_date`;`quotes_fn=stock.quotes if stock else None`。
  `groups_fn` 照舊(檔案)。
  [amendment 2026-08-12: review P1-3 求值時機寫死]fallback 是**每次呼叫求值**的
  模組級函式:
  `def _wall_clock_trade_date() -> str: return os.environ.get("TXO_BACKFILL_DATE") or f"{_date.today():%Y-%m-%d}"`
  —— 長跑跨日要自動前進(edge §7.4),boot 時算一次的靜態字串會停在昨日,
  `_distribute` 日別尺與 market warning 全跟著壞。
- `_start_signals` / `_close_signals`:**零改動**(attach/detach 已有 `if stock is
  not None` guard;bot 建立本就走 service 變數,stock None 時 service 為 None)。
- `_signals` route gate:刪 `_stock(request)` 行,docstring 同步(503 只剩
  「hub 自身降級」一種語意)。
- `/ws/stock`:`stock is None` 分支改 ——
  [amendment 2026-08-12: review P2-5 併入 hub gate]
  (a) boot 尚未完成(`not app.state.boot_done`)**或 hub 亦 None**(壞規則檔 /
  start 炸)→ 維持既有 close(前者保留「重連拿 seed」自癒,後者維持「服務未就緒」
  語意,不留永遠無流量的殭屍連線);
  (b) boot 完成且 hub 在 → 先送一則 `{"type":"status","tc4":"down","backfilling":None}`
  seed(review P1-2;走 `stock_ws.stream(seed=[...])`,與 engine status 形狀一致),
  再 relay(無 quote seed:無 engine 即無 quote 可種)
  [auto-default: boot 窗內維持 close | reason: 早連 client 會錯過 engine 起來後的
  seed,現況 close→重連→拿 seed 的自癒比掛著空流好]。
- breadth attach(732)與關機反序:**零改動**。
- [amendment 2026-08-12: review P2-3]註解同步清單(舊不變式改後成假話,逐處改):
  `_boot_all` docstring「signals 需 stock」(394)→ 改「signals 可獨立於 stock」;
  `_start_signals` 內 `if stock is not None:  # _make_signals 已保證;narrowing 用`
  (518)→ guard 升格為 load-bearing,理由改寫;`_signals` docstring(940-941);
  signals route 區塊註解(1024 起)視內容順改。

### 🔴 copycat/server/__main__.py(--verify 落點隔離)
[amendment 2026-08-12: review P0-3]
- verify 分支 `create_app(...)` 補傳
  `stock_watchlist_path=data_dir / "stock_watchlist.json"`(data_dir = VERIFY_DATA_DIR
  或 fail 變體)→ hub 的 jsonl / 規則檔落點跟著進 verify 隔離區,與既有
  `breadth_data_dir=data_dir` 同一原則(51-54 行註解的隔離精神)。
- [amendment 2026-08-12: review R2-1]本改動的鎖在
  `test_main_wiring.py::test_verify_mode_fake_source_and_neutralize`(kwargs 集合
  恆等斷言),列 §5 該紅第四條。
- prod 分支零改動。

### 🔴 tests/server/test_signal_routes.py(先紅後綠)
- 改寫 §5「該紅」前兩條;新增 T1-T6。
- `make_app`/`BootedClient` 基建沿用(`with_stock=False` 既有參數)。
- [amendment 2026-08-12: review P1-1]T2/T4 的驅動方式明定:`publish_market_events`
  / 對 hub 的任何呼叫**必須回到 event loop 執行**(`WsBroadcaster.publish` 契約
  「必須在 loop 上呼叫」;jsonl 落檔由 worker 非同步完成)—— 用 TestClient portal
  驅動;jsonl / today 斷言用有上限的輪詢等待(比照 test_breadth_routes
  `_wait_counts` 模式),不做一次性立即斷言。
  [amendment 2026-08-12: review R2-5]portal 用法寫死:`portal.call` **只吃位置參數**
  (anyio `call(func, *args)`),而 `publish_market_events` 的 `trade_date` 是
  keyword-only → 必須
  `client.portal.call(functools.partial(hub.publish_market_events, events, trade_date=d))`,
  不得因 TypeError 改用跨執行緒直呼繞過。

### 🔴 tests/server/test_breadth_routes.py
- 改寫 `test_no_hub_leaves_breadth_unattached`(§5 該紅第三條);落點隔離由
  conftest 接住,`_make_app` 本身零改動。

### 🔴 tests/server/test_main_wiring.py
- `test_verify_mode_fake_source_and_neutralize` kwargs 集合 + 正向斷言
  (§5 該紅第四條)。

### 🔴 tests/server/conftest.py(新檔;test-infra)
[amendment 2026-08-12: post-round-2 改良,取代逐站點補傳]
- autouse fixture:monkeypatch `copycat.server.app.WATCHLIST_DEFAULT_PATH` →
  `tmp_path / "stock_watchlist.json"`;docstring 說明「hub 恆建後,未傳
  watchlist path 的 app 測試落點必須隔離出 repo data/」(SC-8)。
- 19 個既有站點零改動;未來新測試自動隔離。

### (視 Phase 4 判定)tests/server/test_stock_routes.py
- T4 若更適合放這裡(WS 測試同儕)則落此檔;不改既有測試。

## 7. Edge cases

1. **TXO_BACKFILL_DATE + TC4 不在**:牆鐘 fallback 取 env 值優先,與 engine 在場
   語意一致(§6 auto-default)。
2. **stock 在場、hub 建構失敗(R9 壞檔)**:stock_ws 已注入 engine,quote/WS 流
   不受 hub None 影響 —— 隔離方向與現況相同,新 bus 不引入反向波及。
3. **無 engine 時 on_watchlist 種子 → basis job**:stub 回 [] → 逐檔一次
   「無已完成日 K,CDP 停用」warning + cache `(date, None)`;自選 30 檔 = 30 行
   一次性 log,無重試風暴。
4. **無 engine 時永不 rollover**:`on_rollover*` 只由 engine 驅動;跨日後牆鐘
   trade_date_fn 自動前進,today_signals 讀新日檔;basis cache 舊日條目由
   `_distribute` 日別尺擋住,detector 無 tick 無狀態 → 無害。
5. **boot 窗內連 `/ws/stock`**:維持 close(§6 auto-default),窗外才走新分支;
   `boot_done` 旗標既有(app.state)。
6. **同內容多 client**:engine 在場走 `stock.stream()`(帶 quote seed),不在場走
   `stock_ws.stream()`(帶 status down seed)—— 同一顆 broadcaster,兩類 client
   併存安全(seed 只入呼叫端 client 佇列,ws.py 既有語意)。
7. [amendment 2026-08-12: review P2-4]**壞自選檔 + TC4 off**:`_start_signals` 的
   membership 種子 `load_watchlist` 對壞檔仍拋 → hub 被 `_boot` 收成 None →
   廣度鏈在此組合下仍死。判定:**接受,不改**
   [auto-default: 維持大聲降級 | reason: 壞自選檔在 TC4-on 時本就把 stock 引擎
   整段停掉(`_start_stock` 同一支 load),對稱;seed 靜默降空名單違反 R9
   「大聲降級」哲學,且自選檔壞損是使用者本機檔案事故,罕見]。
8. [amendment 2026-08-12: review P2-5]**stock None + hub 亦 None**(壞規則檔 /
   start 炸):`/ws/stock` 照舊 close(§6 分支 (a)),不留空流殭屍連線;
   前端維持 `wsStatus === "closed"` 的既有提示語意。

## 8. 執行約束(前輪 user 指示轉入)

- 本輪 user 在場:spec 階段方向性抉擇已逐題問畢(§0);實作階段照 §6 拍板走,
  新增方向性分歧才回頭問。
- R4 輪約束沿用:廣度事件**硬性不進 Discord**;`publish_market_events` R7 語意不動。
- 鐵則 B 三類分離:🔵 stock_engine 注入 → 🔴 測試紅 → 🔴 app.py 綠,不混 commit。

---
self_review_head: 4544b0f7(code review round-1 三 lens + fix 波收斂,2026-08-12)
