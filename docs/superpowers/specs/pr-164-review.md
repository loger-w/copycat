# PR #164 Code Review 比較報告 · SHA 82ee77be
**Report projection schema**: 1

**PR**: [loger-w/copycat#164](https://github.com/loger-w/copycat/pull/164)
**標題**: fix(server,frontend): 回補入列三合一 —— set_main 去重 / 開盤雙發結案 / 群組輪詢盤外不回 false(L69/L70/L71)
**作者**: loger-w
**分支**: `fix/backfill-enqueue-trio` → `master`(PR 已 MERGED,rebase merge)
**變更**: 6 檔案, +106 / -20
**審查日期**: 2026-08-31
**Review input basis**: source repo = loger-w/copycat;source SHA `82ee77bea335585c38a9a72100fe8eb53727e2af`;destination SHA `68833b6cb87348e5e05529be4b79d2f8569730f3`(= merge-base,two-dot 即 three-dot);`input_binding: verified`(worktree HEAD 實測 == source SHA)
**Review continuity**: `source_continuity=CURRENT`(已 MERGED,head 不可變);`base_changed=true`(master 已前進,合併後正常演進);`review_context_changed=false`
**審查工具**: CC(claude-fable-5 orchestrator)+ CC reviewer agents(code-reviewer first-pass + code-reviewer 同軸複查)。**Codex 中性 / Codex 對抗 / Gemini Flash / Gemini Pro 四軸本機不可用**(`codex` / `agy` CLI 不存在)—— CC 單軸 + 同軸 fresh-context 複查,非 cross-axis,判讀請計入此限制。
**Reviewer model 記錄規則**: 上一行只描述工具組合;實際身分以下一行為準。
**Reviewer models**: orchestrator=claude-fable-5;code-reviewer(first-pass)requested=opus / observed=UNAVAILABLE(無 runtime receipt);code-reviewer(複查)requested=opus / observed=UNAVAILABLE;Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=6 → covered 6(六檔皆有 finding 落點)/ no-issues 0 / skipped 0 / **missed 0**;6+0+0+0=6=|F|(chunked: 否)
**定位 (ENH-B)**: anchored exact 9 / ambiguous 0 / **FAILED 0**(F-04/F-07 為「缺東西」型以 enclosing symbol 定位,已於 worktree 重比中)
**React-doctor (2.97)**: PASS — 未引入新問題(0 條)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_SPEC_DETECTED)
**審查軸狀態**: primary(code-reviewer)PASS(pytest test_stock_engine 186 實跑 + query-core 5.101.2 原始碼直讀 + node 邊界轉寫)/ 同軸複查(code-reviewer)PASS(2 支 probe 實測 + mutation 1336 passed + 全 repo refetchInterval baseline 掃描)/ Codex 中性 FAIL(CLI 不存在)/ Codex 對抗 FAIL(CLI 不存在)/ Gemini Flash FAIL(agy CLI 不存在)/ Gemini Pro N-A(未啟用)/ cross-axis verification N-A(單軸,同軸複查代位)
**blast radius (2.9)**: N-A — script 空輸出跳過(「跑了沒結果」非「沒跑」)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-164`
**worktree HEAD**: `82ee77bea335585c38a9a72100fe8eb53727e2af`
**特別揭露**: 本 PR 由本 session(orchestrator)實作;first-pass 與複查為 fresh-context subagent,orchestrator 同人,分級依 SSOT 機械套用、全證據揭露。

**Report generation**: sha256:da2f9a73a5872fbb61068cac5932a44a4a37576dde5ade33300945cee32ef6de

---
## [完整證據副檔](pr-164-review.audit.md)
### finding_uid 索引
[1a17f3ad9e5b904ade51](pr-164-review.audit.md#發現總覽) · [bf29277803f49992bb31](pr-164-review.audit.md#發現總覽) · [18bf80a85f3d1c9c8b72](pr-164-review.audit.md#發現總覽) · [e6e8fcf8af816d62e45a](pr-164-review.audit.md#發現總覽) · [f3729b9929032aa63c3a](pr-164-review.audit.md#發現總覽) · [5f8a7982823f547cc03c](pr-164-review.audit.md#發現總覽) · [df70db8e3e616d7c1a1b](pr-164-review.audit.md#發現總覽) · [af017b4eb41b4c8155f2](pr-164-review.audit.md#發現總覽) · [90028f7124a6720bc50f](pr-164-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC(code-reviewer) | 同軸複查 | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| 1 | set_main 新 guard 讀到「逾時放棄」寫進 _backfilled 的旗標,放棄檔切主圖不再重排 | MED | PARTIAL(校正 LOW:漲跌停值變入列點會救 —— probe 實測放棄後餵 UpperLimitPrice +1 次重排;殘餘窗收斂到「盤中新開主圖+留自選+limits 已落定」;且 first-pass 建議修法 `or key in _backfill_timeouts` 經複查證偽 —— 該 dict 成功不清,會把 churn 原封放回) | Nice to Have | `ask-user` | 分帳設計(_backfill_gave_up set 或判 >MAX)要拍板;簡單修法已被證偽 |
| 2 | 「保險由 reconnect 承接」宣稱不完備:零推播自癒(_heal_tick)重掛不通知 engine、不清 _backfilled,靜默期缺口當日補不回 | MED | CONFIRMED(校正 LOW:repo 自身 stock_source.py:42-44 承重註解為證人;警告不可照字面修 —— heal 時清 _backfilled 以 60s 門檻會放大 churn;正解 = 改口三處註解與該承重註解同步) | Nice to Have | `auto-fix` | 改口註解(stock_engine:627-628 / stock_source:42-44 / next-time),不動 code |
| 3 | 「set_main 無條件入列」前提散落四處未同步(test 2833/2848、stock_engine 1190、app.py 1559、stock_source 42-44) | LOW | CONFIRMED(行號兩處校正 +2;stock_source 那處與 #2 同源、優先) | Nice to Have | `auto-fix` | 四處各改一句 |
| 4 | 「刻意不擋 no_data/冷卻」無測試釘住 —— guard 收斂成 _backfill_wanted 的 mutation 全綠(1336 passed) | LOW | CONFIRMED(mutation 實證) | Nice to Have | `auto-fix` | 補兩條測試 |
| 5 | groupPollInterval 盤外回值未秒級量化,偏離 day-bars-rollover 鐵律 (c)(全 repo 唯一未量化者) | LOW | PARTIAL(baseline 掃描站 finding 這邊 + query-core 5.101.2 機制核實;但「每秒 render→每秒重排」頻率宣稱錯 —— 盤外無 dirty 推播,殘存 render 驅動只剩 orders 10s 輪詢;喚醒時刻無誤差) | Nice to Have | `auto-fix` | Math.ceil(ms/1000)*1000 一行 + 1_000 下限補理由 |
| 6 | msUntilTradingOpen 在 lib/trading-hours.test.ts 零直接測試;14 天 fallback 與 1s 下限兩分支零覆蓋 | LOW | CONFIRMED(間接覆蓋來自 4 條 groupPollInterval 測試;fallback 與 09:00:59.x 下限確實碰不到) | Nice to Have | `auto-fix` | lib 層補一個 describe |
| 7 | next-time L71 結案條「原文:」空尾,原文併進下一條主詞不符 | LOW | CONFIRMED(尾字元核過;同 commit 兩條兄弟條原文完整 = 漏貼而非風格) | Nice to Have | `auto-fix` | 兩句搬回 |
| 8 | msUntilTradingOpen 自帶第二把「下一交易日」尺(14 步 vs NEXT_TRADING_DAY_MAX_STEPS=30) | LOW | PARTIAL(知識重複真;正確性風險假 —— 30 是護欄非業務常數、14>10 春節界安全;兩支域不同不可互換) | 參考用 | `no-op` | 風險不存在;至多補一句交叉引用 |
| 9 | 測試用 ISO 字串建 Date,偏離同族數值建構慣例 | LOW | CONFIRMED(校正:date-time 無位移形依規格為本地時間、寫法正確;AR8 講的是 date-only 坑,不適用 —— 純慣例不一致) | 參考用 | `no-op` | 無缺陷;要齊一時再改 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 1a17f3ad9e5b904ade51 action=ask-user
F-02 finding_uid: bf29277803f49992bb31 action=auto-fix
F-03 finding_uid: 18bf80a85f3d1c9c8b72 action=auto-fix
F-04 finding_uid: e6e8fcf8af816d62e45a action=auto-fix
F-05 finding_uid: f3729b9929032aa63c3a action=auto-fix
F-06 finding_uid: 5f8a7982823f547cc03c action=auto-fix
F-07 finding_uid: df70db8e3e616d7c1a1b action=auto-fix
F-08 finding_uid: af017b4eb41b4c8155f2 action=no-op
F-09 finding_uid: 90028f7124a6720bc50f action=no-op
### Inline Comments per Finding
#### #1 逾時放棄的檔,現在連切主圖也叫不動回補了
**File**: `copycat/server/stock_engine.py`
**Line**: 631

**Comment**:
```
_backfilled 有兩個寫入點:1537 套用成功、1485 逾時放棄(借它當「當日不再入列」冷卻)。
新 guard 讀的是混了兩種意思的集合 —— 連 3 次 SubHistory 逾時的檔,切主圖不再重排。
複查 probe 實測有一條救援還在:首則帶 UpperLimitPrice 的 REALTIME 會走漲跌停值變
入列點(1136-1141,收件人條件正是 code in _backfilled)+1 次重排;殘餘真空窗收斂到
「盤中新開主圖 + 該檔留自選 + limits 已在放棄前落定」。
注意:「guard 加 or key in self._backfill_timeouts」這條快修是錯的 —— 該 dict 成功不清
(只在 rollover 1005 / 真退訂 1390 清),逾時一次後成功的檔會整天繞過 guard,churn 原封
放回。要分帳就開獨立的 _backfill_gave_up set,或判 > _BACKFILL_TIMEOUT_MAX_RETRIES。
怎麼分要拍板。
```
#### #2 「reconnect 承接」講太滿:零推播自癒那條路不通知 engine
**File**: `copycat/server/stock_engine.py`
**Line**: 628

**Comment**:
```
on_reconnect 唯一產生點是 tc4.py:1235(PING 判斷線那條);REALTIME 零推播自癒
(_heal_tick,R2 門檻 60s)重掛訂閱但不清 _backfilled。靜默期缺口自此當日補不回
(修前切主圖會順手補)。stock_source.py:42-44 正是 pr-126 F-01 決策的承重註解,
它點名的兩條救援之一被這次拿掉了 —— 那段要跟 code 同批改口。
不要照字面修(heal 時清 _backfilled 以 60s 門檻會把 churn 放大到遠超修前 75 次):
正解是把「切主圖可補」從三處註解的不變式裡拿掉,靜默缺口的真解另案
(heal 發 per-code 事件或節流式 guard)。
```
#### #3 四處註解還寫著「set_main 無條件入列」
**File**: `tests/server/test_stock_engine.py`
**Line**: 2833

**Comment**:
```
test 2833/2848(「無條件」已假,而且理由反轉 —— 有 guard 之後切回主圖才是有鑑別力
的證人)、stock_engine.py:1190(「三個入列點」其一已條件化)、app.py:1559
(「訂閱與回補都還要靠它」)、stock_source.py:42-44(見 #2,優先)。四處各改一句。
```
#### #4 「刻意不擋 no_data/冷卻」沒有紅燈
**File**: `tests/server/test_stock_engine.py`
**Line**: 210

**Comment**:
```
把 guard 順手收斂成 if self._backfill_wanted(key)(看起來像純重構、與 741/1202 對稱),
整套 1336 條照樣全綠 —— 複查真的做了這個 mutation。而那會讓主圖在冷卻/no_data 下
整天補不回來(group_snapshot docstring 728-731 記載要避免的)。補兩條:
_backfill_failed 打滿後 set_main 仍入列;_no_data 加入後 set_main 仍入列。
```
#### #5 盤外回值毫秒精度,timer 白重排(照家規量化一下)
**File**: `frontend/src/hooks/useGroupSnapshots.ts`
**Line**: 100

**Comment**:
```
全 repo 函式形 refetchInterval 掃過一輪,只有這支盤外分支沒做秒級量化
(day-bars-rollover 鐵律 (c) 的 Math.ceil(ms/1000)*1000)。實害比 first-pass 講的小:
盤外沒有 dirty 推播,render 驅動只剩 orders 10s 輪詢,淨代價 = 盤外每 ~10s 一組
clearInterval/setInterval,喚醒時刻無誤差。照家規補一行,順便給 1_000 下限寫個理由
(目前是整檔唯一沒有理由的數字)。
```
#### #6 msUntilTradingOpen 的兩條防護分支沒人測
**File**: `frontend/src/lib/trading-hours.ts`
**Line**: 29

**Comment**:
```
lib/trading-hours.test.ts 是這模組三支時段函式的測試家,第四支只被 hooks 測試間接
蓋到。零覆蓋的兩條正是刻意的失效方向:14 天窮盡 fallback(回 86_400_000,「日曆異常
不空轉」的唯一保證)與 Math.max(...,1_000) 下限(每天 09:00:59.x 可達)。
補一個 describe:窗前/收盤後/週五→週一/假日跳過/setHolidays 灌 15 天 → 24h fallback/
09:00:59.500 → 1000。
```
#### #7 L71 結案條的原文被貼丟了
**File**: `docs/next-time.md`
**Line**: 82

**Comment**:
```
「原文:」後面直接斷行(尾字元核過),原文兩句被接到下一條「同病:其他 hook」尾巴,
主詞對不上。同 commit 的 L69/L70 兩條原文都貼齊了 —— 三選二的一致性說明這是漏貼。
把兩句搬回來就好。
```
