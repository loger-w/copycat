# PLAN v2 — 台股綜合 R2(condensed;design v2+amendments 對應)

> Changelog:v2(2026-08-06)= impl-spec review round 1(6 P1 / 5 P2 全 accepted)修入:
> R1 _ENV_KEY 入搬移範圍;R2 _Booted+反序 close;R3 state 預掛 None;R4 create_app
> data_dir 通道;R5 依賴表更正;R6 disposition query 參數名 start_date/end_date;
> R7 分鐘鍵改用 index_engine.minute_key(floor+1,域 0901–1330);R8 useBreadth 移
> App 層;R9 as_of/trade_date 推導釘死;R10 verify fake 跳過 token 閘;R11 測試遷移
> 行號更正。Review JSON:`../impl-spec-review-round-1.json`。

> **For agentic workers:** 逐 task 實作,執行模式由 feat.md Phase 3 決定。
> 寫 .py 前讀 `backend-conventions` + `finmind-conventions`;寫 frontend 前讀
> `frontend-conventions` + `frontend-testing`;ADL 圖前過 `dataviz`。
> TDD:每 task 紅測試先行(`[red]` → `[green]` commit;🔵 refactor 單獨)。

**Goal:** FinMind 全市場管線 + 家數帶 + 騰落線(SC-1~SC-5)。
**全域約束:** stdlib-only runtime(urllib,無 httpx);毫元整數運算;
`from __future__ import annotations`;error contract `{"detail":{"error":code}}`;
盤中不起第二台連 TC4 後端;line-length 100。

任務依賴(R5 更正):T1 獨立;T2 先行,**T3 依 T2**(compute_breadth 呼叫
limit_*_milli);T4 / T5 獨立(可與 T2/T3 並行);T6 依 T2-T5;**T7 依 T1 + T6**
(make 內 resolve_token);T8 依 T7 契約(可 fixture 先行);T9 依 T8;T10 隨時。

---

### Task 1:🔵 finmind_token 抽出(oi_levels 零行為改動)

- Create `copycat/server/finmind_token.py`:**四符號**自 oi_levels 搬(R1):
  `_ENV_KEY = "FINMIND_TOKEN"`(:42)+ `_dotenv_values()`(:87-103)+
  `_dotenv_cache`(:106)+ `resolve_token()`(:109-120),docstring 同。
- Modify `copycat/server/oi_levels.py`:刪四符號(含 :42 `_ENV_KEY` —— 其餘處不再
  引用),改 `from copycat.server import finmind_token` 後**經模組屬性呼叫**
  `finmind_token.resolve_token()`(:333);不留 re-export(design R5)。
- Modify `tests/conftest.py:54-78`:patch 目標改 `copycat.server.finmind_token`
  (新模組 stdlib-only,保留 try/except ImportError 亦可)。
- Modify `tests/server/test_oi_levels.py`(R11):`:37 _REAL_DOTENV_VALUES` 與
  `:363-394` `TestResolveToken` 整組遷 Create `tests/server/test_finmind_token.py`
  (patch 目標改新模組);`:131`(`_fresh_cache` fixture 內)**留在原檔** retarget
  成 `monkeypatch.setattr(finmind_token, "_dotenv_cache", None)`;`:430`
  `monkeypatch.setattr(oi, "resolve_token", ...)` 改 patch
  `finmind_token.resolve_token`。
- 驗:`pytest tests/server/test_oi_levels.py tests/server/test_finmind_token.py -q`
  全綠 → 🔵 commit(refactor tag,無 red/green)。

### Task 2:market.py 毫元 limit 介面(SC-1 前置)

- Modify `copycat/market.py`:

```python
def limit_up_milli(prev_close_milli: int) -> int:
    cand = prev_close_milli * 11 // 10
    tick = _tick_milli(cand)
    return cand // tick * tick

def limit_down_milli(prev_close_milli: int) -> int:
    cand = prev_close_milli * 9 // 10
    tick = _tick_milli(cand)          # cand(ceil 前)所在段 — design R13
    return -(-cand // tick) * tick    # ceil

def limit_up_price(prev_close: float) -> float:   # 薄包裝,行為不變
    return round(limit_up_milli(round(prev_close * 1000)) / 1000, 2)
```

- Test `tests/test_market.py`(既有檔追加):手算對照 —— 9.99/45.5/90.9/111.1/999
  段邊界 × up/down;`limit_up_price` 既有案例不動(行為合約)。
- 紅 → 綠 commit(SC-1)。

### Task 3:market_breadth.py 純函式層(SC-1 核心)

- Create `copycat/market_breadth.py`,全零 IO,自 neigui 搬(design §3 逐函式來源):
  - `classify_stock_id(stock_id: str) -> str | None`、
    `filter_universe(candidates: list[str], watch_list: set[str]) -> dict`
  - `build_type_map(rows) -> dict[str, str]`、`build_name_map(rows) -> dict[str, str]`、
    `dedup_sector_map(rows) -> dict[str, str]`(含 `PRIMARY_INDUSTRY_OVERRIDE` 表)
  - `parse_active_disposition(rows: list[dict], today: date) -> set[str]`
  - `max_tick_datetime(rows: list[dict]) -> datetime | None`(Z 尾 UTC→台北 naive)
  - `assemble_universe(rows, primary_sector, watch_list) -> list[dict]`(白名單→filter)
  - `compute_breadth(rows, type_map, name_map) -> dict | None`(毫元 limit 判定:
    `round(close*1000) == limit_up_milli(prev_milli)`;餘規則 neigui 原樣,全空回 None)
- Test `tests/test_market_breadth.py`:逐函式手算小樣本 + limit 邊界手造 fixture
  (漲停/跌停/差半 tick/差一 tick — design §8)。
- **parity**:Create `tests/fixtures/record_breadth_parity.py`(產生腳本:錄原始
  snapshot/stock_info/disposition rows + 以 neigui 現碼跑完整組裝出 expected,寫
  `tests/fixtures/breadth_parity.json`;檔頭註記重跑方式與錄製 row 數);
  `test_breadth_parity`:copycat 全管線(dedup_sector_map→assemble_universe→
  compute_breadth)counts 全等 + rows 逐檔 bucket 全等。
  腳本執行需 FINMIND_TOKEN + import neigui repo —— 一次性手跑,fixture 進版控。
- 紅 → 綠 commit(SC-1)。

### Task 4:breadth_config.py

- Create `copycat/breadth_config.py`(`signals_config.py` 同款):

```python
@dataclass(frozen=True, slots=True)
class BreadthConfig:
    poll_secs: float = 10.0
    window_start: str = "08:55"   # 台北;poll 窗
    window_end: str = "13:40"
    stale_secs: float = 30.0
    backoff_max_secs: float = 60.0
    quota_backoff_secs: float = 300.0
CONFIG_PATH = <repo>/configs/breadth.json
def load_breadth_config(path=CONFIG_PATH) -> BreadthConfig
```

- Test:載入預設 / 覆寫 / 未知鍵 raise(既有 config 測試同款)。紅 → 綠 commit。

### Task 5:breadth_fetch.py 取數層

- Create `copycat/server/breadth_fetch.py`(阻塞;`oi_levels._fetch_rows:180-217`
  同款錯誤分類):
  - `class BreadthFetchError(RuntimeError)`(帶 `quota: bool` 屬性,402 → True 不重試)
  - `fetch_snapshot(token: str) -> list[dict]`:`GET /api/v4/taiwan_stock_tick_snapshot`
    **無 query 參數**(Bearer,timeout 30s,_ATTEMPTS=2)
  - `fetch_stock_info(token: str) -> list[dict]`:`GET /api/v4/data?dataset=TaiwanStockInfo`
    (row 數 log,`< 3000` warning — design R14;門檻依 T3 實錄 4300 列下修
    [phase-3 補註],原 5000 會恆 warning)
  - `fetch_disposition(token: str, today: date) -> list[dict]`:`GET /api/v4/data?
    dataset=TaiwanStockDispositionSecuritiesPeriod&start_date=<today−60d>&
    end_date=<today>`(**參數名 start_date/end_date** — oi_levels/neigui 同款;R6)
- Test `tests/server/test_breadth_fetch.py`:monkeypatch urlopen —— 402 raise
  quota=True 不重試 / TimeoutError 重試一次 / 非 JSON 重試 / row 數 warning /
  **斷言送出的 query 參數名與值**(test_oi_levels `test_range_query_and_bearer`
  同款;R6)。
- 紅 → 綠 commit(SC-3 錯誤分類)。

### Task 6:breadth_engine.py(SC-2/SC-3 核心;高風險面,完整簽名)

- Create `copycat/server/breadth_engine.py`:

```python
class BreadthEngine:
    def __init__(self, *, token: str, config: BreadthConfig,
                 snapshot_fetch: Callable[[str], list[dict]],
                 stock_info_fetch: Callable[[str], list[dict]],
                 disposition_fetch: Callable[[str, date], list[dict]],
                 data_dir: Path | None = None,      # None → <repo root>/data/market
                 today_fn: Callable[[], date] = date.today,
                 now_fn: Callable[[], datetime] = datetime.now) -> None: ...
    async def start(self) -> None    # restore(讀 breadth-<today>.json)+ create_task;零網路 IO
    async def close(self) -> None
    def state(self) -> dict          # {"enabled": True, trade_date, as_of, stale, counts|None, series}
    def stream(self) -> AsyncGenerator[dict, None]
```

- 內部(design §5 全條款):poll loop 首圈無條件 fetch、後續僅窗內;maps 24h TTL
  成功才刷新(失敗保前值不動時戳,冷啟動失敗 degraded 每輪重試);連續失敗退避
  10→20→40→60s、quota 402 → 300s、成功復位;trade_date restore 還原 + 換日判定
  「舊值非 None 且 ≠ 新值」才清 series;**append+落檔僅 `trade_date == today_fn()`**;
  落檔 tmp+`os.replace`,`_version: 1`;compute 回 None 視同該輪失敗;stale =
  degraded or(窗內且 now−last_success > stale_secs);每輪 publish WS payload
  (design §6 形狀,`last_minute` 本輪有 append 才帶)。
- **時刻推導(R9)**:`dt = market_breadth.max_tick_datetime(原始 snapshot rows)`
  (未過濾 —— neigui `_max_tick_date(universe)` 同口徑);`dt is None` → 該輪視同
  失敗(不動 counts/trade_date);`trade_date = dt.date().isoformat()`、
  `as_of = dt.strftime("%H:%M:%S")`。
- **分鐘鍵(R7)**:改用 `index_engine.minute_key(dt.strftime("%H%M%S"), utc=False)`
  (floor+1 終點標記,域 **0901–1330**、1331–1335 clamp —— 與同頁指數分時圖同語意,
  brainstorm SC-4「09:01–13:30」一致);回 None 即丟棄(盤後定盤 14:30 / 盤前自然
  排除)。
- Test `tests/server/test_breadth_engine.py`(fake fetch + tmp_path + 注入
  today_fn/now_fn;design §8 engine 清單全蓋,含 R1/R2/R3 三條指名情境)。
- 紅 → 綠 commit(SC-2 + SC-3)。

### Task 7:app 接線(對外 API;高風險面)

- Modify `copycat/server/app.py`:
  - `DEFAULT_BREADTH: Final = object()`;`create_app(..., breadth_fetchers=None,
    breadth_data_dir: Path | None = None)`(**None=不啟動**;`DEFAULT_BREADTH` →
    真取數層三元組;tuple 三元組直接傳 fake。`breadth_data_dir` 下傳 engine ——
    測試一律傳 tmp_path,避免落檔進真 repo `data/`;R4)。
  - lifespan 進場預掛 `app.state.breadth = None`(其餘八引擎同款預掛區塊;boot 窗內
    REST 才不會 AttributeError → 502;R3)。
  - lifespan:`_boot("breadth", ...)` **排序列最後**(corr 之後);`_Booted` dataclass
    新增 `breadth: BreadthEngine | None = None`,`booted.breadth` 與
    `app.state.breadth` 成對指派;finally 反序 close 鏈**最前面**(signals 之前)加
    breadth try/except close(R2)。`make` 分兩路(R10):`DEFAULT_BREADTH` →
    `finmind_token.resolve_token()` None 則 log「FINMIND_TOKEN 未設定,家數帶停用」
    → None;**顯式 fake 三元組 → 跳過 token 閘**(dummy token 建 engine)。
  - `GET /api/market/breadth`:恆 200 三態(design §6;engine None → enabled=false)。
  - `WS /ws/breadth`:relay helper,首則 seed = scalar payload;engine None →
    accept 後 close(對齊 `/ws/index` 現碼處置)。
- Modify `copycat/server/__main__.py`:prod 分支 `breadth_fetchers=DEFAULT_BREADTH`;
  `--verify` 分支傳 `verify.py` fake 三元組。
- Modify `copycat/server/verify.py`:`fake_breadth_fetchers() -> tuple`(固定小
  fixture 快照,支援以 env `VERIFY_BREADTH_FAIL=1` 注入失敗 — SC-3 real-env 通道;
  無 token 環境照常可用,R10);docstring 補「breadth 走 fake 不打真 FinMind;
  oi-levels 照舊真打」。
- Test `tests/server/test_breadth_routes.py`(**BootedClient** — design R12):REST
  三態 / WS seed+增量 / engine None WS close / **breadth fake 拋錯時
  `/api/index/state` 照常 200(SC-3 隔離)**。
- 紅 → 綠 commit(SC-3 + API 契約)。

### Task 8:前端型別 + useBreadth

- Modify `frontend/src/types.ts`:`BreadthBuckets = [number,number,number,number,
  number]`(註解桶序 lu/u/f/d/ld)、`BreadthCounts`、`BreadthPoint {t: string;
  twse: BreadthBuckets; tpex: BreadthBuckets}`、`BreadthState {enabled; trade_date;
  as_of; stale; counts: {twse; tpex} | null; series: BreadthPoint[]}`。
- Create `frontend/src/hooks/useBreadth.ts`:**手寫 fetch + WS**(鏡射
  `useIndexStream.ts` 結構;merge 契約:onopen refetch 全量、`trade_date` 變更清
  series+refetch、`last_minute` 依 `t` upsert、counts 覆寫)。**呼叫點在 App 層**
  (`useIndexStream`/`useFuturesStream` 現行位置同款),`BreadthState` 以 props 下傳
  IndexPage —— IndexPage 維持純展示,既有 11 例測試不必 stub WS(R8)。
- Test `useBreadth.test.ts`:合併三契約 + 斷線重連補格(frontend-testing 慣例)。
- 紅 → 綠 commit(SC-4 資料層)。

### Task 9:前端元件 + 版面(SC-4)

- Create `frontend/src/components/index/BreadthBand.tsx`:兩列(上市/上櫃)× 五格
  「漲停/上漲/平盤/下跌/跌停」;漲停格紅底(`bg-bull` 系)、跌停格綠底(`bg-bear`
  系)、中間中性;`stale` →「資料延遲」徽章;三態:enabled=false「FinMind 未設定」/
  counts=null「載入中」/ 正常。
- Create `frontend/src/components/index/AdvanceDeclineChart.tsx`:SVG;x=0900–1330、
  y=net(=(lu+u)−(d+ld) 兩市合計);0 軸可見;域外/未知鍵不產生點;`lib/svg-points`
  共用;**先過 dataviz skill**。
- Modify `frontend/src/components/index/IndexPage.tsx:106-107`:雙圖 grid 之後、
  `<CorrSection/>` 之前插入 `<BreadthBand .../>` + `<AdvanceDeclineChart .../>`
  (`breadth: BreadthState | null` 由 App props 下傳;R8)。
- Modify `frontend/src/App.tsx`:呼叫 `useBreadth()` 並下傳 IndexPage(既有
  useIndexStream 同位置)。
- Test:`BreadthBand.test.tsx`(三態 + 格值 + stale)/
  `AdvanceDeclineChart.test.tsx`(net 計算 + 域外鍵防禦 + 0 軸存在)/
  `IndexPage.test.tsx` 追加(傳 breadth props → 中段出現;App.test 視既有 stub
  形狀補 `/api/market/breadth` fetch 分流)。
- 紅 → 綠 commit(SC-4)。

### Task 10:文件債(SC-5)

- Modify `CLAUDE.md`:§0 例外段補「全市場廣度(家數/漲跌停列表/類股)走 FinMind —
  R2 起引入,理由同 §0a 例外句式」;§1 .env 段補 `FINMIND_TOKEN`(已有 secret 列,
  補 breadth 用途與未設降級語意);§0 結構表補 market_breadth / breadth_engine 行。
- 純文件 commit(🟢 chore/docs,無 TDD tag)。

---

**Phase 5 gate**(auto-verify):pytest + ruff + pyright + copycat validate;
frontend:npm test + npx tsc -b + npx eslint src。
**Phase 6**:--verify server(port 8722,fake breadth)REST/WS 三態 + SC-3 注入;
vite dev + claude-in-chrome 截圖(SC-4);SC-1 盤中對照(窗口外記 pending);
SC-2 盤後重啟實測。
