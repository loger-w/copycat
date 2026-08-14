# Verification — mod/group-grid-matrix-layout

## 自動化(fix 波後 HEAD = c43c2532)

| Gate | 指令 | 結果 | exit | 證據 |
|---|---|---|---|---|
| frontend 測試 | `npm test`(frontend/) | 1868 passed(112 files) | 0 | evidence/gate-vitest.txt |
| frontend 型別 | `npx tsc -b` | 0 errors | 0 | evidence/gate-tsc.txt |
| frontend lint | `npx eslint src` | 0 issues | 0 | evidence/gate-eslint.txt |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | 無新增 finding | 0 | evidence/gate-doctor.txt |
| backend 測試 | `.venv\Scripts\python -m pytest -q` | 2662 passed | 0 | task b9ssfromu(本輪未動 .py,20f00d00 前跑,後續 commit 均 frontend-only) |
| backend lint | `ruff check copycat tests` | All checks passed | 0 | 同上 |
| backend 型別 | `pyright` | 0 errors/warnings | 0 | 同上 |
| golden gate | `copycat validate`(four/five replay 先跑) | 42/42 PASS | 0 | task b3hxnjbh9 |

Baseline(開工前):frontend vitest 1851 passed 全綠;本輪淨增 17 條測試。

## 真實環境(UI SC 截圖對照)

環境:fake-source 側車(`evidence/fake_server.py`,port 8721,`neutralize_external_env()`
+ 隔離 watchlist tempdir,零 TC4/ZMQ — ops-discipline 盤中安全通道)+ vite dev 5173。
側車 health 回 `git_sha=c43c2532` = 驗的就是本輪 HEAD。

截圖對照:dispatch subagent(opus)逐 SC 核對 — **5/5 PASS**:

| SC | 判定 | 截圖(evidence/) | 依據(實測) |
|---|---|---|---|
| SC-3 pill 列 | PASS | SC-3_pill-row-zoom.png | 「群組」前置字 + 四顆 pill,選中 accent;全頁群組區零 select;與 view pill 同語彙 |
| SC-1 2 檔 | PASS | SC-1_2cards.jpg | grid-cols-2,rows 計算值 560.5px×2,卡片 868×561 佔半寬半高,下列留空 |
| SC-2 4 檔 | PASS | SC-2_2x2_4cards.jpg | 2×2 填滿,卡高 = 中區 1129 的一半;svg 實測 850×519;document 與格線皆無捲軸;stroke-width 維持 1.4px |
| SC-1 6 檔 | PASS | SC-1_6cards_3x2.jpg | grid-cols-3 × 2 列(576px×3 / 560.5px×2) |
| SC-1/A-1 17 檔 | PASS | SC-5_17cards_tall-viewport-no-stretch.jpg / SC-5_17cards_short-viewport-scroll.png | 固定 4 欄,rows `122px×5` 基準高不被 stretch;高視窗留白於下、矮視窗(clientH 478 < scrollH 642)格線內出捲軸 |

Console:僅存量 `two children with the same key, 0` error(頁面載入起即以 ~1s 節奏刷,
早於進入群組檢視;memory 已列 next-time 的 duplicate-key 存量項),本輪零新增 error。
備註:矮視窗一張因 claude-in-chrome resize 對最大化視窗 no-op,改用 devtools MCP
獨立實例(1600×620)取得;無資料碼卡片顯示「回補中…」佔位(fake source backfill
空 + backfilling 旗標,佔位渲染路徑同屬本輪 grow 驗證面)。

註:SC-1 >16 檔的「右側出捲軸」判準經 review A-1 修正為:「卡片維持基準高;
內容超出格線高才出捲軸(視窗高時留白在下方,不等量撐高)」。

## 白名單逐條(自動化層)

1-10 全數由既有測試覆蓋且綠(GroupGridView 41 / StockPage 49 / memo 2 /
MiniIntradayChart 13,含 lock 補強);#7 寫入時機依 A-3 amendment 為刻意改變,
新語意有 lock。零請求 gate(#2)、memo(#8)、幾何(#9)測試未改動且綠。

## Migration 可逆性

N/A(無 API / 資料格式 / localStorage 語意遷移;STOCK_GROUP_KEY 同 key 同值)。

## Phase 7 goal 核對(重讀 change-spec.md 逐條)

| 項 | 實作 | 測試 | real-env |
|---|---|---|---|
| SC-1 矩陣 | GroupGridView.tsx gridShape + 容器 cn(gridShape) | gridShape 全表 12 條 + 元件級 2×2/17 檔 2 條(綠) | SC-1_2cards / SC-1_6cards_3x2 / SC-5_17cards ×2 PASS |
| SC-2 高度 | grow+h-20(svg/佔位)+ vectorEffect + flex-1/content-start | 高度 class 2 條 + lock(佔位 grow/vector-effect 全覆蓋) | SC-2_2x2_4cards PASS(卡高=中區半、svg 850×519、stroke 1.4) |
| SC-3 pill | role=group aria-label 容器 + aria-pressed pill | 改寫 4 條 + aria 反向 + localStorage 寫入 lock | SC-3_pill-row-zoom PASS |
| 白名單 1-10 | — | 既有測試未動全綠(GroupGridView 41/StockPage 49/memo 2/Mini 13);#7 依 A-3 amendment 刻意改變+lock | 截圖抽核:卡片三態佔位/報價欄如舊 |
| Migration 可逆 | N/A(無遷移;STOCK_GROUP_KEY 同 key 同值) | — | — |

rollbacks:無。既有測試紅名單相符:該紅 4 條已依 TDD 改寫;不該紅零誤傷(baseline 1851 → 1868,全綠)。
