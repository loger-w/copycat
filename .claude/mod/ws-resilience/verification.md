# R4 WS 連線韌性批 — verification

分支 `mod/ws-resilience`(自 `5f9d02b0` master 切出)。串行不開 worktree。

## 1. commits(紅 → 綠 → 🔵)

| sha | 類 | 內容 |
|---|---|---|
| `67e463f3` | 🟢 red | 六條 failing test(前端 ws-reconnect 4 + useCapital 1;後端 relay 3 + route 翻轉 6 + 新增 3)+ change-spec |
| `fe92e0b0` | 🔴 green | N035 / N037 / N038 / N036 / N039 實作 + 契約文件(frontend-conventions WS 節、CLAUDE.md §4) |
| `865f496e` | 🔵 refactor | N034 `WsStatus` 7 → 1(`types.ts`),3 外部讀者改 import |

## 2. 紅 → 綠(紅態證據,`67e463f3` 當下)

前端(`ws-reconnect` / `useCapital` / `useTxoSnapshot` 三檔):**4 failed / 29 passed**(ws-reconnect)
- `open 即武裝:從未收過 ping 的連線 30 s + tick 全靜默 → 重連(N035)`(`expected 0 to be 1`:onopen 後無 interval)
- `watchdog 放棄後的重連延遲 = backoff + floor(random × jitter)(N038)`(`WS_WATCHDOG_JITTER_MS` 未定義 → NaN)
- `節流期間半死 → 回前景後下一個 tick(≤ 5 s)就判定重連`(第一個 tick 被凍結守門吞掉)
- `close() / 放棄 / 自然斷線都拆掉 visibilitychange listener`(零 listener)
- `useCapital`「從未收 ping:open 後 35 s 全靜默 → closed」**單獨跑紅**(`-t N035`;全檔跑時被同 URL 的舊 sticky 記憶
  染綠 —— 正是 sticky 語意的副作用,實作拿掉 sticky 後不再有此現象)

後端(七檔):**12 failed / 180 passed**
- relay ×3:`test_uvicorn_close_sent_runtime_error_on_ping_is_swallowed` / `test_starlette_close_sent_runtime_error_on_send_is_swallowed` /
  `test_close_sent_runtime_error_is_not_logged_as_warning`(RuntimeError re-raise)
- route ×9:breadth 2 / corr 1 / river 1 / stock 2 / capital 1 / futures 1 / index 1(`websocket_connect` 進場沒拋 → 先 accept 才 close)

刻意寫下即綠(既有行為 lock,非紅測):`尚未 onopen(握手中)不武裝`、`onclose 路徑不加 jitter(W1)`、
`節流期間訊息照常 → 回前景不重連(W4 對照組)`、`轉 hidden 不觸發判定`。

## 3. 完成前 gate(全綠;`865f496e` 工作樹)

| 指令 | 結果 |
|---|---|
| `.venv\Scripts\python -m pytest -q` | **2919 passed**(exit 0;171.56 s) |
| `.venv\Scripts\python -m ruff check copycat tests` | All checks passed(exit 0) |
| `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings(exit 0) |
| `.venv\Scripts\python -m copycat validate` | **42/42 PASS**(exit 0) |
| `npx tsc -b`(frontend/) | PASS(exit 0) |
| `npx vitest run`(frontend/) | **141 files / 2672 tests passed** |
| `npx eslint src`(frontend/) | PASS(exit 0) |
| `npx react-doctor@latest --scope changed --no-telemetry` | 1 warning `CorrPanel.tsx:6 only-export-components` = **存量**(`out/doctor-baseline.txt:34` 同檔同條,原 line 7,本輪刪一行 import 位移到 6),無新增 → PASS |

### 3b. review 收修波後重跑(SP3 grace / ST1 marker / ST3 / ST5 / ST6 / SP4)

| 指令 | 結果 |
|---|---|
| `pytest -q tests/server/test_ws_disconnect.py tests/server/test_breadth_routes.py` | 43 passed |
| `ruff check copycat tests` / `pyright` | All checks passed / 0 errors |
| `npx tsc -b` / `npx eslint src/lib/ws-reconnect*.ts` | PASS |
| `npx vitest run`(全套) | **141 files / 2674 tests passed**(+2:SP3 兩條紅測試翻綠) |
| `npx react-doctor@latest --scope changed --no-telemetry` | 仍只有存量 `CorrPanel.tsx:6` → PASS |

## 4. 真實環境(2026-08-25 01:11–01:23,零 TC4 / 零 ZMQ / 零群益)

兩台:`--verify` 8722(fake TXO,其餘引擎不起)+ 側車 8899(`evidence/sidecar_server.py`:fake 六源 + `/_fake/stall`,
`neutralize_external_env` 先於 create_app)+ vite 5199(`vite.sidecar.config.ts` 臨時 proxy → 8899,收尾已刪)+ 兩種分頁:Chrome MCP 分頁(hidden,使用者視窗未搶)與 headless=new Chrome(visible,CDP 腳本 `cdp_stall.py` 驅動)。四進程與臨時檔均已收尾(port 8722 / 8899 / 5199 / 9333 已釋放)。
探針 `ws_probe.py`(python websockets,直連 server 不經 vite)。

| # | 項目 | 證據 | 結果 |
|---|---|---|---|
| E1 | **N036 happy**:8722 上 corr / river / index / capital / futures 五條缺席端點 | `evidence/E1_verify8722_probe.txt`:五條 `REJECTED HTTP 403 (t=0.00–0.02 s)`;`E1b_server_logs_403.txt`:uvicorn 印 `"WebSocket /ws/corr" 403` 等五行,零 traceback | PASS |
| E1' | **N036 側車**:8899 capital 缺席、futures / index 在場 | `E2_sidecar8899_probe.txt`:capital 403;futures / index accepted 且 10 s ping 照舊 | PASS |
| E2 | **W7 未改**:8722 `/ws/stock`(stock 缺席、boot 完成、hub 在)仍 accept + `status{tc4,backfilling}` seed + 10 s ping | E1 檔 `ACCEPTED /ws/stock … t=0.0 status … t=10.01 ping` | PASS |
| E3 | **W8/W10 未改**:8722 `/ws/txo-pnl` snapshot 首則 + ping 10.01 / 20.02 / 30.02 s;`/ws/breadth`(引擎在場)accept + seed | 同上 | PASS |
| E4 | **N035 真心跳下零誤重連**:5199 頁(選擇權 tab)patch `window.WebSocket` 計建連,靜置 ≥ 75 s | headless visible 分頁 `E4_E5_headless_visible_tab.txt` IDLE 段(75 s):`warns=[]`、四條 live WS 零重建;Chrome MCP hidden 分頁 `E4_E5_hidden_tab_mcp.txt`(92 s)同結果 | PASS |
| E5 | **N038 jitter**:`POST /_fake/stall?secs=45` 後各 WS 放棄 → 重連時距 | visible 分頁:四條於 17:22:19.211–.305Z 同一 100 ms 窗放棄,`new` 於 +1.042 / +1.371 / +1.529 / +1.560 s(index / futures / stock / txo-pnl)= [1,2) s 抖散;hidden 分頁同實驗四條 `new` 同一毫秒(Chrome 1 s 對齊吞掉 jitter,`E4_E5_hidden_tab_mcp.txt` 註明) | PASS |
| E5b | **N039 真路徑**:側車開 `copycat.server.ws` DEBUG,stall 釋放瞬間 | `E5b_sidecar_debug_after_stall.txt`:`01:22:34,124 copycat.server.ws DEBUG relay 收尾:close_sent 後的遲到 send(RuntimeError('Cannot call "send" once a close message has been sent.'))` **恰好命中一次**;兩輪 stall(`E5_sidecar_log_after_stall.txt` / E5b)`Exception in ASGI application` = 0、收尾 warning = 0 | PASS |
| E6 | **N036 瀏覽器側**:`/ws/capital` `/ws/breadth` 403 → 前端走「從未 open」分支(對照:舊版 accept-then-close 是 1,2,4,5,5) | visible 分頁 `new` 時距 16.01 / 30.01 / 30.01 s;hidden 分頁 9 / 17 / 31 / 31 s(+1 s 對齊)| PASS |

## 5. 白名單(既有行為)逐條核對

| # | 既有行為 | 核對方式 | 結果 |
|---|---|---|---|
| W1 | onclose 路徑 backoff 三分支逐毫秒不變 | 既有 backoff 案未改 + 新增「onclose 路徑不加 jitter」 | PASS |
| W2 | ping 不進 onMessage / 餵狗 / arm 冪等 | 既有案未改(T1/T2、SC-3) | PASS |
| W3 | close() 後零回呼零 timer | 既有 W3 / A2 案未改 + listener 零殘留案 | PASS |
| W4 | Edge 13 凍結守門 | 既有案未改(移回 watchdog describe)+ hidden 對照組 | PASS |
| W5 | relay 其餘例外 re-raise | `test_send_error_propagates` / `test_heartbeat_non_disconnect_error_propagates` 未改 | PASS |
| W6 | 8 route engine 在場形狀 | 各 route 正向測試未改;E1'/E3 真環境 | PASS |
| W7 | `/ws/stock` XR-3 空流 | `test_signal_routes` 該案未改;E2 | PASS |
| W8 | `/ws/txo-pnl` 不動 | E3 | PASS |
| W9 | hook 對外 shape / `WsStatus` 字面 | tsc 全綠、2672 tests 全綠 | PASS |
| W10 | 心跳契約值 | 常數未動;E3 量到 10.01 s | PASS |

## 6. 未做 / 留尾(交還 user)

- N036 取捨:boot > 30 s 時 client 復原最壞多等 ≤ 25 s(change-spec §1 N036 已算);常態 boot ≈ 12.6 s 兩者同 ≈ 31 s。
- N037 的「立判」實作為「回前景後滿一個 tick 的第一個 tick(≤ 5 s + ε)」而非同步判定(review SP3 補上 grace 機制,
  兩條紅測試釘住:逾期 tick 立刻補跑不判定 / grace 內積壓 ping 到達不誤殺)。
- **N037 真環境未驗到觸發條件**(review SP2):需隱藏 ≥ 5 min(intensive throttling)再回前景;本輪唯一可用的 Chrome 分頁
  在 user 視窗內,拉到前景會搶掉盤點頁,headless 分頁又無法模擬 throttling → 只有 fake-timer 證據。
  User 端可觀察的差異:離開分頁 > 5 min 期間若 server 半死,回來後 ≤ 5 s 重連(舊版最壞 35 s)。
- N039 只認 uvicorn / starlette 兩句原文;升版若改字串 → 退回 re-raise(噪音回來,不是靜默失效)。
