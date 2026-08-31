## 2026-09-01(pr-review #163/#164/#166/#167 四份收修 留尾)

- [ ] **重播蓋日其實可達:凌晨開機時群益 backlog 尚未換日,重播昨日成交以到達日入 `FillRecord.date`**
  (2026-09-01 01:14 真環境實錄,非本輪回歸 —— L76 出貨起即如此):Tue 01:14 boot,ConnectByID 重播
  週一 09:17/09:25 的 D 事件,`date=20260901`(到達日)→ 前端 `rawFill` 的 `date !== todayYmd` 閘放行,
  **週一的成交三角會畫上週二的分時圖**(時刻用的是原始 09:17);`today_qty` 同族(週一買 1 張被計進
  週二當沖淨額)。pr-167 F-02 複查「重播蓋日不可達(clear 零 prod caller)」漏了這條路(開機重播 store
  是新的,效果相同)。早晨 ~08:10 開機未見此症狀 → 群益 backlog 疑似清晨換日,僅跨午夜到清晨那段開機
  會踩。緩解 = 開盤前照常重啟(user 既有流程);真解 = 重播列的 date 語意重審(候選:D 事件 idx23 回報日
  可信度實證後改用之,或 time 落在「今日尚未到達的時刻」時歸前一交易日)。FillRecord docstring 的
  「目前不可達」措辭要一併改口。
- [ ] **水位多計向(pr-163 F-02,對稱留尾,與上方「倒退保護 60 s 洞」成對)**:涵蓋判定以本機到達序為準,
  成交已入券商快照、推播卻晚於 balance 查詢出手的那筆會被快照計一次、落地又重套一次(複查實測 qty 2→3),
  下一輪鏈 ~2 s 自癒。真堵 = 落地時對帳(該鍵快照張數已等於樂觀張數就不重套;有「同鍵兩筆只入帳一筆」殘餘邊界)。
  user 09-01 拍板先做輕(口徑註解 + 本留尾),與 60 s 洞同批等實錄再拍。
- [ ] **零推播自癒重掛不通知 engine(pr-164 F-02 殘餘)**:`_heal_tick` R2 重掛訂閱不清 `_backfilled`,
  靜默期的分鐘缺口當日補不回(「切主圖順手補」的舊救援已隨 set_main 去重 guard 移出不變式,三處註解
  08-31 同批改口)。**不要照字面修** —— heal 以 60 s 門檻清記帳會把 churn 放大到遠超修前 75 次;
  真解 = heal 發 per-code 事件或節流式 guard,另案。
- [ ] **水位配對 token 化(pr-163 F-09)**:begin_snapshot ↔ set_positions 的 1:1 配對靠 client 三個守門旗標維持,
  balance 段超時 abandon 後遲到列被誤認新輪的縫隙裡,W2 會被 round-1 快照消耗 → 該輪退回修前少計行為(非新洞)。
  真堵 = begin_snapshot 回 token、set_positions 驗 token,消掉 store 一個跨呼叫可變欄位。user 09-01 拍板記留尾。

## 2026-08-31(pr-165-review 留尾)

- [ ] **大盤頁 tf=D 的 `is_partial_last` 要不要吃定稿界**(pr-165-review #5):日曆日判準讓 14:00–24:00 印「最後一根未收盤」
  但 bar 已定稿 —— **非** #165 引入(冷啟動 13:45 後首問同樣誤標),定稿界只讓它變常態。docstring 兩口徑註記已補
  (fix/pr-165-review-followups);要不要讓 D 分支改吃 `DAILY_FINAL_TIME` 是 /mod(`is_partial_last` 同時服務 1/W/M,
  夜盤語意另一回事,期貨側不吃本欄)。
- [ ] **`BarsCache.prune` 的 `_daily_tag`(306-307)與 `_daily_pre_final`(308)清理零測試**(pr-165-review #8,內部複查
  REFUTED 單獨立案但缺口是真的):兩行同構、刪掉全綠、失效 = 純記憶體無界成長。要補就兩段一起 —— 比照
  `today_entry_count()` 開 `*_count()` 觀測點 + prune 測試各一行斷言,併 test-hygiene 批。

## 2026-08-31(fix/futures-daily-cache-night 留尾)

- [ ] **前端期貨日 K 的界仍是午夜 —— 一直掛著的分頁 15:01–24:00 還是用早上快照畫 CDP**(後端定稿界落地後,F5 / 新掛載即正確,
  但 `day-bars-rollover.ts` 的 staleTime 到午夜才過期,掛著不動的 preview 要到 00:01 才重問):候選 = `useFuturesBars` 日 K 的界改
  min(午夜, 15:00 錨定翻頁 + slack)。**只有期貨那支該吃 15:00 界**(market / stock 的日 K 沒有錨定日概念),而政策的單一住處在
  `lib/day-bars-rollover.ts` 三支同源 —— 怎麼開這個分岔是設計題,/mod + grilling 一輪再動。
- [ ] **`DAILY_FINAL_TIME = 14:00` 的前提(TC4 DK 定稿寫入時點)未實測**:交易日 14:00 後首刷 `bars/TXF?tf=D` 實錄一次,末根與
  期交所日盤收盤對照(`.claude/bug/futures-daily-cache-night/verification.md` 判準 5)。若 14:00 仍非定稿 → 界往後調。
- [ ] **`BarsCache` 的 `_daily` / `_daily_tag` / `_daily_pre_final` 三份同鍵平行結構**(two-axis review J3):第三份起收成
  `DailyEntry(bars, tag, pre_final)` 的效益已高於單點改動成本 —— 🔵 refactor 候選,動時連 `daily_*` 五個方法一起收。

## 2026-08-30(fix/futures-daily-bars-rollover 留尾)

- [x] **期貨日 K 後端 daily cache 在 15:01–24:00 這段是早上那份快照**(`copycat/server/bars.py::build_period`,鍵 = `(code|L, date.today())`,
  無 TTL;`prune` 只清別天):前端 15:01 錨定日翻頁到 D+1 後,疊線基準要 D 的完整 bar,但後端整個日曆日都回首抓時的 D 部分 bar
  (夜盤段 / 09:00 首抓時只有夜盤那截),要到午夜前端重抓才拿到完整 D bar —— 08-30 的前端修法刻意把界取在午夜,**夜盤 15:01–24:00
  這段的 CDP / MA 仍是「昨天早上的 D 部分 bar」算的**(推論自 cache 鍵,未實錄夜盤畫面)。候選 = 日 K cache 對「末根 == today」的
  結果用短 TTL(比照 `TODAY_TTL_SECS`)或 13:46 後失效一次;個股日 K 走 `build_daily` 同構(但個股 overlay 走後端 `date < today`,
  盤中不會拿部分 bar 當基準,夜盤也沒有現貨交易 → 個股面無症狀)。
  **→ 08-31 fix/futures-daily-cache-night 出貨**:採「定稿界一次失效」(`DAILY_FINAL_TIME = 14:00`,界前寫入的快照過界作廢一次、
  界後寫入即定稿;否決 30s TTL —— 盤中重抓拿回的仍是部分 bar,純付費不治病)+ refetch 空手墊背舊快照(`daily_stale`,盤後 TC4
  關著不得從「早上快照」惡化成「空白到午夜」);`build_daily` 同結構同病一併在 cache 層治好(個股日 K 夜間 F5 同樣拿早上快照)。
  界值 14:00 的 TC4 前提與前端午夜界的殘餘症狀 → 見 08-31 節。
- [x] **App 級 lazy 測試在剛 `npm ci` 的 worktree 全量必紅 1–2 條、每次不同**(`App.memo.test.tsx` railCtx 換主檔 ×3 / `App.corr-tab.test.tsx`
  零 corr WS ×1 / `App.test.tsx` localStorage 記住 index tab + capital WS 唯一掛載 ×1,皆 ~1.1–1.2 s = `waitFor` 預設 1 s 逾時;08-30 worktree 5/5 全量紅、**stash 掉全部改動仍紅同一條** → 環境不是改動;
  主 tree master 同時段 1/1 全綠)。與 08-28 節 chore/test-hygiene-batch-2 的「L68 App.test waitFor 3000」同族,併那批處理;
  單檔重跑 3/3 綠。判讀規則:worktree 全量紅在 App 級 lazy 測試 → 先單檔重跑 + stash 差分,再懷疑改動。 **→ 08-31 chore/app-tests-async-timeout 出貨**:`App.test.tsx` / `App.memo.test.tsx` / `App.corr-tab.test.tsx` 檔頭 `configure({ asyncUtilTimeout: 3000 })`(= L68),剛 `npm ci` 的 worktree 全量 2896/2896 ×2 首次全綠;判讀規則仍留 ops-discipline。
- [x] ~~**`useMarketBars.ts:69` / `useStockBars.ts:95` 與修前 `useFuturesBars` 逐字同病、未修**~~(pr-151-review F-03 改正:原記的
  overlay 兩支不是同病):`useMarketBars` 日 / 週 / 月 K `staleTime: isMinute ? 0 : Infinity`、queryKey `["market-bars", key, tf]` 無日期;
  `useStockBars` 日 K `staleTime: isDaily ? Infinity : 0`、queryKey `["stock-bars", code, "D"]` 無日期 —— 台股綜合 tab 的日 / 週 / 月 K
  與個股頁日 K 整天掛著跨午夜同樣停在昨天(個股 overlay 走後端 `date < today` 不受影響,症狀只在 K 線本身)。修法沿
  `useFuturesBars.ts::msUntilDayRollover`(界嚴格在 from 之後 + 秒級量化;**不要**改吃 `dataUpdatedAt`,切回路徑會漂)。另開 /bug。
  **→ 08-31 fix/daily-bars-siblings-rollover 出貨**:兩支 `staleTime` / `refetchInterval` 改吃同一把尺;`useMarketBars` 日 K 分支**整段不吃 `active`**
  (tab hidden 保留不 unmount,切回只會排到下一個午夜;與期指 `subscribed: active` 是同一個界、不同閘形狀 —— review P-F2 / P-F3 知情);
  `useStockBars` 沿 `barsPollInterval` 先判(20 s 空態重試優先於日界);兩支同加午夜失敗 60 s 重試(error 只在 HTTP 非 2xx,TC4 斷線是 200 降級
  payload 不進 error)。helper 三顆搬 `lib/day-bars-rollover.ts`(user 拍板)。14 條 hook 測試(15 例;pr-159-review F-03 回校)+ 10 突變體全殺。真環境判準 = 09-01 00:01 Network 一發
  `market/bars/*?tf=D` + `stock/bars/<code>?tf=D`、09:00 後末根是 09-01(artifact `.claude/bug/daily-bars-siblings-rollover/verification.md`)。
  **→ 08-31 /pr-review #159(8 條全 Nice)→ fix/pr-159-review-followups 全收修**:F-01 午夜 200+空 bars 視同失敗 60 s 重試
  (`dayBarsRefetchInterval` 加 `retryEmpty`,market / futures true、stock false —— stock 的空+ok = 真無資料刻意不輪詢,SC-4);
  F-02 政策運算式收 `lib/day-bars-rollover.ts`(公開面只剩兩支政策函式,常數全降私有);F-03~F-08 docs / 測試衛生六條。
  報告入 `docs/superpowers/specs/pr-159-review.md`(+ .audit.md)。
- [ ] **三支日 K 跨日測試鷹架逐字三份**(review S-F5,08-31):`rerenderBurst` / `D_SNAPSHOT` / `D1_SNAPSHOT` / `D1_ISO` / `stubFetchByWallClock` 在
  `useFuturesBars.test.ts` / `useMarketBars.test.ts` / `useStockBars.test.tsx` 同形。可抽 `hooks/__fixtures__/day-rollover.ts`;動到期指那檔出本案範圍,
  併 test-hygiene 批。(08-31 followups 又長一對:market / futures 各一條近逐字的「午夜 200+空 bars」測試 —— 抽 fixture 時一併收。)
- [x] ~~**`useIndexOverlay` / `useStockOverlay` 的跨日靠 queryKey 帶 `isoLocalDate(new Date())`**~~(08-31 user 拍板知情不動、結案;render 時重算,**有**日期鍵、風險較低):
  與 08-30 否決的 H3 同構 —— 只在 re-render 時翻鍵。現況無症狀(個股 / 指數頁每秒有 WS 推播 → 必 re-render),但若哪天這兩頁也加了
  「沒人看就退訂」的閘,跨日會與期貨日 K 同病。記著,不動。

## 2026-08-28(next-time 100 條 triage 拍板 —— 新開案;決定表 `docs/superpowers/specs/2026-08-28-next-time-triage.md`)

- [x] ~~**`/mod` 可觀測性小批**:L3 日曆誤標 WARNING / L262 期貨 1K 落後 WARNING / L106 重掛 snapshot 時距 DEBUG /
  損益列 avg·cost·kind INFO / L171 冷門檔退避 60→300 s / VX 加 `sparse` 旗標。零行為改動(退避與 sparse 除外,皆只影響 log 節奏)。~~
  → 08-28 mod/observability-batch-0828 出貨:L106 + L171 同根因(重掛後 SUBQUOTE snapshot 被 `_note_push` 清 attempts)→ 指紋規則一條收兩條;
  退避上限 300 s 早就存在,不必改常數。**真環境待 prod 重啟後看**:次一交易日 `grep 零推播自癒 | grep 6949` 應由 92 發降到 ≤ 10 發且 attempt 遞增;
  `grep 損益列回填` 每檔首輪一行;`grep "期貨 1K"` 只在真落後 / 缺格時出現;VX `grep 零推播自癒 | grep VX` 應 0 發。
  **08-30 /pr-review #145 收修(fix/pr-145-review-followups)**:F-01 週末 / 連假空窗不再算「中段缺格」(冷 memo 30 日窗曾每次重啟固定
  噴「最大 2879 分」;修前 08-31 grep 要先扣掉那批,修後 `grep "期貨 1K"` 判準才成立)、F-08 落後量對齊前端終點標記(非整秒 +1,後端不再少 1)、
  F-13 去重帳按 session 分開、F-09 健康檢查加圍籬、F-03 `_note_push` 裸索引競態;測試層 F-02 / F-04 / F-05 / F-06 / F-07 / F-14 / F-15 釘齊
  (報告 `docs/superpowers/specs/pr-145-review.md`)。
- [ ] **VX `sparse` 全日旗標的取捨**(pr-145 F-18,知情用):sparse 整場豁免 R2、CFE 段 `segment_leg_gate` 恆 True → VX 任何時段只剩 R1,
  但證據只有台北 08:47–09:55 那 68 分鐘;`corr_config.py` 既有註解記「01:02 實測 VX 45 s 推 19 則」(美盤盤中活躍)。若在意美盤時段
  單腿死無人救,候選 = sparse 時段化(比照 `heal_symbol_active`);不在意就維持。
- [x] **`/bug` 無券空單校準**(L151 / L394 併):`_FILL_KIND` 補「無券」、負現股列平倉解鎖、損益列蒐證;倉位線語意等下一筆實錄。
  **→ 08-30 出貨 fix/borrowless-short-calibration**:負現股列歸 `daytrade_sell`(user 拍板)+ 兩條連帶(現股買先沖空單 / 損益列「現股」配
  daytrade_sell 負列)。**prod 重啟後下一筆無券當沖的判準**:log `庫存段 <股號> 現股負股數 … → 無券空單(daytrade_sell)`(INFO,每股號每日一次;parser 那行是 DEBUG 看不到;不得再出現「平倉暫鎖」WARNING)、
  `curl /api/capital/positions` 該列 `kind:"daytrade_sell"` / `today_qty:1` / `avg_source:"broker"`、閃電梯部位標籤「無券」、平倉鈕可按(送現股買)、
  買回後 positions 立即歸零(不出現 cash +1 幽靈列)。倉位線語意仍留尾(下條)。
  **→ 08-31 /pr-review #152 十四條收修(fix/pr-152-review-followups)**:對稱沖銷補齊(無券賣先沖現股多單)、B08 不進 daytrade_sell 淨額、
  庫存段負 T 列每股號每日一次 INFO、確認窗反向單「買回 n 張(現股)」、兩支跨語言 parity 測試;留尾:殘量開列取整批 `fill_avg`
  (含已被沖銷那幾張的價金,多價位分批成交時殘餘列均價偏移;買向 block 同形、快照落地即蓋,參考用)。
  review 收修:parser 那行降 DEBUG(每輪洗版)→ 判準改看 `成交樂觀套用部位 … stock=<股號>`(修前是「不在樂觀套用表」)與
  `損益列回填 <股號> kind=cash 部位=daytrade_sell`;`grep "balance line 負股數"` 對現股列自此 0 筆(融資列仍會印)。
- [x] ~~**`daytrade_sell` 語意散在六處(review 2026-08-30 F-09,Shotgun Surgery)**~~ → 08-31
  refactor/daytrade-sell-kind-table 出貨:前端散點比較收斂 `lib/trade-kinds.ts::KIND_TRAITS`
  (buyLocked / halfTaxToday / borrowFee / order)+ `kindTraits()` 未知字串政策;types.ts trade_kind
  內嵌 union → PositionKind、capital_api 重複 Literal → TradeKind。後端 balance/client/store/close
  四個決策點**刻意不收**(各有方向性邏輯 + 實錄註解,收表變淺)。原文:balance.py / client.py / store.py / close.py
  `_CLOSE_MAP` / `ladder-position.ts`,前端另有 PriceLadder / close-order / flash-send / trade-kinds 各自 `=== "daytrade_sell"`
  字串比較,`positionEcon(kind: string)` 收裸 string。候選 = 前端把 kind 收成單一型別 + 一張「稅 / 費 / 方向」表;等下一次再加種類時併做。
- [x] ~~**`/bug` 部位快照不得倒退**(L227 / L498 併;user 08-28:「樂觀更新不該被資料拿到後改動,下單風險太大」)。~~
  → 08-31 fix/position-snapshot-no-regress 出貨(水位修法,user 拍板只做水位):`store.begin_snapshot()` 記 balance 查詢
  出手時刻每張單累計成交量,`set_positions` 落地只把水位前標「已套用」、水位後增量經 `_apply_fill_locked` 重套於快照之上;
  重播/開機(未 seeded)一律不記水位(`begin_snapshot` 記 None = 快照即真相;pr-163 F-01 收修 ——
  修前只有零 prod caller 的 `clear()` 受保護,每次開機都走的 ConnectByID backlog 路徑會被空水位 `{}` 重套)。
  紅測試 = test_fill_latency `test_chain_landing_does_not_regress_fill_arrived_in_flight` + test_store
  `test_boot_watermark_before_backlog_does_not_reapply_replayed_fills`。
- [ ] **倒退保護(R1 留尾,待實錄再拍)**:成交發生在 balance 查詢出手**前**、但群益報表自身落後(> 0.5 s debounce)
  → 快照仍舊、水位判不出 → 倒退最長 60 s(L642「少一檔 / 多一檔 60s」樣態)。修法候選 =「近 N 秒內有樂觀成交的鍵」
  落地若倒退則保留樂觀值 + 立即重查;TTL 要拍板(user 08-31:「這個問題先緩緩」)。下次盤中遇到部位消失 >5 s 時抓
  `grep "balance 鏈" + 成交樂觀套用` 時序當實錄。
- [x] ~~**`/bug` 期貨日 K `staleTime: Infinity` 跨日不重抓**(L332)。~~ → 08-30 fix/futures-daily-bars-rollover 出貨(見 08-30 節)。
- [x] **`/perf` 開盤回補並行**:user 目標 = **09:00 一開盤自選全部同時開始收,不是一檔一檔排隊**。今日實測:首筆回補 09:02:09 才開始
  (兩分鐘空檔原因未明),之後單工 worker 一秒一檔(09:02 38 檔 / 09:03 16 檔 … 到 09:13)。步驟:① 盤後實驗達錢並行 SubHistory
  4–8 檔會不會壞(不碰 prod)② 能就把單工 worker 改有上限並行、正在看的群組優先 ③ 另診斷 09:00→09:02 空檔。L405 圖牆 DOM 一併量。
  **① 08-28 16:xx 已量(`spikes/stock_backfill_parallel_probe.py`,20 檔,盤後、只 history 不 SUBQUOTE)**:serial 23.3 s(1.16 s/檔)/
  先全部 SubHistory 再收割 **3.3 s** / ThreadPool(4) 並行 backfill **3.4 s**,三法 tick 數逐檔相等、零逾時。根因不是 TC4 慢:`StockQuoteSource.backfill`
  首頁沒備妥就 `sleep(poll_wait=1.0)`(沒有 `_collect_history` 的 0.15 s 退避),單工排隊 = 每檔白等 1 秒;真正的資料成本只有最忙那檔
  (3481 44k ticks 0.98 s)。修法候選(② 的具體版):(a) worker 出隊前先對整批 `_sub_history`(TXO `fetch_backfill` 樣板)+ backfill 首頁 poll 改退避;
  (b) 或 worker 改 N=4 有上限並行。(a) 改動最小、零新執行緒。③ 09:02 才起跑仍未診斷(server 08:14 起、無 rollover;疑 `_backfilled` /
  60 s 輪詢入列時序)。
  **→ 08-30 已出貨(perf/opening-backfill-parallel)**:S1-a backfill 首頁 poll 改基底 `_collect_history` 退避;S1-b worker 出隊時整批 `prepare_backfill`(先全訂再收割);S2 🔴 自選成員**首筆當日成交 tick** 即入列(不做「訂閱當下入列」:08-28 主圖 6207 08:15 入列 → 30 s 逾時 ×2 → 「放棄」,40 檔 = 20 分鐘必敗 REQ)。harness 40 檔 40.72 s → 18.9 s → **0.87 s**。③ 真因 = 入列點全是需求驅動,09:02:08 user 打開群組檢視才有第一筆 `group-state`。**08-31 判準**:`grep "stock backfill" logs/server-20260831-*.log | awk '$2>="09:00:00" && $2<="09:01:00"'` 首筆 ≤ 09:00:05、自選全部完成 ≤ 09:00:30;09 點整點總筆數對照 08-28 的 313。L405 圖牆 DOM **未量**(user 不覺得卡,留著)。
- [x] ~~**set_main 無條件重排回補去重**(08-30 /perf 旁支,user 拍板 next-time):~~ → 08-31 fix/backfill-enqueue-trio 出貨:set_main 只擋 `_backfilled` / 在途兩道(no_data / 冷卻刻意不下沉);斷線缺口保險由 reconnect 清 `_backfilled` 承接。08-31 實測 2455 一天 75 次重複回補是證據。原文:`GET /api/stock/state/{code}` → `set_main` → `_enqueue_backfill` 不看 `_backfilled` / 在途 —— 08-28 8358 一天 44 次、6213 41 次(612 次 state 請求),每次 = SubHistory + 全量收割數千 tick + `apply_backfill`。去重會失去「切主圖時順便修補 live 缺口」的保險(reconnect 已清 `_backfilled`,斷線缺口仍會補)。S1 之後每次重複只花 ~0.3 s,痛感大減,先觀察。
- [x] ~~**開盤瞬間每檔回補兩次**(08-30 觀察):~~ → 08-31 log 核過**結案**:S2 後開盤窗(09:00–09:05)零 sub-second 雙發(08-28 的 1 秒 pattern 消失)。盤中 Δ0s 雙發(09:35 等)= 主圖 fresh subscribe 的「set_main 先入列、首則 REALTIME meta None→值再補一次」刻意設計(鎖停補判需要,stock_engine 註解記載),不改。原文:08-28 09:02–09:03 有 20 檔跑兩次(3042 09:02:20.944 / 09:02:21.976),第二次來自「漲跌停值變」入列點(首則帶 UpperLimitPrice 的 REALTIME 在回補完成後才到 → `prev_limits != meta`)。設計上刻意(補鎖停判定);S2 之後首筆 tick 與meta 同一則到 → 應只剩一次,08-31 log 核。
- [x] ~~**前端 `useGroupSnapshots` 的 `refetchInterval` 回 false 時 TQ 不排 timer**(08-30 觀察):~~ → 08-31 fix/backfill-enqueue-trio 出貨:groupPollInterval 盤外改回 `msUntilTradingOpen`(新純函式),窗開瞬間醒來。原文:08:59 就開著的群組檢視要等 query 被別的事件重估才會在 09:01 後開始輪詢;S2 之後回補不再依賴這條輪詢,影響只剩卡片 60 s 刷新的起點。
- [ ] **同病:`refetchInterval` 回 false 的其他 hook**(08-31 L71 掃出):`useBreadthRows` L46(`active && inTradingHours() ? POLL_MS : false`,靠 tab 切換 re-render 半自癒)與 useMarketBars / useStockBars / useFuturesBars / useIndexOverlay 的 `(q) =>` 形各自的盤外 false 分支 —— 開著不動跨越開盤點的都有同一個洞。candidates = 各自換 `msUntilTradingOpen`(已在 lib/trading-hours);逐支確認盤外語意再動,不在 L71 一次掃。要驗再開。

- [ ] **`/mod` 群組圖牆逐筆**(C9;08-31 C 類四輪**排除**,要先 grilling「資料逐筆不丟」前置再另開案):user 拍板每檔逐筆(現況 60 s 輪詢 group-state + 每秒 watchlist_quote 拉尾);實作條件 = 資料逐筆不丟、
  畫面每畫格合批重繪(50 張卡 memo 教訓)。排在 `/perf` 之後。
- [x] ~~**`/mod` 緩撮第二段**(L478)。~~ → 08-31 mod/chart-ux-batch-0831 出貨(見下方詳細條)。
- [x] ~~**`/mod` 成交點精確版**(L439 / L444 / L435)。~~ → 08-31 mod/chart-ux-batch-0831 出貨。
- [x] ~~**`/mod` 盤前前一交易日 + TXO 自動日期**(L461 / L457)。~~ → 08-31 mod/chart-ux-batch-0831 出貨。
- [x] ~~**`/mod` 斷線徽章分態**(L296)。~~ → 08-31 mod/chart-ux-batch-0831 出貨(status 加 engine 欄,兩句分態)。
- [x] ~~**B2 調研(background research)**:達錢商品資訊欄位還能拿到什麼 —— 暫停交易旗標?當日當沖資格?(L171 / L272);
  證交所當日可當沖名單 API;FinMind 當日更新時刻。~~
  → 08-28 `docs/research/2026-08-28-instrument-flags-survey.md`:達錢**不可**;證交所 `TWTB4U`(含 `Suspension`)/ 櫃買 `tpex_securities` 免 token JSON **可**(盤前公布時刻未證,08:30 打一次);
  FinMind DayTrading 盤前可取、資券 21:00。C1 當沖資格標示 → 資料源定為交易所 OpenAPI 當日名單,等 user 排 `/feat`。
- [x] **D `chore/test-hygiene-batch-2`**:L29 / ~~L68~~(08-31 已出貨 chore/app-tests-async-timeout)/ L231 / L268 / L429 / L368 / L201 / L292 / L6 + 三條零風險 🔵(L111 改名 / L129 HealPolicy / L194 註解)。 **→ 08-31 chore/test-hygiene-batch-2 出貨:L29(rollover 結果面)早在 08-28 0619cc18 已補、L292(futures_engine 錯句)早在 08-26 b0df23b7 已改,兩條只回填;其餘 11 條本批做完(逐條見各自留尾處)。**
  - [x] `tests/server/test_stock_engine.py` 3800+ 行,回補主題散在 6 個 class(約 L210 `TestBackfillGuard` / L911 `TestBackfillTimeoutRetry` /
    L1688 `TestFirstTickEnqueuesBackfill` / L1844 `TestBackfillBatchPrepare` / L1933 `TestBackfillFailureIsolation` / L2614
    `TestWatchlistRemovalBookkeeping`;`/pr-review 153` chunk B 觀察,行號為 08-31 master 6c082132 的值)。#154 已把 `_tick_armed` 兩條
    鏡射測試補進既有 `TestWatchlistRemovalBookkeeping`(抑制碎裂的方向);批次整併時以「同一個記帳集合的邊界測試放同一 class」為原則,不動斷言。 **→ 08-31 chore/test-hygiene-batch-2 出貨:TestBackfillTimeoutRetry 搬到 TestFirstTickEnqueuesBackfill 前 + 主題索引節標(AST 全等腳本斷言);Guard 與 RemovalBookkeeping 留原位。**
- [x] **08-31 盤中對帳清單**(agent 做):L101 / L115 / L125 加權 13:25 後;L96 SXF 最長靜默;L513 group-state 分鐘完整性;
  L467 / L471 heal 階梯(壞日子才有);6949 發數(≤ 40);海外腿休市段亂救;13:50 NK225M probe(L430);L84 SC-13 (b)–(e)。
  **→ 09-01 00:3x 以 08-31 log 對帳(server 只跑 08:10–11:59、build a58e7ac2 含 #145–#157)**:
  **PASS** = 開盤回補並行(首筆 09:00:03、自選全完成 09:00:22,門檻 09:00:05 / 09:00:30;09 時窗 269 筆 vs 08-28 313)/
  損益列回填每檔首輪一行(9 筆 5 檔)/ `期貨 1K` **0 筆**(2879 假警報歸零)/ VX 自癒 0 發 / 海外腿休市段無亂救(SGX TWN 開盤前 3 發同 08-28 型)。
  **FAIL(定性後 = 門檻不切實際,非迴歸,待拍板)** = 6949 自癒 51 發(半天)超 ≤10 / ≤40 兩道門檻:指紋階梯**有效**
  (attempt a1→a30 無逐發重置),51 發 = **階梯封頂 300 s 的常態節奏**(36/50 間隔 = 300–301 s)+ 盤前試撮 8 發(08:30–08:45)+
  三次不明重置(10:48 / 11:41 / 11:45 各回 a1;無 backfill 入列、無成交跡象 —— INFO 看不出是 >10 s 遲到 snapshot 清帳還是 book 更新,
  觀測缺口)。要降到 ≤10/日只能動產品面:冷門檔封頂拉長 / 整輪零推播降頻 / 盤前試撮不救 / 剔出 watchlist。
  **→ 09-01 user 拍板 (e) 接受現狀、本條結案**:51 發是 log 噪音、自癒機制本身未壞;≤10 / ≤40 兩道門檻作廢,
  後續對帳不再對 6949 發數設限(只看 attempt 有沒有在爬 —— 逐發重置回 1 的舊病回來才算迴歸)。
  **UNTESTABLE、順延下一個全天交易日** = 加權 13:25 閘三問(L101/L115/L125)、13:50 NK225M probe(L430)、SC-13 (b)–(e)(L84)
  (server 11:59 已關);heal 階梯(L467/L471,08-31 全日零斷線零 index 自癒 = 不是壞日子);
  L96 SXF 最長靜默(sparse 腿不進 R2 grep,INFO 粒度**永久量不到**,要另加逐筆推播時戳才行 —— 降級為「要量再開觀測」);
  L513 group-state 分鐘完整性(要**盤中即時**連續 curl,事後 log 補不回 —— 下次盤中做)。
- [ ] **08-28 盤後**:L240 run.ps1 第二次 Ctrl+C `--verify` 驗;達錢並行回補實驗(`/perf` 步驟 ①)。

## 2026-08-28(A7 / N037 WS 韌性真環境驗 —— PASS,留尾)

真環境:prod 8721 = `c451e403`(15:09 起,含 #142),preview 4173 分頁開在期貨 tab(微台);user 15:11:42 左右關閉達錢 4,
15:23 重開;斷線 ≈ 11.5 分鐘(夜盤已開)。證據 `logs/server-20260828-1509.log`。

- **PASS 前端 WS**:分頁 6 條 WS(txo-pnl / stock / index / futures / breadth / capital;corr / river 兩條只在相關係數 tab 才開,
  「8 條」是全站上限不是每頁)全程一條都沒斷 —— uvicorn `[accepted]` 從頭到尾 6 條、console 零「s 無訊息,重連」。
  browser↔uvicorn 的 WS 靠 server 10 s ping 活著,與 TC4 斷線正交;「斷 TC4 看 8 條 WS 全回來」這個判準其實測不到 WS 重連,
  真正的 WS 斷線刺激是 **server 重啟**(15:08 優雅停 → 15:09 起,當時無分頁連著,沒量到)。
  **16:38 補驗 PASS**:preview 4173 分頁開著(run.ps1 的 vite dev 5173 不能當觀測端,HMR 會整頁重載)→ user Ctrl+C 重跑 run.ps1
  (`2fb25e3c`,關機收尾 0.16 s)→ 新 log 14 秒內 accepted = 2 分頁 × 6 條 = 12,+60 s 仍 12、closed 0;分頁不重整、期貨 tab
  16:41「即時連線中」資料自流。console 零訊息是設計:server 優雅關機走 onclose 路徑靜默重連,只有靜默 watchdog 那條才印「無訊息,重連」。
- **PASS 後端 TC4 重連**:5 條 quote source 首次 stale 15:12:12(關閉後 30 s),reconnect 退避 8 → 16 → 60 s(封頂);TC4 重開後
  15:23:24–15:23:52 五條全 `TC4 reconnected`、訂閱重掛 0 失敗、0 ERROR;TXO handover 回補 3493 ticks / 290 symbols;index
  「重連重掛 + 重抓」;corr river 回補 TWN / YM / ES / NQ 11 分鐘、SXF 13 分鐘(= 斷線長度);TMF 1K 尾根 15:24,期貨 tab
  15:25 46430「即時連線中」。
- [x] **TC4 斷線期間 log 洪水**(已出貨 PR #146,2026-08-28;判準見 `.claude/mod/tc4-disconnected-log-flood/verification.md` §5):11.5 分鐘長出 6764 行 / 585 KB —— `零推播自癒 … → 重掛` + `自癒重掛失敗 …: TC4 quote not connected`
  每 symbol 每輪各一行(1206 條),reconnect 失敗每次印 4 行 traceback(210 個 `Traceback`)。TC4 整天沒開會長到 ~30 MB,
  且把真訊號淹掉。候選:quote 未連線時零推播自癒整批只印一行(「N 腿等連線」)、reconnect 失敗 traceback 只在第一次與換退避檔時印。
- [ ] **#142 `bars: 慢請求` 第一筆真事件**:15:13:06 console `bars: 慢請求 /api/market/bars/TMF?tf=D 24.9 s 才回(status 200)`
  —— TC4 斷線中的日 K 請求要等 24.9 s 才回(200,後端 cache / 降級路徑),離 30 s timeout 只差 5 s。題 4「一趟永不回」的候選
  在 TC4 半死時是可觸及的;要看盤中有沒有同款(TC4 沒斷卻 > 15 s)。後端 `build_minute` 慢請求 WARNING 留尾(handoff §4)仍未做。

## 2026-08-28(mod/index-heal-holiday-gate 加權自癒休市日補窗內閘 留尾)

- [x] ~~**日曆誤標交易日為休市的可觀測性只靠畫面**:補窗內閘後,`configs/trading_holidays.json` 若把真交易日標成休市,那天 IX0001 分時自癒
  整天不跑(盤外段本來就不跑)—— 症狀 = 全站休市膠囊 + 圖是前一日的,錯得看得見,但 log 零訊號。候選:server 起動時若
  `is_trading_day(today)` 為 False 而 TC4 09:00 後仍有 IX0001 推播 → 印一行 WARNING「日曆說休市但有推播」。 **→ 08-28 拍板做:併 `/mod` 可觀測性小批。**~~
  → 08-28 mod/observability-batch-0828:`index_engine._note_holiday_push`,同日曆日 ≥ 5 個相異現價 WARNING 一次(啟動 snapshot 單價不算)。
- [x] **rollover 設 pending 的 cancel 只擋 `_retry_task` 一支**:heal 與連線 retry 同走 `_schedule_retry` single-flight,現況只有一支;
  日後若分家(各自 task)要一起 cancel。測試 `test_rollover_pending_cancels_the_inflight_retry` 用 dummy task 釘機制,沒釘「舊日分鐘沒疊進新日」
  的結果面(需要可控的慢 fetch hook,`FakeIndexSource` 尚無)。 **→ 08-28:併 D chore/test-hygiene-batch-2(慢 fetch hook 已有 `FakeIndexSource.fetch_gate`,PR #139)。** **→ 08-31 chore/test-hygiene-batch-2 出貨:結果面測試 `test_rollover_keeps_old_day_backfill_out_of_pending` 已於 08-28 0619cc18(PR #139 round-1 收修)補上,本批只回填勾銷;「分家要一起 cancel」那句仍是提醒,不是待辦。**

## 2026-08-28(mod/n075-price-type-label-window N075 標籤文件改口 留尾)

- [ ] **N075 夜盤遠價市價單實驗(user 親做)**:某個夜盤用 copycat 送一張離現價很遠的市價單(不成交),看回報 `date`
  (idx23)是本機日曆日還是所屬交易日,然後刪單;同一筆回報順帶核群益 seq 是日曆日重置還是交易日重置(隔天日盤第一張單的
  seq 有沒有從頭編)。兩者**同口徑** → `store.note_price_type` 改成只記單一候選日即關掉「同檔同方向撞同 seq」的誤標窗;
  **不同口徑**(日界走交易日、seq 走日曆日)→ 日期分不出,才需要送單時刻 ± 窗那類補丁(08-28 拍板程式先不封洞)。
  期貨路徑只綁方向、窗更寬,同一實驗一起看。窗的現況釘在 `tests/capital/test_store.py::
  test_price_type_binding_rejects_same_seq_different_order` s3 案 docstring(與「另一張」輸入逐字相同,不另加案)。
  **08-28 01:xx prod 觀察(1ce0c500,`/api/capital/orders` 08-27 17 筆現股)**:群益 seq 是 13 位(例 `2313211157766`),
  同日前 6 位 `231321` 全同、後段不隨時間單調(09:41:32 …522034 → 09:41:34 …387140),像多條計數器 / 池;「seq 每天從頭重用」
  是 docstring 的**未實證前提**。**pr-134 review F-07 補第一手**:06-10 真樣本(`tests/capital/test_reply.py`)seq `2313091595225` / `2313092627047`、
  audit 08-26 `2313209526540` / `2313209679448`、08-27 `2313211157766` → 前 7 位 `2313091`–`2313092` < `2313209` < `2313211` 逐日遞增,
  seq 看來是**全域遞增計數不重編**(三日樣本外推),撞同 seq 機率趨近零 —— 實驗的意義只剩日界定案。另一個現成線索:06-10 14:59:48 掛給 06-11 的
  預約單 idx23=`20260610`(進單日)、**idx29**=`20260611`(疑似所屬交易日欄;idx28 恆 `PI`,pr-134 報告 F-07 寫 idx28 為誤,逐欄重數為 idx29),`reply.py` 未解析 idx29;夜盤實驗那筆回報順便看 idx29
  是不是交易日 —— 若是,「記兩個候選日」整套可退成讀該欄。同一筆也順便定 **idx23 跨日事件是否變值**(pr-134 F-01:`reply.py` 同日
  C / D 實測不變 vs tc4-market-facts「最新事件日」機制推論,repo 內零跨日樣本)。 **→ user 08-28:後續再測,不排期;等夜盤實驗才動。**

## 2026-08-28(chore/test-hygiene-batch 測試衛生三條 留尾)

- [x] **`test_balance.py` 六處 `RAW_*.replace(",1000,0,,", …)` 字串猜欄位變異**(:105 / :117 / :128 / :140 / :155 / :161):
  `profit_rows.py` 已立「變異一律走 `pnl_variant`(按欄索引),不 `.replace` 猜字串」,庫存列 `balance_rows.py` 沒有對應的
  `balance_variant`;`.replace` 靠子字串唯一性,欄形一改就靜默改錯欄。本輪純搬移不動斷言(scope),候選 = 加 `balance_variant(row, {idx: v})`
  六處改按欄索引。 **→ 08-28:併 D chore/test-hygiene-batch-2。** **→ 08-31 chore/test-hygiene-batch-2 出貨:`balance_rows.balance_variant(row, {idx: v})` 六處改按欄索引,PNL 五處改既有 `pnl_variant`;十一處新舊字串腳本 assert 全等。**
- [x] ~~**`/ws/index` 首則可能是 ping 或任一 dirty 拍,前端 `useIndexStream` 是否假設首則含完整 payload**(本輪 B 校正前提時順帶看到,未查):
  relay docstring 寫「無 seed 的路(index/capital/futures)首則可能是 ping」;前端 helper 已濾 ping,但首則 `twse.p` None 的 payload
  會不會讓現價欄閃一下 `—`,要看 `index-accum` 的合併語意。待查,不是本輪 finding。~~
  → 08-28 查過:`useIndexStream.toSeries` scalar 覆蓋,`p` None 只在 server 剛起、引擎真無價時出現,那時印「—」正確;盤中每則都帶引擎現價,不會閃。

## 2026-08-28(/pr-review #131 回溯 review 留尾)

- [x] ~~**`tests/server/test_bars.py` 5 條在台北 00:00–00:10 會紅**(pr-131 review 順帶發現;reviewer 00:04 實跑 `5 failed`,
  `bars._now_time` 固定 09:00 重跑 51 passed):`copycat/server/bars.py:510` `hold = hi == yesterday and _now_time() < MIDNIGHT_BUFFER_END`
  午夜緩衝窗吃真牆鐘;該檔部分測試已 `monkeypatch.setattr(bars_mod, "_now_time", …)`(:594),這 5 條沒凍結。處置 = 5 條補同一把
  monkeypatch(或 autouse fixture 凍到 09:00,要驗緩衝窗的測試自己覆寫)。與任何 PR 無關,純測試牆鐘相依。~~
  → 08-28 chore/test-hygiene-batch:模組級 autouse `_daytime_clock` 凍 09:00 + `TestModuleClock` 兩條哨兵(fixture 缺席恆紅 / `build_minute` 真路徑永久化 yesterday);00:05 plugin 重跑 53 passed。
- [x] ~~**pr-131 F-04 commit 慣例**(no-op,已 merge 不重寫):純註解 / JSDoc 位移一律 `chore(<scope>)` 不用無 scope 的 `refactor:`;
  測試重組內含新增斷言時另拆 `test` commit。~~
  → 08-28 triage:no-op,慣例已行。

## 2026-08-27(chore/pr-review-128-130-followups 三份 review 22 條收修 留尾)

- [ ] **artifact 引 rebase 前 SHA 在 #129 重演 —— user 2026-08-28 拍板 (b)**(pr-129 F-07;`docs/superpowers/specs/2026-08-25-do-batch-review.md`
  §4.1「47/56 dangling」流程 finding 的續集):rebase merge 必改寫 SHA,artifact(verification / review JSON)寫的分支 SHA 在乾淨 clone 上
  `git show` unknown revision。**拍板 = (b) artifact 不引 SHA,改引「第 n 筆 + commit subject」**(rebase 後順序與標題不變);(a) merge 後補寫
  最終 SHA 不採。待做 = harness 改動(`branch-lifecycle` 收尾節 + `harness/refs/closeout.md` artifact 格式一行),依鐵則 B **攢批**、
  不單獨開;在那之前新分支的 verification 直接照 (b) 寫(`chore/test-hygiene-batch` 當首例)。
- [x] ~~**`tests/server/test_index_routes.py::TestIndexState::test_ws_streams_index_payload` 順序型 flake**(非本輪 finding,如實揭露;08-27 深夜全量 pytest
  1/3135 紅、單跑 1 紅 5 綠、整檔綠):測試 `websocket_connect` 後立刻 `fake.on_message(quote)` 再 `receive_json()` 斷
  `twse.p == 42_039_920`,但 `/ws/index` 連上時先送**初始快照**(`twse.p` None),quote 廣播若排在快照之後,首則就是快照
  → `assert None == 42039920`。與本輪 diff 無關(index routes / ws / engine 未動)。處置 = 測試改「收到含 p 的那則為止」
  (`receive_json` 迴圈 ≤ 2 則),或先 `receive_json()` 吃掉初始快照再送 quote。~~
  → 08-28 chore/test-hygiene-batch:改「收到含 `p` 的那則為止」(ping 不計、上限 5 只防無界等待)。**前提校正**:`/ws/index` 沒有 seed 快照(`index.stream()` 無 seed),搶在 quote 前的是回補完成 / MIS poll 撥 dirty 的 `_broadcast_loop` 拍;「先吃一則快照」那個修法在常態(零前置訊息)會把 quote 誤當快照吃掉,不採。plugin 固定 race 3/3 紅 → 修後 3/3 綠、裸跑 20/20 綠。
- [x] ~~**`tests/capital/test_client.py::_BAL_3357` 12 處內嵌 = `test_balance.RAW_C_MARGIN` 同型重複**(pr-129 F-02 附帶):
  庫存報告列(19 欄)在 test_client 內嵌 12 次、與 test_balance 那份逐字相同;群益改欄形只改到一份、另一份靜默留舊欄形
  —— 與 pr-119 F-05 / pr-129 F-02 同坑。處置 = 比照 `profit_rows.py` 開 `balance_rows.py`(或併同一模組)收成單一定義處。~~
  → 08-28 chore/test-hygiene-batch:`tests/capital/balance_rows.py` 六常數單一定義處(review 另抓到 `test_fill_latency._BAL_ROW` 第三份 → `RAW_T_HELD`),test_client 內嵌 12 處 + `_BAL_*` 11 引用全換,逐 byte 相同。

## 2026-08-27(feat/txf-intraday-overlay 個股分時圖疊台指期 留尾)


- [x] **`src/App.test.tsx`「capital WS 唯一掛載」負載型 flake**(08-27 晚 fix/breakeven-review-followups 三次全量 vitest 與
  全量 pytest **並跑**時 3/3 紅、單獨跑 3/3 綠 2848 passed):該測試 `waitFor` 預設 1 s 等兩個 lazy 頁面掛載,並行負載下 1.8 s。
  不是本輪 diff(純函式)造成。候選 = 該測試 `waitFor(..., { timeout: 3000 })`,或 ops 紀律「全量 vitest 不與全量 pytest 同時跑」。 **→ 08-28:併 D chore/test-hygiene-batch-2。** **→ 08-31 chore/test-hygiene-batch-2 出貨:08-31 已隨 chore/app-tests-async-timeout(e182cc7b)把 App 級測試 asyncUtilTimeout 拉到 3 s,本批回填勾銷。**
- [x] **期貨 tab 改「15:00 夜盤起算」的一天定義(user 08-27 拍板另開 /mod)** —— 08-28 mod/futures-day-1500 出貨(issue #132 / PR #133);留尾見下條:現況前後端都把期指一天排成
  08:45 日盤 → 13:45 → 15:00 夜盤 → 05:00(x 軸左起 08:45;凌晨 ≤05:00 算前一日)。user 要的畫面 = 近全圖左起
  15:00 夜盤、右至隔天 13:45 日盤收,「今天」= 昨 15:00 起算(交易所交易日口徑)。牽動:`frontend/src/lib/allday.ts`
  (段順序 / `anchorDateOf` / `sliceCurrentAllday` / 刻度表)、`copycat/live/futures_source.py::FUTURES_ALLDAY_DOMAIN`
  與回補日窗、`useFuturesBars` 輪詢窗 `inFuturesAllDayHours`、相關係數腿的台期交自癒閘、FuturesChart live 點四道 gate。
  結算價基準不變(15:00→13:45 同一個 ref)。
- [ ] **假日集合「兩個來源」的 Data Clump(mod/futures-day-1500 review round 1 S7)**:`holidays?: ReadonlySet<string>` 從
  `FuturesChart` 經 `sliceCurrentAllday` / `anchorDateOf` / `alldayFillPoints` / `nextTradingDayIso` 四層可選穿透,缺省讀
  `trading-calendar.ts` 模組集合 —— 同一份資料兩個來源(query data vs 模組級)。現在只有 FuturesChart 一個消費者,
  再多一個(例如群組圖牆的期指卡)就該收成一個 `TradingCalendar` 型別或 context,不再各自 `new Set(holidays)`。
- [ ] **期指「每個交易日都有夜盤」假設沒有事實鎖**(mod/futures-day-1500 §6):春節前最後交易日期交所不開夜盤,
  那天的圖左半會空白(錨定日 = 假日後首交易日,夜盤側零 bar → 不補橋,只畫日盤);`inFuturesAllDayHours` 同一假設。
  候選 = 交易日曆 JSON 加「無夜盤日」欄,兩處同吃。要先查期交所公告落成事實(tc4-market-facts)。 **→ 08-28:不急,2027-01 前做(先查期交所公告)。**
- [ ] **SC-13 (b)–(e) 真環境窗口**(mod/futures-day-1500):15:01 翻頁那一刻(左緣換成今 15:00)、次一交易日 08:46 的
  05:00→08:45 水平橋 + 跳價、CDP 五線在 15:00 換組後 user 對 APP、個股頁「台指期」線夜盤時段仍在(解耦後應與改前相同)。 **→ 08-28:08-31 驗,user 看畫面、agent 抓 `/api/market/bars` 對照。**
- [ ] **加一條指數疊線要改 11 處(review round 1 S4 Shotgun Surgery)**:`ChartToggles` 鍵 + `DEFAULTS` + `IndexOverlayKey`
  + `INDEX_OVERLAY_LABEL` + `OVERLAY_KEYS` + `IDX_LINE_CLASS`/`IDX_TEXT_CLASS` + `toggleDefs` 字面 union + `GRID_TOGGLES` union
  + `index.css` token + `GroupGridView` 的 `||` 串;12 個測試檔只為補 `idxTxf: false`。候選 = 收成一張以 `IndexOverlayKey`
  為鍵的表(label / toggleKey / stroke / fill / hint / offTitle),兩處 union 改 `keyof ChartToggles`,測試改共用
  `makeToggles()` factory。F1 結構債,本案不動(scope)。
- [ ] **「HH:MM → 分鐘數」編解碼第三份(review round 1 S5)**:`txf-overlay-series.ts::splitStamp` / `hhmm` 與
  `allday.ts::anchorDateOf`、`index-accum-adapter.ts::minuteOf` 同形;候選 = minute 編解碼收進 `lib/allday.ts` 一處。

## 2026-08-27(fix/corr-sparse-leg-heal-exempt SXF 稀疏腿自癒 churn 留尾)

- [ ] **`sparse` 是人工標記,不是量出來的**:判準寫在 tc4-market-facts(全 attempt 1 且間隔 ≥ 門檻);若哪天 SXF 真死
  (stub),R2 不救、只剩 R1(整條 session 靜默 120 s)—— 其他腿活著時 SXF 會整場不救,零訊號。候選 = 稀疏腿改吃
  更長門檻(如 1800 s)而非整條豁免,要先量 SXF 日盤最長真靜默(今天觀察到 22 分鐘)。 **→ 08-28:08-31 量 SXF 日盤最長真靜默後再定門檻。**
- [x] ~~**個股冷門檔同型(6949 每分鐘一發 attempt 1)**:個股 source 的 R2 60 s 對零股 / 冷門檔同樣是假警報,但個股是
  自選動態集合,沒有設定檔可標 —— 走 08-26 節「從未推播 / 冷門檔退避上限 60→300 s」那條,不套 sparse。~~
  → 08-28 triage:與 08-26 節 N051 6949 條同件事(退避上限 60→300 s),留那條。
- [ ] **收盤段 `IX0001` 每 30 s 一發 —— 已出貨待次一交易日真環境驗**:08-27 user 拍板 13:25(mod/stock-heal-gate-end-1325),
  pr-126 F-01 收修為 per-consumer(mod/heal-gate-per-consumer):**只有 index session** 吃 `in_index_heal_window_now` 13:25,
  個股 / corr 台積電腿留 `in_trading_hours_now` 13:35(試撮期個股仍有簿更新推播,一起關是零收益純代價)。看門狗 13:25 下班、
  訂閱不退、13:30 收盤推播照收。驗法:`grep 零推播自癒 logs/server-<次日>.log | grep IX0001` 13:25 後 0 筆 + 13:36
  `curl /api/index/state` 記 twse 最後更新時戳(同時反證 F-03「誤判 vs 真死」);**驗過再勾**(pr-126 F-08)。 **→ 08-28:08-31 對帳驗(13:25 後 0 筆 + 13:36 現價欄)。**
- [x] ~~**重掛 snapshot 會清 heal attempts → 退避 / 換窗階梯可能永不升級**(08-27 盤後發現,未證):TC4 對 SUBQUOTE 回
  snapshot(tc4-market-facts fresh subscribe 事實)→ `tc4._note_push` 清 `_heal_attempts` / `_heal_next` → 下一輪又從
  attempt 1、base 門檻起算;IX0001 收盤段 19 發 30 s 等距 attempt 全 1、SXF 兩發剛好 240 s 都是這形狀。若 symbol 真死
  但 SUB 仍回 stub snapshot,`HEAL_VARIANT_AFTER` 永遠到不了 = 08-14 凍結 stub 那類病 REALTIME 側沒有逃逸路。要證得先
  加一行 DEBUG 記「snapshot 到達 vs 上次重掛時距」;候選 = 重掛後第一則推播若在 N 秒內且無新成交時戳,不清 attempts。 **→ 08-28:DEBUG 蒐證行併 `/mod` 可觀測性小批。**~~
  → 08-28 mod/observability-batch-0828:直接做候選(不只蒐證):`tc4._note_push` 指紋 + 10 s 寬限,同指紋 snapshot 不清 attempts,DEBUG 一行;6949 一天 92 發即實證。
- [x] **`in_trading_hours_now` / `_TRADING_END` 名不符實**(review Standards P2;per-consumer review F-S2 重申):pr-126 F-01
  後 `_TRADING_END` 回 13:35,13:25–13:30 那半段名實相符了,但 **13:30–13:35 已收盤函式仍回 True** —— 它實質是「個股自癒 /
  健檢閘窗(上界 13:35 是啟發式)」;`corr_source.py:61` / `app.py:416` 讀者只看得到名字,正是 #126 誤共用的同一條失效路。
  index 那把已具名 `in_index_heal_window_now`。獨立 🔵 更名 `in_stock_heal_window_now` / `_STOCK_HEAL_END`,六個讀者一起改。 **→ 08-28:併 D 測試衛生 chore 分支。** **→ 08-31 chore/test-hygiene-batch-2 出貨:更名 `in_stock_heal_window_now` / `_STOCK_HEAL_END` / `_HEAL_START`(六讀者 + CLAUDE.md §4),docstring 補「不是盤中判定」。**
- [ ] **index 閘 13:25 的代價**(review Spec P2-2/3/4;pr-126 F-01 per-consumer 後**只剩指數側**,user 知情):訂閱在
  13:25–13:30 死掉時 (a) 加權分時由 index_engine 尾段回補得回(有日曆且為交易日 → 13:25 起到午夜;無日曆退回 `_HEAL_TAIL_END` 13:40,
  pr-126 F-05);現價欄不靠回補(`_merge_backfill` 只寫 minutes),但同一發自癒會連帶重掛 IX0001
  (`_subscribe_and_backfill`),重掛的 SUBQUOTE snapshot 即一則推播 → 現價欄**應會**跟著回來(pr-128 F-01,未實測;
  08-28 13:36 `/api/index/state` 現價欄 vs 時戳核);(b) 13:25–13:35 新加的**指數**訂閱不武裝健檢。
  個股側不再受影響(閘留 13:35)。pr-126 F-02 / pr-128 F-04 校正一併記下:個股當日重補入列點有五個,**在試撮期訂閱死掉
  這個情境下**會出手的只剩 `set_main_contract`(手動切主圖)與 `_handle_reconnect`(斷線重連);「漲跌停值變」
  (`stock_engine.py` 收件人含 `_backfilled`,只在 upper / lower 真的變動時)與逾時重排該情境下不觸發,群組成員
  60 s 輪詢被 `_backfilled` 擋住;08-27 前那句「個股沒有當日重補」錯。
  兩條都是「13:30 回來一小段」第二段閘的價值,綁下一條的量測 —— 現價欄若真的回來,第二段閘的價值只剩 (b)。 **→ 08-28:併上條 08-31 同一次量。**
- [ ] **IX0001 收盤最後一筆推播幾點到**:index 閘已改 13:25,這個事實現在只決定「要不要加 13:30 回來一小段的第二段閘」
  (user 08-27 提的設計):13:30:0x 即到 → 值得加(多保護試撮 5 分鐘內訂閱死掉的窗);13:33 才到(個股 1K 有 13:33 的
  row,`tests/live/test_stock_source.py:469`)→ 加了也是誤判,維持現狀。量法 = 交易日 13:36 `curl /api/index/state`
  看 twse 最後更新時戳 / minutes 最大鍵,或 13:20 起只聽不訂 probe(`ix_listen_probe.py` 樣板)。 **→ 08-28:併 L101 08-31 同一次量。**
- [x] **`heal_*` 六個參數 Data Clump**(review Standards):`TC4QuoteSource` 六個 heal 參數被 `CorrQuoteSource` 逐字轉發,
  本輪加一個旗標動了 tc4 簽名 + body、corr_source 簽名 + 轉發、app 兩處、四支測試。候選 = `HealPolicy` frozen dataclass
  收攏,四個 source 子類一起改,獨立 🔵。 **→ 08-28:併 D 測試衛生 chore 分支。** **→ 08-31 chore/test-hygiene-batch-2 出貨:`tc4.HealPolicy` frozen dataclass;STOCK_HEAL / FUTURES_HEAL / CORR_HEAL 模組常數 + `dataclasses.replace` 疊閘;test_tc4 28 呼叫點、wiring 10 斷言改 `.heal` 欄位。**

## 2026-08-27(fix/breakeven-avg-source-prod-chain #118 broker 半邊在 prod 是死的 留尾)

- [ ] **流程教訓:blast radius 要 grep「欄位寫入點」不只「建構點」**:#118 的 blast radius 只 grep `Position(` 建構點與
  `avg_source` 字面,沒 grep `avg_price =` 就地寫入 → 真鏈 `client._on_profit_complete` 漏掉,測試綠在一條零 caller 的
  死路徑上。判準:新增欄位時 `grep "<鄰欄>\s*="` 把每個就地寫入點列出來逐一對。待併入 `ops-discipline`(該檔另一 session
  持有未提交修改,先記這裡)。
- [ ] **期貨列 `avg_source` 恆 null(語意缺口,非本輪 bug)**(two-axis Spec (c)):`balance.py::parse_open_interest_line` 給期貨列
  `avg_price=` 群益 OI [6] 平均成本、從不寫 `avg_source`;`merge_fut_positions` / `_stale_fut_positions` 沿用同物件。
  **不會**多加一次買費 —— 期貨列不進 `positionEcon`(`position-summary.ts:116/177` 分開走、`PriceLadder` 是現股梯),
  reviewer 說的後果不成立;真正的缺口是「群益 OI 平均成本含不含手續費」無實證,期貨梯的打平線若日後要吃它得先量。
  與 08-26 節「空方均價語意無真樣本」同一類,等首筆期貨真成交順看。 **→ 08-28:併上條,等首筆期貨真成交。**
- [x] ~~**F-05 `fill_date` 跨日重播復發**(pr-118-review Should):`today_qty` 看成交到達日,群益 ConnectByID 重播含前一日時
  (跨日未重啟)昨天的成交會被算進當沖段 —— 與 08-26 節「`today_qty` 依賴聚合只有當日 backlog」同一條,那條已列。~~
  → 08-28 triage:與 08-26 節「today_qty 依賴聚合只有當日 backlog」同條,留那條。
- [x] ~~**pr-review #116 / #117 / #118 三份報告仍在 repo root 未 commit**(`pr-11N-review{,.audit}.md`);上一輪 #111 是搬進
  `docs/superpowers/specs/` 一起 commit,可比照(單獨 chore)。#117 六條 LOW / #118 十一條 Nice 未動。~~
  → 08-28 triage:六份 `pr-11{6,7,8}-review{,.audit}.md` 已在 `docs/superpowers/specs/`。

## 2026-08-26(fix/breakeven-avg-source-daytrade-tax 打平線均價語意 + 當沖稅 留尾)

- [ ] **空方(融券 / 無券 daytrade_sell)均價語意無真樣本**:群益損益試算的空方「均價」是純賣價、還是扣掉賣費稅後的淨收?
  `positionEcon` 空方分支沿舊式當純價;無券當沖(先賣後買)照法規也是現股當沖 0.15%,但 `today_qty` 減半目前**只套 kind === "cash"**,
  `daytrade_sell` 未套 —— 等 08-27 user 無券當沖實錄(balance.py 負股數整列)一併校準兩件事。 **→ 08-28 併 `/bug 無券空單校準`:① `_FILL_KIND` 補「無券」→ today_qty 對空單生效 ② 負現股列平倉解鎖 ③ 損益列 avg/cost/kind 印 INFO;**倉位線語意(user 確認今日 8358 倉位標記 ≠ 賣出價 512,差約兩檔)等下一筆實錄再定**。**
  **→ 08-30:①② 已出貨(fix/borrowless-short-calibration;前端 `positionEcon` 減半條件加 `daytrade_sell`);③ 已隨 #145 出貨。剩倉位線語意:下一筆無券當沖
  看 `損益列回填 <股號> kind=cash avg=…` 那行的 avg 是否 = 賣出價(純賣價)還是 < 賣出價(扣費稅淨收),再決定 `positionEcon` 空方分支要不要改口徑。**
- [ ] **樂觀加碼時 broker 均價(含費)與純成交價加權**:`_apply_fill_locked` 同向加碼沿用舊來源,新增那幾張少算一次買費
  (0.026%),鏈落地 1–2 s 即消;要精確得讓後端知道折數(= 被否決的修法 B)或前端拆兩段。撞到再說。 **→ 08-28:已知風險,只記著。**
- [ ] **`today_qty` 依賴「聚合只有當日 backlog」**:群益 ConnectByID 只重播當日;若哪天重播含前一日(跨日未重啟、
  或 API 行為變),today_qty 會把昨天的張數算進當沖段。判準 = `_Agg.date` 非今日仍被計入;可加 WARNING 蒐證。 **→ 08-28:已知風險,只記著(可加 WARNING 蒐證併可觀測性小批,視工時)。**
- [x] ~~**群益 APP 損益試算不做當沖減半**(08-26 反推 4991 pnl_base 用 0.3%):今天的部位我們會比 APP 多顯示減半的稅,刻意;
  若 user 日後要「與 APP 一模一樣」模式,加 toggle 把 `SELL_TAX_DAYTRADE` 關成 0.3% 即可。~~
  → 08-28 拍板不做:維持減半(更準),不加「與 APP 一致」toggle。

## 2026-08-26(「做」批 review §5 D 回填:#105 勾銷過頭的留尾 + 跨 PR 留尾)

review `docs/superpowers/specs/2026-08-25-do-batch-review.md` §4.3 點名 #105 那輪 next-time −66/+0 行,七項留尾只活在單輪
verification;這裡回填成 backlog。

- [ ] **N111 深修剩下的一半:ZMQ IO 移出 `_pool_lock`**(`stock_engine.set_watchlist`,#105 verification §5.3):要 per-code
  in-flight 狀態(`owners.add` 先佔位 → IO 鎖外 → 失敗回滾 + 第二個 acquirer 的等待)。**耦合**:N111 現行的退訂正確性
  (`removed` 以 `_refs` 為準)**依賴 IO 在鎖內**,一移出 ST1 洩漏原樣復發 —— 兩件事要同一輪做。
- [ ] **N092 `stock_source.backfill` 真三態化**(§5.4):先把 `parse_hist_tick` 的「試撮窗濾掉」與「解析不出」分流(現在
  兩者都回 None),否則 08:30–09:00 盤前回補會被判成 stub 無限重排。改回傳契約,獨立輪。
- [ ] **N051 另外兩個 churn 來源**(§5.5):收盤段 `IX0001` 13:25:37–13:34 每 30 s 一發共 18 發 → 08-27 user 拍板 index
  閘 13:25(`in_index_heal_window_now`,pr-126 F-01 per-consumer 收修;`_TRADING_END` 留 13:35),**已出貨待次一交易日驗**
  (見 08-27 節「收盤段 IX0001」條,pr-126 F-08 不先勾);個股冷門檔(6921 全日 6 ticks → 153 發)—— 對「從未推播」的檔把
  退避上限 60 s 拉到 300 s。另:N051 逐腿閘的真環境待核項(SXF 休市段自癒發數)#105 §6 沒列,prod 重啟後盤中
  `grep "零推播自癒" | grep SXF` 應大幅少於 M0 的 3 小時 8 發。**08-27 核過:休市段(08:45 前 / 13:45 後)零發 = 逐腿閘
  PASS;日盤 09:45–13:01 另有 11 發是稀疏腿真沒成交的假警報(M0 那 8 發是休市段,不是同一件事),
  已由 fix/corr-sparse-leg-heal-exempt 以 `sparse` 旗標豁免 R2。** 6949 冷門檔 172 發(每分鐘 attempt 1)仍是本條。 **→ 08-28 拍板:6949 退避上限 60→300 s 併 `/mod` 可觀測性小批(達錢無「暫停交易」旗標,今日 6949 回補三次逾時放棄 = 只能反推;暫停交易標示等 B2 調研)。**
  → 08-28 mod/observability-batch-0828:退避上限 300 s 本來就在,病根是重掛 snapshot 清 attempts(上條)→ 指紋規則一併收;**本條留 `[ ]` 到次一交易日 grep 6949 ≤ 10 發驗過再勾**。
- [x] ~~**`corr_source.taifex_leg_gate` 對 SGX / CME / CBOT / OSE 段恆 True**(§5.6):要收得先用 `QUERYINSTRUMENTINFO` 的
  `OpenCloseTime` 把各段時段落成事實(skill 只有 OSE 一組)。~~
  → 08-28 拍板不做:今日實測 SGX TWN 開盤前僅 2 發/日;VX 7 發是稀疏假警報 → 改加 `sparse` 旗標(併可觀測性小批)。
- [x] ~~**`tests/live/test_river_state.py` UTF-8 BOM(N059)**(§5.6)未處理。~~
  → 08-28 triage:與 08-17 節同條(L429),留那條。
- [ ] **corr / futures `_handle_reconnect` 逐字同形**(§7.8 ST5;review 也列 Duplicated Code):對帳單位不同(product vs
  leg.symbol),第三個引擎接同款時再抽;注意兩處**順序已漂**(futures 先 update pending 再 bump epoch,corr 相反),今天等價。
- [ ] **rollover stage1 → worker `set_trade_date` 之間的次毫秒窗**(§7.8 SP1):source 日窗仍舊,靠 `_generation` guard 丟掉
  回補結果 —— 「靠別人擋」不是「結構上不可能」,真要收得把日窗語意納入 generation。
- [ ] **N039 route 層首則 seed send 仍只 catch `WebSocketDisconnect`**(`app.py` 四處),close_sent traceback 噪音仍在。
- [ ] **N038 jitter 對背景分頁無效**(Chrome timer 1 s 對齊),#99 E5 判 PASS 偏寬。
- [ ] **#106 私密視窗偏好靜默不落檔畫面零訊號**(`storage.ts` 四旗標唯一讀者是自己去重)。
- [ ] **/bug H3 昨日段中段缺格 gate 5 不涵蓋**(只比尾根;core 單條 polyline 對任何缺格架橋)+ **切回 tab 最多 60 s 印
  「TC4 回補中」歸因錯**(inactive 停輪詢)。
- [ ] **`futures_engine._leaf_rearm` 不自驅**(只在 `_handle_quote` 消化,`_handle_reconnect` 不自排 → 靠別品推播觸發)。
- [ ] **Duplicated Code 抽取候選**(review §5 D):`capital_api.py` tick 閘尾段六行 ×2;`futExchangeContract` try/catch→null
  第 5 份(`FuturesLadder.tsx`);`flash-locked` 三個產生點(`flash-send.ts` / `FuturesLadder.tsx` / `close-order.ts`);
  `list-drag.ts` 六位置參數 Data Clump(`WatchlistSidebar.tsx` ×2)。
- [x] **「不 Disconnect 則 process 不退」錯句**:`tc4.py` 兩處已改;`futures_engine.py:221/245/258` 三處本輪一併改。 **→ 08-28:併 D 測試衛生 chore 分支。** **→ 08-31 chore/test-hygiene-batch-2 出貨:futures_engine 三處早在 08-26 b0df23b7(「做」批 review §5 B 文件改口)改成「是 daemon=True 之前的舊敘述」,現只剩 L311 一處且正確;本批回填勾銷。**

## 2026-08-26(mod/watchlist-rename-collision A4 改名保留編輯框 留尾)

- [ ] **「新增群組」輸入框仍在 commit 前 eager 清空**(`WatchlistManagerDialog.tsx::submitAddGroup`):佇列視窗內撞名時
  文案出來、字已清(#101 verification §5.3 舊留尾;A4 只收改名)。改成留著要另設守門(清空同時是它的重送防護),
  可照 `renameInFlight` + `onSettled` 的形狀做。
- [x] **`WatchlistManagerDialog.test.tsx` 的 `gatePuts` / `releaseOk` 已是同檔第三份逐字複本**(L365 / L461 / A4 新 describe):
  抽成檔案頂層工廠(`makeGate()` 回 `{ gatePuts, releaseOk, releaseFail }`),要動既有兩個 describe,單獨一個 🔵。 **→ 08-28:併 D chore/test-hygiene-batch-2。** **→ 08-31 chore/test-hygiene-batch-2 出貨:檔頂 `makeGate()` 回 `{ gatePuts, releaseOk, releaseFail }`,三個 describe 各叫一次;N118 測試裡第四份行內 400 resolve 一併改 `releaseFail()`。**
- [x] ~~**`frontend/package-lock.json` 與 `package.json` 不同步**(`npm ci` 拒裝:`@emnapi/core` / `runtime` / `wasi-threads`
  1.2.2 vs 1.2.3):主 tree 的 node_modules 是 `npm install` 長出來的,worktree 只能 robocopy 複製(A4 實踩)。
  修法 = 主 tree 跑一次 `npm install` 把 lock 更新後 commit(單獨 chore,確認 diff 只有 `@emnapi/*`)。~~
  → 同上,08-26 chore/frontend-lockfile-sync 已修。

## 2026-08-26(feat/chart-ux-batch-0826 看盤 UX 四功能 + 成交樂觀套用 留尾)
- [x] ~~**F-20 corr / river route 測試 11 腿 key 字面集合 4 處複製**:要不要改由 `load_config(CONFIG_PATH)` 導出、逐字只留 `tests/test_corr_config.py::_EXPECTED_LEGS`(user 08-26 問「11 腿名單是什麼」,已解釋,待拍板)。~~ → user 08-26 拍板「改」,refactor/f20-corr-leg-keys-from-config:兩檔改讀 `load_config(CONFIG_PATH)`,逐字只留 `_EXPECTED_LEGS`。
- [x] ~~**/pr-review #111 兩條 ask-user**(報告 `docs/superpowers/specs/pr-111-review.md`):F-12 圖牆 toggle 列 5→8 顆在窄寬度會不會換行成兩列 chrome(prod build 分割畫面目視;真換行再收成下拉);F-20 corr / river route 測試的 11 腿 key 字面集合 4 處複製,要不要改由 `load_config(CONFIG_PATH)` 導出、逐字只留 `_EXPECTED_LEGS`。其餘 20 條已於收修 commit 處理。~~ → user 08-26 過目:F-12 螢幕寬度足、不換行,不做;F-20 見下方獨立條。
- [x] ~~**F5 樂觀套用改為「券商快照落地過才開」**(review F-02 收修):開機第一輪鏈落地前的成交只累計;若 prod 觀察到開機後首筆成交沒即時出現,就是這條(鏈通常 1–2 s 內落地)。~~ → 08-26 真環境:13 筆成交全套用、體感變快;鏈 624–5538 ms 落地,無開機首筆延遲觀察。
- [x] ~~**F1 指數疊線右緣標籤與現價泡泡 / CDP 標籤互疊**(1568 寬截圖可見「加權 +0.9x%」壓在 2400 現價標旁):
  末點標籤目前只做 `textAnchor=end` 上移 3px,沒進 `bandLabels` 的避讓;候選 = 把兩顆指數標當 obstacle 餵進既有
  右緣避讓(R1 CDP 七顆那套),或 toggle 開時把標籤改畫在 readout 列。user 過目後決定。~~ → user 08-26 過目「不會」,不做。
- [x] ~~**F1「台指」語意**:本輪解讀為加權指數 IX0001;若 user 原意是台指期(TXF),`useIndexStream.txf` 只有最新價無
  逐分鐘序列,要從 `/api/market/bars/TXF tf=1` 另接一條(期指 08:45 起、窗與現貨不同尺)。~~ → user 08-26 拍板:要的是**台指期**(TXF)→ 另案 /feat(從 `/api/market/bars/TXF tf=1` 接逐分鐘序列)。
- [x] ~~**F4 台積電現貨腿 `TC.S.TWS.2330` 與個股引擎共用 symbol 的 refcount 風險**~~ → /pr-review #111 F-01 升 Must Fix,已收修:corr 的 TWS 腿改用與個股引擎**同一把**訂閱窗 key(`stock_window(當日)`),兩邊各持一份 count 2→1 永不歸零(`tests/live/test_corr_source.py::TestTwsLegWindow`)。盤中仍看一次:自選移除 2330 後 corr 台積電腿要照常有值。
- [x] ~~**F4 台幣匯率達錢不提供**(全樹掃 TWD 只命中 SGX TWN;現貨段只有 TWS;CME / TAIFEX 匯率期貨皆無 TWD):
  要做只能接非即時源(FinMind / 央行)當日線腿,不合相關係數的秒級口徑;若 user 仍要,另案。~~ → user 08-26 拍板:達錢沒有就不做。
- [x] ~~**F4 江波圖 11 色是否分得開**待 user 過目(river-8..11 天藍 / 靛紫 / 鋼灰藍 / 棕褐,後兩色靠低飽和區分);
  `RiverOverlay.tsx` / `RiverPanel.tsx` 註解仍寫「七腿」(成本例證,論點更強不影響正確性)。~~ → user 08-26 過目「分得開」。
- [ ] **F5 期貨成交契約碼組法只有一筆真樣本**(08-26 整天無期貨成交,仍未驗)(`QEF06` + idx33 `202606` → `QEFF6`):首筆真期貨成交後看 log
  「期貨部位鍵差異(樂觀 vs 券商)」;不同就改 `mapping.contract_from_fill`。另 **無券當沖(flag 無券)/ 零股不套**,
  仍走回查鏈;無券的部位狀態與 balance.py 負股數校準同一條(08-20 待實錄)。 **→ 08-28:等首筆期貨真成交,agent 看 log 即可。**
- [x] ~~**F5 真成交耗時數字**:三段 log「balance 鏈: … 自成交回報到達起 N ms」已備,下一筆真成交後把數字記回
  `.claude/feat/chart-ux-batch-0826/verification.md`(現在只有 FakeCom 模擬:修前 463 ms、修後推播早於回查鏈)。~~ → 08-26 已記回 verification.md:樂觀 0.0–0.7 ms、鏈落地 624–5538 ms(13 筆)。
- [ ] **F5 成交到達時回查鏈若在途,該輪落地會短暫覆蓋回成交前快照**(與現狀等長的空窗,不擴大);
  若盤中觀察到「部位閃一下回舊值再回來」就是這條,候選 = 鏈落地時對 `_fill_seen_at` 之後到達的成交重新套一次。 **→ 08-28 拍板升 `/bug 部位快照不得倒退`:鏈落地時對 `_fill_seen_at` 之後到達的成交重新套一次(根治)。**
- [x] ~~**worktree `frontend/npm ci` 失敗:package-lock.json 與 package.json 不同步**(@emnapi/* 版本);主 tree 是
  `npm install` 裝的。開 worktree 只能 robocopy node_modules;要根治就 `npm install` 更新 lock 一次(獨立 chore)。~~ → 08-26 chore/frontend-lockfile-sync `npm install` 更新 lock(diff = @emnapi/* + wasm32-wasi optional 平台包 bundled 項 + yaml peer 旗標)。
- [x] **`tests/server/test_ws_disconnect.py::test_close_sent_runtime_error_is_not_logged_as_warning` 全量並行下偶紅**
  (本輪 1 次;單跑 3/3 綠;不在本分支 diff)—— 與 08-26 fix/tc4-logout 留尾的 flake 候選同一條。 **→ 08-28:併 D chore/test-hygiene-batch-2。** → 08-31 出貨(部分結案):斷言改只看 `copycat.server.ws` logger(caplog 收整個 root,他測殘留背景執行緒的 WARNING 落進 2 秒窗即誤紅);候選根因未親眼抓到那則紀錄,再紅時失敗訊息印 caplog.text 可回溯。**洩漏源已有實證**:pr-160 review 跑 8 檔後端測試,收尾冒出 `tc4.py _listen_loop` 殘留執行緒的 PytestUnhandledThreadExceptionWarning —— 本測試已免疫,其他 caplog 負向斷言未免疫,follow-up 見下一條。
- [ ] **TC4 `_listen_loop` 執行緒活過測試(pr-160 review 實證)**:候選修法 = conftest autouse fixture 測後斷言無殘留
  `_listen_loop` 執行緒(或揪出漏 `close()` 的 fixture)。影響面 = 全套件所有 caplog 負向斷言與執行緒計數斷言。
- [ ] **空回補免 seq bump(pr-160 review F-04)**:`stock_state.apply_backfill` 對 `ticks=[]` 且倖存集 = 現況時仍 `seq +1001`
  → 前端跳號規則整片重掛 tbody,純 no-op、開盤 ×N 檔各一次。候選 = 空回補且無變化時不 bump(行為改動,單獨分支;
  contract 見 CLAUDE.md §4 個股 seq 條「例外已知且刻意」段,改時要同步改口)。

## 2026-08-26(mod/shutdown-budget A1 關機預算同源 留尾)

- [ ] **signals 段(`bot.close()` + hub drain)無上限**,只算進 `LIFESPAN_SLACK_SECS`(5 s);
  Discord 端網路壞掉時 `discord.py` 自己的 timeout 才是上界,超過就擠掉 TC4 的預算。候選 =
  `asyncio.wait_for(signals_close, LIFESPAN_SLACK_SECS)`,但要先確認 hub 落檔在 timeout 內完成
  (jsonl 是真相源,不能被 cancel 半途)。
- [x] **run.ps1 finally 內第二次 Ctrl+C 未驗**:PowerShell 5.1 的 finally 在 `WaitForExit` 阻塞時再按
  Ctrl+C 是否中斷、中斷後 `Stop-Tree` 還跑不跑 —— 跑不到的話 backend 就留著。上限拉到 83 s 之後
  這條路比 15 s 時代更可能被人踩到。盤後用 --verify server 走一次即可驗。 **→ 08-28:今日盤後以 `--verify` server 驗。**
  **→ 09-01 00:26 stub harness 驗畢(結案)**:複製 run.ps1 try/while/finally 結構 + 無視 Ctrl+C 的 stub backend,
  AttachConsole 對整個 console 送真 CTRL_C_EVENT 兩次 —— (1) 第一發直跳 finally(while 後那行不跑,與
  `$backendGotCtrlC` 設計假設一致);(2) **第二發在 `WaitForExit` 阻塞期間被完全無視**:等待仍足秒(30 s 設定值
  00:26:02.450 → 00:26:32.457)、`Stop-Tree` 照跑、backend 樹收乾淨 —— 「finally 被打斷 → backend 留著」**不成立**;
  (3) 翻面代價:第二次 Ctrl+C **不能提前放棄等待**,TC4 半死時狂按無效、最壞等滿 83 s 才硬殺(知情即可,run.ps1
  已印上限與去哪看);(4) finally 之後的語句不會跑(run.ps1 finally 後無語句,無影響)。真 `--verify` server 免跑:
  問題本體是 PS 5.1 語意,stub 的 finally 結構與 run.ps1 逐字同形。
- [ ] **上界 83 s 是「TC4 半死」可計段的數字,不是承諾**:半死時 LOGOUT 自己也送不出去,等待只是給
  **健康** session 收尾的機會;真要縮短得在 `close()` 進場時把 socket 的 RCVTIMEO 調短(`api.lock`
  持有下 setsockopt 才安全,而 KeepAlive Pong 共用同一把鎖)—— 動到 wrapper 共用 socket,獨立一輪。
- [ ] **wrapper `KeepAliveHelper.ThreadProcess` 只 catch ZMQError**(`spikes/TCPY/tcoreapi_mq.py:292-303`,
  本地 patch 版):`Pong` 在 try 外,recv 撞 RCVTIMEO 會帶著 `api.lock` 死掉(= 既知的毒鎖,`_dispose`
  取不到鎖會跳過 Disconnect,無害);但 decode 類例外殺掉執行緒時鎖已釋放、SUB socket 永不關 →
  `Disconnect()` 的 `_ctx.term()` **無界阻塞**,那條 lane 只能靠 run.ps1 硬殺。修法 = try 包住整個迴圈體 +
  finally 關 socket(wrapper 是 gitignored 本地檔,改了要同步 `docs/research/2026-07-06-tc4-stock-tick-1k-api-report.md` §11)。

## 2026-08-26(08-25 盤中觀察對帳 + fix/tc4-logout-and-cancel-reply-warning 留尾)

- [x] **加權分時 minutes 盤中整天沒長(每個交易日都在發生,非 08-25 批回歸)** —— 08-26 PR #115 根治:IX0001 quote 無時間欄位(FilledTime 恆 '0'),分鐘鍵改牆鐘;prod 收盤後重啟、次一交易日 09:10 驗。原記:`index 分時自癒`
  08-20 73 / 08-21 67 / 08-24 91 / 08-25 133 行,形狀 = 09:04 以「空 minutes 09:00 起算」首發、之後每 7 分一發、
  每發「無進展:零新分鐘鍵」、variant 一路爬到封頂;同期 IX0001 REALTIME 在 source 層 30 s 靜默閘 09:00–13:25
  **零觸發**(推播有進來)。兩條路同時失效:1K 回補這半是 TC4 凍結 stub(08-14 已知);推播→`_handle_quote`→
  `s.minutes[key]` 這半未定位(`minute_key(FilledTime, utc=True)` 回 None?`_pending_date` 沒 swap?)。
  user 症狀:「加權分時線中間又卡住」。**下一步 = 交易日 09:10 打 `/api/index/state` 看 `twse.minutes` 筆數與最大鍵**
  (n≈10、max≈0910 = 推播路徑正常 → 自癒判準另有問題;n=0 = 推播寫入壞),再開 /bug。晚間重啟的 1K 回補 270 分鐘
  正常,所以只有盤中能量。
- [x] ~~**期貨 1K 落後 / 中段缺格沒有後端量測**:user 08-25 盤中看到「K 棒沒更新 → 分時不連貫」,後端 log 零筆
  (落後判定在前端 gate 5;後端只記 timeout / 回空,當日 TXF 零筆;17:16 重啟後當日序列完整 → 屬 H1 暫時落後或
  H3 memo 釘住二者之一,事後不可分辨)。候選 = `futures_engine` 每分鐘記「bars 尾 vs 最後成交時戳」差 > N 根的 WARNING
  (固定前綴供 grep),讓 H1/H3 事後可分。 **→ 08-28 拍板做:併 `/mod` 可觀測性小批。**~~
  → 08-28 mod/observability-batch-0828:`futures_engine._check_1k_health`(`bars_range` tf=1 成功時;前綴 `期貨 1K 落後` / `期貨 1K 中段缺格`,同尾根一次)。
- [x] 處置股 badge(FinMind `TaiwanStockDispositionSecuritiesPeriod` 名單已在 breadth 引擎)—— **user 08-26 拍板不做**,
  視覺自評即可;2455 08-25 的 TradeStatus 每 2 分鐘 1→0→1 共 133 次即處置分盤形狀,留作 N100 蒐證樣本。
- [x] **flake 候選:`tests/server/test_stock_engine.py::TestStreamAndStatus::test_stream_receives_tick_and_book`**
  (08-26 全套三輪中一輪紅:`tick_msg["seq"]` 拿到 1002 而非 1,像是別的測試灌了 1000 筆 tick 的狀態漏進來;
  單跑 3/3 綠、其餘兩輪全套綠、當輪 diff 只動 tc4 close / capital reply log)。候選 = 找共用 StockState /
  engine 實例的 fixture 或背景 thread 殘留;再紅一次就開 /bug。 **→ 08-28:併 D chore/test-hygiene-batch-2。** → 08-31 chore/test-hygiene-batch-2 出貨:根因 = 主圖入列的空回補照樣 `apply_backfill`(seq +1001),worker thread 先於 tick 落地時首則 tick seq=1002;測試改用 `backfill_gate` 卡住回補讓 tick 必為首事件,斷言不動。不是狀態外漏。
- [ ] **現股當沖 / 信用當沖資格顯示**(user 08-26 提問,未拍板):現股當沖 = FinMind `TaiwanStockDayTrading`
  (`BuyAfterSale` Y/＊ = 僅先買後賣;回測 `backfill_daytrade.py` 已用),信用當沖 = `TaiwanStockMarginPurchaseShortSale`
  資券標的;兩者皆 EOD 名單,T 日名單 FinMind 幾點更新未實測;群益 `sDayTrade` 是送單意圖不是資格,SKCOM 有無資格查詢 API 未查。 **→ 08-28:併 B2 調研(達錢商品資訊有無當日當沖資格 / 暫停交易;證交所當日名單 API;FinMind 當日更新時刻;順便列達錢還能拿到哪些欄位)。user:不能用前一日名單。**

## 2026-08-25(fix/futures-intraday-lag-bridge 期貨分時 live 點架橋 留尾)

- [ ] **歷史段永久 memo 會把「分頁靜默截斷的非空日」永久釘住**(bug H3;`bars.py::put_hist_range` 只對「截斷後面的日子」不寫負向快取,截斷**當日本身**的非空殘段照樣 `_hist[(code,day)] = got` 永久化):症狀 = 前一交易日序列中間 / 尾巴缺一段,一直到 server 重啟才消失,零 log。候選 = 對 allday 1K 以「該日應有分鐘數 / 尾根時刻」做覆蓋度判定,不足者不入 memo(同 `_possible_data_days` 的日曆判定可算出期望尾根)。本輪 gate 5 只擋「live 點架橋」,中間缺格仍會被 core 單條 polyline 直線相連。

## 2026-08-24(mod/stream-ui-misc two-axis 留尾)

review 收修已出貨(NaN ref 語意反轉 / `commitRef` 單一出口 + backstop 移除 / 文案全繁中 /
seq 契約落檔 / `otcSourceDead` 抽 lib);以下為刻意不做的:

- [ ] **`OVERLAY_LINES` 以「輸入序」查表,輸入本身不帶識別**(`lib/index-chart-svg.ts::
  `OverlayLinePts.index` → `MarketPane` 的 `OVERLAY_LINES[l.index]`):N262 修的是「過濾後
  位置塌陷」,但**位置仍是唯一的識別**——哪天有人在 `buildOverlayGeometry` 的輸入陣列前面
  插一腿(或把加權 / 櫃買調換),線色與標籤會整排錯位,而畫面照畫、零錯誤訊號(現有測試
  鎖的是 `[0,1]` / `[1]` 這種**位置**,同樣跟著漂)。候選 = 輸入改帶 key
  (`{ key: "TWSE" | "OTC", minutes, ref }`),幾何回傳 key、呼叫端以 key 查表(ST4);
  順帶讓 `OVERLAY_LINES` 從陣列變 `Record<key, style>`,「腿數多於樣式表」那條 guard 可退休。
- [x] **`signal-model.ts::formatToastText` 待刪**:prod 已無讀者(只剩 `useSignalAlerts.test`
  拿它當期望值來源)。現況是**同源同義反覆** —— 實作與斷言同一顆函式,文案改動 mutant 全綠。
  順序不可顛倒:**先**把測試的期望值改成字面量(逐字寫死文案 + 註解寫拆解),lock 生效後
  才刪 `formatToastText`。先刪的話那批斷言只能整條拿掉,等於把文案的守門一起丟了。 **→ 08-28:併 D chore/test-hygiene-batch-2。** **→ 08-31 chore/test-hygiene-batch-2 出貨:兩筆:先把 useSignalAlerts / signal-model 測試期望值改字面量 `toastText(id)`(拆解註解),再刪函式 + describe + import;formatGroupToastText docstring 改口。**
- [x] ~~**N109 的真分態需後端 seed 加欄位**~~ → 08-31 出貨:status 加 engine 欄(engine 恆 true / 無 engine seed false),前端兩句分態。原文:`status.tc4 === "down"` 的兩個來源(engine 在但
  TC4 斷 / 無 engine 模式)前端沒有可分辨訊號,本輪只能出「對兩態都誠實」的單句。真解 =
  `stock_engine` 的 status seed 加一個「engine 是否存在」欄(`/api/health` 刻意不含引擎
  健康度,不要改那支),前端才分得出「等它自癒」與「去重啟伺服器」。屬後端改動,擇日排。 **→ 08-28 拍板做:小 `/mod`(後端一欄 + 前端兩句話)。**
- [ ] **N108 判別子是啟發式,換源要重看**(`lib/index-source-health.ts::otcSourceDead`):
  「加權 ≥2 格而櫃買 0 格」只抓得到**開盤即死透**;MIS 盤中才壞(已有格)判不出來,
  而櫃買改用非 MIS 的來源時整條判準的前提(otc 不吃 `stale`、5s poll)就不成立了。
  改櫃買資料源時**必須連這支一起重看**,否則它會靜默地永遠回 false。
- [ ] **N120 回補後 `n` 整段平移一次 → tbody 重掛一次**:`apply_backfill` 的 seq 跳增
  (`_BACKFILL_SEQ_MARGIN` 1000 + 回補筆數)讓由尾回推的號整段位移,同一批成交換一批 key。
  可接受(回補是一次性事件,且跳增本來就是要前端偵測到並重抓全量),characterization 已鎖在
  `stock-accum.test.ts`。真要消掉這一次重掛,key 得改吃「不隨 seq 走的成交識別」
  (後端逐筆給 id,或以 `t + cum_vol` 組鍵)—— 屬跨檔契約改動,不順手做。

## 2026-08-24(架構債盤點,唯讀)

- [ ] **全站抽象化 /refactor Why gate 未過(user 拍板 (d) 沒有具體被卡住)→ 改為盤點文件**
  `docs/superpowers/specs/2026-08-24-architecture-debt-inventory.md`:A 後端 engine 骨架 /
  B app.py / C 三座梯 / D 分時圖 / E localStorage(/mod)/ F WsStatus ×7 / G fade / H fake source
  兩份,每條附觸發條件、半徑、seam、步數草案。**沒撞到觸發條件不動**;撞到時直接取用不重調研。

## 2026-08-24(mod/futures-intraday-features two-axis 留尾)

review 收修已出貨(基準日改吃圖上錨定日 / CDP·MA parity fixture / `splitCapitalStamp` /
全形括號);以下為刻意不做的:

- [ ] **J1:`IntradayChartCore` 的 mode 四態(stock / index / futures / stkfut)分歧散在五處**
  —— x 窗 `xw`、`snapRadius`、`vpEnabled` + 副圖能量、疊線三元組
  (`overlay` / `overlayFailed` / `supported`)、五顆 toggle 的 `available` / `hint` + 空態文案。
  每加一個 mode 就要記得五處都改,漏改的樣態是「新 mode 沿用了現貨窗的預設」——
  圖照畫、只是對位或可用性靜默錯掉,零測試會紅。候選 = **per-mode capability 表**
  (一個 `Record<Mode, Capability>`,五處各自查表),分歧收在一個地方讀得完。
- [ ] **J2:`MINUTE_SNAP_RADIUS` 與 `XWindow` 常數不同源**:snap 半徑是「幾個 key」,
  而 key 的語意由當前 `XWindow` 決定(現貨窗 = 分鐘、近全軸 = 軸索引)。兩者分開放的話,
  換窗時半徑的實際涵蓋範圍跟著變而沒有任何提示。候選 = 併進 `XWindow`(每個窗自帶
  預設 snap 半徑),`buildIntradayGeometry` 的 `opts.snapRadius` 退成覆寫。
- [x] **期貨日 K `staleTime: Infinity` 跨日不重抓 → 基準日停在昨天**
  (`hooks/useFuturesBars.ts:61`):疊線資料源與日 K 模式共用同一份 query,`Infinity` 讓它
  「一天只打一次」—— 但 preview 整天掛著(看盤日常,CLAUDE.md §1)跨過午夜後那份 cache
  不會失效,新交易日的圖會拿**前一天的**基準日畫疊線。本輪的錨定日判準只保證「不畫到
  未來 / 當前這一節」,對「停在更早的一天」無感(那正是它刻意的安全側)。候選 = staleTime
  改吃「到下一個交易日切換點」的毫秒數,或 queryKey 帶交易日。**現象輕微但整天掛著必中**。 **→ 08-28 拍板升 `/bug`(整天掛著必中)。**
  **→ 08-30 fix/futures-daily-bars-rollover 出貨**:日 K `staleTime` / `refetchInterval` 改函式形式吃 `msUntilNextLocalDate` + 60 s slack(界 = 本機日曆午夜,不是 15:00 錨定日翻頁 —— 後端 `build_period` daily cache 鍵是 `date.today()`,午夜前問到的還是同一份);queryKey 帶日期那條否決(只在 re-render 時重算,週末無輪詢 = 無 re-render)。四條 hook 測試釘住(一直在 tab / 切走再切回 / 背景分頁 / 兩個午夜恰兩發)。
  **→ 08-30 晚 /pr-review #151 F-01 Must Fix → fix/pr-151-review-followups 收修**:那版 `msUntilDayRollover(Date.now())` = 「到下一個午夜 + slack」,
  而 TQ v5 每 render 都 `setOptions` 重排計時器 → 00:00–00:01 內任一重繪把那一發推到隔天,「一直在期貨 tab 上」主情境其實沒修好
  (`FuturesChart` 每則 WS 訊息重繪)。改成界嚴格在 from 之後(`msUntilNextLocalDate(new Date(from − slack))`)+ 秒級量化;
  紅測試 = slack 窗內每 100 ms rerender 40 s。報告 `docs/superpowers/specs/pr-151-review.md`。
- [ ] **`o.date` 的夜盤跨午夜組合假設未證**(`lib/fill-marks.ts::alldayFillPoints`):
  群益回報的 `date` 是否為最新事件日**未實證**(08-28 pr-134 F-01:同日 C/D 實測仍原單日期),而近全軸把 `date + time` 組成時戳後丟給 `anchorDateOf`
  —— 這假設了「夜盤 01:00 的成交,`date` 已是次一日曆日」。若群益實際回的是委託所屬交易日
  (即 01:00 成交仍記前一日),`anchorDateOf` 會再退一天 → 該筆成交**靜默不畫**。
  失效在安全側(不畫 < 畫錯分鐘),故本輪不猜。待**真夜盤成交一筆**取證後決定是否改判準。 **→ 08-28:併 N075 夜盤實驗那筆回報順看,等事實。**
- [ ] **`EnergySub` 改單一 `<path>`**(N047 量測後的真正收法,verification §N047):
  1140 個 `<rect>` → 1 個 path,節點數降三個量級。**不走「資料版本 memo key」**——
  1K 回補可以在總量不變下改寫某一分鐘的量,以總量當版本會讓副圖靜默停在舊值(用錯誤換效能)。
- [ ] **期貨 POC 標籤印桶心 `23002.5` 而非檔位價 `23000`**:`futuresBarsToAccum` 以近全軸
  自折 VP(不經 `foldVp`),桶心落在兩檔之間。待 user 表態(verification 待驗項 4)後再定
  —— 改印檔位價要先決定「桶跨多檔時算哪一檔」,不是純顯示改動。 **→ user 08-28:現在就放著(那是價位不是量;不讀它)。**

## 2026-08-24(mod/chart-label-batch two-axis 留尾)

review 收修已出貨(N007 讓位方向 / 界單位 / N044 補完 / 三處斷言字面量 / helper 抽取);
以下為刻意不做的:

- [ ] **LabelSpan 型別統一**:同一個「一段文字的水平佔位」在本批有三種表示法 ——
  `{ x, width }`(`vwapLabelBox`)、`span: [a, b]`(`buildVwapLabel` / `spansOverlap`)、
  `x + half`(極值文字 `maObstacles`)。三者互轉散在呼叫端,轉錯不會紅(只是避讓帶偏)。
  候選 = 一個 `LabelSpan` 型別 + 兩個建構子,轉換只留一處。
- [ ] **`maLabelLeft` 的 MA 標籤寬仍硬編 `EDGE_LABEL_W`(34)**:那是個股 `fmtTickPrice`
  口徑的上界,index / 期指態的 MA 是 8 字(≈45.6px)—— 與 N006 同一種病(N006 只修了
  VWAP 標籤與極值文字的寬)。症狀:走廊左緣算窄了,MA 標籤與極值文字「判定說不撞、
  畫出來撞」的窄帶約 11px。**下輪動 MA 標籤時帶走**。
- [ ] **index 態極值標記文字仍走 `fmt`**(`24283.54`),與同圖 `fmtIndexPts` 兩套口徑
  (R1 verification §5 已記)。它畫在繪圖區內、不參與右緣寬度 clamp,故 N006 沒收它。
- [ ] **N062 修後 1536×678 以下仍會溢出**:6rem 地板讓 1536×700 的家數帶 section 需求
  252 ≤ 262,餘裕只有 **10px** —— 視窗再矮 22px 就回到出捲軸。候選 = 家數帶 section 的
  `flex` 由 `0 0 auto` 改 `5 1 auto`(讓它跟著壓縮而不是硬撐),**本輪未評估**。
- [x] **`CandleChart.test.tsx` 含歷史 NUL 位元組**,git 判整檔 binary(diff / grep 全瞎;
  N026 的 class 鎖因此只能落在新檔 `CandleChart.caption.test.tsx`)。獨立 chore 清掉。 **→ 08-28:併 D chore/test-hygiene-batch-2。** **→ 08-31 chore/test-hygiene-batch-2 出貨:3bef8634 帶進的 `"漲跌 -\0"` 清掉(not.toContain 恆真),改 `/漲跌 -(?!\d)/`;git 不再判 binary。**

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

- [ ] **R5 封關夜近似誤差**(次一營業日休市的夜仍空 churn,方向安全)獨立開條;`river_state.py:72` clamp
  守門改名次小者贏需 per-offset rank(與 TQ-8 同設計);跨午夜表補週五 23:00 / 週六 23:00 / 週日 01:00 / 週一 08:50。
## 2026-08-20(盤後 server log 巡檢發現)

- [ ] **融券的 [25] 代碼未實證,刻意不對映**(上條留尾):首次持融券過夜時 log 會出現
  「種類標籤未知 …整列」,拿該列 [25] 值(疑 3)回填 `balance.py::_PNL_KIND_CODE` 即收工;
  在那之前融券部位的均價/打平照舊缺值(寧缺勿錯)。 **→ 08-28:等首次持融券過夜(今日無券空單走的是現股負股數,沒碰到融券列)。**
- [ ] **當沖空單第二層校準:kind 歸類 + 平倉映射解鎖**(2026-08-20 user 實報空單標記方向錯;
  第一層已出貨 = 現股/融資負股數保留空方向 + 整列蒐證 warning + 平倉暫鎖):user 下一筆
  現股當沖先賣(或資券互抵)開倉期間,log 會出現「balance line 負股數…整列」與損益列的
  「種類標籤未知…整列」(若為融券態)→ 依實錄決定 (a) 負現股列歸 `daytrade_sell`(close
  映射 `("daytrade_sell", False)` 已備)還是維持 cash + 補 `("cash", False)`;(b) 該態損益列
  的 [25] 代碼與均價口徑(打平線要不要吃它)。校準後改 `test_cash_short_direction_close_
  blocked_until_calibrated` 為解鎖語意。注意:打平公式的 SELL_TAX 固定 0.3%(user 拍板不分
  當沖),當沖實際稅 0.15% → 空單打平線會偏保守(往不利側),要精確另議。 **→ 08-28:今日 8358 無券空(現股列 T,-1000)實錄已取得,併上條 `/bug 無券空單校準`;(b) 損益均價口徑等下一筆。**
  **→ 08-30 (a) 已定:負現股列歸 `daytrade_sell`(`_CLOSE_MAP` 既有鍵解鎖 = 現股買);`test_cash_short_direction_close_blocked_until_calibrated` 保留、
  語意改口為「cash 負向 = 資料矛盾」。負**融資**列仍鎖(資券互抵無實錄,WARNING 文案改「融資賣超,未校準」)。(b) 見 08-26 節。**

## 2026-08-20(refactor/memo-boundaries R6 留尾)

- [ ] **GroupGridView 2.5 萬 SVG 節點縮減**(handoff R6 原文):per-card memo 已有,
  節點數縮減屬視覺/結構設計變更(虛擬化或降採樣),另案 /mod。 **→ 08-28:user 目前不覺得卡;併 `/perf 開盤回補並行` 一起量,不卡就勾。**
## 2026-08-20(mod/signals-today-offload 留尾)

- [ ] **loop 預設 executor 同池耦合**(review C-1):to_thread 全走同一 ThreadPoolExecutor
  (daily_bars / capital close / signals-today / hub append),TC4 半死的不可中斷殭屍執行緒
  堆積時全池排隊。若 prod 觀察到 today / daily_bars 變慢,考慮給「純本機檔案 IO」一個
  獨立有界 executor;`_warned_years` check-then-add 跨執行緒(review C-3)屆時一併看。

## 2026-08-19(mod/futures-broadcast-coalesce-leaf-unsub 期貨廣播 coalesce 留尾)

- [x] ~~**leaf 備胎訂閱退訂(user 2026-08-19 拍板本輪不退)**:handoff R2 原要求 HOT 回魂後退 leaf;spec review 指出退訂後 HOT 再被
  TXO session 搶走推播(同 symbol 只推一邊,UNSUB→SUB 救不回)時既有再武裝路徑(pending `st.p is None` 只冷啟動、跨日重武裝只掃
  `_leaf_fed`)都不觸發 → 凍結零訊號;夜盤冷門品「靜默再武裝」又會乒乓。要做 = 先設計 engine 層 HOT 靜默偵測(>N 秒且同族他品有推播)
  再武裝,且 `unsubscribe_leaf` 不得 `_ensure_connected`(review I1 KeepAlive 洩漏)。coalesce 後雙流 WS 流量已歸零,收益只剩 engine CPU。~~
  → 08-28 拍板不做:備胎流負擔 = 幾個商品 × 每秒幾筆,可忽略;退訂有凍結風險。
## 2026-08-19(mod/txo-snapshot-no-redundant-push TXO 快照只在內容有變才推 留尾)

- [x] ~~**TXO 推播仍是全量整包**(review R10):有行情時 spot 每次價變都推整包;delta / 分欄推播未做。
  〔2026-08-20 實測:夜盤 60s 收 24 則,每則中位 17.1 KB(min 15B=ping),0.4 則/s ≈ 410 KB/min;
  日盤價變頻率更高,量級成比例放大〕〔2026-08-21 M0 日盤 12:35 實測 60s:19 則(另 5 則 ping),
  每則 **27.1 KB**(日盤鏈更寬),0.32 則/s,間隔中位 2.7 s(min 1.0 s / max 10.2 s)≈ **503 KB/min**;
  則數比夜盤少但單則大 58%,總流量 +23%〕~~
  → 08-28 拍板不做:本機每秒 ~8 KB 無感;跨機器看盤再做 delta。
## 2026-08-17(mod/corr-nk225m-leg batch3 R5 留尾)

- [x] `tests/live/test_river_state.py` 帶 UTF-8 BOM(`ruff format --check` 報;非 gate)—— 順手批去 BOM。 **→ 08-28:併 D chore/test-hygiene-batch-2。** **→ 08-31 chore/test-hygiene-batch-2 出貨:連同 `tests/server/test_futures_engine.py` 一起去 BOM。**
- [ ] next-time:758(跨 UTC 06/22 邊界推播)本輪 20:1x 起跑仍未跨邊界,**未驗**;`spikes/nk225_leg_probe.py`
  可帶 `--listen-secs` 拉長在 13:5x 起跑順帶驗。 **→ 08-28:08-31 13:50 跑 probe(今日 15:00 才想到,14:00 邊界已過)。**

## 2026-08-17(mod/positions-pnl-display batch3 R3 留尾)

- [x] ~~**成交點精確版 / 群組卡個股期委託標記可直接吃 `code`**~~ → 08-31 出貨(orders/fills 皆附 code;fillsByCode 分組鍵改 code)。原文:(R2 留尾的「契約碼→股號反查」已由本輪後端
  `stock_code_of` 提供;`GET /api/capital/positions` 有欄,orders 尚無 —— 精確版加 `code` 到 orders 同款)。 **→ 08-28:併 L439 精確版。**
## 2026-08-17(mod/intraday-fill-marks batch3 R2 留尾)

- [x] ~~**成交點精確版**(D7 拍板近似版的替代)~~ → 08-31 出貨:FillRecord + GET /api/capital/fills,前端每筆真實價×時刻一點(同點無損合併),近似版三失真消失;舊後端 404 → 不畫(D2 拍板)。store.py 委託建立日註解一併校正於 models.FillRecord docstring。原文:後端 `CapitalStore` 保留逐筆 D 事件
  `(seq_no, time, price, qty, buy_sell, stock_no)`(只留當日)+ `GET /api/capital/fills`,前端每筆一標記;
  近似版已知失真:分批成交壓成一點(最新事件時間 × 均價)、尾段事件是刪單時點落在刪單時刻、
  **昨日部分成交今日刪單的單會以(今日刪單分鐘 × 昨日均價)畫上今日圖**(若 `date` 隨事件變日 —— 未實證,見 08-28 pr-134 F-01 ——
  日期界擋不到;cr1 A-3)。`copycat/capital/store.py:65` 的註解「委託建立日」同樣不精確,精確版一併改。 **→ 08-28 拍板做:`/mod` 成交點精確版(含 L435 orders 加 `code`、L444 群組卡個股期委託)。**
- [x] ~~**群組卡個股期委託不標**~~ → 08-31 併精確版出貨(fillsByCode 吃 code)。
## 2026-08-17(mod/ladder-market-buttons batch3 R1 留尾)

- [ ] 真市價 literal `"M"` 給個股期 / 期貨市價鈕(D3b):prod 實測 `"M"` 可送後可從 limit@邊價切回;
  屆時 OrdersList 標籤對這兩梯才會出現(現在 wire 就是限價 IOC,不標)。
  (2026-08-24 註:user 之後找機會下單再驗;現股側 1068 修時一併盤點期貨端 `"M"` 路徑。) **→ 08-28:併個股期安全首單一起驗,不排期。**
## 2026-08-17(mod/group-grid-full-chart R4 留尾)

- [x] ~~**冷 cache 50 overlay 與瀏覽器 6 條連線交互未量**(review B10):盤中實機錄 waterfall,含同期
  balance / group-state 最大延遲。〔2026-08-21 M0:6 檔暖 cache waterfall 已錄(overlay 各 12–19 ms、
  group-state 6 ms、同期 capital/orders 4 ms、positions 19 ms);冷 cache + 50 檔仍未量〕~~
  → 08-28 拍板不做:冷啟動一次性,暖 cache 已量(12–19 ms)。
## 2026-08-16(mod/trading-calendar 留尾)

- [x] ~~**TXO 面的 `backfill_date` 仍是手動 env**~~ → 08-31 出貨:_txo_auto_backfill_date(場活著 live 窗 / 休市段最近日盤開過的交易日)+ EngineRuntime window identity 讓 08:45 開盤切窗也觸發交接(當時警告的「固定日關 rollover 跨到下週一」洞由此解);env 保留手動覆寫恆優先。原文:`_default_source` / `session_rollover` /
  `live/tc4.py:404` 沒接日曆 —— TXO 有夜盤 session 語意,自動填一個固定日會把 rollover
  關掉並跨到下週一(自動化前要先設計「哪一段夜盤算哪一天」)。休市日要看 TXO 仍靠
  `TXO_BACKFILL_DATE=<上一交易日>`。 **→ 08-28:併下條 `/mod` 一支,TXO 日期沿期貨 tab「錨定日」規則自動算。**
- [x] ~~**非開盤日 / 盤前冷啟動,圖表要維持前一交易日資料(2026-08-24 已拍板開做,原 R3b)**~~ → 08-31 出貨:resolve_trade_date_before,stock 08:00 / index 08:30 各沿自家 stage(D3 拍板);breadth streak 06:00 未動(該面本就日別 EOD,無盤前空窗)。原文:
  交易日 00:00–08:30 重啟 → source 日窗 = 今天而今天還沒開盤,空圖到開盤(spec KR-4 / Q3-R8);
  非交易日已由 R3 日曆處理,此案補「交易日盤前」段。要對齊 stock stage1 08:00 / index 08:30 /
  breadth streak 06:00 三個時序。 **→ 08-28 拍板做:`/mod`(與上條同支)。**
## 2026-08-14(fix/index-line-vanish 收尾留尾巴)

- [ ] **heal 每個 variant 新發一個 history 訂閱、無釋放路徑**(review L1-P2-4):壞日子
  單 session 最多累積 ~18 個 IX0001 1K 訂閱(`_unsub` 只管 REALTIME)。TC4 per-session
  history 訂閱上限未實測;SC-5 側車重演時順手觀察連續多窗口訂閱的行為,若有上限,
  觸頂樣態可能又是「靜默回空」。 **→ 08-28:等壞日子(heal 階梯有爬才看得到)。**
- [ ] **SC-5 側車順驗 stub 語意**(review L1-P2-1 / L2-P1-2 Known Risk):驗「凍結
  stub 的 Time 是否恆為訂閱建立時刻」與「盤中建立的新窗口在該窗真無 1K 時是否產生
  in-domain 假分鐘(實際為當下真實指數價的稀疏點)」;若後者實測發生且被嫌,
  升級手段 = fetch 結果單鍵且鍵=當下分鐘時標記可疑(不動階梯,只加 log)。 **→ 08-28:等壞日子,與上條同窗口。**

## 2026-08-13(mod/trial-pause-badge 第一段收尾留尾巴)

- [x] ~~**緩撮標示第二段:TradeStatus-based per-code 盤中偵測**~~ → 08-31 出貨:_trial_now 第二段吃 TradeStatus==1(盤中 09:00–13:30 採信)、處置股經 breadth 名單標「(處置)」、tc4-market-facts 已回填。原文:(本輪只出時間窗版,
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
  ≈ 2 min,恢復 tick 即集合撮合成交**;(b) per-code `trial` 可直接吃 TradeStatus==1。 **→ 08-28 拍板做:獨立 `/mod`,per-code 吃 TradeStatus==1、文案統一「(緩)」;處置股(分盤撮合 TradeStatus 每 N 分鐘 1→0→1)用 breadth 引擎既有 FinMind 名單改標「(處置)」;先回填 tc4-market-facts。**
## 2026-08-13(fix/index-chart-empty-minutes 收尾留尾巴)

- [ ] **BalanceCollector 殘餘交錯:新輪已收 rows 時舊輪遲到 `##` 會 flush 截斷 / 跨輪混合快照並關閉本輪**(2026-08-21 R7 review F7;2026-08-22 review P1 補:舊輪 rows 與新輪 rows 落同一 staging 時會復活已出清的幽靈部位):COM 無查詢識別不可根治;
  機率 = 兩回應交錯於 ms 級窗。若 prod 觀察到「部位少一檔 / 多一檔 60s 後自癒」即此樣態;候選 = 查詢後 N ms 內的 `##` 才視為本輪。 **→ 08-28:併 `/bug 部位快照不得倒退`,時間窗緩解(查詢後 N ms 內的 `##` 才算本輪)。**
- [ ] **heal 帶 minutes 的廣播對飽和 client 是 at-most-once**(review T-4/C-2,known-risk):
  per-client queue(`ws.py::CLIENT_QUEUE_MAX`,2026-08-24 現為 500;原記 32 已過時)飽和期間
  `QueueFull: pass` 靜默丟掉 heal 那一則 → 該分頁線仍空且無二次機會(引擎
  state 與 log 都顯示已自癒)。觸發窗極窄;系統性解法(per-client 補送 / 低頻週期全量)
  會動 scalar-only 頻寬慣例,獨立輪評估。
## 2026-08-06(stkfut-contracts 題3 收尾留尾巴)

- [ ] **個股期功能待 user 過目**(PR #28 試用指引):合約下拉/分時五檔切換/個股期梯截圖
  四張在 `.claude/feat/stkfut-contracts/evidence/`;**真送單驗證 = prod 安全首單**
  (遠價 1 口 → 群益 APP 核對 → 刪單,§7);首個交易日順看 08:45–09:00 期貨分時有資料
  (夜盤訂閱窗假設的 prod 觀察項)。 **→ user 08-28:個股期之後再測,不排期。**
## 2026-08-06(group-grid 題5 收尾留尾巴)

- [ ] **apply_backfill reset+replay 競態範圍隨 guard 去 main 化擴大**(review B3-f;2026-08-24 起由
  Claude 盯:下次盤中以 group-state 連續抓取對照分鐘完整性,user 不用主動看):SubHistory 與套用之間
  到達的 live tick 被洗掉,現及於全部自選成員(每檔每日一次 + 60s 輪詢自癒)。 **→ 08-28:08-31 對帳。**
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

- [ ] backfill_finmind/backfill_daytrade 空日不進 marker 後,真假日在重跑同 range 時會反覆重抓(range 約 11 個月含 100+ 週末假日);若 FinMind 配額吃緊,疊加靜態台股假日曆只重試「非假日空回應」 **→ user 08-28:回測資料管線,排除不討論。**

## 2026-07-28(capital-order Phase 3 順手清單)

- [ ] TXO 市價單確認框金額 = **估算**,冷門履約價可能是舊價:`snapshot.contracts[].last_price` 是該合約當日**時序最後一筆成交價**、無時效標記(2026-08-05 /mod txo-contract-last-price 拍板 out of scope)。深價外履約價可能整個上午沒成交 → 確認框「預估權利金」與安全閘 `safety._check_qty_amount` 的名目金額都吃到數小時前的價。**送單本身不受影響**(市價走 literal M,`capital/mapping.py:161`,價格不是我方帶的);要收斂的話候選 = last_price 帶成交時刻 + 前端超過 N 分鐘標示為舊價 **→ user 08-28:目前不下選擇權,先放著。**
