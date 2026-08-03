# Design v1: 台指選擇權全市場即時綜合損益圖(txo-aggregate-pnl)

版本:v2(2026-07-18)
Changelog:
- v1 初版。
- v2 依 design-review round 1(9 findings 全 accepted):DR-1 回補↔live 交接協定(§2.3);DR-2 SC-3 契約偏離補記(§4,brainstorm 同步 amend);DR-3 reset 契約具名(§2.3/§4);DR-4 REALTIME 欄位隔離層(§3/§9);DR-5 fallback 邊界內容去重(§2.3);DR-6 unclassified 雙欄位(§2.5);DR-7 有界 queue(§4);DR-8 spike ≥30 斷言(§6);DR-9 tick 分流規則(§2.2)。
- v3 = round 2 findings(DR-10 queue 滿載自癒、DR-11 交接 buffer 獨立於穩態 queue、DR-12 fallback 步驟顯式化、DR-13 TXF 訂閱獨立)+ **SC-1 spike 實測回寫**(docs/research/2026-07-18-txo-chain-probe.md):歷史 TICKS 無累積量 → 混合去重制;SUBQUOTE 必帶時間窗;REALTIME 欄位表定案。

對應 brainstorm.md 全部 SC;/auto 模式,實作級選擇標 `[auto-default]`。

## 1. 架構總覽(SC-2/3/4 骨架)

```
達錢 4 (Touchance 4.0, Windows app, OpenAPI ZMQ @ 127.0.0.1:50774)
   │  login → SessionKey + 動態 SubPort(spikes/TCPY/tcoreapi_mq.py 實證;
   │  CLAUDE.md 舊記載 51171/51141 與現版不符,Phase 8.5 沉澱修正)
   ▼
copycat/live/tc4.py ── TC4QuoteSource(執行緒 + ZMQ SUB,唯一碰 ZMQ 的模組)
   │  · 序列/合約查詢(QueryAllInstrumentInfo "Opt")
   │  · 當日歷史 tick 回補(SubHistory/GetHistory "TICKS")
   │  · 即時訂閱(SubQuote,DataType=REALTIME)
   │  · heartbeat 監看 + exponential backoff 重連 + 收工 Disconnect()
   ▼ (thread → asyncio:loop.call_soon_threadsafe 塞 asyncio.Queue)
copycat/live/aggregate.py ── ChainAggregator(零 IO 狀態機,同 engine/ pattern)
   │  · 逐 tick 內外盤分類 → 逐檔淨部位/簽名成本累積
   │  · snapshot() → 曲線 + BEP + 極值 + 合計(調 payoff.py 純函數)
   ▼
copycat/server/app.py ── FastAPI(薄轉發,route 只 raise 不 catch)
   │  · GET /api/txo/series、POST /api/txo/select、GET /api/txo/snapshot
   │  · WS /ws/txo-pnl:節流 ≤1 msg/s 推 snapshot JSON
   ▼
frontend/ ── React 19 + Vite + TS strict + Tailwind v4 + TanStack Query
      · 損益曲線(手刻 SVG,純渲染抽 lib/pnl-svg.tsx)+ 指標卡 + 序列選單 + 連線徽章
```

單一使用者本機工具:同一時間一個 active 序列(server 端全域),select 切換。

## 2. 資料表示與核心演算法(SC-2)

### 2.1 數值表示

- **內部一律「毫點」整數**(點 × 1000;TXO 最小跳動 0.1 點 → 100 毫點),沿用專案 market.py 毫元整數慣例,杜絕浮點累積誤差。JSON 邊界才轉 float/int NTD。
  `[auto-default: 毫點 int | reason: 專案既有整數運算慣例;聚合累加對浮點誤差敏感]`
- PnL(NTD)= 毫點 × 50 / 1000(TXO 乘數 50 NTD/點)。

### 2.2 tick 分流與內外盤分類(brainstorm 拍板語意)

**分流規則(DR-9)**:進 aggregator 前先按 symbol 路由 —
- `TC.F.*`(TXF 近月)→ 只更新 `spot_price`,**絕不**進部位累積路徑;
- `TC.O.*` 且屬 active 序列合約集合 → 進累積;
- 其他(舊序列殘留、未知 symbol)→ 丟棄並計 `dropped_foreign_ticks`。
測試補「TXF 與 TXO 混流」斷言(§7)。

tick = (symbol, ts, price, qty, bid, ask, cum_volume):
- `price ≥ ask`(ask 有效)→ 外盤:`net_qty += qty`, `net_cost += qty × price`
- `price ≤ bid`(bid 有效)→ 內盤:`net_qty -= qty`, `net_cost -= qty × price`
- 之間 / bid・ask 缺 → 不計方向,`unclassified_qty += qty`(誠實揭露)
- 全部另計 `volume += qty`。

### 2.3 去重、時序與回補↔live 交接(edge 3/5;DR-1/DR-3/DR-5)

**去重主鍵(混合制,spike 定案)**:spike 實測 — live REALTIME 有 `TradeVolume`(當日累積量);歷史 TICKS 的 `TradeVolume` 全為 0(無累積量)。因此:
- **回補段**:按 (symbol, `PreciseTime`, `QryIndex`) 排序灌入,同時逐檔累加 `TradeQuantity` **重建** `rebuilt_cum[symbol]`;
- **live 段**:主鍵 = `TradeVolume` 單調遞增 — `TradeVolume ≤ last_cum[symbol]` → 丟棄(stale-drop)。涵蓋 TC4 重複推播與重連重放。

**交接協定(啟動與重連後同一套,DR-1)**:
1. 建立訂閱(SubQuoteRT,§3),收到的 live tick 先進 **handover buffer**(不進 aggregator);
2. 執行歷史 TICKS 回補直到 GetHistory 追平(最後一頁空或 QryIndex 停滯);
3. 回補結果按 (symbol, PreciseTime, QryIndex) 排序灌入 aggregator,`last_cum[symbol] ← rebuilt_cum[symbol]`;
4. flush buffer:逐檔只放行 `TradeVolume > last_cum[symbol]` 的 tick;
5. 轉為即時消費模式。
訂閱先行 → 無真空窗;回補先灌 → 無誤刪。§7 補「交接順序」整合測試(先 live 後補灌、交錯、重連重放三情境)。
**rebuilt_cum 與 TC4 live TradeVolume 的一致性**是本協定唯一外部假設,2026-07-20 盤中驗證(Known Risk 1);若系統性不一致 → 降級 fallback(下)。

**handover buffer 獨立於穩態 queue(DR-11)**:buffer = 純 list,容量 200,000(全鏈盤中尖峰速率 × 回補分鐘級耗時的量級餘裕);溢出 → 放棄本次交接、重跑協定(從步驟 2 起)並 logger.warning。不與 §4 的穩態 `asyncio.Queue(maxsize=10_000)` 共用物件。

**fallback(rebuilt_cum 若被盤中驗證推翻)**:回補結束時間戳 `T_b`(PreciseTime);交接步驟 3'/4' 顯式替換(DR-12):(3') 按 (symbol, PreciseTime, QryIndex) 排序灌入(同上);(4') live tick `ts < T_b` 丟棄、`ts == T_b` 做內容去重(回補段同 ts tick 的 (price, qty, bid, ask) multiset,命中即消耗丟棄)、`ts > T_b` 放行。殘存同 ts 同內容的真實不同撮合 → 記 `overlap_risk_ticks`(僅觀測不修正,Known Risk 3;DR-5)。
`[auto-default: 混合制主鍵、fallback 備援 | reason: spike 實測歷史無累積量;PreciseTime 微秒級使 ts 碰撞機率極低]`

**reset 契約(DR-3)**:`ChainAggregator.reset(contracts)` 具名方法 — 清空全部 per-symbol 狀態(net_qty / net_cost / last_cum_volume / 計數器)並替換合約集合。呼叫時機:select handler 於 unsubscribe 舊鏈**之後**、新鏈回補**之前**同步呼叫(§4)。§7「切換 reset」測試直接對應此方法。

### 2.4 損益曲線與指標(payoff.py 純函數)

- 部位到期損益為**分段線性**,轉折點只在各履約價 → 網格 = 全部履約價 ∪ {min−step, max+step}(step = 履約價中位間距)。
- `PnL(K) = Σ_c (net_qty_c × intrinsic_c(K) − net_cost_c) × 50`(毫點運算)。
- BEP:相鄰網格點符號翻轉 → 線段線性插值,**精確解**(分段線性,無近似誤差)。
- 最大獲利/虧損:網格點極值;**語意 = 顯示範圍內極值**(net short 時理論虧損無界,與截圖系統同語意,UI 標註「圖表範圍內」)。
  `[auto-default: 顯示範圍極值 | reason: 無界極值無法呈現;截圖同款]`
- 現價預估損益:現價落在網格線段上線性插值。
- 標的現價:TXF 近月(`TC.F.TWF.FITX.HOT`)REALTIME 成交價,同一條 ZMQ 訂閱順帶。

### 2.5 Snapshot JSON(WS 與 REST 同 shape;對外契約)

```json
{
  "series_id": "TXO202607W3", "series_name": "2026/07 F3 週選",
  "status": "live|backfilling|reconnecting|disconnected",
  "accumulated_from": "08:45:00", "generated_at": "13:05:22",
  "spot": {"symbol": "TXF", "price": 43735.0},
  "curve": [[41000, -305406431.6], [41050, ...], ...],
  "beps": [43513.0, 44300.4],
  "max_profit": {"x": 44300, "y": 45050126.0},
  "max_loss": {"x": 41000, "y": -3054064316.0},
  "spot_pnl": 35474590.0,
  "totals": {"call_net_qty": -21526, "put_net_qty": -3412,
              "contracts_active": 118, "ticks": 12345,
              "unclassified_ticks": 87, "unclassified_qty": 321,
              "overlap_risk_ticks": 0, "dropped_foreign_ticks": 0,
              "queue_dropped": 0}
}
```

覆蓋率欄位雙軌(DR-6):`unclassified_ticks`(筆數,前端「分類覆蓋率」用它)+ `unclassified_qty`(口數,量級揭露)。

## 3. TC4 介接(SC-1 spike 決定細節)

- `TC4QuoteSource` 包 `spikes/TCPY/tcoreapi_mq.py` 的 `QuoteAPI`(sys.path 插入,同 backfill_tc4.py 前例;**不重寫 wrapper**)。
  `[auto-default: 重用官方 wrapper | reason: KeepAlive 生命週期 bug 已修過(§0a),重寫徒增風險]`
- **SubQuoteRT(spike 定案)**:現版 TC4 的 `SUBQUOTE`/`UNSUBQUOTE`(REALTIME)**必須帶 `StartTime`/`EndTime`**(當日 UTC 窗 `YYYYMMDD00`~`YYYYMMDD06`),wrapper 原 `SubQuote` 未帶會回 `invalid Date Time Format` — source 層自帶 raw request(用 `api.lock` + `api.socket`,同 spike 寫法),不改 wrapper 檔。
- 序列清單:`QueryAllInstrumentInfo("Opt")` → 過濾 TXO → 解析成 `[{id, name, expiry, symbols:[...]}]`(結構由 spike 實測定,PLAN.md 落地)。
- 回補:對序列全部合約 `SubHistory/GetHistory("TICKS", 當日窗)` 分頁拉齊(QryIndex 迴圈同 backfill_tc4 慣例,含停滯防呆)。
- Heartbeat:PING/PONG 由 wrapper KeepAlive 執行緒處理;source 層另計「最後訊息時刻」,交易時段 > 30s 無訊息 → 判斷線 → 重連(backoff 1,2,4,…,60s 上限,連續失敗持續回報 status)。重連成功 → 重回補 + 重訂閱(部位由回補重建,不歸零)。
- 收工:`Disconnect()` 必呼叫(§0a KeepAlive bug)。
- **QuoteSource Protocol**(`typing.Protocol`)抽象:`list_series() / fetch_backfill(series) / subscribe(series, on_tick) / unsubscribe / close`;測試注入 FakeQuoteSource,server/aggregate 測試不碰 ZMQ。
- **REALTIME 欄位隔離層(DR-4)**:REALTIME 訊息 → 內部 Tick 的欄位對映**收斂在單一函數** `parse_realtime(raw: dict) -> Tick | None`(TICKS 歷史另有 `parse_history_tick`)。REALTIME 真實欄位語意在休市日只能部分驗證(訂閱回傳的 snapshot);下一交易日盤中驗證若發現欄位不符,改動半徑限定在此函數,不動 aggregator 介面。此段標記「先開發、盤中驗證前不視為完成」— Phase 7 表格 SC-1(b) 記 infra 降級,不默認通過。

## 4. Server(SC-3)

- `copycat/server/app.py`:`create_app(source: QuoteSource) -> FastAPI`(DI);module-level `app` 用真 TC4(env `TC4_PORT`,預設 50774;`FRONTEND_ORIGIN` CORS)。啟動:`.venv\Scripts\python -m copycat.server`(canonical;env `TXO_SERVER_PORT` 預設 **8721**,IR-3 統一,frontend dev proxy 同值)。
- 全域 exception handler 從第一天開(§2):route 只 raise;`{"detail": {"error": "<code>"}}`;codes:`TC4_DOWN`(502)/`NOT_READY`(503,尚未完成首次回補)/`UNKNOWN_SERIES`(400)。
- 背景 asyncio task:消費 tick queue → aggregator;WS broadcast 節流 1s(config 常數,測試縮短)。
- **tick queue 有界(DR-7/DR-10)**:`asyncio.Queue(maxsize=10_000)`;滿載 → 丟棄新 tick + `queue_dropped` 計數(snapshot 揭露)+ logger.warning。滿載丟棄 = 若無補救即**永久遺失**(不觸發斷線、不會自動重回補)— 自癒機制:`queue_dropped` 於本節有新增且 queue 壓力解除(佇列清空)後,**觸發一次 §2.3 交接協定重跑**(重回補 + flush),把遺失段補回;§7 補滿載 + 自癒測試。
- 生命週期:lifespan 啟動 → connect → 預設序列(最近週選)走 §2.3 交接協定(訂閱 buffer → 回補 → flush → live);關閉 → unsubscribe + Disconnect。
- **select 切換流程(DR-2/DR-3)**:`POST /api/txo/select` → unsubscribe 舊鏈 → `aggregator.reset(new_contracts)` → 新鏈走 §2.3 交接協定 → WS 下一則 snapshot 自帶新 series_id。**TXF 現貨訂閱獨立於序列選單,select 切換不碰它**(DR-13)— unsubscribe 範圍僅限舊序列 TC.O 合約,現價連續不中斷。**對 SC-3 原文的偏離**:brainstorm 原寫「WS ?series= 參數 + 前端重連切換」,改為 REST select + 單一 WS 流 — 理由:單一使用者本機工具,全域 active 序列語意更簡,序列參數化 WS 對單人工具是 over-design;brainstorm.md SC-3 已同步 amend。
- Python 依賴:`[project.optional-dependencies] live = ["fastapi", "uvicorn", "pyzmq"]`;dev 加 `httpx`(TestClient)、`pytest-asyncio`。**backtest 核心維持 stdlib-only**(copycat/live、copycat/server 不被既有模組 import)。

## 5. Frontend(SC-4)

- 慣例全依 CLAUDE.md §3(React 19 / TQ / strict TS / noUncheckedIndexedAccess / Tailwind semantic token / 繁中 UI / `@/` alias / vitest colocated)。
- 檔案:
  - `src/lib/pnl-svg.tsx` — 純函數:scale 計算、曲線 path、獲利/虧損分區 path(以 BEP 切分)、BEP/現價線座標。無 React 依賴,單元測試釘數字。
  - `src/hooks/useTxoSnapshot.ts` — 原生 WebSocket + 自動重連(backoff),回傳 `{ data, status, error }`;序列清單走 TanStack Query(REST)。WS 是 push 流,不套 TQ。
    `[auto-default: WS 不套 TanStack Query | reason: TQ 是 request/response 模型,硬套 push 流反而繞]`
  - `src/components/PnlChart.tsx / MetricsBar.tsx / SeriesSelect.tsx / ConnectionBadge.tsx`、`App.tsx`。
- 視覺:實作時呼叫 `frontend-design` + `bencium-controlled-ux-designer`(user 指示);/auto 下設計選擇標 auto-default。基調 dark(截圖同氛圍)、獲利/虧損分區雙色、指標卡列頂部、Bull 紅/Bear 綠適用於漲跌字色。
- 序列切換:`SeriesSelect` → `POST /api/txo/select` → TQ invalidate + WS 下一則 snapshot 自帶新 series_id(前端不重連)。

## 6. Spike(SC-1,Phase 2 前執行)

`spikes/txo_chain_probe.py`(一次性,收工 Disconnect):
1. Connect 50774 → 登入成功。
2. `QueryAllInstrumentInfo("Opt")` → dump TXO 序列/合約結構(存 `spikes/out/txo_instruments.json`);**腳本內斷言最近週選合約數 ≥ 30**(DR-8),摘要含 `contracts_count`,未達標 exit 非 0。
3. 取最近週選序列,`SubHistory("TICKS")` 回補上一交易日(2026-07-17)全鏈 → 統計:合約數、tick 筆數、欄位覆蓋率(price/qty/bid/ask/cum_volume 各 %)→ 錄檔 `spikes/out/txo_ticks_20260717.jsonl`(供 SC-5 golden)。
4. `SubQuote` 整條鏈 → 驗訂閱成功 + REALTIME snapshot 欄位(休市日降級驗證;live 流留下一交易日,記 Known Risk)。
5. stdout JSON 摘要;結論落 `docs/research/2026-07-18-txo-chain-probe.md`。

## 7. 測試策略(SC-2/3/5)

| 層 | 方式 |
|---|---|
| payoff.py | 手算小例精確斷言(2 檔部位 → 曲線值/BEP/極值毫點級全等) |
| aggregate.py | 構造 tick 序列:分類/去重/unclassified/`reset()` 切換/TXF·TXO 混流分流(DR-9)各一組 |
| 交接協定 | 三情境整合測試(DR-1):先 live 後補灌不誤刪、buffer flush 只放行 cum_volume 較大者、fallback 內容去重邊界;queue 滿載丟棄+計數(DR-7) |
| server | TestClient + FakeQuoteSource(腳本化 tick + 可控 status):REST shape、WS 訊息、節流(注入短 interval)、斷線 status、error codes |
| replay golden | spike 錄的真實 tick JSONL → aggregator → snapshot 與 golden JSON 全等(`tests/live/test_replay_golden.py`) |
| frontend | vitest:pnl-svg 純函數數字;hook(mock WebSocket);RTL 元件 render(§3 pragma/cleanup 慣例) |
| 既有 gate | pytest / ruff / pyright / validate 全綠(SC-6) |

pyright:`include` 加 server/live 自然涵蓋(同 package);frontend 不在 pyright 範圍。

## 8. SC 對應表

| SC | 設計章節 |
|---|---|
| SC-1 | §6 spike |
| SC-2 | §2 演算法 + §7 測試 |
| SC-3 | §4 server + §3 介接 |
| SC-4 | §5 frontend |
| SC-5 | §6 錄檔 + §7 replay golden |
| SC-6 | §7 既有 gate |

## 9. Known Risks

1. **休市日 live 流驗證缺口**(spike 後已縮小):REALTIME 欄位名/訂閱機制已於休市日實測定案(docs/research/2026-07-18-txo-chain-probe.md §3);遺留 2026-07-20 週一盤中驗證:(a) live push 頻率語意;(b) **rebuilt_cum 與 live TradeVolume 一致性**(§2.3 交接協定唯一外部假設,不一致 → 降級 fallback);(c) heartbeat/重連行為。Phase 7 表格 SC-1(b) 記 infra 降級 + 完成回報明示。
2. **歷史 TICKS 欄位語意未定**(cum_volume 有無、bid/ask 有無):§2.3 已備 fallback;spike 後在 PLAN.md 定案。若歷史 tick **完全無 bid/ask** → 回補段全部 unclassified,「當日累積」語意剩 live 段有效 — 屆時停下回報(方向性影響,不 auto-default)。
3. **fallback 模式 T_b 邊界可能殘存雙計**(DR-5):內容去重後仍無法區分「同 ts 同內容的真實不同撮合」;`overlap_risk_ticks` 僅觀測不修正,數字可能微幅偏高 — 前端不特別警示,計數留 snapshot 供 audit。
4. **QueryAllInstrumentInfo("Opt") 回傳量**:期權全清單可能很大/分頁,spike 實測;超時則改逐序列查詢。
