# Implementation PLAN — 台股綜合 R3:漲跌停列表 + 個股跳轉

> 依 design.md v3;impl-spec review round 1(10 findings)已全數修入。
> condensed 模式,每檔一節;TDD 紅先行,commit tag 依 feat.md Phase 3 步驟 2。
> 高風險節(引擎 / 對外 API)放寬到完整 signature。
> 執行順序:後端 1→2→3→4→5→6(1、2 可並行),前端 7→8→9(7 先;8、9 依 7 的型別),
> 收尾 10。
>
> **事前標記「該變」的既有 assertion(鐵則 E 白名單)**:
> - `tests/test_market_breadth.py::test_compute_breadth_row_shape`(row dict 補三欄)
> - `tests/server/test_main_wiring.py` 的 `len(...["breadth_fetchers"]) == 3` → `== 4`

## 1. `copycat/limit_streaks.py`(新)+ `tests/test_limit_streaks.py`(新)

- 純函式零 IO:`STREAK_WINDOW_DAYS = 10`;
  `compute_day_limitups(rows: list[dict]) -> set[str]`(4 位普通股 filter 用
  `market_breadth.classify_stock_id`;`prev_close = close − spread`,缺欄 / 非數值 /
  `<= 0` 不判;毫元等值 `round(close*1000) == limit_up_milli(round(prev*1000))`);
  `compute_prev_streaks(day_sets: list[set[str]]) -> dict[str, int]`(新→舊,
  交集遞進,只含 streak ≥ 1)。
- 紅測試(SC-2):除權息 spread 日延續 / 中斷 / 缺 row 出局 / 窗長封頂 /
  權證代號剃除 / prev_close ≤ 0 / `compute_day_limitups` 單日語意 / 空輸入。

## 2. `copycat/market_breadth.py`(修)+ `tests/test_market_breadth.py`(擴)

- `_is_touched(high, low, prev_close) -> tuple[bool, bool]`(毫元等值,缺值
  `(False, False)`);`compute_breadth` rows_out 加 `close` / `touched_limit_up`
  / `touched_limit_down`(在既有 prev_close gate 內呼叫;`r.get("high")/("low")`)。
- 紅測試(SC-1):touched 兩向 / 已鎖不 touched / 欄缺降級 / close 直通。
  既有 `test_compute_breadth_row_shape` 預期 dict 補三欄(**事前標記該變**;
  parity oracle 不動)。

## 3. `copycat/server/breadth_fetch.py`(修)+ `tests/server/test_breadth_fetch.py`(擴)

- `_get_rows(..., *, timeout: float = _TIMEOUT)`;
  `fetch_daily_prices(token: str, day: _date) -> list[dict]`:
  `dataset=TaiwanStockPrice, start_date=end_date=day.isoformat()`,timeout=60,
  錯誤分類沿 `_get_rows`(402 → quota=True)。
- 紅測試:URL 組裝(monkeypatch urlopen)/ 402 → quota / timeout 參數傳遞。

## 4. `copycat/server/breadth_engine.py`(修)+ `tests/server/test_breadth_engine.py`(擴)【高風險 — 完整 signature】

```python
DailyPricesFetch = Callable[[str, _dt.date], list[dict]]
_DAILY_MIN_ROWS = 25_000   # 實測 2026-08-05 全市場 42,074 列;部分截斷不可當假日(R16)
_STREAK_ARM_TIME = _dt.time(6, 0)  # 06:00 前不武裝(R15:T-1 EOD 發布餘裕)
_STREAK_SCAN_CAL_DAYS = 25
_STREAK_MAX_ATTEMPTS = 10
_STREAK_GAP_CAL_DAYS = 12
_STREAK_REQ_GAP_SECS = 0.3   # 模組層名字 → 測試 monkeypatch 為 0(不靠真 sleep 測)
_STREAK_RETRY_SECS = 60.0    # 同上;quota 退避仍走 config.quota_backoff_secs

class BreadthEngine:
    def __init__(..., daily_fetch: DailyPricesFetch | None = None)
    # 成果:_streaks / _streaks_day / _streaks_end / _streaks_span / _streaks_skipped
    # 排程:_streak_armed_day / _streak_task / _streak_attempts
    # rows 同源日:_rows_date(_apply 內與 self.rows 同步無條件更新;R14)
    def rows_state(self) -> dict   # design §3.3 code block;日期基準 _rows_date
    async def _compute_streaks_once(self) -> bool   # day 進場取樣;掃描+健檢+純函式+落檔
    async def _compute_streaks_loop(self) -> None   # 重試/退避/上限
    def _maybe_arm_streaks(self) -> None            # _poll_loop 每圈呼叫(見下)
    def _save_streaks(self) / def _restore_streaks(self)  # streaks-<today>.json,_version=1
```

- **行為性機制(review R7,不是簽名但必落)**:
  - `daily_fetch` 一律 `await asyncio.to_thread(...)`(同步阻塞取數 MB 級 /
    timeout 60s,直呼會凍整個 event loop → 全站 WS 一起停,失效域紀律紅線);
    每 request 間 `asyncio.sleep(_STREAK_REQ_GAP_SECS)`。
  - `start()` → `_restore_streaks()`,**命中即 `_streak_armed_day = today`**
    (SC-2「同日第二次啟動不打 FinMind」的實際機制)。
  - `_maybe_arm_streaks` 命中時三動作:清 `_streaks*` / `_streak_attempts = 0` /
    `_streak_armed_day = today`,再起 task。
  - 快取 payload 欄位:`_version / computed_for / data_end / dates / skipped / streaks`。
  - `rows_state()` 落地時把 `self._streaks_end` 綁區域變數再比較(review R4:
    pyright basic 不傳遞經 bool 變數的 narrowing,`rows_date > self._streaks_end`
    會報 reportOptionalOperand;禁 `# type: ignore` 掩蓋)。
- `_maybe_arm_streaks()` 呼叫點:`_poll_loop` **`try:` 之內**、`if first or
  self._in_window()` 之外(review R9:放 try 外的例外會殺整條 poll task —
  家數面板凍住零訊號);武裝條件:daily_fetch 有值、`now.time() >= _STREAK_ARM_TIME`、
  `_streak_armed_day != today`、task None 或 done。
- `close()` cancel `_streak_task`(與 `_task` 同款收攤)。
- 紅測試清單 = design §6 test_breadth_engine 節逐條(成功路徑 / restore 不重打 /
  換日重算 / rows_date==data_end 不 +1 / adopt_date=False 不 +1 / 跨午夜丟棄 /
  低列數整輪失敗 / gap>12 不採用 / skipped guard / 06:00 前不武裝 / 超限同日不再起 /
  退避 / rows_state merge 語意)+ 「`_maybe_arm_streaks` 拋例外時 poll loop 續行」
  (review R9)。fake daily_fetch 用呼叫計數 + 造日曆(含週末空日)。
  **測試機制(review R3)**:monkeypatch `_STREAK_REQ_GAP_SECS`/`_STREAK_RETRY_SECS`
  為 0 後直接 await `_compute_streaks_once()` / `_compute_streaks_loop()`;
  退避斷言驗「sleep 被呼叫的秒數」不真等(既有檔頭「不靠真 sleep 測」慣例)。

## 5. `copycat/server/app.py`(修)+ `tests/server/test_breadth_routes.py`(擴)【對外 API — 完整 signature】

- `BreadthFetchers = tuple[SnapshotFetch, StockInfoFetch, DispositionFetch,
  DailyPricesFetch | None]`(R20);`_make_breadth` DEFAULT 分支第四支 =
  `breadth_fetch.fetch_daily_prices`,顯式注入分支解包 4 槽傳
  `daily_fetch=fetchers[3]`。
- **解包防呆(review R8)**:顯式注入分支解包前 `len(fetchers) != 4` →
  `logger.error("breadth 取數元組長度 %d,預期 4(呼叫端未更新)")` 再 raise —
  repo 外的側車樣板漏改時,錯誤不得被 `_boot` 傘罩吞成與「token 未設」同形。
- `GET /api/market/breadth/rows`:引擎 None → `{"enabled": loading,
  "trade_date": None, "as_of": None, "stale": loading, "streaks_ready": False,
  "rows": []}`;否則 `rows_state()`(design §3.4/§4 契約)。
- 紅測試:三態(loading / 未設定 / 有引擎)+ 契約欄位齊全。
- **三元組 → 四元組波及面(review R1,逐檔列出)**:
  - `tests/server/test_breadth_routes.py`:`_ok_fetchers()` / `_raising_fetchers()`
    工廠補第四槽(raising 版第四支同拋)。
  - `tests/server/test_main_wiring.py`:`len(...) == 3` → `== 4`(已列檔頭該變白名單)。
  - `tests/server/test_verify.py`:兩處 `snapshot, stock_info, disposition =
    fake_breadth_fetchers()` 三元解包改四元。
  - 其餘 grep `breadth_fetchers` 建構點。

## 6. `copycat/server/verify.py`(修)+ `CLAUDE.md` §1(修)+ `tests/fixtures/record_breadth_parity.py`(修)

- `fake_breadth_fetchers()` 四元組:第四支回固定兩日 EOD 造值(含一檔連板),
  `VERIFY_BREADTH_FAIL=1` 同拋 `BreadthFetchError`;fake 快照 rows 補 `high`/`low`
  (至少一檔觸及未鎖);docstring「三支」→「四支」。
- **紅測試(review R2 — SC-6 注入通道不得零覆蓋)**,`tests/server/test_verify.py`:
  - `test_verify_breadth_fail_injects_all_three` 擴到四支(改名 `_all_four`)。
  - 第四支 fake 兩日 EOD 造值餵 `compute_day_limitups` + `compute_prev_streaks`
    後,指定股 streak == 2(語意斷言,防 fake 資料本身沒覆蓋)。
  - `test_fake_breadth_fetchers_feed_the_real_pipeline` 擴斷言:至少一列
    `touched_limit_up is True and limit_up is False`。
- CLAUDE.md §1 `VERIFY_BREADTH_FAIL` 說明同步(R19)。
- `record_breadth_parity._SNAPSHOT_FIELDS` 補 `high`/`low`(不重錄)。

## 7. `frontend/src/types.ts` + `frontend/src/lib/constants.ts`(修)

- `BreadthRow` / `BreadthRowsState`(design §4 直譯;`market: "twse" | "tpex"`)。
- `LIMIT_LIST_OPEN_KEY = "copycat-limit-list-open"`、
  `LIMIT_LIST_FILTER_KEY = "copycat-limit-list-filter"`(review R6:constants.ts
  檔頭命名規則 `copycat-` kebab;key 出貨即進瀏覽器,不得事後改名)。

## 8. `frontend/src/hooks/useBreadthRows.ts`(新)+ `frontend/src/components/index/LimitListSection.tsx`(新)+ 各自 `.test`(新)

- **hook 抽離(review R10:server-state query 一律住 hooks/,useMarketBars 形狀)**:
  `useBreadthRows()` → `useQuery({ queryKey: ["breadth-rows"], queryFn: <hook 內
  小 fetch fn,useCapital fetchJson 同款>, refetchInterval: () =>
  (inTradingHours() ? 10_000 : false), retry: 1 })`
  (`inTradingHours` 自 `@/lib/trading-hours`)。hook 級紅測試:refetchInterval
  gate / 錯誤終態(frontend-testing 的 TanStack error 慣例)。
- LimitListSection:收合 = unmount(CorrSection 逐字慣例:lazy 不需要 —
  本元件無 WS、無重依賴,直 import;localStorage try/catch lazy init);
  展開子元件吃 `useBreadthRows()`。
- 篩選 state 單物件 `{twse, tpex, limitUp, limitDown, touched, minAmount,
  priceMin, priceMax}`,變更即寫 `LIMIT_LIST_FILTER_KEY`;篩選邏輯 OR 狀態 ×
  AND 門檻(design §5.2);狀態歸屬優先序 limit_up > limit_down > touched(R8)。
- 表格欄與文案 / 排序(null streak = -1)/ 空狀態(`as_of` 判別子,R18)/
  stale 膠囊 — design §5.2 逐字。列 onClick → `onOpenStock(stock_id)`。
- 元件級紅測試:design §6 前端節逐條(SC-3/SC-4 的 vitest 面)。
  frontend-testing 慣例:無 jest-dom,用 `toBeTruthy()/textContent` 斷言。

## 9. `frontend/src/components/index/IndexPage.tsx` + `frontend/src/App.tsx`(修)+ 測試(擴)

- `IndexPage` props 加 `onOpenStock?: (code: string) => void`;
  `<LimitListSection onOpenStock={onOpenStock} />` 插在 breadth section 與
  `<CorrSection />` 之間。
- `App.tsx`:`onOpenStock={(code) => { setStockCode(code); setTab("stock"); }}`。
- 紅測試:IndexPage 渲染順序;App 級點擊跳轉(SC-5:tab 切換 + StockPage 收到
  code;mock fetch 沿 App.test 既有 stub)。

## 10. 收尾同步

- `docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md` §5 Round 3
  勾記 open question 4 已拍板(FinMind EOD 回看)— 一行註記,不改結構。
- 側車樣板(review R8):SC-1 盤中驗證用的 breadth_side_server.py(scratchpad /
  evidence 樣板)以四元組重寫本輪版本,附在本輪 evidence/。
- gate:pytest / ruff / pyright / validate + npm test / tsc / eslint(frontend)。
