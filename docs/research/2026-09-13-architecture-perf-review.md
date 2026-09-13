# copycat 架構檢查:改造成高效能量化系統的事實基底

2026-09-13。目的:回答「現在慢在哪、要改成什麼樣、用什麼工具」,作為後續與 Fable 細部討論的輸入。

詳細分區報告見 `docs/research/2026-09-13-arch-scan/`(28 份 + 4 份彙整,1.9 MB)。

---

## 0. 這份報告怎麼產生的、可信度在哪

28 個區塊各派一個 agent 深掃,每一區掃完立即由**第二個 agent 對抗查核**(預設立場是懷疑,任務是把每條打回去)。56 agents、13.5M tokens、3,216 次工具呼叫、91 分鐘,零失敗。掃描與查核 agent 都實際寫了並執行 micro-benchmark(`bench_*.py`、`verify_*.py` 共二十餘支),不是憑印象。

過濾結果:

| | 數量 |
|---|---|
| 掃描提出的 findings | 457 |
| CONFIRMED(證據成立、量級合理) | 211 |
| OVERSTATED(問題在、但沒那麼嚴重) | 210 |
| REFUTED(證據不成立或路徑跑不到) | 23 |
| UNVERIFIABLE(要實測才知道) | 13 |
| 查核時**另外補抓**的漏網 | 143 |
| 校正後 critical | **3** |
| 校正後 high | **46** |

**近半數被降級、23 條被直接駁回**,這正是這份報告的價值:它同時告訴你「哪裡該改」與「哪裡看起來該改但其實不該」。

### 最重要的方法論警告(請先讀這一段)

**這套系統目前沒有任何效能儀器。** 後端 `app.user_middleware == []`(實測)、無 request timing、無 event loop lag 探針、無 tick 吞吐計數;前端無 render 計數、無端到端延遲量測。

後果是:**上面 457 條的每一個量級,包含查核 agent 重測的那些,全部是離線 micro-benchmark + 推估。** 查核過程已經證實掃描 agent 的絕對值系統性高估 1.5–2 倍(parse 28.8 → 21.97 µs、light_snapshot 168 → 82 µs、群組 150 檔 103 → 54 ms、apply_backfill 25 → 11.3 ms)。

有兩個關鍵未知數,它們是十幾條 finding 的共同分母,而**一個都沒被量過**:

1. **TC4 推播率**,尤其「純簿更新」的頻率(簿更新量遠大於成交)。所有「每秒 N 則 × 每則 M µs」的推論都掛在這上面。
2. **前端實際 render 率與主執行緒占用**。

好消息:有兩條**現成、零成本**的量測通道,查核 agent 已經驗證可用。
- `logs/server-*.log` 的回補行記了每檔當日 tick 總數。聚合 `server-20260911-0036.log`:**90 檔、合計 381,107 筆、median 2,247 筆/檔**。這直接驗證了記憶體那一區的核心前提。
- `.claude/mod/group-grid-ticks/verification.md` 有一份 **09-03 開盤 09:01–09:03、prod build、真實 80 檔自選** 的完整 DevTools trace(93 秒、17 MB gz),可以直接解出 render 次數、每次成本、主執行緒忙碌比例。掃描與查核 agent 都沒用到它。

**結論:任何改造動工前,先做第 4 節的 Layer 0。** 沒有它,下面每一條的排序都可能是錯的。

---

## 1. 現況架構全貌

### 1.1 規模

| | 檔數 | LOC |
|---|---|---|
| 後端 `copycat/` | 123 | 37,589 |
| 後端 tests | — | 60,489 |
| 前端 `frontend/src` source | 160 | — |
| 前端 tests | 156 | — |
| 前端合計 | — | 75,233 |

後端 runtime **純 stdlib**(`pyproject.toml` 的 `dependencies = []`);extras 才有 fastapi / uvicorn / pyzmq(live)、comtypes / pywin32(capital)、discord.py。前端 `dependencies` 只有 5 個:react、react-dom、@tanstack/react-query、clsx、tailwind-merge。**沒有圖表庫、虛擬化庫、狀態管理庫、Web Worker、canvas**,所有圖表是手刻 SVG。

### 1.2 耦合結構(graphify AST 知識圖:4,687 nodes / 9,039 edges / 296 communities)

God nodes(degree 由高到低):

| 節點 | degree |
|---|---|
| `create_app()` — `server/app.py` | 115 |
| `Bar1K` — `data/models.py` | 105 |
| `CapitalClient` | 79 |
| `FadeBacktestConfig` / `StockEngine` | 71 |
| `SignalHub` | 70 |
| `TC4QuoteSource` | 51 |

**Import cycles:0。** 模組相依無環 —— 這對重構是最好的消息:可以分層改,不會被循環相依綁死。

產物:`graphify-out/graph.html`(可直接開)、`GRAPH_REPORT.md`、`graph.json`。

### 1.3 後端執行緒拓撲(這是理解「為什麼慢」的關鍵)

Prod 行程內有**五條互相獨立的 TC4 session**:TXO、個股(≤150 檔)、指數、期貨、相關係數。

每條 session 起 **3 個 Python 執行緒**(listener、healer、KeepAlive)+ **3 個 ZMQ Context**(各帶一個 C 層 IO thread)。五條合計 **15 Python 執行緒 + 15 ZMQ IO thread**,再加訂閱瞬間每檔一支 `threading.Timer`(150 檔 = 瞬間 150 執行緒)、Capital COM 執行緒、asyncio 預設 executor(20 workers)。

**而這五條 session 的 SUB socket 連同一個 SubPort 且 `SUBSCRIBE ""`,每一條都收得到全部五條的推播。** 這不是推論 —— repo 自己在 `live/models.py:16-19` 與 `live/aggregate.py:46-48` 明文記載,實測 `dropped_foreign_ticks` 一日 309 萬 vs 真 TXO tick 2,300。

### 1.4 前端資料流拓撲

六條流(watchlist_quote / book / ticks / futures / index / signal)**全部 setState 在 `App`**,而上游沒有任何 memo 邊界。所以每一則訊息都重建 App 的整棵 element tree。

節流狀況不一致:
- `ticks` 有 0.1 s 打包(`_flush_ticks`)
- `watchlist_quote` 有 1 s 節流,但是 **per-code**(150 檔 = 最壞每秒 150 則)
- `book` **完全沒有節流、也不比對內容有沒有變** —— 這是 `/ws/stock` 上唯一裸奔的訊息型別,而它的下游(`accum` identity → `stockCtx` → RightRail memo → PriceLadder)是全站最重的子樹

---

## 2. 三個結構性根因

457 條 findings 收斂下來,絕大多數是這三件事的症狀。

### R1 — 同一則電文被解碼五次,四次是純浪費

五條 session 各自:`recv()` → `.decode("utf-8")` → `find(":")` → `json.loads` → `_note_push` 記帳 → `call_soon_threadsafe` 丟進**同一個** event loop。其中四個 callback 做一次 dict lookup 後立刻 return。平行還有五條 KeepAlive 執行緒對同一則做 decode + `re.search` 全字串掃描,只為了找每 N 秒一次的 PING。

查核重測(876 byte 真實電文、Python 3.13.13 / Windows 11 / ProactorEventLoop):

| 動作 | 每則每 session |
|---|---|
| listener decode + find + json.loads | 6.31 µs |
| `_note_push` 記帳 | 0.53 µs |
| KeepAlive decode + regex | 1.10 µs |
| `call_soon_threadsafe` | ~7–8 µs |

一則電文的行程總成本約 **100 µs,其中約 69% 由四條「這則不關我的事」的 session 付掉**,而且全壓在 GIL 上。

**這條 2026-08-19 就被記過一次**(`docs/research/2026-08-19-browser-crash-scan.md` P2 表第 12 列逐字寫了),沒進 triage,所以一年下來零進展。

### R2 — 單一 event loop,零優先序

**使用者要按下去的那個閃電梯、150 張卡片的 60 s 全量重送、開盤回補重放、訊號層、群益下單回報,全部排在同一條執行緒的同一個 FIFO 上,沒有任何優先序。**

而且 loop 上有幾個固定的長停頓,它們不管有沒有人在看都照跑:

| 停頓源 | 頻率 | 單次 | 說明 |
|---|---|---|---|
| `CorrState.correlations()` | 每 1 秒 | 11.6–13.7 ms | **零 WS client 時照算** —— `_broadcast` 在 boot 就綁上了,永遠不是 None |
| `/api/stock/group-state` | 每 60 秒 | ~33 ms(150 檔) | 群組檢視週期性同步序列化 |
| full GC | 一天 2–3 次 | 71–108 ms | 61 萬個 tick 物件把老年代撐大 |
| `apply_backfill` 重放 | 每檔回補一次 | 9.9 ms(6,000 筆) | 在 event loop 上同步重放整日 tick |
| FinMind `json.loads` | 週期性 | 數十 ms | 在 `to_thread` 裡,但 `json.loads` 是 C 實作**全程持 GIL** —— 整個 process 一起卡,程式碼卻讀起來像已經卸載了 |

另外:**Windows 預設 timer 精度 15.6 ms**,實測閒置 loop 的 `asyncio.sleep(0.05)` 超出量 p50 = 12.43 ms。也就是說每個定時器平均遲到 12 ms,這是整個系統既有的抖動地板,而且沒人量過。一行 `ctypes.windll.winmm.timeBeginPeriod(1)` 可壓到 0.7 ms。

### R3 — 前端六條流共用一個 setState 落點,無 memo 邊界

盤中 App commit 率合計約 **80–200 次/秒**,每一次都重建整棵 element tree。實測單次全樹 render 2.28 ms(比掃描估的低很多,因為實際有六個 memo 邊界擋著,不是掃描說的兩個)。

`TxoPage` 與 `IndexPage` **恆掛載且零 memo**,所以每則 book 連兩張看不見的頁一起重繪。

同一筆成交會造成**兩次**全樹重繪:book 立即送 + 0.1 s 後的 ticks 打包 —— 兩條路沒有對齊。後端其實是同一則 REALTIME quote 同時產出 tick 與 book。

---

## 3. 對「換工具」這個前提的檢驗

你的需求是「後端要用計算夠快、大型資料處理夠好的工具」。28 個區塊獨立投票的結果,**大幅否定了在即時路徑導入這類工具**:

| 工具 | 建議導入 | 有條件 | 不建議 | 結論 |
|---|---|---|---|---|
| **py-spy**(取樣式 profiler) | **10** | 0 | 0 | **全票通過,唯一無異議項** |
| 專屬 ThreadPoolExecutor(stdlib) | 4 | 0 | 0 | 全票通過 |
| ProcessPoolExecutor(stdlib) | 2 | 0 | 0 | 全票通過(離線層) |
| orjson | 4 | 9 | 9 | 分歧,見下 |
| msgspec | 2 | 7 | 7 | 分歧 |
| numpy | 3 | 3 | 6 | 多數保留 |
| httpx | 2 | 2 | 2 | 分歧 |
| **polars** | 1 | 5 | **8** | **多數反對** |
| pyarrow / parquet | 2 | 0 | 3 | 偏保留 |
| **numba** | 0 | 1 | **7** | **幾乎全否** |
| **DuckDB** | 1 | 0 | **5** | **多數反對** |
| **uvloop** | 0 | 0 | **11** | **全票否決**(Windows 不支援) |
| winloop | 0 | 4 | 4 | 分歧,收益推估 < 5% |
| **Web Worker** | 0 | 0 | **7** | **全票否決** |
| **zustand** | 0 | 0 | **5** | **全票否決** |
| Redis / aiofiles | 0 | 0 | 3 各 | 否決 |
| lightweight-charts / uPlot | 1 / 0 | 1 / 3 | 2 / 0 | 有條件,但不是第一步 |

### 為什麼這些被否決(理由都有實測)

- **uvloop**:不支援 Windows。winloop 是替代,但查核指出「瓶頸是純 Python CPU 不是 socket 層」,收益 < 5%。而且實測 uvicorn 目前已經自動選到 Windows 上最好的組合(ProactorEventLoop/IOCP + httptools C parser + WebSocketsSansIOProtocol)—— **不要手動指定 `--loop` / `--http` / `--ws`**。
- **polars / DuckDB 在回測上**:前提是錯的。回測搜索**已經是 Python int bitmask**(`mask |= 1 << i`,走 C 層 bitwise),GA / 窮舉用 bitwise AND 評估。在這個計算形狀上 polars / DuckDB 不會更快。
- **numba**:Windows + Python 3.13 支援落後,且熱路徑的工作單元太小(µs 級),JIT 編譯延遲吃掉收益。
- **numpy 在即時路徑**:`stock_state.py:147-198` 的 `_apply` / `_fold_vp` 實測 **1.96 µs/tick**,VWAP / high / low / VP 全部已經是增量式、穩態零物件配置。300 tick/s 全開也只佔 0.06% 一顆核。**這是全 repo 寫得最好的熱路徑之一,換 numpy 只會變慢。**
- **Web Worker / zustand**:前端的問題是 memo 邊界與節流,不是計算量。實測全樹 render 只要 2.28 ms;把東西搬去 worker 或換 store 都解不到「每秒重繪 80–200 次」這件事。
- **orjson / msgspec 分歧的原因**:查核發現 FastAPI 0.139.2 + pydantic 2.13 **已經走 `dump_json` 的 pydantic-core Rust 快路徑**(1.6 MB 實測 6.8 ms,比 stdlib `json.dumps` 的 14.6 ms 快一倍)。**顯式指定 `ORJSONResponse` 反而會讓 `use_dump_json` 變 False、退回較慢的路徑。** orjson 真正該指的地方是 WS 出站(見 4.2)。

### 絕對禁區(改了會壞,而且零錯誤訊號)

- **`copycat/market.py` 的毫元整數運算**(台股 tick 表 + 漲停價)。換成任何浮點(numpy / polars 的 f64)都引入舍入誤差,**直接影響下單價格正確性**。而且它守著 `tests/fixtures/vp_parity.json` ↔ 前端 `stock-tick.ts::snapDown` 的跨語言 parity 契約。實測 103–187 ns/call,每 tick 呼叫也只有 0.04 ms/s。
- **`tc4common.py::to_milli_units` 的 Decimal**。實測 0.449 µs,手刻整數版(已驗證逐位等值)0.369 µs —— 省不到 0.1 µs,而檔內明文寫著「Decimal 是截斷、float round 是 banker's rounding,在 tick 邊界會分岔」。
- **`backtest/quantiles.py` 的兩/三種分位數演算法**。user 2026-07-20 拍板保留,檔頭明寫「統一演算法會改報告數字 = 行為改動」。換 `np.quantile` = 靜默改掉所有已發布報告。
- **`bollinger.ts` 的直算法**。檔頭明記「不用 Σx²−(Σx)²/n 的一趟法:毫元價位平方後量級 1e11,一趟法在低波動盤整段會有災難性抵銷」。為效能改成一趟法 = 用正確性換速度。
- **`replay/validate.py` 的 42 條 golden + `report.py::med`**。但同時要更正一個廣為流傳的誤解:**`validate` 的比對是帶容差的**(`_within_rel(tol=0.05)`、`_within_pp(0.005/0.01/0.03)`),ulp 級浮點漂移不會讓它紅。多條 finding 拿它當 byte-exact gate 來嚇阻改動,是過度保守。
- **`ws.py` 整支**(per-client 有界 queue + 丟最舊保最新 + 心跳 + FIRST_COMPLETED 收尾)。查核評為「全庫寫得最好的併發 code」。`publish` 的同步 fanout 裡沒有任何 await,**這是「一個慢 client 拖不到其他 client」的唯一保證,任何改 async 的提案都是退步**。
- **`capital/` 的 COM 執行緒模型與 safety.py**。真錢路徑,COM STA 讓它沒有別的寫法,而且目前完全不是效能瓶頸。
- **`uvicorn --reload`**:watchfiles 已裝但刻意沒用。開了 = 每次存檔重建五條 TC4 session,每次付 60 s 零推播代價。

### 真正的結論

**最大的收益全部來自「刪掉重複的工作」與「加閘」,零新相依。** 大型資料處理工具(numpy / parquet / ProcessPool)只在**離線回測層**明確勝出,而那一層不在交易延遲路徑上,買的是研究迭代速度。

---

## 4. 後端改造路線

### Layer 0 — 先裝儀器(不改任何行為,必須最先做)

七個不同區塊的查核 agent 各自獨立地把這一條排成該區第一優先(B02-12 / B04-17 / B10-10 / F6-06 / X5-05 等)。理由一致:**上面每一條的量級都是推估,沒有它就沒有驗收判準,也無法回答「開盤那三秒是誰卡住 loop」。**

1. 純 ASGI timing middleware + event loop lag 探針。
   注意:**Windows 的 15.6 ms timer 粒度會讓天真的 lag 探針變成假訊號產生器** —— 閒置 loop 的 `sleep(0.05)` 本身就 overshoot 12 ms,和真停拍無從分辨。探針必須先校正這個地板,或先做 `timeBeginPeriod(1)`。
2. `timeBeginPeriod(1)`(一行,`__main__.py` 的 `uvicorn.run` 之前)。把整個系統的抖動地板從 12 ms 壓到 0.7 ms。
3. TC4 ingress 吞吐 / 積壓計數(每則 +1,每 60 s 印一行)。這解掉兩個關鍵未知數之一。
4. `py-spy`(全票通過)。取樣式、不需改 code、可 attach 到跑著的 prod process。
5. 下單鏈分段時戳:`perf_counter_ns` + 審計行加毫秒。
   **注意:延遲其實已經量得出來** —— 511 筆審計的秒解析度 pre/post 配對給出 mean ≈ **70 ms**、p99 ≈ 2 s,而純 Python 段只有 p50 ≈ 1.0 ms。也就是 **98.5% 的時間在 `SendStockOrder` + COM pump**,而那一段目前一條 finding 都沒碰。這個數字直接推翻了下單區塊原本的優先序。
6. `logs/` 與那份 09-03 DevTools trace 先拿來驗證現有假設(零成本)。

### Layer 1 — 零相依、零風險的刪浪費

| 項目 | 位置 | 收益 |
|---|---|---|
| corr / river 加 `has_clients` 閘 | `corr_engine.py:320-345` | 沒人看時省掉每秒 13 ms 的 loop 停頓。**三行、零數值風險** |
| listener 在 decode **之前**用 bytes 判 DataType | `tc4.py:1245` | 非 REALTIME 訊息完全跳過 decode + json.loads |
| KeepAlive 的 PING 判斷改 bytes 比對 | `tcoreapi_mq.py:288-297` | 省掉每則每 session 1.1 µs 的全字串 regex |
| `StockMeta` 改 dirty-check | `stock_models.py:194-203` | 八個欄位當日全是常數,每則重建 2.71 µs |
| `_taipei_time` 改整數運算 | `stock_models.py:90-96` | **佔 stock parse 的 36–39%,單點 CP 值最高**。7.37 → 0.52 µs |
| `evaluate_book` 用 latch 旗標整條短路 | `signal_state.py:334-362` | 查核評為訊號區投報率最高的一筆;`on_book` 每則推播都跑而只有 limit_lock 可能出事件 |
| `_distribute` 補 `enabled` 檢查 | `signal_hub.py:985-988` | **停用的 CDP 規則仍付全額狀態推進**,純死工 |
| `_eval_volume` 的 300 秒窗改 running sum | `signal_state.py:658` | 全庫唯一**成本隨單檔 tick 率平方成長**的 per-tick 運算 |
| `engine._consume` 拿掉 `wait_for` 包裝 | `engine.py:377-393` | 0.493 → 2.590 µs;註解自己說 timeout 分支盤中永不觸發 |
| `_hist` / `_states` 加 code 維度淘汰 | `bars.py` / `stock_engine.py` | 前端 `MINUTE_DAYS = 30`,每開一檔圖永久 memo 30 天 1 分 K = 1.74 MiB/檔,150 檔 = 261 MiB |
| `_TICKS_MAXLEN` 檢討 | `stock_state.py:19` | 常數註解寫「熱門股單日 6.2k 實測」,**prod 實測 2303 已達 30,598 筆**(5 倍),最熱的股票正在被靜默截斷 |
| dataclass 加 `slots=True` | `stock_models.py:45-66` | **一行拿走 36% 的 full GC 停頓**(traversal 少掉 `__dict__` 那層),不只是省 19% 記憶體 |
| 加 `Accept-Encoding` | 所有 urllib 外呼 | 傳輸量降約 10 倍:breadth ~924 MB/日 → ~92 MB;screen 網路段 50 s → ~10 s |
| `oi_levels._fetch_rows` 補 `http.client.HTTPException` | `oi_levels.py:158-175` | 與 `breadth_fetch` 2026-09-02 修過的同一個 `IncompleteRead` 洞 |
| `import_neigui` 尾段改 `path.exists()` | `import_neigui.py:238-241` | 12 s → 0.16 s,語意逐字相同,零風險 |
| 下單審計補 `fsync()` | `server/audit.py:34-37` | 唯一「錢動了、事後必須查得到帳」且**不可重建**的一份,目前只有 `flush()` |

### Layer 2 — 資源隔離(便宜的尾部保險)

- **送單前置審計與 TC4 歷史取數共用同一個預設 20-thread executor。** 常態零影響(0.38 ms / 每天約 77 次,prod 511/511 乾淨),但真錢路徑上有一段**無上界的排隊**,鄰居是最壞 20 s 且**不可中斷**的 TC4 取數。`asyncio.wait_for` 逾時只放掉 semaphore 名額,worker thread 中斷不了。
  → 拆具名 lane。**注意隱藏代價**:`ThreadPoolExecutor` 的 worker 是 non-daemon,直譯器退出時會 join 全部 worker,而 `shutdown(wait=False, cancel_futures=True)` 只丟得掉佇列中還沒開跑的。要同步檢查 `shutdown_budget` 的不等式(CLAUDE.md §4 關機預算三方同源契約)。
- **`/api/stock/bars` 完全沒有併發閘**,而它的 payload 比有閘的 `overlay` 大兩個量級(實測單發 ~547 KB)、最壞等待 20 s vs overlay 的 15 s route 逾時。
- **MIS 櫃買快照是 24/7 無閘輪詢**,頻率是報告原本宣稱的 6 倍(17,280 次/日,不是 2,940)。`_mis_loop` 是裸的 `while True:`,沒有時間窗、沒有交易日閘。
- **盤中重啟 server 會在市場時間內跑完整輪盤前篩選**(23 請求 + 21 次 ~63 ms 的 loop 全凍)。`expected_target_date` 的規則是「交易日 08:00 後 = 今天」,所以交易日 10:30 重啟就會觸發。

### Layer 3 — 結構重構(R1 + R2 的根治)

**單 reader thread**:一條執行緒 recv → 解碼**一次** → 依 symbol 查路由表分派 → 每 N 則或每 1 ms 做**一次批次** `call_soon_threadsafe`。五條 KeepAlive 執行緒與其 ZMQ Context 直接不起。**不需要任何新相依。**

前提與風險(查核補抓,掃描漏了):
- 先在 `_ensure_connected` 加一行 log 印 sub_port 確認 —— TC4 若改成 per-session port,單 reader 會**靜默只收一條流**。
- 每條 session 的 `_last_push` / `_sub_at` / `_heal_*` 記帳必須由 reader 分派後照舊呼叫。
- **特別注意 `_last_msg`**(`tc4.py:1249`):它今天由**每一則**訊息推進,包含 PING、包含四條外來 tick。TXO session 在夜盤、corr session 在週末,自家 symbol 本來就沒推播 —— 改成只餵自家訊息後,安靜的 session 會**每 30 秒進一次重連迴圈**。
- `handle_raw(raw: str)` 是四個子類的覆寫點與數十處測試的注入點,必須保留成薄轉接層。
- **不動任何 CLAUDE.md §4 跨檔契約**(全在 wire 之前)。

另外兩條結構級:
- **`handle_raw` 在 `_listen_loop` 的 try 之外** —— 任何例外 = listener 執行緒靜默死亡 = 整條 session 零推播,而兩個 watchdog 都救不到(`_heal_tick` 判的是「TC4 沒推」,這裡是「我們沒在收」;`_check_stale` 只從死掉的迴圈內部被呼叫)。已經發生過。
- **整條行情入口依賴一個 gitignored 的第三方檔案**(`spikes/TCPY/tcoreapi_mq.py`),靠 `sys.path.insert` 在 runtime 載入,內含毒鎖(每支方法是 `lock.acquire()` … `lock.release()` 無 try/finally)。而且**這份檔案已經被本專案改過了**(自持 ZMQ Context、daemon thread、`Close()` 用 `_ctx.term()` 強制中斷)。`tc4.py` 一半的複雜度是在繞它。這是供應鏈風險,不是效能問題,但它讓上面每一條重構都踩在流沙上。

### Layer 4 — 離線回測層(這裡才是「大型資料處理」真正該上的地方)

- **全庫零平行化,16 核只用 1 核。** 17 臂 / 4,660 combo / P² 對全是完美 embarrassingly parallel,**零數值風險**(每臂結果彼此獨立、byte-identical),不需要任何演算法改寫,stdlib `ProcessPoolExecutor` 即可。非 wf 路徑今日資料約 13 h → 8 核約 2 小時。**ROI 遠高於 numpy / numba 路線,應該排離線層第一個做。**(倍數 8–12x 是推估,驗收前不要寫進 spec;Windows spawn 的 pickle 成本可能讓實際落在 4–8x。)
- **`optimize_rule_tp` / `optimize_rule_stops` 才是非 wf 路徑最大的單一成本(約 70%)**,而原報告 19 條 finding 沒有任何一條以它為標的 —— 優先序原本掛在只佔 8% 的 `exhaustive_scan` 和 19% 的 combo 網格上。
- **21,254 個 1K JSON 小檔**:全掃 18 s,55% 花在建 `Bar1K`。而且 `fade_pipeline` 對同一批檔的重讀是 **~19 遍**(不是掃描說的 2–3 遍,因為 `:444` 在 `run_fade_arm` 內部,外層還有 arm × params 迴圈)。N=3,000 時約 34 s、N=10,000 時約 112 s,純 IO/解析,每次調參都重付。這是離線層**單一最大、且最便宜可消**的成本 —— parquet / 記憶體 cache 在這裡明確勝出。
- **`bit_indices` 吃掉 `exhaustive_scan` 的 63%**,但**不要用 numpy matmul**:有一個零相依、**bit-exact**、3.7–6.4x 的純 Python 修法(256 項 byte 預算表展開,輸出逐位相同)。numpy 路線要付新相依 + 浮點加總順序改變 + 屬行為改動不能進純重構 commit。
- **`exhaustive_scan` 的 `out` list 比 `seen` set 多吃 4 倍記憶體(~2.0 GB)** —— `top_n=200` 只在最後截斷,在那之前每個 entry 自帶一顆 n_rows-bit 大整數 mask。這是行程平行化的真正天花板。修法:`out` 換 `heapq` 維持 top-200。
- **注意 venv 現況**:numpy / polars / orjson / msgspec / pyarrow **在專案 `.venv` 一個都沒有**。掃描報告中多處「實測 Nx」的對照組不是在這個環境量的。所有 M/L 級建議的 effort 都要加上「首次引入相依 + 決定放哪個 extras + pyright/ruff 設定 + 驗證鏈影響」。

---

## 5. 前端改造路線

### Layer 0 — 同樣先裝儀器

前端完全沒有效能量測探針。以「改造成高效能量化系統」為目標,這是 F2 / F4 / F5 / F7 全部的根結:**沒有端到端數字,所有改造都只能用推測驗收,而推測在這次查核裡已經被打掉一半以上。**

而且有一個既有量測與報告的因果敘事直接衝突:repo 內唯一一筆 **prod build + 開盤 + 50 張卡** 的 trace 顯示 **`>50 ms long task = 0`**(最大 36.7 ms)。2026-08-19 那筆「主執行緒 ~66% 忙但全是短任務」是 **dev build** 的數字,根因已確認為 React dev 的 Component Performance Track。

**所以「按下單鍵有延遲」目前沒有證據支持是 long task 造成的。** 這一條要先量再改。

### Layer 1 — 節流與去重(後端改一處,砍掉前端全部下游成本)

這是前端最划算的槓桿,而且**改在後端**:

1. **`book` 去重**:`_handle_quote` 對主圖是無條件 publish,TC4 的 REALTIME 有純成交(簿沒變)與純簿更新兩類,前者現在也會把一份一模一樣的五檔再送一次。加「與上次送出的相同就不送」,**延遲代價 0 ms**。
2. **`book` 併進既有 `_flush_ticks`**:同一則 REALTIME quote 同時產出 tick 與 book,現在兩條路各自觸發一次全樹重繪。合併後每筆成交只付一次。這比「另起一支 book timer」好。
   注意:五檔是真錢閃電梯,coalesce 會加 100 ms 延遲 —— 先做去重(0 ms 代價),再決定要不要 coalesce。
3. **`watchlist_quote` 改批次**:後端 1 s 節流是 per-code,150 檔 = 最壞每秒 150 則 WS 訊息,每則各自一次 `setWatchlist` → App 全樹重繪。改成一則帶整批。

### Layer 2 — memo 邊界

- **`TxoPage` / `IndexPage` 恆掛載且零 memo** → 包 memo。
- **`useFuturesStream` 常駐 App 層**,每則 0.1 s coalesce 推播都 `setState` → App 全樹重繪,**不管使用者停在哪顆 tab、也不管期貨頁有沒有被 mount 過**。查核指這才是實測最高頻的驅動源。
- **`LadderView` 130 列無列級 memo**,每則約 780–900 個 element 重建。
- **`searchStocks` 未 memo**:寫在 render body,使用者**正在打字**時每則報價都重掃 2,401 筆名冊。

### Layer 3 — 純函式層的死工(查核補抓,掃描全漏)

- **`buildIntradayGeometry` 內的 `energyFrom` 產出零消費者** —— `g.energyBars` / `g.maxTotal` 全 repo 沒有任何讀者(副圖走另一份、高度不同根本不能共用)。每張卡每次更新都在算。
- **`windowedEntries`(271 筆 copy + filter + sort)每張卡每次更新跑兩次** —— 幾何一次、副圖一次,佔整趟幾何成本的 25%。純參數搬移、零輸出值變化。
- **`areaPolygon` 的 273 × `toFixed(1)` + join 佔 `buildIntradayGeometry` 的 48%** —— 有 ref 101.46 µs vs 無 ref 52.75 µs。只要處理這一個字串建構就砍掉近一半。
- **`haveMinutes` Set 只有 hover 才用得到**,但每次幾何重建(10 Hz)都配置一個 271/1140 元素的中間陣列 + 一個 Set。
- **`applyTick` 的成本 82% 在 `new Map(acc.minutes)`** —— key 是連續分鐘號(最多 271 格),天然適合定長陣列,便宜 67 倍。掃描原本把改造指向「批次化」與「不維護 tape」,但 tape 只佔 6%。
- **群組檢視下主圖 accum 仍在養一份沒有讀者的 tape** —— `tape=0` 只讓 snapshot 不帶 ticks,擋不住 `applyTick` 繼續 append。

### Layer 4 — SVG / 圖表庫(先別急)

`EnergySub` 每卡 271 個 `<rect>`(近全軸 1140),50 卡約 13,550 個節點常駐。這確實是量級最大的前端候選,但:

- **repo 自己已經量過**:`StockIntradayChart.tsx:812-817` 明記 jsdom 滿窗一輪 ~15 ms,而「真瀏覽器的 diff 快一個量級」→ 約 1.5 ms/卡,**且只有當拍收到成交的卡才重建**(不是所有 50 張)。同一段註解的結論是「不值得為它換寫法」。
- **卡片變體其實是退化重疊繪製**:卡片寬 ~246 → plotWidth 170 → 170/270 = 0.63,減 0.4 後被 clamp 到 1px,271 個 1px rect 擠在 170px 內。**降採樣比 path 化更便宜**。
- 第一步是**改單一 `<path d>`**,不是換圖表庫。而且 repo 的 next-time 已經有這一項並附了實測 baseline,同一段註解還有一條反面警告:「別用『總量當資料版本』當 memo key —— 1K 回補可以在總量不變下改寫某一分鐘的量,那種 key 會讓副圖靜默停在舊值」。

**圖表庫(lightweight-charts / uPlot)不是第一步。** 遷移成本包含 CDP/MA parity fixture、overlay 分鐘鍵契約(CLAUDE.md §4 有兩條),而收益在改完 Layer 1–3 之後才看得出來還剩多少。

### 前端明確不要做

- **React Compiler**:會把**沒有 reactive 依賴**的 render-body 計算視為常數並跨 render 快取,而 `FuturesChart.tsx:282-307` 等處正是明文「刻意不進 memo,因為 deps 表達不了『現在幾點』」。被快取住的症狀是期貨 live 點與個股即時末根**凍在掛載那一刻**,兩張圖都畫得出來、零錯誤訊號。**這是真錢畫面的正確性風險,不是效能取捨。**
- **`toLocaleString` 換 Intl 單例**:實測 `toLocaleString("en-US")` 0.232–0.277 µs **比** hoisted `nf.format` 0.398 µs **更快**。`lib/format.ts` 已經 hoist 是正確寫法,但沒必要推廣。
- **`cn()` = `twMerge(clsx())` 優化**:實測 cache hit 每次 **0.076 µs**(不是宣稱的 0.5–2 µs),穩態幾乎 100% hit。
- **`CandleChart` 的 index key 改成 `key={c.t}`**:React 對相同 key 是原地更新 props,不卸載不重掛;改成內容 key **反而**引入 key churn。
- **bundle / code splitting**:實測 dist gz 合計 188 KB。跑在 localhost、一天開一次、開著整天不關。
- **虛擬化**:列數不多(閃電梯 130 列、五檔 10 格),列級 memo 就夠。

---

## 6. 量化系統落差(比效能更重要的一塊)

這一節不在效能軸上,但對「要下實單」這個目標,它比上面任何一條都重要。

### Q1 — 回測與實盤是兩套完全獨立的實作(唯一的 critical)

三條 grep 全部重跑確認:`from copycat.backtest` 在 `copycat/` 下**只命中 `cli.py`**;`grep backtest copycat/live/ copycat/server/` **零命中**。

`copycat/live/signal_state.py` 855 行自己實作了 `_eval_cdp` / `_eval_surge` / `_eval_pullback` / `_eval_volume` / `_eval_sweep` / `_eval_limit_tick`,與 `copycat/backtest/` 零共用程式碼、零 parity fixture。

**成本模型是四份不是三份**:`backtest/fade_simulate.py:81` / `backtest/simulate.py:81`(tday 另一份,多 overnight_tax)/ 前端 `ladder-position.ts` / 群益實扣。而且**兩邊「折數」的慣例相反**(回測是 `1−discount`,前端是 `discount/10`)且數值不一致 —— 誰改誰都不會有錯誤訊號。

`copycat/engine/`(lock_quality / t1_open)**只有 replay 在用**,實盤是另一份鎖板定義。而 CLAUDE.md §0a 的核心資產就是鎖板品質分層(`vol_after_lock_share` / `n_reopens` / `tier`),這三個欄位在回測與實盤是兩個定義下的東西。

最低限度修法(不動架構):新增 replay parity gate —— 同一天的 `data/signals/YYYYMMDD.jsonl`(實盤真相源)與 1K(回測路徑)各跑一次同組進場條件,斷言事件集合對稱差 ≤ 白名單。專案已有 `copycat/replay/` + `copycat validate` 可延伸。

**這條不該進效能改造批** —— 混批會讓 golden 驗證同時要顧向量化與語意兩個變因。

### Q2 — 四週影子期的對照基準在 repo 外、無版控

真正 critical 的一句:**影子期結束要拿來對照的研究基準,是一份無版控、隨時可就地改掉的 7,306 行腳本 + 971 MB 資料。** 後果是「我當初測到 +X 元/筆」不可驗證。

修法:`git init` + 一次 commit(資料檔另 LFS 或 gitignore + 記 sha256)。成本 S。**這是整份報告裡 CP 值最高的一條。**

### Q3 — 系統完全不持久化 tick

150 檔 × ~2,000 筆/日 × 32 B ≈ 9.6 MB/日、含五檔約 25 MB/日、一年 2.3 GB。本機完全負擔得起。

**這是唯一一條「不做就永遠補不回來」的條目 —— 每個交易日都在單向流失。**

更正一個因果誤解:`strategy.md` 的「五檔深度不可回測」**不是**不持久化造成的。`_Book` 的 `bids`/`asks` 線上就是完整五檔;`stock_models.py:116` 註解逐字寫「歷史 TICKS row 只有單一 Bid/Ask 欄」—— **既有歷史**不可回測是 TC4 歷史格式的限制,錄音錄不回來;但**從今天起**可以錄。

### Q4 — 新單零冪等防護

只有平倉有 inflight 去重,新單沒有。前端雙擊 / route 重試 / 網路重送**現在就會**產生重複新單,而三道閘一條都擋不住。審計記錄也沒有 `request_id`。這個不對稱本身就是訊號。

**這條在現況就成立**,不像風控那條是條件式的。

### Q5 — 風控只有單筆閘且預設「不限」

缺帳戶級上限、單日虧損熔斷、異常行情擋單。現況是人工下單(一天個位數)+ `CAPITAL_ORDER_ENABLED` 總開關,裸奔風險有限。**它是「接訊號自動下單」這一步的 blocker,不是今天的缺陷。**

### Q6 — 盤中重啟 = 訊號狀態全失

回補 tick 被刻意設計成不重放進 detector。後果是影子期資料品質降級(重啟後約 5 分鐘窗值偏低 + 60 秒內掃單簇不發 + 政策首筆重推一次),不是線上錯單。缺的是「訊號 jsonl 這份真相源裡沒有斷點記號」。

### Q7 — 逾時的寫入命令沒有 TTL

`asyncio.wait_for(asyncio.shield(fut), timeout=_WRITE_TIMEOUT_S)` 逾時後,底層 future 被 shield 保護不取消,命令仍留在 `_cmd_q`,`_run` 取到就直接送 —— **沒有任何 staleness 檢查**,而且佇列無上界。10 秒前(COM 卡住時可能更久)放棄的單會在恢復後照樣送進市場。

### Q8 — `SendStockOrder` 用 `bAsyncOrder=0`(同步)

四個寫入方法全部把 `bAsyncOrder` 硬寫成 0,而 SKCOM typelib 明明支援非同步。同步呼叫會把**唯一一條 COM 執行緒**整個券商往返期間占住。配合 Layer 0 量到的「98.5% 延遲在 `SendStockOrder` + pump」,**這是下單延遲的最大單一標的**。

---

## 7. 需要你拍板的問題

1. **要不要先做 Layer 0(裝儀器)再談其他?** 我的建議是必須 —— 查核已證實掃描的絕對值系統性高估 1.5–2 倍,而兩個關鍵未知數(TC4 推播率、前端 render 率)是十幾條 finding 的共同分母。
2. **stdlib-only 護欄怎麼定?** 查核指出「orjson 是第一次破例」的說法不成立 —— `dependencies = []` 只涵蓋 core package,`optional-dependencies` 早就有 fastapi / uvicorn / pyzmq / comtypes / discord.py。建議維持「新套件一律進 extras」的原則,但那不是「不能裝」。
3. **效能批與量化正確性批要不要分開?** 建議分開:Q1 的回測/實盤統一是 XL 級且屬行為改動,混進效能批會讓 golden 驗證同時要顧兩個變因。
4. **`spikes/TCPY/tcoreapi_mq.py` 的供應鏈問題要不要先處理?** 它 gitignored、已被本地改過、內含毒鎖,而 Layer 3 的單 reader 重構要踩在它上面。
5. **離線回測層的改造要不要獨立立案?** 它與即時路徑耦合度為零(`server/` 與 `live/` 完全沒 import `backtest`),可以完全獨立進行,而 ProcessPool 那一條是全報告 ROI 最高的效能項。
6. **`graphify-out/`(9.8 MB)沒被 `.gitignore` 蓋到** —— 要我加一行嗎?
7. `docs/research/2026-09-13-arch-scan/`(1.9 MB、31 檔)要 commit 嗎?我沒有動 git。

---

## 附錄:檔案索引

| 檔案 | 內容 |
|---|---|
| `docs/research/2026-09-13-arch-scan/_DIGEST-critical-high.md` | 49 條 critical/high 全文(證據、驗證理由、修法可行性查核) |
| `docs/research/2026-09-13-arch-scan/_MISSED-143.md` | 查核階段補抓的 143 條漏網 |
| `docs/research/2026-09-13-arch-scan/_REFUTED-and-DO-NOT-TOUCH.md` | 23 條駁回 + 各區「不要動」清單 |
| `docs/research/2026-09-13-arch-scan/B*.md` `X*.md` `F*.md` `O*.md` `Q*.md` | 28 份分區長篇報告(各 40–70 KB) |
| `graphify-out/graph.html` | 互動式知識圖(4,687 nodes) |
| `graphify-out/GRAPH_REPORT.md` | 圖譜稽核報告(god nodes、社群、import cycles) |
