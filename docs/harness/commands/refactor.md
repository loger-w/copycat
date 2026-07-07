# Refactor: $ARGUMENTS

(若 $ARGUMENTS 為空,先問我要 refactor 什麼、為什麼再繼續。)

共通鐵則套用 `~/.claude/CLAUDE.md`。自主模式契約見 `~/.claude/commands/auto.md`。

## 核心紀律
**行為絕對不變。** 一旦想順手改行為 → 那不是 refactor,切到 `/mod`。

## Phases

0. **Phase 0|工作區**:呼叫 `branch-lifecycle` 開工節(status 乾淨 + 主線同步 + `git switch -c refactor/<slug>`)。大型 refactor(Phase 3 會 dispatch reviewer)另建 artifact 目錄 `.claude/refactor/<slug>/`
1. **Phase 1|Why? gate**:明確寫出動機(被哪個即將要做的 feature / bug fix 卡住、哪段 duplication / 命名造成 review 看不懂、哪個 deprecated API 逼著動)。**為什麼是現在?** 寫不出明確理由 → 停。Refactor 沒理由就是 churn
2. **Phase 2|測試覆蓋盤點**:現有測試 baseline 全綠;覆蓋不夠 → **先寫 characterization test 把當前行為拍下來**(不求漂亮,求「行為偷偷變了會抓到」),**標 🟢 新測試、跟 refactor 的 🔵 分開 commit**。沒測試保護的 refactor 不允許。大型 refactor 盤點結果落檔 `.claude/refactor/<slug>/test-inventory.md`(Phase 3 reviewer dispatch 的必要輸入)
3. **Phase 3|拆步驟**:寫 `.claude/refactor/<slug>/refactor-plan.md`,拆 N 個小步驟,**每步單獨保持綠**。每步預估 diff > 100 行再拆。大爆炸(一次改 20+ 檔)禁止。大型 refactor dispatch `refactor-plan-reviewer` agent:傳 refactor-plan.md + Phase 2 `test-inventory.md` 路徑(criteria / JSON schema 固化在 agent 定義)。**Max 2 輪;退出條件:無 P0/P1**。2 輪後仍有 → 停下回報 user(縮範圍 / 換拆法 / 接受風險註記)
4. **Phase 4|逐步執行**:每步 = 改 → 跑相關測試 → 全綠 → `git commit`(**純 🔵**)→ 下一步。若紅:**預設 refactor 改錯**(鐵則 C),次選才考慮測試在測 implementation detail(若真是 → 標註,這已經變相是 mod,停下切 `/mod`)
5. **Phase 5|Blast radius**:grep 動到的命名 / signature 所有 caller(含動態用法 / template string / reflection / 外部 caller),跑完整 test suite(不只動到那塊)
6. **Phase 6|自動化驗證**:呼叫 `auto-verify` skill 全綠
7. **Phase 7|真實環境驗證**:呼叫 `auto-verify` 真實環境節 — dev server 跑改動範圍功能,**行為跟 refactor 前完全一樣**;抽 2 個沒改的相關功能確認沒事(同 auto-verify regression 抽樣數)
8. **Phase 8|回頭核**:Phase 1 動機解決了?diff 中沒有任何行為差異?能量化的改進(複雜度 / duplication / 命名 / 行數)有沒有真的好

## 失敗 routing
- 步驟內測試紅 → **預設 refactor 改錯,不是測試錯**;3 次修不過套鐵則 F
- 發現必須改行為才做得下去 → **這已經是 mod**,停下切 `/mod`
- 順手改動的發現 → 寫 `docs/next-time.md`,不在本次處理

## 自主模式建議
✓ 強烈推薦:`/auto 既有測試 refactor 前後皆全綠 /refactor <why>`

## Done
所有既有測試 refactor 前後都全綠 + refactor commits 純 🔵(characterization test 為 🟢 獨立 commit)+ Phase 1 動機被處理。
**全過後呼叫 `branch-lifecycle` 收尾節**(push → PR → review 補齊 → merge 確認 → auto-merge),再做最終回報。

## 禁止(本流程特有,共通禁止見 CLAUDE.md)
- ❌ 沒測試保護就 refactor
- ❌ Refactor + 行為改動混在同一個 commit
- ❌ 「順手」修 lint / rename / 換 library
- ❌ 大爆炸:一個 commit 改 20+ 個檔(門檻同 Phase 3)
- ❌ 預設「測試錯了」(預設是 refactor 改錯)
- ❌ 沒理由的「為了一致性」rename
- ❌ 砍掉「看起來沒用」的 code,沒查過動態用法
