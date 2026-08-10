# Change Spec:bars 空結果三態(逾時 / 真無資料 / TC4 斷線)

/mod bars-tristate-status。2026-08-05。
分流判定:user 帶已成形改法(next-time 條目已指明鏈路、response 欄位、前端分態、測試面)
→ grilling 確認姿態,無 counter-proposal;文案已 AskUserQuestion 拍板。

## 0. 拍板紀錄

- **timeout 文案**:「等待 TC4 回應中…(自動重試)」中性灰(`text-ink-muted`,同「載入中…」樣式)。
- **disconnected 文案**:「TC4 連線中斷,K 線暫不可用(自動重試中)」紅(`text-bear`)。
- **ok + 空**:維持「無 K 線資料」。
- 前端非 ok 且空 → 每 20s 自動重試(> 後端 15s 負向快取 TTL)。

## 1. 成功條件(可驗收)

- **SC-1(timeout)**:source 層 deadline 用滿 → `/api/stock/bars` 回
  `{"status": "timeout", "bars": []}`(unit:fake fetcher);前端 K 線圖區(模式鈕下方)
  置中顯示灰字(`text-ink-muted`)「等待 TC4 回應中…(自動重試)」——**畫面可指認**:
  **同「載入中…」佔位框**(rounded border-line bg-surface 置中),文字如上。
  [amendment 2026-08-05: 自評 WL-COV-2 — 原「原『無 K 線資料』同一佔位框」與「同載入中
  樣式」互相矛盾(CandleChart 內部空態無框無底色);依 user 拍板原文採「同載入中樣式」,
  並補框樣式斷言釘住。]
- **SC-2(disconnected)**:engine 層 `ConnectionError` → `{"status": "disconnected"}`;
  前端同一佔位框置中紅字(`text-bear`)「TC4 連線中斷,K 線暫不可用(自動重試中)」。
- **SC-3(真無資料)**:TC4 回應但窗內無資料 → `{"status": "ok", "bars": []}`;
  前端維持「無 K 線資料」(灰,不變)。
  [amendment 2026-08-05: R7 — **僅 unit 可驗**(fake fetcher 注入 ok+空);真環境無穩定
  觸發手段。真 TC4 上輸入不存在股號的**預期結果是 timeout 文案**,那是 SC-1 的真環境
  證據,**不得拿它判 SC-3 FAIL**。]
- **SC-4(自動重試)**:`data.bars` 空且 `status !== "ok"` → refetch interval = **20,000 ms**
  (unit + 量法:抽純函式 `barsPollInterval(data, isDaily, trading)`,斷言回 20_000;
  20s > `EMPTY_TTL_SECS` 15s → 每輪重試都真打 TC4,不會撞負向快取空轉)。
  [amendment 2026-08-05: R3 — 純函式測綠不足以證明接線。N-8 增列 hook 層接線測試
  (fake timers + renderHook,見 §6);實作註記:TanStack v5 函式形 `refetchInterval`
  的 data 必須讀 `query.state.data`,不可用閉包裡的 data(閉包版恆為初值)。]
- **SC-5(快取保真)**:負向快取 15s 內的重複請求回**存入時的 status**,不得洗白成 ok
  (unit:test_bars.py)。
- **SC-6(status 語意)**:status = 各實際發出 fetch 的最壞值
  (disconnected > timeout > ok);bars 非空照回 bars,前端只在空時分態。

**TC4 協定限制(語意錨點)**:GETHISDATA 空頁無法區分「未備妥」與「無資料」、SUBQUOTE 對
不存在 symbol 照回 OK(CLAUDE.md §8)→「真無資料」**沒有正面訊號**。本輪的誠實表述:
`timeout` = 「等滿 deadline 無回應」(慢**或**查無,不可分,文案用進行式不下結論);
`ok` + 空 = 「TC4 有回應(首頁備妥)但 parse 後無 bar」(域外全丟等罕見路徑)。
**「TC4 查無此檔」的常態表現是 timeout,不是 ok+空** —— 這是協定限制,不是 bug。

## 2. 不能破壞的既有行為白名單

<!-- Phase 5 白名單對照節(finder prompt 必附本節行號範圍) -->

1. **ok + 空 bars → 前端仍顯示「無 K 線資料」**(StockChart.test.tsx「取到空 bars 仍顯示…」
   / SC-3 反向 W-13:不可誤報成失敗)。
2. **isError 態不變**:「K 線載入失敗」+ 錯誤碼(detail.error → HTTP_<status> 取值鏈)照舊;
   4xx/5xx 仍走 error 路徑,不被 status 分態搶走。
3. **負向快取「行為」不變**:15s TTL 擋重複請求、過期自動恢復、key 含 days、
   prune 只丟過期。[amendment 2026-08-05: R1 — 但 **BarsCache 的 API 簽名與回傳型別
   會改**(`empty_mark` 加 status 參數、`empty_fresh` → `empty_status` 回
   `BarsStatus | None`、`today_put/today_get` 加 status,見 R4 修法);直呼這些 API 的
   測試屬「該紅」,新斷言語意在 §5 明列,不是現場即興。]
4. **歷史段永久 memo / 當日段 30s TTL / 分頁截斷不釘空 / 空不覆寫非空 / 跨午夜 key** 全不變。
5. **overlay 路徑零行為變**:`fetch_daily_bars` / `StockEngine.daily_bars`(ConnectionError
   → `[]` 降級)/ `fetch_day_minutes`(30s 舊 deadline)只做機械適配(`.rows`),
   test_stock_routes overlay 測試不紅。
6. **market_bars response 形狀與 meta 不變**(source tag / refusal 體系照舊;
   test_market_routes 僅 fake 簽名適配,斷言的 payload 不變)。
7. **deadline / 退避參數不變**:`BARS_POLL_DEADLINE=10.0`、`_POLL_BACKOFF_START=0.15`、
   `poll_wait=0` 探測一次即回。
8. **tf=1 交易時段 60s 輪詢不變**(20s 是非 ok 空態**新增**,不取代)。
9. **index_engine.bars_range 對外簽名 `(bars, tag)` 與 "unavailable" 降級不變**
   (內部解 3-tuple 丟 status)。
10. **futures 路徑行為不變**(`futures_source.fetch_bars_range` 對外簽名 `list[Bar]` 不動)。
11. **API 錯誤契約不變**:BAD_CODE / BAD_TF / BAD_DAYS 照舊 400。

## 3. Backward compat / migration

- response **加欄位** = 向後相容;前端對缺 `status` 的舊後端 **default "ok"**(= 現況行為),
  版本落差窗口兩個方向都安全。無資料格式 migration。
- `StockSource` Protocol / `BarsFetcher` 簽名改 = 純內部契約,所有實作(真 + fake)同輪改。
- 可逆性:revert 本輪 commit 即回舊契約,無持久化狀態涉入(cache 全 in-memory)。

## 4. Out of scope

- market 頁三態誠實化(index / futures engine 的 status;本輪只機械適配,market 閉包補 "ok")。
- overlay / 分時(fetch_day_minutes)三態。
- bars **非空**但某段降級(如當日段 timeout)的 UI 提示 —— status 照實回傳但前端不顯示。
- 國定假日輪詢空跑(next-time 另條)、交易日曆。
- `fetch_day_minutes` 的 30s deadline 調整。

---

## 5. Diff 級 spec(Phase 3)

### 型別

- `copycat/live/stock_source.py`:新增 `BarsStatus = Literal["ok", "timeout", "disconnected"]`
  (與 `Bar` 同居;server 層已 import 此模組,無循環)。
- `copycat/live/tc4.py`:新增 `class HistoryResult(NamedTuple): rows: list[dict]; timed_out: bool`。
- `copycat/server/bars.py`:
  [amendment 2026-08-05: R5 — `BarsResult` 與 `TaggedBars` **各自做成 NamedTuple**,
  不用裸 tuple:兩者同構(`BarsStatus` 是 `str` 的 Literal 子型別),裸 tuple 下把
  status 版 fetcher 誤傳給 `build_period` 型別合法 → `meta.source` 靜默變 `"ok"`。]
  - `class BarsResult(NamedTuple): bars: list[Bar]; status: BarsStatus`
  - `class TaggedBars(NamedTuple): bars: list[Bar]; tag: str`(`build_period` 回傳與
    `TaggedBarsFetcher` 回傳都改用它)
  - `BarsFetcher = Callable[[str, str, str, str], Awaitable[BarsResult]]`
- status 嚴重度排序 helper:`worst_status(*statuses) -> BarsStatus`
  (disconnected > timeout > ok)放 `bars.py`。

### 逐檔

#### 🔵 commit 1(純重構:`_collect_history` 回傳型別,行為零變,測試不動)

- `live/tc4.py`:`_collect_history` 回 `HistoryResult`;timeout 路徑回
  `HistoryResult([], True)`,收割完成回 `HistoryResult(rows, False)`。
- **4 個 caller 函式 / 8 個呼叫點**機械適配(全取 `.rows`,本 commit 不讀 `.timed_out`)
  [amendment 2026-08-05: R8 — 原「7 個 caller」數錯]:
  `stock_source.fetch_day_minutes`(:398)、`fetch_bars_range_tagged`(:441/:444/:454)、
  `fetch_daily_bars`(:467/:470)、`futures_source.fetch_bars_range`(:116/:119)。
- 既有測試**全綠不動**(無測試直呼 `_collect_history`)。

#### 🔴 commit 2(行為改動:status 沿鏈傳遞 + response 欄位;先改測試紅)

- `live/stock_source.py`:
  - `fetch_bars_range_tagged` → `tuple[list[Bar], str, BarsStatus]`:
    tf=1:status = "timeout" if timed_out else "ok"。
    tf=D:DK 非空 → ("tc4_dk", "ok");否則 fallback,status =
    "timeout" if (dk.timed_out or fb.timed_out) else "ok"(SC-6 worst)。
  - `fetch_bars_range` → `tuple[list[Bar], BarsStatus]`(delegate 取 [0], [2])。
- `server/stock_engine.py`:
  - Protocol `fetch_bars_range -> tuple[list[Bar], BarsStatus]`。
  - `bars_range` → `tuple[list[Bar], BarsStatus]`;`except ConnectionError` →
    `([], "disconnected")`(warning log 保留原句式)。
- `server/index_engine.py`:`bars_range` 內部解 3-tuple 丟 status,對外簽名不變(白名單 9)。
- `server/bars.py`:
  - `_empty`:值改 `(ts, status)`;`empty_mark(code, tf, days, status)`;
    `empty_fresh` **改名 `empty_status`** 回 `BarsStatus | None`(None = 無 fresh 標記);
    `prune` 適配 tuple 值。
  - `build_daily` → `BarsResult`:cached 命中 → (cached, "ok");empty_status 命中 →
    ([], 該 status);fetch 後空 → empty_mark(status);非空 → daily_put + empty_clear。
  - `build_minute` → `BarsResult`:兩段各自的 status 以 `worst_status` 合併
    (**未實際 fetch 且無存檔 status 的段視為 ok**:歷史 memo 命中);
    out 空 → empty_mark(合併 status);歷史段全空不入 memo 的既有行為不變。
  - `build_period`:對外簽名不變(回 `TaggedBars`);`empty_status` /
    `empty_mark(..., "ok")` 適配(market 空態表述走自己的 source tag,
    status 存 "ok" = 現況等價)。
  - 當日段 `_today` cache **存 status**:值改 `(ts, bars, status)`,`today_get` 回
    `(bars, status) | None`,`today_put(code, today, bars, status)`;`_today_ttl` / `prune`
    機械適配。[amendment 2026-08-05: R4 — 原「不存 status」的不變式有洞:`_empty` key 含
    days 而 `_today` 不含,days=1 的當日段 timeout 寫入後,15s 內 days=30 的請求
    `empty_status` 未命中、`today_get` 命中那份源自 timeout 的空 → 若視為 ok 會把
    timeout 洗白,違反 SC-5。存 status 讓兩層一致保真。]
- `server/app.py`:
  - `stock_bars`:`bars, status = await build_*(...)` → response
    `{"code", "tf", "bars", "status"}`。
  - `market_bars`:閉包改名以隔開兩種第二元素語意
    [amendment 2026-08-05: R5]:`plain` → `plain_with_status`(回 `BarsResult(bars, "ok")`)、
    `tagged` → `tagged_source`(回 `TaggedBars`);`build_minute` 回 `BarsResult` →
    解構丟 status。payload 不變(白名單 6)。
- fakes / 測試(**先改,讓其紅**):
  - `tests/helpers/fake_sources.py`:`FakeStockSource.fetch_bars_range` 回
    `(bars_result, bars_status)`(新屬性 `bars_status: str = "ok"` 可注入);
    `FakeIndexSource.fetch_bars_range_tagged` 回 3-tuple(補 "ok")。
  - `tests/server/test_bars.py`:`_Fetcher.__call__` 回 `BarsResult`(可注入
    per-call status);**32 個 `build_daily`/`build_minute` 呼叫點**斷言改解構
    (語意逐條保留)[amendment 2026-08-05: R8 — next-time 的「20 個」是舊估]。
    另 **cache API 直呼處該紅並指定新斷言**[amendment 2026-08-05: R1/R4]:
    - `test_prune_drops_only_expired_empty_marks`:`empty_mark("2330","1",30,"timeout")`
      → prune 後 `empty_status(...) == "timeout"`,過期 prune 後 `is None`
      (順帶覆蓋 SC-5 保真)。
    - `test_prune_evicts_expired_today_entries` / `test_today_cache_keyed_by_date_survives_midnight`
      / `test_prune_drops_out_of_window_entries`:`today_put(..., bars, "ok")`、
      `today_get` 回 `(bars, status) | None`(斷言改比對 `[0]` 或整 tuple)。
  - `tests/server/test_stock_routes.py`:`test_daily_shape_200` 精確相等加
    `"status": "ok"`;`test_tc4_down_returns_empty_200` 改斷言
    `r.json()["status"] == "disconnected"` 且 `bars == []`(該紅:行為真的變了 ——
    原斷言只驗 `bars == []`,現在多驗 status)。
  - `tests/live/test_stock_bars.py`:`fetch_bars_range` 斷言改 2-tuple
    (精確相等處 `== ([...], "ok")`;timeout 案例 `== ([], "timeout")`)。
  - `tests/server/test_stock_engine.py`:`FakeSource.fetch_bars_range` 回 `([], "ok")`。
  - `tests/server/test_market_routes.py`:三個特化 fake 的 `fetch_bars_range_tagged`
    補第三元素;`NoHistoryIndexSource` 降級測試不動。
  - `tests/live/test_futures_bars.py`:**不動、不該紅**(futures 對外簽名不變)。
- 新 unit(🔴 段內的新斷言,見 §6 新測試清單 N-1~N-6)。

#### 🔵 commit 3(前端 payload 型別適配,畫面零變、既有測試全綠)

[amendment 2026-08-05: R2 — 原單一 🟢 commit 混了 🔵 型別適配與 🔴 既有空態/輪詢行為改,
拆成 commit 3(🔵)+ commit 4(🔴)。]

- `frontend/src/hooks/useStockBars.ts`:
  - `type BarsStatus = "ok" | "timeout" | "disconnected"`;
    `type BarsPayload = { bars: Bar[]; status: BarsStatus }`。
  - `fetchBars` 回 `BarsPayload`;**status 正規化集中在此一處**:欄位缺**或值不在
    白名單 {ok, timeout, disconnected}** → 一律 `"ok"`(backward compat §3;
    [amendment 2026-08-05: R6 — 未知值若放行,`barsPollInterval` 的 `!== "ok"` 會輪詢、
    StockChart 卻落「無 K 線資料」,矛盾態零訊號])。
  - `useStockBars` 回傳的 `data` 型別隨之變 `BarsPayload`;本 commit `refetchInterval`
    邏輯**不動**。
- `frontend/src/components/stock/StockChart.tsx`:`data?.bars` 取代 `data`(aggregate 不變),
  渲染分支不動。
- 既有測試全綠不動(舊 mock 缺 status → default "ok" 兜住,含 `StockPage.test.tsx:295`)。

#### 🔴 commit 4(行為改動:空態三分態文案 + 非 ok 空態 20s 自動重試;先改/寫紅測試)

被改的既有行為(所以是 🔴 不是 🟢):(a) timeout / disconnected 下的空態畫面由
「無 K 線資料」換句;(b) tf=D 空結果原本 `staleTime: Infinity` 釘死零流量,改為非 ok
空態 20s 輪詢。

- `frontend/src/hooks/useStockBars.ts`:
  - 新純函式 `barsPollInterval(data: BarsPayload | undefined, isDaily, trading):
    number | false`:data 有值且 `bars.length === 0` 且 `status !== "ok"` → `20_000`;
    否則 `!isDaily && trading ? 60_000 : false`(既有語意)。
  - `refetchInterval` 改吃它,**data 讀 `query.state.data`**(R3 註記:閉包版恆為初值;
    函式形式保留 —— 每次 interval 到期重新求值的既有理由不變)。
- `frontend/src/components/stock/StockChart.tsx`:空態分派(在 isPending / isError 之後):
  `status === "timeout"` 且 bars 空 → 佔位框(同現有樣式)置中 `text-ink-muted`
  「等待 TC4 回應中…(自動重試)」;`"disconnected"` → 置中 `text-bear`
  「TC4 連線中斷,K 線暫不可用(自動重試中)」;否則照舊掛 `CandleChart`
  (其內「無 K 線資料」處理 ok+空)。
- `CandleChart.tsx` **不動**(內部空態句子保留為 ok 路徑的呈現)。

### 既有測試逐一標(該紅 / 不該紅)

**該紅(🔴,隨 commit 2 先改)**:
- `test_bars.py` 全部 20 call site(回傳形狀)。
- `test_stock_routes.py`:`test_daily_shape_200`(精確相等)、
  `test_tc4_down_returns_empty_200`(加 status 斷言)。
- `test_stock_bars.py`:`TestFetchBarsRange*` 全部回傳形狀斷言、
  `TestCollectHistoryWaiting` 的 `_run_with_fake_clock` 回傳解構。
- `test_stock_engine.py` FakeSource、`test_market_routes.py` 特化 fakes、
  `fake_sources.py`(簽名適配)。

**不該紅**:
- `test_futures_bars.py` 全部(futures 對外簽名不變)。
- overlay / snapshot / watchlist / signals 等其餘後端測試。
- frontend 既有 StockChart 測試(SC-3 兩條、error 兩條;mock 缺 status → default ok)、
  `useStockBars.test.tsx`(只驗 URL)、`StockPage.test.tsx`。
- `copycat validate` golden gate(replay 子系統無涉)。

### 新測試清單

- **N-1**(tests/live/test_stock_bars.py):tf=1 timeout → `([], "timeout")`;
  正常 → `(..., "ok")`;tf=D DK timeout + 1K fallback 有資料 → bars 非空 + `"timeout"`
  (SC-6 worst)。
- **N-2**(tests/server/test_stock_engine.py):`bars_range` 遇 ConnectionError →
  `([], "disconnected")`。
- **N-3**(tests/server/test_bars.py):status 流過 build_daily / build_minute;
  兩段 worst 合併(歷史 ok + 當日 timeout → timeout)。
- **N-4**(tests/server/test_bars.py):SC-5 —— empty_mark("timeout") 後 15s 內重複請求回
  `([], "timeout")`,不洗白;過期後恢復重抓。
- **N-5**(tests/server/test_stock_routes.py):response 含 status;fake 注入 timeout →
  `{"status": "timeout"}`。
- **N-6**(tests/server/test_market_routes.py):market payload **不含** status 欄位,
  且 `meta.source` **不得為 `"ok"`**(白名單 6 + R5 誤接守門)。
- **N-7**(frontend StockChart.test.tsx):mock `{bars: [], status: "timeout"}` →
  顯示「等待 TC4 回應中…(自動重試)」且無「無 K 線資料」;`"disconnected"` →
  紅字句;`{bars: []}`(缺 status)→ 仍「無 K 線資料」(default ok 回歸);
  `{bars: [], status: "weird"}` → 仍「無 K 線資料」且不觸發 20s 輪詢
  [amendment 2026-08-05: R6]。
- **N-8**(frontend useStockBars 測試):
  - `barsPollInterval` 純函式:空+timeout → 20_000;空+ok → 既有邏輯;
    非空+timeout → 既有邏輯(不觸發 20s)。
  - **接線測試**[amendment 2026-08-05: R3]:`vi.useFakeTimers()` + renderHook /
    掛 StockChart,fetch mock 回 `{bars: [], status: "timeout"}`,前進 20s 後斷言
    fetch 第二次;反向:`{bars: [], status: "ok"}`(tf=D)前進 60s 仍只一次。
    若 fake timers 與 TanStack 在 jsdom 撞牆(frontend-testing skill 有記錄的坑),
    fallback = Phase 7 真環境量法(fake source 注入 timeout,server log 觀察 ~20s
    一次請求),擇一必須有,**不得兩頭皆無**。

## Known Risks

1. 「真無資料」的正面態(ok+空)在真 TC4 上罕見 —— 查無此檔的常態是 timeout,
   前端會顯示「等待 TC4 回應中…」並每 20s 重試下去(誠實但不收斂)。這是 TC4 協定
   限制(§1 語意錨點),接受;若日後煩人,可在前端加「連續 N 輪 timeout 後改弱提示」。
2. bars 非空但當日段 timeout / disconnected 時,前端無提示(Out of scope 3)——
   最後一根可能停在舊分鐘,與現況相同。
3. 非交易時段的 20s 重試:TC4 收盤後對當日窗若持續 timeout,前端會持續 20s 輪詢
   (原本 tf=D 空結果 staleTime ∞ 釘死 = 零流量)。每輪成本 = 一次 10s deadline 空等
   (後端),頻率受 15s 負向快取緩衝為實質 ~20s 一次 TC4 真打。單人本機用量可接受。

self_review_head: 8f7d44b
<!-- 收尾增量判定(2026-08-05):8f7d44b..HEAD 僅 93bd130(chore:4 張 verification
screenshots + next-time 勾銷,零 code diff)→ 無 code 可審,沿用自評結果不補輪。 -->
