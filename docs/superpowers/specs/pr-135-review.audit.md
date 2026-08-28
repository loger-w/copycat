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

## Spec 依據

- 偵測到 `.claude/chore/test-hygiene-batch/change-spec.md`(= handoff 複本:§2 A / B / C 三條的精確位置與修法(A 兩擇一建議 autouse、B 兩擇一建議「先吃快照」、C 開 `balance_rows.py`)、§3 分支與 commit 分組(test 紅先行獨立 / 🔵 refactor / chore)、§4 gate、§5 SHA dangling 拍板 (b))。非目標:「**不准**改 `bars.py`」(A)、「斷言一條都不動」(C)。
- ⚠️ spec 作者 = PR 作者(handoff 由前一 session 同 agent 產出、commit 署名 Loger 同 PR 作者;`git log --format=%an -- change-spec.md` → Loger)。本 PR 兩處刻意偏離 spec(B 修法 (1)→(2)、A parametrize→哨兵)由作者自己的 two-axis review 判定成立 —— 審報告的人要知道這層同源;本輪 python-reviewer 對 B 的偏離另行 trace 過 `app.py::ws_index` / `index.stream()` 無 seed,結論同意。
- `SPEC_COMPLIANCE` receipt:gate=SKIPPED;dispatch=NOT_APPLICABLE;dispatch_count=0;reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED(reducer `resolve-authority` 以 `py -3.14` 實跑,候選 = change-spec §2.A:37「**不准**改 `bars.py`」NORMATIVE_KEYWORD;回 `{"clause": null, "reason_code": "C4_AUTHORITY_PATH_NOT_ALLOWED", "status": "SKIPPED"}`:spec 位於 `.claude/chore/<slug>/`,不在 `openspec/specs/**` / `openspec/changes/**` 允許路徑);requested_model=opus;observed_model=UNAVAILABLE;effort=xhigh;tools=0;0 clauses / 0 findings / 0 observations / 0 invalidated

## 變更概要

provenance:12 authored / 0 inherited(base = master,免驗)。

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `tests/server/test_bars.py` | 有 finding(修改) | 模組級 autouse `_daytime_clock` 凍 `bars._now_time` → 09:00(`_DAYTIME`);新 `TestModuleClock` 兩條哨兵(`== _DAYTIME` 且 `>= MIDNIGHT_BUFFER_END`;`build_minute` 真路徑永久化 yesterday);第二條 docstring 第三子句宣稱擋不住的情境(F-03) |
| `tests/server/test_index_routes.py` | 有 finding(修改) | `test_ws_streams_index_payload` 改「收到含 `p` 的那則為止」:`_WS_PRE_QUOTE_MAX = 5` 只計 index 則、ping `continue` 不計;docstring 校正「`/ws/index` 無 seed 快照」;ping 分支無計數無牆鐘(F-01) |
| `tests/capital/balance_rows.py` | 有 finding(新增) | 六常數 `RAW_T_BOUGHT` / `RAW_T_FLAT` / `RAW_C_MARGIN` / `RAW_L_SHORT` / `RAW_END` / `RAW_T_HELD`,docstring 引 balance.py 檔頭欄位語意;「唯一定義處」宣稱超出實況(F-02) |
| `tests/capital/test_balance.py` | 無 finding(修改) | 刪五個常數定義、改 import balance_rows;六處 `.replace` 變異未動(作者記 next-time) |
| `tests/capital/test_client.py` | 無 finding(修改) | 內嵌 12 處 + `_BAL_3357` 8 引用 + `_BAL_2493` 3 引用全換常數(reviewer AST 比對 13 處 byte-equal → HEAD 0 處);import 置 `fake_com` 前合字母序 |
| `tests/capital/test_fill_latency.py` | 無 finding(修改) | `_BAL_ROW` → `RAW_T_HELD`(byte-equal 78) |
| `docs/next-time.md` | 無 finding(修改) | 三條勾銷 `~~原文~~ → 結論` 形;新 08-28 節兩條留尾(`balance_variant` / `/ws/index` 首則語意待查) |
| `.claude/chore/test-hygiene-batch/change-spec.md` | 無 finding(新增) | handoff 複本(spec) |
| `.claude/chore/test-hygiene-batch/verification.md` | 無 finding(新增) | §0 白名單 / §1–§3 三條證據 / §4 commit 分組 / §5 三輪 gate(3136 → 3137 → 3139)/ §6 事故 / §7 two-axis;reviewer 自跑數字一致 |
| `.claude/chore/test-hygiene-batch/code-review-round-1.json` | INTENTIONALLY_SKIPPED(新增) | 作者 two-axis round 1:Standards 8 / Spec 4 處置紀錄;非執行碼、作去重基準 |
| `.claude/chore/test-hygiene-batch/evidence/freeze_0005.py` | 無 finding(新增) | A 紅先行 plugin(`bars._now_time` 釘 00:05);不在 `testpaths` |
| `.claude/chore/test-hygiene-batch/evidence/race_index_ws.py` | 無 finding(新增) | B 紅先行 plugin(猴補 `IndexEngine.stream` 撥 dirty + quote 延 50 ms);不在 `testpaths` |

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

### Opus 原始 findings (first-pass, context-aware)

- **F-01**(reviewer 原編號 Opus#1,MEDIUM [python-reviewer])`tests/server/test_index_routes.py:100-108` —— 心跳 `continue` 把「有界迴圈」變成牆鐘無界:`_WS_PRE_QUOTE_MAX` 只計 `type=="index"`,ping 不計數也不設期限;relay `_beat` 定時恆送、`WS_HEARTBEAT_SECS=10` 本檔未 patch(`grep -rn "WS_HEARTBEAT_SECS" tests/` 命中 test_app / test_signal_routes / test_ws_disconnect,不含本檔);`TestClient.receive_json()` 阻塞;repo 無 pytest-timeout(`find_spec('pytest_timeout') is None`)、pyproject 無 timeout。迴歸時由「10 s 後首則 ping 撞 `assert type=="index"` 紅」退化成「全量 pytest 掛死」。fix:ping 獨立上限或整段牆鐘預算。anchor:`                while len(seen) <= _WS_PRE_QUOTE_MAX:` / `                    if msg["type"] == "ping":  # 心跳直送不經 queue(10 s 一發),不算一則`
- **F-02**(reviewer 原編號 Opus#2,LOW [python-reviewer])`tests/capital/balance_rows.py:1` —— docstring「19 欄字面的唯一定義處」與 `test_client.py:1078` / `:1103` 兩列同欄形內嵌不符。search-proof:`grep -rn ",A123456789,1234567890" tests/ --include=*.py | grep -v balance_rows.py` → 庫存列命中僅該兩處,其餘為 30 欄損益列。fix:docstring 明列例外(建議)或一併收成常數。anchor:`"""群益庫存報告(OnRealBalanceReport)列 fixture —— 19 欄字面的**唯一定義處**,`
- **F-03**(reviewer 原編號 Opus#3,LOW [python-reviewer])`tests/server/test_bars.py:602-603` —— 哨兵 docstring 第三子句「擋別的測試把 `_now_time` 改回真牆鐘」機制不成立:autouse 每測試 setup 覆寫、teardown 還原;另 `cache.hist_missing(...) == []` 與 `TestMidnightMemoRace::test_daytime_unaffected` 近複本屬刻意獨立、不需改。fix:刪第三子句。anchor:`        「fixture 被刪」,這一條擋「時刻被凍到窗內 / 別的測試把 `_now_time` 改回真牆鐘」。"""`

已逐條複核成立的 PR 自我宣稱(reviewer 核過,無 finding):(1) 生產碼零 diff:`git diff 5c0244f1...HEAD --stat -- copycat/` 空;(2) 斷言語意不變:`git diff -U0 -- tests/ | grep '^-' | grep -c assert` → 2,皆為 B 那組被有界迴圈等價取代的 `assert msg["type"]=="index"` / `assert …p == 42_039_920`,C 的 diff 零 assert 刪除;(3) 搬移逐 byte 相同:AST 比對五常數 True(69/69/78/75/52)、`_BAL_3357==RAW_C_MARGIN` / `_BAL_2493==RAW_T_BOUGHT` / `_BAL_ROW==RAW_T_HELD` 全 True、base test_client 內嵌 13 處 → HEAD 0 處;(4) reviewer 自跑 `pytest -q tests/server/test_bars.py tests/server/test_index_routes.py tests/capital/test_balance.py tests/capital/test_fill_latency.py` → 111 passed、`ruff check tests` PASS;(5) 作者 round 1 S-1~S-8 / P-1~P-4 處置已讀作去重基準,本輪三條皆非其重複(F-01 是 P-3 收修後的新洞、F-02 是 S-1 收修後仍剩的兩列、F-03 是 S-4 收修新加 docstring 的宣稱)。

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查。

### Codex 對 Opus 的複查結果（對稱化 4.2）

**Codex 複查 Opus 失敗 — 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(本機無 codex)。全部 CC finding 視同 INCONCLUSIVE,改由 4.3b 主 agent 逐條實查(結果在發現總覽「Opus 複查」欄與下方備註):

| Opus # | 原始 severity | 4.3b 判斷 | 備註(他軸為何漏 / 主 agent 實查) |
| --- | --- | --- | --- |
| F-01 | MEDIUM | CONFIRMED | 主 agent `grep -n "WS_HEARTBEAT_SECS\|heartbeat" test_index_routes.py` → 0 命中;`grep -n "^WS_HEARTBEAT_SECS" ws.py` → `:33 WS_HEARTBEAT_SECS: float = 10.0`;`.venv python -c "find_spec('pytest_timeout')"` → False;`grep timeout pyproject.toml` → 0。lone finding 的合理解釋:作者 round 1 Spec P-3 的建議句是「加一行 `if ping: continue`」,兩軸與主 agent 都只看「ping 被誤計」這一面,沒把 relay `_beat` 定時恆送 + receive 阻塞 + 無 pytest-timeout 三件事串起來。 |
| F-02 | LOW | CONFIRMED | 主 agent `grep -n ',A123456789,1234567890"' test_client.py | grep -v 新台幣` → `:1078 "3357,T,0,0,0,0,2000,…"`、`:1103 "2330,T,0,0,0,0,500,…"`。lone 解釋:round 1 S-1 抓的是「第三檔的複本」(`_BAL_ROW`),主 agent 的殘留 grep 只找 `3357,C,2000,1944` / `2493,T,0,0,0,0,0,1000` / `_BAL_` 三個 pattern,同欄形但不同值的合成列落在 pattern 外。 |
| F-03 | LOW | CONFIRMED | 主 agent `sed -n 27,30p test_bars.py` → `@pytest.fixture(autouse=True) def _daytime_clock(monkeypatch)` 每測試 `setattr`;verification §1 已記「plugin 在 import 期改模組屬性,fixture 每條測試再覆寫 → plugin 失效」。lone 解釋:round 1 S-4 要求「補一條走 build_minute 的斷言」,主 agent 補時 docstring 順手把 S-4 原句「別的測試把 `_now_time` 改回真牆鐘」抄成本條的保證,沒對照自己 §1 寫的 plugin 失效機制。 |

## Action Items

**Severity calibration**:6c(移除既有防護類)—— 本 PR 無移除防護 / guard 類改動(生產碼零 diff);6d-1 hedge cap:F-01 的後果建立在「日後推播鏈迴歸」這個未發生前提上 → 不高於 Should Fix;6d-3 Must Fix 雙半條件:三條無一有 user-visible 重現路徑 + 阻擋發布(F-01 是測試層在未來迴歸時的失效形態,今天全綠),無 Must / Should;分級規則 MEDIUM / LOW → Nice to Have;6d-2 由 4.3b 取代(三條全 CONFIRMED、各有 lone 解釋,零降級);未驗證前提閘:三條 severity 都建立在第一手 grep / find_spec / file:line 證據上,拿掉推論部分不降級;provenance cap N-A。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix（合併前必修）

- 無

### Should Fix（強烈建議）

- 無

### Nice to Have（可選優化）

- F-01 `test_ws_streams_index_payload` 迴圈給 ping 獨立小上限或整段套 `time.monotonic()` 牆鐘預算(`tests/server/test_index_routes.py:100-102`)—— 三條中建議優先做:迴歸時「掛死 vs 紅」的代價差最大
- F-02 `balance_rows.py` docstring 比照 profit_rows 明列 test_client `:1078` / `:1103` 兩列例外與理由,或一併收成常數(`tests/capital/balance_rows.py:1`)
- F-03 `TestModuleClock::test_default_clock_persists_yesterday` docstring 刪「別的測試把 `_now_time` 改回真牆鐘」子句(`tests/server/test_bars.py:603`)

### 參考用（任一軸驗證為 REFUTED 或 OUT_OF_SCOPE）

- 無

## 審查工具比較 (qualitative)

- CC 視角(python-reviewer):三條全落在「作者 round 1 收修之後長出來的第二層」—— P-3 加 ping `continue` 後的無界(F-01)、S-1 收第三份後仍剩的同欄形兩列(F-02)、S-4 補哨兵時抄進 docstring 的不成立保證(F-03)。三項白名單(生產碼零 diff / 斷言不變 / byte 相同)reviewer 以 AST 與 diff 計數獨立重驗,與 PR verification 數字一致;spec 兩處刻意偏離(B 無 seed 快照 / A 哨兵)reviewer 另行 trace 同意。與 round 1 in-flow two-axis 的差異:round 1 12 條抓的是第一層(第三份複本 / import 序 / 上限值 / docstring 欄位語意),本輪抓的是收修動作本身帶進來的新問題,尤其 F-01 是把「修 flake」的改動再往下推一步的失效形態。
- Codex / Gemini:N-A。
- 4.3b:CONFIRMED 3 / PARTIAL 0 / 0 降級;三條皆有 lone 解釋(P-3 只看誤計面 / 殘留 grep pattern 太窄 / docstring 抄 S-4 原句)。
- 對抗式第三軸增益:N-A。

## 沒做的部分（結案對帳）

- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(grep / sed / find_spec)。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 以 `py -3.14` 實跑;第一次 input 用了複數 `candidates` 形狀回 `C4_CLI_INPUT_INVALID`,改單一 `candidate` + 四欄 `changed_flow_hint` 後得正式 reason code)。
- 真實環境:本 PR 無 UI / API / 生產碼變更,prod 不需為此重啟;無真環境驗證項。
- 未驗證前提:F-01 的「迴歸時掛死」是機制推論(relay 定時 ping + receive 阻塞 + 無 timeout 三件事都第一手核過,但沒實際製造一次迴歸跑到 hang);F-02 的「群益改欄形時靜默留舊形」是 pr-119 F-05 / pr-129 F-02 已實證過的同型後果,本輪未再實證。
- Self-Verify:已執行,COMPLIANT(auditor 只讀本草稿內嵌全文 + 固定 rubric,零 tool call、未讀其他產物);無修正項。
