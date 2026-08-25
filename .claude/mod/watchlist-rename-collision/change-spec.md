# mod/watchlist-rename-collision — change-spec(A4:#101 N115 改名撞名輸入靜默消失)

需求原文 = `docs/superpowers/specs/2026-08-25-do-batch-review.md` §2.3 Spec 1、§5 A4:
「撞名時保留編輯框(`setRenaming(null)` 移到成功回呼)+ 鎖」。`/auto` 鏈式第一批第 2 條。

---

## §0 現況 vs 目標

| 面 | 現況(`WatchlistManagerDialog.tsx::submitRename`) | 目標 |
|---|---|---|
| 撞既有名 | eager 只擋保留名 / 空白;其餘無條件 `setRenaming(null)` 再 `commit(transform)`;transform 撞名回 `null` → 佇列**非同步** `onError("BAD_GROUP")` → 文案出來但編輯框已關、輸入消失 | 編輯框**只在成功回呼**關;被拒 / PUT 失敗時框與輸入留著,使用者直接改或重試 |
| PUT 4xx | 同上:框已關,文案出來 | 框留著可重試 |
| 成功 | 框關、`setSelected(new)` | 不變(成功回呼內關框 + 選中) |
| 在途重送 | 框已關,不可能重送 | **新守門** `renameBusy`:在途期間 Enter 忽略;任一發結果回來(`onError` 任何值 / `onDone`)解除 |

`[auto-default(首版,review round-1 撤回): 守門解除點放在共用 `onError` | reason(當時): 拒絕路徑只有一條,
加回呼要改 hook 契約]` → **撤回**:reviewer 指出佇列有三條零回呼早退(深比對零 PUT / 世代作廢 / 基底未載入),
全窗旗標會永久卡死;「任一發 onError 都解除」又反過來讓同一改名在途重送。
`[auto-default(round-1 收修): hook `commit` 加 optional 第三參數 `onSettled`(`.finally` 必呼),守門改記 `from` key
| reason: 向後相容的內部 hook 簽名擴充(三個既有 caller 零改動),不動對外 API / 資料格式,可逆;綁 key 順帶收掉
「A 在途、Escape 改 B 被吞」]`

`[auto-default: 「新增群組」輸入框仍 eager 清空(不動) | reason: review A4 只點名改名;新增組的清空是
#101 verification §5.3 已申報的留尾,且清空同時是它的重送防護(改成留著要另設守門),另立一輪]`

## §1 白名單(caller map)

- `submitRename` caller:改名輸入框 `onKeyDown` Enter(唯一)。`setRenaming` 的其他寫點:Escape 取消、
  ✎ 進入編輯、開窗重置 —— 全部不動。
- `useWatchlistCommit({ onError })`:本檔唯一 caller 形狀改為包一層(`setLocalError` + 解除守門);hook 本身零改動。
- 既有測試白名單(不得紅):`WatchlistManagerDialog.test.tsx` 全檔 —— 特別是「改名撞既有名 → 零 PUT + 錯誤文案」、
  N115 兩案(佇列視窗內撞名零 PUT + 文案)、N118(刪組在途改名不復活)、「右欄 derived 值:改名失敗不留懸空」、
  「關閉再開 → 改名輸入框不殘留」;`WatchlistSidebar.test.tsx` / `useWatchlistCommit` 相關全檔(hook 零改動)。
- 行為保留:撞名仍零 PUT + BAD_GROUP 文案;成功後 `setSelected(to)`;開窗重置四件事(+ 守門歸零)。

## §2 backward compat

前端內部 UX;零 API / 資料格式 / hook 契約改動。可觀察差異:被拒或失敗時編輯框留著(舊:關掉);
在途 Enter 被忽略(舊:框已關無此路徑)。

## §3 seams

`WatchlistManagerDialog.test.tsx` 新 describe「改名被拒時保留編輯框(review A4)」四案:撞名保留框 / 4xx 保留框且可重試 /
成功才關框(既有行為 lock)/ 在途連按 Enter 只一筆 PUT 無假錯。

## §4 review round 1 逐條處置

### Standards(無 hard、無 P1/P2)
- **ST1 P3 解除點放共用 onError 有真窗口(別的動作成功提前解除)** — **接受**:與 SP1 同根因,改 per-action `onSettled` + key。
- **ST2 P3 Escape 不清守門 → 在途 Esc 後改別組被吞** — **接受(變形)**:不在 Escape 清(清了同一組又能重送),改守門綁 `from`
  key,別組本來就不擋;測試「A 在途 Escape 改 B 照送」釘住。
- **ST3 P3 Duplicated Code:`gatePuts` / `releaseOk` 同檔第三份** — **申報(留尾)**:抽共用要動既有兩個 describe(白名單外的
  測試碼),本輪不擴 scope;記 next-time。
- **ST4 P3 守門無 UI 反映(在途 Enter 純靜默)** — **申報**:窗口 ≤ 一趟 PUT;a11y 不做(user 08-24 拍板);記錄不動。

### Spec
- **SP1 P1 守門三條零回呼解除漏洞(最實 = 刪組在途改名 → from 消失 → 深比對早退)** — **接受(機制)**:hook 加 `onSettled`
  於 `.finally` 必呼,守門由該發解除;hook 層三案釘三路徑(深比對 / 基底 null / 成功順序)。**誠實記帳**:reviewer 舉的
  具體序列在首版下其實綠 —— 刪組成功的 `onError(null)` 巧合解除了旗標;卡死需要「零回呼早退且期間無其他動作 settle」,
  首版靠巧合而不是設計,改掉。
- **SP2 P2 `[auto-default]` 1 理由不成立,建議 user 拍板** — **接受理由、不停下**:改 hook 簽名是 optional 參數的向後相容
  擴充(內部 hook,非對外契約),/auto 規則下推進,`[auto-default]` 改寫如 §0。
- **SP3 P2 測試缺「守門一定解除」那一半** — **接受**:新增「刪組在途改名後仍能改別組」+ hook 層三案。
- **P3 Escape 在途換組被吞** — 同 ST2。
