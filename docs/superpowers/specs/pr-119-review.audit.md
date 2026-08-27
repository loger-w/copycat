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

## Spec 依據

- 偵測到 `.claude/bug/breakeven-avg-source-prod-chain/spec.md`(路徑不符 Step 2.6 預設 heuristic,但為本 repo /bug 流程的 originating spec,主 agent 手動納入;§A 真鏈補 avg_source + 刪死路徑 + 白名單四項;§B 前端 switch;非目標:空方語意、F-05、11 條 Nice)。
- ⚠️ spec 作者 = PR 作者(同一 session 產出;out-of-scope 判定以此 spec 為據時注意利益重疊)。

- `SPEC_COMPLIANCE` receipt:gate=SKIPPED;dispatch=NOT_APPLICABLE;dispatch_count=0;reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED(spec 位於 `.claude/<flow>/<slug>/`,不在 authority 允許路徑;同 08-27 #118 判定);requested_model=opus;observed_model=UNAVAILABLE;effort=xhigh;tools=0;0 clauses / 0 findings / 0 observations / 0 invalidated

## 變更概要

provenance:11 authored / 0 inherited(base = master,免驗)。

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `.claude/bug/breakeven-avg-source-prod-chain/code-review-round-1.json` | 無 finding(新增) | in-flow two-axis round 1 處置紀錄 |
| `.claude/bug/breakeven-avg-source-prod-chain/spec.md` | 無 finding(新增) | originating bug spec:§A 真鏈 avg_source / §B 前端 switch / 白名單 / 非目標 |
| `.claude/bug/breakeven-avg-source-prod-chain/verification.md` | 有 finding(新增) | loop / 反向驗證 / gate / review 落檔(F-07:修法表仍寫 default) |
| `CLAUDE.md` | 有 finding(修改) | §4 avg_source 契約條產生點 / 讀者改正(F-03:紅燈判準漏期貨列例外) |
| `copycat/capital/client.py` | 無 finding(修改) | `_on_profit_complete` 回填時補 `p.avg_source = "broker"`(核心修法,機制追過成立) |
| `copycat/capital/store.py` | 有 finding(修改) | 刪零 caller 的 `apply_profit_rows`;`positions()` docstring 接住不變式(F-06) |
| `docs/next-time.md` | 無 finding(修改) | 08-27 節留尾 + #116 錯位順修 |
| `frontend/src/lib/ladder-position.test.ts` | 無 finding(修改) | 兩欄同缺 → 與 null 同口徑測試 |
| `frontend/src/lib/ladder-position.ts` | 有 finding(修改) | `?? null` 歸一 + exhaustive switch(F-02:值域外字串仍 NaN) |
| `tests/capital/test_client.py` | 有 finding(修改) | 真鏈 avg_source=broker + kind=None 兩條(F-01 / F-05) |
| `tests/capital/test_store.py` | 有 finding(修改) | store 側兩刪兩改 setup(F-04) |

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

### Opus 原始 findings (first-pass, context-aware)

- **F-01**(reviewer 原編號 F-1,MEDIUM [python-reviewer])`tests/capital/test_client.py:1234-1235` —— 真鏈 seam 只斷言 5 個回填欄中的 2 個,`pnl_base` / `pnl_base_price` / `pnl_cost` 的 ProfitRow → Position 映射全 repo 零覆蓋。anchor:`assert sec is not None and sec.avg_price == 150.55`。search-proof:grep pnl_base/pnl_cost tests/ → 只有 test_models(預設值)與 test_store carry 測試;test_client 零筆
- **F-02**(reviewer 原編號 F-2,MEDIUM [python-reviewer])`frontend/src/lib/ladder-position.ts:101-103` —— `?? null` 只攔 null / undefined:wire 送值域外字串(日後 `AvgSource` 加值、前端未重 build 的窗口)三個 case 全不中 → `cost` 未賦值 → 打平線 / 損益 NaN,與 spec §B 原症狀同形。anchor:`const avgSource: AvgSource | null = input.avgSource ?? null;`。search-proof:grep zod|safeParse frontend/src → 0 筆;grep avg_source frontend/src(非測試)→ 兩處原樣傳遞
- **F-03**(reviewer 原編號 F-3,LOW [python-reviewer])`CLAUDE.md:246-247` —— §4 新增的紅燈判準「持倉列 `avg_source` 非 null」對期貨列必然誤報(期貨列恆 null 是同 PR next-time 明寫的既知語意)。anchor:`跳一格(08-26 修、08-27 才真的修到 prod 路徑,零錯誤訊號);少送 `today_qty` → 當沖減半靜默消失;前端 switch 無`。search-proof:grep avg_source copycat/ → client.py:564 / store.py:289/319/482;balance.py:142 fut 列無 avg_source
- **F-04**(reviewer 原編號 F-4,LOW [python-reviewer])`tests/capital/test_store.py:325-326` —— `test_set_positions_carries_profit_by_composite_key` 收拾沒做完:`c.avg_price is None` 斷兩次、註解重複,function 內 `from copycat.capital.models import Position` 檔頭已有。anchor:`assert c.avg_price is None and c.avg_source is None  # 異種類是另一列,不沿用`。search-proof:sed 檔頭 → `from copycat.capital.models import Position` 已存在;grep `assert c.avg_price` → 325 / 326
- **F-05**(reviewer 原編號 F-5,LOW [python-reviewer])`tests/capital/test_client.py:1241-1243` —— 新測試 docstring 宣稱「標籤與 [25] 皆對不上」,但 fixture 只有 25 欄(index 0–24),`len(parts) > 25` 為 False → `[25]` 備援根本沒走到;同一份 25 欄字面本檔已第 6 / 7 份複製,且 `成交價金` 落在 `[11]` 而 `_PNL_IDX_COST = 12`。anchor:`"""kind=None(標籤與 [25] 皆對不上)在真鏈回填端整列略過:不蓋掉上一輪已知的 broker 均價`。search-proof:python 切逗號 → len(parts)==25;balance.py:197 `len(parts) > _PNL_IDX_KIND_CODE(25)` False;grep 451650 tests/capital/test_client.py → 6 處
- **F-06**(reviewer 原編號 F-6,LOW [python-reviewer])`copycat/capital/store.py:507-509` —— `positions()` 新 docstring 只開「pending 列」一個例外,但 `set_positions` 的 carry-over 也是就地寫,而 `_finalize_positions(self._stale_fut_positions())` 傳的正是已發布的 fut 物件 —— 現況 `p is prev` 五行皆自我賦值故安全,但那是巧合不是不變式。anchor:`"""回傳的是物件**參考**(route 在鎖外 asdict):已發布的 Position 不可就地變更,`。search-proof:grep set_positions copycat/ → 唯一 caller client._finalize_positions:618;grep _stale_fut_positions → 586 / 652
- **F-07**(reviewer 原編號 F-7,LOW [python-reviewer])`.claude/bug/breakeven-avg-source-prod-chain/verification.md:52` —— verification.md §3 假說 B 與 §4 修法表仍寫「`default` 併 `case null`」,但收修 commit `5ff89742` 已拿掉 `default` 改 `?? null` 歸一;§4 表也只列到 `f3fca9cc`,三筆收修只在 §7a 內文。anchor:`| `0375f3aa` | 🔴 | `client.py::_on_profit_complete` 補 `p.avg_source = "broker"`;`ladder-po`。search-proof:grep default verification.md → 45 / 52 兩筆;grep default ladder-position.ts → switch 內無 default

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查。

### Codex 對 Opus 的複查結果（對稱化 4.2）

**Codex 複查 Opus 失敗 — 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(本機無 codex)。全部 CC finding 視同 INCONCLUSIVE,改由 4.3b 主 agent 逐條判斷式複查(結果在發現總覽「Opus 複查」欄與下方備註):

| Opus # | 原始 severity | 4.3b 判斷 | 備註(他軸為何漏 / 主 agent 實查) |
| --- | --- | --- | --- |
| F-01 | MEDIUM | CONFIRMED | 主 agent grep `pnl_base\|pnl_cost` tests/capital/test_client.py → 0 筆;test_store.py:322 只斷 carry(手寫 Position),不經 ProfitRow。lone 原因:他軸缺席(工具)。 |
| F-02 | MEDIUM | CONFIRMED | 主 agent grep zod/safeParse frontend/src → 0,wire 無 schema 層;PriceLadder.tsx:147 / position-summary.ts:148 原樣傳遞。與 #118 F-02 同形,本輪修的是 undefined 那半。lone 原因:工具缺席。 |
| F-03 | LOW | CONFIRMED | 主 agent grep avg_source copycat/ → 寫入點只在 sec 路徑;balance.py:142 建 fut 列不帶 avg_source。本輪出貨時 prod 剛好只有證券部位,判準沒被踩到。 |
| F-04 | LOW | CONFIRMED | 主 agent sed 325-326 / 9-12 / 293 逐字核對:兩行同斷言;檔頭 line 12 已 import Position。round 1 S5 只併了 m 那塊。 |
| F-05 | LOW | CONFIRMED | 主 agent 以 venv 實跑 parse_profit_line(該字面):len 25、[12] = '0' → cost 0.0;替換「信用」後 kind None 是因欄位不存在。test_balance.py:315-316 有 30 欄實證列可派生。 |
| F-06 | LOW | CONFIRMED | 主 agent grep `_stale_fut_positions` client.py → 586 / 652 由 store.positions() 濾出同一批參考餵回 set_positions;store.py:481-485 就地寫五欄。現況自我賦值無值變化,判為文件缺口非行為 bug。 |
| F-07 | LOW | CONFIRMED | 主 agent grep default verification.md → 45 / 52;grep default ladder-position.ts → 只有註解「不用 default 接」。 |

## Action Items

**Severity calibration**:6c(移除既有防護類)—— 本 PR 無移除既有防護類 finding(刪 `apply_profit_rows` 屬零 caller 死路徑,reviewer 已核真鏈覆蓋);6d-1 hedge cap / 6d-3 Must Fix 雙半條件逐條套用(見各條 Action 理由);6d-2 由 4.3b 取代;provenance cap N-A。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix（合併前必修）

- 無

### Should Fix（強烈建議）

- 無

### Nice to Have（可選優化）

- F-01 真鏈測試只釘了均價跟來源,損益三欄的映射沒人守(`tests/capital/test_client.py:1234-1235`)—— 三行斷言零 setup 成本;非 release-blocking(測試覆蓋缺口)→ MEDIUM 落 Nice
- F-02 歸一只擋 nullish,後端先加第三個值的窗口裡前端還是會印 NaN(`frontend/src/lib/ladder-position.ts:101-103`)—— 一行白名單歸一、exhaustiveness 不變;觸發要 AvgSource 加值 + 前端未重 build,假設性情境 → hedge cap,MEDIUM 落 Nice
- F-03 §4 那句紅燈判準碰到期貨列一定誤報(`CLAUDE.md:246-247`)—— 一句文件改口;判準寫錯會誤導漂移排查
- F-04 carry 測試那塊還有一行重複斷言跟一個多餘 import(`tests/capital/test_store.py:325-326`)—— 刪一行重複斷言 + 一行冗餘 import;純可讀性
- F-05 kind=None 那條測試的 fixture 根本沒 [25] 欄,docstring 講的備援分支沒被走到(`tests/capital/test_client.py:1241-1243`)—— docstring 與行為不符 + 第 6/7 份字面複製;抽常數並補 [25] 欄即可
- F-06 positions() 那段不變式漏了 set_positions 對 stale fut 列的就地寫(`copycat/capital/store.py:507-509`)—— docstring 補一句第二個例外與其安全前提;現況靠自我賦值巧合安全
- F-07 verification 寫的前端修法(default)跟實際出貨的 code 相反(`.claude/bug/breakeven-avg-source-prod-chain/verification.md:52`)—— 落檔證據與出貨 code 相反(default 有無正是 F-02 的關鍵事實);表格補三列

### 參考用（任一軸驗證為 REFUTED 或 OUT_OF_SCOPE）

- 無

## 審查工具比較 (qualitative)

- CC 視角(python-reviewer):核心修法三項機制(pending 列未發布、寫入點一一對應、collector reset seam)逐一追過成立;7 條新發現全屬測試鑑別力 / 文件一致性 / 執行期防禦,無行為 bug。
- Codex 中性 / 對抗 / Gemini:N-A,重疊率無法計算。
- 4.2 分佈:全部 INCONCLUSIVE(無 codex);4.3b 主 agent 實查:CONFIRMED 7 / 0 降級(全部 lone finding,他軸缺席為工具缺席非判斷)。
- 對抗式第三軸增益:N-A。

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
