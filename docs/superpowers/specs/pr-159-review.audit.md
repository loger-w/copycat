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

## Spec 依據

- 此 PR 未附 spec/plan 文件(Step 2.6 偵測:14 個變更檔無任一命中 spec 路徑 / 檔名 / frontmatter 規則;`.claude/bug/*` 的 diagnosis / verification 是流程 artifact 非 spec)。按一般 PR 流程 review。意圖來源 = PR body + 6 筆 commit message。
- Spec 作者同人檢查:N-A(無 spec)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_NORMATIVE_CLAUSE`(無任何含 NORMATIVE_KEYWORD / INVARIANT / FORMULA / STATE_TRANSITION / ERROR_CONTRACT 的實作綁定條款來源)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tools=0。0 clauses / 0 findings / 0 observations / 0 invalidated。

## 變更概要

provenance: N-A(base = master)

| 檔案 | 類型 | 說明 |
|---|---|---|
| `.claude/bug/daily-bars-siblings-rollover/code-review-round-1.json` | 新增 | two-axis review 12 條 + disposition artifact |
| `.claude/bug/daily-bars-siblings-rollover/diagnosis.md` | 新增 | diagnosing-bugs 六 phase 紀錄 |
| `.claude/bug/daily-bars-siblings-rollover/verification.md` | 新增 | gate / 突變體 / 真環境判準 artifact |
| `.claude/skills/ops-discipline/SKILL.md` | 修改 | 加「突變體迴圈 git checkout 還原洗掉未 commit 收修」教訓 |
| `docs/next-time.md` | 修改 | 08-30 節第 3 條結案 + 新留尾 S-F5 |
| `frontend/src/components/futures/FuturesChart.tsx` | 修改 | 單行註解路徑回填(helper 搬家) |
| `frontend/src/hooks/useFuturesBars.test.ts` | 修改 | 兩處註解路徑回填,測試本體零改 |
| `frontend/src/hooks/useFuturesBars.ts` | 修改 | helper 三顆搬出至 lib(−53 行) |
| `frontend/src/hooks/useMarketBars.test.ts` | 修改 | 新增跨日曆日 describe(8 it / 9 case) |
| `frontend/src/hooks/useMarketBars.ts` | 修改 | 日/週/月 K staleTime / refetchInterval 改吃 msUntilDayRollover;日 K 分支整段不吃 active |
| `frontend/src/hooks/useStockBars.test.tsx` | 修改 | 新增跨日 describe(6 it)+ wrapper 簽章對齊姊妹檔 |
| `frontend/src/hooks/useStockBars.ts` | 修改 | 日 K barsPollInterval 先判、後接失敗重試 / 日界 |
| `frontend/src/lib/day-bars-rollover.ts` | 新增 | 日 K 新鮮度 helper 三顆的新住處 |
| `frontend/src/lib/trading-calendar.ts` | 修改 | 「唯一讀者」doc 指標更新 |

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

## Opus 原始 findings(first-pass, context-aware)

### chunk 1(typescript-reviewer;12 檔)

前置:junction 接主 repo node_modules 跑 `tsc -b` 0 / `eslint src` 0 / 三檔 hook 測試 63 passed 後拆除;TQ 主張逐條核過 `@tanstack/query-core@5.101.2` build 原始碼(`query.js::isStaleByTime` L127–138、`queryObserver.js` L188–219 / L424),PR doc 三鐵律推導與程式碼一致,`msUntilDayRollover` 邊界算術(00:00:59.999 → 00:01:00.999、00:01:00.000 → +24 h)逐一驗過無誤。

- **F-01 MEDIUM** `useMarketBars.ts:76-88`:午夜那發拿到「200 + 空 bars」會把好資料換成空快照且到次日午夜前不自救。後端證據:`index_engine.py:571-585`(TC4 不可用回 `([], "unavailable")` 不 raise)、`futures_engine.py:372-390`(`ConnectionError` → `return [], "disconnected"`)、`app.py:1749-1754`(D/W/M 走 `build_period`,`_market_payload` 連 `status` 鍵都不給)。TQ 判 success → data 換成空 → interval 排明天、staleTime 整天不過期、`refetchOnWindowFocus` / `refetchOnReconnect` 被 `isStaleByTime`(queryObserver.js L451/L461)擋掉、tab hidden 保留不觸發 refetchOnMount。畫面 = `MarketChart.tsx:142-163` 空 CandleChart + 「取不到資料 · 無資料」整天不變。修前失效樣態是「昨天的 K 線」,此路徑上修後反而更差。同 PR `useStockBars` 有保險(三態 status → `barsPollInterval` 20 s),兩支兄弟同情境處置相反。`bars.py:305-308` `daily_put` 有 don't-cache-empty → 後端不鎖、只有前端鎖住。修法:(a) 日 K 分支加空態閘(data 有值且 bars 空 → 20–60 s 短重試)或 (b) 列知情項 + verification.md 判準補一條;`useFuturesBars` 同洞。search-proof:`grep -rn "barsPollInterval" src --include=*.ts --include=*.tsx | grep -v test`(Grep;於 reviewed SHA 603e1b33 的 worktree 執行)——predicate = 「useMarketBars 側是否存在任何空態重試守門」,命中集僅 `useStockBars.ts:69,110`(定義與唯一取用),useMarketBars / MarketChart 零命中 → 「無等價守門」在 reviewed SHA 成立;另 `grep -rn "unavailable|bars.length === 0"` 於四檔僅命中註解與顯示字串。PR body / diagnosis / verification 全文無「空 bars / unavailable」的 scope 排除聲明 → 非刻意 out-of-scope。anchor = `return q.state.status === "error" ? DAY_ERROR_RETRY_MS : msUntilDayRollover(Date.now());`
- **F-02 MEDIUM** `lib/day-bars-rollover.ts:3-13`+ 三 hook:lib 只收三顆常數/函式,真正會漂的兩行政策運算式(staleTime lambda / error-retry ternary)仍三份;搬家 commit 自稱純搬、concept 數未降;本 PR 的病因(policy 三份、改一支其他綠)原封保留。修法:抽 `dayBarsStaleTime(q)` / `dayBarsRefetchInterval(q)`,或檔頭明寫「政策刻意留 caller、三處同動」。anchor = 同上 ternary(useMarketBars:85 / useStockBars:112 / useFuturesBars:119)
- **F-03 LOW** artifacts / docs 五處指向修前狀態:diagnosis:37(指 useFuturesBars doc)、:58(「只有這兩個讀者」)、:51(「market 7 條 / stock 6 條」)、verification:16(「只有 frontend/src/hooks 五檔」)、next-time:21(「13 條 hook 測試」,實際 14 it / 15 case)。
- **F-04 LOW** `useStockBars.test.tsx:177-179`:巢狀 `afterEach(vi.useRealTimers)` 在檔頂加同款後成 no-op 重複。
- **F-05 LOW** `useMarketBars.ts:55-58`:`@param active` doc 缺「日/週/月 K 整段不吃此參數」例外(知情變更只在行內註解)。
- 附帶正面:修前 boot 期 503 `NOT_READY` 會讓日 K 永久停在「K 線載入失敗」直到重整,新 error 分支讓它 60 s 自癒。
- 逐檔 accounting(12/12):findings 見上;`REVIEWED_NO_ISSUES`: code-review-round-1.json(S-F6 駁回經 python len() 複核成立)、ops-discipline SKILL.md、FuturesChart.tsx、useFuturesBars.test.ts。
- chunk 結論:Warning(可合併但建議先處理 F-01);零 CRITICAL / HIGH。

### chunk 2(typescript-reviewer;lib 2 檔)

前置:`tsc -b` 0 / `eslint` 0 / 63 passed;TQ 三主張核過 query-core 5.101.2 同結論。搬家核對:`msUntilDayRollover` 本體與 base 逐字相同;無 import 迴圈(`trading-calendar.ts` 零 import、兩支兄弟不再 runtime 依賴期貨 hook);舊位置指標 `grep "useFuturesBars.ts::msUntilDayRollover" src` 0 筆;`trading-calendar.ts:97`「唯一讀者」主張 grep 核過正確;lib 無自有測試檔 = seam 由 user 拍板在 hook、突變體 10/10 已釘,知情不動。

- **F-06(原 #1)LOW** `day-bars-rollover.ts:19`:`DAY_ROLLOVER_SLACK_MS` 零讀者 export(兩版 grep 皆只有本檔自讀;測試釘 slack 用字面值且 frontend-testing 明令不 import 常數算期望值 → 不會長出讀者)。修法:降私有或 doc 註明。search-proof:`grep -rn "DAY_ROLLOVER_SLACK_MS" src/`(Grep;reviewed SHA worktree)——predicate = 「此 export 是否有本檔以外的讀者」,命中僅 `src/lib/day-bars-rollover.ts:18,19,22,59`;`git grep -n "DAY_ROLLOVER_SLACK_MS" 0b744bb8 -- frontend/src` 僅 base useFuturesBars 三行 → 兩版皆零外部讀者,在 reviewed SHA 成立(main session 複核同結果)。
- **F-07(原 #2)LOW** `day-bars-rollover.ts:63-73`:`DAY_ERROR_RETRY_MS` doc 仍期指單 hook / 單端點口徑——(a)「分 K 那條包著 inFuturesAllDayHours()」只對期指、且 `= POLL_MS` 改字面後「數值相同」指涉三份各自私有的 POLL_MS 無機制維持;(b) 錯誤面列舉漏 `/api/stock/bars` 的 400 `BAD_CODE`(`app.py:1314-1315`,永久錯誤不自癒)與全域 `@app.exception_handler` 502 `TC4_DOWN`(`app.py:1148-1151`);降級走 200 的主張本身核過為真(`futures_engine.py:377-391` / `stock_engine.py:778-785`);`fetchBars` 名字錯配(僅 stock 側)。BAD_CODE 前端可達性低(`_CODE_RE` 同一把尺)→ 定 LOW。search-proof:`grep -n "api/market/bars" copycat/server/app.py` 等(Grep;reviewed SHA worktree)→ 1382 / 1640 兩支 route——predicate = 「日 K 讀者實際可吃到哪些非 2xx」,逐讀 `app.py:1382-1414`(400 `BAD_CODE`、503)與 `app.py:1640-1748`(參數類 400、503)、`grep -n "exception_handler"` → `app.py:1148` 全域 502;doc 現句只列 `NOT_READY` 503 → 「口徑窄於實況」在 reviewed SHA 成立。
- **F-08(原 #3)LOW** `day-bars-rollover.ts:11-13/24-25/71-72`:「讀者三支」清單三份且措辭互漂(useStockBars 一處「barsPollInterval 先判」一處「本來就無閘」;useMarketBars 一處「整段不吃」一處「不吃 active,見該檔」),違反本檔自立的「只寫這一處」原則。
- 逐檔 accounting(2/2):`day-bars-rollover.ts` 3 條 LOW;`REVIEWED_NO_ISSUES`: trading-calendar.ts。
- chunk 結論:Warning(可合併);零 CRITICAL / HIGH / MEDIUM。

## Codex 原始 findings(first-pass, diff-only)

N-A —— codex CLI 本機未裝,中性軸與對抗軸皆未跑,零 findings。

## Opus 對 Codex 的複查結果(4.1)

N-A —— 無任何非 CC 軸 finding 可驗。

## Codex 對 Opus 的複查結果(對稱化 4.2)

**Codex 複查 Opus 不可用 —— codex CLI 未裝,本輪 Step 4.2 輸入 findings(F-01~F-08 全部)無 cross-axis 證據、視同 INCONCLUSIVE 處理**(不阻斷 review;下表為 main session 的替代性抽驗,非 cross-axis 證據):

| Opus # | verdict 替代狀態 | main session 抽驗 |
|---|---|---|
| F-01 | INCONCLUSIVE(無 Codex) | 後端 `app.py:1749` 註解自證 D/W/M「未三態化」;機制鏈(success 換空資料 → staleTime 擋 focus refetch)與 query-core 行為一致 |
| F-02 | INCONCLUSIVE(無 Codex) | 實測三處:useMarketBars:85 / useFuturesBars:119 逐字同、useStockBars:112 同形(`query` vs `q`)——reviewer 的「三處逐字相同」措辭修正,主張不變 |
| F-03 | INCONCLUSIVE(無 Codex) | sed 逐行抽驗 diagnosis:37/51/58、verification:16、next-time:21 全命中 |
| F-04~F-08 | INCONCLUSIVE(無 Codex) | anchor grep 全命中(見定位 tally);F-06 零讀者 grep 由 main session 複核同結果 |

## Action Items

**Severity calibration**:全 8 條非安全類,沿 reviewer 分類;無 corrected_severity(4.2 未跑)→ effective_severity = 原值。6c Refactor Intent Gate:本 PR 無「移除/削弱既有防護」類 finding(helper 搬家經 AST 對照為純搬)→ 免。6d-1:F-01 的觸發條件(TC4 於 00:01 不可用)為可重現的具體情境、非假設性措辭,不觸發 hedge cap;其餘各條無假設性措辭。6d-3:無 finding 進 Must 候選(零 consensus / 零 CRITICAL / 零 cross-axis CONFIRMED),不適用。4.3a consensus baseline check:N-A(單軸零 consensus)。4.3b lone finding:全 8 條為 lone,但本輪僅一軸實際跑過 diff——「他軸沉默」不構成證據(他軸未走過同一份 diff),依 4.3b 規則不降級,effective_severity 維持原值;此判定記於本行,逐條備註欄不再重複。

**校準套用**:無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

### Must Fix(合併前必修)

(無 —— 零 consensus、零 CRITICAL、零 cross-axis CONFIRMED。)

### Should Fix(強烈建議)

(無 —— 零 HIGH。)

### Nice to Have(可選優化)

- **#1(MED)** 日/週/月 K 午夜空 bars 失效路徑:補空態閘或列知情 + 補真環境判準;`useFuturesBars` 同洞一起處理。`ask-user`。
- **#2(MED)** 政策運算式收進 lib(`dayBarsStaleTime` / `dayBarsRefetchInterval`)或檔頭明寫三處同動。`ask-user`。
- **#3~#8(LOW)** 文件回填 ×3(#3 / #7 / #8)、測試重複 afterEach(#4)、@param doc(#5)、零讀者 export(#6)。`auto-fix` 建議(不自動執行)。

### 參考用(任一軸驗證為 REFUTED 或 OUT_OF_SCOPE)

(無 —— 本輪無 REFUTED / OUT_OF_SCOPE verdict。)

## 審查工具比較(qualitative)

單軸場次(僅 CC typescript-reviewer 兩 chunk;Codex / Gemini 全 N-A)→ 表縮至 Opus 一欄 + 複查欄。全部 8 條落 Nice to Have(零 Must / Should 候選源:無 consensus、無 CRITICAL、無 cross-axis CONFIRMED;2 條 MEDIUM + 6 條 LOW 依分級規則 MEDIUM / LOW → Nice to Have)。

- 單軸場次:CC typescript-reviewer ×2 chunk。兩個 chunk 都主動讀了 `@tanstack/query-core` 5.101.2 build 原始碼與後端 route 實作來驗 doc 主張——F-01(200 空 bars 不自救)正是「前端 diff + 後端語意」跨層對照才抓得到的形狀,diff-only 軸(Codex)本輪缺席,無從比較重疊率。
- 重疊率 / 4.1 / 4.2 分佈:N-A(無他軸)。
- 對抗式第三軸增益:N-A(未跑)。
- chunk 間互補:chunk 2 專注 lib 檔面(export 面 / doc 口徑 / 讀者清單),chunk 1 抓到跨層行為缺口與 artifacts 漂移——chunk 分工未產生重複 finding(F-07 與 F-01 引用同一後端事實但指向不同缺陷:doc 口徑 vs 行為缺口)。

## 沒做的部分(結案對帳)

| 項目 | 狀態 | 理由 / 證據 |
|---|---|---|
| Codex 中性軸 | N-A | codex CLI 本機未裝(`command -v codex` 無);Step 2.98 preset 提問因此略過 |
| Codex 對抗軸 | N-A | 同上;非 user override skip,屬工具缺席、已在此揭露 |
| Gemini Flash 永久軸 | N-A | agy CLI 未裝;Step 2.96 提問略過 |
| Gemini Pro opt-in | N-A | 同上 |
| Step 4.2 Codex 驗 CC first-pass | FAIL(不可用) | 與 header「審查軸狀態」同判(4.2 FAIL);全部 8 條 findings 視同 INCONCLUSIVE、無 cross-axis 證據;main session 抽驗為替代參考非證據 |
| Step 4.1 | N-A | 零非 CC finding |
| 4.3a consensus baseline | N-A | 單軸零 consensus |
| sem blast radius | 空輸出跳過 | sem CLI 未裝,script exit 0 零輸出 |
| C4 spec-compliance | N-A(SKIPPED) | 無 spec、無 normative clause(reason_code=C4_NO_NORMATIVE_CLAUSE) |
| Gemini quota snapshot | N-A | 軸未跑 |
| 未驗證前提 | 揭露 | F-01 的「使用者會在午夜讓後端開著、TC4 關著」發生頻率未實測(機制已驗、頻率未驗);F-02 建議的抽函式對 TQ 型別介面的可行性未實作驗證 |
| 其餘 | 無 | mandatory CC 軸、coverage、re-anchor、react-doctor、Self-Verify 均已執行 |

零 finding 條款:N-A(本輪 8 條)。

**Self-Verify 修正紀錄**(round 1 verdict = VIOLATIONS: R2, R6, R9;修正後**未經第二次獨立稽查**):
- R2:header「審查軸狀態」把 cross-axis 寫成單一 N-A、與對帳表「4.2 FAIL(不可用)」矛盾 → 拆成 4.1 N-A / 4.2 FAIL 並互相註記同判;primary reviewer 軸補 requested=opus(dispatch receipt)/ observed=UNAVAILABLE。
- R6:F-01 / F-06 / F-07 的 search-proof 補 predicate 語意、工具名(Grep)、reviewed-SHA 執行環境與「仍成立理由」。
- R9:React-doctor header 補 PASS 三態;blast radius 由「空輸出跳過」改為 N-A(空輸出跳過)三態。
三處均為報告措辭 / 揭露補強,零 finding 內容、severity、action 變動。
