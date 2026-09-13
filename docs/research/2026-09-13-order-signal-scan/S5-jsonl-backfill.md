# S5 — 訊號:落檔、T+1/T+2 回填與離線讀者契約

> 掃描日 2026-09-13(週日)。工作樹 master `caca1d30`,prod server 未在跑。
> 所有「實測」數字在本機 `.venv`(Python 3.13.13 / ProactorEventLoop / NTFS)量得,
> 腳本在同目錄 `stat_jsonl.py` / `stat2.py` / `stat3.py` / `bench_io.py` / `bench_loop.py`。
> **本輪零 repo 改動、零 server 啟動、零下單。**

---

## 0. 一句話結論

落檔這一段**在今天的量級下完全不是效能問題**(全日 237 ms),
但它是量化系統最不能壞的一段 —— 而它現在的三個要害全都是**零錯誤訊號**:

1. `data/signals/*.jsonl` 是「訊號真相源」,卻**沒有 fsync**、沒有 checksum、沒有重啟標記、
   沒有任何「這一天資料完不完整」的宣告。
2. T+1/T+2 回填的收尾行只說「共回填 n 列」,**從不說「還有 m 列該補而沒補」** ——
   今天的實測就是:`2026-09-12 13:40 共回填 0 列`,而同一刻有 **87 列**政策列 t1/t2 仍是 null。
3. 離線讀者(研究目錄 17 支腳本)**一支都沒有 try/except**,而它們直接 glob
   **prod 的 `data/signals/`**,與 13:40 的 `os.replace` 在同一個目錄上對撞 ——
   實測 Windows 上這個對撞會讓**回填端**直接 `PermissionError` 中止整趟。

---

## 1. 現況地圖:一則訊號從記憶體到檔案到研究腳本

```
[熱路徑・event loop・同步]
 stock_engine._handle_quote
   └► SignalHub.on_tick / on_book          signal_hub.py:598 / :616
        └► 每條規則一顆 SignalDetector      :632 _fanout
             └► SignalEvent
                  └► _emit                  :1012   ← 組 payload(15 欄)
                       ├► self._publish(payload)        WS,同步先送(前端要即時)
                       ├► _enqueue({**payload,"trade_date":...})   :1167
                       │     ├► _jsonl_queue  (maxsize 1000, 滿了丟最舊)  實測 0.616 us
                       │     └► _discord_queue(maxsize 100,  notify=True 才進)
                       └► kind=="sweep_cluster" → _emit_policies  :1042
                             └► 每命中一條政策各發一列(34 欄)→ 同樣 publish + _enqueue

[落檔・獨立 task]
 _jsonl_worker  :1186
   while True: row = await q.get()
               await asyncio.to_thread(self._append_jsonl, row)   ← 每則一次 thread 往返
               finally: q.task_done()
 _append_jsonl  :1412
   path = data/signals/YYYYMMDD.jsonl        (日別取 row["trade_date"])
   path.parent.mkdir(parents=True, exist_ok=True)      ← 每則一次
   with path.open("a", encoding="utf-8") as fh:        ← 每則一次 open/write/close
       fh.write(json.dumps(row, ensure_ascii=False) + "\n")   ← Windows 文字模式 → CRLF
   except OSError: logger.error(...)                   ← 只吃 OSError,其餘由 worker 的傘接

[讀・線上]
 GET /api/stock/signals/today  app.py:1573
   → hub.today_signals() :1421  → read_signals() :1448
     read_text(errors="replace") + splitlines + 逐行 json.loads,壞行跳過
   (前端 useSignalFeed 每 5 分鐘輪詢一次;分頁隱藏時停)

[回填・獨立 task]
 _policy_outcome_worker  :1250   每 30 s 輪詢牆鐘,到 policy_outcome_time(13:40)跑一次/日
   └► _run_policy_outcomes :1272  (整趟包 try/except,worker 不死)
        └► backfill_policy_outcomes :1280
             cutoff = min(trade_date_fn(), today)                ← 雙半守門(見 §3)
             picked = 最近 policy_outcome_days(5)個 date < cutoff 的日檔
             for date, path in picked:
                 raw = await to_thread(path.read_bytes)          ← off-loop
                 lines = raw.splitlines(keepends=True)           ┐
                 逐行 decode("utf-8") → _policy_row_needing_outcome  │ 全在 loop 上
                 targets: code → [(行號, 原文, row)]              ┘
                 for code: bars = await _fetch_outcome_bars(...) ← TC4 日 K + 0.2 s gap
                     t1 = 第一根 t>date 且 o>0;t2 = 第二根;same = t==date 那根
                     for 每列: 補 d_close/d_high/t1_*/t2_*(只補 None)
                        lines[i] = (json.dumps(row) + 原行尾).encode("utf-8")
                 if changed: await to_thread(atomic_write_bytes, path, b"".join(lines))

[讀・離線]
 C:\Users\USER\Documents\copycat-trading-review\scripts\*.py(17 支讀 jsonl)
   全部 glob(r"C:\side-project\copycat\data\signals\*.jsonl")  ← 直接吃 prod 目錄
   全部 open(p, encoding="utf-8") 嚴格解碼 + json.loads 無 try/except
```

### 1.1 真實資料形狀(實測,26 個日檔)

| 指標 | 值 |
|---|---|
| 日檔數 / 總位元組 / 總列數 | 26 / 3,163,199 B / **8,789 列** |
| 列/日 | mean 338、max 719;**spec #192 上線後(09-07~09-11)= 479/593/670/719/686,mean 629** |
| 單列位元組 | mean 360、median 345、max 2,095 |
| 行尾 | **8,789/8,789 全 CRLF**(`_append_jsonl` 文字模式的必然) |
| 壞行 / 重複 id | 0 / 0 |
| kind 分佈 | cdp_cross 3994、surge_pullback 1225、surge 963、crash 658、vol_burst 480、**market_limit_lock 479**、**market_limit_open 367**、sweep_cluster 205、limit_lock 176、**policy 151**、limit_open 91 |
| 缺 `kind` / `trade_date` / `code` / `time` 的列 | **0 / 0 / 0 / 0**(離線讀者的裸 `s["kind"]` 目前安全) |
| 政策列回填率 | t1_open 102/151 = **67.5%**、t2_open 64/151 = **42.4%**、d_close 102/151 |

近 5 日檔 policy 列佔比 2.0–7.1%,但**位元組**佔比高得多(09-11:53,934 B / 289,089 B = **18.7%**)
—— 政策列 34 欄、帶 `peers` / `sweep` / `self` 巢狀物件,是一般列的 3–6 倍長。

---

## 2. 端到端延遲預算

### 2.1 落檔路徑(每則訊號)

| # | 區段 | 位置 | 成本 | 依據 | 備註 |
|---|---|---|---|---|---|
| L1 | `_emit` 組 payload(15 欄 dict literal) | `signal_hub.py:1015-1035` | ~1.5 µs | 推估(dict 15 鍵 + list()) | 熱路徑、同步 |
| L2 | `_enqueue` → `put_nowait` ×2(jsonl+discord) | `:1167-1185` | **0.62 µs/次** | 實測 | 含滿載繞道分支 |
| L3 | 政策列另組 34 欄 dict + `evaluate_policies` | `:1042-1160` | 未量(本輪範圍外) | — | 只在掃單簇命中時 |
| L4 | worker `q.get()` → `to_thread` 派工往返 | `:1188-1190` | **40.7 µs** | 實測(ProactorEventLoop) | 純往返,不含工作 |
| L5 | `json.dumps(row, ensure_ascii=False)` | `:1416` | **一般列 2.81 µs / 政策列 5.59 µs** | 實測 | 在 worker thread |
| L6 | `mkdir(parents=True, exist_ok=True)` | `:1414` | **46.2 µs** | 實測 | **每則都付一次**,純浪費 |
| L7 | `open("a")+write+close` | `:1415-1417` | **152.2 µs** | 實測 | NTFS,warm cache |
| L8 | **一則端到端(loop 視角)** | — | **345 µs**(min 335 / max 371) | 實測 | L4+L5+L6+L7+GIL |
| L9 | **全日總計(686 列)** | — | **237 ms** | 實測外推 | 分散在 4.5 小時 → **可忽略** |
| L10 | 規則/自選 ×10(6,860 列/日) | — | **2,367 ms** | 實測外推 | 仍可忽略;批次寫可降到 88 ms |
| L11 | **executor 飽和時的一則落檔** | — | **1,344 ms**(20 格被 1.5 s 工作佔滿) | **實測** | 見 §4 F-05;TC4 取數最壞 20 s → 這一格可達 **20 s** |

批次寫對照(實測):50 列一次 `open` = 638.7 µs 總 → **12.8 µs/列**,比現行 219 µs **快 17 倍**。

### 2.2 回填路徑(每日 13:40 一次)

| # | 區段 | 位置 | 成本 | 依據 | 備註 |
|---|---|---|---|---|---|
| B1 | `signal_dir.glob("*.jsonl")` + 挑日檔 | `:1294-1307` | < 1 ms | 推估(26 個 dirent) | loop 上 |
| B2 | `to_thread(path.read_bytes)` ×5 | `:1314` | 0.10 ms/檔 → **0.5 ms** | 實測 | off-loop ✔ |
| B3 | **逐行 decode + `json.loads` ×5 檔** | `:1327-1338` | **12.8 ms(3,147 行)** | 實測 | ❌ **全在 event loop 上** |
| B4 | TC4 日 K:`bars_range(tf="D")` × distinct code | `:1386-1408` | **23 次**(09-12 實況);健康 RTT 未量,逾時上界 `_REQ_TIMEOUT_MS` 10 s | 實測次數 / 推估 RTT | 走共用 executor + `api.lock` |
| B5 | `basis_gap_secs` 0.2 s × 每檔 | `:1405` | **4.6 s** | 實測次數 × 設定值 | 純 sleep,讓位給主圖回補 |
| B6 | `json.dumps` 被補的列 | `:1379` | 5.59 µs × 61 = 0.34 ms | 實測 | loop 上 |
| B7 | `b"".join(lines)` + `to_thread(atomic_write_bytes)` | `:1381` | **0.46 ms/檔**(289 KB) | 實測 | off-loop ✔ |
| B8 | **整趟(健康)** | — | **~4.3 s**(09-11 log 實錄 13:40:26.357→13:40:30.660 的可見段) | **實測** | 其中 ~4.6 s 是 B5 的 sleep |
| B9 | **整趟(TC4 全逾時最壞)** | — | **23 × 10 s + 4.6 s ≈ 235 s** | 推估 | 佔住 `api.lock` 與 executor 一格 |

### 2.3 讀取路徑

| # | 區段 | 位置 | 成本 | 依據 |
|---|---|---|---|---|
| R1 | `read_signals`(289 KB / 686 列) | `:1448-1482` | **3.39 ms** | 實測 |
| R2 | `/api/stock/signals/today` 頻率 | `useSignalFeed.ts:81` | 5 min/分頁 → 全日 ~54 次 × 開著的分頁數 | 既有註解 |
| R3 | 全日 REST 讀取總成本 | — | 54 × 3.39 ms ≈ **183 ms/分頁/日** | 實測外推 |

### 2.4 關機路徑(與資料完整性直接相關)

| # | 區段 | 位置 | 成本 | 依據 |
|---|---|---|---|---|
| C1 | `wait_for(_jsonl_queue.join(), 5.0)` | `:564` | 佇列 1000 滿載 × 345 µs = **345 ms** | 實測外推 |
| C2 | `_flush_pending()`(逐則 `to_thread`,**無 timeout**) | `:1236-1246` | 健康 < 350 ms;**executor 飽和時無上界** | 推估 |
| C3 | `LIFESPAN_SLACK_SECS` 預算 | `shutdown_budget.py:44` | **5.0 s**,要涵蓋 crosscheck cancel + breadth + bot.close + hub drain | code |

`_CLOSE_FLUSH_TIMEOUT`(5.0 s)**單獨就吃滿** C3 的整格 slack。`_close_segment`(`app.py`)**沒有 timeout**。

---

## 3. T+1/T+2 回填的完整邏輯(逐條對照 code)

### 3.1 觸發時點

- `_policy_outcome_worker`(`:1250`)**輪詢**而非 `call_later`:時鐘是注入的 `now_fn`,
  loop 時間與它不同尺。`POLICY_OUTCOME_POLL_SECS = 30.0`。
- 起動時**只在已過當日 `policy_outcome_time` 才立即跑一次**(`:1261`)。開盤前起動不跑 ——
  理由寫在 docstring:回填的 DK 與 CDP 基準暖機**共用同一把 TC4 `api.lock`**,
  開機那趟只會把基準 sweep 拉長,而它補的是昨天以前的開盤價,晚到 13:40 一樣。
- `ran_for` 記日期字串,一天只跑一次。整趟包 `try/except`(`_run_policy_outcomes`),
  worker 死掉 = 之後所有政策列 t1/t2 永遠 null 而畫面零訊號 —— 這條防禦是對的。

**實測 log 佐證**(`logs/server-20260911-0905.log`):
```
2026-09-11 13:40:26,357 T+1/T+2 回填 2026-09-09:回填 23 列(14 檔)
2026-09-11 13:40:30,660 T+1/T+2 回填 2026-09-10:回填 38 列(17 檔)
2026-09-11 13:40:30,660 T+1/T+2 回填完成:共回填 61 列(掃 5 個日檔,2026-09-04..2026-09-11)
2026-09-12 13:40:29,046 T+1/T+2 回填完成:共回填 0 列(掃 5 個日檔,2026-09-04..2026-09-12)
```

### 3.2 雙半守門:`cutoff = min(self._trade_date_fn(), self.today)`(`:1291`)

兩半各擋一種:
- `self.today`(牆鐘日)擋住「今天的檔開盤價還沒定」;
- `self._trade_date_fn()`(engine 日別)擋住「hub 日別落後牆鐘」的常態
  (空自選 / 零推播時 engine 的 `trade_date` 會靜默停在昨日,而**昨日檔正是
  `_append_jsonl` 還在寫的檔**)。

這條設計是對的,而且**它保證回填目標檔與正在 append 的檔永不重疊** ——
這正是為什麼 §5 的 `os.replace` 對撞只會來自**外部讀者**,不會來自自己的 append。

**但它也產生一個零訊號盲區(實測到)**:2026-09-12 是週六,engine 日別停在 09-11,
`cutoff = min("2026-09-11", "2026-09-12") = "2026-09-11"` → **09-11 的檔 `date < cutoff` 為 false,整份被排除**。
log 那行「掃 5 個日檔,**2026-09-04**..2026-09-12」的 start = 09-04 就是證據
(若 09-11 在窗內,start 會是 09-07)。於是:

| 檔 | 政策列 | t1_open | t2_open | d_close |
|---|---|---|---|---|
| 20260907 | 29 | 29 | 29 | 29 |
| 20260908 | 12 | 12 | 12 | 12 |
| 20260909 | 23 | 23 | 23 | 23 |
| 20260910 | 38 | 38 | **0** | 38 |
| 20260911 | 49 | **0** | **0** | **0** |

**87 列待補,而 13:40 的收尾行寫「共回填 0 列」** —— 與「全部補齊」逐字同形。

### 3.3 只碰哪些日檔

`:1295-1307`:`glob("*.jsonl")` → stem 必須 8 位數字 → `date < cutoff` → `sort(reverse)` →
`[:policy_outcome_days]`(預設 **5**)→ 再 `sorted()` 升冪處理。

窗是「最近 N 個**日檔**」而不是「最近 N 個日曆日」,所以 server 停機幾天不會讓檔掉出窗;
但 **server 連續運作 N 個交易日而某一天的補值一直失敗**,那一天就會靜默掉出窗、**永遠是 null**。
現況 09-10 的 t2 還剩 3 個交易日的補救機會(窗內只有 09-11 比它新)。無任何告警。

### 3.4 只補哪些欄位(`:1355-1381`)

- 對象判準 `_policy_row_needing_outcome`(`:1625`):`kind == "policy"` 且
  `t1_open` / `t2_open` / `d_close` / `d_high` **任一為 None 或缺**。
- `after = [b for b in bars if b["t"] > date]`;`t1 = after[0] if after[0]["o"] > 0`、
  `t2 = after[1] if ...`。**`o <= 0` 不跳到下一根冒充**(欄名會說謊,spec review F-03)。
- `same = next(b for b in bars if b["t"] == date)` → `d_close` / `d_high`。
- 09-07 前的舊列**沒有** `d_close` / `d_high` 兩鍵 → 一併加上(「只加欄」)。
- 只有 `dirty` 的列才重寫;`changed == 0` → **完全不碰檔案**
  (`test_signal_outcome.py:504` 釘住「零補不呼叫 `atomic_write_bytes`」)。

### 3.5 逐行 bytes 保留契約(`:1318-1381` + CLAUDE.md §4)

```python
lines = raw.splitlines(keepends=True)        # bytes 版:只切 \n / \r / \r\n
for i, line_bytes in enumerate(lines):
    try: line = line_bytes.decode("utf-8")
    except UnicodeDecodeError: undecodable += 1; continue     # 壞行原樣保留
...
body = line.rstrip("\r\n"); eol = line[len(body):]
lines[i] = (json.dumps(row, ensure_ascii=False) + eol).encode("utf-8")   # 行尾原樣接回
...
await asyncio.to_thread(atomic_write_bytes, path, b"".join(lines))       # 零換行翻譯
```

四條不變式,每一條都有明確理由:
1. **bytes 版 `splitlines`**:`str` 版還切 U+2028 等,JSON 字串內出現會把一列切成兩行。
2. **不用 `errors="replace"`**(`read_signals` 用):這裡要**回寫**,U+FFFD 會被寫進檔案。
3. **逐行 decode 而非整檔嚴格解碼**:半寫入切在中文中間那種壞行只讓那一行保留,
   整檔嚴格會讓那一天連續 5 天整檔跳過、t1/t2 永遠 null。
4. **行尾原樣**:prod 全 CRLF;`atomic_write_bytes` 是 `fileio.py` 三個 helper 中
   唯一零換行翻譯的那支,**不可換成 `atomic_write_text`**。

測試釘法:`tests/server/test_signal_outcome.py:164-200`
`@pytest.mark.parametrize("eol", ["\n","\r\n"])` + `assert path.read_bytes() == (eol.join(expected)+eol).encode("utf-8")` ——
**整段 bytes 比對**,連檔尾換行都比。另 `:207-219` 釘「半寫入切在中文中間」那一行位元組原樣。

> ⚠ **一個沒被釘住的半邊**:沒有任何測試斷言 `_append_jsonl` 在 Windows 上**產生** CRLF。
> byte 比對測試比的是手寫 fixture 的行尾。這其實是好事(回填的 per-line eol 邏輯讓
> `_append_jsonl` 換行尾也不會壞),但 CLAUDE.md 與 B06 都把 CRLF 講成硬契約 ——
> **實際上它是「回填必須保留現有行尾」而不是「行尾必須是 CRLF」**。這個口徑差別值得校正:
> 前者有測試、後者沒有,而後者會不必要地嚇阻「批次寫」這類改動。

### 3.6 一個已被 code 明說、但值得標出的暗坑

`_fetch_outcome_bars`(`:1386`)的 `cache` 是 `dict[str, list[Bar] | None]`,**只以 code 為鍵**,
`start`/`end` 是整趟固定值 —— 正確。但 `if not bars: continue`(`:1358`)把 `None`(例外)
與 `[]`(逾時/斷線)收成同一條路。兩者處置相同(留 null 下輪再補),差別只有 log 等級。
**這是對的**(review F-08 已記),不要動。

---

## 4. 回填與 `api.lock` / 共用 executor 的競爭

### 4.1 鎖鏈

```
backfill → engine.bars_range(code,"D",start,end)     stock_engine.py:885
         → asyncio.to_thread(source.fetch_bars_range)   ← 共用 default executor(20 workers)
         → TC4QuoteSource._req  → api.lock.acquire(timeout=DEFAULT_LOCK_TIMEOUT_SECS=12.0)
                                 + _REQ_TIMEOUT_MS(10 s)
```

CDP 基準暖機走 `_basis_worker → _resolve_basis → self._daily_bars(code, 5)`
(`signal_hub.py:929`)→ `engine.daily_bars` → **同一條 stock session、同一把 `api.lock`**。
兩條 worker 是 `SignalHub` 內**各自獨立的 asyncio task**,彼此不互斥 —— 只有 TC4 那把
`api.lock` 在序列化它們。

`basis_gap_secs = 0.2` 兩邊共用(`_basis_worker:838` 與 `_fetch_outcome_bars:1405`),
註解寫得很清楚:「與主圖回補 / K 線 route 共用同一條 TC4 stock session,連發要讓位」。

### 4.2 為什麼「開盤前起動不跑回填」是對的決策

開機那趟的 basis sweep 是 150 檔上限 × (日 K RTT + 0.2 s gap) — 幾十秒級;
回填再插 23 次 `bars_range` 進同一把鎖,基準 sweep 會被拉長到開盤後,
而 **CDP 基準晚一分鐘 = 開盤那一分鐘的 CDP 穿越全部發不出來**。
回填補的是昨天以前的開盤價,晚到 13:40 零損失。這條拍板(整體 review F-10)沒有問題。

### 4.3 真正的競爭窗:13:40

13:40 已過 13:30 收盤,個股引擎的分時自癒閘 `_STOCK_HEAL_END` 是 13:35,
主圖回補基本停了。**實際競爭對手是:使用者開著的 K 線 route、期貨 tab、以及 capital 的 OI 快照。**
09-11 的實測整趟 4.3 s,其中 4.6 s 是 `basis_gap_secs` 的 sleep —— 也就是說
**TC4 取數本身幾乎不花時間,成本全在自己讓位的 sleep 上**。

**推論(未實測):13:40 這個時點把 gap 從 0.2 s 降到 0.05 s 是安全的**,
整趟從 4.3 s 降到 ~1.2 s。但收益太小,不值得動契約以外的東西 —— 列在「不要動」。

---

## 5. 原子寫入:成本、風險、以及一個實測到的 Windows 硬事實

### 5.1 成本(實測)

`atomic_write_bytes(289,089 B)` = **0.46 ms**,在 `to_thread` 上。
為了改 53 KB 的政策列要重寫 282 KB(**18.7% 有效載荷**)—— 一天一次,完全可接受。

### 5.2 風險一:**Windows 上 `os.replace` 撞到任何開著的 handle 就 PermissionError**(實測)

```
目標被 open(mode="r", encoding="utf-8") 開著 → os.replace 失敗:PermissionError [WinError 5] 存取被拒。
目標被 open(mode="rb")                  開著 → os.replace 失敗:PermissionError [WinError 5]
目標被 open("a", encoding="utf-8")      開著 → os.replace 失敗:PermissionError [WinError 5]
```

CPython 在 Windows 上開檔不帶 `FILE_SHARE_DELETE`,所以**連唯讀的讀者也會擋住 rename**。

後果鏈(`signal_hub.py:1381`):
```python
await asyncio.to_thread(atomic_write_bytes, path, b"".join(lines))   # ← 沒有 try/except
```
→ `PermissionError` 逃出 `for date, path in picked:` 迴圈
→ 逃出 `backfill_policy_outcomes`
→ 被 `_run_policy_outcomes` 的 `except Exception: logger.exception("T+1/T+2 回填未預期失敗")` 接住
→ **本趟剩下的日檔全部不補**,而 `ran_for` 已設成今天 → **當天不再重試,要等明天 13:40**。

觸發條件現實得很:研究目錄 17 支腳本全部 `glob(r"C:\side-project\copycat\data\signals\*.jsonl")`
並 `open(p, encoding="utf-8")` 逐行讀。**user 在 13:40 跑 `nosig.py` / `build_viewer.py` / `tickpanel.py`
就會打到**。而 `tickpanel.py`(522 行)與 `build_viewer.py` 讀完整個目錄,窗口是秒級。

另外 `atomic_write_bytes` 的 docstring 明說「寫 tmp 中途失敗 → tmp 殘留、目標檔不動(不加 cleanup)」。
`path.with_suffix(".tmp")` 對 `20260910.jsonl` 產生 `20260910.tmp`,glob 是 `*.jsonl` 所以不會誤讀,
但**殘留檔沒有任何清理**,而且會誤導事後排查(看到 `.tmp` 以為是半寫入的資料)。

### 5.3 風險二:**兩條寫入路徑都沒有 fsync**

- `_append_jsonl`:`with path.open("a")` 的 `close()` 只做 CRT flush,**無 `os.fsync`**。
- `atomic_write_bytes`:`tmp.write_bytes()` 後直接 `os.replace`,**tmp 沒 fsync、目錄沒 fsync**。

`os.replace` 在 NTFS 上對**目錄項**是原子的,但檔案內容還在 page cache。斷電/藍屏時
可能得到「rename 已完成、資料未落盤」的檔 —— NTFS 典型症狀是檔案大小對、內容是零。
而**回填是整檔覆寫**,所以壞掉的是**一整天**的訊號,不是尾巴幾列。

`_MISSED-143.md` 第 141 條已經指出 `atomic_write_text` 缺 fsync 而「受害清單全都可重建」;
**`data/signals/*.jsonl` 不在那個清單裡,而它不可重建** —— tick 流 in-memory 不持久化,
規則檔就地覆寫無歷史,重放也重放不出同一組事件(Q1 §3)。這一份與下單審計同級。

### 5.4 已經寫對的地方(不要動)

- 只重寫 `dirty` 的列、其餘原文逐字保留 → 對帳 diff 乾淨。
- `changed == 0` 完全不碰檔 → 週末 13:40 跑也不會白寫 26 個檔。
- 行尾 per-line 保留 → 混合行尾的檔也安全。
- `read_signals` 的 `errors="replace"` + 壞行跳過(而不是把 except 擴成 `(OSError, ValueError)`
  整檔丟掉)—— round-2 HR-1 的判斷是對的。

---

## 6. 離線讀者契約:逐支盤點

CLAUDE.md §4 的 W1 契約寫的是「**不新增列型、每列 `kind` 恆在、既有列只加欄不改欄**」。
實測 8,789 列缺 `kind`/`code`/`time`/`trade_date` 各 0 列 —— 契約目前**成立**。

### 6.1 讀者清單與它們的假設

| 讀者 | 位置 | 讀法 | 對 `kind` 的假設 | 崩潰面 |
|---|---|---|---|---|
| `read_signals` | `signal_hub.py:1448` | `errors="replace"` + 壞行跳過 | 無假設 | **防禦完整** |
| `_policy_row_needing_outcome` | `signal_hub.py:1625` | 逐行 bytes + 壞行 None | `.get("kind") != "policy"` → 跳過 | **防禦完整** |
| 前端 `signal-model.ts` | `kindLabel` | JSON via REST/WS | 未知 kind **原樣印英文代號** | 不炸(`SignalKind` union 仍保留 `market_limit_*` 當防禦濾網) |
| `nosig.py:26-28` | 研究 | `open(...,encoding="utf-8")` + 裸 `json.loads` | **`s["kind"]` 裸鍵**、`s["trade_date"]` 裸鍵 | **一列壞就整支死** |
| `signal_join.py:8-11` | 研究 | 同上 | `{k:... for k in set(s["kind"] for s in sig)}` **裸鍵** | 同上 |
| `signal_lag.py` / `val.py` / `cooldown_check.py` | 研究 | 同上 | `s["kind"]=="surge"` **裸鍵** | 同上 |
| `build_viewer.py:157-163` | 研究 | 同上 | **白名單** 6 種 kind(`surge/crash/vol_burst/limit_lock/limit_open/surge_pullback`);`s["code"]`/`s["trade_date"]` 裸鍵 | 壞行死;新 kind 安全 |
| `tickpanel.py:83-86` | 研究 | 同上 | 同 build_viewer | 同上 |
| `week0909/policy_week.py:33-38` | 研究 | **硬寫死三個日名** `20260907/08/09` | `s.get("kind")=="policy"`(防禦)+ **`s["policy"]` 裸鍵** | 檔不存在 → FileNotFoundError |
| `week0909/group_multi.py:19-23` | 研究 | 同上 | 同上 | 同上 |
| `week0909/screen_perf.py:62-64` | 研究 | 同上 | 同上 | 同上 |

### 6.2 三個具體的契約漏洞

**(a) 研究腳本沒有一支能容忍半寫入的尾巴。**
`read_signals` 花了一整段 docstring 講「嚴格解碼會讓整天消失」,
回填花了 12 行註解講「逐行 bytes 才不會連續 5 天整檔跳過」——
而**真正做研究對帳的那 17 支腳本,防禦等級是零**。
盤中 `Ctrl+C` / 硬殺切在中文多位元組序列中間,當天檔就有一行壞 bytes,
`nosig.py` 直接 `UnicodeDecodeError` 或 `json.JSONDecodeError` 整支死。
現況實測 0 壞行,**但那只代表還沒發生過**。

**(b) 已退役的 kind 永久留在歷史資料裡,而白名單只涵蓋一半。**
`market_limit_lock` / `market_limit_open` 共 **846 列**(佔全庫 9.6%),
產生點已於 2026-08-16 刪除(`.claude/mod/remove-sector-timeline/`)。
`_kind_text`(`signal_hub.py:138`)對它們沒有分支 → 落到 `return kind` 印英文。
`nosig.py` 的 `LEGACY_KINDS` 七種**不含**這兩個 → 它們被當「無訊號」。
這不是 bug(政策上就不該算),但它證明了一件事:**kind 集合已經是一個有歷史包袱的枚舉,
而唯一的權威清單不在 code 裡,在 CLAUDE.md 的散文與三份研究腳本各自的字面 tuple 裡。**

**(c) 研究腳本直接吃 prod 目錄,與回填在同一份檔上對撞。**
見 §5.2。而且方向是雙向的:回填會因為讀者而失敗;讀者也會在回填 `os.replace` 的瞬間
拿到**舊 inode 的內容**(Windows 上開著的 handle 仍指向舊檔,replace 若成功則讀者讀的是舊資料)。
實測顯示這裡 replace 會失敗,所以讀者其實是「贏」的那一方 —— 但那等於用回填的失敗換讀者的正確。

### 6.3 「既有列只加欄不改欄」已經有一次可觀測的漂移

實測政策列有 **兩種鍵序**:

```
n=122: (..., 't2_date', 'd_close', 'd_high', 'trade_date')      ← 新列(_emit_policies 自然序)
n= 29: (..., 't2_date', 'trade_date', 'd_close', 'd_high')      ← 09-07 舊列,回填時 append 兩鍵
```

原因:09-07 的舊列沒有 `d_close`/`d_high`,回填的 `row["d_close"] = ...` 把它們**加在 dict 尾端**,
而 `trade_date` 是 `_enqueue` 的 `{**row, "trade_date":...}` 早就在尾端了。

功能上無害(JSON 物件無序),但 CLAUDE.md §4 明文寫「回填改成整檔 dumps → 舊列鍵序 …
變動,對帳 diff 整檔紅」—— **這個症狀已經在 09-07 那個檔身上發生過一次了**,
只是原因不是整檔 dumps 而是「補新欄到舊列」。任何以 `diff` 做對帳的流程要知道這件事。

---

## 7. 資料完整性:盤中重啟的斷點

### 7.1 現況:**jsonl 裡沒有任何重啟記號**

我試著從資料反推斷點,結論是**做不到**:

```
20260904.jsonl: n=202 first=09:00:51 last=10:27:54 時間回跳=2   (09:10:11 → 09:10:00)
20260908.jsonl: n=593 first=09:00:01 last=13:25:45 時間回跳=1
20260910.jsonl: n=719 first=09:00:01 last=13:24:30 時間回跳=2
```

`time` 回跳是**常態**(不同 code 的 tick 到達次序,`event.time` 是 tick 時刻不是落檔時刻),
所以「時間回跳 = 重啟」完全不成立。檔案裡沒有 `boot_id`、沒有 `seq`、沒有 gap marker。

### 7.2 重啟真正丟掉什麼

| 丟失項 | 位置 | 後果 |
|---|---|---|
| 六個 detector 的滾動窗 / cooldown / latch / touch_count | `signal_state.py` 記憶體 | 重啟後 `touch_count` 從 1 重數;300 s 窗重新累積 → 開頭 5 分鐘 `vol_burst` / `surge` 判準與平常不同尺 |
| `_policy_touch`(政策 first_of_day 記帳) | `signal_hub.py` 記憶體 | **重啟後同檔同政策會再發一次 `first_of_day=true`** → 影子期對帳的「首筆」被重複計數 |
| 回補 tick | `stock_engine` 刻意**不重放**進 hub | 斷線期間的事件**永久不存在**,而 jsonl 看起來只是那段時間比較安靜 |
| CDP 基準 | `_basis_cache` | 重新 sweep,期間 CDP 規則停用 |

**三個都是零錯誤訊號。** 尤其是 `_policy_touch` 這一項:影子期的整份對帳基準是
「同檔同政策當日首筆」,而重啟會靜默製造第二個「首筆」。09-07~09-11 的 151 列政策列裡
有沒有這種重複,**從檔案裡看不出來**(id 帶 `time_key`,不會撞)。

### 7.3 要加什麼(最小、只加欄、符合 W1)

一個 **session marker 列** + 每列一個 `boot` 欄,兩者互補:

```jsonc
// 1) server 起動 / 換日時各寫一列,kind 恆在(W1),但是**新列型** → 違反 W1「不新增列型」
{"type":"meta","kind":"session","boot":"20260911T090517Z-a3f1","trade_date":"2026-09-11", ...}
```
⚠ **W1 明文禁止新增列型**(研究腳本逐列讀 `s["kind"]` 且 `nosig.py` 的三桶分群以 kind 為輸入)。
所以正解是**只加欄**:

```jsonc
// 2) 每一列加一個 boot id(只加欄,既有讀者完全不受影響)
{"type":"signal","kind":"policy", ..., "boot":"20260911-090517-a3f1"}
```
`boot` 由 process 起動時生成一次(`trade_date` + 起動時刻 + 4 hex),常數成本
(每列多 ~28 bytes = 全日 +19 KB,+6.6% 檔案大小)。

有了它,離線就能:
- `set(row["boot"])` 的元素數 = 當天 process 數;
- 每個 boot 的首列時刻 = 斷點;
- 同 `(code, policy, boot)` 去重 = 修掉 `first_of_day` 的重複計數;
- 兩個 boot 之間的**空窗**可以被明確標成「不知道」而不是「沒有訊號」。

**這是本區塊投報率最高的一項改動**:一個字串欄、零契約破壞、解掉 §7.2 的四項裡的三項。

---

## 8. 量化系統標準:一筆訊號該有什麼才足以事後重現

以「這是要下實單的系統」為準繩,一筆事件記錄至少要能回答五個問題。逐項對照現況:

| # | 問題 | 應有 | 現況 | 判定 |
|---|---|---|---|---|
| 1 | **什麼時候發生的** | 交易所時刻 + 本機到達時刻 + 落檔時刻,且分得開 | 只有 `time`(tick 時刻,秒);且五分之四的規則其實用**本機牆鐘窗**判定(Q1 §3) | ❌ **1/3** |
| 2 | **哪一組參數判出來的** | 生效門檻的完整快照或不可變的參數版本指紋 | 只有 `rule_id` + `rule_name`;`signal_rules.json` 是 `atomic_write_text` **就地覆寫、零歷史**(`signal_rules.py:566`) | ❌ **0/1** |
| 3 | **當時的盤面是什麼** | 觸發當下的報價快照(價/量/五檔/參考價/漲停價) | 一般列只有 `price`;政策列有 `self`(chg_pct/to_limit_pct/touched_upper/locked_up)、`sweep`(detail)、`peers` —— **政策列做得相當好** | 🟡 **政策列 ~0.8 / 一般列 ~0.2** |
| 4 | **族群 / 同伴當時長什麼樣** | 成員名單 + 各自報價的快照 | 政策列有 `groups` / `peers` / `peers_up` / `peer_max` / `leader` / `peer_touched` / `screen_member` | ✅ **政策列 1/1**(一般列 0) |
| 5 | **觸發鏈**:哪一顆 tick → 哪一條規則的哪一個分支 → 哪一條政策 | 觸發 tick 的 id / seq、規則分支、政策判定的中間量 | `rule_id` 有;**觸發 tick 無任何識別**(`StockTick` 的 `seq` 沒有寫進訊號列);政策判定的中間量在 `evaluate_policies` 內,只留 `hits` | ❌ **~0.3/1** |

**加總:政策列 ≈ 3.1 / 5;一般訊號列 ≈ 1.5 / 5。**

### 8.1 最小補強(全部只加欄,符合 W1)

| 欄 | 值 | 成本 | 解掉什麼 |
|---|---|---|---|
| `boot` | process 起動指紋 | 28 B/列 | §7 的重啟斷點 + `first_of_day` 重複 |
| `params_sha` | `rule["params"]` 的 8 hex | 24 B/列 | 問題 2:事後知道當時門檻與現在一不一樣 |
| `t_src` | `"exchange"` / `"wall"` | 22 B/列 | 問題 1:哪些列的時間軸不可回放(Q1 §3.4 已提) |
| `tick_seq` | 觸發 tick 的 `StockTick.seq` | 18 B/列 | 問題 5:離線重放能對回同一顆 tick |

四欄合計 ~92 B/列 = 全日 +63 KB(**+22% 檔案大小**),`json.dumps` +0.6 µs/列。
**在 237 ms/日 的基準上完全無感。**

另外**參數快照的正解不是每列塞 params**,而是:
規則檔改成 append-only 的 `data/signal_rules_history.jsonl`(每次 `save_rules` 多寫一列),
訊號列只帶 `params_sha`。這樣 30 條規則 × 每天幾次編輯 = 每天幾列,零熱路徑成本。

---

## 9. Findings

> 標準:每條附 code 位置;頻率與量級誠實區分;推估標明。

### F-01 `os.replace` 撞到外部讀者 → 整趟回填中止、當天不再重試(**high**,零錯誤訊號)

**位置**:`signal_hub.py:1381` + `copycat/fileio.py:28-31`

```python
# signal_hub.py:1381 —— 沒有 try/except
await asyncio.to_thread(atomic_write_bytes, path, b"".join(lines))
```

**實測**(`bench_io.py`):Windows 上目標檔被**任何** handle 開著(含 `open(...,"r")` / `"rb"`)時,
`os.replace` → `PermissionError [WinError 5]`。CPython 不帶 `FILE_SHARE_DELETE`。

**觸發**:研究目錄 17 支腳本全部 glob prod 的 `data/signals/*.jsonl`;
`tickpanel.py`(522 行)與 `build_viewer.py` 讀整個目錄,秒級窗口。13:40 跑一次就撞得到。

**後果**:例外逃出 `for date, path in picked` 迴圈 → 逃出 `backfill_policy_outcomes` →
被 `_run_policy_outcomes` 接住 log 一行 → **本趟剩餘日檔全不補**,且 `ran_for` 已設 → **明天才重試**。
log 只有一行「T+1/T+2 回填未預期失敗」,**沒有「還剩幾檔沒處理」**。

**修法**:把 `atomic_write_bytes` 那一行包 `try/except OSError` → WARNING + `continue`
(續處理其餘日檔);並在收尾行加「本趟跳過 n 檔」。
**額外**:`atomic_write_bytes` 失敗時清掉殘留 `.tmp`(現行 docstring 明說不清)。

**風險**:零契約。`test_signal_outcome.py:538` 的 `boom_once` 測試現在驗的是
「整趟拋 → worker 續行」,加了 per-file 續行後那條測試的斷言要一起改(**事前標記為該變**)。

---

### F-02 回填收尾行只報「補了幾列」,不報「還有幾列該補」(**high**,零錯誤訊號)

**位置**:`signal_hub.py:1383`

```python
logger.info("T+1/T+2 回填完成:共回填 %d 列(掃 %d 個日檔,%s..%s)", total, len(picked), start, end)
```

**實測**:`2026-09-12 13:40:29 … 共回填 0 列(掃 5 個日檔,2026-09-04..2026-09-12)`,
而同一刻 **87 列**政策列 t1/t2 為 null(09-10 的 38 列缺 t2、09-11 的 49 列全缺)。
「全部補齊」與「一列都補不到」印出完全相同的字。

**根因兩層**:
(a) 週六 engine 日別停在 09-11 → `cutoff = min("2026-09-11","2026-09-12")` → **09-11 的檔被排除**
(log 的 `start=2026-09-04` 就是指紋:若 09-11 在窗內 start 會是 09-07);
(b) `targets` 為空的日檔直接 `continue`(`:1344`),從不計入任何統計。

**後果**:CLAUDE.md §1 的影子期判準寫「13:40 log『回填 n 列』」—— **這條判準無法分辨
『補完了』與『整個窗都沒選到』**。而影子期的整份結論建立在 t1_open 上。

**修法**:收尾行加兩個數:`仍缺 m 列(涵蓋 k 個日檔)` 與 `窗外仍缺 j 列`。
`m == 0` 才是「補完了」。窗外那個數是 F-03 的告警來源。

**風險**:零行為改動,純 log。要多掃一遍 targets(已在記憶體,零額外 IO)。

---

### F-03 日檔掉出 `policy_outcome_days` 窗 = 永久 null,無任何告警(**high**,零錯誤訊號)

**位置**:`signal_hub.py:1307`

```python
picked = sorted(dated[: self._cfg.policy_outcome_days])    # 預設 5
```

窗是「最近 N 個**日檔**」,所以停機幾天不會掉出去(這點設計是對的)。
但只要某一天的補值連續失敗 N 個交易日(TC4 一直逾時 / 該檔下市 / F-01 一直撞),
那個日檔就**靜默掉出窗,永遠是 null**。

**現況風險敞口**(實測):09-10 的 38 列 t2 只剩 **3 個交易日**的補救機會(窗內只有 09-11 比它新)。

**修法**:`backfill_policy_outcomes` 末尾多掃一遍**窗外**日檔的 policy 列(只算數不取數),
`> 0` 就印 WARNING 點名日期與列數。成本 = 每天一次多讀 ~20 個檔 × 3.4 ms ≈ **68 ms**(off-loop)。
或更省:只掃「窗邊界的下一個日檔」。

**風險**:零契約。

---

### F-04 `data/signals/*.jsonl` 兩條寫入路徑都沒有 fsync(**high**)

**位置**:`signal_hub.py:1415-1417`(append)、`copycat/fileio.py:28-31`(`atomic_write_bytes`)

```python
def atomic_write_bytes(path, content):
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(content)      # ← 無 fsync
    os.replace(tmp, path)         # ← 目錄也無 fsync
```

`os.replace` 對**目錄項**原子,但內容仍在 page cache。斷電/藍屏可得到「rename 完成、
內容未落盤」的檔 —— NTFS 典型是大小對、內容零。**而回填是整檔覆寫,壞掉的是一整天。**

`_MISSED-143.md` #141 指出 `atomic_write_text` 缺 fsync 但「受害清單全可重建」;
**`data/signals/` 不在那個清單,而它不可重建**:tick 流 in-memory、規則檔就地覆寫無歷史、
重放產不出同一組事件(Q1 §3)。這一份與 §7 的下單審計同級。

**修法**:給 `fileio.py` 加 `atomic_write_bytes(path, content, *, durable=False)`,
`durable=True` 時 `fh.write` → `fh.flush()` → `os.fsync(fh.fileno())` → `os.replace`
(Windows 上目錄 fsync 不可用也不需要,`MoveFileEx` 是 metadata 操作)。
只有 signals 與下單審計傳 `durable=True`。
append 側:`_append_jsonl` 在**換日的第一則**與**關機 flush**時 fsync,不必每則付(實測 fsync ~1 ms 級)。

**風險**:低。`durable` 預設 False → 既有 caller 零行為改變。

---

### F-05 落檔與 TC4 不可中斷取數同池,實測飽和時單則落檔 1.34 s(**medium**,架構)

**位置**:`signal_hub.py:1190`(`await asyncio.to_thread(self._append_jsonl, row)`);
全庫 66 處 `to_thread`,零處自訂 executor → 預設 `max_workers = min(32, 16+4) = 20`。

**實測**(`bench_loop.py`,以 1.5 s 阻塞工作佔格):

```
佔住  0 格 → 一則落檔  0.84 ms
佔住 10 格 → 一則落檔  0.95 ms
佔住 19 格 → 一則落檔  1.11 ms
佔住 20 格 → 一則落檔  1344.53 ms      ← 完全排隊
```

TC4 歷史取數最壞 20 s 且**不可中斷** → 20 格被吃滿時單則落檔可達 **20 s**。
佇列 1000 深,20 s 內 686 列/日的速率不會溢位,所以**不會丟**,只會遲。
真正的傷害在關機路徑(F-06)。

**修法**:給 jsonl 一條專屬 `ThreadPoolExecutor(max_workers=1, thread_name_prefix="signal-jsonl")`,
`loop.run_in_executor(ex, ...)`。零新相依、零契約。
**但必須同步處理**:`close()` 要 `ex.shutdown(wait=True, cancel_futures=False)`,
而那要算進關機預算(見 F-06)。

---

### F-06 `_flush_pending` 無 timeout;`_CLOSE_FLUSH_TIMEOUT` 已吃滿整格 slack(**medium**)

**位置**:`signal_hub.py:109`(`_CLOSE_FLUSH_TIMEOUT = 5.0`)、`:551-576`(`close`)、
`:1236-1246`(`_flush_pending`)、`shutdown_budget.py:44`(`LIFESPAN_SLACK_SECS = 5.0`)、
`app.py::_close_segment`(**無 timeout**)。

```python
async def _flush_pending(self) -> None:
    for row in rows:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(self._append_jsonl, row)    # ← 無 timeout,executor 飽和時無上界
```

`LIFESPAN_SLACK_SECS` 的 docstring 逐字寫它要涵蓋「crosscheck cancel / breadth /
**signals 的 bot.close + hub drain**」—— 而 `_CLOSE_FLUSH_TIMEOUT` **單獨就是 5.0**。
加上 `_flush_pending` 無上界、`_close_segment` 無 timeout,TC4 半死時 lifespan 可以
超過 `run_grace_secs()`(83 s)→ `run.ps1` `taskkill /T /F` →
**(a) 剩餘 jsonl 列永久丟失(零 log)、(b) 健康的 TC4 session 變殭屍(下一台開頭 ~60 s 零推播)**。

**修法**:(1) `_CLOSE_FLUSH_TIMEOUT` 降到 2.0 s(實測滿佇列 1000 列 = 345 ms,2 s 綽綽有餘);
(2) `_flush_pending` 整段包 `wait_for(..., 1.0)`,逾時就在 log 印**丟了哪些 id**;
(3) 若做 F-05 的專屬 executor,`shutdown_budget` 的 `LIFESPAN_SLACK_SECS` 要重新計算並改
`tests/server/test_shutdown_budget.py` 的不等式(**這是 CLAUDE.md §4「關機預算三方同源」契約**)。

**風險**:動到三方同源契約。改 `_CLOSE_FLUSH_TIMEOUT` 本身不需要改 `run.ps1`(那正是同源的意義),
但**降低它會改變「零漏」語意** —— 要 user 拍板「寧可丟幾列也要準時關」還是相反。

---

### F-07 `_append_jsonl` 每則付一次 `mkdir` + 一次 open/close(**medium**,只在放大時痛)

**位置**:`signal_hub.py:1412-1418`

**實測拆解**:
```
mkdir(parents=True, exist_ok=True) 單獨        = 46.2 us    ← 每則都付,全年無用
open("a")+write+close                          = 152.2 us
json.dumps(政策列)                             =   5.6 us
to_thread 往返                                 =  40.7 us
--------------------------------------------------------
一則端到端(loop 視角)                          = 345   us
批次 50 列一次 open                             =  12.8 us/列   ← 快 17 倍
```

**現況量級誠實說**:686 列/日 × 345 µs = **237 ms/全日**,分散在 4.5 小時 → **不是效能問題**。
列出來的理由是它是「要做量化系統」時第一個會爆的地方:
規則數 30(`MAX_RULES`)+ 自選 150(`WATCHLIST_LIMIT`)的上限下,
或加上 tick 級記帳,就是 6,860 列/日 → 2.37 s,而且**每一則各佔用共用 executor 一格**(F-05)。

**修法**(**只在真的放大時做**):worker 改「drain 佇列拿 N 則 → 一次 `to_thread` 寫 N 行」;
`mkdir` 移到 `start()` 與換日各一次。
**必須一起改**:`close()` 的 `join()` 零漏語意、`_flush_pending` 的保底。
**不必擔心的**:行尾。沒有任何測試斷言 `_append_jsonl` 產生 CRLF,而回填是 per-line 保留行尾
—— 批次寫只要維持「一則一行、`\n` 由文字模式翻譯」就完全相容(見 §3.5 的口徑校正)。

---

### F-08 回填的解析段(12.8 ms)留在 event loop 上(**low-medium**)

**位置**:`signal_hub.py:1314-1338`

```python
raw = await asyncio.to_thread(path.read_bytes)      # ← off-loop ✔  實測 0.10 ms
lines = raw.splitlines(keepends=True)               # ↓ 以下全在 loop 上
for i, line_bytes in enumerate(lines):
    line = line_bytes.decode("utf-8")
    row = _policy_row_needing_outcome(line)         # json.loads 每一行
```

**實測**:5 個日檔 / 3,147 行 = **12.8 ms 連續 loop 阻塞**。
同一個函式裡三段 IO,讀與寫都丟了執行緒,**中間 CPU 最重的那段反而留著**。

一天一次、13:40 盤後 → **嚴重度低**。列出來是因為它是教科書案例,而且修法零風險:
把「讀 → 逐行解析 → 產 targets」整段包成同步函式丟一次 `to_thread`,
回來只拿 `targets`(TC4 取數是 async,必須留在 loop)。

**成本效益**:省 12.8 ms/日。**不值得單獨做**,但若做 F-01 要動這段附近的程式碼,順手做。

---

### F-09 `read_signals` 每次全檔重讀重解(**low**)

**位置**:`signal_hub.py:1448-1482` ← `app.py:1581` ← `useSignalFeed.ts:81`(5 分鐘輪詢)

**實測**:289 KB / 686 列 = **3.39 ms**,在 `to_thread`(off-loop ✔)。
全日 ~54 次 × 開著的分頁數 → 單分頁 **183 ms/日**。

**不是問題**。但檔案是 append-only,增量讀(記 `(path, size, mtime, rows)`,只讀尾端新位元組)
可以降到接近零。**注意**:`today_signals` 的「同日走單檔讀、不去重」語意必須逐字保留
(重啟後重發同一事件會有同 id 兩列,是刻意的)。

**建議**:**不做**。3.39 ms 的 off-loop 讀取換一份要維護的快取失效邏輯,不划算。

---

### F-10 離線讀者零防禦,而它們直接吃 prod 目錄(**high**,但在 repo 外)

**位置**:`C:\Users\USER\Documents\copycat-trading-review\scripts\` — 17 支讀 jsonl,
**無版控**(Q1 已記整體;本條聚焦讀取契約)。

```python
# nosig.py:26-28 / signal_join.py:8-11 / signal_lag.py / val.py / cooldown_check.py
for p in sorted(glob.glob("C:/side-project/copycat/data/signals/*.jsonl")):
    for line in open(p, encoding="utf-8"):        # ← 嚴格解碼
        if line.strip(): sig.append(json.loads(line))   # ← 無 try/except
print(..., {k: ... for k in set(s["kind"] for s in sig)})   # ← 裸鍵
```

三個並存的問題:
1. **半寫入的尾巴會殺掉整支腳本**。server 這半花了兩段 docstring 防這件事,研究那半零防禦。
2. **直接吃 prod 目錄** → 與 13:40 的 `os.replace` 對撞(F-01 的另一半)。
3. **kind 白名單各自為政**:`nosig.py` 七種、`build_viewer.py` 六種、
   而歷史資料裡有 **11 種**(含已退役的 `market_limit_lock/open` 共 846 列)。

**修法**(不改 repo,改工作方式):
(a) 研究前先 `robocopy` / `xcopy` 到 `copycat-trading-review\data\signals-snapshot\` 再讀
  —— **一行指令解掉 F-01 的觸發源與這裡的 (2)**;
(b) 三行的共用 loader(`try: json.loads except: continue` + `errors="replace"`);
(c) kind 白名單收成一份 `kinds.py`,含已退役集合。

**風險**:repo 外,零契約。但 CLAUDE.md §4 的 W1 契約**假設**這些讀者存在且形狀不變,
所以它們的健壯度其實是 repo 的一部分責任。

---

### F-11 政策列有兩種鍵序,對帳 diff 已經花掉一次(**low**,已發生)

**位置**:`signal_hub.py:1370-1373`(補新欄到舊列)

**實測**:151 列政策列有**兩種**鍵序 —— 09-07 的 29 列是
`..., t2_date, trade_date, d_close, d_high`,其餘 122 列是 `..., t2_date, d_close, d_high, trade_date`。

原因:09-07 的列沒有 `d_close`/`d_high`,回填 `row["d_close"] = ...` 把它們 append 到 dict 尾,
而 `trade_date` 早就在尾(`_enqueue` 的 `{**row, "trade_date":...}`)。

**無功能影響**(JSON 物件無序),但 CLAUDE.md §4 把「鍵序變動 → 對帳 diff 整檔紅」
列為要防的症狀 —— 而它已經因為**另一個**原因發生了。任何以 `diff` 做對帳的流程要知道。

**修法**:不修。記錄在案即可(或在加新欄時走「重建整個 row 用固定鍵序」,但那等於整檔 dumps,更糟)。

---

### F-12 非交易日 13:40 仍跑一趟完整回填,結果恆 0 列(**low**,浪費)

**位置**:`signal_hub.py:1250-1270` —— `_past_time(now, policy_outcome_time)` **不看交易日曆**。

**實測**:2026-09-12(週六)13:40 跑了一趟,掃 5 個日檔,`bars_range` 打了
**17 次 TC4 日 K + 3.4 s 的 `basis_gap_secs` sleep**,結果 0 列。
週日 09-13 會再跑一次。一年約 115 個非交易日 × 17 次 = **~2,000 次白打**。

`copycat/trading_calendar.py` 已有純判定函式,`SignalHub` 沒用。

**嚴重度低**(盤後、TC4 通常關著 → `bars_range` 走 `disconnected` 降級路徑幾乎零成本),
但它會讓 `grep 回填` 的判準多出一堆噪音行,而且是**唯一**會在非交易日主動打 TC4 的訊號側路徑。

**修法**:`_policy_outcome_worker` 的條件加 `and is_trading_day(now.date())`。
**注意**:不能加在 `backfill_policy_outcomes` 裡(它是 public,測試直呼)。

---

### F-13 `_append_jsonl` 的日別來自 row,缺欄會落到 `data/signals/.jsonl` 黑洞(**low**,防禦缺口)

**位置**:`signal_hub.py:1413`

```python
path = self._signal_path(str(row.get("trade_date", "")))
# _signal_path: data/signals/{trade_date.replace('-','')}.jsonl  → "" → "data/signals/.jsonl"
```

`"" → ".jsonl"`,而回填的 `stem` 檢查是 `len(stem) != 8 or not stem.isdigit()` → 跳過;
`read_signals` 也永遠讀不到它。**寫進去就再也沒人看得到,零錯誤訊號。**

現況 `_enqueue` 一律 stamp `trade_date`(實測 8,789 列缺 0 列),所以**目前不會發生**。
但它是「防禦寫成了黑洞」的形狀:`row.get(..., "")` 的 fallback 沒有任何人會發現。

**修法**:`if not trade_date: logger.error(...); return`。三行。

---

### F-14 訊號列不帶參數指紋,而規則檔就地覆寫無歷史(**high**,量化缺口)

**位置**:`copycat/signal_rules.py:566`(`save_rules` → `atomic_write_text` 就地覆寫)
+ `signal_hub.py:1017-1018`(列上只有 `rule_id` / `rule_name`)

規則可以從 UI 即時編輯(`upsert_rule`,`MAX_RULES = 30`)。
一則 09-07 的 `vol_burst` 列與一則 09-11 的 `vol_burst` 列,`rule_id` 相同、`rule_name` 相同,
**但門檻可能完全不同,而檔案裡沒有任何痕跡**。

**後果**:影子期四週的對帳(spec #192)建立在「同一組規則跑四週」的假設上,
而這個假設**沒有任何機械保證,也沒有事後查核的手段**。

**修法**(見 §8.1):訊號列加 `params_sha`(8 hex,24 B/列);
`save_rules` 額外 append 一列到 `data/signal_rules_history.jsonl`(每次編輯一列,一天幾列)。
兩者合起來才可重現。

**風險**:`params_sha` 是**只加欄**,符合 W1;history 檔是新檔,無讀者。
`tests/fixtures/signal_param_specs.json` 的 parity 機制不受影響。

---

### F-15 重啟會靜默製造第二個 `first_of_day=true`(**high**,零錯誤訊號,影響影子期結論)

**位置**:`signal_hub.py:1124-1127, 1165`(`self._policy_touch` 是純記憶體 dict)

```python
key = (code, policy)
count = self._policy_touch.get(key, 0) + 1
first = count == 1
notify = first and not late
```

`_policy_touch` 在 `on_rollover` 才清(換日),**重啟不會恢復**。
盤中重啟後,同檔同政策會**再發一次 `first_of_day=true` 且 `notify=true`**。

**影響面**:spec #192 的影子期對帳與 Discord 推播窗判準(「同檔同政策當日首筆」)
**整個建立在這個旗標上**。09-07~09-11 的 151 列裡有沒有這種重複,**從檔案裡看不出來**
(id 帶 `time_key`,不會撞;`touch_count` 會從 1 重數)。

**修法(短)**:加 `boot` 欄(§7.3)→ 離線可以用 `(code, policy, boot)` 去重並看出斷點。
**修法(中)**:`start()` 時從當日 jsonl 重建 `_policy_touch`
(`read_signals(trade_date)` 已存在,3.4 ms)—— 這是**行為改動**,要走 `/mod`。

---

### F-16 `market_limit_lock` / `market_limit_open` 是歷史包袱,而 kind 集合沒有單一權威清單(**low-medium**)

**位置**:歷史資料 846 列(全庫 9.6%);產生點已於 2026-08-16 刪除;
`signal_hub._kind_text:138-170` 無分支 → `return kind` 印英文;
前端 `signal-model.ts` 保留在 `SignalKind` union 當「防禦濾網」。

kind 的權威清單散在四處:`_kind_text` 的 if 鏈、前端 `SignalKind` union、
`nosig.py::LEGACY_KINDS`、`build_viewer.py:162` 的 tuple。四份各不相同。

W1 契約寫「不新增列型」是為了保護讀者,但**沒有人宣告「已退役列型」的集合**,
所以任何新讀者都得自己猜。

**修法**:`copycat/signal_kinds.py` 一個模組,`LIVE_KINDS` / `RETIRED_KINDS` 兩個 frozenset,
`_kind_text` 與前端 parity fixture 都引它。零行為,零熱路徑。

---

### F-17 檔案零輪替、零備份、零校驗(**medium**)

**實測**:26 個檔 / 3.16 MB;近 5 日 mean 257 KB/日 → **約 64 MB/年**。
`data/` 是 git-ignored,沒有備份腳本(對比:`stock_watchlist.json` 有
`data/stock_watchlist.backup-*.json`)。

磁碟不是問題。問題是:**這是唯一一份訊號歷史,單點、無備份、無校驗、無 fsync(F-04)**。
研究腳本 glob 整個目錄 → 誤刪一個檔會讓對帳結果靜默改變,而沒有任何東西會發現。

**修法**:(a) 每日回填成功後順手寫 `data/signals/manifest.json`
(每檔的 size + sha256 + 列數 + policy 列數 + 待補列數)—— 和 F-02 的統計同一趟算完;
(b) 研究前的 snapshot copy(F-10)天然就是備份。

---

## 10. 失效模式表

| # | 模式 | 觸發 | 症狀(使用者/系統看到) | 零訊號 | 位置 | 嚴重度 | 現在怎麼發現 |
|---|---|---|---|---|---|---|---|
| M-01 | 回填撞外部讀者 → 整趟中止 | 13:40 有人在跑研究腳本 | log 一行「未預期失敗」;剩餘日檔全不補;明天才重試 | 半(有 log,但不說剩幾檔) | `signal_hub.py:1381` | **high** | 只能事後 `grep 未預期失敗`;**加 per-file 續行 + 收尾統計** |
| M-02 | 收尾行「共回填 0 列」= 補完了 ⇄ 一列都沒選到 | 非交易日 / engine 日別落後 / 窗選錯 | 判準綠、87 列 null | **是** | `signal_hub.py:1383` | **high** | **實測已發生(09-12)**;加「仍缺 m 列」 |
| M-03 | 日檔掉出 5 日窗 → 永久 null | 連續 N 交易日補不到 | 政策列 t1/t2 永遠 null;影子期樣本靜默縮水 | **是** | `signal_hub.py:1307` | **high** | 無;加窗外待補計數 WARNING |
| M-04 | 斷電/藍屏 → 整天訊號檔零內容 | 回填 `os.replace` 後未落盤時斷電 | 該日檔大小對、內容零;研究腳本讀到空 | **是** | `fileio.py:28-31` | **high** | 無;加 fsync + manifest sha |
| M-05 | 盤中重啟 → 第二個 `first_of_day` | 任何盤中重啟 | 同檔同政策當日推播兩次首筆;對帳重複計數 | **是** | `signal_hub.py:1124` | **是**(id 不撞、touch_count 重數) | 無;加 `boot` 欄 |
| M-06 | 回補 tick 不重放 → 斷線期間事件永久不存在 | TC4 斷線 / 訂閱掉 | jsonl 只是「那段比較安靜」 | **是** | `stock_engine` 回補路徑 | **high** | 無;`boot` 欄 + gap 標記 |
| M-07 | 規則門檻被改而歷史列認不出來 | UI 改規則 | 同 `rule_id` 的列跨週期不可比;影子期假設失效 | **是** | `signal_rules.py:566` | **high** | 無;加 `params_sha` + history 檔 |
| M-08 | 關機時 executor 飽和 → jsonl 尾巴永久丟失 | TC4 半死 + Ctrl+C | run.ps1 taskkill;丟了幾列無 log | **是** | `signal_hub.py:1236-1246` | **medium** | 無;`_flush_pending` 加 timeout + 印丟掉的 id |
| M-09 | 研究腳本被半寫入尾巴殺掉 | 上次硬殺切在中文中間 | `UnicodeDecodeError` / `JSONDecodeError` traceback | 否(會炸) | 研究腳本 | medium | 一跑就知道;加共用 loader |
| M-10 | `trade_date` 缺欄 → 寫進 `data/signals/.jsonl` | `_enqueue` 以外的 caller | 那些列從此沒人看得到 | **是** | `signal_hub.py:1413` | low | 無;三行 fail-fast |
| M-11 | 非交易日白打 TC4 + 噪音 log | 每個週末 / 國定假日 | `grep 回填` 多出噪音行 | 否 | `signal_hub.py:1261` | low | log 裡看得到;加交易日閘 |
| M-12 | 落檔遲滯(非丟失) | executor 20 格被 TC4 佔滿 | WS 已顯示、jsonl 晚幾秒到;前端 5 分鐘 baseline 會蓋回來 | 是 | `signal_hub.py:1190` | low | **實測 1.34 s @ 20 格**;專屬 executor |
| M-13 | 誤刪一個日檔 | 手誤 / 清理腳本 | 對帳數字靜默改變 | **是** | `data/signals/` | medium | 無;manifest |
| M-14 | 新增列型 → 研究腳本 KeyError | 違反 W1 | `s["kind"]` 或 `s["policy"]` KeyError | 否(會炸) | 研究腳本 | medium | 一跑就知道;CLAUDE.md §4 已釘 |
| M-15 | `.tmp` 殘留誤導排查 | `atomic_write_bytes` 中途失敗 | `data/signals/20260910.tmp` 長期躺著 | 是 | `fileio.py:29` | low | 無;失敗時清 tmp |

---

## 11. 改造順序 + 量測判準

> 原則:**先讓「壞了看得出來」,再讓「壞不了」,最後才談快。**
> 這一段目前的速度完全夠用(237 ms/日),所以效能項全部排在最後,而且大部分標「不做」。

### 步驟 1 —— 回填續行 + 收尾統計(F-01 + F-02) · S · 🔴 行為改動

**做什麼**:`atomic_write_bytes` 那一行包 `try/except OSError` → WARNING + continue;
收尾行改成 `共回填 n 列(仍缺 m 列涵蓋 k 個日檔;本趟跳過 j 檔)`。

**為什麼排第一**:M-01 與 M-02 是現在**正在發生**的兩個問題(實測 09-12 的 0 列 + 87 列待補),
而且它們讓後面每一步的驗證都沒有觀測基礎。先量後改。

**量測判準**:
```powershell
# 1. 下一個交易日 13:40 之後
Select-String "回填完成" logs\server-*.log | Select-Object -Last 1
#   必須出現「仍缺 m 列」欄位;m 的值與下列離線統計逐字相等
.venv\Scripts\python -c "..."   # = scratchpad/stat3.py 的『需補』總數
# 2. 故意在 13:39:50 開一個 handle 咬住昨日檔,13:41 看 log
#    必須有「回填寫檔失敗,跳過 <檔名>」WARNING,且「共回填 n 列」n > 0(其餘日檔仍補到)
```

**回滾**:純 log + 一個 try/except,`git revert` 單一 commit。
`test_signal_outcome.py::test_unexpected_error_keeps_worker_alive` 的斷言要事前標「該變」。

---

### 步驟 2 —— 窗外待補告警(F-03) · S · 🟢

**做什麼**:收尾時多掃窗外日檔的 policy 列,`> 0` 印 WARNING 點名日期與列數。

**為什麼排這**:依賴步驟 1 的統計基礎設施(同一趟算)。它是 M-03 唯一的偵測手段。

**量測判準**:
```powershell
# 人工製造:把 policy_outcome_days 暫調成 1(configs/signals.json),跑一趟
#   必須出現「窗外仍缺 j 列」且 j = 實際待補 − 窗內待補
# 恢復設定後,同一行的 j 必須回到 0(或 09-10 的 38,視當時狀態)
```

**回滾**:純 log。

---

### 步驟 3 —— `boot` 欄(F-15 + M-05/M-06 的偵測) · S · 🟢 只加欄

**做什麼**:`SignalHub.__init__` 生成 `self._boot = f"{起動日}-{HHMMSS}-{4 hex}"`;
`_emit` 與 `_emit_policies` 的 payload 各加一個 `"boot": self._boot`。

**為什麼排這**:它是 §7 四項損失裡三項的**唯一離線可見性**,而且 W1 完全允許(只加欄)。
成本 28 B/列 = 全日 +19 KB、`json.dumps` +0.2 µs。

**量測判準**:
```powershell
# 盤中刻意重啟一次 server,盤後:
python -c "import json,glob;s=[json.loads(l) for l in open(r'data\signals\<今日>.jsonl',encoding='utf-8') if l.strip()];print(sorted({r.get('boot') for r in s}))"
#   必須列出 2 個不同的 boot 值,且第二個的首列時刻 ≈ 重啟完成時刻
# 前端 rail / toast 行為必須完全不變(未知欄位)
```

**回滾**:移除兩行;既有讀者對多一個欄位無感(已由 `market_limit_*` 的歷史證明)。

---

### 步驟 4 —— `fileio` 加 `durable=` + signals 兩條寫入路徑用它(F-04) · M · 🔴

**做什麼**:`atomic_write_bytes(path, content, *, durable=False)`;
`durable=True` 時 `open("wb")` → `write` → `flush` → `os.fsync(fileno())` → `os.replace`。
回填傳 `durable=True`;`_append_jsonl` 在**換日首則**與**關機 flush**時 fsync。

**為什麼排這**:M-04 是本區塊唯一「一次壞掉一整天且不可重建」的模式,但它要先有步驟 1–3
的可觀測性才驗得出來(否則壞了也不知道)。

**量測判準**:
```python
# 微量測(scratchpad):durable 版 vs 現行版對 289 KB 的耗時
#   現行實測 0.46 ms;durable 版應 < 20 ms(一天一次,無感)
# 契約:tests/server/test_signal_outcome.py 的兩條 byte 比對必須全綠(內容零改變)
# 其餘 atomic_write_bytes caller 的行為必須完全不變(durable 預設 False)
```

**回滾**:`durable` 預設 False → 只要不傳就是舊行為。

---

### 步驟 5 —— `params_sha` + 規則歷史檔(F-14) · M · 🟢 只加欄 + 新檔

**做什麼**:`_make_slot` 時算 `sha256(json.dumps(rule["params"], sort_keys=True))[:8]` 存 slot;
`_emit` / `_emit_policies` 各加一欄。`save_rules` 額外 append 一列到
`data/signal_rules_history.jsonl`(`{ts, rule_id, kind, params, sha}`)。

**為什麼排這**:影子期四週的結論建立在「同一組規則」上,而現在沒有任何查核手段。
排在 fsync 之後是因為它讓檔案更重要(更值得先保住)。

**量測判準**:
```powershell
# 1. 改一條規則的門檻 → data/signal_rules_history.jsonl 多一列,sha 與改前不同
# 2. 改規則後發出的第一則該 kind 訊號,params_sha 等於新 sha
# 3. 離線:同一個 rule_id 在整個影子期的 params_sha 集合大小 == 1(才有資格合併統計)
```

**回滾**:移除欄位 + 刪新檔。W1 相容。

---

### 步驟 6 —— 關機路徑收緊(F-06) · M · 🔴 涉三方同源契約

**做什麼**:`_CLOSE_FLUSH_TIMEOUT` 5.0 → 2.0;`_flush_pending` 整段 `wait_for(1.0)` 並在
逾時 log 印丟掉的 id 清單;重算 `LIFESPAN_SLACK_SECS` 並改
`tests/server/test_shutdown_budget.py` 的不等式。

**為什麼排這**:要 user 拍板「寧可丟幾列也要準時關」vs 相反 —— **這是決策不是事實**,
按 HITL 紀律要停等。排在後面因為它動 CLAUDE.md §4 契約。

**量測判準**:
```powershell
# 健康路徑:Ctrl+C → log「關機 signals 段」耗時 < 1 s,且「共回填 / 落檔」零丟失訊息
# 注入:monkeypatch 讓 executor 飽和 → 必須印「關機落檔逾時,丟棄 id=[...]」而不是無聲
# 契約:.venv\Scripts\python -m pytest tests/server/test_shutdown_budget.py -q 全綠
# run.ps1 的 run_grace_secs() 值必須與新不等式一致(該測試已釘字面 parity)
```

**回滾**:三個常數回舊值 + revert 測試。

---

### 步驟 7 —— 非交易日閘(F-12) · S · 🔵

**做什麼**:`_policy_outcome_worker` 的觸發條件加 `is_trading_day(now.date())`。

**量測判準**:週末 13:41 `Select-String "T\+1/T\+2 回填" logs\server-*.log` **零命中**;
下一個交易日 13:40 照常有完整三行。

**回滾**:移除一個條件。

---

### 步驟 8 —— manifest + 研究 snapshot(F-17 + F-10) · M · 🟢

**做什麼**:回填收尾寫 `data/signals/manifest.json`(每檔 size/sha256/列數/policy 列數/待補列數);
研究側加一支 `snapshot.ps1` 先複製再讀。

**量測判準**:
```powershell
# manifest 的 sha256 與現場重算逐字相等;待補列數 == 步驟 1 的 m
# 研究腳本改讀 snapshot 後,13:40 期間跑 tickpanel.py 不再讓回填 log 出現「寫檔失敗」
```

---

### 步驟 9 —— jsonl 專屬 executor(F-05) · M · 🔵 · **條件性**

**前提**:步驟 6 完成(關機序列要一起收)。
**做什麼**:`ThreadPoolExecutor(max_workers=1, thread_name_prefix="signal-jsonl")` +
`loop.run_in_executor`;`close()` 加 `ex.shutdown(wait=True)`。

**量測判準**:重跑 `bench_loop.py` 的飽和測試 —— 20 格被佔時單則落檔必須從 **1,344 ms** 降到 **< 5 ms**。

**回滾**:改回 `to_thread`。

---

### 步驟 10 —— 批次落檔(F-07) · M · **現在不做**

**觸發條件**:當 `列數/日 > 3,000`(現況 686)或 `to_thread(_append_jsonl)` 進了
任何 p99 監測的告警線時才做。
**量測判準**(做的時候):全日落檔總耗時從 237 ms → < 30 ms;
`tests/server/test_signal_outcome.py` 兩條 byte 比對全綠;`close()` 零漏測試全綠。

---

## 12. 工具選型

| 工具 | 用在哪 | 為什麼 | 取捨 | 結論 |
|---|---|---|---|---|
| `orjson` | **只用在讀**(`read_signals` / 回填解析) | 解析 3–6×;`read_signals` 3.39 ms → ~1 ms | **絕對不可用於 jsonl 寫入**:CLAUDE.md §1 的影子期判準逐字 `grep '"kind": "policy"'` 帶空白,`orjson.dumps` 不輸出空白;§4 的 byte 比對釘死浮點字面與鍵序 | **不建議**(收益 2.4 ms/次 × 54 次/日 = 130 ms/日,不值得引一個相依) |
| `aiofiles` | jsonl 落檔 | — | 底層還是 thread pool,等於現況 | **不建議** |
| `ThreadPoolExecutor(1)`(stdlib) | jsonl 落檔 + notify | 解 F-05 的 20 s 排隊;零相依、零契約 | 關機序列要一起收(步驟 6 前置) | **有條件導入**(步驟 9) |
| `hashlib`(stdlib) | `params_sha` / manifest sha256 | 解 F-14 / F-17 | sha256 對 289 KB ≈ 0.5 ms,一天一次 | **建議導入** |
| `os.fsync`(stdlib) | `fileio.atomic_write_bytes(durable=)` | 解 F-04 | 一天一次多 ~15 ms | **建議導入** |
| `jsonschema` / `pydantic` 驗 jsonl 列 | 落檔前驗形 | 機械保證 W1 | 熱路徑上每列驗 = 幾十 µs;而契約破壞是**改 code 時**發生不是 runtime | **不建議**(該用測試釘,不是 runtime 驗) |
| `polars` / `pyarrow` / Parquet 取代 jsonl | 訊號歷史存檔 | 查詢快、壓縮好 | **形狀不對**:檔案是 append-only 事件流、一天 686 列 / 257 KB、要人肉 `grep`、要逐行 bytes 保留、17 支離線腳本都吃 JSON。轉 Parquet 等於把 CLAUDE.md §4 的整套契約重寫一遍,換來 3.39 ms → 0.5 ms | **不建議** |
| SQLite(stdlib `sqlite3`) | 訊號歷史 | 原子性、索引、WAL 解掉 M-04/M-13 | 同上:破 W1、破 grep 判準、破 byte 比對測試、17 支腳本全改。**但它是 5 年後的正解** | **不建議現在**;若哪天列數上萬/日再談 |

---

## 13. 不要動(已經寫對的地方)

1. **`read_signals` 的 `errors="replace"` + 壞行跳過**(`:1448-1482`)。
   round-2 HR-1 的分析是對的:嚴格解碼會讓整天消失,擴 except 到 `(OSError, ValueError)` 更糟。

2. **回填的逐行 bytes 處理 + 行尾原樣接回**(`:1318-1381`)。
   四條不變式每一條都有具體理由,且被 `test_signal_outcome.py` 的兩條 byte 比對釘住。
   **特別是「只重寫 dirty 的列」與「零補不碰檔」** —— 這是對帳 diff 乾淨的唯一保證。

3. **`cutoff = min(trade_date, today)` 的雙半守門**(`:1291`)。
   它保證回填目標與正在 append 的檔永不重疊。週六那個副作用(§3.2)要修的是**告警**不是這條判準。

4. **「開盤前起動不跑回填」**(`:1261`,整體 review F-10 拍板)。
   與 CDP 基準暖機共用 `api.lock`,而回填晚到 13:40 零損失。

5. **`o <= 0` 不跳到下一根冒充 T+1**(`:1356-1357`,spec review F-03)。
   欄名會說謊是比 null 更糟的事。

6. **jsonl 與 Discord 兩條佇列不合併**(`:1167`,CC-5)。
   jsonl 是真相源,Discord 可丟;共用一條時 Discord 卡住 jsonl 就缺角,而缺角靜默不可回復。

7. **`close()` 的 `join()` 先於 `cancel()`**(`:559-567`)。
   worker 手上那一則已 `get()` 未寫完,先取消就永久消失。

8. **`basis_gap_secs = 0.2` 兩邊共用**。
   13:40 實測整趟 4.3 s,其中 4.6 s 是這個 sleep —— 看起來「浪費」,
   但它換的是「不與主圖回補搶 `api.lock`」。降到 0.05 s 只省 3 s/日,不值得動。

9. **`json.dumps(..., ensure_ascii=False)` 帶空白的預設分隔符**。
   CLAUDE.md §1 的影子期判準 `grep '"kind": "policy"'` 依賴它。不要「順手」加 `separators=`。

10. **一則訊號的 WS 先送、jsonl 後寫**(`:1036-1037`)。
    前端要即時,jsonl 是歷史。順序反過來會把落檔的 345 µs 加進使用者看到的延遲。

11. **`_put_drop_oldest` 的「丟最舊保最新」+ `_DROP_LOG_EVERY` 節流**(`:1673`)。
    熱路徑零反壓 + 不靜默吞掉。實測 `put_nowait` 0.616 µs。

---

## 14. Open questions(需要 user 拍板)

1. **關機時「零漏」與「準時關」哪個優先?**(步驟 6)
   現況 `_CLOSE_FLUSH_TIMEOUT = 5.0` 選了零漏,但它吃滿 `LIFESPAN_SLACK_SECS` 的整格,
   代價是 TC4 半死時整條 lifespan 可能被 `taskkill` —— **兩邊都輸**。

2. **`policy_outcome_days = 5` 夠不夠?**
   窗是「最近 5 個日檔」。若某天連續補不到(TC4 逾時 / 下市),5 個交易日後永久 null。
   加到 10 的成本 = 每天多讀 5 個檔(+17 ms off-loop)。要不要加?

3. **`_policy_touch` 要不要在重啟時從 jsonl 重建?**(F-15)
   這是**行為改動**:重啟後不再重發 `first_of_day`。
   影子期已經跑了一週,中途改會讓前後兩段的推播口徑不同 —— 要不要等四週結束再改?

4. **研究目錄的 17 支腳本要不要納版控?**
   Q1 已把它列為 critical(「真正在用的那一份不在版本控制裡」)。
   本區塊的 W1 契約**假設它們存在且形狀不變**,但沒有任何東西保證這件事。

5. **`boot` 欄要不要同時進 WS payload?**
   只進 jsonl 的話前端無感(好);同時進 WS 的話前端可以顯示「本次 session 起」的分界。
   我傾向**只進 jsonl**(WS 每則多 28 B × 8 條連線 = 每則多 224 B 序列化)。

6. **manifest 的 sha256 要不要涵蓋「已回填」後的內容?**
   回填會改檔 → sha 會變。要記「最後一次修改後的 sha」還是「首次封檔的 sha」?
   前者能偵測誤刪/損毀,後者能偵測「有人改過我的歷史」。兩個都要的話要記兩個。

---

## 附錄:量測腳本與原始輸出

- `stat_jsonl.py` — 26 檔全庫統計(列數 / kind / 行尾 / 鍵序 / 重複 id)
- `stat2.py` — per-day 回填完成度 / 時間回跳 / 欄位覆蓋率
- `stat3.py` — 回填規模(distinct code / gap 秒數 / 政策列位元組佔比)
- `bench_io.py` — `json.dumps` / `_append_jsonl` / `atomic_write_bytes` / **Windows `os.replace` 對抗 open reader**
- `bench_loop.py` — `to_thread` 往返 / `put_nowait` / 端到端 / **共用 executor 飽和測試**

全部唯讀,不碰 repo;`bench_io.py` / `bench_loop.py` 只寫 scratchpad 下的 `bench/` 子目錄。
