# PR #160 Code Review 比較報告 · SHA d1d76f10
**Report projection schema**: 1

**PR**: [loger-w/copycat#160](https://github.com/loger-w/copycat/pull/160)
**標題**: chore(tests,refactor): test-hygiene-batch-2 —— 08-28 triage D 九條 + E 三條零風險 🔵 + test_stock_engine 回補整併(12 筆,零行為改動)
**作者**: loger-w
**分支**: `chore/test-hygiene-batch-2` → `master`(已 rebase merge,merge commit a58e7ac2)
**變更**: 22 檔案, +1273 / -1193(其中 CandleChart.test.tsx 714/714 為 binary→text 呈現、實際文字面 1 行)
**審查日期**: 2026-08-31
**Review input basis**: source repo UUID `R_kgDOTsITBg` + source SHA `d1d76f10819faacd8391e7c8692b78b3d34dec6f`;destination repo UUID `R_kgDOTsITBg` + destination SHA `a49658fc5a0d910cea7b600c9e5634e2a4d35c6a`(PR fetch 當下 master tip);diff 基準 = merge-base `0b744bb85b824006a8b846272782196065447df0`;`input_binding: verified`(review worktree HEAD 逐位元組等於 source SHA)
**Review continuity**: `source_continuity=CURRENT`(PR 已 MERGED、head ref 凍結於 refs/pull/160/head);`base_changed=false`(master 現 tip = 本 PR 的 rebase merge 產物 a58e7ac2);`review_context_changed=false`
**審查工具**: CC (Fable 5)(context-aware reviewer agents)+ react-doctor 機械軸;Codex 中性 / Codex 對抗 / Gemini Flash / Gemini Pro 本機未安裝(codex / agy CLI 不存在)→ 全記 N-A;cross-axis verification 以 main session 機械複核(第一手重現 + grep)替代 Step 4.2
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=Fable 5(claude-fable-5);primary reviewers=python-reviewer(chunk A)/ typescript-reviewer(chunk B),requested=opus / observed=UNAVAILABLE(Agent 回執不含 runtime model 欄);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(未派,gate SKIPPED);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=22 → covered 13 / no-issues 9 / skipped 0 / **missed 0**(chunked: 是,20 source files > 15 檔門檻;兩 chunk 依語言分割:A 後端 15 檔+2 docs、B 前端 5 檔 —— 混語言 PR 以語言別 primary(python-reviewer / typescript-reviewer)取代 generic fallback,路由偏離已在此揭露)
**定位 (ENH-B)**: anchored exact 12 / ambiguous 1(F-04 錨文字在檔內兩處,取 reviewer 報告的 TestStreamAndStatus 那處 L424)/ **FAILED 0**
**React-doctor (2.97)**: 未引入新問題(--scope changed --base 0b744bb8 --json → diagnostics 0)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_SPEC_DOC_IN_PR —— Step 2.6 未偵測到任何 spec/plan 文件;CLAUDE.md 為專案指示、不符 spec 偵測啟發式)
**審查軸狀態**: primary python-reviewer(chunk A)PASS(findings 9、per-file accounting 17/17)/ primary typescript-reviewer(chunk B)PASS(findings 4、accounting 5/5)/ domain security-reviewer N-A(無 auth / env / request-body 面)/ Codex 中性 FAIL(codex CLI 本機未安裝)/ Codex 對抗 FAIL(同前)/ Gemini Flash N-A(agy CLI 本機未安裝)/ Gemini Pro N-A(未安裝且未 opt-in)/ cross-axis verification PARTIAL(4.1 無非 CC 軸 finding 可驗 → N-A;4.2 Codex 不可用 → main session 機械複核 4 條關鍵主張全 CONFIRMED,其餘依 reviewer 自附第一手證據)
**blast radius (2.9)**: 空輸出跳過(sem CLI 本機未安裝;script 存在但無 sem 可呼叫)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-160`
**worktree HEAD**: `d1d76f10819faacd8391e7c8692b78b3d34dec6f`

**Report generation**: sha256:2bf68e233857ec7bdced2364936755b9adb2fe6871ef09687bf82700b4770b7d

---
## [完整證據副檔](pr-160-review.audit.md)
### finding_uid 索引
[cc1e58458beabb2d1e91](pr-160-review.audit.md#發現總覽) · [939033a78e2327d300b3](pr-160-review.audit.md#發現總覽) · [01cd0861f4d7330958c2](pr-160-review.audit.md#發現總覽) · [e1f87d2a1e5d7560b651](pr-160-review.audit.md#發現總覽) · [3f0d99b9b3f29a486402](pr-160-review.audit.md#發現總覽) · [12ec04c2d9516010d49f](pr-160-review.audit.md#發現總覽) · [a4680981f299403026ac](pr-160-review.audit.md#發現總覽) · [a2cd13d14f5a62d48ad8](pr-160-review.audit.md#發現總覽) · [3bec8f80725150f91443](pr-160-review.audit.md#發現總覽) · [4bc03e0ebb49738bb790](pr-160-review.audit.md#發現總覽) · [5bac88bd6e580c35dc8f](pr-160-review.audit.md#發現總覽) · [5cc9c9499841817ca2b3](pr-160-review.audit.md#發現總覽) · [5aac3a66c7672e5b49ce](pr-160-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | 複查(main 機械複核) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| 1 | HealPolicy 簽名改動漏掉 spikes probe + perf harness 兩個 tracked caller,建構即 TypeError | MED [python-reviewer] | CONFIRMED(main 第一手重現 TypeError) | Should Fix | `auto-fix` | 兩行修法明確;排程中的盤後實驗會炸 |
| 2 | tc4.py:649 / corr_config.py:42 兩處註解仍指名已刪除的 heal_* kwargs | LOW [python-reviewer] | CONFIRMED(main grep 兩處都在) | Nice to Have | `auto-fix` | 導航註解指向不存在的名字 |
| 3 | ws_disconnect flake 結案過度宣稱:根因未親眼觀測仍勾 [x],且 reviewer 重現了 TC4 listener thread 洩漏 | LOW [python-reviewer] | CONFIRMED(reviewer 附執行證據) | Nice to Have | `auto-fix` | 改口 docs + 補 thread 洩漏 follow-up 條 |
| 4 | 空回補仍 `apply_backfill` seq +1001 → prod 純 no-op 的成交明細重掛(修法屬行為改動,本 PR 正確地沒做) | LOW [python-reviewer] | CONFIRMED(stock_state.py:139 直讀) | Nice to Have | `auto-fix` | 只補 next-time 條目,不動 code |
| 5 | next-time L351/L391 巢狀粗體不平衡,渲染後重點句反而變非粗體 | LOW [python-reviewer] | CONFIRMED(L351 六個 `**`) | Nice to Have | `auto-fix` | 拆掉內層粗體即可 |
| 6 | StockQuoteSource 接受 `heal.active` 但靜默覆蓋(FuturesQuoteSource 卻尊重它,兩子類語意不一致) | LOW [python-reviewer] | 未另驗(reviewer 附機制 trace;無現行 caller) | Nice to Have | `ask-user` | 三種修向(assert / 收參數 / 只改文件)是設計取捨 |
| 7 | `balance_variant` 與 `pnl_variant` 逐位元組重複 | LOW [python-reviewer] | 未另驗(reviewer 已 diff 證明) | Nice to Have | `ask-user` | 共用 helper 落點(rows.py / __init__)待拍板 |
| 8 | `toastText` 插進 tick() 的 JSDoc 與本體之間,tick() 失去附掛文件 | LOW [typescript-reviewer] | CONFIRMED(main 直讀 L26-30) | Nice to Have | `auto-fix` | 搬到 sig() 之後即可 |
| 9 | makeGate docstring 把隔離歸功於 per-describe 閉包,實測共用單例也全綠(隔離來自 gatePuts 重設) | LOW [typescript-reviewer] | 未另驗(reviewer 突變體實證) | Nice to Have | `auto-fix` | 改寫一句 docstring |
| 10 | stdlib import 插進 first-party 分組 ×2 + 兩個 tc4 import 清單未排序 + app.py 新增 format 偏差(gate 皆看不到) | LOW [python-reviewer] | 未另驗(reviewer 附 ruff format 對照) | Nice to Have | `auto-fix` | 純機械整理 |
| 11 | signal-model.ts docstring 重排後殘一行 15 字斷尾 | LOW [typescript-reviewer] | 未另驗(cosmetic) | Nice to Have | `auto-fix` | 重排即可 |
| 12 | 四個 session 三個有具名 HEAL 常數、TXO 沒有;dataclass docstring「加欄位只動這裡」少算 __init__ 解構行 | LOW [python-reviewer] | 未另驗(選配一致性) | 參考用 | `no-op` | 選配;拍板後另批 |
| 13 | 新 regex 斷言被下一行 `/漲跌 [+-]?\d/` 嚴格涵蓋 —— 修前也沒有真空窗(資訊性,無需改) | LOW [typescript-reviewer] | 未另驗(reviewer 雙向突變體實證) | 參考用 | `no-op` | 非缺陷;修 PR 敘事認知用 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: cc1e58458beabb2d1e91 action=auto-fix
F-02 finding_uid: 939033a78e2327d300b3 action=auto-fix
F-03 finding_uid: 01cd0861f4d7330958c2 action=auto-fix
F-04 finding_uid: e1f87d2a1e5d7560b651 action=auto-fix
F-05 finding_uid: 3f0d99b9b3f29a486402 action=auto-fix
F-06 finding_uid: 12ec04c2d9516010d49f action=ask-user
F-07 finding_uid: a4680981f299403026ac action=ask-user
F-08 finding_uid: a2cd13d14f5a62d48ad8 action=auto-fix
F-09 finding_uid: 3bec8f80725150f91443 action=auto-fix
F-10 finding_uid: 4bc03e0ebb49738bb790 action=auto-fix
F-11 finding_uid: 5bac88bd6e580c35dc8f action=auto-fix
F-12 finding_uid: 5cc9c9499841817ca2b3 action=no-op
F-13 finding_uid: 5aac3a66c7672e5b49ce action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 這兩支腳本現在一建 StockQuoteSource 就 TypeError
**File**: `spikes/stock_backfill_parallel_probe.py`
**Line**: 89

**Comment**:
```
HealPolicy 收攏把 heal_silence_secs / heal_symbol_silence_secs 從簽名拿掉了,
但這支 probe(還有 .claude/perf/opening-backfill-parallel/evidence/harness_backfill_timing.py:134)
還在傳舊 kwargs → 一建構就 TypeError。ruff 只掃 copycat tests、pyright exclude 掉 spikes,
兩道 gate 都看不到;next-time 的「08-28 盤後:達錢並行回補實驗」排程要跑的正是它。

兩行改掉就好:
src = StockQuoteSource(port=args.port, heal=HealPolicy(silence_secs=None, symbol_silence_secs=None))
harness 那支同形。之後改簽名時 caller grep 順手掃 spikes/ 跟 .claude/。
```
#### #2 兩處註解還在指名已經不存在的 kwargs
**File**: `copycat/live/tc4.py`
**Line**: 649

**Comment**:
```
_heal_tick docstring 這行寫「由 `heal_symbol_silence_secs=None` 整條豁免」,
corr_config.py:42 也還指路 `tc4.TC4QuoteSource(heal_sparse_symbols=)` ——
兩個參數這 PR 剛刪掉,照著 grep 只會找到註解自己。
改成 `HealPolicy.symbol_silence_secs=None` / `tc4.HealPolicy(sparse_symbols=)`。
```
#### #3 ws flake 的結案寫過頭了,而且洩漏源其實重現得到
**File**: `docs/next-time.md`
**Line**: 351

**Comment**:
```
勾 [x] 但同一句自己承認「候選根因未親眼抓到那則紀錄」——這是半結案不是結案。
複查時跑 8 檔後端測試,收尾真的冒出 tc4.py:1188 _listen_loop 洩漏執行緒的
PytestUnhandledThreadExceptionWarning:背景執行緒活過測試是實證,不只是假說。
這條 test 現在免疫了,但套件裡其他 caplog 負向斷言都還沒有。
建議:改成部分結案,另立一條「conftest autouse 斷言測後無殘留 _listen_loop 執行緒」。
順帶:斷言用 r.name == "copycat.server.ws" 比 startswith 準(現在沒有子 logger)。
```
#### #4 空回補的 seq +1001 在 prod 是純 no-op 重掛,值得立條追
**File**: `tests/server/test_stock_engine.py`
**Line**: 424

**Comment**:
```
這個 gate 修 flake 修得對,不動。但它文件化的機制本身值得一條 next-time:
空回補(ticks=[])也走 apply_backfill → seq +1001 → 前端 fromSnapshot 跳號規則
整片重掛 tbody —— 空回補「全數倖存、不洗 live 狀態」(apply_backfill 自己的 docstring),
重掛是純 no-op,開盤 ×N 檔各來一次。候選修法 = ticks 空且 survivors == self.ticks 時
不 bump seq(行為改動,另開分支做,不屬本 PR)。
```
#### #5 兩條出貨註的粗體巢狀爆了,重點句渲染成非粗體
**File**: `docs/next-time.md`
**Line**: 351

**Comment**:
```
L351 這行有 6 個 **:外層粗體包內層「**候選根因未親眼抓到那則紀錄**」,
markdown 解成三段交替 —— 唯一該強調的那句反而變plain。L391 的「**空回補**」同病。
拆掉內層 ** 就好。
```
#### #6 StockQuoteSource 收下 heal.active 然後靜默丟掉
**File**: `copycat/live/stock_source.py`
**Line**: 522

**Comment**:
```
replace(heal, active=in_trading_hours) 無條件蓋掉 caller 給的 active。
改 HealPolicy 之前這個錯誤根本表達不出來;現在
StockQuoteSource(heal=HealPolicy(active=my_gate)) 型別過、跑得動、閘卻不是你給的那把,
零 log 零紅燈 —— 跟 pr-126 共用閘事故同族。FuturesQuoteSource 又是尊重 active 的,
兩兄弟對同一個 HealPolicy 語意不一致。
三選一:assert heal.active is always_active(誤傳就炸)/ 收掉 in_trading_hours 參數改用
active 單一表達 / 至少 docstring 寫明會被蓋。哪個方向要拍板。
```
#### #7 balance_variant 跟 pnl_variant 是逐位元組同一份
**File**: `tests/capital/balance_rows.py`
**Line**: 40

**Comment**:
```
四行 body 跟 profit_rows.pnl_variant 一模一樣,只差 docstring。
這檔自己的模組 docstring 就在講「一份沒改到、其餘靜默留舊」的坑。
候選:抽一支共用 csv_variant,兩個名字留一行 wrapper 保住各自的欄位提示
(balance 的 [1]/[14]、pnl 的 [3]+[25] 成對規則)。落點要拍板。
```
#### #8 toastText 插斷了 tick() 的 JSDoc
**File**: `frontend/src/hooks/useSignalAlerts.test.tsx`
**Line**: 29

**Comment**:
```
新的 toastText 區塊插在 tick() 的 doc comment 跟 tick() 本體中間,
tick() hover 現在看不到自己的 fixture 契約說明(「sig() 的 code 帶 id…同 tick 案正好相反」)。
把 toastText 整塊搬到 sig() 結束後(L25 之後)就歸位,語意上它也是在描述 sig(id)。
```
#### #9 makeGate 的 docstring 把隔離歸功給錯的機制
**File**: `frontend/src/components/stock/WatchlistManagerDialog.test.tsx`
**Line**: 62

**Comment**:
```
「每個 describe 各叫一次(閉包各自持 gated)」——實測把三個呼叫點收成一個
模組級單例,51 條全綠:隔離其實全靠 gatePuts() 開頭的 gated = [],每條測試都先 gate。
docstring 改成「gatePuts() 每條測試重設佇列;三份閉包純屬防禦」比較誠實。
順帶 let gated = [] 的初始化讓「忘了 gatePuts 就 release」的錯誤訊息變鈍
(shift() 吞空、炸在 .resolve),拿掉 = [] 反而報得準。
```
#### #10 import 分組被塞亂了,而 gate 看不到這類問題
**File**: `copycat/live/stock_source.py`
**Line**: 29

**Comment**:
```
from dataclasses import replace 插在兩個 copycat import 中間(test_corr_source.py:6 同形);
futures_source / app.py 的 tc4 import 清單也沒排序;app.py:352-355 新增一處
ruff format 偏差。ruff 沒開 I 規則、E501 也不在預設集,所以全綠 —— 但這批的
賣點就是整潔,順手歸位吧。
```
#### #11 signal-model docstring 重排剩一截斷尾
**File**: `frontend/src/lib/signal-model.ts`
**Line**: 181

**Comment**:
```
「kind 段沿」單獨掛在行尾 ~15 字,上一行改完沒重排。重 flow 一下 180-183。
```
