# Q2 — 工具與套件選型調研(對外查證)

**區塊**:`Q2-tooling-landscape`
**日期**:2026-09-13
**目標環境**:Windows 11 Home 26200 / Python 3.13.13 (MSC v.1944 64-bit) / React 19.2.7 / Vite 6.4.3 / 本機單台(後端 + 前端 + TC4 桌面 app 同機)
**最終目的**:把 copycat 改寫成「專注高效能、可下實單」的量化交易系統。本區負責**選型**,不負責改 code。

> 讀法:§8 是給 Fable 討論用的一頁總表;§1–§7 是每個結論的查證依據;§9「不要動」與 §11「未查證」同樣重要。
> 所有版本號 / wheel 平台 / 授權皆為 **2026-09-13 直接打 PyPI / npm registry 取得**(腳本
> `scratchpad/pypi_probe.py`、`pypi_probe2.py`、`npm_probe.py`),非二手文章轉述。

---

## 0. 一句話結論

這套系統的效能瓶頸**幾乎不會是「Python 算得慢」**,而是三件事:
(a) 熱路徑上的 **Python 物件配置與 dict/list 複製**;(b) **stdlib `urllib` 的同步阻塞外呼混在 async loop 裡**;
(c) 前端 **每張圖每根 K 線一個 React SVG 元素**。

因此選型的優先序不是 numpy/polars,而是:
**msgspec(wire + 熱路徑資料結構)> 非阻塞 HTTP client > 前端 canvas 圖表庫 > polars/DuckDB(只給離線回測)> numba/Cython(多半不需要)**。

而 **uvloop 在 Windows 永遠不會有**(PyPI 實測 `win=NONE`),`winloop` 是唯一替代但要自己承擔風險 —— 這是本專案「Windows 單機」這個硬約束帶來的最大天花板。

---

## 1. 現況基線(實測,非推測)

### 1.1 後端

`C:\side-project\copycat\pyproject.toml`:

```toml
5  requires-python = ">=3.13"
6  dependencies = []
8  [project.optional-dependencies]
9  live = ["fastapi>=0.115", "uvicorn[standard]>=0.30", "pyzmq>=26"]
10 capital = ["comtypes>=1.4", "pywin32>=306"]
11 discord = ["discord.py>=2.4"]
12 dev = ["pytest>=8", "ruff>=0.5", "pyright>=1.1", "httpx>=0.27", "pytest-asyncio>=0.24"]
```

`.venv` 實際裝到的東西(`ls .venv/Lib/site-packages`):

| 套件 | 版本 | 備註 |
|---|---|---|
| Python | **3.13.13** (2026-04-07, MSC v.1944 AMD64) | 非 free-threaded build |
| uvicorn | 0.51.0 | |
| fastapi | 0.139.2 | |
| pyzmq | 27.1.0 | |
| httptools | 0.8.0 | ← `uvicorn[standard]` 給的,**HTTP parser 已經是 C 版** |
| websockets | 16.1.1 | |
| watchfiles | 1.2.0 | |
| httpx / aiohttp | 0.28.1 / 3.14.3 | httpx 來自 dev extra、aiohttp 來自 discord.py —— **都已在機器上,但 runtime code 沒用** |
| **uvloop** | **不存在** | Windows 沒有 wheel(§5.1) |
| numpy / pandas / polars / pyarrow / duckdb / orjson / msgspec / numba | **全部不存在** | |

**已經是最佳解的兩件事**(查 `.venv` 內原始碼確認,不是推測):

`.venv/Lib/site-packages/uvicorn/loops/asyncio.py`
```python
def asyncio_loop_factory(use_subprocess: bool = False):
    if sys.platform == "win32" and not use_subprocess:
        return asyncio.ProactorEventLoop      # ← 單進程模式 = Proactor(IOCP),不是 Selector
    return asyncio.SelectorEventLoop
```

`.venv/Lib/site-packages/uvicorn/protocols/websockets/auto.py`
```python
else:
    from uvicorn.protocols.websockets.websockets_sansio_impl import WebSocketsSansIOProtocol
    AutoWebSocketsProtocol = WebSocketsSansIOProtocol   # ← 新的 sans-io 實作,不是舊 websockets_impl
```

也就是說:**HTTP parser(httptools)、WS 實作(sans-io)、event loop(IOCP Proactor)這三層,現況已經是 Windows 上 uvicorn 能給的最好組合。** 不要以為「沒裝 uvloop = 沒優化」。

`copycat/server/__main__.py` 末行:
```python
uvicorn.run(app, host="127.0.0.1", port=port, timeout_graceful_shutdown=WS_DRAIN_SECS)
```
單進程、無 `--workers`、無 `--reload` → `use_subprocess=False` → Proactor。✅

### 1.2 前端

`frontend/package.json` dependencies 只有 5 個:
```json
"@tanstack/react-query": "^5.62.0",
"clsx": "^2.1.1",
"react": "^19.0.0",
"react-dom": "^19.0.0",
"tailwind-merge": "^3.0.0"
```

`frontend/node_modules/.package-lock.json` 實裝版本:

| 套件 | 實裝 | 2026-09-13 latest | 落後 |
|---|---|---|---|
| react / react-dom | 19.2.7 | **19.3.0** (2026-09-09) | 1 minor |
| vite | **6.4.3** | **8.3.0** (2026-09-10) | **2 個 major** |
| @vitejs/plugin-react | 4.7.0 | 6.1.1 (2026-08-28) | 2 major |
| @tanstack/react-query | 5.101.2 | 5.102.8 | 1 patch |
| typescript | 5.8.3 | — | |
| vitest | 3.2.7 | — | |
| esbuild / rollup | 0.25.12 / 4.62.2 | (Vite 8 兩者都被 Rolldown+Oxc 取代) | |
| @babel/core | 7.29.7 | (被 plugin-react 4.x 拉進來) | |

圖表現況 —— **全手刻 SVG,且是 React 元素層級**:

`frontend/src/components/stock/CandleChart.tsx:221`
```tsx
{g.candles.map((c, i) => (
```
`:176` / `:203` volBars、`:300` hlines、`:353` shown …每根 K 線 / 每根量棒 = 一個 React element + 一個 DOM node。

幾何全部抽乾淨在純函式裡(這是**好消息**,見 §9):
- `frontend/src/lib/candle.ts` 354 LOC — `buildCandleGeometry` 吐 `{candles, volBars, yTicks}` 座標
- `frontend/src/lib/stock-intraday-svg.ts` 921 LOC — `buildIntradayGeometry` / `overlayLines` / `edgePriceLabels` / `layoutEdgeLabels` 全是 pure geometry
- `frontend/src/components/stock/StockIntradayChart.tsx` 1724 LOC 只掛 DOM
- `frontend/src/components/stock/CardIntradayChart.tsx` **71 LOC** 的薄包裝(圖牆 50 張卡用的就是它)

### 1.3 ZMQ 的接法(重要,決定 §5.4 的結論)

`copycat/live/tc4.py`:
```
1185:  self._listener = threading.Thread(target=self._listen_loop, daemon=True)
1245:      raw = (sock.recv()[:-1]).decode("utf-8")      # ← 阻塞 recv,在專用 thread
 571:      message = api.socket.recv()[:-1]
 638:  self._healer = threading.Thread(target=self._heal_loop, daemon=True)
```

**沒有用 `zmq.asyncio`。** ZMQ 走獨立 daemon thread + 阻塞 `recv()`,再把結果丟回 event loop。
這正好是 Windows 上的正解(理由見 §5.4)—— 這一塊**不要動**。

---

## 2. 後端 — 計算與資料

### 2.1 Polars(vs pandas)

**2026-09-13 PyPI 實測結果,這是本次調研最有價值的一條情報:**

```
polars            1.44.2   2026-09-09   requires_python>=3.10
  檔案只有 2 個:polars-1.44.2-py3-none-any.whl (866 KB) + tar.gz
  requires_dist: ['polars-runtime-32==1.44.2',
                  'polars-runtime-64==1.44.2; extra == "rt64"',
                  'polars-runtime-compat==1.44.2; extra == "rtcompat"', ...]

polars-runtime-32 1.44.2   win wheels: polars_runtime_32-1.44.2-cp310-abi3-win_amd64.whl ✅
polars-runtime-64 1.44.2   win wheels: polars_runtime_64-1.44.2-cp310-abi3-win_amd64.whl ✅
```

**要點:**
1. Polars 1.4x 已經**拆成「薄 Python 前端 + 獨立 binary runtime 套件」**。`pip install polars` 現在只裝一個 866 KB 的 py3-none-any wheel,binary 由 `polars-runtime-32` 帶進來。這代表:
   - Windows amd64 wheel **有**(在 runtime 套件裡,`cp310-abi3` → Python 3.13 直接吃)
   - 但**離線安裝 / 內網鏡像 / 鎖版**的做法要跟著改(以前鎖 `polars==x` 就夠,現在要一起鎖 runtime)
2. **預設是 `runtime-32`(32-bit index,約 42 億列上限)**;要超過就裝 `polars[rt64]`。台股回測資料量遠遠碰不到,**預設即可**。
3. `polars-lts-cpu`(給沒有 AVX2 的老 CPU)**最新只到 1.33.1 / 2025-09-09** —— 落後主線整整一年。所以**如果這台機器沒有 AVX2,Polars 實質上是舊版凍結**。先確認 CPU(§10 量測腳本 M1)。
4. `requires_python >= 3.10`,classifiers 沒列到 3.14;**free-threaded wheel = 0 個**(我掃了檔名裡的 `cp313t`/`cp314t`)。
5. Streaming engine:`collect(engine="streaming")` 已是可顯式啟用的成熟路徑,GPU streaming backend 另有(對本專案無關,沒有 GPU 需求)。

**對 copycat 的判斷:**
- **回測 / replay / 特徵工程(`copycat/backtest/`、`copycat/replay/`、`copycat/data/`)→ 建議導入。** 這些是離線批次、資料量以 GB 計(neigui 種子 1.24 GB),手刻 Python loop 在這裡是真的慢,而且慢得沒有理由。
- **即時看盤路徑(`copycat/live/`、`copycat/server/`)→ 明確不要導入。** 每 tick 的資料是「一筆」,不是「一個 DataFrame」。為了單筆資料建 DataFrame 的開銷遠大於 dict。**Polars 在 row-at-a-time 的場景是負優化。**
- pandas(3.0.5,2026-07-22)**沒有理由選**:copycat 沒有任何既有 pandas 程式碼要相容,新建專案直接用 Polars 的 API 更一致、更省記憶體。唯一例外是 FinMind 若回傳 pandas(未查證其 SDK,現況走 `urllib` 自己解 JSON,所以無此包袱)。

來源:
- https://pypi.org/project/polars/
- https://github.com/pola-rs/polars/issues/2922 (lts-cpu / AVX2)
- https://pola.rs/posts/gpu-streaming-backend/

### 2.2 NumPy 2.x

```
numpy  2.5.3  2026-09-06  win=win32,win_amd64,win_arm64  free-threaded wheels=13
```

- Windows wheel 齊全,free-threaded build 也有 wheel(2.0 起就 ship)。
- NumPy 2.5.0 (2026-06-21) 起**丟掉 Python 3.11 支援**;3.13 在支援範圍內。

**對 copycat 的判斷:有條件導入,而且範圍要很窄。**

真正該用 numpy 的只有兩處形狀:
1. `copycat/backtest/` 的 GA 搜索 / 特徵矩陣 —— 但這裡 Polars 已經涵蓋(Polars 內部就是 Arrow + SIMD),**不必兩個都上**。
2. 前端 CDP/MA 的後端對照 `copycat/server/overlay.py::compute_ma` —— **這裡明確不要動**,理由見 §9(golden fixture parity)。

⚠️ **陷阱**:`copycat/market.py` 用**毫元整數**做 tick 表與漲停價運算。改用 numpy float64 會引入 0.5 個 tick 的舍入差,直接打壞下單價格正確性。這是「不要用 numpy 的地方」的教科書案例。

來源:https://numpy.org/devdocs/release/2.3.0-notes.html · https://numpy.org/news/

### 2.3 PyArrow / Parquet

```
pyarrow  25.0.1  2026-08-10  win=win_amd64  free-threaded wheels=7
```

- Windows amd64 wheel ✅(注意:**沒有 win_arm64**,但本機是 amd64,不影響)。
- Polars 不需要 pyarrow 就能讀寫 parquet(內建 Rust 實作);`polars[pyarrow]` 只在需要跟 Arrow 生態互通時才要。

**判斷:不要單獨導入 pyarrow。** 導 Polars 或 DuckDB 任一個,parquet 讀寫就有了,多一個 pyarrow 只是多 90 MB 安裝體積跟一條版本相依鏈。

**但 Parquet 格式本身建議導入**:現況 `copycat/data/store.py` 是「1K atomic JSON」,回測讀取要一路 `json.loads`。同樣的 bar 資料存 parquet,讀取快 10–50 倍且體積小 5–10 倍(量級推估,需 §10 M2 實測)。這是 **格式換掉、不必換函式庫** 的改動。

### 2.4 DuckDB

```
duckdb  1.5.5  2026-07-22  win=win_amd64,win_arm64  free-threaded wheels=0
```

- 嵌入式、零 server、`pip install duckdb` 一行、Windows wheel ✅。
- 向量化執行 + SIMD,可直接 `SELECT ... FROM 'out/*.parquet'` 而不載入全檔。
- **單寫入者限制**(one writer at a time)—— 對 copycat 的離線回測無影響(單進程),但**絕不要**拿它當即時 tick 的落地層。

**判斷:回測查詢層建議導入,與 Polars 二選一或並存。**

分工建議(這是選型的關鍵取捨):
- **DuckDB** 適合:`copycat/backtest/` 的 outcome cache 查詢、`docs/evidence/` 報表產生、跨日 join(T 日 → T+1 開盤)、ad-hoc「這個條件過去三年命中幾次」。SQL 表達 join/窗函數比手刻 Python 清楚一個量級。
- **Polars** 適合:`copycat/replay/` 的逐事件流程、特徵欄位運算、跟 Python 程式碼緊密交織的地方。
- 兩者可零成本互通(都吃 Arrow)。**但先只上一個**,建議先上 DuckDB —— 因為它能直接查現有落檔而幾乎不用改 code(`read_json_auto` 也讀得動現況的 JSON),導入摩擦最小。

來源:https://github.com/duckdb/duckdb · https://kestra.io/blogs/embedded-databases

### 2.5 Numba / Cython / mypyc

```
numba   0.67.0  2026-08-11  win=win_amd64,win_arm64  ft_wheels=4
Cython  3.3.0   2026-08-22  win=win32,win_amd64,win_arm64
mypy    2.3.1   2026-08-15  (mypyc 隨 mypy 一起出貨)
```

**Numba**:Python 3.13 支援自 **0.61.0(2025-01-16)** 起就有(當時不含 free-threading);現在 0.67.0 有 Windows wheel 且有 4 個 free-threaded wheel。所以「numba 在新 Python 上總是落後」這個刻板印象**在 2026 已經不成立**。

**但對 copycat,numba 的判斷是「明確不要」**,理由有三:
1. numba 的收益來自「純數值 tight loop、沒有 Python 物件」。copycat 的熱路徑是 `copycat/live/stock_state.py` / `signal_state.py` 這種**狀態機 + dict + 字串 symbol**,`@njit` 直接 fallback 到 object mode(等於沒加速)或根本編不過。
2. JIT 首次編譯要數百 ms~數秒。開盤瞬間第一筆 tick 觸發編譯 = 正好卡在最不能卡的時刻。要用就得 AOT cache,複雜度陡增。
3. 它會把一個 stdlib-only 的 runtime 變成需要 LLVM 工具鏈的 runtime。對「要下實單、要穩」的系統,這個交換不划算。

**Cython / mypyc**:mypyc 官方自陳「currently alpha software, only recommended for production with careful testing」。copycat 有完整 type annotation(pyright basic mode),理論上 mypyc 可吃 —— 但 alpha + Windows + 要下實單 = **不建議**。

**真正該做的替代方案**:先用 §10 的 M3 profile 找出熱路徑上具體哪幾個函式,然後用 **`__slots__` / dataclass(slots=True) / 預先算好的 lookup table / 避免 dict copy** 這些**零相依**手段處理。以這個 codebase 的形狀,這些手段的收益大於 JIT,而且不引入任何工具鏈風險。

> 註:`docs` / memory 提到 W3 B1 曾試過 `slots=True` 被拒絕(`bars-cache-daily-entry-shipped.md`:「S-03 slots=True 拒絕」)。那是針對某一個 cache entry 的個案決定,不是全庫政策 —— 熱路徑上的 tick/quote 物件值得重新評估。

來源:https://numba.readthedocs.io/en/stable/release/0.61.0-notes.html · https://github.com/mypyc/mypyc

---

## 3. 後端 — 序列化(**本區最高 ROI**)

### 3.1 現況

- WS 推播、HTTP response 全走 FastAPI 預設 → `json.dumps`(CPython 純 Python 的 `json` encoder,Starlette `JSONResponse`)。
- TC4 入站 tick 走 `copycat/live/tc4.py:1245` `raw.decode("utf-8")` + `json.loads`(推測,需 §10 M4 確認實際解析法)。
- FinMind / MIS 外呼回應走 `urllib` + `json.loads`。

**這是每 tick 都在跑的東西**(~數百次/秒 × 50 檔訂閱),而且同一份資料會被序列化兩次(入站解一次、出站編一次)。

### 3.2 候選

```
msgspec  0.21.1  2026-04-12  win=win_amd64,win_arm64  free-threaded wheels=8 ✅
orjson   3.12.0  2026-08-14  win=win32,win_amd64,win_arm64  free-threaded wheels=0
```

| | orjson | msgspec |
|---|---|---|
| 定位 | 純 JSON encode/decode 替換 | JSON + MessagePack + schema 驗證 + `Struct` 資料型別 |
| 效能 | 顯著快於 stdlib `json` | **decode into `Struct` 比 orjson decode 成 dict 還快**(官方 bench:msgspec-struct 0.25 s vs orjson 0.45 s,同一筆 str/int/object 混合資料) |
| 無 schema 時 | — | 與 orjson 同級 |
| free-threaded wheel | **無** | **有(8 個)** |
| 額外好處 | 無 | `Struct` 是 C 層實作、**自帶 `__slots__` 語意 + 比 dict 省記憶體**,可以直接當熱路徑的資料容器用 |
| API 侵入性 | 低(換 `JSONResponse` 的 render) | 中(要定義 Struct 型別) |

**建議:選 msgspec,不要選 orjson。**

理由不只是「decode 比較快」,而是 **msgspec 的 `Struct` 同時解掉兩個問題**:
1. wire 序列化(取代 `json`)
2. 熱路徑的資料容器(取代 dict / 取代沒有 slots 的 dataclass)—— 這是 §2.5 講的「真正該做的替代方案」,msgspec 剛好一次給。

而且 msgspec 有 free-threaded wheel,orjson 沒有 —— 如果未來要走 §5.5 的 free-threading 路線,orjson 會是卡住的那一個。

**⚠️ 契約硬約束(必須點名)**

換序列化層會碰到 CLAUDE.md §4 的多條「跨檔契約」。這些契約全部是**「wire 欄名逐字」**型,序列化換掉但欄名不變就安全;**但只要 msgspec Struct 的欄名 ↔ wire 欄名有任何自動轉換(例如 camelCase 化),整批契約會同時靜默斷掉且零錯誤訊號**:

| 契約 | 產生點 | 讀者 | 換 msgspec 時的紀律 |
|---|---|---|---|
| 個股逐筆 `ticks` 打包 | `copycat/server/stock_engine.py::_flush_ticks` | `frontend/src/hooks/useStockStream.ts` `case "ticks"` | item 欄位 `{code,t,p,q,side,b,a,h,l,seq}` 逐字保留、**無 `type` 欄**;前端 `default` 分支會靜默丟棄 |
| WS 心跳 | `copycat/server/ws.py::WS_HEARTBEAT_SECS` 送 `{"type":"ping"}` | `frontend/src/lib/ws-reconnect.ts::WS_SILENCE_TIMEOUT_MS` | ping 走 relay 直送、不經 per-client queue —— 換序列化要確認這條旁路仍在 |
| API error shape | 全後端 | 前端解 `detail.error` | `{"detail":{"error":"<code>"}}` 不可變形 |
| `avg_source` / `today_qty` | `capital/client.py::_on_profit_complete`、`capital/store.py` | `PriceLadder.tsx` / `lib/position-summary.ts` | snake_case wire 名不可被自動轉 camel |
| `tape_omitted` / `handover.attempt` / `meta.status` | 各自 | `useStockStream` / `ConnectionBadge` / `useMarketBars` | 同上;缺欄一律靜默降級 |
| 政策列 `kind="policy"` + `policy ∈ {P,B-a,B-b,S}` | `signal_hub.py::_emit_policies` | `lib/signal-model.ts` | 字面值 |

另外:**`server/signal_hub.py` 的 jsonl 落檔(`data/signals/*.jsonl`)是研究目錄的離線真相源**,CLAUDE.md §4 明文「回填改成整檔 dumps → 舊列鍵序 / 浮點字面變動,對帳 diff 整檔紅」,且 `tests/server/test_signal_outcome.py` 做 **byte 比對**。
→ **jsonl 落檔這條路一律保留 stdlib `json.dumps`,不要換 msgspec**(msgspec 的浮點字面與鍵序不保證與 stdlib 相同)。這是一個「換序列化但要留一個例外」的明確邊界。

### 3.3 pickle protocol 5

- Python 3.8 起內建,3.13 預設 protocol 就是 5(`pickle.DEFAULT_PROTOCOL == 5`)。
- 價值在 **out-of-band buffer(零複製)**,但那只有在跨進程傳大 buffer 時才有意義。
- copycat 目前**沒有多進程**(單 uvicorn 進程 + threads)。

**判斷:不要動。** 除非走 §5.6 的 shared memory 多進程架構,否則 pickle5 是無用的優化。且 pickle 不可拿來當跨版本落檔格式(反序列化任意 pickle 也是安全風險,對會下單的系統不該引入)。

來源:https://msgspec.dev/benchmarks · https://github.com/msgspec/msgspec

---

## 4. 後端 — HTTP client

### 4.1 現況是明確的問題

- 21 處 `import urllib`,runtime 相依裡**沒有** httpx / aiohttp。
- `urllib.request.urlopen` 是**同步阻塞**。只要它被 async route / async task 直接呼叫,就會把整個 event loop 釘住 —— 所有 WS 推播、所有其他 request 一起停。
- 已知的外呼:FinMind(chip / breadth / 家數)、TPEx MIS 5 s poll(`copycat/server/mis.py`)、Discord webhook(`copycat/notify.py`)。
- MIS 是 **5 秒一次 poll**,FinMind breadth 是盤中週期性 poll。這些**不是偶發**,是常態流量。

> 本區只做選型;「urllib 是否真的在 async context 被直呼、有沒有被 `to_thread` 包起來」屬於 Q1/Q3 的 code 掃描範圍。**選型結論不受影響**:不管有沒有包 thread,換成原生 async client 都更好(省掉 thread pool 往返 + 拿到連線池)。

### 4.2 候選(2026-09-13 實測)

```
httpx     0.28.1   已在 .venv(dev extra)     win=NONE(純 Python,無需 wheel)
aiohttp   3.14.3   已在 .venv(discord.py 拉進來)
niquests  3.21.1   2026-08-28   純 Python
```

| | httpx | aiohttp | niquests |
|---|---|---|---|
| 成熟度 | 高,事實標準 | 高,大型 async 系統多年 | 新,requests 的維護分支 |
| HTTP/2 | ✅(需 `httpx[http2]`) | ❌ | ✅ + **HTTP/3** |
| sync + async 同一 API | ✅ | 只有 async | ✅ |
| 連線池 | ✅ | ✅ `TCPConnector` | ✅ |
| 二手 bench(1000 req) | 2.087 s | 1.351 s | **0.551 s** |
| 是否已在機器上 | ✅ | ✅ | ❌ |

### 4.3 建議

**選 httpx。**

不是因為它最快(bench 上它最慢),而是因為:
1. **它已經在 `.venv` 裡**(dev extra),把它從 dev 提到 live extra 是一行 pyproject 改動,零新風險。
2. **測試已經在用它**(`dev = [... "httpx>=0.27" ...]` 是 FastAPI TestClient 的相依)—— 團隊已經熟悉。
3. sync + async 同 API,代表 `copycat/cli.py` 的離線腳本與 `copycat/server/` 的 async 路徑可以共用同一個 client 封裝與同一套 retry 策略(backend-conventions skill 已有 HTTP retry 慣例)。
4. FinMind / MIS 這種「每 5 秒打一次 localhost 外的小 JSON」場景,**瓶頸是網路 RTT 不是 client 開銷**。bench 上那 1.5 秒差距在 1000 req 才看得出來,copycat 一整天也打不到 1000 次 MIS。

**niquests 不建議**:HTTP/3 對 FinMind/TPEx 沒有意義(對方不支援),新套件 + 要下實單的系統 = 不對等的風險。
**aiohttp 不建議另外導入**(雖然已被 discord.py 帶進來):只有 async API,離線 CLI 那半要另寫一套。

**真正的收益點不是換哪個 client,而是「建一個長生命週期的 `AsyncClient` 放在 app lifespan 裡重用連線池」** —— 現況每次 `urlopen` 都是新的 TCP + TLS 握手。對 FinMind(HTTPS)這是每次 ~100–300 ms 的白給延遲。

⚠️ **契約**:`copycat/notify.py` 的 Discord webhook 有「429 Retry-After 重試一次」與「never-raise / URL 未設 no-op」語意(CLAUDE.md §3 config 節),換 client 要原樣保留;`copycat/server/mis.py` 是「非契約公開端點,失敗 None 降級」,也要保留。

來源:https://pypi.org/project/niquests/ · https://decodo.com/blog/httpx-vs-requests-vs-aiohttp

---

## 5. 後端 — 併發與服務

### 5.1 uvloop:Windows 不支援,實測確認

```
uvloop  0.22.1  2025-10-16  win wheels = NONE
```

PyPI 上 uvloop 最新版**零個 Windows wheel**,且官方 repo 有一個 PR(#606)標題就是「Redirect windows users trying to install uvloop to winloop」。這件事**不會改變**,因為 uvloop 綁 libuv 的 Unix 路徑假設。

→ **結論:在這個專案的部署形狀(Windows 桌面 + TC4 常駐)下,uvloop 永遠不在選項裡。** CLAUDE.md §5 已經寫死「非 headless 友善,Linux Docker 不在規劃內」,所以也不能靠「搬去 Linux」繞過。

### 5.2 winloop:唯一替代,但要自己承擔

```
winloop  0.6.3  2026-04-27  win=win_amd64,win_arm64  free-threaded wheels=2 ✅
```

官方 README(直接抓)宣稱:
- TCP 連線 bench:winloop **0.493 s** vs `WindowsProactorEventLoopPolicy` **2.510 s** vs `WindowsSelectorEventLoopPolicy` **2.723 s**
- 「約 5 倍 於 Selector policy」、「與 uvloop 同級」
- 用法:`import winloop; winloop.install()`

**已知差異 / 限制**(README 自陳):
- **Forking 完全停用**(Windows 本來就沒有 fork,無影響)
- 「Some smaller API calls had to be changed」—— 與 uvloop 有 API 差異
- subprocess 改為釋放 GIL 而非 fork
- 順帶修掉 Python 3.9 Windows 的 SSL 問題

**maturity 評估(誠實版)**:
- 版本號還在 **0.6.x**,還沒到 1.0。
- 專案的長期計畫是「把 winloop 併回 uvloop 然後自己退場」—— 這對「會不會斷維護」是好訊號,對「現在能不能靠它」是中性訊號。
- 官方 README **沒有** production-ready 的明確宣告,也沒有 production 警語。

**判斷:有條件導入 —— 但必須先量測,不要因為「5 倍」這個數字就上。**

那個 5 倍是**建大量 TCP 連線**的 bench。copycat 的 loop 上跑的是:
- ~8 條 WebSocket(前端頁面)—— 長連線,不是 accept 風暴
- 5 s 一次的 MIS poll
- 從 ZMQ thread 丟回來的 `call_soon_threadsafe`
- 0.1 s 的 `call_later` tick flush

**這些全是「少量長連線 + 大量 timer/callback」,不是「高 accept rate」。** winloop 在這種形狀下的收益很可能**接近零**,因為瓶頸不在 loop 的 socket 層。

而風險是實的:換 event loop 會直接影響 CLAUDE.md §4 的**「關機預算三方同源」**契約 ——
`copycat/server/shutdown_budget.py::run_grace_secs()`(現值 83 s)是 `run.ps1` 讀走當 graceful 上限、`__main__.py` 傳給 uvicorn `timeout_graceful_shutdown`、`app.py` lifespan 跑並行 lane 的**同一顆數字**;換 loop 改變了 socket close / drain 的時序特性,這個預算要重新實測。`tests/server/test_shutdown_budget.py` 釘的是不等式與 run.ps1 字面 parity,**不會**幫你抓到「實際 drain 變慢了」。

→ **先做 §10 的 M5 A/B 量測(30 分鐘可得答案),有數字再決定。** 不要當成必做項。

來源:https://github.com/Vizonex/Winloop · https://github.com/MagicStack/uvloop/pull/606

### 5.3 ASGI server / 框架:FastAPI vs Litestar vs Granian

```
uvicorn   0.52.4  2026-08-19  (純 Python)
fastapi   0.141.1 2026-07-29  (純 Python)
granian   2.8.2   2026-08-23  win=win_amd64 ✅  free-threaded wheels=11
litestar  2.24.0  2026-06-11  (純 Python)
```

**Granian**:官方自陳「single-dependency HTTP server binary distributed as a Python wheel for Linux, macOS, and **Windows**」,支援 ASGI/3 + RSGI + WSGI、HTTP/1 + HTTP/2 + websockets。PyPI 實測 win_amd64 wheel ✅。二手 bench 宣稱比 uvicorn plaintext 快 ~35%。

**Litestar**:用 msgspec 取代 pydantic 做序列化,啟動時把 route handler / DI tree 編成執行圖。二手宣稱 2x、遷移案例宣稱 40–120% 改善。

**判斷:兩個都不要動。這是本區最重要的「不要做」。**

理由:

1. **量級不對。** 那些 bench 測的是「plaintext / 小 JSON 的 req/s 上限」,數萬 QPS 量級。copycat 的 HTTP 流量是**一台瀏覽器**在打幾支 `/api/...`,加上 8 條 WS。req/s 是**個位數到兩位數**。把 server 層的 per-request overhead 從 50 µs 降到 35 µs,在這裡是零。

2. **換 ASGI server 會同時打破兩條已釘死的契約:**
   - **關機預算三方同源**(§5.2 已述):`uvicorn.run(..., timeout_graceful_shutdown=WS_DRAIN_SECS)` 這一行是契約的一角,Granian 的 graceful 語意不同,`run.ps1` 的 83 s 預算要整組重算,`tests/server/test_shutdown_budget.py` 的 run.ps1 字面 parity 會紅。
   - **WS 心跳契約**:現況 WS 走 `WebSocketsSansIOProtocol`(§1.1 實測),`copycat/server/ws.py` 的 relay 直送 ping、per-client queue 1000、`WsBroadcaster.dropped` + 「佇列滿」WARNING 這整套背壓機制,是**貼著 uvicorn 的 WS 實作寫的**。CLAUDE.md §4 明文:後端停送 ping 的症狀是「所有 WS 每 ~35 s 重連一次,uvicorn access log 每半分鐘一輪 8 條握手」——換 server 後這個判準連 log 格式都不一樣了。

3. **換框架(FastAPI → Litestar)代價更大**:API error shape `{"detail":{"error":"<code>"}}` 是 Starlette `HTTPException` 的形狀,Litestar 的 error envelope 不同 → 前端 `detail.error` 解析全面斷。而 copycat 的所有 route 幾乎不做 pydantic 驗證(看 `PositionCloseBody.kind` 那類極簡 model),所以 Litestar 最大的賣點(msgspec 取代 pydantic 驗證)在這裡**收益接近零**。

**真正該做的**:如果要吃 msgspec 的序列化紅利,**不必換框架** —— 在 FastAPI 裡自訂一個 `MsgspecResponse(Response)` 覆寫 `render()` 即可,是十幾行的事,且不動任何契約。

來源:https://github.com/emmett-framework/granian · https://asgi.readthedocs.io/en/latest/implementations.html · https://dev.to/locionic/fastapi-vs-litestar-2026-performance-benchmarks-when-to-switch-epf

### 5.4 pyzmq + asyncio:現況已是正解

```
pyzmq  27.2.0  2026-08-20  win=win32,win_amd64,win_arm64  free-threaded wheels=13
```

`zmq.asyncio` 的官方與社群共識:
- 它基於 `zmq.Poller`,「doesn't work well with massive non-zmq socket usage」
- **「not recommended to be used with web servers like aiohttp」**
- `zmq.asyncio` 不能與其他 loop 實作(如 uvloop)良好共存

而 copycat 目前是 **`threading.Thread` + 阻塞 `sock.recv()`**(`copycat/live/tc4.py:1185`、`:1245`)。

→ **這正是官方建議在「ZMQ + web server 同進程」時該走的路。現況已經對了,不要改成 `zmq.asyncio`。**

額外好處:阻塞 recv 在 thread 裡跑,**GIL 在 `zmq_recv` 的 C 呼叫期間是釋放的**,所以這個 thread 真的能跟 event loop 並行。換成 `zmq.asyncio` 反而會把 ZMQ 的 poll 塞進 event loop,讓 tick 解析跟 WS 推播搶同一條時間線。

**唯一值得檢查的是交接點**(Q1/Q3 範圍):thread → loop 的移交是否用 `loop.call_soon_threadsafe` 且**不帶大量資料複製**。

來源:https://pyzmq.readthedocs.io/en/latest/api/zmq.asyncio.html · https://github.com/aio-libs/aiozmq

### 5.5 Python 3.13/3.14 free-threading

事實:
- Free-threaded build 在 **3.13 是 experimental**,**3.14(2025-10-07 發布)經 PEP 779 升為官方支援(Phase 2)**,不再是實驗性。
- **3.13t 的單執行緒效能比一般 build 慢約 40%**;3.14 大幅改善(但仍有成本)。
- 3.14 另有 tail-call interpreter,Windows x86-64 build 的問題已修好。
- 主要套件的 free-threaded wheel 狀況(我實測的 `cp313t`/`cp314t` wheel 數):
  numpy 13 ✅ · pyzmq 13 ✅ · granian 11 ✅ · msgspec 8 ✅ · pandas 8 ✅ · pyarrow 7 ✅ · numba 4 ✅ · winloop 2 ✅
  **polars 0 ❌ · orjson 0 ❌ · duckdb 0 ❌**

**判斷:free-threading 現階段明確不要。**

1. copycat 現在跑 **3.13.13(非 t build)**。要吃 free-threading 得先升 3.14 才有官方支援 —— 那是另一件事。
2. 更關鍵:**`comtypes` / `pywin32`(群益 Capital 下單)在 free-threaded build 下的狀況完全未查證**,而 COM 本身有 apartment threading model(`copycat/capital/client.py` 已經是「COM 專屬執行緒」設計)。把 GIL 拿掉去碰 COM,是拿下單路徑做實驗。
3. copycat 的並行瓶頸不是 CPU-bound multi-thread,是 IO 與 callback。free-threading 對它沒有可指名的收益。

**但 Python 3.14(一般 build)本身值得評估**:官方宣稱最高 30% 的直譯器改善,且是純升版、零 API 改動。這是「零風險拿免費效能」的少數選項之一。
⚠️ 阻擋點:`polars` classifiers 沒列 3.14、`numba` 對 3.14 的狀況未查證。若不導 polars/numba,升 3.14 的阻力主要只剩 `comtypes`/`pywin32`/`pyzmq` 三個 binary 相依 —— 全都要實測(§10 M6)。

來源:https://docs.python.org/3/howto/free-threading-python.html · https://www.phoronix.com/news/Python-3.14 · https://py-free-threading.github.io/

### 5.6 即時數值共享:Redis / shared memory / mmap ring buffer

**判斷:三個都不要。這是目前選型清單裡最明顯的過度工程。**

- copycat 是**單進程**(單 uvicorn、無 workers)。shared memory / mmap ring buffer 解的是**跨進程**零複製問題 —— 這個問題現在不存在。
- Redis 會在 localhost 上多一個 server process + 序列化往返 + 網路 syscall,**比現況的 in-memory dict 慢**。CLAUDE.md §5 已明文「沒有 DB:state = React client + filesystem JSON cache;ZMQ tick 流 in-memory 不持久化」—— 這個決定是對的。
- 二手資料確實指出「shared memory + lock-free ring buffer 可達 sub-microsecond」、「LinkedIn 的 context switch 從 100K/s 降到近零」—— **但那是跨進程、跨機器、百萬 msg/s 的場景**。copycat 是數百 tick/s 單進程。差了三到四個量級。

**唯一會讓它變成選項的觸發條件**:如果未來要把「TC4 接收 + 訊號計算」與「HTTP/WS 服務」拆成兩個進程(例如為了讓 server 重啟不掉 tick 流)。那時 `multiprocessing.shared_memory` + 一個固定容量 ring buffer 才有意義。**現在不是。**

來源:https://howtech.substack.com/p/ipc-mechanisms-shared-memory-vs-message

---

## 6. 前端 — 圖表(本專案前端的**唯一**真瓶頸候選)

### 6.1 問題定義

場景(user 明確提出):**每 0.1 秒更新 + 50 張小圖同時**。

現況:`CardIntradayChart.tsx`(71 LOC)包 `StockIntradayChart.tsx`(1724 LOC),幾何由 `lib/stock-intraday-svg.ts`(921 LOC)算,最後**用 React 渲染 SVG 元素**。

`CandleChart.tsx:221` 的形狀:
```tsx
{g.candles.map((c, i) => (
```
每根 K 線一個 React element。50 張卡 × 每張 ~270 個分時點 + overlay 線 + 標籤 ≈ **上萬個 DOM 節點**,而且每次更新都要走 React reconciliation(即使 memo 擋住大部分,commit 一次仍要 diff)。

CLAUDE.md §1 已經記到症狀:「dev build 的 React Component Performance Track 已由 dev-perf-guard 堵住洩漏,但 **props-diff 開銷仍在** —— 整天掛著一律用 prod build」。這句話本身就是「SVG + React 元素這條路已經頂到天花板」的自白。

### 6.2 候選(2026-09-13 npm registry 實測)

| 套件 | 版本 | 最後發布 | 授權 | unpacked | deps | 渲染 |
|---|---|---|---|---|---|---|
| **lightweight-charts** | **5.2.1** | 2026-08-12 | Apache-2.0(**需署名**) | 3.1 MB | 1 | Canvas 2D |
| **uPlot** | 1.6.32 | **2025-03-14**(18 個月無發布) | MIT | 545 KB | **0** | Canvas 2D |
| klinecharts | 10.0.3 | 2026-08-27 | Apache-2.0 | 2.9 MB | **0** | Canvas 2D |
| echarts | 6.1.0 | 2026-05-19 | Apache-2.0 | **60 MB**(可 tree-shake) | 2 | Canvas / SVG 可選 |
| recharts | 3.10.1 | 2026-07-25 | MIT | 7.5 MB | 11 | **SVG**(每點一個節點) |
| @visx/visx | 4.0.0 | 2026-06-11 | MIT | 12 KB(meta,拉 33 個子套件) | 33 | **SVG** |
| highcharts | 13.0.2 | 2026-08-27 | **商用授權(付費)** | 72 MB | 0 | SVG / Canvas boost |

**逐個排除:**

- **Recharts ❌** — SVG per-point。「performance can drop with larger datasets because each point generates an SVG node」。這**正是現況的問題**,換過去等於原地踏步還多 7.5 MB。
- **visx ❌** — 也是 SVG,而且它是「低階 primitive 集合」不是圖表庫;copycat 已經有 1275 LOC 的自製幾何層,visx 能取代的正好是**已經寫好而且有 golden fixture 釘住的那一半**,能留下的正好是**現在慢的那一半**。負收益。
- **Highcharts ❌** — 商用授權(要下實單 = 商業使用,必須買),72 MB,SVG 為主。對單機自用工具是不必要的法務與成本負擔。
- **ECharts ⚠️** — 技術上可行(canvas、能處理 10 萬點、Apache-2.0),但:60 MB 完整包(雖可 `echarts/core` tree-shake 到 ~150–300 KB)、API 是 option 物件宣告式、**不是為金融 K 線設計**(要自己拼 candlestick series + 十字線 + 副圖)。用來畫 `AdvanceDeclineChart` / `PnlChart` 這種普通圖 OK,用來畫主圖過重。
- **uPlot ⚠️** — 技術上最誘人(545 KB、零相依、「150,000 點冷啟動 90 ms、約 31,000 點/ms 線性」、最佳 cursor/zoom 效能),**但**:
  - **最後發布 2025-03-14,已 18 個月**。這對「要下實單」的系統是實質風險(瀏覽器 API 變動、安全修補)。
  - 原生**沒有 candlestick**(官方 demo 有 OHLC 範例,但要自己寫 path renderer)
  - 沒有 React 綁定(要自己寫 imperative wrapper)
  - 作者自陳:「if you need 60fps with massive streaming datasets, uPlot can only get you so far」
- **lightweight-charts ✅ 首選** — TradingView 出品,**專為金融即時資料設計**:
  - Canvas 2D、基礎 bundle **35 KB**(官方數字,v5 較 v4 再減 16%)
  - **官方明文建議即時流用 `update()` 而非 `setData()`,只重畫變動部分**
  - v5 修掉「series markers pane 每次 mousemove clone 整份資料集」的效能問題 —— 這正是 copycat 的圖有大量 marker(成交點 fills、極值標記、CDP/MA 疊線)的場景
  - 原生 candlestick / bar / line / area / histogram + 多 pane + 十字線 + price scale,copycat 需要的形狀都是內建的
  - 積極維護(2026-08-12 發布 5.2.1)

### 6.3 對「50 張小圖 @ 0.1 s」的具體建議

**主圖(`StockChart` / `CandleChart` / `StockIntradayChart` 單檔頁)→ lightweight-charts。**
- 它就是為這件事做的,`update()` 的增量重繪對 0.1 s 節奏綽綽有餘。

**圖牆 50 張卡(`GroupGridView` + `CardIntradayChart`)→ 這裡要分開想,不要直接套同一個庫。**

50 個 lightweight-charts 實例 = 50 個 canvas + 50 套事件監聽 + 50 份內部資料結構。**這可能比現況更糟。** 小卡片需要的只是「一條折線 + 一條基準線 + 顏色」,不需要十字線、不需要 price scale、不需要 marker。

三個選項,建議順序:
1. **保留自製幾何層,只把渲染從「React SVG 元素」換成「單一 `<path d="...">` 字串」**(零新相依)。
   `buildIntradayGeometry` 已經吐出座標;把 `points.map(p => <circle/>)` 改成一個 `pts()` 串出的 path `d`,DOM 節點數從 O(點數) 降到 O(1)。**這是投報率最高、風險最低的一步,而且不需要任何套件。**
   註:`lib/svg-points.ts::pts` 已經存在(`CandleChart.tsx:18` 有 import),代表這條路專案裡已有基礎設施。
2. 若 (1) 不夠:**一張 canvas 畫 50 張小圖**(單一 `<canvas>` + 手動分格繪製)。一個 rAF、一個 context、50 個 viewport。這是 50 個 canvas 實例的反面,開銷是 1/50。
3. **OffscreenCanvas + Web Worker**(§7.4)—— 只有在 (1)(2) 都不夠時。

**⚠️ 契約硬約束(換圖表庫時必須同動的)**

| 契約 | 為什麼會被碰到 |
|---|---|
| **CDP/MA 前後端同式**(`copycat/server/overlay.py::compute_cdp/compute_ma` ↔ `frontend/src/lib/futures-overlay.ts`,golden fixture `tests/fixtures/overlay_parity.json`) | **絕對不可以改用圖表庫內建的 MA/indicator**。lightweight-charts 沒有內建 MA(要自己餵 line series),所以只要**繼續用 `futures-overlay.ts` 算完再餵給圖表庫**就安全。若哪天用了 ECharts 的 `markLine` 或任何內建 indicator,parity 立刻斷且**兩張圖都畫得出來、零錯誤訊號**。 |
| **台指期疊線分鐘鍵 = 1K 終點標記 −1 分**(`lib/txf-overlay-series.ts::txfBarsToSeries`) | 換渲染層時這個 −1 必須留在資料轉換那一層,不要順手搬進渲染層 |
| **即時末根分鐘鍵 = accum 起點分 +1、上限 13:30**(`lib/live-last-bar.ts::mergeLiveMinuteBars`) | 同上;`lib/live-last-bar.test.ts` 案 1/2/9 會紅 |
| **日 K 定稿界 14:00**(`lib/day-bars-rollover.ts::DAILY_FINAL_TIME` ↔ `copycat/server/bars.py::DAILY_FINAL_TIME`) | 在資料層,不受渲染層影響 —— 但 `StockChart.tsx` 的「即時末根定稿閘」讀者要跟著搬 |
| **江波圖調色盤色數 ≥ 腿數**(`river-colors.ts` 三組字面 class + `index.css` 的 `--color-river-N` token,`tests/test_corr_config.py::test_river_palette_covers_every_leg` 讀原始碼字面鎖住) | 換圖表庫 = 顏色從 Tailwind class 變成 canvas fillStyle 字串,那條**讀原始碼字面**的後端測試會紅。要先改測試的讀法。 |
| 台股慣例 **紅漲綠跌** | lightweight-charts 預設是綠漲紅跌(歐美慣例),`upColor`/`downColor` 必須顯式設定。`CandleChart.tsx:35-39` 的 `BODY_CLASS` 已註明「台股慣例:紅漲(bull)/ 綠跌(bear)」。**這是最容易漏、後果最嚴重的一條:看錯漲跌方向去下單。** |
| **Apache-2.0 署名義務** | lightweight-charts 授權要求在使用者可見的頁面標示 TradingView 並連結 https://www.tradingview.com/;可用 `attributionLogo` chart option 滿足。自用工具也要遵守。 |

來源:
- https://github.com/tradingview/lightweight-charts · https://tradingview.github.io/lightweight-charts/tutorials/demos/realtime-updates · https://tradingview.github.io/lightweight-charts/docs/release-notes
- https://github.com/leeoniya/uPlot · https://cprimozic.net/notes/posts/my-thoughts-on-the-uplot-charting-library/
- https://blog.logrocket.com/best-react-chart-libraries-2026/

---

## 7. 前端 — 狀態、渲染、build

### 7.1 React Compiler

```
babel-plugin-react-compiler  1.0.0  2025-10-07(v1.0 正式版)
eslint-plugin-react-hooks    7.1.1  2026-04-17(內含 compiler lint rules)
```

- **2025-10-07 已 stable / production-ready**,Meta 內部大規模驗證過。
- 官方數字:初次載入與跨頁導航最多改善 ~12%,部分互動快 2.5x 以上,記憶體持平。
- 安裝(官方 Vite 指引,需 Vite ≥ 6.0 + `@vitejs/plugin-react`):
  ```js
  import react, { reactCompilerPreset } from '@vitejs/plugin-react';
  import babel from '@rolldown/plugin-babel';
  plugins: [react(), babel({ presets: [reactCompilerPreset()] })]
  ```
  ⚠️ 這是 **Vite 8 / plugin-react 6.x 的寫法**。copycat 現在是 Vite 6.4.3 + plugin-react 4.7.0,寫法是舊的 `babel: { plugins: [['babel-plugin-react-compiler', {}]] }`。
- **違反 Rules of React 的元件會被自動跳過**(安全降級,不會炸)。先跑 `npx react-compiler-healthcheck@latest` 看覆蓋率。

**判斷:建議導入,而且優先序很高。**

理由:copycat 前端**到處是手寫 memo 護欄**,而且這些護欄的脆弱性已經在註解裡寫明:
```tsx
// CandleChart.tsx:53
/** 穩定 identity 的空線:`[]` 字面量每次 render 都是新 array,會打穿 ChartStatic 的 memo。 */
const EMPTY_LINE: { x: number; y: number }[] = [];
```
```tsx
// CardIntradayChart.tsx:24,28,30
/** 同一個 localStorage key,而 `set` 每次 render 都是新 identity,傳進來還會打穿 memo。 */
/** 無成交的卡每秒都會因為新陣列而打穿 `GroupCard` 的 memo(W-5)。 */
/** 圖牆層只在指數 toggle 開著時才傳(關著恆 null,memo 不被打穿) */
```
還有專門的 memo 測試檔:`GroupGridView.memo.test.tsx`、`StockIntradayChart.memo.test.tsx`。

**這種「靠人維護 referential identity」的架構正是 React Compiler 要取代的東西**,而且它在 50 張卡 × 0.1 s 的場景下每一次打穿都是實打實的重繪。

⚠️ 但有一條**專案特有的紀律**:copycat 的完成前 gate 含 `npx react-doctor@latest --scope changed`(CLAUDE.md §1),而 doctor「只有新增 finding 算 FAIL」。開 compiler 會改變產出的 code 形狀,要先確認 doctor 不會噴一批新 finding。另外 `eslint-plugin-react-you-might-not-need-an-effect`(devDeps)與 compiler 的 lint 可能有重疊訊息。

**建議路徑**:先升 `eslint-plugin-react-hooks` 到 7.x 拿 compiler lint(零 runtime 風險),跑 healthcheck 看有多少元件會被跳過,**有數字再決定要不要開 compiler**。

來源:https://react.dev/blog/2025/10/07/react-compiler-1 · https://react.dev/learn/react-compiler/installation

### 7.2 外部 store(zustand / jotai / valtio / signals / TanStack Store)

```
zustand               5.0.15  2026-?     MIT  95 KB   deps=0
jotai                 3.0.0   2026-09-08 MIT  112 KB  deps=0   ← 剛發 v3 major
valtio                2.3.2   2026-05-01 MIT  101 KB  deps=1
@preact/signals-react 3.12.0  2026-08-04 MIT  193 KB  deps=2
@tanstack/store       0.11.1  2026-08-05 MIT  123 KB  deps=0   ← 還在 0.x
```

二手 bench(1000 個元件訂閱、單次更新,M1 MBP / React 18.2):
Signals **3 ms** < Zustand 12 ms < Jotai 14 ms < Redux Toolkit 18 ms;記憶體 Signals 1.4 MB < Jotai 1.8 MB < Zustand 2.1 MB。

**判斷:全部不建議導入。這是第二個明顯的過度工程。**

理由:
1. copycat **現在沒有 global state 問題**。它的狀態拓樸是:TanStack Query 管 server state + 每個 hook 自己的 `useState`/`useRef` 管 accum + `lib/tick-stream.ts` 管逐筆 fanout。CLAUDE.md §4 的「`setTickView` / `useGroupLiveAccums` / `stock-accum.ts`」那一整套已經是一個**手刻但設計過的 pub-sub**。
2. 高頻更新的正確解法在 React 裡**不是換 store,是「不要讓高頻資料經過 React state」** —— 也就是 §6.3 的 canvas 路線:tick 進來直接畫,完全不 setState。換成 zustand/jotai 只是把 re-render 從 12 ms 變成 14 ms,**問題的量級沒變**。
3. jotai 剛在 **2026-09-08 發 3.0 major**(5 天前),TanStack Store 還在 **0.11.x**(pre-1.0)。對要下實單的系統,這兩個現在導入是自找麻煩。

**唯一可能有價值的**:`@preact/signals-react` 的 signal 可以做到「值變了但元件不 re-render,只更新一個 text node」。如果將來有「數字牆」型需求(例如 50 張卡的報價數字每 0.1 s 跳),signals 是對的工具。但那個場景現在用 canvas 或直接 DOM 操作也能解,且不引入一個會 patch React internals 的套件(`@preact/signals-react` 需要 `signals-react-transform` 或 runtime patching —— 對 React 19.2 的相容性**未查證**)。

來源:https://dev.to/jsgurujobs/state-management-in-2026-zustand-vs-jotai-vs-redux-toolkit-vs-signals-2gge · https://rohitimandi.medium.com/zustand-jotai-and-signals-a-head-to-head-comparison-of-granularity-and-efficiency-077599a4f68e

### 7.3 虛擬化

```
@tanstack/react-virtual  3.14.12  2026-09-11  MIT  56 KB  deps=0
react-window             2.3.1    2026-09-05  MIT  216 KB deps=0
react-virtuoso           4.18.13  2026-09-05  MIT  243 KB deps=0
```

⚠️ **更正一條常見的過時說法**:多篇 2026 文章說「react-window is stable but no longer actively developed」。**registry 實測顯示 react-window 2.3.1 在 2026-09-05 發布**(v2 是重寫版),所以那個說法已經不準。兩者都活著。

**判斷:有條件導入,範圍很窄。**

copycat 裡真正會長的列表只有兩個:
- `TickTape.tsx`(成交明細 tbody)—— 開盤時每秒數百筆,一天累積上萬列
- `SignalRail.tsx`(訊號列)—— 一天數十到數百列,**不需要虛擬化**

`TickTape` 是唯一的候選,而且 CLAUDE.md §4 有一條契約直接相關:
> 個股 `seq` 的兩個口徑 …… 讀者 = `frontend/src/lib/stock-accum.ts::fromSnapshot`(自 `snap.seq` **由尾回推**指派逐筆列的 React key `n`)…… 漂掉的症狀是**成交明細 tbody 靜默整片重掛**(畫面只是閃一下,零錯誤訊號)。

也就是說:**tbody 重掛已經是一個被監控的已知風險點**。導入虛擬化會改變「哪些列真的掛在 DOM 上」,那條 seq→key 契約的語意要重新想過(虛擬化下只有視窗內的列有 DOM,重掛的可觀測性會變)。

選 **@tanstack/react-virtual**:56 KB、零相依、與已在用的 `@tanstack/react-query` 同生態、headless(不強加 DOM 結構,tbody 佈局自己控)。

但**先量測**:如果 accum 本來就只留最近 N 筆(`stock-accum.ts` 很可能有上限,需確認),那 DOM 列數根本沒爆,虛擬化是白做。

### 7.4 Web Worker / OffscreenCanvas

```
comlink  4.4.2  2024-11-07(已 ~2 年無發布)  Apache-2.0  252 KB  deps=0
```

- **OffscreenCanvas 全球支援率 ~95%**,Chrome 69+ / Edge 79+ / Firefox / Safari 都有。本機自用 = 只要 Chrome 一種瀏覽器,**支援度不是問題**。
- comlink 只有 1.1 KB(min+gzip),把 `postMessage` 包成 async function 呼叫。但 **2024-11 之後沒發布**。

**判斷:comlink 不要導入;OffscreenCanvas 在 §6.3 的 (1)(2) 都不夠時才考慮。**

- comlink 解的是「worker 通訊的 DX」。copycat 若要用 worker,通訊協定是「一個 transferable OffscreenCanvas + 一串 tick」—— 這用原生 `postMessage` 寫 30 行就好,不值得為 DX 引入一個停更兩年的套件。
- OffscreenCanvas 真正的價值在「把 50 張圖的繪製搬離主執行緒」。**但前提是繪製真的是主執行緒瓶頸** —— 而現況的瓶頸極可能是 **React reconciliation + DOM 節點數**,不是繪製。先做 §6.3 (1),量一次,再決定。
- ⚠️ worker 拿不到 DOM,所以十字線 hover / tooltip / 點擊選取這些互動要主執行緒與 worker 協調。主圖(有豐富互動)不適合;圖牆小卡(幾乎無互動)才適合。

來源:https://web.dev/articles/offscreen-canvas · https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas

### 7.5 Build:Vite 6 → Vite 8(Rolldown + Oxc)

事實:
- **rolldown-vite 這個過渡套件已於 2026-03-19 封存唯讀**,因為它被併入 Vite 8 beta。
- **Rolldown 1.0 stable:2026-05-07**,API 鎖定 + 向後相容保證。
- **Vite 8 起 Rolldown 是預設 bundler,無需 opt-in**;Vite 也改用 **Oxc** 做 parse/resolve/transform/minify,esbuild + Rollup 雙 bundler 架構退場。
- registry 實測:**vite 8.3.0(2026-09-10)**、**@vitejs/plugin-react 6.1.1(2026-08-28)**。
- Rolldown 官方宣稱比 Rollup 快 10–30×,實際案例:Linear 46 s → 6 s、Beehiiv −64%、Mercedes-Benz −38%。
- `@vitejs/plugin-react-oxc` **已 deprecated**(功能併回 `@vitejs/plugin-react`)。
- **React Compiler 在 Vite 8 必須用 `@vitejs/plugin-react`(Babel 路徑),不能用 `plugin-react-swc`。**

**判斷:建議升級 Vite 6 → 8,但這是 DX 改善,不是 runtime 效能改善。**

要誠實說清楚:**Vite 升級改善的是「build / dev server 有多快」,不是「跑起來的頁面有多快」。** user 的需求是「看盤時夠順」,那是 runtime,Vite 8 不直接幫到。

但它仍值得做,因為:
1. copycat 落後兩個 major,拖越久遷移成本越高。
2. React Compiler 的官方 Vite 安裝路徑現在是寫給 Vite 8 / plugin-react 6.x 的(§7.1)。要開 compiler,順路升 Vite 比較省事。
3. `npm run build` 是完成前 gate 的一部分(CLAUDE.md §1),每天跑很多次;build 從 N 秒到 N/5 秒是實質的開發節奏改善。

⚠️ **風險**:Vite 8 的 migration guide 明文「If you are relying on specific Rollup or esbuild options, you might need to make some adjustments」。copycat 的 `vite.config.ts` 需要先看有沒有自訂 rollup options / esbuild options(本次未讀該檔,標記未查證)。另外 vitest 3.2.7 對 Vite 8 的相容性**未查證** —— 那會影響 3069 條前端測試。

**plugin 選擇**:維持 `@vitejs/plugin-react`(Vite 8 起它內部已用 Oxc 做 react-refresh transform,比 SWC 略快),**不要換 plugin-react-swc**(換了就不能開 React Compiler)。

來源:https://vite.dev/blog/announcing-vite8-beta · https://github.com/vitejs/rolldown-vite · https://vite.dev/guide/migration · https://github.com/vitejs/vite-plugin-react/discussions/1240

---

## 8. 對照總表(給 Fable 討論用)

情境固定為:**Windows 11 單機 / 後端前端同台 / TC4 桌面 app 常駐 / 要下實單 / 單一使用者**。

### 8.1 後端

| # | 現況 | 建議 | 預期收益 | 風險 / 契約 | 是否建議 |
|---|---|---|---|---|---|
| B1 | wire 序列化 `json` stdlib | **msgspec 0.21.1**(`Struct` + json) | 每 tick 的 encode/decode;Struct 同時當熱路徑容器省配置。量級:**中高**(熱路徑) | wire 欄名須逐字保留(`ticks` 打包 / `avg_source` / `tape_omitted` / `meta.status` / 政策列 kind 等 7+ 條契約);**`data/signals/*.jsonl` 落檔留 stdlib json**(byte 比對測試) | ✅ **強烈建議,最高 ROI** |
| B2 | `urllib` 同步外呼(21 處) | **httpx 0.28.1**(已在 venv,提到 live extra)+ lifespan 長生命週期 AsyncClient | 消除 loop 阻塞風險;省掉每次 TLS 握手 ~100–300 ms。量級:**高**(5 s poll 常態) | notify.py 的 429 Retry-After / never-raise、mis.py 的 None 降級要原樣保留 | ✅ **強烈建議** |
| B3 | 回測資料 = 1K atomic JSON + 手刻 loop | **DuckDB 1.5.5** 查詢層(+ 可選 Parquet 落檔) | 離線回測 / evidence 報表快 10–100×。量級:**離線**,不影響盤中 | 單寫入者(離線單進程無礙);不可用於即時落地 | ✅ 建議(離線範圍) |
| B4 | 同上 | **Polars 1.44.2**(`polars` + `polars-runtime-32`) | 特徵工程 / replay 批次。量級:**離線** | ①1.4x 拆成 runtime 子套件,鎖版方式要改;②若 CPU 無 AVX2 只能用凍在 1.33.1 的 `polars-lts-cpu`;③**不可進 `copycat/live/`**(row-at-a-time 是負優化) | ⚠️ 有條件(先驗 CPU;與 B3 擇一先上) |
| B5 | 無 numpy | numpy 2.5.3 | 幾乎無 —— B4 已涵蓋 | ⚠️ **`market.py` 毫元整數運算絕不可改 float**;`overlay.py::compute_ma` 有 golden fixture parity | ❌ 不建議單獨導入 |
| B6 | 無 numba / Cython / mypyc | — | 熱路徑是狀態機 + dict + str,JIT 無法加速;開盤首次編譯反而卡 | mypyc 官方自陳 alpha;引入 LLVM 工具鏈 | ❌ **不建議** |
| B7 | Proactor event loop(uvloop 無 Windows wheel) | winloop 0.6.3(`winloop.install()`) | bench 宣稱 5×,**但那是高 accept-rate 場景**;copycat 是少量長連線 + 大量 timer,推測收益 ≈ 0 | 0.6.x 未到 1.0;**打破「關機預算三方同源」契約**(83 s 要重測,run.ps1 parity) | ⚠️ **先量測(M5)再談**,不是必做 |
| B8 | uvicorn 0.51 + FastAPI 0.139 | Granian 2.8.2 / Litestar 2.24 | req/s 上限提升 —— **但這台機器的 HTTP 流量是個位數 req/s** | **同時打破關機預算 + WS 心跳兩條契約**;Litestar 另打破 `{detail:{error}}` shape | ❌ **明確不建議** |
| B9 | ZMQ 專用 thread + 阻塞 recv | 保持不變 | — | `zmq.asyncio` 官方不建議與 web server 同 loop | ✅ **不要動(已是正解)** |
| B10 | Python 3.13.13 一般 build | 3.14(一般 build) | 官方宣稱最高 30% 直譯器改善,純升版 | comtypes / pywin32 / pyzmq 在 3.14 的狀況要實測;polars classifiers 未列 3.14 | ⚠️ 有條件(M6 驗過再說) |
| B11 | 無 free-threading | 3.13t / 3.14t | 無可指名收益(瓶頸是 IO 非 CPU-bound thread) | 3.13t 單執行緒慢 ~40%;**COM(下單路徑)在 ft build 的行為未查證**;polars/orjson/duckdb 無 ft wheel | ❌ **不建議** |
| B12 | in-memory dict,無 DB | Redis / shared memory / mmap ring buffer | 負收益(單進程下多一層序列化 + syscall) | — | ❌ **不建議**(除非將來拆多進程) |
| B13 | uvicorn[standard] 已給 httptools + ws-sansio | 保持 | — | — | ✅ **不要動(已最佳)** |

### 8.2 前端

| # | 現況 | 建議 | 預期收益 | 風險 / 契約 | 是否建議 |
|---|---|---|---|---|---|
| F1 | 圖牆 50 卡:React SVG 元素 per 點 | **先把 `points.map(<circle/>)` 改成單一 `<path d>` 字串**(零相依,`lib/svg-points.ts::pts` 已存在) | DOM 節點 O(n) → O(1),React commit 大幅縮小。量級:**高**,**且零新相依** | 幾何層不動(golden fixture 安全) | ✅ **第一步就做這個** |
| F2 | 主圖手刻 SVG | **lightweight-charts 5.2.1**(Canvas 2D,35 KB base) | 專為即時金融設計,`update()` 增量重繪;v5 修掉 marker 重繪問題 | ①**紅漲綠跌必須顯式設定**(預設是歐美相反色,看錯方向 = 下錯單);②Apache-2.0 **需 TradingView 署名**(用 `attributionLogo`);③CDP/MA 仍須由 `futures-overlay.ts` 算完再餵,**不可用庫內建 indicator**(parity fixture);④江波圖 palette 那條「後端測試讀前端原始碼字面」的測試要改讀法 | ✅ 建議(主圖) |
| F3 | 圖牆 | 若 F1 不夠 → **單一 canvas 畫 50 格**(非 50 個庫實例) | 1 個 context / 1 個 rAF vs 50 份 | 互動(hover / 點選)要自己做命中測試 | ⚠️ 條件性(F1 量測後) |
| F4 | 手寫 memo 護欄遍佈(`EMPTY_LINE` sentinel、memo 測試檔 ×2) | **React Compiler 1.0**(先上 `eslint-plugin-react-hooks@7` + healthcheck) | 官方:互動最高 2.5×、導航 ~12%;消除「新 array identity 打穿 memo」這類人工債 | 違規元件自動跳過(安全);⚠️ `react-doctor --scope changed` 新 finding 算 FAIL,要先確認不噴一批;官方 Vite 安裝指引是寫給 Vite 8 的 | ✅ 建議(先 lint + healthcheck,有數字再開) |
| F5 | Vite 6.4.3 / plugin-react 4.7.0 | **Vite 8.3.0 + @vitejs/plugin-react 6.1.1**(Rolldown 1.0 stable + Oxc) | build 快數倍(**DX,非 runtime**);解鎖 React Compiler 官方安裝路徑 | migration guide 警告自訂 rollup/esbuild options;**vitest 3.2.7 對 Vite 8 相容性未查證**(3069 條測試) | ⚠️ 建議但排在 F1/F2 之後 |
| F6 | 無 plugin-react-swc | 維持不用 | — | 換了就**不能開 React Compiler** | ✅ 不要換 |
| F7 | 無外部 store | zustand / jotai / valtio / signals / TanStack Store | 幾乎無 —— 正確解是「讓高頻資料不經過 React state」(F1/F3),不是換 store | jotai 3.0 剛發(5 天前);TanStack Store 仍 0.x;signals-react 需 patch React internals(對 19.2 相容性未查證) | ❌ **不建議** |
| F8 | 無虛擬化 | @tanstack/react-virtual 3.14.12(56 KB,零相依) | 只對 `TickTape` 有意義;`SignalRail` 不需要 | ⚠️ 會改變「哪些列有 DOM」→ 影響 seq→React key `n` 那條契約的可觀測性;**先確認 accum 是否已有列數上限** | ⚠️ 條件性 |
| F9 | 無 worker | OffscreenCanvas(原生,~95% 支援;Chrome 本機 100%) | 把 50 卡繪製搬離主執行緒 | 只在 F1/F3 都不夠時;worker 無 DOM,互動要協調 | ⚠️ 最後手段 |
| F10 | 無 comlink | — | DX only;原生 postMessage 30 行搞定 | **2024-11 起無發布** | ❌ 不建議 |
| F11 | Recharts / visx / Highcharts / ECharts | — | Recharts+visx 是 SVG per-point(= 現況的病);Highcharts 要付費且 72 MB;ECharts 60 MB 且非金融專用 | — | ❌ 全部不建議 |
| F12 | uPlot | — | 技術最誘人(545 KB / 零相依 / 31k 點每 ms)但**最後發布 2025-03-14,18 個月無更新**、無原生 candlestick、無 React 綁定 | 維護風險 vs 要下實單 | ❌ 不建議(留作 F2 的備案) |

### 8.3 「明確該做」vs「過度工程」一句話版

**明確該做(在 Windows + 本機單機 + 下實單這個情境下):**
1. **F1** 前端圖牆 SVG 元素 → path 字串(零相依、零契約風險、量級最大)
2. **B2** urllib → httpx + 長生命週期連線池(消除 loop 阻塞風險,這是「不能塞住」的直接答案)
3. **B1** json → msgspec(熱路徑序列化 + Struct 當容器)
4. **F2** 主圖 → lightweight-charts(附三條契約紀律)
5. **F4** React Compiler(先 lint + healthcheck)
6. **B3** DuckDB 給離線回測

**明確是過度工程(不要做):**
1. **B8** 換 ASGI server / 框架(Granian / Litestar)—— 打破兩條契約,換來個位數 req/s 場景下的零收益
2. **B12** Redis / shared memory / ring buffer —— 單進程下是負優化
3. **B11** free-threading —— COM 下單路徑未知風險,無可指名收益
4. **B6** numba / Cython / mypyc —— 熱路徑形狀不對,JIT 編譯時機最糟
5. **F7** 外部 state 管理庫 —— 解錯問題
6. **B5** 單獨導 numpy —— 且 `market.py` 毫元整數是禁區

**要先量測才知道的(不要憑 bench 文章決定):**
- **B7** winloop(M5)
- **B10** Python 3.14(M6)
- **F8** 虛擬化(先確認 accum 列數上限)
- **F3/F9** canvas / OffscreenCanvas(F1 之後再量)

---

## 9. 這些地方不要動(反向結論,同等重要)

1. **`copycat/live/tc4.py` 的 ZMQ threading 模型**(`:1185` `threading.Thread` + `:1245` 阻塞 `recv()`)
   官方文件明說 `zmq.asyncio` 不建議與 web server 同 loop 用。現況已是正解,而且阻塞 recv 在 C 層會釋放 GIL,真正並行。改成 `zmq.asyncio` 是退步。

2. **uvicorn 的 loop / http / ws 三層自動選擇**
   實測已是 Proactor(IOCP)+ httptools + WebSocketsSansIOProtocol —— Windows 上能拿到的最好組合。不要手動指定 `--loop`/`--http`/`--ws`。

3. **`copycat/market.py` 的毫元整數運算**
   台股 tick 表與漲停價。換成任何浮點(numpy / polars 的 f64)都會引入舍入誤差,直接影響下單價格正確性。這是「效能優化的禁區」。

4. **`copycat/server/overlay.py::compute_cdp/compute_ma` 與 `frontend/src/lib/futures-overlay.ts`**
   由 `tests/fixtures/overlay_parity.json` 兩邊各一條測試釘住,且 CLAUDE.md 明文「兩張圖都畫得出來、兩組數字都看起來對,零錯誤訊號」。**不要用任何函式庫的內建 MA/indicator 取代任何一邊。**

5. **`frontend/src/lib/candle.ts` 與 `stock-intraday-svg.ts` 的純幾何函式(1275 LOC)**
   這是整個前端最有價值的資產:渲染與計算已經分離乾淨,且有大量測試。換圖表庫時**保留這一層**,只換「怎麼把座標畫出來」。若換成 visx / Recharts 反而會把這層丟掉、留下慢的那層。

6. **`data/signals/*.jsonl` 的落檔序列化**
   `tests/server/test_signal_outcome.py` 做 byte 比對,研究目錄離線讀者逐列讀。**維持 stdlib `json.dumps`**,不要因為全庫換 msgspec 就連這裡一起換。

7. **`copycat/server/ws.py` 的背壓機制**(per-client queue 1000、丟最舊保最新、`dropped` + 60 s 節流 WARNING「佇列滿」、`window_dropped` 結算)
   這是設計過的、有 prod 判準(`grep "佇列滿" logs/server-*.log` 為 0)的東西。換任何東西都要保住這個可觀測性。

8. **`pyproject.toml:6 dependencies = []` 的 stdlib-only 哲學**
   這個決定讓「離線 replay / 回測」可以在任何一台裝了 Python 的機器上跑,不需要 binary wheel。**建議的做法是加 extras 而非加 `dependencies`**:
   ```toml
   live = [..., "httpx>=0.28", "msgspec>=0.21"]      # ← 新增在 live
   research = ["duckdb>=1.5", "polars>=1.44"]         # ← 新增一個 extra
   ```
   這樣 `copycat replay` / `copycat validate` 的 golden gate 路徑仍可保持 stdlib-only,而 server 與回測各自吃自己的相依。**這是本區最重要的架構建議之一。**

---

## 10. 量測方法(在導入任何東西之前)

所有指令都是唯讀 / 離線,不碰 prod server、不下單。

**M1 — CPU 是否支援 AVX2(決定 Polars 能不能用主線版)**
```powershell
# PowerShell
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
# 或用 coreinfo64.exe / CPU-Z 看 AVX2 旗標
```
判準:有 AVX2 → `pip install polars`;無 → 只能 `polars-lts-cpu`(凍在 1.33.1),那就改推 DuckDB。

**M2 — 現況 JSON store 的讀取成本 vs parquet**
```powershell
.venv\Scripts\python -X importtime -c "import json,glob,time; t=time.perf_counter(); [json.load(open(f,encoding='utf-8')) for f in glob.glob('data/**/*.json',recursive=True)[:200]]; print(time.perf_counter()-t)"
```
再用 duckdb 對同一批做 `read_json_auto` 與轉 parquet 後的 `read_parquet`,三個數字並列。

**M3 — 後端熱路徑 profile(這是所有後端結論的前提)**
```powershell
# 用 --verify 模式(fake source,不碰 ZMQ、不碰群益、不碰 Discord),port 8722
$env:TXO_SERVER_PORT="8722"
.venv\Scripts\python -m cProfile -o profile.out -m copycat.server --verify
# 跑 5 分鐘、前端指向 4173 打一輪,Ctrl+C 後:
.venv\Scripts\python -c "import pstats; pstats.Stats('profile.out').sort_stats('tottime').print_stats(40)"
```
看 `json.encoder` / `json.decoder` / `urllib` 的 tottime 佔比。**若 json 兩者合計 < 3%,B1 的優先序要往下調。**

**M4 — 確認 TC4 入站 tick 的解析法**(本次未讀完 `tc4.py` 全檔,標記未查證)
```powershell
findstr /n "json.loads split( decode(" copycat\live\tc4.py
```

**M5 — winloop A/B(唯一能定 B7 的實驗)**
兩次都跑 `--verify` server(不碰真 TC4),一次原樣、一次在 `__main__.py` 加 `winloop.install()`(**在 worktree 裡改,不改主樹**),各自:
- 用一個腳本開 8 條 WS + 每秒打 20 次 `/api/health`,量 p50/p95 延遲
- 量關機時間(Ctrl+C 到 process 退出),對照 `run_grace_secs()` 的 83 s 預算
判準:**若 p95 改善 < 10%,B7 直接否決。**

**M6 — Python 3.14 相依實測**
```powershell
py -3.14 -m venv .venv314
.venv314\Scripts\pip install -e ".[live,capital,discord,dev]"
.venv314\Scripts\python -c "import zmq, comtypes, win32api; print('ok')"
.venv314\Scripts\python -m pytest -q
```
判準:三個 binary 相依都裝得起來且 pytest 全綠 → B10 可談。

**M7 — 前端主執行緒 profile(這是所有前端結論的前提)**
```
cd frontend && npm run build && npm run preview   # 必須 prod build(CLAUDE.md §1)
```
用 Chrome DevTools MCP:`performance_start_trace` → 開圖牆 50 卡 → 跑 60 s → `performance_stop_trace`。
看三個數字:
1. Scripting vs Rendering vs Painting 的時間分配 → **若 Rendering(layout/style recalc)遠大於 Painting,問題是 DOM 節點數 → F1 是對的;若 Painting 佔大宗 → canvas(F3)才是對的**
2. long task 數量與最長長度
3. DOM node count(`take_snapshot` 或 Performance monitor)

**M8 — bundle 基線**(導入圖表庫前後對照)
```
cd frontend && npx vite build --mode production
# 看 dist/assets/*.js 的 gzip size
```

---

## 11. 未查證 / 需要 user 或實測才知道的事

1. **本機 CPU 是否支援 AVX2** —— 直接決定 Polars 能不能用主線版(M1)。
2. **`frontend/vite.config.ts` 是否有自訂 rollup / esbuild options** —— 決定 Vite 8 遷移成本(本次未讀該檔)。
3. **vitest 3.2.7 對 Vite 8 的相容性** —— 影響 3069 條前端測試。查不到明確聲明。
4. **`comtypes` / `pywin32` 在 Python 3.14 與 free-threaded build 的狀況** —— 這是下單路徑,不能猜。
5. **`copycat/live/tc4.py` 入站 tick 的實際解析法**(`json.loads` vs 字串 split)—— 決定 B1 在入站方向的收益(M4)。
6. **`urllib` 的 21 處呼叫中,有幾處真的在 async context 被直呼**(vs 已被 `asyncio.to_thread` 包住)—— 屬 Q1/Q3 範圍,但決定 B2 的嚴重度。
7. **`frontend/src/lib/stock-accum.ts` 是否已對 tick 列數設上限** —— 決定 F8(虛擬化)要不要做。
8. **`@preact/signals-react` 3.12 對 React 19.2 的相容性** —— 查不到明確聲明(F7 已不建議,故不阻塞)。
9. **uPlot 的實際維護狀態**(GitHub 是否有活躍 commit 只是沒發 npm)—— registry 顯示 2025-03-14 後無發布,但 repo 活躍度未查。
10. **Granian 在 Windows 的 WebSocket 實作細節與 graceful shutdown 語意** —— B8 已不建議,故不阻塞。
11. **React Compiler 對 copycat 的實際覆蓋率** —— 要跑 `npx react-compiler-healthcheck@latest` 才知道(M7 之外的一條)。
12. **lightweight-charts 對「50 個實例同頁」的記憶體與 CPU 行為** —— 官方 bench 都是單圖;這正是 §6.3 要分開處理圖牆的原因,但沒有公開數字。

---

## 12. 來源

**後端 — 計算與資料**
- https://pypi.org/project/polars/
- https://github.com/pola-rs/polars/issues/2922(AVX2 / lts-cpu)
- https://github.com/pola-rs/polars/issues/11658(runtime CPU feature check)
- https://pola.rs/posts/gpu-streaming-backend/
- https://numpy.org/devdocs/release/2.3.0-notes.html
- https://numpy.org/news/
- https://github.com/duckdb/duckdb
- https://kestra.io/blogs/embedded-databases
- https://www.danilchenko.dev/posts/duckdb-vs-polars/
- https://numba.readthedocs.io/en/stable/release/0.61.0-notes.html
- https://github.com/numba/numba/issues/9798(Python 3.13 support)
- https://github.com/mypyc/mypyc

**後端 — 序列化**
- https://msgspec.dev/benchmarks
- https://github.com/msgspec/msgspec
- https://gist.github.com/jcrist/80b84817e9c53a63222bd905aa607b43

**後端 — 併發與服務**
- https://github.com/Vizonex/Winloop
- https://raw.githubusercontent.com/Vizonex/Winloop/main/README.md
- https://github.com/MagicStack/uvloop/pull/606
- https://github.com/emmett-framework/granian
- https://asgi.readthedocs.io/en/latest/implementations.html
- https://www.deployhq.com/blog/python-application-servers-wsgi-vs-asgi-guide
- https://dev.to/locionic/fastapi-vs-litestar-2026-performance-benchmarks-when-to-switch-epf
- https://pyzmq.readthedocs.io/en/latest/api/zmq.asyncio.html
- https://github.com/aio-libs/aiozmq
- https://docs.python.org/3/howto/free-threading-python.html
- https://www.phoronix.com/news/Python-3.14
- https://py-free-threading.github.io/
- https://decodo.com/blog/httpx-vs-requests-vs-aiohttp
- https://pypi.org/project/niquests/
- https://howtech.substack.com/p/ipc-mechanisms-shared-memory-vs-message

**前端**
- https://github.com/tradingview/lightweight-charts
- https://tradingview.github.io/lightweight-charts/tutorials/demos/realtime-updates
- https://tradingview.github.io/lightweight-charts/docs/release-notes
- https://github.com/tradingview/lightweight-charts/blob/master/LICENSE
- https://www.tradingview.com/blog/en/tradingview-lightweight-charts-version-5-50837
- https://github.com/leeoniya/uPlot
- https://cprimozic.net/notes/posts/my-thoughts-on-the-uplot-charting-library/
- https://blog.logrocket.com/best-react-chart-libraries-2026/
- https://react.dev/blog/2025/10/07/react-compiler-1
- https://react.dev/learn/react-compiler/introduction
- https://react.dev/learn/react-compiler/installation
- https://dev.to/jsgurujobs/state-management-in-2026-zustand-vs-jotai-vs-redux-toolkit-vs-signals-2gge
- https://rohitimandi.medium.com/zustand-jotai-and-signals-a-head-to-head-comparison-of-granularity-and-efficiency-077599a4f68e
- https://www.pkgpulse.com/guides/tanstack-virtual-vs-react-window-vs-react-virtuoso-2026
- https://tanstack.com/virtual/latest
- https://web.dev/articles/offscreen-canvas
- https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas
- https://github.com/GoogleChromeLabs/comlink
- https://vite.dev/blog/announcing-vite8-beta
- https://vite.dev/guide/migration
- https://github.com/vitejs/rolldown-vite
- https://github.com/vitejs/vite-plugin-react/discussions/1240

**一手 registry 查詢(2026-09-13 本機執行)**
- `https://pypi.org/pypi/<pkg>/json` — polars / polars-lts-cpu / polars-runtime-32 / polars-runtime-64 / msgspec / orjson / duckdb / numpy / pyarrow / winloop / granian / numba / uvloop / litestar / niquests / pandas / pyzmq / uvicorn / fastapi / Cython / mypy
- `https://registry.npmjs.org/<pkg>` — react / react-dom / vite / @vitejs/plugin-react(-swc) / babel-plugin-react-compiler / eslint-plugin-react-hooks / @tanstack/react-query / @tanstack/store / jotai / valtio / @preact/signals-react / react-window / react-virtuoso / uplot / lightweight-charts / echarts / echarts-for-react / recharts / @visx/visx / highcharts / comlink / klinecharts
- 腳本留在 `scratchpad/pypi_probe.py`、`scratchpad/pypi_probe2.py`、`scratchpad/npm_probe.py`
