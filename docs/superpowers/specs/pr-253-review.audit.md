# PR #253 Code Review 比較報告 · SHA d05aec5b
**Report projection schema**: 1

**PR**: [loger-w/copycat#253](https://github.com/loger-w/copycat/pull/253)
**標題**: fix(capital): 群益回報線斷線後自動重連(Solace / 探針 → degraded → 退避 clear+ConnectByID → ok)
**作者**: loger-w
**分支**: `fix/capital-reply-reconnect` → `master`
**變更**: 13 檔案, +633 / -68
**審查日期**: 2026-09-15
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以收修 PR 處置,不阻擋任何出貨;merge commit `de81c85b`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `d05aec5bcc69b3cf59ae7907c22dfe0f12564d7c`;destination repo id `R_kgDOTsITBg` + baseRefOid `4ad1cc22a3588218c3bee01425ee7ea66aed2b36`;`input_binding: verified`(`refs/pull/253/head` fetch 後 `git rev-parse` = headRefOid;worktree detached 於該 SHA;baseRefOid 可解析)
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 SHA;分支已刪,`refs/pull/253/head` 仍指 `d05aec5b`,產報告前重抓 headRefOid 不變);`base_changed=true`(origin/master 已前進到 `de81c85b` = 本 PR 自己的 merge 結果,無其他人 commit);`review_context_changed=false`(reviewed 內容即 master 現況)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A**(user 已停用,沿 #188 / #190 / #199 / #230 / #238 前例單軸)+ Codex 對抗式 **N-A** + Cross-axis verification(4.1 N-A 無非 CC finding;4.2 以 main session 內部逐條事實核代替,**非跨軸證據**)+ Gemini 軸 **N-A**(user 已停用)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer ×1(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .py 佔 source diff 100%);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派,gate SKIPPED);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=13 → covered 7 / no-issues 4 / skipped 3 / **missed 0**(chunked: 否,7 source 檔 / 701 diff 行,低於 15 檔 / 800 行門檻;covered 與 no-issues 有 1 檔重疊:client.py 既有 finding 又有核過無問題段,計入 covered)
**定位 (ENH-B)**: anchored exact 7 / ambiguous 2 / **FAILED 0**(F-01 `self._set_status("ok")` 在 client.py :537 / :911 雙匹配 → 取 reviewer 回報區間內的 :537;F-07 `connect_reply` :562 / :894 雙匹配 → 取 :562;F-10 anchor `<none>` 為架構觀察不定位)
**React-doctor (2.97)**: N-A(非 React PR;F 無 .jsx / .tsx)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_SPEC)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出;`sem` 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer ×1)PASS(10 raw findings;13/13 accounting;Reuse 基線核過 repo 三處退避算式皆行內、無可重用 helper)/ Codex 中性 N-A / Codex 對抗 N-A / Gemini Flash N-A / Gemini Pro N-A / cross-axis verification:4.1 N-A、4.2 以 main session 內部事實核代替 PASS(10/10 逐條對 worktree code:F-01 機制三段(`balance.clear` `_awaiting=False` + `feed` 不看 `_awaiting` + `_maybe_query_balance` 守門被清)、F-02 `store.clear` 修前零 caller + `check_correct_price` remaining None 直接放行、F-03 tests 零 `on_reply_connect(` 觸發、F-04 斷言前 `_maybe_reconnect_reply` 已標 dirty、F-05 八處 seq 全 0/1、F-06 :894 → :909 中間無 `rc =`、F-08 :158-176 三連空行 + :183 `import time`、F-09 :1006 「五份」:1007 「六份」、F-10 1294 → 1393 行)/ 4.3a N-A(單軸無 consensus)/ 4.3b 逐條見備註
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-253`
**worktree HEAD**: `d05aec5bcc69b3cf59ae7907c22dfe0f12564d7c`

**Report generation**: sha256:2a0e3393812877d7a88adae6454d9f8e6d13245f22e30bb9ed7b051ab30da612

---

## Spec 依據

- 此 PR 未附正式 spec / plan 文件;originating 依據 = `/bug` 流程 artifact `.claude/bug/capital-reply-reconnect/diagnosis.md`(症狀 / loop / 唯一假說 / fix / 已知不救四條)+ `docs/next-time.md` 09-14 節「回報線『修』的那一半」(user 拍板路徑)+ 本 PR 改寫的 `CLAUDE.md` §4 回報線契約條。按一般 PR 流程 review,diagnosis「已知不救」四條(探針值 2 不動狀態 / 不重登 / rc≠0 白清寧空勿雙計 / `_fill_evt_raw` 三份)視為 scope 排除。
- **⚠️ spec 作者 = PR 作者**(diagnosis / next-time / CLAUDE §4 均由 loger-w 於同一分支寫成;「已知不救」是作者自訂的免罪清單 —— 本輪 F-01 判斷時已特別核對:截斷 / 空快照這一面**不在**該清單內,故不受其保護)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_NORMATIVE_SPEC`(diagnosis 與 CLAUDE §4 為描述性契約,無 MUST / SHALL 型 normative clause 可綁 path:line;0 clauses / 0 findings)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool calls N-A。
- Author calibration(Step 2.2):無作者校準檔(`loger-w.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

provenance: N-A(base = master)。六筆 commit:test 紅先行 `83c5f827` → fix `838a9a19` → chore docs `92fd288a` → two-axis round-1 收修 `3366a0ae` → chore docs `427f21de` → chore artifacts `d05aec5b`(SHA 為 PR head;master 上 rebase 後 SHA 已改寫)。

| 檔案 | 變更類型 | 說明 |
|---|---|---|
| `copycat/capital/com.py` | M | `_ReplyEvents` 新 `on_connect` 回呼;Solace 那對與舊 `OnConnect` / `OnDisconnect` 同語意轉發(connection code 0 才算連上,≠ 0 只 WARNING);`_fire` 收攏兩份例外傘;`CapitalCom.setup` 多 `on_reply_connect` |
| `copycat/capital/client.py` | M | `REPLY_RECONNECT_BACKOFF_SECS` + `_reconnect_delay`;`_reply_reconnect_next: float \| None` / `_reply_reconnect_attempt`;`_handle_reply_disconnect` 排重連;`_handle_reply_connect` / `_schedule_reply_reconnect`(只在 degraded 排、去重)/ `_reply_recovered`(清 last_error、`_set_status("ok")`、`_mark_balance_dirty`)/ `_maybe_reconnect_reply`(幫浦圈;`store.clear()` 先於 `connect_reply`);`_probe_reply` 0 → degraded + 排、1 → ok;`_init_com` ConnectByID rc≠0 立即排 |
| `tests/capital/fake_com.py` | M | `FakeCom` / `RecordingCom.setup` 收 `on_reply_connect` |
| `tests/capital/test_reply_reconnect.py` | A | 十案:05:50 場景重播 / 探針單路 / R7 不雙計(`_ReplayingCom`)/ 失敗退避 / 退避表 / 逐步到期 / 開機失敗排程 / 恢復後再掉 / error 態不排 |
| `tests/capital/test_reply_watch.py` | M | 值翻 0 改斷 degraded + 同一圈零 COM 啟動呼叫;`_probe_lines` 前綴收緊 |
| `tests/capital/test_com.py` | M | Solace 案改「轉發 + 三行 log」;`_StubCom` 簽名同步 |
| `tests/capital/test_client.py` | M | 註解:斷線當下不 clear、重連半見 test_reply_reconnect |
| `CLAUDE.md` | M | §4 回報線契約由「辨識而非修」改寫為狀態機全貌 + 四行 log + 盤後 grep 判準 |
| `CONTEXT.md` | M | 回報線詞條補「斷了會自己回來」+ Avoid 重登 |
| `docs/next-time.md` | M | 三條結案;F-18 併 `_fill_evt_raw` |
| `.claude/bug/capital-reply-reconnect/*` | A | diagnosis / verification / code-review-round-1(two-axis 7 + 4) |

## 發現總覽

| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `client.py:537` `_reply_recovered` 沿用 `_set_status("ok")` 的「重登清點」(清 `_pending_sec` / `_balance_inflight_until` / 三 abandoned 旗標 + `_balance.clear()`),但回查鏈跑在 `SKOrderLib`、與 `SKReplyLib_ConnectByID` 無關 —— 恢復落在鏈飛行中時,舊鏈尾列進新 staging、`##` 到即 `_flush()`,`_maybe_query_balance` 守門被清又補第二發(1019)→ 落地**截斷 / 空**證券快照,`_positions_seeded` 在錯 base 上翻 True | HIGH | CONFIRMED(HIGH→HIGH:`balance.py::clear` `_awaiting=False` + `_debts.clear()`;`feed` 不看 `_awaiting`;`client.py:339/356` 清點;`_maybe_query_balance` 只看 `_pending_sec` / `inflight`;round-1 Spec-S-02 只治「停更」,diagnosis 已知不救不含此面) | Must Fix | `auto-fix` | 修法局部:在途鏈存在時跳過清點(或改 `abandon()`);紅先行可寫 |
| F-02 | `client.py:561` `store.clear()` 修前零 caller,活化後每個重連窗(5–60 s)`_orders` 空 → `market_of` → None、`correct_price` 的 `remaining_shares` → None → `check_correct_price` 直接 `GateResult(True)`(跳過「已全成交 / 已刪單 remaining=0 本地擋」),`_fut_multiplier` 退 1 + WARNING;CLAUDE §4 只寫顯示面「委託列表 / 成交點空」 | MEDIUM | CONFIRMED(MED→MED:`git show 4ad1cc22:client.py` 無 `store.clear()`;`safety.py:93-94` remaining None 放行;退化為券商兜底不動錢) | Should Fix | `ask-user` | 文件補「知情接受」或改 `correct_price` 在重連窗明示 blocked,屬產品取捨 |
| F-03 | `client.py:516` `_handle_reply_connect` 在 client 層零測試:`FakeCom.connect_reply` 從不觸發 `on_reply_connect`、七案全走探針路;突變成 `return` 3436 全綠 —— 這是 CLAUDE §4 四行判準第 4 行「恢復(連線事件 code=0)」的來源 | MEDIUM | CONFIRMED(MED→MED:`grep -rn "on_reply_connect(" tests/` 零觸發點) | Should Fix | `auto-fix` | 加一案 + `_ReplayingCom` rc=0 觸發 `on_reply_connect(0)` |
| F-04 | `test_reply_reconnect.py:98` 「恢復即重新武裝庫存查詢」斷言恆真:斷言前 `_maybe_reconnect_reply`(rc=0)已 `_mark_balance_dirty()`,下一圈 `now < due` 早退不清;拿掉 `_reply_recovered` 的 `_mark_balance_dirty()` 照綠 → round-1 Spec-S-02 實際未釘 | MEDIUM | CONFIRMED(MED→MED:`client.py:564` 先標;`_maybe_query_balance` 只在出手時清 due) | Should Fix | `auto-fix` | 新案 = disconnect → 探針 1(未出手)→ 斷 due 非 None |
| F-05 | `client.py:965` 探針值 2「不動狀態」零測試:八處 `reply_connected_seq` 全 0/1;`if value == 0` 突變 `!= 1` 全綠,prod 後果 = 開機首值 2 那刻健康回報線被判斷線 → `store.clear()` + 每 5→60 s 打 ConnectByID + degraded 假黃字 | MEDIUM | CONFIRMED(MED→MED:23:59:56 實錄首值 2 為真實輸入;repo 慣例值域三態以測試釘死) | Should Fix | `auto-fix` | `test_reply_watch` 加 `[1, 2, 2, 1]` 案 |
| F-06 | `client.py:909` 排程理由字串 `rc={rc}` 復用 :894 賦值的變數,中間隔 `get_user_accounts()` 等四語句;目前正確,日後插入 `rc = …` 會靜默報錯 rc | LOW | CONFIRMED(LOW→LOW::894–:909 無其他 `rc =`) | Nice to Have | `auto-fix` | 存 `reply_rc` 一行 |
| F-07 | `client.py:562` STA 同步 outgoing COM 呼叫期間會 pump incoming → `OnSolaceReplyConnection(0)` 可能在 `connect_reply()` 回傳前 dispatch → 「恢復 → ok」先於「ConnectByID 已送出」印出;狀態不壞,但 verification §3 / CLAUDE §4「順序如此」在此路不成立 | LOW | PARTIAL(LOW→LOW:STA 重入機制為 COM 通則,本 PR 未實錄此次序;文件層問題) | Nice to Have | `auto-fix` | 文件改「兩行都要在、順序可互換」 |
| F-08 | `test_reply_reconnect.py:183` 函式內 `import time`(檔頭已有 imports)+ :158-176 三連空行(ruff 預設不含 E303) | LOW | CONFIRMED(LOW→LOW:`cat -A` 三連 `$`) | Nice to Have | `auto-fix` | 兩處各一行 |
| F-09 | `next-time.md:1006-1007` F-18 同一句「建構工廠五份(… 六份)」兩個數字 | LOW | CONFIRMED(LOW→LOW) | Nice to Have | `auto-fix` | 「五份」→「六份」 |
| F-10 | `client.py` 1294 → 1393 行、單 class ~1,190 行;回報線狀態機(五方法 + 探針半邊)是零 IO 純時間輸入的狀態機,可抽 `capital/reply_link.py::ReplyLink` 表驅動測試(退避 / 值 2 / 事件探針同到);本批不動(鐵則 B) | LOW | PARTIAL(LOW→LOW:行數為事實;抽取為設計判斷,無缺陷) | 參考用 | `no-op` | 架構觀察,進 next-time 🔵 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: ec071584f1e0cc8e7bee action=auto-fix
F-02 finding_uid: 294ee0c7ad218b838680 action=ask-user
F-03 finding_uid: 4dddd6065b0e6309243e action=auto-fix
F-04 finding_uid: e9dd895a0b43a8c17884 action=auto-fix
F-05 finding_uid: 0c7886fd2d20c964143c action=auto-fix
F-06 finding_uid: 901b319b6d76967fd92a action=auto-fix
F-07 finding_uid: 4f9afade12b824e98110 action=auto-fix
F-08 finding_uid: dab743f023fb064a907a action=auto-fix
F-09 finding_uid: e6934bddcac5f355c73d action=auto-fix
F-10 finding_uid: 798ecce60d01c22cdde4 action=no-op inline=none

### Inline Comments per Finding（直接複製貼到 PR review）

#### #1 回報線一恢復就把在途的庫存回查鏈清掉,會落地一份少列甚至空的部位快照

**File**: `copycat/capital/client.py`
**Line**: 537

**Comment**:
```
_reply_recovered 借了 _set_status("ok") 的「重登清點」—— 那段的前提是「狀態斷過就沒有進行中的鏈可守」,
對回報線重連不成立:回查鏈走 SKOrderLib(GetRealBalanceReport / OnRealBalanceReport),跟 SKReplyLib_ConnectByID 兩條 lib 各自獨立,
斷線期間鏈照樣在飛、回應照樣會到。

清點把 _pending_sec / _balance_inflight_until / abandoned 旗標全歸零,再 self._balance.clear() 把 _awaiting=False、_debts 清空;
feed() 不看 _awaiting → 舊查詢剩下的列進新 staging,## 一到 _debts 是空的就直接 _flush()。
同時 _maybe_query_balance 的守門也沒了,_mark_balance_dirty 那 0.5 s 後補第二發 GetRealBalance(舊的還在服務 → 1019)、reset() 再清一次 staging。
結果:成交 → 鏈出手 → 0.6 s 後探針回 1 → set_positions 拿到截斷(尾列先到 ## 時是空集合)的證券快照落地,_positions_seeded 在錯的 base 上翻 True,樂觀套用接著往上疊。
自癒要等下一輪(最壞 60 s),log 只有既有的「遲到丟棄」/ 1019,對帳分不出。

最省事:在途鏈存在時不清 ——
    in_flight = self._pending_sec is not None or self._balance_inflight_until is not None
    self._set_status("ok", reset_chain=not in_flight)
_mark_balance_dirty() 保留(store.clear 已把 seeded 打掉,要一次快照重 seed),它會被既有 pending / inflight 守門自然壓到鏈落地之後。
真要清就走 self._balance.abandon()(開遲到 ## 窗),不是 clear()。
紅先行:成交 → 鏈出手 → 探針 1 → 斷 set_positions 沒有被以 0 列呼叫。CLAUDE §4「順帶清在途鏈旗標」那句要一起改成「在途鏈存在時不清」。
```

#### #2 store.clear() 現在每次重連窗都會跑,改價的本地安全閘在那 5–60 秒會靜默放行

**File**: `copycat/capital/client.py`
**Line**: 561

**Comment**:
```
這個 PR 之前 store.clear() 是零 caller 的休眠方法,「store 是空的」只發生在開機前(手上沒單)。
現在每次重連窗 _orders 都會被清,而同一窗內使用者手上是有活單的:
correct_price 拿 remaining_shares → None → check_correct_price 直接 return GateResult(True),
跳掉的不只金額閘,還有「已全成交 / 已刪單 remaining=0 本地要擋、不留給券商兜底」那條;market_of → None 讓市場別交叉驗證變 no-op;_fut_multiplier 查無退 1 加 WARNING。
不會動到錢(券商還是會拒),但這道 defence-in-depth 在窗內消失、零訊號。

CLAUDE §4 那條的「知情接受」只寫了顯示面(委託列表 / 成交點會空),至少把閘這一面補上;
想真修就在重連窗內讓 correct_price 走 CapitalNotReadyError / 明示 blocked,不要寬鬆放行 —— 這要你拍板,屬下一批。
```

#### #3 「連線事件 code=0 → ok」這半邊恢復路徑沒有任何 client 層測試

**File**: `copycat/capital/client.py`
**Line**: 516

**Comment**:
```
FakeCom.setup 只是把 on_reply_connect 存起來,connect_reply() 從不呼它;test_reply_reconnect 七案全走探針路(reply_connected_seq),
沒有一處 com.on_reply_connect(0)。test_com 只證 sink 會把 code 0 轉出去,沒證 client 收到會翻 ok。
把 _handle_reply_connect 整個改成 return,3436 條照綠 —— 而它是 CLAUDE §4 四行判準第 4 行的來源,也是「事件先響、探針還沒到期」時省 10 s 的那條路。

加一案:斷線 → com.on_reply_connect(0) → 斷 status == "ok"、_reply_reconnect_next is None、log 有「群益回報線恢復(連線事件 code=0」。
順手讓 _ReplayingCom.connect_reply 在 rc==0 時呼 self.on_reply_connect(0),更貼近 SKCOM 實況、也順便把 #7 的重入次序鎖住。
```

#### #4 「恢復即重新武裝庫存查詢」那條斷言其實恆真

**File**: `tests/capital/test_reply_reconnect.py`
**Line**: 98

**Comment**:
```
斷言前這案已經跑過 _maybe_reconnect_reply(rc=0),client.py:564 的 _mark_balance_dirty() 早把 _balance_due 設成 now+0.5,
下一圈 _maybe_query_balance 因 now < due 早退、不會清它。所以把 _reply_recovered 裡的 _mark_balance_dirty() 刪掉,這行照綠。
round-1 Spec-S-02 點名的兩條路(斷線 ≤ 5 s 就恢復沒出手過 / rc≠0 後線自己回來)沒有任何測試在斷 _balance_due。

新增一案:disconnect 事件 → 探針 1(中間不要讓 _maybe_reconnect_reply 出手)→ 斷 _balance_due is not None;
或至少在現有斷言前先 client._balance_due = None。
```

#### #5 探針值 2「不動狀態」是契約條款,但沒有測試釘

**File**: `copycat/capital/client.py`
**Line**: 965

**Comment**:
```
CLAUDE §4 寫「0 = 斷、1 = 連、其他值(23:59:56 實錄首值 2 = 連線中)不動狀態」,測試母體卻只有 0 / 1(八處 reply_connected_seq 全是 [1,0,1] 類)。
把這行寫成 if value != 1: 三千多條不紅,prod 後果是開機首值 2 那一刻:健康的回報線被判斷線 → store.clear() 清空委託列表 / 成交點 + 每 5→60 s 打一次 ConnectByID,status 亮 degraded 假黃字 —— 正是 #235 刻意避開的事。

test_reply_watch 加一案:reply_connected_seq = [1, 2, 2, 1] → 斷 status 全程 ok、com.calls == calls_before、status_view()["reply_connected"] == 2。
```

#### #6 這行的 rc 是十五行前那個,中間隔了四個語句

**File**: `copycat/capital/client.py`
**Line**: 909

**Comment**:
```
rc 在 :894 由 connect_reply 賦值,get_user_accounts() 等四句沒改它,現在是對的;
但日後有人在中間插一句 rc = ...,這行(也就是 prod grep 判準第 2 行的「rc=」)就靜默報錯的碼。
在 if rc != 0: 裡存個 reply_rc = rc,理由字串用它。
```

#### #7 四行 log「順序如此」在 STA 重入時會互換,盤後對帳會以為漏一行

**File**: `copycat/capital/client.py`
**Line**: 562

**Comment**:
```
COM 執行緒是 STA(_run 呼 CoInitialize),同步 outgoing 呼叫期間 COM 會 pump 同 apartment 的 incoming call ——
OnSolaceReplyConnection(0) 可能在 connect_reply() 還沒回傳時就 dispatch → _reply_recovered 先印「恢復 → ok」,之後才印「ConnectByID 已送出」。
狀態不會壞(_reply_reconnect_next 已清成 None,後續只是多印一行 INFO),但 verification §3 / CLAUDE §4 寫的「先接已送出、再接恢復」在這條路上不成立。

文件把第 3 / 4 行改成「兩行都要在,重入 dispatch 時順序可能互換」;#3 那個 _ReplayingCom 觸發 on_reply_connect(0) 的寫法正好重現這個次序。
```

#### #8 新測試檔兩個衛生點:函式內 import、三連空行

**File**: `tests/capital/test_reply_reconnect.py`
**Line**: 183

**Comment**:
```
import time 寫在測試函式裡(檔頭已有 logging / Path / pytest),:158-176 有一處三連空行(ruff 預設 select 不含 E303 所以綠)。
上提 import、空行改兩行就好 —— 別順手 ruff format 整檔。
```

#### #9 next-time 那句「五份(…六份)」自己打自己

**File**: `docs/next-time.md`
**Line**: 1007

**Comment**:
```
前一行還寫「CapitalClient 建構工廠五份(」,括號裡現在列六個、結尾補了「六份」。這條是下個 test-hygiene 批的輸入,執行的人要回頭數。
前一行「五份」改「六份」一個字。
```

## CC 主軸原始 findings(first-pass, context-aware)

#### A-01 [HIGH] copycat/capital/client.py:536-538 — 回報線恢復會清掉在途的 SKOrderLib 回查鏈,可落地截斷 / 全空部位快照
anchor `self._last_error = None / self._set_status("ok") / self._mark_balance_dirty()`。機制:`get_real_balance` = `SKOrderLib.GetRealBalanceReport`(`com.py:126/203-205/327`)、`connect_reply` = `SKReplyLib_ConnectByID`(`com.py:150-152`)兩條 lib 獨立;`_set_status("ok")` 清 `_balance_inflight_until` / `_pending_sec` / `_pending_deadline` / 三 abandoned + `self._balance.clear()`(`balance.py:310-320` `_awaiting=False`、`_debts.clear()`、`_staging=[]`);`feed()` 不看 `_awaiting`(`balance.py:345-375`)。時序:t+0.5 鏈 rc=0 → t+0.6 恢復清光 + dirty(due t+1.1)→ t+1.1 第二發(1019)→ `reset()` 再清 → 舊鏈尾列 + `##` → `_flush()` 截斷 / 空 → `set_positions` 落地、`_positions_seeded` 在空 base 翻 True。觸發率:恢復落在鏈飛行中(~1.7 s p50 / 60 s 輪詢 ≈ 3%,成交相鄰時遠高)。自癒 = 下一輪 dirty(1–2 s),最壞 60 s。Fix:在途鏈存在時跳過清點(`reset_chain=` 旗標)或改 `abandon()`;紅先行斷 `set_positions` 未以 0 列呼叫。search-proof:`grep -rn "def get_real_balance|_order = |_reply = " com.py` → 126/203;`grep -n "_set_status(" client.py` → ok caller 只有 `_init_com` 與 `_reply_recovered`。

#### A-02 [MEDIUM] copycat/capital/client.py:561 — `store.clear()` 首度成為活路徑,連帶把改價安全閘在 5–60 s 窗內靜默放寬
`git show 4ad1cc22:copycat/capital/client.py | grep store.clear` → 無。活化後 `_orders` 清空:`market_of` → None(review R3 設計上斷線可刪單)、`correct_price` `remaining_shares` → None → `check_correct_price` `return GateResult(True)`(`safety.py:93-94`,跳過「remaining=0 本地擋」)、`_fut_multiplier` 查無 → 1 + WARNING。Impact:退化到券商兜底,不動錢,但 defence-in-depth 在窗內消失零訊號。Fix:文件補知情接受;真修在重連窗 `correct_price` 明示 blocked(需拍板)。

#### A-03 [MEDIUM] copycat/capital/client.py:511-516 — 兩個恢復訊號之一(`_handle_reply_connect`)在 client 層零測試
`FakeCom.setup` 只存 `on_reply_connect`,`connect_reply()` 不觸發;七案全探針路。突變 `return` → 3436 全綠。Fix:加一案 + `_ReplayingCom` rc==0 呼 `on_reply_connect(0)`。search-proof:`grep -rn "on_reply_connect|_handle_reply_connect" tests/` → 只有 fake_com :30/46/53/174/178 與 test_com :299,零觸發。

#### A-04 [MEDIUM] tests/capital/test_reply_reconnect.py:97 — 「恢復即重新武裝庫存查詢」的斷言恆真
斷言前 `_maybe_reconnect_reply`(rc=0)已 `_mark_balance_dirty()`(`client.py:564`);`_maybe_query_balance` 只在出手時清 due(`:616-620`)。刪 `_reply_recovered` 的 `_mark_balance_dirty()` 照綠;Spec-S-02 兩條路零 `_balance_due` 斷言。search-proof:`grep -n "_balance_due" test_reply_reconnect.py` → 一行;`grep -n "_mark_balance_dirty" client.py` → 468 / 538 / 564 / 630。

#### A-05 [MEDIUM] copycat/capital/client.py:965 — 探針值 2「不動狀態」零測試:`value == 0` → `!= 1` 突變全綠
`grep -rn "reply_connected_seq" tests/` → 8 處全 0/1。prod 後果:開機首值 2 → 健康回報線被判斷線 → `store.clear()` + ConnectByID 迴圈 + degraded 假黃字。Fix:`test_reply_watch` 加 `[1, 2, 2, 1]` 案。

#### A-06 [LOW] copycat/capital/client.py:909 — `_init_com` 排程理由字串重用 15 行前的 `rc`
`:894` 賦值、`:899` `get_user_accounts()` 未改、目前正確;形狀脆。Fix:`reply_rc = rc`。search-proof:`sed -n 890,912p`。

#### A-07 [LOW] copycat/capital/client.py:562 — 四行 log「順序如此」判準會被 STA 重入打破
`_run` `pythoncom.CoInitialize()`(`:980`)、`pump()` = `PumpWaitingMessages`(`com.py:255-257`);同步 outgoing 期間 incoming dispatch → 「恢復」先於「已送出」。狀態不壞。Fix:文件層改「兩行都要在、順序可互換」。

#### A-08 [LOW] tests/capital/test_reply_reconnect.py:162-164, 174 — 三空行 + 函式內 `import time`
`cat -A` 實測三連 `$`;ruff 預設不含 E303。Fix:兩空行、import 上提;不 format 整檔。

#### A-09 [LOW] docs/next-time.md:1006-1007 — F-18 句子「五份(…六份)」自相矛盾
Fix:前一行「五份」→「六份」。

#### A-10 [LOW] copycat/capital/client.py(:500-572 + :939-970)— design decay:1294 → 1393 行,回報線狀態機是可抽的第二關注點
五方法 + 探針半邊為零 IO 純時間輸入狀態機(同 `live/signal_state.py` / `engine/lock_quality.py` 形狀),可抽 `capital/reply_link.py::ReplyLink` 表驅動測試;本批不動(鐵則 B),建議 next-time 🔵。

逐檔 accounting(reviewer 原文摘要):client.py F-01/02/05/06/07/10(另核幫浦圈每圈成本可忽略、`store.clear()` 先於 `connect_reply` 次序對 STA 重入正確且必要、哨兵同款、`_reconnect_delay` 索引與 docstring 一致、COMError 路徑不緊迴圈);`REVIEWED_NO_ISSUES: copycat/capital/com.py`(`_fire` 收攏、code 0 才轉、五個 `setup` 實作全同步);fake_com.py 見 F-03;`REVIEWED_NO_ISSUES: tests/capital/test_client.py`;`REVIEWED_NO_ISSUES: tests/capital/test_com.py`;test_reply_reconnect.py F-04/08(另確認 R7 案真釘 `store.clear()`:`_append_fill_locked` 無 seq 去重,拿掉 clear 重播 append 第二筆 → 紅);test_reply_watch.py 見 F-05(兩條 pre-marked 該變的改動合規);`REVIEWED_NO_ISSUES: CLAUDE.md`(四行 log 逐字對 code 全中;唯 F-01 修時「順帶清在途鏈旗標」那句要改);`REVIEWED_NO_ISSUES: CONTEXT.md`;next-time.md F-09;`INTENTIONALLY_SKIPPED: .claude/bug/capital-reply-reconnect/diagnosis.md — /bug artifact(非 runtime;已知不救四條不含 F-01 面)`;`INTENTIONALLY_SKIPPED: .claude/bug/capital-reply-reconnect/verification.md — 驗證 artifact(§3 順序判準見 F-07)`;`INTENTIONALLY_SKIPPED: .claude/bug/capital-reply-reconnect/code-review-round-1.json — round-1 記錄(處置與 code 逐條對得上)`。Reuse 基線:repo 三處退避算式(`stock_source.py:697` / `tc4.py:770` / `index_engine.py:726`)皆行內、各持 CAP,無可重用 helper。

## Codex 原始 findings(first-pass, diff-only)

N-A —— Codex 中性 / 對抗兩軸未啟用(user 已停用)。

## Opus 對 Codex 的複查結果

N-A(無非 CC finding)。

## Codex 對 Opus 的複查結果(對稱化 4.2)

N-A —— Codex 未啟用;以 main session 內部逐條事實核代替(結果見發現總覽「內部複查」欄),**非跨軸證據**。

| # | Opus title | 內部核結果 | 原始 → 校正 | 備註 |
|---|---|---|---|---|
| F-01 | 恢復清在途鏈 | CONFIRMED | HIGH→HIGH | 三段機制逐段在 worktree 讀到;lone finding,他軸未啟用故無「為何漏」問題;非 hedge:每一步都是 code 讀出來的機制,觸發只靠時序(鏈飛行 ~1.7 s 內恢復) |
| F-02 | store.clear 放寬改價閘 | CONFIRMED | MED→MED | 修前零 caller + `safety.py:93-94` 放行皆核 |
| F-03 | 事件恢復零測試 | CONFIRMED | MED→MED | grep 零觸發 |
| F-04 | 重新武裝斷言恆真 | CONFIRMED | MED→MED | 測試次序核 |
| F-05 | 值 2 零測試 | CONFIRMED | MED→MED | 八處 seq 核 |
| F-06 | rc 復用 | CONFIRMED | LOW→LOW | :894–:909 核 |
| F-07 | STA 重入次序 | PARTIAL | LOW→LOW | 機制為 COM 通則,本 PR 無實錄;文件層 |
| F-08 | 衛生 | CONFIRMED | LOW→LOW | `cat -A` 核 |
| F-09 | 五份 / 六份 | CONFIRMED | LOW→LOW | :1006/:1007 核 |
| F-10 | 行數 / 可抽狀態機 | PARTIAL | LOW→LOW | 1294 → 1393 為事實;抽取為判斷 |

## Action Items

**Severity calibration**:6c Refactor Intent Gate —— 本 PR 無「移除 / 削弱既有防護」類 finding(F-02 是**新活化路徑**的副作用,不是刻意移除閘;仍按 6c 查證設計意圖:diagnosis / CLAUDE §4 只記顯示面,閘面未被任何一層設計文件承接 → 屬漏記,非設計取捨)。6d-1 hedge cap:F-07「可能」重入 → ≤ Should Fix(實給 Nice);F-01 每一步皆機制事實非假設,不受 cap。6d-3 Must Fix 雙半條件:F-01 重現路徑「成交後 ~1 s 內回報線恢復(斷線 ≤ 5 s、或事件先於探針)→ 部位面板短暫少列 / 零持倉、隨後樂觀套用在錯 base 疊」+ release-blocking = 真錢部位資料正確性(runtime data)→ Must。Provenance cap:N-A(base = master)。
**校準套用**:無作者校準檔(`loger-w.md` 不存在)、本輪無套用。

### Must Fix(合併前必修)

- F-01 `_reply_recovered` 在途鏈存在時不得沿用重登清點(或改 `abandon()`);紅先行 + CLAUDE §4「順帶清在途鏈旗標」改寫。post-merge → 收修 PR。

### Should Fix(強烈建議)

- F-02 `store.clear()` 對改價閘的側面影響:至少文件補知情接受(CLAUDE §4 + diagnosis 已知不救);真修需拍板。
- F-03 `_handle_reply_connect` client 層測試 + `_ReplayingCom` 觸發 `on_reply_connect(0)`。
- F-04 「恢復即重新武裝」獨立案(disconnect → 探針 1,未出手)。
- F-05 `test_reply_watch` 值 2 中性案。

### Nice to Have(可選優化)

- F-06 `reply_rc` 一行。F-07 verification §3 / CLAUDE §4「順序可互換」。F-08 import 上提 + 兩空行。F-09 「五份」→「六份」。

### 參考用

- F-10 `CapitalClient` 回報線狀態機抽 `ReplyLink`:設計觀察、無缺陷,建議入 next-time 🔵 欄,不在收修 PR 動。

## 審查工具比較 (qualitative)

- CC 視角(python-reviewer,context-aware):唯一啟用軸。10 條中 1 條 HIGH 是**同一份 PR 兩輪 review 都沒抓到的**(pre-merge two-axis 7 + 4 條聚焦於狀態機自身的排程 / 退避 / 恢復,Spec-S-02 甚至把「借 `_set_status("ok")` 清點」當正確前提補了 `_mark_balance_dirty`);本輪抓到是因為 reviewer 追了 `_set_status("ok")` 清點區塊的**前提**(「沒有進行中的鏈」)是否對新 caller 成立,並讀到 `balance.py` 的 `clear()` / `feed()` 語意 —— runtime-assertion 追機制那條指令的直接產出。
- Codex 中性 / 對抗 / Gemini:N-A。重疊率:N-A(單軸)。
- 內部複查(同軸)分佈:CONFIRMED 8 / PARTIAL 2 / REFUTED 0 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0 —— 非跨軸證據,REFUTED 率 0% 只代表 main session 讀 code 與 reviewer 一致,不代表 over-flag 率低。
- 對抗式第三軸增益:N-A。

## 沒做的部分(結案對帳)

- Codex 中性軸:N-A —— user 已停用(沿 #188 … #238 前例單軸),未起軸、未 retry。
- Codex 對抗式軸:N-A —— 同上。
- Gemini Flash / Pro 軸:N-A —— user 已停用;Step 2.96 / 2.98 兩問依前例不問。
- Cross-axis verification 4.1:N-A(無非 CC finding)。4.2:以 main session 內部逐條事實核代替(PASS 10/10),**非跨軸證據**。4.3a:N-A(單軸無 consensus)。4.3b:全部 10 條為 lone finding;他軸未啟用,「為何漏」不成立,不降級;各條依內部核 verdict 定級(見發現總覽)。
- Review input binding:**verified**(`refs/pull/253/head` = headRefOid `d05aec5b`,worktree detached 於該 SHA;baseRefOid `4ad1cc22` 可解析)。
- Blast radius(2.9):PASS(有跑)但空輸出跳過(`sem` 未安裝)。
- React-doctor(2.97):N-A(非 React PR)。
- Formal spec traceability(2.65):SKIPPED (C4_NO_NORMATIVE_SPEC);spec-compliance-reviewer 未派。
- Author calibration(2.2):無檔、本輪無套用。
- Reviewer 未重跑 pytest / ruff / pyright / validate:全綠證據引自 PR 內 `verification.md`(收修後全量 3436 passed / 3 skipped、ruff 綠、pyright 0、validate 42/42)。
- 未驗前提(集中揭露):F-01 觸發率「≈ 3%」為 reviewer 以 p50 1.7 s / 60 s 輪詢粗估、未實測(機制本身已逐段讀 code 確認);F-07 STA 重入次序為 COM 通則推論、本 PR log 無實錄;F-10 「可抽」為設計判斷。
- 真環境:本 review 未另跑 server;prod(`e05a964f`)尚未含本 PR,PR 的真環境判準(verification §3 四行 log + 可控斷線)要重啟後另做,不在本 review 範圍;**F-01 修好前重啟到本 PR 版本的風險 = 恢復落在鏈飛行中時部位面板短暫錯,最壞 60 s 自癒**。
- Self-Verify:已執行(`skill-verify-auditor`,requested=opus / observed=UNAVAILABLE;唯讀、只 Read 本草稿檔一次,1 tool 呼叫)。R1–R10 全 PASS、`VERDICT: COMPLIANT`,零修正;未重派 auditor。
