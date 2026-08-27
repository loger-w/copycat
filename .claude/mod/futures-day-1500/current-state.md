# current-state:期貨 tab 改「15:00 夜盤起算」的一天定義(mod/futures-day-1500)

> 2026-08-27 晚。來源 handoff `%TEMP%\copycat-handoff-2026-08-27-futures-day-1500.md`(feat/txf-intraday-overlay Q7,
> user 拍板另開 /mod);留尾 `docs/next-time.md` 2026-08-27 節第 2 條。

## 1. 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 一天的段順序(x 軸) | 日盤 0846–1345(300)→ 夜盤前半 1501–2359(539)→ 夜盤後半 0000–0500(301);左緣 08:45 | 夜盤前半 1501–2359 → 夜盤後半 0000–0500 → 日盤 0846–1345;左緣 15:00、右緣 13:45;軸長仍 1140 |
| 錨定日 `anchorDateOf(stamp)` | 日盤 / 夜盤前半 → 當日曆日;夜盤後半(≤05:00)→ 前一日曆日 | 期交所口徑:**日盤 → 當日(不變)**;夜盤前半(D 15:01–23:59)與夜盤後半(D+1 00:00–05:00)→ **D 的次一交易日**(週五夜盤 → 週一;假日前夜盤 → 假日後首交易日)。需要交易日曆(`lib/trading-calendar.ts::isTradingDay`;未載入 = 只跳週末) |
| `sliceCurrentAllday` | 以末根反推錨定日,取 `t >= "{anchor} 08:46"` | 取「錨定日與末根相同」的 bars(等價於 `>= prevTradingDay(anchor) 15:01`,但不需要 prev 方向的日曆查詢) |
| 軸標籤 `ALLDAY_TICKS` | 09:00 11:00 13:00 15:00(釘夜盤段起點)18:00 21:00 00:00 03:00 05:00 | 重排;接縫 05:00\|08:45 需一顆標籤(見 grilling Q4) |
| live 點四道 gate + gate 5 | `liveSlotOf` / `tradeSlotOf` 各回 `{index, anchor}`,anchor 走 `anchorDateOf` | 判準逐字不動,只吃新 `alldayIndexOf` / `anchorDateOf`;開盤瞬間的「首根未回不畫」語意由 08:45–08:46 移到 15:00–15:01(且 08:45–08:46 也有,因 08:46 首根未回時末根 05:00 同錨定日 → 會畫;見 Q5) |
| CDP / MA 基準日(`buildFuturesOverlay(dayK, anchorDate)`,`date < anchorDate`) | 夜盤時段(D 22:00)anchor = D → 基準 = D 的前一交易日 DK(D 當天已收完的 DK 被跳過) | anchor = D 次交易日 → 基準 = **D 當天的 DK**(15:00 起算的一天,昨日 = 剛收的那一天;TC4 DK 把夜盤成形的 bar 標成次交易日,`date < anchor` 恰好剔掉它) |
| 成交點 `alldayFillPoints` | `anchorDateOf(stamp) === anchorDate` | 同式,錨定語意跟著變(D 夜盤成交畫在「D 次交易日」那張圖上) |
| 個股頁「台指期」疊線 `txf-overlay-series` | anchor = `anchorDateOf(末根)`,只取該錨定日的日盤段,與 `quote.date`(index engine trade_date)不同則不疊 | **不受影響**:改為以「日盤 bar 自己的日曆日 == quote.date」為界(夜盤時段個股頁仍疊當天日盤那條);解除對 `anchorDateOf` 的依賴 |
| 後端 `FUTURES_ALLDAY_DOMAIN` / `fetch_bars_range` / `build_minute` 日 cache | 段不跨午夜、bar `t` = 台北牆鐘、cache 以日曆日為單位 | **不動**(Q3 白名單):bars 本來就多回幾天,切片在前端;`t` 維持牆鐘 |
| 輪詢窗 `inFuturesAllDayHours` | 00:00–05:05 看前一日是否交易日;其餘看當日 | 不動(它判的是「現在有沒有盤」,與哪一天無關) |
| corr 腿自癒閘 `segment_leg_gate` | 只看時段 | 不動 |
| 分 K 模式(`aggregateBars` → `CandleChart`)/ 日 K | 5 日連續序列,桶 key 含日曆日 | 不動(x 軸是 bar 序不是一天) |

## 2. Caller map(含動態用法)

`lib/allday.ts` export → 讀者:
- `ALLDAY_SEGMENTS` / `ALLDAY_LEN` / `ALLDAY_WINDOW` / `ALLDAY_HOUR_TICKS` / `ALLDAY_TICKS`:`FuturesChart.tsx`(core xWindow / hourTicks)、`allday.test.ts`
- `alldayIndexOf`:`FuturesChart.tsx::liveSlotOf / tradeSlotOf`、`lib/fill-marks.ts::alldayFillPoints`
- `alldayIndexOfStamp`:`lib/futures-accum-adapter.ts`、`FuturesChart.tsx::tailIndex`
- `alldayHhmmOf`:`FuturesChart.tsx`(core `timeText`)
- `anchorDateOf`:`FuturesChart.tsx`(slice 錨定 / 兩個 gate / overlay 基準 / fills)、`lib/fill-marks.ts`、`lib/txf-overlay-series.ts`
- `sliceCurrentAllday`:`FuturesChart.tsx` 唯一
- 動態用法:無(全部靜態 import;grep `allday` 於 App.tsx / CandleChart / StockIntradayChart / useOiLevels / chart-hlines / types 只是註解或字串 `session=allday`)

後端:`futures_source.FUTURES_ALLDAY_DOMAIN`(parse 段)、`bars.py::build_minute(session=)`、`_possible_data_days`、`app.py` route —— 本案不動。

## 3. 既有行為白名單(W)

| # | 行為 | 守門 |
|---|---|---|
| W1 | 軸長 1140、三段長 300/539/301、死區(13:46–15:00 / 05:01–08:45)回 null、`alldayHhmmOf` 與 `alldayIndexOf` 互逆 | `allday.test.ts` 對應條(改期望索引值,不改語意) |
| W2 | 後端 `/api/market/bars?session=allday` payload、`FUTURES_ALLDAY_DOMAIN`、bars cache 鍵、`meta.status` 三態 | 後端零 diff;`tests/live/test_futures_bars.py` / `tests/server/test_bars*.py` 全綠 |
| W3 | `inFuturesAllDayHours` 輪詢窗逐字不動 | `trading-hours.test.ts` 零改 |
| W4 | live 點 gate 1–5 判準逐字不動(死區 / 錨定日 / 時鐘落後資料 / 資料落後成交 ≤3 根);「分時資料落後 N 根」提示不變 | `FuturesChart.test.tsx` live 節(改 fixture 日期 / 時刻,不改判準) |
| W5 | 個股頁「台指期」疊線行為不變:只疊 quote.date 當天日盤段、終點標記 −1、WS 補尾規則、夜盤時段仍疊當天日盤 | `txf-overlay-series.test.ts` 全部維持綠(「凌晨錨定」條改寫為不依賴 anchorDateOf 的同語意) |
| W6 | 分 K(1–60 分)與日 K 模式畫面零變化;`aggregateBars` 不動 | `candle.test.ts` 零改、FuturesChart 模式列測試零改 |
| W7 | 結算價 `ref` 來源不變(期貨 WS `ReferencePrice`);漲跌色 / 對稱域基準不變 | 不碰 `futures_models` / adapter 的 `ref` 透傳 |
| W8 | 日曆未載入(`/api/calendar` 未回 / 元件級測試)時退化成「只跳週末」,失效方向 = 週五夜盤仍正確歸週一;假日前夜盤才會錯歸假日(與 `inFuturesAllDayHours` 的既有退化同向) | `allday.test.ts` 新增「未載日曆 / 已載假日」兩條 |
| W9 | `ALLDAY_WINDOW` / `ALLDAY_HOUR_TICKS` 模組層常數 identity(memo 不被打穿) | 維持 IIFE 常數寫法 |
| W10 | `sliceCurrentAllday` 回原 bar 物件、不改輸入 | 既有測試條 |
| W11 | `alldayFillPoints`:死區成交不畫、別錨定日不畫 | `fill-marks.test.ts` / `FuturesChart.test.tsx` 成交點節(fixture 換日期) |
