# B08 — K 線聚合 / 疊圖計算 / OI 撐壓 / 市場價格工具

> 掃描日期 2026-09-13 · 工作樹 `C:\side-project\copycat` @ master `caca1d30`
> 範圍:`copycat/server/bars.py` (723) / `copycat/server/overlay.py` (60) /
> `copycat/server/oi_levels.py` (292) / `copycat/market.py` (70),
> 以及它們在 `app.py` 的 route、`live/stock_source.py` 的取數層、
> 前端對應側 `lib/candle.ts` (354) / `lib/live-last-bar.ts` (133) /
> `lib/futures-overlay.ts` (75) / `lib/stock-tick.ts` (184) / `lib/candle-viewport.ts` (73)。

本報告所有數字都是**在本機實測**的(Python 3.13.13 / FastAPI 0.139.2 / pydantic 2.13.4 /
Node 24.13),腳本留在 `scratchpad/bench_bars.py`、`bench_oi.py`、`bench_col.py`、`bench_front.mjs`。
沒實測的一律標「推測」。

---

## 0. 一句話結論

**這個區塊的 CPU 不是問題,IO 拓樸才是。**
`bars.py` 的兩段式快取、`overlay.py` 的 CDP/MA、`market.py` 的毫元整數 tick 表、
`oi_levels.py` 的 pivot,實測成本全部落在「每分鐘 ~5 ms」或「每天一次 ~200 ms」這個
量級,**沒有一條值得換 numpy / polars**。真正要動的是三件事:

1. **群組圖牆掛載時最多 150 發 `/api/stock/overlay`,每發一次 TC4 DK 往返,而 TC4 那一側
   的併發實際上是 1**(`api.lock` 粒度 = 單次 REQ、範圍 = 同一 source)。`overlay_sem = 4`
   只限執行緒不限鎖 → head-of-line,整牆疊線要幾十秒才長出來,期間還跟 tick 回補搶鎖。
2. **`BarsCache._hist` 沒有股號維度的淘汰**。實測 30 日 1 分 K = 2.73 MB / 檔;
   瀏覽 150 檔 ≈ 410 MB,瀏覽 300 檔 ≈ 820 MB,而它是一個整天不重啟的 process。
3. **前端 `StockChart` 的分 K 聚合掛在 `accum.minutes` 上,每 0.1 s 一則 ticks 打包就
   對 8,100 根重跑一次**(實測 1.9 ms/次),下游 `ChartStatic` 的 memo 全穿 →
   700 根蠟燭 × 3 個 SVG 節點每 0.1 s 重建。這是本區塊**唯一真正的熱路徑**。

要「改成量化交易系統」的話,本區塊的終局是第 4 點:**建一層本地歷史 store**
(DuckDB / Parquet),讓日 K / 分 K 的歷史段不再向 TC4 要。那一步會一次解掉 1、
`build_*` 缺 single-flight、以及當日段 30 s TTL 的重複往返。

---

## 1. 架構地圖

### 1.1 後端層次

```
route (app.py)                engine (to_thread)          source (blocking ZMQ)
──────────────────────────    ────────────────────────    ─────────────────────────────
GET /api/stock/bars/{code}
  tf=D  → build_daily ─────┐
  tf=1  → build_minute ────┼→ StockEngine.bars_range ───→ StockQuoteSource
                           │    (asyncio.to_thread)          .fetch_bars_range
GET /api/market/bars/{key} │                                   ├ tf=1 → _collect_history("1K") → parse_1k_bars
  tf=1  → build_minute ────┤                                   └ tf=D → _next_dk_start → _collect_history("DK")
  tf∈DWM→ build_period ────┤   IndexEngine.bars_range                    → parse_dk_bars
                           │   FuturesEngine.bars_range                  → (空) fallback 1K → aggregate_1k_to_daily
GET /api/stock/overlay/{c} │
  → overlay_cache ─(miss)──┼→ StockEngine.daily_bars ───→ .fetch_daily_bars(n=25)
     → build_overlay       │   (semaphore 4 + wait_for)      → DK 40 日窗;空則 1K fallback
                           │
GET /api/index/overlay ────┘   (走 build_period 的 IX0001|L 格,再轉 DailyBar → build_overlay)

GET /api/futures/oi-levels → fetch_oi_levels → to_thread(_fetch_rows: stdlib urllib → FinMind)
                                              → _pivot → OiLevelsCache(正向永久 / 負向 300 s)
```

`copycat/market.py` 不在這條鏈上 —— 它是**純函式工具**,被三類讀者用:
- **每 tick**:`live/stock_state.py::_fold_vp`(`snap_down_milli`)、
  `live/signal_state.py:396`(CDP rearm 的 `tick_size_milli`)。
- **每筆下單前**:`server/capital_api.py:147`(檔位合法性)。
- **離線 / EOD**:`market_breadth.py`、`limit_streaks.py`、`screening.py`、`backtest/*`。

### 1.2 `BarsCache` 的四個字典(bars.py:236-253)

| 欄位 | key | value | 淘汰 |
|---|---|---|---|
| `_hist` | `(f"{code}:{session}", "YYYY-MM-DD")` | `list[Bar]` | **只按日期**(`floor = today − 60d`) |
| `_today` | `(ck, today)` | `(寫入 monotonic, bars, status)` | 日期 **+ TTL**(30 s / 空 15 s) |
| `_daily` | `(code 或 f"{code}\|L", today)` | `_DailyEntry(bars, tag, pre_final_written_at)` | 只留今天 |
| `_empty` | `(ck, tf, days)` | `(寫入時刻, status)` | TTL 15 s |

`_DailyEntry`(bars.py:214-232)是 W3-B1 那批 refactor 的產物 —— 把原本三份同鍵 dict
收成一格。**這個 refactor 是對的,但它解的是正確性問題(三處同步漂移)不是效能問題**;
查詢複雜度前後都是 O(1) dict 查找,記憶體反而多一個 dataclass header(實測 `_DailyEntry`
= 3 欄非 slots,+56 B/格,格數 = 開過圖的 code 數,可忽略)。

### 1.3 資料流:一次「分 K 請求」的完整成本

前端 `useStockBars` 交易時段每 **60 s** 打一發 `?tf=1&days=30`:

```
build_minute(code, days=30, today)
├ cache.prune(today)              ← 四個 dict 全表掃(見 B08-08)
├ empty_status 命中? → 直接回空
├ 歷史段 start..yesterday
│  ├ hist_missing()               ← 逐日曆日查 dict,30 次
│  ├ _possible_data_days()        ← 日曆過濾(擋掉週日這種「永久 missing」黑洞)
│  ├ [有缺] await fetch(lo..hi)   ← to_thread → TC4 SubHistory + 分頁收割 ← **唯一的真成本**
│  ├ put_hist_range()             ← 攤平進 per-day memo,實測 8,100 根 0.75 ms
│  └ hist_range()                 ← 重組 30 天清單,實測 0.03 ms
├ 當日段 today_get()(TTL 30 s)
│  └ [過期] await fetch(today..today) ← **每次輪詢必打一次 TC4**(TTL 30 < 輪詢 60)
└ worst_status + 回 BarsResult
```

穩定態(歷史段全 memo 命中)每 60 s 只有**一次** TC4 當日段往返 + ~5 ms 的 Python/序列化。
**這是刻意設計而且設計得對**(change-spec R2-1/R2-2 的兩段式),不要拆。

---

## 2. 熱路徑逐條(依真實頻率排序)

### HP-1 前端 `StockChart` 分 K 聚合 — **每 0.1 s**(交易時段、分 K 模式)
`frontend/src/components/stock/StockChart.tsx:196-203`

```ts
const bars = useMemo(() => {
  const raw = data?.bars ?? [];
  if (liveMinutes !== null) {
    return aggregateBars(mergeLiveMinuteBars(raw, liveMinutes, liveToday, nowMinute), minutesOf(mode));
  }
  ...
}, [data, mode, liveMinutes, liveDay, dayOpen, liveToday, nowMinute]);
```

`liveMinutes = accum.minutes`,而 `accum` 的 identity 每收到一則 `ticks` 打包就換
(CLAUDE.md §4「個股逐筆 = `ticks` 打包訊息」:`tick_flush_secs` 0.1 s)。
→ **每 0.1 s** 重跑 `mergeLiveMinuteBars`(複製 8,100 元素陣列 + 270 keys 排序)
+ `aggregateBars`(8,100 根建新物件)。

實測(Node 24,8,100 根,n=5):

| 動作 | min | median | p95 |
|---|---|---|---|
| `aggregateBars(bars, 1)`(純 spread) | 0.003 ms | 0.006 ms | 0.031 ms |
| `aggregateBars(bars, 5)` | 1.453 ms | **1.900 ms** | 3.042 ms |
| `mergeLiveMinuteBars + aggregateBars(5)` | 1.571 ms | **1.897 ms** | 2.724 ms |

1.9 ms × 10 Hz = **19 ms/s ≈ 2% 單核**,單看數字不嚇人。真正的代價在下游:
`bars` identity 一換 → `CandleChart:475` 的 `{shown, g, ma5, ma20}` useMemo 重算 →
`ChartStatic` 的 `memo` 全穿 → 最多 **700 根蠟燭 × 3 個 SVG 節點**每 0.1 s 重 diff。
`CandleChart.tsx:403-404` 的註解自己寫了這件事(「每次 render 給新 array 會打穿
ChartStatic 的 memo(最多 700 根蠟燭 × 3 個節點跟著重建)」)—— 只是那句話針對的是
`extraSeries`,而 `bars` 本身現在就是那個每 0.1 s 換 identity 的來源。

**React reconciliation 的實際毫秒數未量**(需要 DevTools trace,本次唯讀掃描沒跑)—— 標推測。

### HP-2 `market.py` tick 表查找 — **每 tick**(~300/s 全市場聚合估計)
`copycat/market.py:15-19`(`_tick_milli`,線性掃 5 段)

實測(Python 3.13,2,000,000 次):

| 呼叫 | ns/call |
|---|---|
| `tick_size_milli(23_450)`(第 2 段命中) | 102.6 |
| `tick_size_milli(1_200_000)`(掃完 5 段 + fallback) | 153.6 |
| `snap_down_milli(23_450)` | 139.8 |
| `limit_up_milli(23_450)` | 186.8 |

即使每秒 10,000 次呼叫也只有 1.4 ms/s。**這是本區塊最不需要動的東西。**

### HP-3 `build_minute` / `build_daily` / `build_period` — **每 60 s / 每開圖**
只有主圖(`StockChart` / `MarketChart` / `FuturesChart`)在打,**群組圖牆的卡片不打 K 線**
(它們吃 `group-state` 批次 + ticks 打包)。所以量級 = 開幾張圖就幾發/分鐘。

實測 route 端到端(FastAPI TestClient,payload = 8,100 根 + status,728,153 B):

| 路徑 | min | median |
|---|---|---|
| `json.dumps(payload)` 裸序列化 | 4.54 ms | 5.75 ms |
| route **有** `-> dict` 回傳註解 | **4.32 ms** | 5.60 ms |
| route **沒有**回傳註解 | **61.28 ms** | 67.98 ms |
| route 手動 `JSONResponse(content=...)` | 6.50 ms | 7.28 ms |

→ 見 B08-06,這是個埋著的地雷。

### HP-4 `/api/stock/overlay/{code}` — **群組圖牆掛載時最多 150 發**
`app.py:1484-1517` + `app.py:541-548`。cache 命中後整天不再打(`staleTime: Infinity`
+ `overlay_cache` 永久),但**第一次**是 150 發齊發。見 B08-02。

### HP-5 OI 撐壓 — **一天一次**
實測(合成 24,000 列 / 5.81 MB;程式碼註解稱真實 10 日窗 ≈ 7 萬列):

| 動作 | min | median |
|---|---|---|
| `json.loads`(5.81 MB) | 48.6 ms | 48.7 ms |
| `_pivot`(24k 列 → 120 檔履約價) | 2.13 ms | 2.55 ms |

外推到 7 萬列 ≈ `json.loads` 140 ms + `_pivot` 7 ms,**全在 `to_thread`、一天一次**。
真實 TXO 月契約 pivot 後的履約價數(本次合成 120 檔;真值需 prod 打一發才知道,標推測)。

### HP-6 `aggregate_period`(W/M K)— **每次 W/M 請求**
實測 1,500 根日 K → 月桶:**0.51 ms**。`build_period` 的 `_shaped` 在 cache 命中路徑
也重算(不 cache 聚合結果),但 0.5 ms/請求 × 1 請求/分鐘 = 記帳項,不是問題。

---

## 3. Findings

> 排序:先「真的會咬人」的,再「記帳」的,最後「不要動」的反向結論在 §5。

---

### B08-01 `BarsCache._hist` 沒有股號維度的淘汰,記憶體隨瀏覽過的股號線性成長
**嚴重度 high · 熱路徑 false(每請求一次)· effort M**

`bars.py:336-359`:

```python
def prune(self, today: _dt.date) -> None:
    """`_hist` / `_daily` 的成長來自**日期維度**(股號受 watchlist 50 檔上限約束)
    —— review P2-5。`_today` 從 round3 起會存空 entry,股號維度不再被「真的有今日
    資料的股號」約束(任何通過 `validate_code` 的字串請求一次就留一筆),所以
    除了日期還要按 TTL evict"""
    floor = (today - _dt.timedelta(days=DAYS_MAX * 2)).isoformat()
    for key in [k for k in self._hist if k[1] < floor]:
        del self._hist[key]
```

**docstring 的前提已經不成立兩次**:
(a) 自選上限 2026-09-01 起是 **150** 不是 50(CLAUDE.md §4「自選上限常數多邊同值」);
(b) 更關鍵 —— `/api/stock/bars/{code}` **不檢查 watchlist 成員資格**,只過
`_valid_code`(`app.py:1448-1452` → `validate_code`)。使用者用搜尋列點過的任何一檔,
只要開了分 K,30 日 1 分 K 就永久留在 `_hist` 直到日期滾過 60 天(而那時 process 早就
重啟了)。同一段 docstring 已經替 `_today` 認過這件事(「任何通過 `validate_code` 的
字串請求一次就留一筆」),但**修正只加在 `_today`,`_hist` 沒跟**。

**量級(實測)**:`tracemalloc` 對 8,100 根 Bar dict = **2,731,556 B**,
**337 B/根**(`sys.getsizeof(dict)` = 272,加上 `t` 字串)。

| 瀏覽過的股號數 | `_hist` 常駐 |
|---|---|
| 30 | 82 MB |
| 150(自選上限) | **410 MB** |
| 300(一天翻過的搜尋量,合理) | **820 MB** |

這是一個整個交易日不重啟的 process,而同一台機器還跑著 TC4 桌面 app + Chrome。

**修法**:`_hist` 加 LRU 上界(`OrderedDict` + `move_to_end`,上界取
「自選上限 × 安全係數」,例如 200 個 `(code:session)` 前綴)。**不要**改成
per-code TTL —— 歷史段「已完成交易日的 1K 不會再變」的永久性是整個兩段式設計的支點。
淘汰的單位要是 **`code:session` 前綴**而不是單一 `(code, date)` 格,否則會把同一檔的
30 天打成碎片、下一次請求又整段重抓。

**風險**:不動任何跨檔契約。會動到 `tests/server/test_bars.py` 的 prune 節(1,176 行,
已有 `today_entry_count()` 這種成長觀測鉤子,加一個 `hist_entry_count()` 同款即可)。

---

### B08-02 群組圖牆掛載 = 最多 150 發 overlay,而 TC4 那側實際併發是 1
**嚴重度 high · 熱路徑 false(每次進圖牆一次)· effort M**

`app.py:541-548` 的註解自己講清楚了問題,但解法只擋了一半:

```python
    # overlay 的 TC4 歷史取數節流(group-grid AD-5 amendment R5)。群組檢視的 `cdp`
    # 預設是開的 → 一進群組就對整組(上限 150 檔)同時打 `/api/stock/overlay`,而
    # `daily_bars` 走 `to_thread` 沒有上限、整組(上限 150 條)請求共用同一條 TC4 歷史通道。
    overlay_sem = asyncio.Semaphore(4)
```

證據鏈:
- `GroupGridView.tsx:454` 的 `GroupCard` → `StockIntradayChart`
- `StockIntradayChart.tsx:1035-1038`:`useStockOverlay(accum.code, ... && (toggles.cdp || toggles.ma))`
- `useStockOverlay.ts`:`staleTime: Infinity`,無批次端點 → **一檔一發**

`Semaphore(4)` 限制的是**同時進 `to_thread` 的協程數**,不是 TC4 那側的併發。
四條工作執行緒最後都要搶 `StockQuoteSource` 的同一把 `api.lock`
(`tc4.py:562` `api.lock.acquire(timeout=self._lock_timeout)`,粒度 = 單次 REQ、
範圍 = 同一 source)—— **實際併發 = 1**。而 `fetch_daily_bars` 一次不是一個 REQ:
`_next_dk_start` + `SubHistory` + 首頁 poll(退避 0.15 s 起)+ `iter_qry_pages` 收割,
每檔至少 3–5 個 REQ。

更糟的是**這把鎖跟盤中 tick 回補 / 訂閱 / `fetch_day_minutes` 是同一把**
(`stock_engine` 的 `_acquire` / `backfill` 全走 `to_thread` → 同一個 source)。
進圖牆 = 對 TC4 stock session 灌 150 檔 × 3–5 REQ 的 burst,期間新訂閱與回補全排隊。

**量級**:單檔 DK 往返未實測(需要 prod TC4)。以 `stock_source.py` 註解的
「實測有資料的標的首頁 <1s 內就備妥」取 0.3 s 保守估,150 檔序列化 ≈ **45 s**
整牆疊線才長齊 —— 標推測,但這個量級與「圖牆 CDP 線慢慢一條條冒出來」的既有觀感一致。

**修法(依優先序)**:
1. **批次端點** `GET /api/stock/overlay?codes=a,b,c`(對齊既有的
   `/api/stock/group-state?codes=` 慣例)。省的是 HTTP 往返,**不省 TC4 往返**。
2. **真正的解**:overlay 只需要「最後一根已完成日 bar 的 H/L/C」+「近 20 根 close」,
   這是**昨天就定案、今天永遠不會變**的資料。它應該來自本地歷史 store(見 B08-14),
   TC4 只在本地缺料時補。那時 150 檔 = 150 次本地查詢 = µs 級。
3. 短期止血:把 overlay 的 `daily_bars` 從**每檔一次 DK 往返**改成**一次區間取數攤平**
   —— TC4 的 `GETHISDATA` 是 per-symbol 的,做不到跨檔批次,所以 (3) 走不通。
   → **結論:短期只能做 (1) 減 HTTP 開銷,真解是 (2)。**

**風險**:批次端點是新增,不動既有契約;但 `/api/stock/overlay/{code}` 的降級語意
(逾時 → 全 null + 200 + **不寫 cache**)必須逐字帶到批次版,否則單檔逾時會把整批
寫成永久空(`overlay.py::OverlayCache.put` 的 don't-cache-empty 就是為這個)。

---

### B08-03 `build_daily` / `build_minute` / `build_period` 沒有 single-flight
**嚴重度 high · 熱路徑 false · effort S**

`bars.py:441-442` 自己承認:

```
    界前唯一走得到「有 stale 可比」的是同 key 併發首抓(build_* 無 inflight dedup),
```

三支 `build_*` 都是「查 cache → miss → `await fetch(...)` → 寫 cache」。`await` 期間
沒有任何佔位,同 key 的第二發請求一樣 miss、一樣發一次 TC4。

觸發情境(都不假設):
- 使用者 F5 / 快速切 tab(TQ 會 refetch)
- 同時開 `npm run preview`(4173)與 `npm run dev`(5173)兩個視窗看同一檔
- 前端 `barsPollInterval` 空態時的 20 s 重試撞上 60 s 常規輪詢
- 日 K 14:00 定稿界作廢那一刻,`/api/index/overlay` 與 `/api/market/bars/TWSE?tf=D`
  **共用同一格 `IX0001|L`**(`app.py:1754-1758` 明寫「同日兩端點合計至多兩次 DK 取數」)
  → 兩支 route 同時 miss 就是同時打

同一個 module 的 `oi_levels.py:120-130` 已經有正確樣板(`_get_lock` + 雙重檢查):

```python
    async with _get_lock():
        # 等鎖期間可能已被前一位填好(單飛:同鍵只讓一條真的去打 FinMind)
        hit = _cache.get(key, now=_now())
        if hit is not None:
            return hit
```

**修法**:`BarsCache` 加 `_inflight: dict[key, asyncio.Future]`,三支 `build_*` 進場
先 `if key in _inflight: return await _inflight[key]`。注意 `oi_levels` 那支是
**module 級單一把鎖**(全域序列化),bars 不能照抄 —— 要 per-key,否則不同股號的
請求互相排隊,把 B08-02 的 head-of-line 從 TC4 層搬到 route 層。

**風險**:`_warn_if_not_advanced` 的 docstring 明寫「界前一律不比(pr-171-review F-05):
tripwire 語意是『作廢後的 refetch』,界前唯一走得到『有 stale 可比』的是同 key 併發首抓」
—— 加了 single-flight 之後那條併發路徑就消失了,**但那段早退邏輯要留著**(它防的是
語意不是併發)。`tests/server/test_bars.py` 有對應案,改動時別順手刪。

---

### B08-04 前端分 K 聚合掛在 0.1 s 的 tick 打包上,整條 memo 鏈每 0.1 s 全穿
**嚴重度 high · 熱路徑 TRUE(每 0.1 s)· effort M**

`frontend/src/components/stock/StockChart.tsx:191-203`:

```ts
  const liveMinutes = liveOn && isMinute ? accum.minutes : null;
  ...
  const bars = useMemo(() => {
    const raw = data?.bars ?? [];
    if (liveMinutes !== null) {
      return aggregateBars(mergeLiveMinuteBars(raw, liveMinutes, liveToday, nowMinute), minutesOf(mode));
    }
    if (liveDay !== null) return mergeLiveDailyBar(raw, liveDay, liveToday, dayOpen);
    return aggregateBars(raw, minutesOf(mode));
  }, [data, mode, liveMinutes, liveDay, dayOpen, liveToday, nowMinute]);
```

同一段程式碼上方的註解(:161)已經算過帳:

```
  // 才重算,成本 = 一次 aggregateBars(30 日 1 分 K ≈ 5,900 根)+ merge O(補的根數)。
```

**但那個帳只算了聚合,沒算下游。** `bars` 換 identity →
`CandleChart.tsx:475` 的 `useMemo` 重算 `buildCandleGeometry` →
`CandleChart.tsx:88` 的 `ChartStatic = memo(...)` 全穿。

`mergeLiveMinuteBars`(`live-last-bar.ts:41-49`)每次做兩件無條件的重工:

```ts
  const out: Bar[] = [...official];          // 複製 5,900–8,100 元素
  ...
  const keys = [...minutes.keys()].filter((m) => m <= nowMinute).sort((a, b) => a - b);
```

`minutes` 是有序插入的 Map(分鐘鍵單調遞增),`sort` 每次都白做;`[...official]`
的複製在「正式段完全沒變、只有尾巴多一根」的常態下也白做。

**實測**(Node 24,8,100 根 + 270 分鐘):

| | min | median | p95 |
|---|---|---|---|
| `aggregateBars(bars, 5)` | 1.453 | **1.900** | 3.042 ms |
| `merge + aggregate(5)` | 1.571 | **1.897** | 2.724 ms |
| `JSON.parse`(728 KB,對照組) | 1.603 | 1.998 | 3.063 ms |

**修法(由便宜到貴)**:
1. **把「正式段」與「即時尾段」拆成兩個 memo**:正式段的 `aggregateBars(raw, n)` 只在
   `data` 換(每 60 s)時重算;即時尾段只聚合 accum 補出來的那幾根(O(補的根數))。
   最後 `[...officialAgg.slice(0, -1), ...liveTail]`。這樣 0.1 s 那一發的成本從
   O(8,100) 降到 O(n 桶數) ≈ O(10)。
2. `mergeLiveMinuteBars` 的 `keys` 去掉 `sort`(Map 已有序),或改成從 `afterMinute`
   起的區間掃描。
3. **節流**:UI 上「分 K 最後一根」不需要 10 Hz。加一個 250 ms 的 coalesce
   (`useDeferredValue` 或自寫 rAF 節流)就能把 10 Hz 降到 4 Hz,零視覺差異。
   `FuturesChart` 那邊已經有「不用期貨 WS 0.1 s coalesce 流」的先例
   (CLAUDE.md §4 個股分時圖「台指期」疊線條:「圖牆 50 張卡 memo 會被打穿」)。

**風險**:`lib/live-last-bar.test.ts` 的案 1 / 案 2 / 案 9 釘住 `+1` 與 13:30 上限;
拆 memo **不改算式**,那幾條不會紅。但 CLAUDE.md §4「個股頁即時末根的分鐘鍵 =
accum 起點分 +1、上限 13:30」是硬契約,拆的時候不能把 `barMinuteOf` 的夾法改掉。
另外 spec #214 的定稿閘(`dataUpdatedAt ≥ DAILY_FINAL_TIME && status === "ok"`)
是日 K 那半邊,拆分 K 不碰它。

---

### B08-05 wire 格式 = 每根 bar 一個 JSON object;欄式二進位可快 36×、小 3.2×
**嚴重度 medium · 熱路徑 false(每 60 s)· effort L**

現況 `app.py:1551` / `:199`:`{"code":…, "tf":…, "bars": [ {t,o,h,l,c,v}, … ], "status":…}`。
30 日 1 分 K = 8,100 根 = **728,153 B**。

實測三種方案(Python 3.13,8,100 根):

| 方案 | 序列化 min | bytes |
|---|---|---|
| `json.dumps(list[dict])`(現況) | 4.41 ms | 728,110 |
| 現場轉欄式 `array('i').tobytes()` | 4.09 ms | 226,800 |
| **cache 本身就存欄式**,送出只 `tobytes()` | **0.12 ms** | 226,800 |

前端側對照:`JSON.parse(728 KB)` = 2.0 ms median;`Int32Array(buffer)` = **0 ms**(零拷貝 view)。

**結論很明確但方向要說對**:
- 「現場把 dict 轉欄式再送」**買不到東西**(4.09 vs 4.41 ms)—— 轉換本身就是成本。
- 真正的 36× 只有在 **`BarsCache` 內部就以欄式儲存**時才拿得到。那同時解掉 B08-01
  的記憶體問題:8,100 根欄式 = 6 個 array + 一個 base date = **約 227 KB vs 2.73 MB,
  省 12×**。
- 但 4.4 ms / 60 s = **0.007% CPU**。**今天不值得做。**

**什麼時候值得做**:(a) 圖牆的卡片開始各自要 K 線(現在不要);(b) 要做 tick-level
replay 串流到前端;(c) 要同時看 10+ 商品的分 K。任一條成立就該做,而「改成量化交易
系統」大概率會踩到 (c)。

**風險(很重,所以列 L)**:動 wire 形狀會撞一整排契約 ——
`Bar` 的 `uv` / `dv` 是 `NotRequired` 且**缺欄 ≠ 0**(`stock_source.py::_delta_vol`
的 docstring + `candle.ts::Bar` 的註解 + `buildCandleGeometry` 的 `maxDelta === 0`
分支);`meta.partial_last` / `meta.status` 三態;`coverage_from/to`。
做法上應該**新增**一個 `Accept: application/octet-stream` 的並行表述而不是取代 JSON,
舊 dist 照走 JSON(CLAUDE.md 已有「版本落差」膠囊的先例)。

---

### B08-06 route 的 `-> dict` 回傳註解是效能關鍵路徑,拿掉就慢 14×(零訊號)
**嚴重度 medium · 熱路徑 false · effort S(只要一條測試)**

FastAPI 0.139 會把**回傳型別註解**當 `response_model`。有註解 → 走 pydantic-core 的
序列化器;沒註解 → 走純 Python 的 `jsonable_encoder` 遞迴。

實測(同一個 8,100 根 payload、同一台機器、TestClient):

| route 定義 | min | median |
|---|---|---|
| `async def r() -> dict:` | **4.32 ms** | 5.60 ms |
| `async def r():`(無註解) | **61.28 ms** | 67.98 ms |
| `return JSONResponse(content=payload)` | 6.50 ms | 7.28 ms |

本區塊四支 route 目前**都有**註解(`app.py:1520` `stock_bars(...) -> dict`、
`:1783` `market_bars(...) -> dict`、`:1485` `stock_overlay(...) -> dict`、
`oi_levels.py:279` `oi_levels(...) -> dict`)—— **現況是對的**。

問題是這件事**沒有被任何測試或註解保護**。任何人(包含未來的 agent)為了「型別更精確」
把 `-> dict` 換成一個手寫的 pydantic model,或是為了「這個註解沒意義」把它刪掉,
K 線 route 會靜默慢 14 倍。這正好是 CLAUDE.md 到處在防的那種「兩邊都跑得起來、
零錯誤訊號」的漂移。

**修法**:在 `bars.py` 或 `app.py` 的 route 上方加一條註解說明為什麼註解不可拆,
外加一條 route 層的 smoke 測試量 payload 大小 × 時間上界(或至少斷言
`route.response_field is not None`)。

**風險**:零。純防禦。

---

### B08-07 `OverlayCache._store` 完全沒有淘汰
**嚴重度 medium · 熱路徑 false · effort S**

`overlay.py:47-60` 全文:

```python
class OverlayCache:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict] = {}
    def get(self, code: str, today: str) -> dict | None:
        return self._store.get((code, today))
    def put(self, code: str, today: str, value: dict) -> None:
        if value.get("cdp") is None and ...:
            return
        self._store[(code, today)] = value
```

**沒有 `prune`,也沒有任何呼叫端在清它。** key 含日期 → 跨日不會覆寫、只會累加。
單筆很小(一個 5 欄 dict + 3 個 int),150 檔 × 250 個交易日 = 37,500 筆 ≈ 幾 MB,
**單看數字不是問題**。列出來的理由是它與 `BarsCache.prune` 的**設計不對稱**:
同一個 app 裡一個有嚴謹的三層淘汰、一個一行都沒有,而兩者持有的是同一類資料。
process 若真的跨月不重啟(quant 系統的目標形狀),它就是一條沒有上界的線。

**修法**:`put` 時順手丟掉 `today` 以外的 key(`_daily` 的 `prune` 就是這樣做的,
一行);或直接把 overlay 併進 `BarsCache`(它本來就是 `_daily` 的衍生值)。

**風險**:`app.py:541` 的註解明寫「per-app 實例(impl-spec R9:module-level 跨測試汙染)」
—— 保持 per-app,不要改成 module 級。`tests/server/test_overlay.py`(115 行)有
don't-cache-empty 的鎖。

---

### B08-08 `prune` 每次 `build_*` 都對四個 dict 做全表 list comprehension
**嚴重度 medium · 熱路徑 false(每請求一次)· effort S**

`bars.py:336-359`,四段各建一個中間 list:

```python
        for key in [k for k in self._hist if k[1] < floor]:
            del self._hist[key]
        ...
        for key in [k for k in self._daily if k[1] != today_iso]:
        ...
        for key in [
            k for k, e in self._today.items()
            if k[1] != today_iso or now - e[0] >= self._today_ttl(e[1])
        ]:
        ...
        for key in [k for k, e in self._empty.items() if now - e[0] >= EMPTY_TTL_SECS]:
```

`prune(today)` 是三支 `build_*` 的**第一行**。`_hist` 在 150 檔 × 60 日 = 9,000 鍵時,
每次請求掃 9,000 + 150 + N + N 次。推估 ~1 ms/請求(未單獨實測,`put_hist_range`
的 8,100 次 dict 操作實測 0.75 ms,同量級)。

現在是 1 請求/分鐘所以無所謂。**但它與 B08-01 綁在一起**:`_hist` 一旦裝了 300 檔就是
18,000 鍵的全表掃,而修 B08-01 的 LRU 也順手解掉這條(LRU 的淘汰是 O(1) 攤提)。

**修法**:`_hist` / `_daily` 的日期淘汰改成「日期一換才跑」(記 `_last_prune_day`,
同日早退);`_today` / `_empty` 的 TTL 淘汰改成 lazy(讀的時候判,反正 `today_get` /
`empty_status` 已經在判了)+ 每 N 次請求跑一次完整掃。

**風險**:`tests/server/test_bars.py` 有「prune 的 TTL evict」測試,`today_entry_count()`
就是為它留的觀測鉤。改成 lazy 要同時改那組斷言的語意(從「掃完之後條目數」變成
「有界成長」)—— 這是把一個嚴格保證換成較弱保證,要 user 拍板。

---

### B08-09 當日段 30 s TTL < 前端 60 s 輪詢 ⇒ 每次輪詢必打一次 TC4,而同一份資料 WS 早就送過了
**嚴重度 medium · 熱路徑 false(每 60 s / 每開圖)· effort L · 架構級**

`bars.py:45` + `:703-709`:

```python
TODAY_TTL_SECS = 30.0
...
    entry = cache.today_get(ck, today.isoformat())
    if entry is None:
        today_bars, raw_today_status = await fetch(code, "1", today.isoformat(), today.isoformat())
```

檔頭寫明這是刻意的:「**當日段**:短 TTL(預設 30s,短於前端 60s 輪詢),讓盤中最後
一根會前進(SC-10)」。

**但這個前提在 spec #214(2026-09-08 即時末根)之後已經部分過時了。** 前端現在自己拿
`accum.minutes` 把最後一根補到現在(`live-last-bar.ts::mergeLiveMinuteBars`),
也就是說**同一份當日分鐘資料,系統裡有兩條獨立來源**:
(a) TC4 1K 歷史,每 60 s 拉一次;(b) TC4 REALTIME tick,`stock_state` 折出 `minutes`,
每 0.1 s 推一次。前者純粹是為了「正式的、後端認證過的」那一份。

**量化系統的正確形狀**:後端自己用 tick 折出當日 1 分 K(`stock_state.MinuteAgg` 已經
有 c/h/l/v/i/o/u 全欄),當日段**零 TC4 往返**;TC4 1K 只在開盤回補與回補缺口時打。
那時 `TODAY_TTL_SECS` 這個常數連同「TTL 要短於前端輪詢」這條推理一起退役。

**風險(很重)**:
- 兩份當日 bar 的口徑必須對齊,而它們**現在就不一樣**:CLAUDE.md §4 明寫
  「1K 的 `t` 是終點標記」vs「accum 的分鐘 key 是起點分」,差 1 分鐘;
  `mergeLiveDailyBar` 的 `v` 取 `last.cum_vol` 而**不取** `accum.volume`(去重口徑不同)。
  後端自折當日 K 等於把這個「兩把尺」問題從前端搬到後端 —— 要先有一份對帳證據
  (同一天的 TC4 1K vs 自折 1K 逐根 diff)才能動。
- 動了之後 `meta.status` 三態(CLAUDE.md §4「`/api/market/bars` 的 `meta.status` 三態」)
  的語意要重新定義:當日段不打 TC4 了,`timeout` 從哪來?

**建議**:列為 quant 改造的中期項,**但必須先做對帳實驗**(見 §7 measurement plan)。

---

### B08-10 `build_period` 的 W/M 聚合結果不入 cache,每次請求重算
**嚴重度 low · 熱路徑 false · effort S**

`bars.py:610-612` + `:584` / `:595` / `:627`:

```python
def _shaped(bars: list[Bar], period: str) -> list[Bar]:
    """長窗日 K → 請求的 period 形狀(`"D"` 原樣、W/M 聚合)。"""
    return bars if period == "D" else aggregate_period(bars, period)
```

`build_period` 的三條回傳路徑(cache 命中 / 新鮮取數 / 墊背)**都**呼叫 `_shaped`。
`_daily` 只存 D 長窗,W/M 每次請求重跑 `aggregate_period`。

實測 1,500 根 → 月桶:**0.51 ms**(含一次 `sorted()`)。大盤頁的 W/M 是使用者手動切
tab 才打,不輪詢 → 一天個位數次。**記帳項,不是問題。**

順帶一提 `aggregate_period:510` 的 `sorted(bars, key=lambda x: x["t"])` 對一份
**來源已經排序過**的清單(`parse_dk_bars` 尾端 `bars.sort(...)`)重排一次。
把 `sorted` 換成 `assert` 或直接信任會省 ~0.2 ms —— 但那會把一個防禦拿掉換不到東西,
**不要動**。

---

### B08-11 `_market_payload` 的 `any(b["v"] > 0 ...)` 對指數路徑必定全掃
**嚴重度 low · 熱路徑 false · effort S**

`app.py:187`:

```python
    has_volume = volume if volume is not None else any(b["v"] > 0 for b in bars)
```

註解說明得很清楚(指數的 DK/1K 沒有量欄位,`_int_field` 缺值回 0 → 整條 v=0,標
`volume=true` 會畫一排貼底 0 高柱)。問題是 **`any` 對「全 0」的輸入沒有短路** ——
IX0001 的 8,100 根每次都全掃。推估 ~0.3 ms(8,100 次 dict 查 + 比較)。

**修法**:`TWSE` 鍵直接傳 `volume=False`(來源層已經知道指數沒量),與 `OTC` 分支
(`app.py:1829` 就是這樣寫的 `volume=False`)對稱。

**風險**:會讓「指數有沒有量」從**資料判定**退回**常數判定**,而註解明講這條是
2026-07-30 real-env 抓到的坑。期指路徑要維持資料判定(它真的有量)。
→ **判定:記帳,不建議動**(省 0.3 ms 換掉一個 real-env 教訓不划算)。

---

### B08-12 OI 撐壓抓 10 日全 TXO(含週選與他月)再丟掉 95%
**嚴重度 low · 熱路徑 false(一天一次)· effort S**

`oi_levels.py:144-151` 的查詢只帶 `dataset` / `data_id` / `start_date` / `end_date`,
沒有 `contract_date` 或 `trading_session` 過濾;`_pivot:180-183` 才在本地濾:

```python
    picked = [
        r for r in rows
        if r.get("trading_session") == "position" and str(r.get("contract_date")) == contract_ym
    ]
```

實測(合成 24,000 列 / 5.81 MB):`json.loads` 48.6 ms + `_pivot` 2.6 ms → 保留 120 檔履約價。
程式碼註解稱真實 10 日窗 ≈ 7 萬列 → 外推 `json.loads` ≈ 140 ms、`_pivot` ≈ 7 ms。

**一天一次、在 `to_thread`、後面還有 300 s 負向快取。不要動。**
唯一值得記的是 `_LOOKBACK_DAYS = 10` 的理由(D15:一次往返涵蓋連假)是對的,
縮到 5 只省一半頻寬而連假就會踩空 —— 那才是真的壞。

**如果**未來要把 OI 拉成盤中多次更新(quant 化合理需求),那時再談:
FinMind 的 `TaiwanOptionDaily` 是日頻資料,盤中重抓沒有新值,所以**天然不該提頻**。

---

### B08-13 `fetch_daily_bars` 每次取數換 DK 窗 ⇒ 每檔每天在 TC4 端建一把新 history 訂閱
**嚴重度 medium · 熱路徑 false · effort M · 需 TC4 端實測**

`stock_source.py:912-913` / `tc4.py:933-940`:

```python
        dk_start = self._next_dk_start(sym, start, end)
```

```
    """DK 取數的窗口 variant:同 (symbol, 窗) 第 n 次取數把 start 日期前移 n−1 日。
    **有副作用**(每呼叫一次序號 +1),每次 DK 取數恰呼叫一次。

    TC4 對 DK history 訂閱 key(symbol|DK|Start|End)的內容**凍結在 key 建立時點**"""
```

這是 `fix/dk-frozen-snapshot` 的修法本體,**功能上必要**。效能上的後果是:
每次 DK 取數 = TC4 端多一把 history 訂閱 key(never 退訂)。
圖牆一開 = 150 檔 × 1 把;加上 14:00 定稿界作廢後每檔再一把 = 300 把/天。

**TC4 端會不會因此變慢 / 吃記憶體 —— 未實測,標推測。** 但 `tc4-market-facts` skill
已經記了「TC4 對訂閱 refcount key 的行為」一整節,這條值得補一次觀測:
連續跑一天後看 TC4 的記憶體與 REQ 延遲有沒有階梯式上升。

---

### B08-14 【架構】live 路徑沒有本地歷史資料層 —— 每一根歷史 bar 都要問 TC4
**嚴重度 high · 熱路徑 false · effort XL · 這是本區塊「改成量化系統」的主軸**

現況三條事實:
1. `overlay.py` 檔頭:「偏離 brainstorm auto-default 的理由見 design v2 R4
   (**data/daily 為凍結研究回補**)」—— 本地日線 (`copycat/data/daily.py::DailyIndex`,
   CSV + `bisect`)**刻意不給 live 用**。
2. `DailyIndex` 的九個 import 全在 `backtest/*` / `replay/*` / `data/*`,零個在
   `server/*` 或 `live/*`(grep 已確認)。
3. CLAUDE.md §5「**沒有 DB**:state = React client + filesystem JSON cache
   (atomic write + `_CACHE_VERSION`);ZMQ tick 流 in-memory 不持久化」。

對「看盤工具」這是對的取捨(零相依、零維運)。對「要下實單的量化系統」這是**結構性缺口**:

- 歷史資料的取得成本 = TC4 桌面 app 的 ZMQ REQ 往返,而那把鎖是**單線程序列化**的。
- 所有歷史都是**易失的**:process 一重啟,`_hist` / `_daily` / `overlay_cache` 全空,
  下一次開圖又要重付一輪 TC4(CLAUDE.md 自己記著這件事:「只能重啟 server 才恢復」
  在 `put_hist_range` 的負向快取註解裡是當成**修復手段**在講的)。
- 回測用的 `data/daily` 與盤中看的 K 線是**兩套資料、兩套程式碼路徑**
  (`DailyIndex._DayRow` 是 float,`Bar` 是毫元 int)—— 量化系統最怕的就是
  「研究時的資料」與「實盤看到的資料」不是同一份。

**建議終局**:
```
TC4 (即時 tick + 當日 1K)  ──┐
FinMind (chip / 廣度 / OI)  ──┼→  本地 append-only 歷史層(Parquet / DuckDB)
                              │      ├ bars_1m(code, ts, o,h,l,c,v,uv,dv)  ← 毫元 int64
                              │      └ bars_1d(code, date, o,h,l,c,v)
                              │
  server/bars.py ─────────────┘      ← 歷史段改查本地,TC4 只補「本地缺的日子」
  server/overlay.py                  ← 150 檔 CDP/MA 變 150 次本地查詢(µs)
  backtest / replay                  ← 與 live 同一份資料、同一個毫元口徑
```

這一步同時解掉 B08-01(記憶體改成 mmap / 按需載入)、B08-02(overlay 不打 TC4)、
B08-03(single-flight 的壓力大減)、B08-09(當日段可以只補缺口)。

**風險 / 代價**:
- 破 stdlib-only。`duckdb` / `pyarrow` 都是大輪子(pyarrow wheel ~40 MB),
  Windows 上有 wheel、不需要編譯,但這是專案哲學的轉向,要 user 拍板。
- 資料正確性的新責任:誰負責補歷史?回補失敗怎麼標?這是一整個 spec 的量。
- 既有的毫元整數口徑必須貫穿(`DailyIndex` 現在是 float)—— 這反而是好事,
  統一成毫元 int64 之後 `market.py` 的 parity 契約會更好守。

---

### B08-15 `mergeLiveMinuteBars` 每次無條件複製整段正式 bars + 排序已有序的 Map keys
**嚴重度 medium · 熱路徑 TRUE(每 0.1 s)· effort S**

`frontend/src/lib/live-last-bar.ts:41-49`(B08-04 的子項,但可以單獨修):

```ts
  const out: Bar[] = [...official];
  ...
  const keys = [...minutes.keys()].filter((m) => m <= nowMinute).sort((a, b) => a - b);
```

`minutes` 由 `stock-accum.ts` 以單調遞增的分鐘鍵插入 → `sort` 恆為 no-op 的比較成本
(270 個元素的 sort ≈ 0.02 ms,× 10 Hz = 0.2 ms/s)。
`[...official]` 複製 8,100 個參考 ≈ 0.05 ms × 10 Hz。

單獨看都很小,但這兩行是 B08-04 那條「把正式段與尾段拆開」修法的**天然切點**:
拆完之後 `official` 根本不需要進這支函式。

**風險**:函式 docstring 明寫「正式段元素 identity 保留、傳入 array 不改;恆回新 array」
—— 「恆回新 array」是呼叫端 memo 的前提,拆的時候要保住。

---

### B08-16 `is_partial_last` / `_warn_if_not_advanced` / `daily_get` 各自呼叫 `_now_time()`
**嚴重度 low · 熱路徑 false · effort S**

`bars.py:90-93` 的 `_now_time()` 是測試唯一凍結點(設計正確),但一次 `build_daily`
會呼叫它 2–3 次(`daily_get` 一次、`_warn_if_not_advanced` 一次、`daily_put` 一次),
route 再呼叫 `is_partial_last` 一次。四次 `datetime.now()` ≈ 1 µs 總計。

**純記帳,不要動。** 提出來是因為「同一個請求裡取樣四次牆鐘」在跨 14:00 定稿界的那一秒
理論上會不一致(`daily_get` 判界前、`daily_put` 判界後)。實際後果:那一次寫入被標成
定稿而不是界前 —— 這正是我們要的方向(安全側)。`bars.py:602-607` 的 `_period_pre_final`
docstring 明寫「與 bars 在同一個同步區塊內取值」就是在處理這一類 race。**設計是對的。**

---

## 4. 工具選型與取捨

| 工具 | 用在哪 | 解決什麼 | 代價 | 判定 |
|---|---|---|---|---|
| **DuckDB** 或 **Parquet + pyarrow** | 新增 `copycat/store/history.py`,`bars.py` 歷史段與 `overlay.py` 改查本地 | B08-14 / B08-02 / B08-01 / B08-09 一次解 | 破 stdlib-only;+40 MB wheel;新增「誰補歷史」的維運責任;回測與 live 的資料口徑要統一成毫元 int64 | **建議導入**(需 user 拍板哲學轉向) |
| **stdlib `array` + `memoryview`** | `BarsCache` 內部改欄式儲存 + 新增 binary 表述 | B08-05(序列化 36×、記憶體 12×、前端零 parse) | **零相依**;但撞 `Bar` wire 契約(uv/dv NotRequired)→ 要做並行表述不能取代 | **有條件導入**(等 B08-05 的觸發條件成立;先做也不虧,因為它同時解 B08-01) |
| **numpy** | `aggregate_period` / `aggregate_1k_to_daily` / `compute_ma` | 帳面上 5–20× | 這三支合計 < 1 ms/請求,**沒有熱路徑**;而 numpy 的 int64 與毫元 int 的溢位語意不同,parity fixture 要重打 | **不建議**(單獨為此導入 = 過度工程;若 B08-14 走 pyarrow,numpy 會順便進來,那時再用) |
| **polars / pandas** | — | — | 本區塊沒有任何 DataFrame 形狀的運算;最大的一份資料是 8,100 根 bar | **不建議** |
| **orjson / msgspec** | route 序列化 | 實測 `-> dict` 已走 pydantic-core 快路徑(4.3 ms / 728 KB ≈ 170 MB/s),orjson 大約再快 2–3× | 換來 ~2 ms/分鐘;msgspec 要重寫 Struct 定義 = 撞所有 wire 契約 | **不建議**(B08-05 的欄式方案便宜得多且快 36×) |
| **uPlot / lightweight-charts**(canvas) | 取代 `CandleChart` 的 SVG | B08-04 的下游(700 蠟燭 × 3 節點 × 10 Hz 的 DOM diff) | `lib/stock-intraday-svg.ts` 921 LOC + `candle.ts` 354 LOC 的行為白名單很厚(極值標記翻面、y 刻度 snap 合法檔位、十字線同步、hover 分鐘節流…);CDN 白名單允許 cdnjs,但 bundle 要自己打 | **有條件導入**(先做 B08-04 的 memo 拆分 + 節流,量到還不夠再談;不要為了「用圖表庫」而換) |
| **Web Worker / Comlink** | 把 `aggregateBars` 搬出主執行緒 | B08-04 | 1.9 ms 的工作跨 worker 要序列化 8,100 根(structuredClone ≈ 同量級)→ **負收益** | **不建議** |
| **cachetools / diskcache** | 取代手刻 `BarsCache` | — | `BarsCache` 的三層語意(永久歷史 / 短 TTL 當日 / 短 TTL 負向 + 定稿界 + 墊背)沒有現成庫表達得出來,而且有 1,176 行測試釘著 | **不建議** |
| **GZip middleware** | HTTP 壓縮 | 728 KB → ~120 KB | **後端與前端在同一台**,localhost 頻寬不是瓶頸;壓縮會**增加** CPU(~3 ms 壓 + ~1 ms 解) | **不建議**(淨損) |

---

## 5. 不要動的地方(反向結論)

1. **`copycat/market.py` 的毫元整數 tick 表**(70 行)。實測 103–187 ns/call,
   每 tick 呼叫也只有 0.04 ms/s。而它守著兩條跨語言 parity 契約
   (`tests/fixtures/vp_parity.json` ↔ `frontend/src/lib/stock-tick.ts::snapDown`;
   `capital_api.py:147` 的下單檔位閘)。換 bisect 省不到 100 ns,契約要同動三處。
   **毫元整數是效能友善**的設計(int 運算 + 無 float 殘差),不是包袱。

2. **`overlay.py::compute_cdp` / `compute_ma`**(60 行整檔)。O(n),n ≤ 1500,
   每檔每天算一次。`build_overlay` 是 `app.py:1761` 明說的「常數時間」。
   `compute_ma` 的 `sum(closes[-n:])` 建一個 5 或 20 元素的切片 —— 增量化(滑動窗)
   在 n=20 的規模是純粹的複雜度。

3. **`oi_levels.py` 的 `_pivot` 與 10 日窗**。一天一次,`to_thread`,實測 2.6 ms。

4. **`bars.py` 的兩段式快取 + 負向快取 + 定稿界 + 墊背**。這四件套是**正確性裝置**
   不是效能裝置,每一條都對應一次 prod 事故(檔頭與各 docstring 逐條記著
   `change-spec R2-2` / `round3 項 9` / `pr-165-review` / `fix/dk-frozen-snapshot`)。
   優化時要從外圍(single-flight、LRU、欄式儲存)加,不要動這四條的語意。

5. **route 的 `-> dict` 回傳註解**。見 B08-06 —— 它現在就是快路徑,**要保護不要清理**。

6. **`aggregate_period` 的 `sorted()`** 與 **`_market_payload` 的 `any(...)`**。
   兩者合計 < 1 ms/請求,而各自對應一條真實教訓(連假週的桶鍵錯位 / 指數假 0 量柱)。

7. **`build_minute` 的 `hist_range` 重組**。實測 0.03 ms / 8,100 根。

---

## 6. 跨檔契約(改造時的硬約束)

依 CLAUDE.md §4,本區塊涉及的契約與「動了要同動哪一邊」:

| 契約 | 產生點 | 讀者 | 本區塊改造時的注意 |
|---|---|---|---|
| **`DAILY_FINAL_TIME` 前後端同值** | `server/bars.py:80`(14:00) | `frontend/src/lib/day-bars-rollover.ts::DAILY_FINAL_TIME`、`components/stock/StockChart.tsx` 的日 K 即時末根定稿閘 | `tests/server/test_bars.py::test_daily_final_time_parity_with_frontend` **釘等值**(比 ≥ 嚴)。B08-09 若改掉當日段取數方式,這條界的語意要重新推導 |
| **期貨 CDP/MA 前後端同式** | `server/overlay.py::compute_cdp/compute_ma` + `build_overlay` 的 `date < today` 界 | `frontend/src/lib/futures-overlay.ts` | golden fixture `tests/fixtures/overlay_parity.json`(expected 手算寫死)+ 兩側各一條測試。**白名單差異只有前端多一道 `usable()` 0 價閘**。任何「換 numpy 算 MA」的動作會改變整數除法語意 → 兩邊同時紅才對,單邊紅就是漂了 |
| **VP 檔位 parity** | `copycat/market.py::snap_down_milli` | `frontend/src/lib/stock-tick.ts::snapDown` | `tests/fixtures/vp_parity.json` 兩側各自斷言。B08 若動 tick 表(不建議)= 三處同動 |
| **`/api/market/bars` 的 `meta.status` 三態** | `live/futures_source.py::fetch_bars_range` → `futures_engine.bars_range` → `server/bars.py::build_minute`(兩段取最壞)→ `app.py::_market_payload` | `frontend/src/hooks/useMarketBars.ts::BarsMeta.status`、`components/futures/FuturesChart.tsx::EMPTY_TEXT` | **只在期指 `tf=1` 出現**;其餘路徑連鍵都不給。硬寫恆 `ok` 是謊報。B08-05 的 binary 表述必須把這一格帶過去 |
| **`Bar` 的 `uv` / `dv` NotRequired(缺欄 ≠ 0)** | `live/stock_source.py::_delta_vol`(兩欄皆缺 → None → 不設欄) | `frontend/src/lib/candle.ts::Bar` + `buildCandleGeometry` 的 `maxDelta === 0` 分支 + `aggregateBars` 的 `hasDelta` | **欄式二進位(B08-05)最難的一點** —— 欄式天生沒有「缺欄」概念,要另帶一個 presence bit 或一個 `has_delta` 旗標 |
| **1K `t` = 終點標記** | `live/stock_source.py::_taipei_minute_key`(分鐘域 0901–1330) | `frontend/src/lib/candle.ts` 檔頭(桶界 (09:00, 09:05])、`lib/txf-overlay-series.ts`(−1 分)、`lib/live-last-bar.ts::barMinuteOf`(+1 分) | **三把尺同源反向**。B08-09(後端自折當日 K)會直接踩這條 |
| **個股頁即時末根 = accum 起點分 +1、上限 13:30** | `frontend/src/lib/live-last-bar.ts::mergeLiveMinuteBars` | `StockChart.tsx` | B08-04 / B08-15 的拆分**不得改算式**;`live-last-bar.test.ts` 案 1/2/9 釘住 |
| **OI 降級語意 = 200 + 空 shape** | `oi_levels.py` 檔頭 + `fetch_oi_levels` | `frontend/src/hooks/useOiLevels.ts` | 任何「改成 4xx 讓前端知道失敗」的優化都是退步 —— 4xx 會被 TQ error 路徑吞成同一種紅色 |
| **「盤前篩選」群組名 / 自選上限 150** | `screen_engine.SCREEN_GROUP` / `stock_watchlist.WATCHLIST_LIMIT` | 多處 | 與 B08-01/B08-02 的「最壞值」推估直接相關:CLAUDE.md 明寫「以『檔數 × 單價』推理的效能預算註解……改值時它們的最壞值跟著變,量測判準要重算」。`bars.py:341` 的 prune docstring **就是這類註解,而且已經漂了(還寫 50)** |

**額外發現(文件層漂移)**:`bars.py:341` 的 `prune` docstring 寫「股號受 watchlist 50
檔上限約束」,但上限自 2026-09-01 起是 150,且該路徑根本不受 watchlist 約束(見 B08-01)。
這正是 CLAUDE.md「第二類讀者 = 以『檔數 × 單價』推理的效能預算註解」那條要防的漂移,
09-02 那一輪改寫漏了這一處。

---

## 7. 量測方法(要證明快或慢,該怎麼量)

### 7.1 已經跑過的(腳本在 scratchpad,可重跑)

```powershell
# 後端:route 序列化 / 欄式對照 / hist_range 合併
.venv\Scripts\python <scratchpad>\bench_bars.py
.venv\Scripts\python <scratchpad>\bench_col.py
# OI pivot + json.loads
.venv\Scripts\python <scratchpad>\bench_oi.py
# 前端純函式(Node,不需要瀏覽器)
node <scratchpad>\bench_front.mjs
# market.py 微基準
.venv\Scripts\python -c "import timeit; ..."
```

### 7.2 還需要在 prod 環境量的(依優先序)

**M-1 `BarsCache` 的實際成長(證 B08-01)** — 零風險,加兩行觀測即可
```python
# 沿 today_entry_count() 的先例加 hist_entry_count() / hist_bytes()
# 或不改 code,盤後直接對跑著的 server 下:
#   (若已有 /api/health) 擴一格 bars_cache={"hist":n,"today":m,"daily":k}
```
判準:一整個交易日結束時 `hist` 鍵數。若 > 3,000(= 50 檔 × 60 日)就證實 B08-01。
搭配 `psutil` / 工作管理員記 RSS 的日內曲線(開盤 / 午盤 / 收盤三點)。

**M-2 圖牆 overlay 的 ramp(證 B08-02)** — 盤中,唯讀
```powershell
# 進群組檢視前清 log 位置,進去之後:
Select-String -Path logs\server-*.log -Pattern "daily_bars|overlay" | Select-Object -Last 200
# 或直接看 uvicorn access log 裡 /api/stock/overlay/ 的時間戳分布
```
判準:第一發與最後一發 `/api/stock/overlay/` 的時間差。若 > 20 s 就證實 head-of-line。
同時 grep `stock backfill` 看回補有沒有被擠到那個窗之後。

**M-3 前端 K 線的 render 成本(證 B08-04 的下游)** — 盤中,需 Chrome DevTools
```
1. npm run preview(4173,prod build —— dev build 的 props-diff 開銷會汙染量測,
   CLAUDE.md §1 已明訂「整天掛著一律用 prod build」)
2. 開個股頁 → 切 5 分 K → Performance 錄 30 s
3. 看 Main thread 的 long task(> 50 ms)數與 scripting 佔比
```
判準:30 s 內 > 50 ms 的 task 數。#187 那一輪已經用過同款判準(「trace 93 s >50ms=0」),
可以直接對照。拆 memo 前後各錄一次。

**M-4 B08-09 的前置對帳(當日段 TC4 1K vs 後端自折)** — 這是**動手前必做**的實驗
```python
# 盤後,同一天:
#   A = GET /api/stock/bars/2330?tf=1&days=1  的 bars(TC4 1K)
#   B = stock_state 的 minutes payload(GET /api/stock/state/2330)
# 逐根比 c / h / l / v,列出所有不等的分鐘與差值。
```
判準:若 `v` 的差異是系統性的(去重口徑)而 `c/h/l` 逐根相等,B08-09 可做;
若 `c/h/l` 也有差,先查清楚原因再說(可能是回補缺口或試撮窗)。

**M-5 DK 窗 variant 對 TC4 端的累積影響(證 B08-13)**
連續兩個交易日不重啟 server,記 TC4 桌面 app 的 RSS 與
`history %s(%s): %.1fs 內首頁未備妥` 這行的出現頻率。若第二天明顯變多 = 證實。

### 7.3 不要用的量法
- **不要**用 `npm run dev` 量前端 —— dev build 的 React Component Performance Track
  與 props-diff 開銷會蓋過真實訊號(CLAUDE.md §1 已記)。
- **不要**用 `pytest` 的執行時間當效能判準 —— 那批測試全部餵 fake source,量到的
  是 fixture 開銷。
- **不要**在盤中對 prod server 做 mutation 型的量測迴圈(`ops-discipline` skill)。

---

## 8. 開放問題

1. **TXO 月契約真實的履約價數與 10 日窗真實列數?** 程式碼註解寫「≈7 萬列」,
   本次用 24,000 列合成外推。要 prod 打一發 `/api/futures/oi-levels` 看
   `oi-levels %s:%d rows → latest=%s / %d strikes` 那行的實際數字。
   (影響:B08-12 的「不要動」結論若列數是 20 萬而不是 7 萬,`json.loads` 會到 400 ms,
   仍在 to_thread、仍一天一次,結論不變 —— 所以這題其實不阻塞任何決定。)

2. **單檔 `fetch_daily_bars` 的實際往返時間?** B08-02 的 45 s ramp 是用
   「首頁 <1s」的註解取 0.3 s 估的。要 M-2 的實測才能確認量級。

3. **`user` 實際上一天會開多少不同股號的分 K?** 決定 B08-01 是 82 MB 還是 820 MB。
   可從 uvicorn access log 的 `/api/stock/bars/` distinct code 數直接數(盤後一次)。

4. **stdlib-only 的哲學要不要為了本地歷史層破例?**(B08-14)這是 user 的決定,
   不是技術問題。相關的已知事實:`extras [live]` 已經有 fastapi/uvicorn/pyzmq,
   `[capital]` 有 comtypes/pywin32 —— **runtime 早就不是純 stdlib 了**,
   `dependencies = []` 守的其實是「核心回測引擎零相依」。所以新增一個
   `extras [store]` 裝 duckdb 並不違背原本的設計意圖,只是要把這件事講清楚。

5. **B08-09(後端自折當日 1 分 K)之後,`meta.status` 三態要怎麼重新定義?**
   當日段不打 TC4 之後,`timeout` 的來源只剩歷史段。這會讓 CLAUDE.md §4 那條契約的
   「這一趟回補請求的結果」語意變窄 —— 需要 grilling 一輪。

6. **`aggregateBars` 拆成「正式段 memo + 尾段」之後,`onTotalChange`(viewport 跟隨)
   的 `prevTotal` / `nextTotal` 會在每 0.1 s 變動嗎?**
   `candle-viewport.ts::onTotalChange` 只在「改動前已貼右緣」時跟進。即時末根每分鐘
   才多一根,所以 total 每分鐘才變一次 —— **推測不受影響**,但拆的時候要驗。
