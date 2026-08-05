# PLAN — 分時圖 VP(condensed;design v2 對應;v2 = impl-spec review R1-R8 修入)

任務順序:T1(stock-accum)→ T2(volume-profile lib)→ T3(toggles + 元件 + fixture 遷移)。

## T1 `frontend/src/lib/stock-accum.ts` + `stock-accum.test.ts`

- `export interface VpCell { t: number; o: number; i: number }`
- `StockAccum` 加必填 `vp: Map<number, VpCell>`
- 私有 `foldVp(vp, t, p, q, side)`(design v2 SC-1 snippet):`p <= 0` 跳過;
  `minuteKey(t)` 窗外([X_START_MIN, X_END_MIN] 外)跳過;`snapDown(p)` bucket;
  cell 重建不就地改。窗常數自 `@/lib/stock-intraday-svg` import(單一定義;
  R4 已實查無 runtime 循環:svg 檔對 accum 是 `import type`(編譯期抹除)、
  runtime 鏈 accum→svg→stock-tick 無環 — **不授權任何常數搬遷 / 新檔**)
- `fromSnapshot`:對 `snap.ticks ?? []` 全量 fold(slice 前來源);`applyTick`:
  `new Map(acc.vp)` 後 fold 本筆
- 失敗測試:`fixture 300 筆 → ticks.length===200 且 vp 總 t=300 筆合計`、
  `applyTick 增量累加`、`p<=0 不入`、`窗外 tick 不入(t="08:59:59.000"/"13:31:00.000")`、
  `side 拆分 o/i/其餘只進 t`、
  **R3 一致性鎖**:minutes 與 ticks 同源構造(同批 tick 聚合,含窗外 + neutral)→
  `Σ vp[*].t === sideSummary(acc.minutes) 的 outer+inner+unch`(同時鎖「窗同尺」與
  「後端 20k 截斷會讓兩數岔開」— design R5/R4 指定的測試鎖)

## T2 `frontend/src/lib/volume-profile.ts`(新)+ `volume-profile.test.ts`(新)

design v2 SC-2 全簽名照抄:`VP_MAX_W_RATIO = 0.22`、`VP_FILL_OPACITY = 0.25`、
`VpBar { y, h, w, priceMilli, total }`、`buildVpBars(vp, g, width)`。
- 域過濾(閉區間外跳過)→ 域內 max t 歸一(**`maxTotal = Math.max(1, ...)`,R8:
  plotWidth/energyFrom 同紀律,禁 NaN 幾何**)→
  `dist = toY(p) − toY(min(p+tickOf(p), yTop))`、`h = max(1, dist × 0.85)` →
  `w = t/maxTotal × plotWidth(width) × VP_MAX_W_RATIO` → priceMilli 降冪排序;
  空/全域外 → []
- 失敗測試:域過濾 / 域內 max 歸一(域縮放後滿寬)/ 退化域 clamp 1 /
  **高密度域兩段式(R6)**:(a) 合成 dist≈1.19(域 200 檔、plotH 238)→
  `h ≤ dist && h ≥ dist×0.8`(相鄰不重疊);(b) dist<1 → `h === 1`
  (clamp 生效,亞像素重疊為刻意接受下界)/ 空輸入 / 降冪排序 /
  w 上限 = plotWidth × 0.22 / **t 全 0 → 無 NaN(w 有限)**(R8)

## T3 toggles + 元件 + fixture 遷移

- `hooks/useChartToggles.ts`:`ChartToggles` 加 `vp: boolean`;`DEFAULTS.vp = true`;
  **不 bump TOGGLES_VERSION**(舊存檔無鍵 → spread 自然預設)
- `components/stock/StockIntradayChart.tsx`:
  - `vpBars` useMemo(design v2 呼叫式,width 用既有 `mainW` = `MAIN.width`,不另宣告)
  - `ChartStatic` 新 prop `vpBars: VpBar[]`,渲染插 y 格線後、areaPolygon 前:
    `<g data-testid="vp-bars">` + 每根 rect **`data-testid="vp-bar"`**(R2:讓既有
    drawnRects 類過濾式有得抓)`x={Y_AXIS_W}` `className="fill-ink-muted"`
    `fillOpacity={VP_FILL_OPACITY}`
  - toggleDefs(物件陣列,R7):加 `{ key: "vp", label: "量分佈", available: true }`,
    並把 key 字面聯集 `"vwap" | "cdp" | "ma"` 擴成含 `"vp"`
- 既有測試遷移(R1/R5,**獨立 commit 無 TDD tag**,以下 assertion 事前標『該變』):
  - `as unknown as StockAccum` fixture 補 `vp: new Map()` **三站點**:
    `StockChart.test.tsx:22` / `StockPage.test.tsx:33`(ACCUM)/ `StockPage.test.tsx:154`
    (accumWithTicks);`as StockAccum` spread 衍生三處(:186/:215/:268)不必動。
    消費端不准 `?? new Map()` 吞
  - `useChartToggles.test.ts`(**既有檔**):local DEFAULTS 補 `vp: true`(6 處
    toEqual 連動)+ :34 與 :124-130 兩處硬列鍵集補 `vp` — 共 8 條 assertion,
    非行為契約變更,事前標記(鐵則 E 合規)
- 失敗測試(`StockIntradayChart.test.tsx`;R2:**另造獨立 fixture 走 fromSnapshot**,
  ticks 落 09:00-13:30 且價格在既有域 [2_090_000, 2_550_000] 內 — 複用 ACCUM snapshot
  參數只換 ticks,**不動共用 ACCUM**,既有 SC-5 `drawnRects === 0` 斷言因此不受影響):
  預設(vp: true)render → `[data-testid="vp-bar"]` 數 > 0;toggles.vp=false → 0;
  `useChartToggles.test.ts` 追加:舊存檔無 vp 鍵 → load 後 `vp===true`

## 驗證 gate(Phase 5)

cwd = frontend/:`npm test` + `npx tsc -b` + `npx eslint src` 全綠。
後端零改 → python gate 以全案 pytest 快掃一次確認零觸碰即可(worktree venv 絕對路徑)。

## 非自動化交付項

- SC-3 AI 截圖對照(常寬 + 窄寬各一,R7)+ user 過目;檔名含 SC-3 落 evidence/。
- 截圖需真頁面:盤後 snapshot 有全日 tick;起 vite dev(proxy 指 prod :8721,零新增訂閱,
  盤中亦安全 — CLAUDE.md §8 紀律)。
