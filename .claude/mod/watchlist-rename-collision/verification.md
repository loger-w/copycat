# mod/watchlist-rename-collision — verification(A4)

分支 `mod/watchlist-rename-collision`(worktree `C:\side-project\copycat-wt-a1`,自 origin/master `ae44ed23` 切)。
純前端,零後端 / 零 TC4 改動。

## 1. commits

| # | 類 | subject |
|---|---|---|
| 1 | 🟢 | `test(frontend): [red] 改名被拒 / PUT 失敗時編輯框保留、在途連按 Enter 守門(review A4)` |
| 2 | 🔴 | `fix(frontend): 改名撞名 / PUT 失敗時保留編輯框與輸入,成功回呼才關(review A4,#101 N115)` |
| 3 | 🟢 | `test(frontend): [red] 守門一定解除 —— 刪組在途改名後仍能改別組、A 在途 Escape 改 B 照送、hook onSettled 三路徑(review A4 round-1)` |
| 4 | 🔴 | `fix(frontend): 改名守門改綁單一動作 + hook 加 onSettled(必呼)(review A4 round-1 SP1 / ST-P3)` |
| 5 | chore | artifacts + next-time |

## 2. 紅態證據(TDD)

`npx vitest run src/components/stock/WatchlistManagerDialog.test.tsx`(實作前)→ **2 failed, 47 passed**:
- 「改名撞既有名 → 文案出來時編輯框仍在」:`getByDisplayValue("觀察")` 找不到(框已關)。
- 「改名 PUT 失敗(4xx)→ 編輯框保留可重試」:同上。
- 「改名成功 → 編輯框才關閉」與「在途連按 Enter」在舊碼下綠(框已關無重送路徑)= 新行為的 lock。

mutation(實作後):拔掉 `if (renameBusy) return` → 「在途連按 Enter」**1 failed**(第二發上路);還原 → 49 passed;
`grep -c MUTANT` = 0。

review round-1 收修的紅態:「A 組改名在途,Escape 後改 B 組」**1 failed**(全窗旗標吞掉 B);hook 三案在 `commit` 尚無
`onSettled` 參數下恆不呼 → 紅。「刪組在途改名(from 消失)後仍能改別組」在首版下**綠** —— 刪組成功的 `onError(null)`
巧合解除了旗標(reviewer SP1 舉的序列本身不卡,卡的條件是零回呼早退且期間無其他 settle);留作 lock 並改成不靠巧合。

## 3. 完成前 gate(worktree `frontend/`;node_modules 以 robocopy 自主 tree 複製 —— `npm ci` 因 package-lock
與 package.json 不同步(`@emnapi/*`,既有問題)拒裝,記 next-time)

| gate | 結果 |
|---|---|
| `npm test`(收修後全量) | **148 files / 2791 passed**(基準 2782 + 9:Dialog 6 + hook 3) |
| `npx tsc -b` | exit 0 |
| `npx eslint src` | exit 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | No issues found |
| 後端 gate | 未動 `copycat/` / `tests/` → 不適用 |

## 4. 真實環境節

### 4.1 AI 截圖(vite dev :5180 → prod 8721 proxy,零新增 TC4 訂閱;撞名路徑 transform 回 null = 零 PUT,不動真自選)

`evidence/rename-collision-keeps-input.png`(claude-in-chrome,真自選:選「石英」→ ✎ → 改成既有組名 `PCB` → Enter):
橫幅印「群組名稱不合法」(綠字),**編輯框仍在原列、值 `PCB`、紅框**,右欄仍是「石英」成員(3042 / 2484)。
操作後 Escape 取消改名、Escape 關窗,真自選零改動(撞名路徑零 PUT;✎ 用 `find` 取 ref 點,不用座標 —— 隔壁就是 × 刪組)。
**這張圖是 round-1 收修前的實作拍的**;收修只動守門機制(不動撞名保留框的 UI),jsdom 六案 + hook 三案覆蓋收修後行為。

### 4.2 edge / 未改功能抽查

- 撞名(既有名)→ 零 PUT + 文案 + 框留著:新案 + 既有「改名撞既有名 → 零 PUT + 錯誤文案」同時綠。
- N115 佇列視窗內撞名兩案、N118 刪組在途改名不復活:綠(白名單)。
- 「右欄 derived 值:改名失敗不留懸空」:綠 —— 失敗後框留著,右欄仍列原組成員。
- 「關閉再開 → 改名輸入框不殘留」:綠(開窗重置含守門歸零)。

## 5. 需 user 過目

改名時把名字改成既有群組名 → 錯誤文案「群組名稱不合法」出現,**輸入框留在原位、字還在**,直接改字再 Enter 即可;
改成功才收框並選中新組。在途(PUT 未回)連按 Enter 不會第二次送出。

## 6. review round 1

(見 `code-review-round-1.json`)
