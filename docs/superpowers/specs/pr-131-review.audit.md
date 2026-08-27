# PR #131 Code Review 比較報告 · SHA 49fac608
**Report projection schema**: 1

**PR**: [loger-w/copycat#131](https://github.com/loger-w/copycat/pull/131)
**標題**: chore: /pr-review #128 / #129 / #130 22 條 finding 收修(sparse WARNING 延後印、測試重組、AvgSource parity、文件 14 條)
**作者**: loger-w(commits 署名 Loger)
**分支**: `chore/pr-review-128-130-followups` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 c80dbde5;回溯 review)
**變更**: 28 檔案, +448 / -88
**審查日期**: 2026-08-28
**Review input basis**: source repo R_kgDOTsITBg + 49fac6084df2142d30eca64400e50a69e6fe1764;destination repo R_kgDOTsITBg + c37e0401deacdb3cdc44d6f29b65a166ce04e8b9;`input_binding: verified`(`git fetch refs/pull/131/head` 後 FETCH_HEAD 與 headRefOid 逐字相等、worktree HEAD = source SHA;destination SHA 為 master 歷史上的既有 commit,`git merge-base --is-ancestor` 成立)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED、分支已刪);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-131`(detached)
**worktree HEAD**: 49fac6084df2142d30eca64400e50a69e6fe1764
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 主 agent 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer(不切塊,單一 dispatch;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=28 → covered 3 / no-issues 25 / skipped 0 / **missed 0**(chunked: 否;FILE_COUNT=13 源檔 ≤ 15、DIFF_LINES=536 < 800;reviewer 逐檔 accounting 28/28,union = F;F-04 為 commit 訊息層 finding、不佔檔案)
**定位 (ENH-B)**: anchored exact 3 / ambiguous 0 / **FAILED 0**(三個 anchor 於 worktree HEAD 以 grep 逐字比中且唯一,line 以比中結果為準;F-04 anchor `<none>`、無 file:line、不計)
**React-doctor (2.97)**: N-A(非 React PR:F 只有 `frontend/src/types.ts` 一個 `.ts`,無 `.jsx` / `.tsx`)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,28 檔全部 authored)
**審查軸狀態**: primary(python-reviewer)PASS(4 findings、28/28 accounting、8 條 PR 自我宣稱逐條核對);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條實查,見備註欄);React-doctor N-A(非 React PR)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus)回 R1–R10 全 PASS、`VERDICT: COMPLIANT`;無需補寫

**Report generation**: sha256:ecbcb14cad67b7fa1e7d84c8a688f54245d13f10d5d914584532c54f460bbbf7

---

## Spec 依據

- 偵測到 `.claude/chore/pr-review-128-130-followups/change-spec.md`(= handoff 複本:§2 三條 ask-user、§3 22 條 finding 的分組與目標措辭、§4 紀律提醒;來源 `docs/superpowers/specs/pr-128-review.md` 6 條 / `pr-129-review.md` 8 條 / `pr-130-review.md` 8 條,全 Nice)。非目標未明列;白名單 = 三個 PR 行為逐 bit 不變,除 #130 F-01。
- ⚠️ spec 作者 = PR 作者(handoff 由前一 session 同 agent 產出;三條 ask-user 由 user 拍板「全做」)。本輪 F-02 正是本 PR 自己的 verification §1 沒跟上同分支後段收修 —— 與 spec 自寫、自實作、自驗同源。
- `SPEC_COMPLIANCE` receipt:gate=SKIPPED;dispatch=NOT_APPLICABLE;dispatch_count=0;reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED(reducer `resolve-authority` 以 `py -3.14` 實跑,候選 = change-spec §3 🔴 那句:spec 位於 `.claude/chore/<slug>/`,不在 `openspec/specs/**` / `openspec/changes/**` 允許路徑);requested_model=opus;observed_model=UNAVAILABLE;effort=xhigh;tools=0;0 clauses / 0 findings / 0 observations / 0 invalidated

## 變更概要

provenance:28 authored / 0 inherited(base = master,免驗)。

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `copycat/corr_config.py` | 無 finding(修改) | 唯一行為改動:`_parse_legs` 回 `_ParsedLegs(legs, bad_sparse)` NamedTuple,壞 sparse WARNING 由 `load_config` 過完 legs / base 兩道降級後才印(#130 F-01);`(review S-3)` 尾綴隨之消失 |
| `copycat/live/stock_source.py` | 無 finding(修改) | 閘註解三段改寫:重補入列點限定語(#128 F-04)、櫃買走 MIS(F-03)、現價欄「應會跟著回來(未實測)」(F-01);reviewer 逐句核過 `_subscribe_and_backfill:297` / `stock_engine.py:1109` |
| `copycat/server/app.py` | 無 finding(修改) | `(review S-1)` 尾綴刪(#130 F-02) |
| `copycat/server/verify.py` | 無 finding(修改) | 既存同型 `(review S-1)` 尾綴一併刪 |
| `configs/correlation.json` | 無 finding(修改) | `_comment` 補 sparse 值型別與「整份被丟時只印改用預設腿」(#130 F-07);JSON 仍可解析、11 腿 |
| `frontend/src/types.ts` | 無 finding(修改) | `/** Position asdict… */` 搬回 `CapitalPosition` 正上方(#129 F-08) |
| `CLAUDE.md` | 有 finding(修改) | §4 三處:avg_source 有界說法 + parity pin(#129 F-01 / F-05)、index 閘 descriptor 改 stale watchdog + 可觀測症狀 + 測試路徑(#128 F-02 / F-06)、sparse 句補 F-01 例外;新括號句漏 `_is_trading_day`(F-03) |
| `docs/next-time.md` | 無 finding(修改) | 新 08-27 章節三條(#129 F-07 SHA dangling、`_BAL_3357` 同型、WS 順序型 flake 標非本輪);原 txf-overlay 標題經 round 1 S-1 還原 |
| `tests/test_corr_config.py` | 無 finding(修改) | 紅先行 `test_bad_sparse_flag_is_not_reported_when_the_whole_file_is_discarded`(parametrize `(tail, base)`);river palette 測試改走 helper |
| `tests/capital/profit_rows.py` | 無 finding(修改) | `RAW_PNL_ROW` / `RAW_PNL_MARGIN` 收進單一定義處(#129 F-02);docstring 七份、刪 155.63 因果句(F-04);reviewer 以 `6f1e6420^` 實數 6 + 1 核過 |
| `tests/capital/test_balance.py` | 無 finding(修改) | 兩列改 import |
| `tests/capital/test_client.py` | 無 finding(修改) | 哨兵 `[25]="3"` → `"9"` + 釘「種類標籤未知」(#129 F-03);`_PNL_3357` 刪、改 `RAW_PNL_MARGIN` |
| `tests/capital/test_models.py` | 無 finding(修改) | 新 `test_avg_source_parity_with_frontend`(#129 F-05) |
| `tests/helpers/frontend_source.py` | 有 finding(新增) | `read_frontend_source(rel)`;docstring「唯一入口」與 `test_stock_watchlist.py:269` 不符(F-01) |
| `tests/live/test_stock_source.py` | 無 finding(修改) | parity 測試搬走、留指路註解;class docstring 櫃買措辭同步 |
| `tests/server/test_index_engine.py` | 無 finding(修改) | 新 `test_watch_end_is_the_index_heal_gate_boundary`(#128 F-06) |
| `tests/server/test_main_wiring.py` | 無 finding(修改) | 三條不看 sparse 的測試改傳 `DEFAULT_CONFIG`(#130 F-05) |
| `.claude/chore/pr-review-128-130-followups/change-spec.md` | 無 finding(新增) | handoff 複本(spec) |
| `.claude/chore/pr-review-128-130-followups/verification.md` | 有 finding(新增) | §1 紅先行 / §3 mutation / §5 gate / §6 事故 / §7 two-axis;§1 描述的是被 §7 收修推翻的中途形態(F-02) |
| `.claude/chore/pr-review-128-130-followups/code-review-round-1.json` | 無 finding(新增) | two-axis round 1:Standards 7 / Spec 4 處置 |
| `.claude/bug/breakeven-avg-source-prod-chain/verification.md` | 無 finding(修改) | 末句改引 `isAvgSource` / `AVG_SOURCES`(#129 F-06) |
| `.claude/bug/breakeven-review-followups/change-spec.md` | 無 finding(修改) | 六份 → 七份(#129 F-04) |
| `.claude/bug/corr-sparse-leg-heal-exempt/verification.md` | 無 finding(修改) | 「三條」→ 當時三條 / 現四條(#130 F-06) |
| `.claude/bug/sparse-review-followups/change-spec.md` | 無 finding(修改) | 白名單第 1 條不綁長度(#130 F-08) |
| `.claude/bug/sparse-review-followups/verification.md` | 無 finding(修改) | 「型別守住」有界改寫(#130 F-03)、`2e31a9bc` 不可覆核註記 + 差異片段(F-04;reviewer 以 `git show` 逐字核對片段正確) |
| `.claude/mod/heal-gate-per-consumer/verification.md` | 無 finding(修改) | M4 列補選集(#128 F-05) |
| `.claude/mod/stock-heal-gate-end-1325/change-spec.md` | 無 finding(修改) | 重補路徑限定語(#128 F-04) |
| `.claude/mod/stock-heal-gate-end-1325/verification.md` | 無 finding(修改) | 同上 |

## 發現總覽

| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | 新 helper docstring 自稱「後端測試讀前端原始碼字面的唯一入口」,但 `tests/test_stock_watchlist.py:269` 仍自己算 `parents[1]` 讀 `frontend/src/lib/constants.ts`(同樣是 §4 parity lock):round 1 S-4 想根治的「各測試各數各的」還剩一處,敘述超出程式碼(`tests/helpers/frontend_source.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep `parents\[` tests/ → 僅 test_stock_watchlist.py:269 一處未走 helper;兩擇一:該條改走 helper,或 docstring 降為「跨語言 parity 測試共用入口」 |
| F-02 | 本 PR 自己的 verification §1 寫 fix commit「以輸出參數蒐集」,但 HEAD 的 `_parse_legs` 已在 `2bd63ccc`(round 1 S-5 / P-3 收修)改成回傳 `_ParsedLegs` NamedTuple;§7 有記、§1 未回指 —— 與本 PR 修的 #129 F-06「引了會被取代的字面」同型(`.claude/chore/pr-review-128-130-followups/verification.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep `def _parse_legs` → `:103 def _parse_legs(raw: object) -> _ParsedLegs \| None`;§1:12 仍寫 `_parse_legs(raw, bad_sparse)`;一句補「(收修後改 NamedTuple 回傳,見 §7)」 |
| F-03 | §4 index 閘條新括號句「有日曆到午夜」漏掉 `_is_trading_day` 這道閘:`_broadcast_loop:656` 是 `now_t >= _WATCH_END and self._is_trading_day(...)`,休市日一發都不打(該處註解自述);契約條寫得比 code 寬,日後有人照這句判「假日晚上沒自癒 = 壞了」。同型漏字亦見 `stock_source.py:53` / `next-time.md:59`(#128 既有,非本 PR 新增)(`CLAUDE.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent sed index_engine.py:653-658 確認 calendar 分支 AND `_is_trading_day`;三處同句一起改「有日曆且為交易日 → 到午夜」 |
| F-04 | commit 慣例兩處瑕疵:(a) `1d2242f5` subject `refactor: …` 無 scope —— 全庫 525 筆 typed subject 中唯一一筆無 scope,且內容全是註解 / JSDoc 位移,依本 PR 自家 round 1 S-7 定調應歸 `chore`;(b) `1f3fe386` 標 `refactor(tests)` 卻含新增斷言(🟢 混 🔵),round 1 已以「不重寫本地歷史」accepted(commit 訊息層,無 file:line) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | 參考用 | `no-op` | 主 agent `git log --pretty=%s` grep 無 scope typed subject → 1(即 1d2242f5)/ 有 scope 524;已 rebase merge 進 master,歷史不重寫;下輪分 commit 時純註解一律歸 `chore(<scope>)`、新增斷言另拆 `test` commit |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 149c1e0df22a7b110310 action=auto-fix
F-02 finding_uid: da19627d3279a66386fa action=auto-fix
F-03 finding_uid: 9e9c9bfe300e6fbf256c action=auto-fix
F-04 finding_uid: 50bff2f62557926c2119 action=no-op inline=none

### Inline Comments per Finding（直接複製貼到 PR review）

#### F-01 這支 helper 說自己是「唯一入口」,但 test_stock_watchlist 還在自己算路徑
**File**: `tests/helpers/frontend_source.py`
**Line**: 1

**Comment**:
```
docstring 寫「後端測試讀前端原始碼字面的唯一入口」,但 tests/test_stock_watchlist.py:269 的
test_frontend_constant_matches_backend 還是自己 Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "constants.ts"
—— 同樣是 CLAUDE.md §4 的 parity lock(WATCHLIST_LIMIT),round 1 S-4 要收的「parents[N] 各數各的」就剩這一處。
下一個人 grep 這支 helper 會以為已經收斂完。

兩擇一:那條改成 read_frontend_source("lib/constants.ts"),或把「唯一入口」降成「跨語言 parity 測試共用入口(river palette / AVG_SOURCES;
constants.ts 那條尚未接)」。前者順手做掉最乾淨。
```

#### F-02 verification §1 寫的還是被 §7 推翻的那個形狀
**File**: `.claude/chore/pr-review-128-130-followups/verification.md`
**Line**: 12

**Comment**:
```
§1 說 fix commit ee916937 是「_parse_legs(raw, bad_sparse) 以輸出參數蒐集」—— 那是 round 1 之前的形態;
2bd63ccc(S-5 / P-3 收修)已改成 def _parse_legs(raw) -> _ParsedLegs | None 回傳 NamedTuple(corr_config.py:103)。
§7 / JSON 有記收修,但 §1 沒回指,只讀 §1 的人拿到的是被自己 review 推翻的實作形狀 —— 正好是本 PR 修 #129 F-06
「引了會被取代的字面」那一型。

§1 那行尾巴補一句「(round 1 S-5 / P-3 收修後改為 `_ParsedLegs` NamedTuple 回傳,見 §7)」就好。
```

#### F-03 這句「有日曆到午夜」把休市日也算進去了,code 沒有
**File**: `CLAUDE.md`
**Line**: 277

**Comment**:
```
新括號句「分時自癒 09:00 起全程都在,_WATCH_END 後只是換成尾段判準接手 —— 有日曆到午夜、無日曆到 13:40」
少了一道閘:index_engine._broadcast_loop:656 有日曆那條是
heal_window = now_t >= _WATCH_END and self._is_trading_day(self._today_fn())
—— 休市日一發都不打(該處註解自己寫「休市日則一發都不打」)。契約條寫得比 code 寬,日後有人照這句去查
「假日晚上為什麼沒自癒」會白查。

改「有日曆且當天是交易日 → 到午夜;無日曆 → 13:40」。stock_source.py:53 與 docs/next-time.md:59 的
「有日曆 → 13:25 起到午夜」是 #128 就有的同型漏字,順手三處一起改。
```

### Opus 原始 findings (first-pass, context-aware)

- **F-01**(reviewer 原編號 F-1,LOW [python-reviewer])`tests/helpers/frontend_source.py:1-3` —— docstring「唯一入口」vs `tests/test_stock_watchlist.py:269` 仍自算 `parents[1]` 讀 `constants.ts`。fix:該條改走 helper 或 docstring 降語。anchor:`"""後端測試讀**前端原始碼字面**的唯一入口(跨語言 parity 測試:river palette / AVG_SOURCES)。`。search-proof:`grep -rn "frontend" tests/ --include=*.py`(排除 helper 本身)→ 命中 test_stock_watchlist.py:269,未 import helper;change-spec §3 只點名 river palette / AVG_SOURCES,未把 constants.ts 列 non-goal
- **F-02**(reviewer 原編號 F-2,LOW [python-reviewer])`.claude/chore/pr-review-128-130-followups/verification.md:12-13` —— §1 寫「輸出參數蒐集」,HEAD `_parse_legs` 已於 `2bd63ccc` 改回傳 `_ParsedLegs`;§7 有記、§1 未回指。fix:§1 補回指句。anchor:`- `ee916937` fix:`_parse_legs(raw, bad_sparse)` 以輸出參數蒐集 `(key, 原值)`,`load_config` 過完 legs / base 兩道降級檢查`。search-proof:`copycat/corr_config.py:103` HEAD 為 `def _parse_legs(raw: object) -> _ParsedLegs | None:`;`git log` 顯示 `2bd63ccc` 在 `ee916937` 之後
- **F-03**(reviewer 原編號 F-3,LOW [python-reviewer])`CLAUDE.md:272-273`(4.6 re-anchor → :277)—— 新括號句「有日曆到午夜」與 `_broadcast_loop:655-658` 對不齊:calendar 分支 AND `_is_trading_day`,休市日不打。fix:改「有日曆且為交易日 → 到午夜」。anchor:`  的凍結點;分時自癒 09:00 起全程都在,`_WATCH_END` 後只是換成尾段判準接手 —— 有日曆到午夜、無日曆到 13:40)`。search-proof:`copycat/server/index_engine.py:655-658`;跨層 parity 另一半 `_INDEX_HEAL_END`(13:25)已核對同值
- **F-04**(reviewer 原編號 F-4,LOW [python-reviewer])commit 訊息(`1d2242f5` / `1f3fe386`)—— (a) `refactor: …` 無 scope,全庫 typed subject 唯一一筆,內容純註解應歸 `chore`;(b) `refactor(tests)` 含新增斷言(🟢 混 🔵),round 1 S-7 已 accepted。fix:純風格,零行為。anchor:`<none>`(最近符號 `tests/capital/test_client.py::test_profit_row_unknown_kind_skipped_keeps_previous_broker_avg`)。search-proof:`git log --pretty=%s \| grep -cE "^(feat\|fix\|chore\|refactor\|perf\|test): "` → 1;有 scope → 524

已逐條複核成立的 PR 自我宣稱(reviewer 核過,無 finding):(1) `pytest -q` 總數 3135 相符,但 reviewer 於台北 00:04–00:06 實跑得 `5 failed, 3127 passed, 3 skipped` —— 5 紅全在 diff 未觸及的 `tests/server/test_bars.py`,根因 `copycat/server/bars.py:510 hold = hi == yesterday and _now_time() < MIDNIGHT_BUFFER_END`(00:00–00:10 午夜緩衝窗吃真牆鐘;該檔部分測試 `monkeypatch bars._now_time`,這 5 條沒凍結),把 `bars._now_time` 固定 09:00 重跑 → `51 passed`;3 skipped = extras 未裝(`requires_tcpy` / discord)。**與本 PR 無關**,屬既有牆鐘相依測試;(2) mutation `_PNL_KIND_CODE` + `"9": "short"` → `1 failed, 402 passed`,紅的正是新斷言「種類標籤未知」;(3) `AVG_SOURCES` 注入 `"oi"` → `test_avg_source_parity_with_frontend` 1 failed;(4) 紅先行 2 failed —— 機械證明(`8e25d87a` 只動 tests、當時 `_parse_legs` 仍在迴圈內 `logger.warning`,新測試兩個 param 必紅);(5) `grep -rn "copycat.server" tests/live/` 僅剩註解字串一行;(6) `RAW_PNL_MARGIN` / `RAW_PNL_ROW` 與舊 `test_balance` / 舊 `test_client._PNL_3357` 程式比對逐 byte True、三列皆 30 欄;(7) 十筆 commit 紅先行順序成立、分類瑕疵見 F-04;(8) `ruff check` PASS / `pyright` 0。

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查。

### Codex 對 Opus 的複查結果（對稱化 4.2）

**Codex 複查 Opus 失敗 — 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(本機無 codex)。全部 CC finding 視同 INCONCLUSIVE,改由 4.3b 主 agent 逐條實查(結果在發現總覽「Opus 複查」欄與下方備註):

| Opus # | 原始 severity | 4.3b 判斷 | 備註(他軸為何漏 / 主 agent 實查) |
| --- | --- | --- | --- |
| F-01 | LOW | CONFIRMED | 主 agent `grep -n 'parents\[' tests/test_stock_watchlist.py` → :269 `Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "constants.ts"`;`grep -rn frontend_source tests` → 只有 test_models / test_corr_config 兩個 caller。lone finding 的合理解釋:round 1 Standards S-4 只看 diff 內兩條 parity 測試,沒 grep 全庫第三個讀者;主 agent 收修時也只改被點名的兩條。 |
| F-02 | LOW | CONFIRMED | 主 agent `grep -n "def _parse_legs" corr_config.py` → `:103 def _parse_legs(raw: object) -> _ParsedLegs \| None:`;verification.md:12 仍寫 `_parse_legs(raw, bad_sparse)`。lone 解釋:round 1 兩軸審的是 a58e37ee(§1 當時正確),收修 commit 2bd63ccc / 1e3dfcbf 只由主 agent 機械快篩,沒人回頭對 §1。 |
| F-03 | LOW | CONFIRMED | 主 agent `sed -n 653,658p index_engine.py` → `elif self._has_calendar: heal_window = now_t >= _WATCH_END and self._is_trading_day(self._today_fn())`;grep「有日曆 → 13:25 起到午夜 / 有日曆到午夜」→ stock_source.py:53、next-time.md:59(#128 既有)、CLAUDE.md:277(本 PR 新增)。lone 解釋:round 1 Spec P-2 修的是「窗從哪開始」,主 agent 改句時照 P-2 建議句抄,沒再讀一次 :656 的 AND。 |
| F-04 | LOW | CONFIRMED | 主 agent `git log --pretty=%s`:無 scope typed subject 1 筆(1d2242f5)、有 scope 524;1f3fe386 含 `assert any("種類標籤未知" …)` 新增斷言。round 1 S-7 已指出、accepted;本輪維持不重寫歷史 → 參考用 / no-op。 |

## Action Items

**Severity calibration**:6c(移除既有防護類)—— 本 PR 無移除防護 / guard 類改動(唯一行為改動是 WARNING 延後印,採用路徑仍印);6d-1 hedge cap:F-03「日後有人照這句判」是假設性後果 → Nice;6d-3 Must Fix 雙半條件:四條無一有 user-visible 重現路徑 + 阻擋發布,無 Must / Should;6d-2 由 4.3b 取代(四條全 CONFIRMED、各有 lone 解釋,零降級);未驗證前提閘:四條的 severity 都建立在第一手 file:line / git log 證據上,拿掉推論部分不降級;provenance cap N-A。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix（合併前必修）

- 無

### Should Fix（強烈建議）

- 無

### Nice to Have（可選優化）

- F-01 `tests/test_stock_watchlist.py:269` 改走 `read_frontend_source("lib/constants.ts")`,或 helper docstring 降為「共用入口」(`tests/helpers/frontend_source.py:1`)
- F-02 verification §1 補「收修後改 `_ParsedLegs` NamedTuple 回傳,見 §7」(`.claude/chore/pr-review-128-130-followups/verification.md:12`)
- F-03 CLAUDE.md:277「有日曆到午夜」→「有日曆且為交易日 → 到午夜」;`stock_source.py:53` / `next-time.md:59` 同句同改

### 參考用（任一軸驗證為 REFUTED 或 OUT_OF_SCOPE）

- F-04 commit 慣例瑕疵(`1d2242f5` 無 scope、`1f3fe386` 🟢 混 🔵):已 rebase merge 進 master、不重寫歷史;round 1 S-7 accepted 的同一件事,本輪只記錄。非 REFUTED / OUT_OF_SCOPE,因無可修 file:line 且處置為 no-op 而列此。

## 審查工具比較 (qualitative)

- CC 視角(python-reviewer):四條全 LOW,全部落在「敘述超出 / 落後 code」這一型 —— helper docstring 超出(F-01)、verification §1 落後收修(F-02)、契約條比 code 寬(F-03)、commit 分類(F-04)。唯一行為改動(WARNING 延後印)與八條自我宣稱逐條核對成立;reviewer 另以 runtime plugin 注入獨立複現兩發 mutation,並抓到 `test_bars` 午夜緩衝窗牆鐘相依(非本 PR)。與 round 1 in-flow two-axis 的差異:round 1 抓的是輸出參數 / helper 重複 / 章節標題被蓋;本輪抓的是那些收修之後文字沒跟上的第二層。
- Codex / Gemini:N-A。
- 4.3b:CONFIRMED 4 / PARTIAL 0 / 0 降級;四條皆有 lone 解釋(round 1 只看 diff 內兩條 / 收修 commit 未回頭對 §1 / 照建議句抄沒重讀 AND / S-7 已 accepted)。
- 對抗式第三軸增益:N-A。

## 沒做的部分（結案對帳）

- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(grep / sed / git log)。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 以 `py -3.14` 實跑;主 python 缺 jsonschema)。
- 真實環境:本 PR 無 UI / API 變更,prod 不需為此重啟;#128 F-01「重掛 snapshot 讓現價欄回來」仍是未實測推論,08-28 13:36 `/api/index/state` 核。
- 未驗證前提:reviewer 的「紅先行 2 failed」為機械證明未實跑(主 agent 於分支上實跑過:`2 failed, 20 deselected`,見 PR verification §1);F-03 的後果「日後有人白查」是推論。
- 順帶發現(非本 PR finding、建議入 next-time):`tests/server/test_bars.py` 5 條在台北 00:00–00:10 會因 `bars._now_time()` 吃真牆鐘而紅(`MIDNIGHT_BUFFER_END` 午夜緩衝),該檔其他測試已 `monkeypatch _now_time`、這 5 條沒凍結。
- Self-Verify:已執行,COMPLIANT(auditor 以 Read 讀取草稿檔本身,未讀其他產物)。
