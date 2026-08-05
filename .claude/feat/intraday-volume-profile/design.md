# design — 分時圖價位別成交量 v1

changelog:
- v1(2026-08-05):初版。
- v2(2026-08-05):design review round 1 七條全修 — R1 顏色改 `fill-ink-muted` +
  `VP_FILL_OPACITY = 0.25` 常數(fill-line 在深底上乘 0.35 幾乎不可見);R2 補
  StockChart/StockPage 既有 fixture 遷移 + SC-4 gate 節;R3 width 實名 `MAIN.width`
  (元件內 `mainW`);R4 Known Risks 記後端 20k deque 上界;R5 foldVp 套
  [09:00, 13:30] 窗(與 windowedEntries/sideSummary 同尺,VP 總張 = 說明列三數和);
  R6 縫改比例式 `h = max(1, dist × 0.85)` + 高密度域測試;R7 「量分佈」標籤維持、
  窄容器截斷接受 + 窄寬截圖對照。

**Goal**:分時圖加價位別成交量水平長條(SC-1..4);零後端改動、前端四檔。

**架構**:資料 fold 在 `stock-accum`(與 tape 同源、先於截斷)→ 幾何純函式新檔
`lib/volume-profile.ts`(SKILL 純渲染抽 lib 紀律)→ `StockIntradayChart` 的 ChartStatic
掛渲染 + toggle。與 CDP overlay 同一「價位 → toY → 畫水平元素」樣板。

## 檔案組織

| 檔 | 變更 | SC |
|---|---|---|
| `frontend/src/lib/stock-accum.ts` | `VpCell` 型別 + `StockAccum.vp` + fromSnapshot 全量 fold + applyTick 增量 | SC-1 |
| `frontend/src/lib/volume-profile.ts`(新) | `buildVpBars` 純函式 + `VP_MAX_W_RATIO` | SC-2 |
| `frontend/src/hooks/useChartToggles.ts` | `vp: boolean`,DEFAULTS `vp: true`,**不 bump version** | SC-3 |
| `frontend/src/components/stock/StockIntradayChart.tsx` | useMemo vpBars → ChartStatic 新 prop → 渲染層 + toggleDefs「量分佈」 | SC-3 |
| `frontend/src/lib/stock-accum.test.ts` | SC-1 | |
| `frontend/src/lib/volume-profile.test.ts`(新) | SC-2 | |
| `frontend/src/components/stock/StockIntradayChart.test.tsx` | SC-3 | |
| `frontend/src/components/stock/StockChart.test.tsx` | R2:fixture 補 `vp: new Map()`(`as unknown as StockAccum` 硬轉會漏欄,執行期 TypeError) | SC-4 |
| `frontend/src/components/stock/StockPage.test.tsx` | R2:同上(兩處 fixture) | SC-4 |

## SC-1 資料層 — stock-accum.ts

```ts
export interface VpCell { t: number; o: number; i: number }  // 總張 / 外盤 / 內盤
// StockAccum 新欄:vp: Map<number, VpCell>(key = snapDown 後毫元檔位)

function foldVp(vp: Map<number, VpCell>, t: string, p: number, q: number, side: string): void {
  if (p <= 0) return;                      // 市價偽價位防禦(isMarketLevel 同規)
  const m = minuteKey(t);                  // R5:與 windowedEntries / sideSummary 同一把尺
  if (m < X_START_MIN || m > X_END_MIN) return;  // 窗外成交不入 VP(口徑一致,可互驗)
  const key = snapDown(p);
  const cell = vp.get(key) ?? { t: 0, o: 0, i: 0 };
  vp.set(key, { t: cell.t + q,
                o: cell.o + (side === "outer" ? q : 0),
                i: cell.i + (side === "inner" ? q : 0) });
}
```
- `fromSnapshot`:對 `snap.ticks ?? []` **原始全量陣列** fold(在 `slice(-TAPE_MAX)` 之前
  的來源上;tape 截斷行為不變)。
- `applyTick`:`const vp = new Map(acc.vp)` 淺拷後 fold 本筆(cell 物件重建不就地改 —
  memo 比較與時間旅行安全;O(價位數) ≤ 域內檔位數 ~200)。
- seq 跳號 / 回補完成 → 既有全量 refetch 路徑走 `fromSnapshot` 重建,天然同源。
- `side` 只認 `"outer"`/`"inner"`,其餘進 t 不進 o/i(與 MinuteAgg 的 u 語意一致,
  分色資料先備、本輪不渲染)。
- 窗常數 `X_START_MIN`/`X_END_MIN` 自 `stock-intraday-svg` import(單一定義);
  窗過濾用**正向條件**(`m >= START && m <= END` 之否定;A3 — NaN 分鐘鍵排除,
  與 windowedEntries 同形)。過濾判定用 `isMarketLevel`(B4 單一定義)。
  **VP 全部 bar 的 t 總和 = 說明列 外+內+未分類 三數之和 —— 在全部 tick 皆 p>0 且
  後端未觸及 20k deque 截斷的前提下成立**(B4 措辭;R5 一致性測試鎖 + B1 的
  fromSnapshot 截斷 characterization)。

## SC-2 幾何層 — lib/volume-profile.ts(新)

```ts
import { plotWidth } from "@/lib/stock-intraday-svg";
import { tickOf } from "@/lib/stock-tick";
import type { VpCell } from "@/lib/stock-accum";

export const VP_MAX_W_RATIO = 0.22;  // bar 最大寬 = 繪圖區 22%(auto-default)
export const VP_FILL_OPACITY = 0.25; // R1:渲染參數收在 lib 常數,不下放 implementer 裁量

export interface VpBar { y: number; h: number; w: number; priceMilli: number; total: number }

export function buildVpBars(
  vp: ReadonlyMap<number, VpCell>,
  g: { toY: (p: number) => number; yDomain: [number, number] },
  width: number,          // svg viewBox 總寬(與 buildIntradayGeometry 同一 width)
): VpBar[]
```
語意:
- 域過濾:`priceMilli < yDomain[0] || > yDomain[1]` 跳過(overlayLines 同規)。
- 歸一分母 = **域內** cell 的 max t(域縮放時 bar 用滿寬度)。
- bar 幾何([amendment 2026-08-05: code review A1/A2/B2 — 原「向上一個 tick」帶讓
  漲停價 bar 恆 1px 且整體上偏一檔]):價位帶**以成交價置中** `[p − tick/2, p + tick/2]`
  兩端各自 clamp 進 yDomain:`half = tickOf(p)/2`、`top = max(toY(yTop), toY(p + half))`、
  `bottom = min(toY(yBottom), toY(p − half))`、`dist = bottom − top`、
  `h = max(1, dist × 0.85)`、`y = top`(R6 比例縫不變;域端點檔位得半高不外溢;
  `toY(p)` 恆落在 bar 內、bar 中心偏離價線僅半條縫 0.075×dist ≈ 亞像素 —
  縫由下緣吃掉,端點檔位才不上溢;測試以精確偏移斷言鎖)。
- `w = (t / maxTotal) × plotWidth(width) × VP_MAX_W_RATIO`;`x` 恆為 `Y_AXIS_W`
  由元件端負責(bar 自左緣向右 — user 拍板)。`width` = 主圖 viewBox 寬
  **`MAIN.width`**(元件內變數 `mainW`,與 `buildIntradayGeometry` 傳入同一值;R3 —
  不得另宣告 800)。
- 空 map / 全域外 → `[]`。輸出依 priceMilli 降冪(穩定 React key)。

## SC-3 畫面 — useChartToggles + StockIntradayChart

- toggles:`ChartToggles` 加 `vp: boolean`;`DEFAULTS = { ..., vp: true }`。
  **不 bump `TOGGLES_VERSION`**:舊存檔無 `vp` 鍵,`{...DEFAULTS, ...flags}` 自然補預設
  (version bump 僅在改「既有鍵」預設時需要 — bb 前例)。
- `StockIntradayChart`:
  - 資料層:`const vpBars = useMemo(() => toggles.vp ? buildVpBars(accum.vp, g, mainW) : [],
    [accum.vp, g, toggles.vp, mainW])`(W-5:穩定 identity 才不打穿 ChartStatic memo)。
  - `ChartStatic` 新 prop `vpBars: VpBar[]`;渲染插在 **y 格線之後、areaPolygon 之前**
    (z-order:長條在紅綠填色與走勢線之下,不遮線):
    `<g data-testid="vp-bars">{vpBars.map(b => <rect key={b.priceMilli} x={Y_AXIS_W}
    y={b.y} width={b.w} height={b.h} className="fill-ink-muted"
    fillOpacity={VP_FILL_OPACITY} />)}</g>`
    (R1:`fill-ink-muted` = EnergySub 量柱同 token,前景圖形語意、深底可見;
    `fill-line` 是格線色,乘透明度後與底色幾乎同值,截圖取證通道會拍不出東西)。
  - toggleDefs 加 `["vp", "量分佈"]`(與 vwap/cdp/ma 同列同樣式)。
- **UI 可指認表述(SC-3 驗收)**:個股頁分時圖繪圖區左側出現一組自左緣價位帶向右延伸的
  水平半透明長條,長度比例 = 該價位當日成交量;圖表工具列多一顆「量分佈」toggle,
  預設亮起,點擊後長條整組消失。

## 測試對應

- SC-1:fixture 300 筆 ticks → `fromSnapshot` 後 `ticks.length === 200` 且 vp 總張 =
  300 筆合計;`applyTick` 增量 = bucket 累加;`p: 0` tick 不入 vp;side 拆分正確。
- SC-2:域過濾 / 域內 max 歸一 / 退化域 h clamp / 空輸入 / 降冪排序。
- SC-3:toggle 預設開 → `vp-bars` 內 rect > 0;`set("vp", false)` 後 rect 消失;
  useChartToggles 舊存檔(無 vp 鍵)load 後 `vp === true`。
- jsdom 紀律照 `frontend-testing` skill(無 jest-dom;fireEvent;colocated)。

## 邊界

- ChartStatic 是 memo:vpBars 必經 useMemo,識別穩定(W-5)。
- hover crosshair 事件模型不動(onMouseMove + onClick,SKILL 觸控條款)。
- `fill` 用 class 不用 pattern(CLAUDE.md §8 SVG pattern 坑不適用 — 單色 rect)。

## SC-4 gate(R2)

`npm test` + `npx tsc -b` + `npx eslint src`(cwd = frontend/)全綠。
既有 fixture 的 `as unknown as StockAccum` 硬轉不會被 tsc 抓 → R2 的兩個測試檔 fixture
必補 `vp`,**消費端不得用 `?? new Map()` 吞**(真漏建 vp 要炸不要靜默空圖)。

## Known Risks

- **「全日」的上界 = 後端 tick deque 20,000 筆**(stock_state.py `_TICKS_MAXLEN`;
  熱門股單日 ~6.2k,漲停攻防股更高)— 超界時 VP 為「最近 2 萬筆」,早盤量靜默缺角。
  接受(零後端改動拍板);VP 總張 = 說明列三數和的一致性測試可間接暴露。
- **窄容器資訊列截斷**(R7;[amendment: Phase 6 實測方向更正]):1280px 下被
  ellipsis 截斷的是**首欄**(外/內盤統計)非尾欄;900px 的中央欄塌縮為既有四欄版面
  行為,皆與 VP 無關。接受;證據 `evidence/SC-3_vp-narrow.png`。
