# refactor/live-server-simplification

來源:docs/next-time.md「2026-07-18 txo-aggregate-pnl Phase 4 P2 彙總」第一條(live/server simplification 五小項)。
自主模式(/auto),退出條件 = 既有測試前後皆全綠;行為零變更。

## 測試盤點(test-inventory)

Baseline(refactor 前):pytest 607 passed / vitest 61 passed(2026-07-20)。

| 目標 | 既有保護 | 縫隙 → 處置 |
|---|---|---|
| aggregate.snapshot call/put 求和 | tests/live/test_aggregate.py 對 call_net_qty/put_net_qty 精確值多處斷言 + txo_golden fixture | 足夠 |
| ConnectionBadge label/tone | label 3 例(live/backfilling/WS broken) | tone class 與 unknown-status fallback 無斷言 → 補 characterization |
| pnl-svg curvePath/areaPaths | curvePath 精確字串;areaPaths 僅結構(含 Z、profit≠loss) | areaPaths 精確輸出無釘 → 補 characterization |
| engine._run_handover 狀態轉換 | live 終態 + snapshots stream on-change + self-heal 重跑 | degraded 路徑無測;抽取為 1:1 機械替換(status 賦值+mark 同序),判定既有保護足夠,不另補(記錄於此供 audit)[auto-default: 不補 degraded characterization | reason: 模擬 buffer overflow 成本高,抽取為同序機械替換,風險極低] |
| MetricsBar t null 檢查 | 格式化值 + DASH(max_profit/beps/spot_pnl null) | totals: null 分支無測 → 補 characterization |

## 步驟(每步單獨綠 + 單獨 commit)

0. 🟢 characterization ×3(ConnectionBadge tone/fallback、areaPaths 精確 path、MetricsBar totals null)
1. 🔵 aggregate.snapshot:call/put 求和雙迴圈併單趟
2. 🔵 engine:抽 `_set_status(status)`(賦值 + `_mark_changed` 集中)
3. 🔵 ConnectionBadge:STATUS_LABEL/STATUS_TONE 併單一 STATUS config
4. 🔵 pnl-svg:抽共用 line path helper(curvePath 與 areaPaths 內層同構消除)
5. 🔵 MetricsBar:totals 提前解構,消除重複 `t ?` 檢查

每步 diff 預估 < 30 行,非大型 refactor → 不 dispatch refactor-plan-reviewer。
