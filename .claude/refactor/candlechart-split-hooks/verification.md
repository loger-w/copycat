# verification — refactor/candlechart-split-hooks(2026-08-11)

## 自動化 gate(worktree `.claude/worktrees/candlechart-split-hooks`)

| 項 | 指令 | baseline(origin/master) | after | exit |
|---|---|---|---|---|
| 前端測試 | `npm test` | 110 檔 / **1722 passed** | 110 檔 / **1727 passed**(+5 = 3 characterization + TC-1/TC-2) | 0 |
| 型別 | `npx tsc -b` | 0 | 0 | 0 |
| Lint | `npx eslint src` | 0 | 0 | 0 |
| doctor | `npx react-doctor@latest --scope changed --no-telemetry` | (CandleChart 在全掃有 no-giant-component + index-key 存量) | **3 issues,全為 no-array-index-as-key 存量**(triage 已裁 SVG 幾何位置式 key = FP;diff 零 `key=` 行變動佐證);**no-giant-component 消失** | — |
| 後端 | `.venv\Scripts\python -m pytest -q`(worktree root,主 tree venv) | — | **2563 passed, 3 skipped** | 0 |

pyright / ruff / validate:diff 零 `.py` 觸及(`git diff origin/master --stat` 僅 4 個 frontend 檔),沿 baseline。

## Mutation 抽驗(characterization 非 vacuous;Edit 成對,無 git checkout)

| Mutant | 預期紅 | 結果 |
|---|---|---|
| A:drag move 移除 `setHover(null)` | 拖曳中清十字線 | 恰紅該條(3 mutant 同跑:3 failed / 47 passed) |
| B:移除 `e.button !== 0` guard | 非左鍵不拖 | 同上 |
| C:up 不卸 mousemove listener | mouseup 後不跟隨 | 同上 |
| D:`panBy(startVp,…)` → 累加式 `(v)=>panBy(v,…)` | 絕對位移不漂移(TC-1) | 恰紅該條(2 mutant 同跑:2 failed / 50 passed) |
| E:移除 `e.preventDefault()` | wheel preventDefault(TC-2) | 同上 |

還原後 52/52 綠、`git grep MUTANT` 零殘留。

## 真實環境

行為零變 + 純前端結構搬遷,可觀察行為全數由元件層測試釘住(hover / 縮放 / 平移 / 延伸 /
memo 結構未動 — diff 中 JSX 與 ChartStatic/XAxisLabels 零改動)。未另開 vite 目視
[auto-default: 略過瀏覽器目視 | reason: 純 🔵 JSX 零變動,diff 可機械證明渲染層未動;
worktree 起 dev server 需另佔 8721 proxy,ops-discipline 盤中紀律下收益為零]。

## 動機核對(可量化改進)

- CandleChart.tsx **766 → 670 行**;主體函式 ~313 → ~217 行。
- viewport(state+wheel+drag+延伸)與 hover 事件層各自成 hook(102 / 34 行),
  未來 K 線迭代(rAF 節流、視窗捷徑)有明確落點。
- react-doctor no-giant-component(CandleChart 條)於 changed-scope 掃描消失;零新增 finding。
