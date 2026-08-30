# PR #145 Code Review 比較報告 · SHA 83adbe03
**Report projection schema**: 1

**PR**: [loger-w/copycat#145](https://github.com/loger-w/copycat/pull/145)
**標題**: mod(observability): 可觀測性小批 —— 重掛 snapshot 指紋 / VX sparse / index 日曆誤標 / 期貨 1K 健康 / 損益列 INFO
**作者**: loger-w(commits 署名 Loger)
**分支**: `mod/observability-batch-0828` → `master`(PR 狀態 MERGED,merge commit 086f2463;遠端分支已刪、回溯 review)
**變更**: 19 檔案, +796 / -27
**審查日期**: 2026-08-28
**Review input basis**: source repo R_kgDOTsITBg + 83adbe03ac89dd2bd231dbf429455ec719d47b75;destination repo R_kgDOTsITBg + e74b40c323fe80006b5761b7a51db3428c6d5809;`input_binding: verified`(遠端分支 merge 後已刪,但 headRefOid 本地存在;`git worktree add --detach` 於該 SHA,worktree HEAD = source SHA 逐字相等;destination SHA `git cat-file -t` = commit、`git merge-base --is-ancestor e74b40c3 origin/master` 成立;spec 自述「自 master e74b40c3」)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前 `gh pr view 145` 重抓 headRefOid / baseRefOid 與 reviewed 完全相同;origin/master 因本 PR 自身 merge 與後續 commit 前進到 541567b0,不影響 PR 的 destination 綁定);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-145`(detached)
**worktree HEAD**: 83adbe03ac89dd2bd231dbf429455ec719d47b75
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC 軸 finding;4.2 N-A 無 codex → 全部 CC finding INCONCLUSIVE,由 4.3b 主 agent 逐條實查)+ Gemini 軸 N-A(本機無 agy)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer × 2 chunk instances(chunk A = 13 檔生產碼 + docs、chunk B = 6 檔測試;dispatch 顯式 model=opus、effort 依 frontmatter xhigh;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=N-A(security-reviewer 未觸發:diff 無 auth / 請求體 / 憑證 env);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(未 dispatch);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=19 → covered 9 / no-issues 10 / skipped 0 / **missed 0**(chunked: 是;FILE_COUNT=13 源檔 ≤ 15 但 DIFF_LINES=823 > 800 → 排序後切兩塊:chunk A 前 13 檔 / chunk B 後 6 檔;兩塊 accounting 聯集 = F,零 repair 輪)
**定位 (ENH-B)**: anchored exact 18 / ambiguous 0 / **FAILED 0**(18 個 anchor 以 `git show 83adbe03:<path>` 逐字比中且唯一;line 以比中結果為準)
**React-doctor (2.97)**: N-A(非 React PR:F 無 `.jsx` / `.tsx`,frontend/ 零 diff)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh <worktree> origin/master` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,19 檔全部 authored)
**審查軸狀態**: primary(python-reviewer chunk A)PASS(9 findings、13/13 accounting、白名單 8 條自核 PASS、乾淨快照 ruff / pyright / 388 passed);primary(python-reviewer chunk B)PASS(9 findings、6/6 accounting、10 次 mutation、worktree 還原 status 空);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification:4.1 N-A / 4.2 FAIL→INCONCLUSIVE(無 codex)/ 4.3b PASS(主 agent 以 `git show` 乾淨內容逐條實查,18 條 CONFIRMED)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus,tools=0)回 R1–R4 / R6–R8 / R10 PASS、R5 / R9 FAIL、`VERDICT: VIOLATIONS: R5, R9`;R5 已補寫 canonical record 欄位對照句;R9 係稽核輸入把 18 個 inline block 摘要化(草稿檔本體含全部 18 塊、helper `comment-coverage` 契約通過),未重派 auditor,**未經第二次獨立稽查**

**Report generation**: sha256:3e33cfd253c2a53eec9ddcac45f9bebfa6110ce9a5ed61f5f458336d250216b7

---
## [完整證據副檔](pr-145-review.audit.md)
### finding_uid 索引
[971fe815bfafee9bcb3c](pr-145-review.audit.md#發現總覽) · [775e3590862acadd697e](pr-145-review.audit.md#發現總覽) · [e8fa9afa43bf62ca7d6a](pr-145-review.audit.md#發現總覽) · [1c404f6b43fb23bedf4c](pr-145-review.audit.md#發現總覽) · [fe3ebc3b0a6e092a2e4c](pr-145-review.audit.md#發現總覽) · [f88931bd5d3caa0d9024](pr-145-review.audit.md#發現總覽) · [182537cae8b80b91e587](pr-145-review.audit.md#發現總覽) · [d5af3529374d0a7898b0](pr-145-review.audit.md#發現總覽) · [ef322a1051e71ac6238c](pr-145-review.audit.md#發現總覽) · [96863a069be142c61fd3](pr-145-review.audit.md#發現總覽) · [d05675972101d4d264a7](pr-145-review.audit.md#發現總覽) · [2906853c6fc091d29dea](pr-145-review.audit.md#發現總覽) · [c5c1199d874fced5a4fe](pr-145-review.audit.md#發現總覽) · [9f5b12fd6bc235523e60](pr-145-review.audit.md#發現總覽) · [66c200f112ffc9f8d501](pr-145-review.audit.md#發現總覽) · [6d81559f8ec5758ffeb1](pr-145-review.audit.md#發現總覽) · [1b869fcc46b8bddd32d8](pr-145-review.audit.md#發現總覽) · [db79faa3958dd8147b75](pr-145-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | `_tradable_minutes_between` 只比 HHMM 落不落在段內、完全不看日期:週五收盤 → 週一開盤、連假整段全被算成可交易分鐘,差距超過 `_MINUTE_WALK_CAP`(2880)還直接回上限 → 冷 memo 時 `build_minute` 抓 30 個日曆日必含 4 個週末,每 (product, session) 一行「期貨 1K 中段缺格 …最大 2879 分」的假警報,每次 server 重啟最多 6 行 —— 正是 L262 要 grep 的訊號,verification §3「開盤零假警報」不成立(`copycat/server/futures_engine.py`) | HIGH [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Should Fix | `auto-fix` | 主 agent 對乾淨快照實跑 `_tradable_minutes_between(週五 15:01, 週一 08:46)` = 2880、`bars.py:503-507` 歷史段 lo..hi 為連續日曆日;最小修法局部(跨 > 1 日曆日的相鄰兩根跳過、走到 cap 視為不判),正解接 `TradingCalendar` 另議 |
| F-02 | `TestHealResubSnapshot` 用真 `time.monotonic()` 當 base,卻把 `_heal_tick(base + 100.0)` 的注入時鐘寫進 `_sub_at`(`_heal` :711),隨後 `_note_push` 取真時鐘 ≈ base → elapsed ≈ −100 s、`−100 <= 10` 恆真 —— 寬限分支是靠「重掛時刻在未來」這個 prod 不會有的組態走進去的;本 PR 唯一的行為改動在 prod 會不會觸發、`_SNAPSHOT_GRACE_SECS` 的值,四條測試都沒釘(mutation `< 0.0` 與 `10.0 → 0.0` 皆存活)(`tests/live/test_tc4.py`) | HIGH [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Should Fix | `auto-fix` | 主 agent 讀 `_heal` :711 `self._sub_at[symbol] = now`(注入值)確認機制;reviewer 已實測 3 行修法(`base - 100.0` + `_heal_tick(base)`)讓 mutation A 被殺 |
| F-03 | `_note_push` 先 `if symbol not in self._heal_attempts: return`,DEBUG 參數裡再裸索引 `self._heal_attempts[symbol]`;`_unsub`(stock_engine `_release`,別的執行緒)會在中間 pop 同一鍵 → KeyError;`_listen_loop` 的 try 只包 `sock.recv()`,`handle_raw(raw)` 裸呼叫 → listener thread 死、整條 session 零推播且 `_check_stale` 一起停(`copycat/live/tc4.py`) | MEDIUM [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `git show` :1129-1135 確認 try 範圍、:941-959 `_unsub` 無鎖、`stock_engine.py:435` 為 caller;窗口 µs 級、機率低但後果是自癒機制自身的失效樣態,修法 = `.get()` 一次取值,三行 |
| F-04 | 休市誤標 WARNING 的「每個日曆日一次」只驗「同一天不重印」,`make_engine` 的 `today_fn` 固定 2026-07-28,`_holiday_date != key` 重置 / `_holiday_warned == key` 兩支換日分支零斷言 —— 退化成「每 process 一次」全綠;prod 連跑數日不重啟,日曆連錯兩天第二天起靜默(`tests/server/test_index_engine.py`) | MEDIUM [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | reviewer mutation(`if self._holiday_warned is not None: return`)65 passed 存活;主 agent 讀 `make_engine` :56 `today_fn or (lambda: _dt.date(2026, 7, 28))`;補一條可變 `today_fn` 的測試即可 |
| F-05 | `_1k_warned` 去重三半只釘一半:「尾根前進後要再印」與「lag / gap 各記各的」未釘 —— 改成每 product 一輩子一次、或兩把 key 併一把,66 條全綠;代價 = 首次 WARNING 後真正持續落後 / 缺格的後續事件全部靜默(`tests/server/test_futures_engine.py`) | MEDIUM [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | reviewer mutation D / E 存活、F(值改常數)2 failed 證明只有「同尾根不重印」被釘;四條測試皆單一份 `_Bars(bars)`,tail_t 恆定;補第三次呼叫換尾根 + 一條同時 lag + gap |
| F-06 | 損益 INFO 斷言 `startswith("… price=156.0")` 剛好切在 `(原 avg=%s,標籤原文=%r)` 之前,`lines[1]` 只查 `"avg=151.0" in` —— 兩格拿掉 407 passed;`標籤原文 = r.kind_raw` 正是 round 1 b1 拍板保留、spec 目標 #4 用來校準無券空單的欄位;`_avg_logged` 的 per-kind 一半同樣未釘(kind 換常數 407 passed)(`tests/capital/test_client.py`) | MEDIUM [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 核 `profit_rows.py:31-34` 欄位([10]=150.55 / [12]=451650 / [9]=12345 / [5]=156)與斷言一致、`pnl_variant({10: …})` 確只動均價欄;修法 = 整行比對或補 `標籤原文='融資'` / `原 avg=None` 兩個 `in` |
| F-07 | 缺格測試的 bar 序列往回跳(15:03 排在 15:02 前):`15:03 → 15:02` delta −1 被快路徑吞掉,真正算成缺格的是 `15:02 → 15:06`(3)與 `15:07 → 05:00`(832)= 「2 段」;排成 TC4 真正會回的遞增序後只剩 1 段、斷言當場紅;註解寫的「15:03–15:05 三根缺」與實際計算不符(`tests/server/test_futures_engine.py`) | MEDIUM [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 以乾淨快照的 `_bar_minute` / `_tradable_minutes_between` 逐對重算:as written 2 段、sorted 1 段;修法 = 遞增序 + 拿掉 15:03、把要驗的缺格明寫成 15:02 跳 15:06 |
| F-08 | 註解宣稱落後量「與前端 gate 5 用『根數』同一把尺」,實際固定少 1:前端 `tradeSlotOf` 非整秒成交 +1 分(終點標記)再數 (from, to],後端 `_last_trade_at` 直接截 `t[:5]` 不 +1 → 尾根 09:01 / 最後成交 09:10:30 前端 10 根、後端 9 分(本 PR 測試就斷言「落後 9 分」);前端 lag=4 就掛徽章、後端 lag=5 才印,L262 原始症狀正落在這條邊緣帶(`copycat/server/futures_engine.py`) | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `ask-user` | 主 agent 讀 `FuturesChart.tsx:101-118` `onBoundary ? 0 : 1` 與 `allday.ts:164-174` `(from, to]` 確認差 1;修法二擇一(後端補 +1 對齊 / 註解改口「少 1」)是口徑決定,user 拍板 |
| F-09 | `_fetch_and_check` 在 `fetch()` 成功後直接呼叫 `_check_1k_health`,沒有例外圍籬;docstring 說「純診斷不影響回傳」但只守了 strptime 的 ValueError,`bar["t"]` 缺鍵 / 非 str / 日後邏輯 bug 都原樣從 `bars_range`(只接 HistoryTimeoutError / ConnectionError)→ `build_minute` → route 逃出去 → 500,「少印一行 log」升級成「圖整個掛掉」(`copycat/server/futures_engine.py`) | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `git show` :372-379 只有兩個 except、`bars.py:500-512` 與 `app.py:1700-1745` 無 try 確認傳導鏈;同檔 `_flush` / `tc4._heal_loop` 都有圍籬先例;三行 `try/except Exception: logger.exception` |
| F-10 | `futures_engine.py` 在 base 是 `ruff format --check` 乾淨的,本 PR 把它弄髒(`_fetch_and_check` 簽名 104 字元 > 100);同批 index_engine / client / corr_config 在 base 就不乾淨不算迴歸,但這是唯一把乾淨檔弄髒的,且 round 1 S2 / b2 已對同檔排版提過一次(`copycat/server/futures_engine.py`) | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 對 base / head 兩版 `ruff format --check --line-length 100`:`already formatted` → `would be reformatted`;修法 = 簽名拆逐參數一行 |
| F-11 | skill 新增第 189–190 行寫「08-28 起 `_note_push` … 重掛後 10 s 內的 SUBQUOTE snapshot **不清** attempts」,緊接的既有第 191–192 行仍以現在式寫「重掛的 SUBQUOTE 本身會回 snapshot … `_note_push` 照樣清 attempts」—— 同一場景兩句互斥,08-31 對帳要靠讀 attempt 階梯,先讀到舊句就會用修前模型解釋修後 log(`.claude/skills/tc4-market-facts/SKILL.md`) | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `git show` :187-194 確認兩句相鄰且同場景;純文件修法 = 舊句加「(08-28 指紋規則之前)」限定 |
| F-12 | `TradeKind` 插在 `PositionCloseRequest` 與 `StockOrderRequest` 之間,把原本嚴格字母序的 import 區弄亂;ruff 未開 `I` 規則所以 gate 不紅(`copycat/capital/client.py`) | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `git show` :50-62 確認;移到 `StockOrderRequest` 之後一行 |
| F-13 | `_1k_warned` 的 kind 是裸字串 `"lag"` / `"gap"`(型別 `tuple[str, str]`,repo 對 `BarsStatus` / `AvgSource` 已用 `Literal`),且 key 不含 session:期貨 tab 對 TXF 打 `session=allday`、大盤 tab 打 day,兩者 domain 不同、缺格結果不同,但日盤時段尾根同一根 → 先跑的靜默壓掉後跑的(`copycat/server/futures_engine.py`) | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep 前端:`FuturesChart.tsx:43` 恆 `session=allday`、`useFuturesBars.ts:13`「大盤 tab 的 TXF(day)」;`app.py:1712/1720` 兩閉包都傳 `eff_session`;key 改 `(product, session, kind)` + `Literal["lag","gap"]` |
| F-14 | 四條新測試全帶 `session="allday"`,`_session_domain` 的 else 分支(`(FUTURES_MINUTE_DOMAIN,)`)與 `_bar_minute` 回 None 時整組 return 兩條路零覆蓋 —— else 改恆回 allday,tests/server 1310 條全綠;`/api/market/bars/TXF?tf=1` 不帶 session 走 day 是合法路由(`tests/server/test_futures_engine.py`) | LOW [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | reviewer mutation I 存活;主 agent grep 新增段無 `session="day"` 的 tf=1 呼叫;各補一行參數化 |
| F-15 | 既有 `test_unsub_clears_every_heal_book`(:1104)明列 5 本帳宣稱「every」,本 PR 新增的 `_push_fp` 沒加進去、另寫 `test_unsub_clears_the_fingerprint` —— 下一個加帳本的人看那條綠燈仍會漏掉自己那本(`tests/live/test_tc4.py`) | LOW [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `git show` :1115-1120 tuple 確無 `_push_fp`,而 `_unsub` :951-957 已含;兩行補回窮舉 |
| F-16 | 兩組新 helper 與既有重疊:`_push_raw(symbol)` ≡ `_push_raw_quote({"Symbol": symbol})`;`_Bars(FakeSource)` 與既有 `TestBarsRangeSession._WithBars`(:1091,spec Caller map 點名)只差「回固定 bars」vs「記 call」,且 `_Bars.fetch_bars_range` 把 tf / start / end 全丟掉,tf="D" 不進健康檢查只能靠「沒 log」間接證明(`tests/live/test_tc4.py`) | LOW [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | reviewer grep `_push_raw(` 20+ 既有 / `_push_raw_quote(` 6 新;合成一支 fake 順手可斷言 tf / session 有被轉發 |
| F-17 | `TestHolidayPushWarning` 直呼 `eng._handle_quote`,同檔既有 10 處餵報價全走 `fake.on_message`(順帶涵蓋 `_on_quote_threadsafe`);降 seam 可接受但 docstring 沒說明為何降(`tests/server/test_index_engine.py`) | LOW [python-reviewer B] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | reviewer grep `fake.on_message(` 10 處既有 / `_handle_quote(` 5 處全新增;class docstring 補一句「純同步:只驗記帳」 |
| F-18 | VX 標成**全日** sparse(`segment_leg_gate` 對 CFE 段恆 True → 任何時段只剩 R1),但證據只有台北 08:47–09:55 這 68 分鐘窗;同檔上兩行既有註解記「01:02 實測 VX 45 s 推 19 則」(美盤盤中活躍)—— 拿早盤 7 發 churn 換美盤時段「單腿死無人救」,CLAUDE.md sparse 契約段自己點名這是零錯誤訊號的誤標代價(`copycat/corr_config.py`) | LOW [python-reviewer A] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(知情用) | 參考用 | `ask-user` | spec 第 5 列明寫兩處加 `sparse: true`、user 已拍板 → 不是 PR 缺陷;主 agent `git show corr_source.py:53-64` 確認 CFE 恆 True、`tc4.py:649` sparse `continue` 無時段條件;是否把 sparse 做成時段化(比照 `heal_symbol_active`)是產品取捨 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 971fe815bfafee9bcb3c action=auto-fix
F-02 finding_uid: 775e3590862acadd697e action=auto-fix
F-03 finding_uid: e8fa9afa43bf62ca7d6a action=auto-fix
F-04 finding_uid: 1c404f6b43fb23bedf4c action=auto-fix
F-05 finding_uid: fe3ebc3b0a6e092a2e4c action=auto-fix
F-06 finding_uid: f88931bd5d3caa0d9024 action=auto-fix
F-07 finding_uid: 182537cae8b80b91e587 action=auto-fix
F-08 finding_uid: d5af3529374d0a7898b0 action=ask-user
F-09 finding_uid: ef322a1051e71ac6238c action=auto-fix
F-10 finding_uid: 96863a069be142c61fd3 action=auto-fix
F-11 finding_uid: d05675972101d4d264a7 action=auto-fix
F-12 finding_uid: 2906853c6fc091d29dea action=auto-fix
F-13 finding_uid: c5c1199d874fced5a4fe action=auto-fix
F-14 finding_uid: 9f5b12fd6bc235523e60 action=auto-fix
F-15 finding_uid: 66c200f112ffc9f8d501 action=auto-fix
F-16 finding_uid: 6d81559f8ec5758ffeb1 action=auto-fix
F-17 finding_uid: 1b869fcc46b8bddd32d8 action=auto-fix
F-18 finding_uid: db79faa3958dd8147b75 action=ask-user
### Inline Comments per Finding（直接複製貼到 PR review）
#### F-01 週末 / 連假的空窗會被算成「中段缺格」,每次冷啟動固定噴假警報
**File**: `copycat/server/futures_engine.py`
**Line**: 434-438

**Comment**:
```
_tradable_minutes_between 只看 HHMM 有沒有落在段內,完全不看日期 → 週五 15:01 → 週一 08:46 這種相鄰兩根,
週六週日整段都被當可交易分鐘;差距 > _MINUTE_WALK_CAP(2880)又直接回上限,所以印出來永遠是「最大 2879 分」。
冷 memo 時 build_minute 對歷史段抓的是近 30 個日曆日(bars.py:503-507 lo..hi 連續),必含 4 個週末
→ TXF/MXF/TMF × day/allday 每次 server 重啟最多 6 行「期貨 1K 中段缺格」全是假的,
重啟後 grep "期貨 1K" 第一批命中沒有一條是真的(verification §3「開盤零假警報」不成立)。
乾淨快照實跑:週五 15:01→週一 08:46 allday = 2880、週五 13:45→週一 08:46 day = 2880;平日隔夜 13:45→08:46 = 1(唯一對的一格)。

最小改法(兩處):
    if (cur_at - prev_at) <= _dt.timedelta(minutes=1) or (cur_at.date() - prev_at.date()).days > 1:
        continue  # 相鄰分鐘,或跨過整個休市日(週末 / 連假)—— 沒有段跨兩個日曆日
並讓 _tradable_minutes_between 走到 cap 時回 0(「不確定就不判」,現在是「不確定就報警」方向反了)。
正解是把 TradingCalendar 餵進 FuturesEngine(bars.py::_possible_data_days 已經是同一個概念),逐分走時跳非交易日 —— 可另開。
```
#### F-02 寬限窗那條分支是靠「未來的 _sub_at」走進去的,prod 真正會發生的正向 elapsed 沒被驗過
**File**: `tests/live/test_tc4.py`
**Line**: 828

**Comment**:
```
base 是真 time.monotonic(),但 _heal_tick(base + 100.0) 會把注入的 base+100 寫進 _sub_at(tc4.py:711),
之後 handle_raw → _note_push 取的是真時鐘 ≈ base → now - sub_at ≈ -100,-100 <= 10 恆真。
分支是走到了、測試也綠,但走的是「重掛時刻在未來」這個 prod 永遠不會有的組態。
實測:把判定式改成 `now - sub_at < 0.0`(prod 永不成立)→ test_tc4 90 passed;_SNAPSHOT_GRACE_SECS 改 0.0 → 624 passed。
本 PR 唯一的行為改動就這一條,而真環境驗證又延到次一交易日 grep —— 兩邊同時放行。

把時間關係倒過來就好(3 行,實測 mutation 被殺):
    src._sub_at = {sym: base - 100.0}
    src._last_push = {sym: base - 100.0}
    src._heal_tick(base)  # 重掛 → _sub_at = base(真時鐘現在),下一則推播 elapsed ≈ +0.001
第二輪 _heal_tick(next_before + 1.0) 不必動。順手補一條 elapsed 落在 (0, 10) 與 (10, ∞) 兩側的對照更穩。
```
#### F-03 DEBUG 那行裸索引 _heal_attempts,跟 _unsub 撞到會把 ZMQ listener thread 打死
**File**: `copycat/live/tc4.py`
**Line**: 736

**Comment**:
```
前面 `if symbol not in self._heal_attempts: return` 到這裡的 `self._heal_attempts[symbol]` 之間沒鎖,
_unsub(stock_engine._release 那條路,別的執行緒)會從中間把同一鍵 pop 掉 → KeyError。
_listen_loop 的 try 只包 sock.recv()、handle_raw(raw) 是裸呼叫(tc4.py:1129-1135)→ listener thread 直接死,
整條 session 零推播、_check_stale 也一起停(它在同一個迴圈裡)—— 正是這套自癒要防的那種失效。
改前用 pop(symbol, None) 結構上不會炸,這是本 PR 新開的路。窗口 µs 級、機率低,但修法零成本:

    attempts = self._heal_attempts.get(symbol)
    if attempts is None:
        return
    ...
    logger.debug("... (attempt %d)", symbol, now - sub_at, attempts)
```
#### F-04 「每個日曆日一次」只驗了同一天不重印,換一天要能再印沒驗
**File**: `tests/server/test_index_engine.py`
**Line**: 1346

**Comment**:
```
兩條測試都跑在 make_engine 預設的單一日曆日(today_fn 固定 2026-07-28),
_note_holiday_push 的 `_holiday_date != key` 重置、`_holiday_warned == key` 早退兩支換日分支零斷言。
實測把它退化成「每 process 一次」(`if self._holiday_warned is not None: return`)→ 65 passed。
prod server 是連跑數日不重啟的,日曆連錯兩天第二天起這行 log 就靜默消失,正好是它存在的場景。

補一條:同一顆 engine 用可變 today_fn(list.pop / nonlocal),第 1 天湊 5 價 → 1 行,第 2 天再湊 5 價 → 2 行,
並斷言第 2 行用的是新日期字串。
```
#### F-05 去重只驗了「同尾根不重印」,尾根換了要再印、lag / gap 不互吞都沒釘
**File**: `tests/server/test_futures_engine.py`
**Line**: 1265

**Comment**:
```
_1k_warned 的契約有三半:同 (product, kind) 同尾根一次 / 尾根前進後重印 / lag 與 gap 各記各的。
四條測試都只用一份固定 _Bars(bars),tail_t 整條測試不變,所以後兩半觀察不到 —— 實測改成
「每 product 一輩子一次」66 passed、lag / gap 併一把 key 66 passed;只有「值改常數」才 2 failed。
真代價:第一次 WARNING 之後,持續落後 / 缺格的後續事件全部靜默,而那正是 L262 要 grep 的東西。

在 test_lag_behind_last_trade_warns_once_per_tail 尾巴加第三次呼叫、換一份尾根更後面的 bars,斷言 count 變 2;
另加一條同一次呼叫同時觸發 lag + gap,斷言兩行都在。
```
#### F-06 損益 INFO 的斷言切在 price 前面,標籤原文(這行 log 存在的理由)沒被釘
**File**: `tests/capital/test_client.py`
**Line**: 2218-2221

**Comment**:
```
startswith("… price=156.0") 剛好停在格式字串的括號前,(原 avg=%s,標籤原文=%r) 兩格沒有任何斷言;
lines[1] 更只查 "avg=151.0" in。實測把這兩格從 logger 呼叫拿掉 → tests/capital 407 passed。
標籤原文 = r.kind_raw 正是 round 1 b1 拍板保留、拿來校準無券空單 [25] 的那一格 —— 下一次 8358 那種現場不可重現,
log 只剩數字就白等了。順帶:_avg_logged 的 kind 換常數也 407 passed(治具只有一種 kind)。

改成整行比對,或至少補:
    assert "原 avg=None" in lines[0] and "標籤原文='融資'" in lines[0]
```
#### F-07 缺格測試的 bar 往回跳(15:03 排在 15:02 前),「2 段」是靠這個不可能的輸入湊出來的
**File**: `tests/server/test_futures_engine.py`
**Line**: 1317-1318

**Comment**:
```
逐對重算:13:45→15:03 missing 2 / 15:03→15:02 delta −1 被快路徑吞掉 / 15:02→15:06 missing 3(段)/ 15:07→05:00 missing 832(段)→ 2 段。
註解說的「15:03–15:05 三根缺」不是實際被算到的那段。排成 TC4 真正會回的遞增序後:13:45→15:02 missing 1、15:03→15:06 missing 2,
都 < 3 → 只剩 1 段,"2 段" 當場紅 —— 誰順手把 bars 排序就踩到一個查不出原因的紅燈。

拿掉 15:03 那根、把要驗的中段缺格明寫成 15:02 直接跳 15:06,段界那條另留一根表達「首根延後兩分不算缺格」。
```
#### F-08 這句「與前端 gate 5 同一把尺」不成立,後端固定少數 1 根
**File**: `copycat/server/futures_engine.py`
**Line**: 35-36

**Comment**:
```
前端 tradeSlotOf 把最後成交換成終點標記(非整秒 +1 分,FuturesChart.tsx:108-109)再數 (from, to] 根數;
後端 _last_trade_at 直接截 t[:5] 不 +1,再數 (tail, last] 可交易分鐘。門檻同值同用 >,但非整秒成交後端恆少 1:
尾根 09:01 / 最後成交 09:10:30 → 前端 10 根、後端 9 分(本 PR 測試就斷言「落後 9 分」)。
結果前端 lag=4 就掛「分時資料落後 4 根」,後端 lag=5 才印 —— user 08-25 那種「K 棒沒更新」正好落在這條邊緣帶。

二擇一:_last_trade_at 對非整秒成交補 1 分(照 tradeSlotOf 的 onBoundary 規則),或把註解改口「後端以成交所在分鐘計,比前端根數少 1」。
```
#### F-09 診斷檢查沒圍籬,它自己炸會把本來 200 的 /api/market/bars 打成 500
**File**: `copycat/server/futures_engine.py`
**Line**: 387-388

**Comment**:
```
docstring 說「純診斷不影響回傳」,但只守了 strptime 的 ValueError;bar["t"] 缺鍵 / 非 str / 這段日後的邏輯 bug
都會從 bars_range(只接 HistoryTimeoutError / ConnectionError)→ build_minute → route 原樣逃出去 → 500。
同檔 _flush、tc4._heal_loop 對這種「漏接一次代價很大」的邊界都有圍籬。三行:

    try:
        self._check_1k_health(product, bars, end, session)
    except Exception:
        logger.exception("期貨 1K 健康檢查失敗(續行)")
```
#### F-10 這支檔在 master 是 ruff format 乾淨的,本 PR 把它弄髒了
**File**: `copycat/server/futures_engine.py`
**Line**: 383

**Comment**:
```
base 版 `ruff format --check --line-length 100` → already formatted;head 版 → would be reformatted,
唯一 hunk 就是 _fetch_and_check 這行簽名(104 字元)。同批其他三檔在 base 就不乾淨、不動它們是對的,
但這支是這批唯一從乾淨變髒的。拆成逐參數一行就好。
```
#### F-11 skill 相鄰兩句對「_note_push 清不清 attempts」互相矛盾
**File**: `.claude/skills/tc4-market-facts/SKILL.md`
**Line**: 192

**Comment**:
```
新加的第 189–190 行說 08-28 起重掛後 10 s 內的 SUBQUOTE snapshot「不清 attempts」;緊接的第 191–192 行(舊句)
仍以現在式說「重掛的 SUBQUOTE 本身會回 snapshot … _note_push 照樣清 attempts」—— 同一場景,現在只有前者為真。
08-31 對帳要靠讀 attempt 階梯,先讀到舊句就會用修前模型解釋修後 log。

把舊句改成「08-28 指紋規則之前 _note_push 無條件清 attempts,所以那批 240 s 等距 attempt 1 是 snapshot 撐出來的」即可;
末句「判稀疏腿看真成交間隔、不看 attempt」仍成立不必動。
```
#### F-12 TradeKind 插在字母序中間
**File**: `copycat/capital/client.py`
**Line**: 59-61

**Comment**:
```
這個 import 區塊原本是嚴格字母序,TradeKind 被插在 PositionCloseRequest 與 StockOrderRequest 之間。
ruff 沒開 I 規則所以 gate 不會紅,會一直漂下去。移到 StockOrderRequest 之後就好。
```
#### F-13 _1k_warned 的 key 是裸字串、又沒帶 session,day / allday 會互相壓掉對方的缺格警告
**File**: `copycat/server/futures_engine.py`
**Line**: 180

**Comment**:
```
兩件事:(a) "lag" / "gap" 是裸字串、型別 tuple[str, str],打錯不會紅,而這本帳是印不印的唯一開關 —— repo 對 BarsStatus / AvgSource 已經用 Literal。
(b) key 沒有 session:期貨 tab 對 TXF 恆打 session=allday(FuturesChart.tsx:43)、大盤 tab 打 day(useFuturesBars.ts:13),
兩者 domain 不同、算出的缺格不同,但日盤時段尾根同一根 → 共用 (TXF, "gap") 這格,先跑的靜默壓掉後跑的。

key 改 (product, session, kind),kind 型別 Literal["lag", "gap"]。
```
#### F-14 session="day" 分支與「壞時戳整組早退」零覆蓋
**File**: `tests/server/test_futures_engine.py`
**Line**: 1232

**Comment**:
```
四條新測試全帶 session="allday",_session_domain 的 else 分支沒人踩 —— 改成恆回 allday,tests/server 1310 條全綠。
/api/market/bars/TXF?tf=1 不帶 session 走 day 是合法路由(app.py:1673),真被這樣打時夜盤分鐘會被當可交易 → 15:0x 假落後。
另一條:_bar_minute 回 None 時 _check_1k_health 是整組 return(不是跳過那根),也沒測試。各補一行參數化即可。
```
#### F-15 那條「every heal book」測試沒加新帳本,名字從此不為真
**File**: `tests/live/test_tc4.py`
**Line**: 874

**Comment**:
```
test_unsub_clears_every_heal_book(:1104)的 tuple 明列 5 本帳、宣稱 every,_push_fp 沒加進去而是另寫一條。
下一個加帳本的人看那條綠燈仍會漏掉自己那本。setup 加 `src._push_fp[HEAL_A] = ("a", "b", "c", "d")`、tuple 加 `src._push_fp` 兩行修回窮舉;
新測試可留(它多驗了首則推播就建檔)。
```
#### F-16 兩組新 helper 跟既有的重疊
**File**: `tests/live/test_tc4.py`
**Line**: 624-626

**Comment**:
```
_push_raw(symbol) 完全等於 _push_raw_quote({"Symbol": symbol}),改電文外殼要改兩處 →
    def _push_raw(symbol: str, **fields: str) -> str:
        return _push_raw_quote({"Symbol": symbol, **fields})
另一處:test_futures_engine.py:1237 的 _Bars 與既有 TestBarsRangeSession._WithBars(:1091,spec Caller map 自己點名的)只差「回固定 bars」vs「記 call」;
合成一支(__init__(bars=None) + bars_calls)還能順手斷言 tf / session 真的有被轉發 —— 現在 _Bars 把 tf/start/end 全丟掉,tf="D" 不進健康檢查只能靠「沒 log」間接證明。
```
#### F-17 新測試直呼 _handle_quote,同檔其他 10 處都走 fake.on_message
**File**: `tests/server/test_index_engine.py`
**Line**: 1338

**Comment**:
```
TestHolidayPushWarning 是本檔第一個繞過 FakeIndexSource.on_message 的地方(既有 10 處全走 fake.on_message,順帶涵蓋 _on_quote_threadsafe)。
降 seam 讓測試純同步、不必 start/close engine,是可以的取捨 —— 但 docstring 沒說,下一個人會以為 _handle_quote 才是慣例。
class docstring 補一句「純同步:本組只驗 _note_holiday_push 的記帳,不需要 loop 與廣播」。
```
#### F-18 VX 標全日 sparse,證據只有台北早盤那 68 分鐘 —— 美盤時段單腿死從此沒人救(知情用)
**File**: `copycat/corr_config.py`
**Line**: 80

**Comment**:
```
不是 PR 缺陷 —— spec 第 5 列明寫兩處加 sparse: true、user 已拍板。只是要知情:
sparse 是整場豁免 R2(tc4.py:649 的 continue 無時段條件),而 CFE 段在 segment_leg_gate 恆 True,所以 VX 任何時段都只剩 R1(整條 session 全靜默才救)。
支持它的證據是台北 08:47–09:55 的 7 發 churn;同檔上兩行既有註解卻記著「01:02 實測 VX 45 s 推 19 則」—— 美盤盤中它是活的。
CLAUDE.md sparse 契約段自己寫了誤標代價:「單腿死(session 其他腿還在推,R1 不成立)時該腿整場不救,零錯誤訊號」。

若在意:把 sparse 做成時段化(比照 heal_symbol_active 那把閘),或至少把「VX 01:02 活躍」寫進新註解,免得下一輪照「7 發 attempt 1」樣板再標一條真的會死的腿。
```
## 沒做的部分（結案對帳）
- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(`git show` / 乾淨快照 python 重算 / ruff format 對照 / grep)。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 以 `PYTHONUTF8=1 py -3.14` 實跑;第一次未帶 `PYTHONUTF8=1` 產生輸入 JSON 回 `C4_CLI_INPUT_INVALID`,重生後得正式 reason code)。
- 真實環境:本 PR 改的是 log 行為,真環境證據要 prod 跑新版之後(PR 自述判準表 verification §3);本輪未起 server、未取 prod log。F-01 的實證是乾淨快照對 `_check_1k_health` / `_tradable_minutes_between` 的離線實跑,不是 prod log。
- 未驗證前提:F-01 的「TC4 `fetch_bars_range` 對跨週末範圍回單一連續 list」由 range fetch 語意與離線實跑推得、未對真 TC4 打過;F-03 的競態未實際製造(µs 窗口),機制三段皆第一手引文;F-08 的「user 08-25 症狀落在邊緣帶」是對症狀的推論,不是量到的 lag 值;F-13(b) 的「先跑的壓掉後跑的」由 key 結構 + 兩種 session 並存推得,未在 prod 觀察到。
- 主 agent 未重跑 chunk B 的 10 次 mutation(以 reviewer 第一手輸出為證),只重算 F-07 與讀取 F-02 / F-04 / F-06 / F-15 的機制;chunk B 結尾 `git status --short` 空、主 agent 事後清 `__pycache__`(MUTANT 殘留 0)。
- Self-Verify:已執行,`VERDICT: VIOLATIONS: R5, R9`。R5(缺 `display_ordinal` / `action_reason` 對照)→ 已在 canonical record 上方補寫欄位對照句;R9(inline blocks 本體不可驗)→ 原因是 auditor prompt 內把「Inline Comments per Finding」18 塊摘要成一段(草稿 58 KB,為控篇幅),草稿檔本體含全部 18 塊、helper `validate_source_contract` 的 `comment-coverage` / `comment-order` / `comment-blocks` 三項通過 —— 屬稽核輸入不完整而非草稿缺口,但 **18 個 inline block 的內文未經 auditor 逐塊審**。修正後未重派 auditor,本報告**未經第二次獨立稽查**。
- 另:auditor prompt 內嵌的草稿與檔案本體除上述 inline 段摘要外逐字相同。
