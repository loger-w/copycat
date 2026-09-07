# PR #175 Code Review 比較報告 · SHA 4ce9acf7
**Report projection schema**: 1

**PR**: [loger-w/copycat#175](https://github.com/loger-w/copycat/pull/175)
**標題**: feat: 盤前選股篩選 —— 三硬條件 → 自選群組「盤前篩選」(#173)
**作者**: XU MIN YU(loger-w)
**分支**: `feat/premarket-screen` → `master`(PR 已 rebase merge、遠端分支已刪;review 環境以 `refs/pull/175/head` 重建)
**變更**: 20 檔案, +1087 / −17
**審查日期**: 2026-09-01
**Review input basis**: source repo `R_kgDOTsITBg` + `4ce9acf72420217b98dda307c472aa7e88629977`;destination repo `R_kgDOTsITBg` + `d6655611d5fa90ff3475d99f207e9910b7a7bdbf`;input_binding: verified(worktree HEAD 逐字節等於 source SHA;base 以精確 SHA 釘定並可解析)
**Review continuity**: source_continuity=CURRENT(產報告前重抓 headRefOid 仍為 4ce9acf7);base_changed=true(master 已因本 PR 自身的 rebase merge 前進至 be70d745 —— diff 基準 d6655611 為 PR API 之 baseRefOid,不受影響);review_context_changed=false
**審查工具**: CC context-aware reviewer agents(primary ×2 chunks)+ 同軸替代驗證(獨立 code-reviewer 踢館 + 突變體實跑 + 主 session 交易日 live re-probe)。Codex 中性、Codex 對抗、Gemini Flash、Gemini Pro 四軸因本機無對應 CLI 全數缺軸 —— 本輪為 CC 單軸 + 同軸驗證,非 cross-axis,詳「沒做的部分」
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary=python-reviewer ×2 chunks(requested=opus / observed=opus);verifier=code-reviewer(requested=opus / observed=opus);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED 未派);Codex=UNAVAILABLE(CLI 不存在);Gemini=UNAVAILABLE(agy CLI 不存在)
**覆蓋 (ENH-A)**: |F|=20 → covered 13 / no-issues 7 / skipped 0 / missed 0(chunked: 是 —— DIFF_LINES 1104 > 800 門檻;chunk A = 10 檔 runtime+docs、chunk B = 10 檔 tests+前端契約)
**定位 (ENH-B)**: anchored exact 18 / ambiguous 0 / FAILED 0(另 1 條為缺失型 anchor:<none>,不計)
**React-doctor (2.97)**: 未引入新問題(--scope changed --base d6655611 實跑,diagnostics 0;既有 0 條)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_AUTHORITY)
**Blast radius (2.9)**: 空輸出跳過(sem CLI 未安裝,script 無輸出)
**Codex preset (2.98)**: 未詢問(codex CLI 不存在,中性/對抗兩軸缺軸,preset 選擇無意義)
**Gemini 軸 (2.96)**: 未詢問(agy CLI 不存在;Flash 永久軸缺軸、Pro N-A)
**Quota (Gemini 軸)**: 未取 dashboard snapshot(軸未跑)
**審查軸狀態**: primary(python-reviewer ×2 chunks)PASS(逐檔 accounting 齊);domain reviewers N-A(security / spec-compliance 未觸發);Codex 中性 FAIL(CLI 不存在);Codex 對抗 FAIL(CLI 不存在);Gemini Flash FAIL(CLI 不存在);Gemini Pro N-A(opt-in 未啟用且 CLI 不存在);cross-axis verification FAIL → 以同軸替代驗證執行(獨立 code-reviewer 踢館,20/20 條逐條 verdict + 3 隻突變體實跑 + 1 條主 session live re-probe 翻案實錘);C4 N-A(gate SKIPPED)
**校準套用**: 無作者校準檔(xu-min-yu.md 不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master)
**worktree**: C:\side-project\copycat\.worktrees\review-pr-175
**worktree HEAD**: 4ce9acf72420217b98dda307c472aa7e88629977

**Report generation**: sha256:0999ef463091422df1f01c52fa96066fe22e68ead1c5cc87fd64d78ed9f5a7df

---
## [完整證據副檔](pr-175-review.audit.md)
### finding_uid 索引
[03499e40707d340cac9b](pr-175-review.audit.md#發現總覽) · [ec913f5d92f606cd5a03](pr-175-review.audit.md#發現總覽) · [861a6067c81845284f99](pr-175-review.audit.md#發現總覽) · [6ad76d52a7f7959b9c8b](pr-175-review.audit.md#發現總覽) · [2ff2a7e6adc08e5fc59b](pr-175-review.audit.md#發現總覽) · [530bfacb34823de849db](pr-175-review.audit.md#發現總覽) · [eab0aca742f97b157673](pr-175-review.audit.md#發現總覽) · [728ec98d96f716dfae08](pr-175-review.audit.md#發現總覽) · [44e2bbcdf598321e5e64](pr-175-review.audit.md#發現總覽) · [871a9fe64b312e359d9a](pr-175-review.audit.md#發現總覽) · [8a55f5a618f1c78f00f6](pr-175-review.audit.md#發現總覽) · [dd316c2d41168c5ce6d0](pr-175-review.audit.md#發現總覽) · [7b44ba428995b954b400](pr-175-review.audit.md#發現總覽) · [fd0d4c000519a9199e4e](pr-175-review.audit.md#發現總覽) · [9cff0bf4edf463dd4faf](pr-175-review.audit.md#發現總覽) · [cac7dbd08afd941d78d0](pr-175-review.audit.md#發現總覽) · [08b2795a9eee5d2efced](pr-175-review.audit.md#發現總覽) · [37e91081527510e80916](pr-175-review.audit.md#發現總覽) · [6a2887582577b85c362b](pr-175-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | 嚴重度(原 → 校正) | 複查(同軸替代驗證) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | skill 的 BuyAfterSale 值域是 08-28 調研已判錯的字面,本 PR 原封保留還蓋上 09-01 新日期戳,同句錯誤另新寫進 breadth_fetch 生產註解 | MEDIUM → MEDIUM | CONFIRMED(調研文 190-196 逐字對照) | Should Fix | `auto-fix` | 值域改對 + 註解同步,零行為改動 |
| 2 | 「DayTrading/PriceAdj data_id 必填」是週六空回應誤判 —— 交易日全市場單日查回 2,076/2,812 列;每晚 ~64 次逐檔 fan-out 可收斂成 1 次 | MEDIUM → MEDIUM | CONFIRMED(主 session 交易日 live re-probe 實錘) | Should Fix | `ask-user` | 收斂 fan-out 是行為改動,拍板後另 PR |
| 3 | `logger.exception` 4 個佔位符只餵 3 個引數(缺 `wait`)—— 非預期失敗那條路的格式化 log 行被 logging handleError 吞掉 | HIGH → MEDIUM | CONFIRMED(實跑 repro;stderr tee 檔仍留 chained traceback 故降級) | Should Fix | `auto-fix` | 補一個引數,一行 |
| 4 | +15% 界的 float 未定義:「界上」fixture 實算 15.000000000000014,`<=` 突變體 18 passed 存活;數學上恰 15% 的鏈可落 14.999…被剔 | MEDIUM → MEDIUM | CONFIRMED(突變體實跑存活) | Should Fix | `auto-fix` | 量化後再比 + 真界值測試對 |
| 5 | 「收盤鎖板 = 毫元精確等值、摸板不算」無近界樣本 —— ±1 檔容差突變體 18 passed 存活 | MEDIUM → MEDIUM | CONFIRMED(突變體實跑存活) | Should Fix | `auto-fix` | 補一筆收在漲停下一檔的 case |
| 6 | `fit_group_codes` 預設 `limit=WATCHLIST_LIMIT` 零測試 —— prod 兩條路徑都走預設,`=50` 突變體 156 passed 存活 | MEDIUM → MEDIUM | CONFIRMED(突變體實跑存活) | Should Fix | `auto-fix` | 補一條不帶 limit 的測試 |
| 7 | 缺 breadth 的「資料日回聲」第二道守門 —— 上游回錯日時 ratio 會把單日漲幅複利 20 次,榜單全假且與正常同形;shrink 後 date 欄已丟,只能在 fetch 當下驗 | MEDIUM → MEDIUM | CONFIRMED(breadth_engine 764-767 對照) | Should Fix | `auto-fix` | 沿 breadth 逐字語意加一行 |
| 8 | 上限 50→150 的第四個讀者(group-state 批次上限 app.py:1710)未列契約,route docstring 與 stock_engine / GroupGridView 十餘處「50 檔」預算敘事未跟;篩選群組首日就是 60 檔 | MEDIUM → MEDIUM | CONFIRMED(兩 chunk 同根因合併;讀者鏈逐處查) | Should Fix | `ask-user` | 脫鉤/量測/補列三選一要拍板 |
| 9 | `compute()` 無跨 attempt memo(失敗整輪重抓 21 個 MB 級)+ disposition 排在逐檔查之後 fail-late | MEDIUM → LOW | PARTIAL(機制屬實;3 attempts 最壞 ~246 req ≈ 配額 4%,影響下修) | Nice to Have | `ask-user` | 抄 `_streak_memo` 值不值得由你裁 |
| 10 | 21:20 用完重試預算後 `_gave_up_for` 鎖到隔日 21:00 才重武裝,名單停前一日且無前端可觀測面 | MEDIUM → LOW | PARTIAL(機制屬實;「21:30 才發布」誤讀 —— 晚出的只有量值欄,空資格回應也不耗 attempt) | Nice to Have | `ask-user` | 短週期追抓 or 跨日重武裝,設計取捨 |
| 11 | 快取目錄 `Path("data")/"market"` 是 CWD 相對,breadth 同目錄是 repo-root 錨定 —— 換 cwd 起 server 每次 boot 整輪重跑 | LOW → LOW | CONFIRMED(run.ps1 -WorkingDirectory 現況有緩解) | Nice to Have | `auto-fix` | 改同款 repo-root 錨定 |
| 12 | `--write` 警語理由錯:server 其實每次操作都重讀檔;讀不到的是訂閱池與廣播(症狀 = 空卡片),CLAUDE.md 同句 | LOW → LOW | CONFIRMED(watchlist_service 讀路徑逐行查) | Nice to Have | `auto-fix` | 兩處改寫正確機制 |
| 13 | CLAUDE.md 契約塊標題仍「雙邊同值」/收尾「同時改兩邊」,實列三讀者且缺 group-state 讀者 | LOW → LOW | CONFIRMED | Nice to Have | `auto-fix` | 與 #8 拍板一起改 |
| 14 | `test_put_at_limit_ok` docstring 仍寫「字面 50 …邊界 = 50」,body 已 range(150) —— 後人照 docstring 修回去就毀錨點 | LOW → LOW | CONFIRMED | Nice to Have | `auto-fix` | docstring 三個數字改 150/151 |
| 15 | `test_baseline_day_volume_not_counted` docstring 講的是隔壁那條(灌天量),fixture 是 0 量,零額外鑑別力 | LOW → LOW | PARTIAL(錯配屬實;測試衛生層級) | Nice to Have | `auto-fix` | 刪或改成真對照組 |
| 16 | `_DAILY_MIN_ROWS` 三份字面(breadth/screen/verify)以 parity 測試代替單源;verify.py 第三份未納 parity | LOW → LOW | PARTIAL(Python-Python 雙源+測試是 repo 既有拍板慣例;可留的是第三份未納) | Nice to Have | `ask-user` | 單源 vs 慣例維持由你裁 |
| 17 | `TestReplaceGroup` 三條不斷言 `_publish` 廣播(同檔其他寫入路徑都有)—— replace_group 是唯一後台觸發的寫入 | LOW → LOW | PARTIAL(`_settle` 共用段由既有 15 支測試間接護住,影響下修) | Nice to Have | `auto-fix` | 補兩行斷言 |
| 18 | fixture 註解「漲停 118.8」實為貼 tick 後 118.5;排序測試 3333 收盤 126.5 高於自身漲停 121(物理不可能)無「刻意」註記 | LOW → LOW | CONFIRMED(limit_up_milli 實算) | Nice to Have | `auto-fix` | 改註解 + 補刻意標記或改 4 天窗 |
| 19 | `_to_float` 第三份逐字複製(screening/limit_streaks/backfill_finmind) | LOW → LOW | PARTIAL(雙向交叉指標俱在,「小 helper 複製+同語意指標」是 repo 長期慣例) | 參考用 | `no-op` | 照既有慣例,不動 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 03499e40707d340cac9b action=auto-fix
F-02 finding_uid: ec913f5d92f606cd5a03 action=ask-user
F-03 finding_uid: 861a6067c81845284f99 action=auto-fix
F-04 finding_uid: 6ad76d52a7f7959b9c8b action=auto-fix
F-05 finding_uid: 2ff2a7e6adc08e5fc59b action=auto-fix
F-06 finding_uid: 530bfacb34823de849db action=auto-fix
F-07 finding_uid: eab0aca742f97b157673 action=auto-fix
F-08 finding_uid: 728ec98d96f716dfae08 action=ask-user
F-09 finding_uid: 44e2bbcdf598321e5e64 action=ask-user
F-10 finding_uid: 871a9fe64b312e359d9a action=ask-user
F-11 finding_uid: 8a55f5a618f1c78f00f6 action=auto-fix
F-12 finding_uid: dd316c2d41168c5ce6d0 action=auto-fix
F-13 finding_uid: 7b44ba428995b954b400 action=auto-fix
F-14 finding_uid: fd0d4c000519a9199e4e action=auto-fix
F-15 finding_uid: 9cff0bf4edf463dd4faf action=auto-fix
F-16 finding_uid: cac7dbd08afd941d78d0 action=ask-user
F-17 finding_uid: 08b2795a9eee5d2efced action=auto-fix
F-18 finding_uid: 37e91081527510e80916 action=auto-fix
F-19 finding_uid: 6a2887582577b85c362b action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 這條 BuyAfterSale 的值域 08-28 就查證過是錯的,這次改動把錯字面又蓋了一次新章
**File**: .claude/skills/finmind-conventions/SKILL.md
**Line**: 66-69

**Comment**:
```
docs/research/2026-08-28-instrument-flags-survey.md:190-196 引官方文件已判定:
「＊」= 停先賣後買(仍可先買後賣);「Y」或空白 = 兩方向皆可 —— 不是「'Y' 或 '＊' = 僅可先買後賣」。
survey §4.5 白紙黑字寫「skill 本體修正留給下一輪動手」,這輪動的正是這條,錯值域原封留著
還補了 (2026-09-01 補多方) 的日期戳,看起來像剛複核過 —— 待收修這件事會就此被埋掉。
同一句錯的還新寫進 copycat/server/breadth_fetch.py:153 的生產註解。

改法:值域照 survey 改對,條目內留一行指向 08-28 調研與下游讀者 backfill_daytrade.py:200-202
(那段照錯規則把 'Y' 也剔了,要不要修 code 另案)。
```
#### #2 「data_id 必填」是週六探的假象 —— 交易日全市場一次查得到,64 次逐檔可以變 1 次
**File**: copycat/server/breadth_fetch.py
**Line**: 143-165

**Comment**:
```
probe 當天用的 2026-08-29 是週六 —— FinMind 對非交易日回空 data 陣列,跟 data_id 沒關係。
今天(交易日 09-01)重探:TaiwanStockDayTrading 無 data_id 全市場單日查回 2,076 列、
TaiwanStockPriceAdj 回 2,812 列。所以:
→ 每晚 ~64 次逐檔資格查其實可以是 1 次全市場查詢(7 日回看的權宜也不用了)
→ docstring 與 SKILL.md 寫成既定事實的「data_id 必填」要改
→ 順帶:還原價其實拉得到全市場,自算係數鏈仍可留(已驗證、零額外請求),但「不得不自算」的理由不成立

行為面(收斂 fan-out)要不要動連同 #1 的 skill 修正一起拍板。
```
#### #3 非預期失敗的那行 log 自己會炸 —— 4 個 %,只給了 3 個值
**File**: copycat/server/screen_engine.py
**Line**: 139-144

**Comment**:
```
格式字串有 %s/%d/%d/%.0f 四個佔位符,引數只餵 data_date / attempt / _MAX_ATTEMPTS,
wait 漏了(抄 breadth_engine.py:706 時掉的,那邊 3 對 3 是對的)。
實跑:logging 在 format 階段丟 TypeError → handleError → 這筆 record 的格式化行不會出現,
stderr 只剩 --- Logging error ---(chained traceback 靠 stderr tee 還撈得回,但帶
timestamp/level 的那行 —— 平常 grep 的對象 —— 沒了)。這條 except Exception 正是
「群組再也不更新」的唯一診斷出口。

補 wait, 第四引數就好;順手考慮 ruff select 加 PLE1205/PLE1206,這種 3-vs-4 只有機器攔得住。
```
#### #4 +15% 的界其實沒被釘住 —— fixture 落在 15.000000000000014,恰在界上的檔進不進榜是 float 運氣
**File**: copycat/screening.py
**Line**: 145

**Comment**:
```
還原鏈 94.5/90 × 103.5/94.5 實算是 15.000000000000014,不是 15.0 —— 所以
if ret_pct < RET_MIN_PCT 改成 <= 整套測試照綠(實跑 18 passed)。反向也存在:
數學上恰 15% 的鏈可以算出 14.999999999999968,那檔會被剔,跟拍板「≥ +15% 要收」相反。

建議:比較前先量化(round(ret_pct, 6) < RET_MIN_PCT,跟鎖板判定「毫元整數再比」同精神),
測試補一組真界上 + 界下(+14.999%)對照,並把界值案例從除權息測試獨立出來
(現在唯一的界上覆蓋寄生在除權息 fixture 裡,日後調 fixture 覆蓋會無聲消失)。
```
#### #5 「摸板不算」沒有近界樣本 —— 把差一檔也算鎖板,整套測試照綠
**File**: tests/test_screening.py
**Line**: 79-87

**Comment**:
```
全檔非鎖板樣本離漲停最近也有 4 個 tick,把精確等值改成 ±1 檔容差(abs(...) <= 500)
實跑 18 passed 存活。spec 拍板「毫元精確等值、摸板不算」正是最容易被善意放寬的口徑
(「差一檔也算鎖板嘛」),放寬後榜單多一批非鎖板檔、零紅燈。

補一筆 D1 收在漲停下一檔的 case(prev_ref 100 → 漲停 110.0,收 109.5)斷言不入榜,
可與 test_no_close_lock_excluded 併成參數化兩例。
```
#### #6 prod 真正在用的 fit_group_codes 預設值沒人測 —— 改成 50 全套 156 條照綠
**File**: tests/test_stock_watchlist.py
**Line**: 289-314

**Comment**:
```
TestFitGroupCodes 三條全部顯式帶 limit=2/3;而兩條 prod 寫入路徑
(screen_engine.py:218、cli.py:397)都不傳 limit → 每晚實際截幾檔就看預設綁定。
把預設改成 = 50 實跑四個測試檔 156 passed 全綠存活。CLAUDE.md 剛把這個預設值
登錄成上限契約讀者,目前無機驗。

補一條不帶 limit 的測試(wl 塞滿 WATCHLIST_LIMIT 檔 → 新檔 dropped == 1),
或 assert inspect.signature(...).parameters["limit"].default == WATCHLIST_LIMIT。
```
#### #7 上游回錯日的話,榜單會整份是假的而且看起來完全正常 —— breadth 的第二道守門沒抄到
**File**: copycat/server/screen_engine.py
**Line**: 167-179

**Comment**:
```
breadth_engine.py:764-767 在同樣位置有兩道閘:列數下限(這裡抄了)+
rows[0].get("date") != key(這裡沒抄)。上游忽略日期參數 / 回到別日快取時,
21 個窗格會是同一天 → ratio 把單日漲幅複利 20 次,當天 +1% 的股票變 +22% 還原漲幅、
當天鎖板變 20 次鎖板,整份通過三硬條件寫進群組,與正常名單同形零訊號。
shrink_rows 的 _KEEP_KEYS 不含 date,縮列後就驗不了 —— 只能在 fetch 當下加:

if rows[0].get("date") != d.isoformat(): raise BreadthFetchError(...)
```
#### #8 150 這個數字還有第四個讀者沒列進契約,而且一整族「50 檔」的預算敘事沒人跟
**File**: copycat/server/app.py
**Line**: 1707-1711

**Comment**:
```
/api/stock/group-state 的批次上限直接引 WATCHLIST_LIMIT → 隨 50→150 靜默放寬,
它自己的 docstring 還在用「最多 50 檔 = 每分鐘把主圖搶走 50 次」推理。
同族:stock_engine.py:484/743/856、watchlist_service.py:238、live/stock_state.py:62/240
與 GroupGridView.tsx 八處註解全以 50 檔為前提;篩選群組首日就是 60 檔、上限 3×,
而且這不再需要手動加股 —— nightly 自動灌。

三選一拍板:(a) group-state 上限脫鉤成自己的常數(它守的是單次請求大小不是自選容量);
(b) 維持耦合但補一次 60–150 檔群組檢視實測,並把各處「50」敘事一次改寫;
(c) 至少把 group-state 讀者補進 CLAUDE.md 契約塊。
```
#### #9 一次失敗把 21 個 MB 級全市場回應全部重抓 —— breadth 有 memo,這裡沒有
**File**: copycat/server/screen_engine.py
**Line**: 156-196

**Comment**:
```
compute() 每個 attempt 從頭掃;失敗多半發生在尾段(逐檔資格查 / disposition),
前面 21 個重量級回應是純浪費;disposition(便宜、單次)還排在 ~60 次逐檔查後面 = fail-late。
breadth 的 _streak_memo(breadth_engine.py:214-218)就是為同一題留的。
量級面:3 attempts 最壞 ~246 req ≈ 配額 4%,燒不乾 —— 是頻寬/時間問題不是配額問題。

要抄的話:dict[date, list[dict]] 存 shrink 後的列、expected 換日清空;
disposition 提到逐檔迴圈前。值不值得做由你裁。
```
#### #10 21:20 之後就放棄到隔天晚上,整個白天名單停在舊的、前端看不出來
**File**: copycat/server/screen_engine.py
**Line**: 102-115

**Comment**:
```
重試預算 = 3 次 × 600s ≈ 21:20 用完;_gave_up_for 鎖住後 _sleep_secs 一律睡到
下一個 21:00,expected 整個隔日白天不變 → 常駐 process 要 ~24h 才重新武裝。
名單停前一日時沒有任何面可分辨新舊(無 route 讀 app.state.screen、群組名固定、
premarket_screen.json 要人工開檔)。有一條 logger.error 但只在 boot console。
實務自癒靠「早上重啟 server 清掉 in-memory 旗標」,那是巧合不是設計。

處置(擇一):cached != expected 時睡短週期(1h)直到追上;或 _gave_up_for 跨日曆日自動清。
```
#### #11 快取目錄是 CWD 相對路徑,同一個 data/market 在 breadth 是 repo-root 錨定
**File**: copycat/server/screen_engine.py
**Line**: 80

**Comment**:
```
breadth 的預設是 Path(__file__).resolve().parents[2] / "data" / "market"(app.py 註解
明寫 repo root);這裡是 Path("data")/"market" 吃 cwd。run.ps1 有 -WorkingDirectory
所以 prod 今天不會踩,但換個 cwd 起 server(側車/服務包裝)→ _cached_data_date()
永遠 None → 每次 boot 整輪重跑(2–4 分鐘)並重寫群組,零訊號。

改成跟 breadth 同款錨定就好。
```
#### #12 --write 的警語理由寫反了 —— server 讀得到檔,跟不上的是訂閱和廣播
**File**: copycat/cli.py
**Line**: 148-152

**Comment**:
```
WatchlistService 沒有記憶體快取,每次操作都 load_watchlist 重讀檔;GET watchlist 也直讀。
所以「server 讀不到這次變更」是錯的心智模型 —— 真實症狀是:檔上多了 ~60 檔、
前端重整看得到群組,但這些檔沒訂閱(set_watchlist / _publish 只在 _settle 發生)
→ 卡片全空逐格「-」。照「讀不到」去排查會查錯方向。CLAUDE.md §1 那行同句。

兩處改成「訂閱池與前端廣播不會跟上 → 新增檔在畫面上是空卡片」。
```
#### #13 契約塊的標題還是「雙邊」,正文已經三個讀者了
**File**: CLAUDE.md
**Line**: 171-176

**Comment**:
```
標題「自選上限常數雙邊同值」與收尾「改值 = 改契約要同時改兩邊」是 50 時代措辭;
本 PR 已把讀者補成三個,§4 其他契約塊用的是「同時改各邊」。group-state 讀者(#8)也缺席。
跟 #8 的拍板一起改:標題改「多邊同值」、收尾「同時改各邊」、讀者補齊。
```
#### #14 這段 docstring 指著錯的數字,照它「修正」回去就毀掉唯一的邊界錨點
**File**: tests/server/test_stock_routes.py
**Line**: 208-218

**Comment**:
```
body 已是 range(150),docstring 還寫「字面 50 …成對釘死邊界 = 50」。
這段 docstring 是「為什麼寫字面值不引常數」的唯一說明 —— 現在它指錯數字,
後人依它把 body 修回 50 的話,上限的測試錨點就靜默失準(正是它自己警告的失效樣態)。
三個數字改 150/151。
```
#### #15 這條測試的 docstring 講的是隔壁那條 —— 自己其實測不出東西
**File**: tests/test_screening.py
**Line**: 100-108

**Comment**:
```
docstring 說「基準日灌天量也救不了」,fixture 卻是 vol_shares=0.0;真的灌天量的是
上一條 test_volume_below_threshold_excluded(999,999,000)。而本條跟
test_pass_all_three_conditions 的差異只有基準日量欄 —— 那是迴圈根本不讀的欄,
斷言又只有 len == 1。「基準日也計量」的突變體在本條照綠,殺它的是隔壁的 avg_lots 斷言。

二選一:刪掉(覆蓋已由鄰居提供);或改成真對照組(灌天量 + assert avg_lots == 5000.0)。
```
#### #16 三份 25_000:兩份有 parity 測試,第三份沒人管
**File**: tests/server/test_screen_engine.py
**Line**: 13-15

**Comment**:
```
breadth_engine / screen_engine 的 _DAILY_MIN_ROWS 有 parity 斷言了,但 verify.py:167
的 _DAILY_PAD_ROWS = 25_000(註解明說刻意不 import breadth_engine 免拖 fastapi)
是第三份,耦合關係沒被任何測試釘住。
「Python-Python 就該單源」在本 repo 不成立 —— index 自癒閘就是拍板過的雙源+parity
(pr-128 F-06),所以維持 parity 形狀 OK;要不要把 verify.py 那份也納進 parity 由你裁。
```
#### #17 replace_group 是唯一後台自動觸發的寫入,偏偏它的測試沒驗廣播
**File**: tests/server/test_watchlist_service.py
**Line**: 701-712

**Comment**:
```
同檔其他寫入路徑的成功測試都釘三段(落檔 → set_watchlist → _publish),
TestReplaceGroup 只驗前兩段。廣播漏發的症狀 = 前端側欄整晚不知道群組換過、要手動重整,
零錯誤訊號。_settle 是共用段所以現在間接有護 —— 補兩行把它變成直接的:

test_creates_group_when_missing 加 assert engine.published == [{"type": "watchlist_changed"}]
test_same_codes_is_noop 加 published 筆數不變。
```
#### #18a fixture 註解的漲停數字沒貼 tick
**File**: tests/test_screening.py
**Line**: 80-81

**Comment**:
```
108_000×11//10 = 118_800,貼 500 毫 tick 後漲停是 118.5,註解寫的 118.8 是
未貼 tick 的中間值(結論「未到」仍對,數字錯)—— 「貼 tick」正是這模組最容易寫錯的一步,
讀者照抄會算錯。改「漲停 118.5(118.8 貼 0.5 元 tick)」。
```
#### #18b 排序測試的 3333 收盤價高於自己的漲停,現實不可能
**File**: tests/test_screening.py
**Line**: 195

**Comment**:
```
3333 收 126.5,但 prev_ref 110 的漲停是 121.0 —— 收盤高於漲停,物理上不可能;
沒有任何「刻意」註記。之所以要這樣,是三天窗湊不出「漲幅更高但最近鎖板日更舊」。
日後若加「收盤 > 漲停 = 髒資料不判」守門,這條會離奇紅掉。
改 4 天窗用合法價(_days 補一個日期),或註明「刻意用不可能收盤壓縮窗長,僅為排序鍵服務」。
```
## 沒做的部分（結案對帳）
- Codex 中性軸:FAIL —— codex CLI 不存在於本機,無 diff-only fresh-eyes 對照。
- Codex 對抗軸:FAIL —— 同上,無紅隊視角。
- Gemini Flash 軸:FAIL —— agy CLI 不存在(永久軸缺軸)。
- Gemini Pro 軸:N-A —— opt-in 未啟用且 CLI 不存在。
- Cross-axis verification:FAIL → 以同軸替代驗證執行(獨立 code-reviewer;PASS,20/20 verdict + 3 突變體 + 1 live re-probe)。「同模型家族互驗」的盲區(兩軸犯同種 no-context 錯誤互相免罪)無法排除。
- spec-compliance-reviewer(C4):N-A —— gate SKIPPED(spec 為 GitHub issue 非 repo 檔)。
- security-reviewer:N-A —— 觸發條件不成立(無 auth / request-body / 新 env 面)。
- Blast radius(2.9):N-A —— 跑了、空輸出跳過(sem CLI 未安裝;「沒跑」與「跑了沒結果」有分)。
- React-doctor(2.97):PASS —— worktree 實跑 `--scope changed --base d6655611`,diagnostics 0。
- 作者校準(2.2):N-A —— 無校準檔,報告帶三態句。
- Provenance(2.55):N-A —— base = master。
- Gemini quota snapshot:N-A —— 軸未跑,未取。
- 未驗證前提:F-02 的「fan-out 可收斂 1 次」已由 live probe 驗證全市場查詢可行,但「單次查詢的 BuyAfterSale 欄位完整性與逐檔一致」未逐檔比對(收修時要抽驗);F-10 的「上游 EOD 何時落檔」僅有 09-01 一晚樣本(21:0x 已可得),發布時刻的日間分佈未量測。
- Step 8 post to PR:N-A —— 未執行(預設不執行;PR 已 merge)。
- **Self-Verify 修正紀錄**:auditor 判 VIOLATIONS: R6, R9 —— R6(absence 型 finding 的 search-proof 未落草稿)以 reviewer 原始輸出的實跑查詢補寫成「Absence / 措辭型 finding 的 search-proof」節;R9(條件式關卡缺 PASS/FAIL/N-A 裁決字樣)已在本節逐項補上裁決標籤。兩項皆為既有執行證據的補寫、非補跑;**未經第二次獨立稽查**。
