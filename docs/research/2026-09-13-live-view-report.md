# 看盤:現況診斷、延遲預算、失效模式與改造順序

2026-09-13。功能導向報告之一(另兩份:下單、訊號)。

材料來源:2026-09-13 架構掃描的 13 個看盤相關區塊(B01–B08 後端、F1–F7 前端),全部經過對抗查核。原始長篇報告在 `docs/research/2026-09-13-arch-scan/`。

**本報告的數字分三類,一律標示:實測(在本機真的量過)、推估(由實測外推)、未量(沒有數字)。**

---

> ## ⚠ 2026-09-13 第四輪實測修正(本報告有實錯,已在下方逐處標註)
>
> 第四輪對抗複驗 + 工具實測擂台(見 `docs/research/2026-09-13-verify-bakeoff/`)推翻了本報告數處結論。
> **最嚴重的一條:§0 與 §2.2 原本寫「五檔最壞延遲 ~3 ms」—— 這是錯的,而且是全份唯一會直接造成交易損失的錯誤。**
> 修正內容見各節的「修正」區塊。原文保留以便對照,但**不要依原文做決策**。

## 0. 一句話結論(已修正)

**看盤的計算鏈總和約 153–211 µs(不含 WS egress)。但鏈子中間有一個 100,000 µs(0.1 秒)的打包窗。**

打包窗**最壞**佔 96%、**平均**約 92%(tick 到達時刻均勻時平均等 50 ms)。**五檔那條路徑完全不適用 —— 它沒有窗。**

**修正一(原文說「微優化影響不到 0.3%」——錯):** 延遲表原本把 starlette 的 `send_json` 留白標「未量」,而**它是全表最大單項**。實測(逐字同參數):1 筆打包 2.29 µs / 30 筆 26.56 µs / **300 筆 375.69 µs,每個 client 各一次**。8 分頁 × 10 則/s × 300 筆 = **30 ms/s 純序列化,在 event loop 上**。換 orjson 實測 **N=1 已 8.7x、N=8 77.4x**。所以「後端無事可做」這個結論反轉。

**修正二(原文說「五檔即時 ~3 ms」——錯,危險):** book 的產生與推播**全在單一 event loop 上**(`stock_engine.py:1360` 在 `_handle_quote` 內),而 §2.3 的抖動表列的每一個停頓都排在它前面且**無優先序**。正確說法:

> 五檔:典型 ~3 ms(推估,只含前端 render JS 側);**最壞 ≥ 60–100 ms** —— 一個開著相關係數面板 + 群組檢視的使用者,閃電梯最壞延遲比原文大兩個量級。

而「~3 ms」的源頭 `F4-ladder-highfreq.md:170` 原文自標「**需以 §7 的量測計畫驗證**」= 推估,且不含 layout + paint。

微優化真正買到的不是逐筆延遲,是:WS egress 的 event-loop stall(期間 8 條 WS 全停推)、GIL 餘裕、抖動下降、自動化後的容量餘裕。

---

## 1. 座標:看盤在哪裡

即時看盤佔這個 repo 的 90%。

| 路徑 | LOC |
|---|---|
| 後端 `live/` + `server/` + `capital/` + 共用純函式 | 25,675 |
| 前端 `frontend/src` 全部 | 75,233 |
| 離線 `backtest/` + `replay/` + `engine/` + `data/` | 11,434 |

### 資料流九段

| 段 | 檔案 | 職責 |
|---|---|---|
| 1 入口 | `live/tc4.py`(1,317) | 唯一碰 ZMQ。五條 session 各一條 listener thread |
| 2 解析 | `live/stock_models.py` / `futures_models.py` / `models.py` / `corr_models.py` | 成交、**五檔**、**試撮**窗、**HOT 合約** |
| 3 交接 | 各 engine 的 `_on_raw_threadsafe` | `call_soon_threadsafe` 進 event loop |
| 4 引擎 | `server/stock_engine.py`(1,832)、`index_engine.py`(822)、`futures_engine.py`(694)、`corr_engine.py`(544)、`engine.py`(462) | 訂閱池、換日、回補、打包 |
| 5 狀態機 | `live/stock_state.py` / `signal_state.py` / `corr_state.py` / `river_state.py` / `aggregate.py` / `payoff.py` | 零 IO 增量計算 |
| 6 訊號 | `server/signal_hub.py`(1,697)+ `signal_policy.py` | 另見訊號報告 |
| 7 廣播 | `server/ws.py`(312) | per-client 有界 queue |
| 8 前端流 | `hooks/useStockStream.ts`、`lib/stock-accum.ts`、`tick-stream.ts` | accum 更新 |
| 9 前端畫 | `lib/stock-intraday-svg.ts`(921)、`components/stock/StockIntradayChart.tsx`(1,724)、`PriceLadder.tsx` | 手刻 SVG |

---

## 2. 端到端延遲預算

### 2.1 一則「有成交」的個股報價:TC4 → 畫面

| # | 區段 | 位置 | 成本 | 依據 |
|---|---|---|---|---|
| 1 | TC4 內部 → ZMQ PUB → loopback | — | **未量** | 黑箱 |
| 2 | listener `recv` + `decode` + `json.loads` | `tc4.py:1245`、`:1189-1211` | 6.31 µs **× 5 session** = 31.6 µs | 實測 |
| 3 | `_note_push` 自癒記帳 | `tc4.py:780-813` | 0.53 × 5 = 2.7 µs | 實測 |
| 4 | KeepAlive `decode` + `re.search` | `tcoreapi_mq.py:288-297` | 1.10 × 5 = 5.5 µs | 實測(平行執行緒,但吃 GIL) |
| 5 | `parse_stock_realtime` | `stock_models.py:188-235` | 有成交 **23.6 µs** / 純簿更新 **13.6 µs** | 實測 |
| 6 | `call_soon_threadsafe` 跨執行緒 | 各 engine | 8.1 µs × 5 = 40.5 µs | 實測(Windows self-pipe write) |
| 7 | `StockDayState.ingest` | `stock_state.py:87-198` | **1.96 µs** | 實測(已是最佳解) |
| 8 | `SignalHub.on_tick`(7 slot) | `signal_hub.py` | 20.7 µs(窗 61)– 78.5 µs(窗 1501) | 實測 |
| 9 | `SignalHub.on_book`(7 slot) | `signal_hub.py:616-630` | 26.4 µs / **每則推播** | 實測 |
| 10 | `WsBroadcaster.publish`(ticks) | `ws.py:65-80` | ~130 µs / 則 | 實測 |
| 11 | starlette `send_json`(**per client**) | `ws.py:262-271` | **26.6 µs**(30 筆)– **375.7 µs**(300 筆)**× 分頁數** | **實測(第四輪補量)** —— stdlib json.dumps,在 loop 上。**全表最大單項**,原文留白 |
| | **後端計算小計(修正)** | | **153–211 µs**(不含 ⑩⑪)/ **283–341 µs**(含 ⑩) | 原文「150–260」加總不符 |
| | **+ WS egress(每則 ticks 打包)** | | **⑩ 130 µs + ⑪ 26.6–375.7 µs × 分頁數** | 開盤多分頁時後端 egress 可達 **3 ms/則** |
| **12** | **`_flush_ticks` 打包窗** | `stock_engine.py:1342` | **0–100 ms** | **設計值,支配項** |
| 13 | 瀏覽器 `onmessage` → `applyTick` | `lib/stock-accum.ts` | 82% 成本在 `new Map(acc.minutes)` | 實測 |
| 14 | App 全樹 re-render | `App.tsx` | **2.28 ms** | 實測 |
| 15 | `buildIntradayGeometry` | `stock-intraday-svg.ts` | 52.75 µs(無 ref)– 101.46 µs(有 ref) | 實測 |
| 16 | `EnergySub` DOM(271–1140 個 `<rect>`) | `StockIntradayChart.tsx:818` | ~1.5 ms / 卡 | **推估**(jsdom 15 ms ÷ 10) |
| 17 | 瀏覽器 layout + paint | — | **未量** | |

**加總(修正):後端計算 153–211 µs + WS egress(130 µs + 26.6–375.7 µs × 分頁數)+ 打包窗 0–100 ms + 前端 ~4 ms。**

打包窗**最壞** 96%、**平均**約 92%;**五檔路徑不適用(無窗)**。開盤多分頁時 WS egress 可達 3 ms/則,是後端最大單項。

### 2.2 各資料型別的最壞延遲(這張表才是你該看的)

| 資料 | 節流機制 | 位置 | 最壞延遲 |
|---|---|---|---|
| **五檔 `book`** | **無節流、不去重** | `stock_engine.py:1359-1360` | 典型 ~3 ms(推估);**最壞 ≥ 60–100 ms**(單 loop FIFO 無優先序,見修正二) |
| 逐筆 `ticks` | 0.1 s 打包 | `stock_engine.py:1342` | **~103 ms** |
| 自選報價 `watchlist_quote` | 1 s 節流(**per code**) | `stock_engine.py:1813-1832` | ~1 s |
| 期貨 | 0.1 s coalesce | `futures_engine.py:655-694` | ~103 ms |
| **加權** | 1 Hz 廣播 | `index_engine.py:744` | ~1 s |
| 櫃買 | MIS 5 s 輪詢 + 1 Hz 廣播 | `index_engine.py:508-517` | **~6 s** |
| 相關係數 / **江波圖** | 1 Hz | `corr_engine.py:223-230` | ~1 s |
| WS 心跳 | 10 s | `ws.py:34` | — |

CLAUDE.md §4 已記「主圖最多晚 0.1 s(user 拍板接受)」。

### 2.3 抖動源(比延遲更值得處理)

| 源 | 頻率 | 單次停頓 | 依據 | 備註 |
|---|---|---|---|---|
| **Windows timer 粒度** | 每個 timer | **p50 +12.47 ms** | 實測 | ⚠ **修正:這不是地板** —— 1000 則/s 推播下自然降到 0.626 ms。而且 `timeBeginPeriod(1)` **單獨無效**(見 Step 0 修正) |
| `CorrState.correlations()` | **每 1 秒** | **12.68–13.66 ms** | 實測 | **零 WS client 時照算**(`_broadcast` 在 boot 就綁上,永遠不是 None) |
| `/api/stock/group-state` | 每 60 秒 | ~33 ms(150 檔) | 實測 | 群組檢視週期性同步序列化 |
| full GC | 一天 2–3 次 | ⚠ **修正:盤中真正上界 25.5 ms** | 實測 | 原文 71.8 ms 是 `gc.collect()` 的數字。擬真自動 GC:dataclass 25.53 ms、加 slots 24.63 ms(**噪音內,slots 買不到停頓改善**) |
| `apply_backfill` 重放 | 每檔回補一次 | 9.9 ms(6,000 筆)/ 32.4 ms(20,000 筆) | 實測 | 在 event loop 上同步重放 |
| FinMind `json.loads` | 週期性 | 數十 ms | 推估 | 在 `to_thread` 裡,但 `json.loads` **全程持 GIL** —— 整個 process 一起卡 |

### 2.4 已知的總量實測

- WS 廣播層總 CPU ≈ **2.1 ms/s**(單核 0.2%)。這一層沒有吞吐量問題。
- 期貨 WS 實測 **17.9 msg/s**(10 秒取樣)。
- 前端主執行緒(09-03 開盤、prod build、80 檔自選、93 秒 trace):整機 **24.9% busy**、**`>50 ms` long task = 0**、最大單一任務 36.7 ms、約 17% 花在 React 全樹重繪。
- 每檔當日 tick 數(`logs/server-20260911-0036.log` 聚合):90 檔、合計 381,107 筆、**median 2,247**、最熱 **30,598**。

### 2.5 兩個關鍵未知數

1. **TC4 推播率**,尤其純簿更新的頻率。十幾條結論的共同分母,**沒被量過**。
2. **`book` 訊息的實際則數/秒**。它是唯一無節流的型別,決定要不要為它加窗。

---

## 3. 失效模式表

**標「靜默」的表示零錯誤訊號 —— 壞了畫面照樣畫得出來。**

> **⚠ 修正三:「16 條裡有 10 條靜默」高估一倍,真正零訊號約 4–5 條。** 第四輪逐條回查:
> - **#1 / #2 不靜默** —— `threading.excepthook` 把 traceback 寫 `sys.stderr`,而 `__main__.py:131` 把 stderr tee 到 `logs/`;而且 healer 是**獨立 daemon thread**,listener 死 → `_last_push` 停滯 → 每輪印「TC4 REALTIME 零推播自癒」WARNING 洪水。正確定性是「**救不到但看得到**」→ 要的是**自動重啟 listener**,不是補偵測。
> - **#5 / #7 / #8 / #9 不靜默** —— 四條都有**跨語言 parity 測試,後端測試直讀前端原始碼字面**(`test_daily_final_time_parity_with_frontend` 等)。改任一邊 `pytest` 就紅,**根本出不了門**。#9 尤其諷刺:原文同一列的「位置」欄自己寫「有釘」,「靜默」欄卻寫「是」。
> - **#4 部分** —— 使用者端永久遺失 ✓,但營運端有 `ws.py:82-97` 的 60 s 節流 WARNING + CLAUDE.md §4 明訂的盤後 grep 判準。
>
> **所以待拍板第 4 條「10 條靜默要不要系統性補偵測」的答案是:不要全補。** 真正該投的是 #6 / #10 / #15。
> 而且第四輪指出**原文的 Step 2 與 Step 3 各自帶進一條新的零訊號失效,原文沒標**(見 §4 修正)。

| # | 失效 | 觸發 | 症狀 | 靜默 | 位置 |
|---|---|---|---|---|---|
| 1 | listener 執行緒死亡 | `handle_raw` 拋例外(它在 `try` **之外**) | 整條 session 零推播,畫面停住 | **是** | `tc4.py:1246-1257` |
| 2 | 兩個 watchdog 都救不到 #1 | 同上 | `_heal_tick` 判的是「TC4 沒推」,這裡是「我們沒在收」;`_check_stale` 只從死掉的迴圈內部呼叫 | **是** | `tc4.py:706-722` |
| 3 | `_TICKS_MAXLEN` 被打破 | 熱門股 > 20,000 筆 | 成交明細最早的筆數被丟掉 | **是** | `stock_state.py:19`(註解前提 6.2k,prod 實測 **30,598**) |
| 4 | WS 丟包丟掉訊號列 | queue 滿(1000) | rail 有 5 分鐘 REST baseline 可補,但 **toast / 嗶 / 桌面通知只走 WS,永久遺失** | **是** | `ws.py:70-80` |
| 5 | ticks 打包契約漂掉 | 後端改回單筆 / 改欄名 | 前端 `default` 分支靜默丟棄,主圖與圖牆同時凍在快照 | **是** | CLAUDE.md §4 |
| 6 | `view` 訊息未在 onopen 重送 | WS 重連 | 圖牆逐筆消失,只剩 60 s 輪詢 | **是** | CLAUDE.md §4 |
| 7 | 日 K 定稿界前後端漂掉 | 兩邊值不同 | 整個下午拿半成品:CDP 基準錯、加權「最後一根未收盤」印到午夜 | **是** | CLAUDE.md §4 `DAILY_FINAL_TIME` |
| 8 | 盤前篩選群組名漂掉 | 後端改名前端沒跟 | 圖牆列出 ~60 張卡 | **是** | CLAUDE.md §4 `SCREEN_GROUP` |
| 9 | 江波圖腿數 > 調色盤色數 | 加第 12 腿 | 第 n+1 腿撞回近白色 | **是** | `tests/test_corr_config.py` 有釘 |
| 10 | 個股 `seq` 語意漂掉 | 後端改成訊息計數 | 成交明細 tbody 整片重掛(畫面閃一下) | **是** | CLAUDE.md §4 |
| 11 | 單 reader 重構打斷 `_last_msg` | 改成只餵自家訊息 | 安靜的 session(TXO 夜盤、corr 週末)每 30 秒進一次重連迴圈 | 否(log 看得到) | `tc4.py:1249` |
| 12 | TC4 半死拖垮共享 executor | TC4 無回應 | overlay 逾時放掉 semaphore 但 worker **中斷不了**,連帶卡住 `bars_range`、下單前置審計 | 否 | `app.py:1496-1514` |
| 13 | MIS 端點壞掉 | TPEx 非契約公開端點無預警變更 | 櫃買資料 None 降級 | 否 | `server/mis.py` |
| 14 | `_hist` / `_states` 無淘汰 | 開過很多檔 | 記憶體線性成長(前端 `MINUTE_DAYS = 30` → 1.74 MiB/檔,150 檔 = 261 MiB) | 否 | `bars.py` / `stock_engine.py` |
| 15 | 前端 accum 薄股跨日 | 昨日恰好只有 `acc.seq` 筆 | 群組卡片由 60 s 輪詢修正;主圖無週期重播種,靠重連/切檔自癒 | **是** | CLAUDE.md §4(已知盲點) |
| 16 | 前端拿到舊 dist | 部署前後端不同版 | 未知 kind 印英文代號;**規則視窗「編輯」按了沒反應**(TypeError,零 ErrorBoundary) | 部分 | CLAUDE.md §4 |

**16 條裡有 10 條是靜默的。** 這是這個 codebase 最需要補的能力 —— 不是更快,是**壞掉要看得出來**。

---

## 4. 改造順序

每一步都附量測判準。**順序不可跳**:Step 0 之前的所有量級都是推估。

### ⚠ 修正四:Step 0 的 `timeBeginPeriod(1)` 原文寫錯,而且判準是陷阱

第四輪實測(T4):**`timeBeginPeriod(1)` 單獨呼叫在 Windows 11 上只有效約 3 秒**,之後被 EcoQoS 收回、退回 12.602 ms。8 種替代配方全無效。

**正確做法是兩行,缺一不可,兩個呼叫都要檢查回傳值:**
1. `SetProcessInformation(ProcessPowerThrottling, IGNORE_TIMER_RESOLUTION)` —— 豁免 EcoQoS
2. `timeBeginPeriod(1)`

實測結果:timer drift p50 **12.47 → 0.556 ms(22.4x)**、p99 14.2 → 1.98 ms,在 `run.ps1` 現行的 `-NoNewWindow` 下複驗穩住。

**原文的驗收判準「重測 sleep 超出量 p50 < 1 ms」會讓錯誤實作在前三秒回報 PASS,零錯誤訊號。** 判準必須改成「持續量 60 秒,p50 全程 < 1 ms」。

收益要誠實拆:盤外約 12 ms、**盤中密集推播時只剩約 2 ms**(推播本身會自然拉高時鐘解析度);且 `queue.get(timeout=)` 一族不受影響 —— **下單路徑不在受益範圍內**。

### ⚠ 修正五:第四輪找到一條 ROI 更高、四輪都漏掉的第一刀

**`_POLL_BACKOFF_START = 0.15` → `0.02`(倍增與 1.0 s 上限不動)。改一行。**

C1 對**開著的達錢 4** 逐發拆解:一次冷日 K 取數的 153 ms 裡,**有 150.5 ms 是我們自己的 `time.sleep`** —— TC4 真正備妥只要 15–40 ms。

- 冷歷史取數 153 → 22–43 ms(**3.5x**)
- 150 檔進群組冷 overlay 5.8 → 2.6 s
- 零新相依、零契約、零數值風險

四輪掃描都沒發現,因為那個均勻度(標準差 < 0.3 ms)看起來太像穩定的服務時間。

**必須保留倍增退避** —— 固定 2 ms 對「查無此檔」的股號會在 10 秒內打 975 發。

### ⚠ 修正六:TC4 無上限併發 → 多開 lane 的收益實測為 0

C1 對真 TC4 實測:6 發目錄查詢分 1..6 條 lane,**牆鐘恆約 19 s(最佳 1.04x)**。8 條並發 LOGIN 全過 —— 所以 user 的新事實講的是**併發許可**,不是**併發吞吐**。

TC4 桌面 app 本身是單一序列化服務端。**「多開 REQ lane」這條方案應刪除。** 唯一有效的是優先權排序(見修正七)。

### Step 0 — 裝儀器(必須最先,不改任何行為)

| 動作 | 位置 | 判準 |
|---|---|---|
| ⚠ **`timeBeginPeriod(1)` 單獨無效** —— 見下方修正 | `server/__main__.py` | ⚠ **原判準是陷阱** —— 見下方修正 |
| 純 ASGI timing middleware | `app.py` | `/api/health` 暴露 p50/p95/p99;`app.user_middleware` 不再是 `[]` |
| event loop lag 探針 | `app.py` 一個 ~20 行 task | 每 100 ms 量 drift,p99 > 20 ms 就 WARNING。**必須在 `timeBeginPeriod(1)` 之後做**,否則是假訊號產生器 |
| TC4 ingress 吞吐計數 | `tc4.py:1244-1250` | 每 60 s 印一行:則數/s、REALTIME 佔比、簿更新 vs 成交比。**這解掉關鍵未知數 #1** |
| `book` 則數計數 | `stock_engine.py:1359` | 同上。**解掉未知數 #2** |
| `py-spy` | 不改 code | attach 到跑著的 prod process,取樣 60 s |
| 前端 render 計數 | `App.tsx` | 每秒 commit 數;與 09-03 trace 對照 |

**Step 0 的產出決定後面每一步要不要做。**

### Step 1 — corr / river 加 `has_clients` 閘

- **改動**:`corr_engine.py:320-345`,三行。
- **收益**:沒人看江波圖時,省掉每秒 12.7–13.7 ms 的 loop 停頓。這是 24 小時無條件成本。
- **判準**:關掉所有瀏覽器分頁,loop lag 探針的 p99 應該從 ~14 ms 掉到接近地板。
- **退路**:單一條件式,直接還原。
- **注意**:如果之後要做「`state()` 讀上一拍快取」,兩者必須一起設計 —— 否則沒人連著的那段時間根本沒算過,新連上的第一個 client 會拿到幾小時前的配對。

### Step 2 — `book` 去重(前端最划算的一步,改在後端)

- **改動**:`stock_engine.py:1359-1360`,加「與上次送出的五檔相同就不送」。
- **收益**:TC4 的 REALTIME 有純成交(簿沒變)與純簿更新兩類,前者現在也會把一份一模一樣的五檔再送一次。**延遲代價 0 ms。**
- **判準**:`book` 則數/s(Step 0 裝的計數)應該下降;前端 App commit 率同步下降。
- **退路**:拿掉比較即可。
- **不要順手做**:「`book` 併進 0.1 s 窗」是另一件事,會讓閃電梯延遲 +100 ms。那是真錢畫面,要你單獨拍板。

### Step 3 — listener 在 decode **之前**用 bytes 判 DataType

- **改動**:`tc4.py:1245`;KeepAlive 同招 `tcoreapi_mq.py:288-297`。
- **收益**:非 REALTIME 訊息完全跳過 `decode` + `json.loads`。
- **判準**:ingress 計數的「每則平均 µs」下降;`py-spy` 上 `json.loads` 佔比下降。
- **風險**:`tcoreapi_mq.py` 是 gitignored 的 vendored 檔,改它要先解決 Step 9 的供應鏈問題,或至少記錄本地修改。

### Step 4 — parse 微優化

| 動作 | 位置 | 實測收益 |
|---|---|---|
| `_taipei_time` 改整數運算 | `stock_models.py:90-96` | 7.37 → 0.52 µs(**佔 parse 的 36–39%,單點 CP 值最高**) |
| `StockMeta` 改 dirty-check | `stock_models.py:194-203` | 2.71 µs / 則(八個欄位當日全是常數) |
| `StockTick` / `StockMeta` 加 `slots=True` | `stock_models.py:45-66` | 記憶體 201 → 153 B/tick;**full GC 71.8 → 45.9 ms** |

- **判準**:`parse_stock_realtime` 的 micro-benchmark 從 23.6 µs 降到 < 15 µs;full GC 停頓(用 `gc.callbacks` 記錄)中位數下降 ≥ 30%。
- **注意**:`_taipei_time` 也被回補路徑的 `parse_hist_tick` 用到,熱門股單日 42,084 次 —— 收益在那邊更大。
- **不要順手改 `to_milli_units`**:實測只省 0.08 µs,而 Decimal 是截斷、float 是 banker's rounding,tick 邊界會分岔。

### Step 5 — 訊號層去重(詳見訊號報告)

`evaluate_book` latch 短路、`_distribute` 補 `enabled` 檢查、`_eval_volume` 改 running sum。這三條在看盤路徑上,因為它們掛在 `_handle_quote` 尾端、每則推播都跑。

### Step 6 — 前端 memo 邊界

| 動作 | 位置 |
|---|---|
| `TxoPage` / `IndexPage` 包 memo(恆掛載且零 memo) | `App.tsx:121-129` |
| `useFuturesStream` 的 setState 降級(常駐 App 層,**不管在哪個 tab 都觸發全樹重繪**) | `hooks/useFuturesStream.ts:49/72/99` |
| `LadderView` 130 列加列級 memo(每則約 780–900 個 element 重建) | `components/stock/LadderView.tsx` |
| `searchStocks` 包 `useMemo`(寫在 render body,打字時每則報價重掃 2,401 筆名冊) | `WatchlistSidebar.tsx:195` |

- **判準**:App commit 率不變的前提下,DevTools Performance 的 Scripting 時間下降;`>16.7 ms` 的任務數下降。
- **必須固定的變因**:量 before/after 時要固定「側欄展開了幾組、圖牆選了哪一組」—— 側欄摺疊會直接改變量級,不控制就不可比。

### Step 7 — 前端死工(純刪,零行為變化)

| 動作 | 位置 | 實測 |
|---|---|---|
| 刪 `energyFrom`(產出**零消費者**) | `stock-intraday-svg.ts` | 整段免費 |
| `windowedEntries` 算一次往下傳(現在跑兩次) | 同上 | 17.5 µs × 2,佔整趟幾何 25% |
| `areaPolygon` 的 `toFixed(1)` 換 `Math.round(x*10)/10` | 同上 | **佔 `buildIntradayGeometry` 的 48%** |
| `haveMinutes` Set 改惰性(只有 hover 用得到) | `stock-intraday-svg.ts:451` | 每次幾何重建省一個 271/1140 元素陣列 + Set |
| 主圖 accum 停止養沒有讀者的 tape | `App.tsx:181` | 群組檢視下 |

- **判準**:`buildIntradayGeometry` 的 micro-benchmark 從 101 µs 降到 < 55 µs。輸出值必須逐格相同(寫 characterization test)。

### Step 8 — `applyTick` 的 `minutes` 改定長陣列

- **實測**:`applyTick` 成本的 **82%** 在 `new Map(acc.minutes)`。key 是連續分鐘號(最多 271 格),換成 index-offset 陣列便宜 **67 倍**。
- **判準**:`applyTick` micro-benchmark;accum 輸出值不變。
- **effort**:M。要改 `stock-accum.ts` 與所有讀 `minutes` 的地方。

### Step 9 — 單 reader 重構(L,根治 R1)

一條執行緒 recv → 解碼**一次** → 依 symbol 查路由表分派 → 每 N 則或每 1 ms 批次 `call_soon_threadsafe`。五條 KeepAlive 執行緒與其 ZMQ Context 直接不起。**零新相依。**

前置與風險:
1. **先在 `_ensure_connected` 加一行 log 印 sub_port 確認。** TC4 若改成 per-session port,單 reader 會靜默只收一條流。
2. `_last_push` / `_sub_at` / `_heal_*` 記帳必須由 reader 分派後照舊呼叫。
3. **`_last_msg`(`tc4.py:1249`)最危險** —— 見失效模式 #11。
4. `handle_raw(raw: str)` 是四個子類覆寫點與數十處測試注入點,保留成薄轉接層。
5. 順手修 **失效模式 #1**:把 `handle_raw` 移進 `try`。
6. **不動任何 CLAUDE.md §4 契約**(全在 wire 之前)。

- **判準**:ingress 計數的每則成本降到現在的 ~1/4;`py-spy` 上 listener 執行緒的 CPU 佔比下降;五條 session 的自癒記帳行為不變(比對 log 的自癒事件數)。
- **實測參考**:批次化 `call_soon_threadsafe` 的原型(deque + `_scheduled` 旗標)實測 **0.040 µs/call**,對現況 8.1 µs 是 **200 倍**。

### Step 10 — SVG 降採樣 / `<path>` 化(L)

`EnergySub` 每卡 271 個 `<rect>`(近全軸 1140),50 卡約 13,550 節點常駐。

⚠ **修正七:原文說「先做降採樣」是錯的,已撤回。** T5 用真 Chrome CDP 實測(不是 jsdom):

| 方案 | 圖牆 50 卡每拍 | 該層單獨 | 保真度 |
|---|---|---|---|
| 現況 SVG rect | 56.83 ms | — | — |
| **降採樣到 170 根** | — | **1.44x** | ❌ **資料失真**(桶內取 max,副圖 maxTotal 與資訊列的「量」不再同源) |
| **單一 `<path>`** | **26.08 ms(2.18x)** | **3.12x** | ✅ **逐像素相同** |
| canvas 2D | 11.27 ms(5.04x) | 6.58x | ✅ 語彙對等 |

成本在「元素個數 ×(React reconcile + DOM 屬性寫 + Blink 樣式重算)」的**線性項**上,271→170 只是沿線滑一格。

**正確順序:先 `<path>` 化**(DOM 18,645 → 3,009 節點、heap Δ +15.56 → +8.81 MB、零新相依、零 bundle、幾何層一行不動)。canvas 是之後的選項,且需你拍板(`CardIntradayChart` 的 doc 明文反對「同一檔在卡片與單檔頁是兩張不一樣的圖」)。

另外:repo 的 N047 註解「真瀏覽器的 diff 快一個量級」**高估 3 倍**(實測 jsdom 13.09 / Chrome 4.0 = 3.3x),而「不值得改」這個結論在單檔頁對(271 格只要 1.52 ms/拍)、**在圖牆錯**(同一層 50 卡要 44.99 ms/拍)。

- **判準**:DOM 節點數;真瀏覽器 trace 的 Rendering + Painting 時間。
- **反面警告**(repo 既有註解):別用「總量當資料版本」當 memo key —— 1K 回補可以在總量不變下改寫某一分鐘的量,那種 key 會讓副圖靜默停在舊值。

---

## 5. 不要動(已驗證)

| 項目 | 理由 |
|---|---|
| `copycat/market.py` 全檔 | 毫元整數 tick 表,實測 103–187 ns/call。**換浮點直接影響下單價格正確性**,且有跨語言 parity 契約 |
| `live/stock_state.py:147-198` `_apply` / `_fold_vp` | 實測 1.96 µs/tick,已是增量 O(1)、穩態零配置。**全 repo 最該被抄的寫法,換 numpy 只會變慢** |
| `server/ws.py` 整支 | 查核評「全庫寫得最好的併發 code」。`publish` 的同步 fanout 是「慢 client 拖不垮別人」的唯一保證,**改 async 是退步** |
| `tc4common.py::to_milli_units` | 省不到 0.1 µs,而 Decimal 截斷 vs float banker's rounding 在 tick 邊界分岔 |
| `server/overlay.py` CDP/MA | O(n),n ≤ 1500,每檔每天算一次。滑動窗增量化是純複雜度 |
| `futures_engine` 的 0.1 s dirty-set coalesce | 已是正確的 coalescing 設計 |
| `IndexEngine._broadcast_loop` | 每拍 < 100 µs,`_dirty` 閘正確 |
| `RiverState` 的分鐘桶 dict | 稀疏、整數鍵,對它用 numpy 是純過度工程 |
| `lib/stock-intraday-svg.ts` 的幾何語意分支 | 每一條對應一個真實 bug 的修法,為速度砍掉任何一條都是用正確性換效能 |
| `bollinger.ts` 直算法 | 一趟法在低波動盤整段會災難性抵銷 |
| `useContainerSize` 的 1px 去抖與 0×0 忽略 | 兩條都是修過的真 bug |
| `lib/ws-reconnect.ts` | 個股 tick 洪流下零 timer churn,設計正確 |
| `uvicorn --reload` | 開了 = 每次存檔重建五條 TC4 session,每次付 60 s 零推播 |
| 手動指定 `--loop` / `--http` / `--ws` | 實測已自動選到 Windows 最佳組合(ProactorEventLoop/IOCP + httptools + WebSocketsSansIOProtocol) |

**已被實測駁回的「優化」**(不要做):`toLocaleString` 換 Intl 單例(前者**更快**)、`cn()` 優化(cache hit 0.076 µs)、`CandleChart` 的 index key 改內容 key(反而引入 key churn)、`_parse_levels` 的字串串接(0.0067 µs)、`json.loads` 改吃 bytes(str **更快**)、虛擬化(列數不多)、Web Worker、zustand、React Compiler(會凍住刻意不進 memo 的牆鐘計算,**真錢畫面正確性風險**)。

---

## 6. 待你拍板

1. **`tick_flush_secs`(0.1 s)要不要動?** 這是逐筆延遲的唯一有意義旋鈕。CLAUDE.md 記著你拍板接受 0.1 s。調到 0.05 s 會讓 WS 則數翻倍。
2. **`book` 要不要併進打包窗?** 併了則數大降,但閃電梯 +100 ms。我建議只做去重(Step 2,0 ms 代價),不併窗。
3. **櫃買 MIS 的 5 秒輪詢 + 24/7 無閘**(實測 17,280 次/日,`_mis_loop` 是裸 `while True`)—— 要不要加交易日/時段閘?
4. **10 條靜默失效模式要不要系統性補偵測?** 這是獨立於效能的一批工作。
5. **Step 9 的前置**:`spikes/TCPY/tcoreapi_mq.py` gitignored、已被本地改過、內含毒鎖。要先處理嗎?
