# PR #199 Code Review 比較報告 · SHA 6be7ff20

**Report projection schema**: 1

**PR**: [loger-w/copycat#199](https://github.com/loger-w/copycat/pull/199)
**標題**: mod(signals): 訊號影子政策層 —— 掃單簇事件 + 四條政策 P / B-a / B-b / S 分開推播與 jsonl、族群 = 自選群組、停 CDP 穿越 / 爆量推播(spec #192)
**作者**: loger-w
**分支**: `mod/signal-shadow-policies` → `master`
**變更**: 43 檔案, +4185 / -127
**審查日期**: 2026-09-07
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以收修 PR 處置,不阻擋任何出貨)
**Review input basis**: source repo id `R_kgDOTsITBg` + source SHA `6be7ff2055ef060d9b82f6594f0034d6ebf33600`;destination repo id `R_kgDOTsITBg` + destination SHA `53d8f15c8812c84138189600fb69749c78b0121e`;`input_binding: verified`(`refs/pull/199/head` FETCH_HEAD 逐字等於 headRefOid、review worktree HEAD 同值;base commit 本地可解析 = merge-base)
**Review continuity**: `source_continuity=CURRENT`(產報告前重抓 headRefOid `6be7ff20` 未變;分支已隨 rebase merge 刪除);`base_changed=true`(origin/master 自 `53d8f15c` 前進至 `1e58a083`,內容 = 本 PR 的 rebase merge 16 筆,其後零新 commit);`review_context_changed=false`(head 未動,base 前進即本 PR 自身落地)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用,沿 #188 / #190 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替(兩批各 25 條並行),非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer ×7 chunk(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model);內部複查=code-reviewer ×2(requested=opus / observed=UNAVAILABLE);security-reviewer N-A(無 trigger 面);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=43 → covered 23 / no-issues 14 / skipped 6 / **missed 0**(chunked: 是,7 chunk;14 source 檔 / 4312 diff 行超過 800 行門檻;chunk map 見「變更概要」)
**定位 (ENH-B)**: anchored exact 48 / ambiguous 2 / **FAILED 0**(50 條 anchor 逐字在 worktree grep:48 條唯一命中;2 條多重命中(#38 / #40)皆含 reviewer 自報行、取自報行)
**React-doctor (2.97)**: 未引入新問題(`--scope changed --base 53d8f15c --json`:newCount 1 / fixedCount 1 / baseTotalCount 2,changedFileCount 11 —— 那一條「new」與「fixed」是同一個 `no-high-complexity-react-function` `SignalRulesDialog` 函式因行號位移(base :156 → head :160)被重新識別,base 即已存在,主 tree master 全量掃描亦命中同函式;本 PR 未動該元件的控制流)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_SPEC_FILE_IN_REPO)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**Codex preset**: N-A(user 停用 Codex,無 preset)
**Gemini 軸**: N-A(user 停用)
**Provenance (2.55)**: N-A(base = master)
**審查軸狀態**: primary(python-reviewer ×7 chunk)PASS(50 findings + 43/43 per-file accounting)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 使用者輸入解析 / 環境憑證)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示「不用 Codex」)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示「不用 Gemini」)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(50/50 verdict 齊、兩批 ID 集合各精確相等、每列四欄齊)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-199`
**worktree HEAD**: `6be7ff2055ef060d9b82f6594f0034d6ebf33600`

**Report generation**: sha256:6e47c85b045402381312060eed82bbb36b09b23fa5317ef628659575dd00f858

---

## Spec 依據

- 此 PR 未附 spec / plan 檔(PR 檔案清單含 `.claude/mod/signal-shadow-policies/verification.md` 與 `code-review-round-1.json`,屬 closeout artifact,非 spec 樣式);spec 為 GitHub issue **#192**(32 條 user stories / Implementation Decisions / Testing Decisions 四條 seams / 白名單 W1–W12)+ tickets #193–#198,reviewer prompt 內嵌濃縮版並可 `gh issue view` 取全文。
- **⚠️ spec 作者 = PR 作者**(issue #192 author `loger-w` = PR 作者;out-of-scope 判定以此 spec 為據時,注意作者自寫 spec 的利益重疊)。
- 已知拍板偏離(reviewer 不得重報):即時判(多發 0.7%、零漏發)/ 回填走 `bars_range(tf="D")`(`DailyBar` 無 open)/ rail 第三行「同伴≥3%」字面 / 多組 WARNING 一檔一天一次 / 自己 chg round 2 / 政策卡 > 1900 字截斷 / open ≤ 0 留 null 不位移 / 三種百分比格式各屬版面 / `_QUIET_KINDS` 與 `_MIGRATE_QUIET_KINDS` 兩集合 / `implement` skill 不可由 agent 呼叫改走 `tdd`。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_SPEC_FILE_IN_REPO`(spec 是 GitHub issue、不是 repo 內檔案,無 `path:line` 可綁的 normative clause;0 clauses / 0 findings / 0 observations / 0 invalidated)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、tools=N-A(未派)。
- Author calibration(Step 2.2):無作者校準檔(`loger-w.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

本 PR = spec #192 六張 tickets(T1 規則模型 + 遷移 v4 / T2 掃單簇偵測器 + golden fixture / T3 政策層 + Discord 四行卡 / T4 T+1、T+2 回填 worker / T5 前端 / T6 文件)+ two-axis review 收修兩筆 + artifacts。Provenance N-A(base = master)。

| chunk | 檔案 | 類型 | 說明 |
|---|---|---|---|
| 1 | `.claude/mod/signal-shadow-policies/*`(9 檔:verification.md / code-review-round-1.json / evidence 7 檔) | 新增 | closeout artifacts:驗證證據、review 處置、側車腳本、截圖 |
| 1 | `.claude/skills/tc4-market-facts/SKILL.md`、`CLAUDE.md`、`CONTEXT.md` | 修改 | 同毫秒群 = 掃單事實;§4 五條契約 + §1 判準列;十個術語 |
| 1 | `copycat/fileio.py` | 修改 | `atomic_write_bytes`(零換行翻譯) |
| 1 | `copycat/live/signal_state.py` | 修改 | `_eval_sweep` 掃單簇偵測、`SignalEvent.detail`、`tick_secs`、SWITCH_KEYS 六鍵 |
| 1 | `copycat/server/app.py` | 修改 | hub 接線 `peers_fn` / `outcome_bars` |
| 2 | `copycat/server/signal_hub.py` | 修改 | `_emit` notify/detail、`_emit_policies`、四行卡、回填 worker、設定驗證 |
| 2 | `copycat/server/signal_policy.py` | 新增 | PeerQuote / 旗標 helper / resolve_groups / evaluate_policies / tod_bucket |
| 2 | `copycat/server/stock_engine.py` | 修改 | `policy_quotes` 行情快照 |
| 3 | `copycat/signal_rules.py`、`copycat/signals_config.py` | 修改 | sweep_cluster kind、遷移 v4、`_append_seed`、十二個設定鍵 |
| 3 | `frontend/src/**`(11 檔:signal-model / useSignalAlerts / SignalRail / SignalRulesDialog / signal-params / useSignalRules + 5 測試) | 修改 | 新 kind 文案、notify 閘、雙嗶、政策列三行 + chip、規則視窗 |
| 4 | `tests/fixtures/record_sweep_cluster_golden.py`、`sweep_cluster_golden.json`、`signal_param_specs.json`、`tests/live/test_signal_state.py`、`tests/server/test_signal_hub.py` | 新增 / 修改 | 研究 golden fixture 與產生腳本;偵測器與 hub 測試 |
| 5 | `tests/server/test_signal_outcome.py` | 新增 | 回填檔案 seam |
| 6 | `tests/server/test_signal_policy.py`、`test_signal_routes.py`、`test_stock_engine.py`、`test_stock_routes.py` | 新增 / 修改 | 政策層主 seam;引擎快照;接線 |
| 7 | `tests/test_signal_rules.py`、`tests/test_signals_config.py` | 修改 | 規則模型 / 遷移 / 設定測試 |

## 發現總覽

| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `CONTEXT.md:118` 術語寫「族群沒人鎖過」,code 只看同伴(自己鎖過不擋)(chunk 1 C1-F1) | MEDIUM | CONFIRMED(校正 LOW;原 MEDIUM):CONFIRMED,LOW:spec #192 Implementation Decisions 字面就是「非 peer_touched」,code 合規;drift 只在 CONTEXT.md / docstring 措辭,列上 `self.touched_upper` 有記,對帳可重算。 | Nice to Have | `ask-user` | 文件 vs code 二選一是語意拍板,不是筆誤 |
| F-02 | `copycat/fileio.py:3` 模組 docstring 還寫「兩個 helper」,現在是三個(chunk 1 C1-F2) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:`atomic_write_text:20`、`atomic_write_bytes:26`、`atomic_open_text:33` 三個;純文件。 | Nice to Have | `auto-fix` | 一行 docstring |
| F-03 | `copycat/live/signal_state.py:298` 「三道 gate 不推進任何狀態」的承諾已被掃單簇打破(chunk 1 C1-F3) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:`_eval_sweep:722-729` 群首筆 return [],觀察值不變;相鄰註解 305-307 已講例外,只有 docstring 那句失真。 | Nice to Have | `auto-fix` | docstring 對齊 |
| F-04 | `copycat/live/signal_state.py:104` frozen dataclass 裝 dict → 掃單簇事件不可 hash(目前沒人 hash)(chunk 1 C1-F4) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:probe `hash(SignalEvent(detail={...}))` → TypeError;grep 消費端只 list 傳遞,零 hash 呼叫點,latent。 | Nice to Have | `auto-fix` | 型別或註記二擇一,局部 |
| F-05 | `.claude/mod/signal-shadow-policies/evidence/fake_server.py:17` 取證腳本釘死已消失的 worktree 路徑,重跑必炸(chunk 1 C1-F6) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:probe 以同 sys.path 匯入,app.__file__ 落在別處、assert False;純 evidence 產物,不影響產品碼。 | Nice to Have | `auto-fix` | 路徑改自我定位兩行(深度已驗) |
| F-06 | `.claude/mod/signal-shadow-policies/verification.md:65` verification.md 的跑法與 vite 側車設定檔互斥(chunk 1 C1-F7) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:兩述至少一假;artifact 文件自相矛盾,無 runtime 影響。 | Nice to Have | `auto-fix` | 文件與檔頭對齊 |
| F-07 | `copycat/server/app.py:821` `live_engine = engine` 別名沒說為什麼(chunk 1 C1-F8) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:pyright probe 顯示 lambda 與 async def 都能捕捉已收斂的 `engine`(同段 :819 直接用 engine),窄化不是成立理由 → 用意未交代。 | Nice to Have | `auto-fix` | 一行註解或刪別名 |
| F-08 | `copycat/server/signal_hub.py:1321` 回填的「逾時」except 在 prod 走不到,逾時因此零記錄(chunk 2 C2-F2) | MEDIUM | CONFIRMED(校正 LOW;原 MEDIUM):CONFIRMED,LOW:dead except + 逾時訊號流失;列會在下一趟再補,無資料丟失,純可觀測性。`test_signal_outcome.py:256` 注入 HistoryTimeoutError 給了假信心。 | Nice to Have | `auto-fix` | 接線改回傳 status + 一行 WARNING |
| F-09 | `copycat/server/signal_hub.py:1271` 整檔嚴格解碼:一個壞位元組讓那一天整檔 5 天內都跳過(chunk 2 C2-F3) | MEDIUM | PARTIAL(校正 LOW;原 MEDIUM):PARTIAL,LOW:確實整檔跳過,但 except 有 WARNING 非靜默;`read_signals` 用 replace 是因為它不回寫,回填要位元組逐字保留、strict 反而避免把 U+FFFD 寫回檔案。 | Nice to Have | `ask-user` | 逐行 bytes 解碼是小改但牽涉回寫策略,拍板再動 |
| F-10 | `copycat/server/signal_hub.py:214` `format_policy_group_text` 對外但沒守「至少一列政策列」(chunk 2 C2-F4) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:Grep `format_policy_group_text` over `copycat/ tests/` → `signal_hub.py:99`(`__all__`)/ `:161`(註解)/ `:1432`(唯一 caller,前一行 `any(_is_policy(row) ...)` gate),tests 零直呼 → 目前不可觸發。 | Nice to Have | `auto-fix` | 兩行 guard |
| F-11 | `copycat/server/stock_engine.py:763` 每顆掃單簇事件對整份自選(≤150)組快照,hub 只讀幾個同伴(chunk 2 C2-F5) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:每檔 60 s 冷卻限住呼叫率,零 IO 仍成立,成本可忽略。 | Nice to Have | `auto-fix` | 加選配參數,R16 紀律不變 |
| F-12 | `copycat/server/stock_engine.py:778` no_data 的同伴連名字都被清空,姊妹 `quotes()` 不是這樣(chunk 2 C2-F6) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:no_data 的 chg_pct 亦 None 不入 quoted/peer_max,只是快照少了名字;無測試。 | Nice to Have | `auto-fix` | 一行拆開 name 與值欄位 |
| F-13 | `copycat/server/signal_policy.py:156` 政策順序不變式寫兩處;`tuple(policy_exclude_groups)` 是 no-op(chunk 2 C2-F7) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:純風格,零行為風險。 | Nice to Have | `auto-fix` | 兩行簡化 |
| F-14 | `copycat/server/signal_hub.py:68` 為一個字串常數,訊號層拖進 FinMind 那整串模組(chunk 2 C2-F8) | LOW | PARTIAL(校正 LOW;原 LOW):PARTIAL,LOW:傳遞相依屬實(probe sys.modules 證實)、無循環;但 CLAUDE.md §4 明訂 `SCREEN_GROUP` 產生點 = `screen_engine`,搬家等於改契約(app 本來就 import 它)。 | Nice to Have | `no-op` | 契約釘在 screen_engine,改動要動文件 |
| F-15 | `copycat/signal_rules.py:111` `_QUIET_KINDS` 裡的 sweep_cluster 是死資料,靜音真值在種子卡字面(chunk 3 C3-F1) | MEDIUM | CONFIRMED(校正 LOW;原 MEDIUM):CONFIRMED,LOW:Grep `_QUIET_KINDS` over `copycat/ tests/` → `signal_rules.py:111`(定義)/ `:353`(docstring)/ `:381`(唯一讀點,通用分支);`:370-374` sweep 分支先 return 故 `:381` 對 sweep_cluster 永不求值。改集合對掃單簇零效果、測試不紅;現值恰好一致。 | Nice to Have | `auto-fix` | 刪 5 行分支或改一行讀集合 |
| F-16 | `copycat/signal_rules.py:444` 掃單簇種子撞名跳過只印 INFO,可是這等於整個政策層不會有事件(chunk 3 C3-F2) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:前提需既有規則恰名「掃單簇」(v3 無此 kind),罕見但可能。 | Nice to Have | `auto-fix` | log 等級 + 一句話 |
| F-17 | `frontend/src/lib/signal-model.ts:281` 「同伴≥3% n・鎖過 有/無」在第三行與 hover 各寫一份(chunk 3 C3-F3) | MEDIUM | PARTIAL(校正 LOW;原 MEDIUM):PARTIAL,LOW:重複屬實;差異只在 null,但型別 `peers_up?: number` 不含 null、後端恆送 int,不可觸發。 | Nice to Have | `auto-fix` | 抽一支 helper |
| F-18 | `frontend/src/lib/signal-model.test.ts:369` `policyTitle` 六段只被四個 `toContain` 摸到(chunk 3 C3-F4) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:Grep `policyTitle` over `frontend/src`(排除定義檔)→ 唯一命中 `SignalRail.tsx:19`(import)/ `:277`(呼叫),測試檔零命中;唯一覆蓋 = `SignalRail.test.tsx` 那幾個 `toContain`。hover-only 字串,最壞是靜默漂移。 | Nice to Have | `auto-fix` | 兩條字面測試 |
| F-19 | `frontend/src/lib/signal-model.ts:97` `isPolicy` 不是型別謂詞;八個政策欄前端零讀者(chunk 3 C3-F5) | LOW | PARTIAL(校正 LOW;原 LOW):PARTIAL,LOW:Grep `peer_max` / `screen_member` / `t1_open` over `frontend/src`(非測試檔)→ 各只命中 `lib/signal-model.ts`(型別宣告);`sweep` / `t2_open` 同;`detail` 因同名於 api-error 等模組另有命中,但 `sig.detail` 零存取。零讀者屬實;`SignalMsg` 是單一介面、欄位皆 optional,型別謂詞在此收斂不到什麼。 | Nice to Have | `auto-fix` | 註解為主 |
| F-20 | `frontend/src/components/stock/SignalRail.tsx:259` 列高預算註解已失真;合併列時 chip 會自己占一行(chunk 3 C3-F6) | LOW | PARTIAL(校正 LOW;原 LOW):PARTIAL,LOW:註解過期屬實;chip 堆疊只在 merged 邊角(政策列與 raw 掃單簇文案去重成一段,常態 merged=false,chip 仍同行)。 | Nice to Have | `auto-fix` | 註解 + 可選版面微調 |
| F-21 | `frontend/src/hooks/useSignalAlerts.ts:225` 雙嗶規則在合併分支與新組分支各寫一份(chunk 3 C3-F8) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:DRY nit,零行為風險。 | Nice to Have | `auto-fix` | 抽一支 helper |
| F-22 | `frontend/src/components/stock/SignalRulesDialog.test.tsx:209` 測試拿 Tailwind class 當選擇器(chunk 3 C3-F9) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:全 frontend 其餘 `selector:` 用法皆為元素名(SVG `text`),無第二處以樣式類定位 → 非既有慣例;失效是大聲紅不是假綠。 | Nice to Have | `auto-fix` | 一行選擇器(節點數已驗) |
| F-23 | `tests/live/test_signal_state.py:882` 換日 / 移出自選的掃單簇清狀態測試:註解說的機制是假的,單欄突變全存活(chunk 4 C4-F1) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):CONFIRMED,MEDIUM:trace 實測 sweeps=[36090.5, 36100.5],lookback0 未過 cutoff → up_pct=0;mutant 全綠;既有 `TestLifecycle:952` / `TestSurgePullback:1150` 同名測試都用兩個 code。 | Nice to Have | `auto-fix` | 改兩支測試的 tick 序列與斷言 |
| F-24 | `tests/live/test_signal_state.py:817` golden self-check 用位置配對 + strict zip,把偶然的等數量變硬閘(chunk 4 C4-F2) | MEDIUM | CONFIRMED(校正 LOW;原 MEDIUM):CONFIRMED,LOW:探測三案 ms 清單完全相同;`b["ms"] == a["ms"]` 會擋錯位,失效是大聲的 ValueError 不是假綠。 | Nice to Have | `auto-fix` | 改配對方式 |
| F-25 | `tests/fixtures/record_sweep_cluster_golden.py:66` 參考碼沒有 09:00–13:30 的 session gate,等式只是這三檔的巧合(chunk 4 C4-F3) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:三案該毫秒各只一筆(不成群、零掃單),去掉末筆結果完全相同 → 目前等式不受影響;重錄挑到含盤外群的日子才會出事。 | Nice to Have | `auto-fix` | loader 加一個時間濾網 |
| F-26 | `tests/fixtures/record_sweep_cluster_golden.py:137` oracle 強度分兩半,docstring 沒分段(chunk 4 C4-F4) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:讀 `sweep_prefix_scan.py` 全文證實只做群內達標統計;純文件精確度。 | Nice to Have | `auto-fix` | docstring |
| F-27 | `tests/server/test_signal_outcome.py:109` 回填「保留行尾」那段邏輯零覆蓋:測試全 LF,prod 檔是 CRLF(chunk 5 C5-F1) | HIGH | CONFIRMED(校正 MEDIUM;原 HIGH):CONFIRMED,MEDIUM:mutant 把行尾硬寫 `"\n"` → 171 tests 全綠;真碼對 CRLF 檔實跑 2 CRLF / 0 lone LF(分支確有效)。實害限於被補的列行尾混雜。 | Nice to Have | `auto-fix` | 測試 parametrize |
| F-28 | `tests/server/test_signal_outcome.py:256` 三種失敗共用一句子字串斷言,warning ↔ exception 分不出來(chunk 5 C5-F2) | MEDIUM | CONFIRMED(校正 LOW;原 MEDIUM):CONFIRMED,LOW:mutant warning→exception 171 tests 全綠;但 traceback 量受限於檔數 × 日檔、每日兩趟,非 #146 等級洪水。repo 有 13 個測試檔斷言 levelno / exc_info。 | Nice to Have | `auto-fix` | parametrize 多一欄 |
| F-29 | `tests/server/test_signal_outcome.py:289` 「回填 2 列」同時命中逐檔行與彙總行(chunk 5 C5-F3) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:mutant 刪 :1312 逐檔 INFO → 全綠。 | Nice to Have | `auto-fix` | 一行斷言 |
| F-30 | `tests/server/test_signal_outcome.py:370` 以 coroutine 名字面做否定斷言,改名後恆真(chunk 5 C5-F4) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:同案 :369 的「無日 K 來源」caplog 斷言已擋住主 mutant(worker 誤啟動時那行 INFO 不會出現),:371 屬裝飾性。 | Nice to Have | `auto-fix` | 一行 |
| F-31 | `tests/server/test_signal_outcome.py:46` 手抄的政策列 fixture 沒釘到 `_POLICY_KEYS`(chunk 5 C5-F5) | LOW | PARTIAL(校正 LOW;原 LOW):PARTIAL,LOW:「自我比對」不確 —— :163 比的是回寫後的鍵序 vs 輸入鍵序,殺得掉重排 mutant;只有「未釘 `_POLICY_KEYS`」這半成立(現值恰相符)。 | Nice to Have | `auto-fix` | 一行 parity |
| F-32 | `tests/server/test_signal_outcome.py:307` 用 `asyncio.sleep(0.05)` 證「沒再跑」,負載重時可能零輪詢(chunk 5 C5-F6) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:方向是漏抓不是誤紅;既有測試風格。 | Nice to Have | `auto-fix` | fake 加計數器 |
| F-33 | `tests/server/test_signal_policy.py:321` `peers_fn` 拋例外的降級路徑(quotes={} / 當日一次 traceback / 換日復位)零測試(chunk 6 C6-F1) | MEDIUM | CONFIRMED(校正 MEDIUM;原 MEDIUM):CONFIRMED,MEDIUM:Grep `peers_error` / `政策行情快照讀取失敗` over `tests/ copycat/` → 只命中實作 `signal_hub.py:1049`,tests 零命中;`_Watch` 只有 `groups_error` / `quotes_error`(`test_signal_hub.py:266-267`)。mutant 刪 try/except(例外炸熱路徑)或改逐 tick 印 → 全綠;姊妹旗標 `_multi_group_warned` 的當日一次有測(`test_signal_policy.py:422`)。 | Nice to Have | `auto-fix` | harness 加旗標 + 一案 |
| F-34 | `tests/server/test_stock_engine.py:1332` `TestPolicyQuotes` docstring 承諾 no_data,卻沒有一案打 `on_no_data`(chunk 6 C6-F2) | MEDIUM | CONFIRMED(校正 LOW;原 MEDIUM):CONFIRMED,LOW:mutant 存活屬實、docstring 有承諾;但引擎層不在議定四 seam,失效路徑屬邊角。 | Nice to Have | `auto-fix` | 兩案 |
| F-35 | `tests/server/test_stock_engine.py:1348` `test_quoted_stock_full_snapshot` 沒 `await engine.close()`(chunk 6 C6-F3) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:腳本掃出 5/193;測試衛生。 | Nice to Have | `auto-fix` | 一行 |
| F-36 | `tests/server/test_signal_policy.py:591` `_fmt` 放在兩個 class 中間,且進位邊界會印 `60.000`;參數化案缺 kind 斷言(chunk 6 C6-F4) | LOW | PARTIAL(校正 LOW;原 LOW):PARTIAL,LOW:59.9995 仍印 59.999、59.99951 起才 60.000,屬潛在非現行;KeyError 是大聲失敗;同 PR 的 `_wait_calls` 也放檔尾。 | Nice to Have | `auto-fix` | 小整理 |
| F-37 | `tests/server/test_signal_policy.py:107` 三處 `type: ignore` 只因群組治具是裸 dict(chunk 6 C6-F5) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:repo 測試普遍容忍(test_index_engine 68 個),本檔 3 個。 | Nice to Have | `auto-fix` | 三個型別標註 |
| F-38 | `tests/server/test_signal_policy.py:560` 換日 / 移出自選歸零兩案沒斷「真的又推了一次」(chunk 6 C6-F6) | LOW | PARTIAL(校正 LOW;原 LOW):PARTIAL,LOW:notify = first_of_day 且 ≤ push_end,first_of_day 已斷;notify ↔ Discord 連動由 :485-491 釘住 → 屬加強非補洞。 | Nice to Have | `auto-fix` | 一行 ×2 |
| F-39 | `tests/server/test_signal_routes.py:55` `_SEEDED_KINDS` 補了 sweep_cluster,同檔 `_RULE_PARAMS` 複製表沒補(chunk 6 C6-F7) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:目前無呼叫點,潛伏 KeyError。 | Nice to Have | `auto-fix` | 刪複製表改 import |
| F-40 | `tests/server/test_signal_policy.py:624` 兩政策合併卡只驗第 0/2/3 行,第 1 行與行數沒守(chunk 6 C6-F8) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:第 1 行內容已由單政策案 :605-610 整串釘住;屬對稱補強。 | Nice to Have | `auto-fix` | 兩行 |
| F-41 | `tests/test_signal_rules.py:407` 種子通知旗以 kind 當 key,兩張回檔卡塌成一張(chunk 7 C7-F1) | MEDIUM | PARTIAL(校正 LOW;原 MEDIUM):PARTIAL,LOW:塌卡屬實(7 → 6 鍵);但兩張回檔卡的 notify 由 `_pullback_seed_rule` 同一行給值,單卡 mutant 造不出來、dict 會一起翻紅。 | Nice to Have | `auto-fix` | dict key 換 name |
| F-42 | `tests/test_signal_rules.py:255` 整數鍵「接受整數浮點」案沒補 sweep 兩鍵,姊妹拒收案有補(chunk 7 C7-F2) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:`INT_PARAM_KEYS` 是共用判定,其他 kind 已覆蓋路徑;對稱性缺口。 | Nice to Have | `auto-fix` | parametrize 加兩列 |
| F-43 | `tests/test_signal_rules.py:899` 案名說「不重複 log」,斷言是「一次都不 log」(chunk 7 C7-F3) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:純命名。 | Nice to Have | `auto-fix` | 改名 |
| F-44 | `tests/test_signal_rules.py:745` id 去重案的 docstring 還指 `_migrate_v2`,迴圈已搬到 `_append_seed`(chunk 7 C7-F4) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:`signal_rules.py:436-457` 迴圈在 `_append_seed`,`_migrate_v2:429-434` 已無;次要。 | Nice to Have | `auto-fix` | docstring(+ 可選參數) |
| F-45 | `tests/test_signal_rules.py:833` 遷移種子「不吃設定檔覆寫」這個分歧,測試側沒複述(chunk 7 C7-F5) | LOW | PARTIAL(校正 LOW;原 LOW):PARTIAL,LOW:分歧已在 `signal_rules.py:421-424` 與 :485 兩處 docstring 明載,只是測試 docstring 未加註。 | Nice to Have | `auto-fix` | 一句 docstring |
| F-46 | `tests/test_signal_rules.py:844` `_v3_set` 只在 vol_burst 顯式寫前置條件,cdp 靠預設(chunk 7 C7-F6) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:純風格。 | Nice to Have | `auto-fix` | 一行 |
| F-47 | `tests/test_signal_rules.py:927` 兩個斷言沒綁同一行,失敗時看不出哪一半(chunk 7 C7-F7) | LOW | CONFIRMED(校正 LOW;原 LOW):CONFIRMED,LOW:要相當刻意的改動才逃得掉。 | Nice to Have | `auto-fix` | 一行 |
| F-48 | `copycat/live/signal_state.py:714` 七顆 detector 都養掃單狀態 —— 但既有設計本來就每顆推進全部 kind(chunk 1 C1-F5) | LOW | REFUTED(校正 LOW;原 LOW):REFUTED:`signal_state.py:190-209` 每顆 detector 都持 `_prev/_window/_pullback/...`,`evaluate:319-323` 對所有 kind 無條件推進(docstring 692「狀態推進無條件」是刻意設計);sweep 窗 60 s 還小於 surge 的 300 s,非新量級。 | 參考用 | `no-op` | 既有架構,非本 PR 引入 |
| F-49 | `copycat/server/signal_hub.py:1085` 兩條掃單簇規則會各出一列政策列 —— 但 spec 就是這樣訂的(chunk 2 C2-F1) | MEDIUM | REFUTED(校正 LOW;原 MEDIUM):REFUTED:spec #192 明訂「任一條該 kind 規則的事件都評,列上記 rule_id」+「每日計數 per (檔, 政策)」+ story 7「對帳統計本來就是同檔一筆」;第二列 notify=False 不進 Discord(`_enqueue:1128`)。 | 參考用 | `no-op` | spec 字面行為 |
| F-50 | `frontend/src/hooks/useSignalAlerts.ts:205` quiet 列不併入 toast 文案 —— spec 就是要它完全不出現(chunk 3 C3-F7) | LOW | REFUTED(校正 LOW;原 LOW):REFUTED:spec #192 story 9「CDP 穿越、爆量停止一切推播(Discord、toast、嗶聲、桌面通知)但 rail 淡色仍列」;gate 上方註解已逐字寫明。 | 參考用 | `no-op` | spec 明文行為 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 80105386eb926f2505aa action=ask-user
F-02 finding_uid: 2457ad4c976a91287766 action=auto-fix
F-03 finding_uid: 462ab9ddd84b63fecd0e action=auto-fix
F-04 finding_uid: f1a767fdc60728cfd76c action=auto-fix
F-05 finding_uid: 9ba7b8bc0bea2c53e384 action=auto-fix
F-06 finding_uid: b29dcd435d206dbda20f action=auto-fix
F-07 finding_uid: c61500eb6e0f1f6c0710 action=auto-fix
F-08 finding_uid: 6f5880b5469a5a46a015 action=auto-fix
F-09 finding_uid: 1f6939e36c648042cc8a action=ask-user
F-10 finding_uid: b1a01a57f932404079c8 action=auto-fix
F-11 finding_uid: 39f4d6c5320cb1b6b616 action=auto-fix
F-12 finding_uid: 6120c42675ec5648640c action=auto-fix
F-13 finding_uid: 450a7476982299a67919 action=auto-fix
F-14 finding_uid: 11a73d00307ab037a67e action=no-op
F-15 finding_uid: 852c99d92bec46d176ad action=auto-fix
F-16 finding_uid: 9a0567bb245d75a3965c action=auto-fix
F-17 finding_uid: 4d10afd74086c1d34afd action=auto-fix
F-18 finding_uid: afd92e301bf7c16aff85 action=auto-fix
F-19 finding_uid: 354ce82386b3b21654dc action=auto-fix
F-20 finding_uid: d828631c21abec6c035d action=auto-fix
F-21 finding_uid: 7a370e172ae6139de232 action=auto-fix
F-22 finding_uid: bd0a62dc77ec346271af action=auto-fix
F-23 finding_uid: 9d90a2b4c51985d8be83 action=auto-fix
F-24 finding_uid: ff123a55b3bb8ce08be4 action=auto-fix
F-25 finding_uid: eea50f5de873e5b0d739 action=auto-fix
F-26 finding_uid: 20edca325d0846dea500 action=auto-fix
F-27 finding_uid: ca8bb435dc2ce726b58d action=auto-fix
F-28 finding_uid: 3d46d6ee1a3bd8435ee4 action=auto-fix
F-29 finding_uid: 31a07a1fe1e80060f577 action=auto-fix
F-30 finding_uid: a2c98e0ab607db10a211 action=auto-fix
F-31 finding_uid: 13470db823d7676b5467 action=auto-fix
F-32 finding_uid: ccca59e6e27ca6abc47a action=auto-fix
F-33 finding_uid: 35ef2fb65b20617c960d action=auto-fix
F-34 finding_uid: 744e1fe87d183135c917 action=auto-fix
F-35 finding_uid: c738e3b77a78991e689e action=auto-fix
F-36 finding_uid: c21dac0e24d66d01bb82 action=auto-fix
F-37 finding_uid: 7cc66c9ac9414528ec7a action=auto-fix
F-38 finding_uid: 5bab11f06f7a0ef7a62d action=auto-fix
F-39 finding_uid: 22d8b1a2b6e3f9fd266b action=auto-fix
F-40 finding_uid: f0a6802c76124e4e7480 action=auto-fix
F-41 finding_uid: b1f23f34aa0e05ae399b action=auto-fix
F-42 finding_uid: ba3b58c1faa5aa919f6f action=auto-fix
F-43 finding_uid: 28357d7e38b8fd503f16 action=auto-fix
F-44 finding_uid: 91d02f746251963890ff action=auto-fix
F-45 finding_uid: 59487c099c7581ef7076 action=auto-fix
F-46 finding_uid: bb6110b40c169d7b406f action=auto-fix
F-47 finding_uid: a55bb6633f0da4f46097 action=auto-fix
F-48 finding_uid: 943a300ddd3621048902 action=no-op
F-49 finding_uid: 1d137f8f562593b00139 action=no-op
F-50 finding_uid: 5de6e7fd2ff67b1a6f76 action=no-op

### Inline Comments per Finding（直接複製貼到 PR review）

#### #1 術語寫「族群沒人鎖過」,code 只看同伴(自己鎖過不擋)

**File**: `CONTEXT.md`
**Line**: 118

**Comment**:
```
CONTEXT.md 這裡寫「族群沒人鎖過」,但同一檔上面定義「同伴 = 族群扣自己」,而 `evaluate_policies` 真正看的是
`peer_touched`(同伴),自己當天鎖過不擋 → B-b 沒有 <6% 那道閘,自己已經摸過漲停照樣命中。
spec #192 的字面就是「非 peer_touched」,所以 code 沒錯,是這兩句(CONTEXT.md:118 + signal_policy.py 模組 docstring 15-16 行)
該改成「**同伴**沒人鎖過(自己鎖過不擋)」。如果原意其實要含自己,那是改 code、要拍板。
```

#### #2 模組 docstring 還寫「兩個 helper」,現在是三個

**File**: `copycat/fileio.py`
**Line**: 3

**Comment**:
```
檔頭這句「兩個 helper …不可互換」是這檔的判準表,這次多了 `atomic_write_bytes`(bytes、零換行翻譯、jsonl 原地回填用)
沒補上去。改成三個、加一列就好。
```

#### #3 「三道 gate 不推進任何狀態」的承諾已被掃單簇打破

**File**: `copycat/live/signal_state.py`
**Line**: 298

**Comment**:
```
`evaluate` 的 docstring 說三道 gate 不過就「不推進任何狀態」,但掃單簇那條軸(`_eval_sweep`)現在排在首 tick gate 前面、
已經推進 `_lookback` / `_sweep_group` 了(回值倒是仍然 [])。下面 305-307 的註解有講,這句沒跟上,改一下。
```

#### #4 frozen dataclass 裝 dict → 掃單簇事件不可 hash(目前沒人 hash)

**File**: `copycat/live/signal_state.py`
**Line**: 104

**Comment**:
```
`SignalEvent` 是 frozen dataclass,`detail` 塞 dict 之後帶 detail 的事件 `hash()` 直接 TypeError(現在沒人 hash 它,
所以是潛伏的)。hub 那兩處 `dict(event.detail)` 防禦拷貝就是這個味道。要嘛改 tuple-of-pairs、要嘛在欄位旁註明「不可雜湊」。
```

#### #5 取證腳本釘死已消失的 worktree 路徑,重跑必炸

**File**: `.claude/mod/signal-shadow-policies/evidence/fake_server.py`
**Line**: 17

**Comment**:
```
`fake_server.py:17` 寫死 `.claude/worktrees/mod-signal-shadow-policies`,worktree 收掉之後這路徑就沒了,
下面 42-45 行那個「必須來自 worktree」的 assert 也跟著必炸 → 這份盤後取證腳本現在重跑不了。
改 `Path(__file__).resolve().parents[4]` 自我定位、assert 改比 repo root;`vite.sidecar.config.ts` 的 `root:` 同樣處理。
```

#### #6 verification.md 的跑法與 vite 側車設定檔互斥

**File**: `.claude/mod/signal-shadow-policies/verification.md`
**Line**: 65

**Comment**:
```
verification.md 說「跑時複製到 frontend/ 再刪」,可是 `vite.sidecar.config.ts` 自己的檔頭寫的是 `--config ../.claude/...`,
而且它的 `import base from "../../../../frontend/vite.config"` 一複製到 frontend/ 就指到 repo 外面。兩句至少有一句是假的。
實際跑的時候是複製過去、順手把 import 改成 `./vite.config` + `root: __dirname` —— 把這個寫進文件,或讓設定檔直接是那個版本。
```

#### #7 `live_engine = engine` 別名沒說為什麼

**File**: `copycat/server/app.py`
**Line**: 821

**Comment**:
```
`live_engine = engine` 這行沒講理由;同一段上面 :819 的 lambda 就直接抓 `engine`,pyright 也能收斂,所以不是為了窄化。
要嘛補半行「為什麼」,要嘛直接用 `engine`。
```

#### #8 回填的「逾時」except 在 prod 走不到,逾時因此零記錄

**File**: `copycat/server/signal_hub.py`
**Line**: 1321

**Comment**:
```
`_fetch_outcome_bars` 這個 `except HistoryTimeoutError` 在 prod 永遠走不到:app 的 `_outcome_bars` 走 `engine.bars_range`,
它已經把 ConnectionError(HistoryTimeoutError 是子類,tc4.py:69)吃成 `BarsResult([], "disconnected")`,然後 `.bars` 又把 status 丟掉
→ 13:40 撞到 TC4 忙,log 只剩一句「共回填 0 列」,查不出是逾時。
讓 `_outcome_bars` 把 `BarsResult` 整個回來,`status != "ok"` 印一行 WARNING(含 code / status),這個 except 就可以刪了。
```

#### #9 整檔嚴格解碼:一個壞位元組讓那一天整檔 5 天內都跳過

**File**: `copycat/server/signal_hub.py`
**Line**: 1271

**Comment**:
```
回填讀檔是整檔 `decode("utf-8")` 嚴格模式,一個壞位元組(`read_signals` 的 docstring 說半寫入切在中文中間**真發生過**)
那一天的檔就每天被跳過、政策列 t1/t2 永遠 null(有 WARNING,不是靜默)。
不能學 `read_signals` 用 `errors="replace"`(這裡要回寫,會把 U+FFFD 寫回去);比較穩的是逐行 bytes 處理:
解不開的那行原樣保留 bytes、其他行照補。要不要這樣改,拍板。
```

#### #10 `format_policy_group_text` 對外但沒守「至少一列政策列」

**File**: `copycat/server/signal_hub.py`
**Line**: 214

**Comment**:
```
`format_policy_group_text` 有進 `__all__`,但 `policies[0]` 沒 guard —— 現在只有 `_send_discord` 先用 `any(_is_policy)` 擋過才叫它,
別人直接呼會拿裸 IndexError。函式自己加一行:沒政策列就退回 `format_signal_group_text(rows)`。
```

#### #11 每顆掃單簇事件對整份自選(≤150)組快照,hub 只讀幾個同伴

**File**: `copycat/server/stock_engine.py`
**Line**: 763

**Comment**:
```
`policy_quotes()` 每次把整份自選(上限 150 檔)都組一遍 `PeerQuote` + `_quote_payload`,但 `_emit_policies` 只讀 `peer_codes` 那幾檔。
有 60 s 冷卻擋著所以不痛,但白做;加個 `codes: list[str] | None = None`,hub 傳 `peer_codes` 進來就好(`_watchlist` 那條 R16 照舊)。
```

#### #12 no_data 的同伴連名字都被清空,姊妹 `quotes()` 不是這樣

**File**: `copycat/server/stock_engine.py`
**Line**: 778

**Comment**:
```
`policy_quotes` 對 `no_data` 的檔把 `meta` 整個歸 None,連 `name` 一起變空字串;姊妹 `quotes()`(:758-759)不看 no_data、名字照給,
而這裡 docstring 又寫「同 quotes()」。政策列 `peers[]` 裡的無資料同伴就會是 `name: ""`,對帳看不出是哪家。
name 改走 `state.meta`,只讓 price / high / book 那幾個值欄位吃 no_data。
```

#### #13 政策順序不變式寫兩處;`tuple(policy_exclude_groups)` 是 no-op

**File**: `copycat/server/signal_policy.py`
**Line**: 156

**Comment**:
```
`evaluate_policies` 回的 `hits` 已經是 P / B-a / B-b / S 順序,hub 那邊又跑一次 `for policy in POLICIES: if policy not in ctx.hits`
—— 同一條排序約定寫兩份。直接 `for policy in ctx.hits` 就好;順手把 `tuple(cfg.policy_exclude_groups)` 拿掉(它本來就是 tuple)。
```

#### #14 為一個字串常數,訊號層拖進 FinMind 那整串模組

**File**: `copycat/server/signal_hub.py`
**Line**: 68

**Comment**:
```
這條複查後歸參考用:`signal_hub` 為了 `SCREEN_GROUP` 把 screening / market_breadth / breadth_fetch 那串一起 import 進來是真的
(沒循環),但 CLAUDE.md §4 已經把這顆常數的產生點釘在 `screen_engine`,搬家 = 改契約,而 app.py 本來就整包 import。
想收再連文件一起搬,不在這次。
```

#### #15 `_QUIET_KINDS` 裡的 sweep_cluster 是死資料,靜音真值在種子卡字面

**File**: `copycat/signal_rules.py`
**Line**: 111

**Comment**:
```
`_QUIET_KINDS` 放了 `sweep_cluster`,但 `default_rules` 在走到 `kind not in _QUIET_KINDS` 之前就先把它攔去 `_sweep_seed_rule`,
那裡是字面 `notify_discord: False` → 集合裡這個成員從來沒被讀過。哪天把它移出集合(掃單簇要推播了)全新安裝照樣關、測試不紅。
最省事:刪掉 :370-374 那個專屬分支,通用分支產出的欄位跟 `_sweep_seed_rule` 一模一樣。
```

#### #16 掃單簇種子撞名跳過只印 INFO,可是這等於整個政策層不會有事件

**File**: `copycat/signal_rules.py`
**Line**: 444

**Comment**:
```
v3→v4 的種子卡撞名跳過走 INFO,但掃單簇種子是政策層唯一的觸發源 —— 誰要是先前自己建過一條叫「掃單簇」的規則,
整個影子期就零事件,盤後 grep WARNING 也看不到。改 WARNING、後面補「政策層將不會產生事件」。
```

#### #17 「同伴≥3% n・鎖過 有/無」在第三行與 hover 各寫一份

**File**: `frontend/src/lib/signal-model.ts`
**Line**: 281

**Comment**:
```
rail 第三行(`policyContextText`)跟 hover 全文(`policyTitle`)都在印「同伴≥3% n・鎖過 有/無」,各自手寫一份,
缺值寫法還不一樣(`?? "-"` vs `=== undefined`;型別上 null 進不來所以現在看不出差)。抽個 `peerPhrase(sig)` 兩邊共用,
之後門檻解凍要改字面只改一處。
```

#### #18 `policyTitle` 六段只被四個 `toContain` 摸到

**File**: `frontend/src/lib/signal-model.test.ts`
**Line**: 369

**Comment**:
```
`policyTitle` 目前只靠 `SignalRail.test.tsx` 那幾個 `toContain`(記憶體 / 2344華邦電 / 較前收 / 距漲停)間接碰到,
「盤前篩選名單・無族群濾網」「(族群最強)」「首筆」「late」這幾段沒人守。在 `signal-model.test.ts` 補兩條整句字面比對就好。
```

#### #19 `isPolicy` 不是型別謂詞;八個政策欄前端零讀者

**File**: `frontend/src/lib/signal-model.ts`
**Line**: 97

**Comment**:
```
`SignalMsg` 這次多了 18 個政策 optional 欄,其中 `detail / sweep / screen_member / peer_max / t1_*/t2_*` 八個前端根本沒人讀,
只是把 wire 形狀抄過來。至少在型別旁註明「wire 存證、前端不讀」,免得下一手以為缺了什麼;`isPolicy` 要不要改成型別謂詞
倒是其次(單一 interface 全 optional,收斂不到東西)。
```

#### #20 列高預算註解已失真;合併列時 chip 會自己占一行

**File**: `frontend/src/components/stock/SignalRail.tsx`
**Line**: 259

**Comment**:
```
`SignalRail.tsx:257-259` 那段「列高封在 1 + 2 + 1 行」是政策第三行加上去之前寫的,現在政策列是 1+2+1+1。
另外 chip 放在 `merged ? "flex flex-col"` 那個容器裡,合併列(同 tick 還有別的 kind)時 chip 會自己占一行;常態(政策 + raw 掃單簇
去重成一段)不會。先把註解改對;chip 要不要搬到 merged 外面同一行,順手看一下。
```

#### #21 雙嗶規則在合併分支與新組分支各寫一份

**File**: `frontend/src/hooks/useSignalAlerts.ts`
**Line**: 225

**Comment**:
```
「政策列嗶兩聲」在併入既有 toast 的分支(:225-228)和開新張的分支(:250-253)各寫了一份。抽個 `beep(double)`,
兩個呼叫點各一行,以後改嗶法只改一處。
```

#### #22 測試拿 Tailwind class 當選擇器

**File**: `frontend/src/components/stock/SignalRulesDialog.test.tsx`
**Line**: 209

**Comment**:
```
這行用 `selector: "span.rounded"` 分辨規則名和種類徽章(兩個都叫「掃單簇」),圓角樣式一改測試就紅。
改成 `getAllByText("掃單簇").length === 2`,或給徽章一個 `data-testid`。
```

#### #23 換日 / 移出自選的掃單簇清狀態測試:註解說的機制是假的,單欄突變全存活

**File**: `tests/live/test_signal_state.py`
**Line**: 882

**Comment**:
```
這兩支測試(`test_reset_day_clears_sweeps_and_lookback` / `test_drop_code_clears_only_that_code`)註解寫「n30 = 1 / 回看窗空」,
實際跑起來末群 n30 是 2,真正讓事件不發的是 `up_pct = 0`(那筆 10:00:00 的基準價是在兩個群**之後**才餵的,永遠當不成 base)。
所以 `reset_day` 不清 `_sweeps` 照樣綠,`drop_code` 三個單欄突變也全綠;而且 drop 案只有一檔,「only that code」什麼都沒斷。
改法:基準筆先餵、重置後只留一個掃單群(這樣 n30 才是唯一約束),drop 案加第二檔並斷它還能發訊。
```

#### #24 golden self-check 用位置配對 + strict zip,把偶然的等數量變硬閘

**File**: `tests/live/test_signal_state.py`
**Line**: 817

**Comment**:
```
`test_fixture_self_check` 用 `zip(..., strict=True)` 按位置配研究 / 即時判兩組事件,現在三案數量剛好一樣所以過;
重錄挑到有「多發」的股票日時會直接 `ValueError: zip() argument 2 is longer`,不是有意義的斷言。
改用 `ms` 當 key 配對:斷 research 的 ms 全部 ⊆ prefix,配到的 pair 再比 `i` / `levels`。
```

#### #25 參考碼沒有 09:00–13:30 的 session gate,等式只是這三檔的巧合

**File**: `tests/fixtures/record_sweep_cluster_golden.py`
**Line**: 66

**Comment**:
```
參考碼 `load_rows` 沒有偵測器那道 09:00–13:30 的 session gate,三案最後一筆 13:30:00.000 收盤撮合是參考碼收、偵測器丟,
現在剛好那毫秒只有一筆(不成群)所以集合還是相等。重錄若挑到 08:xx 試撮列或 13:30 成群的日子就會不等。
loader 加 `[09:00, 13:30)` 濾一下最省事。
```

#### #26 oracle 強度分兩半,docstring 沒分段

**File**: `tests/fixtures/record_sweep_cluster_golden.py`
**Line**: 137

**Comment**:
```
`record_sweep_cluster_golden.py` 的 docstring 把整支說成「參考碼逐字沿研究腳本」,但 `clusters_prefix` 後半(簇窗 / 60 s 漲幅 / 去重 /
qty 前綴)研究裡沒有對應物,是這次自己寫的第二份實作(bisect 跟偵測器的 deque 不同機制,所以還是有對照價值)。
在 docstring 分段講清楚哪一半是研究真值,以後別人才不會把整支當 oracle。
```

#### #27 回填「保留行尾」那段邏輯零覆蓋:測試全 LF,prod 檔是 CRLF

**File**: `tests/server/test_signal_outcome.py`
**Line**: 109

**Comment**:
```
`_write_day` 用 `write_bytes` 寫純 LF,可是 prod 的 `_append_jsonl` 在 Windows 是文字模式 append、寫出來全是 CRLF ——
實作裡 `lines[i][len(body):]` 那段「行尾原樣接回」就是為 CRLF 寫的,現在零覆蓋:把它改成硬寫 `"\n"`,171 條測試照綠,
prod 檔就變成「被補的列 LF、其他列 CRLF」。
`_write_day` 加個 `eol` 參數,byte 比對那案對 `["\n", "\r\n"]` 各跑一次、直接比整段 bytes。
```

#### #28 三種失敗共用一句子字串斷言,warning ↔ exception 分不出來

**File**: `tests/server/test_signal_outcome.py`
**Line**: 256

**Comment**:
```
三個 failure 參數共用同一句「`"2330" in caplog.text and "回填" in caplog.text`」,分不出實作刻意做的「逾時只 warning、其他才 exception」;
把逾時那支改成 `logger.exception` 測試照綠。parametrize 多帶一個 `expect_exc`,斷 `caplog.records[-1].exc_info is None / is not None`。
(順帶:C2-F2 說 prod 其實走不到逾時 except,這案注入 HistoryTimeoutError 給的是假信心,兩條一起收。)
```

#### #29 「回填 2 列」同時命中逐檔行與彙總行

**File**: `tests/server/test_signal_outcome.py`
**Line**: 289

**Comment**:
```
`"回填 2 列" in caplog.text` 同時被逐檔那行「回填 2 列(1 檔)」跟收尾那行「共回填 2 列」命中,逐檔 log 刪了也綠。
改成斷 `"回填 2 列(1 檔)"` 就分得出來。
```

#### #30 以 coroutine 名字面做否定斷言,改名後恆真

**File**: `tests/server/test_signal_outcome.py`
**Line**: 370

**Comment**:
```
`"_policy_outcome_worker" not in names` 是字面否定,哪天 worker 改名這行就永遠成立;前一行 caplog 斷「無日 K 來源」其實已經
守住主要情境,這行要嘛比 `type(h.hub)._policy_outcome_worker.__name__`(改名一起動),要嘛換成正向的「bars 零呼叫」。
```

#### #31 手抄的政策列 fixture 沒釘到 `_POLICY_KEYS`

**File**: `tests/server/test_signal_outcome.py`
**Line**: 46

**Comment**:
```
`_policy_row` 是手抄的政策列形狀,沒跟 `test_signal_policy._POLICY_KEYS` 對過(現在剛好一樣)。加一句
`assert set(_policy_row("2330")) == _POLICY_KEYS | {"trade_date"}`,fixture 漂掉時會紅。
(:163 那個鍵序比對本身是有效的,回寫後重排會被抓到。)
```

#### #32 用 `asyncio.sleep(0.05)` 證「沒再跑」,負載重時可能零輪詢

**File**: `tests/server/test_signal_outcome.py`
**Line**: 307

**Comment**:
```
「10:00 沒到 13:40 所以不再跑」是靠 `asyncio.sleep(0.05)` 撐的,機器忙起來 0.05 s 內可能一次輪詢都沒發生、斷言就空轉。
`_FakeDayBars` 或 hub 曝一個「檢查過幾次」的計數,先等到 ≥ N 次再斷 `calls` 沒增加,三處同款。
```

#### #33 `peers_fn` 拋例外的降級路徑(quotes={} / 當日一次 traceback / 換日復位)零測試

**File**: `tests/server/test_signal_policy.py`
**Line**: 321

**Comment**:
```
`_emit_policies` 那段 `except Exception` → `quotes = {}`(P/B 不評、S 照評)+ `_peers_fn_failed` 當日只印一次 traceback,
整段沒有任何測試走過:把 try/except 刪掉讓例外炸到 `on_tick`、或改成每 tick 印,測試都綠。
`_Watch` 本來就有 `groups_error` / `quotes_error`(它的 docstring 還說兩條失敗路徑都要有替身),補個 `peers_error`,
一案:拋 → 只剩 S、raw 列還在、caplog 一則、`on_rollover()` 後再一則。
```

#### #34 `TestPolicyQuotes` docstring 承諾 no_data,卻沒有一案打 `on_no_data`

**File**: `tests/server/test_stock_engine.py`
**Line**: 1332

**Comment**:
```
`TestPolicyQuotes` 的 docstring 說 no_data → 值欄 None,但四個案子沒有一個呼叫 `src.on_no_data`(同檔 539/689/720/742 有先例),
也沒有「有簿更新、還沒成交」的案。把 `no_data = code in self._no_data` 改成 False 全綠 —— prod 上 TC4 說查無此檔之後,
舊的 `high` 會讓 `touched_upper` 留 True、整個族群的 P/B 被靜默擋掉。補這兩案。
```

#### #35 `test_quoted_stock_full_snapshot` 沒 `await engine.close()`

**File**: `tests/server/test_stock_engine.py`
**Line**: 1348

**Comment**:
```
這案跑完沒 `await engine.close()`,同 class 另外三案都有;背景 task 會留到測試結束。補一行。
```

#### #36 `_fmt` 放在兩個 class 中間,且進位邊界會印 `60.000`;參數化案缺 kind 斷言

**File**: `tests/server/test_signal_policy.py`
**Line**: 591

**Comment**:
```
`_fmt` 夾在兩個 class 中間,而且 `ss:06.3f` 在 ss ≥ 59.99951 會印出 `HH:MM:60.000`(現在那 10 組參數都安全,新加參數才會踩);
參數化那案沒斷 `p["kind"] == "policy"`,壞掉時是 KeyError 而不是可讀的失敗。毫秒整數 divmod、搬到檔頭、補一句 kind。
```

#### #37 三處 `type: ignore` 只因群組治具是裸 dict

**File**: `tests/server/test_signal_policy.py`
**Line**: 107

**Comment**:
```
`_MEM / _SCREEN / _ALL_IN` 宣告成裸 dict,所以 107 / 206 / 662 三處都得壓 `# type: ignore`;`Group` 就兩個鍵,直接 `_MEM: Group = {...}`
就能把 ignore 拿掉,日後 `Group` 加必填鍵治具也會跟著紅。
```

#### #38 換日 / 移出自選歸零兩案沒斷「真的又推了一次」

**File**: `tests/server/test_signal_policy.py`
**Line**: 560

**Comment**:
```
換日 / 移出自選這兩案只斷 `first_of_day` 又變 True,沒斷 Discord 真的又推了一次(`len(h.bot) == 2`);
驗收語是「再度推播」,同檔 491 行那條就是這樣寫的。各加一行。
```

#### #39 `_SEEDED_KINDS` 補了 sweep_cluster,同檔 `_RULE_PARAMS` 複製表沒補

**File**: `tests/server/test_signal_routes.py`
**Line**: 55

**Comment**:
```
`test_signal_routes.py` 的 `_SEEDED_KINDS` 補了 `sweep_cluster`,但同檔 58-70 那份 `_RULE_PARAMS`(從 test_signal_hub 抄來的)沒補,
`_rule_body("sweep_cluster", …)` 一寫就 KeyError。既然這次已經有跨測試檔 import 的先例,直接 import 那張表、把複製件刪掉。
```

#### #40 兩政策合併卡只驗第 0/2/3 行,第 1 行與行數沒守

**File**: `tests/server/test_signal_policy.py`
**Line**: 624

**Comment**:
```
`test_two_policies_same_tick_one_message` 只比 `lines[0] / [2] / [3]`,少了 `lines[1]`(掃單簇那行)跟 `len(lines) == 4`;
同檔 681 行那案是有斷行數的。補上。
```

#### #41 種子通知旗以 kind 當 key,兩張回檔卡塌成一張

**File**: `tests/test_signal_rules.py`
**Line**: 407

**Comment**:
```
`test_seed_notify_flags_quiet_for_negative_kinds` 用 `kind` 當 dict key,兩張「爆拉回檔」卡塌成一個鍵,七條種子只比到六個;
同 class 上下(390 / 433)都寫了「by name 不 by kind」。實務上兩張卡的 notify 是同一行給的所以現在漏不掉,但照慣例改 by name。
```

#### #42 整數鍵「接受整數浮點」案沒補 sweep 兩鍵,姊妹拒收案有補

**File**: `tests/test_signal_rules.py`
**Line**: 255

**Comment**:
```
拒收案(:231-239)補了 `sweep_cluster` 的 `min_sweeps` / `min_levels`,接受整數浮點那案(:247-253)沒補 —— copy-paste 對稱只做一半。
加兩列參數。
```

#### #43 案名說「不重複 log」,斷言是「一次都不 log」

**File**: `tests/test_signal_rules.py`
**Line**: 899

**Comment**:
```
案名 `not_logged_twice` 但斷的是 `count("v3→v4:規則") == 0`(一次都沒 log)。改名 `test_v3_already_quiet_rule_not_flipped_and_not_logged`。
```

#### #44 id 去重案的 docstring 還指 `_migrate_v2`,迴圈已搬到 `_append_seed`

**File**: `tests/test_signal_rules.py`
**Line**: 745

**Comment**:
```
這案 docstring 寫「`_migrate_v2` 的 while 去重迴圈」,迴圈這次已經搬到共用的 `_append_seed`,而且同一趟現在會 append 三張卡
(佔 `-001` → 種子拿 `-002 / -003 / -004`)。docstring 改指 `_append_seed`、講一下三張卡都走同一迴圈;想更嚴可以加「佔 `-003`」那組參數。
```

#### #45 遷移種子「不吃設定檔覆寫」這個分歧,測試側沒複述

**File**: `tests/test_signal_rules.py`
**Line**: 833

**Comment**:
```
`TestMigrationV3ToV4` 的種子參數斷言字面 30 / 2 / 2 / 0.3 / 60,剛好等於 `SignalsConfig()` 預設;`_migrate_v3` 是刻意不吃
`configs/signals.json` 覆寫的(實作 docstring 兩處都有寫),測試這邊補一句同樣的話就好,免得日後有人覺得該吃 cfg 去改它。
```

#### #46 `_v3_set` 只在 vol_burst 顯式寫前置條件,cdp 靠預設

**File**: `tests/test_signal_rules.py`
**Line**: 844

**Comment**:
```
`_v3_set` 裡只有 vol_burst 那條寫了 `notify_discord=True`,cdp_cross 靠 `make` 預設;兩條都是翻旗對象,寫法一致一點(都寫或都不寫)。
```

#### #47 兩個斷言沒綁同一行,失敗時看不出哪一半

**File**: `tests/test_signal_rules.py`
**Line**: 927

**Comment**:
```
`count("v3→v4") == 1 and "跳過種子卡" in caplog.text` 兩半沒綁在同一行,`and` 併在一起失敗也看不出是哪半;
實作那行 WARNING 同時含 tag 跟字串,合成 `count("v3→v4:規則數已達上限") == 1` 就好。
```

#### #48 七顆 detector 都養掃單狀態 —— 但既有設計本來就每顆推進全部 kind

**File**: `copycat/live/signal_state.py`
**Line**: 714

**Comment**:
```
(不是 PR 缺陷,參考用)
這條是 Opus 先提、複查後**不算 PR 缺陷**:每顆 per-rule detector 本來就對所有 kind 無條件推進狀態(`evaluate:319-323`,
docstring 692 明寫是刻意的),掃單簇的 60 s deque 比 surge 那顆 300 s 的 `_window` 還小。要省要連舊的一起做,不在這次。
```

#### #49 兩條掃單簇規則會各出一列政策列 —— 但 spec 就是這樣訂的

**File**: `copycat/server/signal_hub.py`
**Line**: 1085

**Comment**:
```
(不是 PR 缺陷,參考用)
這條複查後**不算缺陷**:spec #192 寫明政策掛所有掃單簇規則、列上記 `rule_id`、計數 per (檔, 政策),第二條規則的那一列
`first_of_day=false`、`notify=false`,只進 jsonl 不推播。對帳時用 `first_of_day` 篩就是一檔一筆。
```

#### #50 quiet 列不併入 toast 文案 —— spec 就是要它完全不出現

**File**: `frontend/src/hooks/useSignalAlerts.ts`
**Line**: 205

**Comment**:
```
(不是 PR 缺陷,參考用)
這條複查後**不算缺陷**:spec #192 第 9 條就是要 CDP 穿越 / 爆量從 toast 裡整個消失(rail 淡色仍列),
閘放在 merge 之前正是那個意思,gate 上方註解也寫了。同 tick 的 toast 只印爆拉是預期行為。
```

## CC 主軸原始 findings(first-pass, context-aware)

### Section A — findings(python-reviewer,七個 chunk,逐字濃縮;原文在各 chunk agent 回傳)

#### C1-F1(→ F-01)[MEDIUM] `CONTEXT.md:118` 術語寫「族群沒人鎖過」,code 只看同伴(自己鎖過不擋)

- anchor: `當日成交價曾觸及漲停價(`touched_upper`,當日高 ≥ 漲停)。「族群沒人鎖過」是 P / B 的共同條件。`
- 問題:CONTEXT.md 已定義「同伴 = 族群成員扣掉自己」,故「族群沒人鎖過」字面含自己;`signal_policy.py` 的 `resolve_groups` peers 扣自己、`evaluate_policies` 只算 `peer_touched`,自己的 `touched_upper` 只寫進 `self` 欄不 gate;`signal_policy.py` 模組 docstring 15-16 行同語。B-b 無 <6% 閘,自己已觸漲停仍可命中。
- 建議:文件改「**同伴**沒人鎖過(自己鎖過不擋,列上 `self.touched_upper` 另記)」;若原意含自己 → 改 code 要 user 拍板。

#### C1-F2(→ F-02)[LOW] `copycat/fileio.py:3` 模組 docstring 還寫「兩個 helper」,現在是三個

- anchor: `兩個 helper 對應既有兩種形狀,newline 語意不同**不可互換**:`
- 問題:本 PR 加了 `atomic_write_bytes`(零換行翻譯),模組頭的「兩個 helper / 不可互換」清單是判準表,未同步。
- 建議:改「三個 helper」並補一列 bytes 版說明。

#### C1-F3(→ F-03)[LOW] `copycat/live/signal_state.py:298` 「三道 gate 不推進任何狀態」的承諾已被掃單簇打破

- anchor: `"""一筆成交 tick → 事件清單。三道 gate 任一不過:回 [] 且**不推進任何狀態**。"""`
- 問題:首 tick gate 現在 `return sweep_events`,且 `_eval_sweep` 在它之前已推進 `_lookback` / `_sweep_group`;回值仍 [](群首筆必回 []),但「不推進狀態」字面不成立。
- 建議:docstring 改「前兩道 gate 回 [] 且零推進;首 tick gate 只初始化,掃單簇軸另行推進」。

#### C1-F4(→ F-04)[LOW] `copycat/live/signal_state.py:104` frozen dataclass 裝 dict → 掃單簇事件不可 hash(目前沒人 hash)

- anchor: `    detail: dict[str, float] | None = None`
- 問題:`@dataclass(frozen=True)` 生成 `__hash__`,帶 `detail` 的事件 `hash()` 會 TypeError;外部可就地改內容,hub 在 998 / 1107 各做一次 `dict(...)` 防禦拷貝。
- 建議:改 `tuple[tuple[str, float], ...]`,或明文註記「自 spec #192 起不可雜湊」。

#### C1-F5(→ F-48)[LOW] `copycat/live/signal_state.py:714` 七顆 detector 都養掃單狀態 —— 但既有設計本來就每顆推進全部 kind

- anchor: `        lookback = self._lookback.setdefault(code, deque())`
- 問題:每條規則一顆 detector,`evaluate` 無條件呼叫 `_eval_sweep`,六顆非掃單簇 slot 逐 tick 維護 `_lookback` deque + 群記帳。
- 建議:不改;若日後要省,連 `_window` 一起做 per-slot kind 早退。

#### C1-F6(→ F-05)[LOW] `.claude/mod/signal-shadow-policies/evidence/fake_server.py:17` 取證腳本釘死已消失的 worktree 路徑,重跑必炸

- anchor: `sys.path.insert(0, r"C:\side-project\copycat\.claude\worktrees\mod-signal-shadow-policies")`
- 問題:分支 worktree 收掉後路徑不存在,42-45 行的 `assert "mod-signal-shadow-policies" in __file__` 必失敗;`vite.sidecar.config.ts` 的 `root:` 同病。
- 建議:`Path(__file__).resolve().parents[4]` 自我定位(已驗:`.claude/mod/signal-shadow-policies/evidence/fake_server.py` 的 parents[4] = repo root),assert 改比對 repo root。

#### C1-F7(→ F-06)[LOW] `.claude/mod/signal-shadow-policies/verification.md:65` verification.md 的跑法與 vite 側車設定檔互斥

- anchor: `(preview proxy → 8899;跑時複製到 `frontend/` 再刪)`
- 問題:verification.md 說「複製到 frontend/ 再刪」,但 `vite.sidecar.config.ts` 檔頭寫 `--config ../.claude/...` 且 `import base from "../../../../frontend/vite.config"` 複製後會指到 repo 外。
- 建議:verification.md 改述為實際做法(當時是複製到 frontend/ 跑,且改了 import 為 `./vite.config` + `root: __dirname`)並讓兩檔一致。

#### C1-F8(→ F-07)[LOW] `copycat/server/app.py:821` `live_engine = engine` 別名沒說為什麼

- anchor: `                    live_engine = engine`
- 問題:此別名唯一作用像是閉包窄化,但註解只講日 K 來源;下一手容易順手刪掉。
- 建議:補半行 why-comment 或直接用 `engine`。

#### C2-F1(→ F-49)[MEDIUM] `copycat/server/signal_hub.py:1085` 兩條掃單簇規則會各出一列政策列 —— 但 spec 就是這樣訂的

- anchor: `            count = self._policy_touch.get(key, 0) + 1`
- 問題:政策層掛在每一條 `sweep_cluster` 規則,`_policy_touch` 以 (code, policy) 記帳、id 含 `rule_id`;第二條規則同顆事件再出一列(first_of_day=false)進 jsonl,離線讀者無去重。
- 建議:不改;對帳腳本以 `first_of_day` 或 (code, policy, date) 去重即可。

#### C2-F2(→ F-08)[MEDIUM] `copycat/server/signal_hub.py:1321` 回填的「逾時」except 在 prod 走不到,逾時因此零記錄

- anchor: `        except HistoryTimeoutError as exc:`
- 問題:app `_outcome_bars` → `StockEngine.bars_range` 只 `except ConnectionError` 回 `BarsResult([], "disconnected")`,`HistoryTimeoutError` 是它的子類(tc4.py:69);`fetch_bars_range` 本身也只回 status 不拋;`.bars` 又丟掉 status → 13:40 遇 TC4 忙只印「共回填 0 列」。
- 建議:`_outcome_bars` 改回 `BarsResult`,`_fetch_outcome_bars` 對 `status != "ok"` 印 WARNING,刪不可達的 except。

#### C2-F3(→ F-09)[MEDIUM] `copycat/server/signal_hub.py:1271` 整檔嚴格解碼:一個壞位元組讓那一天整檔 5 天內都跳過

- anchor: `                text = (await asyncio.to_thread(path.read_bytes)).decode("utf-8")`
- 問題:姊妹 `read_signals` docstring 記載半寫入切在多位元組中間**實際發生過**、改用 `errors="replace"`;這裡 strict → 那天所有政策列 t1/t2 永久留 null(有 WARNING)。
- 建議:改逐行 bytes 處理:壞行原樣保留 bytes、好行照補 —— 既守「其餘列逐字不變」又不因一行毀整檔。

#### C2-F4(→ F-10)[LOW] `copycat/server/signal_hub.py:214` `format_policy_group_text` 對外但沒守「至少一列政策列」

- anchor: `    head = policies[0]`
- 問題:在 `__all__` 對外,前置條件只存在於唯一呼叫點 `_send_discord` 的 `any(_is_policy)`;直接呼叫拿裸 IndexError。
- 建議:空 → 退回 `format_signal_group_text` 或 raise ValueError 具名。

#### C2-F5(→ F-11)[LOW] `copycat/server/stock_engine.py:763` 每顆掃單簇事件對整份自選(≤150)組快照,hub 只讀幾個同伴

- anchor: `    def policy_quotes(self) -> dict[str, PeerQuote]:`
- 問題:`policy_quotes()` 無 code 參數,`_emit_policies` 在 on_tick 同步熱路徑呼叫,每次 150 次 dict 組裝 + `_quote_payload` + `_best_limit_price` 掃五檔。
- 建議:`policy_quotes(codes: list[str] | None = None)`,hub 傳 `peer_codes`(簽名層面建議,未實跑;`:773` 目前 `codes = self._watchlist`,改成 `codes or self._watchlist` 即可)。

#### C2-F6(→ F-12)[LOW] `copycat/server/stock_engine.py:778` no_data 的同伴連名字都被清空,姊妹 `quotes()` 不是這樣

- anchor: `            meta = state.meta if state is not None and not no_data else None`
- 問題:`quotes()` 的 `meta = state.meta if state is not None else None` 不看 no_data、名稱照給;本方法 docstring 寫「同 quotes()」但 name 也歸空 → 政策列 `peers[]` 印空名。
- 建議:name 沿 `quotes()` 口徑取 `state.meta`,只讓值欄位吃 no_data。

#### C2-F7(→ F-13)[LOW] `copycat/server/signal_policy.py:156` 政策順序不變式寫兩處;`tuple(policy_exclude_groups)` 是 no-op

- anchor: `    if quoted and not peer_touched:`
- 問題:`hits` 已依 `POLICIES` 序建成,hub 又 `for policy in POLICIES: if policy not in ctx.hits`;`exclude=tuple(cfg.policy_exclude_groups)` 對已是 tuple 的欄無作用。
- 建議:hub 直接 `for policy in ctx.hits`;刪 `tuple()`。

#### C2-F8(→ F-14)[LOW] `copycat/server/signal_hub.py:68` 為一個字串常數,訊號層拖進 FinMind 那整串模組

- anchor: `from copycat.server.screen_engine import SCREEN_GROUP`
- 問題:`signal_hub` import `screen_engine.SCREEN_GROUP` → 傳遞相依 screening / market_breadth / breadth_fetch / watchlist_service(無循環)。
- 建議:不動;真要收,下沉常數到葉子模組並同步 CLAUDE.md §4 那條契約。

#### C3-F1(→ F-15)[MEDIUM] `copycat/signal_rules.py:111` `_QUIET_KINDS` 裡的 sweep_cluster 是死資料,靜音真值在種子卡字面

- anchor: `_QUIET_KINDS: frozenset[str] = frozenset({"cdp_cross", "vol_burst", "sweep_cluster"})`
- 問題:`default_rules` 在通用分支前就把 sweep_cluster 攔給 `_sweep_seed_rule`(字面 `notify_discord: False`),`kind not in _QUIET_KINDS` 對它永不求值;docstring 353 行說的口徑不成立。
- 建議:刪 sweep 專屬分支(通用分支產出逐欄相同),或讓 `_sweep_seed_rule` 讀集合。

#### C3-F2(→ F-16)[LOW] `copycat/signal_rules.py:444` 掃單簇種子撞名跳過只印 INFO,可是這等於整個政策層不會有事件

- anchor: `        logger.info("訊號規則檔 %s:已有同名規則,跳過種子卡 %r", tag, name)`
- 問題:政策列只掛掃單簇事件,種子卡是唯一觸發源;既有任一條名為「掃單簇」的規則(不論 kind)→ 四週影子期零事件,log 只有 INFO;滿 30 那條反而是 WARNING。
- 建議:v3→v4 撞名改 WARNING 並補一句後果。

#### C3-F3(→ F-17)[MEDIUM] `frontend/src/lib/signal-model.ts:281` 「同伴≥3% n・鎖過 有/無」在第三行與 hover 各寫一份

- anchor: `  const up = sig.peers_up === undefined ? "-" : String(sig.peers_up);`
- 問題:`policyContextText` 與 `policyTitle` 各自組同一句,缺值口徑還不同(`?? "-"` vs `=== undefined`);改字面時一邊不會紅。
- 建議:抽 `peerPhrase(sig)` 共用。

#### C3-F4(→ F-18)[LOW] `frontend/src/lib/signal-model.test.ts:369` `policyTitle` 六段只被四個 `toContain` 摸到

- anchor: `describe("政策組:標記 / 文案 / toast"`
- 問題:測試零直呼 `policyTitle`;`when` 段(tod / 首筆 / late)、無族群分支「盤前篩選名單・無族群濾網」、「(族群最強)」後綴、`｜` 分隔皆未覆蓋。
- 建議:在 `signal-model.test.ts` 補一條全字串字面斷言(有族群 + 無族群各一)。

#### C3-F5(→ F-19)[LOW] `frontend/src/lib/signal-model.ts:97` `isPolicy` 不是型別謂詞;八個政策欄前端零讀者

- anchor: `export function isPolicy(sig: SignalMsg): boolean {`
- 問題:`isPolicy` 回 boolean,非政策列讀 `sig.peers_up` TS 也放行;`detail / sweep / screen_member / peer_max / t1_open / t1_date / t2_open / t2_date` 前端零讀者。
- 建議:把零讀者欄位在型別上註明「wire 形狀存證(jsonl 回看用)」;型別謂詞可選。

#### C3-F6(→ F-20)[LOW] `frontend/src/components/stock/SignalRail.tsx:259` 列高預算註解已失真;合併列時 chip 會自己占一行

- anchor: `封在 1 + 2 + 1 行,不是 1 + 2 + 2。 */}`
- 問題:政策第三行讓上限變 1+2+1+1;chip 容器在 `merged ? "flex flex-col"` 分支與 kind 段堆疊,spec 要求第二行 = chip + kind 文案 + 價。
- 建議:更新註解到新上限;chip 可考慮移出 merged 容器。

#### C3-F7(→ F-50)[LOW] `frontend/src/hooks/useSignalAlerts.ts:205` quiet 列不併入 toast 文案 —— spec 就是要它完全不出現

- anchor: `      if (!shouldNotify(sig)) return;`
- 問題:閘在 merge index 之前 → quiet 列永不進 `entry.items`;同 tick「CDP 穿越 + 爆拉」toast 只印爆拉、rail 印兩段。
- 建議:不改。

#### C3-F8(→ F-21)[LOW] `frontend/src/hooks/useSignalAlerts.ts:225` 雙嗶規則在合併分支與新組分支各寫一份

- anchor: `        if (firstPolicy && getSoundOn()) {`
- 問題:合併分支 `firstPolicy → playBeep + playBeep(OFFSET)`,新組分支 `playBeep(); if (isPolicy) playBeep(OFFSET)`;「政策 = 雙嗶」重複兩份。
- 建議:抽 `beep(double: boolean)`。

#### C3-F9(→ F-22)[LOW] `frontend/src/components/stock/SignalRulesDialog.test.tsx:209` 測試拿 Tailwind class 當選擇器

- anchor: `expect(within(sweepRow).getByText("掃單簇", { selector: "span.rounded" })).toBeTruthy();`
- 問題:規則名與 kind 徽章同為「掃單簇」,靠 `span.rounded`(樣式 class)消歧;改圓角就紅在跟行為無關的地方。
- 建議:改 `data-testid` 或 `getAllByText("掃單簇").length === 2`(已驗:該列只有 `:354` 規則名 span 與 `:357` `KIND_LABEL` 徽章兩個文字節點等於「掃單簇」,摘要行不等)。

#### C4-F1(→ F-23)[MEDIUM] `tests/live/test_signal_state.py:882` 換日 / 移出自選的掃單簇清狀態測試:註解說的機制是假的,單欄突變全存活

- anchor: `        assert ev == []  # 掃單 1 已被丟掉 → n30 = 1`
- 問題:實測 `test_reset_day_clears_sweeps_and_lookback` 末群 n30 = 2(不是註解的 1)、回看窗非空,真正擋事件的是 `up_pct = 0`(基準筆餵在群之後);`reset_day` 不清 `_sweeps` 仍綠;`drop_code` 三個單欄突變都綠;`test_drop_code_clears_only_that_code` 只有一檔,「only that code」無斷言。
- 建議:先餵基準筆(up_pct > 0),重置後只留一個掃單群讓 n30 成唯一約束;drop 案加第二檔並斷言它仍能發訊;註解對齊。

#### C4-F2(→ F-24)[MEDIUM] `tests/live/test_signal_state.py:817` golden self-check 用位置配對 + strict zip,把偶然的等數量變硬閘

- anchor: `for a, b in zip(case["expected_research"], case["expected_prefix"], strict=True)`
- 問題:三案 research / prefix 事件數剛好相等;spec 明寫即時判會多發 0.7%,重錄換股票日多出 prefix 列時失敗樣態是 `zip()` ValueError 而非有意義斷言。
- 建議:以 `ms` 建索引配對,斷言 research_ms ⊆ prefix_ms,配到的 pair 才比 `i` / `levels`。

#### C4-F3(→ F-25)[LOW] `tests/fixtures/record_sweep_cluster_golden.py:66` 參考碼沒有 09:00–13:30 的 session gate,等式只是這三檔的巧合

- anchor: `        if p and p > 0 and q and q > 0:`
- 問題:`SignalDetector.evaluate` 先過 session gate(13:30 end-exclusive);三案末筆都是 13:30:00.000 的收盤撮合,參考碼收下、偵測器丟。
- 建議:`load_rows` 濾 [09:00, 13:30),或 docstring 記「前提:檔內無盤外群」。

#### C4-F4(→ F-26)[LOW] `tests/fixtures/record_sweep_cluster_golden.py:137` oracle 強度分兩半,docstring 沒分段

- anchor: `def clusters_prefix(`
- 問題:`find_sweeps_final` / `clusters_final` / prefix 的掃單合格半段與研究腳本逐行相符;prefix 的簇窗 / 60 s 漲幅 / 去重 / qty 前綴半段沒有研究對應物,是與偵測器同批寫的第二份實作(bisect vs deque,非套套邏輯)。
- 建議:docstring 分段標明哪半是研究真值、哪半是本案自撰。

#### C5-F1(→ F-27)[HIGH] `tests/server/test_signal_outcome.py:109` 回填「保留行尾」那段邏輯零覆蓋:測試全 LF,prod 檔是 CRLF

- anchor: `    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))`
- 問題:`_append_jsonl` 文字模式 append 在 Windows 寫 CRLF;`_write_day` 刻意 `write_bytes` 純 LF,全檔零 CRLF 案;`lines[i][len(body):]` 那段行尾接回是唯一為 CRLF 寫的邏輯。
- 建議:`_write_day` 收 `eol` 參數,byte 比對案對 `["\n", "\r\n"]` parametrize,斷言改整段 bytes 比對。

#### C5-F2(→ F-28)[MEDIUM] `tests/server/test_signal_outcome.py:256` 三種失敗共用一句子字串斷言,warning ↔ exception 分不出來

- anchor: `        [HistoryTimeoutError("DK 逾時"), ConnectionError("TC4 不可用"), RuntimeError("炸")],`
- 問題:實作刻意讓逾時走 `logger.warning`(無 traceback)、其餘走 `logger.exception`;測試不驗 `levelno` / `exc_info`。
- 建議:parametrize 加 `expect_exc`,斷言 `caplog.records[-1].exc_info` 是否為 None。

#### C5-F3(→ F-29)[LOW] `tests/server/test_signal_outcome.py:289` 「回填 2 列」同時命中逐檔行與彙總行

- anchor: `        assert "回填 2 列" in caplog.text`
- 問題:per-file 行「回填 2 列(1 檔)」與收尾「共回填 2 列」互為子字串,刪掉逐檔行仍綠。
- 建議:斷言含檔數 `"回填 2 列(1 檔)"`。

#### C5-F4(→ F-30)[LOW] `tests/server/test_signal_outcome.py:370` 以 coroutine 名字面做否定斷言,改名後恆真

- anchor: `            names = {getattr(t.get_coro(), "__name__", "") for t in h.hub._tasks}`
- 問題:`"_policy_outcome_worker" not in names` 沒有正向孿生案;rename 後永遠不紅。
- 建議:改比 `type(h.hub)._policy_outcome_worker.__name__`,或直接斷 `bars` 零呼叫。

#### C5-F5(→ F-31)[LOW] `tests/server/test_signal_outcome.py:46` 手抄的政策列 fixture 沒釘到 `_POLICY_KEYS`

- anchor: `def _policy_row(code: str, policy: str = "P", **over: Any) -> dict[str, Any]:`
- 問題:fixture 與產生點 `_emit_policies` 無 parity;鍵序斷言是拿 fixture 自己比自己。
- 建議:加一句 `assert set(_policy_row("2330")) == _POLICY_KEYS | {"trade_date"}`。

#### C5-F6(→ F-32)[LOW] `tests/server/test_signal_outcome.py:307` 用 `asyncio.sleep(0.05)` 證「沒再跑」,負載重時可能零輪詢

- anchor: `            assert len(bars.calls) == 1  # 10:00 未到 13:40 → 不再跑`
- 問題:否定命題靠牆鐘時間;正向等待有 `_wait_calls` deadline 迴圈,負向沒有計數器。
- 建議:fake 加正向輪詢計數,先等到「輪詢過 N 次」再斷 calls 未增。

#### C6-F1(→ F-33)[MEDIUM] `tests/server/test_signal_policy.py:321` `peers_fn` 拋例外的降級路徑(quotes={} / 當日一次 traceback / 換日復位)零測試

- anchor: `    async def test_no_peer_quotes_means_no_p_or_b(self, tmp_path: Path, clock: _Clock) -> None:`
- 問題:`signal_hub.py:1044-1051` 整段 except + `_peers_fn_failed` 沒任何測試走;`_Watch` 有 `groups_error` / `quotes_error` 卻缺 `peers_error`,其 docstring 明寫「兩條失敗路徑都要有替身」。
- 建議:`_Watch` 加 `peers_error`;一案:peers_fn 拋 → `_policies == ["S"]`、raw 列在、caplog 只一則、換日後再印。

#### C6-F2(→ F-34)[MEDIUM] `tests/server/test_stock_engine.py:1332` `TestPolicyQuotes` docstring 承諾 no_data,卻沒有一案打 `on_no_data`

- anchor: `    no_data / 缺 meta / 未成交 → 值欄位 None **但鍵仍在**(整檔缺席會讓「族群有幾檔」跟著波動)。`
- 問題:四案是有報價 / 缺 meta / 鎖過鎖死 / 排除偽鍵,無 `src.on_no_data(...)` 案(同檔四個先例),也無「有簿無成交」案;mutant `no_data = False` 全綠 → 舊 `high` 讓 `peer_touched=True` 靜默封殺整族 P/B。
- 建議:補兩案:`on_no_data` 後全值欄 None 鍵仍在;只送簿更新 → price/high/locked/touched None。

#### C6-F3(→ F-35)[LOW] `tests/server/test_stock_engine.py:1348` `test_quoted_stock_full_snapshot` 沒 `await engine.close()`

- anchor: `        assert q["touched_upper"] is False and q["locked_up"] is False`
- 問題:同 class 其餘三案都 close;全檔只 5 案漏(4 案既有)。
- 建議:補一行 close。

#### C6-F4(→ F-36)[LOW] `tests/server/test_signal_policy.py:591` `_fmt` 放在兩個 class 中間,且進位邊界會印 `60.000`;參數化案缺 kind 斷言

- anchor: `    return f"{hh:02d}:{mm:02d}:{ss:06.3f}"`
- 問題:helper 與檔頭 helper 區分家;`ss` 夠接近 60 會印非法時刻(現行 10 組參數已追過,安全);參數化案沒 `assert p["kind"] == "policy"`,壞掉時是 KeyError。
- 建議:毫秒整數 `divmod`、移到檔頭、補 kind 斷言。

#### C6-F5(→ F-37)[LOW] `tests/server/test_signal_policy.py:107` 三處 `type: ignore` 只因群組治具是裸 dict

- anchor: `    wl = _Watch(groups=groups or [], peers=peers or {})  # type: ignore[arg-type]`
- 問題:`_MEM / _SCREEN / _ALL_IN` 宣告成裸 dict → 107 / 206 / 662 各壓一個 ignore;`Group` 只有兩鍵,標註即可。
- 建議:`_MEM: Group = {...}`。

#### C6-F6(→ F-38)[LOW] `tests/server/test_signal_policy.py:560` 換日 / 移出自選歸零兩案沒斷「真的又推了一次」

- anchor: `            assert [(p["touch_count"], p["first_of_day"]) for p in ps] == [(1, True), (1, True)]`
- 問題:#195 驗收語是「換日後首筆再度推播」,兩案只斷 `first_of_day`;`h.bot` 這條證據同檔 491 行已在用。
- 建議:加 `assert len(h.bot) == 2`(:582 同)。

#### C6-F7(→ F-39)[LOW] `tests/server/test_signal_routes.py:55` `_SEEDED_KINDS` 補了 sweep_cluster,同檔 `_RULE_PARAMS` 複製表沒補

- anchor: `    "sweep_cluster",`
- 問題:`_rule_body("sweep_cluster", …)` 一寫就 KeyError;兩份複製表(與 test_signal_hub 的)自此發散。
- 建議:從 `test_signal_hub` import 那張表(本 PR 已立跨檔 import 先例)。

#### C6-F8(→ F-40)[LOW] `tests/server/test_signal_policy.py:624` 兩政策合併卡只驗第 0/2/3 行,第 1 行與行數沒守

- anchor: `            assert len(h.bot) == 1`
- 問題:同檔 681 行的合併案有 `len(lines) == 4`;B-a/B-b 路徑的掃單簇量那行無人看。
- 建議:補 `lines[1]` 與 `len(lines) == 4`。

#### C7-F1(→ F-41)[MEDIUM] `tests/test_signal_rules.py:407` 種子通知旗以 kind 當 key,兩張回檔卡塌成一張

- anchor: `        assert {r["kind"]: r["notify_discord"] for r in rules} == {`
- 問題:同 class 兩處(390 / 433)明寫「by name 不 by kind」;七條種子只比到六鍵。
- 建議:改 by name 七鍵逐條(同 :477 `test_cooldowns_seeded_per_kind`)。

#### C7-F2(→ F-42)[LOW] `tests/test_signal_rules.py:255` 整數鍵「接受整數浮點」案沒補 sweep 兩鍵,姊妹拒收案有補

- anchor: `    def test_integer_keys_accept_integral_float(self, kind: str, key: str) -> None:`
- 問題:`test_integer_keys_reject_fractional` 加了 `min_sweeps` / `min_levels`,接受案沒有;前端 JSON 送 `2.0` 的接受側對新 kind 無案。
- 建議:補兩組參數。

#### C7-F3(→ F-43)[LOW] `tests/test_signal_rules.py:899` 案名說「不重複 log」,斷言是「一次都不 log」

- anchor: `    def test_v3_already_quiet_rule_not_logged_twice(`
- 問題:docstring 寫「不翻、不 log」,斷言 `count == 0`。
- 建議:更名 `..._not_flipped_and_not_logged`。

#### C7-F4(→ F-44)[LOW] `tests/test_signal_rules.py:745` id 去重案的 docstring 還指 `_migrate_v2`,迴圈已搬到 `_append_seed`

- anchor: `        """`_migrate_v2` 的 while 去重迴圈(review F-04):既有規則恰佔走種子要配的 id`
- 問題:本 PR 把 while 去重搬進共用 `_append_seed`;此案現在一趟吃三次 append(佔 `-001` → 種子 `-002/-003/-004`),`-003` 被佔的情境無覆蓋。
- 建議:docstring 改指 `_append_seed`,說明第三張卡也走同一迴圈;可選加 `-003` 被佔參數。

#### C7-F5(→ F-45)[LOW] `tests/test_signal_rules.py:833` 遷移種子「不吃設定檔覆寫」這個分歧,測試側沒複述

- anchor: `    (enabled、通知關、冷卻 60、參數 = 全域設定預設)、(b) cdp_cross / vol_burst 規則通知`
- 問題:seed params 以字面 30/2/2/0.3/60 斷言恰等於 `SignalsConfig()` 預設;`_migrate_v3` 硬寫 `SignalsConfig()` 而 `default_rules` 吃 cfg,測試分不出兩種語意。
- 建議:class docstring 加一句「= `SignalsConfig()` 預設,刻意不吃設定檔覆寫(同 v2→v3)」。

#### C7-F6(→ F-46)[LOW] `tests/test_signal_rules.py:844` `_v3_set` 只在 vol_burst 顯式寫前置條件,cdp 靠預設

- anchor: `            make("vol_burst", id="r-1-002", name="爆量", notify_discord=True),`
- 問題:`make` 預設 `notify_discord=True`;兩條翻旗對象只有一條寫明,讀者易誤讀。
- 建議:兩條都顯式或都不寫。

#### C7-F7(→ F-47)[LOW] `tests/test_signal_rules.py:927` 兩個斷言沒綁同一行,失敗時看不出哪一半

- anchor: `        assert caplog.text.count("v3→v4") == 1 and "跳過種子卡" in caplog.text`
- 問題:姊妹案 771 行是 `count("跳過種子卡") == 3`;實作是單一行 WARNING 同時含 tag 與字串。
- 建議:合成 `count("v3→v4:規則數已達上限") == 1`。

### Section B — per-file accounting(43/43)

- chunk 1(15):findings 7 檔(CONTEXT.md / fileio.py / signal_state.py / evidence/fake_server.py / evidence/vite.sidecar.config.ts / verification.md / app.py);`REVIEWED_NO_ISSUES` CLAUDE.md(§4 五條契約逐條對 code)、tc4-market-facts SKILL.md、code-review-round-1.json(抽驗兩條「已修」聲明落地);`INTENTIONALLY_SKIPPED` migration-dry-run.txt / sidecar-rules-curl.txt / sidecar-startup-log.txt(純 log,與 code 的 log 字面相符)、rules-dialog-list.png / rules-dialog-sweep-edit.png(二進位)。
- chunk 2(3):findings 3 檔(signal_hub.py / signal_policy.py / stock_engine.py);另確認 `_policy_touch` 在 publish 後記帳、rollover / drop_code 三份 state 全清、回填 cutoff 與 jsonl worker 無同檔競寫、`splitlines(keepends)` 逐字往返、worker 排程與 close 路徑正確;四條政策判定逐條比對 spec 相符。
- chunk 3(13):findings 6 檔(signal_rules.py / SignalRail.tsx / SignalRulesDialog.test.tsx / useSignalAlerts.ts / signal-model.ts / signal-model.test.ts);`REVIEWED_NO_ISSUES` signals_config.py、SignalRail.test.tsx、SignalRulesDialog.tsx、useSignalAlerts.test.tsx、useSignalRules.ts、signal-param-parity.test.ts、signal-params.ts(fixture 六鍵三邊逐值對過)。
- chunk 4(5):findings 2 檔(record_sweep_cluster_golden.py / test_signal_state.py);`REVIEWED_NO_ISSUES` signal_param_specs.json、test_signal_hub.py(8 條 TestSweepCluster 逐案追、`loud_seeds` 無靜默減損);`INTENTIONALLY_SKIPPED` sweep_cluster_golden.json(70 KB 單行產物;已解析核對三案 ticks 501/921/753、事件 4/4、5/5、2/2、每案含「早於群末」pair)。
- chunk 5(1):findings 1 檔(test_signal_outcome.py)。
- chunk 6(4):findings 3 檔(test_signal_policy.py / test_stock_engine.py / test_signal_routes.py);`REVIEWED_NO_ISSUES` test_stock_routes.py。跨測試檔 import 有先例(test_compare / test_signal_routes),無雙重 collection。
- chunk 7(2):findings 1 檔(test_signal_rules.py);`REVIEWED_NO_ISSUES` test_signals_config.py(12 個新鍵字面全覆蓋、tuple 轉型有案)。

## Codex 原始 findings

N-A —— user 明示停用 Codex(中性與對抗兩軸皆不跑;沿 #188 / #190 前例)。

## Gemini 原始 findings

N-A —— user 明示停用 Gemini(Flash / Pro 皆不跑)。

## CC 對非 CC 軸的複查結果(Step 4.1)

N-A —— 本輪無非 CC finding。

## 內部複查結果(Step 4.2 之替代;同軸 code-reviewer、非跨軸證據)

兩批(A:C1–C3 共 25 條 / B:C4–C7 共 25 條)並行,各回 STRICT JSON、ID 集合與輸入精確相等、每列 `codex_verdict / corrected_severity / severity_reason / codex_evidence` 四欄齊。分佈:CONFIRMED 37 / PARTIAL 10 / REFUTED 3 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0。校正 severity:MEDIUM 3(C4-F1 / C5-F1 / C6-F1,皆測試覆蓋缺口)、其餘 47 條 LOW。

| CC # | reviewer | title | Verdict | 原始 → 校正 severity | 複查 evidence | 備註 |
|---|---|---|---|---|---|---|
| C1-F1(F-01) | python-reviewer | 術語寫「族群沒人鎖過」,code 只看同伴(自己鎖過不擋) | CONFIRMED | MEDIUM→LOW | spec #192 Implementation Decisions 字面就是「非 peer_touched」,code 合規;drift 只在 CONTEXT.md / docstring 措辭,列上 `self.touched_upper` 有記,對帳可重算。 | 採納 |
| C1-F2(F-02) | python-reviewer | 模組 docstring 還寫「兩個 helper」,現在是三個 | CONFIRMED | LOW→LOW | `atomic_write_text:20`、`atomic_write_bytes:26`、`atomic_open_text:33` 三個;純文件。 | 採納 |
| C1-F3(F-03) | python-reviewer | 「三道 gate 不推進任何狀態」的承諾已被掃單簇打破 | CONFIRMED | LOW→LOW | `_eval_sweep:722-729` 群首筆 return [],觀察值不變;相鄰註解 305-307 已講例外,只有 docstring 那句失真。 | 採納 |
| C1-F4(F-04) | python-reviewer | frozen dataclass 裝 dict → 掃單簇事件不可 hash(目前沒人 hash) | CONFIRMED | LOW→LOW | probe `hash(SignalEvent(detail={...}))` → TypeError;grep 消費端只 list 傳遞,零 hash 呼叫點,latent。 | 採納 |
| C1-F5(F-48) | python-reviewer | 七顆 detector 都養掃單狀態 —— 但既有設計本來就每顆推進全部 kind | REFUTED | LOW→LOW | `signal_state.py:190-209` 每顆 detector 都持 `_prev/_window/_pullback/...`,`evaluate:319-323` 對所有 kind 無條件推進(docstring 692「狀態推進無條件」是刻意設計);sweep 窗 60 s 還小於 surge 的 300 s,非新量級。 | REFUTED → 參考用 |
| C1-F6(F-05) | python-reviewer | 取證腳本釘死已消失的 worktree 路徑,重跑必炸 | CONFIRMED | LOW→LOW | probe 以同 sys.path 匯入,app.__file__ 落在別處、assert False;純 evidence 產物,不影響產品碼。 | 採納 |
| C1-F7(F-06) | python-reviewer | verification.md 的跑法與 vite 側車設定檔互斥 | CONFIRMED | LOW→LOW | 兩述至少一假;artifact 文件自相矛盾,無 runtime 影響。 | 採納 |
| C1-F8(F-07) | python-reviewer | `live_engine = engine` 別名沒說為什麼 | CONFIRMED | LOW→LOW | pyright probe 顯示 lambda 與 async def 都能捕捉已收斂的 `engine`(同段 :819 直接用 engine),窄化不是成立理由 → 用意未交代。 | 採納 |
| C2-F1(F-49) | python-reviewer | 兩條掃單簇規則會各出一列政策列 —— 但 spec 就是這樣訂的 | REFUTED | MEDIUM→LOW | spec #192 明訂「任一條該 kind 規則的事件都評,列上記 rule_id」+「每日計數 per (檔, 政策)」+ story 7「對帳統計本來就是同檔一筆」;第二列 notify=False 不進 Discord(`_enqueue:1128`)。 | REFUTED → 參考用 |
| C2-F2(F-08) | python-reviewer | 回填的「逾時」except 在 prod 走不到,逾時因此零記錄 | CONFIRMED | MEDIUM→LOW | dead except + 逾時訊號流失;列會在下一趟再補,無資料丟失,純可觀測性。`test_signal_outcome.py:256` 注入 HistoryTimeoutError 給了假信心。 | 採納 |
| C2-F3(F-09) | python-reviewer | 整檔嚴格解碼:一個壞位元組讓那一天整檔 5 天內都跳過 | PARTIAL | MEDIUM→LOW | 確實整檔跳過,但 except 有 WARNING 非靜默;`read_signals` 用 replace 是因為它不回寫,回填要位元組逐字保留、strict 反而避免把 U+FFFD 寫回檔案。 | PARTIAL:只採成立的那半 |
| C2-F4(F-10) | python-reviewer | `format_policy_group_text` 對外但沒守「至少一列政策列」 | CONFIRMED | LOW→LOW | Grep `format_policy_group_text` over `copycat/ tests/` → `signal_hub.py:99`(`__all__`)/ `:161`(註解)/ `:1432`(唯一 caller,前一行 `any(_is_policy(row) ...)` gate),tests 零直呼 → 目前不可觸發。 | 採納 |
| C2-F5(F-11) | python-reviewer | 每顆掃單簇事件對整份自選(≤150)組快照,hub 只讀幾個同伴 | CONFIRMED | LOW→LOW | 每檔 60 s 冷卻限住呼叫率,零 IO 仍成立,成本可忽略。 | 採納 |
| C2-F6(F-12) | python-reviewer | no_data 的同伴連名字都被清空,姊妹 `quotes()` 不是這樣 | CONFIRMED | LOW→LOW | no_data 的 chg_pct 亦 None 不入 quoted/peer_max,只是快照少了名字;無測試。 | 採納 |
| C2-F7(F-13) | python-reviewer | 政策順序不變式寫兩處;`tuple(policy_exclude_groups)` 是 no-op | CONFIRMED | LOW→LOW | 純風格,零行為風險。 | 採納 |
| C2-F8(F-14) | python-reviewer | 為一個字串常數,訊號層拖進 FinMind 那整串模組 | PARTIAL | LOW→LOW | 傳遞相依屬實(probe sys.modules 證實)、無循環;但 CLAUDE.md §4 明訂 `SCREEN_GROUP` 產生點 = `screen_engine`,搬家等於改契約(app 本來就 import 它)。 | PARTIAL:只採成立的那半 |
| C3-F1(F-15) | python-reviewer | `_QUIET_KINDS` 裡的 sweep_cluster 是死資料,靜音真值在種子卡字面 | CONFIRMED | MEDIUM→LOW | Grep `_QUIET_KINDS` over `copycat/ tests/` → `signal_rules.py:111`(定義)/ `:353`(docstring)/ `:381`(唯一讀點,通用分支);`:370-374` sweep 分支先 return 故 `:381` 對 sweep_cluster 永不求值。改集合對掃單簇零效果、測試不紅;現值恰好一致。 | 採納 |
| C3-F2(F-16) | python-reviewer | 掃單簇種子撞名跳過只印 INFO,可是這等於整個政策層不會有事件 | CONFIRMED | LOW→LOW | 前提需既有規則恰名「掃單簇」(v3 無此 kind),罕見但可能。 | 採納 |
| C3-F3(F-17) | python-reviewer | 「同伴≥3% n・鎖過 有/無」在第三行與 hover 各寫一份 | PARTIAL | MEDIUM→LOW | 重複屬實;差異只在 null,但型別 `peers_up?: number` 不含 null、後端恆送 int,不可觸發。 | PARTIAL:只採成立的那半 |
| C3-F4(F-18) | python-reviewer | `policyTitle` 六段只被四個 `toContain` 摸到 | CONFIRMED | LOW→LOW | Grep `policyTitle` over `frontend/src`(排除定義檔)→ 唯一命中 `SignalRail.tsx:19`(import)/ `:277`(呼叫),測試檔零命中;唯一覆蓋 = `SignalRail.test.tsx` 那幾個 `toContain`。hover-only 字串,最壞是靜默漂移。 | 採納 |
| C3-F5(F-19) | python-reviewer | `isPolicy` 不是型別謂詞;八個政策欄前端零讀者 | PARTIAL | LOW→LOW | Grep `peer_max` / `screen_member` / `t1_open` over `frontend/src`(非測試檔)→ 各只命中 `lib/signal-model.ts`(型別宣告);`sweep` / `t2_open` 同;`detail` 因同名於 api-error 等模組另有命中,但 `sig.detail` 零存取。零讀者屬實;`SignalMsg` 是單一介面、欄位皆 optional,型別謂詞在此收斂不到什麼。 | PARTIAL:只採成立的那半 |
| C3-F6(F-20) | python-reviewer | 列高預算註解已失真;合併列時 chip 會自己占一行 | PARTIAL | LOW→LOW | 註解過期屬實;chip 堆疊只在 merged 邊角(政策列與 raw 掃單簇文案去重成一段,常態 merged=false,chip 仍同行)。 | PARTIAL:只採成立的那半 |
| C3-F7(F-50) | python-reviewer | quiet 列不併入 toast 文案 —— spec 就是要它完全不出現 | REFUTED | LOW→LOW | spec #192 story 9「CDP 穿越、爆量停止一切推播(Discord、toast、嗶聲、桌面通知)但 rail 淡色仍列」;gate 上方註解已逐字寫明。 | REFUTED → 參考用 |
| C3-F8(F-21) | python-reviewer | 雙嗶規則在合併分支與新組分支各寫一份 | CONFIRMED | LOW→LOW | DRY nit,零行為風險。 | 採納 |
| C3-F9(F-22) | python-reviewer | 測試拿 Tailwind class 當選擇器 | CONFIRMED | LOW→LOW | 全 frontend 其餘 `selector:` 用法皆為元素名(SVG `text`),無第二處以樣式類定位 → 非既有慣例;失效是大聲紅不是假綠。 | 採納 |
| C4-F1(F-23) | python-reviewer | 換日 / 移出自選的掃單簇清狀態測試:註解說的機制是假的,單欄突變全存活 | CONFIRMED | MEDIUM→MEDIUM | trace 實測 sweeps=[36090.5, 36100.5],lookback0 未過 cutoff → up_pct=0;mutant 全綠;既有 `TestLifecycle:952` / `TestSurgePullback:1150` 同名測試都用兩個 code。 | 採納 |
| C4-F2(F-24) | python-reviewer | golden self-check 用位置配對 + strict zip,把偶然的等數量變硬閘 | CONFIRMED | MEDIUM→LOW | 探測三案 ms 清單完全相同;`b["ms"] == a["ms"]` 會擋錯位,失效是大聲的 ValueError 不是假綠。 | 採納 |
| C4-F3(F-25) | python-reviewer | 參考碼沒有 09:00–13:30 的 session gate,等式只是這三檔的巧合 | CONFIRMED | LOW→LOW | 三案該毫秒各只一筆(不成群、零掃單),去掉末筆結果完全相同 → 目前等式不受影響;重錄挑到含盤外群的日子才會出事。 | 採納 |
| C4-F4(F-26) | python-reviewer | oracle 強度分兩半,docstring 沒分段 | CONFIRMED | LOW→LOW | 讀 `sweep_prefix_scan.py` 全文證實只做群內達標統計;純文件精確度。 | 採納 |
| C5-F1(F-27) | python-reviewer | 回填「保留行尾」那段邏輯零覆蓋:測試全 LF,prod 檔是 CRLF | CONFIRMED | HIGH→MEDIUM | mutant 把行尾硬寫 `"\n"` → 171 tests 全綠;真碼對 CRLF 檔實跑 2 CRLF / 0 lone LF(分支確有效)。實害限於被補的列行尾混雜。 | 採納 |
| C5-F2(F-28) | python-reviewer | 三種失敗共用一句子字串斷言,warning ↔ exception 分不出來 | CONFIRMED | MEDIUM→LOW | mutant warning→exception 171 tests 全綠;但 traceback 量受限於檔數 × 日檔、每日兩趟,非 #146 等級洪水。repo 有 13 個測試檔斷言 levelno / exc_info。 | 採納 |
| C5-F3(F-29) | python-reviewer | 「回填 2 列」同時命中逐檔行與彙總行 | CONFIRMED | LOW→LOW | mutant 刪 :1312 逐檔 INFO → 全綠。 | 採納 |
| C5-F4(F-30) | python-reviewer | 以 coroutine 名字面做否定斷言,改名後恆真 | CONFIRMED | LOW→LOW | 同案 :369 的「無日 K 來源」caplog 斷言已擋住主 mutant(worker 誤啟動時那行 INFO 不會出現),:371 屬裝飾性。 | 採納 |
| C5-F5(F-31) | python-reviewer | 手抄的政策列 fixture 沒釘到 `_POLICY_KEYS` | PARTIAL | LOW→LOW | 「自我比對」不確 —— :163 比的是回寫後的鍵序 vs 輸入鍵序,殺得掉重排 mutant;只有「未釘 `_POLICY_KEYS`」這半成立(現值恰相符)。 | PARTIAL:只採成立的那半 |
| C5-F6(F-32) | python-reviewer | 用 `asyncio.sleep(0.05)` 證「沒再跑」,負載重時可能零輪詢 | CONFIRMED | LOW→LOW | 方向是漏抓不是誤紅;既有測試風格。 | 採納 |
| C6-F1(F-33) | python-reviewer | `peers_fn` 拋例外的降級路徑(quotes={} / 當日一次 traceback / 換日復位)零測試 | CONFIRMED | MEDIUM→MEDIUM | Grep `peers_error` / `政策行情快照讀取失敗` over `tests/ copycat/` → 只命中實作 `signal_hub.py:1049`,tests 零命中;`_Watch` 只有 `groups_error` / `quotes_error`(`test_signal_hub.py:266-267`)。mutant 刪 try/except(例外炸熱路徑)或改逐 tick 印 → 全綠;姊妹旗標 `_multi_group_warned` 的當日一次有測(`test_signal_policy.py:422`)。 | 採納 |
| C6-F2(F-34) | python-reviewer | `TestPolicyQuotes` docstring 承諾 no_data,卻沒有一案打 `on_no_data` | CONFIRMED | MEDIUM→LOW | mutant 存活屬實、docstring 有承諾;但引擎層不在議定四 seam,失效路徑屬邊角。 | 採納 |
| C6-F3(F-35) | python-reviewer | `test_quoted_stock_full_snapshot` 沒 `await engine.close()` | CONFIRMED | LOW→LOW | 腳本掃出 5/193;測試衛生。 | 採納 |
| C6-F4(F-36) | python-reviewer | `_fmt` 放在兩個 class 中間,且進位邊界會印 `60.000`;參數化案缺 kind 斷言 | PARTIAL | LOW→LOW | 59.9995 仍印 59.999、59.99951 起才 60.000,屬潛在非現行;KeyError 是大聲失敗;同 PR 的 `_wait_calls` 也放檔尾。 | PARTIAL:只採成立的那半 |
| C6-F5(F-37) | python-reviewer | 三處 `type: ignore` 只因群組治具是裸 dict | CONFIRMED | LOW→LOW | repo 測試普遍容忍(test_index_engine 68 個),本檔 3 個。 | 採納 |
| C6-F6(F-38) | python-reviewer | 換日 / 移出自選歸零兩案沒斷「真的又推了一次」 | PARTIAL | LOW→LOW | notify = first_of_day 且 ≤ push_end,first_of_day 已斷;notify ↔ Discord 連動由 :485-491 釘住 → 屬加強非補洞。 | PARTIAL:只採成立的那半 |
| C6-F7(F-39) | python-reviewer | `_SEEDED_KINDS` 補了 sweep_cluster,同檔 `_RULE_PARAMS` 複製表沒補 | CONFIRMED | LOW→LOW | 目前無呼叫點,潛伏 KeyError。 | 採納 |
| C6-F8(F-40) | python-reviewer | 兩政策合併卡只驗第 0/2/3 行,第 1 行與行數沒守 | CONFIRMED | LOW→LOW | 第 1 行內容已由單政策案 :605-610 整串釘住;屬對稱補強。 | 採納 |
| C7-F1(F-41) | python-reviewer | 種子通知旗以 kind 當 key,兩張回檔卡塌成一張 | PARTIAL | MEDIUM→LOW | 塌卡屬實(7 → 6 鍵);但兩張回檔卡的 notify 由 `_pullback_seed_rule` 同一行給值,單卡 mutant 造不出來、dict 會一起翻紅。 | PARTIAL:只採成立的那半 |
| C7-F2(F-42) | python-reviewer | 整數鍵「接受整數浮點」案沒補 sweep 兩鍵,姊妹拒收案有補 | CONFIRMED | LOW→LOW | `INT_PARAM_KEYS` 是共用判定,其他 kind 已覆蓋路徑;對稱性缺口。 | 採納 |
| C7-F3(F-43) | python-reviewer | 案名說「不重複 log」,斷言是「一次都不 log」 | CONFIRMED | LOW→LOW | 純命名。 | 採納 |
| C7-F4(F-44) | python-reviewer | id 去重案的 docstring 還指 `_migrate_v2`,迴圈已搬到 `_append_seed` | CONFIRMED | LOW→LOW | `signal_rules.py:436-457` 迴圈在 `_append_seed`,`_migrate_v2:429-434` 已無;次要。 | 採納 |
| C7-F5(F-45) | python-reviewer | 遷移種子「不吃設定檔覆寫」這個分歧,測試側沒複述 | PARTIAL | LOW→LOW | 分歧已在 `signal_rules.py:421-424` 與 :485 兩處 docstring 明載,只是測試 docstring 未加註。 | PARTIAL:只採成立的那半 |
| C7-F6(F-46) | python-reviewer | `_v3_set` 只在 vol_burst 顯式寫前置條件,cdp 靠預設 | CONFIRMED | LOW→LOW | 純風格。 | 採納 |
| C7-F7(F-47) | python-reviewer | 兩個斷言沒綁同一行,失敗時看不出哪一半 | CONFIRMED | LOW→LOW | 要相當刻意的改動才逃得掉。 | 採納 |

### Step 4.3a consensus baseline check

N-A —— 本輪只有一軸,無 consensus finding。

### Step 4.3b lone-finding 判斷

全部 50 條為 lone finding。「他軸為何漏」在本輪無意義(user 停用其餘軸),不據此降級;`effective_severity` = 同軸複查的 `corrected_severity`(安全類 finding 零條,無矩陣校準)。發現總覽的排序 = 最終建議群組(Must → Should → Nice → 參考用),群內依 chunk / 原編號;severity 只在格內可見、不驅動排序。

## Action Items

**Severity calibration**:6c(移除 / 削弱既有防護類)—— 本 PR 無此類 finding。6d-1(假設性措辭 cap Should)/ 6d-3(Must 雙半條件:user-visible 重現路徑 + 不修就壞會出貨的東西)—— 50 條中沒有任何一條同時滿足:三條 MEDIUM 全是**測試覆蓋缺口**(死測試不阻擋發布),其餘是 docstring / 文件 / 測試衛生 / 小重複 / 潛伏(無 caller)路徑。Provenance cap N-A。

**校準套用**:無作者校準檔(`loger-w.md` 不存在)、本輪無套用。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

無(依 6d-3,測試覆蓋缺口與可觀測性缺口不阻擋發布;下列三條 MEDIUM 排在 Nice to Have 首位,建議影子期第一週內收)。

### Nice to Have(可選優化)

47 條(見發現總覽 F-01 … F-47)。優先三條(校正 MEDIUM):
- F-23 `tests/live/test_signal_state.py:882` —— 換日 / 移出自選的掃單簇清狀態測試:註解說的機制是假的,單欄突變全存活
- F-27 `tests/server/test_signal_outcome.py:109` —— 回填「保留行尾」那段邏輯零覆蓋:測試全 LF,prod 檔是 CRLF
- F-33 `tests/server/test_signal_policy.py:321` —— `peers_fn` 拋例外的降級路徑(quotes={} / 當日一次 traceback / 換日復位)零測試

其餘 LOW 依 action:`auto-fix`(一次收修 PR 可全吃)/ `ask-user`(F-01 術語 vs code 拍板、F-09 回填逐行 bytes 解碼策略)/ `no-op`。

### 參考用(內部複查 REFUTED / OUT_OF_SCOPE)

- F-48 `copycat/live/signal_state.py:714` —— CC 擔心「七顆 detector 都養掃單狀態 —— 但既有設計本來就每顆推進全部 kind」→ 複查:`signal_state.py:190-209` 每顆 detector 都持 `_prev/_window/_pullback/...`,`evaluate:319-323` 對所有 kind 無條件推進(docstring 692「狀態推進無條件」是刻意設計);sweep 窗 60 s 還小於 surge 的 300 s,非新量級。 → 使用者自行判斷是否採納。
- F-49 `copycat/server/signal_hub.py:1085` —— CC 擔心「兩條掃單簇規則會各出一列政策列 —— 但 spec 就是這樣訂的」→ 複查:spec #192 明訂「任一條該 kind 規則的事件都評,列上記 rule_id」+「每日計數 per (檔, 政策)」+ story 7「對帳統計本來就是同檔一筆」;第二列 notify=False 不進 Discord(`_enqueue:1128`)。 → 使用者自行判斷是否採納。
- F-50 `frontend/src/hooks/useSignalAlerts.ts:205` —— CC 擔心「quiet 列不併入 toast 文案 —— spec 就是要它完全不出現」→ 複查:spec #192 story 9「CDP 穿越、爆量停止一切推播(Discord、toast、嗶聲、桌面通知)但 rail 淡色仍列」;gate 上方註解已逐字寫明。 → 使用者自行判斷是否採納。

## 審查工具比較 (qualitative)

- CC 主軸(python-reviewer ×7 chunk):context-aware;七個 chunk 各自 per-file accounting,43/43 零漏。命中最有價值的三條(回填 CRLF 覆蓋缺口 / peers_fn 例外路徑零測試 / 掃單簇 lifecycle 測試機制為假)都需要讀實作 + 跑突變才看得出來,diff-only 軸不會抓到。
- 內部複查(code-reviewer ×2):同軸、非跨軸證據。REFUTED 率 3/50 = 6%(低於 10%)→ first-pass 命中率高;但 47/50 校正到 LOW,說明 first-pass 對 doc / 測試衛生類過度標 MEDIUM(標準軸 2.8 baseline 的推力)。三條 MEDIUM 全部以 mutant 實跑證實(171 tests 全綠 / 4 案全綠)。
- Codex / Gemini:N-A(user 停用),無重疊率可算;對抗式增益 N-A。
- React-doctor:0 新引入(1 條為 base 既有函式行號位移)。

## 沒做的部分（結案對帳）

- Codex 中性 / Codex 對抗:**N-A**(user 明示停用,per-PR override 沿 #188 / #190 前例)—— 沒有跨軸證據,Step 4.2 以同軸 code-reviewer 內部複查代替(兩批各 25 條,ID 集合精確相等)。
- Gemini Flash / Pro:**N-A**(user 明示停用);Quota 未取。
- security-reviewer:**N-A**(未觸發:PR 未動 auth / cookie / request body 解析 / 憑證 env)。
- spec-compliance-reviewer(C4):**N-A / SKIPPED**(`C4_NO_SPEC_FILE_IN_REPO`:spec 是 GitHub issue,無 repo 內 normative 檔可綁;不派、不補派)。
- Blast radius(2.9):**PASS(空輸出跳過)**。React-doctor(2.97):**PASS(未引入新問題)**。Provenance(2.55):**N-A**(base = master)。
- Author calibration:**N-A**(無校準檔)。
- 未驗證前提:C4-F3(session gate)與 C4-F2(zip strict)的「重錄會出事」是對未來 fixture 的推論,現行 fixture 已 probe 證明不受影響;C6-F4 的 `60.000` 邊界是潛在非現行(實測 59.9995 仍印 59.999)。三條皆已在複查 evidence 標明、校正 LOW。
- Step 4.5 coverage repair 輪:**未觸發**(missed 0)。Step 4.6 re-anchor:2 條 ambiguous 皆含 reviewer 自報行,無 FAILED。
- **Self-Verify(skill-verify-auditor)**:第一輪 `VERDICT: VIOLATIONS: R6, R8`。R6(absence 斷言缺查詢字串 / 工具 / 範圍)→ 已對 C2-F4 / C3-F1 / C3-F4 / C3-F5 / C6-F1(表內以 chunk 編號對照)的複查 evidence 補入實際 Grep 查詢、範圍與逐行命中;R8(修法假設未驗)→ C1-F6 `parents[4]` 深度已實跑驗證、C3-F9 `getAllByText` 節點數已對 `SignalRulesDialog.tsx:354/357` 驗證、C2-F5 改為保留未確認語式(簽名層面)。修正後**未經第二次獨立稽查**(依流程不重派 auditor)。

