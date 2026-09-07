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
## [完整證據副檔](pr-199-review.audit.md)
### finding_uid 索引
[80105386eb926f2505aa](pr-199-review.audit.md#發現總覽) · [2457ad4c976a91287766](pr-199-review.audit.md#發現總覽) · [462ab9ddd84b63fecd0e](pr-199-review.audit.md#發現總覽) · [f1a767fdc60728cfd76c](pr-199-review.audit.md#發現總覽) · [9ba7b8bc0bea2c53e384](pr-199-review.audit.md#發現總覽) · [b29dcd435d206dbda20f](pr-199-review.audit.md#發現總覽) · [c61500eb6e0f1f6c0710](pr-199-review.audit.md#發現總覽) · [6f5880b5469a5a46a015](pr-199-review.audit.md#發現總覽) · [1f6939e36c648042cc8a](pr-199-review.audit.md#發現總覽) · [b1a01a57f932404079c8](pr-199-review.audit.md#發現總覽) · [39f4d6c5320cb1b6b616](pr-199-review.audit.md#發現總覽) · [6120c42675ec5648640c](pr-199-review.audit.md#發現總覽) · [450a7476982299a67919](pr-199-review.audit.md#發現總覽) · [11a73d00307ab037a67e](pr-199-review.audit.md#發現總覽) · [852c99d92bec46d176ad](pr-199-review.audit.md#發現總覽) · [9a0567bb245d75a3965c](pr-199-review.audit.md#發現總覽) · [4d10afd74086c1d34afd](pr-199-review.audit.md#發現總覽) · [afd92e301bf7c16aff85](pr-199-review.audit.md#發現總覽) · [354ce82386b3b21654dc](pr-199-review.audit.md#發現總覽) · [d828631c21abec6c035d](pr-199-review.audit.md#發現總覽) · [7a370e172ae6139de232](pr-199-review.audit.md#發現總覽) · [bd0a62dc77ec346271af](pr-199-review.audit.md#發現總覽) · [9d90a2b4c51985d8be83](pr-199-review.audit.md#發現總覽) · [ff123a55b3bb8ce08be4](pr-199-review.audit.md#發現總覽) · [eea50f5de873e5b0d739](pr-199-review.audit.md#發現總覽) · [20edca325d0846dea500](pr-199-review.audit.md#發現總覽) · [ca8bb435dc2ce726b58d](pr-199-review.audit.md#發現總覽) · [3d46d6ee1a3bd8435ee4](pr-199-review.audit.md#發現總覽) · [31a07a1fe1e80060f577](pr-199-review.audit.md#發現總覽) · [a2c98e0ab607db10a211](pr-199-review.audit.md#發現總覽) · [13470db823d7676b5467](pr-199-review.audit.md#發現總覽) · [ccca59e6e27ca6abc47a](pr-199-review.audit.md#發現總覽) · [35ef2fb65b20617c960d](pr-199-review.audit.md#發現總覽) · [744e1fe87d183135c917](pr-199-review.audit.md#發現總覽) · [c738e3b77a78991e689e](pr-199-review.audit.md#發現總覽) · [c21dac0e24d66d01bb82](pr-199-review.audit.md#發現總覽) · [7cc66c9ac9414528ec7a](pr-199-review.audit.md#發現總覽) · [5bab11f06f7a0ef7a62d](pr-199-review.audit.md#發現總覽) · [22d8b1a2b6e3f9fd266b](pr-199-review.audit.md#發現總覽) · [f0a6802c76124e4e7480](pr-199-review.audit.md#發現總覽) · [b1f23f34aa0e05ae399b](pr-199-review.audit.md#發現總覽) · [ba3b58c1faa5aa919f6f](pr-199-review.audit.md#發現總覽) · [28357d7e38b8fd503f16](pr-199-review.audit.md#發現總覽) · [91d02f746251963890ff](pr-199-review.audit.md#發現總覽) · [59487c099c7581ef7076](pr-199-review.audit.md#發現總覽) · [bb6110b40c169d7b406f](pr-199-review.audit.md#發現總覽) · [a55bb6633f0da4f46097](pr-199-review.audit.md#發現總覽) · [943a300ddd3621048902](pr-199-review.audit.md#發現總覽) · [1d137f8f562593b00139](pr-199-review.audit.md#發現總覽) · [5de6e7fd2ff67b1a6f76](pr-199-review.audit.md#發現總覽)
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
