# PR #153 Code Review 比較報告 · SHA db0e6d48
**Report projection schema**: 1

**PR**: [loger-w/copycat#153](https://github.com/loger-w/copycat/pull/153)
**標題**: perf: 開盤回補並行 —— 退避 poll + 整批 SubHistory + 首筆成交 tick 入列(40 檔 40.7 s → 0.87 s)
**作者**: loger-w(commits 署名 Loger)
**分支**: `perf/opening-backfill-parallel` → `master`(PR 狀態 MERGED,merge commit 2873e004;遠端分支已刪、回溯 review)
**變更**: 14 檔案, +878 / -135(7 commits;merge-base 25312d79)
**審查日期**: 2026-08-30
**Review input basis**: source repo R_kgDOTsITBg + db0e6d4845db9f77b7e07e7d3633d2f179890608;destination repo R_kgDOTsITBg + f5fa90b40c4563c6e270b8bea5ca7f5d16271acc;`input_binding: verified`(遠端分支已刪,改 `git fetch origin refs/pull/153/head` → FETCH_HEAD 與 headRefOid 逐字相同;baseRefOid f5fa90b4 本地可解析;worktree HEAD = source SHA)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`;`review_context_changed=false`(產報告前 `gh pr view 153` 重抓 headRefOid / baseRefOid 與 reviewed 完全相同;origin/master 現為 2873e004 = 本 PR rebase merge 末筆,屬 PR 自身 merge、不算 base 變動)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-153`(detached);chunk B 另用同 SHA 的 `git archive` 快照目錄(reviewer 突變體實驗只在其 scratchpad 副本,兩處 review root 未改動)
**worktree HEAD**: db0e6d4845db9f77b7e07e7d3633d2f179890608
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 `codex` CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A:無非 CC 軸 finding;4.2 Codex 驗 CC first-pass 失敗:Codex 缺席)+ Gemini 軸 N-A(本機無 `agy`)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer × 2 chunk instances(chunk A = 13 檔生產碼 + docs + artifacts、chunk B = 1 檔 engine 測試;dispatch 顯式 model=opus、effort 依 frontmatter xhigh;observed:chunk A 自陳 `claude-opus-5[1m]`(自報,tool calls Read 7 / Bash 15 / Grep 3)、chunk B 自陳 `claude-opus-5[1m]`(自報,Read 5 / Bash 16);observed model 僅為 agent 自報、無 runtime receipt);domain reviewers=未觸發(security-reviewer 無 auth / env / request-body 面);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=14 → covered 6 / no-issues 8 / skipped 0 / **missed 0**(chunked: 是;FILE_COUNT=6 源檔 ≤ 15 但 DIFF_LINES=1013 > 800 → 路徑排序後切兩塊:chunk A 前 13 檔(791 行)/ chunk B `tests/server/test_stock_engine.py`(222 行);兩塊 accounting 聯集 = F,無需 repair 輪)
**定位 (ENH-B)**: anchored exact 13 / ambiguous 0 / **FAILED 1**(F-04 為「缺測試」型,anchor 依契約 `<none>`,inline block 改寫「需人工確認」;其餘 13 個 anchor 以 worktree HEAD 逐字比中且唯一,line 以比中結果為準)
**React-doctor (2.97)**: N-A(非 React PR:F 無 `.jsx` / `.tsx`,frontend/ 零 diff)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh <worktree> origin/master` exit 0 零輸出;reviewer prompt 改注入 main session 人工查得的 caller 清單:Protocol 三個實作者 + `_enqueue_backfill` 六個入列點 + 四個記帳清除點)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,14 檔全部 authored)
**審查軸狀態**: primary(python-reviewer chunk A)PASS(7 findings、13/13 accounting、白名單六條自核 PASS、`tests/live/test_stock_source.py` 76 passed、`ruff format --check` 三檔);primary(python-reviewer chunk B)PASS(7 findings、1/1 accounting、5 個突變體於 scratchpad 副本實測:MUTANT-1/2/5 全綠證實缺口、MUTANT-3/4 紅證實測試有效;全檔 180 passed 基線);domain reviewers N-A(未觸發);spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 FAIL(工具缺席、未啟動);Codex 對抗 FAIL(同上);Gemini Flash FAIL(工具缺席、未啟動);Gemini Pro N-A(未啟用);cross-axis verification 4.1 N-A / 4.2 FAIL(Codex 缺席 → 14 條 first-pass 全部 INCONCLUSIVE,無 cross-axis 證據;main session 對其中 4 條做機械複核,見複查欄)/ 4.3a N-A(無 consensus finding)/ 4.3b PASS(14 條 lone finding 逐條判斷,見備註)
**Self-Verify**: 見文末「沒做的部分」

**Report generation**: sha256:0516228426f7fd71fc70f439bc192c2d648da841d9822cc9c14569af07c6b5f7

---
## [完整證據副檔](pr-153-review.audit.md)
### finding_uid 索引
[05ae92bf92dbb05e9594](pr-153-review.audit.md#發現總覽) · [98b649aaadfd4c70608f](pr-153-review.audit.md#發現總覽) · [515eda694ac926ef0eb2](pr-153-review.audit.md#發現總覽) · [11a92be781288047ddd2](pr-153-review.audit.md#發現總覽) · [5dd68500555f08326ffe](pr-153-review.audit.md#發現總覽) · [4422a4b902dde9efe960](pr-153-review.audit.md#發現總覽) · [24c993ad1b0bcf335577](pr-153-review.audit.md#發現總覽) · [f93908ee65537691990a](pr-153-review.audit.md#發現總覽) · [72ff2817d2aaf526f1e9](pr-153-review.audit.md#發現總覽) · [ce7fc2cee6e406c7b387](pr-153-review.audit.md#發現總覽) · [4c915dc21fd5b0e74ef6](pr-153-review.audit.md#發現總覽) · [44c02ee006420e4c08d6](pr-153-review.audit.md#發現總覽) · [1d9e845c4900cfc2f964](pr-153-review.audit.md#發現總覽) · [f8d8f1bd519d54ae1b3a](pr-153-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | 成員回補走 ConnectionError 分支後,`_tick_armed` 不清 → 當日 tick 通道不再自救 | MED [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE(Codex 缺席);main 複核:`_run_backfill_job` ConnectionError 分支只 `_backfill_failed += 1`、無 timer、無 `_tick_armed.discard` 屬實 | Nice to Have | `auto-fix` | 一行 discard、預算由 `_BACKFILL_MAX_FAILS` 封口 |
| F-02 | 「先全訂再收割」順序未被測試釘住(prepare 搬到收割後 16 條仍綠) | MED [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE;reviewer 突變體 MUTANT-2 全綠實證 | Nice to Have | `auto-fix` | 用既有 `backfill_gate` 取樣,修法已實測紅綠 |
| F-03 | 主圖排除(F-3)未被測試釘住(刪 `code != self._main` 全檔 180 綠) | MED [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE;MUTANT-1 全綠實證 | Nice to Have | `auto-fix` | 改具體斷言 + `_tick_armed == set()`,已實測 |
| F-04 | `_tick_armed` 的兩個訂閱期 discard 點零覆蓋(刪掉全檔仍綠) | MED [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE;MUTANT-5 全綠實證 | Nice to Have | `auto-fix` | 鏡射既有 `TestWatchlistRemovalBookkeeping` 兩條 |
| F-05 | Protocol docstring「失敗只 log 不 raise」寬於實作(只 catch ConnectionError;`_req` 的 `json.loads` 在 try 外) | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE;main 複核:`tc4.py:550` `return json.loads(message)` 在 try/finally 之後屬實 | Nice to Have | `ask-user` | 改 docstring 或擴 catch 到 `ValueError` 是取捨 |
| F-06 | `sent[:2]` 切片斷言釘不住「傳輸失敗就停」 | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE;main 複核:切片對「續送第三筆」的實作也綠,屬實 | Nice to Have | `auto-fix` | 改全等比對一行 |
| F-07 | 去重測試 `or` 斷言:一分支不可能、另一分支與空跑同形 | LOW [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE;reviewer 註 MUTANT-3 今日仍紅(非全無效力) | Nice to Have | `auto-fix` | 改雙碼批次讓去重可觀測 |
| F-08 | 試撮測試 docstring 把守門者寫成 parse(實為 `is_trial` 旗標 + engine guard) | LOW [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE;main 複核:實作期就踩過同一誤解(engine 註解已改、測試 docstring 漏改)屬實 | Nice to Have | `auto-fix` | 改一句 docstring |
| F-09 | 兩條「不入列」測試只有否定斷言、無正向錨點,且固定 `_drain` 睡眠 | LOW [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE;檔內 `wait_until` 既有 20 處用法屬實 | Nice to Have | `auto-fix` | 先錨簿 / meta 落地再斷否定 |
| F-10 | reconnect 測試直呼 `_handle_reconnect()`,檔內其餘 5 處走 `src.on_reconnect()` | LOW [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE | Nice to Have | `auto-fix` | 兩行改成真回呼路徑 |
| F-11 | harness `--trigger watchlist` 是死選項(空轉到 deadline 回假數字);docstring 漏 `ticks` | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE;main 複核:`run()` 只處理 group / ticks 屬實 | Nice to Have | `auto-fix` | 刪 choice + 改 docstring 用法行 |
| F-12 | 新測試引入 ruff format 偏差(類別內兩行空白) | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE;main 複核:`ruff format --check` HEAD would reformat、pre-PR 只有既有兩處偏差,屬實 | Nice to Have | `auto-fix` | 刪一行空白 |
| F-13 | artifact 引用的 SHA(f1b7a52c / 9f30386f / 51a35de3 / f93f530f / 09cc3e63 merge-base)在 rebase 後全部指不到 | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE;reviewer `merge-base --is-ancestor` 逐顆實證 | Nice to Have | `auto-fix` | 依 08-27 拍板改引「第 n 筆 + subject」 |
| F-14 | `_handle_quote` 熱路徑新 guard 把最具選擇性的 `code not in _tick_armed` 放最後 | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE;reviewer 自評 confidence 0.5、量級每 tick 數個 op | Nice to Have | `no-op` | 收益微小不值一筆 commit;下次動到那段順手調 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 05ae92bf92dbb05e9594 action=auto-fix
F-02 finding_uid: 98b649aaadfd4c70608f action=auto-fix
F-03 finding_uid: 515eda694ac926ef0eb2 action=auto-fix
F-04 finding_uid: 11a92be781288047ddd2 action=auto-fix
F-05 finding_uid: 5dd68500555f08326ffe action=ask-user
F-06 finding_uid: 4422a4b902dde9efe960 action=auto-fix
F-07 finding_uid: 24c993ad1b0bcf335577 action=auto-fix
F-08 finding_uid: f93908ee65537691990a action=auto-fix
F-09 finding_uid: 72ff2817d2aaf526f1e9 action=auto-fix
F-10 finding_uid: ce7fc2cee6e406c7b387 action=auto-fix
F-11 finding_uid: 4c915dc21fd5b0e74ef6 action=auto-fix
F-12 finding_uid: 44c02ee006420e4c08d6 action=auto-fix
F-13 finding_uid: 1d9e845c4900cfc2f964 action=auto-fix
F-14 finding_uid: f8d8f1bd519d54ae1b3a action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### F-01 成員回補撞一次 ConnectionError 之後,那檔當天就再也不會靠首筆 tick 補了
**File**: `copycat/server/stock_engine.py`
**Line**: 1192

**Comment**:
```
_tick_armed.add(code) 在 _backfill_wanted 之前就先做了,所以「檢查過一次」= 用掉這個訂閱期唯一的點火權。
逾時那條有 15 s timer 接手沒問題,但 _run_backfill_job 的 except ConnectionError(成員那半)只把
_backfill_failed +1、不設 _backfilled、也不武裝 timer → 開盤 TC4 抖一下,40 檔 fails=1,
_backfill_wanted 重新為真,可是 _tick_armed 已滿,tick 通道整天不再點火,又退回等群組檢視 60 s 輪詢。

成員那半加一行就好(預算由 _BACKFILL_MAX_FAILS=3 封口,每次都要先付一次真失敗 REQ,不會重演 F-2 的毫秒燒盡):

    else:
        logger.warning("backfill %s failed(成員;當日第 %d 次 …)", …)
        self._tick_armed.discard(code)  # 下一筆成交再點火一次
```
#### F-02 「先全訂再收割」這個 perf 案的核心順序,測試其實沒釘到
**File**: `tests/server/test_stock_engine.py`
**Line**: 1816-1817

**Comment**:
```
註解寫「整批一次,且在第一檔收割前」,但兩條斷言都是終局狀態,prepare 跟 backfill 誰先誰後完全不敏感 ——
把 worker 裡 `if len(fresh) >= 2: … prepare` 整塊搬到 for 迴圈之後,這組 16 條照樣全綠(實測)。
順序倒過來 = prepare 變純代價、開盤又回到一分鐘一檔,而且要到下一次真開盤才看得出來。

用既有的 backfill_gate 把第一檔卡在收割中,趁機驗批次早就 Sub 完(clean 綠 / 搬順序後紅,實測過):

    src.backfill_gate = threading.Event()
    engine.group_snapshot(codes)
    await wait_until(lambda: src.backfills == ["2330"])   # 第一檔正在收割
    assert src.prepares == [codes], src.prepares          # …整批早已 Sub 完
    src.backfill_gate.set()
    await _drain(engine)
    assert src.backfills == codes
```
#### F-03 「主圖不走 tick 路徑」這條 guard 拿掉,全檔 180 條還是綠
**File**: `tests/server/test_stock_engine.py`
**Line**: 1778-1782

**Comment**:
```
基準值 n 是在第一則 tick 之後才量的,而 _tick_armed 每訂閱期只點火一次 —— 第一則 tick 若被 tick 路徑
多排了一筆,n 會把它一起吸收;第二則 tick 有沒有 guard 都不會再排。tc4_status 那條同理。
實測把 `and code != self._main` 刪掉:這條、12 條新測試、全檔 180 條全綠。

改成具體值 + 直接量 _tick_armed(clean 綠 / 刪 guard 紅):

    assert src.backfills == ["2330", "2330"]   # 只有 A6-5 那一排,tick 路徑沒插手
    assert engine._tick_armed == set()         # 主圖永不武裝
```
#### F-04 `_tick_armed` 的「訂閱期為界」兩個清除點沒人測
**File**: `tests/server/test_stock_engine.py`
**Line**: 需人工確認（anchor 未在綁定來源中比中或證據 binding 失效）

**Comment**:
```
(缺測試型 finding、無可釘的行;最近符號 = TestWatchlistRemovalBookkeeping::test_backfill_bookkeeping_restarts_after_a_real_unsubscribe,約 2606 行)
`_tick_armed` 四個清除點裡 rollover / reconnect 有測,set_watchlist 移除迴圈跟 set_main 舊主圖 release
那兩個 discard 完全沒測 —— 兩行一起刪掉,全檔 180 條照樣綠(實測)。
失效樣態:自選移除再加回(或主圖換走)之後那檔 _tick_armed 永遠留著 → 首筆成交不再點火,
只剩群組檢視 60 s 輪詢救得回來,卡片 backfilling / no_data 全 False、空著零訊號。

同檔早就有一整個 TestWatchlistRemovalBookkeeping 在釘同構的 _backfilled / _backfill_failed 邊界,
新狀態跟上就好:鏡射 2606 那條,入列動作從 group_snapshot 換成 src.on_message(_quote(...)):
移除 → 加回 → 再送一筆 tick → assert src.backfills.count("2330") == 2;主圖版鏡射 2674。
```
#### F-05 Protocol 說「失敗只 log 不 raise」,實作只擋 ConnectionError
**File**: `copycat/server/stock_engine.py`
**Line**: 199-201

**Comment**:
```
StockQuoteSource.prepare_backfill 只 catch ConnectionError,但 tc4.py:550 的 `return json.loads(message)`
在 try/finally 之後 → 壞電文的 JSONDecodeError 會逸出;evidence/ 底下 13 支側車 fake source 也沒這支方法
(AttributeError)。兩者都靠 worker 的 except Exception 兜住、不會死 worker,但契約文字跟實作不同口徑,
下一個實作者照著 docstring 寫就會少一層。

二選一:
(a) 兩處 docstring 改「傳輸類失敗只 log;其餘例外由 worker 的 except Exception 兜住」
(b) source 端 catch 擴成 (ConnectionError, ValueError)(JSONDecodeError 是 ValueError 子類)
```
#### F-06 這條測試釘不住「傳輸失敗就停」
**File**: `tests/live/test_stock_source.py`
**Line**: 227

**Comment**:
```
docstring 跟 source 註解都說「中斷就停、其餘交逐檔 backfill」,但 sent[:2] 對「2317 失敗後照樣送 2454」的實作也綠 ——
真正要鎖的是沒有第三筆。哪天有人把 for 改成 per-code try/except,這條不會紅,而 _req 已 dispose 連線 → 其餘 N-1 檔全是必敗 REQ。

    assert sent == ["TC.S.TWS.2330", "TC.S.TWS.2317"]
```
#### F-07 去重測試的 `or` 斷言,一邊不可能發生、另一邊跟沒跑一樣
**File**: `tests/server/test_stock_engine.py`
**Line**: 1860

**Comment**:
```
worker 有 `if len(fresh) >= 2` 這道 guard,長度 1 的 prepares 元素永遠不會出現 → `== [["2317"]]` 是死分支。
剩下 `== []` 同時也是「兩筆 2317 沒落同一批」或「set_main 根本沒入列」的結果,沒有任何正向斷言證明那兩筆 job 存在。
(拿掉 dict.fromkeys 今天確實會紅,所以不是全無效力,只是訊息弱、讀者會以為兩種結果都合法。)

改雙碼批次讓去重可觀測:2317 入列兩次 + 2454 一次 →
    assert src.prepares == [["2317", "2454"]]                    # 去重壞掉會是 [["2317","2317","2454"]]
    assert src.backfills == ["2330", "2317", "2317", "2454"]     # 批次組成
```
#### F-08 試撮測試的 docstring 把擋人的那層寫錯了
**File**: `tests/server/test_stock_engine.py`
**Line**: 1722-1723

**Comment**:
```
parse_stock_realtime 不會丟掉試撮成交,它回的 tick 帶 is_trial(stock_models.py:231);真正擋下入列的是
_handle_quote 新加的 `and not tick.is_trial`。docstring 寫「被 parse 濾掉」→ 未來有人據此刪掉 engine 那個 guard,
盤前 08:30–09:00 每檔各排一次必敗的 30 s 歷史請求(測試本身有效:拿掉 not tick.is_trial 這條會紅)。

改成:「試撮成交帶 is_trial=True(parse_stock_realtime 標旗標、不丟棄),由 _handle_quote 的 not tick.is_trial 擋下入列」
```
#### F-09 兩條「不入列」測試只有否定斷言,被測路徑整條失效也會綠
**File**: `tests/server/test_stock_engine.py`
**Line**: 1716-1718

**Comment**:
```
test_book_only_update_does_not_enqueue / test_trial_window_tick_does_not_enqueue 沒有任何證據顯示那則報價真的被處理過
(訂閱失敗、code 不在 _refs、parse 早退……都會綠)。tests/helpers/wait.py 的 docstring 就明講否定型斷言靠固定睡眠是永久假綠;
同檔 wait_until 用了 20 次,新 12 條一次都沒用,還多付 ~19 次 _drain(每次 ~0.31 s)。

先錨正向事實再斷否定:
    await wait_until(lambda: engine.snapshot("2330")["book"]["bid"] is not None)   # 簿更新確實落地
    assert src.backfills == []
試撮那條錨 engine._states["2330"].meta is not None。
```
#### F-10 reconnect 測試直呼 private,跳過檔內其餘 5 處都在走的真回呼路徑
**File**: `tests/server/test_stock_engine.py`
**Line**: 1759

**Comment**:
```
同檔 284 / 478 / 529 / 1582 / 1951 一律 src.on_reconnect() → _on_reconnect_threadsafe → call_soon_threadsafe → _handle_reconnect。
這條獨自跳過那一段;_tick_armed.clear() 跟 tick 回呼同走 call_soon_threadsafe,量到的不是 prod 的順序。

    assert src.on_reconnect is not None
    src.on_reconnect()
```
#### F-11 harness 的 `--trigger watchlist` 是死選項,會給你一個不會報錯的假數字
**File**: `.claude/perf/opening-backfill-parallel/evidence/harness_backfill_timing.py`
**Line**: 180

**Comment**:
```
run() 只處理 group / ticks;傳 watchlist 完全不入列,迴圈空轉到 deadline(40 檔 = 65 s)才回 backfilled: 0 加一個看似合理的 backfill_wall_s。
模組 docstring(L10)又只列 group|watchlist,漏了 review 後才是主角的 ticks。

刪掉 watchlist choice,L10 用法行改成 [--trigger group|ticks] [--tick-gap-ms N]。
```
#### F-12 新測試多了一行空白,`ruff format --check` 現在會判要重排
**File**: `tests/live/test_stock_source.py`
**Line**: 231

**Comment**:
```
L229-230 是兩行空白(類別內方法間應一行)。pre-PR 版的 format 偏差只有既有的 L1109 / L1143 兩處,這一行是本 PR 新加的 ——
下一個人跑整檔 ruff format 會連既有行一起重排(backend-conventions 記的 08-28 真踩)。刪一行空白就好。
```
#### F-13 artifact 裡引的 commit SHA 在 rebase 之後全部指不到
**File**: `.claude/perf/opening-backfill-parallel/verification.md`
**Line**: 13

**Comment**:
```
f1b7a52c / 9f30386f / 51a35de3 / f93f530f 與 code-review-round-1.json 的 head_reviewed / fixed_point 09cc3e63(merge-base 也已變 25312d79)
`git merge-base --is-ancestor <sha> db0e6d48` 全 no —— 想回溯「S1-a 那版量到 18.91 s」的人在 PR 歷史找不到那顆 commit。
照 08-27 拍板改引「第 n 筆 + subject」;要回填 SHA 的話對應是(main session 以 `git merge-base --is-ancestor <sha> db0e6d48` 逐顆驗過、全 yes):
  9f30386f → cdd847fd(第 1 筆 perf(live) 退避)、51a35de3 → eb11b24d(第 2 筆 perf(server,live) prepare_backfill)、
  f1b7a52c → 780f4153(第 6 筆 fix(server,live) review 收修)、f93f530f → ea05509c(第 5 筆 chore(docs,skills))、merge-base 09cc3e63 → 25312d79。
```
