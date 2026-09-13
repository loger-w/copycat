# B13 — 資料層與 IO 原語(atomic write / cache / CLI)架構檢查

分析日期:2026-09-13 · 分析對象:`C:/side-project/copycat`
量測環境:Windows 11 Home 26200、Python 3.13.13、`.venv`、**Defender RealTimeProtection = Enabled**
(`Get-MpComputerStatus` 查得;排除清單需 admin 才看得到 → 以下所有檔案 IO 數字都**已含** Defender minifilter 開銷)

量測腳本(全在 scratchpad,未動 repo):
`scratchpad/bench_dataio.py` / `bench_runtime_io.py` / `bench_sqlite.py` / `bench_daily.py` / `bench_brokers.py` / `bench_csvwrite.py`

---

## 0. 一句話結論

**這個區塊沒有熱路徑。** 全區塊在「每 tick / 每 0.1 s」尺度上執行的 code 是 **0 行** —— `data/`、`fileio.py`、
`configio.py`、`cli.py` 沒有任何一行被 ZMQ tick 迴圈或 WS 廣播迴圈呼叫到。因此:

- **不要**為了「效能」把 `fileio.py` / `configio.py` 改寫成 orjson / aiofiles —— 那是純粹的過度工程。
- 真正的問題有兩類,都不是「每秒跑幾次」型:
  1. **離線 / 開發迴圈被 JSON-per-file 與「迴圈內重寫整檔」拖成分鐘級**(最嚴重一條:一次
     `backfill-daily` 有 **615 秒是純粹在重寫同一份 52 MB CSV**,寫入量 12 GB)。
  2. **從量化系統的角度,這一層缺的不是速度而是「東西」** —— 系統**完全不持久化 tick**。
     收到的每一筆成交、每一次五檔位移在 process 結束時全數消失。這是改寫成量化系統時
     資料層的第一號缺口:沒有錄下來的東西,再快的後端也回測不出來。

---

## 1. 架構地圖

### 1.1 檔案與職責

```
copycat/fileio.py        39 行   全庫唯一 atomic write 原語(3 個 helper)
copycat/configio.py      32 行   dataclass config JSON loader 樣板(啟動期唯一)
copycat/cli.py          451 行   argparse 單體:21 個 subcommand,全部 lazy import
copycat/__main__.py       5 行   → cli.main()

copycat/data/
  models.py              54 行   Bar1K(frozen+slots)+ UTC→台北分鐘索引 + raw dict 解析
  store.py               60 行   1K bar 的「一個 stock-day 一個 JSON 檔」讀寫
  daily.py              209 行   DailyIndex:全市場日線載進記憶體 + bisect 隨機存取
  import_neigui.py      258 行   neigui 種子 → copycat 標準格式(一次性)
  backfill_finmind.py   174 行   FinMind 日線回補(按日,冪等合併)
  backfill_daytrade.py  224 行   FinMind 當沖名單 + 處置期間回補 + DayTradeIndex
  backfill_brokers.py   166 行   FinMind 分點日報回補 + read_brokers
  backfill_tc4.py       169 行   TC4 歷史 1K 回補(唯一會碰 ZMQ 的 data/ 檔)
  scan_events.py        122 行   自產漲停事件掃描(daily → events.csv append)
  label_events.py       108 行   events.csv 分點標籤就地補值
```

### 1.2 磁碟上的實際資料(實測)

| 目錄 | 檔數 | 總大小 | 單檔平均 | 形狀 |
|---|---:|---:|---:|---|
| `data/1k/<stock>/<date>.json` | **21,254** | **256.7 MB** | 12.1 KB | 1,715 個股子目錄,一個 stock-day 一檔,`bars` 為 9 欄陣列的陣列 |
| `data/brokers/<stock>/<date>.json` | **11,011** | **411.7 MB** | 31.7 KB | 分點日報聚合,每檔約 435 個 broker dict |
| `data/daily/prices.csv` | 1 | **52.1 MB** | — | 1,013,469 rows × 8 欄,全市場日線 |
| `data/daytrade/day_trading.csv` | 1 | 9.1 MB | — | 當沖名單 |
| `data/events/events.csv` | 1 | 0.49 MB | — | 11,048 事件 |
| `data/signals/<YYYYMMDD>.jsonl` | ~30 | 0.07–0.30 MB/日 | — | runtime 產物,686 列/日 |
| `data/market/breadth-<date>.json` | 51 | 6–21 KB/日 | — | 家數帶序列 |
| `data/audit/capital-*.jsonl` | 22 | 0.32 MB | — | 下單審計 |
| `logs/server-*.log` | — | 0.24–1.55 MB/場 | — | 17,865 行 / 兩天 |

**合計約 730 MB。**(任務簡報提到的 1.24 GB 是 neigui 那份種子原始資料,不在本 repo。)

### 1.3 資料流

**離線 / 一次性(CLI)**

```
neigui 種子 ──import-neigui──┐
FinMind ──backfill-daily────→ data/daily/prices.csv ──┐
FinMind ──backfill-daytrade─→ data/daytrade/*.csv     ├→ DailyIndex.load / DayTradeIndex.load
FinMind ──backfill-brokers──→ data/brokers/**.json    │   (整份載進記憶體,4.2 s)
TC4 ZMQ ──backfill-tc4──────→ data/1k/**.json ────────┤
                                                       ↓
                          scan-events → events.csv(append)
                          label-events → events.csv(就地補 broker_ids)
                                                       ↓
                   replay / tday-features / tday-search / fade-*
                          (read_bars 逐 stock-day 讀 JSON)
                                                       ↓
                                    out/ 報告 + docs/evidence/
```

**線上(server runtime)** —— 這一層只有 5 個磁碟接觸點,全部低頻:

| 接觸點 | 產生點 | 頻率 | 是否卡 loop |
|---|---|---|---|
| 訊號 jsonl append | `signal_hub.py:1412 _append_jsonl` | 幾百次/日 | 否(`asyncio.to_thread`) |
| 訊號 jsonl 全檔讀 | `signal_hub.py:1462 read_signals` | 每分頁每 5 分鐘 | 否(`app.py:1581 to_thread`) |
| 家數帶落檔 | `breadth_engine.py:956 _save` | **每 10 s** | **是**(同步,在 `_run_cycle` 內) |
| 下單審計 append | `server/audit.py:28 append_audit` | 每筆委託 2 行 | 否(`client.py:885 to_thread`) |
| 自選 / 規則 / 盤前篩選落檔 | `stock_watchlist.py:172` 等 | 每次 PUT / 每日一次 | 視站點 |

**關鍵事實:`DailyIndex` 與 `read_bars` 完全不在 server 裡。** grep 全庫,
`DailyIndex` / `read_bars` / `DayTradeIndex` / `read_brokers` 的 caller 只有
`copycat/backtest/*`、`copycat/replay/*`,一個 `copycat/server/*` 都沒有。這條事實決定了
本區塊所有「JSON 慢」的 finding 都只影響**開發迴圈與研究**,不影響下單延遲。

---

## 2. 熱路徑逐條(誠實分級)

本區塊沒有「每 tick」級。以下按實際頻率由高到低列出**所有**會執行到的路徑:

### HP-1 `breadth_engine._save()` — 每 10 秒,**在 event loop 上**

`copycat/server/breadth_engine.py:956-972`

```python
def _save(self) -> None:
    """tmp + `os.replace` 原子寫。落檔失敗只降級(記憶體序列照在),不得拖垮 poll。"""
    ...
    tmp = path.with_name(f"{path.name}.tmp")
    try:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
```

呼叫鏈:`_poll_loop`(`breadth_engine.py:356`,`poll_secs` 預設 **10.0**,見
`breadth_config.py:22`)→ `await self._run_cycle()` → `self._apply(rows)`(**同步**)→
`_append`(`:595`)→ `_save()`。整條 `_apply`+`_save` 沒有 `to_thread`。

量級:當日序列尾端約 21 KB JSON。`json.dumps` + `mkdir` + 建新檔 + `os.replace` ≈ **1 ms**
(由 12 KB payload 實測 0.54 ms 外推;`mkdir` 每輪一次 syscall)。09:00–13:40 共 ~1,680 次/日。
**單次 1 ms 不致命,但它是「盤中 event loop 上唯一的週期性同步檔案寫」**,而 loop 上同時
跑著 8 條 WS 的 relay。

### HP-2 訊號 jsonl append — 幾百次/日,已在 worker thread

`copycat/server/signal_hub.py:1412-1419`

```python
def _append_jsonl(self, row: dict) -> None:
    path = self._signal_path(str(row.get("trade_date", "")))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
```

實測 open-append-close = **0.167 ms/次**。每列都 `mkdir` + `open` + `close`。686 列/日 →
全日 0.11 s。**完全不是問題,不要動。**

### HP-3 `read_signals` 全檔讀 — 每分頁每 5 分鐘

`copycat/server/signal_hub.py:1448-1481`,實測 289 KB / 686 列 = **5.77 ms/call**。
`app.py:1555-1581` 已用 `asyncio.to_thread` 包起來(註解甚至已經寫明「訊號多的日子會卡住
event loop(8 條 WS 一起頓)」)。前端 `useSignalFeed.ts` 的 `BASELINE_REFETCH_MS = 5 * 60_000`。
**已處理妥當,不要動。** 唯一殘留風險是它與 `daily_bars` / `capital close` 共用 loop
預設 executor(程式碼註解 review C-1 已記載)。

### HP-4 下單審計 — 每筆委託,**在委託送出的關鍵路徑上**

`copycat/server/audit.py:28-38` + `copycat/capital/client.py:885`

```python
# client.py:884-885
# 前置:寫不進去 → AuditWriteError,錢沒動(to_thread 不卡 loop,review B6)
await asyncio.to_thread(self._audit, self._record(action, req))
```

`append_audit` 內部:module-level `threading.Lock` → `base.mkdir` → `open(path,"a")` → `write` →
`flush()` → `close`。實測 open-append-close 0.167 ms,`flush()` 再加 4.1 µs/行。
**所以純寫檔成本 < 0.2 ms** —— 但 `to_thread` 走 loop 預設 executor,而該池同時承載
`signals/today`(5.8 ms)、`daily_bars`、`capital close`,且程式碼註解已記載「TC4 半死的
殭屍執行緒堆積時這條會跟著排隊」。委託送出前**必須等這一發回來**,所以執行緒池排隊
直接變成下單延遲。

### HP-5 `_Tee.write` 每筆 flush — 所有 stdout/stderr

`copycat/server/__main__.py:83-90`,每筆 `write` 立刻 `flush()`。實測 flush 版
**4.1 µs/行** vs 不 flush 0.4 µs/行。實測 log 量 17,865 行 / 兩天。全日成本 < 0.1 s。
**設計是對的(crash 當下要有證據),不要動。**

### HP-6(離線)`read_bars` — 回測 / replay 每 stock-day 一次

`copycat/data/store.py:42-60`。實測(300 個隨機 stock-day,warm cache):

```
read_bars x300 : 220.5 ms → 0.735 ms/檔
  breakdown: read_text 36.6 ms | json.loads 96.8 ms | Bar1K build 93.1 ms
```

**IO 只佔 17%,83% 是 json.loads + dataclass 建構。** 全庫 21,254 檔 → **約 17.4 秒**。

### HP-7(離線)`read_brokers` — label-events 每事件一次

`copycat/data/backfill_brokers.py:83-91`。實測 **5.754 ms/檔**(平均 31.7 KB、~435 個
broker dict)。`label_events` 對 11,048 列各呼叫一次 → **約 63 秒**,`--verify-existing` 同樣。

### HP-8(離線)`DailyIndex.load` — 每次 CLI 執行一次

`copycat/data/daily.py:31-56`。實測 **4,201–4,737 ms**(1,013,469 rows)。拆解:

```
read_bytes 52MB          :    21 ms
decode utf-8             :    20 ms
csv.DictReader 純迴圈    : 1,953 ms
csv.reader   純迴圈      :   864 ms
其餘(_DayRow ×6 float + sort + _dates 建表): ~2,200 ms
```

**檔案 IO 只佔 1%。** 瓶頸 100% 在 `csv.DictReader` 的 per-row dict 建構與 `float()` 呼叫。

---

## 3. Findings

### B13-01 `backfill-daily` 在每日迴圈內重寫整份 52 MB CSV — 615 秒純浪費 · **critical**

**位置**:`copycat/data/backfill_finmind.py:156`(迴圈自 `:137` 起)

```python
    for day in _dates(start, end):
        if day in done:
            skipped += 1
            continue
        raw_rows = _fetch_retry(fetch, day, token, sleep_s)
        ...
        _write_atomic(prices_path, rows)          # ← 156:重寫全部 1,013,469 rows
        atomic_write_text(manifest_path, json.dumps({"done_dates": sorted(done)}, ...))
        if sleep_s:
            time.sleep(sleep_s)
```

`_write_atomic`(`:93-99`)對 `rows`(整份 100 萬筆的 dict)做 `sorted(rows)` + 逐列
`DictWriter.writerow`。實測:

```
_read_existing           : 2,261 ms(啟動一次)
_write_atomic 整份       : 2,672 ms / 次(52.1 MB)
230 天回補迴圈內重寫成本 ≈ 615 s,累計寫入 ≈ 12.0 GB
```

**影響**:一次 `python -m copycat backfill-daily`(預設 2024-06-02..2025-05-01 = 334 天)
的網路等待只有 `sleep_s 0.7 × 天數 ≈ 234 s`,而重寫成本 **≈ 890 s** —— 純 CPU/磁碟浪費是
網路等待的 3.8 倍,而且是 O(天數 × 全庫列數) 的二次式:資料越多越慢。加上 12 GB 的
NTFS 寫入全部要過 Defender minifilter。這條是全區塊唯一真正的 O(n²)。

**修法**(不改資料格式、不動任何跨檔契約):

```python
# A 案(最小改動,5 行):迴圈內只寫 manifest,整檔在迴圈結束後寫一次
    for day in _dates(start, end):
        ...
        if raw_rows:
            done.add(day)
            dirty = True
        atomic_write_text(manifest_path, ...)      # 小檔,保留(續傳 marker 的意義在這)
        if sleep_s:
            time.sleep(sleep_s)
    if dirty:
        _write_atomic(prices_path, rows)           # 迴圈外一次
```
但這樣「中斷不丟進度」的語意會被破壞(docstring `:4-5` 明講)。所以:

```python
# B 案(保住續傳語意):每 N 天才落一次 + 收尾必落
    FLUSH_EVERY = 20
    if fetched % FLUSH_EVERY == 0:
        _write_atomic(prices_path, rows)
    ...  # 迴圈外 finally: _write_atomic(prices_path, rows)
```
成本從 615 s 降到 ~31 s,最壞丟 20 天進度(重跑 20 次 FinMind request,配額充裕)。

```python
# C 案(正解,一併解掉 B13-02/03):prices 改 sqlite3 表,迴圈內只 INSERT OR IGNORE 當日
#   → 每日成本從 2,672 ms 降到 ~20 ms,續傳語意反而更強(WAL 每筆 commit)
```

**風險**:A/B 案只改 `backfill_finmind.py` 一個檔,`prices.csv` 的 schema 與讀者
(`DailyIndex.load`、`scan_events`)完全不動;測試 `tests/data/test_backfill_finmind.py` 存在。
C 案要同時改 `daily.py::DailyIndex.load` 與 `scan_events.py:62` 的直讀,是跨檔改動。
**effort**:A/B = S;C = L。

---

### B13-02 1K bar 用「21,254 個 JSON 小檔」存 —— 換 sqlite3 blob 實測快 27 倍 · **high**

**位置**:`copycat/data/store.py:12-60`

```python
def bars_path(data_dir: Path, stock_id: str, date: str) -> Path:
    return data_dir / "1k" / stock_id / f"{date}.json"
...
def read_bars(...):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Bar1K(m=int(r[0]), open=r[1], ..., unch_volume=r[8]) for r in payload["bars"]]
```

**實測對照**(300 個隨機 stock-day,同一批資料):

| 路徑 | 時間 | 每 stock-day |
|---|---:|---:|
| 現況 `read_bars`(JSON per file) | 245.3 ms | 0.818 ms |
| sqlite3 + 欄式 blob(`array` 打包) | **9.1 ms** | **0.030 ms** |
| sqlite3 全表掃(一次 SELECT) | **4.9 ms** | 0.016 ms |

**27 倍**(隨機存取)/ **50 倍**(全掃)。**sqlite3 是 stdlib,不破壞 `dependencies = []`。**

外推到全庫 21,254 stock-day:
- 現況全量載入 ≈ **17.4 s**(還沒算 `os.walk` 的 164 ms 與 21,254 次 `Path.exists`(11.5 µs 各)= 244 ms)
- sqlite3 全掃 ≈ **0.35 s**

**空間**:本次用 float64 打包,300 天佔 5.46 MB(JSON 3.6 MB)—— 比 JSON 大。
但價格本來就是 `market.py` 的**毫元整數**語意,改 int32 scaled 後每 bar 9×4 = 36 B,
全庫約 **200 MB**(vs JSON 256 MB),而且從 21,254 個 MFT entry 收成 1 個檔。

**parquet / pyarrow 比較**:pyarrow 會帶進 ~50 MB wheel + numpy 相依,而收益相對 sqlite3
只在「欄式壓縮 + 跨檔 predicate pushdown」,對「一次讀一個 stock-day 的 270 根」這種
存取樣態沒有額外好處。**不建議引入 pyarrow/parquet 只為了 1K store。**(見 §5 工具選型)

**風險**:`store.py` 的兩個公開函式(`write_bars` / `read_bars`)是 seam,caller 只有
`backtest/*` 與 `replay/*`(6 處,已 grep 完)。`tests/data/test_store.py` 存在。
**沒有任何跨檔契約會被動到** —— `Bar1K` dataclass 的欄位語意不變、`validate` golden gate
比的是 replay 產物不是儲存格式。改法建議走 expand–contract:`read_bars` 先加「有 db 就讀 db、
沒有就讀 JSON」的雙讀,離線跑一次遷移腳本 + `copycat validate` 對照。
**effort**:M。

---

### B13-03 `DailyIndex.load` 4.2 秒 —— 瓶頸是 `csv.DictReader` 與 dataclass,不是磁碟 · **high**

**位置**:`copycat/data/daily.py:31-56`

```python
    @classmethod
    def load(cls, data_dir: Path) -> DailyIndex:
        rows: dict[str, list[_DayRow]] = {}
        with (data_dir / "daily" / "prices.csv").open("r", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):                      # ← 1,953 ms 純這一行
                raw_spread = r.get("spread")
                rows.setdefault(r["stock_id"], []).append(
                    _DayRow(date=r["date"], open=float(r["open"]), ...)   # ← ~2,200 ms
                )
        for lst in rows.values():
            lst.sort(key=lambda x: x.date)
```

**實測**:現況 4,201 ms / `csv.reader` + tuple 版 **1,937 ms**(2.2×)/ sqlite3 全載
**1,408 ms**(3.0×)。檔案讀取本身只有 21 ms。

`csv.DictReader` 對 1M 列各建一個 dict(8 鍵),然後立刻丟掉 —— 純粹的中間物件。
`_DayRow` 是 `frozen=True, slots=True`(`daily.py:14`),已經是最省的 dataclass 了,
但 1M 個實例 + 1M 次 `.sort(key=lambda)` + 第二份 `self._dates` 索引(`:29`,又一份
1M 個 str 的 list)才是另外那 2.2 s。

**修法**(由輕到重):
1. **`csv.reader` + 欄位索引**(S,~2.2×):照上面 `bench_daily.py::variant_csvreader` 的寫法。
   `_DayRow` 保留,只是不再經 dict。
2. **欄式 `array`**(M,~4×且記憶體降 5×):`self._open = array('d')` 等 6 條平行陣列 +
   `self._offset[sid] = (start, end)`。`_find` 回 index,所有 accessor 改吃 index。
   `adv20` / `ma` / `pos_52w` 從「list comprehension + sum」變成 slice + sum,快且不配置。
3. **sqlite3**(L,3× 載入且支援不全載):真正的收益不是 3× 而是**不必全載** ——
   `screening` 只要 20 日窗、`scan_events` 只要一段日期區間,現在卻都要先付 4.2 s 全載。

**額外**:`daily.py:163-181 bb_width_pct` 對 `window` 天各呼叫一次 `bb_width`,每次又
`_close_window(n)` 重掃 —— O(window × n) 且每次配置新 list。離線路徑,但若被 GA 搜索的
內圈呼叫就會放大。建議改前綴和(Welford / running sum),同一份 `_close_window` 只掃一次。

**風險**:`DailyIndex` 的 18 個公開方法是 backtest/replay 的核心 seam,`tests/data/test_daily.py`
+ `test_daily_struct.py` 存在,`copycat validate` 的 golden gate 直接蓋這條路(replay 產物
逐字比對)。改完跑 `validate` 就知道有沒有改壞 —— 這是本區塊**驗證條件最好**的一條。
**effort**:1 = S,2 = M,3 = L。

---

### B13-04 系統完全不持久化 tick —— 量化系統資料層的第一號缺口 · **high(架構)**

**位置**:全庫。grep `copycat/live/` 與 `copycat/server/` 的所有寫檔點,只找到
訊號 jsonl(`signal_hub.py:1416`)、審計 jsonl(`audit.py:34`)、家數帶 JSON
(`breadth_engine.py:873/970`)、快取類(watchlist / rules / screen)。**沒有任何一行把
收到的 tick 寫下來。** CLAUDE.md §5 明說「ZMQ tick 流 in-memory 不持久化」,這是刻意的。

**代價(對量化系統而言)**:
- `docs/strategy.md` 的**硬限制「五檔委買賣深度不可回測」**(CLAUDE.md §0a)之所以成立,
  正是因為歷史來源只有 TC4 的成交當下一檔 Bid/Ask。但**現在系統每天盤中都在收
  `stock_models` 的五檔位移歸一、試撮窗資料**(`live/stock_models.py`),收完就丟。
  每多丟一天,就是永久少一天「本來可以錄到」的微結構樣本。
- spec #192 影子期的政策對帳(CLAUDE.md「對帳仍需另抓的量:研究『放到尾盤』的 13:20 出場價
  和盤中鎖死判定不在列上」)—— 這正是「沒錄 tick 只好事後補抓日 K 當代理」的直接後果。
- 掃單簇 golden(`tests/fixtures/sweep_cluster_golden.json`)來自研究目錄的離線資料,
  線上偵測器的**回歸驗證沒有生產流量可以重播**。

**量級估算**:自選上限 150 檔(CLAUDE.md 契約),每檔日均 ~2,000 筆成交 →
約 30 萬筆/日。每筆打包成 32 B(時間 int32 + 價 int32 + 量 int32 + bid/ask int32 ×2 + flags)
= **9.6 MB/日**、一年約 2.3 GB。若加上五檔十檔位移每筆 40 B → 約 25 MB/日。
**這個量級對本機 SSD 完全不是問題。**

**修法**:在 `live/tc4.py` 的 tick 回呼下游(**不是回呼裡**)掛一個 recorder:
- 環形 buffer(`collections.deque(maxlen=…)`)+ 一條 writer 執行緒,每 1–2 s 批次 flush;
- 格式:`struct.pack` 定長 record append 到 `data/ticks/<YYYYMMDD>/<code>.bin`,
  或直接一張 sqlite3 表(WAL + 批次 commit,stdlib)。
- **絕不可以**走 `atomic_write_text`(全檔重寫)也**絕不可以**每筆 open/close。

**風險**:這是**新增**,不動任何既有契約。唯一要小心的是它必須是 **fire-and-forget**:
recorder 慢 / 磁碟滿**絕不可以**反壓到 tick 回呼(`tc4.py` 的回呼在 ZMQ 執行緒上)。
建議 `deque(maxlen=N)` 滿即丟最舊 + 60 s 節流 WARNING —— 與 `ws.py::WsBroadcaster.dropped`
同一套已驗證的政策。
**effort**:M。

---

### B13-05 `atomic_write_text` 沒有 fsync —— 斷電時目標檔可能變空,且無訊號 · **medium(正確性)**

**位置**:`copycat/fileio.py:21-31`

```python
def atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")     # ← 寫進 page cache,未落盤
    os.replace(tmp, path)                          # ← rename 是原子的,內容未必在
```

`os.replace` 保證**目錄項**的原子替換,但 tmp 的**內容**還在 OS page cache。Windows/NTFS
在非 transaction 模式下,rename 的 metadata 可能先於 data 落盤 → 斷電後拿到一個
**名字對、內容是 0 位元組或半截** 的目標檔,而原本的舊版本已經沒了。

**誰會痛**:
- `data/stock_watchlist.json`(150 檔自選)—— 壞了整個訂閱池空掉;
- `data/signal_rules.json` —— `signal_rules.py:548` 的版本遷移鏈遇到空檔會怎樣要另查;
- `data/signals/<date>.jsonl` 的回填(`signal_hub.py:1381 atomic_write_bytes`)—— 整日訊號真相源;
- `data/daily/prices.csv`(52 MB)—— 斷電在寫的那 2.7 s 內就整份沒了。

**修法**(3 行,零契約影響):

```python
def atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(".tmp")
    data = content.encode("utf-8")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())      # ← 內容確實落盤後才改名
    os.replace(tmp, path)
```
**注意**:`atomic_write_text` 現在走 `Path.write_text`,有**預設 newline 翻譯**
(`\n` → `\r\n`,fileio.py:4 docstring 明講三個 helper「newline 語意不同**不可互換**」)。
改成 `open("wb")` 會**改掉行尾**,而 `signal_hub` 的 T+1 回填有 **byte 逐字比對測試**
(`tests/server/test_signal_outcome.py`)。所以必須:
`with tmp.open("w", encoding="utf-8") as fh:`(保留 newline 翻譯)+ `flush` + `fsync`。

**成本**:fsync 在 NTFS 上是真 flush,每次約 0.5–5 ms。以本區塊最高頻的
`breadth_engine._save`(10 s 一次)算,可接受;`_append_jsonl` **不要**加 fsync(它每列
一次,而且丟最後一列的代價遠低於 5 ms × 686)。
**風險**:低,但要跑 `tests/server/test_signal_outcome.py` 的 byte 比對確認行尾沒變。
**effort**:S。

---

### B13-06 `breadth_engine` 手刻第二、三份 atomic write,繞過 `fileio.py` 的「唯一實作」 · **medium**

**位置**:`copycat/server/breadth_engine.py:872-875` 與 `:967-972`

```python
        tmp = path.with_name(f"{path.name}.tmp")
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
```

而 `fileio.py:1` 的 docstring 明寫「**全專案唯一實作,取代各站點手刻**」。這兩份是漂掉的
複製品,而且 tmp 命名規則**不同**(`with_name(name + ".tmp")` vs `with_suffix(".tmp")`)。

**症狀**:B13-05 若只修 `fileio.py`,這兩個站點**靜默地拿不到 fsync** —— 家數帶與連板數
落檔仍然可能斷電變空,而且沒有任何訊號告訴你「這裡沒跟上」。這正是 CLAUDE.md 通篇在防的
「改契約只改一邊」型漂移,只是這次漂的是內部原語不是跨檔契約。

**修法**:兩處改成 `atomic_write_text(path, json.dumps(payload, ensure_ascii=False))`,
`except OSError` 的降級語意不變(`atomic_write_text` 不吞例外,caller 的 try 照用)。
**風險**:tmp 檔名從 `breadth-2026-09-11.json.tmp` 變成 `breadth-2026-09-11.tmp` ——
若有任何 glob 掃 `data/market/*.json` 會受影響(實際上 `_series_path` 是精確路徑,無 glob)。
**effort**:S。

---

### B13-07 `path.with_suffix(".tmp")` 在同目錄同 stem 不同副檔名時會撞名 · **medium**

**位置**:`copycat/fileio.py:22 / 28 / 36`

```python
    tmp = path.with_suffix(".tmp")
```

`with_suffix` 替換**最後一個**副檔名。若同一目錄下存在 `foo.csv` 與 `foo.json`,兩者的
tmp 都是 `foo.tmp` —— 兩個並行寫者會互相踩掉對方的 tmp,`os.replace` 會拿到別人的內容
或 `FileNotFoundError`。

**現況掃查**:目前 repo 的實際路徑沒有這種對子(`prices.csv` / `backfill_manifest.json`
stem 不同;`day_trading.csv` / `disposition.csv` / `manifest.json` 也不同)。**所以這是
一顆未爆彈不是現行 bug**。但同時也意味著:**同一個檔案不可以有兩個並行寫者**。
CLAUDE.md 已經為 watchlist 記了「PUT/bot 同鎖」、為訊號回填記了「只碰日期同時小於 hub 日別
與牆鐘日的日檔」—— 這兩條規矩其實就是在補 `fileio` 缺的互斥。

**修法**:tmp 名加上 pid + 單調序號:

```python
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{next(_SEQ)}.tmp")
```
代價:例外路徑會殘留更多 tmp(fileio.py:9 已聲明「寫 tmp 中途失敗 → tmp 殘留」)。
若要收,加一個 `except: tmp.unlink(missing_ok=True); raise`。
**注意**:改 tmp 命名會動到 `tests/` 裡任何斷言 tmp 殘留檔名的測試(需先 grep `.tmp`)。
**effort**:S。

---

### B13-08 `label-events` 對 11,048 個事件各讀一個 32 KB JSON —— 63 秒 · **medium**

**位置**:`copycat/data/label_events.py:89` + `backfill_brokers.py:83-91`

```python
        brokers = read_brokers(data_dir, r["stock_id"], r["date"])   # 5.754 ms × 11,048
```

實測 `read_brokers` **5.754 ms/檔**(31.7 KB、435 個 broker dict)。全程約 **63 s**,
`--verify-existing` 再一次。而實際用到的只有 `top_netbuy_hits`(`label_events.py:27-37`)
取的 **top-5**:整份 435 個 dict 建出來只為了排序取前 5。

`data/brokers` 是全庫最大的一塊(**411.7 MB / 11,011 檔**),而且每檔的
`{"broker_id","name","buy","sell"}` 裡 `name` 是中文字串,重複率極高 —— 這份資料
用 JSON 存的膨脹率是全庫最糟的。

**修法**:
- 最小改動:`read_brokers` 之上加一層「只回 top-N 淨買超」的函式,仍然要 parse 全檔,
  只省掉 list 建構 —— **收益有限,不值得**。
- 正解:與 B13-02 同一套 —— sqlite3 一張
  `brokers(stock_id, date, broker_id, name_id, buy, sell)` 表,broker 名字另建
  `broker_names(name_id, name)` 維度表(全台券商分點約 1,000 個,現在被重複存了 480 萬次)。
  `top_netbuy_hits` 直接變成 `SELECT ... ORDER BY buy-sell DESC LIMIT 5`,
  **63 s → 亞秒**,磁碟從 411 MB 降到 ~80 MB。
**風險**:`read_brokers` 的 caller 只有 `label_events.py:68/89`(2 處,已 grep)。
`tests/data/test_backfill_brokers.py` + `test_label_events.py` 存在。
**effort**:M。

---

### B13-09 `backfill-tc4` 的 `_needs_refetch` 對 11,048 條全 parse 一遍才知道要不要抓 · **medium**

**位置**:`copycat/data/backfill_tc4.py:18-29`

```python
def _needs_refetch(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))   # ← 整份 12 KB 解析
        if isinstance(payload, list):
            return True
        if not isinstance(payload, dict) or "bars" not in payload:
            return True
```

`_find_missing`(`:32-49`)對 events.csv 的每一列都跑這個。以現有 11,048 列、
命中率高(多數檔已存在)估算:11,048 × ~0.5 ms(read+loads,不建 Bar1K)≈ **5.5 秒**
只為了「檢查形狀」。這是 **舊格式偵測**(舊版存成裸 list)的遺留。

**修法**:形狀檢查只需要看前幾個位元組 —— 舊格式開頭是 `[`,新格式是 `{`:

```python
    with path.open("rb") as fh:
        head = fh.read(1)
    if head != b"{":
        return True
    # 深度檢查留給真的要用的時候(read_bars 本來就會 KeyError)
```
11,048 × 11.5 µs(等同 `Path.exists`)≈ **0.13 s**,快 **40 倍**。
或者:B13-02 改 sqlite3 後,這整個函式變成一條 `SELECT 1 FROM bars WHERE ...`。
**風險**:`tests/data/test_backfill_tc4.py` 存在且有壞檔案例,要確認 `"bars" not in payload`
那條分支還有測試涵蓋(用開頭位元組檢查會放過「是 dict 但沒有 bars 鍵」的檔)。
保守做法:開頭位元組是 `{` 才**再**做完整 parse,對正常檔多讀一次,對舊/壞檔早退。
**effort**:S。

---

### B13-10 `import-neigui` 逐 stock-day atomic write,21,254 次 tmp+rename · **medium**

**位置**:`copycat/data/import_neigui.py:35` → `store.write_bars` → `fileio.atomic_write_text`

```python
            bars.sort(key=lambda b: b.m)
            write_bars(data_dir, rec["stock_id"], rec["date"], bars)      # 每行一次 atomic write
```

實測 `atomic_write_text`(12 KB)= **0.540 ms** vs 直接 `write_text` = **0.230 ms**,
**atomic 版是 2.3 倍**(多一次建檔 + 一次 rename,兩次都過 Defender minifilter)。
`json.dumps` 270 根 bar = 0.371 ms。

21,254 次 → atomic 部分 **11.5 s** + dumps **7.9 s** ≈ **20 秒**,加上
`_import_daily` / `_import_limitup` / `_build_events` 與尾端對 events.csv 全表
`read_bars`(`:239/241`,兩次 × 11,048 ≈ 18 s)。整條 `import-neigui` 是分鐘級。

**這裡的 atomic 是浪費**:一次性匯入是「全有全無」的批次作業,中途掛掉本來就要重跑,
逐檔原子性毫無價值。且 `import_neigui.py:254` 的 manifest 反而用**非** atomic 的
`Path.write_text` —— 原子性給錯了地方。

**修法**:給 `write_bars` 加 `atomic: bool = True` 參數,批次匯入路徑傳 `False`;
或 B13-02 之後整個變成一次 `executemany`(實測 300 天建 db 1.56 s,含 JSON 讀取)。
**風險**:`store.write_bars` 的 caller 有 `import_neigui.py:35` 與 `backfill_tc4.py:93`。
後者是逐筆網路回補,**要保留 atomic**。
**effort**:S。

---

### B13-11 `screen_engine._read_cache` 同一趟被讀 2–3 次,每次重新 parse · **low**

**位置**:`copycat/server/screen_engine.py:394-412`

```python
    def _read_cache(self) -> dict | None:
        payload = json.loads(self._cache_path().read_text(encoding="utf-8"))
        ...
    def _cached_target_date(self) -> _dt.date | None:
        payload = self._read_cache()        # 第 1 次
    def _cached_daytrade_rows(self) -> int | None:
        payload = self._read_cache()        # 第 2 次
```

檔案含約 60 個候選 dict,約 10 KB → 每次 ~0.1 ms。**每日 08:00 跑一次 + 啟動補跑。**
量級完全不重要,列出來只是為了說明 `_CACHE_VERSION` 機制的形狀。

**`_CACHE_VERSION` 機制評估(任務問題 4)**:
全庫有 5 個獨立的 `_CACHE_VERSION`(`backtest/pipeline.py:48`=1、`screen_engine.py:55`=2、
`signal_rules.py:58`=4、`stkfut_map.py:26`=2、`stock_names.py:36`=1、`stock_watchlist.py:38`=3)。
兩種語意混在同一個名字裡:
- **作廢式**(`screen_engine:399`、`stkfut_map:111`、`pipeline:259`):版本不符 → 當沒有 → 重算。
  失效成本 = 重跑一次 FinMind 取數(screen ≈ 數十秒)或重跑特徵管線(pipeline,分鐘級)。
- **遷移式**(`signal_rules.py:59-61`):`_SUPPORTED_VERSIONS = tuple(range(1, _CACHE_VERSION+1))`
  + 遷移鏈。失效成本 = 0,但 bump 必須配一條遷移。
- **只寫不讀**(`stock_names.py:134` 寫了 `_cache_version` 但沒有任何地方比對)——
  這一顆是**裝飾品**,bump 它不會讓任何 cache 失效。這是個真的洞:改了 names 格式以為
  bump 就安全,實際上舊檔照吃。

**建議**:把「作廢式」與「遷移式」用不同的常數名分開(`_CACHE_VERSION` vs `_SCHEMA_VERSION`),
並補上 `stock_names` 的讀取側比對。**effort**:S。

---

### B13-12 CLI 是 451 行的 if-chain,但 lazy import 做得對 —— 不要重構 · **low(反向)**

**位置**:`copycat/cli.py:158-431`

21 個 `if args.command == "...":` 分支,每個分支內部才 `import`。看起來很土,但這正是
讓 `python -m copycat screen` 不必載 `backtest/fade_cells.py`(2,000 行)的原因。
唯一在模組頂層的 import 是 `run_import` 與 `TC4_DEFAULT_PORT`(`:11-12`)——
`run_import` 拉進 `data.daily` + `data.store`,約 20 ms,可以下放到分支內。

**這裡不要動。** 換成 subparser dispatch table 或 click/typer 只會多一個相依、
少一點可讀性,而啟動時間本來就已經是毫秒級。

---

### B13-13 `_import_k1` / `scan_events` 的 CSV 全表讀寫 —— 量級可接受,不動 · **low(反向)**

`scan_events.py:25-36` 把 `events.csv`(11,048 列)與 `limitup_all.csv` 全讀進 list、
append 後整份重寫。實測 events.csv 只有 0.49 MB → 全程 < 100 ms,而且**每次只跑一次**
(不在迴圈內,與 B13-01 的病相反)。`label_events.py:47-50` 同理。**不要動。**

---

### B13-14 Windows / NTFS / Defender 的實際代價 · **medium(環境)**

**實測事實**:
- `Get-MpComputerStatus` → `RealTimeProtectionEnabled = True`,排除清單需 admin 才查得到。
- `atomic_write_text` 0.540 ms vs `write_text` 0.230 ms(12 KB)—— 差的 0.31 ms 就是
  「多建一個新檔 + 一次 rename」的 NTFS + minifilter 成本。
- `Path.exists()` 11.5 µs/次(warm);`os.walk` 21,254 檔 = 164 ms。
- `open-append-close` 0.167 ms;`flush()` 4.1 µs。

**對本設計的影響**:
1. **每次原子寫都建新檔** = 每次都觸發一次 Defender on-close 掃描。`data/1k` 的
   21,254 個小檔在 `import-neigui` 期間就是 21,254 次掃描。
2. **NTFS 小檔的 MFT 開銷**:21,254 + 11,011 = 32,265 個小檔,每個至少一個 MFT record
   (1 KB)+ 目錄 B-tree 節點。1,715 + 1,491 = 3,206 個子目錄。備份 / 同步 / 防毒全掃
   的成本是「檔數」驅動不是「位元組」驅動。
3. **`os.replace` 在 NTFS 上不保證 data 先於 metadata 落盤**(B13-05)。
4. `del` / `robocopy` 整個 `data/1k` 的時間遠超過同等位元組的單一大檔。

**行動(不改 code)**:
- 把 `C:\side-project\copycat\data`、`logs`、`.venv`、`__pycache__` 加進 Defender
  ExclusionPath,並把 `python.exe` 加進 ExclusionProcess。**需要 admin,是 ops 動作不是 code 動作。**
- 量測驗證:排除前後各跑一次 `bench_dataio.py`,比 `atomic_write_text` 那一行。
- 若排除後 atomic write 仍 > 0.4 ms,那就是 NTFS 本身,B13-02 的「收成單一 sqlite 檔」
  是唯一解。

---

### B13-15 `breadth_engine._save` 在 event loop 上同步寫檔(每 10 s)· **low–medium**

見 §2 HP-1。修法一行:`await asyncio.to_thread(self._save)` —— 但 `_save` 目前在同步的
`_apply` → `_append` 鏈內,要把 `_append` 改 async 或把 `_save` 提到 `_run_cycle` 層級
`await asyncio.to_thread(...)`。

**誠實評估**:單次 ~1 ms、10 s 一次,占 loop 時間 0.01%。**這條不是效能問題,是紀律問題**
—— 它是盤中 loop 上唯一的週期性同步檔案寫,而磁碟一旦變慢(Defender 全盤掃描、
備份軟體)它就會變成不可預期的 loop 停頓,而**沒有任何訊號**告訴你是它。
若要改,順手做;若時間有限,先做 B13-01/02/04。

---

### B13-16 `write_bars` 的遞增檢查用 `zip(bars, bars[1:])` 建了一份切片複本 · **low**

**位置**:`copycat/data/store.py:17`

```python
    if any(b2.m <= b1.m for b1, b2 in zip(bars, bars[1:])):
```

`bars[1:]` 對 270 個元素建新 list。21,254 次匯入 → 21,254 次 269 元素的 list 配置。
量級 ~0.5 s 總計。改 `itertools.pairwise(bars)`(stdlib,Python 3.10+)零配置。
**S,順手改,但不值得單獨開一個 commit。**

---

## 4. 「沒有 DB」這個決定的代價與引入門檻(任務問題 6)

CLAUDE.md §5 寫「沒有 DB:state = React client + filesystem JSON cache(atomic write +
`_CACHE_VERSION`);ZMQ tick 流 in-memory 不持久化」。

### 4.1 這個決定買到了什麼(誠實)

- `dependencies = []` —— 部署只要一個 Python,沒有 server process、沒有 schema migration、
  沒有「DB 沒起來」這種故障模式。對一個單機看盤工具,這是**對的取捨**。
- 資料可以用 `cat` / `grep` 直接看。CLAUDE.md 全篇的驗證判準大量依賴
  `grep '"kind": "policy"' data/signals/<YYYYMMDD>.jsonl` 這類指令 —— 換成 DB 這些判準全要重寫。
- 檔案就是備份單位;`git`/`robocopy` 可以直接處理。

### 4.2 代價(量化)

| 代價 | 實測 / 估算 |
|---|---|
| 隨機存取慢 27 倍 | `read_bars` 0.818 ms vs sqlite blob 0.030 ms |
| 沒有索引 → 「有哪些 stock-day」只能 `os.walk` | 164 ms / 21,254 檔;或反查 events.csv |
| 沒有 range query → 要一段區間就得全載 | `DailyIndex.load` 4.2 s 才能問一個 20 日窗 |
| 沒有 partial update → 加一天要重寫整檔 | B13-01:615 s / 12 GB |
| 沒有 join → 分點 × 日線 × 事件靠三份記憶體索引 | `fade_pipeline.py` 同時持有 DailyIndex + DayTradeIndex + 逐檔 bars |
| 空間膨脹 | brokers 411 MB(broker 中文名重複存 480 萬次);1K 256 MB |
| 沒有 crash consistency | B13-05:無 fsync |
| 檔數 = 32,265 | NTFS MFT / Defender / 備份成本由檔數驅動 |

### 4.3 具體引入門檻(建議把這幾條寫進 ADR)

**立刻該做(現在就已經越線)**:
1. **1K bar store → sqlite3**(B13-02)。門檻:**stock-day 檔數 > 10,000**。現況 21,254,
   已經是門檻的 2 倍。sqlite3 是 stdlib,`dependencies = []` 不破。
2. **brokers store → sqlite3**(B13-08)。門檻:**單一目錄群 > 300 MB 且需要 top-N 查詢**。
   現況 411 MB。

**加 tick 錄製時必做**:
3. **tick 持久化**(B13-04)一開始就用 sqlite3(WAL + 批次 commit)或定長二進位 append。
   門檻:**寫入頻率 > 1 次/秒**。JSON per-file 在這個頻率下完全不可行。

**目前還不必**:
4. `prices.csv` 可以先用 B13-01 的 B 案(每 N 天 flush)撐著。門檻:
   **當 `DailyIndex.load` 的 4.2 s 開始出現在 server 啟動路徑上**(現在不在),
   或**列數 > 500 萬**(現在 101 萬)。
5. **DuckDB**:門檻是「需要跨 stock-day 的分析型聚合(GROUP BY / window function)且
   資料量 > 10 GB」。現況 730 MB,`backtest/` 的聚合全是 Python 手刻小迴圈。
   **現在引入 DuckDB 是過度工程** —— 它會帶進一個 ~30 MB 的原生相依,而 sqlite3
   在這個資料量上已經足夠(實測全表掃 300 天 4.9 ms)。
6. **parquet / pyarrow**:門檻是「要把資料交給別的工具鏈(pandas/polars/spark)」或
   「單表 > 50 GB 需要壓縮 + predicate pushdown」。目前沒有外部消費者。
   **不建議。**

**絕不要引入**:PostgreSQL / MySQL / Redis —— 單機單使用者、資料量 < 1 GB、沒有並發寫者,
引入一個要維運的 server process 純粹是負債。

---

## 5. 工具選型建議與取捨

| 工具 | 用在哪 | 解決什麼 | 代價 | 結論 |
|---|---|---|---|---|
| **`sqlite3`**(stdlib) | `data/store.py` 1K bar、`backfill_brokers` 分點、(選配)`daily/prices` | 27–50× 隨機存取、檔數 32,265 → 2、range query、crash consistency(WAL) | 零相依;要寫一次性遷移 + 雙讀期;`grep` 式驗證判準要改成 `sqlite3 ... "SELECT"` | **建議導入** |
| **`array` / `struct` / `memoryview`**(stdlib) | `store.py` blob 打包、`daily.py` 欄式儲存、tick recorder | 去掉 per-bar dataclass 建構(實測佔 read_bars 的 38%);記憶體降 5× | 可讀性下降;需要 accessor 包一層 | **建議導入**(與 sqlite3 搭配) |
| **`itertools.pairwise`**(stdlib) | `store.py:17` | 去掉切片複本 | 無 | **建議導入**(順手) |
| **`os.fsync`**(stdlib) | `fileio.py` | crash consistency | 每次 +0.5–5 ms;`_append_jsonl` 不可加 | **建議導入**(除 append 路徑) |
| **`orjson` / `msgspec`** | 若堅持留 JSON | `json.loads` 約 3–5× | 破 `dependencies = []`;Windows wheel 要對 Python 3.13;而 **B13-02 之後 JSON 解析根本不在路徑上了** | **不建議** —— 被 sqlite3 完全取代 |
| **`pyarrow` / parquet** | 1K bar / daily | 欄式壓縮、跨檔 pushdown | ~50 MB wheel + numpy;存取樣態(一次一個 stock-day)用不上 | **不建議** |
| **`duckdb`** | backtest 聚合 | SQL 分析、向量化 | ~30 MB 原生相依;資料量差兩個數量級 | **不建議(現階段)**;門檻見 §4.3.5 |
| **`polars` / `pandas`** | `DailyIndex` / backtest | `read_csv` 快 10×+、向量化特徵 | 大相依;`DailyIndex` 的 18 個方法全要重寫;`copycat validate` golden 要重跑確認逐字相同 | **有條件導入** —— 只在「決定把 `backtest/` 整個改寫成向量化」時才划算,不要為了省 `DailyIndex.load` 的 4 s 而引入 |
| **`aiofiles`** | 任何 | 讓檔案 IO 變 await | 本區塊已經用 `asyncio.to_thread` 解決同一件事,且 aiofiles 內部也是執行緒池 | **不建議** |
| **`filelock`** | `fileio.py` | 跨 process 互斥 | 相依 + Windows 上的鎖語意 | **不建議** —— 單 process,B13-07 的 pid 命名就夠 |
| **`watchdog`** | config 熱重載 | — | 沒有這個需求 | **不建議** |

---

## 6. 不要動的地方

1. **`configio.py` 整個檔案**(32 行)。5 個 caller 全在啟動期,各跑一次,檔案都是幾 KB。
   它現在做的事(unknown-key 檢查 + tuple 轉換)是**正確性**基建不是效能基建。
   引入 pydantic / msgspec 來取代它是純負債。
2. **`cli.py` 的 if-chain + lazy import**(B13-12)。土但正確。
3. **`models.py`**(54 行)。`Bar1K` 已經是 `frozen=True, slots=True`;
   `taipei_min` / `fmt_min` 是純算術。唯一能再快的是不建 dataclass 而用 tuple/array,
   那屬於 B13-02 的範圍,不是這個檔的問題。
4. **`_append_jsonl`**(0.167 ms × 686/日)與 **`_Tee` 的 per-write flush**(4.1 µs)。
   兩者都是「為了可觀測性付的極小代價」,而可觀測性在下實單的系統裡比這 0.1 秒值錢。
   **不要為了效能拿掉 flush。**
5. **`scan_events.py` / `label_events.py` 的 CSV 全表讀寫模式**(B13-13)。
   檔案 0.49 MB、每次跑一次。
6. **`read_signals` 的 `errors="replace"` 與壞行跳過**(`signal_hub.py:1448-1481`)。
   docstring 已經記錄了兩次 review 的教訓,任何「優化」都會退回那些 bug。
7. **atomic write 這個模式本身**。在 `backfill_tc4`(逐筆網路回補)、`signal_hub` 回填
   (整日訊號真相源)、`stock_watchlist`(訂閱池來源)這三處,原子性是必要的,
   0.3 ms 的代價微不足道。只有 `import_neigui` 的批次路徑是浪費(B13-10)。

---

## 7. 跨檔契約影響盤點(改造時的硬約束)

本區塊的改動若照上面的建議走,**只有一條**會碰到 CLAUDE.md §4 的跨檔契約:

| 契約 | 是否受影響 | 說明 |
|---|---|---|
| **T+1 / T+2 回填原地補欄 + 離線讀者契約**(2026-09-07) | **會** | B13-05 加 fsync 時,若把 `atomic_write_text` 從 `Path.write_text`(有 newline 翻譯)改成 binary 寫,行尾會變。該契約要求「只重寫被補的列、其餘列原文逐字保留、行尾原樣」,並由 `tests/server/test_signal_outcome.py` **byte 比對**釘住。→ 必須保留 `open("w", encoding="utf-8")` 的 newline 語意,只加 flush+fsync。`atomic_write_bytes`(signal_hub 回填實際走的那支)本來就零翻譯,加 fsync 無風險。 |
| 自選上限常數多邊同值(150) | 否 | B13 不碰 `WATCHLIST_LIMIT`。 |
| 「盤前篩選」群組名前後端同字面 | 否 | `cli.py:365` 只是 import `SCREEN_GROUP`,不產生也不鏡像。 |
| `OrderRecord.unit` 字面值 | 否 | `capital/store.py` 是記憶體態,不在本區塊。 |
| 訊號列 `notify` 欄 / 政策列形狀 / 訊號規則參數 parity | 否 | jsonl 的**內容** schema 不變,只改寫入原語。 |
| WS 心跳 / `handover.attempt` / `tape=0` / `seq` 口徑 | 否 | 純 wire,與磁碟無關。 |
| 關機預算三方同源 | **間接** | 若 B13-04 加 tick recorder,它的 flush 執行緒要納入 `shutdown_budget.py` 的可計段,或明確標為「不計段、以 daemon thread 丟棄未 flush 資料」。**新增 lane = 改契約**,要同步改 `TC4_LANE_DEPTH` 或在 `run_grace_secs()` 加項。 |
| 日 K 定稿界 14:00 前後端同值 | 否 | `bars.py` 不在本區塊。 |
| 江波圖調色盤 / sparse 腿 / heal gate | 否 | 無關。 |

**另外兩條非 CLAUDE.md 但實際存在的約束**:

- **`copycat validate` golden gate**:`replay` 產物逐字比對 evidence golden。
  B13-02 / B13-03 改的是 `read_bars` / `DailyIndex` 的**實作**,產物必須逐字相同 ——
  這也正是最好的驗證手段(改完跑 `validate`,綠就是沒改壞語意)。
  但注意 **float 往返**:JSON 的 `4.4` 與 sqlite REAL 的 `4.4` 應該同為 IEEE754 雙精度,
  若改成 int32 scaled 就會有捨入 —— 必須先確認 1K 的 open/high/low/close 全部落在
  `market.py` 的毫元格點上(有 `tests/test_market.py` 可查),不然不能 scaled。
- **CLAUDE.md §1 的 grep 式驗證判準**:
  `grep '"kind": "policy"' data/signals/<YYYYMMDD>.jsonl`、
  `grep 佇列滿 logs/server-*.log`、`grep "墊背舊快照"` 等。
  **訊號 jsonl 與 log 絕對不可以改成二進位 / DB** —— 那會讓整套驗收判準失效。
  B13 的所有建議都刻意繞開這兩份。

---

## 8. 量測方法(要證明這個區塊快或慢,怎麼量)

### 8.1 已建好的基準腳本(可重跑)

```powershell
$env:PYTHONUTF8=1
& C:\side-project\copycat\.venv\Scripts\python.exe <scratchpad>\bench_dataio.py     # json/atomic/1k/csv/DailyIndex
& C:\side-project\copycat\.venv\Scripts\python.exe <scratchpad>\bench_runtime_io.py # signals jsonl/flush/walk/exists
& C:\side-project\copycat\.venv\Scripts\python.exe <scratchpad>\bench_sqlite.py     # JSON vs sqlite3 對照
& C:\side-project\copycat\.venv\Scripts\python.exe <scratchpad>\bench_daily.py      # DailyIndex 三變體
& C:\side-project\copycat\.venv\Scripts\python.exe <scratchpad>\bench_brokers.py    # read_brokers
& C:\side-project\copycat\.venv\Scripts\python.exe <scratchpad>\bench_csvwrite.py   # B13-01 的 615 s 證據
```

### 8.2 本次基準值(2026-09-13,Defender 開啟)

```
json.dumps 270-bar          : 0.371 ms      json.loads 270-bar : 0.191 ms
atomic_write_text 12KB      : 0.540 ms      plain write_text   : 0.230 ms
open-append-close           : 0.167 ms      write+flush        : 4.1 us/line
read_bars (JSON)            : 0.818 ms/day  sqlite blob        : 0.030 ms/day  (27x)
read_brokers (32KB)         : 5.754 ms/file
read_signals (289KB/686列)  : 5.77 ms
atomic_write_bytes 289KB    : 0.68 ms
DailyIndex.load             : 4,201 ms      csv.reader 變體 1,937 / sqlite 1,408
prices.csv 全份重寫          : 2,672 ms      → 230 天迴圈 615 s / 12 GB
os.walk data/1k (21,254)    : 164 ms        Path.exists : 11.5 us
```

### 8.3 改造後要重量的項目與判準

| 改動 | 判準 |
|---|---|
| B13-01 | 重跑 `bench_csvwrite.py` 邏輯改寫後版本;`backfill-daily --start X --end Y` 的 wall clock 應趨近 `0.7 s × 天數`(網路下限) |
| B13-02 | `bench_sqlite.py` 的 `read_bars` 那行改打新實作,目標 < 0.05 ms/day;**且 `python -m copycat validate` 必須全 PASS** |
| B13-03 | `bench_daily.py::current` 目標 < 2,000 ms;**且 `copycat validate` 全 PASS** |
| B13-04 | 新增:tick recorder 的 `dropped` 計數盤後必須為 0(仿 `ws.py::WsBroadcaster.dropped` 的 60 s 節流 WARNING);tick 回呼的 p99 延遲不得因 recorder 上升(在 `tc4.py` 回呼入口加 `perf_counter` 直方圖) |
| B13-05 | `tests/server/test_signal_outcome.py` 的 byte 比對必須綠;`bench_dataio.py` 的 atomic_write_text 允許升到 ~2 ms |
| B13-14 | Defender 排除前後各跑一次 `bench_dataio.py`,比 `atomic_write_text` 與 `read_bars` 兩行 |

### 8.4 還缺的探針(目前量不到)

- **loop 停頓分佈**:`asyncio` 的 `loop.slow_callback_duration` + `set_debug(True)`
  只在 debug mode 有;更好的做法是掛一個每 100 ms 的 `call_later` 心跳,記錄
  實際觸發時刻與預期時刻的差,寫進 `/api/health`。有了它才能證明 B13-15 是不是問題。
- **`to_thread` 預設 executor 的排隊深度**:`asyncio.get_running_loop()._default_executor._work_queue.qsize()`
  是私有 API,但可以在 `/api/health` 曝一個近似值。這是 HP-4(下單審計)真正的風險來源,
  目前**完全沒有可觀測性**。
- **prod 的 tick 到達率**:`tc4.py` 收到的 tick 數 / 秒,目前只有丟包計數沒有吞吐計數。
  沒有這個數字就無法為 B13-04 的 recorder 定 buffer 大小。

---

## 9. Open questions(需要 user 拍板或需要跑 profile 才知道)

1. **要不要錄 tick?**(B13-04)這是方向性抉擇不是技術問題。錄了才有微結構回測,
   但也就多了一條盤中寫磁碟的路。CLAUDE.md §5 的「不持久化」是明文決定,要推翻需要 user 拍板。
2. **`data/1k` 的價格是否全部落在毫元格點上?** 決定 B13-02 能不能用 int32 scaled
   (省 45% 空間)還是必須用 float64。要對 21,254 個檔跑一次 `all(round(p*1000) == p*1000)` 掃描。
3. **`copycat validate` 需要先跑過 four/five 兩份 replay 才能驗**(CLAUDE.md §1)——
   本次分析沒有跑(會寫 `out/`,超出唯讀範圍)。B13-02/03 落地前必須先建立 baseline。
4. **Defender 排除清單目前是什麼?** 需要 admin 權限查。若 `data/` 已經排除,
   B13-14 的建議就沒有增量收益,而本次量到的 0.54 ms 就是 NTFS 的裸成本。
5. **`backtest/` 會不會整個改寫成向量化?** 若會,B13-03 的最佳解從「csv.reader 變體」
   變成「polars/numpy」,兩者的投入差一個數量級。這決定了 §5 表格中 polars 那一列的結論。
6. **`stock_names.py` 的 `_CACHE_VERSION` 只寫不讀是刻意的嗎?**(B13-11)
   看起來是漏了讀取側比對,但也可能是「names 表沒有向後不相容的可能」的判斷。
7. **prod server 的實際磁碟是 SSD 還是 HDD?** 本次量測在開發機。若 prod 同機則數字可用。
