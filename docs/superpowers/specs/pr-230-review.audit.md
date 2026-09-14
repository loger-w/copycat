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

## Spec 依據

- 偵測到 spec 檔:`.claude/refactor/slim-fade/change-spec.md`(路徑在 `.claude/refactor/` 且檔名 `*-spec.md`;內容 = why gate 三段 / 「行為不變承諾」5 條 / 「範圍(白名單)」刪與不動兩列 / 「不在本批」)。另一份依據 = `docs/research/2026-09-14-dead-code-inventory.md`(唯讀盤點,§3A A1–A8、§3B B1 為本批範圍來源)。同 PR 內另有 two-axis round-1(`code-review-round-1.json`,Standards 10 + Spec 8,收修於 f8543dde;S-06 / S-08 / S-09 / P-04 標不修)—— 本輪不重報已修條,只報處置不完整處、收修引入的退步或新事實。
- **⚠️ spec 作者 = PR 作者**(`git log --format='%an' -- .claude/refactor/slim-fade/change-spec.md` = Loger = PR 作者 loger-w;本輪 F-10 的「參考用」判定引 change-spec:26 / :31 白名單論證範圍 —— 該白名單同時被 F-03 指出**漏列**了刪測試這一項,利益重疊方向是「白名單比實作小」,正是 reviewer 該補的洞,本輪已補(F-03)而非以 spec 免罪)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_NORMATIVE_CLAUSE`(change-spec.md 全文 grep `MUST|SHALL|NEVER|必須|不得|恆` —— 唯一命中「D1 **不可刪**」在「不在本批」段,是對另案的限制、非本 PR 實作契約;「行為不變承諾」五條是流程層承諾、由 Spec 軸與本輪逐字比對承接,非可綁 `path:line` 的實作契約)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool calls=N-A(未派);0 clauses / 0 findings / 0 observations / 0 invalidated。reducer 安全投影要求:未派故無 `human_projection`;本報告零 C4 內容,`invalidated_ids ∩ report_finding_ids = ∅`(兩集合皆空),無 invalidated 語意外洩,C4 對 Step 4.5 覆蓋零貢獻。
- Author calibration(Step 2.2):無作者校準檔(`loger-w.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

provenance: N-A(base = master)。七筆 commit 全屬 🔵 純刪除 / 🔵 文件 / chore(依賴列名),`copycat/server/**` 零 diff。

| 群 | 檔案 | 變更類型 | 說明 |
|---|---|---|---|
| fade 家族模組 | `copycat/backtest/fade_{anatomy,arms,cells,config,diagnose,entry_anatomy,features,optimize,pipeline,report,simulate,tp,vote}.py`、`market_features.py`、`quantiles.py`(15) | D | 2026-07 T+1 空方當沖研究,五輪已了結;`market_features` 唯一 caller 是 `fade_pipeline`(且 `mkt_daily_rows` 恆 None);`quantiles` 刪後零 runtime caller |
| fade configs | `configs/fade_uc_round{1,2,3,4,4_sens_tp,5}.json`(6) | D | `FadeBacktestConfig` 欄位,零 runtime 引用 |
| fade 測試 | `tests/backtest/test_fade_*.py`(21)、`tests/test_fade_{features,simulate,tp,trigger}.py`(4)、`tests/test_cli_fade.py`、`tests/test_market_features.py`(共 27) | D | 斷言主詞全為已刪符號;非 fade import 僅 `Bar1K` / `write_bars` / `tick_size` / `DailyIndex` 造資料 helper,各有自己的測試 |
| 後端留改 | `copycat/cli.py`(−114:五個 `fade-*` parser + dispatch)、`copycat/backtest/report_fmt.py`(只留 `fmt_cell`)、`copycat/configio.py`(docstring)、`copycat/live/aggregate.py`(−`last_cum`)、`copycat/engine/lock_quality.py`(−`current_lock_start`)、`tests/test_shared_infra_characterization.py`(12 → 3 條) | M | 承諾 2 / 3 / 4 逐條驗證成立(見內部複查) |
| 前端 knip | 44 檔(`frontend/src/**`):33 `export` → 私有、32 type export → 私有、9 個未使用 `export default` 移除、`PriceLadder` 的 `TRADE_KINDS` re-export 移除、`useStockWatchlist` 撤 `Group` re-export;`_KindDomainsMatch` 恢復 export | M | 全部同檔仍用、零跨檔 import(六 chunk 逐符號 grep);後端直讀前端原始碼的 parity 測試不碰任何一個 |
| 依賴 | `frontend/package.json` / `package-lock.json` | M | `@eslint/js` 補列 devDependencies `^9.39.5`;lock 只加 1 行宣告、`packages` 區零變動(獨立 chore commit d850eae1) |
| 文件 / skill | `.claude/skills/tc4-market-facts/SKILL.md`(2 條路徑改述)、`.claude/skills/backend-conventions/SKILL.md`(1 條) | M | 教訓語意保留、指向的存活路徑 `backtest/pipeline.py::_TRADEABLE` 實存且是唯一一份 |
| artifact | `.claude/refactor/slim-fade/{change-spec.md,verification.md,code-review-round-1.json}` | A | 本輪三條 finding 落在前兩檔的算術 / 陳述層 |

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

#### #10 report_fmt 只剩一個函式一個 caller —— round-1 已經拍板不動,這裡只是再提

**File**: `copycat/backtest/report_fmt.py`
**Line**: 1

**Comment**:
```
不是 PR 缺陷,round-1 S-08 逐字同一條、已拍板「不修,記 next-time」;change-spec 白名單也只到 fmt_num / fmt_quantiles、
「不動」清單明列 backtest/report.py。事實沒錯(整檔 = docstring + fmt_cell,唯一 caller report.py:9),
搬回 report.py 輸出逐字不變,但那是下一批瘦身(B 桶)的事,不在這個 PR 動。
```

## CC 主軸原始 findings(first-pass, context-aware)

python-reviewer ×6 chunks(requested=opus),逐字要點;reviewer 原編號 → 發現總覽:R-01(chunk1)→F-01、R-02(chunk1)→F-03、R-03(chunk1)→F-04、R-04(chunk2)→F-05、R-05(chunk2)→F-08、R-06(chunk2)→F-10、R-07(chunk2)→F-09、R-08(chunk3)+R-10(chunk5,同條)→F-02、R-09(chunk4)→F-06、R-11(chunk5)→F-07。chunk 6 零 finding。

#### R-01 [MEDIUM] .claude/refactor/slim-fade/verification.md:21 — pytest 母數對照的差額算錯,基準用的是 09-09 記憶數而非 merge-base
問題:HEAD 端 3352(3349 + 3 skipped)相符,但差額 217 對不上。實刪 274 條(25 支 test_fade_* = 264、test_cli_fade = 2、test_market_features = 8)+ 特徵化 9 條 = 283;無任何被刪檔用 parametrize。故 cda8b849 實為 3635 collected,「3566」是 09-09 記憶值(其後 #225/#226/#227 六筆 commit 都動過 tests/)。公式另漏列兩檔。search-proof:`pytest --collect-only -q`(HEAD)→ 3352;`git grep -cE "^\s*(async )?def test_" cda8b849/HEAD -- tests/` → 3286 / 3003;逐檔 `grep -c parametrize` 全 0;`git log --since=2026-09-09 cda8b849 -- tests/` → 六筆。anchor:`pytest 母數對照:master 3566 → 3349;差額 217 = …`

#### R-02 [MEDIUM] .claude/refactor/slim-fade/change-spec.md:24-29 — 白名單漏列「特徵化測試移除 9 條」
問題:「刪」列逐項列到函式粒度,卻沒列 test_shared_infra_characterization.py 由 12 條砍到 3 條;鐵則 E 對刪測試最嚴,two-axis 兩軸(P-05)都漏了它。實質正當 —— 逐條驗 9 條全部只碰已刪符號。search-proof:`git diff cda8b849...HEAD -- tests/test_shared_infra_characterization.py | grep "^-"` → 移除 import 僅三支已刪模組;`grep -n characterization change-spec.md` → 零。anchor:`刪:\`copycat/backtest/fade_*.py\`、…`

#### R-03 [LOW] .claude/refactor/slim-fade/verification.md:3-4, 22 — 抬頭 commit 清單與「本批未動測試檔」兩處陳述已過時
問題:抬頭「四筆 commit … 0b435f48」但 0b435f48 已拆、f8543dde / 8e0a2470 未列,實為 7 筆;:22「本批未動測試檔」為假(App.memo.test.tsx / river-test-fixtures.ts 都動過)。search-proof:`git log --oneline cda8b849..HEAD` → 7 筆;`git log --oneline cda8b849..HEAD -- <兩檔>` → f8543dde / 9e389873。anchor:`四筆 commit:e70d1a52…0b435f48(前端 knip A5–A8)。`

#### R-04 [LOW] frontend/src/components/corr/RiverPanel.memo.test.tsx:72 — RiverOverlay 的 default export 刪了,memo 測試的 mock 還在憑空造一個 default
問題:`vi.mock` 仍回 `{ ...actual, RiverOverlay: Wrapped, default: Wrapped }`,替身比真模組多一個 export。search-proof:`grep -rn RiverOverlay src/` → 唯一真實讀者 `RiverPanel.tsx:16` 具名;`grep -rn "lazy(" src/` → 只 4 個 page,不含 corr。anchor:`  return { ...actual, RiverOverlay: Wrapped, default: Wrapped };`

#### R-05 [LOW] copycat/configio.py:4 — docstring 把「fade_config 的 validate_*」改寫成泛稱後,repo 裡一個實例都沒有
問題:四個仍在的 loader 沒有任何一個做載入後不變式檢查,grep 帶到語意無關的 `stock_watchlist.validate_code`。search-proof:`git grep -n "validate_" -- copycat/**/*.py` → 只 `validate_code` 家族;四個 `load_dataclass_json` caller 回傳後全部無後續檢查。anchor:`list → tuple 轉換 + dataclass 建構。載入後的額外不變式檢查(validate_* 類)留在 caller。`

#### R-06 [LOW] copycat/backtest/report_fmt.py:1-17 — 模組存在的理由沒了,剩下單函式單 caller 的殼
問題:只剩 `fmt_cell`、唯一 caller `backtest/report.py`;白名單不含搬回,建議記入下一批(= round-1 S-08 已不修)。search-proof:`git grep -n report_fmt -- copycat/* tests/* *.py` → 僅 `report.py:9` 與特徵化測試 `:20`。anchor:`"""報告格式 helper(T 日跟多回測報告用).`

#### R-07 [LOW] frontend/src/App.memo.test.tsx:48-52 — 註解改寫「大體誠實」但仍把三個模組一概而論
問題:仍寫「這三個模組除了元件還 re-export 別的 runtime 符號」:base `FuturesLadder.tsx` 只 export 元件;`isFutMarket` 在 base 零外部 importer。(chunk 2 同時宣稱「`RightRail` 這檔根本不存在,只有 SignalRail」—— 內部複查裁決為誤,見 F-02。)search-proof:`git show cda8b849:…/FuturesLadder.tsx | grep "^export"` → 只 `export function FuturesLadder`;`git grep TRADE_KINDS cda8b849 -- frontend/src/*` → 除自用零 importer。anchor:` *  是這三個模組除了元件還 re-export 別的 runtime 符號(\`PriceLadder\` 的 \`TRADE_KINDS\`、`

#### R-08 [LOW] frontend/src/components/stock/PriceLadder.tsx:43-46 — 改寫後的註解把 `type TradeKind` 的消費者窄化成「測試」,漏掉正式碼 RightRail(chunk 3)
問題:舊註解「(`RightRail` / 測試)」;改寫後只剩「測試 import `type TradeKind` 的既有路徑」。search-proof:`git grep -n 'from "@/components/stock/PriceLadder"' -- frontend/src` → `RightRail.tsx:7` + `PriceLadder.test.tsx:6`。anchor:` *  re-export(測試 import \`type TradeKind\` 的既有路徑)。\`TRADE_KINDS\` 的 re-export 於`

#### R-09 [LOW] frontend/src/lib/river-chart-svg.ts:22 → 症狀 RiverPanel.memo.test.tsx:20 — PAD_Y 降私有後,江波圖 memo 測試檔頭仍把它列為「partial mock 保留真身的其餘 export」(chunk 4)
問題:檔頭列 `offsetAtX / spreadLabelYs / timeTicks / PAD_Y`,PAD_Y 已不在 module 命名空間。search-proof:`git grep -n "^export" frontend/src/lib/river-chart-svg.ts` → 9 筆不含 PAD_Y;`git grep -n PAD_Y -- frontend/src` → 跨檔命中全屬同名不同值常數。anchor:` *  (\`offsetAtX\` / \`spreadLabelYs\` / \`timeTicks\` / \`PAD_Y\` …)一律保留真身 ——`

#### R-10 [LOW] frontend/src/components/stock/PriceLadder.tsx:43-46 — 同 R-08(chunk 5 獨立命中)
問題:與 R-08 同 file:line、同結論。search-proof:`grep -rn 'from "@/components/stock/PriceLadder"' frontend/src` → 兩個消費者,非「只有測試」。

#### R-11 [LOW] frontend/src/lib/trade-kinds.ts:54-56 — `_KindDomainsMatch` 是全檔唯一躲過瘦身的零 importer type export,但沒留下「為何不能降私有」的一行(chunk 5)
問題:降私有會踩 `noUnusedLocals`(實測 TS6196),留 export 正確但理由未寫;附帶算術:降私有的 type export 實為 32(22 interface + 10 type),盤點 A6 寫 33,差額 1 與此吻合。search-proof:`grep -rn _KindDomainsMatch frontend/src` → 只 :43 註解 + :56 宣告;最小重現檔 `tsc --noEmit --strict --noUnusedLocals` → TS6196;`git diff … | grep -c "^-export interface "` = 22、`"^-export type "` = 10。anchor:`export type _KindDomainsMatch = Expect<AssertEqual<TradeKind, PositionKind>>;`

#### 行為不變驗證(reviewer 自跑)
- **承諾 1(server 零改動)**:chunk 1 `git diff cda8b849...HEAD --stat -- copycat/server` 空。
- **承諾 2(CLI)**:chunk 1 / chunk 2 各自 `sub.add_parser` 21 → 16、`if args.command ==` 20 → 15,removed 恰為 fade-diagnose / fade-cells / fade-anatomy / fade-entry-anatomy(多行呼叫)/ fade-search;chunk 1 實跑 `python -m copycat --help` 列 16 個且無 `fade-*`;chunk 2 `git diff --numstat` cli.py = `0 114` 純刪、其餘位元逐字相同。
- **承諾 3(validate)**:replay / engine 未動;chunk 2 驗 `aggregate.py` `_last_cum` 5 處內部使用、`lock_quality.py` `_run_start` 5 處讀者全在;base 側 `git grep current_lock_start cda8b849 -- tests/` 只命中定義本身 → 沒刪保護;三兄弟中 `first_touch_idx` / `n_reopens` 有 SC-8 測試、只砍無測的那一支,一致。
- **承諾 4(report.py 逐字)**:chunk 1 `git diff -- copycat/backtest/report.py` 0 行;`from copycat.backtest.report_fmt import fmt_cell` 仍在;chunk 2 `git grep "fmt_num\|fmt_quantiles"` 只剩兩處說明性註解。
- **承諾 5(前端只拿 export)**:六 chunk 逐符號 `git grep -w` 全 `frontend/src`(含 `*.test.*`):63 個降私有符號全在同檔仍用、零跨檔 import;9 個 `export default` 移除的元件全由具名 import 消費、`lazy()` 四個 page 不在其中;`Group` 的 8 個消費者本來就從 `@/lib/watchlist-model` 取;`ladder-position.test.ts` diff 空、從未 import 那四顆常數;`tsconfig.app.json` 開 `noUnusedLocals` 故「仍在用」有機械擔保;後端 parity 讀者 `tests/helpers/frontend_source.py` 的呼叫點(close-order.ts / types.ts / day-bars-rollover.ts / constants.ts / river-colors.ts / index.css / overlay / signal_rules)無一碰本批降私有的符號,兩條讀 `types.ts` 的正則抓 `export const AVG_SOURCES` 與 `export type PositionKind`,HEAD 仍 export。
- **鐵則 E(刪測試)**:chunk 5 / chunk 6 對 27 個被刪測試檔逐檔 `git show cda8b849:<f>` 看 import 與斷言主詞,全為 fade_* / market_features;非 fade import 僅 `Bar1K` / `write_bars` / `tick_size` / `DailyIndex` 造資料 helper,各有存活測試(`test_market.py` / `tests/data/test_daily*.py` / `test_backfill_daytrade.py`);`test_fade_universe_filter` 測的是 `fade_pipeline.build_fade_universe` 非存活的 `universe.build_universe`(後者由 `test_universe.py` 覆蓋);`test_fade_walk_forward` 的防洩漏守則只守已刪 code(存活 `pipeline.py` grep `walk_forward|oos|_fold|holdout` 零命中)。
- **lock 檔**:chunk 2 逐行核 `package-lock.json` diff 恰 1 行(root devDependencies);`packages["node_modules/@eslint/js"]` 本來就在且 9.39.5 / dev:true → 零 transitive 變動。
- **兩支 SKILL.md**:chunk 1 逐路徑 `test -f`,教訓核心(guard_exit 灌水 / 6 小時黑箱)保住;改述指向 `backtest/pipeline.py::_TRADEABLE`(pipeline.py:79)實存且是存活鏈唯一一份。

### Per-file accounting(100/100,六 chunk 原文要點)

- `.claude/refactor/slim-fade/change-spec.md` — R-02(白名單漏列)。
- `.claude/refactor/slim-fade/code-review-round-1.json` — REVIEWED_NO_ISSUES(處置與 HEAD 逐條對得上;S-06 / S-08 / S-09 / P-04 四條「不修」chunk 1 認為站得住;S-04 的「零 RightRail 檔」前半句經內部複查判假,已由 F-02 承接)。
- `.claude/refactor/slim-fade/verification.md` — R-01 / R-03。
- `.claude/skills/backend-conventions/SKILL.md` — REVIEWED_NO_ISSUES(`fade-search` 確為已刪子指令,改述保留)。
- `.claude/skills/tc4-market-facts/SKILL.md` — REVIEWED_NO_ISSUES(改述指向 `pipeline.py::_TRADEABLE` 實存)。
- `configs/fade_uc_round1.json` … `round5.json`(6)— REVIEWED_NO_ISSUES(`git grep fade_uc` 零 runtime 命中,`--config` 預設 None 無隱式路徑)。
- `copycat/backtest/fade_anatomy.py` / `fade_arms.py` / `fade_cells.py` / `fade_config.py` / `fade_diagnose.py` / `fade_entry_anatomy.py` / `fade_features.py` / `fade_optimize.py` / `fade_pipeline.py` / `fade_report.py` / `fade_simulate.py` / `fade_tp.py` / `fade_vote.py` / `market_features.py` / `quantiles.py`(15)— REVIEWED_NO_ISSUES(runtime 零 dangling;`quantiles` 的「兩演算法不可換」知識隨刪消失但存活鏈只剩 `search.py::_quantile` 一份,風險本身不存在;結論仍在 docs/research B12)。
- `copycat/backtest/report_fmt.py` — R-06。
- `copycat/cli.py` — REVIEWED_NO_ISSUES。
- `copycat/configio.py` — R-05。
- `copycat/engine/lock_quality.py` — REVIEWED_NO_ISSUES。
- `copycat/live/aggregate.py` — REVIEWED_NO_ISSUES。
- `frontend/package-lock.json` — REVIEWED_NO_ISSUES(逐行核過:只加 1 行宣告,`packages` 區零變動)。
- `frontend/package.json` — REVIEWED_NO_ISSUES。
- `frontend/src/App.memo.test.tsx` — R-07。
- `frontend/src/components/capital/CapitalConfirmDialog.tsx` / `CapitalOrdersList.tsx` / `chart/ChartReadout.tsx` — REVIEWED_NO_ISSUES(`ConfirmRow` / `isFutMarket` / `ReadoutTone` 同檔仍用)。
- `frontend/src/components/corr/CorrPanel.tsx` / `RiverCards.tsx` / `RiverPanel.tsx` / `river-test-fixtures.ts` — REVIEWED_NO_ISSUES(四個 default export 全 repo 零 default import;`DAY` 同檔自用)。
- `frontend/src/components/corr/RiverOverlay.tsx` — R-04(症狀落在不在 F 內的 `RiverPanel.memo.test.tsx:72`)。
- `frontend/src/components/futures/FuturesChart.tsx`、`index/AdvanceDeclineChart.tsx` / `BreadthBand.tsx` / `LimitListSection.tsx` / `MarketPane.tsx` — REVIEWED_NO_ISSUES(消費者全具名 import;檔尾 `}` + 單一換行)。
- `frontend/src/components/stock/PriceLadder.tsx` — R-08 / R-10。
- `frontend/src/components/stock/StockIntradayChart.tsx` — REVIEWED_NO_ISSUES。
- `frontend/src/hooks/useFuturesBars.ts` / `useMarketBars.ts` / `useServerBuild.ts` / `useSignalAlerts.ts` / `useSignalSound.ts` / `useStockBars.ts` / `useStockNames.ts` / `useStockStream.ts` — REVIEWED_NO_ISSUES(`BARS_SLOW_WARN_MS` 唯一跨檔命中是測試標題字串;`setSoundOn` 消費者拿 hook 回傳解構值;CLAUDE.md:234 點名的 `useMarketBars.ts::BarsMeta.status` 同名仍在同檔)。
- `frontend/src/hooks/useStockWatchlist.ts` / `useWatchlistCommit.ts` — REVIEWED_NO_ISSUES(`Group` 8 個消費者本來就從 `@/lib/watchlist-model` 取)。
- `frontend/src/lib/candle.ts` / `fee-discount.ts` / `fetch-timeout.ts` / `flash-arm.ts` / `futures-accum-adapter.ts` / `index-chart-svg.ts` / `index-overlay-lines.ts` / `index-source-health.ts` / `ladder-position.ts` / `pane-frame.ts` / `pnl-svg.tsx` / `position-summary.ts` — REVIEWED_NO_ISSUES(24 個符號逐一 `git grep -w`;三組同名常數 `PAD_Y ×3` / `OverlayLine ×2` 確認是各檔私有副本;`ladder-position.test.ts` diff 空;`candle.ts` 三型別無 `.d.ts` / parity / docs 引用)。
- `frontend/src/lib/river-chart-svg.ts` — R-09(症狀落在不在 F 內的 `RiverPanel.memo.test.tsx:20`)。
- `frontend/src/lib/signal-model.ts` / `stkfut.ts` / `stock-accum.ts` / `stock-intraday-svg.ts` / `timeframe.ts` / `types.ts` — REVIEWED_NO_ISSUES(`SignalKind` 降私有不動 CLAUDE.md §4「政策列形狀」契約:指的是值域與文案、消費端寫字面值;`types.ts` 四型別與 parity 無關)。
- `frontend/src/lib/trade-kinds.ts` — R-11。
- `tests/backtest/test_fade_anatomy.py` / `test_fade_cells.py` / `test_fade_cells_round3.py` / `test_fade_cells_round4.py` / `test_fade_diagnose.py` / `test_fade_entry_anatomy.py` / `test_fade_guard.py` / `test_fade_phase_b.py`(8,chunk 5)— REVIEWED_NO_ISSUES(非 fade import 全為造資料 helper;`test_fade_guard` 的 `_TRADEABLE` 三方 parity 測的三支全是 fade 模組,教訓已存 SKILL.md:262)。
- `tests/backtest/test_fade_pool_diagnose.py` / `test_fade_report_round1.py` / `test_fade_round1_config.py` / `test_fade_round2_config.py` / `test_fade_round3_config.py` / `test_fade_round4_config.py` / `test_fade_simulate_round2.py` / `test_fade_simulate_round3.py` / `test_fade_simulate_round4.py` / `test_fade_tp_round4.py` / `test_fade_universe_filter.py` / `test_fade_vote.py` / `test_fade_walk_forward.py`(13,chunk 6)— REVIEWED_NO_ISSUES(斷言主詞全為已刪符號,14 個符號全 repo 零殘留;間接觸及的四個存活模組各有直接覆蓋)。

## 內部複查結果(同軸 code-reviewer,取代 4.2;非跨軸證據)

| # | 原編號 | Verdict | 原始 → 校正 severity | Evidence(要點) | baseline | 單軸可信度 |
|---|---|---|---|---|---|---|
| F-01 | R-01 | CONFIRMED | MEDIUM → MEDIUM | 實測非推算:`git archive cda8b849 \| tar -x` 後 `pytest --collect-only -q` → **3635**;worktree HEAD → **3352**(= verification:12 的 3349 + 3,方法自校驗);`def test_` 計數 3286 / 3003 同差 283;27 刪檔 `parametrize` 全 0;組成 264 + 2 + 8 + 9 = 283 閉合;3566 = MEMORY 09-09 記憶值,同行對 vitest 誠實標「memory 09-09」對 pytest 卻標「master」 | 慣例衝突(verification 文件慣例要求可重跑指令對得上輸出;同檔 vitest 那半有標記憶來源) | 高,機械可驗;chunk 1 停在推算、內部複查實跑 base 得同值 |
| F-02 | R-08 + R-10 | CONFIRMED | LOW → LOW | `ls frontend/src/components/rail/` → `RightRail.tsx` + `RightRail.test.tsx`;`sed -n 7p` 逐字 import;全 repo 對 PriceLadder `type TradeKind` 的 importer 恰 RightRail.tsx:7(正式碼)+ PriceLadder.test.tsx:6;base 註解兩消費者都在,HEAD 抹掉正式碼那半;引入點 f8543dde 依 S-04「零 RightRail 檔」假前提;S-04 後半「零外部 TRADE_KINDS」為真 | 慣例衝突(frontend-conventions:註解陳述須為真) | 高 —— 兩 chunk 各自獨立命中同 file:line;chunk 2 的否定無 file:line 且與 S-04 同源,非 2:2 |
| F-03 | R-02 | CONFIRMED | MEDIUM → LOW | `git diff --diff-filter=M -- tests/` 只此一檔;9 條逐條依賴的符號全為已刪(`quantile_*` ×6 / `fmt_num` / `fmt_quantiles` / `load_fade_config`);change-spec:19 已承諾只刪 `fmt_num / fmt_quantiles`、verification:45 已對倖存三條表態,對帳鏈覆蓋得到;「不動」清單不含 tests/ 故不違反白名單、只是未列 | 慣例支持(白名單慣例以檔案粒度列) | 高(事實無爭議),下修因「這筆沒被審」言過其實 |
| F-04 | R-03 | CONFIRMED | LOW → LOW | `git log --oneline cda8b849..HEAD` = 7 筆、無 0b435f48;同檔 :38 自揭拆分、:28 標題帶 f8543dde;兩測試檔 diff 零 `it(` / `describe(` 增刪 → 「+5 來自主線」結論仍真 | 慣例支持 | 高,機械可驗 |
| F-05 | R-04 | CONFIRMED | LOW → LOW | base `RiverOverlay.tsx:201` `export default`、HEAD 無;`RiverPanel.memo.test.tsx:66-73` 仍 `default: Wrapped`;該檔不在 diff 內(被動漂掉);vitest 3074 全綠、零 default import | 無先例(其餘 8 個拿掉 default 的元件沒有對應 mock 造 default) | 高;風險情境本身是 tsc 攔截 |
| F-06 | R-09 | CONFIRMED | LOW → LOW | base `river-chart-svg.ts:22 export const PAD_Y = 4` → HEAD `const`;mock 掛 `@/lib/river-chart-svg` 故指涉正確;同名不同物三顆已分辨 | 慣例衝突(測試檔頭文件與模組現況脫節) | 高 |
| F-07 | R-11 | CONFIRMED | LOW → LOW | base 與 HEAD :51-56 逐字相同(註解未補);verification:26 記過 TS6196;32 的算術逐行重算成立(`-export type { Group, Watchlist }` 只降 1 符號那行沒被騙到) | 慣例支持(本 repo 註解即契約,豁免理由應在現場) | 高;下次重蹈代價是 tsc 紅(響的) |
| F-08 | R-05 | CONFIRMED | LOW → LOW | `grep -rn validate_ copycat/` 命中僅 configio:4 自身、`stock_watchlist.py:53 validate_code` 及三 caller、`bars.py:341` 註解;`validate_code` 是載入前字串格式檢查;四個 loader 無一做載入後檢查 | 慣例支持(句子的職責邊界宣告仍為真) | 高;僅指涉落空 |
| F-09 | R-07 | PARTIAL | LOW → LOW | FuturesLadder 半邊成立(base / HEAD 都只 `58:export function FuturesLadder`);`isFutMarket` base 零外部 importer;**但** base 原文同樣「三個模組」配兩個例子,失真早已存在;HEAD 改寫縮小失真並補「已拿掉、只剩型別」(驗為真) | 慣例支持現狀(繼承自 baseline) | 中 —— 事實可信,再收一次是措辭品味;chunk 2 同一份報告對 base 側取證不足(見 F-02 裁決) |
| F-10 | R-06 | OUT_OF_SCOPE | LOW → LOW | 整檔 = docstring + `fmt_cell`,唯一 caller `report.py:9`;`code-review-round-1.json` S-08 逐字同條、disposition「不修,記 next-time」;change-spec:26 白名單只到 `fmt_num / fmt_quantiles`、:31 「不動」明列 `backtest/report.py` | 慣例支持(round-1 已拍板) | 高(事實)/ 重覆上報屬噪音 |

**矛盾裁決(內部複查)**:(a) `RightRail.tsx` 存在,chunk 3 / 5 正確,chunk 2 與 round-1 S-04 皆假 —— 取證品質非多數決:兩次獨立 file:line 對一句無 file:line 的否定,且後者與 S-04 同源。(b) base `cda8b849` collected 實測 3635,「3566」為 09-09 記憶值,`git archive` 實跑 + `def test_` 計數兩法閉合。

## Action Items

Severity calibration:6c(移除既有防護類)— 本 PR 刪 27 個測試檔,逐檔驗(chunk 5 / 6 + 內部複查 F-03)全為「測已刪 code 的測試」,非防護削弱;免。6d-1(hedge cap)— F-02「下一輪瘦身照這句判」、F-05「日後有人寫 default import」、F-07「下次 knip 再報」皆為條件句,已在 Nice。6d-3(Must Fix 雙半條件)— 十條皆無 user-visible 重現路徑(全在 artifact 算術 / 註解 / 測試鷹架 / docstring 層),零阻擋出貨,無一落 Must / Should。未驗證前提檢查:F-01 `git archive` 實跑、F-02 `ls` + `sed`、F-03 `--diff-filter=M`、F-04 `git log`、F-05 / F-06 `git show` base 對照、F-07 逐行計數 + TS6196 實錄、F-08 grep 皆第一手,拿掉任何論據等級不變;F-09 的「三個模組」半邊成立半邊繼承,已標 PARTIAL;F-10 事實無爭議、處置引 round-1 拍板。Provenance cap:N-A。校準套用:無作者校準檔(`loger-w.md` 不存在)、本輪無套用。4.3b lone finding:本場 CC 單軸,分片結構下每條至多兩個 chunk 看得到;F-02 是兩 chunk 獨立命中(非 lone);其餘「他軸為何漏」改答分片可見性 + 單軸可信度(見內部複查表末欄);F-01 / F-02 / F-04 / F-05 / F-06 / F-07 / F-08 可獨立採信(機械可驗);F-03 事實可信、severity 下修;F-09 PARTIAL 標 ask-user;F-10 OUT_OF_SCOPE 落參考用。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

無。

### Nice to Have(可選優化)

- **F-01** `verification.md:21` 改「cda8b849 3635 → HEAD 3352(3349 passed + 3 skipped);差額 283 = 25 支 fade 檔 264 + test_cli_fade 2 + test_market_features 8 + 特徵化 9」。
- **F-02** `PriceLadder.tsx:44` 括號回寫「(`RightRail` / 測試 import `type TradeKind` 的既有路徑)」;`code-review-round-1.json` S-04 補註「前半句『零 RightRail 檔』經 pr-230 review 判假(`components/rail/RightRail.tsx` 存在)」。
- **F-03** `change-spec.md:24-26` 白名單補列 `tests/test_shared_infra_characterization.py 12 → 3 條(9 條全為已刪符號的特徵化)`。
- **F-04** `verification.md:4` 改列 7 筆 commit;`:22` 改「動到的測試檔只有註解 / fixture export 關鍵字,母數不受影響」。
- **F-05** `RiverPanel.memo.test.tsx:72` 刪 `default: Wrapped`。
- **F-06** `RiverPanel.memo.test.tsx:20` 刪 `/ PAD_Y` 或改述。
- **F-07** `trade-kinds.ts:55` 註解尾補「`export` 不可拿掉:零 in-file 引用,降私有會 TS6196;knip 會誤報,屬已知」;`change-spec.md:27` 33 → 32 並記差額 = `_KindDomainsMatch`。
- **F-08** `configio.py:4` 刪括號從句,或改「目前無 caller 這麼做(原例 fade_config 已於 2026-09-14 刪除)」。
- **F-09** `App.memo.test.tsx:49` 「三個模組」→「其中兩個模組曾另有 runtime export」—— user 拍板(`ask-user`)。
- 九條可併一筆 `chore(docs)` + 一筆 `chore(test)` 收修(零 runtime 改動,不需重啟 prod;前端只動註解與測試 mock,dist 不需 build)。

### 參考用(任一軸驗證為 REFUTED / OUT_OF_SCOPE / PARTIAL 且不建議動 code)

- **F-10** `report_fmt.py` 單函式單 caller:CC 主軸判 one-instance seam → 內部複查判 OUT_OF_SCOPE(round-1 S-08 逐字同條、已拍板不修;change-spec 白名單與「不動」清單皆排除)→ 使用者自行決定是否在下一批瘦身(B 桶)搬回 `report.py`。

## 審查工具比較(qualitative)

- CC 主軸(python-reviewer ×6 chunks):context-aware;核心問題(純刪除是否刪錯 / 是否留 dangling)以逐檔 `git show` base 側 import + 全 repo `git grep` 自證,27 個被刪測試檔逐檔驗斷言主詞;十條 finding 全在「artifact 算術」「收修引入的註解退步」「diff 外被動漂掉的測試鷹架」「docstring 指涉落空」—— 純看 diff 抓不到(要對照 base 註解原文、`git archive` 實跑、反向 grep 被刪符號的殘留引用)。chunk 間一處矛盾(RightRail 存在與否)由內部複查以 file:line 裁決。
- 內部複查(code-reviewer):同軸、非跨軸證據;10/10 齊,CONFIRMED 8 / PARTIAL 1 / OUT_OF_SCOPE 1 / REFUTED 0;severity 下修 1(F-03 MEDIUM → LOW);兩條以實跑落地(F-01 `git archive` base collect、F-07 最小重現 TS6196)、一條找到 baseline 反證(F-09 三個模組是繼承)。
- Codex / Gemini:N-A(user 停用),無跨軸重疊率可算;對抗式增益 N-A。
- REFUTED 率 0%(PARTIAL 10% / OUT_OF_SCOPE 10%):主軸命中率高,但同模型家族互驗,且十條全 MEDIUM / LOW 文件 / 註解 / 鷹架層 —— 對一個 server 零 diff、gate 全綠、validate 42/42 的純刪除 refactor,這個分佈是預期的。真正有價值的兩條:F-01(對帳數字建立在記憶值上)與 F-02(上一輪收修依假前提把真消費者從註解抹掉)—— 都是「review 產物本身」的正確性問題。

## 沒做的部分(結案對帳)

- Codex 中性軸:N-A —— user 明示停用(沿 #188 / #190 / #199 / #202 / #211 / #218 / #220 / #222 / #228 前例),未起軸、未 retry。
- Codex 對抗式軸:N-A —— 同上。
- Gemini Flash 軸:N-A —— user 明示停用。Gemini Pro:N-A(同上;Step 2.96 依前例不再問)。
- Step 2.98 Codex preset 詢問:N-A(Codex 停用,依前例不再問)。
- Cross-axis verification 4.1:N-A(無非 CC finding)。4.2:以同軸 code-reviewer 內部複查代替(PASS,10/10),**非跨軸證據**。4.3a consensus:N-A(單軸無 consensus;F-02 兩 chunk 同軸命中不算跨軸)。4.3b lone:處置見 Action Items。
- Review input binding:**verified**(`refs/pull/230/head` = headRefOid `8e0a2470`,worktree detached 於該 SHA;merge-base = baseRefOid `cda8b849`)。
- Blast radius(2.9):PASS(有跑)但空輸出跳過(`sem` 未安裝)。
- React-doctor(2.97):PASS,未引入新問題(`newCount 0 / fixedCount 1 / baseTotalCount 15`,changed 48 檔;既有 15 條不計)。
- Formal spec traceability(2.65):SKIPPED (C4_NO_NORMATIVE_CLAUSE);spec-compliance-reviewer 未派。
- Author calibration(2.2):無檔、本輪無套用。
- Reviewer 未重跑全量 pytest / ruff / pyright / validate / vitest:review worktree 純讀碼(chunk 1 實跑 `python -m copycat --help`;內部複查實跑 `pytest --collect-only` 於 base archive 與 worktree HEAD、以及最小重現 `tsc --noUnusedLocals`);全量綠燈證據引自 PR 內 `verification.md`(出貨前實跑 pytest 3349 passed / 3 skipped、ruff 0、pyright 0、validate 42/42、tsc 0、eslint 0、vitest 3074、react-doctor 無新 finding)+ merge 後主樹實跑 `python -m copycat --help` 16 個子指令無 fade-* 與 `python -m copycat validate` 42/42 PASS(orchestrator 於 Step 5 前執行)。
- 未驗前提(集中揭露):F-02「下一輪瘦身照這句判」、F-05「日後有人寫 default import」、F-07「下次 knip 再報」是條件句(皆有 tsc 攔截,已在 Nice);F-09「三個模組」失真是繼承自 baseline 的判定(base 原文並排比對過);F-10 引 round-1 拍板為據。三處在 verification.md 的算術(F-01 / F-04)與 change-spec 的計數(F-03 / F-07 的 33 vs 32)皆由內部複查第一手重算。
- 真環境:純刪除 + 註解 + export 關鍵字,runtime 零觸碰;prod 不需重啟、dist 不需 build;本 review 未另跑 server。
- Self-Verify:已執行(`skill-verify-auditor`,requested=opus / observed=UNAVAILABLE;唯讀、只 Read 本草稿檔一次,2 tool 呼叫)。R1–R10 全 PASS、`VERDICT: COMPLIANT`,零修正;未重派 auditor。
