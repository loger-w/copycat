# S6 — 訊號推播通道(Discord / WS / 瀏覽器通知)

> 區塊:`S6-notification-channels`
> 準繩:**這是一個要下實單的系統**。訊號通道的價值不在「快」,在「**到不到得了人**」。
> 日期:2026-09-13。工作樹 `C:/side-project/copycat`(唯讀,零改動)。
> 量測環境:Windows 11、Python 3.13.13、專案 `.venv`、node v24.13.0。
> 實測資料來源:`data/signals/*.jsonl`(26 個交易日)、`logs/server-*.log`(79 個 session)、`.env`。

---

## 0. 一句話結論

這一段的 **CPU 成本全部是 µs 級、完全不是瓶頸**(全庫最貴的一格是 `format_policy_group_text`
4.43 µs/則,一天 280 則)。問題全部在**可達性**:

- **實測**:prod 的 `DISCORD_WEBHOOK_URL` **沒有設**(`.env` 逐鍵確認)→ `_send_text` 的兩層
  降級只有一層是活的,bot 送不出去 = 永久遺失。
- **實測**:Discord bot 從 process 起來到 `on_ready` 取到頻道要 **7.9–13.8 s**(n=14,中位 ~11.6 s);
  這段窗內的訊號**一則都到不了 Discord**。09-02 / 09-08 / 09-11 三次盤中重啟各實際損失一則
  (`兩層皆未送出`,其中 09-08 那則是 `limit_lock`)。
- **實測**:開盤 `discord_per_min=30` 的節流在 09-01 / 09-02 / 09-03 / 09-09 共擋掉 **55 則**,
  全部只留一行 WARNING,**永不補送**。09-03 單日 13 則。
- **實測**:`ws 佇列滿` / `訊號 jsonl 佇列滿` / `Discord 佇列滿` 在 79 個 session **零命中** ——
  「丟最舊可能丟掉訊號」這條路**尚未發生過**,但結構仍在,且它壞掉時 toast / 嗶 / 桌面通知
  **沒有任何補救路徑**(rail 有 REST baseline,通知沒有)。
- **新發現(本輪)**:`_send_discord` 的 `len(rows) == 1` 分支**繞過長度檢查也繞過分批** ——
  群組名沒有任何長度上限(`stock_watchlist.normalize` 只驗非空 / 不重複 / 非保留名),
  `/watch group add` 造一個 2000 字群組名就能讓**該群組所有成員的訊號整天送不出 Discord**,
  零錯誤訊號。已用實際程式驗證(單則 text = 2062 字 > Discord 2000 硬上限)。
- **新發現(本輪)**:`bot.close()` 內含 aiohttp `ws_close` 預設 **10.0 s** 逾時,
  而 `shutdown_budget.LIFESPAN_SLACK_SECS` 只給 **5.0 s** 涵蓋「bot.close + hub drain + breadth +
  crosscheck」,`_CLOSE_FLUSH_TIMEOUT` 自己又是 5.0 s。預算**低估 10 s**。健康路徑實測
  signals 段 0.00 s(24 次),所以是尾端風險不是日常。
- **系統沒有任何時戳可以算出「訊號產生 → Discord 出現」的延遲**。jsonl 的 `time` 是 TC4
  tick 時刻,與 server 牆鐘實測**不同步且正負不定**(09-11:tick 時刻比 log 早 3.84 s;
  09-09:晚 6.38 s)。這條端到端延遲**目前不可量測**,本身就是一條 finding。

---

## 1. 現況地圖:三條通道怎麼跑

### 1.1 產生點(單一)

`copycat/server/signal_hub.py::SignalHub._emit`(1012–1040)是**唯一**的訊號產生點:

```python
self._publish(payload)                                   # WS 同步先送(前端要即時)
self._enqueue({**payload, "trade_date": trade_date}, notify=notify)
if event.kind == "sweep_cluster" and event.detail is not None:
    self._emit_policies(event, rule, state, payload, trade_date)   # 政策列走同樣兩條路
```

`_publish` = `app.py:832` 注入的 `stock_ws.publish`,**與個股引擎共用同一顆 `WsBroadcaster`**
(`app.py:554`,`maxsize=_CLIENT_QUEUE_MAX = 1000`,`stock_engine.py:55`)。
所以訊號列與 `ticks` / `book` / `watchlist_quote` / `status` / `stkfut` **共用同一條 per-client 佇列**。

`_enqueue`(1167–1185)扇出兩條**獨立有界佇列**:

| 佇列 | 上限 | 滿載策略 | 受 `notify` 閘影響 |
|---|---|---|---|
| `_jsonl_queue` | 1000 | `_put_drop_oldest` | ❌ 恆入(真相源) |
| `_discord_queue` | 100 | `_put_drop_oldest` | ✅ `notify=False` 不入 |

WS 那一條**沒有閘也沒有佇列**:`publish` 在 `_emit` 裡同步呼叫,`notify` 欄只是隨 payload
帶給前端自己判(CLAUDE.md §4「訊號列 `notify` 欄」契約)。

### 1.2 Discord 通道

```
_discord_queue ──► _discord_worker(單一 task,序列)
                     │ head = get()(或用上一輪存下的 _discord_pending)
                     │ while: get_nowait() 且 _same_tick(row, head) → batch.append
                     │        否則 → 存進 _discord_pending,break
                     ▼
                  _send_discord(batch)
                     ├ 政策批(任一列 kind=="policy"):format_policy_group_text 四行卡
                     │    → 超 1900 字**截斷**送出 → _allow_discord() → _send_text
                     └ 一般批:format_signal_group_text + _group_suffix(同群摘要)
                          ├ len(rows)==1 或 len(text)<=1900 → _allow_discord() → _send_text
                          └ 否則 _split_batches 分批,**每批各計一次節流**
                     ▼
                  _send_text(text, row)
                     ├ bot.send_signal(text) → channel.send(text)   ← 主路
                     └ 回 falsy / 例外 → to_thread(notify_discord)  ← webhook fallback(**prod 未設**)
```

節流 `_allow_discord`(1486–1497):全域(非 per-code)deque,60 s 滑動窗,
`discord_per_min = 30`(`signals_config.py:63`,repo 無 `configs/signals.json` → 全走預設)。
**擋下就是丟**,不重排、不延後。

### 1.3 Discord bot 與主 server 的 loop 關係

`discord_bot.py::Bot.start_bg`(479–488):

```python
self._task = asyncio.create_task(self.client.start(self._token))
self._task.add_done_callback(_log_login_failure)
```

在 lifespan 的 `_start_signals`(`app.py:850`)裡呼叫 → **同一條 event loop**,不是另一條 loop
也不是另一個執行緒。已驗 discord.py 2.7.1 的實際形狀:

| 元件 | 載體 | 數量 |
|---|---|---|
| `client.start()`(login + connect + `poll_event` 迴圈) | 主 loop 上的 **1 個 asyncio task** | 1 |
| `KeepAliveHandler` | **`threading.Thread`(daemon=True)** | 每條 gateway 連線 1 條 |
| 每則 dispatch 的事件 handler(`_schedule_event`) | `loop.create_task`,**只在有 listener 時建** | 本專案只註冊 `on_ready` → 幾乎為 0 |
| aiohttp `ClientSession` + connector | 主 loop | 1 |

**會不會互相阻塞?** 結構上不會 —— discord.py 全 async,`send_signal` 是
`await channel.send(text)`,慢的時候卡住的是 `_discord_worker` 這條 task,不是 `on_tick`
(這正是雙佇列要保護的東西)。而且有一個**免費的 loop-lag 儀器**:`KeepAliveHandler.run`
會在 `run_coroutine_threadsafe(...).result(10)` 逾時時印
`Shard ID %s heartbeat blocked for more than %s seconds` + 主執行緒 traceback。
**實測:79 個 log 檔零命中** → 每 ~41 s 取樣一次的心跳從未撞上 ≥10 s 的 loop 阻塞。

但有兩個非零耦合:

1. `Intents.default()`(`discord_bot.py:578`)含 `guild_messages` / `guild_reactions` /
   `typing` 等。這代表**該 guild 裡任何人打的每一則訊息**都會進 gateway → 解壓 → `json.loads`
   → 建 `Message` 物件,**在下單主機的 event loop 上**。本專案只需要 `guilds`。
2. gateway 重連在 prod 真的會發生:log 共 136 次 `Attempting a reconnect`,
   **集中在每天 05:50–05:54**(推估 = 本機網路 / ISP 夜間重連),一輪 6–7 次退避後
   重新 `on_ready` → `fetch_channel` + `tree.sync`。窗長實測最長 **~3 分鐘**
   (09-12 05:50:51 → 05:54:08)。落在盤中就是 3 分鐘的 Discord 全黑。

### 1.4 `/watch` slash 與 `watchlist_service` 同鎖

`discord_bot.py` 的設計是這一段最好的部分:

- 模組層**不 import discord**,三個 handler 是純 async 函式吃 duck-typed interaction ——
  測試不必裝 extras 就守得住合約(非 vacuous gate)。
- 每個 handler 一進來 `defer(thinking=True)`(`_run`,186–208),避開 Discord 3 秒回應窗。
- `group_choices`(399–437)**不能 defer**(autocomplete 沒有 defer),所以套
  `asyncio.wait_for(service.current(), 1.0)`,逾時 / 例外 / service=None **三態一律回空清單**。
- `WatchlistService` 的鎖範圍在 X-3 之後只到**落檔**為止(`_commit`,209–226),
  ZMQ 訂閱搬到鎖外的 `_settle`。所以 autocomplete 等的是檔案 IO 不是 ZMQ。

**實測鎖內成本**(80 檔 / 12 組的真實自選檔):
`load_watchlist` 76.6 µs、`normalize` 108.4 µs、`save_watchlist`(atomic tmp + replace)
**p50 0.69 ms / p95 0.91 ms / max 1.00 ms**。`/watch` 一天幾次 → **不要動**。

降級三態(`create_bot`,563–573 + `on_ready`,502–527):extras 未裝 / token 未設 / token 空
→ 回 `None`,server 照常起;`SIGNALS_DISCORD_CHANNEL_ID` 未設 / `fetch_channel` 失敗 /
頻道不屬 guild → 只降級不 raise。`.env` 實測:`DISCORD_BOT_TOKEN`(72 字)與
`SIGNALS_DISCORD_CHANNEL_ID`(19 字)**都有設**,所以 prod 走完整 bot 路。

### 1.5 WS 通道 → 前端三條提示路

```
stock_ws.publish(signal payload)
  └► 每個 client 的 asyncio.Queue(maxsize=1000)        ← 與 ticks/book/watchlist_quote 同一條
      └► ws.py::relay._send:async for msg in stream → send_json(msg)   ← per-client 各編碼一次
          └► 瀏覽器 useStockStream.handle: case "signal" → emitSignal(msg)
              └► lib/signal-bus.ts(module-level EventTarget)
                  ├► useSignalAlerts(App 常駐,唯一掛載)  → toast / 嗶 / 桌面通知
                  └► useSignalFeed(**只在 StockPage**)     → rail 清單
```

前端 `notify` 閘(`lib/signal-model.ts:95`):

```ts
export function shouldNotify(sig: SignalMsg): boolean { return sig.notify !== false; }
```

`useSignalAlerts.ts:214` 一行早退 —— **toast / 嗶 / 桌面通知三條同時被擋**。
rail 走 `useSignalFeed`,不經這個閘(契約:jsonl / WS / rail 是真相源,不受 `notify` 影響)。

三條提示路的細節:

| 路 | 觸發 | 節流 / 合併 | 靜音鈕 |
|---|---|---|---|
| toast | 每則 `shouldNotify` 的訊號 | 同 `code\|time` 併入既有那張(TTL 剩餘 ≥ 1500 ms);同時顯示上限 4,其餘 `+N` | 不受 |
| 嗶 | **每新組一聲**;政策列雙嗶(偏移 0.18 s) | 併入既有那張不再嗶 | **受**(`useSignalSound` / localStorage) |
| 桌面通知 | 只在 `document.hidden` | 固定 tag `copycat-signal`(OS 層覆蓋)+ 5 s 節流 + 300 ms trailing 合併窗 | **不受**(刻意:靜音 ≠ 不通知) |

`playBeep` 的 AudioContext 單例處理得很細:`closed` → 回收單例讓下一則重建;
`suspended` → 放棄這一聲並排一發 `resume()`(`resuming` 旗標防 pending 堆積) ——
這兩條都是真踩過的坑(節點不可 GC 整天累積)。**不要動。**

### 1.6 自癒:誰補得回來,誰補不回來

| 消費端 | 斷線 / 丟包後的補救 | 覆蓋範圍 |
|---|---|---|
| jsonl | 無(真相源,只靠佇列不丟) | — |
| Discord | **無**。丟了就是丟了 | — |
| rail(`useSignalFeed`) | `GET /api/stock/signals/today` 5 分鐘輪詢 + WS `onopen` 觸發 `invalidateQueries` | **只在 StockPage 掛載時**;分頁隱藏時輪詢停(`refetchIntervalInBackground` 預設 false) |
| toast / 嗶 / 桌面通知 | **無**。baseline 合併**不回灌 bus** | — |

這張表是本區塊最重要的結構事實:**唯一「人在瀏覽器外也收得到」的通道(Discord)零補救,
唯一「人在瀏覽器內會被打斷」的通道(toast/嗶/通知)也零補救**;有補救的那條(rail)
是三者裡最不緊急的,而且只在個股頁才有。

---

## 2. 端到端延遲預算

> 慣例:**實測**=本輪在本機跑出來的數字;**推估**=從程式形狀 + 已知常數推出來,沒有量到;
> **不可量測**=系統沒有任何時戳可以算。
> Windows 預設 timer 精度 15.6 ms 是抖動地板;下表 µs 級的格子都在地板之下,
> 加總起來的意義是「這一段不是延遲來源」,不是「延遲就是這個數」。

### 2.1 WS 路(訊號產生 → 瀏覽器 toast 出現)

| # | 區段 | 位置 | 成本 | 依據 | 備註 |
|---|---|---|---|---|---|
| 1 | `_emit` 組 18 鍵 payload dict | `signal_hub.py:1014-1036` | ~1–2 µs | 推估 | 同步,在 TC4 quote 的 loop callback 上 |
| 2 | `stock_ws.publish` fanout | `ws.py:65-80` | **0.52 µs**(1 client)/ 0.91(2)/ 1.71(4)/ **3.24**(8) | 實測 | 線性於 client 數 |
| 3 | `relay._send` → `send_json` 的 `json.dumps` | `ws.py:262-265` | **2.08 µs**(訊號 374 B)/ **4.73 µs**(政策 836 B) | 實測 | **per-client 各編一次**(starlette 在 `send_json` 才 dumps) |
| 4 | ASGI send → loopback TCP | uvicorn | < 1 ms | 推估 | 同機 4173→8721 |
| 5 | 瀏覽器 `JSON.parse` | `useStockStream.ts` | **0.674 µs** | 實測(node 24) | |
| 6 | `emitSignal` EventTarget dispatch | `signal-bus.ts:22` | **0.105 µs**(1 訂閱者)/ **0.119 µs**(3) | 實測 | |
| 7 | `shouldNotify` + 合併判定 + `setQueue` + React commit + `beepFor` | `useSignalAlerts.ts:211-269` | < 10 ms | 推估 | 09-03 prod trace:>50 ms long task = 0、最大 36.7 ms |
| — | **WS 路合計** | | **推估 < 10 ms**,遠在 15.6 ms 抖動地板之內 | | 延遲不是問題;**到達率**才是 |

### 2.2 Discord 路(訊號產生 → Discord 訊息出現)

| # | 區段 | 位置 | 成本 | 依據 | 備註 |
|---|---|---|---|---|---|
| 8 | `_put_drop_oldest` 入 Discord 佇列 | `signal_hub.py:1673-1688` | **0.936 µs** | 實測(滿載丟最舊路徑) | |
| 9 | `_discord_worker` 取件 + 相鄰合批 | `signal_hub.py:1198-1234` | ~µs | 推估 | **合批幾乎不發生**:09-11 進佇列 284 列 → 280 則,只省 4(實測) |
| 10 | `_group_suffix` → `engine.quotes()` 掃全自選 | `signal_hub.py:747-779` / `stock_engine.py::quotes` | 0.2–0.5 ms/則 | 推估(150 檔 × 12 鍵 payload) | 只在**非政策**批;≤30 則/分 → ≤15 ms/分。**不是問題** |
| 11 | `format_signal_group_text` / `format_policy_group_text` | `signal_hub.py:171/200/266` | **1.23 / 1.29 / 3.61 / 2.77 / 4.43 µs** | 實測 | 單則 / 單則組 / 3 則合批 / 1 政策列 / 2 政策+1 raw |
| 12 | `_allow_discord` 節流記帳 | `signal_hub.py:1486-1497` | **0.584 µs** | 實測 | `datetime.now()` + deque |
| 13 | `channel.send` Discord REST 往返 | `discord_bot.py:535` | **不可量測** | — | 系統在 `_emit` 與 `_send_text` 都沒有記時戳;jsonl 的 `time` 是 TC4 tick 時刻,與 server 牆鐘實測差 −3.84 s(09-11)~ +6.38 s(09-09),**不能拿來相減** |
| 14 | `to_thread(notify_discord)` webhook 降級 | `signal_hub.py:1564` / `notify.py:75-114` | prod **≈0**(URL 未設即回) | 實測(`.env` 無該鍵) | 若有設:429 路徑 = 快速 429 + `sleep(≤5 s)` + 第二次 `urlopen(timeout=5)` → **單則最壞佔用一格共用 pool thread ~10 s(絕對上界 15 s)** |
| — | **Discord 路可控段合計** | | **< 1 ms** | | 網路那一段佔 ~100%,而它**量不到** |

### 2.3 通道可用性(這才是真正的「延遲」)

| # | 區段 | 成本 | 依據 |
|---|---|---|---|
| 15 | **server 起動 → Discord bot 就緒**(此窗內 Discord 零送達) | **7.9 / 8.1 / 8.9 / 10.6 / 10.7 / 11.2 / 12.0 / 12.8 / 13.1 / 13.2 / 13.2 / 13.8 s**(n=14,中位 ~11.6 s) | **實測**(log:process 首行 → `Discord bot 就緒`) |
| 16 | **gateway 重連窗**(退避 0.04–91.6 s,一輪 6–7 次) | 最長 **~3 分鐘**(09-12 05:50:51→05:54:08) | **實測**(136 次 `Attempting a reconnect`) |
| 17 | **節流阻斷**:開盤 60 s 窗內第 31 則起全丟 | 09-01 ×1 / 09-02 ×7 / 09-03 ×13 / 09-09 ×7(+1 合併批)= **55 則** | **實測** |
| 18 | WS 靜默 watchdog → 重連(toast/嗶/通知全黑窗) | 靜默 30 s + 退避 1–30 s ≈ **31–60 s** | 依 `ws-reconnect.ts` 常數 推估 |
| 19 | 關機 signals 段 | 健康路徑 **0.00 s**(24 次實測);最壞 `bot.close()` 10 s(aiohttp `ws_close`)+ `_CLOSE_FLUSH_TIMEOUT` 5 s = **15 s**,而預算只給 5 s | 實測 + 常數推算 |

### 2.4 REST baseline(rail 自癒通道)

| 區段 | 成本 | 依據 |
|---|---|---|
| `read_signals` 讀 + 逐行 `json.loads`(09-11:686 列 / 282 KB) | **p50 3.44 ms / p95 5.18 ms**,在 `to_thread`(共用 executor) | 實測 |
| 出站 JSON 編碼 | **1.33 ms**,**293 KB** | 實測 |
| 頻率 | 每 5 分鐘 × 每個掛載中的 StockPage 分頁(分頁隱藏時停) | 程式 |
| 單日流量 | ~3.5 MB/hr/分頁(且隨當日訊號數單調成長) | 推算 |

---

## 3. 失效模式表

> 「零錯誤訊號」= 使用者與系統畫面上看不出任何異常;最多只有一行 server log。

| # | 失效 | 觸發 | 症狀 | 零訊號? | 現在怎麼發現 | 嚴重度 |
|---|---|---|---|---|---|---|
| F1 | **啟動窗 Discord 全損** | server 起動後 7.9–13.8 s 內有訊號 | 那幾則只有 WS/jsonl,Discord 什麼都沒有 | 是(僅 3 行 WARNING) | `grep 兩層皆未送出 logs/` | **critical**(盤中重啟是常態,09-08 損失的正是 `limit_lock`) |
| F2 | **webhook 降級層是死的** | `DISCORD_WEBHOOK_URL` 未設(prod 現況) | 任何 bot 失敗 = 永久遺失 | 是 | `grep DISCORD_WEBHOOK_URL 未設定 logs/` | **critical** |
| F3 | **開盤節流丟角** | 60 s 內 > 30 則(開盤實測 32–45) | 開盤最重要的那幾則到不了 Discord | 是(僅 WARNING) | `grep 每分鐘上限 logs/` | **high** |
| F4 | **超長單則被 Discord 退回** | 群組名無長度上限;`_send_discord` 的 `len(rows)==1` 分支不檢查也不分批 | 該群組**所有成員**的訊號整天送不出 | 是 | `grep 兩層皆未送出` | **high**(已用程式驗證:2062 字) |
| F5 | **gateway 重連窗全黑** | 網路 flap(實測每天 05:50 一輪) | 最長 ~3 分鐘零 Discord | 是(只有 discord.py 的 ERROR) | `grep "Attempting a reconnect" logs/` | high(目前都落在盤外) |
| F6 | **WS 丟最舊丟掉訊號列** | per-client queue(1000)在慢 client 上溢位 | toast / 嗶 / 桌面通知**永久消失**;rail 只在個股頁才補得回 | 是 | `grep "ws 佇列滿" logs/` | medium(**79 session 零命中**,結構在但未發生) |
| F7 | **toast/嗶/通知無 baseline** | 任何 WS 缺口(重連 31–60 s、分頁睡著、丟包) | 人完全不知道錯過了什麼 | 是 | 無 | **high** |
| F8 | **rail baseline 只在個股頁** | 使用者停在期貨 / 台股綜合 tab | 連 rail 都沒有自癒 | 是 | 無 | medium |
| F9 | **關機預算低估 10 s** | `bot.close()` 撞 aiohttp `ws_close` 10 s 逾時 | `run.ps1` 在 hub 還沒落檔時 taskkill → 佇列裡的訊號列遺失 | 是(被殺就連 `關機落檔逾時` 都印不出來) | `grep 關機收尾` 看 signals 段秒數 | medium(健康路徑實測 0.00 s ×24) |
| F10 | **節流配額被失敗的送出吃掉** | `_allow_discord` 在 `_send_text` **之前**就 append | bot 全掛時仍每分鐘只允許 30 次嘗試,恢復後不補 | 是 | 無 | low |
| F11 | **`_discord_pending` 單槽在關機被丟** | 關機時槽內有一則 | 那則 Discord 永遠不送 | 否(有 `關機丟棄 Discord` INFO) | `grep 關機丟棄 Discord`(79 session 零命中) | low(設計如此,刻意) |
| F12 | **`Intents.default()` 引入外部負載** | bot 所在 guild 有人聊天 | 下單主機的 loop 解每一則 guild 訊息 | 是 | 無 | low |
| F13 | **`tree.sync` 每次 on_ready 重跑** | 每次完整重連 | 燒 Discord application-command 配額 | 是 | `grep "Discord bot 就緒"`(單 log 最多 3 次) | low |
| F14 | **`_allow_discord` 用牆鐘** | NTP 回跳 / 對時 | 節流窗一次性錯算 | 是 | 無 | low |
| F15 | **baseline payload 單調成長** | 當日訊號累積 | 13:30 時每 5 分鐘 293 KB × 分頁數 | 否(Network 面板看得到) | DevTools | low |

---

## 4. Findings(詳表見 structured output;此處只列程式證據)

### N1 `_send_text` 的第二層在 prod 是空的(critical)

`signal_hub.py:1549-1570`:
```python
sender = self._discord_sender
if sender is not None:
    ...
    logger.warning("Discord bot 未送出 %s,改走 webhook", row.get("id"))
ok = await asyncio.to_thread(self._notify_fallback, text)
...
if not ok: logger.warning("Discord 兩層皆未送出 %s(WS/jsonl 不受影響)", row.get("id"))
```
`notify.py:87-89`:`url = resolve_webhook_url(); if url is None: logger.info(...); return False`。
`.env` 實測沒有 `DISCORD_WEBHOOK_URL` → **第二層恆 False**。
prod 實證三次:`2026-09-02 09:01:11`、`2026-09-08 09:23:26`、`2026-09-11 09:05:19`。

### N2 bot 就緒前的訊號無條件遺失(critical)

`discord_bot.py:529-533`:
```python
async def send_signal(self, text: str) -> bool:
    channel = self._channel
    if channel is None:
        return False
```
`self._channel` 只在 `on_ready` 才被指派(519)。`_start_signals`(`app.py:855-858`)在
`bot.start_bg()` 之後**立刻** `hub.attach_discord(bot.send_signal)`,而 `stock.attach_signal_hub(hub)`
是同一函式的最後一行 —— 熱路徑在 bot 就緒**之前**就已經接上。
實測窗 7.9–13.8 s(n=14)。窗內的訊號連「稍後重試」都沒有。

### N3 開盤節流把最有價值的訊號丟掉(high)

`signal_hub.py:1486-1497` + `signals_config.py:63`(`discord_per_min: int = 30`)。
擋下的處置是 `return`,**不排隊、不延後、不補送**。

實測(從 jsonl 重建合批後的則數,與 log 交叉驗證):

| 日期 | Discord 佇列合批後則數 | 單分鐘最大 | 被擋(log 實數) |
|---|---|---|---|
| 09-01 | 230 | 34 | 1 |
| 09-02 | 513 | 37 | 7 |
| 09-03 | 596 | 45 | 13 |
| 09-09 | 339 | 34 | 7(+1 合併批) |
| 09-11 | 280 | 13 | 0 |

09-09 的時間線可逐則對上:09:00:07 起 32 則在 44 秒內湧入,第 31 則
(`5475 surge @09:00:51`)正是 log 裡 `Discord 節流擋下合併 2 則` 點名的那一則。

**Discord 對 bot 送訊息到同一頻道的實際限制是 5 req / 5 s(= 60/min),
而 discord.py 的 `HTTPClient` 自己會處理 429 並等待。** 也就是說
`discord_per_min = 30` 是**純粹自我設限造成的遺失**,不是在保護誰。

### N4 `len(rows)==1` 分支繞過長度檢查與分批(high,本輪新發現)

`signal_hub.py:1520-1527`:
```python
suffix = self._group_suffix(head)
text = format_signal_group_text(rows) + suffix
if len(rows) == 1 or len(text) <= _DISCORD_MAX_CHARS:
    if not self._allow_discord(): ...; return
    await self._send_text(text, head)      # ← 單則:不管多長都直接送
    return
batches = _split_batches(rows, suffix)
```
政策卡那一半**有**截斷(1512-1516),一般批這一半沒有。

群組名沒有任何長度上限:`stock_watchlist.py::normalize:142-145` 只驗
「非空 / 不重複 / 不是保留名」。`discord_bot.py` 有 `_CHOICE_NAME_LIMIT = 100`
但那只用於 autocomplete 過濾(427-433),**不擋建立**;`_REPLY_LIMIT = 1900`
只截斷**回覆文字**,所以 `/watch group add <2000 字>` 的回覆看起來完全正常。

實際驗證(本輪執行):
```
單則 text 長度 = 2062       # 2000 字群組名 + 一個同伴
走 len(rows)==1 分支? True
_DISCORD_MAX_CHARS = 1900  Discord 硬上限 2000
```
後果:`channel.send` 拋 → `send_signal` 回 False → webhook(未設)→ **該群組所有成員的
訊號整天送不出 Discord**,而 WS / rail / toast 全部正常。

### N5 toast / 嗶 / 桌面通知沒有任何補救路徑(high)

`useSignalAlerts.ts:211`:`const off = onSignal((sig) => {...})` —— **唯一**輸入是 bus。
`useSignalFeed.ts:218`:`useEffect(() => onSignal(...))` 也訂 bus,但它另有 baseline;
而 baseline 合成的結果 **不回灌 bus**(`mergeSignals` 只進 `signals` 回傳值)。

所以:WS 有任何缺口(丟最舊 F6、靜默重連 31–60 s、分頁睡著、machine sleep),
rail 補得回、**toast / 嗶 / 桌面通知補不回**,而後三者才是「打斷人」的那一條。

量化 F6 的窗:per-client queue 1000;stock 通道的尖峰訊息率 =
`watchlist_quote` 1 Hz 突發(`_flush_watchlist_loop`,`stock_engine.py:1813-1830`,
dirty 集合逐檔一則 → 最多 150 則/秒)+ `ticks` ≤10/s + `book`(主圖每則 quote)。
→ **client 停頓 ~5–7 秒就開始丟最舊**,而不是天真估的 33 秒。
實測 79 session `ws 佇列滿` 零命中,所以這是結構風險不是現況問題。

### N6 rail baseline 只在 StockPage(medium)

`grep` 結果:`useSignalFeed` 的唯一非測試 caller 是 `components/stock/StockPage.tsx:92`。
`useSignalAlerts` 的唯一 caller 是 `App.tsx:163`。
→ 人停在期貨 tab / 台股綜合 tab 時,瀏覽器端**只剩 WS bus 這一條**,零補救。

### N7 關機預算低估 bot.close 的 10 秒(medium)

`shutdown_budget.py:41-43`:
```python
#: TC4 之外的段(crosscheck cancel / breadth / signals 的 bot.close + hub drain)…
LIFESPAN_SLACK_SECS: float = 5.0
```
而 `_close_signals`(`app.py:867-876`)先 `await bot.close()` 再 `await hub.close()`;
`Bot.close`(`discord_bot.py:490-500`)→ `discord.Client.close` → `await self.ws.close(code=1000)`
→ aiohttp `ClientWebSocketResponse.close` 的 `self._timeout.ws_close`,
**實測預設值 `ClientWSTimeout(ws_receive=None, ws_close=10.0)`**。
`hub.close` 的 `_CLOSE_FLUSH_TIMEOUT = 5.0`(`signal_hub.py:109`)本身就已經等於整個 slack。
→ 最壞 15 s vs 預算 5 s。實測健康路徑 signals 段 **0.00 s**(24 次 `關機收尾` 行),
所以是尾端風險;但 `run.ps1` 硬殺時連 `關機落檔逾時` 那行都印不出來 = 零訊號。

### N8 合批機制幾乎沒有作用(low,診斷用)

`_discord_worker` 的單槽合批設計本身正確(不回塞佇列以免順序亂),
但實測 09-11 進 Discord 佇列 284 列只合成 280 則 —— **省 4 則(1.4%)**。
26 個交易日總計:進佇列 7056 列 → 6851 則,省 205(2.9%)。
原因:`_same_tick` 要求同 `code` 且同**秒**,而不同檔的訊號幾乎不會同秒同碼。
→ 合批不是省 Discord 配額的有效手段,**解節流問題不能指望它**。

### N9 `Intents.default()` 比需要的寬(low)

`discord_bot.py:575-580` 用 `discord.Intents.default()`,含 `guild_messages` /
`guild_reactions` / `typing`。本專案只需要 `guilds`(`fetch_channel` 解 guild + slash
指令走 INTERACTION_CREATE,不需要任何 privileged / message intent)。
現況代表該 guild 的每一則聊天訊息都要在**下單主機的 event loop** 上解壓 + `json.loads` +
建 `Message` 物件。`allowed_mentions=AllowedMentions.none()` 那一行(mention 擴音器防護)
寫得很好,**不要動**。

### N10 節流配額在送出**之前**就被消耗(low)

`_allow_discord` 的 `self._discord_sent.append(now)` 在 `_send_text` 之前(1496)。
bot 全掛時每一次失敗的嘗試仍占一格,恢復後也不補。與 N3 疊加。

### N11 `format_policy_group_text` 的政策卡有截斷保護(反向:寫對了)

`signal_hub.py:1512-1516` 明確處理超長 → 截斷 + WARNING,理由寫在註解裡
(「截斷留痕,不讓整張卡被 Discord 退回而只剩一句『兩層皆未送出』」)。
**N4 要修的就是把這一半的處置搬去另一半。**

### N12 `_put_drop_oldest` / 雙佇列 / `task_done` 記帳(反向:寫對了)

`signal_hub.py:1673-1688` + `_discord_worker` 的 `finally: for _ in batch: task_done()`。
少記一格 → `join()` 永不返回(關機吊死);多記一格 → `task_done() called too many times`
當場打死 worker(之後整天 Discord 無聲而 WS/jsonl 正常)。註解已寫明兩種失效都不指向這裡。
**不要動。**

### N13 `ws.py::relay` 的三 task + 心跳 + close_sent 辨識(反向:寫對了)

`_send` / `_recv` / `_beat` 三 task + `FIRST_COMPLETED`;`send_lock` 明確**不**包住
`async for` 迴圈(包了就是心跳靜默失效);`_CLOSE_SENT_MARKERS` 以原文辨識 uvicorn /
starlette 的 close_sent `RuntimeError`。這是全庫少數把「半死 TCP」處理對的地方。
**不要動。**

### N14 `playBeep` 的 AudioContext 生命週期(反向:寫對了)

見 §1.5。`closed` 回收單例 + `suspended` 單發 resume + `resuming` 旗標,
三個都是真踩過的坑。**不要動。**

### N15 端到端 Discord 延遲不可量測(medium,量測缺口)

`_emit` 不記單調時戳,`_send_text` 送出後也不記。jsonl 的 `time` 是 **TC4 tick 時刻**,
與 server 牆鐘實測不同步:
- 09-11:id 時刻 `09:05:23.000`,log `09:05:19.156`(tick 比牆鐘**早** 3.844 s)
- 09-09:id 時刻 `09:00:51.000`,log `09:00:57.384`(tick 比牆鐘**晚** 6.384 s)
- 09-02:id 時刻 `09:01:05.000`,log `09:01:11.845`(晚 6.845 s)

正負不定 → **不能用兩者相減當延遲**。要回答「訊號到 Discord 幾秒」必須新增
一個 `time.monotonic()` 起點。

### N16 `/api/stock/signals/today` 每 5 分鐘重送當日全量(low)

實測 09-11 全量 686 列 / 出站 293 KB / 編碼 1.33 ms / 讀 p50 3.44 ms。
其中 402 列(59%)是 `notify=false` 的 quiet 列(CDP 穿越 / 爆量 / raw 掃單簇)。
讀在共用 executor(鄰居是不可中斷的 TC4 20 s 取數)→ baseline 可被餓 20 s。
不是效能問題,是「自癒通道本身可被上游卡住」的耦合。

### N17 `engine.quotes()` 為了一個欄位建 150 份完整 payload(low,不建議動)

`stock_engine.py::quotes` 對每個自選碼呼叫 `_quote_payload(code)`(12 鍵 dict +
`_trial_now` + `_disposition_now`)只為了取 `chg_pct`。在 `_group_suffix` 裡每則
**非政策** Discord 訊息各一次。推估 0.2–0.5 ms/則 × ≤30/分 = ≤15 ms/分。
**這不是效能問題**;而且 `chg_pct` 走唯一定義(除權息日分母是 `ref_milli`)是刻意的,
抽出來重算會製造第二份會漂的算式。**不要動。**

### N18 `handle_*` 的 `except Exception` 指令邊界(反向:寫對了)

`_run`(186–208)把例外轉成明確文案 + `logger.exception`,理由是「handler 拋出去只會被
discord.py 記在它自己的 log,使用者停在『思考中』永遠等不到回覆」。這是 CLAUDE.md §E
「不懂的 error 不要 catch」的**正當例外**(指令邊界),註解已寫明。**不要動。**

### N19 `group_choices` 的三態回空 + 1 s 逾時(反向:寫對了)

autocomplete 不能 defer(Discord 3 s 硬窗),且與寫入共用同一把鎖。回空清單讓使用者
仍可手打群組名。X-3 之後鎖內只剩檔案 IO(實測 save p95 0.91 ms),1 s 逾時是充裕的
防禦縱深。**不要動。**

### N20 前端 `notify` 閘一行擋三條路(反向:寫對了,但要知道涵蓋面)

`useSignalAlerts.ts:214` 的 `if (!shouldNotify(sig)) return;` 同時擋 toast / 嗶 / 桌面通知,
而 rail 走另一條。這與 CLAUDE.md §4 契約逐字一致(`notify !== false`,缺欄視為 true)。
**不要動**,但改 `notify` 語意時要記得它一次動三條路。

---

## 5. 改造順序 + 量測判準

> 原則:**先把「量不到」補上,再改「會丟」的**。每一步的判準都要是盤後 grep 得到 /
> curl 得到的具體字串或數字,不是「看起來正常」。
> 全部都是 🔴 行為改動,依 CLAUDE.md §B 分開 commit。

### 步驟 1 — 設 `DISCORD_WEBHOOK_URL`(零程式改動)

**為什麼排第一**:一行 `.env`,把 N1 的第二層點亮,立刻讓 F1 / F4 / F5 三個 critical/high
失效模式從「永久遺失」降級成「webhook 送達」。不改任何程式 = 零回歸風險。

- **判準**:`python -m copycat notify-test` 回 True 且 Discord 頻道看得到;
  下次盤中重啟後 `grep "兩層皆未送出" logs/server-*.log` **零命中**,
  而 `grep "Discord bot 未送出" logs/` 仍有(代表確實走了降級且成功)。
- **回退**:刪掉那一行 env。
- **工作量**:S

### 步驟 2 — 在 `_emit` 記單調時戳,`_send_text` 送出後記延遲(可觀測性)

**為什麼排這裡**:N15。**先量後改** —— 沒有這個數字,步驟 4 的節流調整無法驗證,
而且「Discord 慢」與「Discord 沒送」現在完全不可分辨。

做法:payload 之外掛一個 `_t0 = time.monotonic()`(不進 wire,不改契約),
`_send_text` 成功後 `logger.info("Discord 送達 %s 延遲 %.2fs", row_id, dt)`,
或更省:只在 `dt > 5.0` 時 WARNING + 每日彙總一行 p50/p95。

- **判準**:盤後 `grep "Discord 送達" logs/server-<今日>*.log | wc -l`
  ≈ 當日 `jsonl` 中 `notify != false` 的合批後則數(容差 ±5);
  彙總行印得出 p50 / p95 / max。
- **回退**:移除 log 行(純新增,無行為改動)。
- **工作量**:S

### 步驟 3 — 修 N4:單則超長走截斷,與政策卡同一套處置

**為什麼排這裡**:一個 `/watch group add` 就能讓整個群組整天靜默,且完全零訊號。
修法是把 1512–1516 那五行的處置搬到 1520 的分支前,**不動分批邏輯**。

```python
# 現況(1520):
if len(rows) == 1 or len(text) <= _DISCORD_MAX_CHARS:
# 應為:len(rows) == 1 時先截斷再送(與政策卡同式),len(text) 檢查照舊
```
另加一道源頭閘:`stock_watchlist.normalize` 對 `name` 加長度上限(建議 40,
與 `_CHOICE_NAME_LIMIT = 100` 對齊或更嚴),`WatchlistError("BAD_GROUP")`。
⚠ **這會動到跨檔契約**:前端 `useStockWatchlist.errText` 與
`discord_bot._ERROR_TEXT["BAD_GROUP"]` 的文案要一起看(值域不變,只是新增一個拒絕理由)。

- **判準**:
  (a) 新增測試:單則 row + 2000 字 suffix → `_send_discord` 送出的 text 長度 ≤ 1900 且
      log 有「截斷送出」;突變體(把截斷拿掉)必紅。
  (b) `normalize` 對超長名 raise `BAD_GROUP`;現有 `data/stock_watchlist.json` 的 12 個
      群組名全部通過(`python -c` 逐名長度列印,最長 < 上限)。
  (c) `pytest -q` + `npm test` 全綠。
- **回退**:revert 兩個 commit(截斷 / 長度閘各一筆)。
- **工作量**:S

### 步驟 4 — 節流從「丟」改成「延」

**為什麼排這裡**:N3 實測 55 則永久遺失,全部在開盤最重要的 60 秒。
`_discord_pending` 的單槽機制已經存在(順序保證),改成:節流擋下時
把 batch 放回 pending 並 `await asyncio.sleep(下一格釋出的秒數)`,不 return。
佇列滿(100)時仍丟最舊 —— 有界,不會無限堆。
同時把 `discord_per_min` 從 30 提到 **50**(Discord 對 bot 的頻道限制是
5 req/5 s = 60/min,且 discord.py 自己處理 429;50 留 10 的餘裕)。

⚠ 若步驟 1 之後 webhook 成為主要路徑要注意:**webhook 的限制是 30/min**,
與 bot 的 60/min 不同。所以 `discord_per_min` 提高的前提是 bot 為主路(現況如此)。

- **判準**:
  (a) 下一個開盤日盤後 `grep "每分鐘上限" logs/server-<日>*.log` **零命中**;
  (b) 同日 `grep "Discord 送達" | wc -l`(步驟 2 的那行)= jsonl 合批後則數,**零缺角**;
  (c) 步驟 2 的 p95 延遲 < 60 s(延遲換到達,但不能延到失去意義);
  (d) `grep "Discord 佇列滿" logs/` 仍為 0。
- **回退**:`configs/signals.json` 把 `discord_per_min` 改回 30 + revert worker 那一筆。
- **工作量**:M

### 步驟 5 — bot 未就緒時**排隊**而不是丟

**為什麼排這裡**:N2 / F1。步驟 1 之後 webhook 會接住,但 webhook 是次級通道
(沒有四行卡的頻道上下文、格式不同)。正解是 `send_signal` 在 `_channel is None` 時
不要立刻回 False,而是 `await asyncio.wait_for(self._ready_event.wait(), <=15)`;
`on_ready` 設 event。超時才回 False 走 webhook。
實測就緒窗 7.9–13.8 s → 15 s 上限涵蓋觀測到的全部樣本 + 餘裕。

- **判準**:
  (a) 盤中重啟後 `grep "兩層皆未送出" logs/` 零命中,且 `grep "Discord bot 未送出"` 也零命中
      (代表真的等到了而不是降級);
  (b) 步驟 2 的延遲 log 在重啟後首則顯示 8–14 s(等待是真的,不是假裝);
  (c) 新增測試:fake channel 延後 3 s 就緒 → `send_signal` 回 True 且不走 fallback;
      突變體(拿掉等待)必紅。
- **回退**:revert 該筆(`send_signal` 回到 `if channel is None: return False`)。
- **工作量**:M

### 步驟 6 — toast / 嗶 / 桌面通知補上 baseline 回灌

**為什麼排這裡**:N5 / N6 / F7。前五步都在修 Discord;這一步修**瀏覽器這一半**。
做法:`useSignalFeed` 在 baseline refetch 完成後,把 **本次新出現且 `shouldNotify`
且時刻在最近 N 分鐘內** 的訊號回灌 bus(或改由 `useSignalAlerts` 自己掛一條 baseline
輪詢)。必須帶「已提示過」的 id 集合去重,否則每 5 分鐘整片重響。
同時把 `useSignalFeed` 從 StockPage 提到 App(與 `useSignalAlerts` 同層),
讓期貨 / 台股綜合 tab 也有自癒。

⚠ 這一步會改變「同一則訊號最多提示幾次」的語意,**需 user 拍板**
(HITL:這是決策不是事實)。

- **判準**:
  (a) 新增測試:模擬 WS 斷 40 s 期間後端產生 3 則 `notify=true` 訊號 → 重連後
      toast 出現 3 張且**不重複**;
  (b) 連續兩次 baseline refetch 且無新訊號 → toast 數量不變(去重有效);
  (c) `npm test` + `npx tsc -b` + `npx eslint src` + `react-doctor --scope changed` 無新增 finding。
- **回退**:revert 前端那一筆(純前端,後端零改動)。
- **工作量**:L

### 步驟 7 — `bot.close()` 加逾時,或把 slack 加到 15 s

**為什麼排這裡**:N7 / F9。低機率(實測 24 次全 0.00 s)但修法便宜:
`await asyncio.wait_for(self.client.close(), 3.0)`(3 s 足以涵蓋健康路徑的 0.00 s),
逾時就放棄(daemon thread 會隨 process 收掉)。
**不要**改 `LIFESPAN_SLACK_SECS` —— 那會連帶把 `run.ps1` 的 graceful 窗拉長 10 s,
而 `tests/server/test_shutdown_budget.py` 釘的是不等式,改它要同時改 run.ps1 字面。

- **判準**:
  (a) `grep "關機收尾" logs/` 的 signals 段仍為 0.0x s(沒有因為加了 wait_for 變慢);
  (b) 新增測試:fake client.close 卡 10 s → `Bot.close` 在 3 s 內返回且印 WARNING;
  (c) `tests/server/test_shutdown_budget.py` 全綠(不等式未動)。
- **回退**:revert 該筆。
- **工作量**:S

### 步驟 8 — `Intents.default()` → `Intents(guilds=True)`

**為什麼排最後**:N9 / F12,純粹是把外部負載從下單主機的 loop 上移開,
沒有已知症狀。**要先確認 `fetch_channel` 在只有 guilds intent 時仍解得到 `channel.guild`**
(`on_ready` 的 guild 限定指令註冊依賴它)—— 這是本步驟唯一的真風險。

- **判準**:
  (a) 重啟後 `grep "Discord bot 就緒" logs/` 有命中(= `fetch_channel` + `channel.guild` 都成立);
  (b) `/watch list` 在 Discord 上仍可用(指令同步成功);
  (c) 步驟 2 的 Discord 延遲 p50 不變差。
- **回退**:改回 `Intents.default()`(一行)。
- **工作量**:S

---

## 6. 工具評估

| 工具 | 位置 | 為什麼 | 代價 | 結論 |
|---|---|---|---|---|
| **(無新套件)`_emit` 單調時戳 + `_send_text` 延遲 log** | `signal_hub.py` | 目前端到端 Discord 延遲**完全不可量測**(N15)。TC4 tick 時刻與牆鐘正負不定,不能相減 | 零相依;兩個欄位不進 wire、不動契約 | **建議導入**(步驟 2) |
| **(無新套件)`Discord 送達` 每日彙總一行** | `signal_hub.close` 或換日 | 盤後一行就能對「當日 jsonl 合批則數 vs 實際送達數」 | 零相依 | **建議導入** |
| `httpx`(async webhook) | `notify.py` | 免佔共用 executor 的一格 pool thread(鄰居是不可中斷的 TC4 20 s 取數) | 新 runtime 相依,而 webhook 是 fallback、prod 目前根本沒設 | **不建議**(現階段;若步驟 1 之後 webhook 變主路再談) |
| 專屬 `ThreadPoolExecutor` 給 signals(jsonl + webhook) | `signal_hub` | 與 TC4 殭屍執行緒分池;`/api/stock/signals/today` 的 3.44 ms 讀也不再被餓 20 s | 零相依;關機序列要一起收 | **有條件導入**(B06 已提;本區塊只是受益者,不主推) |
| `orjson` / `msgspec` | WS 出站編碼 | 訊號 payload 2.08 µs、政策 4.73 µs × 686 則/天 = **1.4 ms/天** | wire 欄名逐字契約極多(政策列形狀 / `notify` 欄 / `ticks` 打包) | **不建議**(收益 5 個數量級小於風險) |
| Discord `Embed` 取代純文字 | `format_*` | 2000 字上限改成 4096(embed description),N4 的觸發門檻拉高一倍 | 改變 Discord 上的視覺形狀(user 已習慣四行卡);且**不解決**根因(仍無截斷) | **不建議**(先修 N4 的截斷,不要用更大的桶迴避) |
| Prometheus / OpenTelemetry | 全庫 | 系統完全沒有效能儀器 | 新 runtime 相依 + 要跑 exporter;與 stdlib-only 的 runtime 約束衝突 | **不建議**(本區塊用 log 行就夠;全庫層級的決定不在這裡下) |

---

## 7. 明確「不要動」清單

1. **`_discord_worker` 的單槽 `_discord_pending` + `task_done` 記帳**(`signal_hub.py:1198-1234`)——
   少記一格 `join()` 永不返回(關機吊死),多記一格當場打死 worker(整天 Discord 無聲而
   WS/jsonl 正常)。兩種失效都不指向這裡,註解已寫明。合批效益雖只有 2.9%(N8),
   但它的存在理由是**順序**不是效率。
2. **雙佇列 + `_put_drop_oldest` 的「丟最舊保最新」**(1673-1688)——
   熱路徑零反壓是刻意的;79 session 零命中證明容量是夠的。
3. **`ws.py::relay` 的 `send_lock` 不包住 `async for`**(249-252)——
   包了就是心跳靜默失效,而心跳失效的症狀(所有 WS 每 35 s 重連一輪)與
   CLAUDE.md §4 的 WS 心跳契約直接相關。
4. **`playBeep` 的 AudioContext 三態處理**(`useSignalAlerts.ts:72-112`)——
   `closed` 回收 / `suspended` 單發 resume / `resuming` 旗標,三個都是真踩過的坑。
5. **桌面通知不受靜音鈕影響**(`useSignalAlerts.ts:258-260`)——
   靜音 = 「不要出聲」不是「不要通知」;人離開分頁時桌面通知是唯一抵達路徑。
6. **`allowed_mentions=AllowedMentions.none()`**(`discord_bot.py:579`)——
   群組名是自由文字且會原樣回填訊息,沒有這行任何人都能把 bot 變成 mention 擴音器。
7. **`_run` 的 `except Exception` 指令邊界**(`discord_bot.py:197-199`)——
   CLAUDE.md §E 的正當例外,已轉成明確文案 + `logger.exception`。
8. **`group_choices` 的 1 s 逾時 + 三態回空**(399-437)——
   autocomplete 不能 defer,防禦縱深。實測鎖內只剩 0.69 ms 檔案 IO,更該留著。
9. **`engine.quotes()` 走 `_quote_payload` 唯一定義**(N17)——
   `chg_pct` 的分母在除權息日是 `ref_milli` 不是昨收;抽出來重算會造第二份會漂的算式。
   ≤15 ms/分的成本不值得換這個風險。
10. **`shouldNotify` 的 `!== false`**(`signal-model.ts:95`)——
    CLAUDE.md §4 契約逐字:缺欄視為 true。改成 `=== true` 會讓舊 jsonl / 舊後端整天無聲。
11. **`_CLOSE_FLUSH_TIMEOUT` 的 `join()` 先於 `cancel()`**(`signal_hub.py:551-576`)——
    worker 手上那一則已 `get()` 但沒寫完,先取消就再也找不回(`_flush_pending` 只掃得到
    還在佇列裡的)。改的是 `bot.close()` 的逾時,**不是這個順序**。

---

## 8. 未解問題

1. **Discord REST 送出的實際 RTT 是多少?** 步驟 2 做完才有答案。
   在那之前「開盤 45 則能不能在 60 s 內送完」只能推估。
2. **05:50 的 gateway 重連風暴根因是什麼?**(本機 DHCP 續約 / ISP / Windows 網路省電?)
   落在盤外所以無害,但如果它是「網路每天固定斷一次」,盤中也可能發生。
   需要一次 `Get-NetAdapter` / 事件檢視器對照,不在本區塊。
3. **webhook 該不該設?** 設了會多一條格式不同的訊息源(webhook 沒有四行卡的頻道脈絡);
   但它是唯一在 bot 全掛時還活著的路。這是 user 決策(HITL),不是我能定的。
4. **步驟 6 的「重複提示」語意要怎麼定?** 同一則訊號在 WS 收到過一次、
   baseline 又補一次時要不要再響?我傾向「同 id 只響一次,重啟後可再響」,
   但這會讓「盤中重啟 = 重播當日全部 toast」—— 需要 user 拍板。
5. **`discord_per_min` 提到 50 之後,Discord 的實際 429 行為?**
   discord.py 的 bucket 處理是自動的,但如果同一個 bot application 還有別的用途
   (CLAUDE.md 提過與已退役的 treading-king bot 同 application),全域限制會共享。
   需要一次真實壓測或看 discord.py 的 rate-limit DEBUG log。
6. **群組名長度上限該設多少?** 實測現況 12 個群組名**最長 6 字**(`ALL IN`),
   其餘皆 ≤ 4 字。所以設 40 都綽綽有餘、零遷移風險;但上限值本身是 user 的命名習慣問題,
   我不在報告裡寫死。
