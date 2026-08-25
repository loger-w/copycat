# mod/signal-param-parity — verification(A8)

分支 `mod/signal-param-parity`(worktree `C:\side-project\copycat-wt-a1`,自 origin/master `7d50c948` 切)。
後端 code 零改動(只加測試斷言 + fixture 兩鍵);前端 lib + Dialog。

## 1. commits

| # | 類 | subject |
|---|---|---|
| 1 | 🟢 | `test(signals): [red] parity 補完 —— fixture 加 int_keys / cooldown,前端 parity 三案,Dialog 整數欄一案(review A8)` |
| 2 | 🔴 | `fix(frontend): 訊號規則整數鍵送出前擋並指出欄位;預設值 / 冷卻界併進 lib 同表(review A8,#101 parity 補完)` |
| 3 | 🟢 | `test(frontend): [red] 冷卻秒數非整數擋 / 冷卻預設值落界 / 預設值字面 golden / 整數鍵去重(review A8 round-1)` |
| 4 | 🔴 | `fix(frontend): 冷卻秒數送出前擋非整數;冷卻預設值併進 lib(review A8 round-1 SP1 / SP3)` |
| 5 | chore | artifacts + CLAUDE.md §4 契約條目擴寫 |

commit 邊界偏離(記錄):#2 含純搬移(PARAM_DEFAULTS / COOLDOWN → lib);紅測試已 import 自 lib,拆開留壞 commit。

## 2. 紅態證據(TDD)

`npx vitest run src/lib/signal-param-parity.test.ts src/components/stock/SignalRulesDialog.test.tsx`(實作前)→
**4 failed, 27 passed**:parity「整數鍵集合」「冷卻界」「預設值落值域」(`integer` / `default` / `COOLDOWN_*` 尚不存在)
+ Dialog「整數欄填 2.9 → 須為整數」。後端 `tests/test_signal_rules.py` 補兩個斷言(`INT_PARAM_KEYS` / `COOLDOWN` 對
fixture)在現碼下綠(122 passed)= 鎖。

mutation(實作後):`rearm_ticks` 改 `integer: false` + `default: "2.9"` → **3 failed**(parity 整數鍵案 / Dialog 整數欄案 /
既有「預設 300 payload」案);`git checkout` 還原 → 5 passed。
記帳:首次 mutation 用 sed 在 `}` 後加 `// MUTANT` 把逗號一起註掉 → vitest「no tests」(語法錯誤不是紅);重做不加尾註解。

review round-1 紅態:「冷卻秒數填 300.5 → 須為整數」與「COOLDOWN_DEFAULT 落界整數」**2 failed**;字面 golden 與去重在現碼下綠 = 鎖。
實作後目標兩檔 33 passed。

## 3. 完成前 gate

| gate | 結果 |
|---|---|
| `npm test`(收修後全量) | **148 files / 2797 passed**(基準 2791 + 6:parity 4 + Dialog 2) |
| `npx tsc -b` / `npx eslint src` | exit 0 / exit 0(收修後重跑) |
| `npx react-doctor@latest --scope changed --no-telemetry` | No issues found(4 files,收修後重跑) |
| `pytest -q`(全量) | **3053 passed, 1 skipped**(178.50 s;與 A1 出貨後基準同 —— 本輪只在既有案內加斷言) |
| `ruff check` / `pyright` | All checks passed / 0 errors |
| `copycat validate` | 未重跑:replay 程式碼與 fixture 皆零改動(A1 那輪 42/42 仍為基準) |

## 4. 真實環境節

純表單驗證邏輯;jsdom 案已覆蓋「填 2.9 → 文案 + 零送出 → 改 2 可送」整條路。未另起瀏覽器截圖:
UI 差異只有一句新文案(與既有「須在 a–b 之間」同形同位),過目點見 §5。

## 5. 需 user 過目

訊號規則窗:「重新武裝 tick 數」/「窗內最少張數」/「當日最少張數」填小數 → 儲存時橫幅印「<欄名>須為整數」、
零送出;其他欄填小數照常。「新增規則」表單初值與改動前逐字相同(2 / 300 / 1.5 / 60 / 3 / 60 / 5 / 100 / 500)。

## 6. review round 1

(見 `code-review-round-1.json`)
