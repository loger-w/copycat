# Auto(自主模式): $ARGUMENTS

語法:`/auto <退出條件> <接續指令>`,例:`/auto pytest 全綠 且 紅測試轉綠 /bug 搜尋壞了`。
$ARGUMENTS 解析不出「可機械判定的退出條件 + 接續指令」→ 先問清楚再啟動。

## 契約

啟動後以「跑到退出條件成立」為目標推進接續指令的流程,**減少中途停下問的次數**,但遵守以下邊界:

### 退出條件
- 必須可機械判定:測試綠 / Phase N 完成 / metric 達標 / 表格全綠。「做到差不多」不合格。
- 退出條件成立 → 停下總結報告(做了什麼 / 自動敲定了哪些決策 / 剩什麼沒做)。
- 退出條件 3 次嘗試後仍不成立 → 鐵則 F:停下回報,不無限迭代。

### 自動核准範圍(不停下問的)
- 設計 / 實作選擇:採 own recommendation 推進,**每個 critical decision 在對應 artifact(brainstorm.md / design.md / state.json)標 `[auto-default: <選擇> | reason: <理由>]`**,讓 user 事後可快速 audit 哪些是自動敲定的。
- `superpowers:brainstorming` 的 user-approval HARD-GATE **替代條件**:規格來自 user 撰寫或拍板的文件(prompt 檔 / spec 檔 / 已核准的 design.md)→ 視為預核准,brainstorm.md 記來源;沒有文件但也**無**方向性抉擇 → 採 own recommendation 推進並標 `[auto-default]`;**沒有這類文件又遇到方向性抉擇 → 仍要停**(這是 blocker 不是 gate)。
- **方向性抉擇判定**(上一條的判準):把候選選項互換,brainstorm.md 的 SC 集合 / out of scope / 對外契約(API shape、資料格式、資料源)任一需要改寫 → 方向性抉擇,停;全部不動(純內部實作、可逆)→ 實作選擇,標 `[auto-default]` 推進。
- Review loop 內的 finding 處置(accepted / rejected 照 receiving 紀律走,不需逐條問)。

### 仍必停(自動模式不豁免)
- 破壞性操作(刪檔案 / 改 schema / 遷移資料)
- Scope 變更(退出條件做不到、要縮 / 換方向)
- 花錢或對外發布的動作(git push / `gh pr merge` 除外 — 2026-07-18 拍板全自動,取代 2026-07-07「merge 單一確認點」;推 main / `--force` 附 commit 清單告知即可)

### goal_efficiency_mode(TDD commit 節奏調整)
- 適用:/feat 大量檔數(> 15 檔)+ /auto 同時啟動時,逐檔 red→green→refactor 三 commit 會爆 commit 數。
- 啟用:寫 `state.json.scope_overrides.goal_efficiency_mode = true`。
- 效果:Phase 3 改 wave batch commit,單 `[waveN]` tag,**commit body 必列該 wave 涵蓋的 SC-N**;Phase 8 tag 驗證改驗「全 SC 有 wave 歸屬」而非 [red]/[green] 配對。
- 不啟用時維持標準 TDD 三 commit(預設)。

## 各流程建議用法(摘自各 command)

**疊加內建 /goal(建議預設)**:啟動 /auto 後,同時設內建 `/goal <同一退出條件>` 上機械保險 — harness 層小模型每 turn 判定條件、未成立自動續 turn,補上本契約「續跑靠模型自律」的弱點。優先序:契約的必停清單與鐵則 F 3 次上限**優先於**續跑 — 必停觸發或 3 次不成立時停下回報,不因內建續跑硬闖(此時 `/goal clear` 或等 user 指示)。

| 流程 | 建議 |
|---|---|
| /bug | ✓ `/auto pytest 全綠 且 紅測試轉綠 且 regression 抽樣綠 /bug <desc>` |
| /refactor | ✓ `/auto 既有測試前後皆全綠 /refactor <why>` |
| /perf | ✓ `/auto <metric 達標> 且 既有測試全綠 /perf <metric>` |
| /feat S 級 | ✓ `/auto Phase 8.5 完成 /feat <desc>` |
| /feat 中段自動 | `/auto Phase 7 結構化表格全綠 /feat <desc>`(收尾自動 merge 到底,2026-07-18 起無 merge 確認) |
| /feat L 級 | ⚠ 不建議全自動 |
| /mod L 級 | ⚠ 慎用(caller map / backward compat 對齊價值高) |
