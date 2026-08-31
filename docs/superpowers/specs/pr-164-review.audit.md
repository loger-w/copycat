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

## Spec 依據

此 PR 未附 spec/plan 文件,按一般 PR 流程 review。L69 由 user 拍板於 next-time,L70 為 log 驗證結案(零 code),L71 修 TQ refetchInterval 回 false 不排 timer 的洞。
`SPEC_COMPLIANCE`: gate=SKIPPED / dispatch=NOT_APPLICABLE / dispatch_count=0 / reason_code=C4_NO_SPEC_DETECTED / requested_model=opus / observed_model=UNAVAILABLE / effort=xhigh / 0 clauses / 0 findings。
校準套用:無作者校準檔(loger-w.md 不存在)、本輪無套用。

## 變更概要

| 檔案 | 類型 | 說明 |
|---|---|---|
| copycat/server/stock_engine.py | 行為 | set_main 入列 guard(_backfilled / 在途) |
| tests/server/test_stock_engine.py | 測試 | 紅先行 2 條 + 既有 2 條前提校正 |
| frontend/src/lib/trading-hours.ts | 新純函式 | msUntilTradingOpen |
| frontend/src/hooks/useGroupSnapshots.ts | 行為 | groupPollInterval 盤外回距開點 ms |
| frontend/src/hooks/useGroupSnapshots.test.tsx | 測試 | 4 條新期望 |
| docs/next-time.md | docs | L69/L70/L71 勾銷 + 同病留尾 |

provenance: N-A(base = master)

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

#### #8 又一把「下一個交易日」的尺(參考用,不是缺陷)

**File**: `frontend/src/lib/trading-hours.ts`
**Line**: 30

**Comment**:
```
不是 PR 缺陷:trading-calendar 的 NEXT_TRADING_DAY_MAX_STEPS=30 是「絕不無限迴圈」
護欄非業務常數,14 > 春節 ~10 天,界安全;兩支域不同(ISO+UTC vs 本地 Date+今天也算)
不可直接互換。留著的代價只是下次改上界認知時要記得兩處 —— 要處理的話補一句
交叉引用即可。
```

#### #9 測試用 ISO 字串建 Date(參考用,寫法其實是對的)

**File**: `frontend/src/hooks/useGroupSnapshots.test.tsx`
**Line**: 135

**Comment**:
```
不是 PR 缺陷:date-time 無位移形("2026-08-25T10:00:00")依規格解讀為本地時間,
與受測函式語意正好一致;AR8 那個坑是 date-only 形被當 UTC 午夜,不適用這 7 筆。
只是同族測試(trading-hours.test 的 at() helper)都用數值建構子 —— 要齊一時再改。
```

## CC 原始 findings(first-pass,code-reviewer)

(完整保留;gate:pytest test_stock_engine 186 passed 實跑;前端以 node 轉寫 + query-core 5.101.2 原始碼直讀求證,worktree 無 node_modules 故 vitest 未實跑 —— 已在「沒做的部分」列)

1. **[MEDIUM] 逾時放棄偽記帳被新 guard 一併擋掉** — stock_engine.py:631-632。`_backfilled` 寫入點 1537(成功)/1485(放棄);放棄檔切主圖不再重排,「主圖整天補不回來」正是 629-630 註解要避開的。Search-proof:`grep -rn "_backfilled\.(add|clear|discard)"` → 寫入僅 1485/1537,清除僅 550/618/1003/1071;六入列點逐一核(741/1202 經 _backfill_wanted、1141 需值變、1014/1074 綁 rollover/reconnect)。
2. **[MEDIUM] 「reconnect 承接」不完備** — stock_engine.py:627-628。`on_reconnect` 唯一產生點 tc4.py:1235-1236;`_heal_tick`(618-760)全段無呼叫。靜默期成交只有 apply_backfill 能補,修後該檔已在 _backfilled → 切主圖 no-op。
3. **[LOW] 四處前提未同步** — test 2833/2848、stock_engine 1190、app.py 1557(複查校正 1559)、stock_source.py 44-46(複查校正 42-44)。
4. **[LOW] 刻意差異無測試釘** — TestBackfillGuard;冷卻類斷言全落在 group_snapshot/首筆 tick 路徑,無一以 set_main 為證人。
5. **[LOW] 第二把下一交易日尺** — trading-hours.ts:30;上界 14 vs 30、週末判準不同源;node 轉寫實測失效方向安全。
6. **[LOW] 回值未秒級量化** — useGroupSnapshots.ts:100;query-core 5.101.2 queryObserver.js:115-117/208-219 直讀(每 render 求值、變值即 clear+setInterval);對照 day-bars-rollover 鐵律 (c)。
7. **[LOW] lib 層零直接測試** — msUntilTradingOpen;fallback 與 1s 下限分支零覆蓋。
8. **[LOW] ISO 字串建 Date** — useGroupSnapshots.test.tsx:135;對照 trading-hours.test.ts:12-14 / trading-calendar.ts:38-45(AR8)。
9. **[LOW] next-time 原文空尾** — docs/next-time.md:82;`grep -n "原文:$"` 唯一空尾行。

Cross-cutting:Reuse(guard 刻意不重用 _backfill_wanted 有理由成立;前端兩處可重用未重用 = F-05/F-06)/ Quality(groupPollInterval 簽名改 Date 消掉 leaky 參數,是改善;1_000 無理由併 F-06)/ Efficiency(guard O(1) 鎖內無 await 無 TOCTOU;msUntilTradingOpen 值域 < 2^31-1 實測)/ Design Decay(F-03 是 Shotgun Surgery 訊號,成因 = _backfilled 一名多義,真解在 F-01 分帳)/ Dependency 免。

Per-file accounting:stock_engine.py=F1/F2/F3;test_stock_engine.py=F3/F4(兩支新測試 mutation 可殺:guard and→or 兩支紅);trading-hours.ts=F5/F7;useGroupSnapshots.ts=F6;useGroupSnapshots.test.tsx=F8;docs/next-time.md=F9。

## 同軸複查結果(code-reviewer fresh-context;2 支 probe + mutation + baseline 掃描)

| # | 原 | verdict | 校正 | 複查證據(摘) |
|---|---|---|---|---|
| 1 | MED | PARTIAL | LOW | probe1:恆逾時 3 次後切走切回重排 0 次(機制屬實);probe2:放棄後餵 UpperLimitPrice REALTIME → +1 次重排(漲跌停值變入列點無 _backfill_wanted 閘、收件人正是 in _backfilled)→「當日補不回」被反證;「混三義」誇大(寫入點僅 2);**建議修法證偽**:_backfill_timeouts 成功不清(僅 1005/1390 清),`or key in ...` 會讓逾時一次後成功的檔整天繞過 guard。 |
| 2 | MED | CONFIRMED | LOW | on_reconnect 唯一產生點 tc4.py:1235-1236 核實;_heal→_heal_resub→_resub 全程不呼叫;決定性佐證 = stock_source.py:42-44 承重註解(pr-126 F-01 理由)被 PR 砍掉其點名救援之一;R2 門檻 60s 頻率不低;警告:照字面修會放大 churn,正解改口。 |
| 3 | LOW | CONFIRMED | LOW | 四處核實;行號兩處偏 2(app.py:1559、stock_source:42-44);1190 是前提削弱非證偽。 |
| 4 | LOW | CONFIRMED | LOW | mutation:guard 換 _backfill_wanted → test_stock_engine 186 passed、tests/server 全量 1336 passed;已還原並清 pycache。 |
| 5 | LOW | PARTIAL | LOW(參考用) | 重複真;風險假(30 是護欄非業務常數、14>10 安全、超界 24h 有界收斂);兩支域不同不可互換(ISO+UTC vs 本地 Date;「今天開點已過」無對應概念)。 |
| 6 | LOW | PARTIAL | LOW | baseline 全 repo 函式形 refetchInterval 掃描:全部常數/false/秒級量化,groupPollInterval 盤外是唯一未量化 → 辯護不成立、規則偏離真;但「每秒 render→每秒重排」錯(盤外無 dirty 推播,_flush_watchlist_loop 只推 dirty;殘存 render 驅動 = orders 10s 輪詢);重排用當下剩餘時間,無喚醒誤差;query-core 5.101.2 queryObserver.js:116-117/208-218 核實。 |
| 7 | LOW | CONFIRMED | LOW | grep 全 src 僅定義與唯一讀者;間接覆蓋 4 條;fallback 與 1s 下限(09:00:59.x,open−now 可小到 1ms)確實零覆蓋。 |
| 8 | LOW | CONFIRMED | LOW(參考用) | 8 個字串字面中 7 個為本 PR 新增;但 date-time 無位移形依規格為本地時間,寫法正確;AR8 是 date-only 坑不適用 → 純慣例。 |
| 9 | LOW | CONFIRMED | LOW | :82 尾端「原文:」直斷(len=245 尾字元核過);兄弟條 :80/:81 原文完整 → 漏貼。 |

## Action Items

**Severity calibration**:6c 檢查 —— F-01/F-02 的論式形狀是「移除既有救援路徑」:已走三層意圖查證(PR body 明文拍板 dedup 且記載「切主圖保險由 reconnect 承接」= 設計意圖明確;複查判定為「宣稱過寬」而非「防護誤刪」,invariant 的新 owner = 漲跌停值變入列點(F-01,實測有效)/ 無 owner(F-02,靜默缺口本就無人補,修前救援是意外撿拾));6d-1 無 hedge;6d-2 單軸跳過;6d-3:零 Must 候選(兩條 MED 經複查均降 LOW —— 最壞後果一致為「分時圖靜默缺一段」且有救援/自癒,非錯誤數字或錯誤下單);無作者校準檔。

### Must Fix

無。

### Should Fix

無(兩條 first-pass MEDIUM 經複查證據降級,詳見發現總覽複查欄)。

### Nice to Have(可選優化)

- #1 逾時放棄分帳(注意:簡單修法已證偽,要 _backfill_gave_up set 或判 >MAX)
- #2/#3 三處+四處註解改口(stock_source.py:42-44 承重註解優先,與 code 認知同步)
- #4 補兩條「刻意不擋」測試(mutation 已證現況全綠)
- #6 秒級量化一行 + 1_000 下限理由
- #7 lib 層 describe(fallback + 下限)
- #9 next-time 原文搬回

### 參考用(複查判定非缺陷)

- #5 第二把尺:知識重複真、風險假(護欄非業務常數、域不同不可互換)→ 使用者自行決定要不要補交叉引用
- #8 ISO 字串 Date:寫法依規格正確,AR8 不適用 → 純慣例齊一問題

## 審查工具比較(qualitative)

- 同軸複查此輪糾錯力顯著:反證了 F-01 的「當日補不回」(probe 實測救援路徑)、證偽了 first-pass 的建議修法(_backfill_timeouts 成功不清)、校正了 F-06 的頻率宣稱 —— 三項都改變了處置方向。
- 複查分佈:CONFIRMED 6 / PARTIAL 3 / REFUTED 0 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0;兩條 MEDIUM 全降 LOW,零升級。
- 複查另產出兩條新訊息已併入對應 finding 備註(修法證偽 → #1;stock_source 承重註解 → #2/#3)。

## 沒做的部分(結案對帳)

| 項目 | 狀態 | 理由 |
|---|---|---|
| Codex 中性 / 對抗軸 | FAIL | `codex` CLI 本機不存在 |
| Gemini Flash 軸 | FAIL | `agy` CLI 本機不存在 |
| Gemini Pro 軸 | N-A | opt-in 未啟用 |
| cross-axis verification | N-A | 單軸,同軸 fresh-context 複查代位 |
| blast radius(2.9) | N-A | script 空輸出跳過(有跑,無結果) |
| React-doctor(2.97) | PASS | 已跑,未引入新問題(0 條) |
| C4 formal spec | N-A | SKIPPED(C4_NO_SPEC_DETECTED) |
| 前端 vitest 實跑 | FAIL | worktree 無 node_modules(@tailwindcss/vite 缺)→ 前端斷言以 node 轉寫 + query-core 原始碼直讀代位,第一手但非全套 |
| Gemini quota | N-A | 未跑 Gemini 軸 |
| 未驗證前提 | 無 | 每條 finding 均有第一手執行(probe / mutation / node)或 grep 證據 |

**Self-Verify 修正紀錄**(auditor VERDICT: VIOLATIONS: R9;已修,**未經第二次獨立稽查**):
- R9:React-doctor / blast radius 兩條件式關卡於 header 補明確 PASS / N-A 判定字樣,並補入本對帳表。
