# PR #119 Code Review 比較報告 · SHA bc18163e
**Report projection schema**: 1

**PR**: [loger-w/copycat#119](https://github.com/loger-w/copycat/pull/119)
**標題**: fix(capital): #118 打平線修法在 prod 是死的 —— avg_source=broker 寫入點收斂到真鏈、前端 switch 缺欄防禦
**作者**: loger-w(commits 署名 Loger)
**分支**: `fix/breakeven-avg-source-prod-chain` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 8200f210;回溯 review)
**變更**: 11 檔案, +382 / -73
**審查日期**: 2026-08-27
**Review input basis**: source repo R_kgDOTsITBg + bc18163ef8842d77113b167a554faaa40464f690;destination repo R_kgDOTsITBg + 51b93006f4fdf93d824ec3eec5c6f588676f4508;`input_binding: verified`(worktree HEAD = source SHA,`git fetch refs/pull/119/head` 後 rev-parse 逐字相等;destination SHA 為 master 歷史上的既有 commit,`git merge-base --is-ancestor` 成立)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-119`(detached)
**worktree HEAD**: bc18163ef8842d77113b167a554faaa40464f690
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer(不切塊,單一 dispatch;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=11 → covered 6 / no-issues 5 / skipped 0 / **missed 0**(chunked: 否;FILE_COUNT=6 源檔 ≤ 15、DIFF_LINES=455 < 800;reviewer 逐檔 accounting 11/11,union = F)
**定位 (ENH-B)**: anchored exact 7 / ambiguous 0 / **FAILED 0**(全部 anchor 於 worktree HEAD 以 grep 逐字比中,line 以比中結果為準)
**React-doctor (2.97)**: N-A(非 React PR:F 無 .jsx / .tsx;唯一前端檔 `ladder-position.ts` 為純函式庫)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,11 檔全部 authored)
**審查軸狀態**: primary(python-reviewer)PASS(7 findings、11/11 accounting);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條判斷式複查,見備註欄);React-doctor N-A(非 React PR)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus)回 R1–R10 全 PASS、`VERDICT: COMPLIANT`;無需補寫

**Report generation**: sha256:32b7ba9526734cd8a708be51a56a70fce942bf558ed228c59350d904077aadcc

---
## [完整證據副檔](pr-119-review.audit.md)
### finding_uid 索引
[f25d2f648abbc5d3d921](pr-119-review.audit.md#發現總覽) · [4a6649cacef516b8caa3](pr-119-review.audit.md#發現總覽) · [0a90fa2b3af4a6017676](pr-119-review.audit.md#發現總覽) · [6418225a119947665335](pr-119-review.audit.md#發現總覽) · [6abd07b8d81d5945989f](pr-119-review.audit.md#發現總覽) · [2ce09b9ce596faf1279b](pr-119-review.audit.md#發現總覽) · [9cf72bc58a70eb5c4ea3](pr-119-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | 真鏈 seam 只斷言 5 個回填欄中的 2 個,`pnl_base` / `pnl_base_price` / `pnl_cost` 的 ProfitRow → Position 映射全 repo 零覆蓋(`tests/capital/test_client.py`) | MEDIUM [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 三行斷言零 setup 成本;非 release-blocking(測試覆蓋缺口)→ MEDIUM 落 Nice |
| F-02 | `?? null` 只攔 null / undefined:wire 送值域外字串(日後 `AvgSource` 加值、前端未重 build 的窗口)三個 case 全不中 → `cost` 未賦值 → 打平線 / 損益 NaN,與 spec §B 原症狀同形(`frontend/src/lib/ladder-position.ts`) | MEDIUM [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 一行白名單歸一、exhaustiveness 不變;觸發要 AvgSource 加值 + 前端未重 build,假設性情境 → hedge cap,MEDIUM 落 Nice |
| F-03 | §4 新增的紅燈判準「持倉列 `avg_source` 非 null」對期貨列必然誤報(期貨列恆 null 是同 PR next-time 明寫的既知語意)(`CLAUDE.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 一句文件改口;判準寫錯會誤導漂移排查 |
| F-04 | `test_set_positions_carries_profit_by_composite_key` 收拾沒做完:`c.avg_price is None` 斷兩次、註解重複,function 內 `from copycat.capital.models import Position` 檔頭已有(`tests/capital/test_store.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 刪一行重複斷言 + 一行冗餘 import;純可讀性 |
| F-05 | 新測試 docstring 宣稱「標籤與 [25] 皆對不上」,但 fixture 只有 25 欄(index 0–24),`len(parts) > 25` 為 False → `[25]` 備援根本沒走到;同一份 25 欄字面本檔已第 6 / 7 份複製,且 `成交價金` 落在 `[11]` 而 `_PNL_IDX_COST = 12`(`tests/capital/test_client.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | docstring 與行為不符 + 第 6/7 份字面複製;抽常數並補 [25] 欄即可 |
| F-06 | `positions()` 新 docstring 只開「pending 列」一個例外,但 `set_positions` 的 carry-over 也是就地寫,而 `_finalize_positions(self._stale_fut_positions())` 傳的正是已發布的 fut 物件 —— 現況 `p is prev` 五行皆自我賦值故安全,但那是巧合不是不變式(`copycat/capital/store.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | docstring 補一句第二個例外與其安全前提;現況靠自我賦值巧合安全 |
| F-07 | verification.md §3 假說 B 與 §4 修法表仍寫「`default` 併 `case null`」,但收修 commit `5ff89742` 已拿掉 `default` 改 `?? null` 歸一;§4 表也只列到 `f3fca9cc`,三筆收修只在 §7a 內文(`.claude/bug/breakeven-avg-source-prod-chain/verification.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 落檔證據與出貨 code 相反(default 有無正是 F-02 的關鍵事實);表格補三列 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: f25d2f648abbc5d3d921 action=auto-fix
F-02 finding_uid: 4a6649cacef516b8caa3 action=auto-fix
F-03 finding_uid: 0a90fa2b3af4a6017676 action=auto-fix
F-04 finding_uid: 6418225a119947665335 action=auto-fix
F-05 finding_uid: 6abd07b8d81d5945989f action=auto-fix
F-06 finding_uid: 2ce09b9ce596faf1279b action=auto-fix
F-07 finding_uid: 9cf72bc58a70eb5c4ea3 action=auto-fix
### Inline Comments per Finding（直接複製貼到 PR review）
#### F-01 真鏈測試只釘了均價跟來源,損益三欄的映射沒人守
**File**: `tests/capital/test_client.py`
**Line**: 1234-1235

**Comment**:
```
`_on_profit_complete` 一次寫五個欄(avg_price / avg_source / pnl_base / pnl_base_price / pnl_cost),
刪掉的 `test_apply_profit_rows_fills_existing_only` 是全 repo 唯一斷後三欄映射的地方,
新的真鏈測試只接了前兩欄。哪天 `p.pnl_base_price = r.cost` 這種指派寫錯,前端損益數字靜默錯、測試全綠。

在 test_balance_chain_marks_avg_source_broker 尾巴補三行就好:
    assert sec.pnl_base == 12345.0 and sec.pnl_base_price == 156.0 and sec.pnl_cost == <期望值>
注意 pnl_cost 用現在的 25 欄 fixture 會解出 0.0(451650 落在 [11],`_PNL_IDX_COST` 是 12)——補斷言會順便把 fixture 錯位照出來,見 F-05。
```
#### F-02 歸一只擋 nullish,後端先加第三個值的窗口裡前端還是會印 NaN
**File**: `frontend/src/lib/ladder-position.ts`
**Line**: 101-103

**Comment**:
```
`?? null` 只擋 null / undefined。後端哪天讓 AvgSource 多一個值(next-time 已在討論期貨列語意),
prod 是「後端先重啟、前端 dist 還沒重 build」這種窗口 —— wire 送 "oi" 之類,三個 case 全不中、
沒 default → cost 是 undefined → breakEven / pnl 全 NaN,跟 #118 F-02 那個症狀一模一樣。
上面 9 行的 todayQty 走的是執行期防禦(Number.isFinite),兩個相鄰欄防禦姿態不一致。

改成白名單歸一,switch 主體不動、加值一樣 TS2454:
    const raw = input.avgSource;
    const avgSource: AvgSource | null = raw === "broker" || raw === "fill" ? raw : null;
```
#### F-03 §4 那句紅燈判準碰到期貨列一定誤報
**File**: `CLAUDE.md`
**Line**: 246-247

**Comment**:
```
判準寫「持倉列 avg_source 非 null」,但期貨列(parse_open_interest_line → merge_fut_positions)avg_source 恆 null,
而且是同一份 PR 的 next-time 明寫的既知語意。下次照這句 curl 的人看到 fut 列 null 會誤判契約斷了,
或反過來替期貨列硬填一個沒實證的來源 —— 後者真的會改壞成本語意。

改成:「**證券**持倉列(market == "sec")avg_source 非 null;market == "fut" 恆 null 為既知語意(見 next-time 2026-08-27)」。
```
#### F-04 carry 測試那塊還有一行重複斷言跟一個多餘 import
**File**: `tests/capital/test_store.py`
**Line**: 325-326

**Comment**:
```
325 跟 326 斷的是同一件事(c.avg_price is None),註解也重複;round 1 併了上面 m 那塊,c 這塊漏了。
另外 293 那行 `from copycat.capital.models import Position` 檔頭已經有了(本 PR 剛把同一個 import 塊的 ProfitRow 半邊刪掉,留一半)。

刪 326、把「集保列不沿用融資成本」併進 325 的註解;順手刪 293。
```
#### F-05 kind=None 那條測試的 fixture 根本沒 [25] 欄,docstring 講的備援分支沒被走到
**File**: `tests/capital/test_client.py`
**Line**: 1241-1243

**Comment**:
```
這列 fixture 只有 25 欄(index 0–24),balance.py:197 的 `len(parts) > 25` 是 False → [25] 種類代碼備援根本沒被查,
kind=None 是因為「欄位不存在」不是 docstring 說的「標籤與 [25] 皆對不上」。prod 真列 30 欄、[25] 帶種類代碼,
標籤壞掉的融資列會被 [25] 解回 margin,不會進這條測試鎖的分支;要 prod 可達得讓 [25] 是未對映值(例如 "3")。
順帶:這份字面本檔已經第 6/7 份複製,而它把成交價金放在 [11]、`_PNL_IDX_COST` 取 [12] 得到 0 —— 沒人斷 pnl_cost 所以一直沒訊號。

抽一個 module 常數(或直接用 test_balance.py:315 的 RAW_PNL_ROW / RAW_PNL_MARGIN 30 欄實證列)並補齊 [25];
第二輪變異改 `.replace(",融資,", ",信用,")` + 把 [25] 換成 "3",docstring 才跟行為相符。
```
#### F-06 positions() 那段不變式漏了 set_positions 對 stale fut 列的就地寫
**File**: `copycat/capital/store.py`
**Line**: 507-509

**Comment**:
```
docstring 只開了「client pending 列」一個例外,但同檔 set_positions(480-485)也是就地寫 caller 傳進來的 p,
而 `_finalize_positions(self._stale_fut_positions())` 這條路傳的正是 store.positions() 濾出來的已發布 fut 物件。
現在不會撕裂是因為那條路 p is prev、五行都是 x = x;哪天有人依 docstring 把 carry-over 改成補別的欄,
就會在鎖內改一個 route 正在鎖外 asdict 的物件。

補一句:「set_positions 的 carry-over 也是就地寫,寫的是尚未發布的新一輪列;唯一例外 _stale_fut_positions() 傳回已發布物件,
此時 p is prev、五行皆自我賦值 —— 改那五行前先確認這條仍成立。」
```
#### F-07 verification 寫的前端修法(default)跟實際出貨的 code 相反
**File**: `.claude/bug/breakeven-avg-source-prod-chain/verification.md`
**Line**: 52

**Comment**:
```
§3 假說 B 結果欄跟 §4 `0375f3aa` 那列都寫「default 併 case null」,但 5ff89742 已經把 default 拿掉、
改成 `?? null` 歸一 + exhaustive switch;§4 表也只列到 f3fca9cc,三筆收修只出現在 §7a 內文。
之後有人查「我們到底有沒有加 default」會拿到相反答案,而這正好是 F-02 那條殘餘風險的關鍵事實。

§3 B 結果欄、§4 那列改成最終形態,並把 7b7c284f / 5ff89742 / c28541f9 三列補進 §4 表。
```
## 沒做的部分（結案對帳）
- Codex 中性 / 對抗軸:FAIL(N-A)—— 本機無 `codex` CLI,兩軸零 finding。
- Gemini Flash / Pro:FAIL(N-A)—— 本機無 `agy`。
- Step 2.96 / 2.98 提問:未執行(工具缺席,提問無意義),走預設值並在 header 註明。
- Step 4.1:N-A(無非 CC finding)。Step 4.2:FAIL → 全部 INCONCLUSIVE(無 codex),以 4.3b 主 agent 實查代之(grep / python 實跑 fixture 解析)。
- sem blast radius:跑了,空輸出跳過(無 `sem`)。
- React-doctor:N-A(非 React PR)。
- C4 / spec-compliance:SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED),0 clauses,未派 reviewer。
- 未驗證前提:F-02「日後 AvgSource 加第三值」為假設性情境(已 cap Nice to Have);F-06 的「巧合安全」以 code 追蹤為據,未實跑撕裂讀重現。
- Self-Verify:已執行,COMPLIANT(auditor 以 Read 讀取草稿檔本身,未讀其他產物)。
