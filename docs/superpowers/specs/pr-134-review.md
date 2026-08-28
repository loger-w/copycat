# PR #134 Code Review 比較報告 · SHA 7e28476d
**Report projection schema**: 1

**PR**: [loger-w/copycat#134](https://github.com/loger-w/copycat/pull/134)
**標題**: mod(capital): N075 市價單標籤 —— 程式不封洞、文件改口最新事件日、交易日保險絲不吞審計行(08-28 拍板題 1)
**作者**: loger-w(commits 署名 Loger)
**分支**: `mod/n075-price-type-label-window` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 5c0244f1;回溯 review)
**變更**: 10 檔案, +285 / -25
**審查日期**: 2026-08-28
**Review input basis**: source repo R_kgDOTsITBg + 7e28476d3d04e5dfd8fc8b5fb96b88195b56e32e;destination repo R_kgDOTsITBg + e600f341ab2df432afc0763ab0e5d01f5f1c9366;`input_binding: verified`(`git fetch refs/pull/134/head` 後 FETCH_HEAD 與 headRefOid 逐字相等、worktree HEAD = source SHA;destination SHA 為 master 歷史上的既有 commit,本機 `git rev-parse e600f341` 解析成功)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED、分支已刪);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-134`(detached)
**worktree HEAD**: 7e28476d3d04e5dfd8fc8b5fb96b88195b56e32e
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 主 agent 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer(不切塊,單一 dispatch;dispatch 顯式 model=opus、effort 依 frontmatter xhigh;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位;subagent 33 tool uses / 536 s);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=10 → covered 6 / no-issues 4 / skipped 0 / **missed 0**(chunked: 否;FILE_COUNT=4 源檔 ≤ 15、DIFF_LINES=310 < 800;reviewer 逐檔 accounting 10/10,union = F)
**定位 (ENH-B)**: anchored exact 7 / ambiguous 0 / **FAILED 0**(七個 anchor 於 worktree HEAD 以逐字比中且唯一:store.py:356 / client.py:104 / store.py:359 / verification.md:3 / test_client.py:2127 / client.py:907 / next-time.md:9;line 以比中結果為準)
**React-doctor (2.97)**: N-A(非 React PR:F 無 `.jsx` / `.tsx`,亦無任何前端檔)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,10 檔全部 authored)
**審查軸狀態**: primary(python-reviewer)PASS(7 findings、10/10 accounting、PR 自我宣稱 7 條逐條核對,含獨立重跑 mutation);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條實查,見備註欄;F-1 另以 audit log + server log + 06-10 真樣本第一手核)/ React-doctor N-A(非 React PR)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=sonnet 依 frontmatter)回 `VERDICT: VIOLATIONS: R7`(6c 對 F-06 寫成 N-A、6d-3 未逐條);已依現有產物補寫 Action Items「Severity calibration」段(6c 三層查證 + 6d-3 逐條);**未經第二次獨立稽查**。R1–R6 / R8–R10 PASS

**Report generation**: sha256:d350d476164cc8fa8e91f7cf45027ad4645203554d8183734d5165088e90e8d5

---
## [完整證據副檔](pr-134-review.audit.md)
### finding_uid 索引
[637cc476d877e7aef411](pr-134-review.audit.md#發現總覽) · [c6cb386468522ee88f5f](pr-134-review.audit.md#發現總覽) · [5547ed2d81fffba6f76f](pr-134-review.audit.md#發現總覽) · [1ccfbdc8c6c162147e09](pr-134-review.audit.md#發現總覽) · [19c9176eaf01d4df491a](pr-134-review.audit.md#發現總覽) · [e6a951bca2dd2efefd74](pr-134-review.audit.md#發現總覽) · [ece15b5e9cbced024339](pr-134-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | store docstring 把「`_Agg.date` = 最新事件日」當既成事實(並據此推出隔日事件推日期 → 標籤消失),但同套件 `reply.py:55` 記「idx23 委託建立日;C/D 事件實測仍為原單日期」,repo 內 06-10 真樣本 N / C 兩筆 idx23 / idx24 逐字相同;skill `tc4-market-facts:245` 的「實證」只引 `apply_reply` 覆寫機制、不是跨日事件的值觀測 —— 兩份敘述互斥並存(`copycat/capital/store.py`) | MED [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 第一手核:audit log + server log 顯示 08-27 唯一可疑筆(4991 09:00:25)是當日送單、非跨日樣本;06-10 C 樣本同日;跨日值**未實證** → 兩邊都降成機制描述 + 標未實證,不選邊 |
| F-02 | spec §1「`client.py` docstring 改口」漏同檔 `_today_ymd`(:104「與回報的委託建立日同時區」)與對外 wire 型別 `models.py:132` `OrderRecord.date  # 委託建立日 YYYYMMDD`(skill 逐字點名的那一格);另 `reply.py:55` / `test_reply.py:43` / `test_store.py:535` 同字(`copycat/capital/client.py`) | MED [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `grep -rn 委託建立日 copycat tests` → client.py:104 / models.py:132 / reply.py:55 / test_reply.py:43 / test_store.py:535 五處;與 F-01 同輪處置(措辭依 F-01 結論改「未實證」而非硬改「最新事件日」) |
| F-03 | 「語意錯位沒有把誤標窗拉寬」是無條件斷言:若採事件日語意,他方單入集母體 = 「事件日落在候選集」,是「建立日落在候選集」的超集(0823 建立、0824/0825 有事件的單會入集);docstring 只算了本方單失標、沒算他方單入集(`copycat/capital/store.py`) | MED [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b PARTIAL | Nice to Have | `auto-fix` | 推演成立但前提(事件日語意)依 F-01 未實證;改有界句「本方單只會失標;他方單入集母體視 idx23 語意而定,量級待實驗」 |
| F-04 | artifact 引 rebase 前 SHA:base commit `e600f341` 本身就是「(b) 改引第 n 筆 + commit subject」的拍板落檔,next-time :25-29 明寫「在那之前新分支的 verification 直接照 (b) 寫」;本 PR verification §分支 commit 與 JSON `fixed_point` / `reviewed_head` 仍寫 8 個裸 SHA,`git merge-base --is-ancestor` 全 NO(`.claude/mod/n075-price-type-label-window/verification.md`) | MED [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 核 next-time :25-29 原文;(b) 拍板 e600f341 是在本分支 two-axis review 之後才進 origin/master(rebase 時帶入),round 1 看不到 —— 但 push 前 rebase 已把它拉進來,仍該照 (b) 改 |
| F-05 | 新測試 `test_submit_result_survives_trade_day_fuse` 漏用 `_freeze_today`,斷言拿「送單當下記的日」比「斷言當下重算的 `_today_ymd()`」,跨午夜一瞬會紅 —— repo 正在追同型病(`test_bars` 5 條)(`tests/capital/test_client.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 核 :2081 姊妹測試有 `_freeze_today`、:2108–2130 無;加一行 + 斷 `(_FIXED_YMD,)` |
| F-06 | `_today_ymd()` / `_trade_ymd()` 求值順序被對調(原式在呼叫參數內左→右:本機日先;新版 `_trade_ymd()` 提進 try 先算),跨午夜一瞬舊序得 `(0824, 0825)`、新序 `(0825,)`;白名單 §3-1 宣稱逐 bit 不變、verification §3 只核布林式等價(`copycat/capital/client.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `git show e600f341:copycat/capital/client.py` 核原式 `_today_ymd()` 在前;把 `today = _today_ymd()` 提到 try 之前即恢復原序 |
| F-07 | 留給 user 親做的實驗,repo 內 `tests/capital/test_reply.py:11-15` 06-10 真樣本已給兩個現成數據點:(1) seq 前 6 位 `231309`≠ 08-27 `231321`,前綴隨日變;(2) 06-10 14:59:48 掛給 06-11 的預約單 idx23=`20260610`(進單日)、idx28=`20260611`(所屬交易日)—— 回報**可能另有一欄**直接帶交易日,若證實兩候選日設計可退成讀該欄(`docs/next-time.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 再加第一手:audit 08-26 seq `2313209526540` / `2313209679448`、08-27 `2313211157766` → 前 7 位逐日遞增(`2313092` → `2313209` → `2313211`),seq 為全域遞增計數不重編,撞 seq 實務上不可能;idx28 語意仍未解析(`reply.py` 未讀該欄) |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 637cc476d877e7aef411 action=auto-fix
F-02 finding_uid: c6cb386468522ee88f5f action=auto-fix
F-03 finding_uid: 5547ed2d81fffba6f76f action=auto-fix
F-04 finding_uid: 1ccfbdc8c6c162147e09 action=auto-fix
F-05 finding_uid: 19c9176eaf01d4df491a action=auto-fix
F-06 finding_uid: e6a951bca2dd2efefd74 action=auto-fix
F-07 finding_uid: ece15b5e9cbced024339 action=auto-fix
### Inline Comments per Finding（直接複製貼到 PR review）
#### F-01 這段把「最新事件日」當事實寫,但隔壁 reply.py 記的實測是相反的
**File**: `copycat/capital/store.py`
**Line**: 356-359

**Comment**:
```
這段說 _Agg.date 是最新事件日、隔日成交 / 刪單會把 date 推成隔天 → 標籤消失。
但 reply.py:55 寫的是「idx23 委託建立日;C/D 事件實測仍為原單日期」,
test_reply.py 的 06-10 真樣本 N / C 兩筆 idx23、idx24 逐字相同 —— 刪單回報沒帶刪單當下的日期時間。
skill 那條「實證」只講 apply_reply 有值就覆寫,沒講覆寫進來的值會不會變 —— 覆寫同一個日期等於沒變。
兩邊不可能同時對,現在 repo 內一個檔說 A、隔一個檔說非 A。

沒有跨日事件樣本前兩邊都別下定論。這段改成機制描述:
「apply_reply 每筆回報有值就覆寫 date;idx23 跨日事件會不會變,06-10 C 樣本(同日)看不出、
未實證(reply.py:55 記同日 C/D 仍為原單日期)。若不變 → 標籤不會因隔日事件掉;若變 → 只缺標籤。」
tc4-market-facts:245 那條同步降成「機制:覆寫;值是否變:未實證」。
```
#### F-02 改口漏了 _today_ymd 的 docstring 和 OrderRecord.date 那一行
**File**: `copycat/capital/client.py`
**Line**: 104

**Comment**:
```
spec 說 client.py / store.py 的「委託建立日」要改口,但同檔 _today_ymd 的 docstring 還是
「與回報的委託建立日同時區」;更重要的是 models.py:132 OrderRecord.date  # 委託建立日 YYYYMMDD
—— 那是前端唯一讀得到的 wire 欄位、也是 skill 逐字點名的那一格,還是舊句。
reply.py:55 / test_reply.py:43 / test_store.py:535 同字。

依 F-01 的結論,這五處不是硬改成「最新事件日」,是統一改成
「idx23;每筆回報覆寫;跨日事件是否變值未實證」這一句,五處同一口徑。
```
#### F-03 「沒有把誤標窗拉寬」這句反而是拉寬方向
**File**: `copycat/capital/store.py`
**Line**: 359

**Comment**:
```
如果真照上面「date = 最新事件日」的前提,他方單會不會撞進候選集看的是「事件日落在 (0824, 0825)」,
這比「建立日落在 (0824, 0825)」大 —— 0823 建的預約單只要 0824 / 0825 有成交或刪單就入集。
這段只算了我方單失標那半、沒算他方單入集那半,所以得出「沒拉寬」。

改成有界:「本方單在事件日語意下只會失標(fail-safe);他方單入集母體視 idx23 語意而定
—— 若 idx23 隨事件變,母體是變寬不是變窄;量級待夜盤實驗定案。」
```
#### F-04 這份 verification 引的 8 個 SHA 在 master 上都找不到,而 base commit 剛拍板不要這樣寫
**File**: `.claude/mod/n075-price-type-label-window/verification.md`
**Line**: 3

**Comment**:
```
分支 rebase merge 後這 8 個 SHA(c7e63fa8 / 50758b2d / …)全被改寫,git merge-base --is-ancestor 全 NO,
乾淨 clone 上 git show 是 unknown revision。而這條分支的 base e600f341 本身就是
「artifact 引 SHA 處置 user 拍板 (b) 改引第 n 筆 + commit subject」那筆,next-time:27 寫「在那之前新分支的
verification 直接照 (b) 寫」。

verification.md §分支 commit 與 code-review-round-1.json 的 fixed_point / reviewed_head 改成
「第 1 筆 test(capital): 紅先行 … → 第 2 筆 fix(capital): … → …」;fixed_point 寫 base 的 subject。
```
#### F-05 這條測試沒凍日期,午夜跨日那一瞬會紅
**File**: `tests/capital/test_client.py`
**Line**: 2127

**Comment**:
```
上一條姊妹測試有 _freeze_today(monkeypatch),這條沒有;斷言拿送單當下記進 store 的日
比「現在重算的 client_mod._today_ymd()」,00:00 前後各一邊就不等。repo 正在追 test_bars 那 5 條同型病。

開頭加 _freeze_today(monkeypatch),斷言改 == (_FIXED_YMD,)。
```
#### F-06 try 把 _trade_ymd 提前算了,本機日反而變後算
**File**: `copycat/capital/client.py`
**Line**: 906-907

**Comment**:
```
原式 _today_ymd() 在呼叫參數裡排前面、trade_date=_trade_ymd() 排後面,左→右先算本機日。
新版 _trade_ymd() 進 try 先算、_today_ymd() 到 note_price_type(...) 才算,順序反了。
跨午夜那一瞬:舊序記 (0824, 0825),新序記 (0825,) —— 只少一個候選日、fail-safe 方向,
但白名單 §3-1 說逐 bit 不變、verification 只核了布林式等價。

try 前面先 today = _today_ymd(),下面用 today,就回到原序。
```
#### F-07 要 user 親做的實驗,repo 裡已經有一半答案
**File**: `docs/next-time.md`
**Line**: 9

**Comment**:
```
tests/capital/test_reply.py:11-15 的 06-10 真樣本:三筆同日 seq 前 6 位都是 231309,08-27 是 231321
—— 再加 audit log 08-26 的 2313209526540 / 2313209679448:前 7 位逐日遞增,seq 是全域遞增計數、
不是每天重編,撞同 seq 實務上不可能。這條實驗的「seq 重置口徑」那半可以先寫上這個答案。
另一個:那筆 06-10 14:59:48 掛給 06-11 的預約單,idx23=20260610(進單日)、idx28=20260611(所屬交易日)
—— 回報可能本來就有一欄帶交易日;reply.py 沒解析 idx28。若證實,「記兩個候選日」整套可以退成讀那一欄。
兩點都補進這條留尾,user 只剩「idx23 跨日會不會變」和「idx28 是不是交易日」兩件要核。
```
## 沒做的部分（結案對帳）
- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(grep / sed / git show / audit jsonl / server log)。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 以 `py -3.14` 實跑)。
- 真實環境:本 PR 唯一行為改動的觸發條件 = 日曆資料錯,prod 不可無害觸發,未做;prod 8721 仍跑 1ce0c500(不含本 PR)。
- 未驗證前提:**idx23 跨日事件是否變值**(F-01 / F-03 的核心;repo 內零跨日樣本,08-27 唯一可疑筆經 audit + log 核為同日);**idx28 是否為所屬交易日欄**(F-07;僅一筆預約單樣本吻合,`reply.py` 未解析);reviewer 的全量 pytest / `copycat validate` 未重跑(主 agent 於分支上實跑過:3134 passed、42/42)。
- 順帶發現(第一手,建議入 next-time):群益 seq 前 7 位逐日遞增(`2313092` 06-10 / `2313209` 08-26 / `2313211` 08-27),為全域計數 —— N075 誤標窗「撞同 seq」前提實務上不成立。
- Self-Verify:已執行(skill-verify-auditor,dispatch model=sonnet 依 frontmatter)→ `VIOLATIONS: R7`:auditor 指 6c 把 F-06 的求值順序變動當 N-A、6d-3 只有總結沒逐條。修正 = Action Items「Severity calibration」改寫為 6c 三層查證(結論:非設計意圖、恢復原序)+ 6d-3 七條逐列;修正後未重派 auditor,**未經第二次獨立稽查**。
