# PR #279 Code Review 比較報告 · SHA a6b10002
**Report projection schema**: 1

**PR**: [loger-w/copycat#279](https://github.com/loger-w/copycat/pull/279)
**標題**: feat(book-replay): 簿重播變動分解 + 重新可見 + 成交明細吃檔欄(#269)
**作者**: loger-w
**分支**: `feat/book-replay-changes` → `master`
**變更**: 54 檔案, +7520 / -22(其中 49 檔為 `.claude/feat/book-replay-changes/**` 流程 artifact,含 repo 外回看頁模板副本與驗證腳本;實質 code 1 檔 +688 / -15、測試 1 檔 +1050 / -4、文件 3 檔 + skill 1 檔)
**審查日期**: 2026-09-17
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以收修 PR 處置,不阻擋出貨;master 上 rebase 後最後一筆為 `24d3a97e`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `a6b100020d328de7bc1948f1aa96c1ba043e4111`;destination repo id `R_kgDOTsITBg` + baseRefOid `71c9f077737de42c86eb784d9a95cca3f2875529`;`input_binding: verified`(`git fetch origin refs/pull/279/head` 後 `git rev-parse FETCH_HEAD` = headRefOid;review worktree detached 於該 SHA、`git rev-parse HEAD` 相同;baseRefOid commit 存在,所有 diff 以兩個 full SHA 直接指定、不經移動中的 branch ref)
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 13 筆 SHA;分支已刪,`refs/pull/279/head` 仍指 `a6b10002`,產報告前重抓 headRefOid / baseRefOid 不變);`base_changed=true`(origin/master 前進到 `3024887a` = rebase merge 結果 `24d3a97e` + 一筆只動 `graphify-out/**` 的 graphify commit);`review_context_changed=false`(`git diff --stat a6b10002 24d3a97e` 為空、`git diff --stat 24d3a97e origin/master -- . ':!graphify-out'` 為空)
**審查工具**: CC (Opus 5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A**(user 已停用,沿 #190 起前例單軸;本機 `command -v codex agy sem` 亦三者皆無)+ Codex 對抗式 **N-A** + Cross-axis verification(4.1 N-A 無非 CC finding;4.2 以同軸 `code-reviewer` subagent 獨立複查代替,**非跨軸證據**;main session 另以合成樣本與正式外掛檔獨立重現 F-01)+ Gemini 軸 **N-A**(user 已停用)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-opus-5;primary reviewer=python-reviewer ×5 chunk(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .py 佔 source diff 71%(2,983 / 4,212 行);dispatch A 49 tool uses / 716 s、B 43 / 785 s、C 38 / 725 s、D 50 / 1,747 s、E 22 / 622 s);同軸複查=code-reviewer(requested=opus / observed=UNAVAILABLE;64 tool uses / 1,881 s);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派,gate SKIPPED);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=54 → covered 20 / no-issues 24 / skipped 10 / **missed 0**(chunked: 是 —— source 24 檔 > 15 且 diff 7,542 行 > 800;路徑排序後依 source 行數約 800 依序填塊:A 15 檔(source 11 檔 775 行)、B 29 檔(source 9 檔 846 行,單塊略超)、C 7 檔(模板副本 834 行 + 文件)、D 2 檔(book_replay.py 703 行 + next-time)、E 1 檔(test_book_replay.py 1,054 行);聯集 = F,零 repair 輪)
**定位 (ENH-B)**: anchored exact 32 / ambiguous 1 / **FAILED 0**(去重後 34 條、37 個 pin:33 個逐字 anchor 對 PR head 重定位,32 個唯一比中、F-03 的 `for change in changes:` 兩處(787 / 1027)取自報行 1027;另 4 個 pin(F-04b、F-08、F-09、F-11)reviewer 標 `<none>`,以最近符號行定位;行號自 reviewer 自報校正 2 處:F-19 32→34、F-22 58→62)
**React-doctor (2.97)**: N-A(非 React PR;F 無 .jsx / .tsx)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_REPO_SPEC_PATH)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 review worktree 對 baseRefOid 執行、exit 0、零輸出;sem 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer ×5 chunk)PASS(37 raw findings → 去重 34;54/54 accounting;reviewer 附實跑證據:A 在切換備份模板重套 patch 驗逐位元組相同、修前 commit 重跑不變式、分桶探針;B 以 seed 重現 594 則抽樣、node / Python 逐值比 toFixed;C 重跑 lock_flag_check、WCAG 實算;D 以正式外掛檔還原 TickRow 重跑引擎、量測修法前後差異;E 22 個突變體(scratch 副本、worktree 未動)+ 合成樣本證明非等價)/ Codex 中性 N-A / Codex 對抗 N-A / Gemini Flash N-A / Gemini Pro N-A / cross-axis verification:4.1 N-A、4.2 以同軸 code-reviewer 獨立複查代替 PASS(34/34 verdict、ID 集合完整;CONFIRMED 25 / PARTIAL 8 / OUT_OF_SCOPE 1 / REFUTED 0)/ 4.3a N-A(單軸無 consensus)/ 4.3b 逐條見複查欄與備註
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-279`
**worktree HEAD**: `a6b100020d328de7bc1948f1aa96c1ba043e4111`

**Report generation**: sha256:b9f710af15f32c0518bb3b3a5a781296be3531eec639aa66a5dd2404438db62e

---
## [完整證據副檔](pr-279-review.audit.md)
### finding_uid 索引
[8acd905c7a7a2fc60282](pr-279-review.audit.md#發現總覽) · [25e141d6cfec15932949](pr-279-review.audit.md#發現總覽) · [c898c8d6896acb90a5c7](pr-279-review.audit.md#發現總覽) · [3b9d14179fd4b010110a](pr-279-review.audit.md#發現總覽) · [00e6e0bacb9485372de2](pr-279-review.audit.md#發現總覽) · [179d5eb8b7a2c0777d45](pr-279-review.audit.md#發現總覽) · [549f032774ec0813f786](pr-279-review.audit.md#發現總覽) · [b219f6c190fb48b2a70f](pr-279-review.audit.md#發現總覽) · [3edf65f1ab2c0e700792](pr-279-review.audit.md#發現總覽) · [4ad438347a3b2f520f58](pr-279-review.audit.md#發現總覽) · [d42ffda958d759e27189](pr-279-review.audit.md#發現總覽) · [69dc79f4ece6e9187b8e](pr-279-review.audit.md#發現總覽) · [909fea75525e3af2710f](pr-279-review.audit.md#發現總覽) · [469507938e87b419b3a1](pr-279-review.audit.md#發現總覽) · [4b91ac8cb96129f02885](pr-279-review.audit.md#發現總覽) · [ac72fdc1c142cc2ad7d2](pr-279-review.audit.md#發現總覽) · [4f97f85258a2f3bb993e](pr-279-review.audit.md#發現總覽) · [31533f261d96901b80a5](pr-279-review.audit.md#發現總覽) · [1b94d683ed849b1d0e0b](pr-279-review.audit.md#發現總覽) · [285d76158740937d9f73](pr-279-review.audit.md#發現總覽) · [a007bed1c382b1597471](pr-279-review.audit.md#發現總覽) · [1c82284c59f7d0e5d486](pr-279-review.audit.md#發現總覽) · [38e99f7e6f3a1971a413](pr-279-review.audit.md#發現總覽) · [37d82b53e03e49987869](pr-279-review.audit.md#發現總覽) · [2ff05643ad9d02ac2f13](pr-279-review.audit.md#發現總覽) · [e75ba5f99afb1c2d98d4](pr-279-review.audit.md#發現總覽) · [0daf5afeb3bce5eea9d2](pr-279-review.audit.md#發現總覽) · [f5d0d25fb430138f10de](pr-279-review.audit.md#發現總覽) · [03fa1cb750478cff9ebd](pr-279-review.audit.md#發現總覽) · [ea7675920bb96ffffbce](pr-279-review.audit.md#發現總覽) · [c4c090f720d61352514f](pr-279-review.audit.md#發現總覽) · [f20ed528b9eeac2f145f](pr-279-review.audit.md#發現總覽) · [e38839e3604515159ea6](pr-279-review.audit.md#發現總覽) · [cfc10bef5c6bf4c71f74](pr-279-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `copycat/book_replay.py:370` 當日第一份五檔那一則(`views is None`,不做差分)的成交照樣放進待扣;它附的是成交後簿,自己的減量永遠比不到,於是之後 8 則 / 1 秒內同價位的減量(含沒有成交的簿則撤單)都被扣成「成交」;加上 `_absorb` 由舊到新扣,新成交自己那則的減量被開盤那筆搶走、新成交吃檔空白。例:5314 9/17 09:00:12.659 / .664 兩則簿則寫成「賣 27.75 −110 / −20 成交」(下一筆成交在第 20 則),開盤那列「吃 賣1 −130」;3481 / 1303 / 1326 吃檔記錯列。兩天正式外掛檔:撤單變成交 10 項 30 張 / 12 項 171 張,吃檔不同的列 57 / 72 | MEDIUM | CONFIRMED(MED→MED:同軸以 decode 還原 TickRow 重跑引擎、抽 12 檔重編逐位元組相同後量測,數字與 reviewer 一致;main session 另以合成三則樣本與 5314 正式檔獨立重現;修法要注意:「先扣當則自己的成交」也會改到盤中每天 20–28 列、未必都變好,當日第一則若是盤中才加入的掃單附舊簿,直接跳過會把之後減量誤記撤單;4.3b lone:他軸 N-A,不降級) | Should Fix | `ask-user` | 修法有兩個取捨(第一份五檔那則的成交怎麼處理、待扣扣法順序),改完要重產 9/16、9/17 永久外掛檔並換上正式資料夾 |
| F-02 | `copycat/book_replay.py:390` 1815 開機收到的前一日 14:30 成交(時刻晚於收到超過容差的時刻異常成交)附前一日的簿,被當成當日第一份五檔;09:00 開盤那則跟它比,拆出 12 項、撤單合計 4,591 張(例「買 114.0 1,967 → 172」),吃檔也用舊簿算並搶走下一筆成交自己的 68 張;9/17 同形(撤單 2,141 張) | LOW | CONFIRMED(LOW→LOW:1815 兩天正式檔解回屬實;只影響這一檔開盤那一刻的顯示) | Nice to Have | `ask-user` | 要決定時刻在未來的異常成交附的簿怎麼處理(比照清空則跳過),與 F-01 同一批重產 |
| F-03 | `copycat/book_replay.py:1027` `_check_changes` 只逐項核對列出的量與前後五檔一致,不核對種類與視野相符、該列的有沒有漏、排序;竄改 wire 把被擠出改成撤單、刪掉一項、吃檔檔位改 5、兩項對調,decode 都照收 | LOW | CONFIRMED(LOW→LOW:同軸竄改實跑 4 種皆被接受;CLI 落檔前另有 `decode(...) != code_day` 整體比對,編碼端寫錯擋得住,缺口只在讀回磁碟檔;reviewer 以 9/16 全日跑建議檢查零違反) | Nice to Have | `auto-fix` | 只加 decode 檢查、不改格式,對現行產出零誤擋 |
| F-04 | `copycat/book_replay.py:485` 模組說明寫「同一格分幾則扣到合成一項」,`_EatLedger._add` 只跟最後一項比,非相鄰(市價佇列 → 限價 → 市價佇列)會出兩項;合併分支也沒有任何測試(改成 `if False:` 87 passed) | LOW | CONFIRMED(LOW→LOW:同軸突變 87 passed 屬實;兩天正式檔多項吃檔 18 / 29 筆、非相鄰重複 0 例,目前零影響) | Nice to Have | `auto-fix` | 依(側別、檔位)找既有項合併,補分兩則扣到同一格的測試並斷言 eat 字面 |
| F-05 | `copycat/book_replay.py:693` 模組 445 → 1,118 行,同檔裝時間尺 / 簿重播、變動分解狀態機、外掛檔 v2 編解碼、decode 自檢 | LOW | PARTIAL(LOW→LOW:行數屬實;專案內 signal_state 1,081、live/tc4 1,320、capital/client 1,388、signal_hub 1,826、stock_engine 1,944、server/app 2,210 行,超過千行是常態) | Nice to Have | `no-op` | 專案常態;下次要動它(例如 F-03)再決定要不要拆 package |
| F-06 | `docs/next-time.md:5`「外盤卻吃市價買」那條把吃檔側別與內外盤相反的非市價排隊 209 張歸因於集合競價 / 暫緩撮合 / 鎖板掃單並寫「引擎不改」;套 F-01 修法後 9/16 同筆兩側 86 → 8、集合競價 30 → 0,合計 209 → 89 張 | LOW | CONFIRMED(LOW→LOW:同軸兩個引擎版本分類重算;9/16 主張成立(57% 是記帳產物),9/17 較弱 —— 同筆兩側 121 → 3、集合競價 104 → 0,但暫緩撮合後 486 不變,合計只少 26%;市價排隊那一大塊與「鎖漲停旗標恆外盤」結論不受影響) | Nice to Have | `ask-user` | 數字要等 F-01 決定後連同 F-22 分桶修正重算,再請 user 決定要不要在畫面註明 |
| F-07 | `tests/test_book_replay.py:1033` 測試名宣稱「檔位只數限價」,但買方樣本分不出(買方由高到低排、價 0 恆在最後);全檔沒有賣方市價佇列(鎖跌停)樣本。`_level_of` 的真值判斷改成 `is not None` 87 passed,合成鎖跌停樣本吃檔「賣1」變「賣2」 | MEDIUM | CONFIRMED(MED→LOW:突變屬實;現行程式正確、屬回歸防線缺口,同突變在正式檔只改到 9/17 10 列) | Nice to Have | `auto-fix` | 補鎖跌停樣本,斷言賣方吃檔檔位與賣方市價佇列項排在賣方最前 |
| F-08 | `tests/test_book_replay.py:987` 模組說明「成交前那一則沒列出這個價位,就看扣到那一則的前一則」這條退路沒有測試;改成 `level = before` 87 passed,合成樣本檔位 2 變「五檔外」 | MEDIUM | CONFIRMED(MED→LOW:突變屬實;退路在正式檔每天約 40 列會走到(突變後 9/16 44 列、9/17 42 列吃檔改變),但現行程式正確、屬測試缺口) | Nice to Have | `auto-fix` | TestEaten 補一案:成交則自帶五檔才第一次出現價位、下一則才減量 |
| F-09 | `tests/test_book_replay.py:454` 同價位多筆待扣成交「由舊到新」扣的順序沒有測試(改成 `reversed(unmatched)` 87 passed);這個順序正是 F-01 修法要動的地方 | LOW | CONFIRMED(LOW→LOW:突變 87 passed 屬實) | Nice to Have | `ask-user` | 要釘哪個順序取決於 F-01 的決定,和 F-01 一起補 |
| F-10 | `tests/test_book_replay.py:1390` golden 字面的空吃檔(註解「開機收到的前一日成交:之前沒有簿」)不依賴 `record_unabsorbed` 的 `trade.index == 0` 守門,拿掉照樣 87 passed;`_frames` 清空分支的 `count_trade`(清空那則是成交則時)也沒測到,改成 pass 仍 87 passed | LOW | CONFIRMED(LOW→LOW:兩個突變各自 87 passed 屬實) | Nice to Have | `auto-fix` | 補首則成交、到期時最後一份簿看不到它的樣本,與清空成交則的期間成交一案 |
| F-11 | `tests/test_book_replay.py:1701` decode 有六個檢查沒有竄改案(檔頭 chg 長度、被擠出 / 首次進入量 > 0、重新可見三量不全 0、吃檔側別碼、吃檔張數 > 0),各自拿掉 87 passed;缺 chg 長度檢查時壞檔變 `zip(strict=True)` 的 ValueError,`cli.py` 只接 PluginFormatError | LOW | CONFIRMED(LOW→LOW:六個突變各自 87 passed;traceback 只在檢查被拿掉時出現,CLI 解的是自己剛編好的檔,正常流程碰不到) | Nice to Have | `auto-fix` | 兩組 parametrize 補對應竄改案 |
| F-12 | `tests/test_book_replay.py:1660` 竄改案的 match 字串(「成交」「撤單」「掛入」「前量」「後量」「吃檔」「第 0 則」)是其他錯誤訊息的子字串,分不出是哪道檢查擋下 | LOW | PARTIAL(LOW→LOW:太寬屬實;reviewer 舉的組合突變(拿掉成交範圍檢查 + cancelled 不 clamp)該案單獨跑 1 passed,但整檔另有 3 條會紅,不會悄悄過) | Nice to Have | `auto-fix` | match 改成各檢查獨有的片語 |
| F-13 | `tests/test_book_replay.py:505` 測試檔 675 → 1,721 行;2426 鎖漲停佇列前兩則在 TestChanges(:500)與 TestEaten(:1011)各寫一份,helper 散在類別之間,檔頭 docstring 沒提 #269 | LOW | PARTIAL(LOW→LOW:事實屬實;專案內 test_stock_engine 4,475、test_signal_hub 3,249、test_client 2,306 行,屬風格小債) | Nice to Have | `no-op` | 專案常態;要拆另開純重構 |
| F-14 | `tests/test_book_replay.py:543` `_at` 型別寫 `tuple[object, ...]` 並用 `getattr(c, "price_milli", None)`(`BookChange` 已公開),欄位改名時 pyright 不會提醒;竄改案註解同一個 parametrize 裡混用格位與值(:1651 寫值、:1658 寫格位、:1664 混用) | LOW | CONFIRMED(LOW→LOW) | Nice to Have | `auto-fix` | 型別改 `BookChange`、註解統一成「格位:值」 |
| F-15 | `evidence/viewer_cdp_template.269.html:654` 同一刻價量兩種寫法:中間欄組標頭用 `rpPrice`(去尾零「39.3」)、變動行用 `rpAt` → `rpPx`(固定小數「39.30」),同一組同時出現;頁頭 `rpKind` 張數印原值「2141」、中間欄與成交明細用千分位「2,141」 | LOW | PARTIAL(LOW→LOW:價的不一致是 #269 新造成;頁頭張數原值是既有碼(diff 為 context 行),next-time 已記「rpKind 那行沒動」) | Nice to Have | `ask-user` | 價要統一成階梯的固定小數還是全頁的去尾零,是顯示取捨 |
| F-16 | `evidence/viewer_cdp_template.269.html:113` 目前這一則(標亮組)的標頭有提亮成 `--ink-2`,同組淡色行沒有:`--muted` 疊在 `--sel` 上淺色 2.69:1、深色 3.58:1,都低於 12 px 字 AA 4.5:1;淡色行帶資訊(被擠出、量沒變的回到五檔、五檔全空) | LOW | PARTIAL(LOW→LOW:對比實算屬實;沿用全頁既有 `--muted`;verification.md §4 記成「其他觀察(不改)」是實作端判斷、非 user 拍板;新資訊只有深色標亮組 3.58 這一格) | Nice to Have | `ask-user` | 視覺取捨(加一條標亮組淡色行的提亮色) |
| F-17 | `.claude/feat/book-replay-changes/verification.md:52` 寫「第 3 條的『播放跨則不漏』更正、第 6 條待收尾時補留言」,但 artifacts commit(08:59:58Z)後約 100 秒(留言 `created_at` 09:01:42Z)已在 #269 貼了追記留言,兩條都在 | LOW | CONFIRMED(LOW→LOW) | Nice to Have | `auto-fix` | 改成已留言並附留言時刻 |
| F-18 | `.claude/feat/book-replay-changes/verification.md:112`「13 檔 × 兩天」實為 13 組(代號、日期),不同代號 11 檔(2426、3441 兩天都有),字面會被讀成 26 組 | LOW | PARTIAL(LOW→LOW:措辭不精確屬實,括號已寫明組成;reviewer 寫的「12 檔」也不對,不同代號是 11) | Nice to Have | `auto-fix` | 改成 13 組(11 檔) |
| F-19 | `.claude/feat/book-replay-changes/code-review-round-1.json:34` 追記的增量快篩數字過時:模板增量寫「+33 / −27」實為 +35 / −29、「1x 420」實為 423;「模板增量只動 P-02 / S-04 / S-10 / S-11 的點」但含懸掛縮排 CSS(AI 截圖對照後另加、非 finding) | LOW | CONFIRMED(LOW→LOW:review1.diff 計數、result_playback_sync.json draws 423 屬實;verification.md 是正確數字) | Nice to Have | `auto-fix` | 更新數字並註明懸掛縮排不屬 finding |
| F-20 | `CLAUDE.md:128` 同一列寫「外掛檔永久保留」、CLI 只收簿 parquet 還在(120 交易日)的日子、「回看頁只讀 v2,v1 檔要重產」;下次升格式版本時,超過保留期的外掛檔既重產不了、回看頁也讀不了(模板只認 `p.v !== 2`、decode 只認 FORMAT_VERSION、外掛檔沒有 v(n) → v(n+1) 遷移) | LOW | CONFIRMED(LOW→LOW:前瞻性設計風險、目前沒有壞;這次兩天都在保留期內,最早約 2027-03 升版才會撞到) | Nice to Have | `ask-user` | 下次升版的政策(外掛檔轉換器或回看頁保留舊版讀取)要先定 |
| F-21 | `evidence/no_double_count_check.py:5` 腳本聲稱證明「每筆成交最多被扣一次」,但「有檔位吃檔 = 價位變動算成交」「吃檔 ≤ 成交張數」靠程式結構恆成立(修前也成立),「五檔外 ≥ 期間成交」只比全日加總(餘量 161 張);verification.md / fix commit / review JSON 拿它當全日證據 | MEDIUM | CONFIRMED(MED→LOW:同軸以修前 `ea193356` 引擎重跑 9/16 還原輸入:3374 12,228 = 12,228、超量 0,但五檔外 58 < 期間成交 59;6209 55 < 61,逐檔才看得出、全日加總被蓋掉;P-01 本身有紅先行單元測試,引擎正確性不受影響) | Nice to Have | `auto-fix` | 加逐檔能判別的檢查並在修前 commit 留紅燈,或把說法改成只證明結構不變式 |
| F-22 | `evidence/eaten_side_breakdown.py:62` `seen_cleared` 一旦設上整天不重置,暫緩撮合結束很久之後的成交也歸「暫緩撮合後」桶(9/17 486 張裡 281 張在最近一次清空後 ≥ 10 分鐘、9/16 57 張裡 26 張);「說不通的只有一筆」只人工看了「其他」桶 | LOW | CONFIRMED(LOW→LOW:同軸重算數字一致) | Nice to Have | `auto-fix` | 改以距上一次清空的時間分桶,重跑後更新 verification / JSON / next-time |
| F-23 | `evidence/build_stage_page.py:32`「現用頁 == 現用模板 + blob」只 print,False 照樣寫出測試頁;docstring 與 verification.md 說「每次都先驗」 | LOW | CONFIRMED(LOW→LOW:測試頁切換後已刪;同類的切換腳本對雜湊不符是直接 return 1) | Nice to Have | `auto-fix` | 不相等就非 0 結束,每次輸出存檔 |
| F-24 | `evidence/playback_window_coverage.py:18` 等六支 evidence 腳本寫死已刪的 worktree(`feat-book-replay-changes`)與暫存資料夾 `viewer-cdp-book-269`:照 commit 重跑,有 assert 的三支 AssertionError;沒 assert 的三支不帶參數時 FileNotFoundError(playback_window_coverage 的外掛檔資料夾寫死、glob 為空時 `missed / n` 除以零),帶資料夾參數時靜默 import 主 tree 的 copycat;tc4-market-facts 引用的 `lock_flag_check.py` 數字沒有結果檔、verification.md 沒有對應小節 | LOW | CONFIRMED(LOW→LOW:同軸 ls 兩路徑皆不存在、逐支判定行為;改路徑重跑 lock_flag_check 四個數字與 SKILL.md 完全一致 —— 事實沒錯、只是追不回) | Nice to Have | `auto-fix` | repo root 由 `__file__` 推、外掛檔資料夾改參數(預設正式資料夾)、補 lock_flag 結果檔與小節 |
| F-25 | `evidence/rp269_expected.py:77` 標準答案的「離開 x.x 秒」用 Python `:.1f`(逢半取偶),頁面 `toFixed(1)` 在 250 / 1250 … 9250 ms 進位不同(2250 ms 頁面「2.3 秒」、標準答案「2.2 秒」);13 組抽樣裡有 5 則重新可見踩到,本次 594 則的窗沒涵蓋 | LOW | CONFIRMED(LOW→LOW:node 與 Python 逐值實跑屬實;未重跑抽樣確認窗) | Nice to Have | `auto-fix` | 改用 ROUND_HALF_UP 的 Decimal |
| F-26 | `evidence/verify_changes.mjs:46` 被竄改的 3 則只拿竄改版比、有任何不符就記「抓到竄改」,從沒對原始標準答案比過;「594 則 0 不符」嚴格是 591 則 | LOW | CONFIRMED(LOW→LOW) | Nice to Have | `auto-fix` | 同一次讀到的頁面先比原始、再比竄改版 |
| F-27 | `evidence/verify_playback_sync.mjs:45` 重畫落在標準答案段外時 `continue` 靜默跳過,沒檢查 `checked > 0` 或 `checked === draws`;播放沒啟動或段參數給錯時「比對 0、不符 0」照過 | LOW | CONFIRMED(LOW→LOW:本次結果 1x 423 / 423、10x 216 / 216,不是空跑) | Nice to Have | `auto-fix` | 加 `draws > 0 && checked === draws` 判定 |
| F-28 | `evidence/pp_common.mjs:20` 自己 mkdtemp 的 Chrome profile 不會被 puppeteer 在 close 時刪掉,呼叫端也不清:`%TEMP%` 下 rp269- 開頭已累積 47 個、687 MB | LOW | PARTIAL(LOW→LOW:洩漏屬實;同寫法已在 #270 證據沿用(rp270-)) | Nice to Have | `auto-fix` | 拿掉 userDataDir 或 close 後刪除,順手清掉現有暫存 |
| F-29 | `evidence/rp269_expected.py:243` 驗收樣本只是加進抽樣,期望值仍取自 decode:2426 買 98.0(39 → 120、淨掛 +81、2 分 35 秒)與 2489 賣 39.2(80 → 0、期間成交 80、淨掛 0)在正式外掛檔上的產出沒有字面斷言;tests `:760-812` 以合成列重建同形樣本並字面斷言這些數字,釘的是引擎規則、不是正式檔產出 | LOW | PARTIAL(LOW→LOW:沒有機械字面斷言屬實;驗收數字有截圖逐字核對(SC-1 / SC-4),同軸直查正式檔值也正確(2426 left 39 / now 120 / traded 0 / away 154,911 ms)) | Nice to Have | `auto-fix` | 產出前對兩個驗收樣本加字面斷言 |
| F-30 | `evidence/switch_live_269.py:82` 最後「新頁 == 新模板 + blob」只放進 step() 印出、固定 `return 0`;`:59` / `:81` 的 assert 在 `python -O` 下會被拿掉;verification.md 把 exit 0 當切換證據之一 | LOW | CONFIRMED(LOW→LOW:這次輸出 True) | Nice to Have | `auto-fix` | 比對 False 時 return 1、assert 改明確 if |
| F-31 | `evidence/switch_live_269.py:67` 覆蓋 160 個正式外掛檔前不檢查外掛檔備份資料夾存在、也不比對與正式 v1 同檔;先換模板(:62)才蓋外掛檔,中途失敗會留下三態混雜;不檢查正式資料夾多餘檔 | LOW | CONFIRMED(LOW→LOW:已成功執行,verification 另有人工逐檔比雜湊;v1 可用舊 CLI 從 parquet 重產,可復原) | Nice to Have | `auto-fix` | 開頭斷言備份、改成先蓋外掛檔驗完再換模板、比對檔名集合 |
| F-32 | `evidence/run_with_peak_memory.py:84` docstring 寫掃「子孫程序」,`children_of` 只比 parent pid(直屬子程序);讀 PeakWorkingSetSize 不是 commit,記憶體吃緊、工作集被修剪時會低估 | LOW | CONFIRMED(LOW→LOW:這次 CLI 無 subprocess / multiprocessing,直屬子程序就是幹活的程序,5.68 / 7.77 GB 是有效工作集峰值) | Nice to Have | `auto-fix` | docstring 改直屬子程序並多印 PeakPagefileUsage |
| F-33 | `evidence/syntax_check.py:26` 抽到 0 段 script 時迴圈不執行,照樣印 SYNTAX-OK、exit 0 | LOW | CONFIRMED(LOW→LOW:這次模板確實 1 段主程式;主要保險仍是 DOM 檢查 console 0) | Nice to Have | `auto-fix` | 0 段直接非 0 結束 |
| F-34 | `evidence/viewer_cdp_template.269.html:674` ticket 驗收條件「重新可見的期間變化明確標示『無法分辨是一次掛進或分次堆積』」,量沒變的淡色那一支沒有這句 | LOW | OUT_OF_SCOPE(LOW→LOW:淡色一行是 user 拍板的格式,這一支只在離開時量 = 現在量且期間成交 0 時出現,本來就沒有期間變化可標;定義與規則已對所有回到五檔統一註明) | 參考用 | `no-op` | 不是本 PR 缺陷;淡色行加短註屬新的顯示需求 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 8acd905c7a7a2fc60282 action=ask-user
F-02 finding_uid: 25e141d6cfec15932949 action=ask-user
F-03 finding_uid: c898c8d6896acb90a5c7 action=auto-fix
F-04 finding_uid: 3b9d14179fd4b010110a action=auto-fix
F-05 finding_uid: 00e6e0bacb9485372de2 action=no-op
F-06 finding_uid: 179d5eb8b7a2c0777d45 action=ask-user
F-07 finding_uid: 549f032774ec0813f786 action=auto-fix
F-08 finding_uid: b219f6c190fb48b2a70f action=auto-fix
F-09 finding_uid: 3edf65f1ab2c0e700792 action=ask-user
F-10 finding_uid: 4ad438347a3b2f520f58 action=auto-fix
F-11 finding_uid: d42ffda958d759e27189 action=auto-fix
F-12 finding_uid: 69dc79f4ece6e9187b8e action=auto-fix
F-13 finding_uid: 909fea75525e3af2710f action=no-op
F-14 finding_uid: 469507938e87b419b3a1 action=auto-fix
F-15 finding_uid: 4b91ac8cb96129f02885 action=ask-user
F-16 finding_uid: ac72fdc1c142cc2ad7d2 action=ask-user
F-17 finding_uid: 4f97f85258a2f3bb993e action=auto-fix
F-18 finding_uid: 31533f261d96901b80a5 action=auto-fix
F-19 finding_uid: 1b94d683ed849b1d0e0b action=auto-fix
F-20 finding_uid: 285d76158740937d9f73 action=ask-user
F-21 finding_uid: a007bed1c382b1597471 action=auto-fix
F-22 finding_uid: 1c82284c59f7d0e5d486 action=auto-fix
F-23 finding_uid: 38e99f7e6f3a1971a413 action=auto-fix
F-24 finding_uid: 37d82b53e03e49987869 action=auto-fix
F-25 finding_uid: 2ff05643ad9d02ac2f13 action=auto-fix
F-26 finding_uid: e75ba5f99afb1c2d98d4 action=auto-fix
F-27 finding_uid: 0daf5afeb3bce5eea9d2 action=auto-fix
F-28 finding_uid: f5d0d25fb430138f10de action=auto-fix
F-29 finding_uid: 03fa1cb750478cff9ebd action=auto-fix
F-30 finding_uid: ea7675920bb96ffffbce action=auto-fix
F-31 finding_uid: c4c090f720d61352514f action=auto-fix
F-32 finding_uid: f20ed528b9eeac2f145f action=auto-fix
F-33 finding_uid: e38839e3604515159ea6 action=auto-fix
F-34 finding_uid: cfc10bef5c6bf4c71f74 action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 開盤那筆成交搶走之後的減量,沒成交的撤單被寫成「成交」
**File**: `copycat/book_replay.py`
**Line**: 370

**Comment**:
```
開盤那筆(當日第一份五檔那一則)不做差分,但它的成交照樣進待扣。
它附的是成交後的簿,自己的減量永遠比不到 → 之後 8 則 / 1 秒內同價位只要減量,
連沒有成交的撤單都會被算成「成交」,吃檔也記到開盤那列。
_absorb 又是由舊到新扣,後面那筆成交自己那則的減量會被開盤那筆搶走,吃檔欄變空白。

實例:5314 9/17 09:00:12.659、.664 兩則是簿則(下一筆成交在第 20 則),
中間欄卻寫「賣 27.75 −110 成交」「−20 成交」;開盤那列寫「吃 賣1 −130」。
兩天量起來:撤單變成交 10 項 30 張 / 12 項 171 張,吃檔記錯的列 57 / 72 列。

方向:views is None 那一則的成交不進待扣;要不要把扣法改成先扣當則自己的成交再扣舊的,
要一起想清楚(改扣法也會動到盤中每天二十幾列;當日第一則若是盤中才加入的掃單、附的是舊簿,
直接跳過會把之後的減量誤記成撤單)。改完補紅先行測試,重產兩天外掛檔。
```
#### #2 1815 開機收到的前一日成交,舊簿被當成今天第一份五檔
**File**: `copycat/book_replay.py`
**Line**: 390

**Comment**:
```
1815 每天開機會收到前一日 14:30 的成交(時刻比收到晚七小時的那種異常成交),
它附的是前一天收盤的簿,卻被當成當日第一份五檔。
09:00 開盤那則拿它來比 → 拆出 12 項,撤單合計 4,591 張(例如「買 114.0 1,967 → 172」),
吃檔也拿舊簿算、還搶走下一筆成交自己那 68 張。9/17 同樣形狀。

建議:時刻在未來的異常成交,附的簿不拿來建視野跟吃檔參考簿,比照清空則處理
(只排除「晚於收到時刻超過容差」那種;早於目前時鐘的異常成交附的是當下的簿)。
補一條 1815 形狀的測試,跟 F-01 同一批重產。
```
#### #3 decode 沒核對種類跟視野相不相符,被擠出改成撤單也照收
**File**: `copycat/book_replay.py`
**Line**: 1027

**Comment**:
```
_check_changes 只核對「列出來的每一項」量跟前後五檔對得上,
沒核對種類跟視野是不是相符,也沒核對該列的有沒有漏。
實測竄改:被擠出改寫成撤單、整項刪掉、吃檔檔位 1 改 5、兩項對調 → decode 全部照收。
CLI 落檔前有整體比對所以自己產的檔擋得住,但讀回磁碟檔時這層自檢承諾不完整。

照前後兩份五檔的邊界補三組:
1. 種類 vs 視野:價位變動兩份都看得到、被擠出 = 前看得到後看不到、重新可見 / 首次進入 = 前看不到後看得到
2. 完整性:兩份都看得到且量不同的價位恰一項、落到新邊界外且前有量的必有被擠出、市價佇列量變必有一項
3. 排序:買方在前、同側市價佇列在前再由最優價往外
9/16 全日正式檔跑過零違反,decode docstring 同步列出。
```
#### #4a 「同一格合成一項」只合併相鄰的
**File**: `copycat/book_replay.py`
**Line**: 485

**Comment**:
```
模組說明寫「同一格分幾則扣到合成一項」,這邊只跟最後一項比。
同一筆先扣市價佇列、再扣限價、下一則又扣市價佇列 → 會出「吃 市價買 −4、買1 −3、市價買 −3」兩項市價買。
兩天正式檔目前 0 例,只是承諾跟實作不一致。

改成用 (side, level) 找既有項合併(一筆成交最多幾項,線性找就好),
或把說明改成「連續扣到同一格才合成一項」。
```
#### #4b 合併分支沒有測試,拿掉合併照樣全綠
**File**: `tests/test_book_replay.py`
**Line**: 987

**Comment**:
```
合併分支沒有任何測試:把 _add 的合併條件改成 if False,87 條照樣全綠。
合併拿掉的話外掛檔 eat 會從 [1, 1, 10] 變 [1, 1, 4, 1, 1, 6],round-trip 照綠、回看頁印兩項。

補一案:成交 P×10(五檔還是舊的)→ 下一則 P 減 4 → 再下一則減 6,
斷言 eaten == (Eaten("ask", level=1, qty=10),),順便斷言 encode 的 eat 字面。
```
#### #6 「外盤卻吃市價買」那條的數字被 F-01 放大了
**File**: `docs/next-time.md`
**Line**: 5

**Comment**:
```
這條拿來請 user 決定的數字被 F-01 放大了:
非市價排隊那 209 張裡,「同筆兩側都吃」「集合競價」兩桶大部分是開盤那筆搶減量造成的。
套 F-01 的修法重算,9/16 兩桶 86 / 30 張 → 8 / 0 張,合計 209 → 89 張;9/17 只少 26%(暫緩撮合那桶不受影響)。
「鎖漲停旗標恆外盤」那個主結論不受影響。

F-01 決定後重跑分桶(順便修 F-22 的分桶),再改這條的數字跟歸因。
```
#### #7 「檔位只數限價」用買方樣本分不出來,鎖跌停沒測
**File**: `tests/test_book_replay.py`
**Line**: 1033

**Comment**:
```
這條名稱講「檔位只數限價」,但用的是買方樣本:買方由高到低排,價 0 本來就排最後,
就算把 0 算進去 169.5 還是第 2 檔,分不出來。會被 0 影響檔位的是賣方(0 排第一),全檔沒有 ask=[(0, …)] 的樣本。
實測把 _level_of 的 if (p := book[...]) 改成 is not None,87 條全綠,鎖跌停時「吃 賣1」會變「吃 賣2」。

補一個鎖跌停樣本:ask=[(0, 500), (90_100, 20)] → 外盤成交 90.1×4 → 賣 90.1 剩 16,
斷言 Eaten("ask", level=1, qty=4),同一個樣本再斷言賣方市價佇列那項排在賣方最前。
```
#### #8 吃檔「看扣到那一則的前一則」這條退路沒測
**File**: `tests/test_book_replay.py`
**Line**: 987

**Comment**:
```
模組說明寫:「成交前那一則沒列出這個價位,就看扣到那一則的前一則」。
TestEaten 四案跟字面測試裡,成交價都已經列在成交前那一則,這條退路從沒被走到。
實測把 level = before if before is not None else _level_of(...) 改成 level = before,87 條全綠,
看得到的一檔會被標成「五檔外」。正式檔每天約四十列會走這條。

補一案:簿 ask 100.0 → 成交 100.5×3(成交則自帶的 ask 多出 100.5×10)→ 下一則 100.5 剩 7,
斷言 Eaten("ask", level=2, qty=3)。
```
#### #9 同價位多筆待扣先扣哪筆沒測,而 F-01 正要改它
**File**: `tests/test_book_replay.py`
**Line**: 454

**Comment**:
```
兩筆同價位成交都還沒扣完時,先扣哪一筆沒有測試:把 _absorb 的 for trade in unmatched 改成 reversed,87 條全綠。
先扣哪筆會決定較舊那筆會不會到期(成交變撤單)、吃檔掛到哪一列。

這個順序剛好是 F-01 要不要改的地方 → 先決定 F-01,再照決定補一案:
兩筆 P×5 成交(五檔還是舊的)→ 下一則減 5 → 距較舊那筆第 9 則時再減 5,斷言最後一項 traded 與兩筆各自的吃檔。
```
#### #10 開機成交的空吃檔不靠守門、清空的成交則沒測
**File**: `tests/test_book_replay.py`
**Line**: 1390

**Comment**:
```
這個 [] 的註解說「之前沒有簿,看不出吃哪一檔」,但它其實不靠 trade.index == 0 那道守門:
拿掉守門,這個樣本最後一份簿買方只有一層(整側看得到),結果恰好還是 [],87 條全綠。
另外清空分支裡的 view.count_trade(清空的那一則是成交則時)也沒測到,改成 pass 一樣全綠。

補兩案:
1. 首則成交 105.0×2、1 秒後一份五層賣方到 102.0 → 斷言吃檔 ()(拿掉守門會變「賣五檔外 −2」)
2. 被擠出價位上的成交、成交則五檔全空 → 斷言重新可見的 traded_away(實錄不可能出現的話就刪分支)
```
#### #11 decode 有六個檢查沒有竄改案
**File**: `tests/test_book_replay.py`
**Line**: 1701

**Comment**:
```
decode docstring 列的檢查裡有六條沒有竄改案,各自拿掉 87 條全綠:
檔頭 chg 長度、被擠出量 > 0、首次進入量 > 0、重新可見三量不全 0、吃檔側別碼 0 / 1、吃檔張數 > 0。
其中 chg 長度那條拿掉的話,壞檔會變成 zip(strict=True) 的 ValueError,CLI 只接 PluginFormatError → 吐 traceback。

兩組 parametrize 補:w["chg"].pop() → "chg"、被擠出 / 首次進入量寫 0、重新可見三量改 0、
w["eat"][0].__setitem__(0, 2)、w["eat"][0].__setitem__(2, 0)。
```
#### #12 竄改案的 match 字串太寬
**File**: `tests/test_book_replay.py`
**Line**: 1660

**Comment**:
```
match="成交" 這類字串太寬:算式錯誤的訊息「掛入 … / 撤單 … 不合算式(前量 …、後量 …、成交 …)」裡也有「成交」「撤單」「掛入」「前量」「後量」,
分不出到底是哪道檢查擋下的。目前每案都剛好命中宣稱的檢查,但檢查被換掉時這一案不一定紅(整檔其他測試還會紅)。

改用各檢查獨有的片語,例如「不在 0 到減少的量之間」「不合算式」「與前一則五檔」「當日第一份五檔」。
```
#### #14 _at 用 object 加 getattr,竄改案註解寫法不一
**File**: `tests/test_book_replay.py`
**Line**: 543

**Comment**:
```
_at 用 tuple[object, ...] 加 getattr 取 price_milli,BookChange 已經在 __all__,
欄位改名的時候 pyright 抓不到。改成 _at(changes: tuple[BookChange, ...], price: int) -> list[BookChange],直接讀 c.price_milli。

另外竄改案的註解三種寫法混在一起(有的寫值、有的寫格位、1664 行前兩個是格位後面是值),
讀的人要自己推 slice(48, 51) 對到哪幾格。統一寫成「格位:值」,例如 [45 碼 5, 46 價, 47 離開 80, 48 現在 0, …]。
```
#### #15 同一組裡同一個價寫成 39.3 跟 39.30
**File**: `.claude/feat/book-replay-changes/evidence/viewer_cdp_template.269.html`
**Line**: 654

**Comment**:
```
同一組中間欄裡,組標頭寫「成交 39.3 × 56 外」(rpPrice 會去尾零),變動行寫「買 39.30 0 → 60」(rpPx 固定小數),
同一個價兩種寫法。頁頭的張數也印原值「× 2141 張」,中間欄跟成交明細是「2,141」。

價要統一成哪一種(跟階梯一樣固定小數,或跟全頁一樣去尾零)要決定一下;
頁頭張數改走 rpQty,可以跟 next-time 記的「rpKind 收斂」那條一起做。
```
#### #16 目前這一則的淡色行對比只有 2.7:1
**File**: `.claude/feat/book-replay-changes/evidence/viewer_cdp_template.269.html`
**Line**: 113

**Comment**:
```
目前這一則那組的標頭有提亮(--ink-2),但同一組的淡色行沒有,
淡色字疊在標亮底上:淺色 2.7:1、深色 3.6:1,12 px 字都低於 4.5:1。
淡色行帶的是「被擠出五檔 N 張」「量沒變的回到五檔」「五檔全空」這些資訊,最該看的那一組反而最難讀。

可以加一條 .rp-msg.cur .rp-line.dim,用介於 muted 跟 ink-2 之間的顏色,讓標亮底上到 4.5:1。要不要調是視覺取捨。
```
#### #17 verification 還寫「待收尾時補留言」,其實已經貼了
**File**: `.claude/feat/book-replay-changes/verification.md`
**Line**: 52

**Comment**:
```
這句還寫「待收尾時補留言」,但 artifacts commit 之後大約 100 秒就已經在 #269 貼了追記
(第 1 點是「播放跨則不漏」的更正、第 2 點是首次進入五檔),之後看紀錄的人會以為還沒貼。
改成「兩條都已留言(09-17 17:01,#269 最後一則)」就好。
```
#### #18 「13 檔 × 兩天」其實是 13 組
**File**: `.claude/feat/book-replay-changes/verification.md`
**Line**: 112

**Comment**:
```
「13 檔 × 兩天」會被讀成 26 組,實際是 9/16 10 檔 + 9/17 3 檔 = 13 組 代號|日期,
其中 2426、3441 兩天都有,不同代號是 11 檔。改成「13 組 代號|日期(11 檔)」。
```
#### #19 review 紀錄 JSON 的增量數字停在改懸掛縮排之前
**File**: `.claude/feat/book-replay-changes/code-review-round-1.json`
**Line**: 34

**Comment**:
```
這份 JSON 是 review 處置的正式紀錄,但追記的數字停在懸掛縮排改完之前:
模板增量寫 +33 / −27,review1.diff 實際是 +35 / −29;播放同一刻寫 1x 420,結果檔是 423;
還寫「模板增量只動 P-02 / S-04 / S-10 / S-11 的點」,但增量第一段是懸掛縮排 CSS(截圖對照後另加,不屬 finding)。
更新成 +35 / −29、1x 423,並註明懸掛縮排的來源。
```
#### #20 外掛檔「永久保留」跟「只讀最新版、舊檔重產」下次升版會衝突
**File**: `CLAUDE.md`
**Line**: 128

**Comment**:
```
同一列寫了三件事:外掛檔永久保留、CLI 只收簿 parquet 還在的日子(簿只留 120 交易日)、回看頁只讀 v2 所以 v1 要重產。
這次只有 9/16、9/17 兩天還在保留期內沒事;但下次再升格式版本時,超過 120 交易日的外掛檔(那時唯一留下的簿資料)
既重產不了、回看頁也讀不了,「永久保留」就落空。

這列補一句「重產只在簿 parquet 保留期內可行;之後升版要附外掛檔 v(n) → v(n+1) 轉換,或回看頁保留舊版讀取」,
外掛檔本身有完整的 kf / d / trade,理論上可以自己轉。
```
#### #21 「不重複扣」的檢查在修前也會過
**File**: `.claude/feat/book-replay-changes/evidence/no_double_count_check.py`
**Line**: 5

**Comment**:
```
這支說它證明「每筆成交最多被扣一次」,但前兩條是程式結構保證的:
_traded 每扣一次就記一格吃檔(所以兩邊恆相等)、_absorb 每次最多扣剩量(所以恆 ≤ 成交張數),修前也一樣成立。
第三條「五檔外 ≥ 期間成交」只比全日加總,有 161 張餘量:修前 commit 重跑 3374 是 58 < 59、6209 是 55 < 61,
逐檔才看得出差,加總就被蓋掉了。

要當 P-01 的全日證據,補一條逐檔(或逐價位被擠出期間)能判別的檢查,並在修前 commit 跑一次留紅燈;
不然 verification.md 跟 commit 訊息的說法改成「結構不變式成立」就好,P-01 的保護靠紅先行單元測試。
```
#### #22 「暫緩撮合後」旗標設上就整天不清
**File**: `.claude/feat/book-replay-changes/evidence/eaten_side_breakdown.py`
**Line**: 62

**Comment**:
```
seen_cleared 同一檔第一次清空之後整天都是 True,恢復連續交易幾十分鐘後的成交還是歸「暫緩撮合後」。
重算:9/17 那桶 486 張裡有 281 張是在清空 10 分鐘以後(例如 2455 09:53、6715 10:03),9/16 57 張裡 26 張。
「說不通的只有 6147 一筆」只看了「其他」桶,這一桶沒看。

改成跟上一次清空的距離掛鉤(例如清空後 N 分鐘內,或清空後第一份非空五檔之前),超出的歸「其他」一起看;
跟 F-01 / F-06 一起重跑。
```
#### #23 測試頁的前置檢查只印不擋
**File**: `.claude/feat/book-replay-changes/evidence/build_stage_page.py`
**Line**: 32

**Comment**:
```
前置檢查只 print,是 False 也照樣寫出測試頁;docstring 跟 verification.md 都寫「先驗再照做」。
切換腳本遇到雜湊不符是直接 return 1,這支做法不一致。
改成 if rebuilt_live != live: sys.exit("現用頁不是現用模板 + blob,先確認另一個 session 的狀態"),每次輸出存進 evidence。
```
#### #24a evidence 腳本寫死已刪的 worktree 跟暫存資料夾
**File**: `.claude/feat/book-replay-changes/evidence/playback_window_coverage.py`
**Line**: 18

**Comment**:
```
這支跟 eaten_side_breakdown / eaten_side_check / lock_flag_check / no_double_count_check 一樣,
WORKTREE 寫死成已經刪掉的 feat-book-replay-changes worktree,BOOKDIR 預設是切換後刪掉的 viewer-cdp-book-269。
照 commit 重跑(實跑過):有 assert 的三支 AssertionError;eaten_side_breakdown / lock_flag_check 不帶參數時找不到預設資料夾,
帶資料夾參數就悄悄用主 tree 的 copycat(venv 直接 import 解到主 tree);這支的外掛檔資料夾寫死,找不到檔時 missed / n 除以零。

WORKTREE 改由 Path(__file__).resolve().parents[4] 推 repo root,外掛檔資料夾一律從參數讀、預設正式 viewer-cdp-book。
```
#### #24b 標準答案腳本同樣產不出來
**File**: `.claude/feat/book-replay-changes/evidence/rp269_expected.py`
**Line**: 26

**Comment**:
```
標準答案腳本同樣寫死已刪的 worktree 跟暫存資料夾,rp269_segment_expected 也 import 它,
verification.md 說「之後重跑用 RP_NEW_PAGE / RP_OLD_PAGE 指到正式頁」,但標準答案這一段根本產不出來。
一樣改成由 __file__ 推 repo root、BOOKDIR 用參數或環境變數(正式 viewer-cdp-book 跟暫存那份已驗逐位元組相同)。
```
#### #24c 鎖漲停旗標那筆 commit 沒有驗證小節跟結果檔
**File**: `.claude/feat/book-replay-changes/verification.md`
**Line**: 25

**Comment**:
```
這列 commit(tc4-market-facts 鎖漲停旗標)在 verification.md 沒有對應小節,evidence 裡也沒有 lock_flag_check 的結果檔,
SKILL.md 卻把這支腳本當 10,300 / 5,866 / 3,174 / 7,814 筆全 outer 的出處。
補一小節跟 result_lock_flag_check.txt(重跑過數字完全對得上),附重跑指令
(PYTHONPATH=<repo> python evidence/lock_flag_check.py <回看頁>\viewer-cdp-book)。
```
#### #25 標準答案的秒數四捨五入跟頁面不一樣
**File**: `.claude/feat/book-replay-changes/evidence/rp269_expected.py`
**Line**: 77

**Comment**:
```
標準答案的「離開 x.x 秒」用 Python :.1f,逢半取偶;頁面 rpDur 用 toFixed(1)。
250、1250、2250 … 9250 ms 這十個值兩邊不一樣(2250 ms 頁面是「2.3 秒」、標準答案是「2.2 秒」)。
這 13 組裡有 5 則重新可見剛好踩到(例如 2426 9/16 第 52,683 則、2305 第 9,513 則),這次抽樣的窗沒涵蓋所以 0 不符,
換抽樣或用播放段腳本播到那幾則會誤報成頁面 bug。

改成 str(Decimal(ms / 1000).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),0–9949 ms 逐值比過 toFixed(1) 零差異。
```
#### #26 被竄改的 3 則沒對原始答案比過
**File**: `.claude/feat/book-replay-changes/evidence/verify_changes.mjs`
**Line**: 46

**Comment**:
```
被竄改的 3 則只拿竄改後的版本比,只要有不符就算「抓到竄改」,從來沒對原始標準答案比過;
它們如果同時有真的不符,會被吃進「竄改抓到」而不會出現在 mismatches。所以「594 則 0 不符」嚴格說是 591 則。
改成同一次讀到的頁面狀態先比原始 cases[k](不符進 mismatches),再比竄改版確認抓得到。
```
#### #27 播放同步檢查可能比對 0 次照過
**File**: `.claude/feat/book-replay-changes/evidence/verify_playback_sync.mjs`
**Line**: 45

**Comment**:
```
重畫落在標準答案段外就 continue 跳過,最後沒檢查 checked > 0 或 checked === draws。
播放沒啟動(90 秒逾時 caps 為空)或段的 t0 / t1 給錯時,一樣會得到「比對 0、不符 0」。
這次結果是 423 / 423、216 / 216 沒問題;最後補一個 draws > 0 && checked === draws 的判定,不成立寫進 out 並非 0 結束,
t0 / t1 也寫進結果檔。
```
#### #28 無頭 Chrome 的暫存 profile 沒清,已經 687 MB
**File**: `.claude/feat/book-replay-changes/evidence/pp_common.mjs`
**Line**: 20

**Comment**:
```
自己 mkdtemp 建的 profile,puppeteer 在 browser.close() 時不會幫你刪,呼叫端也都沒清。
本機 %TEMP% 下 rp269- 開頭的已經 47 個、687 MB,每跑一次繼續長(#270 的 rp270- 也是同一個寫法)。
二擇一:拿掉 userDataDir(同一份 puppeteer 實測過:不給時自建 %TEMP%\puppeteer_dev_chrome_profile-*,close() 後自動刪;
自己給的關掉還在),或 close 後 rmSync(dir, {recursive: true, force: true});
現有的 rp269- / rp270- 暫存資料夾可以順手清掉。
```
#### #29 驗收樣本的數字沒有字面斷言
**File**: `.claude/feat/book-replay-changes/evidence/rp269_expected.py`
**Line**: 243

**Comment**:
```
驗收樣本只是加進抽樣,期望值還是取自 decode:引擎要是在真資料上把驗收值算壞(例如淨掛變 +80),
verify_changes 照樣 594 / 594 過。這次的數字有截圖逐字核對所以沒事,風險在之後重產外掛檔時拿這支當回歸。
(tests 760–812 行已用合成列字面斷言同形樣本,缺的是「正式檔產出 = 字面」這一道。)
產出前加字面斷言:2426 第 41,957 則的重新可見 (left, now, traded, net) == (39, 120, 0, 81) 且 round(away_ms / 1000) == 155;
2489 賣 39.2 同樣處理。
```
#### #30 切換腳本最後的比對不影響結束碼
**File**: `.claude/feat/book-replay-changes/evidence/switch_live_269.py`
**Line**: 82

**Comment**:
```
最後這個比對只印出 True / False,之後一律 return 0;前面的 assert 在 python -O 下也會被拿掉。
verification.md 把 exit 0 列成切換證據,但結束碼其實不代表新頁正確(這次印的是 True,沒事)。
比對 False 時印出並 return 1,assert 改成明確的 if / return。
```
#### #31 切換腳本沒先確認外掛檔備份,而且先換模板才蓋外掛檔
**File**: `.claude/feat/book-replay-changes/evidence/switch_live_269.py`
**Line**: 67

**Comment**:
```
蓋掉 160 個正式外掛檔之前,沒檢查 viewer-cdp-book.bak-20260917-pre269 在不在、跟正式 v1 是不是同一份,只靠 docstring 說備份過。
順序也是先換模板(第 3 步)才蓋外掛檔(第 4 步),第 4 步中途失敗會留下「模板 v2、資料夾一半 v2、頁面還是舊版」三種狀態混在一起。
這次順利、備份也人工比過雜湊;下次重用的話:開頭斷言備份存在且逐檔雜湊等於正式檔 → 先複製並驗完外掛檔 → 再換模板 → 再重建,
複製後比對正式資料夾與暫存區的檔名集合相等。
```
#### #32 峰值記憶體只掃直屬子程序,也不是 commit 峰值
**File**: `.claude/feat/book-replay-changes/evidence/run_with_peak_memory.py`
**Line**: 84

**Comment**:
```
docstring 說掃「子孫程序」,children_of 只比 th32ParentProcessID == proc.pid,只有直屬子程序。
讀的也是 PeakWorkingSetSize(實體駐留)不是 commit,記憶體吃緊、工作集被修剪時會低估實際需求。
這次 book-replay 沒有孫程序,數字有效;docstring 改成「直屬子程序」(或改遞迴),同時多印 PeakPagefileUsage。
```
#### #33 語法檢查抽到 0 段也印 SYNTAX-OK
**File**: `.claude/feat/book-replay-changes/evidence/syntax_check.py`
**Line**: 26

**Comment**:
```
regex 抽不到任何 script(頁面結構或屬性寫法改了)時迴圈不跑,直接印 SYNTAX-OK、exit 0。
這次確實是 blob + 1 段主程式,沒事;補一行 if not scripts: sys.exit("找不到程式 script 區塊")。
```
## 沒做的部分（結案對帳）
- Codex 中性軸:N-A(user 已停用;本機無 codex CLI)。
- Codex 對抗軸:N-A(user 已停用)。
- Gemini Flash / Pro 軸:N-A(user 已停用;本機無 agy CLI;Step 2.96 未問、按前例)。
- Codex preset(Step 2.98):N-A(未問、按前例)。
- Cross-axis verification 4.1:N-A(無非 CC finding);4.2:以同軸 code-reviewer subagent 獨立複查代替 PASS,**非獨立跨軸證據**;4.3a:N-A(單軸無 consensus);4.3b:逐條見複查欄 PASS(他軸未執行、不存在「他軸沉默」,不據以降級)。
- Blast radius(Step 2.9):跑了、空輸出跳過(sem 未安裝)。
- React-doctor(Step 2.97):N-A(非 React PR)。
- Formal spec traceability(Step 2.65):SKIPPED (C4_NO_REPO_SPEC_PATH)。
- Author calibration(Step 2.2):無檔、無套用。
- 逐檔覆蓋:54/54(covered 20 / no-issues 24 / skipped 10 / missed 0)PASS;chunk B source 846 行略超 800 門檻(「約 800」),未再拆。
- 行號重定位:33 個逐字 anchor exact 32 / ambiguous 1 / FAILED 0;4 個 `<none>` pin 以最近符號行定位 PASS。
- Codex config mutation / restore(Step 3 / Step 7):N-A(Codex 未執行,未改 `~/.codex/config.toml`)。
- 未驗證前提:F-01 修法方向(先扣當則自己的成交)的淨效益未驗證(補證只量到變動列數與分佈,未逐列判斷改後是否正確),已在 comment 保留「要一起想清楚」語式;F-06 的 9/17 歸因比例依修法版本而定(兩個修法版本的分桶數字已重跑,修法本身未定);F-20 為前瞻風險(最早 120 交易日後才會撞到)。原列的 F-25(抽樣窗)與 F-28(puppeteer 行為、暫存大小)已由 Self-Verify 補證驗掉,見「Search-proof 與機制鏈」。
- 失敗軸 / 工具失敗:無。
- Self-Verify(Step 6):FAIL → 已修正。`skill-verify-auditor`(requested opus)只讀完整證據草稿,輸出 R1–R10 各一行、順序正確、FAIL 集合與 verdict 一致:`VERDICT: VIOLATIONS: R6, R8`(R1–R5、R7、R9、R10 PASS)。
  - R6 缺口:F-07「全檔沒有 ask=[(0, …)] 樣本」、F-08「退路從沒被走到」、F-11「六條沒有竄改案」等 absence / runtime 斷言只附 reviewer 的「87 passed」,沒有查詢指令、file:line 與判斷語意。修正:main session 在暫存複本重跑 13 個突變與 F-12 兩個組合對照、插樁量 6 類分支在 87 案中的執行次數、AST 掃價 0 樣本;重跑 reviewer / 複查員留下的 15 支量測腳本與 demo 合成樣本、照 commit 實跑 6 支 PR 證據腳本;34 條逐條寫進「Search-proof 與機制鏈」(查詢 / 工具 / file:line / 判斷條件 / 結果 / 仍成立理由)。
  - R8 缺口:F-28 修法句把 puppeteer「預設每次一份暫存 profile、關閉時自動刪」寫成定論。修正:讀 `pp_common.mjs` 引用的同一份 bundle 原始碼,並實跑兩次 headless Chrome(給 / 不給 `userDataDir`)驗證,comment 改寫成實測敘述。
  - 補證過程另校正 5 處描述(severity / action / UID 皆不變):F-01「10 則 / 12 則」→「10 項 / 12 項」(量的是價位變動項);F-17 留言時刻 09:01:38Z → GitHub `created_at` 09:01:42Z;F-24「沒 assert 的靜默改用主 tree」→ 只在帶資料夾參數時成立、不帶參數是 FileNotFoundError / ZeroDivisionError;F-29 補明 tests 已以合成列字面斷言同形樣本;Action Items「範圍限開盤與集合競價時刻」→「以開盤為主」(盤中另有 28 / 20 列、至少一例非集合競價)。
  - 以上修正**未經第二次獨立稽查**。
