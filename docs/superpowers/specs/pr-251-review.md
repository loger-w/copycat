# PR #251 Code Review 比較報告 · SHA 541637ac
**Report projection schema**: 1

**PR**: [loger-w/copycat#251](https://github.com/loger-w/copycat/pull/251)
**標題**: perf: 批 B Tier 0 零風險小改十件(#240)—— 輪詢起點 / 窗和 running sum / EcoQoS+timer 1 ms / 相關係數增量 / 審計 mkdir / asdict / switchinterval / 分發與 latch 短路 / 江波圖 str 鍵
**作者**: loger-w
**分支**: `perf/batch-b-tier0` → `master`
**變更**: 65 檔案, +2,749 / -115
**審查日期**: 2026-09-15
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨;rebase merge 後 master tip `f5ba99ac`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `541637ac0b499be1e8f1d1c0230499ccac8787cb`;destination repo id `R_kgDOTsITBg` + baseRefOid `1e0720be6a1efaeeb2ff48faf44be468eef94429`;`input_binding: verified` —— `git fetch origin refs/pull/251/head` 取回的 FETCH_HEAD = headRefOid 逐字相等,review worktree detached 於該 SHA;`git diff --stat 541637ac f5ba99ac` 零行(與落地版逐檔等價)
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 SHA;遠端分支已刪,`refs/pull/251/head` 仍指 `541637ac`,產報告前重抓 headRefOid 仍為它);`base_changed=true`(origin/master 自 `1e0720be` 前進至 `f5ba99ac`,內容 = 本 PR 自身 14 筆 rebase 後 commit,其後零新 commit);`review_context_changed=false`(審的是 PR head,與落地版逐檔等價)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示「一樣走 CC 單軸」,沿 #188 … #238 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **主 session 同軸 4.3b lone-finding 判斷 + 三處自行實跑代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer ×3 chunk instances(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;source diff 全為 .py,chunked 派工:chunk A = 15 `copycat/` 源檔、chunk B = 14 `tests/` 檔、chunk C = 35 artifact + 1 skill 檔);內部複查=主 session(4.3b lone-finding 判斷;另自行實跑 F-05 重複腿名 n60=18、F-06 `grep try/except` 零命中、F-02 `OverlayCache` 無 TTL);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=65 → covered 22 / no-issues 43 / skipped 0 / **missed 0**(chunked: **是**,29 source 檔 / 2,864 diff 行 → 3 chunks(A 15 / B 14 / C 36);65/65 per-file accounting 齊:A = 6 檔有 finding + 9 REVIEWED_NO_ISSUES;B = 6 + 8;C = 10 檔有 finding(含 harness 三支以「finding 脈絡」列出)+ 26 REVIEWED_NO_ISSUES(含 20 份 out_*.json 逐格核對);無 INTENTIONALLY_SKIPPED)
**定位 (ENH-B)**: anchored exact 25 / ambiguous 0 / **FAILED 0**(25 條 anchor 在 worktree 逐字唯一命中:win_timer.py:50 / __main__.py:166 / :151 / :168 / corr_state.py:66 / :213 / signal_state.py:392 / river_backfill.py:31 / corr_engine.py:326 / test_main_wiring.py:138 / test_corr_engine.py:288 / test_signal_state.py:564 / test_models.py:178 / test_corr_state.py:161 / test_stock_bars.py:468 / test_river_state.py:174 / verification.md:25 / :49 / :28 / :42 / diagnosis.md:34 / :37 / :5 / SKILL.md:43 / bench_02:109 / bench_06:94;reviewer 自報行號與重定位一致)
**React-doctor (2.97)**: N-A(非 React PR:F 無 .jsx / .tsx)
**Formal spec traceability (2.65)**: SKIPPED (C4_SPEC_NOT_IN_REPO)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、零輸出;`sem` 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer ×3 chunks)PASS(24 raw findings:A 7 / B 7 / C 10,合併 A5+B1 後 23;65/65 accounting;chunk B 另做 7 個突變體(A / E / F 存活、B / C1 / C2 / D / G 殺紅)+ 14 檔 589 passed 收工;chunk C 在 worktree 全量 pytest 3419 passed / 3 skipped + ruff 全綠 + 20 份 JSON 逐格核對)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 請求體 / 秘鑰讀取;`win_timer` 的 ctypes 是本機 Win32 呼叫無外部輸入)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 N-A(Codex 停用)→ 4.3b 主 session 逐條判斷 PASS(23/23 有 `why_others_might_miss` 解釋;三條自行實跑)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-251`
**worktree HEAD**: `541637ac0b499be1e8f1d1c0230499ccac8787cb`

**Report generation**: sha256:1a6fbfd16989c6ea464536892e8c483369dc7c967340f2eca5f9b76fa2a0c488

---
## [完整證據副檔](pr-251-review.audit.md)
### finding_uid 索引
[6231811d0225717cb371](pr-251-review.audit.md#發現總覽) · [18db288c77b2b9fd55e2](pr-251-review.audit.md#發現總覽) · [6f93a7143a8a495fcb27](pr-251-review.audit.md#發現總覽) · [f1911ce7b35dae195e64](pr-251-review.audit.md#發現總覽) · [15c67f50439d3b129875](pr-251-review.audit.md#發現總覽) · [bdbbf94146a354bf8a71](pr-251-review.audit.md#發現總覽) · [c39dc406307c6613d0e4](pr-251-review.audit.md#發現總覽) · [82e9157e007f681f88dc](pr-251-review.audit.md#發現總覽) · [298c8059ed42fd65fd84](pr-251-review.audit.md#發現總覽) · [705d62e2f6bce70bda5e](pr-251-review.audit.md#發現總覽) · [f309a752ad2d47d451a5](pr-251-review.audit.md#發現總覽) · [48690fc0e099e8eab76c](pr-251-review.audit.md#發現總覽) · [f25ad89723bac40b09bb](pr-251-review.audit.md#發現總覽) · [e91373c45543bbcd91cc](pr-251-review.audit.md#發現總覽) · [487c471e31715c58b533](pr-251-review.audit.md#發現總覽) · [9726852341044a8b9e55](pr-251-review.audit.md#發現總覽) · [5ec3515a77789f59c7d0](pr-251-review.audit.md#發現總覽) · [19ef3bff3da9b8ade22e](pr-251-review.audit.md#發現總覽) · [8cad6ffec083cd4bae0e](pr-251-review.audit.md#發現總覽) · [7f9e7f5cd0f4625c530d](pr-251-review.audit.md#發現總覽) · [71ef901ef81a59f2d53e](pr-251-review.audit.md#發現總覽) · [80a9cf4f208ad6febce8](pr-251-review.audit.md#發現總覽) · [a643c1625bcc56e5df46](pr-251-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸 4.3b) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `verification.md:25` 0-1 的「≤ 45 PASS」由 harness **假設的備妥分佈**決定:`exp` = 15 ms + Exp(5) 截 40,備妥 p50 ≈ 19.6 ms 恰落在新起點 20 ms 左邊 0.4 ms;同一支 harness 的 `--ready-dist uniform` 悲觀選項實跑 p50 **60.7 ms**(未達);committed 的 out_01 只有 exp 那份 | HIGH | CONFIRMED(主 session 稍早自己也跑出 uniform 60.7,§4 只講了 p90 沒講同一結構會翻 p50;「大幅改善」為真、「達標」未定;lone 解釋:JSON 有 `ready_dist` 欄但預設值看起來無害,要重跑另一分佈才看得到) | Should Fix | `ask-user` | 0-1 的驗收要改口徑:相對量(150 → 20–60)或等重啟後真數字;改 verification §2 那格是文件,但「算不算達標」是拍板 |
| F-02 | `verification.md:49` + PR body 試用指引 2:唯一的 0-1 真環境判準會**假 PASS** —— `server/overlay.py:47 OverlayCache` 是 per-(code, today) in-memory **無 TTL**,早上重啟、前端整天掛著 → 盤後跑 `bench_04_prod_overlay.py 150` 量到的是熱路徑(同腳本第 2 段基線 sub-ms),150 檔必然 ≪ 3 s,完全沒碰到 0-1 改的輪詢 | HIGH | CONFIRMED(主 session 實查 `OverlayCache` 只有 `__init__/get/put`,無 TTL / 無 monotonic;判準括號「重啟即冷」只在重啟當下成立,同一行又寫「盤後」;lone 解釋:要翻 OverlayCache 有沒有 TTL 才看得出衝突) | Should Fix | `ask-user` | 判準改成「重啟後**立刻**、前端先別開」或「要求第 3 段 p50 ≫ 第 2 段熱取基線,否則判無效」—— 兩種都是驗收設計,由 user 選 |
| F-03 | `__main__.py:151` `_set_switch_interval` 是純測試 seam,**沒有任何一條釘住它預設綁的是 `sys.setswitchinterval`**;chunk B 突變 A:改成 `lambda secs: None` → `test_main_wiring` 38 案全綠。且 `:168` INFO 印的是常數 `SWITCH_INTERVAL_SECS` 不是 `sys.getswitchinterval()`,盤後 grep 判準對同一失效樣態同時零訊號(A5 + B1 合併) | MEDIUM | CONFIRMED(突變體存活實證;spec seam 原文「原文字面 parity」被換成行為 spy,順序更強但丟了「接到真 API」那一半;lone 解釋:round-1 spec 軸核「釘 [timer_1ms, switchinterval 0.001] — 全符」字面確實符合,要注意被斷言的是替身鉤子本身) | Should Fix | `auto-fix` | 補 `assert main_mod._set_switch_interval is sys.setswitchinterval`(monkeypatch 前先存)+ INFO 改印 `sys.getswitchinterval()`;零 runtime 語意變化 |
| F-04 | `test_corr_engine.py:288` 0-4「沒人聽就不算」只釘了**不廣播**,沒釘**不算**:突變 F(先 `msg = self.state()` 再判 `has_clients`)49 案全綠、perf 目標歸零;突變 E(刪 `app.py:1009` 的 `has_clients=corr_ws.has_clients,`)tests/server 1597 案全綠 —— prod 是否接上零覆蓋(閘退回 None = 舊語意,毫無異狀) | MEDIUM | CONFIRMED(兩個存活突變體實證;docstring「不呼叫 broadcast(也就不算)」括號那句是推論不是斷言;lone 解釋:`sent == []` 讀起來就是「沒算也沒送」) | Should Fix | `auto-fix` | (a) 該案 spy `eng._state.correlations` 計數斷無 client 時 0 次;(b) `test_main_wiring` / app 佈線測試斷 corr 引擎 `_has_clients is corr_ws.has_clients` |
| F-05 | `corr_state.py:66` `_legs` 未去重:舊版逐 leg 重算時重複 key 只是覆寫同一列(冪等),新版 `push` 對同一 `self._pairs[leg][w]` append 兩次 → 主 session 實跑 `CorrState(['TXF','NQ','NQ'],'TXF',windows=(60,))` push 10 筆 **n60 = 18**(舊語意 9);`min_samples` 提早一半達成、前端 n 加倍、r 不變 → 零錯誤訊號;`corr_config` 只驗 base 在腿裡不驗 key 唯一 | MEDIUM | CONFIRMED(實跑重現;現行 `configs/correlation.json` 11 腿 key 唯一 → 今天不觸發,是防禦缺口不是現行 bug;lone 解釋:新測試全用互異腿名,「重掃 → 增量」最典型的隱性前提是舊碼天然冪等) | Should Fix | `auto-fix` | `self._legs = [k for k in dict.fromkeys(leg_keys) if k != base]` + `corr_config` 對重複 key WARNING;加一條重複腿名 n 不加倍的測試 |
| F-06 | `win_timer.py:50` / `__main__.py:166` 只查回傳值不接例外:`WinDLL("winmm")` 載入失敗(`OSError`)或匯出不存在(ctypes `AttributeError`)會穿出 `main()`,在 `create_app` 之前掛掉;spec 0-3 與檔頭 / `__main__` 註解三處都寫「任一失敗 WARNING **不炸啟動**」 | MEDIUM | CONFIRMED 機制、**LOW 影響**(主 session `grep try/except win_timer.py` 零命中;但 Windows 11 上 kernel32 / winmm 恆可載、兩個匯出自 Win8 恆在,例外路徑實務上不可達 —— 6d-1 假設性措辭 cap:維持 Should 不升;lone 解釋:回傳值檢查做得很仔細,reviewer 會覺得失敗處理已完整) | Should Fix | `auto-fix` | `qos_fn()` / `tbp_fn()` 各包 `except (OSError, AttributeError)` → WARNING + 視為失敗;`test_win_timer` 補 qos 拋例外仍回 False 一案 |
| F-07 | `test_signal_state.py:564` 「10 萬次隨機」實際只有 **18.7%** 真的推進狀態:時距 `(0, 0.1, 1, 5, 120, 400)` 平均 87.7 s,100k 筆把假鐘推到 2026-11-13,`evaluate` 第一道 `_in_session` 早退;窗長 max 13、眾數 0–2,`while` 多筆 popleft 路徑幾乎沒走,docstring 自引的「窗 3000 筆」情境從沒驗過 | MEDIUM | CONFIRMED(chunk B 自寫探針計數:99,724 次 evaluate 只 18,656 次進入;強度與宣稱不符,0.47 s 八成空轉;lone 解釋:`_in_session` 早退在 `evaluate` 第一行、離測試很遠,10 萬這數字本身很有說服力) | Should Fix | `auto-fix` | 時距改盤中尺度 `(0, 0.1, 1, 5)` + 每 N 筆顯式 `reset_day` 拉回 09:30;斷言 `max(len(window))` 曾達某下界 |
| F-08 | `diagnosis.md:34` 決定拍板形狀的那一項量測(0-7 不套 timer 時 58.0 / 58.2 零差異、p99 292 → 356)**沒有 artifact**:`bench_07` 無任何 `out_*.json`,`run_all_benches.py` 的 RUNS 不含它,全 repo 搜不到 58.0 / 292 / 356 第二處;十項裡唯一「有結論無證據」 | MEDIUM | CONFIRMED(主 session 確認 evidence 目錄無 out_*07;`out_bench_03_base_4thr` 46 ms 是另一把尺(sleep 0.05 / 60 s),不是同一件事的證據;lone 解釋:§5 把 bench_07 列進「harness 十支」,缺的是輸出不是腳本) | Should Fix | `auto-fix` | 補跑兩輪落 `out_bench_07_{base,timer1ms}.json`(prod-like + timer_1ms 各一),或 §2 標「未存檔 + 重跑指令」 |
| F-09 | `SKILL.md:43` 長效教訓檔三處與本批實作 / 證據對不上:(a)「9 ms → 0.07 ms(208x)」內部不自洽(129x),且 0.07 是收修前值、本批 JSON 9.0414 → 0.061(148x);(b)「32,400 push 3.9e-15」是 T2 舊量,repo 現釘 16,200 push → 3.0e-14,照 skill 訂容差會小一個數量級 → 未來 flaky;(c)「變異下限」正是 round-1 J2 判 Mysterious Name、已改 `_SS_FLOOR`(中心化**平方和**未除 n)的舊說法,照 skill 用變異配 1e-18 會差 n 倍 | MEDIUM | CONFIRMED(逐句對 `corr_state.py:19-22` 與 `out_after_04.json`;J2 收修只動 corr_state 檔頭,round-1 Standards 合規句「backend-conventions §8 改寫對得上實作」是收修**前**寫的;lone 解釋:reviewer 核合規時 SKILL 與實作當時的確一致,是後續收修讓它們分岔) | Should Fix | `auto-fix` | 三處改寫:0.061 ms(148x)/ 16,200 push 3.0e-14 容差 1e-9 / 「中心化平方和 `_SS_FLOOR`,未除 n」 |
| F-10 | `corr_state.py:213` `_corr` 以**位置解包** `sx, sy, sxx, syy, sxy = s`,與 `_add`/`_sub` 的 `_SX…_SXY` 具名索引不同源;把 `range()` 版面的 Σxx / Σyy 換位不會紅(vx / vy 對調,r 仍有限落 [-1,1]) | LOW | CONFIRMED(round-1 J3 收修只改了 `_add`/`_sub`;lone 解釋:reviewer 當「具名索引」已收斂不逐一比對三個函式) | Nice to Have | `auto-fix` | `_corr` 改 `s[_SX], s[_SY], …` |
| F-11 | `signal_state.py:392` 寫路徑 `self._window_vol.get(code, 0) + tick.qty`:讀路徑 `:739` 已改嚴格索引並註明「漏維護要炸開」,寫路徑仍先以 0 補回缺項,之後 popleft 減整窗舊量 → 值可能變負;走到此行時 `code in self._prev` 必成立,嚴格索引安全 | LOW | CONFIRMED(`grep _window_vol` 七處逐一對;round-1 J6 只收了讀路徑那半;lone 解釋:讀路徑註解寫得很強,讀者不會回頭看四行之上的寫路徑) | Nice to Have | `auto-fix` | 改 `self._window_vol[code] + tick.qty` |
| F-12 | `river_backfill.py:31` `_POLL_BACKOFF_START` 兩份同值常數,註解宣告「與 tc4 同一把」但零機械保證:單邊調值兩邊測試都綠 | LOW | CONFIRMED(`grep -rn _POLL_BACKOFF_START copycat/ tests/` 定義兩處、無互引無 parity;CLAUDE.md §4 對跨檔常數慣例是 parity 測試;lone 解釋:既有碼本來就是兩份 0.15,看起來是沿用現況) | Nice to Have | `auto-fix` | `from copycat.live.tc4 import _POLL_BACKOFF_START` 或一條 parity assert |
| F-13 | `corr_engine.py:326` `has_clients` 讓「整天不呼叫 `correlations()`」成常態,而 `correlations()` 改成破壞性逐出後是唯一逐出短窗 deque 的地方 → 無 client 時 60 / 300 窗 deque 只靠 `push` 的 floor 逐出封頂到最長窗上界;正確性靠時間逐出自癒,但「無 client 數小時後首次連線 n{w} 仍正確」與記憶體上界零測試(新 parity 測試最長只跨 100 push 不呼叫) | LOW | CONFIRMED 機制(上界 = 11 腿 × 3 窗 × ~1800 筆 tuple,約數 MB,不是洩漏;lone 解釋:閘看起來只影響「算不算」,要把它和「`correlations` 從純函式變狀態機」疊在一起看才浮出來) | Nice to Have | `auto-fix` | `test_corr_state.py` 補「連續 push 16,200 次零 `correlations`,最後一次 n{w} 與參考相等」 |
| F-14 | `test_models.py:178` 巢狀欄位守門檢查的是**實例值**:將來加 `detail: Sub 或 None = None`,實例值 None → 兩條斷言都綠,而 route 的 `__dict__` 與 `asdict` 在該欄被填值時分岐;docstring 宣稱「加巢狀欄位這條先紅」對 `= None` 不成立 | LOW | CONFIRMED(值檢查 vs 型別檢查;lone 解釋:兩條斷言寫得很像型別檢查) | Nice to Have | `auto-fix` | 改掃 `dataclasses.fields(type(record))` 的 `f.type` 字面白名單純量 |
| F-15 | `test_corr_state.py:161` 全日對照 docstring 宣稱「洞 + 相鄰判定全部走真實路徑」,但 `ts += 1.0` 固定、base 腿恆有值 → 相鄰判定從沒被拒絕、「洞」只走到腿側 None 那一種;reference 本身**獨立**(自維護中價序列 + 重掃 + 兩遍式 `_pearson`)非自證,n=1800 上比閉式更穩,當參考合格 | LOW | CONFIRMED(chunk B 突變 C2 證新案有增量價值:既有 15 案只 1 條跟著紅、新案 3 條紅;純 docstring 過度宣稱) | Nice to Have | `auto-fix` | docstring 改「腿側缺值 + 窗邊界」,或讓 ts 偶爾 +2 / base 偶爾 None |
| F-16 | `test_stock_bars.py:468` 既有斷言 `<= 20.0` 放寬成 `<= 20.0 + 1e-9`:實測必要且無害(突變 D 還原 → 紅,實值 20.000000000000004),但 CLAUDE.md §C 只允許「事前標為該變」的既有 assertion 被改,spec #240 只預告了 1-1 那 25 條;更誠實的寫法 `== pytest.approx(20.0, abs=1e-9)`(「兩輪各用滿 10 s 預算」) | LOW | CONFIRMED(尾差 4e-15 與 commit 訊息一致;程序面欠一則 issue 補記;lone 解釋:行內註解寫得清楚,容易直接接受) | Nice to Have | `auto-fix` | #240 補記一則 + 改 `pytest.approx` |
| F-17 | `test_river_state.py:174` 為一行 helper 加 `# noqa: E731`(本檔唯一 noqa);`def dumps(o) -> str:` 兩行即可 | LOW | CONFIRMED(純風格) | Nice to Have | `auto-fix` | 改 def |
| F-18 | `diagnosis.md:37` 1-1 的「目標」欄寫「in-memory 鍵型別 `str`」,與實作(`river_state.py:164` 註解)、白名單、`out_after_11.json`(`in_memory_minute_key_types = ["int"]`)相反;拿 diagnosis 對帳會判 1-1 未達成 | LOW | CONFIRMED(check_11 欄名收修了、diagnosis 這格沒跟;lone 解釋:欄名本來就標錯過一次) | Nice to Have | `auto-fix` | 改「snapshot(wire 前)鍵 str、in-memory 不動」 |
| F-19 | `bench_02_eval_volume.py:109` `--all` 自稱「整體」但少 `sweep_cluster` / `vol_breakout` 兩種最重的 kind(`signal_state.py:96-99` 七鍵);committed 數字是 vol_burst-only 沒被污染,但 §2 的 0-2 列沒寫「只開 vol_burst」,4.3 µs 易被讀成 prod 每 tick evaluate 成本 | LOW | CONFIRMED(harness docstring 自述「另加四種」與 KIND_SWITCH 七鍵不符;lone 解釋:committed JSON 不受影響,要看 `--all` 路徑才發現) | Nice to Have | `auto-fix` | 從 `KIND_SWITCH` 取全集;§2 該格加「只開 vol_burst」 |
| F-20 | `diagnosis.md:5` §1 baseline 不是 committed 那輪且沒存檔:逐格對 river 150.3(JSON 150.4)、0-2 13.2/89.9/287.5(12.9/89.7/286.3)、0-5 205.9(207.0)、0-6 orders 1328(1345.7)、0-4 push 0.005 vs **0.0084**;bench_01 寫 `--n 30`、committed 是 `--n 60`;「同一把尺」字面不成立 | LOW | CONFIRMED(方向不變,可回溯性缺;lone 解釋:數字同量級,不逐格對不會發現) | Nice to Have | `auto-fix` | §1 標「首輪(未存檔),正式 before = out_before_*.json」 |
| F-21 | `verification.md:28` 0-3 判準主詞含混:「p50 全程 < 1 且 ≤ 0.6」但 `per_10s_p50[3] = 0.622` 超過 0.6(同格又寫 0.50–0.62);全程 p50 0.57 才達標,逐 10 s 桶 vs 全程要寫死一個 | LOW | CONFIRMED(JSON per10s 0.503–0.622) | Nice to Have | `auto-fix` | 判準寫成「全程 p50 ≤ 0.6 且每 10 s 桶 < 1 ms」 |
| F-22 | `verification.md:42` 同檔數字互斥:§1 最終 210 s vs §2「218 → 214 s」;§4 的 0-5「212 → 155」與 §2 表「207.0 → 148.2」是兩輪只有後者有 JSON;「corr push 0.005 → 0.037 ms(合計仍 135x)」沿用舊輪(JSON 0.0084 → 0.0345,148x) | LOW | CONFIRMED(summarize_benches 實跑輸出對照) | Nice to Have | `auto-fix` | 統一引 committed JSON 那一輪 |
| F-23 | `bench_06_asdict.py:94` SimpleNamespace 直呼 coroutine 只量 route body:FastAPI response 編碼 / 驗證不在內;`asdict → __dict__` 的**差值**有效,但「positions ≤ 100 µs」不等於端點總成本(§2「µs/await」措辭救了一半) | LOW | PARTIAL(量法對差值有效、對絕對值不代表端點;T1 §9 原始量法也是 route 規模推導式,本 harness 沿同口徑;lone 解釋:before/after 同尺,差值信賴度不受影響) | 參考用 | `no-op` | 不是缺陷;§2 已標 µs/await;要端點總成本另用 TestClient 量 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 6231811d0225717cb371 action=ask-user
F-02 finding_uid: 18db288c77b2b9fd55e2 action=ask-user
F-03 finding_uid: 6f93a7143a8a495fcb27 action=auto-fix
F-04 finding_uid: f1911ce7b35dae195e64 action=auto-fix
F-05 finding_uid: 15c67f50439d3b129875 action=auto-fix
F-06 finding_uid: bdbbf94146a354bf8a71 action=auto-fix
F-07 finding_uid: c39dc406307c6613d0e4 action=auto-fix
F-08 finding_uid: 82e9157e007f681f88dc action=auto-fix
F-09 finding_uid: 298c8059ed42fd65fd84 action=auto-fix
F-10 finding_uid: 705d62e2f6bce70bda5e action=auto-fix
F-11 finding_uid: f309a752ad2d47d451a5 action=auto-fix
F-12 finding_uid: 48690fc0e099e8eab76c action=auto-fix
F-13 finding_uid: f25ad89723bac40b09bb action=auto-fix
F-14 finding_uid: e91373c45543bbcd91cc action=auto-fix
F-15 finding_uid: 487c471e31715c58b533 action=auto-fix
F-16 finding_uid: 9726852341044a8b9e55 action=auto-fix
F-17 finding_uid: 5ec3515a77789f59c7d0 action=auto-fix
F-18 finding_uid: 19ef3bff3da9b8ade22e action=auto-fix
F-19 finding_uid: 8cad6ffec083cd4bae0e action=auto-fix
F-20 finding_uid: 7f9e7f5cd0f4625c530d action=auto-fix
F-21 finding_uid: 71ef901ef81a59f2d53e action=auto-fix
F-22 finding_uid: 80a9cf4f208ad6febce8 action=auto-fix
F-23 finding_uid: a643c1625bcc56e5df46 action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 0-1 的「達標」是 harness 假設的分佈給的,換悲觀分佈就 60 ms
**File**: `.claude/perf/batch-b-tier0/verification.md`
**Line**: 25

**Comment**:
```
這格的 20.6 ms 是在「TC4 首頁 15 ms + Exp(5 ms) 備妥」這個假設下量的,備妥 p50 ≈ 19.6 ms,
剛好比新起點 20 ms 早 0.4 ms。同一支 harness 換 --ready-dist uniform(15–40 均勻)跑,
p50 直接變 60.7 ms(首輪落空 → 第二輪 20+40)。
150 → 20~60 這個「大幅改善」在任何分佈下都成立,「≤ 45 達標」沒有。
建議這格改寫成相對量(或標「exp 20.6 / uniform 60.7」兩個都列),真數字等重啟後量。
```
#### #2 重啟後那條判準會假 PASS,因為 OverlayCache 沒 TTL
**File**: `.claude/perf/batch-b-tier0/verification.md`
**Line**: 49

**Comment**:
```
server/overlay.py 的 OverlayCache 是 per-(code, today) in-memory、沒有 TTL。
早上重啟、前端整天開著 → 自選那批到盤後早就全 hit;這時跑 bench_04_prod_overlay.py 150
量到的是熱路徑(腳本自己第 2 段的基線就 sub-ms),150 檔一定 ≪ 3 s,完全沒碰到 0-1 改的輪詢。
判準要嘛寫「重啟後立刻跑、前端先別開」,要嘛要求第 3 段 p50 明顯高於第 2 段熱取基線,
不然就判無效。
```
#### #3 0-7 沒有任何測試釘住「真的接到 sys.setswitchinterval」,log 也只印常數
**File**: `copycat/server/__main__.py`
**Line**: 151

**Comment**:
```
_set_switch_interval 是給佈線測試換替身用的模組屬性,但沒有一條測試斷它預設就是
sys.setswitchinterval —— 改成 lambda secs: None,test_main_wiring 38 案照綠(突變實跑)。
盤後那行 INFO 印的又是常數 SWITCH_INTERVAL_SECS,不是 sys.getswitchinterval(),
所以 grep 判準對這個失效樣態也是零訊號。
補兩件:test 加 assert main_mod._set_switch_interval is sys.setswitchinterval(monkeypatch 前先存);
INFO 改印 sys.getswitchinterval()。
```
#### #4 「沒人聽就不算」只釘了不廣播,沒釘不算;prod 有沒有接上也沒人釘
**File**: `tests/server/test_corr_engine.py`
**Line**: 288

**Comment**:
```
sent == [] 只證明沒送。把 tick_once 改成先 msg = self.state() 再判 has_clients 才送,
語意一樣、49 案全綠,但 0-4 想省的那 9 ms 就整個回來了(突變實跑)。
另一半:把 app.py 那行 has_clients=corr_ws.has_clients 刪掉,tests/server 1597 案全綠 ——
閘退回 None 就是舊語意,畫面零異狀。
補:(a) 這案用 spy 包 eng._state.correlations,斷無 client 時呼叫 0 次;
(b) 佈線測試斷 corr 引擎的 _has_clients is corr_ws.has_clients。
```
#### #5 腿名重複時 n{w} 會加倍,舊版不會
**File**: `copycat/live/corr_state.py`
**Line**: 66

**Comment**:
```
_legs 沒去重。舊版 correlations 逐 leg 重算,重複 key 只是把同一列覆寫回去(冪等);
新版 push 的 for leg in self._legs 會對同一個 _pairs[leg][w] append 兩次。
實跑 CorrState(['TXF','NQ','NQ'],'TXF',windows=(60,)) push 10 筆:n60 = 18(舊語意 9)。
r 不變、只有 n 加倍 → min_samples 提早一半達成、前端 n 顯示錯,零錯誤訊號。
今天 configs/correlation.json 11 腿 key 唯一,所以沒發作;但 corr_config 只驗 base 在腿裡。
改 self._legs = [k for k in dict.fromkeys(leg_keys) if k != base],corr_config 對重複 key 印 WARNING。
```
#### #6 「不炸啟動」只擋了回傳值失敗,例外會穿出 main
**File**: `copycat/server/win_timer.py`
**Line**: 50

**Comment**:
```
apply_timer_1ms 兩個回傳值都查了,但 WinDLL("winmm") 載入失敗(OSError)或匯出不存在
(ctypes 的 AttributeError)會直接穿出 main(),在 create_app 之前掛掉;
spec / 檔頭 / __main__ 註解三處都寫「任一失敗 WARNING 不炸啟動」。
Windows 11 上這兩條實務上不可達(kernel32 / winmm 恆可載、匯出自 Win8 恆在),
所以只是把承諾補齊:qos_fn() / tbp_fn() 各包 except (OSError, AttributeError) → WARNING + 視為失敗,
test_win_timer 加一案 qos 拋例外仍回 False。
```
#### #7 「10 萬次隨機」只有 18.7% 真的跑進狀態機,窗最深才 13 筆
**File**: `tests/live/test_signal_state.py`
**Line**: 564

**Comment**:
```
時距 (0, 0.1, 1, 5, 120, 400) 平均 87.7 s,10 萬筆把假鐘從 08-04 09:30 推到 11-13,
evaluate 第一行 _in_session 就早退 —— 探針實測 99,724 次 evaluate 只有 18,656 次真的推進,
窗長 max 13、眾數 0–2。docstring 自己引的「窗 3000 筆」情境從沒驗過,while 多筆 popleft 幾乎沒走。
時距改 (0, 0.1, 1, 5) + 每 N 筆顯式 reset_day 把時鐘拉回 09:30,
再斷 max(len(window)) 曾達到某個下界,讓「窗真的深過」變成可檢查的事實。
```
#### #8 決定 0-3 / 0-7 綁在一起的那項量測沒存 artifact
**File**: `.claude/perf/batch-b-tier0/diagnosis.md`
**Line**: 34

**Comment**:
```
「不套 timer 時 0.001 / 0.005 都 58 ms 零差異、p99 反而 292 → 356」是整批唯一推翻主文件、
決定 0-7 必須排在 0-3 之後並接受吞吐 −7.6% 的量測,但 evidence/ 沒有任何 out_*07.json,
run_all_benches.py 的 RUNS 也不含 bench_07;out_bench_03_base_4thr 的 46 ms 是另一把尺。
補跑兩輪(prod-like / --timer-1ms)落 out_bench_07_*.json,或在 §2 標「未存檔 + 重跑指令」。
```
#### #9 教訓檔那條三個數字 / 名詞已經跟實作對不上
**File**: `.claude/skills/backend-conventions/SKILL.md`
**Line**: 43

**Comment**:
```
(a) 「9 ms → 0.07 ms(208x)」自己就不自洽(129x);0.07 是收修前的值,現在 JSON 是 9.04 → 0.061(148x)。
(b) 「32,400 push 3.9e-15」是 T2 舊量,repo 現在釘的是 16,200 push → 3.0e-14、容差 1e-9;
照 skill 訂容差會小一個數量級,將來 flaky。
(c) 「常數序列以變異下限判」是 round-1 J2 已改掉的說法,實作是 _SS_FLOOR 中心化平方和(未除 n),
照 skill 用變異配 1e-18 會差 n 倍。
三處改寫成現值就好;這是長效教訓檔,錯的數字會被下一批直接引用。
```
#### #10 `_corr` 還是位置解包,跟 `_add`/`_sub` 的具名索引不同源
**File**: `copycat/live/corr_state.py`
**Line**: 213

**Comment**:
```
round-1 把 _add / _sub 改成 _SX…_SXY 具名索引,_corr 這行 sx, sy, sxx, syy, sxy = s 沒跟。
把 range() 版面的 Σxx / Σyy 換位不會紅(vx / vy 對調,r 仍有限落 [-1,1]),相關係數靜默算錯。
改成 s[_SX], s[_SY], s[_SXX], s[_SYY], s[_SXY]。
```
#### #11 寫路徑的 `.get(code, 0)` 把讀路徑那句「漏維護要炸開」抵銷掉了
**File**: `copycat/live/signal_state.py`
**Line**: 392

**Comment**:
```
_eval_volume 那邊改成嚴格索引並註明「四處維護漏一處要炸開」,但這裡先用 .get(code, 0) 把缺項補回 0,
之後 popleft 減掉整窗舊量 → 值變負,症狀是爆量比率低估而不是 KeyError,守門測試抓不到。
走到這行時 code in self._prev 必成立、_window_vol[code] 一定在,直接 self._window_vol[code] + tick.qty。
```
#### #12 兩份 `_POLL_BACKOFF_START` 只靠註解說「同一把」
**File**: `copycat/live/river_backfill.py`
**Line**: 31

**Comment**:
```
tc4.py 與這裡各一份 0.02、各自測試各自釘;單邊調值兩邊都綠,註解就變假的。
專案對跨檔常數的慣例(CLAUDE.md §4)是 parity 測試 —— 要嘛 from copycat.live.tc4 import _POLL_BACKOFF_START,
要嘛加一條 assert 兩邊相等。
```
#### #13 沒 client 時 correlations 整天不會被呼叫,這個新常態沒有守門
**File**: `copycat/server/corr_engine.py`
**Line**: 326

**Comment**:
```
correlations() 現在是唯一逐出短窗 deque 的地方(破壞性逐出),has_clients 閘讓它可能整天不被呼叫。
正確性靠 push 的 floor 逐出自癒,60 / 300 窗最多長到最長窗上界(11 腿 × 3 窗 × ~1800 筆,幾 MB,不是洩漏),
但「無 client 數小時後首次連線 n{w} 仍正確」沒有測試,parity 案最長只跨 100 push 不呼叫。
test_corr_state 補一案:連續 push 16,200 次、期間零 correlations,最後一次 n{w} 與參考相等。
```
#### #14 巢狀欄位守門對「optional 巢狀欄 = None」看不見
**File**: `tests/capital/test_models.py`
**Line**: 178

**Comment**:
```
兩條斷言查的是這三顆實例當下的值。將來加 detail: Sub | None = None,實例值是 None → 都綠,
route 的 __dict__ 與 asdict 在該欄被填值時就分岐。
改掃 dataclasses.fields(type(record)) 的 f.type 字面(from __future__ import annotations 下是字串),
白名單純量型別名。
```
#### #15 全日對照的 docstring 說走了「洞 + 相鄰判定」,其實一半沒走到
**File**: `tests/live/test_corr_state.py`
**Line**: 161

**Comment**:
```
ts += 1.0 固定、base 腿恆有值 → 相鄰判定從沒被拒絕,「洞」只走到腿側 None 那一種。
reference 本身是獨立重寫(自維護序列 + 兩遍式 Pearson),不是自證,當參考合格;
只是 docstring 過度宣稱。改寫成「腿側缺值 + 窗邊界」,或讓 ts 偶爾 +2、base 偶爾 None。
```
#### #16 既有斷言放寬了,但 spec 沒事前標「該變」
**File**: `tests/live/test_stock_bars.py`
**Line**: 468

**Comment**:
```
<= 20.0 + 1e-9 是必要的(還原 → 紅,實值 20.000000000000004),但 CLAUDE.md §C 只允許事前標為該變的既有 assertion 被改,
spec #240 只預告了 1-1 那 25 條。照 0-4 的先例在 #240 補一則留言;
另外 == pytest.approx(20.0, abs=1e-9) 比 ≤ 20+ε 更貼近它想守的「兩輪各用滿 10 s 預算」。
```
#### #17 一行 helper 用了 noqa
**File**: `tests/live/test_river_state.py`
**Line**: 174

**Comment**:
```
本檔唯一一處 noqa。def dumps(o: object) -> str: 兩行就好,不必關 E731。
```
#### #18 diagnosis 的 1-1 目標欄跟交付物相反
**File**: `.claude/perf/batch-b-tier0/diagnosis.md`
**Line**: 37

**Comment**:
```
這格寫「in-memory 鍵型別 str」,但實作、白名單、out_after_11.json 都是 in-memory 仍 int、
snapshot(wire 前)才轉 str。拿 diagnosis 對帳會判 1-1 沒做到。改成「snapshot 鍵 str、in-memory 不動」。
```
#### #19 `--all` 少了兩種最重的 kind
**File**: `.claude/perf/batch-b-tier0/evidence/bench_02_eval_volume.py`
**Line**: 109

**Comment**:
```
signal_state 的 KIND_SWITCH 現在七鍵,這裡漏 sweep_cluster / vol_breakout;committed 數字是 vol_burst-only 沒被污染,
但日後照 docstring 跑「整體」會系統性低估。直接從 KIND_SWITCH 取全集;
verification §2 的 0-2 列也補一句「只開 vol_burst」,4.3 µs 才不會被讀成 prod 每 tick evaluate 成本。
```
#### #20 diagnosis §1 的 baseline 是沒存檔的那一輪
**File**: `.claude/perf/batch-b-tier0/diagnosis.md`
**Line**: 5

**Comment**:
```
逐格對:river 150.3(JSON 150.4)、0-2 13.2/89.9/287.5(12.9/89.7/286.3)、0-5 205.9(207.0)、
0-6 orders 1328(1345.7)、0-4 push 0.005 vs 0.0084;bench_01 寫 --n 30、committed 是 --n 60。
方向都對,但「同一把尺」字面不成立且那輪沒有 out 檔。§1 標「首輪(未存檔),正式 before = out_before_*.json」。
```
#### #21 0-3 的判準主詞含混
**File**: `.claude/perf/batch-b-tier0/verification.md`
**Line**: 28

**Comment**:
```
「p50 全程 < 1 且 ≤ 0.6」—— per_10s_p50[3] = 0.622 超過 0.6,同格又寫 0.50–0.62;全程 p50 0.57 才達標。
寫死一個:「全程 p50 ≤ 0.6 且每 10 s 桶 < 1 ms」。
```
#### #22 同一份 verification 有三組互斥數字
**File**: `.claude/perf/batch-b-tier0/verification.md`
**Line**: 42

**Comment**:
```
§1 最終 210 s vs §2「218 → 214 s」;§4 的 0-5「212 → 155」與 §2 表「207.0 → 148.2」是兩輪、只有後者有 JSON;
「corr push 0.005 → 0.037 ms(合計仍 135x)」是舊輪,JSON 是 0.0084 → 0.0345(148x)。統一引 committed 那一輪。
```
