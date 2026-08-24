# N032 useChartToggles.set 包 useCallback — 驗證(2026-08-24)

## 範圍
next-time N032(user 2026-08-24 拍板「直接排來做」;原 plan review R9 deferred)。
單檔單點:`frontend/src/hooks/useChartToggles.ts` — `set` 由 function 宣告改
`useCallback([], …)`,行為零差異(deps 空陣列前提:load/persist module-level、
setToggles React 穩定)。S 級主 session 直做(feat-phase3 實作模式節)。

## 證據
- `npx tsc -b`:PASS(無輸出)
- `npm test -- --run src/hooks/useChartToggles.test.ts`:14 passed
- `npm test -- --run` 全套:**2532 passed**(0 failed)
- `npx eslint src`:clean
- `npx react-doctor@latest --scope changed --no-telemetry`:無新增 finding

## 行為不變論證
`set` 的函式體逐字未動(重讀 localStorage → persist → setState);只有函式身分
從「每 render 新建」變「穩定」。現況無任何 memo 節點以 `set` 為 prop 比較依據
(N032 原文:目前零受益),故渲染結果與互動路徑零差異。

## round-1 review 後補(Z2/Z3,0 P0/P1)
- Z2:`GroupGridView.tsx` GroupCard 註解改口(舊理由「每 render 新 identity」失效,正確理由「卡片只讀」留任)。
- Z3:`useChartToggles.test.ts` 補身分穩定 lock(同 instance rerender ×2,含 set 呼叫後)。
- 複驗:tsc PASS / 觸及兩測試檔 71 passed / eslint clean。findings 落 `code-review-round-1.json`。
