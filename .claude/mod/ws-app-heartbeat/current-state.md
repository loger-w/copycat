# current-state:8 條 WS 心跳 / 靜默 watchdog(mod/ws-app-heartbeat)

> 2026-08-19。來源:handoff `docs/superpowers/specs/2026-08-19-browser-crash-scan-handoff.md` R3 節 +
> Explore caller map(worktree `.claude/worktrees/ws-app-heartbeat`,行號以該 tree = master e55f6082 為準)。
> D3 user 拍板(08-19):**應用層 ping 進 8 條 WS 契約,前端以「太久沒收到任何訊息」為準主動重連,不靠資料頻率**。

## 1. 後端現況

### 1.1 送出路徑:8 條全走 `copycat/server/ws.py::relay()`(ws.py:94)

| 端點 | route | accept 順序 | engine 缺席 | 首則 | 訊息 `type` 值 |
|---|---|---|---|---|---|
| `/ws/txo-pnl` | app.py:1139 | accept 無條件 | N/A(runtime 恆在) | route 自送 `latest_snapshot()` 再 `relay(snapshots(seed=snap))` | **無 `type` 欄**(`{series_id,status,totals,curve,handover}`) |
| `/ws/breadth` | app.py:1631 | accept → 判 None | boot 未完:送一則載入中 scalar 再 `close()`;否則直接 `close()` | seed 封在 `breadth.stream()` | `breadth` |
| `/ws/corr` | app.py:1665 | accept → 判 None | `close()` | 自送 `corr.state()` | `corr` |
| `/ws/river` | app.py:1688 | accept → 判 None | `close()` | 自送 `river_snapshot()` | `river` / `river_delta` |
| `/ws/index` | app.py:1702 | accept → 判 None | `close()` | 無 seed | `index` |
| `/ws/stock` | app.py:1714 | accept 無條件 | boot 未完或 hub None → `close()`;否則空流 + status seed | `watchlist_quote` 每檔 seed | `status/tick/book/stkfut/watchlist_quote/signal/watchlist_changed` |
| `/ws/capital` | capital_api.py:324 | accept → 判 None | `close()` | 無 seed | **無 `type`,用 `event` 鍵**(`capital_status/capital_order/capital_position`) |
| `/ws/futures` | capital_api.py:346 | accept → 判 None | `close()` | 無 seed | `futures` |

- 8 處 `close()` 皆未帶 close code(預設 1000)。
- `relay(websocket: WsConnection, stream)`:`_send`(stream → `send_json`)+ `_recv`(偵測 disconnect)
  `asyncio.wait(FIRST_COMPLETED)`;`WsConnection` Protocol 只有 `send_json` / `receive`。
- **無任何應用層 ping / heartbeat**(grep `ping|heartbeat|keepalive|ws_ping` 零命中,TC4 ZMQ KeepAlive 除外);
  `__main__.py:187` `uvicorn.run(app, host, port)` 未傳 `ws_ping_*`(uvicorn Config 預設 `ws_ping_interval=20.0 / ws_ping_timeout=20.0`,已驗;
  protocol-level,瀏覽器 JS 看不到,但 server 端半死連線 ≤ ~40 s 會被 uvicorn 關閉)。
- 現況 = 「server 靜默」與「連線半死」在前端不可分辨;前端唯一重連入口是 `ws.onclose`。

### 1.2 相關測試(會被「多一則 ping」影響的斷言)

- `tests/server/test_ws_disconnect.py:644-670` `_FakeWebSocket` / `_RaisingWebSocket`(relay 單元測試的 fake);
  `TestRelay.test_forwards_messages_until_disconnect`(:704-720)斷言 `sent == [{"n":0},{"n":1},{"n":2}]` **精確相等**
  → 預設心跳間隔 ≥ 數秒時不受影響,但若 relay 預設間隔太短會破。
- TestClient 首幀精確斷言:`test_app.py:122-128/157-161`、`test_breadth_routes.py:397-417`、
  `test_corr_routes.py:56-63`、`test_river_routes.py:61`、`test_index_routes.py:76`、
  `test_signal_routes.py:770/873/950`、`test_stock_routes.py:830`、`test_capital_api.py:1104`
  → 皆在連線後毫秒級取幀,心跳間隔秒級時不受影響;**但 ping 不可在首幀前送**(以防萬一仍以「ping 只在 interval 到期後送」為設計)。
- `test_ws_disconnect.py:561-641` 真 uvicorn + RST 測試 `batches >= want` 是地板,多幀無害。

## 2. 前端現況

### 2.1 8 hook 同款骨架(無共用 helper;`grep WebSocket src/lib` 零命中)

共通:`let ws / timer / backoff(1 000→×2→cap 30 000)`;`onopen` 把 backoff 歸零;`onclose`
`if(!alive) return; setTimeout(connect, backoff); backoff*=2`;`onerror = () => ws?.close()`
(**8 處全部關的是閉包共用變數 `ws` 當下指向的 socket**,StrictMode 舊 socket 晚到的 error 會關掉新 socket = FE-WS-ONERROR-ALIAS);
unmount `alive=false; clearTimeout; ws?.close()`。

| hook | `new WebSocket` | onmessage 對未知 type | wsStatus |
|---|---|---|---|
| `useTxoSnapshot.ts` | :23 | **無 type 檢查,每則 `setData(JSON.parse)` 整包覆蓋** → ping 會把 snapshot 清成 `{type:"ping"}` | 回傳 |
| `useBreadth.ts` | :123 | `msg.type!=="breadth"` 早退 | 無 |
| `useCorrelation.ts` | :55 | `!=="corr"` 早退 | 回傳 |
| `useFuturesStream.ts` | :118 | `!=="futures"` 早退 | 回傳 |
| `useIndexStream.ts` | :172 | `!=="index"` 早退 | 回傳 |
| `useRiver.ts` | :141 | 非 river/river_delta 靜默丟 | 回傳 |
| `useStockStream.ts` | :432 | `switch` default return | 回傳(另有 `wsOpenRef` StrictMode 順序註解 :448-459) |
| `useCapital.ts` | :238 | 無 string `event` 欄即忽略 | module store `useCapitalWsStatus()` |

額外 timer(與 WS 重連無關,不動):`useIndexStream` retryTimerRef、`useStockStream` retryTimerRef/scheduleRetry、
`useCapital` invalidateTimers。

### 2.2 UI 消費

`ConnectionBadge.tsx:17-42`:`broken = wsStatus !== "open"` → 「連線中」/「連線中斷,重試中」;
消費處 App / CorrPage / CorrPanel / FuturesLadder / FuturesPage / PriceLadder / StkfutLadder / StockPage。
`WsStatus` 三態型別**7 hook 各自宣告一份同值**(useTxoSnapshot.ts:5 / useCorrelation.ts:11 / useFuturesStream.ts:12 / useIndexStream.ts:11 / useRiver.ts:19 / useStockStream.ts:16 / useCapital.ts:29)+ `types.ts:2` 一份;ConnectionBadge 從 useTxoSnapshot import。
**非 Badge 消費者(capital)**:`useFlashArm.ts:50` `wsStatus==='closed' → dispatch conn_lost`(閃電下單解除武裝,level 觸發);`FuturesLadder.tsx:139/380`、`PriceLadder.tsx:392` lockDisabled。

### 2.3 前端測試

8 hook 各有 colocated test,各自一個 `FakeWS`(`vi.stubGlobal("WebSocket", FakeWS)`,`emit(obj)` 手動餵),
沒有測試斷言整條連線的訊息總數 → 心跳只在測試主動 emit 時才有影響。
`useTxoSnapshot.test.ts:7-25` `FakeWebSocket.instances[]`。

## 3. 瀏覽器事實(設計約束)

- Chromium `ws.close()` 對半死 TCP:送 Close frame 後等對方回應,**closing handshake timeout = 60 s** 才 fire `onclose`
  → watchdog 觸發時**不能只 `close()` 等 onclose**,要自己直接走重連路徑(卸掉舊 socket handler,close 丟著不等)。
- accept-then-close 會 fire `onopen` → 現況 backoff 歸零 → 1 Hz 重連(engine 缺席期間持續)。

## 4. 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 後端心跳 | 無 | `relay()` 每 `WS_HEARTBEAT_SECS`(10 s)送 `{"type":"ping"}`,8 條同時生效 |
| 前端半死偵測 | 無(只靠 onclose) | 共用 helper:>`WS_SILENCE_TIMEOUT_MS`(30 s)無任何訊息 → 卸 handler、close、立即走重連 |
| ping 對 payload | — | 6 條 type 過濾天然忽略;`/ws/capital` 無 event 忽略;`/ws/txo-pnl` **前端必須顯式過濾 `type==="ping"`** |
| backoff 歸零時機 | onopen | 連線存活 ≥ `WS_MIN_UPTIME_MS`(5 s)才在 onclose 歸零(accept-then-close / 載入中 scalar 不再 1 Hz) |
| onerror | 關共用變數 `ws` | 關自身 socket |
| 後端 accept-then-close | 8 處 | **不動**(前端 min-uptime 規則已解 1 Hz;改 reject-before-accept 會動 breadth 載入中 scalar 契約與多個 route 測試,收益為零) |
| 契約文件 | CLAUDE.md §4 無 | §4 新增「WS 心跳契約」條目(產生點 / 讀者 / 改值同改兩邊) |

## 5. Caller / backward compat

- 後端:`relay` 簽名**新增 keyword-only 參數**(預設值 = 開啟),8 端點 / **9 個 call site**(`/ws/stock` 兩分支 app.py:1740/1748)零改動;`WsConnection` Protocol 不變
  (ping 走既有 `send_json`)→ 測試 fake 不用改。
- 前端:8 hook 改吃共用 helper;對外回傳 shape(`wsStatus` / state)不變;`WsStatus` 型別與 ConnectionBadge 不動。
- 舊前端 bundle 對新後端:見 change-spec §3(TXO 頁 render 例外;dev HMR 不發生;重啟後端後重整分頁)。
- 新前端對舊後端:見 change-spec §3(watchdog 以首則 ping 武裝 → 行為 = 現況)。
- Migration:無資料格式變更,無狀態持久化;可逆 = revert PR。
