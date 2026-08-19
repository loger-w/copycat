# copycat(前 trash-mr-warrant)— 達錢 4 看盤工具 + 分點行為指紋辨識

User-global `~/.claude/CLAUDE.md` 的鐵則一律繼承,不重述。本檔只放「讀 code 看不出來」的
專案級事實;**累積教訓已全數移至專案 skills(見 §8 索引),本檔不再累積教訓全文**(2026-08-10)。

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

- `<type>(<scope>): <subject>`,type ∈ feat/fix/chore/refactor/perf,scope 多用 dq4/warrant/
  frontend/backend;subject 描述「為何」> 「做了什麼」;三類分開(🔴 行為 / 🟢 新功能 / 🔵 重構)。
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
