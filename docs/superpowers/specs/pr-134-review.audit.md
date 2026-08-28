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

## Spec 依據

- 偵測到 `.claude/mod/n075-price-type-label-window/change-spec.md`:§1 現況 vs 目標五列(`_Agg.date` 語意改口 / 誤標窗釘現況 / `_trade_ymd` 保險絲 / review §5 回填 / N099 改維持鎖)、§2 caller map、§3 既有行為白名單六條、§4 唯一行為改動(`_note_price_type` 只收 `RuntimeError` → WARNING + `trade_date=None`)、§5 seams、§6 留尾 + 兩條 knowing。非目標未明列;白名單 = 六條逐 bit 不變。
- ⚠️ spec 作者 = PR 作者(同 session 同 agent 自寫 spec、自實作、自驗;08-28 拍板由 user 下,但「改口最新事件日」這條目標的**事實來源**是 agent 自己引的 skill 條目,本輪 F-1 正是這個來源與同套件另一份實測互斥)。
- `SPEC_COMPLIANCE` receipt:gate=SKIPPED;dispatch=NOT_APPLICABLE;dispatch_count=0;reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED(reducer `resolve-authority` 以 `py -3.14` 實跑,候選 = change-spec §4「`_trade_ymd()` 拋 `RuntimeError` … 時」ERROR_CONTRACT 句:spec 位於 `.claude/mod/<slug>/`,不在 `openspec/specs/**` / `openspec/changes/**` 允許路徑);requested_model=opus;observed_model=UNAVAILABLE;effort=xhigh;tools=0;0 clauses / 0 findings / 0 observations / 0 invalidated

## 變更概要

provenance:10 authored / 0 inherited(base = master,免驗)。

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `copycat/capital/client.py` | 有 finding(修改) | 唯一行為改動:`_note_price_type` guard 改 early-return,`_trade_ymd()` 包 `try/except RuntimeError` → WARNING(`exc_info=True`)+ `trade_date=None`;`_trade_ymd` / `_note_price_type` docstring 改口「`_Agg.date`(最新事件日)」+ 保險絲兩把函式點名。F-2 漏改 `_today_ymd` docstring、F-6 求值順序對調 |
| `copycat/capital/store.py` | 有 finding(修改) | 全為 docstring / 註解:`_Agg.date` 欄位註解改「最新事件日」、`note_price_type` 新增語意段 + 08-28 拍板段(期貨路徑更寬、關窗條件句、指向 s3 案)、`_price_type_of` / `_today_net_lots_locked` 改口。F-1 與 `reply.py:55` 互斥、F-3 「沒拉寬」無條件句 |
| `tests/capital/test_client.py` | 有 finding(修改) | 新 `_trade_ymd_blows_fuse` 替身 + 兩條紅先行測試(late 審計行 / 送單結果);`_dated` docstring 改口。F-5 第二條漏 `_freeze_today` |
| `tests/capital/test_store.py` | 無 finding(修改) | s3 案 docstring 註明「同一組輸入 store 分不出同一張 / 另一張 = N075 未封的窗」;`test_price_type_not_applied_across_days` docstring 改口(reviewer 核過與 store 語意一致) |
| `docs/next-time.md` | 有 finding(修改) | 新 08-28 節:夜盤遠價市價單實驗(user 親做)+ prod seq 13 位觀察。F-7 未引 repo 內已有的 06-10 真樣本(seq 前綴 / idx28) |
| `docs/superpowers/specs/2026-08-24-do-batch-rounds.md` | 無 finding(修改) | N099 `[ ]` → `[x]` + 08-28 拍板維持鎖 |
| `docs/superpowers/specs/2026-08-25-do-batch-review.md` | 無 finding(修改) | §5 A2 / A3 / A5 / A7 + C 類回填 08-28 拍板(reviewer 核過與 change-spec §1 / next-time 一致) |
| `.claude/mod/n075-price-type-label-window/change-spec.md` | 無 finding(新增) | spec(caller map + 白名單 + 唯一行為改動 + seams + 留尾) |
| `.claude/mod/n075-price-type-label-window/verification.md` | 有 finding(新增) | §1 gate 表 / §2 mutation / §3 白名單逐條 / §5 真環境 / §6 goal。F-4 §分支 commit 引 rebase 前 SHA |
| `.claude/mod/n075-price-type-label-window/code-review-round-1.json` | 有 finding(新增) | two-axis round 1:Standards 5 / Spec 6 處置。F-4 `fixed_point` / `reviewed_head` 引 rebase 前 SHA |

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

### Opus 原始 findings (first-pass, context-aware)

- **F-01**(reviewer 原編號 F-1,MEDIUM [python-reviewer])`copycat/capital/store.py:356-359` —— 「最新事件日」推論與 `reply.py:55` 實測註記互斥,PR 只改一邊;`apply_reply` 覆寫機制只保證欄位會被蓋、不保證蓋進來的值是新的一天;06-10 N / C 樣本 idx23 / idx24 逐字相同。fix:降格成機制描述,或同輪把 `reply.py:55` 一起改口並註明哪一份觀測作廢。anchor:`另一個前提要說清楚:`_Agg.date` 是**最新事件日**,不是委託建立日(`apply_reply` 有值就`。search-proof:`grep -rn "最新事件日|idx23|委託建立日" copycat tests docs .claude/skills` → `reply.py:55` 與 `tests/capital/test_reply.py:43` 持相反敘述;`sed -n '11,15p' tests/capital/test_reply.py` 逐欄比對 N / C
- **F-02**(reviewer 原編號 F-2,MEDIUM [python-reviewer])`copycat/capital/client.py:104-106` —— spec §1 點名的 client.py 改口漏 `_today_ymd`;`models.py:132` `OrderRecord.date` 宣告點(skill 逐字點名)也沒跟。anchor:`    """價格別記憶的日界 = 本機日曆日(與回報的委託建立日同時區)。`。search-proof:`grep -rn "委託建立日" copycat tests` → 改口後仍 `client.py:104` / `models.py:132` / `reply.py:55` / `test_reply.py:43`(主 agent 補 `test_store.py:535`)
- **F-03**(reviewer 原編號 F-3,MEDIUM [python-reviewer])`copycat/capital/store.py:359` —— 「語意錯位沒有把誤標窗拉寬」無條件斷言;事件日語意下他方單入集母體是建立日語意的超集。anchor:`被隔日事件推日期仍在集合內,標籤照帶。語意錯位沒有把誤標窗拉寬(review §2.4 Standards 1)。`。search-proof:N/A: docstring-vs-code(對 `_price_type_of` :391-406 與 prune :376-383 逐行核過,綁定只比 stock_no / buy_sell)
- **F-04**(reviewer 原編號 F-4,MEDIUM [python-reviewer])`.claude/mod/n075-price-type-label-window/verification.md:3`(+ `code-review-round-1.json`)—— 引 rebase 前 SHA,違反父 commit `e600f341` 剛落檔的 (b) 拍板。anchor:`分支 commit(master 1ce0c500 起):c7e63fa8 test 紅先行 → 50758b2d fix → 04ca8f47 chore docs → 4f9d6404 refactor(tests) 收修 →`。search-proof:`git log -1 --format=%s e600f341` + `grep -n "第 n 筆" docs/next-time.md`(:27)+ 8 個 SHA 逐一 `git merge-base --is-ancestor` → 全 NO
- **F-05**(reviewer 原編號 F-5,LOW [python-reviewer])`tests/capital/test_client.py:2108-2127` —— 漏 `_freeze_today`,以事後重算牆鐘比對。anchor:`    assert client.store._price_types[result.seq_no][1] == (client_mod._today_ymd(),)`。search-proof:`grep -n "_freeze_today(monkeypatch)" tests/capital/test_client.py` → 1821 / 1851 / 1873 / 1899 / 2081,2108–2130 無
- **F-06**(reviewer 原編號 F-6,LOW [python-reviewer])`copycat/capital/client.py:906-907` —— `_trade_ymd()` / `_today_ymd()` 求值順序對調。anchor:`            trade_date: str | None = _trade_ymd()`。search-proof:N/A: docstring-vs-code(對照 `git show e600f341:copycat/capital/client.py` 原呼叫式參數順序)
- **F-07**(reviewer 原編號 F-7,LOW [python-reviewer])`docs/next-time.md:9-12` —— 留尾未引 `test_reply.py:11-15` 真樣本(seq 前綴 231309;預約單 idx23 / idx28 不同日)。anchor:`  **08-28 01:xx prod 觀察(1ce0c500,`/api/capital/orders` 08-27 17 筆現股)**:群益 seq 是 13 位(例 `2313211157766`),`。search-proof:`sed -n '11,15p' tests/capital/test_reply.py` + `grep -rn "idx28" copycat/capital/reply.py` → 未解析

已逐條複核成立的 PR 自我宣稱(reviewer 核過,無 finding):(1) `pytest -q tests/capital` → 405 passed(相符);(2) mutation(撤 try)→ `2 failed, 5 passed, 100 deselected`,紅的正是兩條新測試;已 `git checkout --` 還原、`grep -c MUTANT` = 0、`git status --porcelain` 空;(3) `ruff check` PASS、`pyright copycat/capital tests/capital` 0 errors(未跑全 repo);(4) 白名單 §3-5 `git diff e600f341...HEAD -- store.py` 只有 docstring / 註解行;§3-1 布林式等價 PASS 但求值順序有一格出入(F-06);(5) 「兩把保險絲都 raise RuntimeError、日盤走 `last_trading_day` 夜盤走 `next_trading_day`」對 `trading_calendar.py:58-80` / `client.py:150-156` 逐行核過;`_calendar()` 只降級 OSError / ValueError,RuntimeError 確為唯一穿出型別;(6) `_on_late_result` 的 `_note_price_type`(:378)在 `_audit`(:391)之前;(7) 全量 3134 / `copycat validate` 42/42 未重跑(需主 tree `out/`)。

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查。

### Codex 對 Opus 的複查結果（對稱化 4.2）

**Codex 複查 Opus 失敗 — 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(本機無 codex)。全部 CC finding 視同 INCONCLUSIVE,改由 4.3b 主 agent 逐條實查:

| Opus # | 原始 severity | 4.3b 判斷 | 備註(他軸為何漏 / 主 agent 實查) |
| --- | --- | --- | --- |
| F-01 | MEDIUM | CONFIRMED(互斥並存為真;哪邊對**未實證**) | 主 agent 第一手:`data/audit/capital-20260827.jsonl` 4991 sell 於 09:00:25 送單、`logs/server-20260827-0814.log` 09:00:25.711 委託 / .838 成交 —— 同日,非跨日樣本;06-10 C 樣本同日。repo 內**沒有**跨日事件樣本,`reply.py:55`「C/D 實測仍為原單日期」與 skill「最新事件日」都只能各自成立在同日觀測 + 機制推論上。lone 解釋:round 1 兩軸的 prompt 由主 agent 把 skill 條目當 ground truth 注入,reviewer 沒被要求去核 skill 本身;本輪 python-reviewer 是從 `grep 委託建立日` 反向撞到 `reply.py:55`。 |
| F-02 | MEDIUM | CONFIRMED | 主 agent grep 五處(見 Action 理由)。lone 解釋:round 1 Spec F-01 只抓 `store.py:82` 一格,主 agent 收修時 grep 的是 `_Agg.date` 不是「委託建立日」字面。 |
| F-03 | MEDIUM | PARTIAL | 推演本身成立(超集關係對 `_price_type_of` 的三項比對逐行核過),但「是否真的拉寬」取決於 F-01 未實證的 idx23 語意 —— 若 idx23 不隨事件變,兩種語意母體相同、原句反而對。改有界句即可,不是選邊。lone 解釋:round 1 Standards S-1 / Spec F-03 都在看保險絲那段,沒有推「他方單」那一半。 |
| F-04 | MEDIUM | CONFIRMED | 主 agent 核 `docs/next-time.md:25-29` 原文與 `git log -1 e600f341`;8 個 SHA `merge-base --is-ancestor` 全 NO。lone 解釋:(b) 拍板 commit 是在本分支 round 1 review **之後**才進 origin/master(push 前 rebase 帶入),round 1 reviewer 看不到;主 agent rebase 後只重跑 gate 沒重讀 next-time 新增段。 |
| F-05 | LOW | CONFIRMED | 主 agent 核 :2081 有 `_freeze_today`、:2108–2130 無。lone 解釋:round 1 Standards F-4 看的是斷言「綁文案」問題並收修成 levelname + seq,沒看日期比對那一行。 |
| F-06 | LOW | CONFIRMED | 主 agent `git show e600f341:copycat/capital/client.py` :902-903 `_today_ymd()` 在 `trade_date=_trade_ymd()` 之前。lone 解釋:round 1 兩軸都核「布林式等價」與「try 只包 `_trade_ymd()`」,沒核參數求值順序。 |
| F-07 | LOW | CONFIRMED(主 agent 再加一組第一手) | audit 08-26 seq `2313209526540` / `2313209679448`、08-27 `2313211157766`、06-10 `2313091595225` → 前 7 位 `2313092` < `2313209` < `2313211` 逐日遞增,seq 全域遞增不重編。lone 解釋:round 1 時 next-time 那段尚未存在(是 round 1 之後主 agent 加的 93861b60),無人審過。 |

## Action Items

**Severity calibration**:
- 6c(移除 / 削弱既有防護類):本 PR 不移除任何 guard(唯一宣告的行為改動是**加**保險絲降級);但 **F-06 是一個未宣告的既有行為變動**(`_today_ymd()` / `_trade_ymd()` 求值順序對調),依 6c 三層查證 —— spec(change-spec §4)只宣告「try 包 `_trade_ymd()`」、PR description 與 commit subject(`fix(capital): 交易日推算保險絲炸掉時價格別標籤退回只記本機日…`)都沒提順序、verification §3-1 宣稱逐 bit 不變 → **非設計意圖,是收修副作用**;新 contract 下沒有人接手「本機日先算」這個 invariant → 結論 = 恢復原序(F-06 修法),severity 維持 LOW(跨午夜一瞬、fail-safe 方向)。其餘六條不涉防護 / guard,6c N-A。
- 6d-1 hedge cap:F-03「若採事件日語意」、F-06「跨午夜那一瞬」為條件 / 窄窗後果 → 不高於 Should;實際落 Nice。
- 6d-3 Must Fix 雙半條件逐條:F-01 重現路徑 = 讀兩個檔看到相反敘述(可重現)/ 阻擋發布 = 否(文件);F-02 同上 / 否;F-03 重現 = 推演、非畫面 / 否;F-04 重現 = 乾淨 clone `git show <sha>` unknown revision(可重現)/ 否(artifact);F-05 重現 = 00:00 前後跑該測試(可重現、窄窗)/ 否(測試衛生,不進 runtime);F-06 重現 = 跨午夜那一瞬送單看候選日集合(理論可重現、未觀測)/ 否(fail-safe 少一候選日);F-07 重現 = N-A(留尾補資料)/ 否。七條「阻擋發布」全否 → 無 Must / Should。
- 6d-2 由 4.3b 取代(6 CONFIRMED + 1 PARTIAL,各有 lone 解釋,零降級)。
- 未驗證前提閘:F-01 / F-03 的 severity 建立在「互斥並存」這個 grep 得到的事實上、不建立在哪邊對,拿掉「哪邊對」的推論不降級;F-07 的「seq 全域遞增」由三日 audit / 樣本第一手支撐,「idx28 = 交易日欄」標未驗證。
- provenance cap N-A(全 authored)。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix（合併前必修）

- 無

### Should Fix（強烈建議）

- 無

### Nice to Have（可選優化）

- F-01 `store.py:356-359` 降成機制描述 + 標未實證;skill `tc4-market-facts:245` 同步降(`copycat/capital/store.py`)
- F-02 `client.py:104` / `models.py:132` / `reply.py:55` / `test_reply.py:43` / `test_store.py:535` 五處統一口徑(`copycat/capital/client.py`)
- F-03 `store.py:359` 改有界句(`copycat/capital/store.py`)
- F-04 verification.md §分支 commit + JSON `fixed_point` / `reviewed_head` 改「第 n 筆 + subject」(`.claude/mod/n075-price-type-label-window/verification.md`)
- F-05 `test_submit_result_survives_trade_day_fuse` 加 `_freeze_today` + 斷 `(_FIXED_YMD,)`(`tests/capital/test_client.py:2127`)
- F-06 `today = _today_ymd()` 提到 try 之前(`copycat/capital/client.py:906`)
- F-07 next-time 08-28 節補 seq 全域遞增(06-10 / 08-26 / 08-27 三日前綴)+ idx28 疑似交易日欄兩點(`docs/next-time.md:9`)

### 參考用（任一軸驗證為 REFUTED 或 OUT_OF_SCOPE）

- 無

## 審查工具比較 (qualitative)

- CC 視角(python-reviewer):七條全在「文件宣稱 vs 程式 / 樣本」這一型,且抓到本 PR 的核心前提(「`_Agg.date` = 最新事件日」)在同套件內有相反實測 —— 這是 in-flow two-axis round 1 結構上抓不到的:round 1 的 prompt 把該前提當 ground truth 注入。reviewer 另獨立重跑 mutation 與 capital 子集,並從 06-10 真樣本讀出 idx28 疑似交易日欄(F-07),是本輪最高價值的觀察。
- Codex / Gemini:N-A。
- 4.3b:CONFIRMED 6 / PARTIAL 1 / 0 降級;七條皆有 lone 解釋(前提由主 agent 注入 / grep 字面不同 / (b) 拍板晚於 round 1 / 收修沒回頭核 / 求值順序未核 / next-time 段晚於 round 1)。
- 對抗式第三軸增益:N-A。

## 沒做的部分（結案對帳）

- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(grep / sed / git show / audit jsonl / server log)。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 以 `py -3.14` 實跑)。
- 真實環境:本 PR 唯一行為改動的觸發條件 = 日曆資料錯,prod 不可無害觸發,未做;prod 8721 仍跑 1ce0c500(不含本 PR)。
- 未驗證前提:**idx23 跨日事件是否變值**(F-01 / F-03 的核心;repo 內零跨日樣本,08-27 唯一可疑筆經 audit + log 核為同日);**idx28 是否為所屬交易日欄**(F-07;僅一筆預約單樣本吻合,`reply.py` 未解析);reviewer 的全量 pytest / `copycat validate` 未重跑(主 agent 於分支上實跑過:3134 passed、42/42)。
- 順帶發現(第一手,建議入 next-time):群益 seq 前 7 位逐日遞增(`2313092` 06-10 / `2313209` 08-26 / `2313211` 08-27),為全域計數 —— N075 誤標窗「撞同 seq」前提實務上不成立。
- Self-Verify:已執行(skill-verify-auditor,dispatch model=sonnet 依 frontmatter)→ `VIOLATIONS: R7`:auditor 指 6c 把 F-06 的求值順序變動當 N-A、6d-3 只有總結沒逐條。修正 = Action Items「Severity calibration」改寫為 6c 三層查證(結論:非設計意圖、恢復原序)+ 6d-3 七條逐列;修正後未重派 auditor,**未經第二次獨立稽查**。
