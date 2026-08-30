# PR #151 Code Review 比較報告 · SHA 989d7cbb

**Report projection schema**: 1

**PR**: [loger-w/copycat#151](https://github.com/loger-w/copycat/pull/151)
**標題**: fix(frontend): 期貨日 K 跨日曆日重抓 —— preview 整天掛著跨午夜後 CDP / MA 基準日不再停在前一天
**作者**: loger-w(display name XU MIN YU;commits 署名 Loger)
**分支**: `fix/futures-daily-bars-rollover` → `master`(PR 狀態 MERGED,merge commit d5d69e1a;遠端分支已刪、回溯 review)
**變更**: 9 檔案, +402 / -10
**審查日期**: 2026-08-30
**Review input basis**: source repo R_kgDOTsITBg + 989d7cbbc4b9fdaadef6906a43bf9cab6c3a24cd;destination repo R_kgDOTsITBg + 09cc3e63700cce399cd777c0510ee1bc417220f4;`input_binding: verified`(遠端分支 merge 後已刪,以 `git fetch origin refs/pull/151/head` 取得 FETCH_HEAD = headRefOid 逐字相等;`git worktree add --detach` 於該 SHA,worktree HEAD = source SHA;destination SHA `git cat-file -t` = commit、`git merge-base origin/master 989d7cbb` = 09cc3e63 = destination SHA,`git merge-base --is-ancestor` 成立;diff 一律 `09cc3e63...989d7cbb` 不用移動的 branch ref)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前 23:18 `gh pr view 151` 重抓 headRefOid / baseRefOid 與 reviewed 完全相同、state MERGED;origin/master 因本 PR merge 與後續 commit 前進到 25312d79,不影響 PR 的 destination 綁定);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-151`(detached)
**worktree HEAD**: 989d7cbbc4b9fdaadef6906a43bf9cab6c3a24cd
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC 軸 finding;4.2 N-A 無 codex → 全部 CC finding INCONCLUSIVE,由 4.3b 主 agent 逐條實查,含對 F-01 修法建議的拋棄式 vitest 模擬四例)+ Gemini 軸 N-A(本機無 agy)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewer=typescript-reviewer × 1(未切塊;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位;tool_uses=40、subagent_tokens≈168k、13.4 min);domain reviewers=N-A(security-reviewer 未觸發:diff 無 auth / 請求體 / 憑證 env);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(未 dispatch);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=9 → covered 6 / no-issues 2 / skipped 1 / **missed 0**(chunked: 否;FILE_COUNT=5 源檔 ≤ 15 且 DIFF_LINES=412 ≤ 800;reviewer 逐檔 accounting 9/9,零 repair 輪)
**定位 (ENH-B)**: anchored exact 9 / ambiguous 0 / **FAILED 0**(9 個 anchor 以 python 對 worktree 檔案逐行全等比對,皆唯一命中;line 以比中結果為準,reviewer 自報行號全部一致)
**React-doctor (2.97)**: 未引入新問題(既有 0 條不計)—— worktree 內 `npx -y react-doctor@latest . --offline --no-score --scope changed --base 09cc3e63 --json` exit 0、`newCount 0 / fixedCount 0 / baseTotalCount 0`、changedFileCount 5、reactDetected true
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_CLAUSE_CANDIDATE)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh <worktree> origin/master` exit 0 零輸出;由 reviewer grep 補:`useFuturesBars(` caller = FuturesChart.tsx:164/170 + App.tsx:193;`FuturesChart` 唯一掛載點 FuturesPage.tsx:144、無 memo)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(xu-min-yu.md / loger-w.md 皆不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,9 檔全部 authored)
**審查軸狀態**: primary(typescript-reviewer)PASS(10 條 finding、9/9 accounting、對 `@tanstack/query-core@5.101.2` 寫獨立模擬腳本實跑 A/B 兩案);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification:4.1 N-A / 4.2 FAIL→INCONCLUSIVE(無 codex)/ 4.3b PASS(主 agent 直讀 TQ 原始碼 `useBaseQuery.js:69-70` / `queryObserver.js:112-118, 208-218` / `query.js:127-137` / `focusManager.js:9-18`,並以主 tree vitest 拋棄式模擬四例驗證 F-01 與修法建議;9 條 CONFIRMED、reviewer 10 條中 TS-2 併入 F-02、其餘一對一)
**Finding record 欄位**: 發現總覽表格後每行 `F-nn finding_uid: <20-hex> action=<action>` 為 canonical internal record —— `F-nn` = `display_ordinal`(表格與 inline block 同編號)、`finding_uid` = sha256(file path + verbatim anchor + normalized root cause)[:20](選取與 mutation 用它,不用編號)、`action` 與表格 Action 欄同值、`action_reason` 即表格「Action 理由」欄
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus,tools=0,32 s)回 R1–R10 全 PASS、`VERDICT: COMPLIANT`(格式核驗:恰 10 行、順序固定、FAIL 集合空 = verdict 一致);稽核輸入 = 草稿全文逐字內嵌(含全部 9 個 inline block,未摘要);無修正、未重派

**Report generation**: sha256:7538e216e6abbbb7f95ae020d138fdc1b3ed3c6a938aa9ffc809194a2496187b

---

## Spec 依據

- 此 PR 未附正式 spec／plan 文件(F 內無 `/specs/` `/plans/` 路徑、無 `*-spec.md` 檔名、無 frontmatter type)。意圖依據 = (1) `docs/next-time.md` 08-24 節原條「期貨日 K `staleTime: Infinity` 跨日不重抓 → 基準日停在昨天」(候選:staleTime 改到下一個交易日切換點,或 queryKey 帶交易日);(2) PR 內 `.claude/bug/futures-daily-bars-rollover/diagnosis.md`(六 phase:H1 `staleTime: Infinity` + 不輪詢 / H2 後端 `build_period` cache 鍵 = `date.today()` → 界取日曆午夜 / H3 queryKey 帶日期否決);(3) handoff `%TEMP%\copycat-handoff-2026-08-29-work-queue.md` §1c(seam = `frontend/src/hooks/*.test.ts`)。
- 意圖文件作者:diagnosis.md 與 next-time 條目皆由 PR 作者(同一 session 的 agent)所寫 → ⚠️ spec 作者 = PR 作者(out-of-scope 判定以此為據時注意利益重疊;本輪唯一用它排除的是「後端 15:01–24:00 快照」留尾,該留尾經 reviewer 與主 agent 對 `bars.py:430-433` 核實為真)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_NORMATIVE_CLAUSE_CANDIDATE`(F 內無任何含 MUST / SHALL / NEVER / INVARIANT / FORMULA 型可綁定條款的文件;diagnosis.md 為敘事型診斷紀錄,未進 reducer —— 零候選即無 `resolve-authority` 可呼叫)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、tools=0;0 clauses / 0 findings / 0 observations / 0 invalidated。

## 變更概要

Provenance:base = master,9/9 authored(N-A)。

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `frontend/src/hooks/useFuturesBars.ts` | 行為改動 | 日 K query 的 `staleTime`(以 `dataUpdatedAt` 起算)/ `refetchInterval`(以 `Date.now()` 起算)由 `Infinity` / `false` 改成函式形式吃 `msUntilDayRollover`(下一個本機日曆日 00:00 + 60 s slack);error 態 `refetchInterval` 回 60 s;分 K 分支逐字等價(重排成早退) |
| `frontend/src/lib/trading-calendar.ts` | 新增 | 純函式 `msUntilNextLocalDate(from: Date)`:到下一個本機日曆日 00:00 的毫秒數 |
| `frontend/src/components/futures/FuturesChart.tsx` | 註解 | 「一天只打一次」→「同一日曆日只打一次、跨午夜重抓一次」 |
| `frontend/src/hooks/useFuturesBars.test.ts` | 測試 | 新 describe 五條(一直在 tab 跨午夜 / 切走跨午夜再切回 / 背景分頁跨午夜回前景 / 兩個午夜恰兩發 / 午夜失敗 60 s 重試)+ `focusManager` afterEach 還原 + `isoLocalDate` import |
| `frontend/src/lib/trading-calendar.test.ts` | 測試 | helper 三例(22:00 → 2 h / 恰午夜 → 整天 / 23:59:59.500 → 500 ms) |
| `docs/next-time.md` | 文件 | 08-24 L408 與索引勾銷;新增 08-30 節三條留尾(後端夜盤段快照 / worktree App 級 vitest flake 判讀 / overlay hooks 跨日靠 render 時翻鍵) |
| `.claude/bug/futures-daily-bars-rollover/diagnosis.md` | artifact | 六 phase 診斷紀錄 |
| `.claude/bug/futures-daily-bars-rollover/verification.md` | artifact | gate 指令 + exit code + 真實環境判準(留 08-31) |
| `.claude/bug/futures-daily-bars-rollover/code-review-round-1.json` | artifact | 分支內 two-axis review round 1:11 條全接受收修 + 增量快篩 |

## 發現總覽

| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | 日 K 的 `refetchInterval` 以 `Date.now()` 起算,而 TQ v5 每一次 render 都 `setOptions` → 值逐毫秒不同 → 計時器 clear + 重排;已過午夜但還沒到 +60 s slack 的那 60 秒內任一重繪,回的是「到明天午夜」≈ 24 h → 原本排在 00:01:00 的那一發被推到隔天。`FuturesChart` 無 memo、`state` 吃期貨 WS(0.1 s coalesce),午夜正在夜盤 → 60 秒內約 600 次 render **必中**;TQ `focusManager` 只聽 `visibilitychange`,整夜可見的分頁沒有回焦退路 → **主情境(人一直在期貨 tab 上跨午夜)沒修好**,只有「切走再切回」與「背景分頁回前景」兩條真的修好(`frontend/src/hooks/useFuturesBars.ts`) | HIGH [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(主 agent 直讀 TQ 原始碼 + 主 tree vitest 模擬:現碼 slack 窗內每 100 ms 一次 rerender → 09:00 仍 1 發) | Must Fix | `auto-fix` | 修法一行且經模擬驗證:`msUntilDayRollover` 改成「下一個 00:00+slack 嚴格在 from 之後」(`msUntilNextLocalDate(new Date(from - DAY_ROLLOVER_SLACK_MS))`),重繪與「15:00 退訂 → 20:00 切回」兩路徑都 00:01 準時;reviewer 建議的 `q.state.dataUpdatedAt` 版在切回路徑實測晚到 11:02(漂 11 h),不採 |
| F-02 | 同根因的第二個後果:改動前日 K 分支恆回 `false`、分 K 恆回離散值,`nextRefetchInterval !== #currentRefetchInterval` 恆假 → 零計時器 churn;改動後日 K 回逐毫秒變的數 → 期貨 tab 開著時每次 render 一組 `clearInterval` + `setInterval`(每秒約 10 組,兩個 observer 同鍵 ×2);註解只寫「每次結果落地都重新求值」,漏了「每次 render 也重算」—— 正是 F-01 沒被發現的原因(`frontend/src/hooks/useFuturesBars.ts`) | MEDIUM [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(機制同 F-01;reviewer 模擬 10 分鐘每 100 ms 一次 render:6003 次 vs 零 render 5 次) | Nice to Have | `ask-user` | F-01 的正確修法(R2)保留 `Date.now()` 起算,churn 不會消失;消 churn 的 `dataUpdatedAt` 版有切回漂移(F-01 模擬 C)。取捨 = 接受每秒 ~10 組計時器增刪(單次 µs 級)並把註解補「render 也重算」,或加秒級量化(`Math.ceil(ms / 1000) * 1000`,churn 降到 1/s、到點最多晚 1 s)—— 由 user 拍板 |
| F-03 | 留尾清單把兩支真正同形的 hook 漏掉了:`useMarketBars.ts:69`(`staleTime: isMinute ? 0 : Infinity`、queryKey 無日期)與 `useStockBars.ts:95`(`staleTime: isDaily ? Infinity : 0`、`["stock-bars", code, "D"]` 無日期)與修前 `useFuturesBars` 逐字同形、既沒修也沒記;被記下來的 `useIndexOverlay` / `useStockOverlay` 反而**有**日期在 queryKey(`isoLocalDate(new Date())`),風險等級不同(`docs/next-time.md`) | MEDIUM [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(主 agent grep 四支 queryKey / staleTime 逐字核對) | Nice to Have | `auto-fix` | 純文件修正:08-30 節補一條點名 `useMarketBars.ts:69` / `useStockBars.ts:95` 同形未修(台股綜合 tab 日 / 週 / 月 K 與個股日 K 整天掛著同樣停在昨天;個股 overlay 走後端 `date < today` 不受影響),並修正 overlay 兩支「有日期鍵」的描述;兩支 hook 的 code 修法沿 F-01 R2 另開 |
| F-04 | 註解「TQ `isStaleByTime` 對 `!updatedAt` 直接判過期」寫錯了機制:`query.js:128` 實際看的是 `this.state.data === void 0`,`dataUpdatedAt` 只在第三條 `timeUntilStale` 才用到;round-1 刪 `from <= 0` 守衛的理由正是這句話。結論在本 repo 成立(無 `initialData` / `setQueryData`),但機制寫錯;順帶 `msUntilDayRollover(0)` 實際回 57,660,000(epoch 在台北 = 08:00)(`frontend/src/hooks/useFuturesBars.ts`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(主 agent 直讀 `query.js:127-137`) | Nice to Have | `auto-fix` | 一行註解改成「`state.data === undefined` 直接判過期(`query.js:128`);本 query 無 `initialData`,`data` 有值 ⇔ `dataUpdatedAt > 0`」 |
| F-05 | error 重試註解說「拿分 K 的 60 s 同口徑」,但分 K 那條包著 `inFuturesAllDayHours()` 時段閘、error 分支沒有,且 `retry: 1` 讓每輪其實是兩發 → TC4 整個週末沒開 + 期貨 tab 開著 = 每分鐘兩發 503 無退避無上限;round-1 增量快篩已知情,但碼上註解會讓讀者以為有閘(`frontend/src/hooks/useFuturesBars.ts`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(`queryObserver.js:214-218` interval → `#executeFetch` → `retry: 1` 兩發;同族 `useIndexOverlay` error 輪詢同樣無閘,非破例) | Nice to Have | `auto-fix` | 註解改口「與分 K 的 60 s 數值相同但不吃時段閘 —— 失效方向選『多打』不選『整天不救』(週末 TC4 未開時每分鐘兩發 503,已知情)」;要不要加閘 / 退避是產品取捨,預設不加 |
| F-06 | `FuturesChart.tsx:167` 註解宣稱「跨午夜重抓一次」,而這個元件自己每則 WS 訊息重繪一次正是吃掉那一發的原因(F-01);且 `mode === "day"` 時 `useFuturesBars(product, mode)` 與 `useFuturesBars(product, "day")` 完全同鍵掛兩個 observer,各自維護一組會 churn 的 interval → F-02 次數 ×2(請求不翻倍:in-flight 共用 `#retryer.promise`)(`frontend/src/components/futures/FuturesChart.tsx`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(主 agent grep:`FuturesPage.tsx:144` 唯一掛載、無 `memo(` 邊界;`useFuturesStream.ts:72/99` 每則訊息 `setState`) | Nice to Have | `auto-fix` | F-01 修好後這句才成立;順序上先修 hook,再把註解改成「跨午夜由 `msUntilDayRollover` 負責,判準見該處」 |
| F-07 | 四條跨午夜測試綠,但 `renderHook` 的 wrapper 在推進期間不重繪(查詢落地後 observer 不再通知)→ slack 窗內 `setOptions` 一次都不會被呼叫,而生產路徑那 60 秒約 600 次;測試 1 與測試 5 的斷言結構上不可能紅在 F-01 這一維,round-1 背書的三個突變體(固定 24 h / slack=0 / 拔 error 分支)全落在盲區之外 —— 測試名「人一直在期貨 tab 上」正好是它唯一測不到的情境(`frontend/src/hooks/useFuturesBars.test.ts`) | MEDIUM [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(主 agent 以同 seam 加 `rerender({ tick })` 每 100 ms 一次 40 s → 現碼 09:00 仍 1 發,證明缺口為真且補法可紅) | Nice to Have | `auto-fix` | 補一條紅測試:00:00:10 起每 100 ms `rerender` 40 秒,斷言 00:01:01 仍變 2 發;現碼必紅、R2 必綠(主 tree 模擬 A / B 已實跑);與 F-01 同一輪收修 |
| F-08 | 診斷紀錄 Phase 4 列了三支 TQ 內部函式,沒列 `setOptions`(`queryObserver.js:112-118`)與 `useBaseQuery` 的 per-render effect —— 正是 F-01 機制所在;`focusManager.isFocused()` 只看 `visibilitychange` 沒寫清楚;Phase 6 blast radius 只列 overlay 兩支(見 F-03)(`.claude/bug/futures-daily-bars-rollover/diagnosis.md`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(主 agent `grep setOptions diagnosis.md` 零命中) | Nice to Have | `auto-fix` | 補兩點(per-render `setOptions` 路徑、`focusManager` 只聽 `visibilitychange`)+ Phase 6 補 `useMarketBars` / `useStockBars` |
| F-09 | 驗證紀錄「真實環境」第 1 條判準(00:01:00 ± 數秒出現一發 `tf=D`)寫得對,但依 F-01 它會失敗(期貨 tab 開著 = 那 60 秒有重繪);同文件 mutation 表 M1/M2/M3 全殺會被讀成「界已釘牢」,而三個突變體共用 F-07 的 seam 盲區(`.claude/bug/futures-daily-bars-rollover/verification.md`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(推論鏈全部落在 F-01 / F-07 第一手證據上) | Nice to Have | `auto-fix` | 保留第 1 條當紅燈判準;mutation 表旁註明「三個突變體共用 render 盲區」;F-07 新測試落地後重跑 mutation |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: f89474d9916714ae44f1 action=auto-fix
F-02 finding_uid: ad20419f4b57dcb54911 action=ask-user
F-03 finding_uid: 41cb38a2f7541181eee5 action=auto-fix
F-04 finding_uid: 8b12b0513d8f0a8a33ba action=auto-fix
F-05 finding_uid: 1a5c25e1a0bbd862e9fe action=auto-fix
F-06 finding_uid: 103684d4c01f14680672 action=auto-fix
F-07 finding_uid: 9d9b876e7267ab3b4c70 action=auto-fix
F-08 finding_uid: 09376eb0219fd8bb9a7f action=auto-fix
F-09 finding_uid: c896b31948ade85c73b7 action=auto-fix

### Inline Comments per Finding（直接複製貼到 PR review）

#### F-01 午夜過後那 60 秒只要畫面重繪一次,「午夜那一發」就被推到隔天 —— 主情境沒修好
**File**: `frontend/src/hooks/useFuturesBars.ts`
**Line**: 151

**Comment**:
```
refetchInterval 回的是 msUntilDayRollover(Date.now()),而 TanStack v5 的 useBaseQuery 每一次 render 都
observer.setOptions(...)(useBaseQuery.js:69-70);值逐毫秒不一樣 → queryObserver.js:115-118 判「interval 變了」
→ #updateRefetchInterval 先 clearInterval 再 setInterval。平常這只是 churn(remaining 每次重算都對),
但 00:00:00–00:01:00 這 60 秒內 msUntilNextLocalDate 已經是「到明天午夜」+60 s ≈ 24 h
→ 排在 00:01:00 的那一發被清掉、改排到 D+2 00:01。FuturesChart 沒 memo、state 吃期貨 WS(0.1 s coalesce),
午夜正是夜盤 → 那 60 秒約 600 次 render,必中;focusManager 只聽 visibilitychange(focusManager.js:9-18),
整夜可見的分頁沒有回焦退路 → 「人一直在期貨 tab 上跨午夜」這條(PR 的主情境)實際上還是停在昨天。
主 tree vitest 模擬:00:00:10 起每 100 ms rerender 40 秒 → 隔天 09:00 tf=D 仍只 1 發。

修法一行:把界定義成「下一個 00:00+slack 嚴格在 from 之後」,slack 窗內目標就不會跳到隔天:

export function msUntilDayRollover(from: number): number {
  // 界 = 下一個「00:00 + DAY_ROLLOVER_SLACK_MS」且嚴格在 from 之後;
  // from 落在 00:00–00:01 之間時回的是「到今天 00:01」,不是「到明天」
  return msUntilNextLocalDate(new Date(from - DAY_ROLLOVER_SLACK_MS));
}

refetchInterval / staleTime 兩處呼叫不用動。模擬結果:slack 窗內每 100 ms rerender → 00:01:01 恰 2 發;
「09:00 抓 → 15:00 退訂 → 20:00 切回」→ 00:01:01 恰 2 發。
⚠ 不要改成 msUntilDayRollover(q.state.dataUpdatedAt):值雖然跨 render 穩定,但 setInterval 的週期是從
「重新武裝的時刻」起算 —— 同一路徑模擬 20:00 切回時武裝了 15 h,那一發晚到 11:02 才打(漂 11 h)。
配套:test 1 補「slack 窗內 rerender」那條紅測試(見 F-07),現碼必紅、這個改法必綠。
```

#### F-02 日 K 每次重繪都 clear + set 一次計時器,master 上是零次
**File**: `frontend/src/hooks/useFuturesBars.ts`
**Line**: 145

**Comment**:
```
改動前日 K 分支恆回 false、分 K 恆回 60_000 / false → nextRefetchInterval !== #currentRefetchInterval 恆假,
零計時器 churn;現在日 K 回一個逐毫秒變的數 → 每次 render 一組 clearInterval + setInterval,
期貨 tab 開著每秒約 10 組(FuturesChart 同鍵掛兩個 observer,×2)。單次成本 µs 級、不影響正確性,
但這條註解只寫「每次結果落地都重新求值」,漏了「每次 render 也重算」—— F-01 就是躲在這句後面。

F-01 的正確修法(從 Date.now() 起算)不會消掉 churn;要消掉得用 dataUpdatedAt 起算,但那版有切回漂移。
兩個選擇:(a) 接受 churn、註解補上「render 也重算」;(b) 秒級量化
  return Math.ceil(msUntilNextLocalDate(new Date(from - DAY_ROLLOVER_SLACK_MS)) / 1000) * 1000;
churn 降到每秒 1 組、到點最多晚 1 s。要哪個你拍板。
```

#### F-03 留尾清單點名的兩支不是同病,真正同病的兩支沒被記到
**File**: `docs/next-time.md`
**Line**: 13

**Comment**:
```
這條記的 useIndexOverlay / useStockOverlay 其實都有日期在 queryKey(useIndexOverlay.ts:25 / useStockOverlay.ts:15
的 isoLocalDate(new Date())),跨日至少會翻鍵。跟修前 useFuturesBars 逐字同形的是另外兩支:
- useMarketBars.ts:69  staleTime: isMinute ? 0 : Infinity,queryKey 沒日期 → 台股綜合 tab 的日 / 週 / 月 K
- useStockBars.ts:95   staleTime: isDaily ? Infinity : 0,queryKey ["stock-bars", code, "D"] 沒日期 → 個股頁日 K
整天掛著跨午夜,這兩張圖的日 K 一樣停在昨天(個股 overlay 走後端 date < today,不受影響;症狀只在 K 線本身)。

補一條點名這兩支(修法沿 F-01 的 msUntilDayRollover),並把 overlay 那兩支改寫成「有日期鍵、只在 re-render 時翻,
風險較低」。
```

#### F-04 這行註解把 TanStack 的過期判準寫錯了,而刪守衛的理由正是這句
**File**: `frontend/src/hooks/useFuturesBars.ts`
**Line**: 67

**Comment**:
```
query.js:127-137 的 isStaleByTime 第一條是 if (this.state.data === void 0) return true; —— 看的是 data 是不是
undefined,不是 !updatedAt;dataUpdatedAt 要到第三條 timeUntilStale 才用到。結論在這把 query 成立
(沒有 initialData / placeholderData / setQueryData,data 有值 ⇔ dataUpdatedAt > 0),但機制寫錯,
下次有人加 initialData 會照這句推論「沒資料一定過期」而漏掉一條路。順帶:msUntilDayRollover(0)
實際回 57,660,000(epoch 在台北是 1970-01-01 08:00),不是 0。

改成:尚無資料不用守:TQ isStaleByTime 對 state.data === undefined 直接判過期(query.js:128);
本 query 無 initialData,data 有值 ⇔ dataUpdatedAt > 0。
```

#### F-05 寫「跟分 K 同口徑」,但分 K 有時段閘、這條沒有,而且每輪是兩發
**File**: `frontend/src/hooks/useFuturesBars.ts`
**Line**: 72

**Comment**:
```
分 K 那條的 60 s 外面包著 inFuturesAllDayHours();error 分支的 60 s 沒任何閘,retry: 1 又讓每輪 = 本體 + 一次
retry = 兩發 → TC4 整個週末沒開 + 期貨 tab 開著 = 每分鐘兩發 503,無退避無上限。round-1 增量快篩已經知情、
成本也真的不高,但碼上這句「同口徑」會讓讀的人以為有閘。

註解改口就好:與分 K 的 60 s 數值相同,但不吃時段閘 —— 失效方向選「多打」不選「整天不救」
(週末 TC4 未開時每分鐘兩發 503,已知情)。真要省可加 inFuturesAllDayHours() 或指數退避,預設不加。
```

#### F-06 這句「跨午夜重抓一次」在這個元件裡正好是假的
**File**: `frontend/src/components/futures/FuturesChart.tsx`
**Line**: 167

**Comment**:
```
依 F-01,FuturesChart 每則 WS 訊息重繪一次(FuturesPage.tsx:144 唯一掛載、沒 memo;useFuturesStream 每則 setState)
正是把午夜那一發吃掉的原因,所以這句在修好 F-01 之前不成立。另外 mode === "day" 時
useFuturesBars(product, mode) 和 useFuturesBars(product, "day") 完全同鍵掛兩個 observer,各自一組會 churn 的
interval(請求不翻倍,in-flight 共用 promise;翻倍的是計時器增刪)。

順序上先修 hook,這句再留;保守一點改成「跨午夜由 msUntilDayRollover 負責,判準見該處」。
```

#### F-07 四條跨午夜測試綠,但 seam 天生量不到「重繪」這一維
**File**: `frontend/src/hooks/useFuturesBars.test.ts`
**Line**: 307

**Comment**:
```
renderHook 的 wrapper 在 advanceTimers 期間不會重繪(查詢落地後 observer 沒新通知),所以 slack 窗內
setOptions 一次都不會被呼叫 —— 生產路徑那 60 秒約 600 次。測試 1 / 測試 5 因此結構上不可能紅在 F-01,
round-1 用來背書的三個突變體(固定 24 h / slack=0 / 拔 error 分支)也都在這個盲區外。
名字叫「人一直在期貨 tab 上」的那條,正好是它唯一測不到的情境。

補一條(主 tree 已實跑過形狀,現碼必紅):
  const { rerender } = renderHook(({ tick }) => { void tick; return useFuturesBars("TXF", "day"); },
    { initialProps: { tick: 0 }, wrapper: wrapper(newClient()) });
  await vi.advanceTimersByTimeAsync(0);
  await vi.advanceTimersByTimeAsync(15 * 60 * 60_000 + 10_000);          // 00:00:10
  for (let i = 1; i <= 400; i += 1) { rerender({ tick: i }); await vi.advanceTimersByTimeAsync(100); } // → 00:00:50
  await vi.advanceTimersByTimeAsync(11_000);                               // 00:01:01
  expect(urls.filter((u) => u.includes("tf=D")).length).toBe(2);
F-01 的改法落地後再把 M1 / M2 / M3 三個突變體重跑一次。
```

#### F-08 診斷紀錄的儀器清單漏掉 setOptions,盤點清單漏掉兩支同形 hook
**File**: `.claude/bug/futures-daily-bars-rollover/diagnosis.md`
**Line**: 28

**Comment**:
```
Phase 4 列了 #computeRefetchInterval / #updateStaleTimeout / resolveStaleTime 三支,沒列 setOptions
(queryObserver.js:112-118)和 useBaseQuery 每 render 一次的 effect(useBaseQuery.js:69-70)—— F-01 就在那裡。
另外 focusManager.isFocused() 的實作只聽 visibilitychange(不是視窗 focus),這決定 F-01 有沒有退路,
紀錄沒寫清楚。Phase 6 的 blast radius 只列 overlay 兩支,真正同形的是 useMarketBars / useStockBars(F-03)。

補這三點,下一個照紀錄復盤的人才不會踩同一個盲區。
```

#### F-09 驗證紀錄把唯一能抓到這個 bug 的檢查排到 08-31,而那條檢查會失敗
**File**: `.claude/bug/futures-daily-bars-rollover/verification.md`
**Line**: 24

**Comment**:
```
「真實環境」第 1 條(00:01:00 ± 數秒出現一發 tf=D)判準寫得對,但依 F-01 它會失敗:期貨 tab 開著 = 那 60 秒
有重繪 = 那一發被推到隔天。同一份文件的 mutation 表(M1 / M2 / M3 全殺)則會被讀成「界已釘牢」,
可是三個突變體共用 F-07 那個 seam 盲區,給的是假信心。

保留第 1 條當紅燈判準;mutation 表旁註明「三個突變體都在 render 這一維之外」;
F-07 新測試落地後重跑 mutation,再更新這張表。
```

### Opus 原始 findings (first-pass, context-aware)

typescript-reviewer(dispatch model=opus)回 10 條;TS-2「計時器 churn」與 TS-1 同根因不同後果,主 agent 併為 F-02 獨立列(reviewer 本來就分開列,未合併)。逐條原文摘要(severity / file:line / problem / impact / fix / search-proof):

- **TS-1**(HIGH)`useFuturesBars.ts:149-151` —— `refetchInterval` 以 `Date.now()` 起算 + TQ 每 render `setOptions` 重排 → slack 窗內重繪把午夜那一發推到隔天;主情境沒修好。impact:CDP / MA 基準日還是停在昨天。fix:改吃 `q.state.dataUpdatedAt`(主 agent 4.3b 實測此修法有切回漂移,改採 R2,見 F-01)。search-proof:`grep "useFuturesBars("` → FuturesChart.tsx:164/170、App.tsx:193;`grep FuturesChart` → FuturesPage.tsx:144 唯一掛載、無 memo;`useFuturesStream.ts:86-104` 每則 WS setState。mechanism_trace:對 `@tanstack/query-core@5.101.2` 獨立模擬(假時鐘 + `timeoutManager.setTimeoutProvider` + 手動 `setOptions`):slack 窗零 render → 2 發;有 render → 1 發。
- **TS-2**(MEDIUM)`useFuturesBars.ts:145-146` —— 連續值 interval → 每 render 一組 clear + set。search-proof:`grep refetchInterval` 同族三支皆回離散值,本 PR 全庫首例。mechanism_trace:10 分鐘每 100 ms render:6003 次 vs 5 次。
- **TS-3**(MEDIUM)`docs/next-time.md:13-15` —— 留尾清單漏 `useMarketBars.ts:69` / `useStockBars.ts:95`,列到的 overlay 兩支有日期鍵。search-proof:`grep staleTime frontend/src --include=*.ts | grep -v test` 六命中逐支讀 queryKey。
- **TS-4**(LOW)`useFuturesBars.ts:67` —— 註解誤述 `isStaleByTime` 判準。search-proof:`grep "initialData\|placeholderData\|setQueryData" | grep futures-bars` 零命中;`query.js:127-137` 直讀。
- **TS-5**(LOW)`useFuturesBars.ts:72-74` —— error 重試「同口徑」但無時段閘、每輪兩發。search-proof:同族 `useMarketBars` / `useStockBars` 有閘、`useIndexOverlay` error 輪詢無閘。
- **TS-6**(LOW)`FuturesChart.tsx:165-167` —— 註解「跨午夜重抓一次」在本元件為假;同鍵兩 observer churn ×2。search-proof:`grep "<FuturesChart"` / `grep "memo("` 零命中。
- **TS-7**(MEDIUM)`useFuturesBars.test.ts:307-309` —— seam 量不到 render 維度;M1/M2/M3 全在盲區外。search-proof:`grep rerender` 只有測試 3 切訂閱;frontend-testing SKILL.md:49 未涵蓋「render 次數影響 TQ 計時器」。
- **TS-8**(LOW)`diagnosis.md:28-29` —— 儀器清單漏 `setOptions` / `focusManager` 只聽 visibilitychange;blast radius 漏兩支 hook。search-proof:`grep setOptions diagnosis.md` 零命中。
- **TS-9**(LOW)`verification.md` 真實環境節 —— 第 1 條判準會失敗;mutation 表假信心。anchor `<none>`(主 agent 以 `## 真實環境` 標題行定位 :24)。
- reviewer 刻意不 flag(已核為留尾 / 慣例 / 無問題):後端 `build_period` 夜盤段快照(留尾正確)、overlay 兩支 render 時翻鍵(已入留尾但清單不全 → TS-3)、worktree App 級 vitest flake(差分證據合理)、匯出常數無 import(同檔 `BARS_FETCH_TIMEOUT_MS` 既有慣例)、`msUntilNextLocalDate` DST / 月末進位(`Date` 建構子處理溢位、台灣無夏令)、分 K 路徑逐字等價 / FuturesChart 純註解 / 無 scope creep。
- Accounting:`useFuturesBars.ts` FINDINGS / `trading-calendar.ts` REVIEWED_NO_ISSUES / `FuturesChart.tsx` FINDINGS / `useFuturesBars.test.ts` FINDINGS / `trading-calendar.test.ts` REVIEWED_NO_ISSUES / `next-time.md` FINDINGS / `diagnosis.md` FINDINGS / `verification.md` FINDINGS / `code-review-round-1.json` INTENTIONALLY_SKIPPED(純流程紀錄;唯一異議 P-F3 slack 值在 TS-1 內反駁)。

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 `codex` CLI,中性與對抗兩軸未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查(Codex / Gemini 皆未啟動)。

### Codex 對 Opus 的複查結果（對稱化 4.2）

Codex 複查 Opus 失敗(N-A:本機無 codex)—— 本輪 Step 4.2 輸入 findings 無 cross-axis 證據,10 條全部視同 INCONCLUSIVE。代之以 Step 4.3b 主 agent 逐條實查(單軸 lone finding 判斷式複查,非機械降級):

| Opus # | Opus reviewer | Opus title | Verdict | 原始 → 校正 severity | 主 agent evidence(4.3b) | 備註 |
| --- | --- | --- | --- | --- | --- | --- |
| F-01 | typescript-reviewer | slack 窗內重繪推遲午夜那一發 | 4.2 INCONCLUSIVE → 4.3b CONFIRMED | HIGH→HIGH | 直讀 `useBaseQuery.js:69-70`(每 render `setOptions`)、`queryObserver.js:112-118`(`nextRefetchInterval !== #currentRefetchInterval` 即 `#updateRefetchInterval`)、`:208-218`(`#clearRefetchInterval` 後重 `setInterval`)、`focusManager.js:9-18`(只 `visibilitychange`);主 tree vitest 模擬 A:09:00 掛載、00:00:10 起每 100 ms `rerender` 40 s → 09:00 `tf=D` 仍 1 發 | 他軸為何漏:無他軸(Codex / Gemini 未啟動);分支內 two-axis review 的 Spec 軸讀了 TQ 原始碼但只追 `#computeRefetchInterval` 何時重算、沒追 `useBaseQuery` 每 render `setOptions` —— 盲區與 F-08 同源。修法建議另做模擬 B / C / D:R2(界嚴格在 from 之後)重繪與切回兩路徑皆 00:01;reviewer 的 `dataUpdatedAt` 版切回路徑 11:02 才打 |
| F-02 | typescript-reviewer | 計時器 churn | 4.2 INCONCLUSIVE → 4.3b CONFIRMED | MEDIUM→MEDIUM | 機制同上;reviewer 自報模擬 6003 vs 5 次未重跑(以其第一手輸出為證);R2 修法保留 `Date.now()` 起算,churn 為刻意保留的代價 | lone finding、機制已由 F-01 證據涵蓋 → 維持 severity;處置交 user(ask-user) |
| F-03 | typescript-reviewer | 留尾清單漏兩支同形 hook | 4.2 INCONCLUSIVE → 4.3b CONFIRMED | MEDIUM→MEDIUM | `grep -n "queryKey\|staleTime\|refetchInterval" useMarketBars.ts useStockBars.ts`:`:69 staleTime: isMinute ? 0 : Infinity` / `:91 ["stock-bars", code, "D"]` + `:95 staleTime: isDaily ? Infinity : 0`;overlay 兩支 `:25` / `:15` 帶 `isoLocalDate(new Date())` | 文件型;code 同病另開 |
| F-04 | typescript-reviewer | 註解誤述 isStaleByTime | 4.2 INCONCLUSIVE → 4.3b CONFIRMED | LOW→LOW | `query.js:127-137` 直讀:第一條 `this.state.data === void 0` | 註解修正 |
| F-05 | typescript-reviewer | error 重試「同口徑」誤述 | 4.2 INCONCLUSIVE → 4.3b CONFIRMED | LOW→LOW | `queryObserver.js:214-218` interval 回呼 → `#executeFetch`;hook `retry: 1`;round-1 JSON `increment_screen.notes` 已知情 | 註解修正;是否加閘為取捨 |
| F-06 | typescript-reviewer | FuturesChart 註解 + 同鍵雙 observer | 4.2 INCONCLUSIVE → 4.3b CONFIRMED | LOW→LOW | `FuturesPage.tsx:144` 唯一掛載;`grep "memo("` 只命中內部 ChartStatic 註解;`useFuturesStream.ts:72/99` setState | 隨 F-01 收 |
| F-07 | typescript-reviewer | 測試 seam 量不到 render | 4.2 INCONCLUSIVE → 4.3b CONFIRMED | MEDIUM→MEDIUM | 主 agent 以同 seam 加 `rerender` 實跑(模擬 A)→ 現碼紅得出來,證明缺口為真且補法可行 | 與 F-01 同輪 |
| F-08 | typescript-reviewer | diagnosis 儀器 / 盤點缺口 | 4.2 INCONCLUSIVE → 4.3b CONFIRMED | LOW→LOW | `grep setOptions diagnosis.md` 零命中;Phase 6 段只列 overlay 兩支 | 文件 |
| F-09 | typescript-reviewer | verification 判準會失敗 / mutation 假信心 | 4.2 INCONCLUSIVE → 4.3b CONFIRMED | LOW→LOW | 推論全建立在 F-01 / F-07 第一手證據;verification.md「真實環境」第 1 條原文核對 | 文件 |

## Action Items

Severity calibration:6c Refactor Intent Gate 無適用 finding(本 PR 未移除 / 削弱既有防護)。6d-1 hedge:F-05「TC4 整個週末沒開」為情境描述、非假設繞過,LOW 不受影響。6d-2 lone finding 全部走 4.3b 判斷式複查(見上表,零機械降級)。6d-3 Must Fix 雙半條件:F-01 具體重現路徑 =「交易日晚上開期貨 tab、分頁保持可見、掛過 00:00 → 08:46 日盤開後 CDP / MA 疊線基準日(core readout `date`)仍是前一日、DevTools Network 00:01 沒有 `tf=D` 請求」;release-blocking = runtime 行為(疊線畫錯基準)—— 且這正是本 PR 唯一要修的行為,兩半皆過。其餘 8 條為文件 / 註解 / 測試覆蓋 / 效能觀察,不阻擋發布 → 依 MEDIUM / LOW 落 Nice to Have。Provenance cap N-A。

校準套用:無作者校準檔(xu-min-yu.md / loger-w.md 不存在)、本輪無套用。

### Must Fix（合併前必修）

- **F-01** `useFuturesBars.ts:151` —— 界改成「下一個 00:00+slack 嚴格在 from 之後」:`msUntilNextLocalDate(new Date(from - DAY_ROLLOVER_SLACK_MS))`;配 F-07 紅測試。PR 已 merge,此條為收修分支的第一優先;08-31 開盤前若 preview 已掛過午夜,主情境仍會停在昨天。

### Should Fix（強烈建議）

- 無(唯一 HIGH 已列 Must Fix;無 PARTIAL / INCONCLUSIVE 的 HIGH)。

### Nice to Have（可選優化）

- **F-02** churn 取捨(ask-user):接受每秒 ~10 組計時器增刪並補註解,或秒級量化。
- **F-03** next-time 08-30 節補 `useMarketBars.ts:69` / `useStockBars.ts:95` 同形未修;修正 overlay 兩支描述。
- **F-04** 註解改成 `state.data === undefined` 判準 + `dataUpdatedAt > 0` 等價說明。
- **F-05** error 重試註解改口「數值同、不吃時段閘、失效方向選多打」。
- **F-06** `FuturesChart.tsx:167` 註解隨 F-01 修正。
- **F-07** 補「slack 窗內 rerender」紅測試;F-01 落地後重跑 M1 / M2 / M3。
- **F-08** diagnosis.md 補 `setOptions` per-render 路徑、`focusManager` 只聽 `visibilitychange`、Phase 6 補兩支 hook。
- **F-09** verification.md mutation 表旁註明 render 盲區;保留真實環境第 1 條為紅燈判準。

### 參考用（任一軸驗證為 REFUTED 或 OUT_OF_SCOPE）

- 無。

## 審查工具比較 (qualitative)

- CC 視角(typescript-reviewer,context-aware):唯一啟動的模型軸。10 條中最重的 F-01 是「library 內部機制 × 元件重繪頻率」的跨層交互 —— 分支內 round-1 review(同為 opus two-axis)讀了 TQ 原始碼卻沒追到 `useBaseQuery` 每 render `setOptions` 這一段,本輪 reviewer 以獨立模擬腳本補上第一手證據。
- 主 agent 4.3b:對 F-01 修法建議做了 reviewer 沒做的第二層驗證(模擬 C:`dataUpdatedAt` 版切回漂移 11 h),避免收修時把一個洞換成另一個洞。
- Codex 中性 / 對抗、Gemini:N-A,重疊率無法計算。Opus 複查 Codex(4.1):N-A。Codex 複查 Opus(4.2):N-A → 4.3b 分佈 CONFIRMED 9 / REFUTED 0 / PARTIAL 0 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0。
- 對抗式第三軸增益:N-A。

## 沒做的部分（結案對帳）

- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(直讀 TQ 原始碼 + 主 tree vitest 拋棄式模擬四例 `__r2sim.test.ts`,跑完即刪、`git status` 無殘留)。
- sem blast radius:跑了,空輸出跳過(無 sem)。React-doctor:PASS,未引入新問題。C4:SKIPPED (C4_NO_NORMATIVE_CLAUSE_CANDIDATE) —— 零候選條款,未呼叫 reducer(與 pr-145 的 `C4_AUTHORITY_PATH_NOT_ALLOWED` 不同:那次有 spec 檔但路徑不在 allowlist,本次根本沒有可綁定的規範句)。
- 真實環境:PR 自述的 08-31 跨午夜判準本輪未驗(需真時間);F-01 的證據是 TQ 原始碼直讀 + 主 tree vitest 假時鐘模擬,不是 prod 觀察。**依 F-01,08-31 那條判準預期會失敗**(前提 = preview 掛在期貨 tab 且分頁可見)。
- 未驗證前提:F-01「那 60 秒約 600 次 render」是由 0.1 s coalesce 推得的上界,夜盤實際 tick 頻率未量(但即使 1 次重繪就足以觸發);F-02 的 6003 vs 5 次是 reviewer 自報模擬、主 agent 未重跑(機制已第一手);F-05「週末每分鐘兩發 503」由 `retry: 1` 與無閘推得,未實跑。
- 主 agent 未重跑 reviewer 的 `midnight.mjs` 模擬(以主 tree vitest 另寫四例代之,結論一致)。
- Self-Verify:已執行,`VERDICT: COMPLIANT`(R1–R10 全 PASS);零修正,故無「未經第二次獨立稽查」事項。
