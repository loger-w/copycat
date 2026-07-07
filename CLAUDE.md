# copycat(前 trash-mr-warrant)— 達錢 4 看盤工具 + 分點行為指紋辨識

User-global `~/.claude/CLAUDE.md` 的鐵則(觀察優先 / Scope / 測試 / 證據 / 禁止繞過 / 3 次上限 / Sub-agent)一律繼承,不在這裡重述。本檔只放「讀 code 看不出來」的專案級事實。

---

## 0. 目的 & 結構

- **DQ4 = Touchance 4.0**(達錢 4,艾揚資訊獨立平台,**非任何券商產品**)。命名容易跟 DQ2 國際贏家(SYSTEX)、XQ 全球贏家(SysJust)混淆 — 三家不同公司不同產品,溝通時一定要附 Touchance 全名。
- 身份釐清詳細報告:`docs/research/2026-06-26-dq4-and-broker-api-survey.md`。
- 做達錢 4 / Touchance 4.0 **期貨 + 選擇權 + 權證** 即時看盤 / 監控工具,**以及**分點(broker branch)盤中行為指紋辨識(2026-07-06 新增,見 §0a)。Scope 分 phase 推進:
  - **Phase 1(現在)= 期貨 + 選擇權即時看盤**。主資料源 = **Touchance** push tick + **FinMind** 補期貨 / 選擇權 chip。
  - **Phase 2 = 權證監控延伸**(待 Touchance 個股 / 權證涵蓋驗證)。
  - **Phase 3+ = 下單**(若擴展)。先過 §7 規範。
- Read-only 看盤,直到 §7 路徑明確開啟。
- **個股 + 族群「純看盤」即時監控不在這個專案** — 那塊 use case 純 FinMind 一條線就完成且不要 Windows + Touchance 常駐,**回到 neigui(前 trash-cmoney)擴展**(2026-06-26 第三次釐清後分離)。
  - **例外(2026-07-06)**:分點盤中行為指紋辨識(鎖漲停攻擊手法 / 鎖板品質評分 / T+1 出貨劇本判別,見 §0a)**不受此排除限制**——排除理由是「純 FinMind 就做得到,不需要 Windows + Touchance 常駐」,但這塊工作的核心訊號(每分鐘內外盤張數、逐筆 Bid/Ask、鎖板前後量能結構)**FinMind 完全沒有**,必須靠 Touchance tick / 1K 才拿得到,原排除理由在此不成立,因此留在 copycat。
- 「Mr Warrant」= 權證小哥 reference,場景偏 **權證 + 選擇權 trader workflow**(純現貨個股 / 族群監控不在此 scope,在 neigui;分點行為指紋辨識例外,見上)。
- 目錄結構待專案啟動後填(預期跟 neigui 同樣 backend/ + frontend/ 分離,但不強制)。

### 0a. 分點行為指紋辨識(2026-07-06 新增能力)

- **緣起**:`neigui` 專案(前 trash-cmoney)的 broker-signature-explorer spec 用 FinMind 日線資料驗證圈內分點 intel,後續用 Touchance tick / 1K 做盤中微結構驗證,發現**身分判定精度天花板只有 2–2.8x lift**,但**鎖板品質(時機 / 自然度 / 排隊消耗)+ T+1 開盤前 6 分鐘微結構**這些不需要知道身分的訊號效果量遠大於猜身分 —— 這是本能力的核心設計原則。
- **規格文件**:`docs/strategy.md`(完整策略邏輯:Phase 1 縮池 / Phase 2 鎖板品質評分 / Phase 3 T+1 決策,含期望值表、已知限制)。
- **佐證資料**:`docs/evidence/`(EDA、GA 規則搜索天花板驗證、TC4 tick playbook 等 5 份報告 + 2 份事件明細 CSV)。
- **TC4 連線元件**:`spikes/TCPY/tcoreapi_mq.py` —— 2026-07-06 修過 KeepAlive 執行緒生命週期 bug(一次性腳本收工前必須呼叫新增的 `Disconnect()`,否則 process 不會退出),細節見 `docs/research/2026-07-06-tc4-stock-tick-1k-api-report.md` §11。
- **這塊能力是通用框架,不是「優式偵測器」**:`strategy.md` 裡驗證的「五虎」只是 user 圈內 intel 提供的其中一個候選分點集合(非公開媒體 corroborate,機率性 roster,非每次都同一組),**不是專案本身要綁定的身份**。分點集合應做成可替換的輸入(watchlist),不要 hardcode 特定分點名稱到偵測邏輯裡 —— 之後可能驗證完全不同的分點集合。
- **目前階段(2026-07-07)**:策略調整與回測基建期,尚未落地盤中;終局 = 盤中輔助手動下單。第一個交付物 = 評分引擎 + 歷史 replay(Phase 2 鎖板品質 + Phase 3 T+1 開盤訊號,事件驅動、無 lookahead、身分無關),策略門檻全部收在版本化 strategy config,調策略 = 改 config 重跑對照,不動引擎。設計 spec:`docs/superpowers/specs/2026-07-07-broker-fingerprint-replay-design.md`。種子資料 = neigui `backend/data/research/five-tigers/`(1.24 GB,本機不納版控)。**硬限制:五檔委買賣深度不可得**(TC4 tick 僅成交當下一檔 Bid/Ask),依賴掛牆厚度的策略假設不可回測。

```
copycat/                  # Python 3.13 package(stdlib-only runtime;pytest/ruff/pyright dev)
├── data/                 #   models(Bar1K/台北分鐘索引)、store(1K atomic JSON)、
│                         #   daily(adv20/一價到底/連板)、import_neigui(種子匯入)
├── engine/               #   lock_quality(LockTracker)、t1_open(T1Tracker)— 零 IO 狀態機
├── replay/               #   runner / report(summary.md)/ validate(golden gate)/ compare
├── backtest/             #   T 日跟多隔日沖 GA 回測(2026-07-07):config(BacktestConfig 版本化)、
│                         #   universe(LOCKABLE_GROUPS/權重)、features(neigui 同源 19 欄 + 位階族)、
│                         #   simulate(悲觀成交/鎖死凍結)、search(GA/凍結規則)、stats(三道驗證)、
│                         #   pipeline(features/search CLI 入口,outcome cache 三重失效)、report
├── market.py             #   台股 tick 表 + 漲停價(毫元整數運算)
├── strategy_config.py    #   全部策略門檻(版本化,configs/*.json 覆寫)
├── watchlist.py          #   可替換分點集合(watchlists/*.json)
└── cli.py                #   python -m copycat <import-neigui|replay|validate|compare|backfill-daily|tday-features|tday-search>
data/(git-ignored)       # 匯入產物;out/(git-ignored)= replay 產物
docs/superpowers/         # spec 與 implementation plan
```

---

## 1. 啟動 & 驗證(覆寫 `auto-verify` 預設)

| 用途 | 指令 | 工作目錄 |
|------|------|---------|
| 測試 | `.venv\Scripts\python -m pytest -q` | repo root |
| Lint | `.venv\Scripts\python -m ruff check copycat tests` | repo root |
| 型別 | `.venv\Scripts\python -m pyright` | repo root |
| 種子匯入(一次性) | `.venv\Scripts\python -m copycat import-neigui --src C:\side-project\neigui\backend\data\research\five-tigers` | repo root |
| Replay | `.venv\Scripts\python -m copycat replay --watchlist watchlists/four_tigers.json` | repo root |
| Golden 驗證 gate | `.venv\Scripts\python -m copycat validate` | repo root |
| Config 實驗對照 | `.venv\Scripts\python -m copycat compare out/A out/B` | repo root |
| 日線回補(位階特徵前置,一次性) | `.venv\Scripts\python -m copycat backfill-daily` | repo root |
| T 日跟多回測:特徵 | `.venv\Scripts\python -m copycat tday-features` | repo root |
| T 日跟多回測:搜索+報告 | `.venv\Scripts\python -m copycat tday-search --report-date <YYYY-MM-DD>`(報告 → docs/evidence/) | repo root |

完成前要過的 gate:`pytest -q` + `ruff check` + `pyright` + `copycat validate` 全 PASS(validate 需先跑過 four/five 兩份 replay)。venv = Python 3.13(`py -3.13 -m venv .venv`;`py` launcher 預設 3.14,別直接用)。目前無 frontend。

**部署前置(Touchance 特性)**:

Touchance 4.0 是 **Windows 桌面 app**,Python client 透過 **ZMQ**(Quote port 51171 / Trade port 51141)跟它通訊。意味著:

- 後端 host 必須是 **Windows + Touchance 常駐開啟 + ZMQ ports 對 localhost 通**。
- 不是 headless Linux server 友善,**Docker 化困難**(要先驗證跨 host ZMQ 是否可用)。
- 預期實作初期都在本機跑(Touchance + FastAPI backend + React frontend 同台 Windows);若要拆出,先確認 ZMQ 跨網段穩定度。
- 這個 repo 一啟動就被 Windows 綁住(scope 純 Touchance),Linux Docker 不在規劃內。

`.env` 需要的 secret:
- `FINMIND_TOKEN`(沿用 trash-cmoney,補期貨 / 選擇權 chip 用)
- `FRONTEND_ORIGIN`(CORS)
- Touchance 訂閱授權碼 / 帳號 — 實裝時補確切變數名

---

## 2. Python 風格(專案特化)

只列非顯而易見、跨檔一致的:

- **`from __future__ import annotations` 強制**寫在每個 `.py` 第一行(註解後)。
- Type hints **無例外**:函式參數 + 回傳、module-level globals。`dict | None` / `list[dict]` 風格,不要 `Optional` / `List`。
- **Logging**:`logger = logging.getLogger(__name__)`,**禁止** `print`。
- **FastAPI error contract**(若採 FastAPI 後端):`raise HTTPException(status_code=..., detail={"error": "<code>"})` — frontend 依賴 `detail.error` 字串解析。新 endpoint 不要塞自由文字。
  - 502 = upstream 故障;503 = 服務尚未就緒;400 = 用戶錯;404 = 找不到。
- **全域 exception handler**(從第一天就開):`@app.exception_handler` 在 `main.py`,route 內**只 raise 不 catch**。避免 trash-cmoney `routes/options.py` 6 處重複 try/except 的債。
- **外部 IO 慣例**(類比 trash-cmoney `services/finmind.py` 樣板):
  - Module-level singleton client,不要每次 `new`。
  - 所有外部呼叫先過 rate limiter / token bucket。
  - JSON cache 用 `atomic_write_json` / `read_json`,寫入帶 `_cache_version`,版本 bump 即失效。
  - 同 key 並發走 `_run_once` inflight dedup。
- **async**:`httpx.AsyncClient(timeout=30.0)` + `await`。同步阻塞函式不要混進 route handler。WebSocket / Stream 用 `asyncio` event loop。
- **錯誤處理**:catch 要具體(`httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException`,以及 DQ4 SDK 特有 exception),不裸 `except`。`except Exception` 只在 route 邊界 + 一定要 `logger.exception` + 轉 502。
- **測試**:pytest + `asyncio_mode = "auto"`,async test 不用 `@pytest.mark.asyncio`。Mock 走 `monkeypatch`,不 `unittest.mock`。
- **Ruff**:line-length 100。Format 跟既有檔對齊,不順手重排既存格式。
- **pyright basic**(從第一天就開)— type hint 已寫齊,加 checker 拿免費 invariant check。

---

## 3. React / TypeScript 風格(若採 React 前端)

從 trash-cmoney §7 升級路線的「採納項」直接內建,不重蹈技術債:

- **Custom hook 統一回傳 shape**:`{ data, loading, error, refresh, ...extras }`。
- **Server state 一律走 TanStack Query**,**禁止**手寫 `useEffect + fetch + seqRef`。React 19 + TQ 是新專案 baseline,避開 trash-cmoney 累積 8 個手寫 hook 的債。
- **Stale-drop**:TQ 自帶 cancellation,不額外寫 `seqRef`。
- **Function component + hooks only**。沒有 class 元件,**沒有 `forwardRef`**(React 19 `ref` 是普通 prop)。
- **TypeScript**:`strict: true` + **`noUncheckedIndexedAccess: true`**(從第一天就開)。
- **Tailwind 用 semantic token**:`text-ink` / `text-ink-muted` / `text-ink-dim` / `text-accent` / `border-line` / `bg-bg` / `bg-bg-deep`。token 在 `src/index.css` 的 `@theme`。**Bull = 紅 / Bear = 綠**(台股慣例,不套美股 green-up)。
- **重元件 lazy**:跨 tab 切換的大元件走 `React.lazy()` + `<Suspense fallback={...}>`。
- **純渲染抽到 `lib/*-svg.tsx`**:SVG 計算函式無 React 依賴,獨立單元測試。元件只負責掛 DOM。
- **`cn(...classes)`** 走 `lib/utils.ts`(`clsx` + `tailwind-merge`),不直接拼字串。
- **UI 文字一律繁體中文**(`重新整理` / `載入中` / `無交易日` …)。錯誤訊息、aria-label 也用繁中。
- **Vitest 測試 colocated** `*.test.tsx` / `*.test.ts`,跑 RTL 的檔要在頂端寫 `/** @vitest-environment jsdom */` pragma。`afterEach(cleanup)`。
- **Path alias** `@/` → `src/`(`vite.config.ts` + `tsconfig.app.json`)。**新 code 一律用 `@/`**,不用相對 import。
- **Date 用 `YYYY-MM-DD` 字串** 在 API + state 流動;`new Date()` 只在邊界。
- **`hidden` attribute > 條件 render**:tab 切換用 `<div hidden={tab !== "x"}>` 保留 DOM。
- **`eslint-plugin-react-you-might-not-need-an-effect`** 開起來,`useEffect` 是 anti-pattern 直接 lint 抓。

---

## 4. 跨檔契約

- **API error JSON shape**:`{ "detail": { "error": "<code>" } }`,frontend client 解 `detail.error`。改契約 = 同時改兩邊。
- **Refresh 慣例**:URL query `?refresh=true` → backend 跳過 cache、重抓 upstream。frontend 一律走 `queryClient.invalidateQueries` + refetch with refresh flag。
- **Cache version bump**:`_CACHE_VERSION`(在各 service 內)+1 即作廢所有舊 cache,不需手動清。

---

## 5. 資料源

**確認結果(2026-06-26 deep-research + targeted Touchance fetch,完整報告 `docs/research/2026-06-26-dq4-and-broker-api-survey.md`)。**

**這個 repo 只做 Touchance scope。個股 + 族群即時監控分到 trash-cmoney(純 FinMind 一條線更乾淨)。**

---

### 主資料源 = Touchance 4.0(達錢 4)

- 艾揚資訊獨立平台,**非券商產品**(易混淆,溝通要寫全名)。Python API 走 **ZMQ**(Quote port 51171 / Trade port 51141)。
- User 持有最高會員訂閱(綁帳號不綁 repo,事實留 user memory `touchance-account-tier`)。
- 涵蓋:**國內外期貨即時行情** + 歷史(1 分 K 一年、日 K 十年)+ 下單抽象 + 帳務查詢。
- 官方 GitBook:https://touchance-1.gitbook.io/touchance/
- 官方 Python wrapper:GitHub `TOUCHANCE/TCPY`
- 環境前置:`pip install zmq` + Touchance Windows app 常駐 + 與 ZMQ ports 通。
- **下單前提**:Touchance 只是抽象層,實際送單仍要向所屬期貨商申請 API 交易權限 — §7 流程要考慮這層。

---

### 補強資料源 = FinMind Sponsor(期貨 / 選擇權 chip)

Touchance **沒涵蓋**期貨 / 選擇權籌碼面(三大法人 / 大戶 OI / 結算價)。這些走 FinMind Sponsor(user 已持有 token,沿用 trash-cmoney 接入慣例):

- `taiwan_options_snapshot` / `taiwan_futures_snapshot`(備援,主要走 Touchance push)
- `TaiwanOptionInstitutionalInvestors` + `AfterHours` — 日盤 + 夜盤三大法人選擇權
- `TaiwanOptionOpenInterestLargeTraders` — 大戶 OI
- `TaiwanOptionFinalSettlementPrice` — 結算價

詳細 dataset 列表見 trash-cmoney CLAUDE.md §5 + memory `finmind-api-reference`。

**FinMind 接入慣例**:借鏡 trash-cmoney `services/finmind.py` 樣板(Bearer header / TokenBucket rate limiter / `_run_once` inflight dedup / atomic JSON cache / `_CACHE_VERSION` invalidate)。**不要重新發明**。

---

### 排除清單(專案級決策)

- ❌ **不用 Fubon Neo / `fubon-neo`** — user 明確排除(2026-06-26)。對應 user memory `feedback-no-fubon-api`。
- ❌ **個股 + 族群即時監控不在此 repo** — 那塊去 trash-cmoney 做(純 FinMind / Linux Docker / 不要 Touchance 常駐 / 沿用既有 FinMind 接入)。
- Shioaji / 凱基 SUPER PY / 群益 Touch Prime / 元大易策略 等其他券商 Python SDK,目前 scope 內沒有理由整合。

---

### 沒有 DB

- State = client(React) + filesystem JSON cache(backend),沿用 trash-cmoney `utils/cache.py` atomic write + `_CACHE_VERSION` 慣例。
- ZMQ 即時 tick 流 in-memory(不持久化);歷史與 chip EOD 才走 JSON cache。

---

### Open Questions(實作時要驗)

1. Touchance 是否真涵蓋台股權證 underlying / 隱波?官方文件主打期貨,**沒看到台股權證鏈描述**,Phase 2 實裝時要驗,可能要 fallback FinMind 或 TPEx OpenAPI。
2. 跨網段 / Docker 化 Touchance ZMQ socket 是否可行?若想把 backend 拆出 Touchance host,要先實測。
3. ZMQ reconnect / heartbeat 紀律 — Touchance 本機 app 崩潰或重啟時,Python client 行為要規範。
4. Touchance 的 TXO 期權鏈深度 — 若有提供五檔 OI 深度,FinMind snapshot 可能不必補;若沒有,FinMind 是補強的關鍵。

---

## 6. 提交慣例

- Commit message 既有風格:`<type>(<scope>): <subject>`,type 取 `feat` / `fix` / `chore` / `refactor` / `perf`,scope 多用 `dq4` / `warrant` / `frontend` / `backend`。subject 描述「為何」 > 「做了什麼」。
- 三類分開(對應 user-global B 條):🔴 行為改 / 🟢 新功能 / 🔵 重構 不混 commit。
- DevTools MCP 驗證截圖放 `docs/specs/<feature>/screenshots/`,commit 訊息註明 `chore(...): ... verification screenshots`。

---

## 7. 高 blast radius 動作:下單(若 scope 擴展)

只要 scope 擴張到 `place_order` / `cancel_order` / `modify_order`,所有相關函式預設要過三道閘:

1. **環境檢查 / 雙環境隔離**:模擬戶 vs 正式戶,正式戶要 `DQ4_LIVE=1` env var + 啟動 banner 印出「環境名 + 帳號末 4 碼」。誤觸正式戶要明顯。預設啟動 = 模擬戶。
2. **二次確認**:CLI / UI 操作要二次確認(或 `--dry-run` flag 顯示模擬結果),不可一鍵下單。
3. **不可逆動作審計**:每筆 order request / response 寫 append-only log(JSON Lines),含 `request_id / timestamp / 帳戶遮罩 / 結果`,事後可重建。

WebSocket / 即時 Stream 紀律:

- **Reconnect**:exponential backoff + max retry,連續失敗要主動回報不要靜默重連。
- **Heartbeat 必開**:N 秒未收視為斷線,觸發 reconnect。
- **Stale tick drop**:每筆 tick 帶 `timestamp / sequence number`,過時資料不蓋新狀態(類比 trash-cmoney `seqRef`,但比對時序)。
- **Subscribe dedup**:同一個 symbol 不重複訂閱,參考 trash-cmoney `_run_once` inflight pattern。

---

## 8. Lessons Learned(累積 — 從 /feat 等流程的 Phase 8.5 沉澱)

### 規劃階段預錨定(尚未實作驗證,先記下避免重踩)

- **trash-mr-warrant 只做 Touchance scope**(期貨 + 選擇權 + 權證 + 下單)。個股 + 族群即時監控**分到 trash-cmoney 做**(純 FinMind / Linux Docker / 不要 Touchance 常駐 / 已有 FinMind 接入慣例可借鏡)。這是 2026-06-26 第三次釐清的結論 — 前兩次先把 Touchance 當 phase-無關主源,再分 phase 但同 repo,最終分 repo。(Trigger:擴 scope 或選資料源時、或有 PR 想把個股相關 code 推進這個 repo)
- **「達錢 4」≠ 任何券商產品 = Touchance 4.0**(艾揚)。命名容易跟「DQ2 國際贏家」(SYSTEX)、「XQ 全球贏家」(SysJust)混淆 — 三家不同公司不同產品。實作或對外文件提到「DQ4」時一定要附 Touchance 全名避免歧義。(Trigger:寫 README / commit message / 跟非自己人溝通時)
- **Touchance 主打期貨,台股權證涵蓋待驗**:官方 `行情串接` 文件只給 TXF 範例 + 「QuoteManager 商品檔 ( 國內外期貨熱門月 )」字樣 → 權證涵蓋不明,Phase 2 啟動前要驗(若沒涵蓋,Phase 2 改 fallback FinMind 權證分點 + TPEx 公開資料)。(Trigger:Phase 2 啟動前)
- **Touchance Python API = ZMQ**,**不是** REST/WebSocket/COM/DDE/RTD。Quote port 51171 / Trade port 51141。寫 client 時記得是 `pyzmq` + asyncio,不是 `httpx` / `aiohttp`。Async 整合模式跟 trash-cmoney 既有 httpx pattern 不同,新接 service 不要照貼。(Trigger:寫 `services/touchance_*.py`)
- **Touchance 下單仍要券商授權**:Touchance 本身只是抽象層,實際送單要再向所屬期貨商申請 API 交易權限。設計下單流程(§7)時要假設「即使 Touchance 通了,期貨商那邊還可能擋」,要分開錯誤碼:`TOUCHANCE_DOWN` vs `BROKER_REJECTED`。
- **Touchance Windows app 常駐 = 部署綁定**:這個 repo 一啟動就被 Windows 綁住(scope 純 Touchance),Linux Docker 不在規劃內。寫 code 時放心用 ZMQ + Windows 路徑;若想跨 host 部署(Touchance host vs Python backend host),先實測 ZMQ 跨網段穩定度。

### 實作後沉澱

- **FinMind `TaiwanStockPrice` 無 data_id 全市場回傳含權證等**,一天 ~3 萬 rows;334 天真跑灌了 4.2M rows 進 prices.csv。`backfill_finmind` 已內建 known_ids 過濾(只收既有檔已知代碼,冷啟動空檔會 warning),別移除。(2026-07-07,Trigger:碰 backfill 或新增 FinMind dataset)
- **urllib 的 SSL read timeout 以 `TimeoutError` 拋出,不包在 `URLError`**,retry 的 except 集合要含它,否則長跑批次中途炸。(2026-07-07,Trigger:寫任何 HTTP retry)
- **prev_close 語意 = 當日 close − spread(除權息參考價),neigui 同源**;`DailyIndex.ref_prev_close` row-level 處理 spread 缺值(None → fallback 前日 close)。不要用「前一日 close」直接當參考前收。(2026-07-07,Trigger:碰漲停價/報酬率計算)
- **驗證指令別接 `| tail`/`| head` 再看結果** — pipe 會把 exit code 換成 tail 的 0,本 feature 兩次踩到(ruff 紅著 commit、backfill 崩了顯示 exit 0)。要嘛先落檔再 tail,要嘛檢查 `$?` 前不接管線。(2026-07-07,Trigger:任何 gate 指令)
- **neigui 種子事件池有截止邊界**(3055 的 2026-06-24 鎖板不在池內)— 用 replay/backtest 結論時記得資料端點,滾動重驗要先刷新種子池。(2026-07-07,Trigger:引用回測結論或排 Phase B)

(寫入規則參考 trash-cmoney CLAUDE.md §8。)
