# PR #133 Code Review 比較報告 · SHA f95441d1
**Report projection schema**: 1

**PR**: [loger-w/copycat#133](https://github.com/loger-w/copycat/pull/133)
**標題**: mod: 期貨 tab 分時圖改 15:00 夜盤起算的一天(錨定日 = 期交所口徑、05:00→08:45 空檔畫水平線)
**作者**: loger-w(commits 署名 Loger)
**分支**: `mod/futures-day-1500` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 a32c5cc4;回溯 review)
**變更**: 21 檔案, +1053 / -342(含 1 張 binary 截圖)
**審查日期**: 2026-08-28
**Review input basis**: source repo R_kgDOTsITBg + f95441d1beb4a82fb2bbdb9fee7dd278931f281d;destination repo R_kgDOTsITBg + c80dbde5113c9743b443bd348b94a6258eece41f;`input_binding: verified`(`git fetch refs/pull/133/head` 後 FETCH_HEAD 與 headRefOid 逐字相等、worktree HEAD = source SHA;destination SHA 以精確 commit 綁定(`git rev-parse --verify c80dbde5…^{commit}` 成立),不用已前進的 `origin/master` 分支 ref)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED、分支已刪);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-133`(detached)
**worktree HEAD**: f95441d1beb4a82fb2bbdb9fee7dd278931f281d
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 主 agent 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=typescript-reviewer ×2(chunked 兩塊並行;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=21 → covered 11 / no-issues 9 / skipped 1 / **missed 0**(chunked: 是;FILE_COUNT=14 源檔 ≤ 15 但 DIFF_LINES=1154 源檔行 > 800 → 依路徑排序切兩塊:chunk 1 = 6 檔 / 821 行(allday ×2、FuturesChart ×2、StockIntradayChart ×2),chunk 2 = 8 源檔 / 333 行 + 7 非源檔(CONTEXT / next-time / 5 個 artifacts);兩塊 accounting 6 + 15 = 21,union = F;skipped 1 = `evidence/SC-13_night_session_2026-08-28_0021.jpg` binary)
**定位 (ENH-B)**: anchored exact 12 / ambiguous 1 / **FAILED 0**(全部 anchor 於 worktree HEAD 以逐字比中;F-12 anchor `const dm = dayMinuteOf(b);` 命中 :76 / :85 兩處,取 reviewer 報的 74–86 區間內最近的 :76;F-14 anchor `<none>`(commit 訊息層),不計)
**React-doctor (2.97)**: 未引入新問題(既有 2 條不計)—— `npx react-doctor@latest --offline --no-score --scope changed --base c80dbde5 --json` 於 worktree `frontend/` 實跑:`newCount 0 / fixedCount 0 / baseTotalCount 2`,changedFileCount 14
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,21 檔全部 authored)
**審查軸狀態**: primary(typescript-reviewer chunk 1)PASS(4 findings、6/6 accounting、8 條 PR 自我宣稱逐條核對);primary(typescript-reviewer chunk 2)PASS(9 findings、15/15 accounting、round-1 disposition 六條 + commit 慣例核對);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條實查,見備註欄;14 條 CONFIRMED 13 / REFUTED 1)/ 4.5 PASS(missed 0)/ 4.6 PASS;React-doctor PASS(新引入 0)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus)回 R1–R10 全 PASS、`VERDICT: COMPLIANT`;無需補寫

**Report generation**: sha256:5bb3aa59b49d212c5d4cf1f6639ca001da5caafca8808a628713515c1408e74e

---

## Spec 依據

- 偵測到 `.claude/mod/futures-day-1500/change-spec.md`(§0 目標一句話、§1「錨定日」名詞、§2 SC-1~SC-13、§3 白名單 W12/W13、§4 grilling 兩輪 + Q9 拍板 (a) 水平橋只在日盤第一筆到了才補、§5 三類 commit 順序、§6 取捨:假設每個交易日都有夜盤 / 日曆未載入退化 / 橋是視覺格)+ `current-state.md`(現況 vs 目標表、caller map、白名單 W1–W11:後端 / 輪詢窗 / corr 閘 / 分 K 日 K / 個股頁疊線行為零變)。非目標明列:後端 `FUTURES_ALLDAY_DOMAIN` / `build_minute` cache / route、`inFuturesAllDayHours`、corr 腿自癒閘、江波圖與相關係數時間軸、分 K 與日 K 模式。
- ⚠️ spec 作者 = PR 作者(change-spec / current-state 由同一 session 同 agent 產出;grilling 拍板由 user 逐題回覆)。本輪 F-01 / F-02 / F-05 正是 spec / 白名單自寫、自實作、自驗的漏 —— 收修(P5)改了簽名,白名單 W12 與 W1 沒跟著回校。
- `SPEC_COMPLIANCE` receipt:gate=SKIPPED;dispatch=NOT_APPLICABLE;dispatch_count=0;reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED(reducer `resolve-authority` 以 `PYTHONUTF8=1 py -3.14` 實跑,候選 = change-spec.md:29 SC-7「只有夜盤側(日盤未開)→ 不補,線停在 05:00」INVARIANT;spec 位於 `.claude/mod/<slug>/`,不在 `openspec/specs/**` / `openspec/changes/**` 允許路徑;首兩次 `C4_CLI_INPUT_INVALID` 為 Windows cp950 stdin 解碼問題,非 reducer 判定);requested_model=opus;observed_model=UNAVAILABLE;effort=xhigh;tools=0;0 clauses / 0 findings / 0 observations / 0 invalidated

## 變更概要

provenance:21 authored / 0 inherited(base = master,免驗)。

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `frontend/src/lib/allday.ts` | 無 finding(修改) | 核心:四段近全軸(1501–2359 / 0000–0500 / 空檔 0501–0845 `tradable:false` / 0846–1345,軸長 1365)、`ALLDAY_GAP`、`anchorDateOf` 期交所口徑(夜盤 → 次一交易日,吃 `nextTradingDayIso`)、`sliceCurrentAllday` 改「錨定日 == 末根」、九顆刻度重排、新 `alldayBarsBetween`、`anchorClassOf` 三分類單一來源;reviewer 核過新依賴單向無循環、壞時刻落 `"d"` 與舊 `isFinite` 早退同結果 |
| `frontend/src/lib/allday.test.ts` | 無 finding(修改) | 36 案重寫:索引字面、刻度整表寫死、互逆掃描以 `ALLDAY_GAP` 分流、假日 / 顯式集合 / 週末 (a)(b) / 翻頁 |
| `frontend/src/lib/trading-calendar.ts` | 無 finding(修改) | 新 `nextTradingDayIso`(30 步護欄)/ `shiftIso`(UTC 進位、Invalid Date 原樣回傳);`isTradingDayIso` module-private |
| `frontend/src/lib/trading-calendar.test.ts` | 無 finding(修改) | 16 案:跳週末 / 假日 / 跨年 / 30 步 / garbage 不炸 / 顯式集合優先 |
| `frontend/src/lib/futures-accum-adapter.ts` | 有 finding(修改) | 空檔水平橋:夜盤側 + 日盤側都有格時於 `ALLDAY_GAP.end` 補一格 v=0 / h,l=null;Σ 與 high-low 以 key 位置認橋跳過(F-11) |
| `frontend/src/lib/futures-accum-adapter.test.ts` | 無 finding(修改) | 22 案:fixture 改夜盤、橋節四條(兩側 / 只夜 / 只日 / live 佔位算日盤側)、1064 字面 |
| `frontend/src/components/futures/FuturesChart.tsx` | 有 finding(修改) | `useQuery(calendarQueryOptions)` 當 slice / anchorDate / fills memo dep;`holidaySet` 穿到 `liveSlotOf` / `tradeSlotOf` / `alldayFillPoints`(F-10);gate 5 改 `alldayBarsBetween`;gate 1–4 判準逐字不動 |
| `frontend/src/components/futures/FuturesChart.test.tsx` | 有 finding(修改) | 54 案:SC-1 橋 y 相等 / 15:01 翻頁 / 13:45–15:00 看剛收 / 假日同一把尺(F-06)/ 日曆載入重切 / gate 5 跨空檔 2 放行 4 擋 / N042 fixture 改週四夜 + 週五日盤 / 成交點三條 |
| `frontend/src/components/stock/StockIntradayChart.tsx` | 有 finding(修改) | 只改三行註解(943 / 949 / 1337);同檔 938 / 1060 / 1384 / 1388 仍舊口徑(F-03 / F-08) |
| `frontend/src/components/stock/StockIntradayChart.futures.test.tsx` | 無 finding(修改) | fixture 改前一晚 15:01 + 當日日盤;VWAP 23005 reviewer 重算相符;橋格進 polyline 期望值 |
| `frontend/src/lib/fill-marks.ts` | 無 finding(修改) | `alldayFillPoints` 加選配第 4 參 `holidays`、`anchorDateOf(stamp, holidays)`;唯一 prod caller 已同源 |
| `frontend/src/lib/fill-marks.test.ts` | 有 finding(修改) | 索引字面 1109 / 419 / 599、日期換邊、方向不變;一條標題殘「死區」(F-07) |
| `frontend/src/lib/txf-overlay-series.ts` | 有 finding(修改) | 解耦:不再 import `anchorDateOf`,`dayMinuteOf` 判日盤 bar,日盤日 = 最後一根日盤 bar 的日曆日;bars 掃兩遍(F-12) |
| `frontend/src/lib/txf-overlay-series.test.ts` | 無 finding(修改) | 三條只改標題、期望值零改(W5 parity 成立) |
| `CONTEXT.md` | 無 finding(修改) | 「錨定日」詞條,與 allday.ts / txf-overlay-series.ts 現況逐條相符 |
| `docs/next-time.md` | 有 finding(修改) | 勾銷 15:00 起算條 + 三條留尾(S7 Data Clump / 無夜盤日假設 / SC-13 b–e);勾銷行只寫「#132」(F-13) |
| `.claude/mod/futures-day-1500/change-spec.md` | 有 finding(新增) | spec;§3 W12「簽名不變(caller 零改)」在 P5 收修後未修訂(F-02) |
| `.claude/mod/futures-day-1500/current-state.md` | 有 finding(新增) | 現況表 / caller map / 白名單;W1 與 SC-1 / SC-3 矛盾(F-05) |
| `.claude/mod/futures-day-1500/verification.md` | 有 finding(新增) | §1 自動化 / §2 SC 對照 / §3 真環境 / §4 白名單 / §5 review / §6 收尾;§4 W12 句與 HEAD 不符(F-01)、§1 七檔數字四檔錯(F-04) |
| `.claude/mod/futures-day-1500/code-review-round-1.json` | 有 finding(新增) | two-axis round 1:Standards 7 / Spec 6 處置;`reviewed_head` 指到 dangling SHA 8c09cbaf(F-09) |
| `.claude/mod/futures-day-1500/evidence/SC-13_night_session_2026-08-28_0021.jpg` | INTENTIONALLY_SKIPPED(新增) | binary 截圖;兩位 reviewer 皆目視核過 §3 宣稱(九顆標籤 / 15:00→00:21 / 右半留白 / 46064 / 疊線基準 08-27 / VWAP 46246) |

## 發現總覽

| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | verification §4 以「W12 `alldayFillPoints` 簽名不變、`git diff` 未觸函式體只改註解」結掉白名單,但 HEAD 上 P5 收修就是加第 4 參 `holidays` + 函式體改 `anchorDateOf(stamp, holidays)`(`.claude/mod/futures-day-1500/verification.md:58`) | MEDIUM [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `git diff c80dbde5...HEAD -- fill-marks.ts` → `+  holidays?: ReadonlySet<string>,` / `-    if (anchorDateOf(stamp) !==` / `+    if (anchorDateOf(stamp, holidays) !==`;一句改成「簽名加選配 holidays、唯一 caller 已同源」 |
| F-02 | change-spec §3 W12「簽名不變(caller 零改)」同根未修訂 —— spec 是回歸依據,日後讀者會以為第 4 參是誤加(`.claude/mod/futures-day-1500/change-spec.md:40`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 同 F-01 證據;補一行「P5 後修訂」 |
| F-03 | `StockIntradayChart.tsx:1384` 註解「夜盤 00:00–05:00 的成交屬前一交易日」與新規則方向相反,且與同檔 1337 這一版剛改的「屬次一交易日」互相矛盾;:1388「近全軸窗 08:45–05:00」、:938「三段軸」同樣過期(SC-12 只改了三行) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `sed -n 938p;1337p;1384p;1388p` 逐行核:1337 新口徑、其餘三行舊口徑;in-flow review P1 只點名三行、收修只改那三行 |
| F-04 | verification §1 七檔案數四檔錯(allday 寫 37 實 36、adapter 20 實 22、txf 14 實 13、calendar 15 實 16;§1 第 18 行自己寫 36/36 與第 11 行矛盾);總和 233 對、分項是事後補寫(`verification.md:11`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `grep -cE '^\s*it\('` 七檔 → 36 / 22 / 54 / 13 / 16 / 53 / 39,`it.each` / `test(` 零;36+22+54+13+16+53+39 = 233 與宣稱總數相符 |
| F-05 | current-state 白名單 W1 要求「軸長 1140 + `alldayHhmmOf` 與 `alldayIndexOf` 互逆」,正是 SC-1(1365)/ SC-3(空檔索引也回時刻)要改掉的兩件事;下次被當回歸清單讀會得出相反結論(`current-state.md:40`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 對照 change-spec SC-1 / SC-3 與 allday.test.ts「可交易索引互逆;空檔索引反查後 alldayIndexOf 回 null」;W1 改寫成真正不變的那部分 |
| F-06 | P5 唯一 regression lock「假日前夜盤:live 點與成交點跟 slice 吃同一份日曆」在正確實作下日曆載入前後畫面相同,`waitFor(length 3)` 可在日曆落地前通過 → 突變只在載入後才紅,判別力靠時序(`FuturesChart.test.tsx:284`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 逐態推演:載入前兩邊皆讀空模組集合 → 錨定 08-19 一致 → 3 點 + 成交點都畫;突變體亦然;只有載入後(08-20 vs 08-19)才分家。作者 mutation 紅是時序運氣;姊妹條 :289 有「1 → 3」屏障、本條沒有 |
| F-07 | SC-12「死區」口徑更新漏三處測試文字:`fill-marks.test.ts:417` 標題、`FuturesChart.test.tsx:591 / :648` 註解;14:30 現在叫「一天之外」,與「空檔」成因處置都不同(`frontend/src/lib/fill-marks.test.ts:417`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `grep -rn 死區 frontend/src` → 三處(排除 index-chart-svg.test 無關語境);源檔已清乾淨 |
| F-08 | `MINUTE_SNAP_RADIUS = 3` 的推導註解(「1139 個 key 壓 ~724px → 1px ≈ 1.6 key」)在 1365 軸下算不出來:snap 半徑實質縮 ~15%,且空檔 225 格內只有 08:45 一格橋、hover 中段 ±3 key 必落空(誠實行為但零文件)(`StockIntradayChart.tsx:1060`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `grep -rn "1139\|1140"` → SIC.tsx:939 / 1060 / 1509 與 stock-intraday-svg.ts:159(不在 F)四處推導文字;`useFuturesBars.ts:21` 的 1140 是可交易分鐘數、仍正確不改。二選一:3 → 4 或改註解數字 + 補「空檔 snap 必落空是刻意」 |
| F-09 | code-review-round-1.json `reviewed_head` 指到 8c09cbaf,不在出貨歷史上(真正是 5316f857;verification §5 寫對了)—— 又一顆 dangling artifact SHA(`code-review-round-1.json:7`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `git merge-base --is-ancestor` 逐顆:d6f93a12 NO / 8c09cbaf NO / 608b1cfc yes / 1dbb7775 yes / 5316f857 yes(chore commit 後來 `--amend` 帶入 next-time,SHA 變了、JSON 沒回填) |
| F-10 | `liveSlotOf` / `tradeSlotOf` 兩支 file-local helper 的 `holidays` 是選配,而 P5 的復發面正是「有人忘了傳」;各只有一個 caller,收成必填是零成本型別擋(`FuturesChart.tsx:135`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep → 定義 :98 / :135、caller :278 / :286 各一;lib 側維持選配(S7 已 rejected 記 next-time),本條只收元件內兩支 |
| F-11 | adapter 的 Σ / high-low 靠「key 恰等於 `ALLDAY_GAP.end`」認出橋 = 位置當哨兵;空檔段哪天變 tradable,落 1064 的真成交會靜默排除在量 / 均價 / 高低之外、零測試紅。現況安全(`alldayIndexOf` 對 0501–0845 一律 null、橋是唯一寫入者)(`futures-accum-adapter.ts:119`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `ask-user` | 改法是把 Σ / high-low 累加移到插橋之前(插橋後只排序),結構取捨;現況零行為問題,是否值得動由 user 決定 |
| F-12 | 解耦後 `txfBarsToSeries` 對 bars 掃兩遍(第一圈找日盤日、第二圈折 minutes),caller memo deps 含每拍 ~1 s 的 `txfP / txfTime` → 每秒 2 × ~5,700 次 `dayMinuteOf`;實測量級 < 1 ms、只在鈕開著時(`txf-overlay-series.ts:76`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `ask-user` | 主 agent 核 App.tsx:208 deps;修法 = 第一圈結果存陣列給第二圈(不可改「由尾往前找」,會破亂序防禦);效益 < 1 ms,做不做由 user |
| F-13 | next-time 勾銷行寫「出貨(#132)」,PR 是 #133 —— 但 #132 是本案的 GitHub **issue**(已 closed,標題同 PR),不是不存在的編號;只是 issue / PR 混寫沒標明(`docs/next-time.md:23`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b **REFUTED**(#132 = issue) | 參考用 | `no-op` | 主 agent `gh issue view 132` → `issue #132 CLOSED mod: 期貨 tab 改 15:00…`;reviewer 只查了 `gh pr view 132`。順手可改「issue #132 / PR #133」,不算缺陷 |
| F-14 | commit `5316f857` subject 寫「StockIntradayChart / fill-marks / adapter 註解口徑改」,但該筆只動 CONTEXT.md / next-time.md / StockIntradayChart.tsx;fill-marks / adapter 的註解實際落在 `1dbb7775`(`reset --soft` 重打時分錯)。另 `1dbb7775` 🔴 行為與 🟢 測試同一筆(紅先行 commit 被併掉)(commit 訊息層,無 file:line) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | 參考用 | `no-op` | 主 agent `git show --stat 5316f857` → 3 檔、無 fill-marks / adapter;已 rebase merge 進 master,不重寫歷史;下次 `reset --soft` 重打後以 `git show --stat` 回填 subject |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 473b40f7a93bde5a9cac action=auto-fix
F-02 finding_uid: e7afe0c08b17714a9a40 action=auto-fix
F-03 finding_uid: bd625799f7df6be04695 action=auto-fix
F-04 finding_uid: e762e6769857bfb87a1b action=auto-fix
F-05 finding_uid: 953e2668871dbc475854 action=auto-fix
F-06 finding_uid: 4748d991fa24526620a5 action=auto-fix
F-07 finding_uid: d3a4880ee61b6a810da7 action=auto-fix
F-08 finding_uid: 5a9d8a48d439d3068761 action=auto-fix
F-09 finding_uid: fcd99456a3713e99baf0 action=auto-fix
F-10 finding_uid: 049feda6cb1fc4ccb29c action=auto-fix
F-11 finding_uid: 9d43eb3cf97eebff4b47 action=ask-user
F-12 finding_uid: 9b0923daeed409128920 action=ask-user
F-13 finding_uid: f001c935cb60c12e45c3 action=no-op
F-14 finding_uid: 183025e6d8390e2d4cb5 action=no-op inline=none

### Inline Comments per Finding（直接複製貼到 PR review）

#### F-01 W12 這句說「函式體沒動」,但 P5 的修就是動了它
**File**: `.claude/mod/futures-day-1500/verification.md`
**Line**: 58

**Comment**:
```
「W12 alldayFillPoints 簽名不變(git diff 未觸 fill-marks.ts 函式體,只改註解)」—— 一跑 git diff 就被推翻:
P5 收修加了第 4 參 holidays?: ReadonlySet<string>,函式體改成 anchorDateOf(stamp, holidays)。
既有 3 參 caller 不受影響是真的,但理由要換:
「W12:簽名加選配 holidays(既有三參呼叫相容);唯一 prod caller FuturesChart.tsx:254 已同步傳 holidaySet」。
```

#### F-02 spec 的 W12 也還是收修前的話
**File**: `.claude/mod/futures-day-1500/change-spec.md`
**Line**: 40

**Comment**:
```
§3 W12「alldayFillPoints 簽名不變(caller 零改)」在 P5 之後已經不成立(第 4 參 holidays + caller 改傳同一份日曆)。
spec 是日後回歸的依據,補一行:「P5 後修訂:簽名加選配 holidays,caller 必須傳與 anchorDate 同源的那一份」。
```

#### F-03 這行把錨定規則講反了,跟 47 行前剛改的那句打架
**File**: `frontend/src/components/stock/StockIntradayChart.tsx`
**Line**: 1384

**Comment**:
```
1384「夜盤 00:00–05:00 的成交屬前一交易日」—— 新規則正好相反(夜盤 15:01 → 05:00 屬**次一**交易日),
時段也漏了 15:01–23:59;同檔 1337 這一版已經改成「屬次一交易日的錨定日」,兩行互相矛盾。
順手一起改:1388「近全軸窗是 08:45–05:00」→ 15:00–13:45;938「近全三段軸」→ 四段。
```

#### F-04 這一格的七個數字有四個對不上,和自己第 18 行也打架
**File**: `.claude/mod/futures-day-1500/verification.md`
**Line**: 11

**Comment**:
```
第 11 行寫「allday 37、adapter 20、txf 14、trading-calendar 15」,HEAD 上 it( 實數是 36 / 22 / 13 / 16
(第 18 行自己就寫 allday 36/36)。總和 233 是對的,分項是事後補的。
直接貼 vitest 的 per-file 輸出,或改成「allday 36、adapter 22、FuturesChart 54、txf 13、trading-calendar 16、fill-marks 53、SIC.futures 39 = 233」。
```

#### F-05 W1 寫的是本案要改掉的東西,不是要守住的東西
**File**: `.claude/mod/futures-day-1500/current-state.md`
**Line**: 40

**Comment**:
```
白名單 W1「軸長 1140、alldayHhmmOf 與 alldayIndexOf 互逆」正是 SC-1(1365)/ SC-3(空檔索引也回時刻,不再全域互逆)要改的。
下次有人拿這張表當回歸清單會得出相反結論。改寫成真正不變的那部分:
「空檔 / 一天之外 alldayIndexOf 仍回 null;可交易索引與 alldayHhmmOf 仍互逆;三個可交易段的段界字串與後端 FUTURES_ALLDAY_DOMAIN 相同」。
```

#### F-06 這條「同一把尺」測試的紅靠時序,不靠結構
**File**: `frontend/src/components/futures/FuturesChart.test.tsx`
**Line**: 284

**Comment**:
```
正確實作下,日曆載入前(兩邊都讀空模組集合 → 錨定 08-19)和載入後(都讀 query → 08-20)畫面一樣:3 點 + 成交點都在。
所以 waitFor(length 3) 可能在日曆還沒落地時就過,接著同步斷言 last-dot 就跑完 ——
突變(live 改回讀模組集合)只在載入後才分家,現在紅是時序運氣。
補一個只有載入後才成立的屏障再斷言:ordersBody 多塞一筆 { date: "20260820", time: "09:00:30" } 的成交
(載入前 anchorDate 08-19 → 不畫;載入後 08-20 → 畫),先 await waitFor(fill-B-1079) 再驗 last-dot。
姊妹條 :289 的「1 → 3」就是這種屏障。
```

#### F-07 三處測試文字還在說「死區」,14:30 現在叫「一天之外」
**File**: `frontend/src/lib/fill-marks.test.ts`
**Line**: 417

**Comment**:
```
源檔註解已全面改成「空檔(05:01–08:45)/ 一天之外(13:46–15:00)」,只剩這條標題、FuturesChart.test.tsx:591 / :648 的註解還寫「死區」。
兩者成因處置不同(一天之外 = 不在這一天;空檔 = 在軸上要畫水平線),沿用舊詞會混。
這條標題改「一天之外的成交(14:30)→ 不畫」,那兩行註解改「非空檔 / 非一天之外」。
```

#### F-08 snap 半徑的推導註解已經算不出來
**File**: `frontend/src/components/stock/StockIntradayChart.tsx`
**Line**: 1060

**Comment**:
```
「1139 個 key 壓 ~724px → 1px ≈ 1.6 key」是 1140 軸的數字;現在 1365 個 key 壓同寬度 → 1.88 key/px,
MINUTE_SNAP_RADIUS = 3 的 ±1.9px 變 ±1.6px(縮 ~15%)。另外空檔 225 格裡只有 08:45 一格橋,
hover 落在空檔中段 ±3 key 必落空 → 十字與資料點不畫(對的行為,但沒寫)。
二選一:3 → 4 維持 ~±1.9px;或把 939 / 1060 / 1509 的數字改 1365 / ~1.9,並補一句「空檔段 snap 落空是刻意」。
stock-intraday-svg.ts:159 那句 1139 同型但不在本 PR。useFuturesBars.ts:21 的 1140 是可交易分鐘數,還是對的,別動。
```

#### F-09 reviewed_head 指到一顆不在歷史上的 SHA
**File**: `.claude/mod/futures-day-1500/code-review-round-1.json`
**Line**: 7

**Comment**:
```
"history rewritten after fixes → 608b1cfc / 1dbb7775 / 8c09cbaf":8c09cbaf 是 chore commit --amend 前的 SHA,
merge-base --is-ancestor 不成立;真正出貨的是 5316f857(verification §5 寫對了)。
artifacts commit 前用 git log --oneline 回填,不要憑 reset --soft 前的記憶寫。
```

#### F-10 這兩支 helper 的 holidays 可以直接必填
**File**: `frontend/src/components/futures/FuturesChart.tsx`
**Line**: 135

**Comment**:
```
liveSlotOf / tradeSlotOf 是 file-local、各只有一個 caller(:278 / :286),而 P5 那類 bug 就是「有人忘了傳」。
參數改成 holidays: ReadonlySet<string> | undefined(必填、可 undefined)零成本,型別就擋住下次漏傳;
lib 側的 anchorDateOf / sliceCurrentAllday / alldayFillPoints 維持選配(S7 已記 next-time),這裡只收元件內這兩支。
```

#### F-11 橋是靠「key 剛好等於 1064」認出來的
**File**: `frontend/src/lib/futures-accum-adapter.ts`
**Line**: 119

**Comment**:
```
Σ / high-low 迴圈用 k === ALLDAY_GAP.end 跳過橋 —— 橋跟真成交格唯一的差別是索引。現在安全
(alldayIndexOf 對 0501–0845 一律 null、橋是這一格唯一寫入者),但哪天空檔段變 tradable,落在 1064 的真成交會
靜默被排除在量 / 均價 / 高低之外,四個數字都只是數字,沒有測試會紅。
更穩的寫法:amountMilli / volume / high / low 在插橋**之前**對 rows 跑一遍,插橋後只做排序 —— 就不需要哨兵。
零行為問題,做不做你決定。
```

#### F-12 解耦後 bars 每秒被完整掃兩遍
**File**: `frontend/src/lib/txf-overlay-series.ts`
**Line**: 76

**Comment**:
```
第一圈掃日盤日、第二圈折 minutes,兩圈都對每根 bar 跑 dayMinuteOf → splitStamp;caller(App.tsx:208)的 memo deps
含每拍 ~1 s 的 txfP / txfTime,所以是每秒 2 × ~5,700 次。量級 < 1 ms、只在鈕開著時,純可選。
要收就把第一圈的 dayMinuteOf 結果存成陣列給第二圈用;別改成「由尾往前找第一根日盤 bar」,那會破掉檔頭刻意保留的亂序防禦。
```

#### F-13 不是 PR 缺陷:#132 是 issue 不是 PR
**File**: `docs/next-time.md`
**Line**: 23

**Comment**:
```
reviewer 提「出貨(#132)但 PR 是 #133、#132 不存在」—— #132 是本案的 GitHub issue(gh issue view 132:CLOSED、標題同 PR),
next-time 那行指的是 issue,不是錯號。順手可寫成「issue #132 / PR #133」讓兩個編號都追得到,不算缺陷。
```

### Opus 原始 findings (first-pass, context-aware)

chunk 1(typescript-reviewer;allday ×2 / FuturesChart ×2 / StockIntradayChart ×2):

- **F-03**(reviewer 原編號 C1-1,LOW)`StockIntradayChart.tsx:1384-1388` —— 錨定規則註解方向相反、與 1337 矛盾;938 三段軸過期。anchor:`        // 相等判定(夜盤 00:00–05:00 的成交屬前一交易日),caller 折好後由 \`fills\` 傳入。`。search-proof:Grep「近全軸|夜盤|08:45|05:00|13:45|15:01」於本檔 → 1337 新口徑、1384 / 1388 / 938 舊口徑;Grep「死區」全 src → prod code 已清。spec_ref:SC-12 / round-1 P1(disposition fixed 但只覆蓋三行)
- **F-08**(C1-2,LOW)`StockIntradayChart.tsx:1060` —— `MINUTE_SNAP_RADIUS = 3` 推導註解在 1365 軸下失效、空檔中段 snap 必落空零文件。anchor:`  // 近全軸(1139 個 key 壓 ~724px)才開 hover 命中的就近 snap(N046);現貨 / 個股期 /`。search-proof:Grep「MINUTE_SNAP_RADIUS」→ 定義 stock-intraday-svg.ts:165、讀者 SIC.tsx:1063;Grep「1139|1140」→ 939 / 1060 / 1509;useFuturesBars.ts:21 仍正確。mechanism:`buildIntradayGeometry(…, { snapRadius })` 收 key 單位半徑(stock-intraday-svg.ts:463),不隨窗寬換算 px
- **F-06**(C1-3,LOW)`FuturesChart.test.tsx:284-286` —— P5 lock 判別力靠時序、無「日曆已載入」屏障。anchor:`        await waitFor(() => expect(mainLineXs(container).length).toBe(3)); // 22:00 / 22:29 / live 22:31`。search-proof:Read test-utils.tsx → `wrap()` 每次新 QueryClient、無 prefetch;Grep「useTradingCalendar」於本測試檔 → 零,模組集合只被 `clearHolidays()` 清空。mechanism:calendarQueryOptions staleTime Infinity / retry 1;fetch mock async 立即 resolve,但 TQ setData → re-render 跨數個 microtask,與 `findIntraday()` 的 waitFor 輪詢未同步
- **F-10**(C1-4,LOW)`FuturesChart.tsx:98-135` —— `liveSlotOf` / `tradeSlotOf` 的 `holidays` 選配、各一個 caller、可收必填。anchor:`function liveSlotOf(now: Date, holidays?: ReadonlySet<string>): { index: number; anchor: string } | null {`。search-proof:Grep「liveSlotOf|tradeSlotOf」→ 定義各 1、caller :278 / :286、測試零直呼;`alldayFillPoints` prod caller 只 :254(選配是為了 fill-marks.test 既有 3 參呼叫)。spec_ref:W12 / S7(rejected)/ P5(fixed)

chunk 2(typescript-reviewer;calendar ×2 / adapter ×2 / fill-marks ×2 / txf ×2 / CONTEXT / next-time / 5 artifacts):

- **F-01**(C2-1,MEDIUM)`verification.md:58` —— W12 以「函式體未動、只改註解」結案,HEAD 簽名與函式體都改。anchor:`- W3 \`trading-hours.ts\` 零 diff;W6 \`candle.ts\` 零 diff;W12 \`alldayFillPoints\` 簽名不變(\`git diff\` 未觸 \`fill-marks.ts\` 函式體,只改註解)。`。search-proof:`git diff c80dbde5..HEAD -- fill-marks.ts` hunk 含 `+  holidays?: ReadonlySet<string>,` 與 `anchorDateOf(stamp, holidays)`;grep alldayFillPoints 全庫 → 唯一 prod caller FuturesChart.tsx:254 已帶 holidaySet。spec_ref:change-spec §3 W12 / round-1 P5
- **F-04**(C2-2,LOW)`verification.md:11` —— 七檔案數四檔錯、與第 18 行矛盾、加總口徑重複計 FuturesChart。anchor:`| \`npx vitest run\` 本案七檔(allday / adapter / FuturesChart / txf-overlay / trading-calendar / fill-marks / SIC.futures) | 收修後全綠 233 + FuturesChart 54(allday 37、adapter 20、FuturesChart 54、txf 14、trading-calendar 15、SIC.futures 39) |`。search-proof:`grep -c "\bit("` 逐檔 → 16 / 13 / 22 / 36 / 53 / 54 / 39,`test(` 皆 0
- **F-02**(C2-3,LOW)`change-spec.md:40` —— W12 spec 未修訂。anchor:`- W12:\`alldayFillPoints\` 簽名不變(caller 零改),錨定語意隨 \`anchorDateOf\` 變。`。search-proof:同 C2-1;change-spec 全檔 grep holidays → 僅此一處、無修訂註記
- **F-05**(C2-4,LOW)`current-state.md:40` —— W1 與 SC-1 / SC-3 衝突。anchor:`| W1 | 軸長 1140、三段長 300/539/301、死區(13:46–15:00 / 05:01–08:45)回 null、\`alldayHhmmOf\` 與 \`alldayIndexOf\` 互逆 | \`allday.test.ts\` 對應條(改期望索引值,不改語意) |`。spec_ref:SC-1 / SC-3
- **F-09**(C2-5,LOW)`code-review-round-1.json:7` —— reviewed_head 8c09cbaf dangling。anchor:`"reviewed_head": "d6f93a12 (pre-fix; history rewritten after fixes → 608b1cfc / 1dbb7775 / 8c09cbaf)",`。search-proof:`git merge-base --is-ancestor` 逐顆 → d6f93a12 NO / 8c09cbaf NO / 608b1cfc、1dbb7775、5316f857 yes
- **F-13**(C2-6,LOW)`docs/next-time.md:23` —— 「出貨(#132)」PR 是 #133、`gh pr view 132` 解析不到。anchor:`- [x] **期貨 tab 改「15:00 夜盤起算」的一天定義(user 08-27 拍板另開 /mod)** —— 08-28 mod/futures-day-1500 出貨(#132);留尾見下條`。search-proof:`gh pr view 133` → MERGED;`gh pr view 132` → Could not resolve(**主 agent 4.3b 以 `gh issue view 132` 反證:#132 = 本案 issue**)
- **F-12**(C2-7,LOW)`txf-overlay-series.ts:74-86` —— bars 掃兩遍、每秒重折。anchor:`  for (const b of bars) {\n    const dm = dayMinuteOf(b);\n    if (dm !== null && (anchor === null || dm[0] > anchor)) anchor = dm[0];\n  }`。mechanism:App.tsx:208 useMemo deps `[txfBarsList, txfP, txfTime, txfDate, txfRef, txfStale]`;txfP / txfTime 來自 `useIndexStream().txf` ~1 s 一拍;bars 規模 allday.ts 註「5 日 ≈ 5,700 根」
- **F-11**(C2-8,LOW)`futures-accum-adapter.ts:118-119` —— Σ / high-low 以 key 位置當哨兵認橋。anchor:`  for (const [k, m] of sorted) {\n    if (k === ALLDAY_GAP.end) continue; // 橋:不是成交,不進 Σ 與高低`。search-proof:grep ALLDAY_GAP 全庫 → 產生點 allday.ts:75-78、唯一消費者 adapter :1 / :102 / :103 / :106 / :119;grep alldayIndexOf → 空檔 `if (!seg.tradable) continue`(allday.ts:85)是唯一擋人的地方。mechanism:rows 三個寫入點(bar 迴圈 / live 合入 / 橋)只有橋能產出 key 1064;live.index 來自 liveSlotOf → alldayIndexOf 同樣進不了空檔
- **F-07**(C2-9,LOW)`fill-marks.test.ts:417` —— 測試標題殘「死區」。anchor:`  it("死區成交(14:30,近全軸上沒有那一格)→ 不畫(不夾到最近的段界)", () => {`。search-proof:`grep -rn 死區 frontend/src` → fill-marks.test.ts:417、FuturesChart.test.tsx:591 / :648、index-chart-svg.test.ts:184(無關語境);源檔已無此詞。spec_ref:SC-12
- **F-14**(chunk 2「commit 慣例核對」段,主 agent 升格為 finding,LOW)commit `5316f857` subject 點名 fill-marks / adapter 但只動 3 檔;`1dbb7775` 🔴 混 🟢。anchor:`<none>`(最近符號 `git show --stat 5316f857`)。search-proof:`git show --stat --format=%s 5316f857` → CONTEXT.md / docs/next-time.md / StockIntradayChart.tsx 三檔

已逐條複核成立的 PR 自我宣稱(reviewer 核過,無 finding):(1) W2 後端零 diff(`git diff c80dbde5..HEAD -- copycat/ tests/` 空);(2) W3 `trading-hours.ts` / W6 `candle.ts` 零 diff;(3) W13 `FUT_LIVE_LAG_MAX = 3` 與「分時資料落後 {lagBehind} 根(TC4 回補中)」字面不變;(4) W9 `ALLDAY_WINDOW` / `ALLDAY_HOUR_TICKS` 仍模組層 IIFE;(5) round-1 S3 / S5 / S6 / P5 / P6 disposition 在 HEAD 成立(isTradingDayIso 無 export、allday 已無 shiftDate、`dayMinuteOf` 兩處共用、五處全帶 holidaySet、shiftIso Invalid Date 早退 + garbage 測試);S7 rejected 處置合理(caller 傳 `undefined` 不是空 Set、退化方向正確);(6) SC-13 (a) 真環境截圖兩位 reviewer 目視核過(九顆標籤、線 15:00→00:21、右半留白、readout 00:21、昨收 46064、疊線基準 2026-08-27、VWAP 46246.17;刻度間距比 03:00→05:00 : 05:00→09:00 ≈ 1 : 2 與索引 120 : 240 相符);(7) `holidays` 陣列 identity 在 TQ `structuralSharing` 下 5 分鐘 refetch 回同一份時不變 → `holidaySet` memo 不每 5 分鐘打穿;(8) `wrap()` 每次新 QueryClient、全域 `afterEach` 有 `vi.useRealTimers()`。**不成立**:W12 句(F-01)、§1 七檔數字(F-04)。**無法核**(worktree 無 node_modules、依指示不跑):全量 vitest / tsc / eslint / pytest 綠燈、mutation 紅、紅先行(三筆 commit 依 type 重打後 `test` commit 不存在,紅根數只有 verification 自陳)。

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查。

### Codex 對 Opus 的複查結果（對稱化 4.2）

**Codex 複查 Opus 失敗 — 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(本機無 codex)。全部 CC finding 視同 INCONCLUSIVE,改由 4.3b 主 agent 逐條實查(結果在發現總覽「Opus 複查」欄與下方備註):

| Opus # | 原始 severity | 4.3b 判斷 | 備註(他軸為何漏 / 主 agent 實查) |
| --- | --- | --- | --- |
| F-01 | MEDIUM | CONFIRMED | `git diff c80dbde5...HEAD -- fill-marks.ts` 三行 hunk(第 4 參 + `anchorDateOf(stamp, holidays)`)。lone 解釋:in-flow round 1 P5 收修由主 agent 直做、verification §4 那句是收修前寫的、沒回校 |
| F-02 | LOW | CONFIRMED | change-spec §3 W12 同句;同 F-01 根因 |
| F-03 | LOW | CONFIRMED | `sed -n 1384p` 「夜盤 00:00–05:00 的成交屬前一交易日」;`1337p` 已是「屬次一交易日的錨定日」;`938p`「近全三段軸」。lone 解釋:round 1 P1 只點名 946 / 949 / 1337,主 agent patch 只改那三行 |
| F-04 | LOW | CONFIRMED | `grep -cE '^\s*it\('` → 36 / 22 / 54 / 13 / 16 / 53 / 39,總和 233 = 宣稱總數;分項四處錯。lone 解釋:數字憑 vitest 摘要行記憶手抄 |
| F-05 | LOW | CONFIRMED | W1 字面「軸長 1140 … 互逆」vs SC-1 / SC-3 與 allday.test 互逆條的空檔分流。lone 解釋:current-state 在 grilling Q4 拍板(空檔保留)之前寫,拍板後沒回改 |
| F-06 | LOW | CONFIRMED | 逐態推演(載入前 / 後 / 突變體)三態表:只有「突變體 + 載入後」紅;`git diff` 顯示作者 mutation 是一次性人工跑、無屏障。lone 解釋:round 1 P5 要「新測試 + mutation 紅」,紅了就收,沒問「為什麼紅」 |
| F-07 | LOW | CONFIRMED | `grep -rn 死區 frontend/src` 三處(排除無關 index-chart 語境)。lone 解釋:SC-12 驗證方式寫 grep,但收修 patch 只 grep 了源檔 |
| F-08 | LOW | CONFIRMED | `grep -rn "1139\|1140"` 四處推導註解;`MINUTE_SNAP_RADIUS = 3` 未動。lone 解釋:snap 半徑不在 spec 牽動清單,軸長 1140 → 1365 的連帶沒盤到 |
| F-09 | LOW | CONFIRMED | `git merge-base --is-ancestor 8c09cbaf HEAD` NO;5316f857 yes。lone 解釋:chore commit 在 JSON 寫完後才 `--amend` 帶入 next-time |
| F-10 | LOW | CONFIRMED | `grep -n "liveSlotOf(\|tradeSlotOf("` → :278 / :286 各一 caller。judgement:收兩支 file-local helper 不與 S7 rejected 衝突 |
| F-11 | LOW | CONFIRMED(判斷式) | 追 rows 三個寫入點 + `alldayIndexOf` 空檔 null → 現況安全;結構取捨 → ask-user |
| F-12 | LOW | CONFIRMED(判斷式) | App.tsx:208 deps 含 txfP / txfTime;成本 < 1 ms → ask-user |
| F-13 | LOW | **REFUTED** | `gh issue view 132` → `issue #132 CLOSED mod: 期貨 tab 改 15:00 夜盤起算…`;reviewer 只查 `gh pr view 132`。next-time 那行指 issue 編號,非錯號;可改「issue #132 / PR #133」 |
| F-14 | LOW | CONFIRMED | `git show --stat 5316f857` 三檔無 fill-marks / adapter;歷史已 merge 不重寫 → no-op |

## Action Items

**Severity calibration**:6c(移除既有防護類)—— 本 PR 無移除防護 / guard 類改動(gate 1–4 判準逐字不動、gate 5 只把裸差換成可交易距離、加的是 holidaySet 同源);6d-1 hedge cap:F-11「哪天空檔段變 tradable」、F-08「日後」皆假設性後果 → Nice;6d-3 Must Fix 雙半條件:十四條無一有 user-visible 重現路徑 + 阻擋發布(全部是文件 / 註解 / 測試韌性 / 結構取捨),無 Must / Should;F-01 reviewer 給 MEDIUM 但它是 artifacts 敘述不符,不阻擋任何會出貨的東西 → Nice(與 #131 F-02 同型同級);6d-2 由 4.3b 取代(13 條 CONFIRMED 各有 lone 解釋,零降級;F-13 REFUTED → 參考用);未驗證前提閘:十三條 CONFIRMED 的 severity 都建立在第一手 git diff / grep / sed / gh 證據上,拿掉推論部分不降級;F-06 的「作者 mutation 紅是時序運氣」是主 agent 推演,未實跑兩態 —— 標未驗證,但不影響等級(Nice);provenance cap N-A。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix（合併前必修）

- 無

### Should Fix（強烈建議）

- 無

### Nice to Have（可選優化）

- F-01 verification §4 W12 句改「簽名加選配 holidays、唯一 caller 已同源」(`.claude/mod/futures-day-1500/verification.md:58`)
- F-02 change-spec §3 W12 補「P5 後修訂」(`.claude/mod/futures-day-1500/change-spec.md:40`)
- F-03 `StockIntradayChart.tsx:1384` 錨定方向改正、:1388 窗改 15:00–13:45、:938 三段 → 四段
- F-04 verification §1 七檔數字改 36 / 22 / 54 / 13 / 16 / 53 / 39(`verification.md:11`)
- F-05 current-state W1 改寫成真正不變的部分(`current-state.md:40`)
- F-06 P5 測試加「只有日曆載入後才畫」的成交點屏障(`FuturesChart.test.tsx:284`)
- F-07 三處測試文字「死區」→「一天之外」/「非空檔」(`fill-marks.test.ts:417`、`FuturesChart.test.tsx:591 / :648`)
- F-08 `MINUTE_SNAP_RADIUS` 註解數字改 1365 / ~1.9 或半徑 3 → 4,補「空檔 snap 落空是刻意」(`StockIntradayChart.tsx:1060`)
- F-09 JSON `reviewed_head` 8c09cbaf → 5316f857(`code-review-round-1.json:7`)
- F-10 `liveSlotOf` / `tradeSlotOf` 的 `holidays` 改必填(`FuturesChart.tsx:135`)
- F-11(ask-user)adapter Σ / high-low 移到插橋之前、去掉 key 哨兵(`futures-accum-adapter.ts:119`)
- F-12(ask-user)`txfBarsToSeries` 第一圈結果存陣列給第二圈(`txf-overlay-series.ts:76`)

### 參考用（任一軸驗證為 REFUTED 或 OUT_OF_SCOPE）

- F-13 Opus [typescript-reviewer] 擔心 next-time 勾銷行「#132」是不存在的 PR 編號 → 主 agent 於 `gh issue view 132` 找到它是本案 issue(CLOSED)→ 使用者自行判斷要不要把那行改成「issue #132 / PR #133」
- F-14 commit `5316f857` subject 點名未動的檔、`1dbb7775` 🔴 混 🟢:已 rebase merge 進 master、不重寫歷史;非 REFUTED / OUT_OF_SCOPE,因無可修 file:line 且處置為 no-op 而列此

## 審查工具比較 (qualitative)

- CC 視角(typescript-reviewer ×2 chunked):十四條裡 **零行為 bug** —— 兩位 reviewer 都把橋(polyline 逐 key 連線、vwapLine 對 v=0 加 0、極值反查 `m.h === target` 對 h=null 必不命中)、gate 5 等價、holidaySet 五處同源、TQ structuralSharing 對 memo 的影響、TS 預設參數每次呼叫求值等機制追到底後放行。命中集中在三型:(a) artifacts 敘述落後收修(F-01 / F-02 / F-04 / F-05 / F-09,五條全在 spec / 白名單 / verification 自寫自驗的同源漏),(b) SC-12 口徑更新只做到 in-flow review 點名的那幾行(F-03 / F-07 / F-08),(c) 判斷式結構點(F-06 測試屏障、F-10 型別擋、F-11 哨兵、F-12 雙掃)。與 in-flow two-axis round 1(13 條:橋位置字面值、兩把假日尺、shiftIso 炸、三處 Duplicated)的差異:round 1 抓 code 層,本輪抓的是收修之後**文件與註解沒跟上**的第二層 —— 與 #131 的型態一致。
- Codex / Gemini:N-A。
- 4.3b:CONFIRMED 13 / REFUTED 1(F-13:reviewer 查 `gh pr view 132` 未查 `gh issue view`)/ 0 降級;十三條皆有 lone 解釋。
- 對抗式第三軸增益:N-A。
- 覆蓋 / 定位:chunked 兩塊 21/21 accounting、missed 0;anchor exact 12 / ambiguous 1 / FAILED 0。

## 沒做的部分（結案對帳）

- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(git diff / grep / sed / merge-base / gh issue)。
- sem blast radius:跑了,空輸出跳過。React-doctor:跑了,新引入 0(既有 2 條不計)。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 以 `PYTHONUTF8=1 py -3.14` 實跑;前兩次 `C4_CLI_INPUT_INVALID` 為 stdin cp950 解碼,非判定)。
- 自動化綠燈(全量 vitest / tsc / eslint / pytest)與 mutation 紅:本輪未於 worktree 複跑(無 node_modules、依 2.5.4 純讀 review),只引 verification.md 自陳;主 agent 在出貨前實跑過(見 PR body),但那不是本輪的獨立證據。
- 未驗證前提:F-06「作者 mutation 紅是時序運氣」為主 agent 推演,未實跑「日曆未載入 + 突變體」那一態;F-11 / F-12 的「現況安全 / < 1 ms」為 reviewer 追機制與量級估算,未實測。
- 真環境:SC-13 (b)–(e)(15:01 翻頁、次一交易日 08:46 水平橋 + 跳價、CDP 對 APP、個股頁夜盤疊線)待窗口,由 PR verification 自陳、本輪未新增證據;prod 8721 重啟後才看得到本 PR 畫面。
- Self-Verify:已執行,COMPLIANT(auditor 以 Read 讀取草稿檔本身,未讀其他產物;header 與本行為 auditor 回覆後填入,依指示判 N-A)
