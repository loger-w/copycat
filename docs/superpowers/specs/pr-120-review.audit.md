# PR #120 Code Review 比較報告 · SHA 46c661cc

**Report projection schema**: 1

**PR**: [loger-w/copycat#120](https://github.com/loger-w/copycat/pull/120)
**標題**: fix(corr): SXF 稀疏腿以設定檔 sparse 旗標豁免 R2 單 symbol 自癒(仍留 R1 母體)
**作者**: loger-w(commits 署名 Loger)
**分支**: `fix/corr-sparse-leg-heal-exempt` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 7c7ad17e;回溯 review)
**變更**: 15 檔案, +497 / -11
**審查日期**: 2026-08-27
**Review input basis**: source repo R_kgDOTsITBg + 46c661cc6db4189144c7e0d61d2aa539db97d532;destination repo R_kgDOTsITBg + 8200f210e15d7c2cafe58dbc661ff4347a2fb6c4;`input_binding: verified`(worktree HEAD = source SHA,`git fetch refs/pull/120/head` 後 rev-parse 逐字相等;destination SHA 為 master 歷史上的既有 commit,`git merge-base --is-ancestor` 成立)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-120`(detached)
**worktree HEAD**: 46c661cc6db4189144c7e0d61d2aa539db97d532
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer(不切塊,單一 dispatch;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=15 → covered 5 / no-issues 10 / skipped 0 / **missed 0**(chunked: 否;FILE_COUNT=9 源檔 ≤ 15、DIFF_LINES=508 < 800;reviewer 逐檔 accounting 15/15,union = F)
**定位 (ENH-B)**: anchored exact 5 / ambiguous 0 / **FAILED 0**(全部 anchor 於 worktree HEAD 以 grep 逐字比中,line 以比中結果為準)
**React-doctor (2.97)**: N-A(非 React PR:F 無前端檔)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,15 檔全部 authored)
**審查軸狀態**: primary(python-reviewer)PASS(5 findings、15/15 accounting);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條判斷式複查,見備註欄);React-doctor N-A(非 React PR)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus)回 R1–R10 全 PASS、`VERDICT: COMPLIANT`;無需補寫

**Report generation**: sha256:052821dbdc4a760bd664eb2172cf28cac54d0400ba761652e2d3556072074af2

---

## Spec 依據

- 偵測到 `.claude/bug/corr-sparse-leg-heal-exempt/spec.md`(/bug originating spec:症狀、根因、要求 1–4 含白名單、驗證 seam、非目標)。
- ⚠️ spec 作者 = PR 作者(同一 session 產出)。

- `SPEC_COMPLIANCE` receipt:gate=SKIPPED;dispatch=NOT_APPLICABLE;dispatch_count=0;reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED(spec 位於 `.claude/<flow>/<slug>/`,不在 authority 允許路徑;同 08-27 #118 判定);requested_model=opus;observed_model=UNAVAILABLE;effort=xhigh;tools=0;0 clauses / 0 findings / 0 observations / 0 invalidated

## 變更概要

provenance:15 authored / 0 inherited(base = master,免驗)。

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `.claude/bug/corr-sparse-leg-heal-exempt/code-review-round-1.json` | 無 finding(新增) | in-flow round 1 14 條處置,與 HEAD 逐條對得上 |
| `.claude/bug/corr-sparse-leg-heal-exempt/spec.md` | 無 finding(新增) | 症狀 / 根因 / 要求 1–4 + 白名單 / 非目標,與 diff 一致 |
| `.claude/bug/corr-sparse-leg-heal-exempt/verification.md` | 有 finding(新增) | 反向驗證 stash 整檔(F-05) |
| `.claude/skills/tc4-market-facts/SKILL.md` | 無 finding(修改) | SXF 日盤靜默事實 + attempt 恆 1 更正 |
| `CLAUDE.md` | 有 finding(修改) | §4 sparse 契約條(F-01:誤標症狀寫反) |
| `configs/correlation.json` | 無 finding(修改) | SXF `sparse: true` + `_comment` |
| `copycat/corr_config.py` | 有 finding(修改) | `Leg.sparse`、`_parse_legs` 只認字面 true、非 tc4 腿 WARNING(F-02 非 bool 靜默) |
| `copycat/live/corr_source.py` | 無 finding(修改) | 透傳 `heal_sparse_symbols` |
| `copycat/live/tc4.py` | 無 finding(修改) | `heal_sparse_symbols` 參數、R2 `continue`、邊界註解 |
| `copycat/server/app.py` | 有 finding(修改) | `_default_corr_source(calendar, config)`、`_make_corr` 同一份 config(F-04 optional 不變量) |
| `docs/next-time.md` | 無 finding(修改) | N051 改口 + 四條留尾 |
| `tests/live/test_corr_source.py` | 無 finding(修改) | 預設空集合 + 透傳 |
| `tests/live/test_tc4.py` | 有 finding(修改) | `TestHealSparseSymbol` 四條(F-03 測試名反) |
| `tests/server/test_main_wiring.py` | 無 finding(修改) | sparse 集合接線兩面 |
| `tests/test_corr_config.py` | 無 finding(修改) | sparse 解析 / parity / 非 tc4 WARNING |

## 發現總覽

| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | §4 新契約條「誤標」半句寫「session 死時該腿整場不救」—— 實作相反:sparse 仍在 R1 母體,session 死時**一定**整批重掛;誤標真正的代價是**單腿死**(其他腿還在推、R1 不成立)時整場不救。同 PR 的 next-time 與 `tc4.py:340` 都寫對,只有 §4 寫反(`CLAUDE.md`) | MEDIUM [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 契約條唯一判準寫反(誤標症狀);一句改對並對齊 next-time;非 release-blocking |
| F-02 | `sparse` 打成 `"true"` / `1` / `"yes"` 全部靜默變 False(行為 fail-safe 正確),但同一支 `load_config` 剛為「標在非 tc4 腿」加了 WARNING —— 同類「旗標被丟掉」一種點名一種沉默,且測試把沉默釘成契約(`copycat/corr_config.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 行為 fail-safe 正確,只補 WARNING 訊號;與同函式 S6 那條 WARNING 判準一致 |
| F-03 | 測試名讀作「稀疏腿不會**阻止** R1 觸發」,本體卻是 `HEAL_A` 活著 → `assert api.rt_requests == []`(R1 **不**觸發、靜默的稀疏腿不把它拖進整批重掛);要表達的是「不會**誤觸** R1」(`tests/live/test_tc4.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 測試名與斷言相反;改名不動本體 |
| F-04 | 「source 稀疏腿集合與 engine 腿組吃同一份 config」是本 PR 立的不變量,但 `config` optional + `:408` 的 fallback 讓「各讀各的」結構上仍合法;prod 唯一 caller 帶 config、四個測試 caller 全不帶 → 刪掉 `corr_cfg` 引數 3115 條全綠,不變量零訊號;測試因此綁真檔 `CONFIG_PATH`(`copycat/server/app.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `ask-user` | config 改必填 = 四個測試 caller 一起改、簽名變動;不變量現況只活在註解,要不要用型別守請 user 決定 |
| F-05 | 反向驗證 `git stash push copycat/live/tc4.py` 一併撤掉建構子參數與 `_heal_tick` 的 `continue`,三條全炸在 `TypeError`(與 §1 紅先行同一個紅),證不到行為那一行 load-bearing;真正該證的是只拿掉 `continue` 時哪幾條紅(語意上 2 紅 2 綠)(`.claude/bug/corr-sparse-leg-heal-exempt/verification.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 反向驗證與紅先行同源(建構子 TypeError),沒帶新資訊;改成 mutation 級重跑並記回 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 020b74d636a9dac3f341 action=auto-fix
F-02 finding_uid: 8c295cf185bdfc61f3cb action=auto-fix
F-03 finding_uid: 8577fe510484126663b5 action=auto-fix
F-04 finding_uid: fe88cf800eb28e4e36b9 action=ask-user
F-05 finding_uid: 3b3f7d8a7d95416134fc action=auto-fix

### Inline Comments per Finding（直接複製貼到 PR review）

#### F-01 §4 那句「誤標 = session 死時不救」剛好寫反

**File**: `CLAUDE.md`
**Line**: 257-258

**Comment**:
```
「誤標」那半句寫「session 死時該腿整場不救」—— 但 sparse 只跳 R2、仍在 R1 母體,session 整條死掉時一定會被整批重掛
(同一行前半句自己也寫了「sparse 腿仍在 R1 母體」)。誤標真正付的代價是**單腿死**(其他腿還在推 → R1 結構上不成立)時整場不救。
同 PR 的 next-time 08-27 第一條跟 tc4.py:340 都寫對了,只有 §4 這條反。§4 是漂移排查的唯一權威,
照這句去查「session 死沒死」會查錯方向。

改成:「單腿死(session 其他腿還在推,R1 不成立)時該腿整場不救;session 整條死掉仍由 R1 整批救」,與 next-time 同句。
```

#### F-02 sparse 打錯型別會靜默失效,同函式另一種誤設卻有 WARNING

**File**: `copycat/corr_config.py`
**Line**: 100-102

**Comment**:
```
`is True` 本身對(json 的 true 就是 True 單例、1 is True 是 False,fail-safe 方向也對),問題是只有行為沒訊號:
"sparse": "true" / 1 / "yes" 全部靜默變 False,而同一支 load_config 剛剛才為「標在非 tc4 腿」加了 WARNING。
correlation.json 是給人手改的檔,打成字串 → 這條腿的修復靜默不生效,退回每 240 s 一發那個 bug,只能事後 grep log 才知道。

_parse_legs 同一處補型別檢查(module 已有 logger):
    raw_sparse = item.get("sparse")
    if raw_sparse is not None and not isinstance(raw_sparse, bool):
        logger.warning("corr 設定檔 %s 的 sparse 非 true/false(%r),旗標無效", item.get("key"), raw_sparse)
sparse=raw_sparse is True 不動;既有 "yes" / 1 兩案加一條 caplog 斷言。
```

#### F-03 這條測試的名字跟它斷言的方向相反

**File**: `tests/live/test_tc4.py`
**Line**: 1334

**Comment**:
```
名字讀作「稀疏腿不會阻止 R1 觸發」,但本體是 _last_push = {HEAL_A: 95, HEAL_B: 10} + assert rt_requests == []——
釘的是「HEAL_A 活著 → R1 不觸發、靜默的稀疏腿不會把它拖進整批重掛」,測試內註解也這樣寫。
它守的是「別誤觸整批重掛」(誤觸 = 10 條腿一起 UNSUB+SUB),名字反了以後看到它紅會往錯方向查。

改名 test_sparse_symbol_does_not_trigger_r1_while_another_leg_is_alive,本體不動。
```

#### F-04 config 是 optional,所以「同一份」那條不變量其實沒人守

**File**: `copycat/server/app.py`
**Line**: 389-391

**Comment**:
```
本 PR 立的不變量是「source 的稀疏腿集合跟 engine 的腿組吃同一份 config」,但 config 是 optional、:408 有 fallback,
各讀各的在結構上還是合法;prod 唯一 caller(:886)帶 config,四個測試 caller 全不帶 → 把 :887-889 的 corr_cfg 引數刪掉,
3115 條全綠。不變量只活在註解裡,哪天被當「沒人用的參數」清掉就分岔回去。附帶四個測試因此綁在真檔 CONFIG_PATH 上。

改必填:`def _default_corr_source(calendar: TradingCalendar | None, config: CorrConfig) -> CorrSource:`,刪 :408;
四個測試 caller 顯式傳 load_config() 或自建 CorrConfig —— 刪引數即 TypeError,由型別守。簽名變動 + 四處測試,要不要做你決定。
```

#### F-05 反向驗證 stash 整支 tc4.py,紅的是簽名不是那行 continue

**File**: `.claude/bug/corr-sparse-leg-heal-exempt/verification.md`
**Line**: 49-50

**Comment**:
```
`git stash push copycat/live/tc4.py` 把建構子參數跟 _heal_tick 的 continue 一起撤了,三條測試全炸在 TypeError ——
跟 §1 Phase 1 的紅是同一個紅,證不到「那行 continue 是 load-bearing」。
本輪結論不受影響(兩條測試確實釘得住),但 §5 掛的是「反向驗證 PASS」的旗,這次它沒帶新資訊;
下次照抄這個手法、改動只在 body 不在簽名時,反向驗證會變成永遠 PASS 的空跑。

改成 mutation 級:只註解掉 `if sym in self._heal_sparse: continue` 兩行,記「2 failed / 2 passed」跟是哪兩條;簽名層的紅由 §1 涵蓋不重複計。
```

### Opus 原始 findings (first-pass, context-aware)

- **F-01**(reviewer 原編號 F-1,MEDIUM [python-reviewer])`CLAUDE.md:257-258` —— §4 新契約條「誤標」半句寫「session 死時該腿整場不救」—— 實作相反:sparse 仍在 R1 母體,session 死時**一定**整批重掛;誤標真正的代價是**單腿死**(其他腿還在推、R1 不成立)時整場不救。同 PR 的 next-time 與 `tc4.py:340` 都寫對,只有 §4 寫反。anchor:``heal_symbol_active` **正交**:sparse 腿仍在 R1 母體。漂掉的症狀:該腿每 240 s 一發「零推播自癒 … attempt 1」`。search-proof:grep 稀疏腿 tc4.py / app.py / corr_config.py 三處註解;sed 620-650 tc4.py 確認 R1 母體未扣 sparse
- **F-02**(reviewer 原編號 F-2,LOW [python-reviewer])`copycat/corr_config.py:100-102` —— `sparse` 打成 `"true"` / `1` / `"yes"` 全部靜默變 False(行為 fail-safe 正確),但同一支 `load_config` 剛為「標在非 tc4 腿」加了 WARNING —— 同類「旗標被丟掉」一種點名一種沉默,且測試把沉默釘成契約。anchor:`legs.append(`。search-proof:grep -n 'isinstance\|logger' copycat/corr_config.py → 無值域檢查;load_config :131-138 只判 leg.source
- **F-03**(reviewer 原編號 F-3,LOW [python-reviewer])`tests/live/test_tc4.py:1334` —— 測試名讀作「稀疏腿不會**阻止** R1 觸發」,本體卻是 `HEAL_A` 活著 → `assert api.rt_requests == []`(R1 **不**觸發、靜默的稀疏腿不把它拖進整批重掛);要表達的是「不會**誤觸** R1」。anchor:`def test_sparse_symbol_does_not_keep_r1_from_firing(self) -> None:`。search-proof:sed -n 1334,1352p tests/live/test_tc4.py;_heal_tick:629 quiet_since = max(...)
- **F-04**(reviewer 原編號 F-4,LOW [python-reviewer])`copycat/server/app.py:389-391` —— 「source 稀疏腿集合與 engine 腿組吃同一份 config」是本 PR 立的不變量,但 `config` optional + `:408` 的 fallback 讓「各讀各的」結構上仍合法;prod 唯一 caller 帶 config、四個測試 caller 全不帶 → 刪掉 `corr_cfg` 引數 3115 條全綠,不變量零訊號;測試因此綁真檔 `CONFIG_PATH`。anchor:`def _default_corr_source(`。search-proof:grep -rn _default_corr_source → app.py:886 + test_main_wiring.py:458/471/479/496/527;grep DEFAULT_CORR tests → 只斷 sentinel
- **F-05**(reviewer 原編號 F-5,LOW [python-reviewer])`.claude/bug/corr-sparse-leg-heal-exempt/verification.md:49-50` —— 反向驗證 `git stash push copycat/live/tc4.py` 一併撤掉建構子參數與 `_heal_tick` 的 `continue`,三條全炸在 `TypeError`(與 §1 紅先行同一個紅),證不到行為那一行 load-bearing;真正該證的是只拿掉 `continue` 時哪幾條紅(語意上 2 紅 2 綠)。anchor:`git stash push copycat/live/tc4.py → TestHealSparseSymbol 3 failed`。search-proof:sed -n 46,51p verification.md;git diff 8200f210...HEAD -- copycat/live/tc4.py

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查。

### Codex 對 Opus 的複查結果（對稱化 4.2）

**Codex 複查 Opus 失敗 — 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(本機無 codex)。全部 CC finding 視同 INCONCLUSIVE,改由 4.3b 主 agent 逐條判斷式複查(結果在發現總覽「Opus 複查」欄與下方備註):

| Opus # | 原始 severity | 4.3b 判斷 | 備註(他軸為何漏 / 主 agent 實查) |
| --- | --- | --- | --- |
| F-01 | MEDIUM | CONFIRMED | 主 agent sed tc4.py:624-635:R1 母體 subs 不看 _heal_sparse,命中後整批含 sparse;test_sparse_symbol_still_rides_r1_batch_heal 已證。 |
| F-02 | LOW | CONFIRMED | 主 agent grep isinstance|logger corr_config.py:_parse_legs 只有兩道結構檢查;load_config WARNING loop 只判 source。 |
| F-03 | LOW | CONFIRMED | 主 agent sed 1334-1352:R1 判定 max(95,10)=95,95 < 70 不成立 → 無請求,與名字宣稱相反。 |
| F-04 | LOW | CONFIRMED | 主 agent grep _default_corr_source → prod caller 僅 app.py:886;測試 caller 五處僅一處帶 config。round 1 P5 反駁 reviewer 同意。 |
| F-05 | LOW | CONFIRMED | 主 agent 讀 verification §5 與 tc4.py diff(建構子 + 指派 + 兩行 continue 同檔);stash 一次全撤 → TypeError 同源。未實跑 mutation。 |

## Action Items

**Severity calibration**:6c(移除既有防護類)—— 本 PR 無移除既有防護類 finding(sparse 旗標只豁免 R2、R1 母體保留,reviewer 逐項核白名單四項逐字未動);6d-1 hedge cap / 6d-3 Must Fix 雙半條件逐條套用(見各條 Action 理由);6d-2 由 4.3b 取代;provenance cap N-A。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix（合併前必修）

- 無

### Should Fix（強烈建議）

- 無

### Nice to Have（可選優化）

- F-01 §4 那句「誤標 = session 死時不救」剛好寫反(`CLAUDE.md:257-258`)—— 契約條唯一判準寫反(誤標症狀);一句改對並對齊 next-time;非 release-blocking
- F-02 sparse 打錯型別會靜默失效,同函式另一種誤設卻有 WARNING(`copycat/corr_config.py:100-102`)—— 行為 fail-safe 正確,只補 WARNING 訊號;與同函式 S6 那條 WARNING 判準一致
- F-03 這條測試的名字跟它斷言的方向相反(`tests/live/test_tc4.py:1334`)—— 測試名與斷言相反;改名不動本體
- F-04 config 是 optional,所以「同一份」那條不變量其實沒人守(`copycat/server/app.py:389-391`)—— config 改必填 = 四個測試 caller 一起改、簽名變動;不變量現況只活在註解,要不要用型別守請 user 決定
- F-05 反向驗證 stash 整支 tc4.py,紅的是簽名不是那行 continue(`.claude/bug/corr-sparse-leg-heal-exempt/verification.md:49-50`)—— 反向驗證與紅先行同源(建構子 TypeError),沒帶新資訊;改成 mutation 級重跑並記回

### 參考用（任一軸驗證為 REFUTED 或 OUT_OF_SCOPE）

- 無

## 審查工具比較 (qualitative)

- CC 視角(python-reviewer):六項實查(R1/R2 母體、Data Clump、`is True` 解析、config 讀取點、parity 測試冗餘、六處說明)逐一給獨立判斷,5 條新發現全屬文件 / 訊號 / 命名 / 不變量守護,無行為 bug;round 1 的 14 條處置逐條對得上,P5 反駁同意。
- Codex / Gemini:N-A。
- 4.3b:CONFIRMED 5 / 0 降級。
- 對抗式第三軸增益:N-A。

## 沒做的部分（結案對帳）

- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)。
- 真實環境:次一交易日 `grep 零推播自癒 | grep SXF` 全日 0 筆(非 0 須同秒成批)尚未驗;prod 15:20 起的 59b70213 已含本 PR。
- 未驗證前提:F-05 指出的「只拿掉 continue 兩條紅兩條綠」為 reviewer 語意推演,主 agent 未實跑該 mutation。
- Self-Verify:已執行,COMPLIANT(auditor 以 Read 讀取草稿檔本身,未讀其他產物)。
