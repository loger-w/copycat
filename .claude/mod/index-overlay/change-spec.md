# change-spec — 指數分時圖 overlay(mod/index-overlay,L 級)

分流判定:**已成形**(user 指名做法 + 落點檔案 + UI 形式;grilling 姿態,決策點多屬
實作級 → [auto-default];域外疊線呈現屬方向性,已停等拍板)。

已拍板(user):CDP/日均線只做加權,櫃買無日 K 來源跳過;均價線 = 當日 minutes 前端
累計算術平均(指數無成交量);重用 overlay.py 純函式;日 K 走 index engine session;
新開 GET /api/index/overlay 只回加權;前端仿 StockIntradayChart oLines + toggle;
**域外疊線 = 右緣掛牌**(2026-08-14 user 拍板,見決策 9)。

[amendment 2026-08-14: spec review round-1 — P0-1/P0-2/P1-3~7/P2-8~11 全數採納改寫]
[amendment 2026-08-14b: spec review round-2(限縮輪)— R2-P0-1/P0-2/P1-3~6/P2-7~10
全數採納,修法逐字取 reviewer 處方:後端改走 `build_period`(鍵 `IX0001|L` 與 market
bars 日 K 真共用槽;裸 `IX0001` 是 stock session 槽,不得碰);rightEdgeLabels 補
三段式堆疊。index overlay **不使用** overlay_cache 作快取(原 `IX0001|OVL` 方案作廢);
`OverlayCache` 類別與 app 層實例是 stock overlay 的既有依賴,**保留不動**(W-6)]

## 成功條件(SC)

- **SC-1 加權分時均價線**:加權分時圖出現白色均價線(stroke-ink、1.2 寬,同個股 VWAP
  外觀);第 k 個**已有**分鐘鍵上的值 = 前 k 個已有分鐘收盤的算術平均(缺分鐘不補值,
  P2-10)。「均價」鈕 title=「分鐘收盤均價(指數無成交量)」以區辨個股 VWAP 語意。
  驗證:`index-chart-svg.test.ts` 幾何測試(給定 minutes 斷言 avgLine 各點值)+ 截圖指認
  「加權分時圖走勢線旁另有一條白色平滑線」。
- **SC-2 櫃買分時均價線**:同 SC-1,櫃買分時圖。驗證:同幾何測試(與市場無關)+ 截圖。
- **SC-3 加權 CDP/MA 疊線 + toggle**:加權分時圖頂列 toggle「均價 / CDP / MA」三顆;
  CDP 開 → **域內**的線畫水平虛線(ah 紅/nh 淡紅/cdp 琥珀/nl 淡綠/al 綠,同個股配色)
  + 線右端價位文字;**域外**的線不畫、改在右緣掛牌小字「CDP 24120↑」/「MA20 23850↓」
  (↑ = 在域上方,↓ = 域下方;同線色)。MA 開 → ma5/ma20 同規則。值來自
  `/api/index/overlay`。
  驗證:`MarketChart.test.tsx`(域內 fixture → line 數 + 右端文字;域外 fixture → 掛牌
  文字)+ 盤中截圖(指認物 = 域內線**或**右緣掛牌,允許 0 條域內線)。
- **SC-4 櫃買側 CDP/MA 反灰**:櫃買分時圖「均價」可按;「CDP」「MA」disabled 反灰 +
  title=「櫃買無日 K 資料源」(文案唯一化,P2-8)。驗證:`MarketChart.test.tsx` 斷言
  disabled + title。
- **SC-5 後端 endpoint**:`GET /api/index/overlay` 回 `{cdp, ma5, ma20, date}`(形狀同
  `/api/stock/overlay/{code}`)。日 K 經
  `build_period(tagged_fetch, bars_cache, "IX0001", today, "D")`(R2-P0-1 首選)—
  鍵自動成 `IX0001|L`,與 `/api/market/bars/TWSE?tf=D` **真共用**同一槽(同日兩端點
  只發一次 DK 取數);tagged_fetch 即 market bars TWSE 分支同款
  `index.bars_range("D",…)` 包裝(TaggedBarsFetcher,第二元素本來就是 source tag —
  無 status 語意錯接,R2-P1-3 併消)。已完成 bar 規則由 build_overlay 承擔
  (Bar→DailyBar 轉形 date=t[:10])。TC4 down(bars 空)→ 200 全 null;
  **index engine 缺席 → 503 `{detail:{error:"NOT_READY"}}`(沿用 `_index` 既有閘)**。
  驗證:`pytest tests/server/test_index_routes.py -q`(happy / TC4 down 全 null /
  今日 partial 剔除 / cache 命中不重抓 / engine 缺席 503 / 與 stock session 裸
  `IX0001` 槽互不汙染,共 6 條)。
- **SC-6 昨收標籤**:分時圖昨收虛線右端「昨收 <fmt 值>」(fill-ink-dim 小字,halo 描邊);
  與疊線右緣文字同走一套右緣標籤堆疊(決策 6),互不疊字;ref 缺值不畫。
  驗證:`MarketChart.test.tsx` 斷言文字 + 截圖指認。
- **SC-7 域外語意**:CDP/MA 超出 autofit y 域 → 該線不畫線體、右緣掛牌(SC-3);
  **y 域不因疊線 / 均價線改變**(分時走勢縮放不受影響,W-1)。
  驗證(R2-P2-7:不用恆真斷言):幾何測試(域外值 → 無線體 + 掛牌項)+ 元件測試
  「同一 series 下 CDP/MA toggle 開 vs 關,左緣 yTicks 文字與 refY 位置逐字相同」。

驗證窗口:截圖類(SC-1/2/3/6)最佳在盤中或盤後當日(server 持有當日 minutes);
窗口外降級:`TXO_BACKFILL_DATE=<上一交易日>` 起 server 或以元件測試 + 次一交易日盤中
user 過目補截圖。

## 決策記錄

1. [auto-default] 櫃買 CDP/MA toggle:**disabled 反灰 + title**(非隱藏)| reason:
   StockIntradayChart stkfut 態同紀律 — 反灰 + tooltip 講得出為什麼。
2. [auto-default] toggle 鍵:**重用全域 ChartToggles 的 vwap/cdp/ma**(「均價」= vwap 鍵)
   | reason: bb 已是同 store 共用先例;不新增鍵、不 bump TOGGLES_VERSION。
   **aria 口徑採個股版**:`aria-pressed={toggles[k] && available}` +
   `disabled={!available}`(不用 MarketPane.Btn 的 aria-pressed/aria-disabled 並存寫法)
   — MarketPane.test.tsx (f)「選中鈕不得反灰」合約因此天然成立(P1-3)。
3. [amendment 2b] overlay 結果**不另設 cache**:日 bar 已在 bars_cache,
   `build_overlay` 是常數時間。index overlay 不使用 overlay_cache(原 `IX0001|OVL`
   方案作廢);`OverlayCache` 類別與 `app.py:373` 實例是 stock overlay 的既有依賴,
   **保留不動**(R2-P2-9 措辭唯一化)。
4. [amendment 2b] 日 K 取數:**重用 `build_period` + 鍵 `IX0001|L`**(R2-P0-1:
   market bars 日 K 走 build_period、鍵帶 `|L` 後綴、窗 `DAILY_LONG_WINDOW_DAYS=1825`
   — 這才是真共用槽;裸 `IX0001` 是 `/api/stock/bars/IX0001` 的 **stock session**
   `build_daily` 槽,共用它 = 重開 `|M`/`|L` 後綴當初堵住的 W-12 跨 session 汙染洞)。
   窗 5 年,MA20 恆足額(P2-11 併消)。
5. [auto-default] 均價線:**stroke-ink(白)1.2 寬**,綁「均價」toggle | reason: 個股
   VWAP 同外觀。
6. [amendment 2b] 右緣標籤系統(P1-6 / R2-P0-2 / R2-P1-4 / R2-P2-8):指數圖無 R_AXIS
   保留帶(toX 吃滿全寬)→ 不引入內縮(W-1/W-2 不動)。所有右緣文字收進單一 pure
   function `rightEdgeLabels`(落點 `index-chart-svg.ts`),textAnchor="end" 貼
   x=width−2、halo 描邊(stroke-surface + paintOrder)。佈局規則(決定性、逐段可測):
   - **昨收為 fixed**:y 恆 = refY,不參與推擠;其餘標籤對它讓位(R2-P1-4)。
   - 掛牌初始 y:↑ 項(域上方)= bounds.top、↓ 項(域下方)= bounds.bottom;
     域內線標初始 y = 線 y。排序鍵 = 初始 y,同 y 時依 ah→nh→cdp→nl→al→ma5→ma20;
     容量不足丟棄 = 排序末端優先(R2-P2-8)。
   - **三段式堆疊**(R2-P0-2,同個股 `edgePriceLabels` 演算法精神):
     (a) capacity = floor((bottom−top)/10)+1,超量依排序截斷;(b) 由上而下 10px
     最小距下推(對 fixed 昨收讓位);(c) **由下而上回推**處理底部溢出;
     (d) clamp [8, height−14] 後仍相距 <10px 者丟棄。
   - **不重用 `edgePriceLabels`**(它只管 ma5/ma20 且 obstacles 語意不同)。
   測試:「3 項同時貼底 → y 兩兩相距 ≥10 且全在界內」「8 項全塞得下」
   「cdp 與昨收同 y±3px → 昨收 y 不動、cdp 被推開」。
7. [auto-default] 右緣價位文字口徑:**index fmt(/1000,至多 2 位小數)**,不 snap tick、
   不用個股 fmtTickPrice | reason: 指數非可下單價。CDP 線標「<價>*」的 `*` 記號保留
   (與 MA 名稱掛牌區辨,同個股語彙)。
8. [auto-default] MarketChart Props 重塑:**showBb/onToggleBb → toggles/onToggle 整包
   下傳** | reason: 單一 caller;行為不變屬 🔵。
9. **[user 拍板 2026-08-14] 域外疊線 = 右緣掛牌**(域內照畫;域外不畫線、右緣印
   「<名> <價>↑/↓」方向標;y 域不擴)| 三選一(掛牌 / 擴域 / 純 clip)拍板掛牌。
10. [amendment 2b] useIndexOverlay refetch 策略(P1-5 / R2-P1-5):仿 useStockOverlay
    (staleTime Infinity / retry 1 / queryKey 含 localYmd),另加(條件式可直接落碼,
    error 態 `data` 是 undefined,必須查 status 不能查 data):
    `refetchInterval: (q) => (q.state.status === "error" || (q.state.data != null &&
    q.state.data.cdp === null && q.state.data.ma5 === null && q.state.data.ma20 ===
    null)) ? 60_000 : false` — TC4 恢復 / server 起來後 ≤60s 自動補上。
    測試拆兩條:全 null → 60s 後補上;503 error → 60s 後補上。
11. [amendment] 反灰文案唯一化(P2-8):櫃買態 =「櫃買無日 K 資料源」;加權但資料
    null/error =「無日線資料」(沿個股文案)。測試斷言同字面。

## 不能破壞的既有行為白名單

- W-1 分時走勢線本體(accent 色、1.4 寬)與 autofit y 域(±0.3% pad)不變;
  **疊線 / 均價線不得改變 y 域**(SC-7);`toX` 分母(全寬)不變。
- W-2 左緣三格 yTicks(位置 x=2、字級、夾制)不變。
- W-3 昨收虛線本體(全寬、dash "2 3")不變。
- W-4 K 線模式(mode ≠ intraday)整段不變:BB toggle 行為、meta 列、OTC refusal 分支、
  載入/錯誤態文案。
- W-5 期指 pane(series=null)「等待指數資料…」不變;toggle 列只在 series 非 null 的
  分時態出現。
- W-6 `/api/stock/overlay/{code}` 行為與 overlay_cache 語意不變(本輪不再共用該 cache,
  零觸碰)。
- W-7 `IndexEngine.bars_range` 簽名不變;日 K 一律從 index engine session 問(W-12
  紀律),不經 stock session。
- W-8 `useChartToggles` 存檔 schema 不變(不新增鍵、不 bump 版本、不改預設)。
- W-9 StockIntradayChart 疊線外觀零變化;`overlayLines` 簽名放寬(P0-1)對既有 caller
  為 no-op — 既有 StockIntradayChart / stock-intraday-svg 測試全綠 = 機驗。
- W-10 加權 vs 櫃買重疊圖(OverlayCard / buildOverlayGeometry)不動。
- W-11 `/api/index/state`、WS 流、index_engine 推播/回補路徑不動。
- W-12 IntradayChart 的 `role="img"` + `aria-label="${name}分時走勢"` 維持掛在 **svg
  節點**(toggle 列在 svg 外);文案不變(P1-7)。
- W-13 MarketChart 的 `useMarketBars(marketKey, mode, active)` 呼叫位置與 `active`
  轉發不變(intraday 態 enabled=false 的既有輪詢 gate,XR-4)(P1-7)。
- W-14 [R2-P1-6 改寫] overlay 端點對 bars_cache 的存取一律經既有 `build_period`,
  不新增任何 put/get 分支;鍵 = `IX0001|L`(與 market bars 日 K 同槽),與 stock
  session 的裸 `IX0001` 槽、`|M` 槽的隔離語意不變(W-12)。`test_bars.py` 不該紅 =
  這條的機驗。

## Backward compat / migration

- 新 endpoint 純增,無舊 caller;無資料格式變更;無 migration(可逆性 N/A)。
- MarketChart props 變更為前端內部 interface,單一 caller 同 commit 調整。
- `overlayLines` 簽名放寬(結構型 Pick)— 既有 caller 零改動、零行為差異。
- localStorage:零 schema 變更(決策 2)。

## Out of scope

- 櫃買 CDP/MA 的替代日 K 來源(FinMind 等)— 已拍板跳過。
- 期指分時圖疊線(series 恆 null)。
- K 線(day/week/month)模式的 CDP/MA。
- OverlayCard 重疊圖加均價。
- stock overlay 端點對 IX0001 的可達性收緊(`_CODE_RE` 放行為既有行為;本輪已不共用
  overlay_cache,無汙染面)。

## Edge cases

1. TC4 down / bars 空 → endpoint 200 全 null(bars_cache 空態短 TTL 負向快取承接
   don't-cache-empty);前端 `cdpAvailable/maAvailable` 反灰(title「無日線資料」),
   **60s refetch 自動恢復**(決策 10),不需重新整理。
2. index engine 缺席(達錢 4 沒開 / create_app 未給 index_source)→ 503 NOT_READY
   (`_index` 既有閘);前端 isError → 同反灰態(P1-4)。
3. 已完成 bar < 20(理論殘留:上市新指數等)→ ma20 null,ma5/cdp 照回;MA 鈕
   available = ma5≠null 或 ma20≠null(同個股語意)。180 日窗下長假不再觸發。
4. CDP/MA 全域外(常態)→ 線體 0 條、右緣掛牌逐條可見(SC-3/SC-7);toggle 仍亮。
5. ref = null(引擎冷啟)→ 均價線照畫(不依賴 ref);昨收標籤不畫;既有 geometry
   fallback(ref=均值)不動。
6. 換日:前端 queryKey 含 localYmd() 自動失效;後端 bars_cache prune(today)自然換槽。
7. 今日 partial 日 K bar 混入 → build_overlay `date < today` 剔除(既有)。
8. minutes 空(開盤前)→ avgLine 空陣列,不畫線不炸;右緣標籤僅剩昨收(若 ref 有值)。
9. 右緣標籤同 y 相近(cdp ≈ 昨收等)→ `rightEdgeLabels` 10px 最小距下推,不疊字
   (決策 6)。

## Diff 級變更(三類分開)

### 🔵 refactor(先行,行為零差異)

| 檔 | 動什麼 |
|---|---|
| `frontend/src/lib/stock-intraday-svg.ts` | (a) `LEVEL_STROKE` / `LEVEL_FILL` 自 StockIntradayChart 搬入並 export;(b) `overlayLines` 第二參數 `IntradayGeometry` → `Pick<IntradayGeometry, "yDomain" \| "toY">`(函式體只用這兩欄,對既有 caller no-op;P0-1) |
| `frontend/src/components/stock/StockIntradayChart.tsx` | 刪本地兩表改 import;其餘不動 |
| `frontend/src/components/index/MarketChart.tsx` | Props `showBb/onToggleBb` → `toggles: ChartToggles` + `onToggle`;K 線分支行為不變;useMarketBars 呼叫位置 / active 轉發不動(W-13) |
| `frontend/src/components/index/MarketPane.tsx` | 傳法對齊 |

### 🟢 新功能

| 檔 | 動什麼 |
|---|---|
| `copycat/server/app.py` | `GET /api/index/overlay`:`_index(request)`(缺席 503)→ `index.bars_range("D",…)` 包成 TaggedBarsFetcher(同 market bars TWSE 分支樣板)→ `build_period(fetch, bars_cache, "IX0001", today, "D")`(鍵 `IX0001\|L` 共用槽)→ Bar→DailyBar 轉形(date=t[:10]/high=h/low=l/close=c)→ `build_overlay(bars, today)` 直回(無另設 cache) |
| `tests/server/test_index_routes.py` | 新測試 ×6(happy / down 全 null / partial 剔除 / cache 命中不重抓 / engine 缺席 503 / 與 stock 裸 `IX0001` 槽互不汙染) |
| `frontend/src/lib/index-chart-svg.ts` | `IndexGeometry` 擴欄 `avgLine: IndexPt[]` + `toY` 匯出(既有欄不動);新 pure fn `rightEdgeLabels`(昨收+域內疊線+域外掛牌收集、堆疊、clamp;決策 6)與域內/域外分類 helper |
| `frontend/src/lib/index-chart-svg.test.ts` | avgLine 值 / 空態 / toY 一致性 / rightEdgeLabels 堆疊與 clamp / 域外分類 |
| `frontend/src/hooks/useIndexOverlay.ts`(新) | 仿 useStockOverlay + 決策 10 的 refetchInterval |
| `frontend/src/hooks/useIndexOverlay.test.tsx`(新) | enabled 閘 ×2 + 全 null → refetch 恢復 ×1 |
| `frontend/src/components/index/MarketChart.tsx` | IntradayChart:toggle 列(決策 2 aria 口徑;OTC 態 CDP/MA disabled+title)、均價 polyline、`overlayLines`(重用 stock lib)+ 右緣標籤(rightEdgeLabels)、昨收標籤;TWSE 分時才 enabled useIndexOverlay |
| `frontend/src/components/index/MarketChart.test.tsx`(新) | SC-3/4/6/7 元件測試(域內/域外 fixture、disabled+title、昨收、error 態反灰、toggle 開關 y 域不變)+ W-12 機驗(R2-P2-10:`getByRole("img", { name: "加權指數分時走勢" })` 節點 tagName = svg 且 toggle 鈕不在其內) |

### 既有測試判定(逐檔,P1-3)

- `MarketPane.test.tsx`:**不該紅**;其中 (f)「aria-pressed=true 不得 aria-disabled」
  = 決策 2 aria 口徑的機驗,不得為過而改。
- `IndexPage.test.tsx` / `App.test.tsx`:**不該紅**(props 重塑由 🔵 commit 同步;
  App.test 綜合鏈 W-11/W-13 不動)。
- `StockIntradayChart.*` / `stock-intraday-svg` 系:**不該紅** = W-9(搬家 + 簽名放寬)
  機驗。
- `index-chart-svg.test.ts`:既有 assertion 不該紅(擴欄不改舊欄)。
- 後端 `test_index_routes.py` / `test_stock_routes.py` / `test_overlay.py` /
  `test_bars.py`:**不該紅**(端點純增、cache 只讀共用)。
- 若出現上列以外的紅 → 打到不該動的,回 spec 查漏,不改 assertion。

### 新測試清單(對應 SC)

- SC-1/2:`index-chart-svg.test.ts`(avgLine)
- SC-3/4/6:`MarketChart.test.tsx` + `index-chart-svg.test.ts`(rightEdgeLabels 三段式
  三條斷言,見決策 6)
- SC-5:`test_index_routes.py` ×6
- SC-7:幾何測試(域外分類)+ 元件測試(toggle 開關 y 域不變)
- W-12:`MarketChart.test.tsx` aria/svg 機驗
- hook:`useIndexOverlay.test.tsx` ×4(enabled 閘 ×2 / 全 null 60s 恢復 / error 60s 恢復)

## [phase-3 補註 2026-08-14](實作期發現,只追加不重跑 review)

- rightEdgeLabels:capacity 只套在可動標籤,fixed 昨收恆畫(對齊 edgePriceLabels 把
  obstacles 排除在 capacity 外的精神);bounds 退化(top > bottom)→ 回「只剩昨收」。
- 域內/域外分類 helper 定名 `outOfDomainLevels(overlay, g, toggles)`,push 次序與
  overlayLines 逐行對齊(同值不重不漏)。
- avgLine 值保留浮點(不進文字,只供 toY)。
- 既有 yTick `<text>` 加 `data-testid="index-ytick"`(SC-7 比對錨;位置/字級不動,W-2 不變)。
- MarketPane.test.tsx 一處 selector 因 SC-6 新增第二處「昨收 <值>」文字撞
  getMultipleElements,依 frontend-testing skill 收斂 selector scope(語意未放寬),
  記於 green commit body — 既有測試判定表補:此屬 test-infra selector 收斂,非行為紅。

## Baseline

- 後端 pytest:2673 passed(2026-08-14);前端 vitest:112 檔 1868 passed。全綠。

## self_review_head

self_review_head: 1bcc7005522eb2600c40c29e43dabe7655de98bc(2026-08-14 自評收斂:
correctness lens 0 findings;白名單 lens W-1~W-14 全 PASS;P2×3 accepted 已修,
見 code-review-round-1.json)
