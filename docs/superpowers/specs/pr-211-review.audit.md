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

## Spec 依據

- 此 PR 未附 spec / plan **檔**(Step 2.6 heuristic 對 25 檔零命中:`docs/next-time.md`、`.claude/mod/w2-daily-bars-and-screen-0800/verification.md` / `code-review-round-1.json` 的路徑與檔名皆不符 specs / plans / *-spec.md 規則)。實質 spec = **GitHub issue #204**(Problem / Solution / 24 條 User Stories / Implementation Decisions / Testing Decisions / Out of Scope / Further Notes 含**既有行為白名單**與 backward compat)+ tickets #205–#210(各自 AC)+ 對話拍板(_RETRY_UNTIL 09:00;402 = 當日放棄,#209 已留言校正;T4「睡到下一交易日」實作為每日曆日醒 + 非交易日 tick 零動作;T2 事前標為該變實數 9 條)。**⚠️ spec 作者 = PR 作者**(同一 session 寫入;out-of-scope 判定以此 spec 為據時注意利益重疊)。
- Out of Scope 五項(盤中即時最後一根 / 墊背自救 / 當沖資格顯示 / bars.py 定稿界值與快取結構 / useIndexOverlay 與 useGroupSnapshots 行為)本輪逐條核過**零碰**(chunk B 逐檔驗;`git diff --stat` 無 bars.py)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_SPEC_DOCUMENT`(spec 在 issue tracker 而非 repo 檔,無可綁定 `path:line` 的 MUST / SHALL / INVARIANT 條款)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool call count=N-A(未派);0 clauses / 0 findings / 0 observations / 0 invalidated。
- Author calibration(Step 2.2):無作者校準檔(`loger-w.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

provenance: N-A(base = master,25 檔全 authored)。

| 檔案 | 類型 | 說明 |
|---|---|---|
| `frontend/src/lib/trading-hours.ts` | 修改 | T1:`msUntilNextOpen(now, opens)` 共用骨架;新 `msUntilFuturesTradingOpen`(08:46)/ `msUntilFuturesAllDayOpen`(08:40 / 14:55)/ `offHoursInterval`(秒級量化 + 1 s 下限);`msUntilTradingOpen` 改走候選表 |
| `frontend/src/lib/trading-hours.test.ts` | 測試 | 三個新 describe(13 案:窗前 / 收盤後 / 跨週末 / 假日 / 14 天窮盡 / 與 `in*Hours` 起點同尺 / 量化) |
| `frontend/src/hooks/useGroupSnapshots.ts` | 🔵 重構 | `groupPollInterval` 盤外量化改用 `offHoursInterval`(既有測試不改仍綠) |
| `frontend/src/lib/day-bars-rollover.ts` | 修改 | T2:日 K 新鮮度政策加第二道界 14:00 定稿界 + slack(兩界各取「第一個嚴格在後」的最小);export `DAILY_FINAL_TIME = [14, 0]` 供後端 parity |
| `frontend/src/hooks/useFuturesBars.ts` / `useMarketBars.ts` / `useStockBars.ts` | 修改 | T2 只改註解口徑(午夜 → 兩道界);T3 分 K 盤外回距開點 ms(futures 近全時段開點 / market 依 isIndex 分流 09:01 或 08:46 / stock `barsPollInterval` 加 `now` 參數) |
| `frontend/src/hooks/useBreadthRows.ts` | 修改 | T3:盤外回 `offHoursInterval(msUntilTradingOpen())`,`active=false` 仍 false |
| `frontend/src/hooks/useIndexOverlay.ts` | 文件 | 只加註解:其 false 是「資料健康」不是時段閘,刻意不動 |
| `frontend/src/hooks/useFuturesBars.test.ts` / `useMarketBars.test.ts` / `useStockBars.test.tsx` / `useBreadthRows.test.ts` | 測試 | T2 各一條 14:00 界案 + 9 條事前標為該變(期貨 4 / 加權 3 / 個股 2);T3 各一至兩條盤外自醒案;`barsPollInterval` 三案改型 + 量化案 |
| `copycat/screening.py` | 修改 | T4:`RUN_TIME` 21:00 → 08:00;`expected_data_date` → `expected_target_date`(回目標交易日);新 `data_date_of`(前一交易日) |
| `copycat/server/screen_engine.py` | 修改 | T4 目標交易日制(compute 吃目標日、EOD 窗自資料日往回、當沖 / 處置用目標日、快取 v2、`tick()` / `_due()`);T5 重試時間盒 `_RETRY_UNTIL` 09:00、402 當日放棄、WARNING 降級;T6 相對閘 0.8 / 絕對下限 1,000 / `daytrade_rows` 落檔 / `_read_cache` 收一份;round-1 收修(`_compute_with_daytrade_rows` 回值、`_give_up`、`_prior_text`) |
| `copycat/cli.py` | 修改 | `screen --date` 改為目標交易日並印資料日 |
| `copycat/server/app.py` | 文件 | 註解 21:00 → 08:00 一行 |
| `tests/test_screening.py` | 測試 | 排程判定兩案事前標為該變(08:00 / 目標交易日)+ `data_date_of` |
| `tests/server/test_screen_engine.py` | 測試 | compute 三 fetcher 日期 / 快取 v2 / `TestTick`(含 S-01 `_loop` 案)/ `TestRetryWindow` 五案 / `TestDayTradeRelativeGate` 四案;`_engine` helper `Fetch` 別名 + `daytrade_floor` |
| `tests/server/test_bars.py` | 測試 | `test_daily_final_time_parity_with_frontend`(直讀前端字面釘等值) |
| `CLAUDE.md` / `CONTEXT.md` | 文件 | §0 / §1 改口 08:00 制;§4 新契約「日 K 定稿界前後端同值」;CONTEXT.md「盤前篩選」節兩詞(目標交易日 / 資料日) |
| `docs/next-time.md` | 文件 | 五條勾銷(C16 / C18 / C21 / C22 / F-01)+ 2026-09-08 節四條留尾 |
| `.claude/mod/w2-daily-bars-and-screen-0800/verification.md` / `code-review-round-1.json` | 新增 | gate 兩輪數字、紅→綠、10 突變體、spec 逐條對、真環境判準;分支自身 two-axis round-1(13 條 + 1 觀察)處置 |

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

#### #15 這條 hasattr 斷言是白箱,但建議的替代寫法會更弱 —— 不用改

**File**: `tests/server/test_screen_engine.py`
**Line**: 520

**Comment**:
```
不是 PR 缺陷。assert not hasattr(eng, "_daytrade_rows_seen") 確實只鎖一個字串,
換名重新引入 instance 通道照樣綠;但同案 :518「compute 不印前值 INFO」+ :510-527 的 payload /
前值保留是行為斷言,round-1 F-01 的真實危害已被蓋住。reviewer 建議的「compute 前後 cache 檔 bytes
逐字相等」測的是檔案沒被寫,對 instance 屬性通道完全無感,換上去反而更弱。維持現況。
```

#### #16 「<= 突變體存活」實跑是被殺的,S-01 那條測試恰好守到 nxt == 09:00:00

**File**: `copycat/server/screen_engine.py`
**Line**: 164

**Comment**:
```
不是 PR 缺陷。內部複查真的把 `nxt < deadline` 改成 `<=` 跑整檔:1 failed, 19 passed,
殺手是 TestTick::test_loop_reruns_immediately_when_a_long_tick_crossed_today_run_time ——
它從 07:00:00 整起算,第 12 次落在 08:50:00、nxt 恰 = 09:00:00,突變體多排一段 sleep 讓
sleeps == [600.0]*11 紅。TestRetryWindow 那組時鐘都落 :30 確實碰不到邊界,但同檔另一案已覆蓋,
再補 08:50:00 起算案屬冗餘。
```

#### #17 這條姊妹案的鑑別力是改名案的真子集,留著是刻意留證

**File**: `frontend/src/hooks/useFuturesBars.test.ts`
**Line**: 156

**Comment**:
```
不是 PR 缺陷。姊妹案(週三 14:00 → 180 s 零請求)跟改名案(同起點 → 14:54:59 前零請求)
setup 逐字相同,180 s ⊂ 54 min 59 s,任何讓姊妹案紅的突變體必先讓改名案紅。
但 :128-129 註記 + round-1 OBS 明載「原斷言原樣保留在下方姊妹案」是刻意的「事前標為該變」留證。
要收的話可改成互補點(active=false 在停輪詢窗仍零請求 —— 現在 :180 那條測的是夜盤 22:00),不急。
```

#### #18 三段式牆鐘 stub 又多了一份,併進 W3 B2 那條就好

**File**: `frontend/src/hooks/useMarketBars.test.ts`
**Line**: 263

**Comment**:
```
不是 PR 缺陷。useFuturesBars.test.ts 抽了 stubDayFetchThreeWay(只 1 個 caller),
這裡跟 useStockBars.test.tsx:324 各自 inline 同一份 d1 / afterFinal / partial_last 邏輯。
三份 payload 不同(market / futures 有 meta.partial_last、stock 是 {bars,status}),跨檔抽要先統一
回應模型 —— 正是 W3 B2「三支 hook 測試鷹架抽 fixture」那條,把「三段式定稿 stub」加進它的範圍描述即可。
```

## CC 主軸原始 findings(first-pass, context-aware)

### Section A — chunk A findings(python-reviewer,逐字要點;reviewer 原編號 → 發現總覽:R-A1→F-02、R-A2→F-05、R-A3→F-06、R-A4→F-04、R-A5→F-07、R-A6→F-15、R-A7→F-16、R-A8→F-08、R-A9→F-09、R-A10→F-01、R-A11→F-10)

前置:讀過 spec #204(Out of Scope / 白名單)、tickets #207 / #209 / #210、backend-conventions、CLAUDE.md §4、round-1 json 13 條處置;round-1 收修逐條核到位(F-01 欄位已刪、F-03 `_RETRY_UNTIL`、F-04 402 明講、F-08 `_prior_text`、S-01 `_due()`、S-05 INFO 落檔後)。實跑 `pytest tests/server/test_screen_engine.py tests/test_screening.py tests/server/test_bars.py -q` → 120 passed。揭露:spec 作者 = PR 作者。

#### R-A1 [MEDIUM] screen_engine.py:56-61, 237-276 — 重試盒「每 600 s、共 6 次」只在假時鐘下成立;每 attempt 重抓 21 個 MB 級 EOD
- Problem:sleep 固定 `_RETRY_SECS`,attempt 時長(21 × `fetch_daily_prices`,`_DAILY_TIMEOUT=60` 註解自陳 MB 級;+ 當沖 + 處置,序列 + `_REQ_GAP_SECS`)不扣;相對閘 `_require_daytrade_complete` 在 21 次 EOD 之後(:276),而「名單沒出齊」是預期最常走的失敗路徑。
- Impact:log 間隔不是 10 分鐘;09:00 前實際 3–4 次而非 6 次;08:40 才出名單那天可能錯過。配額最壞 6×23 ≈ 2.2%,痛在時間頻寬。
- Fix:(a) fail-fast —— 當沖 fetch + 空集合閘 + 回聲閘 + 相對閘提到 EOD 迴圈前(22 → 1 請求;`test_daily_date_echo_mismatch_raises` 因 fixture 名單健康仍綠);(b) 沿 breadth `_streak_memo`(next-time F-09)。至少改 :58-61 註解。
- Search-proof:`grep -n "def fetch_daily_prices" -A 25 copycat/server/breadth_fetch.py` → 無 data_id、`timeout=_DAILY_TIMEOUT`;spec Out of Scope 不含重試成本;白名單只要求 `_REQ_GAP_SECS` 不變;`docs/next-time.md:893` F-09 未勾;測試 `_install_fake_sleep` 只由 sleep 推進時鐘。
- anchor:`#: 每 600 s → 08:00:30 … 08:50:30 共 6 次。**402 配額用盡不重試、當天直接放棄**(round-1 F-04 / S-02:`

#### R-A2 [LOW] screen_engine.py:302-315 — 相對閘失敗同一件事印兩行 WARNING
- Problem / Impact / Fix / Search-proof:見 F-05;`grep -n "raise BreadthFetchError"` → 218 / 250 / 259 / 262 / 274 / 312,只有 312 配自己的 warning。
- anchor:`f"盤前篩選 {target} 當沖名單只有 {n} 列(前值 {self._prior_text(prior)},門檻 {floor}),"`

#### R-A3 [LOW] screen_engine.py:300 + 321 — `prior` 讀兩次,`_read_cache` 整輪 4 次
- 見 F-06。anchor:`prior = self._cached_daytrade_rows()` / `self._write_cache(target, final, written, daytrade_rows)`

#### R-A4 [LOW] screen_engine.py:222-229, 296-300 — `compute()` docstring「不改引擎狀態」但讀引擎快取,CLI 預覽吃 prod 前值
- 見 F-04。Search-proof:`grep -n "ScreenEngine(" copycat/cli.py` → 382 未傳 data_dir;`screen_engine.py:102-106` `_dir` fallback = repo-root `data/market`。anchor:`n = len(dt_rows)` / `prior = self._cached_daytrade_rows()`

#### R-A5 [LOW] screening.py:55-58(+ cli.py:377-381)— `data_date_of` 前置條件未言明,CLI `--date` 不驗
- 見 F-07。Search-proof:`grep -rn "data_date_of" .` → cli.py:390、screen_engine.py:236/394。anchor:`def data_date_of(target: _dt.date, cal: TradingCalendar) -> _dt.date:`

#### R-A6 [LOW] test_screen_engine.py:520 — `hasattr` 斷言白箱
- 見 F-15。anchor:`assert not hasattr(eng, "_daytrade_rows_seen")`

#### R-A7 [LOW] test_screen_engine.py:308-346 — end-exclusive 邊界零覆蓋,`<`→`<=` 突變體存活
- 見 F-16。Search-proof:`grep -n "8, 5[05]"` → 只有 `_dt.time(8, 50, 30)`。anchor:`<none>`(symbol `TestRetryWindow.test_fails_every_10_min…`;實作 screen_engine.py:164)

#### R-A8 [LOW] CLAUDE.md:125 — `screen` 預設值措辭
- 見 F-08。anchor:`| 盤前篩選(手動/預覽) | … 預設今天 / 最近交易日;資料日 = 其前一交易日自動推);`

#### R-A9 [LOW] docs/next-time.md:893(+ :199 / :899 / :911)— F-09 數字過時;三處「(原文:」少收尾
- 見 F-09。Search-proof:`grep -n "(原文:" docs/next-time.md` → 199 / 899 / 911 段末無 `)`。anchor:`- [ ] **screen_engine 跨 attempt memo + disposition fail-fast**(review F-09,MED→LOW PARTIAL):… 最壞 3 attempts ≈ 全配額 4% …`

#### R-A10 [LOW] verification.md:109 — 判準字面「前值 None」與 code 不符
- 見 F-01。Search-proof:`screen_engine.py:293-294` `_prior_text`;`grep -rn "前值 None" copycat/` → 0。anchor:`… log 印「前值 None」。`

#### R-A11 [LOW] code-review-round-1.json:4, 16 — 頂層 `"spec"` 鍵重複
- 見 F-10。Search-proof:全 repo 156 份 round-1 json 唯一重複鍵;既有用 `spec_source`。anchor:`"spec": "GitHub issue #204 + tickets #205-#210 + 對話拍板(…)",`

### Section B — chunk B findings(typescript-reviewer,逐字要點;R-B1→F-03、R-B2→F-11、R-B3→F-14、R-B4→F-12、R-B5→F-17、R-B6→F-13、R-B7→F-18)

前置:spec #204 / #205–#208 已讀;round-1 前端 F-02 / F-05 / OBS 收修到位。無 node_modules 未跑 vitest / tsc。結論:無 Must / Should;行為面算術與時序全部成立(兩界取最小 5 個測點、`msUntilFuturesAllDayOpen` 與 `inFuturesAllDayHours` 不漏窗證明、六案算式逐條驗算)。

#### R-B1 [LOW] day-bars-rollover.ts:44 — 成本註解與後端實際路徑相反
- 見 F-03。Search-proof:bars.py:354-418 / :569-585 逐段;`_warn_if_not_advanced` 有 `bars[-1]["t"] == day` 閘。anchor:` *    三張圖是同一個後端界。成本 = 每個掛著的日 K query 每天多一發(含非交易日,後端 cache 命中不打 TC4)。`

#### R-B2 [NICE] useMarketBars.ts:75-77,102 — 兩把 `new Date()`
- 見 F-11。anchor:`      return inHours() ? POLL_MS : offHoursInterval(msUntilOpen());`

#### R-B3 [NICE] useStockBars.ts:73-81 — `trading` 與 `now` 可矛盾
- 見 F-14。anchor:`  return trading ? POLL_MS : offHoursInterval(msUntilTradingOpen(now));`

#### R-B4 [NICE] useBreadthRows.ts:49(同形 useMarketBars.ts:101)— 「退訂語意」與 doc 矛盾
- 見 F-12。anchor:`    // \`active=false\` 仍回 false(退訂語意:切回 tab 那次 render 重新求值)`

#### R-B5 [NICE] useFuturesBars.test.ts:156-165 — 姊妹案被改名案完全覆蓋
- 見 F-17。anchor:`  it("停輪詢窗(週三 14:00)三個輪詢週期內零請求(既有斷言,回值不再是 false 但 55 分內不打)", async () => {`

#### R-B6 [NICE] useStockBars.test.tsx:181-184 — R3 註解被新 describe 截斷
- 見 F-13。anchor:`// 接線測試(R3):純函式綠不足以證明 refetchInterval 真的吃它 —— TanStack v5 函式形`

#### R-B7 [NICE] useMarketBars.test.ts:256-266 — 三段式牆鐘 stub 第三份
- 見 F-18。anchor:`        const afterFinal = now.getHours() >= 14;`

### Section C — per-file accounting(25/25;chunk A 12 + chunk B 13)

| 檔 | 結果 |
|---|---|
| `copycat/cli.py` | finding(R-A5);其餘 REVIEWED_NO_ISSUES(rename 全鏈無殘留) |
| `copycat/screening.py` | finding(R-A5) |
| `copycat/server/app.py` | REVIEWED_NO_ISSUES(純註解 1 行;wiring 三道停用閘未動) |
| `copycat/server/screen_engine.py` | findings(R-A1 / A2 / A3 / A4) |
| `tests/server/test_bars.py` | REVIEWED_NO_ISSUES(parity 姿態與既有一致;regex 抓不到有明確 assert 訊息;釘等值與 §4 同口徑) |
| `tests/server/test_screen_engine.py` | findings(R-A6 / A7);`monkeypatch asyncio.sleep` 全域同款屬既有慣例 |
| `tests/test_screening.py` | REVIEWED_NO_ISSUES(兩條事前標為該變與 spec 逐字對得上) |
| `CLAUDE.md` | finding(R-A8);§0 / §4 新契約五要素齊 |
| `CONTEXT.md` | REVIEWED_NO_ISSUES(兩詞與 code 一致,Avoid 對到最易混的誤用) |
| `docs/next-time.md` | finding(R-A9) |
| `.claude/mod/w2-daily-bars-and-screen-0800/verification.md` | finding(R-A10) |
| `.claude/mod/w2-daily-bars-and-screen-0800/code-review-round-1.json` | finding(R-A11) |
| `frontend/src/lib/day-bars-rollover.ts` | finding(R-B1);兩界取最小算術逐點追過 |
| `frontend/src/lib/trading-hours.ts` | REVIEWED_NO_ISSUES(不漏窗證明;doc「14 個日曆日」與 `d <= 14` 差一,不值得改) |
| `frontend/src/lib/trading-hours.test.ts` | REVIEWED_NO_ISSUES(六案算式驗算全對;同尺釘住 round-1 F-02) |
| `frontend/src/hooks/useBreadthRows.ts` | finding(R-B4) |
| `frontend/src/hooks/useBreadthRows.test.ts` | REVIEWED_NO_ISSUES(active=false 跨 09:01 仍零請求案補到新格) |
| `frontend/src/hooks/useMarketBars.ts` | findings(R-B2 / R-B4 同形);白名單(日 K 不吃 active、retryEmpty true)未動 |
| `frontend/src/hooks/useMarketBars.test.ts` | finding(R-B7);事前標為該變 3 條與拍板一致 |
| `frontend/src/hooks/useStockBars.ts` | finding(R-B3);20 s 空態優先次序、retryEmpty false 未動 |
| `frontend/src/hooks/useStockBars.test.tsx` | finding(R-B6);事前標為該變 2 條一致 |
| `frontend/src/hooks/useFuturesBars.ts` | REVIEWED_NO_ISSUES(近全時段開點接線正確;subscribed + gcTime 未動) |
| `frontend/src/hooks/useFuturesBars.test.ts` | finding(R-B5);事前標為該變 4 條一致 |
| `frontend/src/hooks/useGroupSnapshots.ts` | REVIEWED_NO_ISSUES(`offHoursInterval` 與原內聯式逐字等價) |
| `frontend/src/hooks/useIndexOverlay.ts` | REVIEWED_NO_ISSUES(只加註解;消費端 MarketChart 同掛 useMarketBars,註解更站得住) |

## Codex 原始 findings

N-A —— Codex 中性 / 對抗式軸皆未啟用(user 明示停用)。

## Gemini 原始 findings

N-A —— Gemini Flash / Pro 皆未啟用(user 明示停用)。

## CC 對非 CC 軸的複查結果(Step 4.1)

N-A —— 無非 CC finding。

## 內部複查結果(Step 4.2 之替代;同軸 code-reviewer、非跨軸證據)

批次一輪、18/18 回 verdict、ID 集合精確等於輸入、每列 verdict / corrected_severity / severity_reason / evidence / fix_assumption / cross_file_context 六欄齊;複查者實跑:pytest 三檔、一次 `<`→`<=` 突變(還原並刪 pyc)、`_run_attempts` log 重現、`_read_cache` 計次、`data_date_of` / `expected_target_date` 直呼。**注意:同軸(CC)內部複查,不構成跨軸證據**;Must Fix 候選來源中的「Codex CONFIRMED verifications of Opus findings」本輪不存在。

| # | reviewer | title | Verdict | 原始 → 校正 severity | 內部複查 evidence(要點) | 修法假設核 | 備註 |
|---|---|---|---|---|---|---|---|
| F-01 | python-reviewer | verification.md 判準「前值 None」 | CONFIRMED | LOW→LOW | `_prior_text(None)` = 「無(用絕對下限)」,WARNING :304-311 / INFO :324-326 皆走它;round-1 F-08 收修後判準未改口 | 成立(一行文件) | 4.3b:cross_file_context = yes;明早驗收字串 |
| F-02 | python-reviewer | 重試盒 6 次不實 + 相對閘在 EOD 後 | PARTIAL | MED→LOW | :198-207 sleep 固定 600 不扣 attempt 時長 ✓;閘在 :276(EOD 迴圈 :240-264 後)✓;`_DAILY_TIMEOUT=60` ✓;**但** 150 s/attempt → 5 次、300 s → 4 次,最後一次皆 08:45–08:53,08:40 名單仍抓得到 → 「錯過」refuted;頻寬成本 = next-time F-09 既有留尾 | 成立(`_engine` daytrade_floor 預設 1、echo 案當沖 fixture 健康,重排不改觸發順序) | 4.3b:yes;實際後果 = 註解不實 + 頻寬 |
| F-03 | typescript-reviewer | 成本註解與後端相反 | CONFIRMED | LOW→NICE | bars.py:354-359 `daily_get` 界前 entry 過界回 None;`daily_put` :379-383 界前必記;14:01 那發必 miss → build_daily :408-412 真 fetch;同段 :45-46「拿到墊背」自相矛盾 | 成立(純註解) | 4.3b:yes |
| F-04 | python-reviewer | compute 讀 prod 快取,CLI 預覽被擋 | PARTIAL | LOW→NICE | cli.py:366-372 無 data_dir → screen_engine.py:102-106 fallback repo-root ✓;docstring :223 三個否定句皆真,只「純結果」可質疑;過去日列數與前值同量級、被擋機率極低;刪鍵確重置 server 基準 | 成立但兩套門檻;docstring 改口成本更低 | 4.3b:yes |
| F-05 | python-reviewer | 相對閘雙印 WARNING | CONFIRMED | LOW→NICE | 實跑重現兩行(前值 2000 / 今日 1500 / now 08:55);:190 `reason = f"取數失敗:{e}"` 內嵌整句;其他五處只 raise | 半成立(US19 + T5 AC 各要一行;收成一行得把提示搬進 exception) | 4.3b:no |
| F-06 | python-reviewer | prior 讀兩次 | CONFIRMED | LOW→NICE | monkeypatch `_read_cache` 計次:一次成功 tick = 3 讀,`_loop` 回來 `_due` +1 = 4 ✓;:320 `await _write_group` 確為 await 點 | 成立(無其他讀者依賴 :321) | 4.3b:no |
| F-07 | python-reviewer | `data_date_of` 前置未言明 | CONFIRMED | LOW→NICE | 實跑 `data_date_of(週六)` = `data_date_of(週一)` = 09-04(撞窗);cli.py:377-381 零驗證;:274 訊息怪 FinMind | 成立(兩法不衝突) | 4.3b:yes |
| F-08 | python-reviewer | CLAUDE.md §1 預設值措辭 | CONFIRMED | LOW→NICE | `expected_target_date(09-01 07:00)` = 08-31;CONTEXT.md:96-100 精確;cli.py:386 印採用值 | 成立 | 4.3b:yes |
| F-09 | python-reviewer | F-09 數字過時 + 三處括號 | CONFIRMED | LOW→NICE | :893 數字 vs T5 時間盒 ✓;括號腳本:199 / 899 / 911 各缺 2、皆本 PR + 行;舊條目慣例不加括號(:47-49) | 成立 | 4.3b:no |
| F-10 | python-reviewer | round-1.json `spec` 鍵重複 | CONFIRMED | LOW→NICE | `object_pairs_hook` 掃 371 份:唯一重複鍵;`json.loads` 後 `type(d['spec'])` = list;6 份用 `spec_source` | 成立 | 4.3b:yes |
| F-11 | typescript-reviewer | 兩把鐘 | CONFIRMED | NICE→NICE | :102 兩次 `new Date()`;msUntilNextOpen :39 `<=` 跳過今天 → 明天(跨週末 ~72 h);同形 useBreadthRows:52-53 / useFuturesBars:137;useStockBars:116-118 單一 now;函式形每 render 重估自癒;第二把鐘是本 PR 新增 | 成立 | 4.3b:yes |
| F-12 | typescript-reviewer | 「退訂語意」與 doc 互斥 | CONFIRMED | NICE→NICE | 兩支 useQuery 無 `subscribed`(只 useFuturesBars:113 有);main.tsx:16 QueryClient 無 defaultOptions → refetchOnWindowFocus true;分 K staleTime 0 | 成立 | 4.3b:no |
| F-13 | typescript-reviewer | R3 註解錯位 | CONFIRMED | NICE→NICE | git diff:R3 兩行為 context,新 describe 插在其與 SC-4 之間;R3 理由只對吃 data 的 20 s 空態成立 | 成立 | 4.3b:no |
| F-14 | typescript-reviewer | `trading` + `now` 可矛盾 | PARTIAL | NICE→NICE | 唯一 prod caller :116-118 同源;測試 :147-166 確餵矛盾組合;(a) 內算會吃日曆快取、測試要 stub | 半成立(doc 註明較低風險) | 4.3b:yes |
| F-15 | python-reviewer | `hasattr` 白箱 | CONFIRMED | LOW→NICE | :520 確白箱;但 :518 行為斷言 + :510-527 payload / 前值保留已蓋 F-01 危害 | **不成立**:bytes 比對對 instance 屬性通道無感,替換更弱 | 4.3b:no |
| F-16 | python-reviewer | end-exclusive 邊界零覆蓋 | REFUTED | LOW→NICE | 實跑 `<`→`<=`:1 failed / 19 passed,殺手 `TestTick::test_loop_reruns_immediately…`(:219-256,07:00:00 整起算、第 12 次 08:50:00、nxt == 09:00:00、`sleeps == [600.0]*11` 紅);已還原 + 刪 pyc、`git status` clean | 不成立(補案冗餘) | 4.3b:yes |
| F-17 | typescript-reviewer | 姊妹案被覆蓋 | CONFIRMED | NICE→NICE | 180 s ⊂ 54 min 59 s 嚴格真子集(反向突變 200 s / 3600 s 姊妹案綠、改名案紅);:128-129 + round-1 OBS 刻意留證 | 成立(取捨) | 4.3b:no |
| F-18 | typescript-reviewer | 三段式 stub 第三份 | CONFIRMED | NICE→NICE | `grep -c 'stubDayFetchThreeWay('` = 2;market :262-266 / stock :324-326 inline;payload 不同需先統一回應模型 | 成立(不在本 PR 動) | 4.3b:yes |

複查順手核到、**不列 finding**(不在 18 條範圍且 diff 未觸及該行):`copycat/server/breadth_fetch.py:12-13` 模組 doc 仍寫「402 … 呼叫端改走長退避」,與本 PR 把 402 改成當日放棄後的 screen_engine 事實不符(breadth_engine 自己仍走退避,doc 對 breadth 仍對、對 screen 不對);`copycat/server/screen_engine.py:62-63` `_REQ_GAP_SECS` doc 仍寫「~60 次資格查」(pr-175 F-02 後已收斂成 1 次)。兩者屬「註解落後於行為」,可併 F-02 / F-09 同批收。

### Step 4.3a consensus baseline check

N-A —— 本輪單軸,無 consensus finding。

### Step 4.3b lone-finding 判斷

本輪只有 CC 一軸(兩個 chunk reviewer 各審不同檔,零重疊),18 條全為 lone finding,「他軸為何漏」在單軸情境下無意義(N-A);改記「是否依賴跨檔脈絡」(diff-only 讀者會不會漏),列於上表備註欄:yes 11 條(F-01 / F-02 / F-03 / F-04 / F-07 / F-08 / F-10 / F-11 / F-14 / F-16 / F-18)、no 7 條。`effective_severity` 一律取 `corrected_severity`:LOW 2(F-01 判準字串、F-02 節奏註解 + 閘位置)、NICE 16。無安全類 finding,severity-calibration 矩陣不適用。

## Action Items

**Severity calibration**:6c Refactor Intent Gate N-A(本 PR 無「移除 / 削弱既有防護」類 finding;T5 把三次盒換時間盒是拍板的契約變更,F-02 講的是新盒的註解與閘位置,不是拿掉防護)。6d-1 hedge cap:F-11「跨 09:01:00 那一毫秒」與 F-04「過去日可能被擋」皆假設情境 → ≤ Should Fix(實際落 Nice);F-16 的「突變體存活」被實跑反證。6d-3 Must Fix 雙半條件:18 條皆無 user-visible 且 release-blocking 的後果(F-02 的「錯過名單」被推算反證後只剩註解不實 + 頻寬;F-01 是驗收字串)→ 零 Must / 零 Should。Provenance cap N-A(base = master)。未驗證前提檢查:F-02 的節奏推算(150 s / 300 s per attempt)是**假設值**,實際 attempt 時長待明早 log 實錄(見沒做的部分);F-04 的「被擋機率極低」是量級推論非實測;其餘 finding 的 severity 建立在第一手 file:line / 實跑輸出上。

**校準套用**:無作者校準檔(`loger-w.md` 不存在)、本輪無套用。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

無。

### Nice to Have(可選優化)

- F-01 `verification.md:109` 判準字串改「當沖名單 n 列(前值 無(用絕對下限))」—— **明早驗收前先改**,純文件。
- F-02 `screen_engine.py` **拍板**:(a) 當沖 fetch + 三道閘提到 EOD 迴圈前(fail-fast)/ (b) 只改註解 + 併 next-time F-09;不論哪條,:59 註解「共 6 次」改「理論 6 次、實際視取數耗時 4–6 次」。
- F-03 `day-bars-rollover.ts:44` 成本註解改事實(14:01 必走上游;TC4 關著回墊背不進 retryEmpty)。
- F-04 `screen_engine.py` **拍板**:prior 由呼叫端傳入(CLI 走絕對下限)/ 只改 docstring 口徑。
- F-05 `screen_engine.py:304-315` 雙印收一行(提示搬進 exception 訊息、閘內 warning 刪;或 reason 不含 `{e}`)。
- F-06 `screen_engine.py` `_require_daytrade_complete` 回 `(n, prior)`,`_run_once` 不再自己讀。
- F-07 `screening.py:55` docstring 補「target 為交易日」前置;或 CLI 驗 `is_trading_day`。
- F-08 `CLAUDE.md:125` 預設值改寫為排程判定值三段口徑。
- F-09 `docs/next-time.md:893` 補 T5 / T6 後的成本敘述;:199 / :899 / :911 補 `)`。
- F-10 `code-review-round-1.json:4` 鍵名改 `spec_source`。
- F-11 `useMarketBars.ts:102` / `useBreadthRows.ts:52` / `useFuturesBars.ts:137` 各取一次 `now` 傳兩函式。
- F-12 `useBreadthRows.ts:49` / `useMarketBars.ts:101` 註解改「只停 interval(非退訂,回前景仍會 refetch)」。
- F-13 `useStockBars.test.tsx:181-182` R3 註解移到 SC-4 describe 上方。
- F-14 `useStockBars.ts:73-81` doc 補「`trading` 必須 = `inTradingHours(now)`;測試刻意餵矛盾值」。

### 參考用(內部複查 REFUTED / 修法不成立 / 刻意取捨)

- F-15 CC[python-reviewer] 擔心 `hasattr` 斷言白箱 → 內部複查於同案 :518 / :510-527 找到行為斷言已蓋 F-01 危害,且建議的 bytes 比對對 instance 通道無感(更弱)→ 不改。
- F-16 CC[python-reviewer] 擔心 end-exclusive 邊界零覆蓋 → 內部複查實跑 `<`→`<=` 突變被 `TestTick` S-01 案殺(1 failed)→ 非缺陷、補案冗餘。
- F-17 CC[typescript-reviewer] 擔心姊妹案冗餘 → 真子集屬實,但 :128-129 + round-1 OBS 明載刻意留證 → 取捨非缺陷,要收改成互補點不急。
- F-18 CC[typescript-reviewer] 擔心三段式 stub 第三份 → 屬 W3 B2 鷹架項新增量,payload 不同需先統一回應模型 → 不在本 PR 動,W3 B2 範圍加一句。

## 審查工具比較 (qualitative)

- CC 視角(context-aware,chunked ×2):18 條裡 **零行為錯誤** —— 兩個 reviewer 都把本批的核心算術(兩界取最小、三支開點同尺、不漏窗、時間盒)逐點追過並確認成立;抓到的是四類邊角:(1) 註解 / 文件與 code 事實脫節(F-01 / F-03 / F-08 / F-09 / F-12 / F-13,其中 F-01 是明早就要用的驗收字串)、(2) 新機制的成本與位置(F-02 相對閘在 21 次 EOD 之後、F-06 重讀、F-05 雙印)、(3) CLI 預覽路徑的未揭露副作用(F-04 / F-07)、(4) 測試強度 / 冗餘(F-14 / F-15 / F-16 / F-17 / F-18)。與分支自身 round-1(13 條)相比,本輪抓到的是 round-1 收修後的殘留(F-01 是 F-08 收修沒同步到判準、F-06 是 F-01 回值化後留下的第二次讀、F-10 是 round-1 artifact 自己的鍵名)。
- Codex 中性 / 對抗式:N-A(user 停用),無重疊率可算。
- Gemini:N-A(user 停用)。
- 內部複查結果分佈(4.2 替代、同軸):CONFIRMED 14 / PARTIAL 3 / REFUTED 1 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0;REFUTED 率 5.6%,校正後 LOW 2 / NICE 16(F-02 MED→LOW 因「錯過名單」被推算反證、F-03 等 9 條 LOW→NICE 因後果只在文件 / log / 測試面)。複查者另實跑一次突變體反證了 F-16 的「零覆蓋」主張 —— 這是本輪內部複查最有價值的一筆。
- 對抗式第三軸增益:N-A。
- React-doctor 機械軸:0 新引入(newCount 0 / fixedCount 0 / baseTotalCount 0)。

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
