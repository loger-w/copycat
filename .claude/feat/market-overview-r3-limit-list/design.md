# Design — 台股綜合 R3:漲跌停列表 + 個股跳轉

版本:v3(2026-08-06)
上游:brainstorm.md(Q1–Q7 已拍板)/ 總 spec §5 Round 3
Changelog:
- v1 初版
- v3 依 design review round 2(限縮輪)修訂:
  - [R13/P1] 重算武裝與成功分離:新增 `_streak_armed_day`,`_poll_loop` 以它判是否
    起 task(成功與否不影響「今日已排程」);嘗試上限因此真正生效,超限後同日不再重跑。§3.3。
  - [R14/P1] 新增 `_rows_date`(與 `self.rows` 同步無條件更新);`rows_state()` 判式
    與 payload `trade_date` 改用它 — `_apply` 的 `adopt_date=False` 路徑會讓
    `_trade_date` 與 rows 脫鉤,舊判式在該路徑重現 R1 的 +1。§3.3。
  - [R15/P1] 換日重算加時間閘(06:00 後才 arm)+ 快取記 `skipped`(被當假日跳過的
    日集合),`rows_state()` 對 `trade_date ∈ skipped` 回 null;KR-1 重寫(原接受
    理由被 R9 修法推翻)。§3.3 / §8。
  - [R16/P1] `_DAILY_MIN_ROWS` 以實測訂 25,000(2026-08-05 真跑單日全市場 42,074
    列、4 位普通股 2,334 檔;1000 幾乎恆真形同無健檢);每日取數 log 實際列數。§3.3。
  - [R17/P1] brainstorm SC-1 補 amendment(prev_streak → streak/streak_capped、
    三元組 → 四元組)。
  - [R18/P2] 載入/暫無判別子改 `as_of` sentinel(`stale` 只管膠囊)— 原規則在重啟
    路徑上兩態顛倒。§3.4 / §5.2。
  - [R19/P2] 改動清單補 CLAUDE.md §1 `VERIFY_BREADTH_FAIL`「三支→四支」+ verify.py
    docstring 同步。§3.3a。
  - [R20/P2] `BreadthFetchers` 第四槽型別 `DailyPricesFetch | None`(停用是契約的
    一部分,不用 cast 掩蓋)。§3.3a。
- v2 依 design review round 1 修訂(全部 finding 落點):
  - [R1/P0] 連板數改**後端算完**(`streak` + `streak_capped` per-row),以
    `trade_date` vs `data_end` 判「今日這根是否已在 streak 內」— 盤前 / 假日開站
    (rows = 上一交易日收盤快照)不再重複 +1。§3.3 / §4 / §5.2。
  - [R2/P1] 注入點明寫:`BreadthFetchers` 三元組 → **四元組**(+DailyPricesFetch),
    `_make_breadth` DEFAULT 分支 / `verify.fake_breadth_fetchers`(補第四支 fake +
    `VERIFY_BREADTH_FAIL` 注入 + fake 快照補 `high`/`low`)/ 既有建構點改動清單。§3.3a。
  - [R3/P1] streak loop 的 `today` 進場取樣一次,收尾不符即丟棄重跑。§3.3。
  - [R4/P1] 「空回應=假日」補兩道健檢:單日列數 < `_DAILY_MIN_ROWS` 視同取數失敗;
    快取記完整 `dates`,相鄰日曆間距 > 12 日 → 該輪不採用。§3.3。
  - [R5/P1] 記憶體串流化:逐日 rows → `compute_day_limitups` 集合後即丟,
    純函式吃 `list[set[str]]`(10 個小集合,不是 30 萬 dict)。§3.2。
  - [R6/P1→RESOLVED] `total_amount` 元口徑已以真快照算術實證(2330@12:19:
    15339 張 × 均價 2375.78 × 1000 ≈ 3.644e10 == 36442215000)。§5.2 註記。
  - [R7/P2] parity 註記改指真正會紅的 `test_compute_breadth_row_shape`;
    `record_breadth_parity._SNAPSHOT_FIELDS` 補 high/low(本輪不重錄)。§3.1 / §6。
  - [R8/P2] 多狀態列優先序 limit_up > limit_down > touched;null streak 排序視為 -1。§5.2。
  - [R9/P2] 換日守門 `task is None or task.done()`;檢查移至 `_poll_loop` 每圈
    (不受窗 gate,盤前即重算)。§3.3。
  - [R10/P2] `_get_rows` 加 `timeout` 參數(EOD 帶 60s);前端 refetchInterval
    改函式形式套交易時段 gate(既有 hook 慣例)。§3.3a / §5.2。
  - [R11/P2] 封頂語意由後端 `streak_capped` 表達,前端顯示「N+ 板」;
    窗收不滿(長假)同樣觸發封頂旗標。§3.3 / §5.2。
  - [R12/P2] SC-2 真值 oracle 指定 `data/events/limitup_all.csv`(獨立實作鏈)+
    人工逐日核對;空 rows 且 stale 文案改「暫無資料(延遲)」。§5.2 / §7。

註:brainstorm Q4 的「rows 加 `prev_streak`、前端 +1」被 R1 推翻,已標 amendment。

## 1. 總覽與資料流

```
BreadthEngine(R2 既有 10s poll)
  ├─ rows(engine 內存,R2 已產)──┐
  └─ [新] streak 背景 task          ├─→ [新] rows_state() ─→ [新] GET /api/market/breadth/rows
      FinMind TaiwanStockPrice      │    (後端算 streak/streak_capped)      │
      回看 10 交易日(每日一次,     │                                        ▼
      快取 data/market/streaks-*.json)                  [新] LimitListSection(TanStack Query
                                                         窗內 10s 輪詢,收合展開才 mount)
                                                              │ 點列
                                                              ▼
                                            App.onOpenStock:setStockCode + setTab("stock")
                                            (個股 tab 既有 set_main 路徑,零新機制)
```

原則:零新增訂閱、零新 poll 節奏(rows 搭 R2 既有 10s 循環;streak 每日一次)、
列表頻寬跟著消費者走(REST on-demand,不進 WS)、**連板算術只在後端**(單一真相,
前端零日期推理)。

## 2. SC 對應表

| SC | 設計章節 |
|----|---------|
| SC-1 rows 端點 | §3.3 / §3.4 / §4 |
| SC-2 連板數管線 | §3.1 / §3.2 / §3.3 |
| SC-3 列表畫面 | §5.2 |
| SC-4 篩選持久化 | §5.2 |
| SC-5 跳轉 | §5.3 |
| SC-6 失效域隔離 | §3.3a / §3.4 / §5.2(stale 表述)|

## 3. 後端

### 3.1 `copycat/market_breadth.py` — rows 欄位擴充(修改)

`compute_breadth` 的 `rows_out` 每列新增三欄:

- `close: float | None` — 現價(snapshot `close` 直通)。
- `touched_limit_up: bool` — `high` 毫元等值 == `limit_up_milli(prev_milli)` 且
  `limit_up == False`(曾觸及漲停、現價未鎖)。
- `touched_limit_down: bool` — 對稱以 `low` 判。

實作:`_is_limit` 旁新增

```python
def _is_touched(high: float | None, low: float | None, prev_close: float) -> tuple[bool, bool]:
    """毫元等值判「盤中曾觸及停板」;high/low 缺(舊 fixture / 剪裁快照)→ (False, False)。"""
```

呼叫點在既有 `prev_close is not None and prev_close > 0` gate 內;`high`/`low` 用
`r.get(...)`(真快照有此欄 — 2026-08-06 實跑 parse 確認)。
**該變的既有 assertion = `tests/test_market_breadth.py::test_compute_breadth_row_shape`**
(整 dict 等值,事前標記);parity oracle(`test_breadth_parity`)只比 counts 與逐檔
bucket,不受影響、不重錄。順手:`tests/fixtures/record_breadth_parity.py` 的
`_SNAPSHOT_FIELDS` 白名單補 `high`/`low`(讓下次重錄能覆蓋 touched;本輪不重錄)。

### 3.2 `copycat/limit_streaks.py` — 連板數純函式(新檔,零 IO)

```python
STREAK_WINDOW_DAYS = 10  # 回看交易日數

def compute_day_limitups(rows: list[dict]) -> set[str]:
    """單日 TaiwanStockPrice 全市場 rows → 該日收盤漲停的 4 位普通股代號集合。"""

def compute_prev_streaks(day_sets: list[set[str]]) -> dict[str, int]:
    """`day_sets` = 連續交易日的漲停集合,**新 → 舊**排序(day_sets[0] = 最近可得
    交易日)。回傳 {stock_id: 截至 day_sets[0] 的連續漲停日數},只含 streak ≥ 1。"""
```

- **記憶體串流化(R5)**:呼叫端逐日 fetch → `compute_day_limitups` → 即丟 raw rows;
  常駐只有 ≤ 10 個小集合(全市場單日 ~3 萬列含權證,10 日全持有是數百 MB 級,
  live server 內不可接受)。
- `compute_day_limitups` 規則:
  - Universe:`classify_stock_id(sid) is None`(4 位普通股)才判。
  - `prev_close = close − spread`(FinMind 欄名 `close`/`spread`,
    `backfill_finmind._map_row` 已驗證;除權息安全);`prev_close <= 0` 或欄缺 /
    非數值 → 不判(streak 於該日中斷)。
  - 漲停 = 毫元精確等值:`round(close*1000) == limit_up_milli(round(prev_close*1000))`。
  - 上市首五日無漲跌幅限制:close 天然不等於公式漲停價,自然不計(不需特判)。
- `compute_prev_streaks` 演算法:`candidates = day_sets[0]`(streak=1),逐個較舊日
  `candidates ∩= day_sets[i]`,存活者 streak+1;缺 row(新上市)→ 不在該日集合 →
  自然出局。streak 上限 = len(day_sets)。

### 3.3 `copycat/server/breadth_engine.py` — streak 編排(修改)

streak 編排收進既有引擎(同一個 FinMind 失效域、同一份 config / data_dir,
獨立新類會複製生命週期樣板):

- ctor 新參數 `daily_fetch: DailyPricesFetch | None = None`
  (`DailyPricesFetch = Callable[[str, _dt.date], list[dict]]`;None = 連板停用,
  rows 端點照常、`streak` 恆 null)。
- 新狀態:
  - 成果:`_streaks: dict[str, int]`、`_streaks_day: str | None`(這份是為哪個
    today 算的)、`_streaks_end: str | None`(= 最新資料日 `data_end`)、
    `_streaks_span: int`(實際收到的交易日數)、`_streaks_skipped: set[str]`
    (掃描中被當假日跳過的日期,R15 guard 用)。
  - 排程(R13:**武裝與成功分離**):`_streak_armed_day: str | None`(今日已排程
    過 task,不論成敗)、`_streak_task: asyncio.Task | None`、
    `_streak_attempts: int`(武裝日內的嘗試計數)。
  - `_rows_date: str | None`(R14:`self.rows` 的資料日 — `_apply` 內與
    `self.rows = ...` **同行無條件更新**;`adopt_date=False` 路徑會讓
    `_trade_date` 與 rows 脫鉤,streak 判式不得用 `_trade_date`)。
- `start()`:先 `_restore_streaks()`(讀 `data/market/streaks-<today>.json`,
  版本 / 形狀不符或 `computed_for != today` → 略過;命中則連 `_streak_armed_day`
  一併設為 today)。**不在 start() 起 task**(交給 `_poll_loop` 的武裝檢查,
  時間閘一致);維持 start() 本體零網路 IO(R2 失效域紀律)。
- **武裝檢查(R9+R13+R15)**:`_poll_loop` **每圈、窗 gate 之外**:
  `daily_fetch 有值 and now.time() >= _STREAK_ARM_TIME(06:00) and
  _streak_armed_day != today and (_streak_task is None or _streak_task.done())`
  → 清 `_streaks*`、`_streak_attempts = 0`、`_streak_armed_day = today`、起
  `_compute_streaks_loop()` task。
  - 時間閘理由(R15):若 00:00 即重算,T-1 EOD 可能未發布 → T-1 被當假日跳過 →
    `data_end = T-2` 且該輪**成功**,盤中判式 `T > T-2` 仍 +1 → 整天連板數少 1
    並落檔固化。FinMind EOD 於當日盤後發布,06:00 重算時 T-1 必然可得
    (13+ 小時餘裕);00:00–06:00 之間 `_streaks_day`(昨日)≠ today →
    `ready=False` → 連板欄 null,誠實降級。
  - 超限語意(R13):`_streak_attempts` 只在武裝日切換時歸零;task 超限結束後
    `_streak_armed_day == today` 擋住再武裝,**同日不再重跑**(壞上游不整天燒配額)。
- `_compute_streaks_once()`(單次嘗試;R3 時序修正):
  1. **進場取樣一次 `day = self._today_fn()`**;掃描起點 `day − 1`、快取檔名、
     `computed_for` 全用這個 `day`。
  2. 自 `day − 1` 往回掃日曆日(上限 25 日),`await asyncio.to_thread(daily_fetch, ...)`,
     每 request 間 `asyncio.sleep(0.3)`;單日回應:空 → 假日候選,記入 `skipped`
     並跳過;**非空但列數 < `_DAILY_MIN_ROWS` = 25_000 → 視同該日取數失敗,整輪
     失敗**(R4/R16:部分截斷不可當假日;實測 2026-08-05 全市場單日 42,074 列、
     4 位普通股 2,334 檔,門檻 ~0.6×;每日 log 實際列數供校準)。非空日即
     `compute_day_limitups` 後丟棄 raw rows,收滿 `STREAK_WINDOW_DAYS` 個交易日或
     掃完 25 日為止(收不滿 → `_streaks_span` < 10,封頂語意照樣成立,R11)。
  3. **連續性健檢(R4)**:收到的 `dates` 相鄰兩日日曆間距 > 12 日 → 該輪不採用
     (視同失敗;12 日容春節極端連假,見 KR-3)。
  4. `compute_prev_streaks(day_sets_newest_first)` → 收尾檢查
     `self._today_fn() == day`,**不符即丟棄結果、視同該次失敗**(R3:跨午夜的
     結果是「以昨日為基準」的錯值,且會被快取固化);相符才寫入
     `_streaks/_streaks_day/_streaks_end/_streaks_span/_streaks_skipped` +
     `_save_streaks()`(tmp + `os.replace`,失敗只降級)。
     若 `data_end != day − 1`(昨日被跳過)log warning:昨日若為交易日即少計
     (KR-1 殘餘風險的觀測訊號)。
- `_compute_streaks_loop()`:包 `_compute_streaks_once`,失敗重試:quota →
  sleep `config.quota_backoff_secs`,否則 60s;非預期例外 → log + 60s(任務存活
  邊界)。**嘗試上限 10 次**,超限 log error 後 task 結束(連板欄當日 null;
  再武裝由 `_streak_armed_day` 擋住,R13)。成功後 task 結束。
- `close()`:一併 cancel `_streak_task`。
- 新方法 `rows_state()`(REST 全量;**連板算術在此,R1;日期基準 = `_rows_date`,R14**):

```python
def rows_state(self) -> dict:
    today = self._today_fn().isoformat()
    ready = self._streaks_day == today and self._streaks_end is not None
    rows_date = self._rows_date
    rows_out = []
    for row in self.rows:
        streak: int | None = None
        capped = False
        if ready and row["limit_up"] and rows_date is not None:
            prev = self._streaks.get(row["stock_id"], 0)
            if rows_date in self._streaks_skipped:
                pass                        # rows 資料日曾被當假日跳過 → 關係不明,null(R15)
            elif rows_date > self._streaks_end:
                streak = prev + 1           # rows = 今日盤中,昨日止的 streak + 今日
            elif rows_date == self._streaks_end:
                streak = max(prev, 1)       # rows = 上一交易日收盤快照,該日已在 streak 內
            # rows_date < data_end(理論不可能)→ 保持 None
            if streak is not None and prev >= self._streaks_span:
                capped = True               # streak 撞到回看窗邊緣 → 顯示「N+ 板」
        rows_out.append({**row, "streak": streak, "streak_capped": capped})
    return {"enabled": True, "trade_date": rows_date, "as_of": self._as_of,
            "stale": self._stale(), "streaks_ready": ready, "rows": rows_out}
```

payload 的 `trade_date` = `_rows_date`(= rows 的資料日,與列表內容同源;
`market_breadth` 端點的 `trade_date` 維持既有序列語意,兩端點語意不同屬設計刻意)。
`streak` 三值語意:int(= 含今日的連板數,僅 limit_up 列)/ null(非漲停列、
未就緒、停用、或日期關係異常)。前端**不做任何日期或 +1 算術**。

**streaks 快取檔**:`data/market/streaks-<today>.json`
`{"_version": 1, "computed_for": "<today>", "data_end": "<最新資料日>",
"dates": ["...按新→舊..."], "skipped": ["..."], "streaks": {sid: int}}`
(`dates`/`skipped` 供稽核與 R15 guard;restore 時 `computed_for` 必須 == today
才採用)。

### 3.3a 取數與注入點(修改)

**`copycat/server/breadth_fetch.py`**:
- `_get_rows` 加 keyword-only `timeout: float = _TIMEOUT` 參數(R10)。
- 新增:

```python
def fetch_daily_prices(token: str, day: _date) -> list[dict]:
    """單日全市場 EOD(dataset=TaiwanStockPrice, start=end=day, 無 data_id)。
    timeout=60(MB 級回應,對照 backfill_finmind 慣例);錯誤分類沿 `_get_rows`
    (402 → BreadthFetchError(quota=True) 不重試)。"""
```

(不重用 `backfill_finmind.fetch_day`:錯誤契約不同 — 那條拋 RuntimeError/HTTPError,
R2 引擎的退避分類吃 `BreadthFetchError.quota`。)

**注入點接線(R2 finding;全部列入改動清單)**:
- `app.py`:`BreadthFetchers` 擴成**四元組**
  `tuple[SnapshotFetch, StockInfoFetch, DispositionFetch, DailyPricesFetch | None]`
  (R20:第四槽 None = 連板停用,是契約的一部分,不用 cast 掩蓋;長度固定 4);
  `_make_breadth` DEFAULT_BREADTH 分支補 `breadth_fetch.fetch_daily_prices`,
  解包與 `BreadthEngine(..., daily_fetch=...)` 同步。
- `copycat/server/verify.py`:`fake_breadth_fetchers()` 補第四支 fake
  (回固定兩日 EOD 造值;`VERIFY_BREADTH_FAIL=1` 時同樣拋 `BreadthFetchError` —
  SC-6 注入涵蓋新路徑);fake 快照 rows 補 `high`/`low`(verify 畫面才看得到
  「觸及未鎖」);verify.py docstring 的注入描述同步(R19)。
- **`CLAUDE.md` §1 `VERIFY_BREADTH_FAIL` 說明「三支」→「四支(含 daily prices)」**
  (R19:該句是 SC-6 注入通道的權威記載,不改就成錯誤文件)。
- 既有以三元組建構的測試 / 側車樣板呼叫點:grep `breadth_fetchers` 全數改四元組。
- [amendment 2026-08-06(impl-spec review R8 落地 + Phase 4 R3-T5 收進契約)]:
  `_make_breadth` 顯式注入分支解包前 `len(fetchers) != 4` → `logger.error`
  (「取數元組長度 %d,預期 4(呼叫端未更新)」)再 raise — 防 repo 外側車樣板
  漏改時被 `_boot` 傘罩吞成與「token 未設」同形。
- [amendment 2026-08-06(Phase 4 R3-BE-1/2/3/4、R3-T3 落地)]:前緣間距同閾值
  檢查(today↔dates[0] > 12 日 → 整輪失敗);day→set memo 跨 attempt 保留進度;
  成功時 `_streak_armed_day` 對齊 day;restore 補 dates 非空 / dates[0]==data_end /
  長度一致三檢;per-day date 回聲檢查 + 全日零漲停 warning。

### 3.4 `copycat/server/app.py` — 路由(修改)

```python
@app.get("/api/market/breadth/rows")
async def market_breadth_rows(request: Request) -> dict:
```

恆 200 三態(R2 `market_breadth` 同款判式:`_breadth` / `_breadth_booted`):
引擎 None → `{"enabled": <loading>, "trade_date": None, "as_of": None,
"stale": <loading>, "streaks_ready": False, "rows": []}`(`stale` 對齊 R2 loading
分支語意,R18);否則 `breadth.rows_state()`。
**前端載入判別子 = `as_of`**(首輪成功前恆 null;R18 — `stale` 在冷啟動 degraded
下恆 True,拿它判「載入中」會兩態顛倒)。
不碰 WS(brainstorm Q2);失效域:本 route 只讀 breadth 引擎,TC4 系零依賴(SC-6)。

## 4. API 契約(前後端同步)

```
GET /api/market/breadth/rows →
{ enabled: bool, trade_date: string|null, as_of: "HH:MM:SS"|null, stale: bool,
  streaks_ready: bool,
  rows: [{ stock_id, name, market: "twse"|"tpex", close: number|null,
           change_rate: number, volume_ratio: number|null, total_amount: number|null,
           limit_up: bool, limit_down: bool,
           touched_limit_up: bool, touched_limit_down: bool,
           streak: number|null, streak_capped: bool }] }
```

## 5. 前端

### 5.1 `types.ts` / `constants.ts`(修改)

- `BreadthRow` / `BreadthRowsState` interface(§4 直譯)。
- 新 key:`LIMIT_LIST_OPEN_KEY`(收合)、`LIMIT_LIST_FILTER_KEY`(篩選 JSON)。

### 5.2 `components/index/LimitListSection.tsx`(新檔)

- 收合 section,`CorrSection` 同款慣例:標題「漲跌停」、`aria-expanded` 鈕、
  **收合 = unmount**(query 只在展開時存在)、localStorage lazy init 全包 try/catch。
- 展開時 `useQuery({ queryKey: ["breadth-rows"],
  refetchInterval: () => (inHours() ? 10_000 : false) })`(R10:交易時段 gate,
  既有 useMarketBars / useGroupSnapshots 慣例;`inHours` 用專案既有實作)。
- 篩選列(單一 state 物件,JSON 存 `LIMIT_LIST_FILTER_KEY`,任一變更即寫回):
  - 市場:「上市」「上櫃」checkbox(預設皆開)。
  - 狀態:「漲停」「跌停」「觸及未鎖」checkbox(預設皆開;OR 語意;
    觸及未鎖 = `touched_limit_up || touched_limit_down`,已鎖列不重複入此類)。
  - 成交金額門檻:number input(**億元;`total_amount` 元口徑已實證** —
    2330@12:19 真快照 15339 張 × 均價 2375.78 × 1000 ≈ 3.644e10 ==
    36442215000;`total_amount >= x*1e8`,null 不過門檻)。
  - 股價區間:min / max number input(空 = 不限;`close` null 不過區間篩)。
- **狀態歸屬優先序(R8)**:`limit_up > limit_down > touched`;badge 取第一個命中
  (多狀態列如「觸及漲停後殺到跌停」歸 limit_down,badge 唯一)。
- 表格欄:代號、名稱、市場(上市/上櫃)、現價、漲跌幅%(`text-bull`/`text-bear`)、
  連板(`limit_up` 列:`streak != null` → `streak_capped ? "N+ 板" : "連 N 板"`;
  `streak == null` → 「-」;非漲停列空白)、成交金額(億,1 位小數)、量比、
  狀態 badge。
- 預設排序:漲停(streak desc,**null 視為 -1 排組內最後**,R8)→ 跌停 → 觸及,
  同組內 `total_amount` desc(穩定可測)。
- 空 / 載入 / stale 表述(R12+R18,判別子 = `as_of`):`enabled=false` →
  「FinMind 未設定」;`as_of == null` →「載入中…」;`as_of != null` 且 rows 空 →
  「暫無資料(延遲)」;`stale=true` **只**負責標題列 amber「延遲」膠囊
  (BreadthBand 同款語彙),不參與空狀態分流;篩選後 0 列 →「無符合條件」。
  [amendment 2026-08-06(Phase 3 Task D 新發現 case):query error 終態(網路 /
  proxy 斷;端點恆 200 故僅發生在傳輸層)→「載入失敗」,`isError` 判在
  `data === undefined` 之前 — 否則「已放棄」會永遠顯示成「載入中…」。]
  [amendment 2026-08-06(Phase 4 code review):(a) FE-1 —「載入失敗」只在
  從未成功(`isError && data === undefined`)時出現;有 data 的 refetch 失敗
  **保留表格** + 標題列「更新失敗」膠囊(border 版與「延遲」區分)。(b) FE-4 —
  空態三分:狀態池(有任一狀態的列)為 0 →「今日尚無漲跌停」;池 > 0 且篩選後
  0 列 →「無符合條件」。(c) FE-2 — App 傳 `active={tab === "index"}` 貫穿至
  `useBreadthRows(active)`,hidden tab 停輪詢(只停 interval 不關 enabled,
  useFuturesBars 慣例)。]
- 列 `onClick` → `props.onOpenStock(stock_id)`;`cursor-pointer` + hover 高亮。

### 5.3 `IndexPage.tsx` / `App.tsx`(修改)

- `IndexPage` 新 prop `onOpenStock?: (code: string) => void`;
  `<LimitListSection onOpenStock={onOpenStock} />` 插在家數 section 與
  `<CorrSection />` 之間(總 spec §4 版面:列表屬「下方區塊」帶)。
- `App.tsx`:`<IndexPage ... onOpenStock={(code) => { setStockCode(code); setTab("stock"); }} />`
  —— `setTab("stock")` 走既有 visited gate → StockPage mount → 既有
  `/api/stock/state/{code}`(內含 set_main)路徑,個股 tab 零改動。

## 6. 測試策略

後端(pytest):
- `tests/test_limit_streaks.py`(新):除權息 spread 日連板延續 / 非漲停中斷 /
  窗內缺 row(新上市)出局 / 窗長上限封頂 / 權證代號被剃除 / prev_close ≤ 0 不判 /
  `compute_day_limitups` 單日語意。
- `tests/test_market_breadth.py`(擴):touched 兩向 / high==漲停且已鎖 → touched
  False / 欄缺降級 / close 直通;`test_compute_breadth_row_shape` 預期補新欄
  (事前標記「該變」;parity oracle 不動)。
- `tests/test_breadth_engine.py`(擴):
  - streak 成功路徑(fake daily_fetch 含假日空日)/ 快取 restore 同日不重打
    (fake 計數 == 0)/ 換日清舊值重算(含「restore 命中、task 從未存在」情境,R9)。
  - **rows = 上一交易日快照(rows_date == data_end)時 streak 不 +1**(R1)。
  - **`adopt_date=False` 路徑(快照日既非今日也非序列日)不 +1**(R14:判式用
    `_rows_date` 不用 `_trade_date`)。
  - **跨午夜完成的結果被丟棄**(R3:today_fn 前後不一致)。
  - **窗中真交易日回空高估防禦**:低列數日(門檻 25,000 附近取值)→ 整輪失敗;
    dates 間距 > 12 → 不採用(R4/R16)。
  - **rows_date ∈ skipped → streak null**(R15 guard)。
  - **06:00 前不武裝**(R15 時間閘);**超限後同日不再起新 task**(R13:fake
    daily_fetch 呼叫次數有上界)。
  - 取數失敗退避 / 嘗試上限 10 次後放棄。
  - `rows_state()` merge 語意(ready 前 null、非漲停列 null、capped 旗標)。
- route 測試(擴):`/api/market/breadth/rows` 三態(loading / 未設定 / 有引擎)。

前端(vitest):
- `LimitListSection.test.tsx`(新):篩選各維度 / localStorage 持久化(SC-4)/
  列點擊呼叫 onOpenStock / 連板欄三態文案(連 N 板 / N+ 板 / -)/ 多狀態列歸屬
  (R8)/ stale 膠囊與「暫無資料(延遲)」/ 收合 unmount。
- `App.test.tsx`(擴):onOpenStock 觸發後 tab 切 stock、StockPage 收到 code(SC-5)。
- `IndexPage.test.tsx`(擴):section 出現在家數帶之下。

## 7. 驗證計畫(窗口)

| SC | anytime | 盤中加強 |
|----|---------|---------|
| SC-1 | pytest route + engine | 側車 server(fake TXO + 真 FinMind 四支,R2 樣板)curl 對照 |
| SC-2 | pytest 純函式 + 快取計數;真 EOD 實跑,oracle = `data/events/limitup_all.csv`(獨立實作鏈)交叉 + 人工逐日核對 1-2 檔 close vs 漲停價(R12) | —(EOD 盤後即定)|
| SC-3 | vite dev + fixture 截圖 | 真資料截圖 + user 過目 |
| SC-4 | vitest | — |
| SC-5 | vitest App 級 | 點擊後五檔跳動截圖 + user 過目 |
| SC-6 | pytest + `--verify` `VERIFY_BREADTH_FAIL=1` 注入(涵蓋第四支 fake,R2 finding)| — |

## 8. Known Risks

- **KR-1(P2,v3 重寫)**:武裝時間閘 06:00 後,T-1 EOD「仍」缺席的情境只剩
  FinMind 端異常(正常發布是前日盤後,13+ 小時餘裕)。該情境下 T-1 被記入
  `skipped`:盤前(rows_date = T-1 ∈ skipped)→ null 誠實降級;**盤中**
  (rows_date = T)判式 `T > T-2` 仍會 +1 → 連板數少 1,靜默。殘餘窗 = FinMind
  丟失昨日整日資料且當日快取已固化;`data_end != day−1` 的 log warning +
  `dates`/`skipped` 落檔為觀測與稽核通道。接受理由:觸發前提是上游資料事故,
  且錯向為少計(保守向),重啟不放大(cache 當日有效)。
- **KR-2(P2)**:rows payload ~2800 列 × 15 欄,10s 輪詢數百 KB —— 僅列表展開 +
  交易時段內發生(R10 gate),單機 localhost 可接受。
- **KR-3(P2)**:連續性健檢閾值 12 日曆日 — 春節極端連假(~9-11 日)不誤殺;
  若未來出現 > 12 日的停市,該輪會被誤判不採用(連板欄 null 降級,非錯值)。
