# R4 類股強弱 + 訊號事件流 Implementation Plan(condensed)

> **For agentic workers:** 依 task 逐個實作;執行模式由 feat.md Phase 3 /
> `refs/feat-phase3.md` 決定。每 task TDD 紅先行(`[red]`/`[green]` tag,
> 判準見 feat.md Phase 3 步驟 2)。design.md 章節引用 = 唯一機制真相源,
> 本檔只給落點與測試清單。

**Goal:** 台股綜合 tab 補上類股強弱面板與訊號事件流(全市場鎖板/開板事件入
signal_hub 單一匯流排)。

**Architecture:** design.md v3(§1 資料流圖)。後端:chain 取數(7 天 cache、
獨立 task)→ `sector_rotation` 純函式 → engine 掛點 + REST;breadth rows diff
(last_emitted 對帳制)→ hub `publish_market_events` → jsonl/WS。前端:兩個
收合區塊 + feed 層 market 過濾。

**Tech Stack:** Python 3.13 stdlib(server extras fastapi)/ pytest;React 19 +
TS strict + TanStack Query / vitest。

## Global Constraints

- 寫 .py 前讀 `backend-conventions`;FinMind 照 `finmind-conventions`;寫
  frontend 前讀 `frontend-conventions` + `frontend-testing`(brainstorm §6)。
- 三類 commit 分離 + TDD tag(feat.md Phase 3 步驟 2 判準)。
- 事件 kind 字串:`market_limit_lock` / `market_limit_open`;id 文法
  `{trade_date}-breadth-{code}-{kind}-{direction}-{as_of}`(design §7)。
- 毫元整數:事件 `price = round(close * 1000)`。
- 驗證指令不接 `| tail`;mutation 驗證 sleep 1 防同秒 pycache。

---

### Task 1:sector_rotation 純函式(SC-1)

**Files:** Create `copycat/sector_rotation.py`、`tests/test_sector_rotation.py`
**Produces:** `ChainMap`、`rows_to_chain_map(rows)`、
`compute_sector_rotation(universe_rows, chain_map)`、
`compute_sector_members(universe_rows, chain_map, name_map, industry, sub_industry=None)`
(簽名與輸出 shape:design §3)。

- 紅:neigui `test_market_today.py:239-360` 八案等價搬(hand-calc/排序/去重/
  null 排除/vol_ratio 兩案/零成員 skip/空 universe)+ `rows_to_chain_map` 案
  (正常 parse / **缺 sub_industry 整列丟(R4)** / 同 (industry,sub) 內 sid 去重)
  + members 案(known/unknown/sub 指定/**change_rate None 排最後/vol_ratio
  缺欄與分母 0 → None** — 等價搬 neigui `test_market_today.py:407-447`,R11)。
- 綠:忠實搬 neigui `market_today.py:242-312/:425-470` + `industry_chain.py:114-128`,
  docstring 記「邏輯全等、實作適配」與來源行號(market_breadth.py 檔頭慣例)。

### Task 2:chain_store(SC-2)

**Files:** Create `copycat/server/chain_store.py`、`tests/server/test_chain_store.py`
(R7:tests/server/ 為準,design §2 已對齊)
**Produces:** `load_chain(path) -> tuple[list[dict], float] | None`、
`save_chain(path, rows, fetched_at)`(design §4.2)。

- 紅:roundtrip / 檔缺 None / `_version` 不符 None / 壞 JSON None / rows 非 list
  None / 原子寫(tmp 不殘留)。
- 綠:`{"_version":1,"fetched_at",rows}`,tmp + `os.replace`(breadth_engine
  `_save` 同款);fetched_at epoch。

### Task 3:fetch_industry_chain + config 鍵(SC-2)

**Files:** Modify `copycat/server/breadth_fetch.py`、`copycat/breadth_config.py`;
tests:`tests/server/test_breadth_fetch.py` + `tests/test_breadth_config.py`(R7)。
**Produces:** `fetch_industry_chain(token) -> list[dict]`;`BreadthConfig` 新鍵
`event_cooldown_secs: float = 600.0`、`chain_ttl_hours: float = 168.0`。

- 紅:chain fetch 成功 / 402 → `BreadthFetchError(quota=True)` / rows < 1000
  warning(既有 dataset 測試 pattern 照搬);config 兩鍵預設值 + json 覆寫 +
  未知鍵 raise(既有案擴充)。
- 綠:`dataset=TaiwanStockIndustryChain` 無其他參數,沿 `_get_rows` 慣例。

### Task 4:market_breadth.limit_judged(SC-5 前置)

**Files:** Modify `copycat/market_breadth.py`(`compute_breadth` rows_out)、
`tests/test_market_breadth.py`
**Produces:** rows_out 新鍵 `"limit_judged": bool`(design §6.1)。

- 紅:prev_close 可判 → True;close None / change_price None / prev_close ≤ 0
  → False(三態);parity 測試不動(oracle 不比逐鍵 — R2-2)。
- 綠:一行布林,與 limit 判定同一條件式。

### Task 5:hub 新入口(SC-6)

**Files:** Modify `copycat/server/signal_hub.py`;tests
`tests/server/test_signal_hub.py`(R7)。
**Produces:** `publish_market_events(events, *, trade_date)`、
`market_event_state(trade_date) -> tuple[dict[tuple[str,str],bool], dict[tuple[str,str,str],int]]`、
`today_signals()` 聯集讀、`_kind_text` 兩案(全文:design §7)。

- 紅:(a) 發兩則 → `_publish` 收到 payload(id 文法斷言)、jsonl 佇列 2、
  Discord 佇列 0;(b) `_closing` 零入列;(c) trade_date 與 `_trade_date_fn()`
  不符 → warning 一次 + 落傳入值檔;(d) `market_event_state` 回放
  lock→open → `(("2330","up") -> False, 計數 {lock:1, open:1})`;檔缺 → `({}, {})`;
  (e) `today_signals` 兩日別檔聯集(**日期字串升冪串接** — 舊日在前,R9)+
  id 去重 + **同日回歸案:兩 fn 同日 → 只讀一次檔、輸出與既有行為逐字同**(R9);
  (f) `_kind_text` market 兩案文案;(g) **never-raise 紅案:注入會拋的
  `publish` callback → 不外拋、後續則照發**(R4)。
- 綠:design §7 逐條。高風險面(共用 hub):簽名照 design 全文,
  不得動 `_emit`/`_enqueue` 既有語意。

### Task 6:engine — chain 刷新 + rotation 掛點(SC-2/SC-4)

**Files:** Modify `copycat/server/breadth_engine.py`;tests
`tests/server/test_breadth_engine.py`(R7)。
**Consumes:** Task 1 純函式、Task 2 store、Task 3 fetcher/config。
**Produces:** ctor `chain_fetch` 參數 + 六個初始化欄位(design §4.3)、
`_maybe_arm_chain()` 獨立 task、`sector_state()`、`sector_members(industry, sub)`。

- 紅:(a) start 時 load_chain 進 `_chain_map`(過期也用);(b) TTL 過期武裝
  task,成功換表 + save;失敗沿舊表 + 60s 退避;quota → quota_backoff;
  **fetch 成功但 parse 後為空 → 不換表、不落檔、rotation 仍有值**(R6);
  (c) poll loop 不因 chain fetch hang 而阻塞(fake sleep fetch + 斷言家數輪照跑);
  (d) 首輪未成 `sector_state()` → rotation None;(e) `_apply` 成功後
  rotation/universe_rows 更新;(f) `sector_members` known/unknown。
- 綠:design §4.3/§5;task 形狀鏡射 streak(close() cancel)。

### Task 7:engine — diff 事件源(SC-5)

**Files:** Modify `copycat/server/breadth_engine.py`(續)+ 同測試檔。
**Consumes:** Task 4 `limit_judged`、Task 5 hub 入口。
**Produces:** `attach_signal_hub(hub)` / `detach_signal_hub()`、
`_diff_limit_events(trade_date, rows_out, as_of)`(機制全文:design §6)。
**呼叫點傳 `breadth["rows"]`(= `self.rows`,compute_breadth 輸出),不是
`_apply` 的入參 `rows`(原始快照,無 limit 欄)— R2。**

- 紅(SC-5 驗收案全列):(a) lock→open→relock 三轉移三則,每則
  (kind, code, direction, time, touch_count) 正確(**id 文法歸 Task 5 hub 層;
  另加一條真 SignalHub(fake publish + tmp data_dir)接 engine 的整合案保
  端到端 id 證據** — R5);(b) 開盤首輪已鎖檔發 lock(seed 空);(c) 盤中重啟
  seed 回放 → 已發布不重發、停機期轉移補發;(d) 冷卻內抖動 → 冷卻結束補對帳,
  終態收斂;對向桶不互吃;(e) `limit_judged=False` 列跳過(缺欄輪零假事件);
  (f) hub None 早退零推進(R2-1);(g) `_append` None 輪(域外/他日)不觸發;
  (h) 換日 re-seed;(i) **餵只有原始快照欄位的列 → 0 則且 log 有可辨識
  warning**(R2);(j) **單列壞值(close 為字串)→ 只丟該筆、同輪其他檔照發、
  poll 不死**(R4)。
- 綠:design §6.2-6.4 虛擬碼;`code = row["stock_id"]`;逐筆 try/except + 批次傘。

### Task 8:app 接線 + verify(SC-3/SC-6/SC-7 取證面)

**Files:** Modify `copycat/server/app.py`、`copycat/server/verify.py`;tests
既有 route/verify 測試檔擴充。
**Consumes:** Task 6/7 engine 面、Task 5 hub。
**Produces:** `GET /api/market/sector`(三態)、`GET /api/market/sector/members`
(industry 缺席 422 / 空字串或查無 404 SECTOR_NOT_FOUND / sub 空字串當未指定)、
`/api/stock/signals/today?market=exclude`、fetchers 五元組、attach/detach 接線。

- 紅:route 三態(引擎 None loading / boot 完成 rotation null / 正常)+ members
  三語意 + today `?market=exclude` 過濾 + 五元組長度 guard(注入點三處跟進:
  `tests/server/test_breadth_routes.py` / `test_verify.py` / `test_main_wiring.py`
  — R7)+ attach 在 boot 成功後、detach 在 close 前(接線測試沿
  `_start_signals` 慣例)+ **flip 紅案:monkeypatch 牆鐘 → 1101 的 limit_up
  兩態**(R3)。
- 綠:design §5/§8;verify.py fake 五元組(chain fake 固定小表涵蓋 fake 股票)、
  `VERIFY_BREADTH_FLIP=1` 翻轉 1101 — **依牆鐘 `datetime.now().minute // 11`
  奇偶(不是 clamp 後的 snapshot stamp 分鐘;週期 11 分 > 冷卻 600s,每次翻轉
  必發事件,R3)**、`VERIFY_BREADTH_FAIL` 涵蓋 chain(data_dir 無 chain 檔前置);
  `tests/server/test_verify.py` 形狀斷言跟進。

### Task 9:前端 — signal 模型與過濾(SC-8)

**Files:** Modify `frontend/src/lib/signal-model.ts`、
`frontend/src/hooks/useSignalFeed.ts`、`frontend/src/hooks/useSignalAlerts.ts`、
`frontend/src/components/stock/StockPage.tsx`;對應 `.test.ts(x)`。
**Produces:** `SignalKind` + `"market_limit_lock" | "market_limit_open"`、
`isMarketKind(kind: string): boolean`、`kindLabel` market 兩案(依 direction:
「全市場鎖漲停/鎖跌停」「全市場漲停/跌停打開」,與後端 `_kind_text` 對齊)、
`useSignalFeed(opts?: { market?: "include" | "exclude" })`(design §9.3:exclude =
baseline `?market=exclude` + live 過濾;include = 分族各 cap 200 合併)。
**queryKey 帶模式 `["stock-signals-today", market]`,`onWsOpen` invalidate 用
prefix key(R1 — P0):exclude 與 include 兩掛載點各自 cache,不得共用固定 key。**

- 紅:isMarketKind 三案;kindLabel 字串;feed exclude(250 market + 3 自選 →
  3 則)、include 分族(切族斷言);**同一 QueryClient 同時 render exclude +
  include 兩消費端 → 兩次 fetch、URL 各為 `?market=exclude` 與無參數、內容
  不同**(R1);alerts 早退(market → toast 不變、beep 未呼叫);
  StockPage rail 無 market 列。
- 綠:過濾在 `mergeSignals` 之前;alerts handler 開頭早退。

### Task 10:前端 — SectorSection(SC-3)

**Files:** Create `frontend/src/components/index/SectorSection.tsx`、
`frontend/src/lib/sector-model.ts` + tests;Modify `frontend/src/lib/constants.ts`
(`SECTOR_OPEN_KEY = "copycat-sector-open"`)、
`frontend/src/components/index/IndexPage.tsx`(掛載,`LimitListSection` 之後)。
**Consumes:** Task 8 routes。
**Produces:** `SectorSection({ active, onOpenStock })`;sector-model:
`SectorRotation` 型別族 + `fetchSectorState` / `fetchSectorMembers`。

- 紅:收合 persist(open key 讀寫)/ 展開後產業列(名 + members + 著色漲跌 +
  量比)/ 點產業展開 subs / 成員列點擊 `onOpenStock` / rotation null → 「類股
  資料未就緒」/ stale 標記 / 輪詢 gate = `open && active && inTradingHours()`
  (與 `useBreadthRows` 同式,R8 — 盤後停輪詢,紅案標明)。
- 綠:design §9.1;`LimitListSection` pattern(收合 = unmount、try/catch
  localStorage);成員 lazy query 只在鑽取時帶 `sub`(空字串不送)。

### Task 11:前端 — SignalTimelineSection(SC-7)

**Files:** Create `frontend/src/components/index/SignalTimelineSection.tsx` + test;
Modify `constants.ts`(`SIGNAL_TIMELINE_OPEN_KEY = "copycat-signal-timeline-open"`)、
`IndexPage.tsx`(掛載)。
**Consumes:** Task 9 feed include 模式。
**Produces:** `SignalTimelineSection({ onOpenStock })`(無 `active` prop — 資料
是一次性 query + WS bus,無輪詢可 gate,R8)。

- 紅:收合 persist / 時間倒序列(時刻 + 代號名稱 + kindLabel 文案)/ market 列
  「廣度」badge(title 註記精度)/ kind chips 過濾(含「自選 250 market 擠壓」
  分族案)/ 列點擊 `onOpenStock` / 自選 + market 同軸案。
- 綠:design §9.2;`useSignalFeed({ market: "include" })`。

### Task 12:文件同步(Phase 3 尾)

**Files:** Modify `CLAUDE.md`(結構樹 breadth_engine/新檔一行 + FinMind dataset
補記)、總 spec §5 R4(「industry override 表」記載更正 + 拍板回寫)、
`docs/next-time.md`(「觸及未鎖事件」候選)。🟢 chore commit,不掛 TDD tag。

### Task 13:窗限取證工具(R10;非 TDD,scratchpad + evidence)

沿 R2/R3 側車樣板(`breadth_side_server.py`)升級:五元組真取數(含 chain)+
`/api/market/sector` 曝露;另備兩端對照腳本(curl neigui
`/api/market/snapshot?refresh=true` 與 copycat sector state 各落檔、比 industries
序列與逐業 avg_change_rate ≤ 0.01pp — design §5 量法)。產物放 scratchpad,
evidence 落 `.claude/feat/market-overview-r4-sector-signals/evidence/`。
**排程:必須在 Phase 6 盤中窗(下一交易日 09:01–13:30)之前備妥。**

---

**依賴序**:1/2/3/4 可並行 → 5 → 6/7(7 依 4+5)→ 8;前端 9 → 10/11 並行
(10/11 依 8 的契約,可先 fixture 並行);12 收尾;13 於 Phase 6 前備妥。
