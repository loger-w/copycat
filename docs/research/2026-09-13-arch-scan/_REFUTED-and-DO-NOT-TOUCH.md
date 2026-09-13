### REFUTED(23 條:掃描說有問題、查核證明沒有)

* [B03-ws-broadcast] seq-gap refetch 在 event loop 上同步卡 45.9 ms(jsonable_encoder 佔 87%)
  理由: 檔案/行號與引用逐字屬實(app.py:1668-1671 `async def stock_state(... ) -> dict`;stock_state.py:19 `_TICKS_MAXLEN = 20_000 # 熱門股單日 6.2k 實測`;snapshot 的 ticks 展開在 :295-307)。**但機制整條是錯的**:本 repo `.venv` 裝的是 fastapi 0.139.2 / pydantic 2.13.4 / starlette 1.3.1 / uvicorn 0.51.0 / py3.13.13。我直讀 `fastapi/routing.py::get_
* [B04-stock-engine] _parse_levels 每則做 20 次字串串接 + 20 次 dict.get
  理由: 「_parse_levels 占 parse 三成」這半 CONFIRMED(實測雙側 6.425 µs / 21.97 µs = 29%,agent 說 35%)。但**歸因與修法都是錯的**。實測:`'Bid'+'3'` = 0.0067 µs,10 次串接合計 0.067 µs = parse 的 0.3%;真正的成本是 `to_milli`(Decimal)0.29 µs × 10 = 2.9 µs,占 _parse_levels 的 45%,其餘是 dict.get(0.02 µs × 20)與 list/tuple 配置。我照 fix 段寫了預建 key 表原型,實測單側 3.00
* [B05-live-state] _context 每則訊息重算已經算過的最佳限價檔,且 TickContext 無 slots
  理由: 事實描述對(signal_hub.py:992-1010 確實重算 `_best_limit_price` ×2,而 stock_models.py:221-222 剛算過同一份),但**量級整整誇大一個數量級**。實測:`_best_limit_price` 正常簿 **0.075 µs**、鎖停市價佇列簿 0.088 µs(它是 `for price, _vol in levels: if price > 0: return price`,正常簿**第一圈就 return**,根本不是「掃五檔」);TickContext 建構 0.727 µs。所以 _context 全支約 1.0–1.
* [B08-bars-overlay] mergeLiveMinuteBars 每 0.1 s 無條件複製整段正式 bars + 排序已有序的 Map keys
  理由: 程式碼位置對(live-last-bar.ts:41 `const out: Bar[] = [...official];`、:49 `[...minutes.keys()].filter(...).sort(...)`),`minutes` 由 `applyTick` 以單調遞增分鐘鍵插入所以 sort 恆 no-op 也對。**但量級錯了一個數量級,而且方向是往上錯**:我實測 Node 24,`[...bars]`(5,670 個物件參考)median **0.003 ms**(V8 對 dense array 走 memcpy 快路徑),不是 0.05 ms;`[...minutes.
* [B09-external-io] DailyIndex.load 52 MB CSV 要 3.5 s;若 B09-01 採納,不要沿用這個全載模式
  理由: 這不是一條 finding,是 B09-01 修法的一個註腳,卻被當成獨立條目掛 medium。 (1)**前提是自我否定的**。它的立論是「若採納 B09-01(server 改讀本地 EOD store),這支會變成 server 啟動路徑的一環」—— 但 B09-01 的修法段**明確寫著不要用 prices.csv、要另建按日分檔**。所以這個「若」在報告自己的建議下永遠不成立。 (2)報告自己標「現況不是熱路徑」(server 不載,只有離線回測 / replay CLI 用)。 (3)`DailyIndex.load` 我讀了 `copycat/data/daily.py:30-5
* [B09-external-io] mis.py 的 _fail_streak 是 module-level 可變全域,多 worker thread 非原子更新
  理由: **code 屬實**(`mis.py:23-24` `_fail_streak = 0`、`:42` `global _fail_streak`、`:75` `_fail_streak += 1`),但宣稱的失效**在 prod 走不到**。 唯一呼叫端是 `index_engine._mis_loop`(`index_engine.py:508-517`): ```python while True: snap = await asyncio.to_thread(self._mis_fetch) # await —— 上一發回來才有下一發 ... await asyncio.sleep(s
* [B10-capital-order] 幫浦圈例外分支 time.sleep(1.0) 佔住唯一的送單執行緒
  理由: `client.py:791-793` 三行逐字存在(`logger.exception("COM 幫浦圈例外(本輪略過)")` + `time.sleep(1.0)`),而且確實排在 `_cmd_q.get(timeout=0.05)`(client.py:811)之前。但這條分支在 prod **從未執行過**:`grep -c "COM 幫浦圈例外" logs/*.log` 全部為 0。它的第二段影響描述還有事實錯誤:『例外被吞掉』不成立 —— `logger.exception` 會印完整 traceback 到 log 與 console,不是零訊號;『使用者只看到按鈕轉圈』也不成立
* [B10-capital-order] 三條路徑各自呼叫 store.orders() 建全表,只為找一筆
  理由: 三個呼叫點行號全對:`capital_api.py:191` `rec = next((o for o in client.store.orders() if o.seq_no == seq_no), None)`、`client.py:1065` 同式、`client.py:1139` `for o in self.store.orders():`。fut 改價雙建也屬實(route `capital_order_correct_price` 先 `_correct_price_tick_gate(client, ...)`,再 `client.correct_price` → `_fut_
* [B10-capital-order] REST 每列都跑 stock_code_of / _fill_code 反查(含一次 path.stat())
  理由: 『每列都跑』是錯的。`mapping.py:109-136 stock_code_of` 第一行就是 `if market == "sec": return stock_no` —— **證券列根本不會呼叫 `lookup_product`,零 stat**;`capital_api.py:240-247 _fill_code` 同樣是 `return stock_code_of("fut", stock_no) if unit == "口" else stock_no`,只有期貨列才反查。這個帳戶的部位與委託絕大多數是現股/融資(audit 樣本 `trade_kind: margin`、`
* [B11-backtest-fade] fade_features 對同一個 window 重掃 40–64 次(149/197 欄來自三個三層迴圈)
  理由: 三個錯誤,且其中一個是斷章取義。(1) **耗時誇大 4 倍**:我 repeat-time 真 bar 序列,`fade_trigger_features` = **53.9µs**(真實迴圈內攤提 75µs),不是 231µs。(2) **欄數錯**:實測 **208 欄**,不是 197。(3) **`_bid_exhaustion` 的證據被截斷**:他貼的片段停在 `total = b.up_volume + b.down_volume`,但原始碼 fade_features.py:147-151 的迴圈是 `for b in reversed(window): ... else: 
* [B12-backtest-core-replay] fade walk-forward 的 mask & (1 << i) 是 O(n²) bigint
  理由: code 位置對(fade_pipeline.py:254-258,`mask = apply_rule(conds, all_feat)` 然後 `for i in val_ids if mask & (1 << i)`),複雜度標籤技術上也對。**但常數小到不構成問題**,報告自己也承認「未實測」。我把 n 查出來了:out/fade_ga/rules_final.json 的 results[0] 顯示 n_train=940 / n_test=819 → all_feat ≈ **1,759 列**,val_ids ≈ 0.25×940 ≈ 235,candidates = 30(fa
* [B13-data-io] label-events 對 11,048 事件各讀一個 32 KB JSON,63 秒只為取 top-5
  理由: 兩個支柱都倒。(1) **單次成本錯了 12 倍**:我實測 `read_brokers` = **0.443 / 0.476 ms/檔**(兩次不同隨機樣本,平均檔 36.7 KB、513 個 broker),不是 5.754 ms。為了排除 page cache 的嫌疑,我另外做了 first-touch vs second-touch 對照:0.452 → 0.417(seed 777)、0.421 → 0.413(seed 31337)—— **首觸與二觸幾乎相同**,所以 5.754 ms 不是冷快取造成的,就是量錯了。(2) **頻率錯了**:`label_events.py:86
* [X1-blocking-io] WsBroadcaster 讓每個 client 各自序列化同一則訊息
  理由: 機制敘述沒錯(ws.py:65-80 同一個 dict 進每條 queue、:262-265 每 client 各一次 `send_json`),**但支撐 impact 的事實是錯的**。他寫「index.state()(含 ~280 分鐘 × 2 指數)…每秒推一次」。回去讀 index_engine.py:744 —— 每秒廣播走的是 `self._publish(self._payload())`,而 `_payload()`(:790-801)= `twse.scalar()` + `otc.scalar()` + `txf()`,`scalar()`(:150-158)只有 p/r
* [X2-serialization] 全庫沒設 sys.setswitchinterval —— 5 條 TC4 listener thread 可各霸佔 GIL 5 ms
  理由: `grep -rn setswitchinterval` 零命中這一點屬實。但**因果機制不成立**,兩個獨立理由:(1) 掃描把 `parse_stock_realtime`(它自己算 21.4–45.7us)算在 listener thread 上,實際不是 —— `copycat/server/stock_engine.py:1147-1150` 的 `_on_raw_threadsafe` 是 `loop.call_soon_threadsafe(self._handle_quote, quote)`,而 `parse_stock_realtime` 的唯一 stock 呼叫點是 `s
* [X5-memory] 每則行情的字串三度複製 + json.loads 吃 str 而非 bytes
  理由: evidence 的兩行 code 逐字屬實(`tc4.py:1245 raw = (sock.recv()[:-1]).decode("utf-8")`、`:1195-1199 msg = json.loads(raw[idx + 1 :])`),但**結論與修法三項全錯**,我逐項實測: (1) **「json.loads 吃 str 比吃 bytes 慢」是反的**。實測同一份電文:`json.loads(str)` **4.54 µs** vs `json.loads(bytes)` **4.90 µs` —— stdlib json 對 bytes 會先跑 `detect_encod
* [F2-svg-lib] buildIndexOverlayLines 每卡逐點重算,x 座標對所有卡相同卻算 40,650 次
  理由: 程式碼引用逐字屬實(`index-overlay-lines.ts:87-105`),`sortedIndexRows` 的 WeakMap 跨卡共用也確認是既有修法。但作為**可行動的效能 finding** 它不成立,三個理由:(1) 前提與 F2-01 同一個閘 —— `idxOn = !index && !futures && (toggles.idxTwse || toggles.idxOtc || toggles.idxTxf)`,而三顆 toggle 在 `useChartToggles.ts` 的 DEFAULTS 全是 false,關著時回 `EMPTY_IDX_LINES`
* [F5-app-shell-query] cn() = twMerge(clsx()) 用在每秒數萬次的列渲染上
  理由: 單次成本的估值錯了 20–40 倍。我用 repo 內實際安裝的版本(clsx 2.x + tailwind-merge 3.x,frontend/node_modules)跑基準,模擬 WatchlistSidebar 一列的實際 class 串:**cache hit 每次 0.076 µs**(不是宣稱的 0.5–2 µs),clsx 單獨 0.015 µs;全 miss 情境才 3.98 µs,但本 repo 的列渲染器 class 串只隨少數條件分支變動,穩態幾乎 100% hit、distinct key 數十個(LRU 500 綽綽有餘)。 次數也偏高:`WatchlistSid
* [F6-lib-build] ESLint 沒有 eslint-plugin-react-hooks —— effect 重訂閱風暴沒有任何靜態守門
  理由: 「package.json devDependencies 無 eslint-plugin-react-hooks」這半句是真的(我逐字核過 frontend/package.json),但由此推出的結論「rules-of-hooks 與 exhaustive-deps 都沒在跑 / 沒有任何靜態守門」**是錯的**。 證據鏈:(a) `react-doctor` 在 devDependencies(`"react-doctor": "^0.9.11"`),而 CLAUDE.md §1 的前端 gate 逐字要求 `npx react-doctor@latest --scope changed
* [F6-lib-build] 沒有 Web Worker 邊界設定;types.ts 反向依賴元件檔,擋住把 wire 型別搬進 worker
  理由: 事實半邊成立:`types.ts:1` 逐字 `import type { HandoverProgress } from "@/components/ConnectionBadge";`,`grep new Worker|?worker` 零命中,vite.config.ts 無 worker 區塊。 但 impact 的核心機制不成立:「`types.ts` 的反向依賴會在搬型別進 worker 時**把整個 ConnectionBadge 元件模組拖進去**」—— `import type` 是型別匯入,TypeScript 一律抹除(`tsconfig.app.json` 有 `iso
* [F7-render-audit] 零 useSyncExternalStore / useDeferredValue / startTransition / Activity
  理由: **標題的核心證據是假的。** `grep -rn "useSyncExternalStore" src` 有 **4 個呼叫點**,不是零命中: - `src/hooks/useCapital.ts:81` `return useSyncExternalStore(subscribeWsStatus, () => currentWsStatus);` - `src/hooks/useChartToggles.ts:137` `const toggles = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);` - `src/h
* [F7-render-audit] CandleChart 的可變長度序列用 index 當 key
  理由: 行號與寫法屬實(CandleChart.tsx:176 / 203 / 221 / 300 / 353 都是 `map((x, i) =>` + `key={\`v-${i}\`}` 之類)✓。 **但 impact 的機制寫反了。** React 對 keyed children 的比對是「相同 key → 復用同一個 fiber 與 DOM 節點,只更新 props」。平移 / 縮放後陣列仍是 `v-0 … v-N`,**每個位置都命中同一個 key → 原地更新 x/y 屬性,不卸載不重掛**。會卸載的只有陣列**變短**時多出來的尾巴。 改成 `key={c.t}` 反而會引入 key
* [F7-render-audit] OrderBook 每格用 toLocaleString 而非 lib/format 的 Intl 單例
  理由: 三處呼叫點屬實(OrderBook.tsx:30 `n.toLocaleString("en-US")` / pnl-format.ts:13 / OrderPanel.tsx:302)✓,lib/format.ts:1-2 的兩個 Intl 單例也屬實 ✓。 **但前提(「toLocaleString 每次呼叫會做一次 locale 解析…仍比預建 formatter 慢」)經實測是假的。** 我在 Node(與 Chrome 同一顆 V8)跑 500,000 次: - `n.toLocaleString("en-US")` = **0.232 μs/op** - `new Intl.Num
* [Q1-quant-gap] lookahead 防護純靠註解與命名紀律,零機械閘
  理由: 兩個關鍵事實都不成立。 (1)「同一個 frozen dataclass 裡兩者**型別相同**、並列」——原始碼 `t1_open.py:38,40` 逐字是 `auction_share_adv20: float | None` 與 `auction_share_dayvol: float`,**型別不同**。而且 finding 自己貼的 evidence 區塊就印著這兩行不同的標註,impact 文字與自己的證據自相矛盾。 (2)「任何下游拿錯 `auction_share_dayvol` 都不會有任何訊號」—— 全庫 grep 只有三個讀者:`t1_open.py:153`(寫入,`

### do_not_touch 精選(每區前 3 條)

-- B01-tc4-ingress
   · `tc4common.py::to_milli_units` 的 Decimal:實測只有 0.449 µs,我寫的手刻整數截斷版(已驗證逐位等值)是 0.369 µs —— **省不到 0.1 µs**,而檔內明文寫著「🚨 不與 float 家族合併:Decimal 是截斷、float round 是 banker's rounding,在 tick 邊界會分岔」。期望收益接
   · `live/session.py` 整檔(80 LOC):純字串 / time 判定,每次訂閱才呼叫一次,完全不在熱路徑。
   · `tc4common.py::iter_qry_pages`:回補分頁游標,離線路徑。
-- B02-server-core
   · **FastAPI 的回應序列化路徑**。實測 0.139 + pydantic 2.13 已走 dump_json 的 pydantic-core Rust 快路徑（1.6 MB / 6.8 ms，比 stdlib json.dumps 的 14.6 ms 快一倍）。顯式指定 ORJSONResponse 會讓 use_dump_json 變 False，退回「pydanti
   · **app.py 的 2133 行本身**。實測 `python -X importtime -c "import copycat.server.app"` 總 389 ms，其中 app.py 自身只佔 3.6 ms、fastapi 佔 223 ms。切成 5 個檔省不到 3.6 ms 裡的任何一毫秒，對 import / reload 時間零幫助。要切只能以可維護性 / 注
   · **__main__.py 的 _Tee per-write flush**。實測 write+flush 5.4 µs/行 vs 純 write 0.3 µs。crash 當下 log 已落盤的證據價值遠大於這個成本（註解也記了 asyncio warning 事故那次差點無檔案證據）。access_log 每請求多 ~11 µs，也不是問題。
-- B03-ws-broadcast
   · WsBroadcaster.publish 的同步 fanout(ws.py:65-80):裡面沒有任何 await,是「一個慢 client 拖不到其他 client」的唯一保證。任何為了效率把它改 async 的提案都是退步。
   · 「滿了丟最舊、保最新」對 quote 型訊息(watchlist_quote / book / index / futures / corr)—— 這些是自足快照,丟舊的完全正確。只有 ticks 例外(B03-05)。
   · relay 的三 task + FIRST_COMPLETED + finally 同步 cancel + _consume_ws_task 結構(ws.py:219-312):實測框架成本 1.1 us/則,且 docstring 把每個決策的失效樣態都寫清楚了(send-only 察覺不到斷線、send_lock 不得包 async for、close_sent 後的 Ru
-- B04-stock-engine
   · copycat/server/stock_engine.py:450-484 `_acquire`/`_release` refcount 訂閱池 —— 分派已是 O(1) dict lookup,且「先寫記帳再訂閱」是 TC4 在 SUB 回來後毫秒級推第一則 REALTIME 的實證修法(§8 實證),順序不可換,否則冷門標的整天唯一的那一則 meta 會被丟掉、畫面只是空
   · ZMQ REQ 全程 asyncio.to_thread(_resubscribe_all:964-978 / set_watchlist:551 / set_main_contract:637-641 / _retry_round:1030,1047,1059)—— 這是 event loop 不被 TC4 半死拖垮的唯一防線。rollover_stage1 的 set_tr
   · copycat/server/stock_engine.py:541-558 set_watchlist 的逐項取鎖(N111)—— 拿 Discord interaction token 15 分鐘逾時換來的設計;且「N111 的退訂正確性依賴 IO 在鎖內」,把 IO 移出鎖會讓 ST1 訂閱洩漏原樣復發
-- B05-live-state
   · StockDayState.ingest / _apply / _fold_vp(stock_state.py:87-198)—— 實測 1.96 µs/tick,VWAP / high / low / VP 全部已經是增量式,穩態零物件配置。300 tick/s 全開也只佔 0.06% 一顆核。這是全 repo 寫得最好的熱路徑之一,換 numpy 只會變慢。唯一該動的是它持
   · to_milli_units 的 Decimal 實作(tc4common.py:16)—— 實測 0.41 µs vs 手刻 0.39 µs,只快 5%,而 docstring 記了明確的正確性理由(截斷 vs banker's rounding 在 tick 邊界分岔)。這是最容易被誤判成瓶頸的地方。
   · ChainAggregator / payoff 全家(aggregate.py、payoff.py)—— 實務態 13.66 µs/秒,極端 120 檔全活也只有 141.97 µs/秒,且 engine.py:70 已節流到 1 Hz。curve_points 的 O(n²) 在 n = 實際有部位的合約數(個位數)下完全無關。**過度工程警告**:這裡最容易被「O(n²)
-- B06-signals
   · **雙佇列 fanout + 丟最舊背壓**(signal_hub.py:1167-1184, 1673-1687):jsonl(1000)/ Discord(100)兩條獨立有界佇列、`_put_drop_oldest` 不 await put、熱路徑零反壓、丟棄有計數與節流 log。實證全日零丟(`grep -c 佇列滿 logs/server-20260911-0905.
   · **`_discord_worker` 的單槽 `_discord_pending` 合批**(signal_hub.py:1198-1234):不回塞佇列(避免順序亂)、`task_done()` 恰一次的記帳。少記一格關機吊死、多記一格 worker 猝死,改動風險遠大於收益。
   · **掃單簇的滑動窗實作**(signal_state.py:718-748):`lookback` / `sweeps` 都是 deque + 單向剪裁、amortized O(1),且 `lookback` 刻意保留「窗前最後一筆」當漲幅基準(`while len(lookback) >= 2 and lookback[1][0] <= cutoff`)。**不是**每次重掃
-- B07-other-engines
   · IndexEngine._broadcast_loop / _payload / _Series.scalar —— 每拍 < 100 µs,_dirty 閘已正確,minutes 全量只在回補成功後帶一次(_push_minutes_once)。這是一個寫得對的 1 Hz loop,量測證明它不是熱點。
   · FuturesEngine._flush 的 0.1 s per-product dirty-set coalesce —— 已經是正確的 coalescing 設計(payload 是全量快照所以合併無資訊損失;失敗那則回標 dirty 下週期重送;迭代 list(self._dirty) 快照避免恆拋時原地打轉)。不要改成 per-tick 直推(五檔會洗爆 WS),也不要
   · RiverState 的 dict[int, int] 分鐘桶 —— 日盤 300 / 夜盤 840 格 × 11 腿,每拍 O(1) 寫入。對它用 numpy array 是純過度工程:稀疏、整數鍵、需要『只填空缺』與『名次小者贏』的語意,array 表達不了。
-- B08-bars-overlay
   · copycat/market.py 全檔(70 行):毫元整數 tick 表實測 103–187 ns/call,每 tick 呼叫也只有 0.04 ms/s。而它守著兩條跨語言 parity 契約(tests/fixtures/vp_parity.json ↔ frontend/src/lib/stock-tick.ts::snapDown;capital_api.py:14
   · copycat/server/overlay.py 全檔(60 行):compute_cdp / compute_ma 都是 O(n),n ≤ 1500,每檔每天算一次;app.py:1761 明說「build_overlay 是常數時間」。compute_ma 的 sum(closes[-n:]) 在 n=5/20 的規模做滑動窗增量化是純粹的複雜度
   · copycat/server/oi_levels.py 的 _pivot 與 10 日窗:一天一次、asyncio.to_thread、實測 2.6 ms(外推真實列數 ~7 ms)。_LOOKBACK_DAYS=10 的連假理由是對的,縮短才是真的壞
-- B09-external-io
   · `market_breadth.compute_breadth`(實測 5.42 ms / 每 10 s,duty cycle 0.05%)—— 丟 to_thread 的 context switch 成本比省下的多。
   · `market_breadth.dedup_sector_map` / `build_type_map` / `build_name_map` 的 4 次 sort(實測合計 3.84 ms,一天 1–2 次)—— 合併省 2 ms/天,換掉 tie-break 語意的可讀性與 breadth_parity oracle 的明確性,不划算。
   · `limit_streaks.compute_prev_streaks`(實測 0.00 ms)—— 交集遞進 + early break 已是這個問題的最佳解,W=10、|D₀|≈22–38。
-- B10-capital-order
   · copycat/capital/safety.py 全檔 —— 五個純函式閘合計 < 5 µs,它是安全邊界不是熱路徑;任何「優化」都是在動拒單判準。要加的是新的閘(B10-12),不是改快現有的
   · copycat/capital/mapping.py 的契約碼轉換 / regex / is_option_contract 四層收斂 —— 實測含 stat 也只有 ~50 µs。第 4 層結構判別是為了「個股期上線後整條被送進期權面」那個 P0 設計的,動它就是動送單分流
   · copycat/stkfut_map.py::_product_index 的 stat() 簽章 cache —— 實測 0.004 ms。mtime_ns 簽章是 A4 刻意設計:refresh-stkfut-map 是另一個 process 跑的 CLI,拿掉簽章 = 新上市個股期被 unknown product multiplier 拒單而對映檔明明已更新
-- B11-backtest-fade
   · fade_cells 的評估 pass 本身(_simulate_r3_trades 實測 0.11–0.23 s/pass,round 4 全跑約 10 s)。這裡換 numpy/polars 是純過度工程 —— fade-cells 的 32 s 有 71% 在 build_universes 的 JSON 載入,修 B11-07/B11-12 就好。把 _evaluate
   · fade_diagnose.stratified_permutation_p 的 RNG 演算法(random.Random(seed=42))。確定性已寫進 configs/*.json 並體現在 docs/evidence/uc_pool_fade_2026-07-15*.md 的 p 值裡,換 numpy RNG = 舊報告不可重現。這是離線一次性診斷,分鐘級可接受。若真
   · quantiles.py 的兩種分位數演算法(quantile_round 的 banker's rounding vs quantile_trunc 的 int 截斷)。檔頭 docstring 明寫「user 2026-07-20 拍板保留,統一演算法會改報告數字 = 行為改動」。numpy 的 np.percentile 兩種都不等價(插值版)。不要碰。
-- B12-backtest-core-replay
   · copycat/replay/validate.py 全檔 —— 42 條 golden 常數(_G_LOCK/_G_GAP/_G_AUCTION)與容忍值(±5%/±0.5pp/±1pp/±3pp)是 characterization 錨點,出處鏈寫在 docstring(intraday_playbook §2d / open_gap_definition §2-3 / s
   · copycat/replay/report.py::med(:20-22)—— s[len(s)//2] 偶數不取平均,是 42 條 golden 的一部分;換成 statistics.median 會讓 gate 全紅
   · copycat/backtest/quantiles.py 的 round / trunc 兩份演算法 —— user 2026-07-20 明確拍板保留,docstring 寫明「統一演算法會改報告數字 = 行為改動,不得在 refactor 內做」
-- B13-data-io
   · copycat/configio.py 整個檔案(32 行):5 個 caller(backtest/config.py:129、fade_config.py:417、breadth_config.py:36、signals_config.py:72、strategy_config.py:43)全在啟動期各跑一次,檔案都是幾 KB。它做的 unknown-key 檢查 + tu
   · copycat/cli.py 的 451 行 if-chain + 分支內 lazy import:土但正確。正是這個寫法讓 `python -m copycat screen` 不必載 backtest/fade_cells.py(2,000 行)。換 click / typer / dispatch table 會多一個相依、少一點可讀性,而啟動時間本來就是毫秒級。最多只把
   · copycat/data/models.py(54 行):Bar1K 已是 `frozen=True, slots=True`,taipei_min / fmt_min 是純算術。唯一能再快的是不建 dataclass 而用 tuple/array —— 那屬於 B13-02 的儲存層改動,不是這個檔的問題。
-- X1-blocking-io
   · **`_Tee` 的 per-write flush**(server/__main__.py:88-97)。原本預期是每行 log 的同步磁碟寫入災難,**實測只有 4.85 µs**(OS page cache 吸收),換來的是「crash 當下 log 已落盤」的排查價值。不要動。
   · **`_append_jsonl` 的 open+append+close 每列一次**(signal_hub.py:1412-1418)。200 µs/列但在 to_thread 裡,而一天只有 ~686 列(實測 data/signals/20260911.jsonl = 289 KB / 686 列)。檔案不長開的好處(外部工具可隨時讀、crash 不掉資料)遠大於 20
   · **`WatchlistService._settle` 在鎖外**(watchlist_service.py:228-253)。已被 X-3 / N111 兩輪改過把「鎖凸出」收斂掉,結構正確;剩下的 _commit 檔案 IO 只有 0.1–2 ms。不要再優化。
-- X2-serialization
   · **所有 HTTP route 的 response class(最重要)** —— FastAPI 0.139.2 的 dump_json fast path 已是 pydantic-core Rust(routing.py:709-731,本 repo 39 支路由全標 `-> dict` 且未指定 response_class 而命中)。加 ORJSONResponse 
   · **不要加 GZipMiddleware** —— 同機 loopback,gzip 3.3MB 要 20–40ms CPU,會把 18.9ms 的 event-loop stall 變成 40+ms
   · copycat/server/signal_hub.py:1375-1382 的逐行 bytes 保留回填 —— CLAUDE.md §4 明記 byte 比對契約 + tests/server/test_signal_outcome.py 釘住;已走 to_thread。改 parser 時必須把這裡列入硬白名單(Rust serializer 的浮點字面 / 鍵序與 std
-- X3-concurrency
   · copycat/server/ws.py 整支 —— per-client 有界 queue + 丟最舊保最新 + 60 s 節流 WARNING + 窗到期結算規模 + 10 s 心跳 + FIRST_COMPLETED 收尾 + _is_close_sent_error 的兩句 uvicorn/starlette 原文辨識。這是全庫寫得最好的併發 code,每個分支背後都有
   · copycat/server/shutdown_budget.py + app.py lifespan 的並行 lane + run.ps1 的 WaitForExit —— 三方同源、由 tests/server/test_shutdown_budget.py 的不等式與 test_boot_window.py::TestShutdownLanes 的 lane 形狀機驗釘住
   · copycat/capital/client.py 的 COM 執行緒模型(20 Hz 幫浦 / _cmd_q + future / shield 保護真錢命令 / _drain_pending 失敗收斂)—— 真錢路徑,而且 COM STA 讓它沒有別的寫法,且目前完全不是效能瓶頸。不要為了效能碰它。
-- X4-numeric
   · copycat/market.py:15-19 的 5-zone tick 表 —— n=5 的 tuple 線性掃描,實測在噪音以下;改 bisect 對 n=5 反而更慢,numpy 的 array 建構開銷遠大於整段成本。而且 snap_down_milli 與前端 stock-tick.ts::snapDown 有 tests/fixtures/vp_parity.js
   · copycat/live/stock_state.py:147-198 的 _apply / _fold_vp —— 已經是增量 O(1),是全庫最該被抄的寫法。檔頭 60-64 行明寫「逐 tick 增量維護,不在請求時掃 ticks」的理由(150 檔 × 20k 的同步迴圈會卡住 WS fanout)。這正是 X4-01 要推廣的模式。
   · copycat/backtest/quantiles.py 的三種分位數演算法 —— user 2026-07-20 拍板保留,檔頭明寫「統一演算法會改報告數字 = 行為改動」。換 np.quantile / polars quantile = 靜默改掉所有已發布報告。
-- X5-memory
   · futures_engine(server/futures_engine.py:115-145,645-694)—— 全庫記憶體紀律最好的一支:_ProductState 有 __slots__、_dirty dict 合併 + 單一 flush timer(0.1 s)、payload() 只在送出時複製 bids/asks。10 個商品 × 每 0.1 s 完全可忽略。一行
   · RiverState(live/river_state.py)—— 分鐘桶 dict,上界 = 一天的分鐘數(day 300 / night 840),換場清空。結構正確,佔用可忽略
   · CorrState 的儲存層(live/corr_state.py:55-78)—— 時間戳逐出 + _cap = 3600 雙保險,檔頭把「為什麼不用固定長度 deque」講得很清楚(event loop 漏拍會讓固定長度的實際時間跨度失真)。要改的是 correlations() 的演算法(X5-03),不是 _series 的結構
-- F1-stream-hotpath
   · lib/tick-stream.ts 的 EventTarget pub/sub —— 題目假設的「50 張卡各訂閱一次、扇出 50 次 callback」在本 codebase **不成立**:subscribeTicks 全 repo 只有一個訂閱者(useGroupLiveAccums.ts:144),一則打包只 dispatch 一次 CustomEvent,卡片由圖牆
   · lib/ws-reconnect.ts 的退避三分支 / 靜默 watchdog / ping 過濾 —— onmessage 只寫 lastMsgAt 時間戳(:202)、單一 setInterval 巡檢(:188),檔頭明記「個股 tick 洪流下零 timer churn」,設計正確。WS_SILENCE_TIMEOUT_MS 是 §4 心跳契約的一半,動它要同動後端 
   · 0.1 s tick 打包機制本身(#180)—— 後端 _flush_ticks 與前端「整則只 commit 一次」都已經做對了。問題不在打包,在打包之後的 per-item applyTick 與 App 層 setState。
-- F2-svg-lib
   · chart-crosshair.ts(43 行)/ chart-frame.ts(100)/ pane-frame.ts(173)/ time-labels.ts(31)/ spot-session.ts(14)/ timeframe.ts(73)/ candle-viewport.ts(73)—— 全部是常數與 O(1) 換算,熱路徑成本為零。這些檔的註解密度極高(每個數字都
   · lib/pnl-svg.tsx —— TXO payoff 曲線隨部位變(低頻,每分鐘跑不到一次)。xDomain 被 buildScales 與 invertX 各算一次、interpCurve 是 O(n) 線性搜尋,兩者都是真的,但在這個頻率下改它是過度工程。
   · bollinger.ts 的直算法 —— 檔頭明記「不用 Σx²−(Σx)²/n 的一趟法:毫元價位平方後量級 1e11,一趟法在低波動盤整段會有災難性抵銷」。為了效能改成一趟法 = 用正確性換速度。要快就縮輸入(F2-11),不要改算法。
-- F3-chart-components
   · buildIntradayGeometry 的語意分支:norm() 的「0 = 不可得」收口、hasRef 與首筆 fallback 的分權、極值的等值反查(entries.find(m => m.h === target))、域外不畫、flat 退化域特判 —— 每一條都對應一個真實 bug 的修法(註解裡有實測樣本),為速度砍掉任何一條都是用正確性換效能
   · lib/index-overlay-lines.ts 的 SORTED_ROWS WeakMap 快取(per-series 排序一次、50 張卡共用、隨舊物件 GC)—— 已是最佳解,應往外複製而不是改它
   · useContainerSize 的 1px 去抖與 0×0 忽略 —— 兩條都是修過的真 bug(ResizeObserver 回饋迴圈告警、hidden tab 量到 0×0 沖掉有效量測)
-- F4-ladder-highfreq
   · OrderBook.tsx:143-168 與 DepthBar.tsx:75-84 的五檔歸一計算 —— 最多 10 個格子、每則約 30 次基本運算,完全不是熱點;且 limitOnly / bestLimit / marketQty 是 2026-07-31 user 拍板的口徑契約(一律只算限價量),兩邊漂移的症狀是同一檔在兩頁總量不同且零錯誤訊號
   · components/ladder/ArmRow.tsx 的 DOM —— ArmRow.characterization.test.tsx:110/134 以兩梯 outerHTML 字面量鎖死(class / 元素順序 / aria-pressed 任一變動即紅),而它一次 render 只有 2 顆鈕,做效能改動零收益
   · PriceLadder / StkfutLadder / FuturesLadder 的 clickPrice / marketOrder 同步段 —— 已查證 click→fetch 無阻塞(TanStack 通知走 setTimeout(0) macrotask、fetch 在 microtask 先發);不要加 optimistic UI、不要搬 Web Worker、不
-- F5-app-shell-query
   · **Bundle 大小 / code splitting**:實測 dist gz 合計 188 KB(index 123 KB + StockPage 22 + CandleChart 15 + IndexPage 9 + FuturesPage 6 + CorrPage 5 + CSS 8)。這是跑在 localhost、一天開一次、開著整天不關的工具,首屏從 127.0.
   · **GroupCard 的 14 個 prop 穩定化**(GroupGridView.tsx:132-179, 453-477):EMPTY_FILLS / EMPTY_POSITIONS / NOOP_HOVER / latest-ref pick / indexSeries 條件傳 null,每一條都有註解說明失效樣態。這是全檔最好的工程,F5-01 做完後仍有價值(60
   · **日 K 新鮮度政策 lib/day-bars-rollover.ts**:三支 hook 共用,與後端 DAILY_FINAL_TIME 有 golden fixture parity(CLAUDE.md §4「日 K 定稿界前後端同值」)。msUntilDayRollover / dayBarsRefetchInterval 的每個分支都對應一個實際踩過的坑,而頻率是一天
-- F6-lib-build
   · lib/format.ts:1-2 —— Intl.NumberFormat 已在 module 層 hoist,這是正確寫法。全庫 grep `new Intl.` 只有這兩行、零個在函式內,慣例是乾淨的。
   · lib/pnl-format.ts:13 與 components/stock/OrderBook.tsx:30 的 toLocaleString("en-US") —— 看起來像「每次建 formatter」,**實測不是**:toLocaleString(locale) 0.277 µs、hoisted nf.format 0.398 µs、new Intl.NumberF
   · lib/storage.ts 整支 —— 4 個獨立 warn 旗標 + per-key parse 旗標 + 空字串走「無資料」而非 JSON.parse(""),每條都有註解寫明理由,是全庫 45 處裸 localStorage 收斂的成果。要改的是呼叫頻率(F6-04),不是這一層。
-- F7-render-audit
   · **`ChartStatic`(StockIntradayChart.tsx:171、CandleChart.tsx:88)/ `EnergySub`(:818)/ `GroupCard`(GroupGridView.tsx:132)三個 memo 邊界,以及它們周圍的十餘個 `EMPTY_*` 模組常數**。這些已經是正確解,而且每一個都附了失效樣態的註解(例:StockIn
   · **`lib/stock-intraday-svg.ts` 的幾何演算法**(921 LOC)。271 格的迴圈不是瓶頸(每次 buildIntradayGeometry 約 271 次迭代,而且已被 useMemo 護住),而裡面全是台股領域知識:tick 表 snapDown、漲跌停域 vs 對稱 autofit、判定率 75 % 門檻的雙峰樣本推導、CDP 標籤的 1D 
   · **`useEffect` 紀律與 adjust-state-during-render pattern**(App.tsx:150-154 prevStockCode / StockPage.tsx:143-147 prevCode / RightRail.tsx:184-196 prevInstrument / StockChart.tsx isFut 收斂 / fee-d
-- O1-ops-devloop
   · **logging 全鏈**:全庫 `logger.xxx(f"...")` = 0 次(全部 %-style lazy),熱路徑(tick 分派、WS publish)零 logger;實測 15.5 µs/行 + console 23.8 µs,全日總成本 0.56 秒。ruff 的 PLE1205/PLE1206 已機械擋住格式參數數量錯誤(存量 0)。已經是最佳實踐,沒
   · **關機預算 / lane 設計(shutdown_budget.py)**:83 s 是 TC4 半死的可計上界,prod log 實測整段收尾 0.21–0.30 s,而 run.ps1 的 WaitForExit 在 process 一退就回 —— 「盤中改完要等 83 秒」是誤解。三方同源 + 不等式測試釘住,是這個 repo 設計最紮實的一塊。
   · **uvicorn --reload / watchfiles**:watchfiles 已裝(uvicorn[standard] 帶的)但刻意沒用。開了 reload = 每次存檔重建五條 TC4 session,每次付 60 s 零推播的 reap 代價。絕對不要加。
-- Q1-quant-gap
   · copycat/backtest/simulate.py 的時序語意 —— 悲觀成交(進場 = 觸發 bar close + slippage,cap 在漲停)、鎖死 bar 凍結全部停損與 S1 計時、同 bar 停損 > 時間出場取最差、excluded_unfillable。這比 backtrader/vectorbt 的預設嚴謹得多,換通用框架會丟掉台股特化的正確性
   · 訊號 id 的決定性鍵(signal_hub SC-7:trade_date-rule_id-code-kind-levels|direction-time_key)—— 這是重啟安全與前端去重的基礎,任何『改用 uuid』都是倒退
   · 下單審計的 shield + 「結果未知,勿重送」+ late 補審計(client.py:889-901)—— 真錢路徑上最難寫對的一段,已經寫對了
-- Q2-tooling-landscape
   · copycat/live/tc4.py:1185/:1245 的 ZMQ threading 模型(threading.Thread + 阻塞 sock.recv())—— pyzmq 官方明說 zmq.asyncio 不建議與 web server 同 loop 用;且阻塞 recv 在 C 層釋放 GIL 真正並行。改成 zmq.asyncio 是退步。
   · uvicorn 的 loop / http / ws 三層自動選擇 —— .venv 原始碼實測已是 ProactorEventLoop(IOCP)+ httptools(C 版 HTTP parser)+ WebSocketsSansIOProtocol,是 Windows 上 uvicorn 能給的最好組合。不要手動指定 --loop / --http / --ws;也不要
   · copycat/market.py 的毫元整數運算(台股 tick 表 + 漲停價)—— 換成任何浮點(numpy / polars 的 f64)都引入舍入誤差,直接影響下單價格正確性。這是效能優化的絕對禁區。
