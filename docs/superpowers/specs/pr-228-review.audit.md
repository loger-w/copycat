# PR #228 Code Review 比較報告 · SHA 21385338
**Report projection schema**: 1

**PR**: [loger-w/copycat#228](https://github.com/loger-w/copycat/pull/228)
**標題**: mod(signal): 訊號層三件顯示層小改 —— CDP 列閘 / 放量離開 kind / 掃單簇大單筆數格(#224)
**作者**: loger-w
**分支**: `mod/signal-context-trio` → `master`
**變更**: 35 檔案, +2091 / -104
**審查日期**: 2026-09-14
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨;merge commit `e60024cd`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `213853381f61fbc24a06574defba3ba2f20118c5`;destination repo id `R_kgDOTsITBg` + baseRefOid `1a032b9b3c5c259abf44b24e83de934d884520df`;`input_binding: verified` —— `git fetch origin refs/pull/228/head` 取回的 FETCH_HEAD = headRefOid 逐字相等,review worktree detached 於該 SHA,`git merge-base origin/master HEAD` = baseRefOid
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 SHA;分支已隨 `--delete-branch` 刪除,但 `refs/pull/228/head` 仍指 `21385338`,產報告前重抓 headRefOid 仍為它);`base_changed=true`(origin/master 自 `1a032b9b` 前進至 `e60024cd`,內容 = 本 PR 自身 13 筆 rebase 後 commit,其後零新 commit);`review_context_changed=false`(審的是 PR head,與落地版逐檔等價)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用,沿 #188 / #190 / #199 / #202 / #211 / #218 / #220 / #222 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer ×2(chunked;requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .py 94% / .ts+.tsx 6% 的 source diff 行);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE;純讀碼 + grep + 只讀 pytest / 突變體模擬);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=35 → covered 8 / no-issues 19 / skipped 8 / **missed 0**(chunked: **是**,21 source 檔 / 1568 source diff 行(.py 1478 / .ts+.tsx 90)超過 15 檔 / 800 行門檻 → 依排序路徑切兩塊:chunk A = `.claude/**` + `CLAUDE.md` + `CONTEXT.md` + `copycat/**` + `frontend/**`(27 檔,source 14)、chunk B = `tests/**`(8 檔);35/35 per-file accounting 齊,skipped 8 = 4 張截圖 + 4 個證據 JSON)
**定位 (ENH-B)**: anchored exact 11 / ambiguous 1 / **FAILED 0**(全部 anchor 在 worktree 逐字命中:signal_state.py:3 / signal_hub.py:986 / :1195 / change-spec.md:53 / test_signal_state.py:1518(reviewer 自報 1515-1521)/ :1622(自報 1618-1624)/ :1496 / test_signal_hub.py:2614(自報 2613-2619)/ :1750 / :3195 / test_signal_policy.py:186 / test_signal_rules.py:1047(**ambiguous**:anchor 亦命中 :954 的 v3→v4 同型斷言,取 reviewer 自報 1046-1047 內的 1047))
**React-doctor (2.97)**: 未引入新問題(既有 2 條不計;`npx -y react-doctor@latest . --offline --no-score --scope changed --base 1a032b9b --json` 於 review worktree `frontend/` 執行,`newCount 0 / fixedCount 0 / baseTotalCount 2`,changedFileCount 9)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_CLAUSE)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出;`sem` 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer chunk A)PASS(4 findings + 27/27 accounting;只讀 pytest 371 passed)/ primary(python-reviewer chunk B)PASS(8 findings + 8/8 accounting;只讀 pytest 595 passed + 五組突變體模擬)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 請求體解析 / 秘鑰讀取)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(12/12 verdict 齊、ID 集合精確相等、每列八欄齊)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-228`
**worktree HEAD**: `213853381f61fbc24a06574defba3ba2f20118c5`

**Report generation**: sha256:99170a237d0aa18d9076aafc28d3d20f54bdcf68b05e223e899ca0e6ef6e0a38

---

## Spec 依據

- 偵測到 spec 檔:`.claude/mod/signal-context-trio/change-spec.md`(檔名 `*-spec.md` 且在 `.claude/mod/` 流程目錄;內容 = §0 現況 vs 目標三件 / §1 caller map / §2 既有行為白名單 W-1..W-14 / §3 grilling 17 題 `[auto-default]` 決策(全採建議解,理由逐題)/ §4 seams 三個既有 seam / §5 三張 tickets / §6 out of scope)。GitHub 側 spec issue #224 + tickets #225 / #226 / #227(已隨 merge 自動 close;#224 留言追記 W-11 改字與 Q13 已知差異)。同 PR 內另有 two-axis round-1(`code-review-round-1.json`,Standards 7 + Spec 4,全數處置、收修 commit `ddc98768` / `9e2d9485` / `a897d3ae` / `0802bd9f` / `f06b9c08`)—— 本輪不重報已收修條目,只報處置不完整處或新事實。
- **⚠️ spec 作者 = PR 作者**(`git log --format='%an' -- .claude/mod/signal-context-trio/change-spec.md` = Loger = PR 作者 loger-w;且本 PR 全程 `/auto` 疊加、grilling 17 題由 agent 採建議解落檔 —— out-of-scope 判定以此 spec 為據時,注意「決策與實作同一手」的利益重疊;本輪 §6 out of scope 未被用來免罪任何 finding,反向的 R-A4 指出 §2 W-14 敘述低估實作成本)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_NORMATIVE_CLAUSE`(change-spec.md 全文 grep `MUST|SHALL|NEVER|必須|不得|恆` 三命中:`:34` 引 W1 離線讀者契約的敘述句、`:36` 白名單標題「不得破壞」、`:82` grilling 理由「定義必須同源」—— 皆為計畫層白名單 / 理由敘述,無可綁 `path:line` 的 actor / operation / precondition / result 實作契約;CLAUDE.md §4 新增三條屬專案指令檔,不在 spec 偵測路徑)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool calls=N-A(未派);0 clauses / 0 findings / 0 observations / 0 invalidated。reducer 安全投影要求:未派故無 `human_projection`;本報告零 C4 內容,`invalidated_ids ∩ report_finding_ids = ∅`(兩集合皆空),無 invalidated 語意外洩,C4 對 Step 4.5 覆蓋零貢獻。
- Author calibration(Step 2.2):無作者校準檔(`loger-w.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

provenance: N-A(base = master,35 檔全 authored)。

| 檔案 | 類型 | 說明 |
|---|---|---|
| `copycat/signals_config.py` | 設定 | 新增 `cdp_gate_days / cdp_gate_pct`(#225)、`breakout_band_pct / min_dwell_secs / ratio / cooldown_secs`(#226)、`big_lot_ratio / big_lot_window_secs`(#227)八欄與註解 |
| `copycat/server/signal_hub.py` | 後端 | `_resolve_basis` 加列閘三分支(日 K 不足 INFO / 分母 ≤ 0 WARNING / 漲幅不足 INFO)+ `_gate_return_pct`;`_basis_bars = days + 3`;`_emit_policies` 自 `detail` 拆出 `big_lots_120s` 放頂層(bool 守門);`format_policy_group_text` 第 2 行尾「・大單 n 筆」;`_kind_text` 加 `vol_breakout` |
| `copycat/live/signal_state.py` | 後端 | `BIG_LOTS_KEY` + `_advance_big_lots`(研究 `bigtick_hits` 逐字)寫進掃單簇 `detail`;新 kind `vol_breakout`:`_Dwell` / `_Break` + `_eval_breakout` / `_breakout_event`(S-01 收修:不合格離帶不 pop 在飛累加器);`KIND_SWITCH` / `SWITCH_KEYS` 七鍵;`reset_day` / `drop_code` 六份新狀態清理 |
| `copycat/signal_rules.py` | 後端 | `RULE_KINDS` / `PARAM_SPECS` / `_DEFAULT_NAMES` / `_QUIET_KINDS` / `_seed_params` / `_seed_cooldown` / `rule_config` 加 `vol_breakout`;`_CACHE_VERSION` 4→5、`_migrate_v4` append 種子卡(不翻旗)、遷移鏈 `version <= 3` 收窄;兩張靜音種子卡收成 `_quiet_seed_rule(kind)` |
| `frontend/src/lib/signal-model.ts` | 前端 | `SignalKind` 加 `vol_breakout`、`kindLabel` 文案、`big_lots_120s?: number \| null` + `bigLotsPhrase`(第三行尾 / hover 一段;缺欄或 null 不印) |
| `frontend/src/lib/signal-params.ts` | 前端 | `PARAM_FIELDS.vol_breakout` 三欄(0.6 / 600 / 4) |
| `frontend/src/hooks/useSignalRules.ts` | 前端 | `RULE_KINDS` 加 `vol_breakout` |
| `frontend/src/components/stock/SignalRulesDialog.tsx` | 前端 | `KIND_LABEL` 放量離開 + `ruleSummary` 一行摘要 |
| `frontend/src/components/stock/SignalRail.tsx` | 前端 | `toneOf` 併入 `vol_breakout`(向上紅 / 向下綠) |
| `tests/fixtures/signal_param_specs.json` | fixture | `vol_breakout` 三鍵值域(前後端 parity) |
| `tests/live/test_signal_state.py` | 測試 | `TestBigLots` 十案、`TestVolBreakout` 十二案(含 S-01 紅先行)、開關鍵七鍵;formatter hook 重排的兩段既有格式已還原 |
| `tests/server/test_signal_hub.py` | 測試 | 日 K 治具改六根歷史 `_HIST` / `_flat_hist`;`TestCdpGate` 七案;`_write_rules` 改引 `_CACHE_VERSION`;`_RULE_PARAMS` / 種子序 / Discord 文案;`TestVolBreakoutRule` 端到端 quiet 列 |
| `tests/server/test_signal_policy.py` | 測試 | `_POLICY_KEYS` + `big_lots_120s`;大單端到端案;Discord 第 2 行「・大單 0 筆」;缺欄第 2 行不變案 |
| `tests/server/test_signal_outcome.py` | 測試 | `_policy_row` 加 `big_lots_120s: 0`(回填 byte 比對涵蓋 W-8) |
| `tests/server/test_signal_routes.py` | 測試 | `_SEEDED_KINDS` 加 `vol_breakout` |
| `tests/test_signal_rules.py` | 測試 | 七 kind / PARAM_SPECS 字面 / 種子 / 冷卻;遷移鏈斷言更新;`TestMigrationV4ToV5` 七案;`rule_config` 映射案 |
| `tests/test_signals_config.py` | 測試 | 八顆新預設值 |
| `CLAUDE.md` | 契約 | §4 三條:`big_lots_120s` 欄 / `vol_breakout` kind + 規則檔 v5 / CDP 列閘(產生點、讀者、漂掉症狀、盤後判準) |
| `CONTEXT.md` | 術語 | 「CDP 列閘 / 放量離開 / 大單敲檔」三詞 + _Avoid_ |
| `.claude/mod/signal-context-trio/change-spec.md` | 新增 | caller map / 現況 vs 目標 / 白名單 / grilling 17 題 auto-default / seams / tickets / out of scope(review 後 W-11 改字、Q13 已知差異補記) |
| `.claude/mod/signal-context-trio/code-review-round-1.json` | 新增 | two-axis round-1:Standards 7 + Spec 4 全處置 |
| `.claude/mod/signal-context-trio/verification.md` | 新增 | 紅先行表 / 中途輪 / 側車真環境八案 / 最終輪(pytest 3626 / vitest 3074 / ruff / pyright / tsc / eslint / doctor / validate 42/42)|
| `.claude/mod/signal-context-trio/evidence/sidecar_server.py` | 證據 | 零 TC4 側車(neutralize + worktree import 錨點 + 三檔劇本推播執行緒) |
| `.claude/mod/signal-context-trio/evidence/*.json`(4)/ `*.png`(4) | 證據 | 側車四端點 JSON 與 rail / 全頁 / 規則視窗 / 編輯表單截圖 |

## 發現總覽

| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `signal_state.py:3` 模組 docstring 仍寫「六類訊號」清單,本 PR 加了第七類 `vol_breakout` 沒更新;`CLAUDE.md:60` 結構樹同一份清單也沒加(該行 base 上已漏 `surge_pullback`,本 PR 讓落差變兩項) | LOW | CONFIRMED(LOW→LOW:純文字陳舊,機器真值 `RULE_KINDS` 七值有測試釘) | Nice to Have | `auto-fix` | 兩處文字各改一行,零 runtime |
| F-02 | `signal_hub.py:986` `_gate_return_pct` 只對分母 `close[-6] ≤ 0` 回 None;分子 `close[-1] ≤ 0` 會算成 −100% 走「漲幅不足」INFO 桶,壞資料被記進不合格檔,round-1 F-02「兩種原因分講」只做了半邊 | LOW | PARTIAL(LOW→LOW:實跑 close[-1]=0 → −100.0 落 986 行 INFO 桶;但閘的**結果**不變(CDP 仍 None),差異止於 log 分桶;反例只在 `cdp_gate_pct ≤ −100` 時成立) | Nice to Have | `auto-fix` | 一行擴 `or done[-1]["close"] <= 0` + WARNING 文案「首尾日 K 收盤 ≤ 0」,以「log 分桶一致性」立案 |
| F-03 | `change-spec.md:53` W-14 寫「非掃單簇規則的 detector 不維護大單狀態以外的新東西 / 開銷 = 每 tick 一次 deque append」低估:每條規則的 detector 都無條件跑 `_eval_breakout` 狀態機(`_dwell` / `_break` 兩份 dict + 離帶時 dataclass / set 配置),非 vol_breakout slot 只推進不產出;結論 bounded 為真、理由句錯 | LOW | CONFIRMED(LOW→LOW:實測 enabled 只有 vol_burst 的 detector 餵 20,000 tick 後 `_dwell` / `_big_hits` 都有狀態,4.33 µs/tick/detector;上限 30 條規則 × 4.33 µs 仍 bounded) | Nice to Have | `auto-fix` | 改 W-14 敘述為「兩軸狀態機 per-detector 各一份、非該 kind 只推進不產出、per-tick O(1)、中位只在候選 tick 算」;spec artifact 文字修正 |
| F-04 | `test_signal_state.py:1518` `test_reset_day_clears_lots_and_hits` 前置大單 09:59:30.000、發訊 10:01:30.500,窗起點 09:59:30.500 → 即使 `reset_day` 不清 `_big_hits` 也被窗剪掉,兩邊都 0,不 discriminate;跨日殘留(自午夜秒數)是真風險 | MEDIUM | CONFIRMED(MEDIUM→MEDIUM:突變體「reset_day 不清 `_big_hits`」113 passed 存活;對照 `drop_code` 不 pop 與 `reset_day` 不清 `_dwell` 兩顆姊妹突變體都被殺;前置改 10:00:30.000 後正常 0 / 突變 1,鑑別成立) | Nice to Have | `auto-fix` | 一個字面(前置時刻改 10:00:30.000);影子期研究欄 `big_lots_120s` 跨日污染的唯一守門 |
| F-05 | `test_signal_state.py:1622` 迴盪「有成交分鐘 ≥ 4」地板(spec Q10、`_BREAKOUT_MIN_MINUTES`)無邊界案:唯一案 2 分鐘、其餘全 10 / 11 分鐘;常數改 3 / 5 / 8 / 10 全綠 | MEDIUM | CONFIRMED(MEDIUM→MEDIUM:四個突變值 113 passed 全存活;姊妹常數 `_BIG_LOT_MIN_TICKS` 29 / 31 兩顆都被殺、`breakout_min_dwell_secs` 有 599 / 600 精確邊界 —— 本條是同 feature 唯一漏網) | Nice to Have | `auto-fix` | 補「恰 4 個有成交分鐘 → 發 / 3 個 → 不發」兩案;研究同源常數不得靜默改掉 |
| F-06 | `test_signal_hub.py:2614` `test_vol_breakout_kind_text_by_direction` docstring 宣稱釘「方向缺值退向上」但零斷言;三元反轉照綠。前端鏡像 `signal-model.test.ts:350-352` 同樣沒補缺 direction 案 | MEDIUM | PARTIAL(MEDIUM→**LOW**:突變體「fallback 反轉」177 passed 存活,缺口為真;但 `direction` 線上恆由 detector 填,缺值只在舊 / 外來列,後果止於一則文案的方向字;真缺陷是 docstring 宣稱釘了而沒釘) | Nice to Have | `auto-fix` | 後端加無 direction 的 row 斷「放量向上離開」、前端 `kindLabel` 補同一案;兩邊逐字契約各一行 |
| F-07 | `test_signal_state.py:1496` `test_median_uses_the_most_recent_300_ticks` 沒釘 300:`_BIG_LOT_MEDIAN_TICKS` 改 200 / 299 / 301 / 400 全綠;CLAUDE.md §4 新契約逐字寫「中位取最近 300 筆」 | LOW | CONFIRMED(LOW→LOW:四顆突變全存活;構造只要求窗長落在 (0, 600) 且能翻轉中位;漂掉只改 `big_lots_120s` 命中數(研究欄),不改任何訊號是否發出) | Nice to Have | `auto-fix` | 補一案讓第 301 筆是否入母體翻轉結果(300 筆 1 張 + 1 筆 100 張的排列) |
| F-08 | `test_signal_hub.py:1750` 「日 K 不足」INFO 只斷 `"5" in lines[0]`(實得根數),需求根數 `(需 6)` 未斷;log 寫錯 `cdp_gate_days` 仍綠;CLAUDE.md 盤後判準「整批全『日 K 不足』= 抓取根數被改小」正是讀這兩個數 | LOW | CONFIRMED(LOW→LOW:突變體「第三個 arg −1」131 passed 存活;姊妹案 docstring 明寫「不得印成『只有 6 根(需 6)』」卻無案斷「需 6」) | Nice to Have | `auto-fix` | 改斷 `"只有 5 根(需 6)"` 子字串 |
| F-09 | `test_signal_hub.py:3195` `_fmt_secs` 是第三份時刻格式化微變體(`test_signal_policy._fmt` / `test_signal_state._ms_time`),且定義在檔尾唯一使用者之後(同檔慣例 helper 緊接使用者之前) | LOW | PARTIAL(LOW→LOW:「重複」半邊 REFUTED —— 三份輸入域不同(整數秒 / 浮點秒 / 毫秒),且 `grep "^def _bar("` 19 檔各持私有 helper 是 repo 既有形狀、`tests/helpers/` 無格式化先例;「位置」半邊 CONFIRMED —— 唯一使用者在 :3175、同檔 `_sweep_group` 緊接 `TestSweepCluster` 之前) | Nice to Have | `ask-user` | 只剩可讀性偏好(上移到使用者前);要不要動由 user 拍板 |
| F-10 | `test_signal_policy.py:186` round-1 F-06 收修的 bool / 非數值守門(`_emit_policies` 與 `format_policy_group_text` 各一處)零測試;產生點 `_advance_big_lots` 恆回 int,bool 只能由手改 jsonl / 未來新產生點帶入 | LOW | CONFIRMED(LOW→LOW:`grep "big_lots_120s.*True\|BIG_LOTS_KEY: True" tests/ frontend/src` 零命中;守門所防輸入在現行拓撲產不出來,屬防禦性程式碼的測試缺口) | Nice to Have | `ask-user` | 為不可達輸入補案是 user 對防禦性測試密度的偏好;要補 = 純函式層一案(`detail={BIG_LOTS_KEY: True}` → 頂層 None) |
| F-11 | `test_signal_rules.py:1047` v4→v5 撞名 WARNING 只斷 count 與 levelname,未斷 `skip_note`「(放量離開種子沒進去 = 影子期 rail 零放量離開列)」;v3→v4 同型案(`:954-955`)依 review F-29 斷後果句 | LOW | CONFIRMED(LOW→LOW:突變體「v4→v5 的 skip_note 清空」212 passed 存活;`:971` 的「放量離開」抓的是規則名不覆蓋 skip_note) | Nice to Have | `auto-fix` | 補 `"rail 零放量離開列" in hits[0].getMessage()` 一行,與姊妹案同口徑 |
| F-12 | `signal_hub.py:1195` `"sweep": dict(detail)` 是第二次淺拷貝(1153 行已 `dict(event.detail or {})`),讀起來像在防別名 | LOW | REFUTED(LOW→LOW:1195 位於 `for policy in ctx.hits:` **迴圈內**,同 dict 字面的 `"self": dict(me)` / `[dict(p) for p in ctx.peers]` 同手法 = 每列自己一份;同 tick 多政策列是常態(`test_signal_policy.py:284` `["B-a","B-b"]`、`:368` `["P","S"]`),拿掉會讓多列共用同一顆 dict) | 參考用 | `no-op` | 兩次拷貝防的不是同一件事,刪掉會引入真實別名;不是缺陷 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: cc3cd222c50a381499fc action=auto-fix
F-02 finding_uid: d0e9ffac666699a55345 action=auto-fix
F-03 finding_uid: 7ddbc5619e3938ffb6e8 action=auto-fix
F-04 finding_uid: 8432ed56fbf4d719fdf3 action=auto-fix
F-05 finding_uid: 7dd212ad8d301d65499f action=auto-fix
F-06 finding_uid: 02c73ead59cd885ea09a action=auto-fix
F-07 finding_uid: 806a5de91e5b4dad9067 action=auto-fix
F-08 finding_uid: da2731c9603af66c10ba action=auto-fix
F-09 finding_uid: 026bcfbba1c28da9173f action=ask-user
F-10 finding_uid: e071edf1d0c030b507ba action=ask-user
F-11 finding_uid: a4f7e30decd440f2ac2e action=auto-fix
F-12 finding_uid: 9ae5056d957a90170e0e action=no-op

### Inline Comments per Finding（直接複製貼到 PR review）

#### #1 檔頭還寫「六類訊號」,第七類放量離開沒進清單

**File**: `copycat/live/signal_state.py`
**Line**: 3

**Comment**:
```
這支檔頭的六類清單是「寫或改 .py 前先讀」的第一眼資訊,本 PR 加了第七類卻沒更新;同檔下面
SWITCH_KEYS 註解已經是「#226 起七鍵」、測試也叫 test_seven_switch_keys_and_kind_map,只剩這句漂著。
CLAUDE.md:60 的結構樹那行 signal_state(CDP 穿越/爆拉跌/爆量/鎖板/掃單簇) 也一起補 —— 那行從 #174 起就漏了爆拉回檔。

改成「七類訊號:… / 掃單簇 / 放量離開」就好。
```

#### #2 分子那根日 K 收盤是 0 的話,會被記進「漲幅不足」桶而不是壞資料

**File**: `copycat/server/signal_hub.py`
**Line**: 986

**Comment**:
```
_gate_return_pct 只擋分母 close[-6] ≤ 0;最後一根 close[-1] ≤ 0 時算出 −100%,走 986 行的
「前 5 日累計 -100.00% < +5.00%」INFO → 盤後 grep "CDP 列閘" 會把壞資料當成一檔真的不合格。
閘的結果本身是對的(CDP 一樣不評),只是 round-1 F-02 要求「兩種原因分得出來」只做了分母半邊。

_gate_return_pct 的 `if base <= 0` 擴成 `if base <= 0 or done[-1]["close"] <= 0`,
WARNING 文案改「首尾日 K 收盤 ≤ 0(壞資料)」即可。
```

#### #3 W-14 那句「開銷 = 每 tick 一次 deque append」低估了

**File**: `.claude/mod/signal-context-trio/change-spec.md`
**Line**: 53

**Comment**:
```
實作上每條規則的 detector 都在 enabled gate 之前無條件跑 _eval_breakout(_dwell / _break 兩份 dict,
離帶時還配 _Dwell dataclass + set),非 vol_breakout 的 slot 只是推進不產出;實測 enabled 只有
vol_burst 的 detector 餵兩萬筆 tick 後 _dwell / _big_hits 都有狀態,4.33 µs/tick/detector。
「bounded」的結論沒錯(30 條規則 × 4.33 µs),但理由句會讓下一個加 kind 的人低估 N 條規則的乘法。

W-14 改寫成:兩軸狀態機 per-detector 各一份;非該 kind 的 slot 只推進不產出;per-tick O(1);中位只在候選 tick 算。
```

#### #4 reset_day 那條大單測試,前置命中本來就在 120 s 窗外 —— 不清 hits 也是 0

**File**: `tests/live/test_signal_state.py`
**Line**: 1518

**Comment**:
```
前置大單打在 09:59:30.000,發訊在 10:01:30.500,窗起點是 09:59:30.500 → 就算 reset_day 完全忘了清
_big_hits,那一筆也會被窗自己剪掉,正常跟突變都是 0。突變體「reset_day 不清 _big_hits」跑整檔
113 passed 存活;對照 drop_code 不 pop / reset_day 不清 _dwell 兩顆姊妹突變都被殺。
跨日殘留是真風險(secs 是自午夜秒數,昨日 10:00 的命中會落進今日 10:01 的窗)。

前置那筆改 "10:00:30.000"(窗內)就鑑別得了:正常 0、突變 1。
```

#### #5 「有成交分鐘 ≥ 4」這顆地板沒有邊界案,改 3 / 5 / 8 / 10 全綠

**File**: `tests/live/test_signal_state.py`
**Line**: 1622

**Comment**:
```
_BREAKOUT_MIN_MINUTES = 4 是研究 len(vols) >= 4 的線上對應,唯一碰到它的案只給 2 個有成交分鐘,
其餘全是 10 / 11 分鐘 —— 常數改成 3 / 5 / 8 / 10 跑整檔都 113 passed。同 feature 的其他邊界
(第 30 筆、窗含端點、帶含端點、停留 599 vs 600)都釘得精確,獨缺這顆;研究同源常數被靜默改掉零訊號。

補兩案:恰 4 個有成交分鐘 → 發;3 個 → 不發。
```

#### #6 docstring 說釘了「方向缺值退向上」,其實一條斷言都沒有

**File**: `tests/server/test_signal_hub.py`
**Line**: 2614

**Comment**:
```
只測了 direction="up" / "down" 兩列;把 _kind_text 的三元反轉成 '向上' if d == 'up' else '向下'
照樣 177 passed。線上 direction 恆由 detector 填,缺值只在舊列 / 外來列出現,後果止於一則文案的方向字,
所以不重 —— 但 docstring 宣稱釘了而沒釘,後手會以為有保護。前端 signal-model.test.ts:350 同樣沒補缺 direction 案。

後端加一列 self._row(kind="vol_breakout", pct=4.0)(不帶 direction)斷「放量向上離開 4.0 倍」;
前端 kindLabel 補同一案(direction: null)。
```

#### #7 「最近 300 筆」的 300 沒被釘住

**File**: `tests/live/test_signal_state.py`
**Line**: 1496

**Comment**:
```
_BIG_LOT_MEDIAN_TICKS 改 200 / 299 / 301 / 400 整檔全綠 —— 這案的構造(300 筆 100 張 + 300 筆 1 張)
只要求窗長落在 (0, 600) 且能翻轉中位。CLAUDE.md §4 新契約逐字寫「中位取最近 300 筆」,對帳靠它同源。
影響只到 big_lots_120s 的命中數(研究欄),不改任何訊號是否發出。

補一案讓第 301 筆是否入母體會翻轉結果,例如 300 筆 1 張 + 再 1 筆 100 張的排列。
```

#### #8 「日 K 不足」那行只斷了實得根數,需求根數 (需 6) 沒斷

**File**: `tests/server/test_signal_hub.py`
**Line**: 1750

**Comment**:
```
斷言是 "日 K" in lines[0] and "5" in lines[0];把 log 第三個參數寫錯成 cdp_gate_days(印成「只有 5 根(需 5)」)
照樣 131 passed 存活。CLAUDE.md 的盤後判準「整批全『日 K 不足』= 抓取根數被改小」正是靠這兩個數指向。
姊妹案的 docstring 還寫「不得印成『只有 6 根(需 6)』」,卻沒有任何一案斷過「需 6」。

改斷 "只有 5 根(需 6)" 子字串。
```

#### #9 _fmt_secs 放在檔尾、在唯一使用者之後

**File**: `tests/server/test_signal_hub.py`
**Line**: 3195

**Comment**:
```
「第三份時刻格式化」這半不成立:test_signal_policy._fmt 吃浮點秒帶毫秒、test_signal_state._ms_time 吃毫秒、
這份吃整數秒恆 .000,輸入域不同;而且 tests/ 下 19 檔各持自己的 _bar 變體本來就是 repo 形狀。
剩下的只是位置:定義在 :3195、唯一使用者在 :3175,同檔慣例是 helper 緊接使用者之前(_sweep_group 在 TestSweepCluster 前)。

要動就把它上移到 TestVolBreakoutRule 之前;不動也行,純可讀性。
```

#### #10 round-1 F-06 補的 bool 守門,零測試

**File**: `tests/server/test_signal_policy.py`
**Line**: 186

**Comment**:
```
_emit_policies 與 format_policy_group_text 各一處「bool 先擋」是 round-1 review 要來的改動,
但 grep tests/ frontend/src 找不到任何 big_lots_120s 帶 True 的案;產生點 _advance_big_lots 恆回 int,
這輸入現行拓撲產不出來,所以是防禦性程式碼的測試缺口,不是功能缺口。

要補的話一條純函式層案就夠:detail={BIG_LOTS_KEY: True} → 政策列頂層 None、Discord 第二行不印「大單」;
不補也說得過去,看你對防禦性測試密度的偏好。
```

#### #11 v4→v5 撞名 WARNING 的後果句沒人斷

**File**: `tests/test_signal_rules.py`
**Line**: 1047

**Comment**:
```
只斷了 count 與 levelname;把 _migrate_v4 傳給 _append_seed 的 skip_note 整段清空,212 passed 照綠。
v3→v4 的同型案(:954)依 review F-29 有斷「零政策列」那句後果;這裡少了「(放量離開種子沒進去 = 影子期 rail 零放量離開列)」的唯一讀者。
(:971 的 "放量離開" in hits[1] 抓的是規則名,不算。)

補一行 assert "rail 零放量離開列" in hits[0].getMessage()。
```

#### #12 那個 dict(detail) 不是多餘的 —— 每列政策列要自己一份

**File**: `copycat/server/signal_hub.py`
**Line**: 1195

**Comment**:
```
不是 PR 缺陷,不用改。1153 行的 dict(event.detail) 是為了讓 pop 不動到事件物件;1195 行的 dict(detail)
在 for policy in ctx.hits: 迴圈裡,跟同一個字面裡的 "self": dict(me) / [dict(p) for p in ctx.peers]
是同一手法 = 每列自己一份。同 tick 多政策列是常態(測試有 ["B-a","B-b"] / ["P","S"] 兩案),
拿掉會讓多列共用同一顆 dict。
```

## CC 主軸原始 findings(first-pass, context-aware)

python-reviewer ×2(chunked;requested=opus),逐字要點;reviewer 原編號 → 發現總覽:R-A1→F-01、R-A2→F-02、R-A3→F-12、R-A4→F-03、R-B1→F-04、R-B2→F-05、R-B3→F-06、R-B4→F-07、R-B5→F-08、R-B6→F-09、R-B7→F-10、R-B8→F-11。

chunk A 逐條追過機制、確認**不成立**故不報的候選(reviewer 原文):(a) S-01 收修(刪 `else pop`)是否讓「合格離帶」覆蓋在飛 pending —— 不可能,`min_dwell_secs` 值域下限 60 s 保證合格離帶必跨分鐘界,步驟 (1) 已先刪;(b) `avg` 除零 —— `dwell.vol ≥ 1`、`n_min ≥ 4`;(c) `_quiet_seed_rule` 與原 `_sweep_seed_rule` 逐鍵 / 鍵序等價;(d) `sweep` 少鍵 —— `_emit` 於 `signal_hub.py:1076` 自行 `dict(event.detail)`,`_emit_policies` 的 `pop` 只動本地副本,無 aliasing;(e) 遷移鏈 `version <= 3` / `_migrate_v4` 無條件 —— v1..v4 皆正確接上;(f) 無界資料結構 / `reset_day` / `drop_code` 六份新狀態全數清理。chunk B 撤回一條:`test_band_is_inclusive_and_anchored_at_segment_first_tick` 的「錨」半邊實測「錨 = 前一筆價」突變會讓事件消失 → 殺得掉,不報;`_CACHE_VERSION` / `_HIST` sed 全檔替換逐處核對,斷言語意未被改動;刻意未替換的 `test_no_completed_bar_leaves_basis_none`(:1671)正確落在「零已完成 bar → WARNING」分支。

#### R-A1 [LOW] copycat/live/signal_state.py:3 — 模組 docstring 仍寫「六類訊號」,本 PR 加了第七類卻沒更新
問題:同檔 `SWITCH_KEYS` 上方註解已改「#226 起七鍵」、測試也叫 `test_seven_switch_keys_and_kind_map`,只有檔頭那句還是六類且不含「放量離開」;`CLAUDE.md:60` 的結構樹同一份清單也沒加(該行 base 上就已漏 `surge_pullback`)。影響:零 runtime;檔頭是 backend-conventions 要求先讀的第一眼資訊。修法:檔頭改七類;`CLAUDE.md:60` 補「爆拉回檔 / 放量離開」。search-proof:`grep -rn "六類|六種|七類|七種"` 五檔 → 只有 `signal_state.py:3`;`grep -n "signal_state(CDP" CLAUDE.md` → :60。anchor:`六類訊號:CDP 五線穿越 / 爆拉跌 / 爆拉回檔 / 爆量 / 鎖漲跌停與打開 / 掃單簇。設計要點:`

#### R-A2 [LOW] copycat/server/signal_hub.py:986-994 — F-02 的「壞資料 vs 政策」分講只做了分母半邊
問題:`_gate_return_pct` 只對 `base <= 0` 回 None;若 `done[-1]["close"] <= 0`,算出 −100.00% 走 `elif gate < cdp_gate_pct` → INFO「前 5 日累計 -100.00% < +5.00%」。影響:CDP 停掉的結果是對的(修前反而會拿 close=0 去 `compute_cdp`,是改善);但盤後 `grep "CDP 列閘"` 會把壞資料歸進「漲幅不足」桶。修法:`if base <= 0 or done[-1]["close"] <= 0`,WARNING 文案改「首尾日 K 收盤 ≤ 0」。search-proof:`fetch_daily_bars` 上游不濾 0 價 bar(CLAUDE.md §4 已記 TC4 會送 0 價 bar);`TestCdpGate` 只有 `test_zero_close_base_is_bad_data_warning` 鎖分母。anchor:`        elif gate < self._cfg.cdp_gate_pct:`

#### R-A3 [LOW] copycat/server/signal_hub.py:1195 — `dict(detail)` 是第二次淺拷貝,讀起來像在防 `event.detail` 被改
問題:`detail` 於 1153 行已是 `dict(event.detail or {})` 的私有副本、只在本函式內 `pop` 一次,1195 再包一層 `dict()` 沒有防護作用。修法:`"sweep": detail,`。search-proof:`grep -n "detail" signal_hub.py` → 寫入點 1076 / 1153 / 1156 / 1195,無第三個讀者持有引用。anchor:`                "sweep": dict(detail),`(內部複查 REFUTED,見下)

#### R-A4 [LOW] .claude/mod/signal-context-trio/change-spec.md:53 — W-14 的熱路徑成本敘述與實作不符(低估)
問題:W-14 寫「非掃單簇規則的 detector 不維護大單狀態以外的新東西 … 開銷 = 每 tick 一次 deque append」;實作上每條規則的 detector 都跑完整 `_eval_breakout` 狀態機,`enabled = frozenset({rule["kind"]})` 保證非 `vol_breakout` slot 永不發事件。影響:實測 `median` 於 300 長 deque 3.2 µs,結論 bounded 為真,但理由句錯。修法:改寫 W-14。search-proof:`signal_hub.py:477` per-rule enabled、`:624` 逐 slot evaluate。anchor:`- W-14 熱路徑:大單中位只在候選 tick(外盤且價升)才算;非掃單簇規則的 detector 不維護大單狀態以外的新東西(狀態是 per-detector,但只有掃單簇規則讀它;開銷 = 每 tick 一次 deque append)。`

#### R-B1 [MEDIUM] tests/live/test_signal_state.py:1515-1521 — `test_reset_day_clears_lots_and_hits` 釘不住它宣稱的「舊命中不得殘留」
問題:前置大單 09:59:30.000,發訊 10:01:30.500,窗起點 09:59:30.500 —— 就算 `reset_day` 不清 `_big_hits`,那一筆也會被 120 s 窗剪掉,兩邊都是 0。影響:跨日殘留是真風險,這條是唯一守門卻不 discriminate。修法:前置改 `"10:00:30.000"`。search-proof:scratchpad `mut_reset2.py` 模擬 reset_day 忘清 `_big_hits`:`09:59:30.000 clean=0 mutant=0`、`10:00:30.000 clean=0 mutant=1`。anchor:`        self._big(det, "09:59:30.000")`

#### R-B2 [MEDIUM] tests/live/test_signal_state.py:1618-1624 — 迴盪「有成交分鐘 ≥ 4」地板(spec Q10)整段未釘
問題:唯一案例只給 2 個有成交分鐘,其餘全 10 分鐘 —— 門檻值本身落在寬帶裡沒有邊界案。影響:研究同源常數靜默收緊 = 薄股整類不再發,零錯誤訊號。修法:補恰 4 → 發 / 3 → 不發。search-proof:`_BREAKOUT_MIN_MINUTES` 改 3/5/6/9/10 跑 `-k VolBreakout` 皆 12 passed,到 11 才 6 failed(對照 `_BIG_LOT_MIN_TICKS` 改 29/31 立刻紅)。anchor:`        assert self._bo(det, 50_000, 10, self._T0 + 590) == []  # 只有兩個有成交的分鐘`

#### R-B3 [MEDIUM] tests/server/test_signal_hub.py:2613-2619 — docstring 宣稱釘 W-11「方向缺值退向上」,但零斷言
問題:只測 `direction="up"` / `"down"`;三元反轉照綠,W-11 的舊列 / 舊 jsonl 會整批印成「放量向下離開」。修法:加 `self._row(kind="vol_breakout", pct=4.0)` 斷「放量向上離開」。search-proof:實跑 `format_signal_text` 缺欄與 `direction=None` 皆回「放量向上離開 4.0 倍」—— 行為對,測試沒蓋。anchor:`        """#226:「放量向上 / 向下離開 x.x 倍」與前端 \`kindLabel\` 逐字;方向缺值退向上(與 limit_* 同慣例)。"""`

#### R-B4 [LOW] tests/live/test_signal_state.py:1496-1507 — 中位母體「最近 300 筆」只釘了「有窗 vs 整天」,沒釘 300
問題:`_BIG_LOT_MEDIAN_TICKS` 改 200 / 299 / 301 / 400 全部 13 passed;CLAUDE.md §4 新契約逐字寫「中位取最近 300 筆」。修法:補一案讓第 301 筆是否入母體會翻轉結果。anchor:`    def test_median_uses_the_most_recent_300_ticks(self) -> None:`

#### R-B5 [LOW] tests/server/test_signal_hub.py:1750 — 「日 K 不足」INFO 只斷了實得根數,沒斷需求根數
問題:`"5" in lines[0]` 只認 `len(done)`;把 log 的 `cdp_gate_days + 1` 寫成 `cdp_gate_days` 仍綠。修法:改斷 `"只有 5 根(需 6)"`。anchor:`            assert len(lines) == 1 and "日 K" in lines[0] and "5" in lines[0]`

#### R-B6 [LOW] tests/server/test_signal_hub.py:3195-3198 — `_fmt_secs` 是第三份時刻格式化微變體,且置於唯一使用者之後
問題:`test_signal_policy._fmt`、`test_signal_state._ms_time` 已有兩份;新這份定義在檔尾 3195 行,而本檔其餘模組層 helper 全在 85–530 行。修法:上移到 `_tick` 附近或沿 `_fmt` 口徑。anchor:`def _fmt_secs(secs: int) -> str:`

#### R-B7 [LOW] tests/server/test_signal_policy.py:186 — round-1 F-06(bool / 非數值守門)收修後零測試
問題:`_emit_policies` 的 `isinstance(big_raw, (int, float)) and not isinstance(big_raw, bool)` 與 `big_lots=None` 兩分支無任何 case。修法:純函式層一案(`detail={BIG_LOTS_KEY: True}` → 頂層 None)。anchor:`            assert msg["big_lots_120s"] == 0 and raw["detail"]["big_lots_120s"] == 0`

#### R-B8 [LOW] tests/test_signal_rules.py:1046-1047 — v4→v5 撞名 WARNING 未斷 `skip_note`,與 v3→v4 同位測試口徑不一致
問題:v3→v4 同型測試依 review F-29 斷 `"零政策列" in hits[0].getMessage()`;新的 v4→v5 版只斷 count 與 levelname。修法:補 `"rail 零放量離開列" in hits[0].getMessage()`。anchor:`        assert len(hits) == 1 and hits[0].levelname == "WARNING"`

### Per-file accounting(35/35,reviewer 原文要點)

chunk A(27):
- `.claude/mod/signal-context-trio/change-spec.md` — R-A4(W-14 成本敘述);其餘 §0/§1/§3/§5 與 code 逐條對得上。
- `.claude/mod/signal-context-trio/code-review-round-1.json` — REVIEWED_NO_ISSUES(7+4 條 disposition 與五筆收修 commit 一一對應)。
- `.claude/mod/signal-context-trio/evidence/health.json` — INTENTIONALLY_SKIPPED — 證據 JSON(git_sha 8bc115ab 與 verification §2 一致)。
- `.claude/mod/signal-context-trio/evidence/rail_2026-09-14.png` — INTENTIONALLY_SKIPPED — 截圖證據。
- `.claude/mod/signal-context-trio/evidence/rules.json` — INTENTIONALLY_SKIPPED — 證據 JSON(抽查:8 卡涵蓋七 kind)。
- `.claude/mod/signal-context-trio/evidence/rules_dialog_2026-09-14.png` — INTENTIONALLY_SKIPPED — 截圖證據。
- `.claude/mod/signal-context-trio/evidence/rules_edit_breakout_2026-09-14.png` — INTENTIONALLY_SKIPPED — 截圖證據。
- `.claude/mod/signal-context-trio/evidence/sidecar_server.py` — REVIEWED_NO_ISSUES(neutralize 在 create_app 前、worktree import 錨點 assert、port 非 8721、劇本數字與 verification 4.3564 倍推導一致)。
- `.claude/mod/signal-context-trio/evidence/signals_today.json` — INTENTIONALLY_SKIPPED — 證據 JSON(抽查:2317 零 cdp_cross、big_lots_120s 出現 2 次 = detail + 政策列頂層)。
- `.claude/mod/signal-context-trio/evidence/state_2330.json` — INTENTIONALLY_SKIPPED — 證據 JSON。
- `.claude/mod/signal-context-trio/evidence/stock_page_2026-09-14.png` — INTENTIONALLY_SKIPPED — 截圖證據。
- `.claude/mod/signal-context-trio/verification.md` — REVIEWED_NO_ISSUES(紅先行三列、+2 測試數差、S-01 不重跑側車理由互洽)。
- `CLAUDE.md` — R-A1(:60 結構樹漏列;§4 三條與 code 逐字核過:`_BASIS_BARS_SLACK=3`、閉區間下界、缺欄不印皆對)。
- `CONTEXT.md` — REVIEWED_NO_ISSUES(三詞常數與 code 一致)。
- `copycat/live/signal_state.py` — R-A1。
- `copycat/server/signal_hub.py` — R-A2 / R-A3。
- `copycat/signal_rules.py` — REVIEWED_NO_ISSUES(`_quiet_seed_rule` 等價、v4→v5 不翻旗、`_SUPPORTED_VERSIONS` 自動跟上、`rule_config` 尾端 raise 仍是唯一機驗)。
- `copycat/signals_config.py` — REVIEWED_NO_ISSUES(八欄註解齊、`cdp_gate_days < 1` 由 hub 建構期 raise)。
- `frontend/src/components/stock/SignalRail.test.tsx` — REVIEWED_NO_ISSUES(mid-test `cleanup()` 是 repo 既有 pattern;新舊列兩態各一條)。
- `frontend/src/components/stock/SignalRail.tsx` — REVIEWED_NO_ISSUES(`toneOf` 併入 limit_* 分支,方向語意相同)。
- `frontend/src/components/stock/SignalRulesDialog.test.tsx` — REVIEWED_NO_ISSUES(七類下拉序 = 後端 RULE_KINDS 序)。
- `frontend/src/components/stock/SignalRulesDialog.tsx` — REVIEWED_NO_ISSUES(`KIND_LABEL` 為 `Record<RuleKind,…>` 漏加 tsc 會紅;`ruleSummary` 字面與截圖一致)。
- `frontend/src/hooks/useSignalRules.ts` — REVIEWED_NO_ISSUES。
- `frontend/src/lib/signal-model.test.ts` — REVIEWED_NO_ISSUES(kindLabel 三態 + big_lots 0 / 缺欄兩態皆釘;缺 direction 案見 F-06)。
- `frontend/src/lib/signal-model.ts` — REVIEWED_NO_ISSUES(`bigLotsPhrase` 以 typeof + `Number.isFinite` 守門,與 wire `number | null` 一致)。
- `frontend/src/lib/signal-param-parity.test.ts` — REVIEWED_NO_ISSUES(七 kind 健檢 + 0.6/600/4 字面 golden)。
- `frontend/src/lib/signal-params.ts` — REVIEWED_NO_ISSUES(min/max/integer 與後端一致)。

chunk B(8):
- `tests/fixtures/signal_param_specs.json` — REVIEWED_NO_ISSUES(`vol_breakout` 三鍵值域與 `PARAM_SPECS` 一致;全 float → `int_keys` 正確不動)。
- `tests/live/test_signal_state.py` — R-B1 / R-B2 / R-B4。
- `tests/server/test_signal_hub.py` — R-B3 / R-B5 / R-B6。
- `tests/server/test_signal_outcome.py` — REVIEWED_NO_ISSUES(`_policy_row` 加 `big_lots_120s: 0` 即讓既有 byte 比對覆蓋 W-8)。
- `tests/server/test_signal_policy.py` — R-B7。
- `tests/server/test_signal_routes.py` — REVIEWED_NO_ISSUES(`_SEEDED_KINDS` 加一值,兩處順序斷言涵蓋 v5 種子序)。
- `tests/test_signal_rules.py` — R-B8。
- `tests/test_signals_config.py` — REVIEWED_NO_ISSUES(八顆新預設值逐一釘住)。

## 內部複查結果(同軸 code-reviewer,取代 4.2;非跨軸證據)

| # | 原編號 | Verdict | 原始 → 校正 severity | Evidence(要點) | baseline | 單軸可信度 |
|---|---|---|---|---|---|---|
| F-01 | R-A1 | CONFIRMED | LOW → LOW | `signal_state.py:3` 逐字六項無放量離開;`signal_rules.py:43-51` RULE_KINDS 七值;`CLAUDE.md:60` 結構樹未動(`git diff 1a032b9b..21385338 -- CLAUDE.md` 只在 §4 +22 行),「base 上已漏 surge_pullback」為真 | 慣例支持 | 高 —— 純文字比對;價值等同 typo |
| F-02 | R-A2 | PARTIAL | LOW → LOW | 實跑 `_gate_return_pct`:close[-6]=100、close[-1]=0 → −100.0(非 None),落 986 行 INFO 桶;但 CDP 仍 None(預設 5.0,−100 必不過閘),差異止於 log 分桶;反例只在 `cdp_gate_pct ≤ −100`(無 sign 驗證)時成立 | 慣例支持 | 高 —— round-1 F-02 已把「兩種原因分得出來」立為本 PR 口徑,分子半邊沒跟;請以 log 分桶一致性立案 |
| F-03 | R-A4 | CONFIRMED | LOW → LOW | `signal_state.py:370-371` 在 enabled gate 之前無條件跑兩軸;detector per-rule(`signal_hub.py:308` / `:476` / `:624`);bench enabled 只有 vol_burst 餵 20,000 tick:4.33 µs/tick/detector,`_dwell` / `_big_hits` 都有狀態;上限 30 條規則 × 4.33 µs 仍 bounded | 無先例 | 中 —— 事實確鑿,是規格文件措辭層級 |
| F-04 | R-B1 | CONFIRMED | MEDIUM → MEDIUM | 突變體 `reset_day` 不清 `_big_hits` → 113 passed 存活;`drop_code` 不 pop / `reset_day` 不清 `_dwell` 兩顆姊妹都被殺;根因 `signal_state.py:874` window_start = 09:59:30.500 先 popleft;前置改 10:00:30.000 → 正常 0 / 突變 1 | 慣例支持 | 高 —— 突變體與修法鑑別性皆實跑 |
| F-05 | R-B2 | CONFIRMED | MEDIUM → MEDIUM | `_BREAKOUT_MIN_MINUTES` 改 3 / 5 / 8 / 10 → 113 passed 全存活(3 再加 hub + policy 177 passed);唯一觸地板案 2 分鐘,其餘 `_dwell(minutes=10)` 或 11;姊妹 `_BIG_LOT_MIN_TICKS` 29 / 31 兩顆都被殺、`breakout_min_dwell_secs` 有 599 / 600 | 慣例支持 | 高 —— 八次突變跑是機械事實 |
| F-06 | R-B3 | PARTIAL | MEDIUM → **LOW** | 突變體 fallback 反轉 → 177 passed 存活,缺口為真;但 `direction` 線上恆由 `signal_state.py:967` 填,缺值只在舊 / 外來列,後果止於文案方向字;前端 `signal-model.test.ts:350-352` 同樣無缺 direction 案,`signal-model.ts:152-153` ↔ `signal_hub.py:163` 逐字契約兩邊同時無鎖 | 慣例支持 | 高 —— 唯一修正 first-pass 的是 severity |
| F-07 | R-B4 | CONFIRMED | LOW → LOW | `_BIG_LOT_MEDIAN_TICKS` 改 200 / 299 / 301 / 400 → 113 passed 四顆全存活;構造只要求窗長落 (0, 600);對照 `_BIG_LOT_MIN_TICKS` 29 / 31 皆 FAILED | 慣例支持 | 高 —— 值不值得補案(研究欄 vs 發訊行為)由 user 權衡 |
| F-08 | R-B5 | CONFIRMED | LOW → LOW | 突變體攔截 `logger.info` 第三 arg −1 → 131 passed 存活;「5」來自 `len(done)`,訊息變「只有 5 根(需 5)」仍含 5;`grep "需 6"` 全 repo 只命中兩行 docstring | 慣例支持 | 高 —— 一行修法 |
| F-09 | R-B6 | PARTIAL | LOW → LOW | 重複半邊 REFUTED:三份輸入域不同(整數秒 / 浮點秒帶 F-36 進位註解 / 毫秒);`grep "^def _bar("` 19 檔各持變體;`tests/helpers/` 六支全是 boot / fake / wait 類無格式化先例。位置半邊 CONFIRMED:`:3195` 定義、唯一使用者 `:3175`、同檔 `_sweep_group` 緊接 `TestSweepCluster` 前 | 慣例衝突 | 高 —— 19 檔 `_bar` 是可重複 grep 事實;位置屬格式偏好 |
| F-10 | R-B7 | CONFIRMED | LOW → LOW | `grep "big_lots_120s.*True\|BIG_LOTS_KEY: True" tests/ frontend/src` 零命中;兩處守門(`signal_hub.py:1157-1161` / `:248-250`)無 bool 案;產生點 `signal_state.py:876` `len(hits)` 恆 int → 防禦性程式碼的測試缺口 | 慣例支持 | 中 —— 零覆蓋可單軸採信;為不可達輸入補案屬 user 偏好 |
| F-11 | R-B8 | CONFIRMED | LOW → LOW | 突變體 `tag == "v4→v5"` 時清空 `skip_note` → 212 passed 存活;`:1046-1047` 只斷 count 與 levelname;姊妹 `:954-955` / `:969-971` 有斷後果句;`:971` 的「放量離開」抓的是規則名 | 慣例支持 | 高 —— 姊妹案的斷法定義了應有強度 |
| F-12 | R-A3 | REFUTED | LOW → LOW | `signal_hub.py:1195` 在 `for policy in ctx.hits:`(:1176 起)迴圈內;同字面 `"self": dict(me)`(:1197)/ `[dict(p) for p in ctx.peers]`(:1200)同手法 = 每列一份;`test_signal_policy.py:284` `["B-a","B-b"]`、`:368` `["P","S"]` 證多政策同 tick 是常態;`signal_policy.py:52` POLICIES 固定序 | 慣例衝突 | 高 —— 迴圈位置是結構事實,直接駁回 |

## Action Items

Severity calibration:6c(移除既有防護類)— 本 PR 無此類 finding,免(列閘與守門都是**新增**防護)。6d-1(hedge cap)— F-02「若 `cdp_gate_pct ≤ −100`」、F-06「舊 / 外來列」、F-10「未來新產生點」皆為條件句,已在 Nice。6d-3(Must Fix 雙半條件)— 十二條全無 user-visible 重現路徑(F-02 差異止於 log 分桶;F-04 / F-05 / F-06 / F-07 / F-08 / F-11 是測試強度;F-01 / F-03 / F-09 是文件 / 可讀性;F-10 防禦性測試缺口;F-12 駁回),零阻擋出貨,無一落 Must / Should;依「MEDIUM / LOW → Nice to Have」與「REFUTED → 參考用」分級,MEDIUM 兩條(F-04 / F-05)不因 consensus 升級(單軸無 consensus)。未驗證前提檢查:F-02 實跑 probe、F-03 bench、F-04 / F-05 / F-06 / F-07 / F-08 / F-11 突變體實跑、F-01 / F-09 / F-10 / F-12 grep / 讀碼皆第一手;拿掉任何論據等級不變。Provenance cap:N-A。校準套用:無作者校準檔(`loger-w.md` 不存在)、本輪無套用。4.3b lone finding:本場 CC 單軸,十二條全 lone,「他軸為何漏」改答單軸可信度(見內部複查表末欄);F-01 / F-02 / F-04 / F-05 / F-06 / F-07 / F-08 / F-11 可獨立採信(實跑 / 突變體 / 逐字比對);F-03 / F-10 事實可信、處置是取捨;F-09 半駁半採、位置屬偏好(ask-user);F-12 REFUTED 落參考用。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

無。

### Nice to Have(可選優化)

- **F-04** `test_reset_day_clears_lots_and_hits` 前置大單改 `"10:00:30.000"`(窗內),讓「reset_day 不清 `_big_hits`」突變體紅。
- **F-05** `TestVolBreakout` 補「恰 4 個有成交分鐘 → 發 / 3 個 → 不發」兩案,釘 `_BREAKOUT_MIN_MINUTES`。
- **F-06** 後端 `test_vol_breakout_kind_text_by_direction` 加無 direction row 斷「放量向上離開」;前端 `kindLabel` 補 `direction: null` 案。
- **F-02** `_gate_return_pct` 擴 `or done[-1]["close"] <= 0`,WARNING 文案改「首尾日 K 收盤 ≤ 0」,並補一案(close[-1]=0 → WARNING 不落「漲幅不足」)。
- **F-07** `test_median_uses_the_most_recent_300_ticks` 補第 301 筆翻轉案。
- **F-08** `test_insufficient_history_is_not_qualified` 改斷 `"只有 5 根(需 6)"`。
- **F-11** `test_v4_seed_skipped_on_name_collision_warns` 補 `"rail 零放量離開列" in hits[0].getMessage()`。
- **F-01** `signal_state.py:3` 改七類 + `CLAUDE.md:60` 結構樹補「爆拉回檔 / 放量離開」。
- **F-03** change-spec W-14 敘述改寫(per-detector 兩軸狀態機、只推進不產出、per-tick O(1))。
- **F-09** `_fmt_secs` 上移到 `TestVolBreakoutRule` 之前 —— **ask-user**(純可讀性)。
- **F-10** bool 守門補一案純函式層(`detail={BIG_LOTS_KEY: True}` → 頂層 None)—— **ask-user**(防禦性測試密度偏好)。
- 九條 auto-fix 可併一筆 `test(backend,frontend)` + 一筆 `fix(backend)`(F-02 一行 runtime)+ 一筆 `chore(docs)` 收修;F-02 之外零 runtime 改動,prod 重啟時機不受影響。

### 參考用(任一軸驗證為 REFUTED / OUT_OF_SCOPE / PARTIAL 且不建議動 code)

- **F-12** `"sweep": dict(detail)` 第二次淺拷貝:CC 主軸判多餘 → 內部複查於 `signal_hub.py:1176-1200` 找到它在多政策列迴圈內、與同字面兩個姊妹拷貝同手法(每列一份),拿掉會讓同 tick 多列共用同一顆 dict → 不是缺陷,不動。

## 審查工具比較(qualitative)

- CC 主軸(python-reviewer ×2 chunked):context-aware;chunk A 對 runtime 四檔逐機制追過六個「看似成立」的候選(S-01 覆蓋、除零、種子等價、sweep 少鍵、遷移鏈、狀態清理)後全部撤回,只留文件 / log 分桶 / 可讀性四條;chunk B 以突變體實跑找出六條「測試不 discriminate」(F-04 / F-05 / F-06 / F-07 / F-08 / F-11)—— 純看 diff 抓不到,要對照姊妹案的精確邊界與研究常數同源要求。
- 內部複查(code-reviewer):同軸、非跨軸證據;12/12 齊,CONFIRMED 8 / PARTIAL 3 / REFUTED 1 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0;severity 下修 1(F-06 MEDIUM→LOW);一條以 bench 落地(F-03 4.33 µs/tick/detector)、一條駁回(F-12 迴圈內每列一份)、一條半駁(F-09 重複半邊 19 檔 `_bar` 慣例)。
- Codex / Gemini:N-A(user 停用),無跨軸重疊率可算;對抗式增益 N-A。
- REFUTED 率 8%(PARTIAL 25%):主軸命中率高,但同模型家族互驗;十二條全 Nice / 參考用 —— 對一個 two-axis round-1 已收修 11 條、所有 gate 綠、真環境八案 PASS 的 PR,這個分佈是預期的。

## 沒做的部分(結案對帳)

- Codex 中性軸:N-A —— user 明示停用(沿 #188 / #190 / #199 / #202 / #211 / #218 / #220 / #222 前例),未起軸、未 retry。
- Codex 對抗式軸:N-A —— 同上。
- Gemini Flash 軸:N-A —— user 明示停用。Gemini Pro:N-A(同上;Step 2.96 依前例不再問)。
- Step 2.98 Codex preset 詢問:N-A(Codex 停用,依前例不再問)。
- Cross-axis verification 4.1:N-A(無非 CC finding)。4.2:以同軸 code-reviewer 內部複查代替(PASS,12/12),**非跨軸證據**。4.3a consensus:N-A(單軸無 consensus);4.3b lone:十二條全 lone,處置見 Action Items。
- Review input binding:**verified**(`refs/pull/228/head` = headRefOid `21385338`,worktree detached 於該 SHA;merge-base = baseRefOid `1a032b9b`)。
- Blast radius(2.9):PASS(有跑)但空輸出跳過(`sem` 未安裝)。
- React-doctor(2.97):PASS,未引入新問題(`newCount 0`,changed 9 檔;既有 2 條不計)。
- Formal spec traceability(2.65):SKIPPED (C4_NO_NORMATIVE_CLAUSE);spec-compliance-reviewer 未派。
- Author calibration(2.2):無檔、本輪無套用。
- Reviewer 未重跑全量 pytest / vitest / ruff / pyright / validate:review worktree 純讀碼(chunk A 只讀 pytest 371 passed;chunk B 595 passed;內部複查各檔 113 / 131 / 177 / 212 passed 與突變體皆於 scratchpad 模擬,worktree 零改動);全量綠燈證據引自 PR 內 `verification.md` §4(出貨前實跑 pytest 3626 passed / 3 skipped、vitest 3074、ruff 0、pyright 0、tsc / eslint 0、react-doctor 無新 finding、validate 42/42)。
- 未驗前提(集中揭露):F-02「壞資料被誤用」在預設設定下不成立(只有 log 分桶差異;`cdp_gate_pct ≤ −100` 是理論路徑);F-03「bounded」的上限是以 30 條規則 × 單 detector bench 推算,未做 50 檔 × 30 規則的整體壓測;F-06 / F-10 的缺值 / bool 輸入在現行拓撲產不出來;F-09 位置與 F-12 拷貝是慣例 / 品味判定。皆已對應落 Nice / 參考用。
- 真環境:本 review 未另跑 server;PR 內側車八案(零 TC4)為出貨前證據,S-01 收修後未重跑側車(理由見 verification §4)。prod 尚未重啟、dist 尚未 build(部署前後端同版:規則視窗新 kind 需新 dist)。
