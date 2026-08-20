# B1 handoff:台股綜合窄容器可讀性三合一(/mod)

> 2026-08-21 從 next-time 三條(90/92/52)合併升級開工。本檔自足:新 session 讀完
> 即可跑 `/mod`。三條同屬「一頁總覽後 pane/右欄變窄」一族,一輪收。

## 三個子項與實測數字(2026-08-20 MCP 機械量測,非估計)

1. **K 線態文字不可讀**:1536×864 兩欄態,加權 pane 的 CandleChart 實渲染
   **282×113px、scale 0.202(viewBox 寬 1400 寫死)→ 全部文字 3.0px 高**。
   比 next-time 原估(312–420px)更窄。
2. **漲跌停表水平捲軸**:右欄 scroller clientWidth **431px**、表格需 **612px** →
   恆有捲軸、**約 30% 欄寬(金額(億)/量比/狀態尾段)藏在捲軸後**,非邊緣 case。
3. **週期列折 3 行**:~350px pane 週期列(分時/1–10分/30/60/90/日K/週K/月K)
   **折 3 行、總高 74px(單鈕 22px)**,兩個 pane 都命中,吃掉約 50px 圖高。

截圖:`docs/specs/next-time-mcp-verification-2026-08-20/screenshots/90-52-overview-dayk-and-3row-periods.jpg`
(同張含子項 1 與 3 實景;子項 2 見同資料夾其他張的右欄)。

## 檔案地圖

- `frontend/src/components/index/MarketPane.tsx` —— pane 佈局、週期列、K 線態掛載。
- `frontend/src/components/stock/CandleChart.tsx` —— **共用元件**(個股頁也用),
  viewBox 寬 1400 寫死、約五處 fontSize。
- `frontend/src/lib/pane-frame.ts` —— 既有 `paneUnitScale` + `svgFontRem` 字級補償,
  **目前只蓋 intraday/overlay,K 線態沒接**(2026-08-16 onepage 輪只補了分時)。
- `frontend/src/components/index/LimitListSection.tsx` —— 漲跌停 9 欄表。

## 修法候選(next-time 原文,spec 階段拍板)

- 子項 1:(a) CandleChart 收 `unitScale` prop 套進五處 fontSize(沿 pane-frame 既有
  口徑);或 (b) MarketPane 窄 pane 傳較小 viewBox(需 CandleChart 開 `width` prop)。
  **硬約束:個股頁 CandleChart 不得受影響**(共用元件,預設值必須零差異)。
- 子項 2:(a) 金額(億)/量比 兩欄在窄容器 `@[…]:hidden`;(b) 縮 px-2 → px-1。
  th/徽章已 `whitespace-nowrap`(防折行截字,別退回)。
- 子項 3:(a) 週期鈕收窄(px/字級);(b) 折疊(次要檔位收進「更多」)。

## 相關債(動的時候一併看,不強制入 scope)

- next-time 91:`rightEdgeLabels` 的 `EDGE_LABEL_H` 未隨 unitScale 縮放 —— 字放大後
  右緣標籤(昨收/CDP/MA)間距相對變密可能相疊;`lib/index-chart-svg.ts` 是個股圖
  共用契約,動它要盤 caller。
- MarketPane K 線態的 y-tick 全 0 duplicate key(next-time 08-05 futures-allday 節)
  若順路碰到可收。

## 驗證(SC 候選)

- 機械判定:1536×864 iframe 下 (a) CandleChart 文字實高 ≥ 8px(或拍板閾值);
  (b) LimitList scroller `scrollWidth <= clientWidth`(或拍板保留捲軸但首 N 欄可見);
  (c) 週期列 ≤ 2 行。個股頁 CandleChart 幾何/字級 **零變**(回歸鎖)。
- viewport 控制手法:同源 iframe host(`frontend/public/__viewport_host.html?w=&h=`,
  臨時檔收尾刪)—— `resize_window` 對最大化視窗無效、`computer.zoom` 會污染 device
  metrics,見 skill `ops-discipline`「claude-in-chrome 截圖驗證三個坑」節。
  對照組:2560 寬(user 實機)不得退化。
- 完成 gate:`npm test` + `npx tsc -b` + `npx eslint src` + react-doctor(見 auto-verify)。

## Traps

- 先讀 `frontend-conventions`(container query 量的是最近 @container 祖先 ——
  2026-08-16 這頁踩過)與 `frontend-testing`。
- MarketPane.size.test 依賴 `INTRADAY_CHROME_Y` 等常數字面(next-time 已記硬寫問題),
  動佈局高度時注意這些測試的語意是「鎖行為」還是「鎖舊字面」。
- M 級 → 實作依 harness 紀律 dispatch(顯式帶 model)。

## 起跑 prompt

```
/mod 台股綜合窄容器可讀性三合一:1536 兩欄態下 (1) K 線態 CandleChart 文字 3.0px 不可讀(pane 實渲染 282px、viewBox 1400 寫死)(2) 漲跌停表 431/612px 恆水平捲軸、30% 欄寬藏起來 (3) 週期列折 3 行 74px 吃圖高。先讀 docs/superpowers/specs/2026-08-21-b1-overview-narrow-pane-handoff.md(實測數字/檔案地圖/修法候選/驗證手法已備齊);硬約束 = 個股頁共用 CandleChart 零差異。
```
