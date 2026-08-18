# progress ledger — mod/futures-intraday-core

| 包 | 內容 | 狀態 | commit |
|---|---|---|---|
| P1 🟢 | core mode="futures" + xWindow/hourTicks/timeText/hlines 注入;lib/allday 新增;futures-accum-adapter | done | b7695d5c [red] / 8433a5fd [red 追加 R2-1] / fbb446d5 [green] |
| P2 🔴 | FuturesChart 換 IntradayChartCore(量測 box / live gate 4 tailIndex / hlines) | pending | |
| P3 🔴 | FUT_CHART_MODES 1–10/15/30/60 | pending | |
| review | change-spec round 1:P0×1 P1×3 P2×5 全 accepted 已修;round 2 限縮輪進行中 | | |

## 順手清單(看到但**本輪不動**)

- `ChartHLine` 型別與 `EMPTY_HLINES` 空集合常數現在各有兩份:`CandleChart.tsx`(既有,
  private 常數)與 `StockIntradayChart.tsx`(P1 新增)。型別是 import 同一份不會漂,
  但空集合常數是兩顆。搬進 `lib/` 是 🔵 純重構,與本輪三類 commit 混不得。
- P1 交付後 `FuturesChart.tsx:48-54` 的 private `indexOfBar` 與新的
  `allday.alldayIndexOfStamp` 暫時並存(重複一份)—— 由 P2 的 §3.3 刪除收斂,不在 P1 動。
