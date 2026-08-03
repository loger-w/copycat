# change-spec — stock-ui-round2 批一(圖表)

分支 `mod/stock-ui-round2`。Phase 1 現況表:`current-state.md`(同目錄,reviewer 必讀)。
Round 1 review:`change-spec-review-round-1.json`(19 findings 全數 accepted)。

> **Round 1 修復標記**:凡本輪因 review 而改的段落皆標
> `[amendment 2026-07-29: <finding id> <原因>]`。限縮輪只審這些段落。

## 分流判定

**已成形改法 → grilling 姿態**(命中判準:user 逐項列出 13 個具體改動點,含參考實作來源
`treading-king`、指定設計方法 `fable 5`、指定預設值)。已於 2026-07-29 停下拍板,
user 回答 4 題決策(見下 §0)。項 4 / 項 9 的歧義以 counter-proposal 提出、user 未反對 →
標 `[auto-default]` 推進。

## 0. User 拍板紀錄(2026-07-29)

| 決策 | 選擇 |
|---|---|
| Scope 切分 | **拆兩批,圖表批先**。批一 = 項 1-8、10、11;批二(項 9、12、13)另開一輪 |
| 項 7 兩塊量能 | **留內外盤能量副圖**,砍主圖底部成交量 bar |
| 項 12 自選群組 | 預設群組取代「全部」(**批二**,本輪不做) |
| 項 13 打平價 | 含成本、費率寫進設定(**批二**,本輪不做) |

`[auto-default: 項 4「均線用白色」= VWAP 均價線改白,MA5/MA20 維持黃/紫 | reason: 白色只能給一條線;MA5/MA20 在 K 線也用同一組色票 token,改白會讓兩條 MA 無法區分。已於拍板輪以 counter-proposal 提出,user 未反對]`

`[auto-default: 項 9「跟隨置中隨價位中心變動」判定為描述現況(PriceLadder.tsx:239-246 已實作),批二再確認 | reason: 現行 effect 依 centerPrice 值變化重捲,語意已符合字面描述;無症狀描述無法定位改動點]`

`[auto-default 2026-07-29(amendment R11): 撤回 fable 建議的 onMouseMove → onPointerMove 遷移,hover 與拖曳平移全部維持 mouse 事件 | reason: (1) 專案 frontend-conventions skill 明文「overlay 是 onMouseMove + onClick 才成立,改 pointer event + pointerType 過濾就會破」—— fable 為 fresh context 讀不到,其觸控理由在本專案剛好相反;(2) jsdom 26.x 無 window.PointerEvent,fireEvent.pointerMove 會退回 Event 建構而丟失 clientX/clientY,🟢 區整批新測試寫不出正確的紅]`

---

## 1. 成功條件(可驗收;UI 類寫成畫面可指認表述)

### SC-1|捲軸樣式(項 1)— 驗證項,預期無改動

真實環境開個股頁,DevTools 對「明細清單容器」「閃電梯價格列容器」「自選側欄 ul」三處
取 computed style,`scrollbar-width` 皆為 `thin`、`scrollbar-color` 第一段為
`rgb(85, 97, 122)`(= `--color-ink-dim #55617a`)。**畫面可指認**:三處捲軸為細灰條、
軌道透明(不是 Windows 預設的白底淺灰粗條)。

若三處皆符合 → 本項結案為「上一輪 `mod/stock-ui-fixes` SC-5 已完成」,無 code 改動,
於最終回報附 computed style 證據。若任一處不符 → 補該處樣式。

### SC-2|江波圖漲跌配色與填色(項 2、3、4)

**畫面可指認**:

1. 走勢線在**平盤虛線(昨收)以上的區段為紅色**(`--color-bull #f0524f`)、**以下的區段為綠色**
   (`--color-bear #3ba272`);同一條線跨越平盤時在平盤處變色。
2. 走勢線與平盤虛線之間**有半透明色塊**:線在平盤上 → 紅色塊(不透明度 0.15);線在平盤下
   → 綠色塊(不透明度 0.15)。色塊上緣/下緣貼齊走勢線,另一邊貼齊平盤虛線。
3. **均價(VWAP)線為白色**(`--color-ink #e8edf5`);CDP 五線與 MA 線顏色不變
   (CDP = `ink-dim` 灰虛線、MA5 黃 `#f0b429`、MA20 紫 `#b794f4`)。
4. `meta.ref` 缺(無昨收)時,走勢線退回**單色且無填色**,圖不崩。
   `[amendment 2026-07-29: R18 — fallback 價線維持 accent 桃紅(不是白),否則會與同樣改白的
   VWAP 線同色無法分辨]` **畫面可指認**:此情境下圖上兩條線一桃紅(走勢)一白(均價),可區分。

### SC-3|CDP 預設開啟(項 5)

**畫面可指認**:清除 localStorage `copycat-chart-toggles` 後重載個股頁,江波圖右上
「CDP」鈕呈 accent 高亮外框(`border-accent text-accent`)、`aria-pressed="true"`,
且圖上出現 CDP 疊線與右緣 `AH`/`NH`/`CDP`/`NL`/`AL` 文字 label
`[amendment 2026-07-29: R6 — 補限定條件]`(該檔有日線資料,**且該線價位落在當日漲跌停域內**;
落在漲跌停之外的線不畫 —— 見 §7 Known Risks)。
已存有 toggles 的使用者維持自己的設定(不覆蓋)。

### SC-4|江波圖 Y 區間與刻度(項 6)

**畫面可指認**:

1. 江波圖**最上緣刻度價位 = 漲停價、最下緣 = 跌停價**(與五檔面板顯示的漲跌停同值)。
2. `[amendment 2026-07-29: R14 — 原寫死「11 個」與 B1 的 snapDown 去重規則互斥]`
   左緣自上而下顯示**至多 11 個價位數字**,對應 +10% / +8% / +6% / +4% / +2% / 0(昨收) /
   −2% / −4% / −6% / −8% / −10%;每個價位皆為**合法台股 tick**,且**去重後彼此不重複**
   (低價股 tick 粗時相鄰檔位可能 snap 到同價 → 少於 11 個屬正常)。
   **實測標的 `2330`**(tick 5 元、價位 ≈ 232 元,tick 佔比 0.2%)應為**恰 11 個**。
3. `[amendment 2026-07-29: R14 — 右緣 % 由 snap 後價位反算,非整 2% 階]`
   右緣對應顯示同樣數量的百分比,值為**該刻度價位相對昨收的實際 %**(snap 後可能是
   `+7.9%` 而非 `+8.0%`),正紅負綠、0 灰。
4. 無漲跌停資料的標的(fallback)維持現行對稱 autofit + 3 條刻度,不套 11 條。

### SC-5|單一量能顯示(項 7)

**畫面可指認**:江波圖**主圖區(走勢線所在的框)底部不再有任何柱狀圖**;主圖下方仍有一條
獨立的雙色柱狀副圖(每分鐘一組:左半紅=外盤、右半綠=內盤)。副圖下方的
「累積外盤 / 內盤 / 外盤比 / VWAP」文字列不變。

### SC-6|K 線縮放與指標(項 8)

**畫面可指認**:

1. **模式列**:`江波圖` + `1分K`…`10分K`(10 顆)+ `日K`。分 K 顆數由 `1` 到 `10` 連續。
   **「往前」鈕與「近 N 日」文字消失**。
2. `[amendment-2 2026-07-29: R30 — MAX_VISIBLE=700 使「縮小到全覽 30 日」不可達,原表述會被判 FAIL]`
   **預設載入範圍**:切到任一分 K,不需任何點擊、模式列不再有任何「載入更多」入口,
   且可**以拖曳平移一路走到 30 日前的第一根**。縮放不負責全覽 —— 上限 700 根是 ≥2px 保護
   (SC-6.3),1 分 K × 30 日約 5,900 根本來就無法一屏看完。
3. `[amendment 2026-07-29: R7 — 原「縮放下限 = 全部資料」會退回「蠟燭 <2px 只剩色塊」的已知問題]`
   **滾輪縮放**:游標放在 K 線圖上滾動滾輪 → 蠟燭數量增減(放大時蠟燭變寬、根數變少),
   **游標所指的那根蠟燭在縮放前後保持在同一水平位置**。可視根數夾在
   **[20, min(總根數, 700)]** —— 700 承接舊 `MINUTE_MAX_BARS.m1` 的「每根 ≥2px」保護
   (viewBox 寬 1400 ÷ 700 = 2px/根)。資料少於 700 根時上限 = 全部。
4. **拖曳平移**:在 K 線圖上按住左鍵水平拖曳 → 視窗左右移動,拖到資料端點即停(不空捲)。
5. **MA**:所有 K 線模式(含分 K)都畫 MA5(黃)與 MA20(紫)兩條線。
6. **布林通道**:20 期 ± 2 標準差,上/中/下三條線(中軌 = MA20,與 MA20 同一條),
   上下軌之間有極淡填色;由 **K 線圖頂列右側**的 `BB` toggle 鈕控制(與江波圖 toggle 鈕同
   樣式與同高度 —— 位置必須與 B8(a) 的 chrome 對稱表一致),**預設關**。
   `[amendment-2 2026-07-29: R22 — 原寫「模式列旁」與 B8(a) 表格互斥,且模式列在 figure 之外]`
   `[amendment 2026-07-29: R9]` 開啟時**上下軌完整落在圖框內不被裁切**(y 域需納入 BB 值域)。
7. `[amendment 2026-07-29: R3 — 原量測法結構上做不到,見下]`
   **同尺寸**:量測對象 = `StockChart` 底下的 `figure` 元素之
   `getBoundingClientRect().height`。**在 1440×900 與 1920×1080 兩個視窗尺寸下**,
   `江波圖` 與任一 K 線模式的該值差 **≤ 2px**;切換模式時下半列(五檔 / 明細)不上下跳動。
   達成手段見 §4 B8(chrome 逐項對稱 + viewBox 比例對齊),**不是**單靠調 viewBox 高度。

### SC-7|十字線 + 軸標籤 + 資訊列(項 10、11)

依 fable 設計(`fable-crosshair-design.md`,同目錄)。**畫面可指認**:

1. **垂直線**:江波圖 snap 到 hover 分鐘;K 線 snap 到 hover 蠟燭中心。虛線
   (`stroke-ink-muted`, dash `2 2`, width 0.7)。江波圖的垂直線**延伸到內外盤副圖**。
2. **水平線**:**兩張圖都有**,且**跟隨滑鼠 y**(不再鎖定該分鐘收盤價)。滑鼠上下移動時
   水平線跟著動。
3. **左緣價位標籤**:跟著水平線,顯示滑鼠所在價位(snap 到合法 tick),深色不透明底
   (`fill-bg-deep` + `stroke-line`)+ 白字。貼近圖上下緣時標籤**完整可見不被裁切**。
   `[amendment 2026-07-29: R17]` 滑鼠移到 K 線底部量區時,標籤顯示**夾制在資料值域內的價位**
   (不得出現低於全域最低價或負值)。
4. **右緣 % 標籤**(僅江波圖):同一價位相對昨收的百分比,正紅負綠。
5. **底部時間標籤**(兩圖):垂直線落點下方的時間帶上顯示 `HH:MM`(江波圖)/
   bar 時間(K 線),貼近左右緣時水平夾制不被裁切。
   `[amendment 2026-07-29: R19]` **上下亦不得被裁**:標籤矩形底邊 ≤ viewBox 高度。
6. **資訊列**:圖表**上方**單行,固定高度、欄位順序固定、缺值顯示 `-`。
   - **沒 hover 時顯示即時資料**(江波圖 = 最新分鐘;K 線 = 最後一根),不是空白。
   - hover 時切換為游標所在 bar,且「時間」欄文字轉 accent 色作為態提示。
   - 江波圖欄位:`時間 / 價 / 漲跌% / 量 / 外 o / 內 i`;K 線欄位:`時間 / 開 高 低 收 / 漲跌% / 量`。
   - K 線原本圖下方的 `figcaption` tooltip 移除;江波圖原本 SVG 內浮動小方框移除。
7. **移出圖表**:十字線、三個軸標籤全部消失,資訊列**立即**回到即時態(無動畫)。
8. **江波圖無成交分鐘**:垂直線與資訊列 hover 態不顯示(回即時態),但
   **水平線 + 左價標 + 右 % 標仍照常顯示**(量尺不依賴資料)。

---

## 2. 不能破壞的既有行為白名單

> Phase 5 finder prompt 必附本節行號範圍。

1. **閃電梯武裝紀律全數不動**:換股 / capital WS 斷線 / idle 5 分 / Esc / 連 3 次失敗 /
   離開畫面(unmount)自動解除;未武裝點價不送單;同格 500ms 防抖。
   `RightRail` 閃電 tab **維持條件 render,不得改 `hidden`**(D-13)。本輪不碰交易相關檔案。
2. **江波圖 `minuteOf` 對無資料 bucket 回 `null`**(不 snap 最近分鐘)—— SC-1/R6。
3. **靜態圖層不得因 mousemove 重建**:hover state 不得進入 `ChartStatic` 的 props;
   靜態層(蠟燭 / 量 / 刻度 / 疊線)不得因 mousemove 重建。
   `[amendment 2026-07-29: R8 — 原措辭只涵蓋 ChartStatic,漏掉江波圖副圖]`
   **另涵蓋江波圖的內外盤副圖 energyBars 層**(現況 `StockIntradayChart.tsx:271-278` 是內聯
   JSX、不在任何 memo 內 —— 本輪 B9 讓每次 mousemove 都 setState 後會變成每動一下重建
   最多 540 個 `<rect>`)。
4. **`useStockBars` 的 `tf=D` query key 不含 days**(D-15);`inTradingHours()` 週末 gate
   維持 —— 非交易時段不得出現週期性輪詢。
5. **K 線載入失敗態與「無資料」態必須分得開**:失敗顯示「K 線載入失敗」+ 錯誤碼,
   空 bars 顯示「無 K 線資料」(上一輪 SC-3)。
6. **版面防溢出**:`StockChart` 外層 `shrink-0`;`StockPage` 下半列 `min-h-56` 地板(W-17)。
7. **`select-none`** 在兩張圖的 `figure` 上維持(拖曳不反白)。
8. **全站捲軸樣式**(`index.css` `*` 規則)不得回退;TXO / 期貨 / 指數頁視覺不受影響。
9. **`aggregateBars` 的終點標記語意**(桶界 `(09:00, 09:05]`,跨日不合併)不變。
10. **overlay(CDP/MA)可用性降級**:overlay 未回前不預先反灰;回了但該類 null 或請求失敗
    → 反灰 + disabled + title「無日線資料」。
11. **`buildIntradayGeometry` 的 fallback 對稱域**(無 upper/lower 時以 ref 置中)不變。
12. **江波圖 X 域固定 09:00–13:30**,不因資料範圍縮放。
13. `[amendment 2026-07-29: R11]` **hover 互動維持 mouse 事件模型**(`onMouseMove` /
    `onMouseLeave`),不得改為 pointer 事件 —— 專案 `frontend-conventions` 記載觸控靠 tap 的
    synthetic mousemove 生效,改 pointer 會破。

---

## 3. Backward compat / migration

| 項目 | 策略 |
|---|---|
| `copycat-chart-mode` localStorage | 舊值 `intraday`/`m1`/`m5`/`day` **全部仍合法**(新增 `m2`…`m10`)。`initialMode()` 白名單改為 `^m([1-9]\|10)$` + 三個字面值;無法識別 → `intraday`。**無 migration 需求** |
| `copycat-chart-toggles` localStorage | 新增 `bb`(布林,預設 false);`load()` 的 `{...DEFAULTS, ...saved}` 天然向後相容。`cdp` 預設由 false 改 true **只影響尚未寫入該 key 的使用者**(既有使用者保留自己的選擇 —— 刻意,不做強制覆蓋) |
| `/api/stock/bars` | **完全不改**。2–10 分 K 全走前端 `aggregateBars(data, n)`,`tf` 仍只送 `D`/`1` |
| `DAYS_STEP` / `DAYS_MAX` export | `[amendment 2026-07-29: R2 — 原寫「只被 StockChart.tsx 引用」與 code 不符]` **caller = `components/stock/StockChart.tsx` + `hooks/useStockBars.test.tsx`**(後者 `:7` import 兩者、`:88`/`:90`/`:91`/`:93` 用 `DAYS_STEP`、`:107` 斷言 `DAYS_MAX === 30`)。`DAYS_STEP` 刪除;`DAYS_MAX` 更名 `MINUTE_DAYS = 30`。**兩個 caller 都要同步改**,測試檔改動已列入 §5 |
| `buildCandleGeometry` signature | `[amendment 2026-07-29: R15a — 原承諾指向不存在的改動]` 新增**選用**參數 `extraSeries?: readonly (number \| null)[][]`,用於把 BB 上下軌納入 y 域(R9)。既有兩個呼叫端不傳也能編譯、行為不變 |
| `buildIntradayGeometry` signature | **不變**(`priceAtY` 是往回傳物件加欄位,非改參數) |

**Migration 可逆性**:全部改動只動前端 render 與 localStorage 預設值,**無持久化資料格式變更**、
無後端 schema 變更。回退 = `git revert`,使用者既有 localStorage 值在舊 code 下仍合法
(`m2`…`m10` 會被舊 `initialMode()` 判為不合法 → fallback `intraday`,不崩)。

---

## 4. Diff 級變更(逐檔;三類分開標記)

執行順序 **🔵 → 🔴 → 🟢**。

### 🔵 純重構(測試完全不動,改完該綠的還是綠)

**R1. `frontend/src/components/stock/CandleChart.tsx`** — 修 memo 破洞
- `ma5Line` / `ma20Line` 目前在 render body 內以 `showMa ? maLine(...) : []` 產生
  (`:187-188`),**每次 render 都是新 array identity**(含 `[]` 字面量)→ `ChartStatic`
  的 `memo` 實際上每次都被打穿。現況只在換蠟燭時 setState 所以不痛;SC-7 讓水平線跟滑鼠 y
  後**每個 mousemove 都 re-render**,700 根蠟燭會每次全部重建。
- 改法:`maLine` 提到元件外(純函數,吃 `values` + `g`),`ma5Line`/`ma20Line` 包
  `useMemo(..., [g, ma5, ma20, showMa])`。
- 既有測試:`CandleChart.test.tsx` 全部**不該紅**。

**R2a. `frontend/src/lib/candle.ts`** — 抽 `priceAtY`(K 線)
`[amendment 2026-07-29: R1 — 江波圖的 priceAtY 依賴 B1 改動後的 toY,已移入 🔴 B1;
只有 K 線這份的 toY 結構不變,可留在 🔵]`
- `CandleGeometry` 新增 `priceAtY(ySvg: number): number` —— `toY` 的逆函數:
  `p = hi − ((y − PAD_Y) / usable) × span`。
- `[amendment 2026-07-29: R17]` 三個邊界必須寫死:
  1. **回傳前 clamp 進 `[lo, hi]`**(滑鼠移到底部量區時反演值會低於 `lo`、極端為負,
     未夾制會顯示負價標籤)。fable 原文有「clamp 進 y 域後 snapDown」,初版吸收時掉了。
  2. `span <= 0`(全平盤)→ 回 `hi`。
  3. **空 bars 早退分支**(`candle.ts:135-143`)也要給 `priceAtY: () => 0`,
     否則呼叫即 `undefined is not a function`。
- 新測試(`lib/candle.test.ts`):**round-trip** —— 對域內 5 個價位斷言
  `priceAtY(toY(p))` 與 `p` 差 ≤ 1 tick;量區 y 值夾制到 `lo`;空幾何不崩。
- 純新增 export,**無既有行為改動**;既有測試不該紅。

**R3. `frontend/src/components/stock/StockIntradayChart.tsx`** — 副圖 memo 化
`[amendment 2026-07-29: R8 — 新增]`
- 把 `:271-278` 的內外盤副圖抽成 `const EnergySub = memo(function EnergySub({ bars }) {...})`,
  props 只有 `bars`(= `subGeo.energyBars`);SC-7 要加的 hover 垂直線畫在 `EnergySub`
  **之外**的獨立 `<g>`(同一個 `<svg>` 內),不進 memo props。
- 動機與 R1 相同:B9 之後每個 mousemove 都 setState,540 個 `<rect>` 不可每次重建。
- 既有測試不該紅(DOM 結構不變)。

**R4. `frontend/src/lib/candle.ts` — `buildCandleGeometry` 新增選用參數 `extraSeries`**
`[amendment-2 2026-07-29: R20 — §3 compat 表與 N6 呼叫端都寫了這個參數,卻沒有任何 diff
bullet 擁有 lib/candle.ts 的實作改動,等於沒人做也沒測試鎖]`
- signature:`buildCandleGeometry(bars, size, extraSeries?: readonly (number | null)[][])`。
- 語意:`extraSeries` 非空時,其所有**非 null** 元素一併參與 `hi` / `lo` 計算;
  `yTicks` 仍以最終 `hi` / `lo` 產生。不傳 = 行為與現況完全一致(故歸 🔵)。
- **對齊要求**:呼叫端傳入前必須先 `.slice(start, start + count)` 與 `shown` 對齊 ——
  若照抄現有 MA 的寫法卻漏了 slice,y 域會被視窗外的極值撐開,圖被壓扁**且不會報錯**
  (看起來只是「有點扁」)。此要求同時寫進 N6。
- 新測試(`lib/candle.test.ts`):傳入超出 o/h/l/c 值域的 series → `toY(該值)` 落在
  `[PAD_Y, priceBottom − PAD_Y]` 內;不傳 `extraSeries` 時 `hi`/`lo` 與現況相同。
- 既有測試不該紅。

### 🔴 行為改動(先改測試讓它紅 → 再改實作)

**B1. `stock-intraday-svg.ts` — Y 域改為精確漲跌停 + 11 條刻度 + priceAtY(SC-4)**
- `yTop = upper` / `yBottom = lower`(拿掉 `×1.02` / `×0.98`)。
- 為免走勢線在漲跌停時被圖框裁掉半條 stroke,`toY` 映射值域改為
  `[PAD_Y, height − X_LABEL_H − PAD_Y]`,`PAD_Y = 4`、`X_LABEL_H = 14`(幾何留邊,
  **不是**擴大價格域)。→ `upperY` / `lowerY` 恆非 null(域端點必在域內)。
- `[amendment 2026-07-29: R1 — priceAtY 必須與改動後的 toY 同步,故從 🔵 移到此處]`
  **同一 bullet 內**新增 `priceAtY(ySvg) = yTop − ((ySvg − PAD_Y) / (height − X_LABEL_H − 2×PAD_Y)) × (yTop − yBottom)`,
  回傳前 clamp 進 `[yBottom, yTop]`。`PAD_Y` / `X_LABEL_H` **必須是模組級共用常數**,
  `toY` 與 `priceAtY` 不得各自硬編(這正是初版的錯誤來源:初版沿用改動前的
  `p = yTop − (y/height)×range`,在 y=4 與 y=242 兩端各有 −0.3% / +1.4% 的系統性偏移,
  中間點剛好正確 → 目視最難察覺)。
- `yTicks`:有 upper/lower 且 `ref > 0` 時產生**至多 11 點**,價位 =
  `snapDown(round(ref × (1 + pct/100)))`,pct ∈ `[10, 8, 6, 4, 2, 0, -2, -4, -6, -8, -10]`;
  `pct = ±10` 直接用 `upper` / `lower` 原值、`pct = 0` 用 `ref` 原值。
  以 `priceMilli` **去重**(保留先出現者),避免 React key 重複。
- fallback(無 upper/lower)分支**完全不動**(白名單 11)。
- **該紅的既有測試**:`lib/stock-intraday-svg.test.ts:27`(斷言 `yTop = upper×1.02`)、
  `:60`(yTicks 5 點 → 至多 11 點)。
- **新測試**:round-trip `priceAtY(toY(p)) ≈ p`(域內 5 點,±1 tick);
  y 超界夾制;`[amendment 2026-07-29: R6]` **overlay 值介於 `upper` 與 `upper×1.02` 之間 →
  `overlayLines` 不給該線**(鎖住收窄後的新語意)。
- **不該紅**:`:22` `:47` `:85` `:113` `:157` `:173` `:180`。

**B2. `stock-intraday-svg.ts` + `StockIntradayChart.tsx` — 砍主圖量 bar(SC-5)**
- `IntradayGeometry.volumeBars` 與 `VolumeBar` 型別**刪除**(唯一 consumer 是主圖)。
  `energyBars` 保留。
- `StockIntradayChart.tsx:96-106` 的 `<rect>` 群組刪除;`DIR_CLASS` 常數刪除。
- **該紅**:`lib/stock-intraday-svg.test.ts:97`(volume bar dir)、`:137`(改為只驗 energy);
  `components/stock/StockIntradayChart.test.tsx:122`(量 bar 著色)。

**B3. `stock-intraday-svg.ts` + `StockIntradayChart.tsx` — 價格線漲跌雙色 + 填色(SC-2)**
- geometry 新增 `areaPolygon: string`(封閉多邊形點串:`起點x,refY → 各點 → 終點x,refY`);
  `priceLine` 保留原樣供既有 consumer。
- 元件層:`<defs>` 兩個 clipPath(`above` / `below`,rect 以 `refY` 切),
  polygon ×2(bull/bear,`fillOpacity 0.15`)+ polyline ×2(bull/bear,各套 clipPath)。
- `[amendment 2026-07-29: R5 — 初版理由「主圖與副圖同頁兩個 geometry」不成立(副圖只畫
  energyBars,不產生 clipPath)]` clipPath id 仍需唯一化,**正確理由 = SVG `id` 是 document
  全域**(同頁若出現第二個 chart instance、或 HMR 殘留節點都會撞)。
  `[amendment-2 2026-07-29: R28 — React 19 的 useId 產出 `«r0»` 形態、含非識別字元,放進
  `url(#…)` fragment 參照能否被瀏覽器正確解析未實測;失敗模式是**靜默**的(SVG 規範下無效
  clip-path 參照會讓元素不被繪製 → 雙色兩段同時消失,但 jsdom 測試全綠)]`
  實作以 `useId()` 取唯一種子後**先過濾成 `[A-Za-z0-9]`** 再拼 id:
  `const uid = useId().replace(/[^a-zA-Z0-9]/g, "")` → `${uid}-above` / `${uid}-below`。
  新測試 (b) 追加一條:兩個 id 皆只含 `[A-Za-z0-9_-]`。
- `meta.ref` 缺 → `refY` 無意義 → 退回**單條 `stroke-accent` 桃紅線**、無填色、無 clipPath
  `[amendment 2026-07-29: R18 — 原寫 stroke-ink,會與同樣改白的 VWAP 同色]`。
- **該紅**:無(見 §5 說明 —— `:61` 只斷言 polyline 數量,B3 後仍綠,屬**需改寫**)。
- **新測試**(`[amendment 2026-07-29: R5 — SC-2 原本零測試鎖]`):
  (a) 平盤上下各有一段的資料 → `polyline[class*=stroke-bull]` 與 `[class*=stroke-bear]` 各一、
      `polygon[class*=fill-bull]` / `fill-bear` 各一且 `fill-opacity=0.15`;
  (b) 兩個 `<clipPath>` id 互不相同,且被對應元素以 `clip-path=url(#…)` 正確引用;
  (c) `meta.ref = null` → 只有一條 `stroke-accent` 價線、無 polygon、無 clipPath,
      且 VWAP 仍為 `stroke-ink`(兩線可區分);
  (d) VWAP 線為 `stroke-ink` 且全圖不含 `stroke-profit`。

**B4. `StockIntradayChart.tsx` — VWAP 線改白(SC-2)**
- `stroke-profit` → `stroke-ink`。
- **該紅**:無 —— `[amendment 2026-07-29: R13 — 初版 B4 說 :86 該紅、§5 又列不該紅,自相矛盾;
  實際 `:86` 用 polyline **數量**比對,換 class 不影響]`。改由 B3 的新測試 (d) 鎖住。
- `--color-profit` token **不刪**(TXO 損益圖 `pnl-svg.tsx` 仍用)。

**B5. `hooks/useChartToggles.ts` — CDP 預設開 + 新增 bb + set 改先重讀(SC-3、SC-6)**
- `DEFAULTS = { vwap: true, cdp: true, ma: false, bb: false }`。
- `[amendment-2 2026-07-29: R21 — R16 的 prop 化只做了一半:StockIntradayChart.tsx:135
  仍自呼叫 useChartToggles,與 StockChart 那份**同時存活**。hook 是純 useState,`set` 以自己
  那份 stale `prev` 整包寫回同一個 localStorage key → 後寫的一方會覆蓋對方的變更。
  可重現:江波圖關 CDP → 切 K 線按 BB(StockChart 的 prev 仍是 mount 當下的 cdp:true)
  → 切回江波圖,CDP 自己亮回來]`
  **`set` 改為「先重讀 localStorage 再 merge」**:
  ```ts
  function set(key, value) {
    const next = { ...load(), [key]: value };   // load() 重讀,不用 stale prev
    window.localStorage.setItem(KEY, JSON.stringify(next));
    setToggles(next);
  }
  ```
  **為什麼這樣就夠**(不需改模組級 store,也不需把 toggles 一路 prop drill 進
  StockIntradayChart):`StockChart.tsx:79-99` 是 `mode === "intraday" ? <StockIntradayChart/>
  : <CandleChart/>` —— 兩者**互斥掛載**,江波圖的 toggle 鈕與 K 線的 BB 鈕不可能同時在畫面上。
  跨 instance 需要的只是**持久化正確性**,不是即時同步;切回江波圖時 StockIntradayChart
  重新 mount 即 `load()` 讀到最新值。模組級 store 反而會在測試間留下狀態污染
  (`beforeEach` 的 `removeItem` 清不掉模組變數)。
- **新測試**(`useChartToggles.test.ts`):兩個 instance 交替 `set` 不互相覆蓋 ——
  hookA 設 `cdp:false` → hookB(先於該次 set 就已 mount)設 `bb:true` →
  localStorage 應為 `{vwap:true, cdp:false, ma:false, bb:true}`。
- `[amendment 2026-07-29: R4 — 初版只標 :16 該紅,漏了兩條 toEqual 全等比對]`
  **該紅**:`hooks/useChartToggles.test.ts:16`(預設值)、
  `:21`(`toEqual({vwap,cdp,ma})` → 多一個 `bb` key 必紅,期望值補 `bb:false`)、
  `:34`(`toEqual({vwap:true,cdp:false,ma:false})` → 預設變了必紅)。
  另 `components/stock/StockIntradayChart.test.tsx:93`(beforeEach 清 key → cdp 預設 true
  → 測試裡那次 click 變成**關掉** CDP → `waitFor(getByText("CDP"))` 逾時必紅);
  改法:拆成「預設即有 CDP 疊線」+「click 後疊線消失」兩案例,維持 toggle 行為覆蓋。
- **不該紅**:`useChartToggles.test.ts` 無其他案例。

**B6. `components/stock/StockChart.tsx` — 模式列 1–10 分 K + 移除「往前」(SC-6)**
- `MODES` 產生 12 顆鈕(江波圖 + m1..m10 + 日K)。`initialMode()` 白名單同步放寬。
- `aggregateBars(data, n)` 的 `n` 由模式解析(`m1` → 1,不聚合)。
- **刪除「往前」鈕與「近 N 日」文字**;`days` state 刪除,改常數 `MINUTE_DAYS` 傳給 `useStockBars`。
- `MINUTE_MAX_BARS` / `DAILY_MAX_BARS` 常數刪除(viewport 取代,見 N2/N6)。
- 持有 `useChartToggles`,以 `showBb` **與 `onToggleBb`** 兩個 prop 下傳 `CandleChart`
  (`[amendment 2026-07-29: R16 — useChartToggles 是每 instance 各自 useState,
  兩邊各自呼叫會「按了沒反應」]`
  `[amendment-2 2026-07-29: R22 — BB 鈕落在 CandleChart 頂列(B8(a) chrome 對稱表要求),
  故需要寫回的回呼,原本只定義唯讀的 showBb 是缺件]`)。
- **`<CandleChart key={`${code}-${mode}`} …/>`**
  (`[amendment-2 2026-07-29: R25 — viewport 只在 useState 初值時套 INIT_BARS,無重新初始化
  路徑;換股或換模式(m1→m10 讓 total 由 ~5,900 變 ~590)沿用舊 `start` 會落在任意區間。
  key 強制重掛 = 最小且不可能漏的重置手段]`)
- **該紅**:`StockChart.test.tsx:66`(四顆鈕文字)、`:108`(分K 才有往前鈕)、
  `:126`(往前到上限 disabled)。
- **需改寫(非自動變紅)**:`:119`「日K 無往前鈕」是 `queryByRole(...).toBeNull()`,
  拿掉鈕後仍綠但成為廢測試 → 併入新的模式列測試或刪
  (`[amendment 2026-07-29: R13c]`)。
- **不該紅**:`:72` `:81` `:88` `:98` `:139` `:159` `:176` `:182`。

**B7. `hooks/useStockBars.ts` — ChartMode 擴充 + 常數更名(SC-6)**
`[amendment 2026-07-29: R15b — ChartMode 實際定義在本檔 :10,初版誤掛在 B6/StockChart 名下]`
- `ChartMode` 由 `"intraday" | "m1" | "m5" | "day"` 改為
  `"intraday" | "day" | "m1" | "m2" | ... | "m10"`(union 展開,不用 template literal 型別 —— 在
  `noUncheckedIndexedAccess` 下推導較穩)。
- **已核**:`isDaily`(`mode === "day"`)、`enabled`(`mode !== "intraday"`)、
  `tf`(非日 K 一律 `"1"`)三處判斷對 `m2`…`m10` 皆仍成立,**邏輯不需改**。
- `DAYS_STEP` 刪除;`DAYS_MAX` 更名 `MINUTE_DAYS = 30`。
- **該紅**(`[amendment 2026-07-29: R2 — 初版誤稱本檔無測試]`):
  `hooks/useStockBars.test.tsx:7`(import 兩個已刪/改名的 export → 編譯即紅)、
  `:85`(用 `DAYS_STEP` 當 initialProps 與 URL 斷言 → 改字面值 5 / 10)、
  `:107`(`expect(DAYS_MAX).toBe(30)` → 改 `MINUTE_DAYS`)。
- **不該紅**:`:32` `:41` `:49` `:54` `:59` `:67` `:75` `:97`。

**B8. `CandleChart.tsx` + `StockIntradayChart.tsx` — 兩圖尺寸對齊(SC-6.7)**
`[amendment 2026-07-29: R3 — 初版只對齊 svg 高度,漏算兩個 figure 的非 svg chrome 差約
26px;且用固定 viewBox 高補固定 px 差額只能在單一容器寬成立(H_ideal = 1400×(0.4125+Δ/w),
w=700→625、w=1400→601)]`

分兩步,**先對稱 chrome(讓 Δ=0)再對齊 viewBox 比例**:

**(a) chrome 逐項對稱** —— 兩個 `figure` 內除 svg 外的元素必須結構與高度一一對應:

| 位置 | 江波圖 | K 線 |
|---|---|---|
| 頂列 | `mb-1 flex h-[1.375rem] items-center justify-between` — 左 `ChartReadout`、右 vwap/cdp/ma 鈕 | **同 class** — 左 `ChartReadout`、右 `BB` 鈕(同 `rounded border px-2 py-0.5 text-xs` 樣式) |
| 主 svg | 800×260 | 1400×**578** |
| 副 svg | 800×70,**移除 `mt-1`**(緊貼主圖) | 無 |
| 底列 | `mt-1 flex h-4 ...` figcaption(累積外內盤 / 外盤比 / VWAP) | **新增同 class figcaption** — 視窗摘要「N 根 · 高 X · 低 Y · 期間 ±Z%」 |

高度用 **rem 任意值**(`h-[1.375rem]` / `h-4`)不用 px —— root font-size 縮放(≥1920 112.5%)
兩邊才會等比放大(專案鐵則:新 code 禁 px-literal)。

**(b) viewBox 比例對齊**:江波圖 svg 佔容器寬比 = `(260+70)/800 = 0.4125`;
K 線需 `H/1400 = 0.4125` → `H = 577.5`,取整 **578**。殘差 `(578/1400 − 0.4125)×w`,
w=1400 時 **0.5px**,遠低於 SC-6.7 的 2px 門檻。

- `VOL_RATIO 0.22` 不變。量區高實算 =
  `(height − X_LABEL_H) × VOL_RATIO = (578 − 14) × 0.22 = 124px`
  (`[amendment 2026-07-29: R19b — 初版寫 127,是拿 578×0.22 算的,與 code 的
  `bottom × VOL_RATIO` 不符]`)。
- **該紅**:`lib/candle.test.ts` 中以 `height: 320` 硬編建構 `Size` 的案例(實作時逐一確認)。

**B9. `StockIntradayChart.tsx` — hover 水平線改跟滑鼠 y + 移除 SVG tooltip(SC-7)**
- hover state 由 `hoverMin: number | null` 改
  `hover: { min: number | null; y: number } | null`;`y` 先 `Math.round` 再 setState,
  且以 `setHover(prev => 值相同就回 prev)` 讓 React bail out(防亞像素抖動空 render)。
- `[amendment 2026-07-29: R11 — 撤回 pointer 遷移]` **事件維持 `onMouseMove` / `onMouseLeave`**。
- 水平線 y = 滑鼠 y;垂直線維持 snap 分鐘。
- 移除 122×34 SVG tooltip(`:257-266`),內容移入資訊列(N5)。
- 新增 hover 分鐘收盤價的 `<circle r=2.5 className="fill-ink">`。
- **該紅**:`StockIntradayChart.test.tsx:129`(hover 十字與 tooltip)、
  `:140`(無資料分鐘 → 改為:垂直線與資訊列 hover 態不顯示,水平線與價位標籤仍在)。

**B10. `CandleChart.tsx` — 移除 figcaption tooltip(SC-7)**
- `data-testid="candle-tooltip"` 的 `<figcaption>` 移除,內容移入資訊列(N6)。
  底部改放 B8(a) 要求的視窗摘要 figcaption。
- **該紅**:`CandleChart.test.tsx:69`。

### 🟢 新功能(先寫紅測試 → 實作 → 綠)

**N1. `frontend/src/lib/bollinger.ts`(新檔)**
- `bollinger(bars, n = 20, k = 2): { mid: number; upper: number; lower: number }[]`,
  元素可為 null(前 n−1 根)。毫元整數運算;σ 用 `Math.round(Math.sqrt(variance))`。
- 新測試:足量資料三線齊、不足 n 根全 null、全平盤 σ=0 三線重合、空輸入不崩、
  `[amendment 2026-07-29: R9]` **上軌 > 全域最高價的案例**(供 N6 的 y 域納入驗證)。

**N2. `frontend/src/lib/candle-viewport.ts`(新檔)— 縮放/平移純函數**
- `type Viewport = { start: number; count: number }`。
- `zoomAt(vp, total, factor, anchorRatio): Viewport` —— 保證錨點那根 index 不變。
- `panBy(vp, total, deltaBars): Viewport` —— 夾制在 `[0, total)`。
- `[amendment 2026-07-29: R7]` `MIN_BARS = 20`、**`MAX_VISIBLE = 700`**。
  700 = viewBox 寬 1400 ÷ 2px,承接舊 `MINUTE_MAX_BARS.m1` 的保護(該常數註解明載
  「超過 ~700 根寬度就被壓到 <2px」)。
  `[amendment-2 2026-07-29: R31 — 原寫「夾在 [MIN_BARS, min(total, MAX_VISIBLE)]」在
  total < 20 時區間為空(下界 20 > 上界 total),行為未定義。而小資料量正是既有測試的常態:
  CandleChart.test.tsx 的 BARS 只有 3 根、`:60` 用 8 根、StockChart.test.tsx 的 BARS 只有
  2 根 —— 全是 §5 標「不該紅」的案例,夾制次序寫錯會直接波及]`
  **夾制次序寫死**:
  ```ts
  let c = Math.max(1, Math.min(count, total, MAX_VISIBLE));
  if (total >= MIN_BARS) c = Math.max(c, MIN_BARS);   // 資料本來就不足 20 根 → 不強拉
  const start = Math.max(0, Math.min(startWanted, total - c));
  ```
- 新測試補一條:`total < MIN_BARS` 時 `count === total` 且 `start === 0`。
- `[amendment 2026-07-29: R10 — 初版「total 變動時保持貼右緣」會讓盤中平移最多 60 秒後
  被 refetchInterval 拉回(useStockBars.ts:61 交易時段每 60s 重取)]`
  `onTotalChange(vp, prevTotal, nextTotal): Viewport` ——
  **僅當改動前已貼右緣**(`vp.start + vp.count >= prevTotal`)才跟進新資料延伸;
  否則保持 `start` 不動(以 index 錨定)。
  `[amendment-2 2026-07-29: R25 — 界線必須寫死]` **`onTotalChange` 只處理「同一 code + mode
  的序列延伸」**(= 60s refetch 追加新 bar)。換股與換模式**不走這條路徑**,由 N6 的
  `key={code}-{mode}` 強制重掛回到 `INIT_BARS` 初始式 —— 否則使用者平移過之後切 10 分 K,
  `start` 仍是以 1 分 bar 計的舊 index,畫面會落在一段任意區間。
- 新測試:錨點守恆、`MIN_BARS`/`MAX_VISIBLE` 夾制、端點不空捲、
  `onTotalChange` **兩案例**(貼右緣 → 跟進;已平移 → 不動)。

**N3. `frontend/src/components/chart/ChartReadout.tsx`(新檔)— 共用資訊列**
- Props:`fields: { label: string; value: string; tone?: "bull" | "bear" | "muted" }[]`
  + `hovering: boolean`。純 presentational,無資料依賴。
- 外層 class 由呼叫端給(B8(a) 的頂列容器持有高度),元件本身只排欄位。
- `hovering` 時第一欄套 `text-accent`,否則 `text-ink-muted`。
- 新測試:欄位順序與數量、tone 對應 class、hovering 態切換 class。

**N4. `frontend/src/lib/chart-crosshair.ts`(新檔)— 夾制 helper**
- `clampTagY(ySvg, boxH, plotBottom)` = `clamp(ySvg − boxH/2, 0, max(0, plotBottom − boxH))`
- `clampTagX(xSvg, boxW, width)` = `clamp(xSvg − boxW/2, 0, max(0, width − boxW))`
- 新測試:中段不動、四邊夾制、`plotBottom < boxH` 的退化不回負值。

**N5. `StockIntradayChart.tsx` — 左價標 / 右 % 標 / 底部時間標 / 資訊列**
- 尺寸(viewBox 800×260):左標 `w=46 h=14 x=0`;右標 `w=46 h=14 x=754`,`textAnchor=end x=796`;
  底部時間標 `w=34 h=13`,`y = 247`。背景 `fill-bg-deep` + `stroke-line`(**不透明**)。
  `[amendment 2026-07-29: R19a → amendment-2 2026-07-29: R29 — 原註「綁定 height − X_LABEL_H」
  算出 260 − 14 = 246 ≠ 247,與寫死的數字打架]`
  **統一公式 = `y = height − boxH`**(標籤底邊恰貼 viewBox 底):江波圖 `260 − 13 = 247`、
  K 線 `578 − 14 = 564`。前提 `boxH ≤ X_LABEL_H`,標籤才不會蓋到繪圖區。
- 價位 = `snapDown(g.priceAtY(ySvg))`(B1);% = `(p − ref) / ref × 100`,`ref` 缺則不畫右標。
- 垂直線延伸進內外盤副圖(畫在 `EnergySub` memo 之外的獨立 `<g>`,見 R3)。
- 資訊列走 `ChartReadout`,掛在頂列左半。欄位:`時間 / 價 / 漲跌% / 量 / 外 / 內`;
  無 hover 時取最新分鐘 agg。
- 新測試:左價標隨滑鼠 y 變動且 snap tick、右 % 標正負著色、無 ref 時右標不出現、
  資訊列預設即時態、hover 態切換、無資料分鐘的分解退化(水平線在、垂直線不在)。

**N6. `CandleChart.tsx` — 水平線 / 左價標 / 底部時間標 / 資訊列 / 縮放平移 / BB**
- 尺寸(viewBox 1400×578):左標 `w=56 h=16 x=0`;底部時間標 `w=48 h=14`,
  `y = height − boxH = 578 − 14 = 564`(`[amendment 2026-07-29: R19a — fable 原稿
  y=307+14=321 > 320 的 off-by-one 被初版照抄;amendment-2 R29 統一公式]`)。
- `[amendment 2026-07-29: R7]` **初始 viewport** =
  `{ start: max(0, total − INIT_BARS), count: min(total, INIT_BARS) }`,
  `INIT_BARS` = 日 K **120**(沿用舊 `DAILY_MAX_BARS`)/ 分 K **240**
  (≈ 1 個交易日的 1 分 K 全長,切進去先看今天,再往左縮放看更早)。
- **滾輪縮放**:以 ref 掛**原生** `wheel` listener 並 `{ passive: false }` —— React 的
  `onWheel` 綁在 root 且為 passive,`preventDefault()` 無效會讓頁面跟著捲。
- **拖曳平移**:`onMouseDown` 記起點 → `window` 上掛 `mousemove` / `mouseup`(拖出圖外仍跟手),
  換算 deltaBars;拖曳中不更新 hover(避免十字線抖動)。
  `[amendment 2026-07-29: R11]` 全程 mouse 事件,不用 pointer capture。
- `bars` identity 變更時走 `onTotalChange`(N2)。
- `[amendment 2026-07-29: R9]` `buildCandleGeometry(shown, DIMS, extraSeries)` ——
  BB 開啟時把上下軌陣列傳入,y 域一併納入,上下軌才不會被裁到圖外(實作條目見 🔵 R4)。
  `[amendment-2 2026-07-29: R20]` **傳入前必須 `.slice(start, start + count)` 與 `shown` 對齊**
  (照抄現有 MA 的 `movingAverage(bars,n).slice(start)` 寫法即可;漏了 slice 會讓 y 域被
  視窗外極值撐開、圖被壓扁且不報錯)。
- `[amendment 2026-07-29: R16]` `showBb` 由 **prop** 傳入(`StockChart` 持有 hook),
  `CandleChart` 不自呼叫 `useChartToggles`。
  `[amendment-2 2026-07-29: R22]` BB 鈕本身畫在 `CandleChart` **頂列右側**(B8(a) chrome
  對稱表),因此另需 **`onToggleBb: (v: boolean) => void`** prop 寫回。
- `[amendment-2 2026-07-29: R25]` viewport 的重置由 `StockChart` 給的
  `key={`${code}-${mode}`}` 負責(整個元件重掛)—— 元件內不另寫 reset effect,
  避免兩套重置路徑互相打架。
- `maxBars` prop 刪除(viewport 取代);`showMa` prop 刪除(恆真)。
  **屬型別破壞**:凡傳這兩個 prop 的呼叫端與測試都要同步改
  (`[amendment 2026-07-29: R12]`)。
- 新測試:滾輪縮放改變蠟燭數、錨點守恆、拖曳平移、端點停止、
  資訊列即時/hover 態、左價標夾制(含量區不出負價)、MA 在分 K 也畫、
  BB prop 開關、BB 上軌超出 o/h/l/c 值域時仍落在圖框內。

**N7. `StockChart.tsx` — BB 狀態持有者**
`[amendment-2 2026-07-29: R22 — 原條目把鈕放在「StockChart 的模式列」,與 B8(a) 的
chrome 對稱表(鈕在 K 線 figure 頂列)互斥。拍板:**鈕畫在 CandleChart 頂列**,
StockChart 只當狀態持有者]`
- `StockChart` 呼叫 `useChartToggles()`,把 `bb` 以 `showBb` + `onToggleBb` 兩個 prop
  下傳 `CandleChart`;**鈕的 DOM 在 `CandleChart` 內**(N6),不在模式列。
- 模式列本身不新增任何按鈕(維持 12 顆模式鈕)。

---

## 5. 測試清單彙總

`[amendment 2026-07-29: R2/R4/R5/R12/R13 — 整表重寫;新增 useStockBars.test.tsx 一列,
修正 5 處標錯,並區分「該紅(自動變紅)」與「需改寫(不會自動紅但非改不可)」]`

`[amendment-2 2026-07-29: R23/R24/R26/R27 — 整表第二次修正:補回漏列的 `:69`、
`:78` 方向標反、三處殘留的反向標記、`lib/candle.test.ts` 整列事實錯誤]`

| 檔案 | 該紅(自動變紅) | 需改寫(不自動紅) | 不該紅 |
|---|---|---|---|
| `lib/stock-intraday-svg.test.ts` | `:27` `:60`(B1)、`:97` `:137`(B2) | — | `:22` `:47` `:85` `:113` `:157` `:173` `:180` |
| `components/stock/StockIntradayChart.test.tsx` | `:78`(B5 — `:82` 斷言 CDP `aria-pressed==="false"` 且 `:20` beforeEach 清 key → 走 DEFAULTS,必紅)、`:93`(B5,click 變成關 CDP)、`:122`(B2)、`:129`(B9) | `:61`(B3/B4 後仍綠 —— 只驗 polyline 數量;改為斷言雙色 polyline + polygon)、`:114`(11 刻度下 `2090`/`2550`/`+9.9%`/`0%` **仍全部成立**;改為斷言 11 條與 ±2% 價位)、`:140`(無資料分鐘既不畫垂直線也不畫時間標、資訊列回即時態 → `queryByText(/11:1/)` 仍 null 保持綠;改為**正向**斷言 SC-7.8:水平線 + 左價標在、垂直線與 hover 資訊列不在) | `:69` `:86` `:101` `:148` |
| `hooks/useChartToggles.test.ts` | `:16` `:21` `:34`(B5) | — | — |
| `hooks/useStockBars.test.tsx` | `:7` import(編譯即紅)、`:85`(DAYS_STEP)、`:107`(DAYS_MAX)(B7) | — | `:32` `:41` `:49` `:54` `:59` `:67` `:75` `:97` |
| `components/stock/StockChart.test.tsx` | `:108` `:126`(B6,「往前」鈕消失 → `getByRole` 拋錯) | `:66`(RTL string name 是**全等**比對,新增 m2–m10 後四個 label 仍各自唯一命中 → 保持綠;改為斷言 12 顆鈕與 `1分K`…`10分K` 連續)、`:119`(`queryByRole(...).toBeNull()`,拿掉鈕後仍綠成廢測試 → 併入模式列測試或刪) | `:72` `:81` `:88` `:98` `:139` `:159` `:176` `:182` |
| `components/stock/CandleChart.test.tsx` | `:38`(`:42` 傳 `maxBars={120}` → prop 刪除即型別破壞)、`:46` `:60`(`:50`/`:64` 傳 `showMa` → 同上)、`:69`(B10 移除 `data-testid="candle-tooltip"` → `getByTestId` 拋錯) | `:55`(**`:56` 根本沒傳 `showMa`** → 刪 prop 不產生型別錯誤;`showMa` 恆真後 BARS 只 3 根湊不出 MA5,執行期仍綠 → 語意作廢,改為給 ≥5 根資料並斷言「MA 恆畫」) | `:21` `:26` `:31` `:79` `:85` |
| `lib/candle.test.ts` | **—**(B8 只改 `CandleChart.tsx:14` 的 `DIMS` 常數;`lib/candle.ts` 的 `X_LABEL_H`/`PAD_Y`/`VOL_RATIO` 皆不動,而 `buildCandleGeometry` 的 `size` 由**測試自帶**(`:158` 用 1400×320、`:86-155` 用 400×200)→ 全部維持綠) | — | **全檔既有案例** |

> `[amendment-2 2026-07-29: R26/R27 — 上一版把 `:66` `:55` 與整個 `lib/candle.test.ts`
> 標成該紅,實際都不會自動變紅;「實作時逐一確認」等於把 spec 該定的紅綠合約丟給實作階段]`

新測試檔:`lib/bollinger.test.ts`、`lib/candle-viewport.test.ts`、
`lib/chart-crosshair.test.ts`、`components/chart/ChartReadout.test.tsx`。

既有檔內新增的案例:
- `lib/stock-intraday-svg.test.ts`:`priceAtY` round-trip / 夾制、overlay 落在
  `upper`~`upper×1.02` 之間不給線(B1)
- `lib/candle.test.ts`:`priceAtY` round-trip / 量區夾制 / 空幾何(R2a)、
  `extraSeries` 撐開 y 域(R4,`[amendment-2 2026-07-29: R20]`)
- `hooks/useChartToggles.test.ts`:兩 instance 交替 `set` 不互相覆蓋(B5)
- `components/stock/StockIntradayChart.test.tsx`:SC-2 四條鎖(B3)+ 軸標籤/資訊列(N5)
- `components/stock/CandleChart.test.tsx`:縮放/平移/資訊列/BB(N6)

新測試檔:`lib/bollinger.test.ts`、`lib/candle-viewport.test.ts`、
`lib/chart-crosshair.test.ts`、`components/chart/ChartReadout.test.tsx`。

---

## 6. Out of scope(本輪明確不做)

- **項 9**(閃電梯跟隨置中)、**項 12**(自選側欄重做 + 後端 `watchlist_quote` 加 `name`)、
  **項 13**(閃電梯部位/未實現損益/打平價 + 費率設定)—— 批二。
- `docs/next-time.md:85` 記載的 `_SPOT_PREFIX` 既有 bug(個股期 tick 汙染台指現價)—— 另開 `/bug`。
- `docs/next-time.md:93` 「全部群組顯示尚無自選」既有 bug —— 併入批二項 12。
- 後端 `/api/stock/bars` 的 `tf` 值域擴充、inflight dedup、國定假日 gate。
- 觸控手勢工程(pinch zoom);**且不做 pointer 事件遷移**(見白名單 13)。
- 江波圖的縮放/平移(江波圖 X 域固定 09:00–13:30 是白名單 12)。

---

## 7. Known Risks

- **分 K 預設載 30 日的首載延遲**:`docs/next-time.md:82` 實測 `tf=1&days=5`(810 根 /
  3 交易日)耗時 2.1s;30 日 ≈ 22 交易日 ≈ 5,900 根,線性外推約 **10–15s**。歷史日走後端
  永久 memo,**只有每檔第一次**要付。緩解:載入態文案不變;若真環境實測 >20s,退回預設
  10 日 + 縮放到左端自動續載(本輪不做,記 `docs/next-time.md`)。
  `[auto-default: 預設 30 日一次載完 | reason: user 明確要求「不需要再點往前才能看 30 日」;
  漸進續載是更大的工程且會引入捲動位置維持問題]`
- `[amendment 2026-07-29: R6]` **CDP / MA 疊線在漲跌停域外會不畫**:yDomain 由
  `[lower×0.98, upper×1.02]` 收成 `[lower, upper]`,落在那 2% 夾層的 AH / NH / AL / NL 或
  跳空後的 MA 會從「有畫」變成「不畫」,且 UI 無提示。**接受此行為**,理由:超出漲跌停的
  價位當日不可能成交,畫出來是雜訊。已由 B1 新測試鎖住語意,SC-3 表述同步限定。
- `[amendment 2026-07-29: R7]` **zoom out 到 700 根時的 DOM 量與 pan 成本**:700 根 ×
  (影線 + 實體 + 量 bar) ≈ 2,100 個節點,拖曳平移每次 `mousemove` 都會重算
  `buildCandleGeometry` 並 diff 整個 `ChartStatic`。緩解:`MAX_VISIBLE = 700` 上限 +
  R1/R3 的 memo 修復;若真環境拖曳掉幀,改 rAF 節流 pan(本輪不做,記 `docs/next-time.md`)。
- `[amendment-2 2026-07-29: R30]` **走到 30 日前的第一根需要多次拖曳**:1 分 K × 30 日
  ≈ 5,900 根、最大視窗 700 根、`INIT_BARS` 240 → 從右端拖到最左端約需 8 次滿寬拖曳
  (視窗 700 時)。§7 首載的 10–15s 成本是為這 30 日資料付的,但取用路徑偏長。
  **本輪不加捷徑**(雙擊回最右 / Home 跳最左屬新互動,scope 紀律不順手加)——
  記入 `docs/next-time.md`,真用起來嫌煩再開。
- **11 條 Y 刻度在 260px 高度下間距約 23px**,字級 0.625rem(10px)。若真環境視覺過密,
  降為隱藏 ±6(user 明確點名 ±2/±4/±6/±8,故預設全留)。
- **`upper`/`lower` 缺值的標的**(新上市前五日 / 無漲跌幅)走 fallback 域,SC-4 的 11 條刻度
  不適用 —— 刻意(白名單 11)。
- **K 線 viewBox 578 高**在窄視窗(容器寬 < 600px)下渲染高 ≈ 248px,蠟燭會偏扁。
  現況 320 高在窄視窗下更扁,**不是回歸**。專案主場景是 1440+ 桌面。

---

self_review_head: 3e891f17961c96f137a1f3dabf2a6e322661d346
