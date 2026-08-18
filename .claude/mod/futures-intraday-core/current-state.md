# current-state — 期貨頁分時圖換 IntradayChartCore + 分 K 檔位 1–10/15/30/60

分支 `mod/futures-intraday-core`;行號基準 master `010330ad`(2026-08-18)。
前輪同型改動(加權 / 櫃買分時圖換 core,PR #63)artifact:`.claude/mod/index-intraday-core/`。

## 1. 現況(讀 code 得到的事實)

### 1.1 期貨分時圖 = `FuturesChart.tsx` 內自繪 SVG(`frontend/src/components/futures/FuturesChart.tsx`)

- 模式列 `FUT_CHART_MODES`(`lib/fut-chart-mode.ts:13-21`):`intraday / m1 / m5 / m15 / m30 / m60 / day`;
  `isFutChartMode` 由該表推導(localStorage 白名單);`futMinutesOf("m30") → 30`;
  `initialFutChartMode` 壞值退 `intraday`。K 線 = `aggregateBars(bars, minutes)` → `CandleChart`
  (`FuturesChart.tsx:322-323, 393-403`),`MINUTE_INIT_BARS = 240`、`DAILY_INIT_BARS = 120`。
- 分時(`mode === "intraday"`)= module-private `IntradayChart`(`:127-244`):
  - viewBox `1140 × 340`(`INTRADAY_VB_W = ALLDAY_LEN` **export 供測試算 x**;`INTRADAY_VB_H = 340`),
    `className="w-full"` → 高度隨寬度等比(無量測)。
  - x = 近全軸索引 / 1140(`toX(index)`,`:99-101`);索引由 `indexOfBar("YYYY-MM-DD HH:MM")`
    (`:48-54`)經 `alldayIndexOf(HHMM)`(`lib/allday.ts`)取得;死區(13:46–15:00 / 05:01–08:45)→ null 略過。
  - 序列 = `sliceCurrentAllday(bars)`(錨定日 slice)→ `IntradayPoint{index, c}`(`:275-284`)。
  - **live 點**(`:288-305`):牆上時鐘 `liveSlotOf(new Date())`(當前分 + 1 為終點標記;死區 null;
    回 `anchor` 供錨定日 gate);三道 gate:`state.p` null / 死區 / `live.anchor !== anchorDateOf(last.t)`
    / 時鐘落後資料(`tail.index > live.index`)→ 不畫;同索引覆寫尾點、否則 push;
    `<circle data-testid="allday-live">`。**刻意不進 useMemo**(deps 表達不了「現在幾點」)。
  - y 域(`buildIntradayGeometry` `:103-125`):`hi/lo` = closes ∪ base(ref 或均值)× (1±0.3%);
    3 格刻度 `[yBottom, base, yTop]` 左上角灰字;昨收虛線 `2 3`;`ALLDAY_TICKS` 九個時間標籤 + 淡直線;
    主線 `<polyline data-testid="allday-line" class="stroke-accent" 1.4>`(單色,無紅綠、無填色、無均價線、
    無高低點、無 hover)。
  - **overlay hlines**(`:216-241`,testid `chart-hline`):持倉均價(本契約、`fmt` label「均 X 多N口」、
    `<title>` 證據)+ OI 撐壓(`pickOiLines`);**超出 y 域不畫**(`g.hlineY` 回 null);線 `5 3` 虛線、
    label 右對齊 `x = W − 4`、`fill-ink stroke-surface` halo。分時 / K 線兩模式共用同一份 `hlines` useMemo(`:262-286`)。
  - 外框:`<div className="rounded-md border border-line bg-surface p-2">`(`:380`);
    空序列 → 「無分時資料」(`:371-377`);`meta.source === "unavailable"` → 「暫無資料(TC4 未回應)」(`:363`);
    isPending「載入中…」/ isError「K 線載入失敗」。
  - 根 `<div className="flex min-h-0 flex-1 flex-col">{modeRow}{body()}</div>`(`:407-412`);
    **無 useContainerSize、無 toggles、無 readout**。
- 資料:`useFuturesBars(product, mode, active)`(`hooks/useFuturesBars.ts`):分鐘級一律 `tf=1&days=5&session=allday`
  (**同一份原料餵分時與所有分 K**;`mode !== "day"` 即分鐘級),日 K `tf=D`;`active=false` 停輪詢。
  後端 1K bar 帶 `uv/dv`(futures-allday SC-8,`stock_source.py:62-70`)= 內外盤量。
- caller:`FuturesPage.tsx:143`(唯一;`product/state/resolvedYm/active`);App lazy 掛 `hidden` 保留 DOM。
- `FuturesProductState`(`types.ts:176-190`)有 `p / ref / upper / lower / name`;`upper/lower` = ±10% 漲跌停。

### 1.2 個股分時圖 = `IntradayChartCore`(`components/stock/StockIntradayChart.tsx`;R4 後含 mode="index")

- Props(`:735-756`):`accum: StockAccum` / `toggles`(受控)/ `onToggle` / `variant page|card` / `width` /
  `mainHeight` / `subHeight` / `stkfut` / `fills` / `mode?: "stock"|"index"` / `overlay` / `overlayError` /
  `overlaySupported` / `overlayOffTitle` / `ariaLabel`。
- x 窗 `xw = stkfut ? STKFUT_WINDOW : SPOT_WINDOW`(`:784`)— **線性單段窗**(`XWindow{start,end}` 分鐘數);
  `hourTicks = hourTicksOf(xw)`(`:785`);時間文字 `hhmm(minute)`(readout `:950`、time-tag `:1207`);
  `minuteToX / minuteOf / windowedEntries / sideSummary / barW` 全吃 `xw`(`lib/stock-intraday-svg.ts`)。
  **幾何對 key 的唯一要求 = 落在 `[xw.start, xw.end]` 的整數、可排序** —— key 不必是「分鐘數」語意。
- index 態閘(`const index = mode === "index"` `:778`):overlay 改注入(`:796-799`)、副圖 `EMPTY_ENERGY`
  (`:836`)、`vpEnabled` 排除(`:849`)、`supported`(`:860`)、readout 三欄、`side` null(`:913`)、hover 不
  snap + `fmtIndexPts`(`:1004-1007`)、toggle 三顆(`:1028-1050`)、`priceText/tickText`(`:1114-1115`)、
  空態文字 + 去框(`:904`)、外層 div(`:1306`)。
- 沒有「任意水平線(hlines)」能力:overlay 只有 CDP/MA 七種 `OverlayLevel`。
- 尺寸:page 變體由 caller(`StockChart.tsx:132-138`)`useContainerSize` + `svgBox(size, 800)` 反解
  `mainH/subH`(260:70);未量到走 800×260 / 800×70。
- 前輪 R4 adapter 樣板:`lib/index-accum-adapter.ts`(`indexSeriesToAccum`;v=1、h=l=c、窗內鍵、`upper/lower null`)。

### 1.3 期貨頁 K 線與相鄰不動件

- `CandleChart` 用法(`FuturesChart.tsx:393-403`):`key=${product}-${mode}`、`initBars`、`hlines`、`volumeDelta`;
  **未傳 `height`**(固定 viewBox 1400×578 等比)。
- `useChartToggles`(`hooks/useChartToggles.ts`)= 全站單一 localStorage key(個股頁 / 群組圖牆 / 台股綜合共用同一份)。
- `useFuturesBars` 只看 `mode !== "day"`,對 `FutChartMode` 值域無其他假設。

### 1.4 既有測試(caller map of tests)

- `FuturesChart.test.tsx`(373 行):import `INTRADAY_VB_W`、`allday-line` points x 值、`allday-live`、`chart-hline`
  (`getAllByTestId("chart-hline")` 分時 / K 線兩組)、模式列 aria-pressed / localStorage、輪詢 gate、
  `meta.source=unavailable` 文案、live 錨定日 gate 四案。
- `fut-chart-mode.test.ts`:七檔值域逐值 + `isFutChartMode("m7") === false`(← 目標下要翻)+ `futMinutesOf`。
- `FuturesPage.test.tsx`(307 行):不引用分時 svg 內部語彙(grep `allday-|INTRADAY_VB_W` 無命中)。
- `StockIntradayChart*.test.tsx` / `GroupGridView*.test.tsx` / `MarketChart.test.tsx` / `MarketPane*.test.tsx`:
  core 的 stock / index 態消費者(W-1 / W-2 白名單的機械閘)。

## 2. 現況 vs 目標

| 面向 | 現況 | 目標 | caller 影響 | backward compat / migration |
|---|---|---|---|---|
| 期貨分時圖元件 | `FuturesChart` 內自繪 `IntradayChart`(單色線、3 格刻度、無 hover / readout / 均價 / 高低 / 副圖) | 換 `IntradayChartCore` **mode="futures"**:hover 十字 + readout 六欄 + 昨收紅綠填色 + 均價線(真 VWAP,Σc·v/Σv)+ 高低點 + 成交量副圖 + 說明列(外/內/未分類/判定率;bars 帶 uv/dv)+ VP(分鐘收盤 × 量折入)+ hlines(持倉均價 / OI 撐壓)保留 | `FuturesPage` 單一 caller,簽名不動 | 無對外 API / storage 變更 |
| x 軸 | 近全三段軸(1140 索引,死區不佔 x),`ALLDAY_TICKS` 九標籤 | 同一條軸:core 加 `xw` / `hourTicks` / `timeText` 注入;adapter 把 bar → **軸索引當 key**,`xw = {0, 1139}` | core 新 optional props,預設 = 現行為 | — |
| 分時尺寸 | viewBox 1140×340 等比(高隨寬) | 同個股頁:`useContainerSize` + `svgBox(size, 800)` 反解 mainH/subH(260:70),量不到走 800×260/70 | FuturesChart 內部 | — |
| y 域 | hi/lo × (1 ± 0.3%) | core 對稱 autofit(以 ref 置中,半幅 ≥ 1%);`upper/lower` 傳 null(±10% 漲跌停域會把期指日內線壓成平線) | — | 觀感差異(同 R4 §5) |
| live 現價點 | 牆上時鐘落點 + 三道 gate,`allday-live` | gate 邏輯**保留原樣**在 FuturesChart(純函式不動),結果餵 adapter 合進 minutes;現價圈 = core `last-dot`(序列末點) | 測試 testid 改 | — |
| hlines | 自繪 `chart-hline`(域外不畫、`<title>`、右對齊 label) | core 新 `hlines?: readonly ChartHLine[]` prop,ChartStatic 繪製,**語意逐項同**(域外不畫 / `<title>` / testid `chart-hline`) | stock / index 態不傳 = 零渲染 | — |
| 空態 | 「無分時資料」 | core futures 態空態文字沿用「無分時資料」 | — | — |
| K 線檔位 | intraday / 1 / 5 / 15 / 30 / 60 / 日K(7 檔) | intraday / **1–10** / 15 / 30 / 60 / 日K(**15 檔**) | `useFuturesBars` 只看 `!== "day"` 不動;`futMinutesOf` 已泛化 | localStorage 舊值皆在新值域內 → 免 migration;新值被舊 build 讀到走 `isFutChartMode` 白名單退 intraday(向後亦安全) |
| toggles | 期貨分時無 toggle | 吃全站 `useChartToggles`(與個股 / 綜合同一份 localStorage) | — | 既有 key,不 bump 版本 |
| CDP / MA / 成交點 | 無 | **本輪不做**:反灰 + tooltip(期貨無現股日線疊線來源;成交點需近全軸日期界另做,留 next-time 既有條) | — | — |

## 3. 動態用法 grep 結果

- `FUT_CHART_MODES / isFutChartMode / futMinutesOf / FutChartMode`:只 `FuturesChart.tsx`、`useFuturesBars.ts`、
  `fut-chart-mode(.test).ts` 四檔;無字串拼接動態引用。
- `INTRADAY_VB_W`(FuturesChart export):只 `FuturesChart.test.tsx`。
- `allday-line / allday-live`:只 `FuturesChart.test.tsx`。
- `chart-hline`:`FuturesChart.test.tsx`(分時 + K 線)、`CandleChart.test.tsx`(K 線自有)。
- `mode="index"` / `IntradayChartCore` 消費者:`MarketChart.tsx`、`CardIntradayChart.tsx`、`StockIntradayChart`(wrapper)、
  對應測試。
