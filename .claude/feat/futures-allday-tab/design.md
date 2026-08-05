# design v2 — 期貨 tab 近全圖表 + 交易輔助

changelog:
- v1(2026-08-05):初版。
- v3(2026-08-05):限縮 round 2 全 9 條 accepted 修入:§1.1(刪 +1 分鐘子句 —— 1K
  Time 已是終點標記,R2-1)、§2(快取鍵改請求端可算的 (contract_ym, today),R2-2)、
  §7(close body key = stock_no,複合鍵僅 UI 列選取,R2-3)、§3.2(live 點錨定日
  gate,R2-4)、§3.1(段長 300/539/301,R2-6)、§4.1(days=5 的 initBars 誠實記帳,
  R2-7)、§10(盤中當日段收割量測,R2-8)、§4.2(停輪詢邊界與 brainstorm 同步,
  R2-9);brainstorm SC-11 amendment(R2-5)。
- v2(2026-08-05):design review round 1 全 16 條 accepted 修入。變更節:§1.1(UTC
  datetime 轉換取代 2400 wrap,D1)、§1.2(allday 取數窗前移 + 台北日期 filter,D2;
  DK 口徑分歧處理,D13)、§1.3(uv/dv 聚合貫通,D6)、§1.4(session 三層簽名 + cache
  不變式重論證,D4/D2;三態取捨明文,D8)、§2(FinMind 真樣本 + position 過濾 + range
  回退 + per-strike 回傳,D9/D15)、§3.1(段起點 ticks,D11;錨定日 slice,D16)、
  §3.2(live 點終點標記,D12)、§4.1(days=5 + payload 預算,D10)、§4.2(星期維度,
  D7)、§4.3(aggregateBars 24:00 正規化 + uv/dv,D5/D6)、§5.1(完整字串相等,D14)、
  §5.2(±10% 帶內取 max,D9)、§6.1(現貨時段 gate,D3)、§7(close body 共用 helper,
  D14)、§8(檔案清單補 futures_engine.py / fake_sources.py / candle.ts 幾何)。

對應 brainstorm.md SC-1〜SC-12。tab 結構不變、TXO/個股/大盤/相關係數 tab 行為零改動
(行為白名單;`/api/market/bars` 既有語意由 `session` 參數預設值保護)。

## 0. 總覽:資料流

```
TC4 1K(UTC 窗,夜盤 rows 本來就在) ──┐
                                        ├─ futures_source.fetch_bars_range(session)
TC4 DK ────────────────────────────────┘        │
                                 server/bars.py 兩段式 cache(key 加 session)
                                                │
                /api/market/bars/{TXF|MXF|TMF}?tf=1&session=allday
                                                │
frontend useFuturesBars(近全分 K)──┬── 分時圖(兩段拼接軸 + WS 現價接尾)
                                    ├── K 線(aggregateBars 1–60 分 / 日K)+ 內外盤副圖
useFuturesStream(既有 WS)──────────┘        overlays:持倉均價線(useCapitalPositions)
useIndexStream.twse(既有)── 期現價差              + OI 撐壓線(/api/futures/oi-levels)
FinMind TaiwanOptionDaily ── server/oi_levels.py(新)── OI 撐壓線
```

## 1. 後端:夜盤分鐘域(SC-3)

### 1.1 `copycat/live/stock_source.py` — parse_1k_bars 多段域 [v2: D1]

`parse_1k_bars(rows, domain)` 的 `domain` 參數擴為
`tuple[str, str, str] | Sequence[tuple[str, str, str]] | None`(單段 = 既有語意,零 caller
改動;序列 = 逐段嘗試,行落在哪段用哪段的 clamp)。每段 `(start, end, clamp_end)` 語意
不變,段本身不跨午夜(夜盤拆兩段,見 1.2)。行不落任何段 → 丟(既有語意)。

**台北時刻推導(取代 v1 的 key==2400 wrap;v1 規則在既有 `+8 %24` 實作下永不觸發)**
[v3: R2-1]:多段路徑不再用 `_taipei_minute_key` 的「只加小時」捷徑,改走**完整
datetime 轉換**:`datetime.strptime(f"{row.Date} {row.Time.zfill(6)}", ...) +
timedelta(hours=8)` → 台北 date 與 HHMM 同時得出(UTC 16:00 之後的列日期自然 +1,
永不出現 2400),再對台北 HHMM 做段判定與 clamp。**不加 1 分鐘** —— 1K row 的 `Time`
本身已是 bar 終點標記(`river_models.minute_end_from_1k` 實證註明「不加 1」;既有
`_taipei_minute_key` 亦只 +8),加 1 會讓多段路徑整體晚一分(0846 首根變 0847、
SC-3 的 15:01 斷言 FAIL)。與 §3.2 live 點的 +1 是**不同語意**:那裡的來源是牆上
時鐘(當前時刻屬於「下一個終點標記」的 bar),兩節互為對照。Phase 3 紅測試含:
UTC Time="155900" → 當日 23:59(不進位);UTC Time="160000" → 次日 00:00。
單段既有路徑(個股/日盤)**不動**,行為零變化。

**Date 欄語意假設**:1K row 的 `Date` 是 UTC 日曆日(與 `Time` 同源;佐證:DK 的
Date/Time 已實證為 UTC — CLAUDE.md §8 海外期貨 `Time=210000`;`stock_window` 以 UTC
小時建窗慣例)。此假設由 Phase 3 紅測試固定(Time="160000" 的列 → 台北次日 00:00)
+ Phase 6 真資料核對(夜盤 15:00 台北首根的 Date/Time 原值落 log 檢查)。

**排序**:近全序列靠 `t = "YYYY-MM-DD HH:MM"` 字典序天然時序正確,既有 sort 不需改。

### 1.2 `copycat/live/futures_source.py` — 近全段定義與取數窗 [v2: D2/D13]

```python
FUTURES_ALLDAY_DOMAIN: tuple[tuple[str, str, str], ...] = (
    ("0846", "1345", "1350"),  # 日盤(既有 FUTURES_MINUTE_DOMAIN)
    ("1501", "2359", "2359"),  # 夜盤前半(15:00 開盤,首根終點標記 1501)
    ("0000", "0500", "0505"),  # 夜盤後半(05:00 收盤,0501–0505 clamp 併入 0500)
)
```

`fetch_bars_range(product, tf, start_date, end_date, *, session="day")`:

- `session="allday"` 且 tf="1":**SubHistory 窗前移** —— start = `(start_date − 1 日)16`、
  end = `end_date 23`(UTC 小時粒度)。理由:台北日 D 的凌晨段(00:00–05:00)在 UTC 日
  D−1 的 16:00–21:00,v1 的 `D00–D23` 窗抓不到。parse 後**以台北日期 filter 到
  `[start_date, end_date]`**。
  **多收的方向(code-review TZ-1 更正,原文講反了)**:低端多收的是 UTC (start−1)
  16:00–23:59 = 台北 `start_date` 的 00:00–07:59 —— 正是要救的那段,不會被 filter 掉;
  台北 start−1 的夜盤前半(15:01–23:59)= UTC (start−1) 07:01–15:59,**根本不在窗內**。
  filter 真正擋掉的是**高端**:UTC `end_date` 16:00–23:00 = 台北 `end_date+1` 的
  00:00–07:00(次日凌晨盤)。防線正確,理由是單邊的。
- `session="day"`(預設)與 tf="D":窗與行為**零改動**(既有 caller 全不變)。
- source 端 `session` 為 keyword-only + 預設 `"day"`。

**日 K 口徑(D13 分歧處理)**:DK 是 TC4 給什麼畫什麼(與大盤 tab 同一路)。Phase 6
實測當日 DK `v` 對照 1K 日盤量+夜盤量:(a) DK 含夜盤量 → 無事,量柱與分 K 加總同口徑;
(b) DK 僅日盤量 → 接受口徑差(日 K 量柱 = 日盤量),在 FuturesChart 日 K 模式的 meta
列標註「日K量:TC4 口徑」,不改資料。實測結果回寫本節 [實測後補]。

`fetch_day_1k`(江波圖)不動。

### 1.3 內外盤欄位(SC-8 後端半)[v2: D6]

`_parse_1k_rows` 額外抽 `UpVolume` / `DownVolume`(缺值 0);`Bar` TypedDict 加
`uv: NotRequired[int]`、`dv: NotRequired[int]`。1K 路徑一律填(個股頁不讀新欄位,
行為不變);DK 路徑不填。`_fold` / `_merge_into` 對 uv/dv 累加(缺值視 0);
`aggregate_1k_to_daily` 同步累加。前端聚合貫通見 §4.3。

### 1.4 session 貫通:三層簽名 + cache [v2: D4/D2/D8]

三層簽名一次寫齊:

1. `app.py market_bars`:query `session: str = "day"`(值域 `day|allday`;其他值或
   TWSE/OTC 帶 `allday` → 400 `{"detail":{"error":"INVALID_SESSION"}}`)。route 內
   `tagged_source` closure 把 session 轉給 engine。
2. `futures_engine.bars_range(product, tf, start, end, *, session="day")`:原樣轉給
   source 的 `fetch_bars_range`(`asyncio.to_thread(lambda: fetch(..., session=session))`
   或 functools.partial;fetch 仍由 getattr 取得)。
3. source(§1.2)與 `tests/helpers/fake_sources.py` 的 fake `fetch_bars_range` 同步加
   keyword-only `session="day"`。

**cache key**:`bars.py` 的 per-(code,date) 歷史 memo、today、empty 負向 cache 的 code
鍵一律改複合字串 `f"{key}:{session}"`(day 也帶後綴,單一格式;in-memory 無相容問題)。
日 K memo 不帶 session(tf=D 無 session 維度)。

**兩段式不變式(跨午夜重論證)**:parse 已保證 bar 的 date/t 是台北日曆日(§1.1),
台北日 D 的 bars 最晚在台北 D 23:59 前產生完畢(D 的凌晨段 00:00–05:00 在 D 當日凌晨、
日盤在 D 白天、夜盤前半在 D 晚間)→「date < today(台北)即不變」仍成立,歷史 memo
安全。today 段每次以 `fetch(code, "1", today, today)` 取(§1.2 窗前移使其涵蓋今日
凌晨段)。`put_hist_range` 的日期範圍語意不變(§1.2 filter 保證 by_date 只含窗內日期,
無靜默丟棄)。

**三態取捨(D8)**:market bars 路徑目前無三態(`plain_with_status` 固定 ok,空態以
`meta.source="unavailable"` 表述)——**本輪沿用此單一表述,不引入三態**。理由:三態
需要 futures_engine.bars_range 升級回 (bars, status) 並貫通 market_payload,blast
radius 及於大盤 tab;期貨 tab 空態文案用「資料載入中/暫無資料」進行式(不下結論,
與 §1 stock BarsStatus 文案紀律同精神)。brainstorm edge case 3 已 amendment 記取捨。

## 2. 後端:OI 撐壓(SC-11)[v2: D9/D15]

新檔 `copycat/server/oi_levels.py`:

- **資料源**:FinMind `TaiwanOptionDaily`(data_id=`TXO`)。**真樣本(2026-08-05 實打,
  6,972 rows @ 2026-08-04)**:
  `{"date":"2026-08-04","option_id":"TXO","contract_date":"202608W1","strike_price":35900.0,
  "call_put":"call","open":0.0,...,"open_interest":0,"trading_session":"after_market"}`;
  `contract_date` 值域樣本 `{202608, 202608F1, 202608F2, 202608W1, 202608W2, 202609,
  202610, 202612, 202703}`;`trading_session ∈ {position, after_market}`,**OI 在
  `position` 列**(after_market 列 OI 為 0)。
- **口徑**:filter `trading_session == "position"` 且 `contract_date == <TXF resolved
  YYYYMM>`(精確等值 → 週選 W / F 序列自然排除)。**不在後端取 max** —— 回傳月契約
  **per-strike 陣列**,前端以現價帶內取 max(§5.2;理由:真樣本顯示全域 max 會選到
  深度價外垃圾履約價,call max 落在 55000)。
- **取數**:單次 range 查詢 `start_date = today − 10 日曆日, end_date = today`,取
  `max(date)` 那一日的列(D15:一次往返涵蓋連假,無序列回退)。HTTP 用 stdlib urllib
  包 `asyncio.to_thread`;Bearer token 讀取:`FINMIND_TOKEN in os.environ` 即用(含空
  字串=未設可壓制)→ 否則 repo root `.env`(utf-8-sig、never-raise)。retry except 集合
  含 `TimeoutError`(§8 教訓);HTTP 402(配額用盡)不 retry、直接進負向快取。
- **快取** [v3: R2-2 鍵改請求端可算]:查表鍵 = `(contract_ym, today)`(today = 台北
  日曆日,請求當下可算;值內含 resolved_date 與 strikes)。正向永久、跨日自然換鍵
  (EOD 不變;**刻意不落盤** ——
  一天一次呼叫、重啟頻率低,樣板的 atomic JSON cache 對這個量級是純複雜度;402 風險由
  單次 range 查詢 + 永久正向快取壓到每日 ≤ 數次)。失敗/402 負向快取 300s(不可永久 ——
  FinMind 恢復後自癒)。inflight dedup 用 asyncio.Lock 單飛。
- **Endpoint**:`GET /api/futures/oi-levels` →
  `{"date": "YYYY-MM-DD" | null, "contract": "YYYYMM" | null,
    "strikes": [{"strike": int, "call_oi": int, "put_oi": int}] }`(strike 升冪;
  call/put 缺該 strike 列時填 0)。token 未設 / 取數失敗 / resolved_contract 未解析 →
  `{"date": null, "contract": null, "strikes": []}`(HTTP 200;SC-11 降級語意)。
  contract 取自 futures_engine state(TXF resolved_contract)。
- 註冊:`app.py` 內與 market_bars 同層(與群益無關,不進 capital_api)。

## 3. 前端:近全軸與分時圖(SC-1)

### 3.1 新 `lib/allday.ts` [v2: D11/D16]

- `ALLDAY_SEGMENTS`:與後端 §1.2 三段對齊(日盤 300 / 夜盤前半 **539** / 夜盤後半
  **301**,總 1140 [v3: R2-6 段長更正,與 index 錨點一致];註明「與
  futures_source.FUTURES_ALLDAY_DOMAIN 對齊,改一邊必改另一邊」)。vitest:三段長度
  相加 = 1140 且 `alldayIndexOf("2359") === 838`、`alldayIndexOf("0000") === 839`。
- `alldayIndexOf(hhmm: string): number | null` — "0846"→0、"1345"→299、"1501"→300、
  "0000"→839、"0500"→1139;域外 null。
- `ALLDAY_TICKS`:`{index, label}[]` — **以段內偏移直接給 index,不經 alldayIndexOf
  查值**(D11:15:00 標籤釘在夜盤段起點 index 300,label 仍寫 "15:00");
  [09:00, 11:00, 13:00, 15:00, 18:00, 21:00, 00:00, 03:00, 05:00]。vitest 斷言每個
  tick 的 index 落在 [0,1139]。
- `sliceCurrentAllday(bars: Bar[]): Bar[]` [v2: D16 錨定日推導] —— 取**最後一根 bar**
  反推交易錨定日 anchor:時刻落日盤段或夜盤前半段 → anchor = 該 bar 日期;落夜盤後半
  段(≤05:00)→ anchor = 該 bar 日期 − 1 日。slice = 所有 `t >= "{anchor} 08:46"` 的
  bars(字串比較;不依賴任何特定分鐘 bar 存在 —— 08:46 無成交也不錯位)。空輸入回空。

### 3.2 分時圖 render(進 `FuturesChart.tsx`,見 §5)[v2: D12]

折線 = slice 後 bars 的 `c`,x = `alldayIndexOf(bar.t 的 HHMM)` 比例映射,y 幾何仿
`MarketChart.IntradayChart`(ref 虛線 + y ticks)。**WS 現價接尾**:`futuresStream`
的 `state.p` 非 null 且 bars 已載入 → 以**終點標記分鐘(當前台北分 + 1 分)**為 key
在序列尾追加/覆寫 live 點(D12:bar 是終點標記,10:00:30 的 live 點屬 10:01 那根;
datetime 運算含跨午夜進位)。只在渲染層 merge,不寫 query cache。live 分鐘落死區
(13:46–15:00 / 05:01–08:45)→ 不畫 live 點。**錨定日 gate(R2-4 [v3])**:live 分鐘
先以 §3.1 同規則算交易錨定日(≤05:00 → 前一日),**與 slice 的 anchor 不同 → 不畫**
—— 開盤瞬間(08:45–08:46,今日首根 bar 未回)slice 仍錨在前一交易日,live 點若照畫
會落在 x=0 拉出橫貫整圖的假線;等首根新 bar 進來自然切換。vitest:最後一根 bar =
D 05:00、時鐘 = D 08:45:30 → 無 live 點。

## 4. 前端:資料 hook 與時窗(SC-2/SC-3/SC-12)

### 4.1 `hooks/useFuturesBars.ts`(新)[v2: D10]

仿 `useMarketBars`:

- 分 K/分時共用**單一 query**:`/api/market/bars/{product}?tf=1&days=5&session=allday`
  (**days=5 不是 30**,D10 payload 預算:≈4 交易日 × 1140 ≈ 4,600 根,每根 8 欄
  int/str,JSON ≈ 400 KB;冷啟動 TC4 收割 ≈ 4,600 列,線性外推 §8 實測 810 列/2.1s
  ≈ 12s,一次性、歷史段永久 memo)。**誠實記帳(R2-7 [v3])**:60 分 K ≈76 根、30 分
  K ≈152 根,**不足 initBars=240 —— 初始視窗即全部資料,長週期回看歷史本輪不支援**
  (後續要支援可對 n≥30 另發長窗 query 或引導用日 K;入 Known Risks)。
  日 K `?tf=D`(既有路徑,長窗歸 CandleChart 既有行為)。
- queryKey 含 session 與 days;`refetchInterval` 60s,開關用 `inFuturesAllDayHours()`
  (§4.2),函式形式(TQ 每次 interval 重新求值)。
- **雙份 cache 取捨(D10 記錄)**:大盤 tab `TXF`(day)與期貨 tab `TXF:allday` 是兩份
  後端 cache,同 symbol 歷史抓兩遍 —— 接受:day 路徑 30 日窗已存在且大盤 tab 是
  visited-gate 的低頻頁;合併兩者(allday 超集 + 服務端裁剪)是後續優化,本輪不做。
- 空態/壞態:`meta.source === "unavailable"` → 圖表區顯示「暫無資料(TC4 未回應)」
  進行式文案(§1.4 三態取捨)。

### 4.2 `lib/trading-hours.ts` — `inFuturesAllDayHours()` [v2: D7]

**含星期維度**(夜盤後半屬前一交易日):

- 週一〜週五:`08:40–13:50 ∪ 14:55–23:59` → true(停輪詢窗 = **13:51–14:54**與
  05:06–08:39 [v3: R2-9 邊界以本節為準,brainstorm 同步])。
- 週二〜週六:`00:00–05:05` → true(前一日的夜盤後半;週六凌晨 = 週五夜盤)。
- 其餘(含週日全日、週六 05:06 後)→ false。國定假日不處理(既有兩支同)。

既有 `inFuturesTradingHours`(日盤)不動。SC-12 測點(brainstorm 已 amendment):
(週三 10:00)T、(週三 13:47)T、(週三 14:30)F、(週三 14:56)T、(週三 16:00)T、
(週四 00:30)T、(週六 00:30)T、(週六 10:00)F、(週日 20:00)F、(週一 03:00)F、
(週一 08:50)T。

### 4.3 聚合:`lib/candle.ts` aggregateBars [v2: D5/D6]

- **24:00 正規化(D5)**:`bucketEnd >= 1440` → 桶時戳改為**次日 00:00**(date +1,
  minute 0;`stampOf` 不得產出 "24:00"),且桶 key 用正規化後的 (date, minute) ——
  23:56–23:59 與次日 00:00(若 n 使其同桶)自然合併。日盤-only 資料(個股/大盤)
  永不觸發 minute≥1436,行為零變化。vitest:23:56–00:03 @ n=5 無 "24:00" 且桶界正確。
- **uv/dv 貫通(D6)**:聚合桶累加 `uv`/`dv`(任一來源 bar 缺欄 → 該桶不設欄?——
  否,統一「缺值視 0 累加,只要任何來源 bar 有欄就設欄」;全缺 → 不設,維持
  NotRequired 語意)。vitest 斷言聚合後 uv/dv 總和不變。

### 4.4 timeframe:期貨 tab 自帶模式列

**不動 `lib/timeframe.ts`**(大盤頁專用;動 union 會讓大盤頁長按鈕,W-1 同型教訓)。
新 `lib/fut-chart-mode.ts`:
`type FutChartMode = "intraday" | "m1" | "m5" | "m15" | "m30" | "m60" | "day"`、
`FUT_CHART_MODES`(分時/1分/5分/15分/30分/60分/日K)、`futMinutesOf`、localStorage key
`copycat-fut-chart-mode`(`lib/constants.ts` 註冊 + purgeOrphanKeys 白名單,還原走
白名單驗證)。

## 5. 前端:FuturesChart 元件(SC-1/2/7/8/11)

新 `components/futures/FuturesChart.tsx`(FuturesPage 主區、DepthBar 下方):

- 頂列:模式鈕列(aria-pressed;點選寫 localStorage)。
- `intraday` → §3.2 分時 SVG(幾何函式抽 `lib/allday.ts` 可測)。
- 分 K → `aggregateBars(minuteBars, n)` 餵 `CandleChart`;日 K → daily bars 餵
  `CandleChart`。
- **CandleChart 擴充(additive,個股/大盤零行為變化)**:
  - `hlines?: {priceMilli: number, label: string, className: string}[]` — 水平 overlay
    線(持倉均價、OI 撐壓);超出當前 y 視窗的線**不畫**(clamp 到邊緣會誤導價位)。
    父層以 `useMemo` 穩定陣列 identity(ChartStatic memo 不被打穿,D6;candle.ts 檔內
    EMPTY_LINE 同型考量)。
  - `volumeDelta?: boolean`(預設 false)— true 時量區改畫內外盤:外盤(uv)bull 色柱
    與內盤(dv)bear 色柱並列(同 bar 兩根半寬柱),**歸一分母 = 視窗內 max(uv+dv)**
    (D6;與既有 maxVol 分開算,主量柱不並存)。整段
    `!bars.some(b => (b.uv ?? 0) + (b.dv ?? 0) > 0)` → 回退既有量柱(SC-8 隱藏判定)。
  - 兩 prop 都不傳 = 現狀,既有測試不動。幾何改動落 `lib/candle.ts`
    (buildCandleGeometry 或旁支函式,入檔案清單)。
- 分時圖 overlay:均價線與 OI 線同樣畫(共用 hline 幾何)。

### 5.1 持倉均價線(SC-7)[v2: D14]

`useCapitalPositions()` → filter `market === "fut"` 且 `stock_no` 與當前
`futExchangeContract(product, resolvedYm)` **完整字串相等**(不做前綴/長度猜測;
rollover:舊月契約部位不匹配新月圖表 → 不畫,正確)。多筆各畫一條;label =
`均 {price} {多|空}{qty}口`。`avg_price` null → 不畫。未登入/hook error → 空,天然降級。

### 5.2 OI 撐壓線(SC-11)[v2: D9]

新 `hooks/useOiLevels.ts`:useQuery `/api/futures/oi-levels`,staleTime 1h,
`retry 1`、`throwOnError: false`(線消失即降級)。**取線邏輯在前端**
(`lib/oi-levels.ts` 純函式,可測):以當前現價(`state.p`,fallback `ref`)為中心,
**帶內 strikes = [0.9 × spot, 1.1 × spot]**,call_oi 最大者 = 壓力、put_oi 最大者 =
支撐(帶內空 → 不畫;spot 無值 → 不畫)。label = `壓 {strike}` / `撐 {strike}`,
hover title 含 OI 口數與 date。TXF/MXF/TMF 共用同一份。strike → priceMilli ×1000。

## 6. 前端:header 價差與結算(SC-5/SC-6)

### 6.1 期現價差 [v2: D3]

`FuturesPage` 新 prop `twse: IndexSeries | null`(App 已持有,傳入一行)。顯示於報價列
後:`價差 {+/−N.n}`(`state.p − twse.p` 毫點差 /1000)。**顯示 gate(D3)**:
`twse.p != null && !twse.stale && inTwseSessionNow()` —— 新增 `lib/spot-session.ts`
`inTwseSessionNow()`(週一〜五 09:00–13:33;`index_engine` 的 stale 只在 09:00–13:25
watch 窗內維護,收盤後 p 保留收盤值且 stale 恆 false,單靠 stale 會整夜顯示假價差)。
gate 不過 → `價差 —`。色:正=text-bull、負=text-bear、零/無=text-ink-dim。
vitest 必含:夜間 `{p: 23000, stale: false}` + 期貨有價 → 顯示 `價差 —`。

### 6.2 結算倒數

新 `lib/settlement.ts`:

- `thirdWednesday(ym: string): string`(YYYYMM → YYYY-MM-DD;純日曆計算)。
- `settlementCountdown(ym: string, today: string): number | null` — 今天(含)到第三週三
  的**週一〜週五日數**(T-0 = 當天;已過 → null,防 HOT 換月前殘留)。國定假日不扣
  (brainstorm known limitation)。
- FuturesPage header badge:`結算 T-{N}`(font-mono text-xs);N==0 → amber 底
  `今日結算`。resolvedYm null → 不顯示。
- `FuturesLadder` 頂部警示列:元件內部由 `resolvedYm` 自算,T-0 時武裝列上方插一條
  amber 細列 `⚠ 今日結算`。

## 7. 前端:全撤 / 平倉(SC-10)[v2: D14]

`FuturesLadder` 武裝列旁兩鈕:

- **全撤**:`myLots.flatMap(l => l.seqNos)` 逐筆 `cancelOrder.mutate({seq_no, market:
  "fut"})`(與既有 `cancelLot` 同規則:直刪無彈窗 —— 只減暴露)。`myLots` 空 → disabled。
- **平倉**:`useCapitalPositions` filter fut + 契約完整字串相等(同 §5.1)→ 有部位才
  enabled;點擊開 `CapitalConfirmDialog`(列出將平的每筆:方向/口數/估價),確認後逐筆
  `useClosePosition().mutate`。**close body 與 `CapitalPositionsList` 共用同一支
  helper**(D14/R2-3 [v3]:抽 `lib/close-order.ts` 建
  `{market, key: pos.stock_no, price, qty: Math.abs(pos.qty)}`,`kind` **只在
  `market === "sec"` 且 `kindOf(pos) !== null` 時附加**(fut 不送 —— 既有註解:OI 列
  無庫存種類維);`price` = `futCloseEstimate`。**複合鍵 `rowKeyOf`(stock_no:kind)
  只用於 UI 列選取,不進 body**。CapitalPositionsList 改呼叫同 helper 為行為不變的
  抽取,以既有 vitest 斷言 body 形狀不變當保護)。
- 兩鈕都在 ladder 內 → 隨 D-13 條件 render unmount,不引入跨 tab 存活的送單面。

## 8. 檔案清單(預估)[v2: D4/D5/D6]

| 檔 | 動作 |
|---|---|
| `copycat/live/stock_source.py` | parse_1k_bars 多段域 + UTC datetime 轉換 + uv/dv |
| `copycat/live/futures_source.py` | FUTURES_ALLDAY_DOMAIN + session 參數 + 窗前移/filter |
| `copycat/server/futures_engine.py` | bars_range 加 keyword-only session 轉發 |
| `copycat/server/bars.py` | cache key 帶 session 複合鍵 |
| `copycat/server/app.py` | market_bars session query + oi_levels 註冊 |
| `copycat/server/oi_levels.py` | 新:FinMind OI service + endpoint |
| `tests/helpers/fake_sources.py` | fake fetch_bars_range 加 session 參數 |
| `frontend/src/lib/allday.ts` | 新:兩段軸 + 錨定日 slice |
| `frontend/src/lib/fut-chart-mode.ts` | 新:模式值域 |
| `frontend/src/lib/settlement.ts` | 新:第三週三 |
| `frontend/src/lib/spot-session.ts` | 新:現貨時段判定(價差 gate) |
| `frontend/src/lib/oi-levels.ts` | 新:帶內取 max 純函式 |
| `frontend/src/lib/close-order.ts` | 新:close body 共用 helper(自 CapitalPositionsList 抽取) |
| `frontend/src/lib/trading-hours.ts` | inFuturesAllDayHours(星期維度) |
| `frontend/src/lib/candle.ts` | Bar uv/dv、aggregateBars 24:00 正規化 + uv/dv、hline/delta 幾何 |
| `frontend/src/hooks/useFuturesBars.ts` | 新 |
| `frontend/src/hooks/useOiLevels.ts` | 新 |
| `frontend/src/components/stock/CandleChart.tsx` | hlines + volumeDelta(additive) |
| `frontend/src/components/futures/FuturesChart.tsx` | 新:主圖元件 |
| `frontend/src/components/futures/FuturesPage.tsx` | 掛 chart + 價差 + 結算 badge |
| `frontend/src/components/futures/FuturesLadder.tsx` | 全撤/平倉鈕 + T-0 警示列 |
| `frontend/src/components/capital/CapitalPositionsList.tsx` | 平倉 body 改走共用 helper(行為不變) |
| `frontend/src/App.tsx` | FuturesPage 傳 twse prop |
| `frontend/src/lib/constants.ts` | 新 localStorage key |
| `frontend/src/types.ts` | oi-levels 回應型別 |

## 9. SC 對應表

| SC | 設計節 |
|---|---|
| SC-1 分時圖 | §3, §5 |
| SC-2 多週期 | §4.4, §4.3, §5 |
| SC-3 夜盤貫通 | §1 |
| SC-4 商品同步 | 既有(FuturesChart 吃 `product` prop 隨 App state;迴歸測試) |
| SC-5 價差 | §6.1 |
| SC-6 結算 | §6.2 |
| SC-7 均價線 | §5.1 |
| SC-8 內外盤副圖 | §1.3, §4.3, §5 |
| SC-9 掛單(既有) | 迴歸:既有測試 |
| SC-10 全撤/平倉 | §7 |
| SC-11 OI 線 | §2, §5.2 |
| SC-12 夜盤時窗 | §4.2 |

## 10. 驗證與真實環境注意 [v2: D13]

- 自動化:pytest(§1 段域/UTC 轉換/uv/dv、§1.4 session key、§2 service mock 用真樣本
  欄位形狀)+ vitest(§3 軸/slice、§4.2 時窗、§4.3 聚合、§5 元件、§6 lib、§7 鈕)。
- SC-3 量法(可直接複製):
  `curl -s "localhost:<port>/api/market/bars/TXF?tf=1&days=5&session=allday"` → python 數
  bars 長度且斷言存在 `t` 以 `15:01` 結尾與 `00:0x` 開頭時刻的 bar、`13:45` 與 `15:01`
  相鄰。真 TC4 下單日約 300 + 840 根/交易日。
- 真實環境:**盤中不起第二台 TC4 後端**。HTTP 層(session 參數、oi-levels)用 fake
  source + 另一 port;UI 用 vite dev(proxy 8721)。SC-3 真 TC4 驗證需跑新 code 的
  server —— 窗口不可得則記 `phase_6_blocked_reason`,fallback = fake rows(含夜盤/
  midnight 構造樣本)+ user prod 重啟後過目。
- OI 真實驗證:oi-levels 在 fake-source server 上直接真打 FinMind(不碰 TC4)。
- Phase 6 量測項(D10/R2-8 [v3]):allday 單次回應 bytes、冷啟動收割秒數、
  **盤中當日段單次收割耗時與列數(allday vs day 對照)** —— allday 當日窗 ≈31 小時
  最多 ~1140 列且走 futures session `api.lock`,若實測 >1s 考慮提高當日段 TTL,
  結果回寫本節。

## Known Risks

- Date 欄語意(§1.1)為強佐證假設,Phase 6 真資料核對前不視為已證;若實測翻案
  (Date 已是台北日),修正點單一(轉換函式),測試改斷言即可。
- 國定假日:結算倒數與時窗判定都不含假日行事曆(既有慣例一致)。
- days=5 下 30/60 分 K 無歷史回看(初始視窗即全部;R2-7 已知取捨)。
