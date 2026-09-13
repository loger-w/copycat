# V1-verify-liveview —— 複驗「看盤報告」(2026-09-13)

複驗對象:`C:/side-project/copycat/docs/research/2026-09-13-live-view-report.md`
立場:預設懷疑。每一條都回原始碼 / 回 log / 重新量。
本檔所有「我實測」= 2026-09-13 在本機新量,腳本在同目錄
(`v1_bench.py` / `v1_bench2.py` / `v1_applytick.mjs` / `v1_codec.py` / `v1_ws.py` / `v1_rest2.py` / `v1_corr.py`)。

量測環境:Windows 11、系統 Python 3.13.13(**未動專案 .venv**)、node v24.13.0、
拋棄式 venv `scratchpad/venvs/v1`(orjson 3.12.0 / msgspec 0.21.1 / fastapi 0.139.2 / numpy)。
我的機器數字與報告的機器數字有 ±25% 差異(同量級),**所有「倍數」與「歸因比例」才是結論**,絕對值僅供對照。

---

## 0. 總評

這份報告的**方向**是對的(打包窗支配逐筆延遲、微優化買的是 GIL 餘裕不是延遲、
不要為速度砍幾何分支),但它有**三個結構性錯誤**,任何一個都足以讓照著做的人做錯事:

1. **延遲預算表的小計算錯,而且漏掉了最大的一項。**
   「後端計算小計 150–260 µs」無論怎麼加都對不上表身(153–211 或 283–341);
   更要命的是表裡標「未量」的 #11(`send_json` per client)我十分鐘就量出來了 ——
   **開盤 300 筆打包 376 µs/client**,是它自己最大實測項(#10 的 130 µs)的 2.9 倍。
   「後端全鏈 0.25 ms」這個頭條數字建立在把最大項留空上。

2. **「五檔最壞延遲 ~3 ms」與報告自己的 2.3 表直接矛盾。**
   2.3 表列了同一條 event loop 上每秒 12.68–13.66 ms、每 60 秒 33 ms、GC 71.8 ms 的停頓。
   這些全部排在 book 前面。**閃電梯的最壞延遲不是 3 ms,是 ≥ 100 ms。**
   而報告的 §0 又說閃電梯是真錢畫面 —— 這個矛盾是整份報告最危險的一條。

3. **「最大收益全部是刪掉重複工作、零新相依」在 user 的新目標下是錯的。**
   我實測:orjson 在 WS egress 5.6–13.5x、ingress 2.93x;numpy 對 `CorrState.correlations`
   10x 且逐值差 1.4e-16。這兩個都是**語意等價、可 golden 對照、風險可控**的替換,
   而報告一條都沒提(numpy 的否定被寫在 `RiverState` 上,但真正該上的是 `CorrState`)。

另外:**失效模式表的「靜默」旗標高估**。標 10 條靜默,我查下來至少 5 條有明確訊號
(log / WARNING / 跨語言 parity 測試),其中 #9 報告自己在「位置」欄寫了測試檔名還標「是」。
高估靜默的代價不是白做工,是**把稽核預算花在已經有守門的地方,而真正零訊號的那幾條反而沒被排序**。

**能不能當改造依據?** 第 3、4、5 節(失效模式、不要動清單、待拍板)可以直接用。
**第 2 節的延遲預算表與第 4 節的 Step 2/3/7/8 順序不能直接用**,要照本檔修正。

---

## 1. 延遲預算表逐格複驗(§2.1)

| # | 報告值 | 我的判決 | 依據 |
|---|---|---|---|
| 2 | 6.31 µs **× 5** = 31.6 µs「實測」 | **標籤錯**:6.31 是實測,×5 是**前提未證**的推論 | 我實測 `decode+find+json.loads` = 4.45–5.93 µs(752–830 B),同量級。但「×5」的前提是五條 session 的 `SubPort` 相同 —— `tc4.py:487` `self._sub_port = q["SubPort"]` 是**各自登入時拿的**,`_DIGEST` 自己寫「建議先在 `_ensure_connected` 加一行 log 確認」。報告把整格標「實測」抹掉了這個前提 |
| 3 | 0.53 × 5 = 2.7 µs | 合理 | `_note_push` 在 `_realtime_msg` 內,五條都跑 ✓ |
| 4 | KeepAlive 1.10 × 5 = 5.5 µs | **CONFIRMED 且被低估的結構** | 我實測 `decode + re.search` = 1.17 µs ✓。但報告沒講**為什麼**這是純浪費:`spikes/TCPY/tcoreapi_mq.py:288-291` 的 KeepAlive **自己開一顆 SUB 訂 `""`**,所以全市場每一則都被它 decode 一次。換 `b'"PING"' in raw` 預判 = 0.31 µs(我實測),省 0.86 µs × 5 |
| 5 | 23.6 / 13.6 µs | 合理 | 我實測 19.5 / 9.6 µs,比例相符(有成交 ≈ 2x 純簿更新)✓ |
| 6 | `call_soon_threadsafe` 8.1 × 5 = 40.5 µs | **CONFIRMED,而且比報告寫的更糟** | 我回查四支 `handle_raw`:`stock_source.py:925`、`futures_source.py:222`、`corr_source.py:164` **一個 symbol 過濾都沒有**,無條件 `self._on_message(quote)`;TXO 走 base `tc4.py:1213` 的 `parse_realtime` —— 我實測它對個股電文**回 Tick 不是 None**(個股電文有 TradingPrice/TradeQuantity/PreciseTime),所以 TXO 也照付。**×5 成立**。過濾全部發生在 **loop 上**(`corr_engine.py:265` `self._by_symbol.get(...)` → return),等於四份垃圾在 event loop 上排隊 |
| 8 | on_tick 20.7–78.5 µs | 未複驗(訊號報告的範圍) | — |
| 9 | on_book 26.4 µs / 每則推播 | 位置正確 | `stock_engine.py:1364-1365` `if self._signal_hub is not None and self._pending_date is None: on_book` ✓ |
| 10 | `publish` ~130 µs/則 | 單位是「每則打包」不是「每則報價」 | `ws.py:65-80` 只做 `put_nowait` fanout。130 µs 對一次 put_nowait 偏高,推測含 `_settle_drop_window` 與多 client |
| **11** | **「未量」** | **可量而未量,而且它是最大項** | 我實測 `json.dumps(separators=(",",":"), ensure_ascii=False)`(= `starlette/websockets.py:174` 逐字):1 筆打包 2.29 µs / 10 筆 9.33 / 30 筆 26.6 / **300 筆 375.7 µs**,**每個分頁各一次**。8 個分頁 × 10 則/s × 300 筆 = **30 ms/s 純序列化在 loop 上** |
| 14 | App 全樹 2.28 ms「實測」 | **數字對、名字錯** | 來源 = `_DIGEST` 1037 行,09-03 開盤 prod preview(4173)93 s trace 的 **React work loop(`rt`)單次平均**,73 次/秒。是 **prod build ✓**,但它是「一次 React 工作迴圈」不是「App 全樹 render」 |
| 15 | `buildIntradayGeometry` 52.75–101.46 µs | **下界是反事實不是案例** | 兩個數字來自 `_MISSED-143.md:219`:101.46 = 有 ref、52.75 = **無 ref(`areaPolygon` 恆空)**。prod 每一檔都有參考價 → **真值恆是上界**。而 `F1-stream-hotpath.md:117` 對同一支函式量到 **126 µs(主圖)/ 116 µs(卡片)**。報告挑了較低的那組且沒說為什麼 |
| 16 | EnergySub ~1.5 ms/卡「推估」 | 標籤誠實 ✓ | jsdom ÷ 10 的外推,標「推估」正確 |

### 小計算不出來

逐格相加(取有成交路徑):

- **不含 #10**:31.6+2.7+5.5+23.6+40.5+1.96+20.7+26.4 = **152.96 µs(最小)～ 210.76 µs(最大,#8 取 78.5)**
- **含 #10**:**282.96 ～ 340.76 µs**

報告寫「**約 150–260 µs**」。下界 150 ≈ 不含 #10 的最小值;上界 260 **兩種算法都到不了**
(不含 #10 是 211、含 #10 是 341)。這一格是手感不是加總。

**再加上我實測的 #11**(單分頁 30 筆打包 26.6 µs、開盤 300 筆 376 µs),
「後端計算 ~0.25 ms」在開盤多分頁時實際是 **0.4–3 ms**。

### 「打包窗吃掉 96% 以上」

- 最壞(tick 剛好在窗開頭到):100 / (100 + 0.25 + 4) = 95.9% ✓
- **平均**(到達時刻均勻 → 平均等 50 ms):50 / 54.25 = **92.2%**
- **五檔那條路徑:0%**(無窗)

「96% 以上」只在最壞成立。結論方向不變(微優化買不到逐筆延遲),但
**寫成「以上」會讓人以為平均更高,實際相反**。

---

## 2. 「五檔 ~3 ms」怎麼來的 —— 這是本報告最嚴重的一條

### 來源

`F4-ladder-highfreq.md:170` 逐字:

> **每則 render 的 JS 側 ≈ 1–3 ms**(Chrome、prod build;**需以 §7 的量測計畫驗證**)

也就是:

1. 它是 **推估**,原文自己標「需驗證」。報告 §2.2 表把它抄成 `~3 ms` **連標籤都沒有**(表無「依據」欄),§0 更寫成「本來就是即時的(~3 ms)」。
2. 它 **只是前端 render 的 JS 側**。不含後端計算(~0.25 ms)、不含 `send_json`(我實測 book 訊息小,約 2–3 µs)、**不含 layout + paint**(表 #17 自己標「未量」)、不含瀏覽器合成。
3. **它包含 2.28 ms 的 App 全樹**嗎 —— 幾乎可以確定包含:2.28 ms 是 prod trace 的 React work loop 平均,而 book → `useStockStream` setState → App 重繪就是那一趟。所以 1–3 ms ≈ 2.28 ms 加減。**不是額外疊加,是同一件事的兩種說法。**

### 致命處:表頭寫的是「最壞延遲」

§2.2 的欄名逐字是「**最壞延遲**」。而 book 的產生與推播**全部在單一 event loop 上**
(`stock_engine.py:1360` 在 `_handle_quote` 內,`_handle_quote` 由 `call_soon_threadsafe` 排進 loop)。
報告自己的 §2.3 列出同一條 loop 上的停頓:

| 排在 book 前面的停頓 | 頻率 | 單次 |
|---|---|---|
| `CorrState.correlations()` | **每 1 秒** | 12.68–13.66 ms |
| `/api/stock/group-state` | 每 60 秒 | 33 ms(150 檔) |
| full GC | 一天 2–3 次 | 71.8 ms |
| `apply_backfill` 重放 | 每檔回補一次 | 9.9–32.4 ms |
| `B04-stock-engine.md:175` 群組全量重送上限 | 每 60 秒 | **103 ms** |

**一個開著相關係數面板 + 群組檢視的使用者,他的閃電梯最壞延遲 ≥ 103 ms,不是 3 ms。**
而這正是 user 要下單的那個畫面。報告把 3 ms 放進「最壞延遲」欄,等於告訴 user
「這裡不用管」——這是我在這份報告裡找到**唯一會直接造成交易損失**的錯誤。

**正確寫法**:五檔「典型 ~3 ms / 最壞 ≥ 100 ms(單 loop FIFO,無優先序)」。
`_MISSED-143.md` 的 B04 節已經點出這件事(「使用者要按下去的那個閃電梯,和 150 張卡片的
60 s 全量重送……全部排在同一條執行緒的同一個 FIFO 上,沒有任何優先序」),**報告沒有收進來**。

---

## 3. 失效模式「靜默」旗標逐條複驗(§3)

報告:「16 條裡有 10 條是靜默的」。我逐條回原始碼 / 測試查:

| # | 報告 | 我的判決 | 證據 |
|---|---|---|---|
| 1 | listener 執行緒死亡 **靜默=是** | **REFUTED —— 有兩種訊號** | (a) `handle_raw` 確實在 `try` 外(`tc4.py:1249-1250`)✓,但 thread 死掉時 `threading.excepthook` 把 traceback 寫 `sys.stderr`,而 `server/__main__.py:131` 把 `sys.stderr` 換成 tee 到 `logs/server-*.log` → **traceback 進得了 log**。(b) `_start_healer`(`tc4.py:634`)是**獨立執行緒**;listener 死 → `_note_push` 不再被呼叫 → `_last_push` 停滯 → `_heal_tick` R1 命中 → `_heal()` 每輪印 `logger.warning("TC4 REALTIME 零推播自癒:%s 靜默 %.0fs → 重掛…")`。**零推播 + 持續 WARNING 洪水,不是零訊號** |
| 2 | 兩 watchdog 救不到 **靜默=是** | **一半 CONFIRMED、一半 REFUTED** | 「救不到」✓(重掛 SUB 救不活死掉的 thread;`_check_stale` 確實只從死迴圈內部呼叫)。「靜默」✗ —— 同上,healer 在叫。**報告把「修不好」寫成「看不到」,這兩件事在稽核排序上是相反的優先級** |
| 3 | `_TICKS_MAXLEN` 被打破 **靜默=是** | **CONFIRMED,但缺頻率** | `stock_state.py:19` `_TICKS_MAXLEN = 20_000` + 註解「熱門股單日 6.2k 實測」✓。我自己重跑 `logs/server-20260911-0036.log` 聚合:**89 檔、合計 380,606、median 2,834、max 30,598**。max 與報告**逐字相符** ✓;但「median 2,247」我兩種算法都得不到(每檔取首筆 = 2,834;全 167 列 = 131)。**真正該寫的是:89 檔裡只有 2 檔超過 20,000(2.2%)** |
| 4 | WS 丟包 **靜默=是** | **OVERSTATED** | `ws.py:82-97` `_settle_drop_window` 有 60 s 節流 WARNING「上一窗共丟 n 則」,CLAUDE.md §4 有盤後 `grep "佇列滿"` 判準。**使用者端靜默 ✓(toast 永久遺失)、營運端不靜默 ✗**。應標「部分」 |
| 5 | ticks 打包契約漂掉 **是** | 部分 | `tests/server/test_stock_engine.py:4162 TestTickBundle` 存在 ✓ —— 改欄名後端測試會紅。**單邊改動擋得住,兩邊一起改才靜默** |
| 6 | `view` 未在 onopen 重送 **是** | CONFIRMED | `tests/server/test_stock_routes.py:1009 TestStockWsView` 釘的是後端解析,**onopen 重送是前端行為**,沒有跨邊守門 ✓ |
| 7 | 日 K 定稿界漂掉 **是** | **REFUTED** | `tests/server/test_bars.py:986 test_daily_final_time_parity_with_frontend` —— **後端測試直讀前端原始碼字面釘等值**。改任一邊就紅,**根本出不了門** |
| 8 | 盤前篩選群組名漂掉 **是** | **REFUTED** | `tests/server/test_screen_engine.py:34 test_screen_group_name_parity_with_frontend`,同上姿態 |
| 9 | 江波圖腿數 > 色數 **是** | **REFUTED,且報告自相矛盾** | 報告的「位置」欄自己寫「`tests/test_corr_config.py` **有釘**」,同一列的「靜默」欄卻寫「是」。`tests/test_corr_config.py:265 test_river_palette_covers_every_leg` 存在 ✓ |
| 10 | 個股 `seq` 語意漂掉 **是** | **CONFIRMED(真靜默)** | 兩邊各自有測試,但**沒有跨語言 parity**;症狀(tbody 整片重掛)是視覺閃一下 |
| 11 | 單 reader 打斷 `_last_msg` **否** | CONFIRMED ✓ | 標「否(log 看得到)」正確 |
| 12–14 | **否** | CONFIRMED ✓ | — |
| 15 | 前端 accum 薄股跨日 **是** | CONFIRMED ✓ | CLAUDE.md §4 自承已知盲點 |
| 16 | 舊 dist **部分** | CONFIRMED ✓ | 有 `VersionDriftBadge` |

### 結論

**真正零訊號的是 #6 / #10 / #15 / #16(部分)/ #4(使用者端半邊),約 4–5 條,不是 10 條。**

而報告**漏標**的靜默失效有兩條,它們是自己提的改法帶進來的(見 §4)——
**漏標的比誤標的危險,而這兩條是報告自己造的**。

---

## 4. 改造順序複驗(§4)

### Step 2 —— book 去重「延遲代價 0 ms」

**數字面 CONFIRMED,但這一步有三個報告沒講的東西。**

我實測(node/py,`v1_bench.py`):

| 形狀 | best |
|---|---|
| `StockBook` 全比(相同,要比完 10 格) | **0.1787 µs** |
| 不同(第 2 格分岔早退) | 0.0930 µs |
| `prev.get(code) == (bids, asks)`(真實修法形狀) | **0.0525 µs** |

0.18 µs 相對 0.1 秒的窗確實是 0 ms ✓。但:

1. **母體只有一檔。** `stock_engine.py:1360` 逐字:
   `if code == self._main:` → `self._publish({"type": "book", ...})`。
   **全 repo 只有這一個 `book` 發送點**(我 grep 過 `copycat/server/*.py`)。
   所以「前端最划算的一步」的收益母體是**主圖那一檔**,不是 150 張卡。
   報告的 §2.2 表與 Step 2 都沒說這件事,讀者會以為是全市場級的省。
   (收益仍在:主圖一檔開盤 ~50 則/s × App 全樹 2.28 ms = 114 ms/s ≈ 11% 單核,值得做。)
2. **它新增一條靜默失效模式。** 現況每則報價都重送一份五檔 = 一則掉了下一則就修回來。
   去重之後,`ws.py` 佇列滿丟掉那一則 book,**在下一次五檔真的變動之前永遠不會被修**。
   鎖漲停時五檔可以幾分鐘不變 —— **閃電梯會停在錯的簿上,零錯誤訊號**。
   修法:去重要配一個「每 N 秒無條件重送一次」的 keepalive,或改成「同內容也送,但前端比較後不 setState」
   (後者把省的地方從 wire 移到 render,book 只有一檔、payload 小,這個方案風險低很多)。
   **報告一個字都沒提。**
3. `has_clients` 這類閘同理:`ws.py:55` 只有 `self._clients: set[...]`,**沒有 `has_clients` 屬性**。

### Step 3 —— bytes 預判 DataType:**收益未證,且順序倒置**

我實測(`v1_bench2.py`,752 B compact 電文):

| | best |
|---|---|
| 現況 `decode + find(':') + json.loads` | 5.93 µs |
| Step 3 修法,**訊息是 REALTIME**(命中 → 還是要 decode+loads) | **5.90 µs** ← 幾乎零收益 |
| Step 3 修法,訊息是 PING(早退) | 0.17 µs |
| 預判本身的成本(掃完整則才判否) | 0.31 µs |

**結論:Step 3 對 REALTIME 訊息零收益。** 它只在**非 REALTIME 訊息**上省,
而非 REALTIME 佔比正是報告自己列的「關鍵未知數 #1」——
**報告把一個收益完全取決於未知數的步驟,排在收益已實測的 Step 4(parse 微優化)前面。**

而且它**帶進一條報告沒標的靜默失效**:needle 是字面比對。我實測:

```
b'"DataType":"REALTIME"' in COMPACT  -> True
b'"DataType":"REALTIME"' in SPACED   -> False   ← TC4 若哪天送帶空白的 JSON
```

TC4 是 Windows 桌面 app 的黑箱輸出,格式不是契約。
**needle 對不上 = 全市場資料靜默消失,畫面凍住,零錯誤訊號**,而它的 fail 方向是 fail-closed(最糟的那個方向)。

**更值錢的招報告沒看到**:同樣是 bytes 預判,**判 symbol 而不是判 DataType**。我實測:

| | best |
|---|---|
| 單一 symbol needle 命中 | 0.179 µs |
| 未命中(掃完整則) | 0.263 µs |

一條 session 判掉「不是我的」訊息,省下 `decode+loads` 5.9 + `parse` 2.3 + `call_soon_threadsafe` 8.1 ≈ **16 µs**,
成本 0.26 µs。四條 session × 16 µs = **每則省 ~64 µs**,是 Step 3 現寫法的數十倍。
(fail 方向也較好:needle 對不上 → 該 session 收不到自家資料,而 R1 自癒 watchdog 會立刻叫。)

### Step 3 vs Step 9 —— **做了一個,另一個白做**

報告 Step 3 的 risk 欄自己寫:

> `tcoreapi_mq.py` 是 gitignored 的 vendored 檔,**改它要先解決 Step 9 的供應鏈問題**

然後把 Step 3 排在 Step 9 **前面六步**。而 Step 9 的收益欄寫:

> 五條 KeepAlive 執行緒與其 ZMQ Context **直接不起**

**KeepAlive 執行緒不起了,Step 3 的 KeepAlive 半邊 100% 是白工。**
listener 半邊也大部分被吸收(單 reader 只 decode 一次,×5 的放大消失,
Step 3 剩下的價值 = 單執行緒上跳過 PING 的 ~0.17 µs/則)。

**結論:Step 3 應該併進 Step 9,或在 Step 9 之後只保留「symbol 預篩」那一版。
現在的順序是純浪費。**

### Step 9 —— 六條前置**漏了會讓五條 session 全死的那一條**

`spikes/TCPY/tcoreapi_mq.py:84-91`:

```python
def Pong(self, sessionKey, id = ""):
    self.lock.acquire()
    obj = {"Request":"PONG","SessionKey":sessionKey, "ID":id}
    self.socket.send_string(json.dumps(obj))
    ...
```

Pong 是 **per session** 的(帶 `sessionKey`),走**該 session 的 REQ socket + api.lock**。
單 reader 把 KeepAlive 執行緒關掉之後,**必須自己對五個 session 各發一次 Pong**,
否則 TC4 判五條全部逾時斷線。報告列了六條前置(`_last_msg` / `_last_push` / `_sub_at` /
`handle_raw` 薄轉接 / sub_port log / 不動 §4 契約),**沒有這一條**。
漏掉的失效不是靜默的(整批斷線很吵),但它是「這個重構會不會一上線就炸」的分水嶺。

### Step 7 —— 「刪 `energyFrom`」措辭會打爆副圖

`energyFrom`(`stock-intraday-svg.ts:313`)有**兩個呼叫點**:

- `:340` `buildEnergyBars` → `StockIntradayChart.tsx:1625` `<EnergySub bars={subEnergy.bars} …>` **真的在用**
- `:418` `buildIntradayGeometry` 內 → `:516-517` 放進回傳物件的 `energyBars` / `maxTotal`

我 grep `frontend/src/` 非測試檔的 `.energyBars` —— **零命中**。
所以「**geo 的 energyBars 零消費者**」語意 CONFIRMED ✓,
但**照「刪 `energyFrom`」的字面做,副圖整條死**。
正確寫法:「刪 `buildIntradayGeometry` 內的 `energyFrom` 呼叫與回傳物件的兩個欄位」。

其餘三項(`windowedEntries` 算兩次 17.5 µs×2、`areaPolygon` 的 `toFixed` 佔 48%、
`haveMinutes` 惰性)來源是 `_MISSED-143.md:217-219`,標「實測」屬實 ✓。

「主圖 accum 停止養沒有讀者的 tape(`App.tsx:181`)」:`App.tsx:181` 的
`{ tape: stockView !== "group" }` **只控制 REST 快照**(`useStockStream.ts:109` 加 `tape=0`),
`applyTick` 仍然無條件 `[...acc.ticks, x].slice(-200)`。所以這一項確實還沒做 ✓,
但我實測它只佔 `applyTick` 的 **0.1–10.6%**(tape 0.53 µs / 全趟 10.5 µs),
和同一張表裡 25% / 48% 的項目放在一起會讓人高估。

### Step 8 —— 「82% 在 `new Map(acc.minutes)`」**只在一種形狀下成立**

我用 node v24(與 Chrome 同 V8)逐字複刻 `applyTick` 拆解(`v1_applytick.mjs`):

| 形狀 | 全趟 | minutes | **vp** | tape | spread |
|---|---|---|---|---|---|
| 主圖滿載(271 / vp 124 / tape 200) | 10.56 µs | **73.9%** | 26.5% | 5.0% | 0.2% |
| **低價股 autofit(271 / vp 900 / 200)** | 38.44 µs | **21.4%** | **68.5%** | 1.7% | 0.0% |
| **群組卡片(271 / vp 900 / tape 0)** | 38.62 µs | **20.0%** | **77.7%** | 0.1% | 0.1% |
| 早盤(60 / vp 100 / 200) | 5.53 µs | 25.8% | 51.9% | 10.6% | 0.2% |

「82%」只在 vp 小的那一格接近(我量 73.9%)。
**在成本最高的兩格(38 µs),`new Map(acc.vp)` 才是大頭(68–78%),minutes 只有 20%。**
而 `vp` 會多大,`stock-accum.ts:451` 的註解自己寫著:
「**不是固定的 ~200** …… autofit 的低價股(tick 0.01 元)可以近千檔」。

**照 Step 8 只改 minutes:輕載省 74%、重載只省 21%。而 Step 8 的 effort 標 M
(要改所有讀 `minutes` 的地方)—— 花 M 的力氣買最壞情境 21%,CP 值判斷是錯的。**

「換 index-offset 陣列便宜 **67 倍**」我也量了:

| | best |
|---|---|
| `new Map(m271)` 複製 | 9.63 µs |
| `Float64Array(271×7).slice()`(真 columnar) | 3.13 µs → **3.1x** |
| `Array(271 個物件).slice()`(淺拷) | 0.144 µs → **67x** |

**67 倍只對「陣列裝物件的淺拷」成立**,而那不是 columnar,
而且要另外處理 per-minute cell 的 copy-on-write(現在 `applyTick` 是建新 cell 物件,淺拷可行)。
報告只寫「換成 index-offset 陣列便宜 67 倍」,沒說是哪一種,**照 Float64Array 做會發現只有 3x**。

### Step 8 漏了更便宜的那一步:**批次化**

`F1-stream-hotpath.md:415 F1-03` 提了 `applyTicks(acc, items)`(一則打包一次 immutable 複製),
**報告完全沒收**。我實測(主圖滿載 271/124/200):

| 打包筆數 | 逐筆 `applyTick` | 批次 `applyTicks` | 倍數 |
|---|---|---|---|
| 1 | 13.9 µs | 15.8 µs | 0.88x(略慢) |
| 5 | 65.6 µs | 11.4 µs | **5.8x** |
| 20 | 274.2 µs | 17.3 µs | **15.9x** |
| 50 | 712.3 µs | 13.4 µs | **53x** |

`tick_flush_secs = 0.1 s`,開盤 2330 可到 20–50 筆/秒 → **每則打包 5–5 筆以上是常態**。
批次化:**一支新函式、`minutes` 仍是 Map、零契約改動、effort S**,
收益比 Step 8(effort M、要動所有 `minutes` 讀者)大一個量級。

**Step 8 應該改成:先做 `applyTicks` 批次化(S),量完再決定要不要動容器。**

### Step 1 —— 前提 CONFIRMED,但只解了一半

`app.py:1003` `broadcast=corr_ws.publish` —— **在 boot 綁上,與有沒有人看無關** ✓,
所以「零 WS client 時照算 12.7–13.7 ms」的前提成立。

但 **有人看的時候那 13 ms 還在**,而它每秒一次,直接排在閃電梯的 book 前面(見 §2)。
報告把它列在「抖動源」而不是「閃電梯延遲源」,所以 Step 1 只加閘不修算式。
**這是 §5「換工具」該進來的地方**(見下節)。

---

## 5. 以「TC4 會員無上限、可同時打多隻 API」重評

先把兩件事分開(user 的提示是對的):

- **(a) TC4 服務端併發許可 —— user 說無上限。**
- **(b) ZMQ REQ socket 是嚴格 lockstep —— 協定強制,和配額無關。**
  `tcoreapi_mq.py` 的 `TCoreZMQ` 用 `self.lock` 包住 `send_string` + `recv`,
  這把鎖**不可能拿掉**,只能**開更多顆 socket / 更多 session**。

### 對這份報告的具體影響

1. **本報告沒有任何一條結論建立在「TC4 有併發上限」上** —— 它根本沒討論取數併發。
   所以**新事實不推翻這份報告的任何一條**。但它**開啟了一條這份報告完全沒有的路**:

2. **新增的最大機會:回補走獨立 session。**
   報告 §2.3 把 `apply_backfill` 重放(9.9–32.4 ms)列為抖動源、
   失效模式 #12 把「TC4 半死拖垮共享 executor、連帶卡住 `bars_range`」列為風險 ——
   兩條指向同一件事:**開盤 150 檔回補與盤中看盤取數擠在同幾顆 REQ socket 上**。
   既然 TC4 併發無上限,正解是**替回補開專用 session(一顆或多顆自己的 REQ socket)**,
   讓它完全不碰看盤那幾條的 `api.lock`。**報告的 Step 0–10 沒有這一條。**

3. **Step 9(單 reader)不受影響、仍然值得做** —— 它省的是**本機 CPU / GIL**(五份重複解碼),
   不是 TC4 的配額。新事實既不強化也不削弱它。

4. **Step 9 的方向要注意不要走反:** 「無上限」誘人把 session 開更多,
   但**推播側(SUB)開更多 session 只會讓每則訊息被解碼更多次**。
   正確的形狀是:**推播側收斂成一條 reader(Step 9),取數側(REQ)放開成多條。**
   報告只寫了前半,沒寫後半。

---

## 6. 以「前端後端都要用計算最快的工具」重評

報告 §0 / §5 的立場:「**最大收益全部是刪掉重複工作、零新相依**」,
§5 明列「換 numpy 只會變慢」「對它用 numpy 是純過度工程」。

**這個立場在 user 的新目標下有三處站不住,而且我有實測。**

### (1) `json.dumps` —— 這是最硬的一條

`starlette/websockets.py:174` 逐字 `json.dumps(data, separators=(",",":"), ensure_ascii=False)`
→ **stdlib、純 Python 路徑、在 event loop 上、每個 client 各一次**。

我實測(`v1_ws.py`,逐字同參數):

| 打包筆數 | stdlib `json.dumps` | `orjson.dumps` | 倍數 |
|---|---|---|---|
| 1 | 2.29 µs | 0.17 µs | 13.5x |
| 10 | 9.33 µs | 1.11 µs | 8.4x |
| 30 | 26.56 µs | 4.77 µs | 5.6x |
| **300(開盤)** | **375.69 µs** | **44.82 µs** | **8.4x** |

8 個分頁、10 則/s、開盤 300 筆:**30 ms/s → 3.6 ms/s**。
**這比報告 Step 1–8 全部加起來省得還多**,而它是一行 `send_text(orjson.dumps(m).decode())`。

ingress 側(`v1_codec.py`):`json.loads` 4.45 µs → `orjson.loads(bytes)` **1.52 µs(2.93x)**、
`msgspec.json.decode` 1.93 µs(2.31x)。現況 10 條執行緒(5 listener + 5 KeepAlive)
每則共 22.2 µs → 7.6 µs。

**「零新相依」這個框架本身是假的**:`pyproject.toml` 的 `dependencies = []` 只管 core package,
`[project.optional-dependencies].live` 已經有 fastapi / uvicorn / pyzmq。
`_MISSED-143.md` 已經指出這點,**報告沒收**。

**誠實的反面**:REST 路徑不用改。我量過 FastAPI 0.139 的真實鏈
(`routing.py:322` `field.serialize_json`,pydantic-core Rust):150 檔 4.09 MB
**dump_json 19.4 ms**,orjson 7.6 ms 只有 2.6x,不值得為它動 response class。
**WS 才是問題,REST 不是** —— 這個區分報告和我都該寫清楚。

### (2) `CorrState.correlations()` —— 該上 numpy 的是這裡,不是 RiverState

`corr_state.py:133` 用 `statistics.correlation` —— **純 Python**,
外層兩層迴圈(11 腿 × 3 窗)+ 每窗兩次 list comprehension 掃 3600 筆。

我實測同語意的 numpy 版(`v1_corr.py`,11 腿 / 窗 60,300,3600 / 3600 樣本):

| | best |
|---|---|
| 現況 `statistics.correlation` | **8.955 ms** |
| `np.corrcoef` 同語意 | **0.909 ms** |
| | **10x** |
| 逐值最大差 | **1.388e-16** |

**逐值差 1.4e-16 = 可以寫 golden fixture 釘死的等價替換。**
這一格每秒都在跑,而且排在閃電梯前面。報告 §5 的「不要動」清單把 numpy 的否定
寫在 `RiverState 的分鐘桶 dict`(那條我同意,稀疏整數鍵 dict 對 numpy 不利),
**但 `CorrState` 是密集浮點時間序列 —— 教科書級的 numpy 場景,報告沒分辨。**

Step 1 的 `has_clients` 閘仍然要做(省掉沒人看時的成本),
但**它不能取代把 13 ms 降到 0.9 ms**,因為有人看的時候那 13 ms 就落在真錢畫面前面。

### (3) 前端:`<canvas>` 連被列為選項都沒有

§4 Step 10 寫「**先做降採樣,不是 `<path>` 化,也不是換圖表庫**」。
以「effort 最小」為準則這是對的,以「**計算最快**」為準則不是:
50 卡 × 271 `<rect>` ≈ 13,550 個常駐 DOM 節點,
**一張 `<canvas>` 把它變成 0 個 DOM 節點 + 一次 `fillRect` 迴圈**。
報告的「不要換圖表庫」我同意(圖表庫會把手刻的幾何語意分支全丟掉),
但 **canvas ≠ 圖表庫** —— 幾何算式一行都不用動,只換 renderer。
報告連把它列進選項都沒有,`_REFUTED` 清單也只駁回了 Web Worker / zustand / React Compiler。

### (4) 報告說對的部分(我不推翻)

- `market.py` 毫元整數 tick 表 —— **不要動**,有跨語言 parity 契約且影響下單價格 ✓
- `stock_state.py::_apply` 1.96 µs —— 增量 O(1),換 numpy 確實只會變慢 ✓
- `ws.py` 同步 fanout —— 「慢 client 拖不垮別人」的唯一保證 ✓
- `to_milli_units` 的 Decimal —— 截斷 vs banker's rounding 在 tick 邊界分岔,不可換 float ✓
- `React Compiler` —— 會凍住刻意不進 memo 的牆鐘計算 ✓

---

## 7. 引用位置與零星錯誤

| 報告 | 實際 | 影響 |
|---|---|---|
| Step 6「`searchStocks` 包 `useMemo` \| `WatchlistSidebar.tsx:195`」 | 路徑是 `frontend/src/components/stock/WatchlistSidebar.tsx:195`(行號對 ✓);**同一個問題在 `WatchlistManagerDialog.tsx:170` 也有一份,報告漏** | 施工會漏改一半 |
| Step 6「`TxoPage` / `IndexPage` 包 memo \| `App.tsx:121-129`」 | 121-129 是 `visited` 的 `useState`(只是「恆掛載」的**證據**,不是要改的地方) | 讀者會去錯地方 |
| §2.4「每檔當日 tick:90 檔、381,107 筆、median 2,247、最熱 30,598」 | 我重跑同一份 log:**89 檔、380,606、median 2,834、max 30,598**。max 逐字相符、總數差 0.13%、**median 兩種算法都不是 2,247** | 低 |
| §2.1 #15「52.75–101.46 µs」 | 下界是「無 ref」的反事實;`F1` 對同函式量到 126 µs | 會低估幾何成本 ~25% |

---

## 8. 建議的修正順序(取代報告 §4)

保留 Step 0(裝儀器)為第一步 —— **這一條完全同意,而且它自己就能解掉報告的兩個關鍵未知數**。
其後改成:

| 新序 | 動作 | 依據 | 對報告的關係 |
|---|---|---|---|
| 0 | 裝儀器(照原 Step 0)**+ 加 `book` 則數計數 + 加 `send_json` 計時** | 原 Step 0 已有前兩項 | 補 #11 |
| 1 | **WS egress 換 orjson**(`send_text(orjson.dumps(m).decode())`) | 實測 5.6–13.5x,開盤 30 ms/s → 3.6 ms/s | **報告沒有** |
| 2 | `applyTicks` 批次化 | 實測 N=20 → 15.9x,effort S,零契約 | **報告沒有**(F1-03 有) |
| 3 | corr/river `has_clients` 閘 **+ `correlations` 換 numpy** | 實測 10x,逐值差 1.4e-16 | 原 Step 1 只做一半 |
| 4 | `book` 去重 **+ 週期無條件重送 keepalive** | 實測比較 0.05 µs;keepalive 補上去重帶進的靜默洞 | 原 Step 2 + 修正 |
| 5 | parse 微優化(`_taipei_time` 整數化 / `StockMeta` dirty-check / `slots=True`) | 我實測 `_taipei_time` 7.45 µs,與報告 7.37 相符 | 原 Step 4,**提前** |
| 6 | 前端死工純刪(**改寫成「刪 geometry 內的 energyFrom 呼叫」**) | 原 Step 7 | 措辭修正 |
| 7 | 前端 memo 邊界 | 原 Step 6 | 不變 |
| 8 | **回補開專用 TC4 session**(新事實解鎖) | 失效模式 #12 + 抖動源 `apply_backfill` | **報告沒有** |
| 9 | 單 reader 重構(**併掉原 Step 3**,前置補「代五個 session Pong」) | 原 Step 9 | 合併 + 補前置 |
| 10 | `applyTick` 容器(**先解 `vp` 再解 `minutes`**) | 實測重載時 vp 佔 68–78% | 原 Step 8 修正 |
| 11 | SVG 降採樣 / **canvas** | 原 Step 10 + canvas 選項 | 補選項 |

---

## 9. 附:量測腳本

| 檔 | 量什麼 |
|---|---|
| `v1_bench.py` | book 去重比較、`parse_stock_realtime`、listener 解碼、`parse_realtime` 對個股電文、`_taipei_time` |
| `v1_bench2.py` | Step 3 bytes 預判(命中 / 未命中 / needle 格式敏感性)、symbol 預篩、KeepAlive |
| `v1_applytick.mjs` | `applyTick` 逐段歸因(四種形狀)、批次化對比、容器替換 |
| `v1_codec.py` | orjson / msgspec vs stdlib(ingress + egress + group payload) |
| `v1_ws.py` | `starlette send_json` 逐字同參數的 per-client 序列化成本 |
| `v1_rest2.py` | FastAPI 0.139 真實 REST 鏈(pydantic-core dump_json)—— **證明 REST 側不用改** |
| `v1_corr.py` | `statistics.correlation` vs `np.corrcoef`(含逐值等價核對) |

**未動 repo 任何檔案、未動專案 `.venv`、未起 server、未下任何單。**
