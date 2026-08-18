# progress ledger — mod/futures-intraday-core

| 包 | 內容 | 狀態 | commit |
|---|---|---|---|
| P1 🟢 | core mode="futures" + xWindow/hourTicks/timeText/hlines 注入;lib/allday 新增;futures-accum-adapter | done | b7695d5c [red] / 8433a5fd [red 追加 R2-1] / fbb446d5 [green] |
| P2 🔴 | FuturesChart 換 IntradayChartCore(量測 box / live gate 4 tailIndex / hlines) | done | 28b826fe [red] / 05d59757 [green] |
| P3 🔴 | FUT_CHART_MODES 1–10/15/30/60 | done | 2d05bb96 [red] / 4ab97cef [green] |
| review | change-spec round 1:P0×1 P1×3 P2×5 全 accepted 已修;round 2 限縮輪進行中 | | |

## 順手清單(看到但**本輪不動**)

- `ChartHLine` 型別與 `EMPTY_HLINES` 空集合常數現在各有兩份:`CandleChart.tsx`(既有,
  private 常數)與 `StockIntradayChart.tsx`(P1 新增)。型別是 import 同一份不會漂,
  但空集合常數是兩顆。搬進 `lib/` 是 🔵 純重構,與本輪三類 commit 混不得。
- P1 交付後 `FuturesChart.tsx:48-54` 的 private `indexOfBar` 與新的
  `allday.alldayIndexOfStamp` 暫時並存(重複一份)—— 由 P2 的 §3.3 刪除收斂,不在 P1 動。
  **已於 P2(05d59757)收斂,本條勾銷。**
- P2 新增:`MAIN_RATIO_NUM/DEN`(260:70)與 `INTRADAY_VB_W = 800` 在 `FuturesChart` /
  `StockChart` / `chart-frame.CARD_MAIN_RATIO` 三處各有一份(core 的 `DEFAULT_W` /
  `MAIN.height` / `SUB.height` 未 export)。收成一份是 🔵 純重構,本輪不動。
- P2 新增:`FuturesChart.test.tsx` 的模式列 15 顆案以 `container.querySelector("div > div")`
  取頂列(core 的 toggle 鈕也是 button,`screen` 全域取會混到)。core 若哪天在頂列外
  再包一層,這個選擇器會靜默取錯 —— 值得的話改成給模式列一個 testid,🔵 重構。

## P2 / P3 驗證數字(2026-08-18)

- `npm test -- --run`:129 檔 2273 案全綠(P2 green 時 2272,P3 補一案)。
- `npx tsc -b` / `npx eslint src`:零錯。
- 個股 / 群組 / 綜合既有測試(`StockIntradayChart*` / `GroupGridView*` / `MarketChart` /
  `MarketPane*` / `stock-intraday-svg` / `App` / `FuturesPage`)一支未紅、一字未改(SC-9)。
