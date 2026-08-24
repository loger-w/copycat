## 2026-08-22(日間鏈 R1–R10 review 留尾;結論 `docs/superpowers/specs/2026-08-22-daytime-chain-review.md`)

P0/P1 與四輪小批已全數出貨(PR #88 欠帳計數 / #89 VWAP 避讓 / #90 R8 留尾 / #91 calendar+tape_omitted;
prod 8721 = 6adf20d9、dist 已重建)。

**待 user 過目 / 盤中觀察(真環境無法刻意觸發,以測試代證的五項)**:
- [ ] **#88 部位面板不再瞬清**:連續死查詢後部位不得被清成空、平倉鍵不得鎖住;log 出現
  「collector 忽略放棄輪遲到的終止符(部位更新抑制一次,尚欠 n)」= 修復路徑命中。若其後仍見部位瞬清
  → 20s `STALE_WINDOW_S` 太短,量實際遲到秒數再調。
- [ ] **#89 個股分時圖右緣 VWAP × MA5 錯開**:2330 盤後開 MA+均價,白色 VWAP 數字與琥珀 MA5 數字上下錯開
  (08-22 真資料兩者本就只差 0.7px 看不出,下一交易日差距大時再看;截圖 docs/specs/mod-vwap-label-avoid/screenshots/)。
- [ ] **#90 log 兩句正常訊息**:「backfill … timeout 但已退訂,不重排」(移出自選後不再白打 TC4)/
  「river 回補 single-flight … 併回 pending(legs=…)」(reconnect 撞上回補中那輪,接著補不是丟掉)。看到即正常。
- [ ] **#91 群組 → 單檔首 paint**:右下成交明細先閃「載入明細…」再出資料(次秒級,可能看不到);不該再短暫顯示「尚無成交」。
- [ ] **#91 休市膠囊 5 分鐘內亮**:日曆錯標真交易日為假日時,整天掛著的 preview 分頁跨午夜後 5 分鐘內出現
  「日曆判今日休市」(平常交易日與週末不亮);真窗口 = 下一個錯標平日。

以下為本次不動的 P2:

- [ ] **VWAP 標籤寬度 index 態低估**(2026-08-22 mod/vwap-label-avoid review P2):`StockIntradayChart.tsx` VWAP 文字硬編 `fmt`
  不吃 `priceText`,加權 `24283.54` 實寬 ≈45px > `VWAP_LABEL_W`=40 → clamp 字尾溢右緣帶(既有)+ 新 obstacle 判定多一道 ≈5px 誤判窄帶。
  修法 = VWAP 文字走 priceText 或寬度依 mode 取值。
- [ ] **VWAP 就地標籤 × 極值標記文字不互相避讓**(同上 review P2):兩者都「不可動」,日高/低落在盤末最後幾分鐘且價位≈VWAP 時疊印仍可達。
- [ ] **VP 圖層在 tapeOmitted 時的佔位**(2026-08-22 mod/calendar-poll-tape-omitted out of scope):群組切單檔首 paint VP 空,
  與「無成交」同形;可沿 `accum.tapeOmitted` 讓 VP toggle 區印載入中。
- [ ] **R1 超容 clamp 全堆界邊**:`lib/stock-intraday-svg.ts:643-666` dropOverflow=false 時上緣標籤被
  clamp 成完全同 y(測試字面量 `[4,4,4,4,10,20,30]`),4×4 圖牆 capacity 6 / n=7 會踩到;改成界內等距壓縮。
- [ ] **R2 MarketPane 週期 radiogroup 內混「重疊」toggle**(`MarketPane.tsx:493` trailing):新引入的
  aria-required-children 違規,與 GroupGridView.tsx:346 同批相反決定不一致;搬出容器。
- [ ] **R2 OrderPanel kind 單向靜默收斂**(`OrderPanel.tsx:66`):估價暫缺(WS 快照空窗)時市價翻回限價且不復原;
  改回 disabled 送出鈕或估價回來時還原。
- [ ] **R2 StockChart 停用 pill 新增 cursor-not-allowed**(`RadioPills.tsx:84` vs `StockChart.tsx:169`,視覺零變偏差);
  `RadioPills.test.tsx:260/276` onInteract 改 `toHaveBeenCalledTimes`。
- [ ] **R3 toast 合併與 `groupSignals` 不等價**(`useSignalAlerts.ts:187` 全索引 vs 相鄰)→ hook 內補註解;
  `formatToastText` 只剩測試在用要標明;`ToastStack.tsx:29` 比照 B3 clamp;背景 >5 分鐘 intensive throttling
  首則延遲待 user 實測。
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

- [ ] **1536×864 高度下 K 線態仍吃地板 96 → CandleChart svg 被 figure 壓到 81px(實縮 0.84)**:
  根因 = K 線態雙層 figure chrome 100(分時只 26)+ Quote figcaption 在 350px pane 折三行,
  864 高沒有空間;改前同樣被壓(0.20)。候選:K 線態 chrome 瘦身(CandleChart 共用 figure,
  需顧個股頁零差異)或 Quote figcaption 單行化。證據 `.claude/mod/overview-narrow-pane-legibility/
  evidence/SC-1-1536-candle-crop3x.png`;1920×1080 / 2560×1440 未吃地板。
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
- [ ] **useChartToggles.set 包 useCallback**:目前零受益(無 memo 節點收 onToggle);
  哪天有邊界要收 onToggle 時一併做(plan review R9)。

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

- [ ] **期貨分時 CDP / MA 疊線**:本輪反灰(title「期貨分時本輪不提供 CDP/MA/成交點」)。要做 = 以期貨日 K
  (`useFuturesBars(product, "day")` 已有)前端算 CDP / MA5 / MA20;先拍板「昨日 H/L/C 取日盤 vs 近全時段」
  口徑,再經 core 的 `overlay` 注入(index 態同管道)。
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
- [ ] 真 TC4 層 user 過目點:對稱域 ±1% 地板讓平靜日線視覺變平(同 index R4);量欄「-」佔位語意。
  〔2026-08-20 夜盤截圖已存(TMF −0.39% 近全軸、日盤+夜盤線、五檔活跳):docs/specs/
  next-time-mcp-verification-2026-08-20/screenshots/27-futures-allday-night-session.jpg〕

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

- [ ] **合併 toast 多行觀感**(2026-08-21 R3 review C7):三段 kind 文案 ~45 字在 `w-72` 下折 2–3 行,ToastStack 無 clamp;
  user 過目「1 張三段 + 3 張單則 + 溢出列」後決定是否比照 B3 加 line-clamp。
- [ ] **背景分頁首則通知延遲 ≈1s**(2026-08-21 R3 review C1):trailing 模型的 300ms 合併窗在 hidden tab 受瀏覽器 timer ≥1s clamp;
  若嫌慢,候選 = 首則 leading 發、窗尾同 tag 補發合併文案。
- [ ] **規則 UI `rearm_dwell_secs` step="1" 且前端不擋 0–3600 值域**(code review T-10 rejected):沿
  `window_secs` 既有慣例(值域由後端 INVALID_RULE 擋、文案泛用);要做就連 rearm_ticks / window_secs 一起
  加前端值域提示。
## 2026-08-17(mod/corr-nk225m-leg batch3 R5 留尾)

- [ ] **相關係數 tab 七腿 prod 重啟後過目**:小日經 fuchsia(river-7)與標普薰衣草紫 / accent 桃紅可辨度;
  並排模式三欄格局第 7 卡獨佔第 4 列(1080p 側車截圖 `.claude/mod/corr-nk225m-leg/evidence/SC-3-cards-nk225m.jpg`)—
  若嫌浪費,候選 = 卡片 grid 改 `auto-fit minmax` 或 4 欄;本輪 out of scope。
  〔2026-08-20 真 TC4 夜盤截圖已存(重疊七腿含「小日經 自 16:01 起算 0%」腿級註記、並排 7 卡
  小日經獨佔第 3 列):docs/specs/next-time-mcp-verification-2026-08-20/screenshots/43-corr-*.jpg〕
- [ ] **每日台北 14:45–16:00 小日經腿 stale / corr 三窗依窗長先後轉「—」(w1800 最長 30 分後)/ 江波圖夜盤窗前 60 格空**(OSE 日盤收 → 夜盤開;
  台指夜盤 15:00 已開)= 預期行為非訂閱失效(判別:16:00 後恢復推播)。若覺得刺眼,候選 = 腿級「休市中」
  標示(需 OpenTime/CloseTime 語意,另案)。
- [ ] **江波圖 end 格被 clamp 近似值先佔後,1K 回補的真收盤 bar 被「只填尚無值」擋掉**(2026-08-21 R5 spec review R5;characterization 已鎖
  `test_clamp_approximation_blocks_the_real_close_bar`,改時該案該紅):per-leg 旗標「end 格為近似值」讓 `apply_backfill` 覆寫一次。S 級。
- [ ] `tests/live/test_river_state.py` 帶 UTF-8 BOM(`ruff format --check` 報;非 gate)—— 順手批去 BOM。
- [ ] next-time:758(跨 UTC 06/22 邊界推播)本輪 20:1x 起跑仍未跨邊界,**未驗**;`spikes/nk225_leg_probe.py`
  可帶 `--listen-secs` 拉長在 13:5x 起跑順帶驗。

## 2026-08-17(mod/index-intraday-core batch3 R4 留尾)

- [ ] **真 TC4 指數推播下的 core 圖 + 個股頁 / 群組圖牆前後對照待 prod 重啟過目**(側車 fake 序列已驗;
  SC-5 截圖層未做:FakeStockSource 無個股資料)。〔2026-08-20 真 TC4 全日線截圖已存(加權/櫃買
  分時 + 均價/CDP/MA 全開):docs/specs/next-time-mcp-verification-2026-08-20/screenshots/
  48-overview-intraday-overlays.jpg,「平不平」你看圖拍板〕看點:對稱 autofit 域含 ±1% 地板 —— 加權日振幅 < 1%
  時線的視覺振幅比舊「hi×1.003 / lo×0.997 緊貼域」小(spec §5);若 user 覺得太平,候選 = index 態
  幾何加「地板 %」參數(core `buildIntradayGeometry` 需開 option,另案)。
- [ ] **兩欄態較矮視窗(容器 ≥ 1050 但主 grid 高 < ~800px)家數帶 section 溢出走主 grid 捲軸**(KR-3,
  code review C-3):`--idx-adl-min` 10rem 地板 + 家數帶兩列固定 chrome ≈ 306px > 分到的 5/11。1080p /
  864p 實測不捲;命中再降地板或 section 改 `5 1 auto`。〔2026-08-20 機械實測釘邊界:1536×700
  主 grid 622/676 = 54px 捲軸、溢出源家數帶 section 262/316;1536×864 = 786/786 不捲〕
## 2026-08-17(mod/positions-pnl-display batch3 R3 留尾)

- [ ] **側欄 chip 過長時股名被 truncate 到看不見**(2330 有現股 + 雙契約個股期:`2張 +0.26% · 期 2口/空1口`
  在 240px 側欄把「台積電」整個擠掉;AD-6 拍定「名稱 truncate、chip shrink-0」)。user 過目後若嫌,候選:
  期段收進 tooltip 只留 `· 期`、或 chip 上限寬 + truncate。〔2026-08-20 實測:現況純現股短 chip
  (「1張 —」28px)零 truncation;極端 case 需現股+個股期並存部位才會重現〕
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
- [ ] **▲/▼ 可見度**待 user 過目:尺寸沿 `INTRADAY_MARK`(外緣 3px 級),fake 鋸齒價線下 ▼ 綠疊
  綠線不易辨識;真盤若仍不顯眼,調 `lib/fill-marks.ts::FILL_MARK` 或 halo 色(一行)。
  〔2026-08-20 真成交截圖已存:6456 尾盤 ▲、6451 ▲+▼(686px 圖上 6×5px 三角);
  docs/specs/next-time-mcp-verification-2026-08-20/screenshots/63-fill-mark*.jpg,顯不顯眼你看圖拍板〕
- [ ] **toggle 關態 `EMPTY_MARKS` identity 無機械閘**(cr1 B-p2-3 rejected:關態沒有可計次函式);
  症狀僅掉幀。若日後改 ChartStatic memo 契約,順手補 render-count 閘。

## 2026-08-17(mod/ladder-market-buttons batch3 R1 留尾)

- [ ] **D4 現股市價安全首單未做**(user 盤中):現股 `nSpecialTradeType=1 + bstrPrice=估價 + ROD` 端到端從未 prod 驗;
  首單 = 低價股 1 張市價買/賣 → 群益 APP 核對成交型別 + 委託列表「市價」標籤 → 截圖回填
  `.claude/mod/ladder-market-buttons/verification.md` §4。個股期 / 期貨市價鈕(limit@貼漲跌停 + IOC,
  走 `/api/capital/order/future` 經 `_stkfut_gates`,**與平倉路由不同**)prod 首發同待。
- [ ] **委託列表「市價」標籤的日界語意**(KL-4):`store.note_price_type` 記本機日曆日,`_price_type_of`
  要求與回報 `_Agg.date`(委託建立日)相等;夜盤跨午夜 / 盤後預約單未實證 → 不符只缺標籤不誤標。
  收斂候選:交易日口徑(`trading_calendar`)或 ±1 日窗(與前端 `ymdWindow` 同口徑)。
- [ ] 真市價 literal `"M"` 給個股期 / 期貨市價鈕(D3b):prod 實測 `"M"` 可送後可從 limit@邊價切回;
  屆時 OrdersList 標籤對這兩梯才會出現(現在 wire 就是限價 IOC,不標)。
## 2026-08-17(mod/ladder-pills-avgpct R6 留尾)

- [ ] 群組平均漲幅**不設覆蓋率門檻**(review C4 auto-default):1/10 檔有成交仍顯示,靠 title「n/N 檔有成交」
  可查證;若 user 盤前掃側欄覺得誤導,候選 = n < ceil(N/2) 時降 ink-dim。

## 2026-08-17(mod/flash-arm-lock 留尾)

- [ ] **鎖定態換標的 / 換梯的掛載瞬間禁送窗**(spec E-8 / R-7 / R-8,review 建議 (b)):鎖定拿掉了
  「換標的必須重按武裝」的時間緩衝,新梯掛載即直送態、座標與前一梯重疊,主圖五檔
  `stock-price-click` 也會把使用者帶到已武裝且置中的梯。候選:換 instrumentKey / 換梯後前
  N 百毫秒點價只 hint 不送(沿 `lastClick` 防抖機制),需新 SC → user 拍板。
- [ ] **鎖定態全域指示器**(spec R-3):停在 TXO / 指數頁或右欄委託 / 部位 tab 時畫面上沒有任何
  「鎖定中」訊號,回到梯上才看得到。候選:RightRail tablist 旁小徽章(UI 拍板)。
- [ ] **CapitalConfirmDialog 開著時 Esc 不解除鎖定**(spec R-6;next-time:190 既有語意的鎖定版):
  窗內 stopPropagation → 鎖定中 + 平倉確認窗開著時 Esc 只關窗。改 capture 監聽屬 🔴,另案。
- [ ] **未鎖定時「WS closed 期間仍可武裝」的既有邊沿語意**(spec review R1 衍生):鎖定鈕已在非 open
  時 disabled + level 觸發,武裝鈕未跟進(維持既有);要一致化可把 `armDisabled` 也吃 wsStatus。
- [ ] **後端 source="flash-locked" 稽核**(spec §8):payload source 可擴,讓審計檔看得出鎖定態送單。
- [ ] `FuturesLadder.tsx` 內 `futExchangeContract` 未 try/catch(App.tsx 那份有;既有問題,review p2 (d))。
## 2026-08-17(mod/group-grid-full-chart R4 留尾)

- [ ] **群組圖牆真 TC4 層待 prod 重啟 + 盤中 user 過目**(PR 試用指引):卡片單檔同款圖(VWAP 標 /
  VP+POC / 高低 / CDP·MA)、圖牆頂 toggle 列同步、點卡片只換閃電目標。盤中順量:冷 cache
  進群組 overlay 真耗時(route Semaphore(4)+ 15s 逾時降級)、50 檔 group-state 真 payload
  (fake 17 檔 319 KB → 換算 940 KB;上界 1.5 MB)、liveP 每秒真機 paint 成本(fake 量到 JS
  longtask 0,paint 未含)。〔2026-08-21 M0 盤中實測(prod build,12:35,航運 6 檔):
  `group-state` 6 檔全日 217 分鐘 = 92.9 KB(每檔 15.5 KB,含 vp)→ 50 檔換算 **≈ 775 KB**
  (低於 940 KB 估,在 1.5 MB 上界內);`/api/stock/overlay` ×6 並發各 12–19 ms(磁碟 cache
  命中,日線 date=2026-08-20;真冷 cache 須清 cache 才量得到,盤中未做);rAF 45 s 2670 幀 =
  **60.0 fps**、PerformanceObserver longtask **0**。另觀察:群組檢視會觸發成員 tick 回補
  (log 12:36 2609 29772 / 2615 12451 / 2606 3117 ticks),非只讀。〕
- [ ] **1080p 4×4 卡片刻度互疊**(SC-1-4x4-1080p 截圖):卡 266×182 px 時左緣 11 條 y 刻度成團、
  右緣 CDP/MA 標籤疊。R2-1 決議不動共用 ChartStatic(W-1);候選 = card 變體 y 刻度減量(±10/6/2 三條)
  或 chrome 依可用高分級。user 實機 2560 寬 4×4(430×262)可讀。
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
- [ ] **交易日盤前(00:00–08:30)冷啟動仍空圖到開盤**(spec KR-4 / Q3-R8):long-running
  server 不受影響(兩段式 rollover stage2 前不清狀態),但那個時段**重啟**的話 source
  日窗 = 今天而今天還沒開盤。要做需同時對齊 stock stage1 08:00 / index 08:30 /
  breadth streak 06:00 三個時序 → 待 user 決定是否開 R3b。
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

- [ ] **期貨態 POC(D6 若 user 要)**:需 `foldVp` 分鐘窗參數化(現硬編現貨窗)+
  期貨態 vp toggle 解禁,連動 stock_state 折入層;本輪拍板 POC 僅現貨態。

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
- [ ] **R7 時間窗代價兩面**(2026-08-22 fix/balance-collector-owed-count 改口):(a) 真空帳戶在死查詢後最晚下一輪(≤60s)才顯示無部位(刻意);
  (b) **窗外(>`STALE_WINDOW_S`=20s,未量測)才遲到的舊輪零列 `##` 仍會把有庫存清成空集合**(最壞 60s 自癒)—— 不是只影響真空帳戶。
  若 prod log 出現「忽略放棄輪遲到的終止符」後接部位瞬清,代表 20s 窗太短,量到實際延遲再調。
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

- [ ] **確認窗開著時 Esc 不再解除階梯武裝**(刻意:窗內 Esc 以窗優先,stopPropagation
  擋掉三處 window 層 Escape 監聽 FuturesLadder:243 / PriceLadder:310 / StkfutLadder:235)。
  窗關後階梯仍武裝,靠第二次 Esc 或 idle 計時器解除;若 user 反映心智模型脫鉤,替代
  設計 = 拿掉 stopPropagation、改三支階梯的 listener 自查 `document.querySelector(
  "dialog[open]")` 再決定 disarm(動 4 檔,獨立輪)。
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

## 2026-08-06(market-overview-r4-sector-signals 收尾留尾巴)

> **〔2026-08-16 部分作廢〕** R4 類股強弱 / 訊號時間軸 / 全市場鎖板事件已整組刪除
> (mod/remove-sector-timeline)。下列 9 條中,**除「同頁 stale 標記兩款並存」外的 8 條**
> 全部失去標的、不再處理;該條的 SectorSection 已隨刪除消失,但 BreadthBand(bull 色
> 「資料延遲」)vs LimitListSection(amber「延遲」)的不一致仍在,條目改寫為只提這兩者。

- [ ] **同頁 stale 標記兩款並存(仍成立)**:BreadthBand 是 bull 色「資料延遲」,
  LimitListSection 是 amber「延遲」— 視覺是否統一待 user 過目時定。
## 2026-08-06(market-overview-r3-limit-list 收尾留尾巴)

- [ ] **user 過目待做(SC-3/4/5 雙層之二)**:綜合 tab「漲跌停」收合區塊(家數帶之下、
  相關係數之上)— 展開後篩選列(上市/上櫃/漲停/跌停/觸及未鎖 + 金額(億)/股價區間)、
  表格九欄(3081 聯亞當日顯示「連 5 板」)、點列跳個股 tab。AI 截圖六張在
  `.claude/feat/market-overview-r3-limit-list/evidence/SC-{3,4,5}_*.png`(盤後真數據)。
- [ ] **SC-5 盤中層待驗**:點列表任一檔跳個股 tab 後五檔開始跳動(需 prod server +
  盤中;截圖層已驗 tab 切換與主圖標的設定)。
- [ ] 跌停連板數欄(Q4 拍板不做)、列表迷你預覽(D-5)仍在 next-time 池。

## 2026-08-06(market-overview-r2-finmind 收尾留尾巴)

- [ ] **user 過目待做(SC-4 雙層之二)**:綜合 tab 中段家數帶(上市/上櫃 × 漲停/上漲/平盤/
  下跌/跌停,漲停紅底/跌停綠底,戳記「日期 · 時刻」)+ 騰落線(0 軸、末值標籤)。
  AI 截圖三張在 `.claude/feat/market-overview-r2-finmind/evidence/SC-4_*.png`(盤中真數據)。
- [ ] **SC-1 的「neigui panel 畫面同分鐘截圖」層未做**(panel 未在跑;數字層已以
  neigui 現碼即時對照等價驗過,見 evidence/SC-1_live-parity.txt)。要補就任一交易日
  兩邊同開比對一次;純 optional。
- [ ] **WS /ws/breadth 無 enabled 欄**(review 波一偏離 3):boot 未完成時 WS 送一則
  載入中 scalar 再關,前端靠退避重連自癒;R3 若要前端據 WS 顯示載入中,payload 補欄位。
## 2026-08-06(market-overview-r1-tab Phase 6 real-env 沉澱)

- [ ] `MarketPane.tsx` 七個 localStorage 呼叫點裸奔無 try/catch(review SI-2,
  rejected — design 明文「照抄現邏輯」):storage 被政策鎖時預設頁首 render 即白屏,
  且全 frontend 零 ErrorBoundary。要修就抽 `@/lib/storage`(`readKey` / `writeKey`,
  讀寫兩側都包 try/catch),既有同型 try/catch(`App.tsx::initialStockCode` 的
  setItem/removeItem、`hooks/useChartToggles.ts::persist`、
  `LimitListSection.tsx::loadFilter` / `persistFilter`)一併收斂。
  (原文引用的樣板 `CorrSection.tsx:18-34` 已於 2026-08-16 subtab 退役時刪檔。)
- [ ] 舊存檔 `copycat-market-key="OTC"` 的使用者升版首載左右兩張都櫃買(review SI-3,
  rejected — 點一下左圖「加權」即永久自癒):若真嫌,IndexPage 做一次性 seed
  (MARKET2_KEY_STORE 未設時依左值選互補標的),冪等不引入持續耦合。

## 2026-08-06(stkfut-contracts 題3 收尾留尾巴)

- [ ] **個股期功能待 user 過目**(PR #28 試用指引):合約下拉/分時五檔切換/個股期梯截圖
  四張在 `.claude/feat/stkfut-contracts/evidence/`;**真送單驗證 = prod 安全首單**
  (遠價 1 口 → 群益 APP 核對 → 刪單,§7);首個交易日順看 08:45–09:00 期貨分時有資料
  (夜盤訂閱窗假設的 prod 觀察項)。
- [ ] **_symbol_to_key/_states 隨瀏覽合約單調成長**(review A7c,量級無害僅記錄)。
- [ ] **OrderBook 元件層無合約簿專屬斷言**(review B8;hook 層已鎖,截圖層已過 —
  若日後改 OrderBook 資料源,補一條)。
- [ ] **catalog 冷查詢持 api.lock 秒級**(review A3 已以開機預熱緩解;若 prod 觀察到
  盤中首開下拉造成 TC4 斷線,升級為獨立 session)。

## 2026-08-06(group-grid 題5 收尾留尾巴)

- [ ] **群組檢視待 user 過目**(2026-08-17 註:mini 圖已由 R4 換成單檔同款,±10% 域議題消滅,過目改看 R4 條目)(PR #27 試用指引):個股頁「單檔｜群組」pill、mini 分時圖牆、
  點卡切檔;盤中 Discord 訊號同群摘要實發。過目時順看:mini 圖沿用 ±10% 漲跌停域,
  1% 波動僅 ~3.4px(主圖 1/5.5)— 若「看不出誰在動」,候選解 = mini 圖改 autofit 域。
- [ ] **reconnect 不清 `_backfill_failed`**(fix 輪 deviation 2):斷線期間成員連 3 次
  回補失敗 → TC4 重連後該檔當日不再入列(主圖不受影響)。一行
  `self._backfill_failed.clear()` 於 `_handle_reconnect` 可解。
- [ ] **rollover stage1→stage2 窗 `_backfilled` 殘留**(review B3-e):停在兩段之間
  (開盤前/假日)時群組成員不重回補;正常日首 tick 觸發 stage2 後 60s 自癒,假日無資料
  可補 — 影響低,記錄備查。
- [ ] **apply_backfill reset+replay 競態範圍隨 guard 去 main 化擴大**(review B3-f):
  SubHistory 與套用之間到達的 live tick 被洗掉,現及於全部自選成員(每檔每日一次 +
  60s 輪詢自癒)。若盤中觀察到卡片閃缺分鐘,從這裡追。
- [ ] **同步率 badge / CorrState 掛群組卡片**(brainstorm auto-default 未做):全配對
  成本趨近零,掛不掛看 user 用過 grid 後的需求。

## 2026-08-06(signal-rules 題1 收尾留尾巴)

- [ ] **規則 UI 待 user 過目**(PR #25 試用指引):訊號欄「監聽規則」區 + 規則 Dialog
  (新增/編輯/刪除/開關);盤中自訂規則真 tick 觸發 + Discord 文末規則名實發。
- [ ] **關閉規則的歷史列視覺弱化**(design R14a 記帳):filterKinds 移除後關閉規則當日
  已發的列仍顯示(帶規則名可辨識);若 user 覺得干擾,補 per-rule 淡化或「只看啟用」勾選。

## 2026-08-05(intraday-volume-profile 題2 收尾留尾巴)

- [ ] **VP 畫面待 user 過目**(PR #22 試用指引):個股頁分時圖左緣水平量條 +「量分佈」toggle。
  AI 截圖三張已入 `.claude/feat/intraday-volume-profile/evidence/`。
- [ ] **外內盤分色 VP 未做**(quintet 拍板選配):`VpCell` 已帶 o/i 資料,渲染層與 toggle 未接線;
  做之前留意鎖停日 side 判定品質(LOW_DECIDED_PCT 議題)。
## 2026-08-05(signal-rules 題1 code review 尾巴)

- [ ] 🔵 **`SignalDetector` 的暫存基準家族已無呼叫端**(`set_staged_basis` /
  `clear_staged` / `swap_staged_basis` + `_staged` / `_staged_date`):規則化之後暫存區
  與日別判定整組移交 `SignalHub`(基準快照歸 hub 唯一持有)。真移除屬純結構改動,
  本輪只在 `signal_state.py` 模組 docstring 標了「不要回頭呼叫」(review B4)。
  動的時候 `tests/live/test_signal_state.py` 的對應測試一起刪。
- [ ] **`default_rules` 的 `time.time()` 與注入時鐘不一致**(review A6(3),僅測試可觀察):
  遷移種子的 id epoch 走真實時鐘,hub 其餘各處走 `now_fn`。要收斂就把 epoch 當參數傳進去。
- [ ] **30 條規則的熱路徑成本未量測**(review A6(6),design 已知):per-tick N × evaluate,
  上限 30 是 REST 可寫入的無界量守門值;真要壓成本得先量 tick 密度尖峰。

## 2026-08-05(discord-watchlist 題4 收尾留尾巴)

- [ ] **SC-4 Discord 實發待 user 過目**(prod 重啟後,試用指引見 PR #21):`/watch add` 的
  group 欄 autocomplete 選單、`/watch groups` 空群組與衍生標注、group add/rename/remove 全鏈。
- [ ] **群組名長度 / 群組數上限未加**(review A2 縮範圍,user auto-default 記錄):回覆層已以
  1900 截斷 + send 防護兜底,超長名只影響觀感不再永久卡死;真要根除在 `normalize` 加
  name ≤ 32 / 群組數 ≤ 30,`_CHOICE_NAME_LIMIT` 的略過分支順帶變不可達防禦。
- [ ] **讀時遷移 orphan union 理論可推破 30 上限**(design Known Risks):該態下群組操作
  大聲拒絕(`WATCHLIST_UNAVAILABLE`)、自癒 = 前端整份 apply;僅手改檔可達,不加遷移端 cap。

## 2026-08-05(bars-tristate-status 收尾留尾巴)

- [ ] `StockChart.tsx` 的 isPending / emptyNote(timeout/disconnected)/ isError 三個
  佔位框 class 字串幾乎相同(僅文字與色差),可抽 `<ChartNotice tone text sub?>`;
  本輪為守「畫面零變」白名單未動(自評順手項)。
- [ ] `StockEngine.daily_bars`(overlay 路徑)與 `futures_engine.bars_range` /
  `index_engine.bars_range` 仍把 ConnectionError 吞成空且無原因 —— 與本輪修的是同一類病;
  market 頁三態誠實化已列本輪 change-spec Out of scope 1,做的時候 `BarsStatus` /
  `worst_status` / `_coerce_status` 基建都在 `server/bars.py` 可直接沿用。
- [ ] 本輪 Known Risks 1:TC4 查無此檔(常態表現 = timeout)前端會顯示「等待 TC4 回應中…」
  並每 20s 重試不收斂 —— 誠實但不收斂,若實用上煩人,候選解 = 連續 N 輪 timeout 後
  降級弱提示(「多次未回應,可能查無此檔」)。
## 2026-08-05(stock-intraday-autofit-range 沉澱)

- [ ] **autofit 分支的畫面待盤後實看**:本輪改的路徑(無 meta → autofit 域含當日高低)盤中不可達
  (盤中個股帶 meta 走漲跌停分支),目前以 SC-3 臨界回歸測試(2330 2026-07-30 實例數字)+
  元件測試(day-high circle 由不畫變畫)代替。盤後開個股頁看任一檔的高低標記即實看。
  白名單畫面證據:`docs/specs/stock-intraday-autofit-range/screenshots/2026-08-05-intraday-limit-branch-whitelist.png`
  (3481 群創,**漲跌停分支**,域恰為 [43.05, 52.5] 未被當日高 50.5 撐開;autofit 分支未入鏡)。
- [ ] **負域 cosmetic 風險(刻意不 clamp)**:對稱域設計下 `dayLow < ref×0.0909`(盤中跌逾 91%)
  時 yBottom 為負 → 3 點 fallback 刻度印負價位。±10% 制度下不可達、興櫃實務不存在;
  不 clamp 是因會破壞「域以 ref 為中心」的對稱語意(SC-4)。`ref=0`(無成交且無 metaRef)
  的另一條負域路徑已修(ref > 0 才併極值)。若日後真出現負刻度,從這裡追。

## 2026-08-05(capital-position-key-kind 收尾留尾巴)

- [ ] **store 鍵未帶 market**(round 1 review A-2 的殘留):鍵是 `(stock_no, kind)`,
  `position_for` 的 `market` 參數只收斂「掃描母體」,擋不住 sec 與 fut 兩列**股號與種類
  都相同**時的鍵碰撞(後到者勝)。實務上撞不到 —— 期交所契約碼必含英文字母、股號全數字
  (本輪想寫 fut 方向的測試就是卡在這:全數字契約碼過不了 `exchange_product_of`),
  且真撞到時 A-3 的重複鍵 warning 會叫。要根除就把鍵改成 `(market, stock_no, kind)`,
  代價是 `apply_profit_rows` 得寫死 `market="sec"`(損益試算報告本來就只有證券)
- [ ] 平倉 dup guard 未按 kind 細分(本輪 out of scope,白名單 5 的保守行為):同檔兩
  種類**同向**平倉時,第二筆會被「已有同向活躍委託」擋(委託回報沒有庫存種類這一維,
  活單掃描只能以標的比對)。要細分需先確認回報端能否還原種類(sFlag / flag_label)

## 2026-08-05(txo-contract-last-price Phase 5 review 沉澱)

- [ ] **TXO 市價估價的 reset 窗 UX**(review S-1,P1 判為 Known Risk 不擋本輪):
  `last_price` 掛在會被 `reset()` 清空的累積狀態上 → 序列切換 / self-heal / rollover
  後 `contracts` 會空到回補完成(數分鐘),期間市價鈕鎖回、**已開的確認框因
  `premium != null` gate 靜默卸載、`handleConfirm` 靜默 return** —— 方向是 fail-safe
  (估價消失 = 回到本輪前狀態,送單走 literal M 不受估價影響,不會送錯價),但
  **零訊息**,user 只會看到「按了沒反應」。後端保留 last_price 跨 reset 無效(row 本身
  隨 `_pos` 消失,單保價值救不回 row)。修法 = 前端獨立輪:dialog gate 拆分 +
  `setSubmitError`,或 `status=backfilling` 時沿用上一份估價並標示「回補中」

## 2026-08-04(stock-signals Phase 6 沉澱)

- [ ] 訊號 Discord 文案帶的是 tick 時刻(模擬/回補情境會顯示過去時刻)— 若 user 反映
  「太慢了」是指希望帶發送時刻或兩者並列,屬文案調整一行事。

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

## 2026-07-18(txo-aggregate-pnl Phase 4 自評 P2 彙總,10 條聚類)

- [ ] engine._run_handover 重試時 re-subscribe 與 activate 的 unsubscribe 不對稱,若改主動觸發自癒要先收斂這段

## 2026-07-21(stock-terminal Phase 4 自評 P2 彙總,13 條聚類)

- [ ] 個股 stream 韌性候選:hook pending 重放只驗 seq>S 不驗連續性(回補期 WS 掉訊成永久缺筆);fromSnapshot 以 vwap×cum_vol 還原 VWAP 分子與後端 Σq 分母有近似差;apply_backfill 對回補列不去重(TC4 重送列會雙算);tc4_status 只靠 on_reconnect 復位(純 REQ 失敗 banner 永久誤掛)
- [ ] 個股 UI 盤後體驗:reset() 保留 book 與 design 字面不符(rollover 後非觸發檔殘留昨日五檔)。〔2026-07-31 盤點:**後半「盤後重載側欄顯示 `-`」已做掉**,可刪 —— `stock_engine` 連線種子逐檔送 `_quote_payload`,`ref` 欄在尚無成交時給參考價,`WatchlistSidebar` 已渲染「參考」態〕
- [ ] 個股效能/清潔候選:snapshot 每次全量序列化 20k tick deque(切檔/跳號 refetch 都全量 JSON);_states 永不清除;F:xxx 建立永不使用的 StockDayState;backfill TICKS 訂閱事後不退訂
- [ ] 個股雜項:健檢 in_trading_hours 在 subscribe 時判定而非 timer 觸發時(`stock_source.py:518-520`);watchlist 啟動時 TC4 離線可被 50 檔 × 10s(≈500s)拖慢 lifespan(`app.py::_boot_engines` 序列化,stock 段在 index/breadth 之前)。~~backfill 首頁 30s 逾時靜默回空無 log~~ 已由 08-21 R8 `raise HistoryTimeoutError` 解掉(2026-08-24 盤點縮寫)〔2026-08-13 上限 30→50 同步;**退出準則**:若實測 TC4 離線啟動致 index/breadth 就緒 >10 分鐘 → 做 per-code timeout 縮短 / 並行訂閱〕

## 2026-07-20(backfill 雙修 review P2)

- [ ] backfill_finmind/backfill_daytrade 空日不進 marker 後,真假日在重跑同 range 時會反覆重抓(range 約 11 個月含 100+ 週末假日);若 FinMind 配額吃緊,疊加靜態台股假日曆只重試「非假日空回應」

## 2026-07-28(stock-ui-upgrade Phase 4 review P2 彙總)

- [ ] PriceLadder 全域 rows(最壞 ~200 列)無上限 lock 測試;若低價股(tick 10 毫元、±10% = 2000 列)出現效能問題再虛擬化
## 2026-07-28(capital-order Phase 3 順手清單)

- [ ] 期貨平倉「範圍市價 P + IOC」候選:prod 實測 bstrPrice="P"/"M" 可送性後,可從限價貼漲跌停切回(docs/research/2026-07-28-skcom-typelib.md)
- [ ] TXO 市價單確認框金額 = **估算**,冷門履約價可能是舊價:`snapshot.contracts[].last_price` 是該合約當日**時序最後一筆成交價**、無時效標記(2026-08-05 /mod txo-contract-last-price 拍板 out of scope)。深價外履約價可能整個上午沒成交 → 確認框「預估權利金」與安全閘 `safety._check_qty_amount` 的名目金額都吃到數小時前的價。**送單本身不受影響**(市價走 literal M,`capital/mapping.py:161`,價格不是我方帶的);要收斂的話候選 = last_price 帶成交時刻 + 前端超過 N 分鐘標示為舊價
- [ ] 選擇權閃電梯(本輪 out of scope,TXO 表單已群益化)
- [ ] 群益回報自動重連(本輪拍板不做;做之前 store 聚合非冪等 → 必先 clear 再重播 backlog)
- [ ] OnAccount / OnOpenInterest 欄序為 prod 未實測假定(com.py `_parse_account_row`、balance.py `parse_open_interest_line` docstring 已標)— 首次 prod 登入核對後校正

## 2026-07-28(capital-order Phase 4 code review round 1 追加)

- [ ] COM 卡死 stalled 心跳偵測(review B7):寫入 timeout 連發 / 幫浦圈停擺目前只靠 log,需心跳觀測基建(status 加 last_pump_ts + watchdog 降級);監控面非正確性,本輪 deferred
- [ ] 期貨改價 `CorrectPriceBySeqNo` 末參數 nTradeType=0(ROD)對期權 IOC/FOK 單的影響 prod 首驗(review A6;test 沙盒未開通不可先驗)— 若群益端把改價後 TIF 重設為 ROD,IOC 單改價語意會變
## 2026-07-29(trade-layout-rework 順手清單)

- [ ] K 線 endpoint 未做 inflight dedup(專案 `_run_once` 慣例):同 code 併發請求會各自打一輪 TC4。單人本機用量下未觀察到問題,若之後多分頁/多 client 再補
## 2026-07-29(stock-ui-round2 批一 順手清單)

- [ ] **批二(user 已拍板拆兩批)剩一項**:項 9 閃電梯跟隨置中(判定為描述現況,
  待 user 確認是否有症狀;定位(2026-08-24 更新):`LadderView.tsx:140-165` 的 `follow` state 與
  `centerPrice` 的 scrollIntoView effect(已從 `PriceLadder.tsx` 搬出,行為未動)
  - [x] ~~項 13 閃電梯部位 + 未實現損益 + 含成本打平價(需新增手續費折數設定,user 拍板
    預設 6 折)~~ **2026-08-05 已出貨**(feat/ladder-position-pnl):部位條(卡片底部,
    誤送風險考量不放梯上方)+ 梯內打平/均價標記 + 折數設定(標題列,localStorage
    `copycat-fee-discount`);**折數 user 實答更正為 1.8 折**(原「6 折」記載過時);
    計算含證交稅 0.3% 固定 + 融券借券費 0.08%;`lib/ladder-position.ts` 純函數五組手算例釘住
  - [x] ~~項 12 自選側欄重做(預設群組取代「全部」+ 顯示名稱 → 需後端 `watchlist_quote`
    加 `name` 欄位,跨檔契約改動)~~ **2026-07-31 盤點:做掉了,但走的是另一條路** —
    側欄已改為「未分組 section + 逐群組 section 並列」+ `WatchlistManagerDialog`
    (`WatchlistSidebar.tsx:458-555`),後端 schema 升 v3(未分組 = `codes − ∪groups` 衍生
    不另存);名稱改由 `/api/stock/names` REST 供應(`useStockNames.ts` → `WatchlistSidebar.tsx:76,99,282`)。
    **`watchlist_quote` 至今仍沒有 `name` 欄位 —— 原記載的跨檔契約改動不需要發生**
- [ ] K 線「走到 30 日前第一根」的取用路徑偏長:1 分 K × 30 日 ≈ 5,900 根、最大視窗 700 根、
  初始 240 根 → 從右端拖到最左端約需 8 次滿寬拖曳。本輪刻意不加捷徑(雙擊回最右 / Home
  跳最左屬新互動,scope 紀律)。真用起來嫌煩再開
- [ ] 拖曳平移每次 mousemove 都重算 `buildCandleGeometry` 並 diff 整個 ChartStatic;
  700 根時約 2,100 個節點。目前靠 MAX_VISIBLE=700 + memo 修復壓住,真環境拖曳掉幀再改 rAF 節流
- [ ] 布林通道填色用 `fill-ink-muted` 0.07,在 20 期低波動段會蓋成一大片灰塊;
  若嫌干擾可改只畫上下軌不填色,或降到 0.04
- [ ] `MINUTE_INIT_BARS = 240` / `DAILY_INIT_BARS = 120` / `MAX_VISIBLE = 700` /
  `ZOOM_STEP = 1.15` 四個常數分散(**2026-08-24 盤點:已擴散到四檔** ——
  `StockChart.tsx:24-25` / `FuturesChart.tsx:50-51`(同兩支 INIT_BARS 複本)/ `lib/candle-viewport.ts:14` /
  `hooks/useCandleViewport.ts:13`);
  若之後要做「可設定的圖表偏好」再收斂到單一 config

## 2026-07-29(stock-ui-fixes 順手清單)


## 2026-07-30(realtime-correlation 收尾沉澱)

- [ ] TCPY 路徑運算式 `Path(__file__).resolve().parent.parent.parent / "spikes" / "TCPY"` 在 production 重複兩處(`live/tc4.py:148`、`data/backfill_tc4.py:104`;原第三處 `live/tc4_trade.py` 已於 2026-08-04 隨舊 trade 路刪除),`tests/conftest.py` 的 `TCPY_DIR` 是第三處。當時刻意不抽共用常數(P2 測試層 bug 不動 production 檔)。**收斂條件**:出現第四處、或 `spikes/TCPY` 位置要改時,抽 `copycat/tc4common.py` 的 `TCPY_DIR` 單一定義,三處都引它。
- [ ] realtime-correlation 訂閱窗的**反向**驗證仍未做:「沿用 `session_window` 會失效」是推論不是實證 —— 台指日盤窗(UTC 00–06)+ 夜盤窗(UTC 06–22)合計涵蓋 UTC 00–22,訂閱當下海外腿幾乎不會落窗外;真正的風險是「訂閱後跨過窗結束邊界(UTC 06 / 22)推播是否停止」。驗法:在 UTC 05:5x(台北 13:5x)前訂閱並持續監聽到 UTC 06:0x 之後,看推播是否中斷。全天窗實作本身已是防禦性選擇,此項只影響「基底 source 是否也該改」的判斷。
- [ ] `corr_state.correlations()` 每腿每次重建 `leg_by_ts` dict(1800 entries)、每窗各過濾一次。實測滿窗 tick 6.43 ms(門檻 200 ms)不構成問題;若日後窗長或腿數放大再看。
## 2026-07-30(index-river-chart 收尾沉澱)

- [ ] 內外盤能量副圖:1K row 實測帶 `UpVolume`/`DownVolume`/`UpTick`/`DownTick`,
  live REALTIME 也有 `TradeQuantity` + 五檔可判內外盤 → 江波圖副圖(量柱 / 內外盤)
  資料齊備,本輪 user 拍板不做。要做時注意六腿量單位不可比(各腿自己歸一)。
- [ ] `river-chart-svg.ts` 與既有 `index-chart-svg.ts` / `stock-intraday-svg.ts` 三份幾何
  模組結構相似(x 等分 / autofit / 平盤線 / 時間刻度)。本輪刻意不泛化既有兩支(已上線
  且窗寫死 09:00–13:30)。**收斂條件**:出現第四份、或既有兩支需要可變窗時,抽共用
  `window → toX/toY` 層。
- [ ] `_collect_history`(**2026-07-31 更正:已自 `stock_source` 上提到 `live/tc4.py:337`**)
  與 `river_backfill.collect_1k_minutes` 是同型邏輯的兩份實作(前者服務 K 線 / overlay
  且參數已被四個呼叫點綁住)。若第三個回補路徑出現,以 `collect_1k_minutes` 的
  「吃 bound method」形狀收斂。
- [ ] `_schedule_backfill` 覆寫 `_backfill_task` 參照:兩次快速重連可能留下 close() 不會
  await 的孤兒 task(inflight 旗標在第一個 await 前設定,重入窗極小;孤兒的 fetch 失敗
  已被 ConnectionError 攔)。要對稱化就比照 `futures_engine._leaf_tasks` 用集合 + gather。
- [ ] 江波圖每則 delta 重算全窗幾何(滿窗夜盤 840 點 × 6 腿);`timeTicks` 逐分鐘掃窗且
  每張卡各算一次。與既有 IndexPage 同款做法,未量到掉幀;真環境掉幀先量再改 memo。
- [ ] 台指腿的 live 分鐘桶用**本機時鐘**(futures_engine 的 `st.t` 在既有 bug 1 情境不可靠)。
  若本機時鐘與交易所差超過一分鐘,台指線會相對其餘腿位移一格。
## 2026-07-30(stock-ui-round3 順手清單)

- [ ] `_POLL_BACKOFF_START = 0.15` 與 `BARS_POLL_DEADLINE = 10.0`(**2026-07-31 更正:
  後者已去底線且與 `_collect_history` 一起上提到 `live/tc4.py:40,43`**)兩個常數是實測推得
  (有資料標的首頁 <1s 備妥),TC4 忙碌時的真實分布未量。若 real-env 出現誤判為空的
  頻率偏高,先量首頁備妥時間分布再調,不要盲目放大 deadline(那會把 60s 問題帶回來)。

## 2026-07-30(stock-ui-round4 自評 review 沉澱)

- [ ] 股票名稱表(`copycat/stock_names.json`)無自動更新:新上市 / 改名要手動 `python -m copycat refresh-stock-names`。若要自動化,考慮 server 啟動時檢查檔案 mtime > N 天才背景重抓(**不要**放進 request path,ISIN 頁 10 MB)
- [ ] `dropTargetFromPointer` 的 nearest-zone 在兩個 zone 距離相等時取先出現者(未定義偏好);群組間縫隙很窄時使用者感受不到,若日後 section 間距變大再定規則

## 2026-07-30(stock-ui-round5 沉澱)

- [ ] `WatchlistManagerDialog` 的群組列**沒有排序握把**(spec 草圖有 `⋮⋮`,但 SC-14 沒有「群組
  排序」這條 → 刻意不長沒有行為的 UI)。若日後群組變多想調順序,那時再一併設計拖曳語意。
- [ ] 側欄的零 PUT 判定用 `JSON.stringify(next) === JSON.stringify(wl)` 深度比較(W-22)。
  物件鍵序目前由 model 純函數保證一致,若日後有人改成從別處組 `Watchlist`(鍵序不同)
  這個比較會失效成「永遠不相等」→ 悄悄退化回每次都送 PUT。要更穩就換成逐欄位比較。
  〔2026-07-31 盤點:**已擴散到三處**(`WatchlistSidebar.tsx:104` / `WatchlistManagerDialog.tsx:87`
  / `StockPage.tsx:57`),鍵序假設的曝險比原記載大〕
  〔2026-08-04 查證:三處已收斂為單一函數 `watchlist-model.ts:25` `isSameWatchlist`
  (三呼叫點皆 import 之),鍵序風險單點化 —「擴散」不再成立,殘項只剩「單點換
  逐欄位比較」,價值低,降為條件觸發(真出現「永不相等 → 每次都送 PUT」退化再改)〕
## 2026-07-30(index-board 大盤看盤改造 順手清單)

- [ ] **期指分時走勢**(本輪 out of scope):大盤頁選台指期時「分時」鈕 disabled,自動落到 1 分 K。
  要做需接 corr/river 的分鐘序列當資料源(那條管線目前只餵加權/櫃買)
- [ ] **期指夜盤 K 線**:`FUTURES_MINUTE_DOMAIN = ("0846","1345","1350")` 只取日盤,夜盤(15:00–05:00)落在域外被丟。
  要做需決定 x 軸怎麼表現跨午夜(`aggregateBars` 跨日不合併)。
  〔2026-07-31 15:51 畫面確認:夜盤已開 51 分鐘,大盤頁台指期標題現價 43776 是**即時**的,
  但 1 分 K 最後一根停在 **13:45** —— 現價與 K 線不同源的落差在畫面上看得見〕
- [ ] **櫃買永久歷史庫存**:目前只有「本機當日合成」(server 啟動後由 MIS 5 秒快照累積,重啟即歸零)。
  永久化需要排程 + 落盤 + 長期維護,屬新 scope。/adhd 的 logistics/3am frame 都獨立提出這條
- [ ] **大盤頁「加權」在**盤後重啟 server 後**顯示 `-`**(原記載措辭不精確,2026-07-31 更正):
  `twse.p` 只由 REALTIME push 設定,但**盤中起跑的 server 盤後照樣有值** —— 15:52 實測
  加權 43119.75 / 高 43214.36 / 低 41610.41 / 昨收 39933.3 全部有值(該 server 13:20 起跑,
  state 留在記憶體)。真正的觸發條件是**盤後重啟**。
  - **watchdog 不會被污染**(subagent 查證):stale 判定只看 `_last_push`(僅 `_handle_quote`
    更新)與 `in_watch_window()`(09:00–13:25)。只要修法不碰 `_last_push`、不設 `stale=False`,
    種 `p` 對告警零影響。
  - **真正的風險在別處**:`fetch_day_minutes` 只有每分鐘 close → **只種得到 `p`**;
    `high`/`low` 用分鐘 close 取 max/min 會系統性內縮,`ref`(昨收)根本拿不到。
    要全補得再打一次 DK(CLAUDE.md 已實證 IX0001 DK 可用 748 根)。
    **只種 `p` 的話畫面變成「現價有值、高/低/昨收 `-`」—— 半修比不修更難解讀。**
    另 `TXO_BACKFILL_DATE` 休市模式下種出來的是別的交易日收盤價卻長得像現價;
    且需 guard `if self._twse.p is None` 才不會蓋掉已到的 live 值(`_retry_loop` 會再呼叫)。
  - 開工前先做可證偽的 2 分鐘實驗:盤後重啟 server 打 `/api/index/state` 確認 `twse.p` 為 null。
- [ ] **期指的高/低在大盤頁顯示 `-`**(2026-07-31 15:51 畫面再確認):`futures_engine` 的
  payload 有 `ref`/`upper`/`lower` 但沒有當日高低。**開工前必做一件事:dump 一則 TXF
  REALTIME 確認有無 `HighPrice`/`LowPrice` 欄** —— 資料源二選一不是實作細節:
  - `index_engine` 用 TC4 的 `HighPrice`/`LowPrice`;`live/stock_state.py` 則刻意**不用**
    (個股 REALTIME 的 33 欄樣本裡沒有這兩欄),改逐 tick running max/min。
    **期貨段有沒有這兩欄無實證**,`parse_stock_realtime` 也沒抽。
  - 有 → 照 `index_engine` 兩行取值,**小**;沒有 → 自算,但**盤中重啟 server 會低估
    當日振幅且零錯誤訊號**(期貨 `fetch_day_1k` 只回 `(minute, close)`,沒有 h/l 可回補;
    個股是靠 `apply_backfill` 重放 tick 補起來的,期貨沒有這條路),**中**。
  - **日 / 夜盤語意未定**:`cum_vol` 已是每時段重起算,高低要「全日」還是「當時段」是
    產品決策。走 TC4 欄位 = 接受平台語意;自算則要在 `_handle_quote` 的
    `tick.trade_date != st.date` 分支補 reset(現在只清 `resolved_ym`)。
  - **最容易漏的改動點**:`IndexPage.tsx:45-49` **自帶一份同名 local interface**(只有
    `p`/`ref`),不加這裡前端拿不到值;`<Quote>` 本身早已收 `high`/`low` optional prop(零改動)。
- [ ] `/api/market/diag` 診斷端點(/adhd 3am frame 提案,本輪判定非正確性必需):
  把三個標的 × 各週期的 cache key、entry 年齡、上次 upstream 呼叫時間與結果攤成一頁
- [ ] `MARKET_KEYS`(後端)與 `MarketKey`(前端 `lib/timeframe.ts`)是兩份手動同步的值域;
  第三個消費端出現時考慮 codegen 或 shared JSON(現況新增標的要改兩處)

## 2026-07-31(stock-ui-round4 Phase 5 自評 P2 彙總)

- [ ] 側欄 / Dialog / StockPage 三處 mutation 為 last-write-wins(K-4);pending 防護現況(2026-08-04 收尾 review F3 實測更正):StockPage 3 處有 `save.isPending` 防護、Dialog 僅「加入股票」建議列一處(:354),**Sidebar 零防護**(`commit()` 無 pending 檢查,拖曳 / × / 加入群組全裸)— 除跨元件並發外,同元件內連點 / 拖曳期間重複 PUT 亦未防〔2026-08-04 /bug 輪評估:與 K-3(fallback 狀態混淆)**非同根因**,修法域也不同(pending 防護 / 後端版本戳 vs 入口 gate),未併入該輪,維持本條待處理〕
- [ ] EMPTY_WL 危險窗封閉的成立條件是跨檔不變式(2026-08-04 收尾 review F1,`commit()` 早退 rejected_with_reason):現況全 repo 無 `resetQueries` / `removeQueries`、StockPage 永不卸載(App visited+hidden)→ watchlist query data 成功後不會退回 undefined,入口 + Dialog 同 gate 已涵蓋;**若日後**對 `stock-watchlist` 改用 resetQueries / 改 queryKey / 讓 StockPage 可卸載(gcTime 回收),危險窗會重開且測試零訊號 — 屆時再補 `commit()` 的 `data === undefined` 早退(repo 精神:不可達防禦 = 沒有測試覆蓋的死碼,見 WatchlistSidebar.tsx 拖曳 teardown 註解,現在不加)
- [ ] 自選載入失敗態側欄仍渲染空「未分組」區塊 +「拖曳到此移出群組」提示(2026-08-04 /bug 輪 Phase 7 截圖觀察):無寫入風險(無列可拖),純視覺突兀 — error 態可考慮整段收起只留錯誤文案
- [ ] 預覽非自選股後 `copycat-stock-main-code` 仍會記住它(K-1):重整後主區停在該檔而側欄無對應列可反白,後端 `_main` 長期掛在非自選 code(refcount 吃得下,不佔 50 檔上限)。〔2026-08-04 更名同步:key 已改 `copycat-stock-main-code`(`lib/constants.ts` MAIN_CODE_KEY);真正持久化點在 App.tsx 的 setItem useEffect,別被 LEGACY 遷移常數誤導〕
## 2026-07-31(stock-ui-round6:市價偽檔位 / 內外盤判定)

- [ ] **價差內成交(bid < 成交價 < ask)的判定**:2026-07-31 實測 4989 / 6207 這類近漲停股
  有約半數成交落在這裡。逐筆拆解顯示主因是**時序假影** —— 同一則 REALTIME 帶的五檔已是
  成交後的簿,`p=55700 b=55600 a=55800` 判 neutral 而 `p=55700 b=55700 a=55800` 判 inner,
  同一個價格因為簿的新舊而落到不同類。修法候選 = tick rule(比對前一筆成交價),
  但那是換一套演算法,要先有對照驗證窗。本輪由「判定率」欄誠實呈現,未修。
- [ ] **`0` 檔位是否只在鎖漲跌停出現**:實測只見鎖漲停一例(2327)。若集合競價期間
  或其他情境也推 price=0,`_best_limit_price` 的作用面會比預期大(方向仍正確)。
  下次碰到集合競價時段的簿快照時順手確認。
- [ ] **`relabel_locked_side` 只掛在 `apply_backfill`**:live 路徑靠 `_best_limit_price` 就夠
  (五檔有第二檔可退)。若之後出現「簿裡只有市價檔、連第二檔都沒有」的 live 情境,
  live 也會判不出來 —— 屆時再考慮把 relabel 提到 `ingest`。
  - 〔2026-07-31 15:5x 盤後畫面驗證:**修法在真環境成立**。2327 國巨(整日鎖漲停)
    內盤 5964 / **判定率 100%** / 外盤比 0.0% —— 對照 CLAUDE.md §8 記載的修法前狀態
    「全日 5450 張成交 `cum_outer = cum_inner = 0`、副圖整片灰、外盤比分母 0 算不出來」。
    2330(尾盤鎖漲停)判定率 98%〕

## 2026-08-03(candle-right-edge-hover /bug 輪 —— 新流程首驗)

- [ ] `_this_week_days` 兩個已知邊界(收尾 review P2-4,均為極低機率):`date.today()`
  同算式取兩次 + fixture 與 route 各自取 today,週日跨午夜起跑理論上可跨週變紅;
  docstring 宣告 n<=7 但無 guard。要根治得讓 route 的 today 可注入,成本不成比例,先記帳。

## 2026-08-03(stock-page-dedupe-deadcode /refactor 輪 —— 行為類發現與範圍外遺留)

盤點 artifacts:`.claude/refactor/stock-page-dedupe-deadcode/`(三份 findings + 計畫)。
以下 [behavior] 全部是 /refactor 中發現但**修了就改行為**的項目,要修走 /bug 或 /mod。

- [ ] `CapitalPositionsList.tsx:79` 損益額正號判 `pnl >= 0`(顯示 `+0`),與全站 pct 的
  `> 0`(0 不帶號)不一致 — 是否對齊屬行為微調待拍板;對齊時順帶決定「整數損益額」
  要不要也走共用 formatter(2026-08-04 frontend-dedupe-format 圈出,依三類分離不混入)。
- [ ] **跳過的 JSX / 參數化抽取**(plan review 裁定語意分岔,抽了即改行為或淨可讀性負值):
  D-8 漲跌色 tone(中性態四種落點刻意不同)、D-10 ToggleButton(off 態 hover 分岔)、
  D-13 GroupPicker(容器/stopPropagation/disabled 全不同;**側欄群組鈕 stopPropagation
  「點群組不換主圖股票」無測試背書** — 補測試後才值得再議)、D-14 suggest 列 JSX
  (aria-label 語意不同;本輪只收 SUGGEST_LIMIT)。
- [ ] **B-D6 `_on_*_threadsafe` 守衛 8 份 × 4 行**(四引擎 loop=None close 閘):語意單一
  定義有價值但 mixin 間接性 > 收益,暫不動;第五個引擎出現時再收。
- [ ] **L-5 backfill 首頁抓兩次**(stock_source 輪詢 `_get_history(...,"0")` 丟棄 first 後
  iter_qry_pages 又抓第 0 頁):每回補多一趟 REQ。修前必先驗 QryIndex 游標語意
  (拿 first 末筆 QryIndex 當 start 是否嚴格銜接),改壞會靜默少一頁。

## 2026-08-04(startup-names-futures-resub /bug 收尾留尾巴)

- [ ] **啟動窗內其他 REST query 的失敗終態未盤點**:本輪只修 `useStockNames`
  (refetchInterval 無資料 3s 輪詢)。同窗口失敗的其他 query(watchlist GET、capital
  poll 類已有 interval 天然免疫;一次性 staleTime Infinity 類才有險)若 user 再回報
  「某面板初載空、用一陣子才出現」,先套同款 refetchInterval 再查別的。
  〔2026-08-05 mod/startup-http-window 盤點補充:窗內落 error 終態且無 interval 的
  一次性 query 至少四條 — useSeries / useStockWatchlist / useSignalFeed today /
  useSignalRules(原 useSignalsConfig,signal-rules 起改指這條;皆 retry:1),
  需視窗重聚焦或重載才回復;lifespan 背景化後
  窗形狀從「連線被拒」變「503」,終態問題本身不變。另:窗內誤按序列切換會看到原始碼
  字串「切換失敗:HANDOVER_BUSY」(SeriesSelect.tsx:33 原樣印 error.message),中文
  文案候選與此條同批處理〕
- [ ] **`test_index_routes::test_ws_streams_index_payload` 既有 flake 窗被 boot 背景化
  略微放寬**(2026-08-05 觀測一次,全套 ×3 + 單檔 ×3 重跑皆綠):index 引擎 boot 回補設
  `_dirty` 後 `_broadcast_loop` 會推一則 `p=None` payload,ws client 若在該 flush 前
  註冊就收到它當首則。master 本就有同一 race,靠時序運氣繞過。修法方向:測試改吃「第一
  則非 None 的 payload」或 engine 對 `p=None` 的首推抑制;修時勿加 sleep 掩蓋。
  〔2026-08-06 R4 輪加證:全套又目擊 3 次(Task 2/7/8 各一,單檔與重跑皆綠),
  另一 implementer 定位到第二觸發路徑 — 牆鐘落在 09:00–13:25 時 watchdog 分支把
  `stale` 翻真 → `_dirty` → 搶在測試 quote 前 publish `p=None`。重現率已高到
  幾乎每次全套必中一次,建議升優先度處理。〕〔2026-08-16 mod/overview-onepage-corr-tab
  輪再加證:後端零 diff,全套 1 failed/2563 目擊同一 `None == 42039920`,單測 ×3 皆綠。〕
- [ ] **個股頁現價旁加漲跌額(絕對點數)**:本輪(mod/stock-price-prominence)只放大字級,
  % 旁沒有漲跌額;要加時連同 fmtPct 慣例一起看(2026-08-04 change-spec out of scope)。
- [ ] **三頁現價字級是否統一**:個股頁現價已改 text-3xl,期貨頁 FuturesPage.tsx L54 仍
  text-lg、指數頁 IndexPage.tsx L178 仍 text-2xl;是否統一由獨立決策,不順手改
  (2026-08-04 change-spec-review P2-4)。

## 2026-08-04(asyncio-socket-send-warning 收尾留尾巴)

- [ ] `relay` 收尾假設 uvicorn sansio 的 `writable` 恆 set(無 pause_writing → send_json 非懸掛點、cancel 必打進 generator):若未來 uvicorn 加回 write flow control,「懸在 send_json 的 generator 遺棄」路徑變可達,`_consume_ws_task` docstring 的「取消同時關閉 generator」不再成立(review async lens 附註)

## 2026-08-04(remove-tc4-trade-path 收尾沉澱)

- [ ] `copycat/live/trade_models.py` 瘦身候選:僅 `BrokerRejectedError` 與 `mask_account` 有 production consumer(皆 `capital/client.py`;2026-08-04 增量 review F5 全符號盤點)— 其餘全數零引用:`OrderRequest` / `millipts_from_price_str` / `price_str_from_millipts` / `to_neworder_param` / `TouchanceDownError` / `AccountInfo` / `OrderReport` / `parse_accounts` / `parse_execution_report` / `parse_fill_report` / `classify_is_sim`。動它時 `tests/live/test_trade_models.py` 對應測試同步縮,且先 grep 確認 capital 端沒長出新引用。
- [ ] `frontend/src/lib/trade-text.ts` 瘦身候選(review F3):`TRADE_ERROR_TEXT` 有 6 個無 producer 的 dead key(TOUCHANCE_DOWN / TRADE_NOT_READY / LIVE_DISABLED / CONFIRM_REQUIRED / PREVIEW_EXPIRED / SYMBOL_NOT_ALLOWED,一對一對應已刪的 _TRADE_ERROR_MAP)+ `orderStatusText` / `orderSideText` 已 test-only(唯一 production consumer 是被刪的 OrdersList/OrderConfirm)。**⚠ `INVALID_ORDER` 必留**(capital_api 仍回它);`tradeErrorText` / `shortSymbol` 是 useCapital 等現行 consumer 在用,不可整檔刪。`trade-text.test.ts:7-8` 對 dead key 的斷言一併清。
## 2026-08-04(ws-test-consolidation 收尾沉澱)

- [ ] `test_no_write_to_dead_transport` 其實有**兩個**獨立 flake 源(本輪實測):(a) 既知的 0.5s 固定收 frame 窗(全套負載下漏窗);(b) 新發現 — `_ws_handshake` 讀到 `\r\n\r\n` 即停,101 回應與 server 第一則 frame 落同一 TCP segment 時該 frame 被握手緩衝吞掉 → `sock.recv` 等到 5s timeout,實測 6 跑掛 1(≈17%)。**2026-08-24 盤點:源 (b) 已由 55d6f6af 收(既有測試改 `_ws_handshake_keep_rest` + `assert rest or sock.recv(4096)`);源 (a) 仍是 `test_ws_disconnect.py:179-186` 字面 0.5s 固定窗 + TimeoutError 即 break** — 改用同檔已有的 deadline 迴圈 helper `_recv_batches`(:298-311)即可。
- [ ] corr/river 兩路突斷測試讀 `engine._loop` private(engine 無公開 loop 取用面;repo 已有 `broadcaster._clients` 先例):若日後 `create_app` 透出 `corr_tick_secs`(現寫死 1.0 不經參數),兩路可改回純 source-driven 端到端 pump,一併移除 private 讀取。

## 2026-08-04(subscribe-retry-recovery 收尾沉澱)

- [ ] 三處重試迴圈都是**固定間隔無 backoff**(corr 10s / stock 10s / futures 10s,
  index_engine 另有 `_schedule_retry` 的 backoff)。TC4 長時間斷線時單檔 SUBQUOTE 要等
  `_REQ_TIMEOUT_MS`(10s)才失敗,實質退化成「每輪一次慢失敗」的串行慢輪 —— 不會打爆
  TC4,但 log 會持續刷同一行 warning。要不要加 backoff / 降頻,等真實斷線一次再看
  (現在改是猜)。與既有「index_engine `_schedule_retry` backoff 收斂統一」條目同批處理。

## 2026-08-05(futures-allday-tab 收尾留尾巴)

- [ ] **SC-3 真 TC4 量法待 prod 重啟後補**:merge 後 user 自然重啟 prod(新 code),跑
  `curl -s "localhost:8721/api/market/bars/TXF?tf=1&days=5&session=allday"` 數 bars
  (單交易日 ≈300 日盤 + ≈840 夜盤)、抽查 15:01 與 00:0x bar、13:45/15:01 相鄰;
  順帶補 design §1.2 的日 K 口徑實測(DK v 對照 1K 日盤+夜盤量)與 §1.1 Date 欄語意
  真資料核對。畫面同時 user 過目分時圖夜盤段是否前進。
- [ ] **OI 撐壓線在分時/分 K 模式幾乎恆在 y 窗外**(現價 ±0.3% 域 vs 撐壓 ±7%),實際
  只在日 K 看得到 —— 超窗不畫是 design 拍板(clamp 會誤導價位),但若實用上想在分 K
  看,候選解 = y 域 opt-in 擴展或圖緣方向指示箭頭。
- [ ] **30/60 分 K 桶終點落死區標 14:00**(review LF-5,既有大盤 tab 行為同款,白名單
  未動):桶涵蓋 13:01–13:45 卻自稱 14:00,要修需大盤/期貨兩頁一起(夾回段末 13:45)。
- [ ] **平倉確認彈窗補 danger 紅底**(review T6 偏離 1):prod 送單面,CapitalPositionsList
  有、ladder 沒有;引入 useCapitalStatus 需補既有測試的 status mock。
- [ ] `todayOf` 私有函式在 FuturesPage/FuturesLadder 各一份(4 行),收斂進 settlement.ts。
- [ ] **分時圖無資料時 y-tick 全 0 → React duplicate key console error**(Phase 6 fixture 實測
  3.5 次/秒;prod 有真資料不觸發)。**2026-08-24 盤點:K 線路徑已安全**(`candle.ts` `seen` 去重 + 空 bars
  回 `[]`,MarketChart 已委派 CandleChart);**剩分時 fallback** `stock-intraday-svg.ts:412-416`
  無條件 push `[yTop, ref, yBottom]` 無去重,三者皆 0 時 `StockIntradayChart.tsx:319`
  `key={`yt-${t.priceMilli}`}` 仍撞 → fallback 分支加 `seen` 或 key 帶 index 即根除。
- [ ] days=5 下 30/60 分 K 無歷史回看(初始視窗即全部;design Known Risk):要支援回看
  可對 n≥30 另發長窗 query。

## 2026-08-06(stkfut-order-channel /bug 收尾留尾巴)

- [ ] **`_stkfut_gates` / `_require_legal_tick` 的 `round(price*1000)` 對 ±inf 拋
  OverflowError**,route 的 `except ValueError` 不涵蓋 → 502 TC4_DOWN 而非 400
  (NaN 反而正確;quintet review C-5)。修法 = catch 併入 OverflowError 或先過
  `math.isfinite`。本輪抽共用 helper 時刻意不動語意,兩處呼叫點同一份修一次即可。
- [ ] **當沖 checkbox 不隨合約切換重置**(StkfutLadder `dayTrade` state;quintet
  review C-4):同元件的武裝鍵與口數都已 per-instrument 化,獨漏這格。
- [ ] **前端 `isOrderBlocked` 在 unit=null(對映表過期)時放行**,後端 multiplier_of
  兜底成 400 INVALID_ORDER —— fail-closed 但錯誤碼指向使用者參數,真因是伺服器端
  對映檔過期(quintet review C-3);建議分開錯誤碼(MAP_STALE 或沿用
  PRODUCT_NOT_ALLOWED)。
- [ ] **ws flake 家族新樣本**:`test_index_routes.py::test_ws_streams_index_payload`
  全套件跑偶紅(`twse.p == None`,快照先於 tick 送達的時序),單檔重跑綠、全套件
  重跑綠(2026-08-06 一次;與既有 ws_disconnect flake 待排查條目同批)。
- [ ] **quintet review 其餘 12 條 P2 尚未逐條入帳**(E-2/E-3/E-4/E-5、X-1/X-2/X-3、
  F-1~F-5、W-1~W-3;全文 `.claude/bug/stkfut-order-channel/` 同批 artifacts 的
  `review-findings.md`):review 建議優先 X-2/X-3/E-5(共用資源結構性)與
  F-2/F-3(鎖板場景/可用性)。E-1(P1,期貨回補 cum 假設)另案處理,
  第一步 = prod 停機窗跑 ticks_probe 對合約 leaf 印 TradeVolume。
  (2026-08-06 追記:E-2/E-3/E-4/E-5 已由 fix/stock-engine-p2s 批次修畢)

## 2026-08-06(stock-engine-p2s /bug 收尾留尾巴)

- [ ] **退訂清帳的秒級殘留窗(review A-1)**:在途/佇列中的 backfill job 完成時把
  `_backfilled`/`_backfill_failed` 寫回(generation 只在 stage1 bump,退訂不 bump)。
  完整解 = per-code 訂閱 epoch(退訂 +1,worker 套用前比對);窗長 = job 排隊 +
  SubHistory 往返(秒級),已在 `set_watchlist` removed 迴圈註解記帳。
- [ ] **stage2 提前後的開盤前空回補佔記帳(review A-2)**:合約 tick 08:45 完成
  stage2 → 群組輪詢在 09:00 前入列的現貨回補必為空,仍 `_backfilled.add` →
  疊加「重掛失敗由重試輪補上」時該檔缺口整天補不回。候選解 = `_backfilled.add`
  只在回補真的套用到列時記,或 stage2 後現貨開盤前不接受群組入列。
- [ ] **補市日(週六)+ 自選空 + 主圖合約仍整天不換日**:checkpoint weekday>=5
  不武裝、無現貨快路徑 tick;極罕見組合(E-3 修法註解已記載)。

## 2026-08-06(R4 round-2 復審 rejected 項與架構級遺留)

review 全文 `.claude/feat/market-overview-r4-sector-signals/code-review-round-2.json`。
accepted 13 組已修(同日 fix/r4-review-round2);以下 rejected / 遞延:
〔2026-08-16 註:R4 類股 / 時間軸 / 廣度事件已整組刪除(mod/remove-sector-timeline)——
XR-7、FE-4 隨之作廢;HR-6 / HR-3 / HR-5 是 hub 通用議題仍成立,但「漲停潮日數百則廣度
事件」的量級前提已消失,只剩自選規則訊號量級。〕

- [ ] **HR-6:WS 事件類訊息丟包無回補**(`ws.py` drop-oldest 對一次性 signal =
  永久遺失且不斷線,baseline 重抓只掛 onWsOpen)。候選:signal payload 加 seq +
  前端 gap 偵測觸發 invalidate,或 baseline 盤中週期重抓。R4 把漲停潮日數百則
  廣度事件灌進同一 per-client 佇列(上限 1000 按 30 檔自選推的;2026-08-13 上限改 50 後
  滿速緩衝 ≈ 20s 仍夠,不調參),量級重估後再定。
- [ ] **HR-3:hub close() 逾時路徑可致 jsonl 檔內順序倒置**(cancel 後 to_thread
  的 OS thread 照樣寫完,_flush_pending 另起 thread 並寫)。後果有界(重啟後最壞
  補發一則假 open,終態收斂);修法要 thread join 機制,複雜度不成比例,先記著。
- [ ] **HR-5:`_append_jsonl` 吞 OSError 後無對外可見管道**(`dropped_jsonl` 全
  repo 零讀取點,/api/health 刻意極簡)。觀測性議題:候選 = health 加 signal 節
  或 dropped 計數入 /api/stock/signals/today meta。
- [ ] **EC-1:streak 重試迴圈跨午夜後以 D+1 重算繞過 06:00 武裝閘**——風險窗僅
  00:00-06:00 且需 FinMind EOD 遲發 >6h(正常 D 日傍晚已發布),`:1121` 的
  「最新資料日不是昨日」warning 是觀測訊號;擋窗會破壞 R3-BE-3 拍板的跨午夜
  恢復行為。真踩到再修(修法要同時保住兩個語意)。
- [ ] **XR-2 殘餘:adopt_date=False 時家數帶標頭日期(`_trade_date`)與 counts
  資料日錯位**——本輪已修 stale 會亮(`_last_success` 不再刷),日期標示要完全
  誠實需 per-view date(band 用 series 日、counts 用 rows 日),等真的踩到再說。
## 2026-08-07(frontend-stream-p2s /bug 收尾留尾巴)

- [ ] **首掛第一發 refetch 失敗時不排重試(review A-4)**:effect 宣告順序使第一發
  refetch 必早於 ws.onopen,`wsOpenRef` 尚 false → scheduleRetry 第三道檢查早退;
  自癒退到 WS onopen 的 refetch(非死路,延遲從 1s 變 WS 連上時間)。
  候選解 = 第三道檢查放寬成「WS open 或本 session 從未 open 過」。
- [ ] **book 推播與 snapshot 的定序是近似不是嚴格(review A-3)**:pendingBook 蓋回
  假設「推播晚於後端 handle」,誤差窗 = request 單程延遲(localhost 次毫秒)。
  嚴格定序需後端給 book seq(契約改動);鎖板稀疏推播場景若再見一格舊簿,先想起這條。

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
- [ ] **RiverPanel 並排 / 重疊是單選 pill 但無 aria-pressed / radiogroup**(2026-08-21 a11y 批 spec review R13):
  `corr/RiverPanel.tsx:86-100`;換 `ui/RadioPills` 即可(RiverPanel.test 6+ 處以 button 定位要改 radio)。S 級,順手批。
- [ ] **App `<nav role="tablist">` 含非 tab 子節點**(既有;2026-08-21 a11y review A11Y-p2-2):`App.tsx` nav 內同時包
  `VersionDriftBadge` + `IndexBar`,違反 aria-required-children。修法:tablist role 收到只包五顆 tab 的內層 div。S 級。
- [ ] **RadioPills `onInteract` 每次 label 點擊觸發兩次**(2026-08-21 fix 波實測:label activation 轉發 click 到內層 input 再冒泡):
  現僅用於 PriceLadder 重置武裝閒置計時,冪等無害;若之後有人拿它計數,要在 label onClick 過濾 `e.target` 為 input 的那次。
- [ ] **P2:自選列組內排序無鍵盤路徑**(既存):拖拉握把是唯一排序入口(pointer
  only;aria-hidden 化後對 AT 不可見)。管理 Dialog 只有移組/移除,無排序。
  補鍵盤排序入口(如 Dialog 內上移/下移鈕)列排期。
