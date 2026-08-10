# current-state:server 啟動期 HTTP 空窗(mod/startup-http-window)

日期:2026-08-05。Baseline:`pytest -q` → **1720 passed**(76.3s,exit 0)。

## 1. 現況:lifespan 阻塞結構(copycat/server/app.py)

`create_app` 的 lifespan(app.py:231-489)在 `yield`(:454)前**同步 await 完整引擎
啟動鏈**,期間 uvicorn 不 serve 任何 HTTP(ASGI lifespan 語意:startup 完成前不收
request)。真實量測(next-time 2026-08-04 條):fake 延遲 12s → 12.6s 才首次 200;
prod 常態 = TXO 全鏈回補數十秒~分鐘級。

yield 前的順序(行號 = 2026-08-05 HEAD 587bcd7):

| # | 段落 | 行號 | 阻塞成分 | _boot 隔離 |
|---|------|------|----------|-----------|
| 0 | `app.state.build` + banner | :234-235 | git subprocess ~50ms | 無(刻意:banner 必印) |
| 1 | `EngineRuntime(...)` 建構 | :236-243 | 純 wiring(source 建構 lazy,見 §3) | — |
| 2 | `app.state.runtime` + `await runtime.start()` | :244-245 | **主阻塞**:list_series REQ + activate → subscribe + fetch_backfill(TXO 全鏈,to_thread)| **無** — 失敗 = lifespan 例外,server 起不來 |
| 3 | stock `_boot`(start + 自選回填)| :247-279 | subscribe REQ 逐檔 + set_watchlist;秒級 | 有 |
| 4 | `WatchlistService` 建構 | :281-286 | 純建構 | —(依賴 stock 非 None)|
| 5 | signals `_boot`(hub.start + bot 登入 + attach)| :288-343 | discord 登入(網路)| 有 |
| 6 | index `_boot` | :345-372 | IX0001 subscribe + 當日 1K 回補;秒級 | 有 |
| 7 | capital `_boot`(COM 執行緒 spawn)| :374-393 | DLL 載入 + spawn;login 在 COM 執行緒非同步 | 有 |
| 8 | futures `_boot` | :395-414 | TXF/MXF/TMF subscribe REQ | 有 |
| 9 | corr `_boot`(六腿 subscribe;1K 回補已是背景 `_schedule_backfill`)| :416-452 | 六腿 subscribe REQ | 有 |

關機反序(finally :455-489):signals → corr → futures → capital → index → stock →
runtime,各自 try/except 續行。

## 2. app.state 掛載順序依賴(重審清單,user 指定起點)

1. **watchlist_service 必先於 signals**(:281-286 註解):`service` 是 `_start_signals`
   closure 自由變數;反了 = NameError 被 `_boot` 吞成「訊號靜默停用」。
2. **signals 需 stock**(`_make_signals` stock None → None;`_start_signals` 末行
   `stock.attach_signal_hub` 必須是最後一行,CC-2)。
3. **index 讀 `runtime.spot_millipts`**(:358):bound method 引用,runtime 未 started
   時回 None(`_agg is None`)— 引用本身不需 runtime 已 start,但現況順序是 start 後。
4. **capital 先 `set_broadcast` 再 `start`**(:383):啟動狀態事件不漏。
5. **corr 必後於 futures**(:416-418):base 腿讀 `futures.state()`;futures None →
   getter 回空 dict(corr 自身把「上游空著」當正常態,CLAUDE.md §8)。
6. `_close_signals` 用 nonlocal `bot` + closure `stock`/`service` — 關機路徑與 boot
   同 scope(背景化時這些 local 的存活範圍要重整)。
7. `app.state.discord_bot` 只在 signals 成功時掛 bot(:343)。
8. WsBroadcaster 四座(capital_ws/futures_ws/corr_ws/river_ws)在 create_app 頂層
   建構、lifespan 外掛載(:501-504)— 不在阻塞鏈上。
9. `register_capital(app)`(:505)是 route 註冊,lifespan 外。
10. 關機反序 :455-489(上表)。

## 3. Source 建構子皆 lazy(背景化的前提事實)

- `TC4QuoteSource.__init__`(tc4.py:124-153):純欄位,連線走 `_ensure_connected`。
- `StockQuoteSource.__init__`(stock_source.py:304+):同款 lazy。
- futures/corr source 繼承 `TC4QuoteSource`/`StockQuoteSource` 家族,同 lazy。
- `capital_factory.get_capital`(factory.py:87+):讀 env + 建 `SkcomCapitalCom`
  wrapper;COM init/login 在 `client.start` spawn 的 COM 執行緒。
→ **建構(make)全部便宜;貴的是 start/subscribe/backfill。**

## 4. Caller map:app.state 消費點與 None 行為

| 屬性 | 消費點 | None 時行為 |
|------|--------|-------------|
| `runtime` | app.py `_runtime`(:521,txo **series/select/contracts/snapshot** 四條)、`ws_txo_pnl`(:562)、`_make_index` txf_getter | **無 None guard — 假設恆存在**。但未 started 的 runtime:`list_series()` 空 → 503 NOT_READY;`latest_snapshot()` series_id None → 503(snapshot route);`snapshots()` 可訂(無資料不 yield);`spot_millipts()` → None;**`/api/txo/contracts`(:545-550)回 200 空列表**(`orderable_symbols` 只剩 SPOT,被 `TC.O.` 前綴濾掉)= 既有「空鏈」形狀,前端 OrderPanel fallback 有測試釘住(OrderPanel.test.tsx:248-263)。**即:掛「未 started 的 runtime」= 既有 NOT_READY / 空鏈語意,不需 None guard**(review R6 補列) |
| `stock` | `_stock`(:576)+ ws_stock(:857) | 503 NOT_READY / WS close |
| `watchlist_service` | `_watchlist_service`(:582;先 `_stock` gate) | 503 NOT_READY |
| `signal_hub` | `_signals`(:589;先 `_stock` gate) | 503 NOT_READY |
| `index` | `_index`(:710)+ ws_index(:845)+ market_bars TWSE/OTC | 503 / WS close |
| `futures` | market_bars(:767)、capital_api :178/:244/:252 | 503 / WS close |
| `corr` | corr/river REST+WS(:801-843) | 503 CORR_NOT_READY / RIVER_NOT_READY / WS close |
| `capital` | capital_api :115/:127/:230 | disabled 語意(route 自處理) |
| `discord_bot` | (無 route 消費;測試斷言用) | — |
| `build` | `/api/health`(:512) | 恆存在(yield 前第 0 步) |

**結論:除 `runtime` 外全部 route 已把 None 處理成 503/WS close;`runtime` 以
「已建構未 started」掛載即可沿用既有 NOT_READY 語意。啟動窗的對外形狀 = 既有
「引擎降級」形狀,前端無新狀態**(useStockNames refetchInterval 等自癒已在,
next-time 2026-08-04 條)。

## 5. 測試契約(最大 blast radius)

- starlette `TestClient` 的 `with client:` = **lifespan startup 跑完才返回**。現況所有
  server 測試依此假設「進 context = 引擎就緒」,直接打 route 期待 200、或直接斷言
  `app.state.signal_hub is not None`(test_signal_routes.py:67 等)。
- 站點:`TestClient(` 33 處 / 9 檔;`create_app(` 測試側 ~20 處(多數經各檔
  `make_client` helper);`test_ws_disconnect.py` 另有真 uvicorn 治具
  `_RunningServer`(:226,等 `server.started` = HTTP ready,背景化後 ≠ 引擎就緒)
  + 舊式 inline uvicorn(:140)。
- `tests/server/test_stock_routes.py:59-99` 兩條 characterization 釘住 `_boot` 降級
  契約(start 失敗 close source + 503);其斷言在 with 區塊後檢查 `fake.closed` —
  背景化後仍需成立(關機路徑必須把「boot 進行中」收乾淨)。
- `test_main_wiring.py` monkeypatch create_app,不受影響。

## 6. 現況 vs 目標

| 面向 | 現況 | 目標 |
|------|------|------|
| HTTP 可用時點 | 引擎鏈全部 start 完(數十秒~分鐘)| lifespan 立即 yield,首次 200 亞秒級 |
| 啟動窗對外行為 | 連線被拒/掛起(uvicorn 未 serve)| 503 NOT_READY / WS close(= 既有降級形狀)|
| TXO runtime 失敗 | lifespan 例外,**server 整台起不來** | 背景 task 內失敗 → log + NOT_READY(行為改動,需拍板)|
| 引擎啟動順序 | 順序不變(§2 依賴全保留)| 同順序,搬進背景 task |
| 關機 | yield 後才可能關機 | 需處理「boot 進行中收到關機」:cancel + 反序關已起引擎(`_boot` 對 CancelledError 的 cleanup 是新分支 — 現 except Exception 接不到)|
| 測試「進 context = 就緒」 | 成立 | 不成立 → 需 readiness 等待機制 |
| 就緒可觀測 | 無(HTTP 通 = 就緒)| 需新管道(候選:/api/health 加欄位) |

## 7. Backward compat 面

- HTTP API shape:不變(503 NOT_READY 是既有 error code;前端已處理)。
- `/api/health`:若加 boot 狀態欄位 = 純增欄(前端忽略未知欄;dev 版本落差膠囊
  只讀 git_sha,不受影響)。
- `create_app` signature:內部 API(caller = __main__ + 測試,同 repo 同輪改)。
- 「TXO source 壞 → server 起不來」變「起得來但恆 NOT_READY」:唯一對外可感知的
  行為改動;banner/log 仍可判。--verify 模式(__main__:126-138)走 fake source,
  boot 快速完成,行為實質不變。
