## 2026-08-24(fix/futures-bars-gap 收尾留尾)

- [ ] **非交易日「當日段」查詢仍白付 10s**(review C1,刻意不對稱):週日/假日開站時
  today 段照發、15s TTL 節流;日曆錯標風險考量不套過濾。若之後嫌 log 吵或假日看盤卡,
  候選 = today 段接 resolve_trade_date(與 R3/N089 盤前冷啟動案同一塊)。
- [ ] **連假首日無夜盤且為窗尾唯一可能日 → 仍重複探測**(review C2,2026-02 春節形狀):
  要收得動 put_hist_range last_seen 防護(P1-2 取捨),屆時一併評估。

## 2026-08-22(日間鏈 R1–R10 review 留尾;結論 `docs/superpowers/specs/2026-08-22-daytime-chain-review.md`)

P0/P1 與四輪小批已全數出貨(PR #88 欠帳計數 / #89 VWAP 避讓 / #90 R8 留尾 / #91 calendar+tape_omitted;
prod 8721 = 6adf20d9、dist 已重建)。

**待 user 過目 / 盤中觀察(真環境無法刻意觸發,以測試代證的五項)**:
以下為本次不動的 P2:

- [ ] **VWAP 標籤寬度 index 態低估**(2026-08-22 mod/vwap-label-avoid review P2):`StockIntradayChart.tsx` VWAP 文字硬編 `fmt`
  不吃 `priceText`,加權 `24283.54` 實寬 ≈45px > `VWAP_LABEL_W`=40 → clamp 字尾溢右緣帶(既有)+ 新 obstacle 判定多一道 ≈5px 誤判窄帶。
  修法 = VWAP 文字走 priceText 或寬度依 mode 取值。
- [ ] **VWAP 就地標籤 × 極值標記文字不互相避讓**(同上 review P2):兩者都「不可動」,日高/低落在盤末最後幾分鐘且價位≈VWAP 時疊印仍可達。
- [ ] **VP 圖層在 tapeOmitted 時的佔位**(2026-08-22 mod/calendar-poll-tape-omitted out of scope):群組切單檔首 paint VP 空,
  與「無成交」同形;可沿 `accum.tapeOmitted` 讓 VP toggle 區印載入中。
  **user 附註(2026-08-24):顯示載入中時 UI 不得跑版,排版要固定(佔位同尺寸)。**
- [ ] **R1 超容 clamp 全堆界邊**:`lib/stock-intraday-svg.ts:643-666` dropOverflow=false 時上緣標籤被
  clamp 成完全同 y(測試字面量 `[4,4,4,4,10,20,30]`),4×4 圖牆 capacity 6 / n=7 會踩到;改成界內等距壓縮。
- [ ] **R2 OrderPanel kind 單向靜默收斂**(`OrderPanel.tsx:66`):估價暫缺(WS 快照空窗)時市價翻回限價且不復原;
  改回 disabled 送出鈕或估價回來時還原。
- [ ] **R2 StockChart 停用 pill 新增 cursor-not-allowed**(`RadioPills.tsx:84` vs `StockChart.tsx:169`,視覺零變偏差);
  `RadioPills.test.tsx:260/276` onInteract 改 `toHaveBeenCalledTimes`。
- [ ] **R3 toast 合併與 `groupSignals` 不等價**(`useSignalAlerts.ts:187` 全索引 vs 相鄰)→ hook 內補註解;
  `formatToastText` 只剩測試在用要標明;`ToastStack.tsx:29` 比照 B3 clamp;背景 >5 分鐘 intensive throttling
  首則延遲待 user 實測。**2026-08-24 拍板:不改成一致(兩面用途不同、差異僅極端交錯可見),補註解即可。**
- [ ] **R4 `RightRail.tsx:285` / `futures-ladder.ts:156` 註解「後端會 400 BAD_TICK」不實**(平倉路由不過
  `_require_legal_tick`,前端 edgeOf 是唯一守門)→ 改口;`WatchlistSidebar.tsx:334` `to` 未變時回同 reference;
  補兩處邊價顯式等值 lock;作廢態給視覺回饋。
- [ ] **R5 封關夜近似誤差**(次一營業日休市的夜仍空 churn,方向安全)獨立開條;`river_state.py:72` clamp
  守門改名次小者贏需 per-offset rank(與 TQ-8 同設計);跨午夜表補週五 23:00 / 週六 23:00 / 週日 01:00 / 週一 08:50。
- [ ] **R6 膠囊不讀 `years_loaded`**(日曆過期零提示);盤前 hub 聯集 vs 標題 trade_date 落差歸 R3b。
- [ ] **R7 欠帳窗續命**(2026-08-22 round-2 review P2):`abandon()` 把單一 `_stale_until` 推到 now+20 會替所有未清欠帳續命
  (profit/OI 段兩次 abandon 相距 60s,第 1 筆早該過期)→ 多吞一次合法空回應。正解 = 每筆欠帳各自 deadline(deque),或 abandon 時先剔除已過期。
- [ ] **R7 P2 三條**(profit 段 `000` 表頭先關窗已由 2026-08-22 fix/balance-collector-owed-count「rows 不動欠帳 + 吞終止符清 _last_feed」一併消滅):吞終止符 WARNING 帶
  collector 名;`_set_status("ok")` 改專用 clear 不走 reset(`client.py:240`);`_query_open_interest` 無期貨
  帳號提前 return 不清 `_oi_abandoned`(`client.py:467`)。
- [ ] **R8 `fetch_daily_bars` AND → 只看 `fb_timed_out`**(`stock_source.py:753`;`test_dk_ready_but_empty_plus_1k_timeout_returns_empty`
  鎖住的是窄路徑錯誤行為,事前標該變);期貨 K 線三態 status 通道(已有條)。
- [ ] **R9 `phase` / `attempts_max` write-only**(`engine.py:251`,註解引用不存在的 UI 症狀);`buffer is None`
  路徑 phase≠status 無測。〔`handover.attempt` 與 `tape=0` 契約已於 2026-08-22 mod/calendar-poll-tape-omitted 登記 CLAUDE.md §4〕
- [ ] **R10 `corr_config.py` 預設仍是六腿,不只 logger 文案**(2026-08-24 盤點更正):`DEFAULT_CONFIG`
  (`corr_config.py:59-68`)legs 只有 TXF/TWN/YM/ES/NQ/SXF、缺 NK225M,而 `configs/correlation.json`
  已 7 腿 → 設定檔壞掉退回預設時江波圖/相關係數會**真的少一腿**;`:97/100/104/108` 四條 logger
  「改用預設六腿」文案同批。→ 🔴 微幅,下次動 corr_config 帶走(DEFAULT_CONFIG 補 NK225M + 文案改「預設腿」)。

## 2026-08-21(refactor/housekeeping-batch-2026-08-21 R10 留尾)

- [ ] **全站 `localStorage` get/set 收斂到 `lib/storage.ts::readLocal` / `writeLocal`**(/mod)。
  先例已有、但只做在單一模組:`lib/fut-chart-mode.ts::initialFutChartMode` / `persistFutChartMode`
  兩支都包 try/catch,註解也寫明理由(「在 `useState` 初始器裡跑,拋出去就是整頁白屏」)——
  問題是同一套 try/catch 每個呼叫端各抄一次,漏抄的那份零訊號。
  **散落規模(2026-08-24 重 grep,不含測試)= 45 處,分佈 14 個檔(08-21 記 13 檔,新增 `StockPage.tsx`)**:
  `App.tsx` / `RightRail.tsx`(`initialTab()`)/ `MarketPane.tsx` / `RiverPanel.tsx` /
  `LimitListSection.tsx` / `GroupGridView.tsx` / `StockChart.tsx` / `StockPage.tsx` / `WatchlistSidebar.tsx` /
  `useChartToggles.ts` / `useSignalSound.ts` / `fee-discount.ts` / `fut-chart-mode.ts` /
  `stock-view.ts`(判準 `grep -rn "localStorage\.\(get\|set\)Item" frontend/src`,不寫死行號)。
  失效面:Safari 私密視窗 / 企業政策鎖儲存時,光是**存取** localStorage 就拋 → 讀取端在 render
  路徑上 = 白屏(全 frontend 零 ErrorBoundary);quota 滿時 `setItem` 拋 → 使用者操作中途炸掉。
  **紅測試先行**(這是升成 /mod 而非 🔵 順手批的理由):(a) `getItem` stub 成「存取即拋」→ 元件
  仍掛得起來且退回預設值;(b) `setItem` stub 成拋 `QuotaExceededError` → 呼叫端不炸。
  承接 2026-08-14 mod/overview-subtabs 節的舊條(已標作廢改指本條);2026-08-06 節
  「`MarketPane.tsx` 七個 localStorage 呼叫點裸奔」是同一批,動工時一併帶走。
- [ ] **`outOfDomainLevels` 的邊界案 `p === yTop` / `p === yBottom` 無測試**(既有,R10 review T-4):
  `index-chart-svg.test.ts` 只有「明顯域外(±50~100 萬)/ 明顯域內」兩組,價位**恰好落在域端點**時
  沒有任何 assertion 釘住。現行實作是嚴格不等式(`p > yTop` / `p < yBottom`,`lib/index-chart-svg.ts:48`)
  → 端點值算**域內**、不掛牌;改成 `>=` 就會多掛一顆而全套照樣綠。補 2 案即可(純測試,🟢)。

## 2026-08-21(bug/history-timeout-propagation code review round-1 留尾)

- [ ] **F10:`stock_source.fetch_daily_bars` 的 1K fallback 沒有縮窗**。同檔的
  `fetch_bars_range_tagged` 對 DK 空的 fallback 會把視窗縮到 `_OHLC_FALLBACK_WINDOW_DAYS`
  (避免 4.5× 量級放大,R2-7),`fetch_daily_bars` 兩段卻都用整個 `_DAILY_WINDOW_DAYS`。
  兩段各自的 deadline 已收到 10s,所以不是延遲問題,是**收割量**問題(DK 不支援的股號
  每次 overlay 都整窗拉 1K)。要動之前先量一次真實列數,別憑感覺調窗。

## 2026-08-21(mod/overview-narrow-pane-legibility B1 留尾)

- [ ] CandleChart figcaption(`120 根 / 高 / 低 / 期間`)在 < ~320px 寬會折兩行溢出固定 `h-4`(既有,
  與上條同根)。
- [ ] `Y_TICKS = 5` 不隨 svg 高調整:1:1 後 96px 高的圖 5 條刻度 + 10px 字幾乎相接(可依高度降為 3)。
## 2026-08-20(盤後 server log 巡檢發現)

- [ ] **融券的 [25] 代碼未實證,刻意不對映**(上條留尾):首次持融券過夜時 log 會出現
  「種類標籤未知 …整列」,拿該列 [25] 值(疑 3)回填 `balance.py::_PNL_KIND_CODE` 即收工;
  在那之前融券部位的均價/打平照舊缺值(寧缺勿錯)。
- [ ] **當沖空單第二層校準:kind 歸類 + 平倉映射解鎖**(2026-08-20 user 實報空單標記方向錯;
  第一層已出貨 = 現股/融資負股數保留空方向 + 整列蒐證 warning + 平倉暫鎖):user 下一筆
  現股當沖先賣(或資券互抵)開倉期間,log 會出現「balance line 負股數…整列」與損益列的
  「種類標籤未知…整列」(若為融券態)→ 依實錄決定 (a) 負現股列歸 `daytrade_sell`(close
  映射 `("daytrade_sell", False)` 已備)還是維持 cash + 補 `("cash", False)`;(b) 該態損益列
  的 [25] 代碼與均價口徑(打平線要不要吃它)。校準後改 `test_cash_short_direction_close_
  blocked_until_calibrated` 為解鎖語意。注意:打平公式的 SELL_TAX 固定 0.3%(user 拍板不分
  當沖),當沖實際稅 0.15% → 空單打平線會偏保守(往不利側),要精確另議。

## 2026-08-20(refactor/memo-boundaries R6 留尾)

- [ ] **RiverOverlay hover 的 render body 成本**(review F5):幾何已 memo,但每 mousemove
  仍重跑 timeTicks + 七腿 polyline 字串重組(夜盤滿窗 840 分);要收斂把 polyline 字串
  併入幾何 useMemo — 注意 RiverCards 的 timeTicks 現在是計次探針,動它要一併換探針。
- [ ] **GroupGridView 2.5 萬 SVG 節點縮減**(handoff R6 原文):per-card memo 已有,
  節點數縮減屬視覺/結構設計變更(虛擬化或降採樣),另案 /mod。
## 2026-08-20(mod/signals-today-offload 留尾)

- [ ] **loop 預設 executor 同池耦合**(review C-1):to_thread 全走同一 ThreadPoolExecutor
  (daily_bars / capital close / signals-today / hub append),TC4 半死的不可中斷殭屍執行緒
  堆積時全池排隊。若 prod 觀察到 today / daily_bars 變慢,考慮給「純本機檔案 IO」一個
  獨立有界 executor;`_warned_years` check-then-add 跨執行緒(review C-3)屆時一併看。

## 2026-08-19(mod/ws-app-heartbeat 8 條 WS 應用層心跳 + 前端靜默 watchdog 留尾)

- [ ] **7 份 `WsStatus` 同值型別宣告 + `types.ts` 一份**(spec review R13):本輪刻意不收斂;下次動 hook 時統一從一處 import。
- [ ] **分頁第一代連線在首則 ping 前就半死 → 永久不偵測**(spec §4.2 殘餘盲區,同現況;sticky 只涵蓋後代):要封得掉要「open 即武裝」對舊後端就會誤重連,等 prod 穩定跑心跳一陣子後可考慮翻成一律 open 即武裝。
- [ ] **後端 accept-then-close 8 處未改 reject-before-accept**(handoff R3 原建議):前端 short-lived cap 5 s 已把空轉降到 0.2 Hz;uvicorn access log 仍每 5 s 一行,嫌吵再改。
- [ ] **隱藏分頁 > 5 min 的 Chrome intensive throttling 下 watchdog 恆不判定**(review A3;凍結守門每 tick 成立):false negative、回前景 ≤ 35 s 自癒;若要封,候選 = `visibilitychange` 回前景時重置基準並立即評估,或以「tick 間有無收到任何訊息」取代純時間守門。
- [ ] **watchdog 同步觸發的 thundering herd**(review A7):8 條 WS 同 tick 觸發、1 s 後齊重連 + refetch;真環境未見問題,若 prod 觀察到復原卡頓再對 watchdog 路徑加 jitter。
- [ ] **uvicorn `close_sent` 後 ASGI send 的 `RuntimeError` 窗口**(spec Edge 5):`_beat` 與 `_send` 同款曝險 → ASGI traceback log 噪音;prod 觀察到再決定是否在 relay 辨識該 RuntimeError 訊息收斂。

## 2026-08-19(mod/futures-broadcast-coalesce-leaf-unsub 期貨廣播 coalesce 留尾)

- [ ] **leaf 備胎訂閱退訂(user 2026-08-19 拍板本輪不退)**:handoff R2 原要求 HOT 回魂後退 leaf;spec review 指出退訂後 HOT 再被
  TXO session 搶走推播(同 symbol 只推一邊,UNSUB→SUB 救不回)時既有再武裝路徑(pending `st.p is None` 只冷啟動、跨日重武裝只掃
  `_leaf_fed`)都不觸發 → 凍結零訊號;夜盤冷門品「靜默再武裝」又會乒乓。要做 = 先設計 engine 層 HOT 靜默偵測(>N 秒且同族他品有推播)
  再武裝,且 `unsubscribe_leaf` 不得 `_ensure_connected`(review I1 KeepAlive 洩漏)。coalesce 後雙流 WS 流量已歸零,收益只剩 engine CPU。
## 2026-08-19(mod/txo-snapshot-no-redundant-push TXO 快照只在內容有變才推 留尾)

- [ ] **TXO 推播仍是全量整包**(review R10):有行情時 spot 每次價變都推整包;delta / 分欄推播未做。
  〔2026-08-20 實測:夜盤 60s 收 24 則,每則中位 17.1 KB(min 15B=ping),0.4 則/s ≈ 410 KB/min;
  日盤價變頻率更高,量級成比例放大〕〔2026-08-21 M0 日盤 12:35 實測 60s:19 則(另 5 則 ping),
  每則 **27.1 KB**(日盤鏈更寬),0.32 則/s,間隔中位 2.7 s(min 1.0 s / max 10.2 s)≈ **503 KB/min**;
  則數比夜盤少但單則大 58%,總流量 +23%〕
## 2026-08-18(mod/futures-intraday-core 期貨分時圖換 core + 檔位 1–10/15/30/60 留尾)

- [ ] **期貨分時 CDP / MA 疊線(2026-08-24 已拍板:昨日 H/L/C 用前一交易日資料)**:本輪反灰
  (title「期貨分時本輪不提供 CDP/MA/成交點」)。做法 = 以期貨日 K(`useFuturesBars(product, "day")`
  已有)前端算 CDP / MA5 / MA20,經 core 的 `overlay` 注入(index 態同管道)。
- [ ] **期貨分時成交點**(承 08-17 R2 留尾):core 已共用幾何,只差近全軸的日期界(夜盤成交屬錨定日;
  `fillPoints` 現為今日 ∨ 昨日活單)+ 成交分鐘 → `alldayIndexOf`;做完把 `fills.available = !futures` 解開。
- [ ] **hlines label 與 VWAP 末點標籤同走廊無避讓**(cr1 A-1):持倉均價貼近 VWAP 時兩標籤 halo 互蓋。
  候選 = 域內 hline 的 y 併入 `maObstacles`,VWAP 標籤也避 hlines。
- [ ] **VWAP 末點標籤走 `fmt` 不走 `priceText`**(cr1 A-5b):期指 VWAP 8 字 > `VWAP_LABEL_W` 估值,與同圖
  左緣 `fmtIndexPts` 兩套口徑(index 態既有同型)。候選 = VWAP 標籤吃注入口徑並重估寬。
- [ ] **近全軸 hover 命中率**(KR-5):1139 索引壓 724 單位,無 bar 分鐘反演回 null → 十字退化;夜盤薄量常見。
  候選 = futures 態限定「±N 索引最近 snap」(動 `minuteOf` 白名單,另案)。
- [ ] **副圖 1140 根 1 單位寬 rect 每 tick 重建**(KR-4):真環境 hover 目視未見掉幀(TMF 夜盤);若日後 TXF
  日盤高頻 tick 卡,候選 = EnergySub 改單一 path。
## 2026-08-18(fix/tc4-realtime-refcount-kill 開盤全站零推播 root cause 留尾)

- [ ] **shutdown 保證 LOGOUT**:09:00:49 那次是 uvicorn graceful shutdown 但 lifespan 沒跑完就被 run.ps1 `taskkill /T /F`
  收掉(TC4 log 直到 60s 後 reap 才 `RemoveLoginInfo`);sources `close()` 有 UNSUB+Disconnect 但沒機會執行。
  候選 = run.ps1 Ctrl+C 後先等 lifespan(輪詢 :8721 消失、上限 ~10s)再 taskkill;或 app lifespan 把 capital-com
  執行緒收尾放到 TC4 sources close 之後。有自癒後不再是必要條件,但少一輪 ~60s 暗窗。
- [ ] **TXO session 與 futures session 雙持 `TXF.HOT` 同 key**:單 session UNSUB→SUB 永遠到不了 count 0,靠第 3 次
  heal 的 window variant 才救得回(多一輪 backoff)。候選 = TXO source 的 SPOT 訂閱改用不同窗(例如 EndTime 07)或
  由 futures_engine 單持、TXO 讀 futures.state。
- [ ] **corr 海外腿在自身休市段落入 R2「從未推播」母體**(C-6 放寬後):每腿最慢 300s 一發 UNSUB+SUB、每 3 發換窗;
  上限 6 腿 × 12 發/小時。要收 = corr 每腿各自時段閘。〔2026-08-21 M0 log 對帳(08:39–11:42 三小時):
  SXF.HOT 8 發(靜默 240–244s,10:28 起每 4–12 分一發,全 attempt 1),其餘海外腿零發;
  **真正的 churn 大戶是個股冷門檔**:6921 嘉雨恩-創 153 發(全日 6 ticks,60s 靜默 → 每 ~70s 重掛)、
  6949 59 發 —— 個股 R3 健檢對「當日本來就沒成交」的檔一樣狂重掛,建議併入同一條收;**收盤段 IX0001 加權 13:25:37–13:34 每 30 s 一發共 18 發**(收盤集合競價 + 收盤後指數本就停推,source 層 R2 靜默閘不知道指數的時段)、13:45 日盤收後 TXF/MXF/TMF 各 2 發(夜盤 15:00 前的空窗,同類)〕
- [ ] **rollover 舊窗 key 洩漏(既有行為,非本輪引入)**:stage 2 `_resub` 的 UNSUB 用新日期窗,前一交易日的 key 留在 session 上直到
  session 死;死時歸零會把 symbol 上游帶走(正是殭屍 reap 殺 key 的素材)。要收 = set_trade_date 前先對舊窗逐 symbol UNSUB。
## 2026-08-18(mod/signal-denoise 個股訊號降噪留尾)

- [ ] **規則 UI `rearm_dwell_secs` step="1" 且前端不擋 0–3600 值域**(code review T-10 rejected):沿
  `window_secs` 既有慣例(值域由後端 INVALID_RULE 擋、文案泛用);要做就連 rearm_ticks / window_secs 一起
  加前端值域提示。
## 2026-08-17(mod/corr-nk225m-leg batch3 R5 留尾)

- [ ] **江波圖 end 格被 clamp 近似值先佔後,1K 回補的真收盤 bar 被「只填尚無值」擋掉**(2026-08-21 R5 spec review R5;characterization 已鎖
  `test_clamp_approximation_blocks_the_real_close_bar`,改時該案該紅):per-leg 旗標「end 格為近似值」讓 `apply_backfill` 覆寫一次。S 級。
- [ ] `tests/live/test_river_state.py` 帶 UTF-8 BOM(`ruff format --check` 報;非 gate)—— 順手批去 BOM。
- [ ] next-time:758(跨 UTC 06/22 邊界推播)本輪 20:1x 起跑仍未跨邊界,**未驗**;`spikes/nk225_leg_probe.py`
  可帶 `--listen-secs` 拉長在 13:5x 起跑順帶驗。

## 2026-08-17(mod/index-intraday-core batch3 R4 留尾)

- [ ] **兩欄態較矮視窗(容器 ≥ 1050 但主 grid 高 < ~800px)家數帶 section 溢出走主 grid 捲軸**(KR-3,
  code review C-3):`--idx-adl-min` 10rem 地板 + 家數帶兩列固定 chrome ≈ 306px > 分到的 5/11。1080p /
  864p 實測不捲;命中再降地板或 section 改 `5 1 auto`。〔2026-08-20 機械實測釘邊界:1536×700
  主 grid 622/676 = 54px 捲軸、溢出源家數帶 section 262/316;1536×864 = 786/786 不捲〕
## 2026-08-17(mod/positions-pnl-display batch3 R3 留尾)

- [ ] **個股期均價字面兩份**:header / chip 用 `fmt(Math.round(avg*1000))`(`1185`),`StkfutLadder` 部位列用
  `toFixed(2)`(`1185.00`);同值不同字面,收斂時二選一(建議 ladder 改 fmt,🔴 `StkfutLadder.test.tsx` 值斷言該紅)。
- [ ] **`code` null 的個股期倉位(除權息調整碼 EE1/CD1 形、新上市未 refresh)三處靜默不顯示**,閃電梯照舊;
  無任何提示。候選:positions 回傳 `code_missing` 計數 → 側欄底一行「n 筆個股期倉位無法對映」。
- [ ] **成交點精確版 / 群組卡個股期委託標記可直接吃 `code`**(R2 留尾的「契約碼→股號反查」已由本輪後端
  `stock_code_of` 提供;`GET /api/capital/positions` 有欄,orders 尚無 —— 精確版加 `code` 到 orders 同款)。
- [ ] `useFeeDiscount` 跨分頁 `storage` 事件有掛未驗收(spec §5);另 `PriceLadder` 折數輸入框仍是元件內
  state(改值時 persist 通知其他三處,但另一分頁的 PriceLadder 不會跟)。
- [ ] `useCapitalPositions` 現有 ≥ 4 個 observer(側欄 / header / 圖牆 / 梯):實測同 tick 掛載去重成 15s 一發;
  若日後有 observer 在不同時點掛載(lazy 頁面),15s 窗內可能多打 —— 要收斂就把 refetchInterval 移到單一
  provider hook。

## 2026-08-17(mod/intraday-fill-marks batch3 R2 留尾)

- [ ] **成交點精確版**(D7 拍板近似版的替代):後端 `CapitalStore` 保留逐筆 D 事件
  `(seq_no, time, price, qty, buy_sell, stock_no)`(只留當日)+ `GET /api/capital/fills`,前端每筆一標記;
  近似版已知失真:分批成交壓成一點(最新事件時間 × 均價)、尾段事件是刪單時點落在刪單時刻、
  **昨日部分成交今日刪單的單會以(今日刪單分鐘 × 昨日均價)畫上今日圖**(`date` 是最新事件日,
  日期界擋不到;cr1 A-3)。`copycat/capital/store.py:65` 的註解「委託建立日」同樣不精確,精確版一併改。
- [ ] **期貨分時成交點 ▲/▼ 仍關閉**(2026-08-24 盤點更正:期貨分時已換 `IntradayChartCore`,「另一套幾何」
  前提不再成立;現況是 `StockIntradayChart.tsx` ~1187 `{ key: "fills", available: !futures }` 在 futures 態
  寫死不可用,理由 = 近全軸(夜盤跨日)的日期界未處理)。資料源同 `fillPoints`(契約碼 key);
  做法 = fills 的 x 映射走 `allday.ts` 三段軸,再解開 `available`。
- [ ] **群組卡個股期委託不標**(契約碼→股號反查留給精確版一起做)。
- [ ] **toggle 關態 `EMPTY_MARKS` identity 無機械閘**(cr1 B-p2-3 rejected:關態沒有可計次函式);
  症狀僅掉幀。若日後改 ChartStatic memo 契約,順手補 render-count 閘。

## 2026-08-17(mod/ladder-market-buttons batch3 R1 留尾)

- [ ] **D4 現股市價安全首單 — 1068 已修(PR #94),待 prod 重啟 + 安全首單兩筆**:user 盤中 5608 市價賣 ×5、
  6770 市價買 ×1 全被群益拒:`SK_ERROR_SPECIAL_TRADE_TYPE_IS_MARKETPRICE_AND_ORDERPRICE_SHOULD_BE_ZERO`。
  根因(已修,PR #94):市價映射 `bstrPrice` 歸 "0"(字面 "0" 為推定,仍 1068 → 改試 "0.00")。
  驗收兩筆:低價股 1 張市價 + **一鍵平倉一筆**(該路徑 audit 全史零成功,本修首次成立)→
  群益 APP 核對 → 截圖回填 `.claude/mod/ladder-market-buttons/verification.md` §4。
- [ ] **委託列表「市價」標籤的日界語意**(KL-4):`store.note_price_type` 記本機日曆日,`_price_type_of`
  要求與回報 `_Agg.date`(委託建立日)相等;夜盤跨午夜 / 盤後預約單未實證 → 不符只缺標籤不誤標。
  收斂候選:交易日口徑(`trading_calendar`)或 ±1 日窗(與前端 `ymdWindow` 同口徑)。
- [ ] 真市價 literal `"M"` 給個股期 / 期貨市價鈕(D3b):prod 實測 `"M"` 可送後可從 limit@邊價切回;
  屆時 OrdersList 標籤對這兩梯才會出現(現在 wire 就是限價 IOC,不標)。
  (2026-08-24 註:user 之後找機會下單再驗;現股側 1068 修時一併盤點期貨端 `"M"` 路徑。)
## 2026-08-17(mod/flash-arm-lock 留尾)

- [ ] **鎖定態全域指示器**(spec R-3):停在 TXO / 指數頁或右欄委託 / 部位 tab 時畫面上沒有任何
  「鎖定中」訊號,回到梯上才看得到。候選:RightRail tablist 旁小徽章(UI 拍板)。
- [ ] **CapitalConfirmDialog 開著時 Esc 不解除鎖定**(spec R-6;next-time:190 既有語意的鎖定版):
  窗內 stopPropagation → 鎖定中 + 平倉確認窗開著時 Esc 只關窗。改 capture 監聽屬 🔴,另案。
- [ ] **未鎖定時「WS closed 期間仍可武裝」的既有邊沿語意**(spec review R1 衍生):鎖定鈕已在非 open
  時 disabled + level 觸發,武裝鈕未跟進(維持既有);要一致化可把 `armDisabled` 也吃 wsStatus。
- [ ] **後端 source="flash-locked" 稽核**(spec §8):payload source 可擴,讓審計檔看得出鎖定態送單。
- [ ] `FuturesLadder.tsx` 內 `futExchangeContract` 未 try/catch(App.tsx 那份有;既有問題,review p2 (d))。
## 2026-08-17(mod/group-grid-full-chart R4 留尾)

- [ ] **冷 cache 50 overlay 與瀏覽器 6 條連線交互未量**(review B10):盤中實機錄 waterfall,含同期
  balance / group-state 最大延遲。〔2026-08-21 M0:6 檔暖 cache waterfall 已錄(overlay 各 12–19 ms、
  group-state 6 ms、同期 capital/orders 4 ms、positions 19 ms);冷 cache + 50 檔仍未量〕
- [ ] **>20k tick 日單檔頁 vp 偏小**(review R2-5):單檔頁 vp 折自已被 deque(20k)截斷的 snapshot
  ticks,後端增量 vp 全日 → 該類日子卡片與單檔頁 POC 可能不同;parity fixture 只鎖同輸入折法。
  〔2026-08-21 M0 真樣本:2609 陽明 12:36 回補 29772 ticks,`/api/stock/state/2609` 回 20000 ticks、
  首筆 09:16:54 → 09:00–09:16 開盤段已被截掉;航運大漲日一檔就中,非罕見路徑〕
- 文案殘留:`GroupGridView.test.tsx` 仍有「mini 分時圖」字樣的 describe 敘述(行為無涉);順手時改。

## 2026-08-16(mod/trading-calendar 留尾)

- [ ] **TXO 面的 `backfill_date` 仍是手動 env**:`_default_source` / `session_rollover` /
  `live/tc4.py:404` 沒接日曆 —— TXO 有夜盤 session 語意,自動填一個固定日會把 rollover
  關掉並跨到下週一(自動化前要先設計「哪一段夜盤算哪一天」)。休市日要看 TXO 仍靠
  `TXO_BACKFILL_DATE=<上一交易日>`。
- [ ] **非開盤日 / 盤前冷啟動,圖表要維持前一交易日資料(2026-08-24 已拍板開做,原 R3b)**:
  交易日 00:00–08:30 重啟 → source 日窗 = 今天而今天還沒開盤,空圖到開盤(spec KR-4 / Q3-R8);
  非交易日已由 R3 日曆處理,此案補「交易日盤前」段。要對齊 stock stage1 08:00 / index 08:30 /
  breadth streak 06:00 三個時序。
## 2026-08-16(mod/overview-onepage-corr-tab 收尾留尾巴)

- [ ] **週末補班(extra_trading_days)漏設無膠囊提示**(2026-08-21 R6 spec review R9):膠囊週末守門排除;後端判休市 → 報價凍住 + 無(緩)(tick 層 is_trial 純窗丟棄)。
  候選:`/api/calendar` additive 加 extra_trading_days,條件改「後端判非交易日且(非週末 或 …)」。
- [ ] **`TXO_BACKFILL_DATE` 忘了清造成整盤凍結無提示**(R6 review 觀察):payload 已有 `backfill_env`,可比照膠囊掛一顆。S 級。
## 2026-08-14(fix/index-line-vanish 收尾留尾巴)

- [ ] **TC4 凍結 stub 的姊妹 ready-check 未收緊**(review L2-P2-4):`river_backfill.
  collect_1k_minutes:52`、`stock_source.backfill:499`、`tc4._fetch_symbol_ticks` 仍是
  「首頁非空即 break」(2026-08-24 盤點:三處仍在 `river_backfill.py:58`、`stock_source.py:608`、
  `tc4.py:751`);空窗毒化訂閱回凍結 stub 時同樣被騙。~~river 的 `minute_end_from_1k` 只讀 Time
  不讀 Date~~ 這半邊已由 `river_models.py::parse_1k_minutes(rows, utc_day)` 丟棄異日列解掉,
  剩 ready-check 本體。index 側已用「差量進展 + 窗口 variant」繞開;姊妹路徑要收就沿
  `_collect_history 靜默回空家族`(2026-08-13 節)一起做三態化 + stub 簽名判定,獨立輪。
- [ ] **heal 每個 variant 新發一個 history 訂閱、無釋放路徑**(review L1-P2-4):壞日子
  單 session 最多累積 ~18 個 IX0001 1K 訂閱(`_unsub` 只管 REALTIME)。TC4 per-session
  history 訂閱上限未實測;SC-5 側車重演時順手觀察連續多窗口訂閱的行為,若有上限,
  觸頂樣態可能又是「靜默回空」。
- [ ] **`_twse.minutes` 的 worker thread 寫 vs event loop 迭代讀無鎖**(review L1-P2-3,
  既有家族、本輪把讀寫推得更中心):被取消 retry 的 orphan to_thread 仍會 `update()`,
  與 `_minutes_lag_exceeded` 的 `max(m)` / `_payload` 的 `dict(...)` 理論可撞
  `RuntimeError: dictionary changed size during iteration`(炸點在 try/except 外,
  该發 heal 靜默消失)。收法 = worker 只回傳 dict、event loop 端合併,動 `_retry_loop`
  與 `_subscribe_and_backfill` 簽名,小輪。
- [ ] **SC-5 側車順驗 stub 語意**(review L1-P2-1 / L2-P1-2 Known Risk):驗「凍結
  stub 的 Time 是否恆為訂閱建立時刻」與「盤中建立的新窗口在該窗真無 1K 時是否產生
  in-domain 假分鐘(實際為當下真實指數價的稀疏點)」;若後者實測發生且被嫌,
  升級手段 = fetch 結果單鍵且鍵=當下分鐘時標記可疑(不動階梯,只加 log)。

- [ ] **期貨態 POC(2026-08-24 已拍板要做)**:需 `foldVp` 分鐘窗參數化(現硬編現貨窗)+
  期貨態 vp toggle 解禁,連動 stock_state 折入層。

## 2026-08-13(mod/watchlist-ux-limit-50 收尾留尾巴)

- [ ] **側欄下方空白區拖曳仍 append 最後一組**(2026-08-21 R4 review F3,作廢帶鏡像):zonesNow 回傳最後 section bottom,`y > lastBottom + ROW_H` → null。S 級。
- [ ] **後端個股期平倉路徑不過 `_require_legal_tick`**(R4 review F4,後端 /mod):`/api/capital/position/close` 直送 close_position,只驗 price>0;
  前端 edgeOf 是唯一檔位守門,漏接 = 券商退單零訊號。修法:close route 由 req.key 反查 product,tickable 個股期補 tick 閘。
- [ ] **ETF 期貨 / 除權息調整腿的平倉估價用現股 tick 表**(R4 review F5):`isOrderBlocked` 只擋閃電梯,平倉鍵不擋;現為嚴格改善(0.01 倍數),可比照送單面讓 blocked 腿 closePriceOf 回 null。
## 2026-08-13(mod/trial-pause-badge 第一段收尾留尾巴)

- [ ] **緩撮標示第二段:TradeStatus-based per-code 盤中偵測**(本輪只出時間窗版,
  **09:00–13:25 盤中暴漲暴跌觸發的暫緩撮合不會亮** → 使用者回饋 backlog 第 3 條
  維持未勾銷):蒐證通道已埋 — engine 對每檔現貨 TradeStatus 轉態記 log,固定前綴
  `trade-status-observe`,窗外事件 WARNING(episode 起訖成對)。等真實延緩撮合樣本
  出現後:(a) 依 log 把值域/起訖/恢復實測事實記回 `tc4-market-facts` skill;
  (b) 依蒐證結果把 `trial` 推導從純時間窗升級為 per-code(TradeStatus 驅動),
  wire 契約(`watchlist_quote.trial` / snapshot `trial`)已就位不用動;(c) badge 表述
  是否分化(試撮「(緩)」vs 盤中暫緩「(暫停)」)屆時拍板。已知限制:休市日/週末
  窗內純時間照標(無交易日曆,第二段天然消除)。**蒐證判讀注意**(review D6-2):
  窗內起 / 窗外訖的 episode(如收盤試撮窗跨越的延緩撮合)在第一段規則下全程只有
  DEBUG — 對帳時 13:25–13:30 前後要併看 DEBUG 級,別只 grep WARNING。
  **〔2026-08-21 M0 首批真樣本(`logs/server-20260821-0839.log`,26 行 = 13 個完整 episode,
  全部 trial_window=False → WARNING)〕**:TradeStatus 0→1 後約 2 分鐘 1→0,時長 1:55–2:05,
  形狀 = TWSE「延緩撮合 2 分鐘」:開盤段 09:00:34–09:04:15 起 11 檔(3026/6207/6213/2615/2637/
  3037/2484/3042/4958/6456/8046),**盤中段** 3037 09:06:06→09:08:01、3042 09:09:35→09:11:30
  各一次(即第二段要亮的那種)。0→1 那筆 tick qty 極小(1–15)、1→0 那筆 qty 大(62–608,
  = 延緩後集合撮合那筆)。可據此做 (a) skill 事實回填:**TradeStatus=1 即延緩撮合中,episode
  ≈ 2 min,恢復 tick 即集合撮合成交**;(b) per-code `trial` 可直接吃 TradeStatus==1。
- [ ] **`stock_engine._quote_payload` docstring「四個產出點」已漂移**:實為 8 處
  (:373 set_watchlist / :457 quotes() Discord 摘要 / :647 retry 重掛種子 /
  :767 _handle_no_data / :919 轉態補推 / 連線 seed / 1s flush / 本輪新增的
  窗翻轉補推;2026-08-13 spec review R5 grep 證實 7 處 + 本輪 +1)。
  下次動該函式時順修 docstring。

## 2026-08-13(fix/index-chart-empty-minutes 收尾留尾巴)

- [ ] **BalanceCollector 殘餘交錯:新輪已收 rows 時舊輪遲到 `##` 會 flush 截斷 / 跨輪混合快照並關閉本輪**(2026-08-21 R7 review F7;2026-08-22 review P1 補:舊輪 rows 與新輪 rows 落同一 staging 時會復活已出清的幽靈部位):COM 無查詢識別不可根治;
  機率 = 兩回應交錯於 ms 級窗。若 prod 觀察到「部位少一檔 / 多一檔 60s 後自癒」即此樣態;候選 = 查詢後 N ms 內的 `##` 才視為本輪。
- [ ] **期貨 K 線三態 status 通道**(2026-08-21 R8 plan review P1-6):`_market_payload` 無 status 欄、`build_minute` 丟棄第二元素、前端 BarsMeta 只看 `source === "unavailable"`;
  timeout 目前在 `futures_engine.bars_range` 內吃掉只 log。要三態需 payload + route + 前端 FuturesChart 分支同批。
- [ ] **盤外時段啟動踩 timeout 無自癒**:分時自癒 gate 在 watch window(09:00–13:25),
  盤後/晚間啟動若 1K 回補 timeout,線缺到次日 09:06 才自癒。實測晚間 TC4 閒時回補快
  (18:17 啟動無 timeout),風險低;若要覆蓋,detector 改「窗外以 min(now, 13:30) 為
  期望覆蓋終點」,但要處理休市日恆空的輪詢噪音。
- [ ] **heal 帶 minutes 的廣播對飽和 client 是 at-most-once**(review T-4/C-2,known-risk):
  per-client queue(`ws.py::CLIENT_QUEUE_MAX`,2026-08-24 現為 500;原記 32 已過時)飽和期間
  `QueueFull: pass` 靜默丟掉 heal 那一則 → 該分頁線仍空且無二次機會(引擎
  state 與 log 都顯示已自癒)。觸發窗極窄;系統性解法(per-client 補送 / 低頻週期全量)
  會動 scalar-only 頻寬慣例,獨立輪評估。
- [ ] **pending 期間連線類 retry 把新日 1K merge 進舊日 minutes dict**(review T-1 附帶,
  latent 既有):廣播已被 T-1 修復擋住,但 server 端 `state()` 在 swap 前(≤60s)仍可能
  給出混日 minutes(重整頁面恰落在該窗會短暫畫混日線)。修法 = retry 成功時 pending 態
  寫進 `_pending_minutes` 而非 `_twse.minutes`,要對齊 swap 的 backfill 合併語意,獨立小輪。
- [ ] **櫃買(MIS)無回補來源的同症狀**:MIS 從開盤即死透的日子,otc 分時線整天空且
  引擎無從回補(已文件化降級)。唯一可做的是 UI 分態文案(「櫃買快照源中斷」vs 現在
  的無線靜默),順下輪前端批。

## 2026-08-12(mod/signal-hub-decouple XR-3 收尾留尾巴)

- [ ] **前端 tc4="down" 文案分態**(review R2-6 accepted 偏差):StockPage 對
  `status.tc4 === "down"` 顯示「達錢 4 連線中斷,恢復後自動回補」,但 XR-3 後無
  engine 模式(TC4 從未開)也會收到 status down seed,而該模式 TC4 恢復**不會**
  自癒(stock engine 只在 boot 建,需重啟 server)。候選:seed 加欄位或前端分態
  文案(「達錢 4 未連線,啟動後需重啟 server」)。frontend 小改,順下輪前端批。
- [ ] **`_empty_daily_bars` 語意堆疊**(C-4 已修 gap sleep;殘餘觀察):無 engine 時
  basis job 仍逐檔跑一輪(50 檔 50 行「CDP 停用」warning,一次性)。若嫌吵,候選
  = 無 engine 時 on_watchlist 不排 basis job(hub 加模式分支,spec 當時判不值得)。

## 2026-08-11(fix/tc4-lock-p2s 收尾留尾巴)

- [ ] **X-3 深修:把 ZMQ 訂閱迴圈移出 `stock_engine._pool_lock`(review 首位 finding,P2)**:
  X-3 只收斂了 service 鎖(讀路 / 落檔不再堆積),engine 端 `_pool_lock` 仍序列化整段
  逐檔 `to_thread(_acquire)` 迴圈 —— TC4 故障下第二個寫入者的 `_settle` 還是等第一個
  的迴圈走完,Discord 回覆仍可能拖過 interaction token 上限。修法方向 = 同檔 backfill
  worker 的 per-code 取鎖模式(鎖只護共享結構,ZMQ IO 在鎖外逐檔做);要重新對齊
  「名單先指派再訂閱」(round4 項 4)與 seq 定序的不變式,獨立輪做。
- [ ] **`set_watchlist(seq=None)` 豁免顯式化(review,latent)**:None 分支唯一生產
  caller = app.py boot 還原,安全前提是「service 在 restore 之後才建構 + routes 前置
  503」,這條不變式沒在任何地方斷言;Protocol 預設 None → 未來 caller 漏帶 keyword
  零訊號。最便宜的硬化 = boot 顯式帶 sentinel(seq=0)、刪 None 分支。
## 2026-08-11(mod/capital-confirm-native-dialog 收尾留尾巴)

- [ ] **CapitalConfirmDialog 新 caller 硬性契約**:onConfirm / onCancel 必須卸載元件
  (closedRef 一次性 settled 旗標;JSDoc 已載明,無機械防護)。

## 2026-08-11(fix/watchlist-dialog-swallowed-callback 收尾留尾巴)

- [ ] **BAD_GROUP eager 驗證與套用基底分歧(review C-4/W-3,P2)**:submitAddGroup /
  submitRename 用 render 閉包 `wl` 做撞名 eager 檢查,套用卻在佇列 `baseRef` 上 —— 佇列
  視窗內交錯時偽陰性(驗證放行 → 套用撞名 → 靜默零 PUT 無文案,輸入框已清空看似成功)
  或偽陽性(誤報 BAD_GROUP)。已無資料錯(dedup 兜底),只剩無回饋的罕見交錯。要收:
  撞名判定搬進 transform(make 回傳 reject 訊號 → setLocalError),eager 檢查降級純 UX。
- [ ] **Dialog 佇列 onDone 在 unmount 後仍執行(review W-8,已拍板採「不漏清」語意)**:
  promise chain 不受掛載狀態約束,PUT 在途時整頁換 tab 卸載後 `onGroupDeleted` 照跑
  (冪等 localStorage 清理,unmount 後執行正是 W-20 要的;setSelected 是 React no-op)。
  與 CapitalConfirmDialog「unmount 零 callback」lock 語意刻意不同(真錢下單 vs 冪等清理)。
  若要機械釘住:補一條 unmount-after-PUT 仍清 `WL_COLLAPSED_KEY` 的 lock。
- [ ] **跨元件並發寫者(Dialog 佇列 vs 側欄拖曳)**:兩者各持獨立 mutation observer,不互相
  序列化;關窗後佇列殘餘的 sub-second 窗內側欄拖曳仍以 render 閉包算 next,理論上可互相
  覆寫(modal 開著時側欄不可互動,窗口極窄)。要收 = 佇列上提到 hook 層讓三個 caller 共用。
- [ ] **佇列交錯覆蓋缺口其餘兩類(review W-5 附帶)**:刪組+改名交錯、失敗短路後
  「新動作以未變基底重算」的更多組合,現有 lock 只釘了連刪 / 連點 / 失敗短路三條主路徑。
- [ ] **useBreadth / useIndexStream handler 同 tick 回寫升級(P2,自癒型)**:兩檔 ref 只在
  commit 後由 useLayoutEffect 同步,同一 macrotask 兩則 WS 訊息時第二則以舊底合併(下一格
  upsert / onopen refetch 自癒)。若要關窗:handle 內算出 next 同步回寫 ref(與
  useFuturesStream imperative 配對同形,各 3-4 行)。註解已標明不同級。
- [ ] **TickTape key 穩定序號真解**:回推索引 key 在 `TAPE_MAX=200` 滿載後仍逐筆位移
  (與修前同級,未惡化)。真解 = stock-accum 累加單調 dropped 計數或後端 seq 入 TickRow,
  key 改 `${dropped + ticks.length - 1 - i}`。
- [ ] **StockChart spotMode 在 prod 無讀者(記錄性)**:StockPage 的 `{accum ? …}` gate 讓
  換合約必卸載重掛,A6「還原現貨模式」實際由 localStorage 兌現;spotMode 只在
  same-instance(測試)路徑有讀者。日後想刪它或想真驗 A6,先看 StockChart 是否已脫離
  accum gate。

## 2026-08-06(stkfut-contracts 題3 收尾留尾巴)

- [ ] **個股期功能待 user 過目**(PR #28 試用指引):合約下拉/分時五檔切換/個股期梯截圖
  四張在 `.claude/feat/stkfut-contracts/evidence/`;**真送單驗證 = prod 安全首單**
  (遠價 1 口 → 群益 APP 核對 → 刪單,§7);首個交易日順看 08:45–09:00 期貨分時有資料
  (夜盤訂閱窗假設的 prod 觀察項)。
## 2026-08-06(group-grid 題5 收尾留尾巴)

- [ ] **apply_backfill reset+replay 競態範圍隨 guard 去 main 化擴大**(review B3-f;2026-08-24 起由
  Claude 盯:下次盤中以 group-state 連續抓取對照分鐘完整性,user 不用主動看):SubHistory 與套用之間
  到達的 live tick 被洗掉,現及於全部自選成員(每檔每日一次 + 60s 輪詢自癒)。
## 2026-07-07(tday-join-ga-backtest 收尾沉澱)

- [ ] simulate 完整 derived-series 預計算重構(review F2 只做了 anchor 網格限定;若 Phase B 全量變慢再做)

## 2026-07-11(fade-round-1 收尾 review P2 彙總,18 條聚類)

- [ ] fade pipeline 效能候選(6h 長跑;/perf 先 profile 再動):診斷段重讀全部 1K bars(run 時已讀過)、optimize_rule_tp 重算 optimize_rule_stops 已算過的 rule mask、guard_dist_grid 每格全量重模擬、by_source O(sources×trades) 重掃

## 2026-07-14(fade-round-2 自評 review P2 彙總)

- [ ] fade 診斷效能候選(/perf 先 profile):diagnose_pool_fade 對同一 universe base+stress+lock_grid 共 5 次全量重模擬(可單迴圈多配置);evaluate_cells 每 cell×variant 各 base/stress 兩趟 + baseline ×4 = 16 趟(觸發判定可先算一次共用)
- [ ] write_pool_fade_report / write_cells_report 兩份 markdown 表建構結構相似(第三份出現時抽共用 table builder)
- [ ] fade_cells 新增 cell 需改多點(find fn / _simulate_cell_trades 分支 / specs 列表 / config):cell 數 >4 時抽 registry
- [ ] fade_cells find_cell_a_entry 的 headroom 除式無 b.close>0 防禦(實際 1K 資料恆正;若接入外部資料源先補 guard)
- [ ] backfill_brokers/label_events 對 FinMind 非數值欄位(如 'N/A')無韌性(現況未觀察到;出現時在 aggregate 層加 tolerant parse + 計數)

## 2026-07-15(fade-round-3 自評 review P2 彙總,8 條聚類)

- [ ] evaluate_cells_from_universe 頂層 round gate 分岔 → **觸發條件已到**(2026-08-24 盤點:`fade_cells.py:263-286`
  已是 round5 → round4 → round3 → round2 四段 if-elif chain),下次動 fade 回測時抽 evaluator factory
- [ ] 底倉格 grid 對 in_w 掃 6 次(單次分桶可 O(n),n 小暫無感)
- [ ] run_cells 三次 build_fade_universe(cellb 可由 main 超集記憶體過濾,現況重讀 1K JSON)
- [ ] validate_disaster_fields 在 _simulate_core 每 call 驗一次(GA 熱迴圈微耗;可改 config frozen 後驗一次的快取)

## 2026-07-16(fade-round-4 自評 review P2 彙總,12 條聚類)

- [ ] fade_anatomy 效能候選(單次跑分鐘級,量級可接受;/perf 先 profile):flush_anatomy 每個 z 全宇宙重掃(可單趟收三個 z)、hl_anatomy 每個 k × arm 重算 entry idx(可 cache)、_evaluate_round4 消融 5 組 × 5 變體 = 25 趟全量模擬
- [ ] check_flush_exit(cfg 驅動)與 _tp1(combo 驅動)結構重複但錨不同(進場後最低 vs running_low 含 trig)——已在 docstring 註明差異;若 Phase B 網格路徑退役,_tp1 可刪併

## 2026-07-17(fade-round-5 收尾 review P2 彙總,8 finder → 6 條)

- [ ] round5 效能候選(/perf 先 profile):stress 跑法重執行 entry_fn 全宇宙掃描(進場 idx 不依 run_cfg)、樣本預算表 4×全宇宙重掃(可單趟 _iter_votes 同時判多個 S)、消融 3 單訊號各自重跑狀態機
- [ ] 敏感度區塊複製貼上(S/c/m 三塊近同)+ disaster_off 手刻出異形 dict shape + round 輪次 dispatch 鏈成長(round 6 時考慮 active_round 單點解析);flow_flip_anatomy 出現率分母含 len(bars)<2 跳過日(輕微低估,不影響判準)

## 2026-07-20(backfill 雙修 review P2)

- [ ] backfill_finmind/backfill_daytrade 空日不進 marker 後,真假日在重跑同 range 時會反覆重抓(range 約 11 個月含 100+ 週末假日);若 FinMind 配額吃緊,疊加靜態台股假日曆只重試「非假日空回應」

## 2026-07-28(capital-order Phase 3 順手清單)

- [ ] TXO 市價單確認框金額 = **估算**,冷門履約價可能是舊價:`snapshot.contracts[].last_price` 是該合約當日**時序最後一筆成交價**、無時效標記(2026-08-05 /mod txo-contract-last-price 拍板 out of scope)。深價外履約價可能整個上午沒成交 → 確認框「預估權利金」與安全閘 `safety._check_qty_amount` 的名目金額都吃到數小時前的價。**送單本身不受影響**(市價走 literal M,`capital/mapping.py:161`,價格不是我方帶的);要收斂的話候選 = last_price 帶成交時刻 + 前端超過 N 分鐘標示為舊價
## 2026-08-10(startup-names-futures-resub 回溯補審 — 當輪漏跑 code review,補審抓到 3 P1)

> 完整 findings:`.claude/bug/startup-names-futures-resub/code-review-round-1.json`
> (2 lens 回溯審 diff 99ef8888^..2d144765,逐條對照 HEAD e3aeda5b 現碼,全部仍成立)。
> 三條 P1 的正解都已存在於 corr/stock 姊妹實作,照抄即可 — 建議合併成一輪 /bug 或 /mod。

- [ ] P2(共用層,獨立 /mod):tc4 `_ensure_connected` 無鎖 check-then-act ×
  `_check_stale` 重連 race → 雙 QuoteAPI 落敗者永不 Disconnect;本輪 diff 讓觸發窗
  系統性放大。**2026-08-24 盤點:`_api_lock` 已存在(`tc4.py:295-299`)但只護 `_dispose` 的
  check-then-clear 與指標發布(:337-339);`_ensure_connected` 的 check(:319)與 QuoteAPI 建立(:324-336)
  仍在鎖外、無 `_stop` 早退 → 本條未解。**修 = check+建立+發布以 `_api_lock` 原子化 + `_stop` 早退,
  stock/corr/index 四 source 一起回歸。

## 2026-08-12(fix/futures-resub-recovery 收尾留尾巴)

- [ ] **reconnect 對帳不含 leaf 訂閱**:`_handle_reconnect` 只回填 HOT 品;重連若掉了
  leaf 契約訂閱(`_leaf_done` 記帳仍在、p 有舊值不武裝),要等跨日重武裝才補回。
  影響限「HOT 因 spot 衝突零推播 + 重連掉 leaf」雙重疊加,低頻記錄備查;要收 =
  on_reconnect 時對 `_leaf_fed` 品清 `_leaf_done` 當日鍵重走 fallback。
- [ ] **`_check_stale` 迴圈中途拋錯尾段蒸發對 stock/corr/index 的復原完整性未逐一盤點**
  (本輪只修 futures + tc4 warning):stock 有 `_resubscribe_all`/`_failed_resubs`
  對帳、index 有 self-heal 鏈,corr 的 `_on_reconnect` 只重跑回補**不重訂閱**
  (corr_engine.py:108 註解自承)— corr 腿在重連掉訂下疑似同病,下次動 corr 時
  比照 futures 接對帳。

## 2026-08-11(react-doctor /chore 快修批 review 留尾巴,全部既存非本批引入)

- [ ] **P2:MarketPane OverlayCard 單邊 ref 缺值時線色/標籤錯位**(既存):
  `buildOverlayGeometry` filter 掉 ref null/0 的 series,`g.lines` index 與
  OVERLAY_LINES 錯位 —— twse.ref 缺時僅剩的櫃買線會畫成加權色標「加權」。
  修法 = callee 帶回原始 index(或 filter 改保位 null),OVERLAY_LINES 註解已標。
- [ ] **RadioPills `onInteract` 每次 label 點擊觸發兩次**(2026-08-21 fix 波實測:label activation 轉發 click 到內層 input 再冒泡):
  現僅用於 PriceLadder 重置武裝閒置計時,冪等無害;若之後有人拿它計數,要在 label onClick 過濾 `e.target` 為 input 的那次。
- [ ] **P2:自選列組內排序無鍵盤路徑**(既存):拖拉握把是唯一排序入口(pointer
  only;aria-hidden 化後對 AT 不可見)。管理 Dialog 只有移組/移除,無排序。
  補鍵盤排序入口(如 Dialog 內上移/下移鈕)列排期。
