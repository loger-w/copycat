# PR #220 Code Review 比較報告 · SHA c4e43f67
**Report projection schema**: 1

**PR**: [loger-w/copycat#220](https://github.com/loger-w/copycat/pull/220)
**標題**: refactor(backend): BarsCache 日 K 三份同鍵 dict 收成 _DailyEntry 一格(W3 B1,行為不變)
**作者**: loger-w
**分支**: `refactor/bars-cache-daily-entry` → `master`
**變更**: 10 檔案, +354 / -41
**審查日期**: 2026-09-09
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨;merge commit `def15623`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `c4e43f679f967155300a210747c2c1782db37435`;destination repo id `R_kgDOTsITBg` + baseRefOid `45df8dbd8f8358fa1ca731dc940cb2915969d16e`;`input_binding: verified` —— `git fetch origin refs/pull/220/head` 取回的 commit = headRefOid 逐字相等,review worktree detached 於該 SHA,`git merge-base origin/master HEAD` = baseRefOid
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 SHA;分支已隨 `--delete-branch` 刪除,但 `refs/pull/220/head` 仍指 `c4e43f67`,產報告前重抓 headRefOid 仍為它);`base_changed=true`(origin/master 自 `45df8dbd` 前進至 `def15623`,內容 = 本 PR 自身 4 筆 rebase 後 commit `62cc1cdf` / `be9ec653` / `a6a5662b` / `def15623`,其後零新 commit);`review_context_changed=false`(審的是 PR head,與落地版逐檔等價)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用,沿 #188 / #190 / #199 / #202 / #211 / #218 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .py 100% 的 source 改動,單派不 chunk);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE;純讀碼 + grep baseline);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=10 → covered 4 / no-issues 6 / skipped 0 / **missed 0**(chunked: **否**,2 source 檔 / 137 source diff 行(+97 / −40),低於 15 檔 / 800 行門檻;10/10 per-file accounting 齊)
**定位 (ENH-B)**: anchored exact 5 / ambiguous 0 / **FAILED 0**(五條 anchor 在 worktree 逐字唯一命中:bars.py:219(reviewer 自報 218-219,校正為 219)/ bars.py:604 / test_bars.py:783 / verification.md:58-59 / compare_bars.py:34-35)
**React-doctor (2.97)**: N-A(非 React PR;F 無 .jsx / .tsx)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_CLAUSE)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出;`sem` 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer)PASS(5 findings + 10/10 accounting;另自跑 4000 序列 × 12 步隨機差分驗舊三 dict 版 vs 新版零分歧)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 請求體解析 / 秘鑰讀取)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(5/5 verdict 齊、ID 集合精確相等、每列六欄齊)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-220`
**worktree HEAD**: `c4e43f679f967155300a210747c2c1782db37435`

**Report generation**: sha256:41914dcaf83951cf1ede87c001adabeb20090bef851248e0b55546ba004821fb

---

## Spec 依據

- 偵測到 spec 檔:`.claude/refactor/bars-cache-daily-entry/design.md`(路徑在 `.claude/refactor/` 且為 /refactor 流程的設計記錄;內容 = why gate / seam 判定 / 四條必須保住的 interface 事實 / 不做清單 / 步驟)。關鍵:承諾 = **行為絕對不變**;seam 不動、六個 `daily_*` 公開方法簽名不動;`_DailyEntry` 為 module 內部型別;四條 interface 事實(tag 不被 bars 覆寫帶掉 / 只有 tag 不算快照 / tag put 不動 bars 與標記 / 空 bars 三欄全 no-op)先以 characterization 釘住;**不做**:`daily_put` 簽名加 tag、`build_daily` 補 tag、`_DailyEntry` 加方法。同 PR 內另有 two-axis round-1(`code-review-round-1.json`,Standards 5 + Spec 4)已處置 —— 本輪不重報已修條,只報處置不完整處。
- **⚠️ spec 作者 = PR 作者**(`git log --format='%an' -- .claude/refactor/bars-cache-daily-entry/design.md` = Loger = PR 作者 loger-w;本輪無任何 finding 引 design.md 的不做清單免罪,利益重疊未實際發生作用)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_NORMATIVE_CLAUSE`(design.md 全文無 MUST / SHALL / NEVER 等 normative keyword、無 INVARIANT / FORMULA / STATE_TRANSITION / ERROR_CONTRACT 形式條款;「必須保住的 interface 事實」是白名單敘述、已由 characterization 測試釘住,非可綁 `path:line` 的實作契約)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool calls=N-A(未派);0 clauses / 0 findings / 0 observations / 0 invalidated。reducer 安全投影要求:未派故無 `human_projection`;本報告零 C4 內容,`invalidated_ids ∩ report_finding_ids = ∅`(兩集合皆空),無 invalidated 語意外洩,C4 對 Step 4.5 覆蓋零貢獻。
- Author calibration(Step 2.2):無作者校準檔(`loger-w.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

provenance: N-A(base = master,10 檔全 authored)。

| 檔案 | 類型 | 說明 |
|---|---|---|
| `copycat/server/bars.py` | 修改 | `_daily` / `_daily_tag` / `_daily_pre_final` 三份同鍵 dict → `dict[(code, today), _DailyEntry(bars, tag, pre_final_written_at)]`(裸 `@dataclass`,三欄 Optional);六個 `daily_*` 方法改讀寫 entry(`setdefault` 就地改欄)、`prune` 日 K 段三段收一段;docstring 三處回校(`build_period`「三處 → 兩處」、`_period_stale_or_empty` 註解、`PeriodBars`「pop → 清成 None」);`daily_get` 只有 tag 的格加註 |
| `tests/server/test_bars.py` | 測試 | 新 class `TestDailyEntryFields` 四條 characterization(tag 不被覆寫帶掉 / tag-only 不算快照 / tag put 不動 bars 與標記 / 空 bars 三欄 no-op 含過界不 pop);`TestPhase5Hardening` 兩條 prune 測試的註解回校 |
| `docs/next-time.md` | 文件 | 09-07 盤點 B1「三份同鍵平行結構」條目勾銷 + 出貨註 |
| `.claude/refactor/bars-cache-daily-entry/design.md` | 新增 | why gate / codebase-design 詞彙的 seam 判定 / 四條 interface 事實 / 不做清單 / 步驟(含 round-1 Spec-01 / Spec-04 回校) |
| `.claude/refactor/bars-cache-daily-entry/verification.md` | 新增 | 全量 gate(pytest 3562 / ruff / pyright / validate 42)+ 重構完成判準 + 突變體 3 紅 1 參考 + 側車 master vs worktree 對照表 + 回頭核動機 |
| `.claude/refactor/bars-cache-daily-entry/code-review-round-1.json` | 新增 | two-axis round-1:Standards 5 judgement(S-03 `slots=True` 拒絕)+ Spec 4 nice 全處置 |
| `.claude/refactor/bars-cache-daily-entry/evidence/sidecar_bars.py` | 新增 | 零 ZMQ 側車(neutralize 在 create_app 前、import 錨點 assert、自選檔 tempdir) |
| `.claude/refactor/bars-cache-daily-entry/evidence/compare_bars.py` | 新增 | 兩台側車同請求 diff(8 條路徑) |
| `.claude/refactor/bars-cache-daily-entry/evidence/mutants.txt` / `sidecar-compare-master-vs-worktree.txt` | 新增 | 突變體輸出(M1–M3 紅 / M4 綠)/ 8 列 SAME + RESULT: ALL SAME |

## 發現總覽

| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `bars.py:219` `_DailyEntry` docstring 寫「收成一格後『無快照時標記必也不在』變成**結構保證**」,但三欄型別上各自 Optional、寫入半邊仍是 `daily_put` 的單點約定(只有 prune 半邊結構化);round-1 Spec-01 只回校了 design.md,同源的 code docstring 未同動 | LOW | CONFIRMED(LOW→LOW:純措辭精度、零 runtime;緩解 = 同 docstring 下一句已寫「三欄彼此獨立」、`_period_stale_or_empty` 註解只講機制;grep `結構保證` 全 repo 僅此一處超譯) | Nice to Have | `auto-fix` | 一行改「一條單點約定 + prune 的結構保證」,與 design.md 回校後措辭對齊 |
| F-02 | `bars.py:604` `_period_pre_final` docstring 殘留「標記的 **pop**」,收攏後 `daily_put` 是欄位指派無 pop;round-1 S-04 只修了 `PeriodBars` 那一處。內部複查另找出同型殘留 `bars.py:387`「不 pop 界前標記」與 `test_bars.py:169`「也不 pop 界前標記」,共三處 | LOW | CONFIRMED(LOW→LOW:純詞彙陳舊,句子實質主張重構後更成立;損害 = grep `pop` 會誤中 `bars.py:300` 的真 pop;範圍由 1 處擴為 3 處) | Nice to Have | `auto-fix` | 三處「pop」改「清成 None / 不清標記」,同 S-04 口徑 |
| F-03 | `test_bars.py:783` `_make_mutable_clock` docstring 寫「定稿界**兩個** class 共用的唯一一份」,本 PR 新增第三個呼叫端 `TestDailyEntryFields`(:171);同 PR 為同類理由維護了 `build_period` 的「三處 → 兩處」,此處數字沒跟 | LOW | CONFIRMED(LOW→LOW:測試 helper 註解計數失準、零測試行為;grep 呼叫點 3(171 / 800 / 1049)vs base 2(752 / 1001);該 helper 有 pr-171-review F-12 漂移前科) | Nice to Have | `auto-fix` | 改「三個 class 共用」或去掉數字 |
| F-04 | `verification.md:58-59` 真實環境表 10 列,但 `evidence/compare_bars.py::PATHS` 只 8 條、evidence txt 只 8 列;「分 K `tf=1`」與「`/api/calendar`」兩列(419 B / 183 B 位元組計法)不是該腳本的輸出,重跑對不上列數 | LOW | CONFIRMED(LOW→LOW:證據出處標示不精確非造假;失準的兩列是「未改功能抽查」旁證,不承載行為不變主張;房規是手動 curl 另立小節標示,例 `.claude/mod/bars-tristate-status/verification.md:29`) | Nice to Have | `auto-fix` | 兩條路徑補進 `PATHS` 重跑,或表格註明「手動 curl,不在腳本內」 |
| F-05 | `compare_bars.py:34-35` 只比 A == B、無正確性下限(不驗 200 / bars 非空),兩台同壞仍印 `RESULT: ALL SAME`;port 8731 / 8732 寫死而側車吃 argv | LOW | PARTIAL(LOW→LOW:前半 literally 成立但本次產物逐列 `200/200 … bars=5` + meta 可直讀、兩台同版由 `sidecar_bars.py:37` import 錨點 assert 與 `/api/health` git_sha 守住;後半 REFUTED —— 一次性取證腳本寫死 port、只 print 不 assert 是長期房規:`sc1_api_boundary.py:9` / `poll_futures.py:10` / `restart_trials.py:39` 同型) | 參考用 | `no-op` | 不改;要「取證腳本一律帶下限 assert」是新政策不是本 PR 缺陷,user 拍板才動 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: aacf9021dd35d4406717 action=auto-fix
F-02 finding_uid: 91b5f8d5bdfd76fd699e action=auto-fix
F-03 finding_uid: ca4b2cf3b7fd0fc79fe3 action=auto-fix
F-04 finding_uid: 81816979194749fdfd51 action=auto-fix
F-05 finding_uid: d1b111c45b3f2d4ba518 action=no-op

### Inline Comments per Finding（直接複製貼到 PR review）

#### #1 這句「結構保證」講過頭了,寫入那半還是靠 daily_put 一個人守

**File**: `copycat/server/bars.py`
**Line**: 219

**Comment**:

```
三欄都是 Optional,`bars=None` 配一個非 None 的 `pre_final_written_at` 型別上完全合法 —— 「無快照時標記必也不在」
真正靠的是 `daily_put` 空手早退 + 只在非空 bars 後才寫標記這一條單點約定;結構化的只有 prune 那半(同鍵同格一刀清)。
design.md 在 round-1 Spec-01 已經改口成「一條單點約定 + prune 的結構保證」,這句 docstring 沒跟。
順手對齊一下就好:

    收成一格後 prune 的「同鍵同刪」由結構吸收;「無快照時標記必也不在」的寫入半邊仍是
    `daily_put` 的單點約定(空手早退、標記只隨非空 bars 寫入),不是型別級保證。
```

#### #2 「pop」這個字還留了三處,實作已經沒有 pop 了

**File**: `copycat/server/bars.py`
**Line**: 604

**Comment**:

```
`daily_put` 現在是 `entry.pre_final_written_at = now if now < DAILY_FINAL_TIME else None`,沒有 pop 這個動作;
拿 `pop` 去 grep 只會撞到 :300 的 `_empty.pop`。round-1 S-04 修了 `PeriodBars` 那句,這裡漏了,
同型的還有 :387 註解「含不 pop 界前標記」和 test_bars.py:169「也不 pop 界前標記」。
三處一起改成「清成 None」/「不清標記」跟 S-04 同口徑。
```

#### #3 helper 的「兩個 class 共用」現在是三個

**File**: `tests/server/test_bars.py`
**Line**: 783

**Comment**:

```
`_make_mutable_clock` 這輪多了 `TestDailyEntryFields`(:171,`test_daily_put_empty_is_noop_for_all_three` 推到 14:01 跨界)這個呼叫端,
docstring 還寫「定稿界兩個 class 共用的唯一一份」。這支 helper 就是 pr-171-review F-12 抓過會漂的那一支,
數字寫死下次改凍結點語意的人會漏看第三個。改「三個 class 共用」或乾脆不帶數字。
```

#### #4 表裡那兩列「未改功能抽查」用附上的腳本重跑不出來

**File**: `.claude/refactor/bars-cache-daily-entry/verification.md`
**Line**: 58-59

**Comment**:

```
真實環境那張表有 10 列,但 `evidence/compare_bars.py` 的 PATHS 只有 8 條、evidence txt 也只有 8 列;
`tf=1&days=2` 跟 `/api/calendar` 這兩列(還有「419 B / 183 B」這種位元組寫法)是另外手動 curl 的,
表頭卻寫「compare_bars.py 同請求 diff」。後手重跑對不上列數。
兩條補進 PATHS 重跑一次最乾淨;不然就在表格另立一小節「手動 curl(不在腳本內)」,
房規是這樣標的(例:.claude/mod/bars-tristate-status/verification.md:29)。
```

#### #5 比對腳本只看兩邊一樣,不看兩邊都對 —— 但這次產物看得出來是對的,不用改

**File**: `.claude/refactor/bars-cache-daily-entry/evidence/compare_bars.py`
**Line**: 34-35

**Comment**:

```
不是 PR 缺陷,參考用。`same = (sa, ba) == (sb, bb)` 確實沒驗 200 / bars 非空,兩台同時壞掉也會印 ALL SAME;
但這支腳本每列都印 `{sa}/{sb} bars=N meta=…`,留存的 txt 逐列 `200/200 … bars=5`,下限是看得到的,
兩台「其實同版」也由 sidecar_bars.py:37 的 import 錨點 assert + /api/health git_sha 守住。
port 寫死跟 repo 裡其他一次性取證腳本(sc1_api_boundary.py / poll_futures.py / restart_trials.py)同型,是房規。
要改成「取證腳本一律帶下限 assert」是新政策,不在這個 PR 的帳上。
```

## CC 主軸原始 findings(first-pass, context-aware)

python-reviewer(requested=opus),逐字要點;reviewer 原編號 → 發現總覽:R-01→F-01、R-02→F-02、R-03→F-03、R-04→F-04、R-05→F-05。

#### R-01 [LOW] bars.py:218-219 — `_DailyEntry` docstring 的「結構保證」超出實作(Spec-01 只回校 design.md,未鏡像到 code)
問題:三欄型別上各自 Optional,`bars=None` + `pre_final_written_at` 非 None 完全合法;該不變式只靠「`daily_put` 是標記的唯一寫入點」這條單點約定維持,結構化的只有 prune 半邊。影響:`_period_stale_or_empty:619` 的「值恆 False」與 `daily_get:365` 的「此時必也是 None」都建立在這句上;日後若有人加第二個標記寫入點,兩處靜默失真、零錯誤訊號。修法:比照 design.md 回校措辭「一條單點約定 + prune 的結構保證」。spec 對照:round-1 Spec-01 認定的正是這句超譯,disposition 只改了 design.md(「結構收益」段已含「不是型別級保證」),同源 code docstring 未同步 —— 處置不完整,不是重報。search-proof:Read bars.py 195-235(三欄 `X | None = None` 於 229-231);design.md:27-29;code-review-round-1.json:15。anchor:`    收成一格後「無快照時標記必也不在」變成結構保證(標記只由 \`daily_put\` 非空寫入)。`

#### R-02 [LOW] bars.py:604 — `_period_pre_final` docstring 殘留「pop」術語(S-04 只修了 `PeriodBars` 那一處)
問題:收攏後 `daily_put` 是欄位指派(:392 `entry.pre_final_written_at = now if … else None`),不再有 pop。影響:純可讀性,拿「pop」grep 實作會落空(S-04 當初認定的正是這個症狀)。search-proof:`grep -n "pop" copycat/server/bars.py` → 300(`_empty.pop`,真實)/ 387(註解「不 pop 界前標記」)/ 604(本條);base 版另有 384 `self._daily_pre_final.pop(...)`,已刪。spec 對照:design.md 步驟 2 列「三處 docstring」不含本函式,屬遺漏而非刻意排除(不做清單無此項)。anchor:`    與 bars 在同一個同步區塊內取值:標記的 pop 與 \`_daily\` 的覆寫是 \`daily_put\` 內同一段`

#### R-03 [LOW] test_bars.py:783 — `_make_mutable_clock` docstring 的「兩個 class 共用」已被本 PR 變成三個
問題:本 PR 新增第三個呼叫端。search-proof:`grep -n "_make_mutable_clock"` base = 定義 732 + 呼叫 752(`TestDailySnapshotFinality`)/ 1001(`TestFrozenRefetchSignal`);head 多了 171(`TestDailyEntryFields`)。影響:同一 PR 為同類理由維護了 `build_period` docstring 的「三處 → 兩處」,此處數字沒跟;下次判「還有誰共用這把凍結鐘」會被誤導。修法:改「三個 class 共用」或不帶數字。附帶:round-1 S-05 提到的「前向引用後定義的 helper」在 fix 後仍在(class 135、helper 780),執行期無誤,僅記帳。anchor:`    定稿界兩個 class 共用的唯一一份(pr-171-review F-12:曾複製成 \`_clock\` 逐字副本,`

#### R-04 [LOW] verification.md:58-59 — 表列兩列無法由附上的證據重跑
問題:`compare_bars.py::PATHS` 只有 8 條、evidence txt 也只有 8 行,這兩列不在其中(「419 B / 183 B」位元組計法不是該腳本的輸出格式,顯然另以 curl 手跑)。影響:重跑腳本得 8 列,與表格 10 列對不上,事後無法自證這兩列跑過。修法:兩條路徑補進 `PATHS` 重跑,或表格註明「手動 curl,不在腳本內」。search-proof:compare_bars.py:10-19 PATHS 8 條;sidecar-compare txt 9 行(8 列 + RESULT)。anchor:`| \`/api/stock/bars/2330?tf=1&days=2\` | 未改功能抽查 1(分 K 兩段式) | SAME(419 B) |`

#### R-05 [LOW] compare_bars.py:34-44 — 兩台同時壞掉也會印 `ALL SAME`
問題:比對只看「兩邊一樣」,沒有正確性地板(不驗 `sa == 200`、不驗 `bars` 非空)。本次兩台都 200 且 bars=5,結論成立;但腳本被下次重用時,若共同前提壞掉(fake source 簽名變更 → 兩台同 500 / 同 bars=0),摘要行仍印 `RESULT: ALL SAME`,人通常只貼那一行。修法:`all_ok &= same and sa == 200 and bool(ba.get("bars"))`。另:`A`/`B` 埠號寫死 8731/8732 而 `sidecar_bars.py` 的埠是 argv,重用時兩檔要一起改。anchor:`    same = (sa, ba) == (sb, bb)`

#### 行為等價驗證(核心問題,reviewer 自跑)
以 `git show 45df8dbd:copycat/server/bars.py` 還原舊三 dict 版,與 head 版並排跑隨機差分:4000 條序列 × 12 步,操作集 {`daily_put` 非空 / `daily_put` 空 / `daily_tag_put` / `prune`},時鐘每步隨機取 {09:00, 13:40, 14:00, 14:01, 23:59},每步對 3 鍵 × 2 日全讀四個 getter —— **divergences: 0**。儲存 list identity aliasing 新舊皆 `daily_get(...) is b` / `daily_stale(...) is b`。手動逐狀態核對亦一致:tag-only 格三個 getter 全 None;`prune` 仍是 `_daily` 唯一 evictor(含 tag-only 格);`daily_put` 空手三欄全 no-op。`daily_get` 由兩次 dict 查找降為一次。Concept-count(baseline Design Decay 10):改前 3 dict + 「三處同步」+ 「同鍵同刪」+ 「分開存的歷史理由」;改後 1 dict + 1 dataclass + 1 條單點約定 —— 真減少非搬家(`prune` 7 → 2 行、`__init__` 宣告 3 → 1、跨容器不變式 2 → 1、公開簽名逐字不變);`_DailyEntry` 非 pass-through。

### Per-file accounting(10/10,reviewer 原文要點)

- `copycat/server/bars.py` — R-01 / R-02。
- `tests/server/test_bars.py` — R-03。
- `docs/next-time.md` — REVIEWED_NO_ISSUES(勾選 + 出貨註與實作相符)。
- `.claude/refactor/bars-cache-daily-entry/design.md` — REVIEWED_NO_ISSUES。
- `.claude/refactor/bars-cache-daily-entry/verification.md` — R-04。
- `.claude/refactor/bars-cache-daily-entry/code-review-round-1.json` — REVIEWED_NO_ISSUES(S-03 拒絕 `slots=True` 的 grep 反證複查成立,不挑戰)。
- `.claude/refactor/bars-cache-daily-entry/evidence/compare_bars.py` — R-05。
- `.claude/refactor/bars-cache-daily-entry/evidence/sidecar_bars.py` — REVIEWED_NO_ISSUES(`neutralize_external_env()` 在 `create_app` 前、import 錨點 assert、自選檔落 tempdir,三道隔離到位)。
- `.claude/refactor/bars-cache-daily-entry/evidence/mutants.txt` — REVIEWED_NO_ISSUES(M4 存活判讀獨立複核:拿掉 guard 後 tag-only 格仍回 `entry.bars` = None,測試不紅,「冗餘但保留當意圖註記」成立)。
- `.claude/refactor/bars-cache-daily-entry/evidence/sidecar-compare-master-vs-worktree.txt` — REVIEWED_NO_ISSUES。

## 內部複查結果(同軸 code-reviewer,取代 4.2;非跨軸證據)

| # | 原編號 | Verdict | 原始 → 校正 severity | Evidence(要點) | baseline | 單軸可信度 |
|---|---|---|---|---|---|---|
| F-01 | R-01 | CONFIRMED | LOW → LOW | `bars.py:219` 逐字成立;229-231 三欄 `X | None = None`;唯一寫入點 `daily_put`(385-392)空手早退 387、非空才寫 bars 389 後指派標記 392 = 單點約定;結構化只有 `prune`(347-348)。design.md:27-29 已回校、`code-review-round-1.json:15` disposition 只寫「design.md 回校」→ code docstring 未同動。緩解:同 docstring 220-221「三欄彼此獨立」、`_period_stale_or_empty` 619-620 只講機制 | 無先例(grep `結構保證` 全 repo 僅此一處超譯,`engine/__init__.py:1` 的用法確為結構性) | **不足以獨立採信**:機械半邊(design.md 改、code 未改)可驗;「算不算超譯」是措辭判斷,round-1 Spec 軸對同一句下相反判斷(「程式碼註解其實誠實」)—— 需 user 拍板改哪一邊 |
| F-02 | R-02 | CONFIRMED | LOW → LOW | `bars.py:604` 逐字成立;`daily_put` 385-392 無 pop、392 為欄位指派。S-04(`code-review-round-1.json:9`)只修 `PeriodBars`(diff bars.py:120)。**範圍擴大**:`grep -n pop copycat/server/bars.py` 另有 :387「不 pop 界前標記」、`tests/server/test_bars.py:169`「也不 pop 界前標記」,共三處 | 慣例支持(同輪 S-04 已把同型判為值得修並照修,本條是漏網兄弟) | 可獨立採信:純機械字面比對,零判斷;另兩處同型方向一致 |
| F-03 | R-03 | CONFIRMED | LOW → LOW | `test_bars.py:783` 逐字成立;呼叫點 171 / 800 / 1049 共三個,base(`git show 45df8dbd:…`)定義 732、呼叫 752 / 1001 共兩個;171 在新增 `TestDailyEntryFields`,推 `now["t"]` 到 14:01 跨界確為定稿界用戶;docstring 不在本 PR diff 內 | 無先例偏支持(grep `唯一一份` 只三處,唯此處寫死數量;helper 有 pr-171-review F-12 前科) | 可獨立採信:一條 grep + 一條 `git show` 即重現;即使不算「定稿界 class」共用者數量仍 2 → 3 |
| F-04 | R-04 | CONFIRMED | LOW → LOW | `verification.md:58-59` 逐字成立;`compare_bars.py:10-19` PATHS 8 條不含兩列;txt 8 列 + RESULT;腳本 :40 印 `SAME 200/200 <path> bars=N meta=…` 產不出「419 B」;表頭 :49 把 10 列歸給 8 列產物。「手動 curl」是推論非明述 | 慣例支持(房規手動 curl 另立小節,例 `.claude/mod/bars-tristate-status/verification.md:29`;147 份 verification.md 中 24 份含 curl) | 可獨立採信:列數與字面比對 30 秒重現;「用什麼跑」推論即使錯也不影響結論 |
| F-05 | R-05 | PARTIAL | LOW → LOW(note 級) | 前半成立:`compare_bars.py:34` 只 `same = (sa, ba) == (sb, bb)`,全檔無 200 / 非空 assert。緩解在同腳本 + 產物:`:40` 印 `{sa}/{sb}` `bars={len}` 整包 meta,txt 8 列 `200/200 … bars=5`、TWSE 三列 meta 帶 `tc4_dk / coverage_from 2026-09-05 / partial_last true`;「兩台同版」由 `sidecar_bars.py:37` `assert str(loaded).startswith(ROOT)` + `has _DailyEntry` 印記 + verification.md:47 兩台 git_sha(`45df8dbd` vs `3af3c822`)守住。後半 REFUTED:port 寫死 vs 側車 argv 有合理由(側車要兩 root、比對端固定兩 port) | 慣例衝突(一次性取證腳本「印狀態筆數由人讀、不 assert、base URL 寫死」是長期房規:`sc1_api_boundary.py:9` / `poll_futures.py:10` / `restart_trials.py:39`) | 單軸會系統性高估:無 assert 機械可驗為真,「是不是問題」取決於取證文化 + 產物內容,只看 diff 必報成缺口;PARTIAL 建立在三支前例 + txt 實錄 |

## Action Items

Severity calibration:6c(移除既有防護類)— 本 PR 無此類 finding,免。6d-1(hedge cap)— F-01「日後若有人加第二個寫入點」是條件句,已在 Nice;F-05「兩台同壞」是未實現風險,已在參考用。6d-3(Must Fix 雙半條件)— 五條皆無 user-visible 重現路徑(全在 docstring / 測試註解 / 取證文件層),零阻擋出貨,無一落 Must / Should。未驗證前提檢查:F-01 ~ F-04 全為字面 + grep + `git show` 第一手,拿掉任何論據等級不變(已是 LOW);F-05 的「fake source 簽名變更會讓兩台同 500」是假設情境,已標 PARTIAL + 參考用。Provenance cap:N-A。校準套用:無作者校準檔(`loger-w.md` 不存在)、本輪無套用。4.3b lone finding:本場 CC 單軸,五條全 lone,「他軸為何漏」改答單軸可信度(見內部複查表末欄);F-02 / F-03 / F-04 純機械比對可獨立採信;F-01 內部複查自陳「措辭判斷需 user 拍板」但因等級已是 LOW、Nice to Have 不再降;F-05 PARTIAL 落參考用。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

無。

### Nice to Have(可選優化)

- **F-01** `bars.py:219` `_DailyEntry` docstring「結構保證」改口為「prune 半邊結構吸收 + 寫入半邊單點約定」,與 design.md:27-29 對齊。內部複查提醒:round-1 Spec 軸對同一句持相反判斷(認為 code 註解誠實、design.md 超譯),兩份文件現在措辭不一致是事實,改哪一邊由 user 定。
- **F-02** 三處「pop」(`bars.py:604` / `:387` / `test_bars.py:169`)改「清成 None / 不清標記」,同 S-04 口徑。
- **F-03** `test_bars.py:783` 「兩個 class」改「三個 class」或去數字。
- **F-04** `compare_bars.py::PATHS` 補 `tf=1&days=2` 與 `/api/calendar` 重跑一次覆蓋 txt,或 verification.md 表格另立「手動 curl」小節。
- 四條可併一筆 `chore(docs)` 收修(零 runtime 改動,不需重啟 prod)。

### 參考用(任一軸驗證為 REFUTED / OUT_OF_SCOPE / PARTIAL 且不建議動 code)

- **F-05** `compare_bars.py` 無正確性下限 + port 寫死:CC 主軸擔心兩台同壞仍印 ALL SAME → 內部複查於留存 txt 逐列 `200/200 bars=5` + `sidecar_bars.py:37` import 錨點 assert 找到下限可直讀、port 寫死為三支前例同型房規 → 使用者自行判斷是否要立「取證腳本一律帶 assert」新政策(建議不動本 PR)。

## 審查工具比較(qualitative)

- CC 主軸(python-reviewer):context-aware;核心問題(行為等價)以 4000 序列隨機差分 + identity aliasing 自證零分歧,五條 finding 全是「同一輪 review disposition 沒同步到的兄弟處」與「證據可重跑性」—— 純看 diff 抓不到(要對照 round-1 JSON 與 base 版 docstring)。
- 內部複查(code-reviewer):同軸、非跨軸證據;5/5 齊,CONFIRMED 4 / PARTIAL 1 / REFUTED 0 / OUT_OF_SCOPE 0;severity 零下修(全 LOW);一條範圍擴大(F-02 由 1 處 → 3 處)、一條半邊反證(F-05 port 寫死 = 房規)、一條自陳需 user 拍板(F-01 措辭)。
- Codex / Gemini:N-A(user 停用),無跨軸重疊率可算;對抗式增益 N-A。
- REFUTED 率 0%(PARTIAL 20%):主軸命中率高,但同模型家族互驗,且五條全 LOW 文件層 —— 對一個所有 gate 綠 + 差分零分歧的純重構,這個分佈是預期的。

## 沒做的部分(結案對帳)

- Codex 中性軸:N-A —— user 明示停用(沿 #188 / #190 / #199 / #202 / #211 / #218 前例),未起軸、未 retry。
- Codex 對抗式軸:N-A —— 同上。
- Gemini Flash 軸:N-A —— user 明示停用。Gemini Pro:N-A(同上;Step 2.96 依前例不再問)。
- Step 2.98 Codex preset 詢問:N-A(Codex 停用,依前例不再問)。
- Cross-axis verification 4.1:N-A(無非 CC finding)。4.2:以同軸 code-reviewer 內部複查代替(PASS,5/5),**非跨軸證據**。4.3a consensus:N-A(單軸無 consensus);4.3b lone:五條全 lone,處置見 Action Items。
- Review input binding:**verified**(`refs/pull/220/head` = headRefOid `c4e43f67`,worktree detached 於該 SHA;merge-base = baseRefOid `45df8dbd`)。
- Blast radius(2.9):PASS(有跑)但空輸出跳過(`sem` 未安裝)。
- React-doctor(2.97):N-A(非 React PR,F 無 .jsx / .tsx)。
- Formal spec traceability(2.65):SKIPPED (C4_NO_NORMATIVE_CLAUSE);spec-compliance-reviewer 未派。
- Author calibration(2.2):無檔、本輪無套用。
- Reviewer 未重跑全量 pytest / ruff / pyright / validate:review worktree 純讀碼(reviewer 只跑自寫的差分腳本);全量綠燈證據引自 PR 內 `verification.md`(出貨前實跑 pytest 3562 passed / 3 skipped、ruff 0、pyright 0、validate 42/42、突變體 M1–M3 紅、側車 ALL SAME)。
- 未驗前提(集中揭露):F-04「那兩列是手動 curl」是推論(文件未明述),不影響結論;F-05「fake source 簽名變更會讓兩台同 500」是假設情境未實際發生;F-01「日後加第二個標記寫入點」是條件句。
- 真環境:純重構、runtime 行為不變;PR 出貨時側車對照已做,本 review 未另跑;prod 8721 仍為 `45df8dbd`(未重啟,本 PR 不需為它重啟)。
- Self-Verify:已執行(`skill-verify-auditor`,requested=opus / observed=UNAVAILABLE;唯讀、只 Read 本草稿檔一次,1 tool 呼叫)。R1–R10 全 PASS、`VERDICT: COMPLIANT`,零修正;未重派 auditor。
