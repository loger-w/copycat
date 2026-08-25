# PR #106 Code Review 比較報告 · SHA 06484a79

**Report projection schema**: 1
**PR**: [loger-w/copycat#106](https://github.com/loger-w/copycat/pull/106)
**標題**: mod(frontend): N022 全站 localStorage 收斂到 lib/storage —— 私密視窗 / 政策鎖存取即拋不白屏、quota 滿寫入不炸(48 處 → 單一出口)
**作者**: XU MIN YU(loger-w;commits 署名 Loger)
**分支**: `mod/storage-consolidation` → `master`(PR 狀態 MERGED,merge commit cd74c10b;本輪為事後回顧 review)
**變更**: 22 檔案, +1189 / -185
**審查日期**: 2026-08-25
**Review input basis**: source repo R_kgDOTsITBg + 06484a79ee652582c0b8ce9b668240076b809809;destination repo R_kgDOTsITBg + 7ad289063351c1321ca4e549ddd1e3c565485cc6;`input_binding: verified`(worktree HEAD = source SHA;`refs/pull/106/head` FETCH_HEAD = source SHA;merge-base(source, destination) = destination SHA;PR 已 merge,`origin/master` 已前進 14 commit 至 892135aa 但 PR 記錄的 destination SHA 不變)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-106`(detached)
**worktree HEAD**: 06484a79ee652582c0b8ce9b668240076b809809
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 缺席 → 全數 INCONCLUSIVE)+ Gemini 軸 N-A(本機無 agy CLI;Flash 永久軸與 Pro opt-in 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=typescript-reviewer ×2(chunk 1 / chunk 2;frontmatter requested=opus effort=xhigh;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / secret / request-body / session 面);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(未派工);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=22 → covered 5 / no-issues 17 / skipped 0 / **missed 0**(chunked: 是,2 塊;FILE_COUNT=16 源檔 > 15、DIFF_LINES=1374 > 800,兩門檻皆觸發;chunk 1 = 7 檔 636 行、chunk 2 = 15 檔 738 行;union = F)
**定位 (ENH-B)**: anchored exact 7 / ambiguous 0 / **FAILED 0**(全部 anchor 於 worktree HEAD 逐字唯一比中;F-05 由 reviewer 自報 24-29 修正為 26-27,F-07 修正為 1)
**React-doctor (2.97)**: 未引入新問題(既有 4 條不計;工具 baseline 報 newCount=1 = `src/components/stock/GroupGridView.tsx:72 only-export-components`,但該行不是 `+` 行 —— 是 base 第 78 行 `export function gridShape` 因上方刪 6 行位移而來,ID 含行號故被算成新;依「file:line 落在 + 行才算新」判為 pre-existing)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(xu-min-yu.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,22 檔全部 authored)
**審查軸狀態**: primary(typescript-reviewer chunk 1)PASS(4 findings、7/7 accounting);primary(typescript-reviewer chunk 2)PASS(3 findings、15/15 accounting);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(codex 缺席);Codex 對抗 N-A(codex 缺席);Gemini Flash N-A(agy 缺席);Gemini Pro N-A(opt-in 未開且 agy 缺席);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL(Codex 缺席,7 條全 INCONCLUSIVE)/ 4.3a N-A(無 consensus)/ 4.3b PASS(7 條 lone 逐條判斷);react-doctor PASS(跑於 worktree frontend/,exit 0);coverage assertion PASS;re-anchor PASS
**Self-Verify**: PASS(VERDICT: COMPLIANT,零修正;詳「沒做的部分(結案對帳)」)

**Report generation**: sha256:cf1809a9ec21e36c3f430e3d7fc9ab5e062b9916c6b1732e9d18033644157a9c

---

## Spec 依據

- 偵測到 spec:`.claude/mod/storage-consolidation/change-spec.md`(檔名符合 `*-spec.md`;PR 內新增,200 行,全文注入兩支 reviewer)。另兩份 `verification.md` / `code-review-round-1.json` 為驗證紀錄與 review JSON,不當 spec 用。
- 關鍵內容:§0 既有行為白名單(caller map;22 支 key 字面值逐字不變;19 條預設值表;W1–W10 不可破壞語意);§1 七條判定型決定(布林回傳 / readLocal 回 null / 不加 writeLocalJson / readLocalJson 回 unknown / 四旗標各自警告一次、壞 JSON per-key / **不做 in-memory fallback** / storage.ts 不 import constants.ts);§2 申報的兩項可觀察差異(失敗時 console 警告一次、purgeOrphanKeys 逐鍵吞);§3 測試 seams;§4 round-1 review 收修。
- ⚠️ spec 作者 = PR 作者(`git log --format=%an` 於 spec 路徑 = Loger,與 commits 作者相同;out-of-scope 判定以此 spec 為據時,注意作者自寫 spec 的利益重疊)。本輪有兩處 finding 的分級依賴此 spec 的範圍宣告(F-06 依 §1.2「呼叫點逐字不動」、F-05 的修法依 §1 決定 6「不做 in-memory fallback」)。
- SPEC_COMPLIANCE receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED`、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool calls=0(無)。0 clauses / 0 findings / 0 observations / 0 invalidated。說明:曾以 W2(「App 舊 key 遷移:setItem 成功才 removeItem」,change-spec.md:84,INVARIANT)送 `pr-review-c4.py resolve-authority`,reducer 回 SKIPPED —— 它只接受 `openspec/specs/**` 與 `openspec/changes/**` 路徑作為 authority,本 repo 的 spec 住在 `.claude/mod/`,結構上不在 C4 lane 的授權範圍;非本 PR 缺陷。另註:本機為 Windows,`pr-review-c4.py dispatch-envelope` 的 permit 目錄依賴 POSIX(`/private/tmp` + `os.getuid`),即使路徑合格也無法派工 —— 本輪未走到那一步。

## 變更概要

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `frontend/src/lib/storage.ts` | 新增 | 唯一 localStorage 出口:readLocal / writeLocal / removeLocal / readLocalJson;四旗標各警告一次 |
| `frontend/src/lib/storage.test.ts` | 新增測試 | 16 案:讀寫刪 JSON 成功 / 失敗態、旗標獨立、getter 拋(SP1 形狀) |
| `frontend/src/components/index/MarketPane.storage.test.tsx` | 新增測試 | 4 案:存取即拋不白屏、QuotaExceededError 不中斷 handler |
| `frontend/src/App.test.tsx` | 測試 | +3 案:存取即拋退預設 tab、寫入拋不打穿樹、舊 key 遷移順序 |
| `frontend/src/App.tsx` | 修改 | 7 裸奔 + 3 已包呼叫點搬家;遷移改 `if (writeLocal) removeLocal`;1 行 react-doctor inline disable |
| `frontend/src/components/index/MarketPane.tsx` | 修改 | 10 處一對一搬家(4 initializer + 5 handler) |
| `frontend/src/components/corr/RiverPanel.tsx` | 修改 | 3 裸 + 1 已包;initialOff 併入 readLocalJson |
| `frontend/src/components/index/LimitListSection.tsx` | 修改 | loadFilter 走 readLocalJson;縮排 / import 序 |
| `frontend/src/components/rail/RightRail.tsx` | 修改 | 3 處搬家 |
| `frontend/src/components/stock/GroupGridView.tsx` | 修改 | loadGroupName / persistGroupName 內部換出口 |
| `frontend/src/components/stock/StockChart.tsx` | 修改 | 2 處搬家 |
| `frontend/src/components/stock/StockPage.tsx` | 修改 | selectView 換出口;import 序 |
| `frontend/src/components/stock/WatchlistSidebar.tsx` | 修改 | 2 persist + loaders 搬家 |
| `frontend/src/hooks/useChartToggles.ts` | 修改 | load / persist 換出口;v<2 升級仍立刻落檔(W8) |
| `frontend/src/hooks/useSignalSound.ts` | 修改 | setSoundOn 換出口、忽略回傳(W4);新註解 |
| `frontend/src/lib/constants.ts` | 修改 | purgeOrphanKeys 逐鍵 removeLocal;新 import |
| `frontend/src/lib/fee-discount.ts` | 修改 | persistDiscount 寫失敗早退不通知(W3) |
| `frontend/src/lib/fut-chart-mode.ts` | 修改 | 讀寫換出口 |
| `frontend/src/lib/stock-view.ts` | 修改 | 單行化 |
| `.claude/mod/storage-consolidation/change-spec.md` | 文件 | spec(見上) |
| `.claude/mod/storage-consolidation/verification.md` | 文件 | 驗證紀錄:commits 表、紅態證據、mutation、gate、§7 真環境過目清單 |
| `.claude/mod/storage-consolidation/code-review-round-1.json` | 文件 | two-axis review round 1 JSON |

Provenance:N-A(base = master,全部 authored)。

## 發現總覽

| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | 複查 | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | verification §7 真環境驗收判準「console 只有一則讀取失敗」與 code 實際輸出不符(存取即拋 = 三則、第一則是刪除失敗;配額 0 = 零則讀取失敗) | MED [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(Codex 缺席);4.3b lone 維持 MED;機制由 orchestrator 第一手核對 App.tsx:114 / constants.ts:48 / storage.ts:63-66 | Nice to Have | `auto-fix` | 純文件修正、修法明確;做 §7 真環境過目前先改,否則會產生假 FAIL |
| F-02 | verification 稱 inline react-doctor disable 是「全 repo 唯一一處」,base 已有兩處(StockPage.tsx:109 / useStockStream.ts:325);storage.ts 檔頭同句複製 | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE;4.3b lone 維持 LOW | Nice to Have | `auto-fix` | 兩處文字同步改成「第三處」即可 |
| F-03 | verification §1「🔴 只碰裸奔處」與 fa0003d9 實際內容(含 RiverPanel initialOff、App 遷移區塊兩處已包)及 spec §1.2 表格互相矛盾 | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE;4.3b lone 維持 LOW | Nice to Have | `auto-fix` | 只改紀錄敘述,不重寫歷史(與 ST2 同取捨) |
| F-04 | spec §2 把 console.warn 標為「dev console 警告」,但 code 無 DEV 閘、vite 無 drop_console,prod build 一樣印;附 line 8「14 個檔」實為 15 | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE;4.3b lone 維持 LOW | Nice to Have | `auto-fix` | 去掉「dev」字樣、數字更正;code 本身是對的 |
| F-05 | useSignalSound 新註解主張「這邊的真相是使用者剛按的開關」,但 getSoundOn 每次快照重讀 storage,寫失敗時通知只讓訂閱者讀回舊值,W3 / W4「刻意相反」零可觀察差異 | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE;4.3b lone 維持 LOW | Nice to Have | `ask-user` | 改註解(預設)或改行為補 in-memory 覆寫 —— 後者撞 spec §1 決定 6 非目標,要 user 拍板 |
| F-06 | GroupGridView 的 loadGroupName / persistGroupName 收斂後成純 pass-through(各一個呼叫點、無 edge case) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE;4.3b lone 維持 LOW;reviewer 自評屬 spec §1.2「呼叫點逐字不動」範圍內 | Nice to Have | `no-op` | 非本 PR 缺陷,收斂後才浮出的可回收殘骸,記 next-time |
| F-07 | constants.ts 新 import 插到檔頭 doc 之前,同批其餘五檔皆「doc → import」 | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE;4.3b lone 維持 LOW | Nice to Have | `auto-fix` | 搬一行;tsc / eslint 皆綠,純可讀性 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: be558c447b7ea2ebb30e action=auto-fix
F-02 finding_uid: 5bfdbefeae697845e2a7 action=auto-fix
F-03 finding_uid: 6a7befc542a555c69ee0 action=auto-fix
F-04 finding_uid: 351eaea38caf7a0d7d86 action=auto-fix
F-05 finding_uid: 0037da6f1be6f4adfb71 action=ask-user
F-06 finding_uid: 84aa7aadbb7e02a916ff action=no-op
F-07 finding_uid: 52d12fba25df295400d0 action=auto-fix

### Inline Comments per Finding（直接複製貼到 PR review）

#### #1 §7 的真環境驗收判準對不上 code:存取即拋會是三則警告、第一則是「刪除失敗」

**File**: `.claude/mod/storage-consolidation/verification.md`
**Line**: 150-152

**Comment**:
```
這段寫「console 有 storage: localStorage 讀取失敗… 一則(只有一則)」,但照現在的 code 不可能長這樣:
App.tsx:114 的 purgeOrphanKeys() 在 module scope,比任何 render / readLocal 都早跑,
七把鍵各走 removeLocal → 政策鎖下第一則印的是 warnRemove 的「刪除失敗(政策鎖?),殘值留著,下次啟動再清」;
接著 initializer 才印「讀取失敗」、掛載 effect 再印「寫入失敗」→ 存取即拋是三則。
配額 0(只有 setItem 拋)那種形狀 readLocal 是成功的 → 「讀取失敗」一則都不會有。

§8.5 已經把警告種類修成四種,卻留一句「§7 真環境清單不變」——漏改的正是這一節。
照這份清單去驗會得到假 FAIL(或把三則當正常略過)。

改成依失效形狀分述:
  存取即拋(私密視窗 / 政策鎖):console 依序三則 —— 刪除失敗、讀取失敗、寫入失敗,各一則;第一則在畫面出來之前。
  只有寫入拋(配額 0):只有「寫入失敗」一則,不會有讀取失敗。
§8.5 末句同步改「§7 已同步更新」。
```

#### #2 「全 repo 唯一一處 inline disable」不成立,base 就有兩處

**File**: `.claude/mod/storage-consolidation/verification.md`
**Line**: 124

**Comment**:
```
merge-base 7ad28906 上已經有 StockPage.tsx:109(no-pass-data-to-parent)和
useStockStream.ts:325(no-set-state-after-await-in-effect)兩處同款 inline disable,
本輪加的是第三處。這句話被當成「選 inline 而不是 doctor.config.json」的稀缺性理由,前提不對。
lib/storage.ts 檔頭 26-27 行同一句也要一起改。

→ 「本輪是 repo 內第三處 inline disable(既有:StockPage.tsx:109 / useStockStream.ts:325),沿用同款語法」
```

#### #3 §1「🔴 只碰裸奔處」跟 fa0003d9 實際內容對不上

**File**: `.claude/mod/storage-consolidation/verification.md`
**Line**: 16

**Comment**:
```
fa0003d9(🔴)除了 27 處裸奔,也改寫了兩處原本就包著 try/catch 的地方:
RiverPanel.tsx::initialOff(整段 try/catch → readLocalJson)和 App.tsx::initialStockCode 的遷移區塊。
RiverPanel 只在這個 commit 出現(d8c3924e 的檔案清單沒有它),commit message 寫的「已包的 21 處走下一個 🔵」也不成立。
有意思的是 change-spec §1.2 的表是對的(RiverPanel 3 裸 + 1 已包、App 7 讀寫 + 3 已包都標 🔴),
而且照 §8.4 新判準(會產生新 console 輸出就不算 🔵)這樣歸 🔴 反而正確 —— 錯的只是這行敘述。

→ 「🔴 動實作,含裸奔 27 處與 RiverPanel / App 內同函式的已包處(改寫後同樣會產生 console 輸出,依 §8.4 歸 🔴);🔵 其餘 21 處已包 try/catch 的逐字搬家」
不重寫歷史,只改紀錄。
```

#### #4 這些 console.warn 不是 dev-only,prod build 一樣會印

**File**: `.claude/mod/storage-consolidation/change-spec.md`
**Line**: 163

**Comment**:
```
storage.ts:49-67 與 readLocalJson 的 warn 都是無條件 console.warn,沒有 import.meta.env.DEV 判斷;
vite.config.ts 也沒設 esbuild.drop / drop_console,Vite 預設不剝 console。
這其實是對的 —— 看盤日常跑 build + preview,§7 就是要在真瀏覽器 console 看這些訊息;dev-only 反而驗不到。
所以 code 沒問題,標籤錯了:「dev」拿掉,或寫成「console 警告(prod build 亦會印,§7 靠它)」。
verification §5.1 同一個字也一起改。

順帶:line 8「48 個呼叫點 / 14 個檔」,base 實測是 15 個檔(呼叫點 48 正確)。
```

#### #5 這段註解講的機制跟同檔第 21 行打架:開關的真相還是在 storage

**File**: `frontend/src/hooks/useSignalSound.ts`
**Line**: 26-27

**Comment**:
```
註解說「那邊的真相在 storage、這邊的真相是使用者剛按下的那個開關」,但 line 21 的
getSoundOn() = readLocal(SOUND_KEY) !== "off",而它同時就是 useSyncExternalStore 的 getSnapshot ——
每次快照都重讀 storage。寫失敗時「仍通知」只會讓訂閱者讀回舊值(配額滿:storage 還是 "on" → 回 true;
政策鎖:讀失敗 → 預設 true),開關會自己彈回去。W3 / W4 這組「刻意相反」在可觀察行為上是零差異,
這也是為什麼既有三案寫不出鑑別它的鎖。行為跟 master 一樣(W4 守住了,不是回歸),只是註解把站不住的機制寫成不變式。

預設改註解就好:
  // 寫入結果不看:兩種失效態下通知都只會讓訂閱者重讀 storage 裡的舊值(開關會自己彈回去),
  // 留著通知只是省一個分支 —— 與 fee-discount::persistDiscount 早退的差別僅止於此。
要真的讓開關在寫失敗時照使用者選的走,得在 module 級補一份 in-memory 覆寫當 getSnapshot 來源 ——
那撞到 spec §1 決定 6(不做 in-memory fallback),要另外拍板。spec §0.4 W4 的理由句也跟著改。
```

#### #6 loadGroupName / persistGroupName 收斂後只剩轉發,可以直接 inline(不是本 PR 缺陷)

**File**: `frontend/src/components/stock/GroupGridView.tsx`
**Line**: 51-58

**Comment**:
```
不是 PR 缺陷,記 next-time 就好:這輪的目標是「呼叫點逐字不動、只換出口」(spec §1.2),所以留著沒錯。
只是收斂之後這兩支各只剩一行、各只有一個呼叫點(258 / 328)、也沒包任何 edge case,
刪掉改成 useState(() => readLocal(STOCK_GROUP_KEY)) 和 writeLocal(STOCK_GROUP_KEY, name) 複雜度就直接消失。
對照同批的 readStockView(帶值域判讀)/ persistCollapsed(帶 JSON.stringify)/ useChartToggles::persist(帶版本欄)都還有內容,那些該留。
```

#### #7 constants.ts 的新 import 插到檔頭 doc 前面了

**File**: `frontend/src/lib/constants.ts`
**Line**: 1

**Comment**:
```
同一輪動到的 storage.ts / stock-view.ts / fee-discount.ts / fut-chart-mode.ts / useSignalSound.ts
全部是「檔頭 doc → import」,只有這檔變成 import 在最上面、doc 被夾在 import 和 TAB_KEY 的 JSDoc 之間。
tsc / eslint 都綠,純可讀性 —— 把 import { removeLocal } from "@/lib/storage"; 移到檔頭 doc 之後就好。
(31 個 @/lib/constants 引用者因此多一條到 lib/storage 的邊,單向無環、tree-shake 得掉,不值得為此搬 purgeOrphanKeys。)
```

## Opus 原始 findings (first-pass, context-aware)

chunk 1(typescript-reviewer;7 檔):

- **TS1-1** MEDIUM `.claude/mod/storage-consolidation/verification.md:150-152` — §7 真環境驗收判準「console 只有一則讀取失敗」在本 PR 的 code 下不可能成立。機制(逐行讀):App.tsx:114 `purgeOrphanKeys()` module scope → constants.ts:47-49 七鍵逐一 `removeLocal` → storage.ts:63-66 `warnRemove` 獨立文案;App.tsx:182-195 三條 effect 掛載即 `writeLocal` → `warnWrite`。存取即拋 = 三則、首則刪除失敗;配額 0 = 零則讀取失敗。§8.5 改了警告種類卻宣告「§7 不變」。Search-proof:Grep `purgeOrphanKeys|ORPHAN_STORAGE_KEYS`;Grep `localStorage` 全 src(排除 storage.ts / tests)確認無其他存取路徑。Spec-ref:change-spec §2「每種故障一次」(申報正確,錯在 verification 縮寫)。→ F-01
- **TS1-2** LOW `verification.md:124` — 「inline disable 全 repo 唯一一處」與 base 不符(StockPage.tsx:109、useStockStream.ts:325 在 7ad28906 即存在,`git show 7ad28906:<path> | grep` 核過);storage.ts:26-27 同句。→ F-02
- **TS1-3** LOW `verification.md:16` — 「🔴 只碰裸奔處」與 fa0003d9 內容(RiverPanel::initialOff、App 遷移區塊兩處已包)及 spec §1.2 表格矛盾;逐 commit `git show --stat` 核過 d8c3924e 不含 RiverPanel / App。→ F-03
- **TS1-4** LOW `change-spec.md:163` — 「dev console 警告」無 DEV 閘、vite 無 drop_console(grep `drop|pure|minify|terser` 無命中);line 8「14 個檔」以 `git archive 7ad28906` 解出實測 15。→ F-04
- 驗證註記(非 finding):收斂 grep 判準複驗 0 行;`npx vitest run src/App.test.tsx` 53 passed;獨立重跑 M5 mutation(TAB_KEY 換回裸 setItem)→ (b)(c) 兩條紅,證實 App 層 `not.toThrow` 非 vacuous;RiverPanel / LimitListSection 等價性逐路徑核過;兩個候選未 flag(JSON 陣列讀取的形狀驗證重複 —— spec §1 決定 4 明文保留;敘事型註解 —— 既有 house style)。
- Accounting:REVIEWED_NO_ISSUES code-review-round-1.json / App.test.tsx / App.tsx / RiverPanel.tsx / LimitListSection.tsx。

chunk 2(typescript-reviewer;15 檔):

- **TS2-1** LOW `frontend/src/hooks/useSignalSound.ts:24-29`(re-anchor 26-27)— setSoundOn 新註解主張的機制被同檔 line 21 推翻;reviewer 在 worktree 寫暫時測試實測(a)配額滿 setSoundOn(false) 後 getSoundOn() 仍 true、(b)政策鎖同上,已還原。Search-proof:Grep `useSignalSound|setSoundOn(` 讀者 StockPage.tsx:84 / useSignalAlerts.ts:126;既有三案無寫入失敗案。Spec-ref:§0.4 W4。→ F-05
- **TS2-2** LOW `GroupGridView.tsx:51-58` — Design-8 pass-through;宣告 51 / 56、呼叫 258 / 328、非 export。Spec-ref §1.2(reviewer 自評範圍內,參考用)。→ F-06
- **TS2-3** LOW `constants.ts:1-3` — import 在檔頭 doc 前;head -12 五檔對照;`@/lib/constants` 引用者 31 檔。→ F-07
- 驗證註記(非 finding):worktree 內 `npx tsc -b` exit 0、`npx eslint src` exit 0、`npx vitest run` 147 files / 2782 tests passed;兩個 mutation 皆紅(MarketPane.selectKey 裸 setItem → 2 紅;readLocal 把 `window.localStorage` 提到 try 外 → lib + MarketPane SP1 鎖紅);storage.ts 逐行核:三支出口整句在 try 內、W9 守住、readLocalJson 空字串早退、`__proto__` 不污染原型、四旗標互不共用;storage.ts 檔頭 35 行 doc 含 react-doctor 誤報全文 —— spec §1.3 明文決定放這裡,不 flag。
- Accounting:REVIEWED_NO_ISSUES storage.ts / storage.test.ts / MarketPane.storage.test.tsx / MarketPane.tsx / RightRail.tsx / StockChart.tsx / StockPage.tsx / WatchlistSidebar.tsx / useChartToggles.ts / fee-discount.ts / fut-chart-mode.ts / stock-view.ts。

合併:無跨 reviewer 重複(兩 chunk 檔案不相交),無 dedup、無 severity 分歧;7 條全數保留。無 strict-liability finding。

## Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 `codex` CLI,中性軸與對抗軸皆未啟動(0 findings;非「跑了沒結果」,是「沒跑」)。

## Opus 對 Codex 的複查結果

N-A —— Step 4.1 無輸入(Codex / Gemini 軸皆未啟動)。

## Codex 對 Opus 的複查結果(對稱化 4.2)

**Codex 複查 Opus 失敗 — 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(codex CLI 缺席,batch 未派出,非 JSON parse 失敗)。7 條全數視同 INCONCLUSIVE:

| Opus # | Opus reviewer | Opus title | Verdict | 原始 → 校正 severity | Codex evidence | 備註 |
| --- | --- | --- | --- | --- | --- | --- |
| TS1-1 | typescript-reviewer | verification §7 判準不符 | INCONCLUSIVE | MEDIUM→MEDIUM | — | orchestrator 第一手核對 App.tsx:114 / constants.ts:48 / storage.ts:63-66,機制成立;無 Codex 反證 |
| TS1-2 | typescript-reviewer | inline disable 非唯一 | INCONCLUSIVE | LOW→LOW | — | reviewer 附 base 層 grep 證據 |
| TS1-3 | typescript-reviewer | 🔴 分類敘述矛盾 | INCONCLUSIVE | LOW→LOW | — | reviewer 附逐 commit stat 證據 |
| TS1-4 | typescript-reviewer | dev console 標籤失準 | INCONCLUSIVE | LOW→LOW | — | reviewer 附 vite.config grep 證據 |
| TS2-1 | typescript-reviewer | useSignalSound 註解機制不成立 | INCONCLUSIVE | LOW→LOW | — | reviewer 以暫時測試實測兩種失效態 |
| TS2-2 | typescript-reviewer | GroupGridView pass-through | INCONCLUSIVE | LOW→LOW | — | reviewer 自評屬 spec 範圍內 |
| TS2-3 | typescript-reviewer | constants.ts import 位置 | INCONCLUSIVE | LOW→LOW | — | 純可讀性 |

## Step 4.3 補充複查

- 4.3a consensus baseline check:N-A(無 consensus finding —— 只有一個模型軸實際跑)。
- 4.3b lone finding 判斷:7 條全部 lone。「他軸為何漏」的解釋一致:其他軸(Codex ×2 / Gemini)**未執行**(工具缺席),不是走過同一份 diff 而沉默 —— 「多軸沉默」條件不成立,依 4.3b 第 2 / 3 項不構成降級理由;7 條維持 `effective_severity = original_severity`。無安全類 finding,severity-calibration 矩陣不適用。

## Action Items

**Severity calibration**:6c Refactor Intent Gate —— 本 PR 無「移除 / 削弱既有防護」類 finding(收斂反向:把裸奔加上防護),不適用。6d-1 hedge cap —— 7 條皆為肯定句且附第一手證據,無假設性措辭。6d-3 Must Fix 雙半條件 —— 無任何 finding 具「不修就壞會出貨的東西」:F-01 影響的是驗收文件(假 FAIL 風險)而非 runtime / 資料 / build,其餘為文件與註解一致性、pass-through、import 位置;故 Must Fix / Should Fix 皆空。未驗證前提閘:F-01 的機制鏈(module scope 執行序、warnRemove 獨立文案)由 orchestrator 第一手讀 file:line 核對,非僅 reviewer 自陳;F-05 的兩種失效態由 reviewer 實跑暫時測試;F-02 / F-03 / F-04 以 git / grep 第一手證據;拿掉未驗證論據後等級不變。Provenance cap:N-A。

**校準套用**:無作者校準檔(xu-min-yu.md 不存在)、本輪無套用。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

無(Opus 無 HIGH;4.2 全 INCONCLUSIVE 但無 HIGH 可升)。

### Nice to Have(可選優化)

- F-01(MEDIUM)verification §7 判準改寫 —— 建議在 user 執行 §7 真環境過目**之前**先改,避免對正確的 code 判假 FAIL。
- F-02(LOW)「唯一一處」→「第三處」,verification.md:124 與 storage.ts:26-27 同步。
- F-03(LOW)verification §1 分類敘述改為事實,不重寫歷史。
- F-04(LOW)去「dev」、14 → 15。
- F-05(LOW)改註解(預設)—— 或另拍板補 in-memory 覆寫(撞 spec §1 決定 6)。
- F-06(LOW)記 next-time:inline loadGroupName / persistGroupName。
- F-07(LOW)constants.ts import 歸位。

### 參考用(任一軸驗證為 REFUTED 或 OUT_OF_SCOPE)

無 —— 沒有任何軸產生 REFUTED / OUT_OF_SCOPE verdict(4.1 無輸入、4.2 未執行)。

## 審查工具比較 (qualitative)

- Opus(typescript-reviewer ×2)視角:context-aware;本輪 7 條中 4 條落在文件與 code 的一致性(靠跨檔追 module 執行序、逐 commit stat、base 層 grep 才抓得到),3 條落在 code 註解 / 結構;兩支各自跑了 mutation 與完整 gate(tsc / eslint / vitest 2782)背書 REVIEWED_NO_ISSUES。
- Codex 中性 / 對抗視角:未執行。
- Gemini 視角:未執行。
- 兩者重疊率:N-A(單軸)。
- Opus 複查 Codex(4.1):N-A。Codex 複查 Opus(4.2):INCONCLUSIVE 7 / CONFIRMED 0 / REFUTED 0 / PARTIAL 0 / OUT_OF_SCOPE 0 —— REFUTED 率不可計,**本輪 Opus first-pass 的 over-flag 程度沒有 cross-axis 量測**,user 讀 Nice to Have 時請自帶折扣。
- 對抗式第三軸增益:N-A。

## Review continuity（產報告前重驗）

產報告前重抓 `gh pr view 106 --json headRefOid,baseRefOid,state`:headRefOid = 06484a79…(同 reviewed)、baseRefOid = 7ad28906…(同 reviewed)、state = MERGED、headRepository.id = R_kgDOTsITBg。`source_continuity=CURRENT`、`base_changed=false`、`review_context_changed=false`。`origin/master` 已前進至 892135aa(14 commits,含本 PR 的 rebase-merge 產物與後續 review 文件),不影響 PR 記錄的 destination SHA。

## 沒做的部分（結案對帳）

| 項目 | 狀態 | 理由 / 證據 |
| --- | --- | --- |
| Codex 中性軸 | N-A | 本機無 `codex` CLI(`command -v codex` 無);未起、未 retry、無 fallback 可走 |
| Codex 對抗軸 | N-A | 同上;preset 一律含對抗但工具缺席 |
| Gemini Flash 永久軸 | N-A | 本機無 `agy` CLI;未向 user 詢問 Pro opt-in(工具缺席時提問無意義) |
| Gemini Pro opt-in 軸 | N-A | 同上 |
| Step 2.9 blast radius | N-A | 本機無 `sem`;script exit 0 空輸出 → 跳過(header 已標「空輸出跳過」) |
| Step 2.65 C4 formal-spec lane | SKIPPED | `C4_AUTHORITY_PATH_NOT_ALLOWED`(spec 在 `.claude/mod/`,reducer 只認 `openspec/`);另 Windows 平台 `dispatch-envelope` 無法派工,本輪未走到 |
| Step 4.1 | N-A | 無非 CC finding |
| Step 4.2 Codex 驗 Opus | FAIL | Codex 缺席;7 條全 INCONCLUSIVE,**本報告零 cross-axis 證據** |
| Step 4.3a | N-A | 無 consensus |
| security-reviewer | N-A | 未觸發(無 auth / secret / request body / session / RBAC 面) |
| Reviewer observed model | 未取得 | Agent tool 回傳無 runtime model;requested=opus 來自 frontmatter,observed 記 UNAVAILABLE |
| Quota snapshot | 未取 | 未取 dashboard snapshot(Gemini 軸未跑) |
| 未驗證前提 | 無 | 7 條 finding 的支點皆有第一手證據(見 Action Items 未驗證前提閘) |
| Self-Verify | PASS | skill-verify-auditor(frontmatter model=sonnet)以固定 R1–R10 rubric 稽查本草稿全文:R1–R10 各一行 PASS、`VERDICT: COMPLIANT`,格式與 FAIL 集合一致性檢查通過;零修正,未派第二次稽查 |
