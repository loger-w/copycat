---
name: tc4-market-facts
description: TC4(達錢 4)與台股市場資料的實測事實全集(專案累積教訓)。碰訂閱 / symbol 樹 / tick 解析 / 歷史回補(1K/DK)/ 指數期指 / 海外段 / 鎖漲跌停 / 個股期 / TXO 序列 / 群益送單欄位 / prev_close 與事件母體語意前先讀對應節。
---

# TC4 / 市場資料實測事實(2026-08-10 自專案 CLAUDE.md §8 遷移,內容未改)

> 寫入規則:新教訓屬「TC4 / 市場資料 / 券商 API 實測事實」者追加到本檔對應節;
> 各條保留原始日期與 Trigger 標註。

## 訂閱與 symbol 存在性

- **台指期產品碼是 TXF 不是 FITX**(`TC.F.TWF.TXF.*`;FITX 只出現在 Quote 的 `Security` 欄位)。
  **SUBQUOTE 對不存在的 symbol 照回 Success=OK**(平台不驗證,零錯誤訊號),訂閱成功 ≠ symbol
  存在;新 symbol 要先過 QUERYALLINSTRUMENT 或確認有推播。(2026-07-20,Trigger:訂閱新 symbol)
- **`QUERYINSTRUMENTINFO` 對不存在 symbol 回 parse failed = 存在性 oracle**(SUBQUOTE 回 OK
  不可靠之外的第二判法);股票 / 指數同段查詢會附父節點資訊(TickSize/OpenCloseTime)。
  `QUERYALLINSTRUMENT` 25 個 Type 名窮舉只有 `Fut`/`Fut2`/`Opt` 有效(wrapper 註解寫 Options 是錯的);
  股票類無有效 Type(Stock/Stk/Sec/Equity 全 Fail),股號存在性靠「訂閱後有無推播」健檢。(2026-07-28)
- **現版 `SUBQUOTE REALTIME` 必帶 StartTime/EndTime**(官方 wrapper SubQuote 未帶會 fail,
  見 docs/research/2026-07-18-txo-chain-probe.md)。client 是 `pyzmq` + asyncio,不是 httpx/aiohttp,
  新接 service 不要照貼 trash-cmoney 的 httpx pattern。(Trigger:寫 TC4 client)
- **TC4 REALTIME 訂閱的真實模型(2026-08-18 以 `C:\TC4\APPs\TCoreRelease\Logs\QuoteZMQService-*.log`
  + 受控 probe 實證;取代 07-28「同 symbol 跨 session 只推一邊」的錯誤結論)**:
  (a) 推播是**單一 PUB port(54322)廣播**,所有 session 都收得到所有 symbol 的 REALTIME,不存在「只推一邊」;
  (b) TC4 refcount 以 **key = `symbol|DataType|StartTime|EndTime`** 計(log `Add/RemoveSubQuoteCount(...) count:N, SumSubCount:M`),
  但**上游 feed 以 symbol 為單位**:key count 0→1 才 `ReqSubQuote(symbol)`;**任一把 key SumSubCount 歸 0 → 上游退訂整個
  symbol,同 symbol 其他 key(count 仍 >0)一起斷,之後對那些 key 再 SUBQUOTE 因 count>0 不重掛上游 → 永久零推播**;
  (c) 沒 LOGOUT 就死的 process(taskkill /F、crash)其 session 約 60s 後被 `ExecuteCheckPingTime` reap,reap 時它獨持的 key
  (夜盤窗、昨日窗、舊 corr 全天窗…)歸零 → 殺掉新 server 同 symbol 的活 key。**這就是每次重啟後 ~60s「訂閱成功但零推播」
  的根因**(07-28 夜盤三次重啟、07-30 futures 間歇零推播、08-13 index REALTIME 靜默、08-17/18 全站零推播皆同一機制)。
  (d) 復活條件:讓某把 key 走 count 0→1 —— 自己是唯一持有者時 UNSUB→SUB 即可;多持(TXF.HOT 由 TXO+futures 雙 session
  持有、外部 probe 也持)時只有**換一把新 key(window variant)**才會觸發 `ReqSubQuote`,且新 key 一旦退訂 symbol 又斷。
  修法 = source 層零推播自癒(R1 session 靜默 / R2 symbol 靜默 / 個股 R3 health-check 重掛 + 第 3 次起 window variant),
  見 `.claude/bug/tc4-realtime-refcount-kill/`。**probe 腳本收工必 UNSUB + Disconnect,且不要用 prod 的窗訂 prod 的 symbol**
  (退訂時會把 prod 的 feed 一起帶走)。leaf fallback(futures_engine)仍保留:leaf 是不同 symbol,天然新 key。
  (Trigger:重啟後零推播 / 新引擎訂既有模組已訂的 symbol / 寫任何 TC4 probe)
- **`Disconnect()` 不等於登出**(2026-08-26 fix/tc4-logout 實證):wrapper `tcoreapi_mq.Disconnect()` 只關 KeepAlive 執行緒
  + socket,**不送 LOGOUT 電文**;送 LOGOUT 的是 `Logout(sessionKey)`。沒送 LOGOUT 的 session 走上面 (c) 的 60 s reap
  (08-25 17:15:29 Ctrl+C:708 筆 UNSUBQUOTE 貼秒,五個 `RemoveLoginInfo` 全在 17:16:31)。LOGOUT 電文 TC4 會回
  `{"Reply":"LOGOUT","Success":"OK"}`,且 `RemoveLoginInfo` 與 `DoWork:{"Request": "LOGOUT"}` 同一毫秒(00:56:15.324,零訂閱
  probe)。`TC4QuoteSource.close()` 自此 = UNSUB 全部 → LOGOUT(`_req`)→ Disconnect;拋棄式 probe 收工同序。
  判 prod 收工乾不乾淨:`grep RemoveLoginInfo QuoteZMQService-*.log` 時戳貼著 Ctrl+C,而非 60 s 後由 `ExecuteCheckPingTime` 帶出。
  (Trigger:寫 TC4 client 收工路徑 / probe 腳本 / 對帳 TC4 session log)
- **同 symbol 的歷史一律從「持有該 symbol REALTIME 訂閱的那條 session」問**(2026-07-30 通則):
  加權 `IX0001` 的 REALTIME 與當日 1K 回補都在 index session(`app.py` `_default_index_source()`
  獨立 session),從個股 session 問同一檔有把推播搶走的風險,失效樣態是「訂閱成功但零推播」
  零錯誤訊號。新增任何歷史取用點前先問「這個 symbol 的 REALTIME 訂閱在誰手上」。
  (Trigger:新增任何 SubHistory 取用點)

## tick 欄位語意與時刻

- **TC4 tick 欄位語意**(2026-07-18 實測,詳 docs/research/2026-07-18-txo-chain-probe.md):
  歷史 TICKS 的 `TradeVolume` 全為 0(無累積量,排序靠微秒級 `PreciseTime` + `QryIndex`);
  REALTIME 才有累積 `TradeVolume`(去重主鍵)。`PreciseTime`/`FilledTime` 是 **UTC**,顯示要 +8。
  REALTIME 五檔命名有位移:`Bid`=最佳、`Bid1`=第二檔。(Trigger:live tick 解析 / 現價源 / 時間欄位顯示)
- **加權 IX0001 的 REALTIME quote 沒有時間欄位**(2026-08-26 12:23 只聽不訂 probe 實證):`FilledTime` / `PreciseTime`
  恆 `'0'`,只有 `TradeDate`、`TradingPrice`、`ReferencePrice`、`HighPrice`、`LowPrice`。任何「用 FilledTime 算分鐘鍵」的
  路徑對指數都是 None → 分鐘永遠不由推播寫(08-20 起每個交易日的「加權分時線卡住」根因;分時線其實全靠 1K 自癒
  一段段補、階梯封頂後就停)。指數是 5 秒一筆快照,分鐘鍵用**收到當下的台北牆鐘**(`index_engine._handle_quote`,
  fix/index-quote-no-filledtime)。期貨 / 個股 quote 的 `FilledTime` 正常。**只聽不訂 probe 寫法**:LOGIN → SUB 連
  SubPort、topic `""` → 讀 PUB 廣播(所有 session 收得到所有 symbol)→ LOGOUT → Disconnect,零 refcount 影響,
  盤中安全 —— 要看任何 symbol 的原始 quote 欄位一律用這招,不要為了看欄位去 SUBQUOTE。
  (Trigger:指數分鐘 / 任何 quote 缺欄位 / 想看原始推播欄位)
- **`PreciseTime` 欄寬跨交易所段不同,`FilledTime` 才是通用的**(2026-07-30 實證):台期交(TWF)
  是 `HHMMSSffffff`(11–12 位),**CME/CBOT/SGX 是 `HHMMSS`**。`stock_models._taipei_time` 的
  `zfill(12)` 對海外段會把 6 位值左補 → 恆為台北 08:00:00.0xx 的假時刻,tick 照樣解析成功只有
  時刻是假的(極安靜)。任何跨段用 tick 時刻的功能一律走 `FilledTime`(UTC HHMMSS,zfill(6);`index_engine` 對
  IX0001 **不能**用它 —— 指數 quote 的 FilledTime 恆 `'0'`,走牆鐘,見下方 08-26 bullet;實例:MES 的 PreciseTime 與 FilledTime 同值 `"41256"` = 04:12:56 UTC),
  缺值才退回本機時鐘。(Trigger:跨段 tick 時刻 / 分鐘聚合 / 時序去重)
- **個股 REALTIME 實測事實**(2026-07-21,stock-terminal):上市+上櫃**全掛 `TC.S.TWS.<code>` 段**
  (TWO/TPE/OTC 段無推播);推播自帶完整五檔+漲跌停/參考價;**試撮期(13:25–13:30)TC4 不推
  成交 tick**(時間窗過濾為雙保險),`TradeStatus` 值域實測 {0=正常, 1=試撮期簿更新};**盤後
  fresh subscribe 會回當日收盤 snapshot**(延遲分鐘級)—— **但 snapshot 只含成交 tick,不含五檔**
  (2026-07-29 實測盤後 1.5h `book.bids`/`book.asks` 恆空;五檔 / 閃電梯盤後恆空是常態,tick 明細與
  江波圖走 TICKS 回補所以有資料)。(Trigger:個股訂閱 / 試撮處理 / 盤外顯示)

## 鎖漲跌停:市價單佇列價格欄 = 0(2026-07-31 實證)

TC4 在鎖漲跌停時會於簿的第一檔推「市價單佇列」,價格欄是 `0`(不是價格,是「這些委託沒有限價」)。
它會**同時**打穿四處而且全部靜默:
(a) `derive_side` — 鎖漲停(ask 側空、`bids[0]=(0,N)`)時 `price <= 0` 恆假 → 每筆成交判 neutral
(實測 2327 全日 5450 張 `cum_outer = cum_inner = 0`);鎖跌停對稱地 `price >= 0` 恆真 → 一律判 outer;
(b) 任何 `bids[0][0] === upper` 形式的鎖停判定 → badge 永不出現;
(c) 前端直接把 `0` 印在五檔上;
(d) **對整份簿做聚合**的地方(總量列、量 bar 歸一分母)— 市價量混入使定義隨日子變,跨日跨股比較
靜默失真;市價佇列可以是限價量的數倍,五根限價 bar 一起被壓扁。
修法 = **只在消費端過濾**(`_best_limit_price` 往下找第一個 `price > 0` 檔位),簿本身原樣保留 0
檔位(五檔與閃電梯顯示成「市價」);**市價量要獨立顯示不可只留 hover**(鎖板日「無限價排隊多少張」
正是 §0a 鎖板品質核心訊號);排除市價後 `maxQty` 變小,市價列自己的 bar 需夾制。
**另一層**:歷史 TICKS row 只有單一 `Bid`/`Ask` 欄,`StockDayState.apply_backfill` 先 reset 再重放 →
live 期間判好的值每次切檔被洗掉;那層靠 `relabel_locked_side`(鎖漲停 + 對手側不可得 → 內盤,
鎖跌停 → 外盤;漲跌停制度下的恆等式)。
(Trigger:內外盤判定 / 五檔顯示 / 鎖停偵測 / 拿 `book.bids[0]` 當最佳價 / 對簿做 sum/max)

- **`derive_side` 與回測的內外盤是兩條獨立鏈路**(2026-07-31):`derive_side` 只在
  `copycat/live/stock_models.py`;回測(`backtest/fade_*.py`、`data/models.py`)用 TC4 1K row 的
  `UpVolume`/`DownVolume`/`UnchVolume`(`Bar1K`),無呼叫關係。改 live 判定不影響回測口徑。
  (Trigger:評估改 live 內外盤判定的 blast radius)

## 歷史回補(1K / DK / TICKS)

- **TC4 歷史批次回補要「先全鏈 SubHistory 再逐檔收割」**:逐檔 Sub→sleep→收 280 檔 ~10 分鐘,
  先全訂讓 TC4 平行備資料再收割 → ~2 分鐘。(2026-07-18,Trigger:多 symbol 歷史回補)
- **TC4 股票 1K 實測可回補一年以上**(2026-07-10),官方「1 分 K 一年」限制僅適用期貨。
  先實測邊界再排回補計畫。(Trigger:排回補範圍 / 回測期間)
- **股票 SubHistory `DK` 直接支援**(2330 25 根零略過,官方文件未載);2317 180 日窗實證
  `Open`/`Volume` 欄位名成立(`o=240000`、`v` 與 REALTIME 累積總量一致);耗時 `tf=D` 1.1s、
  `tf=1&days=5` 2.1s。`stock_source.py` 防禦解析與略過計數 log 保留為韌性。(2026-07-28/29)
- **TC4 1K 當日回補在 CME/CBOT/SGX/TWF 四段皆可用**(2026-07-30):六腿實跑覆蓋率 100%
  (SXF 94.4%,稀疏腿真沒成交)。**推論邊界:MTWN SubHistory 逾時空 = 該檔本身無資料,
  不能推論整個 SGX 段不支援** — 單檔無資料 ≠ 交易所段不支援。1K row 另帶 `UpVolume`/`DownVolume`/`UpTick`/`DownTick`
  (= 內外盤量),首頁固定 50 列必須走 `iter_qry_pages` 收割。兩盤別各自完整落在單一 UTC 日 →
  回補窗用「當日 UTC 全天窗」即可。(Trigger:TC4 分鐘級回補 / 內外盤能量副圖)
- **TC4 1K 跨午夜(夜盤)時刻推導必走完整 UTC datetime 轉換,`+8 %24` 捷徑只對日盤安全**
  (2026-08-05):UTC 16:00 後的列日期會留在前一天 — 失效樣態「bar 都在、只有日期錯」。
  多段域走 `stock_source._taipei_dt_key`;1K 的 `Time` **本身已是終點標記,不加 1**(「+1 分」
  只屬牆上時鐘來源的 live 點)。allday 取數窗要前移一日到 UTC (start−1)16,parse 後以台北日期
  filter 掉 end+1 凌晨段。Date 欄 = UTC 日曆日是強佐證假設(真資料核對待 prod 重啟,見 `docs/next-time.md`);
  1K 的 Time 為終點標記同註於 `river_models.minute_end_from_1k`。
  (Trigger:夜盤 1K / 分鐘域 / 近全序列)

- **TC4 1K 首頁 30s timeout 在早晨冷啟動是高機率事件,且 `_collect_history` 對 timeout
  靜默回空(不 raise)**(2026-08-13 實證,連三早晨 3/3:08:23 / 08:58 / 08:01;盤後閒時啟動
  則秒回):TC4 剛開 + server 同時搶 255 檔個股訂閱 + 6 腿 river 回補時,IX0001 1K 首頁
  30s 內備不齊。caller 拿到空 dict 與「該日真無資料」不可分 → 任何把「開機那一次回補」
  當唯一資料源的設計都會靜默失去全日資料。同日另實證:**REALTIME 推播可整段靜默
  (「訂閱成功但零推播」家族)而同 session 的 1K 歷史照常可取**(盤中 minutes 全空、
  14:52 同 session 當場取回 270 根)→ 修復用「產出面覆蓋度偵測 + 重掛/重抓自癒」
  (index_engine 分時自癒,grep `index 分時自癒`),不是猜輸入面哪環死了。
  (Trigger:設計任何「開機回補 + 推播增量」的資料鏈 / 排查分時線缺失)
- **1K history 訂閱在「窗內無資料時建立」會進「凍結 stub 態」,同窗口重送 SubHistory
  永不恢復**(2026-08-14 實證,fix/index-line-vanish 三組受控實驗 + prod 全日事故):
  (a) 毒化態下 GETHISDATA 回**單列凍結 stub**(Time = 訂閱建立時刻、Close 隨當下現價
  漂)而**非空頁** — 「首頁非空即 break」的 ready-check 會被騙,`timed_out=False` +
  一列垃圾,全鏈零 log;symbol 本身也死(pre-open)時才是恆空 → 30s timeout。
  (b) 窗內資料出現後,同窗口重送 SubHistory + GETHISDATA("0") 依然只回那根凍結 stub
  (實測 40 分鐘後仍凍在建立分鐘)。(c) **逃逸維度只有兩個**:換窗口字串(同 session、
  同 symbol、僅 end hour +1 即是全新訂閱,實測立即取回全量)或換 session。(d) 健康
  訂閱(建立時窗內有資料)不受影響:分頁 cursor 消耗殆盡後重問 "0" 永遠從頭給。
  對策 pattern:`fetch_day_minutes(window_variant=)` 窗口階梯 + 引擎「新分鐘鍵差量」
  進展判定(值漂不算進展;絕對 lag 也不是判準 — 部分回補是真進展);log 簽名 =
  「rows 非空但解析後全域外」grep `疑似凍結 stub`。**姊妹 ready-check(river_backfill /
  stock backfill / _fetch_symbol_ticks)未收緊**,見 docs/next-time.md 2026-08-14 節。
  (Trigger:任何 SubHistory/GETHISDATA 輪詢迴圈 / 空窗訂閱重試設計 / 排查「回補回垃圾」)
- **TICKS 歷史訂閱盤前(窗內無資料時)建立只會 30 s 逾時,**不**進凍結 stub 態;同窗口盤中重送 SubHistory 即取回全量**(2026-08-28 prod 實錄:主圖 6207 08:15 入列 → 逾時 ×2 → 08:16「放棄」,09:02 同窗再訂 117 筆;與上條 1K 的行為不同)。代價是每檔佔單工 worker 30 s —— 「訂閱當下就入列」對 40 檔自選 = 20 分鐘必敗 REQ,回補入列要等「有成交」的正面訊號(stock_engine 首筆當日成交 tick 入列,perf/opening-backfill-parallel)。另:**個股回補一秒一檔不是 TC4 慢**——SubHistory 後首頁備妥約 0.2 s(probe 08-28:20 檔逐檔 1.16 s/檔 vs 先全訂再收割 0.17 s/檔,tick 逐檔相等零逾時;真資料成本 3481 44k ticks 0.98 s),整批 SubHistory 40 檔 TC4 吃得下。(Trigger:設計個股 / 合約 TICKS 回補的入列時機或批次)

## 指數與期指

- **TC4 指數/日 K**(2026-07-28 盤中):加權 = `TC.S.TWS.IX0001`(REALTIME 含五檔/高低/漲跌停鍵);
  TWS 指數目錄 81 檔;**櫃買指數不在 TC4 symbol 樹**(掃盡皆無)→ 走 TPEx MIS poll。
  **現貨段(`TC.S.*`)只有台股 TWS 一段**(2026-07-29:美股 102 組合、港日星陸 8 種全滅,
  AAPL 當對照)— 美股個股與美股現貨指數不在達錢 4 產品線內,訂閱等級再高也拿不到。
  probe 工具:`spikes/index_symbol_probe.py` / `index_node_probe.py`。(Trigger:訂指數 / 查存在性)
- **指數 / 期指 K 線邊界**(2026-07-30 夜盤):(a) `IX0001` DK 5 年窗實回 748 根(≈3 年,TC4 端
  深度上限),`tf=1` 正常;(b) 期指 DK 深度 5 年:TXF/MXF 各 1213 根;(c) **指數的 DK/1K 沒有
  量欄位**(缺值回 0 → 整條 `v=0`)— 判定量之有無要看資料(`any(v>0)`)不看商品類別;
  (d) **期指 1K 分鐘域 08:46–13:45 不是個股的 0901–1330** — 套個股尺會靜默丟開盤前 15 分 +
  錯併 13:31–13:35 + 丟 13:36–13:45,圖照樣畫得出來零 assertion 紅。`stock_source.parse_1k_bars(rows,
  domain)` 的 domain 參數為此而開(`FUTURES_MINUTE_DOMAIN`);(e) 冷載入耗時 0.02–0.04s,
  不需非同步化。(Trigger:指數/期指歷史 K 線 / 量副圖 / 分鐘域轉換)

- **期指 `ReferencePrice` = 期交所當日結算價,不是日盤收、不是夜盤收**(2026-08-27 實測,/pr-review 127 F-03):
  16:34(夜盤已開)`/api/futures/state` TXF `ref` = 46064;FinMind `TaiwanFuturesDaily` TX 202609 同日
  `settlement_price` = 46064、日盤 `close` = 46078、after_market `close` = 45993。故日盤 08:45 起看到的 `ref`
  = 前一交易日結算價,夜盤 15:00 起換成當日結算價 —— 15:00 起算的一天只有一個基準。個股分時圖「台指期」
  疊線的相對 % 與期貨 tab 漲跌色都拿這一格。單筆樣本;結算價與收盤價恰好相等的日子分不出來,要再驗挑差異日。
  (Trigger:任何拿期指 `ref` 當昨收 / 算 % 的地方)

## 海外商品(2026-07-29/30 實證,realtime-correlation)

- **台期交自己就有美國四大指數期貨**:`UDF` 道瓊 / `SPF` 標普 / `UNF` 那斯達克 / **`SXF` 費半**
  (另有 `SOF`)— 全在 `TC.F.TWF.*`,台幣計價同時段同結算。**查商品必查 catalog 中文名(CHT 欄)
  不能只比對 symbol 前綴**(連掃兩輪才發現費半)。
- **但台期交這幾檔流動性極差**(SPF 近 60 日 57 天 <100 口)→ 日 K 收盤不是市場定價;道瓊/標普/
  納指改用 CME/CBOT 的 `YM`/`ES`/`NQ`(量大數千倍),費半無 CME 對應只能 SXF。
- **富台** = `TC.F.SGX.TWN.HOT`(`MTWN` 小富台 SubHistory 逾時空);**SGX 在台灣連假照開** →
  富台 929 根 vs 台指 860 根,配對計算必須取交集日。
- **海外期貨 DK 收盤時點 = 該市場收盤**(美股期貨 `Time=210000` = 美東 16:00),與美股現貨日 K
  日界天然對齊。
- **訂閱海外腿用全天窗**(`corr_source.py` 覆寫 `_rt_request` 為 `all_day_window()`)— 基底寫死
  台指盤別窗,而 TC4 對訂閱一律回 OK,窗不匹配的失效樣態是「訂閱成功零推播」。誠實記帳:
  「沿用 session 窗會失效」是推論不是實證 — 台指日盤窗(UTC 00–06)+ 夜盤窗(UTC 06–22)
  合計涵蓋 UTC 00–22,海外近 23 小時交易的時段幾乎都落在其中之一,訂閱當下不會落窗外;
  真正的風險是「跨過窗結束邊界(UTC 06 或 22)推播是否停止」,需跨邊界連續觀察才能驗。
- SXF 推播密度隨時段差異極大(146 則/60s vs 2 則/40s)。**日盤 4 分鐘零推播是常態**(2026-08-27 09:45–13:01
  R2 240 s 自癒 11 發全 attempt 1),對它的 symbol 級自癒只會 churn;已以設定檔 `sparse: true` 豁免 R2(仍吃 R1)。
  **VX(VIX 期貨)同型**:台北 08:00–10:00 是美盤夜間段,2026-08-28 08:47–09:55 R2 7 發全 attempt 1 真沒成交
  → 08-28 起也標 `sparse: true`(`tests/test_corr_config.py` 鎖集合 {SXF, VX})。
  另:2026-08-28 起 `tc4._note_push` 以推播指紋(PreciseTime / TradeDate / TradeVolume / TradingPrice)辨識
  重掛後 10 s 內的 SUBQUOTE snapshot,**不清** attempts —— 之後 log 裡「attempt 恆 1」才真的代表中間有推播。
  **08-28 指紋規則之前的 log,「attempt 恆 1」不能當「中間有真成交」的證據**:重掛的 SUBQUOTE 本身會回 snapshot
  (本節 fresh subscribe 事實),當時 `_note_push` 無條件清 attempts —— 08-27 SXF 有兩發間隔剛好 240 s
  (10:22→10:26、11:04→11:08)就是 snapshot 撐出來的,IX0001 收盤段 13:25–13:35 每 30 s 一發 attempt 全 1 同理。
  判稀疏腿一律看「日盤真成交間隔常 ≥ 門檻」(1K 或 tick 密度),不看 attempt(修後的 attempt 階梯只證明「有推播」,
  仍不證明「有成交」)。
- **日經有、韓指無(2026-08-17 重跑 Fut 全量 dump 實證)**:17 個交易所段與 06-30 快照零增減,
  **無 KRX 段、全樹零命中 KOSPI** → 韓指做不到(D14 拍板不做不追蹤)。日經三處:OSE
  `TC.F.OSE.{NK225,NK225M,NK225MC,NK400}.HOT`、SGX `TC.F.SGX.NK.HOT`、CME `NKD`。夜盤 60s 推播
  MES 219 / NK225 102 / **NK225M 175** / SGX NK 78,首分鐘 1K Volume NK225M 3285 vs NK225 182 →
  相關係數第七腿選**小日經 `NK225M`**。OSE 段 `FilledTime` 6 位 HHMMSS(同 CME/SGX)、
  `PreciseTime` 12 位、五檔 Bid/Ask 同欄名,`parse_stock_realtime` / `minute_end_from_utc_hhmmss`
  / 1K `parse_1k_minutes` 零改即通;OSE `OpenTime=160000 / CloseTime=144500`(台北時刻,夜盤
  16:00 → 次日 14:45)。腳本 `spikes/nk225_leg_probe.py`(記得只 probe 未被 prod 訂閱的 symbol)。
- **CME single stock futures(含 TSMC ADR)2026-07-27 上市,達錢 4 尚未上架**:55 檔美股 +
  22 檔微型、現金結算、**一天 23 小時交易 — 台股盤中也會有 TSM 連續報價(ADR 現貨在台股
  盤中休市),這是值得定期回頭確認上架的原因**。實測 64 種命名組合全 fail(對照組 ES 回 OK);
  上架後在 `configs/correlation.json` 的 `legs` 加一筆即可。
  (Trigger:接海外商品 / 選指數資料源 / 繼承 TC4QuoteSource / 評估 TSM 資料源)

## 個股期 / TXO / 權證

- **個股期不在 Fut 商品樹但可訂閱**:`TC.F.TWF.<期交所兩碼+F>.HOT`(CDF=2330);對映靠期交所
  清單頁(`copycat/stkfut_map.py` refresh CLI),**同股號標準(2,000 股)/小型(100 股)並存取
  契約單位大者**;推播 `SecurityName` 帶「名稱(股號)」可交叉核對。(2026-07-21)
- **TXO 序列動態發現**:月選(TXO)第三週三到期後即從合約清單消失;週選 TX4/TX5(+TXY/TXZ
  待確認)同月並存 → 序列清單每次跟 TC4 查,不可 hardcode。(2026-07-18,Trigger:序列選單/合約發現)
- **台股權證涵蓋待驗**(Phase 2 啟動前):官方文件只給 TXF 範例,權證涵蓋不明;若沒涵蓋,
  Phase 2 改 fallback FinMind 權證分點 + TPEx 公開資料。

## 市場資料語意(回測 / 統計前必讀)

- **prev_close 語意 = 當日 close − spread(除權息參考價),neigui 同源**;`DailyIndex.ref_prev_close`
  row-level 處理 spread 缺值(None → fallback 前日 close)。不要用「前一日 close」直接當參考前收。
  (2026-07-07,Trigger:漲停價/報酬率計算)
- **neigui 種子事件池不可當母體**:系統性漏收約三分之二真收盤漲停(母體 10,900 vs 種子 3,511)。
  `scan-events` CLI 已自產補全(產物 `data/events/events.csv` + limitup_all 同步);
  引用種子池結論或做母體統計前先跑 scan-events。
  (2026-07-07/10,Trigger:引用回測結論 / 算 base rate / 以事件池當母體)
- **模擬器出場 status 的入統計集合 = `fade_simulate.TRADEABLE_STATUSES` 單一定義**;新增出場
  status 只改這一處(曾因 guard_exit 只加一邊 → 最差虧損被靜默剔除 → 期望值灌水)。
  `pipeline.py`(舊 T 日)另有自己的 `_TRADEABLE`,兩者不通用。(2026-07-11,Trigger:模擬器出場 status)

## 群益 Capital(SKCOM)

- **關鍵事實**(2026-07-28,詳 docs/research/2026-07-28-skcom-typelib.md):(a) 期權下單共用
  `FUTUREORDER` struct(`SendFutureOrder`/`SendOptionOrder` 同簽名);刪改減共用證券 BySeqNo
  家族(帳號換期貨戶)。(b) **test 沙盒此帳號未開通**,登入恆 1097 — 送單面驗證只能 FakeCom +
  prod 安全首單(遠價 1 單位 → APP 核對 → 刪單)。(c) nQty:證券=張 / 期貨=口。(d) 期交所市價單
  限 IOC/FOK(ROD+市價會退單);期貨平倉走限價貼漲跌停+IOC。**此條只對期交所**:證交所逐筆交易的
  現股市價 ROD 合法(鎖停日簿頂 price=0 的「市價佇列」就是留存簿中的未成交市價 ROD 單;2026-08-17
  batch3 R1 review 曾誤套此條,機械反證後現股閃電梯市價鈕維持 market+ROD)。(e) OnAccount/OnOpenInterest 欄序
  為未實測假定,首次 prod 登入要核對。(Trigger:碰 copycat/capital / 群益送單欄位 / 驗證方式)
- **SKCOM 事件字串的中文欄位在本機是不可逆亂碼,勿依賴中文標籤解析**(2026-08-20 prod 實證):
  `OnProfitLossGWReport` 整列中文欄(股名/幣別/種類)損毀 —「現股」→`'2{aN'`、「融資」→`'?A﹐e'`,
  形態 = Big5 bytes 被當 CP1252 解讀再 best-fit 壓回 ASCII(`¸`→`,` 再被轉全形 `﹐`),多對一不可逆;
  系統 ACP=950 正常,損壞在 SKCOM 自身鏈路。數字欄不受影響。**種類判定走 [25] 代碼備援**
  (現股=1/融資=2,06-11 乾淨樣本 + 08-20 亂碼樣本雙源交叉;融券代碼未實證不對映)—
  `balance.py::_PNL_KIND_CODE`。06-11 的乾淨中文 fixture 說明鏈路曾正常,何時壞掉未知;新接任何
  SKCOM 事件欄位一律優先用代碼/數字欄,中文欄當 display-only。(Trigger:解析任何 SKCOM 事件字串)
- **`OrderRecord.date` / `time` 來自回報 idx23 / idx24,`CapitalStore.apply_reply` 對每筆回報「有值就覆寫」
  —— 但覆寫進來的值在跨日事件會不會變,未實證**(2026-08-17 R2 review 只核了覆寫機制;08-28 pr-134
  review F-01 撞到 `reply.py` 記「同日 C / D 回報 idx23 / idx24 仍為原單日期」,06-10 真樣本 N / C 逐字相同,
  repo 內零跨日事件樣本)。兩種可能:idx23 隨事件變 → 昨日建立今日成交的單 `date` 是今日、`avg_fill_price`
  是昨日的,任何以 `date` 當日期界的前端聚合(`ladder-lots.ts` 三梯徽章、`fill-marks.ts` 成交點)擋不住跨日
  均價;idx23 不變 → `date` 就是委託建立日,前端日期界成立。要真擋只能後端留逐筆 D 事件(精確版,next-time)。
  另 06-10 預約單樣本 **idx29**=`20260611`(隔日,= 該單所屬交易日?;idx28 恆 `PI`,pr-134 報告 F-07 寫 idx28 為誤)疑似另有交易日欄,`reply.py` 未解析。
  **拿到第一筆跨日事件(昨日掛、今日成交 / 刪單)的 raw 回報就能定案** —— 看 idx23 / idx29 各是哪一天。
  (Trigger:任何吃 CapitalOrder date/time 做日期界或時間定位的功能;任何宣稱 `_Agg.date` 語意的 docstring)
