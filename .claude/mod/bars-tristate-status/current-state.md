# Current State:bars 空結果三態(逾時 / 真無資料 / TC4 斷線)

/mod bars-tristate-status Phase 1 現況表。2026-08-05。

## 症狀(next-time 2026-07-30 stock-ui-round3 第一條,原 change-spec Known Risks 1)

「有資料但 TC4 慢」→ `BARS_POLL_DEADLINE=10s` 誤判為空 + 15s 負向快取 →
`CandleChart` 顯示**肯定語氣**的「無 K 線資料」而非「還在等」。
`stock_engine.bars_range` 連 `ConnectionError` 都吞成 `[]` → 斷線也顯示同一句。

## 鏈路現況(由下而上)

### 1. `copycat/live/tc4.py` — `_collect_history`(:337-381)

- 回傳 `list[dict]`。**timeout 路徑(:366-370)回 `[]`**,與「首頁備妥但 0 rows」不可分。
- log 一行 `history %s(%s): %.1fs 內首頁未備妥,回空`(僅 server log 可見)。
- TC4 通訊失敗由 `_req` 收斂為 `ConnectionError`(raise,往上傳)。
- **TC4 協定限制**:GETHISDATA 空頁無法區分「未備妥」與「無資料」(檔頭 :51 註解、
  fetch_backfill 註解)。SUBQUOTE 對不存在 symbol 照回 OK。→「真無資料」**無法**從
  TC4 得到正面訊號;deadline 用滿 = 「慢或查無」的疊加態。可正面確認的只有:
  (a) 首頁備妥、rows 收齊(可能 parse 後為空,例如域外全被丟);(b) ConnectionError。
- callers(4 個函式 / 8 個呼叫點,含子類;R8 更正):
  - `stock_source.fetch_day_minutes` :398(overlay/index 分時,**不傳** deadline → 30s 舊值)
  - `stock_source.fetch_bars_range_tagged` :441(1K)、:444(DK)、:454(1K fallback)——
    三處都傳 `BARS_POLL_DEADLINE`
  - `stock_source.fetch_daily_bars` :467(DK)、:470(1K fallback)—— overlay 路徑,不傳 deadline
  - `futures_source.fetch_bars_range` :116(1K)、:119(DK)—— 傳 `BARS_POLL_DEADLINE`
- `river_backfill` 是**同型邏輯的獨立實作**(檔頭註明不碰私有面),不呼叫 `_collect_history`。

### 2. `copycat/live/stock_source.py` — `fetch_bars_range` / `fetch_bars_range_tagged`(:415-456)

- `fetch_bars_range` → `list[Bar]`(delegate 到 tagged 取 [0])。
- `fetch_bars_range_tagged` → `tuple[list[Bar], str tag]`,tag ∈ {tc4_1k, tc4_dk, tc4_dk_1k_agg}。
- timeout 資訊在這層**已丟失**(_collect_history 回 [] 就當空)。
- `fetch_bars_range_tagged` 的外部 caller:`index_engine.bars_range` :348(getattr 動態取用!
  grep 字串拼接確認過:getattr(self._source, "fetch_bars_range_tagged", None),fallback
  `([], "unavailable")`)。FakeIndexSource(tests/helpers/fake_sources.py:89)同簽名。

### 3. `copycat/server/stock_engine.py` — `StockSource` Protocol + `bars_range`(:61, :279-287)

- Protocol:`fetch_bars_range(...) -> list[Bar]`。
- `bars_range`:`except ConnectionError → log warning + return []`。**斷線在此被吞成空**。
- 同檔 `daily_bars`(:271-277)同款吞法 —— overlay 路徑,**不在本輪 scope**(overlay
  另有全 null 降級契約)。

### 4. `copycat/server/bars.py` — `BarsFetcher` + `build_daily` / `build_minute` / `build_period`

- `BarsFetcher = Callable[..., Awaitable[list[Bar]]]`(:57);`TaggedBarsFetcher`(:274)。
- `_empty` 負向快取:(code, tf, days) -> **只存時間戳**(:81),原因不存 →
  15s 內的重複請求回 `[]`,無法還原「為什麼空」。
- `build_minute`:歷史段全空「可能是 TC4 失敗」→ 不入 memo(:353);兩段都空 → empty_mark。
- `build_daily`:空 → empty_mark;`build_period`(市場長窗)同款,key=`{code}|L`。
- caller:`app.py` stock_bars(:657/:665)、market_bars(:779 build_minute、:787 build_period,
  fetcher 是 route 內閉包 `plain`/`tagged` 包 index/futures engine)。

### 5. `copycat/server/app.py` — `/api/stock/bars/{code}`(:645-666)

- response:`{"code", "tf", "bars"}`。**無 status 欄位**。
- market_bars 有自己的 meta(source tag / refusal)體系,response 形狀獨立。

### 6. frontend

- `hooks/useStockBars.ts`:fetch 後只取 `.bars`;`retry: 1`;tf=D `staleTime: Infinity`
  (**空結果會釘死到 remount**);tf=1 交易時段每 60s 輪詢。
- `components/stock/StockChart.tsx`:isPending → 「載入中…」;isError → 「K 線載入失敗」+
  錯誤碼(2026-07-29 事故後分出來的,SC-3);否則掛 `CandleChart`。
- `components/stock/CandleChart.tsx`:544:`shown.length === 0` → 「無 K 線資料」。
  空的三種來源(逾時 / 真無資料 / 斷線降級)在此**全部收斂成同一句肯定語氣**。

## 測試現況(baseline 待背景跑完確認全綠)

- `tests/server/test_bars.py`:32 個 `build_daily`/`build_minute` call site(next-time
  的「20 個」是舊估;R8 重數)+ cache API 直呼(empty_mark/empty_fresh/today_put/today_get),
  **精確相等斷言**(`== []` / `== hist + cur` / `!= []`)。fetcher 替身 `_Fetcher.__call__`
  回 `list[Bar]`。
- `tests/server/test_stock_routes.py`:`test_daily_shape_200` 對 response **整體 `==`**
  (:364-368,加欄位必紅);`test_tc4_down_returns_empty_200`(:429-440)斷言吞
  ConnectionError 後 `bars == []`。
- `tests/live/test_stock_bars.py`:`fetch_bars_range` 回傳值精確相等 ×10+;
  `TestCollectHistoryWaiting` 假時鐘測 deadline/退避。
- `tests/live/test_futures_bars.py`:`futures_source.fetch_bars_range` 精確相等 ×4。
- `tests/server/test_stock_engine.py`:FakeSource.fetch_bars_range 回 []( :90-94,
  斷言不依賴)。
- `tests/server/test_market_routes.py`:三個特化 fake 的 `fetch_bars_range_tagged`;
  `NoHistoryIndexSource`(fetch_bars_range_tagged = None)測 getattr 降級。
- `tests/helpers/fake_sources.py`:FakeStockSource.fetch_bars_range、
  FakeIndexSource.fetch_bars_range_tagged、FakeFuturesSource.fetch_bars_range。
- frontend `StockChart.test.tsx`:SC-3 一組(失敗態 vs 空 bars 分離)、
  「取到空 bars 仍顯示無 K 線資料」;`StockPage.test.tsx:295` bars mock `{bars: []}`;
  `useStockBars.test.tsx` 只驗 URL 組裝。

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| `_collect_history` 回傳 | `list[dict]`(timeout=空) | rows + timeout 旗標可分 |
| source `fetch_bars_range(_tagged)` | bars(+tag) | bars(+tag)+ 三態 status |
| engine `bars_range` | ConnectionError → `[]` | → status="disconnected" |
| `BarsFetcher` / build_* / `_empty` | 只有 bars;負向快取無原因 | status 流過 + 快取存原因 |
| `/api/stock/bars` response | `{code, tf, bars}` | + `status` 欄位 |
| 前端空態 | 一句「無 K 線資料」 | 三態文案(還在等 / 真無 / 斷線) |
| 前端重試 | tf=D 空結果釘死(staleTime ∞) | 非 ok 態要能自動重試 |

## Backward compat / blast radius 備註

- `BarsFetcher` 簽名改 → market_bars 的 `plain`/`tagged` 閉包、index_engine、
  futures 路徑都要機械適配;market response 形狀**不動**(有自己的 meta 體系)。
- overlay 路徑(`fetch_daily_bars` / `daily_bars` / `fetch_day_minutes`)**不動**:
  `_collect_history` 若改回傳型別,這些 caller 機械取 rows,行為不變。
- 「真無資料」受 TC4 協定限制:只能表述為「TC4 回應了但窗內無資料」(首頁備妥），
  deadline 用滿一律 timeout(語意=慢或查無,不可分)。文案必須反映此不確定性。
