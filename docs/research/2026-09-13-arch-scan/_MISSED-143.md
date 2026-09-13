### 驗證階段補抓的漏網(143 條,列出全部標題 + 為何重要)

-- B01-tc4-ingress
   * 單 reader 重構會靜默打斷 `_last_msg` —— 安靜的 session 會每 30 秒進一次重連迴圈  @copycat/live/tc4.py:1249(`self._last_msg = time.monotoni
     B01-01 的 risk 段列了「`_last_push` / `_sub_at` / `_heal_*` 記帳必須由 reader 分派後照舊呼叫」,但**漏了 `_last_msg`**,而它才是那個會炸的。`_last_msg` 今天由**每一則**訊息推進 —— 包含 PING、包含四條「不關我的事」的外來 tick。TXO session 在夜盤、corr session 在週末,自家 symbol 本來
   * `StockMeta` 每則訊息重建一次,八個欄位全是「全日常數」——2.71 µs/則,比 B01-04 的修法收益大 3.7 倍  @copycat/live/stock_models.py:194-203(`parse_stock_realti
     `StockMeta` 的八個欄位 —— `SecurityName` / `ReferencePrice` / `UpperLimitPrice` / `LowerLimitPrice` / `YClosedPrice` / `YTradeVolume` / `OpenTime` / `CloseTime` —— **當日全部是常數**(參考價、漲跌停、昨收、昨量、開收盤時刻都不會盤中變)。但它們每一則 REALT
   * B01-05 的最小改動 (b) 其實可以直接套在五條 `_listen_loop` 上,不必等任何重構  @copycat/live/tc4.py:1245(`raw = (sock.recv()[:-1]).decod
     掃描把「decode 之前先用 bytes 判」只寫成 KeepAlive 的最小改動 (b),沒發現**同一招在 listener 上更值錢**。五條 listener 今天對**每一則**訊息都先 `.decode("utf-8")` 建一個 str,然後 `_realtime_msg` 才做 `json.loads` 並在 `msg.get("DataType") != "REALTIME"` 時丟掉 —— P
   * 這條 finding(五條 session 重複解碼)2026-08-19 就被記過一次,但沒有進 triage,所以一年下來零進展  @docs/research/2026-08-19-browser-crash-scan.md 的 P2 表第 1
     B01-01 不是新發現,是**復發**:那份掃描的 P2 表第 12 列逐字寫「`copycat/live/tc4.py:886` | 五個 source 各開 wildcard SUB,全市場推播 JSON 解析五次 | 後端 CPU」。我 grep 過 `docs/next-time.md` 與 `docs/superpowers/specs/2026-08-28-next-time-triage.md`,**
   * 整個 ingress 沒有任何吞吐 / 積壓計量,所以所有 CPU% 宣稱都建立在推估上  @copycat/live/tc4.py:1244-1250(listener 迴圈,無計數)、copycat/s
     整份 B01 報告裡每一條的 impact 都乘上「日均 ~200 則/s、開盤峰值 1500+/s」,而這兩個數字**一個都沒被量過**。我試著回推:唯一的規模證據 `dropped_foreign_ticks` 是**兩次 rollover 之間**的計數(`ChainAggregator.reset()` 會 `self.totals = Totals()`,09-11 那份 log 裡 15:00 與 05:
-- B02-server-core
   * Windows 預設 timer 精度(15.6 ms)讓所有『定時』路徑天生帶 ~12 ms 抖動 —— 一行 timeBeginPeriod(1) 可壓到 0.7 ms  @copycat/server/__main__.py:193(uvicorn.run 之前)/ 影響 engin
     這是本區塊 CP 值最高、也最被完全漏掉的一條。整份掃描花很多篇幅在『某段程式碼在 loop 上花 11–58 ms』,但沒人量過這台機器的 loop **本來就有多鈍**。我實測閒置 loop 的 asyncio.sleep(0.05) 超出量:min 9.11 / p50 12.43 / p95 14.11 / max 14.17 ms —— 也就是說每一個定時器平均遲到 12 ms。加一行 ctypes.win
   * corr.state() 在零 WS 訂閱時照樣每秒算 13.7 ms —— 一個 client 計數判斷就能把常態成本歸零  @copycat/server/corr_engine.py:325-327(tick_once 尾段)+ cop
     B02-04 把修法全押在『改算式 / 引 numpy』,但漏了一個零數值風險、零相依、五行就能寫完的前置:`tick_once` 的最後是 `if self._broadcast is not None: self._broadcast(self.state())`,而 `_broadcast` 在 boot 就綁上 WsBroadcaster.publish 了 —— 它跟『有沒有人在看江波圖 / 相關係數面板』
   * boot 耗時的 prod 實測資料就在 repo 的 logs/ 裡,掃描 agent 說『我沒有 prod log』  @logs/server-*.log(grep 「boot 序列結束」);逐段拆解見 logs/server-20
     B02-09 的整條 finding 建立在『影響量級未知』之上,並據此給了 effort L 的 DAG 重構建議。實際資料是:最近 10 次啟動 = 10.1 / 11.7 / 15.6 / 20.3 / 11.3 / 9.8 / 34.5 / 15.2 / 11.0 / 16.3 秒,中位數 ~13 s —— 按報告自己訂的 gate(>20 s 才動),答案是**不動**。而且逐行拆出來還能看到瓶頸不在『串行
   * group-state 的成本歸因錯置:sorted() 只佔建構的 5%,而序列化(更大的一半)沒有任何建構側快取碰得到  @copycat/live/stock_state.py:200-219(_minutes_payload)/ :
     B02-02 的首選修法(快取已排序 list、把 O(n log n) 降成 O(1) 攤銷)瞄準的是錯的東西,照做會做完發現沒省到。我把 32 檔那一格拆開量:sorted(minutes 270 項) = 0.0074 ms,建 270 個 wire dict = 0.0845 ms,vp = 0.0588 ms —— 排序佔 5%。真正該快取的是**已收盤分鐘的 wire dict 本身**(收盤後不再變),
   * 新增具名 ThreadPoolExecutor 有『行程退不掉』的隱藏代價,B02-01 的風險段只提到關機預算不等式  @建議新增的 copycat/server/pools.py(尚不存在)vs copycat/server/shu
     `concurrent.futures.ThreadPoolExecutor` 的 worker 是 **non-daemon**,直譯器退出時 `concurrent.futures.thread._python_exit` 會 join 全部 worker;而 `shutdown(wait=False, cancel_futures=True)` **只丟得掉佇列中還沒開跑的**,正在跑的 TC4 執行緒照樣被 
-- B03-ws-broadcast
   * signal / status / watchlist_changed 與 ticks 共用同一條 stock_ws queue,而這三種是一次性事件 —— 丟包時『丟最舊』丟掉的可能是一則交  @C:/side-project/copycat/copycat/server/ws.py:70-80(丟包政策)
     掃描在 B03-05 明文把丟包政策分成『ticks 不自足』與『其餘完全成立』兩類,但 `/ws/stock` 這一條 queue 上至少還有三種一次性事件。其中 `signal` 最嚴重:訊號列在 rail 上有 5 分鐘 REST baseline(`/api/stock/signals/today`)可以補回來,**但 toast / 嗶聲 / 桌面通知只走 WS bus** —— `useSignalAle
   * /api/stock/group-state 才是這一層真正的同步阻斷(150 檔實測 ~33 ms),而且它是每 60 秒固定發生,不是丟包時才發生 —— 掃描把 critical 掛在 3  @C:/side-project/copycat/copycat/server/app.py:1708-1732(
     掃描的 B03-01 把『REST 在 event loop 上同步序列化』這個**正確的擔憂**掛在了錯的路由上(主圖 tape,真值 3–4 ms、事件驅動)。實際上同一個機制在 group-state 上大一個量級、而且是**週期性的**:群組檢視每 60 s 對整組(可到 150 檔,盤前篩選群組本身就 ~60 檔)打一發 batch,payload 含每檔的 minutes(270 格)+ vp(數百檔位)
   * 整個 B03 區塊的 CPU 總量約 2 ms/s(單核 0.2%)—— 這一層沒有吞吐量問題,只有延遲尖峰與一次性訊息遺失兩種風險,報告的 severity 分佈把兩者混在一起了  @C:/side-project/copycat/copycat/server/ws.py 全檔 + C:/sid
     我把每一類訊息實測後加總:ticks 10/s × ~130 us + watchlist_quote 80/s × 4.1 us + book ~50/s × 4.6 us + stkfut ~10/s × 4.6 us + relay 框架 ~1.1 us/則 ≈ **2.1 ms/s**。報告裡 B03-02(high)、B03-03(high)、B03-04(medium)、B03-06(medium)、B0
-- B04-stock-engine
   * listener 執行緒的 json.loads 每則 6.56 µs,在 DataType 過濾之前,且因 GIL 直接與 event loop 搶 CPU  @copycat/live/tc4.py:1190-1211(_realtime_msg)+ :1226-1252
     掃描 agent 的區塊地圖提到了 json.loads,但 20 條 finding 沒有一條量它,整份報告把 listener thread 當成免費。實測一則真實 REALTIME 電文(905 bytes):decode('utf-8') 0.317 µs + find(':') 0.021 µs + json.loads **6.560 µs** + _note_push 指紋 tuple 0.399 µs
   * to_milli = int(Decimal(raw)*1000),每則推播呼叫約 15 次 ≈ 3–4 µs,是 B04-02 + B04-03 的共同真因  @copycat/tc4common.py:16-29(to_milli_units)← copycat/live
     B04-02(meta 重建)與 B04-03(_parse_levels)各自提了一個 effort M/S、有契約風險的修法,去追它們各自 2.7 µs / 0.8 µs 的收益 —— 但兩者的共同成本源頭是同一支函式。實測 `to_milli_units('2380')` = 0.2908 µs,其中 `int(Decimal('2380')*1000)` 佔 0.2642 µs;一則 REALTIME 呼叫它
   * GC:自動停頓只有 ~2 ms(3.13 incremental),但任何一次強制 gc.collect() 是 99–370 ms 的 loop 全凍;boot 後 gc.freeze()   @程序全域(無對應程式碼落點);相關堆的來源 = copycat/live/stock_state.py:19/:
     B04-06 把 tick 物件陣列講成記憶體問題卻標 on_hot_path=false,沒有人回答『這些常駐物件對延遲做了什麼』。我實測了:在 150 檔 × 6,000 tick(900k 常駐 StockTick)的堆上,**自動** GC 的最壞單次停頓是 gen1 的 2.25 ms、gen0 中位 0.1 ms,15 萬筆留存 tick 期間 GC 總停頓 17.5 ms / 160 ms —— Pyt
   * 單一 event loop 上「下單決策面」與「150 張卡片輪詢」零優先序分離 —— 這是本區塊 20 條 finding 的共同上游  @copycat/server/app.py(lifespan 單一 loop)+ stock_engine.py
     報告把每個症狀各列一條(B04-04 的 60 s 尖峰、B04-15 的開盤重放、B04-07 的 book 直發、B04-14 的 loop-only 約束),卻沒有把它們寫成同一件事:**使用者要按下去的那個閃電梯,和 150 張卡片的 60 s 全量重送、和開盤的回補重放、和訊號層、和群益下單回報,全部排在同一條執行緒的同一個 FIFO 上,沒有任何優先序**。以我實測的數字,主圖五檔更新在最壞情況下要排在一
   * orjson 的「stdlib-only 第一次破例」framing 不成立 —— live server 早就有三個第三方 runtime 相依  @C:/side-project/copycat/pyproject.toml:6-12
     工具建議把 orjson 的主要成本寫成「這是 pyproject.toml `dependencies = []` 這條 stdlib-only 哲學的**第一次破例**,要 user 明確拍板」。實查:`dependencies = []` 只涵蓋 **core package**;`[project.optional-dependencies]` 已經有 `live = ["fastapi>=0.115", "
-- B05-live-state
   * 五條 TC4 listener 各自 json.loads 同一則電文,其中四條再把不屬於自己的 quote 丟過 thread 邊界才丟棄(B05-09 的反向,量級大一個數量級)  @copycat/live/tc4.py:1189-1212(_realtime_msg,五個 source 共用
     prod 跑五條獨立 TC4 session(app.py:406/416/428/442 + TXO,__main__ docstring「真 source 四路 sentinel」),每條 listener 都 `sock.setsockopt_string(zmq.SUBSCRIBE, "")`(tc4.py:1241),而 .claude/skills/tc4-market-facts/SKILL.md 逐字
   * 老年代 GC 停頓:150 檔 × 6000 tick 常駐讓受追蹤物件達 91 萬,成長期實測最大單次停頓 110 ms(全庫無人 import gc)  @copycat/live/stock_state.py:19(_TICKS_MAXLEN = 20_000)、4
     這是本區塊**最大的單次 event loop 停頓**,而且不需要任何人打開群組檢視、不需要任何請求 —— 它在 tick 流自己把老年代撐大的過程中自動發生。掃描 agent 把 B05-07 的記憶體議題定位成「RSS 吃數百 MB」(對 Windows 桌面機不痛不癢),完全沒連到 GC 停頓,因此也就沒有把 columnar(array)那條從「激進版 L」重新定位成「根治 110 ms 停頓」的唯一解 —
   * StockDayState.apply_backfill 在 event loop 上同步重放整日 tick,6000 筆 = 9.9 ms、20000 筆 = 32.4 ms;且入列點有六個  @copycat/server/stock_engine.py:1688 `state.apply_backfil
     掃描 agent 把 `snapshot(tape=True)` 列為「低頻但集中在系統最忙時」的停頓來源,卻漏了同一份 ticks 的**寫入側**:回補的網路與解析確實走 `asyncio.to_thread`(stock_engine.py:1589),但 `apply_backfill` 的重放 —— reset + 逐筆 `_apply`(deque append、minutes setdefault、VP
   * 區塊地圖的「parse_stock_realtime 24.9 µs,每則都跑(含純簿更新)」把總帳灌水約 2 倍  @copycat/live/stock_models.py:188-235(早退在 218-219,_taipei
     這個數字是整份報告「總帳 25–36 ms/s」與多條 finding(尤其 B05-04)的分母。純簿更新在 218 行就 `return None, book, meta`,不走 _taipei_time(strptime + 兩個 datetime/timedelta 物件)、不走 _best_limit_price ×2、不建 StockTick —— 而區塊地圖自己說「總訊息數更高,估 500–1500/s
-- B06-signals
   * on_book 可用 latch 旗標**證明性等價**地整條短路 —— 比 B06-04 的 lazy key 更省、比 B06-06 的「簿有沒有變」更安全  @copycat/live/signal_state.py:334-362(evaluate_book)+ cop
     這是整個 B06 區塊投報率最高的一筆,而掃描 agent 提了兩條較差的替代方案(lazy strftime / 簿變動旗標)卻沒看到它。 `evaluate_book` 的整個函式體是一個雙向迴圈,每個方向有三道 `continue`:`354 if limit_milli is None or not reopened: continue`、`356 if not self._latch.get((code, 
   * **停用的** CDP 規則仍付全額狀態推進 —— basis 分發不看 enabled,實測 2.1 us/tick 純死工且無任何消費者  @copycat/server/signal_hub.py:985-988(_distribute)與 :523(
     `_distribute` 的過濾條件只有 `if slot.rule["kind"] != "cdp_cross": continue` —— **沒有檢查 `rule["enabled"]`**,`_seed_slot`(523)同形。所以一條被使用者停用的 CDP 規則,它的 detector 照樣拿到 basis,`evaluate` 照樣每 tick 跑 `_advance_rearm`(對 5 條線迴圈 
   * B06-07 的記憶體半邊 running sum 修不掉 —— 掃描 agent 的「這個問題直接消失」只對 CPU 成立  @copycat/live/signal_state.py:318-323 + copycat/signal_ru
     B06-07 的 fix 欄逐字寫「做 B06-01 的 running sum,這個問題直接消失(O(1) 與窗長無關)」。這會誤導施工:running sum 只消掉 `sum()` 的 CPU,deque 本身仍然依 `surge_window_secs` 裝滿。 30 條 `window_secs=3600` 的 vol_burst 規則,對**單一**高頻檔(5 tick/s)= 30 × 18,000 筆
   * 關機預算:_CLOSE_FLUSH_TIMEOUT(5.0 s)恰等於 shutdown_budget.LIFESPAN_SLACK_SECS(5.0 s),而那個 slack 還要涵蓋另外兩  @copycat/server/signal_hub.py:109, 551-576 + copycat/serv
     B06-08 建議給訊號落檔加專屬 executor 並「close() 的關機序列要一起收」,但沒查 CLAUDE.md §4「關機預算三方同源」這條契約,所以沒看到預算已經是緊的。 `shutdown_budget.py` 的 `LIFESPAN_SLACK_SECS = 5.0` 註解逐字寫「TC4 之外的段(crosscheck cancel / breadth / **signals 的 bot.close
   * 兩筆零風險的微小浪費,應併入 B06-01 / B06-04 的同一次編輯  @copycat/live/signal_state.py:649-650 + copycat/server/si
     單獨都不值得開 ticket,但它們與已排程的改動在同一個函式/同一行附近,不順手收就要再開一次編輯窗。 (1) `_eval_volume` 每 tick 重算當日 09:00 的 epoch 秒:`open_dt = now.replace(hour=9, minute=0, second=0, microsecond=0)` 後接 `_mono(open_dt)` —— 這是**當日常數**,我實測 0.333
   * 掃描 agent 的所有熱路徑數字都建立在一個未經驗證的負載假設上(合成 5 tick/s / 窗長 1501),而 repo 裡沒有任何 prod 側的 tick / quote 率量測  @scratchpad/arch-scan/bench2.py(合成序列)vs. copycat/server/s
     這是比任何單一 finding 都重要的方法論缺口,而報告只把它寫成 B06-13 的一條 medium。 bench2.py 生成的是「單檔、固定 0.2 s 間隔、連續 4800 秒」的 tick 序列 → 窗長恆為 1501。而報告自己在「量級實證」段寫「全日 ~7 tick/s 均值」(80 檔合計)—— 換算成 per-code 是 0.0875 tick/s,窗長約 **26**。兩者差 58 倍,而 `
-- B07-other-engines
   * `dict(leg_series)` 可以整個拿掉(不必 array、不必增量矩)—— 11 條序列恆等長且逐格對齊  @copycat/live/corr_state.py:62-78(push / _evict)與 corr_st
     `push` 對 `self._series.items()` 的**每一條** series 同拍 append、`_evict` 對所有 series 套同一個 cutoff pop、cap 裁切條件也相同,而 `_series` 的鍵在建構後不再變動 → 任何時刻 11 條 deque 恆等長、第 i 格的 ts 恆相同。因此 `leg_by_ts.get(ts)` 完全等價於 `zip(base_series
   * `await asyncio.to_thread(self._state.correlations, now)` 是 B07-01 的低風險緩解,而且在這裡其實是安全的  @copycat/server/corr_engine.py:223-230(_run)與 300-324(tic
     掃描在 B07-14 用 GIL 論證擋掉『把工作搬去別的執行緒』,但那個論證對 25 µs 的 parse 成立、對 12 ms 的整批計算不成立:loop 上的 callback 不可搶佔,worker thread 上的同樣工作每 sys.setswitchinterval(預設 5 ms)讓出一次 GIL。把 correlations() 丟 to_thread 不會減少總 CPU,但會把 tick 解析與 
   * `mid_from_book` 沒有『0 = 市價單佇列』的過濾,是一條沒有測試釘住的隱性相依  @copycat/live/corr_models.py:20-28 對照 copycat/live/stock_
     corr 的中價直接取 `bids[0][0]` / `asks[0][0]`,而 `_parse_levels`(stock_models.py:171-185)**刻意保留**價格 0 的市價單佇列檔位(該檔位明文說『過濾它是消費端的事』)。tick / derive_side 那條路有 `_best_limit_price` 把 0 濾掉,corr 這條沒有。今天不出事只因為鎖漲跌停時對手側是空的 → `mid
   * B07-02 與 B07-03 互相耦合,分開做會做出一個錯的東西  @copycat/server/corr_engine.py:320-324 與 copycat/server/a
     掃描把兩條列成獨立 finding,但照 B07-02 在『沒有 client 時不算 correlations』之後,B07-03 建議的『state() 讀上一拍快取』就會端出任意舊的值 —— 沒人連著的那段時間根本沒有任何一拍算過,新連上的第一個 client 會拿到幾小時前的配對。自洽的設計只有一個:state() 內建『上一拍快取 + 過期(> 1 tick)才即時算』,廣播端直接讀快取,REST / WS
   * river delta 同樣在零 client 時照建照送,has_clients 閘要一次做完  @copycat/server/corr_engine.py:343-345(_river_tick 尾端)
     與 B07-02 完全同形(`if self._river_broadcast is not None: self._river_broadcast(self._river.delta(...))`),掃描只對 corr 提。它本身很便宜(11 鍵 dict,µs 級),提出來只是為了避免『閘』這件事分兩次開案 —— 若決定做 B07-02,順手涵蓋它;若決定不做(因為 B07-01 修完就沒必要),兩條一起否決。
-- B08-bars-overlay
   * 日 K 模式(mode === "day")的 memo 鏈同樣每 0.1 s 全穿,而 B08-04 明確把它排除在外  @frontend/src/components/stock/StockChart.tsx:184、:196-20
     `liveDay = liveOn && mode === "day" && !dailyFinal ? accum : null`(:184)—— accum 每則 ticks 打包換 identity,所以在日 K 模式、14:00 定稿界之前,`bars` memo 同樣每 0.1 s 重算(`mergeLiveDailyBar` 複製 ~120 根 + 換末根),`bars` identity 一變一樣打穿 
   * overlay 逾時後執行緒不可中斷 + 預設 ThreadPoolExecutor 無自訂上限 ⇒ 病態 TC4 下 executor 可被 overlay 吃滿,連帶卡住 bars_ran  @copycat/server/app.py:1496-1514(wait_for + 註解自承)、copycat
     B08-02 只追到 `api.lock`,沒追到執行緒池。`overlay_sem` 逾時(15 s)時 route 放掉名額讓下一檔進場,但 `asyncio.to_thread` 起的工作執行緒**中斷不了**,而 `fetch_daily_bars` 最壞要付 DK 10 s + 1K fallback 10 s(`BARS_POLL_DEADLINE = 10.0`)= 20 s > 15 s 的 rout
   * /api/stock/bars 完全沒有併發閘,而 payload 比 overlay 大兩個量級、最壞等待是它的 1.3 倍  @copycat/server/app.py:1519-1551(無 semaphore)vs app.py:14
     同一個 app 裡兩支都會打 TC4 歷史的 route,一支有 Semaphore(4) 一支一個閘都沒有 —— 而沒閘的那支單發 payload ≈ 547 KB(我實測)、最壞等待是歷史段 10 s + 當日段 10 s = 20 s(overlay 只有 15 s route 逾時),對 executor 的壓力更大。現況因為「圖牆卡片不打 K 線」而沒事,但那正是 B08-05 列的第一個觸發條件(「圖牆卡
   * B08-14 漏看:repo 已經有一條 FinMind → 本地日線的完整管線,overlay 的 CDP/MA 不需要新相依就能離開 TC4  @copycat/server/breadth_fetch.py:37、:128-140;copycat/cli.
     B08-14 的 evidence 只 grep 了 `DailyIndex` 的 import,結論是「live 路徑沒有本地歷史層」→ 直接跳到「新增 copycat/store/history.py(DuckDB 或 Parquet+pyarrow)」+「破 stdlib-only 需 user 拍板」。但 `breadth_fetch.py:37 _PRICE_DATASET = "TaiwanStockPr
   * B08-01 只算了後端記憶體,前端 TanStack Query cache 有對稱的線性成長(每換一檔分 K ≈ 1 MB JS 物件,gcTime 預設 5 分鐘)  @frontend/src/hooks/useStockBars.ts:107-120(queryKey 含 co
     `stockBarsKey(code, isDaily, days)` 以 code 入 key,每換一檔就是一份獨立 cache entry,內含 ~5,700 個 JS 物件(每個 8 欄,估 ~150–200 B → 0.9–1.1 MB/檔)。grep 全前端沒有任何 `gcTime` / `cacheTime` 設定 → TanStack Query v5 預設 5 分鐘才回收。在 m5 模式下快速點過 3
-- B09-external-io
   * MIS 櫃買快照是 24/7 無閘輪詢,頻率是報告宣稱的 ~6 倍(17,280 次/日,不是 2,940)  @copycat/server/index_engine.py:508-517(_mis_loop)、:262(s
     報告的熱路徑宣稱寫「每 5 s(09:00–13:25 窗),~2,940 次/日」,並據此算出「純握手一日累計 ~56 s」。**那個窗不存在。** `_mis_loop` 是裸的 `while True:` —— 沒有時間窗、沒有交易日閘、沒有 `_WATCH_END`(13:25 那把閘是 `_broadcast_loop` 的 stale watchdog 用的,不是 mis loop 用的)。它從 serv
   * 盤中重啟 server 會**設計上**在市場時間內跑完整輪盤前篩選(23 請求 + 21 次 ~63 ms loop 全凍)—— 比 B09-04 的 46 分鐘理論值可達得多  @copycat/screening.py::expected_target_date + copycat/ser
     B09-04 花了整條篇幅在推一個需要「23 個請求幾乎每一發都逾時一次再成功」才成立的 46 分鐘上界,卻漏掉旁邊那條**每次盤中重啟都會走**的路: `expected_target_date` 的規則是「交易日 `RUN_TIME`(08:00,含)後 = 今天」。所以交易日 **10:30 重啟 server** → `_due()` 回今天 → `tick()` → `_run_attempts(today
   * streak 的每日重抓有一個 ~10 行的修法,不需要 B09-01 的整個 EodStore  @copycat/server/breadth_engine.py::_compute_streaks_once(
     B09-01 把 streak(10 份)與 screen(21 份)綁成同一個 M 級 EodStore 提案,並承認它帶著「落檔寫錯 = 連板數整天錯著且零錯誤訊號」的風險。但 streak 那半根本不需要存 EOD。 `_compute_streaks_once` 每日算出的 `day_set = compute_day_limitups(rows)` 是**每日 20–40 個股號的集合**(log 實錄「4
   * oi_levels._fetch_rows 漏接 http.client.HTTPException(IncompleteRead)—— 與 breadth_fetch 2026-09-02   @copycat/server/oi_levels.py:158-175(_fetch_rows 的 except
     `breadth_fetch._get_rows` 的 except 元組裡有這麼一條,而且註解寫得很重: ```python except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e: # http.client.HTTPException 涵蓋 `IncompleteRead`(MB 級回應讀到一半斷
-- B10-capital-order
   * SendStockOrder 用 bAsyncOrder=0(同步)—— 這才是 ~70 ms 端到端裡最大的一段,而且 SKCOM 明明支援非同步  @copycat/capital/com.py:150-169(send_stock_order / send_f
     四個寫入方法全部把 bAsyncOrder 硬寫成 0,而 typelib 摘錄逐字列出 `SendStockOrder(bstrLogInID: BSTR, bAsyncOrder: VARIANT_BOOL, pAsyncOrder: STOCKORDER) -> (bstrMessage, retCode)` —— 非同步是券商 API 原生支援的。同步呼叫會把**唯一一條 COM 執行緒**整個券商往返期間占
   * 逾時的寫入命令沒有 TTL —— 會在 COM 執行緒恢復後照樣送進市場,而且佇列無上界  @copycat/capital/client.py:886-898(shield + wait_for)、cli
     `await asyncio.wait_for(asyncio.shield(fut), timeout=_WRITE_TIMEOUT_S)` 逾時後,底層 future 被 shield 保護不取消,命令 tuple 仍留在 `_cmd_q`;`_run` 取到就直接 `result = fn()` —— **沒有任何 staleness 檢查**。也就是說 10 秒前(或 COM 執行緒卡住時,可能更久)使用者放
   * 端到端延遲其實已經量得出來:511 筆審計 ts 配對給出 mean ≈ 70 ms、p99 ≈ 2 s —— 這個數字推翻了本批的優先序  @C:/side-project/copycat/data/audit/capital-*.jsonl(全 10 
     掃描宣稱『整條鏈零延遲量測』因此無法排序,但秒解析度的 pre/post 兩行已經給得出粗分布:473 組同秒、36 組跨 1 秒、1 組 2 秒、1 組 4 秒。用 P(跨秒) ≈ latency/1000 反推,平均總延遲 ≈ 70 ms,而它自己量到的純 Python 段只有 p50 ≈ 1.0 ms —— 也就是 **98.5% 的時間在 SendStockOrder + pump 那一段**,而那一段本批一
   * 所有 N 相關的量級推論都用了與 prod 差 15–60 倍的假基準(真實 N = 16–63,不是 200/1000)  @logs/server-*.log(Capital reply seq 去重)、data/audit/capit
     B10-06 / B10-07 / B10-08 / B10-16 四條 medium/low 全部以 N=200 或 N=1000 計算影響,但 prod 單一 session 的實際不同委託筆數是 16–63,單日審計行最多 154(= 77 次寫入動作)。我在同一台機器實測:store.orders() N=30 → 0.053 ms / N=63 → 0.144 ms;asdict N=30 → 0.124 
   * inline 審計的真正理由不是 0.27 ms 的檔案 IO,而是砍掉送單協程的兩次 event loop 排程往返  @copycat/capital/client.py:885(前置 to_thread)、client.py:91
     B10-01/05/14 都用「檔案 IO 多快」來論證,但真正跟 B10-15(loop 被 tick fanout 佔滿)連動的是:送單協程在一次請求裡至少有 3 個 await 點,其中 2 個是 `to_thread`(每個 = 一次 executor 提交 + 一次 `call_soon_threadsafe` 回跳 + 一次 loop 重新排程)。loop 忙時,每次重新排程都要排在已經在 ready q
   * CapitalStore._orders 永不裁剪且 clear() 零 prod caller —— O(N) 路徑的成長軸是 process uptime,不是當日筆數  @copycat/capital/store.py:145-147(_orders / _order_seq)、s
     B10-07 說「隨單日委託筆數線性惡化」,但真相更糟也更精確:`clear()` 沒有 production 呼叫者(`models.py:125-126` 逐字自承「`clear()` 零 prod caller」,`store.py:299-306` 的 docstring 也寫「不能假設聚合只有當日 —— prod 8721 跨日長跑、`_orders` 沒有 caller 會清(review 2026-08
-- B11-backtest-fade
   * optimize_rule_tp / optimize_rule_stops 才是非 wf 路徑最大的單一成本,而報告完全沒有對應 finding  @copycat/backtest/fade_optimize.py:101-132(optimize_rule_
     熱路徑清單第 4 項提到了它,但 B11-01~B11-19 十九條**沒有任何一條**以它為標的 —— 於是整份改造排序把 critical 掛在實測只佔 8% 的 exhaustive_scan 和 19% 的 combo 網格上,卻漏掉佔約 70% 的這一塊。它同時也是唯一在 wf 與非 wf **兩條路徑都會跑**的重成本(wf 下每 fold 呼叫一次 optimize_tp_for_indices)。任何
   * exhaustive_scan 的 out list 比 seen set 多吃 4 倍記憶體(~2.0 GB),B11-05 只抓到小的那一半  @copycat/backtest/search.py:152, 158-160, 167(`out: list[
     `top_n=200` 只在**最後**截斷;在那之前 `out` 會累積所有通過支持門檻的規則,每個 entry 都自帶一顆 n_rows-bit 的大整數 mask。這才是讓 exhaustive_scan 一個臂就吃 ~2.5 GB 的主因,也是 B11-09 行程平行化(8 worker)的真正天花板。修法與 B11-05 同一族(把 `out` 換成 `heapq` 維持 top-200,`seen` 整個
   * 回測與前端的手續費折數慣例相反、數值不一致(B11-03 的可驗證實例),而且成本模型是四份不是三份  @copycat/backtest/fade_simulate.py:81-83 vs copycat/backt
     B11-03 只給了「概念重疊、無一行共用」的定性說法,說服力不如一個可以當場跑出兩個不同數字的實例。這個實例同時證明:(a) 兩邊對「折數」的定義相反(回測是 1−discount,前端是 discount/10),誰改誰都不會有錯誤訊號;(b) tday 與 fade 在 backtest 內部就已經各有一份成本函式,所以 CLAUDE.md §4 那套跨語言 parity 測試的形狀應該一次覆蓋四個產生點而非兩
   * wf_test_starts 這個分支閘讓報告的多條熱路徑互斥,而最近一次真實 fade-search 走的正是被判定「不跑」的那一邊  @copycat/backtest/fade_pipeline.py(run_fade_arm 的 `if cfg
     報告把 B11-02(4,660 combo 網格,5.7 h)、B11-17(每 fold 重建 predicates)、B11-01 的「walk-forward 下再乘 fold 數」、B11-06 的 ValueError 陷阱當成同一條管線上並存的成本相加 —— 實際上它們分屬兩條**永不共存**的分支。改造計畫的第一步應該是先釘住「目標是哪一條路徑」,否則會為一條當前 config 根本不執行的程式碼做 
   * 基準量測跑在系統 Python(有 numpy 2.4.4)而非專案 .venv(乾淨 stdlib),容易把「已經裝好」誤判成事實  @pyproject.toml:`dependencies = []` + C:\side-project\cop
     報告的工具建議把「numpy 只要放 backtest extras 即可」講得像零成本,但 CLAUDE.md §1 的完工 gate(pytest -q / ruff / pyright / copycat validate)全部跑在 .venv,extras 必須真的裝進 .venv 才驗得動,而且 `copycat validate` 的 golden gate 也在同一個解譯器下 —— 這會讓「stdlib
-- B12-backtest-core-replay
   * bit_indices 有一個零相依、bit-exact、3.7–6.4x 的純 Python 修法 —— 報告直接跳到 numpy  @copycat/backtest/search.py:81-88
     B12-01 是本區塊最大成本,而報告給的唯一修法(numpy matmul)要付三筆代價:新相依(venv 目前連 numpy 都沒裝)、浮點加總順序改變 → D11 determinism 與 docs/evidence 全部要 parity 或重拍、屬 🔴 行為改動不能進純重構 commit。改用 256 項 byte 預算表展開,輸出與現況**逐位相同**(我斷言過 `f(m) == bit_indices(
   * outcome cache 的 _SIM_FIELDS 漏了 baseline 停損組三個欄位 → 改 baseline 會靜默用到過期 cache(正確性,非效能)  @copycat/backtest/config.py:106-125(_SIM_FIELDS)vs copyca
     pipeline.py:270-277 用 `cfg.baseline_s2_lookback` / `cfg.baseline_s2_buffer` / `cfg.baseline_t1300` 組出 baseline StopCombo,它直接決定 pnl['baseline'] —— 而 GA fitness、θ 曲線、三道驗證全部吃這一組。但這三個欄位**不在 _SIM_FIELDS 裡**,所以改動它們 s
   * simulate_sample 每個 combo 重算 S2 swing low,單項就比 B12-09 列的四項加總還貴  @copycat/backtest/simulate.py:112-117
     B12-09 列了 _round_trip_cost / tick_size / post slice / deque 四項並估「20-30%」,實測四項合計只有 6.6%;而它沒列的 S2 swing low(`window = bars[...]` + `min(b.low for b in window)`)實測就佔 7.5%。s2_m 只有三個相異值(5/15/30),per-sample memo 三份即可
   * run_features 把整個 universe 的 bars 全留在記憶體(~563 MB),與 B12-17『不建議全量記憶體快取』自相矛盾,且是真正的擴張天花板  @copycat/backtest/pipeline.py:106-125(per_sample)
     per_sample 對每個樣本 append (s, bars, stat, avg20, struct, t1_open),bars 整份留著給後面 11 個 θ 的迴圈用 —— 也就是 run_features **已經**是全量 bars 記憶體快取。B12-17 卻以「1-2 GB 太大」為由否決在 _load_or_simulate 做同樣的事,兩邊標準不一致,而且那個 1-2 GB 是 replay 的
   * pipeline.py:431 的 feat_rows_anchor 同樣 rank-invariant,B12-06 只抓了 θ 迴圈那半  @copycat/backtest/pipeline.py:431
     `feat_rows_anchor = [_feature_row(rows[i]) for i in test_idx]` 的 test_idx 在 :381 算好、在 rank 迴圈外,所以這一行也是每個 rank 重建一次(10 次 × 3 regime)。B12-06 的修法若只提 θ 迴圈那半,會漏掉這一段。兩處是同一個 memo 就能一起收掉,算同一筆工。
   * 報告與工具建議假設 numpy/msgspec/pyarrow/polars/orjson 已可用 —— 實際上 venv 一個都沒有  @pyproject.toml(dependencies = [];optional: live/capital/
     所有 M/L 級建議的 effort 都要加上「首次引入相依 + 決定放哪個 extras + pyright/ruff 設定 + CI/驗證鏈影響」。好消息是報告最重要的前提被我驗證為真:`pyproject.toml` 的 `dependencies = []`,而且 `grep` 確認 copycat/server 與 copycat/live **完全沒有 import copycat.backtest**,
   * 多條 finding 拿 copycat validate 當 byte-exact gate 來嚇阻改動,實際上它是帶容差的  @copycat/replay/validate.py:41-44
     B12-01 / B12-04 / B12-07 / B12-18 的 risk 段都寫「會讓 copycat validate 42 條 golden 全紅 / 全面重拍」。實際上 validate 的比對是 `_within_rel(tol=0.05)` 與 `_within_pp(tol=0.005 / 0.01 / 0.03)` —— ulp 級浮點漂移不會讓它紅。這會影響決策:如果決策者以為連小數尾都動不得
-- B13-data-io
   * B13-01 的 B 案照做會造成靜默永久丟資料 —— manifest 必須與 prices.csv 同節奏寫  @copycat/data/backfill_finmind.py:156-159
     這是唯一一條「照建議改就會壞」的項目,而且壞的方式是零錯誤訊號的永久資料缺口。現在 `_write_atomic(prices_path, rows)`(:156)與 `atomic_write_text(manifest_path, ...)`(:157)是每天成對寫的,所以 marker 與資料恆一致。若只把 prices 改成每 N 天寫、manifest 照舊每天寫,中途當掉時 manifest 已宣告那 N
   * import_neigui 尾段的 read_bars 只判 None,等價於一行 path.exists() —— 12 s → 0.16 s,零風險  @copycat/data/import_neigui.py:238-241
     `read_bars` 回 None 的唯一路徑就是 `store.py:44` 的 `if not path.exists(): return None`。這兩行只拿它的 None 性來建缺檔清單,卻為此把 11,048×2 個 12 KB JSON 完整 parse 成 Bar1K list 再丟掉。換成 `bars_path(data_dir, ...).exists()` 語意逐字相同(實測 0.55 ms 
   * 下單審計 append_audit 只有 flush() 沒有 fsync() —— B13-05 指的洞在這裡最痛,卻整條被跳過  @copycat/server/audit.py:34-37
     B13-05 花了整條篇幅講 atomic_write_text 缺 fsync,受害清單列了 watchlist / signal_rules / prices.csv(全都可重建:watchlist 有 backup 檔、prices.csv 可重抓 FinMind),卻完全沒看 §7 閘三的下單審計 —— 那是唯一「錢動了、事後必須查得到帳」且**不可重建**的一份。它走的不是 fileio,是 builtin
   * stock_watchlist._CACHE_VERSION 也是只寫不讀 —— 裝飾品是兩顆,B13-11 只抓到一顆  @copycat/stock_watchlist.py:38 與 :176(讀取側 load_watchlist 
     B13-11 把 stock_watchlist.py:38/176 列在「對照」組,暗示它屬於作廢式或遷移式。實際上 `load_watchlist` 從頭到尾沒有讀過 `_cache_version`,它靠形狀遷移(`"codes" in payload` 判 v3/v1、else v2)。所以 CLAUDE.md §4『bump 即作廢所有舊 cache』這句通則對六顆裡的**兩顆**是假的,而 watchli
   * backtest GA 搜索對同一批 1K 檔重複讀,process 內零快取 —— 這才是 read_bars 的真實放大器  @copycat/backtest/pipeline.py:286、copycat/backtest/fade_p
     B13-02 把 read_bars 的成本用「全庫 21,254 次 = 一趟」來估,但 `pipeline.py:286` 的 `read_bars` 在 `for row in rows` 內,而該函式又被 theta / combo 外層迴圈反覆呼叫;`fade_pipeline.py:444` 同形。我 grep 全庫 `lru_cache` / `bars_cache` 在 backtest/ 與 rep
   * scan_events 把同一份 52 MB prices.csv 讀兩次(DailyIndex.load 3.3 s + 自己再逐行掃 1.7 s)  @copycat/data/scan_events.py:41 與 :62
     B13-13 說「scan_events / label_events 的全表讀寫實測 < 100 ms 且每次執行只跑一次」—— 那只對 events.csv 成立。`scan_limitup_events` 第一行就 `DailyIndex.load(data_dir)`(把 prices.csv 全部 1,013,469 列讀進記憶體,實測 3,278 ms),接著 :62 又 `(data_dir / "da
   * B13-04 的因果講錯:五檔線上已經有,歷史不可回測是 TC4 TICKS 格式造成的,不是不持久化造成的  @copycat/live/stock_models.py:65-66 與 :116
     B13-04 寫『strategy.md 的硬限制「五檔深度不可回測」正是本決定的直接產物』。原始碼講的正好相反:`_Book` 的 `bids`/`asks` 是 `L0..L4` 的完整五檔(REALTIME 推播就有),而 :116 的註解逐字寫「歷史 TICKS row 只有單一 Bid/Ask 欄(不像 REALTIME 有五檔…)」。所以「既有歷史不可回測」是 TC4 歷史資料格式的限制,錄音錄不回來;能
-- X1-blocking-io
   * SignalDetector._eval_volume 每一筆成交都對 300 秒窗做一次 O(n) 求和(掃描 agent 完全漏掉,量級大於它抓的 X1-08 一個數量級)  @copycat/live/signal_state.py:658(`window_vol = sum(qty f
     這是本區塊唯一一處「成本隨單檔 tick 率平方成長」的熱路徑,而且就在 event loop 上、就在掃描 agent 拿來當 medium finding 的那 2.94 µs 旁邊。`surge_window_secs` 實查 = **300.0 秒**,窗長 ≈ 該檔 tick 率 × 300;每收一筆成交就把整條窗重新加總一次。單檔每秒成本 ≈ 9·r² µs(r = 該檔 tick/s):r=1 → 9 
   * SignalDetector.evaluate_book 每「一則行情 × 每條規則」付一次 _clock_key(),而 key 只在 latch 真的翻轉時才用得到  @copycat/live/signal_state.py:348(`key = _clock_key(now)`
     與 X1-08 完全同型的反模式(算了才早退),但頻率是它的 **1 倍/則 × 4 條規則**、單次成本 3.5 倍,而掃描 agent 抓了 X1-08 卻沒抓這條。`on_book` 不像 `on_tick` 掛在 `state.ingest(tick)` 為真的分支裡 —— 它掛在 `_handle_quote` 尾端,**每一則 REALTIME(含純簿更新、含沒有成交的那些)都走**,而純簿更新在個股盤中
   * Windows 計時器粒度(~15.6 ms)是整個 loop 既有的抖動地板 —— 它同時使 X1-12 的探針設計失效,也為所有 timer 驅動路徑設下天花板  @跨切:copycat/server/corr_engine.py:225(`await asyncio.slee
     三個後果。(1) **X1-12 提議的探針照做就是假訊號產生器**:閒置 loop 的 `sleep(0.05)` 本身就 overshoot 12 ms,和 X1-01 的真停拍無從分辨 —— 若照做,第一天就會得到「整天都有 12 ms lag」的結論並據此做錯決策(已寫進 X1-12 的 fix_soundness)。(2) **它為改造設了天花板**:`_flush_ticks` 的 0.1 s 打包、co
   * TC4 listener → event loop 的交棒沒有批次化:每一則電文一次 call_soon_threadsafe,等於一次 self-pipe 寫入 + 一次 loop 喚醒  @copycat/live/tc4.py:1226-1253 `_listen_loop` → :1213 `ha
     掃描 agent 在區塊地圖裡量了這個成本(11.5 µs)卻沒有開成 finding,而它是「改造成高效能量化系統」這個目標下**最結構性**的一項:目前每一則行情各自付一次跨執行緒喚醒,3,000 則/s 就是 3,000 次 loop 喚醒/s。後端已經有現成的批次化先例可以照抄 —— `_flush_ticks` 的 0.1 s `call_later` 打包(#180,把 50 檔開盤每秒數百則 WS 訊息
-- X2-serialization
   * 快照的 Python 端建構成本與序列化同量級 —— 所有「換序列化器」的收益上限因此被高估一倍  @copycat/live/stock_state.py:266-310(snapshot 的 ticks lis
     報告六條路徑裡把 HTTP 那一條整個歸給「pydantic-core Rust 序列化」,但送進 pydantic-core 之前,payload 本身是 Python 一個一個 dict 組出來的,而那一半跟序列化一樣貴、一樣在 event loop 上、而且**換任何序列化器都省不到**。這直接改變三件事:(a) X2-06 的 stall 數字低估 1.4–2x;(b) X2-03 列式改造的收益被低估(列式
   * asyncio.to_thread 裡的 json.loads 不釋放 GIL —— 全系統最大的週期性停頓在 FinMind 取數,不在任何 wire 序列化  @copycat/server/breadth_fetch.py:70(urlopen(...).read() →
     CPython 的 `json.loads` 是 C 實作、全程持 GIL。丟進 to_thread 只是把「event loop 上同步」換成「整個 process 一起卡」——event loop、5 條 TC4 listener、COM 下單執行緒同時停,而程式碼讀起來完全像是已經卸載了。這比 X2-06 的理論最壞(18.9 ms、實際 1.4 ms)大一個量級,而且是週期性的;它同時也是 X2-02 那個 
   * pyproject 的 fastapi>=0.115 不保證 X2-01 那條 Rust fast path 存在 —— 4x 退步可以經由依賴解析靜默發生  @C:/side-project/copycat/pyproject.toml(live = ["fastapi>
     X2-01 把整條 fast path 當成既成事實,並建議加一條「斷言 route.response_class 仍是 DefaultPlaceholder」的回歸測試。但那條測試在**舊版 FastAPI 上一樣會綠** —— `DefaultPlaceholder` 在舊版也存在,只是 `serialize_response` 沒有 `dump_json` 參數、整條 fast path 不存在。也就是說 X2
   * _handle_quote 整條跑在 event loop 上 —— 入站路徑真正的 loop 負擔是 JSON 的 3–5 倍,而掃描把它記在 listener thread 名下  @copycat/server/stock_engine.py:1147-1150(_on_raw_threads
     這是熱路徑宣稱 HP-1 的執行緒歸屬錯誤,而錯誤方向剛好讓最重要的結論失準:被算在「listener thread」上的 21.4–45.7us parse,其實每一微秒都花在 event loop 上。所以(a) X2-02 的 GIL 飢餓假說沒有主體;(b) 但 event loop 的真實負擔比整份報告量到的 JSON 總帳(6.6 ms/牆鐘秒,跨全部執行緒)大好幾倍,而且全集中在同一條執行緒上 —— 要
   * X2-04 的修法會把「零 client 時免費」變成恆定成本 —— publish 少一道空集合早退  @copycat/server/ws.py:65-67(publish 的 for queue in self._
     這是修法本身的反效果,掃描的 risk 欄列了 seed / fake / 測試三項卻沒列這一項。現況 `publish` 在沒有 client 時是空迴圈、幾乎免費;改成「入口序列化一次」後,瀏覽器全關的時段(盤後掛機整夜、夜盤期貨仍在推)每條 broadcaster 都會照常做 json.dumps。stock_ws 峰值 ~190 則/s、futures_ws 30–50 則/s,而這台機器整晚是掛著的。修法必
-- X3-concurrency
   * SignalHub.on_book 每則推播跑 7 slot,頻率是 on_tick 的數倍,卻沒有任何 finding  @copycat/server/signal_hub.py:616-630 → copycat/live/sign
     掃描把 on_book 列進「熱路徑宣稱」表(26.4 µs)卻**沒有為它開任何 finding**,而它是全庫頻率最高的 Python 工作:`_handle_quote` 尾端無條件呼叫(唯一的閘是 `_pending_date is None`,換日期間才擋),也就是**每則推播**都跑 —— 簿更新的量遠大於成交,這點掃描自己在 X3-05 講過。 更關鍵的是:X3-06 提出的「共用 SharedTick
   * 整份報告最大的缺口:TC4 推播率(尤其簿更新率)全庫零量測,而三條 finding 的量級全部掛在它上面  @copycat/live/tc4.py:1225-1231(_listen_loop → handle_raw)
     X3-04(call_soon_threadsafe)、X3-05(parse)、以及上面那條 on_book,三條加起來是 event loop 上最大的一塊固定開銷,而它們的量級**全部**是「推估數百~千則/s」乘出來的。掃描自己在熱路徑表裡誠實標了「量級未量測」,卻在 finding 的 impact 欄把推估值當結論用、並據此給了 high severity。 這造成施工順序錯亂:我用真資料把 X3-01 
   * ws.relay 對每條連線各做一次 send_json(starlette 內部 json.dumps),N 個分頁 = N 份序列化同一個 dict  @copycat/server/ws.py:262-271(`_send` 內 `await websocket.
     掃描在資料流圖裡寫了「relay._send → starlette json.dumps」,但沒有立案、也沒有量測。這是 X3-03 建議 orjson 時**真正該指的地方**:group-state 是每 60 s 一發,而 WS 是每則訊息 × 每條連線。 `WsBroadcaster.publish` 把同一個 dict 丟進每個 client 的有界 queue,序列化發生在 per-client 的 `
   * 「ProactorEventLoop 的 call_soon_threadsafe 比 Selector 快 24%」複現不出來 —— 工具建議唯一的量化背書不成立  @工具建議表最後一項(ProactorEventLoop,現況)
     結論(維持 Proactor、不要換)本身是對的,但理由是假的,而這個數字同時被 X3-04 的 impact 引用。錯誤的量測會讓後續決策踩空:如果有人根據「loop 選型能換到 24%」去評估 winloop,就會高估收益 —— 而報告在 winloop 那一欄已經正確地說「瓶頸是純 Python CPU 不是 socket 層,收益 <5%」,兩處自相矛盾。 實際原因:CPython 的 `BaseEventL
   * parse_hist_tick 走同一支 _taipei_time,回補重放一檔熱門股 = 42,084 次 strptime;X3-05 的修法收益其實在這裡最大  @copycat/live/stock_models.py:238-273(parse_hist_tick)→ :
     X3-05 只談即時路徑,漏了回補路徑 —— 而回補才是 `_taipei_time` 真正被大量呼叫的地方。`_collect_history` 收割回來的 TICKS row 逐列走 `parse_hist_tick`,實測語料顯示熱門股單日 42,084 列。 它在 `to_thread` 裡所以不卡 event loop,但它**佔著一個 executor worker、而且排在 `api.lock` 的隊伍
   * data/signal_rules.json 是 8/15 的過期檔(只有 4 條規則),誤導任何以工作樹當 prod 真相的量測  @C:/side-project/copycat/data/signal_rules.json(mtime 202
     這不是效能問題,是**下一位做量測的人會踩的坑**:repo 工作樹的規則檔只有 `cdp_cross / surge_crash / vol_burst / limit_lock` 四條,少了 `surge_pullback ×2` 與 `sweep_cluster`。任何人直接 `load_rules(repo/data/...)` 去量 SignalHub,會量到 4 slot 而不是 prod 的 7 slo
-- X4-numeric
   * 訊號 rule slot fan-out 把所有 per-code 狀態機複製 N 份:N 個 slot 各跑一次共用的窗維護,只有一個能發訊  @copycat/server/signal_hub.py:455-462(`_make_slot`)+ :607
     掃描把「五個 kind 中四個 O(1)」判成「都很好」,但它算的是**一個 detector 內**的成本,漏了外層乘上 slot 數。`_make_slot` 給每條規則建一顆**獨立的 `SignalDetector`**,每顆有自己的 `_prev` / `_window` / `_lookback` / `_sweeps` / `_sweep_group`。於是每筆 tick:窗 append + 時間逐出
   * fade_pipeline 對同一批 1K 檔的重讀是 ~19 遍不是 2–3 遍(掃描把自己最有價值的建議低估了 6 倍)  @copycat/backtest/fade_pipeline.py:674-675(`for arm in AL
     掃描寫「fade_pipeline 三處各讀一趟,無 cache」,把 :97 / :444 / :703 當成三個平行的一次性讀取。但 :444 不在頂層,它在 `run_fade_arm` 內部 —— 那支函式的 docstring 自己寫「單一 arm × param set 的完整流程」,而外層是 `for arm in ALL_ARMS` × `for params in arm.anchor_params
   * 掃描把 breadth 的 2000 列當成每 10 秒的 WS 廣播 —— 那是 REST on-demand,而且有 tab gate  @copycat/server/breadth_engine.py::payload(WS 訊息)vs :565 
     這是 X4-04 整條建議的最大一個數字(3,966 µs),也是「orjson 建議導入」的主要說服力來源,而它的前提是錯的。`BreadthEngine.payload()` 回的是 `{type, trade_date, as_of, stale, counts, last_minute}` —— counts 是兩個市場各 5 個整數、last_minute 是一格,整則大概幾百 bytes。2000+ 列的
   * `data/signal_rules.json`(prod 規則檔)相對現行 `rule_config` 已經過期,會 KeyError —— 掃描拿它當「prod 實測 4 條規則」的證據時  @C:\side-project\copycat\data\signal_rules.json(mtime 202
     我照掃描說的「prod data/signal_rules.json 實測 4 條規則全 enabled」去載入時,`rule_config(rule, cfg)` 直接 `KeyError: 'rearm_dwell_secs'` —— 檔案裡 cdp_cross 的 params 只有 `rearm_ticks`。 這有兩個意義:(1) 掃描宣稱的「prod 實測 4 條」其實沒有真的把這個檔餵進現行程式碼跑過,
   * 熱路徑成本的「平均」被系統性高估:純簿更新比帶成交便宜 45%,而簿更新才是多數  @copycat/live/stock_models.py:216-220(`if price is None o
     掃描的區塊地圖把「`parse_stock_realtime` 實測 22.0 µs/則」當成每則 REALTIME 推播的成本,並據此推「500–2000 則/s」的總量。但 stock_models.py:218-220 的早退讓純簿更新完全跳過 `_taipei_time`(strptime)、`_best_limit_price` ×2、`derive_side`、`is_trial_window` 與 `S
   * numpy / polars / orjson 全部未安裝在專案 .venv —— 所有「實測 Nx」的對照組都不是在這個環境量的  @C:\side-project\copycat\.venv(Python 3.13.13);pyproject.
     掃描報告有多處寫「實測」的加速比(polars read_csv 144x、orjson 9.3x、numpy corr 151x、search 146x),但這些套件在專案 venv 裡一個都沒有。掃描自己在 X4-02 露了口風(「另一 venv 17.12 ms」),說明它至少有一部分量測是在別的環境做的。 這不代表數字是假的(這些都是業界熟知的量級),但它改變了決策的性質:**「現況」那一半我全部能在這個 v
-- X5-memory
   * `_taipei_time` 才是 parse 熱路徑的第一大成本(39%),而 X5-06 的三條修法一條都沒碰到它  @copycat/live/stock_models.py:90-96(`_taipei_time`);呼叫點 `
     X5-06 把 parse 的 21.66 µs 歸因到「三件套全建」,開的藥是 slots / levels 改 array / meta dirty-check。我把 18.86 µs 拆開之後,佔比是:`_taipei_time` **7.37 µs(39%)** > `_parse_levels` ×2 6.32 µs(34%) > `StockMeta` 2.97 µs(16%)。最大那一塊沒被點名,而它是
   * `slots=True` 單獨就砍 36% 的 full GC 停頓 —— 報告只記了「省 19% 記憶體」,導致 X5-01 的分期建議錯了  @copycat/live/stock_models.py:45-61(StockTick)、:63-66(Sto
     報告把 slots 放在 X5-06 的 (a),標「省 19%」,然後把整個 GC 停頓的解答押在 L 級的欄式 tape(X5-01)。實測顯示這個分期是錯的:**slots 一行就拿走 36% 的停頓**,因為 traversal 少掉 `__dict__` 那一層間接。這改變的是決策 —— 應該先出 slots(S,零風險,可當天上線),用 X5-05 的 GC 探針量四週,再決定 L 級欄式重寫要不要做。報
   * 報告宣稱「沒有一個數字是 prod 實錄」—— 但 logs/ 裡就有,而且它直接驗證了報告自己的 60 萬筆核心前提  @logs/server-2026091*.log(`backfill <code>: <n> ticks` 行,
     報告把「所有數字都是離線 bench」當成最大風險寫進 X5-05,並據此主張「改造之後也無法證明改對了」。這句話會讓 user 低估整份報告的可信度,也錯過一個**已經存在的零成本量測通道**。 實際上回補 log 每一行都記了該碼當時的當日 tick 總數。我聚合 `server-20260911-0036.log`(00:36 起站、回補涵蓋完整一個交易日):**90 檔、合計 381,107 筆、median
   * `_TICKS_MAXLEN = 20_000` 的假設前提已被 prod 打破(實測 30,598),最熱的股票正在被靜默截斷  @copycat/live/stock_state.py:19
     這條常數的註解逐字是「熱門股單日 6.2k 實測、漲停攻防股更高(design r1-F8)」—— 6.2k 是它被訂出來時的觀測。prod log 顯示 2303 當日 **30,598 筆**、6770 **21,950 筆**,已經是那個前提的 **5 倍**。 後果:`deque(maxlen=20_000)` 會靜默丟掉最早的筆數,影響 `snapshot()` 的 `ticks` tape(成交明細只看得
   * corr 面板零 WS client 時照樣每秒算 13.4 ms —— 一個三行、零風險的 gate,X5-03 完全沒考慮  @copycat/server/corr_engine.py:320-322(`if self._broadcas
     X5-03 直接跳到「增量維護配對序列」(要處理逐出語意與 `now` 時戳對齊、需要 golden fixture)與「numpy ring buffer」(新 C 相依 + float64 末位差異)。但 `_broadcast` = `corr_ws.publish`,在 app 啟動時就掛上且**永遠不是 None** —— 也就是說沒有任何人開著相關係數面板時,`state()` 仍每秒把 10 腿 × 1
   * `_hist` 的 Bar dict 被 CPython 自動 untrack —— 這推翻了 X5-04 的 GC 論述,也讓 X5-05 的「改完應歸零」判準會誤報失敗  @copycat/server/bars.py:237(`self._hist`)、:344-346(prune)
     X5-04 寫「每個死掉的 StockDayState 裡的 tick 都還在被 gen2 掃描」,並把 `_hist` 與 `_states` 放在同一個 GC 論述下。實測顯示兩者性質完全不同:**加進 324,000 個 Bar dict 之後,`gc.get_objects()` 反而從 13,201 掉到 12,723**,`gc.collect(2)` 只要 6.5 ms —— CPython 的 `_P
-- F1-stream-hotpath
   * 主圖 `book` 每則 TC4 quote 無節流廣播 —— /ws/stock 唯一沒有窗也沒有節流的訊息型別  @C:/side-project/copycat/copycat/server/stock_engine.py:1
     三種訊息裡 watchlist_quote 有 1 s 節流(`_flush_watchlist_loop`)、ticks 有 0.1 s 打包(`_flush_ticks`),**只有 book 是每則 TC4 quote 直接 publish、無節流無去重**。簿變動不需要成交,活躍主圖的 book 頻率可以高於成交頻率,每一則在瀏覽器都做 `setAccum({ ...acc, book })` → App 全
   * applyTick 的成本 82% 在 `new Map(acc.minutes)`,而容器換成陣列可便宜 67 倍  @C:/side-project/copycat/frontend/src/lib/stock-accum.ts:
     掃描把 applyTick 的改造指向「批次化」(F1-03)與「不維護 tape」(F1-06),但實測顯示 tape 只佔 6%、批次化只降呼叫次數,而**單次成本的 82% 是 minutes 這個 Map 的複製**。`minutes` 的 key 是連續的分鐘號(`minuteKey`,X_START_MIN..X_END_MIN,最多 271 格),天然適合定長陣列或 index-offset 陣列——i
   * buildIntradayGeometry 內的 `energyFrom` 產出零消費者 —— 最熱的純函式帶著一段死工  @C:/side-project/copycat/frontend/src/lib/stock-intraday-
     `g.energyBars` / `g.maxTotal` 全 repo 沒有任何讀者:副圖走的是 `StockIntradayChart.tsx:1096 subEnergy = buildEnergyBars(accum.minutes, { width: w, height: subH }, xw)`,而 geometry 內那份是以 **mainH** 算的,高度不同**根本不能共用**。所以每張卡、每次更新
   * `windowedEntries`(271 筆 copy + filter + sort)每張卡每次更新跑兩次  @C:/side-project/copycat/frontend/src/lib/stock-intraday-
     同一份 `accum.minutes`、同一個 `xw`,在一次卡片更新裡被展開/過濾/排序兩次(geometry 一次、副圖的 buildEnergyBars 一次)。實測單次 17.5 µs,兩次 = 35 µs ≈ 一張卡整趟幾何成本(約 137 µs)的 25%。修法是把 `entries` 算一次往下傳(或讓 buildEnergyBars 吃已算好的 entries),純參數搬移、零輸出值變化——比 F1
   * `areaPolygon` 的 273 × toFixed(1) + join 是 buildIntradayGeometry 的最大單項(48%)  @C:/side-project/copycat/frontend/src/lib/stock-intraday-
     掃描把它列成 F1-04 八個 bullet 之一,然後把整支函式的解法推向「幾何增量化」(effort L,且自承有等值反查的靜默精度風險)。實測顯示只要處理這一個字串建構就砍掉近一半:有 ref(會建 areaPolygon)101.46 µs vs 無 ref(areaPolygon 恆空)52.75 µs。`toFixed(1)` 本身 273 次 = 19.25 µs,而 `Math.round(x*10)
   * 群組檢視下主圖 accum 同樣在養一份沒有讀者的 tape(F1-06 的另一半)  @C:/side-project/copycat/frontend/src/App.tsx:181(`{ tape
     `opts.tape=false` 只讓 **snapshot** 不帶 ticks(`stateUrl` 加 `tape=0`),擋不住 `useStockStream.ts:385 acc = applyTick(acc, item)` 繼續往 `acc.ticks` append;而群組檢視下 `TickTape` 在另一個分支、完全不渲染。F1-06 只點名群組卡片,漏了主圖這一份——同一個 `keepTap
   * 量測方法論漏洞:側欄摺疊狀態會直接改變 F1-01 的量級,before/after 不控制它就不可比  @C:/side-project/copycat/frontend/src/components/stock/Wa
     F1-01/F1-02 的收益全部押在「側欄 150 列每秒重跑 150 次」這個前提上,但使用者若把群組摺起來,那些列連 element 都不建。掃描 §7 的量測計畫(DevTools Network WS 數則數 / Performance trace)沒有把「側欄展開了幾組、圖牆選了哪一組」列為必須固定的變因,照那份計畫量出來的 before/after 可能只是反映使用者當下摺了幾組。任何 /perf 立案
-- F2-svg-lib
   * watchlist_quote 每秒 per-code 逐則推播 → 每秒觸發 N 次整棵 App 重繪(無 toggle、永遠開著)  @後端 C:\side-project\copycat\copycat\server\stock_engine.p
     這是比 F2-01 更根本、而且**沒有任何開關**的固定開銷,掃描 agent 完全沒抓到。後端每秒把 dirty 集合逐檔 publish(一檔一則 WS 訊息);前端每則各自 `setWatchlist((prev) => ({ ...prev, [code]: q }))`。瀏覽器對每則 WS message 各派一個 task,React 18 的 auto-batching 只在單一 task 內生效 —
   * EnergySub 在卡片寬度下是退化重疊繪製(271 個 1px rect 擠在 170px 內),存在比 path 化更便宜的降採樣解  @C:\side-project\copycat\frontend\src\components\stock\St
     掃描 agent 把 card 與 page 兩個變體當同一個問題處理(F2-02/F2-03 都只提 path 化)。實際上卡片變體是**退化**的:`barW = Math.max(1, plotWidth(width)/(xw.end-xw.start) - 0.4)`,卡片寬 ~246 → plotWidth = 246−36−40 = 170 → 170/270 = 0.63,減 0.4 後被 clamp 
   * 每筆 tick 在 accum 層拷貝兩個 Map + 兩次 200 元素陣列,是整個幾何層失效的上游源頭  @C:\side-project\copycat\frontend\src\lib\stock-accum.ts:
     掃描 agent 把區塊界定在「SVG 繪圖計算層」,但它整份報告的每一條頻率宣稱都建立在『accum.minutes / accum.vp 每 tick 換 identity』上,卻沒有去看那個 identity 是怎麼換的。`applyTick` 每筆成交做:`new Map(acc.minutes)`(≤271 entry)、`new Map(acc.vp)`(數十到數百 entry,低價股 autofit 可
   * 整批數字全部來自 JS 微基準(疑為 node/jsdom),沒有一筆是真瀏覽器 trace,且全是開盤尖峰當穩態  @報告 C:\Users\USER\AppData\Local\Temp\claude\C--side-proje
     方法論層級的漏洞,會直接誤導改造排序。(1) 所有『實測』都是純 JS 計時(0.101 ms / 0.530 ms / 1.539 ms / 15 ms jsdom),沒有任何一筆分得出 Scripting vs Rendering vs Painting —— 而 F2-02/F2-03/F2-13 的整套論述前提正是『慢在 DOM 節點與 style recalc 而不是純計算』,那恰恰是純 JS 微基準測不到
-- F3-chart-components
   * 群組圖牆與單檔圖表是**互斥檢視**,最壞成本不可相加  @frontend/src/components/stock/StockPage.tsx:312 `{view =
     區塊地圖把 StockChart 與 GroupGridView 畫成 StockPage 底下的並列子樹,讀起來像是同時掛著。實際上 `view` 是單選 pill,群組檢視「吃掉整個 main 主體」(元件內註解原文)。因此 F3-01 / F3-03 / F3-13 / F3-14(圖牆側)與 F3-05 / F3-06(單檔 K 線側)**永遠不會同時發生**,把兩邊的 ms/s 疊起來當總帳是錯的。排改造順
   * 圖牆掛載瞬間會發出約 50 個併發 `/api/stock/overlay`,且 50 個 useQuery 訂閱常駐在 core 內  @frontend/src/components/stock/StockIntradayChart.tsx:102
     CDP 預設開(useChartToggles DEFAULTS `cdp: true`),而 `useStockOverlay` 是**在 IntradayChartCore 內**呼叫的 —— 圖牆每張卡一個 useQuery 實例。切進一個 50 檔的群組會在同一拍對後端打約 50 發 `/api/stock/overlay`(後端那支要日 K,走 TC4),而 TC4 的 `api.lock` 是全域序列化的
   * 全部量測都是 Node + esbuild 的純 JS 微基準,沒有一條數字來自真瀏覽器的 prod build  @報告 §2 微基準表(Node 24.13.0)+ 本區塊所有 ms/s 推導
     本區塊的三大判讀((a) 全序列重折、(b) mousemove 打進 React、(c) SVG 節點量級)裡,只有 (a) 是純 JS 可量的;(b) 的強制 layout 與 (c) 的 reconciler + DOM 成本**完全沒有量測**,全靠「真瀏覽器通常是 JS 的 2-5 倍」這種係數推出來。而排序恰恰取決於 (b)(c)。本專案 CLAUDE.md 已明載日常看盤要跑 `npm run buil
   * 整份報告沒有一條談端到端延遲,而那才是量化系統的效能指標  @(全區塊)+ CLAUDE.md §4「個股逐筆 = ticks 打包訊息」契約(`tick_flush_sec
     user 的目標是「改造成高效能量化系統」,但這一區的 19 條 finding 全部是「主執行緒 CPU ms/s」,沒有任何一條問「從後端收到成交到畫面上那一格動,總共幾毫秒」。而系統裡最大的一段固定延遲根本不在前端:後端 `_flush_ticks` 的 0.1 s 打包本身就是 100 ms 的上界,且 CLAUDE.md 記著「主圖最多晚 0.1 s(user 拍板接受)」。若延遲預算真要收緊,先動的是那顆
   * `buildIntradayGeometry` 每次都建一份只有 hover 才用得到的 `haveMinutes` Set  @frontend/src/lib/stock-intraday-svg.ts:451 `const haveMi
     與 F3-08 是同一個形狀(幾何回傳包裡塞了只有某條路徑才用的東西):這個 Set 只被 `minuteOf` 使用,而 `minuteOf` 只在 mousemove 時被呼叫;但它在**每次幾何重建**(10 Hz)都配置一個 271 / 1140 元素的中間陣列 + 一個 Set。修 F3-08 時順手改成惰性(第一次 minuteOf 才建、或直接用 `entries` 二分搜)是同一趟的事,掃描只抓到 e
-- F4-ladder-highfreq
   * TxoPage 與 IndexPage 恆掛載、零 memo 邊界 —— 每則 book 連兩張看不見的頁一起重繪  @frontend/src/App.tsx:121-129(visited index/txo 恆 true)、:
     `useStockStream` 的 `accum` state 住在 App,每則 book / ticks / watchlist_quote 都讓 **App 根重繪**;而 TxoPage 是 App 內一支**沒有 memo 的一般函式元件**,`<TxoPage />` 無條件 render(註解逐字:「index 改為恆 true … txo 維持恆 true」),IndexPage 同樣恆掛。於是每則
   * 同一筆成交造成兩次全樹重繪(book 立即 + 0.1 s 後的 ticks 打包),兩條路沒有對齊  @copycat/server/stock_engine.py:1319-1342(tick 入 _pending
     後端是**同一則 REALTIME quote** 同時產出 tick 與 book:tick 進 0.1 s 打包窗、book 當場送出。前端兩則各自 `setAccum` → 每筆成交付**兩次** App 全樹重繪。這解釋了為什麼 F4-03(細化 deps)單獨做會是 no-op,也給出比 F4-01 建議的「另起一支 book timer」更好的修法:**把 book 併進既有 `_flush_ticks`
   * 改造前沒有任何 prod-build 的盤中主執行緒基準,而唯一一筆既有量測與報告的因果敘事相衝  @.claude/mod/group-grid-ticks/verification.md:120-121;doc
     報告把 F4-01 定為 critical、把「按下單鍵有延遲」歸因於 long task,但 repo 內唯一一筆 **prod build + 開盤 + 50 張卡** 的 trace 顯示 `>50 ms long task = 0`(最大 36.7 ms)。同時 2026-08-19 那筆「主執行緒 ~66% 忙但全是短任務」是 **dev build** 的數字,根因已確認為 React dev 的 Com
   * FuturesLadder 有與 F4-04 完全同款的 inline ref churn,但 F4-04 只點名 LadderView  @frontend/src/components/futures/FuturesLadder.tsx:466-46
     `ref={(el) => { if (r.isCenter && el) centerRef.current = el; }}` 的箭頭 identity 一樣每 render 換,React 因此對 121 列各做一次 detach(null)+attach —— 242 次呼叫,其中 240 次什麼也沒做(只有 isCenter 那列真的寫值)。量級同樣是幾十 µs、同樣會在列級 memo 後自動消失,所以**
-- F5-app-shell-query
   * `book` 訊息是 App 層唯一完全無節流的推播路徑(F5-01 修完後它會接手成為主要重繪源)  @copycat/server/stock_engine.py:1359-1360(產生)/ frontend/s
     三條個股推播裡,`ticks` 有 0.1 s 打包(`_tick_flush_secs`)、`watchlist_quote` 有 1 s 節流(`_flush_watchlist_loop`),唯獨 `book` **每則 TC4 quote 就發一則**,而且發之前不比對五檔內容有沒有變。前端收到就 `setAccum({ ...acc, book })` 無條件更新 → App 全樹重繪。TC4 對主圖那一檔
   * repo 內已經有一份可直接量測的 production trace 與 render bench,掃描完全沒用,所有頻率/量級都是推估  @.claude/mod/group-grid-ticks/verification.md:120-121 + e
     這份 trace 是 09-03 開盤 09:01–09:03、prod preview(4173)、真實 80 檔自選下錄的 93 秒完整 DevTools trace(17 MB gz),裡面直接可以解出 render 次數、每次 render 成本、主執行緒忙碌比例與逐函式 self time。掃描報告的核心數字(「每秒 110–180 次重繪」「CPU 幾乎全被吃掉」「twMerge 36–144 ms/s」
   * `searchStocks` 未 memo:打字找股票時每則報價都重掃 2,401 筆名冊  @frontend/src/components/stock/WatchlistSidebar.tsx:195
     `const suggestions = searchStocks(input, names, SUGGEST_LIMIT);` 直接寫在 render body。`input` 空字串時純函式第一行早退(`if (trimmed === "") return [];`),所以平常零成本 —— 但使用者**正在打字**時,每一則 watchlist_quote / book / futures 推播造成的 re-re
   * 區塊地圖的「memo 邊界只有兩處」不正確,而這直接影響所有 render 類 finding 的成本推估  @frontend/src/components/stock/CandleChart.tsx:88;StockIn
     全庫實際有六個 memo 邊界,而不是報告開頭說的兩個。被擋住的正是全站最貴的兩棵子樹(最多 700 根蠟燭 × 3 節點的 K 線、逐筆分時圖),加上 `StockChart.tsx:196-203` 以 `liveMinutes` / `nowMinute` 純量當 dep 的 useMemo —— 這三件事合起來解釋了為什麼實測「全樹一次 render」只要 2.28 ms 而不是數十毫秒。把現況描述成「架構只
   * F5-04 只談 window focus,漏了同樣預設開著的 `refetchOnReconnect`  @frontend/src/main.tsx:16
     `new QueryClient()` 同時把 `refetchOnReconnect` 留在預設 true。本專案有 8 條手寫 WebSocket 與一套 `connectWithRetry`,網路/proxy 抖動時 TanStack 的 onlineManager 與那 8 條 WS 的重連會在同一時刻觸發 —— 齊發的批次與 alt-tab 那批完全相同(含 breadth-rows 562 KB 與會搶 
-- F6-lib-build
   * 全篇「~10 commit/s」的 render 率基準沒有出處,而真正的驅動源(watchlist_quote 一碼一則)最高可達 ~150 則/s —— 本區塊每一條「每 render」成  @copycat/server/stock_engine.py:1813-1832(`_flush_watchli
     F6-03 / F6-04 / F6-05 / F6-12 的影響量級全部乘上這個數,而掃描把它寫死成「~10 commit/s」且沒有任何量測或呼叫鏈佐證。後端側欄節流是「1 s 合併一則 **per code**」,不是「1 s 一則」——自選上限 150 檔(CLAUDE.md §4 自選上限契約)意味著開盤最壞每秒 150 則 watchlist_quote,每則各自一次 `setWatchlist` set
   * searchStocks 實際上就在 tick 路徑上(只是被空字串早退擋住),F6-12 的「不是 tick 熱路徑」判斷方向錯  @frontend/src/components/stock/WatchlistSidebar.tsx:195(r
     這決定了 F6-12 該用什麼修法:如果真的只是「人打字」,那 0.3 ms 一次根本不必修;正因為它在 render body、而側欄每則 quote 重繪,搜尋框有字的期間才會被乘上 render 率。修法也因此從「預處理大寫表」變成「呼叫端 useMemo」——後者一行、零新概念。掃描把頻率判錯後,連帶給出了偏複雜的修法。
   * 同一顆 `minutes` 資料的**寫入端**每秒整份複製 270 鍵物件,成本與 F6-11 抓的讀取端同級甚至更高  @frontend/src/hooks/useIndexStream.ts:61
     F6-11 花了一整條在講 `Object.keys(otc.minutes)`(實測 5.5 µs、1–2 次/s),卻沒注意到同一顆物件在上游每則 index WS 訊息都被整份 spread 一次 —— 同量級成本、同樣的 1–2 次/s。兩者都不是問題,但只抓其中一半代表掃描是以「檔案清單」而非「資料流」在看。嚴格說 hook 屬 F2 區塊,交給 orchestrator 判歸屬,但 F6-11 的結論(「
   * F6-02 的建議修法會打斷版本落差膠囊那條路:`/__build/sha` 是 vite plugin 端點,不是後端端點  @frontend/sha-plugin.ts(`buildShaPlugin`)+ frontend/src/h
     F6-02 的 risk 段只列了 port 三邊契約與 SPA fallback,漏了這一個真的會壞的整合點。瀏覽器若改成直開 `http://127.0.0.1:8721/`(FastAPI StaticFiles),`/__build/sha?since=...` 這支 dev-server 端點就不存在了,版本落差膠囊(spec #192 整體 review F-20 明確保留的那顆,用來擋「舊 dist +
-- F7-render-audit
   * 期貨 WS 才是實測最高頻的 App 全樹重繪驅動源,而且與使用者在哪個 tab 無關  @frontend/src/hooks/useFuturesStream.ts:49/72/99 → fronte
     掃描把期貨流歸在 U3、成本算在「隱藏期貨 tab 重算 1365 格」上,但一階成本根本不在那裡:`useFuturesStream` 常駐 App 層,每則 0.1 s coalesce 推播都 `setState(next)` → **App 全樹重繪,不管使用者停在哪一顆 tab、也不管期貨頁有沒有被 mount 過**。而且 `state` 是整包三商品的物件,任一商品動就換 identity。這是本區塊唯
   * book 訊息未去重:純成交 quote 也會重送一份完全相同的五檔  @copycat/server/stock_engine.py:1359-1360
     F7-03 直接跳到「coalesce 0.1 s,五檔延遲 +100 ms」,但這是真錢閃電梯。更便宜的一步在前面:`_handle_quote` 對主圖是**無條件** publish —— TC4 的 REALTIME 有純成交(TradeQuantity>0、簿沒變)與純簿更新兩類,前者現在也會把一份一模一樣的 bids/asks 再送一次。加一個「與上次送出的相同就不送」的比較,**延遲代價 0 ms**,
   * PriceLadder render body 還有兩個與 buildLadder 同路徑、同樣沒包 memo 的計算,F7-08 只抓了三分之一  @frontend/src/components/stock/PriceLadder.tsx:243(aggreg
     F7-08 把 PriceLadder 的成本等同於 buildLadder(實測 7.4 μs),但同一個 render body 裡還有 `aggregateLots(ordersData?.orders, code, ymdWindow(...), "股", fills)` —— 它要掃一遍全帳戶當日 fills 建 seq 索引 —— 加上 `positionRows(...)` 與兩次 `markMap(.
   * React Compiler 會凍結本 repo「刻意不進 memo」的牆鐘計算 —— 這是真錢畫面的正確性風險,不是效能取捨  @frontend/src/components/futures/FuturesChart.tsx:282-307
     F7-04 的 risk 只寫到「render 期寫 ref 的幾處 compiler 會標記」。真正危險的是反面:React Compiler 會把**沒有 reactive 依賴**的 render-body 計算視為常數並跨 render 快取,而這兩處正是明文「刻意不進 memo,因為 deps 表達不了『現在幾點』」。被快取住的症狀是期貨 live 點與個股即時末根**凍在掛載那一刻**,兩張圖都畫得出來、
   * lib/tick-stream.ts 的 emitTicks 文件與實作已漂 —— 掃描口中「全庫唯一做對的解耦」拿來當擴大樣板前要先修  @frontend/src/lib/tick-stream.ts:50;frontend/src/hooks/us
     區塊地圖把 tick-stream 立為「全庫唯一做對的解耦,應該擴大而不是收回」,F7-13 也要拿它當 quote-store 的樣板。但它的 docstring 還停在舊契約:寫「把一則 ticks 打包中**非主圖**的 items 原序丟進來」,而 pr-187 review spec F-01 之後實作丟的是**整則含主圖**(因為主圖那一檔在群組裡也有一張卡,兩份 accum 各自獨立)。任何照這份 d
-- O1-ops-devloop
   * Windows console QuickEdit 會把整個 server 凍住 —— `_Tee.write` 的 console 那一半跑在 event loop 執行緒上  @copycat/server/__main__.py:83-90(`_Tee.write` 的 `return 
     O1-04 在同一段 code 上量了 0.56 秒/天然後收工,卻漏掉同一段 code 的真風險:`_Tee` 的 `_stream` 就是原始 `sys.stdout`,而 run.ps1 以 `-NoNewWindow` 把 backend 接到操作者的 PowerShell 視窗,所以 uvicorn 每則 access log 都是**在 event loop 執行緒上同步寫真實 CONOUT$**。Win
   * boot 真正的 30 秒在 `_collect_history` 的預設 30 s 首頁預算,而它不是關機預算的輸入 —— 這是最便宜的 boot 收益  @copycat/live/tc4.py:992 `budget = deadline_secs if deadl
     O1-07 把 boot 慢歸因到 dry 輪(實測只有 1.14 s)與 CDP 基準的 1303(根本不在 boot 路徑上),完全沒看到真正卡住 boot 的那 30 秒。2026-09-04 那次 38.7 s 的 boot,index watchdog(09:01:02.552)到 futures watchdog(09:01:32.589)之間整整 30 秒的空窗,填的是兩發 30 s 的 TICKS/1
   * 真正毫秒級的 GIL 持有者是歷史回補頁解析(0.525 ms/頁),不是每 tick(2.4 µs)—— O1-05 / msgspec 的正當論據在這裡  @copycat/live/tc4.py:998-1010 `_collect_history` 的 `_get_
     O1-05 用「5 條 _listen_loop 全程持 GIL」推出「event loop 最壞等 5 ms」,但我量到單則 tick 的 decode+loads 只有 **2.4 µs**,switch interval 的 5 ms 上界在這種工作單元下永遠觸不到。真正會一口氣持 GIL 好幾百微秒到毫秒的,是回補的 `HisData` 頁解析:1,000 列 = **0.525 ms**,而開盤 boot 
   * `asyncio.wait_for` 逾時不會釋放 to_thread 的 worker,而關機預算假設 COM join 立刻起跑 —— O1-02 該用的實證在 repo 裡,而它的 ri  @copycat/server/app.py:1507(註解)、app.py:952 `lambda c: asy
     O1-02 想證明「池會塞滿」,卻去數 call site(還數錯 44%),而 repo 裡就有一句逐字的實證:overlay route 的 `asyncio.wait_for(..., timeout=15)` 逾時後「放掉的是 semaphore 名額 —— `to_thread` 的工作執行緒**中斷不了**」。這才是池飽和的真實機制:TC4 半死時,每 15 秒就有最多 4 個被放棄但仍阻塞的 worke
   * log 78% 的 access noise 之所以存在,是因為前端對「已經由 WS 推播的資料」再 REST 輪詢 4,384 次/日 —— O1-04 只診斷到「可讀性」就停了  @copycat/server/app.py:942 `loop.call_soon_threadsafe(cap
     O1-04 正確地判定 access log 不是效能瓶頸(我重算同意),但停在「真正的成本是可讀性」。往前一步就會看到:排名第一的 `/api/capital/positions`(4,384 次/日,占 access 行 31%)拿的是**同一份已經由 `/ws/capital` 推播出去的資料**,而後端那支 route 的工作只是 `with self._lock: return list(self._pos
-- Q1-quant-gap
   * `_eval_volume` 的 `sum(qty for ...)` 是全庫唯一 O(窗長) 的 per-tick 運算,成本隨個股 tick 率平方成長  @copycat/live/signal_state.py:657 附近(`_eval_volume` 內 `wi
     Q1-17 指認的成本來源(「每 tick 對 N 個 deque 各做 append + popleft + 時間比較」)經實測**不成立** —— 那條路徑幾乎不隨窗長變(窗 301→15,001 時 cdp_cross 只從 2.8 μs 到 6.5 μs)。真正的成本全部集中在這一行:它每筆成交 tick 掃一次整個 300 秒窗。因為窗長本身正比於該檔的 tick 率,總成本 ≈ 300 s × Σ(各檔 
   * `on_book` 對每一則 quote 無條件跑全部規則,而只有 limit_lock 規則可能產出事件 —— 其餘規則 100% 白付  @copycat/server/stock_engine.py:1367-1368(`if self._signa
     `evaluate_book` 的 docstring 明寫「只評估『鎖停打開』」,但它在任何早退**之前**就先付了 `now = self._now_fn()`、`_in_session(now)`、`mono = _mono(now)`、`key = _clock_key(now)`(一個 f-string + strftime 格式化)。`enabled` 完全沒有參與這段 —— 一條 cdp_cross 規
   * `_taipei_time` 用 `datetime.strptime` + timedelta + 兩次格式化,佔每筆成交 tick 解析成本的 35%  @copycat/live/stock_models.py:89-95(`_taipei_time`),由 cop
     `parse_stock_realtime` 是整條 quote 熱路徑上最貴的單一函式(比整個訊號層還貴),而它 1/3 的成本花在一個純粹的格式轉換上:`_dt.datetime.strptime(date_utc, "%Y%m%d")` 建一顆 datetime、加兩次 timedelta、再用兩個 f-string 做 strftime 格式化 —— 全部可以用整數運算取代(`hh*3600+mm*60+ss
   * 「TC4 ZMQ 電文接收(唯一入口)」不是唯一的 —— prod 同時跑五個 `TC4QuoteSource` instance,各自一條 listener thread 與一次完整 jso  @copycat/live/tc4.py:1185(`self._listener = threading.Thr
     掃描的熱路徑 #1 標題寫「唯一入口」,而 `tc4.py:1216` 的 docstring 也寫「子類覆寫這一支即可共用整個 `_listen_loop`」—— 那是說**實作**唯一,不是**執行個體**唯一。prod 有五條獨立的 listener thread、五個 ZMQ SUB socket、五份 `json.loads` + `_note_push` 的 GIL 佔用。這對三條 finding 的實作
-- Q2-tooling-landscape
   * 單檔頁 K 線每則 ticks 打包(0.1 s)重跑 aggregateBars(~5,900 根)+ 重繪最多 700 根蠟燭 —— 這才是 CandleChart 真正的 per-tic  @C:/side-project/copycat/frontend/src/components/stock/St
     掃描引了 `CandleChart.tsx:221 g.candles.map(...)` 當圖牆的證據,但 CandleChart 根本不在圖牆路徑上(消費端只有 FuturesChart / MarketChart / StockChart)。它真正的熱度來自另一條完全沒被追到的鏈:spec #214 的即時末根讓 `bars` useMemo 把 `accum.minutes` 當 dep,而 accum 每則
   * WS 出站是 per-client 各編一次,不是「一則 encode 後 fanout」;而 Q2-03 的 MsgspecResponse 修法完全碰不到 WS  @C:/side-project/copycat/.venv/Lib/site-packages/starlett
     掃描的熱路徑宣稱把 WS 出站寫成「encode 成 bytes,再 fanout 到 per-client queue」—— 次序反了。`WsBroadcaster.publish` fanout 的是 **dict**,每個 client 的 `_send()` 各自呼叫 `websocket.send_json(msg)`,而 starlette 在那裡才 `json.dumps`。所以 N 個瀏覽器分頁 = 
   * 所有 to_thread 共用 loop 預設 ThreadPoolExecutor(max_workers = min(32, cpu+4)),overlay 150 檔 / daily_b  @C:/side-project/copycat/copycat/server/app.py:1568-1571;
     Q2-01 把外呼的風險講成「釘住 event loop」,而原始碼裡每一處都已 to_thread,所以那個機制不存在。真正的結構性風險是 executor 共池:overlay 進群組時對上限 150 檔同時打、`daily_bars` 走 to_thread 沒有上限、capital close 的 COM join、MIS 5s poll、breadth 取數、signals jsonl 落檔、Discord
   * Q2-02 提的「第一步:改單一 <path>」已經是 repo 自己的 next-time 項,而且附了實測 baseline —— 掃描沒引到,等於漏掉現成的量測基準  @C:/side-project/copycat/frontend/src/components/stock/St
     這不只是「撞題」。那段註解同時記了 N047 的量測結果(jsdom 滿窗一輪 ~15 ms、隔離的純 rect 層 ~17 ms、真瀏覽器快一個量級)與一條**反面警告**(「要收的話別用『總量當資料版本』:1K 回補可以在總量不變下改寫某一分鐘的量,那種 memo key 會讓副圖靜默停在舊值」)。改造若不知道這條,很可能第一個念頭就是加 memo key —— 那正是被點名會造成靜默錯值的做法。既有 basel
   * HTTP 路由的 `-> dict` 走的是 pydantic-core(Rust)序列化,不是純 Python encoder;最大 payload 實測毫秒級個位數,而零相依修法就能吃掉大  @C:/side-project/copycat/copycat/server/app.py:1519-1520(
     掃描說「FastAPI/Starlette 預設 json.dumps(CPython 純 Python encoder)」有兩層錯:①stdlib json 在 indent=None 時用 C encoder(`_json.Encoder`);②FastAPI 因為有 `-> dict` 回傳標註而建了 response_field,序列化走 pydantic-core(Rust),`jsonable_encod
   * 回測搜索已經是 Python int bitmask(C 層 bitwise),Polars / DuckDB 在這個計算形狀上不會更快 —— Q2-06 / Q2-07 的「快 10–100  @C:/side-project/copycat/copycat/backtest/search.py:25-46
     兩條 finding 都建立在「回測是逐檔 json.load + 手刻 Python loop、無向量化」這個前提上。實際結構是:run_features 讀一次 bars → 落 CSV → `build_predicates` 把每個謂詞物化成一個任意精度 int bitmask(`mask |= 1 << i`)→ GA / 窮舉用 bitwise AND 評估;outcome 另走 `_outcomes_p
