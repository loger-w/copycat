# T3-bench-storage —— 資料儲存與載入實測擂台

日期 2026-09-13 · 環境 Windows 11 Home 26200 / Python 3.13.13 / 拋棄式 venv
`scratchpad/venvs/T3`(**專案 `.venv` 零接觸,repo 零改動**)

所有數字皆為**實測**;推估值一律標「推估」。

---

## 0. Setup(可重現)

```powershell
py -3.13 -m venv <scratch>\venvs\T3
<scratch>\venvs\T3\Scripts\python.exe -m pip install pyarrow polars duckdb numpy orjson
```

| 套件 | 版本 | wheel 大小 | Windows py3.13 安裝狀況 |
|---|---|---|---|
| pyarrow | 25.0.1 | 27.9 MB | 純 wheel,無編譯 |
| polars | 1.44.2 | 0.87 MB + `polars-runtime-32` 51.3 MB | 1.4x 起 runtime 拆成獨立套件,**兩個都要裝** |
| duckdb | 1.5.5 | 13.2 MB | 純 wheel |
| numpy | 2.5.3 | — | 純 wheel |
| orjson | 3.12.0 | — | 純 wheel |

venv 落地總大小 **361.5 MB**(對照:現況後端 runtime `dependencies = []`)。
安裝全程無 MSVC / 無 conda / 無 pre-built 缺料,**Windows 上五個套件零障礙**。

### Benchmark 腳本(全在 `scratchpad/verify-bakeoff/`)

| 腳本 | 內容 | 原始輸出 |
|---|---|---|
| `t3_common.py` | 共用 helper;repo 現況 code 逐字複製(不 import repo,避免產生 `__pycache__`) | — |
| `b1_baseline.py` | 現況 1K 全量載入拆解(IO / parse / 建物件) | `out-b1.txt` |
| `b2_convert.py` | 21,254 JSON → 7 種候選格式 + 磁碟佔用 | `out-b2.txt` |
| `b3_read.py` | 全量載入 13 路 + 單檔隨機讀 12 路 + 記憶體 | `out-b3.txt` |
| `b4_csv_jsonl_range.py` | prices.csv / 區間查詢 / signals+audit jsonl | `out-b4.txt` |
| `b5_ticks_atomic.py` | tick 持久化 11 路 + 原子寫入 | `out-b5.txt` |
| `b6_tail.py` | tick 寫入尾端穩定性覆核(兩輪) | `out-b6.txt` |
| `b7_stdlib_only.py` | 零新相依能拿到多少 | `out-b7.txt` |

### 真實輸入(先自行清點,非沿用上一輪說法)

| 資料 | 實測 |
|---|---|
| `data/1k/**/*.json` | **21,254 檔 / 256,701,357 B (244.8 MB) / 5,689,980 bars / 1,715 檔股票** |
| 每股日數 | median **9**、max 67;≥20 日只有 380 檔、≥30 日只有 168 檔(= 五虎事件種子集,不是完整歷史) |
| 每檔 bar 數 | 平均 268(= 09:01–13:30 全場) |
| `data/daily/prices.csv` | 52,059,407 B (49.6 MB) / **1,013,469 列** |
| `data/signals/*.jsonl` | 26 檔 / 3.0 MB / **8,789 列** |
| `data/audit/capital-*.jsonl` | 22 檔 / 0.3 MB / **1,075 列** |
| `data/brokers/` | 11,011 檔 / 392.6 MB(本輪未量,非任務範圍) |

---

## 1. 對決一:1K bar 載入

### 1.1 先拆帳:55% 在建物件這件事成立嗎?→ **成立(實測 53.5%)**

`b1_baseline.py`,同一批 21,254 檔、page cache 全暖、取 3 次最佳:

| 段 | 耗時 | 佔比 |
|---|---|---|
| `read_bytes` 光讀(IO 地板) | **1.013 s** | 9.7% |
| `read_text` + utf-8 decode | 1.227 s | 11.8% |
| `json.loads` 到 `list[list]` | **4.841 s** | 46.5% |
| **現況 `read_bars`(json + Bar1K)** | **10.415 s** | 100% |
| → 其中 `Bar1K` 建構 | **5.574 s** | **53.5%** |

**因此(Amdahl,算術推論非量測):**
- **只換格式、還是回傳 `list[Bar1K]` → 速度上限 1.87x。**
- 連物件一起丟(回 array / Table)→ 上限 **10.28x**(= IO 地板)。

旁證:`orjson` 把 parse 從 4.841 s 壓到 2.029 s(2.4x),但全鏈只從 10.415 s → 7.344 s(**1.42x**),
剩下的錢全被 `Bar1K` 收走。`Bar1K(*r)` 免掉逐欄索引再省到 6.200 s(1.68x)——**仍然撞在 1.87x 的天花板下**。

> 量測侷限:上一輪報的「全掃 18 秒」本輪重現不到,三支腳本的現況基線分別是
> **10.415 s / 12.299 s / 14.162 s**(機器負載漂移 ±35%)。**所有倍數一律在同一次執行內比,
> 不跨腳本比絕對秒數。**

### 1.2 全量載入對決(`b3_read.py`,同一次執行,基線 12.299 s)

| 方案 | 全量載入 | vs 現況 |
|---|---|---|
| 現況 JSON + `Bar1K` | 12.299 s | 1.00x |
| **P1 per-file parquet → arrow** | **14.507 s** | **0.85x(更慢)** |
| **P1 per-file parquet → `Bar1K`** | **21.217 s** | **0.58x(更慢)** |
| S1 sqlite(每 bar 一列)全掃 | 7.736 s | 1.59x |
| B1 per-file 自訂二進位 → `Bar1K` | 8.814 s | 1.40x |
| B1 per-file 自訂二進位 → numpy | 1.953 s | 6.30x |
| P2 per-stock parquet → arrow | 1.419 s | 8.67x |
| S2 sqlite blob-per-file → numpy | 0.503 s | 24.5x |
| **B2 整併二進位 → numpy** | **0.228 s** | **54.0x** |
| **P3 單一 parquet → arrow** | **0.070 s** | **176.9x** |
| **P3 單一 parquet → polars** | **0.029 s** | **429x** |
| P3 duckdb `count(*)` | 0.012 s | 1014x |
| P3 polars lazy `count` | 0.001 s | 22193x(只讀 metadata,不是同一件事) |

### 1.3 單檔隨機讀(1,000 次隨機 `(stock_id, date)`,`b3_read.py`)

| 方案 | p50 | p99 | max |
|---|---|---|---|
| 現況 JSON + `Bar1K` | **686.2 us** | 735.7 us | 835.6 us |
| P1 per-file parquet → arrow | 708.5 us | 905.0 us | 997.8 us |
| P1 per-file parquet → `Bar1K` | 1,001.5 us | 1,258.9 us | 2,919.3 us |
| P2 per-stock parquet(`filters=`) | 1,204.8 us | 1,590.4 us | 2,435.8 us |
| S1 sqlite 索引 → tuple | 403.0 us | 444.2 us | 568.8 us |
| S1 sqlite 索引 → `Bar1K` | 728.9 us | 781.6 us | 963.9 us |
| S2 sqlite blob → numpy | 211.7 us | 264.3 us | 500.9 us |
| B1 per-file bin → `Bar1K` | 478.7 us | 590.5 us | 943.0 us |
| B1 per-file bin → numpy | 86.3 us | 152.6 us | 262.5 us |
| **B2 整併 bin → numpy** | **19.4 us** | **40.3 us** | 60.9 us |
| duckdb on parquet(檔) | **5,869.4 us** | 8,601.4 us | 9,146.1 us |
| duckdb in-memory table | **2,108.5 us** | 2,751.2 us | 2,869.9 us |

### 1.4 磁碟佔用(`b2_convert.py`)

| 格式 | 磁碟 | vs JSON | 轉檔一次性 |
|---|---|---|---|
| JSON(現況)21,254 檔 | 244.8 MB | 1.00x | — |
| P1 per-file parquet(21,254 檔) | **110.8 MB** | 2.21x | 24.77 s |
| P2 per-stock parquet(1,715 檔) | 37.1 MB | 6.60x | 5.82 s |
| **P3 單一 parquet(zstd)** | **29.9 MB** | **8.20x** | 5.20 s |
| S1 sqlite 每 bar 一列 + index | **463.8 MB** | **0.53x(更大)** | 8.78 s |
| S2 sqlite blob-per-file | 423.3 MB | 0.58x | 4.04 s |
| B1 per-file 自訂二進位 | 358.3 MB | 0.68x | 10.45 s |
| B2 整併二進位 + index | 359.1 MB | 0.68x | **2.40 s** |

### 1.5 記憶體(全量常駐)

| 表示法 | 常駐 | 每根 bar |
|---|---|---|
| **現況 `list[Bar1K]`** | **1,665.9 MB** | 307.0 B(`sys.getsizeof(Bar1K)` 本體 104 B,其餘是 list + float 物件) |
| arrow Table(含 stock_id/date 字串欄) | 482.9 MB | 89 B |
| arrow Table(只留 9 個數值欄) | 363.6 MB | 67 B |
| polars DataFrame | 434.1 MB | 80 B |
| numpy (N,8) float64 | 347.3 MB | 64 B |
| numpy (N,8) float32 | **173.6 MB** | 32 B |

**結論:`Bar1K` 讓同一份資料脹了 9.6x 記憶體。**

### 1.6 零新相依能拿到多少(`b7_stdlib_only.py`,同一次執行,基線 14.162 s)

| 方案 | 全量 | vs 現況 | 需要新套件? |
|---|---|---|---|
| 現況 `read_text` + json + `Bar1K` | 14.162 s | 1.00x | — |
| `read_bytes` + json + `Bar1K`(改一行) | 14.014 s | 1.01x | 否 |
| json → `list[list]`(不建物件) | 6.422 s | 2.21x | 否 |
| 自訂 bin + `array.array`(per-file) | 1.641 s | 8.63x | 否 |
| **自訂 bin + `array.array`(整併檔)** | **0.195 s** | **72.6x** | **否** |

**最重要的一格:`array.array`(stdlib)整併檔 0.195 s,與 numpy 版 0.228 s 同一檔次。
整併 + 不建物件這兩件事貢獻了幾乎全部收益,第三方套件貢獻 ≈ 0。**

---

## 2. 對決二:tick 持久化(現況完全沒有)

輸入:依任務給的形狀合成一日 tick 流 —— **150 檔 × median 2,247 筆 = 351,430 筆**,
欄位照 `copycat/live/stock_models.py::StockTick`(code / price_milli / qty / cum_vol /
time / trade_date / side / is_trial / bid_milli / ask_milli),打亂成交錯到達序。

### 2.1 盤中寫入延遲(每筆,含序列化;`b5_ticks_atomic.py`)

| 方案 | p50 | **p99** | max | 全日總寫入 | 日終檔案 |
|---|---|---|---|---|---|
| jsonl `json.dumps` buffered 64 KB | 2.90 us | 5.1 us | 9.75 ms | 1.07 s | 67.0 MB |
| **jsonl `orjson` buffered 64 KB** | **0.50 us** | **1.0 us** | 8.92 ms | 0.22 s | 60.3 MB |
| jsonl `orjson` 無緩衝(每筆 write) | 2.40 us | 4.7 us | 0.10 ms | 0.98 s | 60.3 MB |
| **jsonl 每筆 flush + `fsync`** | **365.50 us** | **2,049.7 us** | 11.65 ms | **345.21 s** | 60.3 MB |
| parquet 批寫(每 5,000 筆) | 0.10 us | 0.3 us | **28.94 ms** | 0.92 s | 8.5 MB |
| parquet 批寫(每 50,000 筆) | 0.10 us | 0.3 us | **200.38 ms** | 1.41 s | **7.8 MB** |
| sqlite WAL `sync=NORMAL`(單一 tx) | 3.00 us | 7.0 us | 6.83 ms | 1.12 s | 12.1 MB |
| sqlite WAL `sync=OFF`(單一 tx) | 3.00 us | 6.8 us | 7.44 ms | 1.11 s | 12.1 MB |
| sqlite WAL `sync=FULL`(單一 tx) | 3.10 us | 6.6 us | 0.30 ms | 1.12 s | 12.1 MB |
| sqlite WAL(**每筆 commit**) | 14.60 us | 25.9 us | 10.88 ms | 6.27 s | 12.1 MB |
| 自訂 binary append buffered 64 KB | 1.90 us | 2.7 us | 0.12 ms | 0.69 s | 12.1 MB |

### 2.2 尾端穩定性覆核(`b6_tail.py`,預先序列化、跑兩輪、351,430 次)

上表的 8–10 ms max 是不是常態?**不是,是暖機。**

| 方案 | p50 | p99 | **p999** | max | >100 us 次數 | >1 ms 次數 |
|---|---|---|---|---|---|---|
| jsonl buffered 64 KB(第 1 / 2 輪) | 0.10 / 0.10 us | 0.20 / 0.10 us | 15.80 / 14.60 us | **0.107 / 0.088 ms** | 1 / 0 | 0 / 0 |
| jsonl buffered 1 MB | 0.10 us | 0.10–0.20 us | 0.20 us | 0.436 / 0.668 ms | 61 / 61 | 0 / 0 |
| jsonl 無緩衝 | 1.60 us | 2.80 us | 14.40 / 13.80 us | 0.187 / 8.877 ms | 1 / 6 | 0 / 2 |
| **binary 36 B buffered 64 KB** | **0.10 us** | **0.10 us** | **0.20 us** | **0.086 / 0.082 ms** | **0 / 0** | **0 / 0** |
| binary 無緩衝 | 1.60 / 2.50 us | 2.50 / 3.50 us | 7.10 / 9.50 us | 8.838 ms(**兩輪都在 i=20**) | 3 | 2 |
| jsonl buffered + 每 5,000 筆 fsync | 0.10 / 0.20 us | 0.20 / 0.30 us | 21.4 / 25.8 us | 1.222 / 0.984 ms | 70 / 75 | 1 / 0 |

**判準結論:64 KB buffered append 的穩態最壞單筆 = 0.11 ms,>1 ms 出現 0 次。
tick 持久化不會卡 event loop —— 只要 (a) 用緩衝、(b) 不逐筆 fsync、(c) parquet writer 不在 loop 上。**

### 2.3 隔日讀回(全日 351,430 筆)

| 方案 | 讀回 |
|---|---|
| jsonl + `json.loads`(現況風格) | **1,045.8 ms** |
| jsonl + `orjson.loads` | 318.2 ms |
| sqlite 全掃 → tuple | 353.6 ms |
| sqlite 兩欄 `fetchall` | 168.8 ms |
| **parquet → arrow** | **5.0 ms** |
| **binary → numpy structured** | **3.4 ms** |

### 2.4 年度磁碟(240 交易日,由日終實測×240 **推估**)

| 方案 | 每日 | 每年(推估) |
|---|---|---|
| jsonl(orjson) | 60.3 MB | **14.5 GB** |
| sqlite WAL | 12.1 MB | 2.9 GB |
| 自訂 binary 36 B/筆 | 12.1 MB | 2.9 GB |
| **parquet zstd** | **7.8 MB** | **1.9 GB** |

---

## 3. 對決三:回測用的查詢(只量「資料載入」那一段)

**先確認任務前提:上一輪說搜索已是 Python int bitmask 走 C 層 —— 本輪照指示不碰搜索邏輯,
只量「取某檔某區間的 1K bar」。**

輸入:200 組 `(stock_id, 連續 15 個交易日)`,候選 548 檔(該資料集 ≥30 日者只有 168 檔,
不足以取 200 組,故窗改 15 日;`b4_csv_jsonl_range.py`)。

| 方案 | p50 | p99 | 200 組總計 |
|---|---|---|---|
| 現況 目錄掃描 + `json.loads` | 5.666 ms | 6.652 ms | 1.14 s |
| 現況 預建索引 + `json.loads` | 5.337 ms | 5.836 ms | 1.20 s |
| **duckdb on parquet(檔)** | **7.026 ms** | 9.649 ms | 1.43 s |
| duckdb in-memory table(+ index) | 2.686 ms | 3.444 ms | 0.54 s |
| pyarrow P2 per-stock `filters=` | 1.626 ms | 2.296 ms | 0.33 s |
| **polars `scan_parquet` P2 per-stock** | **0.810 ms** | **1.244 ms** | **0.17 s** |

**duckdb 在這個形狀上輸給目錄掃描(0.81x)。** 上一輪的預判成立,而且理由比預期更基本:
duckdb 每次查詢都要重開 parquet footer + 規劃 + 執行,固定開銷 ~7 ms,
而要取的資料只有 ~4,000 列。整份載進 in-memory table 後降到 2.7 ms,仍輸給 polars 的 0.81 ms。

---

## 4. 對決四:原子寫入(`copycat/fileio.py`)

`b5_ticks_atomic.py`,每組 n=300,用**真實 payload**:

| Payload | 方案 | p50 | p99 | max |
|---|---|---|---|---|
| 1K bar 檔 12,803 B | 直接 `write_text`(非原子) | 0.211 ms | 0.269 ms | 0.282 ms |
| | **現況 `atomic_write_text`(tmp + `os.replace`)** | **0.520 ms** | **0.625 ms** | 0.664 ms |
| | atomic + `fsync` | 0.900 ms | 1.078 ms | 1.873 ms |
| `stock_watchlist.json` 2,559 B | 直接 `write_text` | 0.221 ms | 0.363 ms | 1.563 ms |
| | **現況 `atomic_write_text`** | **0.525 ms** | **0.658 ms** | 0.702 ms |
| | atomic + `fsync` | 0.896 ms | 1.069 ms | 1.107 ms |
| signals 日檔 288,403 B | 直接 `write_text` | 0.611 ms | 0.744 ms | 1.253 ms |
| | **現況 `atomic_write_text`** | **0.943 ms** | **1.138 ms** | 1.475 ms |
| | atomic + `fsync` | 1.410 ms | 1.609 ms | 1.855 ms |

**讀法:**
- 原子性(tmp + rename)的價碼 = **+0.31 ms**(小檔)/ +0.33 ms(288 KB)。與檔案大小幾乎無關,
  是「多開一個檔 + rename 兩個 syscall」的固定費。
- **`fsync` 再加 +0.38 ms(小檔)~ +0.47 ms(288 KB),p99 推到 1.1–1.6 ms。**
  換到的是耐斷電;現況不做,是對的取捨(本機看盤,不是交易所撮合)。
- 現況三處呼叫點的執行緒位置(grep 實查):
  - `server/signal_hub.py:1381` 已經是 `await asyncio.to_thread(atomic_write_bytes, ...)` ✅
  - `server/screen_engine.py:445` 與 `stock_watchlist.py:172`(經 `watchlist_service._save_locked`,
    在 async 方法內同步呼叫)**在 event loop 上跑 0.52 ms**。頻率低(排程 / PUT),不是熱點,
    但這是 loop 上唯一還在的同步檔案寫。

---

## 5. 附帶對決:prices.csv 與 jsonl(順手量到,對回測與訊號鏈有用)

### 5.1 `prices.csv`(49.6 MB / 1,013,469 列)→ `copycat/data/daily.py::DailyIndex.load`

| 方案 | 最佳 | vs 現況 | 新相依 |
|---|---|---|---|
| **現況 `csv.DictReader` + `_DayRow` + sort** | **3.935–4.727 s** | 1.00x | — |
| `csv.reader`(位置索引)+ 同樣 `_DayRow` + sort | 2.970 s | **1.54x** | 否 |
| `csv.reader` + 純 tuple + sort | 1.839 s | **2.48x** | 否 |
| `csv.reader` 光掃(不建物件) | 0.590–0.748 s | 6.7x | 否 |
| `csv.DictReader` 光掃 | 1.419–1.880 s | 2.8x | 否 |
| duckdb `read_csv_auto` | 0.090–0.110 s | **~43x** | duckdb |
| pyarrow `csv.read_csv` | 0.031 s | **~140x** | pyarrow |
| **`polars.read_csv`** | **0.021–0.023 s** | **~200x** | polars |
| polars `read_csv` + sort | 0.043 s | ~100x | polars |
| (轉 parquet 13.4 MB 後)`polars.read_parquet` | 0.010 s | ~400x | polars |
| (同上)`pyarrow.read_table` | 0.013–0.014 s | ~330x | pyarrow |

記憶體:現況 `dict[str, list[_DayRow]]` = **281.6 MB**;polars DataFrame = **63.8 MB**(4.4x)。

### 5.2 signals / audit jsonl

| 資料 | `json` 逐行(現況) | `orjson` 逐行 | `polars.read_ndjson` | `duckdb read_json_auto` |
|---|---|---|---|---|
| signals 26 檔 / 3.0 MB / 8,789 列 | 41.7–54.2 ms | **16.7 ms(3.2x)** | **失敗** | 119.6 ms(更慢) |
| audit 22 檔 / 0.3 MB / 1,075 列 | 4.2 ms | **2.6 ms(1.6x)** | 16.9 ms(更慢) | 51.2 ms(更慢) |

`polars.read_ndjson` 對真實 signals 日檔直接拋
`ComputeError: expected null in json value, got object` —— 訊號列的 `levels`(list)與掃單簇列的
`detail`(object)讓 schema 不齊,**欄式讀取器吃不下這份檔**。這正好呼應 CLAUDE.md §4
「離線讀者逐列讀 `s["kind"]`、只加欄不改欄」的契約:那份 jsonl 的形狀本來就是列式的。

`read_bytes` + `splitlines` 取代 `open` 逐行:41.7 → 36.2 ms(1.15x,零相依)。

---

## 6. 違反直覺的量測結果

1. **Per-file parquet 比 JSON 慢**(全量 0.85x,要建物件更慢到 0.58x;單檔隨機讀 708 us vs 686 us)。
   268 列的小檔,parquet 的 footer + schema + zstd frame 固定開銷吃掉全部好處。
   **parquet 的勝利完全來自「整併」,不來自「格式」。**
2. **自訂二進位比 JSON 大 1.46x**(358 MB vs 245 MB)。`24.1` 寫成文字 4 bytes、寫成 float64 是 8 bytes;
   而 `0.0` 這種欄位在 JSON 裡是 3 bytes。想省磁碟要靠**壓縮 + 欄式**,不是靠二進位。
3. **sqlite 每 bar 一列 = 463.8 MB,比 JSON 大 1.9x**(含 index)。
4. **duckdb 的單點查詢是全場最慢的一路**(5,869 us,比 `json.loads` 慢 8.5x);
   區間查詢也輸給目錄掃描(7.03 ms vs 5.67 ms)。duckdb 的固定規劃成本 ~7 ms 在小查詢上是純負擔。
5. **stdlib `array.array` 追平 numpy**(整併檔 0.195 s vs 0.228 s)。這一格的意思是:
   **此處第三方套件的邊際貢獻 ≈ 0,收益全在資料布局。**
6. **`orjson` 把 parse 加速 2.4x,但全鏈只快 1.42x** —— 教科書級的 Amdahl 現場。
7. **parquet incremental writer 的單次 flush 最壞 200 ms**(每 50,000 筆那組)。
   p50 看起來 0.1 us 很美,但那是「大部分呼叫只是 append 到 list」;真正的成本集中在一格,
   **平均值在這裡是騙人的,只有 max 有意義。**
8. **`binary 無緩衝` 的 8.838 ms max 兩輪都落在 i=20** —— 可重現 = 新檔首次實體配置,
   是暖機不是抖動。若不跑兩輪、不看 `max@i`,會誤判成「無緩衝寫入不穩」。
9. **`polars.read_ndjson` 讀不了自家 signals 日檔。**
10. **`Bar1K` 讓 5.69M 根 bar 佔 1.67 GB**(307 B/根)。numpy float32 只要 173.6 MB。

---

## 7. 建議(附成本與阻斷風險)

### R1 ── 1K bar:**有條件導入**,而且導入的是「布局」不是「套件」

- **不要做**:把 `data/1k/**/*.json` 換成 per-file parquet。實測更慢(0.85x / 0.58x),
  磁碟只省 2.21x,還多一個 86 MB 的 pyarrow 相依。**這是最容易做錯的一步。**
- **要做的話**:加一支**整併快取**(單一 parquet 或單一自訂 bin + index),
  `read_bars` **原封不動**,另開 `read_bars_arrays(stock_id, date) -> (m, o, h, l, c, v, uv, dv, nv)`
  回 `array.array` / numpy,只給回測的熱路徑用。
- 收益(實測):全量 72.6x(14.162 → 0.195 s,stdlib `array.array`)、單檔隨機讀 35x(686 → 19.4 us)、
  記憶體 9.6x(1,666 → 174 MB f32)。
- 成本:多一份衍生檔(360 MB bin / 30 MB parquet)、要處理「JSON 是真相源、bin 是快取」的失效;
  **消費端要改成吃 array**,不改就只剩 1.87x 上限。
- **阻斷風險(CLAUDE.md §4)**:`read_bars -> list[Bar1K] | None` 是 `replay/runner`、
  `backtest/pipeline`、`fade_*` 的既有契約,`copycat validate` 的 golden gate 站在它上面。
  **改簽名 = 打契約**;新增姊妹 API 則零風險。

### R2 ── `prices.csv`:**建議導入,但導入的是 `csv.reader`,不是 polars**

- `DictReader → reader` 一處改動拿 **1.54x**;再丟掉 `_DayRow` 拿 **2.48x**;**零新相依**。
- polars 能拿 ~200x(3.9 s → 0.021 s),但 `DailyIndex` 的下游是 `bisect` + 逐筆 `ohlc()` 查詢,
  拿到 DataFrame 之後還是要退回 Python 物件才餵得進去 —— 200x 的載入省下 3.9 s,
  代價是 runtime 從 `dependencies = []` 變成拖一個 60 MB 的 Rust 套件。
- **裁決:先做 `csv.reader`(免費 1.5–2.5x);polars 留給「哪天 `DailyIndex` 整支改成欄式」再談。**
- 阻斷風險:`_DayRow.spread` 有 `None` vs `0.0` 的**刻意語意**(空字串 → None,0.0 是合法平盤值),
  位置索引改寫時 `r.get("spread")` → `r[spi]` 要保住這條;`data/daily/` 下不同來源的 CSV 欄序不保證一致,
  **必須從 header 建索引(如 `b7` 的寫法),不可寫死欄位序號。**

### R3 ── tick 持久化:**建議導入**(這是本區唯一「從無到有」的一格)

- 推薦組合:**盤中 64 KB buffered append(jsonl 或 36 B binary)+ 盤後轉 parquet**。
  - 盤中寫入穩態最壞 **0.11 ms / 筆**,>1 ms 出現 **0 次**(351,430 筆 × 2 輪);全日總寫入 0.22–0.69 s。
  - 日終 60.3 MB(jsonl)/ 12.1 MB(binary);盤後轉 parquet 降到 7.8 MB,隔日讀回 **5.0 ms**。
- **不要做**:(a) 逐筆 `fsync`(p99 2,050 us,全日 345 s,直接殺死 loop);
  (b) 把 `ParquetWriter.write_table` 放在 event loop 上(單次 flush 最壞 **200 ms**);
  (c) 每筆 commit 的 sqlite(14.6 us p50,比 append 慢 7–29x 且沒換到什麼)。
- 成本:年增 1.9–14.5 GB 磁碟(推估);一個新的收盤轉檔工序;
  parquet 那一段需要 pyarrow(86 MB)—— 若要維持 stdlib-only,binary + `array.array` 讀回也只要 3.4 ms。
- 阻斷風險:低(全新路徑,不碰既有契約)。唯一要小心的是**寫入點在 `stock_engine._handle_quote` 的熱路徑上**
  (CLAUDE.md §4「個股逐筆 = `ticks` 打包訊息」那條),多一個 `fh.write` 是 0.1 us 等級,
  但 buffer flush 的 0.09 ms 會落在某一筆 tick 上 —— 與該路徑既有的 0.1 s `call_later` 打包節奏相比可忽略。

### R4 ── duckdb:**不建議**(用在本專案的任何線上路徑)

- 單點 5,869 us、區間 7,026 us,兩項都輸給現況目錄掃描。
- 它唯一合理的位置是**離線臨時研究**(對整併 parquet 下 ad-hoc SQL),
  那屬於 `docs/research/` 的一次性腳本,不該進 `copycat/` runtime。
- 成本:13 MB wheel;收益:線上為負。

### R5 ── polars:**有條件導入**,範圍限定在回測 / 研究

- 唯一實測有壓倒性優勢且形狀對得上的一格:**per-stock parquet 的區間查詢 0.810 ms vs 現況 5.337 ms(6.6x)**,
  以及 `prices.csv` 的 ~200x。兩者都在 `copycat/backtest/` 與 `docs/research/` 這一側。
- **不要進 `copycat/live/` 與 `copycat/server/`**:看盤鏈的資料量是「一檔一天 268 根」,
  polars 的固定開銷在那個尺度上是負收益(參見 per-file parquet 的 0.85x)。
- 成本:`pyproject` 要開一個 `[backtest]` extras(60 MB);
  完工 gate(`pytest` / `pyright`)會開始吃 polars 的 type stub。

### R6 ── 原子寫入:**維持現況,不加 `fsync`**

- 現況 0.52 ms p50 / 0.66 ms p99,對每次 PUT / 每次排程各一發的頻率完全不是問題。
- `fsync` 要 +0.38~0.47 ms 且 p99 破 1 ms,換到的耐斷電在「本機看盤、資料可重抓」的場景下不值。
- **唯一值得動的一行**:`stock_watchlist.py:172`(經 `watchlist_service`)與
  `screen_engine.py:445` 包成 `await asyncio.to_thread(...)`,與 `signal_hub.py:1381` 對齊。
  收益 0.52 ms 的 loop 佔用,**這不是效能優化,是一致性**。

---

## 8. 量測侷限 / 什麼情況下結論會反轉

1. **全部是 warm page cache。** 244.8 MB 在 32 GB 機器上第二次起全在記憶體。
   冷開機第一發會慢,而**冷讀恰好是整併格式贏更多的情境**(1 次 seek vs 21,254 次)——
   本輪沒量冷讀,結論方向不變但倍數會更大。
2. **`data/1k` 是研究種子集**(每股 median 9 日、max 67 日),不是完整歷史。
   若哪天長成每股數千日,per-stock parquet(P2)與整併檔(P3/B2)的差距會縮小,
   而「現況目錄掃描」會**惡化得比表上更快**(每檔一次 `open` 的固定費 × 檔數)。
3. **tick 流是合成的**(依任務給的 150 檔 × median 2,247 筆)。真實開盤集中度更高,
   瞬時速率會遠高於平均;但本輪量的是**單筆延遲**,不是吞吐,結論(0.11 ms 上限)對速率不敏感。
4. **機器負載漂移 ±35%**(現況基線 10.4 / 12.3 / 14.2 s 三次)。所有倍數都在同一次執行內比。
5. **磁碟是本機 NVMe,未量 `fsync` 的裝置差異。** 若哪天資料落到網路磁碟或 USB,
   `atomic_write_text` 的 +0.31 ms 與 `fsync` 的 +0.4 ms 都會放大一到兩個數量級,R6 的結論會反轉。
6. **沒量並行。** 全部單執行緒。若回測改成多 process 讀同一份整併檔,
   mmap / 共享記憶體會再開一條路,本輪未探。
7. **反轉條件總表**:
   - 若消費端**不肯**從 `list[Bar1K]` 改成 array → R1 的 72.6x 立刻退回 **1.87x 上限**,
     那時候整件事的投報率就只剩「省記憶體」,不值得動格式。
   - 若哪天要對 1K bar 下**跨檔聚合查詢**(「找出所有 XX 的日子」)→ duckdb + 整併 parquet 會翻盤,
     但那是**新需求**,不是現況路徑。
   - 若 tick 要做**跨日回放 + 大量掃描** → parquet(5.0 ms 讀回、7.8 MB/日)明顯勝過 jsonl(318 ms、60 MB/日),
     R3 的「jsonl 就夠」會改成「一開始就寫 parquet」。

---

## 9. 未量(誠實標注)

- `data/brokers/`(11,011 檔 / 392.6 MB)的載入路徑 —— 不在任務四格內。
- 冷 cache(reboot / `Clear-FileSystemCache`)讀取。
- mmap / `memoryview` 零拷貝路徑對回測的端到端影響。
- 多 process / 多執行緒並行讀。
- pyarrow / polars 的 import 時間對 server 冷啟的影響。
- 回測搜索邏輯本身(**任務明示不碰**)。
