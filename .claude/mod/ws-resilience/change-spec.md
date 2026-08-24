# R4 WS 連線韌性批(`mod/ws-resilience`)— change spec

來源:`docs/superpowers/specs/2026-08-24-do-batch-rounds.md` §R4(六條:N035 / N037 / N038 / N034 / N036 / N039)。
前置 grep:前端 8 支 WS hook 全走 `lib/ws-reconnect.ts::connectWithRetry`(零自寫骨架);後端 8 個
accept 點(`app.py` 6 + `capital_api.py` 2)全走 `ws.py::relay`。`WsStatus` 同值宣告 7 份
(useCapital / useCorrelation / useFuturesStream / useIndexStream / useRiver / useStockStream / useTxoSnapshot),
外部讀者 3 處(ConnectionBadge / CorrPanel ← useTxoSnapshot;FuturesPage ← useFuturesStream;useFlashArm ← useCapital)。

## 0. 既有行為白名單(不可破壞;優先於本輪新行為)

| # | 既有行為 | 守住的方式 |
|---|---|---|
| W1 | **onclose 路徑**的 backoff 三分支時序逐毫秒不變(1,2,4,…30 / 短命 cap 5 / 存活 ≥5 s 歸零);jitter 只加在 watchdog 放棄路徑 | `ws-reconnect.test.ts` 既有 backoff 案全數不改 |
| W2 | `{type:"ping"}` 不進 `onMessage`;每則訊息(含 ping)餵狗;`arm()` 冪等只留一顆 interval | 既有案不改 |
| W3 | `handle.close()` 後所有回呼不再觸發、零殘留 timer;watchdog 放棄路徑先卸 handler 再 close | 既有案不改;新增「close() 也拆 visibilitychange listener」 |
| W4 | Edge 13 凍結守門:tick 間隔 > 2×tick 只重置基準不判定(睡醒 / 長阻塞不誤殺) | 既有案不改 |
| W5 | `relay`:`WebSocketDisconnect` 吞掉收尾;**其餘例外一律 re-raise**(不懂的 error 不 catch) | `test_send_error_propagates` / `test_heartbeat_non_disconnect_error_propagates` 不改 |
| W6 | 8 條 route 在 engine **在場**時的 seed / stream 形狀與順序 | 各 route 既有正向測試不改 |
| W7 | `/ws/stock` XR-3 空流:stock 缺席但 boot 已完成且 hub 在 → accept + `status:{tc4:"down"}` seed | `test_signal_routes` 該案不改 |
| W8 | `/ws/txo-pnl` 無 None 分支,行為不動 | 不碰 |
| W9 | 8 hook 對外 shape(`wsStatus` 三值字串、state)不變;`WsStatus` 字面聯集逐字相同 | N034 純搬家,tsc 全綠即證 |
| W10 | 心跳契約值不變:後端 10 s / 前端 30 s + 5 s tick(CLAUDE.md §4) | 常數不動 |

## 1. 逐條處置

### N035 — open 即武裝(🔴 前端)
`sock.onopen` 一律 `arm()`;刪 `pingingUrls` sticky Set 與 `resetWsPingMemory`(3 個測試呼叫點同步刪)。
理由:prod 心跳自 08-20 起穩定跑;sticky 只涵蓋後代,分頁**第一代**連線在首則 ping 前半死永久不偵測的盲區
只有「open 即武裝」封得掉。代價(接受):對**不送 ping 的後端**(舊版 / dev 前端先於後端熱更新),
零流量 30–35 s 會被判半死重連 —— 重連是安全方向,且該情境已不存在於 prod。
事前標記「該變」:`ws-reconnect.test.ts`「從未收過 ping → 永不武裝」「不同 URL 不互相 sticky」「sticky:同 URL 後續世代」、
`useCapital.test.tsx`「從未收 ping:60 s 全靜默仍是 open(W11)」— W11 的舊語意「從未收 ping 的連線不會多出 closed 邊沿」
由本條**明文推翻**(新 closed 來源 = 任何 open 後 30–35 s 全靜默;閃電武裝解除是安全方向,原 W11 已接受同款來源)。

### N037 — visibilitychange 回前景重置(🔴 前端)
Chrome intensive throttling(隱藏 > 5 min)把 5 s tick 拉成 1/min → 每個 tick 都撞 Edge 13 守門(`sinceTick > 2×tick`)
→ 恆重置基準、恆不判定;回前景後第一個 tick 仍被吞,最壞再等 35 s。
處置:武裝期間監聽 `document.visibilitychange`,轉 `visible` 時把 **tick 基準(`lastTickAt`)重設為 now**,
讓緊接的下一個 tick(≤ 5 s)以真實 `lastMsgAt` 判定。**不同步立判**:凍結期間積壓的 frame 要留派發窗口,
否則健康連線會被誤殺(false positive 比 false negative 貴:8 條齊重連 + refetch)。偵測延遲從「≤ 35 s」收成「≤ 5 s」。
listener 隨 `arm()` 掛、隨 `clearWatchdog()` 拆(watchdog 放棄 / onclose / `handle.close()` 三路都經過它);
`typeof document === "undefined"` 時跳過(非瀏覽器環境)。

### N038 — watchdog 放棄路徑加 jitter(🔴 前端)
8 條 WS 對同一顆 server 半死 → 同一 5 s 窗內齊判定、1 s 後齊重連 + 齊 refetch。
處置:`scheduleReconnect(jitterMs)` 只在 **watchdog 放棄路徑**傳 `WS_WATCHDOG_JITTER_MS = 1_000`
(`delay + floor(random() × jitter)`);onclose 路徑 jitter 0(W1)。下一輪 backoff 以**未加 jitter 的 delay** 倍增。
測試:watchdog describe 固定 `Math.random` → 0(既有案時序不動),另一案 0.5 → 1 000 + 500 ms。

### N034 — `WsStatus` 收斂 `types.ts`(🔵 前端)
`src/types.ts` 新增 `export type WsStatus`;7 支 hook 刪本地宣告改 import;3 個外部讀者改自 `@/types` import。零行為。

### N036 — 8 處 accept-then-close 改 reject-before-accept(🔴 後端)
engine 缺席分支移到 `accept()` **之前**:starlette 在 CONNECTING 態送 `websocket.close` = uvicorn 回 HTTP 403 拒握手
(`websockets_impl.py:288`),browser 端 `onopen` 不觸發、直接 onerror/onclose。
- `/ws/breadth`:載入中分支**不再送「載入中 scalar」**(send 需先 accept;REST `/api/breadth/state` 已回同語意 loading 態,
  前端 `useBreadth` 對該 frame 的處理與 REST 同形,無獨立讀者)。兩分支(未 boot / 未設定)皆 reject。
- `/ws/stock`:三旗標(stock / boot_done / signal_hub)改在 accept **之前**同一同步區塊讀 —— 原本「accept 之後讀」是為了
  避免跨 await 的兩時點快照;搬到 accept 之前同樣是單一時點。殘餘 race = 讀到 `stock=None & boot_done=False` 後 boot 恰好
  完成 → 這一代被 reject,client 退避後重連即拿到 seed(與現況同款自癒)。`stock=None & boot_done=True` 是終態
  (XR-3:TC4 從未起 → 要重啟 server),不會被 accept 後的變化推翻。
- `/ws/corr` `/ws/river` `/ws/index` `/ws/capital` `/ws/futures`:`None` 分支前移。
- **已知取捨(向 user 申報)**:前端對「握手失敗」走「從未 open」分支(cap 30 s),對 accept-then-close 走短命 cap 5 s。
  改 reject 後 **boot 期間**的重連節奏由 1,2,4,5,5,… 變 1,2,4,8,16,30,…:server 重啟 → boot ≈ 12.6 s 的常態下
  復原時點兩者同為 ≈ 31 s(短命 cap 要到再下一輪才生效);**boot > 30 s 時最壞多等 ≤ 25 s**。
  收益 = 握手期零 accept/close 往返、uvicorn access log 由每 5 s 一行降到每 ≤ 30 s 一行、
  `wsStatus` 不再閃 `open`。可逆 = revert 8 處(各 3–5 行)。
事前標記「該變」:`test_breadth_routes`「test_engine_absent_closes」「test_before_boot_sends_loading_frame_then_closes」、
`test_corr_routes` / `test_river_routes`「test_closes_when_engine_disabled」、`test_signal_routes`
「test_closes_when_hub_also_none」「test_closes_inside_boot_window」(`_expect_close` 假設 accept 先行 → 改成
`websocket_connect` 進場即拋)。`/ws/capital` `/ws/futures` `/ws/index` 缺席案原本**無測試** → 新增。

### N039 — relay 辨識 close_sent `RuntimeError`(🔴 後端)
窗口:client 斷線 → uvicorn `asgi_receive` 收到 `ConnectionClosed` 先 `closed_event.set()` → `_recv` 拿到 disconnect;
在 `FIRST_COMPLETED` 取消 `_send` / `_beat` 之前,它們若已排入 `send_json` → uvicorn `asgi_send` 落到
「`Unexpected ASGI message 'websocket.send', after sending 'websocket.close' or response already completed.`」
(`websockets_impl.py:349`;sansio / wsproto 同前綴)或 starlette「`Cannot call "send" once a close message has been sent.`」
(`websockets.py:98`)的 `RuntimeError` → relay 依 W5 re-raise → uvicorn 印整段 ASGI traceback(純噪音,連線本來就已斷)。
處置:`ws.py::_is_close_sent_error(exc)` **只認這兩句前綴 / 子字串**;`relay` 收尾與 `_consume_ws_task` 對它視同
`WebSocketDisconnect`(`logger.debug` 一行,不 warning)。其餘 `RuntimeError` 照舊 re-raise(W5 兩條既有測試不動)。

## 2. Backward compat / migration
- 無資料格式、無持久化;前後端可獨立部署:新前端對舊後端 = N035 的已接受代價;舊前端對新後端 = reject 走其 onclose
  重連,無新形狀訊息。可逆 = revert PR。
- 契約文件:`frontend-conventions` skill WS 節的「收到首則 ping 武裝、sticky per-URL、`resetWsPingMemory`」改寫為
  「open 即武裝、visibilitychange 重置、watchdog jitter」;CLAUDE.md §4 心跳契約條**值不變**,只加一句「前端 open 即武裝」。

## 3. 測試 seams
- 前端:`lib/ws-reconnect.test.ts`(helper 層,fake timers + FakeWS)+ `useCapital.test.tsx` 一條翻轉(hook 整合)。
- 後端:`tests/server/test_ws_disconnect.py::TestRelay`(fake WS 注入)+ 各 route 測試(TestClient 進場即拋)。
