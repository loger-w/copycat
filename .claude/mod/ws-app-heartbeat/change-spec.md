# change-spec:8 條 WS 應用層心跳 + 前端靜默 watchdog(mod/ws-app-heartbeat)

> 2026-08-19。現況表見同目錄 `current-state.md`。規格來源 = handoff R3 節(user 撰寫/拍板文件)+
> D3 user 拍板「server 定時報平安」→ 方向已定,其餘細節採 `[auto-default]`。
> **分流判定**:已成形方案(需求指名做法:後端 ping 訊息 + 前端靜默重連;決策點 = 間隔 / 落點 / backoff 規則)
> → grilling 姿態逐題自答,無方向性抉擇(D3 已拍板),不再停等。
> 規模:**L**(後端 1 檔 + 測試 2 檔;前端 1 新 lib + 8 hook + 測試;跨前後端契約)→ spec review 1 輪 + 實作 dispatch。

## 0. 目標一句話

8 條 WS 的半死連線(TCP 活著但無資料)前端能自己分辨並重連:後端每條 WS 固定週期送
`{"type":"ping"}`;前端「太久沒收到任何訊息」就卸掉舊 socket 立刻重連;順手修 accept-then-close
1 Hz 重連與 onerror alias。

## 1. 成功條件(SC)

| # | 條件 | 驗證方式 |
|---|---|---|
| SC-1 | 後端:任一 WS 連線在無推播時,每 **10 s**(`WS_HEARTBEAT_SECS`)收到一則 `{"type":"ping"}`;有推播時 ping 照送(定時,不看流量),且不與推播 frame 交錯 | (a) `tests/server/test_ws_disconnect.py::TestRelay::test_heartbeat_*`(小間隔 0.02 s,fake WS);(b) route 層:TestClient 連 `/ws/txo-pnl`(monkeypatch `ws.WS_HEARTBEAT_SECS=0.05`)收到 ping;(c) 真環境:側車 server(fake source,port 8899,零 ZMQ)+ `websockets` client 連 `/ws/txo-pnl` 量連續 3 則 ping 間隔,期望 10.0 ± 0.5 s,證據 `evidence/SC-1_ping_interval.txt` |
| SC-2 | 前端:連線**收到第一則 ping 後武裝 watchdog**;之後自最後一則訊息(含 ping)起 **30 s**(`WS_SILENCE_TIMEOUT_MS`)無任何訊息 → hook 卸掉舊 socket 的 handler 並 `close()`、`wsStatus` 轉 `closed`、依 backoff 排程新連線(不等舊 socket 的 onclose)。**未收過 ping 的連線不武裝**(= 對舊後端 / 不送 ping 的 server 行為與現況完全相同) | (a) `lib/ws-reconnect.test.ts`(fake timers:ping 後 30 s 無訊息 → onClose 回呼 + 新 WebSocket 建立;ping 後 29 s 又收到任一訊息則不觸發;**從未收 ping 時 60 s 無訊息也不觸發**;舊 socket 遲到的 onclose 不再觸發第二次重連;舊世代 watchdog 不得觸發新世代重連);(b) `useTxoSnapshot.test.ts` 整合一條(ping → 30 s → instances+1);(c) 真環境:vite dev proxy 指側車;**先確認 DevTools WS 面板該連線已收到 ≥ 1 則 ping(等 ≥ 10 s)**,再 `POST /_fake/stall?secs=45` 同步阻塞 event loop(TCP 活、零 frame = 半死)→ 最後一則訊息後 **30–36 s**(timeout + 一個 tick)內 helper 觸發:DevTools Network WS 面板見舊連線關閉 + 新連線 pending;badge 序列見 SC-7;阻塞結束 → 新連線 open、badge 回原態;證據 = Network 面板截圖(時間戳)+ badge 兩張 `evidence/SC-2_*.png` + user 過目 |
| SC-3 | ping 不污染資料:8 hook 收到 `{"type":"ping"}` 後 state 不變(特別是 `useTxoSnapshot` 的 `data`) | `useTxoSnapshot.test.ts`「ping 不覆蓋 snapshot」(紅先行:現況會 `setData({type:"ping"})`);helper 測試「ping 不進 onMessage」 |
| SC-4 | backoff 三分支:(i) 存活 ≥ **5 s**(`WS_MIN_UPTIME_MS`)後斷 → 下次 1 s(現況相同);(ii) **有 open 但存活 < 5 s**(accept-then-close / breadth 載入中 scalar)→ 倍增但 cap **5 s**(`WS_SHORT_LIVED_CAP_MS`):1,2,4,5,5,…(engine 起來後最壞多等 5 s);(iii) 從未 open(握手失敗 / server down)→ 倍增 cap 30 s(現況相同) | `lib/ws-reconnect.test.ts`(fake timers 三情境);真環境:側車以 `capital=None` 起 → `/ws/capital` accept-then-close,DevTools Network WS 連線間隔 1,2,4,5,5(截圖 `evidence/SC-4_backoff.png`) |
| SC-5 | onerror 只關自身 socket:舊 socket 的 error 不關新 socket | `lib/ws-reconnect.test.ts`(兩代 FakeWS:第一代 onerror → 第一代 close 被呼叫、第二代未被 close) |
| SC-6 | 契約文件:專案 CLAUDE.md §4 新增「WS 心跳契約」條目(產生點 `copycat/server/ws.py::WS_HEARTBEAT_SECS` / 讀者 `frontend/src/lib/ws-reconnect.ts::WS_SILENCE_TIMEOUT_MS`;timeout 必 > interval,改值同改兩邊) | `grep -n "WS 心跳" CLAUDE.md` |
| SC-7(UI 可指認) | ConnectionBadge(個股頁 / 期貨頁 / 相關係數頁 header 右側膠囊)兩段可觀察序列:watchdog 觸發瞬間(最後一則訊息後 30–36 s)轉「連線中斷,重試中」(warn 色)→ 約 1 s 後(backoff 1 s 重連 → onConnecting)轉「連線中」並維持到 server 恢復 → 恢復後新連線 open、回原狀態文字 | 同 SC-2(c):badge「連線中斷,重試中」截圖(可能只有 ~1 s,以 DevTools 錄影 / 連拍或先把側車 stall 前手動縮短 backoff 不可 — 改以 `console` 時戳 + Network 面板為主證,badge 截圖為輔)+ user 過目 |

量化 SC 量法:SC-1(c) 用 `evidence/sc1_measure.py`(websockets client,印每則 ping 的到達時間差);
SC-2(c) 用 DevTools Network WS 面板時間戳(最後一則 ping 時刻 vs 舊連線關閉 / 新連線建立時刻)。
偵測延遲 = `silenceTimeout` ~ `silenceTimeout + tick`(30–35 s),SC 上界一律寫 36 s。
驗證窗口:無盤中依賴(側車零 ZMQ,任何時段可驗)。

## 2. 不能破壞的既有行為白名單(W)

| # | 行為 | 守門測試 |
|---|---|---|
| W1 | 8 hook 對外回傳 shape 與 `WsStatus` 三態值域不變;`ConnectionBadge` 不動 | 8 hook 既有測試全綠 + tsc |
| W2 | 首則 seed 行為不變:txo `latest_snapshot` / corr `state()` / river `river_snapshot()` / stock watchlist_quote / breadth payload;ping **不會**在首則之前送出 | `test_app.py:122-161`、`test_corr_routes.py:56`、`test_river_routes.py:61`、`test_signal_routes.py:770/873/950`、`test_breadth_routes.py:397-417` |
| W3 | unmount → WS 關閉且不重連(instances 不增) | `useCorrelation.test.ts:125`、`useRiver.test.ts:239` 等既有 |
| W4 | StrictMode 舊 socket 晚到的 close 不清新 socket 的 `wsOpenRef`(useStockStream :448-459 註解語意) | `useStockStream.test.ts` 既有 + helper「stop 後舊 socket 事件全忽略」 |
| W5 | onopen 觸發 refetch(breadth / futures / index / stock)仍發生 | `useBreadth.test.ts:159`、`useFuturesStream.test.ts:162`、`useIndexStream.test.ts:186`、`useStockStream.test.ts:110` |
| W6 | `relay` 斷線偵測(`_recv`)與 `WebSocketDisconnect` 吞法不變;真 uvicorn RST 零 dead-transport 警告 | `tests/server/test_ws_disconnect.py` 全綠 |
| W7 | 8 route 在 engine 缺席時的行為不變(accept-then-close / breadth 載入中 scalar / stock 空流 status seed) | `test_breadth_routes.py:411`、`test_signal_routes.py:770`、`test_capital_api.py`、各 route 測試 |
| W8 | backoff 初值 1 s / cap 30 s / 倍增不變;健康連線斷線 → 1 s 重連 | `useTxoSnapshot.test.ts:52` 既有 + helper 測試 |
| W9 | ping 不經 per-client queue(`WsBroadcaster` 丟最舊邏輯不受影響、queue 不被 ping 佔位) | `test_ws_disconnect.py::TestRelay` 既有 + 設計(ping 由 relay 直送) |
| W10 | `WsConnection` Protocol 不變(ping 走既有 `send_json`),測試 fake 零改動 | pyright + `_FakeWebSocket` 不改 |
| W11 | `useCapitalWsStatus` 的非 Badge 消費者(`useFlashArm.ts:50` `closed` → `conn_lost` 解除武裝;`FuturesLadder.tsx:139/380`、`PriceLadder.tsx:392` lockDisabled)語意不變:`closed` 只在「真的斷線」或「收過 ping 後 30 s 全靜默」出現;**從未收 ping 的連線(舊後端)不會多出任何 closed 邊沿**;已接受的新 closed 來源 = 真靜默 30–36 s(解除武裝是安全方向);主執行緒凍結由 §4.2 防誤判規則擋 | `useCapital.test.tsx` 新增「ping 後 35 s 靜默 → status closed」+「無 ping 時 60 s 靜默仍 open」;`useFlashArm.test` 既有 |
| W12 | 7 hook 在 `connect()` 本體呼叫的 `setWsStatus("connecting")`(含每次重連)保留 → helper 提供 `onConnecting` | `lib/ws-reconnect.test.ts`「重連時 onConnecting 再次觸發」+ 8 hook 既有 |
| W13 | `/ws/stock` hub-only 空流分支(app.py:1740,TC4 down)也收得到 ping(恆無推播的那條流正是心跳最有價值處) | 新測試 `test_ws_stock_hub_only_stream_gets_ping` |

## 3. Backward compat / migration

- 後端 `relay(websocket, stream, *, heartbeat_secs: float | None = None)`:keyword-only 新參數,
  `None` → 讀模組常數 `WS_HEARTBEAT_SECS`(呼叫時讀,測試可 monkeypatch);`<= 0` 停用。8 個 call site 零改動。
- 兩個方向的版本錯位窗口(`[amendment 2026-08-19: spec review R1/R3]`):
  - **新前端 + 舊後端**(dev:`git pull` 後 vite HMR 立即換前端,後端要等手動重啟 → 這是實際會出現的窗口):
    舊後端不送 ping → **watchdog 永不武裝** → 行為 = 現況,零誤重連、零 `closed` 邊沿、閃電下單武裝不受影響。
  - **舊前端 + 新後端**(production build 分頁未重整就重啟後端):舊 `useTxoSnapshot` 會把 `{type:"ping"}` 當
    snapshot `setData` → `App.tsx:343` 的 `snapshot ?` 真值守門過、`snapshot.contracts` undefined → **TXO 頁 render 例外**,
    且 R1(#68)後下一則推播可能要等到有變動。舊 bundle 無法由新 code 補救;dev 模式不會發生(HMR 先換前端);
    處置 = PR 試用指引與 handoff 明寫「**後端重啟後一律重整瀏覽器分頁**」(本就是過目流程),不做 feature flag
    (`[auto-default: 不做相容旗標 | reason: dev 模式零窗口;prod build 尚未採用(R0 待拍板);旗標會讓契約雙態]`)。
- 無資料格式 / 持久化變更,migration 無;可逆 = revert PR。

## 4. 設計決定(`[auto-default]` 清單)

1. 心跳落點 = `relay()` 內第三個 task `_beat`(`asyncio.sleep(secs)` → `send_json(PING)`),與 `_send` 共用一把
   `asyncio.Lock` 序列化 send(不交錯 frame)。**鎖只包住單次 `await websocket.send_json(...)`,不得包住
   `async for` 迴圈或 `await queue.get()`**(否則 `_beat` 永遠等鎖 = 心跳靜默失效;寫進 docstring)。
   **`_beat` 加入 `asyncio.wait({send, recv, beat}, FIRST_COMPLETED)` 集合**,例外分流與 `_send` 完全相同
   (`WebSocketDisconnect` 吞掉 — starlette 對死 transport 的 OSError 已轉成 1006 WebSocketDisconnect;其他例外
   re-raise),`finally` 對未完成的三個 task 一律 cancel + `_consume_ws_task`(不留 unretrieved)。
   `[auto-default: 定時送,不做 idle-only | reason: user 選「定時報平安」;省下的頻寬 ~20 B/10 s 不值得多一條邏輯]`
   `[auto-default: _beat 例外路徑 = _send 同款 | reason: 單一規則;dead transport 在 starlette 層已是 WebSocketDisconnect]`
2. 間隔:後端 10 s、前端 timeout 30 s(3×,容一次 event loop 卡頓)、min-uptime 5 s、short-lived cap 5 s。
   `[auto-default: 10/30/5/5 | reason: uvicorn protocol ping 預設 20/20 s 同量級;30 s = 畫面最多停半分鐘即自癒;5 s 遠大於 accept-then-close 的毫秒級存活;short-lived cap 5 s = boot 期間最壞多等 5 s 接上 seed,同時把 1 Hz 空轉降到 0.2 Hz(spec review R6)]`
   **watchdog 武裝時機(`[amendment 2026-08-19: round-2 R16]`)**:(a) 該連線收到第一則 `{type:"ping"}` 即武裝;
   (b) **sticky**:helper 以 URL 為鍵維護模組層 `Set<string>` 「此 server 會送 ping」,某一代收過 ping 後,同 URL 之後每一代
   **onopen 即武裝**(寬限 = 完整 silenceTimeout)→ 封住「新一代連線在首則 ping 前就半死」的盲區;
   (c) 舊後端從未送 ping → 永不 sticky → 行為 = 現況(R1 相容結論不變)。
   `[auto-default | reason: 對不送 ping 的 server 行為零改變;既有 8 hook 測試從不 emit ping → 既有 fake-timers 測試(useStockStream.test.ts:507 累積 31 s)不受影響;
   殘餘盲區 = 整個分頁生命週期的**第一代**連線在首則 ping 前就半死(永久不偵測,同現況);之後各代由 sticky 涵蓋]`
   測試:gen1 收過 ping → gen2 open 後從未收 ping、30 s+tick 全靜默 → 仍觸發重連;不同 URL 不互相 sticky;測試間 `resetWsPingMemory()`(測試用 export)。
   **凍結防誤判**:tick 同時記 `lastTickAt`;若 `now - lastTickAt > tick * 2`(主執行緒長阻塞 / 機器睡眠 → 8 條 WS 會同時誤判靜默、
   capital 轉 closed 解除閃電武裝)→ 本 tick 只把 `lastMsgAt = now` 重置基準、不判定靜默(`[auto-default | reason: 凍結期間 server 的 ping 不是沒送是沒被處理;
   重置後若真半死,下一個 timeout 仍會抓到]`)。測試:`vi.setSystemTime` 跳 40 s 再跑一個 tick → 不觸發;之後再靜默 30 s+tick → 觸發。
3. 前端共用 helper `frontend/src/lib/ws-reconnect.ts::connectWithRetry(url, handlers, opts?)`,8 hook 全部改吃它
   (`[auto-default: 抽共用 helper | reason: 8 份同款骨架,三個新行為各抄 8 次才是過度;helper 有 8 個具體 caller 不算投機抽象]`)。
   API:
   ```ts
   export const WS_SILENCE_TIMEOUT_MS = 30_000; export const WS_WATCHDOG_TICK_MS = 5_000;
   export const WS_MIN_UPTIME_MS = 5_000; export const WS_SHORT_LIVED_CAP_MS = 5_000;
   export const WS_BACKOFF_START_MS = 1_000; export const WS_BACKOFF_CAP_MS = 30_000;
   export interface WsHandlers { onConnecting?(): void; onOpen?(): void; onMessage(msg: unknown): void; onClose?(): void; }
   export interface WsOptions { label?: string /* console.warn 前綴 */; silenceTimeoutMs?; watchdogTickMs?; minUptimeMs?; shortLivedCapMs?; backoffStartMs?; backoffCapMs? }
   export interface WsHandle { close(): void /* 停止重連 + 關 socket,之後所有回呼不再觸發 */ }
   export function connectWithRetry(url: string | (() => string), handlers: WsHandlers, opts?: WsOptions): WsHandle
   ```
   `WsHandlers` 另含 `onConnecting?(): void`(每次建 socket 前呼叫,含首次與每次重連;承接 7 hook 在 `connect()` 本體的
   `setWsStatus("connecting")`,spec review R4)。
   語意:`onMessage` 收到的是 `JSON.parse` 後的值(parse 失敗 `console.warn(label…)` 忽略);
   `{type:"ping"}` 在 helper 內過濾不進 `onMessage`(但會武裝 / 餵 watchdog)。
   **逐 handler 的世代語意(round-2 R17)**:🔵 階段 `onclose` **只由 `stopped`(= 現行 alive / handle.close())守門,不做世代比對**
   (逐字複刻);`onerror` 關閉包共用 `current`(alias,逐字複刻);`onmessage` 綁該代。🔴 (a) 把 `onerror` 改關自身;
   🟢 watchdog 放棄舊 socket時**主動卸掉它的 onmessage/onclose/onerror**(= 遲到事件不可能再進 helper),不另做世代比對。
   `handle.close()` 後任何舊事件不再觸發回呼也不排重連。
   **`openedAt` 每代獨立(round-2 R14)**:`connect()` 第一行 `openedAt = null`,只有 `onopen` 寫 `Date.now()`。
   **watchdog 實作**:第一則 ping 到達時啟動**單一 `setInterval`**(tick = `WS_WATCHDOG_TICK_MS` 5 s)比對 `lastMsgAt`
   (`onmessage` 只寫一個 `Date.now()`,不做 per-message timer 重排 — 個股 tick 洪流下零 timer churn);
   `now - lastMsgAt > silenceTimeoutMs` → 卸 handler(onmessage/onclose/onerror = null)+ `sock.close()` + 同步走 onClose/重連路徑
   (不等 onclose;Chromium closing-handshake timeout 60 s)。**任何關閉路徑(onclose / watchdog / handle.close())都 clearInterval**,
   舊世代 watchdog 不得觸發新世代重連。偵測延遲 = timeout ~ timeout + tick;測試以 tick 邊界表述(ping 後推進 35 s 觸發;推進 29 s 再一個 tick 不觸發)。
   backoff(三分支,SC-4;**onopen 不再歸零 backoff**,歸零由 onclose 的 lived ≥ minUptime 分支等效達成 — round-2 R15):
   `onclose` 時 `lived = openedAt !== null ? now - openedAt : null`;
   `delay = lived !== null && lived >= minUptime ? start : backoff`;`setTimeout(connect, delay)`;
   `backoff = min(delay*2, lived !== null ? shortLivedCap : cap)`。
4. ping 形狀 `{"type":"ping"}`,不帶 ts(`[auto-default: 無 ts | reason: YAGNI;要時 additive 加欄不破契約]`)。
5. 後端 accept-then-close 8 處**不動**(前端 min-uptime + short-lived cap 已把 1 Hz 降到 0.2 Hz 且復原延遲上界 5 s;
   改 reject-before-accept 會動 breadth 載入中 scalar 契約與多條 route 測試;見 current-state §4)。
6. `WsStatus` 型別現況 = 7 hook 各一份同值宣告 + `types.ts` 一份(spec review R13);**本輪不收斂**(out of scope),
   helper 不引入第 9 份 — 狀態對映由各 hook 自己在 onConnecting/onOpen/onClose 內做。
7. server 端半死偵測:uvicorn 預設 `ws_ping_interval=20 / ws_ping_timeout=20`(protocol-level,已驗 Config 預設)→ 半死連線
   server 端 ≤ ~40 s 由 uvicorn 回收,relay `_recv` 收到 disconnect 收尾;本輪不另做 stale reap(spec review R12,記 §6)。

## 5. Edge cases

1. ping 與推播同一瞬間 → send lock 序列化,兩個完整 frame,順序不保證但各自完整(測:fake WS `sent` 含兩者且 stream 順序保留)。
2. watchdog 觸發時舊 socket 的 `onclose` 60 s 後才到 → 已卸 handler,忽略;不會造成第二次重連(測:helper)。
3. 連線 open 後收過資料,之後後端卡死 → 自最後一則起 30 s 觸發(watchdog 每則訊息 touch)。
4. 慢 client 推播 backlog(`send_json` await drain 卡住)→ `_beat` 等鎖,不疊加 ping;client 那端 watchdog 仍可能觸發重連(正確:它確實收不到東西)。
5. relay 收尾:三個 task(send/recv/beat)都在 `finally` cancel。`_beat` 送出時 client 已斷 → uvicorn 拋 `ClientDisconnected(OSError)`
   → starlette(application_state 仍 CONNECTED 時)轉 `WebSocketDisconnect(1006)` → 吞掉收尾(已驗 starlette/websockets.py:85-89、
   uvicorn protocols/utils.py:10)。uvicorn keepalive timeout 已 `close_sent` 後的 ASGI send 會拋 **`RuntimeError`**(非 OSError)→ relay
   依「其他例外 re-raise」丟出 → uvicorn 印 ASGI traceback:**與現行 `_send` 同款曝險(窗口 = transport.close 到 connection_lost 之間)**,
   本輪接受(僅 log 噪音),以測試 `test_heartbeat_non_disconnect_error_propagates`(`_beat` send 拋 RuntimeError → relay re-raise,同 `_send`)釘住選擇,不寬鬆 catch。
   **半死 TCP 下 `send_json` 不會 raise**(寫入只進核心緩衝)→ 後端**不靠** ping 偵測對端,對端偵測靠 uvicorn protocol ping/pong(§4.7)。
6. `heartbeat_secs<=0` → 不建 `_beat` task,行為 = 現況(測:`sent` 無 ping)。
7. 握手直接失敗(server down):無 onopen → lived 0 → backoff 倍增(現況相同)。
8. vitest fake timers:helper 用 `Date.now()`(`vi.useFakeTimers` 連 Date 一起假),測試可精確推進。
9. dev 下前端先於後端熱更新(新前端 + 舊後端無 ping):watchdog 永不武裝 → 行為 = 現況(§3)。
10. boot 期間 engine 缺席(accept-then-close):重連 1,2,4,5,5,… → engine 起來後最壞 5 s 接上 seed(現況 1 s;SC-4 (ii))。
11. 半死期間 client 每 ~31–36 s 新開一條、舊連線 server 端留到 uvicorn ping timeout(≤ ~40 s)→ 單一瀏覽器後端最多同時 2 條同源連線,不累積。
12. 曾健康(lived ≥ 5 s)→ server down、之後握手連續失敗:`openedAt` 每代重設 → 走「從未 open」分支 2,4,8,…,30(不會退化成 1 Hz;R14 紅測)。
13. 主執行緒凍結 / 睡眠喚醒:tick 間隔 > 2×tick → 重置基準不判定(§4.2);若真半死,下一個 timeout 仍抓到。
14. 分頁第一代連線在首則 ping 前就半死 → 永久不偵測(同現況;§4.2 殘餘盲區,user 知情接受)。
15. `[amendment 2026-08-20: code review A3]` Chrome intensive wake-up throttling(分頁**隱藏** > 5 min → timer 每分鐘一次)下,凍結守門每 tick
    都成立 → watchdog 在隱藏分頁恆不判定(false negative,不會誤殺武裝);回前景後 ≤ 35 s 自癒。看盤分頁常駐可見,接受;記 next-time。
16. `[amendment 2026-08-20: code review A6]` 第三個版本錯位方向:後端**回滾**到無 ping 版而分頁未重整 → sticky Set 已記該 URL 會 ping
    → 每代 onopen 即武裝、35 s 後誤殺(含 capital closed 邊沿)。處置同 §3:後端重啟(含回滾)後一律重整分頁。
17. `[amendment 2026-08-20: code review A7]` server 卡死 > 30 s 後 8 條 WS 在同一 tick 內觸發、1 s 後同時重連 + 4 條 onOpen refetch
    (thundering herd)。真環境兩輪 stall 復原皆即時;不加 jitter,記 next-time 候選。

## 6. Out of scope

- 後端 engine 缺席改 reject-before-accept / 帶 close code;uvicorn `ws_ping_*` 調整;TC4 上游 KeepAlive。
- `/ws/breadth` 加 `enabled` 欄(next-time:506);回補重試期間把進度寫進 payload(next-time:17,本輪心跳已讓「零訊息」不再誤判)。
- ConnectionBadge 文案分態(tc4 down vs ws closed)、`WsStatus` 搬家。
- R4–R6(AudioContext / signals today 阻塞 / memo 邊界)。
- 後端 stale connection reap(uvicorn protocol ping 20/20 已涵蓋,§4.7);7 份 `WsStatus` 重複宣告收斂(記 next-time)。

## 7. Diff 級章節(逐檔;🔴 行為 / 🟢 新功能 / 🔵 重構;順序 🔵 → 🔴 → 🟢)

### 後端(dispatch 包 BE;可與前端包平行,檔案互斥)

| 檔 | 類 | 動什麼 |
|---|---|---|
| `copycat/server/ws.py` | 🟢 | `WS_HEARTBEAT_SECS: float = 10.0`、`PING: dict[str, str] = {"type": "ping"}`;`relay(..., *, heartbeat_secs: float | None = None)`;`_beat` task + `asyncio.Lock`(`_send` 亦取鎖);`finally` cancel 三 task;docstring 補心跳語意與「ping 不經 queue」 |
| `tests/server/test_ws_disconnect.py::TestRelay` | 🟢 `[red]`→`[green]` | `test_heartbeat_ping_when_idle`(0.02 s,等 ~0.07 s,`sent` 含 ≥ 2 則 PING)、`test_heartbeat_preserves_stream_order`(混合推播,非 ping 子序列 = 原順序)、`test_heartbeat_disabled_when_zero`、`test_heartbeat_stops_on_disconnect`(disconnect 後等 3 個間隔 `sent` 不再增)、`test_heartbeat_send_disconnect_ends_relay_cleanly`(`_beat` 的 send 拋 WebSocketDisconnect → relay 正常返回、不 re-raise、無 unretrieved 警告;用 `_RaisingWebSocket` 樣式 fake)、`test_heartbeat_non_disconnect_error_propagates`(`_beat` send 拋 RuntimeError → relay re-raise,同 `_send`;Edge 5);`TestBroadcastRouteDisconnect::test_no_write_to_dead_transport` **fixture 顯式 `monkeypatch.setattr(ws, "WS_HEARTBEAT_SECS", 0)`**(該測試鎖 RST 後零寫入不變式,心跳是無關變因;docstring 寫明)+ 新增一條同 harness、心跳 0.2 s 開啟版本(`test_no_write_to_dead_transport_with_heartbeat`,證 RST 後 ping 不產生 dead-transport 警告;spec review R10) |
| `tests/server/test_signal_routes.py`(或 test_ws_heartbeat.py) | 🟢 | `test_ws_stock_hub_only_stream_gets_ping`:TC4 down(stock None、boot_done、hub 在)連 `/ws/stock`,首幀 status seed(W2)後收到 ping(W13;monkeypatch 0.05 s) |
| `tests/server/test_app.py`(或新 `tests/server/test_ws_heartbeat.py`) | 🟢 | TestClient 連 `/ws/txo-pnl`,`monkeypatch.setattr(ws_mod, "WS_HEARTBEAT_SECS", 0.05)`,首幀仍 snapshot(W2),隨後 `receive_json()` 得 `{"type":"ping"}`(證 route 未傳參也吃模組常數) |
| `CLAUDE.md` §4 | 文件(併 🟢 commit 或獨立 chore) | 新增 WS 心跳契約條目(SC-6) |

既有測試:**全部不該紅**(預設 10 s 遠大於測試取幀時間;`test_forwards_messages_until_disconnect` 精確相等不受影響)。

### 前端(dispatch 包 FE-1 🔵 → FE-2 🔴/🟢;同一 worktree 序列)

| 檔 | 類 | 動什麼 |
|---|---|---|
| `frontend/src/lib/ws-reconnect.ts`(新) | 🔵 | `connectWithRetry` **逐字複刻**現行語意:onConnecting(connect 本體)/ **onopen 歸零 backoff** / onerror 關「閉包共用當前 socket」(**含 alias 缺陷,`sock.onerror = () => current?.close()`**)/ onclose 只由 stopped 守門、倍增重連 cap 30 s / close() 停止;**本 commit 不含** watchdog / ping 過濾 / 三分支 backoff / onerror 修正 |
| `frontend/src/lib/ws-reconnect.test.ts`(新) | 🔵(characterization) | 現行語意鎖定:onConnecting 每次重連觸發、重連倍增、cap、close() 後不重連且舊事件不回呼、parse 失敗忽略,以及**兩條事前標為「該變」的現況鎖**(下一 🔴 commit 翻轉):(1) onerror alias(兩代 socket:第一代 error 關的是第二代);(2) onopen 歸零 backoff(open→立刻 close→1 s→open→立刻 close→仍 1 s) |
| 8 hook(`useTxoSnapshot/useBreadth/useCorrelation/useFuturesStream/useIndexStream/useRiver/useStockStream/useCapital`) | 🔵 | 以 helper 取代自家 `ws/timer/backoff/alive/connect` 骨架;connect 本體的 `setWsStatus("connecting")` → `onConnecting`,onOpen/onMessage/onClose 內容逐字搬入;8 hook 既有測試零改動全綠(限制:既有測試蓋不到 onerror alias / connecting 重發,由 helper characterization 補) |
| `frontend/src/lib/ws-reconnect.ts` + test(+ `useTxoSnapshot.test.ts`) | 🔴 `[red]`→`[green]`(三個獨立 red/green 對) | (a) onerror 關自身(SC-5):翻轉 characterization (1) 的預期為「第一代 error 只關第一代」(事前已標「該變」= 鐵則 E 合法通道);(b) backoff 三分支(SC-4):**移除 onopen 歸零**,翻轉 characterization (2)(事前已標「該變」),紅測 = open 後 <5 s close 連續 → delay 1,2,4,5,5;≥5 s → 1;未 open → 1,2,…,30;**曾 open ≥5 s → 之後連續未 open 就 close → 2,4,8**(R14);(c) ping 過濾(SC-3):紅測 = `useTxoSnapshot.test.ts` emit `{type:"ping"}` → `data` 不變 |
| `frontend/src/lib/ws-reconnect.ts` + test + `useTxoSnapshot.test.ts` + `useCapital.test.tsx` | 🟢 `[red]`→`[green]` | watchdog(SC-2):helper 測 ping 後 35 s 無訊息 → 卸 handler + close + onClose + 新連線;ping 後 29 s 有訊息再一個 tick 不觸發;無 ping 60 s 不觸發;被放棄的舊 socket 遲到 onclose/onmessage 不回呼不重複重連;舊世代 interval 不觸發新世代;close() 清 interval;sticky(gen1 ping → gen2 open 即武裝;跨 URL 不 sticky;`resetWsPingMemory`);凍結防誤判(setSystemTime 跳 40 s);hook 整合:txo(ping→35 s→instances+1)、capital(status closed / 無 ping 仍 open,W11) |

既有前端測試:**全部不該紅**(🔵 階段零改動;🔴 階段新增紅測試,「該變」的 assertion 只有 🔵 列自己新加並事前標記的兩條 characterization:onerror alias、onopen 歸零)。
註:`useTxoSnapshot.test.ts:52`(open→close→1.1 s 重連)在三分支規則下仍綠(lived 0 <5 s → delay = 初值 1 s);
`useStockStream.test.ts:507`(fake timers 累積 31 s)不受 watchdog 影響(測試從不 emit ping → 未武裝)。

### 文件

| 檔 | 動什麼 |
|---|---|
| `docs/superpowers/specs/2026-08-19-browser-crash-scan-handoff.md` | D3 已拍板註記 + R3 標已出貨(收尾時) |
| `docs/next-time.md` | :728「前端 WS 無 heartbeat 判停」勾銷;:17 註記心跳已讓零訊息不誤判(進度欄位仍待);新增「7 份 WsStatus 重複宣告收斂」 |

## 8. 新測試清單(彙總)

後端 TestRelay 5 + RST 心跳版 1 + route 層 2(txo-pnl / stock hub-only);前端 helper(characterization ≥ 6、🔴 3 組、🟢 ≥ 6)+ `useTxoSnapshot.test.ts` 2(ping 忽略 / watchdog 重連)+ `useCapital.test.tsx` 2(W11)。

## 9. 執行約束(沿 handoff / 專案慣例)

- 後端:`from __future__ import annotations`、type hints 全、`logger`、測試 `asyncio_mode=auto`、monkeypatch 不用 unittest.mock。
- 前端:`@/` alias、繁中 warn 文案、vitest colocated、`noUncheckedIndexedAccess`。
- 三類分離 commit;`[red]`/`[green]` 配對;包內 gate 只跑觸及範圍(pytest tests/server/test_ws_disconnect.py + test_app.py;vitest hooks/ + lib/ws-reconnect),全套由 main session 波尾跑。
- 鐵則 E:不改既有 assertion;既有測試紅 = 打到白名單,回頭查。

## 10. Changelog

- 2026-08-20 code review round 1(`code-review-round-1.json`,P0 0 / P1 2 / P2 12):T1/T2/T3/T5/T7 測試補強、T4 事件驅動、A1 🔵 對等修正、A2/A5 🔴 close() 卸 handler + connect 守門、A4/T6 docstring;A3/A6/A7 記 Edge 15–17。

- 2026-08-19 spec review round 2 限縮輪(`change-spec-review-round-2.json`,P0 0 / P1 5 / P2 3,全 accepted):R14 openedAt 每代重設 + 紅測;
  R15 移除 onopen 歸零、🔵 兩條「該變」characterization;R16 sticky per-URL 武裝 + 殘餘盲區如實記;R17 逐 handler 世代語意(🔵 不做世代比對,🟢 卸 handler);
  R18 SC-7 兩段序列 + 證據改 Network 面板為主;R19 Edge 5 機制更正 + RuntimeError 同 _send 接受 + 測試釘住;R20 偵測延遲 30–36 s、測試 tick 邊界;
  R21 驗證先等首則 ping + 凍結防誤判。

- 2026-08-19 spec review round 1(`change-spec-review-round-1.json`):R1/R3 → watchdog 改「收到首則 ping 後武裝」+ §3 兩向窗口重寫 + W11;
  R2 → 同招解(既有測試不 emit ping)+ 註明;R4 → `onConnecting` + W12;R5 → `_beat` 進 wait 集合、例外同 `_send`、Edge 5 改寫;
  R6 → short-lived cap 5 s 三分支;R7 → 🔵 逐字複刻 alias、🔴 翻轉;R8 → setInterval + 清理規則;R9 → 9 call site + W13;
  R10 → RST 測試顯式停心跳 + 心跳版;R11 → 鎖範圍明寫;R12 → §4.7 uvicorn ping/pong;R13 → WsStatus 7 份事實更正。

## 11. self_review_head

- `self_review_head: 298e201f`(code review round 1 + fix 波收斂;2026-08-20)
