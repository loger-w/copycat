# Goal(自主模式): $ARGUMENTS

語法:`/goal <退出條件> <接續指令>`,例:`/goal pytest 全綠 且 紅測試轉綠 /bug 搜尋壞了`。
$ARGUMENTS 解析不出「可機械判定的退出條件 + 接續指令」→ 先問清楚再啟動。

## 契約

啟動後以「跑到退出條件成立」為目標推進接續指令的流程,**減少中途停下問的次數**,但遵守以下邊界:

### 退出條件
- 必須可機械判定:測試綠 / Phase N 完成 / metric 達標 / 表格全綠。「做到差不多」不合格。
- 退出條件成立 → 停下總結報告(做了什麼 / 自動敲定了哪些決策 / 剩什麼沒做)。
- 退出條件 3 次嘗試後仍不成立 → 鐵則 F:停下回報,不無限迭代。

### 自動核准範圍(不停下問的)
- 設計 / 實作選擇:採 own recommendation 推進,**每個 critical decision 在對應 artifact(brainstorm.md / design.md / state.json)標 `[auto-default: <選擇> | reason: <理由>]`**,讓 user 事後可快速 audit 哪些是自動敲定的。
- `superpowers:brainstorming` 的 user-approval HARD-GATE **替代條件**:規格來自 user 撰寫或拍板的文件(prompt 檔 / spec 檔 / 已核准的 design.md)→ 視為預核准,brainstorm.md 記來源;**沒有這類文件又遇到方向性抉擇 → 仍要停**(這是 blocker 不是 gate)。
- Review loop 內的 finding 處置(accepted / rejected 照 receiving 紀律走,不需逐條問)。

### 仍必停(自動模式不豁免)
- `git push` / PR 建立(push 前列 commit 清單 + 目標 branch 給 user 確認)
- **merge 不必停**(2026-07-06 拍板):`branch-lifecycle` 收尾 gate 全綠即自動 local merge(可逆;push 仍必停,有 push-gate 硬攔)
- 破壞性操作(刪檔案 / 改 schema / 遷移資料)
- Scope 變更(退出條件做不到、要縮 / 換方向)
- 花錢或對外發布的動作

### goal_efficiency_mode(TDD commit 節奏調整)
- 適用:/feat 大量檔數(> 15 檔)+ /goal 同時啟動時,逐檔 red→green→refactor 三 commit 會爆 commit 數。
- 啟用:寫 `state.json.scope_overrides.goal_efficiency_mode = true`。
- 效果:Phase 3 改 wave batch commit,單 `[waveN]` tag,**commit body 必列該 wave 涵蓋的 SC-N**;Phase 8 tag 驗證改驗「全 SC 有 wave 歸屬」而非 [red]/[green] 配對。
- 不啟用時維持標準 TDD 三 commit(預設)。

## 各流程建議用法(摘自各 command)
| 流程 | 建議 |
|---|---|
| /bug | ✓ `/goal pytest 全綠 且 紅測試轉綠 且 regression 抽樣綠 /bug <desc>` |
| /refactor | ✓ `/goal 既有測試前後皆全綠 /refactor <why>` |
| /perf | ✓ `/goal <metric 達標> 且 既有測試全綠 /perf <metric>` |
| /feat S 級 | ✓ `/goal Phase 8.5 完成 /feat <desc>` |
| /feat 中段自動 | `/goal Phase 7 結構化表格全綠 /feat <desc>`(保留 PR 決策) |
| /feat L 級 | ⚠ 不建議全自動 |
| /mod L 級 | ⚠ 慎用(caller map / backward compat 對齊價值高) |
