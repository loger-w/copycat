# R1 前端圖表標籤/版面批 change-spec(branch `mod/chart-label-batch`)

來源:`docs/superpowers/specs/2026-08-24-do-batch-rounds.md` §R1 九條
(N006 / N045 / N007 / N044 / N009 / N026 / N027 / N023 / N062)。

行為改動 🔴 與純測試 🟢 分開 commit;每條行為改動先有紅測試或**事前標記該變**的既有斷言。
a11y 類 finding 一律不做(user 2026-08-24 拍板)。

---

## 共用新設施(lib/stock-intraday-svg.ts,N006/N045/N007/N044 共用)

| 名稱 | 語意 |
|---|---|
| `labelWidth(text)` | 0.5625rem 字級的文字寬估值:半形 5.7px / 全形 9px。**係數由既有兩顆常數反推**:「1005.0」6 字 → 34.2 ≈ `EDGE_LABEL_W`(34)、「1405.67」7 字 → 39.9 ≈ `VWAP_LABEL_W`(40)。 |
| `spansOverlap(a, b)` | 兩段文字的 x 區間相交判定(端點相接不算)。走廊避讓的水平判準,與既有 `maObstacles` 的「x 區間碰到走廊才算 obstacle」同一把尺。 |
| `yieldToFixed(y, fixed, gap, bounds)` | **可動標籤讓開不可動鄰居**的唯一機制(N007 / N044 同一套):與任一 fixed 中心距 < gap 時往遠離該鄰居的方向推到剛好 gap,掃到不再相撞為止;**沒讓位就完全不動**(不無故 clamp),讓位後才 clamp 進 bounds。 |
| `vwapLabelBox(endX, text, w)` | VWAP 就地標籤的水平定位 + 寬度估值(見 N006)。 |
| `VWAP_LABEL_W` | 由 `StockIntradayChart.tsx` **移到 lib**(`vwapLabelBox` 需要它,且它與 `R_AXIS_W` 是同一組右緣幾何)。值不變 = 40。 |

---

## N006 + N045 — VWAP 標籤口徑與寬度(🔴)

**現況**:`ChartStatic` 的 VWAP 就地標籤文字硬編 `fmt(vwapMilli)`、寬度硬編常數
`VWAP_LABEL_W = 40`。index / futures 態全圖走 `fmtIndexPts`(左緣刻度 / CDP / MA / hover)
只有這顆走 `fmt` → (a) 同圖兩套口徑(加權印 `24283.54`、刻度印 `24284`;期指 `23006.15`);
(b) 8 字實寬 ≈45.6px > 40 → 盤末 `Math.min(…, w − R_AXIS_W − 40)` 內縮不足,字尾溢進右緣
疊線標籤帶,且 MA 避讓的 obstacle 判定少算 ≈5px 的窄帶。

**改動**:
1. `ChartStatic` 新增 prop `vwapText`(預設 `fmt` = stock 態逐值不變),元件傳
   `ptsPrice ? fmtIndexPts : fmt` —— 與 `priceText` **分開**:stock 態不可換成
   `fmtTickPrice`(VWAP 是統計量不是可掛單價,review F3 不推翻)。
2. 寬度改走 `vwapLabelBox` = `max(VWAP_LABEL_W, labelWidth(text))`。下限 40 保住 stock 態
   短字的既有位置(既有斷言 `x + 40 ≤ 800 − R_AXIS_W` 不動),實測字寬只在長字時接手。

**測試**:`stock-intraday-svg.test.ts` 對 `labelWidth` / `vwapLabelBox` 的字面量案
(「24283.54」45.6、期指 8 字「23006.15」、短字回下限 40);元件層 index 態加權
`24283.54` → 標籤文字 `24284` 且 `x + 寬 ≤ 800 − R_AXIS_W`;futures 態 `23006.15` → `23006`。

## N007 — VWAP 就地標籤 × 極值標記文字避讓(🔴)

**現況**:兩者都畫在繪圖區內、都可能落在盤末右緣區,彼此完全不避讓。
極值文字的預設側(日高在上 / 日低在下)與 VWAP 末點的中心距恰好 = `EDGE_LABEL_H`,
**但翻面態**(極值貼圖框 → `markLabelY` 翻到標記另一側)會把文字翻到 VWAP 那一側,
1 < Δ < 21 都疊 —— 盤末摸到接近漲停的日高 + VWAP 略低於它就是這條路徑。

**改動(最小侵入)**:VWAP 標籤**不可動**(它的 y = 線末點在哪 = 資訊),**極值文字讓位** ——
標記圓不動(承載「哪一分鐘 / 什麼價位」),只把文字沿原方向推開到中心距 `EDGE_LABEL_H`。
判準與既有 `maObstacles` 同款:x 區間相交才算(`labelWidth` 算實際字寬),左半場的極值不無故位移。
極值文字 y 是 baseline、VWAP 是中心(`dy=0.35em`)→ 一律先正規化成中心再比,
沿用既有 `BASELINE_TO_CENTER`。

**測試**:日高貼域頂(觸發 `markLabelY` 翻面)+ VWAP 落在翻面後的位置附近 + 兩者都在右緣區
→ 修前 Δ ≈ 3.2px(紅),修後 ≥ 10;對照組:同價位但日高在左半場 → 文字 y 逐值不變。

## N044 — hlines label 與 VWAP 末點標籤同走廊避讓(🔴)

**現況**:`hlines`(持倉均價 / OI 撐壓,futures 態)的 label 畫在 `x = w − R_AXIS_W − 2`
(anchor=end)、y = 線 y − 3,與 VWAP 就地標籤在盤末的 x 區間完全重疊時兩層 halo 互蓋。

**改動**:**同 N007 一套機制**(`yieldToFixed`,不另做第二套):hline label 是「這條線在哪」的
冗餘訊息(線體照畫)→ 它讓位;fixed 集合同樣只在 x 區間相交時納入 VWAP。
label 文字含中文 → `labelWidth` 的全形分支負責算對區間。

**測試**:futures 態 hline 價位貼近 VWAP 末點 → label y 與 VWAP y 中心距 ≥ `EDGE_LABEL_H`
(修前 = 0.x px);對照組:hline 遠離 VWAP → y 仍為 `線 y − 3` 逐值不變。

## N009 — 走廊 A 超容 clamp 全堆界邊 → 界內等距壓縮(🔴)

**現況**:`layoutEdgeLabels(dropOverflow:false)` 裝不下時,最後一道 clamp 把上緣好幾顆壓成
**完全同一個 y**(既有測試字面量 `[4,4,4,4,10,20,30]`)—— 同 y 的那幾顆等於只看得到最後畫的
那一顆,與 D6「寧可擠也不丟資訊」的立場矛盾。4×4 圖牆(capacity 6 / n 7)真的踩得到。

**改動**:排序後若 `n > capacity`,改為界內等距:`y_i = top + i × (bottom − top)/(n − 1)`,
直接回傳(裝不下時對 obstacles 讓位無解,不再跑兩輪 sweep)。`dropOverflow:true`(走廊 B)不變。

**測試**:既有 `bandLabels` 容量不足案的字面量 `[4,4,4,4,10,20,30]` **屬事前標為該變**,
更新為 `[4, 8.33, 12.67, 17, 21.33, 25.67, 30]` 並補「相鄰間距全等」與「y 兩兩相異」斷言。

## N026 — CandleChart figcaption 窄容器折行溢出(🔴)

**現況**:`<figcaption className="mt-1 flex h-4 …">` 四段(`120 根 / 高 / 低 / 期間`)在
< ~320px 寬折成兩行,而 `h-4`(16px)是固定高 → 第二行直接溢出壓到下方(高度必須固定:
與江波圖 figcaption 逐項對稱才有「切模式不跳高」)。

**改動**:高度不動(截字派):figcaption 加 `overflow-hidden whitespace-nowrap`,四段各加
`min-w-0 truncate` → 恆一行、窄容器逐段省略號,不跑版也不整段消失。

**測試**:class 鎖(jsdom 不套 CSS,只防漏寫)。

## N027 — 矮圖 `Y_TICKS = 5` 降階(🔴)

**現況**:`lib/candle.ts` 的 `Y_TICKS` 恆 5。1:1 viewBox 後 96px 高的 K 線圖可用高
`(96 − 14) × (1 − 0.22) − 12 ≈ 52px`,5 條刻度間距 ~13px 而字高 10px,幾乎相接。

**改動**:`size.height < Y_TICKS_MIN_H(140)` → 降為 3 條。門檻的由來:h=140 時可用高 86.3px、
5 條間距 21.6px ≈ 2× 字高,再矮就開始相接(常數帶註解,不是魔數)。既有測試用的 200 / 320
兩個高度都在門檻之上 → 逐值不變。

**測試**:同一組 bars 在 height 96 → ≤ 3 條且相鄰間距 ≥ 2× 字高;height 200 → 5 條(對照)。

## N023 — `outOfDomainLevels` 端點案(🟢 純測試)

**現況**:`lib/index-chart-svg.ts:48` 用嚴格不等式 → `p === yTop` / `p === yBottom` 算**域內**
(不掛牌),而 `overlayLines` 的域判定是閉區間(端點會畫線)—— 兩者互補正確,但無 assertion。

**改動**:零 code 改動,補 characterization:端點值不進 `outOfDomainLevels`、**且**進
`overlayLines`(互補性一起釘,改成 `>=` 就會兩邊都有 = 紅)。

## N062 — 兩欄態矮視窗家數帶 section 溢出(🔴)

**現況**:`IndexPage` 左欄兩欄態設 `--idx-adl-min: 10rem`(騰落線 wrapper 的 min-height 地板)。
家數帶兩列固定 chrome ≈ 148px + gap 8 + 地板 160 = 316px > section 分到的 5/11
(2026-08-20 機械實測:1536×700 主 grid 622/676 出 54px 捲軸、溢出源 section 262/316)。

**改動**:地板 `10rem → 6rem`(= wrapper 自身 `h-24` 的 96px = 單欄態高度)。
它是**地板不是指定高**:1536×864 實測 section 分到 337px、wrapper 實際 181px 遠高於任一地板
→ 正常視窗逐值不變,只有被壓到極限時才退回單欄態的 96px 而不再溢出。

**測試**:`IndexPage.test.tsx` 的 class 鎖字面量 `--idx-adl-min:10rem` **事前標為該變** → `6rem`。
CSS 層(真的不捲了)jsdom 量不到,證據只能靠上述機械實測的算術對照。

---

## 白名單(本輪**不動**)

- 極值標記文字在 index 態仍走 `fmt`(`24283.54` 8 字),與同圖 `fmtIndexPts` 兩套口徑 ——
  與 N006 同型但**不在 R1 清單**;它畫在繪圖區內、不參與右緣寬度 clamp,溢出風險不同。留 next-time。
- `maObstacles` 的極值半寬由 `EDGE_LABEL_W / 2`(17,固定上界)改為 `labelWidth(text) / 2`
  (實際字寬)—— 這是 N007 需要「同一把尺」的直接後果(同一段文字不能有兩個寬度),
  既有兩條 obstacle 測試(右緣區命中 / 左半場不命中)在兩種算法下同號,不是行為漂移。
- a11y、React 效能、其他輪次條目一律不碰。
