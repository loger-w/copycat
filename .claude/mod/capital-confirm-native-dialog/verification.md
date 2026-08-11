# Verification — mod/capital-confirm-native-dialog(2026-08-11)

## 自動化 gate(全綠;task byml5fm11 baseline / b27a07c40 final / bkyze4mdf backend)

| Gate | 指令 | 結果 | exit |
|---|---|---|---|
| 前端測試 | `npm test`(frontend/) | **110 檔 / 1722 passed**(baseline 1710 + 新增 12) | 0 |
| 型別 | `npx tsc -b` | OK | 0 |
| Lint | `npx eslint src` | OK | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | **No issues found**(SC-6:prefer-html-dialog 消失、零新增) | 0 |
| 後端回歸(零 .py diff,保險) | `.venv\Scripts\python -m pytest -q` | 2566 passed | 0 |
| ruff / pyright | 同 CLAUDE.md §1 | All checks passed / 0 errors | 0 |
| `copycat validate` | **skip** — 零 .py diff,replay 引擎未觸及;validate 前置需重跑 four/five 兩份 replay,對純 frontend 改動屬純儀式 | — |

mutation 驗證 ×3(Edit 成對,MUTANT 殘留 grep = 0):
1. cleanup 加 `el.close()` → lock test「unmount 零 callback」紅(10 紅)→ 還原綠。
2. 拔確認鈕 `closedRef` → 「確認後 Esc/close 不補發 onCancel」紅 → 還原綠。
3. 拔 `e.stopPropagation()` → 「窗內 Esc 不外洩 window」紅 → 還原綠。

## 真實環境(真 Chrome,vite dev 5175 + initScript fetch-override 假 capital 資料;
後端 8721 未起 — 沿 ladder-position-pnl fake-positions 先例;prod server 不受本改動影響)

路徑:個股 tab → 交易面板「委託」→ 假活單(2330,env=prod)→ 刪單 → 確認窗。
**vite dev = StrictMode 全站包 → 窗正常開啟即實證 R1 `!el.open` guard(dev double-invoke 不炸)。**

| 驗證點 | 證據 | 結果 |
|---|---|---|
| SC-1 真 showModal 路徑 | `dialog[open]` `isModal:true` | PASS |
| SC-3 初始 focus = 取消鈕 | `activeElement: BUTTON:取消`, `activeInsideDialog:true` | PASS |
| SC-4a 背景不可點 | 刪單鈕座標 elementFromPoint → DIALOG(backdrop 蓋住) | PASS |
| SC-4b 背景不可 focus | 對背景刪單鈕 `focus()` → activeElement 仍取消鈕 | PASS |
| SC-4c 關窗後背景復原 | Esc 後 elementFromPoint → 刪單鈕(可點) | PASS |
| SC-4d focus 歸還 | Esc 後 `activeElement === 刪單鈕`(觸發鈕) | PASS |
| SC-2 Esc = 取消 | Esc 後窗自 DOM 消失、委託列仍在、零送單 | PASS |
| 白名單 3 視覺 | 截圖:置中偏差 dx0/dy0、backdrop 壓暗、danger `bg-loss` 標題列 + 正式 badge、margin computed auto | PASS |
| 未改功能抽樣 | tabs 切換 / 委託列表渲染 / 斷線 banner 降級(後端 down)皆正常 | PASS |

截圖:`evidence/SC-3_SC-4_dialog-open-danger-focus-cancel.png`(danger 態開窗 + focus)。
**user 過目層(雙層之二)待做** — 驗收點見收尾回報。

## §7 白名單逐條核對(對照 change-spec.md)

1. callback 契約:props 介面不變(`git diff` 僅 .tsx/.test.tsx 兩檔);確認/取消逐 click
   直呼(測試「渲染標題…callbacks」+「取消後補 close 不二次」鎖住)✓
2. caller 零 diff(4 檔未動,reviewer 與本地 `git diff --stat` 雙確認);unmount 零
   callback([lock] + mutation)✓
3. 視覺:danger bg-loss / dl 版式 / 按鈕配色 class 未動;遮罩 backdrop:bg-bg/85 截圖過目 ✓
4. 二次確認流程不變:窗仍必經,Esc 僅能取消(onConfirm 無任何新觸發路徑)✓
5. 既有 2 支測試一字未改(diff 零刪除行)且綠 ✓

Migration:無(props/wire 不變);可逆 = revert commits。
