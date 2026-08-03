# candle-right-edge-hover

## Phase 1|重現(2026-08-03 12:27,穩定重現)

- 來源:docs/next-time.md 2026-07-29 條(stock-ui-round2 自評 lens 抓到,當輪依鐵則 B 駁回不順手改)。
- 最小重現:`buildCandleGeometry(bars×10, {width:400, height:300})` 後呼叫 `indexOf`:
  - `indexOf(399.9)` → `9` ✓
  - `indexOf(400)` → **`null`**(預期 `9`)
  - `indexOf(400.1)` → `null`(超界,正確)
- 症狀:CandleChart 最右一個像素 hover 失去十字線。
- 影響範圍:所有用 `buildCandleGeometry().indexOf` 的 hover 路徑(K 線圖);嚴重度 P2
  (單一像素、無資料正確性影響)。
- 重現腳本:暫存 `src/lib/__repro_right_edge.test.ts`(跑畢即刪,紅測試由 Phase 3 正式落
  `candle.test.ts`)。

## Phase 2|Root cause(實驗證實)

`lib/candle.ts:257-261`:

```ts
const indexOf = (x: number): number | null => {
  if (x < 0 || x > size.width) return null;   // x === width 通過 guard
  const i = Math.floor(x / slot);             // slot = width / bars.length
  return i >= 0 && i < bars.length ? i : null; // floor(width/slot) === bars.length → null
};
```

x === size.width 時 `Math.floor(size.width / slot) === bars.length`(整除),被
`i < bars.length` 濾成 null。假說唯一且由上述三點重現直接證實(一次一變數:只變 x)。

## 修法決策(implementation 級,`[auto-default]`)

next-time 條目列的兩個候選:(a) guard 改 `x >= size.width` 回 null(宣告右緣出界 —
行為仍是無十字線,不解症狀);(b) `Math.min(bars.length - 1, Math.floor(x / slot))`
夾制(右緣映到最後一根)。**採 (b)**:症狀是「最右像素理應對應最後一根」,(a) 只是把
現況合法化;(b) 同時吸收浮點邊界(slot*len 略小於 width)一族。guard 本體不動。

## Phase 8|反向驗證(2026-08-03 12:38 PASS)

`git revert --no-commit f226354`(修復 commit)→ `candle.test.ts` **1 failed | 38 passed**
(紅回來的正是右緣那條)→ `git revert --abort` 還原 → **39 passed**。測試確實抓得住 bug。

## 輪內附帶修復(獨立 root cause,獨立 commit)

Phase 6 gate 撞到既有測試紅:`test_market_routes.py::TestTwse::
test_weekly_aggregates_from_same_long_daily_fetch` — fixture 固定 2026-07-27~29(ISO W31),
`is_partial_last` 對 W 比「最後一根 ISO 週 == today ISO 週」→ 寫測試當週 True、
2026-08-03(W32)起恆 False。**日期依賴的潛伏測試缺陷,與本 diff 無關**(本分支零 .py
改動,後端與 master 逐位元相同)。修法 = 該測試改當前 ISO 週(週一~三)動態 fixture +
FakeIndexSource 選配 daily_bars(預設路徑零改動),commit `d84c440`。
今天(週一)fixture 含兩天未來日照樣綠 = 「未來日無妨」拿到實證。
