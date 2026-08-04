# Bug: `asyncio WARNING socket.send() raised exception.`

- 回報:2026-08-04 11:06:35,962(user 的 prod server console,build 74942ca +dirty,09:26 啟動)
- Branch:`fix/asyncio-socket-send-warning`(worktree `.claude/worktrees/fix+asyncio-socket-send-warning`)
- 嚴重度:P2(不影響行情正確性,但殭屍廣播迴圈持續耗 CPU / 灌 log,每個突斷連線永久留一隻)

## Phase 1|重現步驟(穩定重現,fake source,不碰 TC4)

1. `repro_server.py`(scratchpad):`create_app(FakeQuoteSource, throttle_secs=0.05)` + thread 每 0.1s 推一筆 tick,uvicorn port 8899。
2. `repro_client.py`:raw socket 對 `/ws/txo-pnl` WS 握手 → 收 1 秒訊息(7821 bytes)→ `SO_LINGER(1,0)` + `close()` = **TCP RST 突斷,無 WS close frame**。
3. 觀察 server log。

結果(2026-08-04 11:13):
```
client aborted with RST at 11:13:15
2026-08-04 11:13:15,872 asyncio WARNING socket.send() raised exception.
2026-08-04 11:13:15,973 asyncio WARNING socket.send() raised exception.
...(每次廣播一則)
count(+6s)=56 → count(+11s)=613   ← 無限累積,殭屍迴圈不退場
```

對照組 `repro_client_graceful.py`(同流程但送標準 close frame 1000):**warn count = 0**,
handler 正常退場(close 後 sans-io conn 進 CLOSING,下次 send 觸發 `InvalidState` →
`ClientDisconnected`,`run_asgi` 收掉)。

觸發情境(真實環境):瀏覽器分頁被殺 / vite dev server 重啟(proxy 上游突斷)/
機器睡眠恢復 —— 任何沒有 WS close frame 的 TCP 層斷線。

## Phase 2|Root cause(實驗證明)

三段鏈路,缺一不可:

1. **uvicorn 0.51 `websockets_sansio_impl.py`**:`connection_lost()`(L125)只把
   `{"type": "websocket.disconnect"}` 放進 receive queue,不設旗標;`websocket.send`
   路徑(L436-442)寫 transport 前**不檢查 `transport.is_closing()`**,sans-io 狀態機
   感知不到 TCP 斷線(state 仍 OPEN),`conn.send_text` 不 raise。
2. **asyncio transport**:connection lost 後 `transport.write()` 改為累加 `_conn_lost`
   並丟棄資料,**第 6 次起每次寫都 log** `socket.send() raised exception.`
   (`LOG_THRESHOLD_FOR_CONNLOST_WRITES = 5`;Selector/Proactor 兩實作同文案)。
3. **copycat 六路 WS handler 全是 send-only 迴圈**(`app.py`:`/ws/txo-pnl` L518、
   `/ws/corr` L712、`/ws/river` L736、`/ws/index` L751、`/ws/stock` L764、
   capital_api 的 `/ws/capital` `/ws/futures`):`await websocket.accept()` 後只
   `async for msg: send_json`,**從不 `receive()`** → 永遠收不到 queue 裡的
   disconnect 訊息 → 迴圈永不退場。

結論:**突斷(無 close frame)的 WS client 會在 server 留下一隻永久殭屍廣播迴圈**,
每 tick 對死 transport 序列化 + 寫一次,asyncio 每寫一次 warning 一次。warning 本身
無害(資料被丟棄),但殭屍 handler 是真實資源洩漏(CPU / WsBroadcaster queue 常駐)。

## 修法(main session 拍板)

App 層修(uvicorn 行為是上游設計,版本無關的正解是 handler 要能感知斷線)。
實作時發現 `capital_api.py` 的 `/ws/capital` `/ws/futures` **已有**此樣式
(`_stream_to_ws`,review B3)— 修法即泛化該樣式為 `ws.py relay()` 套到裸的五路:
`copycat/server/ws.py` 加共用 `relay(websocket, stream)` — sender task(原 send 迴圈)
+ watcher task(`websocket.receive()` 直到 disconnect)並跑,`asyncio.wait`
FIRST_COMPLETED,任一完成即 cancel 另一個並 `aclose` stream。六路 handler 全改走它。
`[auto-default: app 層 receive-watcher 共用 helper | reason: uvicorn send 路徑不檢查
is_closing 是上游行為,app 層 watcher 版本無關、同時解掉殭屍 handler 資源洩漏;
patch uvicorn 或逐 handler 各寫 watcher 皆劣]`

## Phase 8|反向驗證輸出(2026-08-04)

- fix HEAD 上只拔 app.py 行為修復(`git checkout a012ee5 -- copycat/server/app.py`,relay 保留)→
  `TestAbruptDisconnect` **FAILED**,log 出現 `WARNING asyncio:proactor_events.py:353 socket.send() raised exception.`
- 還原(`git checkout HEAD -- copycat/server/app.py`)→ `test_ws_disconnect.py` **4 passed in 2.02s**
- 備註:紅 commit 1543972 本身因單元測試 import relay 而 ImportError(收集失敗),
  斷言級的紅以上述手術式還原證明。

## Phase 7|修復後重走重現步驟(2026-08-04 11:32)

同一 repro_server/repro_client(worktree code):RST 後持續推 tick 8s → **warning 0 則**
(修復前同窗口 613 則)。
