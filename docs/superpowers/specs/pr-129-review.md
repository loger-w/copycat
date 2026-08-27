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
## [完整證據副檔](pr-129-review.audit.md)
### finding_uid 索引
[fae7dde376bc06fbf398](pr-129-review.audit.md#發現總覽) · [57256fe40e3bdcde8cc7](pr-129-review.audit.md#發現總覽) · [281305b8e499d4bcbcb1](pr-129-review.audit.md#發現總覽) · [7aab1c366e2ecafd07d8](pr-129-review.audit.md#發現總覽) · [e4983699bf87dcda5934](pr-129-review.audit.md#發現總覽) · [6bbbb37fbce014aec352](pr-129-review.audit.md#發現總覽) · [eb36e4746e8399aa124a](pr-129-review.audit.md#發現總覽) · [59fde2ef7631f52b7532](pr-129-review.audit.md#發現總覽)
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
## 沒做的部分（結案對帳）
- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(grep / git show / python 比對)。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A(無 .tsx)。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 實跑)。
- 真實環境:本 PR 零行為改動(前端白名單對合法輸入逐 bit 不變),prod 不需為此重啟;`avg_source == "broker"` 判準的真環境核對留 08-28。
- 未驗證前提:F-05 的「後端先加值」是假設性情境(cap Nice);F-03 的「日後補 "3": "short"」同樣假設性。
- Self-Verify:已執行,COMPLIANT(auditor 以 Read 讀取草稿檔本身,未讀其他產物)。
