# PR #128 Code Review 比較報告 · SHA 0011a169

**Report projection schema**: 1

**PR**: [loger-w/copycat#128](https://github.com/loger-w/copycat/pull/128)
**標題**: fix(stock): 現貨自癒閘改 per-consumer —— index session 單獨 13:25,個股 / corr 台積電腿改回 13:35(pr-126 F-01 HIGH + 六條收修)
**作者**: loger-w(commits 署名 Loger)
**分支**: `mod/heal-gate-per-consumer` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 7f4bc98d;回溯 review)
**變更**: 12 檔案, +343 / -51
**審查日期**: 2026-08-27
**Review input basis**: source repo R_kgDOTsITBg + 0011a1698ff365b63b4ada944f4f3ff0127cae17;destination repo R_kgDOTsITBg + 24129d7570c8025cf34f9d516b6a72379d36bc1b;`input_binding: verified`(`git fetch refs/pull/128/head` 後 FETCH_HEAD 與 headRefOid 逐字相等、worktree HEAD = source SHA;destination SHA 為 master 歷史上的既有 commit,`git merge-base --is-ancestor` 成立)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-128`(detached)
**worktree HEAD**: 0011a1698ff365b63b4ada944f4f3ff0127cae17
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 主 agent 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer(不切塊,單一 dispatch;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=12 → covered 5 / no-issues 7 / skipped 0 / **missed 0**(chunked: 否;FILE_COUNT=5 源檔 ≤ 15、DIFF_LINES=394 < 800;reviewer 逐檔 accounting 12/12,union = F)
**定位 (ENH-B)**: anchored exact 6 / ambiguous 0 / **FAILED 0**(全部 anchor 於 worktree HEAD 以 grep 逐字比中,line 以比中結果為準)
**React-doctor (2.97)**: N-A(非 React PR:F 無前端檔)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,12 檔全部 authored)
**審查軸狀態**: primary(python-reviewer)PASS(6 findings、12/12 accounting);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條實查,見備註欄);React-doctor N-A(非 React PR)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus)回 R1–R7 / R9 / R10 PASS、R8 FAIL → `VERDICT: VIOLATIONS: R8`;已修正(F-01 修法與 Nice 條目改未確認語式),**未經第二次獨立稽查**

**Report generation**: sha256:bea0ea15ede0199cf064c3d1fbc3ad251bf38ba648c8b3deb29bf12887b7d19d

---

## Spec 依據

- 偵測到 `.claude/mod/heal-gate-per-consumer/change-spec.md`(/mod 小活分流 change spec:現況 vs 目標五列、新閘落點理由、caller map 九讀者、白名單六條、驗證 seam;非目標 = pr-126 F-07 兩份邊界表合併,user 拍板不做)。來源 `docs/superpowers/specs/pr-126-review.md` F-01(HIGH,Should Fix)+ F-02 ~ F-06、F-08。
- ⚠️ spec 作者 = PR 作者(同一 session 產出)。本輪 F-01 / F-04 兩條正是 spec / 註解自述的「代價」與「路徑」寫得比實碼嚴重 —— 與 pr-126 F-02 同型,作者自寫 spec 的利益重疊再次兌現。

- `SPEC_COMPLIANCE` receipt:gate=SKIPPED;dispatch=NOT_APPLICABLE;dispatch_count=0;reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED(reducer `resolve-authority` 實跑:spec 位於 `.claude/mod/<slug>/`,不在 authority 允許路徑);requested_model=opus;observed_model=UNAVAILABLE;effort=xhigh;tools=0;0 clauses / 0 findings / 0 observations / 0 invalidated

## 變更概要

provenance:12 authored / 0 inherited(base = master,免驗)。

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `.claude/mod/heal-gate-per-consumer/change-spec.md` | 無 finding(新增) | 現況 vs 目標 / 落點理由 / caller map / 白名單 / seam |
| `.claude/mod/heal-gate-per-consumer/code-review-round-1.json` | 無 finding(新增) | in-flow two-axis round 1 處置 |
| `.claude/mod/heal-gate-per-consumer/verification.md` | 有 finding(新增) | 紅先行 / mutation 表 / 白名單 / gate;M4 列分母不同(F-05) |
| `.claude/mod/stock-heal-gate-end-1325/change-spec.md` | 無 finding(修改) | 頂部改口 + 代價 (b) / caller map 2330 列 / 代價 (d)(pr-126 F-02 / F-04) |
| `.claude/mod/stock-heal-gate-end-1325/verification.md` | 無 finding(修改) | §8 一句改口 |
| `CLAUDE.md` | 有 finding(修改) | §4 新條「index 自癒閘上界 = `_WATCH_END`」;descriptor 與漂掉症狀寫錯(F-02) |
| `copycat/live/stock_source.py` | 有 finding(修改) | `_TRADING_END` 回 13:35、新 `_INDEX_HEAL_END` + `in_index_heal_window_now`、註解收 pr-126 F-02 / F-03 / F-05;代價段仍過重(F-01)、「櫃買」誤植(F-03)、重補路徑漏一條(F-04) |
| `copycat/server/app.py` | 無 finding(修改) | `_default_index_source` 換牆鐘 |
| `docs/next-time.md` | 有 finding(修改) | pr-126 F-08 兩條改回 open、代價改口、命名條;:40「現價欄停在最後一筆」為 F-01 同句複本 |
| `tests/live/test_corr_source.py` | 無 finding(修改) | `TestTwsLegClock` 改回 13:35 語意,註解列指認 |
| `tests/live/test_stock_source.py` | 有 finding(修改) | 端點 13:34:59 / 13:35:00;新 `TestIndexHealWindowGate` + 與 `_WATCH_END` 同值;parity 放 live 側(F-06)、docstring 沿用 F-02 descriptor |
| `tests/server/test_main_wiring.py` | 無 finding(修改) | 兩 factory 各拿各的牆鐘 + 兩把互不牽動 |

## 發現總覽

| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | `_INDEX_HEAL_END` 代價段仍把 index 側講得比實際嚴重:13:25 後 `index_engine._broadcast_loop` 的分時自癒(lag > 3 分即出手,節奏 60 s 起倍增)走 `_retry_loop → _subscribe_and_backfill → self._source.subscribe_symbol(IX0001)`,**重抓 1K 與重掛訂閱是同一發**,重掛的 SUBQUOTE snapshot 本身即一則推播 → 現價欄**應有**復原路(推論自 skill 既載事實,未於真環境量到);13:25 後真正關掉的只有 source 層 REALTIME watchdog 那條。這是 user 知情拍板與「第二段閘」設計的輸入,形狀同 pr-126 F-02(`copycat/live/stock_source.py`) | MEDIUM [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep index_engine.py:297 `subscribe_symbol(_SYMBOL)` 在 `_subscribe_and_backfill` 內、:345 retry 走同函式;註解與 next-time:40 同句改口,非 release-blocking |
| F-02 | 新 §4 契約把 `_WATCH_END` 稱「分時 watchdog 凍結點」—— 吃它的是**推播靜默(stale)watchdog**(`index_engine.py:624-628`),分時自癒窗反而**從 `_WATCH_END` 開始**(:653-658);且「漂掉的症狀:一把還在救、另一把已凍結」正是 13:25 後的**正常態**,拿它當紅燈會對健康狀態報警,真漂移(兩值不同)反而無判準;同句複製到 `test_stock_source.py:1270` docstring(`CLAUDE.md`) | MEDIUM [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep `_in_watch_window()` → :625 stale 判定、:653 heal 分支下界;§4 descriptor 與症狀兩句改口 + 測試 docstring 同步 |
| F-03 | 新閘註解 / docstring 說是「IX0001 / 櫃買」的閘,但櫃買走 `index_engine._mis_loop`(`mis.fetch_otc_snapshot` 5 s HTTP poll),不在 TC4 session 上、MIS 無時段閘;`IndexEngine` 對 TC4 只訂 `_SYMBOL="IX0001"`(`copycat/live/stock_source.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep index_engine.py:21 / :27 / :164;兩處括號改「IX0001;櫃買走 MIS poll 不吃這把」 |
| F-04 | pr-126 F-02 的改口仍漏一個入列點:「漲跌停值變」那條收件人正是 `code == self._main or code in self._backfilled`(`stock_engine.py:1106-1113`),另有 `_fire_backfill_timeout_retry`;「只剩 `set_main_contract` / `_handle_reconnect`」字面照抄 pr-126 建議句但不成立,同句複製到 next-time 與兩份 artifact(`copycat/live/stock_source.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent sed stock_engine.py:1104-1114 確認 `code in self._backfilled` → `_enqueue_backfill`;加限定語「收盤試撮期訂閱死掉這個情境下」並補列 |
| F-05 | mutation 表四列混兩種分母:M1–M3 合計 139(三個測試檔),M4 合計 103(只跑兩個 live 檔),表頭未標選集;讀者會以為 M4 少了 36 個測試(`.claude/mod/heal-gate-per-consumer/verification.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 對照本 session 實跑紀錄:M4 確只跑 test_corr_source + test_stock_source;補「選集 = 兩個 live 檔 103 tests」一句 |
| F-06 | 跨層 parity 測試放在 live 側:`tests/live/` 唯一一筆 `from copycat.server import index_engine`,依賴方向是 server → live;同類 parity(overlay / signal params)在 repo 是「兩邊各一條」或放依賴方(`tests/live/test_stock_source.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `ask-user` | 主 agent grep `from copycat.server` tests/live/ → 僅 :1272;函式內 import 無循環,搬到 `tests/server/test_index_engine.py` 屬測試重組(獨立 🔵),要不要做請 user 決定 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 7ad324396d556d08e82e action=auto-fix
F-02 finding_uid: 7dfe0bf0a0513a595e6f action=auto-fix
F-03 finding_uid: 7df3a3993ad86dfa8875 action=auto-fix
F-04 finding_uid: 257d5939eee8fd9671c0 action=auto-fix
F-05 finding_uid: 57c444af5a36377bbe16 action=auto-fix
F-06 finding_uid: e2d5fd4c7021ce27cbfa action=ask-user

### Inline Comments per Finding（直接複製貼到 PR review）

#### F-01 13:25 後 index_engine 的分時自癒會連訂閱一起重掛,現價欄不是「不會回來」
**File**: `copycat/live/stock_source.py`
**Line**: 49-51

**Comment**:
```
代價段寫「加權分時由 index_engine 尾段回補補齊,但現價欄不會(回補只寫 minutes)」—— 前半對、後半太重。
index_engine._broadcast_loop:653-682 在 13:25 後(有日曆到午夜)只要 minutes 落後牆鐘 > 3 分就 _schedule_retry
→ _retry_loop:345 → _subscribe_and_backfill → self._source.subscribe_symbol("IX0001")(:297)。
重抓 1K 跟重掛訂閱是同一發,節奏 60 s 起倍增到 900 s;重掛的 SUBQUOTE 本身會回 snapshot(tc4-market-facts:74,
第 47 行自己引的事實)→ 走 _on_quote_threadsafe → _apply_twse,現價欄是有路回來的。
真正 13:25 後關掉的只有 source 層 REALTIME watchdog 那條。順帶:指數 13:25 起不更新,牆鐘走到 13:29 lag 就 = 4 > 3,
健康日這發本來就會出手,不只訂閱死掉才會。這段是 user 拍板跟「要不要第二段閘」(next-time:38-40)的輸入,
寫重了下一個 session 會為已有兜底的情境再加閘 —— 跟這輪修的 pr-126 F-02 同型。

改成:「…但現價欄不靠回補(_merge_backfill 只寫 minutes);同一發自癒會連帶重掛 IX0001
(index_engine._subscribe_and_backfill),重掛的 SUBQUOTE snapshot 即一則推播 → 現價欄應會跟著回來
(未實測,次一交易日核)。13:25 後真正關掉的只有 source 層 REALTIME watchdog 那條路。」docs/next-time.md:40 同句一併改。
```
#### F-02 §4 那條把 _WATCH_END 叫「分時 watchdog 凍結點」,而且給的漂掉症狀正好是正常態
**File**: `CLAUDE.md`
**Line**: 269-272

**Comment**:
```
兩件事。(a) 13:25 凍結的是推播靜默(stale)watchdog:index_engine.py:624-628 的
not stale and self._in_watch_window() and now − _last_push > _stale_secs 才是吃 _WATCH_END 的那把;
分時(minutes)自癒剛好相反 —— 它的窗從 _WATCH_END 開始(:653-658,有日曆到午夜、無日曆到 13:40)。
repo 自己的用語也分得清楚(index_engine.py:48「watchdog 判定窗」vs _LAG_HEAL_MIN「分時自癒」)。
(b)「漂掉的症狀:一把還在救、另一把已凍結」—— 13:25 之後本來就是「index_engine 分時自癒還在救、
source 層 REALTIME watchdog 已凍結」。照這句當紅燈會對健康狀態報警,真漂移(兩個常數不同值)反而沒判準。
同一句 descriptor 也複製到 tests/live/test_stock_source.py:1270-1271 的 docstring。

descriptor 改「推播靜默(stale)watchdog 凍結點」,補一句「分時自癒窗反而從這一點開始(到午夜 / 13:40)」;
症狀改可觀測的:「兩把值不同 → 次一交易日 grep 零推播自癒 | grep IX0001 在 13:25 後又出現(值被放寬),
或加權 stale 徽章在 13:2x 提早熄滅(值被收緊)」。test_stock_source.py:1270-1271 同句同步。
```
#### F-03 註解說這把閘管「IX0001 / 櫃買」,但櫃買根本不在這條 TC4 session 上
**File**: `copycat/live/stock_source.py`
**Line**: 43

**Comment**:
```
櫃買指數走 index_engine._mis_loop(mis.fetch_otc_snapshot,5 s HTTP poll)寫 self._otc,
IndexEngine 對 TC4 只訂 _SYMBOL = "IX0001"(index_engine.py:27、:297)。in_index_heal_window_now 對櫃買零作用,
MIS poll 也沒有任何時段閘。:480 的 docstring 同一句再寫一次(從舊 change-spec 的「IX0001 / OTC 看門狗」沿用下來)。
讀者會以為 13:25 後櫃買也「下班」,次一交易日核對時把 MIS 還在 poll(或 poll 壞掉)算到這把閘頭上。

兩處改「(IX0001;櫃買走 MIS poll 不吃這把)」。
```
#### F-04 「個股當日重補只剩 set_main_contract / _handle_reconnect」還是漏了漲跌停值變那條
**File**: `copycat/live/stock_source.py`
**Line**: 38-39

**Comment**:
```
_enqueue_backfill 的 docstring 自己列了五個產出點(stock_engine.py:1284-1285),其中「漲跌停值變」那條的收件人
正是 code == self._main or code in self._backfilled(:1106-1113,註解寫「收件人放寬到今日已回補過的檔」);
另外 _fire_backfill_timeout_retry(:1327)也會重入列。pr-126 F-04 的 inline comment 也點過 :1109-1113。
「只剩兩條」是逐字照抄 pr-126 F-02 建議句,但在本 PR 之後仍不成立;同句又複製到 next-time 跟兩份 artifact。

加限定語或補列:「(在收盤試撮期訂閱死掉這個情境下)當日重補只剩 set_main_contract / _handle_reconnect;
另有『漲跌停值變』(stock_engine.py:1106-1113,只在 upper/lower 真的變動時)與逾時重排,該情境下不會出手。
群組成員 60 s 輪詢被 _backfilled 擋。」
```
#### F-05 mutation 表 M4 那列的分母跟前三列不一樣,沒標
**File**: `.claude/mod/heal-gate-per-consumer/verification.md`
**Line**: 42

**Comment**:
```
M1 / M2 / M3 的 failed + passed 都是 139 = 三個受影響測試檔(test_stock_source 73 + test_corr_source 30 +
test_main_wiring 36);M4 的 2 failed, 101 passed 合計 103 = 只跑了兩個 live 檔。表頭只寫「在 db3dd3c4 上實跑」。
讀者比對會以為 M4 少了 36 個(collection error 那類),而反向驗證表的價值就在「同一組測試、只動一行」。
結論沒錯(test_main_wiring 不碰時鐘值,139 組下應是 2 failed, 137 passed)。

M4 那列補「(選集 = 兩個 live 檔 103 tests)」,或補跑成 139 組讓四列同分母。
```
#### F-06 跨層 parity 放在 live 側,tests/live 唯一一筆 import copycat.server
**File**: `tests/live/test_stock_source.py`
**Line**: 1272

**Comment**:
```
依賴方向是 server → live(index_engine.py:16 import copycat.live.stock_source),這條同值 parity 放在被依賴那側,
grep "from copycat.server" tests/live/ 全目錄只有這一筆。函式內 import、沒循環,功能上 OK;
但同類 parity(overlay / signal params)在 repo 是「兩邊各一條」或放依賴方,live 的測試檔因此綁上 server.mis / server.ws 的 import 鏈。
風險只有一種:日後有人依「live 不碰 server」清 import 時把這條 pin 一起搬掉,而 §4 契約點名的就是它。

維持現狀也可以(契約已點名);要收的話搬到 tests/server/test_index_engine.py 反向斷言
_WATCH_END 落在 stock_source.in_index_heal_window_now 的邊界上,CLAUDE.md 那行同步改路徑。你決定。
```

### Opus 原始 findings (first-pass, context-aware)

- **F-01**(reviewer 原編號 F-1,MEDIUM [python-reviewer])`copycat/live/stock_source.py:49-51` —— 代價段「現價欄不會(回補只寫 minutes)」寫重:`_broadcast_loop:653-682` 13:25 後 lag > 3 即 `_schedule_retry` → `_retry_loop:345` → `to_thread(_subscribe_and_backfill)` → `self._source.subscribe_symbol(_SYMBOL)`(:297),重掛的 SUBQUOTE snapshot 走 `_on_quote_threadsafe → _apply_twse`;13:25 後真正關掉的只有 source 層 REALTIME watchdog;健康日 13:29 lag=4 本來就會出手。impact:user 拍板與第二段閘設計的輸入寫重,形狀同 pr-126 F-02。fix:改口 + next-time:40 同句。anchor:`#: 13:25–13:30 死掉,加權分時由 index_engine 尾段回補補齊(有日曆 → 13:25 起到午夜;無日曆退回` / `#: `_HEAL_TAIL_END` 13:40),但**現價欄不會**(回補只寫 minutes);13:25 後新加的指數訂閱不武裝健檢。`。search-proof:grep `_WATCH_END|_HEAL_TAIL_END` index_engine.py → 653-658;sed 275-300 / 331-400 → :297 / :345;`_heal_secs = 60.0`(:201)、`_HEAL_BACKOFF_CAP`(:63);skill:74,180
- **F-02**(reviewer 原編號 F-2,MEDIUM [python-reviewer])`CLAUDE.md:269-272` —— (a) 吃 `_WATCH_END` 的是 stale watchdog(:624-628),分時自癒窗從 `_WATCH_END` 開始(:653-658);(b)「一把還在救、另一把已凍結」是 13:25 後正常態;descriptor 複製到 test_stock_source.py:1270。fix:descriptor 改 stale watchdog、症狀改可觀測。anchor:`` `app._default_index_source` 注入),必須與 `copycat/server/index_engine.py::_WATCH_END`(分時 watchdog 凍結點)``。search-proof:grep `_in_watch_window|stale` index_engine.py → :624-628 / :653-658;sed 40-58 → `_WATCH_END` 註解「watchdog 判定窗」、`_HEAL_TAIL_END` 註解「兩條路的下界都是 `_WATCH_END`」
- **F-03**(reviewer 原編號 F-3,LOW [python-reviewer])`copycat/live/stock_source.py:43` —— 櫃買走 `_mis_loop` / `fetch_otc_snapshot`,不在 TC4 session,MIS 無時段閘;`_SYMBOL="IX0001"` 唯一訂閱;:480 docstring 同句。fix:改「IX0001;櫃買走 MIS poll 不吃這把」。anchor:`#: **只有 index session**(IX0001 / 櫃買)吃的閘上界 = 收盤試撮起點,**end-exclusive**(13:25:00 起關;`。search-proof:grep `mis|otc|OTC` index_engine.py → `_mis_fetch`(:179)/`_mis_loop`(:464)/`_apply_otc`(:475);grep `_SYMBOL` → :297;grep `StockQuoteSource(` copycat/ → app.py:363 / :375
- **F-04**(reviewer 原編號 F-4,LOW [python-reviewer])`copycat/live/stock_source.py:38-39` —— `_enqueue_backfill` 五個產出點(:1284-1285),「漲跌停值變」收件人 `code == self._main or code in self._backfilled`(:1106-1113)、`_fire_backfill_timeout_retry`(:1327);「只剩兩條」不成立,同句複製到 next-time 與兩份 artifact。fix:加限定語 + 補列。anchor:`#: R1 / R2 / 健檢三條救援路;個股當日重補路徑只剩 `set_main_contract` / `_handle_reconnect`,群組` / `#: 60 s 輪詢被 `_backfilled` 擋 —— pr-126 F-02)。index session 吃下面另一把 `_INDEX_HEAL_END`。`。search-proof:grep `_enqueue_backfill|_backfilled` stock_engine.py → :611 / :725 / :987 / :1046 / :1113 / :1327;sed 1090-1120
- **F-05**(reviewer 原編號 F-5,LOW [python-reviewer])`.claude/mod/heal-gate-per-consumer/verification.md:42` —— M1–M3 合計 139(73 + 30 + 36),M4 合計 103(兩個 live 檔),表頭未標選集。fix:補選集或補跑。anchor:`| M4 `_TRADING_END` 比較 `<` → `<=` | `TestTwsLegClock[13-35-False]` + `TestTradingHoursGate` → `2 failed, 101 passed` |`。search-proof:reviewer 實跑三檔 → 139 passed;`--collect-only` 逐檔 73 / 30 / 36
- **F-06**(reviewer 原編號 F-6,LOW [python-reviewer])`tests/live/test_stock_source.py:1272` —— `tests/live/` 唯一 `from copycat.server` import;依賴方向 server → live;同類 parity 在 repo 放兩邊或依賴方。fix:維持或搬到 `tests/server/test_index_engine.py`。anchor:`        from copycat.server import index_engine`。search-proof:grep `from copycat.server|import copycat.server` tests/live/ → 僅 :1272;index_engine.py:16 import live

已逐條複核成立的 PR 自我宣稱(reviewer 核過,無 finding):`_INDEX_HEAL_END == _WATCH_END` 由 `test_end_matches_index_engine_watchdog_window` 兩條斷言在秒級等價釘住,絕對值另由 `TestIndexHealWindowGate::test_boundary` 與 `tests/server/test_index_engine.py:188-192` 釘;`test_stock_and_index_heal_gates_are_two_different_clocks` 對調接線會紅,corr 半邊由既有 `test_corr_tws_leg_gate_ands_the_calendar_with_the_stock_session` 守;邊界表註解「哪列擋哪個 mutation」指認正確(value-only revert 由 13:25 / 13:26 / 13:30 三列擋、`<`→`<=` 由 13:35 列 + 端點擋、新補 `(13, 36, False)` 保住 pr-111 F-08 的 13:45 保護);pr-126 F-05 / F-04 改口與實碼相符;Reuse 無現成 window helper;三檔 139 passed;commit test / fix / chore×3 三類未混;F-07 依 user 拍板未做。**無 CRITICAL / HIGH**。

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查。

### Codex 對 Opus 的複查結果（對稱化 4.2）

**Codex 複查 Opus 失敗 — 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(本機無 codex)。全部 CC finding 視同 INCONCLUSIVE,改由 4.3b 主 agent 逐條實查(結果在發現總覽「Opus 複查」欄與下方備註):

| Opus # | 原始 severity | 4.3b 判斷 | 備註(他軸為何漏 / 主 agent 實查) |
| --- | --- | --- | --- |
| F-01 | MEDIUM | CONFIRMED | 主 agent grep index_engine.py → `_subscribe_and_backfill` 內 `self._source.subscribe_symbol(_SYMBOL)`(:297),`_retry_loop` :345 `to_thread(self._subscribe_and_backfill, …)`;重掛即 snapshot 是 skill 既載事實。in-flow two-axis 兩軸都沒抓到:兩軸都把 pr-126 F-05 的處方(「有日曆到午夜」)當終點,沒追回補那條路會不會重掛。 |
| F-02 | MEDIUM | CONFIRMED | 主 agent grep `_in_watch_window()` → :625 在 stale 判定式內、:653 是 heal 三分支的第一支(窗內 True)、:656 / :658 以 `_WATCH_END` 為下界;CLAUDE.md:269 與 test_stock_source.py:1270 兩處 descriptor 逐字同。 |
| F-03 | LOW | CONFIRMED | 主 agent grep index_engine.py → :21 import `fetch_otc_snapshot`、:27 `_SYMBOL = "IX0001"`、:164 `mis_fetch` 注入;櫃買確走 MIS。 |
| F-04 | LOW | CONFIRMED | 主 agent sed stock_engine.py:1104-1114 → `(code == self._main or code in self._backfilled)` 後 `self._enqueue_backfill(code)`。pr-126 F-02 建議句本身就漏了這條,本 PR 逐字照抄。 |
| F-05 | LOW | CONFIRMED | 主 agent 對照本 session 的 mutation 實跑指令:M4 只列了 test_corr_source + test_stock_source 兩檔(103 = 73 + 30),M1–M3 跑三檔。 |
| F-06 | LOW | CONFIRMED | 主 agent grep `from copycat.server` tests/live/ → 僅 test_stock_source.py:1272;函式內 import,無循環。純結構,ask-user。 |

## Action Items

**Severity calibration**:6c(移除既有防護類)—— 本 PR 是**恢復**防護(個股 / corr 閘回 13:35),不屬移除類;6d-1 hedge cap:F-01 的損害是「下一個 session 可能為已有兜底的情境加第二段閘」的間接後果 → cap Nice;6d-3 Must Fix 雙半條件:六條無一有 user-visible 重現路徑 + 阻擋發布(全是註解 / 文件 / 測試放置),無 Must / Should;6d-2 由 4.3b 取代;provenance cap N-A。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix（合併前必修）

- 無

### Should Fix（強烈建議）

- 無

### Nice to Have（可選優化）

- F-01 `_INDEX_HEAL_END` 代價段改口:分時自癒會連帶重掛 IX0001,現價欄應會跟著回來(**未實測**,次一交易日以 `/api/index/state` 現價欄 vs 時戳核)(`copycat/live/stock_source.py:49-51`;next-time:40 同句)
- F-02 §4 descriptor 改「stale watchdog 凍結點」+ 可觀測漂掉症狀(`CLAUDE.md:269-272`;test_stock_source.py:1270 同步)
- F-03 「IX0001 / 櫃買」改「IX0001;櫃買走 MIS poll 不吃這把」(`copycat/live/stock_source.py:43`、:480)
- F-04 個股當日重補路徑補「漲跌停值變」+ 逾時重排,加情境限定語(`copycat/live/stock_source.py:38-39`;next-time / artifact 同句)
- F-05 mutation 表 M4 補選集註記或補跑 139 組(`.claude/mod/heal-gate-per-consumer/verification.md:42`)
- F-06 parity 測試放置(`tests/live/test_stock_source.py:1272`;ask-user)

### 參考用（任一軸驗證為 REFUTED 或 OUT_OF_SCOPE）

- 無

## 審查工具比較 (qualitative)

- CC 視角(python-reviewer):行為改動本身(per-consumer 拆閘)通過全部自述核對(同值 pin、兩把 callable pin、邊界表指認、mutation 表);抓到的六條全是「修 pr-126 文件 finding 時再留一層殘影」—— F-01 / F-04 是代價 / 路徑仍寫重(與 pr-126 F-02 / F-05 同型)、F-02 是新立的契約條 descriptor 指錯 watchdog 且症狀寫成正常態、F-03 櫃買誤植、F-05 / F-06 證據衛生。in-flow two-axis round 1 抓的是 verification 缺檔 / 命名條 / §4 該不該立;本輪抓的是立了之後寫得對不對。
- Codex / Gemini:N-A。
- 4.3b:CONFIRMED 6 / 0 降級;無 lone-finding 降級(他軸缺席不算沉默)。
- 對抗式第三軸增益:N-A。

## 沒做的部分（結案對帳）

- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(grep / sed 追 code 路徑)。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 實跑)。
- 真實環境:本 PR 的 13:25 / 13:35 兩把閘要等次一交易日(08-28)驗:`grep 零推播自癒 | grep IX0001` 13:25 後 0 筆、13:25–13:35 個股面照救、13:36 `/api/index/state` 時戳;prod 8721 現跑 user 19:26 自起的孤兒 SHA `f8232339`(行為含本 PR),明早應從 master 重起。
- 未驗證前提:F-01「重掛 snapshot 讓現價欄回來」是 skill 既載事實的推論,未於 13:25 後真環境量到(次一交易日可用 `/api/index/state` 現價欄 vs 時戳核);F-02 的可觀測症狀是建議的判準,未實跑。
- Self-Verify:已執行,`VERDICT: VIOLATIONS: R8` —— auditor 抓到 F-01 的修法 / Nice 條目把「重掛 snapshot 讓現價欄回來」寫成肯定句,而本報告自己列它為未驗證前提;修正 = 發現總覽、inline block、Nice 條目三處改成「應會跟著回來(未實測,次一交易日核)」。修正後未重派 auditor,**未經第二次獨立稽查**(auditor 以 Read 讀取草稿檔本身,未讀其他產物)。
