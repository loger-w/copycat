# PR #165 Code Review 比較報告 · SHA 7887075f

**Report projection schema**: 1

**PR**: [loger-w/copycat#165](https://github.com/loger-w/copycat/pull/165)
**標題**: fix(backend): 期貨日 K daily cache 加定稿界 14:00 —— 夜盤段不再是早上快照
**作者**: loger-w
**分支**: `fix/futures-daily-cache-night` → `master`
**變更**: 7 檔案, +399 / -18
**審查日期**: 2026-08-31
**PR 狀態**: MERGED(post-merge 審查;findings 以留尾 / 收修 PR 處置)
**Review input basis**: source repo id `R_kgDOTsITBg` + source SHA `7887075f877386f47c2007a94ffab9108ab08411`;destination repo id `R_kgDOTsITBg` + destination SHA `7d121a02940d93974919df1f06a63aa5824b305b`;`input_binding: verified`(worktree HEAD == source SHA 精確比中;diff 以 merge-base `68833b6c` 三點語意計)
**Review continuity**: `source_continuity=CURRENT`(head OID 未變;分支已隨 rebase merge 刪除);`base_changed=true`(origin/master 已前進至 `81ab5d05`,含本 PR 之 rebase merge 與後續 #166);`review_context_changed=true`(通知性質;本輪無 PR mutation 計畫)
**審查工具**: CC (Fable 5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A** + Codex 對抗式 **N-A** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 內部複查替代、非跨軸**)+ Gemini 軸 **N-A**(本機無 `codex` / `agy` CLI,四軸全數不可用;Step 2.96 / 2.98 詢問因軸不可用而略過,degrade 依 Error Handling「CC 軸必備、其餘軸缺席註明」)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewer=python-reviewer(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=7 → covered 4 / no-issues 3 / skipped 0 / **missed 0**(chunked: 否,3 source 檔 / 417 diff 行低於門檻)
**定位 (ENH-B)**: anchored exact 10 / ambiguous 0 / **FAILED 0**(F-01 雙 anchor 各一)
**React-doctor (2.97)**: N-A(非 React PR — F 無 .jsx/.tsx,唯一前端檔 day-bars-rollover.ts 為 .ts 純註解)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_IMPLEMENTATION_BINDING_CLAUSE)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 執行、零輸出)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer)PASS(9 findings + 7/7 per-file accounting)/ security-reviewer N-A(無 trigger 面)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 FAIL(`codex` CLI 不存在於本機,`which codex` 空)/ Codex 對抗 FAIL(同上)/ Gemini Flash FAIL(`agy` CLI 不存在,`which agy` 空)/ Gemini Pro N-A(未 opt-in 且 CLI 不存在)/ cross-axis verification FAIL(無第二獨立軸)→ 以 CC 內部複查(code-reviewer,9/9 verdict)替代,結果標示為**同軸內部複查、非跨軸證據**
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-165`
**worktree HEAD**: `7887075f877386f47c2007a94ffab9108ab08411`

**Report generation**: sha256:5e149db4261f89b8e1fceb40db36ab1f5a4c908c96b5f9c324a6ce56e330144a

---

## Spec 依據

- 偵測到 spec / plan 檔(路徑 `.claude/bug/` 不在 Step 2.6 heuristic 清單,由 main session 判斷納入 —— 三檔即本 /bug 的 originating spec):
  - `.claude/bug/futures-daily-cache-night/diagnosis.md` — 紅迴圈、H1–H3 假說、候選 (a)/(b)/(c) 拍板((b) 定稿界 14:00 + 墊背)、blast radius、**明文 non-goals**:前端午夜界不動(next-time)、交易日曆耦合刻意拿掉、DailyEntry 收攏延後。
  - `.claude/bug/futures-daily-cache-night/verification.md` — gate 清單(pytest 3213/3216、前端 2914、validate 42/42)、反向驗證、真實環境判準 1–5(留 user)。
  - `.claude/bug/futures-daily-cache-night/code-review-round-1.json` — 出貨前已跑過一輪 two-axis review:收 J1/J2/J5/J7/S-1/S-2/S-7、J3 入 next-time、J4/J6/S-3/S-4 知情反駁。
- **⚠️ spec 作者 = PR 作者**(loger-w;out-of-scope 判定以此 spec 為據時,注意作者自寫 spec 的利益重疊)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_IMPLEMENTATION_BINDING_CLAUSE`(三檔皆非正式 plan / 診斷散文,無帶穩定 path:line 的 NORMATIVE_KEYWORD / INVARIANT / FORMULA / STATE_TRANSITION / ERROR_CONTRACT 條款)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tools=N-A;accounting:0 clauses / 0 admitted findings / 0 observations / 0 invalidated。
- **Reducer 安全投影**:C4 未派 → reducer(`pr-review-c4.py`)未執行、不存在任何 `human_projection` 或 `invalidated` 集合;本報告零 C4 來源內容,`invalidated_ids ∩ report_finding_ids = ∅` 恆真(空集),無 invalidated 語意可外洩 —— Step 5.0 的 C4 兩條 checklist 以空集滿足。

## 變更概要

provenance: N-A(base = master)

| 檔案 | 類型 | 說明 |
|---|---|---|
| `copycat/server/bars.py` | 行為修復 + 收修重構 | `_daily` memo 加定稿界 `DAILY_FINAL_TIME=14:00`(界前快照過界作廢一次、界後寫入定稿)+ `daily_stale` 墊背(refetch 空手回舊快照、status/tag 不洗白)+ `_daily_stale_or_empty` / `_shaped` 抽共用 |
| `tests/server/test_bars.py` | 測試 | `TestDailySnapshotFinality` 8 條(紅先行 6 + review S-1/S-2 補 2)+ `_TaggedFetcher` 替身 + `_mutable_clock` |
| `frontend/src/lib/day-bars-rollover.ts` | 純註解 | 修正「15:01–24:00 再怎麼問都同一份」的過時敘述(該留尾即本 PR) |
| `docs/next-time.md` | docs | 銷 08-30 條 + 08-31 三條留尾 |
| `.claude/bug/futures-daily-cache-night/diagnosis.md` | artifact | 診斷 + 拍板 |
| `.claude/bug/futures-daily-cache-night/verification.md` | artifact | 驗證證據 |
| `.claude/bug/futures-daily-cache-night/code-review-round-1.json` | artifact | 出貨前 two-axis review 處置 |

表結構註:單軸 run(Codex / Gemini 四軸 N-A → 發現總覽無對應欄;「內部複查」= 同軸 code-reviewer,非跨軸)。零 Must Fix / 零 Should Fix:主軸即判零 CRITICAL/HIGH,內部複查再把 3 條 MEDIUM 全數降 LOW(因果鏈或 baseline 反證,逐條見複查表)。

## 發現總覽

| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `DAILY_FINAL_TIME=14:00` 與 app.py `_calendar_crosscheck` 的 14:00 是兩份互不知情的字面值 | MED | PARTIAL(降 LOW:兩 predicate 語意不同、「誤發 WARNING」因果鏈不成立) | Nice to Have | `auto-fix` | 各補一行交叉註記即可、零行為 |
| F-02 | 墊背路徑零 log、build_period 墊背回應與新鮮取數逐字相同 | MED | PARTIAL(降 LOW:上游 engine 失敗時已有固定可 grep WARNING;真正靜默僅「ok+空」一格;D/W/M 無 status 屬既有白名單) | Nice to Have | `auto-fix` | 比照同檔 584 行慣例補一行 INFO |
| F-03 | 「失敗窗沿 EMPTY_TTL_SECS 重試至成功」措辭與請求驅動現實矛盾(前端三個空態自癒因墊背非空全不觸發) | MED | PARTIAL(降 LOW:行為已是 spec 明文知情留尾、殘留純文字口徑) | Nice to Have | `auto-fix` | 三處文字改口徑、不動 code |
| F-04 | `_period_stale_or_empty` 的 W/M 墊背形狀零測試(`return TaggedBars(stale, tag)` 突變體全綠) | LOW | CONFIRMED(墊背窗週/月 K 可回未聚合日 K、零錯誤訊號) | Nice to Have | `auto-fix` | 既有測試尾補 3 行 `period="W"` 斷言 |
| F-05 | `is_partial_last` tf=D 日曆日判準使大盤頁 14:00–24:00 印「最後一根未收盤」但 bar 已定稿 | LOW | PARTIAL(「修前恰好對」不成立 —— 冷啟動晚問同樣誤標;`is_partial_last` 不在 diff 內、非本 PR 引入) | Nice to Have | `no-op` | 非本 PR 引入;docstring 註記 + 是否讓 D 分支吃界走 next-time /mod |
| F-06 | app.py index_overlay docstring「同日兩端點只發一次 DK 取數」被定稿界改成至多兩次、未同步 | LOW | CONFIRMED(本 PR 造成的 docstring 漂移;共用同格主張仍真、只有次數失真) | Nice to Have | `auto-fix` | 句尾補「至多兩次」一行 |
| F-07 | verification.md「六條」「6 條全綠」是收修前快照,實際 8 條 | LOW | CONFIRMED(同檔下節已載 S-1/S-2 補測與 61 綠、可對帳,僅回校漏做) | Nice to Have | `auto-fix` | 兩處數字回校(repo 有 pr-159 F-03 回校前例) |
| F-08 | prune 對 `_daily_pre_final` 的清理零測試 + 無條件重建 set 與鄰居形狀不一致 | LOW | REFUTED(鄰居 `_daily_tag` prune 306-307 同構、同樣零測試、長期未爆;要補就整段一起、非本 PR 債) | 參考用 | `no-op` | baseline 反證;純記憶體上限 ~code 數×交易日數 |
| F-09 | 界值 14:00:00 整無測試,`>=`→`>` / `<`→`<=` 突變體存活 | LOW | REFUTED(`MIDNIGHT_BUFFER_END` 精確界 00:10 平行未釘、同突變體同樣存活未爆;界上一秒失效方向良性且 S-4 已知情) | 參考用 | `no-op` | baseline 反證;一秒窗無實害 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 1ab4972b2652f1f3829c action=auto-fix
F-02 finding_uid: d94fbd0a11eb597635cc action=auto-fix
F-03 finding_uid: 73c1eac28654d3d11fca action=auto-fix
F-04 finding_uid: 351b6ebfde549a1f39a8 action=auto-fix
F-05 finding_uid: 35896d2b770f096b445d action=no-op
F-06 finding_uid: ce362d0b26e3417b955b action=auto-fix
F-07 finding_uid: 3629a765bb0288390f12 action=auto-fix
F-08 finding_uid: da90790e519259ab1b5e action=no-op
F-09 finding_uid: 88251b4d6e4f18e69457 action=no-op

### Inline Comments per Finding（直接複製貼到 PR review）

#### #1 這個 14:00 在 app.py 還有一份、彼此不知道對方存在

**File**: `copycat/server/bars.py`
**Line**: 73

**Comment**:
```
DAILY_FINAL_TIME = time(14, 0) 跟 app.py:566 _calendar_crosscheck 的 _clock_time(14, 0)
長得一樣但語意不同 —— 這邊問「今日 DK 定稿了沒」(全 code)、那邊問「今日 IX0001 DK
存在了沒」(只 boot 跑一次)。複查過:把這邊往後調不會弄壞那邊的判斷,所以不用 import
同動;但下一個調界值的人會想知道另一份在哪 —— 兩邊註解各補一行「另一個 14:00 讀者在
app.py:566 / bars.py:73,語意不同刻意分家」就好。
```

#### #2 墊背路徑一行 log 都沒有,3am 分不出「定稿到手」還是「一直吃墊背」

**File**: `copycat/server/bars.py`
**Line**: 506-513

**Comment**:
```
_period_stale_or_empty / _daily_stale_or_empty 走到墊背時 payload 跟新鮮取數長一模一樣
(舊 tag 也是 "tc4_dk"),而 D/W/M 又沒有 status 欄。上游 engine 失敗那刻是有固定
WARNING 可 grep 的,真正全靜默的只剩「TC4 回 ok + 空」這一格 —— 但墊背這層自己補一行
比照同檔 build_minute 584 行的慣例最省事:

logger.info("bars %s: 定稿界後 refetch 空手,墊背舊快照(%s)", key, day)

失敗窗最多 15 s 一行,可接受;不想吵就 per (code, day) 印一次。
```

#### #3 「重試至成功」這句話會被當自癒承諾讀,實際是「下一個請求才重試」

**File**: `copycat/server/bars.py`
**Line**: 71-72

**Comment**:
```
「refetch 失敗窗沿 EMPTY_TTL_SECS 節奏重試至成功」—— cache 沒有背景 refresher,重試是
請求驅動;而墊背回的是非空快照,前端三條空態自癒(retryEmpty / barsPollInterval /
useIndexOverlay 輪詢)全都以「bars 空」為觸發條件 → 掛著的分頁到午夜前不會再問,實務上
等於 F5 才重試。行為本身是 next-time 已知情的留尾、不用動 code,但這句(bars.py doc +
diagnosis.md + review JSON S-7 同句)改成「失敗窗的重試由下一個請求驅動,節奏上限
EMPTY_TTL_SECS 一次」比較不會誤導。
```

#### #4 墊背窗的週/月 K 沒測到 —— `_shaped` 那行改壞會拿日 K 冒充週 K

**File**: `copycat/server/bars.py`
**Line**: 513

**Comment**:
```
_period_stale_or_empty 裡的 _shaped(stale, period) 是它四個呼叫點裡唯一沒測試蓋的
(tests 裡 build_period 13 處全是 "D")。把它改成 return TaggedBars(stale, tag) 突變體
全綠 —— 失效樣態是墊背窗內週/月 K 直接回最多 1500 根日 bar,圖照樣畫得出來零訊號。
test_period_expired_refetch_empty_falls_back_to_stale 尾巴補一次 period="W" 請求、
斷言根數 < 日 bar 數,3 行了事。
```

#### #5 大盤頁 14:00 後印「最後一根未收盤」是錯的 —— 但不是這個 PR 弄的

**File**: `copycat/server/bars.py`
**Line**: 454-455

**Comment**:
```
不是 PR 缺陷、先講清楚:is_partial_last 的 tf=D 判準是「末根日期 == 今日」,大盤頁
tf=D 在 14:00–24:00 會一直印「· 最後一根未收盤」(MarketChart.tsx:162),但那根 13:30
就收了。這判準在本 PR 之前就這樣(冷啟動晚問同樣誤標),is_partial_last 也不在 diff 內
—— 只是定稿界讓「拿到定稿 bar + 標未收盤」的時段變常態。期貨側不受影響(futures-overlay
明寫不吃 partial_last)。建議 docstring 補一句「與 DAILY_FINAL_TIME 是兩個口徑」,
D 分支要不要吃界另開 /mod。
```

#### #6 index_overlay docstring 的「同日只發一次 DK」已經不成立了

**File**: `copycat/server/app.py`
**Line**: 1620

**Comment**:
```
「同日兩端點只發一次 DK 取數」—— 定稿界落地後這格同日會作廢一次,成本變「至多兩次
(界前一次、界後定稿一次)」。bars.py 自己的 doc 已改口徑、這句沒跟。這是別人日後估
TC4 取數預算會引用的句子,句尾補一句就好。
```

#### #7 verification.md 的測試數停在收修前快照

**File**: `.claude/bug/futures-daily-cache-night/verification.md`
**Line**: 37

**Comment**:
```
「TestDailySnapshotFinality 六條」「反向驗證 …6 條全綠」是 review 收修前的數字,
S-1/S-2 補的兩條寫在下一節、實檔是 8 條。同檔下節有 61 綠可對帳所以不至於誤導,
但唯一列測試清單的那節跟現況對不上 —— 六→八、並把兩條併進清單(pr-159 F-03 有
回校前例)。
```

#### #8 prune 那行新集合清理沒測試 —— 但鄰居兩行同樣沒測,不是這個 PR 的債

**File**: `copycat/server/bars.py`
**Line**: 308

**Comment**:
```
不是 PR 缺陷:_daily_pre_final 的跨日清理(308)刪掉確實全綠、集合會無界成長 —— 但
緊鄰的 _daily_tag prune(306-307)同構、同樣零測試、長期未爆,失效模式一樣是純記憶體
(上限 ~50 code × 交易日數的 tuple)。要補就兩段一起補 daily_pre_final_count() 型
觀測點,併 test-hygiene 批,不單獨立案。
```

#### #9 14:00:00 整那一秒的包含性沒釘 —— 與 MIDNIGHT_BUFFER_END 同款、一秒窗無實害

**File**: `copycat/server/bars.py`
**Line**: 326

**Comment**:
```
不是 PR 缺陷:>= 與 < 的界上突變體確實存活(測試用 09:00 / 14:01 / 20:00 / 22:00),
但同檔 MIDNIGHT_BUFFER_END 的精確界 00:10 也從來沒釘、同款突變體同樣存活未爆;界上
一秒的失效方向兩邊都良性(多墊背一秒 / 早一秒定稿,後者 review S-4 已知情)。想釘的話
把 test_period_post_final_snapshot_memoized 的 14:01 改成 bars_mod.DAILY_FINAL_TIME
就順便表達了「界上即定稿」。
```

## CC 主軸原始 findings(first-pass, context-aware)

primary = python-reviewer(9 findings + 總評「Warning —— 可合併,零 CRITICAL/HIGH」;修復結構核過:prune 同鍵、跨午夜無復活、`daily_get`→`empty_status`→墊背順序、三引擎 bars_range 降級回空不 raise 故墊背可達;對 add/discard 與兩合取項的心算突變 4 殺)。原始編號 → 本報告編號:主軸 F-01..F-04 → 同號;F-07→F-05、F-08→F-06、F-09→F-07、F-05→F-08、F-06→F-09。各條原始 severity / file:line / problem / impact / fix / search-proof / anchor 全文保留於主軸回報,重點如下:

1. [MED→#1] bars.py:73 vs app.py:566 兩份 14:00 字面值互不知情;search-proof:`Grep "_clock_time|time\(14|14, 0\|14:00" copycat/` 程式碼字面僅兩處。
2. [MED→#2] 墊背零 log + D/W/M payload 無 status;search-proof:`grep -n "logger\." bars.py` 僅 134/584 兩處。
3. [MED→#3] 「重試至成功」與前端三 hook 觸發條件矛盾;search-proof:三 hook 條件逐行讀。
4. [LOW→#4] `_shaped` 第四呼叫點突變體存活;search-proof:tests 內 `build_period(` 13 處全 "D"。
5. [LOW→#8] prune 308 行零覆蓋 + 無條件重建;search-proof:tests 零命中 `_daily_pre_final`。
6. [LOW→#9] 界值 14:00 整無測試;search-proof:test 檔無 `14, 0` / `DAILY_FINAL_TIME`。
7. [LOW→#5] `is_partial_last` 與定稿界兩套口徑,MarketChart 14:00–24:00 印錯話;search-proof:前端 `partial_last` 唯一渲染點 MarketChart.tsx:162。
8. [LOW→#6] app.py:1620「只發一次 DK」失真。
9. [LOW→#7] verification.md 六條 vs 實際八條。

**Per-file accounting(7/7)**:findings → bars.py / test_bars.py / diagnosis.md / verification.md;`REVIEWED_NO_ISSUES` → day-bars-rollover.ts、docs/next-time.md、code-review-round-1.json;`INTENTIONALLY_SKIPPED` → 無。

## Codex 原始 findings

N-A —— 本機無 `codex` CLI,中性與對抗兩軸皆未執行(缺軸已於 header 與「沒做的部分」註明)。

## Gemini 原始 findings

N-A —— 本機無 `agy` CLI,Flash / Pro 皆未執行。

## CC 對非 CC 軸的複查結果(Step 4.1)

N-A —— 無非 CC 軸 finding 可驗。

## 內部複查結果(Step 4.2 之替代;同軸 code-reviewer、非跨軸證據)

Codex 不可用 → 由未參與 first-pass 的 `code-reviewer`(opus)以 4.2 同款測試(事實 / impact / baseline-comparable / runtime-assertion trace / spec-scope)逐條複查。**此為同軸內部複查,不構成 cross-axis 證據;全部 findings 視同無跨軸 CONFIRMED**,Must Fix 候選來源中「cross-axis CONFIRMED」一項本輪不可達。

| # | 主軸 severity | Verdict | 原始 → 校正 | 複查 evidence(摘) | 備註 |
|---|---|---|---|---|---|
| F-01 | MED | PARTIAL | MED→LOW | app.py:538-540 docstring 自陳語意=「存在」非「定稿」、crosscheck 僅 boot 跑一次、改 bars 常數對 app.py 行為零影響;baseline:`session.py:18 _TXO_DAY` vs `index_engine.py:35 _FUT_DAY` 同事實兩份長期未爆 | 「誤發 WARNING」因果鏈不成立;交叉註記仍值得 |
| F-02 | MED | PARTIAL | MED→LOW | futures_engine.py:375/386/389、index_engine.py:576/584、stock_engine.py:784 失敗時有固定 WARNING 可 grep;「D/W/M 不給 status」= app.py:1755-1756 明文白名單 §0.2-1(spec-scope) | 「無法排查」被推翻;殘餘=「ok+空」一格,補 INFO 仍建議 |
| F-03 | MED | PARTIAL | MED→LOW | 三 hook 觸發條件逐行核實屬實;`grep build_period\(|build_daily\(` 僅 app.py 三個 route 呼叫點、無背景 refresher;next-time.md:3-6 與 day-bars-rollover.ts:41-43 明文知情 | 行為=知情留尾;殘留純文字口徑(S-7 成本上界句被當自癒承諾讀) |
| F-04 | LOW | CONFIRMED | LOW→LOW | tests 13 處 build_period 全 "D";test_market_routes.py:114-119 的 W 命中 cache-hit 分支非墊背分支;OTC 迴圈 refusal 早退 | 真覆蓋缺口、突變體存活成立 |
| F-05 | LOW | PARTIAL | LOW→LOW | MarketChart.tsx:162 逐字屬實;futures 側不吃 partial_last 屬實;**反證:修前冷啟動 13:45 後首問回定稿 bar、partial_last 照樣 True** —— 誤標與快照新舊無關;is_partial_last 不在 diff 內 | 非本 PR 引入、本 PR 只提高頻率 |
| F-06 | LOW | CONFIRMED | LOW→LOW | app.py:1619-1620 逐字屬實;bars.py:70-71 已改口徑此句未跟;共用同格主張仍真 | 本 PR 造成的 doc 漂移 |
| F-07 | LOW | CONFIRMED | LOW→LOW | verification.md:37 / :31-33 屬實;實檔 8 條(test_bars.py:722–832);同檔 41-46 已載 61 綠可對帳 | 僅回校漏做 |
| F-08 | LOW | REFUTED | LOW→LOW | 鄰居 `_daily_tag` prune(bars.py:306-307)同構、同樣零測試(全 repo 僅 test_index_routes.py:200 提及且不驗 prune)、長期未爆;刪 308 行零行為差 | baseline test 不過 → 不單獨立案 |
| F-09 | LOW | REFUTED | LOW→LOW | `MIDNIGHT_BUFFER_END` 精確界 00:10 平行未釘(測試凍 00:03/00:15/10:00)、同款突變體存活未爆;界上一秒失效方向良性、早一秒定稿已被 S-4 知情反駁涵蓋 | baseline test 不過 |

## Action Items

**Severity calibration**(SSOT `~/.claude/references/finding-severity-rules.md`):
- 6c Refactor Intent Gate:本 PR 無「移除/削弱既有防護」類 finding → N-A。
- 6d-1 hedge cap:F-01 原文含「真的往後調時」假設性框架 → 複查已降 LOW,cap 自然滿足;其餘無 hedge。
- 6d-2 lone finding:單軸 review 依 SSOT 明文 skip(rule 2 = multi-axis only),不做機械降級。
- 6d-3 Must 雙半條件:零候選(全場 corrected_severity LOW、無 user-visible 重現路徑 + release-blocking 同時成立者)。
- 未驗證前提閘:9 條 evidence 皆第一手(worktree file:line / grep 輸出);F-01 原「誤發 WARNING」前提經複查判不成立、已從 severity 論據移除(MED→LOW 即其結果)。
- Provenance cap:N-A(base = master)。

**校準套用**:無作者校準檔(loger-w.md 不存在)、本輪無套用。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

無。

### Nice to Have(可選優化)

- **#1** bars.py:73 / app.py:566 兩份 14:00 各補一行交叉註記(import 同動經複查判不必要)。
- **#2** 墊背路徑補一行固定字串 INFO(比照 build_minute 584 慣例)。
- **#3** 「重試至成功」三處(bars.py doc / diagnosis.md / review JSON S-7 句)改口徑為「下一個請求驅動、節奏上限 EMPTY_TTL_SECS」。
- **#4** 補 `period="W"` 墊背形狀測試 3 行(殺 `_shaped` 第四呼叫點突變體)。
- **#5** `is_partial_last` docstring 補「與 DAILY_FINAL_TIME 兩個口徑」註記;D 分支要不要吃界 → next-time /mod(非本 PR 引入)。
- **#6** app.py:1620 docstring 補「至多兩次」。
- **#7** verification.md 六條→八條回校。

### 參考用(內部複查 REFUTED)

- **#8** prune `_daily_pre_final` 清理零測試 → 鄰居 `_daily_tag` 同構同樣未測未爆;要補併 test-hygiene 批整段一起,不是本 PR 的債。使用者可自行決定是否仍要求本 PR 範圍補。
- **#9** 界值 14:00:00 包含性未釘 → `MIDNIGHT_BUFFER_END` 平行未釘;一秒窗失效方向良性。想釘 = 把 14:01 換成 `DAILY_FINAL_TIME` 常數一行。

## 審查工具比較 (qualitative)

- CC 主軸(python-reviewer):context-aware,強項在跨檔一致性(兩份 14:00、docstring 漂移、artifact 數字回校)與突變體推演;本輪 9 條全部附 search-proof。
- 內部複查(code-reviewer,同軸):3/9 PARTIAL、3/9 CONFIRMED、2/9 REFUTED、1/9 PARTIAL(非本 PR 引入)—— MEDIUM 全降 LOW。REFUTED 率 22%、降級率 33%:主軸在 cross-cutting baseline 推力下對「新增行零覆蓋」與「字面值重複」有 over-flag 傾向,複查的 baseline-comparable test(鄰居同構未爆)是主要反證來源。
- 重疊率 / 對抗式增益 / Gemini 增益:N-A(單軸 run)。
- **注意**:內部複查與主軸同為 CC,系統性盲點(兩者共享的訓練先驗)無第二軸可對消 —— 本報告的 REFUTED / 降級結論可信度低於正常多軸 run,user 對 #8/#9 保留自行覆判空間。

## 沒做的部分(結案對帳)

| 項目 | 狀態 | 理由 / 證據 |
|---|---|---|
| Codex 中性軸 | FAIL | `which codex` 空 —— CLI 不存在於本機;無 preset 詢問(問了也無法執行) |
| Codex 對抗軸 | FAIL | 同上;preset 一律含對抗的要求在 CLI 缺席下不可達 |
| Gemini Flash 永久軸 | FAIL | `which agy` 空 |
| Gemini Pro opt-in | N-A | 未詢問(CLI 缺席,詢問無意義);依 2.96 預設本應 flash-only |
| Cross-axis verification(4.1/4.2) | FAIL | 無第二獨立軸;以同軸 code-reviewer 內部複查替代並全程標示非跨軸;Must Fix 的「cross-axis CONFIRMED」來源本輪不可達 |
| 4.3a consensus baseline check | N-A | 單軸無 consensus 可言 |
| 4.3b lone-finding 判斷 | N-A | SSOT 6d-2 明文 single-axis skip |
| sem blast radius | N-A | 腳本空輸出跳過 |
| React-doctor | N-A | 非 React PR(F 無 .jsx/.tsx) |
| spec-compliance-reviewer(C4) | N-A | gate SKIPPED(C4_NO_IMPLEMENTATION_BINDING_CLAUSE) |
| security-reviewer | N-A | 無 trigger 面(無 auth/secret/request-body/session/RBAC 變更) |
| Reviewer observed runtime model | 無法取得 | harness dispatch 不回報 runtime model → observed=UNAVAILABLE(requested=opus 有 dispatch 紀錄) |
| Quota snapshot | N-A | Gemini 軸未跑 |
| 未驗證前提 | 無 | 9 條 findings 的 evidence 皆第一手 file:line / grep;F-01 唯一未驗證前提(WARNING 因果鏈)已被複查以第一手證據推翻並降級 |

**Self-Verify 修正紀錄**:auditor(skill-verify:pr-review)判 `VERDICT: VIOLATIONS: R4` —— 原缺口 = 「Spec 依據」的 C4 receipt 未陳述 reducer 安全投影要求;修正 = 補寫「Reducer 安全投影」一節(C4 未派 → reducer 未執行、零 C4 內容、invalidated 交集恆空)與 accounting 四值。R1–R3 / R5–R10 全 PASS。依 Step 6.3 修正後不重派 auditor —— **本報告未經第二次獨立稽查**。
