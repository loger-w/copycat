# PR #200 Code Review 比較報告 · SHA 60137dae
**Report projection schema**: 1

**PR**: [loger-w/copycat#199](https://github.com/loger-w/copycat/pull/199) + [loger-w/copycat#200](https://github.com/loger-w/copycat/pull/200)(整體 review;標題編號取 range 頭 = #200 的 rebase merge commit)
**標題**: spec #192「訊號影子政策層」整體 review —— 掃單簇事件 + 四條政策 P / B-a / B-b / S 影子推播與 jsonl、族群 = 自選群組、停 CDP 穿越 / 爆量推播(PR #199 T1–T6)+ pr-199 review 收修(PR #200)
**作者**: loger-w(兩 PR 同人)
**分支**: `master` range `53d8f15c..60137dae`(= `mod/signal-shadow-policies` 16 筆 + `fix/pr-199-review-followups` 7 筆,皆 rebase merge、分支已刪)
**變更**: 47 檔案, +6523 / -183(23 commits)
**審查日期**: 2026-09-07
**PR 狀態**: 兩 PR 皆 MERGED(post-merge 整體 review,user 2026-09-07 拍板;findings 以收修 PR 處置,不阻擋任何出貨;prod 09-07 跑 `1e58a083` = #199 版,#200 未上線、行為無差)
**Review input basis**: source repo id `R_kgDOTsITBg` + source SHA `60137dae55d221513f0914b0161f33f4c88dc61b`(range 頭 = #200 mergeCommit,= origin/master);destination repo id `R_kgDOTsITBg` + destination SHA `53d8f15c8812c84138189600fb69749c78b0121e`(range 底 = #199 baseRefOid);`input_binding: verified`(review worktree HEAD 逐字等於 source SHA;destination 本地可解析且 `git log 53d8f15c..60137dae` 恰 23 筆)
**Review continuity**: `source_continuity=CURRENT`(產報告前 `git fetch origin master` 重抓,origin/master 仍 `60137dae`,零新 commit);`base_changed=false`(destination 是歷史 commit);`review_context_changed=false`
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用,沿 #188 / #190 / #199 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替(兩批 22 + 25 條並行,各自獨立 worktree,非跨軸證據)**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewers=python-reviewer ×3 chunk(C1 / C3a / C3b)+ typescript-reviewer ×1(C2)+ code-reviewer ×1(C4 文件契約)(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model);domain reviewer=code-reviewer ×1(D1 spec 語意對帳;requested=opus / observed=UNAVAILABLE);內部複查=code-reviewer ×2(V1 / V2;requested=opus / observed=UNAVAILABLE);security-reviewer N-A(無 trigger 面);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派,gate SKIPPED);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=47 → covered 29 / no-issues 16 / skipped 2 / **missed 0**(chunked: 是,5 chunk C1 8 / C2 11 / C3a 6 / C3b 6 / C4 16;14 source 檔 / 6706 diff 行超過 800 行門檻;chunk map 見「變更概要」;D1 domain reviewer 不計入 coverage)
**定位 (ENH-B)**: anchored exact 45 / ambiguous 3 / **FAILED 0**(47 條 anchor 逐字在 review worktree grep:45 條唯一命中(13 條校正了 reviewer 自報行號);3 條多重命中(C1-F2 / C4-F7 / D1-F2)皆含或取最近自報行)
**React-doctor (2.97)**: 未引入新問題(`--scope changed --base 53d8f15c --json`:newCount 1 / fixedCount 1 / baseTotalCount 2,changedFileCount 11 —— 那條「new」與「fixed」是同一個 `no-high-complexity-react-function` `SignalRulesDialog` 函式行號位移(:160)被重新識別,base 即存在;與 #199 review 同一結果)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_SPEC_FILE_IN_REPO)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 review worktree 對 `53d8f15c` 執行、exit 0、零輸出)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**Codex preset**: N-A(user 停用 Codex,無 preset)
**Gemini 軸**: N-A(user 停用)
**Provenance (2.55)**: N-A(range 底 = master 歷史 commit,無 inherited 檔)
**審查軸狀態**: primary(python-reviewer ×3 + typescript-reviewer ×1 + code-reviewer ×1,5 chunk)PASS(42 findings + 47/47 per-file accounting)/ domain D1(code-reviewer,spec 語意對帳)PASS(5 findings;32 story 30 符合 2 部分 / W1–W12 12 PASS)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 使用者輸入解析 / 憑證 env)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(47/47 verdict 齊:CONFIRMED 35 / PARTIAL 11 / REFUTED 1;兩批 ID 集合各精確相等、每列四欄齊;17 個突變體序列重跑 16 存活 1 被 golden 殺)
**worktree**: `C:/side-project/copycat/.worktrees/review-range-192`(primary;內部複查另用 `-v1` / `-v2` 兩棵同 SHA)
**worktree HEAD**: `60137dae55d221513f0914b0161f33f4c88dc61b`

**Report generation**: sha256:cdc68d2d9a89139ba4a10ffd725a9c34365b52068e44ecbcd026289b54f14ea0

---

## Spec 依據

- Spec = GitHub issue **#192**「訊號影子政策層」(Problem Statement / Solution / 32 user stories / Implementation Decisions / Testing Decisions 四條 seams / Out of Scope / 白名單 W1–W12 / Backward compat / 決策來源 / 真環境驗收)+ tickets #193–#198(T1–T6 AC)。repo 內無 normative 檔(不在 F 內、不是 `.md` 檔)。
- ⚠️ **spec 作者 = PR 作者**(issue #192 與兩 PR 皆 loger-w;out-of-scope / 白名單判定以此 spec 為據時注意利益重疊;本輪 D1 軸把 32 條 story 逐條對 code 驗,不是只信 spec 字面)。
- 研究 SoT(spec 決策來源,repo 外):`C:\Users\USER\Documents\copycat-trading-review\HANDOFF-2026-09-06-signal-research.md` §8(拍板表 / §8.2 數字 / §8.3 實作要求)、`scripts/combo_events.py`(掃單簇與 `group_feats` 定義)、`scripts/combo_wlpolicy.py`(§8.2 表產生腳本)。D1 / V1 對這些做了逐字與逐格對帳(見 F-01、F-32 與「D1 摘要」)。
- 前兩輪已 review 產物(本輪不重報、只複查收修):`docs/superpowers/specs/pr-199-review.md` F-01..F-50、`.claude/mod/signal-shadow-policies/code-review-round-1.json`(19 條)、`.claude/bug/pr-199-review-followups/code-review-round-1.json`(11 條)。本輪 10 條屬「複查收修」(標題含「複查」;結果:收修全部正確落地,6 條為「修了一半 / 零回歸保護」)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED` / `dispatch=NOT_APPLICABLE` / `dispatch_count=0` / `reason_code=C4_NO_SPEC_FILE_IN_REPO` / `requested_model=opus` / `observed_model=UNAVAILABLE` / `effort=xhigh` / runtime tool calls N-A(未派)。0 clauses / 0 findings / 0 observations / 0 invalidated。spec 語意對帳改由 **D1 一般 domain reviewer** 執行(不是 C4 pipeline,無 reducer receipt;findings 併入 CC 主軸欄,不另立 axis 欄)。

## 變更概要

Range `53d8f15c..60137dae` 47 檔(source 14 / tests・fixtures 13 / frontend tests 5 / 文件・流程產物 15);chunk 欄 = Step 2.95 分派(C1 後端 source / C2 前端 / C3a 後端測試前半 / C3b 後端測試後半 / C4 文件契約與產物)。Provenance N-A。

| 檔案 | 類型 | +/− | chunk | 說明 |
|---|---|---|---|---|
| `.claude/bug/pr-199-review-followups/code-review-round-1.json` | 新增 | +22/−0 | C4 | 流程產物 / 取證 |
| `.claude/bug/pr-199-review-followups/verification.md` | 新增 | +60/−0 | C4 | 流程產物 / 取證 |
| `.claude/mod/signal-shadow-policies/code-review-round-1.json` | 新增 | +29/−0 | C4 | 流程產物 / 取證 |
| `.claude/mod/signal-shadow-policies/evidence/fake_server.py` | 新增 | +97/−0 | C4 | 流程產物 / 取證 |
| `.claude/mod/signal-shadow-policies/evidence/migration-dry-run.txt` | 新增 | +16/−0 | C4 | 流程產物 / 取證 |
| `.claude/mod/signal-shadow-policies/evidence/rules-dialog-list.png` | 二進位 | +-/−- | C4 | 流程產物 / 取證 |
| `.claude/mod/signal-shadow-policies/evidence/rules-dialog-sweep-edit.png` | 二進位 | +-/−- | C4 | 流程產物 / 取證 |
| `.claude/mod/signal-shadow-policies/evidence/sidecar-rules-curl.txt` | 新增 | +7/−0 | C4 | 流程產物 / 取證 |
| `.claude/mod/signal-shadow-policies/evidence/sidecar-startup-log.txt` | 新增 | +17/−0 | C4 | 流程產物 / 取證 |
| `.claude/mod/signal-shadow-policies/evidence/vite.sidecar.config.ts` | 新增 | +20/−0 | C4 | 流程產物 / 取證 |
| `.claude/mod/signal-shadow-policies/verification.md` | 新增 | +139/−0 | C4 | 流程產物 / 取證 |
| `.claude/skills/tc4-market-facts/SKILL.md` | 修改 | +8/−0 | C4 | 同毫秒群 = 掃單事實 |
| `CLAUDE.md` | 修改 | +37/−0 | C4 | §4 五條契約 + §1 影子期判準列 |
| `CONTEXT.md` | 修改 | +45/−0 | C4 | 十個術語(掃單 / 掃單簇 / 族群 / 同伴 / 鎖過 / 政策 …) |
| `copycat/fileio.py` | 修改 | +10/−1 | C1 | 新增 atomic_write_bytes(回填整檔覆寫用) |
| `copycat/live/signal_state.py` | 修改 | +160/−8 | C1 | 掃單簇偵測器 _eval_sweep(同毫秒群 / 簇窗 / 60 s 漲幅 / 冷卻)+ SignalEvent.detail |
| `copycat/server/app.py` | 修改 | +17/−0 | C1 | 接線 peers_fn(engine.policy_quotes)與 outcome_bars(bars_range tf=D) |
| `copycat/server/signal_hub.py` | 修改 | +458/−4 | C1 | 政策層 _emit_policies / 四行卡 format_policy_group_text / T+1 T+2 回填 worker / notify 欄 |
| `copycat/server/signal_policy.py` | 新增 | +193/−0 | C1 | 新檔:族群解析 resolve_groups、evaluate_policies(P / B-a / B-b / S)、tod 五桶 |
| `copycat/server/stock_engine.py` | 修改 | +38/−0 | C1 | 新增 policy_quotes 行情快照(touched_upper / locked_up) |
| `copycat/signal_rules.py` | 修改 | +154/−39 | C1 | sweep_cluster 第六 kind、PARAM_SPECS 五鍵、v3→v4 遷移(種子 + 翻旗)、回退手順 |
| `copycat/signals_config.py` | 修改 | +17/−1 | C1 | sweep_* 六鍵 + policy_* 六鍵(tuple 欄 policy_exclude_groups) |
| `docs/superpowers/specs/pr-199-review.audit.md` | 新增 | +1187/−0 | C4 | review 報告(#199) |
| `docs/superpowers/specs/pr-199-review.md` | 新增 | +587/−0 | C4 | review 報告(#199) |
| `frontend/src/components/stock/SignalRail.test.tsx` | 新增 | +122/−0 | C2 | 測試 / 治具 |
| `frontend/src/components/stock/SignalRail.tsx` | 修改 | +86/−36 | C2 | 前端 |
| `frontend/src/components/stock/SignalRulesDialog.test.tsx` | 修改 | +52/−2 | C2 | 測試 / 治具 |
| `frontend/src/components/stock/SignalRulesDialog.tsx` | 修改 | +9/−3 | C2 | 前端 |
| `frontend/src/hooks/useSignalAlerts.test.tsx` | 新增 | +58/−0 | C2 | 測試 / 治具 |
| `frontend/src/hooks/useSignalAlerts.ts` | 修改 | +33/−8 | C2 | 前端 |
| `frontend/src/hooks/useSignalRules.ts` | 新增 | +3/−0 | C2 | 前端 |
| `frontend/src/lib/signal-model.test.ts` | 新增 | +140/−0 | C2 | 測試 / 治具 |
| `frontend/src/lib/signal-model.ts` | 修改 | +148/−5 | C2 | 前端 |
| `frontend/src/lib/signal-param-parity.test.ts` | 修改 | +10/−1 | C2 | 測試 / 治具 |
| `frontend/src/lib/signal-params.ts` | 新增 | +9/−0 | C2 | 前端 |
| `tests/fixtures/record_sweep_cluster_golden.py` | 新增 | +250/−0 | C3a | 測試 / 治具 |
| `tests/fixtures/signal_param_specs.json` | 修改 | +9/−2 | C3a | 測試 / 治具 |
| `tests/fixtures/sweep_cluster_golden.json` | 新增 | +1/−0 | C3a | 測試 / 治具 |
| `tests/live/test_signal_state.py` | 修改 | +225/−2 | C3a | 測試 / 治具 |
| `tests/server/test_signal_hub.py` | 修改 | +335/−19 | C3a | 測試 / 治具 |
| `tests/server/test_signal_outcome.py` | 新增 | +472/−0 | C3a | 測試 / 治具 |
| `tests/server/test_signal_policy.py` | 新增 | +785/−0 | C3b | 測試 / 治具 |
| `tests/server/test_signal_routes.py` | 修改 | +5/−14 | C3b | 測試 / 治具 |
| `tests/server/test_stock_engine.py` | 修改 | +131/−2 | C3b | 測試 / 治具 |
| `tests/server/test_stock_routes.py` | 新增 | +4/−0 | C3b | 測試 / 治具 |
| `tests/test_signal_rules.py` | 修改 | +279/−36 | C3b | 測試 / 治具 |
| `tests/test_signals_config.py` | 新增 | +39/−0 | C3b | 測試 / 治具 |

## 發現總覽

| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `copycat/server/signal_hub.py:1077` 研究 §8.2 基準表的「12:30 前」= `combo_wlpolicy.py:41` `df.tod < 1230`,`tod` 是字串桶被 pandas 讀成 int 恆真 → 表含 65 筆 late=1;線上 `late` 本身正確(D1-F1) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V1 逐格重算 events.csv:sweepc 865、tod ∈ {900…1200} 全 <1230、late=1 65 筆;「排除 ALL IN」列 tod<1230 = 無濾網 = 36/+5,497/22%,late==0 → 35/+5,784/23%;其他列同向修正、無拍板翻面 | Nice to Have | `ask-user` | 改的是研究目錄的表或腳本,不在 repo;影子期對帳前先做 |
| F-02 | `tests/server/test_signal_outcome.py:263` `cutoff = min(hub 日別, 牆鐘日)` 只釘 hub 超前那半;突變 `cutoff = self.today` 全綠;hub 落後牆鐘(空自選 / 零推播停在昨日)是常態,昨日檔正是 `_append_jsonl` 還在寫的檔(C3a-F1) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑 M2 全量 467 passed / 0 failed;CLAUDE.md 明載 trade_date 空自選 / 零推播停在昨日,`_append_jsonl:983/1006` 用同一顆 `_trade_date_fn` → 13:40 `atomic_write_bytes:1332` 會整檔覆寫仍在 append 的檔 | Nice to Have | `auto-fix` | 補一案鏡像既有案(hub 日別 = 昨日、牆鐘 = 今日)即可 |
| F-03 | `copycat/server/signal_policy.py:109` `policy_exclude_groups` 逐字比對、零命中零訊號;prod 無 `configs/signals.json`,user 在自選把「ALL IN」改名即失效 → ALL IN 四檔互不相干的股票變同伴、污染影子期(C1-F5) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V1 以 events.csv 原地驗 ALL IN 當族群 n=10 / −1,471(事件級 16 / −3,605)逐字符 §8.2;緩解 = 政策列自帶 `groups` / `peers`、卡面第三行印族群(非全盲);spec story 14 把改名→改設定寫成 user 流程 → 結論是載入期補一則 WARNING | Nice to Have | `auto-fix` | 載入期加一則「排除組名零命中」WARNING,幾行、局部 |
| F-04 | `tests/server/test_signal_hub.py:2291` 簇窗 `[s−30, s]` 與回看 `≤ s−60` 兩個閉區間界零樣本(合成案用 31 s / 窗前無成交,golden 也無);突變 `<`→`<=`、`<=`→`<` 皆全綠(C3a-F2) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑 M3 / M4 各全量 467 passed(含 golden 三案);真資料 20260907 的 75 列 sweep/policy 時刻鍵 100% `.000`(全檔 479 只 2 列非 .000)→ 恰差 30 / 60 s 是常態不是邊角 | Nice to Have | `auto-fix` | 兩條合成案(掃單相差恰 30 s;回看基準恰在 s−60) |
| F-05 | `tests/live/test_signal_state.py:700` `TestSessionGates` 四案 `_ALL` 不含 sweep_cluster;突變把兩道早退改成掃單簇照跑全綠;`_eval_sweep` 已刻意上移到首 tick gate 前,再上一格無測試紅;收盤撮合同秒大群可造假簇(C3a-F3) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑 M6 全量 467 passed;golden 殺不掉因 record 腳本 :65-67 自己加了 [09:00, 13:30) gate;F-25 收修紀錄「三案各只掉 13:30:00.000 收盤撮合一筆」= 收盤同秒大群實證 | Nice to Have | `auto-fix` | TestSessionGates 補一案 `_SWEEP` 盤外兩群 → [] + 一案舊日 trade_date |
| F-06 | `tests/server/test_signal_policy.py:179` 複查 round-1 std F-01(HIGH):`chg = round(…, 2)` 拿掉後全綠;既有案 chg 是整齊值或走 `pytest.approx`,兩把尺的差落在測試看不到的地方(C3b-F3) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑刪 round 全量 467 passed;既有 ref=50_000 → 0.8 兩邊一樣;實算 ref=48_933 → 2.997977,round 後 3.0(leader True)、不 round 2.998(False)→ 一案可釘 `self.chg_pct` 與 B-a/B-b | Nice to Have | `auto-fix` | 一案 ref=48_933 + peer 3.0,斷 chg_pct [3.0, 3.0] 與 [B-a, B-b](補案已實跑紅綠) |
| F-07 | `tests/server/test_signal_policy.py:265` `under_cap = chg < 6` 只有 +3.92 / +7.23 兩個遠離界的案;突變 `<=` 全綠;chg 已 round 2,恰 6.0 是每天都可能出現的整數格(C3b-F1) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑 `<=` 全量 467 passed;既有 ref=47_000 → 7.23 離界 1.23;實算 ref=47_547 → 6.000379 → round 6.0,`<` False / `<=` True → 補案可殺 | Nice to Have | `auto-fix` | 一案 ref=47_547、groups=[_MEM, _SCREEN]、peer 1.0 → [](補案已實跑紅綠) |
| F-08 | `tests/server/test_signal_policy.py:245` `leader = chg >= peer_max` 只測 3.92 vs 3.0;突變 `>` 全綠;兩邊都 round 2 撞同格是常態;研究 `_leader` 含平手(C3b-F2) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑 `>` 全量 467 passed;實算 ref=48_932 → 3.000082 → 3.0 與 peer 3.0 平手 → 補案可殺;研究 `group_feats` `_leader = int(self_chg >= mx)` 含平手 | Nice to Have | `auto-fix` | 一案 ref=48_932 + peer 3.0 → [B-a, B-b](補案已實跑紅綠) |
| F-09 | `tests/server/test_stock_engine.py:1439` `locked_up_flag = price == upper and _best_limit_price(asks) is None`;第二筆同時改價又改賣側,只靠 `price != upper` 成立;突變去掉賣側半邊全綠;`self/peers.locked_up` 是對帳快照欄(C3b-F6) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑全量 467 passed;`locked_up` 不進任何政策條件(`evaluate_policies` 只讀 `touched_upper`),純 jsonl 快照欄(story 16)→ 對帳錯非漏發錯 | Nice to Have | `auto-fix` | 第三筆 price=2550 ask=2550 → locked_up False(補案已實跑紅綠) |
| F-10 | `copycat/server/signal_hub.py:1224` `_policy_outcome_worker` 無條件先跑一趟;`_req` 全域 `api.lock` 序列化;開機當下與 `on_watchlist` 排進的 150 檔基準 job 交錯;回填零時效性(C1-F2) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V1 核 tc4.py:547-562 `_req` 每發都 `api.lock.acquire`、`_collect_history` 同鎖;量測 prod 五日檔待補 = 20260907 29 列 / 15 相異 code → 首跑 15 次 DK ≈ 5–18 s(stock_source.py:752 probe 0.02–0.98 s)≈ 150 檔基準 sweep 10% 延後;風險窗 = 接近 09:00 才啟動 | Nice to Have | `ask-user` | 延後 startup 那趟 / 只在 13:40 後啟動才立即跑,是排程取捨 |
| F-11 | `copycat/server/signal_hub.py:1093` 研究 `nosig.py:52` `own` 無 kind 白名單(同檔 :53 `others` 有)→ `has_sig` / `any_sig_day` 自 09-07 起把 sweep_cluster / policy 算進去;glob 整目錄 → 同一張表 09-07 前後兩把尺(D1-F2) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V1 逐行確認 :52 / :53 兩把尺、:13 glob 整目錄;現況尚未爆(fills.json 最後 2026/09/03),影子期 fills 進來才發作;CLAUDE.md §4「不新增列型」對不做白名單的讀者無保護力 | Nice to Have | `ask-user` | 改的是研究目錄腳本 + CLAUDE.md 契約措辭;腳本歸 user 管 |
| F-12 | `.claude/skills/tc4-market-facts/SKILL.md:75` skill 新 bullet 稱「鎖停日 ask 市價佇列 0、`derive_side` 判 outer」;但 `ask_milli` 經 `_best_limit_price` 0→None、鎖漲停 `derive_side` 判 neutral(同 skill :93 自證);`tick.side=="outer"` 與 `ask>0 and price>=ask` 在 prod 等價;真正理由 = 與研究 `find_sweeps` 逐字對齊(C4-F2) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V1 核 stock_models.py:149-151 / :221-222 / 歷史 :256-258 全把 0 歸 None;`derive_side:103-105` outer 分支逐字 = `_eval_sweep:725` 去掉死條件 `ask > 0`;研究 `pull_ticks.py:63` 保留原始 Ask=0 才需要 `ask[i] > 0` | Nice to Have | `auto-fix` | 改一句括號內文,把真正理由寫進去 |
| F-13 | `frontend/src/components/stock/SignalRail.test.tsx:583` `SignalRail.tsx:185` `every(!shouldNotify)` 是唯一實作點;三案各自單元素成組,every/some 等價;突變 some 全綠;prod 政策列 = 政策 notify=true + raw 掃單簇 notify=false 混合組(C2-F2) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑 every→some 主 tree 全量 2381 passed;真資料 25 個政策組中 15 組混合、cdp_cross 155 全 quiet 與 surge 混組更普遍 → some 讓多數列變淡色,story 9 的降噪反轉 | Nice to Have | `auto-fix` | 既有「同 tick 政策 + raw」案補一行 not.toContain("opacity-50") |
| F-14 | `frontend/src/lib/signal-model.ts:290` `policyContextText` 對 `groups: []` 的 S 列仍走 `peerPhrase`;`policyTitle`(hover)與 Discord 第三行都有無族群分支,只有畫面那行沒有;真資料 S 22 列中 16 無族群、9 列 notify=true(C2-F1) | MEDIUM | CONFIRMED(校正 LOW;原 MEDIUM):V2 真資料實查同數;緩解 = 同列 S chip + hover 全文正確 + `groups=[]` 已落 jsonl → 事後重算不受害;code 合規 spec 字面 | Nice to Have | `ask-user` | 無族群 S 列第三行改印什麼是文案拍板 |
| F-15 | `frontend/src/hooks/useSignalAlerts.test.tsx:718` `useSignalAlerts.ts:234` `if (firstPolicy) beepFor(true)`(併入既有 toast 的雙嗶)刪掉全綠;既有兩案都走新開 toast 或 firstPolicy=false(C2-F3) | MEDIUM | CONFIRMED(校正 LOW;原 MEDIUM):V2 序列重跑刪行全量 2381 passed;真資料 25 政策組中「有 notify=true 非政策同伴」= 0 → 現況零踏到;要踏到需 user 開掃單簇通知或同秒撞 surge | Nice to Have | `auto-fix` | 一案:先 emit notify=true 的 raw 掃單簇、再 emit 政策列 → toasts 1、oscillators 3 |
| F-16 | `frontend/src/hooks/useSignalAlerts.test.tsx:710` `SECOND_BEEP_OFFSET_S` 改 0 全綠;fake `createOscillator().start` 丟參數,沒人讀得到起始時刻(C2-F4) | LOW | CONFIRMED(校正 LOW;原 LOW):V2 序列重跑 offset→0 全量 2381 passed;根因如述 | Nice to Have | `auto-fix` | fake 記 starts.push(t),一案斷兩聲起點相差 > 0 |
| F-17 | `frontend/src/lib/signal-model.ts:104` 後端 `_kind_text` pct=0 / None → `掃單簇 +0.00%`;前端 pct=0 → `掃單簇 0.00%`、null → `掃單簇`;`up_pct` 值域下限 0 合法可達;F-11 否決理由只講小數位沒講正負號(C2-F5) | LOW | CONFIRMED(校正 LOW;原 LOW):V2 兩邊實測(後端 .venv 直跑、前端一次性 probe)結果如述;裁定 C4 契約 2 的 PASS 只在預設組態成立,`up_pct=0` 時 session 前 60 s 窗前無成交會產 `up_pct=0.0`;兩軸相容 | Nice to Have | `auto-fix` | fmtPct 加 signedZero 或 kindLabel 改走與後端同式 |
| F-18 | `frontend/src/lib/signal-model.ts:307` `policyTitle` 首段是整組 tags、尾段 `when` 取 anchor 單列的 `first_of_day`;計數是 per (檔, 政策),P 與 S 可一真一假;真資料 4 組同 tick 目前一致 → latent(C2-F6) | LOW | CONFIRMED(校正 LOW;原 LOW):V2 真資料四組(4979 / 6213 / 3105×2)`first_of_day` 皆一致;分岔路徑存在(S 母體寬、早盤先單獨命中一次後再與 P 同 tick) | Nice to Have | `auto-fix` | when 段改 per-tag 或只在單政策時印 |
| F-19 | `frontend/src/lib/signal-model.ts:283` round-1 S-02 只把 `peers_up` 換成 `??`,`peer_touched` 仍 `=== undefined`(null → 印「無」);`policyTitle:299-301` `=== null ? "-"` 是 dead(`pct1` 已處理)(C2-F7) | LOW | PARTIAL(校正 LOW;原 LOW):V2 核後端 `peer_touched` 恆 bool(signal_policy.py:87 / hub :1119)、`peers_up` 恆 int → null 不可達;dead 三元屬實;純一致性 | Nice to Have | `auto-fix` | 兩行:`peer_touched ?? null` 統一判 null;peer 迴圈直接 pct1 |
| F-20 | `frontend/src/components/stock/SignalRulesDialog.tsx:76` 舊 dist `PARAM_FIELDS` 只有五 kind,`toForm` 對後端種子「掃單簇」列 `for…of undefined` 拋 TypeError(onClick 內,零 ErrorBoundary → 點了沒反應);spec 只寫訊號列「印英文代號、不炸」(C2-F9) | LOW | CONFIRMED(校正 LOW;原 LOW):V2 核 `PARAM_FIELDS: Record<RuleKind,…>` 型別 total map、runtime 新 kind = undefined;`ruleSummary:96-116` 有 fallback、`toForm` 無;下一次加 kind 原樣重演 | Nice to Have | `ask-user` | 改文件(補「規則視窗需同版」)或改 code 加退路,二選一 |
| F-21 | `frontend/src/lib/signal-model.test.ts:5` `groupPolicyAnchor` export 但測試檔沒 import;突變改取末筆全綠;唯一可觀察分岔 = C2-F6 的 first_of_day(C2-F10) | LOW | PARTIAL(校正 LOW;原 LOW):V2 序列重跑取末筆全量 2381 passed;同事件各政策列除 policy/id/touch_count/first_of_day/notify 外欄位相同 → 第三行輸出逐字相同,差異只在 C2-F6 hover | Nice to Have | `auto-fix` | 一案兩則政策列 first_of_day 一真一假,斷回先到那則(順帶把 C2-F6 釘成紅先行) |
| F-22 | `copycat/server/signal_hub.py:715` `self._groups` 空 = P/B/S 全不評(first-pass 寫「S 只在篩選成員活」有誤:`screen_member` 也由 `_groups` 產生);失敗時只留一行「同群摘要沿用上一份」,盤後 grep 零政策列的人連不到這行(C1-F1) | MEDIUM | PARTIAL(校正 LOW;原 MEDIUM):V1 核 `app.py:854` `load_watchlist` 在 `on_watchlist` 之前求值、不在 hub try 內 → 壞檔先在 `_boot` 大聲停用整顆 hub;後續 `on_watchlist` 失敗只沿用舊值;缺檔回空 dict 不拋;成立只剩 log / docstring 漏族群消費者(與 C1-F8 同根) | Nice to Have | `auto-fix` | log 文案點名兩個消費者(與 C1-F8 一起改) |
| F-23 | `copycat/server/app.py:841` `groups_fn` 現在是族群判定唯一來源,漏接 = 三條政策整段無資料;註解卻說失效很輕、只靠接線測試把關;`_refresh_groups` docstring 同病(C1-F8) | LOW | CONFIRMED(校正 LOW;原 LOW):V1 核 app.py:839-842 逐字仍如此、`signal_hub.py:704-708` 同;與 C1-F1 同根因,收修一起改 | Nice to Have | `auto-fix` | 兩處註解各補一句政策層的失效樣態 |
| F-24 | `copycat/server/signal_hub.py:1254` 同函式另外兩條出口都有 log(:1267 零列 / :1335 彙總),只有目錄不存在這條靜默 return;13:40 判準那行不會出現(C1-F3) | LOW | CONFIRMED(校正 LOW;原 LOW):V1 核 prod 目錄已有 15 個日檔恆在,只全新安裝 / 換 data_dir 第一天可達 | Nice to Have | `auto-fix` | 換成一行 INFO,與 :1267 同款 |
| F-25 | `copycat/server/signal_hub.py:1055` round-1 std F-09 收修後第二次起零痕跡;降級 = `quotes={}` → P/B-a/B-b 全不評只剩 S;hub 已有 `dropped_jsonl` + `_DROP_LOG_EVERY` 節流計數慣例(C1-F4) | LOW | CONFIRMED(校正 LOW;原 LOW):V1 核旗標只 `on_rollover:667` 復位;`peers_fn` = `engine.policy_quotes` 純記憶體讀,拋例外等於已有別的 bug → 觸發機率低 | Nice to Have | `auto-fix` | 旗標換計數器 + 每 N 筆一行 WARNING 帶總數 |
| F-26 | `copycat/live/signal_state.py:713` `secs = mono`(牆鐘,1.78e9)混入自午夜秒數(3e4)的 deque;:744 只從左剪,毒值恆不小於 window_start → n30 變當日累計掃單數;docstring 觸發條件「空字串」寫錯(:308 已走時鐘)(C1-F6) | LOW | PARTIAL(校正 LOW;原 LOW):V1 探針實跑(tick.time="bogus")deque 長度 2→3→4 永不修剪,後果比 first-pass「min_sweeps 降 1」更重(簇窗整個失效);prod 不可達(`_taipei_time:89-95` 恆 HH:MM:SS.fff);docstring 確寫錯 | Nice to Have | `auto-fix` | `if secs is None: return []` + 修 docstring 觸發條件 |
| F-27 | `copycat/server/stock_engine.py:775` F-11 收修後 hub 恆傳 list;`None` 預設是 Speculative Generality,且扭曲測試方向(:1395 唯一傳清單)(C1-F7) | LOW | PARTIAL(校正 LOW;原 LOW):V1 核 10:1 比例正確,但 :776-798 per-code 組裝兩路共用,None 分支獨有只名單來源 → 「prod 分支只 1 案」在覆蓋意義上不成立;`quotes()` 是 `codes=None` 慣例來源 | Nice to Have | `auto-fix` | codes 改必填,呼叫端與測試各改一行 |
| F-28 | `copycat/signals_config.py:75` 六個 `policy_*` 鍵只有兩個 HH:MM:SS 有驗證;`policy_exclude_groups` 型別錯 = 裸 AssertionError、元素非 str 靜默;`policy_outcome_days ≤ 0` → `dated[:0]` 恆空、每趟印「本趟零列」(C1-F9) | LOW | PARTIAL(校正 LOW;原 LOW):V1 裸 assert 半 REFUTED(`configio.py:30` 四支設定共用 loader,strategy / backtest / fade 三個 tuple 鍵長期未爆);元素非 str 半 = C1-F5 同後果;`policy_outcome_days ≤ 0` 半 CONFIRMED(:1265 → :1267 把設定錯講成資料狀態);prod 無 signals.json 全走預設 | Nice to Have | `auto-fix` | `policy_outcome_days >= 1` 放進 SignalHub.__init__ 既有驗證迴圈(F-06 開好位置) |
| F-29 | `copycat/signal_rules.py:451` `_append_seed` 兩條跳過分支後果相同,`skip_note` 只接撞名(:448)不接滿載(:451);`test_signal_rules.py:945` 斷的正是缺後果那版字串(C1-F10 ≡ C3b-F8) | LOW | CONFIRMED(校正 LOW;原 LOW):V1 突變 :451 接 skip_note → `-k seed_skipped` 仍 4 passed = 訊息內容零釘;prod 規則檔 v1 4 條 → v4 7 條,距 30 遠 | Nice to Have | `auto-fix` | 一行接 skip_note + 測試斷言改含後果整句 |
| F-30 | `copycat/signal_rules.py:513` `_migrate_v3` 翻旗是版本觸發(`load_rules` 只看 `version != 4`);照手順退 v3 後任何一次升回都再翻一次(C1-F11) | LOW | PARTIAL(校正 LOW;原 LOW):V1 核 :471-472 已寫「翻旗只認 v3 之前的檔」,讀者推一步即得;行為本身是遷移正確語意;成立只剩手順段沒把後果講完 | Nice to Have | `auto-fix` | 回退段補一句 |
| F-31 | `copycat/server/signal_hub.py:1315` 研究「放到尾盤 B」出場鏈吃 13:20 價 vs 漲停價;政策列有 t1/t2 四欄與 `to_limit_pct`(可還原漲停價),沒有事件日 13:20 價 / 收盤 / 當日高 → §8.2「每筆」「鎖死」兩欄仍要另抓日 K(D1-F3) | LOW | PARTIAL(校正 LOW;原 LOW):V1 核 spec Out of Scope 明寫週對帳腳本留研究目錄,研究目錄已有 daily_all / daily_sep / kbar_* 且 `nosig.py:22-31` 已用日收盤算鎖板;T+1/T+2 open(唯一事後拿不到的)確實補了;成立只剩文件補一句 | Nice to Have | `ask-user` | (a) 文件補句 或 (b) worker 順手補事件日 bar close/high 兩欄,二選一 |
| F-32 | `copycat/server/signal_hub.py:1059` spec「已知刻意差異」只列鎖過閘 / 即時判兩條;線上 chg 用當筆價,研究 `frompc` 用下一筆 +1 檔進場價;865 事件 12 筆(1.4%)在 6% 界翻面;另兩條未落檔差異 = 同伴 chg 10 s 格點 vs 即時、多組留最後一組 vs 聯集(D1-F4) | LOW | CONFIRMED(校正 LOW;原 LOW):V1 重現 865 / 12 筆(1.39%,逐筆清單)、絕對差 p90 0.375 pt;spec 明文「自己的價…取當筆 state」→ 與 C1 面 2「不構成實作 finding」相容,兩軸都對;純文件缺口 | Nice to Have | `auto-fix` | signal_policy.py 模組 docstring 補三條差異 |
| F-33 | `CONTEXT.md:98` CONTEXT.md:98 漏括號;`signals_config.py:49` / `signal_state.py:698` 註解與 :735 實作都有括號(D1-F5 ≡ C4-F3) | LOW | CONFIRMED(校正 LOW;原 LOW):V1 核三處有括號、只 glossary 漏;D1 與 C4 各自獨立抓到同一行(強佐證) | Nice to Have | `auto-fix` | 補一對括號 |
| F-34 | `CONTEXT.md:108` `_group_suffix:735` 零排除;盤前篩選 38 檔是最大組,命中率遠高於 ALL IN 8 檔;glossary 只點名 ALL IN 讓人推論同群摘要有扣盤前篩選(C4-F4) | LOW | CONFIRMED(校正 LOW;原 LOW):V1 核 `_group_suffix` 逐字零排除 | Nice to Have | `auto-fix` | 一句改「盤前篩選 / ALL IN 都不扣」 |
| F-35 | `CLAUDE.md:60` CLAUDE.md §0 server/ 表無 `signal_policy`,live/ 行 kind 集合未列掃單簇;§4 五條契約以 `signal_policy.py::resolve_groups` 為產生點(C4-F5) | LOW | CONFIRMED(校正 LOW;原 LOW):V1 核兩節不一致;#198 AC 不含 §0 | Nice to Have | `auto-fix` | :60 補「掃單簇」+ server/ 表補一行 |
| F-36 | `.claude/mod/signal-shadow-policies/verification.md:23` mod 版 15 + followups 版 6 個 sha 存在但不在 60137dae 祖先鏈(rebase merge 前分支 commit,dangling);落地 sha 1:1 對得上但無映射記錄(C4-F1) | MEDIUM | CONFIRMED(校正 LOW;原 MEDIUM):V1 抽驗 5 sha 存在 / NOT_ANCESTOR;subject 1:1 唯一,`git log --grep` 可對回(c331b33d→1c707137 等),復原成本近零 | Nice to Have | `auto-fix` | 表頭加 merged sha 欄或段首一句映射說明 |
| F-37 | `.claude/mod/signal-shadow-policies/evidence/sidecar-rules-curl.txt:1` `sidecar-rules-curl.txt` 是 print 格式(`notify=` 非 wire 欄 `notify_discord`),verification.md:59 記成「側車 GET 同七條」;`rules-dialog-sweep-edit.png` select 收合、min/max 是 HTML 屬性(C4-F6) | LOW | CONFIRMED(校正 LOW;原 LOW):V1 開圖核:select 只見「掃單簇」、min/max 不可見;list.png 相符;七條與旗標另由 migration-dry-run / startup-log 核過 | Nice to Have | `auto-fix` | curl 重錄原始 JSON(或檔首補指令);§4 第三列收斂宣稱 |
| F-38 | `.claude/mod/signal-shadow-policies/code-review-round-1.json:6` mod 版 19 條無 `file` 錨、`disposition` 是 ~1.5 KB 散文;followups 版 per-finding 有 file/disposition/commit;內容齊、形狀不可機械讀(C4-F7) | LOW | CONFIRMED(校正 LOW;原 LOW):V1 程式化比對鍵集如述 | Nice to Have | `auto-fix` | mod 版拆成 per-finding 欄位,收尾鏈固定用後者 schema |
| F-39 | `tests/server/test_signal_hub.py:2328` 案名 / docstring 說釘兩件事,四條斷言只反映「發過的群不再發」;突變「群內每達標筆都登記」hub 全綠、只 golden 3 紅(C3a-F4) | LOW | PARTIAL(校正 LOW;原 LOW):V2 序列重跑 M1 全量 3 failed / 464(golden 三案紅)獨立重現;保護存在,只是落在 AC 指名以外的 seam | Nice to Have | `auto-fix` | 補一個 4 筆第一群 + 第二群不成群,斷 published == [] |
| F-40 | `tests/server/test_signal_outcome.py:345` 零補時 `b"".join(lines)` 與原檔逐位元組相同,`read_bytes() == before` 在重寫 / 不重寫下都成立;突變 `if True:` 全綠(C3a-F5) | LOW | CONFIRMED(校正 LOW;原 LOW):V2 序列重跑 M7 全量 467 passed;後果只 IO / mtime 雜訊(過去日檔無 concurrent append,除非 C3a-F1 守門先拿掉) | Nice to Have | `auto-fix` | 斷 st_mtime_ns 或 monkeypatch atomic_write_bytes 計次 0 |
| F-41 | `tests/fixtures/record_sweep_cluster_golden.py:42` 6715 4/4、1727 5/5、8103 2/2;差異全是「發訊早 / 層數低」那類;`test_fixture_self_check` 只封 ⊆ 與 earlier 非空,重錄路徑若多發大增仍全過(C3a-F6) | LOW | PARTIAL(校正 LOW;原 LOW):V2 核 11 事件中 6 個 prefix 與 research 的 i/price/levels/qty 不同(1727 第 5 事件 i=301/77.3/3/5 vs 310/78.3/13/50),集合相等比對已釘即時判語意;缺口只在重錄 self-check 不封多發上界 | Nice to Have | `auto-fix` | CASES 補一個含多發的股票日,或 self-check 加多發上界 |
| F-42 | `tests/server/test_signal_outcome.py:152` `_Harness` 硬寫 `basis_gap_secs=0.0`;`_fetch_outcome_bars` 尾端 gap 段永遠 no-op;突變刪段全綠;AC 明列逐檔間隔沿 CDP gap(C3a-F7) | LOW | CONFIRMED(校正 LOW;原 LOW):V2 序列重跑 M5 全量 467 passed;prod 預設 `basis_gap_secs` 0.2;後果 = 回填時對 TC4 逐檔節流失效 | Nice to Have | `auto-fix` | 一案 days=1 兩 code、gap 0.05,monkeypatch asyncio.sleep 計次 |
| F-43 | `tests/server/test_signal_outcome.py:368` docstring 自陳「worker 死掉 = 之後所有政策列 t1/t2 永遠 null 零訊號」並用 try/except 擋;測試沒有讓 backfill 本體拋例外的案(既有失敗案在 `_fetch_outcome_bars` 內就吃掉)(C3a-F8) | LOW | CONFIRMED(校正 LOW;原 LOW):V2 通讀 TestSchedule 四案 + no_source 案無一讓本體拋;`_FakeDayBars` 失敗注入打不到外層傘 | Nice to Have | `auto-fix` | monkeypatch atomic_write_bytes 第一次拋 OSError,推到隔日 13:40 斷第二趟仍跑 |
| F-44 | `tests/server/test_signal_policy.py:376` 守門 `ref is None or ref <= 0 or price <= 0` 改成 `ref is None` 全綠;`to_milli_units("0")` 回 0 不是 None;失效 = ZeroDivisionError → `_fanout` 傘吞、只留 ERROR、raw 列仍在 → 只斷零政策列殺不掉,補案要連 caplog 斷(C3b-F4) | MEDIUM | CONFIRMED(校正 LOW;原 MEDIUM):V2 序列重跑全量 467 passed;型別可達但「TC4 真送 ReferencePrice=0」無實證;終局與守門相同(零政策列 + raw 列在)只多 traceback;`price <= 0` 半不可達(`_eval_sweep:708-710` 早退) | Nice to Have | `auto-fix` | 一案 ref=0,caplog.at_level(ERROR) 內斷零政策列 + raw 列在 + caplog.text == "" |
| F-45 | `tests/server/test_signal_policy.py:437` 姊妹旗標 `_peers_fn_failed` F-33 補洞時兩半都測了,`_multi_group_warned` 只有當日一次那半;刪 `on_rollover:666` `clear()` 與 `drop_code:761` `discard()` 全綠(C3b-F5) | LOW | CONFIRMED(校正 LOW;原 LOW):V2 序列重跑刪兩歸零點全量 467 passed;旗標只 gate log,無資料面後果 | Nice to Have | `auto-fix` | 既有案尾加 on_rollover() + 再發一顆,斷 count == 2 |
| F-46 | `tests/server/test_signal_routes.py:59` F-39 改共用 `_RULE_PARAMS` 的 rationale 是讓 `_rule_body("sweep_cluster")` 寫得出來,結果整檔 16 個呼叫點無一傳 sweep_cluster;先例 `test_post_surge_pullback_round_trips`(C3b-F7) | LOW | PARTIAL(校正 LOW;原 LOW):V2 反證「整檔零 caller」不準(:103 `_rule_body` 內有用),缺往返案那半成立;值域另由 parity 三處釘 | Nice to Have | `auto-fix` | 照 surge_pullback 先例複製一條 sweep_cluster 往返案 |
| F-47 | `frontend/src/components/stock/SignalRail.tsx:282` rail 無 memo、StockPage 每 ticks 打包重繪;政策列每 render 多做 `policyContextText` + `policyTitle`(map 全部同伴);建議 memo 子元件 / 惰性 title(C2-F8) | LOW | REFUTED(校正 LOW;原 LOW):V2 baseline —— 同檔 `SignalRail.tsx:269` `ruleTitle` 每組每規則名做 reverse + Set,對 rail 每一列執行且長期未列效能問題;`policyTitle` 只在政策組(一天 25 組)跑,是最小的那份 | 參考用 | `no-op` | 同 pattern 平行更重處長期未爆,非本 range 缺陷 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 4ddc56b5fcc8d5a76b13 action=ask-user
F-02 finding_uid: 4c10b40937fe4a23cb75 action=auto-fix
F-03 finding_uid: 7a49868f4f658d63f041 action=auto-fix
F-04 finding_uid: db995a72148739fc4e5d action=auto-fix
F-05 finding_uid: 0b2a12dcf89834fb526a action=auto-fix
F-06 finding_uid: c351c24660eeb1aa5476 action=auto-fix
F-07 finding_uid: f8984d2a4d669f944a2d action=auto-fix
F-08 finding_uid: 339959f8215f691283a2 action=auto-fix
F-09 finding_uid: 106618211e2b9c3c58b5 action=auto-fix
F-10 finding_uid: 64ed0af23ddbdf18b38b action=ask-user
F-11 finding_uid: 1b94267836d2befe69df action=ask-user
F-12 finding_uid: 15040adbcf1c2690a291 action=auto-fix
F-13 finding_uid: 1ed2a85a0e2b1e78b692 action=auto-fix
F-14 finding_uid: 9e9b43edacdf7041b6c2 action=ask-user
F-15 finding_uid: 41b5a735ac318811eff5 action=auto-fix
F-16 finding_uid: cd5f428560ac9d00f5b0 action=auto-fix
F-17 finding_uid: 58fd1c90ad4cc2b0cefe action=auto-fix
F-18 finding_uid: c7dbed7543afac883990 action=auto-fix
F-19 finding_uid: db9e368444d0bf671425 action=auto-fix
F-20 finding_uid: 068019813b2e8f05c069 action=ask-user
F-21 finding_uid: fb7e890075dd06e51579 action=auto-fix
F-22 finding_uid: 9209c946b9de48474114 action=auto-fix
F-23 finding_uid: 8b7e753ac2a7e83c6547 action=auto-fix
F-24 finding_uid: c5623924f9d2fec55c57 action=auto-fix
F-25 finding_uid: 1aed0f32df2b8b20eedf action=auto-fix
F-26 finding_uid: df200d6d88254373b38d action=auto-fix
F-27 finding_uid: c20939dc01c9cd3136b9 action=auto-fix
F-28 finding_uid: a98133e574538c70ba69 action=auto-fix
F-29 finding_uid: 86c75a1d7d22c15ae678 action=auto-fix
F-30 finding_uid: bc5cbba9f6d2f95ef729 action=auto-fix
F-31 finding_uid: 6e8746e9e48b5d6516d3 action=ask-user
F-32 finding_uid: aa610aaf5d5261ba17da action=auto-fix
F-33 finding_uid: d13f55efb214f5ba6106 action=auto-fix
F-34 finding_uid: 2e4115511b91511d6ab3 action=auto-fix
F-35 finding_uid: 1aaeff5b25849bbe973e action=auto-fix
F-36 finding_uid: 6793995d94a5861e9508 action=auto-fix
F-37 finding_uid: 49da91997ab1a2452658 action=auto-fix
F-38 finding_uid: 2b1fc1ef4c4cfd8d61dc action=auto-fix
F-39 finding_uid: 7daa2f161abb7be249e4 action=auto-fix
F-40 finding_uid: 6e9ef8a18831feb7294a action=auto-fix
F-41 finding_uid: af7482a913eb57ebffda action=auto-fix
F-42 finding_uid: 8eb5ed2576f710fdfc29 action=auto-fix
F-43 finding_uid: 713d549a335784d6f726 action=auto-fix
F-44 finding_uid: 04feaca54016e38de49a action=auto-fix
F-45 finding_uid: 071ae01e2c8e8ae5a343 action=auto-fix
F-46 finding_uid: 57240361d1a767da5c42 action=auto-fix
F-47 finding_uid: a4f72fcbeb340a92778f action=no-op

### Inline Comments per Finding（直接複製貼到 PR review）

#### #1 影子期要對決的研究 §8.2 基準表,「12:30 前」濾網其實是 no-op

**File**: `copycat/server/signal_hub.py`
**Line**: 1077

**Comment**:
```
線上的 late(secs > 12:30)是對的,問題在對照組:研究 §8.2 那張表用 combo_wlpolicy.py:41 的
`df.tod < 1230` 當「12:30 前」,可是 tod 是 "0900"/"0910"/"0930"/"1030"/"1200" 五個桶,pandas 讀成 int 後全部 < 1230
→ 濾網沒作用,表裡混著 65 筆 late=1 的事件。V1 重算過:「排除 ALL IN」列 36/+5,497/22% 改成 late==0 是 35/+5,784/23%。
影子期必然是 late==false,四週後直接對 +5,497 等於比兩個母體。修法擇一:HANDOFF §8.2 表下加註,或把 :41 改 `(df.late == 0)` 重出 wlpolicy.out。
```

#### #2 「只碰過去日」只釘了 hub 日別超前那一半,拿掉另一半會整檔覆寫還在寫的當日檔而測試全綠

**File**: `tests/server/test_signal_outcome.py`
**Line**: 263

**Comment**:
```
signal_hub.py:1252 的 `cutoff = min(self._trade_date_fn(), self.today)` 兩半各擋一種情境,但這裡只有 hub 日別**超前**牆鐘那一案。
把 min 改成只看 self.today,test_signal_outcome + test_signal_hub + test_signal_policy 全綠(V2 全量 467 也綠)。
漏掉的那半是常態:午夜到當日首 tick 前 hub 日別停在昨日、牆鐘已是今日,昨日檔正是 _append_jsonl 還在寫的檔,
放掉守門就是 atomic_write_bytes 整檔蓋掉中間 append 進去的列、零訊號。
補一案:h.date = _PREV(落後)+ 牆鐘 _DATE,斷 20260803.jsonl 的 t1_open 仍是 None。
```

#### #3 排除組名對不上任何自選群組時零訊號,改個組名 ALL IN 就靜默變族群

**File**: `copycat/server/signal_policy.py`
**Line**: 109

**Comment**:
```
resolve_groups 的 `if name in exclude` 是逐字比對:設定寫「ALL IN」、自選群組改成「ALL-IN」/「All in」,排除就整個失效,
沒有任何 log。prod 現在沒有 configs/signals.json,靠預設值,所以 user 在自選 UI 改一次名就生效。
研究 §8.2 說得很清楚:ALL IN 當族群是負的(n=10、每筆 −1,471)—— 那四檔會變成彼此的同伴,P/B 在錯的族群上發,
四週的資料被污染。列上有 groups/peers 欄事後看得出來,但沒人會去看。
補法:hub _refresh_groups 之後對 exclude 逐名查「有沒有任何群組叫這個名」,零命中 WARNING 一次(與 _multi_group_warned 同款每日去重)。
```

#### #4 簇窗與回看基準的閉區間界零樣本,兩個邊界突變體全綠,而 prod tick 全落在整秒

**File**: `tests/server/test_signal_hub.py`
**Line**: 2291

**Comment**:
```
spec 兩個窗都寫閉區間:「落在 [s − cluster_window, s]」「時刻 ≤ s − up_window 的最後一筆」,研究參考碼也是 bisect 含界。
線上 signal_state.py:744 `sweeps[0] < window_start` 與 :719/:748 `<= cutoff` 目前是對的,但測試全部離界很遠(31 s、窗前完全無成交),
把 :744 改 `<=`、或 :719/:748 改 `<`,全量 467 tests 照綠。
prod 個股 tick 時刻實測全是整秒(09-07 那 75 列 sweep/policy 100% `.000`),恰差 30 s / 60 s 每天都會撞到,漂了就是漏發或多發。
TestSweepCluster 補兩案:(a) 掃單 1 在 10:01:00.000、掃單 2 在 10:01:30.000 → 應發;(b) 回看基準那筆恰在 s − 60.000 → 漲幅算得出來、應發。
```

#### #5 掃單簇軸完全沒有 session gate 測試,把 _eval_sweep 搬到 09:00–13:30 閘之前全綠

**File**: `tests/live/test_signal_state.py`
**Line**: 700

**Comment**:
```
signal_state.py:300-311 把 _eval_sweep 上移到「首 tick 只初始化」gate 之前(刻意,註解有講),它現在正好卡在 _in_session 與舊日 snapshot 兩道 gate 之後。
再往上挪一格 —— 盤前試撮與 13:30 收盤撮合的成交進回看窗與同毫秒群 —— 全量 467 tests 照綠,
因為 TestSessionGates 用的 _ALL 不含 sweep_cluster,而 golden fixture 的產生腳本自己先濾掉了窗外資料。
收盤撮合那一筆常是當日最大的同秒群(F-25 收修時三案各掉一筆就是它),足以造假掃單簇 → 假政策列進 jsonl。
補:TestSessionGates 加 `_SWEEP` 案(08:59 餵完整兩群 → [],進窗後第一群仍算首群),外加一案舊日 trade_date。
```

#### #6 round-1 唯一那條 HIGH(chg round 2 同尺)的修正沒有任何測試釘住,拿掉 round 全綠

**File**: `tests/server/test_signal_policy.py`
**Line**: 179

**Comment**:
```
signal_hub.py:1059 的 `chg = round((price - ref) / ref * 100, 2)` 是 round-1 標準軸 F-01(唯一 HIGH)的修法:自己不 round、同伴走 _quote_payload round 2,
leader = chg >= peer_max 就是兩把尺。可是把 round 拿掉,test_signal_policy / hub / outcome 全綠(V2 全量 467 也綠)——
既有案的 chg 不是 0.8 這種整齊值就是 pytest.approx,看不出差別。這是已經錯過一次的東西,現在零回歸保護。
補一案:_fire(h, _state(ref=48_933, upper=55_000))(2.99797 → round 3.0)+ peers 華邦電 3.0,
同時斷 [m["self"]["chg_pct"]] == [3.0, 3.0] 與 _policies(h) == ["B-a", "B-b"](現行綠、拿掉 round 紅,已實測)。
```

#### #7 「自己較前收 < 6%」恰等於 6.00 時該不該發沒有任何測試,`<` 改 `<=` 全綠

**File**: `tests/server/test_signal_policy.py`
**Line**: 265

**Comment**:
```
signal_policy.py:160 `under_cap = chg < max_chg_pct` 是 P / B-a / S 三條共用的閘,測試只有 +3.92 和 +7.23,
改成 `<=` 全量 467 tests 照綠。chg 在 hub 已經 round 到 0.01,恰好 6.00 不是浮點巧合,是每天都會出現的格。
補一案:_fire(h, _state(ref=47_547, upper=55_000))(50_400/47_547 → 6.0)、groups=[_MEM, _SCREEN]、同伴 1.0,
斷 _policies(h) == [](現行綠、`<=` 紅,已實測)。
```

#### #8 「自己是族群最強」平手時算不算沒測,`>=` 改 `>` 全綠,而平手在同族群同步拉抬時是常態

**File**: `tests/server/test_signal_policy.py`
**Line**: 245

**Comment**:
```
signal_policy.py:159 `leader = … chg >= peer_max` 決定 B-a / B-b;測試只有自己 3.92 > 同伴 3.0,改成 `>` 全量 467 綠。
自己和同伴的 chg 都 round 到 0.01,同族群一起拉的時候撞同一格很常見,研究定義 group_feats 的 _leader 也是 `>=`。
改錯這一格,「與同伴同幅」那批 B 事件靜默消失、jsonl 少列。
補一案:_fire(h, _state(ref=48_932, upper=55_000))(chg 恰 3.0)+ peers 華邦電 3.0,斷 _policies(h) == ["B-a", "B-b"]。
```

#### #9 locked_up 的「限價賣側空」那一半沒被任何測試釘住,拆掉市價佇列判斷仍全綠

**File**: `tests/server/test_stock_engine.py`
**Line**: 1439

**Comment**:
```
signal_policy.py:66-74 locked_up_flag 的兩半:price == upper、限價賣側空。TestPolicyQuotes 那案第二筆同時把價 2550→2545 又把賣側 ""→2550,
所以 locked_up False 只被「價 ≠ 漲停」一項解釋;把整個判斷改成 `return price == upper`,全量 467 綠。
後果:每一筆「在漲停價成交但賣方還掛得出限價」的 tick 都記成 locked_up: true —— 這欄不進政策條件,但它就是 story 16 留給事後重算的快照。
在既有兩筆後補第三筆 src.on_message(_quote(cum=3, price="2550", bid="2545", ask="2550")),斷 price == upper == 2_550_000 且 locked_up is False。
```

#### #10 start 那一趟 T+1/T+2 回填零延遲連發 DK,跟 CDP 基準暖機搶同一把 TC4 鎖

**File**: `copycat/server/signal_hub.py`
**Line**: 1224

**Comment**:
```
signal_hub.py:526-542 start() 同一輪起 _basis_worker 和 _policy_outcome_worker,後者 :1220-1224 第一件事就是 _run_policy_outcomes(),
`_past_time` 只決定 ran_for、不決定跑不跑。回填的 bars_range 與基準的 fetch_daily_bars 最後都落到 tc4._req → api.lock.acquire,
TC4 請求是全域序列化的,兩條 worker 只會互相拉長。V1 量了 prod:明早首跑 15 檔 DK ≈ 5–18 s,基準 sweep 約晚 10%;
影子期日檔累積後會到 40–75 檔。這一趟補的是昨天以前的開盤價,晚到 13:40 一樣。
方向:start 那趟只在 `_past_time(now, policy_outcome_time)` 成立時立即跑,其餘等排程;或先等基準佇列排空。
```

#### #11 新的兩個 kind 讓研究 nosig.py 的三桶分群靜默換尺,而契約只保證「不新增列型」

**File**: `copycat/server/signal_hub.py`
**Line**: 1093

**Comment**:
```
story 27 / W1 / CLAUDE.md §4 保證的是「每列 kind 恆在、不新增列型」,擋得住 KeyError,擋不住「以 kind 為輸入但沒白名單」的讀者。
研究目錄 nosig.py:52 `own = [s for s in byday[d] if s["code"]==f["code"]]` 沒濾 kind(下一行 others 有),has_sig / any_sig_day 決定 A/B/C 三桶,
09-07 起同檔同日多了 sweep_cluster 46 筆/日、policy 29 筆/日,原本「完全無訊號」的買進會被重新歸類,而它 glob 整個 data/signals → 同一張表兩把尺。
兩件事:nosig.py:52 補既有六 kind 白名單(一行);CLAUDE.md §4 那條改成「離線讀者以 kind 為輸入必須帶白名單;新增 kind 值本身允許」。
```

#### #12 新沉澱的掃單事實把「不用 tick.side」的理由寫錯,跟同一支 skill 的鎖漲停節自相矛盾

**File**: `.claude/skills/tc4-market-facts/SKILL.md`
**Line**: 75

**Comment**:
```
這條 bullet 的括號說「鎖停日 ask 是市價佇列 0,derive_side 會判 outer,所以改用 ask > 0 and price >= ask」—— 三件事都對不上 code:
線上 tick.ask_milli 就是 derive_side 吃的 ask0,stock_models.py:149-160 _best_limit_price 把全市價 / 空簿回 None,0 到不了任何一邊;
鎖漲停時 derive_side 給的是 neutral(這支 skill 自己 :93 就這麼寫);所以 tick.side == "outer" 跟 `ask is not None and ask > 0 and price >= ask` 在 prod 等價。
真正的理由是研究 pull_ticks.py:63 保留原始 Ask=0、find_sweeps 才要 `ask[i] > 0`,線上為了逐字對齊而保留同一道閘。
括號改成這句,不然 Trigger「想改用 side 判外盤」會把後人引去補一個不存在的洞。
```

#### #13 「全組 quiet 才淡色」的 every 沒有混合組案,改成 some 全綠,而 prod 每則政策列都是混合組

**File**: `frontend/src/components/stock/SignalRail.test.tsx`
**Line**: 583

**Comment**:
```
SignalRail.tsx:185 `group.items.every((s) => !shouldNotify(s))` 是「全列皆 quiet 才淡色」的唯一實作,但這三案的組都只有一個元素,
every 和 some 對單元素恆等 —— 改 some,vitest 41 案綠,V2 跑全量 2381 也綠。
prod 種子掃單簇規則通知關,每一則政策列在 rail 上都是「政策 notify=true + raw 掃單簇 notify=false」同 tick 混合組,
some 版本會讓每一列政策列都 50% 淡色,正好是 story 19「醒目」的反面。
同檔 :546「同 tick 政策 + raw 掃單簇」那案已經有混合組治具,補一行 expect(li.className).not.toContain("opacity-50") 就殺得掉。
```

#### #14 沒有族群的 S 政策列,rail 第三行照樣印「同伴≥3% 0・鎖過 無」,跟 hover 的「盤前篩選名單・無族群濾網」矛盾

**File**: `frontend/src/lib/signal-model.ts`
**Line**: 290

**Comment**:
```
policyContextText 對所有政策列同一條路:peers_up ?? "-" 只在缺欄時退 -,而 S 列後端送的是 groups: []、peers: []、peers_up: 0、peer_touched: false,
都是真值,語意卻是「根本沒有同伴」。同一顆 span 的 title(policyTitle :312)和 Discord 第三行(signal_hub.py:257)都有
`groups.length === 0 → 盤前篩選名單・無族群濾網` 這條分支,只有畫面上看得見的那行沒有。
09-07 的 29 列政策列裡 16 列(全 S)groups 為空、9 列跳了 toast —— 盤中讀到「同伴≥3% 0・鎖過 無」跟一則族群乾淨的 P 列長一樣。
補同一條分支(無族群 → 「無族群・+x.x%/停 y.y%」之類),文案由你定。
```

#### #15 合併分支的政策雙嗶那一行整行刪掉,測試全綠

**File**: `frontend/src/hooks/useSignalAlerts.test.tsx`
**Line**: 718

**Comment**:
```
useSignalAlerts.ts 發雙嗶有兩條路:新開 toast(:254)和併入既有 toast(:234 `if (firstPolicy) beepFor(true)`)。
新增四案只走前者;「同 tick 兩條政策」第二則併入時 firstPolicy 已是 false,本來就不該響。把 :234 整行刪掉,44 案綠、V2 全量 2381 也綠。
只要你把「掃單簇」規則通知打開(規則視窗一鍵),raw 列先開一張 toast、政策列隨後併入,雙嗶就只能由 :234 發。
補一案:先 emit notify:true 的 raw 掃單簇、再 emit 政策列,斷 toasts.length === 1 且 oscillators === 3。
```

#### #16 「雙嗶」只數 oscillator 個數,第二聲偏移改 0(兩聲同時發 = 聽起來一聲)全綠

**File**: `frontend/src/hooks/useSignalAlerts.test.tsx`
**Line**: 710

**Comment**:
```
useSignalAlerts.ts:58 SECOND_BEEP_OFFSET_S = 0.18 的註解自己說「兩聲同時 start 聽起來是一聲」—— 錯開才是這功能的可觀察內容,
測試卻只斷 oscillators === 2。把 offset 改 0 全綠,因為 fake 的 createOscillator() 回的 start: () => {} 把參數丟了。
fake 改成 starts.push(t),補一條斷兩聲起點相差 > 0(不要寫死 0.18)。
```

#### #17 複查 F-11:「掃單簇 +x.xx%」在 pct=0 / 缺 pct 兩點前後端不逐字,而 F-11 的否決只答了小數位

**File**: `frontend/src/lib/signal-model.ts`
**Line**: 104

**Comment**:
```
CLAUDE.md §4 說「掃單簇 +x.xx%」前後端逐字對齊(_kind_text ↔ kindLabel)。實測:非零值一致;pct=0 後端 `掃單簇 +0.00%`、前端 `掃單簇 0.00%`;
缺 pct 後端 `+0.00%`、前端 `掃單簇`。差在 format.ts:24-26 fmtPct 對零不帶號,後端 f"{value:+.2f}%" 帶。
round-1 F-11 提過零值不同,否決理由講的是「一位 / 兩位小數是版面需求」,沒回答正負號。up_pct 值域下限是 0,設 0 後窗前無成交的簇會發 up_pct=0.0。
surge/crash 同病(既有),要收就一起:fmtPct 給 signedZero 參數,或 kindLabel 這幾支改與後端同式。
```

#### #18 同 tick 兩條政策而 first_of_day 一真一假時,hover 標題並列兩個標記卻只印 anchor 那條的「首筆」

**File**: `frontend/src/lib/signal-model.ts`
**Line**: 307

**Comment**:
```
policyTitle 第一段 `政策 ${tags.join("・")}` 是整組標記,尾段 when 卻取 groupPolicyAnchor 選出的單一列的 first_of_day / late。
first_of_day 是 per (檔, 政策)計數(signal_hub.py:1088-1090),S 早上先發過、P 第一次命中同 tick → hover 印「政策 P・S｜…｜0930・首筆」對 S 是錯的。
09-07 四組同 tick P+S 目前都一致,還沒上演。when 段改成 per-tag(P 首筆・S 非首筆),或只在組內單一政策時印。
```

#### #19 複查 S-02:同一行 peer_touched 還是 === undefined(null 會印「無」);policyTitle 的 peer 迴圈有個永遠不成立的 null 三元

**File**: `frontend/src/lib/signal-model.ts`
**Line**: 283

**Comment**:
```
signal-model.ts:283-285 peers_up 用 ??(null/undefined 都退 -),下一行 peer_touched 用 === undefined,收到 null 會落到 `null ? "有" : "無"` 印「無」——
round-1 S-02 的理由「?? 更穩」對這半同樣適用,只是沒改到。後端恆送 bool,所以不可觸發,純一致性。
另外 :299-301 `p.chg_pct === null ? "-" : pct1(...)`:pct1 第一行就把 null/undefined 收成 "-",外面這個三元是 dead code。
```

#### #20 新後端配舊 dist 時,規則視窗對「掃單簇」那列按「編輯」點了沒反應;spec 的 Backward compat 括號只保證訊號列不炸

**File**: `frontend/src/components/stock/SignalRulesDialog.tsx`
**Line**: 76

**Comment**:
```
spec Backward compat 那句「dist 舊 build 收到 policy kind 只會印英文代號、不炸」對 WS 訊號列成立(kindLabel 尾行 return kind 有測試釘),
規則視窗這條不成立:舊 dist 的 PARAM_FIELDS 只有五個 kind,GET /api/stock/signals/rules 回來的種子「掃單簇」按「編輯」走 toForm →
PARAM_FIELDS["sweep_cluster"] 是 undefined → for…of 丟 TypeError。呼叫點在 onClick,React 不卸載,症狀就是點了沒反應、只有 console 有錯。
今天早上有 build 所以沒踩到,但下一次加 kind 會原樣重演。二選一:spec / CLAUDE.md 補「規則視窗需同版」;或 toForm / ruleSummary / KIND_LABEL 對未知 kind 給 `?? []` 退路。
```

#### #21 groupPolicyAnchor「取組內最早到那則」的契約零測試,改取最後到 131 案全綠

**File**: `frontend/src/lib/signal-model.test.ts`
**Line**: 5

**Comment**:
```
signal-model.ts:271-273 groupPolicyAnchor docstring 說「組內最早到的政策列」,它是 rail 第三行與 hover 的唯一資料來源;
把 arrivalOrder(group).find(isPolicy) 換成 group.items.find(isPolicy)(取最後到),signal-model + SignalRail + useSignalAlerts 131 案全綠、V2 全量 2381 也綠。
同 tick 各政策列脈絡欄位相同,唯一會分岔的是 first_of_day —— 正好是 C2-F6 那個 bug。
補一案:兩則政策列 first_of_day 一真一假,斷 groupPolicyAnchor 回先到那則。
```

#### #22 群組讀取失敗的 log 只講「同群摘要」,但同一份 _groups 現在也是族群判定唯一來源

**File**: `copycat/server/signal_hub.py`
**Line**: 715

**Comment**:
```
signal_hub.py:703-715 _refresh_groups 失敗時保舊值是對的,問題是訊號:log 只講「同群摘要沿用上一份(0 組)」,
可是 _emit_policies:1037 用的是同一份 _groups,空的話 resolve_groups 零命中 → :1041 直接 return,P/B-a/B-b/S 一整天零列。
V1 查過可達性:app.py:854 的 load_watchlist 在 on_watchlist 之前求值、壞檔會先在 _boot 大聲停用整顆 hub,所以真走到這條路要靠瞬時 IO 失敗,不算急。
文案改成同時點名兩個消費者就好:「同群摘要與政策族群沿用上一份(%d 組;0 組 = 本日 P/B/S 全不評)」,_refresh_groups docstring 一起改。
```

#### #23 groups_fn 注入處的註解還停在同群摘要時代,「漏接 = 通知少一段尾巴」已不成立

**File**: `copycat/server/app.py`
**Line**: 841

**Comment**:
```
app.py:839-842 這段是在解釋 groups_fn / quotes_fn 為什麼只靠接線測試把關 —— 理由是「漏接的失效樣態是通知少一段尾巴」。
spec #192 之後 groups_fn 經 signal_hub.py:713 → 1037 resolve_groups 決定族群,漏接的後果是 P/B-a/B-b 整段不評,不是少段尾巴;
它又正好緊鄰新加的 peers_fn= / outcome_bars= 兩行,最容易在這裡讀出錯的風險印象。改寫成兩個消費者各自的失效樣態,_refresh_groups docstring(:704-708)一起。
```

#### #24 data/signals/ 不存在時整趟回填零 log,盤後判準分不出「worker 沒跑」與「沒東西可補」

**File**: `copycat/server/signal_hub.py`
**Line**: 1254

**Comment**:
```
backfill_policy_outcomes 的三條出口,:1267「沒有日期 < %s 的已封閉日檔,本趟零列」和 :1335「共回填 %d 列」都有 log,
只有 :1253-1255 `if not signal_dir.exists(): return` 靜默。全新部署 / data_dir 打錯那天 13:40 完全沒那一行,跟「worker 沒起來」長一樣。
換成 logger.info("T+1/T+2 回填:%s 不存在,本趟零列", signal_dir) 即可。
```

#### #25 複查 F-09:「當日一次」旗標把 traceback 收乾淨了,但沒留計數,事後不知當天幾顆事件被降級

**File**: `copycat/server/signal_hub.py`
**Line**: 1055

**Comment**:
```
signal_hub.py:1050-1056 這道「當日只印一次」節流是 round-1 F-09 修的,本身正確。可是第二次以後的失敗完全沒痕跡,
而降級的後果不小:quotes = {} → evaluate_policies 的 quoted 為空 → P/B-a/B-b 全不評(:162),只剩 S。
四週對帳時「P 沒發」是條件不成立還是快照壞掉,只能翻那列 peers 全 null 去猜。hub 已有 dropped_jsonl + _DROP_LOG_EVERY 的慣例(:1136-1140),
旗標換成計數器、首次 exception、之後每 N 筆一行 WARNING 帶總數,on_rollover 照舊歸零。
```

#### #26 tick_secs 解析失敗時退回牆鐘秒數,把 1.78e9 混進 sweeps deque → 此後整條 deque 永不修剪

**File**: `copycat/live/signal_state.py`
**Line**: 713

**Comment**:
```
signal_state.py:709-713 tick_secs 回 None 時退回 mono(1970 起算秒,≈1.78e9),sweeps deque 裝的是自午夜秒數(≈3e4)。
V1 探針實跑:毒值進去後 :744 `sweeps[0] < window_start` 恆假,整條 deque 從此不修剪,n30 變成當日累計掃單數,簇窗形同取消。
lookback 那半會自癒(:719 比的是 lookback[1])。目前不可達:tick.time 由 _taipei_time 恆產 HH:MM:SS.fff;docstring 說「空字串」也不對,:308 空字串走時鐘。
改成 `if secs is None: return []`(沒可信時刻就不推進掃單軸)+ 修 docstring。
```

#### #27 policy_quotes(codes=None) 整份自選分支零生產呼叫者,TestPolicyQuotes 十一個呼叫點十個走死分支

**File**: `copycat/server/stock_engine.py`
**Line**: 775

**Comment**:
```
stock_engine.py:775 `picked = self._watchlist if codes is None else list(codes)`:生產路徑只有 app.py:820 注入、hub :1049 恆傳 peer_codes,
None 分支沒有 caller。test_stock_engine 的 policy_quotes() 十一個呼叫點只有 :1395 傳清單。V1 補一句:per-code 組裝兩路共用,所以覆蓋不算真的缺,
但參數形跟 prod 不同就是會誤導。codes 改必填(Iterable[str]),呼叫端與測試各改一行。
```

#### #28 policy_outcome_days ≤ 0 會靜默停掉整個回填,那行 INFO 看起來完全正常

**File**: `copycat/signals_config.py`
**Line**: 75

**Comment**:
```
六個 policy_* 鍵裡 F-06 只把兩個 HH:MM:SS 拉進 SignalHub.__init__ 驗證。policy_outcome_days 設 0 / 負數 → :1265 dated[:0] 恆空 →
每趟印「沒有日期 < X 的已封閉日檔,本趟零列」,把設定錯講成資料狀態,T+1/T+2 永遠不補。
裸 assert 那半 V1 推翻了(configio.py:30 是四支設定共用的 loader,既有形狀);元素非 str 那半跟 C1-F5 同後果。
把 `policy_outcome_days >= 1` 放進 __init__ 那個驗證迴圈就好。
```

#### #29a 複查 F-16:「種子沒進去 = 影子期零政策列」只掛在撞名分支,滿 30 條分支沒有,而測試把弱版本釘死

**File**: `copycat/signal_rules.py`
**Line**: 451

**Comment**:
```
signal_rules.py:436-461 _append_seed 兩條跳過分支後果一樣(掃單簇種子沒進去 = 政策層整期零列),F-16 的收修只把 skip_note 接在撞名那行(:448),
滿 30 條這行(:451)還是只說「規則數已達上限」—— 而滿載其實比撞名更可能(撞名需要 v3 世界就有一張叫「掃單簇」的卡)。
tests/test_signal_rules.py:945 斷的正是缺後果那版字串,等於把不對稱釘死。
:451 加 `%s` + skip_note,測試比照 :932 撞名案改斷 "零政策列" in hits[0].getMessage()。
```

#### #29b 複查 F-16:「種子沒進去 = 影子期零政策列」只掛在撞名分支,滿 30 條分支沒有,而測試把弱版本釘死

**File**: `tests/test_signal_rules.py`
**Line**: 945

**Comment**:
```
這條斷的是缺後果的那版字串(:451 沒接 skip_note),把不對稱釘死了。source 接上後這裡改成與 :918-933 撞名案對稱:
斷 hits[0].getMessage() 同時含「規則數已達上限」與「零政策列」。
```

#### #30 回退手順沒寫「退回 v3 再升 v4,翻旗會再跑一次」,手動改回的通知會被第二次遷移靜默再關

**File**: `copycat/signal_rules.py`
**Line**: 513

**Comment**:
```
signal_rules.py:507-518 回退手順:刪種子卡、通知改回 true、_cache_version 改 3 → 起舊碼。沒寫的是:再升回 v4 碼時 load_rules 看到 version != 4 又跑一次 _migrate_v3,
cdp_cross / vol_burst 的通知會被再關一次 —— 如果當初退回就是為了要 CDP 穿越的通知,這一輪來回會讓決定靜默消失。
:471-472 其實已經講了翻旗只認 v3 前的檔,回退段補一句「再升級翻旗會重跑;要保留通知升級後在規則視窗再開一次」就完整。
```

#### #31 回填只補 T+1/T+2 開盤,事件當日的 13:20 出場價與「鎖死留倉」旗標不在列上,story 18 的「週對帳直接讀 jsonl」只成立一半

**File**: `copycat/server/signal_hub.py`
**Line**: 1315

**Comment**:
```
研究「放到尾盤 B」的出場鏈(combo_events.py:331-340 hold_exit)是 13:20 價 vs 漲停價:≥ 漲停 → 鎖死留倉隔日開盤出,否則 13:20 出。
政策列上有 t1_open/t1_date/t2_open/t2_date 與 self.to_limit_pct(可還原漲停價),沒有事件日的 13:20 價 / 收盤 / 當日高。
所以四週後 §8.2 的「每筆」「鎖死」兩欄還是得對 ~29 列/日 × 20 日的 (code, date) 另抓一次日 K。spec 把週對帳腳本留在研究目錄,那邊有資料,不算缺陷;
但 story 18 的「週對帳直接讀 jsonl」讀起來像補齊了。二選一:CLAUDE.md §4 回填那條補一句;或 worker 已經抓到事件日那根 D bar,順手補 d_close / d_high 兩欄。
```

#### #32 「線上 chg 用當筆成交價、研究用進場價」這條口徑差沒落在任何文件裡,而它讓 1.4% 的事件在 6% 界上翻面

**File**: `copycat/server/signal_hub.py`
**Line**: 1059

**Comment**:
```
signal_policy.py:1-22 模組 docstring 的「與研究的已知差異」只有兩條(鎖過閘只看同伴、即時判 0.7%)。第三條沒寫:
線上 chg = (當筆成交價 − ref) / ref,研究 frompc 用「觸發後下一筆 +1 檔」的進場價。V1 拿 events.csv 865 個 sweepc 事件重算:12 筆(1.4%)在 6% 界翻面,絕對差 p90 0.375 pt。
spec 明訂當筆 state,所以 code 沒錯,只是這條和「即時判 0.7%」同量級卻沒同等待遇。
docstring 補三條:當筆價 vs 進場價、同伴 chg 即時快照 vs 10 s 格點、一檔多組聯集 vs 研究只留最後一組。
```

#### #33 glossary 的「掃單」層數公式漏了括號,字面讀成 群高 − (首價 ÷ 檔距)

**File**: `CONTEXT.md`
**Line**: 98

**Comment**:
```
CONTEXT.md:98「層數(群高 − 首價 ÷ 首價檔距,四捨五入)≥ 2」照運算優先序是 群高 − (首價 ÷ 檔距)。
code(signal_state.py:735)是 round((群高 − 首價) ÷ 首價檔距),signals_config.py:49 與 signal_state.py:698 的註解都寫對了,只有 glossary 漏。
改成「層數((群高 − 首價) ÷ 首價檔距,四捨五入)≥ 2」。
```

#### #34 「族群 vs 同群摘要」的差異只寫不扣 ALL IN,漏掉更常發生的那一項:同群摘要連盤前篩選也不扣

**File**: `CONTEXT.md`
**Line**: 108

**Comment**:
```
CONTEXT.md:105-109 族群那條寫「扣掉盤前篩選(恆)與設定排除的組名(預設 ALL IN)」,下面 _Avoid_ 的同群摘要只說「不扣 ALL IN」,
兩條並排讀會以為同群摘要至少扣了盤前篩選。signal_hub.py:735 _group_suffix 是 next(g for g in self._groups if code in g["codes"]),零排除;
盤前篩選 38 檔是最大組,同時在盤前篩選與族群組的檔印哪組全看自選檔的組序。改成「盤前篩選 / ALL IN 都不扣」。
```

#### #35 §0 目錄樹沒補新模組 server/signal_policy.py,§4 卻已經拿它當契約產生點

**File**: `CLAUDE.md`
**Line**: 60

**Comment**:
```
CLAUDE.md §4 寫「產生點 copycat/server/signal_policy.py::resolve_groups」,§0 那張 server/ 模組表沒這個檔;:60 的 signal_state 那行 kind 集合也還是舊的。
§0 是新 session 決定「政策判定住在哪」的唯一索引。:60 補「掃單簇」,server/ 表補一行 signal_policy(族群判定 + 四條政策純函式,零 IO)。
```

#### #36a 兩份 verification.md 的 commit 表 21 個 sha 全是 rebase 前的舊 sha,gc 後「哪筆是紅先行」查不到

**File**: `.claude/mod/signal-shadow-policies/verification.md`
**Line**: 23

**Comment**:
```
兩份 verification.md 的 commit 表(mod 版 15 個、followups 版 6 個 sha)全部是 PR rebase merge 前的分支 commit,
git cat-file 還在、merge-base --is-ancestor 全 NO —— 下一次 gc 就沒了。落地的是另一組(706e4b16→b66c072e、9f13b8c9→44665bd6…),subject 一對一,但沒任何文件記映射。
表頭加一欄 merged sha,或段首一行「本表 sha = rebase 前;落地見 git log 53d8f15c..60137dae 順序一一對應」;以後收尾鏈直接取 merge 後 sha。
```

#### #36b 兩份 verification.md 的 commit 表 21 個 sha 全是 rebase 前的舊 sha,gc 後「哪筆是紅先行」查不到

**File**: `.claude/bug/pr-199-review-followups/verification.md`
**Line**: 10

**Comment**:
```
同一件事:這六個 sha 也是 rebase 前的分支 commit,不在 master 祖先鏈,gc 後查不到。加 merged sha 欄(706e4b16→b66c072e、ae750d3b→380cbdaf、9f13b8c9→44665bd6…)。
```

#### #37 兩件證據的宣稱大於它們能證的:「curl 產物」其實是 Python 摘要,編輯窗截圖證不了「六類」與「min/max 值域」

**File**: `.claude/mod/signal-shadow-policies/evidence/sidecar-rules-curl.txt`
**Line**: 1

**Comment**:
```
verification.md:59 說 sidecar-rules-curl.txt 是「側車 GET /api/stock/signals/rules 同七條」,檔案內容卻是 `notify= False` 這種 Python print,
不是 curl 的 JSON,也沒留指令;CLAUDE.md §1 判準看的是 wire 欄 notify_discord,這份證據把欄名改寫掉了。
rules-dialog-sweep-edit.png 開來看:select 是收合態只顯示「掃單簇」,證不了「六類」;min/max 是 HTML 屬性,畫面上沒有。
curl 那份重錄成原始 JSON(或檔首補實際指令);§4 第三列的宣稱收斂成截圖真的看得到的兩句。
```

#### #38 同一 range 的兩份 round-1 json schema 不一致:mod 版每條只有 id/severity/finding,處置擠在一顆字串裡

**File**: `.claude/mod/signal-shadow-policies/code-review-round-1.json`
**Line**: 6

**Comment**:
```
兩份 code-review-round-1.json:followups 版每條 {id, severity, file, finding, fix, disposition, commit},mod 版 19 條只有 {id, severity, finding},
處置擠在頂層一顆 ~1.5 KB 的 disposition 字串,要複查任何一條都得先讀散文對 id、又沒有 file:line。內容核過是齊的。
mod 版比照 followups 版拆開,收尾鏈以後固定用後者 schema。
```

#### #39 這條的斷言只證得出「不再發」,證不出「不算第二個掃單」,主 seam 上該 AC 其實靠 golden 把關

**File**: `tests/server/test_signal_hub.py`
**Line**: 2328

**Comment**:
```
test_signal_hub.py:2328 這案名字說「同群後續 tick 不再發、也不算第二個掃單」,四條斷言(len 1 / price / levels / qty)只證前半:
group.fired 後 _eval_sweep 早退,重複登記的路走不到。把 signal_state.py:736 的 qualified 一次性守衛拿掉,hub 全綠、只有 golden 三案紅。
不算零覆蓋,但 #194 AC 把它列在主 seam。補一個 4 筆第一群 [50_000, 50_100, 50_200, 50_300](第 3、4 筆都達標)+ 第二群不成群,斷 h.published == [] —— 重複登記時 n30 變 2 就會發。
```

#### #40 「file_untouched」測的是內容不變,不是沒重寫,拿掉 if changed 守衛照綠

**File**: `tests/server/test_signal_outcome.py`
**Line**: 345

**Comment**:
```
test_signal_outcome.py:345 零補案只比 path.read_bytes() == before,而零補時 lines 沒動、b"".join(lines) 逐位元組等於原檔,
signal_hub.py:1331 `if changed:` 改 `if True:`(零補也 atomic 覆寫)照綠。docstring 契約「零補則不碰檔案」沒守門人。
改比 path.stat().st_mtime_ns,或 monkeypatch hub_mod.atomic_write_bytes 斷呼叫 0 次。
```

#### #41 三個 case 的 prefix 與 research 事件數逐案相等,「即時判多發 0.7%」在 fixture 裡零樣本,self-check 也不封上界

**File**: `tests/fixtures/record_sweep_cluster_golden.py`
**Line**: 42

**Comment**:
```
fixture 三案 expected_prefix 與 expected_research 事件數逐案相等(4/4、5/5、2/2),差異全是「發訊早於群末 / 層數低」,spec 講的「多發 60 個(0.7%)」零樣本。
test_fixture_self_check 只斷 research_ms ⊆ prefix 與 earlier 非空,兩條都不封多發上界 —— 定義改壞成大量多發、有人重跑 record 腳本重錄,self-check 仍全過。
V2 補一句:11 事件中 6 個 tuple 與 research 不同,偵測器改回「群結束才判」立刻紅,所以語意已釘住,缺的是 oracle 完整性。
擇一:CASES 從 sweep_prefix_scan.py 的 60 個多發樣本挑一個股票日;或 self-check 加 len(prefix) − len(research) ≤ 小常數。
```

#### #42 回填的逐檔間隔 basis_gap_secs 零覆蓋:harness 一律設 0,刪掉整段全綠

**File**: `tests/server/test_signal_outcome.py`
**Line**: 152

**Comment**:
```
test_signal_hub.py:332 harness 建 SignalsConfig 時硬寫 basis_gap_secs=0.0,signal_hub.py:1354-1355 `if basis_gap_secs > 0: await asyncio.sleep(...)` 在測試裡永遠不跑;
整段刪掉,test_signal_outcome + test_signal_hub 全綠。#196 AC 明列「逐檔間隔沿 CDP 基準 worker 的 gap」,一趟回填幾十檔沒 gap 就是對 TC4 連珠砲。
補一案 policy_outcome_days=1 + 兩個 code、basis_gap_secs=0.05,monkeypatch asyncio.sleep 斷每檔各睡一次。
```

#### #43 _run_policy_outcomes 的例外傘(worker 不因單趟失敗死掉)沒有任何測試

**File**: `tests/server/test_signal_outcome.py`
**Line**: 368

**Comment**:
```
signal_hub.py:1233-1239 _run_policy_outcomes 的 try/except 是「worker 不因單趟失敗死掉」的唯一保護,docstring 自己寫了死掉的後果(t1/t2 永遠 null、零訊號)。
測試裡沒有任何一案讓 backfill_policy_outcomes 本體拋 —— 現有失敗案全在 _fetch_outcome_bars 那層就被吃掉。
補一案:monkeypatch hub_mod.atomic_write_bytes 第一次拋 OSError,推時鐘到隔日 policy_outcome_time,斷 outcome_bars 第二趟有被打、log 有「未預期失敗(worker 續行)」。
```

#### #44 「不評政策」的守門只測參考價 None,ref ≤ 0 / 價 ≤ 0 零案;拆掉那半是熱路徑 ZeroDivisionError 被傘吞,測試不紅

**File**: `tests/server/test_signal_policy.py`
**Line**: 376

**Comment**:
```
signal_hub.py:1031 `if ref is None or ref <= 0 or price <= 0: return`,測試只餵 ref=None。改成只剩 `ref is None`,全量 467 綠。
ref == 0 型別上到得了(tc4common.to_milli_units("0") 回 0 不是 None;_quote_payload:1724 就是用真值判斷擋它),拿掉守門後 chg = price/0 拋 ZeroDivisionError →
被 _fanout 的 per-event 傘接住只留一行 ERROR,raw 列早就送出、政策列本來就該零 —— 所以只斷「零政策列」殺不掉,要連 caplog 一起。
補一案 _fire(h, _state(ref=0, upper=55_000)),在 caplog.at_level(logging.ERROR, logger="copycat.server.signal_hub") 內斷 _policies(h) == [] + kinds == ["sweep_cluster"] + caplog.text == ""。
```

#### #45 多族群 WARNING 的「一天一次」有測,「換日 / 移出自選後要再警告」沒測,兩個歸零點刪掉全綠

**File**: `tests/server/test_signal_policy.py`
**Line**: 437

**Comment**:
```
test_signal_policy.py:407-440 只斷「同檔同日只警告一次」,拿掉 signal_hub.py:666 的 _multi_group_warned.clear()(換日)與 :761 的 discard(code)(移出自選)反而更符合這條斷言,全綠。
失效只是長跑 server 跨日後再也不提醒族群設定重疊。比照 TestPeersFnFailure:775-781,案尾加 h.hub.on_rollover() + 再發一顆,斷 count("多個族群組") == 2。
```

#### #46 新 kind 的 route 往返案缺席,而上一個新 kind(surge_pullback)有先例

**File**: `tests/server/test_signal_routes.py`
**Line**: 59

**Comment**:
```
test_signal_routes.py:43 import 共用 _RULE_PARAMS(F-39)的理由是「複製件少補 sweep_cluster 時 _rule_body 一寫就 KeyError」,但整檔 16 個 _rule_body 呼叫沒一個傳 "sweep_cluster"。
同 class :597 test_post_surge_pullback_round_trips 就是為上一個新 kind 補的(pr-177 F-03),掃單簇是同一類。
照那條複製:body 換 _rule_body("sweep_cluster", "掃單簇 2"),斷 kind、params 五鍵精確、cdp_levels == []。
```

#### #47 只有 hover 才看得到的 policyTitle 每次 render 都整串組出來,而 rail 沒 memo 邊界 —— 但同檔更重的同 pattern 長期存在

**File**: `frontend/src/components/stock/SignalRail.tsx`
**Line**: 282

**Comment**:
```
不是 PR 缺陷。C2 擔心 policyTitle 在每次 render 組整串 hover 字串(rail 無 memo、每 0.1 s tick 打包重繪);
V2 找到同檔 :269 ruleTitle 對 rail 每一組每一個規則名都做 [...items].reverse() + Set,比 policyTitle(一天只 25 個政策組)重得多,長期沒被當效能問題。
答不出「為什麼政策列會炸而 ruleTitle 不會」,列參考;真要收,方向是整條 rail 抽 memo 子元件,不是只動這行。
```

## CC 主軸原始 findings(first-pass, context-aware)

### Section A — findings(六軸,逐字濃縮;原文在各 agent 回傳;每條含 anchor / severity / 主張 / search-proof 摘要)

#### C1

```text
# C1 後端 source(python-reviewer, opus)— 11 findings: MED 3 / LOW 8;fileio.py REVIEWED_NO_ISSUES
C1-F1 MED signal_hub.py:703-715 群組讀取失敗 log 只講「同群摘要」,但 self._groups 也是族群唯一來源;失敗/首次 on_watchlist 前 → P/B 全不評、S 只在篩選成員活,零訊號。修:log 點名兩消費者或早退加當日一次 WARNING。anchor: `            logger.exception("群組結構讀取失敗,同群摘要沿用上一份(%d 組)", len(self._groups))` spec: 族群定義 / story 31
C1-F2 MED signal_hub.py:1220-1224 start 那一趟回填零延遲連發 DK,與 CDP 基準暖機搶 api.lock(全域序列化);估 15–40 檔 × DK + 0.2 s gap,撞開盤前自啟窗;價值零時效。修:延後或只在 _past_time 成立時立即跑。anchor: `        await self._run_policy_outcomes()` 數字為估算。
C1-F3 LOW signal_hub.py:1253-1255 data/signals/ 不存在整趟零 log,分不出 worker 沒跑 vs 沒東西補。anchor: `        if not signal_dir.exists():`
C1-F4 LOW signal_hub.py:1050-1056 複查 std F-09:當日一次旗標無計數,第二次後失敗零痕跡;降級 = quotes={} → P/B 全不評只剩 S。修:計數器 + _DROP_LOG_EVERY 節流(hub 既有慣例)。anchor: `                    logger.exception("政策行情快照讀取失敗,視為同伴無報價(當日只印一次):%s", code)`
C1-F5 MED signal_policy.py:91-115 policy_exclude_groups 組名對不上任何群組零訊號;user 改名 ALL IN(prod 無 configs/signals.json)→ ALL IN 靜默變族群(研究 −1,471/筆)、污染影子期。修:載入時 exclude 名零命中 WARNING 一次。anchor: `            if name in exclude:` spec: story 14 / R1 / §8.2
C1-F6 LOW signal_state.py:709-713 tick_secs 解析失敗退回牆鐘 mono(1.78e9)混入 sweeps deque → 該筆永不過期、min_sweeps 悄降 1;lookback 半邊自癒;目前不可達(_taipei_time 恆 HH:MM:SS.fff);docstring 觸發條件(空字串)寫錯。修:secs None → return []。anchor: `        if secs is None:\n            secs = mono`
C1-F7 LOW stock_engine.py:763-796 policy_quotes(codes=None) 整份自選分支零生產呼叫者;TestPolicyQuotes 11 呼叫點 10 個走 None,prod 分支只 1 案。修:codes 必填。anchor: `        picked = self._watchlist if codes is None else list(codes)`
C1-F8 LOW app.py:839-842 groups_fn 注入處註解「漏接失效 = 通知少一段尾巴」已失真(現在 = P/B 全不評);_refresh_groups docstring 同。anchor: `                    # 都輕同步,不進熱路徑。漏接的失效樣態是「通知少一段尾巴」而已,`
C1-F9 LOW signals_config.py:53-61,72-77 policy_exclude_groups 型別錯 = 裸 AssertionError 無訊息、元素非 str 靜默;policy_outcome_days ≤ 0 → dated[:0] 恆空、每趟印「本趟零列」看似正常。修:進 SignalHub.__init__ 驗證迴圈(F-06 開好位置)。anchor: `        tuple_keys=("policy_exclude_groups",),`
C1-F10 LOW signal_rules.py:445-452 複查 F-16:滿 30 條分支未接 skip_note(同 C3b-F8)。anchor: `        logger.warning("訊號規則檔 %s:規則數已達上限 %s,跳過種子卡 %r", tag, MAX_RULES, name)`
C1-F11 LOW signal_rules.py:507-518 回退手順未寫「退 v3 再升 v4 翻旗重跑」→ 使用者改回的通知被第二次遷移靜默再關。anchor: `    - 退到 v3:刪掉「掃單簇」種子卡、把 cdp_cross / vol_burst 規則的 \`notify_discord\` 改回`
面 2 結論:evaluate_policies ↔ group_feats 逐條同義;差異三處不構成 finding:(a) chg 當筆價 vs 進場價(spec 明訂當筆 state);(b) chg round 2 vs 不 round(±0.005 帶內);(c) 同伴 chg 即時 vs 10 s 格點。to_limit_pct / pct 不 round 非問題(不進判定)。locked_up 加賣側空不進政策條件。即時判逐行對 clusters_prefix 等價;tick_size 分段同;冷卻軸牆鐘 vs tick 時刻 <1 s(docstring 已寫)。
面 4 結論:on_tick → _emit_policies 全程同步零 await 零 IO;peers_fn 每顆 sweep_cluster 事件恰一次(detail 非 None 且 peer_codes 非空);出口序 WS → jsonl → Discord → _policy_touch(計數最後,F-04 收修正確);任一拋 → 傘吞、該政策及其後政策不落列不計數(自洽);raw 列先於政策列入列 → 佇列滿先丟 raw,jsonl 可能「有政策列無 sweep_cluster 列」(政策列自帶 sweep 欄可對帳;09-07 佇列滿 0)。
```

#### C2

```text
# C2 前端(typescript-reviewer, opus)— 10 findings: MED 3 / LOW 7;5 檔 REVIEWED_NO_ISSUES
C2-F1 MED signal-model.ts:290-293 policyContextText 無族群 S 列第三行印「同伴≥3% 0・鎖過 無」,與 hover / Discord「盤前篩選名單・無族群濾網」矛盾;真資料 S 22 中 16 無族群(9 notify=true)。anchor: `export function policyContextText(sig: SignalMsg): string {` spec: 前端節第三行字面(code 合規,實資料回饋)
C2-F2 MED SignalRail.test.tsx:583-585 quiet 淡色 `every`→`some` 突變 41 綠;prod 每則政策列都是混合組(政策 notify=true + raw notify=false)。anchor: `expect(items[0]?.className).toContain("opacity-50");` 產生點 SignalRail.tsx:185-187
C2-F3 MED useSignalAlerts.test.tsx:718-725 合併分支雙嗶 `if (firstPolicy) beepFor(true)`(useSignalAlerts.ts:234)整行刪 44 綠;user 開掃單簇通知時政策列雙嗶只能由此發。anchor: `it("同 tick 兩條政策 → 一張 toast、標記並列;第二則併入不再嗶", () => {`
C2-F4 LOW useSignalAlerts.test.tsx:710-716 SECOND_BEEP_OFFSET_S 改 0 全綠;fake createOscillator start 丟參數。anchor: `it("政策列 → toast 帶標記、嗶兩聲", () => {`
C2-F5 LOW signal-model.ts:104-106 複查 F-11:pct=0 前端「掃單簇 0.00%」後端「掃單簇 +0.00%」,缺 pct 前端「掃單簇」後端「+0.00%」;F-11 否決理由只答小數位未答正負號;up_pct 下限 0 可達。anchor: `function sweepLabel(pct: number | null): string {`
C2-F6 LOW signal-model.ts:307-309 policyTitle 的 when 段取 anchor 單列 first_of_day,同 tick 兩政策一真一假時 hover 誤述(latent;真資料 4 組同 tick 目前一致)。anchor: `const when = [sig.tod, sig.first_of_day ? "首筆" : sig.first_of_day === false ? "非首筆" : "", sig.late ? "late" : ""]`
C2-F7 LOW signal-model.ts:283-285 / 299-301 複查 S-02:peer_touched 仍 `=== undefined`(null → 印「無」);policyTitle peer 迴圈 `=== null` 三元 dead(pct1 已處理)。anchor: `const up = sig.peers_up ?? "-";`
C2-F8 LOW SignalRail.tsx:280-283 policyTitle 每 render 組整串(hover-only),rail 無 memo、StockPage 每 ticks 打包重繪;方向 memo 子元件 / 惰性 title。anchor: `title={policyTitle(anchor, tags)}`
C2-F9 LOW SignalRulesDialog.tsx:74-76 舊 dist 配新後端:規則視窗對「掃單簇」列按編輯 toForm PARAM_FIELDS[kind] undefined → TypeError(onClick 內,點了沒反應);spec Backward compat 括號只涵蓋訊號列。anchor: `for (const field of PARAM_FIELDS[rule.kind]) {`
C2-F10 LOW signal-model.test.ts:3-14 groupPolicyAnchor「最早到」契約零測試(改取末筆 131 綠)。anchor: `groupKindLabels,`
REVIEWED_NO_ISSUES: useSignalAlerts.ts / useSignalRules.ts / signal-params.ts / signal-param-parity.test.ts / SignalRulesDialog.test.tsx(F-22 收修到位)
面 5 結論:訊號列退化路徑乾淨(shouldNotify !== false 三態釘住、kindLabel 未知回原字串、缺欄一律 `-`、無 NaN/undefined/"null");破口只在規則視窗(C2-F9)與零值正負號(C2-F5)。
突變體:beepFor 合併分支刪 / every→some / offset→0 / anchor 取末筆 四個存活(主 tree 實跑、已還原);tsc / eslint / 166 tests 綠。
```

#### C3a

```text
# C3a 後端測試前半(python-reviewer, opus)— 8 findings: MED 3 / LOW 5;baseline 224 passed;突變全還原
C3a-F1 MED test_signal_outcome.py:263-275 「只碰過去日」只釘 hub 日別超前那半;M2 `cutoff = self.today`(拿掉 hub 半)177 綠。常態路徑 = 午夜後~當日首 tick 前 hub 日別=昨日、牆鐘=今日,昨日檔正是 _append_jsonl 還在寫的檔 → 整檔覆寫會蓋掉 append 列。anchor: `async def test_hub_date_ahead_of_wall_clock_keeps_wall_day_untouched(` spec: #196 AC 只碰過去日
C3a-F2 MED test_signal_hub.py:2291-2326 簇窗閉區間 / 回看基準 ≤ 兩界零樣本;M3 `<`→`<=`(signal_state.py:744)240 綠、M4 `<=`→`<`(:719,:748)240 綠;golden 三案也無 30/60 s 整差樣本。anchor: `async def test_sweeps_outside_cluster_window_do_not_count(` spec: Implementation Decisions 閉區間
C3a-F3 MED test_signal_state.py:700-733 掃單簇軸零 session gate / 舊日 gate 測試(_ALL 不含 sweep_cluster);M6 兩道早退改成掃單簇照跑 203 綠;_eval_sweep 已刻意上移至首 tick gate 前,再上一格無測試紅;收盤撮合同毫秒群可造假簇。anchor: `class TestSessionGates:` spec: #194 09:00–13:30 閘沿既有
C3a-F4 LOW test_signal_hub.py:2328-2356 「同群不算第二個掃單」主 seam 斷言證不出;M1 群內每達標筆都登記 → hub 全綠、只 golden 3 紅。anchor: `async def test_first_qualifying_tick_fires_and_group_counts_once(` spec: #194 AC
C3a-F5 LOW test_signal_outcome.py:345-353 「零補不碰檔案」只證內容不變;M7 `if changed:`→`if True:` 21 綠。anchor: `async def test_empty_bars_leaves_null_and_file_untouched(`
C3a-F6 LOW record_sweep_cluster_golden.py:41-46 三案 prefix == research 事件數(4/4, 5/5, 2/2),「即時判多發 0.7%」零樣本;self-check 只封 ⊆ 與 earlier 非空、不封多發上界(重錄路徑削弱)。anchor: `CASES: tuple[tuple[str, str], ...] = (` spec: #194 AC 含即時判差異的已知列表。重跑腳本 byte-identical。
C3a-F7 LOW test_signal_outcome.py:152-154 basis_gap_secs 零覆蓋(harness 硬寫 0.0);M5 刪 gap 段 140 綠。anchor: `def _harness(tmp_path: Path, clock: _Clock, bars: _FakeDayBars | None, **over: Any) -> _Harness:` spec: #196 逐檔間隔沿 CDP gap
C3a-F8 LOW test_signal_outcome.py:368-392 `_run_policy_outcomes` 例外傘(worker 不死)零測試。anchor: `class TestSchedule:`
REVIEWED_NO_ISSUES: signal_param_specs.json / sweep_cluster_golden.json(重跑 byte-identical)
參考碼比對:find_sweeps_final / clusters_final 與研究 combo_events.py find_sweeps + sweepc 段逐條相同(price[j]>p0 / ask[i]>0 / p0>=ask[i]-1e-9 / tick_size(p0) / bisect 含界 / 60 s 去重);load_rows 與 combo_panel.py:128-139 同;tick_size 與 market.py::_ZONES 逐段同。
F-23..F-32 收修複查全成立。
突變流水 M1–M7(全還原);環境備註:平行 reviewer 在同棵 worktree 動 signal_policy.py(locked_up_flag 拿掉 _best_limit_price is None)—— 並行突變互污染風險,M3/M4 期間可能受影響。
```

#### C3b

```text
# C3b 後端測試後半(python-reviewer, opus)— 8 findings: MED 5 / LOW 3;baseline 570 passed;突變全還原
C3b-F1 MED test_signal_policy.py:254-267 under_cap `<`→`<=` 177 綠;chg 已 round 2,恰 6.0 是整數格。補案(已實跑殺):ref=47_547 → chg 6.0、groups=[_MEM,_SCREEN]、peer 1.0 → []。anchor: `            assert _policies(h) == ["B-b"]` spec: P/B-a/S chg < 6
C3b-F2 MED test_signal_policy.py:234-252 leader `>=`→`>` 177 綠;平手常態(兩邊 round 2);研究 _leader 含平手。補案:ref=48_932 → chg 3.0 + peer 3.0 → ["B-a","B-b"]。anchor: `            assert _policies(h) == ["B-a", "B-b"]`
C3b-F3 MED test_signal_policy.py:179-184 複查 round-1 std F-01(HIGH):chg round 2 修正零回歸保護(拿掉 round 177 綠)。補案:ref=48_933(2.99797→3.0)+ peer 3.0 → self.chg_pct [3.0,3.0] 且 ["B-a","B-b"]。anchor: `            assert msg["self"] == {`
C3b-F4 MED test_signal_policy.py:369-382 守門去掉 `ref <= 0 or price <= 0` 177 綠;ref=0 真實可達(to_milli_units("0") 回 0);失效 = ZeroDivisionError 被 _fanout 傘吞、只留 ERROR log、raw 列仍在 → 只斷零政策列殺不掉,補案要連 caplog.text == "" 斷。anchor: `            _fire(h, _state(ref=None, upper=None))` spec: #195 參考價缺或價 ≤ 0 不評
C3b-F5 LOW test_signal_policy.py:407-440 _multi_group_warned 兩個歸零點(on_rollover :666 / drop :761)刪掉 156 綠;只影響可觀測性。anchor: `            assert caplog.text.count("多個族群組") == 1  # 同檔同日只警告一次`
C3b-F6 MED test_stock_engine.py:1427-1443 locked_up「限價賣側空」半邊零釘(去掉 `_best_limit_price(asks) is None` 362 綠);第二筆同時改價與賣側;影響 self/peers.locked_up 對帳欄。補案:第三筆 price=2550 ask=2550 → locked_up False。anchor: `        src.on_message(_quote(cum=2, price="2545", bid="2545", ask="2550"))` spec: 當下鎖死 = 現價 = 漲停且限價賣側空
C3b-F7 LOW test_signal_routes.py:43/59-60 F-39 共用 _RULE_PARAMS 後整檔零 caller;新 kind route 往返案缺(先例 test_post_surge_pullback_round_trips)。anchor: `# 各 kind 的合法參數表直接沿 \`test_signal_hub._RULE_PARAMS\`(review F-39):複製件少補 sweep_cluster 時`
C3b-F8 LOW test_signal_rules.py:934-945 複查 F-16:skip_note「零政策列」只串撞名分支,滿 30 條分支(signal_rules.py:451)沒有;測試釘住弱版本。anchor: `        assert caplog.text.count("v3→v4:規則數已達上限 30,跳過種子卡") == 1`
REVIEWED_NO_ISSUES: test_stock_routes.py / test_signals_config.py
殺掉的突變:late `>=`(1 failed)、peers_up `>`(3 failed)。
AC 無覆蓋:#195 價 ≤ 0 兩半;#193 route 往返;#193 十二鍵覆寫案只 5 鍵(loader 通用已釘,備查)。
```

#### C4

```text
# C4 文件契約(code-reviewer, opus)— 7 findings: MED 2 / LOW 5;16/16 accounting(6 no-issues, 2 skipped)
C4-F1 MED .claude/mod/signal-shadow-policies/verification.md:8-24 + .claude/bug/pr-199-review-followups/verification.md:10-17 兩份 commit 表 21 個 sha 全是 rebase 前分支 sha(存在但不在 60137dae 祖先鏈),gc 後消失;落地 sha 1:1 對得上(706e4b16→b66c072e 等)但無映射記錄。anchor: `| \`8c9802b5\` | review r1 | 🔵 | PeerQuote TypedDict / 旗標 helper 共用 / arrivalOrder / 折行 |`
C4-F2 MED .claude/skills/tc4-market-facts/SKILL.md:74-75 新 bullet 稱「鎖停日 ask 市價佇列 0、derive_side 判 outer」故不用 tick.side —— 但 ask_milli 由 _best_limit_price 濾掉市價佇列(0 → None),同 skill §鎖漲跌停寫鎖漲停判 neutral;tick.side=="outer" 與 ask>0 and price>=ask 在 prod 等價;真正理由是與研究 find_sweeps 逐字對齊(研究 tick 檔保留 Ask=0)。anchor: `  (鎖停日 \`ask\` 是市價佇列 0,\`derive_side\` 會判 outer,研究要求 ask > 0)。**即時判(群內首次達標即發)vs 群結束才判**:`
C4-F3 LOW CONTEXT.md:98 層數公式漏括號(= D1-F5)。anchor: `的成交、層數(群高 − 首價 ÷ 首價檔距,四捨五入)≥ 2。一筆主動買單一次吃掉多檔賣單的痕跡。`
C4-F4 LOW CONTEXT.md:105-109 「族群 vs 同群摘要」差異只寫不扣 ALL IN,漏「也不扣盤前篩選」(_group_suffix 零排除;盤前篩選 38 檔最大組)。anchor: `_Avoid_: 同群摘要(Discord 尾巴的「同群」取群組序第一個含它的組,不扣 ALL IN —— 另一把尺,只是通知裝飾)、`
C4-F5 LOW CLAUDE.md:60,76 §0 目錄樹沒補 server/signal_policy.py、live 行 kind 集合未列掃單簇;§4 已以它當產生點。anchor: `│                         #   個股訊號:signal_state(CDP 穿越/爆拉跌/爆量/鎖板,零 IO)`
C4-F6 LOW verification.md:59,61 + evidence/sidecar-rules-curl.txt:1 + rules-dialog-sweep-edit.png 「curl 產物」是 Python 摘要(notify= False 非 wire 欄 notify_discord);編輯窗截圖證不了「六類 select」「min/max 值域」;list.png 相符。anchor: `CDP 穿越 cdp_cross enabled= True notify= False cooldown= 600`
C4-F7 LOW .claude/mod/signal-shadow-policies/code-review-round-1.json mod 版 schema 每條只 id/severity/finding、無 file 錨、處置擠一顆字串;followups 版 per-finding 有 file/disposition/commit。anchor: `  "id": "F-01",\n  "severity": "HIGH",`
REVIEWED_NO_ISSUES: followups round-1.json / fake_server.py(複查 F-05 PASS,從 C:\ 實跑)/ migration-dry-run.txt / rules-dialog-list.png / sidecar-startup-log.txt / vite.sidecar.config.ts(複查 F-05/F-06 PASS)
INTENTIONALLY_SKIPPED: pr-199-review.md / .audit.md(review 產物;抽查 11 條 auto-fix 全落地)
五契約 PASS:notify(prod 479 列零缺欄、公式 0 例外)/ 政策列形狀+id 逐字 / parity(措辭偏差 `_eval_sweep 必須` vs 實走 evaluate,不列)/ 回填 cutoff=min(hub, wall) 逐字等 / 族群排除。§1 判準全實跑可得(policy 29、佇列滿 0、13:40「共回填 0 列(掃 5 個日檔)」預期)。
gate 複驗:4 次 pytest,3 次 3494 passed 3 skipped;第 1 次 golden 三紅 = 自身 __pycache__ 干擾(存證,不列)。
```

#### D1

```text
# D1 spec 語意對帳(code-reviewer, opus)— 5 findings: MED 2 / LOW 3
story 1–32:30 符合 / 2 部分(18、27)/ 0 不符;W1–W12 12/12 PASS(W1 真列 key tuple 20260902 14 鍵 → 20260907 15 鍵只多 notify 序不動;W4/W9 format_signal_group_text / _group_suffix / _split_batches 零 hunk;W10 start():542 進 _tasks → close():563-567)
面 2 差異四條:(1) 即時判 0.7%(已落檔);(2) chg 線上當筆價 vs 研究進場價(下一筆 +1 檔),865 事件 p50 0 / p90 +0.361 / 範圍 [−1.135,+1.422] pt,12/865=1.4% 在 6% 界翻面(未落檔);(3) 同伴 chg 研究 10 s 格點 vs 線上即時(未落檔);(4) 多組:研究 code2grp 留最後一組 + ALL IN 整筆丟 vs 線上聯集 + 逐組排除(未落檔,09-07 groups 長度皆 ≤1)。鎖過閘只看同伴 = 同義(研究 _locked_before 本就只掃 peers)。locked_up 加賣側空:零影響(非政策輸入)。線上 P ↔ §8.2 第二列(排除 ALL IN n=36);S 三列不可對照(研究以面板特徵近似)。
面 3:§8.3 三桶足夠;§8.2 n / 同檔一筆 / tod / 三門檻重算可只讀 jsonl;「每筆」「鎖死」不可(需 13:20 價;漲停價可由 to_limit_pct 還原)。
D1-F1 MED signal_hub.py:1077(對象 = 對帳基準)§8.2 表「12:30 前」= combo_wlpolicy.py:41 `df.tod < 1230`,tod 是字串桶 pandas 讀成 int 恆真 → 表含 65 筆 late=1;改 late==0 後「排除 ALL IN」列 36/+5,497/22% → 35/+5,784/23%。建議 HANDOFF §8.2 加註或改 combo_wlpolicy.py 重出。anchor: `        late = secs is not None and end_secs is not None and secs > end_secs`
D1-F2 MED signal_hub.py:1093-1097 nosig.py:52 `own` 無 kind 白名單 → 三桶分群靜默換尺,glob 整目錄 → 09-07 前後兩把尺;契約「不新增列型」擋不住此類讀者。建議契約改寫 + nosig.py 補白名單。anchor: `                "type": "signal",` (實跑 signal_join / nosig 不炸)
D1-F3 LOW signal_hub.py:1315-1325 回填只補 T+1/T+2 open;事件日 13:20 價 / 收盤 / 當日高不在列 → story 18「直接讀 jsonl」只成立一半;建議 (a) 文件補句 (b) worker 順手補事件日 bar close/high。anchor: `                after = [b for b in bars if b["t"] > date]`
D1-F4 LOW signal_hub.py:1057-1059 chg 口徑差(當筆價 vs 進場價,1.4% 翻面)未落任何文件;建議 signal_policy.py docstring 補三條差異。anchor: `        chg = round((price - ref) / ref * 100, 2)`
D1-F5 LOW CONTEXT.md:96-98 glossary 層數公式漏括號「群高 − 首價 ÷ 首價檔距」;signals_config.py:49 / signal_state.py:693 有括號。anchor: `的成交、層數(群高 − 首價 ÷ 首價檔距,四捨五入)≥ 2。`
story 30 表面不符(S 無同伴報價仍評)但 Implementation Decisions / #195 AC 寫明 P/B 另要求 peers_quoted ≥ 1 → 一致。
```

### Section B — per-file accounting(47/47)

| chunk | 檔數 | 有 finding | REVIEWED_NO_ISSUES | INTENTIONALLY_SKIPPED |
|---|---|---|---|---|
| C1 後端 source | 8 | 7(fileio 以外) | 1(`copycat/fileio.py`) | 0 |
| C2 前端 | 11 | 6(SignalRail.tsx / SignalRail.test.tsx / SignalRulesDialog.tsx / useSignalAlerts.test.tsx / signal-model.ts / signal-model.test.ts) | 5(useSignalAlerts.ts / useSignalRules.ts / signal-params.ts / signal-param-parity.test.ts / SignalRulesDialog.test.tsx) | 0 |
| C3a 後端測試前半 | 6 | 4(record_sweep_cluster_golden.py / test_signal_state.py / test_signal_hub.py / test_signal_outcome.py) | 2(signal_param_specs.json / sweep_cluster_golden.json) | 0 |
| C3b 後端測試後半 | 6 | 4(test_signal_policy.py / test_signal_routes.py / test_stock_engine.py / test_signal_rules.py) | 2(test_stock_routes.py / test_signals_config.py) | 0 |
| C4 文件契約與產物 | 16 | 8(mod verification.md / followups verification.md / mod round-1.json / SKILL.md / CLAUDE.md / CONTEXT.md / sidecar-rules-curl.txt / rules-dialog-sweep-edit.png) | 6(followups round-1.json / fake_server.py / migration-dry-run.txt / rules-dialog-list.png / sidecar-startup-log.txt / vite.sidecar.config.ts) | 2(pr-199-review.md / .audit.md —— 已審過的 review 產物;抽查 11 條 auto-fix 全落地) |
| **合計** | **47** | **29** | **16** | **2** |

`MISSED = F − accounted = ∅`;coverage repair 輪未觸發。D1 domain reviewer 的 per-file 標記不計入(domain reviewer 不參與 coverage 算術)。

## Codex 原始 findings

N-A —— user 明示停用 Codex 中性 / 對抗兩軸(沿 #188 / #190 / #199 前例),零 finding。

## Gemini 原始 findings

N-A —— user 明示停用 Gemini Flash / Pro,零 finding。

## CC 對非 CC 軸的複查結果(Step 4.1)

N-A —— 無非 CC finding 可驗。

## 內部複查結果(Step 4.2 之替代;同軸 code-reviewer、非跨軸證據)

兩批並行(V1 = C1 / D1 / C4 共 22 條;V2 = C2 / C3a / C3b 共 25 條),各自獨立 detached worktree(`review-range-192-v1` / `-v2`,同 SHA),前端突變在主 tree 序列做並逐檔還原;ID 集合各精確相等、每列 verdict / corrected_severity / severity_reason / evidence / lone_note 五欄齊。V2 對 17 個建立在「突變體全綠」上的主張**序列重跑**並各加一次全量(後端五支測試檔 467 / 前端 2381):16 存活、1 被 golden 殺(C3a-F4 M1);結果與 first-pass 逐條一致,C3a 自報的「並行互污染」疑慮**未成立**。

分佈:CONFIRMED 35 / PARTIAL 11 / REFUTED 1 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0;校正後 severity CRITICAL 0 / HIGH 0 / MEDIUM 13 / LOW 34(first-pass MEDIUM 17 → 校正後 13:降級 C1-F1、C4-F1、C2-F1、C2-F3、C3b-F4;升級 0)。

| # | axis id | verdict | 原 → 校正 severity | 摘要 |
|---|---|---|---|---|
| F-01 | D1-F1 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V1 逐格重算 events.csv:sweepc 865、tod ∈ {900…1200} 全 <1230、late=1 65 筆;「排除 ALL IN」列 tod<1230 = 無濾網 = 36/+5,497/22%,late==0 → 35/+5,784/23%;其他列同向修正、無拍板翻面 |
| F-02 | C3a-F1 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑 M2 全量 467 passed / 0 failed;CLAUDE.md 明載 trade_date 空自選 / 零推播停在昨日,`_append_jsonl:983/1006` 用同一顆 `_trade_date_fn` → 13:40 `atomic_write_bytes:1332` 會整檔覆寫仍在 append 的檔 |
| F-03 | C1-F5 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V1 以 events.csv 原地驗 ALL IN 當族群 n=10 / −1,471(事件級 16 / −3,605)逐字符 §8.2;緩解 = 政策列自帶 `groups` / `peers`、卡面第三行印族群(非全盲);spec story 14 把改名→改設定寫成 user 流程 → 結論是載入期補一則 WARNING |
| F-04 | C3a-F2 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑 M3 / M4 各全量 467 passed(含 golden 三案);真資料 20260907 的 75 列 sweep/policy 時刻鍵 100% `.000`(全檔 479 只 2 列非 .000)→ 恰差 30 / 60 s 是常態不是邊角 |
| F-05 | C3a-F3 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑 M6 全量 467 passed;golden 殺不掉因 record 腳本 :65-67 自己加了 [09:00, 13:30) gate;F-25 收修紀錄「三案各只掉 13:30:00.000 收盤撮合一筆」= 收盤同秒大群實證 |
| F-06 | C3b-F3 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑刪 round 全量 467 passed;既有 ref=50_000 → 0.8 兩邊一樣;實算 ref=48_933 → 2.997977,round 後 3.0(leader True)、不 round 2.998(False)→ 一案可釘 `self.chg_pct` 與 B-a/B-b |
| F-07 | C3b-F1 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑 `<=` 全量 467 passed;既有 ref=47_000 → 7.23 離界 1.23;實算 ref=47_547 → 6.000379 → round 6.0,`<` False / `<=` True → 補案可殺 |
| F-08 | C3b-F2 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑 `>` 全量 467 passed;實算 ref=48_932 → 3.000082 → 3.0 與 peer 3.0 平手 → 補案可殺;研究 `group_feats` `_leader = int(self_chg >= mx)` 含平手 |
| F-09 | C3b-F6 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑全量 467 passed;`locked_up` 不進任何政策條件(`evaluate_policies` 只讀 `touched_upper`),純 jsonl 快照欄(story 16)→ 對帳錯非漏發錯 |
| F-10 | C1-F2 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V1 核 tc4.py:547-562 `_req` 每發都 `api.lock.acquire`、`_collect_history` 同鎖;量測 prod 五日檔待補 = 20260907 29 列 / 15 相異 code → 首跑 15 次 DK ≈ 5–18 s(stock_source.py:752 probe 0.02–0.98 s)≈ 150 檔基準 sweep 10% 延後;風險窗 = 接近 09:00 才啟動 |
| F-11 | D1-F2 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V1 逐行確認 :52 / :53 兩把尺、:13 glob 整目錄;現況尚未爆(fills.json 最後 2026/09/03),影子期 fills 進來才發作;CLAUDE.md §4「不新增列型」對不做白名單的讀者無保護力 |
| F-12 | C4-F2 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V1 核 stock_models.py:149-151 / :221-222 / 歷史 :256-258 全把 0 歸 None;`derive_side:103-105` outer 分支逐字 = `_eval_sweep:725` 去掉死條件 `ask > 0`;研究 `pull_ticks.py:63` 保留原始 Ask=0 才需要 `ask[i] > 0` |
| F-13 | C2-F2 | CONFIRMED | MEDIUM→MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):V2 序列重跑 every→some 主 tree 全量 2381 passed;真資料 25 個政策組中 15 組混合、cdp_cross 155 全 quiet 與 surge 混組更普遍 → some 讓多數列變淡色,story 9 的降噪反轉 |
| F-14 | C2-F1 | CONFIRMED | MEDIUM→LOW | CONFIRMED(校正 LOW;原 MEDIUM):V2 真資料實查同數;緩解 = 同列 S chip + hover 全文正確 + `groups=[]` 已落 jsonl → 事後重算不受害;code 合規 spec 字面 |
| F-15 | C2-F3 | CONFIRMED | MEDIUM→LOW | CONFIRMED(校正 LOW;原 MEDIUM):V2 序列重跑刪行全量 2381 passed;真資料 25 政策組中「有 notify=true 非政策同伴」= 0 → 現況零踏到;要踏到需 user 開掃單簇通知或同秒撞 surge |
| F-16 | C2-F4 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V2 序列重跑 offset→0 全量 2381 passed;根因如述 |
| F-17 | C2-F5 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V2 兩邊實測(後端 .venv 直跑、前端一次性 probe)結果如述;裁定 C4 契約 2 的 PASS 只在預設組態成立,`up_pct=0` 時 session 前 60 s 窗前無成交會產 `up_pct=0.0`;兩軸相容 |
| F-18 | C2-F6 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V2 真資料四組(4979 / 6213 / 3105×2)`first_of_day` 皆一致;分岔路徑存在(S 母體寬、早盤先單獨命中一次後再與 P 同 tick) |
| F-19 | C2-F7 | PARTIAL | LOW→LOW | PARTIAL(校正 LOW;原 LOW):V2 核後端 `peer_touched` 恆 bool(signal_policy.py:87 / hub :1119)、`peers_up` 恆 int → null 不可達;dead 三元屬實;純一致性 |
| F-20 | C2-F9 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V2 核 `PARAM_FIELDS: Record<RuleKind,…>` 型別 total map、runtime 新 kind = undefined;`ruleSummary:96-116` 有 fallback、`toForm` 無;下一次加 kind 原樣重演 |
| F-21 | C2-F10 | PARTIAL | LOW→LOW | PARTIAL(校正 LOW;原 LOW):V2 序列重跑取末筆全量 2381 passed;同事件各政策列除 policy/id/touch_count/first_of_day/notify 外欄位相同 → 第三行輸出逐字相同,差異只在 C2-F6 hover |
| F-22 | C1-F1 | PARTIAL | MEDIUM→LOW | PARTIAL(校正 LOW;原 MEDIUM):V1 核 `app.py:854` `load_watchlist` 在 `on_watchlist` 之前求值、不在 hub try 內 → 壞檔先在 `_boot` 大聲停用整顆 hub;後續 `on_watchlist` 失敗只沿用舊值;缺檔回空 dict 不拋;成立只剩 log / docstring 漏族群消費者(與 C1-F8 同根) |
| F-23 | C1-F8 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V1 核 app.py:839-842 逐字仍如此、`signal_hub.py:704-708` 同;與 C1-F1 同根因,收修一起改 |
| F-24 | C1-F3 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V1 核 prod 目錄已有 15 個日檔恆在,只全新安裝 / 換 data_dir 第一天可達 |
| F-25 | C1-F4 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V1 核旗標只 `on_rollover:667` 復位;`peers_fn` = `engine.policy_quotes` 純記憶體讀,拋例外等於已有別的 bug → 觸發機率低 |
| F-26 | C1-F6 | PARTIAL | LOW→LOW | PARTIAL(校正 LOW;原 LOW):V1 探針實跑(tick.time="bogus")deque 長度 2→3→4 永不修剪,後果比 first-pass「min_sweeps 降 1」更重(簇窗整個失效);prod 不可達(`_taipei_time:89-95` 恆 HH:MM:SS.fff);docstring 確寫錯 |
| F-27 | C1-F7 | PARTIAL | LOW→LOW | PARTIAL(校正 LOW;原 LOW):V1 核 10:1 比例正確,但 :776-798 per-code 組裝兩路共用,None 分支獨有只名單來源 → 「prod 分支只 1 案」在覆蓋意義上不成立;`quotes()` 是 `codes=None` 慣例來源 |
| F-28 | C1-F9 | PARTIAL | LOW→LOW | PARTIAL(校正 LOW;原 LOW):V1 裸 assert 半 REFUTED(`configio.py:30` 四支設定共用 loader,strategy / backtest / fade 三個 tuple 鍵長期未爆);元素非 str 半 = C1-F5 同後果;`policy_outcome_days ≤ 0` 半 CONFIRMED(:1265 → :1267 把設定錯講成資料狀態);prod 無 signals.json 全走預設 |
| F-29 | C1-F10 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V1 突變 :451 接 skip_note → `-k seed_skipped` 仍 4 passed = 訊息內容零釘;prod 規則檔 v1 4 條 → v4 7 條,距 30 遠 |
| F-30 | C1-F11 | PARTIAL | LOW→LOW | PARTIAL(校正 LOW;原 LOW):V1 核 :471-472 已寫「翻旗只認 v3 之前的檔」,讀者推一步即得;行為本身是遷移正確語意;成立只剩手順段沒把後果講完 |
| F-31 | D1-F3 | PARTIAL | LOW→LOW | PARTIAL(校正 LOW;原 LOW):V1 核 spec Out of Scope 明寫週對帳腳本留研究目錄,研究目錄已有 daily_all / daily_sep / kbar_* 且 `nosig.py:22-31` 已用日收盤算鎖板;T+1/T+2 open(唯一事後拿不到的)確實補了;成立只剩文件補一句 |
| F-32 | D1-F4 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V1 重現 865 / 12 筆(1.39%,逐筆清單)、絕對差 p90 0.375 pt;spec 明文「自己的價…取當筆 state」→ 與 C1 面 2「不構成實作 finding」相容,兩軸都對;純文件缺口 |
| F-33 | D1-F5 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V1 核三處有括號、只 glossary 漏;D1 與 C4 各自獨立抓到同一行(強佐證) |
| F-34 | C4-F4 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V1 核 `_group_suffix` 逐字零排除 |
| F-35 | C4-F5 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V1 核兩節不一致;#198 AC 不含 §0 |
| F-36 | C4-F1 | CONFIRMED | MEDIUM→LOW | CONFIRMED(校正 LOW;原 MEDIUM):V1 抽驗 5 sha 存在 / NOT_ANCESTOR;subject 1:1 唯一,`git log --grep` 可對回(c331b33d→1c707137 等),復原成本近零 |
| F-37 | C4-F6 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V1 開圖核:select 只見「掃單簇」、min/max 不可見;list.png 相符;七條與旗標另由 migration-dry-run / startup-log 核過 |
| F-38 | C4-F7 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V1 程式化比對鍵集如述 |
| F-39 | C3a-F4 | PARTIAL | LOW→LOW | PARTIAL(校正 LOW;原 LOW):V2 序列重跑 M1 全量 3 failed / 464(golden 三案紅)獨立重現;保護存在,只是落在 AC 指名以外的 seam |
| F-40 | C3a-F5 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V2 序列重跑 M7 全量 467 passed;後果只 IO / mtime 雜訊(過去日檔無 concurrent append,除非 C3a-F1 守門先拿掉) |
| F-41 | C3a-F6 | PARTIAL | LOW→LOW | PARTIAL(校正 LOW;原 LOW):V2 核 11 事件中 6 個 prefix 與 research 的 i/price/levels/qty 不同(1727 第 5 事件 i=301/77.3/3/5 vs 310/78.3/13/50),集合相等比對已釘即時判語意;缺口只在重錄 self-check 不封多發上界 |
| F-42 | C3a-F7 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V2 序列重跑 M5 全量 467 passed;prod 預設 `basis_gap_secs` 0.2;後果 = 回填時對 TC4 逐檔節流失效 |
| F-43 | C3a-F8 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V2 通讀 TestSchedule 四案 + no_source 案無一讓本體拋;`_FakeDayBars` 失敗注入打不到外層傘 |
| F-44 | C3b-F4 | CONFIRMED | MEDIUM→LOW | CONFIRMED(校正 LOW;原 MEDIUM):V2 序列重跑全量 467 passed;型別可達但「TC4 真送 ReferencePrice=0」無實證;終局與守門相同(零政策列 + raw 列在)只多 traceback;`price <= 0` 半不可達(`_eval_sweep:708-710` 早退) |
| F-45 | C3b-F5 | CONFIRMED | LOW→LOW | CONFIRMED(校正 LOW;原 LOW):V2 序列重跑刪兩歸零點全量 467 passed;旗標只 gate log,無資料面後果 |
| F-46 | C3b-F7 | PARTIAL | LOW→LOW | PARTIAL(校正 LOW;原 LOW):V2 反證「整檔零 caller」不準(:103 `_rule_body` 內有用),缺往返案那半成立;值域另由 parity 三處釘 |
| F-47 | C2-F8 | REFUTED | LOW→LOW | REFUTED(校正 LOW;原 LOW):V2 baseline —— 同檔 `SignalRail.tsx:269` `ruleTitle` 每組每規則名做 reverse + Set,對 rail 每一列執行且長期未列效能問題;`policyTitle` 只在政策組(一天 25 組)跑,是最小的那份 |

#### V1 全文(逐字濃縮)

```text
# V1 內部複查(code-reviewer, opus;worktree v1)— 22 條:CONFIRMED 16 / PARTIAL 6 / REFUTED 0;校正 MED 5 / LOW 17;worktree 收工乾淨
C1-F1 PARTIAL MED→LOW:_groups 空 = P/B/S 全不評(first-pass「S 只在篩選成員活」錯:screen_member 也由 _groups 產生);可達性被 app.py:854 load_watchlist 在 on_watchlist 前求值、不在 hub try 內 → 壞檔先在 _boot 大聲停用整顆 hub 擋掉;成立只剩 log/docstring 漏族群消費者。
C1-F2 CONFIRMED MED:tc4.py:547-562 _req 全走 api.lock、_collect_history 同鎖;_policy_outcome_worker:1220-1224 無條件先跑;實測 prod 五日檔待補 = 20260907 29 列 / 15 相異 code → 首跑 15 次 DK ≈ 5–18 s(stock_source.py:752 probe 0.02–0.98 s)≈ 150 檔基準 sweep 10% 延後;風險窗 = 接近 09:00 才啟動。
C1-F3 CONFIRMED LOW:prod 目錄恆在(15 日檔),只全新安裝可達。
C1-F4 CONFIRMED LOW:旗標只 on_rollover:667 復位;peers_fn 純記憶體讀,拋 = 別的 bug。
C1-F5 CONFIRMED MED:events.csv 原地驗 ALL IN 當族群 n=10 / −1,471(事件級 16 / −3,605)逐字符 §8.2;緩解 = 政策列自帶 groups/peers、卡面第三行印族群(非全盲);spec story 14 把改名→改設定寫成 user 流程;結論 = 載入期補 WARNING。
C1-F6 PARTIAL LOW:探針實跑(tick.time="bogus")_sweeps 毒值後 deque 永不修剪,n30 = 當日累計掃單數(簇窗整個失效,比 first-pass 的「min_sweeps 降 1」更重);prod 不可達(_taipei_time 恆合法);docstring 觸發條件確寫錯。
C1-F7 PARTIAL LOW:10:1 比例正確,但 :776-798 per-code 組裝兩路共用,None 分支獨有只名單來源;quotes() 是 codes=None 慣例來源。
C1-F8 CONFIRMED LOW:app.py:839-842 與 _refresh_groups docstring :704-708 同病,與 C1-F1 同根因(收修一起改)。
C1-F9 PARTIAL LOW:裸 assert 半 REFUTED(configio.py:30 四支設定共用 loader,strategy/backtest/fade 三個 tuple 鍵長期未爆);元素非 str 半 = C1-F5 同後果;policy_outcome_days ≤ 0 半 CONFIRMED(:1265 dated[:0] → :1267 把設定錯講成資料狀態)。
C1-F10 CONFIRMED LOW:突變 :451 接 skip_note → -k seed_skipped 4 passed 仍綠 = 訊息內容零釘(撞名案 :932 有 assert 零政策列、滿檔案 :945 只 count);prod 規則檔 v1 4 條 → v4 7 條(rule_id -006 相符),距 30 遠。
C1-F11 PARTIAL LOW::471-472 已寫翻旗只認 v3 前的檔;回退段沒重述後果。
D1-F1 CONFIRMED MED:逐格重算:sweepc 865,tod ∈ {900,910,930,1030,1200} 全 <1230,late=1 65 筆;排除 ALL IN:tod<1230 = 無濾網 = 36/+5,497/22%;late==0 = 35/+5,784/23%;其他列同向修正(S 110/+1,313/15%→99/+1,433/17%;P 自選 43/+4,703/23%→42/+4,923/24%;P 相關 126/+3,132/18%→120/+3,324/19%),無拍板翻面。
D1-F2 CONFIRMED MED:nosig.py:52 own 無白名單、:53 others 有(同檔兩把尺);glob 整目錄跨期混用;fills.json 最後 2026/09/03,影子期 fills 進來才發作。
D1-F3 PARTIAL LOW:spec Out of Scope 明寫週對帳腳本留研究目錄,研究目錄已有 daily_all/daily_sep/kbar_* 且 nosig.py:22-31 已用日收盤算鎖板;成立只剩文件補一句。
D1-F4 CONFIRMED LOW:重現 865 / 12 筆(1.39%;逐筆清單 8358/08-06 … 8358/08-26);|Δ| p90 0.375 pt、範圍 ±[−1.42,+1.13];spec 明文當筆 state;docstring 未記。
D1-F5 CONFIRMED LOW:三處有括號(signals_config.py:49 / signal_state.py:698 / :735 實作),只 CONTEXT.md:98 漏;併 C4-F3。
C4-F1 CONFIRMED MED→LOW:5 sha 抽驗存在但 NOT_ANCESTOR;subject 1:1 唯一可 git log --grep 對回(c331b33d→1c707137 等),復原成本近零。
C4-F2 CONFIRMED MED:ask_milli 經 _best_limit_price 0→None(stock_models.py:149-151、歷史 :256-258);鎖漲停 derive_side = neutral(skill :93 自證);_eval_sweep :725 `ask > 0` 是死條件、與 derive_side outer 分支等價;真正理由 = 研究 pull_ticks.py:63 保留原始 Ask=0。
C4-F4 CONFIRMED LOW:_group_suffix :735 零排除;盤前篩選 38 檔命中率遠高於 ALL IN 8 檔。
C4-F5 CONFIRMED LOW。C4-F6 CONFIRMED LOW(開圖核:select 收合只見掃單簇、min/max 屬性不可見;list.png 相符)。C4-F7 CONFIRMED LOW(程式化比對鍵集)。
跨軸裁定:D1-F4 vs C1 面 2 相容(兩軸都對);C2-F5 vs C4 契約 2:預設組態 PASS 成立,up_pct=0 可設定邊界下 C2-F5 成立,不衝突(後端 None→+0.00%、前端 null→無數字;0.0 後端 +0.00% 前端 0.00%)。
最重要三條:D1-F1 / C1-F5 / C4-F2。
```

#### V2 全文(逐字濃縮)

```text
# V2 內部複查(code-reviewer, opus;worktree v2 + 主 tree 前端)— 25 條:CONFIRMED 19 / PARTIAL 5 / REFUTED 1;校正 MED 8 / LOW 17;兩棵樹收工乾淨
C2-F1 CONFIRMED MED→LOW:真資料 S 22 列 16 列 groups=[]、9 列 notify=true;緩解 = S chip + hover 正確 + groups=[] 已落 jsonl。
C2-F2 CONFIRMED MED:every→some 全量 2381 綠;真資料 25 政策組中 15 混合組;cdp_cross 155 全 quiet 與 surge 混組更普遍 → some 讓多數列淡色。
C2-F3 CONFIRMED MED→LOW:刪 :234 全量 2381 綠;真資料 25 政策組中「有 notify=true 非政策同伴」= 0 → 現況零踏到;需 user 開掃單簇通知或同秒撞 surge。
C2-F4 CONFIRMED LOW:offset→0 2381 綠;fake createOscillator 不記 start 參數。
C2-F5 CONFIRMED LOW(裁定 C2-F5 對,C4 PASS 只在預設 config):實測後端 _kind_text pct=0 / None → "掃單簇 +0.00%",policy 缺 tag → "政策 "(尾空白);前端 pct=0 → "掃單簇 0.00%"、null → "掃單簇"、缺 tag → "政策";非零逐字對齊;up_pct 值域下限 0 合法,session 前 60 s 窗前無成交 → up_pct=0.0 可達。
C2-F6 CONFIRMED LOW:真資料 4 組同 tick P+S first_of_day 皆一致 → 現況未誤述;分岔路徑存在(S 母體寬、早盤先單獨命中)。
C2-F7 PARTIAL LOW:peer_touched 後端恆 bool(signal_policy.py:87 / hub :1119)不可達;dead 三元屬實。
C2-F8 REFUTED LOW:baseline —— 同檔 :269 ruleTitle 每組每規則名做 reverse + Set,比 policyTitle(每天 25 組)更重且長期未列效能問題。
C2-F9 CONFIRMED LOW:PARAM_FIELDS 型別 total map,runtime 新 kind → undefined → for…of 拋;ruleSummary 有 fallback、toForm 無;spec 緩解只寫訊號列。
C2-F10 PARTIAL LOW:取末筆 2381 綠;同事件各政策列除 policy/id/touch_count/first_of_day/notify 外欄位相同 → 第三行輸出逐字相同,差異只在 C2-F6 hover。
C3a-F1 CONFIRMED MED:M2 全量 467 綠;CLAUDE.md 明載 trade_date 空自選/零推播停在昨日;_append_jsonl(:983/:1006)用同一顆 _trade_date_fn → 13:40 atomic_write_bytes 整檔覆寫仍在 append 的檔。
C3a-F2 CONFIRMED MED:M3 / M4 全量 467 綠(含 golden);真資料 75 列 sweep/policy 時刻鍵 100% .000(全檔 479 只 2 列非 .000 = limit_open 伺服器時刻)→ 恰差 30/60 s 常態。
C3a-F3 CONFIRMED MED:M6 全量 467 綠;golden 殺不掉因 record 腳本 :65-67 自己加 [09:00,13:30) gate;F-25 收修紀錄「三案各只掉 13:30:00.000 收盤撮合一筆」= 收盤同秒大群實證。
C3a-F4 PARTIAL LOW:M1 全量 3 failed / 464(golden 三案紅)獨立重現;主 seam 斷言證不出但保護存在。
C3a-F5 CONFIRMED LOW:M7 467 綠;後果只 IO/mtime 雜訊(過去日檔無 concurrent append,除非 C3a-F1 守門先拿掉)。
C3a-F6 PARTIAL LOW:三案事件數皆相等屬實;但 11 事件中 6 個 prefix 與 research 的 i/price/levels/qty 不同(1727 第 5 事件 i=301/77.3/3/5 vs 310/78.3/13/50),集合相等比對已釘即時判語意;缺口只在重錄 self-check 不封多發上界。
C3a-F7 CONFIRMED LOW:M5 467 綠;prod 預設 basis_gap_secs 0.2;#196 AC 明文。
C3a-F8 CONFIRMED LOW:TestSchedule 四案 + no_source 案無一讓 backfill 本體拋;_FakeDayBars 失敗注入打不到外層傘。
C3b-F1 CONFIRMED MED:`<=` 全量 467 綠;既有案 ref=47_000 → 7.23;ref=47_547 → 6.000379 → round 6.0 可殺。
C3b-F2 CONFIRMED MED:`>` 467 綠;既有 3.92 vs 3.0;ref=48_932 → 3.000082 → 3.0 平手可殺;研究 _leader 含平手。
C3b-F3 CONFIRMED MED:刪 round 467 綠;既有 ref=50_000 chg 0.8 approx;ref=48_933 → 2.997977 → round 3.0 vs 不 round 2.998 → 一案釘 self.chg_pct 與 B-a/B-b。
C3b-F4 CONFIRMED MED→LOW:守門收成 ref is None 467 綠;to_milli_units("0") → 0 型別可達(TC4 真送 0 無實證);終局同守門(零政策列 + raw 列在)只多 traceback;price ≤ 0 半不可達(_eval_sweep :708-710 早退)。
C3b-F5 CONFIRMED LOW:刪兩歸零點 467 綠;旗標只 gate log。
C3b-F6 CONFIRMED MED:去掉賣側空 467 綠;第二筆同時改價與賣側;locked_up 不進政策條件、純快照欄(story 16)→ 對帳錯非漏發錯。
C3b-F7 PARTIAL LOW:_RULE_PARAMS 有 caller(:103 _rule_body 內),但 16 個 _rule_body 呼叫無 sweep_cluster;值域另由 parity 三處釘。
突變總表 17 發:16 存活、1(M1)被 golden 殺;序列重跑結果與 first-pass 一致,含 M3/M4 → 並行互污染疑慮未成立。
最重要三條:C3a-F1 / C3b-F1+F2+F3 一族 / C3a-F2。
一次性 probe frontend/src/lib/__v2probe.test.ts 已刪;runner 留 scratchpad/v2/。
```

### Step 4.3a consensus baseline check

無跨軸 consensus(單軸)。同軸內重合兩組已在合併時去重(D1-F5 ≡ C4-F3;C1-F10 ≡ C3b-F8),裁定為強佐證而非 consensus 豁免;跨軸說法衝突兩組(C2-F5 vs C4 契約 2 PASS;D1-F4 vs C1 面 2)由 V1 / V2 各裁定為「相容、兩軸都對」(見各列複查欄)。

### Step 4.3b lone-finding 判斷

47 條全部是 lone finding(只有 CC 一軸)。每條複查欄的 `lone_note` 已解釋「其他 chunk / D1 為何沒 flag」——全部是分片範圍不同(前端 / 後端 source / 測試 / 文件 / spec 語意各一軸)或需要跨檔・跨目錄・實跑才看得出,無一是「真的漏」。校正後 severity 已依複查 impact 定案,不再因「他軸沉默」機械降級。

## Action Items

**Severity calibration**:47 條 first-pass 無 CRITICAL / HIGH;複查後 MEDIUM 13 / LOW 34。依 6d-3 雙半條件(具體 user-visible 重現路徑 + 不修就壞會出貨的東西)無 Must Fix 候選;Should Fix 的條件是 first-pass HIGH 且非 REFUTED,本輪零 HIGH → 全部落 Nice to Have(46)與參考用(1,REFUTED)。6c Refactor Intent Gate:本 range 無「移除 / 削弱既有防護」類 finding,免。Provenance cap N-A。**但要注意優先序**:F-01–F-13 是校正後 MEDIUM,其中 F-01 / F-02 / F-03 / F-06–F-09 直接關係「影子期四週的資料能不能用來下結論」,建議在影子期對帳前先做(表內 Action 理由已標)。

**校準套用**:無作者校準檔(`docs/pr-review-calibration/loger-w.md` 不存在)、本輪無套用。

### Must Fix（合併前必修）

無。(兩 PR 已 merge;本輪零 CRITICAL / HIGH;無 strict-liability。)

### Should Fix（強烈建議）

無(依規則需 first-pass HIGH;本輪零 HIGH)。

### Nice to Have（可選優化）

F-01 … F-46(校正後 MEDIUM 13 + LOW 33;各條處置見發現總覽 Action 欄:auto-fix 40 / ask-user 6 / no-op 1(no-op 那條在參考用))。ask-user 6 條:F-01(研究表 / 腳本在 repo 外)、F-10(startup 回填排程取捨)、F-11(研究腳本 + 契約措辭)、F-14(無族群 S 列第三行文案)、F-20(舊 dist 規則視窗:改文件或改 code)、F-31(事件日出場價:改文件或補兩欄)。

### 參考用（任一軸驗證為 REFUTED 或 OUT_OF_SCOPE）

- F-47(C2-F8):CC 擔心 rail 政策列每 render 組 hover 字串 → 內部複查於 `SignalRail.tsx:269` 找到同檔更重的同 pattern(`ruleTitle` 對每組每規則名 reverse + Set)長期未爆 → 使用者自行判斷是否採納;真要收是整條 rail 抽 memo 子元件。

## 審查工具比較 (qualitative)

- CC 主軸六分片:後端 source(C1)抓到啟動期背景 worker 搶 TC4 鎖與設定字串排除失效這類要跨 `tc4.py` / `app.py` / 環境事實才看得到的問題;前端(C2)以真資料統計證明「無族群 S 列」是多數情形並實跑四個前端突變體;後端測試兩分片(C3a / C3b)以 15 個後端突變體把「測試釘住了什麼」量化,找出政策謂詞三個界(6.00 恰等 / leader 平手 / round 兩把尺)與偵測器兩個窗界零樣本;文件契約(C4)把 CLAUDE.md 五條契約與 §1 判準對 prod 真資料 / 真 log 實跑全 PASS,並抓到 skill 沉澱的事實寫錯;spec 語意對帳(D1)是本輪獨有的價值 —— 32 story / W1–W12 逐條對帳、研究 `group_feats` 逐條件對照(確認「鎖過閘只看同伴」其實同義)、並發現研究 §8.2 基準表的時間濾網是 no-op。
- 內部複查(同軸,非跨軸):V1 對 D1-F1 / D1-F4 / C1-F5 逐格重算研究資料、對 C1-F6 跑探針(發現後果比 first-pass 更重)、對 C1-F9 用 baseline 推翻半條;V2 序列重跑全部 17 個突變體 + 全量,證明 first-pass 數字可信、並用真資料量化 C2-F2 / C2-F3 的可達性。REFUTED 率 1/47 = 2%;降級 5 / 升級 0 —— first-pass 命中率高,但 severity 有向上漂的傾向(MEDIUM 17 → 13)。
- Codex 中性 / 對抗、Gemini:N-A。對抗式第三軸增益:N-A。
- 前兩輪(#199 50 條 + #200 11 條)與本輪 47 條零重複;本輪 10 條是對收修的複查,結論全部是「收修正確,但修了一半 / 零回歸保護」而非修錯。

## 沒做的部分（結案對帳）

- Codex 中性 / Codex 對抗:**N-A**(user 2026-09-07 明示停用,per-PR override 沿 #188 / #190 / #199 前例)—— 沒有跨軸證據,Step 4.2 以同軸 code-reviewer 內部複查代替(兩批 22 + 25 條,ID 集合精確相等,各自獨立 worktree)。
- Gemini Flash / Pro:**N-A**(user 明示停用);Quota 未取。
- security-reviewer:**N-A**(未觸發:range 未動 auth / cookie / request body 解析 / 憑證 env;新設定鍵走既有 `configio` loader、新 API 參數走既有 `normalize_rule`)。
- spec-compliance-reviewer(C4):**N-A / SKIPPED**(`C4_NO_SPEC_FILE_IN_REPO`:spec 是 GitHub issue,無 repo 內 normative 檔可綁;不派、不補派)。spec 語意對帳由 D1 一般 domain reviewer 執行,**不是 C4 pipeline**,無 reducer receipt。
- Blast radius(2.9):**PASS(空輸出跳過)**。React-doctor(2.97):**PASS(未引入新問題)**。Provenance(2.55):**N-A**。Author calibration:**N-A**(無校準檔)。
- 未驗證前提(逐條標明):F-10(C1-F2)的「5–18 s / 10% 延後」是 V1 以 probe 成本推估,未在 prod 開機實測;F-44(C3b-F4)的「TC4 真的送過 ReferencePrice=0」無實證,只證型別可達;F-01(D1-F1)的「無拍板會翻」只覆蓋 §8.2 表列出的那幾列,未重跑 §8.1 拍板依據的其他 `.out`;F-31(D1-F3)「研究目錄已有補足資料」是對檔案存在的觀察,未實跑一次完整週對帳;C1 面 4 的「佇列滿時 raw 列先於政策列被丟」是 code 推論,09-07 佇列滿 0 無實錄。
- 影子期尚未真環境驗證的項目(review 時明知、留給判準):T+1 / T+2 回填 worker 明日(09-08)13:40 才第一次對真資料跑(log「回填 n 列」、29 列 `t1_open` 補上);#200 未上線(下次啟動自然帶上,行為無差);`frontend/dist` 落後 #200 一版(preview 前 `npm run build`)。
- Step 4.5 coverage repair 輪:**未觸發**(missed 0)。Step 4.6 re-anchor:45 exact / 3 ambiguous(皆含或取最近自報行)/ 0 FAILED;13 條校正了 reviewer 自報行號(表內與 inline block 已用校正後行號)。
- 環境事件(存證,不列 finding):(1) C3a 在 first-pass 期間觀察到另一 reviewer(C3b)在同一棵 primary worktree 做 `locked_up_flag` 突變,提出並行互污染疑慮 → 內部複查改為每批獨立 worktree 並序列重跑 17 個突變體,結果與 first-pass 逐條一致,疑慮未成立;(2) C4 在 primary worktree 跑 4 次全量 pytest,3 次 `3494 passed, 3 skipped`(與 followups verification.md 宣稱逐字相符),第 1 次 golden 三案紅 = 自身另一 python 程序同時寫 `__pycache__` 的干擾,單獨與後續三次全綠;(3) V2 為 C2-F5 寫的一次性 probe `frontend/src/lib/__v2probe.test.ts` 跑完即刪,主 tree `git status` 只剩開場既有的六個 untracked `pr-17x-review*.md`。三棵 worktree 收工 `status --porcelain` 皆空。
- **Self-Verify(skill-verify-auditor,dispatch marker `skill-verify:pr-review`,model opus)**:第一輪 `VERDICT: VIOLATIONS: R5`(R1–R4、R6–R10 PASS)。R5 原缺口 = Action Items「Nice to Have」段手寫的處置計數「auto-fix 39 / ask-user 7」與 canonical uid record / 表格 Action 欄(實為 auto-fix 40 / ask-user 6 / no-op 1)不一致,且「ask-user 七條」下只列六條。修正方式 = 產報告腳本改為由 finding 資料程式計數並斷言 ask-user 集合(本段數字現與 canonical record 同源),重產草稿並重跑 helper 契約檢查 OK。修正後**未重派 auditor,未經第二次獨立稽查**。

