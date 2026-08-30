# copycat(前 trash-mr-warrant)— 達錢 4 看盤工具 + 分點行為指紋辨識

User-global `~/.claude/CLAUDE.md` 的鐵則一律繼承,不重述。本檔只放「讀 code 看不出來」的
專案級事實;**累積教訓已全數移至專案 skills(見 §8 索引),本檔不再累積教訓全文**(2026-08-10)。

## Agent skills

### Issue tracker

Specs 與 tickets 走本 repo 的 GitHub Issues(`gh` CLI)。See `docs/agents/issue-tracker.md`.

### Triage labels

五個 canonical 角色標籤採預設字串。See `docs/agents/triage-labels.md`.

### Domain docs

Single-context:根目錄 `CONTEXT.md`(領域術語 glossary)+ `docs/adr/`(架構決策,lazily
建檔)。See `docs/agents/domain.md`.

---

## 0. 目的 & 結構

- **DQ4 = Touchance 4.0**(達錢 4,艾揚資訊獨立平台,**非任何券商產品**;易與 DQ2 國際贏家
  (SYSTEX)、XQ 全球贏家(SysJust)混淆 — 對外溝通必附 Touchance 全名)。身份報告:
  `docs/research/2026-06-26-dq4-and-broker-api-survey.md`。
- 做達錢 4 **期貨 + 選擇權 + 權證**即時看盤/監控,**以及**分點盤中行為指紋辨識(§0a)。
  Phase 1(現在)= 期貨+選擇權即時看盤(Touchance push tick + FinMind 補 chip);
  Phase 2 = 權證監控(待 TC4 涵蓋驗證);Phase 3+ = 下單(先過 §7)。Read-only 看盤直到 §7 開啟。
- **個股+族群「純看盤」監控不在本專案**(回 neigui 做)。例外兩塊留 copycat:
  (a) 分點盤中行為指紋(2026-07-06:核心訊號 FinMind 沒有,必靠 TC4 tick/1K);
  (b) 全市場廣度掃描(2026-08-06:台股綜合 tab 的一環,FinMind 廣度發現 → TC4 深度盯盤
  一鍵銜接;總 spec `docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md`)。
- 「Mr Warrant」= 權證小哥 reference,場景偏權證+選擇權 trader workflow。

### 0a. 分點行為指紋辨識

- 核心設計原則:**身分判定精度天花板低(2–2.8x lift),鎖板品質 + T+1 開盤微結構這些
  「不需要知道身分」的訊號效果量遠大於猜身分**(neigui broker-signature-explorer 驗證結論)。
- 規格 `docs/strategy.md`(Phase 1 縮池 / Phase 2 鎖板品質評分 / Phase 3 T+1 決策);
  佐證 `docs/evidence/`;replay 設計 spec `docs/superpowers/specs/2026-07-07-broker-
  fingerprint-replay-design.md`;種子資料 = neigui `backend/data/research/five-tigers/`
  (1.24 GB,本機不納版控)。TC4 連線元件 `spikes/TCPY/tcoreapi_mq.py` — 2026-07-06 修過
  KeepAlive 執行緒生命週期 bug,一次性腳本收工必呼叫 `Disconnect()` 否則 process 不退
  (細節 `docs/research/2026-07-06-tc4-stock-tick-1k-api-report.md` §11;檔案 gitignored)。
- **通用框架不綁「五虎」**:分點集合是可替換輸入(watchlists/*.json),不 hardcode 分點名稱。
- 現階段 = 評分引擎 + 歷史 replay(事件驅動、無 lookahead、身分無關),門檻全收版本化
  strategy config。**硬限制:五檔委買賣深度不可回測**(TC4 tick 僅成交當下一檔 Bid/Ask)。

```
copycat/                  # Python 3.13 package(stdlib-only runtime;pytest/ruff/pyright dev)
├── data/                 #   models(Bar1K)、store(1K atomic JSON)、daily、import_neigui
├── engine/               #   lock_quality(LockTracker)、t1_open(T1Tracker)— 零 IO 狀態機
├── replay/               #   runner / report / validate(golden gate)/ compare
├── backtest/             #   T 日跟多隔日沖 GA 回測:config/universe/features/simulate/
│                         #   search/stats/pipeline(outcome cache 三重失效)/report
├── live/                 #   TXO 看盤:models/payoff/aggregate/handover/tc4(唯一碰 ZMQ)
│                         #   個股:stock_models(五檔位移歸一/試撮窗)、stock_state、stock_source
│                         #   個股訊號:signal_state(CDP 穿越/爆拉跌/爆量/鎖板,零 IO)
│                         #   期貨:futures_models(HOT YYYYMM 解析)、futures_source
│                         #   相關係數:corr_models/corr_state/corr_source(海外腿全天窗)
│                         #   六腿江波圖:river_models/river_state/river_backfill
├── capital/              #   群益 Capital 下單(extras [capital]):com/client(COM 專屬執行緒)/
│                         #   models/safety/mapping/reply/store/balance/close/factory
│                         #   ⚠ test 沙盒未開通(1097),驗證走 prod 安全首單;達錢 4 無下單
│                         #   功能 → 下單全走群益(2026-07-28 拍板)
├── server/               #   FastAPI 轉發層:engine(EngineRuntime/QuoteSource Protocol)、app、
│                         #   stock_engine(訂閱池/兩段式 rollover/回補 worker)、overlay(CDP/MA;
│                         #   已完成 bar 剔除 / don't-cache-empty)、
│                         #   index_engine(加權 IX0001 push+1K 回補、櫃買 MIS 5s poll、watchdog
│                         #   09:00-13:25、兩段式換日 pending buffer)、mis(TPEx 非契約公開端點,
│                         #   可能無預警壞,失敗 None 降級)、capital_api、futures_engine(五檔+
│                         #   resolved_contract)、
│                         #   corr_engine(三窗 Pearson;兼六腿江波圖,同一報價流餵 RiverState)、
│                         #   signal_hub(雙佇列 fanout:jsonl 真相源+Discord 節流)、discord_bot
│                         #   (/watch slash,token 缺降級)、watchlist_service(PUT/bot 同鎖 +
│                         #   canonical 零寫早退)、oi_levels(TXO 月契約 OI 撐壓)、breadth_engine
│                         #   (FinMind 家數 poller + 連板 EOD task;類股輪動 / 全市場鎖板事件
│                         #   已於 2026-08-16 刪除)、breadth_fetch、
│                         #   finmind_token、__main__(port env TXO_SERVER_PORT 預設 8721)
│                         #   /api/trade/* 已刪(2026-08-04)→ 404,下單全走群益 capital
├── market.py             #   台股 tick 表 + 漲停價(毫元整數運算)
├── market_breadth.py     #   全市場廣度純函式(零 IO;parity oracle fixture 對照)
├── limit_streaks.py      #   連板數純函式(prev_close = close − spread)
├── trading_calendar.py   #   台股交易日曆純判定(configs/trading_holidays.json;檔缺=只擋
│                         #   週末+WARNING、壞檔 raise;缺年 WARNING 每年節流一次)
├── breadth_config.py / signals_config.py / corr_config.py / strategy_config.py  # configs/*.json 覆寫
│                         #   (另 configs/trading_holidays.json = 交易日曆資料,非 dataclass 覆寫)
│                         #   (signals:檔缺=全預設、壞檔 raise;corr:base 腿必須 source=
│                         #   futures_engine — 同 symbol 衝突;notify:429 Retry-After 重試一次)
├── notify.py             #   Discord webhook(URL 未設 no-op、never-raise;CLI notify-test)
├── stock_watchlist.py    #   個股自選(schema v2 groups;v1 讀時遷移)
├── watchlist.py          #   可替換分點集合(watchlists/*.json)
└── cli.py                #   python -m copycat <import-neigui|replay|validate|compare|...>
frontend/                 # React 19 + Vite + TS strict + Tailwind v4 + TanStack Query
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
| TXO 看盤 server | `.venv\Scripts\python -m copycat.server`(需達錢 4 開啟;port 8721;非交易日自動取最近交易日(`configs/trading_holidays.json`,`GET /api/calendar` 可查;`years_loaded` 不含當年 = 日曆過期要更新);`TXO_BACKFILL_DATE` 仍為手動覆寫,TXO 面與交易日盤前冷啟動仍需要它) | repo root |
| 跑著的 server 是哪一版 | `curl -s localhost:8721/api/health` → `{git_sha,...}`;判法與教訓見 skill `ops-discipline` | repo root |
| Frontend dev / 測試 / build | `npm run dev` / `npm test` / `npm run build` | frontend/ |
| **看盤日常(prod build)** | `npm run build` 後 `npm run preview`(port 4173;proxy 沿用 dev 的 /api + /ws → 8721)。dev build 的 React Component Performance Track 已由 dev-perf-guard 堵住洩漏,但 props-diff 開銷仍在 —— 整天掛著一律用本列,`npm run dev` 只做開發(2026-08-20) | frontend/ |
| Config 實驗對照 | `.venv\Scripts\python -m copycat compare out/A out/B` | repo root |
| 日線回補(一次性) | `.venv\Scripts\python -m copycat backfill-daily` | repo root |
| T 日回測:特徵 / 搜索 | `... tday-features` / `... tday-search --report-date <YYYY-MM-DD>`(報告 → docs/evidence/) | repo root |

完成前 gate:`pytest -q` + `ruff check` + `pyright` + `copycat validate` 全 PASS(validate 需先跑過
four/five 兩份 replay)。venv = Python 3.13(`py -3.13 -m venv .venv`;`py` 預設 3.14 別直接用)。
動到 frontend/ 另加:`npm test` + `npx tsc -b` + `npx eslint src` +
`npx react-doctor@latest --scope changed --no-telemetry`(在 frontend/;doctor 只有
**新增** finding 算 FAIL,存量不擋;誤報處置與 rules 口徑見 auto-verify skill 4.4.0 節)。

**部署前置(Touchance 特性)**:TC4 是 Windows 桌面 app,Python client 走 **ZMQ**(實測登入
port = **50774**,SubPort 動態;官方文件 51171/51141 與現版不符)。後端 host 必須 Windows +
TC4 常駐 + ZMQ 對 localhost 通;非 headless 友善,Linux Docker 不在規劃內;初期全在本機同台跑。

`.env` secrets(runtime 讀取語意見 skill `backend-conventions` env 節):
- `FINMIND_TOKEN`(oi-levels TXO OI 撐壓 + 家數帶 breadth;未設 → breadth 停用,其餘不受影響)
- `DISCORD_WEBHOOK_URL`(選配;未設 no-op。驗收 `python -m copycat notify-test`)
- `DISCORD_BOT_TOKEN` + `SIGNALS_DISCORD_CHANNEL_ID`(訊號推送 + `/watch`;token 未設 → bot
  降級,推送 fallback webhook。同 application 的 command sync 會覆蓋 treading-king bot
  舊指令 — 該 bot 已退役,可接受)
- `FRONTEND_ORIGIN`(CORS)
- Touchance 訂閱授權碼 — 實裝時補確切變數名
- 群益 Capital(沿 treading-king):`CAPITAL_USER_ID` / `CAPITAL_PASSWORD` /
  `CAPITAL_FULL_ACCOUNT`(證券帳號;期貨帳號登入後 GetUserAccount 自動發現,**不另設 key**)/
  `CAPITAL_ENV`(test 沙盒未開通 → 1097 降級)/ `CAPITAL_DLL_DIR` / `CAPITAL_ORDER_ENABLED`
  (false=總開關全擋)/ `CAPITAL_MAX_QTY` / `CAPITAL_MAX_AMOUNT`(未設/0=不限,user 拍板)/
  `CAPITAL_AUDIT_DIR`(選配,預設隨 `TXO_AUDIT_DIR`;審計檔 `capital-YYYYMMDD.jsonl`)
- `VERIFY_GATE_SKIP` 不在此;`VERIFY_BREADTH_FAIL=1`(verify server 專用,非 .env:breadth fake
  取數齊拋 BreadthFetchError 的失效注入通道,prod 不看)

---

## 2. Python 風格 → 專案 skill `backend-conventions`(寫或改任何 `.py` 前先讀)

## 3. React / TypeScript 風格 → 專案 skill `frontend-conventions`(寫或改 `frontend/` 前先讀)

## 4. 跨檔契約

- **API error JSON shape**:`{ "detail": { "error": "<code>" } }`,frontend 解 `detail.error`。
  改契約 = 同時改兩邊。
- **Refresh 慣例**:`?refresh=true` → backend 跳過 cache 重抓;frontend 走
  `queryClient.invalidateQueries` + refetch with refresh flag。
- **Cache version bump**:`_CACHE_VERSION`(各 service 內)+1 即作廢所有舊 cache。
- **`OrderRecord.unit` 字面值(張/口/股)是前端過濾鍵**(2026-08-13 起,閃電梯零股閘
  `ladder-lots.ts` 依 `unit === "股"` 排除):產生點 `capital/store.py::_to_record`,改字面值
  = 改契約要同時改兩邊;`tests/capital/test_store.py` 有 lock。
- **自選上限常數雙邊同值**(2026-08-13 起 = 50):產生點 `copycat/stock_watchlist.py::
  WATCHLIST_LIMIT`(唯一擋人的地方),讀者 = 前端 `frontend/src/lib/constants.ts::
  WATCHLIST_LIMIT`(只餵 `errText` 文案)+ bot `discord_bot.py::_ERROR_TEXT`(f-string
  已同源)。改值 = 改契約要同時改兩邊;漂掉的症狀是文案數字與實際擋人的數字不符,零錯誤訊號。
- **WS 心跳契約**(2026-08-19 起):後端每條 WS 每 `WS_HEARTBEAT_SECS`(10 s)送
  `{"type":"ping"}`(產生點 `copycat/server/ws.py::WS_HEARTBEAT_SECS`,relay 直送不經
  per-client queue);讀者 = 前端 `frontend/src/lib/ws-reconnect.ts::WS_SILENCE_TIMEOUT_MS`
  (30 s 靜默 watchdog,**必須 > 心跳間隔**,否則健康連線會被誤判半死而狂重連)。
  改值 = 改契約要同時改兩邊;前端 hook 的 `onMessage` 看不到 ping(helper 已過濾)。
  2026-08-25 起前端 **onopen 即武裝**(不再等首則 ping):後端若停送 ping,所有 WS 每 ~35 s 重連一次,
  症狀是 uvicorn access log 每半分鐘一輪 8 條握手 —— 這是契約被單邊改掉的訊號,不是前端 bug。

- **TXO 回補進度欄 `handover.attempt`**(2026-08-21 起):產生點 `copycat/server/engine.py::_run_handover_locked`
  寫 `_handover={attempt,attempts_max,phase}`;唯一讀者 `frontend/src/components/ConnectionBadge.tsx`(只讀 `attempt`,
  `status==='backfilling' && attempt>1` 才印「第 n 次」)。後端改欄名 → badge 靜默退回逐字「回補中」,零錯誤訊號。
- **`/api/stock/state/{code}?tape=0` 字面值 + `tape_omitted`**(2026-08-21 起):後端 `app.py` 只認字串 `"0"`
  省略 ticks 並回 `tape_omitted: true`;讀者 `frontend/src/hooks/useStockStream.ts::stateUrl`(送 `tape=0`)與
  `lib/stock-accum.ts::fromSnapshot`(讀 `tape_omitted` → `accum.tapeOmitted`,TickTape 空態分流)。漂掉的症狀:
  群組檢視省不到流量 / 切回單檔空態永遠印「尚無成交」。
- **個股 `seq` 的兩個口徑**(2026-08-24 起):`snapshot.seq` = `ticks` 的**尾筆**序號;
  `tick.seq` **每收下一筆成交 +1**(產生點 `copycat/live/stock_state.py::ingest` 與 `snapshot()`)。
  讀者 = `frontend/src/lib/stock-accum.ts::fromSnapshot`(自 `snap.seq` **由尾回推**指派逐筆列的
  React key `n`)與 `applyTick`(新列直接取 `msg.seq`)—— 兩條路徑靠這條契約落在同一把尺上。
  後端改成別的語意(訊息計數 / 每次 snapshot 自增)= 改契約要同時改兩邊;漂掉的症狀是
  **成交明細 tbody 靜默整片重掛**(畫面只是閃一下,零錯誤訊號)。
  例外已知且刻意:`apply_backfill` 的 seq 跳增會讓號整段平移一次(回補當下重掛一次)。
- **訊號規則參數契約前後端同表**(2026-08-25 起,N055;08-26 A8 補齊):產生點 `copycat/signal_rules.py`
  的 `PARAM_SPECS`(值域;出界 → `INVALID_RULE`)、`INT_PARAM_KEYS`(非整數拒收)、`COOLDOWN_MIN/MAX`
  —— 唯一擋人的地方;前端鏡像 `frontend/src/lib/signal-params.ts`:`PARAM_FIELDS` 的 `min`/`max`/`integer`
  (規則窗即時提示與 input 屬性、送出前「<欄名>須為整數」)+ `COOLDOWN_MIN/MAX`。漂掉的症狀:前端寬於
  後端 → 使用者拿回泛用 INVALID_RULE;前端窄於後端 → 合法值被擋、說明還寫著錯的界 —— 兩邊都零錯誤訊號。
  以共用 golden fixture `tests/fixtures/signal_param_specs.json`(`specs` / `int_keys` / `cooldown`)釘住:
  `tests/test_signal_rules.py::test_param_specs_parity_with_frontend` + `frontend/src/lib/
  signal-param-parity.test.ts` 各自斷言。**前端「新規則」預設值(`ParamField.default`)不在 fixture**(後端沒有
  對應概念,種子走 `SignalsConfig`),由前端 parity 測試釘「落在值域內、整數鍵為整數」。
- **期貨 CDP/MA 前後端同式**(2026-08-24 起):產生點 `copycat/server/overlay.py::compute_cdp/compute_ma`
  (+ `build_overlay` 的 `date < today` 界),前端鏡像 `frontend/src/lib/futures-overlay.ts`
  (期貨分時不打 `/api/stock/overlay` —— 那支吃股號,拿現股 CDP 疊期貨價是假陳述)。
  **差異白名單 = 前端多一道 `usable()` 0 價閘**(TC4 期貨會送 0 價 bar),連帶 MA 母體在壞 bar
  時可能與後端不同(視窗前挪)。漂掉的症狀:同一組日 K 的 CDP 在個股頁與期貨頁長不一樣 ——
  兩張圖都畫得出來、兩組數字都看起來對,零錯誤訊號。因此以**共用 golden fixture**
  `tests/fixtures/overlay_parity.json`(expected 手算寫死)釘住:後端
  `tests/server/test_overlay.py::test_overlay_parity_with_frontend` + 前端
  `frontend/src/lib/overlay-parity.test.ts` 各一條,改壞任一邊只有那一邊紅。
- **`/api/market/bars` 的 `meta.status` 三態**(2026-08-25 起,N104):產生點
  `copycat/live/futures_source.py::fetch_bars_range`(raise `HistoryTimeoutError`)→
  `copycat/server/futures_engine.py::bars_range`(裸 tuple `(bars, status)`;值域持有者
  `copycat/live/stock_source.py::BarsStatus`,`BarsResult` 到 `app.py` 才組 —— 08-25 review 回校)→
  `copycat/server/bars.py::build_minute`(兩段取最壞)→ `app.py::_market_payload(status=…)`。
  值域 `ok | timeout | disconnected`,沿 `/api/stock/bars` 既有三態語意。**這一格只在期指
  `tf=1` 出現;其餘路徑(加權 / 櫃買 / 日週月 K)連鍵都不給** —— 缺欄 = 該路徑尚未三態化。
  硬寫一個恆 `ok` 是謊報:index proxy miss 時會是 `source:"unavailable"` + `status:"ok"`,
  而後者的意思正好是「問到了、就是沒有」。
  讀者 = `frontend/src/hooks/useMarketBars.ts::BarsMeta.status`(optional)與
  `components/futures/FuturesChart.tsx::EMPTY_TEXT`(空態三句話)。後端拿掉這一格 → 前端
  `?? "ok"` 靜默退回單一句「暫無資料(TC4 未回應)」,「TC4 忙」與「真沒 K 線」再度不可分辨,
  零錯誤訊號。**與 `FuturesChart` 的 gate 5「分時資料落後 N 根(TC4 回補中)」是兩件事**:
  `status` = 這一趟回補請求的結果(bars **空**時才讀得到);gate 5 = 資料尾 vs WS 最後成交
  (bars **非空**時才成立)。兩者並存不合併 —— 處置不同(等重試 vs 看當日段完整性)。
- **關機預算三方同源**(2026-08-26 起,A1):產生點 `copycat/server/shutdown_budget.py`
  (`run_grace_secs()` = `WS_DRAIN_SECS` + `TC4_LANE_DEPTH` × `tc4.close_worst_secs()` +
  `COM_JOIN_TIMEOUT_SECS` + slack;現值 83 s = TC4 半死**可計段**的上界,`Disconnect()` 的 KeepAlive
  `term()` 無上界不計;健康路徑實測 1–3 s)。讀者 =
  `run.ps1`(啟動時 `python -c` 讀 `run_grace_secs()` 當 Ctrl+C 後的 graceful 上限,超時才
  `taskkill /T /F`)、`copycat/server/__main__.py`(uvicorn `timeout_graceful_shutdown=WS_DRAIN_SECS`)、
  `app.py` lifespan(TC4 session **並行 lane**:corr→futures 串鏈 ‖ index ‖ stock ‖ txo,capital 最後;
  每段進場印「關機 <段> 段開始」、收尾印「關機收尾 …」彙總行,單段 > 2 s 印 WARNING 點名)。改任一邊的 timeout
  (`_REQ_TIMEOUT_MS` / `DEFAULT_LOCK_TIMEOUT_SECS` / COM join)**不需要**改 run.ps1 —— 那正是同源的
  意義;**改 lane 形狀(串鏈加深 / 把 capital 搬回中間)= 改契約**,要同步改 `TC4_LANE_DEPTH`。
  漂掉的症狀:run.ps1 在 lifespan 還在退訂時硬殺,健康 session 也變殭屍,下一台開頭 ~60 s 零推播,
  零錯誤訊號(只在 TC4 log `RemoveLoginInfo` 晚 60 s 才看得到)。不等式由
  `tests/server/test_shutdown_budget.py` 釘住(含 run.ps1 字面 parity 與 UTF-8 BOM)。

- **部位均價語意 `avg_source` + 當沖段 `today_qty`**(2026-08-26 起,fix/breakeven-avg-source-daytrade-tax;
  08-27 fix/breakeven-avg-source-prod-chain 校正產生點):`broker` 的產生點是 `copycat/capital/client.py::
  _on_profit_complete`(損益試算回填 pending 列,群益「平均買進成本」**已含買進手續費**,prod 實證 4991 469.50 →
  469.62);`fill` 的產生點是 `copycat/capital/store.py::_apply_fill_locked`(樂觀套用 = 純成交價);
  `set_positions` 只沿用不產生。**`avg_source` 沒有第二個寫入點** —— 08-26 那版把 `broker` 寫在 store 一條零 caller
  的方法上,測試綠、prod 全 null。`today_qty` 產生點 `store.py::_with_today_qty_locked`(當日聚合 buy − sell,
  clamp 到 [0, |qty|],per (股號, 種類),fut 恆 0)。wire 欄名的讀者 = `frontend/src/components/stock/
  PriceLadder.tsx` 與 `frontend/src/lib/position-summary.ts`(把 `avg_source` / `today_qty` 映成 `avgSource` / `todayQty`
  餵 `lib/ladder-position.ts::positionEcon`,唯一算式所在):`broker` 不再加買費、`fill` 加;現股 / 無券空單(`daytrade_sell`,08-30 起)`today_qty` 那段賣出稅 `SELL_TAX_DAYTRADE` 0.15%、其餘 0.3%。
  漂掉的症狀:後端少送 `avg_source` → 前端當 fill 全加一次買費 → 損益比群益 APP 少一筆買費、打平線在快照落地時
  跳一格(08-26 修、08-27 才真的修到 prod 路徑,零錯誤訊號);少送 `today_qty` → 當沖減半靜默消失;前端 switch 無
  default 時整欄缺席(舊後端)= NaN 印到四處 —— 紅燈判準 `curl /api/capital/positions` **證券**持倉列(`market == "sec"`)`avg_source` 非 null;
  `market == "fut"` 列:OI 快照來源的 fut 列 `avg_source` 恆 null(期貨列走 OI 不經損益回填,見 next-time 2026-08-27);唯一非 null
  是 `_apply_fill_locked` 樂觀套用**新建**的 fut 列(`"fill"`),下一輪 OI 快照落地即覆蓋(OI 連續失敗時 `_stale_fut_positions()` 沿用更久)
  —— 兩者都不是契約斷了,也不要替 OI 列硬填來源(pr-119 F-03 / pr-129 F-01)。兩邊值域以
  `tests/capital/test_models.py::test_avg_source_parity_with_frontend` 釘住(後端測試直讀 `types.ts::AVG_SOURCES` 字面比
  `get_args(AvgSource)`;pr-129 F-05):後端先加值而前端沒跟,白名單會把新值**靜默**歸 null 退回修前口徑,零訊號。
- **證券部位 `kind` 的 `daytrade_sell` 值**(2026-08-30 起,fix/borrowless-short-calibration):產生點
  `copycat/capital/balance.py::parse_balance_line`(現股 T 列負股數 → `daytrade_sell`)與 `store.py::_FILL_KIND`(「無券」);
  讀者 = `frontend/src/lib/ladder-position.ts::positionEcon`(當沖稅減半條件 `cash | daytrade_sell`)、`lib/trade-kinds.ts`
  (閃電梯 / header / chip 標籤「無券」)、`lib/close-order.ts::KIND_TEXT`(部位面板「無」/ 確認窗「無券」;**鍵集 = `kindOf`
  送 kind 的值域**,與 wire `server/capital_api.py::PositionCloseBody.kind` 同為 `TradeKind` 四值 —— 「標得出來就送得出去」)。
  漂掉的症狀分兩種:後端把負現股列改成**別的字串** → `kindOf` 回 null → 前端減半靜默消失、標籤印原字串 / 空白、平倉退回
  同檔唯一列 —— 讀者都不會報錯;改回 **`cash`** → `kindOf` 認得、照送 `kind:"cash"` → `position_for` 命中負向 cash 列 → `_CLOSE_MAP`
  無 `(cash, False)` → 平倉直接 403(資料矛盾,`test_cash_short_direction_is_data_contradiction_and_rejected` 釘的就是這個);
  wire 值域單邊收窄 → 前端送 `daytrade_sell` 吃 422。`tests/capital/test_store.py -k borrowless` +
  `tests/server/test_capital_api.py::test_close_body_kind_daytrade_sell_sends_cash_buy` + 前端 `ladder-position.test.ts`
  「無券空單」/ `close-order.test.ts` 釘住。
- **江波圖調色盤色數 ≥ 相關係數腿數**(2026-08-26 起,F4):產生點 `configs/correlation.json` / `copycat/corr_config.py::
  DEFAULT_CONFIG` 的腿數(現 11),讀者 = `frontend/src/components/corr/river-colors.ts`(`RIVER_STROKES/FILLS/TEXTS`
  三組字面值 class)+ `index.css` 的 `--color-river-N` token。顏色依腿序位取模指派,腿數 > 色數的症狀是第 n+1 腿
  **靜默撞回 base 近白色**,零錯誤訊號。`tests/test_corr_config.py::test_river_palette_covers_every_leg` 以原始碼字面鎖住;
  加腿 = JSON + DEFAULT_CONFIG + 三組 class + token 同步。
- **個股分時圖「台指期」疊線的分鐘鍵 = 期指 1K 終點標記 −1 分**(2026-08-27 起,feat/txf-intraday-overlay):
  產生點 `frontend/src/lib/txf-overlay-series.ts::txfBarsToSeries`(吃 `/api/market/bars/TXF?tf=1&session=allday`
  的 bar,`t` 是**終點標記**:08:45 開盤首根標 08:46,`copycat/live/futures_source.py` 分鐘域 0846–1345),
  讀者 = `lib/index-overlay-lines.ts::buildIndexOverlayLines`(分鐘鍵與加權 / 櫃買 / 個股 tick 同尺 = **起點**
  HHMM)。後端若把 1K 標記改成起點(或前端忘了 −1)→ 整條台指期線靜默右移一格,兩張圖都畫得出來零訊號;
  `lib/txf-overlay-series.test.ts` 釘 `08:46 → "0845"`。結算價 `ref` 取期貨 WS `FuturesProductState.ref`
  (TC4 `ReferencePrice` = 前一交易日日盤結算價,與期貨 tab 漲跌顏色同一把尺);補尾現價取 index engine 轉供的
  `txf` 報價(每拍 ~1 s),**不用**期貨 WS 0.1 s coalesce 流(圖牆 50 張卡 memo 會被打穿)。
- **相關係數稀疏腿 `sparse` 旗標**(2026-08-27 起):產生點 `configs/correlation.json` 腿的 `"sparse": true`(只認字面
  true)與 `copycat/corr_config.py::DEFAULT_CONFIG`(降級時的同一組;`tests/test_corr_config.py::
  test_sparse_legs_are_sxf_and_vx_and_the_repo_file_agrees` 鎖兩邊集合一致;08-28 起 VX 也是稀疏腿),讀者 = `app._default_corr_source` →
  `CorrQuoteSource(heal_sparse_symbols=)` → `tc4.TC4QuoteSource._heal_tick` R2 迴圈 `continue`。與時段閘
  `heal_symbol_active` **正交**:sparse 腿仍在 R1 母體。漂掉的症狀:該腿每 240 s 一發「零推播自癒 … attempt 1」
  (漏標)或**單腿死**(session 其他腿還在推,R1 不成立)時該腿整場不救(誤標;session 整條死掉仍由 R1 整批救),
  兩邊都零錯誤訊號。`sparse` 打成 `"true"` / `1` / `null` 一律無效並印 WARNING(pr-120 F-02)—— 但只在該設定檔
  **被採用**時印;整份因缺欄 / base 不在 legs 被丟棄時只印「改用預設腿」,旗標不另印(pr-130 F-01)。
- **index session 自癒閘上界 = `index_engine._WATCH_END`**(2026-08-27 起,pr-126 F-01 per-consumer):產生點
  `copycat/live/stock_source.py::_INDEX_HEAL_END`(13:25,end-exclusive;`in_index_heal_window_now` 只給
  `app._default_index_source` 注入),必須與 `copycat/server/index_engine.py::_WATCH_END`(**推播靜默(stale)watchdog**
  的凍結點;分時自癒在**交易日** 09:00 起全程都在,`_WATCH_END` 後只是換成尾段判準接手 —— 有日曆且交易日到午夜、
  有日曆的休市日**整天**一發都不打(08-28 起窗內段也吃日曆,N105 補窗內閘);無日曆 → 窗內照救、盤外到 13:40
  (`_broadcast_loop` 的 heal_window:窗內 `not _has_calendar or _is_trading_day`、盤外 `_has_calendar and _is_trading_day`,pr-131 F-03)
  **同值同語意** —— 兩把都釘在
  「收盤試撮起指數不更新」這一個事實。個股 / corr 台積電腿走另一把 `_TRADING_END` 13:35(試撮期個股仍有簿更新推播),
  **三個消費者不共用一把閘**。13:25 後「index_engine 分時自癒還在救、source 層 REALTIME watchdog 已凍結」是**正常態**,
  不是漂移;漂掉(兩把值不同)的可觀測症狀:值被放寬 → 次一交易日 `grep 零推播自癒 | grep IX0001` 在 13:25 後又出現;
  值被收緊 → 加權 stale 徽章 13:2x 提早熄滅。`tests/server/test_index_engine.py::
  test_watch_end_is_the_index_heal_gate_boundary` 鎖住(放依賴方 server 側,pr-128 F-06);`tests/server/test_main_wiring.py::
  test_stock_and_index_heal_gates_are_two_different_clocks` 鎖「兩把不同 callable」。

## 5. 資料源

- **主資料源 = Touchance 4.0**:國內外期貨即時行情 + 歷史(分 K/日 K)+ 帳務。**無下單功能
  (2026-07-21 實證)→ 下單全走群益 Capital(2026-07-28 拍板)**。官方 GitBook:
  https://touchance-1.gitbook.io/touchance/;wrapper:GitHub `TOUCHANCE/TCPY`。
  User 持最高會員訂閱(綁帳號不綁 repo)。
- **補強 = FinMind Sponsor**(期貨/選擇權 chip:三大法人/大戶 OI/結算價 + 全市場廣度)。
  接入慣例見專案 skill `finmind-conventions`;dataset 細節見 memory `finmind-api-reference`。
- **排除**:❌ Fubon Neo(user 明確排除);❌ 個股+族群純監控(回 neigui);其他券商 SDK 無整合理由。
- **沒有 DB**:state = React client + filesystem JSON cache(atomic write + `_CACHE_VERSION`);
  ZMQ tick 流 in-memory 不持久化。
- Open questions:權證涵蓋(Phase 2 前驗)、跨網段 ZMQ、reconnect 紀律規範化、TXO 期權鏈深度。

## 6. 提交慣例

- `<type>(<scope>): <subject>`,type ∈ feat/fix/chore/refactor/perf/test(`test` = 純測試 commit,
  紅先行那一筆;08-25 review 補列,既有 83 筆),scope 多用 dq4/warrant/frontend/backend;subject
  描述「為何」> 「做了什麼」;三類分開(🔴 行為 / 🟢 新功能或測試 / 🔵 重構)。
- 驗證截圖放 `docs/specs/<feature>/screenshots/`。

## 7. 高 blast radius 動作:下單

`place_order` / `cancel_order` / `modify_order` 相關函式預設三道閘:
1. **雙環境隔離**:正式戶要 `DQ4_LIVE=1` + 啟動 banner 印「環境名 + 帳號末 4 碼」;預設模擬戶。
2. **二次確認**:CLI/UI 二次確認或 `--dry-run`,不可一鍵下單。
3. **審計**:每筆 order req/res 寫 append-only JSONL(request_id/timestamp/帳戶遮罩/結果)。

WebSocket / Stream 紀律:reconnect = exponential backoff + max retry + 連續失敗主動回報;
heartbeat 必開(N 秒未收視為斷線);stale tick drop(timestamp/seq 比對,過時不蓋新);
subscribe dedup(inflight pattern)。

## 8. 累積教訓 → 專案 skills 索引(2026-08-10 遷移)

教訓全文依觸發領域收在五支專案 skill,**新教訓直接寫進對應 skill,本檔不再累積**:

| Skill | 涵蓋 | 先讀時機 |
|---|---|---|
| `tc4-market-facts` | TC4 訂閱/symbol/tick/回補/指數期指/海外/鎖停市價佇列/個股期/TXO/群益 SKCOM/市場資料語意 | 碰任何 TC4 或市場資料語意 |
| `ops-discipline` | 盤中驗證通道(第二台/側車/--verify)/worktree 三險/mutation pycache/版本落差判法 | 盤中驗證、開收 worktree、驗證迴圈 |
| `backend-conventions` | Python 風格 + HTTP retry/uvicorn/env 語意/rollover 快路徑/長跑 log | 寫或改任何 .py |
| `frontend-conventions` | React/TS 風格 + dialog display/SVG pattern 坑 | 寫或改 frontend/ |
| `finmind-conventions` | FinMind 認證/配額/dataset 口徑(TaiwanStockPrice 全市場/BuyAfterSale/TaiwanOptionDaily) | 接 FinMind dataset |

退役(重複/過時)條目清單與還原路徑:見 `~/.claude/harness/RATIONALE.md` 2026-08-10 節。
