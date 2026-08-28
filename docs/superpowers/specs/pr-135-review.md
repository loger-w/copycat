# PR #135 Code Review 比較報告 · SHA 6bd565df
**Report projection schema**: 1

**PR**: [loger-w/copycat#135](https://github.com/loger-w/copycat/pull/135)
**標題**: chore(tests): 測試衛生三條 —— test_bars 牆鐘凍結 / index WS 順序 flake / 庫存報告列 fixture 單一定義處
**作者**: loger-w(commits 署名 Loger)
**分支**: `chore/test-hygiene-batch` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 7a069bd1;分支已刪、回溯 review)
**變更**: 12 檔案, +387 / -62
**審查日期**: 2026-08-28
**Review input basis**: source repo R_kgDOTsITBg + 6bd565dfa36b090cef5083038231786bc9eb913a;destination repo R_kgDOTsITBg + 5c0244f1f9dfeb9e6f2194d09ceb3c67c4a2d113;`input_binding: verified`(`git fetch origin refs/pull/135/head` 後 `git worktree add --detach` 於 headRefOid,worktree HEAD = source SHA 逐字相等;destination SHA 為 master 歷史上的既有 commit、`git merge-base --is-ancestor` 成立;`merge-base(base, head)` = destination SHA)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED、分支已刪;origin/master 因本 PR 自身 rebase merge 與後續一筆 chore(skills) 前進到 d34d372c,不影響 PR 的 destination 綁定);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-135`(detached)
**worktree HEAD**: 6bd565dfa36b090cef5083038231786bc9eb913a
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC 軸 finding;4.2 N-A 無 codex → 全部 CC finding INCONCLUSIVE,由 4.3b 主 agent 逐條實查)+ Gemini 軸 N-A(本機無 agy)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer(不切塊,單一 dispatch;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=N-A(security-reviewer 未觸發:無 auth / 請求體 / 憑證路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(未 dispatch);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=12 → covered 3 / no-issues 8 / skipped 1 / **missed 0**(chunked: 否;FILE_COUNT=8 源檔(6 tests + 2 evidence plugin)≤ 15、DIFF_LINES=449 < 800;reviewer 逐檔 accounting 12/12,union = F;skipped = `code-review-round-1.json`(作者 two-axis 紀錄 artifact、非執行碼,reviewer 已讀作去重基準))
**定位 (ENH-B)**: anchored exact 3 / ambiguous 0 / **FAILED 0**(三個 anchor 於 worktree HEAD 以 grep 逐字比中且唯一:test_index_routes.py:100 + :102(兩行 anchor)、balance_rows.py:1、test_bars.py:603;line 以比中結果為準)
**React-doctor (2.97)**: N-A(非 React PR:F 無 `.jsx` / `.tsx`,frontend/ 零 diff)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh <worktree> origin/master` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,12 檔全部 authored)
**審查軸狀態**: primary(python-reviewer)PASS(3 findings、12/12 accounting、三項白名單自核 PASS、111 passed 抽跑);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification:4.1 N-A / 4.2 FAIL→INCONCLUSIVE(無 codex)/ 4.3b PASS(主 agent 逐條 grep / find_spec 實查,三條 CONFIRMED)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus,tools=0)回 R1–R10 全 PASS、`VERDICT: COMPLIANT`;無需補寫

**Report generation**: sha256:b148dcbcc633903763487c787a928a5e54dea217b257456b3c4ce168192e915c

---
## [完整證據副檔](pr-135-review.audit.md)
### finding_uid 索引
[cbeebfa0fb36494afcad](pr-135-review.audit.md#發現總覽) · [c2d358ae7641f163b33d](pr-135-review.audit.md#發現總覽) · [ebcb302dbdd2c5d4c12c](pr-135-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | `test_ws_streams_index_payload` 的 ping `continue` 不計數也無牆鐘上限:`_WS_PRE_QUOTE_MAX` 只計 `type=="index"`,而 relay `_beat` 每 10 s 恆送 ping(本檔未 monkeypatch `WS_HEARTBEAT_SECS`)、repo 無 pytest-timeout —— 本測試要守的迴歸(`_handle_quote` 不再撥 dirty / loop 死)發生時,修前 10 s 後首則 ping 讓 `assert type=="index"` 直接紅,修後永遠拿到 ping → 全量 pytest 掛死。作者 round 1 P-3 只處理「ping 被誤計」沒處理「ping 無限」(`tests/server/test_index_routes.py`) | MEDIUM [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep 本檔無 `WS_HEARTBEAT_SECS`、`ws.py:33 = 10.0`、`find_spec('pytest_timeout') is None`、pyproject 無 timeout;修法局部:ping 另設小上限或整段套 `time.monotonic()` 預算逾時 `pytest.fail` |
| F-02 | `balance_rows.py` docstring 自稱「19 欄字面的**唯一定義處**」,但 `test_client.py:1078`(`3357,T,…,2000,…`)與 `:1103`(`2330,T,…,500,…`)仍內嵌兩列同欄形庫存列 —— 不是被搬走那串的複本,但群益改欄形時同樣靜默留舊形;樣板 `profit_rows.py` 對自己的例外有明寫,本檔沒有(`tests/capital/balance_rows.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep `,A123456789,1234567890"` test_client.py 排除損益列 → :1078 / :1103 兩處;零風險修法 = docstring 比照 profit_rows 明列例外與理由 |
| F-03 | `TestModuleClock::test_default_clock_persists_yesterday` docstring 宣稱「這一條擋 … 別的測試把 `_now_time` 改回真牆鐘」—— 但模組級 autouse 在每條測試 setup 都 `monkeypatch.setattr` 覆寫、teardown 還原,外部洩漏在本檔任一測試執行時都已被蓋掉(verification §1「plugin 重跑 52 passed = plugin 失效」正是這個事實),第三種情境偵測不到(`tests/server/test_bars.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 讀 `_daytime_clock`(:27–30)確認 autouse + monkeypatch 每測試重設;純文件修法 = 刪第三子句 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: cbeebfa0fb36494afcad action=auto-fix
F-02 finding_uid: c2d358ae7641f163b33d action=auto-fix
F-03 finding_uid: ebcb302dbdd2c5d4c12c action=auto-fix
### Inline Comments per Finding（直接複製貼到 PR review）
#### F-01 ping 一直 continue 的話,推播鏈真壞掉時這條測試會掛死而不是變紅
**File**: `tests/server/test_index_routes.py`
**Line**: 100-102

**Comment**:
```
while len(seen) <= _WS_PRE_QUOTE_MAX 只數 type=="index" 的則,ping 走 continue 不計數也沒期限。
relay 的 _beat 是定時恆送(ws.py:33 WS_HEARTBEAT_SECS=10,本檔沒 monkeypatch),receive_json 又是阻塞等
→ 哪天 _handle_quote 不撥 dirty 或 _broadcast_loop 死掉(正是這條要守的迴歸),迴圈每 10 s 拿一則 ping、永遠不收斂,
全量 pytest 直接掛死(repo 沒裝 pytest-timeout、pyproject 也沒 timeout)。修前的形態是首則 ping 撞 assert type=="index" 直接紅。

最省事:給 ping 一個小上限,或整段套牆鐘預算:

deadline = time.monotonic() + 3.0
while len(seen) <= _WS_PRE_QUOTE_MAX:
    assert time.monotonic() < deadline, f"3 s 內沒等到含 p 的 index payload;已收 {seen}"
    ...
```
#### F-02 這份說自己是「唯一定義處」,test_client 裡還有兩列 19 欄庫存字面
**File**: `tests/capital/balance_rows.py`
**Line**: 1

**Comment**:
```
docstring 寫「19 欄字面的唯一定義處」,但 test_client.py:1078 的 "3357,T,0,0,0,0,2000,…" 和 :1103 的
"2330,T,0,0,0,0,500,…" 還是同欄形的庫存列(不是被搬走那串的複本,是另外兩筆合成列)。群益改欄形時這兩列一樣靜默留舊形,
正是這份 docstring 說要消滅的失效樣態。profit_rows.py 對自己的例外是明寫的(「那兩種列留在 test_balance,只有 parser 邊界測試用得到」),這裡沒有對應句。

零風險的改法:docstring 補一句「test_client 另有兩列一次性合成列(:1078 同股號現股 2 張 / :1103 零股 500)留在測試內,只該處用得到」;
或乾脆也收進來當 RAW_T_HELD_2K / RAW_T_ODD_LOT。
```
#### F-03 這句「擋別的測試把 _now_time 改回真牆鐘」其實擋不住
**File**: `tests/server/test_bars.py`
**Line**: 603

**Comment**:
```
第二條哨兵的 docstring 說它擋「別的測試把 _now_time 改回真牆鐘」—— 但模組級 autouse _daytime_clock(:27)每條測試 setup 都
monkeypatch.setattr 蓋回 _DAYTIME、teardown 還原,外部洩漏(他檔永久指派、或 -p freeze_0005 在 import 期改屬性)在本檔任一測試跑的時候都已經被蓋掉了。
verification §1 自己寫的「plugin 重跑 52 passed = plugin 失效」就是這個事實。所以這條實際只擋「凍結點被改到窗內」和「fixture 被刪」兩種。

把第三個子句刪掉就好,純文件、零 code 改動。
```
## 沒做的部分（結案對帳）
- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(grep / sed / find_spec)。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 以 `py -3.14` 實跑;第一次 input 用了複數 `candidates` 形狀回 `C4_CLI_INPUT_INVALID`,改單一 `candidate` + 四欄 `changed_flow_hint` 後得正式 reason code)。
- 真實環境:本 PR 無 UI / API / 生產碼變更,prod 不需為此重啟;無真環境驗證項。
- 未驗證前提:F-01 的「迴歸時掛死」是機制推論(relay 定時 ping + receive 阻塞 + 無 timeout 三件事都第一手核過,但沒實際製造一次迴歸跑到 hang);F-02 的「群益改欄形時靜默留舊形」是 pr-119 F-05 / pr-129 F-02 已實證過的同型後果,本輪未再實證。
- Self-Verify:已執行,COMPLIANT(auditor 只讀本草稿內嵌全文 + 固定 rubric,零 tool call、未讀其他產物);無修正項。
