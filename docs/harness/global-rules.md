# 共通鐵則(所有任務一律遵守)

## A. 觀察優先(動手前)
動手前先看:
- 新功能 → brainstorm + 看 conventions
- Bug → 穩定重現 + 蒐證
- Mod → grep 所有 caller(含動態用法)
- Refactor → 測試覆蓋盤點
- Optimize → profile 真實 bottleneck

**Root cause > 症狀**:沒釐清根因不能提交。

## B. Scope 紀律
- 看到順手想改的 → 寫進「下次處理」清單,不在這次動
- 不為「未來可能」加 abstraction
- 三類動作分開 commit:🔴 行為改動 / 🟢 新功能 / 🔵 純重構(emoji 前綴的強制範圍由流程 command / 專案 CLAUDE.md 定義;未定義處只要求三類不混,不強制 emoji)
- 不順手 lint fix / rename / 升 dependency

## C. 測試紀律
TDD 走 `superpowers:test-driven-development`(紅先行)。沒測試保護的 code 先寫 characterization 再動。既有測試紅 → 預設「動到不該動的」,測試是行為合約不是裝飾。

## D. 證據要求(完成 ≠ 自動化綠燈)
完工前過 `superpowers:verification-before-completion` + `auto-verify`,完成必附證據(指令輸出 / 測試數字 / 截圖 / 量測對照)。不用「應該可以」「probably」「我覺得」收尾。自動化全綠 ≠ Done,還要真實環境 + 回到動機核對。

## E. 禁止繞過手段
- ❌ `--no-verify` / `--skip-hooks` / `--no-gpg-sign`
- ❌ `.skip` / `xfail` / `pytest -k 'not failing'` / 砍測試
- ❌ 改 test assertion 來讓它通過(除非該 assertion 已事前標為「該變」)
- ❌ `try/except: pass`、`except: log; return`(catch 後沒處理 = 吞錯誤)
- ❌ Mock 掉真實依賴讓測試通過
- ❌ 重啟服務 / 清 cache / sleep + retry 當作 fix
- ❌ 在 caller 加 `if` 規避 root cause
- ❌ Root cause 沒釐清就提交修改
- **不懂的 error 不要 catch**;catch 後要有具體處理邏輯,純 log 等於吞掉

## F. 失敗處理:3 次上限
任一步驟修不過 3 次 → 停下來,回報:
1. 哪個 phase / step
2. 完整錯誤訊息
3. **試過的 3 種策略 + 各自為什麼沒成功**
4. 推測根因(不是現象)

不允許「繼續試試看」。3 次過後通常代表 hypothesis 錯,要回上一階段。

## G. Sub-agent / Loop 紀律
- Sub-agent 是 fresh context → 明確傳入 goal + spec + criteria + 上輪 feedback
- Review criteria 結構化(checklist + JSON 回傳),不是「請反思一下」
- Loop max 3 輪,嚴重度 P0/P1/P2,退出條件「無 P0/P1」(流程 command 檔可**顯式覆寫** P1 門檻 — 覆寫處必標明,以 command 檔為準)
- 禁止「直到沒問題為止」的無限迴圈
- 資源:Workflow `agent()` 預設 `effort:'low'` 省額度;Agent tool 無 effort 參數改用最小可勝任 model(如 haiku);難 judge 才升級且說明理由

## H. Git 推送紀律
- 流程分支 push(單獨指令 `git push -u origin <feat|fix|mod|refactor|perf>/<slug>`,PR 收尾用)屬自動步驟,不必停。
- 其他 push(main / `--force` / 非流程分支)前必列 `origin/<branch>..HEAD` commit 清單 + 目標 branch 給我確認;「push」≠「直推 main」。
- `gh pr merge` = PR 收尾單一確認點(push-gate hook ask 框,試用完按 allow 即 merge 到底)。自主模式(/auto)不豁免。

---

# 流程入口(slash commands)

| 指令 | 場景 | 核心紀律 |
|------|------|---------|
| `/feat <goal>` | 新功能 / 空白頁面 | 不過度設計、TDD |
| `/bug <description>` | 線上 bug / 異常 | Root cause、紅測試先行 |
| `/mod <change>` | 改既有功能邏輯 / 介面 | Caller map、三類分離 |
| `/refactor <why>` | 純結構優化(行為不變) | 小步快跑、行為絕對不變 |
| `/perf <metric>` | 效能優化 | 量化目標、profile 找 bottleneck |

各指令的詳細 phases 在 `~/.claude/commands/<name>.md`。共通鐵則自動套用,不在每個 command 重複貼。

---

# 預設驗證

驗證(自動化 + 真實環境)走 `auto-verify` skill — 依專案形狀選指令、依 feature shape 選驗證方式。專案層 `<project>/CLAUDE.md` 可覆寫該 skill 預設。

---

# 溝通偏好
- **始終用 Traditional Chinese 回覆**(不論我發問用什麼語言、不論引用的外部資料是英文)
- code / 回覆不加 emoji,除非我明確要求
- 引用 skill 時用明確名稱(`superpowers:brainstorming`),不用「反思一下」這種泛稱
