## 2026-08-14(mod/overview-subtabs 收尾沉澱)

- [ ] **tablist 的 ARIA 半套(台股綜合 + RightRail 同型)**(review A-4):兩處
  `role="tablist"`/`role="tab"` 都沒有 `aria-controls` / panel 的 `role="tabpanel"` +
  `aria-labelledby` / roving tabindex(方向鍵不能切)。IndexPage 新列是照 RightRail
  樣板抄的,非本輪回歸 — 修就兩處一併(樣板級決定),獨立小輪。
- [ ] **RightRail `initialTab()` 與 MarketPane 四處裸 `localStorage.getItem` 無 try/catch**
  (本輪 out-of-scope 既有債,round-2 P0-1 因此限定 (s5) 只能按 key 部分 stub):Safari
  私密視窗下是白屏風險面;修法照四殼/IndexPage `initialSubTab()` 慣例包 try/catch,
  純 🔵 順手批。

## 2026-08-14(mod/index-overlay 收尾沉澱)

- [ ] **`localYmd()` 兩份重複**(useStockOverlay.ts / useIndexOverlay.ts 各一份,包 C
  刻意不動既有檔以免擴散 diff):抽到 `@/lib/format` 或 `@/lib/utils` 單一來源;
  漂掉的失效是兩 hook 的 queryKey 換日時刻不一致,靜默。純 🔵,/refactor 順手批。
- [ ] **個股 CDP 右緣標籤帶疊字修法可借 index 側 rightEdgeLabels**:index-chart-svg 的
  rightEdgeLabels(fixed 錨 + 三段式 + 殘餘丟棄)與個股 edgePriceLabels 擴到 CDP 的
  既有 next-time 項(2026-08-14 fix/index-line-vanish 節)同族,動工時先比對兩份演算法
  可否合一,不要各長一套。
- [ ] **rightEdgeLabels 的 clamp-vs-fixed 隱性前提**(自評 correctness lens 註記):
  (d) 段 clamp 後只對前一顆 movable 查距離、不回查 fixed 昨收;現標籤上限 8 顆不可達,
  未來 index overlay 加種類(如 VWAP 掛牌)時要補回查或補測試。

## 2026-08-14(fix/index-line-vanish 收尾留尾巴)

- [ ] **TC4 凍結 stub 的姊妹 ready-check 未收緊**(review L2-P2-4):`river_backfill.
  collect_1k_minutes:52`、`stock_source.backfill:499`、`tc4._fetch_symbol_ticks` 仍是
  「首頁非空即 break」;空窗毒化訂閱回凍結 stub 時同樣被騙,且 river 的
  `minute_end_from_1k` 只讀 Time 不讀 Date — 凍結 stub 會變成今日分鐘寫進 RiverState
  (江波圖憑空一點)。index 側已用「差量進展 + 窗口 variant」繞開;姊妹路徑要收就沿
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

- [ ] **CDP 五個右緣帶標籤自身互疊**(盤中截圖附帶觀察,2330 實證 `2455*`…`2415*` 五個
  擠成一團字疊字):既有擁擠問題、本輪 out of scope 已列。收斂方向 = 把本輪
  `edgePriceLabels` 的 1D 避讓推廣到右緣帶內 CDP 標籤(同一支函式換 bounds),或
  近價合併顯示;動既有 CDP 標籤位置屬行為改動,獨立 /mod 輪。
- [ ] **期貨態 POC(D6 若 user 要)**:需 `foldVp` 分鐘窗參數化(現硬編現貨窗)+
  期貨態 vp toggle 解禁,連動 stock_state 折入層;本輪拍板 POC 僅現貨態。

## 2026-08-13(mod/watchlist-ux-limit-50 收尾留尾巴)

- [ ] **側欄 sticky 遮蔽帶的拖曳落點語意**(review A-3,既有語意的量變):游標在 sticky
  搜尋區上放開時 `dropTargetFromPointer` 取最近 zone(落未分組 index 0)而非作廢;本輪
  全收/全展鈕使 sticky 高一列,遮蔽帶隨之加高。收斂方向 = 把 sticky 高度傳進 `zonesNow`,
  y 落帶內回 null(拖到搜尋列 = 作廢),不動 ROW_H / bounds。
- [ ] **conftest 自選隔離 fixture 的組合跑 flake**:`tests/server/test_signal_routes.py::
  TestConftestWatchlistIsolation::test_hub_data_dir_isolated_without_explicit_path` 在
  特定 8 檔組合同跑時紅(`hub._data_dir == data`,隔離未生效),單跑與全套跑皆綠;
  master 5a1a97aa 可重現,非 watchlist-ux-limit-50 引入。它是 XR-3 SC-8 擋牆自身的鎖,
  壞掉是靜默的(某顆 hub 讀真 `data/stock_watchlist.json`);二段 bisect 未定位到單一
  污染源。候選:fixture 改 autouse session 級斷言、或該測試自帶 delenv/monkeypatch
  不依賴共用 fixture。

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
- [ ] **`stock_engine._quote_payload` docstring「四個產出點」已漂移**:實為 8 處
  (:373 set_watchlist / :457 quotes() Discord 摘要 / :647 retry 重掛種子 /
  :767 _handle_no_data / :919 轉態補推 / 連線 seed / 1s flush / 本輪新增的
  窗翻轉補推;2026-08-13 spec review R5 grep 證實 7 處 + 本輪 +1)。
  下次動該函式時順修 docstring。

## 2026-08-13(mod/ladder-order-status review rejected 候選)

- [ ] **BalanceCollector 無輪次識別:遲到的 `##` 可 flush 空集合全量蓋部位**(review C2/W2,
  rejected — collector 輪次化超出該輪 scope):零事件死查詢 10s 逾期解卡後 `_balance.reset()`
  再發第二次查詢,第一輪遲到的 `##` 會以空 staging flush → `set_positions([])` → 有庫存
  顯示無部位(最壞 60s 自癒)。master 原本無守門時暴露面更大(任一筆重查都可撞),守門
  已收窄到 10s 逾期窗。真解 = 發查詢帶輪次序號給 collector(feed/## 驗 token),或逾期
  解卡改換新 collector 實例;動 `balance.py` 三個 collector 共用節奏,獨立小輪。

## 2026-08-13(fix/index-chart-empty-minutes 收尾留尾巴)

- [ ] **`_collect_history` timeout「靜默回空」語意是家族性風險**:本次事故根源之一
  (`history ... 30.0s 內首頁未備妥,回空` 不 raise → caller 無從排 retry)。index 側已用
  產出面 lag 偵測繞開,但同一語意的其他 caller(river_backfill 六腿、bars_range 各處)
  在「TC4 冷啟動忙碌」窗口同樣拿到空結果且無重試 —— river 六腿 08:23 實錄裡 TXF/TWN/SXF
  三腿同秒 timeout 回空。候選:回傳三態(ok/timeout/empty)或 timeout 專用 exception,
  逐 caller 決定重試;動基底 `TC4QuoteSource` 需盤 blast radius,獨立輪。
- [ ] **盤外時段啟動踩 timeout 無自癒**:分時自癒 gate 在 watch window(09:00–13:25),
  盤後/晚間啟動若 1K 回補 timeout,線缺到次日 09:06 才自癒。實測晚間 TC4 閒時回補快
  (18:17 啟動無 timeout),風險低;若要覆蓋,detector 改「窗外以 min(now, 13:30) 為
  期望覆蓋終點」,但要處理休市日恆空的輪詢噪音。
- [ ] **heal 帶 minutes 的廣播對飽和 client 是 at-most-once**(review T-4/C-2,known-risk):
  per-client queue(32 深)飽和期間 heal 那一則被丟 → 該分頁線仍空且無二次機會(引擎
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
- [ ] **測試 deadline-poll helper 已有 6 份手抄(/refactor 素材)**:`_wait_until`
  (test_stock_engine:931 / test_corr_engine:352 / test_futures_engine:359 /
  test_breadth_engine:234)+ 本輪 `_wait_calls`(test_signal_hub:372)/ `_wait_codes`
  (test_watchlist_service:54);fail-N-then-succeed fake 也有 3 份(_FlakyBars /
  _FlakySource ×2)。sleep 間隔已漂移(0.01 vs 0.005)。收斂到 tests/helpers/。

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

- [ ] **user 過目待做(SC-3/SC-7 雙層之二)**:綜合 tab「類股強弱」(三層清單:產業 →
  子產業 → 成員,著色漲跌% + 量比,點成員跳個股)與「訊號時間軸」(倒序、kind chips、
  market 列「廣度」badge)兩個收合區塊,位於漲跌停列表與相關係數之間。AI 截圖見
  `.claude/feat/market-overview-r4-sector-signals/evidence/`。
- [ ] **prod 8721 重啟後才含 R4**:廣度事件 + 類股面板隨下次啟動生效;首啟順手目視
  `data/market/industry_chain.json` 開始落檔、盤中時間軸出現全市場鎖板事件。
- [ ] **「觸及未鎖」事件不做**(R4 Phase 0 拍板):touched 是當日不可逆 latch,開板已由
  open 事件涵蓋;若日後要,從 breadth rows 的 touched_* 旗標 diff 起。
- [ ] **同頁 stale 標記兩款並存**:SectorSection 沿 BreadthBand 版(bull 色「資料延遲」),
  LimitListSection 是 amber「延遲」— 視覺是否統一待 user 過目時定。
- [ ] **時間軸歷史日回看不做**(R4 out of scope):jsonl 按日分檔,要做時 today 端點
  加 `?date=` 即可。
- [ ] **廣度事件與規則訊號共用 jsonl 佇列(1000,drop-oldest)**(review C-6,量級
  安全暫不動):單輪廣度批次數百 < 1000;若漲停潮日觀察到 `dropped_jsonl` 上升,
  丟棄 warning 先分家族計數,再考慮廣度獨立佇列。
- [ ] **`--verify` 模式無 stock engine → SignalHub 恆 None → 廣度事件層在官方 verify
  上不可達**(Phase 6 實測;design §8 的取證通道假設漏了這層):事件鏈取證用
  `evidence/events_side_server_r4.py`(FakeStockSource 組裝,jsonl 隔離 tmp)。
  若 verify 要原生支援,補 fake stock source 進 verify.py 是獨立決策。
- [ ] **SC-4 盤中同時刻 REST 對照層未做**(窗外降級層已 PASS — 兩實作同快照全等):
  任一交易日盤中 neigui `/api/market/snapshot?refresh=true` 與 copycat
  `/api/market/sector` 同分鐘各落檔比對一次即補齊;純 optional。
- [ ] 類股成員表小型股「成交額」顯示 0.0(億元捨入)— 外觀候選,要改就低於 0.05 億
  顯示千萬/萬單位。

## 2026-08-06(market-overview-r3-limit-list 收尾留尾巴)

- [ ] **user 過目待做(SC-3/4/5 雙層之二)**:綜合 tab「漲跌停」收合區塊(家數帶之下、
  相關係數之上)— 展開後篩選列(上市/上櫃/漲停/跌停/觸及未鎖 + 金額(億)/股價區間)、
  表格九欄(3081 聯亞當日顯示「連 5 板」)、點列跳個股 tab。AI 截圖六張在
  `.claude/feat/market-overview-r3-limit-list/evidence/SC-{3,4,5}_*.png`(盤後真數據)。
- [ ] **SC-5 盤中層待驗**:點列表任一檔跳個股 tab 後五檔開始跳動(需 prod server +
  盤中;截圖層已驗 tab 切換與主圖標的設定)。
- [ ] **prod 8721 重啟後才含 R3**:FinMind poller 活在 server process;下次啟動順手目視
  列表區塊 + `data/market/streaks-<date>.json` 開始落檔(06:00 後武裝)。
- [ ] **側車樣板已升四元組**:`.claude/feat/market-overview-r3-limit-list/evidence/
  breadth_side_server_r3.py`(R2 樣板是三元組,已過時 — 下次盤中驗 FinMind 管線用這份)。
- [ ] 跌停連板數欄(Q4 拍板不做)、列表迷你預覽(D-5)仍在 next-time 池。

## 2026-08-06(market-overview-r2-finmind 收尾留尾巴)

- [ ] **user 過目待做(SC-4 雙層之二)**:綜合 tab 中段家數帶(上市/上櫃 × 漲停/上漲/平盤/
  下跌/跌停,漲停紅底/跌停綠底,戳記「日期 · 時刻」)+ 騰落線(0 軸、末值標籤)。
  AI 截圖三張在 `.claude/feat/market-overview-r2-finmind/evidence/SC-4_*.png`(盤中真數據)。
- [ ] **prod 8721 實測未在跑**(Phase 6 發現):下次啟動 `python -m copycat.server` 即含
  R2(無「等重啟生效」問題);首啟順手目視 —— 家數帶與指數圖並置、`/api/index/state`
  正常、`data/market/breadth-<date>.json` 開始落檔。
- [ ] **SC-1 的「neigui panel 畫面同分鐘截圖」層未做**(panel 未在跑;數字層已以
  neigui 現碼即時對照等價驗過,見 evidence/SC-1_live-parity.txt)。要補就任一交易日
  兩邊同開比對一次;純 optional。
- [ ] **WS /ws/breadth 無 enabled 欄**(review 波一偏離 3):boot 未完成時 WS 送一則
  載入中 scalar 再關,前端靠退避重連自癒;R3 若要前端據 WS 顯示載入中,payload 補欄位。
- [x] ~~R3 前置已備:`BreadthEngine.rows`(compute_breadth 全量 rows)存引擎屬性未曝露,
  接列表時開 REST 曝露面即可。~~ **2026-08-06 R3 已出貨**(`/api/market/breadth/rows` +
  連板數管線 + LimitListSection,見下方 R3 收尾節)。

## 2026-08-06(market-overview-r1-tab Phase 6 real-env 沉澱)

- [ ] **既有 bug:React duplicate key(key=0)每 5 秒刷 console — 根因已定位:
  `MarketChart.tsx:69` y 軸刻度 `key={t.priceMilli}` 在無資料時三刻度全 0**
  (夜盤加權 p=null 即觸發;master 同樣會刷,非 R1 引入 — 但雙 pane + index 恆掛載後
  更常駐可見)。〔同日 intraday-volume-profile 題2 也記到此症狀:隔離實驗證明與 VP
  無關、5s 節奏 = 指數推播 re-render — 兩條同根因,併此一條〕修法一行:key 加索引
  (`` key={`${t.priceMilli}-${i}`} ``)或空資料時不畫刻度。修時補 lock test(空 series
  三刻度 key 唯一)。
- [ ] `MarketPane.tsx` 七個 localStorage 呼叫點裸奔無 try/catch(review SI-2,
  rejected — design 明文「照抄現邏輯」):storage 被政策鎖時預設頁首 render 即白屏,
  且全 frontend 零 ErrorBoundary。要修就把 `CorrSection.tsx:18-34` 那對守衛抽
  `@/lib/storage`(readKey/writeKey)供兩處共用,順帶收斂 App.tsx / useChartToggles
  的同型 try/catch。
- [ ] 舊存檔 `copycat-market-key="OTC"` 的使用者升版首載左右兩張都櫃買(review SI-3,
  rejected — 點一下左圖「加權」即永久自癒):若真嫌,IndexPage 做一次性 seed
  (MARKET2_KEY_STORE 未設時依左值選互補標的),冪等不引入持續耦合。

## 2026-08-06(stkfut-contracts 題3 收尾留尾巴)

- [ ] **個股期功能待 user 過目**(PR #28 試用指引):合約下拉/分時五檔切換/個股期梯截圖
  四張在 `.claude/feat/stkfut-contracts/evidence/`;**真送單驗證 = prod 安全首單**
  (遠價 1 口 → 群益 APP 核對 → 刪單,§7);首個交易日順看 08:45–09:00 期貨分時有資料
  (夜盤訂閱窗假設的 prod 觀察項)。
- [ ] **refresh-stkfut-map 後需重啟 server 才生效**(review A4 已修 mtime cache,但
  CLAUDE.md §1 該指令列尚未註記 — 下次動 CLAUDE.md 時順補)。
- [ ] **_symbol_to_key/_states 隨瀏覽合約單調成長**(review A7c,量級無害僅記錄)。
- [ ] **OrderBook 元件層無合約簿專屬斷言**(review B8;hook 層已鎖,截圖層已過 —
  若日後改 OrderBook 資料源,補一條)。
- [ ] **catalog 冷查詢持 api.lock 秒級**(review A3 已以開機預熱緩解;若 prod 觀察到
  盤中首開下拉造成 TC4 斷線,升級為獨立 session)。

## 2026-08-06(group-grid 題5 收尾留尾巴)

- [ ] **群組檢視待 user 過目**(PR #27 試用指引):個股頁「單檔｜群組」pill、mini 分時圖牆、
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
- [ ] **duplicate-key console error(key=0)嫌疑已鎖定**(題2 輪首記,題1 輪 Phase 6
  隔離定位):以 `priceMilli` 當 React key 的清單在「無資料/全 0」態全撞 key 0 —
  `MarketChart.tsx:69`、`PriceLadder.tsx:535`、`StockIntradayChart.tsx:230`、
  `FuturesLadder.tsx:298`(行號為 2026-08-06 快照)。每 5 秒節奏 = 行情輪詢重繪。
  修法候選:key 加 prefix 或空態不 render 列表。
- [ ] **關閉規則的歷史列視覺弱化**(design R14a 記帳):filterKinds 移除後關閉規則當日
  已發的列仍顯示(帶規則名可辨識);若 user 覺得干擾,補 per-rule 淡化或「只看啟用」勾選。

## 2026-08-05(intraday-volume-profile 題2 收尾留尾巴)

- [ ] **VP 畫面待 user 過目**(PR #22 試用指引):個股頁分時圖左緣水平量條 +「量分佈」toggle。
  AI 截圖三張已入 `.claude/feat/intraday-volume-profile/evidence/`。
- [ ] **外內盤分色 VP 未做**(quintet 拍板選配):`VpCell` 已帶 o/i 資料,渲染層與 toggle 未接線;
  做之前留意鎖停日 side 判定品質(LOW_DECIDED_PCT 議題)。
- [x] ~~既有 console error:React duplicate key(key=0)每 5 秒一則 — 找到那個 map 的
  key 來源修掉~~ **根因已由 market-overview-r1-tab Phase 6 定位,併入 2026-08-06 節首條**

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
- [ ] 後端 commit `8f7d44b` 的 message 漏了 ` [green]` TDD tag(implementer 筆誤;
  check_feat_tags 為 warning 模式,未 amend 保 sha 穩定)。

## 2026-08-05(ladder-position-pnl 收尾留尾巴)

- [ ] **真持倉部位條畫面待 user 盤中過目**:本輪 SC-1/SC-4 的畫面驗證以 fake positions
  (fetch override)截圖降級完成,真持倉態需群益登入 + 實際持倉才看得到 — 盤中開個股頁
  閃電 tab,持倉標的底部應出現部位條(kind + 量 + 均價 / 未實現 / 打平)與梯內
  amber(打平)/ 紫(均價)左緣標記。
- [ ] **口徑已知簡化(皆 user 拍板,回頭看會問)**:不套低消 NT$20(聚合無筆數)/
  不計融資利息 / 證交稅固定 0.3% 不分當沖(當沖 0.15% 情境打平價偏保守)/
  融券借券費 0.08% 已計(kind=short 賣段)。折數預設 1.8(user 2026-08-05 實答,
  取代舊「6 折」記載);localStorage key `copycat-fee-discount`。

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

- [ ] **SC-7 真實環境驗證待補**(群益夜間登入 fail,memory 記「待白天觀察」):下次自然
  重啟後打 `GET /api/capital/positions` 確認形狀正常、面板部位列顯示與現況一致(單一
  種類帳戶下畫面應無差異,sec 列多一個 現/資/券 小字標籤)。同檔資+集保並存是低頻
  狀態,真要驗兩列並存需等實際持倉出現
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

- [x] ~~🔴 **既有 bug:有 WS client 連著時 server graceful shutdown 卡死**~~
  **2026-08-04 chore/ws-test-consolidation 關閉**:根因(send-only 迴圈不 receive)已由
  relay 修掉(同日稍早查證確認,7 條 route 全走 ws.py relay);本輪補上缺的證據兩件 —
  (a) 真環境重現確認:真 uvicorn + 真 socket 保持連線下 `should_exit` → **0.28s 關機
  乾淨**(`TestGracefulShutdownWithLiveClient`),負向對照(monkeypatch relay 回
  send-only)同測試紅、server 8s 關不掉;(b) 整合回歸
  `test_shutdown_completes_while_client_stays_connected` 已入
  `tests/server/test_ws_disconnect.py`。prod 級(真 TC4)關機驗證依「夜盤不重啟」
  紀律待下次自然重啟窗口,回歸測試已足以守住此 bug 形狀。
- [x] ~~驗證 harness(fake server 腳本)應比照 `tests/conftest.py` 中和 CAPITAL_* /
  DISCORD_*:本輪 harness 首啟以真憑證打了一次群益登入(失敗降級零狀態改變,但
  不該發生)。寫任何「起真 app 的驗證腳本」前先 `CAPITAL_USER_ID=""` 這類壓制。~~
  **2026-08-04 chore/server-launch-wrapper 完成**:`python -m copycat.server --verify`
  = fake TXO source + 其餘引擎不啟動 + `copycat/server/verify.py
  neutralize_external_env()`(13 key 設空字串壓制 env 與 .env + 兩模組 `_dotenv_values`
  patch + notify webhook cache 釘死三層),port 預設 8722 錯開 prod(顯式設 8721 會
  拒啟)。之後驗 HTTP 層一律用它,不再手寫 fake server 腳本。
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

- [ ] evaluate_cells_from_universe 頂層 round gate 分岔:再加一輪會變 if-elif chain,屆時抽 evaluator factory
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

- [ ] 觀測性:前端 WS 無 heartbeat 判停(server 靜默時段分不出斷線 vs 無變更;考慮 server 週期 keepalive frame + client stale timer,週一盤中觀察真實需求再定)
- [ ] engine._run_handover 重試時 re-subscribe 與 activate 的 unsubscribe 不對稱,若改主動觸發自癒要先收斂這段

## 2026-07-19(dq4-order-phase1 Phase 4 自評 P2 彙總,15 條聚類,shortSymbol/BLOCKED_REASON 已本輪吸收)

- [x] ~~錯誤碼三層對照(backend _TRADE_ERROR_MAP / frontend TRADE_ERROR_TEXT / 測試字面值)無單一 source:若錯誤碼家族再擴,考慮 codegen 或 shared JSON。〔2026-07-31 盤點:「家族再擴」的條件已達成 —— `capital_api.py:345` 長出第二個 `_CAPITAL_ERROR_MAP`〕~~ **2026-08-04 查證後關閉(不做)**:`capital_api.py` 全檔僅 290 行,`_CAPITAL_ERROR_MAP` 全 repo 只有定義 `:260`(3 entries)+ 消費 `:275` 各一處 —— 07-31「:345 第二個 map」是重構前的陳舊記載,升級條件不成立。且 `_TRADE_ERROR_MAP` 8 碼將隨舊 trade 路刪除消失(AUDIT_WRITE_FAILED / BROKER_REJECTED / INVALID_ORDER 三碼留存 — 前二為 app.py 獨立 handler,後者為 capital_api route 邊界;2026-08-04 增量 review F1 校正),剩餘重複量(3 個 capital 碼 + trade-text.ts 文字表)不值得 codegen;前端未知碼原樣顯示(trade-text.ts:24)= 安全漂移。
- [ ] trade 效能微優化候選(手動單低頻,全部先不動;若未來策略自動下單高頻化再 /perf):orders_view 每 poll 重建 list、account_view 每呼叫 sorted、orderable_symbols 每呼叫重建 set
- [ ] parse_execution_report 的 err_code 判定含 0/"0" 白名單,真值域(design §8 #3)整合實測後回頭校正

## 2026-07-21(stock-terminal Phase 4 自評 P2 彙總,13 條聚類)

- [ ] 個股 stream 韌性候選:hook pending 重放只驗 seq>S 不驗連續性(回補期 WS 掉訊成永久缺筆);fromSnapshot 以 vwap×cum_vol 還原 VWAP 分子與後端 Σq 分母有近似差;apply_backfill 對回補列不去重(TC4 重送列會雙算);tc4_status 只靠 on_reconnect 復位(純 REQ 失敗 banner 永久誤掛)
- [ ] 個股 UI 盤後體驗:reset() 保留 book 與 design 字面不符(rollover 後非觸發檔殘留昨日五檔)。〔2026-07-31 盤點:**後半「盤後重載側欄顯示 `-`」已做掉**,可刪 —— `stock_engine` 連線種子逐檔送 `_quote_payload`,`ref` 欄在尚無成交時給參考價,`WatchlistSidebar` 已渲染「參考」態〕
- [ ] 個股效能/清潔候選:snapshot 每次全量序列化 20k tick deque(切檔/跳號 refetch 都全量 JSON);_states 永不清除;F:xxx 建立永不使用的 StockDayState;backfill TICKS 訂閱事後不退訂
- [ ] 個股雜項:健檢 in_trading_hours 在 subscribe 時判定而非 timer 觸發時;backfill 首頁 30s 逾時靜默回空無 log;watchlist 啟動時 TC4 離線可被 50 檔 × 10s(≈500s)拖慢 lifespan〔2026-08-13 上限 30→50 同步;**退出準則**:若實測 TC4 離線啟動致 index/breadth 就緒 >10 分鐘 → 做 per-code timeout 縮短 / 並行訂閱〕

## 2026-07-20(backfill 雙修 review P2)

- [ ] backfill_finmind/backfill_daytrade 空日不進 marker 後,真假日在重跑同 range 時會反覆重抓(range 約 11 個月含 100+ 週末假日);若 FinMind 配額吃緊,疊加靜態台股假日曆只重試「非假日空回應」

## 2026-07-28(stock-ui-upgrade Phase 4 review P2 彙總)

- [x] ~~frontend localStorage key 無統一前綴(copycat-tab / stock-main-code / copycat-chart-toggles / stock-ladder-open / stock-wl-group)— 下次新增 key 時考慮收斂 `copycat-` 前綴 + lib/constants.ts 集中~~ **2026-08-04 refactor/frontend-localstorage-keys 完成**:15 個 key 全集中 `lib/constants.ts`(值不變);`stock-main-code` 改名 `copycat-stock-main-code` 含一次性讀舊寫新 migration;孤兒鍵啟動清除。之後新增 storage key 一律進 constants.ts。
- [ ] PriceLadder 全域 rows(最壞 ~200 列)無上限 lock 測試;若低價股(tick 10 毫元、±10% = 2000 列)出現效能問題再虛擬化
- [x] ~~stock-ui-upgrade real-env 真截圖待補(TC4 離線 infra_fail)~~ **2026-07-31 盤點:已補畢** — `.claude/feat/stock-ui-upgrade/real-env-verification-round-2.json` 記「2026-07-28 10:00-10:05 盤中(大跌日,5483 -6.6%),達錢 4 開啟後補驗(round 1 infra_fail 解除)」,`evidence/` 下 5 張截圖齊備(SC-1 hover / SC-2,3,5,6 stock-page-live / SC-4 cdp-ma-overlay / SC-6 group-tab / SC-7 ladder)

## 2026-07-28(capital-order Phase 3 順手清單)

- [x] ~~舊 TC4 trade 路刪除(server/trade.py、live/tc4_trade.py、fake_trade.py、frontend useTrade.ts/OrdersList.tsx/OrderConfirm.tsx + 測試;/api/trade/* 恆 503)~~ **2026-08-04 /mod remove-tc4-trade-path 完成**:11 檔全刪、`/api/trade/*` → 404(四路 404 + 對照錨迴歸鎖)、AuditWriteError handler 改獨立註冊(+ 探針測試)。同日稍早另一 session 的查證註記所列必留物(trade_models / 兩 handler / corr 第二處 sentinel)全數命中並保留,見 `.claude/mod/remove-tc4-trade-path/`(change-spec + 兩輪 review JSON + verification)
- [x] ~~TXO snapshot 補推 per-contract last_price(OrderPanel 市價估價目前缺值全鎖,限價不受影響;ContractRow.last_price 前端欄位已預留)~~ **2026-08-05 修畢(mod/txo-contract-last-price)**:aggregator 過 stale-drop 後逐 tick 記 `> 0` 成交價(0 價不收 — §8「0 不是價格」同款防禦)、`_contract_rows` additive 加欄(點,float);golden regen + ticks.jsonl 獨立斷言(QryIndex 單鍵 + shuffle 異構化)。零成交合約不出現在 contracts → 市價仍鎖 = 預期行為;reset 窗 UX 記 2026-08-05 節 Known Risk 條目
- [x] ~~app.py futures source 啟動旗標借用 trade_source is DEFAULT_TRADE(sentinel 語意耦合已註解;__main__ 顯式傳 DEFAULT_FUTURES 後可解耦)~~ **2026-08-04 同輪解耦**:`__main__` 顯式傳 DEFAULT_FUTURES + DEFAULT_CORR(corr 同款借用一併解),`trade_source` 參數與 DEFAULT_TRADE sentinel 刪除;`tests/server/test_main_wiring.py` 上鎖(kwargs 整份相等)
- [ ] 期貨平倉「範圍市價 P + IOC」候選:prod 實測 bstrPrice="P"/"M" 可送性後,可從限價貼漲跌停切回(docs/research/2026-07-28-skcom-typelib.md)
- [ ] TXO 市價單確認框金額 = **估算**,冷門履約價可能是舊價:`snapshot.contracts[].last_price` 是該合約當日**時序最後一筆成交價**、無時效標記(2026-08-05 /mod txo-contract-last-price 拍板 out of scope)。深價外履約價可能整個上午沒成交 → 確認框「預估權利金」與安全閘 `safety._check_qty_amount` 的名目金額都吃到數小時前的價。**送單本身不受影響**(市價走 literal M,`capital/mapping.py:161`,價格不是我方帶的);要收斂的話候選 = last_price 帶成交時刻 + 前端超過 N 分鐘標示為舊價
- [ ] 選擇權閃電梯(本輪 out of scope,TXO 表單已群益化)
- [ ] 群益回報自動重連(本輪拍板不做;做之前 store 聚合非冪等 → 必先 clear 再重播 backlog)
- [ ] OnAccount / OnOpenInterest 欄序為 prod 未實測假定(com.py `_parse_account_row`、balance.py `parse_open_interest_line` docstring 已標)— 首次 prod 登入核對後校正

## 2026-07-28(capital-order Phase 4 code review round 1 追加)

- [ ] COM 卡死 stalled 心跳偵測(review B7):寫入 timeout 連發 / 幫浦圈停擺目前只靠 log,需心跳觀測基建(status 加 last_pump_ts + watchdog 降級);監控面非正確性,本輪 deferred
- [ ] 期貨改價 `CorrectPriceBySeqNo` 末參數 nTradeType=0(ROD)對期權 IOC/FOK 單的影響 prod 首驗(review A6;test 沙盒未開通不可先驗)— 若群益端把改價後 TIF 重設為 ROD,IOC 單改價語意會變
- [x] ~~部位 store `(stock_no, kind)` 鍵位改造(review A4):現況同檔多種類庫存 dedupe 只留張數大者(sec)/同契約淨額合併(fut),被捨棄種類平倉鍵不到。〔2026-08-04 查證:dedupe 實際住在 `balance.py`(`dedupe_positions` :70-88 / `merge_fut_positions` :92-112,由 `client.py:348/:399` 寫入前套用),`store.py` 只是 `stock_no` 單鍵 dict(:74,:230)— 那兩個函式是單鍵設計的補償層(docstring 自承「寧少不錯」)。改造範圍 = store 鍵 + 移除 sec dedupe 補償 + 平倉 `req.key` 帶 kind(client.py:809/:824)+ REST 與前端 `CapitalPositionsList`(以 stock_no 找列)連動,含 wire 契約,比原記載大〕~~ **2026-08-05 修畢(mod/capital-position-key-kind)**:`store._positions` 改 `(stock_no, kind)` 複合鍵(`set_positions` carry-over / `apply_profit_rows` 同鍵回填、kind=None 整列略過;`position_for(stock_no, kind=None)` 三態 = 精確鍵 / 唯一列 fallback / 多列回 None 不猜);**`balance.dedupe_positions` 補償層已刪**(`merge_fut_positions` 保留 — fut 列 kind 恆 cash,同契約 B/S 複合鍵下仍同鍵,不合併會互蓋);`close_position` sec 走 `(key, kind)`,無 kind 且同檔多列 → 403 ORDER_BLOCKED「請指定種類」(fail-safe 不猜種類),fut 走唯一匹配不寫死 cash;close 兩把鍵顯式分離(inflight 含 kind、活單掃描仍以標的);`_on_profit_complete` 兩段判別(查無股號靜默 / 種類不符才 warning);wire 加 optional `kind`(`PositionCloseRequest` / `PositionCloseBody` / 前端 `CapitalCloseBody`),前端 rowKey 複合化 + sec 列種類標籤(現/資/券,代號 span 的獨立子元素)+ 確認彈窗種類列。gate:pytest 1686 / npm test 1002 / ruff / pyright 0 / validate 42/42。**真環境待驗**(群益登入 + 面板部位列,見下)

## 2026-07-29(trade-layout-rework 順手清單)

- [x] ~~`stock-ladder-open` localStorage key 已停用(閃電梯摺疊機制隨右欄 tab 取代):舊值殘留無害,未做清除 migration;若之後做 key 收斂(見 2026-07-28 條)一併清掉~~ **2026-08-04 已清**(`ORPHAN_STORAGE_KEYS` 啟動 removeItem,見 lib/constants.ts)。
- [x] ~~`/api/stock/bars` 的真實環境驗證待補~~ **(a)(b)(d) 已於 2026-07-29 18:00 盤後驗畢**(mod/stock-ui-fixes;重啟 server 後實打 2317):(a) `tf=D` → **116 根**,落在 100–120 ✅;(b) **DK 的 `Open`/`Volume` 欄位名假定成立**,`o=240000` / `v=81973` 皆真值且 `v` 與畫面表頭總量一致,server log 無「DK rows 解析略過」warning ✅;(d) 當日段耗時 `tf=D` 1.1s / `tf=1&days=5` 2.1s(810 根 / 3 交易日),遠低於 5s 門檻 ✅
  - [ ] **(c) 仍待盤中驗**:分K 停留 ≥2 分鐘看最後一根 `t` 前進(SC-10)—— 需交易時段,盤後當日段不會再前進
- [x] ~~`BarsCache` 三個 dict(`_hist` / `_today` / `_daily`)永不清除~~ **2026-07-31 盤點:已由後續輪次順手解掉** — `server/bars.py:158-183` 有 `prune(today)`:`_hist` 按 `today - DAYS_MAX*2` 刪、`_daily`/`_daily_tag` 非今日即刪、`_today` 按日期 + TTL evict、`_empty` 過期即刪;三個呼叫點(bars.py:207/312/337)在每次 `build_*` 開頭。註解記來源為「review P2-5」「self-review round2 P2」
- [x] ~~🔴 **既有 bug:`_SPOT_PREFIX = "TC.F."` 讓任何期貨 tick 覆寫台指現價**~~ **已於 2026-07-30 修畢(mod/index-board)**:收斂為 `TC.F.TWF.TXF.`(台指期產品樹,含月份 leaf,常數單一定義在 `models.SPOT_PREFIX`)。real-env 夜盤實證:IndexBar 台指 41750.0 vs 期貨 tab TXF 41749.0(差 1.0 點),TXO snapshot spot 同值,`dropped_foreign_ticks` 4057 筆 = 被正確擋掉的個股期/海外六腿/小台微台。另加節流 warning `txo spot 無 TXF 推播`(盤中連續 3 分鐘無現價才印)—— 收斂後多了「靜默空白」的新失效態,比亂跳更難察覺
- [ ] K 線 endpoint 未做 inflight dedup(專案 `_run_once` 慣例):同 code 併發請求會各自打一輪 TC4。單人本機用量下未觀察到問題,若之後多分頁/多 client 再補
- [ ] `inTradingHours` 只擋週末,**國定假日仍會每 60s 空跑**。〔2026-07-31 盤點:兩個子前提已漂移但**結論不變** —— 後端短負向快取已做(`bars.py:45` `EMPTY_TTL_SECS = 15.0`,空結果也存)、deadline 已縮到 10s,但 **15s TTL < 前端 60s 輪詢**,假日每輪仍會真打 TC4〕。要根治需要交易日曆
- [x] ~~`_collect_history` 對「真的沒資料」與「TC4 沒回」都等滿 `poll_wait*30` ≈ 30s~~ **2026-07-31 盤點:已做** — `live/tc4.py:40` `BARS_POLL_DEADLINE = 10.0`,`_collect_history` 簽名加 `deadline_secs`(tc4.py:337-343、:358 fallback 回舊預算),另加退避輪詢(:353-354);K 線呼叫點皆已改傳(`stock_source.py:451/454/464`、`futures_source.py:130/133`,overlay 共用路徑一併評估過)。**注意**:`_collect_history` 已自 `stock_source` 上提到 `live/tc4.py`,舊條目引用的檔名過期

## 2026-07-29(stock-ui-round2 批一 順手清單)

- [ ] **批二(user 已拍板拆兩批)剩一項**:項 9 閃電梯跟隨置中(判定為描述現況,
  待 user 確認是否有症狀;定位:`PriceLadder.tsx` 的 `follow` state 與 `centerPrice` 的
  scrollIntoView effect,行為未動)
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
- [x] ~~分 K 首載耗時未量到(2330 走後端永久 memo)。change-spec §7 估 10–15s;若 >20s 退回
  預設 10 日~~ **2026-07-31 盤點:已於 stock-ui-round3 量到,估值高估近一個量級** —
  冷資料標的 1101 / 2603 / 3037 三檔 `?tf=1&days=30` 實測 **2.12 / 2.13 / 2.12s**
  (`.claude/mod/stock-ui-round3/real-env-verification.md:78`);三檔幾乎完全相同 →
  主導成本是固定等待不是資料量。>20s 的退回條件不成立
- [x] ~~`buildCandleGeometry` 的 `yTicks` 是等分不 snap 合法 tick → 日 K 左緣會出現
  `2547.32` 這種非法價位~~ **2026-07-31 盤點:已收** — `lib/candle.ts:234-242`
  `const raw = Math.round(lo + (span * i) / (Y_TICKS - 1)); const priceMilli = snapNearest(raw);`
  + 出界/重複過濾,:230 的 `span<=0` 分支與 :251-253 保底那根亦 snap;註解直接引用「round3 項 10」
- [ ] 布林通道填色用 `fill-ink-muted` 0.07,在 20 期低波動段會蓋成一大片灰塊;
  若嫌干擾可改只畫上下軌不填色,或降到 0.04
- [x] ~~**既有行為,自評 lens 抓到但本輪駁回不修(鐵則 B 不順手改)**:`candle.ts` 的
  `indexOf` guard 是 `x > size.width` 才回 null,`x` 恰等於 `size.width` 時
  `Math.floor(x/slot)` 算出 `bars.length` → 被 `i < bars.length` 擋掉一樣回 null,
  但那個像素理應對應最後一根。症狀 = 最右一個像素的 hover 失去十字線。
  本輪未動那行;要修時 `x >= size.width` 或 `Math.min(bars.length-1, …)` 擇一~~
  **2026-08-03 修畢(fix/candle-right-edge-hover,/bug 流程)**:採 `Math.min` 夾制,
  紅測試先行 + 反向驗證 + 真環境右緣四點掃描 PASS;artifact 見
  `.claude/bug/candle-right-edge-hover/`
- [ ] `MINUTE_INIT_BARS = 240` / `DAILY_INIT_BARS = 120` / `MAX_VISIBLE = 700` /
  `ZOOM_STEP = 1.15` 四個常數分散(**2026-07-31 盤點:已從兩檔擴散到三檔** ——
  `StockChart.tsx:20-21` / `candle-viewport.ts:14` / `CandleChart.tsx:32`);
  若之後要做「可設定的圖表偏好」再收斂到單一 config

## 2026-07-29(stock-ui-fixes 順手清單)

- [x] ~~🔴 **server 版本無可視性 —— 本輪 item 2 的真正代價**:「K 線沒有資料」的根因是 :8721 跑的是**舊版 build**(`openapi.json` 根本沒有 `/api/stock/bars` 這條 route),但前端與人都無從辨識執行中的 server 是哪一版~~ **2026-07-31 修畢(後端兩個候選都做了,前端比對未做)**:新增 `copycat/server/build_info.py` + `/api/health` 回 `{git_sha, git_dirty, started_at}`,啟動印 banner。排查用法 = `git log <git_sha>..HEAD -- copycat/` 有輸出即該重啟。
  - 真環境證據(fake source、獨立 port,刻意不碰 TC4):`copycat server build dfbc795 +dirty started_at=2026-07-31T15:59:24` / HTTP 200 `{"git_sha":"dfbc795","git_dirty":true,...}`
  - 8 條測試;反向驗證 route 改成每次請求重算 → `capture` 被叫 4 次而非 1 次 → 紅
  - `git_dirty` 三態(拿得到 sha 但問不到 status → `None` 而非 `False`):假的「乾淨」比沒有更糟
  - **剩下的**:前端狀態列/console 比對版本未做(第三個候選修法)。真要防同一類事故,前端拿到 `git_sha` 後與 build 時嵌入的 sha 比對才是閉環
- [x] ~~自選清單「全部」群組顯示「尚無自選,輸入股號新增」但主檔 2317 有完整資料~~ **2026-07-31 盤點:前提消滅(不是查明根因)** — 「全部」群組已不存在(側欄改為未分組 + 逐群組 section 並列,無群組切換 tab),frontend 全域 grep「尚無自選」零命中;後端 watchlist 升 v3,`ungrouped()` 由 `codes − ∪groups` 衍生。原症狀所在的 UI 元素不復存在,根因永遠不會查了
- [x] ~~五檔垂直版式的高度預算餘裕很薄(1440×800 下只剩 2px,再長一點就頂到 `min-h-56` 地板讓 `<main>` 出捲軸)~~ **2026-07-31 盤點:機制已不存在** — `StockPage.tsx:188` 下半列改成 `h-56 shrink-0`(**確定高度**,不吃剩餘空間,剩餘全歸圖表),`min-h-56` 已從 frontend/src 全數消失。不再是「會被內容撐大而頂到地板」的 min-height,原退化路徑不成立
- [ ] 盤後重啟 server 後五檔 / 閃電梯恆空(TC4 REALTIME 五檔盤後無推播;tick 明細與江波圖走 TICKS 回補所以有資料)。CLAUDE.md §8 記載「盤後 fresh subscribe 會回當日收盤 snapshot(延遲分鐘級)」—— 本次實測 1.5 小時後 `book.bids`/`book.asks` 仍為空,該記載可能只適用成交 tick 不含五檔,值得再確認後修正文件。

## 2026-07-30(realtime-correlation 收尾沉澱)

- [ ] **P1 既有 bug:`futures_engine` 會間歇性整段零推播(期貨面板時好時壞)**。〔2026-07-30 10:24 更正:原記「P0 死鎖 / 一直是壞的」下得過重〕TXO runtime 的訂閱清單含 `SPOT_SYMBOL = TC.F.TWF.TXF.HOT`(`server/engine.py:89`),`futures_engine` 訂同一 symbol 時 TC4 只推一邊(CLAUDE.md §8);其 leaf fallback 需先由推播解析契約月份才啟動 → 全零推播時啟動不了。**兩個相反的實測狀態**:(i) 2026-07-29 17:33 起跑的 server 到 00:50 為止 TXF/MXF/TMF 全 `p=null`、`seq=0`,同時段獨立訂閱 TXF.HOT 有 235 則/30 秒(MXF 324 則)、五檔俱全 → TC4 端正常;(ii) 2026-07-30 10:24 起跑的 server 六腿含 TXF 全部正常有值,realtime-correlation 的 base 腿與五對相關係數都算得出來。**故為間歇性,觸發條件未定位**(疑似啟動時序 / TC4 session 殘留 / 先前有 process 訂過同 symbol)。下輪要做的第一件事是**穩定重現**(鐵則 A:先穩定重現再談修),而不是直接動 fallback。修法候選:leaf fallback 改為可由「非推播來源」取得月份(合約清單查詢),或 runtime 與 futures_engine 共用單一 TXF 訂閱。
  - **〔2026-07-30 夜盤重現嘗試:5/5 全部健康,未重現 → 依鐵則 A 不改 code〕** 詳細 `.claude/bug/futures-engine-silent/repro.md`。**已排除的條件**:夜盤冷啟動、hard kill 造成的 TC4 session 殘留、連續快速重啟(各試 4–5 次全正常)、以及「一個 process 起兩份 app」(`python -m copycat.server` 確實有 parent/child 兩個 process,但 **parent 是 1 執行緒 0 連線的 stub**,child 才持 5 條 TC4 session)。
  - **⚠ 但這 5 次的證據力比表面弱 —— 平台實例是完美混淆變數(2026-07-30 17:xx 補查)**:`TOUCHANCE.exe` / `TCore64.exe` 的實際啟動時刻是 **2026-07-30 10:22:23**,即 handoff 引為「健康狀態 (ii)」的 10:24 那台 server 起跑前 2 分鐘。今天的 12:57 server、10:24 server、以及我這 5 次重測,**全部跑在同一個 TC4 process 實例上**;而 07-29 17:33 的失敗必然是另一個實例。**100% 的健康觀測集中在實例 A、唯一的失敗在實例 B —— 我只變動了 client 側條件,平台側從頭到尾沒變過。**「5 次獨立試驗」實際上是「同一個試驗做了 5 次」。**下一步該做的實驗是重啟達錢 4 本身再起 server**,那是唯一從未被變動的變數。
  - **〔同日 21:02 已補做,混淆解除:仍未重現〕** 重啟達錢 4 本身(新實例 pid 7164,21:02:54;**自動回來、不需手動登入**,port 50774 約 15 秒後 LISTENING)後冷啟動 server → **三品 18 秒內全有值**(trial6,證據 `trial6_fresh_tc4.log` / `trial6_poll.txt`)。故健康狀態已在**兩個不同的 TC4 process 實例**上各自觀測到,平台實例不再是混淆變數,「平台年齡 / 暖機狀態」也不再是活假說。累計 **6/6 未重現**,涵蓋:夜盤、hard kill 殘留、連續快速重啟、兩個 TC4 實例、回補負載 17k–48k ticks。
  - 附帶反證:trial6 的啟動**零 REQ timeout**(5 條 session 的 connect 全落在 270 ms 內)而回補達 48k ticks —— 比先前健康那次的 17k 重得多、接近失敗夜的 69k,卻完全沒有逾時。故「回補負載重 → REQ 逾時 → 訂閱失敗」這條因果鏈的前半段(負載→逾時)並非必然,逾時另有觸發源。
  - **兩條連帶更正**:(a) 17:33 那台**沒有 corr engine** —— corr 的第一個 commit 是 07-29 23:57,故當晚是 4 條 TC4 session 而非 5 條,「corr 搶訂 TXF.HOT」與「第 6 條 session 超過平台上限」兩個假說對當晚不成立(且我的重測是 5 條 session + 更重負載卻全健康,資源耗盡類假說反而被削弱)。(b) 「三品全 null、seq=0」**沒有任何存檔快照**(全 repo 與 .claude 搜過),來源是當下看 API 的印象;而現存 `server2.log` 顯示同晚稍後 TXF/MXF 是**有**資料的。`seq=0` 更像「從未被寫入過的初始值」指紋 —— 若真是訂閱衝突,通常會有零星推播或 resolve 痕跡。故「失效點在引擎根本沒起來」與「症狀描述本身不精確」都還沒被排除。
  - **原記載的主因解釋不了症狀(更正)**:「同 symbol 撞 `SPOT_SYMBOL`」最多只能解釋 TXF 一品,`MXF`/`TMF` 沒有任何其他模組訂閱卻同樣 `p=null`。不要再把這條當唯一假說。
  - **新的首要假說(讀 code + 探針成立,尚未在真環境確認)**:`_subscribe_all`(`server/futures_engine.py:127`)`except ConnectionError` 只 log 就跳下一品,**失敗的商品之後沒有任何重試路徑** —— 失敗 symbol 不進 `_subscribed`,而 `_check_stale` 的重訂閱只走 `list(self._subscribed)`(`live/tc4.py:456`);leaf fallback 又需要先收到推播才會排程。探針(`mechanism_probe.py`,真 engine + 假 source)實測:三品訂閱失敗 → `seq=0`、三品 `p=null`、`subscribe_symbol` 每品只呼叫一次、leaf 永不觸發 —— **與通報症狀逐項相同**。佐證:當晚兩份 log 的 TC4 connect 間隔是 30.0s = 3 × `_REQ_TIMEOUT_MS`(今天只有 1 ×),即當晚 TC4 REQ 通道確實在逾時。
  - **下次再發生時的一次定案法**:grep server log 有沒有 `futures <p> subscribe ... failed`(`_subscribe_all` 的 warning)。**有** → 上述機制確認,修法 = 失敗品進重試佇列(或把失敗 symbol 也記進 `_subscribed` 讓 `_check_stale` 接手)。**沒有** → 不是它,改查 SubPort / listener 執行緒存活。
  - **前提:server 要留 log**。通報那台沒保存 stdout,是這輪定位不了的直接原因 —— 日常啟動建議 `python -m copycat.server > logs/server-YYYYMMDD-HHMM.log 2>&1`。
  - **〔2026-08-04 首要假說的缺陷已修(fix/startup-names-futures-resub)〕**:`_subscribe_all`
    失敗品改進 `_pending_subs`,背景 `_resub_loop`(預設 10s)重試至成功;warning 字串
    `futures subscribe %s failed` 原封不動(本條 grep 判準繼續有效),重試成功另印
    `futures %s subscribe retry ok`。**真實觸發源(REQ 為何逾時)仍未定位** —— 修的是
    「失敗後零復原路徑」,下次真發生時症狀應在 ~10s 內自癒並在 log 留上述兩行;若再出現
    「三品長時間 p=null 且 log 無 subscribe failed」= 不是這條機制,回頭查 SubPort / listener。
    (第 8 次觀測 2026-08-04 00:06:三品健康,未重現。)
  - **〔2026-07-31 15:47 第 7 次未重現,且涵蓋一個全新條件〕** 一台 13:20 起跑、**橫跨日盤 → 夜盤 session 轉換**的 server(先前 6 次全是單一盤別內的冷啟動),15:47 打 `/api/futures/state`:TXF/MXF/TMF **三品全有價 + 五檔俱全**,`resolved_contract=202608`,`seq=138718`。同一台的六腿江波圖與相關係數表(台指腿正是讀 `futures_engine.state()`)夜盤畫面全部有值。累計 **7/7 未重現**。判準不變:下次發生時先 grep server log 有沒有 `futures <p> subscribe ... failed`。
- [x] ~~`test_index_engine.py::test_rollover_two_phase` 只在真實時鐘 ≥ 08:30 才會綠~~ **2026-07-30 修畢**:建構子補 `now_fn`(預設 `now_time()` = 真實牆鐘 → prod 行為零改變;`IndexEngine(` 只有 `app.py:210` 與測試兩個呼叫點)。另補 `test_rollover_gate_opens_at_0830` 覆蓋門檻本身(原本無測試 —— 唯一的時鐘讀取沒有注入點,寫不出來)。注入 00/08/10/23 皆綠;反向驗證 revert → 12 紅。
- [x] ~~`test_tc4.py::TestConnectInterruptible` 與 `test_tc4_trade.py::TestFailedConnectGcSafety` 依賴未進版控的 `spikes/TCPY/`~~ **2026-07-30 修畢**:`tests/conftest.py` 出 `requires_tcpy` marker,兩個 class 整體 skip。**過程中抓到第三條(原記載未列)**:`test_check_stale_reconnect_loop_stoppable_when_app_dead` 在缺 wrapper 時是**假綠** —— 重連執行緒死於 `ModuleNotFoundError` 也滿足 `assert not worker.is_alive()`,等於沒驗到「迴圈可中斷」。雙向驗證:缺 TCPY → 3 skipped/37 passed;複製 TCPY 進 worktree → 40 passed/**0 skipped**(marker 不過度 skip)。
- [ ] TCPY 路徑運算式 `Path(__file__).resolve().parent.parent.parent / "spikes" / "TCPY"` 在 production 重複兩處(`live/tc4.py:148`、`data/backfill_tc4.py:104`;原第三處 `live/tc4_trade.py` 已於 2026-08-04 隨舊 trade 路刪除),`tests/conftest.py` 的 `TCPY_DIR` 是第三處。當時刻意不抽共用常數(P2 測試層 bug 不動 production 檔)。**收斂條件**:出現第四處、或 `spikes/TCPY` 位置要改時,抽 `copycat/tc4common.py` 的 `TCPY_DIR` 單一定義,三處都引它。
- [x] ~~realtime-correlation 的 SC-5 日盤補驗~~ **2026-07-30 10:24 已驗**:日盤六腿全部有中價且非 stale(TXF 40646 / TWN 3462.62 / YM 51909.5 / ES 7388.88 / NQ 27638 / SXF 10776),五對相關係數算出實值(TWN 0.590 / YM 0.147 / ES 0.336 / NQ 0.520;SXF 因整窗中價未動 → 標準差 0 正確回 null)。SC-6 同時驗過:60 秒收 61 則、間隔中位數 1.010s、seq 連續遞增。
- [ ] realtime-correlation 訂閱窗的**反向**驗證仍未做:「沿用 `session_window` 會失效」是推論不是實證 —— 台指日盤窗(UTC 00–06)+ 夜盤窗(UTC 06–22)合計涵蓋 UTC 00–22,訂閱當下海外腿幾乎不會落窗外;真正的風險是「訂閱後跨過窗結束邊界(UTC 06 / 22)推播是否停止」。驗法:在 UTC 05:5x(台北 13:5x)前訂閱並持續監聽到 UTC 06:0x 之後,看推播是否中斷。全天窗實作本身已是防禦性選擇,此項只影響「基底 source 是否也該改」的判斷。
- [ ] `corr_state.correlations()` 每腿每次重建 `leg_by_ts` dict(1800 entries)、每窗各過濾一次。實測滿窗 tick 6.43 ms(門檻 200 ms)不構成問題;若日後窗長或腿數放大再看。
## 2026-07-30(index-river-chart 收尾沉澱)

- [x] ~~🔴 **既有 bug 加證:`aggregate.py:21 _SPOT_PREFIX = "TC.F."` 的汙染範圍比原記載更大**
  (real-env 實見 IndexBar 台指顯示成富台 3419 / 納指 27488,開 server 就踩)~~
  **2026-07-31 盤點:與 2026-07-29 條的 `[x]` 是同一個根因,同一個 commit 一起修掉了** —
  修復 commit `abfcd7a`(2026-07-30 index-board)。現況:`models.py:23`
  `SPOT_PREFIX = "TC.F.TWF.TXF."`(註解明寫「不可放寬成 `"TC.F."`」),`aggregate.py:21`
  引用它;`route()` 對非台指期的 `TC.F.*` → 不匹配前綴 → 不在 `_contracts` →
  `dropped_foreign_ticks += 1; return`,即丟棄且只計數 = 完全等同本條要求的修法。
  **教訓**:同一個 bug 在兩個分節各記一條(07-29 修了打勾、07-30 又記一條沒打勾),
  盤點時才發現 —— 加新條目前先 grep next-time.md 有沒有同根因的既有條目
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
- [ ] `ws_river_count.py`(evidence 腳本)第一版沒回 Pong → uvicorn 的 websockets 在
  ping_interval + ping_timeout(各 20s)後關連線,量成「39 則/60 秒」。**寫任何手打
  WebSocket client 的量測腳本都要回 Pong**,否則超過 40 秒的觀測窗會被截斷。

## 2026-07-30(stock-ui-round3 順手清單)

- [x] ~~🔴 **「有資料但 TC4 慢」會顯示肯定語氣的錯誤結論**(change-spec Known Risks 1):
  `_BARS_POLL_DEADLINE=10s` 誤判為空 + 15s 負向快取 → `CandleChart` 顯示「無 K 線資料」
  而非「還在等」。~~ **2026-08-05 已修**(mod/bars-tristate-status):三態
  `status ∈ {ok, timeout, disconnected}` 沿 `_collect_history`(HistoryResult)→
  `fetch_bars_range(_tagged)` → `bars_range` → `BarsFetcher`(BarsResult NamedTuple)→
  response 傳遞;負向快取與 `_today` cache 連 status 一起存(不洗白);前端 timeout =
  灰字「等待 TC4 回應中…(自動重試)」、disconnected = 紅字、ok+空維持「無 K 線資料」,
  非 ok 空態每 20s 自動重試(> 15s 負向快取)。**注意語意界線:TC4 查無此檔的常態表現
  是 timeout 不是 ok+空**(GETHISDATA 空頁無法區分未備妥/無資料,協定限制)。
  當年估的「20 個 call site」實數 32。
- [ ] 大螢幕明細列數不再隨視窗變高(下半列固定 224px ≈ 7 列)。1920×1080 上明細與
  1440×900 一樣多,這是「圖表吃剩餘高度 + 兩塊卡片貼底」的直接代價(Known Risks 2)。
  若之後嫌明細太短,考慮把下半列改成 `flex-1 max-h-72 min-h-56`(需重驗 SC-6)。
- [ ] 五檔卡片底部約 24px 留白:`h-full` 讓卡片撐滿 224px 而內容約 200px。這是對舊
  `self-start` 取捨的刻意推翻(user 要求貼底)。若嫌空,可讓五檔列高改為內容高並只讓
  明細貼底(但兩塊底邊就不齊平)。
- [ ] `--color-time` 與 `--color-ma5` 目前同色值(#f0b429),語意獨立是刻意的。
  若之後 MA5 改色,時間軸不受影響 —— 但也要記得兩者並置時對比度會消失。
- [ ] `_POLL_BACKOFF_START = 0.15` 與 `BARS_POLL_DEADLINE = 10.0`(**2026-07-31 更正:
  後者已去底線且與 `_collect_history` 一起上提到 `live/tc4.py:40,43`**)兩個常數是實測推得
  (有資料標的首頁 <1s 備妥),TC4 忙碌時的真實分布未量。若 real-env 出現誤判為空的
  頻率偏高,先量首頁備妥時間分布再調,不要盲目放大 deadline(那會把 60s 問題帶回來)。

## 2026-07-30(stock-ui-round4 自評 review 沉澱)

- [x] ~~localStorage key 收斂:`stock-wl-group`(舊 activeGroup)在本輪後已成**孤兒鍵**(讀取端移除,刻意不清);新增的 `copycat-stock-wl-collapsed` 已用 `copycat-` 前綴。做 `lib/constants.ts` 集中時一併清掉孤兒鍵~~ **2026-08-04 已清**(refactor/frontend-localstorage-keys,`ORPHAN_STORAGE_KEYS` 啟動 removeItem)。
- [ ] 股票名稱表(`copycat/stock_names.json`)無自動更新:新上市 / 改名要手動 `python -m copycat refresh-stock-names`。若要自動化,考慮 server 啟動時檢查檔案 mtime > N 天才背景重抓(**不要**放進 request path,ISIN 頁 10 MB)
- [x] ~~worktree 陷阱:`spikes/TCPY/` 在 .gitignore 內 → 新 worktree 缺它會讓 `test_tc4.py::…dead_port…` 與 `test_tc4_trade.py::…gc…` 兩支以 `ModuleNotFoundError` 紅~~ **2026-07-31 盤點:測試變紅的前提已解除** — `tests/conftest.py:21-25` 出 `requires_tcpy` marker(wrapper 不在時整 class skip),同檔 2026-07-30 條已記雙向驗證(缺 TCPY → 3 skipped/37 passed;補 TCPY → 40 passed/0 skipped)。殘留事實:`.gitignore` 仍排除 `spikes/TCPY/`,worktree 仍需 `Copy-Item` 帶過去(那是 CLAUDE.md §8 的 worktree 教訓,不是本條)
- [x] ~~**盤中不要起第二台後端**:TC4 同 symbol 跨 session 只推一邊,驗證用途只起前端 dev server。本輪踩過一次(約 90 秒),值得考慮寫進 CLAUDE.md §8~~ **2026-07-31 已寫進 CLAUDE.md §8**(連同「若非驗行情則用 fake source + 另一個 port」這條繞法)
- [ ] `dropTargetFromPointer` 的 nearest-zone 在兩個 zone 距離相等時取先出現者(未定義偏好);群組間縫隙很窄時使用者感受不到,若日後 section 間距變大再定規則

## 2026-07-30(stock-ui-round5 沉澱)

- [ ] **SC-1~SC-22 的畫面對照大部分仍未做**(merge 時只有量化 gate + 後端真實資料佐證)。
  - [x] ~~最該補的一項:側欄「管理」鈕的 `<dialog>` / `showModal()`~~ **2026-07-31 15:5x 真瀏覽器驗畢**
    (Chrome 1440 視窗,盤後):關閉態 `open:false` / class 帶 `hidden` / `display:none` /
    rect 0×0(不佔版面);點「管理」→ `showModal()` 正常開啟,backdrop 變暗、群組列
    (未分組 1 / 自選 3)與加入自選輸入框齊備;按 ESC → `open:false` / `display:none` /
    **`childCount:0`**(內容卸載 = React prop 確實被 `onClose` 同步回去)。
    round6 的兩個修法(display 跟著 open 切、補 `onClose`)在真瀏覽器均成立。
  - 其餘 SC 的畫面對照仍缺;顏色類要盤中(見下條)。
- [ ] **顏色類 SC 只能盤中驗**:收盤後 TC4 不推 REALTIME → `meta` 恆為 `null`,而漲跌色一律以
  `meta.ref` 為基準 → 明細三欄(SC-5)、現價圈(SC-2)、左軸刻度(SC-20)盤後全灰。
  這是既有行為不是本輪的 bug,但排驗收時程要考慮進去(盤後只驗得到幾何與有無)。
- [x] ~~**江波圖 autofit 域裝不下逐筆極值 —— 有實例了**:2330 於 2026-07-30 盤後(無 meta →
  autofit)域為 `[2160.5, 2259.5]` 而當日最高 `2260.0` 落在域外 0.5 元 → 高點線不畫(設計如此,
  spec R12)。要讓兩條線在無漲跌停時也必定看得到,得把 y 域改成「含當日高低」再算 —— 那會動到
  `buildIntradayGeometry` 的域語意與一整批座標斷言,是獨立一輪的工作,不要順手改。~~
  **2026-08-05 已修**(mod/river-autofit-daily-range):autofit 半幅池併入 `input.high/low`
  (norm 歸一、`ref > 0` 才併 — 無錨點時擴域只放大垃圾);markFor 同步吃 norm 值;
  2330 臨界形狀(域外 0.02%)有回歸測試釘住;漲跌停分支與域外 guard 不動。
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

- [ ] **memo 是否被打穿沒有任何測試 pattern**(review F11,rejected_with_reason):`StockIntradayChart` 的 `ChartStatic` / `EnergySub`、`CandleChart` 的 `ChartStatic` 全域零覆蓋,W-3 一直只靠 code review + 註解自律。要補就該一次建立可重用的 render-count 觀測基建(而不是為單一 props 發明一套沒人維護的寫法);它守的是效能不是正確性,優先度依實測掉幀情況再定
- [x] ~~側欄的 `EMPTY_WL` fallback 在自選載入失敗時仍可能被寫入而把整份自選清空(change-spec K-3)~~ **2026-08-04 /bug 修掉**(fix/watchlist-empty-wl-clobber):真破口 = 「管理」鈕在 error/pending 態照樣渲染並把 EMPTY_WL 傳進 Dialog,Dialog 的新增群組 / 加入股票以空自選為基底整份 PUT;修法 = `data === undefined` 時不渲染「管理」鈕(沿用 StockPage gate pattern;TanStack Query 成功過後 refetch 失敗仍保留舊 data,undefined 只發生在從未成功載入,入口 gate 涵蓋整個危險窗)。regression 測試鎖 error/pending 兩態,反向驗證過。artifacts:`.claude/bug/watchlist-empty-wl-clobber/`
- [ ] 側欄 / Dialog / StockPage 三處 mutation 為 last-write-wins(K-4);pending 防護現況(2026-08-04 收尾 review F3 實測更正):StockPage 3 處有 `save.isPending` 防護、Dialog 僅「加入股票」建議列一處(:354),**Sidebar 零防護**(`commit()` 無 pending 檢查,拖曳 / × / 加入群組全裸)— 除跨元件並發外,同元件內連點 / 拖曳期間重複 PUT 亦未防〔2026-08-04 /bug 輪評估:與 K-3(fallback 狀態混淆)**非同根因**,修法域也不同(pending 防護 / 後端版本戳 vs 入口 gate),未併入該輪,維持本條待處理〕
- [ ] EMPTY_WL 危險窗封閉的成立條件是跨檔不變式(2026-08-04 收尾 review F1,`commit()` 早退 rejected_with_reason):現況全 repo 無 `resetQueries` / `removeQueries`、StockPage 永不卸載(App visited+hidden)→ watchlist query data 成功後不會退回 undefined,入口 + Dialog 同 gate 已涵蓋;**若日後**對 `stock-watchlist` 改用 resetQueries / 改 queryKey / 讓 StockPage 可卸載(gcTime 回收),危險窗會重開且測試零訊號 — 屆時再補 `commit()` 的 `data === undefined` 早退(repo 精神:不可達防禦 = 沒有測試覆蓋的死碼,見 WatchlistSidebar.tsx 拖曳 teardown 註解,現在不加)
- [ ] 自選載入失敗態側欄仍渲染空「未分組」區塊 +「拖曳到此移出群組」提示(2026-08-04 /bug 輪 Phase 7 截圖觀察):無寫入風險(無列可拖),純視覺突兀 — error 態可考慮整段收起只留錯誤文案
- [ ] 預覽非自選股後 `copycat-stock-main-code` 仍會記住它(K-1):重整後主區停在該檔而側欄無對應列可反白,後端 `_main` 長期掛在非自選 code(refcount 吃得下,不佔 50 檔上限)。〔2026-08-04 更名同步:key 已改 `copycat-stock-main-code`(`lib/constants.ts` MAIN_CODE_KEY);真正持久化點在 App.tsx 的 setItem useEffect,別被 LEGACY 遷移常數誤導〕
- [ ] **驗證環境阻塞:達錢 4 未開時 server 起不來,錯誤訊息不指向根因**(2026-07-31 stock-ui-round4 Phase 7):`TC4 quote connect failed: Resource temporarily unavailable`(ZMQ REQ 的 EAGAIN)——實際成因是桌面程式沒開/沒登入,不是資源競爭。當時觀察序列:port 50774 有聽 + 舊 server 有真資料 → 舊 server 消失、port 仍聽但 LOGIN 逾時 → port 關閉。**「50774 有聽」不等於 OpenAPI 可用**,排查時先確認 app 已登入再看程式碼。另:兩個 server 同時連 TC4 是否可行本輪**未證實**(觀察被 app 關閉污染),別把「單一 session」當已知事實

## 2026-07-31(stock-ui-round6:市價偽檔位 / 內外盤判定)

- [x] ~~**側欄自選列的漲跌停亮燈**(本輪 out of scope)~~ **2026-07-31 做掉了**:
  `_quote_payload` additive 加 `upper`/`lower`(`no_data` 時 meta 已為 None → 自動滿足
  「所有值欄位一律 None」契約,零例外路徑);前端用既有 `limitState()`,亮燈時整塊吃
  底色 + 白字。**側欄亮燈 = 觸停,與主區五檔的鎖停 badge 刻意不共用**(後者是
  `bids[0]===upper`,需要五檔,側欄沒有)。後端 1 + 前端 4 條測試,含「`chg_pct=+19.9%`
  但 `upper=null` → 不亮」把「不可用百分比猜」釘住。
  - **⚠ 畫面對照未做**:要看到亮燈得**重啟 :8721**(舊 build 不發 `upper`/`lower`),
    而重啟會清掉櫃買當日 in-memory 序列 → 刻意沒做。下次重啟後順手看一眼即可
    (今天 2327 / 2330 都鎖漲停,是現成的驗證素材)。
- [ ] **價差內成交(bid < 成交價 < ask)的判定**:2026-07-31 實測 4989 / 6207 這類近漲停股
  有約半數成交落在這裡。逐筆拆解顯示主因是**時序假影** —— 同一則 REALTIME 帶的五檔已是
  成交後的簿,`p=55700 b=55600 a=55800` 判 neutral 而 `p=55700 b=55700 a=55800` 判 inner,
  同一個價格因為簿的新舊而落到不同類。修法候選 = tick rule(比對前一筆成交價),
  但那是換一套演算法,要先有對照驗證窗。本輪由「判定率」欄誠實呈現,未修。
- [ ] **`0` 檔位是否只在鎖漲跌停出現**:實測只見鎖漲停一例(2327)。若集合競價期間
  或其他情境也推 price=0,`_best_limit_price` 的作用面會比預期大(方向仍正確)。
  下次碰到集合競價時段的簿快照時順手確認。
- [x] ~~**五檔的 `maxQty` / 總量列仍計入市價量**~~ **2026-07-31 user 拍板照建議做掉:
  分開顯示**。總量列與量 bar 歸一一律只算限價量,市價量獨立成一列(`h-4` 固定高度,
  兩側為 0 時整列空字串 → 有無市價量都不抖動),移除原本的 hover title。
  另補 bar 寬夾制 —— 反向驗證:拿掉夾制,2327 市價列算出 **170%** 會溢出列外。
  測試 5 條。**畫面只驗到空態**(2327 盤後的簿已無 price=0 檔位,市價佇列是盤中才推的),
  有市價量那態下次盤中鎖停時補看。以下為當時的拍板依據:
  市價 14167 vs 最佳限價 11877,量 bar 被市價那列壓縮、總量列 26,216 混著兩者。
  - **兩個數字回答的問題不同**:總量列 = 「委買 vs 委賣力道對比」,是**跨日跨股比較**的
    相對讀數 —— 現況讓同一欄位在鎖停日是「市價 + 4 檔限價」、平常日是「5 檔限價」
    (市價偽檔位吃掉 DEPTH 一格),**定義隨日子變、比較靜默失真**;量 bar = 「哪一檔厚」,
    是限價檔之間的形狀比較,市價檔沒有價位卻參與歸一。2327 壓縮比 0.84 還算輕,
    但市價佇列可以是限價量的數倍,那時五根限價 bar 會一起壓成看不見的短樁。
  - **subagent 建議(未執行)= 分開顯示**:總量列只算限價量、市價量獨立成一個數字;
    量 bar 歸一分母排除市價檔。三案取捨 —— 全含保住「總壓力」頭條但定義漂移;
    **全排除會藏掉鎖板日最重要的數字**(14167 張無限價排隊 = §0a 鎖板品質核心訊號),
    在本專案最在意的情境下反而最糟。
  - **最強反對**:鎖漲停時交易者要的可能正是「買方一共排了 26,216 張」這個合計,
    拆開反而逼他心算。若這個讀法成立,正解是**維持全含但把市價量常駐顯示**
    (而非 hover),只改 `maxQty`。
  - 改動點:`OrderBook.tsx:150`(maxQty 過濾)/ `:151-152`(總量)/ `:233-250`(顯示,
    需預留固定高度避免市價量為 0 的日子抖動)/ `OrderBook.test.tsx:193-207,328` 斷言重算。
- [x] ~~**判定率門檻 60% 的吵雜度**~~ **2026-07-31 user 拍板照建議做掉:門檻 60 → 75,
  警示改掛「判定率」本身(不再暗化外盤比)**。真環境確認:4989 判定率 64% →
  `text-warn` / `rgb(240,180,41)` / title 齊備,外盤比 42.0% 恢復正常色 —— **這正是
  舊門檻 60 抓不到的那一檔**;2327 判定率 100% 無警示。新增 `--color-warn` token
  (語意獨立於 ma5/time,沿用專案「同色值、語意獨立」慣例)。測試 5 條含 74/75 邊界。
  **保留的疑慮**(寫進 `stock-intraday-svg.ts` 註解):樣本僅 6 檔、單日、集中在近漲停股,
  那個「雙峰間隔」可能是抽樣假象 —— 若平常日出現大量判定率 70% 左右的普通股被標成
  可疑,回頭重估這個值。以下為當時的拍板依據:
  2026-07-31 **盤後**重量四檔:2327 **100%** / 2330 98% / 4989 **64%** / 6207 51%
  —— 只有一檔落在暗色,原記載「近漲停股常態落在 50%」偏悲觀。
  - **併上盤中舊樣本(2330 100% / 2317 83.7% / 6207 52% / 4989 50.8%)後分佈是雙峰**:
    正常群 83.7–100、劣化群 51–64。60 落在**劣化群內部** → 4989(未分類 1500 /
    總量 4132,逾三分之一被排除在分母外)被顯示為完全可信。最大間隔切點約 74。
  - **subagent 建議(未執行)**:(a) 門檻 60 → **75**;(b) 警示從「暗化外盤比」改成
    「標記判定率本身」—— 降對比在 UI 語彙裡是「不重要 / 停用」,而這個數字是
    「重要但失真」;且判定率本來就印在旁邊,暗化沒增加任何資訊位元,只增加一個
    懸崖(4989 盤中 50.8% → 盤後 64%,跨過門檻整個亮暗翻面)。
  - **最強反對**:樣本僅 6 檔、單一交易日、集中在近漲停股;83.7 與 64 之間的「間隔」
    可能是抽樣假象,平常日判定率 70% 的普通股會被新門檻標成可疑而舊門檻不會。
    若不接受換門檻,(b) 只改呈現的部分不依賴樣本量,可單獨採納。
  - 改動點:`stock-intraday-svg.ts:136` 常數 + `StockIntradayChart.tsx:804-811` 呈現 +
    `StockIntradayChart.test.tsx:634,649,659` 斷言。
  - [x] ~~註解裡的 2327 = 0%~~ **已更正**(那是 round6 修法前的數字,修法正是為了消滅它;
    留著會讓下一個人用失效證據重推門檻)。
- [ ] **`relabel_locked_side` 只掛在 `apply_backfill`**:live 路徑靠 `_best_limit_price` 就夠
  (五檔有第二檔可退)。若之後出現「簿裡只有市價檔、連第二檔都沒有」的 live 情境,
  live 也會判不出來 —— 屆時再考慮把 relabel 提到 `ingest`。
  - 〔2026-07-31 15:5x 盤後畫面驗證:**修法在真環境成立**。2327 國巨(整日鎖漲停)
    內盤 5964 / **判定率 100%** / 外盤比 0.0% —— 對照 CLAUDE.md §8 記載的修法前狀態
    「全日 5450 張成交 `cum_outer = cum_inner = 0`、副圖整片灰、外盤比分母 0 算不出來」。
    2330(尾盤鎖漲停)判定率 98%〕

## 2026-07-31(next-time 全檔盤點輪 —— 新增)

- [ ] **同一個 bug 在兩個分節各記一條、只有一條被打勾**:`_SPOT_PREFIX` 汙染在 07-29 條
  已 `[x]`(commit `abfcd7a`),07-30 index-river-chart 卻又記了一條沒打勾的紅標,
  盤點才發現。**加新條目前先 grep 本檔有沒有同根因的既有條目**,而不是新增一條加證。
- [ ] **本檔的條目引用會隨重構靜默腐爛**:本輪盤點抓到三處引用失效(`stock_source._collect_history`
  → `live/tc4.py`、`_BARS_POLL_DEADLINE` → 去底線、`min-h-56` → `h-56 shrink-0`),
  都是「條目還在、指的東西已經搬走或改名」。條目寫 `檔案:行號` 很好用但過期無聲;
  下次大盤點時同樣要逐條回查,或考慮條目只寫**符號名**不寫行號。
- [x] ~~**前端狀態列版本比對**(`/api/health` 的第三個候選修法,本輪只做後端兩個):
  前端拿到 `git_sha` 後與 build 時嵌入的 sha 比對才是閉環 —— 現況仍需要人主動去打
  `/api/health` 才發現版本落差。~~ **2026-08-05 已出貨**(feat/frontend-version-drift):
  比對語意經兩輪 review 升級 — dev 模式**不是**單純 sha 等值(HMR 下會漏報動機情境 +
  對純前端 commit 誤報恆亮),而是 vite middleware `/__build/sha?since=<後端sha>` 跑
  `git log <since>..HEAD -- :/copycat`(top-level magic pathspec;vite cwd 在 frontend/,
  寫相對路徑會恆回 false 的靜默失效 — 實踩過)= CLAUDE.md §8 判法含路徑過濾的完整自動化,
  `behind:true` 才在 nav 列亮 amber「版本落差」膠囊 + console.warn(pair 去重)。
  真環境已驗:後端 8ef1346 vs HEAD ba31a8e 差 30 個 commit、其中**零個碰 copycat/**
  (前端/docs/artifact)→ 不亮(正確);since 指到 copycat commit 之前 → 亮。
  (drift 態像素級截圖不完整 — Chrome 視窗異常依紀律不重試,DOM/座標/title 已逐字查證
  → 待 user 自然複現時過目。)
  - [ ] **build/prod 的 equal 模式未經真環境驗證**(無 build 部署形態),且無路徑過濾 →
    純前端 commit 會誤亮。真要部署前先決定:CI 注入 copycat/ 範圍 sha,或把 range 判別
    搬到後端 /api/health。
  - [ ] **膠囊只判 commit 落差**:後端 uncommitted(git_dirty=true)跑舊 code 不會亮;
    /api/health 已回 git_dirty 而前端零消費,要不要併入膠囊/title 是下次議題。

## 2026-08-03(candle-right-edge-hover /bug 輪 —— 新流程首驗)

- [x] ~~**verify-gate hook 攔不到 copycat 的實際收尾路徑**:本 repo 無 remote,收尾走
  branch-lifecycle fallback 的 `git merge --ff-only`,而 hook 觸發式只有
  `git push` / `gh pr merge` —— 本輪的擋下/放行實證是靠「主動試 push」做出來的,
  日常收尾不會自然經過 gate。候選:hook 觸發式加「在 main 上 merge 流程分支」的形;
  或 copycat 補 remote(順帶解 artifact 異地備援)。~~ **2026-08-03 同日採「補 remote」
  解掉**:`https://github.com/loger-w/copycat`(**PRIVATE** — 策略 IP / 具名分點
  watchlist 不可比照 neigui 走 public;neigui 是排除 intel 目錄才敢公開的),
  master 00d451a 起追蹤。自此收尾走完整 branch-lifecycle(push → PR → merge),
  verify-gate 攔的正是這條路;artifact 同時獲得異地備援。
- [ ] **固定日期 fixture 的同型潛伏紅**:test_market_routes 的 partial_last 週期斷言
  已修(d84c440,動態 ISO 週 fixture),但全 tests/ 可能還有其他「fixture 寫死日期 +
  斷言隨 today 變」的組合 —— 下次任何測試在沒改 code 的日子突然紅,先想日期依賴
  (本輪 pattern:寫測試當週 True、跨週後恆 False)。
- [ ] d84c440 夾帶 ~10 行 ruff format churn(`_apply_otc` 合行、v 元組拆行;收尾 review P2-3):
  專案 gate 只有 `ruff check` 沒有 `ruff format`,implementer 順手 format 違反鐵則 B —
  blame 會指到語意無關 commit。已成事實不回滾;**之後 dispatch prompt 的邊界句要含
  「不要 ruff format 整檔」**(本輪第三個 dispatch 已補)。
- [ ] `_this_week_days` 兩個已知邊界(收尾 review P2-4,均為極低機率):`date.today()`
  同算式取兩次 + fixture 與 route 各自取 today,週日跨午夜起跑理論上可跨週變紅;
  docstring 宣告 n<=7 但無 guard。要根治得讓 route 的 today 可注入,成本不成比例,先記帳。

## 2026-08-03(stock-page-dedupe-deadcode /refactor 輪 —— 行為類發現與範圍外遺留)

盤點 artifacts:`.claude/refactor/stock-page-dedupe-deadcode/`(三份 findings + 計畫)。
以下 [behavior] 全部是 /refactor 中發現但**修了就改行為**的項目,要修走 /bug 或 /mod。

- [x] **[behavior] ref=0 的「無參考價」語意不一致**(一族三處)**→ 2026-08-03 修畢
  (mod/next-time-behavior-fixes M5,d3739cc):幾何入口 ref/upper/lower <=0 統一歸一
  null + 元件端一次歸一;review 補抓 upper/lower=0 走 [0,0] flat 分支與 hover 價色恆 bull
  兩處原描述沒涵蓋的失效**:
  (a) `stock-intraday-svg.ts` `ref = input.meta?.ref ?? (prices[0] ?? 0)` 用 `??`,而後端
  `to_milli_units("0")` 回 0 非 None → TC4 送 ReferencePrice="0" 時 ref 卡 0,autofit 分支
  算出 yTop=hi×1.1 / yBottom=−hi×1.1 整條走勢壓上半;StockPage/OrderBook 同件事用 truthy 判。
  (b) StockIntradayChart 的 lastTone 只擋 `ref === null`,而 `markTone` 多 `ref <= 0` 分支 —
  ref=0 時兩者 className 分岔(Track A6 因此跳過收斂;lastTone 那份是既有不一致)。
  修法方向:ref=0 一律視為無參考價(對齊 hasRef / tickTone / 後端 chg_pct),需 🔴 + 測試。
- [x] **[behavior] 前端增量 VWAP 分母錯位****→ 2026-08-03 修畢(M4,2208a0e+74cc449):
  snapshot 增 additive `vol`(去重剔試撮 Σqty),前端種子 `snap.vol ?? cum_vol ?? 0`**:前端用 `vwap × last.cum_vol` 還原分子再
  `+ msg.q` 累加,後端分母是去重剔試撮後的 Σqty ≠ cum_vol(TC4 TradeVolume)→
  訂閱前漏單/試撮期時靜默分歧,至下次全量 refetch 才收斂(`stock-accum.ts` vs
  `stock_state.py:139-141`)。
- [x] ~~**[behavior] `/api/stock/bars` tf=D 忽略 days 但仍對 days 做 400 驗證**~~
  **2026-08-03 修畢(M1,f322781):tf=D 路徑不再驗 days**。
- [x] **[behavior] DepthBar 鎖停判定仍用 `b[0]?.[0] === upper`****→ 2026-08-03 修畢
  (M6,145c462):全套對齊 OrderBook — badge best-limit + maxVol/總量 limit-only +
  0 價顯示「市價」(spec review S-6 把原本只修 badge 的半套擋下)**:市價佇列 0 價檔位會打穿
  (CLAUDE.md §8 2026-07-31 條;OrderBook 已改 `_best_limit_price` 思路,DepthBar 只服務
  期貨面尚未觀測到 0 價檔位,屬潛伏不一致)。
- [x] ~~**[behavior] CandleChart 滾輪 useEffect deps 缺 dimW/dimH**~~ **2026-08-03 結案
  (M7,c420481):spec review S-1 推翻 R-4 —— dimW = DIMS.width 模組常數、dimH 不參與
  錨點,無可觀察 bug;deps 已補為 🔵 hygiene**。
- [x] ~~**[behavior] TickTape**:`limit` 切股不歸零 + 每 render reverse~~ **2026-08-03
  修畢(M8,354fc6b key={code} + 68577a0 🔵 reverse useMemo)**。
- [x] **[behavior] 後端 payload 死欄位****→ 2026-08-03 修畢(M3,3a7cf27+a9708ba):
  六欄移除、cum_inner/cum_outer 內部累加連帶清除;y_close_milli parse 鏈刻意保留
  (除權息判別唯一來源,S-9);names.count/bars.code,tf 維持公開**:
  `snapshot.stkfut_prod`(stock_engine 每 snapshot 算)、`meta.y_close`、
  `cum_inner`/`cum_outer`、`snapshot.tc4`/`backfilling`。清除屬 wire 契約改動 → /mod;
  `names.count` / `bars.code,tf` 為刻意公開 API 表面,不清。
- [x] ~~**[behavior] `_resub_task` 不進 `_tasks`,close() 不取消它**~~ **2026-08-03 修畢
  (M2,1aaa5eb):resub task 併入 `_tasks`(覆寫失參照的同類洩漏一併解)**。
- [x] **[behavior] useStockNames 錯誤路徑****→ 2026-08-03 修畢(M9,cdd9dbc:
  併入 parseError)**:`res.json().catch(() => ({}))` 後直接
  `body.detail?.error`,body 為合法 JSON `null` 時 TypeError 逸出 queryFn(錯誤訊息變
  TypeError 文字)— 與 `lib/api-error.ts` parseError 產出不同,Track A4 因此跳過;
  修掉即可併入 parseError。
- [x] ~~**範圍外重複遺留**(本輪只收個股頁):parseError 同鏈現況 = `lib/api-error.ts` 共用版
  + `useSeries.ts:5` 自有版(2026-08-04 校正:原記載「×3(useTrade / useCapital / useSeries)」
  已失準 — useTrade.ts 隨舊 trade 路刪除、useCapital 已無 parseError);fmtPct 同字串 × 5(IndexBar / IndexPage / FuturesPage / RiverCards /
  RiverOverlay,後兩者已各自包 pct());chgPct 大盤 2 處;CandleChart「期間漲跌」
  (分母=視窗首根收盤)與「跨日漲跌」(分母=前一根收盤)是語意變體不可併 chgPct。~~
  **2026-08-04 refactor/frontend-dedupe-format 收畢**:useSeries 副本刪除、
  `parseCapitalError` 改吃新 export `parseErrorDetail`(suffix 邏輯留 useCapital);
  fmtPct 6 處(含 signal-model)/ chgPct 2 處全指回 `lib/format.ts`;CandleChart
  語意變體與 IndexBar local `fmt`(實作不同)刻意不動。
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

- [x] ~~**「訂閱失敗零重試」同結構還有三處**~~ **2026-08-05 修畢(mod/subscribe-retry-recovery)**:
  corr 照抄 futures pending-resub 形狀(log 判準:`corr subscribe %s(%s)失敗,進重試佇列` /
  `corr %s subscribe retry ok`);stock 單一對帳式常駐重試迴圈涵蓋 watchlist + rollover
  `_resubscribe_all` 失敗(新 `_failed_resubs`)+ stkfut(短鎖逐項 + 段級 break +
  round-robin 防餓死);全成功路徑 subscribe 序列不變有測試鎖。原記載三處 + review 挖出的
  rollover 重掛失敗共四條路都有復原。(原條目:本輪只修 futures_engine,鐵則 B 不順手擴):
  `corr_engine.py:129`(腿訂閱失敗「該腿停用」— 整天沒該腿的相關係數與江波圖線)、
  `stock_engine.py:164`(自選逐檔 watchlist subscribe 失敗 — 該檔沒行情,直到下次
  set_watchlist 才有機會重掛)、`stock_engine.py:226`(stkfut 個股期腿同款)。
  對照組:`index_engine` 已有 `_schedule_retry` backoff 是好樣板。若要收斂,考慮把
  futures_engine 的 pending-resub 形狀泛化(或至少 corr 腿先補 — 失效面最大)。
  〔2026-08-04 查證:三處零重試仍成立,但語意本質不同、**勿硬泛化** — corr 與
  futures 同構(一次性/無鎖),照抄 pending-resub 形狀即可;stock watchlist 是動態
  集合,重試須與 `_watchlist`/`_refs` 對帳、進 `_tasks`、拿 `_pool_lock`,且失敗檔
  被 rollback 出 `_refs`(stock_engine.py:163-170)→ 連 rollover 的
  `_resubscribe_all`(迭代 `_refs`)都接不到,比原記載更死;stkfut 重試前須驗
  `self._main` 仍同檔,否則替已不看的股票掛腿、owner refcount 洩漏〕
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
- [x] ~~**lifespan 阻塞本身**(root 條件):TXO 全鏈回補 `await` 在 yield 前,啟動窗常態
  數十秒~分鐘級,期間整個 HTTP 面不可用(真實量測:fake 延遲 12s → 12.6s 才首次 200)。
  前端已能自癒,但若想根治「重啟後空窗」,得把 runtime.start 的回補段移到背景 task
  (engines 的 app.state 時序假設要全部重審)— 獨立一輪的架構工作,勿順手。~~
  **2026-08-05 修畢(mod/startup-http-window)**:整段引擎啟動序列(runtime.start +
  六段 `_boot`)搬進單一背景 task(保序),lifespan 立即 yield;同 fake 12s 延遲量測
  首次 200 = **0.037s**(原 12.6s)。窗內對外形狀 = 既有降級語意(503 NOT_READY /
  WS close / `/api/stock/names` 照常 200);新增 `/api/ready` readiness probe
  (`{ready, error}`);TXO source start 失敗改「txo 面降級不炸 server」;activate 交接
  重入 guard(select during handover → 503 `HANDOVER_BUSY`,連舊的
  select-during-rollover 並發洞一起關);關機中斷 boot 有 CancelledError 清理協定。
  測試側 `BootedClient`/`wait_boot`(tests/helpers/boot.py)取代裸 TestClient(進
  context = 等到 boot 完成,語意同舊)。**prod 自然重啟後待目視**:啟動窗降級形狀 +
  `/api/ready` 翻轉;窗內 `/api/capital/status` 回 disabled(組態語意誤讀窗,10s 自癒)
  屬預期。
- [ ] **`test_index_routes::test_ws_streams_index_payload` 既有 flake 窗被 boot 背景化
  略微放寬**(2026-08-05 觀測一次,全套 ×3 + 單檔 ×3 重跑皆綠):index 引擎 boot 回補設
  `_dirty` 後 `_broadcast_loop` 會推一則 `p=None` payload,ws client 若在該 flush 前
  註冊就收到它當首則。master 本就有同一 race,靠時序運氣繞過。修法方向:測試改吃「第一
  則非 None 的 payload」或 engine 對 `p=None` 的首推抑制;修時勿加 sleep 掩蓋。
  〔2026-08-06 R4 輪加證:全套又目擊 3 次(Task 2/7/8 各一,單檔與重跑皆綠),
  另一 implementer 定位到第二觸發路徑 — 牆鐘落在 09:00–13:25 時 watchdog 分支把
  `stale` 翻真 → `_dirty` → 搶在測試 quote 前 publish `p=None`。重現率已高到
  幾乎每次全套必中一次,建議升優先度處理。〕
- [ ] **個股頁現價旁加漲跌額(絕對點數)**:本輪(mod/stock-price-prominence)只放大字級,
  % 旁沒有漲跌額;要加時連同 fmtPct 慣例一起看(2026-08-04 change-spec out of scope)。
- [ ] **三頁現價字級是否統一**:個股頁現價已改 text-3xl,期貨頁 FuturesPage.tsx L54 仍
  text-lg、指數頁 IndexPage.tsx L178 仍 text-2xl;是否統一由獨立決策,不順手改
  (2026-08-04 change-spec-review P2-4)。

## 2026-08-04(asyncio-socket-send-warning 收尾留尾巴)

- [x] ~~WS 突斷整合覆蓋只有 `/ws/txo-pnl` 一路:broadcaster 路由要進 parametrize 需 fake source 收斂 tests/helpers/ + 顯式佈線~~ **2026-08-04 chore/ws-test-consolidation 完成**:fake source 已收斂 `tests/helpers/fake_sources.py`(FakeFutures/Index/Corr/Stock 聯集定義,8 個消費檔改 import,特化變體留原檔);突斷 parametrize 六路全上(/ws/futures /ws/index /ws/stock 端到端 pump;/ws/corr /ws/river 引擎層 `tick_once` pump — 1 Hz 廣播推不滿 asyncio 5 次門檻故不走 source 層,讀 `engine._loop` private 有註明;/ws/capital 走 app.py 注入的 broadcast 邊界),零排除路由,mutation 驗證(relay 換 send-only)六路全紅非 vacuous。
- [x] ~~prod server 啟動 log 落檔慣例不一致:00:54 的 instance 有 `logs/server-*.log`,09:26 重啟的沒有(console-only)— 這次 11:06 的 asyncio warning 差點無檔案證據可查;考慮統一啟動包裝(固定 stdout 轉存 logs/)~~ **2026-08-04 chore/server-launch-wrapper 完成**:落檔搬進 `python -m copycat.server` 本體(`__main__._setup_prod_log` 把 sys.stdout/stderr tee 到 `logs/server-YYYYMMDD-HHMM.log`,每筆 write 即 flush、寫壞降級 console-only)— run.ps1 與手動起 server 同享,不再靠 operator 記得重導向。
- [ ] `relay` 收尾假設 uvicorn sansio 的 `writable` 恆 set(無 pause_writing → send_json 非懸掛點、cancel 必打進 generator):若未來 uvicorn 加回 write flow control,「懸在 send_json 的 generator 遺棄」路徑變可達,`_consume_ws_task` docstring 的「取消同時關閉 generator」不再成立(review async lens 附註)

## 2026-08-04(remove-tc4-trade-path 收尾沉澱)

- [ ] `copycat/live/trade_models.py` 瘦身候選:僅 `BrokerRejectedError` 與 `mask_account` 有 production consumer(皆 `capital/client.py`;2026-08-04 增量 review F5 全符號盤點)— 其餘全數零引用:`OrderRequest` / `millipts_from_price_str` / `price_str_from_millipts` / `to_neworder_param` / `TouchanceDownError` / `AccountInfo` / `OrderReport` / `parse_accounts` / `parse_execution_report` / `parse_fill_report` / `classify_is_sim`。動它時 `tests/live/test_trade_models.py` 對應測試同步縮,且先 grep 確認 capital 端沒長出新引用。
- [ ] `frontend/src/lib/trade-text.ts` 瘦身候選(review F3):`TRADE_ERROR_TEXT` 有 6 個無 producer 的 dead key(TOUCHANCE_DOWN / TRADE_NOT_READY / LIVE_DISABLED / CONFIRM_REQUIRED / PREVIEW_EXPIRED / SYMBOL_NOT_ALLOWED,一對一對應已刪的 _TRADE_ERROR_MAP)+ `orderStatusText` / `orderSideText` 已 test-only(唯一 production consumer 是被刪的 OrdersList/OrderConfirm)。**⚠ `INVALID_ORDER` 必留**(capital_api 仍回它);`tradeErrorText` / `shortSymbol` 是 useCapital 等現行 consumer 在用,不可整檔刪。`trade-text.test.ts:7-8` 對 dead key 的斷言一併清。
- [ ] `tests/server/test_ws_disconnect.py::test_no_write_to_dead_transport` 是既有 timing flake(0.5s 收 frame 窗,全套負載下間歇紅;2026-08-04 雙跑對照:全套 1 failed/1620 → 重跑 1621 passed、單檔 6 passed)。放寬候選:時間窗改 deadline 迴圈。與 remove-tc4-trade-path 零因果。〔2026-08-05 加證:capital-position-key-kind 輪(diff 零碰 WS/transport)4 次全套 2 紅 2 綠,且**單檔重跑也紅過一次**(後續單測綠 / tests/server 全段綠 / 同檔連跑兩次綠)— 重現率比原記載高,下輪處理時當真 bug 排查(deadline 迴圈化),不要重跑掉〕
  〔2026-08-06 R3 輪再加證:worktree 全套下 ~3/5 紅(base 4/4 綠)— 隔離實證為
  **時序位移推高既有 flake 命中率**(新增 4 個 breadth route 測試改變排程;移除即恢復、
  production code 零涉入;停用連板 task 無效)。修法已驗證可行:該測試改用
  `_ws_handshake_keep_rest` + `assert rest or sock.recv(4096)` → 同組合 4/4 綠。
  優先級應再上調 — 它現在會間歇咬到每一輪的全套 gate〕
- [x] ~~下次自然重啟 prod server 時,目視 futures / corr / river 三面板有值 —— sentinel 解耦(`__main__` 顯式傳 DEFAULT_FUTURES/DEFAULT_CORR)的 real-env 確認(自動化已由 `test_main_wiring.py` 守;2026-08-04 依「盤中/夜盤不重啟」紀律未做重啟驗證)。~~ **2026-08-04 23:09 user 指示重啟驗畢**(build 7310418):futures TXF/MXF/TMF 三品全值(五檔 + resolved_contract 202608)、corr 六腿全非 stale(w60 有值,長窗待樣本累積屬預期)、river 六腿回補 491 分鐘(SXF 438,稀疏腿正常);UI 目視期貨 / 相關係數 tab 皆「即時連線中」,截圖 `.claude/mod/remove-tc4-trade-path/evidence/restart-corr-river-panel.png`。**同場首驗 server-launch-wrapper 的 log 落檔**:`logs/server-20260804-2309.log` 自動生成,banner / 引擎 / uvicorn access 全入檔。另觀測:23:09 群益登入回 `SK_ERROR_TELNET_LOGINSERVER_FAIL`(降級 status=error,其餘不受影響)— 疑似群益夜間維護窗,白天重啟再看。

## 2026-08-04(ws-test-consolidation 收尾沉澱)

- [ ] `test_no_write_to_dead_transport` 其實有**兩個**獨立 flake 源(本輪實測):(a) 既知的 0.5s 固定收 frame 窗(全套負載下漏窗);(b) 新發現 — `_ws_handshake` 讀到 `\r\n\r\n` 即停,101 回應與 server 第一則 frame 落同一 TCP segment 時該 frame 被握手緩衝吞掉 → `sock.recv` 等到 5s timeout,實測 6 跑掛 1(≈17%)。新測試已用 `_ws_handshake_keep_rest`(回傳殘留位元組)免疫;修既有測試需動 `assert sock.recv(4096)` 斷言,依紀律留待專輪 — 修時兩個源一起收(窗改 deadline 迴圈 + 換 keep_rest)。
- [ ] `tests/conftest.py` 只中和 CAPITAL_* 與 DISCORD_BOT_TOKEN,**沒中和 `DISCORD_WEBHOOK_URL`** — 任何建 SignalHub 的測試(如 /ws/stock 整合路)在開發機 shell / .env 有該值時會真的對外發 Discord 訊息。本輪在該 case builder 內單點 monkeypatch 擋掉;建議升級成 conftest 全域中和(與既有 delenv CAPITAL_* 同型)。
- [ ] corr/river 兩路突斷測試讀 `engine._loop` private(engine 無公開 loop 取用面;repo 已有 `broadcaster._clients` 先例):若日後 `create_app` 透出 `corr_tick_secs`(現寫死 1.0 不經參數),兩路可改回純 source-driven 端到端 pump,一併移除 private 讀取。

## 2026-08-04(subscribe-retry-recovery 收尾沉澱)

- [ ] corr 腿重試成功時的補分鐘是 **best-effort**:`_schedule_backfill` 在 inflight 時是丟棄
  不是排隊(`corr_engine.py:298-302`),重試恰好撞上 start() 那次回補未完 → 失敗窗內的
  江波圖分鐘就此缺一段(本輪只加一行 info 留痕)。要真正補齊得讓 `_schedule_backfill`
  可排隊,與上面第 212 行「覆寫 `_backfill_task` 參照的孤兒 task」同一次收(同一個函式)。
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
- [ ] **MarketChart 無資料時 y-tick 全 0 → React duplicate key console error**(Phase 6
  fixture 實測 3.5 次/秒;prod 有真資料不觸發):`key={t.priceMilli}` 改帶 index 即根除。
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

- [x] **XR-3:SignalHub 深綁 stock engine** — **2026-08-12 已根治**(mod/signal-hub-decouple,
  PR #43):bus 上提 app 層 stock_ws、trade_date 牆鐘 fallback、daily_bars stub、
  gate 只看 hub;TC4 不在時廣度鏈(today/WS/jsonl)全活。衍生留尾:前端
  `tc4="down"` 文案「恢復後自動回補」在無 engine 模式不成立(engine 只在 boot 建,
  需重啟 server)→ 前端文案分態,見下方 2026-08-12 節。
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
- [x] ~~**XR-5:08:55-09:00 試撮窗四區塊 gate 互相矛盾**(家數/rows/連板收試撮價,
  連板判式在試撮漲停上照 +1;騰落線與事件流不收;前端 09:01 才開輪詢 → 試撮
  快照殘留畫面到 09:01)。要不要排除/標示試撮窗 = 產品語意,待 user 拍板。~~
  **2026-08-12 grilling 拍板「排除」並出貨**:試撮價可被假單操縱、無決策價值 →
  `breadth_config` 預設 `window_start` 08:55→09:00,試撮價不進系統,四區塊自動
  一致;前端不動(開盤前顯示昨日收盤資料是誠實狀態,非殘影)。收尾 review C-2 追加
  `_apply` 資料時刻 gate([08:30,09:00) 整輪不採用):窗只擋「取數時刻」,09:00 整
  首輪可能拿到上游未刷新的試撮快照、盤前重啟窗外首圈同款 —— 兩條縫一起堵死。
- [ ] **XR-6:後端 `_in_window` 無星期維度**,週末照 10s 打 FinMind(~1,710 次/日,
  配額安全)。加星期 gate 有週六補市日非對稱風險(rollover 教訓把週六補市當真
  場景),暫維持現狀。
- [ ] **XR-7:開盤首輪廣度事件逐則 WS frame → 時間軸 N 則各自重排重繪**(漲停潮
  日 ~200 則擠在 09:01 一秒)。未 profile 先不動;若真 jank,候選 = hub 批次
  publish 或前端 buffer 一個 frame 再 setState。
- [ ] **FE-4:SectorSection 不顯示 trade_date/as_of**(sector-model 有欄位,UI 丟
  掉;唯一日期戳來自 BreadthBand 的 `_trade_date`,兩者可脫鉤)。加 stamp 是 UI
  增項,待四輪 user 過目時一併拍板。
- [x] ~~**FE-7:產業列每 10s 依 avg 重排,展開/鑽取中的區塊在游標下位移**(誤點成員
  = setStockCode + set_main,代價不只看錯)。候選 = 鑽取中凍結排序;UX 拍板項。~~
  **2026-08-12 grilling 拍板並出貨**:任何展開/鑽取期間凍結排序(產業/子產業/成員
  三層,數字照更新)+「排序已凍結」標籤,全收合恢復即時重排;凍結判定看「畫面上
  真的展開著什麼」(展開目標從清單消失不會無限凍結)。
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

- [x] ~~**P1:`_resub_loop` 只接 ConnectionError**(futures_engine.py:155)— 壞電文
  殺死復原路徑且零 log;同顆例外從 close() 的 `await resub` 重拋 → `source.close()`
  跳過 → KeepAlive 洩漏。~~ **2026-08-12 修畢(fix/futures-resub-recovery)**:照 corr
  形狀 `_resub_round` + except Exception 續行;close suppress 放寬到 Exception。
- [x] ~~**P1:close() 不等 in-flight `to_thread`**(futures_engine.py:162)— orphan
  thread 跨過 source.close() 後 subscribe → 重建 TC4 連線無人 Disconnect。~~
  **2026-08-12 修畢(同輪)**:照 stock `_EngineClosing` 縮窗(worker 先查
  `_loop is None`);`attempts <= n+1` 允許值改鎖「close 後零新 subscribe」。
  縮窗殘餘 race 的根治 = 下方 P2-5 tc4 `_ensure_connected` 原子化(獨立 /mod)。
- [x] ~~**P1:`_check_stale` 重連掉訂閱零復原零覆蓋**(tc4.py:678-682)。~~
  **2026-08-12 修畢(同輪)**:futures engine 接 on_reconnect 全品回填
  `_pending_subs` 對帳(UNSUB→SUB 冪等,重掛活品無害);tc4 重掛失敗補 grep 判準
  warning `TC4 reconnect resubscribe %s failed`;舊 repro.md 措辭已 amendment 更正。
- [x] ~~P2:重試成功後 HOT + leaf 雙訂閱(`_leaf_fed` 跨日每天複製)。~~
  **2026-08-12 修畢(同輪)**:重試成功處 `_leaf_fed.discard(product)`;當日既存
  雙訂閱接受(leaf 無退訂路、兩邊值相同),`__init__` 過寬註解一併更正。
- [x] ~~P2:useStockNames 永久錯誤態每 3s 無限輪詢不退避(useStockNames.ts:37);
  error 態無 consumer 在讀,註解與現實不符。~~ **2026-08-11 修畢
  (mod/stock-names-error-poll-stop):拍板「停止」不是退避 — 連續失敗
  20 輪(≈77s;每輪 = 1s backoff + 3s interval)即停,復原後門 = 分頁
  visibilitychange 或重整(v5 focusManager 不聽純 window focus,review 抓到並鎖測試);
  retry 註解改述現實(error 無 consumer)。**
- [x] ~~P2:test_futures_engine 兩條收斂不變式 mutant 存活(:405 改
  `assert engine._resub_task is None` 照 corr 版;收斂後補 pending 空 + task done)。~~
  **2026-08-12 修畢(同輪)**:兩斷言照 corr 版改寫,M1/M2 mutant 抽驗紅後還原綠
  ([lock] commit body 記 mutation-verified)。
- [x] ~~P2:useStockNames 測試不鎖輪詢節奏與停止條件(interval 改 1ms / 停止條件拿掉
  皆全綠)— 成功案 sleep 3.5s 斷言 fetch 次數不增。~~ **2026-08-11 修畢(同上輪):
  白盒 literal 3000 鎖節奏 + 上限停止;成功案改 fake-timer 推進 10s 斷言不增
  (決定性等價,免 wall-clock);雙 mutation 抽驗紅後還原綠。**
- [ ] P2(共用層,獨立 /mod):tc4 `_ensure_connected` 無鎖 check-then-act ×
  `_check_stale` 重連 race → 雙 QuoteAPI 落敗者永不 Disconnect;本輪 diff 讓觸發窗
  系統性放大。修 = check+建立+發布以 `_api_lock` 原子化 + `_stop` 早退,
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
- [ ] **P2:WatchlistSidebar row div 無鍵盤路徑**(既存;doctor
  no-static-element-interactions :298):`wl-row-*` div onClick 選股無 role/tabIndex/
  鍵盤 handler。要嘛換 button / 補 key handler,要嘛確認選股有其他鍵盤入口後 ignore。
- [ ] **P2:自選列組內排序無鍵盤路徑**(既存):拖拉握把是唯一排序入口(pointer
  only;aria-hidden 化後對 AT 不可見)。管理 Dialog 只有移組/移除,無排序。
  補鍵盤排序入口(如 Dialog 內上移/下移鈕)列排期。
