# PR #131 Code Review 比較報告 · SHA 49fac608
**Report projection schema**: 1

**PR**: [loger-w/copycat#131](https://github.com/loger-w/copycat/pull/131)
**標題**: chore: /pr-review #128 / #129 / #130 22 條 finding 收修(sparse WARNING 延後印、測試重組、AvgSource parity、文件 14 條)
**作者**: loger-w(commits 署名 Loger)
**分支**: `chore/pr-review-128-130-followups` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 c80dbde5;回溯 review)
**變更**: 28 檔案, +448 / -88
**審查日期**: 2026-08-28
**Review input basis**: source repo R_kgDOTsITBg + 49fac6084df2142d30eca64400e50a69e6fe1764;destination repo R_kgDOTsITBg + c37e0401deacdb3cdc44d6f29b65a166ce04e8b9;`input_binding: verified`(`git fetch refs/pull/131/head` 後 FETCH_HEAD 與 headRefOid 逐字相等、worktree HEAD = source SHA;destination SHA 為 master 歷史上的既有 commit,`git merge-base --is-ancestor` 成立)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED、分支已刪);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-131`(detached)
**worktree HEAD**: 49fac6084df2142d30eca64400e50a69e6fe1764
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 主 agent 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer(不切塊,單一 dispatch;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=28 → covered 3 / no-issues 25 / skipped 0 / **missed 0**(chunked: 否;FILE_COUNT=13 源檔 ≤ 15、DIFF_LINES=536 < 800;reviewer 逐檔 accounting 28/28,union = F;F-04 為 commit 訊息層 finding、不佔檔案)
**定位 (ENH-B)**: anchored exact 3 / ambiguous 0 / **FAILED 0**(三個 anchor 於 worktree HEAD 以 grep 逐字比中且唯一,line 以比中結果為準;F-04 anchor `<none>`、無 file:line、不計)
**React-doctor (2.97)**: N-A(非 React PR:F 只有 `frontend/src/types.ts` 一個 `.ts`,無 `.jsx` / `.tsx`)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,28 檔全部 authored)
**審查軸狀態**: primary(python-reviewer)PASS(4 findings、28/28 accounting、8 條 PR 自我宣稱逐條核對);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條實查,見備註欄);React-doctor N-A(非 React PR)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus)回 R1–R10 全 PASS、`VERDICT: COMPLIANT`;無需補寫

**Report generation**: sha256:ecbcb14cad67b7fa1e7d84c8a688f54245d13f10d5d914584532c54f460bbbf7

---
## [完整證據副檔](pr-131-review.audit.md)
### finding_uid 索引
[149c1e0df22a7b110310](pr-131-review.audit.md#發現總覽) · [da19627d3279a66386fa](pr-131-review.audit.md#發現總覽) · [9e9c9bfe300e6fbf256c](pr-131-review.audit.md#發現總覽) · [50bff2f62557926c2119](pr-131-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | 新 helper docstring 自稱「後端測試讀前端原始碼字面的唯一入口」,但 `tests/test_stock_watchlist.py:269` 仍自己算 `parents[1]` 讀 `frontend/src/lib/constants.ts`(同樣是 §4 parity lock):round 1 S-4 想根治的「各測試各數各的」還剩一處,敘述超出程式碼(`tests/helpers/frontend_source.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep `parents\[` tests/ → 僅 test_stock_watchlist.py:269 一處未走 helper;兩擇一:該條改走 helper,或 docstring 降為「跨語言 parity 測試共用入口」 |
| F-02 | 本 PR 自己的 verification §1 寫 fix commit「以輸出參數蒐集」,但 HEAD 的 `_parse_legs` 已在 `2bd63ccc`(round 1 S-5 / P-3 收修)改成回傳 `_ParsedLegs` NamedTuple;§7 有記、§1 未回指 —— 與本 PR 修的 #129 F-06「引了會被取代的字面」同型(`.claude/chore/pr-review-128-130-followups/verification.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep `def _parse_legs` → `:103 def _parse_legs(raw: object) -> _ParsedLegs \| None`;§1:12 仍寫 `_parse_legs(raw, bad_sparse)`;一句補「(收修後改 NamedTuple 回傳,見 §7)」 |
| F-03 | §4 index 閘條新括號句「有日曆到午夜」漏掉 `_is_trading_day` 這道閘:`_broadcast_loop:656` 是 `now_t >= _WATCH_END and self._is_trading_day(...)`,休市日一發都不打(該處註解自述);契約條寫得比 code 寬,日後有人照這句判「假日晚上沒自癒 = 壞了」。同型漏字亦見 `stock_source.py:53` / `next-time.md:59`(#128 既有,非本 PR 新增)(`CLAUDE.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent sed index_engine.py:653-658 確認 calendar 分支 AND `_is_trading_day`;三處同句一起改「有日曆且為交易日 → 到午夜」 |
| F-04 | commit 慣例兩處瑕疵:(a) `1d2242f5` subject `refactor: …` 無 scope —— 全庫 525 筆 typed subject 中唯一一筆無 scope,且內容全是註解 / JSDoc 位移,依本 PR 自家 round 1 S-7 定調應歸 `chore`;(b) `1f3fe386` 標 `refactor(tests)` 卻含新增斷言(🟢 混 🔵),round 1 已以「不重寫本地歷史」accepted(commit 訊息層,無 file:line) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | 參考用 | `no-op` | 主 agent `git log --pretty=%s` grep 無 scope typed subject → 1(即 1d2242f5)/ 有 scope 524;已 rebase merge 進 master,歷史不重寫;下輪分 commit 時純註解一律歸 `chore(<scope>)`、新增斷言另拆 `test` commit |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 149c1e0df22a7b110310 action=auto-fix
F-02 finding_uid: da19627d3279a66386fa action=auto-fix
F-03 finding_uid: 9e9c9bfe300e6fbf256c action=auto-fix
F-04 finding_uid: 50bff2f62557926c2119 action=no-op inline=none
### Inline Comments per Finding（直接複製貼到 PR review）
#### F-01 這支 helper 說自己是「唯一入口」,但 test_stock_watchlist 還在自己算路徑
**File**: `tests/helpers/frontend_source.py`
**Line**: 1

**Comment**:
```
docstring 寫「後端測試讀前端原始碼字面的唯一入口」,但 tests/test_stock_watchlist.py:269 的
test_frontend_constant_matches_backend 還是自己 Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "constants.ts"
—— 同樣是 CLAUDE.md §4 的 parity lock(WATCHLIST_LIMIT),round 1 S-4 要收的「parents[N] 各數各的」就剩這一處。
下一個人 grep 這支 helper 會以為已經收斂完。

兩擇一:那條改成 read_frontend_source("lib/constants.ts"),或把「唯一入口」降成「跨語言 parity 測試共用入口(river palette / AVG_SOURCES;
constants.ts 那條尚未接)」。前者順手做掉最乾淨。
```
#### F-02 verification §1 寫的還是被 §7 推翻的那個形狀
**File**: `.claude/chore/pr-review-128-130-followups/verification.md`
**Line**: 12

**Comment**:
```
§1 說 fix commit ee916937 是「_parse_legs(raw, bad_sparse) 以輸出參數蒐集」—— 那是 round 1 之前的形態;
2bd63ccc(S-5 / P-3 收修)已改成 def _parse_legs(raw) -> _ParsedLegs | None 回傳 NamedTuple(corr_config.py:103)。
§7 / JSON 有記收修,但 §1 沒回指,只讀 §1 的人拿到的是被自己 review 推翻的實作形狀 —— 正好是本 PR 修 #129 F-06
「引了會被取代的字面」那一型。

§1 那行尾巴補一句「(round 1 S-5 / P-3 收修後改為 `_ParsedLegs` NamedTuple 回傳,見 §7)」就好。
```
#### F-03 這句「有日曆到午夜」把休市日也算進去了,code 沒有
**File**: `CLAUDE.md`
**Line**: 277

**Comment**:
```
新括號句「分時自癒 09:00 起全程都在,_WATCH_END 後只是換成尾段判準接手 —— 有日曆到午夜、無日曆到 13:40」
少了一道閘:index_engine._broadcast_loop:656 有日曆那條是
heal_window = now_t >= _WATCH_END and self._is_trading_day(self._today_fn())
—— 休市日一發都不打(該處註解自己寫「休市日則一發都不打」)。契約條寫得比 code 寬,日後有人照這句去查
「假日晚上為什麼沒自癒」會白查。

改「有日曆且當天是交易日 → 到午夜;無日曆 → 13:40」。stock_source.py:53 與 docs/next-time.md:59 的
「有日曆 → 13:25 起到午夜」是 #128 就有的同型漏字,順手三處一起改。
```
## 沒做的部分（結案對帳）
- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(grep / sed / git log)。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 以 `py -3.14` 實跑;主 python 缺 jsonschema)。
- 真實環境:本 PR 無 UI / API 變更,prod 不需為此重啟;#128 F-01「重掛 snapshot 讓現價欄回來」仍是未實測推論,08-28 13:36 `/api/index/state` 核。
- 未驗證前提:reviewer 的「紅先行 2 failed」為機械證明未實跑(主 agent 於分支上實跑過:`2 failed, 20 deselected`,見 PR verification §1);F-03 的後果「日後有人白查」是推論。
- 順帶發現(非本 PR finding、建議入 next-time):`tests/server/test_bars.py` 5 條在台北 00:00–00:10 會因 `bars._now_time()` 吃真牆鐘而紅(`MIDNIGHT_BUFFER_END` 午夜緩衝),該檔其他測試已 `monkeypatch _now_time`、這 5 條沒凍結。
- Self-Verify:已執行,COMPLIANT(auditor 以 Read 讀取草稿檔本身,未讀其他產物)。
