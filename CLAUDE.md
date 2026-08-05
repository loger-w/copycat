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
├── live/                 #   TXO 即時看盤(2026-07-18):models(TC4 訊息對映/毫點)、payoff(到期
│                         #   損益純函數)、aggregate(內外盤累積狀態機)、handover(回補↔live 交接)、
│                         #   tc4(TC4QuoteSource,唯一碰 ZMQ 的模組)— extras [live] 才需 fastapi/pyzmq
│                         #   個股看盤(2026-07-21):stock_models(REALTIME 對映/五檔位移歸一/試撮窗)、
│                         #   stock_state(當日狀態機:去重/分鐘聚合/VWAP)、stock_source(繼承 TC4QuoteSource)
│                         #   個股訊號(2026-08-04):signal_state(SignalDetector 零 IO:CDP 穿越/
│                         #   爆拉跌/爆量/鎖板,三層去重+盤別/trade_date gate,staged basis 日別標記)
│                         #   期貨行情(2026-07-28):futures_models(HOT 契約 YYYYMM 解析)、
│                         #   futures_source(TXF/MXF/TMF HOT REALTIME)
│                         #   即時相關係數(2026-07-30):corr_models(中價/對數報酬)、
│                         #   corr_state(三窗滾動 Pearson/盤別重置/報酬不跨洞,零 IO)、
│                         #   corr_source(泛化 symbol 訂閱;覆寫全天窗 — 海外腿不可用台指盤別窗)
│                         #   六腿江波圖(2026-07-30):river_models(盤別窗/終點標記分鐘鍵/
│                         #   收盤 clamp/1K 解析;分鐘桶用 FilledTime 不用 PreciseTime — 欄寬
│                         #   跨段不同)、river_state(per-leg 分鐘序列狀態機,零 IO)、
│                         #   river_backfill(1K 當日回補共用收割器,吃 bound method)
├── capital/              #   群益 Capital 下單(2026-07-28,extras [capital]=comtypes+pywin32):
│                         #   com(SKCOM COM 封裝,證券+期權共用 FUTUREORDER)、client(COM 專屬
│                         #   執行緒+命令佇列+審計三段不對稱)、models/safety(上限 None=不限)/
│                         #   mapping(期交所碼轉換/乘數)/reply/store/balance/close/factory(env 單例)
│                         #   ⚠ 群益 test 沙盒帳號未開通(1097),驗證走 prod 安全首單;
│                         #   達錢 4 無下單功能 → 下單全走群益(2026-07-28 拍板)
├── server/               #   FastAPI 轉發層:engine(EngineRuntime/QuoteSource Protocol)、app(routes/WS)、
│                         #   stock_engine(個股訂閱池/兩段式 rollover/回補 worker/廣播,2026-07-21)、
│                         #   overlay(CDP/MA 疊線計算,2026-07-28:已完成 bar 剔除/don't-cache-empty;
│                         #   資料源 = TC4 DK 優先 1K 聚合 fallback,DK 支援度未實測)、
│                         #   __main__(python -m copycat.server,port env TXO_SERVER_PORT 預設 8721)
│                         #   index_engine(指數引擎,2026-07-28:加權 TC4 IX0001 push+1K 回補、
│                         #   櫃買 MIS 5s poll、台指期由 TXO runtime spot 轉供;watchdog 09:00-13:25、
│                         #   兩段式換日 pending buffer;REST /api/index/state + WS /ws/index)、
│                         #   mis(TPEx 櫃買 MIS 快照,非契約公開端點,失敗 None 降級)、
│                         #   capital_api(/api/capital/* + /ws/capital + /api/futures/state +
│                         #   /ws/futures,2026-07-28)、futures_engine(TXF/MXF/TMF 五檔 +
│                         #   resolved_contract HOT→YYYYMM)、
│                         #   corr_engine 另兼六腿江波圖(2026-07-30):同一份報價流餵
│                         #   RiverState(零新增訂閱)、背景 1K 回補逐腿降級、每秒 delta;
│                         #   REST /api/river/state(全量)+ WS /ws/river(首則全量後每秒增量)
│                         #   corr_engine(即時相關係數,2026-07-30:每秒 pull 六腿中價 →
│                         #   三窗滾動 Pearson;base 腿(台指)讀 futures_engine.state() 不自訂
│                         #   TXF.HOT 避 symbol 衝突 — ⚠ 該上游目前零推播,見 §8 與 next-time;
│                         #   REST /api/corr/state + WS /ws/corr);TC4 trade 路已刪
│                         #   (2026-08-04,/api/trade/* → 404;下單全走群益 capital)
│                         #   訊號接線(2026-08-04):server/signal_hub(基準 worker/雙佇列 fanout:
│                         #   jsonl 真相源+Discord 節流/enabled 持久化)、server/discord_bot(discord.py
│                         #   bot 進 server,/watch slash 指令,模組層零 discord import、token 缺降級)、
│                         #   server/watchlist_service(PUT/bot 同鎖 + canonical 零寫早退 + 廣播)
├── market.py             #   台股 tick 表 + 漲停價(毫元整數運算;tick_size_milli 毫元版)
├── signals_config.py     #   訊號門檻(configs/signals.json 覆寫;檔缺=全預設、壞檔 raise)
├── notify.py             #   Discord webhook 發送層(2026-07-27):notify_discord() keyword-only、
│                         #   URL 未設 no-op、429 Retry-After 重試一次、never-raise;stdlib urllib。
│                         #   訊號內容/觸發時機未定(待討論);CLI `notify-test` 實發驗證
├── corr_config.py        #   相關係數六腿設定(configs/correlation.json 覆寫 legs/base;
│                         #   base 腿必須 source=futures_engine — 同 symbol 衝突)
├── strategy_config.py    #   全部策略門檻(版本化,configs/*.json 覆寫)
├── stock_watchlist.py    #   個股自選(2026-07-28 起 schema v2 groups;v1 讀時遷移、上限以聯集計)
├── watchlist.py          #   可替換分點集合(watchlists/*.json)
└── cli.py                #   python -m copycat <import-neigui|replay|validate|compare|backfill-daily|tday-features|tday-search>
frontend/                 # React 19 + Vite + TS strict + Tailwind v4 + TanStack Query(綜合損益單頁)
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
| TXO 看盤 server | `.venv\Scripts\python -m copycat.server`(需達錢 4 開啟;port 8721;休市日補 env `TXO_BACKFILL_DATE=<上一交易日>`) | repo root |
| **跑著的 server 是哪一版** | `curl -s localhost:8721/api/health` → `{git_sha, git_dirty, started_at}`;接著 `git log <git_sha>..HEAD -- copycat/` **有輸出 = 後端 code 比跑著的新,該重啟**。啟動 banner 也印同一份(`copycat server build <sha> [+dirty] started_at=…`)。**「改了沒生效」先查這條再查 code** —— 2026-07-29 曾為此誤查一輪(:8721 的 `openapi.json` 根本沒有那條 route)。**2026-08-05 起 dev(vite)下這條已自動化**:nav 右緣 amber「版本落差」膠囊亮 = 同一判法(middleware range 判別含 `-- :/copycat` 過濾)命中,uncommitted 改動仍不可測 | repo root |
| Frontend dev / 測試 / build | `npm run dev` / `npm test` / `npm run build` | frontend/ |
| Config 實驗對照 | `.venv\Scripts\python -m copycat compare out/A out/B` | repo root |
| 日線回補(位階特徵前置,一次性) | `.venv\Scripts\python -m copycat backfill-daily` | repo root |
| T 日跟多回測:特徵 | `.venv\Scripts\python -m copycat tday-features` | repo root |
| T 日跟多回測:搜索+報告 | `.venv\Scripts\python -m copycat tday-search --report-date <YYYY-MM-DD>`(報告 → docs/evidence/) | repo root |

完成前要過的 gate:`pytest -q` + `ruff check` + `pyright` + `copycat validate` 全 PASS(validate 需先跑過 four/five 兩份 replay)。venv = Python 3.13(`py -3.13 -m venv .venv`;`py` launcher 預設 3.14,別直接用)。動到 frontend/ 另加:`npm test` + `npx tsc -b` + `npx eslint src`(在 frontend/)。

**部署前置(Touchance 特性)**:

Touchance 4.0 是 **Windows 桌面 app**,Python client 透過 **ZMQ** 跟它通訊(**實測 OpenAPI 登入 port = 50774**,SubPort 動態發配;官方文件的 51171/51141 與現版不符,2026-07-18 實測)。意味著:

- 後端 host 必須是 **Windows + Touchance 常駐開啟 + ZMQ ports 對 localhost 通**。
- 不是 headless Linux server 友善,**Docker 化困難**(要先驗證跨 host ZMQ 是否可用)。
- 預期實作初期都在本機跑(Touchance + FastAPI backend + React frontend 同台 Windows);若要拆出,先確認 ZMQ 跨網段穩定度。
- 這個 repo 一啟動就被 Windows 綁住(scope 純 Touchance),Linux Docker 不在規劃內。

`.env` 需要的 secret:
- `FINMIND_TOKEN`(沿用 trash-cmoney,補期貨 / 選擇權 chip 用)
- `DISCORD_WEBHOOK_URL`(Discord 通知,選配;未設時 notify 層 no-op。驗收:`python -m copycat notify-test`)
- `DISCORD_BOT_TOKEN` + `SIGNALS_DISCORD_CHANNEL_ID`(2026-08-04 沿用 treading-king bot;
  個股訊號推送 + `/watch` slash 指令。token 未設 → bot 降級不啟動,推送 fallback webhook。
  同 application 的 command sync 會覆蓋 treading-king bot 舊指令 — 該 bot 已退役,可接受)
- `FRONTEND_ORIGIN`(CORS)
- Touchance 訂閱授權碼 / 帳號 — 實裝時補確切變數名
- 群益 Capital(2026-07-28,沿用 treading-king 值):`CAPITAL_USER_ID` / `CAPITAL_PASSWORD` /
  `CAPITAL_FULL_ACCOUNT`(證券帳號;期貨帳號登入後 GetUserAccount 自動發現)/
  `CAPITAL_ENV`(test|prod;test 沙盒群益端未開通,登入 1097 → 降級 status=error)/
  `CAPITAL_DLL_DIR` / `CAPITAL_ORDER_ENABLED`(false=總開關全擋)/
  `CAPITAL_MAX_QTY` / `CAPITAL_MAX_AMOUNT`(未設/0 = 不限,user 拍板)/
  `CAPITAL_AUDIT_DIR`(選配,預設隨 TXO_AUDIT_DIR;審計檔 capital-YYYYMMDD.jsonl)。

---

## 2. Python 風格(專案特化)

整節移至專案 skill `backend-conventions`(2026-07-28 瘦身,neigui 同款);寫或改任何 `.py` 前先讀該 skill。

---

## 3. React / TypeScript 風格

整節併入專案 skill `frontend-conventions`「React / TypeScript 基本風格」節(2026-07-28 瘦身);寫或改 `frontend/` 前先讀該 skill。

---

## 4. 跨檔契約

- **API error JSON shape**:`{ "detail": { "error": "<code>" } }`,frontend client 解 `detail.error`。改契約 = 同時改兩邊。
- **Refresh 慣例**:URL query `?refresh=true` → backend 跳過 cache、重抓 upstream。frontend 一律走 `queryClient.invalidateQueries` + refetch with refresh flag。
- **Cache version bump**:`_CACHE_VERSION`(在各 service 內)+1 即作廢所有舊 cache,不需手動清。

---

## 5. 資料源

**確認結果(2026-06-26 deep-research + targeted Touchance fetch,完整報告 `docs/research/2026-06-26-dq4-and-broker-api-survey.md`)。**

---

### 主資料源 = Touchance 4.0(達錢 4)

- 身份釐清(≠ 任何券商產品)與 ZMQ port 事實見 §0 與 §1 部署前置,不重述(2026-07-28 去重)。
- User 持有最高會員訂閱(綁帳號不綁 repo,事實留 user memory `touchance-account-tier`)。
- 涵蓋:**國內外期貨即時行情** + 歷史(1 分 K 一年、日 K 十年)+ 帳務查詢。~~下單抽象~~ **達錢 4 無下單功能(2026-07-21 實證,§8),下單全走群益 Capital(2026-07-28 拍板,§0)** — 2026-06-26 survey 的「下單抽象 + 券商授權前提」記載已被實證推翻(2026-07-28 更正)。
- 官方 GitBook:https://touchance-1.gitbook.io/touchance/
- 官方 Python wrapper:GitHub `TOUCHANCE/TCPY`
- 環境前置:`pip install zmq` + Touchance Windows app 常駐 + 與 ZMQ ports 通。

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
- **Touchance Python API = ZMQ**,**不是** REST/WebSocket/COM/DDE/RTD。實測登入 port 50774(SubPort 動態);且現版 `SUBQUOTE REALTIME` 必帶 StartTime/EndTime(官方 wrapper SubQuote 未帶會 fail,見 docs/research/2026-07-18-txo-chain-probe.md)。寫 client 時記得是 `pyzmq` + asyncio,不是 `httpx` / `aiohttp`。Async 整合模式跟 trash-cmoney 既有 httpx pattern 不同,新接 service 不要照貼。(Trigger:寫 `services/touchance_*.py`)
- **Touchance 下單仍要券商授權**:Touchance 本身只是抽象層,實際送單要再向所屬期貨商申請 API 交易權限。設計下單流程(§7)時要假設「即使 Touchance 通了,期貨商那邊還可能擋」,要分開錯誤碼:`TOUCHANCE_DOWN` vs `BROKER_REJECTED`。
- **Touchance Windows app 常駐 = 部署綁定**:這個 repo 一啟動就被 Windows 綁住(scope 純 Touchance),Linux Docker 不在規劃內。寫 code 時放心用 ZMQ + Windows 路徑;若想跨 host 部署(Touchance host vs Python backend host),先實測 ZMQ 跨網段穩定度。

### 實作後沉澱

- **FinMind `TaiwanStockPrice` 無 data_id 全市場回傳含權證等**,一天 ~3 萬 rows;334 天真跑灌了 4.2M rows 進 prices.csv。`backfill_finmind` 已內建 known_ids 過濾(只收既有檔已知代碼,冷啟動空檔會 warning),別移除。(2026-07-07,Trigger:碰 backfill 或新增 FinMind dataset)
- **urllib 的 SSL read timeout 以 `TimeoutError` 拋出,不包在 `URLError`**,retry 的 except 集合要含它,否則長跑批次中途炸。(2026-07-07,Trigger:寫任何 HTTP retry)
- **prev_close 語意 = 當日 close − spread(除權息參考價),neigui 同源**;`DailyIndex.ref_prev_close` row-level 處理 spread 缺值(None → fallback 前日 close)。不要用「前一日 close」直接當參考前收。(2026-07-07,Trigger:碰漲停價/報酬率計算)
- **驗證指令別接 `| tail`/`| head` 再看結果** — pipe 會把 exit code 換成 tail 的 0,本 feature 兩次踩到(ruff 紅著 commit、backfill 崩了顯示 exit 0)。要嘛先落檔再 tail,要嘛檢查 `$?` 前不接管線。(2026-07-07,Trigger:任何 gate 指令)
- **neigui 種子事件池不可當母體**:除截止邊界(3055 的 2026-06-24 鎖板不在池內)外,實證**系統性漏收約三分之二真收盤漲停**(母體 10,900 vs 種子 3,511,抽驗 15 筆全為真漲停;2026-07-14 review 更正:早前寫「約一半」係低估)。`scan-events` CLI 已自產補全(data/events/events.csv + limitup_all 同步);引用種子池結論或做母體統計前先跑 scan-events。(2026-07-07 邊界 → 2026-07-10 漏收實證合併,Trigger:引用回測結論、算 base rate、或任何以事件池當母體的分析)
- **TC4 股票 1K 實測可回補一年以上**(2025-07-01 起回補成功,2026-07-10 實測),官方文件「1 分 K 一年」限制**僅適用期貨**。排股票歷史回補計畫時不要被官方數字自我設限,先實測邊界。(2026-07-10,Trigger:排 TC4 歷史回補範圍或評估回測期間長度)
- **FinMind `TaiwanStockDayTrading` 的 `BuyAfterSale` 欄位 'Y' 或 '＊' = 僅可先買後賣**——對先賣後買的空方策略即**不可交易**,當沖資格過濾必須把這類標記視為 excluded,不是「可當沖」。(2026-07-10,Trigger:碰當沖資格 proxy 或新增依賴 DayTrading dataset 的過濾)
- **模擬器出場 status 的入統計集合 = `fade_simulate.TRADEABLE_STATUSES` 單一定義**(收尾 review 已從 fade_pipeline/fade_optimize 兩份手動同步收斂,測試驗兩端同物件)。新增出場 status 只改這一處;曾因 guard_exit 只加一邊,最差虧損被靜默剔除 → 期望值灌水。注意 `pipeline.py`(舊 T 日 pipeline)另有自己的 `_TRADEABLE` 狀態字彙,兩者不通用。(2026-07-11,Trigger:模擬器新增/改出場 status)
- **TC4 tick 欄位語意(2026-07-18 實測,詳 docs/research/2026-07-18-txo-chain-probe.md)**:歷史 TICKS 的 `TradeVolume` 全為 0(無累積量,排序靠微秒級 `PreciseTime` + `QryIndex`);REALTIME 才有累積 `TradeVolume`(去重主鍵)。`PreciseTime`/`FilledTime` 是 **UTC**,顯示要 +8。REALTIME 五檔命名有位移:`Bid`=最佳、`Bid1`=第二檔。~~休市日期貨(FITX)不推 snapshot~~ **2026-07-20 更正:FITX 沒推播的真因是該 symbol 不存在** — TC4 symbol 樹的台指期產品碼是 **TXF**(`TC.F.TWF.TXF.*`),FITX 只出現在 Quote 的 `Security` 欄位;且 **SUBQUOTE 對不存在的 symbol 照回 Success=OK**(平台不驗證,零錯誤訊號),訂閱成功 ≠ symbol 存在,新 symbol 要先過 QUERYALLINSTRUMENT 或確認有推播。(Trigger:碰 live tick 解析、現價源、訂閱新 symbol、或任何用 TC4 時間欄位的顯示)
- **TXO 序列動態發現**:月選(TXO)第三週三到期後即從合約清單消失;週選產品碼 TX4/TX5(+TXY/TXZ 待確認別)同月並存 → 序列清單必須每次跟 TC4 查,不可 hardcode;`QUERYALLINSTRUMENT` 的 Type 實測是 `"Opt"`(wrapper 註解寫 Options 是錯的)。(2026-07-18,Trigger:碰序列選單/合約發現)
- **TC4 歷史批次回補要「先全鏈 SubHistory 再逐檔收割」**:逐檔 Sub→sleep→收 280 檔實測 ~10 分鐘,先全訂讓 TC4 平行備資料再收割 → ~2 分鐘。(2026-07-18,Trigger:寫任何 TC4 多 symbol 歷史回補)
- **純 `uvicorn` 沒有 WebSocket protocol 支援**,WS upgrade 直接 404(且錯誤訊息不會提示缺件)— 要 `uvicorn[standard]`。(2026-07-18,Trigger:新增 WS endpoint 或部署裝依賴)
- **個股 REALTIME 實測事實(2026-07-21,stock-terminal 落地)**:上市+上櫃**全掛 `TC.S.TWS.<code>` 段**(TWO/TPE/OTC 段無推播);推播自帶完整五檔+漲跌停/參考價;**試撮期(13:25–13:30)TC4 不推成交 tick**(時間窗過濾為雙保險),`TradeStatus` 值域實測 {0=正常, 1=試撮期簿更新};**盤後 fresh subscribe 會回當日收盤 snapshot**(延遲分鐘級);股票類 `QUERYALLINSTRUMENT` 無有效 Type(Stock/Stk/Sec/Equity 全 Fail),股號存在性靠「訂閱後有無推播」健檢。(Trigger:碰個股訂閱/試撮處理/盤外顯示)
- **個股期不在 Fut 商品樹但可訂閱**:`TC.F.TWF.<期交所兩碼+F>.HOT`(CDF=2330);對映靠期交所股票期貨清單頁(`copycat/stkfut_map.py` refresh CLI),**同股號標準(2,000 股)/小型(100 股)並存取契約單位大者**;推播 `SecurityName` 帶「名稱(股號)」可交叉核對。**達錢 4 無下單功能**(合作清單全期貨商),交易面另接券商 API。(2026-07-21,Trigger:期現對照/個股期訂閱/評估下單路線)
- **TC4 指數/日 K 實測(2026-07-28 盤中)**:(a) 加權指數 = `TC.S.TWS.IX0001`(REALTIME 推播含五檔/高低/漲跌停鍵);TWS 指數目錄 81 檔(IX0001-42 上市類股 + IX0100+ 特色),**櫃買指數不在 TC4 symbol 樹**(TWO/OTC/TPE/GTSM 段與 IX0043-0200 掃盡皆無)。**2026-07-29 補實證:現貨段(`TC.S.*`)只有台股 TWS 一段** —— 美股 17 段名 × {AAPL, TSM} × 3 格式 = 102 組合全 `parse failed`(AAPL 當對照:若有美股不可能全滅)、港/日/星/陸現貨 8 種亦全滅、`QUERYALLINSTRUMENT` 25 個 Type 名窮舉只有 `Fut`/`Fut2`/`Opt` 有效且零美股命中;官方訂閱層也只賣「國內期貨 / 海外期貨」兩類權限。**美股個股與美股現貨指數不在達錢 4 產品線內,訂閱等級再高也拿不到**(是沒有,不是沒找到)。(b) `QUERYINSTRUMENTINFO` 對不存在 symbol 回 parse failed = **存在性 oracle**(SUBQUOTE 照回 OK 不可靠,健檢之外的第二判法);股票/指數同段查詢會附父節點資訊(TickSize/OpenCloseTime)。(c) **股票 SubHistory `DK` 直接支援**(2330 實測 25 根日 K 解析零略過,官方文件未載;overlay 的 1K 聚合 fallback 為備援)。**2026-07-29 盤後補實證(2317,180 日曆日窗)**:DK 的 **`Open` / `Volume` 欄位名假定成立** —— 回 116 根、`o=240000`(240 元)與 `v=81973` 皆真值且 `v` 與 REALTIME 累積總量完全一致,server log 零「DK rows 解析略過」;耗時 `tf=D` 1.1s、`tf=1&days=5`(810 根 / 3 交易日)2.1s。原「只實證 H/L/C」的保留可解除,`stock_source.py` 的防禦解析與略過計數 log 保留為韌性即可。probe 工具:`spikes/index_symbol_probe.py`(--candidates 覆寫)/`index_node_probe.py`。(Trigger:訂閱指數、查 symbol 存在性、抓日 K)
- **海外指數期貨在 TC4 的取得與陷阱(2026-07-29/30 實證,realtime-correlation)**:(a) **台期交自己就有美國四大指數期貨**:`UDF` 美國道瓊 / `SPF` 美國標普500 / `UNF` 那斯達克100 / **`SXF` 費城半導體**(2023-12 上市,DK 631 根)/ 另有 `SOF` 半導體30指 —— 全在 `TC.F.TWF.*` 段,台幣計價、與台指同時段同結算。**查商品必查 catalog 的中文名(CHT 欄)不能只比對 symbol 前綴**,否則會漏(本輪連掃兩輪才發現費半)。(b) **但台期交這幾檔流動性極差**:SPF 近 60 交易日有 57 天成交 <100 口、12 天零成交 → 日 K 收盤價不是市場定價,不可用於報酬相關;道瓊/標普/納指改用 CME/CBOT 的 `YM`/`ES`/`NQ`(DK 924 根、量大數千倍),費半無 CME 對應只能用 SXF。(c) **富台** = `TC.F.SGX.TWN.HOT`(DK 929 根;`MTWN` 小富台 SubHistory 逾時空),**SGX 在台灣連假照開** → 富台 929 根 vs 台指 860 根,配對計算必須取交集日。(d) **海外期貨 DK 的收盤時點 = 該市場收盤**(美股期貨 `Time=210000` = 21:00 UTC = 美東 16:00),與美股現貨日 K 日界天然對齊。(e) **訂閱海外腿建議用全天窗**(`corr_source.py` 覆寫 `_rt_request` 為 `all_day_window()`)—— 基底 `TC4QuoteSource._rt_request` 寫死台指盤別窗,而 TC4 對訂閱一律回 `Success: OK`,窗不匹配的失效樣態會是「訂閱成功但零推播」毫無錯誤訊號,故用全天窗消除一整類風險。**但要誠實記帳:「沿用 session 窗會失效」目前是推論不是實證** —— 台指日盤窗(UTC 00–06)+ 夜盤窗(UTC 06–22)合計涵蓋 UTC 00–22,海外期貨近 23 小時交易的時段幾乎都落在其中之一,訂閱當下不會落窗外;真正的風險是「訂閱後跨過窗結束邊界(UTC 06 或 22)推播是否停止」,那需要跨邊界連續觀察才能驗,2026-07-30 日盤驗證(六腿全有推播,含 CME 三檔)只證明了全天窗這條路可行。(f) 費半 SXF 的推播密度隨時段差異極大:23:09 為 146 則/60 秒,00:55 只有 2 則/40 秒。(Trigger:接任何海外商品行情、選指數資料源、或繼承 TC4QuoteSource 寫新 source)
- **TC4 REALTIME 的 `PreciseTime` 欄寬跨交易所段不同,`FilledTime` 才是通用的(2026-07-30 實證)**:台期交(TWF)是 `HHMMSSffffff`(微秒 11–12 位),**CME / CBOT / SGX 是 `HHMMSS`**(實測 MES 的 PreciseTime 與 FilledTime 同值 `"41256"` = 04:12:56 UTC)。`stock_models._taipei_time` 的 `zfill(12)` 對海外段會把 6 位值左補成 `000000041256` → **恆為台北 08:00:00.0xx 的假時刻**,與真實時刻無關。失效樣態極安靜:tick 照樣解析成功(價量都對),只有時刻是假的 —— 相關係數只用五檔中價所以沒被咬到,江波圖是第一個依賴跨段 tick 時刻的功能,四條海外腿的 live 點全部落在盤別窗外(畫面表現為「回補到啟動時刻後就不再前進」)。任何要用 tick 時刻的跨段功能一律走 `FilledTime`(UTC HHMMSS,zfill(6);`index_engine` 對 IX0001 也是用它),缺值才退回本機時鐘。(Trigger:任何跨交易所段用 tick 時刻 / 分鐘聚合 / 時序去重)
- **TC4 1K 當日回補在 CME / CBOT / SGX / TWF 四段皆可用(2026-07-30 實證)**:六腿(TXF/TWN/YM/ES/NQ/SXF)實跑各 201–247 列 → 日盤窗內 202 分鐘、覆蓋率 100%(SXF 94.4%,稀疏腿真的沒成交)。**富台 TWN 的 1K 可用**(先前只知小富台 MTWN 的 SubHistory 逾時空 —— 那是該檔本身無資料,不能推論 SGX 段)。1K row 另帶 `UpVolume`/`DownVolume`/`UpTick`/`DownTick`(= 內外盤量),首頁固定 50 列必須走 `iter_qry_pages` 收割。兩個盤別各自完整落在單一 UTC 日 → 回補窗用「當日 UTC 全天窗」即可涵蓋。(Trigger:排任何 TC4 分鐘級回補、或評估內外盤能量副圖)
- **CME single stock futures(含 TSMC ADR)2026-07-27 上市,達錢 4 尚未上架**:55 檔美股 + 22 檔微型、現金結算、一天 23 小時交易 —— 那 23 小時交易是關鍵,代表台股盤中也會有 TSM 的連續報價(ADR 現貨在台股盤中是休市的)。2026-07-29 實測 TC4 對 `CME`/`CME_SSF`/`CME_EQ`/`CMESSF` × `TSM`/`NVDA`/`AAPL` 等 64 種命名組合全 fail(對照組 `TC.F.CME.ES.HOT` 回 OK)。上架後在 `configs/correlation.json` 的 `legs` 加一筆即可(SC-8 設計)。(Trigger:評估 TSM/美股個股資料源、或想確認 TC4 是否已上架 SSF)
- **`statistics.correlation` 是 stdlib(Python 3.10+)且夠快**:1800 樣本實測 0.15 ms、六腿五對三窗的完整 tick 6.43 ms。相關係數不必自寫增量統計量(整批重算讓「增量 vs 整批一致」恆真,免追浮點誤差上界);常數序列會拋 `StatisticsError`,catch 後回 `None`。(2026-07-30,Trigger:要算相關/共變異數而想引 numpy 或自寫演算法時)
- **長跑 pipeline 必須有進度 log**:round 1 fade-search 跑 6 小時全程黑箱,無法判斷卡死或正常。fold/arm/generation 邊界各 log 一行(logger,含完成比例與耗時),成本近零。(2026-07-11,Trigger:寫任何預期 >10 分鐘的批次/搜索迴圈)
- **TC4 同 symbol 跨 session 只推一邊**(2026-07-28 夜盤三次重啟實證):TXO runtime 已訂 `TC.F.TWF.TXF.HOT`(spot)時,futures engine 同 symbol 的 SUBQUOTE 回 OK 但**永收不到推播**(哪邊贏不確定性存在)。解法 = 訂**實際月份 leaf 契約**(symbol 字串不同即無衝突;`futures_engine` leaf fallback:resolve 已知後寬限 3s 仍零推播才補訂,換月靠跨日清 p 重武裝)。**2026-07-30 補實證:該 leaf fallback 有前提,且 futures_engine 會間歇性整段零推播** —— fallback 要先「由推播解析出契約月份」才會補訂,當**全部商品都零推播**時啟動不了。實測到的兩個相反狀態:(i) 2026-07-29 17:33 起跑的 server 到 00:50 為止 TXF/MXF/TMF 全 `p=null`、`seq=0`(期貨面板整晚壞著),同時段獨立訂閱 TXF.HOT 有 235 則/30 秒、MXF 324 則、五檔俱全 → TC4 端正常,問題在 server 內;(ii) 2026-07-30 10:24 起跑的 server 六腿(含 TXF)全部正常有值。**所以是間歇性而非必然死鎖,觸發條件未定位**(疑似與啟動時序 / TC4 session 殘留 / 先前有 process 訂過同 symbol 有關)。**新引擎不要假設「讀既有 engine 的 state 一定拿得到行情」**,那條上游可能整段空著且無錯誤訊號 —— 要嘛自己有 fallback,要嘛把「上游空著」當正常狀態處理(`corr_engine` 選後者:base 腿無資料時回 `None` 不假造)。修法候選見 `docs/next-time.md`。(Trigger:任何新引擎要訂閱既有模組已訂的 symbol、或要讀既有 engine 的 state 當資料源)
- **TC4 指數 / 期指 K 線的實測邊界(2026-07-30 夜盤,index-board)**:(a) **加權 `IX0001` 的 `DK` 確實支援** —— 5 年窗實回 **748 根**(2023-07-03 起 ≈ 3 年,TC4 端自己的深度上限),`tf=1` 的 1K 亦正常;先前 CLAUDE.md 只實證過個股 DK,指數段的疑問可解除。(b) **期指 DK 深度是 5 年**:TXF / MXF 各 **1213 根**(2021-08-02 起),比指數深一倍。(c) **指數的 DK / 1K 沒有量欄位** —— `_int_field` 缺值回 0 → 整條序列 `v=0`;若直接畫量副圖會出現一排貼底的 0 高柱,與「真的零成交」無法區分。判定量之有無要**看資料**(`any(v>0)`)不要看商品類別。(d) **期指的 1K 分鐘域是 08:46–13:45,不是個股的 0901–1330** —— 套個股那把尺會靜默丟掉開盤前 15 分(台指期 08:45 開盤跳空是看盤重點)、把 13:31–13:35 的成交錯併進 13:30 那根、再丟掉 13:36–13:45;圖畫得出來、根數也合理,沒有任何 assertion 會紅。`stock_source.parse_1k_bars(rows, domain)` 的 domain 參數就是為此而開(`FUTURES_MINUTE_DOMAIN`)。(e) 冷載入耗時實測:加權 DK 5 年窗 0.022s、期指 DK 0.026s、期指 1K 2 日 0.036s —— 遠低於個股標的的量級,不需非同步化。(Trigger:碰指數 / 期指的歷史 K 線、量副圖、或任何分鐘域轉換)
- **同 symbol 的歷史一律從「持有該 symbol REALTIME 訂閱的那條 session」問(2026-07-30 升為通則)**:先前只記了台指 `TC.F.TWF.TXF.HOT` 一例(`river_backfill` 檔頭)。加權 `IX0001` 同理 —— 它的 REALTIME 訂閱與當日 1K 回補都在 **index session**(`app.py` `_default_index_source()` 是獨立 session),從個股 session 問同一檔有把推播搶走的風險,而失效樣態是「訂閱成功但零推播」零錯誤訊號:右上角加權、大盤分時線、`/ws/index` 的 `last_minute`、watchdog stale 會同時安靜失效。新增任何歷史取用點前先問「這個 symbol 的 REALTIME 訂閱在誰手上」。(Trigger:新增任何 SubHistory 取用點)
- **群益 SKCOM 關鍵事實(2026-07-28,capital-order;詳 docs/research/2026-07-28-skcom-typelib.md)**:(a) 期權下單共用 `FUTUREORDER` struct(`SendFutureOrder`/`SendOptionOrder` 同簽名,無 OPTIONORDER);刪改減共用證券 BySeqNo 家族(帳號換期貨戶)。(b) **test 沙盒(SetAuthority(2))此帳號未開通**,登入恆 1097 — 送單面驗證只能 FakeCom 測試 + prod 安全首單(遠價 1 單位 → APP 核對 → 刪單)。(c) nQty:證券=張(treading-king prod 實戰實證)/期貨=口。(d) 期交所市價單限 IOC/FOK(ROD+市價會退單);市價 literal M 未實測,期貨平倉走限價貼漲跌停+IOC。(e) OnAccount/OnOpenInterest 欄序為未實測假定,首次 prod 登入要核對。(Trigger:碰 copycat/capital、群益送單欄位、或評估群益驗證方式)
- **worktree 內的 gitignored 依賴要「複製」不要「junction」**(2026-07-30 真踩到):`frontend/node_modules` 與 `spikes/TCPY` 都被 gitignore,worktree 一開出來就缺(前者前端跑不動、後者 `test_tc4.py` 直接紅;原並列的 `test_tc4_trade.py` 已於 2026-08-04 隨舊 trade 路刪除)。用 Windows junction 連回主 tree 雖然當下可用,但**收尾 `git worktree remove --force` 會沿著 junction 把主 tree 的目標內容一起刪掉** —— 實測主 tree 的 `node_modules`(195 項)與 `spikes/TCPY`(TC4 官方 wrapper + 2026-07-06 的 Disconnect 修補,且**不在版控**)雙雙被清空。復原路徑:`npm ci` 重建前端依賴;TCPY 從另一個 worktree / `C:\side-project\neigui\backend\data\research\five-tigers\tcoreapi_mq.py`(同 hash)/ `C:\Users\USER\Downloads\tc4_python_api_2407\` 複製回來。**正確做法 = `Copy-Item -Recurse`**(TCPY 才 22 MB;node_modules 走 `npm ci`),或先 `Remove-Item` junction 本身再 remove worktree。(Trigger:開 worktree 做前端/TC4 相關工作,或收尾清 worktree 前)
- **`git worktree remove` 會把 `.claude/mod/<slug>/` 的 artifact 一起刪掉(2026-07-30 真踩到)**:`.claude/` 是 gitignored,worktree 內產出的 `change-spec.md` / `current-state.md` / review JSON **從未進版控**,收尾移除 worktree 時連同消失 —— 其他每一輪都留在主 tree,只有這輪事後才發現缺口(靠對話記錄重建,逐字排版已失真)。**在 worktree 做 /feat /mod 時,artifact 一開始就寫到主 tree 的 `.claude/<flow>/<slug>/`**(reviewer dispatch 吃絕對路徑,寫哪邊都一樣),或至少在 `git worktree remove` 前 `Copy-Item -Recurse` 出來。同理適用任何 gitignored 的產出(截圖若放 `docs/specs/` 有版控則安全)。(Trigger:在 worktree 跑流程 command、或收尾清 worktree 前)
- **worktree 內直跑腳本會靜默 import 到主 tree 的 code**(2026-07-30 真踩到):venv 裝的是 editable copycat(`__editable__.copycat-0.1.0.pth` 釘死 `C:\side-project\copycat`)。`pytest` 不受影響(pyproject `pythonpath=["."]` 讓 cwd 優先)、`python -c` 也不受影響(`sys.path[0]` = cwd);但 **`python <dir>/script.py` 的 `sys.path[0]` 是「腳本所在目錄」**,worktree 內的 probe / repro 腳本因此 import 到**主 tree** 的 `copycat`。失效樣態極安靜:腳本正常跑完、只是驗的是別份 code —— 本輪據此一度誤判「修好的 code 沒生效」。worktree 內任何直跑腳本開頭都要 `sys.path.insert(0, <repo root>)`。另:`git worktree remove` 若有 process 還開著 worktree 內的檔案(例:server stdout 導向那裡)會以 `Invalid argument` 失敗,且**會先刪掉 `.git/worktrees/<name>` 中繼資料再失敗** → 收尾要 `git worktree prune` + 手動 rmdir。(Trigger:在 worktree 寫直跑腳本、或收尾清 worktree)
- **server 不載 dotenv 檔**:runtime 讀設定一律「`name in os.environ` 即用(含空字串 = 未設,可壓制 .env)→ 否則 repo root .env」逐 key fallback(capital/factory 慣例;cli/notify 舊慣例是「僅未設才 fallback」,下單開關類安全 key 必須用新語意)。讀 .env 用 `utf-8-sig` + never-raise(Windows BOM 會讓首 key 靜默失效 — 真踩過)。測試側 `tests/conftest.py` 全域中和 dotenv + delenv CAPITAL_*(否則開發機真憑證流入測試,最壞載真 SKCOM DLL → segfault,實測過)。(2026-07-28,Trigger:新增任何 env 設定讀取或 env 相依測試)

- **rollover stage1/stage2 可在同一同步區塊內連發(快路徑),掛兩段通知的模組不能假設中間有 await(2026-08-04 stock-signals 實證)**:`_handle_quote` 的快路徑(週六補市日 / checkpoint 沒跑)會在同一則 quote 內接連跑 stage1 → stage2,任何「stage1 排非同步預備、stage2 消費」的設計在此路徑下預備必為空;更陰的是預備 job 事後完成的**殘留**會被下一次快路徑誤當有效 → 用日別標記(basis_date)驗證,不符即丟。訊號 CDP 基準的 staged swap 就是這樣修的(design review MFS-2)。(Trigger:掛 rollover 兩段通知、或任何 stage1 預備/stage2 消費的設計)
- **盤中不要起第二台連 TC4 的後端(2026-07-31 升為紀律)**:同 symbol 跨 session 只推一邊(見上一條),第二台會靜默搶走跑著那台的推播 —— 失效樣態是「原本好好的面板突然全空,而兩邊都沒有錯誤訊息」。**驗前端改動只起 vite dev server**(proxy 已指 8721,零新增訂閱);**驗後端 HTTP 層(route 形狀 / 非行情 endpoint)則用 fake source + 另一個 port**,那條路完全不碰 ZMQ,盤中也安全(本輪驗 `/api/health` 即如此)。同理:**不要為了看新 code 就重啟跑著的 server** —— 櫃買當日序列是純 in-memory,重啟即歸零(§8 另有條目),真要重啟先確認那份資料不再需要。(Trigger:盤中要驗證任何後端改動)
- **TC4 在鎖漲跌停時會於簿的第一檔推「市價單佇列」,價格欄是 `0`(2026-07-31 實證)**:`0` 不是價格,是「這些委託沒有限價」。它會**同時**打穿三處而且全部靜默:(a) `derive_side` —— 鎖漲停(ask 側空、`bids[0]=(0,N)`)時 `price <= 0` 恆假 → 每筆成交判 neutral,實測 2327 國巨全日 5450 張成交 `cum_outer = cum_inner = 0`、內外盤副圖整片灰、外盤比分母 0 算不出來;鎖跌停對稱地 `price >= 0` **恆真** → 一律判 outer(方向碰巧對但 bid 側判定被整條短路);(b) 任何 `bids[0][0] === upper` 形式的鎖停判定 → badge 永不出現;(c) 前端直接把 `0` 印在五檔上,看起來像有人掛 0 元。修法是**只在消費端過濾**(`_best_limit_price` 往下找第一個 `price > 0` 的檔位),簿本身要原樣保留 0 檔位 —— 五檔與閃電梯得把它顯示成「市價」。**另一個更隱蔽的層次**:歷史 TICKS row 只有單一 `Bid`/`Ask` 欄沒有第二檔可退,而 `StockDayState.apply_backfill` 會先 `reset()` 再用回補重放 → **live 期間判好的值每次切檔都被洗掉**;那層要靠 `relabel_locked_side`(鎖漲停 + 對手側整個不可得 → 內盤,鎖跌停 → 外盤;這是漲跌停制度下的恆等式不是猜測)。**還有第四處(2026-07-31 補)**:任何**對整份簿做聚合**的地方 —— 總量列、量 bar 的歸一分母。市價量混進去會讓同一個欄位「鎖停日 = 市價 + 4 檔限價、平常日 = 5 檔限價」(市價那格吃掉 `DEPTH` 的一格),定義隨日子變、跨日跨股比較**靜默失真**;量 bar 更慘,市價佇列可以是限價量的數倍,五根限價 bar 會一起被壓成看不見的短樁。修法同上(消費端過濾成 limit-only),但**市價量要獨立顯示不可只留 hover** —— 鎖板日「無限價排隊多少張」正是 §0a 鎖板品質的核心訊號。另注意排除市價後 `maxQty` 變小,市價列自己的 bar 需夾制(2327 實測算出 170%)。(Trigger:碰內外盤判定、五檔顯示、鎖停偵測、任何拿 `book.bids[0]` 當最佳價、或任何對整份簿做 sum/max 的地方)
- **`derive_side` 與回測的內外盤是兩條獨立鏈路(2026-07-31 釐清)**:`derive_side` 只存在於 `copycat/live/stock_models.py`;回測(`backtest/fade_*.py`、`data/models.py`)用的是 TC4 **1K row** 的 `UpVolume`/`DownVolume`/`UnchVolume`(`Bar1K`),兩者無呼叫關係。改 live 的判定**不影響任何回測口徑** —— 本輪一度以「共用口徑」為由把修法判成 trap,grep 後推翻。(Trigger:評估改動 live 內外盤判定的 blast radius)
- **Tailwind 的 `display` utility 會蓋掉 UA stylesheet 的 `dialog:not([open]){display:none}`(2026-07-31 真踩到)**:author 層永遠贏瀏覽器層。`<dialog>` 的 className 一旦帶 `flex`(或任何 display utility),**關閉的 dialog 照樣佔版面** —— 實測是一個 896×480 的空盒子壓在圖表上,而且因為內容做了 `{open ? … : null}` 所以是**空盒子**,更難被理解成「Dialog 開著」。828 個既有測試全綠:jsdom 的 `HTMLDialogElement` 是空 class、測試環境也不載入 Tailwind CSS,computed `display` 永遠測不到。修法是讓 display 跟著 `open` 切,且**用 prop 選 class 不用 Tailwind 的 `open:` variant** —— variant 產出的 class 字串恆定,測試只能斷言「有這個 class」,回歸時抓不到。另外必須補 `onClose` 把 prop 拉回同步:瀏覽器對 modal dialog 的原生 cancel/close 擋不掉(`stopPropagation` 只擋 React 合成事件),否則元素關了 prop 沒關,同一個 bug 換形態復發。(Trigger:碰 `<dialog>` 的樣式、或任何靠 UA stylesheet 預設行為的元素)
- **SVG `fill` 是 presentation attribute,優先權低於任何 CSS 宣告**:要用 `<pattern>` 填色就**不能**同時留 `fill-*` class 當「保險」,Tailwind 的 `fill:` 會直接蓋掉 pattern → 畫面退回實心色而**零錯誤訊號**(同 `url(#…)` 解析失敗完全靜默那一類坑)。另 `<pattern>` 必須 `patternUnits="userSpaceOnUse"`:`objectBoundingBox` 會讓 tile 被每個 rect 各自拉伸,270 根不同高度的柱子會長出 270 種紋理密度;窄元素(本例柱寬 ~2.5px)還要在 tile 內先鋪一層底色再疊線條,否則整根可能落在空白帶上被畫成透明 = 看起來「沒有量」。(Trigger:用 SVG pattern / gradient 填色)

(寫入規則參考 trash-cmoney CLAUDE.md §8。)
