# PR #230 Code Review 比較報告 · SHA 8e0a2470
**Report projection schema**: 1

**PR**: [loger-w/copycat#230](https://github.com/loger-w/copycat/pull/230)
**標題**: refactor: 專案瘦身第一批 —— 刪 fade 回測家族(7,259 行)+ 盤點 A 桶死碼 + 前端 knip 清理
**作者**: loger-w
**分支**: `worktree-refactor-slim-fade` → `master`
**變更**: 100 檔案, +207 / -12,799
**審查日期**: 2026-09-14
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨;merge commit `99d57732`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `8e0a24702e6db9e60120607b68797234693efa93`;destination repo id `R_kgDOTsITBg` + baseRefOid `cda8b849486ce262d6f032e7417814e962ff205f`;`input_binding: verified` —— `git fetch origin refs/pull/230/head` 取回的 FETCH_HEAD = headRefOid 逐字相等,review worktree detached 於該 SHA,`git merge-base origin/master HEAD` = baseRefOid
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 SHA;分支已隨 `--delete-branch` 刪除,但 `refs/pull/230/head` 仍指 `8e0a2470`,產報告前重抓 headRefOid 仍為它);`base_changed=true`(origin/master 自 `cda8b849` 前進至 `99d57732`,內容 = 本 PR 自身 7 筆 rebase 後 commit,其後零新 commit);`review_context_changed=false`(審的是 PR head,與落地版逐檔等價)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用,沿 #188 / #190 / #199 / #202 / #211 / #218 / #220 / #222 / #228 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer ×6 chunk instances(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .py 佔 source diff 行 98.7%(11,117 / 11,268),chunked 派工,每 chunk ≤ 15 source 檔);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE;純讀碼 + grep + `git archive` base 實跑 `pytest --collect-only`);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=100 → covered 9 / no-issues 91 / skipped 0 / **missed 0**(chunked: **是**,88 source 檔 / 11,268 source diff 行,超過 15 檔 / 800 行門檻 → 6 chunks(26 / 16 / 15 / 15 / 15 / 13,非 source 檔亦各有 owner);100/100 per-file accounting 齊;lockfile 逐行核過故計 no-issues 非 skipped)
**定位 (ENH-B)**: anchored exact 11 / ambiguous 0 / **FAILED 0**(11 條 anchor(F-04 兩個 pin)在 worktree 逐字唯一命中:verification.md:21 / PriceLadder.tsx:44 / change-spec.md:24 / verification.md:4 與 :22 / RiverPanel.memo.test.tsx:72 / RiverPanel.memo.test.tsx:20 / trade-kinds.ts:56 / configio.py:4 / App.memo.test.tsx:49 / report_fmt.py:1;reviewer 自報行號與重定位一致或校正 1–2 行)
**React-doctor (2.97)**: 未引入新問題(既有 15 條不計、本 PR 反修掉 1 條;`npx -y react-doctor@latest . --offline --no-score --scope changed --base cda8b849 --json` 於 review worktree `frontend/` 執行(npm ci 後),`newCount 0 / fixedCount 1 / baseTotalCount 15`,changedFileCount 48、analyzedFileCount 46)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_CLAUSE)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出;`sem` 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer ×6 chunks)PASS(10 raw findings → 去重 9 + 1 重覆上報;100/100 accounting;chunk 1 另實跑 `python -m copycat --help` 對 CLI 16 個子指令)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 請求體解析 / 秘鑰讀取;package.json 只加一項 devDependency 且 lock 逐行核過)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(10/10 verdict 齊、ID 集合精確相等、每列五欄齊;另裁決兩處 chunk 間矛盾)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-230`
**worktree HEAD**: `8e0a24702e6db9e60120607b68797234693efa93`

**Report generation**: sha256:4429cc2280a10eda77677569c46b3792a5f8db64284deb1aacd334e48003708f

---
## [完整證據副檔](pr-230-review.audit.md)
### finding_uid 索引
[d00fc698e265e351214f](pr-230-review.audit.md#發現總覽) · [8a30d83de15d6cc2810b](pr-230-review.audit.md#發現總覽) · [24de5c2649291f2b5fdf](pr-230-review.audit.md#發現總覽) · [813a7c8811ca7e990e35](pr-230-review.audit.md#發現總覽) · [caf1d617a2ee09f90cb7](pr-230-review.audit.md#發現總覽) · [7d77c54afbc74a980d28](pr-230-review.audit.md#發現總覽) · [9812476a2cfdece7a398](pr-230-review.audit.md#發現總覽) · [966f1a0c99d036a7b772](pr-230-review.audit.md#發現總覽) · [00d1fae490ffc949517e](pr-230-review.audit.md#發現總覽) · [5fe3b30640580bd43c5f](pr-230-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `verification.md:21` pytest 母數對照「master 3566 → 3349;差額 217」三處皆錯:基準是 09-09 記憶值(base `cda8b849` 實測 `--collect-only` **3635**)、差額實為 **283**(25 支 fade 檔 264 + `test_cli_fade` 2 + `test_market_features` 8 + 特徵化 9)、且 217 連自己列的組成(264 + 9)都對不上;這一格正是用來證明「沒刪到不該刪的測試」的對帳 | MEDIUM | CONFIRMED(MEDIUM→MEDIUM:`git archive cda8b849` 實跑 `pytest --collect-only -q` → 3635;HEAD → 3352 = 3349 + 3 skipped 自校驗;`def test_` 計數 base 3286 / HEAD 3003 同差 283;27 個刪檔 `parametrize` 全 0 故一對一;實質未刪錯任何存活覆蓋) | Nice to Have | `auto-fix` | 三個數字改 3635 → 3352、差額 283、組成補列兩檔;零 runtime,`chore(docs)` 一筆 |
| F-02 | `PriceLadder.tsx:44` 註解「此處只剩型別 re-export(**測試** import `type TradeKind` 的既有路徑)」把正式碼消費者 `components/rail/RightRail.tsx:7` 抹掉;這是 round-1 收修 S-04 依「全 repo 零 `RightRail` 檔」這個**假前提**引入的退步(base 註解原本兩個消費者都在) | LOW | CONFIRMED(LOW→LOW:`ls frontend/src/components/rail/` 兩檔在;`sed -n 7p RightRail.tsx` 逐字 `import { PriceLadder, type TradeKind } from "@/components/stock/PriceLadder"`;chunk 3 與 chunk 5 各自獨立命中同一 file:line;chunk 2 的「不存在」無 file:line、與 S-04 同源;S-04 另半句「零外部 `TRADE_KINDS`」為真) | Nice to Have | `auto-fix` | 括號回寫「`RightRail` / 測試」;tsc 是硬攔截(照舊句刪 re-export 會 TS2305)故 LOW,但是本輪最該收的一條 |
| F-03 | `change-spec.md:24-26` 白名單逐檔列到 `test_cli_fade.py` 粒度,獨缺唯一被**修改**的測試檔 `tests/test_shared_infra_characterization.py`(12 → 3 條);鐵則 E 對刪測試最嚴,white list 是對帳基準 | MEDIUM | CONFIRMED(MEDIUM→LOW:`git diff --diff-filter=M -- tests/` 只此一檔;9 條逐一驗只碰 `quantile_round / quantile_trunc / quantiles_round / fmt_num / fmt_quantiles / load_fade_config`,零行為斷言被放棄;change-spec:19 已承諾只刪 `fmt_num / fmt_quantiles`、verification:45 已對倖存三條表態,對帳鏈覆蓋得到,「這筆沒被審」言過其實) | Nice to Have | `auto-fix` | 白名單補一列「特徵化測試移除 9 條,全為已刪符號」 |
| F-04 | `verification.md:4` 抬頭「四筆 commit … 0b435f48」已過時(0b435f48 被 §1.5 拆成 9e389873 + d850eae1;f8543dde / 8e0a2470 未列,實為 7 筆);`:22`「本批未動測試檔」為假(`App.memo.test.tsx` f8543dde 純註解、`river-test-fixtures.ts` 9e389873 一行 `export` 拿掉) | LOW | CONFIRMED(LOW→LOW:`git log --oneline cda8b849..HEAD` 7 筆;同檔 :38 已自揭拆分,讀者可對帳;兩測試檔 diff 零 `it(` / `describe(` 增刪,故「3069 → 3074 來自主線」結論仍真、只是理由句錯) | Nice to Have | `auto-fix` | 抬頭改列 7 筆;:22 改「動到的測試檔只有註解 / fixture export,母數不受影響」 |
| F-05 | `RiverPanel.memo.test.tsx:72` `vi.mock("@/components/corr/RiverOverlay")` 仍回 `{ ...actual, RiverOverlay: Wrapped, default: Wrapped }`,但本批(9e389873)已刪 `RiverOverlay` 的 `export default` → 測試替身比真模組多一個 export;該測試檔不在 diff 內(被動漂掉) | LOW | CONFIRMED(LOW→LOW:base `RiverOverlay.tsx:201` 有 `export default`、HEAD 無;唯一真實讀者 `RiverPanel.tsx:16` 具名 import;風險情境「有人寫 default import → 測試綠、tsc 紅」本身就是攔截,不會靜默出貨) | Nice to Have | `auto-fix` | 刪 `default: Wrapped` 一鍵,零行為 |
| F-06 | `RiverPanel.memo.test.tsx:20` 檔頭列「`offsetAtX` / `spreadLabelYs` / `timeTicks` / `PAD_Y` … 一律保留真身」,`river-chart-svg.ts:22` 的 `PAD_Y` 本批已降私有,不在 module 命名空間;同檔不在 diff 內 | LOW | CONFIRMED(LOW→LOW:`git show cda8b849:frontend/src/lib/river-chart-svg.ts \| grep PAD_Y` → `22:export const PAD_Y = 4`,HEAD → `const`;mock 掛的是 `@/lib/river-chart-svg` 故指涉的正是這顆(`stock-intraday-svg.ts` / `candle.ts` 同名不同物);零行為) | Nice to Have | `auto-fix` | 刪 `/ PAD_Y` 或改述「PAD_Y 已 module-private」;可與 F-05 同一筆 |
| F-07 | `trade-kinds.ts:56` `_KindDomainsMatch` 是本批唯一被保留的零 importer type export(周邊 32 條同類全降私有),但 :51-55 註解無一字說明「必須留 export,否則 `noUnusedLocals` TS6196」—— 只記在 verification.md:26;下次 knip 會再報、照本批手勢降私有 → tsc 紅(響的),或被當死碼刪 → 型別值域雙向斷言靜默消失。附帶:盤點 A6 / change-spec:27 寫 33 條 type export,實際 `-export interface` 22 + `-export type` 10(含 `{ Group, Watchlist }` 只降 1 符號)= **32**,差額 1 = 這條 | LOW | CONFIRMED(LOW→LOW:base 與 HEAD :51-56 逐字相同(註解未補);32 的算術逐行重算成立(雙符號 re-export 那行沒被騙到);TS6196 在本批實際發生過一次(verification:26)證明攔截有效) | Nice to Have | `auto-fix` | :55 註解尾補一句「`export` 不可拿掉:零 in-file 引用,降私有會 TS6196;knip 會誤報,屬已知」;change-spec:27 的 33 改 32 並記差額歸屬 |
| F-08 | `configio.py:4` docstring 把「如 fade_config 的 validate_*」改寫成「(validate_* 類)」後,repo 內一個實例都沒有(四個仍在的 loader 無一做載入後不變式檢查;grep `validate_` 只帶到 `stock_watchlist.validate_code`,那是載入**前**的字串格式檢查) | LOW | CONFIRMED(LOW→LOW:`grep -rn validate_ copycat/` 命中僅 configio:4 自身、`stock_watchlist.py:53 validate_code` 及三個 caller、`bars.py:341` 註解;句子作為職責邊界宣告仍為真、只是括號指涉落空) | Nice to Have | `auto-fix` | 刪該從句,或改「目前無 caller 這麼做(原例 fade_config 已於 2026-09-14 刪除)」 |
| F-09 | `App.memo.test.tsx:49` 改寫後仍寫「這三個模組除了元件還 re-export 別的 runtime 符號」,但 base 側 `FuturesLadder.tsx` 從無第二個 runtime export、`isFutMarket` 在 base 也零外部 importer —— 「全量 mock 會把它們一起吃掉」的災情在現有樹上從未可能發生 | LOW | PARTIAL(LOW→LOW:FuturesLadder 半邊成立(`git show cda8b849:… \| grep ^export` 只 `58:export function FuturesLadder`);但 base 原文同樣「三個模組」配兩個例子,失真早已存在;HEAD 改寫**縮小**了失真(降為歷史陳述並補「已拿掉、只剩型別」,後半句驗為真)—— 屬繼承自 baseline 的既有瑕疵,非本批引入) | Nice to Have | `ask-user` | 要不要順手把「三個」收斂成「其中兩個曾另有 runtime export」是措辭品味;本批已是改善方向,user 拍板要不要再收一次 |
| F-10 | `report_fmt.py:1-17` 模組存在理由(兩份語意不同的 `_fmt` 並存)沒了,只剩 `fmt_cell` 一函式、唯一 caller `backtest/report.py:9`(one-instance seam);chunk 2 自標「= round-1 S-08 已不修」 | LOW | OUT_OF_SCOPE(LOW→LOW:事實成立;`code-review-round-1.json` S-08 逐字同一條、disposition 明載「不修,記 next-time 候選」;change-spec:26 白名單只到 `fmt_num / fmt_quantiles`、:31 「不動」明列 `backtest/report.py` —— 重覆上報屬 review 噪音,非新資訊) | 參考用 | `no-op` | 已於 round-1 拍板不修;搬回 `report.py` 是下一批瘦身(B 桶)候選 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: d00fc698e265e351214f action=auto-fix
F-02 finding_uid: 8a30d83de15d6cc2810b action=auto-fix
F-03 finding_uid: 24de5c2649291f2b5fdf action=auto-fix
F-04 finding_uid: 813a7c8811ca7e990e35 action=auto-fix
F-05 finding_uid: caf1d617a2ee09f90cb7 action=auto-fix
F-06 finding_uid: 7d77c54afbc74a980d28 action=auto-fix
F-07 finding_uid: 9812476a2cfdece7a398 action=auto-fix
F-08 finding_uid: 966f1a0c99d036a7b772 action=auto-fix
F-09 finding_uid: 00d1fae490ffc949517e action=ask-user
F-10 finding_uid: 5fe3b30640580bd43c5f action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 pytest 母數對照的三個數字都不是 merge-base 的
**File**: `.claude/refactor/slim-fade/verification.md`
**Line**: 21

**Comment**:
```
「master 3566 → 3349;差額 217」—— 3566 是 09-09 記憶裡的數,不是 cda8b849 的。
在 base 實跑 pytest --collect-only 是 3635,HEAD 3352(= 3349 + 3 skipped),差 283。
283 = 25 支 fade 測試檔 264 + test_cli_fade 2 + test_market_features 8 + 特徵化 9。
現在這行連自己列的組成都對不上(264 + 9 ≠ 217)。這一格是用來證明「沒刪錯測試」的,
數字對不上就沒有證明力(實際沒刪錯,逐檔 import 驗過)。

改成:「cda8b849 3635 → HEAD 3352(3349 passed + 3 skipped);差額 283 = 264 + 2 + 8 + 9」。
```
#### #2 PriceLadder 註解把 RightRail 這個正式碼消費者寫掉了
**File**: `frontend/src/components/stock/PriceLadder.tsx`
**Line**: 44

**Comment**:
```
「此處只剩型別 re-export(測試 import type TradeKind 的既有路徑)」—— 不只測試在用,
components/rail/RightRail.tsx:7 就是 import { PriceLadder, type TradeKind } from 這條路徑。
這句是照 round-1 S-04「全 repo 零 RightRail 檔」改的,那個前提是假的(ls components/rail/ 就在)。
S-04 另一半「零外部 TRADE_KINDS import」倒是真的,拿掉 TRADE_KINDS re-export 沒問題。

括號改回「(RightRail / 測試 import type TradeKind 的既有路徑)」就好。
下一輪瘦身照現在這句判「只有測試在用」去收 re-export,RightRail 會紅在 tsc,不會靜默,但白跑一趟。
```
#### #3 白名單漏了唯一被改的測試檔
**File**: `.claude/refactor/slim-fade/change-spec.md`
**Line**: 24

**Comment**:
```
「刪:」清單列到 test_cli_fade.py / test_market_features.py 這種檔案粒度,
但 tests/test_shared_infra_characterization.py 從 12 條砍到 3 條沒列。
這是本批唯一「修改而非整檔刪」的測試檔,也是鐵則 E 最敏感的類別。
9 條逐一看過:quantile_round / quantile_trunc / quantiles_round / fmt_num / fmt_quantiles /
load_fade_config,全是已刪符號,零行為斷言被放棄 —— 所以是漏列不是漏審。

補一列:「tests/test_shared_infra_characterization.py 12 → 3 條(移除的 9 條全為已刪符號的特徵化)」。
```
#### #4a 抬頭 commit 清單過時
**File**: `.claude/refactor/slim-fade/verification.md`
**Line**: 4

**Comment**:
```
「四筆 commit … 0b435f48」—— 0b435f48 已經在 §1.5 拆成 9e389873 + d850eae1,
f8543dde(收修)跟 8e0a2470(artifacts)也沒列,PR head 是 7 筆。
§1.5 有揭露拆分所以讀者對得回去,但抬頭自己要改成 7 筆。
```
#### #4b 「本批未動測試檔」不是真的
**File**: `.claude/refactor/slim-fade/verification.md`
**Line**: 22

**Comment**:
```
App.memo.test.tsx(f8543dde 改註解)跟 river-test-fixtures.ts(9e389873 拿掉一個 export)都動過。
兩檔 diff 零 it( / describe( 增刪,所以「3069 → 3074 的 +5 來自主線」這個結論還是對的,只是理由句錯。
改成「動到的測試檔只有註解 / fixture 的 export 關鍵字,母數不受影響」。
```
#### #5 RiverOverlay 的 default export 拿掉了,mock 還在造一個
**File**: `frontend/src/components/corr/RiverPanel.memo.test.tsx`
**Line**: 72

**Comment**:
```
vi.mock 回 { ...actual, RiverOverlay: Wrapped, default: Wrapped } —— 這批已經把 RiverOverlay.tsx
的 export default 刪了(唯一讀者 RiverPanel.tsx:16 是具名 import),替身現在比真模組多一個 export。
有人日後寫 default import,測試綠、tsc 紅。這檔不在 PR diff 裡,是被動漂掉的。

刪掉 default: Wrapped 這一鍵就好,零行為。
```
#### #6 檔頭列的 PAD_Y 已經不是 export 了
**File**: `frontend/src/components/corr/RiverPanel.memo.test.tsx`
**Line**: 20

**Comment**:
```
「(offsetAtX / spreadLabelYs / timeTicks / PAD_Y …)一律保留真身」—— river-chart-svg.ts:22 的 PAD_Y
這批從 export const 變 const,不在 module 命名空間了(stock-intraday-svg / candle 各自有同名的另一顆,不相干)。
前三個仍 export、句子其餘成立。

把「/ PAD_Y」拿掉,或改「PAD_Y 已 module-private」。跟 #5 同檔可以一筆改。
```
#### #7 唯一留下的零 importer type export,沒寫為什麼不能降私有
**File**: `frontend/src/lib/trade-kinds.ts`
**Line**: 56

**Comment**:
```
周邊 32 條同類 type export 這批全降私有,只有 _KindDomainsMatch 留 export —— 留是對的
(降私有會撞 noUnusedLocals → TS6196,verification.md:26 記了那次紅燈),但 :51-55 的註解一個字都沒提。
下次 knip 又會報它,照這批的手勢降私有 → tsc 紅(還好是響的);更糟的是被當死碼整條刪掉 →
TradeKind ⇄ PositionKind 的雙向斷言靜默消失。

:55 註解尾補一句:「`export` 不可拿掉:零 in-file 引用,降私有會 TS6196;knip 會誤報,屬已知」。
順帶:盤點 A6 / change-spec:27 寫 33 條 type export,實際 22 interface + 10 type(其中 { Group, Watchlist } 只降 Group)= 32,差的那 1 條就是它。
```
#### #8 configio docstring 的舉例換成泛稱後,repo 裡沒有實例
**File**: `copycat/configio.py`
**Line**: 4

**Comment**:
```
「載入後的額外不變式檢查(validate_* 類)留在 caller」—— 原句舉的是 fade_config 的 validate_*,
刪掉之後四個還在的 loader(backtest / breadth / signals / strategy)沒有任何一個做載入後檢查,
grep validate_ 只會帶到 stock_watchlist.validate_code,那是載入前的股號格式檢查、不是同一件事。
句子的職責邊界宣告本身還是對的,只是括號指不到東西。

刪掉括號,或寫「目前無 caller 這麼做(原例 fade_config 已於 2026-09-14 刪除)」。
```
#### #9 partial mock 的理由還是「三個模組」,其實只有兩個曾經有多餘的 runtime export
**File**: `frontend/src/App.memo.test.tsx`
**Line**: 49

**Comment**:
```
這次改寫已經比舊版誠實(舊版還說 RightRail 直接 import TRADE_KINDS,那不成立),
但「這三個模組除了元件還 re-export 別的 runtime 符號」仍是一概而論:
FuturesLadder.tsx 在 base 就只有 export function FuturesLadder 一個 export;isFutMarket 在 base 也零外部 importer。
不是這批引入的問題(base 原文就是三個配兩個例子),要不要再收一次是措辭品味 —— 交你決定。
收的話首句改「其中兩個模組曾另有 runtime export(PriceLadder 的 TRADE_KINDS、CapitalOrdersList 的 isFutMarket)」。
```
