# Refactor Plan — stock-page-dedupe-deadcode(2026-08-03,v2 依 review 修正)

動機(Phase 1):user 指定 — 個股頁面前後端去重、刪死碼、清邏輯疑點;六輪迭代後的清理窗口。
Baseline(Phase 2):pytest 1481 passed / vitest 898 passed / ruff / pyright / tsc / eslint 全綠。
輸入:findings-frontend-dup.md(D-*)、findings-backend-dup.md(B-D*)、findings-deadcode.md(DC-*、L-*)。
Review 輪 1:14 findings(4 P0 / 3 P1 / 7 P2)全 accepted,已反映於本版;變更處標【R-n】。
限縮輪 2:8 findings(1 P1 / 7 P2)全 accepted,標【R2-n】;無 P0 → Phase 3 退出條件達成。

## Scope 拍板([auto-default] 彙整)

1. **[auto-default: 行為改動類(L-6/L-7/L-9/L-14/L-16【R-4】/L-17 + 後端 payload 欄位 DC-15~18 後端側)一律只記 docs/next-time.md | reason: /refactor 行為絕對不變;wire payload 形狀屬可觀察行為;L-16 deps 修正會改 resize 後滾輪錨點]**
2. **[auto-default: 逐字相同的具名 helper(D-1 fmt / D-2 pts / D-3 hhmm)一次收斂全部 caller,含期貨/大盤頁 | reason: 同 helper 留兩份違背去重目標;改動純 import 置換且測試全覆蓋]**
3. **[auto-default: inline 表達式類重複(D-7/D-9)只收個股頁呼叫點 | reason: 控制 diff 面;其餘記 next-time]**
4. **[auto-default: 跳過 D-8(tone)、D-10(ToggleButton)、D-13(GroupPicker)【R-3】、D-14 JSX 抽取【R-7】 | reason: 語意分岔(中性態/hover/stopPropagation/aria-label/testid),參數化抽取淨可讀性負值或即行為改動;D-14 只收 SUGGEST_LIMIT 常數]**
5. **[auto-default: 僅測試引用的死碼(DC-3/4/6/7/8/12/17 前端側/19/21)連同對應測試斷言一併移除,逐條圈定刪除範圍【R-10】 | reason: 測試在測已下線的能力=死碼的一部分;非「砍紅測試讓它過」]**
6. P3 類(D-15~D-22、B-D14~B-D17)與 B-D6、L-5 全部不動;理由已載於 findings 檔。

## 步驟(每步單獨綠、單獨 🔵 commit;characterization 為 🟢 獨立 commit)

### Track C — 後端

- **C1** | B-D1+L-11:`fetch_day_minutes` 改呼叫 `_taipei_minute_key`(None→continue;dict 覆寫政策保留;域維持個股 0901-1330)。【R-8】呼叫必須留在原 `except (KeyError, ValueError)` try 區塊內,`skipped` 計數語意不變(Time/Close 解析失敗 +1、域外靜默 continue);步驟測試加一列壞 Time row 斷言只 skip 不 raise。
- **C2** | B-D8:`tc4common.TC4_DEFAULT_PORT`;app.py `_tc4_port()` 收 5 處;各 source/cli 預設值引常數。不合併 `_default_stock_source`/`_default_index_source`。
- **C3** | B-D9:Decimal `to_milli`≡`to_millipts` 收斂到 tc4common,原檔留薄別名(import 面不變)。不碰 float 家族、不碰吞例外行為。
- **C4** | B-D5:`WsBroadcaster` 搬 `server/ws.py`,`__init__(self, maxsize: int = 500)`【R-5】預設 500 不變;app.py:29 import 與 :200-203 四個建構點、tests/server/test_capital_api.py:19 的 `_CLIENT_QUEUE_MAX` import、**capital_api.py 自身 :315/:337 的型別註記**【R2-7】一併處理(留 re-export 或同步改 import,擇一,傾向直接改 import 去除間接層)。【R2-7】本步 commit 前必跑 `pyright`(from __future__ annotations 讓漏 import 在測試不紅)。stock_engine(1000)/index_engine(32)改持實例;stock `stream(seed=...)` 種子**呼叫當下同步入佇列**(對齊現行 :487-491),不可借 _publish。驗:test_stock_engine TestStreamAndStatus、test_index_engine、test_capital_api(含 :602-619 背壓測試)。
- **C5** | B-D4:tc4.py 基底 `_resub(sym)`/`_unsub(sym)`;三 source 改呼叫,外圍(_seen/Timer/leaf 組字)留原地;失敗語意維持 raise ConnectionError。
- **C6** | B-D2+B-D3【R-1 重構】:
  1. 🟢 characterization(獨立 commit)【R2-3】:驅動點沿用 test_tc4.py TestListenerFollowsSubPort 的 real-PUB harness(基底此時尚無 handle_raw 可直呼)— 先送壞電文(無冒號 / 非 JSON / DataType≠REALTIME / Quote 使 parse_realtime 回 None)再送一則合法電文,斷言 `got == [合法那則]` 且 listener 執行緒仍活著;不做逐路徑計時等待型否定斷言。
  2. 🔵 基底 tc4.py:`_listen_loop` 訊息處理段拆 `handle_raw(raw)` hook;基底 `handle_raw` = 現有 TXO 解析逐字搬移。**三個子類只刪 `_listen_loop`,全部保留自己的 `handle_raw`**(futures/corr 刪掉會走 `_on_tick is None` 靜默黑洞)。
  3. 🔵 futures↔corr 的 handle_raw 逐字重複改共用:基底加 `_realtime_msg(raw) -> dict | None`【R2-4】(找冒號→json.loads→DataType 檢查,**回整則 msg**);四份 handle_raw 改 `msg = self._realtime_msg(raw)` + **`if msg is None: return`(禁 truthy 判定 — 空 Quote 現況照送 `_on_message({})`)**,`msg.get("Quote", {})` 取值留在各自 handle_raw;stock 版保 `_seen.add` 早於 `_on_message`。
  單獨 commit 序列,唯一碰 TXO 實盤路徑。
- **C7** | B-D7【R-6】【R2-1】:`_boot` 兩段式 — `await _boot(name, make, start, close)`:make 回傳物件(可回 None = sentinel 解析空,整段跳過不記失敗 log)、_boot 自己 `await start(obj)`,make 與 start 都在 try 內,except 分支持有 obj 可 close。**start 參數語意 = 「帶到就緒的全部工作」**:stock 的 start = `await o.start(); persisted = load_watchlist(wl_path)["codes"]; if persisted: await o.set_watchlist(persisted)`(load_watchlist 對壞檔不吞例外,現況由該 except 接住 — 必須留在 try 內);capital 的 start = async 包 sync:`c.set_broadcast(_capital_broadcast); c.start(loop)`;capital closer 承載 to_thread。建構順序(corr 在 futures 後)與關機反序保留。🟢 補 characterization:start() 拋例外的 fake,斷言 source 被 close 且 app 照起(503 降級)。
- **C9** | B-D11【R-2】:`_valid_code(code)` 做**普通函式**,在各 route `_stock(request)` **之後**呼叫(錯誤優先序:engine None + 非法碼 → 503 不變)。`_index(request)` 比照 _stock;app.py:627 是 futures 閘**不動**(或另立 _futures,本輪不動)。
- **C10a** | 🔵 純死碼:DC-1(StockEngineLike/AnyDict + Any import)、DC-2(watchlist_codes)、DC-5(buy_sell_flag;連動 6 個測試 kwargs 建構點:test_stock_engine.py:150,167、test_stock_state.py:26、test_stock_models.py:305,325,357)。【R-9】
- **C10b** | 🔵 僅測試引用死碼:DC-3(ungrouped:刪 TestUngrouped 整 class、test_v2_file_migrates_codes_from_union 最後一行 assert、**tests/test_stock_watchlist.py:15 import 清單中的 `ungrouped,`**【R2-5】;`test_ungrouped_codes_count_toward_limit` 整條保留【R-10】)、DC-4(parse_isin_html + **tests/test_stock_names.py:11 import 行**;呼叫點改寫::52,60,65 → `result, _ = parse_isin_html_with_stats(...)`,:73,76,79 → `parse_isin_html_with_stats(...)[0]`【R2-5】)。
- **C10c** | 🔵 safe 微修:L-12(late import 併檔頭)、L-13(補持有防 GC 註解)、L-18(刪 no-op 重讀或註解)、L-20(vol 解析移序)、L-10(docstring 校正)、L-8(補去重不對稱語意註解)。

### Track A — 前端去重

- **A1** | D-1:`fmt` → lib/format.ts export;9 caller 全收;WatchlistSidebar `fmtPrice` 內部改呼叫 fmt。【R-12】禁令:MarketChart.tsx / IndexPage.tsx / IndexBar.tsx 的本地指數版 `fmt`(`Math.round(v*100)/100`)一律不動。
- **A2** | D-2:新檔 lib/svg-points.ts `pts()`;6 caller 收(含 MarketChart/IndexPage/RiverCards/RiverOverlay,只換 pts 不碰其本地 fmt【R-12】);stock-intraday-svg.ts:340 inline 版不動,加註精度須與 pts 一致。
- **A3** | D-3【R-13】:`hhmm()` + `HOUR_TICKS` 放**中性位置** `lib/time-labels.ts`(不放 stock-intraday-svg,避免 index 頁反向依賴 stock 專屬 lib 且同檔混兩份同名 X_START_MIN);caller 收 StockIntradayChart(X_LABELS 改 hhmm)+ MarketChart + **IndexPage.tsx:26-29(第四份逐字相同 X_LABELS)**【R2-2】。
- **A4** | D-4:新檔 lib/api-error.ts `parseError(res)`(以 useStockWatchlist 版為準);收 useStockBars/useMarketBars/useStockWatchlist。useStockNames 行內版先驗錯誤路徑語意,不同則跳過記 next-time。useTrade/useCapital/useSeries 記 next-time。
- **A5** | D-5:watchlist-model.ts 加 `isSameWatchlist(a,b)`;三處 commit 判定式改呼叫,副作用留各檔。
- **A6** | D-6:StockIntradayChart lastTone 改呼叫既有 `markTone`;:751 三元式不動。
- **A7** | D-11:lib/utils.ts 加 `safeIdToken(raw)`;兩 caller 收。
- **A8** | D-12:candle.ts `X_LABEL_H` 改 export;CandleChart.tsx:30 改 import。
- **A9** | D-7+D-9:format.ts 加 `fmtPct(v)`、`chgPct(v, ref)`;收個股頁呼叫點(StockPage/OrderBook/DepthBar/WatchlistSidebar/CandleChart:352,654/StockIntradayChart:581)。CandleChart:343 前收分母變體不收。範圍外記 next-time。
- **A11′** | D-14 降級【R-7】:只把 `SUGGEST_LIMIT` 移 lib/stock-search.ts(兩處硬編收斂);JSX 抽取記 next-time。
- (A10 GroupPicker 取消【R-3】,記 next-time,含「側欄群組鈕 stopPropagation 無測試背書」缺口)

### Track B — 前端死碼 + safe 修

- **B1** | lib 層死碼:DC-6(upperY/lowerY + 測試斷言)、DC-7/DC-8(EnergyBar.total/SideSummary.total + 測試;:180 區域變數保留)、DC-9(OverlayLine.kind)、DC-10(Candle.bar)、DC-11(Pt)、DC-12(reorder/insertIndexFromPointer + 測試)、DC-13(setMembership + 測試)、DC-14(FUT_KEYS)。
- **B2a** | DC-17:cumInner/cumOuter 前端全鏈,**含 wire 型別 `StockSnapshot.cum_inner/cum_outer`(stock-accum.ts:95-96;與 B2c y_close 同一處理原則:前端型別刪、後端 payload 不動)**【R2-6】。fixture 圈定:snapshot 形 = useStockStream.test.ts:36-37、StockIntradayChart.test.tsx:53-54,107,128,515,871,927、stock-accum.test.ts:10-11,121;accum 形 = StockChart.test.tsx:15-16、StockPage.test.tsx:20-21。【R-11】
- **B2b** | DC-15(stkfutProd)+ DC-18(accum.tc4/accum.backfilling)。**不得動 useStockStream 的 status.tc4/status.backfilling 與 StockPage「回補中…」**(同名活碼)。【R-11】
- **B2c** | DC-16:y_close(fixture 面最大:stock-accum.test/stock-intraday-svg.test:28,588/PriceLadder.test:16/RightRail.test:15/StockChart.test:22/StockPage.test:30/useStockStream.test:41/StockIntradayChart.test:63,110,518,874,929)。後端 payload 不動。【R-11】
- **B3** | 元件層:DC-19(DepthBar onPriceClick + 測試;Tag 分支簡化 div)、DC-20(drag.index)、DC-21(re-export;測試改 import 來源)、DC-22(priceTone 去 export)。
- **B4** | safe 邏輯修:L-1(抽 buildEnergyBars 或副圖沿用 g.maxTotal,輸出逐值同)、L-2(bandSeries 併幾何 memo)、L-3(shownAgg 重用 hoverAgg)、L-4(limitOnly 區域變數)、L-15(nameOf 改 Map memo)、L-19(subW;commit message 明寫「今日 mainW≡subW 故輸出同值」【R-4】)。L-16 移除(→ next-time [behavior])。

### Track T — 測試層去重【R-14】

- **T1** | B-D13:抽 `tests/helpers/fake_txo.py`(名稱去底線),六檔改 import;conftest 不放類別。【R2-8】`_SERIES`/`_C` 常數一併搬入並 export(六檔逐字相同),六檔改 import 同一份,不各留一份;個別需求走 `FakeTxoSource(series=...)` 建構參數。
- **T2** | B-D12:抽 `tests/helpers/tc4_fakes.py`;test_backfill_tc4 變體不收。確認 pytest import 模式下 `tests.helpers` 可解析。
- **T3** | D-23:`frontend/src/test-utils.tsx` 收 wrap() 五份。D-24 不收。

### 收尾

- **N1** | docs/next-time.md 補記:[behavior] L-6/L-7/L-9/L-14/L-16/L-17、後端 payload 死欄位
  (stkfut_prod/y_close/cum_inner/cum_outer/tc4/backfilling/names.count/bars.code,tf)、
  L-13 關機取消 _resub_task、範圍外 parseError 三處與 fmtPct 五處、D-8/D-10/D-13/D-14 JSX/B-D6
  跳過理由、L-5 QryIndex 驗證條件、側欄 stopPropagation 測試缺口【R-3】。

## 執行紀律

- 每步:改 → 跑該步相關測試 → 綠 → 🔵 commit(characterization 🟢)→ 下一步;紅 = 預設 refactor 改錯。
- 實作全 dispatch implementer subagent(model: opus),per-track 分批;prompt 禁 format 整檔、禁順手改 scope 外、附本檔對應步驟全文。
- Phase 5 blast radius:全 suite + grep(含動態:hasattr on_reconnect、type: ignore 處、JSON key、
  getByLabelText/testid 字串、`Math.round(v * 100) / 100` 應仍 3 份【R-12】、
  `stock-suggest` testid 應僅側欄一份)。
- Phase 7 真實環境:fake source + 非 8721 port 驗 HTTP 層;前端 vite dev 畫面對照(盤後態,
  以 refactor 前後同資料同畫面為準);盤中不起第二台連 TC4 後端。
