# PR #159 Code Review 比較報告 · SHA 603e1b33
**Report projection schema**: 1

**PR**: [loger-w/copycat#159](https://github.com/loger-w/copycat/pull/159)
**標題**: fix(frontend): useMarketBars 日/週/月 K 與 useStockBars 日 K 跨日曆日重抓 —— 與期指日 K 同一把尺(pr-151-review F-03)
**作者**: loger-w
**分支**: `fix/daily-bars-siblings-rollover` → `master`(PR 已 MERGED 2026-08-30T17:02:57Z,rebase merge;本 review 為 merge 後回溯審)
**變更**: 14 檔案, +750 / -86
**審查日期**: 2026-08-31
**Review input basis**: source repo id `R_kgDOTsITBg` + source SHA `603e1b33f2a5ac7fc8cfcfb62cd006e20395c2f8`;destination repo id `R_kgDOTsITBg` + destination SHA `0b744bb85b824006a8b846272782196065447df0`;`input_binding: verified`(worktree HEAD = source SHA、destination SHA 可解析,Step 2.5 sanity check PASS)
**Review continuity**: `source_continuity=CURRENT`(refetch head OID 不變;merged PR 不可變)`;base_changed=true`(origin/master 已前進 19 commits 至 a58e7ac2,含本 PR 自身 rebase merge 的 7 筆 + PR #160 + docs chore)`;review_context_changed=true`(僅通知,不重審、不改 findings)
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(CLI 未裝)** + Codex 對抗式 **N-A(CLI 未裝)** + Cross-axis verification(4.1 無輸入 N-A;4.2 **不可用**——Codex CLI 未裝,全部 CC findings 無 cross-axis 證據、視同 INCONCLUSIVE)+ Gemini 軸 **N-A**(agy CLI 未裝;Flash 永久軸與 Pro opt-in 皆無法跑,Step 2.96 提問因此略過)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewer=typescript-reviewer ×2 chunks(dispatch requested=opus;observed=UNAVAILABLE——Agent tool 無 runtime model receipt 機制);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(未派,gate SKIPPED);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=14 → covered 9 / no-issues 5 / skipped 0 / **missed 0**(chunked: 是——DIFF_LINES 836 > 800;chunk 1 = 排序前 12 檔 761 行、chunk 2 = lib 2 檔 75 行)
**定位 (ENH-B)**: anchored exact 6 / ambiguous 1 / **FAILED 1**
**React-doctor (2.97)**: PASS — 未引入新問題(worktree merge-base 錨定 `--scope changed`,newCount 0 / baseTotal 0)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_CLAUSE)
**Quota (Gemini 軸 only、選填)**: N-A(Gemini 軸未跑,未取 dashboard snapshot)
**審查軸狀態**: primary typescript-reviewer chunk 1/2 **PASS**(requested=opus(dispatch receipt)/ observed=UNAVAILABLE;12/12 accounting、5 findings)/ chunk 2/2 **PASS**(requested=opus / observed=UNAVAILABLE;2/2 accounting、3 findings)/ domain reviewers **N-A**(security 未觸發:無 auth / env secrets / request-body / session / RBAC 面)/ Codex 中性 **N-A**(codex CLI 未裝)/ Codex 對抗 **N-A**(codex CLI 未裝)/ Gemini Flash **N-A**(agy CLI 未裝)/ Gemini Pro **N-A**(agy CLI 未裝、未詢問 opt-in)/ cross-axis verification 4.1 **N-A**(零非 CC finding 可驗)、4.2 **FAIL**(codex CLI 未裝、不可用 → 全部 findings 視同 INCONCLUSIVE;與「沒做的部分」同判)/ blast radius **N-A**(空輸出跳過:sem CLI 未裝,`sem-pr-blast-radius.sh` exit 0 零輸出)/ provenance **N-A**(base = master)

**worktree**: `C:/side-project/copycat/.worktrees/review-pr-159`
**worktree HEAD**: `603e1b33f2a5ac7fc8cfcfb62cd006e20395c2f8`

**Report generation**: sha256:a9037c930a24effe8583e416c7d9b9821600a2b8437489798f24ac625290b1c4

---
## [完整證據副檔](pr-159-review.audit.md)
### finding_uid 索引
[04d7237cbb5729a362d9](pr-159-review.audit.md#發現總覽) · [a27559d48d42add4dab9](pr-159-review.audit.md#發現總覽) · [1766b16b1dd9b83af2d3](pr-159-review.audit.md#發現總覽) · [fbf2e553e4b025274480](pr-159-review.audit.md#發現總覽) · [8116a01f4aa1a492e869](pr-159-review.audit.md#發現總覽) · [d9986bdce14f71b15f0a](pr-159-review.audit.md#發現總覽) · [2a1eaf44526aeaddcf1c](pr-159-review.audit.md#發現總覽) · [9514f0e1849f15a19dfc](pr-159-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | 複查(cross-axis) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| 1 | 日/週/月 K 午夜那發拿到 200+空 bars 會把好資料換成空快照、整天不自救 | MED | 無他軸(INCONCLUSIVE);main session 抽驗後端 `app.py:1749` 註解自證「未三態化」,機制成立 | Nice to Have | `ask-user` | 修法有 (a) 空態閘 / (b) 知情+補判準 兩路,且 useFuturesBars 同洞,是行為決策 |
| 2 | 新 lib 只收常數,兩行政策運算式仍三份(本 PR 的病因形狀原封保留) | MED | 無他軸(INCONCLUSIVE);main session 實測:useMarketBars:85 / useFuturesBars:119 逐字同、useStockBars:112 同形(`query` vs `q`)——「三處逐字」修正為「同形三處、逐字兩處」 | Nice to Have | `ask-user` | 抽 dayBarsStaleTime / dayBarsRefetchInterval 是設計取捨,user 剛拍板過 lib 範圍 |
| 3 | 三份 artifacts / docs 有指向搬家前狀態的陳述(diagnosis:37/51/58、verification:16、next-time:21) | LOW | 無他軸;main session sed 逐行抽驗 5 處全命中 | Nice to Have | `auto-fix` | 純文件回填、五句話 |
| 4 | useStockBars.test 巢狀 afterEach(vi.useRealTimers) 在檔頂加了同款後成重複 | LOW | 無他軸;grep 實證 26 / 178 兩處 | Nice to Have | `auto-fix` | 刪三行、零行為 |
| 5 | useMarketBars @param active doc 沒寫「日/週/月 K 整段不吃這個參數」 | LOW | 無他軸;知情變更只在行內註解,簽章 doc 缺 | Nice to Have | `auto-fix` | 補一句 doc |
| 6 | DAY_ROLLOVER_SLACK_MS 是零讀者的 export | LOW | 無他軸;grep 兩版皆零外部讀者(main session 複核同結果) | Nice to Have | `auto-fix` | 降私有 const、機械 |
| 7 | DAY_ERROR_RETRY_MS doc 仍是期指單 hook / 單端點口徑(漏 /api/stock/bars 的 400 BAD_CODE、全域 502;fetchBars 函式名錯配) | LOW | 無他軸;reviewer 附後端 file:line 實讀 | Nice to Have | `auto-fix` | doc 改兩句 |
| 8 | 「讀者三支」清單在 73 行內寫三次且措辭已互漂 | LOW | 無他軸;三處位置實讀確認 | Nice to Have | `auto-fix` | 收成檔頭一份 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 04d7237cbb5729a362d9 action=ask-user
F-02 finding_uid: a27559d48d42add4dab9 action=ask-user
F-03 finding_uid: 1766b16b1dd9b83af2d3 action=auto-fix
F-04 finding_uid: fbf2e553e4b025274480 action=auto-fix
F-05 finding_uid: 8116a01f4aa1a492e869 action=auto-fix
F-06 finding_uid: d9986bdce14f71b15f0a action=auto-fix
F-07 finding_uid: 2a1eaf44526aeaddcf1c action=auto-fix
F-08 finding_uid: 9514f0e1849f15a19dfc action=auto-fix
### Inline Comments per Finding
#### #1 午夜那發若拿到 200+空 bars,台股綜合 tab 的日 K 會整天空白且不自救
**File**: `frontend/src/hooks/useMarketBars.ts`
**Line**: 85

**Comment**:
```
後端 D/W/M 路徑在 TC4 不可用時回 200 + 空 bars(app.py:1749 自己註明「未三態化」、
futures_engine/index_engine 都不 raise)。00:01 那發碰上「後端活著、TC4 沒開」→ TQ 判 success、
好資料被換成空快照 → interval 排到明天、staleTime 整天不過期、refetchOnWindowFocus 也被
isStaleByTime 擋掉 → 主圖空白一整天,只剩 meta 一行小字。修前的失效樣態是「昨天的 K 線」,
這條路上反而變差。同 PR 的 useStockBars 有現成保險(空+非 ok → barsPollInterval 20 s)可對照。

兩條路擇一:
(a) 日 K 分支加空態閘:data 已有值且 bars.length === 0 → 回 20–60 s 短重試;
(b) 不修就列知情項 + verification.md 真環境判準補一條「午夜那發回空」的覆蓋。
useFuturesBars(#151/#155)有同一個洞,一起處理較省事。
```
#### #2 兩行「政策運算式」仍逐字/同形三份——本 PR 的病因形狀原封留著
**File**: `frontend/src/lib/day-bars-rollover.ts`
**Line**: 需人工確認（anchor 未在綁定來源中比中或證據 binding 失效）

**Comment**:
```
(pin 位置需人工確認:實際複製點 = useMarketBars.ts:85 / useFuturesBars.ts:119(逐字同)/ useStockBars.ts:112(同形,query vs q)。)
新 lib 檔頭自述「三顆常數/函式的唯一住處」,但真正會漂的是這兩行運算式:
staleTime 的 (q) => msUntilDayRollover(q.state.dataUpdatedAt) 和
error ? DAY_ERROR_RETRY_MS : msUntilDayRollover(Date.now()) —— 三支 hook 各留一份。
這個 PR 之所以存在,就是「政策只寫在 useFuturesBars、兩支兄弟沒跟上」漂了兩週。
同一條 drift 通道還在:改一支、其他兩支的測試照綠。

收法:lib 出 dayBarsStaleTime(q) / dayBarsRefetchInterval(q),hook 只留接線
(useStockBars 保留 barsPollInterval 先判的順序)。不做的話,至少把檔頭那句
「唯一住處」改成「政策運算式刻意留在 caller、三處必須同動」。
```
#### #3 三份 artifacts / docs 留著搬家前的陳述
**File**: `.claude/bug/daily-bars-siblings-rollover/diagnosis.md`
**Line**: 37

**Comment**:
```
五處漏回填:diagnosis:37 仍指 useFuturesBars.ts::msUntilDayRollover(doc 已搬 lib)、
:58「只有這兩個讀者」(已是三個)、:51「market 7 條 / stock 6 條」(round-1 後是 8+6)、
verification:16「只有 frontend/src/hooks 五檔」(最終 diff 是 8 個前端檔+4 文件檔)、
next-time:21「13 條 hook 測試」(實際 14 it / 15 case)。各改一句就好。
```
#### #4 巢狀 afterEach(vi.useRealTimers) 變重複
**File**: `frontend/src/hooks/useStockBars.test.tsx`
**Line**: 177-179

**Comment**:
```
檔頂 afterEach 這次加了 vi.useRealTimers(),SC-4 describe 裡那份就是 no-op 了,
姊妹檔都只有檔頂一份。刪掉 177-179 就好。
```
#### #5 @param active 沒寫日/週/月 K 的例外
**File**: `frontend/src/hooks/useMarketBars.ts`
**Line**: 55

**Comment**:
```
「日/週/月 K 整段不吃 active」是這次的知情變更,但只寫在 refetchInterval 行內註解;
讀簽章的人(MarketChart)看不到。@param active 補一句:
「只作用於分 K:日/週/月 K 的午夜重抓與失敗重試不吃這道閘(理由見 refetchInterval 內註)」。
```
#### #6 DAY_ROLLOVER_SLACK_MS 是零讀者的 export
**File**: `frontend/src/lib/day-bars-rollover.ts`
**Line**: 19

**Comment**:
```
整個 src/ 只有本檔自己讀它(測試釘 slack 用牆鐘字面值、也不 import)。
降成非 export 的 const;真要留 export 就在 doc 寫明「目前無外部讀者」。
```
#### #7 DAY_ERROR_RETRY_MS doc 口徑窄於三讀者實況
**File**: `frontend/src/lib/day-bars-rollover.ts`
**Line**: 63-73

**Comment**:
```
兩句範圍不足:「分 K 那條包著 inFuturesAllDayHours()」只對期指(另兩支是 inTradingHours /
inFuturesTradingHours);「/api/market/bars 的 503 只有 NOT_READY」漏了 useStockBars 打的
/api/stock/bars 另有 400 BAD_CODE(永久錯誤、每分鐘兩發不會自己好)與全域 502 TC4_DOWN;
fetchBars 這名字只是 stock 那支(期指 fetchFuturesBars / 市場 fetchMarketBars)。
改成三讀者口徑:「各 hook 分 K 另有自己的時段閘;非 2xx 一律走這條——TC4 斷線/慢在兩支
bars route 都是 200 降級不進 error,非 2xx 實際來源是引擎未就緒 503、參數類 400、全域 502」。
```
#### #8 「讀者三支」清單寫了三次且已互漂
**File**: `frontend/src/lib/day-bars-rollover.ts`
**Line**: 11-13

**Comment**:
```
module header、msUntilDayRollover doc、DAY_ERROR_RETRY_MS doc 各列一次讀者清單,
附註已互漂(useStockBars 一處寫「barsPollInterval 先判」一處寫「本來就無閘」)。
本檔自己立的原則就是「只寫這一處」——清單留檔頭一份,其他兩處寫「讀者見檔頭」。
```
## React-doctor 機械掃描
(header 狀態 = 未引入新問題,本段依規則僅留 header 一行。)
