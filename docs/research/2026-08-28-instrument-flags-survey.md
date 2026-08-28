# 台股現貨旗標資料源調查(2026-08-28,B2 調研)

> 目的:回答 `docs/next-time.md` 2026-08-13 節 / 2026-08-26 節累積的 B2 調研三題 ——
> 達錢 4(TC4)對台股現貨還能拿到哪些欄位?證交所/櫃買有沒有機器可讀的「當日可現股
> 當沖標的」「暫停交易」名單?FinMind `TaiwanStockDayTrading` / `TaiwanStockMargin
> PurchaseShortSale` 的 T 日資料幾點可取?user 08-28 拍板:當沖資格**不能用前一日
> 名單**,要當日的;順便盤點達錢還能拿到哪些欄位。
> 本報告只讀不改 code;探測腳本輸出留在 session scratchpad,未落版控。

## 結論先行

1. **達錢暫停交易 / 處置 / 當沖資格旗標:不可**——TC4 REALTIME quote 是 Fut/Opt/Fut2/
   股票共用同一份泛用電文 schema(§1),欄位裡沒有任何「暫停交易」「處置」「注意股」
   「當沖資格」「全額交割」的專屬旗標;`TradeStatus` 值域只有 `{0=正常, 1=試撮/延緩
   撮合中}` 兩檔,是**盤中撮合節奏**訊號,不是**法規身分**旗標(出處:官方 QuantBridge
   電文格式(行情篇)PDF `spikes/TCPY/QuantBridge電文格式(行情篇).pdf` p.7–9;`copycat/
   live/stock_models.py:211-215`;`.claude/skills/tc4-market-facts/SKILL.md` 鎖漲跌停節)。
   **可間接反推**:本專案 08-25 已實測「處置股分盤撮合」在 `TradeStatus` 上留下
   `1→0→1` 每 N 分鐘循環的行為指紋(2455,133 次/日),但這是**盤中觀測**,不是
   盤前可查的欄位(`docs/next-time.md` 2026-08-13 節 L557-562)。
2. **證交所 / 櫃買當日名單 API:可**——兩邊 OpenAPI 都有免 token 的 JSON 端點,今日
   (2026-08-28,`Date` 欄回 `1150828`)實測皆回**當日**資料:證交所
   `GET https://openapi.twse.com.tw/v1/exchangeReport/TWTB4U`(當沖標的全清單 1,232 檔)、
   `/announcement/notice`(注意股)、`/announcement/punish`(處置股)、`/exchangeReport/
   TWTAWU`(暫停交易);櫃買 `GET https://www.tpex.org.tw/openapi/v1/tpex_securities`
   (當沖標的全清單 844 檔)、`tpex_trading_warning_information`(注意)、
   `tpex_disposal_information`(處置)、`tpex_spendi_today`(暫停/恢復)、`tpex_cmode`
   (變更交易/分盤/列管/停止交易四合一)。**更新時刻未證**——官方頁面與 swagger 都沒寫
   明公布時刻,本次探測是收盤後(台北 16:23)打的,只能證實「當日資料收盤後已在」,
   證不了「盤前 08:30 是否已可用」。
3. **FinMind T 日可取時刻:部分可**——官方 `llms-full.txt` 明寫 `TaiwanStockDayTrading`
   「target list & BuyAfterSale marker available pre-market same day;volume/value 收盤後
   ~21:30 才更新」,即當沖資格名單本身**盤前就有 T 日的**,滿足「不能用前一日名單」;
   但 `TaiwanStockMarginPurchaseShortSale`(信用/融資融券)是 `Update: Mon-Fri 21:00`,
   T 日資料要**收盤後**才出,盤前只能拿到 T-1 的。`TaiwanStockDispositionSecuritiesPeriod`
   (處置)官方文件未寫更新時刻(未證),但本專案 `breadth_engine.py` 已知「處置股名單
   每天都變」故按交易日強制重抓(見 §4)。

---

## 1. 達錢(TC4)欄位總表

### 1.1 REALTIME quote(Fut / Opt / Fut2 / 股票共用同一份 schema)

來源:`spikes/TCPY/QuantBridge電文格式(行情篇).pdf`(用 `pdftotype.exe -layout` 轉存純文字
於 `spikes/TCPY/行情篇.txt`,原始 PDF 中文欄位說明因非嵌入字型多數遺失,以下以欄位名 +
本專案實測語意為準)p.7 起「1.」節 REALTIME Quote 欄位列表。股票 `TC.S.TWS.*` 走同一份
`Quote` dict,無專屬欄位——`copycat/live/stock_models.py::parse_stock_realtime` 讀到的鍵
與 PDF 泛用清單逐一對得上(唯一落差見表末備註)。

| 欄位 | 語意(官方文件 / 本專案實測) | 本專案是否已用 | 出處 |
|---|---|---|---|
| `Symbol` | 完整 symbol(如 `TC.S.TWS.2330`) | 否 | 行情篇 PDF p.7 |
| `Exchange` / `ExchangeName` | 交易所代碼 / 全名 | 否 | 同上 |
| `Security` | 股號本體(如 `2330`) | **是**(`stock_models.py:224`) | 同上 |
| `SecurityName` | 證券名稱 | **是**(`:202`) | 同上 |
| `SecurityType` | 證券種類 | 否 | 同上 |
| `TradeQuantity` | 該筆成交量 | **是**(`:217`) | 同上 |
| `FilledTime` | 成交時刻 HHMMSS(UTC) | 否(股票走 `PreciseTime`) | 同上;`tc4-market-facts` skill |
| `TradeDate` | 交易日期 | **是**(`:220`) | 同上 |
| `FlagOfBuySell` | 內外盤旗標(交易所端算好的) | 否(本專案自算 `derive_side`) | 同上 |
| `OpenTime` / `CloseTime` | 開盤/收盤時刻 | **是**(`:208-209`) | 同上 |
| `BidVolume`/`BidVolume1-9` | 五檔買量(位移命名,L0 無尾碼) | **是**(`_parse_levels`) | 同上 |
| `AskVolume`/`AskVolume1-9` | 五檔賣量 | **是** | 同上 |
| `TotalBidCount` / `TotalBidVolume` | 委買總筆數/總量 | 否 | 同上 |
| `TotalAskCount` / `TotalAskVolume` | 委賣總筆數/總量 | 否 | 同上 |
| `BidSize` / `AskSize` | 未查得確切語意(官方 PDF 中文說明遺失) | 否 | 同上,未證 |
| `FirstDeriveBidVolume` / `FirstDeriveAskVolume` | 衍生買賣量(未查得確切語意) | 否 | 同上,未證 |
| `BuyCount` / `SellCount` | 買賣筆數 | 否 | 同上 |
| `EndDate` / `BeginDate` | 未查得確切語意 | 否 | 同上,未證 |
| `BestBidVolume` / `BestAskVolume` | 最佳買賣量 | 否 | 同上 |
| `YTradeDate` | 昨交易日 | 否 | 同上 |
| `ExpiryDate` | 到期日(期權用) | 否 | 同上 |
| `TradingPrice` | 成交價 | **是**(`:216`) | 同上 |
| `Change` | 漲跌 | 否(本專案自算) | 同上 |
| `TradeVolume` | 當日累積量 | **是**(`:227`) | 同上 |
| `OpeningPrice`/`HighPrice`/`LowPrice`/`ClosingPrice` | 開高低收 | 否 | 同上 |
| `ReferencePrice` | 參考價(平盤) | **是**(`:203`) | 同上 |
| `UpperLimitPrice` / `LowerLimitPrice` | 漲停 / 跌停價 | **是**(`:204-205`) | 同上 |
| `YClosePrice`(PDF 命名)/ **實測鍵名 `YClosedPrice`** | 昨收價 | **是**(`:206`,鍵名見下方備註) | 同上 |
| `YTradeVolume` | 昨量 | **是**(`:207`) | 同上 |
| `Bid`/`Bid1-9` | 五檔買價(位移命名) | **是** | 同上 |
| `Ask`/`Ask1-9` | 五檔賣價 | **是** | 同上 |
| `PreciseTime` | 次秒級時刻(UTC) | **是**(`:220`) | 同上 |
| `FirstDeriveBid` / `FirstDeriveAsk` | 未查得確切語意 | 否 | 同上,未證 |
| `SettlementPrice` | 結算價(期貨用) | 否(期貨面另讀,見 skill) | 同上 |
| `BestBid` / `BestAsk` | 最佳買賣價 | 否 | 同上 |
| `Deposit` | 保證金(期貨用) | 否 | 同上 |
| `TickSize` | 檔位跳動單位 | 否 | 同上 |
| `TradeStatus` | 撮合狀態,實測值域 `{0,1}` | **是**(`:211-215`,僅觀測不丟棄) | 同上;見 §1.2 |

**備註(鍵名落差)**:PDF 文件寫 `YClosePrice`,但本專案 `stock_models.py:206` 實際讀的鍵是
`YClosedPrice`(多一個 `d`)。兩者出處分屬「官方靜態文件」vs「本專案對 prod payload 的
實測讀值」,未去信官方核對何者為現行版——**以本專案實測讀值為準**(讀不到就是 None,
已有 fixture/測試守著,見 `tests/live/test_stock_models.py` 系列)。

### 1.2 `TradeStatus` 值域與「處置股」行為指紋(本專案實測,非官方文件)

- 官方 PDF 對 `TradeStatus` 沒有中文說明可讀(非嵌入字型遺失)。
- 本專案 2026-07-21 盤中實測值域 `{0=正常, 1=試撮期簿更新}`(`.claude/skills/
  tc4-market-facts/SKILL.md` 個股 REALTIME 節)。
- 2026-08-21 M0 真樣本(`logs/server-20260821-0839.log`,13 個完整 episode)確認:
  `TradeStatus 0→1` 後約 2 分鐘變回 `0`,對應 TWSE「個股單筆爆量/爆漲跌觸發的延緩撮合
  2 分鐘」機制,`0→1` 那筆 tick 量極小(1–15 張)、`1→0` 那筆量大(62–608 張,= 延緩後
  集合競價成交)(`docs/next-time.md` 2026-08-13 節 L556-561)。
- 2026-08-25 真樣本(2455 全新,同日出現在 TWSE `/announcement/punish` 的處置清單,
  `DispositionPeriod` 115/08/24~115/08/28):`TradeStatus` **整天** `1→0→1` 循環,每 2 分鐘
  一次、共 133 次——這是「處置股分盤撮合」的行為指紋,與單次「延緩撮合」的差別只在
  **重複次數**(一次 vs 整天反覆),不是不同的欄位值(`docs/next-time.md` 同節 L557)。
- **結論**:TC4 沒有「這檔是不是處置股」的旗標欄位,但可以用「`TradeStatus` 整天反覆
  N 分鐘循環」這個**行為模式**在盤中即時反推。這是推論(pattern matching),不是欄位
  直讀;本專案 08-28 已拍板「處置股標示改用既有 breadth 引擎的 FinMind 名單(§4),不用
  這個行為指紋」(`docs/next-time.md` 同節,08-28 拍板句)。

### 1.3 商品目錄查詢(`QUERYALLINSTRUMENT` / `QUERYINSTRUMENTINFO`)——股票沒有專屬 Type

- 官方 wrapper 註解與 PDF 範例都只示範 `Type: "Fut"`(`spikes/TCPY/交易篇.txt:150-156`、
  `spikes/TCPY/行情篇.txt:95-99`);官方 wrapper `tcoreapi_mq.py:71-73` 的中文註解寫
  「期货:Future / 期权:Options / 证券:Stock」,但本專案 2026-07-21 / 07-28 兩輪實測
  這些字面值**全部 Fail**,唯一有效的三個 `Type` 字面值是 `Fut`(期貨)、`Opt`(期權)、
  `Fut2`(個股期貨,不是現股)——`docs/research/2026-07-21-stock-spot-quote-order-probe.md:16`、
  `.claude/skills/tc4-market-facts/SKILL.md` 訂閱節。
- 換句話說:**TC4 商品樹裡沒有「現股股票」這個可查詢的 Type**,個股只能用外部給的股號
  清單直接訂閱(watchlist 輸入制),存在性驗證走「訂閱後有無推播」而非目錄查詢。
- `QUERYINSTRUMENTINFO` 對股票 symbol 可查(存在性 oracle,對不存在 symbol 回 parse
  failed),回應內容是父節點層級的 `TickSize`/`OpenCloseTime` 等**契約屬性**,不含
  法規身分欄位(`docs/handoff-2026-07-28.md:46-48`;`.claude/skills/tc4-market-facts/
  SKILL.md` 訂閱節)。PDF 範例(期貨 `TC.F.TWF.FITX.201907`)回應欄位:`Duration`、
  `EXG.SIM`、`EXGName.CHS/CHT`、`OpenCloseTime`、`OrderType`、`OrderTypeMX`、
  `OrderTypeMX.TC`、`Position`、`ResetTime`、`Symbol.SS2`、`TimeZone`(`spikes/TCPY/
  交易篇.txt:210-224`)——同樣是**交易時段/委託型態**這類契約屬性,不是「暫停交易/
  處置/當沖」這類法規身分。

---

## 2. 交易所 API(證交所 / 櫃買 OpenAPI,今日實測)

探測方式:`curl` 直打 `swagger.json` 取得完整 path 清單 + 各端點 schema,再直接呼叫端點
驗證今日(2026-08-28,民國 1150828)確實回當日資料。以下端點皆**免 token**、回應含
`application/json` + `text/csv` 兩種格式。

### 2.1 證交所(TWSE)`https://openapi.twse.com.tw/v1`

| Path | summary | 回應欄位 | 今日實測 |
|---|---|---|---|
| `/exchangeReport/TWTB4U` | 上市股票每日當日沖銷交易標的及統計 | `Date`/`Code`/`Name`/`Suspension`(暫停現股賣出後現款買進當沖註記) | **1,232 列**,`Date` 全為 `1150828`;62 列 `Suspension="Y"` |
| `/announcement/notice` | 集中市場當日公布注意股票 | `Number`/`Code`/`Name`/`NumberOfAnnouncement`/`TradingInfoForAttention`/`Date`/`ClosingPrice`/`PE` | 今日回單列全空值(疑為「今日無新增注意股」的空態表示法,非端點失效) |
| `/announcement/punish` | 集中市場公布處置股票 | `Number`/`Date`/`Code`/`Name`/`NumberOfAnnouncement`/`ReasonsOfDisposition`/`DispositionPeriod`/`DispositionMeasures`/`Detail`/`LinkInformation` | 4 列,含 `DispositionPeriod` 涵蓋今日(如 `115/08/24～115/08/28`)的在途處置股 |
| `/exchangeReport/TWTAWU` | 集中市場暫停交易證券 | `Number`/`Code`/`Name`/`TradingHaltDate`/`TradingHaltTime`/`TradingResumptionDate`/`TradingResumptionTime` | 1 列(泰山 1218,08/13-08/14 舊事件,疑似滾動窗非嚴格「今日」) |
| `/exchangeReport/TWTBAU1` | 集中市場暫停先賣後買當日沖銷交易標的預告表 | `Code`/`Name`/`StartDate`/`EndDate`/`Reason` | 未實測(schema 已取得) |
| `/exchangeReport/TWTBAU2` | 同上歷史查詢 | 同上 | 未實測 |
| `/exchangeReport/TWT85U` | 集中市場證券變更交易 | `Code`/`Name`/`PeriodicCallAuctionTrading`(分盤集合競價) | 未實測 |

### 2.2 櫃買中心(TPEx)`https://www.tpex.org.tw/openapi/v1`(302 導轉自 `/openapi/`)

| Path | summary | 回應欄位(實測鍵名) | 今日實測 |
|---|---|---|---|
| `/tpex_securities` | 上櫃股票現股當沖交易標的資訊 | `資料日期`/`證券代號`/`證券名稱`/`暫停現股賣出後現款買進當沖註記` | **844 列**,`資料日期="1150828"` |
| `/tpex_spendi_today` | 上櫃當日公布暫停/恢復交易股票 | `Date`/`SecuritiesCompanyCode`/`CompanyName`/`暫停交易`/`恢復交易` | 今日回單列全空值(今日無新增) |
| `/tpex_disposal_information` | 上櫃處置有價證券資訊 | `Date`/`SecuritiesCompanyCode`/`CompanyName`/`DispositionPeriod`/`DispositionReasons`/`DisposalCondition` | 22 列,含涵蓋今日的在途處置 |
| `/tpex_trading_warning_information` | 上櫃公布注意股票資訊 | `Date`/`SecuritiesCompanyCode`/`CompanyName`/`TradingInformation`/`ClosePrice`/`PriceEarningRatio` | 27 列 |
| `/tpex_cmode` | 上櫃股票變更交易、分盤交易、管理股票與停止交易資訊 | `Date`/`SecuritiesCompanyCode`/`CompanyName`/`AlteredTrading`/`PeriodicTrading`/`ManagedStock`/`MatchingFrequency`/`SuspensionOfTrading`/`FinancialAnnouncements` | 21 列,`Date="1150828"` |
| `/tpex_intraday_trading_pre` / `_his` | 上櫃暫停先賣後買當沖標的預告 / 歷史查詢 | 同 TWSE TWTBAU1/2 對應版本 | 未實測 |
| `/tpex_margin_trading_term` | 上櫃融資融券暫停融券賣出預告表 | 未展開 | 未實測 |

**更新時刻:未證**。官方頁面(`https://www.twse.com.tw/zh/page/trading/exchange/
TWTB4U.html`)只寫「本資訊自民國103年1月6日起開始提供」,沒有公布時刻;swagger.json
本身也不含更新頻率欄位。本次探測是台北 16:23(收盤後)打的,`Last-Modified` header(TPEx
回的)也是當天 08:11 UTC(=台北 16:11)——只能證實「收盤後已更新」,**證不了盤前
08:30 是否已是當日名單**,要盤前實測才能定案。

**全額交割股:未查得獨立端點**。TWSE/TPEx OpenAPI 的 swagger 都搜不到「全額交割」
字樣;現行 schema 只看得到「變更交易」(`TWT85U`/`tpex_cmode.AlteredTrading`+
`PeriodicTrading`)這個較上位的類別,「全額交割」是否已被併入其中一項測度、或完全
沒有機器可讀來源——未證,需要另外查證交所現行規則對照(不在本次調研範圍內完成)。

---

## 3. FinMind

來源:`https://finmind.github.io/llms-full.txt`(官方文件原始檔,直接 `curl` 讀取全文,
非 WebFetch 摘要;WebFetch 對同一頁的摘要曾把更新時間翻成英文, 已改用原始檔核對逐字)。

| Dataset | Tier | Update(原文) | 對本專案的意義 |
|---|---|---|---|
| `TaiwanStockDayTrading`(當日沖銷交易標的及成交量值) | Free(帶 data_id)/ Sponsor(全市場) | **"target list & BuyAfterSale marker available pre-market same day; volume/value(Volume/BuyAmount/SellAmount)updated after close ~21:30"** | 當沖資格名單本身**T 日盤前就有**,滿足「不能用前一日名單」;但成交量值欄位要收盤後 21:30 才補齊 |
| `TaiwanStockMarginPurchaseShortSale`(個股融資融劵表) | Free(帶 data_id)/ Sponsor(全市場) | `Mon-Fri 21:00` | 信用/融資融券餘額**T 日收盤後才出**,盤前只能拿到 T-1 資料——若要判定「T 日信用當沖資格」不能只靠這支 dataset 盤前查詢 |
| `TaiwanStockDispositionSecuritiesPeriod`(公布處置有價證券表) | Backer/Sponsor | 官方文件**未寫更新時刻**(未證) | 本專案 `breadth_engine.py` 已知「處置股名單每天都變」,故按交易日邊界強制重抓(§4);未證盤前幾點可取 T 日新增處置 |

`BuyAfterSale` 欄位語意(官方文件逐字):`＊` = 該股被停止「先賣後買」當沖(仍可先買後賣);
`Y` 或空白 = 兩個方向都允許。**注意**:這欄只反映「交易所層級」的股票資格,實際能不能
先賣後買還要看券商當下的借券庫存與投資人本身的信用資格——這點與本專案 `tc4-market-
facts` skill 既有教訓(`TaiwanStockDayTrading` 的 `BuyAfterSale` 'Y' 或 '＊' = 僅可先買後賣)
用語略有出入,以官方文件逐字為準:**只有 `＊` 才是「僅可先買後賣」,`Y` 是兩個方向都可**
——本專案既有 skill 文字有誤,已在 §4 記為待收修項。

**配額**:接入慣例、6000 req/hr rolling window、Bearer token 認證等既有事實見專案 skill
`finmind-conventions`,本次調研沒有新發現需要更動。

**本專案既有用法**:`copycat/data/backfill_daytrade.py` 已用 `TaiwanStockDayTrading`,但是
**事後 proxy**(「該股當日出現在 TaiwanStockDayTrading = 有當沖成交」),用於回測標記
漲停股次日可否當沖,**不是**即時盤前查詢——與這次 user 想要的「T 日盤前就知道能不能
當沖」是不同用途(前者容忍事後統計偏差,後者要即時正確)。

---

## 4. 對 copycat 的含意(列選項,不做決策)

1. **現股當沖資格盤前判定**:FinMind `TaiwanStockDayTrading` 的名單欄位(`BuyAfterSale`)
   官方保證盤前可取,是唯一同時滿足「機器可讀 + T 日 + 盤前」的來源;若要在盤前秀
   「今天能不能當沖」,走這支 dataset 比 TC4(完全沒有欄位)或證交所/櫃買 OpenAPI
   (更新時刻未證)都更有把握——但仍要盤前 08:30 左右實測驗證 pre-market 是否真的
   已生效,不能只信文件字面。
2. **信用當沖資格**沒有一個「T 日盤前」的機器可讀來源:FinMind `TaiwanStockMargin
   PurchaseShortSale` T 日 21:00 後才更新,TWSE/TPEx OpenAPI 相關端點更新時刻未證。
   若要盤前判定信用當沖資格,選項有限:(a) 接受用 T-1 資料當近似值(有失真風險,尤其
   當日剛被停資/停券的股票會誤判)、(b) 找 TWSE/TPEx 有沒有專屬「暫停融資/融券」端點
   並盤前實測時刻(本次只找到 swagger 有 `/tpex_margin_trading_term` 上櫃融資融券暫停
   融券賣出預告表,細節未展開)、(c) 問群益 SKCOM 有沒有帳戶層級的信用資格查詢
   API(`.claude/skills/tc4-market-facts/SKILL.md` 已記「SKCOM 有無資格查詢 API 未查」)。
3. **暫停交易 / 處置股**盤中顯示,TC4 本身給不出旗標,兩條路:(a) 沿用本專案既有
   `breadth_engine.py` 的 FinMind `TaiwanStockDispositionSecuritiesPeriod` 名單(已在跑,
   已知「每天都變」故按交易日重抓,見 `breadth_engine.py:434-436`),(b) 改打證交所/
   櫃買 OpenAPI 的 `/announcement/punish` + `tpex_disposal_information`(本次證實免
   token、今日資料已在,且欄位比 FinMind 版更細:有 `DispositionMeasures`/`Detail` 逐字
   說明處置措施,FinMind 版只有 `condition`/`measure` 代碼)——換源要衡量「多一個
   外部相依」against「更即時/更細的措施說明」,屬方向性抉擇,不在本次調研範圍內拍板。
4. **`TradeStatus` 的處置行為指紋**(§1.2)本專案 08-28 已拍板不用來判定處置身分
   (改用 FinMind/交易所名單),但它對「盤中暫緩撮合」(非處置,單次 2 分鐘事件)這個
   完全不同的現象仍有用——兩者不要混為一談,是本次調研順手核實的既有教訓。
5. **skill 文字待收修**:`.claude/skills/finmind-conventions/SKILL.md` 附錄現寫
   「`TaiwanStockDayTrading` 的 `BuyAfterSale` 欄位 'Y' 或 '＊' = 僅可先買後賣」,但官方
   `llms-full.txt` 原文是「`＊` = 停先賣後買(僅可先買後賣);`Y` 或空白 = 兩方向皆可」——
   `Y` 被本專案 skill 誤歸類為限制態,方向錯了。本次調研只負責記錄落差,skill 本體
   修正留給下一輪 `/mod` 或 `/chore` 動手。

---

## 來源清單

- 官方電文格式 PDF(本機):`spikes/TCPY/QuantBridge電文格式(行情篇).pdf`、
  `spikes/TCPY/QuantBridge電文格式(交易篇).pdf`(以 `pdftotext.exe -layout` 轉存純文字
  比對,轉存檔案未落版控)。
- 官方 wrapper:`spikes/TCPY/tcoreapi_mq.py`、`spikes/TCPY/quote_sample.py`。
- 本專案原始碼:`copycat/live/stock_models.py`、`copycat/data/backfill_daytrade.py`、
  `copycat/market_breadth.py`、`copycat/server/breadth_engine.py`、`copycat/server/
  breadth_fetch.py`、`copycat/live/tc4.py`(`Fut2` 個股期查詢)。
- 本專案既有調研:`docs/research/2026-07-21-stock-spot-quote-order-probe.md`、
  `docs/research/2026-07-18-txo-chain-probe.md`、`docs/handoff-2026-07-28.md`、
  `docs/next-time.md`(2026-08-13 / 2026-08-26 節)、`.claude/skills/tc4-market-facts/
  SKILL.md`、`.claude/skills/finmind-conventions/SKILL.md`、`.claude/mod/trial-pause-badge/
  change-spec.md`、`.claude/feat/stock-terminal/design.md`。
- 證交所 OpenAPI:`https://openapi.twse.com.tw/v1/swagger.json`(2026-08-28 台北 16:23
  抓取)、`https://openapi.twse.com.tw/v1/exchangeReport/TWTB4U`、`/announcement/notice`、
  `/announcement/punish`、`/exchangeReport/TWTAWU`、`https://www.twse.com.tw/zh/page/
  trading/exchange/TWTB4U.html`。
- 櫃買 OpenAPI:`https://www.tpex.org.tw/openapi/swagger.json`(302 → `/openapi/v1/
  swagger.json`)、`https://www.tpex.org.tw/openapi/v1/tpex_securities`、
  `tpex_spendi_today`、`tpex_disposal_information`、`tpex_trading_warning_information`、
  `tpex_cmode`。
- FinMind:`https://finmind.github.io/llms-full.txt`(原始檔直接 curl,2026-08-28 抓取)。
