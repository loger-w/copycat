# PR #275 Code Review 比較報告 · SHA 2aed3b92
**Report projection schema**: 1

**PR**: [loger-w/copycat#275](https://github.com/loger-w/copycat/pull/275)
**標題**: feat(book-replay): 簿重播引擎 + keyframe/delta 外掛檔 + CLI book-replay(#267)
**作者**: loger-w
**分支**: `feat/book-replay-engine` → `master`
**變更**: 16 檔案, +1413 / -4(其中 9 檔 +424 為 `.claude/feat/book-replay-engine/**` 流程 artifact;實質 code 2 檔 +476、測試 1 檔 +470、文件 4 檔 +43 / -4)
**審查日期**: 2026-09-16
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以收修 PR 處置,不阻擋出貨;merge commit `efce8c03`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `2aed3b92d85a410e6e5fb54c346092d5a884141d`;destination repo id `R_kgDOTsITBg` + baseRefOid `a5c90f160c5c725a410cad374825fdd5a654d86a`;`input_binding: verified`(`refs/pull/275/head` fetch 後 `git rev-parse FETCH_HEAD` = headRefOid;review worktree detached 於該 SHA;baseRefOid commit 存在,所有 diff 以兩個 full SHA 直接指定、不經移動中的 branch ref)
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 13 筆 SHA;分支已刪,`refs/pull/275/head` 仍指 `2aed3b92`,產報告前重抓 headRefOid / baseRefOid 不變);`base_changed=true`(origin/master 前進到 `1c964d51` = merge `efce8c03` + 一筆只動 `graphify-out/**` 的 graphify commit,無其他人 commit);`review_context_changed=false`(`git diff 2aed3b92 efce8c03` 為空、`efce8c03..1c964d51` 排除 `graphify-out` 後為空)
**審查工具**: CC (Opus 5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A**(user 已停用,沿 #188 / #190 / #199 / #230 / #238 / #253 / #255 / #263 前例單軸)+ Codex 對抗式 **N-A** + Cross-axis verification(4.1 N-A 無非 CC finding;4.2 以同軸 `code-reviewer` subagent 獨立複查代替,**非跨軸證據**)+ Gemini 軸 **N-A**(user 已停用)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-opus-5;primary reviewer=python-reviewer ×3 chunk(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .py 佔 source diff 94%(1,082 / 1,150 行);dispatch A 32 tool uses / 479 s、B 24 / 366 s、C 18 / 328 s);同軸複查=code-reviewer(requested=opus / observed=UNAVAILABLE;31 tool uses / 546 s);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派,gate SKIPPED);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=16 → covered 12 / no-issues 3 / skipped 1 / **missed 0**(chunked: 是 —— source 5 檔 < 15 但 diff 1,417 行 > 800 門檻;路徑排序後依序填塊:A 12 檔(artifacts 9 + tc4-market-facts SKILL + CLAUDE.md + CONTEXT.md,465 行)、B 3 檔(book_replay.py / cli.py / next-time.md,482 行)、C 1 檔(test_book_replay.py,470 行);聯集 = F,零 repair 輪)
**定位 (ENH-B)**: anchored exact 13 / ambiguous 0 / **FAILED 0**(去重後 13 條逐字 anchor 對 PR head 重定位全部唯一比中;6 條行號自 reviewer 自報校正:F-01 376→381、F-02 315→376、F-03 419→431、F-04 192→247、F-05 396→404、F-08 305→317)
**React-doctor (2.97)**: N-A(非 React PR;F 無 .jsx / .tsx)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_REPO_SPEC_PATH)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 review worktree 對 baseRefOid 執行、exit 0、零輸出)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer ×3 chunk)PASS(14 raw findings → 去重 13;16/16 accounting;reviewer 附實跑證據:C 以記憶體內突變體 M1–M10 + 三個控制組、B 竄改探針與 `pyarrow.lib.ArrowIOError` / `ArrowInvalid` MRO 實查、A 探針腳本)/ Codex 中性 N-A / Codex 對抗 N-A / Gemini Flash N-A / Gemini Pro N-A / cross-axis verification:4.1 N-A、4.2 以同軸 code-reviewer 獨立複查代替 PASS(13/13 verdict、ID 集合完整;CONFIRMED 10 / PARTIAL 2 / REFUTED 1)/ 4.3a N-A(單軸無 consensus)/ 4.3b 逐條見複查欄與備註
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-275`
**worktree HEAD**: `2aed3b92d85a410e6e5fb54c346092d5a884141d`

**Report generation**: sha256:b14a0d9b976cf7b821f72d6bcdff65fd305e16dbf4ccc6ec4648212724f05ed2

---

## Spec 依據

- 正式 spec = GitHub issue #265(簿重播時光機,48 user stories / Implementation Decisions / Testing Decisions / Out of Scope)與本 PR 的 ticket #267(九條 acceptance criteria);**不在 repo 檔案內**。實作期間 user 追加兩項格式拍板(時間軸改用 server 收到時刻、成交則存價量),已以留言追記在 #265,並在 #268 留言附改寫後的驗收時刻;連帶發現另開 #274。repo 內另有 `.claude/feat/book-replay-engine/verification.md`(AC 逐條對照)與兩輪 merge 前 two-axis 紀錄 `code-review-round-1.json` / `code-review-round-2.json`;本輪 reviewer 讀過,不重提已處置條。F-08 是 round-2 收修**說過頭**的部分(處置文字與 docstring 宣稱已補齊,實際仍有缺口),不是重提。
- **⚠️ spec 作者 = PR 作者**(issue #265 / #267 與兩項追加拍板皆由 loger-w 提出,實作也由同一帳號提交;out-of-scope 判定以此 spec 為據時注意利益重疊 —— 本輪 13 條無一落在 spec 的 Out of Scope 清單內)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_REPO_SPEC_PATH`(spec 是 GitHub issue,無 repo 內 path:line 可綁;模組說明「外掛檔 v1」是實作者自寫的格式描述,非 MUST / SHALL 型 normative clause;0 clauses / 0 findings / 0 observations / 0 invalidated)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool calls N-A。報告的 C4 輸入規則 = 只取自最後一次 reducer `human_projection`:本輪 gate SKIPPED、未派 `spec-compliance-reviewer`、未跑 reducer,`human_projection` 為空集合,`invalidated_ids ∩ report_finding_ids = ∅`(兩者皆空),整份報告零 C4 候選或 invalidated 語意內容。
- Author calibration(Step 2.2):無作者校準檔(`loger-w.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

provenance: N-A(base = master)。13 筆 commit(PR head 序):docs `828c0c29` → feat `747f1694`(引擎 + 編碼)→ feat `99b09dd5`(CLI)→ docs `0b1dbff6` → round-1 收修 refactor `e0a08941` / feat `955aa83b`(收到時刻軸 + 成交欄位,user 拍板)/ docs `08f3beb8` / skills `fab92858` / docs `02a43950` → round-2 收修 refactor `ecfca97e` / feat `aa4b2b20` / docs `f86676a1` → artifacts `2aed3b92`(SHA 為 PR head;master 上 rebase 後已改寫,merge 結果 `efce8c03`)。

| 檔案 | 變更類型 | 說明 |
|---|---|---|
| `copycat/book_replay.py` | A | 零 IO 簿重播引擎:`replay_books`(依代號分組、`msg_seq` 排序、一次一個交易日)、`Frame` / `Trade` / `BookReplay`(`anomalous_trades`)、時鐘點規則(不倒退 + 未來容差 60 s)、`recv_ms` 不倒退軸;外掛檔 v1:`encode` / `plugin_js`(gzip mtime=0)/ `parse_plugin_js`(呼叫鍵比對)/ `decode`(keyframe 自檢 + `_check_header`)/ `book_at`;`PluginPayload` TypedDict、`PluginFormatError` |
| `copycat/cli.py` | M | 子命令 `book-replay --date YYYYMMDD [--dir] [--out]` + `_book_replay`:只收兩個 parquet 都在的已轉檔日(否則 exit 2)、`load_day` → `replay_books` → 逐檔 encode → parse + decode 全等自檢 → `atomic_write_text`、摘要一行、自檢失敗 / IO exit 1 |
| `tests/test_book_replay.py` | A | 27 案:排序分組 / 混日拒絕、TestClock 四條(時鐘點、1815 未來時刻、收盤撮合晚到 vs 蓋章倒退、本機鐘落後)、收到時刻軸不倒退、成交欄位、round-trip / 跳轉(K=1/3/256)/ 外掛檔文字格式、decode 竄改 11 種 + delta 對不上 keyframe、parse 非外掛檔 / 呼叫鍵不符 |
| `CONTEXT.md` | M | 新增「引擎回放」「簿重播」「厚檔」條目;「五檔」條收窄「不可回測」到 TC4 歷史 tick |
| `CLAUDE.md` | M | §0a「五檔不可回測」收窄、「歷史 replay」→「歷史引擎回放」;§1 指令表加 `book-replay` 列 |
| `.claude/skills/tc4-market-facts/SKILL.md` | M | 同毫秒群條標註與 09-16 實測衝突(待 #274);新增「REALTIME 個股成交時刻只到整秒、recv_ns 反而很穩」條 |
| `docs/next-time.md` | M | 2026-09-16 節一條:`book-replay` / `ticks-compact` 的 `--date` / `--dir` 參數重複 |
| `.claude/feat/book-replay-engine/{verification.md, code-review-round-1.json, code-review-round-2.json, evidence/*}`(9 檔) | A | 流程 artifact(gate 數字 / AC 對照 / 真環境 CLI 執行紀錄 / 直讀 parquet 驗證腳本與輸出 / 瀏覽器 file:// 解碼頁與截圖 / 兩輪 review 原文與處置) |

## 發現總覽

| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `tests/test_book_replay.py:381` 外掛檔 v1 的線上格式沒有任何一條字面 golden 測試:編碼測試只有 `decode(encode(day)) == day`、`book_at` 對 frames、外殼 head/tail/gzip/base64;payload 各鍵語意(`kind` 的 t/b、`seq` / `recv` 差值、`clock` 攤平、`trade` 四格順序、`d` 攤平)從未與寫死的字面比。`_KIND_CODE` 對調 t/b(`_KIND_NAME` 跟著反推)27 條全綠;CLI 落檔前的自檢用同一份 `decode`,同步漂移也抓不到;repo 外依模組說明寫的 JS 讀者(evidence 解碼頁寫死 `kind === "t"`、`trade[k*4+1]` 為價)會靜默讀錯永久檔 | MEDIUM | PARTIAL(MED→MED:M1 實跑 27 passed、encode 的 kind 由 `tbbtbbbt` 變 `bttbtttb` 屬實;reviewer 另稱的 M7「`_TRADE_CELLS` 反序全綠」**不成立** —— decode 以位置參數 `Trade(*next(trades))` 建物件,只反序格序會紅 2 條,只有 decode 也改成依欄名 zip 的對稱寫法才全綠;4.3b lone:他軸 N-A,不降級) | Should Fix | `auto-fix` | 在議定 seam 上加一條字面 golden 測試(小 fixture、`keyframe_every=2`、成交價量內外盤取不同值),不動格式、不動實作 |
| F-02 | `tests/test_book_replay.py:376` round-trip 與跳轉用的 `_lock_limit_up_rows` 第 0 則就是成交、三筆成交全是時鐘點,所以 decode 的兩條特例 —— 首筆成交前(`clock_ms=None, after=i+1`)與成交則號不在 `clock` 裡(時刻異常)—— 從沒走過 round-trip;decode 的 `clock_index = -1` 改成 `0` 27 條全綠 | LOW | CONFIRMED(LOW→LOW:M8 實跑 27 passed;健全性檢查:簿則→成交兩則時引擎得 `[(None,1),(32400000,0)]`、M8 下 decode 得 `[(None,0),…]` 不相等;TestClock 只呼叫 `replay_books` 不走 decode;真資料上 CLI 全等自檢會大聲失敗,所以是回歸保護缺口不是出貨風險) | Nice to Have | `auto-fix` | fixture 開頭補簿列 → 1815 型未來時刻成交,中段補一筆蓋章倒退成交,或直接沿用 F-01 的 golden fixture 再做 round-trip |
| F-03 | `tests/test_book_replay.py:431` `_check_header` 的時鐘點檢查含四個條件(則號遞增、則號 < n、落在成交則、毫秒不減),竄改表只有「落在簿則」一條;拿掉 `ms < prev_ms`、拿掉 `prev_index <`、拿掉 `< n` 各自 27 條全綠,後者越界時拋 `IndexError` 而非 `PluginFormatError` | LOW | CONFIRMED(LOW→LOW:M4 / M5 / M10 各跑一次皆 27 passed;M4 下毫秒倒退檔被接受、M5 下則號不遞增被接受、M10 下 `IndexError: string index out of range`;只影響竄改 / 損壞檔的拒收品質) | Nice to Have | `auto-fix` | 竄改表補三案:則號倒序、則號 = n、同序但後一點毫秒 −1,皆 match「時鐘點」 |
| F-04 | `tests/test_book_replay.py:247` `CLOCK_FUTURE_TOLERANCE_MS` 的界沒釘:現有案只有晚 2.5 s 接受、晚約 7 小時拒絕;容差改成 3_000、`<=` 改 `<` 都 27 條全綠。容差被收窄到秒級時,本機鐘偏(#236 實測秒級)的日子整天成交不當時鐘點、文字標籤退回「首筆成交前第 N 則」,測試不紅 | LOW | CONFIRMED(LOW→LOW:M2 實跑 27 passed、晚 3.5 s 的成交由 `(36004000,0)` 變 `(None,1)`;M3 實跑 27 passed、晚恰 60.000 s 由 `(36060500,0)` 變 `(None,1)`;只影響文字標籤,不影響五檔 / 時間軸 / 檔案完整性;repo 慣例會釘界值,例 CDP 列閘「恰 5.00% 落閉區間下界」) | Nice to Have | `auto-fix` | 補兩個界值案:達錢時刻 = 收到時刻 + 60.000 s 當時鐘點、+ 60.001 s 不當,並斷言 `anomalous_trades` 0 / 1 |
| F-05 | `tests/test_book_replay.py:404` `plugin_js` 的 gzip `mtime=0`(docstring 與 CLAUDE §1「同資料重跑逐位元組相同」的依據)沒有測試:程式碼那處改成 `mtime=12345` 27 條全綠;同一行三個條件串成一條 `and` 斷言,失敗時看不出哪段錯 | LOW | CONFIRMED(LOW→LOW:M6 實跑 27 passed、gzip header bytes[4:8] 由 `00 00 00 00` 變 `39 30 00 00`;reviewer 另註只替換第一處 `mtime=0` 會打到 docstring、已改打程式碼那處重跑;只影響決定性承諾,不影響資料正確性) | Nice to Have | `auto-fix` | 補 `base64.b64decode(blob)[4:8] == b"\x00\x00\x00\x00"`;三個條件拆成三條 assert(不拿整個 blob 當字面,zlib 版本會變) |
| F-06 | `copycat/cli.py:430` `_book_replay` 的 `except OSError` 只包 mkdir 與寫檔,`load_day` / `replay_books` 在 try 外:讀 parquet 權限 / 磁碟錯直接 traceback(旁邊 `ticks-compact` 依 pr-263 F-03 印一行人話);`out_dir.mkdir` 排在約 30 s / 5.7 GB 的整天讀取之後,`--out` 不可寫要讀完才失敗 | LOW | CONFIRMED(LOW→LOW:`cli.py:431` 在 try 之外逐字;實跑假 `20260916.parquet` + `-book.parquet` → `pyarrow.lib.ArrowInvalid` 完整 traceback、exit 1、輸出目錄未建;**補充**:壞 parquet 拋的 `ArrowInvalid` 是 `ValueError` 不是 `OSError`,照搬 ticks-compact 的 `except OSError` 也接不到,只有權限 / 磁碟類會接到;exit code 仍符合 CLAUDE §1「IO exit 1」) | Nice to Have | `auto-fix` | 前置檢查通過後先 `mkdir`,把 `load_day` / `replay_books` 移進同一個 `except OSError` 範圍;壞 parquet 的 `ValueError` 維持大聲失敗(不懂的錯不 catch) |
| F-07 | `copycat/book_replay.py:251` 時鐘點的毫秒寫進 `clock`,同一則成交的 `row.ms` 又寫進 `trade` 第一格 —— 永久格式 v1 裡同一事實存兩份,`_check_header` 不比對;`clock[1]` 減 1000 後 `decode` 照收、結果不等於原始。回看頁做文字標籤時得挑一個來源讀,兩份可分岔;09-16 約 37.5 萬筆成交只有 1 筆不是時鐘點,等於多存約 37.5 萬個整數 | LOW | CONFIRMED(LOW→LOW:`_frames` 設 `clock = row.ms`、`Trade.ms = row.ms` 逐字,encoder 保證兩份相等;竄改實跑 `frame0.clock_ms=39759000` 而 `trade.ms=39760000`、`equal_to_original=False`;只有手改或損壞檔才分岔;趁 #268 JS 讀者還沒上線改成本最低) | Nice to Have | `ask-user` | 二選一是 v1 永久格式的決定:(a) `clock` 只存則號(或只存「不是時鐘點的成交則號」)、標籤毫秒一律讀 `trade`;(b) 保留現格式、`_check_header` 加一致性檢查並寫明相等 |
| F-08 | `copycat/book_replay.py:317` `decode` / `PluginFormatError` docstring、測試 docstring、commit subject「補成真的」與 `code-review-round-2.json` 處置都宣稱「檔頭與內容不符一律拒絕」,實跑仍有缺口:`kf_every=0` → `ZeroDivisionError`;delta 奇數長度或欄號 ≥ 20 → `IndexError`;最後一個 keyframe 之後的 delta 用負欄號默默寫進 askq4 被接受;`seq` 差值 ≤ 0 被接受;內外盤填非文件值被接受;`book_at(payload, n)` 回第 n−1 則、`book_at(payload, -1)` 回最後一個 keyframe 而非最後一則 | LOW | CONFIRMED(LOW→LOW:逐項實跑 —— `kf_every=0` ZeroDivisionError、奇數長度 / 欄號 20 IndexError、第 7 則加 `[-1,555]` 被接受且 askq4=555、seq 差值 0 / −5 被接受、內外盤 `'weird'` / `7` 被接受、`book_at(8)` 等於 frames[7]、`book_at(-1)` 等於最後 keyframe;CLI 只解自己剛產的檔且有全等自檢,不影響已出貨外掛檔;問題在說法過頭 + `book_at` 作為 JS 移植參考時越界回錯值) | Nice to Have | `auto-fix` | `_check_header` 驗 `kf_every` ≥ 1(`encode` 同步)、decode 迴圈驗 delta 偶數長度 / 0 ≤ 欄號 < 20 / seq 差值 > 0 / 內外盤值域,`book_at` 對 index 不在 [0, n) 拋 `IndexError`;補對應竄改案 |
| F-09 | `CONTEXT.md:249`「簿重播」條寫「達錢時刻比收到時刻還晚的不算」,但引擎容許晚 ≤ 60 s(測試明確斷言晚 2.5 s 照當時鐘點),0–60 s 這段兩邊相反;「早於目前時鐘的不算」完全沒寫;「晚 81–1,137 ms」沒寫明是排除離群後的一般盤中成交。glossary 是術語權威,照字面實作「時刻可信」判定會在本機鐘落後時把真成交判成異常 | LOW | CONFIRMED(LOW→LOW:`CONTEXT.md:248–249` 逐字對 `book_replay.py` 容差與不倒退條件;全分布由 main session 以 pyarrow 讀 `data/ticks/20260916.parquet` 的 `recv_ns` / `ms` 兩欄、逐列算 `(recv_ns//1e6 + 8h) mod 1 日 − ms` 實算:n=375,387、min −25,117,270 ms、max 118,594 ms、p50 614、p99 1,114、> 1,137 ms 390 筆、> 5 s 57 筆、< 0 1 筆(同軸 code-reviewer 另算數字一致);純文件,目前無依 glossary 另寫的實作) | Nice to Have | `auto-fix` | 改成「達錢時刻晚於收到時刻超過 60 秒、或早於目前標籤時刻的成交不算」;統計補「一般盤中成交;收盤撮合晚 5–40 s、7772 緩撮晚 118 s、開機收到前一日成交屬例外」 |
| F-10 | `.claude/skills/tc4-market-facts/SKILL.md:110` 把 recv − 達錢時刻寫成「最小 81 ms、p50 614 / p90 1,023 / p99 1,113」,漏掉三種離群實錄(1815 約 −7 小時、收盤撮合晚 5–40 s、7772 緩撮晚 118 s,只寫在 `book_replay.py` 模組說明);該條 Trigger 含「評估 recv_ns 的精度」,讀者照統計設緊容差會把收盤撮合與緩撮成交判成異常 | LOW | CONFIRMED(LOW→LOW:同 F-09 的 pyarrow 全分布實算 —— p50 614 / p99 1,114 與 skill 所記對得上,但 min −25,117,270 ms(1815)、max 118,594 ms(7772)、> 1,137 ms 390 筆;main session 以 `git show 2aed3b92:.claude/skills/tc4-market-facts/SKILL.md` 取 PR head 全文、Python `re.findall` 逐字查「1815 / 收盤撮合 / 晚到 / 開機收到 / 13:30:00 / 7772」,六個關鍵字各 0 命中;無 runtime 影響) | Nice to Have | `auto-fix` | 同一條補三種離群實錄與「統計排除了這約 80 筆」 |
| F-11 | `.claude/feat/book-replay-engine/evidence/verify_against_parquet.py:60` 直讀 parquet 驗證腳本:(a) 比了 msg_seq / 種類 / 五檔 / 收到時刻 / 成交欄,沒比 `clock_ms` / `after` / `anomalous_trades`;(c) 印出的「成交 X 之後第 N 則」取自 payload 自身的 `clock`,不是獨立驗證;母體 = 目錄內 `*.js`,沒斷言 parquet 代號集合 = 檔案集合(少產一檔 (a) 照過);`:95` 的 `next()` 沒給 default,前綴關係時拋 `StopIteration`;`verification.md:57` 的空簿計數不在 `.out.txt` | LOW | CONFIRMED(LOW→LOW:`:83–92` 的 got 欄位、`:122–123` 標籤來源、`:60` glob 母體、`:95` 無 default 逐字;空簿計數 grep 只命中 verification.md 本身;一次性證據腳本不出貨,檔案集合另有 CLI 摘要 80 檔側證,StopIteration 仍是大聲失敗) | Nice to Have | `auto-fix` | truth 側依模組說明獨立重算時鐘點並比 `(clock_ms, after)`、斷言 parquet distinct code = `{f.stem}`、`next(..., None)`、把空簿計數印進輸出 |
| F-12 | `CLAUDE.md:543` §4「tick 存檔」契約的讀者清單只有 `load_day` / `to_stock_tick` / 研究目錄,沒列簿重播:`book-replay` CLI(`cli.py:419` / `:425`)同樣吃「成交 parquet 存在 = 已轉檔」這個三處讀者同一判準;外掛檔 v1 的 `fields` 取自 `TickRow` 欄序 | LOW | PARTIAL(LOW→LOW:讀者清單缺口屬實;reviewer 所稱的靜默後果**大多不成立** —— 改五檔欄序的記憶體突變(價量交錯)→ 測試 3 failed(`_tuple` 依文件欄序獨立排);新增 kind → `encode` 的 `_KIND_CODE[frame.kind]` 拋 KeyError 大聲失敗;Python decode 只用在 CLI 自檢剛產的檔,沒有讀永久舊檔的讀者) | Nice to Have | `auto-fix` | §4 該條讀者清單補一行 `copycat/book_replay.py` + `book-replay` CLI(沿用轉檔判準;外掛檔 `fields` 取自 TickRow 欄序,改欄序 = 改外掛檔格式要 +1 版本) |
| F-13 | `.claude/feat/book-replay-engine/verification.md:54` 等產出物引用的 commit hash(`08f3beb8`、`828c0c29`、`955aa83b`、`f86676a1`、`aa4b2b20` 等)是 rebase 前的 PR head SHA,rebase merge 後在 master 上查不到,`git show` 證據指令無法照抄重現 | LOW | REFUTED(LOW→LOW:事實成立,但屬 repo 長期系統性流程 —— artifact 在 rebase merge 前 commit,必然引用 rebase 前 hash。main session 實跑 `git merge-base --is-ancestor <sha> origin/master`(exit 0 = 在 master、1 = 不在)逐一驗 12 個 hash 皆 exit 1:本 PR 的 `08f3beb8` / `828c0c29` / `955aa83b` / `f86676a1` / `aa4b2b20`,以及 master 上既有 `.claude/feat/tick-persist/verification.md` 引用的 `05441e4e` / `8380cc21` / `d8cce448`、`.claude/mod/stock-side-flag/verification.md` 引用的 `9df04481` / `b1c3fd13` / `c415d1d4` / `d19b4b3d`(`git show origin/master:<path>` 各命中 1–2 次)—— 同模式早已存在;要改屬 merge 策略 / closeout 流程議題,非本 PR 缺陷) | 參考用 | `no-op` | 不是本 PR 缺陷;若要處理,另開流程議題(closeout rebase merge 後回填 master SHA 或改引 commit 標題) |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: c3134cb594374a0f3e52 action=auto-fix
F-02 finding_uid: 6c2c41ec528991c3bc91 action=auto-fix
F-03 finding_uid: 804c0e84f0d44f3c4b33 action=auto-fix
F-04 finding_uid: 10def3c82e13ee4a1f48 action=auto-fix
F-05 finding_uid: 448b301fa95257867d9f action=auto-fix
F-06 finding_uid: 38f6b9d9bccbf57b60ef action=auto-fix
F-07 finding_uid: 6939bcec16dc52e550f6 action=ask-user
F-08 finding_uid: 5cad4ad4426c0e81161e action=auto-fix
F-09 finding_uid: 796cac8e0e671ea4cd39 action=auto-fix
F-10 finding_uid: 579d285441fd1f1c7412 action=auto-fix
F-11 finding_uid: 85e7e033898a7dfbf953 action=auto-fix
F-12 finding_uid: 62b84a9d3d98647b3ba8 action=auto-fix
F-13 finding_uid: 5615bd03c844266754be action=no-op

### Inline Comments per Finding（直接複製貼到 PR review）

#### #1 外掛檔格式沒有字面測試,把 t / b 對調 27 條照樣全綠

**File**: `tests/test_book_replay.py`
**Line**: 381

**Comment**:
```
這邊的編碼測試都是對稱的:decode(encode(day)) == day、book_at 對 frames、外殼格式。
payload 每個鍵長什麼樣(kind 用 t/b、seq 跟 recv 存差值、clock 攤平、trade 四格順序、d 攤平)
沒有一條拿寫死的字面比。實測把 _KIND_CODE 的 t/b 對調,27 條全綠,
CLI 落檔前的自檢用的也是同一份 decode → 一樣抓不到。
外掛檔要永久保留,回看頁的 JS 是照模組說明寫死 kind === "t"、trade[k*4+1] 當價在讀,
兩邊一起漂的時候會靜默讀錯,FORMAT_VERSION 也不會跟著 +1。

建議補一條 golden:3–4 則的小 fixture(開頭一則簿列、中間一筆 1815 那種未來時刻的成交,
keyframe_every=2,成交的價 / 張 / 內外盤取彼此不同的值),斷言 encode(day) 整個 dict
等於寫死的字面(v / fields / seq / kind / recv / clock / trade / kf / d 全部)。
```

#### #2 round-trip 的 fixture 第一則就是成交,「首筆成交前」跟「時刻異常成交」兩條路沒被解碼驗過

**File**: `tests/test_book_replay.py`
**Line**: 376

**Comment**:
```
_lock_limit_up_rows 第 0 則就是成交而且是時鐘點,三筆成交也全是時鐘點,
所以 decode 的兩條特例(clock_ms=None 那段、成交則號不在 clock 裡)round-trip 從沒走過。
實測把 decode 的 clock_index = -1 改成 0,27 條全綠。
真資料上 CLI 自檢會喊出來,但自動化這層沒有保護。

fixture 開頭補「簿列 → 1815 那種未來時刻的成交」,中段補一筆蓋章早於目前時鐘的成交就能蓋到;
或直接沿用 #1 的 golden fixture 再做一次 round-trip。
```

#### #3 時鐘點的檔頭檢查有四個條件,只有「落在簿則」有竄改測試

**File**: `tests/test_book_replay.py`
**Line**: 431

**Comment**:
```
_check_header 的時鐘點那段要擋四件事:則號要遞增、則號要 < n、要落在成交則、毫秒不能倒退。
竄改表只有「落在簿則」這一條。實測分別拿掉 ms < prev_ms、prev_index <、< n,都是 27 條全綠,
拿掉 < n 的時候越界還會變成 IndexError 而不是 PluginFormatError。

parametrize 再補三個 case 就好:則號倒序([3, ms3, 0, ms0, …])、則號 = n、
同序但後一點毫秒 −1,都 match「時鐘點」。
```

#### #4 60 秒容差的界沒釘住,改成 3 秒或把 <= 改成 < 都照樣全綠

**File**: `tests/test_book_replay.py`
**Line**: 247

**Comment**:
```
現在只有兩端:晚 2.5 秒要當時鐘點、晚 7 小時不當。
實測容差改成 3_000 → 27 條全綠(晚 3.5 秒的成交就不當時鐘點了);<= 改成 < → 一樣全綠。
本機鐘偏個幾秒(#236 量過秒級)的那天,容差要是被誰收窄,整天的標籤都會退回
「首筆成交前第 N 則」,測試不會紅。

補兩個界值 case:達錢時刻 = 收到時刻 + 60.000 s 要當時鐘點、+ 60.001 s 不當,
順手斷言 anomalous_trades 分別是 0 / 1。
```

#### #5 「重跑逐位元組相同」靠的 mtime=0 沒有測試

**File**: `tests/test_book_replay.py`
**Line**: 404

**Comment**:
```
plugin_js 的 docstring 跟 CLAUDE §1 都說同一份資料重產會逐位元組相同,靠的是 gzip mtime=0。
實測把程式碼那處改成 mtime=12345,27 條全綠(gzip header 的 MTIME 變 39 30 00 00)。
同一秒呼叫兩次比對也抓不到,mtime 精度是秒。

補一行:
assert base64.b64decode(blob)[4:8] == b"\x00\x00\x00\x00"
另外這行三個條件串成一條 and,紅的時候看不出是哪段錯,拆成三條 assert 比較好讀。
(不建議拿整個 blob 當字面,zlib 版本不同壓縮結果會變。)
```

#### #6 讀整天那段在 try 外面,IO 錯會噴 traceback,--out 不可寫也要等讀完才失敗

**File**: `copycat/cli.py`
**Line**: 430-432

**Comment**:
```
except OSError 只包到 mkdir 跟寫檔,load_day / replay_books 在 try 前面,
讀 parquet 遇到權限或磁碟錯會直接噴 traceback;旁邊的 ticks-compact 是印一行人話(pr-263 F-03)。
另外 out_dir.mkdir 排在整天讀取(約 30 秒、5.7 GB)之後,--out 指到不能寫的地方要讀完才知道。

前置檢查過了之後先 mkdir,再把 load_day(...) 跟 replay_books(...) 移進同一個 try。
注意壞掉的 parquet 丟的是 pyarrow.lib.ArrowInvalid(是 ValueError 不是 OSError),
except OSError 接不到它 —— 那個維持大聲失敗就好,不要為了它加寬 except。
```

#### #7 clock 的毫秒跟 trade 的成交時刻是同一個值存兩份,decode 不比對

**File**: `copycat/book_replay.py`
**Line**: 251-253

**Comment**:
```
時鐘點的毫秒是 row.ms,同一則成交的 Trade.ms 也是 row.ms,所以 clock 裡的毫秒
一定等於該則 trade 的第一格 —— 永久格式裡同一件事存了兩份,_check_header 沒比。
實測把 clock[1] 減 1000,decode 照收、解出來跟原本不一樣。
回看頁做文字標籤時得挑一個來源讀,兩份就有機會分岔;09-16 約 37.5 萬筆成交只有 1 筆
不是時鐘點,等於多存了約 37.5 萬個整數。

JS 讀者還沒上線,現在改最便宜,二選一:
(a) clock 只存則號(或反過來只存「不是時鐘點的成交則號」),標籤毫秒一律讀 trade;
(b) 格式不動,_check_header 加「時鐘點毫秒 == 該成交則時刻」,格式說明寫明兩者相等。
```

#### #8 「檔頭不符一律拒絕」還沒補齊,book_at 越界也會回錯的簿

**File**: `copycat/book_replay.py`
**Line**: 317-318

**Comment**:
```
docstring、commit subject 跟 round-2 處置都寫「一律拒絕 / 補成真的」,實跑還有這些漏網:
- kf_every=0 → ZeroDivisionError(encode(keyframe_every=0) 也是)
- delta 長度奇數、欄號 ≥ 20 → IndexError
- 最後一個 keyframe 之後的 delta 用負欄號(例 [-1, 555])→ 默默寫進 askq4,照收
- seq 差值 ≤ 0、內外盤填文件以外的值 → 照收
- book_at(payload, n) 回第 n-1 則;book_at(payload, -1) 回的是最後一個 keyframe 不是最後一則

CLI 只解自己剛產的檔又有全等自檢,已出貨的檔不受影響;但 book_at 是給 JS 移植照抄的規則,
越界不報錯容易帶歪。_check_header 驗 kf_every ≥ 1、迴圈驗 delta 偶數長度 / 0 ≤ 欄號 < 20 /
seq 差值 > 0 / 內外盤值域,book_at 對 index 不在 [0, n) 拋 IndexError,各補一個竄改案。
```

#### #9 glossary 寫的標籤規則跟引擎相反:晚到 60 秒內的成交其實照算

**File**: `CONTEXT.md`
**Line**: 249

**Comment**:
```
這句「達錢時刻比收到時刻還晚的不算」跟實作對不上:引擎容許晚 60 秒內
(test_a_few_seconds_of_local_clock_lag_is_not_an_anomaly 明確斷言晚 2.5 秒照當時鐘點);
另一條「早於目前時鐘的不算」完全沒寫。
「晚 81–1,137 ms」也沒講是排除離群後的數字 —— 09-16 全分布最小 −25,117,270 ms(1815)、
最大 118,594 ms(7772),超過 1,137 ms 的有 390 筆。

glossary 是術語權威,照字面實作「時刻可信」會在本機鐘慢的時候把真成交當異常。改成:
「達錢時刻晚於收到時刻超過 60 秒、或早於目前標籤時刻的成交不算」,
統計補一句「一般盤中成交;收盤撮合晚 5–40 s、緩撮晚 118 s、開機收到前一日成交屬例外」。
```

#### #10 skill 的 recv 統計沒寫離群,讀者照數字設容差會把收盤撮合當異常

**File**: `.claude/skills/tc4-market-facts/SKILL.md`
**Line**: 110

**Comment**:
```
這條寫「最小 81 ms、p50 614 / p90 1,023 / p99 1,113」,但同一天就有三種離群:
1815 開機收到前一日成交(約 −7 小時)、13:30 收盤撮合晚 5–40 秒、7772 緩撮晚 118 秒,
這些只寫在 book_replay.py 的模組說明,skill 裡 grep 不到。
這條的 Trigger 寫著「評估 recv_ns 的精度」,照數字設緊容差就會踩到。

同一條補上三種離群實錄,並註明「統計排除了這約 80 筆」。
```

#### #11 parquet 驗證腳本沒驗文字標籤,也沒確認一檔都沒少

**File**: `.claude/feat/book-replay-engine/evidence/verify_against_parquet.py`
**Line**: 60

**Comment**:
```
真值那側確實沒經過引擎,但:
- (a) 比了 msg_seq / 種類 / 五檔 / 收到時刻 / 成交欄,沒比 clock_ms / after / anomalous_trades
- (c) 印出的「成交 X 之後第 N 則」直接拿 payload 自己的 clock,等於自己印自己
- 母體是目錄裡有的 *.js,沒斷言 parquet 的代號集合 = 檔案集合,少產一檔 (a) 照過
- :95 的 next() 沒給 default,兩邊是前綴關係時會丟 StopIteration 而不是印出差異
- verification.md:57 的空簿計數不在 .out.txt 裡

truth 側照模組說明重算時鐘點比 (clock_ms, after)、斷言 distinct code == {f.stem}、
next(..., None)、空簿計數也印進輸出。
```

#### #12 CLAUDE §4 的 tick 存檔契約沒把簿重播列成讀者

**File**: `CLAUDE.md`
**Line**: 543

**Comment**:
```
讀者清單只有 load_day / to_stock_tick / 研究目錄,但 book-replay CLI(cli.py:419 / :425)
也吃「成交 parquet 存在 = 已轉檔」這個三處同一判準,外掛檔 v1 的 fields 也直接取自 TickRow 欄序。
(真改欄序的話測試會先紅、新增 kind 會 KeyError 大聲失敗,所以不是靜默壞,是契約文件缺一行。)

這條讀者清單補一行:copycat/book_replay.py + book-replay CLI —— 沿用轉檔判準;
外掛檔 fields 取自 TickRow 欄序,改欄序 = 改外掛檔格式,FORMAT_VERSION 要 +1。
```

#### #13 引用的 commit hash 是 rebase 前的 —— 不是本 PR 缺陷,屬流程議題

**File**: `.claude/feat/book-replay-engine/verification.md`
**Line**: 54

**Comment**:
```
不是本 PR 缺陷。這些 hash(08f3beb8、828c0c29 …)是 rebase merge 前的 PR head SHA,
master 上查不到,git show 照抄會失敗 —— 但 artifact 在 merge 前 commit 就必然如此,
tick-persist、stock-side-flag 的 verification.md 也都一樣。
要處理的話是 closeout 流程(rebase merge 後回填 master SHA 或改引 commit 標題),另開議題。
```

## CC 主軸原始 findings(first-pass, context-aware)

python-reviewer ×3 chunk 原文摘要(完整原文依 chunk 保存於本 session;合併規則:A-5 與 B-3 同根因併為 F-08)。

#### A-1 [LOW] CONTEXT.md:249-250 — 「簿重播」標籤規則與引擎 / 測試相反、「81–1,137 ms」未標母體 → F-09
#### A-2 [LOW] .claude/skills/tc4-market-facts/SKILL.md:110-111 — recv − 達錢時刻統計漏三種離群實錄 → F-10
#### A-3 [LOW] .claude/feat/book-replay-engine/verification.md:54 — 產出物引用 rebase 前 hash、master 查不到 → F-13
#### A-4 [LOW] .claude/feat/book-replay-engine/evidence/verify_against_parquet.py:60 — 漏驗標籤欄、母體受限已產出檔、next() 無 default、空簿計數不在輸出 → F-11
#### A-5 [LOW] .claude/feat/book-replay-engine/code-review-round-2.json:24 — round-2 處置「讓說法成立」說過頭(奇數 delta / 欄號越界 IndexError、seq −5 接受、末段負欄號接受)→ F-08(併)
#### A-6 [LOW] CLAUDE.md:543 — §4 tick 存檔契約讀者清單沒加簿重播 → F-12
#### B-1 [LOW] copycat/cli.py:430-452 — 讀檔段不在 try、IO 錯 traceback、mkdir 在整天讀取後 → F-06
#### B-2 [LOW] copycat/book_replay.py:251-253 — clock 毫秒與 trade 時刻重複存、decode 不驗一致 → F-07
#### B-3 [LOW] copycat/book_replay.py:305-318,361-395 — decode 竄改檢查缺口(kf_every=0 / 負欄號 / seq 不遞增 / 內外盤值域)+ book_at 無範圍檢查 → F-08
#### C-1 [MEDIUM] tests/test_book_replay.py:376-408 — 外掛檔線上格式無字面測試,round-trip 擋不住同步漂移(M1 / M7)→ F-01
#### C-2 [LOW] tests/test_book_replay.py:315-384 — round-trip fixture 缺首筆成交前與時刻異常成交(M8)→ F-02
#### C-3 [LOW] tests/test_book_replay.py:419-458 — 時鐘點檢查四條件只測一條(M4 / M5 / M10)→ F-03
#### C-4 [LOW] tests/test_book_replay.py:192-256 — 容差界值未釘(M2 / M3)→ F-04
#### C-5 [LOW] tests/test_book_replay.py:396-408 — mtime=0 決定性無測試(M6)→ F-05

逐檔 accounting(三塊聯集 = F):A — code-review-round-1.json(F-13)、code-review-round-2.json(F-13、F-08)、evidence/cli_runs.txt(F-13)、`INTENTIONALLY_SKIPPED: evidence/file_url_decode_2303.png — 二進位截圖`、`REVIEWED_NO_ISSUES: evidence/file_url_decode_check.html`(解碼規則逐條對模組說明正確)、evidence/file_url_decode_results.txt(F-13)、`REVIEWED_NO_ISSUES: evidence/verify_against_parquet.out.txt`(數字與 verification §2 一致)、evidence/verify_against_parquet.py(F-11)、verification.md(F-13、F-11)、SKILL.md(F-10)、CLAUDE.md(F-12)、CONTEXT.md(F-09);B — book_replay.py(F-07、F-08)、cli.py(F-06)、`REVIEWED_NO_ISSUES: docs/next-time.md`;C — tests/test_book_replay.py(F-01–F-05)。

## Codex 原始 findings(first-pass, diff-only)

N-A —— Codex 軸未啟用(user 已停用;沿 #188 / #190 / #199 / #230 / #238 / #253 / #255 / #263 前例)。零 Codex finding。

## Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查(Codex 中性 / 對抗 / Gemini 皆未啟用)。

## Codex 對 Opus 的複查結果(對稱化 4.2)

Codex 軸未啟用 → 本段以**同軸 `code-reviewer` subagent 獨立複查**代替(未參與 first-pass、唯讀、禁外查、strict JSON 13/13 ID 集合完整;**非跨軸證據**,REFUTED 率不可解讀為 first-pass 命中率)。13 條全 non-strict-liability;C4 未派,無 C4 finding。

| Opus # | Opus reviewer | Opus title | Verdict(同軸) | 原始 → 校正 severity | 同軸 evidence | 備註 |
|---|---|---|---|---|---|---|
| C-1 → F-01 | python-reviewer(C) | 格式無字面 golden 測試 | PARTIAL | MED→MED | M1 27 passed、kind `tbbtbbbt`→`bttbtttb`;M7 照字面做 2 failed(decode 位置參數建 Trade)| 4.3b lone:他軸 N-A;M7 論據校正後 M1 仍成立 → 維持 Should |
| C-2 → F-02 | python-reviewer(C) | fixture 缺兩種則 | CONFIRMED | LOW→LOW | M8 27 passed;簿則→成交時 decode 結果不等 | Nice(CLI 真資料自檢會喊) |
| C-3 → F-03 | python-reviewer(C) | 時鐘點檢查只測一條 | CONFIRMED | LOW→LOW | M4 / M5 / M10 各 27 passed;M10 IndexError | Nice |
| C-4 → F-04 | python-reviewer(C) | 容差界值未釘 | CONFIRMED | LOW→LOW | M2 晚 3.5 s 翻 `(None,1)`;M3 恰 60.000 s 翻 `(None,1)` | Nice |
| C-5 → F-05 | python-reviewer(C) | mtime=0 無測試 | CONFIRMED | LOW→LOW | M6 header bytes 39 30 00 00、27 passed | Nice |
| B-1 → F-06 | python-reviewer(B) | CLI 讀檔在 try 外 | CONFIRMED | LOW→LOW | 假 parquet 實跑 ArrowInvalid traceback、exit 1;ArrowInvalid 為 ValueError | Nice;修法只收 OSError |
| B-2 → F-07 | python-reviewer(B) | clock / trade 時刻重複 | CONFIRMED | LOW→LOW | 竄改 clock ms 被接受、結果不等 | Nice;格式決定 → ask-user |
| B-3 + A-5 → F-08 | python-reviewer(B + A) | decode 缺口 / book_at 越界 | CONFIRMED | LOW→LOW | 逐項實跑 7 種漏網 | Nice;說法過頭 |
| A-1 → F-09 | python-reviewer(A) | glossary 標籤規則相反 | CONFIRMED | LOW→LOW | 09-16 parquet 全分布實算 | Nice;相反只在 0–60 s 段 |
| A-2 → F-10 | python-reviewer(A) | skill 統計漏離群 | CONFIRMED | LOW→LOW | 同上實算、grep 零命中 | Nice |
| A-4 → F-11 | python-reviewer(A) | 驗證腳本漏驗 | CONFIRMED | LOW→LOW | 逐行對 got 欄位 / 標籤來源 / 母體 | Nice(一次性腳本) |
| A-6 → F-12 | python-reviewer(A) | §4 讀者清單缺 | PARTIAL | LOW→LOW | 缺口屬實;欄序突變 3 failed、新 kind KeyError | Nice;靜默後果不成立 |
| A-3 → F-13 | python-reviewer(A) | rebase 前 hash | REFUTED | LOW→LOW | 12 個 hash `merge-base --is-ancestor` 皆 exit 1,含 tick-persist / stock-side-flag 既有 verification 同模式 | 參考用;流程議題 |

## Action Items

**校準套用**:無作者校準檔(`loger-w.md` 不存在)、本輪無套用。6c Refactor Intent Gate:本 PR 無「移除 / 削弱既有防護」類 finding,免。6d-1:F-07(「兩份可分岔」需手改 / 損壞檔)、F-12(欄序變動的後果)為假設性情境,皆已在 Nice 以下。6d-3:無 Must Fix —— 本輪沒有任何一條寫得出 user-visible 重現路徑且不修就壞會出貨的東西(外掛檔已由 CLI 全等自檢與直讀 parquet 全量驗證,回看頁尚未讀取 v1)。Provenance cap:N-A(base = master)。未驗證前提已拿掉重估:F-01 拿掉「#268 JS 讀者會照模組說明讀」這個尚未發生的前提後,仍有 repo 內既存的外部讀者(evidence 解碼頁寫死格式)與 M1 全綠的第一手證據 → Should 不變;F-07 拿掉「讀者會挑錯來源」後只剩重複與不驗 → Nice 不變。

### Must Fix（合併前必修）

無。

### Should Fix（強烈建議）

- **F-01** 在議定 seam 上加外掛檔 v1 的字面 golden 測試(MEDIUM,PARTIAL —— M7 論據不成立、M1 成立)。

### Nice to Have（可選優化）

- **F-02** round-trip fixture 補首筆成交前與時刻異常成交。
- **F-03** 時鐘點竄改案補三條(倒序 / 越界 / 毫秒倒退)。
- **F-04** 容差界值 60.000 / 60.001 s 兩案。
- **F-05** gzip MTIME 位元組斷言 + 拆 assert。
- **F-06** CLI 先 mkdir、讀檔進 `except OSError` 範圍(壞 parquet 的 ValueError 維持大聲失敗)。
- **F-07** clock 與 trade 時刻重複:(a) 去重或 (b) 一致性檢查(**ask-user**:v1 永久格式決定,#268 前拍板)。
- **F-08** decode 補齊 kf_every / delta 形狀 / seq 遞增 / 內外盤值域檢查,`book_at` 範圍檢查,各補竄改案。
- **F-09** CONTEXT「簿重播」標籤規則改對 + 統計標母體。
- **F-10** tc4-market-facts 那條補三種離群實錄。
- **F-11** 直讀 parquet 驗證腳本補標籤比對 / 代號集合 / `next` default / 空簿計數。
- **F-12** CLAUDE §4 tick 存檔條讀者清單補簿重播。

### 參考用

- **F-13** rebase 前 hash:repo 長期流程模式(REFUTED as PR-specific);要處理另開 closeout 流程議題。

## 審查工具比較 (qualitative)

- CC 主軸(python-reviewer × 3 chunk,context-aware):13 條中 1 條 Should、11 條 Nice、1 條參考用,零 Must。分佈:測試強度 5 條(F-01–F-05,全部附**記憶體內突變體實跑證據**,chunk C 先跑三個會紅的控制組確認替換手法生效)、格式 / 解碼韌性 3 條(F-06–F-08,chunk B 逐項竄改實跑)、文件與契約 3 條(F-09 / F-10 / F-12)、證據腳本 1 條(F-11)、流程 1 條(F-13)。主路徑(排序 → 時鐘點 → 收到時刻軸 → 編碼 → 自檢 → 落檔)兩個 chunk 各自追過,核心行為零 finding;最有分量的是 F-01 —— 永久格式只被自己的對稱 round-trip 保護。
- Codex 中性 / 對抗、Gemini 軸:N-A(user 已停用),重疊率無法計算;4.1 N-A;4.2 由同軸 code-reviewer 獨立複查代替(CONFIRMED 10 / PARTIAL 2 / REFUTED 1 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0),**非跨軸證據**。同軸複查仍抓到兩處 first-pass 論據過頭(F-01 的 M7、F-12 的靜默後果)與一條屬流程而非本 PR 的 finding(F-13)。
- 對抗式第三軸增益:N-A。
- 與 merge 前兩輪 two-axis review 的關係:round-1 21 條、round-2 15 條已在 PR 內收修;本輪 13 條全為新條,其中 F-08 是 round-2「讓說法成立」收修**沒補完**的部分。

## 沒做的部分（結案對帳）

- Codex 中性軸:N-A(user 已停用)。
- Codex 對抗軸:N-A(user 已停用)。
- Gemini Flash / Pro 軸:N-A(user 已停用;Step 2.96 未問、按前例)。
- Codex preset(Step 2.98):N-A(未問、按前例)。
- Cross-axis verification 4.1:N-A(無非 CC finding);4.2:以同軸 code-reviewer subagent 獨立複查代替 PASS,**非獨立跨軸證據**;4.3a:N-A(單軸無 consensus);4.3b:逐條見複查欄 PASS(他軸沉默不存在,不據以降級)。
- Blast radius(Step 2.9):跑了、空輸出跳過。
- React-doctor(Step 2.97):N-A(非 React PR)。
- Formal spec traceability(Step 2.65):SKIPPED (C4_NO_REPO_SPEC_PATH)。
- Author calibration(Step 2.2):無檔、無套用。
- 逐檔覆蓋:16/16(covered 12 / no-issues 3 / skipped 1 / missed 0)PASS。
- 行號重定位:13/13 exact PASS。
- Codex config mutation / restore(Step 3 / Step 7):N-A(Codex 未執行,未改 `~/.codex/config.toml`)。
- 未驗證前提:F-01 的「#268 回看頁 JS 會照模組說明寫」是尚未發生的未來讀者(已拿掉重估、不影響 Should);F-07「讀者可能挑錯來源」與 F-12「欄序變動後果」為假設情境(皆 Nice);F-06 的 30 s / 5.7 GB 取自 PR 內 verification 實測,非本輪重量。同軸複查原稱「`.claude/bug/sparse-review-followups/verification.md:34` 等早有 `git show <hash>` 前例」,main session 以 `git cat-file -e origin/master:<path>` 查該三個路徑皆不存在、無法證實 → 已自 F-13 證據刪除,F-13 的 REFUTED 改由上述 12 個 hash 實跑結果支撐。
- 失敗軸 / 工具失敗:無。
- Self-Verify(Step 6):`skill-verify-auditor`(description 含 `skill-verify:pr-review`;requested=opus / observed=UNAVAILABLE;唯讀,輸入 = 本草稿全文 —— 以 Read 讀草稿檔而非 prompt 內嵌,內容同一份、未讀其他產物,沿 #263 前例)對第一版草稿判 `VERDICT: VIOLATIONS: R4, R6`,R1–R3 / R5 / R7–R10 PASS;輸出格式驗過(R1–R10 各一行、順序正確、FAIL 集合與 verdict 一致)。R4 缺口 = C4 段未寫 reducer 安全投影要求 → 已於「Spec 依據」補寫本輪 `human_projection` 為空、零 invalidated 語意。R6 缺口 = F-13 的「不在 master」與 F-10 的「grep 零命中」未附查詢指令與工具 → main session 補跑 `git merge-base --is-ancestor`(12 個 hash)、`git show` + `re.findall`(6 個關鍵字)、pyarrow 全分布實算,結果與原述一致後寫回 F-09 / F-10 / F-13,並刪除一句無法證實的前例。修正後**未重派 auditor、未經第二次獨立稽查**。
