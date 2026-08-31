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

## Spec 依據

- 此 PR 未附 spec/plan 文件,按一般 PR 流程 review。PR body(12 筆逐條摘要 + 「零行為改動」主張)作為 intent 來源注入兩個 reviewer。
- 上游依據:`docs/superpowers/specs/2026-08-28-next-time-triage.md` §D/§E(住在 repo、非本 PR 變更檔,不觸發 spec 偵測)。
- spec 作者同人標注:N-A(未偵測到 spec)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_SPEC_DOC_IN_PR`、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、tools=0;0 clauses / 0 findings。

## 變更概要

provenance: N-A(base = master)。

| 檔案 | 類型 | 說明 |
|---|---|---|
| CLAUDE.md | docs | §4 契約條 `_TRADING_END` → 更名後文字(1 行) |
| copycat/live/tc4.py | 🔵 refactor | `HealPolicy` frozen dataclass 取代六個 `heal_*` kwargs |
| copycat/live/stock_source.py | 🔵 refactor | 改名 `in_stock_heal_window_now`/`_STOCK_HEAL_END`/`_HEAL_START` + `STOCK_HEAL` 常數 |
| copycat/live/futures_source.py | 🔵 refactor | `FUTURES_HEAL` 常數 + heal 轉發改單參數 |
| copycat/live/corr_source.py | 🔵 refactor | `CORR_HEAL` 常數 + heal 轉發改單參數 |
| copycat/server/app.py | 🔵 refactor | 四工廠改 `HealPolicy(...)` / `replace(...)` 接線 |
| tests/capital/balance_rows.py | test | 新 `balance_variant` 按欄索引 helper |
| tests/capital/test_balance.py | test | 11 處 `.replace` 猜欄位 → `balance_variant`/`pnl_variant` |
| tests/live/test_tc4.py | test | 28 呼叫點 kwargs → `heal=HealPolicy(...)` |
| tests/live/test_stock_source.py | test | 改名跟隨 + `TestStockHealWindowGate` |
| tests/live/test_corr_source.py | test | 改名跟隨 + `replace(CORR_HEAL, ...)` |
| tests/server/test_main_wiring.py | test | 10 條 kwargs 斷言改讀 `.heal` 欄位 |
| tests/server/test_stock_engine.py | test | seq 競速 gate + `TestBackfillTimeoutRetry` 純搬移 + 節標 |
| tests/server/test_ws_disconnect.py | test | caplog 斷言限定 `copycat.server.ws` logger |
| tests/live/test_river_state.py | test | 去 UTF-8 BOM |
| tests/server/test_futures_engine.py | test | 去 UTF-8 BOM |
| frontend/src/components/stock/CandleChart.test.tsx | test | 清 NUL 位元組;佔位斷言改 regex(文字面 1 行) |
| frontend/src/components/stock/WatchlistManagerDialog.test.tsx | test | 三份 gate 複本 → `makeGate()` 工廠 |
| frontend/src/hooks/useSignalAlerts.test.tsx | test | 期望值改字面量 `toastText(id)` |
| frontend/src/lib/signal-model.test.ts | test | `formatToastText` describe 刪除、單則組改直接字面量 |
| frontend/src/lib/signal-model.ts | 🔵 refactor | 刪 `formatToastText`(零 prod 讀者)+ docstring 改口 |
| docs/next-time.md | docs | D 批 14 條勾銷 + 逐條出貨註 |

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

#### #12 不是缺陷:TXO 是四個 session 裡唯一沒有具名 HEAL 常數的

**File**: `copycat/live/tc4.py`
**Line**: 175

**Comment**:
```
不是 PR 缺陷,選配一致性:STOCK_HEAL / FUTURES_HEAL / CORR_HEAL 都有名字,
TXO 的 policy 在 app.py 裡散裝組(TXO_HEAL_SILENCE_SECS 還留在 tc4.py)。
grep「*_HEAL =」想盤四個 session 門檻會少一個。要補的話:
tc4.py 加 TXO_HEAL = HealPolicy(silence_secs=TXO_HEAL_SILENCE_SECS)、app 用 replace()。
另 dataclass docstring「加欄位只動這裡 + _heal_tick 讀者」少算了 __init__ 的解構行。
```

#### #13 不是缺陷:那條 NUL 斷言修前其實也沒有真空窗

**File**: `frontend/src/components/stock/CandleChart.test.tsx`
**Line**: 222

**Comment**:
```
不是 PR 缺陷,認知校正用:對 CandleChart.tsx:519 植入 C4 突變後,
修前的含 NUL 斷言雖然恆真,下一行 /漲跌 [+-]?\d/ 照樣紅 —— 佔位洞一直有人守著。
新 regex 是好的意圖文件化,但嚴格說被 L223 涵蓋(L222 會中的 text L223 必不過)。
不用改;PR 敘事別讀成「修前這條測試有覆蓋洞」。
```

### CC 原始 findings(first-pass, context-aware)

#### python-reviewer(chunk A,15 源檔 + 2 docs)

自主驗證(worktree 內):9 檔 pytest 598 passed / 2 skipped;ruff check 全過;pyright 0。HealPolicy 值全等以「實例化每個子類與每個 app 工廠、dump 六個 `_heal_*` 屬性對照舊 kwarg 預設」逐格證明(7 組 wiring 全 match;frozen dataclass 無 mutable-default 疑慮、hash 可用;replace 不改共用常數)。class 搬移以 AST 比對 44 class:僅 TestStreamAndStatus 差異(即 gate 修改)、模組級非 class 語句 33=33 逐位元組同、順序如節標宣稱。balance_variant 11 處(10 相異)新舊字串重跑全 SAME。

1. **MEDIUM** `spikes/stock_backfill_parallel_probe.py:89` — 移除 heal_* kwargs 打斷兩個 gate 看不到的 tracked caller;實際執行兩個呼叫形狀均 `TypeError: unexpected keyword argument 'heal_silence_secs'`;ruff 只掃 copycat/tests、pyright exclude spikes;next-time 開放條「08-28 盤後 達錢並行回補實驗」正是排程呼叫。search-proof:全 repo grep heal_* kwargs → 5 hits(2 註解 + 1 刻意 docstring + 這 2 個 live call);`git ls-files` 證兩檔皆 tracked。anchor: `    src = StockQuoteSource(port=args.port, heal_silence_secs=None, heal_symbol_silence_secs=None)`
2. **LOW** `copycat/live/tc4.py:649-650` — `_heal_tick` docstring 與 `corr_config.py:42` 指名已刪 kwargs;grep 該名只會找到註解自身。anchor: `        深價外契約那種本來就沒成交的 symbol 由 \`heal_symbol_silence_secs=None\` 整條`
3. **LOW** `copycat/live/stock_source.py:519-529` — `replace(heal, active=in_trading_hours)` 靜默蓋掉 caller 的 active;改動前此錯不可表達,現在型別過、無 log 無紅燈;FuturesQuoteSource 尊重 active,兩子類語意分歧;無現行 caller(`_default_stock_source`/`_default_index_source` 都走 `in_trading_hours=`),屬 latent。anchor: `        # \`heal.active\` 一律被 \`in_trading_hours\` 蓋掉(健檢與自癒同一把閘,不另開參數)。`
4. **LOW** `tests/capital/balance_rows.py:40-47` — `balance_variant` 與 `pnl_variant` body 逐位元組同;deletion test:直接 import pnl_variant 只損失欄位提示 docstring。anchor: `def balance_variant(row: str, changes: dict[int, str]) -> str:`
5. **LOW** `copycat/live/stock_source.py:29` — stdlib import 進 first-party 分組(test_corr_source.py:6 同);futures_source.py:22-25 / app.py:355 import 清單未排序;app.py:352-355 新 `ruff format --check` 偏差(base 該檔本已 dirty,非 gate 回歸);兩行超 100 字元(E501 不在 ruff 預設集)。ruff format 對照:HEAD 會改 app.py + test_futures_engine.py、base 會改三檔 → BOM 清理讓 test_river_state 變 format-clean 屬實。anchor: `from dataclasses import replace`
6. **LOW** `tests/server/test_ws_disconnect.py:1002-1010` — scoping 本身正確(ws.py 是 `copycat/server/` 下唯一 ws* 模組、單一 module logger,SUT 輸出 100% 仍在斷言覆蓋內);但 next-time:351 勾 [x] 與「候選根因未親眼抓到」自相矛盾;複查時實際重現 `tc4.py:1188 _listen_loop` 殘留執行緒在測後拋 ModuleNotFoundError(PytestUnhandledThreadExceptionWarning)= 假說的洩漏源存在實證;其他 caplog 負向斷言未免疫。建議部分結案 + follow-up 條 + `==` 取代 `startswith`。search-proof:`ls copycat/server/ | grep -i ^ws` → 僅 ws.py。anchor: `            if r.levelno >= logging.WARNING and r.name.startswith("copycat.server.ws")`
7. **LOW** `tests/server/test_stock_engine.py:421-426` — gate 修法正確且斷言全數不動(機制 trace:stock_engine.py:1530 無條件 `apply_backfill`、stock_state.py:139 `+ max(len,1) + 1000`);但它文件化的 prod 行為(空回補純 no-op 重掛 ×N 檔)沒有對應 next-time 條。anchor: `        # 主圖入列的**空回補**照樣 \`apply_backfill\` → seq 跳增 1001(stock_state`
8. **LOW** `docs/next-time.md:351,391` — 巢狀粗體不平衡,重點句渲染反轉。anchor:(L351 全行,含六個 `**`)
9. **LOW(Nice/參考)** `copycat/live/tc4.py:175-202` — TXO 無具名 policy 常數(三缺一);docstring「加欄位只動這裡 + _heal_tick 讀者」少算 `__init__` 六行解構。呼叫端六 kwargs → 一參數的縮減是真的,非 relocate-not-reduce。anchor: `@dataclass(frozen=True)` + `class HealPolicy:`

Per-file accounting(17/17):corr_source ✓NO_ISSUES(CORR_HEAL 120/240 全等;Callable import 仍有讀者;:61 docstring 改名正確)、futures_source(import nit 併 #5;FUTURES_HEAL 值全等)、stock_source(#3、#5)、tc4(#2、#9)、app(#5 併;四工廠 runtime 驗證值全等;`_default_index_source` 正確不動)、balance_rows(#4)、test_balance ✓NO_ISSUES(11 處轉換字串全等;欄索引 [1][14][3][9][10][25] 對 19/30 欄格式全對;:358 刻意矛盾列保留原樣)、test_corr_source(#5 併;120/240 與九列邊界表不動)、test_river_state ✓NO_ISSUES(單一 BOM 移除,format 轉 clean)、test_stock_source ✓NO_ISSUES(改名 only;四端點斷言含 13:34:59/13:35:00 全在;nit:1343 行 101 字元)、test_tc4 ✓NO_ISSUES(28 處 1:1、零門檻漂移;兩個 `_src` helper 透明轉發)、test_futures_engine ✓NO_ISSUES(BOM only;`from __future__` 仍首句;format-dirty 屬 pre-existing)、test_main_wiring ✓NO_ISSUES(10 條斷言等強或更強;兩條改形處各做突變驗證仍紅)、test_stock_engine(#7;搬移 AST-pure、無 fixture 順序依賴)、test_ws_disconnect(#6)、CLAUDE.md ✓NO_ISSUES(:296 唯一 `_TRADING_END`;`_INDEX_HEAL_END` 正確不動)、docs/next-time.md(#8 + #6 的結案措辭;14 個勾銷抽驗兩條「早已做掉」的 SHA 皆為真 commit)。

chunk verdict:**Warning — mergeable with follow-ups**(零 CRITICAL/HIGH;兩大主張直驗成立;唯 MEDIUM 兩 caller 破損建議先修)。

#### typescript-reviewer(chunk B,5 檔)

自主驗證(worktree 內 npm ci 後):tsc -b 0 / eslint 0 / vitest 153 檔 2897 全綠 / react-doctor changed-scope 無本批新命中;突變測試後 worktree 還原乾淨。binary-diff 主張獨立驗證:舊 blob 37307 bytes 恰 1 個 NUL(offset 11747,L222 字串內)、新 0 NUL、CRLF 數同、去 NUL 重 diff 恰 1 行。

1. **LOW** `useSignalAlerts.test.tsx:27-37` — toastText 區塊插在 tick() doc comment 與本體間,tick() 失去附掛文件;搬到 sig() 後即歸位。anchor: `/** \`sig(id)\` 一則的 toast / 通知文案,**逐字寫死**(不再拿 \`formatToastText\` 當期望值 ——`
2. **LOW** `CandleChart.test.tsx:222-223` — 突變體雙向實證:新 regex 對 C4 突變會紅(工作正常),但同突變下修前的恆真斷言時代 L223 也會紅 → L222 被 L223 嚴格涵蓋(L222 中則 L223 必敗;反向不成立,如 `漲跌 NaN%`)。修前無覆蓋洞;新行是意圖文件化。regex 對 `fmtPct`(toFixed(2) 負值後必有數字)與 readout 尾空格渲染逐一校驗無誤警。anchor: `    expect(text).not.toMatch(/漲跌 -(?!\d)/); // 佔位 "-"(prev 缺值)不得出現;負值 "-1.23%" 不算`
3. **LOW** `WatchlistManagerDialog.test.tsx:62,70` — docstring 隔離歸因錯(收成單例 51/51 仍綠;隔離全靠 gatePuts 重設,已逐測試驗證 gate-first 順序);`let gated = []` 讓空佇列誤用的錯誤訊息變鈍。hoist 本身 byte-exact:舊 3/3/1 份複本互為逐位元組同、新工廠 body 與 old[0] 逐位元組同、N118 行內 400-resolve 與 releaseFail 字元級同;beforeEach 每測試新建 vi.fn → mockImplementation 不可能跨測試洩漏。anchor: ` *  對應 resolver 必已存在,release 不會撲空。每個 describe 各叫一次(閉包各自持 \`gated\`);`
4. **LOW** `signal-model.ts:180-181` — docstring 重排殘斷尾。anchor: ` *  另起一行放得下)。kind 段沿`

審計問題結論:formatToastText 刪除安全(全 repo grep 零活讀者;fmt/fmtPct 仍有讀者故 import 不死);10 處字面量代換逐一對號(含 `toastText("B")` 大寫屬正確非 typo);formatGroupToastText 欄位口徑 lock 由「傳遞鎖」變「兩條直接字面量」,消除共 mutant 盲點 —— 等強偏強。零斷言弱化。

Per-file accounting(5/5):CandleChart(#2)、Dialog(#3)、useSignalAlerts(#1)、signal-model.test ✓NO_ISSUES(describe 刪除正確、存活斷言等強或更強)、signal-model.ts(#4)。

chunk verdict:**Approve**(4 LOW)。

### Codex 原始 findings(first-pass, diff-only)

N-A —— codex CLI 本機未安裝,中性與對抗兩軸皆未執行(見審查軸狀態)。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可驗(Codex / Gemini 軸未執行)。

### Codex 對 Opus 的複查結果(對稱化 4.2)

Codex 不可用 → 本輪 Step 4.2 輸入 findings 無 cross-axis 證據,全數視同 INCONCLUSIVE 處理;由 main session 機械複核(第一手重現,非 subagent 自陳)部分替代:

| Opus # | 標的 | main 複核方式 | 結果 |
|---|---|---|---|
| F-01 | 兩 caller TypeError | worktree 內實際執行呼叫形狀 | CONFIRMED(`TypeError: unexpected keyword argument 'heal_silence_secs'` 重現;兩檔 grep 在案) |
| F-02 | 殘留 kwarg 名註解 | grep tc4.py:649 / corr_config.py:42 | CONFIRMED(兩處都在) |
| F-05 | 巢狀粗體 | 直讀 L351,數 `**` = 6 | CONFIRMED |
| F-08 | tick() JSDoc 被插斷 | 直讀 L26-30 | CONFIRMED(兩個連續 JSDoc 疊在 toastText 前) |
| 其餘 9 條 | — | 未另行複核 | 依 reviewer 自附之第一手證據(執行輸出 / AST 比對 / 突變體)採信;標 INCONCLUSIVE(無 cross-axis) |

### Consensus / lone-finding 處置(4.3)

- consensus 條:0(僅一個模型軸執行,無跨軸 consensus 可言;react-doctor 為機械軸且 0 命中)。
- **全部 13 條皆 lone finding**,「他軸為何漏」有統一解釋:其他軸本機未安裝、未執行 —— 非「看過同 diff 而沉默」,依 4.3b 這是最弱形式的沉默證據,不構成降級理由。各條維持 reviewer 原 severity;F-01 經 main 第一手 CONFIRMED。
- severity 未建立在未驗證前提上:唯一 Should Fix(F-01)的全部論據(TypeError、gate 盲區、排程呼叫)皆 main session 第一手驗證;其餘 Nice/參考用不受此閘約束。

## Action Items

**校準套用**:無作者校準檔(loger-w.md 不存在)、本輪無套用。

**分級說明**:F-01 為 MEDIUM(影響面 = 研究腳本與量測 harness,非 runtime/資料/build-CI → 不過 6d-3 Must 雙半條件);按 Action-Items 字面映射 MEDIUM 落 Nice to Have,此處上調至 Should Fix 並揭露理由:具體重現路徑(跑 probe 即 TypeError)+ 排程中的工作(next-time「08-28 盤後」條)必然踩中 + 零 gate 訊號 —— 「會壞但不阻擋出貨」的字面分類會讓它沉底,與其實際成本不符。無 finding 因未驗證前提被撐高(見 4.3 節末)。6c Refactor Intent Gate:本 PR 無「移除既有防護」類 finding(F-06 是「新增靜默覆蓋面」非移除防護)→ N-A。

### Must Fix(合併前必修)

無。(PR 已 merge;本輪零 CRITICAL、零 release-blocking finding。)

### Should Fix(強烈建議)

- **F-01** spikes probe + perf harness 補 `heal=HealPolicy(...)`(兩行);順帶把「改簽名 → grep spikes/ 與 .claude/」寫進 caller-map 習慣。

### Nice to Have(可選優化)

- **F-02** tc4.py:649 / corr_config.py:42 註解改指 `HealPolicy` 欄位名。
- **F-03** next-time ws 條改部分結案 + 立 TC4 listener thread 洩漏 follow-up(conftest autouse 斷言);斷言 `startswith` → `==` 選配。
- **F-04** 立 next-time 條:空回補免 seq bump(行為改動、另分支)。
- **F-05** next-time L351/L391 拆內層粗體。
- **F-06** StockQuoteSource `heal.active` 靜默覆蓋:assert / 收參數 / 補文件三選一,待拍板。
- **F-07** `balance_variant`/`pnl_variant` 收斂共用 helper,落點待拍板。
- **F-08** toastText 區塊搬到 sig() 後。
- **F-09** makeGate docstring 改寫隔離歸因;`= []` 初始化選配移除。
- **F-10** import 分組 / 排序 / app.py format 歸位。
- **F-11** signal-model.ts docstring 重排。

### 參考用(資訊性或選配)

- **F-12** TXO_HEAL 具名常數 + dataclass docstring 補 `__init__` 解構行 —— 選配一致性,非缺陷。
- **F-13** 新 regex 被 L223 涵蓋、修前無真空窗 —— 認知校正,無需改動。

## 審查工具比較(qualitative)

- 本輪僅 CC 軸(語言別雙 primary)+ react-doctor 機械軸執行;Codex / Gemini 缺席使 cross-axis 驗證退化為 main session 機械複核 —— 重疊率、REFUTED 率等跨軸統計無法計算。
- 兩個 primary 的行為與過往多軸場次的 CC 軸一致:強在 context-aware(F-01 正是「diff 之外的 caller」型,diff-only 軸原理上抓不到)與自主驗證(runtime dump、AST 比對、突變體);弱在無人踢館 —— 13 條全 lone,over-flag 校正只能靠 severity 紀律自律。
- 對抗軸缺席的估計損失:本 PR 為純測試/重構、無 trust boundary 變化,紅隊增益面窄;主要風險(值漂移、斷言弱化)已由 reviewer 用突變體/AST 自行覆蓋。
- react-doctor 機械軸:0 新命中,與 typescript-reviewer 的 changed-scope 掃描一致。

## 沒做的部分(結案對帳)

- Codex 中性軸:FAIL —— codex CLI 本機未安裝,未執行。
- Codex 對抗軸:FAIL —— 同上;preset 機制(2.98)因此未詢問。
- Gemini Flash 軸:N-A —— agy CLI 本機未安裝(永久軸在本機硬體上不可用)。
- Gemini Pro 軸:N-A —— 未安裝且未 opt-in(2.96 詢問因不可用而略過)。
- Step 4.2 Codex 驗 CC first-pass:FAIL → 以 main session 機械複核替代(4 條第一手 CONFIRMED、9 條採信 reviewer 自附證據並標 INCONCLUSIVE);此替代非對稱軸,獨立性弱於原設計,已在複查表逐條揭露。
- sem blast radius:N-A —— sem CLI 未安裝,script 空輸出跳過。
- C4 formal-spec 軸:SKIPPED(C4_NO_SPEC_DOC_IN_PR)。
- 未驗證前提:F-06 的「latent 失效」與 F-03 的「其他 caplog 斷言同險」是機制推論(有 file:line 支撐、無爆炸實例);兩條均 ≤ Nice to Have,不影響分級。
- Quota(Gemini 軸):未取 dashboard snapshot(軸未執行)。
- 其餘:無。
