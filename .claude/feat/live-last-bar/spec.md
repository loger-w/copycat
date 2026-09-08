## Problem Statement

看盤日常是 preview 頁整天掛著(CLAUDE.md §1)。個股頁的 K 線在盤中**不會當下更新**:

- 分 K(1–10 分)每 60 s 向後端拿正式 1 分 K,後端當日段又有 30 s 快取 → 最新那一兩根晚 30–90 s 才出現,進行中的那分鐘整根看不到。
- 日 K 今天那根在第一次開圖抓一次後整天不動;W2(#206)後 14:01 換一次定稿、午夜再一次,盤中仍是早上的快照。

user(09-08 grilling Q1 原話):「在盤中當下不能更新嗎?我有發現在看盤當下 日K 跟分K 都不會當下更新,我想做成即時更新可以嗎」。
後端不再更常抓已排除(日 K 盤中每分鐘打 TC4 DK 會與即時行情搶同一把 `api.lock`,且 DK 同 session 重查有凍結快照問題,#171 已用換窗繞過但成本仍在)。
前端手上本來就有逐筆成交折出的即時狀態(`StockAccum`:每分鐘高 / 低 / 收 / 量 / 內外盤、當日高低、現價、累積量),
缺的只是「拿它把最後一根算出來」。

## Solution

前端新增**即時末根**(CONTEXT.md):以 `StockAccum` 折出的資料,蓋在**正式 K 棒**之後補到現在;正式 K 棒到了就讓位。

- **分 K**:正式 1 分 K 最後一根之後、到現在這一分鐘為止的每一分鐘,由 accum 的分鐘累積補成 1 分 bar(含進行中的那分鐘),
  再走既有 `aggregateBars` 聚成 2–10 分。60 s 輪詢照舊,正式版一到就換掉補的那幾根。
- **日 K**:今天那根以 accum 的當日高 / 低 / 現價 / 累積量即時更新(價與量都動);今天那根還沒有(09:00 前開圖)就補一根。
  正式版**定稿**(日 K 資料是 14:00 界後才抓回來的)就不再蓋。
- **節奏**:逐筆 —— 後端 `ticks` 打包 0.1 s 一則,accum 每則更新一次,K 線跟著重算;整張圖重畫量測 > 16 ms 才退到只重畫末根(見 Implementation Decisions)。
- 三頁只做**個股頁**(user Q10 (a));期貨 / 加權另開批,規則寫成共用純函式讓下一批只接線。

## User Stories

1. As a 盯盤者, I want 個股頁分 K 最後一根跟著每筆成交跳(含進行中那分鐘), so that 看 3 分 K 時不用等 60–90 秒才看到這一分鐘。
2. As a 盯盤者, I want 日 K 今天那根的高低收與量盤中即時變, so that 日 K 不是早上的快照。
3. As a 盯盤者, I want 正式 1 分 K 每分鐘到了就自然換掉前端補的那幾根, so that 畫面上停留的永遠是最接近正式的值(補的根最多存在 90 s)。
4. As a 盯盤者, I want 13:30 收盤到 14:01 之間今天那根維持前端算的值、14:01 換達錢定稿, so that 收盤後不會退回早上的舊值。
5. As a 盯盤者, I want 14:01 那發失敗**或拿到墊背舊快照**(達錢關著 / 忙:後端回 200 + 界前快照 + status 非 ok)時今天那根不退回舊值, so that 失敗不比沒做更糟。(pr-218 review F-01 回校:原句只寫「失敗」,HTTP 非 2xx 那半)
6. As a 盯盤者, I want 09:00 前開著的頁不會把昨天的成交貼成今天那根, so that 早上開圖不出假 K。
7. As a 盯盤者, I want 換股當下不會把前一檔的成交貼到新股的 K 線上, so that 切股不閃錯圖。
8. As a 盯盤者, I want 個股期合約態維持只有分時、K 線鈕反灰, so that 這批不動合約態(Q8)。
9. As a 盯盤者, I want 逐筆節奏下頁面不卡, so that 熱門股開盤也順(Q2 拍板逐筆,掉幀才退)。
10. As a 維護者, I want 補尾規則是一支零 React 的純函式, so that 期貨 / 加權下一批直接接線、規則表用單元測試釘住。
11. As a 維護者, I want 分鐘鍵對齊(accum 起點分 → 1K 終點分 +1;13:30 收盤併進 13:30 那根)由測試釘住, so that 不會出現整條右移一格或 13:31 這根不存在的 bar。

## Implementation Decisions

**純函式 `frontend/src/lib/live-last-bar.ts`(seam (b))**

- `mergeLiveMinuteBars(official: readonly Bar[], accum: StockAccum, today: string, nowMinute: number): Bar[]`
  - 只補 `t` 嚴格晚於正式 1 分 K 末根(且末根日期 = today)的分鐘;正式末根不是 today(09:00 前 / 首根未到)→ 從 accum 最早的分鐘補起。
  - 分鐘鍵對齊:accum 分鐘 `m`(起點分,`HH*60+MM` of tick time)→ 1K bar 終點標記 `m + 1`;**上限 13:30**(`min(m+1, 810)`,收盤撮合 13:30:00 那筆併進 13:30 那根,不產生 13:31);下限 09:01(試撮 tick 後端已丟,accum 無 09:00 前分鐘,仍以 `< 09:01` 丟棄防禦)。
  - 補的 bar:`o` = 前一根(正式或已補)的 `c`(前端沒記每分鐘首筆;最多 90 s 後被正式版換掉,user Q11 知情);`h` / `l` = 分鐘 `h` / `l`(null → 用 `c`);`c` = 分鐘 `c`;`v` = 分鐘 `v`;`uv` / `dv` = 分鐘 `o` / `i`(外 / 內盤;既有 1K 有欄,補的根也給欄才不會讓聚合桶「全缺」與「部分缺」在桶界漂)。
  - 只補到 `nowMinute` 對應的 bar(進行中那分鐘 = `min(nowMinute + 1, 810)`);accum 分鐘若晚於它(時鐘倒退)忽略。
  - 純函式:不讀時鐘、不讀日曆;`today` / `nowMinute` 由呼叫端給。
- `mergeLiveDailyBar(official: readonly Bar[], accum: StockAccum, today: string, opts: { dayOpen: number | null }): Bar[]`
  - 末根 `t === today` → 以 merged 取代:`o` 保留正式的;`h` / `l` 取**正式與 accum 的聯集**(`Math.max` / `Math.min`;pr-218 review F-02 回校:accum 的 running max/min 只在 TICKS 回補落地後才是當日全量,盤中重啟 / 回補放棄時直接取代會窄化;原句「必然 ⊇」為假),`c = accum.last.p`,`v = accum.last.cum_vol`(= TC4 當日累積量,DK 的 `v` 與之同源;不用 `accum.volume` 那是 VWAP 分母、去重口徑不同)。
  - 末根 `t < today` → append 一根 `{t: today, o: dayOpen ?? accum 最早分鐘的 c, h, l, c, v}`。
  - 末根 `t > today`(不該發生)或 accum 無成交(`last === null` / `high === null`)→ 原樣回傳。
  - `dayOpen` 由呼叫端給:今天正式 1 分 K 首根(09:01)的 `o`(有就用),否則 null → 退 accum 最早分鐘 `c`。
- 兩支都不改動傳入的 array / 正式 bar 物件(新 array + 新末根物件),正式段元素 identity 保留(CandleChart geometry 的 memo 友善)。

**接線 `StockChart.tsx`(seam (a))**

- `useStockBars` 多回 `dataUpdatedAt`(TQ 既有欄位,hook 零邏輯改動)。
- 啟動閘(呼叫端判,純函式不判):
  - `accum.code === code` 且 `!accum.noData` 且非期貨態(既有 `isFut` 已擋 K 線)。
  - **牆鐘同日 09:00 起**(`now` 時分 ≥ 09:00;日期 = `isoLocalDate(now)`):stock engine 08:00 才換日,凌晨 accum 仍是昨天的,09:00 前不補(story 6)。
  - **交易日**(`isTradingDay(now)`;2026-09-08 two-axis spec S-01 修訂,原句「交易日曆不看:休市日 accum 無成交 → 純函式自然 no-op」前提為假):休市日引擎 rollover stage2 等新日首筆 tick、假日永遠不來,accum 整天沿用前一交易日的分鐘 / 高低 / 現價,不擋會把前一交易日貼成今天的假 K。週末靠 weekday、國定假日靠 `/api/calendar` 假日集合(未載入退回只擋週末)。
  - 日 K 另加**定稿閘**:`dataUpdatedAt` **≥** 今天 14:00 界(`DAILY_FINAL_TIME`,與 `lib/day-bars-rollover.ts` 同一顆常數;界的定義 = 當日 14:00:00 本機時刻,等於即算定稿,與 CLAUDE.md §4 口徑同;two-axis spec S-02 回校)**且那一趟 `status === "ok"`** → 不蓋(story 4 / 5:14:01 refetch HTTP 失敗時 `dataUpdatedAt` 不前進 → 繼續補;達錢關著 / 忙時後端回 200 + 墊背 + status 非 ok,`dataUpdatedAt` 會前進但 status 擋住 → 繼續補;pr-218 review F-01 回校;真定稿才停)。分 K 無此閘(正式 1 分 K 只會往後追加,補的根永遠只在正式末根之後)。
- 順序:1 分 K 原料 → `mergeLiveMinuteBars` → `aggregateBars(…, minutesOf(mode))`(補在聚合**之前**,2–10 分的進行中桶由既有聚合算);日 K → `mergeLiveDailyBar`。
- `useMemo` deps = `[data, accum, mode, today, nowMinute, final]`:accum 每則 ticks 打包換 identity(0.1 s),重算成本 = 一次 `aggregateBars`(30 日 1 分 K ≈ 5,900 根,O(n))+ merge O(補的根數)。
- 「現在幾分」由 render 時的 `new Date()` 取(與 `FuturesChart` live 點同慣例:牆鐘不進 memo deps 的問題以 `nowMinute` 純量 dep 解 —— 同分鐘同 accum 命中 memo)。
- **重畫成本**:CandleChart `ChartStatic` memo 會因 `bars` identity 每 0.1 s 打穿一次,重建可視 ≤ 700 根 × 3 節點。實作時以 React Profiler / `performance.now()` 量單次 commit;**> 16 ms** 才做退路(只重畫末根:`ChartStatic` 拆成「正式段 memo + 末根層」,正式段 bars identity 穩定就不重建)。量測數字寫進 verification。

**不動**

- 後端零改動;`useStockBars` 輪詢節奏、日 K 兩道界政策、`barsPollInterval`、CandleChart geometry / viewport(追加根走既有 `onTotalChange` 延伸)、`StockIntradayChart`、群組圖牆卡片、個股期合約態、`CandleChart` readout。

## Testing Decisions

- seam (b) `lib/live-last-bar.test.ts` 規則表(每條一案):
  1. 正式末根 today 09:05、accum 分鐘 09:04 / 09:05 / 09:06 → 只補 09:06、09:07 兩根,09:06 的 `o` = 正式 09:05 的 `c`,09:07 的 `o` = 補的 09:06 的 `c`。
  2. 13:29 與 13:30 兩個 accum 分鐘 → 併進單一根 13:30(h/l/v 合併、c 取 13:30),不產生 13:31。
  3. 正式末根不是 today(昨天 13:30)→ 從 accum 最早分鐘補起、`o` = 昨天末根 `c`。
  4. `nowMinute` 09:06 → 09:08 的 accum 分鐘不補(時鐘倒退防禦)。
  5. 分鐘 `h` / `l` 為 null → 用 `c`;`uv` / `dv` = 分鐘 `o` / `i`。
  6. 日 K 末根 today → `o` 保留、h/l/c/v 換 accum;末根昨天 → append today 一根,`o` = `dayOpen`,dayOpen null → accum 最早分鐘 `c`。
  7. 日 K accum 無成交(`last === null`)→ 原樣;末根日期 > today → 原樣。
  8. identity:正式段元素 `===` 原物件、傳入 array 未被改動。
  9. 與 `aggregateBars(…, 3)` 串接:補的 09:06 / 09:07 落進 09:06 桶(終點 09:06 = (09:03, 09:06])與 09:09 桶(進行中)。
- seam (a) `StockChart.livebar.test.tsx`(RTL;fetch mock 回一份 1 分 K + 日 K;時鐘固定盤中):
  1. 3 分 K 模式:掛載 → 圖上最後一根 = 進行中桶(來自 accum);rerender 換一份多一筆成交的 accum → 末根 `c` / `h` 變。斷言走 CandleChart 既有可讀面(readout / `data-*` 屬性,依 `CandleChart.test.tsx` 既有作法)。
  2. 日 K 模式:今天那根 h/l/c/v = accum;時鐘改 08:59 → 不補;`dataUpdatedAt` 改為 14:00:30 後 → 不蓋。
  3. `accum.code !== code` → 不補(換股 race)。
  4. 週六 09:06 → 不補(休市日;S-01 修訂)。
- 突變體至少三隻:`m + 1` 改 `m`(整條右移 → 案 1 / 9 紅)、13:30 上限拿掉(案 2 紅)、定稿閘拿掉(seam (a) 案 2 紅)。
- 量測:verification 記單次 CandleChart commit 時長(3 分 K 700 根可視、逐筆 0.1 s);真環境判準見 Further Notes。

## Out of Scope

- 期貨頁、加權 / 櫃買頁(含週 / 月 K)—— 下一批各自接線(原料不同:期貨無當日高低、加權無量)。
- 個股期合約態 K 線(D10 既有:只提供分時)。
- 每分鐘首筆價(真正的分鐘開盤價)—— 前端 accum 不記,補的根用前一根收盤代替。
- 後端 1 分 K / 日 K 快取、輪詢節奏;群組圖牆卡片。
- 「即時」視覺標示(user Q9 (a))。

## Further Notes

**既有行為白名單(不得變)**

- `useStockBars` 的 queryKey / 輪詢 / 日 K 兩道界 / `barsPollInterval` / `retryEmpty:false`。
- `aggregateBars` 桶界語意(終點標記、09:00 原點)、`candle.ts` 其餘;CandleChart viewport / geometry / readout;`onTotalChange` 延伸行為。
- StockChart 模式收斂(期貨態 → intraday)、A6 spotMode、`emptyNote` 三態、成交點 fills。
- 個股 WS / accum 形狀(`stock-accum.ts` 零改動;新 lib 只讀它)。

**契約提醒(CLAUDE.md §4)**

- 「個股分時圖台指期疊線分鐘鍵 = 1K 終點標記 −1 分」是同一把尺的反向(這裡 accum 起點分 +1 = 1K 終點標記);兩處各自釘測試,不共用 helper(方向相反、上限 13:30 只有這邊有)。
- `DAILY_FINAL_TIME` 多一個前端讀者(定稿閘);常數 doc「src/ 內零讀者」要改口,parity 測試不變。

**真環境判準(寫進 verification)**

- 盤中個股頁 3 分 K:最後一根與成交明細同步跳(目測 < 1 s),每整 3 分鐘新根自己長出;60 s 後 Network 一發 `tf=1` 回來,補的根被換掉時畫面無跳動 / 無整條右移。
- 日 K:今天那根高低收與側欄高 / 低 / 現價逐字同值、量 = 側欄總量;13:30 後值停住;14:01 Network 一發 `tf=D` 後今天那根 = 達錢定稿(可能微調一格),之後成交明細沒新筆。
- 08:5x 開著的頁:日 K 末根仍是昨天(不補);09:00 第一筆成交後才長出今天那根。
- React Profiler 抓 60 s 逐筆:單次 commit p95 記錄;> 16 ms 即啟動退路票。

**參考**:handoff `%TEMP%\copycat-handoff-2026-09-08-pr211-fixes-and-live-bar.md` §2;W2 spec #204(定稿界由來);CLAUDE.md §4 日 K 定稿界 parity;`FuturesChart.tsx` live 點(牆鐘落點範本);CONTEXT.md「正式 K 棒」「即時末根」(本批新增)。
