# change-spec:期貨 tab 改「15:00 夜盤起算」的一天定義(mod/futures-day-1500)

> 2026-08-27 晚。現況表 / caller map / 白名單見同目錄 `current-state.md`。
> 規格來源 = handoff(feat/txf-intraday-overlay Q7)+ grilling 兩輪 user 拍板(見 §4)。
> 規模:**M**(前端 lib 2 檔 + 元件 1 檔 + 日曆 helper;後端零 diff;測試 5 檔)。主 session 直做。

## 0. 目標一句話

期貨 tab 的台指期分時圖(近全軸)把「一天」改成期交所口徑:x 軸左起 15:00 夜盤、經 05:00→08:45 無交易空檔(保留在軸上、
畫水平線)、右至 13:45 日盤收;「今天」= 最後一根 bar 所屬的交易日;bar 時戳維持牆鐘。

## 1. 名詞(進 CONTEXT.md)

- **錨定日**:一根 1K bar / 一筆成交 / 一個牆鐘時刻所屬的**交易日**(期交所口徑)。日盤(08:46–13:45)→ 當日曆日;
  夜盤(D 15:01–23:59 與 D+1 00:00–05:00)→ D 的**次一交易日**(週五夜盤 → 週一;假日前夜盤 → 假日後首交易日)。
  分時圖只畫「錨定日 = 末根 bar 錨定日」的 bar。空檔時刻(13:46–15:00 / 05:01–08:45)→ 當日曆日(前者 = 剛收的那天,
  後者 = 即將開的那天;兩者都不會有 bar / live 點)。

## 2. 成功條件(SC)

| # | 條件 | 驗證 |
|---|---|---|
| SC-1 | `ALLDAY_SEGMENTS` 四段:夜盤前半 1501–2359(539)→ 夜盤後半 0000–0500(301)→ **空檔 0501–0845(225,`tradable:false`)** → 日盤 0846–1345(300);`ALLDAY_LEN` = 1365;`ALLDAY_WINDOW` = [0, 1364] | `allday.test.ts` |
| SC-2 | `alldayIndexOf`:1501→0、2359→538、0000→539、0500→839、0846→1065、1345→1364;空檔(0501–0845、1346–1500)與壞值 → null(bar / live / 成交點在空檔一律不畫,W4) | `allday.test.ts` |
| SC-3 | `alldayHhmmOf`:反演**軸位置**,空檔索引也回時刻(840→"05:01"、1064→"08:45";hover 底標誠實);可交易索引與 `alldayIndexOf` 互逆 | `allday.test.ts` |
| SC-4 | `ALLDAY_TICKS` 九顆重排:15:00(釘 index 0)18:00 21:00 00:00 03:00 05:00 09:00 11:00 13:00;index 嚴格遞增、全落窗內;`ALLDAY_HOUR_TICKS` 同步 | `allday.test.ts`;`FuturesChart.test.tsx` SC-2 底部標籤條 |
| SC-5 | `anchorDateOf` 依 §1;吃 `lib/trading-calendar.ts` 新 helper `nextTradingDayIso(iso)`(週末 + 假日集合;未載入 = 只跳週末;上限 30 天防無限迴圈) | `allday.test.ts` 新增:週一夜→週二、週二凌晨→週二、週五夜→週一、週六凌晨→週一、`setHolidays` 後假日前夜→假日後首交易日、`clearHolidays` 後退化;`trading-calendar.test.ts` helper 條 |
| SC-6 | `sliceCurrentAllday` = 「錨定日 == 末根錨定日」的 bars(原物件、不改輸入);13:45–15:00 之間末根 = 13:45 → 畫剛收的那天;15:01 首根一到翻頁 | `allday.test.ts` 改寫全部切片案例(含週末 (a)(b) 與夜盤 only 冷啟動) |
| SC-7 | **空檔水平線**:`futuresBarsToAccum` 在「夜盤側有 ≥1 格且日盤側有 ≥1 格(bar 或 live)」時,於 index 1064(08:45)補一格 bridge `{c: 夜盤末格 c, v:0, o:i:u:0, h:null, l:null}`;不進 vp、不進 high/low、不進 Σ;只有夜盤側(日盤未開)→ 不補,線停在 05:00 | `futures-accum-adapter.test.ts` 新增三條(兩側都有 → 有 bridge;只夜盤 → 無;只日盤 → 無) |
| SC-8 | live gate 1–4 判準逐字不動;**gate 5 的落後根數改以可交易索引距離計**(新 `alldayBarsBetween(from, to)`),08:46 首根未回時對 05:00 尾根不誤報「落後 227 根」 | `FuturesChart.test.tsx` live 節 fixture 換日期;新增「尾根 05:00、成交 08:47 → 不報落後」 |
| SC-9 | FuturesChart 的 slice / anchorDate memo 把日曆 query data 納入 deps(`useQuery(calendarQueryOptions)` 共用 cache),日曆載入後不等下一輪 bars 才重切 | `FuturesChart.test.tsx` 一條:假日前夜 bars,`setHolidays` 後重 render → slice 含假日後日盤 |
| SC-10 | CDP / MA 基準 = 錨定日前一交易日 DK(算式不動);夜盤時段基準自動變成剛收那天的 DK | `FuturesChart.test.tsx` N042 節「夜盤成形」條改期望值 |
| SC-11 | 個股頁「台指期」疊線解耦:以「日盤 bar 的日曆日 == quote.date」為界;quote.date 缺 → 最後一根**日盤** bar 的日曆日;行為 = 現況(W5) | `txf-overlay-series.test.ts` 全綠(「凌晨錨定」條改寫為同語意,不 import `anchorDateOf`) |
| SC-12 | CONTEXT.md 加「錨定日」條;`allday.ts` 檔頭 / FuturesChart / fill-marks 註解的「死區(13:46–15:00 / 05:01–08:45)」口徑更新 | grep |
| SC-13(真環境) | prod 重啟後:(a) 15:00 開盤前看圖 = 左起昨 15:00 右至今 13:45;(b) 15:01 首根到 → 翻頁,左起今 15:00;(c) 次日 08:46 → 05:00 至 08:45 水平線 + 08:46 跳價;(d) CDP 值在 15:00 換組,user 對 APP;(e) 個股頁台指期線夜盤時段仍在 | 截圖 `evidence/`;user 過目 |

## 3. 不能破壞的既有行為白名單

見 `current-state.md` §3 W1–W11。本 spec 追加:
- W12:`alldayFillPoints` 簽名不變(caller 零改),錨定語意隨 `anchorDateOf` 變。
  **P5 後修訂**(pr-133 F-02):簽名加選配 `holidays`,caller 必須傳與 `anchorDate` 同源的那一份日曆(`FuturesChart` 傳 `holidaySet`);既有三參呼叫仍相容。
- W13:`FUT_LIVE_LAG_MAX = 3` 與提示文案「分時資料落後 N 根(TC4 回補中)」不變。

## 4. 拍板紀錄(grilling)

| 題 | 拍板 |
|---|---|
| Q1 bar `t` | 牆鐘不改 |
| Q2 錨定日 | 期交所口徑(§1);週幾不顯示 |
| Q3 13:45–15:00 | 看剛收的那天 |
| Q4 空檔 | 05:00→08:45 保留在 x 軸,畫水平線(user 平時 APP 樣式);標籤九顆重排不疊字 |
| Q5 CDP 基準 | 接受連帶變化,user 事後對 APP |
| Q6 個股頁台指期線 | 只看日盤、解耦 |
| Q7 不動清單 | 後端 / 輪詢窗 / corr 閘 / 江波圖 / 分 K 日 K 全不動 |
| Q8 seams | `allday.test.ts` + adapter + FuturesChart + txf-overlay-series + trading-calendar |
| Q9 空檔線形 | (a) 水平 |
| Q10 13:45→15:00 | 不保留(在一天之外) |

`[auto-default]` 待 user 表態:bridge 只在日盤側已有格時才補(日盤未開時線停在 05:00,右側留白);替代 = 空檔期間跟牆鐘延伸。

## 5. 實作順序(三類分開 commit)

1. 🔵 `trading-calendar.ts` 加 `nextTradingDayIso`(純新增 + 測試,不改既有 export)。
2. 🔴 先改 `allday.test.ts` / adapter / FuturesChart / txf-overlay 測試讓它們紅 → 再改 `allday.ts`(四段 + 錨定 + 切片 + ticks + `alldayBarsBetween`)、adapter bridge、FuturesChart(gate 5 距離、日曆 deps)、txf-overlay 解耦。
3. 🟢 CONTEXT.md 錨定日條、註解口徑、artifacts。

## 6. 風險 / 已知取捨

- 假設「每個交易日都有夜盤」(沿 `inFuturesAllDayHours` 既有假設);春節前無夜盤那種特例不處理,症狀 = 該日圖左半空白。
- 日曆未載入時假日前夜盤暫歸假日(60 s 內 bars 重取 + SC-9 deps 會自癒)。
- 空檔水平線是前端補的視覺格,hover 到 08:45 那格 readout 印夜盤末價、量印「-」(v=0 走既有 futures 態分流)。
