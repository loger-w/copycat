# progress ledger — stkfut-contracts

plan: .claude/feat/stkfut-contracts/implementation/PLAN.md(v2)
branch: feat/stkfut-contracts(start 50b463bc)

| task | 狀態 | commits | review |
|---|---|---|---|
| T1 合約發現(fixture/parser/catalog/route) | done | 1f802748 [red] / 1d85f03f [green] | |
| T2 乘數 + 下單閘(map v2/lookup/mapping/capital_api) | done | 41285a9a [red] / 8bfa81f1 🔴 [green] | |
| T3 引擎/資料源(路由/試撮/轉移表/夜盤) | done | 943aea53 [red] / 2bdad6c3 [green] | |
| T4 切換 API(?contract= 驗證) | done | 17fd1603 [red] / 6be0d188 [green] | 2304 綠;catalog None → 503 分流 accept |
| T5 前端幾何/圖表態 | done | 6a2eb00d 🔵 / 67699f96 [red] / 5854a1b1 [green] | 1478 綠;mutation 反證 ×2 |
| T6 前端資料流 | done | 05db930a [red] / c0cd8496 [green] | 1498 綠;render 期重置防一拍 400 |
| T7 下單面(LadderView/StkfutLadder/RightRail) | done | 3d33d374 🔵 / 4f5c6dfc [red] / 4fa8d373 [green] | 1519 綠;ETF 前端判準(股號開頭 0)待 Phase 4 覆核 |

main gate 備註:T3 偏離 4(合約鍵 no_data 廣播例外)入 SC-7 措辭;T7 偏離 1 為 Phase 4 焦點。
