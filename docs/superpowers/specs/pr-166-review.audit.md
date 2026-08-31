# PR #166 Code Review 比較報告 · SHA b43fa716

**Report projection schema**: 1

**PR**: [loger-w/copycat#166](https://github.com/loger-w/copycat/pull/166)
**標題**: refactor(frontend,server): daytrade_sell 散點比較收斂 KIND_TRAITS 特性表(next-time L54,F-09)
**作者**: loger-w
**分支**: `refactor/daytrade-sell-kind-table` → `master`(PR 已 MERGED,rebase merge)
**變更**: 8 檔案, +75 / -19
**審查日期**: 2026-08-31
**Review input basis**: source repo = loger-w/copycat;source SHA `b43fa71693edb63ee6dcceea948cdf856b88419c`;destination SHA `ca929f6b1464fbd5e873aef0232707bc38edfb41`(diff 以 merge-base `7d121a02` three-dot 計,與 PR 檔案清單逐檔一致);`input_binding: verified`(worktree HEAD 實測 == source SHA)
**Review continuity**: `source_continuity=CURRENT`(已 MERGED,head 不可變);`base_changed=true`(master 已前進,合併後正常演進);`review_context_changed=false`
**審查工具**: CC(claude-fable-5 orchestrator)+ CC reviewer agents(typescript-reviewer first-pass + code-reviewer 同軸複查)。**Codex 中性 / Codex 對抗 / Gemini Flash / Gemini Pro 四軸本機不可用**(`codex` / `agy` CLI 不存在)—— CC 單軸 + 同軸 fresh-context 複查,非 cross-axis,判讀請計入此限制。
**Reviewer model 記錄規則**: 上一行只描述工具組合;實際身分以下一行為準。
**Reviewer models**: orchestrator=claude-fable-5;typescript-reviewer requested=opus / observed=UNAVAILABLE(Agent dispatch 通道不回傳 runtime model 名 —— 此為觀測面失敗原因,非軸失敗;軸 PASS 判定依據 = 其提交的實跑證據)/;code-reviewer(複查)requested=opus / observed=UNAVAILABLE(同上);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=8 → covered 3(trade-kinds.ts / ladder-position.test.ts / types.ts 有 finding)/ no-issues 5(ladder-position.ts / PriceLadder.tsx / capital_api.py / CLAUDE.md / docs-next-time.md)/ skipped 0 / **missed 0**;3+5+0+0=8=|F|(chunked: 否)
**定位 (ENH-B)**: anchored exact 5 / ambiguous 0 / **FAILED 0**
**React-doctor (2.97)**: 未引入新問題(0 條;first-pass 另在 worktree 實跑 react-doctor 掃 311 檔亦零新增)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_SPEC_DETECTED)
**審查軸狀態**: primary(typescript-reviewer)PASS(worktree 實跑 tsc/eslint/vitest 2918/pytest 496/ruff + 71,680 組行為差異測試 + 16 格 mutation)/ 同軸複查(code-reviewer)PASS(tsc 六組 drift 重現 + node 實測 + base 對照)/ Codex 中性 FAIL(CLI 不存在)/ Codex 對抗 FAIL(CLI 不存在)/ Gemini Flash FAIL(agy CLI 不存在)/ Gemini Pro N-A(未啟用)/ cross-axis verification N-A(單軸,同軸複查代位)
**blast radius (2.9)**: 空輸出跳過
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-166`
**worktree HEAD**: `b43fa71693edb63ee6dcceea948cdf856b88419c`
**特別揭露**: 本 PR 由本 session(orchestrator)實作;first-pass 與複查為 fresh-context subagent,orchestrator 同人,分級依 SSOT 機械套用、全證據揭露。

**Report generation**: sha256:d12876da47c6e31e4abfe36429c22b052146b46d678fc0cb1ddb6ae455779016

---

## Spec 依據

此 PR 未附 spec/plan 文件,按一般 PR 流程 review。PR 意圖 = 行為不變 refactor(🔵),白名單 = CLAUDE.md §4 daytrade_sell 契約條全文 + 跨語言 parity 測試全程綠。
`SPEC_COMPLIANCE`: gate=SKIPPED / dispatch=NOT_APPLICABLE / dispatch_count=0 / reason_code=C4_NO_SPEC_DETECTED / requested_model=opus / observed_model=UNAVAILABLE / effort=xhigh / 0 clauses / 0 findings。
校準套用:無作者校準檔(loger-w.md 不存在)、本輪無套用。

## 變更概要

| 檔案 | 類型 | 說明 |
|---|---|---|
| frontend/src/lib/trade-kinds.ts | 重構核心 | KIND_TRAITS 表 + kindTraits() + UNKNOWN_KIND_TRAITS + 交集型別 |
| frontend/src/lib/ladder-position.ts | 重構 | 稅/借券費/排序改吃 traits,刪 KIND_ORDER |
| frontend/src/lib/ladder-position.test.ts | 測試 | characterization(未知 kind = margin 同款) |
| frontend/src/components/stock/PriceLadder.tsx | 重構 | 4 處買側鎖改 KIND_TRAITS[tradeKind].buyLocked |
| frontend/src/types.ts | 重構 | trade_kind 內嵌 union → PositionKind |
| copycat/server/capital_api.py | 重構 | 重複 Literal → TradeKind(wire 形不變,OpenAPI enum 逐字同) |
| CLAUDE.md / docs/next-time.md | docs | §4 讀者位置更新 / L54 勾銷 |

provenance: N-A(base = master)

**行為不變承諾驗證結果(雙方獨立)**:first-pass 以 71,680 組參數矩陣(pre/post 版本並列)`JSON.stringify` 逐位比對 + 排序 16 輪轉/256 配對全等 + 後端 `model_json_schema()` 逐字同;複查另以 node 實測原型鏈鍵等值、base comparator NaN 行為等值。**成立**。

## 發現總覽

| # | 問題 | CC(typescript-reviewer) | 同軸複查 | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| 1 | `daytrade_sell.order: 3` 是無測試看守常數(mutation 3→0 全套 2918 綠存活;表 16 格唯一無人看的一格) | MED | CONFIRMED(校正 LOW:純顯示序位、且是 ?? 3 → 顯式常數的等價轉換) | Nice to Have | `auto-fix` | D13 排序測試加一個元素 |
| 2 | 交集型別註解高估涵蓋:「值域漂開會 tsc 紅」半對半錯 —— 複查實測「TradeKind 加值不補表」會紅(推翻 first-pass 該半),真缺口 = 補表不補 types.ts(A2)與單邊減值(B),真閘在 PriceLadder:296 型別窄化 | LOW | PARTIAL(細節校正,結論同向;first-pass 提議的 _SameDomain 型式另經本機 tsc 實測為 circular constraint 編不過,已換 Expect<AssertEqual> 型式並實測三情境) | Nice to Have | `auto-fix` | 改註解口徑或補 Expect<AssertEqual> 雙向斷言(蓋 A2/B,已實測) |
| 3 | kindTraits 對原型鏈鍵("toString" 等)繞過 ?? fallback,與 close-order.ts kindOf 的 Object.hasOwn 明文慣例相左(非回歸:舊 KIND_ORDER 同洞;實務不可達) | LOW | CONFIRMED(踢館假說「buyLocked 直接索引會白屏」經追源推翻:tradeKind 純記憶體封閉值域) | Nice to Have | `auto-fix` | Object.hasOwn 一行 + docstring 引 kindOf |
| 4 | characterization 掛在 describe("secPositionsOf") 下(受測是 positionEcon);「相對 oracle 違反手算慣例」那半經複查判定不成立(等價關係斷言正是宣告意圖,對目標突變銳利) | LOW | PARTIAL(只收錯位那半) | Nice to Have | `auto-fix` | 搬區塊即可 |
| 5 | PositionKind docstring 只寫「平倉」但本 PR 擴用到下單 trade_kind;後端另有同名三值 Literal(不含 daytrade_sell),grep 混淆被本 PR 加重(前後端同一 wire 欄命名分歧) | LOW | CONFIRMED | Nice to Have | `auto-fix` | 改兩行註解,不動型別(兩名獨立是 #2 真閘前提) |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: f2882b1b807b9d16cd1b action=auto-fix
F-02 finding_uid: 561f7824d1bcaf40f2ef action=auto-fix
F-03 finding_uid: 4b1a3b0447b2faf3f68c action=auto-fix
F-04 finding_uid: be222a52e98178cf6342 action=auto-fix
F-05 finding_uid: 1c1339eba8c4435543e6 action=auto-fix

### Inline Comments per Finding

#### #1 表上 16 格只有 daytrade_sell 的排序那格沒人看

**File**: `frontend/src/lib/trade-kinds.ts`
**Line**: 47

**Comment**:
```
mutation 實測:order: 3 改成 0,全套 2918 條照樣綠 —— 其他 15 格(buyLocked/
halfTaxToday/borrowFee)都有測試殺得掉,只有這格沒有。收斂前它走 ?? 3 fallback,
被 D13「未知 kind 殿後」那條連帶保護;收斂成顯式常數後保護就斷了。
同股號融資/融券多單 + 無券空單是會共存的(cash 那向有沖銷、margin/short 沒有),
打錯這格 = 無券列排到前面,零訊號。
修法一行:ladder-position.test.ts 的 D13 陣列加一個 pos({ kind: "daytrade_sell", qty: -2 }),
順便讓 UNKNOWN_KIND_TRAITS 這個 export 有真正的消費者。
```

#### #2 交集型別的註解把功勞記錯了機制

**File**: `frontend/src/lib/trade-kinds.ts`
**Line**: 28

**Comment**:
```
「值域漂開由交集型別 tsc 紅出來」—— 實測半對:表漏列/多列三個方向都會紅(這半做得好),
但「補了表、types.ts 沒跟」(A2)與「TRADE_KINDS 單邊減值」(B)兩向交集不紅。
今天真正擋住 A2 的是 PriceLadder.tsx:296 把 tradeKind 餵進 trade_kind?: PositionKind
的型別窄化 —— 那道閘是 call-site 偶然形成的,哪天送單改走別的 helper 就無聲消失。
三行零 runtime 的雙向斷言可以把 A2/B 都蓋掉(已於本機 tsc --strict 實測:
同域編過、加值紅 TS2344、減值紅 TS2344;first-pass 原提的 _SameDomain<A extends B,
B extends A = A> 型式經實測是 circular constraint TS2313 編不過,不要用):

type AssertEqual<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;
type Expect<T extends true> = T;
type _KindDomainsMatch = Expect<AssertEqual<TradeKind, PositionKind>>;

或者把註解縮到它真正做到的事,把值域看守點指到 PriceLadder:296。
```

#### #3 kindTraits 收得下 "toString" 這種原型鏈鍵

**File**: `frontend/src/lib/trade-kinds.ts`
**Line**: 62

**Comment**:
```
kindTraits("toString") 拿到的是 Object.prototype.toString(函式,非 nullish → ?? 不觸發),
型別卻標成 KindTraits。隔壁 close-order.ts:25-26 對同一個輸入已有明文相反決定
(「用 Object.hasOwn 不用 in:kind 是後端字串直傳的」)。不是回歸(舊 KIND_ORDER 同洞)、
實務也打不到(後端 kind 是封閉集),但這裡自稱「未知值政策的唯一收斂點」,
政策卻比隔壁那個有書面理由的弱 —— 一行改 Object.hasOwn 就對齊了。
```

#### #4 characterization 放錯 describe

**File**: `frontend/src/lib/ladder-position.test.ts`
**Line**: 200

**Comment**:
```
這條測的是 positionEcon 的稅費分支,卻掛在 describe("secPositionsOf") 底下 ——
vitest -t "positionEcon" 篩不到它。搬進 describe("positionEcon 邊界")就好。
(「相對 oracle 違反手算慣例」那半複查判不成立:expect(mystery).toEqual(margin)
正是「未知 = margin 同款」的宣告本身,對目標突變銳利,不用改。)
```

#### #5 PositionKind 的說明還停在「平倉」,而後端有個同名但少一值的傢伙

**File**: `frontend/src/types.ts`
**Line**: 105

**Comment**:
```
本 PR 讓 PositionKind 多了兩個職責(下單 trade_kind + 交集另一半),但 103 行還寫
「平倉可指定的庫存種類」。更麻煩的是 grep:後端 models.py:23 有同名三值
PositionKind = Literal["cash","margin","short"] —— 不含 daytrade_sell,只是 balance
解析中繼;前端這個四值對應的是後端 TradeKind。改兩行註解:補上下單職責 +
「與後端同名型別不同值域」一句。型別本身不要動(兩名獨立正是 #2 那道真閘的前提)。
```

## CC 原始 findings(first-pass,typescript-reviewer)

(完整保留 reviewer 結論;gate 全跑:tsc 0 / eslint 0 / vitest 2918 / pytest 496 / ruff clean / react-doctor 零新增;71,680 組行為差異測試 + mutation 表 + 後端 schema 逐字比對,worktree 零殘留)

1. **[MEDIUM] `daytrade_sell.order: 3` 無測試看守** — trade-kinds.ts:47。mutation 3→0 全套存活;其餘 15 格 mutation 全被殺。Impact:排序看得見(secPositionsOf → PositionBar),同股號 margin/short + daytrade_sell 可共存。Fix:D13 測試加元素。Search-proof:first-pass `Grep "daytrade_sell" --include=*.test.ts --include=*.test.tsx frontend/src` → **19 個行命中**(ladder-position.test.ts:82/196/318-324、close-order.test.ts:50/54/63/67/71/145、PriceLadder.test.tsx:398/416/1420/1514、CapitalPositionsList.test.tsx:212/222);複查同查詢以**測試案**計 = 9 案 —— 兩個數字是行命中 vs 案數的口徑差,非互斥,兩方逐一檢視結論一致:無一將 daytrade_sell 餵進 secPositionsOf。
2. **[LOW] 交集型別機驗範圍比 docstring 窄** — trade-kinds.ts:26-28/41-43。五組 tsc repro:表漏/多列紅,TradeKind 加值/減值不紅;真專案 A 情境紅在 PriceLadder.tsx:296。Fix:改註解或 _SameDomain。(複查校正:「加值不補表」實際會紅;真缺口是 A2/B。)
3. **[LOW] kindTraits 收原型鏈鍵** — trade-kinds.ts:61-63。與 close-order.ts kindOf 的 Object.hasOwn 明文慣例相左;非回歸、實務不可達。
4. **[LOW] characterization 掛錯 describe + 相對 oracle** — ladder-position.test.ts:195-202。(複查:只收錯位那半。)
5. **[LOW] PositionKind docstring 過窄 + 後端同名異域** — types.ts:103-105/155。後端 models.py:23 同名三值;parity 測試比的是 TradeKind 所以不設防。

其餘核可事實(first-pass):`KIND_TRAITS[tradeKind]` 不會 runtime undefined(tradeKind 唯二來源皆 useState<TradeKind>("cash"),無持久化、無 wire);`PriceLadder.tsx:77` 的 `=== "cash"` 是「預設 vs 非預設」呈現軸非 daytrade_sell 語意,留著正確;safety.py:65-66 後端閘實存;後端四決策點不收的判斷同意。

Per-file accounting:trade-kinds.ts=F1/F2/F3;ladder-position.ts=REVIEWED_NO_ISSUES(71,680 組等值);ladder-position.test.ts=F4;PriceLadder.tsx=REVIEWED_NO_ISSUES(四處 migrate 等值、buyLocked mutation 被殺);types.ts=F5;capital_api.py=REVIEWED_NO_ISSUES(schema 逐字同、import 非死碼);CLAUDE.md=REVIEWED_NO_ISSUES;docs/next-time.md=REVIEWED_NO_ISSUES。

## 同軸複查結果(code-reviewer fresh-context)

| # | 原 severity | verdict | 校正 | 複查證據(摘) |
|---|---|---|---|---|
| 1 | MEDIUM | CONFIRMED | LOW | 唯一讀者 ladder-position.ts:169 sort;全 repo 9 處 daytrade_sell 測試無一餵 secPositionsOf;反證性檢查:另三格都有測試殺 mutation;影響上界 = 列序與 label 次序,不觸數值;可觀測窗實存(margin/short + daytrade_sell 共存)。降級理由:純顯示 + 等價轉換非行為缺陷。 |
| 2 | LOW | PARTIAL | LOW | 六組 tsc drift 實測:A(加值不補表)**RED**(推翻 first-pass 該半)、A2(補表不補型別)GREEN、B(單邊減值)GREEN、C RED、D GREEN、D+ladder RED、A2+ladder RED、B+ladder GREEN → 綜合:B 兩道都不抓。註解「加新種類時」半對半錯。 |
| 3 | LOW | CONFIRMED | LOW | node 實測五個原型鏈鍵全繞過 fallback;base 同洞(git show 對照,comparator 同 NaN);close-order 明文慣例逐字引;踢館假說(buyLocked 白屏)追源推翻 —— 不可達。 |
| 4 | LOW | PARTIAL | LOW | describe 錯位屬實(182 起 secPositionsOf,新 it 在 194-202);「違反手算慣例」不成立:227 行註解是該 block header、反對的是「用受測常數回推」,等價關係斷言不是那個反模式且對目標突變銳利。 |
| 5 | LOW | CONFIRMED | LOW | types.ts:103 職責過窄屬實;models.py:23 同名三值屬實;parity 測試對後端 PositionKind 不設防;本 PR 加重 grep 分歧(後端同欄改 TradeKind、前端改 PositionKind);緩解 = 103 行已有「後端 TradeKind 同字彙」半句。 |

## Action Items

**Severity calibration**:**6c 對 #1 已走**(論式形狀 =「收斂前 ?? 3 fallback 的連帶保護被移除」):(1) 設計意圖 —— PR body 明文為行為不變收斂、把隱式 fallback 升為顯式常數,意圖層清楚;(2) 耦合判定 —— ?? 3 的保護是與舊結構耦合的**偶然產物**(daytrade_sell 不在 KIND_ORDER 才被 fallback 蓋到),新模型下顯式常數合理存在 → 屬 logical-coupling artifact 非防護誤刪,finding 不因 6c 被丟;(3) 新契約下 invariant 的 owner —— 無(表格值無測試看守)→ finding 保留、處置 = 補測試 owner(D13 加元素),此即 #1 的修法。其餘四條非防護移除類,6c N-A。6d-1 無 hedge;6d-2 單軸跳過;6d-3:無 Must Fix 候選(全部不阻擋發布);無作者校準檔。

### Must Fix

無。

### Should Fix

無。

### Nice to Have(可選優化)

- #1 D13 測試補 daytrade_sell 元素(一行,補回本 PR 弄丟的那格保護)
- #2 _SameDomain 雙向斷言或改註解口徑
- #3 kindTraits 改 Object.hasOwn
- #4 characterization 搬 describe
- #5 types.ts 兩行註解(職責 + 同名異域警語)

### 參考用(REFUTED / OUT_OF_SCOPE)

無(兩條 PARTIAL 為細節校正,結論同向,已列 Nice to Have)。

## 審查工具比較(qualitative)

- 本輪亮點是**雙方各自跑了可執行證據**:first-pass 71,680 組差異矩陣 + 16 格 mutation;複查六組 tsc drift 重現並校正了 first-pass 的一項 tsc 宣稱(「加值不紅」→ 實測會紅)—— 同軸複查在這輪展示了非零的糾錯力。
- 複查分佈:CONFIRMED 3 / PARTIAL 2 / REFUTED 0 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0。
- 行為不變承諾:雙方獨立核可,成立。

## 沒做的部分(結案對帳)

| 項目 | 狀態 | 理由 |
|---|---|---|
| Codex 中性 / 對抗軸 | FAIL | `codex` CLI 本機不存在 |
| Gemini Flash 軸 | FAIL | `agy` CLI 本機不存在 |
| Gemini Pro 軸 | N-A | opt-in 未啟用 |
| cross-axis verification | N-A | 單軸,同軸 fresh-context 複查代位 |
| blast radius(2.9) | N-A | script 空輸出跳過 |
| C4 formal spec | N-A | SKIPPED(C4_NO_SPEC_DETECTED) |
| Gemini quota | N-A | 未跑 Gemini 軸 |
| 未驗證前提 | 無 | 每條 finding 均有第一手執行(tsc repro / node / mutation)或 grep 證據 |

**Self-Verify 修正紀錄**(auditor VERDICT: VIOLATIONS: R2, R3, R6, R7, R8;逐條已修,**未經第二次獨立稽查**):
- R2:observed=UNAVAILABLE 補上觀測面失敗原因(Agent dispatch 通道不回傳 runtime model 名)與軸 PASS 的實際依據。
- R3:覆蓋對帳修正(covered 3 / no-issues 5;3+5=8=|F|)。
- R6:F-01 search-proof 補查詢字串與逐檔 file:line;19 vs 9 為行命中 vs 案數口徑差,已調和。
- R7:#1 補走 6c 三問(意圖=顯式化收斂/耦合=偶然保護屬 logical-coupling artifact/新 owner=無 → 處置=補測試),finding 保留。
- R8:#2 修法經本機 tsc --strict 三情境實測 —— **first-pass 原提型式 circular constraint 編不過(稽核抓到的真問題)**,已換 Expect<AssertEqual> 並附實測結果。
