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
## [完整證據副檔](pr-163-review.audit.md)
### finding_uid 索引
[a3f7208713e9a944f314](pr-163-review.audit.md#發現總覽) · [52f2d97d8071e314effe](pr-163-review.audit.md#發現總覽) · [d046619ecd0d8960a8fb](pr-163-review.audit.md#發現總覽) · [fd82acfff4d566e8be52](pr-163-review.audit.md#發現總覽) · [012c4b55f58757b59253](pr-163-review.audit.md#發現總覽) · [61c78a9a943b580edd93](pr-163-review.audit.md#發現總覽) · [8eb4dffd0c7103c96fe3](pr-163-review.audit.md#發現總覽) · [468c9e48d6f2ad157d77](pr-163-review.audit.md#發現總覽) · [44cde64470f69c242043](pr-163-review.audit.md#發現總覽) · [7ce96f275ffbfd69dad2](pr-163-review.audit.md#發現總覽)
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
