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

## Spec 依據

- 此 PR 未附 spec／plan 文件,按一般 PR 流程 review。意圖來源 = PR body + `.claude/bug/breakeven-avg-source-daytrade-tax/verification.md`(/bug 六 phase 紀錄:Phase 1 紅先行、Phase 2 prod 真資料、Phase 3 四條假說、反向驗證、對帳規則)與 `code-review-round-1.json`(in-repo two-axis round 1:5 spec + 9 standards 全收修);皆為驗證 / review 紀錄、不當 spec 用。user 拍板:修法 A(`avg_source`)、今天進來的張數 0.15% / 過往 0.3% / 混合按張數分段。
- SPEC_COMPLIANCE receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED`(無 openspec/** 或 normative 文件候選)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool calls=0(無)。0 clauses / 0 findings / 0 observations / 0 invalidated。
- reducer 安全投影:本 PR 無 C4 dispatch,故無 `human_projection`;報告內 C4 finding 0、observation 0、invalidated 0,不含任何 invalidated 語意;C4 相關內容只以本 receipt 呈現,未新增獨立 review axis 欄。

## 變更概要

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `copycat/capital/models.py` | 後端 model | `AvgSource = Literal["broker","fill"]`;`Position.avg_source` / `today_qty` 兩欄 |
| `copycat/capital/store.py` | 後端 store | `_Agg.fill_date`、ctor `today` 注入、`_today_net_lots_locked` / `_with_today_qty_locked`、樂觀套用標 `fill`、`apply_profit_rows` 標 `broker`、`set_positions` 沿用 `avg_source` 並重算 `today_qty` |
| `frontend/src/types.ts` | 前端型別 | `AvgSource`、`CapitalPosition.avg_source` / `today_qty` |
| `frontend/src/lib/ladder-position.ts` | 前端純函數 | `positionEcon` 第六參數 `PositionEconInput`;`SELL_TAX_DAYTRADE`;cost 依來源;有效稅率按張數加權;`Number.isFinite` 守門 |
| `frontend/src/lib/position-summary.ts` / `components/stock/PriceLadder.tsx` | 前端 caller | 傳 `{avgSource, todayQty}` |
| `frontend/src/lib/ladder-position.test.ts` / `position-summary.test.ts` / `tests/capital/test_store.py` | 測試 | 紅先行 + review 收修測試(字面量期望、跨日 fill_date、net ≤ 0、per-kind、NaN 守門、現股空方) |
| 13 個 `frontend/src/components/**/*.test.tsx` + `lib/close-order.test.ts` | 測試 fixture | 補 `avg_source: null, today_qty: 0` |
| `CLAUDE.md` / `CONTEXT.md` / `docs/next-time.md` | docs | §4 契約條、兩則術語、4 條留尾 |
| `.claude/bug/breakeven-avg-source-daytrade-tax/{verification.md,code-review-round-1.json}` | docs(驗證 / review 紀錄) | 六 phase 證據、round 1 14 條 disposition |

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

### Opus 原始 findings (first-pass, context-aware)

- **F-01** [python-reviewer(chunk 1)] CRITICAL `copycat/capital/store.py:507-527`(anchored: exact;baseline: none)— `apply_profit_rows` 無 prod caller;真鏈 `client.py:534-564 _on_profit_complete` 就地寫 `avg_price` 不寫 `avg_source`;`set_positions` :481 沿用分支因 `avg_price` 非 None 跳過。search-proof:Grep `apply_profit_rows` → `copycat/**` 零 caller(舊 review 產物 `.claude/mod/capital-position-key-kind/change-spec-review-round-1.json:15` 亦載「prod 無 caller 屬實」);`set_positions` 唯一生產呼叫點 client.py:614。mechanism:reviewer 以 venv 實跑兩條路徑 —— prod 式 → `avg_source=None`;`apply_profit_rows` → `'broker'`。
- **F-02** [typescript-reviewer(chunk 2)] HIGH `frontend/src/lib/ladder-position.ts:89-107`(anchored: exact;baseline: Quality-4 / round 1 P2 殘餘)— switch 無 default。search-proof:`zod|valibot|superstruct` 零命中;`capital/positions` 唯一取數點 useCapital.ts:171 裸 cast;`git log -S` 兩欄同 commit d0b058ea。mechanism:node 重跑同形 switch → cost undefined → NaN;pnl-format.ts:11 只擋 null;PriceLadder.tsx:153 beTick 只擋 null。
- **F-03** [python-reviewer(chunk 1)] HIGH `CLAUDE.md:236-242`(anchored: exact;baseline: 文件一致性)— 契約條產生點 / 讀者皆指錯。search-proof:Grep `avg_source|today_qty` 前端非測試檔命中 types.ts / PriceLadder.tsx:147-148 / position-summary.ts:148-149 / ladder-position.ts 註解。
- **F-04** [python-reviewer(chunk 1)] HIGH `.claude/bug/breakeven-avg-source-daytrade-tax/verification.md:48`(anchored: exact;baseline: none)— blast radius 漏 `client._on_profit_complete`;三段證據無一經 prod 鏈。search-proof:`client.py` 不在 PR 27 檔 diff 內;Grep `avg_price` 於 client.py 命中 :560 就地寫入。
- **F-05** [python-reviewer(chunk 1)] MEDIUM `copycat/capital/store.py:173-176`(anchored: exact;baseline: none)— `fill_date` 到達日語意在重播下失效。search-proof:Grep `fill_date` 於 copycat/ 命中 :84 定義 / :176 唯一寫入 / :205,246 讀取;`CapitalStore.clear` 無 caller。mechanism:stamp 在 `_positions_seeded` 判斷之前;`a.date` 未被 `_today_net_lots_locked` 讀取。
- **F-06** [typescript-reviewer(chunk 2)] MEDIUM `tests/capital/test_store.py:813-824`(anchored: exact;baseline: 測試強度)— per-kind / fut=0 無鑑別力。search-proof:`B03R2|B04R2|B01R2` 全 tests 僅 :817 一處;store.py:204-229 逐條 continue 推演。mechanism:`_apply_fill_locked` 只重算 `(key_no, kind)` 那一列(:283 / :315),`set_positions` 才全列(:496)。
- **F-07** [typescript-reviewer(chunk 2)] MEDIUM `frontend/src/lib/position-summary.test.ts:96-125`(anchored: ambiguous → :99;baseline: 測試強度)— pass-through 無 lock。search-proof:全前端 16 個 fixture 檔皆 `avg_source: null, today_qty: 0`,無一帶 broker / today_qty > 0。
- **F-08** [typescript-reviewer(chunk 2)] MEDIUM `frontend/src/lib/ladder-position.ts:109-118`(anchored: exact;baseline: 刻意差異無鎖)— 空方不讀 `cost`。search-proof:`BROKER` 於測試檔只有 :223 / :229 兩處皆多方;`positionEcon(-` 全前端無 broker 呼叫。mechanism:本地重算空方 BROKER 與 FILL 完全同值。
- **F-09** [python-reviewer(chunk 1)] MEDIUM `copycat/capital/store.py:204-220`(anchored: ambiguous → :211;baseline: Efficiency-1 / -6)— N+1 + 無界。search-proof:`_with_today_qty_locked` 呼叫點 :283 / :315(單列)/ :496(迴圈);`clear()` 無 caller。mechanism:client.py:497-505 快照鏈至少每 60 s 一輪。
- **F-10** [python-reviewer(chunk 1)] MEDIUM `copycat/capital/models.py:158-161`(anchored: exact;baseline: Quality-8 註解)— 註解與 store docstring 互斥。search-proof:`ConnectByID` 命中 store.py:8 / models.py:159。
- **F-11** [typescript-reviewer(chunk 2)] MEDIUM `frontend/src/lib/ladder-position.test.ts:270-279`(anchored: exact;baseline: 測試強度)— 窗口組合不真實。search-proof:`git log -S` 兩欄同 commit;capital_api.py:255 asdict 全量;`avgSource: undefined` 僅此一處。
- **F-12** [python-reviewer(chunk 1)] LOW `copycat/capital/store.py:298-304`(anchored: exact;baseline: none)— `prev.qty == 0` 加權分支 source 沿用。search-proof:`qty == 0` 於 capital/ 命中 balance.py:52 / :64 / :98 過濾、store.py:295 刪列;生產端無 qty==0 列。mechanism:代入 :300-304 化簡 == fill_avg。
- **F-13** [python-reviewer(chunk 1)] LOW `copycat/capital/store.py:91-92`(anchored: exact;baseline: Reuse-2)— 重複 helper。search-proof:`%Y%m%d|strftime\(` 於 copycat/ 命中 client.py:107 / store.py:92 字面相同。
- **F-14** [python-reviewer(chunk 1)] LOW `docs/next-time.md:8-9`(anchored: exact;baseline: 文件一致性)— 留尾判準過時。search-proof:`a.date` 於 `_today_net_lots_locked` 零命中;`a.date` 讀者只有 orders() 排序(:434)與 `_price_type_of`(:385-389)。
- **F-15** [typescript-reviewer(chunk 2)] LOW `frontend/src/types.ts:106-110`(anchored: exact;baseline: Quality-8)— JSDoc 錯置。值域與後端 `models.py:26` 逐字相同。
- **F-16** [typescript-reviewer(chunk 2)] LOW `frontend/src/lib/ladder-position.test.ts:220-223`(anchored: exact;baseline: none)— 註解中間值算錯。reviewer 以 Python 獨立重算 14 顆字面期望全部相符(BE 各條與精確值差 ≤ 0.005)。
- **F-17** [python-reviewer(chunk 1)] LOW `frontend/src/components/rail/RightRail.test.tsx:76-79`(anchored: exact;baseline: 風格)— 縮排;另一處 `WatchlistSidebar.dragrender.test.tsx:52-54`。
- **F-18** [typescript-reviewer(chunk 2)] LOW `frontend/src/lib/ladder-position.ts:73-80`(anchored: exact;baseline: Quality-2 參數蔓延)— 六參數。search-proof:`positionEcon(` prod 呼叫點恰兩處,皆持完整 `CapitalPosition`。

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸皆未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC finding 可複查。

### Codex 對 Opus 的複查結果(對稱化 4.2)

**Codex 複查 Opus 失敗 —— 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(本機無 codex,batch 未起跑)。所有 CC finding 視同 INCONCLUSIVE,改由 4.3b 主 agent 判斷式複查:

| Opus # | Opus reviewer | Opus title | Verdict | 原始 → 校正 severity | Codex evidence | 備註 |
| --- | --- | --- | --- | --- | --- | --- |
| F-01 | python-reviewer(chunk 1) | `avg_source="broker"` 在 prod 永遠不會產生 | INCONCLUSIVE(4.2 N-A)→ 4.3b CONFIRMED | CRITICAL→CRITICAL | — | 主 agent 於 worktree HEAD 實跑:`grep -rn apply_profit_rows copycat/` 只命中定義;`Position(avg_price=None)` 就地設 `avg_price=469.62` 後 `set_positions` → `avg_source=None`。lone;他軸為何漏 = 全部未啟動;第一手證據 → 維持 CRITICAL。6d-3:重現 = prod 重啟後下一筆成交,券商快照落地時打平線仍跳一格、損益仍少一筆買費(user 原始症狀);不修 = 本 PR 宣稱的 runtime 修復不成立 → Must。主 agent 即 PR 作者,承認 Phase 1–6 三段證據皆走測試專用路徑。 |
| F-02 | typescript-reviewer(chunk 2) | switch 無 default → NaN | INCONCLUSIVE(4.2 N-A)→ 4.3b CONFIRMED | HIGH→HIGH | — | 主 agent 核對:TS 的 `let cost: number` 在 union 三格窮舉下視為 definitely assigned,runtime 值不在三格內即 undefined;`useCapital.ts` 裸 cast 無驗證。lone;維持 HIGH。6d-3:重現 = 新 dist 配舊後端(user 日常流程「先 build 後擇時重啟 8721」的窗口)開閃電梯 → 損益印「NaN」、打平線消失;不修 = 真錢畫面 runtime 錯值 → Must。註:與 F-01 疊加後,**現行 prod(新後端)送 null 走修前口徑而非 NaN**,NaN 只在舊後端窗口。 |
| F-03 | python-reviewer(chunk 1) | CLAUDE.md 契約條指錯 | INCONCLUSIVE(4.2 N-A) | HIGH→HIGH | — | 4.3b:主 agent 是該條作者,確認寫的是設計意圖而非 prod 實際路徑;docs 不阻擋出貨 → Should(6d-3 下半不成立);隨 F-01 一起改。 |
| F-04 | python-reviewer(chunk 1) | verification blast radius 漏欄位寫入點 | INCONCLUSIVE(4.2 N-A) | HIGH→HIGH | — | 4.3b:主 agent 承認 —— blast radius 只 grep 了 `Position(` 建構點,沒 grep `avg_price =` 寫入點;三段證據確實無一經 client 鏈。docs → Should。 |
| F-05 | python-reviewer(chunk 1) | fill_date 重播跨日 | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | 4.3b:PARTIAL —— 機制成立(stamp 在 seeded 判斷前、`a.date` 未用);觸發條件「重播與原成交不同日曆日」在現行流程(收盤後 / 盤前重啟)發生機率低,且群益 backlog 是否含前一交易日成交未實測(未驗證前提,標記)。runtime 稅率風險 → Should,不升 Must(重現路徑依賴未驗證的 backlog 日界)。 |
| F-06 | typescript-reviewer(chunk 2) | per-kind / fut=0 測試無鑑別力 | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | 4.3b:主 agent 讀 store.py 重算觸發點(:283 / :315 單列、:496 全列)確認推演成立;測試強度 → Nice。 |
| F-07 | typescript-reviewer(chunk 2) | secSummary pass-through 無 lock | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | 4.3b:全前端 fixture 皆 null/0 屬實;測試強度 → Nice。 |
| F-08 | typescript-reviewer(chunk 2) | 空方不讀 avgSource 無鎖 | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | 4.3b:刻意差異(verification 與 next-time 已記 08-27 校準),缺 characterization 屬實 → Nice。 |
| F-09 | python-reviewer(chunk 1) | N+1 掃描持鎖 | INCONCLUSIVE(4.2 N-A) | MEDIUM→LOW | — | 4.3b:PARTIAL —— 形狀成立,但現量級(數十列 × 數百單)毫秒級;效能數字為推估未量測(未驗證前提)→ 降 LOW / Nice。 |
| F-10 | python-reviewer(chunk 1) | models.py 註解矛盾 | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | 4.3b:主 agent 承認 round 1 收修時只改了 store.py docstring 沒回改 models.py;註解 → Nice。 |
| F-11 | typescript-reviewer(chunk 2) | 窗口測試組合不真實 | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | 4.3b:成立,且正是 F-02 的紅先行缺口;測試 → Nice,隨 F-02 一起改。 |
| F-12 | python-reviewer(chunk 1) | prev.qty==0 加權分支 source | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:代數成立,生產端無 qty==0 列 → Nice。 |
| F-13 | python-reviewer(chunk 1) | 重複日 helper | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:Reuse → Nice。 |
| F-14 | python-reviewer(chunk 1) | 留尾判準過時 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:主 agent 承認留尾寫於收修前未更新 → Nice。 |
| F-15 | typescript-reviewer(chunk 2) | JSDoc 錯置 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:成立 → Nice。 |
| F-16 | typescript-reviewer(chunk 2) | 註解中間值算錯 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:主 agent 重算 489500 × 0.0032565 = 1594.057,reviewer 對 → Nice。 |
| F-17 | python-reviewer(chunk 1) | fixture 縮排 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:sed 插入未對齊屬實 → Nice。 |
| F-18 | typescript-reviewer(chunk 2) | 參數蔓延 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:取捨題 → Nice / ask-user。 |

## Action Items

**display_ordinal / action_reason 對應**:canonical record 的 `F-NN` 即 `display_ordinal`(序號連續,與發現總覽及 inline block 標題一致);`action_reason` = 發現總覽「Action 理由」欄,依命令固定格式不重複進 canonical record。

**Severity calibration**:6c(移除既有防護類)本 PR 無此類 finding → 免;6d-1 hedge:F-05 觸發條件含「群益 backlog 是否含前一日」未驗證前提,已 cap Should;其餘斷言皆有實跑或 file:line;6d-3:F-01 / F-02 具體重現路徑 + runtime 錯值 → Must;F-03 / F-04 docs → Should;6d-2 由 4.3b 取代。Provenance cap N-A。未驗證前提:F-05 的 backlog 日界、F-09 的效能數字 —— 兩條皆非 Must 的支點。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix(合併前必修)

- F-01 `avg_source="broker"` 在 prod 永遠不會產生 —— 重現:prod 重啟後下一筆整股成交,券商快照落地(1–2 s)時打平線仍跳一格、損益仍比群益 APP 少一筆買費(`curl /api/capital/positions` 持倉列 `avg_source` 全 null);不修 = 本 PR 宣稱修掉的兩個 user 症狀在 runtime 原封不動 → Must。
- F-02 `avgSource` switch 無 default → NaN —— 重現:`npm run build` 後 preview 配尚未重啟的舊後端(user 日常流程的窗口)開閃電梯 → 四處印「NaN」、打平線消失;不修 = 真錢畫面 runtime 錯值 → Must(一行 `default:`)。

### Should Fix(強烈建議)

- F-03 CLAUDE.md §4 契約條產生點 / 讀者指錯(隨 F-01 一起改)
- F-04 verification blast radius 漏欄位寫入點 + 真實環境節補 payload 觀測格
- F-05 `fill_date` 到達日語意在跨日重播下失效(觸發條件依賴未驗證的 backlog 日界)

### Nice to Have(可選優化)

- F-06 per-kind / fut=0 測試補鑑別力
- F-07 `secSummary` pass-through 補 broker / today_qty > 0 案例
- F-08 空方 BROKER === FILL characterization
- F-09 `set_positions` 一次掃建當日淨張數表
- F-10 models.py `today_qty` 註解改指 `fill_date`
- F-11 窗口測試改兩欄同缺(隨 F-02)
- F-12 `prev.qty == 0` 加權分支 source = fill
- F-13 `_local_yyyymmdd` 與 `_today_ymd` 併一支
- F-14 next-time 留尾判準改寫
- F-15 `AvgSource` 搬到 `PositionKind` 旁
- F-16 註解中間值改 1594.06 / 18285.94
- F-17 兩處 fixture 縮排
- F-18 `positionEcon` 簽名收成吃 row(ask-user)

### 參考用(任一軸驗證為 REFUTED 或 OUT_OF_SCOPE)

無 —— 本輪無 REFUTED / OUT_OF_SCOPE(4.1 / 4.2 皆 N-A;4.3b 兩條 PARTIAL 未推翻)。

## 審查工具比較 (qualitative)

- Opus(CC context-aware)視角:chunk 1 reviewer 以 venv 實跑 prod 式鏈重現 F-01(全場最重、且是 in-repo two-axis round 1 與主 agent 反向驗證都沒看到的路徑 —— round 1 兩軸與主 agent 三者都只驗了 `apply_profit_rows`);chunk 2 reviewer 獨立重算 14 顆字面期望值全部相符,並以 node 重跑 switch 證實 F-02。兩支 reviewer 對「round 1 已收修」的項目逐條複核後不重報,本輪 18 條全部是 round 1 未抓到的新 finding。
- Codex 中性 / 對抗視角:N-A(本機未裝)。重疊率無法計算;4.1 分佈 N-A;4.2 分佈:INCONCLUSIVE 18 / 18(工具缺席,非 Opus over-flag 的訊號)。
- 對抗式第三軸增益:N-A。Gemini 軸增益:N-A。
- 本輪 lone finding = 18 / 18(所有他軸皆未啟動);4.3b 以主 agent 第一手證據判斷:F-01 / F-02 實跑 CONFIRMED,F-05 / F-09 因未驗證前提 PARTIAL 降半級,其餘維持。
- 流程教訓(供 harness):/bug 的 blast radius 只 grep 建構點不 grep 欄位寫入點、反向驗證只跑新測試不觀測 prod payload,三段證據同走一條測試專用路徑仍能全綠 —— 這是 F-01 漏網的結構原因,已記入 F-04 的修法。

## 沒做的部分(結案對帳)

- Codex 中性軸:FAIL / N-A —— 本機無 `codex` CLI,未起跑,零 finding;報告以 CC 軸為主。
- Codex 對抗軸:FAIL / N-A —— 同上。
- Gemini Flash 軸(永久軸):FAIL / N-A —— 本機無 `agy`,未起跑;Pro 軸未啟用亦無工具。
- Step 4.1:N-A —— 無非 CC finding。
- Step 4.2:FAIL → 全部 INCONCLUSIVE —— codex-companion batch 無法起跑;以 4.3b 主 agent 判斷式複查補位(F-01 / F-02 另以實跑 CONFIRMED),**不冒充 cross-axis 證據**。
- Step 2.9 blast radius:N-A —— 無 `sem`,空輸出跳過。
- Step 2.65 C4:SKIPPED(C4_AUTHORITY_PATH_NOT_ALLOWED);本機 `pr-review-c4.py` permit 目錄 POSIX-only。
- Step 2.96 / 2.98 提問:未問(工具缺席,無對象可設定),按預設記錄。
- Step 2.97 React-doctor:PASS(0 新增;19 檔掃描)。
- 未驗證前提:F-05 群益 ConnectByID backlog 是否含前一交易日成交(決定跨日重播是否真會發生);F-09 效能數字為推估。兩條皆已 cap 且非 Must 支點。
- 前端 chunk reviewer 無法在 review worktree 跑 tsc / vitest(無 node_modules,read-only;以 node 單檔重跑 switch 語意);自動化 gate 以 PR 分支 verification.md 為準(pytest 3106 / vitest 151 檔 / tsc / eslint / react-doctor / validate 42/42 全綠)—— 全綠與 F-01 並存,正說明 gate 沒有覆蓋 prod 鏈。
- 主 agent 利益重疊:本 PR 六個 commit 皆由本 session 的主 agent 產出,4.3b 判斷式複查由同一 agent 執行;兩支 reviewer 為獨立 fresh context,finding 本體不受此影響;主 agent 對 F-01 / F-03 / F-04 / F-10 / F-14 的「承認」為當事人自述。
- Self-Verify:auditor 輸出格式完整,`VERDICT: VIOLATIONS: R4, R5, R8`。R4 原缺口 = 缺 reducer 安全投影陳述 + header「Self-Verify」與本節互指 → 補一條安全投影陳述、header 改寫為實際結果;R5 原缺口 = 無 `display_ordinal` 字面 → canonical record 下補對應說明;R8 原缺口 = F-01「順手刪 `apply_profit_rows`」與 F-02「wire 型別改 optional 會讓 tsc 逼出分支」兩句為未經第一手驗證的斷言語式 → 改為保留語式(刪除需同步改 `test_store.py` 四處 caller;tsc 逼出分支為 TS 定性推論、未實跑)。三處皆為補寫 / 改措辭,不改 finding 結論。**未經第二次獨立稽查。**
