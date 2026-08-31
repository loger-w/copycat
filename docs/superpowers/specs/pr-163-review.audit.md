# PR #163 Code Review 比較報告 · SHA c340d69c

**Report projection schema**: 1

**PR**: [loger-w/copycat#163](https://github.com/loger-w/copycat/pull/163)
**標題**: fix(capital): 部位快照涵蓋水位 —— 樂觀部位不被鏈落地倒退(next-time L57)
**作者**: loger-w
**分支**: `fix/position-snapshot-no-regress` → `master`(PR 已 MERGED,rebase merge)
**變更**: 5 檔案, +108 / -8
**審查日期**: 2026-08-31
**Review input basis**: source repo = loger-w/copycat;source SHA `c340d69cdd276c18df95c76a6ac94d137b570561`;destination SHA `0e8e49a7699e75bb8cf34c287fb20cc3f14df96d`(diff 以 merge-base `dfc3cdf2` three-dot 計,與 PR 檔案清單逐檔一致);`input_binding: verified`(worktree HEAD 實測 == source SHA;destination SHA 本地存在)
**Review continuity**: `source_continuity=CURRENT`(PR 已 MERGED,head 不可變);`base_changed=true`(master 已前進至 #167 之後,屬合併後正常演進);`review_context_changed=false`
**審查工具**: CC(claude-fable-5 orchestrator)+ CC reviewer agents(python-reviewer first-pass + code-reviewer 同軸複查)。**Codex 中性 / Codex 對抗 / Gemini Flash / Gemini Pro 四軸本機不可用**(`codex` / `agy` CLI 不存在)——本報告為 **CC 單軸 + 同軸獨立實例複查**,非 cross-axis;複查實例為 fresh-context subagent、附獨立重現腳本,但同屬 CC 模型家族,判讀時請計入此限制。
**Reviewer model 記錄規則**: 上一行只描述工具組合;實際身分以下一行為準。
**Reviewer models**: orchestrator=claude-fable-5;python-reviewer requested=opus / observed=UNAVAILABLE(無 runtime receipt,依 dispatch 參數);code-reviewer(複查)requested=opus / observed=UNAVAILABLE;Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=5 → covered 4(store.py / client.py / test_fill_latency.py / docs-next-time.md 各有 finding)/ no-issues 1(test_store.py)/ skipped 0 / **missed 0**;4+1+0+0=5=|F|(chunked: 否,5 檔 / 190 diff 行)
**定位 (ENH-B)**: anchored exact 7 / ambiguous 2 / **FAILED 1**(F-10 docs 行,錨文含反引號比對失敗)
**React-doctor (2.97)**: N-A(非 React PR)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_SPEC_DETECTED)
**審查軸狀態**: primary(python-reviewer)PASS(420 tests 實跑 + 5 支重現腳本)/ 同軸複查(code-reviewer)PASS(5 支獨立重現腳本 + base 對照)/ Codex 中性 FAIL(CLI 不存在)/ Codex 對抗 FAIL(CLI 不存在)/ Gemini Flash FAIL(agy CLI 不存在)/ Gemini Pro N-A(未啟用)/ cross-axis verification N-A(單軸;以同軸 fresh-context 複查代位,證據為獨立執行腳本)
**blast radius (2.9)**: 空輸出跳過
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-163`
**worktree HEAD**: `c340d69cdd276c18df95c76a6ac94d137b570561`
**特別揭露**: 本 PR 由本 session(orchestrator)自己實作;first-pass 與複查 reviewer 均為無對話脈絡的 fresh subagent,但 orchestrator 同人,報告分級由 orchestrator 依 SSOT 規則機械套用並全文揭露證據供覆核。

**Report generation**: sha256:917598bd1a48495d35dec9bf4cc6000c33e17a4c121fe8a006fa4684779802af

---

## Spec 依據

此 PR 未附 spec/plan 文件,按一般 PR 流程 review(docs/next-time.md 為待辦清單非 spec)。PR body 載明修法拍板脈絡(user 08-31 拍板「只做水位」)。
`SPEC_COMPLIANCE`: gate=SKIPPED / dispatch=NOT_APPLICABLE / dispatch_count=0 / reason_code=C4_NO_SPEC_DETECTED / requested_model=opus / observed_model=UNAVAILABLE / effort=xhigh / 0 clauses / 0 findings。
校準套用:無作者校準檔(loger-w.md 不存在)、本輪無套用。

## 變更概要

| 檔案 | 類型 | 說明 |
|---|---|---|
| copycat/capital/store.py | 行為 | `_snapshot_watermark` 欄位、`begin_snapshot()`、`set_positions` 水位消耗 + 增量重套、`clear()` 丟水位 |
| copycat/capital/client.py | 行為 | `_maybe_query_balance` rc==0 後呼叫 `begin_snapshot()` |
| tests/capital/test_fill_latency.py | 測試 | 紅先行 in-flight 倒退 repro + 水位前不雙計護欄 |
| tests/capital/test_store.py | 測試 | clear 丟水位防幻影加倉 |
| docs/next-time.md | docs | L57 勾銷 + 倒退保護留尾 |

provenance: N-A(base = master)

## 發現總覽

| # | 問題 | CC(python-reviewer) | 同軸複查 | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| 1 | 開機 backlog 重播被空水位 `{}` 重套,部位多/少報 ~2s、平倉鈕可按 | CRIT | CONFIRMED(校正 HIGH:必然自癒 + 單人 localhost) | Must Fix | `auto-fix` | 修法三行已雙方實測(未 seeded 記 None) |
| 2 | 「水位後成交快照必然沒看到」是跨伺服器時序假設,多計向被本 PR 首開(複查已執行重現 qty 2→3) | MED | CONFIRMED | Should Fix | `ask-user` | 修法涉對帳策略拍板(留尾 or 落地對帳) |
| 3 | 落地重套是新的真錢寫入路徑,零 log、prod 無判準 | MED | CONFIRMED | Should Fix | `auto-fix` | 一行 INFO,量級每輪鏈數筆 |
| 4 | 新測試全部預 seeded,開機(未 seeded)路徑零覆蓋 → #1 得以綠燈出貨 | MED | CONFIRMED(復核:決定因素是 begin_snapshot 相對成交到達的先後) | Should Fix | `auto-fix` | 一條 store 級測試,寫法已給 |
| 5 | `部位落地 %d 列` 與 capital_position.count 用 len(merged),重套加/刪列後失準 | LOW | CONFIRMED(前端不讀 count,僅 log 對帳) | Nice to Have | `auto-fix` | 改讀 store 實際列數 |
| 6 | 拒套類別(無券買向)在落地時多印一次 WARNING(一次性) | LOW | CONFIRMED(實測 2 筆;開機路徑下逐筆各多一次) | Nice to Have | `ask-user` | 接受註記 vs 預判 二選一 |
| 7 | 簡體字「与」(store.py:548,全 repo 唯一) | LOW | CONFIRMED | Nice to Have | `auto-fix` | 一字修正 |
| 8 | next-time 留尾「clear() 連水位丟(重播不幻影加倉)」對開機路徑不成立;多計向未記 | LOW | CONFIRMED(clear 零 prod caller,受保護路徑不會跑) | Nice to Have | `auto-fix` | 隨 #1 修法一併改口 |
| 9 | begin_snapshot↔set_positions 1:1 配對是隱式契約,collector 跨輪交錯時靜默退回修前行為 | LOW | PARTIAL(無可執行直路重現;真發生退回舊行為非新洞) | Nice to Have | `ask-user` | token 化屬設計選擇 |
| 10 | begin_snapshot 全量複製含零成交單,_orders 長跑不清 | LOW | PARTIAL(基線是既有 _orders,本 PR 僅短命拷貝) | Nice to Have | `auto-fix` | 一行過濾 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: a3f7208713e9a944f314 action=auto-fix
F-02 finding_uid: 52f2d97d8071e314effe action=ask-user
F-03 finding_uid: d046619ecd0d8960a8fb action=auto-fix
F-04 finding_uid: fd82acfff4d566e8be52 action=auto-fix
F-05 finding_uid: 012c4b55f58757b59253 action=auto-fix
F-06 finding_uid: 61c78a9a943b580edd93 action=ask-user
F-07 finding_uid: 8eb4dffd0c7103c96fe3 action=auto-fix
F-08 finding_uid: 468c9e48d6f2ad157d77 action=auto-fix
F-09 finding_uid: 44cde64470f69c242043 action=ask-user
F-10 finding_uid: 7ce96f275ffbfd69dad2 action=auto-fix

### Inline Comments per Finding

#### #1 開機重播的成交會被再套一次,部位面板短暫多/少報,平倉鈕還可按

**File**: `copycat/capital/store.py`
**Line**: 593

**Comment**:
```
begin_snapshot() 在開機第一圈就被呼叫(_balance_last_ts=0.0 → 第一圈必發查詢),
那時 backlog 還沒到,水位記下的是空 dict {} —— 而 set_positions 只把 None 當「無水位」,
{} 走有水位分支 → ConnectByID 重播的每筆當日成交 covered=(0,0) → 全部重套到剛落地的
券商快照上。實測:昨庫 3 賣 1(快照 2)開機後顯示 1;今買 1(快照 1)開機後顯示 2,
平倉鈕可按 = 賣 2 張變 1 張裸空。~2 秒後下一輪鏈自癒,但錯誤值已經 emit 出去。

修法三行(已驗證回到 base 行為):

    self._snapshot_watermark = (
        {a.seq_no: (a.filled_qty, a.fill_value) for a in self._orders.values()}
        if self._positions_seeded else None   # 未 seeded = 開機/重播:快照即真相
    )

順手把 _apply_fill_locked docstring「只在 _positions_seeded 之後套」跟新呼叫點對齊,
並補一條開機時序的 store 級測試(begin_snapshot → 重播 D → set_positions → 斷言快照值)。
```

#### #2 水位打開了「多計」這一向,修前不可能發生

**File**: `copycat/capital/store.py`
**Line**: 119

**Comment**:
```
「水位後才到的成交,快照取數必然沒看到」—— 這句的判準是我們 COM 執行緒的到達時刻,
但快照內容的判準是券商帳務入帳時刻,兩者無順序保證。成交已入券商報表、推播卻晚於
查詢出手的那筆,會被快照計一次、落地又重套一次(複查實測 qty 2→3)。修前全標已套用,
多計不可能;本 PR 打開了這一向,而 next-time 留尾只記了少計那向(60s 洞)。

要嘛把註解改成可證偽口徑(「以本機到達序為準,與券商入帳序的偏差是已知殘餘」)+
補對稱留尾;要嘛落地時對帳(該鍵快照張數已等於樂觀張數就不重套)。哪條走法要拍板。
```

#### #3 落地重套是新的真錢寫入路徑,但全程零 log

**File**: `copycat/capital/store.py`
**Line**: 605

**Comment**:
```
這行是本 PR 唯一讓 store 部位「故意不等於」券商快照的地方,卻沒有留痕 —— 同鏈其他
每一步(套了/沒套/部位落地)都有 INFO。#1/#2 兩種偏差在 prod 只能靠肉眼對群益 APP。
重套成功時印一行(seq/股號/增量張數/水位值)就夠,量級每輪鏈最多幾筆,不會洗版。
```

#### #4 新測試都先 set_positions([]) 預熱,開機路徑零覆蓋

**File**: `tests/capital/test_fill_latency.py`
**Line**: 129

**Comment**:
```
兩條新測試開頭都先 set_positions([]) 把 seeded 打開,水位機制只在「已 seeded」這半被
驗;#1 的洞正好在另一半。複查實測:把 begin_snapshot 挪到 backlog 之前(= client 真實
時序)既有護欄測試就從 7 變 4。補一條 store 級測試:
CapitalStore() → begin_snapshot() → 重播 N+D → set_positions([1 張]) → 斷言 1 張。
```

#### #5 「部位落地 N 列」與 count 在重套加列後對不上

**File**: `copycat/capital/client.py`
**Line**: 665

**Comment**:
```
set_positions 現在可能再加列(重套新增)或刪列(沖銷),兩個讀者還用 len(merged)。
前端不讀 count 所以只影響 log 對帳 —— 但那正是 #3 要補的實錄素材。兩處改
len(self.store.positions()) 就好(已核:`def positions()` 存在於 worktree store.py:610,
回傳 list[Position]),順手把 set_positions docstring「全量替換」補上新語意。
```

#### #6 無券買向成交在落地時會多印一次 WARNING

**File**: `copycat/capital/store.py`
**Line**: 605

**Comment**:
```
拒套類別由 _apply_fill_locked 早退沒錯,但早退前會印 log:實測一筆無券買向成交
回報當下 2 行、落地後累計 3 行。一次性不是洪水(下一輪水位涵蓋後閘門就關),
開機路徑(#1)下 backlog 每筆拒套各多一次。two-way:註解註明「會多印一行」,
或閘門前加 _FILL_KIND 預判 —— 二選一即可。
```

#### #7 簡體字「与」

**File**: `copycat/capital/store.py`
**Line**: 548

**Comment**:
```
「(与 F-02 同一類洞)」→「與」。全 repo 唯一一個簡體字。
```

#### #8 留尾寫的保證對真正會跑的路徑不成立

**File**: `docs/next-time.md`
**Line**: 需人工確認（anchor 未在綁定來源中比中或證據 binding 失效）

**Comment**:
```
「clear() 連水位一起丟(重播不幻影加倉)」—— store.clear() 目前零 prod caller,
受保護的重播路徑永遠不會跑;真正每次開機都走的 ConnectByID backlog 路徑不受保護(#1)。
#1 修好後把這句改成「重播/開機(未 seeded)一律不記水位」,另補 #2 的多計向留尾。
```

#### #9 水位配對是隱式契約,collector 跨輪交錯時靜默退回修前行為

**File**: `copycat/capital/store.py`
**Line**: 551

**Comment**:
```
begin_snapshot ↔ set_positions 的 1:1 配對靠 client 三個守門旗標維持;balance 段
超時 abandon 後遲到列被誤認新輪的縫隙裡,W2 會被 round-1 快照消耗 → 該輪退回
修前的少計行為(不是新洞)。要真堵就 token 化(begin_snapshot 回 token、
set_positions 驗 token),同時消掉 store 一個跨呼叫可變欄位 —— 屬設計選擇,不急。
```

#### #10 begin_snapshot 全量複製含零成交單

**File**: `copycat/capital/store.py`
**Line**: 556

**Comment**:
```
filled_qty == 0 的委託放進水位是 no-op(get 預設 (0,0.0) 結果相同),而 _orders
長跑不清。加個 if a.filled_qty 過濾(已核:`_Agg.filled_qty: int = 0` 存在於
worktree store.py:79),鎖內少複製一截。
```

## CC 原始 findings(first-pass,python-reviewer,context-aware)

（以下為 reviewer 原文結論的完整保留;全部斷言經 reviewer 於 worktree 實跑驗證,重現腳本置於其 scratchpad,worktree 零改動;`pytest tests/capital -q` 420 passed / ruff / pyright 0)

1. **[CRITICAL→複查校正 HIGH] 開機首輪:ConnectByID backlog 重播的成交被當成「水位後增量」重套到券商快照上** — store.py 593-607 / client.py 232+524-526。水位消耗迴圈不看 `_positions_seeded`;`begin_snapshot()` 記空 dict 而 `set_positions` 只把 None 當無水位 → backlog 全部成交重套。實跑:昨庫賣向 7→4、買向 1→2(base 正確)。Impact:真錢部位面板在「當日已交易後重啟」時多/少報 ~2-5s,平倉鈕可按。Fix:未 seeded 時記 None(已 monkeypatch 驗證)。Search-proof:`Grep "snapshot_watermark|begin_snapshot"` 全樹 → 產生點僅 client.py:526(`self.store.begin_snapshot()`,本 draft 定稿時於 worktree 重跑 `grep -n begin_snapshot` 核得 client.py:526 / store.py:552 定義 / store.py 內 6 處引用)、消耗點僅 store.py:593-607,兩處皆無 `_positions_seeded` 判斷;`Grep "_positions_seeded"` → 僅 store.py:117/185/546/608,守門只在 apply_reply。
2. **[MEDIUM] 「快照必然沒看到」是未證實跨伺服器時序假設,多計向留尾未記** — store.py 118-121。到達序 vs 券商入帳序無保證;修前多計不可能,本 PR 打開;留尾只記少計向。
3. **[MEDIUM] 落地重套零 log** — store.py 605-607。本 PR 唯一讓部位故意偏離快照的機制無留痕,與同鏈 log 慣例相反;next-time 的 grep 判準抓不到它。
4. **[MEDIUM] 新測試兩條都預先 seeded,開機路徑零覆蓋** — test_fill_latency.py 129/157。紅先行有效性實測:base 上 repro 紅、護欄綠;但主路徑(開機)未受測,F-01 得以出貨。clear 測試只覆蓋零 prod caller 的變體。
5. **[LOW] count 與「部位落地 N 列」低報** — client.py 664-667。實測鏈飛行中買進新檔 → count=1、store 2 列。
6. **[LOW] 水位輪次錯配靜默退回倒退行為** — store.py 551-557。collector F7 殘餘風險路徑上 W2 被 round-1 消耗。
7. **[LOW] begin_snapshot 全量複製含零成交/終態單** — store.py 554-557。µs 級+鎖內,隨長跑線性。
8. **[LOW] 拒套類別落地多印一次 WARNING** — store.py 605-607。一次性非洪水。
9. **[LOW] 簡體字「与」** — store.py 547-548。Search-proof:`grep -ro "与" copycat/` → 全樹唯一 1 筆,位於 store.py:548(複查重跑同查詢核實)。
10. **[LOW] 留尾單向 + clear 保證對開機不成立** — docs/next-time.md 57-64。

Per-file accounting:store.py=F1/2/3/5/6/7/9;client.py=F1(共同錨)/F4;test_fill_latency.py=F8;test_store.py=REVIEWED_NO_ISSUES(clear 測試經 mutation 驗證有效 MUTANT KILLED);docs/next-time.md=F10。
Reviewer 結論:Block(F-01 可穩定重現、碰真錢平倉張數,修法三行)。

## 同軸複查結果(code-reviewer fresh-context,獨立重現腳本 + base 對照)

| # | 原 severity | verdict | 校正 severity | 複查證據(摘) |
|---|---|---|---|---|
| 1 | CRITICAL | CONFIRMED | HIGH | 逐步核 boot 順序(`_balance_last_ts=0.0`/OnConnect 後才推 backlog/`{}` 走有水位分支/`_apply_fill_locked` 自身不查 seeded);repro:賣向 2→1、買向 1→2 且 kind=cash 可平倉 = 賣 2 變 1 裸空;自癒實測 0.53s 後回正但錯值已 emit;降級理由:必然自癒+單人 localhost+需盤中重啟前提,對照本 repo CRITICAL 基準(pr-118 不自癒)低一級。補充:store.clear() 零 prod caller(`grep -rn "store.clear()" copycat/` → 唯一命中 com.py:273 且為「另案處理」註解,worktree 重跑核實)→ 本 PR 唯一有防護的重播路徑永遠不會跑;`_apply_fill_locked` docstring 與新呼叫點互相矛盾。 |
| 2 | MEDIUM | CONFIRMED | MEDIUM | repro_f02:seeded 穩態 1 張 → 成交推播晚到但券商報表已含 → 落地 qty=3(base 同輸入 qty=2);base 結構上不可能多計(落地不呼叫 _apply_fill_locked)。 |
| 3 | MEDIUM | CONFIRMED | MEDIUM | 迴圈內零 log 屬實;repro 全程 stdout 無一行提到重套;CLAUDE.md §4 慣例每條契約附 grep 判準,此機制缺口屬實。 |
| 4 | LOW | CONFIRMED | LOW | count 無下游消費者(useCapital.ts:124 只 invalidate);pre-PR 已有重複列合併誤差源,本 PR 多開一向。 |
| 5 | LOW | PARTIAL | LOW | 「隱式契約無斷言」為真且是同檔唯一裸奔的跨輪狀態;但具體交錯走不到直路(三層守門逐條核),唯一縫隙是 10s abandon 後遲到列誤認,真發生退回修前行為非新洞。 |
| 6 | LOW | PARTIAL | LOW | 兩事實各自成立,但成長主體是既有 _orders(pre-existing baseline),本 PR 只加短命 O(N) 拷貝。 |
| 7 | LOW | CONFIRMED | LOW | repro_f07 量到確切 2 筆(apply_reply 1 + 落地 1),第二三輪靜默。 |
| 8 | MEDIUM | CONFIRMED | MEDIUM | repro_f08 三組對照:begin_snapshot 放 backlog 前(真實時序)7→4;420 passed 證實套件對 F-01 無感;銳化:決定因素是 begin_snapshot 相對成交到達先後。 |
| 9 | LOW | CONFIRMED | LOW | grep 全 copycat 唯一簡體字,行號 548。 |
| 10 | LOW | CONFIRMED | LOW | clear 零 prod caller(唯二處是「另案」註解);真正會跑的 backlog 重播不受保護(repro 已證);多計向未記屬實。 |

## Action Items

**Severity calibration**:6c 不觸發(無「移除既有防護」類 finding —— F-01 是新增機制的洞,非削弱既有 guard);6d-1 無 hedge 措辭(全部有執行證據);6d-2 單軸 review 依 SSOT 跳過;6d-3 逐條走過(見下);無作者校準檔。

### Must Fix(合併前必修;PR 已 merge → 建議立即開收修 PR)

- **#1 開機重播重套**(HIGH,雙方獨立執行證實):repro = 「當日已有成交後重啟 server → 開機 ~2 秒內部位面板張數錯、平倉鈕可按」— user-visible 具體重現 ✓;不修就壞 runtime 資料正確性(真錢平倉張數來源)✓。修法三行 + docstring 對齊 + 一條開機測試。

### Should Fix(強烈建議)

- **#2 多計向**(MED CONFIRMED,已執行重現):競態性使 user-visible repro 無法決定性寫出 → 不上 Must;兩條修法(改口徑+補留尾 / 落地對帳)需拍板。
- **#3 重套零 log**(MED CONFIRMED):不阻擋發布(observability)但直接決定 #1/#2 在 prod 有無判準。
- **#4 開機路徑測試**(MED CONFIRMED):防 #1 回歸的紅燈,與 #1 同批補。

### Nice to Have(可選優化)

- #5 count 改讀實際列數;#6 重複 WARNING 二選一;#7 簡體字;#8 留尾改口(隨 #1);#9 水位 token 化(設計選擇);#10 零成交過濾。

### 參考用(REFUTED / OUT_OF_SCOPE)

無 —— 本輪零 REFUTED / 零 OUT_OF_SCOPE。

## 審查工具比較(qualitative)

- 單軸 + 同軸複查:first-pass 與複查各自獨立寫重現腳本、互相對照(F-01 兩方各自重現且結果一致;F-02 複查追加了 first-pass 沒有的執行重現)。
- 複查分佈:CONFIRMED 8 / PARTIAL 2 / REFUTED 0 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0 —— REFUTED 率 0%,first-pass 命中率高,Must/Should 可放心採納;但單軸無 fresh-eyes 對照,diff-only 視角的盲點(如跨檔語感類 smell)本輪無人補位。
- severity 校正 1 條(CRIT→HIGH),校正理由 = impact 量級(自癒窗 + 單人環境),非真實性。

## 沒做的部分(結案對帳)

| 項目 | 狀態 | 理由 |
|---|---|---|
| Codex 中性軸 | FAIL | `codex` CLI 本機不存在 |
| Codex 對抗軸 | FAIL | 同上 |
| Gemini Flash 軸 | FAIL | `agy` CLI 本機不存在 |
| Gemini Pro 軸 | N-A | opt-in 未啟用(且 CLI 不存在) |
| cross-axis verification | N-A | 單軸;以同軸 fresh-context 複查代位(獨立執行證據已附) |
| blast radius(2.9) | N-A | script 空輸出跳過 |
| React-doctor(2.97) | N-A | 非 React PR |
| C4 formal spec | N-A | SKIPPED(C4_NO_SPEC_DETECTED) |
| Gemini quota | N-A | 未跑 Gemini 軸 |
| 前端 gates | N-A | 本 PR 無前端檔 |
| F-10 anchor 定位 | FAIL | docs 行錨文比對失敗,inline 塊標「需人工確認」 |
| 未驗證前提 | 無 | 本輪每條 finding 均有第一手執行或 grep 證據;F-05/F-06 標 PARTIAL 未升級 |

**Self-Verify 修正紀錄**(auditor VERDICT: VIOLATIONS: R3, R6, R8;逐條已修,**未經第二次獨立稽查**):
- R3:header 覆蓋對帳數字誤植(covered 3 → 實為 4;4+1=5=|F| 等式已補)。
- R6:三處 absence 斷言的 search-proof(查詢字串 + file:line)自 reviewer 原文補寫回報告,並於 worktree 重跑核實(begin_snapshot 產生點 client.py:526 / store.clear 唯一命中 com.py:273 / 「与」唯一 store.py:548)。
- R8:#5 / #10 修法引用的 API 於 worktree 第一手核實(store.positions() @610、_Agg.filled_qty @79),已附註。
