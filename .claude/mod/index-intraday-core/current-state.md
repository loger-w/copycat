# current-state — 台股綜合左欄:指數分時圖換 IntradayChartCore + 騰落線吃 flex

分支 `mod/index-intraday-core`,基準 master `c958b141`(2026-08-17)。行號皆為本基準,
prompt 內的 `de44d49b` 快照行號已重 grep 校正。

## 1. 現況(改動前)

### 1.1 指數分時圖(自繪版)

| 項 | 現況 | 位置 |
|---|---|---|
| 元件 | `IntradayChart`(module-private,自繪 SVG) | `frontend/src/components/index/MarketChart.tsx:92-252` |
| 幾何 | `buildIndexGeometry`:yTop=hi×1.003 / yBottom=lo×0.997(hi/lo 含 series.high/low 與全部分鐘收盤),3 個 yTicks [yBottom, ref, yTop] | `lib/index-chart-svg.ts:62-83` |
| viewBox | `SIZE={640,220}`;`height` prop 為 viewBox 單位(caller `paneSvgHeight` 反解),`unitScale` 補字級 | `MarketChart.tsx:29,105,134-135` |
| 均價線 | `g.avgLine` = 分鐘收盤**算術平均**(指數無量);toggle title「分鐘收盤均價(指數無成交量)」 | `MarketChart.tsx:122,227-229` |
| 疊線 | 只做加權(`isTwse`);`overlayLines` 域內畫線 + `outOfDomainLevels` 域外 → 右緣掛牌 `名稱 價位↑↓`;`rightEdgeLabels` 堆疊(昨收 / `價位*` / MA 名稱+價位) | `MarketChart.tsx:107-141,213-248`;`lib/index-chart-svg.ts:96-258` |
| toggle 列 | 三顆(均價 / CDP / MA),`h-[1.375rem] mb-1`(=26px chrome),櫃買 CDP/MA 反灰 title「櫃買無日 K 資料源」,加權失敗「無日線資料」 | `MarketChart.tsx:114-125,147-165` |
| 缺 | **無 hover 十字線 / readout / 高低點標記 / 現價圈 / 平盤紅綠填色 / 左緣價位帶** | — |
| overlay 查詢 | `useIndexOverlay(gate)` 在 `MarketChart` 層無條件呼叫;gate = intraday && TWSE && (cdp‖ma);`overlayError = gate && isError`(G-2:閘關時不鎖鈕) | `MarketChart.tsx:299-323`;`hooks/useIndexOverlay.ts` |
| a11y | svg `role="img" aria-label="{name}分時走勢"`,toggle 鈕在 svg 外 | `MarketChart.tsx:166-171` |

### 1.2 個股 core(要注入的目標)

| 項 | 現況 | 位置 |
|---|---|---|
| 匯出 | `IntradayChartCore(CoreProps)`、`StockIntradayChart(Props)`(非受控包裝)、`ChartVariant = "page"\|"card"` | `components/stock/StockIntradayChart.tsx:647-692, 1164-1184` |
| Props | `accum / mainHeight / subHeight / stkfut / fills`;Core 另 `toggles / onToggle / variant / width` | `:647-680` |
| overlay | **內建** `useStockOverlay(accum.code, !stkfut && !isInstrumentKey(code) && (cdp‖ma))` | `:708-711` |
| 幾何 | `buildIntradayGeometry({minutes,meta,high,low},{w,mainH},xw)`;缺 upper/lower → **對稱 autofit**(ref 置中,半幅 = max 偏離×1.1,最少 1%);yTicks fallback 3 格 [yTop, ref, yBottom] | `lib/stock-intraday-svg.ts:320-416` |
| 副圖 / VP | `EnergySub`(需 `m.v`)、`buildVpBars(accum.vp)`;`vpEnabled = toggles.vp && !stkfut` | `:744-763, 1088-1105` |
| readout | 六欄(時間 / 價 / % / 量 / 外 / 內)+ 成交欄;card 切前四 | `:822-880` |
| 說明列 | `figcaption`(外盤 / 內盤 / 未分類 / 外盤比 / 判定率 / VWAP);card 省略(`side === null`) | `:796, 1119-1145` |
| toggle 列 | 五顆(均價 / CDP / MA / 量分佈 / 成交點);disabled title `stkfut ? "期貨合約本輪不提供" : "無日線資料"` | `:899-943` |
| 右緣 | CDP `價位*` 走 `fmtTickPrice`(tick snap)、MA 名稱在 R_AXIS 帶 + `edgePriceLabels` 價位;**域外疊線靜默不畫**(`overlayLines` push 早退) | `:90-95, 341-363, 442-457`;`lib/stock-intraday-svg.ts:500-524` |
| hover 價標 | `snapDown(g.priceAtY(y))`(可下單價位) | `:882` |
| 空態 | `priceLine.length === 0` → 「尚無成交」 | `:785-791` |
| wrapper | page = `<figure ... p-4 border>`;card = `<div>` | `:1153-1159` |
| 尺寸契約 | 單檔頁 `svgBox`(viewBox 800 等比)、card `cardSvgBox`(**1:1 px**) | `components/stock/StockChart.tsx:139-144`;`lib/chart-frame.ts:59-66` |
| aria | svg `aria-label="分時走勢圖"`(寫死) | `:945-953` |
| VWAP 標籤 | 末點右側就地標,值 = `accum.vwap`(後端逐筆) | `:205-209, 462-470` |

### 1.3 資料 shape

- `IndexSeries { p, ref, high, low, stale, minutes: Record<"HHMM", milli> }`(`hooks/useIndexStream.ts:13-20`),
  **無量**;鍵已由後端 `minute_key` 過濾 0901–1330。
- `StockAccum`(`lib/stock-accum.ts:71-98`):`minutes: Map<min, MinuteAgg{c,v,i,o,u,h?,l?}>`、`vwap`、`vp`
  (必填 Map)、`meta{name,ref,upper,lower,y_vol}`、`high/low`、`last{p,t,cum_vol}`、`trial`(必填)。
- `buildIntradayGeometry` 的 vwapLine 以 `m.c × m.v` 加權:v=0 → vwapLine 空(均價線消失);
  **v=1 → 走勢 = 分鐘收盤算術平均 = 現版 avgLine 語意**。
- 高低標記 = 等值反查 `m.h === accum.high`(`stock-intraday-svg.ts:460-470`)。

### 1.4 佈局

| 項 | 現況 | 位置 |
|---|---|---|
| 主 grid | `flex-col ... @[1050px]:grid grid-cols-[3fr_2fr]`,`overflow-y-auto` | `components/index/IndexPage.tsx:124-127` |
| 左欄 | `@container flex flex-col gap-3 @[1050px]:min-h-0` | `:131` |
| 雙圖 grid | `grid grid-cols-1 gap-3 flex-1 min-h-80 @[640px]:grid-cols-2`(320 = 標的列 28 + 週期列折 2 行 56 + gap 24 + figure 192) | `:137-140` |
| 家數帶+騰落線 section | `flex shrink-0 flex-col gap-2` | `:168-171` |
| 騰落線 wrapper | `flex h-24 shrink-0 items-center justify-center`(96px 固定);`useContainerSize` 已掛;fallback vb 高 150 | `components/index/AdvanceDeclineChart.tsx:69-73, 82` |
| MarketPane figure | `flex min-h-48 flex-1 flex-col ... p-4`;量測 wrapper `mt-2 flex min-h-0 flex-1 flex-col`;figure chrome = border 2 + p-4 32 + caption 20 + mt-2 8 = 62 | `components/index/MarketPane.tsx:411, 428` |
| PANE_FRAMES | intraday `{chromeY:26, insetX:0, vbW:640}` / overlay `{62,34,640}` / candle `{100,34,1400}`;`paneSvgHeight` 地板 96px、−2 抗抖 | `lib/pane-frame.ts:36-59` |
| unitScale | `paneUnitScale` → `MarketChart.unitScale`(**只作用分時態**,K 線態 CandleChart 不吃) | `MarketPane.tsx:350, 446`;`MarketChart.tsx:275-278` |

## 2. Caller map

| 符號 | caller | 影響 |
|---|---|---|
| `IntradayChartCore` | `StockIntradayChart`(page)、`CardIntradayChart`(card)、**新:`MarketChart`** | 加 mode/overlay 注入 props,預設值下前兩者零變化(白名單) |
| `StockIntradayChart` | `StockChart.tsx:176` | 不動 |
| `MarketChart` | `MarketPane.tsx:437-447`(唯一) | intraday 分支換元件;`height` 語意改 px;`unitScale` 移除 |
| `IntradayChart`(index 自繪) | `MarketChart.tsx:309`(module-private,唯一) | 刪除 |
| `buildIndexGeometry` | `MarketChart.tsx:106`、`lib/index-chart-svg.test.ts` | 唯一元件 caller 消失 → 函式 + 測試保留(純函式,`buildOverlayGeometry` 同檔;死碼清理記 next-time,本輪不砍) |
| `outOfDomainLevels` / `rightEdgeLabels` / `RightEdgeLabel` | `MarketChart.tsx:11-14`、`lib/index-chart-svg.test.ts` | `outOfDomainLevels` 續用(index 態掛牌);`rightEdgeLabels` 失去元件 caller,同上保留 |
| `PANE_FRAMES.intraday` | `MarketPane.tsx:346`、`MarketPane.size.test.tsx:140` | 移除(intraday 改 1:1 box);測試該紅 |
| `paneUnitScale` | `MarketPane.tsx:350` | 續用(overlay 態) |
| `useIndexOverlay` | `MarketChart.tsx:302` | 不動 |
| `ChartToggles` | `IndexPage` 上提 → 兩 pane 共用;鍵 vwap/cdp/ma/bb/vp/fills | index 態只用 vwap/cdp/ma |
| `svgFontRem` | `MarketChart.tsx:134-135`、`MarketPane.tsx:127` | MarketChart 端消失,OverlayCard 續用 |
| 動態用法 grep | `grep -rn "IntradayChart\b\|MarketChart\|unitScale\|PANE_FRAMES" frontend/src` 無字串拼接 / 動態 import | — |

## 3. 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 指數分時圖元件 | `MarketChart.IntradayChart` 自繪(無 hover / readout / 高低 / 現價圈) | `IntradayChartCore mode="index"`:hover 十字 + readout(時間/點位/漲跌%)+ 昨收線 + 均價線 + CDP/MA(加權)+ 域外掛牌 + 高低點 + 現價圈 + 紅綠填色 |
| 幾何 y 域 | hi×1.003 / lo×0.997(緊貼) | 對稱 autofit(ref 置中,半幅 ≥1%)— **觀感差異**:漲跌一邊倒的日子另一半留白;3 個 yTicks 同現版 |
| 尺寸 | viewBox 640×H 等比 + unitScale 補字 | **1:1 px**(同 card 變體):width = 量到寬、mainHeight = 量到高 − 26 − 2(地板 96);unitScale 對分時態失效 → 移除 prop |
| 副圖 / VP / 成交點 | 無 | 無(index 態一律關,toggle 列只三顆) |
| 騰落線 | `h-24` 固定 96px | `flex-1 min-h-40` 吃 flex 剩餘;section `flex-[2] min-h-0`;雙圖 grid `flex-[3]` |
| Backward compat | — | 無對外 API / storage 格式變更;`ChartToggles` 鍵不變;`MarketChart.height` 語意改 px(單一 caller 同步) |
| Migration | — | 無 |

## 4. 既有測試盤點(該紅 / 不該紅)

- 該紅(🔴 預告):`MarketChart.test.tsx`(自繪假設:右緣文字 / aria-label `{name}分時走勢` / viewBox 220 / 均價 polyline 選擇器 / 域外掛牌文字格式)、`MarketPane.size.test.tsx:137-166`(PANE_FRAMES 三態)+ `:168-188`(分時 svg 高 = paneSvgHeight)、`AdvanceDeclineChart.test.tsx:196-241`(TD-6 h-24 固定)、`IndexPage.test.tsx:322-332`(y3 min-h-80 若地板值改)。
- 不該紅:`StockIntradayChart.test.tsx` / `.variant.test.tsx` / `stock-intraday-svg.test.ts` / `GroupGridView*.test.tsx` / `chart-frame*.test.ts` / `index-chart-svg.test.ts` / `MarketPane.test.tsx`(除 :318-431 中依賴自繪 svg 者,待實測)/ `IndexPage.test.tsx` 其餘 / `App.test.tsx`。
