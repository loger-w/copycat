# 達錢 4(Touchance 4.0)個股現貨:即時行情 ✅ / 下單涵蓋 ❌(平台面)實測報告

> 目的:驗「個股現貨下單是否被 Touchance 涵蓋」+「個股即時行情抓不抓得到」,給下一批(個股 + 個股期)開工定路線。
> 測試日 2026-07-21(週一)盤中 10:56–10:58。TC4 本機常駐(10:24 起),Quote RepPort 50774 / Trade RepPort **50744**(當日 log;trade 預設 51207 不可寫死,同 quote 一樣要從 `TradeZMQService-*.log` 抓)。
> 探測腳本:session scratchpad `probe_stock_spot.py`(依 2026-07-06 報告 §8 樣板 + 07-18 REALTIME 帶時窗修法)。

---

## TL;DR

| 問題 | 答案 |
|---|---|
| 個股即時行情(REALTIME push)? | 🟢 **可以**。`TC.S.TWS.2330` 盤中 20 秒收 27 筆推播,`TradeVolume` 為當日累積量(12479→12481)、`Bid`/`Ask` 有值、`FilledTime` UTC+8 換算與牆鐘吻合 |
| 個股現貨下單走 TC4 OpenAPI? | 🔴 **平台面不涵蓋**。官方合作夥伴全數為期貨商(台新/群益/富邦/統一/凱基),無任何證券商;「證券加值服務」是 MultiCharts 專屬加值路線(非 ZMQ OpenAPI),且原公告頁已 404 |
| 本機 trade port 現況? | LOGIN OK 但 `ACCOUNTS` 回 `[]`(TC4 log `m_strLoginType=` 空)— **TC4 目前未登入任何交易帳戶**(期貨帳戶也沒有);下單面連期貨都尚未可實測,與「期貨商 API 權限延後申請」一致 |
| 商品樹查得到股票嗎? | 🔴 `QUERYALLINSTRUMENT` Type=`Stock`/`Stk`/`Sec`/`Equity` **全部 Fail**(wrapper 註解寫 `Stock`,現版 drift)。股票 symbol 存在性只能靠「訂閱後看有沒有推播」驗證 |

## 1. 行情面細節 🟢

- 訂閱電文與 TXO 完全同款:`SUBQUOTE` + `SubDataType: REALTIME` + 當日 UTC 窗(`2026072100`~`2026072106`),回 `Success: OK`,SUB socket 即有推播。`copycat.live.tc4.build_rt_request` 原樣可用,只差 symbol 換 `TC.S.TWS.<code>`。
- 推播欄位與期權 REALTIME 同構:`TradingPrice` / `TradeQuantity`(單筆張數)/ `TradeVolume`(當日累積,去重主鍵可沿用)/ `Bid` / `Ask` / `FilledTime`(UTC)/ `Security`(=股票代碼)/ `Exchange: TWS`。樣本存 scratchpad `stock_realtime_sample.json`。
- 意義:**個股 + 個股期的「行情」面沒有新障礙**——TXO 看盤那套 QuoteSource / 交接 / 去重直接複用。

## 2. 下單面證據鏈 🔴

1. **本機實測**:trade port LOGIN OK、`ACCOUNTS` 0 rows(`TradeZMQService-20260721-0.log`:`SendData:{"Reply":"ACCOUNTS","Success":"OK","Accounts":[]}`)。TC4 app 未登任何交易帳戶,無法做帳戶型別的實證。
2. **官方合作清單**(touchance.com.tw/cooperate):台新期貨、群益期貨、富邦期貨、統一期貨、凱基期貨 —— **全是期貨商,零證券商**。TC4 內建下單匣的前提也是「向所屬期貨商申請 API 交易權限」。
3. **「證券加值服務」公告**(tc_post?idno=189,已 404,僅剩搜尋快取):首波與某證券商 WinTrade 平台合作股票程式交易,屬 **MultiCharts 加值服務**路線,不是達錢 4 ZMQ OpenAPI;快取對券商名稱記載不一(元大/元富),無法確認。
4. TC4 UI 字串裡的「證券市值/證券收支」僅為期貨帳戶保證金試算欄位(A00049/A00050 `Order.xaml`/`TWQueryMargin.xaml`),非現貨下單功能。

**結論:個股現貨下單不要走 Touchance。** 要做現貨下單得接證券商自家 API(注意:富邦 Neo 已被 user 明確排除,見 CLAUDE.md §5),或維持「TC4 只做行情 + 現貨手動下單」。個股期(股票期貨)屬期交所商品、走期貨商帳戶,**不受此限**——但同樣卡在期貨商 API 權限申請(user 延後)。

## 3. 對下一批(個股 + 個股期)的路線含意

- 行情:個股 `TC.S.TWS.*`、個股期 `TC.F.TWF.<個股期產品碼>.*` 都走既有 TC4QuoteSource 模式,無新風險(個股期推播待實測,預期同期貨)。
- 下單:白名單擴充只該擴到**個股期**(期貨商帳戶);個股現貨下單排除在 TC4 路線外,列開放題。
- 商品發現:股票類 `QUERYALLINSTRUMENT` 無有效 Type,個股 watchlist 得自帶代碼清單(反正本專案本來就是 watchlist 輸入制),存在性用「訂閱後 N 秒內有無推播」健檢(07-20 教訓:SUBQUOTE 對不存在 symbol 照回 OK)。
