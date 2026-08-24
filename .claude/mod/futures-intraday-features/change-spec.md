# change-spec — R2 期貨分時補齊四功能 + 兩效能項

來源:`docs/superpowers/specs/2026-08-24-do-batch-rounds.md` §R2(N042 / N043 / N070 / N096 / N046 / N047 / N087)。
級別 M(跨 lib + 兩元件 + 測試)。拍板前置已在盤點頁完成(CDP/MA 用前一交易日 H/L/C;
夜盤成交屬錨定日)→ 本輪不再開 brainstorm。

## 現狀盤點(讀 code 得到,與 spec 記載有兩處出入)

| 條 | spec 記載 | 現行 code | 處置 |
|---|---|---|---|
| N042 | 反灰,要前端算 | `overlaySupported={false}` 寫死;core 第四道閘 `futures` 不打 `/api/stock/overlay` | 前端算 overlay 注入(同 index 管道) |
| N043/N070 | `available: !futures` 寫死 | 同左(`StockIntradayChart.tsx:1234`) | 近全軸日期界 + 解開 |
| **N096** | 「vp toggle 解禁 + foldVp 參數化」 | **VP/POC 期貨態早已可用**:`vpEnabled = toggles.vp && !stkfut && !index`、toggle `available: !stkfut`;期貨 vp 由 `futuresBarsToAccum` 自折,**不經 `foldVp`** | 只補 lock 測試 + 更正過時註解;`foldVp` 參數化**不做**(唯一需要它的是 stkfut 態,屬 R2 外且該態刻意不畫 VP) |
| N046 | 無 bar 分鐘反演回 null | 同左(`buildIntradayGeometry.minuteOf`) | 加 snapRadius(futures 態限定) |
| **N047** | 1140 rect 每 tick 重建 | `EnergySub` 已 memo,但 `subEnergy` 的 deps 帶 `accum.minutes`,live 價一變就換 identity → 每 tick 重跑 | 量測後**留原樣** + 註解(見 verification §N047) |
| N087 | vp 折自被 deque(20k) 截斷的 snapshot | 同左(`fromSnapshot` 折全量 `snap.ticks`) | 選**標示**(最小方案) |

## SC

- **SC-1(N042)**:期貨分時 CDP / MA 兩鈕可按,按下畫出五條 CDP + MA5/MA20(域內者),
  右緣價位標走 `fmtIndexPts`;基準日 = 日 K 最後一根**已完成** bar(`meta.partial_last` 為真時剔除末根)。
  日 K 尚未回 → 不預先反灰(同既有「未回視為可用」紀律);回了但無已完成 bar → 兩鈕反灰。
- **SC-2(N043/N070)**:期貨分時「成交點」鈕不再反灰;近全軸上買 ▲ / 賣 ▼ 落在
  `alldayIndexOf(成交 HHMM)`,且**只畫錨定日相同**的成交(夜盤 00:00–05:00 的成交屬前一日錨定日)。
- **SC-3(N096)**:期貨態量分佈 + POC highlight 有 lock 測試(characterization,現行即綠)。
- **SC-4(N046)**:近全軸 hover 落在無 bar 的分鐘時,十字垂直線/readout 命中**最近**有 bar 的
  分鐘(距離 ≤ `MINUTE_SNAP_RADIUS`),超過則維持退化(只剩水平量尺)。stock / index 態逐值不變。
- **SC-5(N087)**:snapshot ticks 觸頂(≥ 20000)時,量分佈鈕的 tooltip 講明「僅含最近 20000 筆」。

## 不能破壞的既有行為白名單

1. `mode="stock"` / `"index"` 的軸、時間文字、價位口徑、hover 退化規則**逐值不變**
   (`StockIntradayChart.futures.test.tsx` 的 W-1 describe 全綠不動)。
2. `fillPoints` / `fillsByCode` 既有簽名與日期界(今日 ∨ 昨日活單)不動 —— 新的近全軸界另開函式。
3. `buildIntradayGeometry` 前三參數與回傳形狀不變(第四參數 optional,預設 = 現行行為)。
4. 期貨 hlines / VWAP / readout 六欄 / live 佔位「-」等既有語彙不動。
5. `overlayLines` / `edgePriceLabels` / `bandLabels` 幾何不動(只是期貨態開始有輸入)。

## Diff

- 🟢 `lib/futures-overlay.ts`(新):`buildFuturesOverlay(bars, partialLast)` → `StockOverlay`;
  公式與 `copycat/server/overlay.py::compute_cdp / compute_ma` **逐式相同**(整數毫元、floor)。
- 🟢 `lib/fill-marks.ts`:抽出共用的 `baseFill`,新增 `alldayFillPoints(orders, key, anchorDate)`
  —— 錨定日相等 + `alldayIndexOf` 當軸 key;聚合沿用同一支 `aggregate`。
- 🟢 `components/futures/FuturesChart.tsx`:掛 `useFuturesBars(product,"day")`(與日 K 模式同 queryKey,
  TQ 自然去重)+ `useCapitalOrders`;注入 `overlay` / `overlayError` / `overlaySupported` / `fills`。
- 🔴 `components/stock/StockIntradayChart.tsx`:`fills` toggle 解除 futures 反灰;
  futures 態傳 `snapRadius`;vp 鈕在 `accum.vpTruncated` 時帶 hint;過時註解更正。
- 🔴 `lib/stock-intraday-svg.ts`:`buildIntradayGeometry` 第四參數 `opts.snapRadius`(預設 0 = 現行);
  `minuteOf` 在 snapRadius > 0 時就近命中;`export const MINUTE_SNAP_RADIUS`。
- 🟢 `lib/stock-accum.ts`:`StockAccum.vpTruncated?`(唯一產生點 `fromSnapshot`,`ticks.length >= VP_TICK_CAP`)。
- 測試:`lib/futures-overlay.test.ts`(新)、`lib/fill-marks.test.ts`、`lib/stock-intraday-svg.test.ts`、
  `components/futures/FuturesChart.test.tsx`、`components/stock/StockIntradayChart.futures.test.tsx`、
  `lib/stock-accum.test.ts`;兩份 fetch stub 補 `/api/capital/orders` 路由(test-infra)。

## Out of scope(留 next-time)

- `foldVp` 分鐘窗參數化 / 個股期(stkfut)態 VP:期貨態不經 `foldVp`,參數化目前無讀者。
- N047 的 `EnergySub` 單一 path 改寫 / 資料版本 memo key:量測未見瓶頸,且「以總量當版本」
  的判準有靜默 stale 風險(見 verification)。
- N087 的精確補全(以 1K bar 聚合補開盤段):需後端 endpoint,非最小方案。
- 成交點精確版(N069/N066/N071)、a11y。
