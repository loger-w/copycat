# PR #211 Code Review 比較報告
**Report projection schema**: 1

**PR**: [loger-w/copycat#211](https://github.com/loger-w/copycat/pull/211)
**標題**: mod(W2 批): 日 K 14:00 定稿界 / 輪詢頁盤外自醒 / 盤前篩選改 08:00 目標交易日制 + 重試時間盒 + 當沖名單相對閘(spec #204,#205–#210)
**作者**: loger-w
**分支**: `mod/w2-daily-bars-and-screen-0800` → `master`
**變更**: 25 檔案, +1461 / -210
**審查日期**: 2026-09-08
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `dfdc149dddf14ea61bb40a658307c6e3c78dd31a`;destination repo id `R_kgDOTsITBg` + baseRefOid `de192ca33314f57c7a40140ea4e356ab820668ef`;`input_binding: unverified` —— PR 走 rebase merge、分支已刪,`dfdc149d` 不在任何 ref 上;實際審的是 **master 上該 PR 落地的 range `de192ca3..5b8c8b01`**(21 筆 rebase 後 commit,`gh pr view --json mergeCommit` = `5b8c8b01`),與 PR head 內容逐檔等價但 SHA 不同;review input 未驗證,不宣稱 Reviewed SHA
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫全部 SHA;分支已隨 `--delete-branch` 刪除,產報告前重抓 PR head 仍為 `dfdc149d`);`base_changed=true`(origin/master 自 `de192ca3` 前進至 `5b8c8b01`,內容 = 本 PR 自身的 21 筆,其後零新 commit);`review_context_changed=false`(worktree HEAD = `5b8c8b01` = 當前 master,審的就是落地版)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用,沿 #188 / #190 / #199 / #202 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewers **chunked ×2**:chunk A(後端 + 文件 + artifacts 12 檔)=python-reviewer(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model)、chunk B(前端 13 檔)=typescript-reviewer(requested=opus / observed=UNAVAILABLE)—— .py 改動 ~241 行 vs .ts 非測試 ~232 行、兩語言各 ~50%,無 >40% 主語言,依 chunk 語言各派專屬 reviewer(取代 generic `code-reviewer` 單派);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE;實跑 pytest + 一次 `<`→`<=` 突變 + log 重現);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=25 → covered 15 / no-issues 10 / skipped 0 / **missed 0**(chunked: **是**,20 source 檔 / 1671 diff 行,超過 800 行門檻 → 依語言切 chunk A 12 檔 + chunk B 13 檔,聯集 = F;兩 chunk 各自 12/12、13/13 per-file accounting 齊)
**定位 (ENH-B)**: anchored exact 17 / ambiguous 1 / **FAILED 0**(R-A3 的 `prior = self._cached_daytrade_rows()` 在 screen_engine.py:300 與 :321 兩處命中,finding 本身就是講這兩處 → ambiguous;R-A7 anchor `<none>`(缺測試型),釘到被守的實作行 screen_engine.py:164;其餘 17 條 anchor 逐字唯一命中,行號以 grep 結果為準)
**React-doctor (2.97)**: 未引入新問題(`--scope changed --base de192ca3 --json` 於 review worktree:newCount 0 / fixedCount 0 / baseTotalCount 0,changedFileCount 13;`.tsx` 只有 `useStockBars.test.tsx`)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_SPEC_DOCUMENT)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `de192ca3` 執行、exit 0、零輸出)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary chunk A(python-reviewer)PASS(11 findings + 12/12 accounting;實跑 `pytest tests/server/test_screen_engine.py tests/test_screening.py tests/server/test_bars.py` 120 passed)/ primary chunk B(typescript-reviewer)PASS(7 findings + 13/13 accounting;無 node_modules 純讀碼)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 請求體解析 / 秘鑰讀取)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(18/18 verdict 齊、ID 集合精確相等、每列六欄齊)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-211`
**worktree HEAD**: `5b8c8b01befbde64d0ce3083c55ddeb1f5962278`

**Report generation**: sha256:d397912f85a70da36d104778569d3ba608a281f479afd319554113787f33a431

---
## [完整證據副檔](pr-211-review.audit.md)
### finding_uid 索引
[f19b0c46f50eb36f826b](pr-211-review.audit.md#發現總覽) · [c94e0884d80625ef8c07](pr-211-review.audit.md#發現總覽) · [f06f18bab14926f054b1](pr-211-review.audit.md#發現總覽) · [db693abf882ecc0781f7](pr-211-review.audit.md#發現總覽) · [8293caa349083f6f694c](pr-211-review.audit.md#發現總覽) · [9875ae4250a7f51906a0](pr-211-review.audit.md#發現總覽) · [2036d60a601a90ad4623](pr-211-review.audit.md#發現總覽) · [43ac5347f2adca121140](pr-211-review.audit.md#發現總覽) · [dc63ddabb9cc27d38185](pr-211-review.audit.md#發現總覽) · [cfaf1ed4049e2f2413a1](pr-211-review.audit.md#發現總覽) · [4db77c5843183bc4e3fe](pr-211-review.audit.md#發現總覽) · [88251147cf7a2312ae97](pr-211-review.audit.md#發現總覽) · [2fd16fb61acbe11239c8](pr-211-review.audit.md#發現總覽) · [1312dd9ece9d4bd630c1](pr-211-review.audit.md#發現總覽) · [cef13ec2212934077668](pr-211-review.audit.md#發現總覽) · [e985fd9f0d4adf2adeea](pr-211-review.audit.md#發現總覽) · [c6ac5a21bdba6f86f351](pr-211-review.audit.md#發現總覽) · [d86625a0f3532ecff692](pr-211-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `verification.md:109` 明早要 grep 的真環境判準寫「log 印『前值 None』」,但 `_prior_text(None)` 印的是「無(用絕對下限)」,兩個印點都走它 → 判準 0 命中 | LOW | CONFIRMED(LOW→LOW:這是 08:00 制第一個交易日的驗收字串,對不上會讓驗收者誤判「沒跑」;round-1 F-08 收修後判準沒跟著改口) | Nice to Have | `auto-fix` | 純文件一行:改成「當沖名單 n 列(前值 無(用絕對下限))」 |
| F-02 | `screen_engine.py:59` 註解「每 600 s → 08:00:30 … 08:50:30 共 6 次」只在零耗時假時鐘成立:sleep 固定 600 不扣 attempt 時長(每 attempt 序列抓 21 個 MB 級 EOD + 當沖 + 處置),且相對閘 `_require_daytrade_complete`(:276)排在 21 次 EOD **之後** —— 「名單沒出齊」這條最常走的失敗路徑每次都先重下載 21 個已定稿 EOD | MED | PARTIAL(MED→LOW:節奏與閘位置兩點事實成立,但「08:40 才出名單那天會錯過」被推算反證 —— attempt 150 s 時 5 次、300 s 時 4 次,最後一次都落在 08:45–08:53,08:40 出的名單一樣抓到;頻寬成本為真但已是 next-time F-09 既有留尾) | Nice to Have | `ask-user` | 兩條路要拍板:(a) 當沖名單 fetch + 三道閘提到 EOD 迴圈前(fail-fast,失敗路徑 22 → 1 請求;內部複查核過不改既有測試觸發順序)/ (b) 只改註解為「理論 6 次,實際視取數耗時 4–6 次」+ 併 F-09 |
| F-03 | `day-bars-rollover.ts:44` 成本註解「後端 cache 命中不打 TC4」與後端相反:`daily_get` 對界前 entry 過界回 None(bars.py:358-359),14:01 那發**必然** miss、每把 key 每天一趟 180 日窗 SubHistory;同段下一句自己講「拿到墊背」= 有 fetch,自相矛盾 | LOW | CONFIRMED(LOW→NICE:只誤導日後評估成本的人,行為與墊背正確;`_warn_if_not_advanced` 有 `bars[-1]["t"] == day` 閘,週末那發不污染 pr-171 判準) | Nice to Have | `auto-fix` | 註解改事實:「14:01 那發必走上游(界前快照過界作廢是後端設計);TC4 關著時回 `daily_stale` 墊背 + INFO,不進 retryEmpty 迴圈」 |
| F-04 | `screen_engine.py:299-300` `compute()` docstring 寫「純結果 … 不改引擎狀態(CLI 共用)」但**讀**引擎快取(`_cached_daytrade_rows`);CLI 的 ScreenEngine 不帶 data_dir → 落 repo-root prod 快取,`screen --date <過去日>` 可能被 server 前值擋(traceback),而 WARNING 建議刪鍵會砍掉 server 基準 —— 白名單「CLI 預覽路徑」的未揭露副作用 | LOW | PARTIAL(LOW→NICE:路徑主張第一手成立(cli.py:366-372 無 data_dir → screen_engine.py:102-106 fallback);但 docstring 三個否定句都為真、只有「純結果」四字可質疑,且過去日名單列數與前值同量級、被擋機率極低) | Nice to Have | `ask-user` | 二選一:prior 由呼叫端傳入、CLI 傳 None 走絕對下限(CLI 與 server 兩套門檻)/ 只改 docstring 口徑「相對閘吃 server 前值」 |
| F-05 | `screen_engine.py:313` 相對閘失敗同一件事印兩行 WARNING:閘內 `logger.warning` + `_run_attempts` 的「第 n 次取數失敗:{e};HH:MM:SS 再試」把整句 exception 內嵌 → 一行內「盤前篩選 <日>」出現兩次;其他五處 BreadthFetchError 都只 raise 不自印 | LOW | CONFIRMED(LOW→NICE:實跑重現兩行;兩行各帶不同資訊(刪鍵提示 vs 下一次時刻),對帳者不會被誤導,只是冗餘;spec US19 + T5 AC 各要一行,是兩條要求的直譯) | Nice to Have | `auto-fix` | 刪鍵提示搬進 exception 訊息、閘內 `logger.warning` 刪(那句會隨 give-up 行一起印);或 `reason` 不含 `{e}` |
| F-06 | `screen_engine.py:300` + `:321` `prior` 讀兩次(閘決定門檻一次、`_run_once` 落檔前再讀只為印 log),中間隔 `_write_group` await;整輪 `_read_cache` 讀檔 4 次;手動刪鍵時「擋人的前值」與「log 印的前值」可不一致 | LOW | CONFIRMED(LOW→NICE:實測計次一輪 4 讀相符;小 JSON 多讀不可觀測,不一致窗要人在 await 期間手改檔) | Nice to Have | `auto-fix` | `_require_daytrade_complete` 回 `(n, prior)` 或 `_compute_with_daytrade_rows` 一併帶出,`_run_once` 不再自己讀(沿 round-1 F-01 回值姿態) |
| F-07 | `screening.py:55` `data_date_of` 前置「target 為交易日」未言明;CLI `--date 2026-09-05`(週六)→ 資料窗與週一 target 撞窗、當沖 fetch 週六回空 → 錯誤訊息「當沖名單尚無資料(FinMind 未更新?)」把輸入錯講成上游問題 | LOW | CONFIRMED(LOW→NICE:實跑 `data_date_of(週六)` = `data_date_of(週一)` = 09-04;只影響 CLI 手動誤用的訊息,prod 的 target 恆由 `expected_target_date` 產出) | Nice to Have | `auto-fix` | docstring 補前置一句;或 CLI 解析後 `if not cal.is_trading_day(target)` 印明確錯誤 |
| F-08 | `CLAUDE.md:125` §1 表 `screen` 預設值寫「預設今天 / 最近交易日」,交易日 07:59 其實回前一交易日(`expected_target_date(09-01 07:00)` = 08-31);CONTEXT.md:96-100 寫得精確,表沒跟上 | LOW | CONFIRMED(LOW→NICE:文件精度;CLI 會印採用的目標日與資料日,誤用當場可見) | Nice to Have | `auto-fix` | 改「預設 = 排程判定值(交易日 08:00 起 = 今天;之前 / 非交易日 = 前一交易日)」 |
| F-09 | `docs/next-time.md:893` F-09 memo 條「最壞 3 attempts ≈ 全配額 4%」被 T5(時間盒 4–6 次)+ T6(相對閘在 EOD 後)打過時;:199 / :899 / :911 三處本 PR 新增的「(原文:」少收尾括號(各缺 2) | LOW | CONFIRMED(LOW→NICE:backlog 數字與標點;括號配對腳本確認三處皆本 PR 新增) | Nice to Have | `auto-fix` | 補一句「W2 T5 起上限 = 時間盒,T6 相對閘在 21 次 EOD 後才判 → 失敗路徑成本成常態」;三處補 `)` |
| F-10 | `code-review-round-1.json:4` 與 `:16` 頂層 `"spec"` 鍵重複(字串 + 陣列),`json.load` 後字串那份靜默消失;全 repo 371 份 .claude json 唯一重複鍵,既有 6 份用 `spec_source` | LOW | CONFIRMED(LOW→NICE:artifact 元資料,只影響日後回溯) | Nice to Have | `auto-fix` | :4 改鍵名 `spec_source` |
| F-11 | `useMarketBars.ts:102`(同形 `useBreadthRows.ts:52` / `useFuturesBars.ts:137`)`inHours()` 與 `msUntilOpen()` 各自 `new Date()` 兩把鐘:跨 09:01:00 瞬間第一把判盤外、第二把判開點已過 → 回到明天(跨週末 ~72 h);`useStockBars.ts:116-118` 單一 `now` 是唯一做對的 | NICE | CONFIRMED(NICE→NICE:觸發窗 = 開點那一毫秒兩個相鄰語句之間,且函式形 refetchInterval 每 render 重估、盤中 WS 驅動 render 秒級自癒;第二把鐘是本 PR 新增) | Nice to Have | `auto-fix` | 三支各取一次 `const now = new Date()` 傳進兩函式(兩支 API 都吃 optional now),與 useStockBars 同形 |
| F-12 | `useBreadthRows.ts:49`(同形 `useMarketBars.ts:101`)新註解「退訂語意」與同檔 doc 互斥:兩支無 `subscribed`,`active=false` 只停 interval,回前景仍 `refetchOnWindowFocus`(分 K staleTime 0) | NICE | CONFIRMED(NICE→NICE:實查兩支 useQuery 選項無 subscribed、main.tsx QueryClient 無 defaultOptions;用詞誤導但行為正確且刻意) | Nice to Have | `auto-fix` | 改「只停 interval(非退訂,回前景仍會 refetch);切回 tab 那次 render 重新求值」 |
| F-13 | `useStockBars.test.tsx:181-182` R3 接線註解(閉包 data 恆為初值)被新 describe 插在它與原本描述的 SC-4 describe 之間,掛到不屬於它的區塊 | NICE | CONFIRMED(NICE→NICE:git diff 確認 R3 兩行是 context、新 describe 整塊插入其間;R3 理由只對吃 data 的 20 s 空態成立) | Nice to Have | `auto-fix` | 兩行移到 SC-4 describe 正上方 |
| F-14 | `useStockBars.ts:81` `barsPollInterval` 同時吃 `trading` 與 `now` 可矛盾,測試餵矛盾組合(trading=true + now=08:00)隔離分支;函式已依賴 trading-hours,注入 trading 已無隔離價值 | NICE | PARTIAL(NICE→NICE:唯一 prod caller 同源推導、矛盾態不可達;修法 (a) 內算 `inTradingHours(now)` 會讓純函式吃到日曆快取、測試得 stub 日曆,反而違背「抽成純函式才量得到」;(b) doc 註明前置較低風險) | Nice to Have | `auto-fix` | doc 補「`trading` 必須 = `inTradingHours(now)`,測試刻意餵矛盾值只為隔離分支」 |
| F-15 | `test_screen_engine.py:520` `assert not hasattr(eng, "_daytrade_rows_seen")` 白箱只鎖字串,換名重入隱藏通道照樣綠 | LOW | CONFIRMED(LOW→NICE:同案 :518「compute 不印前值 INFO」+ :510-527 payload / 前值保留是行為斷言,F-01 真實危害已蓋;**建議修法不成立**:cache 檔 bytes 比對測的是檔案未被寫,對 instance 屬性通道無感,換上去反而弱於現況) | 參考用 | `no-op` | 現況已有行為斷言;替代寫法更弱,不改 |
| F-16 | `test_screen_engine.py:308-346` `_next_attempt_at` end-exclusive 邊界(nxt == 09:00:00)零覆蓋,`<`→`<=` 突變體存活(TestRetryWindow 時鐘皆落 :30) | LOW | REFUTED(LOW→NICE:實跑突變 `<`→`<=` → **1 failed, 19 passed**,殺手 = `TestTick::test_loop_reruns_immediately_when_a_long_tick_crossed_today_run_time`(07:00:00 整起算,第 12 次落 08:50:00、nxt 恰 = 09:00:00,`sleeps == [600.0]*11` 紅);TestRetryWindow 那組確實不動,但同檔另一案已覆蓋) | 參考用 | `no-op` | 非缺陷;補 08:50:00 案屬冗餘 |
| F-17 | `useFuturesBars.test.ts:156` 保留的姊妹案(180 s 零請求)被改名案(14:54:59 前零請求)完全覆蓋,鑑別力真子集,兩案要同步維護 | NICE | CONFIRMED(NICE→NICE:180 s ⊂ 54 min 59 s 嚴格真子集確認;但 :128-129 註記 + round-1 OBS 明載「原斷言原樣保留」是刻意留證,屬取捨非缺陷) | 參考用 | `no-op` | 刻意留證;要收可改成互補點(active=false 在停輪詢窗),不急 |
| F-18 | `useMarketBars.test.ts:263` 三段式牆鐘 stub 第三份(futures 抽 `stubDayFetchThreeWay` 只 1 caller、market / stock 各自 inline)= W3 B2「D_SNAPSHOT 鷹架三份」的新增量 | NICE | CONFIRMED(NICE→NICE:三份形狀近似但 payload 不同(market / futures 有 meta.partial_last、stock 無 meta),跨檔抽取要先統一回應模型 —— 與 W3 B2 同一件事) | 參考用 | `no-op` | 不在本 PR 動;W3 B2 範圍描述加「三段式定稿 stub」 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: f19b0c46f50eb36f826b action=auto-fix
F-02 finding_uid: c94e0884d80625ef8c07 action=ask-user
F-03 finding_uid: f06f18bab14926f054b1 action=auto-fix
F-04 finding_uid: db693abf882ecc0781f7 action=ask-user
F-05 finding_uid: 8293caa349083f6f694c action=auto-fix
F-06 finding_uid: 9875ae4250a7f51906a0 action=auto-fix
F-07 finding_uid: 2036d60a601a90ad4623 action=auto-fix
F-08 finding_uid: 43ac5347f2adca121140 action=auto-fix
F-09 finding_uid: dc63ddabb9cc27d38185 action=auto-fix
F-10 finding_uid: cfaf1ed4049e2f2413a1 action=auto-fix
F-11 finding_uid: 4db77c5843183bc4e3fe action=auto-fix
F-12 finding_uid: 88251147cf7a2312ae97 action=auto-fix
F-13 finding_uid: 2fd16fb61acbe11239c8 action=auto-fix
F-14 finding_uid: 1312dd9ece9d4bd630c1 action=auto-fix
F-15 finding_uid: cef13ec2212934077668 action=no-op
F-16 finding_uid: e985fd9f0d4adf2adeea action=no-op
F-17 finding_uid: c6ac5a21bdba6f86f351 action=no-op
F-18 finding_uid: d86625a0f3532ecff692 action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 明早要 grep 的判準寫「前值 None」,但 log 永遠印不出這四個字
**File**: `.claude/mod/w2-daily-bars-and-screen-0800/verification.md`
**Line**: 109

**Comment**:
```
這一行是 08:00 制第一個交易日要照著 grep 的驗收判準,寫「log 印『前值 None』」——
但 screen_engine.py 的 _prior_text(None) 回的是「無(用絕對下限)」,WARNING 與 INFO 兩個印點
都走它(round-1 F-08 收修就是把兩處統一成這個字串),所以 grep「前值 None」必 0 命中,
明早會讓人先懷疑功能沒跑。

改成:log 印「當沖名單 n 列(前值 無(用絕對下限))」。
```
#### #2 「每 600 s 共 6 次」只在假時鐘成立;而且名單沒出齊時要先重抓 21 個已定稿的 EOD 才知道
**File**: `copycat/server/screen_engine.py`
**Line**: 59

**Comment**:
```
_run_attempts 是「算 nxt = now + 600 → await sleep(600)」,attempt 自己花的時間沒扣掉;
一個 attempt 是序列抓 21 個 MB 級全市場 EOD(_DAILY_TIMEOUT 60 s)+ 當沖 + 處置,
所以實際節奏 = 600 s + attempt 時長,09:00 前跑得完 4–6 次,不是註解寫死的 6 次
(推算過:150 s/attempt → 5 次、300 s → 4 次;最後一次都落 08:45–08:53,08:40 出的名單仍抓得到,
所以不會「錯過」,只是註解不實 + 白花頻寬)。

更痛的是 _require_daytrade_complete 排在 21 次 EOD 之後(:276):T6 的立論正是「名單常只出一半」,
這條最常走的失敗路徑每次都先把 21 個不會變的過去日 EOD 重下載一遍才發現。

兩條路請拍板:
(a) 把「當沖名單 fetch + 空集合閘 + 回聲閘 + 相對閘」整段提到 EOD 迴圈前 —— 失敗路徑 22 → 1 個請求,
    節奏就真的接近 10 分鐘;_REQ_GAP_SECS 與各閘語意不變、只換順序(內部複查核過既有測試
    test_daily_date_echo_mismatch_raises 的觸發順序不受影響)。
(b) 只改這段註解為「理論 6 次;實際視取數耗時 4–6 次」,fail-fast 併進 next-time F-09 那條。
```
#### #3 這句「後端 cache 命中不打 TC4」跟後端相反,14:01 那發一定要打
**File**: `frontend/src/lib/day-bars-rollover.ts`
**Line**: 44

**Comment**:
```
「成本 = 每天多一發(含非交易日,後端 cache 命中不打 TC4)」—— 後端 daily_get 對「界前寫入
且已過 14:00」的 entry 直接回 None(bars.py:358-359),而常開頁 00:01 那發正好把當日 entry
寫成界前,所以 14:01 這一發**必然** miss,每把 key 每天真的多走一趟 180 日窗 SubHistory;
非交易日拿空手時是 daily_stale 墊背,不是 cache hit。同段下一句自己寫「14:01 那發拿到墊背」
—— 有墊背就是有 fetch,兩句打架。

改成事實就好:「14:01 那發必走上游(界前快照過界作廢是後端設計);TC4 關著時回 daily_stale 墊背
+ 一行 INFO,墊背非空所以不會進 retryEmpty 的 60 s 迴圈」。
```
#### #4 compute() 說自己「純結果、CLI 共用」,但它會拿 server 的前值來擋 CLI 預覽
**File**: `copycat/server/screen_engine.py`
**Line**: 299-300

**Comment**:
```
round-1 把寫入側的隱藏通道拆了,讀取側還在:compute → _require_daytrade_complete →
_cached_daytrade_rows → _read_cache。CLI 那顆 ScreenEngine 不帶 data_dir(cli.py:366-372),
落在 repo-root data/market/premarket_screen.json = prod 那份快取,所以
python -m copycat screen --date <過去某日> 的成敗會看 server 上次成功那天的列數;
被擋時 CLI 沒 try/except 直接 traceback,而 WARNING 給的處置「刪 daytrade_rows 鍵」會順手把
server 的基準也砍掉。機率不高(過去日名單列數跟前值同量級),但 docstring「純結果」四字不成立。

二選一請拍板:
- prior 改由呼叫端傳入,_run_once 給快取值、compute() 給 None(= 只走絕對下限 1,000);
  CLI 與 server 變兩套門檻,docstring 就對了。
- 行為不動,docstring 改口「相對閘會讀 server 前值,CLI 預覽同吃」。
```
#### #5 相對閘擋下時同一件事印兩行,第二行還把第一行整句包進去
**File**: `copycat/server/screen_engine.py`
**Line**: 313

**Comment**:
```
_require_daytrade_complete 先 logger.warning 一行,再 raise 幾乎同文的 BreadthFetchError;
_run_attempts 接到後 reason = f"取數失敗:{e}" 又印一行「第 n 次取數失敗:盤前篩選 <日> 當沖名單
只有 …;HH:MM:SS 再試」→ 同一行裡「盤前篩選 <日>」出現兩次(實跑重現過)。
其他五處 BreadthFetchError 都只 raise 不自印,只有這裡雙印。

最省事:刪鍵提示搬進 exception 訊息、閘內那行 logger.warning 刪掉(提示會跟著
_run_attempts 的那行一起印,give-up 行也帶到)。或者 reason 不要含 {e}。
```
#### #6 prior 讀了兩次,擋人用的跟 log 印的可能不是同一個值
**File**: `copycat/server/screen_engine.py`
**Line**: 300

**Comment**:
```
閘內 _cached_daytrade_rows() 讀一次決定門檻(:300),_run_once 落檔前又讀一次只為印 log(:321),
中間隔著 _write_group 的 await;整輪 _read_cache 讀檔 4 次(實測計次)。有人照 WARNING 指示
手動刪 daytrade_rows 鍵時,log 會印「前值 無」但閘其實是用舊值擋的。

_require_daytrade_complete 已經回列數了,改回 (n, prior) 或讓 _compute_with_daytrade_rows
一併帶出,_run_once 不再自己讀 —— 跟 round-1 F-01 的回值姿態同一套。
```
#### #7 --date 給非交易日時,錯誤訊息會怪到 FinMind 頭上
**File**: `copycat/screening.py`
**Line**: 55

**Comment**:
```
data_date_of 的前提是 target 本身是交易日,docstring 沒寫;CLI 的 --date 直接
date.fromisoformat 零驗證。給 2026-09-05(週六)→ data_date_of 回 09-04,資料窗跟週一 target
完全一樣,接著當沖 fetch 週六回空 → raise「當沖名單尚無資料(FinMind 未更新?)」,
把「你給的日子不是交易日」講成上游沒資料。prod 不受影響(expected_target_date 只回交易日)。

docstring 補一句「前置:target 為交易日(prod 唯一來源 expected_target_date)」;
或 CLI 解析完加 if not cal.is_trading_day(target): 印明確錯誤退出。
```
#### #8 §1 表寫「預設今天 / 最近交易日」,07:59 跑其實是昨天那份
**File**: `CLAUDE.md`
**Line**: 125

**Comment**:
```
預設走 expected_target_date:交易日 07:59 回的是前一交易日(實跑 09-01 07:00 → 08-31)。
那天既不是「今天」,而「最近交易日」在今天就是交易日時最自然的讀法也是今天。
CONTEXT.md 那段寫得精確(「交易日 08:00 起 = 今天,之前 / 非交易日 = 今天之前最近的交易日」),
表沒跟上。CLI 會印採用的日期,所以只是文件精度。

改成「預設 = 排程判定值(交易日 08:00 起 = 今天;之前 / 非交易日 = 前一交易日)」。
```
#### #9 F-09 那條的數字被這批打過時了,另外三處「(原文:」沒收尾
**File**: `docs/next-time.md`
**Line**: 893

**Comment**:
```
(a) 這條寫「最壞 3 attempts ≈ 全配額 4%」—— T5 把三次盒改成時間盒(理論 6 次、實際 4–6 次),
T6 又新增一條排在 21 次 EOD 之後的失敗觸發源,成本量級跟觸發頻率都變了,勾銷五條時沒回頭改。
補一句「W2 T5 起上限 = 時間盒;T6 相對閘在 21 次 EOD 後才判 → 失敗路徑成本成常態」。

(b) :199 / :899 / :911 三處本 PR 新增的「(原文:…」各缺 2 個收尾括號(括號配對腳本掃過;
同批 C17 條與 08-31 期貨條都有收尾,是漏不是風格)。
```
#### #10 這份 JSON 頂層 "spec" 鍵重複,字串那份被 parser 靜默丟掉
**File**: `.claude/mod/w2-daily-bars-and-screen-0800/code-review-round-1.json`
**Line**: 4

**Comment**:
```
:4 的 "spec": "GitHub issue #204 + …拍板…" 跟 :16 的 "spec": [ …findings… ] 同鍵,
json.load 後只剩陣列,「這輪對照哪份 spec / 哪些拍板」整段消失。掃過 .claude 下 371 份 json
只有這一份有重複鍵;既有 6 份 artifact 都是 spec_source(字串)+ spec(陣列)並存。

:4 改鍵名 spec_source 就好。
```
#### #11 這裡讀了兩把鐘,跨 09:01:00 那一毫秒可能算成「明天再說」
**File**: `frontend/src/hooks/useMarketBars.ts`
**Line**: 102

**Comment**:
```
inHours() 跟 msUntilOpen() 各自 new Date():第一把落 09:00:59.999 判盤外、第二把落
09:01:00.000 判「今天開點已過」→ msUntilNextOpen 跳到明天(跨週末最長 ~72 h)。
useBreadthRows.ts:52 / useFuturesBars.ts:137 同形;useStockBars.ts:116-118 取一次 now 再推 trading,
是唯一做對的。實務上下一次 render 就重估回 POLL_MS(盤中 WS 一直在推),所以只是姿態不一致。

三支各取一次 const now = new Date() 傳進兩個函式(兩支 API 都吃 optional now),跟 useStockBars 同形。
```
#### #12 這句「退訂語意」跟同一檔上面的 doc 打架
**File**: `frontend/src/hooks/useBreadthRows.ts`
**Line**: 49

**Comment**:
```
這支跟 useMarketBars 都沒有 subscribed 選項,active=false 只是不排 interval,observer 還訂著;
同檔 :37-40 的 doc 自己寫得很清楚「只停 refetchInterval,不關 enabled …(useFuturesBars 才走 subscribed)」。
新加的行內註解寫「退訂語意」會讓人以為 active=false 期間零背景請求 —— 其實回前景還會
refetchOnWindowFocus(分 K staleTime 0;main.tsx 的 QueryClient 沒關它)。useMarketBars.ts:101 同一句。

改成「只停 interval(非退訂,回前景仍會 refetch);切回 tab 那次 render 重新求值」。
```
#### #13 R3 那兩行註解被新 describe 截斷,掛到不屬於它的區塊上
**File**: `frontend/src/hooks/useStockBars.test.tsx`
**Line**: 181-182

**Comment**:
```
「接線測試(R3):…refetchInterval 若讀閉包裡的 data 會恆為初值」講的是下面
useStockBars 非 ok 空態自動重試接線(SC-4)那組(閉包 data 的 bug 長在 20 s 空態那條路);
新 describe「分 K 盤外自醒」整塊插在中間後,這兩行在版面上變成新 describe 的抬頭,
而 09:01 自醒案跟 data 完全無關。

把這兩行搬到 SC-4 describe 正上方,新 describe 只留自己那行 W2 T3 註解。
```
#### #14 trading 跟 now 兩個參數可以互相矛盾,測試也真的餵了矛盾組合
**File**: `frontend/src/hooks/useStockBars.ts`
**Line**: 81

**Comment**:
```
加了 now 之後,barsPollInterval 同時吃「已判好的 trading」跟「原始時刻 now」,型別上可以矛盾;
測試 :159/:165/:171 就用 trading=true 配 now=08:00 來隔離分支。唯一 prod caller(:116-118)
是同一個 now 推出來的,矛盾態到不了 prod。內部複查也核過:改成函式內算 inTradingHours(now)
會讓純函式吃到日曆快取、測試得再 stub 日曆,反而違背「抽成純函式才量得到」的初衷。

所以只補 doc:「trading 必須 = inTradingHours(now)(呼叫端同源);測試刻意餵矛盾值只為隔離分支」。
```
## 沒做的部分（結案對帳）
- Codex 中性軸:N-A —— user 明示停用(09-05 起 per-PR override,沿 #188 / #190 / #199 / #202 前例),未起軸、未 retry。
- Codex 對抗式軸:N-A —— 同上。
- Gemini Flash 軸:N-A —— user 明示停用。Gemini Pro:N-A(同上;Step 2.96 依前例不再問)。
- Step 2.98 Codex preset 詢問:N-A(Codex 停用,依前例不再問)。
- Cross-axis verification 4.1:N-A(無非 CC finding)。4.2:以同軸 code-reviewer 內部複查代替(PASS,18/18),**非跨軸證據** —— 14 條 CONFIRMED 全來自同一模型家族,user 讀 Nice to Have 時應據此下調權重。
- Review input binding:**unverified** —— PR headRefOid `dfdc149d` 已被 rebase merge 改寫且分支刪除,無法在任何 ref 上 checkout;審的是 master range `de192ca3..5b8c8b01`(gh 回報的 mergeCommit),與 PR head 逐檔內容等價但 SHA 不同;報告標題不宣稱 Reviewed SHA。
- Primary reviewer 派法偏離 Step 3「pick exactly one」:兩語言各 ~50% 無主語言,依 chunk 語言各派專屬 reviewer(python / typescript)而非 generic `code-reviewer` ×2;聯集覆蓋 F 全集、零重疊,不影響 4.5 coverage 算術。
- Blast radius(2.9):PASS(有跑)但空輸出跳過。
- React-doctor(2.97):PASS,未引入新問題(newCount 0)。
- Formal spec traceability(2.65):SKIPPED (C4_NO_SPEC_DOCUMENT);spec-compliance-reviewer 未派。
- Author calibration(2.2):無檔、本輪無套用。
- Reviewer 未實跑前端測試 / 型別:review worktree 無 `node_modules`,typescript-reviewer 純讀碼;前端綠燈證據引自 PR 內 `verification.md`(出貨前實跑 vitest 3046 / tsc 0 / eslint 0 / react-doctor 0);後端三個觸及測試檔由 chunk A reviewer 實跑 120 passed、內部複查另跑整檔 + 一次突變。
- 未驗前提(集中揭露):F-02 的「實際 4–6 次」建立在 attempt 時長 150–300 s 的**假設值**上(EOD 單發實測時長未量,只有 `_DAILY_TIMEOUT=60` 上界)—— 明早 08:00 制第一個交易日 log 的「HH:MM:SS 再試」間隔即可實錄,拍板 (a)/(b) 前先看這個;F-04 的「被擋機率極低」是量級推論;F-11 的「秒級自癒」依賴盤中 WS 驅動 render,開盤前 08:xx 的加權頁無推播時要靠計時器本身重估(仍成立,因 TQ 在 interval 到期後會重算)。
- 真環境:本 PR 出貨時即標 prod 重啟 + `npm run build`(dist 已於 merge 後重 build)後的下一交易日判準(`verification.md` §6);本 review 亦未驗。
- Self-Verify:已執行(`skill-verify-auditor`,requested=opus / observed=UNAVAILABLE;唯讀、只 Read 本草稿檔一次,2 tool 呼叫)。結果 R1–R10 全 PASS、`VERDICT: COMPLIANT`,輸出格式完整(十行 + 一行 verdict、順序正確、無 FAIL)→ 零修正,直接發布。
