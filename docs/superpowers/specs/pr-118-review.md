# PR #118 Code Review 比較報告 · SHA ea4cfa2b
**Report projection schema**: 1

**PR**: [loger-w/copycat#118](https://github.com/loger-w/copycat/pull/118)
**標題**: fix(capital): 部位帶 avg_source / today_qty — 打平線不跳格、損益對齊群益、當沖稅減半
**作者**: loger-w(commits 署名 Loger)
**分支**: `fix/breakeven-avg-source-daytrade-tax` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 51b93006;回溯 review)
**變更**: 27 檔案, +516 / -52
**審查日期**: 2026-08-27
**Review input basis**: source repo R_kgDOTsITBg + ea4cfa2b3b5b9fe1f16be55c2beb4fc44e13b08c;destination repo R_kgDOTsITBg + 733d772e1b57ea45b3401516fb86abf1f968e62d;`input_binding: verified`(worktree HEAD = source SHA,`git fetch refs/pull/118/head` 後 rev-parse 逐字相等;destination SHA 為 master 歷史上的既有 commit)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-118`(detached)
**worktree HEAD**: ea4cfa2b3b5b9fe1f16be55c2beb4fc44e13b08c
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer ×1(chunk 1)+ typescript-reviewer ×1(chunk 2)(依 chunk 主語言分派 —— chunk 1 py 84 / tsx 52 行,chunk 2 ts 202 / py 95 行;全 PR py 179 vs ts+tsx 254 行,ts 59% 名義上獨佔「pick exactly one」,但兩種語言在 chunk 內分離,故逐 chunk 派語言 reviewer;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=27 → covered 12 / no-issues 15 / skipped 0 / **missed 0**(chunked: 是,2 塊;FILE_COUNT=22 源檔 > 15 觸發、DIFF_LINES=494 < 800;sorted path 穩定切分:chunk 1 = 前 20 檔(15 源檔)、chunk 2 = 後 7 檔(7 源檔);union = F;covered = chunk 1 的 verification.md / CLAUDE.md / models.py / store.py / next-time.md / RightRail.test.tsx / WatchlistSidebar.dragrender.test.tsx + chunk 2 的 ladder-position.ts / ladder-position.test.ts / position-summary.test.ts / types.ts / test_store.py;no-issues = 其餘 15 檔,含 13 個 fixture 檔、PriceLadder.tsx、CONTEXT.md、code-review-round-1.json、close-order.test.ts、position-summary.ts)
**定位 (ENH-B)**: anchored exact 16 / ambiguous 2 / **FAILED 0**(全部 anchor 於 worktree HEAD 逐字比中;ambiguous 2 = F-07 `position-summary.test.ts`(:99 / :114 同句,取 reviewer 自報 96-125 內最近的 :99)與 F-09 `store.py`(`for a in self._orders.values():` :211 / :500,取 reviewer 自報 204-220 內的 :211);line 以比中結果為準)
**React-doctor (2.97)**: 未引入新問題(worktree HEAD 以 `--scope changed --base 733d772e` 掃 19 個 .ts/.tsx 檔,diagnostics 0、errorCount 0、warningCount 0;既有 0 條)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,27 檔全部 authored)
**審查軸狀態**: primary(python-reviewer chunk 1)PASS(10 findings、20/20 accounting);primary(typescript-reviewer chunk 2)PASS(8 findings、7/7 accounting);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條判斷式複查,F-01 另以 venv 實跑 prod 式鏈 CONFIRMED,見備註欄);React-doctor PASS(0 新增)
**Self-Verify**: auditor(skill-verify-auditor,model=opus)回 R1–R3 / R6 / R7 / R9 / R10 PASS、R4 / R5 / R8 FAIL;主 agent 依現有產物補寫(見「沒做的部分」),**未經第二次獨立稽查**

**Report generation**: sha256:d0ae7255f6df46915dd02f9830bb62c31cfce7e0681f213f814310c74e1ee4e1

---
## [完整證據副檔](pr-118-review.audit.md)
### finding_uid 索引
[515ff7096f824ff100e1](pr-118-review.audit.md#發現總覽) · [79dafaa4ea9140d1b252](pr-118-review.audit.md#發現總覽) · [49215a83e2e8c0624e32](pr-118-review.audit.md#發現總覽) · [a9921fbf7f8b85cff854](pr-118-review.audit.md#發現總覽) · [0359156aeaf31672ab9e](pr-118-review.audit.md#發現總覽) · [71a31acda06046f91a43](pr-118-review.audit.md#發現總覽) · [2d13fedd28e18a7b188e](pr-118-review.audit.md#發現總覽) · [ba852f7583b383476af8](pr-118-review.audit.md#發現總覽) · [24c1df1ee8eba4d5a79c](pr-118-review.audit.md#發現總覽) · [1e163bd6e464a665e795](pr-118-review.audit.md#發現總覽) · [8d7416d480261e083c4c](pr-118-review.audit.md#發現總覽) · [e0c4284fdbbb9d0ee221](pr-118-review.audit.md#發現總覽) · [58ab7c62fdca891a58f5](pr-118-review.audit.md#發現總覽) · [1ff50ab6e8df1d2d4e77](pr-118-review.audit.md#發現總覽) · [f155f87bc8f895e3ddfb](pr-118-review.audit.md#發現總覽) · [3da88875b7da915b5d20](pr-118-review.audit.md#發現總覽) · [350a6fbb5ff373a1a187](pr-118-review.audit.md#發現總覽) · [09569b9ed16805f7654d](pr-118-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | `avg_source="broker"` 在 prod 永遠不會產生:唯一寫入者 `apply_profit_rows` 無生產 caller,真鏈 `client._on_profit_complete` 就地寫 `avg_price` 不寫 `avg_source` → 打平線跳格 / 少一筆買費原封不動(`copycat/capital/store.py`) | CRIT [python-reviewer(chunk 1)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 主 agent 實跑 CONFIRMED,見備註 | Must Fix | `auto-fix` | `client.py::_on_profit_complete` 回填 `avg_price` 同區塊補 `p.avg_source = "broker"`,並在 `test_client.py` 既有鏈樣板釘 `positions()[0].avg_source == "broker"`;再擇一收斂寫入者:刪 `apply_profit_rows`(需同步改 `test_store.py` 四處 caller,未實做)或讓 client 改呼叫它 |
| F-02 | `avgSource` 的 switch 沒有 default:舊後端(兩欄同缺)payload → `cost` 未賦值 → 損益 / 打平線靜默 NaN,round 1 的守門只堵了 `today_qty` 一半(`frontend/src/lib/ladder-position.ts`) | HIGH [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Must Fix | `auto-fix` | `default:` 併入 `case null`(修前口徑),註解「缺欄退成 fill」改成真話;或 wire 型別改 `avg_source?:`(TS 定性推論:optional 會讓未賦值的 `cost` 被 tsc 擋下,未實跑) |
| F-03 | CLAUDE.md §4 新契約條兩處指錯:產生點指向無 prod caller 的 `apply_profit_rows`、「唯一讀者」指向讀不到 wire 欄名的 `positionEcon`(`CLAUDE.md`) | HIGH [python-reviewer(chunk 1)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Should Fix | `auto-fix` | 產生點改列 `client.py::_on_profit_complete`(broker)+ `store._apply_fill_locked`(fill)+ `_with_today_qty_locked`;讀者改列 `PriceLadder.tsx` / `position-summary.ts` 兩個轉接點;隨 F-01 一起改 |
| F-04 | verification 的 blast radius 漏列 `client.py::_on_profit_complete`(prod 唯一券商均價寫入點),三段證據全走測試專用路徑,無一格觀測 `/api/capital/positions` 實際 payload(`.claude/bug/breakeven-avg-source-daytrade-tax/verification.md`) | HIGH [python-reviewer(chunk 1)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Should Fix | `auto-fix` | blast radius 補「欄位寫入點」類;真實環境節加 `curl /api/capital/positions \| jq '{stock_no,avg_source,today_qty}'` 一格,持倉列 `avg_source` 必須 `"broker"` |
| F-05 | `fill_date` 是回報到達日:跨日重啟時 backlog 重播會把往日成交重新蓋成今天 → 隔夜庫存算進 `today_qty`、稅少收一半,round 1 P1 換條路徑復發(`copycat/capital/store.py`) | MED [python-reviewer(chunk 1)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Should Fix | `auto-fix` | stamp 時比對 `a.date`(委託建立日)不同日 → 不計入 today_qty + WARNING 蒐證;或 `_positions_seeded` 為 False 的重播窗口改用 `a.date` |
| F-06 | per-kind 與「fut 恆 0」兩個名目都無鑑別力:刪 `_FILL_KIND` 種類過濾或 `market != "sec"` 守門,測試照樣綠(`tests/capital/test_store.py`) | MED [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 融資成交後補一次 `set_positions` 讓 cash 列重算再斷言 0;fut 那格改用與當日成交同號的契約列 |
| F-07 | `secSummary` 新接線的 pass-through 沒有鑑別力測試:把 `p.avg_source` / `p.today_qty` 硬寫常數全套照綠(`frontend/src/lib/position-summary.test.ts`) | MED [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 加一列 `pos({avg_source:"broker", today_qty:3})` 案例,期望值字面量手算 |
| F-08 | 空方分支完全不看 `avgSource`(cost 算了不用),docstring 說刻意但無測試鎖(`frontend/src/lib/ladder-position.ts`) | MED [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 補 characterization「空方 BROKER === 空方 FILL」,08-27 空方實錄校準時改的就是這條 |
| F-09 | `_today_net_lots_locked` 每個部位重掃全部委託(N+1),`_orders` 跨日不清無界,全程持鎖(`copycat/capital/store.py`) | MED [python-reviewer(chunk 1)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | `set_positions` 一次掃建 `dict[(stock_no, kind), int]` 再餵各列;`self._today()` 一輪算一次 |
| F-10 | `today_qty` 欄註解仍寫「聚合裡的成交都是今天的」,與 store.py 收修後實作與 docstring 正面矛盾(`copycat/capital/models.py`) | MED [python-reviewer(chunk 1)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 改「來源 = 聚合中 `fill_date == 今天` 的成交(聚合跨日不清)」,權威敘述留 `_today_net_lots_locked` 一處 |
| F-11 | 「後端未重啟窗口」測試餵 `broker + 缺 today_qty`,wire 產不出這組合;真窗口(兩欄同缺)未覆蓋(`frontend/src/lib/ladder-position.test.ts`) | MED [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 改成 `{} as unknown as PositionEconInput`,F-02 修好前紅在 NaN、修好後綠 |
| F-12 | `prev.qty == 0` 走加權分支時均價實際等於純成交價,`avg_source` 卻沿用舊值(`copycat/capital/store.py`) | LOW [python-reviewer(chunk 1)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 加權分支補 `if prev.qty == 0: source = "fill"` |
| F-13 | `_local_yyyymmdd()` 與 `client.py::_today_ymd()` 逐字相同的重複 helper(`copycat/capital/store.py`) | LOW [python-reviewer(chunk 1)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 留一支、另一支 import |
| F-14 | 新增留尾描述的是收修前設計,判準 `_Agg.date` 與出貨實作對不上(`docs/next-time.md`) | LOW [python-reviewer(chunk 1)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 改寫成「到達日 == 交易日;重播跨日破功;判準 = fill_date 與 `_Agg.date` 不同日仍計入」 |
| F-15 | `AvgSource` 插在 `CapitalPosition` 的 JSDoc 與 interface 之間,說明掛錯符號(`frontend/src/types.ts`) | LOW [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 搬到 `PositionKind` 旁 |
| F-16 | 18,286 那顆字面期望的手算註解中間值算錯(1593.86 應為 1594.06;結論仍對)(`frontend/src/lib/ladder-position.test.ts`) | LOW [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 改兩個數字;群益取整那句移到 verification |
| F-17 | 兩個 fixture 新欄縮排與所在物件不對齊(`frontend/src/components/rail/RightRail.test.tsx`) | LOW [python-reviewer(chunk 1)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 兩處縮排補齊(另一處 `WatchlistSidebar.dragrender.test.tsx:54`) |
| F-18 | `positionEcon` 六參數已到上限,兩個 prod caller 都是同一列 `CapitalPosition` 拆四欄再組回(`frontend/src/lib/ladder-position.ts`) | LOW [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `ask-user` | 收成吃 `Pick<CapitalPosition,…>` 會失去測試呼叫的直白性,取捨題 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 515ff7096f824ff100e1 action=auto-fix
F-02 finding_uid: 79dafaa4ea9140d1b252 action=auto-fix
F-03 finding_uid: 49215a83e2e8c0624e32 action=auto-fix
F-04 finding_uid: a9921fbf7f8b85cff854 action=auto-fix
F-05 finding_uid: 0359156aeaf31672ab9e action=auto-fix
F-06 finding_uid: 71a31acda06046f91a43 action=auto-fix
F-07 finding_uid: 2d13fedd28e18a7b188e action=auto-fix
F-08 finding_uid: ba852f7583b383476af8 action=auto-fix
F-09 finding_uid: 24c1df1ee8eba4d5a79c action=auto-fix
F-10 finding_uid: 1e163bd6e464a665e795 action=auto-fix
F-11 finding_uid: 8d7416d480261e083c4c action=auto-fix
F-12 finding_uid: e0c4284fdbbb9d0ee221 action=auto-fix
F-13 finding_uid: 58ab7c62fdca891a58f5 action=auto-fix
F-14 finding_uid: 1ff50ab6e8df1d2d4e77 action=auto-fix
F-15 finding_uid: f155f87bc8f895e3ddfb action=auto-fix
F-16 finding_uid: 3da88875b7da915b5d20 action=auto-fix
F-17 finding_uid: 350a6fbb5ff373a1a187 action=auto-fix
F-18 finding_uid: 09569b9ed16805f7654d action=ask-user
### Inline Comments per Finding（直接複製貼到 PR review）
#### F-01 券商均價那一半在 prod 是死的,打平線跳格跟少一筆買費根本沒修到
**File**: `copycat/capital/store.py`
**Line**: 523

**Comment**:
```
`avg_source="broker"` 只在 `apply_profit_rows` 這裡寫,但這支方法在 copycat/ 底下沒有任何 caller
(全 repo 只有 tests/capital/test_store.py 在呼叫)。prod 真正的鏈是
client.py::_on_profit_complete → 直接就地 `p.avg_price = r.avg_price`(:560-563,沒碰 avg_source)
→ _finalize_positions → store.set_positions。進到 set_positions 時 avg_price 已經有值,
:481 那個「avg_price is None 才沿用」的分支整段跳過 → avg_source 停在預設 None。

實跑模擬 prod 鏈:Position(avg_price=469.62) → set_positions → avg_source=None。
前端拿到 null 走 `case null` = 修前口徑 → 損益還是少 120、打平線落地還是跳一格。
today_qty 那半是真的生效(走 set_positions),所以症狀變成「當沖減半有了、買費重複算還在」,更難認。

最小修:_on_profit_complete 回填 avg_price 那個區塊同時 `p.avg_source = "broker"`;
然後把寫入者收成一個:刪 apply_profit_rows(test_store.py 四處 caller 要一起改)或讓 client 改呼叫它 —— 兩條路都沒實做,擇一。
回歸測試釘在真 seam:tests/capital/test_client.py 已有 _on_balance_complete / _on_profit_complete /
_finalize_positions 的驅動樣板(:1525 / :1650 / :1913),補一條「跑完整條鏈後
store.positions()[0].avg_source == 'broker'」。現在那條 test_profit_rows_mark_avg_source_broker
測的是 prod 走不到的方法,就是這次漏網的原因。
```
#### F-02 avgSource 的 switch 沒 default,舊後端 payload 會把損益印成 NaN
**File**: `frontend/src/lib/ladder-position.ts`
**Line**: 99

**Comment**:
```
switch 只有 "broker" / "fill" / null 三格。值來自 useCapital.ts:171 的裸 fetchJson<T> cast,
沒有 runtime 驗證 —— 舊後端(avg_source 跟 today_qty 同一個 commit 加的,兩欄一起缺)給的是
undefined,三格全不中,`let cost: number` 沒被賦值 → `cost / (1 − f − t)` 跟 `(p − cost)·q` 全 NaN。
pnlText 只擋 null,Math.round(NaN) 不是 null → 閃電梯 / 側欄 chip / header / 群組卡四處印「NaN」,
snapBreakEven(NaN) 讓打平線整條消失。round 1 P2 的 Number.isFinite 只守了 today_qty 那半。
:89-90 註解「與 avg_source 缺欄退成 fill 同一個方向」現在是假話。

補 `default:` 併進 `case null` 那格(cost = avg × (1 + f),來源未知走修前口徑),註解改成真話。
或者 types.ts 把 wire 型別寫成 `avg_source?: AvgSource | null`—— 照 TS 的 definite-assignment 規則應會讓沒賦值的 cost 被 tsc 擋下(未實跑,先當方向)。
```
#### F-03 CLAUDE.md 新契約條指的產生點跟讀者都是錯的地方
**File**: `CLAUDE.md`
**Line**: 237

**Comment**:
```
「產生點 store.py(… apply_profit_rows = broker)」—— apply_profit_rows 在 prod 沒 caller,
broker 這半的產生點實際不存在;真正寫券商均價的是 client.py::_on_profit_complete。
「唯一讀者 ladder-position.ts::positionEcon」—— positionEcon 收的是 {avgSource, todayQty},
看不到 avg_source / today_qty 這兩個 wire 欄名;真正讀 wire 欄的是 PriceLadder.tsx:147-148 跟
position-summary.ts:148-149。契約條的用途是「下次改這條要去改哪」,指錯檔下一輪就再漏一次。

產生點改列 client.py::_on_profit_complete(broker)+ store._apply_fill_locked(fill)+
store._with_today_qty_locked(today_qty);讀者改列 PriceLadder.tsx / position-summary.ts 兩個轉接點,
positionEcon 標「口徑收斂處」。跟 F-01 一起改。
```
#### F-04 verification 的 blast radius 漏掉 prod 唯一寫均價的地方,三段證據都沒走過真鏈
**File**: `.claude/bug/breakeven-avg-source-daytrade-tax/verification.md`
**Line**: 48

**Comment**:
```
blast radius 列的是 Position「建構點」(balance.py / 樂觀套用 / apply_profit_rows),
但「欄位寫入點」不是同一組:client.py::_on_profit_complete(:560-563)才是 prod 把券商均價寫進部位的地方,
它不在清單裡,所以 avg_source 沒補上去(= F-01)。
Phase 1 紅先行、Phase 2 手算、反向驗證三段跑的全是 apply_profit_rows / positionEcon,
沒有一格觀測 /api/capital/positions 的實際 payload —— 那正是唯一能戳破 F-01 的觀測。

補兩件事:blast radius 加「欄位寫入點」一類(grep `\.avg_price\s*=` / `avg_price=` 全 copycat/capital/);
真實環境節加一格可機械檢查的證據 ——
curl -s localhost:8721/api/capital/positions | jq '.positions[] | {stock_no, avg_source, today_qty}'
持倉且損益試算回得來時 avg_source 必須是 "broker";現況跑這行會全是 null。
```
#### F-05 fill_date 記的是到達日,跨日重啟重播會把昨天的成交蓋成今天
**File**: `copycat/capital/store.py`
**Line**: 176

**Comment**:
```
D 分支無條件 `a.fill_date = self._today()`,記的是這則回報進 handler 的本機日。即時推送下 = 交易日,
重播下不是:模組 docstring 說重啟靠 ConnectByID 當日 backlog 重播重建。只要重播跟原成交不同日曆日
(跨午夜重啟、或以後補自動重連時跨日重連),那批往日成交會被戳成今天 → 隔夜庫存算進 today_qty →
稅減半、打平線偏低,零錯誤訊號。這就是 round 1 P1 想根治的樣態,換條路進來。
而且 stamp 在 `_positions_seeded` 判斷之前,重播期間照樣 stamp。

把「到達日 == 交易日」寫成明示不變量並加機械檢查:stamp 時比對 a.date(委託建立日),
不同日就不計入 today_qty 並印一行 WARNING 蒐證;或重播窗口(_positions_seeded 為 False)改用 a.date。
```
#### F-06 per-kind 跟「fut 恆 0」那條測試拿掉守門也照綠
**File**: `tests/capital/test_store.py`
**Line**: 820

**Comment**:
```
cash 列的 today_qty 是 :816 set_positions 當下算的(零委託 → 0),之後那筆 B03R2 融資成交只重算 margin 列,
cash 列沒被重算過 → 把 store.py:216-217 的 _FILL_KIND 種類過濾整段刪掉,margin 仍 1、cash 仍舊值 0,全綠。
fut 那格:_today_net_lots_locked 第一道就是 `a.stock_no != stock_no`,fut 列是 QEFF6、當日唯一委託是 4989
→ 拿掉 `p.market != "sec"` 守門 net 仍 0,也全綠。

融資成交後補一次 set_positions([Position(sec, 4989, qty=2)]) 讓 cash 列重算再斷言 0;
fut 那格改用與當日有成交的證券同號的契約列,或直接對 _with_today_qty_locked 單測 market 守門。
```
#### F-07 secSummary 那三行接線沒有測試在守,硬寫常數全套照綠
**File**: `frontend/src/lib/position-summary.test.ts`
**Line**: 99

**Comment**:
```
本檔 pos() fixture 是 avg_source: null / today_qty: 0,期望值卻傳 { avgSource: "fill", todayQty: 0 }——
null 跟 fill 在 positionEcon 是同一格,所以剛好綠,但證明不了 position-summary.ts:147-150
真的把該列的 avg_source / today_qty 傳下去。把那兩行改成硬寫 { avgSource: "fill", todayQty: 0 },
四條 SC-5 跟全庫其他測試全部照綠(16 個 fixture 檔沒有一處帶 "broker" 或 today_qty > 0)。
漂掉的症狀 = 側欄 chip / header / 群組卡的損益跟閃電梯不一致、當沖減半在這三處靜默消失。

加一列 pos({ avg_source: "broker", today_qty: 3 }) 的案例,期望值字面量手算;
既有案例的 fixture 跟期望輸入同源(fixture 是 null 就傳 avgSource: null)。
```
#### F-08 空方完全不看 avgSource,說是刻意的但沒東西鎖著
**File**: `frontend/src/lib/ladder-position.ts`
**Line**: 109

**Comment**:
```
cost 只有多方在用;空方 BE 跟 pnl 直接吃裸 avg。docstring :68「空方均價語意無真樣本,沿舊式當純價」
寫得誠實,但沒有測試釘「空方 BROKER === 空方 FILL」—— 以後有人把空方也接上 cost(看起來像顯而易見的一致性修正)
不會有任何測試紅,而那會直接動真錢畫面的空方打平線。專案對「刻意的兩邊不一樣」一律留鎖(§4 parity fixture)。

補一條 characterization:
expect(positionEcon(-2, 100, 98_000, 1.8, "cash", BROKER)).toEqual(positionEcon(-2, 100, 98_000, 1.8, "cash", FILL))
it 名寫「08-27 空方實錄校準前刻意忽略來源」;校準時要改的就是這條。
```
#### F-09 每個部位重掃一次全部委託,而 _orders 跨日不清
**File**: `copycat/capital/store.py`
**Line**: 211

**Comment**:
```
set_positions 對每列呼叫 _with_today_qty_locked → _today_net_lots_locked,後者每次整掃 self._orders
並重跑一次 self._today()。一輪快照 = O(部位數 × 委託數),_orders 是跨日不清的(clear() 全 repo 無 caller),
整段在 with self._lock 裡,同時擋住 positions() / orders() 兩支 REST。現在量級只是幾毫秒,
但會隨「連跑幾週不重啟」線性惡化,症狀是 REST/WS 偶發卡頓、無錯誤訊號。

set_positions 先一次掃建 dict[(stock_no, kind), int],再餵給每列;self._today() 一輪算一次。
_apply_fill_locked 那條(單列)維持現況即可。
```
#### F-10 models.py 的 today_qty 註解跟 store.py 說的正好相反
**File**: `copycat/capital/models.py`
**Line**: 160

**Comment**:
```
這裡寫「ConnectByID 只重播當日 backlog,所以聚合裡的成交都是今天的」,
store.py::_today_net_lots_locked 的 docstring 明說相反:「也不能假設聚合只有當日 —— prod 8721 跨日長跑、
_orders 沒有 caller 會清(review P1)」,並改成逐筆比 fill_date。讀 models.py 的人會把 fill_date 過濾當贅碼刪掉,
那正是 round 1 P1 修掉的 bug。

改寫成「來源 = 委託聚合中 fill_date == 今天的成交(聚合本身跨日不清,不可假設只有當日)」,
權威敘述留 _today_net_lots_locked 一處、這裡只指過去。
```
#### F-11 「後端未重啟窗口」測試餵的組合 wire 上產不出來
**File**: `frontend/src/lib/ladder-position.test.ts`
**Line**: 272

**Comment**:
```
舊後端的 Position 同時沒有 avg_source 跟 today_qty(兩欄同一 commit d0b058ea 加的),
序列化是 capital_api.py:255 的 asdict 全量帶欄 —— 窗口 payload 是兩欄都缺,不是「broker + 缺 today_qty」。
這條鎖住了一個真環境不存在的組合,真正的窗口(avgSource 也 undefined)落在 F-02 的 NaN 缺口裡,
測試對它沉默。`as unknown as { avgSource: "broker"; todayQty: number }` 也手抄了一份 shape。

改成 `{} as unknown as PositionEconInput`(兩欄皆缺),期望值照字面量 —— F-02 修好前紅在 NaN、修好後綠。
```
#### F-12 prev.qty == 0 走加權分支時均價其實是純成交價,source 卻沿用舊值
**File**: `copycat/capital/store.py`
**Line**: 299

**Comment**:
```
加權條件 `prev.qty == 0 or (prev.qty > 0) == (signed > 0)`:prev.qty == 0 時分子退化成 fill_avg × |signed|、
分母 |signed|,結果就是純成交價;但 source 仍是 :298 取的 prev.avg_source,若舊值是 "broker" 就把純價標成含買費 →
前端少加一次買費。翻倉分支(:311-312)同一情境是明確標 "fill" 的。
實務上幾乎打不到(balance.py 兩支 parser 都濾掉 0 張),所以 LOW。

加權分支補 `if prev.qty == 0: source = "fill"`,讓「均價是這張單的」跟 source = fill 永遠綁一起。
```
#### F-13 `_local_yyyymmdd()` 跟 client.py 的 `_today_ymd()` 一模一樣
**File**: `copycat/capital/store.py`
**Line**: 91

**Comment**:
```
函式體 `return time.strftime("%Y%m%d")` 跟 client.py:103-107 的 _today_ymd() 逐字相同,
連「抽成 module 函式讓測試注入固定值」的理由都同一個。以後要把「本機日」換成交易日語意
(client.py 已有 _trade_ymd 走 TradingCalendar)要記得改兩處。留一支、另一支 import 過去。
```
#### F-14 新加的留尾寫的是收修前的設計,判準指向不存在的機制
**File**: `docs/next-time.md`
**Line**: 8

**Comment**:
```
「today_qty 依賴『聚合只有當日 backlog』… 判準 = _Agg.date 非今日仍被計入」——
出貨的實作已經不依賴那個前提(round 1 P1 改成逐筆比 _Agg.fill_date == today),
_Agg.date 從頭到尾沒參與 _today_net_lots_locked 的判斷,照這條去 grep 會查到不存在的機制;
真正的殘餘風險(F-05:重播把往日成交蓋成今天的到達日)反而沒記。

改寫成「today_qty 依賴『成交回報到達日 == 交易日』;backlog 重播跨日時破功。
判準 = 重播期間 stamp 的 fill_date 與 _Agg.date 不同日仍被計入」。
```
#### F-15 AvgSource 插在 CapitalPosition 的 JSDoc 跟 interface 中間
**File**: `frontend/src/types.ts`
**Line**: 108

**Comment**:
```
`/** Position asdict(…) */` 跟 `/** 後端 AvgSource 同字彙 */` 兩個 JSDoc 疊在 AvgSource 上,
CapitalPosition 從此沒有說明,而「Position asdict」那句掛在一個字串聯集上。
把 AvgSource 連註解搬到 PositionKind(:103-104)旁邊,兩者都是值域型別。
```
#### F-16 18,286 那顆期望值的手算註解中間值算錯(答案沒錯)
**File**: `frontend/src/lib/ladder-position.test.ts`
**Line**: 221

**Comment**:
```
489.5 × 1000 × (0.0002565 + 0.003) = 1594.05675,不是 1593.86;pnl = 19880 − 1594.06 = 18285.94,不是 18286.1。
四捨五入後仍是 18_286,toBe 沒錯,但註解是這顆字面值的唯一佐證,差 0.2 元會讓下一個核對的人先懷疑錯的那邊。
改兩個數字;「群益 18,285 是用未四捨五入的 469.6204 算的」那句是 vendor 取整口徑,移到 verification.md 去。
```
#### F-17 兩個 fixture 新欄縮排沒對齊
**File**: `frontend/src/components/rail/RightRail.test.tsx`
**Line**: 78

**Comment**:
```
`avg_source: null, today_qty: 0, code: null, ...over,` 用 8 空格,同一物件其餘欄位是 4 空格;
WatchlistSidebar.dragrender.test.tsx:54 同樣(8 vs 鄰行 16)。其餘 10 個 fixture 檔都對齊,
這兩處是機械插入沒收乾淨。專案沒 prettier gate 所以不會被擋。補齊到同層。
```
#### F-18 positionEcon 六個參數,兩個 prod caller 都是同一列拆四欄再組回
**File**: `frontend/src/lib/ladder-position.ts`
**Line**: 79

**Comment**:
```
qty / avgPrice / kind / input 四項在 PriceLadder.tsx:146 跟 position-summary.ts:147 都來自同一列 CapitalPosition;
這輪為了加兩欄改了約 40 個呼叫點(含 16 檔 fixture)。
若收成 positionEcon(row: Pick<CapitalPosition, "qty"|"avg_price"|"kind"|"avg_source"|"today_qty">, lastMilli, discount),
下次加欄只動產生點跟 fixture,F-07 那種「fixture 與期望輸入不同源」在結構上也不可能。

參考用不是 must:純量簽名讓本檔手算測試讀起來直白,取捨明擺著。要不要收,你決定。
```
