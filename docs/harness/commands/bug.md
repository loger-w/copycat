# Bug: $ARGUMENTS

(若 $ARGUMENTS 為空,先問我 bug 描述再繼續。)

共通鐵則套用 `~/.claude/CLAUDE.md`。自主模式契約見 `~/.claude/commands/auto.md`。

## 核心紀律
**穩定重現 → 紅測試 → 修 root cause → 反向驗證**。沒重現先別動 code。

## Phases

0. **Phase 0|工作區**:呼叫 `branch-lifecycle` 開工節(status 乾淨 + 主線同步 + `git switch -c fix/<slug>`)
1. **Phase 1|重現 + 蒐證**:最小重現步驟 / stack trace / error log / 截圖 / 影響範圍(哪些功能、哪些使用者、嚴重度)。**無法穩定重現 → 停下問**,不靠猜
2. **Phase 2|Root cause**:呼叫 `superpowers:systematic-debugging` 並**遵循其方法論**:調查階段可先列候選假說清單(廣度),但**驗證嚴格一次一個假說、一次改一個變數**(不同時驗多個)。用實驗證明 root cause(不是「看起來像」)。不允許跳過假說驗證直接改 code
3. **Phase 3|紅測試先行**(鐵則 C):用 Phase 1 重現條件寫測試 → 現在紅且訊息符合 → 以後防 regression。「寫不出測試」九成是測試設計問題,寫不出來說明原因
4. **Phase 4|最小修改**:只動 root cause 對應那幾行。不順手 refactor / rename / lint(順手衝動寫進 `docs/next-time.md`)。Commit 標 🔴 行為改動(鐵則 B)
5. **Phase 5|Blast radius**:grep 同函式 / 變數所有 caller(含動態用法 / template string / reflection / 外部 caller),列受影響功能各跑 sanity check
6. **Phase 6|自動化驗證**:呼叫 `auto-verify` skill(驗證指令來源以該 skill 為準)全綠
7. **Phase 7|真實環境驗證**:dev server 重走 Phase 1 重現步驟,**現在不會發生**;抽 2 個沒改的相關功能確認沒打壞;Console 0 errors
8. **Phase 8|反向驗證**(關鍵):暫時還原 Phase 4 修復讓 bug 重現 — 修復已 commit(本流程預設,Phase 4 有 commit)→ `git revert --no-commit <fix-sha>`;尚未 commit → `git stash`。Phase 3 紅測試**該紅回來** → 還原修復(`git revert --abort` / `git stash pop`)→ 綠回去。**還原修復後測試還是綠 → 測試沒抓到 bug,回 Phase 3 重寫測試**(計入鐵則 F 次數)
9. **Phase 9|留尾巴**:同類結構的 code 可能有同樣問題?寫進 `docs/next-time.md`(不在本次 fix 處理)

## 失敗 routing
- **同一 root cause 假設下修 3 次還紅 → 遵循 `superpowers:systematic-debugging` 的處置:STOP,質疑的是架構理解不是又一個假說** — 回報 user(三策略 + 各自為何失敗 + 推測的架構層根因),等 user 決定,**不是**自行回去再列一批假說硬試(這也是鐵則 F 的本意)
- 重現步驟跑不出來 → 回 Phase 1 蒐證,不允許「姑且修一下」
- Blast radius 抽樣紅 → 改錯方向,回 Phase 2

## 自主模式建議
✓ 強烈推薦:`/auto pytest 全綠 且 Phase 3 紅測試轉綠 且 regression 抽樣綠 /bug <desc>`

## Done
紅測試綠 + 既有測試保持綠 + regression 抽樣綠 + 反向驗證通過。
**全過後呼叫 `branch-lifecycle` 收尾節**(push → PR → review 補齊 → merge 確認 → auto-merge),再做最終回報。

## 禁止(本流程特有,共通禁止見 CLAUDE.md)
- ❌ 「無法重現,姑且修一下」
- ❌ 「重啟服務就好」「清 cache 就好」當 fix
- ❌ 在 caller 加 `if x is None` 規避 root cause
- ❌ Root cause 沒釐清就提交
- ❌ 改測試 assertion 硬讓它過(預設是「測試對 / 程式錯」)
- ❌ 同時改多個變數驗證假說(一次一個)
