# PR #222 Code Review 比較報告 · SHA 43528ea7
**Report projection schema**: 1

**PR**: [loger-w/copycat#222](https://github.com/loger-w/copycat/pull/222)
**標題**: refactor(test): W3 B2 測試鷹架批 —— 日 K 跨日 fixture / ws_stream fixture / TC4 _listen_loop 執行緒守門
**作者**: loger-w
**分支**: `refactor/w3-b2-test-scaffolds` → `master`
**變更**: 13 檔案, +604 / -252
**審查日期**: 2026-09-09
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨;merge commit `d994fa7e`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `43528ea70afe54c37c6fc234dbe1f1d2c3ac7701`;destination repo id `R_kgDOTsITBg` + baseRefOid `bebdcd3d0786698cf7ff3cfc6e38a23cdf8f1e4c`;`input_binding: verified` —— `git fetch origin refs/pull/222/head` 取回的 FETCH_HEAD = headRefOid 逐字相等,review worktree detached 於該 SHA,`git merge-base origin/master HEAD` = baseRefOid
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 SHA;分支已隨 `--delete-branch` 刪除,但 `refs/pull/222/head` 仍指 `43528ea7`,產報告前重抓 headRefOid 仍為它);`base_changed=true`(origin/master 自 `bebdcd3d` 前進至 `d994fa7e`,內容 = 本 PR 自身 8 筆 rebase 後 commit,其後零新 commit);`review_context_changed=false`(審的是 PR head,與落地版逐檔等價)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用,沿 #188 / #190 / #199 / #202 / #211 / #218 / #220 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .py 57% / .ts+.tsx 43% 的 source diff 行,單派不 chunk、指示涵蓋全部 13 檔);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE;純讀碼 + grep + 一次性 pytest 插件實測);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=13 → covered 6 / no-issues 7 / skipped 0 / **missed 0**(chunked: **否**,8 source 檔 / 651 source diff 行(.py 370 / .ts+.tsx 281),低於 15 檔 / 800 行門檻;13/13 per-file accounting 齊)
**定位 (ENH-B)**: anchored exact 6 / ambiguous 0 / **FAILED 0**(六條 anchor 在 worktree 逐字唯一命中:test_conftest_guards.py:14 / conftest.py:105 / day-rollover.ts:16 / test_capital_api.py:1075(reviewer 自報 1074-1077,校正為 1075)/ verification.md:63 / test_capital_api.py:1092(reviewer 自報 1056-1092,校正為 1092))
**React-doctor (2.97)**: 未引入新問題(既有 0 條不計;`npx -y react-doctor@latest . --offline --no-score --scope changed --base bebdcd3d --json` 於 review worktree `frontend/` 執行,`newCount 0 / fixedCount 0 / baseTotalCount 0`,changedFileCount 4)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_CLAUSE)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出;`sem` 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer)PASS(6 findings + 13/13 accounting;另自跑 touched-file pytest 90 passed 與行為不變逐字比對)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 請求體解析 / 秘鑰讀取)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(6/6 verdict 齊、ID 集合精確相等、每列六欄齊)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-222`
**worktree HEAD**: `43528ea70afe54c37c6fc234dbe1f1d2c3ac7701`

**Report generation**: sha256:0032860aabff0b8e949a040075d5c1de091d282757834ca993125704cb52324e

---
## [完整證據副檔](pr-222-review.audit.md)
### finding_uid 索引
[be7c888a2027a42917b2](pr-222-review.audit.md#發現總覽) · [00e588a7898ba155cd6e](pr-222-review.audit.md#發現總覽) · [8d94a37068e9942c2644](pr-222-review.audit.md#發現總覽) · [9b15736ec086c503f068](pr-222-review.audit.md#發現總覽) · [ddb0912a04572b637e67](pr-222-review.audit.md#發現總覽) · [677191e925e52f97155d](pr-222-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `test_conftest_guards.py:14` 自檢 `from tests.conftest import leaked_tc4_threads` 拿到的是 **第二個 module 物件**(`tests/` 無 `__init__.py`、importmode 預設 prepend → `conftest` 與 `tests.conftest` 兩份),守門 fixture 用的是 `conftest` 那份;`tests/capital/test_factory.py:22` 既有註解已明文警告「經 `import tests.conftest` 拿**函式**會踩雙重 import」,本 PR 是第一次以此路徑拿函式 | LOW | CONFIRMED(LOW→LOW:插件實測 `HOLDERS: ['conftest', 'test_conftest_guards', 'tests.conftest']`、兩個 module id / 兩個 function id;今日不 vacuous(同檔兩份無法分歧),風險只在 module 級可變狀態 / monkeypatch) | Nice to Have | `auto-fix` | 修法明確且有既有慣例:`leaked_tc4_threads` + 兩顆常數搬 `tests/helpers/threads.py`(有 `__init__.py`),conftest 與自檢各 import 同一物件 |
| F-02 | `conftest.py:105` 守門以 `t.ident` 當身分鍵;stdlib 文件明寫 ident「may be recycled when a thread exits and another thread is created」→ 測前存在的執行緒在該測試內死亡、新起的 listener 撿到同 ident 會被當「測前就在」放行(假陰性,方向是漏放非誤紅) | LOW | CONFIRMED(LOW→LOW:`threading.Thread.ident.__doc__` 逐字;需「舊執行緒剛好死 + TID 剛好重用」雙巧合;漏抓 = 退回改前狀態,不會誤紅;repo 內無其他 `.ident` 用法可對照) | Nice to Have | `auto-fix` | 一行改 `before = set(threading.enumerate())` + `t not in before`,`join_secs` 語意不變;多留 dead Thread 參考無害 |
| F-03 | `day-rollover.ts:16` `D1_ISO` 與 `:44` `pastDailyFinal` 兩個 export 零外部消費者(三檔 import 清單皆無;`pastDailyFinal` 只被同檔 `partialLastAt` / `snapshotAtWithDailyFinal` 用);design.md Seam 1 Interface 段把兩者列入 = 記錄過寬 | LOW | CONFIRMED(LOW→LOW:grep 全 `frontend/src` 只命中 fixture 內部;其餘 export 全有消費者;eslint 無 unused-export 規則不會紅;repo 唯一另一支共用 helper `test-utils.tsx` 兩 export 皆有消費者,樣本僅 2) | Nice to Have | `ask-user` | 「降 module-private」與「只改 design.md Interface 描述」兩條路都成立,是 API surface 品味;內部複查建議交 user |
| F-04 | `test_capital_api.py:1075` `ws_stream(maxsize=3, on=b)` 時 `maxsize` 被靜默忽略(`b = on if on is not None else WsBroadcaster(maxsize=maxsize)`),Protocol 簽名讓兩者看似可並存;現有 9 個呼叫點無一同時傳(`:1116` 只帶 `on=b`),今日無實害 | LOW | CONFIRMED(LOW→LOW:事實無爭議;docstring `:1067-1069` 已寫明 `on=b` 用途但只擋人不擋機器;為零個現存誤用加 assert 屬取捨) | Nice to Have | `auto-fix` | 一行 `assert on is None or maxsize == _CLIENT_QUEUE_MAX`,與 `test_custom_maxsize_applies_to_client_queue` 存在的理由(參數被忽略要抓得到)同方向 |
| F-05 | `verification.md:63` 動機核對表寫「三檔 −118 / +62 行(`git diff --stat` 5aa1c08c)」,實測 `git diff --numstat bebdcd3d..5aa1c08c` 三檔 = 25/42 + 21/40 + 17/37 = **+63 / −119**,`--stat` 同樣 63 / 119;HEAD 口徑 +65 / −128 亦不是 62/118 | LOW | CONFIRMED(LOW→LOW:兩個候選 range 都產不出 62/118,是筆誤非口徑差;動機核對表其餘數字(90 / 3565 / 8 份 / 3 條 / 3 紅 1 紅)複核皆對) | Nice to Have | `auto-fix` | 改「+63 / −119」並標 5aa1c08c 口徑(HEAD 口徑不同,因 F-04 後又刪了 futures 三段 stub 參數) |
| F-06 | `test_capital_api.py:1092` `TestWsBroadcasterBackpressure`(測 `ws.py`)住在 1463 行的 capital_api 測試檔,本批把 `ws_stream` + `_queue_full_warnings` 也放進去 = 錯置固化(Divergent Change);`tests/server/` 無 `test_ws.py` | LOW | PARTIAL(LOW→參考用:**class 在 base 就在**(`git show bebdcd3d:…:1055`,檔長 1450),本 PR 未加深錯置、fixture 模組私有搬檔零額外成本;`capital_api.py` 自己 import `WsBroadcaster` 並持 `/ws/capital` `/ws/futures` 兩條路由,非全然無關;`tests/server/` 4348 / 2957 / 2119 行多主題大檔是常態,1463 非離群) | 參考用 | `no-op` | 既有結構非本 PR 缺陷;「開 `tests/server/test_ws.py` 搬整組」是下一批 test-hygiene 候選,user 拍板才動 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: be7c888a2027a42917b2 action=auto-fix
F-02 finding_uid: 00e588a7898ba155cd6e action=auto-fix
F-03 finding_uid: 8d94a37068e9942c2644 action=ask-user
F-04 finding_uid: 9b15736ec086c503f068 action=auto-fix
F-05 finding_uid: ddb0912a04572b637e67 action=auto-fix
F-06 finding_uid: 677191e925e52f97155d action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 自檢 import 到的是 conftest 的第二份副本,不是守門真正用的那顆
**File**: `tests/test_conftest_guards.py`
**Line**: 14

**Comment**:
```
`tests/` 沒有 `__init__.py`,pytest 預設 prepend 模式把 `tests/conftest.py` 載成頂層 `conftest`;
這裡再 `from tests.conftest import` 就多載一份 → `sys.modules` 同時有 `conftest` 跟 `tests.conftest` 兩個物件,
守門 fixture 跑的是前者、自檢測的是後者(實測兩個 function id 不同)。今天不會假綠(同一檔案編出來的兩份改不出差異),
但 F-01 要擋的就是「靜默」—— 哪天守門邏輯沾上 module 級狀態或被 monkeypatch,自檢就測到另一份。
`tests/capital/test_factory.py:22` 早就寫著「經 `import tests.conftest` 拿函式會踩雙重 import,拿常數才安全」。

把 `leaked_tc4_threads` + `_TC4_THREAD_MARKERS` / `_TC4_THREAD_JOIN_SECS` 搬去 `tests/helpers/threads.py`
(那個 package 有 `__init__.py`,`tc4_fakes` / `frontend_source` 都住那),conftest 跟自檢一起 `from tests.helpers.threads import`。
```
#### #2 用 ident 當身分鍵,OS 會回收 → 有機會漏放新起的 listener
**File**: `tests/conftest.py`
**Line**: 105

**Comment**:
```
`threading.Thread.ident` 文件明寫「may be recycled when a thread exits and another thread is created」。
測前就在的某條執行緒在這條測試裡死掉、之後新起的 `_listen_loop` 撿到同一個 id → `t.ident not in before` 為 False,被當「測前就在」放行。
方向是漏抓不是誤紅,機率也低,但這支 fixture 的價值就是不靜默。

改存物件就好:

    before = set(threading.enumerate())
    ...
    if t not in before and any(m in t.name for m in _TC4_THREAD_MARKERS)

單條測試期間多握幾個 dead Thread 參考無害,`join_secs` 那半不用動。
```
#### #3 `D1_ISO` 跟 `pastDailyFinal` export 了但沒人用
**File**: `frontend/src/hooks/__fixtures__/day-rollover.ts`
**Line**: 16

**Comment**:
```
三檔測試的 import 清單都沒有這兩個名字;`D1_ISO` 只被同檔 `pastMidnight` 用、`pastDailyFinal` 只被 `partialLastAt` / `snapshotAtWithDailyFinal` 用。
design.md Seam 1 的 Interface 段卻把它們列進去 —— 記錄比實作大。eslint 沒有 unused-export 規則,之後只會愈長愈大。

兩條路:把 `export` 拿掉降成 module-private(註解留著說明 14:00 界的來源),或只改 design.md 把它們移出 Interface。看你要哪一種。
```
#### #4 `ws_stream(maxsize=…, on=b)` 兩個一起給時 maxsize 會靜默失效
**File**: `tests/server/test_capital_api.py`
**Line**: 1075

**Comment**:
```
`b = on if on is not None else WsBroadcaster(maxsize=maxsize)` —— `on` 給了 `maxsize` 就沒人看,Protocol 簽名又讓兩個看起來能並存。
現在 9 個呼叫點沒人同時傳,所以沒事;但下一個照簽名寫 `ws_stream(maxsize=3, on=b)` 的人會拿到一條參數沒生效的假綠測試,
而 `test_custom_maxsize_applies_to_client_queue` 存在的理由正是「參數被忽略要抓得到」。

補一行機械擋就好:

    assert on is None or maxsize == _CLIENT_QUEUE_MAX, "on= 模式沿用既有 broadcaster,不吃 maxsize"
```
#### #5 動機核對表的行數差 1
**File**: `.claude/refactor/w3-b2-test-scaffolds/verification.md`
**Line**: 63

**Comment**:
```
表裡寫「三檔 −118 / +62 行(git diff --stat 5aa1c08c)」,實跑 `git diff --numstat bebdcd3d..5aa1c08c` 三檔是 25/42 + 21/40 + 17/37 = +63 / −119,
`--stat` 也印 63 / 119;HEAD 口徑是 +65 / −128,兩個 range 都湊不出 62/118,是筆誤。
改成「+63 / −119(5aa1c08c 當下口徑;HEAD 口徑 +65 / −128,F-04 後又刪了 futures 三段 stub 參數)」。
```
