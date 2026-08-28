## 2026-08-28(mod/index-heal-holiday-gate 加權自癒休市日補窗內閘 留尾)

- [ ] **日曆誤標交易日為休市的可觀測性只靠畫面**:補窗內閘後,`configs/trading_holidays.json` 若把真交易日標成休市,那天 IX0001 分時自癒
  整天不跑(盤外段本來就不跑)—— 症狀 = 全站休市膠囊 + 圖是前一日的,錯得看得見,但 log 零訊號。候選:server 起動時若
  `is_trading_day(today)` 為 False 而 TC4 09:00 後仍有 IX0001 推播 → 印一行 WARNING「日曆說休市但有推播」。
- [ ] **rollover 設 pending 的 cancel 只擋 `_retry_task` 一支**:heal 與連線 retry 同走 `_schedule_retry` single-flight,現況只有一支;
  日後若分家(各自 task)要一起 cancel。測試 `test_rollover_pending_cancels_the_inflight_retry` 用 dummy task 釘機制,沒釘「舊日分鐘沒疊進新日」
  的結果面(需要可控的慢 fetch hook,`FakeIndexSource` 尚無)。

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
  C / D 實測不變 vs tc4-market-facts「最新事件日」機制推論,repo 內零跨日樣本)。

## 2026-08-28(chore/test-hygiene-batch 測試衛生三條 留尾)

- [ ] **`test_balance.py` 六處 `RAW_*.replace(",1000,0,,", …)` 字串猜欄位變異**(:105 / :117 / :128 / :140 / :155 / :161):
  `profit_rows.py` 已立「變異一律走 `pnl_variant`(按欄索引),不 `.replace` 猜字串」,庫存列 `balance_rows.py` 沒有對應的
  `balance_variant`;`.replace` 靠子字串唯一性,欄形一改就靜默改錯欄。本輪純搬移不動斷言(scope),候選 = 加 `balance_variant(row, {idx: v})`
  六處改按欄索引。
- [ ] **`/ws/index` 首則可能是 ping 或任一 dirty 拍,前端 `useIndexStream` 是否假設首則含完整 payload**(本輪 B 校正前提時順帶看到,未查):
  relay docstring 寫「無 seed 的路(index/capital/futures)首則可能是 ping」;前端 helper 已濾 ping,但首則 `twse.p` None 的 payload
  會不會讓現價欄閃一下 `—`,要看 `index-accum` 的合併語意。待查,不是本輪 finding。

## 2026-08-28(/pr-review #131 回溯 review 留尾)

- [x] ~~**`tests/server/test_bars.py` 5 條在台北 00:00–00:10 會紅**(pr-131 review 順帶發現;reviewer 00:04 實跑 `5 failed`,
  `bars._now_time` 固定 09:00 重跑 51 passed):`copycat/server/bars.py:510` `hold = hi == yesterday and _now_time() < MIDNIGHT_BUFFER_END`
  午夜緩衝窗吃真牆鐘;該檔部分測試已 `monkeypatch.setattr(bars_mod, "_now_time", …)`(:594),這 5 條沒凍結。處置 = 5 條補同一把
  monkeypatch(或 autouse fixture 凍到 09:00,要驗緩衝窗的測試自己覆寫)。與任何 PR 無關,純測試牆鐘相依。~~
  → 08-28 chore/test-hygiene-batch:模組級 autouse `_daytime_clock` 凍 09:00 + `TestModuleClock` 兩條哨兵(fixture 缺席恆紅 / `build_minute` 真路徑永久化 yesterday);00:05 plugin 重跑 53 passed。
- [ ] **pr-131 F-04 commit 慣例**(no-op,已 merge 不重寫):純註解 / JSDoc 位移一律 `chore(<scope>)` 不用無 scope 的 `refactor:`;
  測試重組內含新增斷言時另拆 `test` commit。

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


- [ ] **`src/App.test.tsx`「capital WS 唯一掛載」負載型 flake**(08-27 晚 fix/breakeven-review-followups 三次全量 vitest 與
  全量 pytest **並跑**時 3/3 紅、單獨跑 3/3 綠 2848 passed):該測試 `waitFor` 預設 1 s 等兩個 lazy 頁面掛載,並行負載下 1.8 s。
  不是本輪 diff(純函式)造成。候選 = 該測試 `waitFor(..., { timeout: 3000 })`,或 ops 紀律「全量 vitest 不與全量 pytest 同時跑」。
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
  候選 = 交易日曆 JSON 加「無夜盤日」欄,兩處同吃。要先查期交所公告落成事實(tc4-market-facts)。
- [ ] **SC-13 (b)–(e) 真環境窗口**(mod/futures-day-1500):15:01 翻頁那一刻(左緣換成今 15:00)、次一交易日 08:46 的
  05:00→08:45 水平橋 + 跳價、CDP 五線在 15:00 換組後 user 對 APP、個股頁「台指期」線夜盤時段仍在(解耦後應與改前相同)。
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
  更長門檻(如 1800 s)而非整條豁免,要先量 SXF 日盤最長真靜默(今天觀察到 22 分鐘)。
- [ ] **個股冷門檔同型(6949 每分鐘一發 attempt 1)**:個股 source 的 R2 60 s 對零股 / 冷門檔同樣是假警報,但個股是
  自選動態集合,沒有設定檔可標 —— 走 08-26 節「從未推播 / 冷門檔退避上限 60→300 s」那條,不套 sparse。
- [ ] **收盤段 `IX0001` 每 30 s 一發 —— 已出貨待次一交易日真環境驗**:08-27 user 拍板 13:25(mod/stock-heal-gate-end-1325),
  pr-126 F-01 收修為 per-consumer(mod/heal-gate-per-consumer):**只有 index session** 吃 `in_index_heal_window_now` 13:25,
  個股 / corr 台積電腿留 `in_trading_hours_now` 13:35(試撮期個股仍有簿更新推播,一起關是零收益純代價)。看門狗 13:25 下班、
  訂閱不退、13:30 收盤推播照收。驗法:`grep 零推播自癒 logs/server-<次日>.log | grep IX0001` 13:25 後 0 筆 + 13:36
  `curl /api/index/state` 記 twse 最後更新時戳(同時反證 F-03「誤判 vs 真死」);**驗過再勾**(pr-126 F-08)。
- [ ] **重掛 snapshot 會清 heal attempts → 退避 / 換窗階梯可能永不升級**(08-27 盤後發現,未證):TC4 對 SUBQUOTE 回
  snapshot(tc4-market-facts fresh subscribe 事實)→ `tc4._note_push` 清 `_heal_attempts` / `_heal_next` → 下一輪又從
  attempt 1、base 門檻起算;IX0001 收盤段 19 發 30 s 等距 attempt 全 1、SXF 兩發剛好 240 s 都是這形狀。若 symbol 真死
  但 SUB 仍回 stub snapshot,`HEAL_VARIANT_AFTER` 永遠到不了 = 08-14 凍結 stub 那類病 REALTIME 側沒有逃逸路。要證得先
  加一行 DEBUG 記「snapshot 到達 vs 上次重掛時距」;候選 = 重掛後第一則推播若在 N 秒內且無新成交時戳,不清 attempts。
- [ ] **`in_trading_hours_now` / `_TRADING_END` 名不符實**(review Standards P2;per-consumer review F-S2 重申):pr-126 F-01
  後 `_TRADING_END` 回 13:35,13:25–13:30 那半段名實相符了,但 **13:30–13:35 已收盤函式仍回 True** —— 它實質是「個股自癒 /
  健檢閘窗(上界 13:35 是啟發式)」;`corr_source.py:61` / `app.py:416` 讀者只看得到名字,正是 #126 誤共用的同一條失效路。
  index 那把已具名 `in_index_heal_window_now`。獨立 🔵 更名 `in_stock_heal_window_now` / `_STOCK_HEAL_END`,六個讀者一起改。
- [ ] **index 閘 13:25 的代價**(review Spec P2-2/3/4;pr-126 F-01 per-consumer 後**只剩指數側**,user 知情):訂閱在
  13:25–13:30 死掉時 (a) 加權分時由 index_engine 尾段回補得回(有日曆且為交易日 → 13:25 起到午夜;無日曆退回 `_HEAL_TAIL_END` 13:40,
  pr-126 F-05);現價欄不靠回補(`_merge_backfill` 只寫 minutes),但同一發自癒會連帶重掛 IX0001
  (`_subscribe_and_backfill`),重掛的 SUBQUOTE snapshot 即一則推播 → 現價欄**應會**跟著回來(pr-128 F-01,未實測;
  08-28 13:36 `/api/index/state` 現價欄 vs 時戳核);(b) 13:25–13:35 新加的**指數**訂閱不武裝健檢。
  個股側不再受影響(閘留 13:35)。pr-126 F-02 / pr-128 F-04 校正一併記下:個股當日重補入列點有五個,**在試撮期訂閱死掉
  這個情境下**會出手的只剩 `set_main_contract`(手動切主圖)與 `_handle_reconnect`(斷線重連);「漲跌停值變」
  (`stock_engine.py` 收件人含 `_backfilled`,只在 upper / lower 真的變動時)與逾時重排該情境下不觸發,群組成員
  60 s 輪詢被 `_backfilled` 擋住;08-27 前那句「個股沒有當日重補」錯。
  兩條都是「13:30 回來一小段」第二段閘的價值,綁下一條的量測 —— 現價欄若真的回來,第二段閘的價值只剩 (b)。
- [ ] **IX0001 收盤最後一筆推播幾點到**:index 閘已改 13:25,這個事實現在只決定「要不要加 13:30 回來一小段的第二段閘」
  (user 08-27 提的設計):13:30:0x 即到 → 值得加(多保護試撮 5 分鐘內訂閱死掉的窗);13:33 才到(個股 1K 有 13:33 的
  row,`tests/live/test_stock_source.py:469`)→ 加了也是誤判,維持現狀。量法 = 交易日 13:36 `curl /api/index/state`
  看 twse 最後更新時戳 / minutes 最大鍵,或 13:20 起只聽不訂 probe(`ix_listen_probe.py` 樣板)。
- [ ] **`heal_*` 六個參數 Data Clump**(review Standards):`TC4QuoteSource` 六個 heal 參數被 `CorrQuoteSource` 逐字轉發,
  本輪加一個旗標動了 tc4 簽名 + body、corr_source 簽名 + 轉發、app 兩處、四支測試。候選 = `HealPolicy` frozen dataclass
  收攏,四個 source 子類一起改,獨立 🔵。

## 2026-08-27(fix/breakeven-avg-source-prod-chain #118 broker 半邊在 prod 是死的 留尾)

- [ ] **流程教訓:blast radius 要 grep「欄位寫入點」不只「建構點」**:#118 的 blast radius 只 grep `Position(` 建構點與
  `avg_source` 字面,沒 grep `avg_price =` 就地寫入 → 真鏈 `client._on_profit_complete` 漏掉,測試綠在一條零 caller 的
  死路徑上。判準:新增欄位時 `grep "<鄰欄>\s*="` 把每個就地寫入點列出來逐一對。待併入 `ops-discipline`(該檔另一 session
  持有未提交修改,先記這裡)。
- [ ] **期貨列 `avg_source` 恆 null(語意缺口,非本輪 bug)**(two-axis Spec (c)):`balance.py::parse_open_interest_line` 給期貨列
  `avg_price=` 群益 OI [6] 平均成本、從不寫 `avg_source`;`merge_fut_positions` / `_stale_fut_positions` 沿用同物件。
  **不會**多加一次買費 —— 期貨列不進 `positionEcon`(`position-summary.ts:116/177` 分開走、`PriceLadder` 是現股梯),
  reviewer 說的後果不成立;真正的缺口是「群益 OI 平均成本含不含手續費」無實證,期貨梯的打平線若日後要吃它得先量。
  與 08-26 節「空方均價語意無真樣本」同一類,等首筆期貨真成交順看。
- [ ] **F-05 `fill_date` 跨日重播復發**(pr-118-review Should):`today_qty` 看成交到達日,群益 ConnectByID 重播含前一日時
  (跨日未重啟)昨天的成交會被算進當沖段 —— 與 08-26 節「`today_qty` 依賴聚合只有當日 backlog」同一條,那條已列。
- [ ] **pr-review #116 / #117 / #118 三份報告仍在 repo root 未 commit**(`pr-11N-review{,.audit}.md`);上一輪 #111 是搬進
  `docs/superpowers/specs/` 一起 commit,可比照(單獨 chore)。#117 六條 LOW / #118 十一條 Nice 未動。

## 2026-08-26(fix/breakeven-avg-source-daytrade-tax 打平線均價語意 + 當沖稅 留尾)

- [ ] **空方(融券 / 無券 daytrade_sell)均價語意無真樣本**:群益損益試算的空方「均價」是純賣價、還是扣掉賣費稅後的淨收?
  `positionEcon` 空方分支沿舊式當純價;無券當沖(先賣後買)照法規也是現股當沖 0.15%,但 `today_qty` 減半目前**只套 kind === "cash"**,
  `daytrade_sell` 未套 —— 等 08-27 user 無券當沖實錄(balance.py 負股數整列)一併校準兩件事。
- [ ] **樂觀加碼時 broker 均價(含費)與純成交價加權**:`_apply_fill_locked` 同向加碼沿用舊來源,新增那幾張少算一次買費
  (0.026%),鏈落地 1–2 s 即消;要精確得讓後端知道折數(= 被否決的修法 B)或前端拆兩段。撞到再說。
- [ ] **`today_qty` 依賴「聚合只有當日 backlog」**:群益 ConnectByID 只重播當日;若哪天重播含前一日(跨日未重啟、
  或 API 行為變),today_qty 會把昨天的張數算進當沖段。判準 = `_Agg.date` 非今日仍被計入;可加 WARNING 蒐證。
- [ ] **群益 APP 損益試算不做當沖減半**(08-26 反推 4991 pnl_base 用 0.3%):今天的部位我們會比 APP 多顯示減半的稅,刻意;
  若 user 日後要「與 APP 一模一樣」模式,加 toggle 把 `SELL_TAX_DAYTRADE` 關成 0.3% 即可。

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
  已由 fix/corr-sparse-leg-heal-exempt 以 `sparse` 旗標豁免 R2。** 6949 冷門檔 172 發(每分鐘 attempt 1)仍是本條。
- [ ] **`corr_source.taifex_leg_gate` 對 SGX / CME / CBOT / OSE 段恆 True**(§5.6):要收得先用 `QUERYINSTRUMENTINFO` 的
  `OpenCloseTime` 把各段時段落成事實(skill 只有 OSE 一組)。
- [ ] **`tests/live/test_river_state.py` UTF-8 BOM(N059)**(§5.6)未處理。
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
- [ ] **「不 Disconnect 則 process 不退」錯句**:`tc4.py` 兩處已改;`futures_engine.py:221/245/258` 三處本輪一併改。

## 2026-08-26(mod/watchlist-rename-collision A4 改名保留編輯框 留尾)

- [ ] **「新增群組」輸入框仍在 commit 前 eager 清空**(`WatchlistManagerDialog.tsx::submitAddGroup`):佇列視窗內撞名時
  文案出來、字已清(#101 verification §5.3 舊留尾;A4 只收改名)。改成留著要另設守門(清空同時是它的重送防護),
  可照 `renameInFlight` + `onSettled` 的形狀做。
- [ ] **`WatchlistManagerDialog.test.tsx` 的 `gatePuts` / `releaseOk` 已是同檔第三份逐字複本**(L365 / L461 / A4 新 describe):
  抽成檔案頂層工廠(`makeGate()` 回 `{ gatePuts, releaseOk, releaseFail }`),要動既有兩個 describe,單獨一個 🔵。
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
  仍走回查鏈;無券的部位狀態與 balance.py 負股數校準同一條(08-20 待實錄)。
- [x] ~~**F5 真成交耗時數字**:三段 log「balance 鏈: … 自成交回報到達起 N ms」已備,下一筆真成交後把數字記回
  `.claude/feat/chart-ux-batch-0826/verification.md`(現在只有 FakeCom 模擬:修前 463 ms、修後推播早於回查鏈)。~~ → 08-26 已記回 verification.md:樂觀 0.0–0.7 ms、鏈落地 624–5538 ms(13 筆)。
- [ ] **F5 成交到達時回查鏈若在途,該輪落地會短暫覆蓋回成交前快照**(與現狀等長的空窗,不擴大);
  若盤中觀察到「部位閃一下回舊值再回來」就是這條,候選 = 鏈落地時對 `_fill_seen_at` 之後到達的成交重新套一次。
- [x] ~~**worktree `frontend/npm ci` 失敗:package-lock.json 與 package.json 不同步**(@emnapi/* 版本);主 tree 是
  `npm install` 裝的。開 worktree 只能 robocopy node_modules;要根治就 `npm install` 更新 lock 一次(獨立 chore)。~~ → 08-26 chore/frontend-lockfile-sync `npm install` 更新 lock(diff = @emnapi/* + wasm32-wasi optional 平台包 bundled 項 + yaml peer 旗標)。
- [ ] **`tests/server/test_ws_disconnect.py::test_close_sent_runtime_error_is_not_logged_as_warning` 全量並行下偶紅**
  (本輪 1 次;單跑 3/3 綠;不在本分支 diff)—— 與 08-26 fix/tc4-logout 留尾的 flake 候選同一條。

## 2026-08-26(mod/shutdown-budget A1 關機預算同源 留尾)

- [ ] **signals 段(`bot.close()` + hub drain)無上限**,只算進 `LIFESPAN_SLACK_SECS`(5 s);
  Discord 端網路壞掉時 `discord.py` 自己的 timeout 才是上界,超過就擠掉 TC4 的預算。候選 =
  `asyncio.wait_for(signals_close, LIFESPAN_SLACK_SECS)`,但要先確認 hub 落檔在 timeout 內完成
  (jsonl 是真相源,不能被 cancel 半途)。
- [ ] **run.ps1 finally 內第二次 Ctrl+C 未驗**:PowerShell 5.1 的 finally 在 `WaitForExit` 阻塞時再按
  Ctrl+C 是否中斷、中斷後 `Stop-Tree` 還跑不跑 —— 跑不到的話 backend 就留著。上限拉到 83 s 之後
  這條路比 15 s 時代更可能被人踩到。盤後用 --verify server 走一次即可驗。
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
- [ ] **期貨 1K 落後 / 中段缺格沒有後端量測**:user 08-25 盤中看到「K 棒沒更新 → 分時不連貫」,後端 log 零筆
  (落後判定在前端 gate 5;後端只記 timeout / 回空,當日 TXF 零筆;17:16 重啟後當日序列完整 → 屬 H1 暫時落後或
  H3 memo 釘住二者之一,事後不可分辨)。候選 = `futures_engine` 每分鐘記「bars 尾 vs 最後成交時戳」差 > N 根的 WARNING
  (固定前綴供 grep),讓 H1/H3 事後可分。
- [x] 處置股 badge(FinMind `TaiwanStockDispositionSecuritiesPeriod` 名單已在 breadth 引擎)—— **user 08-26 拍板不做**,
  視覺自評即可;2455 08-25 的 TradeStatus 每 2 分鐘 1→0→1 共 133 次即處置分盤形狀,留作 N100 蒐證樣本。
- [ ] **flake 候選:`tests/server/test_stock_engine.py::TestStreamAndStatus::test_stream_receives_tick_and_book`**
  (08-26 全套三輪中一輪紅:`tick_msg["seq"]` 拿到 1002 而非 1,像是別的測試灌了 1000 筆 tick 的狀態漏進來;
  單跑 3/3 綠、其餘兩輪全套綠、當輪 diff 只動 tc4 close / capital reply log)。候選 = 找共用 StockState /
  engine 實例的 fixture 或背景 thread 殘留;再紅一次就開 /bug。
- [ ] **現股當沖 / 信用當沖資格顯示**(user 08-26 提問,未拍板):現股當沖 = FinMind `TaiwanStockDayTrading`
  (`BuyAfterSale` Y/＊ = 僅先買後賣;回測 `backfill_daytrade.py` 已用),信用當沖 = `TaiwanStockMarginPurchaseShortSale`
  資券標的;兩者皆 EOD 名單,T 日名單 FinMind 幾點更新未實測;群益 `sDayTrade` 是送單意圖不是資格,SKCOM 有無資格查詢 API 未查。

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
- [ ] **`signal-model.ts::formatToastText` 待刪**:prod 已無讀者(只剩 `useSignalAlerts.test`
  拿它當期望值來源)。現況是**同源同義反覆** —— 實作與斷言同一顆函式,文案改動 mutant 全綠。
  順序不可顛倒:**先**把測試的期望值改成字面量(逐字寫死文案 + 註解寫拆解),lock 生效後
  才刪 `formatToastText`。先刪的話那批斷言只能整條拿掉,等於把文案的守門一起丟了。
- [ ] **N109 的真分態需後端 seed 加欄位**:`status.tc4 === "down"` 的兩個來源(engine 在但
  TC4 斷 / 無 engine 模式)前端沒有可分辨訊號,本輪只能出「對兩態都誠實」的單句。真解 =
  `stock_engine` 的 status seed 加一個「engine 是否存在」欄(`/api/health` 刻意不含引擎
  健康度,不要改那支),前端才分得出「等它自癒」與「去重啟伺服器」。屬後端改動,擇日排。
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
- [ ] **期貨日 K `staleTime: Infinity` 跨日不重抓 → 基準日停在昨天**
  (`hooks/useFuturesBars.ts:61`):疊線資料源與日 K 模式共用同一份 query,`Infinity` 讓它
  「一天只打一次」—— 但 preview 整天掛著(看盤日常,CLAUDE.md §1)跨過午夜後那份 cache
  不會失效,新交易日的圖會拿**前一天的**基準日畫疊線。本輪的錨定日判準只保證「不畫到
  未來 / 當前這一節」,對「停在更早的一天」無感(那正是它刻意的安全側)。候選 = staleTime
  改吃「到下一個交易日切換點」的毫秒數,或 queryKey 帶交易日。**現象輕微但整天掛著必中**。
- [ ] **`o.date` 的夜盤跨午夜組合假設未證**(`lib/fill-marks.ts::alldayFillPoints`):
  群益回報的 `date` 是否為最新事件日**未實證**(08-28 pr-134 F-01:同日 C/D 實測仍原單日期),而近全軸把 `date + time` 組成時戳後丟給 `anchorDateOf`
  —— 這假設了「夜盤 01:00 的成交,`date` 已是次一日曆日」。若群益實際回的是委託所屬交易日
  (即 01:00 成交仍記前一日),`anchorDateOf` 會再退一天 → 該筆成交**靜默不畫**。
  失效在安全側(不畫 < 畫錯分鐘),故本輪不猜。待**真夜盤成交一筆**取證後決定是否改判準。
- [ ] **`EnergySub` 改單一 `<path>`**(N047 量測後的真正收法,verification §N047):
  1140 個 `<rect>` → 1 個 path,節點數降三個量級。**不走「資料版本 memo key」**——
  1K 回補可以在總量不變下改寫某一分鐘的量,以總量當版本會讓副圖靜默停在舊值(用錯誤換效能)。
- [ ] **期貨 POC 標籤印桶心 `23002.5` 而非檔位價 `23000`**:`futuresBarsToAccum` 以近全軸
  自折 VP(不經 `foldVp`),桶心落在兩檔之間。待 user 表態(verification 待驗項 4)後再定
  —— 改印檔位價要先決定「桶跨多檔時算哪一檔」,不是純顯示改動。

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
- [ ] **`CandleChart.test.tsx` 含歷史 NUL 位元組**,git 判整檔 binary(diff / grep 全瞎;
  N026 的 class 鎖因此只能落在新檔 `CandleChart.caption.test.tsx`)。獨立 chore 清掉。

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

- [ ] **GroupGridView 2.5 萬 SVG 節點縮減**(handoff R6 原文):per-card memo 已有,
  節點數縮減屬視覺/結構設計變更(虛擬化或降採樣),另案 /mod。
## 2026-08-20(mod/signals-today-offload 留尾)

- [ ] **loop 預設 executor 同池耦合**(review C-1):to_thread 全走同一 ThreadPoolExecutor
  (daily_bars / capital close / signals-today / hub append),TC4 半死的不可中斷殭屍執行緒
  堆積時全池排隊。若 prod 觀察到 today / daily_bars 變慢,考慮給「純本機檔案 IO」一個
  獨立有界 executor;`_warned_years` check-then-add 跨執行緒(review C-3)屆時一併看。

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
## 2026-08-17(mod/corr-nk225m-leg batch3 R5 留尾)

- [ ] `tests/live/test_river_state.py` 帶 UTF-8 BOM(`ruff format --check` 報;非 gate)—— 順手批去 BOM。
- [ ] next-time:758(跨 UTC 06/22 邊界推播)本輪 20:1x 起跑仍未跨邊界,**未驗**;`spikes/nk225_leg_probe.py`
  可帶 `--listen-secs` 拉長在 13:5x 起跑順帶驗。

## 2026-08-17(mod/positions-pnl-display batch3 R3 留尾)

- [ ] **成交點精確版 / 群組卡個股期委託標記可直接吃 `code`**(R2 留尾的「契約碼→股號反查」已由本輪後端
  `stock_code_of` 提供;`GET /api/capital/positions` 有欄,orders 尚無 —— 精確版加 `code` 到 orders 同款)。
## 2026-08-17(mod/intraday-fill-marks batch3 R2 留尾)

- [ ] **成交點精確版**(D7 拍板近似版的替代):後端 `CapitalStore` 保留逐筆 D 事件
  `(seq_no, time, price, qty, buy_sell, stock_no)`(只留當日)+ `GET /api/capital/fills`,前端每筆一標記;
  近似版已知失真:分批成交壓成一點(最新事件時間 × 均價)、尾段事件是刪單時點落在刪單時刻、
  **昨日部分成交今日刪單的單會以(今日刪單分鐘 × 昨日均價)畫上今日圖**(若 `date` 隨事件變日 —— 未實證,見 08-28 pr-134 F-01 ——
  日期界擋不到;cr1 A-3)。`copycat/capital/store.py:65` 的註解「委託建立日」同樣不精確,精確版一併改。
- [ ] **群組卡個股期委託不標**(契約碼→股號反查留給精確版一起做)。
## 2026-08-17(mod/ladder-market-buttons batch3 R1 留尾)

- [ ] 真市價 literal `"M"` 給個股期 / 期貨市價鈕(D3b):prod 實測 `"M"` 可送後可從 limit@邊價切回;
  屆時 OrdersList 標籤對這兩梯才會出現(現在 wire 就是限價 IOC,不標)。
  (2026-08-24 註:user 之後找機會下單再驗;現股側 1068 修時一併盤點期貨端 `"M"` 路徑。)
## 2026-08-17(mod/group-grid-full-chart R4 留尾)

- [ ] **冷 cache 50 overlay 與瀏覽器 6 條連線交互未量**(review B10):盤中實機錄 waterfall,含同期
  balance / group-state 最大延遲。〔2026-08-21 M0:6 檔暖 cache waterfall 已錄(overlay 各 12–19 ms、
  group-state 6 ms、同期 capital/orders 4 ms、positions 19 ms);冷 cache + 50 檔仍未量〕
## 2026-08-16(mod/trading-calendar 留尾)

- [ ] **TXO 面的 `backfill_date` 仍是手動 env**:`_default_source` / `session_rollover` /
  `live/tc4.py:404` 沒接日曆 —— TXO 有夜盤 session 語意,自動填一個固定日會把 rollover
  關掉並跨到下週一(自動化前要先設計「哪一段夜盤算哪一天」)。休市日要看 TXO 仍靠
  `TXO_BACKFILL_DATE=<上一交易日>`。
- [ ] **非開盤日 / 盤前冷啟動,圖表要維持前一交易日資料(2026-08-24 已拍板開做,原 R3b)**:
  交易日 00:00–08:30 重啟 → source 日窗 = 今天而今天還沒開盤,空圖到開盤(spec KR-4 / Q3-R8);
  非交易日已由 R3 日曆處理,此案補「交易日盤前」段。要對齊 stock stage1 08:00 / index 08:30 /
  breadth streak 06:00 三個時序。
## 2026-08-14(fix/index-line-vanish 收尾留尾巴)

- [ ] **heal 每個 variant 新發一個 history 訂閱、無釋放路徑**(review L1-P2-4):壞日子
  單 session 最多累積 ~18 個 IX0001 1K 訂閱(`_unsub` 只管 REALTIME)。TC4 per-session
  history 訂閱上限未實測;SC-5 側車重演時順手觀察連續多窗口訂閱的行為,若有上限,
  觸頂樣態可能又是「靜默回空」。
- [ ] **SC-5 側車順驗 stub 語意**(review L1-P2-1 / L2-P1-2 Known Risk):驗「凍結
  stub 的 Time 是否恆為訂閱建立時刻」與「盤中建立的新窗口在該窗真無 1K 時是否產生
  in-domain 假分鐘(實際為當下真實指數價的稀疏點)」;若後者實測發生且被嫌,
  升級手段 = fetch 結果單鍵且鍵=當下分鐘時標記可疑(不動階梯,只加 log)。

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
## 2026-08-13(fix/index-chart-empty-minutes 收尾留尾巴)

- [ ] **BalanceCollector 殘餘交錯:新輪已收 rows 時舊輪遲到 `##` 會 flush 截斷 / 跨輪混合快照並關閉本輪**(2026-08-21 R7 review F7;2026-08-22 review P1 補:舊輪 rows 與新輪 rows 落同一 staging 時會復活已出清的幽靈部位):COM 無查詢識別不可根治;
  機率 = 兩回應交錯於 ms 級窗。若 prod 觀察到「部位少一檔 / 多一檔 60s 後自癒」即此樣態;候選 = 查詢後 N ms 內的 `##` 才視為本輪。
- [ ] **heal 帶 minutes 的廣播對飽和 client 是 at-most-once**(review T-4/C-2,known-risk):
  per-client queue(`ws.py::CLIENT_QUEUE_MAX`,2026-08-24 現為 500;原記 32 已過時)飽和期間
  `QueueFull: pass` 靜默丟掉 heal 那一則 → 該分頁線仍空且無二次機會(引擎
  state 與 log 都顯示已自癒)。觸發窗極窄;系統性解法(per-client 補送 / 低頻週期全量)
  會動 scalar-only 頻寬慣例,獨立輪評估。
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
