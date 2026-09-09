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

## Spec 依據

- 偵測到 spec 檔:`.claude/refactor/w3-b2-test-scaffolds/design.md`(路徑在 `.claude/refactor/` 且為 /refactor 流程的設計記錄;內容 = why gate 三段 / 三個 seam 的 interface 與不進 fixture 清單 / 步驟 / round-1 回校)。關鍵:承諾 = **行為絕對不變**(runtime 零觸碰;既有測試名 / 斷言 / 期望數逐字不動,只換料從哪來);Seam 1 `hooks/__fixtures__/day-rollover.ts`(Response 信封不進 fixture;`wrapper` / `newClient` 19 檔重複明列**不在本批**);Seam 2 模組內 async fixture `ws_stream`(不進 conftest);Seam 3 root conftest autouse 守門 + 生效自檢三條(F-01 收)+ 唯一洩漏源補 stop + join。同 PR 內另有 two-axis round-1(`code-review-round-1.json`,Standards 9 + Spec 5,全數接受收修 bd959f64)—— 本輪不重報已修條,只報處置不完整處或新事實。
- **⚠️ spec 作者 = PR 作者**(`git log --format='%an' -- .claude/refactor/w3-b2-test-scaffolds/design.md` = Loger = PR 作者 loger-w;本輪 F-06 的「參考用」判定引 design.md「不進 conftest」論證範圍 + 審查紀律「不改動的既有 code 不報」,未直接以 spec 不做清單免罪;F-03 反過來指出 design.md Interface 記錄過寬 —— 利益重疊方向是「記錄比實作大」,非縮水免罪)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_NORMATIVE_CLAUSE`(design.md 全文 grep `MUST|SHALL|NEVER|必須|不得|恆` 零命中;「行為絕對不變」是流程層承諾、由 Spec 軸與本輪逐字比對承接,非可綁 `path:line` 的實作契約;「不進 fixture」清單為白名單敘述)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool calls=N-A(未派);0 clauses / 0 findings / 0 observations / 0 invalidated。reducer 安全投影要求:未派故無 `human_projection`;本報告零 C4 內容,`invalidated_ids ∩ report_finding_ids = ∅`(兩集合皆空),無 invalidated 語意外洩,C4 對 Step 4.5 覆蓋零貢獻。
- Author calibration(Step 2.2):無作者校準檔(`loger-w.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

provenance: N-A(base = master,13 檔全 authored)。

| 檔案 | 類型 | 說明 |
|---|---|---|
| `frontend/src/hooks/__fixtures__/day-rollover.ts` | 新增 | 三支日 K hook 跨日測試共用鷹架:D / D 14:00 定稿 / D+1 三份快照、`pastMidnight` / `pastDailyFinal`、`snapshotAt` / `snapshotAtWithDailyFinal` / `partialLastAt`、`firstCallsAfterMidnight(n)`、`rerenderBurst` |
| `frontend/src/hooks/useFuturesBars.test.ts` | 測試 | 改吃 fixture;`stubDayFetchThreeWay` 三參數單呼叫點 → `stubDayFetchWithDailyFinal()`;測試名 / 斷言零改動 |
| `frontend/src/hooks/useMarketBars.test.ts` | 測試 | 改吃 fixture;三段 stub 與「午夜 200+空 bars」stub 改用 `snapshotAtWithDailyFinal` / `partialLastAt` / `firstCallsAfterMidnight` |
| `frontend/src/hooks/useStockBars.test.tsx` | 測試 | 改吃 fixture(`{bars, status}` 信封自留) |
| `tests/conftest.py` | 測試基建 | root autouse `_no_leaked_tc4_threads` + 抽出 `leaked_tc4_threads(before, *, join_secs)`;docstring 記快照時點 / autouse 定義順序前提 |
| `tests/test_conftest_guards.py` | 新增 | 守門生效自檢三條(正向 / 負向 / `tc4.py` 字面 parity 不帶 `name=`) |
| `tests/live/test_stock_source.py` | 測試 | `test_subscribe_starts_listener_when_sub_port_known` 補 `try/finally` `_stop.set()` + listener / healer join(唯一洩漏源) |
| `tests/server/test_capital_api.py` | 測試 | `TestWsBroadcasterBackpressure` 八份 `try/finally aclose` 骨架 → 模組內 async fixture `ws_stream`(Protocol 型別、`maxsize` 預設同 ws.py、`on=` 開同顆第二條)+ `_queue_full_warnings`;三行簽名拆行 |
| `docs/next-time.md` | 文件 | 三條勾銷 + 出貨註;記 `StockChart.test.tsx` 四條盤中必紅(baseline 同紅、非本批)+ `wrapper/newClient` 19 檔重複不在本批 |
| `.claude/skills/frontend-testing/SKILL.md` | 文件 | 測試鷹架檔位慣例(跨檔共用 `__fixtures__/`、單檔 colocated `*-test-fixtures.ts`;信封不進 fixture) |
| `.claude/refactor/w3-b2-test-scaffolds/design.md` | 新增 | why gate / 三 seam / 不做清單 / 步驟(含 round-1 回校) |
| `.claude/refactor/w3-b2-test-scaffolds/verification.md` | 新增 | baseline + 兩輪全量 gate + 突變體(前端 3 紅 / 後端 1 紅)+ 守門紅先行 + 動機核對 + baseline 同紅四條記帳 |
| `.claude/refactor/w3-b2-test-scaffolds/code-review-round-1.json` | 新增 | two-axis round-1:Standards 9 + Spec 5 全接受收修 + review 後增量快篩 |

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

#### #6 backpressure 那組測試住在 capital_api 檔裡 —— 但這是本來就在的,不是這個 PR 的帳

**File**: `tests/server/test_capital_api.py`
**Line**: 1092

**Comment**:

```
不是 PR 缺陷,參考用。`TestWsBroadcasterBackpressure` 測的是 `ws.py`,住在 1463 行的 `test_capital_api.py`,
本批把 `ws_stream` fixture 跟 `_queue_full_warnings` 也放進來,看起來像把錯置固化 ——
但 class 在 base 就在這(`git show bebdcd3d:…` :1055),fixture 是模組私有、搬檔時整組一起走零額外成本;
`capital_api.py` 自己也 import `WsBroadcaster` 持兩條 /ws 路由,不算完全無關;`tests/server/` 裡 4348 / 2957 / 2119 行的大檔是常態。
要動的話是下一批 test-hygiene 開 `tests/server/test_ws.py` 把 class + fixture + helper 整組搬過去,不在這個 PR 的帳上。
```

## CC 主軸原始 findings(first-pass, context-aware)

python-reviewer(requested=opus),逐字要點;reviewer 原編號 → 發現總覽:R-01→F-01、R-02→F-02、R-03→F-03、R-04→F-04、R-05→F-05、R-06→F-06。

#### R-01 [LOW] tests/test_conftest_guards.py:14 — 生效自檢測到的是 `tests.conftest` 這份副本,不是守門 fixture 實際呼叫的那顆
問題:`tests/` 無 `__init__.py`,pytest 以 `importmode=prepend` 把 `tests/conftest.py` 載成頂層模組 `conftest`;自檢檔用 `from tests.conftest import` 又載一次 → 同一份原始碼存在兩個 module 物件。實測(自訂 plugin 於 `pytest_sessionfinish` 印):`CONFTEST MODULES: ['conftest', 'tests.conftest']` / 兩個 holder id 不同。影響:目前不 vacuous(兩份編譯自同一檔,改 `_TC4_THREAD_MARKERS` 兩邊同動),但 conftest 頂層被執行兩次,且日後只要守門邏輯沾上 module 級可變狀態 / 被 monkeypatch,自檢就會靜默測到另一份。修法:`leaked_tc4_threads` + 兩顆常數搬 `tests/helpers/threads.py`(該 package 已有 `__init__.py`,既有 `tests.helpers.tc4_fakes` / `frontend_source` 同型)。search-proof:`grep -rn "from tests\.\|import tests\." tests/` → `tests/capital/test_factory.py:22` 已明文警告「經 `import tests.conftest` 拿函式會踩雙重 import,捕到已 patch 的假貨 —— import 常數 `CAPITAL_ENV_KEYS` 無此問題」;`ls tests/helpers/` → `__init__.py boot.py corr_legs.py fake_sources.py fake_txo.py frontend_source.py tc4_fakes.py wait.py`。spec 對照:design.md:69–72(F-01 收:偵測邏輯抽出 + 自檢三條)只談抽函式,未談放哪。anchor:`from tests.conftest import leaked_tc4_threads`

#### R-02 [LOW] tests/conftest.py:105,126 — 快照以 `t.ident` 當身分鍵,ident 會被 OS 回收再用 → 假陰性
問題:`before = {t.ident for t in threading.enumerate()}`,判定 `t.ident not in before`。CPython 的 `ident` 是 OS thread id,Windows 會回收;測試期間某條在 `before` 內的執行緒死掉、之後新起的 TC4 listener 撿到同一個 ident,就被當成「測前就在」而放行。影響:守門靜默漏抓(方向是漏放而非誤紅)。修法:`before = set(threading.enumerate())`,比對改 `t not in before`;`join_secs` 語意不變。search-proof:`grep -rn "threading.Thread" copycat/` → 只有 `tc4.py:638/1185`(無 `name=`)與 `capital/client.py:709`(`name="capital-com"`,不含標記),確認名字比對面本身正確;ident 是唯一的身分弱點。spec 對照:design.md:62–64 只寫「快照 `threading.enumerate()`」,未指定身分鍵。anchor:`        if t.ident not in before and any(m in t.name for m in _TC4_THREAD_MARKERS)`

#### R-03 [LOW] frontend/src/hooks/__fixtures__/day-rollover.ts:16,44-46 — `D1_ISO` / `pastDailyFinal` 兩個 export 零外部消費者
問題:三支測試檔都沒 import 這兩個名字(`pastDailyFinal` 只被同檔的 `partialLastAt` / `snapshotAtWithDailyFinal` 用;`D1_ISO` 只被 `pastMidnight` 用)。影響:公開面比消費者需要的大,與 design.md 自稱的「Interface(小)」相違;eslint 不擋未使用的 export。修法:兩者降成 module-private。search-proof:`grep -rn "\bD1_ISO\b|\bpastDailyFinal\b" frontend/src --include=*.ts*`(排除 fixture 本身)→ 零命中;對照 `partialLastAt` 2 處、`snapshotAt` 4 處、`rerenderBurst` 6 處都有真消費者。spec 對照:design.md:30–34 把 `D1_ISO` 列進 Interface —— 記錄與實況不合(是記錄過寬,不是 code 少做)。anchor:`export const D1_ISO = "2026-08-06";`

#### R-04 [LOW] tests/server/test_capital_api.py:1074-1077 — `on=` 模式下 `maxsize` 被靜默忽略(F-02 處置留下的殘口)
問題:`ws_stream(maxsize=3, on=b)` 會拿到 `b` 既有的 maxsize,`maxsize=3` 無聲失效;Protocol 簽名 `maxsize: int = ..., *, on: ... = ...` 讓兩者看起來可並存。影響:目前唯一 `on=` 呼叫點沒帶 maxsize,所以無症狀;但下一個人照簽名寫就得到一條「參數沒生效」的假綠測試 —— 而 `test_custom_maxsize_applies_to_client_queue` 存在的理由正是「參數被忽略要抓得到」。修法:補一行機械擋 `assert on is None or maxsize == _CLIENT_QUEUE_MAX`。search-proof:`grep -n "ws_stream(" tests/server/test_capital_api.py` → 8 個呼叫點,只有 `_, fast = ws_stream(on=b)` 用 `on=`,無人同時帶兩者。spec 對照:design.md:48–50 宣告 `open(maxsize=..., *, on=None)`,同樣沒說明兩者互斥。anchor:`        maxsize: int = _CLIENT_QUEUE_MAX, *, on: WsBroadcaster | None = None`

#### R-05 [LOW] .claude/refactor/w3-b2-test-scaffolds/verification.md:63 — 行數與實測差 1
問題:寫「三檔 −118 / +62 行(`git diff --stat` 5aa1c08c)」;實測 `git diff --numstat bebdcd3d..5aa1c08c` = `25/42` + `21/40` + `17/37` = +63 / −119(PR HEAD 口徑則是 +65 / −128)。影響:動機核對表的量化數字不可逐字採信;其餘數字(90 passed touched-file、3565 全量、8 份骨架、三條自檢、突變體 3 紅 / 1 紅)另跑 / 另數皆對得上。修法:改成 +63 / −119 並標明是 5aa1c08c 當下口徑。spec 對照:n/a。anchor:`| 日 K 跨日鷹架逐字份數 | 3 檔各一份(常數 + 判定 + 計數器 + rerenderBurst ≈ 40 行 ×3) | fixture 一份;三檔 −118 / +62 行(\`git diff --stat\` 5aa1c08c) |`

#### R-06 [LOW] tests/server/test_capital_api.py:1056-1092 — ws 層鷹架焊進 1463 行的 capital_api 測試檔(Divergent Change)
問題:`TestWsBroadcasterBackpressure` 測的是 `copycat/server/ws.py`,卻住在 `test_capital_api.py`(1463 行,已過 ~1000 行警戒線);ws.py 的另一半測試在 `test_ws_disconnect.py`(1098 行),`tests/server/` 沒有 `test_ws.py`。本批把該類專屬的 fixture + helper 也放進 capital_api,等於把錯置固化。影響:改 ws.py 要同時翻兩個大檔;design.md 只論證了「不進 conftest」,沒論證「該不該搬到 ws 自己的檔」。修法(下一批):新開 `tests/server/test_ws.py` 整組搬過去。search-proof:`ls tests/server/` 40 檔無 `test_ws.py`;`grep -n "WsBroadcaster" tests/server/test_ws_disconnect.py` → :45 / :861;`wc -l` 1463 / 1098。spec 對照:design.md:52–53「不進 conftest:唯一使用者是這個 class」—— 論證方向只到 conftest,未及檔位。anchor:`class TestWsBroadcasterBackpressure:`

#### 行為不變驗證(reviewer 自跑)
逐條比對三支前端測試的 diff:測試名、`expect` 斷言、次數(`toBe(1)/(2)`)、`advanceTimersByTimeAsync` 數列全逐字未動,唯一字面改動是 `D_FINAL` → `D_FINAL_SNAPSHOT`。helper 等價性:`firstCallsAfterMidnight(n)` 的 `if (!pastMidnight() || left <= 0) return false; left -= 1;` 與原 `if (d1 && failLeft > 0) { failLeft -= 1; … }` 同義(午夜前不遞減、`n=0` 恆 false 皆保留);`snapshotAtWithDailyFinal` = `d1 ? D1 : afterFinal ? D_FINAL : D`、`partialLastAt` = `d1 || !afterFinal` 逐字對應;`D_FINAL_SNAPSHOT` 值與三檔原 inline 值相同。原本一次 `new Date()` 拆成兩次在 `vi.useFakeTimers()` 下時間凍結,無差。後端八條:`caplog.at_level` 範圍、`monkeypatch.setattr` 位置、`b.dropped` / `b.window_dropped` 數值全未動;`WsBroadcaster()` → `ws_stream()` 等價因 `ws.py:53 __init__(maxsize: int = CLIENT_QUEUE_MAX)`。唯一不同是 teardown 順序(原 `slow` → `fast`,現 `reversed(opened)` = fast → slow),`aclose()` 只把自己的 queue 從 `_clients` 移除,順序無關。實跑 `pytest tests/test_conftest_guards.py tests/live/test_stock_source.py tests/server/test_capital_api.py::TestWsBroadcasterBackpressure` → 90 passed,與 verification.md §2b 一致。

### Per-file accounting(13/13,reviewer 原文要點)

- `.claude/refactor/w3-b2-test-scaffolds/code-review-round-1.json` — REVIEWED_NO_ISSUES(14 條處置與 commit `bd959f64` 內容逐條對得上;`increment_after_review` 已覆蓋 review 後三筆)。
- `.claude/refactor/w3-b2-test-scaffolds/design.md` — R-03(Interface 記錄過寬)。
- `.claude/refactor/w3-b2-test-scaffolds/verification.md` — R-05。
- `.claude/skills/frontend-testing/SKILL.md` — REVIEWED_NO_ISSUES(「fixture 檔在 src/ 下 import vitest 沒問題」有先例:`components/corr/river-test-fixtures.ts:1` 同樣 `import { vi } from "vitest"`;`vite.config.ts` `include: ["src/**/*.test.{ts,tsx}"]` 不會收走 fixture)。
- `docs/next-time.md` — REVIEWED_NO_ISSUES(三條勾銷與實作對得上;「到 09-09 已長成八份」= 該 class 實際 8 條;「test_capital_api 非 test_ws_disconnect」的筆誤更正正確)。
- `frontend/src/hooks/__fixtures__/day-rollover.ts` — R-03。
- `frontend/src/hooks/useFuturesBars.test.ts` — REVIEWED_NO_ISSUES。
- `frontend/src/hooks/useMarketBars.test.ts` — REVIEWED_NO_ISSUES。
- `frontend/src/hooks/useStockBars.test.tsx` — REVIEWED_NO_ISSUES。
- `tests/conftest.py` — R-01 / R-02。
- `tests/live/test_stock_source.py` — REVIEWED_NO_ISSUES(`try/finally` 只包住原兩行,`_stop.set()` + join(3.0) 對 listener / healer 兩條;`_heal_loop` 是 `while not self._stop.wait(poll)`,`set()` 後立即返回 → 不會吃滿 3 s)。
- `tests/server/test_capital_api.py` — R-04 / R-06。
- `tests/test_conftest_guards.py` — R-01。

## 內部複查結果(同軸 code-reviewer,取代 4.2;非跨軸證據)

| # | 原編號 | Verdict | 原始 → 校正 severity | Evidence(要點) | baseline | 單軸可信度 |
|---|---|---|---|---|---|---|
| F-01 | R-01 | CONFIRMED | LOW → LOW | `pyproject.toml:30-33` 只設 `testpaths` / `pythonpath=["."]`,無 `importmode`(預設 prepend);`tests/__init__.py` 不存在(`tests/capital/` `tests/helpers/` 有)。插件實測 `pytest_sessionfinish` 掃 `sys.modules`:`HOLDERS: ['conftest', 'test_conftest_guards', 'tests.conftest']`,module id 兩個、function id 兩個;`conftest.py:112` autouse 用 `conftest` 那份、`test_conftest_guards.py:14` 測 `tests.conftest` 那份;三條自檢只有字面 parity 那條不受影響。今日不 vacuous(同檔兩份無法分歧) | 慣例衝突(既有兩處 `from tests.conftest import` 拿的是常數 `CAPITAL_ENV_KEYS` 與 mark `requires_tcpy`;`tests/capital/test_factory.py:22` 逐字警告拿函式會踩雙重 import;修法 `tests/helpers/threads.py` 符合六檔 `from tests.helpers.tc4_fakes import` 既有慣例) | 高,可單軸信(可執行復現 + repo 內既有反例註解,非品味) |
| F-02 | R-02 | CONFIRMED | LOW → LOW | `threading.Thread.ident.__doc__` 逐字「may be recycled when a thread exits and another thread is created」;`conftest.py:126` 存 ident 集、`:105` 判定;假陰性路徑成立,需雙巧合;漏抓 = 退回改前狀態不誤紅;改存 Thread 物件正解 | 無先例(`grep "\.ident\b" tests copycat` 只有本 PR 新增 4 處) | 高(文件明文 + 一行修法),但屬「理論風險 vs 複雜度」取捨 |
| F-03 | R-03 | CONFIRMED | LOW → LOW | `grep -rn "D1_ISO\|pastDailyFinal" frontend/src` 兩者僅在 `day-rollover.ts` 內部;三檔 import 清單(`useFuturesBars.test.ts:10-17` / `useMarketBars.test.ts:8-16` / `useStockBars.test.tsx:8-15`)皆無;design.md Seam 1 確實列入。零行為 / 零型別風險;eslint 無 unused-export 規則 | 慣例支持(弱):repo 唯一另一支共用前端測試 helper `frontend/src/test-utils.tsx` 兩 export 皆有消費者(`wrap` 39 / `fillOf` 3),樣本僅 2 | 事實可單軸信;「要不要降 private」是品味 |
| F-04 | R-04 | CONFIRMED | LOW → LOW | `test_capital_api.py:1074-1076` `b = on if on is not None else WsBroadcaster(maxsize=maxsize)`;Protocol `:1059-1062` 兩參數並列;9 個呼叫點無一同時傳(`:1116` 只 `on=b`),今日無實害;docstring `:1067-1069` 寫明用途但只擋人 | 無先例(fixture 本批新生);design.md Seam 2 明列此 interface、F-02 已查證非 speculative generality,未排除本條 | 中 —— 事實無爭議,「為零個現存誤用加 assert」是取捨 |
| F-05 | R-05 | CONFIRMED | LOW → LOW(文件層) | `git diff --numstat bebdcd3d..5aa1c08c` 三檔 25/42 + 21/40 + 17/37 = +63 / −119;`--stat` 印 63 insertions / 119 deletions;`5aa1c08c^..5aa1c08c` 同;HEAD 口徑 +65 / −128;兩 range 皆產不出 62/118 = 筆誤 | 慣例支持(verification 文件慣例要求可重跑指令對得上輸出) | 高,機械可驗 |
| F-06 | R-06 | PARTIAL | LOW → 參考用 / next-time | 事實半邊成立(`wc -l` 1463 / 1098,class 在 `:1092`);但 (1) `git show bebdcd3d:tests/server/test_capital_api.py` 已有該 class(`:1055`,檔長 1450),本 PR 未加深錯置、fixture 模組私有搬檔零額外成本;(2) `test_ws_disconnect.py:1-19` 測的是突斷 / relay / graceful shutdown 非 backpressure,且 `capital_api.py:50,384-413` 自己 import `WsBroadcaster` 持 `/ws/capital` `/ws/futures`,放此非全然無關;(3) 審查紀律「不改動的既有 code 除非 CRITICAL 否則不報」→ 歸 next-time | 慣例支持現狀(`tests/server/` 4348 / 2957 / 2119 行多主題大檔是常態,1463 非離群) | 低—中 —— Divergent Change 在此 repo 是品味議題,需 user 拍板 |

## Action Items

Severity calibration:6c(移除既有防護類)— 本 PR 無此類 finding,免(守門是**新增**防護,F-02 談的是它的盲點不是移除)。6d-1(hedge cap)— F-01「日後沾上 module 級狀態」、F-02「舊執行緒剛好死 + TID 重用」、F-04「下一個人照簽名寫」皆為條件句,已在 Nice;F-06 已在參考用。6d-3(Must Fix 雙半條件)— 六條皆無 user-visible 重現路徑(全在測試基建 / fixture surface / 文件層),零阻擋出貨,無一落 Must / Should。未驗證前提檢查:F-01 插件實測、F-02 stdlib docstring 逐字、F-03 grep、F-04 讀碼、F-05 numstat 皆第一手,拿掉任何論據等級不變(已是 LOW);F-06 的「錯置」判定建立在品味,已標 PARTIAL + 參考用。Provenance cap:N-A。校準套用:無作者校準檔(`loger-w.md` 不存在)、本輪無套用。4.3b lone finding:本場 CC 單軸,六條全 lone,「他軸為何漏」改答單軸可信度(見內部複查表末欄);F-01 / F-02 / F-05 可獨立採信(可執行復現 / 文件逐字 / 機械比對);F-03 / F-04 事實可信、處置是品味,F-03 標 ask-user;F-06 PARTIAL 落參考用。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

無。

### Nice to Have(可選優化)

- **F-01** `leaked_tc4_threads` + 兩顆常數搬 `tests/helpers/threads.py`,conftest 與 `test_conftest_guards.py` 改 `from tests.helpers.threads import`(消除雙重 import;與 `test_factory.py:22` 既有警告同口徑)。
- **F-02** `conftest.py` 快照改存 Thread 物件(`before = set(threading.enumerate())` / `t not in before`),`leaked_tc4_threads` 簽名的 `before: set[int | None]` 改 `set[threading.Thread]`,自檢兩條同步。
- **F-03** `D1_ISO` / `pastDailyFinal` 降 module-private **或** 只改 design.md Interface 段 —— 二選一,user 拍板(`ask-user`)。
- **F-04** `ws_stream` 內補 `assert on is None or maxsize == _CLIENT_QUEUE_MAX`。
- **F-05** `verification.md:63` 改「+63 / −119(5aa1c08c 口徑;HEAD +65 / −128)」。
- 五條可併一筆 `chore(test)` / `chore(docs)` 收修(零 runtime 改動,不需重啟 prod、不需 build)。

### 參考用(任一軸驗證為 REFUTED / OUT_OF_SCOPE / PARTIAL 且不建議動 code)

- **F-06** `TestWsBroadcasterBackpressure` 住在 `test_capital_api.py`:CC 主軸判 Divergent Change 固化 → 內部複查於 base `bebdcd3d` 找到 class 本就在此(:1055)、`capital_api.py` 自持兩條 /ws 路由、`tests/server/` 大檔為常態 → 使用者自行判斷是否要開 `tests/server/test_ws.py` 搬整組(建議記 next-time 併下一個 test-hygiene 批,不動本 PR)。

## 審查工具比較(qualitative)

- CC 主軸(python-reviewer):context-aware;核心問題(行為不變)以逐字 diff 比對 + helper 等價推導 + touched-file pytest 90 passed 自證;六條 finding 全是「守門機制的盲點」(雙重 import / ident 重用)、「fixture surface 記錄 vs 實況」與「文件數字可重跑性」—— 純看 diff 抓不到(要對照 `test_factory.py:22` 既有註解、stdlib 文件、numstat)。
- 內部複查(code-reviewer):同軸、非跨軸證據;6/6 齊,CONFIRMED 5 / PARTIAL 1 / REFUTED 0 / OUT_OF_SCOPE 0;severity 零下修(全 LOW);一條以插件實測落地(F-01 `sys.modules` 雙 holder)、一條找到 base 即在的反證(F-06)。
- Codex / Gemini:N-A(user 停用),無跨軸重疊率可算;對抗式增益 N-A。
- REFUTED 率 0%(PARTIAL 17%):主軸命中率高,但同模型家族互驗,且六條全 LOW 測試基建 / 文件層 —— 對一個所有 gate 綠 + 逐字比對零差異的純測試重構,這個分佈是預期的。

## 沒做的部分(結案對帳)

- Codex 中性軸:N-A —— user 明示停用(沿 #188 / #190 / #199 / #202 / #211 / #218 / #220 前例),未起軸、未 retry。
- Codex 對抗式軸:N-A —— 同上。
- Gemini Flash 軸:N-A —— user 明示停用。Gemini Pro:N-A(同上;Step 2.96 依前例不再問)。
- Step 2.98 Codex preset 詢問:N-A(Codex 停用,依前例不再問)。
- Cross-axis verification 4.1:N-A(無非 CC finding)。4.2:以同軸 code-reviewer 內部複查代替(PASS,6/6),**非跨軸證據**。4.3a consensus:N-A(單軸無 consensus);4.3b lone:六條全 lone,處置見 Action Items。
- Review input binding:**verified**(`refs/pull/222/head` = headRefOid `43528ea7`,worktree detached 於該 SHA;merge-base = baseRefOid `bebdcd3d`)。
- Blast radius(2.9):PASS(有跑)但空輸出跳過(`sem` 未安裝)。
- React-doctor(2.97):PASS,未引入新問題(`newCount 0`,changed 4 檔;既有 0 條)。
- Formal spec traceability(2.65):SKIPPED (C4_NO_NORMATIVE_CLAUSE);spec-compliance-reviewer 未派。
- Author calibration(2.2):無檔、本輪無套用。
- Reviewer 未重跑全量 pytest / ruff / pyright / validate / vitest:review worktree 純讀碼(primary 只跑 touched-file pytest 90 passed;內部複查跑 `tests/test_conftest_guards.py` + `test_capital_api.py` 87 passed 與一次性 `sys.modules` 插件);全量綠燈證據引自 PR 內 `verification.md`(出貨前實跑 pytest 3565 passed / 3 skipped、ruff 0、pyright 0、validate 42/42、vitest 3065 / 4 failed baseline 同紅、突變體前端 3 紅 / 後端 1 紅)。
- 未驗前提(集中揭露):F-01「日後守門邏輯沾上 module 級可變狀態」與 F-04「下一個人照簽名寫」是條件句;F-02「測前執行緒死亡 + TID 重用」是文件允許但未在本 suite 觀測到的情境;F-06「Divergent Change」是品味判定。皆已對應降到 Nice / 參考用。
- 真環境:純測試改動、runtime 零觸碰;prod 不需重啟、dist 不需 build;本 review 未另跑 server。
- Self-Verify:已執行(`skill-verify-auditor`,requested=opus / observed=UNAVAILABLE;唯讀、只 Read 本草稿檔一次,1 tool 呼叫)。R1–R10 全 PASS、`VERDICT: COMPLIANT`,零修正;未重派 auditor。
