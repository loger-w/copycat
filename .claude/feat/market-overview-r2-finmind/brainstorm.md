# Brainstorm — 台股綜合 R2:FinMind 管線搬移 + 家數帶 + 騰落線

日期:2026-08-06
來源:總 spec `docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md` §5 Round 2
(D-1~D-7 已拍板不重議;user 指示「照 §5 Round 2 做,open questions 2、3 在 Phase 0/1 拍板」)
+ R1 handoff `.claude/feat/market-overview-r1-tab/handoff.md` §4。

**分流判定記錄**:已成形方案 — 條件 1 中(spec 指名資料流 / 搬移來源檔 / UI 形式)、
條件 2 中(open questions 2、3 為可拷問決策點)。規格來自 user 拍板文件 → 預核准替代
條件成立(auto.md),決策逐題 `[auto-default]`,無方向性抉擇(open questions 由 spec
顯式委派本輪拍板)。

---

## 1. 目標

把 neigui 的全市場 FinMind 管線(universe snapshot + 純函式 compute_breadth)搬進
copycat server,供台股綜合 tab 顯示:
- **家數帶**:上市/上櫃 × 漲停/上漲/平盤/下跌/跌停(五桶互斥)。
- **騰落線**:當日家數差分鐘序列(重啟不歸零)。
- 這是 R3(漲跌停列表)/ R4(類股強弱、事件流)的管線前置。

## 2. 拍板決策(grilling 決策樹)

### Q1(= spec open question 2a)FinMind HTTP 層:stdlib urllib vs httpx?
`[auto-default: stdlib urllib(同步 fetch + asyncio.to_thread) | reason: copycat runtime
stdlib-only 慣例;mis.py 同款 pattern 已產線驗證(5s poll、to_thread、逐項 except 列舉、
TimeoutError 獨立列);poller 每 10s 一個 request 無並發需求,httpx 引依賴零效益。
neigui 是 httpx/async — 搬「邏輯」不搬 HTTP 層(handoff §4 明文)]`

### Q2(= spec open question 2b)poll 間隔預設?
`[auto-default: 10s,configs/market.json 可覆寫 | reason: handoff 建議 10s(360 req/hr);
兩專案共用同一顆 FINMIND_TOKEN(Sponsor 6000 req/hr),copycat 360 + neigui 現用合計
遠低於配額;5s 增益有限(FinMind snapshot 上游更新頻率非 tick 級)]`

[amendment 2026-08-06: design review R16 — 覆寫檔名拍板 `configs/breadth.json`
(非本題原寫的 market.json),與 breadth_config.py 同名可尋]

### Q3(= spec open question 3)breadth WS 併入 index WS 還是獨立?
`[auto-default: 獨立 /ws/breadth + 獨立 breadth_engine | reason: spec §3 失效域隔離原則 —
FinMind 掛掉只影響家數/列表/類股,TC4 系(index_engine)零改動 = regression 面最小;
推播節奏不同(breadth 10s vs index 1s throttle);server/ws.py relay helper 讓新 WS
邊際成本極低(ws-zombie 教訓已收斂在 helper)。spec 已顯式把此決策委派本輪,
前後端同 repo 同輪落地,非跨系統契約]`

### Q4 universe 過濾要不要整套搬(sector_map 白名單 + ETF/權證/處置股)?
`[auto-default: 整套搬 | reason: SC-1 要求家數十個數字與 neigui 同時刻一致 —— 兩邊
universe 定義不同數字必不等。需搬:_dedup_sector_map(含 _PRIMARY_INDUSTRY_OVERRIDE)+
_build_type_map + _build_name_map + classify_stock_id + filter_universe +
處置股清單 fetch(TaiwanStockDispositionSecuritiesPeriod,24h TTL)]`

### Q5 sector_map / 處置股清單要不要落檔 cache?
`[auto-default: in-memory 24h TTL,不落檔 | reason: 重啟重抓成本 2 個 request(vs 配額
6000/hr)可忽略;copycat 無 neigui utils/cache 基建,為 2 req 搬一層 cache 不划算;
盤中不重啟是既有紀律。universe snapshot 同樣不落檔(10s 就重抓)。唯一落檔 =
當日家數分鐘序列(SC-2 防重啟歸零)]`

### Q6 騰落線序列的儲存形狀?
`[auto-default: 每分鐘存十桶 counts 全量(twse/tpex × 五桶),騰落 net 由前端算 |
reason: 270 分鐘 × 10 int 極小;存 counts 讓 R3/R4 與未來(分市場騰落、漲跌停家數
時間序列)零成本復用;net 定義(含不含 limit 桶)留前端一行運算,改定義不動後端]`
- 騰落線顯示定義:net = (limit_up + up) − (down + limit_down),上市+上櫃合計一條
  `[auto-default | reason: 標準騰落定義把漲停計入上漲;家數帶已分市場,線圖合計一條
  資訊密度剛好]`

### Q7 rows 全量(R3 前置)這輪曝不曝露?
`[auto-default: engine 內存 rows(compute_breadth 原樣輸出),REST/WS 本輪不帶 rows |
reason: WS 每 10s 推 ~1000 rows 是無消費者的頻寬;R3 接列表時再開 rows 曝露面,
引擎層已備好零改動]`

### Q8 FINMIND_TOKEN 缺席時的行為?
`[auto-default: breadth 引擎不啟動 poller,REST/WS 回 unavailable 態,前端家數帶顯示
「FinMind 未設定」;server 照常起 | reason: notify.py「未設 no-op」慣例;token 是新
選配依賴,不得讓既有 TXO/個股/指數功能因它缺席受影響。env 讀取走 capital/factory
慣例(os.environ 含空字串壓制 → repo .env fallback,utf-8-sig + never-raise)]`

### Q9 poller 盤中窗口 gate?
`[auto-default: 台北 08:55–13:40 內才 poll;啟動時(任何時刻)先 fetch 一次填現值;
窗外不打 FinMind | reason: 省配額 + snapshot 窗外不更新;08:55 起涵蓋試撮、13:40 收
到收盤末筆(FinMind tick 到 13:30,buffer 10 分鐘吸收上游延遲)。序列只在「row 的
tick date == trade_date 且分鐘鍵在域內」時 append,盤後啟動的一次性 fetch 只填
scalar 不污染序列]`

## 3. 成功條件(SC gate)

- **SC-1 家數對照一致**:盤中同一時刻,copycat 家數帶十個數字(上市/上櫃 × 五桶)與
  neigui MarketBreadthPanel 一致(容差 = 同分鐘內取樣差,逐格差 ≤ 該分鐘兩次 poll 的
  變動量;精確判準 = 以錄製 fixture 餵兩邊 compute 層數字全等)。
  驗證:pytest `test_breadth_parity`(把 neigui universe fixture 餵 copycat
  compute_breadth,與 neigui market_today.compute_breadth 輸出全等)+ 盤中兩邊畫面
  同分鐘截圖逐格比對。
  **驗證窗口:盤中(fixture 層 anytime)**;窗口外降級 = fixture 全等 + 盤中對照
  記 pending 待下一交易日。
- **SC-2 重啟序列不歸零**:server 重啟後騰落線當日序列保留(當日 JSON 落檔 restore)。
  驗證:pytest(落檔→新 engine 載回→序列等值);real-env = 盤後真實重啟(盤中不重啟
  紀律),`/api/market/breadth` 序列筆數重啟前後一致。**驗證窗口:anytime(real-env
  排盤後)**。
- **SC-3 失效域隔離**:FinMind 連續失敗時,家數帶顯示 stale 標記(前值保留),
  且指數圖 / WS /ws/index 不受影響。
  驗證:pytest(fake fetch 拋錯 → state stale=true、counts 保前值)+ vitest
  (stale UI 呈現)+ real-env fake 注入(--verify 模式 port 8722,不碰 ZMQ)。
  **驗證窗口:anytime**。
- **SC-4 UI 畫面可指認**:綜合 tab 中段(雙指數圖之下)出現家數帶 —— 上市/上櫃兩列,
  每列五格依序「漲停/上漲/平盤/下跌/跌停」,漲停格紅底醒目、跌停格綠底醒目(台股
  紅漲綠跌慣例);其下騰落線圖(x=分鐘 09:01–13:30,y=漲跌家數差,0 軸可見)。
  驗證:AI 以 claude-in-chrome 開 vite dev 截圖對照本表述 + user 過目雙層。
  **驗證窗口:anytime(數字跳動需盤中;盤後顯示末值即可核版面)**。
- **SC-5 文件債**:CLAUDE.md §0 補 FinMind 例外記載、§1 .env 補 FINMIND_TOKEN;
  驗證:`grep -n "FINMIND_TOKEN" CLAUDE.md` 兩處命中(§1 表 + secret 段)且 §0 例外
  段提及 R2。**驗證窗口:anytime**。
  [amendment 2026-08-06: code review SPEC-7 — 實際兩處命中 = §0 結構樹(finmind_token
  模組行)+ §1 secret 段;「§1 表」原敘述不精確,grep 兩處 + §0 例外段判準不變]

## 4. Edge cases

1. **FinMind 失敗 / token 過期(402)**:counts 保前值 + stale=true;不 raise、不影響
   TC4 系(SC-3)。JWT 過期是日常事件(finmind-conventions)。
2. **處置股清單 fetch 失敗**:視為空 set 續行 + stale=true(neigui 同語意 —— 處置股
   可能漏排,警示而非中斷)。
3. **盤後啟動**:snapshot 回上一交易日資料;一次性 fetch 只填 scalar(家數帶顯示該日
   終值 + 日期),序列不 append(tick date ≠ 今日則不進序列)。
4. **盤中重啟(不該發生但要韌性)**:落檔 restore 讓序列不歸零;restore 只認同
   trade_date 的檔。
5. **change_rate null / index rows(001/101)/ ETF / 權證 / 新上市未入 TaiwanStockInfo**:
   全部排除於 universe(與 neigui 全等 —— SC-1 前提)。
6. **落檔損壞 / 版本不符**:read 失敗 → 從空序列開始 + warning(never-raise;
   `_CACHE_VERSION` 慣例)。

## 5. Out of scope

- 漲跌停**列表**(rows 曝露面)→ R3。
- 類股強弱(sector_rotation)、訊號事件流、breadth diff 事件 → R4。
- compute_breadth 以外的純函式(index_strength / cap_tiers / sector_members)**不搬**
  —— R4 用到 sector_rotation 時再搬(scope 紀律:不為未來可能先搬)。
- 大盤級衍生訊號(騰落背離)→ next-time(總 spec non-goal)。
- neigui 端任何改動(唯讀參照)。
- 期貨 tab / 個股 tab 零改動。

## 6. 執行約束(跨輪掃描 — R1 handoff §4 + 總 spec §6 + R1 brainstorm)

- 搬**邏輯與測試**,不整檔貼(neigui 是 httpx/async + 自家 cache utils)。
- 新 WS 一律走 `server/ws.py` relay helper(ws-zombie 教訓)。
- 當日序列必須落檔(櫃買序列重啟歸零教訓)。
- 盤中不起第二台連 TC4 的後端;HTTP 層驗證用 `python -m copycat.server --verify`
  (fake source + port 8722);前端驗證只起 vite dev。
- FinMind poller 活在同一 server process → prod 生效需重啟,排盤後。
- 寫 .py 前讀 `backend-conventions`;寫 frontend 前讀 `frontend-conventions` +
  `frontend-testing`;騰落線圖過 `dataviz` skill;FinMind 接入照 `finmind-conventions`
  (Bearer header、service module wrap get_finmind 的 patchability 慣例對應本專案 =
  module-level fetch 函式可注入)。
- 收尾 rebase 撞 `docs/next-time.md` 時先 grep 同根因條目再新增。

## 7. 規模分流

**L**:≥5 檔(backend client + 純函式 + engine + app 接線 + 前端元件×2 + hook)、
跨前後端、新外部依賴面(FinMind)。輪數同 M(2026-07-26 制)。
