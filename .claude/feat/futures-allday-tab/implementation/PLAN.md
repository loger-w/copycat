# implementation PLAN(condensed)— futures-allday-tab

依 design.md v3。impl-spec review round 1(16 條)全數修入,見
`impl-spec-review-round-1.json`。TDD:每節列紅測試(對應 SC);實作順序 = 後端 → 前端 lib → 前端元件
(依賴序)。commit tag 紀律照 feat 流程(🟢 test [red] → 🟢 feat [green])。

## 後端

### 1. `copycat/live/stock_source.py`(高風險:共用 util)

- `Bar` 加 `uv: NotRequired[int]`、`dv: NotRequired[int]`(import `NotRequired` from
  typing;Python 3.13 OK)。
- `_parse_1k_rows`:`_RawK` 加 `uv`/`dv`(`_int_field(row, "UpVolume")` / `"DownVolume"`,
  缺值 0)。
- `_fold` / `_merge_into`:uv/dv 累加(`bar["uv"] = bar.get("uv", 0) + k["uv"]`;僅在
  來源有欄時設 —— 1K 路徑恆有,DK 路徑不經 _fold 不受影響)。`aggregate_1k_to_daily`
  同步。
- `parse_1k_bars(rows, domain)`:`domain: tuple[str,str,str] | Sequence[tuple[str,str,str]]
  | None`。單值(tuple of 3 str)→ 既有路徑零改動。序列 → 新路徑:每列走
  `_taipei_dt_key(date_str, time_str, segments)`(新函式):
  `datetime(UTC) + timedelta(hours=8)` → 台北 (date, HHMM),逐段判定(含 clamp:
  `seg_end < key <= clamp_end` → seg_end),**不加 1 分鐘**;回 `(date_str, key) | None`。
- `_merge_into` 簽名改 `_merge_into(bar: Bar, k: _RawK) -> None`(R10;吃 _RawK 才拿
  得到 uv/dv,呼叫點 `_fold` 同步)。多段判別法寫死:`isinstance(domain[0], str)` →
  單段既有路徑(三元素 str tuple 也是 Sequence,不可用 isinstance(Sequence) 判)。
- 紅測試(`tests/live/test_stock_bars.py` 新 class,SC-3):
  - UTC Time="004500"(台北 08:45)→ **丟棄**(落 day 段 start 0846 之前,與既有
    FUTURES_MINUTE_DOMAIN 同語意;R9 拍板)。
  - 單段路徑(tuple)行為零變化;序列路徑走新分支(R10)。
  - Time="070100" → 台北 15:01(夜盤前半首根)。
  - Time="155900" → 台北 23:59 **當日**(不進位、不加 1)。
  - Time="160000" → 台北**次日** 00:00。
  - Time="205900" → 次日 04:59;Time="210300" → clamp 次日 0500;Time="211000" → 丟。
  - uv/dv:兩列同分鐘 → 累加;聚合日 bar uv/dv 總和正確。

### 2. `copycat/live/futures_source.py`

- `FUTURES_ALLDAY_DOMAIN`(design §1.2 三段)。
- `fetch_bars_range(..., *, session: str = "day")`:tf="1" 且 session="allday" →
  SubHistory 窗 start=`(start_date−1日)16`、end=`end_date 23`;parse 用
  FUTURES_ALLDAY_DOMAIN;之後 filter `start_date <= bar.t[:10] <= end_date`。
  其餘路徑零改動。
- 紅測試(`tests/live/test_futures_bars.py`,R16 指名):fake collect rows(跨 UTC 日)
  → session=allday 回含夜盤 bars 且窗外台北日期被 filter;**直接斷言 SubHistory 窗字串**
  = `(start−1日)16` / `end 23`(含跨月、跨年各一例);session 預設 day 行為不變
  (既有測試保護)。

### 3. `copycat/server/futures_engine.py`

- `bars_range(self, product, tf, start, end, *, session: str = "day")`:
  `functools.partial(fetch, product, tf, start, end, session=session)` 進 to_thread;
  source 無該參數時(舊 fake)—— 不做相容分支,fake 同步升級(見 §5;**含
  `tests/server/test_futures_engine.py` 內嵌的 `Boom.fetch_bars_range`**,R2 —— 漏改
  會讓既有降級測試由 ConnectionError 變 TypeError 爆掉)。
- 紅測試:fake source 收到 session kwarg(`tests/server/test_bars.py` / 既有引擎測試檔)。

### 4. `copycat/server/bars.py`(高風險:共用 cache)

- cache key(R7/R8 精確化):**只有 `build_minute`** 的三處 cache 呼叫(hist memo /
  today / `_empty` 負向)的 code 鍵改複合 `f"{code}:{session}"`;`build_daily`(個股
  tf=D)與 `build_period`(大盤/期指 tf=D,鍵 `f"{code}|L"`)**完全不動**(tf=D 無
  session 維度)。**複合鍵只在 cache 查表處組出,傳給 `fetch` 的第一個引數維持原
  `code`**(覆寫掉會讓個股以 "2330:day" 查 TC4,全空如 timeout)。
- `app.py` 的 minute fetcher closure 綁 session。
- 紅測試(`tests/server/test_bars.py`):同 code 不同 session 各自獨立 cache(day 寫入
  不污染 allday;負向 cache 同理);**fetcher 收到的 code 不含 `:session` 後綴**(R8)。

### 5. `tests/helpers/fake_sources.py`

- fake `fetch_bars_range` 簽名加 `*, session="day"`,記錄收到的 session(供斷言);
  可注入夜盤 rows。

### 6. `copycat/server/app.py`

- `market_bars`:query `session: str = "day"`;值域驗證(非 `day|allday` 或非期指 key
  帶 allday → 400 `INVALID_SESSION`);傳入 minute 路徑(tf=D 忽略 session —— 忽略的
  參數不進 cache key,D-15 慣例)。
- 註冊 oi_levels router/route。
- 紅測試(`tests/server/test_market_routes.py`):
  - `?session=allday` 對 TXF → fake source 收到 allday、回含夜盤 bars。
  - `?session=allday` 對 TWSE → 400 INVALID_SESSION;`?session=xxx` → 400。
  - 無 session → day(既有測試不紅)。

### 7. `copycat/server/oi_levels.py`(新)

```python
async def fetch_oi_levels(contract_ym: str, *, token: str | None, today: date) -> OiLevels
# OiLevels = {"date": str|None, "contract": str|None, "strikes": [{"strike","call_oi","put_oi"}]}
def register_oi(app) -> None  # GET /api/futures/oi-levels(R1:engine 走
#   request.app.state.futures —— create_app 期 state.futures 恆 None,boot 後才有;
#   state.futures None / resolved_contract None → 200 空 shape)
```

- urllib + to_thread;range 查詢 today−10..today;filter session=position +
  contract_date==ym;取 max(date) 日;pivot per-strike。
- 快取 `(contract_ym, today)` 正向永久 / 失敗與 402 負向 300s;asyncio.Lock 單飛;
  token 讀取 env→.env(utf-8-sig never-raise);retry except 含 TimeoutError,402 不 retry。
- 紅測試(`tests/server/test_oi_levels.py` 新檔;mock urlopen 用 design §2 真樣本欄位):
  正常 pivot / after_market 列被濾 / 週選 W 碼被濾 / token 缺 → 空 shape / 402 → 負向
  快取(第二次呼叫不再打)/ 正向快取命中不重打。
- **route 整合測試(R3;同檔或 test_market_routes.py)**:(a) fake futures engine 有
  resolved_contract + mock service → 200 strikes 形狀正確;(b) resolved_contract None
  → 200 `{date:null,contract:null,strikes:[]}`;(c) `app.state.futures is None` →
  同 (b) 200 空 shape(降級一律 200,SC-11 語意)。

## 前端 lib(全部新檔先寫紅測試;SC 對應標於各節)

### 8. `lib/allday.ts`(SC-1/SC-3)

`ALLDAY_SEGMENTS`(300/539/301)、`alldayIndexOf(hhmm): number|null`、
`ALLDAY_TICKS: {index,label}[]`(段起點法)、`sliceCurrentAllday(bars): Bar[]`
(錨定日推導)、`anchorDateOf(t: string): string`(§3.1/§3.2 共用;≤05:00 → date−1)。
紅測試:錨點值(0846→0(注意 0845 開盤首根即 0846)、1345→299、1501→300、2359→838、
0000→839、0500→1139)、段長總和 1140、ticks 全部有效、slice 缺 08:46 不錯位、
夜盤-only 冷啟動 fallback、空輸入;**週末跨越(R5,edge case 2)**:(a) 末根 =
週六 05:00 → anchor = 週五、slice 含週五 08:46 起全段;(b) 同份 bars 追加週一 08:46
一根 → anchor 切至週一、週五段被切掉。

### 9. `lib/fut-chart-mode.ts`(SC-2)+ `lib/constants.ts`

mode union / 標籤列 / `futMinutesOf` / localStorage key + purge 白名單。紅測試:還原
白名單驗證(壞值 → 預設 intraday)。

### 10. `lib/trading-hours.ts`(SC-12)

`inFuturesAllDayHours(now?: Date): boolean`(星期維度,design §4.2)。紅測試:
brainstorm SC-12 的 11 個(星期,時刻)對。

### 11. `lib/candle.ts`(高風險:共用 util;SC-2/SC-8)

- `Bar` 加 `uv?: number; dv?: number`。
- `aggregateBars`:(a) 桶 `bucketEnd >= 1440` → date+1、minute−1440 正規化(`stampOf`
  永不產 "24:00";與次日 00:00 桶同 key 自然合併);(b) uv/dv 累加(任一來源有欄即設,
  缺值視 0)。
- 新幾何(R11 拍板單一形式):`buildCandleGeometry` 輸出**新增欄**
  `deltaVol: {uvH: number, dvH: number}[] | null` —— 與 `candles` 同索引對位(同 cx /
  柱寬 / 量區高度來源),分母 = 視窗內 `max(uv+dv)`,視窗內全無 uv/dv → null(SC-8
  隱藏判定的資料面);hline:`hlineYOf(priceMilli, geometry): number | null`(超出 y
  視窗回 null 不畫)。24:00 正規化的 date+1 用 `new Date(\`${date}T00:00:00\`)` +1 天
  再格式化(candle.ts 現無日期加法 helper)。
- 紅測試:23:56–00:03 @ n=5 無 "24:00" 且桶界正確;**跨月/跨年**(2026-08-31 23:56 →
  2026-09-01 00:00;12-31 → 次年 01-01,R11);uv/dv 聚合總和不變;deltaVol 對位與
  null 判定;日盤資料行為 bit-for-bit 不變(既有測試保護)。

### 12. `lib/settlement.ts`(SC-6)

`thirdWednesday(ym): string`、`settlementCountdown(ym, today): number|null`(週一〜五
計數;過期 null)。紅測試:2026-08(第三週三 = 8/19)、月初/T-0/跨月/已過。

### 13. `lib/spot-session.ts`(SC-5)

`inTwseSessionNow(now?: Date): boolean`(週一〜五 09:00–13:33)。紅測試:日內/夜間/週末。

### 14. `lib/oi-levels.ts`(SC-11)

`type OiLine = {priceMilli: number; label: string; className: string; title: string}`
(R4;title = `「壓/撐 {strike}・OI {口數}口・{date}」`,承載 SC-11 的 hover 驗收);
`pickOiLines(strikes, spotMilli, date): {call: OiLine|null, put: OiLine|null}`(±10%
帶內取 max;帶內空或 spot null → null)。紅測試:真樣本形狀(深度價外 55000 被帶
排除)、帶內空、spot null、**title 內含口數與日期**(R4)。

### 15. `lib/close-order.ts`(高風險:送單面;SC-10)

`closeBodyOf(pos: CapitalPosition, price: number): CapitalCloseBody` — key=stock_no、
kind 僅 sec 且 kindOf 非 null 附加、**qty 由 helper 內部給(重現 CapitalPositionsList
既有送法,以既有測試錨定;兩個呼叫端 body 同形,不開 qty 參數 —— R12:同形正是抽
helper 的理由)**。`kindOf` 與其值域常數(`KIND_TEXT` 的鍵集)**一併移入本檔**(R13:
值域單一定義;CapitalPositionsList import 回去做 UI 標籤)。紅測試:fut 不含 kind、
sec 含、daytrade_sell 不含(kindOf null)、兩呼叫端同形;`CapitalPositionsList` 改走
helper 後既有測試斷言 body 形狀不變。

## 前端 hooks / 元件

### 16. `hooks/useFuturesBars.ts`(SC-1/2/3)

單 query `tf=1&days=5&session=allday` + 日 K `tf=D`;refetchInterval 60s ×
`inFuturesAllDayHours()` 函式形式;queryKey 含 session/days。測試:hook 層以
`frontend-testing` 慣例 mock fetch,斷言 URL 與輪詢開關。

### 17. `hooks/useOiLevels.ts`(SC-11)

useQuery `/api/futures/oi-levels`,staleTime 1h,retry 1,throwOnError false。
紅測試(R14):mock fetch 500 → 不 throw、data undefined(降級設定真的關著)。

### 18. `components/stock/CandleChart.tsx`(SC-7/8/11)

Props 加 `hlines?: {priceMilli, label, className, title?: string}[]`(R4:title 渲染
成 svg `<title>`;父層 useMemo 穩定)與 `volumeDelta?`;ChartStatic 增渲染;
兩 prop 缺省 = 現狀(既有測試不動)。測試:hline 超窗不畫、title 渲染、volumeDelta
無資料回退量柱、有資料畫雙柱。

### 19. `components/futures/FuturesChart.tsx`(新;SC-1/2/4/7/8/11)

模式列 + 分時 SVG(allday 軸 + live 點含錨定日 gate)+ CandleChart 掛載 + overlays
(均價線 §5.1 完整字串相等 / OI 線)+ 空態文案(meta.source unavailable → 進行式)。
**日 K 量口徑 meta 註記本輪不做**(R15 拍板:design §1.2 D13 若 Phase 6 實測為
(b) DK 僅日盤量,記 `docs/next-time.md` 加註記,不在本輪加 UI)。
測試:模式切換持久化、分時 render(含 13:45→15:01 相鄰)、live gate 開盤瞬間案例、
均價線有/無部位、OI 線降級。

### 20. `components/futures/FuturesPage.tsx` + `App.tsx`

Page:掛 FuturesChart、header 價差(gate 三條件)+ 結算 badge;新 props
`twse`(App 傳入)。App:一行 prop。測試:價差三態 + 夜間假價差案例(stale false
仍顯 —)、badge T-N/T-0、SC-4 商品切換圖表跟隨。

### 21. `components/futures/FuturesLadder.tsx`(高風險:送單面;SC-6/9/10)

- 全撤鈕:`myLots.flatMap(seqNos)` 逐筆 cancel;空 → disabled。
- 平倉鈕:positions filter(fut + 契約完整相等)→ **gate(R6):任一筆
  `futCloseEstimate` 為 null → 鈕 disabled + title「無行情估價」(與
  CapitalPositionsList est===null 處置一致;後端對 price<=0 直接 raise,不可送)** →
  CapitalConfirmDialog → 確認後逐筆
  `useClosePosition().mutate(closeBodyOf(pos, est))`(est 已保證非 null)。
- T-0 警示列(settlementCountdown===0)。
- 測試:全撤 disabled/送出 seq 清單、平倉 dialog 內容與確認後 body、非本契約部位不入
  清單、**有部位但估價 null → disabled + title(R6)**、T-0 列出現;**既有掛單顯示/
  點刪測試不動(SC-9 迴歸)**。

### 22. `components/capital/CapitalPositionsList.tsx`

close body 改走 `closeBodyOf`(行為不變重構;既有測試綠 = 保護)。🔵 refactor commit。

### 23. `types.ts`

`OiLevelsResponse` 型別。

## 驗證 gate(完成前)

pytest -q / ruff / pyright / copycat validate(後端);npm test / npx tsc -b /
npx eslint src(frontend/)。UI SC 截圖:Phase 6(claude-in-chrome,vite dev proxy 8721)。
