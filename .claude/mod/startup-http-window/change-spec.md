# change-spec:server 啟動期 HTTP 空窗根治(mod/startup-http-window)

分流判定:user 帶已成形改法(「把回補段移到背景 task + 重審 app.state 掛載順序」,
docs/next-time.md 2026-08-04 條已預錨定做法與風險面)→ grilling 確認模式,無 counter-proposal
(整段背景化比「只背景化 TXO 回補」乾淨:單一 code path、順序依賴原樣保留、測試面一次收)。
自主模式:各決策取建議解標 `[auto-default]`,無方向性未決項。

參照:`.claude/mod/startup-http-window/current-state.md`(Phase 1 現況表,以下引用 §N 皆指它)。

## 1. 決策記錄

- **D1 `[auto-default]` 整段 boot 序列搬進單一背景 task(保序,不並行)**:runtime.start
  + stock/signals/index/capital/futures/corr 六段 `_boot` + service/bot 掛載,原順序原樣
  搬入 `_boot_all()` 背景 task;lifespan 先掛 build + 未 started 的 runtime + 其餘
  placeholder(None)即 yield。不並行化各引擎 start(§2 依賴 1-5 + TC4 同 session 時序
  假設,並行是另一輪的事)。
- **D2 `[auto-default]` TXO runtime start 失敗語意改變(🔴)**:現況「lifespan 例外 →
  server 整台起不來」→ 改為「log exception + txo 面降級,其餘引擎照起」
  (= 補上 user 指出的「未包 _boot 隔離」)。不加自動重試(out of scope,見 §5)。
  [amendment 2026-08-05: R10 — 邊界寫準:(a) `EngineRuntime(...)` 與 `_default_source()`
  **建構**仍留 yield 前 = fail-fast(pyzmq 未裝 / ImportError 屬環境壞,該吵);D2 只隔離
  `start()` 的執行期失敗。(b) 部分失敗(activate 階段 ConnectionError)時 `_series` 已填、
  `_consume` 已跑 → `/api/txo/series` 可 200、self-heal 鏈仍會嘗試 —— log 文案用
  「txo 面降級」,不得斷言恆 NOT_READY。]
- **D3 `[auto-default]` 關機中斷 boot 的清理協定**:finally 先 cancel boot task 並 await,
  再依既有反序關「已掛載」引擎;`_boot` 樣板新增 CancelledError 分支(close 已建物件後
  re-raise)—— 現 `except Exception` 接不到 CancelledError,會洩漏已連線 session。
- **D4 `[auto-default]` 就緒可觀測 = 新 `/api/ready`**:回 `{"ready": bool, "error":
  str | null}`(boot task 正常結束即 true,含 D2 降級結束 —— 個別引擎好壞由既有 503
  語意表述;`error` 見 R3 amendment)。**不動 `/api/health`**:其 docstring 明文
  「刻意不含引擎健康度」,build 身分保持純粹。
  [amendment 2026-08-05: R8 — `boot_done = True` 只在**非 cancel** 結束路徑設
  (`except CancelledError: raise` 不設;用 try/except/else 結構),關機中的 server 不得
  宣告就緒,`wait_boot` 也不得被關機中 task 誤放行。]
- **D5 `[auto-default]` 測試遷移 = `BootedClient` + `wait_boot`**:tests/helpers 新增
  `wait_boot(app, timeout)`(輪詢 `app.state.boot_done`)與 `BootedClient(TestClient)`
  (`__enter__` 後自動 wait_boot;wait_boot 於 done 後檢查 boot_error,非 None 即 raise
  —— 讓 R3 的 fail-silent 在測試側變回 loud,r2: R16);既有 33 個 TestClient 站點機械替換、
  `test_ws_disconnect` 的 `_RunningServer.__enter__` 與舊式 inline uvicorn 治具補
  wait_boot。既有測試語意不變(等到就緒才斷言 = 原契約)。
- **D6 `[auto-default]` select 並發 guard(🔴)**:啟動窗開放後,`runtime.start` 已填
  `_series` 但初始 handover 未完的整段(prod = 分鐘級)裡,`/api/txo/series` 已回清單 →
  前端可 POST `/api/txo/select` → `activate()` 無 `_handover_running` 檢查 → 與 boot 中
  的 handover 並發共用 `_buffer`(engine.py:171-172 註解警告的正是這件事;現況靠
  「HTTP 面關著」偶然不可達,select-during-rollover 其實既有可達,同類修掉)。
  `activate` 進場先查 busy,busy → raise `HandoverBusyError` → route 轉 503。
  [amendment 2026-08-05: R2 — 只查 `_handover_running` 擋不住相鄰兩個 select:
  `activate` 在 `_run_handover` 設旗標**之前**有 `await asyncio.to_thread(unsubscribe)`
  讓出點(engine.py:158),A 停在那裡時 B 照樣通過。互斥升級為涵蓋**整個 activate**:
  進場(series lookup 後)同步 `if self._handover_running: raise HandoverBusyError`
  → 同步 `self._handover_running = True`(check 與 set 之間零 await,單執行緒 loop 即
  原子)→ 整段 try/finally 復位;`_run_handover` 內部的 set/reset 維持現狀(自 activate
  重入時已 True 無妨,兩層 finally 復位冪等)。self-heal 直呼 `_run_handover` 的路不經
  activate,其既有 :277 check 不動。engine 單元補「兩個 activate 並發,第二個 raise」
  (fake unsubscribe 阻塞即可,不需 HTTP)。]
  [amendment 2026-08-05: R12 — 錯誤碼不複用 NOT_READY(語意擴張:同碼多出「重試即成功」
  來源):改新碼 `HANDOVER_BUSY`(503,`{"detail":{"error":"HANDOVER_BUSY"}}` 契約形狀
  不變,本輪不動前端)。]
  [amendment 2026-08-05 r2: R21 — 前端行為查證更正:select 路**沒有**碼→文案對照
  (useSeries.ts:26 `parseError` 後原樣 throw,SeriesSelect.tsx:33 印
  `切換失敗:{error.message}`)→ 窗內誤按序列會看到「切換失敗:HANDOVER_BUSY」原始碼
  字串。列入 Phase 7 目視**預期**(非 bug);中文文案候選回寫 next-time,本輪不動前端。]
  [amendment 2026-08-05 r2: R22 — 巢狀 finally 復位的正確性依賴不變式「activate 在
  `_run_handover` 之後不得再 await」(內層 finally 清 False 後到外層 finally 間現況零
  讓出點,安全但脆;尾端日後補 await 會開出第三個 activate 溜進來的真窗且無測試會紅)。
  實作必須在 activate 的 finally 上方與 `_run_handover` docstring 各留一行註解寫明此
  不變式。]

## 2. 成功條件(可驗收)

- **SC-1(量化)**:fake TXO source 注入 12s 啟動延遲(沿用 next-time 量測法:scratchpad
  腳本,uvicorn thread + fake source,不碰 ZMQ),量 `t(uvicorn listen) → t(/api/health
  首次 200)`。**目標 < 1.0s**(現況 ≈ 12.6s);同腳本量 `/api/ready` 從 false 翻 true
  發生在 boot 完成後(≈12s+ε),窗內 `/api/txo/snapshot` 與 `/api/stock/watchlist` 回 503。
  Unit = 秒,量法 = 腳本內 `time.monotonic()` 差,證據落 verification.md。
  [amendment 2026-08-05: R5 — `/api/txo/state` 不存在(全 repo 僅本 spec 命中),窗內
  503 判準改用 `/api/txo/snapshot`(series_id None → 503 NOT_READY,app.py:552-558)。]
- **SC-2**:`pytest -q` 全綠(baseline 1720 + 新增);ruff / pyright / `copycat validate`
  全 PASS。
- **SC-3**:關機中斷 boot 不洩漏:boot 進行中 exit lifespan → 已建 source 的 `close()`
  被呼叫(新測試斷言 fake.closed)。
- **SC-4**:select busy guard:初始 handover 進行中 POST select → 503 `HANDOVER_BUSY`,
  handover 完後同請求 200(新測試)。[amendment 2026-08-05 r2: R14 — 碼名與 R12 對齊]
- **SC-5**:UI 面(畫面可指認):本輪不動前端;真環境重啟後啟動窗內前端各面板顯示
  **既有降級形狀**(TXO 頁「尚未就緒」、個股/指數面板空態)—— 此項在 prod 重啟驗證時
  目視,屬 Phase 7 盤後項。
  [amendment 2026-08-05: R11 — 「boot 完成後自癒」主張限縮:refetchInterval 自癒只有
  useStockNames 與 poll 類(capital 10s);窗內落 error 終態且**無** interval 的一次性
  query 至少四條(useSeries / useStockWatchlist / useSignalFeed today / useSignalsConfig
  enabled,皆 retry:1)→ 需視窗重聚焦或重載才回復。此非本輪退步(現況窗內連線被拒同樣
  落終態),列為已知限制,回寫 docs/next-time.md 既有條目(2026-08-04「啟動窗內其他
  REST query 的失敗終態未盤點」L618-621)。Phase 7 目視步驟**不得靠重新整理拿 PASS**:
  等 boot 完成後先觀察哪些面板自己回來、哪些要重載,照實記錄。]
  [amendment 2026-08-05: R7 — 窗內 `/api/capital/status` 回 200 `{"status":"disabled"}`
  (capital None 的既有語意 = 組態未啟用,非降級)→ operator 可能誤讀「群益設定掉了」;
  10s poll 自癒。列入 Phase 7 目視預期與 Known Risks,本輪不改 route(改 starting 語意
  屬 scope 外)。]
  [amendment 2026-08-05: R6 — 窗內 `/api/txo/contracts` 回 200 空列表(`orderable_symbols`
  只剩 SPOT,被 route 的 `TC.O.` 前綴過濾掉;reviewer 原稱「回假全鏈 [TXF]」經 grep 反證
  不成立,app.py:549)→ 前端 OrderPanel 對空列表已有 fallback 行為測試釘住
  (OrderPanel.test.tsx:248-263)。屬既有「空鏈日」形狀,非新狀態;caller map 已補列。]

## 3. 不能破壞的既有行為白名單

<!-- reviewer 對照節:行號範圍 L106-L124 -->
1. **引擎啟動順序與依賴**(current-state §2 條 1-5):watchlist_service 先於 signals;
   signals 需 stock 且 `attach_signal_hub` 是 `_start_signals` 最後一行(CC-2);index 的
   txf_getter 綁 runtime;capital 先 set_broadcast 再 start;corr 後於 futures。
2. **關機反序**:signals → corr → futures → capital → index → stock → runtime,各自
   try/except 續行(app.py:455-489)。
3. **`_boot` 降級契約**:make 回 None = 靜默跳過;start 失敗 = log + close 已建物件 +
   該引擎 None(503);不波及其他引擎。characterization:
   tests/server/test_stock_routes.py:59-99 兩條(含「壞自選檔 → 個股單獨降級」)。
4. **HTTP error contract**:`{"detail": {"error": code}}`;NOT_READY / CORR_NOT_READY /
   RIVER_NOT_READY 語意不變;`/api/health` 回應 shape 不變(純 build 身分)。
   [amendment 2026-08-05 r2: R14 — 本輪**新增**碼 `HANDOVER_BUSY`(503,僅
   /api/txo/select),既有三碼語意不動;前端無 select 碼→文案映射,原樣印碼(見 R21)。]
5. **`/api/stock/names` 不過 `_stock` 閘**(TC4 沒開也能搜尋)—— 窗內也必須 200。
6. **canonical 零寫早退 PUT**、signals 的 membership 種子時序(hub start 後從檔案重讀,
   窗內 PUT 與 hub 種子最終一致 —— current-state §4 尾段查證)。
7. **--verify 模式**行為(fake source、port 8722、env 壓制)照舊可用。
8. **banner 最先印**(引擎起不來也要印得出來,app.py:233-235)。
9. **rollover / self-heal 鏈**:`_maybe_self_heal` 的 `_handover_running` 重入 guard、
   rollover 天然補跑語意(engine.py:277-280)不動。
10. **同內容測試時序**:BootedClient 等待後,既有測試的斷言語意(「就緒後行為」)零改動
    —— 任何既有 assertion 都不因本輪改寫(鐵則 E;唯一例外見 §4 該紅清單)。

## 4. Backward compat / migration

- HTTP:`/api/ready` 純新增;其餘 API shape 不變。前端不動(unknown endpoint 不影響)。
- `create_app` signature 不變(caller = __main__ + 測試)。
- **對外可感知的行為改動只有兩條**:(a) D2 —— TXO source 壞時 server 起得來但 txo 面
  降級(log + /api/ready 可判);(b) D6 —— handover 進行中 select 回 503,**新錯誤碼
  字串 `HANDOVER_BUSY` 首次出現在 /api/txo/select 回應**(原本同時序是 buffer 互搶的
  未定義行為/連線被拒)[amendment 2026-08-05 r2: R14]。無資料 migration;可逆 =
  revert commit。

## 5. Out of scope

- runtime.start 失敗的自動重試 / self-heal 補鏈(失敗恆 NOT_READY 待重啟;要做是獨立輪,
  與 next-time「futures_engine 間歇零推播」條同族)。
- 各引擎 start 並行化(保序;並行另議)。
- 前端任何改動(user 指定此輪只動後端)。
- `_HANDOVER_RETRIES` / 回補本身的速度優化。
- prod 重啟真環境驗證(盤後;user 指示排程)。

---

# Phase 3:diff 級 spec

## 檔案 1:`copycat/server/engine.py`

- 🔴 **新增 `class HandoverBusyError(RuntimeError)`**(module level,docstring:交接進行
  中不可重入 activate;route 層轉 503)。
- 🔴 **`activate()` 進場 guard**:`series = self._series[series_id]`(KeyError → 400 優先
  順序保留)之後、任何 mutation(unsubscribe)之前:
  `if self._handover_running: raise HandoverBusyError(series_id)`。

## 檔案 2:`copycat/server/app.py`

- 🔵 **抽 `_boot_all`(先做,行為不變)**:lifespan 內 :245-452 的啟動序列(runtime.start
  至 corr 掛載)原樣搬進 lifespan 內的 `async def _boot_all() -> None`,lifespan 先
  `await _boot_all()` 再 yield(此 commit 仍同步,測試全綠不動)。搬遷時引擎 local 變數
  (stock/signals/bot/index/capital/futures/corr/service)改為集中在一個 lifespan scope 的
  可變 record(`booted: dict[str, Any]` 或小 dataclass),`_boot_all` 邊完成邊寫入
  `app.state.X` 與 record;finally 的反序 close 改讀 record(順序表不變)。
  `_close_signals` 等 closure 隨序列搬入 `_boot_all` 內,close callable 存進 record
  (`booted["signals_close"]`)供 finally 呼叫 —— nonlocal `bot` 的存取路徑就此消失。
- 🔴 **deferral 本體**:
  - lifespan yield 前:`app.state.build` + banner(不動)→ 建 `EngineRuntime` 並掛
    `app.state.runtime`(未 started;NOT_READY 語意由現有 route 承接,current-state §4)
    → 其餘 8 個 app.state 全掛 None placeholder(stock / watchlist_service / signal_hub /
    discord_bot / index / capital / futures / corr)→ `app.state.boot_done = False` +
    `app.state.boot_error = None` [amendment 2026-08-05 r2: R15 — boot_error 必須與
    boot_done 同點初始化,否則正常路徑 /api/ready 直取屬性 AttributeError → 被
    `_unhandled` 轉 502] → `boot_task = asyncio.create_task(_boot_all())` → yield。
  - `_boot_all` 內:`await runtime.start()` 包 try/except Exception → log exception
    (訊息:「TXO runtime 啟動失敗,txo 面降級(其餘引擎照起)」)不 re-raise(D2);
    **CancelledError 穿透**(關機路徑)。
    [amendment 2026-08-05: R3 — `_boot_all` **整體**另包頂層
    `except asyncio.CancelledError: raise` + `except Exception: logger.exception(
    "boot 序列非預期中止,後續引擎未啟動")` 並記 `app.state.boot_error = repr(exc)`
    (正常路徑 None)—— 背景化把「序列本體拋例外」從 fail-loud 變 fail-silent
    (WatchlistService 建構、state 指派等不在 `_boot` 傘內),沒有頂層 catch 時後續引擎
    全部靜默不啟動且 /api/ready 照樣 true。`/api/ready` 回 `{"ready", "error"}`。]
    [amendment 2026-08-05: R8 — 完成標記語意:`boot_done = True` 於 try/except 結構
    **之後**設(CancelledError re-raise 天然跳過;Exception 中止路徑已被 R3 頂層 catch
    吃掉後仍會走到 → done=true + error 非 null = 「boot 結束但不完整」)+ log boot
    總耗時(`time.monotonic()` 差)。關機中的 server 不得宣告就緒。]
  - finally(關機):`boot_task.cancel()`(若未 done)→ 取回 boot task 結果 → 既有反序
    close(讀 record;None = 未起,跳過)→ `await runtime.close()`(恆做,runtime 必存在)。
    [amendment 2026-08-05: R4 — 取回不得拋:`try: await boot_task
    except BaseException: logger.exception("boot task 以例外結束(關機續行)")`
    (或 gather(return_exceptions=True))。boot task 若以非 CancelledError 例外結束,
    裸 await 會在反序 close **之前**把例外重拋 → 六段 close + runtime.close 全跳過,
    TC4 session / COM 執行緒 / hub worker 一次全洩漏 —— 與白名單 2「各自 try/except
    續行」同精神,反序 close 必須無條件執行。]
- 🔴 **`_boot` 樣板加 CancelledError 分支**(D3):
  ```python
  except asyncio.CancelledError:
      if obj is not None:
          try:
              await close(obj)
          except BaseException:
              logger.exception("%s close 失敗(關機中斷 boot,忽略)", name)
      raise
  ```
  docstring 補一句(關機中斷 boot 時已建物件不得洩漏;close 內部多為 to_thread,
  執行緒工作不受 cancel 影響,會自然跑完)。
  [amendment 2026-08-05: R13 — 二次 cancel 下未受保護的 close 會半途中斷。]
  [amendment 2026-08-05 r2: R20 — **推翻 R13 的 shield 解**:已 cancel 的 task 內
  shield 收到第二次 cancel 時,外層 await 立即拋、內層 close task 變無人 await 的孤兒,
  lifespan finally 走完 loop 即關 → close 依然沒完成還多 `Task was destroyed` 警告;
  且各 close 內部是 `asyncio.to_thread`(engine.py:150),執行緒派出去後本就不受
  cancel 影響,shield 要防的「半途中斷」對這類 close 不成立。改 best-effort
  `await close(obj)` + `except BaseException` log(第二次 cancel 被 log 後 re-raise
  原 CancelledError);殘餘風險(純 async close 被二次 cancel 中斷)記 Known Risks。]
- 🔴 **select route**:`except HandoverBusyError` → `raise HTTPException(503,
  detail={"error": "HANDOVER_BUSY"})`(放在既有 KeyError→400 的 except 旁)
  [amendment 2026-08-05 r2: R14 — 碼名與 R12/SC-4/測試 5 對齊]。
- 🟢 **`/api/ready`**:
  ```python
  @app.get("/api/ready")
  async def ready(request: Request) -> dict:
      s = request.app.state
      return {
          "ready": bool(getattr(s, "boot_done", False)),
          "error": getattr(s, "boot_error", None),
      }
  ```
  docstring:readiness probe;true = boot 序列結束(個別引擎可能降級,由各 route 503
  表述;error 非 null = 序列未走完即中止);getattr default 防 lifespan 外請求。
  [amendment 2026-08-05 r2: R15 — 片段補 error 欄,與 D4/R3 一致]

## 檔案 3:`tests/helpers/boot.py`(新檔)

- 🟢 `wait_boot(app, timeout: float = 10.0, *, allow_error: bool = False)`:輪詢
  `getattr(app.state, "boot_done", False)`,`time.sleep(0.005)`,逾時 raise
  AssertionError(訊息含 timeout)。跨執行緒讀 bool(GIL 原子)。
  [amendment 2026-08-05 r2: R16 — done 之後檢查 `getattr(app.state, "boot_error",
  None)`:非 None 且未 `allow_error` → raise AssertionError(含 repr(error))。R3 把
  序列崩潰從 fail-loud 變 fail-silent,測試側等待器必須把它變回 loud,否則 33 個遷移
  站點在 boot 崩掉時只看到一片 503 照樣綠。測試 6 顯式傳 allow_error=True。]
- 🟢 `class BootedClient(TestClient)`:`__enter__` 呼叫 super 後 `wait_boot(self.app)`
  再回 self。
  [amendment 2026-08-05 r2: R23 — wait_boot 失敗時必須歸還資源:
  `try: wait_boot(...) except BaseException: super().__exit__(None, None, None); raise`
  —— 否則逾時的 client lifespan 永不關閉,portal 執行緒 + boot task 污染後續測試。]
  [amendment 2026-08-05: R9 — starlette `TestClient.app` 宣告型別是 `ASGIApp` 非
  `FastAPI`,直接傳 `wait_boot(self.app)` 會卡 pyright(SC-2 gate)。`BootedClient.
  __init__` 自存 `self._fastapi: FastAPI = app` 再傳,或 `cast("FastAPI", self.app)`;
  `wait_boot` 內一律 getattr default。]

## 檔案 4:測試機械遷移(9 檔,行為斷言零改動)

- `TestClient(` → `BootedClient(`:test_app / test_health / test_stock_routes /
  test_index_routes / test_corr_routes / test_river_routes / test_market_routes /
  test_capital_api / test_signal_routes(import 同步加)。
- `test_ws_disconnect.py`:`_RunningServer.__enter__` 在 `server.started` 後加
  `wait_boot(self.app)`(建構子存 app 引用);:140 舊式 inline uvicorn 治具同補;
  TestClient 站點(若有)同遷。
- **該紅測試:無**(既有測試在 BootedClient 下語意不變)。唯一 assertion 調整候選:無。
  若實作中發現某測試依賴「lifespan 例外 → TestClient enter 直接炸」(D2 改動面),逐條
  對照本 spec 處置 —— grep `runtime.start` 失敗類測試現況:test_stock_routes 兩條
  characterization 針對 stock `_boot`(非 runtime),不受 D2 影響。

## 檔案 5:新測試 `tests/server/test_boot_window.py`(新檔,全 🟢/🔴 紅先行)

fake:`BlockingTxoSource(FakeTxoSource)` —— `list_series` 阻塞在 `threading.Event`
(gate),`close()` 記 flag。

1. 🔴(deferral 的紅測試)`test_lifespan_yields_before_boot_completes`:gate 未放行,
   `with TestClient(app)`(裸 TestClient,刻意不等)進場應**立即返回**(< 2s);窗內
   `/api/health` 200、`/api/ready` false、`/api/txo/series` 503、`/api/stock/watchlist`
   503;放行 gate → `wait_boot` → `/api/ready` true、`/api/txo/snapshot` 200
   [amendment 2026-08-05: R5 — route 改 snapshot]。**exit 前必先放行 gate**(R1,見下)。
2. 🟢 `test_shutdown_during_boot_closes_started`(SC-3):fake 帶 `entered`
   Event(進入阻塞點即 set)→ 測試先 `entered.wait(2)` 確認 boot 真的卡在該段 →
   `threading.Timer(0.2, gate.set).start()` → exit context → 斷言 fake TXO source
   `closed`(runtime.close 恆做)+ **`app.state.boot_done is False`**(R8:cancel 路徑
   不設 —— 這是「boot 真被中斷」的鑑別證據)+ placeholder 全 None。
   [amendment 2026-08-05: R1 — 原步驟「exit 後才放行」會卡死:阻塞點跑在
   `asyncio.to_thread` 的 loop 預設 executor,`TestClient.__exit__` → anyio Runner.close
   → `loop.shutdown_default_executor()`(3.13 THREAD_JOIN_TIMEOUT=300s)join 執行緒,
   單執行緒測試永遠走不到放行行。`boot_task.cancel()` 只讓 asyncio 側返回,執行緒不受
   影響。測試 3 同款修正。]
   [amendment 2026-08-05 r2: R17 — 補 `entered` 同步點與鑑別斷言:沒有 entered.wait 時
   exit 可能發生在 boot 一行都沒跑(create_task 只是排程)或已跑完(Timer 先放行)——
   後者走正常反序 close,`fake.closed` 恆 True,測試綠但中斷路徑一次都沒執行。]
3. 🟢 `test_boot_cancel_closes_inflight_engine`(`_boot` CancelledError 分支):TXO fast,
   stock source 的 `set_trade_date` 阻塞(entered Event + Timer 放行,同測試 2 協定)→
   `entered.wait(2)` 確認 boot 卡在 stock 段 → exit → 斷言 `fake.closed is True` **且**
   `app.state.stock is None`(= 該引擎從未掛載,close 只可能來自 CancelledError 分支,
   非正常反序)[amendment 2026-08-05 r2: R17 — 鑑別斷言,防 vacuous]。
4. 🟢 `test_runtime_start_failure_degrades_not_crash`(D2):TXO source `list_series`
   raise → enter 不炸、wait_boot 後 `/api/ready` ready=true(error null;D2 是受控降級
   非序列中止)、`/api/txo/series` 503、**其餘引擎照起**(帶 stock fake,
   `/api/stock/watchlist` 200)。
5. 🔴(D6 紅測試)`test_select_during_handover_returns_503`:`fetch_backfill` 阻塞的
   fake → 窗內(series 已列出)POST `/api/txo/select` → 503 `HANDOVER_BUSY` → 測試
   執行緒**直接 `gate.set()`** → wait_boot → 同請求 200。engine 層另補兩條單元:
   (a) `_handover_running` True 時 `activate` raise `HandoverBusyError`;(b) **兩個
   activate 並發,第二個 raise**(fake unsubscribe 阻塞重現 R2 的讓出點,不需 HTTP)。
   [amendment 2026-08-05 r2: R18 — 本測試**不用** Timer:測試執行緒在兩次 POST 之間
   自由,預先 arm 0.2s Timer 反而在慢機器上讓第一次 POST 晚於放行 → 拿 200 假紅。
   R1 的 Timer 協定只適用「放行時機必須落在 `__exit__` 阻塞期間」的測試(2/3)。]
6. 🟢 `test_boot_sequence_exception_surfaces_error`(R3):以 monkeypatch 讓 `_boot` 傘
   外一步拋(例:WatchlistService 建構 raise)→ wait_boot 後 `/api/ready` 回
   `{"ready": true, "error": <非 null>}`(boot 結束但不完整;斷言 error 有值 + 不炸
   lifespan;後續引擎未啟動 = index None → 503)。

## Commit 切分(🔵 → 🔴 → 🟢)

1. 🔵 `refactor(backend): lifespan 啟動序列抽 _boot_all + booted record(仍同步 await)`
   — 測試不動全綠。
2. 🔴 `fix(backend): 啟動序列移背景 task,HTTP 面即開(含關機中斷清理、D2 降級、測試
   BootedClient 遷移)` — 紅測試 = test_boot_window 1/2/3/4/6(先紅後綠,依 repo TDD
   tag 慣例拆 🟢 test [red] / 🔴 fix [green] 兩 commit)。
3. 🔴 `fix(backend): activate 交接重入 guard(select during handover → 503)` — 紅測試
   = test_boot_window 5 + engine 單元兩條。
4. 🟢 `feat(backend): /api/ready readiness probe` — 紅測試先行。

[amendment 2026-08-05 r2(排序協調):/api/ready 排最後、但 deferral 的紅測試(測試 1/
4/6)引用它 → **🔴 commit 內的窗態/結束態斷言一律走 `app.state.boot_done` /
`app.state.boot_error` 直讀**(TestClient.app 經 cast),`/api/ready` 的 HTTP 面斷言
(false→true、error 欄)集中放 commit 4 的 🟢 紅測試(沿用 BlockingTxoSource 重驗一條
窗內 false)。如此 🔵→🔴→🟢 順序不變且無前向依賴。]

## Known Risks

- `asyncio.to_thread` 不可中斷:關機中斷 boot 時,卡在 `list_series` / `fetch_backfill`
  的執行緒會活到該 to_thread 呼叫自然結束才退。[amendment 2026-08-05: R1 — 敘述更正:
  to_thread 執行緒是 **non-daemon**(3.9+)且 concurrent.futures 有 atexit join,
  關機/退出**會** join 它。][amendment 2026-08-05 r2: R19 — 上限寫準:單發 REQ ≤
  `_REQ_TIMEOUT_MS` 10s;`fetch_backfill` 是全鏈多 REQ 迴圈(~280 檔 sub + 多輪收割),
  prod 量級**分鐘級** —— boot 中途 Ctrl-C 可能要等回補收割跑完才退出。]
  與現況(整段 await 完才能關機)相比是嚴格改善,接受。
- 純 async close 在二次 cancel 下可能半途中斷(R20 決議的殘餘面):現役 close 的重活都
  在 to_thread(不受 cancel 影響),接受不 shield;新增純 async close 的引擎時重估。
- 窗內 WS 連上即 close(引擎 None):前端既有 reconnect 迴圈承接;與「引擎降級日」同
  形狀,非新狀態。
- 窗內 `/api/capital/status` 回 `{"status":"disabled"}`(R7):組態語意誤讀窗,10s poll
  自癒,接受不改。
- 窗內一次性 query 落 error 終態需重載(R11):既有 next-time 條目追蹤,本輪不動前端。
self_review_head: ea4a106330fac9a2ffd6da0f9109171735823645
