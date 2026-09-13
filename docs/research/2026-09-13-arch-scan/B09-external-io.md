# B09 — 外部 IO(FinMind / MIS / 廣度 / 盤前篩選)架構掃描

掃描日期:2026-09-13
工作目錄:`C:\side-project\copycat`(HEAD `caca1d30`,master,唯讀)
量測機器:Windows 11、16 邏輯核心、Python 3.13(`.venv`)

---

## 0. 一句話結論

這一區**沒有「同步 HTTP 直接跑在 event loop 上」的 critical 失誤** —— 每一個 urllib 呼叫點都已經包在
`asyncio.to_thread` 裡,那道功課做完了。真正的問題是另外三件,而且每一件都有實測數字:

1. **`asyncio.to_thread` 對 `json.loads` 是無效的隔離** —— C 層 JSON 解碼全程持有 GIL,實測
   9.3 MB payload 讓 event loop **整整凍住 72 ms**(baseline 對照:同樣在 thread 裡 `time.sleep`,
   loop 最大停頓 3 ms)。盤前篩選一輪要解 21 份這種 payload。
2. **每天重新下載 ~31 份不會變的歷史 EOD**,而本機 `data/daily/prices.csv`(52 MB,欄位完全對得上)
   早就存在卻沒有任何 server 路徑在用。實測:streak 10 日掃描 39 s、screen 21 日窗 53 s。
3. **stdlib `urllib` 不送 `Accept-Encoding`**(已對 CPython 3.13 原始碼確認),所有 FinMind / MIS 回應
   **全部未壓縮傳輸**。實測壓縮比 5.5–6.0×。光是 breadth 每 10 秒一次的全市場快照,一個交易日就
   下載約 **0.9 GB** 未壓縮 JSON。

換句話說:這一區要的不是 numpy / polars(純函式全部在 2–63 ms 量級,換掉是純負債),而是
**傳輸層**(壓縮 + 連線池 + 並行)與**快取層**(不要重抓不變的歷史)。

---

## 1. 架構地圖

```
                     ┌──────────────────────── FinMind api.finmindtrade.com ────────────────────┐
                     │  /taiwan_stock_tick_snapshot   (全市場即時快照,無 query)                 │
                     │  /data?dataset=TaiwanStockInfo                       (代碼對照表)         │
                     │  /data?dataset=...DispositionSecuritiesPeriod        (處置股)             │
                     │  /data?dataset=TaiwanStockPrice&start=end=D          (單日全市場 EOD)     │
                     │  /data?dataset=TaiwanStockDayTrading&start=end=D     (當日當沖名單)       │
                     │  /data?dataset=TaiwanFutOptDailyInfo (oi_levels,B09 邊界外但同一把 token)│
                     └─────────────────────────────────┬───────────────────────────────────────┘
                                                       │ stdlib urllib.request.urlopen(阻塞)
                     ┌─────────────────────────────────┴──────────────────────────┐
                     │  copycat/server/breadth_fetch.py   `_get_rows()`           │
                     │  (唯一取數函式;5 個 wrapper;_ATTEMPTS=2;402 不重試)        │
                     └───────┬────────────────────────────────┬───────────────────┘
                             │ asyncio.to_thread              │ asyncio.to_thread
              ┌──────────────┴───────────┐        ┌───────────┴────────────────────┐
              │ BreadthEngine            │        │ ScreenEngine                   │
              │ server/breadth_engine.py │        │ server/screen_engine.py        │
              │  _poll_loop  每 10 s     │        │  _loop → tick → _run_attempts  │
              │  _compute_streaks_loop   │        │  每交易日 08:00(+ 啟動補跑)   │
              │    每日 06:00 起,10 日  │        │    21 日 EOD 窗 + 當沖 + 處置  │
              └──────┬───────────────────┘        └──────────┬─────────────────────┘
                     │ 純函式(零 IO)                          │ 純函式(零 IO)
        ┌────────────┴─────────────┐              ┌───────────┴──────────────┐
        │ copycat/market_breadth.py│              │ copycat/screening.py     │
        │ copycat/limit_streaks.py │              │ copycat/limit_streaks.py │
        │ copycat/market.py(毫元) │              │ copycat/trading_calendar │
        └────────────┬─────────────┘              └───────────┬──────────────┘
                     │                                        │
       ┌─────────────┴──────────────┐            ┌────────────┴─────────────────────┐
       │ data/market/breadth-D.json │            │ data/market/premarket_screen.json│
       │ data/market/streaks-D.json │            │ WatchlistService.replace_group   │
       │ WsBroadcaster(/ws/breadth) │            │   → 「盤前篩選」群組(契約!)    │
       │ REST /api/market/breadth   │            └──────────────────────────────────┘
       │ REST /api/market/breadth/rows                                            
       └──────────────────────────────┘

                     ┌──────────────── TPEx mis.twse.com.tw(非契約公開端點)────────┐
                     │  getStockInfo.jsp?ex_ch=otc_o00.tw                            │
                     └──────────────────────┬───────────────────────────────────────┘
                                            │ stdlib urlopen(timeout 5 s)
                             copycat/server/mis.py `fetch_otc_snapshot()`
                                            │ asyncio.to_thread
                             index_engine._mis_loop  每 5 s(09:00–13:25 watchdog 窗)
```

### 資料流(一個交易日的完整時間軸)

| 時刻 | 誰 | 做什麼 | 實測 |
|---|---|---|---|
| 00:36(server 啟動) | breadth `_refresh_stock_info` | TaiwanStockInfo 4,321 列 | log 一行 |
| 06:00:07 | breadth `_maybe_arm_streaks` | 武裝連板重算 | — |
| 06:00:07 → 06:00:46 | breadth `_compute_streaks_once` | 10 個交易日 EOD,每日 44,587–46,213 列 | **39 s** |
| 08:00:30 | screen `tick` → `_run_attempts` 第 1 次 | 當沖名單閘擋下(FinMind 未更新) | fail-fast,1 request |
| 08:10 / 08:20 / 08:30 / 08:40 | 同上第 2–5 次 | 同樣被當沖名單閘擋下 | 各 1 request |
| 08:50:32 → 08:51:25 | 第 6 次成功 | 當沖 + 處置 + **21 日 EOD 窗** + 三硬條件 + 寫群組 | **53 s** |
| 09:00:06 | breadth `_apply` | 換日、清當日序列 | — |
| 09:00–13:40 | breadth `_poll_loop` | 每 10 s 一次全市場快照 | **~1,680 次** |
| 09:00–13:25 | index `_mis_loop` | 每 5 s 一次櫃買快照 | **~2,940 次** |
| 依需求 | `/api/market/breadth/rows` | 前端台股綜合 tab active 時每 10 s | 1,954 列 payload |

日誌證據(`logs/server-20260911-0036.log`):

```
1245:2026-09-11 06:00:07,364 breadth streak 武裝 2026-09-11(回看 10 交易日)
1246:2026-09-11 06:00:09,899 breadth streak 2026-09-10:46213 列 / 22 檔漲停
...
1258:2026-09-11 06:00:46,411 breadth streak 2026-09-11 完成:22 檔 / 10 交易日(資料至 2026-09-10)

1525:2026-09-11 08:00:30,463 盤前篩選 2026-09-11 第 1 次取數失敗:… 當沖名單尚無資料;08:10:30 再試
…(第 2–5 次同)…
2287:2026-09-11 08:51:25,698 盤前篩選 2026-09-11(資料日 2026-09-10):硬條件 33 檔 → 資格後 32 檔
2290:2026-09-11 08:51:25,731 盤前篩選 2026-09-11 當沖名單 2082 列(前值 2080)
```

---

## 2. 逐一列出每個 urllib 呼叫點(任務指定問題 #1)

| # | 檔案:行 | 函式 | 是否 async def | 包 to_thread? | timeout | 重試 | 頻率 |
|---|---|---|---|---|---|---|---|
| 1 | `server/breadth_fetch.py:70` | `_get_rows`(全區唯一 urlopen) | 否(同步) | 由呼叫端包 | `_TIMEOUT=30`;EOD/當沖 `_DAILY_TIMEOUT=60` | `_ATTEMPTS=2`,**無退避無 jitter** | 見下 |
| 1a | ← `fetch_snapshot` ← `breadth_engine.py:399` | `_fetch_snapshot` | ✅ `await asyncio.to_thread` | 30 s | 2 | **每 10 s,~1,680 次/日** |
| 1b | ← `fetch_stock_info` ← `breadth_engine.py:451` | `_refresh_stock_info` | ✅ to_thread | 30 s | 2 | 一天 1–2 次(24h TTL + 換日) |
| 1c | ← `fetch_disposition` ← `breadth_engine.py:486` | `_refresh_disposition` | ✅ to_thread | 30 s | 2 | 一天 1–2 次 |
| 1d | ← `fetch_daily_prices` ← `breadth_engine.py:750` | `_compute_streaks_once` | ✅ to_thread | **60 s** | 2 | 一天 ≤ 10 成功 / 上界 ~35 次 |
| 1e | ← `fetch_daily_prices` ← `screen_engine.py:297` | `_compute_with_daytrade_rows` | ✅ to_thread | **60 s** | 2 | 一天 21 次 × 最多 6 attempts |
| 1f | ← `fetch_day_trading` ← `screen_engine.py:264` | 同上 | ✅ to_thread | **60 s** | 2 | 一天 ≤ 6 次 |
| 1g | ← `fetch_disposition` ← `screen_engine.py:274` | 同上 | ✅ to_thread | 30 s | 2 | 一天 ≤ 6 次 |
| 2 | `server/mis.py:46` | `fetch_otc_snapshot` | 否(同步) | ✅ `index_engine.py:511` to_thread | `_TIMEOUT=5` | **0**(單次即 None 降級) | **每 5 s,~2,940 次/日** |
| 3 | `server/oi_levels.py:156` | `_fetch_rows` | 否 | ✅ `oi_levels.py:260` to_thread | `_TIMEOUT`(見該檔) | `_ATTEMPTS` | 每日快取,請求驅動 |
| 4 | `copycat/notify.py:15` | Discord webhook | 否 | ✅ `signal_hub.py:1563` | — | — | 訊號驅動 |
| 5 | `data/backfill_*.py`(3 支) | CLI 離線回補 | — | 不適用(CLI) | 60 s | 有 | 離線 |
| 6 | `copycat/stkfut_map.py:179`、`stock_names.py` | 一次性建表 | — | 離線 | 30 s | — | 離線 |

**結論:event loop 上沒有裸的同步 HTTP。** 這道功課本 repo 做完了 —— 但那並不等於「不會塞住」,見 §4 的
`B09-02`(GIL)與 `B09-06`(共用 executor)。

---

## 3. 熱路徑逐條(含實測)

量測腳本在 `scratchpad/arch-scan/bench_b09*.py`(唯讀,不動 repo)。

### HP-1 `BreadthEngine._run_cycle` —— 每 10 s(交易日 09:00–13:40,~1,680 次/日)

`breadth_engine.py:377-395`

```python
async def _run_cycle(self) -> None:
    rows = await self._fetch_snapshot()          # to_thread,~0.55 MB
    if rows is not None:
        await self._refresh_maps()               # 多半 no-op
        last_minute = self._apply(rows)          # ← 在 event loop 上
    self._ws.publish(self.payload(last_minute))
```

`_apply` 全程**在 event loop 上**跑,實測分解(fixture `tests/fixtures/breadth_parity.json`,
snapshot 2,865 列 / universe 1,954 檔):

| 步驟 | 實測 |
|---|---|
| `max_tick_datetime(rows)` | 0.70 ms |
| `assemble_universe(rows, sector, watch)` | 0.82 ms |
| `compute_breadth(universe, tmap, nmap)` | **5.42 ms** |
| `_append` → `_save`(21 KB 整份 rewrite) | ~0.2–0.5 ms(同步檔案 IO) |
| 合計 loop 佔用 | **≈ 7–8 ms / 10 s** |

另外 `_fetch_snapshot` 那一趟在 worker thread:TLS 握手 **85–106 ms**(實測)+ 下載 0.55 MB +
`json.loads` 3.3 ms(loop 停頓 3.16 ms)。

判定:**這條不是瓶頸**。7–8 ms / 10 s = 0.08% duty cycle。不要動。

### HP-2 `GET /api/market/breadth/rows` —— 每 10 s(前端台股綜合 tab active 時)

`app.py:1940` → `breadth_engine.rows_state()`(`breadth_engine.py:280-324`)

```python
for row in self.rows:
    ...
    rows_out.append({**row, "streak": streak, "streak_capped": capped})
```

實測(1,954 列 × 13 欄):

| 步驟 | 實測 |
|---|---|
| `rows_state()` dict 重建 | **0.35 ms** |
| FastAPI 序列化(route 有 `-> dict` 註解,走 pydantic-core) | **4.5 ms**(TestClient p50) |
| 對照:若拿掉 `-> dict` 註解(退回 `jsonable_encoder`) | **41 ms**(9× 慢) |
| payload 大小 | 559 KB |

判定:**已經在快路徑上,不要動**。細節見 `B09-15`(隱形契約)。

### HP-3 `index_engine._mis_loop` —— 每 5 s(~2,940 次/日)

`index_engine.py:505-515`、`mis.py:41-80`

```python
while True:
    snap = await asyncio.to_thread(self._mis_fetch)   # urlopen timeout 5 s
    if snap is not None: self._apply_otc(snap)
    await asyncio.sleep(self._poll)                   # sleep 在 fetch 之後 → 不會堆疊
```

實測:TLS 握手 **17.8–20.9 ms**(mis.twse.com.tw)。payload 極小(單一 msgArray),
解析 < 0.1 ms。`_apply_otc` 在 loop 上,O(1)。

判定:節奏正確(sleep 在後、不堆疊)、payload 微小。唯一浪費 = 每次一次完整握手
(2,940 × ~19 ms ≈ **56 s/日** 純握手)。低優先。

### HP-4 `BreadthEngine._compute_streaks_once` —— 每日一次 06:00

`breadth_engine.py:719-851`

```python
while d >= floor and len(day_sets) < STREAK_WINDOW_DAYS:      # 10 個交易日
    rows = await asyncio.to_thread(fetch, self._token, d)      # 每日 44k–46k 列
    await asyncio.sleep(_STREAK_REQ_GAP_SECS)                  # 0.3 s
    ...
    day_set = compute_day_limitups(rows)                       # ← 在 loop 上!
```

⚠️ **注意**:`compute_day_limitups(rows)` 沒有包 to_thread,它跑在 event loop 上
(`breadth_engine.py:775`)。實測 45k 列 = 7.3–24.1 ms(視權證/ETF 佔比),每日 10 次。
06:00 盤外,無害;但這是一個「以為在背景其實在前景」的樣態。

實測整體:log 39 s / 10 日。合成量測(45k 列、9.3 MB):

| 步驟 | 實測 | loop 停頓 |
|---|---|---|
| `json.loads`(worker thread) | 72.7–77.2 ms | **72.25 ms(全程凍住)** |
| `compute_day_limitups`(loop) | 7.3–24.1 ms | 7.2 ms |
| 網路(TLS + 下載 4.5–9 MB) | ~2.2–5.0 s / 日 | — |

### HP-5 `ScreenEngine._compute_with_daytrade_rows` —— 每交易日 08:00(最多 6 attempts)

`screen_engine.py:248-328`

```python
dt_rows  = await asyncio.to_thread(self._day_trading_fetch, ...)  # 1 request
disp_rows= await asyncio.to_thread(self._disposition_fetch, ...)  # 1 request
while d >= floor and len(days) < WINDOW_DAYS:                     # 21 個交易日
    rows = await asyncio.to_thread(self._daily_fetch, self._token, d)
    await asyncio.sleep(_REQ_GAP_SECS)                            # 0.3 s
    memo[d] = shrunk = shrink_rows(rows)                          # ← 在 loop 上!
    days.append((d, shrunk))
cands = hard_candidates(days)                                     # ← 在 loop 上!
final = apply_eligibility(...)
```

⚠️ 同樣的樣態:`shrink_rows`(21 次 × 7.4–21.9 ms)與 `hard_candidates`(63 ms)
**都跑在 event loop 上**。

實測(合成 45k 列 / 21 日窗 / 2,000 檔普通股):

| 步驟 | 實測 | loop 停頓 |
|---|---|---|
| `json.loads` × 21(worker) | 21 × 72–77 ms ≈ **1.6 s** | 每次 **72 ms 全凍**,21 次 |
| `shrink_rows` × 21(loop) | 21 × 7.4 ms ≈ 0.16 s | 每次 5.1 ms |
| `hard_candidates`(loop) | **63.0 ms** | 15.9 ms(GIL switch 有讓出) |
| `apply_eligibility` | < 0.1 ms | — |
| 網路(23 次請求) | ≈ **50 s** | — |
| **實測總 wall** | **53.3 s**(08:50:32.378 → 08:51:25.698) | |

**bottleneck 在網路,不在計算**(計算佔 ~1.8 s / 53 s = 3.4%)。這是決定「不要上 polars」的關鍵數字。

### HP-6 `_refresh_stock_info` 後的三張對照表重建 —— 一天 1–2 次

`breadth_engine.py:466-468`,三個純函式都在 **loop 上**:

| 函式 | 實測(4,300 列) | 備註 |
|---|---|---|
| `dedup_sector_map` | 2.32 ms | 內部**雙重 sort** 4,300 列 |
| `build_type_map` | 0.88 ms | 又 sort 一次同一份 |
| `build_name_map` | 0.64 ms | 又 sort 一次同一份 |

三支各自 sort 同一份 rows(共 3 次 + dedup 的 2 次 = 4 次 sort)。總計 3.8 ms / 天。**不要動。**

---

## 4. Findings

### B09-01 `critical` / `architecture` — 每天重抓 ~31 份不會變的歷史 EOD,而本機已有同欄位的離線存量沒人用

**位置**:`copycat/server/screen_engine.py:190`(`eod_memo` 生命週期)、`:297`;
`copycat/server/breadth_engine.py:218`(`_streak_memo`)、`:670`(每次武裝清空)、`:750`

**證據**:

```python
# screen_engine.py:190  —— memo 是 _run_attempts 的區域變數,函式回傳即消失
eod_memo: EodMemo = {}

# breadth_engine.py:663-670 —— 每日武裝時整組清空
self._streaks = {}
...
self._streak_memo = {}
self._streak_armed_day = today
```

`data/daily/prices.csv` 已經存在且欄位完全對得上(`stock_id,date,open,high,low,close,spread,volume_lots`):

```
$ ls -la data/daily/
-rw-r--r-- 1 USER 197608 52059407 Jul 17 22:40 prices.csv
-rw-r--r-- 1 USER 197608     4972 Jul 17 22:40 backfill_manifest.json
```

實測載入:`DailyIndex.load(Path('data'))` → **3,523 ms**,2,044 檔 × 平均 509 個日期(~1M 列)。
更新工具也在:`python -m copycat backfill-daily`(`data/backfill_finmind.py`,冪等 by
`(stock_id, date)`,有 manifest 續傳)。但**檔案停在 2026-07-17**,且 `screen_engine` /
`breadth_engine` 兩支 server 引擎都**完全沒引用它**。

**影響**:
- streak 每日重抓 D−1..D−10 共 10 份(其中 9 份昨天抓過)→ **39 s / 日**
- screen 每日重抓 D−1..D−21 共 21 份(其中 20 份昨天抓過)→ **~50 s / 日**(網路段)
- 兩者的日期窗**重疊**:screen 的 21 日窗是 streak 10 日窗的 **超集**,同一個早上各下載一份
- 每日冗餘傳輸:31 × ~4.5 MB ≈ **140 MB/日**(未壓縮,見 B09-03),其中 ~29 份是重複的
- 真正新增的資料只有「D−1 那一天」一份

**修法**:
1. 抽一支 `EodStore`(deep module,單一 seam):`get(date) -> list[dict] | None`,
   命中本地就不打 FinMind;miss 才 fetch 並落檔。落檔格式先用現成的 `shrink_rows` 後
   JSON(~2,000 檔 × 4 欄,每日 < 200 KB),或直接餵回 `data/daily/prices.csv` 的 schema。
2. `screen_engine` 與 `breadth_engine` 兩邊都注入同一個 store(兩者的窗天然共享)。
3. 完整性判準要換:`_DAILY_MIN_ROWS = 25_000` 是針對 FinMind **原始** 45k 列(含權證)的守門,
   本地存量只有 ~2,000 檔普通股,要改成對普通股檔數的門檻(否則本地命中會一律誤判成截斷)。

**風險**:
- 落檔一旦寫錯就是「連板數/篩選名單整天錯著且零錯誤訊號」,而這正是 breadth 全檔註解一路在防的事。
  必須沿用既有守門:`_require_date_echo`(資料日回聲)+ 列數門檻 + 原子寫 + `_version` 欄。
- **不動任何跨檔契約**:`SCREEN_GROUP`「盤前篩選」字面、`WATCHLIST_LIMIT`、
  `premarket_screen.json` 的 `_CACHE_VERSION` 都不受影響(這是純取數層的事)。
- `tests/fixtures/breadth_parity.json` 全管線 oracle 只釘純函式,取數層改動不碰它。

**Effort**:M

---

### B09-02 `critical` / `blocking-io` — `asyncio.to_thread` 對 `json.loads` 完全無效:實測單次凍住 event loop 72 ms

**位置**:`copycat/server/breadth_fetch.py:70-71`

```python
with urlopen(req, timeout=timeout) as resp:
    payload = json.load(resp)        # ← 4.5–9 MB;C 層解碼全程持有 GIL
```

**證據**(`bench_b09f.py`,`await asyncio.sleep(0)` 心跳測 loop 停頓):

```
baseline sleep(0.1)                work= 103.3 ms | loop 停頓 max=  3.07 ms | ticks=40738
json.loads(EOD 45k / 9MB)          work=  72.7 ms | loop 停頓 max= 72.25 ms | ticks=9
json.loads(snapshot 2865/0.54MB)   work=   3.3 ms | loop 停頓 max=  3.16 ms | ticks=4
compute_day_limitups(45k)          work=   7.3 ms | loop 停頓 max=  7.21 ms | ticks=4
hard_candidates(21d x 2000)        work=  63.0 ms | loop 停頓 max= 15.88 ms | ticks=26
```

讀法:baseline(thread 在 `time.sleep`,GIL 已釋放)103 ms 內 loop 跑了 **40,738 拍**,最大停頓 3 ms。
同樣包在 `to_thread` 裡的 `json.loads`,72.7 ms 內 loop 只跑了 **9 拍**,最大停頓 **72.25 ms** ——
`to_thread` 一點隔離作用都沒有,因為 CPython 的 `_json` C 掃描器在整趟解碼期間不釋放 GIL、
也沒有 bytecode 邊界可供 GIL 切換。

反直覺的對照:**純 Python 迴圈反而比 C 層 JSON 解碼溫和** —— `hard_candidates` 做了 63 ms 的工,
loop 仍跑了 26 拍(最大停頓 15.9 ms),因為純 Python 每 `sys.setswitchinterval()` 會讓出一次。

實測吞吐:`json.loads` = **121 MB/s**。真實 FinMind EOD 依文件約 4.5 MB(`breadth_fetch.py:41-43`
「回應是 MB 級」;2026-09-02 實錄「4.5MB 全市場回應截斷」)→ **每份約 37 ms 的全凍**。

**影響**:
- screen 一輪 21 份 → **~0.8 s 的 loop 全凍,散成 21 段 37 ms**
- streak 一輪 10 份 → ~0.4 s,散成 10 段
- 兩者常態都在盤外(06:00 / 08:00–09:00),**但 B09-04 會把 screen 推進盤中**
- 37 ms 的 loop 全凍在盤中意味著:TC4 tick fanout、WS 心跳、閃電梯更新全部停一拍

**修法**(依收益排序):
1. **`orjson` / `msgspec`**:兩者都是 Rust/C 實作,公開 benchmark 對大型 JSON 約 3–6× 於 stdlib
   (**推測,本機未裝無法實測** —— 量測方法見 §7)。37 ms → ~7–12 ms。
   `msgspec.json.decode(buf, type=list[EodRow])` 另可**直接產 struct**,省掉 45k 個 dict 的建構
   與後續 `shrink_rows` 一整趟。
2. **gzip**(見 B09-03):傳輸量降 5.5×,但**解碼時間不變**(解壓後還是同樣大的字串)。
   注意 `zlib` 解壓**會**釋放 GIL(實測 9.4 MB → 15.4 ms,且不凍 loop),所以 gzip 是純賺。
3. **不要**用 `ijson` 之類的 streaming parser:純 Python 迭代反而更慢。

**風險**:`orjson` / `msgspec` 是 binary wheel,Windows 有官方 wheel,但這會**打破
`dependencies = []` 的 stdlib-only runtime 哲學**(pyproject.toml line 6)。建議放進
`[live]` extras 而非核心 `dependencies`,並保留 stdlib fallback:

```python
try:
    from orjson import loads as _loads
except ImportError:
    from json import loads as _loads
```

`_get_rows` 是**唯一**的解碼點(5 個 wrapper 全走它),改一處全收 —— 這是這個 codebase
少數真正的 deep module,值得利用。

**Effort**:S(單點替換 + fallback)

---

### B09-03 `high` / `blocking-io` — stdlib `urllib` 不送 `Accept-Encoding`:所有 FinMind / MIS 回應未壓縮傳輸,breadth 一日下載 ~0.9 GB

**位置**:`copycat/server/breadth_fetch.py:66`、`copycat/server/mis.py:44`、`copycat/server/oi_levels.py:154`

```python
req = Request(url, headers={"Authorization": f"Bearer {token}"})   # 只有 Authorization
```

**證據**:CPython 3.13 `urllib.request.AbstractHTTPHandler.do_request_` 原始碼(本機 inspect 確認)
只會補上 `Host` / `Content-type` / `Content-length` / `Transfer-encoding`,
外加 opener 的 `addheaders = [('User-agent', 'Python-urllib/3.13')]`。
**沒有 `Accept-Encoding`**,而 HTTP 的預設語意是「不送就別壓」。

實測壓縮比:

```
EOD  raw 9.36 MB → gzip 1.72 MB   ratio 5.5   (gzip.decompress 15.4 ms,且不凍 loop)
snapshot raw 0.544 MB → gzip 0.091 MB  ratio 6.0
```

**影響**(以 09:00–13:40 / 10 s 輪詢 = 1,680 次計):

| 路徑 | 次數/日 | 未壓縮 | gzip 後 | 省 |
|---|---|---|---|---|
| breadth snapshot | 1,680 | **~914 MB** | ~152 MB | 762 MB |
| screen EOD 21 份 | 21 | ~95–195 MB | ~17–35 MB | ~78–160 MB |
| streak EOD 10 份 | 10 | ~45–94 MB | ~8–17 MB | ~37–77 MB |
| MIS | 2,940 | 微量 | 微量 | — |
| **合計** | | **~1.05–1.2 GB/日** | **~180–200 MB/日** | **~0.9–1 GB/日** |

這同時是 **wall time**:screen 那 50 s 的網路段,絕大部分是在拉未壓縮 bytes。

**修法**:
- 最小改動(stdlib,零新相依):`Request(url, headers={..., "Accept-Encoding": "gzip"})`
  + 依 `resp.headers.get("Content-Encoding")` 決定要不要 `gzip.decompress`。
  改動範圍 = `breadth_fetch._get_rows` 一個函式 + `mis.py` / `oi_levels.py` 各一處。
- 正規改動:換 `httpx`,它預設就送 `Accept-Encoding: gzip, deflate` 並透明解碼(見 B09-05)。

**風險**:
- 需先**確認 FinMind 真的支援 gzip**(未驗證,見 §9 open question)。不支援時伺服器會照回未壓縮,
  `Content-Encoding` 不存在 → fallback 路徑就是現況,零回退風險。
- MIS 是非契約公開端點(`mis.py:3` 明寫「可能無預警壞」),額外 header 理論上可能觸發不同行為 ——
  MIS payload 本來就微小,**建議 MIS 不要動**。

**Effort**:S

---

### B09-04 `high` / `concurrency` — `ScreenEngine._run_attempts` 沒有整體 deadline,最壞單一 attempt 可跑 46 分鐘、跨進盤中

**位置**:`copycat/server/screen_engine.py:183-220`、`:64`、`breadth_fetch.py:43-44`

```python
_RETRY_UNTIL = _dt.time(9, 0)          # 只約束「下一次 attempt 的『起算』時刻」
...
def _next_attempt_at(self) -> _dt.datetime | None:
    nxt = now + _dt.timedelta(seconds=_RETRY_SECS)
    deadline = _dt.datetime.combine(now.date(), _RETRY_UNTIL)
    return nxt if nxt < deadline else None
```

時間盒只管「什麼時候**開始**下一次」,不管「這一次要跑多久」。單一 attempt 的理論上界:

```
23 requests × _ATTEMPTS(2) × _DAILY_TIMEOUT(60 s) = 2,760 s = 46 分鐘
```

實錄的最後一次 attempt 起於 **08:50:32**(log line 2070 的下一輪)。FinMind 慢的日子,
那一趟可以一路跑到 **09:36**。

**影響**:B09-02 的 21 段 × 37 ms loop 全凍,會落在 **09:00–09:30 開盤最忙的半小時**。
同時 B09-06 的 worker thread 也在那段時間被佔住。而目前**沒有任何觀測能看出這件事發生了**
(成功那行 log 只印結果,不印耗時)。

**修法**:
1. 在 `_run_attempts` 外層包 `asyncio.timeout(deadline - now)`,`deadline` = 當日 `_RETRY_UNTIL`。
   逾時 → 走既有的 `_give_up` 路徑(語意完全對得上「過了開盤就不追」,
   `screen_engine.py:16-18` 的 docstring 已經這樣寫,只是實作沒守住)。
2. 順手把 `_DAILY_TIMEOUT` 拆成 connect / read 兩段(stdlib urlopen 做不到;httpx 可以)。

**風險**:`_give_up` 會把 `_gave_up_for = target`,群組維持前一日名單 —— 這是既有且已拍板的降級語意
(user 2026-09-08 拍板 Q8),不是新行為。測試檔 `tests/server/test_screen_engine.py` 有對應案。

**Effort**:S

---

### B09-05 `high` / `blocking-io` — 完全沒有連線池:每次 `urlopen` 付一次完整 TCP+TLS 握手(實測 FinMind 85–106 ms)

**位置**:`breadth_fetch.py:70`、`mis.py:46`、`oi_levels.py:156` —— 全部用 `urllib.request.urlopen`,
它每次都建新的 `HTTPSConnection` 並在 context manager 結束時關閉。

**證據**(本機實測,純握手,不發 API 請求):

```
api.finmindtrade.com [105.9, 88.0, 84.4] ms (TCP+TLS handshake)
mis.twse.com.tw      [ 20.0, 17.8, 20.9] ms (TCP+TLS handshake)
```

**影響**:

| 路徑 | 次數/日 | 純握手成本 |
|---|---|---|
| breadth snapshot | 1,680 | **~150 s/日** |
| MIS | 2,940 | ~56 s/日 |
| screen 23 + streak 10 | 33 | ~3 s/日 |

這段成本落在 worker thread(握手期間 GIL 已釋放)→ **不凍 loop**,但它是純粹的延遲與上游負擔。
對 breadth 而言,每一輪 10 s 的取數有 ~90 ms(~1%)是在重建同一條連線。

**修法**:改用 `httpx.AsyncClient`(**`httpx 0.28.1` / `httpcore 1.0.9` 已經裝在 `.venv` 裡**,
目前掛在 `[dev]` extras 給 `TestClient` 用)。收益:
- 連線池 + keep-alive(省掉 99% 的握手)
- 預設 `Accept-Encoding: gzip, deflate` 並透明解壓(順手解掉 B09-03)
- 原生 async → **拿掉 `to_thread`**,IO 段真正在 loop 上等,不再佔 worker(解掉 B09-06 的一半)
- `httpx.Timeout(connect=, read=, write=, pool=)` 四段式(解掉 B09-04 的一半)
- 可設 `limits=httpx.Limits(max_connections=…)` 控住並行(配合 B09-07)

**風險 / 取捨**:
- **打破 `dependencies = []`**。建議進 `[live]` extras(和 fastapi / uvicorn 同層),不進核心。
  CLI 離線路徑(`data/backfill_*.py`)可以繼續用 urllib,不必一起搬。
- `httpx.AsyncClient` 的生命週期要掛在 `app.py` lifespan 上,並且要納入 §4 的
  **「關機預算三方同源」契約**(`copycat/server/shutdown_budget.py::run_grace_secs()` /
  `run.ps1` / `__main__.py`)—— 加一個 aclose 段就要重算 `TC4_LANE_DEPTH` 那條不等式,
  `tests/server/test_shutdown_budget.py` 會紅。**這是這條改動唯一會動到跨檔契約的地方,必須點名。**
- `breadth_fetch._get_rows` 目前是**同步**函式且由呼叫端包 to_thread —— 改 async 會讓
  `screen_engine` / `breadth_engine` 三個注入點(`SnapshotFetch` / `DailyPricesFetch` 等
  `Callable` 型別別名,`breadth_engine.py:108-111`)全部要改成 awaitable。
  測試的 fake 取數器也要跟著改(`tests/server/test_breadth_engine.py`、`test_screen_engine.py`)。
  這是 M 級不是 S 級的原因。
- HTTP/2(`httpx[http2]` 需另裝 `h2`):對**序列**請求幾乎沒有收益,配合 B09-07 的並行才有意義。
  **建議先不上**,把它留給量測證明有必要之後。

**Effort**:M

---

### B09-06 `high` / `concurrency` — 全部 FinMind / MIS IO 共用 loop 預設 ThreadPoolExecutor,與 TC4 / capital COM / signal jsonl 同池

**位置**:全區 `asyncio.to_thread` 呼叫點;無任何 `set_default_executor` / `ThreadPoolExecutor`
(`grep -rn "set_default_executor\|ThreadPoolExecutor\|max_workers" copycat/` → **零命中**)。

專案自己已經記下這個風險,`app.py:1568-1572`:

```python
# to_thread 走 loop 預設 executor,與 daily_bars / capital close 同池且工作
# 執行緒不可中斷 —— TC4 半死的殭屍執行緒堆積時這條會跟著排隊(review C-1);
# today 若變慢先查同池鄰居,別急著懷疑 jsonl。
```

**證據 / 量級**:本機 16 邏輯核心 → 預設 `max_workers = min(32, 16+4) = 20`。同池住戶:

| 住戶 | 最長佔用 |
|---|---|
| `breadth_fetch` EOD(`_DAILY_TIMEOUT=60`,`_ATTEMPTS=2`) | **120 s / 次** |
| `breadth_fetch` snapshot / info / disposition(30 s × 2) | 60 s / 次 |
| `mis.fetch_otc_snapshot`(5 s) | 5 s / 次,每 5 s 一發 |
| `app.py:544` `daily_bars`(**「走 to_thread 沒有上限、整組(上限 150 條)請求共用同一條 TC4 歷史通道」**) | 不定 |
| `capital` COM close join(`app.py:952`) | `COM_JOIN_TIMEOUT_SECS` |
| `signal_hub` jsonl 讀寫、`_append_jsonl`、`backfill_policy_outcomes` | 不定 |
| `stock_engine` 訂閱 / 回補 / `_resubscribe_all`(ZMQ REQ 全程 to_thread) | TC4 半死時無上界 |

**影響**:screen 那一輪 53 s 期間,有一條 worker 從頭佔到尾。TC4 半死(專案 §8 已記載的常態失效)
時殭屍執行緒堆積,20 個名額用完 → **所有 `to_thread` 開始排隊**,包含 `/api/stock/signals/today`、
`daily_bars`、閃電梯的 capital 路徑。這正是 app.py 註解在警告的事。

**修法**:給外部 HTTP IO 一個**專屬**有界 executor:

```python
# app.py lifespan
app.state.http_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="finmind")
# breadth_fetch 呼叫端:loop.run_in_executor(app.state.http_pool, fn, ...)
```

隔離失效域(和 `breadth_engine` 檔頭「完全不碰 TC4 / ZMQ,失效域隔離 SC-3」的設計意圖一致)。
若採 B09-05 的 httpx async,這條的 FinMind 部分自動消失(不再用 thread),只剩 MIS 要處理。

**風險**:新增一個 executor 要進關機序列(`app.py` lifespan + `shutdown_budget`),
同 B09-05 的契約注意事項。

**Effort**:S(獨立 executor)/ 隨 B09-05 一起做則 0 額外成本

---

### B09-07 `high` / `serialization` — screen 的 21 份 EOD 完全序列取數,無並行;實測 53 s

**位置**:`copycat/server/screen_engine.py:282-312`

```python
while d >= floor and len(days) < WINDOW_DAYS:
    ...
    rows = await asyncio.to_thread(self._daily_fetch, self._token, d)
    await asyncio.sleep(_REQ_GAP_SECS)        # 0.3 s,每一發都睡
```

同款在 `breadth_engine.py:750-751`(`_STREAK_REQ_GAP_SECS = 0.3`)。

**證據**:實測 08:50:32.378 → 08:51:25.698 = **53.3 s / 23 requests**,約 2.3 s/request。
其中 23 × 0.3 s = 6.9 s 是刻意的 gap。streak 同樣 39 s / 10 requests ≈ 3.9 s/request。

FinMind Sponsor 配額 = **6,000 req/hr**(專案 skill `finmind-conventions`)。
一天全部 FinMind 請求量:1,680(snapshot)+ 21 + 10 + ~5 ≈ 1,716 次 —— 用掉不到
**每小時**額度的 1/3,分散在一整天。並行 4–6 條完全不會撞配額。

**修法**:`asyncio.gather` + `asyncio.Semaphore(4)`(或 httpx 的 `Limits`)。
21 日窗 50 s → **~13 s**。但注意:
- **這個改動的優先序低於 B09-01**。做完 B09-01(本地 EOD store)之後,每天只要抓 1 天,
  並行就沒有意義了。**兩者擇一,先做 B09-01。**
- 並行後 `_require_date_echo` / `_DAILY_MIN_ROWS` 的失敗處理要改成「收集全部結果再判」,
  目前的 `raise → 整輪重試` 在 gather 下會變成部分完成。
- `_REQ_GAP_SECS` 的 0.3 s 是禮貌性節流,並行後要改成 semaphore 限流。

**風險**:中。fail-fast 語意(`pr-211 F-02`,當沖名單先過閘)是刻意設計,並行化時要保住
「名單沒出齊就只花 1 個請求」這個性質 —— 當沖名單與處置股必須**仍然序列在前**,
只有那 21 份 EOD 並行。

**Effort**:M

---

### B09-08 `medium` / `blocking-io` — 純函式全部在 event loop 上跑,`to_thread` 只包了網路那一段

**位置**:
- `breadth_engine.py:775` `compute_day_limitups(rows)` —— 45k 列,7.3–24.1 ms,每日 10 次
- `screen_engine.py:306` `shrink_rows(rows)` —— 45k 列,7.4–21.9 ms,每日 21 次
- `screen_engine.py:317` `hard_candidates(days)` —— **63.0 ms**,每日 1 次
- `breadth_engine.py:528-529` `assemble_universe` + `compute_breadth` —— 6.2 ms,**每 10 s**
- `breadth_engine.py:466-468` 三張對照表 —— 3.8 ms,每日 1–2 次

```python
# screen_engine.py:297-306 —— fetch 包了 to_thread,shrink 沒有
rows = await asyncio.to_thread(self._daily_fetch, self._token, d)
await asyncio.sleep(_REQ_GAP_SECS)
if rows:
    ...
    memo[d] = shrunk = shrink_rows(rows)      # ← loop 上
```

**影響**:單看數字都不大(最大 63 ms)。但這是 B09-04 的放大器 —— screen 若跑進盤中,
`hard_candidates` 那 63 ms 會落在盤中。而 `compute_breadth` 的 6 ms × 每 10 s 是常態盤中負擔。

**修法**:把 `shrink_rows` / `compute_day_limitups` 併進取數那一趟的 `to_thread`
(反正 payload 已經在那條 thread 上,順便縮掉還能少一次 45k 列的跨執行緒 refcount 壓力):

```python
def _fetch_and_shrink(token, d):          # 一起丟 to_thread
    return shrink_rows(_daily_fetch(token, d))
```

`hard_candidates`(63 ms)單獨包一次 `to_thread`。
`compute_breadth`(6 ms / 10 s)**不要動** —— 6 ms 的工丟 thread,context switch 成本比省下的多。

**風險**:低。純函式無狀態,搬到 thread 無副作用。但 `shrink_rows` 之後 `_require_date_echo`
需要原始 `rows[0]["date"]`,合併時順序要保住(`screen_engine.py:305` 的註解已經點名
「`shrink_rows` 後 date 欄已丟,只能在 fetch 當下驗」)。

**Effort**:S

---

### B09-09 `medium` / `blocking-io` — 落檔全部是 event loop 上的同步檔案 IO

**位置**:
- `breadth_engine.py:956-973` `_save()` —— **每 10 s** 一次,`_series_list()` 排序 + `json.dumps`
  + `tmp.write_text` + `os.replace`
- `breadth_engine.py:856-876` `_save_streaks()` —— 每日一次
- `screen_engine.py:420-445` `_write_cache()` —— 每日一次,`atomic_write_text`
- `screen_engine.py:394-401` `_read_cache()` —— 每次 `_due()` 判定都整份讀 + `json.loads`
  (`_loop` 一輪會呼叫 2 次:`tick()` 一次、迴圈末再一次;`_run_once` 再一次)

```python
# breadth_engine.py:967-971 —— 每 10 s、在 event loop 上
tmp = path.with_name(f"{path.name}.tmp")
try:
    self._data_dir.mkdir(parents=True, exist_ok=True)     # 每次都 stat
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
```

**證據 / 量級**:`breadth-2026-09-02.json` = 21,113 bytes(整天 270 個分鐘格的上界)。
`json.dumps` + 21 KB 寫 + `os.replace` ≈ 0.2–0.5 ms。**在乾淨機器上完全無感**。

**影響**:Windows + 防毒即時掃描時,`os.replace` 偶發可以到數十 ms。這是 `atomic write` 在
Windows 上的已知特性。低機率、低嚴重度,但它每 10 s 就賭一次,且整天累計 1,680 次。

**修法**:`_append` 的落檔改 `asyncio.create_task(asyncio.to_thread(self._save))`
——或更好:**改成每 N 分鐘落一次 + 收盤/關機時強制落一次**。序列檔的用途是「重啟後續寫」,
掉最後幾格的代價遠低於每 10 s 賭一次。

**風險**:低。但要注意 `_save` 讀的是 `self._series` 與 `self._trade_date`,丟 thread 後
與下一輪 `_apply` 的寫入會有 race(換日清序列那一刻)。要嘛先做 snapshot 再丟 thread,
要嘛維持同步。**這是為什麼我把它列 medium 而不是 high:修法本身有 race 風險,而收益很小。**

**Effort**:S

---

### B09-10 `medium` / `observability` — 完全沒有單次請求的耗時觀測

**位置**:`breadth_fetch.py:90-96`(失敗才 log,且只印 `type(last).__name__`)、
`breadth_engine.py:784`(成功印列數,不印耗時)、`screen_engine.py:319-327`(印結果,不印耗時)

```python
logger.warning(
    "breadth %s 取數失敗(第 %d/%d 次):%s",
    label, attempt + 1, _ATTEMPTS, type(last).__name__,     # ← 連 e 的訊息都沒有
)
```

**影響**:整個 §3 的量測我都得靠**兩行 log 的時戳相減**(06:00:07 → 06:00:46)才推得出來,
而 screen 那一輪 53 s 是靠 WARNING 與 INFO 兩行的時戳差。
目前無從分辨「FinMind 慢」「網路慢」「解碼慢」「本地計算慢」——
而這正是要證明 B09-02 / B09-03 / B09-05 的改動有沒有效所需要的資料。

**修法**:`_get_rows` 內加三個計時段(connect+download / decode / 列數),成功路徑 INFO 一行:

```
breadth daily_prices 2026-09-10:46213 列 / 4.7 MB / net 2180 ms / decode 38 ms
```

這一行同時是 B09-01/02/03/05 的**驗收判準**(改動前後 grep 同一行對照)。

**風險**:零(純加 log)。注意 `PLE1205/PLE1206`(ruff extend-select)會檢查 logging 參數個數。

**Effort**:S

---

### B09-11 `medium` / `architecture` — `finmind_token` 用 CWD 相對路徑,與全專案 repo-root 錨定慣例不一致

**位置**:`copycat/server/finmind_token.py:22`

```python
def _dotenv_values() -> dict[str, str]:
    env_file = Path(".env")            # ← CWD 相對
```

對照 `breadth_engine.py:82-84` 與 `screen_engine.py:106-112` 的註解,兩邊都刻意錨定 repo root
並寫明理由:

```python
#: 錨定 repo root(`__main__.LOG_DIR` 同慣例):cwd 相對會在子目錄起 server 時
#: 長出第二份 data/,而序列檔「換個地方存」的表現是重啟後序列莫名歸零
_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "market"
```

**影響**:在子目錄(或 worktree 內某層)起 server → `.env` 讀不到 → `resolve_token()` 回 None
→ **breadth 引擎不建(`app.py:676` `app.state.breadth = None`)、screen 引擎不建、
oi_levels 恆空 shape** —— 三個功能一起靜默消失,而畫面上 breadth 會顯示成「未設定」
(合法配置態),零錯誤訊號。這正是 `ops-discipline` skill 的 worktree 三險在防的那類事故。

**影響是正確性/可操作性,不是效能** —— 但它會讓「效能改動有沒有生效」的量測整組失真
(以為改壞了,其實是根本沒跑)。

**修法**:`Path(__file__).resolve().parents[2] / ".env"`,並保留 CWD 相對當 fallback。

**風險**:低。`_dotenv_cache` 是模組層 global,測試要記得清(既有測試可能依賴 CWD 行為,
先 grep `tests/` 對 `finmind_token` 的 monkeypatch)。

**Effort**:S

---

### B09-12 `medium` / `algorithmic` — `_get_rows` 的重試無退避、無 jitter,且 `Request` 物件跨 attempt 重用

**位置**:`copycat/server/breadth_fetch.py:66-97`

```python
req = Request(url, headers={"Authorization": f"Bearer {token}"})   # 迴圈外建一次
last: Exception | None = None
for attempt in range(_ATTEMPTS):
    try:
        with urlopen(req, timeout=timeout) as resp:                # 同一個 req 重用
            payload = json.load(resp)
    ...
    logger.warning(...)          # ← 立刻進下一圈,零 sleep
raise BreadthFetchError(...)
```

**影響**:
- `IncompleteRead`(專案已實錄:2026-09-02「4.5MB 全市場回應截斷」)觸發時,**立刻**重下載
  整份 4.5 MB。上游正在抽風時,立即重打命中率低而成本加倍。
- 上游 5xx / 連線重置時同理。
- 兩次 60 s timeout 背靠背 = 120 s 佔住一條 worker(B09-06)。
- `Request` 跨 attempt 重用:`do_request_` 會對它 `add_unredirected_header`,重用在 stdlib
  下實務上可行,但不是文件保證的用法。

**修法**:attempt 間加 `time.sleep(0.5 * 2**attempt + random.uniform(0, 0.3))`,
`_ATTEMPTS` 提到 3。注意 `_get_rows` 是同步函式跑在 worker thread,用 `time.sleep` 正確
(會釋放 GIL);**不要**改成 `asyncio.sleep`。

**風險**:低。402 不重試的既有語意(`breadth_fetch.py:73-74`)必須保住 —— 那是刻意的,
配額用盡重打只會燒更多。

**Effort**:S

---

### B09-13 `medium` / `data-structure` — `DailyIndex.load` 52 MB CSV → 3.5 s;這是本區唯一正當的 parquet/duckdb 候選

**位置**:`copycat/data/daily.py:30-50`

```python
@classmethod
def load(cls, data_dir: Path) -> DailyIndex:
    rows: dict[str, list[_DayRow]] = {}
    with (data_dir / "daily" / "prices.csv").open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):     # ~1M 列 × 8 欄,每列建一個 dict 再建一個 dataclass
            ...
```

**證據**:實測 `DailyIndex.load(Path('data'))` = **3,523 ms**;52.1 MB / 2,044 檔 / 平均 509 個日期。

**影響**:目前只有離線回測 / replay CLI 在用(server 不載),所以**現況不是熱路徑**。
但若採納 B09-01(server 改讀本地 EOD store),這支就會變成 server 啟動路徑的一環,
3.5 s 會直接加到 boot 時間上 —— 而 `breadth_engine.start()` 的設計原則明寫
「**零網路 IO**(restore 本地檔 + 起 poll task 即返回)」。

**修法(若 B09-01 採納)**:不要沿用 `prices.csv` 全載模式。改成**按日期分檔**
(`data/daily/eod-YYYY-MM-DD.json`,每檔 ~2,000 列 × 4 欄 < 200 KB),要哪天讀哪天,
21 日窗 = 21 次小讀,總計 < 50 ms。**這比上 parquet 更符合「零相依 + 按日期存取」的形狀。**

若真要上欄式存量(整庫查詢 / 回測特徵工程),`polars.read_parquet` 對同樣 1M 列 × 8 欄
預期 < 100 ms(**推測,未實測**),但那是 B10/回測區的事,不是本區。

**風險**:改 `prices.csv` 的存放格式會動到 `data/backfill_finmind.py`、`backtest/` 全鏈。
**建議:不要改 `prices.csv`,另建按日分檔的 EOD store,兩者並存。**

**Effort**:M

---

### B09-14 `low` / `algorithmic` — `dedup_sector_map` / `build_type_map` / `build_name_map` 各自排序同一份 4,300 列(共 4 次 sort)

**位置**:`copycat/market_breadth.py:111`、`:126`、`:147-151`

```python
def build_name_map(rows): sorted_rows = sorted(rows, key=lambda r: r.get("date") or "", reverse=True)
def build_type_map(rows): sorted_rows = sorted(rows, key=lambda r: r.get("date") or "", reverse=True)
def dedup_sector_map(rows):
    filtered = [r for r in rows if r.get("type") in ("twse", "tpex")]
    sorted_rows = sorted(sorted(filtered, key=...industry...), key=...date..., reverse=True)  # 兩段
```

**實測**:2.32 + 0.88 + 0.64 = **3.84 ms**,一天跑 1–2 次。

**判定:不要動。** 合併成一次 sort 省 ~2 ms/天。三支各自獨立的可讀性與
`tests/fixtures/breadth_parity.json` 的 tie-break 語意(`dedup_sector_map` docstring 明寫
「stable 兩段排序」)值錢得多。列在這裡只為了說明「已經檢查過、確認不值得」。

**Effort**:—(不做)

---

### B09-15 `medium` / `render` — `-> dict` 回傳註解是一個沒人寫下來的效能契約:拿掉會讓 breadth rows 序列化慢 9×

**位置**:`copycat/server/app.py:1940`

```python
@app.get("/api/market/breadth/rows")
async def market_breadth_rows(request: Request) -> dict:     # ← 這個 `-> dict` 是效能契約
```

**證據**(TestClient,1,954 列 / 559 KB payload):

```
/annotated   len= 559316  p50=   4.46 ms  min=   3.86 ms     # async def f(...) -> dict
/raw         len= 559316  p50=  41.26 ms  min=  36.93 ms     # async def f(...)   無註解
```

原因:FastAPI 自 0.89 起會把回傳型別註解當 `response_model`,序列化改走 **pydantic-core 的
Rust serializer**;無註解時 fall back 到純 Python 的 `fastapi.encoders.jsonable_encoder`
(單獨量測:**35.17 ms**,而 `json.dumps` 只要 3.83 ms)。

**影響**:
- 現況已在快路徑(4.5 ms),**不需要換 ORJSONResponse,也不需要動 `rows_state()`**。
- 但任何人「順手清掉沒用的型別註解」就會讓這條 route **在 event loop 上多花 37 ms**,
  每 10 s 一次,零錯誤訊號。全站其他 `-> dict` route 同理。

**修法**:不改 code,把這件事寫進 `backend-conventions` skill 的一行:
「route 的回傳型別註解不可省 —— 它決定走 pydantic-core 還是 `jsonable_encoder`(實測 9×)」。

**Effort**:S(純文件)

---

### B09-16 `low` / `allocation` — `rows_state()` 每次 REST 請求重建 1,954 個 dict

**位置**:`copycat/server/breadth_engine.py:302-316`

```python
for row in self.rows:
    ...
    rows_out.append({**row, "streak": streak, "streak_capped": capped})
```

**實測:0.35 ms**(1,954 列)。每 10 s 一次(tab active 時)。

**判定:不要動。** 這是典型的「看起來像問題其實不是」—— 0.35 ms 相對於同一條路徑上
4.5 ms 的序列化是 8%。把 `streak` 併進 `compute_breadth` 的產出來省掉這一步,
會把「連板算術只在 `rows_state()`(單一真相)」這個明寫的設計原則(`:281`)打破,
換 0.35 ms。不划算。

**Effort**:—(不做)

---

### B09-17 `low` / `architecture` — breadth 與 screen 各自打一次 `fetch_disposition`,同日同資料兩份快取

**位置**:`breadth_engine.py:486` 與 `screen_engine.py:274`,都呼叫
`breadth_fetch.fetch_disposition(token, today)`,參數完全相同(`app.py:1040` / `:1122` 同一支函式)。

**影響**:每日多 1 次請求 + 1 次 TLS 握手 + ~0.1 MB。可忽略。

列在這裡是因為:做 B09-01 的 `EodStore` 時,順手把 `disposition` / `stock_info` 也收進
同一個「當日對照表快取」層,成本趨近於零,且能讓兩個引擎的處置股名單**保證一致**
(目前兩邊各自 parse,理論上可能在跨日邊界拿到不同的名單)。

**Effort**:S(併進 B09-01)

---

### B09-18 `low` / `algorithmic` — `limit_streaks` 的演算法複雜度(任務指定問題 #5)

**位置**:`copycat/limit_streaks.py:42-84`

```python
def compute_day_limitups(rows) -> set[str]:      # O(n),n = 45k 列
    for row in rows:
        if not isinstance(sid, str) or classify_stock_id(sid) is not None: continue
        ...
        if round(close * 1000) == limit_up_milli(round(prev_close * 1000)): out.add(sid)

def compute_prev_streaks(day_sets) -> dict[str, int]:    # O(W × |candidates|)
    candidates = set(day_sets[0])                        # |candidates| ≈ 20–40 檔
    streaks = {sid: 1 for sid in candidates}
    for older in day_sets[1:]:                           # W = 10
        candidates &= older
        if not candidates: break
        for sid in candidates: streaks[sid] += 1
```

**複雜度**:`compute_day_limitups` = O(n) 單趟,無巢狀;`compute_prev_streaks` =
O(W × |D₀|) 且有 early break,W=10、|D₀| ≈ 22–38(log 實錄)。

**實測**:`compute_day_limitups(45k)` = 7.3–24.1 ms;`compute_prev_streaks(10 日)` = **0.00 ms**。

**判定:演算法完全正確,不要動。** 交集遞進是這個問題的最佳解,而且已經有 early break。
`compute_day_limitups` 的 O(n) 常數項來自 `classify_stock_id` 的 `strip()` / `isdigit()` /
`startswith("00")`,對 43k 個 5 位權證代號在 `len(s) != 4` 就短路 —— 已經是最便宜的順序。

**Effort**:—(不做)

---

### B09-19 `low` / `algorithmic` — `hard_candidates` 的 `series` 中間表建 42k 個 tuple + dict-of-dict

**位置**:`copycat/screening.py:121-132`

```python
series: dict[str, dict[int, tuple[float, float | None, float | None]]] = {}
for idx, (_, rows) in enumerate(days):              # 21 日
    for row in rows:                                 # ~2,000 檔
        ...
        series.setdefault(sid, {})[idx] = (close, spread, volume)
```

**複雜度**:O(D × N) = 21 × 2,000 = 42,000 次 `setdefault` + tuple 建構,
再加外層 O(N × D) 的連乘迴圈。**實測 63.0 ms**,每天一次。

**判定:不要動。** 這是本區**唯一**看起來像 numpy/polars 候選的東西,但它一天跑一次 63 ms。
換成 polars 的 `pl.DataFrame.pivot` + `cum_prod` 大概能到 5 ms —— 省 58 ms/天,
代價是一個 60 MB 的 binary 相依 + `tests/fixtures/breadth_parity.json` / screening 測試全要重驗
浮點位元等值。**這筆交易是虧的。**

唯一該注意的:它在 event loop 上(見 B09-08),包一次 `to_thread` 即可。

**Effort**:—(不做,只做 B09-08 的 to_thread)

---

### B09-20 `low` / `concurrency` — `mis.py` 的 `_fail_streak` 是 module-level global

**位置**:`copycat/server/mis.py:23-24`、`:42`、`:75`

```python
_WARN_AFTER = 3
_fail_streak = 0          # 模組層可變全域

def fetch_otc_snapshot(fetcher=urlopen):
    global _fail_streak
```

**影響**:目前只有一個 index engine 在用,實務無害。但它是從多條 worker thread
(`asyncio.to_thread`)進來的**非原子** read-modify-write —— 對照 `trading_calendar.py:97`
的 `_warn_lock`(同一個專案為了完全一樣的問題加了鎖,並在註解裡寫明理由:
「沒有它時節流不成立 …「這行只該出現一次」這個判準就不能用了」)。

`mis.py` 沒有那把鎖。**不是效能問題**,是可觀測性判準問題,且與專案既有慣例不一致。

**Effort**:S

---

## 5. 工具選型建議與取捨

| 工具 | 用在哪 | 解決什麼 | 預期收益 | 代價 | 建議 |
|---|---|---|---|---|---|
| **`httpx` (AsyncClient)** | `breadth_fetch._get_rows`、`oi_levels._fetch_rows` | 連線池 + 自動 gzip + 原生 async(拿掉 to_thread)+ 四段 timeout | 握手 −99%(~150 s/日)、傳輸 −80%(~0.9 GB/日)、worker 佔用歸零 | **已裝在 `.venv`(dev extras)**;要搬進 `[live]`;打破 `dependencies = []` 哲學;取數層 `Callable` 型別別名要改 awaitable;**要進關機預算契約** | **建議導入(進 `[live]` extras)** |
| **`orjson`** | `breadth_fetch._get_rows` 唯一解碼點 | 大 payload 解碼慢且全程持 GIL | 37 ms → ~7–12 ms 的 loop 全凍(推測 3–6×) | binary wheel(Windows 有官方 wheel);新相依 | **有條件導入**:先量測證明比例(§7),再進 `[live]` + stdlib fallback |
| **`msgspec`** | 同上,且可直接 decode 成 struct | 解碼 + 省掉 45k 個 dict 的建構 + 取代 `shrink_rows` 一整趟 | 比 orjson 再快一截,記憶體大幅降 | 要定義 schema(FinMind 欄位會變 → schema 要容錯);比 orjson 侵入性高 | **有條件導入**:只在 B09-02 量測顯示解碼真的是 bottleneck 時 |
| **stdlib `gzip` + `Accept-Encoding` header** | 同上(不換 httpx 的話) | 傳輸量 5.5× | ~0.9 GB/日 | **零新相依**,~15 行 | **建議導入**(若不採 httpx,這是最佳 CP 值改動) |
| **`polars` / `numpy`** | `market_breadth` / `screening` / `limit_streaks` | 純函式加速 | 最多省 ~2–3 s/**天** | 60 MB+ binary 相依;`breadth_parity.json` 全管線 oracle 要重驗浮點等值;毫元整數判定(`market.limit_up_milli`)在 numpy float 下語意會變 | **不建議** —— 實測計算只佔 screen 一輪的 3.4%,bottleneck 在網路 |
| **`duckdb` / parquet** | `data/daily/prices.csv`(52 MB → 3.5 s 載入) | 離線回測的整庫查詢 | 3.5 s → < 0.3 s(推測) | 新相依;動到 `backfill_finmind` + `backtest/` 全鏈 | **不建議在本區**;是 B10/回測區的題目。本區要的是「按日分檔小 JSON」不是欄式庫 |
| **`ORJSONResponse`(FastAPI)** | `/api/market/breadth/rows` | route 序列化 | **零** —— 實測已在 pydantic-core 快路徑(4.5 ms) | — | **不建議**(見 B09-15) |
| **`uvloop`** | event loop | — | **Windows 不支援**(uvloop 是 libuv + Unix only) | — | **不可用**(執行環境硬限制) |
| **專屬 `ThreadPoolExecutor`** | FinMind / MIS IO | 與 TC4 / capital / signal 同池競爭(20 worker) | 失效域隔離 | 要進關機序列 | **建議導入**(若不採 httpx async;採了則只剩 MIS 需要) |

### 建議的執行順序(收益/風險比排序)

1. **B09-10**(加耗時 log)—— 零風險,且是後面所有改動的驗收判準。**先做這個。**
2. **B09-03**(stdlib gzip)—— 零新相依,~15 行,省 ~0.9 GB/日。
3. **B09-04**(screen 整體 deadline)—— 5 行,把最壞情況擋在盤外。
4. **B09-01**(本地 EOD store)—— 本區最大單筆收益;做完之後 B09-07 就不必做了。
5. **B09-08**(純函式進 to_thread)—— S 級,清掉「以為在背景其實在前景」。
6. **B09-11 / B09-12 / B09-20**(小修)。
7. **B09-05**(httpx)—— M 級,要動關機預算契約;等 1–6 的量測數字出來再決定是否值得。
8. **B09-02**(orjson/msgspec)—— 等 B09-10 的 decode 計時證明它是 bottleneck 才做。

---

## 6. 這裡不要動(反向清單)

| 位置 | 為什麼不要動 |
|---|---|
| `market_breadth.compute_breadth`(5.4 ms / 10 s) | 0.05% duty cycle。丟 `to_thread` 的 context switch 成本比省下的多。 |
| `market_breadth.dedup_sector_map` / `build_type_map` / `build_name_map`(4 次 sort,3.8 ms/天) | 合併省 2 ms/天,換掉 tie-break 語意的可讀性與 parity oracle 的明確性。不划算。 |
| `limit_streaks.compute_prev_streaks`(實測 0.00 ms) | 交集遞進 + early break 已是最佳解。 |
| `limit_streaks.compute_day_limitups` 的 `classify_stock_id` 短路順序 | 已經是最便宜的順序(`len != 4` 對 43k 權證先短路)。 |
| `screening.hard_candidates`(63 ms/天) | 唯一看起來像 polars 候選的東西,但一天一次。換 polars = 60 MB 相依 + 浮點等值重驗,省 58 ms/天。虧的。 |
| `breadth_engine.rows_state()` 的 dict 重建(0.35 ms) | 併進 `compute_breadth` 會打破「連板算術單一真相」的設計原則,換 0.35 ms。 |
| `app.py` 各 route 的 `-> dict` 回傳註解 | **千萬不要清掉** —— 它決定走 pydantic-core(4.5 ms)還是 `jsonable_encoder`(41 ms)。見 B09-15。 |
| `mis.py` 的 payload 處理 / `_TIMEOUT=5` / 單次不重試 | 非契約公開端點,已明寫「可能無預警壞,失敗 None 降級」。payload 微小,加壓縮/重試只增加打擾上游的風險。 |
| `breadth_fetch` 的 **402 不重試** 語意 | 刻意設計。配額用盡重打只會燒更多且必然同樣失敗。任何重試改動都要保住這條。 |
| `screen_engine` 的 **fail-fast 順序**(當沖名單 → 處置股 → 21 日 EOD) | `pr-211 F-02` 刻意設計,把失敗路徑從 22 個請求砍到 1 個。實錄 09-11 前五次 attempt 各只花 1 個請求就是這個設計在生效。並行化時必須保住。 |
| `uvloop` | Windows 不支援。 |

---

## 7. 量測方法(要證明快慢,該怎麼量)

### 7.1 已經做過的(腳本在 `scratchpad/arch-scan/`)

```powershell
# 純函式 + payload 解碼成本
.venv\Scripts\python scratchpad\arch-scan\bench_b09.py     # fixture 驅動
.venv\Scripts\python scratchpad\arch-scan\bench_b09b.py    # 45k 列合成 EOD
.venv\Scripts\python scratchpad\arch-scan\bench_b09c.py    # jsonable_encoder vs json.dumps
.venv\Scripts\python scratchpad\arch-scan\bench_b09d.py    # TestClient 端到端 route 序列化
.venv\Scripts\python scratchpad\arch-scan\bench_b09f.py    # event loop 停頓(sleep(0) 心跳)
```

`bench_b09f.py` 是本次最關鍵的方法:用 `await asyncio.sleep(0)` 當心跳(**不能用
`sleep(0.001)`** —— Windows timer 解析度 15.6 ms 會把訊號吃掉,實測 baseline p50 就是 15.52 ms),
量「to_thread 裡的工作讓 event loop 停多久」。

### 7.2 還需要做的

**(a) FinMind 是否支援 gzip(B09-03 的前提)** —— 花 1 個配額請求:

```powershell
.venv\Scripts\python -c "
import urllib.request, os
t = os.environ['FINMIND_TOKEN']
req = urllib.request.Request(
    'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo',
    headers={'Authorization': f'Bearer {t}', 'Accept-Encoding': 'gzip'})
with urllib.request.urlopen(req, timeout=30) as r:
    print(dict(r.headers))    # 看 Content-Encoding
"
```

**(b) 真實 EOD payload 大小 / 解碼時間**(本報告的 4.5 MB 是引自檔內註解與 09-02 事故實錄,
我的合成 payload 是 9.3 MB / 203 bytes per row,偏大)—— 直接在 `_get_rows` 加 B09-10 的計時 log,
跑一個交易日就有 31 筆真實樣本。

**(c) orjson / msgspec 的實際比例** —— 在**另建**的 venv 裝(不要污染 `.venv`):

```powershell
py -3.13 -m venv %TEMP%\bench-venv
%TEMP%\bench-venv\Scripts\pip install orjson msgspec
%TEMP%\bench-venv\Scripts\python scratchpad\arch-scan\bench_b09f.py   # 加 orjson 分支
```

**(d) 共用 executor 的排隊證據(B09-06)** —— 在 `app.py` lifespan 加一條每 30 s 的探針:

```python
ex = asyncio.get_running_loop()._default_executor
logger.info("executor 佇列 %d / 執行緒 %d", ex._work_queue.qsize(), len(ex._threads))
```

盤中 `grep "executor 佇列" logs/server-*.log | awk '$N > 0'` 命中即證實排隊。

**(e) 改動前後的驗收判準(盤後 grep)**:

| 改動 | 判準 |
|---|---|
| B09-03 gzip | 新 log 行的 `MB` 欄降到 ~1/5.5 |
| B09-01 EOD store | `grep "breadth streak" logs/…` 的首尾時戳差 39 s → < 5 s;`盤前篩選` 成功行與該輪首次 WARNING 的時戳差 53 s → < 8 s |
| B09-04 deadline | 交易日 `grep "盤前篩選.*今日放棄"` 若出現,時刻必 < 09:00 |
| B09-02 orjson | 新 log 的 `decode` 欄 37 ms → < 12 ms |
| B09-08 to_thread | 無直接 log;以 `bench_b09f.py` 的 loop 停頓迴歸測試釘 |

### 7.3 現場探針(不改 code)

```powershell
# 每次全市場 EOD 的 wall time(靠兩行 log 的時戳差,現況唯一可得的量測)
Select-String -Path logs\server-*.log -Pattern "breadth streak 2026" | Select-Object -First 12

# 盤前篩選一輪的 wall time
Select-String -Path logs\server-*.log -Pattern "盤前篩選"

# 確認 FinMind / MIS 的握手成本(不打 API,零配額)
.venv\Scripts\python -c "import socket,ssl,time; ..."   # 見本報告 §4 B09-05 的證據段
```

---

## 8. 這一區的硬約束(改造時不可違反)

1. **`dependencies = []` 的 stdlib-only runtime 哲學**(`pyproject.toml:6`)。任何新套件都應該進
   `[live]` extras,且核心純函式層(`market_breadth` / `limit_streaks` / `screening` /
   `trading_calendar`)**必須維持零第三方相依** —— 它們被 CLI / 回測 / 測試在沒有 `[live]` 的
   環境下 import(`finmind_token.py:4-5` 明寫這個理由:「conftest 是每一條測試都載的模組,
   中和 FinMind 憑證時不該被迫拉進 fastapi」)。
2. **`tests/fixtures/breadth_parity.json`(1.14 MB)全管線 oracle**:`market_breadth` 的
   `dedup_sector_map` tie-break、`assemble_universe` 兩步順序、`compute_breadth` 的五桶互斥
   都被它釘住。換任何數值/排序實作都必須逐位元通過。
3. **「盤前篩選」群組名前後端同字面**(CLAUDE.md §4):產生點
   `screen_engine.SCREEN_GROUP`,讀者 = 前端 `lib/constants.ts::SCREEN_GROUP_NAME`,
   由 `test_screen_group_name_parity_with_frontend` 直讀前端字面釘住。重構 screen_engine 時
   這顆常數不可改名、不可搬走。
4. **自選上限常數多邊同值**(CLAUDE.md §4,現值 150):`stock_watchlist.WATCHLIST_LIMIT` →
   `fit_group_codes`(screen 的 nightly 截位)→ 前端 `constants.ts` → bot `_ERROR_TEXT`。
   screen 改動不可繞過 `fit_group_codes`。
5. **關機預算三方同源**(CLAUDE.md §4):`shutdown_budget.run_grace_secs()` /
   `run.ps1` / `__main__.py` / `app.py` lifespan 的並行 lane 形狀。
   **新增任何要在關機時 await 的資源(httpx AsyncClient、專屬 executor)都是改契約**,
   要同步改 `TC4_LANE_DEPTH`,`tests/server/test_shutdown_budget.py` 有字面 parity 測試。
6. **FinMind Sponsor 配額 6,000 req/hr**(skill `finmind-conventions`)。目前日用量 ~1,716 次,
   餘裕很大,但並行化時要留意 burst。
7. **402 不重試**(`breadth_fetch.py:13-15`、`:73-74`):breadth 走 `quota_backoff_secs` 長退避,
   screen 當天直接放棄。任何重試策略改動必須保住。
8. **失效域隔離(SC-3)**:`breadth_engine` 檔頭明寫「完全不碰 TC4 / ZMQ,`start()` 零網路 IO」。
   引入共用 client / executor 時不可讓 FinMind 的失效傳導到 TC4 系。
9. **Windows-only host**:`uvloop` 不可用;`os.replace` 原子寫在防毒下有尾延遲;
   `asyncio` 預設 `ProactorEventLoop`。
10. **API error JSON shape `{"detail": {"error": "<code>"}}`**(CLAUDE.md §4)——
    breadth 兩支 route 走「恆 200 三態」不用 503,這是刻意的(`app.py:1918-1926`),改不得。
11. **序列檔 / 快取的 `_version` 欄**:`breadth_engine._FILE_VERSION`、`_STREAK_FILE_VERSION`、
    `screen_engine._CACHE_VERSION`。任何落檔格式改動都要 +1(CLAUDE.md §4「Cache version bump」)。

---

## 9. Open questions(查不出來 / 需要 user 或 profile)

1. **FinMind 是否支援 gzip?** B09-03 的收益全押在這上面。要花 1 個配額請求探(§7.2 (a))。
   若不支援,B09-03 降為「零收益、零風險」,B09-01 與 B09-05 的重要性相對升高。
2. **真實 EOD payload 到底幾 MB?** 檔內註解說「MB 級」、09-02 事故實錄說 4.5 MB,
   而 log 只記列數(45k–46k)。我的合成 payload 是 9.3 MB。差 2× 會讓 B09-02 的
   loop 停頓從 37 ms 變 74 ms —— 這個數字直接決定 orjson 值不值得。
3. **user 要不要為了效能打破 `dependencies = []`?** 這是哲學決策不是技術決策。
   我的建議:純函式層絕對不碰;`[live]` extras 可以加 httpx(已經在 venv 裡)。
   orjson / msgspec 等量測數字出來再談。
4. **盤前篩選的名單延遲(08:00 → 08:51)是 FinMind 上游的問題,不是本系統的效能問題** ——
   實錄五次 attempt 全是「當沖名單尚無資料」。任何本地優化都救不了這一段。
   user 是否接受「名單 08:51 才出」?若不接受,方向是改資格判準(例如改用前一交易日名單)
   而不是改效能。
5. **`data/daily/prices.csv` 停在 2026-07-17 是刻意的還是忘了跑?**
   B09-01 的修法要不要復用它,取決於 user 對這份存量的意圖。
6. **breadth snapshot 的 10 s 輪詢間隔是否還有降的空間/需求?**
   目前 `poll_secs = 10.0`。若未來要拉到 2–3 s(量化交易情境),B09-03/B09-05 就從
   「省頻寬」升級成「可行性前提」——1,680 次/日會變成 8,400 次/日,握手成本 150 s → 750 s,
   傳輸 0.9 GB → 4.5 GB,而 FinMind 配額 6,000/hr 也會開始緊(8,400/4.7 h ≈ 1,790/hr,仍在額度內但
   餘裕從 1/3 降到 1/3 以下需重算)。
7. **是否有人實際在看「台股綜合」tab?** `/api/market/breadth/rows` 的 10 s 輪詢只在 tab active 時發生。
   若實務上很少開,HP-2 的優先序可以再降。
