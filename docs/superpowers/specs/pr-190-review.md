# PR #190 Code Review 比較報告 · SHA 8a0190fd
**Report projection schema**: 1

**PR**: [loger-w/copycat#190](https://github.com/loger-w/copycat/pull/190)
**標題**: fix(frontend): 閃電梯已成交量統一以 fills 成交價落格(市價單終於上梯;限價同一把尺)
**作者**: loger-w
**分支**: `mod/ladder-market-fill-marker` → `master`
**變更**: 9 檔案, +445 / -26
**審查日期**: 2026-09-05
**PR 狀態**: MERGED(post-merge 審查;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨)
**Review input basis**: source repo id `R_kgDOTsITBg` + source SHA `8a0190fd0f7387de9d46bcd7540aeeca8713ec1b`;destination repo id `R_kgDOTsITBg` + destination SHA `0b73e5120b17c20dd329ef98e765a944800dd359`;`input_binding: verified`(`refs/pull/190/head` FETCH_HEAD 逐字等於 headRefOid、worktree HEAD 同值;base commit 本地可解析)
**Review continuity**: `source_continuity=CURRENT`(產報告前重抓 headRefOid `8a0190fd` 未變;分支已隨 rebase merge 刪除);`base_changed=true`(origin/master 自 `0b73e512` 前進至 `cc693acb`,內容 = 本 PR 的 rebase merge 8 筆,其後零新 commit);`review_context_changed=false`(head 未動,base 前進即本 PR 自身落地)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用)** + Codex 對抗式 **N-A(user 明示停用)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=typescript-reviewer(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=9 → covered 3 / no-issues 6 / skipped 0 / **missed 0**(chunked: 否,6 source 檔 / 471 diff 行低於 15 檔 or 800 行門檻)
**定位 (ENH-B)**: anchored exact 5 / ambiguous 0 / **FAILED 0**(五條 anchor 皆在 worktree 以 grep 逐字唯一命中:ladder-lots.test.ts:200 / ladder-lots.ts:125 / ladder-lots.test.ts:252 / PriceLadder.tsx:242 / ladder-lots.ts:90)
**React-doctor (2.97)**: 未引入新問題(`--scope changed --base 0b73e512 --json`:newCount 0 / fixedCount 0 / baseTotalCount 0,changedFileCount 6)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_IMPLEMENTATION_BINDING_CLAUSE)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 base `0b73e512` 執行、exit 0、零輸出)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(typescript-reviewer)PASS(5 findings + 9/9 per-file accounting)/ security-reviewer N-A(無 trigger 面:純前端顯示邏輯,未動 auth / cookie / 使用者輸入處理)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示「不用 Codex」)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示「不用 Gemini」)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(5/5 verdict 齊、ID 集合精確相等、每列四欄齊)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-190`
**worktree HEAD**: `8a0190fd0f7387de9d46bcd7540aeeca8713ec1b`

**Report generation**: sha256:b1660ef140b5d70f336b72e9490849b4515cbea73fab9d1dfcc089aac5caa37d

---
## [完整證據副檔](pr-190-review.audit.md)
### finding_uid 索引
[18d5d89190c63164ed00](pr-190-review.audit.md#發現總覽) · [b713f3d36be1349d4540](pr-190-review.audit.md#發現總覽) · [8944a4b350fe23200cb0](pr-190-review.audit.md#發現總覽) · [840762cd964876346012](pr-190-review.audit.md#發現總覽) · [f2a6816409db9cb1c84f](pr-190-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `ladder-lots.test.ts:199-200` 市價節 describe 前的 doc 仍寫「限價單路徑不看 fills(白名單 W1)」,與同檔下一節「限價單:已成交量同樣以 fills 成交價落格」字面互斥 | MED | CONFIRMED(降 LOW:純測試檔 docstring;blame 兩行出自首輪 5bf556ad、擴及限價的 d1aa60a8 未回校;spec W1 已改述;grep「不看 fills」全 frontend/src 僅此一處) | Nice to Have | `auto-fix` | 改述兩行 docstring,零行為 |
| F-02 | `ladder-lots.ts:125` 的 `sideOf(f.buy_sell) ?? buy` 是不可達 fallback(:156 已濾非 B/S),但一旦可達會把賣單成交靜默畫在買側;檔頭 doc「非 B/S 整筆跳過」在 fills 路徑只剩後端 `store.py:273` 間接保證 | LOW | CONFIRMED(不可達性由 :156 + `types.ts:152 buy_sell: string` 字面判定;專案立場基線 `WatchlistSidebar.tsx:333-334` 曾據「不可達防禦 = 無覆蓋死碼」刪同型 guard;修法需多一步:光窄化回傳型別不消 fallback,呼叫點要改 `f.side === "B" ? buy : sell`) | Nice to Have | `auto-fix` | 窄化 helper 輸出型別 + 呼叫點三元,兩行 |
| F-03 | `ladder-lots.test.ts:252` 案名寫「他檔的 fills → 零 entry」,但案內只有同股號不同 seq 的 fill,`groupUsableFillsBySeq` 不讀 `stock_no` / `code`,「他檔」這一關靠後端 seq 全域唯一 | LOW | CONFIRMED(fixture 預設 stock_no 2330;姊妹 `fill-marks.ts:158` 有股號閘、本檔刻意沒有;後端 `store.py:194-197` 以 seq_no 為全域鍵故現況不誤計;補案方向要寫成「同 seq 就算數、不看股號」否則會紅) | Nice to Have | `auto-fix` | 案名改述或補一筆明寫立場 |
| F-04 | `PriceLadder.tsx:242` 註解「每 render 重算:純算術」漏記新事實:每 tick 掃整帳戶當日 fills(`/api/capital/fills` 無股號過濾)並配置一個 Map | LOW | PARTIAL(事實成立但「已不準」被同語慣例反證:`FuturesLadder.tsx:108` 對 `splitMyLots` 同樣寫「純算術」而 `futures-ladder.ts:63` 也建 Map;真正差異 = 同份 fills 的另兩個消費者 `StockChart.tsx:83-86` / `GroupGridView.tsx:355` 都有 useMemo、只有本處逐 tick 裸跑) | Nice to Have | `auto-fix` | 註解補一句;要省再包 useMemo 與姊妹對齊 |
| F-05 | `aggregateLots` 五個位置參數,呼叫端 `(orders, code, ymdWindow(...), "股", fills)` 讀不出第 3/4/5 是誰;建議 options 物件 | LOW | REFUTED(基線:`frontend/src/lib/*.ts` ≥5 位置參數者 8 支皆未旗標,無材質差異;呼叫點 2 prod + ~25 測試;姊妹 `splitMyLots` 維持位置參數,單改一支反而形狀分歧;型別已擋多數錯序,唯 `key` 與 `excludeUnit` 兩個 string 可互換) | 參考用 | `no-op` | 非缺陷;日後要收斂應連 splitMyLots 一起 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 18d5d89190c63164ed00 action=auto-fix
F-02 finding_uid: b713f3d36be1349d4540 action=auto-fix
F-03 finding_uid: 8944a4b350fe23200cb0 action=auto-fix
F-04 finding_uid: 840762cd964876346012 action=auto-fix
F-05 finding_uid: f2a6816409db9cb1c84f action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 這段 doc 還說限價單不看 fills,下一節就在測限價單吃 fills
**File**: `frontend/src/lib/ladder-lots.test.ts`
**Line**: 199-200

**Comment**:
```
「限價單路徑不看 fills(白名單 W1)」是第一輪只做市價單時寫的,第二輪把限價單也統一之後
沒回頭改 —— 同檔 :275 那個 describe 就叫「限價單:已成交量同樣以 fills 成交價落格」,
兩句放一起是互斥的,spec 的 W1 也已經改成「成交價 = 委託價時畫面零差」。
改述成:「市價單沒有委託價可當梯列鍵,只能靠 fills;限價單同尺,見下一節」就好。
```
#### #2 `?? buy` 走不到,但真走到會把賣單畫在買側
**File**: `frontend/src/lib/ladder-lots.ts`
**Line**: 124-125

**Comment**:
```
sideOf(f.buy_sell) ?? buy 這個 fallback 現在不可達(groupUsableFillsBySeq :156 已經把
非 B/S 的列濾掉),但它選的預設是「畫在買側」—— 哪天有人拿掉 :156 那道過濾,賣單成交會
靜默跑到買方那一欄,測試不會紅。上面那行「側別已過濾,不會回 null」的註解正是型別沒窄化
的補丁。
最省事的改法:groupUsableFillsBySeq 回 { side: "B" | "S"; price; qty }[](過濾當下就
窄化),這裡改 f.side === "B" ? buy : sell,null 分支和那行註解一起消失。注意光改回傳型別
不夠 —— sideOf 的參數還是 string | null、照樣回 Map | null,呼叫點要一起換。
```
#### #3 這個案名說有測「他檔的 fills」,其實沒有那一關
**File**: `frontend/src/lib/ladder-lots.test.ts`
**Line**: 252-256

**Comment**:
```
案內只有 fill({ seq_no: "OTHER" })—— 同股號、不同 seq;fixture 的 stock_no 預設就是
2330。而 groupUsableFillsBySeq 從頭到尾不讀 stock_no / code,「他檔」靠的是後端 seq 全域
唯一(store.py 以 seq_no 當鍵),不是這裡擋的。案名寫得比覆蓋大,下一個人會以為有守門。
兩條路挑一:改名成「fills 無同 seq 成交 → 零 entry」;或補一筆
fill({ stock_no: "2317", seq_no: "M1" }) 並斷言「同 seq 就算數、不看股號」—— 注意方向
要寫成採計,寫成排除會直接紅(現行 code 沒有股號閘)。
```
#### #4 「每 render 重算:純算術」現在每 tick 會掃整帳戶的 fills
**File**: `frontend/src/components/stock/PriceLadder.tsx`
**Line**: 241-243

**Comment**:
```
這行現在多做一件事:aggregateLots 在 orders 迴圈前無條件把整份 /api/capital/fills(全帳戶
當日成交、無股號過濾)掃一遍並配一個 Map,而 PriceLadder 隨報價逐 tick 重繪。量級小(散戶
單日數十筆)不是效能問題,FuturesLadder 對 splitMyLots 也用同一句「純算術」—— 所以不算寫
錯,只是漏了新事實。註解補一句「含掃一遍全帳戶 fills」即可;真要省,同份 fills 的另外兩個
消費者(StockChart / GroupGridView)都包了 useMemo,這裡對齊就好。
```
## 沒做的部分（結案對帳）
- Codex 中性軸:N-A —— user 明示「不用 Gemini 跟 Codex」,依 per-PR override 停用,未起軸、未 retry。
- Codex 對抗式軸:N-A —— 同上。
- Gemini Flash 軸:N-A —— user 明示停用。Gemini Pro:N-A(同上;Step 2.96 問過、user 答覆為兩軸皆不跑)。
- Step 2.98 Codex preset 詢問:問過,user 答覆為停用 Codex → N-A。
- Cross-axis verification 4.1:N-A(無非 CC finding)。4.2:以同軸 code-reviewer 內部複查代替(PASS,5/5),**非跨軸證據** —— 五條的 CONFIRMED 全來自同一模型家族,user 讀 Nice to Have 時應據此下調權重。
- Blast radius(2.9):PASS(有跑)但空輸出跳過。
- React-doctor(2.97):PASS,未引入新問題(newCount 0)。
- Formal spec traceability(2.65):SKIPPED (C4_NO_IMPLEMENTATION_BINDING_CLAUSE);spec-compliance-reviewer 未派。
- Author calibration(2.2):無檔、本輪無套用。
- Reviewer 未實跑測試 / 型別:review worktree 無 `node_modules`,typescript-reviewer 純讀 code;綠燈證據引自 PR 內 `verification.md`(主 session 出貨前實跑)。
- 未驗前提(集中揭露):F-4 的「PriceLadder 隨報價逐 tick 重繪」為 reviewer 讀 code 推論(未量測 render 頻率);F-2 的「未來有人拿掉 :156 過濾」為假設情境(已依 6d-1 cap)。其餘 finding 的修法假設由內部複查逐條驗過(F-2 修法需多一步、F-3 補案方向已更正)。
- 真環境(PR 自身 SC-5):本 PR 出貨時即標「未驗,週六 prod 關著」,本 review 亦未驗;判準留下一交易日 user 過目(見 PR body 試用指引)。
- Self-Verify:已執行(`skill-verify-auditor`,requested=opus / observed=UNAVAILABLE;唯讀、只讀本草稿)。結果 R1–R10 全 PASS、`VERDICT: COMPLIANT`,輸出格式完整(十行 + 一行 verdict、順序正確、無 FAIL)→ 零修正,直接發布。
