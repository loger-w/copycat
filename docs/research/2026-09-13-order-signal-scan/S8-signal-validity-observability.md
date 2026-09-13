# S8 — 訊號:量化有效性、時間語意與可觀測性

掃描日期:2026-09-13(週日,盤後)· 範圍:橫向統整 S1–S7 的訊號段,對照
`docs/strategy.md`、`CONTEXT.md` §訊號政策層、研究基準 `Documents\copycat-trading-review\HANDOFF-2026-09-06-signal-research.md` §8。

**未改動 repo 任何檔案、未啟動 server、未下任何單。** 量測腳本留在
`<scratchpad>\order-signal-scan\`:`bench_s8.py`(序列化 / 落檔 / 時鐘元件)、
`ms_vs_sec.py`(毫秒 vs 秒解析度對照)、`reconcile_shadow.py`(影子期對帳劇本原型)、
`bench_policy.py`(政策層成本)。資料來源 = `data/signals/*.jsonl`(26 個交易日 / 8,003 列)、
`logs/server-*.log`、`tests/fixtures/sweep_cluster_golden.json`。

---

## 0. 一句話結論

訊號層的**演算法寫得很好、lookahead 防護是乾淨的**(§4 S8-12,實證),但它建立在
**三個沒人量過的時間假設**上,而三個現在都被 prod 資料推翻:

1. **「同毫秒群」在 prod 其實是「同秒群」** —— TC4 live 推播的 `PreciseTime` 毫秒**恆為 000**
   (實測 7,852 / 7,852 條 tick 路訊號列,零例外)。golden fixture 釘的是研究歷史 tick 的
   **真毫秒**(98.8% 非零),也就是說 **parity 驗的是 prod 從來不會產生的輸入形狀**。
   把 fixture 的 tick 截成秒重跑,同一批 tick 的事件數 11 → 9、時刻最多位移 41 秒。
2. **本機時鐘沒有任何紀律**(`W32Time` 服務 **Stopped**)且**落後**交易所時鐘 ——
   09-11 收盤撮合那一筆(tick 時刻 `13:30:00`)穿過了本該把它擋掉的 `_in_session` 13:30 界,
   產出 4 則假的爆量訊號。
3. **盤中重啟 = cooldown / latch / suppressed / 政策當日計數全失憶**,而 jsonl 裡**沒有斷點記號**。
   實測:09-08 / 09-10 / 09-11 三次盤中重啟各產出 **8 / 43 / 28** 則本該被冷卻擋掉的重複發訊;
   09-07 / 09-09 的盤前重啟 **0 則**(乾淨對照組)。

而**影子期四週的對帳現在跑不完**:B-a 政策五個交易日 **0 命中**(§4 S8-07)、三桶對帳的另外
兩桶靠 repo 外一份 09-05 就停更的 `fills.json`(§4 S8-08)、研究基準的出場口徑(放到尾盤)
與拍板的實單口徑(T+1 開盤出)不是同一件事(§4 S8-09)。**這三件不在影子期結束前補,
四週就是白跑。** §6 給了一份現在就能跑的對帳劇本原型與它缺的欄位。

反過來:**政策層純函式、雙佇列 fanout、回填的逐行 byte 保留、Discord 降級三態
—— 這幾塊不要動**,理由見 §8。

---

## 1. 現況地圖(以時間語意為主軸)

### 1.1 三條時間軸,系統同時在用

| 軸 | 取得方式 | 用在哪 | 解析度(prod 實測) |
|---|---|---|---|
| **交易所時刻**(tick 時刻) | TC4 `PreciseTime`(UTC)→ `stock_models._taipei_time` → `StockTick.time` = 台北 `HH:MM:SS.fff` | 掃單簇的**同毫秒群 / 簇窗 / 60 s 回看窗**;`SignalEvent.time_key`(tick 路);政策層 `late` / `tod` 判定 | **秒**(毫秒恆 `.000`) |
| **本機牆鐘** | `SignalHub._now_fn = datetime.datetime.now`(app 未注入,走預設) | `_in_session` 盤中窗閘、`_mono` 的窗軸(surge / 爆量 / 爆拉回檔)、**全部 cooldown**、CDP rearm 駐留、`_clock_key`(簿路 `limit_open` 的 `time_key`)、回填 worker 的 13:40 時點、Discord 每分鐘節流、jsonl 檔名日別的一半 | 微秒(`datetime.now()` 相鄰不同值 p50 = **0.0010 ms**,走的是 `GetSystemTimePreciseAsFileTime`,**不是** 15.6 ms 的 timer 精度) |
| **引擎交易日** | `engine.trade_date`(兩段式 rollover,stage2 才前進) | `TickContext.trade_date`(舊日 snapshot gate)、`_event_id` 的日期段、jsonl 檔名、回填 cutoff | 日 |

**`_clock_key` / `_mono` / `_now_fn` 的實際分佈**(`copycat/live/signal_state.py`):

```
signal_state.py:301   now = self._now_fn()          # evaluate 入口,本機
signal_state.py:302   if not self._in_session(now)  # 本機 09:00–13:30(end-exclusive)
signal_state.py:305   mono = _mono(now)             # 本機,秒純量
signal_state.py:306   key = tick.time or _clock_key(now)   # ← 交易所時刻優先,缺才退本機
signal_state.py:345-348  evaluate_book:now / mono / key = _clock_key(now)  # ← 全本機
```

也就是說:**成交路的事件時刻是交易所時鐘,簿路(`limit_open`)的事件時刻是伺服器時鐘**,
而兩者寫進同一個 `time_key` 欄、同一個 `id`。這在 prod 資料上看得一清二楚:

```
非 .000 毫秒的訊號列:{'limit_open': 69}            ← 簿路,伺服器鐘
= .000 毫秒的訊號列 :{'cdp_cross': 3994, 'surge': 963, 'crash': 658,
                      'limit_lock': 176, 'vol_burst': 480, 'surge_pullback': 1225,
                      'sweep_cluster': 205, 'policy': 151, 'limit_open': 22}
```
(26 個交易日全量;`limit_open` 22 則 `.000` 是 tick 路那半 —— 同一個 kind 的兩半走兩把尺。)

### 1.2 資料流(從時間語意看)

```
交易所撮合 ──(不可量:tick 時刻只有秒,且本機鐘未校)──▶ TC4 桌面 app
   │
   ▼ ZMQ SUB(五條 session 共用 PUB 廣播)
listener thread:decode + json.loads(4.9 µs)+ _note_push
   │ loop.call_soon_threadsafe(8.56 µs;Proactor 自管道 write)
   ▼ ── 自此全部在 event loop 單執行緒 ──
_handle_quote(stock_engine.py:1300+)
   ├ state.ingest(tick)    ← 試撮窗 / 重複 tick 在此短路(回補重放不走這條)
   ├ hub.on_tick(code, tick, state)      ← 7 顆 detector × evaluate      94.6 µs/tick(B06 實測)
   │     └ _emit ─┬ _publish(WS,同步)   ← 唯一「即時」的一條
   │              ├ _enqueue → jsonl 有界佇列(1000)→ worker → to_thread → 205 µs/則
   │              ├ _enqueue → Discord 有界佇列(100)→ 合批 → 每分鐘 30 則節流
   │              └ (kind == sweep_cluster) _emit_policies  ← 政策層 7.8 µs/事件
   └ hub.on_book(code, state)            ← 7 顆 evaluate_book             23.9 µs/quote
背景:_basis_worker(CDP 基準)/ _jsonl_worker / _discord_worker / _policy_outcome_worker(13:40)
```

**三條真相源的時間語意各不相同**:WS 是「當下」(無時戳);jsonl 列上**只有交易所 tick 時刻**
(`time`,秒級),**沒有任何本機時戳** —— 這是 §5 延遲可觀測性為零的根因;Discord 的時間
是 Discord 伺服器蓋的。

### 1.3 prod 規則集(經 `load_rules` 實跑,不是讀那份過期檔)

`data/signal_rules.json` 仍是 **2026-08-15 的 `_cache_version: 1` / 4 條**,每次開機走
`v1→v2→v3→v4` 遷移鏈在**記憶體**變成 7 條(09-11 log 64–69 行逐條可見),**從不落檔**:

| rule_id | kind | 名稱 | enabled | notify | cooldown | 關鍵 params |
|---|---|---|---|---|---|---|
| r-1785975520-000 | cdp_cross | CDP 穿越 | ✔ | ✘ | 600 | rearm_ticks 5 / dwell 300 |
| r-1785975520-001 | surge_crash | 爆拉爆跌 | ✔ | ✔ | 1800 | pct 2.0 / window 300 |
| r-1785975520-002 | vol_burst | 爆量 | ✔ | ✘ | 1800 | ratio 3 / window 300 / min_elapsed 15 |
| r-1785975520-003 | limit_lock | 鎖漲跌停 | ✔ | ✔ | 600 | — |
| r-1789276016-004 | surge_pullback | 爆拉回檔 1% | ✔ | ✔ | 60 | surge 2.0 / pct 1.0 |
| r-1789276016-005 | surge_pullback | 爆拉回檔 2% | ✔ | ✔ | 60 | surge 2.0 / pct 2.0 |
| r-1789276016-006 | sweep_cluster | 掃單簇 | ✔ | ✘ | 60 | 30 s / ≥2 掃單 / ≥2 層 / +0.3% / 60 s |

`configs/signals.json` **不存在** → `SignalsConfig` 全走預設(`policy_exclude_groups = ("ALL IN",)`、
`policy_push_end 12:30:00`、`policy_outcome_time 13:40:00`、`policy_outcome_days 5`)。

> 我**無法重現** prompt 裡「`rule_config()` 會 KeyError」那條:以 repo 內 `.venv` 實跑
> `load_rules(Path('data/signal_rules.json'))` 正常回 7 條,`rule_config` 也正常。
> 該檔是舊版但遷移鏈吃得下來,不是壞檔。

### 1.4 量級(影子期 5 個交易日 09-07..09-11 實測)

| kind | 列數 / 日 | 去重事件 / 日 | 放大 |
|---|---|---|---|
| cdp_cross | 253.2 | 252.2 | 1.00 |
| surge_pullback | 164.4 | 163.2 | 1.01 |
| surge | 54.4 | 54.4 | 1.00 |
| sweep_cluster | 41.0 | 41.0 | 1.00 |
| vol_burst | 40.6 | 40.6 | 1.00 |
| crash | 35.4 | 35.4 | 1.00 |
| **policy** | **30.2** | **26.4** | **1.14** |
| limit_lock | 7.2 | 7.2 | 1.00 |
| limit_open | 3.0 | 3.0 | 1.00 |

**合計 629 列 / 日,其中 `notify=true` 283 列 / 日**(= Discord + toast + 嗶 + 桌面通知)。
政策列的 1.14 放大 = 同一顆掃單簇事件同時命中 P 與 S(19 / 151 列),**對帳要先去重**。

---

## 2. 端到端延遲預算

口徑:一筆成交從交易所撮合到(a)瀏覽器 rail 亮燈 /(b)jsonl 落檔 /(c)Discord 卡片。
`基準` 欄標明 **實測 / 推估 / 不可量**。所有 µs 級數字皆以 repo 內 `.venv`
(CPython 3.13.13 / Windows 11)實跑。

| # | 區段 | 位置 | 成本 | 基準 | 備註 |
|---|---|---|---|---|---|
| L1 | 交易所撮合 → TC4 app 收到 → ZMQ PUB | TC4 桌面 app(黑箱) | **不可量** | 不可量 | tick 時刻只有**秒**解析度(§4 S8-01),且本機鐘未校(S8-02)→ 連「本機收到時 − 交易所時刻」這個最基本的差都算不準 |
| L2 | ZMQ recv + decode + `json.loads` | `tc4.py:1225 _listen_loop` | **4.90 µs**/則 | 實測(X3) | listener thread,非 loop |
| L3 | `call_soon_threadsafe` 跨界 | `stock_engine.py:1147` | **8.56 µs**/則 | 實測(X3) | Proactor 自管道 write syscall,一則一次 |
| L4 | loop ready-queue 等待 | event loop | **0 ~ 130 ms**(常態);最壞 **~20 s** | 實測(X3)/ 推估 | 130 ms = `group_snapshot` 每分鐘兩次的實測停擺;20 s = 共用 20-worker executor 被不可中斷的 TC4 歷史取數塞住 |
| L5 | `state.ingest` + ticks 打包 | `stock_engine.py:1316` | ~2 µs | 實測(B05:`_apply` 1.96 µs/tick) | — |
| L6 | `hub.on_tick` ctx 組建 + 7 顆 detector evaluate | `signal_hub.py:598` / `signal_state.py:292` | **94.6 µs**/tick(窗長 1501) | 實測(B06 bench2) | 其中 `vol_burst` 的 `sum()` 佔 69.7 µs;成本 ≈ 0.046 µs × 窗長 → **越爆量越慢** |
| L7 | `hub.on_book` 7 顆 evaluate_book | `signal_hub.py:616` | **23.9 µs**/quote | 實測(B06 bench3) | 其中 `_clock_key` 的 strftime 佔 63%(本機實測 1.62 µs × 7) |
| L8 | 政策層(只在掃單簇事件) | `signal_policy.py` | **7.8 µs**/事件(resolve 1.87 + evaluate 5.95) | 實測(bench_policy.py) | 41 事件 / 日 → **全日 0.32 ms**,零最佳化空間 |
| L9 | `_emit` payload 組裝 + `WsBroadcaster.publish` fanout | `signal_hub.py:1012` / `ws.py:65` | ~5 µs + N × 0.2 µs | 推估 | publish 只 put dict,不編碼 |
| L10 | WS 每 client `send_json` | starlette | **2.77 µs**(一般列)/ **5.44 µs**(政策列)× N client | 實測(bench_s8.py) | per-client 各編碼一次;8 條 WS = 同一則編 8 次 |
| L11 | WS → 瀏覽器 → rail 亮燈 | 前端 | ~1–5 ms | 推估 | 本機 loopback;F1/F7 區塊 |
| L12 | `_enqueue` → jsonl 佇列 → worker → `to_thread` → open/write/close | `signal_hub.py:1186,1412` | **205 µs**/則(NTFS 實測)+ thread-pool 往返 ~50–100 µs;**排隊時間 0 ~ 20 s** | 實測 + 推估 | 佔用**共用** 20-worker executor 一格,鄰居是不可中斷的 TC4 取數 |
| L13 | Discord 合批 + 每分鐘 30 則節流 + bot / webhook | `signal_hub.py:1198,1486` | **0 ~ 60 s**(節流窗)+ 網路 | 推估 | 節流滿時該則只進 WS/jsonl(有 WARNING) |
| L14 | T+1/T+2 回填(每日 13:40 一次) | `signal_hub.py:1280` | **4.3 s**(09-11 log 實測,61 列 / 5 個日檔);其中 loop 上逐行解析 **2.43 ms × 日檔數** | 實測 | `_fetch_outcome_bars` 的 0.2 s/檔 gap 是主成本 |
| L15 | `read_signals` 全檔(`/api/stock/signals/today`,每 5 分鐘 × 每個分頁) | `signal_hub.py:1448` | **3.23 ms**/次(686 列 / 289 KB) | 實測 | 已在 `to_thread`,但同樣是共用 executor |

**可加總的「熱路徑」總計**(一筆帶成交的 quote,7 條規則,窗長 1501):
L2 + L3 + L5 + L6 + L7 + L9 ≈ **134 µs**,其中 **訊號層佔 118 µs = 88%**。
在 event loop 上的部分(L3 之後)= **125 µs**。

**這個預算最重要的一件事:L1 與 L4 兩段 —— 也就是**真正決定訊號早晚的兩段 —— **現在完全量不到**,
而 L6/L7 這些量得到的微秒級成本加起來還不到 L4 常態抖動(130 ms)的千分之一。
**先把 L1 / L4 變成可量,再談把 L6 從 94.6 µs 優化到 12 µs。**

---

## 3. 失效模式表

**「零錯誤訊號」= 發生時沒有任何 log / 例外 / 畫面異常,只能靠事後翻資料才發現。**

| # | 失效模式 | 觸發 | 症狀 | 零訊號 | 嚴重度 | 現在怎麼發現 |
|---|---|---|---|---|---|---|
| FM-01 | 「同毫秒群」退化成「同秒群」 | 恆常(TC4 live `PreciseTime` 毫秒恆 000) | 掃單簇的群含整整一秒的成交:`outer` 只由該秒首筆決定、層數橫跨整秒高低;事件集合與研究定義不同(fixture 實測 11 → 9 則、時刻位移最多 41 s) | **是** | critical | 現無。要加:啟動時抽樣 tick 的毫秒分佈,全 000 就 WARNING;fixture 加一組「毫秒截秒」案 |
| FM-02 | 本機鐘落後 → 收盤撮合那一筆穿過 `_in_session` 13:30 界 | 本機鐘落後量 > 推播延遲(W32Time 未跑,漂移無上界) | 13:30:00 的收盤撮合大量被當盤中爆量,產出假 `vol_burst`(09-11 實測 4 則) | **是** | high | 現無。判準:`grep '"time": "13:30' data/signals/*.jsonl` 應為 0 |
| FM-03 | 本機鐘**超前** → 開盤前幾秒的 tick 被 `_in_session` 擋掉 | 同上,反向 | 09:00:00.xxx 的開盤集合競價整批不評估;該檔當天首個窗基準點整個位移 | **是** | high | 現無。判準:每日首則訊號時刻若恆 > 09:00:0X 就是它 |
| FM-04 | 盤中重啟失憶 → 冷卻 / latch / suppressed / 政策當日計數全部歸零 | 任何盤中重啟 | 8–43 則重複發訊(實測);`first_of_day` 不再是「當日第一次」;政策列會重推一次 | **是**(id 不同,去重擋不住) | high | 現無斷點記號。判準見 §6 步驟 3 的冷卻違反檢查 |
| FM-05 | 重啟期間的 `limit_open` 永久遺失 | 重啟時某檔正好打開漲停 | latch 為 False → 打開不發;該檔當日再也不會有那一則 | **是** | high | 現無 |
| FM-06 | 政策列 T+1/T+2 永久 null | 連續 3+ 個交易日沒跑到 13:40 回填(收盤前關機 / 沒開 server) | 該日檔掉出「最近 5 個日檔」窗,永遠不再被掃到 | **是**(log 只印「共回填 0 列」,與健康的無事可做**同字串**) | high | 現無。判準:`t1_open` 仍 null 且日期 < 今天−2 交易日的列數 |
| FM-07 | 窗(surge / 爆量 / 爆拉回檔)用**本機收到時刻**,遇到推播積壓就壓縮 | L4 停擺(130 ms 常態)或更長的 loop 阻塞 | 一批積壓 tick 的 `mono` 幾乎相同 → 300 s 窗實際涵蓋的**交易所時間**比 300 s 長 → 漲幅 / 量比虛高 | **是** | medium | 現無。要加:窗兩端同時記 tick 時刻,兩者差 > 窗長 × 1.2 時 WARNING |
| FM-08 | `limit_lock`(交易所鐘)與 `limit_open`(伺服器鐘)配對算持續時間 | 任何離線分析 | 鎖停持續時間帶入一個未知常數偏差(= 本機鐘落後量) | **是** | medium | 現無。只能從 `id` 的毫秒位是不是 000 反推是哪一把尺 |
| FM-09 | B-a 樣本恆為 0 | 政策定義本身(B-a ⊂ B-b,且 prod 的族群同伴極稀薄) | 四週影子期結束仍無法對 B-a 下判斷 | 否(數得出來,但沒人在數) | high | `reconcile_shadow.py` 已印 `n=0` |
| FM-10 | 三桶對帳只剩一桶 | `fills.json` 停更(09-05,早於影子期起點 09-07) | 「訊號有他沒打 / 他打了沒訊號」兩桶無資料 | **是** | high | 檢查該檔 mtime;或改讀 repo 內 `data/audit/capital-*.jsonl` |
| FM-11 | 對帳把兩套出場口徑混著比 | 研究表 = 放到尾盤;拍板實單 = T+1 開盤出 | 「有沒有達標」的結論隨口徑翻面(實測 S @09:00–09:30 尾盤 −2,568 vs T+1 開 −935) | 否(但很容易犯) | high | §6 劇本兩套各算一次 |
| FM-12 | `d_high` 被當成前瞻 MFE | 任何用 `d_high` 算「最多能賺多少」的分析 | `d_high` 是**事件日全日**最高,含發訊**之前**的高點 → 系統性高估(實測 P +3.80% vs 尾盤 +0.80%) | **是** | medium | 欄名不說謊但也不說清楚;`d_close` 才是有效前瞻量 |
| FM-13 | 進場價系統性樂觀一檔 | 政策列 `price` = 掃單簇當筆成交價;研究進場 = 觸發後下一筆 +1 檔 | 每筆高估 ≈ **0.135%**(一檔佔價中位數,實測)+ 下一筆漂移 | 否(已列在 `signal_policy.py` docstring 差異 2) | medium | 對帳時整批扣掉 |
| FM-14 | TC4 斷線 / 引擎降級不進 jsonl | 盤中任何斷線 | 「那天沒訊號」與「那天沒資料」在離線讀者眼裡一模一樣 | **是** | medium | 只能翻 `logs/server-*.log` 對時間;jsonl 自己看不出來 |
| FM-15 | 改 `default_rules` / 遷移鏈 → 下次重啟靜默換規則集 | `data/signal_rules.json` 仍是 v1,遷移每次開機重跑 | prod 規則(含門檻、`notify`)在無人編輯的情況下隨 code 變動 | 部分(遷移每步有 INFO,但沒有「最終規則集」那一行) | low | `curl /api/stock/signals/rules` 人工比對 |

---

## 4. Findings

### S8-01 【critical / 有效性】prod 的「同毫秒群」其實是「同秒群」,golden fixture 驗的是 prod 不存在的輸入形狀

**證據 1(prod 恆為秒解析度)**:26 個交易日全部 8,003 列訊號,由 `id` 尾段還原 `time_key` 的毫秒:

```
tick 路(evaluate)產出的 7,852 列 → 毫秒 100% 為 "000"
簿路(evaluate_book,_clock_key 本機鐘)產出的 69 列 limit_open → 毫秒非零
掃單簇事件 154 / 154 全為 "000"
```

**證據 2(研究資料是真毫秒)**:`tests/fixtures/sweep_cluster_golden.json` 的 2,172 筆研究 tick,
**2,147 筆(98.8%)毫秒非零**;500 筆 tick 有 392 個相異毫秒鍵、但只有 322 個相異秒鍵。

**證據 3(差異的量級,實測 `ms_vs_sec.py`)**:把 fixture 的 tick 時刻截到秒(= prod 形狀)後
重跑**同一顆** `SignalDetector`:

| 案例 | tick 數 | 研究毫秒解析度 | 秒解析度(prod 形狀) | 事件時刻差異 |
|---|---|---|---|---|
| 6715 / 2026-08-17 | 500 | 4(= fixture expected) | **3** | 09:20:43 → 09:20:35(位移 8 s),多一則掉了 |
| 1727 / 2026-08-05 | 920 | 5 | **4** | 09:06:50 → 09:07:31(位移 **41 s**) |
| 8103 / 2026-08-19 | 752 | 2 | **2** | 兩則時刻都只剩秒 |
| **合計** | 2,172 | **11** | **9** | 兩組**事件時刻集合都不相等** |

平均群大小從 1.14–1.28 放大到 1.53–1.60(放大 1.22–1.34×)。

**為什麼 parity 測試抓不到**:`tests/live/test_signal_state.py::TestSweepClusterGolden::_run`
直接把 fixture 的毫秒餵成 `time=_ms_time(ms)`,**並且把注入時鐘也設成同一個 tick 時刻**
(`clock.now = _ms_clock(base, ms)`)。所以那支測試同時做了兩件 prod 不成立的事:
(a) 毫秒是真的;(b) 冷卻的牆鐘軸與 tick 軸完全對齊。

**影響**:掃單簇是**政策層唯一的觸發器**(`_emit` 只在 `kind == "sweep_cluster"` 時叫
`_emit_policies`)。整個影子期的母體形狀因此與研究 1,883 股票日的母體形狀不同,
而研究算出來的 `+5,784/筆`、`鎖死 23%` 這些基準是在**毫秒母體**上算的。
再加上 §4 S8-13(96% 的事件卡在門檻正下緣),群長度放大 1.2–1.3× 正好打在最敏感的地方。

**這條 finding 不是「線上寫錯了」** —— `_eval_sweep` 逐字照 spec 實作、fixture 也真的綠。
問題在於**驗證用的輸入與生產用的輸入是兩種東西,而沒有任何一道閘會發現這件事**。

---

### S8-02 【high / 時間語意】本機時鐘零紀律且落後交易所鐘;13:30 收盤界被打穿

**證據 1(沒有時鐘紀律,實測)**:

```
Get-Service W32Time → Status: Stopped, StartType: Manual
w32tm /query /status → 0x80070426(服務尚未啟動)
```

Windows 11 Home 預設是「Automatic (Trigger Start)」;現況是 Manual + Stopped,
也就是**沒有持續的 NTP 校時**。一般 PC RTC 漂移 1–20 ppm = **0.1–1.7 秒 / 日**,
一週不校可以累積到 10 秒等級。

**證據 2(落後,方向明確)**:09-11 有 4 則訊號的 tick 時刻是 `13:30:00`:

```
('2026-09-11', '13:30:00', 'vol_burst', '2344')
('2026-09-11', '13:30:00', 'vol_burst', '2408')
('2026-09-11', '13:30:00', 'vol_burst', '2327')
('2026-09-11', '13:30:00', 'vol_burst', '3037')
```

`_in_session` 是 `_SESSION_START <= now.time() < _SESSION_END`,`_SESSION_END = 13:30`
(end-exclusive,註解明寫「13:30 起是收盤撮合」),而 `now` 是**本機鐘**。
一筆交易所時刻 13:30:00.000 的 tick 要能通過這道閘,本機鐘在**評估當下**必須嚴格小於 13:30:00 ——
而評估必然發生在成交**之後**。所以 **本機鐘落後交易所鐘的量 > 推播+處理延遲 ≥ 0**,不等式恆成立。

**證據 3(量級的一個樣本)**:09-11 log 第 81 行,本機 `09:05:19.156` 發出的訊號,`id` 裡的
tick 時刻是 `09:05:23.000` —— **交易所時刻比本機時刻早到 3.84 秒**(該筆是重新訂閱後的
snapshot quote,所以這個數只能當上界的一個觀測,不是穩定量測)。

**影響**(依嚴重度):
1. **13:30 收盤撮合被當盤中爆量**(FM-02,已發生 4 次):收盤集合競價那一筆的量在
   300 秒窗裡是天文數字,`vol_burst` 必中。`_SESSION_END` 存在的唯一理由就是擋它,而它沒擋住。
2. **09:00 開盤集合競價可能反過來被擋掉**(FM-03):本機鐘落後 δ 時,交易所 09:00:00 的
   tick 在本機 `09:00:00 − δ + 延遲` 到達;δ > 延遲就整批不評估。26 個交易日裡有 **14 天**的
   首則訊號晚於 09:00:02,**沒有任何管道能分辨**那是「真的沒事發生」還是「被閘掉了」。
3. cooldown / rearm dwell 在漂移的鐘上算:600 秒窗的秒級誤差 → **可忽略**。
4. `policy_push_end 12:30` 走 **tick 時刻**(`tick_secs(event.time_key)` vs `tick_secs(cfg.policy_push_end)`)
   → **免疫**,這段寫對了。

---

### S8-03 【high / 有效性】盤中重啟失憶,實測每次 8–43 則重複發訊,jsonl 零斷點記號

`SignalDetector` 的 `_cooldown` / `_touch` / `_latch` / `_suppressed` / `_side` / `_prev` /
`_window` / `_pullback` / `_sweep_group` / `_sweeps` / `_lookback` 全在記憶體;
`SignalHub._policy_touch`(政策 `first_of_day` 的唯一依據)同樣。回補 tick 刻意**不重放**
進 detector(`stock_engine.py:1352` 註解:「回補重放走 `apply_backfill`,不經過這裡 — SC-5」)。

**量化(實測,以 `data/signals/` 全量 + 各 rule 的 cooldown 對照)**:

| 交易日 | 重啟時刻 | 違反冷卻的相鄰發訊對 | 其中跨重啟點 |
|---|---|---|---|
| 2026-09-07 | 08:03(盤前) | **0** | 0 |
| 2026-09-08 | 09:23(**盤中**) | 9 | **8**(89%) |
| 2026-09-09 | 08:12(盤前) | **0** | 0 |
| 2026-09-10 | 09:05(**盤中**) | 44 | **43**(98%) |
| 2026-09-11 | 09:05(**盤中**) | 28 | **28**(100%) |

樣本(09-11):

```
5314 limit_lock down   09:00:14 → 09:05:23 (Δ309s,冷卻 600s)   ← Discord 推了兩次
3374 cdp_cross (al)    09:00:13 → 09:05:43 (Δ330s,冷卻 600s)
3491 surge             09:00:16 → 09:09:17 (Δ541s,冷卻 1800s)
6505 crash             09:00:18 → 09:16:05 (Δ947s,冷卻 1800s)
```

**盤前重啟 0 則、盤中重啟 8–43 則**,這個對照組讓歸因幾乎沒有懸念。
占比 ≈ 一天 629 列的 **1.3%–6.8%**。

**暖機時間(按現行參數推算,標推估)**:

| 規則 | 重啟後多久語意才正確 | 依據 |
|---|---|---|
| sweep_cluster | **~60 s**(回看窗)+ 30 s(簇窗) | `sweep_up_window_secs 60` / `cluster_window 30` |
| surge / crash / surge_pullback / vol_burst | **300 s**(共用窗) | `surge_window_secs 300` |
| vol_burst 的日均量分母 | **0 s**(`ctx.day_volume = tick.cum_vol` 由 TC4 帶,不靠記憶) | `signal_state.py:653` |
| cdp_cross | 基準重抓 **≈17 s**(80 檔 × (0.2 s gap + ~15 ms 日 K))+ 2 筆 tick 建側別 | `basis_gap_secs 0.2`;13:40 回填 log 反推日 K RTT |
| cdp_cross 的 suppressed / 冷卻 | **整天不會正確**(無持久化) | — |
| limit_lock latch | **下一筆 tick 重發一次**(FM-04);重啟期間的打開**永久遺失**(FM-05) | `_eval_limit_tick` |
| 政策 `first_of_day` | **整天不會正確**(`_policy_touch` 歸零) | `signal_hub.py:1136` |

**修法選項與取捨**:

| 選項 | 做法 | 優點 | 代價 / 風險 |
|---|---|---|---|
| (a) **記斷點**(建議先做) | 開機時往當日 jsonl 補一列 `{"kind":"session_start", ...}`;或每列加 `boot_id` | 零風險、零行為改變;離線讀者立刻分得出重複 | **違反 W1 契約「不新增列型」** → 只能走 `boot_id` 加欄那條;`nosig.py` 三桶分群靠 `SIGNAL_KINDS` 白名單,加欄安全 |
| (b) **狀態持久化** | 每次 `_arm` / latch 轉移寫一份小 JSON;開機 restore | 真正解掉重複發訊 | 熱路徑加 IO(或加一條 flush worker);restore 的日別 / 跨日語意是新的一整組失效面;`_window` / `_lookback` 這種大狀態不值得持久化 |
| (c) **回補重放** | 開機時把當日回補 tick 重放進 detector,但事件全丟棄(只暖狀態) | 窗與 latch 一次到位;不需要新檔案 | 破壞 SC-5 的「回補不進 detector」設計;重放 2,247 筆(單檔中位)× 80 檔 × 7 detector ≈ **1.4 億次 evaluate**,以 94.6 µs/tick 算是**天文數字** → 必須先做 B06 F-02(七顆合一)才可行 |
| (d) **只持久化冷卻表**(折衷) | 只存 `_cooldown` / `_touch` / `_latch` / `_policy_touch` 四張小表(全日 < 10 KB),窗讓它自然暖回來 | 解掉 100% 的實測重複(那 43 則全是冷卻 / latch 造成)、成本近零 | 需要一條「這份快照是今天的」日別尺(沿 `_basis_cache` 既有寫法) |

**建議 (a) + (d)**:(a) 讓四週影子期的資料**現在**就可對帳(不然那 8–43 則永遠混在裡面),
(d) 才是根治。**(c) 在做完 B06 F-02 之前不要碰。**

---

### S8-04 【high / 時間語意】偵測器內部兩把時鐘:窗走本機、掃單簇走交易所

```python
# signal_state.py:305-323 —— surge / vol_burst / surge_pullback 的窗
mono = _mono(now)                      # ← 本機牆鐘
window.append((mono, price, tick.qty))
cutoff = mono - self._cfg.surge_window_secs
while window and window[0][0] < cutoff: window.popleft()

# signal_state.py:716-724 —— 掃單簇的窗
secs = tick_secs(key)                  # ← 交易所 tick 時刻(自午夜秒數)
lookback.append((secs, price))
cutoff = secs - cfg.sweep_up_window_secs
```

兩把尺在同一顆 detector、同一筆 tick 上並存。模組 docstring 自己講了設計理由
(「掃單簇的窗用 tick 時刻,冷卻用牆鐘」),**理由是對的**(要與研究定義同源),
但沒有人注意到**其他四種 kind 的窗完全走另一把尺**。

**影響**:只要推播積壓(L4 的 130 ms 停擺、或更長的 loop 阻塞),一批 tick 會拿到幾乎相同的
`mono`,於是 300 秒的本機窗**實際涵蓋的交易所時間比 300 秒長** → 窗最舊點更舊 →
`_window_change_pct` 虛高 → `surge` / `surge_pullback` 誤發、`vol_burst` 的 `window_vol` 虛高。
反向(推播突然變慢)則是窗被過早剪掉。

現況 130 ms 的量級下影響可忽略;但這是一條**隨系統變忙而放大**的偏差,而「最忙的時候」
正好是訊號最有價值的時候。**修法**:窗軸統一改用 `tick_secs(key)`(掃單簇已經在用),
`mono` 只留給 cooldown / rearm dwell。**風險**:`tick.time` 缺值時(`key = _clock_key(now)`)
會混入本機鐘的自午夜秒數 —— 這正是 `_eval_sweep` 已經處理過的那個坑
(`signal_state.py:709` 註解:「退回牆鐘會把 1.78e9 混進自午夜秒數」),統一時要沿用同一個守門。

---

### S8-05 【high / 時間語意】`limit_open` 的兩半走兩把尺

`_eval_limit_tick`(tick 路)產出的 `limit_open` 用**交易所**時刻;
`evaluate_book`(簿路)產出的用 `_clock_key(now)` = **伺服器**時刻。
實測 91 則 `limit_open` 裡 **69 則走簿路、22 則走 tick 路**。

同一個 kind 的 `time` / `time_key` / `id` 有兩種語意,而**唯一能分辨的線索是毫秒位是不是 000**。
任何「鎖停維持了多久」的離線計算(= `limit_open.time − limit_lock.time`)都帶入一個
未知常數偏差(= 本機鐘落後量,S8-02)。**零錯誤訊號。**

`signal_state.py:347` 的註解已經寫了「簿路無成交 → 事件時刻是伺服器時刻(design §9)」——
**設計是知情的**,但列上沒有任何欄位把這件事告訴離線讀者。

**修法(低風險)**:政策列加一個 `time_src: "tick" | "server"` 欄(只加欄 = W1 允許)。

---

### S8-06 【high / 對帳】回填窗只掃最近 5 個日檔;錯過 3 個交易日即永久 null,且 log 分不出來

```python
# signal_hub.py:1300-1312
dated = [(date, path) for ... if date < cutoff]
dated.sort(reverse=True)
picked = sorted(dated[: self._cfg.policy_outcome_days])    # policy_outcome_days = 5
```

T+2 需要事件日之後兩個交易日,所以一列最多有 **3 個交易日的餘裕**才會掉出窗。
`_policy_outcome_worker` 只在**每日 13:40** 或**啟動時已過 13:40** 才跑 ——
也就是說「13:35 就關掉 server」或「那天沒開」連續三次,該日的政策列就**永遠**補不到,
而且:

```
2026-09-12 13:40:29 INFO T+1/T+2 回填完成:共回填 0 列(掃 5 個日檔,2026-09-04..2026-09-12)
```

這一行(09-12 週六,健康的無事可做)與「所有待補的列都掉出窗了」**是同一個字串**。
**零錯誤訊號。**

現況資料:09-11 的 49 列政策列 `t1_open` 仍 null(正常 —— T+1 是 09-14),
其餘 102 列都補齊了。所以**目前沒有實際損失**,但影子期還有三週,而 user 的開關機習慣
(09-04 的 log 10:28 就結束)已經證明「13:40 前關機」是會發生的。

**修法**:`backfill_policy_outcomes` 收尾多印一行「掃描範圍外仍 null 的政策列:n 列(最舊 YYYY-MM-DD)」
(全目錄掃一次,一天一次,2.43 ms × 檔數)。這一行非零 = 已經在流失。

---

### S8-07 【high / 對帳】B-a 政策五個交易日 0 命中;B-a ⊆ B-b 且各自成列

實測 151 列政策列:`{'S': 111, 'P': 35, 'B-b': 5, 'B-a': 0}`。

看 `evaluate_policies`:

```python
if leader and peers_up >= 1 and under_cap: hits.append("B-a")
if leader and peers_up >= 1:               hits.append("B-b")
```

**B-a 是 B-b 的真子集**(多一個 `under_cap`)。B-a = 0 而 B-b = 5,代表那 5 次
`leader and peers_up >= 1` 的場合**全部** `chg ≥ 6%`。也就是說五個交易日裡,
「自己最強 + 至少一檔同伴已動 + 自己還沒漲過 6%」這個組合**一次都沒出現**。

**外推**:4 週 ≈ 20 個交易日 → 以同樣頻率,B-a 期末樣本數 **期望值仍在 0–2 之間**。
**影子期四週結束時,B-a 這一條政策不會有可判斷的樣本。**

根因在 §4 S8-19:prod 的族群同伴太薄(151 列中 82 列 `groups` 為空、同伴數中位數 **0**)。

另外,**一顆事件同時命中多條政策時各自成列**(實測 151 列 → 132 個去重事件,19 列是
P+S 同時命中)。任何把 P 桶與 S 桶的筆數相加的統計都會**重複計 19 筆**。

---

### S8-08 【high / 對帳】三桶對帳的另外兩桶靠 repo 外一份停更的 `fills.json`

研究 HANDOFF §8.3 要求的對帳是**三桶**:訊號有他有打 / 訊號有他沒打 / 他打了沒訊號。
實作在 `Documents\copycat-trading-review\scripts\nosig.py`(`python -X utf8 scripts/nosig.py policy`),
它讀 `data/fills.json`:

```
fills.json        mtime = 2026-09-05 00:48     ← 影子期起點是 09-07
scripts/ 目錄     無 .git                      ← 無版控(prompt 已述,實證)
```

**影子期到目前為止的成交一筆都不在對帳資料裡。** 而 repo 內其實有更新的真相源:
`data/audit/capital-*.jsonl`(09-07..09-11 每日都有,最新 09-11 12:36)。

---

### S8-09 【high / 對帳】研究基準與拍板實單是兩套出場口徑,不能直接比

- 研究 §8.2 那張表(`+5,784/筆`、`+3,324`、`+1,433`、`+3,239`)全部是「**放到尾盤**」。
- Q4 拍板的實單政策是「**T+1 開盤出**」。
- 線上政策列上有 `d_close`(尾盤代理)與 `t1_open`(T+1 開盤),兩個都在。

實測兩套口徑的差距足以翻轉結論:

| 桶(first_of_day 且 late=false) | n | 放到尾盤 | T+1 開盤出 |
|---|---|---|---|
| 政策 P | 27 | **+0.80%(+4,003/筆)** 勝率 48% | +0.46%(+2,295/筆)勝率 39% |
| 政策 S | 62 | +0.04%(**+216/筆**)勝率 46% | +0.59%(+2,969/筆)勝率 48% |
| S @ 09:00–09:30 | 41 | **−0.51%(−2,568/筆)** 勝率 41% | −0.19%(−935/筆)勝率 41% |
| 政策 B-b | 3 | −7.38%(−36,911/筆)勝率 0% | −5.43%(−27,144/筆)勝率 0% |

(每筆 NT$ = 50 萬名目 × 報酬率;與研究表同口徑。)

**S 這一桶兩套口徑的符號是反的。** 而研究表最看好的那一格(S @09:00–09:30,`+3,239/筆`)
在線上前五天是 **−2,568/筆**。

---

### S8-10 【medium / 對帳】`d_high` 是事件日**全日**最高,不是前瞻 MFE

`backfill_policy_outcomes` 取「日期**等於**該日檔日那根」的 `high` / `close`。
`d_close` 是純前瞻(收盤在事件之後);`d_high` **含發訊之前的高點**。

實測落差:P 桶 `d_high` 平均 +3.80%,而同一批的尾盤是 +0.80%。
任何拿 `d_high` 當「最多可以賺到多少」的分析都會系統性高估。

**鎖死率反而可以正確算**(高 ≥ 漲停 與順序無關),而且漲停價可以從
`self.to_limit_pct` 還原(`upper = price × (1 + to_limit_pct/100)`,151 / 151 列都算得出來):

| 桶 | n | 可判鎖死 | 事件日觸及漲停 | 研究基準 |
|---|---|---|---|---|
| P | 27 | 23 | 3 = **13%** | 19–23% |
| S | 62 | 46 | 7 = **15%** | 17–22% |
| B-b | 3 | 2 | 0 = 0% | — |

---

### S8-11 【medium / 對帳】進場價系統性樂觀一檔

政策列的 `price` = 掃單簇那一筆的成交價(`event.price_milli`);
研究 `frompc` 的進場價是「觸發後**下一筆 +1 檔**」。
`signal_policy.py` docstring 差異 2 已經記了這件事,但沒有量。

**實測**:151 列的「一檔差佔價」中位數 **0.135%**、平均 0.155%、最大 0.500%。
以 50 萬名目算是 **675 元 / 筆**,而 P 桶的尾盤成績是 +4,003 元 / 筆 —— 佔 17%。
S 桶的 +216 元 / 筆,扣掉一檔就**翻負**。

**對帳時必須整批扣**,而且要扣兩次(進出各一)還是一次(研究只在進場加一檔)要先對齊定義。

---

### S8-12 【medium / 反向 finding】lookahead 防護是乾淨的 —— 不要動

逐條查證:

- `t1_open` / `t2_open` / `d_close` / `d_high` **只有兩個寫入點**(`backfill_policy_outcomes`)
  與**零個線上讀取點**。全庫 grep:
  `copycat/` 只有 `signal_hub.py` 碰它們;`frontend/src/lib/signal-model.ts:88` 只宣告型別
  (`t1_open?: number | null`),沒有任何消費邏輯。
- 回填只在**日期同時小於** hub 日別與牆鐘日的日檔上跑(`cutoff = min(self._trade_date_fn(), self.today)`),
  當日檔完全不碰。
- `_policy_row_needing_outcome` 只在回填路徑被呼叫,不在 `read_signals` 路徑。
- detector 對「舊日 snapshot」有明確 gate(`tick.trade_date != ctx.trade_date` → 回 `[]` 且
  **不推進任何狀態**),換日前的 pending 期間 engine 不呼 `on_book`。
- 回補 tick 不進 detector(SC-5),所以「用今天稍早才知道的資料回頭改判定」這條路不存在。
- CDP 基準只取 `b["date"] < basis_date` 的已完成日 K(`_resolve_basis`),當日 partial bar 排除。

**結論:線上訊號沒有任何 lookahead。** 這一塊寫得比多數量化系統嚴謹,**不要重構它**。
(唯一要注意的是 §4 S8-10:`d_high` 不是 lookahead bug,是**對帳側**的口徑誤用。)

---

### S8-13 【medium / 有效性】掃單簇 96% 的命中卡在門檻正下緣

實測 151 列政策列的來源事件:

```
sweep n30  分佈:{2: 145, 3: 3, 5: 2, 4: 1}     ← 門檻 min_sweeps = 2
sweep levels 分佈:{2: 145, 6: 3, 3: 2, 4: 1}   ← 門檻 min_levels = 2
sweep up_pct 中位數 = 0.97%                     ← 門檻 0.3%
```

**96% 的事件在兩個整數門檻的正下緣**(恰好 =2)。這代表:

1. 訊號母體**完全由邊際案決定**,而不是由「明顯的掃單簇」決定。
2. 對 §4 S8-01 的群長度變化**極度敏感** —— 群從「同毫秒」放大到「同秒」,
   `levels = round((群高 − 首價) / 首價檔距)` 會把整秒的高低差算進去,
   一個本來 levels=1 的群很容易變成 2。
3. `min_sweeps` / `min_levels` 從 2 調到 3,母體會掉到 **4%**(6 / 151)—— 這是一個
   極陡的懸崖,調參數之前一定要先把 S8-01 釐清。

`up_pct` 中位 0.97% 遠高於門檻 0.3%,所以**綁住母體的是層數與掃單數這兩個整數門檻**,
不是漲幅門檻。

---

### S8-14 【medium / 可觀測性】tick → 訊號 → 推播 的每一段都量不到

- `SignalHub` 對外只有 `dropped_jsonl` / `dropped_discord` / `dropped` 三個計數
  (`signal_hub.py:416-421`),**沒有任何耗時、次數、水位**。
- `/api/health` 只回 build 身分(`app.py:1290`,docstring 明寫「刻意不含引擎健康度」)。
- **jsonl 列上沒有任何本機時戳** —— `time` 是交易所 tick 時刻(秒級),
  `trade_date` 是日別。所以「這則訊號從成交到落檔花了多久」**在資料層面就不可回推**。
- `app.user_middleware == []`,無 request timing、無 loop lag 探針(prompt 已述,我沒有推翻)。
- CDP 基準 sweep 的**成功路徑零 log**(`_resolve_basis` 只在失敗 / 過期 / 逾時時記);
  09-11 全日 log `grep 基準` **零命中** → 只能推論「全部成功」,但「什麼時候完成的」
  「幾檔拿到基準」都不可觀測。重啟後 CDP 盲窗有多長 → 現在答不出來。

**最小可行探針**(純 stdlib、零契約、三處各 3 行):

```python
# 1) signal_hub.on_tick / on_book:固定桶直方圖(10 µs 一桶,64 桶)
t0 = time.perf_counter_ns()
...
self._tick_hist[min((time.perf_counter_ns() - t0) // 10_000, 63)] += 1

# 2) _enqueue → _append_jsonl:row 落檔前補一個本機時戳欄(只加欄 = W1 允許)
row["emit_ms"] = int(self._now_fn().timestamp() * 1000)     # 訊號產生當下
row["write_ms"] = int(time.time() * 1000)                   # 落檔當下

# 3) 每分鐘一行 INFO:p50 / p95 / p99 / 評估次數 / 兩條佇列 high-water / 窗長分佈
```

`row["emit_ms"]` 這一欄同時解掉 §4 S8-05(兩把尺)與 §5 的整條延遲鏈:
有了「訊號產生當下的本機時刻」與「tick 的交易所時刻」,
**本機鐘與交易所鐘的差(S8-02)也順便變成每一則都量得到的東西**。

---

### S8-15 【medium / 可觀測性】TC4 斷線 / 引擎降級不進 jsonl

離線讀者(研究腳本、對帳劇本)看到某天某檔零訊號時,**分不出**三種完全不同的情況:

1. 那檔那天真的沒有符合條件的行情;
2. TC4 那段時間斷線 / 該檔訂閱掉了;
3. server 根本沒開(這種還看得出來 —— 整個日檔不存在)。

09-11 log 裡 index engine 的自癒警告滿地都是(09:10 / 09:12 / 09:17 …),
但**個股 session 的健康度完全不進 jsonl**。

**修法**:同 S8-03(a),以「加欄」而不是「加列型」表達(W1 契約)。
或最省事:對帳劇本每次都併讀當日 `logs/server-*.log` 的 `TC4` / `自癒` 行,
把有斷線的時段標成「不可用」而不是「零訊號」。

---

### S8-16 【medium / 有效性】族群母體在 prod 太薄,P / B 政策幾乎沒有作用面

實測 151 列政策列:

```
groups 為空的列:82 / 151 (54%)
同伴數:中位數 0,最大 12
peers_up 分佈:{0: 136, 1: 12, 2: 3}       ← 「同伴已動 ≥1 檔」只有 15 / 151
peer_touched(同伴鎖過):{False: 149, True: 2}
leader:{False: 116, True: 35}
screen_member:{True: 133, False: 18}
```

研究 HANDOFF §8.2 的讀法已經預告過:「面板 90 檔只 27 檔有自選群組 …… 其餘 63 檔政策 P
永遠不發」。prod 的比例更極端 —— **超過一半的掃單簇事件根本沒有族群可判**,
所以實際上跑的幾乎只有 S(盤前篩選成員 + <6%,無族群濾網)。

這件事本身是 user 的自選群組結構決定的(CONTEXT.md:「user 增刪群組就是在調族群」),
不是 bug。但它直接決定了**影子期能回答什麼問題**:
「族群濾網值不值得」這個問題(= S vs P 的差)在現有母體上是可回答的;
「B 系列值不值得」不是(S8-07)。

---

### S8-17 【medium / 有效性】窗軸與冷卻軸的不一致讓 golden fixture 的「零漏發」承諾不完全轉移

`tests/live/test_signal_state.py::TestSweepClusterGolden` 的斷言強度(逐項查證):

- `test_detector_matches_prefix_reference`:**集合相等且逐元素相等**
  (`[g[:5] for g in got] == [e[:5] for e in expected]`,含 `time_key` / `price` / `n30` / `levels` / `qty`,
  `up_pct` 另以 `pytest.approx(abs=1e-9)` 比)。**很強。**
- 另加 `research_ms <= {g[0] for g in got}` = **研究定義的事件時刻 ⊆ 線上事件時刻**(零漏發)。
- `test_fixture_self_check` 另釘 fixture 自身的三個不變式(每案 ≥300 tick、≥2 個 expected、
  研究 ⊆ 即時判、至少一則「發訊早於群末」)。

**但**:樣本只有 **3 個股票日 / 2,172 筆 tick / 11 則事件**,而且測試把注入時鐘設成 tick 時刻
(`clock.now = _ms_clock(base, ms)`)—— 於是 **prod 裡「冷卻走本機鐘、窗走 tick 時刻」
這個唯一的兩軸交互,在 golden 測試裡被消掉了**。加上 S8-01 的毫秒問題,
這支測試驗的是一個「毫秒真實、兩鐘完全同步」的理想世界。

**其他五種 kind(cdp_cross / surge / crash / surge_pullback / vol_burst / limit_lock)
完全沒有任何研究 parity fixture** —— `tests/fixtures/` 下只有
`sweep_cluster_golden.json`(行為)與 `signal_param_specs.json`(**只有值域,不是行為**)。
也就是說 629 列 / 日裡的 **588 列(93.5%)是零 parity 保護**的。
這在「訊號只是輔助」的定位下可接受;要拿它下實單之前要補。

---

### S8-18 【low / 可觀測性】關機盡力落檔吞掉失敗

```python
# signal_hub.py:1243-1245
for row in rows:
    with contextlib.suppress(Exception):
        await asyncio.to_thread(self._append_jsonl, row)
```

`_append_jsonl` 內部已經對 `OSError` 記 error,但 `to_thread` 本身的失敗
(executor 已關、CancelledError 以外的任何東西)在這裡被靜默吞掉。
量級:只在關機時、只影響佇列裡剩下的幾則。**列出來記帳,不建議在這一輪改。**

另註:`_CLOSE_FLUSH_TIMEOUT = 5.0 s` 對照落檔 205 µs / 則 → 5 秒可以寫 ~16,000 則,
而佇列上限是 1000。**現況綽綽有餘**,prompt 提到的「恰等於 `LIFESPAN_SLACK_SECS`」
在訊號這一側不是實際風險(真正的風險是共用 executor 被 TC4 塞住,那是 S8 之外的事)。

---

### S8-19 【low / 有效性】`data/signal_rules.json` 永遠是 v1,遷移鏈每次開機重跑

`_load_or_migrate_rules` 只在檔案**不存在**時 `save_rules`;遷移後的結果**不落檔**。
09-11 log 64–69 行每次開機都印一遍 v1→v2→v3→v4。

正面:rule id 是從 v1 推導的,所以**跨重啟穩定**(`_event_id` 的決定性前提成立,實證:
26 天的 id 前綴都是同一組 `r-1785975520-00x` / `r-1789276016-00x`)。

負面:**prod 的規則集實際上定義在 code 裡**(`default_rules` + `_migrate_v*`),
改那段 code = 下次重啟靜默換掉線上規則(門檻、`notify_discord` 都會變),
而唯一的線索是遷移那幾行 INFO —— **沒有「最終規則集」的一行 log**。
影子期四週橫跨多次重啟,這是一條「基準在四週中間被換掉而沒人知道」的路。

**修法**:啟動時多印一行「訊號規則 n 條:kind/name/enabled/notify/cooldown」的摘要
(或一個雜湊),盤後 grep 就能確認四週用的是同一組。

---

### S8-20 【low / 反向 finding】政策層本身不要動

`signal_policy.py` 全檔純函式、零 IO、零狀態。實測:

```
resolve_groups(11 組 / 12 成員)      1.867 us
evaluate_policies(11 同伴)          5.947 us
tick_secs + tod_bucket              0.331 us
```

合計 **7.8 µs / 掃單簇事件 × 41 事件 / 日 = 全日 0.32 ms**。
`_emit_policies` 的 28 鍵 dict + 深拷貝同理(`json.dumps(政策列)` 實測 5.44 µs)。
**零最佳化空間也零必要。** 這一塊的品質風險在**定義**(S8-07 / S8-16),不在效能。

---

## 5. 延遲可觀測性:現在量得到什麼、探針要埋在哪

| 區段 | 現在量得到? | 要埋什麼 | 埋在哪 |
|---|---|---|---|
| 交易所 → TC4 → 本機 | **否**(tick 只有秒、本機鐘未校) | (1) 先修時鐘(§7 步驟 1);(2) 每則 tick 記 `recv_ms − tick_secs×1000` 的直方圖 | `stock_source.handle_raw` 或 `tc4._note_push` |
| loop ready-queue 等待 | **否** | `loop.slow_callback_duration` + 一條 1 s 週期的 `monotonic` 漂移探針 | `app.py` lifespan 起一條 task |
| detector evaluate | **否** | `perf_counter_ns` 固定桶直方圖,per-rule 分桶 | `signal_hub.on_tick` / `on_book` 頭尾各一行 |
| 窗長 / lookback 長度 | **否** | 每分鐘取一次 `sum(len(w) for ...)` 的 p50/p99 | `signal_hub` 的一條週期 task |
| 訊號產生 → jsonl 落檔 | **否**(列上無本機時戳) | row 加 `emit_ms` / `write_ms` 兩欄(只加欄 = W1 允許) | `_emit` / `_append_jsonl` |
| 訊號產生 → WS 抵達瀏覽器 | **否** | 前端收到時 `performance.now()` − payload 的 `emit_ms` | `useSignalFeed` / `useSignalAlerts` |
| 訊號產生 → Discord | 部分(Discord 蓋的時戳) | 同上 `emit_ms` 即可回推 | — |
| 兩條佇列水位 | **只有丟棄計數** | high-water mark(丟之前的水位看不到) | `_enqueue` |
| CDP 基準何時就緒 | **否**(成功路徑零 log) | sweep 結束一行 INFO:「n 檔就緒 / m 檔停用,耗時 X s」 | `_basis_worker` 需要一個 sweep 邊界概念(現在是純逐檔佇列) |
| TC4 斷線期間 | log 有,**jsonl 沒有** | 見 S8-15 | — |

**判準建議**(探針上線後盤後 grep):
- `on_tick` p99 < 200 µs;`每秒評估次數 × p50 < 10 ms/s`(loop 佔用 < 1%)。
- `emit_ms − tick 時刻` 的 p50 / p99 —— 這是**唯一**能回答「訊號比行情晚多久」的數字。
- `write_ms − emit_ms` p99 < 50 ms(超過就是共用 executor 被塞)。
- `本機鐘 − 交易所鐘` 的每日中位數,|偏差| > 1 s 就要處理。

---

## 6. 影子期四週後的對帳劇本(現在就能跑,以及缺什麼)

### 6.1 現在就能跑的部分

腳本原型:`<scratchpad>\order-signal-scan\reconcile_shadow.py`(唯讀,只吃 `data/signals/*.jsonl`)。

```
cd C:\side-project\copycat
set PYTHONUTF8=1
.venv\Scripts\python.exe <scratchpad>\order-signal-scan\reconcile_shadow.py
```

口徑對齊研究 §8.2 重算版:**事件級同檔同日首筆**(= 線上 `first_of_day`)、`late == False`、
每筆 50 萬名目、兩套出場各算一次。前五個交易日的實際輸出:

```
政策 P     n= 27 | 尾盤 +0.80% (+4003/筆) 勝率 48% | T+1開 +0.46% (+2295/筆) 勝率 39%
政策 B-a   n=0  —— 樣本不足,無法對帳
政策 B-b   n=  3 | 尾盤 -7.38% (-36911/筆) 勝率  0% | T+1開 -5.43% (-27144/筆) 勝率  0%
政策 S     n= 62 | 尾盤 +0.04% (  +216/筆) 勝率 46% | T+1開 +0.59% ( +2969/筆) 勝率 48%
S @09:00-09:30  n= 41 | 尾盤 -0.51% (-2568/筆) 勝率 41% | T+1開 -0.19% ( -935/筆) 勝率 41%

研究基準(§8.2 重算版,放到尾盤):
  P(自選版排除 ALL IN)  n= 35  +5784/筆  鎖死 23%
  P(相關族群版對照)     n=120  +3324/筆  鎖死 19%
  S 全時段(12:30 前)   n= 99  +1433/筆  鎖死 17%
  S 只在 09:00-09:30    n= 79  +3239/筆  鎖死 22%
```

鎖死率(由 `self.to_limit_pct` 還原漲停價,151 / 151 列可算):P **13%** / S **15%**(基準 17–23%)。

**讀法(五天,樣本很小,只當方向)**:P 在基準區間內偏低;S 顯著低於基準;
**S 在研究最看好的 09:00–09:30 那一格是負的**;B 系列沒有樣本(B-b 那 3 筆全是 ≥6% 的,
正好印證 Q2 那場「≥6% 不進 vs 跟鎖 ≥7%」的爭議 —— 但 n=3 不能下結論)。

### 6.2 現在**不夠**、四週前一定要補的五件事

| # | 缺什麼 | 不補的後果 | 怎麼補 | 成本 |
|---|---|---|---|---|
| C1 | **重啟斷點記號**(S8-03) | 8–43 則 / 次的重複發訊混在資料裡,`first_of_day` 不可信,「發訊數 / 日」與「誤報率」都算不準 | 每列加 `boot_id`(只加欄,W1 允許);或至少把每次開機時刻寫進一個 `data/signals/boots.jsonl` | S |
| C2 | **`fills.json` 換成 repo 內 `data/audit/capital-*.jsonl`**(S8-08) | 三桶對帳只剩一桶,等於沒對到 user 的實際取捨 —— 而 §8 的定位明寫「影子期不是驗規則,是驗規則 + 他的取捨」 | 寫一支 `audit → fills` 轉換,或改 `nosig.py` 直接讀 audit | M |
| C3 | **出場口徑二選一並寫死**(S8-09) | 結論隨口徑翻面 | 對帳腳本兩套都印(已做),但**過關判準只能綁一套**;建議綁 **T+1 開盤出**(= 拍板的實單口徑),尾盤那一套只當與研究表的橫向對照 | S |
| C4 | **進場價扣一檔**(S8-11) | P 桶高估 17%、S 桶直接翻負 | 對帳腳本統一 `entry = price + tick_size(price)` | S |
| C5 | **B-a 樣本為零的處置**(S8-07) | 四週後對 B-a 無話可說,而它是 Q3a 拍板要驗的三條之一 | 二選一:(a) 承認 B 系列在現有自選結構下不可驗,四週後直接刪;(b) 現在就擴自選群組讓族群有同伴(user 決定) | 決策,非工程 |

### 6.3 每週對帳的固定動作(R2「每週,併進現有週判準」)

```
# 1. 量:這一週發了多少、推了多少
PYTHONUTF8=1 python -c "import json,glob,collections;
rows=[json.loads(l) for f in glob.glob('data/signals/2026MMDD*.jsonl') for l in open(f,encoding='utf-8') if l.strip()];
print(collections.Counter(r['kind'] for r in rows));
print('notify', sum(1 for r in rows if r.get('notify') is not False))"

# 2. 成績:政策桶對帳(§6.1 腳本)
PYTHONUTF8=1 .venv\Scripts\python.exe <scratchpad>\order-signal-scan\reconcile_shadow.py

# 3. 資料品質三查(每一項都應該是 0):
#    (a) 冷卻違反(= 盤中重啟造成的重複)
#    (b) tick 時刻 >= 13:30:00 的列(= 收盤撮合穿過 _in_session,S8-02)
#    (c) 日期 < 今天−2 交易日 而 t1_open 仍 null 的政策列(= 回填在流失,S8-06)

# 4. 三桶:python -X utf8 scripts/nosig.py policy   ← 需先做 C2
```

---

## 7. 訊號品質指標(Q7)

### 7.1 現在算得出來的

| 指標 | 定義 | 現值(影子期 5 日) | 資料來源 |
|---|---|---|---|
| 發訊數 / 日 | jsonl 列數 | **629**(去重事件 624) | jsonl,直接數 |
| 推播數 / 日 | `notify !== false` 的列數 | **283** | jsonl `notify` 欄 |
| 政策事件 / 日 | 去重 `(日, 代號, 時刻, rule_id)` | **26.4**(列 30.2) | jsonl |
| 各 kind 佔比 | — | cdp_cross 40% / surge_pullback 26% / surge 9% / sweep_cluster 7% / vol_burst 6% | jsonl |
| 政策勝率 | `t1_open > price` 的比例 | P 39% / S 48% / B-b 0% | jsonl(回填後) |
| 政策每筆損益 | 見 §6.1 | — | jsonl(回填後) |
| 鎖死率 | `d_high ≥ upper`(upper 由 `to_limit_pct` 還原) | P 13% / S 15% | jsonl |
| **重複發訊率** | 違反該規則 cooldown 的相鄰對 / 總列數 | **1.3%–6.8%**(只在盤中重啟日) | jsonl + 規則 cooldown |

### 7.2 「誤報率」現在**定義不出來**,而且不補資料就永遠定義不出來

「誤報」在這個系統裡有三種互不相同的意思,三種現在都無法自動判:

1. **偵測誤報**(訊號說有掃單簇,實際上沒有):要比對 raw tick,而線上 tick **不落檔**。
   →「誤報率」在偵測層沒有真值可比。
   **唯一可行的替代**:S8-01 的機驗 —— 把研究歷史 tick 灌進線上 detector,
   比對線上 vs 研究定義的事件集合。這正是 golden fixture 在做的事,但只有 3 個股票日。
   **建議把 fixture 擴到 30–50 個股票日,並加一組「毫秒截秒」的 prod 形狀案。**
2. **政策誤報**(訊號有、行情沒走):**可以自動算** —— 就是 §6.1 的勝率 / 每筆損益。
   建議把「誤報」定義成 **`t1_open ≤ price × (1 + 一檔)` 的比例**(= 扣掉進場滑價後不賺),
   現值:P 61% / S 52%。
3. **通知誤報**(推了但 user 不會打):**要 C2 的成交資料**才算得出來
   (= 三桶的「訊號有、他沒打」桶)。這是 §8.3 明文要求的桶,現在**零資料**。

### 7.3 建議的「訊號健康度」每日一行(探針上線後)

```
訊號日報 2026-09-11:發 629(推 283)| 政策 26 事件 / 30 列(P 6 / B-a 0 / B-b 1 / S 23)
  | 評估 p50 96us p99 480us,窗長 p99 1820 | jsonl 佇列峰值 12 / 1000,丟 0
  | 本機鐘−交易所鐘 中位 −3.9 s  ← 非零就是 S8-02
  | 重複發訊(違反冷卻)28  ← 非零就是盤中重啟
  | 13:30 界穿透 4  ← 非零就是 S8-02 的收盤撮合
```

前三行是效能、後三行是**有效性**。現在**六行一行都沒有**。

---

## 8. 不要動的地方(附理由)

1. **`signal_policy.py` 全部**:純函式、零 IO、7.8 µs / 事件 × 41 事件 / 日(實測)。
   它的風險在定義不在實作。
2. **lookahead 防護的整條鏈**(S8-12):日別 gate、回補不進 detector、
   `b["date"] < basis_date`、回填 cutoff `min(trade_date, today)` —— 四道都對,
   而且每一道的失效樣態都是靜默的。**改任何一道之前先讀 S8-12 的查證清單。**
3. **雙佇列 fanout + 丟最舊背壓**:實證全日零丟(`grep -c 佇列滿 logs/server-20260911-0905.log` = 0),
   熱路徑零反壓。B06 §6.1 已說過,我複查同意。
4. **回填的「只重寫被補的列、其餘 byte 逐字保留」**:`tests/server/test_signal_outcome.py`
   byte 比對釘住,離線讀者契約(W1)依賴它。**jsonl 的序列化器與行尾不可換。**
   §4 S8-14 建議的 `emit_ms` / `write_ms` 是**加欄**,不碰既有列 —— 加欄前要確認回填
   不會把舊列的鍵序打亂(它用 `json.dumps(row)` 重寫被補的列,鍵序由 dict 插入序決定,
   加在尾端是安全的)。
5. **`_event_id` 的決定性鍵**:26 天的實證顯示 id 跨重啟穩定(規則 id 從 v1 檔推導)。
   改 `default_rules` 的 id 生成 = 把四週影子期切成兩段。
6. **CDP 基準 worker 的 0.2 s 逐檔 gap + 有限重試 + 日別尺**:它是為了不搶 TC4 `api.lock`
   而**刻意慢**的。
7. **`_in_session` 的 13:30 end-exclusive 界本身**(要改的是它用哪把鐘,不是界值):
   界值對應收盤撮合,是市場事實。
8. **`sweep_cluster` 的 deque 滑動窗實作**:amortized O(1),而且 `lookback` 刻意保留
   「窗前最後一筆」當基準。改它會同時動到 golden fixture。

---

## 9. 開放問題(要 user 或要跑 profile 才答得出來)

1. **TC4 live 推播的毫秒是真的恆為 0,還是某個設定 / 訂閱模式的結果?**
   `.claude/skills/tc4-market-facts/SKILL.md:71-78` 明寫「REALTIME 與歷史 TICKS 的毫秒同源」——
   我的 prod 資料(7,852 / 7,852)與它牴觸。要一支只聽不訂的 probe(skill §tc4 有寫法)
   把原始 `PreciseTime` 印出來確認。**這是 S8-01 的前提,要先釘死。**
2. **本機鐘落後交易所鐘多少?** 我只有一個 3.84 s 的樣本與一個方向證明。
   要 `emit_ms` 探針(S8-14)跑一天才知道是 0.1 s 還是 5 s,量級決定 S8-02 要不要緊急處理。
3. **B-a 樣本為零要怎麼辦?**(S8-07 / C5)承認不可驗並刪掉,還是調自選群組讓族群有同伴?
   這是方向性抉擇,要 user 拍板。
4. **對帳的過關判準綁哪一套出場?**(S8-09 / C3)T+1 開盤出(拍板的實單口徑)
   還是放到尾盤(研究表的口徑)?§8.1 Q6b 說「不設事前過關標準,四週後只寫成績」——
   那至少**口徑**要在四週結束前先定,不然「成績」會有兩個版本。
5. **要不要把窗軸統一到 tick 時刻?**(S8-04)這會改掉 surge / vol_burst / pullback
   四種 kind 的判定基準,等於把八月以來的歷史訊號與之後的切成兩段。影子期中途改不合適;
   要嘛四週結束後做,要嘛現在做並重新起算四週。
6. **`vol_burst` 的 4 則假訊號要不要從影子期資料裡剔掉?** 它們 `notify=false`,
   沒推播給人,但進了 jsonl。對帳只看政策列的話無影響;`nosig.py legacy` 那套會受影響。
7. **其他五種 kind 要不要補 research parity fixture?**(S8-17)629 列 / 日裡 93.5% 是零 parity 保護。
   「訊號只是輔助」的定位下可接受;要下實單前必補。

---

## 附:量測腳本

| 檔 | 做什麼 | 重跑方式 |
|---|---|---|
| `bench_s8.py` | 序列化 / 落檔 / 時鐘元件 / 全檔解析成本 | `PYTHONUTF8=1 .venv\Scripts\python.exe bench_s8.py` |
| `ms_vs_sec.py` | **S8-01 的決定性量測**:golden fixture 的 tick 截到秒後重跑同一顆 detector | 同上 |
| `reconcile_shadow.py` | **§6 的對帳劇本原型**,兩套出場口徑 + 研究基準對照 + 缺口自檢 | 同上 |
| `bench_policy.py` | 政策層 `resolve_groups` / `evaluate_policies` 成本 | 同上 |

一次性查核用的 inline 指令(冷卻違反、毫秒分佈、13:30 穿透、各日發訊量)全部寫在本報告
對應段落裡,可直接複製重跑。
