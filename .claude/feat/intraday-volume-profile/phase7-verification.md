# phase7 verification — intraday-volume-profile(HEAD 3826ffa)

fresh 證據(主 agent 本 session 親跑,HEAD 未再變):pytest 1822 passed /
vitest 1157 passed / tsc 0 / eslint 0;截圖三張(subagent DOM+目視雙證)。

| SC | 實作檔案:行號 | 自動化測試 | real-env 證據 | regression 抽樣 |
|---|---|---|---|---|
| SC-1 vp fold(全量/增量/窗/防禦) | stock-accum.ts:104-127(foldVp)/:158-162(fromSnapshot)/:205-207(applyTick) | stock-accum.test.ts vp 節 9 條(含 R3 一致性鎖、NaN 鍵、F4 截斷 characterization) | 截圖 41 根 bar = prod 全日 tick 折出 | tape 截斷不變(ticks ≤ 200 斷言);後端 pytest 1822 零觸碰 |
| SC-2 buildVpBars 幾何 | volume-profile.ts 全檔(置中帶 amendment 後) | volume-profile.test.ts 13 條(域過濾/歸一/置中/端點半高/高密度兩段/NaN 防禦/真幾何) | bar 寬 0.3~159.3 ∝ 量(DOM 實證) | — |
| SC-3 畫面 + toggle | StockIntradayChart.tsx:218-240(vp-bars g)/:524-526(useMemo)/:624-630(toggleDefs);useChartToggles.ts:11-19 | StockIntradayChart.test.tsx VP 節 5 條 + useChartToggles 舊存檔測試 | 截圖:`evidence/SC-3_vp-default-on.jpg` / `SC-3_vp-toggled-off.jpg` / `SC-3_vp-narrow.png` + **user 過目待列收尾回報** | SC-5「主圖無量 bar」不受影響(drawnRects 白名單已免疫);console 隔離實驗證 VP 零新增 error |
| SC-4 零退化 | — | vitest 1157 / tsc 0 / eslint 0 / pytest 1822(automated-verification.md) | — | 既有 toggles 行為(bb 升級語意)測試綠 |

無 FAIL → 不觸發分流。SC-3 real-env 欄 = `截圖 + user 過目`(允許例外之 UI SC 形式)。
