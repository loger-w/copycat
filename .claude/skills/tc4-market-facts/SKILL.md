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
- **TC4 同 symbol 跨 session 只推一邊**(2026-07-28 夜盤三次重啟實證):TXO runtime 已訂
  `TC.F.TWF.TXF.HOT` 時,futures engine 同 symbol SUBQUOTE 回 OK 但永收不到推播。解法 = 訂實際
  月份 leaf 契約(symbol 字串不同即無衝突;futures_engine leaf fallback:resolve 已知後寬限 3s
  仍零推播才補訂,換月靠跨日清 p 重武裝)。**2026-07-30 補實證:leaf fallback 有前提(要先由
  推播解析出契約月份,全部商品零推播時啟動不了),且 futures_engine 會間歇性整段零推播**
  (實測兩個相反狀態並存,觸發條件未定位)。**新引擎不要假設「讀既有 engine 的 state 一定拿得到
  行情」**——要嘛自己有 fallback,要嘛把「上游空著」當正常狀態處理(corr_engine 選後者:base 腿
  無資料回 None 不假造)。修法候選見 `docs/next-time.md`。(Trigger:新引擎訂既有模組已訂的 symbol、或讀既有 engine state 當資料源)
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
- **`PreciseTime` 欄寬跨交易所段不同,`FilledTime` 才是通用的**(2026-07-30 實證):台期交(TWF)
  是 `HHMMSSffffff`(11–12 位),**CME/CBOT/SGX 是 `HHMMSS`**。`stock_models._taipei_time` 的
  `zfill(12)` 對海外段會把 6 位值左補 → 恆為台北 08:00:00.0xx 的假時刻,tick 照樣解析成功只有
  時刻是假的(極安靜)。任何跨段用 tick 時刻的功能一律走 `FilledTime`(UTC HHMMSS,zfill(6);`index_engine` 對
  IX0001 也是用它;實例:MES 的 PreciseTime 與 FilledTime 同值 `"41256"` = 04:12:56 UTC),
  缺值才退回本機時鐘。(Trigger:跨段 tick 時刻 / 分鐘聚合 / 時序去重)
- **個股 REALTIME 實測事實**(2026-07-21,stock-terminal):上市+上櫃**全掛 `TC.S.TWS.<code>` 段**
  (TWO/TPE/OTC 段無推播);推播自帶完整五檔+漲跌停/參考價;**試撮期(13:25–13:30)TC4 不推
  成交 tick**(時間窗過濾為雙保險),`TradeStatus` 值域實測 {0=正常, 1=試撮期簿更新};**盤後
  fresh subscribe 會回當日收盤 snapshot**(延遲分鐘級)。(Trigger:個股訂閱 / 試撮處理 / 盤外顯示)

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
  靜默回空(不 raise)**(2026-08-13 實證,連續兩早晨 2/2:08:23 / 08:58;盤後閒時啟動
  則秒回):TC4 剛開 + server 同時搶 255 檔個股訂閱 + 6 腿 river 回補時,IX0001 1K 首頁
  30s 內備不齊。caller 拿到空 dict 與「該日真無資料」不可分 → 任何把「開機那一次回補」
  當唯一資料源的設計都會靜默失去全日資料。同日另實證:**REALTIME 推播可整段靜默
  (「訂閱成功但零推播」家族)而同 session 的 1K 歷史照常可取**(盤中 minutes 全空、
  14:52 同 session 當場取回 270 根)→ 修復用「產出面覆蓋度偵測 + 重掛/重抓自癒」
  (index_engine 分時自癒,grep `index 分時自癒`),不是猜輸入面哪環死了。
  (Trigger:設計任何「開機回補 + 推播增量」的資料鏈 / 排查分時線缺失)

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
- SXF 推播密度隨時段差異極大(146 則/60s vs 2 則/40s)。
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
  限 IOC/FOK(ROD+市價會退單);期貨平倉走限價貼漲跌停+IOC。(e) OnAccount/OnOpenInterest 欄序
  為未實測假定,首次 prod 登入要核對。(Trigger:碰 copycat/capital / 群益送單欄位 / 驗證方式)
