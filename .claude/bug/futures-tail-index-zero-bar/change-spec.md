# bug/futures-tail-index-zero-bar — 期貨分時 gate 5 的尾根跳過 0 價 bar

日期:2026-08-28。來源:`docs/superpowers/specs/2026-08-25-do-batch-review.md` §2.2 Spec 2、§5 A3;
08-28 user 拍板題 4「順帶」(memory `do-batch-batch2-decisions-0828`;handoff `copycat-handoff-2026-08-28-q4-q5.md` §1.2)。
小活分流(單檔一處、無對外 API)。門檻 `FUT_LIVE_LAG_MAX` 3 → 4 **不在本案**(拍板:先量再定)。

## 1. 現況 vs 目標

| 項 | 現況 | 目標 |
|---|---|---|
| `FuturesChart.tsx::tailIndex` | slice 尾往前第一個「索引可解」的 bar;0 價 bar 也算 | 與 `futures-accum-adapter.ts::futuresBarsToAccum` 同一把尺:`c <= 0` 整根跳過 |

失效樣態(改前):真 bar 至 10:00、後五根 0 價、最後成交 10:05:30 → tailIndex 取 10:05(畫面上不存在)→ lag 1 → 架橋,
主線從 10:00 直線拉到 10:07;真缺 6 根卻不印「落後 N 根」。

## 2. Caller map

`tailIndex` 只有 `FuturesChart.tsx` 內兩個讀者:`tailIndex > live.index`(時鐘落後守衛)與 `alldayBarsBetween(tailIndex, trade.index)`(gate 5)。
無動態用法。adapter 的 0 價規則在 `futures-accum-adapter.ts:45-47`。

## 3. 既有行為白名單

1. 五道 gate 的判準逐字不動(只換尾根的定義)。
2. `anchorDate`(`sliceCurrentAllday` 末根)不動:錨定日只看時戳,0 價 bar 的日期照樣可信。
3. adapter 對 `h`/`l` ≤ 0 的容忍(以 `c` 代)不動;本案只鏡射 `c <= 0` 那一條。
4. 門檻 3 不動。

## 4. 行為改動(🔴 一筆)

`tailIndex` 迴圈加 `if (b.c <= 0) continue;`。

## 5. Seams

`frontend/src/components/futures/FuturesChart.test.tsx::gate 5 的尾根跳過 0 價 bar`(紅先行:改前 mainLine 3 點 / 改後 2 點 + 「落後 6 根」)。
