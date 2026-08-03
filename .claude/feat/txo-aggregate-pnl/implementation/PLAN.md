# Implementation Plan(condensed): txo-aggregate-pnl

> For agentic workers: goal_efficiency_mode=true → Phase 3 wave batch commit(單 `[waveN]` tag,body 列涵蓋 SC-N)。
> 每節 = 一檔:動什麼 / 新增 signature / 失敗測試對應 SC-N。設計依據 design.md v3;TC4 實測事實依 docs/research/2026-07-18-txo-chain-probe.md。

**Goal**:台指選擇權全市場即時綜合損益圖(當日內外盤累積 → 到期損益曲線 + BEP/極值指標),FastAPI + React,行情走達錢 4。

**Global constraints**(全 task 隱含):
- Python:`from __future__ import annotations` 首行;type hints 無例外;logging 不 print;毫點整數運算;ruff line-length 100;pyright basic。
- React:CLAUDE.md §3 全套(TQ/strict TS/noUncheckedIndexedAccess/semantic token/繁中 UI/`@/` alias/vitest colocated + jsdom pragma + afterEach(cleanup))。
- 測試紀律:紅先行(wave 內 red→green 一次 commit,body 註 SC)。

## Wave 1:聚合引擎(SC-2)

### pyproject.toml(modify)
- `[project.optional-dependencies]` 加 `live = ["fastapi>=0.115", "uvicorn>=0.30", "pyzmq>=26"]`;dev 加 `httpx>=0.27`(TestClient)、`pytest-asyncio>=0.24`。
- `[tool.pytest.ini_options]` 加 `asyncio_mode = "auto"`(CLAUDE.md §2)。

### copycat/live/__init__.py(create)
- 空(package marker + docstring)。

### copycat/live/models.py(create)
- `MULTIPLIER = 50`;`to_millipts(s: str) -> int | None`(str 十進位 → 毫點,空/無效 → None)。
- `@dataclass(frozen=True) OptionContract`:`symbol: str; cp: str; strike_millipts: int`。
- `@dataclass(frozen=True) Tick`:`symbol: str; precise_time: int;`(HHMMSSffffff µs 整數)`price_millipts: int; qty: int; bid_millipts: int | None; ask_millipts: int | None; cum_volume: int | None`。
- `@dataclass(frozen=True) SeriesInfo`:`series_id: str; name: str; expiry: str; contracts: tuple[OptionContract, ...]`。
- `parse_history_tick(symbol: str, raw: dict) -> Tick | None`:欄位 `TradingPrice/TradeQuantity/Bid/Ask/PreciseTime`;cum_volume=None(spike:歷史無累積量);缺 price/qty/PreciseTime → None。
- `parse_realtime(raw: dict) -> Tick | None`(DR-4 隔離層):`Quote` dict → Tick;欄位 `Symbol/TradingPrice/TradeQuantity/TradeVolume(累積)/Bid/Ask/PreciseTime`;無成交(TradeQuantity 空或 0)→ None。
- `parse_option_symbol(symbol: str) -> tuple[str, str, str, int] | None` → (prod, expiry, cp, strike_pts)。
- 失敗測試(tests/live/test_models.py):spike 真實樣本 dict → 各欄位精確值;缺欄位 → None;`to_millipts("102")==102000`、`to_millipts("")` is None。【SC-2】

### copycat/live/payoff.py(create)
- 全純函數,毫點整數,回傳 NTD 用 float(僅邊界)。
- `intrinsic_millipts(cp: str, strike_millipts: int, k_millipts: int) -> int`。
- `@dataclass(frozen=True) PositionRow`:`contract: OptionContract; net_qty: int; net_cost_millipts: int`。
- `build_grid(strikes_millipts: list[int]) -> list[int]`:去重排序 ∪ {min−step, max+step}(step=中位相鄰差)。
- `curve_points(rows: list[PositionRow], grid: list[int]) -> list[tuple[int, float]]`:`(k, Σ(net_qty×intrinsic−net_cost)×50/1000)`。
- `find_beps(curve) -> list[float]`(線段符號翻轉線性插值,點位)。
- `extremes(curve) -> tuple[tuple[float, float], tuple[float, float]]`(max_profit/max_loss (x_pts, y_ntd))。
- `interp_pnl(curve, x_millipts) -> float | None`(範圍外 None)。
- 失敗測試(tests/live/test_payoff.py):手算 2 檔小例(sell 1 C@43000 cost 100pt、buy 2 P@42000 cost 30pt)全網格精確值、BEP 插值、極值;單檔無 BEP;格點=履約價。【SC-2】

### copycat/live/aggregate.py(create)
- `@dataclass Totals`(可變):`ticks/unclassified_ticks/unclassified_qty/overlap_risk_ticks/dropped_foreign_ticks: int`(queue_dropped 屬 engine 層,IR-1)。
- `class ChainAggregator`:
  - `__init__(self, contracts: Iterable[OptionContract])`;內部 `_pos: dict[str, _PosState]`(net_qty/net_cost/volume)、`_last_cum: dict[str, int]`、`totals: Totals`、`spot_millipts: int | None`。
  - `route(self, tick: Tick) -> None`:TC.F.* → `spot_millipts` 更新;symbol ∈ contracts → `_ingest`;其他 → dropped_foreign(§2.2 DR-9)。
  - `_ingest`:live 去重(`tick.cum_volume is not None and cum ≤ _last_cum[sym]` → drop);內外盤分類(≥ask 外 / ≤bid 內 / 其間或缺 → unclassified);累積。
  - `ingest_backfill(self, ticks: list[Tick]) -> dict[str, int]`:排序灌入 + 重建 cum(Σqty)寫 `_last_cum`,回傳 rebuilt cum(交接協定 step 3)。
  - `reset(self, contracts: Iterable[OptionContract]) -> None`(DR-3:清空全部狀態)。
  - `snapshot(self, *, series: SeriesInfo, status: str, accumulated_from: str, queue_dropped: int = 0) -> dict`:組 §2.5 JSON(調 payoff;無部位 → curve=[]、beps=[];queue_dropped 由 engine 注入,IR-1)。
- 失敗測試(tests/live/test_aggregate.py):分類三態、live 去重、TXF/TXO/foreign 混流路由、reset 清空、snapshot totals 數字、call/put 淨口數、**空狀態(無 tick → curve=[]、beps=[]、totals 全 0,edge 1;IR-4)**。【SC-2】

### copycat/live/handover.py(create)
- `class HandoverBuffer`:`cap=200_000`;`append(tick) -> bool`(False=溢出);`flush_into(agg: ChainAggregator) -> int`(逐檔放行 `cum_volume > _last_cum`,經 `agg.route`)。
- `run_handover(agg, backfill_ticks: list[Tick], buffer: HandoverBuffer) -> None`:§2.3 步驟 3-4(排序灌入 + flush);溢出訊號由呼叫端(engine)處理重跑。
- fallback(內容去重)本輪**不實作**(混合制為主案;被週一盤中驗證推翻才回 Phase 2 追加)— PLAN 註記,非 TBD。
- 失敗測試(tests/live/test_handover.py):三情境(先 live 後補灌不誤刪 / flush 只放行較大 cum / 溢出回報 False)。【SC-2】

## Wave 2:server + replay golden(SC-3、SC-5)

### copycat/server/__init__.py(create)
- 空。

### copycat/server/engine.py(create)
- `class QuoteSource(Protocol)`:`list_series() -> list[SeriesInfo]`;`fetch_backfill(series: SeriesInfo) -> list[Tick]`;`subscribe(series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None`;`unsubscribe(series: SeriesInfo) -> None`;`close() -> None`(status 由 engine 自身狀態機管理,無 status_hint;IR-2)。
- `class EngineRuntime`:
  - `__init__(self, source: QuoteSource, *, throttle_secs: float = 1.0, queue_maxsize: int = 10_000)`。
  - `async start(self)`:list_series → 選最近序列 → `activate(series_id)`。
  - `async activate(self, series_id: str)`:§4 select 流程(unsub 舊 → reset → 訂閱進 HandoverBuffer → to_thread fetch_backfill → run_handover → live);溢出 → 重跑(max 3 次後 status=degraded + log)。
  - `on_tick`(thread-safe callback):`call_soon_threadsafe` 塞 queue;滿 → queue_dropped++。
  - `async _consume(self)`:queue → `agg.route`;偵測 queue_dropped 新增且 queue 清空 → 自癒重跑交接(DR-10)。
  - `latest_snapshot(self) -> dict`;`async snapshots(self) -> AsyncIterator[dict]`(節流 broadcast;asyncio.Condition)。
  - `status` 機:connecting/backfilling/live/reconnecting/disconnected/degraded。
- 失敗測試(tests/server/test_engine.py,FakeQuoteSource):activate 全流程 snapshot 正確、select 切換 reset、queue 滿載計數+自癒重跑、節流(throttle_secs=0.01)。【SC-3】

### copycat/server/app.py(create)
- `create_app(source: QuoteSource | None = None, *, throttle_secs: float = 1.0) -> FastAPI`;module-level `app = create_app()`(lazy 真 TC4:env `TC4_PORT` 預設 50774、`FRONTEND_ORIGIN` CORS)。
- lifespan:EngineRuntime start/close。全域 exception handler(§2 慣例):`HTTPException` passthrough、其他 → 502 `{"detail":{"error":"TC4_DOWN"}}` + logger.exception。
- Routes(只 raise 不 catch):`GET /api/txo/series` → `{"series": [...]}`(未就緒 503 NOT_READY);`POST /api/txo/select` body `{"series_id": str}`(未知 400 UNKNOWN_SERIES);`GET /api/txo/snapshot`;`WS /ws/txo-pnl`(connect 即推當前,後續走 snapshots())。
- 失敗測試(tests/server/test_app.py,TestClient + FakeQuoteSource):REST shape/error codes 三種、WS 首訊息 + 後續推播、select 後 snapshot series_id 變更。【SC-3】

### copycat/server/__main__.py(create)
- `python -m copycat.server` → uvicorn.run(app, host=127.0.0.1, port env `TXO_SERVER_PORT` 預設 8721)。logging.basicConfig INFO。

### tests/live/test_replay_golden.py + tests/fixtures/txo_golden/(create)
- spike 錄檔抽樣(`spikes/out/txo_ticks_20260717.jsonl` 取 ATM ±5 檔約 2,000 筆)copy 進 `tests/fixtures/txo_golden/ticks.jsonl`(repo 內,≪1MB);首跑產 `expected_snapshot.json` 後**人工核對數字量級**再定 golden。
- 測試:JSONL → parse_history_tick → ingest_backfill → snapshot == golden(全等)。【SC-5】

## Wave 3:TC4 source 接線(SC-1 wiring)

### copycat/live/tc4.py(create)
- `class TC4QuoteSource(QuoteSource)`:包 wrapper `QuoteAPI`(sys.path 插入 spikes/TCPY,同 backfill_tc4 前例)。
  - `connect()`:Connect(port) + RCVTIMEO 60s;`list_series()`:QueryAllInstrumentInfo("Opt") → parse_option_symbol 分組 → 最近 expiry 排序,name = `{Security} {expiry}`(+EndDate 若合約清單可得;REALTIME 才有 EndDate 時 fallback 純 expiry 並註記,IR-5);TXF spot symbol 常數 `TC.F.TWF.FITX.HOT`。
  - `_sub_rt(request, symbol)`:raw SUBQUOTE/UNSUBQUOTE 帶當日 UTC 窗(spike §3 事實)。
  - `fetch_backfill(series)`:全鏈逐檔 SubHistory/GetHistory("TICKS") 分頁(QryIndex 停滯防呆,同 backfill_tc4)→ parse_history_tick。
  - `subscribe`:啟動 SUB thread(SubPort)收 REALTIME → parse_realtime → on_tick;TXF 一併訂。
  - heartbeat:thread 內記 last_msg 時刻;`is_stale(threshold)` 由 engine 輪詢觸發 reconnect(reconnect = Disconnect → Connect → 由 engine 重跑 activate)。
  - `close()`:Unsub 全部 + `Disconnect()`(§0a KeepAlive bug)。
- 測試:`parse` 層已在 models 測;本檔僅煙霧測試(mock QuoteAPI 物件驗 request 組裝與 series 分組)tests/live/test_tc4.py。盤中整合驗證 = 2026-07-20(Known Risk 1)。【SC-1】

## Wave 4:frontend(SC-4)

### frontend/ scaffold(create:package.json / vite.config.ts / tsconfig.json+app+node / index.html / src/main.tsx / src/index.css / src/vite-env.d.ts / eslint.config.js)
- Vite + React 19 + TS strict + `noUncheckedIndexedAccess` + Tailwind v4(`@theme` semantic tokens:ink/ink-muted/ink-dim/accent/line/bg/bg-deep + profit/loss 雙色)+ TanStack Query + clsx/tailwind-merge + vitest/RTL/jsdom + `@/` alias(vite + tsconfig)+ `eslint-plugin-react-you-might-not-need-an-effect`。
- dev proxy:`/api`、`/ws` → `http://127.0.0.1:8721`(ws: true)。

### src/lib/utils.ts(create)
- `cn(...inputs: ClassValue[]) -> string`(clsx + twMerge)。

### src/lib/format.ts(create)
- `formatNtd(v: number) -> string`(億/萬 縮寫,如 `NT$ 4,505萬`→ 實作:>1e8 → `X.XX 億`;千分位)、`formatPts(v: number) -> string`。
- 失敗測試 format.test.ts:邊界(負值/0/1e8)。【SC-4】

### src/lib/pnl-svg.tsx(create,純函數無 React state)
- `type SnapshotCurve = { curve: [number, number][]; beps: number[]; spot: number | null; spotPnl: number | null }`。
- `buildScales(curve, width, height, pad) -> { x: (pts:number)=>number; y: (ntd:number)=>number }`(y domain 對稱含 0)。
- `curvePath(curve, scales) -> string`;`areaPaths(curve, scales) -> { profit: string; loss: string }`(以零線+BEP 切分);`bepMarkers(beps, scales) -> {x:number}[]`;`zeroLineY(scales) -> number`。
- 失敗測試 pnl-svg.test.ts:小 curve 手算 path 座標、BEP 位置、profit/loss 面積分段數。【SC-4】

### src/hooks/useSeries.ts(create)
- TQ:`useSeries() -> { data: SeriesInfo[] | undefined, ... }`(GET /api/txo/series);`useSelectSeries() -> mutation`(POST /api/txo/select + invalidate)。

### src/hooks/useTxoSnapshot.ts(create)
- 原生 WebSocket + backoff 重連(1s→2s→…→30s cap);`useTxoSnapshot() -> { data: Snapshot | null, wsStatus: "connecting"|"open"|"closed" }`;unmount cleanup。
- 失敗測試 useTxoSnapshot.test.ts(mock WebSocket class):訊息更新 data、斷線 → wsStatus closed + 重連排程。【SC-4】

### src/components/(create:PnlChart.tsx / MetricsBar.tsx / SeriesSelect.tsx / ConnectionBadge.tsx)+ src/App.tsx
- `PnlChart({snapshot})`:SVG(lib 純函數)+ 軸標籤 + 現價虛線 + BEP 標記;`hidden` 慣例不條件卸載。
- `MetricsBar({snapshot})`:指標卡(最大獲利/最大虧損/BEP 兩平點/標的現價/現價到期預估/Call/Put 淨口數/參與合約數/分類覆蓋率)。
- `SeriesSelect`(select 元素 + mutation)、`ConnectionBadge`(status → 繁中文案 + 色)。
- App:dark 版面組裝。視覺實作前呼叫 `frontend-design` + `bencium-controlled-ux-designer`(user 指示)。
- 失敗測試:MetricsBar.test.tsx(數字 render)、PnlChart.test.tsx(空狀態「尚無成交累積」/有資料出 path)、ConnectionBadge.test.tsx(狀態文案)。【SC-4】

## Wave 5:收尾驗證(SC-6)

- 全 gate:pytest -q / ruff / pyright / copycat validate / frontend `npm test` + `npx tsc --noEmit`。
- 真實環境:server 起動(TC4 開啟)→ 瀏覽器截圖(曲線著色/BEP/指標)存 docs/specs/txo-aggregate-pnl/screenshots/;休市日數字 = 07-17 回補重建。
- CLAUDE.md 更新:§0 結構圖加 live/server/frontend、§1 指令表加 server/frontend、§5 TC4 port 事實修正(50774 / SUBQUOTE 時間窗)。
