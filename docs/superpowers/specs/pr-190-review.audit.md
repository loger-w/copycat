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

## Spec 依據

- 偵測到 spec:`.claude/mod/ladder-market-fill-marker/change-spec.md`(路徑符合 `*-spec.md`)。Goals:閃電梯 PriceLadder「我的單」的已成交量統一以 fills 表逐筆成交價落格,限價 / 市價同一把尺、與成本線同尺;殘量與 seqs(刪單入口)留委託價列;可用 fills(qty>0 / price>0 / 側 B,S / 非 excludeUnit)總量恰等於 `filled_qty` 才用成交價,否則整張退回委託價。Non-goals / 已知殘餘(§4):成交前 ~0.1 s 無標記;fills 載入前一拍位移;`0(0)` 畫面態知情接受;成本 / 打平線不動;StkfutLadder 不傳 fills、FuturesLadder 不動。白名單 W1–W8(§3)。
- **⚠️ spec 作者 = PR 作者**(`git log --format=%an` 於 spec 路徑 = Loger,與 PR 作者同人;out-of-scope 判定以此 spec 為據時,注意作者自寫 spec 的利益重疊)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_IMPLEMENTATION_BINDING_CLAUSE`(spec 為非正式 change-spec / SC 表,無 MUST / SHALL / INVARIANT 級可綁定條款)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool call count=N-A(未派);0 clauses / 0 findings / 0 observations / 0 invalidated。
- Author calibration(Step 2.2):無作者校準檔(`loger-w.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

provenance: N-A(base = master,9 檔全 authored)。

| 檔案 | 類型 | 說明 |
|---|---|---|
| `frontend/src/lib/ladder-lots.ts` | 修改 | `aggregateLots` 新增選傳 `fills`;可用 fills 總量恰等於 `filled_qty` 才逐筆落成交價列,否則退回委託價;`groupUsableFillsBySeq` / `limitPriceOf`(`price <= 0` 視為無委託價)/ `addToLot` 三支 helper;檔頭與 `LadderLot` docstring 回校 |
| `frontend/src/lib/ladder-lots.test.ts` | 測試 | 既有「市價 price=null 全排除」改述為「無 fills 時不上梯」+ price=0 幽靈 entry 斷言;新增市價節 6 案、限價節 7 案(含總量不等雙向 / 異常列三種) |
| `frontend/src/components/stock/PriceLadder.tsx` | 修改 | 接 `useCapitalFills()`,`aggregateLots` 第五參數傳 fills(接線收成兩行避 react-doctor no-giant-component) |
| `frontend/src/components/stock/PriceLadder.test.tsx` | 測試 | mock 補 `/api/capital/fills` 預設路由;新增「市價買全成交(fills 兩價)→ 兩列各 `(1)` 徽章」案 |
| `frontend/src/lib/fill-marks.ts` | 文件 | 分工 docstring 改述為限價 + 市價都吃 fills |
| `frontend/src/lib/futures-ladder.ts` | 文件 | 與 ladder-lots 互指的一致性敘述補「filled 落格」第三處差異 |
| `.claude/mod/ladder-market-fill-marker/change-spec.md` | 新增 | spec(含追加拍板、SC、白名單、backward compat) |
| `.claude/mod/ladder-market-fill-marker/verification.md` | 新增 | gate 證據與紅→綠紀錄 |
| `.claude/mod/ladder-market-fill-marker/code-review-round-1.json` | 新增 | 分支自身 two-axis round-1(14 條)處置 |

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

#### #5 五個位置參數讀起來吃力,但全 repo 同型八支都這樣,不算缺陷

**File**: `frontend/src/lib/ladder-lots.ts`
**Line**: 90-96

**Comment**:
```
不是 PR 缺陷,參考用。aggregateLots(orders, code, ymdWindow(...), "股", fills) 第 3/4/5
個引數確實要翻 doc 才知道是什麼,但 lib/ 底下 ≥5 個位置參數的函式有八支(positionEcon /
buildIndexOverlayLines / moveToGroup …)全都這樣寫,姊妹 splitMyLots 也是位置參數;型別
已擋掉多數錯序(Set / 陣列),只剩 key 與 excludeUnit 兩個 string 可互換。日後真要收成
options 物件,連 splitMyLots 一起改,不單改一支。
```

## CC 主軸原始 findings(first-pass, context-aware)

### Section A — findings(typescript-reviewer,逐字)

#### F-1 測試檔開頭還寫著「限價單路徑不看 fills」,下一個 describe 就在打自己的臉
- severity: MEDIUM
- file: `frontend/src/lib/ladder-lots.test.ts` line 199-200
- anchor: `/** 市價單沒有委託價可當梯列鍵 → 已成交量改由 fills 表(逐筆真實成交價)落格;` / ` *  限價單路徑不看 fills(白名單 W1)。 */`
- body: 第二輪拍板後限價單也吃 fills(`ladder-lots.ts:120-127` 不分市價 / 限價),下一個 describe 正是「限價單:已成交量同樣以 fills 成交價落格」。這段是 5bf556ad 首輪留下、d1aa60a8 未回校的殘句;spec §3 的 W1 已改寫成「已成交量在成交價 = 委託價時畫面零差」。測試檔的段落 doc 是後人判斷「這一節在釘什麼」的唯一線索,留著會讓下一個人以為限價路徑有一道不存在的隔離。建議改述為「市價單只有這條路;限價單同尺,見下一節」。
- spec-ref: §3 W1「已成交量在『成交價 = 委託價』…時畫面零差;**不傳 fills 時整套算式一字不改**」
- mechanism-traced: 讀 `aggregateLots` 主迴圈,`fillsExplainAll` 分支在 `limitPriceOf` 之前、對所有單一體適用。

#### F-2 `?? buy` 這個 fallback 走不到,但真走到就會把賣單畫在買側
- severity: LOW
- file: `frontend/src/lib/ladder-lots.ts` line 124-125
- anchor: `        // 側別已在 groupUsableFillsBySeq 過濾為 B/S,sideOf 不會回 null` / `        addToLot(sideOf(f.buy_sell) ?? buy, Math.round(f.price * 1000), { qty: 0, filled: f.qty });`
- body: 不可達分支 + 需要一行 WHAT 註解解釋才讀得懂,而它選的預設(買側)是**靜默畫錯邊**,不是不畫。型別上可以整段消失:`groupUsableFillsBySeq` 改回 `Map<string, { side: "B" | "S"; price: number; qty: number }[]>`(過濾當下就窄化),呼叫端 `f.side === "B" ? buy : sell` 沒有 null 可 fallback,註解也不必寫。順帶:檔頭 doc 第 2 條「對 `buy_sell` 非 B/S 的單**整筆跳過**」現在只靠後端 `store.py::_append_fill_locked` 寫 `a.buy_sell or ""` 這條間接保證,本檔已不再自己擋。
- mechanism-traced: `groupUsableFillsBySeq:156` 已排除非 B/S;`CapitalFill.buy_sell` 型別是 `string`,不會被那道 if 窄化,`?? buy` 是型別層的權宜。

#### F-3 測試名承諾「他檔的 fills」,但 code 與測試都沒有這一關
- severity: LOW
- file: `frontend/src/lib/ladder-lots.test.ts` line 252-256
- anchor: `  it("fills 無同 seq 成交 / 他檔的 fills → 零 entry(未成交殘量沒有價位可掛)", () => {`
- body: 案內只有 `fill({ seq_no: "OTHER" })`(同股號、不同 seq),沒有任何 `stock_no` 不同的 fill;而 `groupUsableFillsBySeq` 從頭到尾不讀 `f.stock_no` / `f.code`,所以「他檔」這一關實際上不存在,靠的是後端 seq 全域唯一。建議改名為「fills 無同 seq 成交」,或補一筆 `fill({ stock_no: "2317", seq_no: "M1" })` 明寫「seq 唯一 → 不另設股號閘」的知情立場。
- search-proof: `grep -n "stock_no\|f.code" frontend/src/lib/ladder-lots.ts` → 只有 `o.stock_no !== key`(單那一側);對照 `lib/fill-marks.ts:87` `code: f.code ?? f.stock_no` 有 code 分組。
- mechanism-traced: `copycat/capital/store.py:144` `self._orders: dict[str, _Agg]` 以 seq_no 為鍵、`_append_fill_locked` 寫 `seq_no=a.seq_no` → 目前不可能跨股撞號,故只是命名 / 覆蓋問題,不是活的 bug。

#### F-4 「每 render 重算:純算術」這句話已經不準了
- severity: LOW
- file: `frontend/src/components/stock/PriceLadder.tsx` line 241-243
- anchor: `  // (張梯混進零股量級差一千倍,其刪單入口仍在委託列表)。每 render 重算:純算術。` / `  const lots = aggregateLots(ordersData?.orders, code, ymdWindow(new Date(), [0]), "股", fills);`
- body: 這一行現在每次 render 會把**全帳戶當日 fills**(所有股號 / 期貨列都在同一份 `/api/capital/fills`)掃一遍並配置一個 `Map<string, CapitalFill[]>`,而 PriceLadder 隨報價逐 tick 重繪。量級仍小(散戶單日成交數十筆),不是效能問題,但註解說的「純算術」與實際的「每 tick 一次 O(全帳戶 fills) 配置」不同。最省事的處置是回校註解;想順手省的話 `aggregateLots` 可在 `orders` 為空時早退(`ladder-lots.ts:113` 在迴圈前無條件呼叫)。

#### F-5 五個位置參數,呼叫端讀不出 `"股"` 和 `fills` 是誰
- severity: LOW(參考用)
- file: `frontend/src/lib/ladder-lots.ts` line 90-96
- anchor: `export function aggregateLots(`
- body: 本輪把第五個 optional 位置參數加上去後,呼叫端長成 `aggregateLots(orders, code, ymdWindow(...), "股", fills)` —— 第 3/4/5 個引數都要回頭翻 doc 才知道是日期界 / 零股閘 / 成交表。round-1 已把內部 `bump` 收成具名物件(std F-07),公開介面同一個病沒收。只有兩個呼叫端,現在改成 `aggregateLots(orders, key, { filledDates, excludeUnit, fills })` 成本仍低;不改也可接受。

### Section B — per-file accounting (9/9)

| 檔案 | 狀態 |
|---|---|
| `frontend/src/lib/ladder-lots.ts` | findings F-2 / F-5 |
| `frontend/src/lib/ladder-lots.test.ts` | findings F-1 / F-3 |
| `frontend/src/components/stock/PriceLadder.tsx` | finding F-4 |
| `frontend/src/components/stock/PriceLadder.test.tsx` | REVIEWED_NO_ISSUES |
| `frontend/src/lib/fill-marks.ts` | REVIEWED_NO_ISSUES |
| `frontend/src/lib/futures-ladder.ts` | REVIEWED_NO_ISSUES |
| `.claude/mod/ladder-market-fill-marker/change-spec.md` | REVIEWED_NO_ISSUES |
| `.claude/mod/ladder-market-fill-marker/verification.md` | REVIEWED_NO_ISSUES |
| `.claude/mod/ladder-market-fill-marker/code-review-round-1.json` | REVIEWED_NO_ISSUES |

reviewer 自陳:review worktree `frontend/` 無 `node_modules`,未實跑 vitest / tsc / eslint,型別與測試綠燈以 PR 內 `verification.md` 的紀錄為憑,本輪為純讀 code 判斷(主 session 於出貨前已實跑:vitest 2980 綠 / tsc 0 / eslint 0 / build 0,見該檔)。

## Codex 原始 findings

N-A —— user 明示本輪不跑 Codex(中性與對抗式兩軸皆停用)。

## Gemini 原始 findings

N-A —— user 明示本輪不跑 Gemini(Flash / Pro 皆停用)。

## CC 對非 CC 軸的複查結果(Step 4.1)

N-A —— 無非 CC finding。

## 內部複查結果(Step 4.2 之替代;同軸 code-reviewer、非跨軸證據)

批次一輪、5/5 回 verdict、ID 集合精確等於輸入、每列 verdict / corrected_severity / severity_reason / evidence 四欄齊。**注意:這是同軸(CC)內部複查,不構成跨軸證據**;Must Fix 候選來源中的「Codex CONFIRMED verifications of Opus findings」本輪不存在。

| # | reviewer | title | Verdict | 原始 → 校正 severity | 內部複查 evidence | 修法假設核 | 備註 |
|---|---|---|---|---|---|---|---|
| F-1 | typescript-reviewer | 測試檔 doc 仍寫限價不看 fills | CONFIRMED | MED→LOW | `ladder-lots.test.ts:199-200` 現字面「限價單路徑不看 fills(白名單 W1)」;`git blame -L 198,201` 兩行出自 5bf556ad(只做市價那輪),d1aa60a8 只改 :275 之後新節;矛盾對象同檔 :275 describe、:290 案、`ladder-lots.ts:76-89` doc;`change-spec.md:42` W1 已改述;grep「不看 fills」全 frontend/src 僅此一處 | 成立:改述兩行 docstring,零行為、零測試改動,不牽動 W1–W8 | 4.3b:單軸 N-A;同檔兩句字面互斥 + blame 時序,不依賴跨檔推理,單軸可證 |
| F-2 | typescript-reviewer | `?? buy` 不可達 fallback | CONFIRMED | LOW→LOW | `ladder-lots.ts:124-125` 輸入已在 :156 濾過 → 不可達;不窄化原因 `types.ts:152 CapitalFill.buy_sell: string` + `sideOf` 簽章 :100-101 `(bs: string \| null)`;檔頭 doc 第 2 條在 fills 路徑只剩 `store.py:273 buy_sell=a.buy_sell or ""` 間接保證(空字串被 :156 濾 → fillsExplainAll 假 → 不繞過 :130-131);專案立場基線 `WatchlistSidebar.tsx:333-334` 曾據「不可達防禦 = 無覆蓋死碼」刪同型 guard | 半成立:`groupUsableFillsBySeq` module-private、唯一呼叫 :113、消費端只用 qty/price/buy_sell → 窄化可編譯;但光改回傳型別不消 `?? buy`(sideOf 仍回 `Map \| null`),呼叫點要改 `f.side === "B" ? buy : sell` | 4.3b:單軸 N-A;不可達性由字面型別直接判定;屬「未來的守門」非現有缺陷 |
| F-3 | typescript-reviewer | 案名「他檔的 fills」無對應輸入 | CONFIRMED | LOW→LOW | `ladder-lots.test.ts:252-256` 案內只有 `fill({ seq_no: "OTHER" })`,fixture :51-65 stock_no / code 預設 2330;`groupUsableFillsBySeq:149-163` 不讀 stock_no / code,對照 `fill-marks.ts:158 if (f.stock_no !== key) continue` 刻意不同;同檔 :111 的「他檔」是 orders 側且有實測;緩解 `store.py:194-197` seq_no 全域鍵 | 改名成立(最省);補案要寫成「同 seq 就算數、不看股號」,寫成排除會紅(需先加 `f.stock_no !== key` 閘 = 行為改動) | 4.3b:單軸 N-A;案名與輸入的落差是純字面比對 |
| F-4 | typescript-reviewer | 「純算術」註解漏記全帳戶 fills 掃描 | PARTIAL | LOW→LOW | 事實成立:`ladder-lots.ts:113` 在 orders 迴圈前呼叫 `groupUsableFillsBySeq`,掃整份 fills(`capital_api.py:264-274` 回整帳戶錨定交易日全部成交、無股號過濾、無筆數上限)並配 Map;反證:`FuturesLadder.tsx:108` 對 `splitMyLots` 同句「每 render 重算,純算術」而 `futures-ladder.ts:63` 也建 Map + 迴圈 → 本 repo「純算術」不等於零配置;真差異 = `StockChart.tsx:83-86` / `GroupGridView.tsx:355` 對同份 fills 都有 useMemo,只有本處逐 tick 裸跑 | 兩個建議都成立:註解回校零風險;orders 空早退語意等價(`for (const o of orders ?? [])` 零圈、key null guard 在 :99 更早);真要省是整個 aggregateLots 包 useMemo 與姊妹對齊 | 4.3b:單軸 N-A;「已不準」斷語被同語慣例反證 → PARTIAL,成立的只有「漏記新事實」半句 |
| F-5 | typescript-reviewer | 五個位置參數 | REFUTED | LOW→LOW | 基線:`frontend/src/lib/*.ts` 多行簽章 ≥5 位置參數者 8 支(6 參數 4 支:`index-overlay-lines.ts::buildIndexOverlayLines` / `ladder-position.ts::positionEcon` / `list-drag.ts::dropTargetFromPointer` / `watchlist-model.ts::moveToGroup`;5 參數 `stock-accum.ts::foldVp` / `stock-intraday-svg.ts::yieldToObstacles` 等)全未旗標;呼叫端 prod 2 處(`PriceLadder.tsx:243` 5 引數 / `StkfutLadder.tsx:126-130` 3 引數)+ 測試 ~25 處;型別已擋多數錯序,唯 `key: string \| null` 與 `excludeUnit?: string` 可互換 | 技術上成立但成本效益不成立:round-1 std F-07 收的是零外部呼叫點的私有 helper;公開 API + 25 測試呼叫點是另一量級,且姊妹 `splitMyLots(orders, contract, filledDates)` 維持位置參數,單改一支反而形狀分歧 | 4.3b:不因單軸降級,是被基線 grep 直接反證;finding 自陳參考用 |

### Step 4.3a consensus baseline check

N-A —— 本輪單軸,無 consensus finding。

### Step 4.3b lone-finding 判斷

本輪只有 CC 一軸,五條全為 lone finding,「他軸為何漏」在單軸情境下無意義(N-A);判斷改以「該條能否不依賴跨軸就獨立成立」為準,結論列於上表備註欄:F-1 / F-2 / F-3 由同檔字面 + blame / 型別直接判定(成立);F-4 半句成立(PARTIAL);F-5 被基線反證(REFUTED)。`effective_severity` 一律取 `corrected_severity`(全 LOW);無安全類 finding,severity-calibration 矩陣不適用。

## Action Items

**Severity calibration**:6c Refactor Intent Gate N-A(本 PR 無「移除 / 削弱既有防護」類 finding;F-2 是新加的不可達 fallback,不是拿掉守門)。6d-1 hedge cap:F-2「哪天有人拿掉過濾」為假設性措辭 → ≤ Should Fix(實際落 Nice)。6d-3 Must Fix 雙半條件:五條皆無 user-visible 重現路徑與 release-blocking 後果 → 零 Must / 零 Should。Provenance cap N-A(base = master)。

**校準套用**:無作者校準檔(`loger-w.md` 不存在)、本輪無套用。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

無。

### Nice to Have(可選優化)

- F-01 `ladder-lots.test.ts:199-200` describe doc 改述(限價單同尺,見下一節)。
- F-02 `ladder-lots.ts:124-125` `groupUsableFillsBySeq` 回窄化 `{side:"B"|"S"; price; qty}[]` + 呼叫點 `f.side === "B" ? buy : sell`,刪 `?? buy` 與那行註解;檔頭 doc 第 2 條補一句「fills 路徑的側別由 groupUsableFillsBySeq 過濾」。
- F-03 `ladder-lots.test.ts:252` 案名改「fills 無同 seq 成交 → 零 entry」或補一筆同 seq 他股 fill 並斷言採計(明寫依賴後端 seq 全域唯一)。
- F-04 `PriceLadder.tsx:242` 註解補「含掃一遍全帳戶當日 fills」;可選:`aggregateLots` 包 `useMemo` 與 `StockChart` / `GroupGridView` 對齊。

### 參考用(內部複查 REFUTED / OUT_OF_SCOPE)

- F-05 CC[typescript-reviewer] 擔心 `aggregateLots` 五個位置參數可讀性 → 內部複查於 `frontend/src/lib/*.ts` 找到同型 8 支未旗標、姊妹 `splitMyLots` 同形狀 → 使用者自行判斷;若日後收斂 options 物件應兩支一起改。

## 審查工具比較 (qualitative)

- CC 視角(context-aware):五條全是「文件 / 命名 / 型別收斂 / 效能預算註解」類,無 runtime 缺陷 —— 與 PR 自身分支上的 two-axis round-1(14 條)已把 P2 級的 zero-unit 閘、兩支 query 不同步膨脹、price 0 幽靈格等收掉相符;本輪抓到的是 round-1 收修後殘留的敘述漂移(F-1 尤其:第二輪擴 scope 時第一輪的 docstring 沒回校)。
- Codex 中性 / 對抗式:N-A(user 停用),無重疊率可算。
- Gemini:N-A(user 停用)。
- 內部複查結果分佈(4.2 替代、同軸):CONFIRMED 3 / PARTIAL 1 / REFUTED 1 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0;REFUTED 率 20%,校正後五條全 LOW(F-1 MED→LOW)。
- 對抗式第三軸增益:N-A。
- React-doctor 機械軸:0 新引入(PR 出貨前主 session 即因 no-giant-component 新報而把接線收成兩行,本輪確認 changed scope 零新問題)。

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
