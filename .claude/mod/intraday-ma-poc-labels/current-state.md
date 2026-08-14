# 現況調查:分時圖均線價格標籤 + POC(mod/intraday-ma-poc-labels)

日期:2026-08-14。目標:StockIntradayChart 兩個資訊補強 —— (1) VWAP/MA5/MA20 右緣即時價格
數值標籤;(2) volume profile 的 POC(最大量價位)highlight + 價格標籤。

## 相關檔案與現況

### frontend/src/lib/stock-intraday-svg.ts(幾何純函式)
- `buildIntradayGeometry` 產出 `vwapLine: (Pt & { vwap: number })[]`(:338-348,running Σc×v/Σv,
  每分鐘一點);`yTicks` 是函式內寫死的固定清單(TICK_PCTS ±10..0,:352-372)——
  **user 指示不硬塞 yTicks,額外價位標籤另開渲染分支**。
- `overlayLines(overlay, g, toggles)`(:452-476)→ `OverlayLine { y, priceMilli, level }`,
  level ∈ ah/nh/cdp/nl/al/ma5/ma20;域外(閉區間外)不給;toggle 關的類別不給。
- 版面常數:`Y_AXIS_W = 36`(左緣價位帶)、`R_AXIS_W = 40`(右緣疊線標籤帶;最寬內容
  `1005.0*` ≈ 34px @0.5625rem)、`PAD_Y = 4`、`X_LABEL_H = 14`;`plotWidth(w) = w − 36 − 40`。
- `toY` 值域 = `[PAD_Y, PAD_Y + plotH]`,plotBottom = h − X_LABEL_H。

### frontend/src/lib/volume-profile.ts
- `buildVpBars(vp, g, width) → VpBar[]`:域內過濾(閉區間、與 overlayLines 同規)→
  歸一分母取**域內** max(`Math.max(1, ...)` 防全 0)→ 每檔位出 `{ y, h, w, priceMilli, total }`。
- `total` 欄位註解明言「**本輪未接線**——留給後續的分色 / hover 用」= 本次 POC 的接點。
- **沒有算 POC**(最大量價位);全部 bar 同色同透明度(`VP_FILL_OPACITY = 0.25`)。
- 排序:priceMilli 降冪(React key 穩定)。

### frontend/src/components/stock/StockIntradayChart.tsx
- `ChartStatic`(memo,:109-372)畫:y 格線與左緣刻度 → **vp-bars(:238-251,全部
  `fill-ink-muted` + `VP_FILL_OPACITY`)** → 平盤填色 → oLines(線 + 右緣標籤
  `x = w − R_AXIS_W + 2`,`levelText`:CDP 印 `價位*`、**MA 印名稱 "MA5"/"MA20" 無價格**)
  → VWAP polyline(`stroke-ink` 白,**無任何標籤**)→ 主價線 → 極值標記。
- 右緣帶內標籤**無任何碰撞處理**(CDP 五線接近時本來就會疊,既有狀態)。
- toggle:vwap 兩態恆可用;cdp/ma `available = !stkfut && *Available`;vp `available = !stkfut`;
  `vpEnabled = toggles.vp && !stkfut`(foldVp 折入窗是現貨窗,期貨態畫了就是假資料,:563-566)。
- 期貨態(stkfut)語意:overlay 不打請求、VP 不畫 —— **user 指示此語意不動**。

### 配色 token(index.css)
- `--color-ma5 #f0b429 黃`、`--color-ma20 #b794f4 紫`、VWAP 線 = `stroke-ink` 白。
- `stroke-surface` + `paintOrder="stroke"` halo 是本 repo 圖內文字的既有樣板
  (EnergySub 量刻度、極值標記、FuturesChart 右緣 overlay 標籤 `textAnchor="end"` 皆用)。

## Caller map(grep 全量,含動態用法查無)

| 符號 | caller |
|---|---|
| `buildVpBars` / `VpBar` / `VP_FILL_OPACITY` | StockIntradayChart.tsx(唯一元件 caller)+ volume-profile.test.ts + StockIntradayChart.test.tsx:1038 |
| `vwapLine` | StockIntradayChart.tsx(polyline)+ stock-intraday-svg.test.ts:722-730 |
| `overlayLines` / `levelText` / `LEVEL_FILL` | StockIntradayChart.tsx(唯一元件 caller)+ stock-intraday-svg.test.ts |
| `buildIntradayGeometry` | StockIntradayChart / MiniIntradayChart / volume-profile.test.ts(薄包)|
| `R_AXIS_W` | StockIntradayChart、MiniIntradayChart(幾何補償:加回再用 viewBox 裁掉)、兩測試檔 |

| `StockIntradayChart`(元件本身)| StockChart.tsx:157(唯一元件 caller)+ StockChart.test.tsx(未 mock,連帶渲染新標籤;review F8 逐條查無 text 計數 / 右緣斷言,不該紅)+ StockChart.futconverge.test.tsx(vi.mock,不受影響)|

MiniIntradayChart 不畫 VWAP / oLines / VP → 只要不動 `buildIntradayGeometry` 輸出與
`R_AXIS_W` 值就零影響。動態用法:無(`import` 全靜態,無字串拼 key 存取)。

## 既有測試會受影響的點

- `StockIntradayChart.test.tsx:1030-1041`「預設開:每個成交價位一根長條…」:**loop 全部
  vp-bar 斷言 `VP_FILL_OPACITY` + `fill-ink-muted`** → POC bar 改色/透明度後**該紅**(預告)。
- `volume-profile.test.ts`:多為 `find(...).w/.y/.h` 逐欄斷言 + `toEqual([])`,VpBar 加欄位
  不破壞;無整物件深比對。
- `stock-intraday-svg.test.ts`:不動幾何 → 不該紅。

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| VWAP 線 | 只有白色 polyline,無價位資訊 | 右緣即時 VWAP 數值標籤(白、跟線色) |
| MA5/MA20 線 | 右緣帶只印名稱 "MA5"/"MA20" | 名稱保留,另補即時價位數值標籤(黃/紫跟線色) |
| 標籤碰撞 | 右緣帶零碰撞處理(既有) | 新增標籤之間互相避讓、不疊 y 軸刻度/彼此 |
| VP bars | 全部同色 0.25 透明度,`total` 未接線 | POC(域內最大量價位)判定 + highlight + 長條尖端價格標籤 |
| 期貨態 | overlay/VP 不畫,vwap toggle 可用 | 語意不動;VWAP 標籤兩態都出,POC 隨 VP 既有可用性(現貨) |

## Backward compat / migration

- 純前端渲染,無 API / 資料格式改動,無 migration。
- `VpBar` 加欄位 = additive,唯一 caller 在同 repo 同輪改;不構成對外契約。
- signature 變更:`buildVpBars` 回傳元素多 `poc` 欄(additive);新增 lib 純函式一支
  (右緣標籤佈局);`ChartStatic` props 視需要加(memo-safe 純量/穩定 identity)。
