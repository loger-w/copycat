# PR #129 Code Review 比較報告 · SHA d08739b3

**Report projection schema**: 1

**PR**: [loger-w/copycat#129](https://github.com/loger-w/copycat/pull/129)
**標題**: fix(capital/frontend): pr-119 七條收修 —— avg_source 白名單歸一(AVG_SOURCES 同源)、損益三欄映射斷言、30 欄 fixture 共用、文件三處
**作者**: loger-w(commits 署名 Loger)
**分支**: `fix/breakeven-review-followups` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 44722310;回溯 review)
**變更**: 14 檔案, +216 / -44
**審查日期**: 2026-08-27
**Review input basis**: source repo R_kgDOTsITBg + d08739b339ab6518c4da7e329351cadafa58d87f;destination repo R_kgDOTsITBg + 2cde2b224de3f9c754acdb9fe63aaecd9da46060;`input_binding: verified`(`git fetch refs/pull/129/head` 後 FETCH_HEAD 與 headRefOid 逐字相等、worktree HEAD = source SHA;destination SHA 為 master 歷史上的既有 commit,`git merge-base --is-ancestor` 成立)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-129`(detached)
**worktree HEAD**: d08739b339ab6518c4da7e329351cadafa58d87f
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 主 agent 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer(不切塊,單一 dispatch;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=14 → covered 8 / no-issues 6 / skipped 0 / **missed 0**(chunked: 否;FILE_COUNT=8 源檔 ≤ 15、DIFF_LINES=260 < 800;reviewer 逐檔 accounting 14/14,union = F)
**定位 (ENH-B)**: anchored exact 8 / ambiguous 0 / **FAILED 0**(全部 anchor 於 worktree HEAD 以 grep 逐字比中,line 以比中結果為準)
**React-doctor (2.97)**: N-A(F 只有 `.ts`,無 `.jsx` / `.tsx`,未觸發)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,14 檔全部 authored)
**審查軸狀態**: primary(python-reviewer)PASS(8 findings、14/14 accounting);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條實查,見備註欄);React-doctor N-A
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus)回 R1–R10 全 PASS、`VERDICT: COMPLIANT`;無需補寫

**Report generation**: sha256:3d0c18f5283321391a507e21294bb0dd3ad3f5387290840d11626d831bc35c01

---

## Spec 依據

- 偵測到 `.claude/bug/breakeven-review-followups/change-spec.md`(pr-119 七條收修的 change spec:現況 vs 目標表、caller map 三讀者、白名單五條、驗證 seam;非目標未明列 —— F-05 的「跨語言 parity」既非目標也非非目標)。來源 `docs/superpowers/specs/pr-119-review.md` F-01 ~ F-07 全 Nice / 全 auto-fix。
- ⚠️ spec 作者 = PR 作者(同一 session 產出)。本輪 F-04(「六份」數錯)正是 spec 自述數字與 base 實況對不上。

- `SPEC_COMPLIANCE` receipt:gate=SKIPPED;dispatch=NOT_APPLICABLE;dispatch_count=0;reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED(reducer `resolve-authority` 實跑:spec 位於 `.claude/bug/<slug>/`,不在 authority 允許路徑);requested_model=opus;observed_model=UNAVAILABLE;effort=xhigh;tools=0;0 clauses / 0 findings / 0 observations / 0 invalidated

## 變更概要

provenance:14 authored / 0 inherited(base = master,免驗)。

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `.claude/bug/breakeven-avg-source-prod-chain/verification.md` | 有 finding(修改) | 舊 verification §3 B / §4 列改最終形態 + 三列收修(F-07);末句引用的字面已被本 PR 後續 commit 取代(F-06) |
| `.claude/bug/breakeven-review-followups/change-spec.md` | 有 finding(新增) | 現況 vs 目標 / caller map / 白名單;「六份」數字 off-by-one(F-04) |
| `.claude/bug/breakeven-review-followups/code-review-round-1.json` | 有 finding(新增) | in-flow two-axis round 1 處置;引用 rebase 前 SHA(F-07) |
| `.claude/bug/breakeven-review-followups/verification.md` | 有 finding(新增) | 紅先行 / mutation / gate;引用 rebase 前 SHA(F-07) |
| `CLAUDE.md` | 有 finding(修改) | §4 avg_source 紅燈判準改「證券列非 null;fut 列恆 null」(F-01:fut 樂觀套用列會是 fill) |
| `copycat/capital/store.py` | 無 finding(修改) | `positions()` docstring 補第二個就地寫例外 |
| `docs/next-time.md` | 無 finding(修改) | App.test.tsx 負載 flake 條目 |
| `frontend/src/lib/ladder-position.test.ts` | 無 finding(修改) | 值域外字串 case(紅先行) |
| `frontend/src/lib/ladder-position.ts` | 無 finding(修改) | `isAvgSource` guard + 白名單歸一;switch 不動 |
| `frontend/src/types.ts` | 有 finding(修改) | `AVG_SOURCES as const` 推導 `AvgSource`(F-05 跨語言無 parity;F-08 孤兒 JSDoc) |
| `tests/capital/profit_rows.py` | 有 finding(新增) | 30 欄共用 fixture + `pnl_variant`;docstring 數字 / 155.63 語意(F-04) |
| `tests/capital/test_client.py` | 有 finding(修改) | 四處 fixture 改共用;kind=None 第二輪 [25]="3"(F-03);檔尾 `_PNL_3357` 與 `RAW_PNL_MARGIN` 逐 byte 相同(F-02) |
| `tests/capital/test_fill_latency.py` | 無 finding(修改) | fixture 改 `pnl_variant` |
| `tests/capital/test_store.py` | 無 finding(修改) | 重複斷言 / 冗餘 import 刪除 |

## 發現總覽

| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | §4 新判準把「fut 列 `avg_source` 恆 null」寫成絕對事實,但 `store._apply_fill_locked` 的新倉分支對 `_FUT_MARKETS` 同樣寫 `avg_source="fill"`:期貨成交樂觀套用建出的 fut 列在下一輪 OI 快照落地前是 `"fill"`,OI 失敗時 `_stale_fut_positions()` 沿用已發布物件留更久 —— 判準寫錯會把正常的 `"fill"` 判成契約斷了(`CLAUDE.md`) | MEDIUM [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep `store.py:289 avg_source="fill"` 在 `market="fut"` 共用分支內;一句改成有界說法即可,非 release-blocking |
| F-02 | F-05 去重漏掉最大的一份:`test_client.py` 檔尾 `_PNL_3357` 與 `test_balance.py::RAW_PNL_MARGIN` **逐 byte 相同**(30 欄 vs 30 欄),本輪反而替它加了「與 `PNL_3357_MARGIN` 是兩組值」的註解,真正的重複對象沒提 —— prod 實列在 repo 內仍有兩份互不知情的複本(`tests/capital/test_client.py`) | MEDIUM [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `ask-user` | 主 agent python 逐字比對 identical=True;修法是把 `RAW_PNL_MARGIN` / `RAW_PNL_ROW` 搬進 `profit_rows.py`(動到 test_balance,測試重組 🔵),要不要做請 user 決定 |
| F-03 | kind=None 哨兵用 `[25]="3"`,而 `balance.py:153-156` 明寫「融券代碼未實證(疑 3)→ 刻意不對映」:日後補上 `"3": "short"`,`_on_profit_complete` 對 ("3357","short") 一樣 `continue` 並印「種類不符」,測試照綠但 docstring「標籤與 [25] 皆對不上」已不再被驗 —— 與本輪要修的 F-05 同型(docstring 說 A、測試走 B)的復發預留位(`tests/capital/test_client.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 讀 balance.py:151-158 確認「疑 3」;哨兵改 `"9"` + 補 `種類標籤未知` caplog 斷言,零 setup 成本 |
| F-04 | 新 fixture 模組 docstring 兩處失準:「共六份」實為七份(base `test_client` 6 + `test_fill_latency` 1;pr-119 原文自己寫「第 6 / 7 份」;change-spec.md:11 同錯);「配 `_BAL_3357` 的 155.63」—— 155.63 是庫存報告 [16] **維持率**,balance.py 檔頭與 test_balance.py:91 都明寫絕不可當價格,repo 內也無任何以 155.63 為期望值的斷言(`tests/capital/profit_rows.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 對 base 版兩檔各 grep -c 451650 → 6 + 1;balance.py:11-13 維持率警告;純 docstring 改口 |
| F-05 | `AVG_SOURCES` 與後端 `models.AvgSource = Literal["broker","fill"]` 仍是純人工同步,而本輪的威脅模型正是「後端先加值」:白名單把它從 NaN 降級成**靜默**退回修前口徑(損益少一筆買費、打平線跳格),零測試會紅;repo 對這類跨檔契約已有 golden fixture 雙邊各斷言的樣板三處,avg_source 沒有(`frontend/src/types.ts`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `ask-user` | 超出 pr-119 F-01~F-07 範圍(spec 未列為目標亦未列為非目標);補 parity 測試是新 seam,要不要做請 user 決定 |
| F-06 | 修 F-07(文件與出貨 code 相反)時補的「最終形態」那句引 `raw === "broker"` 或 `raw === "fill"` 的三元白名單字面,同一個 PR 兩個 commit 後(review S-2 收修)已改成 `isAvgSource(...)` + `AVG_SOURCES`,該字面 repo 內已不存在 —— 同 PR 內重演 F-07 的漂移(`.claude/bug/breakeven-avg-source-prod-chain/verification.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep `raw === "broker"` frontend/src → 無命中;一句改口 |
| F-07 | artifact(verification §1/§2、review JSON)引用的 8 個 commit SHA 全是 rebase 前的,`git merge-base --is-ancestor` 對六筆全回 no —— merge 後在乾淨 clone 上等於死連結,紅先行 / mutation 的追溯鏈斷掉(08-25 do 批 review 已記過的 47/56 dangling 流程 finding 重演)(`.claude/bug/breakeven-review-followups/verification.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `no-op` | 流程層(rebase merge 必然改寫 SHA),與既有 next-time 條目併案;本輪不回改 |
| F-08 | 孤兒 JSDoc:`/** Position asdict… */` 描述的是 `CapitalPosition`,base 已被 `AvgSource` 註解隔開,本輪再插入 `AVG_SOURCES` + 推導型別兩列,距離再拉開;編輯器 hover 誰也掛不到(`frontend/src/types.ts`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent sed types.ts:104-113 確認;一行位移零行為(base 已有此病,本 PR 加重) |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: fae7dde376bc06fbf398 action=auto-fix
F-02 finding_uid: 57256fe40e3bdcde8cc7 action=ask-user
F-03 finding_uid: 281305b8e499d4bcbcb1 action=auto-fix
F-04 finding_uid: 7aab1c366e2ecafd07d8 action=auto-fix
F-05 finding_uid: e4983699bf87dcda5934 action=ask-user
F-06 finding_uid: 6bbbb37fbce014aec352 action=auto-fix
F-07 finding_uid: eb36e4746e8399aa124a action=no-op
F-08 finding_uid: 59fde2ef7631f52b7532 action=auto-fix

### Inline Comments per Finding（直接複製貼到 PR review）

#### F-01 §4 說 fut 列 avg_source 恆 null,但期貨樂觀套用那條會寫 "fill"
**File**: `CLAUDE.md`
**Line**: 248

**Comment**:
```
這句是修 pr-119 F-03 加的,方向對,但「恆 null」太絕對:store._apply_fill_locked 的新倉分支
(line 282-291)對 _FUT_MARKETS 走同一段 Position(..., avg_source="fill") —— 期貨成交樂觀套用建出來的
fut 列,在下一輪 OI 快照落地前 avg_source 就是 "fill";OI 查詢失敗時 _stale_fut_positions() 沿用已發布物件
(avg_price 非 None → carry-over 整段跳過),那列會帶著 "fill" 留更久。
照這句去 curl 看到 fut 列 "fill" 會判成契約斷了、往錯方向查,或反過來「順手改回 null」把樂觀套用的來源抹掉。

改成有界說法:「OI 快照來源的 fut 列 avg_source 恆 null;唯一非 null 是 _apply_fill_locked 樂觀套用新建的
fut 列("fill"),下一輪 OI 快照落地即覆蓋(OI 連續失敗時由 _stale_fut_positions() 沿用更久)」。判準本身仍只看 sec 列。
```
#### F-02 F-05 去重漏了最大的一份:檔尾 _PNL_3357 跟 test_balance.RAW_PNL_MARGIN 逐 byte 相同
**File**: `tests/capital/test_client.py`
**Line**: 1466-1472

**Comment**:
```
本輪開了 profit_rows.py 收 30 欄字面,但檔尾這份 _PNL_3357 跟 tests/capital/test_balance.py:316 的
RAW_PNL_MARGIN 是完全相同的 30 欄字串(逐字比對 identical)。新加的那行註解說它「與 PNL_3357_MARGIN 是兩組值」
—— 那句對,但真正重複的對象是 RAW_PNL_MARGIN,沒提。結果 prod 實列在 repo 裡仍有兩份互不知情的複本;
下次群益改欄只改到一份,另一份靜默留舊欄形,踩的就是 F-05 這次那個坑。

修法:把 test_balance 的 RAW_PNL_MARGIN / RAW_PNL_ROW 搬進 profit_rows.py,test_balance 與這裡都改 import;
模組 docstring 補「prod 實列 vs 合成列」分工。(_BAL_3357 在本檔另有 12 處內嵌且等於 test_balance.RAW_C_MARGIN,
同型問題但不在本輪 spec 範圍,記 next-time 就好。)要不要在這輪做,你決定。
```
#### F-03 kind=None 哨兵挑到 "3",而 balance.py 寫著「融券疑 3、待實證」
**File**: `tests/capital/test_client.py`
**Line**: 1258-1263

**Comment**:
```
[25] 備援分支可達性成立(30 欄 > 25、"3" 不在 _PNL_KIND_CODE),這點沒問題。
問題是哨兵值:balance.py:153-156 明寫「融券代碼未實證(疑 3)→ 刻意不對映」。等首筆融券實錄到手、有人補
"3": "short",這條測試不會紅 —— kind 變 "short" 後 by_key.get(("3357","short")) 一樣是 None,一樣 continue、
一樣印「種類不符略過 … 原文='信用'」,測試唯一的 log 斷言兩條路都滿足,avg_price 也一樣不被 999 蓋掉。
綠燈留著,但 docstring 講的「標籤與 [25] 皆對不上」已經沒人驗 —— 正是這輪要修掉的 F-05 同型病。

兩擇一或都做:哨兵改成不可能被對映的碼(如 "9");再補一條把 kind=None 釘死的斷言 ——
parse_profit_line 在 kind is None 時另印「profit line 種類標籤未知」(balance.py:203),
assert any("種類標籤未知" in r.message for r in caplog.records) 就能把「未知種類」跟「種類不符」分開。
```
#### F-04 新 fixture 模組的 docstring 數字跟「155.63」語意都不準
**File**: `tests/capital/profit_rows.py`
**Line**: 8-14

**Comment**:
```
兩處:(a)「散在兩個測試檔共六份」—— base 版 test_client.py 有 6 份、test_fill_latency.py 1 份,合計 7
(pr-119 原文自己寫「第 6 / 7 份」);change-spec.md:11 同一個數字也錯。
(b)「均價 150.55 配 _BAL_3357 的 155.63 給 balance 鏈測試斷言」—— 155.63 是庫存報告 [16] 的即時維持率,
balance.py 檔頭跟 test_balance.py:91 都寫「絕不可當價格」,repo 內也沒有任何斷言拿 155.63 當期望值。
這支模組存在的理由就是當欄形 / 份數的唯一真相,自己失準最傷。

「共六份」改「共七份(test_client 6 + test_fill_latency 1)」並同步 change-spec.md:11;
第 14 行刪掉「配 _BAL_3357 的 155.63」那個因果句(要留就寫「[16]=155.63 是維持率,與價格無關」);
下游私有常數的互指註解留在下游那邊就好,共用模組不用反向指名。
```
#### F-05 AVG_SOURCES 跟後端 models.AvgSource 還是純人工同步,這輪的威脅模型正好是「後端先加值」
**File**: `frontend/src/types.ts`
**Line**: 109-110

**Comment**:
```
前端這側同源沒問題(let cost + 無 default 的 switch,AvgSource 多一個成員就 TS2454 紅)。
但跨語言那側:copycat/capital/models.py:26 的 Literal["broker", "fill"] 跟這兩行只靠雙向註解互指。
這輪反覆援引的情境正是「後端先加值 / 前端 dist 沒重 build」—— 白名單把它從印 NaN 降成靜默退回修前口徑
(損益少一筆買費、打平線跳格),沒有任何測試或 gate 會紅,比 #118 更難看到。
repo 對這類契約已有樣板(overlay_parity.json / signal_param_specs.json / river palette 讀前端字面),avg_source 沒有。

照樣板補一條:tests/fixtures/avg_sources.json 雙邊各斷言,或後端測試直接讀 types.ts 字面比 get_args(AvgSource);
CLAUDE.md §4 avg_source 那條補 pin 的位置。這超出 pr-119 F-01~F-07 的範圍,要不要這輪做你決定。
```
#### F-06 修 F-07 補的「最終形態」那句,同一個 PR 內就被後面的 commit 作廢了
**File**: `.claude/bug/breakeven-avg-source-prod-chain/verification.md`
**Line**: 60

**Comment**:
```
F-07 的要旨是「落檔證據跟出貨 code 相反」。這句把最終形態寫成 raw === "broker" || raw === "fill" ? raw : null,
那是 review 收修前的形態;兩個 commit 後(S-2)已改成 isAvgSource(input.avgSource) + AVG_SOURCES as const,
grep 'raw === "broker"' frontend/src 現在零命中。同一個 PR 內就重演了 F-07。

改成「最終形態經 fix/breakeven-review-followups(pr-119 F-02 + review S-2)成為白名單歸一:
ladder-position.ts::isAvgSource 吃 types.ts::AVG_SOURCES(型別由該陣列推導)」,不要引會被取代的字面。
```
#### F-07 artifact 裡引的 commit SHA 全是 rebase 前的,merge 後在乾淨 clone 上是死連結
**File**: `.claude/bug/breakeven-review-followups/verification.md`
**Line**: 15-23

**Comment**:
```
不是 PR 缺陷、是流程層:verification §1/§2 跟 code-review-round-1.json 引的 15fcfd09 / 9e8de3a1 / ce05f592 /
11f11923 / e084b1e2 / 196b1c89 / f8232339 / f2e2aa28,對照分支實際 7 筆(085f9eae … d08739b3)全對不上;
git merge-base --is-ancestor 六筆全 no。本機還撿得到孤兒物件,乾淨 clone 上「紅先行落在哪一筆」的追溯鏈直接斷。
08-25 do 批整體 review 記過的 47/56 dangling 就是同一件事。

處置:artifact 在 merge 後補寫最終 SHA、或改引「相對順序 + commit subject」;要留 SHA 就得用 merge commit。
與既有 next-time 條目併案,本輪不回改。
```
#### F-08 那行 /** Position asdict… */ 現在夾在 AVG_SOURCES 前面,誰也沒描述到
**File**: `frontend/src/types.ts`
**Line**: 106-110

**Comment**:
```
這句描述的是下面的 CapitalPosition,base 就已經被 AvgSource 的註解隔開一次,這輪又插進 AVG_SOURCES +
推導型別兩列,離得更遠。TS 只把「最近那段」掛給下一個宣告,所以現在 hover CapitalPosition 看不到說明、
hover AVG_SOURCES 看到的是 Position 的話。

把 106 那行搬到 export interface CapitalPosition { 正上方就好,一行位移零行為。
```

### Opus 原始 findings (first-pass, context-aware)

- **F-01**(reviewer 原編號 F-1,MEDIUM [python-reviewer])`CLAUDE.md:248` —— §4 新判準把「fut 列 avg_source 恆 null」寫成絕對事實,但 `store._apply_fill_locked` 新倉分支對 `_FUT_MARKETS` 同樣寫 `avg_source="fill"`(line 282-291,`market, kind, key_no = "fut", "cash", contract` 之後共用);OI 失敗時 `_stale_fut_positions()` 沿用已發布物件(avg_price 非 None → carry-over 跳過)留更久。impact:依 §4 會把正常 "fill" 判成契約斷了或順手抹掉。fix:改有界說法。anchor:`` `market == "fut"` 列恆 null 是既知語意(期貨列走 OI 不經損益回填,見 next-time 2026-08-27),不是契約斷了,也不要替它硬填來源(pr-119 F-03)。``。search-proof:grep `avg_source` store.py → :289 `avg_source="fill"` 在 `prev is None` 分支;sed 455-505 確認 carry-over 只在 `p.avg_price is None`
- **F-02**(reviewer 原編號 F-2,MEDIUM [python-reviewer])`tests/capital/test_client.py:1466-1472` —— `_PNL_3357` 與 `test_balance.py:316::RAW_PNL_MARGIN` 逐 byte 相同(python 比對 identical: True,30 欄 vs 30 欄);本輪加的註解只提 `PNL_3357_MARGIN` 是兩組值,沒提真正的重複對象;prod 實列兩份複本。impact:欄形變動只改一份。fix:搬進 `profit_rows.py` 共用。anchor:`#: 2026-06-11 prod 實列(均價 311.75;與 `profit_rows.PNL_3357_MARGIN`(150.55)是兩組值,見該模組註)`。search-proof:grep `451650|468000,464000` tests/ 零殘留;逐字比對 identical
- **F-03**(reviewer 原編號 F-3,LOW [python-reviewer])`tests/capital/test_client.py:1258-1263` —— kind=None 哨兵 `[25]="3"` 是 balance.py:153-156「融券未實證(疑 3)刻意不對映」的保留碼;補對映後 `_on_profit_complete` 對 ("3357","short") 一樣 continue + 印「種類不符」,測試綠但 docstring 不再被驗。fix:哨兵改 "9" / 補 `種類標籤未知` 斷言。anchor:`        client._handle_profit(pnl_variant(row, {3: "信用", 25: "3", 10: "999.00"}))`。search-proof:sed 140-215 balance.py;sed 535-570 client.py 同一條 log
- **F-04**(reviewer 原編號 F-4,LOW [python-reviewer])`tests/capital/profit_rows.py:8-14` —— 「共六份」實為七份(base test_client 6 + test_fill_latency 1);「配 `_BAL_3357` 的 155.63」是維持率不是價;共用模組反向指名下游私有常數。fix:數字改七、刪 155.63 因果句。anchor:`而且散在兩個測試檔共六份 —— 沒人斷 `pnl_cost` 所以一直零訊號。變異一律走 `pnl_variant`(按欄索引),`。search-proof:`git show 2cde2b22:… | grep -c 451650` → 6 / 1;grep 155.63 tests/ → 只有 test_balance.py:91 維持率警告
- **F-05**(reviewer 原編號 F-5,LOW [python-reviewer])`frontend/src/types.ts:109-110` —— `AVG_SOURCES` 與 `models.py:26 AvgSource Literal` 無機械連結;後端先加值時白名單靜默退回修前口徑、零測試紅;repo 既有三處 parity 樣板無 avg_source。fix:補 golden fixture 雙邊斷言。anchor:`export const AVG_SOURCES = ["broker", "fill"] as const;`。search-proof:grep -rln "frontend/src" tests/ → overlay / signal_rules / corr_config 三處;grep AvgSource copycat/ → models.py:26 唯一;spec 未列為目標或非目標
- **F-06**(reviewer 原編號 F-6,LOW [python-reviewer])`.claude/bug/breakeven-avg-source-prod-chain/verification.md:60` —— 「最終形態」引的 `raw === "broker" || raw === "fill" ? raw : null` 已被同 PR 後續 commit(review S-2)取代為 `isAvgSource` + `AVG_SOURCES`。fix:改引 guard 與陣列名。anchor:`最終形態再經 `fix/breakeven-review-followups`(pr-119 F-02)改為白名單歸一 `raw === "broker" || raw === "fill" ? raw : null`。`。search-proof:grep `raw === "broker"` frontend/src → 無命中;git show 34412657 顯示替換
- **F-07**(reviewer 原編號 F-7,LOW [python-reviewer])`.claude/bug/breakeven-review-followups/verification.md:15-23` —— 引用的 8 個 SHA 全非合併後歷史(六筆 `merge-base --is-ancestor` 全 no);追溯鏈斷。fix:merge 後補寫最終 SHA / 改引相對順序 + subject / 用 merge commit;流程層併 next-time。anchor:`| `15fcfd09` | test | F-01 三欄斷言;F-05 fixture 30 欄常數 + kind=None 第二輪 [25]=3;F-04 test_store 去重 |`。search-proof:for s in …; merge-base --is-ancestor → 全 no;`git log 2cde2b22..HEAD` 7 筆無一相符
- **F-08**(reviewer 原編號 F-8,LOW [python-reviewer])`frontend/src/types.ts:106-110` —— `/** Position asdict… */` 與 `CapitalPosition` 之間隔 `AVG_SOURCES`、`AvgSource`、空行;孤兒 JSDoc。fix:搬到 interface 正上方。anchor:`/** Position asdict(sec=股號;fut=期交所契約碼;空方 qty 為負)。 */`。search-proof:sed 104-113 types.ts

已驗證通過的 PR 自述主張(reviewer 逐項核過,無 finding):`PNL_3357_MARGIN` 30 欄且與 `_PNL_IDX_*` / `RAW_PNL_MARGIN` 對齊(451650 = 150.55 × 3000;2.73% 對上 [21]);tests/ 25 欄字面零殘留;`isAvgSource` + `AVG_SOURCES` 保住 exhaustiveness 且白名單自動放行新成員;kind=None 第二輪走得到 [25] 備援;F-06 `positions()` docstring 的「`p is prev`、五行自我賦值」成立(`_with_today_qty_locked` 對 fut 回同物件);commit 分類 test → 🔴 → 🔵 三筆分離。

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查。

### Codex 對 Opus 的複查結果（對稱化 4.2）

**Codex 複查 Opus 失敗 — 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(本機無 codex)。全部 CC finding 視同 INCONCLUSIVE,改由 4.3b 主 agent 逐條實查(結果在發現總覽「Opus 複查」欄與下方備註):

| Opus # | 原始 severity | 4.3b 判斷 | 備註(他軸為何漏 / 主 agent 實查) |
| --- | --- | --- | --- |
| F-01 | MEDIUM | CONFIRMED | 主 agent grep store.py → `:289 avg_source="fill"`,該分支 `market, kind, key_no = "fut", "cash", contract` 後共用;§4 句確為絕對語。in-flow two-axis 兩軸都沒抓到:兩軸都拿 pr-119 F-03 的處方當前提,沒追樂觀套用那條路。 |
| F-02 | MEDIUM | CONFIRMED | 主 agent python 逐字比對 `_PNL_3357` vs `RAW_PNL_MARGIN` → identical=True、30/30 欄。in-flow Standards 軸抓到「同檔兩顆同義常數」但只比對了新常數,沒往 test_balance 看。 |
| F-03 | LOW | CONFIRMED | 主 agent sed balance.py:151-158 → 「融券代碼未實證(疑 3)→ 刻意不對映」逐字在。哨兵選值是 in-flow 兩軸都沒想到的維度。 |
| F-04 | LOW | CONFIRMED | 主 agent `git show 2cde2b22:test_client.py | grep -c 451650` → 6、test_fill_latency → 1;balance.py:11-13 與 test_balance.py:91 維持率警告在。 |
| F-05 | LOW | CONFIRMED | 主 agent 確認 models.py 與 types.ts 無 parity 測試;spec 未把跨語言 parity 列為目標或非目標 → 非 OUT_OF_SCOPE,但超出 pr-119 七條 → ask-user。 |
| F-06 | LOW | CONFIRMED | 主 agent grep `raw === "broker"` frontend/src → 無命中;verification.md:60 字面仍在。 |
| F-07 | LOW | CONFIRMED | 主 agent 對六個 SHA 跑 `merge-base --is-ancestor HEAD` 全 no;rebase merge 的必然後果,流程層。 |
| F-08 | LOW | CONFIRMED | 主 agent sed types.ts:104-113:註解與 interface 之間隔三個宣告;base 已隔一個(既有),本 PR 加重。 |

## Action Items

**Severity calibration**:6c(移除既有防護類)—— 本 PR 不屬移除防護類(白名單歸一是**加**防護、簽名不動);6d-1 hedge cap:F-05 的損害情境是「後端先加值」的假設性窗口 → cap Nice;6d-3 Must Fix 雙半條件:八條無一有 user-visible 重現路徑 + 阻擋發布(全是文件 / 測試 / 型別同步),無 Must / Should;6d-2 由 4.3b 取代;provenance cap N-A。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix（合併前必修）

- 無

### Should Fix（強烈建議）

- 無

### Nice to Have（可選優化）

- F-01 §4 fut 列「恆 null」改有界說法(`CLAUDE.md:248`)—— 樂觀套用列會是 "fill",判準寫錯誤導漂移排查
- F-02 `_PNL_3357` 與 `RAW_PNL_MARGIN` 逐 byte 相同(`tests/capital/test_client.py:1466-1472`)—— 搬進 `profit_rows.py`(ask-user,動 test_balance)
- F-03 kind=None 哨兵改不可對映碼 + 補「種類標籤未知」斷言(`tests/capital/test_client.py:1258-1263`)
- F-04 `profit_rows.py` docstring「六份 → 七份」、刪 155.63 因果句(`tests/capital/profit_rows.py:8-14`;change-spec.md:11 同步)
- F-05 `AVG_SOURCES` ↔ `models.AvgSource` parity 測試(`frontend/src/types.ts:109-110`;ask-user,超出 pr-119 範圍)
- F-06 舊 verification 末句改引 `isAvgSource` / `AVG_SOURCES`(`.claude/bug/breakeven-avg-source-prod-chain/verification.md:60`)
- F-07 artifact 引 rebase 前 SHA(`.claude/bug/breakeven-review-followups/verification.md:15-23`)—— 流程層,no-op 併 next-time
- F-08 `/** Position asdict… */` 搬到 `CapitalPosition` 正上方(`frontend/src/types.ts:106-110`)

### 參考用（任一軸驗證為 REFUTED 或 OUT_OF_SCOPE）

- 無

## 審查工具比較 (qualitative)

- CC 視角(python-reviewer):抓到的都是「修 review finding 時自己再犯一次同型錯」—— F-01 修判準寫成絕對語、F-02 去重漏最大一份、F-04 數字失準、F-06 修「文件與 code 相反」時引了會被取代的字面;加上兩條結構性的(F-05 跨語言 parity 缺、F-07 rebase SHA 死連結)。in-flow two-axis round 1 抓的是「殘留 25 欄字面」與「白名單同源」,本輪抓的是那些收修留下的第二層殘影。
- Codex / Gemini:N-A。
- 4.3b:CONFIRMED 8 / 0 降級;無 lone-finding 降級(他軸缺席不算沉默)。
- 對抗式第三軸增益:N-A。

## 沒做的部分（結案對帳）

- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(grep / git show / python 比對)。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A(無 .tsx)。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 實跑)。
- 真實環境:本 PR 零行為改動(前端白名單對合法輸入逐 bit 不變),prod 不需為此重啟;`avg_source == "broker"` 判準的真環境核對留 08-28。
- 未驗證前提:F-05 的「後端先加值」是假設性情境(cap Nice);F-03 的「日後補 "3": "short"」同樣假設性。
- Self-Verify:已執行,COMPLIANT(auditor 以 Read 讀取草稿檔本身,未讀其他產物)。
