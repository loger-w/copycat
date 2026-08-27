# PR #126 Code Review 比較報告 · SHA d76e8534

**Report projection schema**: 1

**PR**: [loger-w/copycat#126](https://github.com/loger-w/copycat/pull/126)
**標題**: fix(stock): 現貨自癒 / 健檢時窗上界 13:35 → 13:25(收盤試撮起交易所不更新,看門狗每 30 s 誤判 19 發/日)
**作者**: loger-w(commits 署名 Loger)
**分支**: `mod/stock-heal-gate-end-1325` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 dc819faa;回溯 review)
**變更**: 7 檔案, +289 / -14
**審查日期**: 2026-08-27
**Review input basis**: source repo R_kgDOTsITBg + d76e8534b1b199c179c2c754c5ea156d909fbd8f;destination repo R_kgDOTsITBg + 59b70213ca38ad1e4e65f99df99ecc6bf493b6f1;`input_binding: verified`(worktree HEAD = source SHA,`git fetch refs/pull/126/head` 後 rev-parse 逐字相等;destination SHA 為 master 歷史上的既有 commit,`git merge-base --is-ancestor` 成立)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-126`(detached)
**worktree HEAD**: d76e8534b1b199c179c2c754c5ea156d909fbd8f
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer(不切塊,單一 dispatch;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=7 → covered 6 / no-issues 1 / skipped 0 / **missed 0**(chunked: 否;FILE_COUNT=3 源檔 ≤ 15、DIFF_LINES=303 < 800;reviewer 逐檔 accounting 7/7,union = F)
**定位 (ENH-B)**: anchored exact 8 / ambiguous 0 / **FAILED 0**(全部 anchor 於 worktree HEAD 以 grep 逐字比中,line 以比中結果為準)
**React-doctor (2.97)**: N-A(非 React PR:F 無前端檔)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,7 檔全部 authored)
**審查軸狀態**: primary(python-reviewer)PASS(8 findings、7/7 accounting);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條判斷式複查,見備註欄);React-doctor N-A(非 React PR)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus)回 R1–R10 全 PASS、`VERDICT: COMPLIANT`;無需補寫

**Report generation**: sha256:1feb83dc960461065fd8ca49c63f6cdfbda8f306024f30283156d36b7daa3cef

---

## Spec 依據

- 偵測到 `.claude/mod/stock-heal-gate-end-1325/change-spec.md`(/mod 小活分流 change spec:現況 vs 目標、caller map 六讀者、白名單五條 + 已知行為變更、三條代價、留尾;非目標 = 6949 冷門檔 / 第二段閘 / 改長門檻)。
- ⚠️ spec 作者 = PR 作者(同一 session 產出)。本輪 F-01 / F-02 / F-04 三條正是 spec 自述的「事實」與 code / log 對不上 —— 作者自寫 spec 的利益重疊在此具體兌現。

- `SPEC_COMPLIANCE` receipt:gate=SKIPPED;dispatch=NOT_APPLICABLE;dispatch_count=0;reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED(spec 位於 `.claude/<flow>/<slug>/`,不在 authority 允許路徑;同 08-27 #118 判定);requested_model=opus;observed_model=UNAVAILABLE;effort=xhigh;tools=0;0 clauses / 0 findings / 0 observations / 0 invalidated

## 變更概要

provenance:7 authored / 0 inherited(base = master,免驗)。

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `.claude/mod/stock-heal-gate-end-1325/change-spec.md` | 有 finding(新增) | 現況 vs 目標 / caller map / 白名單 / 代價(F-02 代價 (b) 錯、F-04 caller map R1) |
| `.claude/mod/stock-heal-gate-end-1325/code-review-round-1.json` | 無 finding(新增) | in-flow two-axis round 1 處置 |
| `.claude/mod/stock-heal-gate-end-1325/verification.md` | 有 finding(新增) | 紅先行 / 反向驗證 / gate;§6 明寫真環境未驗(F-08 證據來源) |
| `copycat/live/stock_source.py` | 有 finding(修改) | `_TRADING_END` 13:35 → 13:25、`<=` → `<`、~12 行常數註解(F-01 / F-02 / F-03 / F-05) |
| `docs/next-time.md` | 有 finding(修改) | IX0001 兩條勾銷(F-08)、命名 🔵 + 三條代價留尾 |
| `tests/live/test_corr_source.py` | 有 finding(修改) | `TestTwsLegClock` 邊界表改 13:25 False(F-06 註解 mutation 不成立) |
| `tests/live/test_stock_source.py` | 有 finding(修改) | `TestTradingHoursGate` 秒級端點鏡像(F-07 兩份表) |

## 發現總覽

| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | 以 IX0001 單一 symbol 的量測關掉**三個消費者共用**的閘:個股 / 2330 在 13:25–13:30 試撮期仍有 REALTIME 簿更新推播(skill 事實 TradeStatus=1、`_note_push` 不分成交 / 簿更新),那 5 分鐘原本就不會誤判 → 對個股面純粹拿掉收盤集合競價期間的 R1 / R2 / 健檢三條救援路(`copycat/live/stock_source.py`) | HIGH [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Should Fix | `auto-fix` | CONFIRMED(兩日 log 反查);損害是「訂閱若在收盤集合競價期間死掉則整段零訊號」的條件式後果 → 6d-1 hedge cap 不落 Must;修法 = index session 單獨 13:25、個股 / corr 現貨腿留 13:35(注入點現成) |
| F-02 | 代價 (b)「個股側**沒有**當日重補路徑」與實碼不符:`_enqueue_backfill` 五個產出點,`_backfilled` 只擋 `group_snapshot` 60 s 輪詢那條;`set_main_contract` 無條件入列、`_handle_reconnect` 先 clear 再入列、漲跌停值變路徑明確收已回補檔 —— round 1 Spec P2 只證了輪詢那條,disposition 卻放大成「無路徑」並落到四處(`copycat/live/stock_source.py`) | MEDIUM [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | user 知情基礎寫錯(把代價講得比實際嚴重),四處同句改口;非 release-blocking |
| F-03 | 註解斷言「全是誤判」,唯一證據是 19 發 30 s 等距 attempt 全 1;同 PR 保留的 next-time「重掛 snapshot 會清 heal attempts(未證)」與 skill:182 都明寫 attempt 恆 1 不能當證據 —— 現有資料無法區分「交易所不更新」與「訂閱真死 + stub snapshot」(`copycat/live/stock_source.py`) | MEDIUM [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 註解把未證推論寫成事實,與同 PR next-time「未證」條牴觸;改成誠實記帳一句 |
| F-04 | caller map 寫 corr 台積電腿「13:26 起不進 R2 母體」,但逐 symbol 閘在 `_heal_tick:624` **母體形成處**扣除 —— R1 的判定母體與整批重掛清單同一份,2330 同時退出 R1 與 R2:corr session 13:25–13:30 整條被 reap 時 R1 不會救 2330;反向,2330 是該窗少數仍推播的腿,移出母體讓 corr 的 R1 更容易成立(`.claude/mod/stock-heal-gate-end-1325/change-spec.md`) | MEDIUM [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | caller map 漏了 R1 半邊(blast radius 少一半);F-01 修成 per-consumer 後 2330 留 13:35,本條隨之消失,但 spec 文字仍要改對 |
| F-05 | 代價 (a) 引的 `_HEAL_TAIL_END` 13:40 是 `index_engine._broadcast_loop` 的**無日曆**分支;prod 有 `configs/trading_holidays.json` → `_has_calendar` 為真 → 尾段窗 13:25 起到午夜(`copycat/live/stock_source.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 引用到 prod 走不到的分支(低估保護);一句改口 |
| F-06 | `(13, 35, False)` 註解說「改回 13:35 會紅」,但上界已是 end-exclusive:`13:35 < 13:35` 仍 False → value-only revert 這列照綠;真正擋住的是沒註解的 `(13, 26)` / `(13, 30)` 兩列(`tests/live/test_corr_source.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 註解宣稱的 mutation 不成立(end-exclusive 下 13:35 列對 value-only revert 不敏感);註解搬到 13:26 列 |
| F-07 | round 1 S4 的「本檔加鏡像」讓同一函式有兩份邊界斷言:corr 那份 10 列分鐘精度、stock 這份 4 列秒級;本 PR diff 正好示範改一個常數要動兩個測試檔,兩份表已各自漂(F-06)(`tests/live/test_stock_source.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `ask-user` | 兩份邊界表 / 兩種精度分裂真相源;搬表屬測試重組(獨立 🔵),要不要做請 user 決定 |
| F-08 | `verification.md` §6 自己寫「本輪無法當日驗」,同 PR 卻把 next-time 這條與 08-26 N051 那半條都打成 `[x]` + 刪除線 —— 開放項清單是掃留尾的入口,勾掉就不會再被掃到(`docs/next-time.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 真環境未驗先勾銷(鐵則 D);改回 [ ] 標「待次一交易日驗」 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 843b66dc52b26657610c action=auto-fix
F-02 finding_uid: b1fd6242e8826833c831 action=auto-fix
F-03 finding_uid: 8fd09dff4fa10091824e action=auto-fix
F-04 finding_uid: bbb439c7e1a89189bd58 action=auto-fix
F-05 finding_uid: ad462d316b2183e54605 action=auto-fix
F-06 finding_uid: 4412a03121296ae25db3 action=auto-fix
F-07 finding_uid: 80445370ceb8e404e1a4 action=ask-user
F-08 finding_uid: 5742dcb856a879ce5673 action=auto-fix

### Inline Comments per Finding（直接複製貼到 PR review）

#### F-01 這把閘三個地方共用,只量了加權就一起關,個股收盤那 5 分鐘的保護被拿掉了

**File**: `copycat/live/stock_source.py`
**Line**: 34-35

**Comment**:
```
這把 `_TRADING_END` 是三個消費者共用的:個股 session 看門狗 + 健檢、加權 / 櫃買 session、corr 台積電腿。
但「13:25 起交易所不更新 → 全是誤判」只量了 IX0001。個股在 13:25–13:30 試撮期是有 REALTIME 簿更新推播的
(tc4-market-facts:TradeStatus=1、213 筆),`_note_push` 不分成交 / 簿更新都算推播 → 個股那 5 分鐘本來就不會觸發 R1/R2。
反查 08-26 / 08-27 兩天 log:舊閘開著時 13:25–13:35 除了整天在發的 6949,數十檔自選一發都沒有。
所以改 13:25 對個股零收益,只剩代價:收盤集合競價期間訂閱被 TC4 reap 掉,R1 / R2 / 健檢三條救援路全部下班,五檔 / 現價停到重啟、零訊號。

拆成 per-consumer:index session 用 13:25(症狀所在),個股 / corr 現貨腿留 13:35。
注入點現成 —— app._default_index_source 已經是獨立的 StockQuoteSource(in_trading_hours=…),傳另一把 gate 就好,不動簽名。
```

#### F-02 代價 (b) 寫「個股沒有當日重補」是錯的,切主圖或重連都會重補

**File**: `copycat/live/stock_source.py`
**Line**: 38-39

**Comment**:
```
`_enqueue_backfill` 有五個產出點(docstring :1284 自己列的),`_backfilled` 只擋 group_snapshot 那條 60 s 輪詢;
set_main_contract 是無條件入列(:611)、_handle_reconnect 先 clear 再入列(:1044-1046)、漲跌停值變那條更是明確收已回補的檔(:1109-1113)。
round 1 只證了「輪詢那條不補」,寫進註解 / change-spec / next-time / verification 四處時放大成「沒有當日重補路徑」——
把代價講得比實際嚴重,留尾又拿它當「13:30 第二段閘」的價值,前提錯了決策會偏。

四處同步改成:「當日重補只剩 set_main_contract(手動切主圖)與 _handle_reconnect(斷線重連);群組成員 60 s 輪詢被 _backfilled 擋住,不切主圖補不回來」。
```

#### F-03 註解把「全是誤判」寫成事實,同一份 PR 的 next-time 卻說這還沒證

**File**: `copycat/live/stock_source.py`
**Line**: 35

**Comment**:
```
「全是誤判」唯一的證據是 19 發 30 s 等距、attempt 全 1。但這份 PR 自己留的 next-time 寫著:重掛的 SUBQUOTE 會回 snapshot,
`_note_push` 照樣清 attempts → attempt 恆 1 是 snapshot 撐出來的形狀、未證;skill:182 也點名 IX0001 收盤段同理。
所以現在的資料分不出「交易所不更新(誤判)」跟「訂閱真死 + stub snapshot」——後者正是 08-14 凍結 stub 那類病,
關閘就是拿掉加權當日唯一的復原路。這句留在 code 裡會被下一個 session 當事實引。

改成誠實記帳:「19 發全 attempt 1;attempt 恆 1 無法區分誤判與真死(見 next-time『重掛 snapshot 會清 heal attempts』),
本輪按誤判處理,次一交易日 13:36 以 /api/index/state 的 twse 最後更新時戳反證」。
```

#### F-04 caller map 只說 2330 退出 R2,其實 R1 也一起沒了

**File**: `.claude/mod/stock-heal-gate-end-1325/change-spec.md`
**Line**: 31

**Comment**:
```
tc4._heal_tick:621-624 的註解跟實碼都寫「逐 symbol 閘在母體形成處扣除,不是在 R2 迴圈 continue」——
subs 同時是 R1「全部 symbol 都靜默」的判定母體跟重掛清單。所以正確敘述是 2330 同時退出 R1 與 R2。
漏掉的兩個後果:(1) corr session 在 13:25–13:30 整條被 reap,R1 整批重掛清單裡沒有 2330,要到隔天 08:30 才有人救;
(2) 2330 是那 5 分鐘少數仍在推的腿,移出母體等於拿掉它對 R1「有腿在流」的抑制,corr 的 R1 在該段更容易成立。

該格改「13:25 起退出 R1 **與** R2 母體(逐 symbol 閘扣在 tc4._heal_tick:624 母體形成處)」,代價段補第四條。
(F-01 改成 per-consumer 後 2330 留 13:35,這條就自然消失,但 spec 文字仍要改對。)
```

#### F-05 代價 (a) 引的 13:40 是沒日曆才走的分支,prod 其實補到午夜

**File**: `copycat/live/stock_source.py`
**Line**: 37

**Comment**:
```
index_engine._broadcast_loop:653-658 三分支:窗內 True;`elif self._has_calendar` → now >= 13:25 且交易日,**到午夜**沒上界;
`else` 才是 13:25–13:40。prod 有 configs/trading_holidays.json → 走中間那支。註解引 13:40 是 prod 不會走的分支,方向是低估保護。

改成「由 index_engine 尾段回補補齊(有日曆 → 13:25 起到午夜;無日曆退回 _HEAL_TAIL_END 13:40)」。
```

#### F-06 邊界表那句「改回 13:35 會紅」在 end-exclusive 下不成立

**File**: `tests/live/test_corr_source.py`
**Line**: 208

**Comment**:
```
上界改成 end-exclusive 之後,`time(13,35) < time(13,35)` 是 False,跟期望值一樣 → 只把常數改回 13:35 這列照樣綠。
真正夾得住 value-only revert 的是 (13, 26) 跟 (13, 30) 兩列,而它們沒註解 —— 下次有人「精簡邊界表」最可能先刪它們。

註解改口成「舊上界值;end-exclusive 下這列對 value-only revert 不敏感,擋 13:35 復原的是上面 13:26 / 13:30 兩列」,或把註解搬到 (13, 26)。
```

#### F-07 同一把閘的邊界表分兩檔兩種精度,改一個常數要動兩處

**File**: `tests/live/test_stock_source.py`
**Line**: 1233-1235

**Comment**:
```
round 1 用「本檔加鏡像」解「改常數本檔不紅」,結果同一個函式有兩份表:corr 那份 10 列只到分鐘、stock 這份 4 列到秒;
這次改一個常數就同時動了兩個測試檔,而 corr 那份已經帶了一句不成立的 mutation 註解(見 F-06)。

把 10 列表整段搬進 test_stock_source.py::TestTradingHoursGate(常數所在檔、順手升秒級),
test_corr_source.py 只留 segment_leg_gate 前綴分派的測試 —— TestTwsLegClock 本來要證的是「吃的是同一把閘」,一列 13:26 就夠。
屬測試重組(獨立 🔵),要不要做你決定。
```

#### F-08 真環境還沒驗就把 next-time 兩條勾掉了

**File**: `docs/next-time.md`
**Line**: 8-9

**Comment**:
```
verification §6 寫「本輪無法當日驗,要等次一交易日」,同一份 PR 卻把這條跟 08-26 N051 那半條都打成 [x] + 刪除線。
next-time 是掃留尾的入口,勾掉的不會再被掃到;明天 grep 若不是 0 筆(或個股面冒出 F-01 那種新症狀),沒有 open 項承接。

兩條改回 [ ],狀態寫「已出貨待次一交易日真環境驗(13:25 後 IX0001 0 筆 + 13:36 /api/index/state twse 最後更新時戳)」,驗過再勾。
```

### Opus 原始 findings (first-pass, context-aware)

- **F-01**(reviewer 原編號 F-1,HIGH [python-reviewer])`copycat/live/stock_source.py:34-35` —— 以 IX0001 單一 symbol 的量測關掉**三個消費者共用**的閘:個股 / 2330 在 13:25–13:30 試撮期仍有 REALTIME 簿更新推播(skill 事實 TradeStatus=1、`_note_push` 不分成交 / 簿更新),那 5 分鐘原本就不會誤判 → 對個股面純粹拿掉收盤集合競價期間的 R1 / R2 / 健檢三條救援路。anchor:`#: 交易所 13:25–13:30 只收單不撮合、指數也不更新,看門狗在這 5 分鐘 + 13:30 後每 30 s 判一次`。search-proof:grep 零推播自癒 logs/server-20260827-0814.log | grep ' 13:2[5-9]:' | grep -v IX0001 → 只有 6949 ×5;08-26 同形;grep -rn in_trading_hours copycat → 讀者六處三消費者;tc4.py:1060 `_note_push` 無 TradeStatus 過濾
- **F-02**(reviewer 原編號 F-2,MEDIUM [python-reviewer])`copycat/live/stock_source.py:38-39` —— 代價 (b)「個股側**沒有**當日重補路徑」與實碼不符:`_enqueue_backfill` 五個產出點,`_backfilled` 只擋 `group_snapshot` 60 s 輪詢那條;`set_main_contract` 無條件入列、`_handle_reconnect` 先 clear 再入列、漲跌停值變路徑明確收已回補檔 —— round 1 Spec P2 只證了輪詢那條,disposition 卻放大成「無路徑」並落到四處。anchor:`#: 補齊,但**現價欄不會**(回補只寫 minutes);(b) 個股側**沒有**當日重補路徑(`_backfilled` 當日`。search-proof:grep _backfilled|_enqueue_backfill copycat/server/stock_engine.py → 入列 :611/:725/:987/:1046/:1113,guard 只 :719
- **F-03**(reviewer 原編號 F-3,MEDIUM [python-reviewer])`copycat/live/stock_source.py:35` —— 註解斷言「全是誤判」,唯一證據是 19 發 30 s 等距 attempt 全 1;同 PR 保留的 next-time「重掛 snapshot 會清 heal attempts(未證)」與 skill:182 都明寫 attempt 恆 1 不能當證據 —— 現有資料無法區分「交易所不更新」與「訂閱真死 + stub snapshot」。anchor:`#: 「零推播」全是誤判(2026-08-27 IX0001 13:25:46 起 19 發 / 日,每個交易日都在發)。`。search-proof:sed -n 10,14p docs/next-time.md;grep 'attempt 恆 1' .claude/skills/tc4-market-facts/SKILL.md → :182
- **F-04**(reviewer 原編號 F-4,MEDIUM [python-reviewer])`.claude/mod/stock-heal-gate-end-1325/change-spec.md:31` —— caller map 寫 corr 台積電腿「13:26 起不進 R2 母體」,但逐 symbol 閘在 `_heal_tick:624` **母體形成處**扣除 —— R1 的判定母體與整批重掛清單同一份,2330 同時退出 R1 與 R2:corr session 13:25–13:30 整條被 reap 時 R1 不會救 2330;反向,2330 是該窗少數仍推播的腿,移出母體讓 corr 的 R1 更容易成立。anchor:`| `app.py:413` `segment_leg_gate(tws=)` | corr 台積電現貨腿 | 13:26 起不進 R2 母體 |`。search-proof:sed -n 616,626p copycat/live/tc4.py;grep -n 'def segment_leg_gate' -A 30 corr_source.py(TC.S.TWS. → tws())
- **F-05**(reviewer 原編號 F-5,LOW [python-reviewer])`copycat/live/stock_source.py:37` —— 代價 (a) 引的 `_HEAL_TAIL_END` 13:40 是 `index_engine._broadcast_loop` 的**無日曆**分支;prod 有 `configs/trading_holidays.json` → `_has_calendar` 為真 → 尾段窗 13:25 起到午夜。anchor:`#: 訂閱若剛好在 13:25–13:30 死掉,(a) 加權分時由 index_engine 尾段回補(`_HEAL_TAIL_END` 13:40)`。search-proof:sed -n 650,660p copycat/server/index_engine.py;grep _has_calendar → :190
- **F-06**(reviewer 原編號 F-6,LOW [python-reviewer])`tests/live/test_corr_source.py:208` —— `(13, 35, False)` 註解說「改回 13:35 會紅」,但上界已是 end-exclusive:`13:35 < 13:35` 仍 False → value-only revert 這列照綠;真正擋住的是沒註解的 `(13, 26)` / `(13, 30)` 兩列。anchor:`(13, 35, False),  # 舊上界「收盤補正止」:夾到分鐘精度,改回 13:35 會紅`。search-proof:sed -n 455,466p stock_source.py(`< _TRADING_END`);代入 13:35 → False
- **F-07**(reviewer 原編號 F-7,LOW [python-reviewer])`tests/live/test_stock_source.py:1233-1235` —— round 1 S4 的「本檔加鏡像」讓同一函式有兩份邊界斷言:corr 那份 10 列分鐘精度、stock 這份 4 列秒級;本 PR diff 正好示範改一個常數要動兩個測試檔,兩份表已各自漂(F-06)。anchor:`"""`in_trading_hours_now` 是個股 session 看門狗 / 健檢、index session、corr 台積電腿共用的一把閘`。search-proof:grep -rn in_trading_hours tests → test_corr_source.py:198-215 + test_stock_source.py:1237-1241
- **F-08**(reviewer 原編號 F-8,LOW [python-reviewer])`docs/next-time.md:8-9` —— `verification.md` §6 自己寫「本輪無法當日驗」,同 PR 卻把 next-time 這條與 08-26 N051 那半條都打成 `[x]` + 刪除線 —— 開放項清單是掃留尾的入口,勾掉就不會再被掃到。anchor:`- [x] ~~**收盤段 `IX0001` 每 30 s 一發**~~ → 08-27 user 拍板 13:25(mod/stock-heal-gate-end-1325):看`。search-proof:sed -n 52,58p verification.md(§6 次一交易日);grep '^- \[x\]' docs/next-time.md → :8

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查。

### Codex 對 Opus 的複查結果（對稱化 4.2）

**Codex 複查 Opus 失敗 — 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(本機無 codex)。全部 CC finding 視同 INCONCLUSIVE,改由 4.3b 主 agent 逐條判斷式複查(結果在發現總覽「Opus 複查」欄與下方備註):

| Opus # | 原始 severity | 4.3b 判斷 | 備註(他軸為何漏 / 主 agent 實查) |
| --- | --- | --- | --- |
| F-01 | HIGH | CONFIRMED | 主 agent 反查 08-26 / 08-27 兩日 log:舊閘 13:35 仍開時,13:25–13:30 與 13:30–13:35 非 IX0001 的自癒**只有 6949**(整日每分鐘一發的冷門檔),數十檔自選零發 → 個股在該窗持續收推播,關閘對個股零收益。skill:72-73 記試撮期 TradeStatus=1 簿更新 213 筆。round 1 兩軸都沒抓到:兩軸都拿 spec 的「交易所不更新」當前提。 |
| F-02 | MEDIUM | CONFIRMED | 主 agent grep stock_engine.py:`_enqueue_backfill(` 入列點 611 / 725 / 987 / 1046 / 1113,`_backfilled` 判斷只在 719。round 1 的 P2 反被本輪推翻。 |
| F-03 | MEDIUM | CONFIRMED | 主 agent 讀 next-time:10-14 與 skill:182(本 session 稍早自己寫的更正),註解確與之牴觸。若真相是後者,關閘等於拿掉加權當日唯一復原路徑。 |
| F-04 | MEDIUM | CONFIRMED | 主 agent sed tc4.py:616-626:`subs = sorted(... if self._heal_symbol_active(s))` 在 R1 之前,R1 `for sym in subs` 用同一份;CLAUDE.md §4 sparse 條刻意區分兩者。 |
| F-05 | LOW | CONFIRMED | 主 agent sed index_engine.py:650-660 三分支;`_has_calendar = is_trading_day is not None`(:190),app 在日曆檔存在時必傳。 |
| F-06 | LOW | CONFIRMED | 主 agent 代入:time(13,35) < time(13,35) → False = 期望值,列為綠。 |
| F-07 | LOW | CONFIRMED | 主 agent grep in_trading_hours tests → 只有這兩處斷言;本 PR diff 兩檔同時被改。搬表要動既有 corr 測試 → ask-user。 |
| F-08 | LOW | CONFIRMED | 主 agent sed next-time:8-9 與 verification §6;鐵則 D 自動化綠 ≠ Done。 |

## Action Items

**Severity calibration**:6c(移除既有防護類)—— 本 PR **屬**移除既有防護類(關閉 13:25–13:35 看門狗 / 健檢窗):6c 查證 —— spec / commit message 的設計意圖 = 「交易所 13:25 起不更新 → 誤判」,但該前提只以 IX0001 量測(verification §0 的 grep 帶 `| grep IX0001`),個股 / corr 現貨腿無量測;主 agent 以 08-26 / 08-27 兩日 log 反查 13:25–13:30 個股自癒 → 只有 6949(整日 churn 檔),其餘數十檔零發 = 個股在該窗仍收推播、原本沒有誤判 → 對這兩個消費者是**純防護削弱**,invariant 無人接手(F-01 CONFIRMED,升 Should Fix);6d-1 hedge cap / 6d-3 Must Fix 雙半條件逐條套用(見各條 Action 理由);6d-2 由 4.3b 取代;provenance cap N-A。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix（合併前必修）

- 無

### Should Fix（強烈建議）

- F-01 這把閘三個地方共用,只量了加權就一起關,個股收盤那 5 分鐘的保護被拿掉了(`copycat/live/stock_source.py:34-35`)—— CONFIRMED(兩日 log 反查);損害是「訂閱若在收盤集合競價期間死掉則整段零訊號」的條件式後果 → 6d-1 hedge cap 不落 Must;修法 = index session 單獨 13:25、個股 / corr 現貨腿留 13:35(注入點現成)

### Nice to Have（可選優化）

- F-02 代價 (b) 寫「個股沒有當日重補」是錯的,切主圖或重連都會重補(`copycat/live/stock_source.py:38-39`)—— user 知情基礎寫錯(把代價講得比實際嚴重),四處同句改口;非 release-blocking
- F-03 註解把「全是誤判」寫成事實,同一份 PR 的 next-time 卻說這還沒證(`copycat/live/stock_source.py:35`)—— 註解把未證推論寫成事實,與同 PR next-time「未證」條牴觸;改成誠實記帳一句
- F-04 caller map 只說 2330 退出 R2,其實 R1 也一起沒了(`.claude/mod/stock-heal-gate-end-1325/change-spec.md:31`)—— caller map 漏了 R1 半邊(blast radius 少一半);F-01 修成 per-consumer 後 2330 留 13:35,本條隨之消失,但 spec 文字仍要改對
- F-05 代價 (a) 引的 13:40 是沒日曆才走的分支,prod 其實補到午夜(`copycat/live/stock_source.py:37`)—— 引用到 prod 走不到的分支(低估保護);一句改口
- F-06 邊界表那句「改回 13:35 會紅」在 end-exclusive 下不成立(`tests/live/test_corr_source.py:208`)—— 註解宣稱的 mutation 不成立(end-exclusive 下 13:35 列對 value-only revert 不敏感);註解搬到 13:26 列
- F-07 同一把閘的邊界表分兩檔兩種精度,改一個常數要動兩處(`tests/live/test_stock_source.py:1233-1235`)—— 兩份邊界表 / 兩種精度分裂真相源;搬表屬測試重組(獨立 🔵),要不要做請 user 決定
- F-08 真環境還沒驗就把 next-time 兩條勾掉了(`docs/next-time.md:8-9`)—— 真環境未驗先勾銷(鐵則 D);改回 [ ] 標「待次一交易日驗」

### 參考用（任一軸驗證為 REFUTED 或 OUT_OF_SCOPE）

- 無

## 審查工具比較 (qualitative)

- CC 視角(python-reviewer):抓到 spec 三處「事實」與 code / log 不符(F-01 三消費者共用閘只量了一個、F-02 個股重補路徑、F-04 R1 母體),以及 F-03 把未證推論寫成註解事實 —— 全是 in-flow two-axis round 1 沒抓到的,且 round 1 Spec 軸的 P2-2 結論反被本輪推翻(放大成「無當日重補路徑」)。
- Codex / Gemini:N-A。
- 4.3b:CONFIRMED 8 / 0 降級;F-01 由主 agent 以兩日 prod log 反查 CONFIRMED(見備註)。
- 對抗式第三軸增益:N-A。

## 沒做的部分（結案對帳）

- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(log grep、code 追蹤)。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)。
- 真實環境:PR 出貨在收盤後,prod 15:20 起的 59b70213 不含本 PR;13:25 閘的真環境判準要等次一交易日(verification §6)。**F-01 的處置(per-consumer 閘)應在次一交易日開盤前重啟之前落地**,否則個股面會以削弱後的閘跑一整天。
- 未驗證前提:F-03 指出「全是誤判」與「訂閱真死 + stub snapshot」兩假說以現有資料不可分(next-time 已列量法);F-01 的反查是「無自癒 ⇒ 有推播」的推論,未直接量個股 13:25–13:30 的推播筆數(只聽不訂 probe 可補)。
- Self-Verify:已執行,COMPLIANT(auditor 以 Read 讀取草稿檔本身,未讀其他產物)。
