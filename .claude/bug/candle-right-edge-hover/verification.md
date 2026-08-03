# Phase 6|自動化驗證(2026-08-03 12:31–12:40,全綠)

| # | 指令 | cwd | exit | 結果 |
|---|------|-----|------|------|
| 1 | `npx vitest run` | frontend/ | 0 | **895 passed (895)** |
| 2 | `npx tsc -b` | frontend/ | 0 | 0 errors |
| 3 | `npx eslint src` | frontend/ | 0 | 0 issues |
| 4 | `.venv\Scripts\python -m pytest -q` | repo root | 0 | **1481 passed**(第一輪 1 failed = 既有日期依賴測試,d84c440 修畢後重跑全綠;見 repro.md) |
| 5 | `.venv\Scripts\python -m ruff check copycat tests` | repo root | 0 | All checks passed |
| 6 | `.venv\Scripts\python -m pyright` | repo root | 0 | 0 errors, 0 warnings |

- `copycat validate` **未跑**:diff 不觸及 replay / engine / backtest(僅 frontend/src/lib
  一行 + 兩個測試檔),且 validate 需先跑 four/five 兩份 replay(沿 index-river-chart 前例)。
- 驗證指令皆未接管線後綴,exit code 單獨檢查(§8 教訓)。

# Phase 8|反向驗證

revert f226354 → candle.test.ts 1 failed | 38 passed(紅回來的正是新測試)→ 還原 → 39 passed。

# Phase 7|真實環境驗證(2026-08-03 12:41–12:42,PASS)

- 執行:dispatch opus subagent(auto-verify「UI 畫面驗證」節,2026-08-03 制)、chrome-devtools
  MCP、http://localhost:5174(vite dev → 跑著的 :8721,盤中未起第二台後端)。
- 標的 6207(盤中即時)、1分K 240 根:右緣 hover(rect.right − 0.5)十字線出現,
  垂直線 x=1397.08 = 最後一根中心,讀數列顯示 12:41 那根 OHLC;右緣 0.01/0.5/1/2px
  四點全命中最後一根,左移 30px 連續映射到 12:39 那根(非 clamp 硬吃)。
- 左側對照組(rect.left + 10)→ 第一根,機制正常;mouseleave 後十字線元素歸 0
  (陰性對照,排除「常駐參考線」假陽性)。
- 截圖:`evidence/SC-right-edge-crosshair.png`。console 無新增 error(既有 StrictMode
  WS warn ×5 與 favicon 404 與本修復無關)。
- **user 過目**:收尾回報列出可指認表述 + 操作路徑(雙層之第二層)。
- 收尾後全套重跑(P2 補強後):vitest 898 passed / pytest 1481 passed(2026-08-03 13:0x)
