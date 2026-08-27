# PR #127 Code Review 比較報告 · SHA 2eb85544
**Report projection schema**: 1

**PR**: [loger-w/copycat#127](https://github.com/loger-w/copycat/pull/127)
**標題**: feat(frontend): 個股分時圖疊「台指期」當日走勢(與加權 / 櫃買並存)
**作者**: loger-w(commits 署名 Loger)
**分支**: `feat/txf-intraday-overlay` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 1a2becc5;回溯 review)
**變更**: 32 檔案, +721 / -75
**審查日期**: 2026-08-27
**Review input basis**: source repo R_kgDOTsITBg + 2eb855445d3810f5d955f98d8025eabe6c3993c7;destination repo R_kgDOTsITBg + dc819faadb45e5f12fe18479253590ec25259aad;`input_binding: verified`(`git fetch origin refs/pull/127/head` 後 FETCH_HEAD = source SHA,worktree detach 於該 SHA 並 rev-parse 相等;base SHA 本地存在)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED,分支已刪、以 refs/pull/127/head 定錨);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-127`(detached)
**worktree HEAD**: 2eb855445d3810f5d955f98d8025eabe6c3993c7
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex N-A → 以 4.3 同軸 `code-reviewer` 批次機制 / baseline 複查代之,**非獨立軸**)+ Gemini 軸 N-A(本機無 agy)+ React-doctor 機械軸(跑了)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=typescript-reviewer(不切塊,單一 dispatch;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / env secret / request body / session / RBAC 面);4.3 verification=code-reviewer(dispatch 顯式 model=opus;observed=UNAVAILABLE);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=32 → covered 8 / no-issues 21 / skipped 3 / **missed 0**(chunked: 否;FILE_COUNT=8 源檔 ≤ 15、DIFF_LINES=726 < 800;reviewer 逐檔 accounting 32/32,主 session 以集合運算對帳 union = F、無多餘路徑)
**定位 (ENH-B)**: anchored exact 9 / ambiguous 0 / **FAILED 0**(全部 anchor 於 worktree HEAD 以逐字比中,line 以比中結果為準,與 reviewer 自報行號一致)
**React-doctor (2.97)**: 未引入新問題(`react-doctor@0.9.12 --scope changed --base dc819faa` baseline 模式報 newCount=1 → `GroupGridView.tsx:70 only-export-components`,但該行不在本 PR 任何 hunk(hunk 起點 260 / 270 / 420)且 master 同行同 warning → 判存量;既有 4 條不計)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_INPUT_INVALID)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,32 檔全部 authored)
**審查軸狀態**: primary(typescript-reviewer)PASS(9 findings、32/32 accounting);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification:4.1 N-A / 4.2 FAIL(N-A)→ 4.3 同軸 code-reviewer 批次 PASS(6/6 回 verdict、ID 集合完全相符)+ 主 session 直核 3 條(TS-7/8/9);React-doctor PASS(跑了、零新引入)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus)回 R1–R7 / R9 / R10 PASS、R8 FAIL(F-04 修法假設無第一手驗證)→ 主 session 補查 `lib/storage.test.ts:13-22` 先例後改寫 F-04 修法語式;**未經第二次獨立稽查**

**Report generation**: sha256:96e666f05ad4ef6741263b8604f6444bdd5519e20465881419b46bf5c26065ce

---
## [完整證據副檔](pr-127-review.audit.md)
### finding_uid 索引
[f5bc14fffd435792ad06](pr-127-review.audit.md#發現總覽) · [ee3d74541ed64f4644a5](pr-127-review.audit.md#發現總覽) · [74a4a75db6b2e187d1cb](pr-127-review.audit.md#發現總覽) · [be5da913002cba4f8660](pr-127-review.audit.md#發現總覽) · [9656cda308a10e741c0d](pr-127-review.audit.md#發現總覽) · [312b8bf97e9d8a3d1380](pr-127-review.audit.md#發現總覽) · [bd8e813cd3130a1e5e0e](pr-127-review.audit.md#發現總覽) · [a0d981a2e182a6f39ffb](pr-127-review.audit.md#發現總覽) · [7004eea3269097959ff0](pr-127-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | spec §3 的輸入說明仍寫 `quote: {p, t, date}(期貨 WS)`,與同份 spec §1 / §2、CLAUDE.md §4 契約與實作(index engine 轉供報價)相反;下一個照 §3 接期貨 WS 的人會把圖牆 50 張卡的 memo 每 0.1 s 打穿一次、畫面看起來完全正常(`.claude/feat/txf-intraday-overlay/spec.md`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);主 session 直核 CONFIRMED(sed 57 行逐字) | Nice to Have | `auto-fix` | 一句文件改口,零風險 |
| F-02 | 測試檔頭寫「期貨 allday 1K bars + 期貨 WS 現價」、stale 條名寫「期貨 WS 非 open」,實際補尾價來自 index WS、stale 是兩條 WS 任一;斷言正確但測試名是本 repo 判「這條在守什麼」的入口(`frontend/src/lib/txf-overlay-series.test.ts`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);主 session 直核 CONFIRMED(sed 6 / 132 行) | Nice to Have | `auto-fix` | 兩處註解改字 |
| F-03 | CONTEXT.md「TC4 `ReferencePrice` = 前一交易日日盤**結算價**」是 vendor 語意斷言,repo 內(tc4-market-facts 期指節 / docs / spikes)零佐證;`ref` 產生鏈與期貨 tab 同源為真,但「= 結算價」對照 Touchance 文件未查證,而 UI 文案「相對結算價 %」與 CLAUDE.md §4 都引它(`CONTEXT.md`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3 CONFIRMED(baseline 慣例支持:期貨 tab 漲跌色 / 梯中心價已用同一格) | Nice to Have | `ask-user` | 只有 user(TC4 使用者)能對照達錢 4 畫面確認;確認前文件改「參考價,期交所口徑待實測」 |
| F-04 | `useChartToggles` 的模組層 `cached` / `cachedRaw` 跨測試存活,`beforeEach` 只清 localStorage;機制上「存檔為空時 persist 失敗再 set」會留下 `cachedRaw=null` 讓下一條測試靜默拿到上一條的 toggles。逐條追過現有 17 條順序不觸發(第 85-98 條先寫入才裝 spy)(`frontend/src/hooks/useChartToggles.test.ts`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3 PARTIAL(現況不觸發;baseline 慣例衝突:`storage.test.ts:21` 對模組旗標用 `vi.resetModules`,本檔是唯一有快取卻不重置者) | Nice to Have | `auto-fix` | 照 `lib/storage.test.ts:13-22` 樣板(type-only import + `vi.resetModules()` + 每測試 `await import`) |
| F-05 | 台指期鈕開著時 `txfSeries` memo 隨 index engine ~1 Hz 報價失效,`txfBarsToSeries` 每秒重掃 5 日 allday bars(盤中形狀 4,725 根)只為補一格尾;4.3 實測 0.33 ms/次(單幀預算 ~2%),且期貨 tab `FuturesChart` 同型 memo 以 10 倍頻率全掃長跑無事故 → 無使用者可感影響(`frontend/src/App.tsx`) | MEDIUM [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3 PARTIAL → 校正 LOW(實測 bench;WeakMap 每拍 miss 那半 REFUTED:twse / otc 本來就每則推播換新物件) | Nice to Have | `ask-user` | 可選最佳化(先 `sliceCurrentAllday` 切當日再掃),要不要為 0.3 ms 動 code 是取捨 |
| F-06 | `useFuturesBars(key, mode, active = true, enabled = true)` 相鄰兩顆同型 positional boolean、唯一新呼叫端同一運算式傳兩次;寫反順序 tsc 全綠(`frontend/src/hooks/useFuturesBars.ts`) | MEDIUM [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3 REFUTED → 校正 LOW(既有五處 hook 同走 positional boolean 預設值:`useMarketBars` / `useStockBars` / `useBreadthRows` / `useFlashArm`,options 物件僅 `useStockStream` 一例;兩個 @param 各有獨立 doc,測試另釘 (false, enabled) 組合) | 參考用 | `no-op` | 與既有慣例無實質差異,不構成本 PR 缺陷 |
| F-07 | `getSnapshot` 每次 render 同步讀 localStorage(改前 `useState(load)` 每 mount 一次),六個持有者含 App(每則推播重繪)與 StockIntradayChart(每 mousemove)(`frontend/src/hooks/useChartToggles.ts`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3 REFUTED(`lib/fee-discount.ts:41-68` 同款 getSnapshot 每次 readLocal 且消費端更多、檔內明文取捨;`useSignalSound.ts` 同款;本檔多一層 raw 字串比對反而更省;舊寫法的省是以跨 instance 不同步換來,正是 spec Q8 要修的) | 參考用 | `no-op` | 慣例支持;無迴圈、identity 穩定 |
| F-08 | `quote.date` 為 null(index state 未回 / 退避)時錨定日 ≠ 交易日的守門讓開,理論上冷啟動撞 05:00–08:46 窗會疊前一日日盤段;spec §3.1 明文「quote 沒給日期時不擋」(`frontend/src/lib/txf-overlay-series.ts`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3 OUT_OF_SCOPE(spec.md:63-64 逐字;且 `StockIntradayChart.tsx:1183` priceLine 空即早退、盤前整張圖走空態不畫疊線;index engine 08:30 前 tradeDate 本就 = 前一交易日 = bars 錨定日) | 參考用 | `no-op` | spec 已拍板取捨;渲染路徑讓該窗打不到 |
| F-09 | `splitStamp` / `hhmm` 是時戳拆解第三份(`candle.ts:26` 未 export 的同形、`allday.ts:141/161`、`index-accum-adapter.ts::minuteOf`),且 minute → `hhmm()` → `minuteOf()` 同路徑編碼再解碼;本 PR 已入 `docs/next-time.md` 08-27 節(round 1 S5)(`frontend/src/lib/txf-overlay-series.ts`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);主 session 直核 CONFIRMED 但已 deferred(next-time 第 3 條逐字);reviewer 自註「不要求本輪處理」 | 參考用 | `no-op` | 已排進 next-time;收斂時連 `minuteOf` 一起搬,只搬一半會變第四份 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: f5bc14fffd435792ad06 action=auto-fix
F-02 finding_uid: ee3d74541ed64f4644a5 action=auto-fix
F-03 finding_uid: 74a4a75db6b2e187d1cb action=ask-user
F-04 finding_uid: be5da913002cba4f8660 action=auto-fix
F-05 finding_uid: 9656cda308a10e741c0d action=ask-user
F-06 finding_uid: 312b8bf97e9d8a3d1380 action=no-op
F-07 finding_uid: bd8e813cd3130a1e5e0e action=no-op
F-08 finding_uid: a0d981a2e182a6f39ffb action=no-op
F-09 finding_uid: 7004eea3269097959ff0 action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### F-01 spec §3 那行輸入說明還寫著「期貨 WS」,跟 §2 和 CLAUDE.md 講的相反
**File**: `.claude/feat/txf-intraday-overlay/spec.md`
**Line**: 57

**Comment**:
```
§1 / §2 / §3.6 在 review round 1 都回校成「補尾現價走 index engine 轉供的 txf 報價」,
§3 開頭的參數表這行漏掉,還寫 `quote: {p, t, date} | null`(期貨 WS)。
實作(App.tsx 取 useIndexStream().txf / tradeDate)跟 CLAUDE.md §4 都站 index engine 這邊 —
下一個照 §3 去接期貨 WS 的人,圖牆 50 張卡的 memo 會每 0.1 s 被打穿一次,畫面卻完全正常。

改成:`quote: {p, t, date} | null`(index engine 每拍轉供的 `useIndexStream().txf` + `tradeDate`;**不是**期貨 WS)
```
#### F-02 測試檔頭跟 stale 那條的名字還說「期貨 WS 現價」
**File**: `frontend/src/lib/txf-overlay-series.test.ts`
**Line**: 6

**Comment**:
```
檔頭「期貨 allday 1K bars + 期貨 WS 現價」、第 132 行「stale 原樣透傳(期貨 WS 非 open → …)」
兩處跟實際資料源不同:補尾價來自 index WS 的 txf 報價,stale 是 index WS 或期貨 WS 任一非 open(App.tsx)。
斷言本身對,只是測試名會把讀者導去錯的資料源。

檔頭改「+ index engine 轉供的台指期現價(useIndexStream().txf)」;
第 132 行條名改「stale 原樣透傳(index / 期貨 WS 任一非 open → 標籤加註「(中斷)」)」。
```
#### F-03 「ReferencePrice = 前一交易日日盤結算價」這句 repo 裡找不到佐證
**File**: `CONTEXT.md`
**Line**: 66-68

**Comment**:
```
`ref` 的產生鏈是實的(TC4 ReferencePrice → stock_models.ref_milli → futures_engine st.ref → 前端),
期貨 tab 的漲跌色跟梯中心價也用同一格,所以「跟期貨 tab 同一把尺」沒問題。
但「它等於前一交易日日盤結算價」這句全 repo 只有本 PR 新寫的 CONTEXT.md / CLAUDE.md 自己在講:
tc4-market-facts 期指節沒記 ReferencePrice 語意,spikes 也沒有落檔 probe。
若實際是前一日收盤價不是結算價,整條線的分母跟「相對結算價 %」文案一起錯、零訊號。

兩條路:(a) 你在達錢 4 期貨報價面板對一次「參考價」是否等於前一日結算價,對上就在這條補「08-2x 實測」;
(b) 對不到之前把這句改成「TC4 參考價(`ReferencePrice`);是否等於期交所結算價待實測」。
```
#### F-04 toggles 的模組層快取沒有測試重置出口,隔離靠「persist 一定成功」
**File**: `frontend/src/hooks/useChartToggles.test.ts`
**Line**: 9-11

**Comment**:
```
`cached` / `cachedRaw` 是模組變數、跨 test 存活,beforeEach 只清 localStorage。
現在 17 條都過是因為每個 set 都把 cachedRaw 設成非 null 字串,下一條清掉 key 後 raw(null) ≠ cachedRaw 必重載;
但只要有一條在「存檔為空 + setItem 拋」時 set,就會留下 cachedRaw=null,下一條的 removeItem 變 no-op、
getSnapshot 直接回上一條的 toggles,而且靜默。lib/storage.test.ts:21 對模組旗標就用 vi.resetModules 隔離。

照 lib/storage.test.ts:13-22 的樣板:頂層只留 `type StorageMod = typeof import(...)` 這種 type-only import,
beforeEach 內 `vi.resetModules()` 後 `await import("@/hooks/useChartToggles")` 取新模組。
(純靜態 import 下只呼叫 resetModules 不夠 —— 已綁定的模組不會被換掉,storage.test 會寫成 await import 就是為了這個。)
```
#### F-05 台指期鈕開著時每秒重掃 5 日 bars 只為接一格尾,實測 0.3 ms —— 要不要動是取捨
**File**: `frontend/src/App.tsx`
**Line**: 207-210

**Comment**:
```
txfSeries 的 deps 含 txfP / txfTime,index engine 每拍(~1 s)價變就換值 → 每秒跑一次 txfBarsToSeries
把 5 日 allday bars(盤中 ~4,700 根)從頭掃一遍,bars 其實 60 s 才換一次。
量過:0.33 ms/次,單幀預算的 2%;期貨 tab 的 FuturesChart 同型 memo 以期貨 WS 0.1 s 的頻率全掃 slice 也長跑沒事。
所以不是 bug、不擋。要省的話最省事的改法是進函式先 `sliceCurrentAllday(bars)` 只掃當日那段(~300 根),
不必拆兩顆 memo。
```
## 沒做的部分（結案對帳）
- Codex 中性 / 對抗軸:FAIL(N-A)—— 本機無 `codex` CLI,兩軸零 finding。
- Gemini Flash / Pro:FAIL(N-A)—— 本機無 `agy`。
- Step 2.96 / 2.98 提問:未執行(工具缺席,提問無意義),走預設值並在 header 註明。
- Step 4.1:N-A(無非 CC finding)。Step 4.2:FAIL → 全部 INCONCLUSIVE(無 codex),以 4.3 **同軸** `code-reviewer` 批次 + 主 session 直核代之 —— 這不是獨立 cross-axis 證據,F-06 / F-07 的 REFUTED 與 F-05 的降級都來自同一模型家族的 baseline / bench,user 看「參考用」時可自行下調權重。
- sem blast radius:跑了,空輸出跳過(無 `sem`)。
- React-doctor:PASS(跑了,零新引入;newCount=1 為 baseline 模式對整檔 warning 的誤標,以 hunk 行號對照排除)。
- C4 / spec-compliance:SKIPPED (C4_AUTHORITY_INPUT_INVALID),0 clauses,未派 reviewer;spec 在 `.claude/feat/`,authority 只認 openspec/。
- 未驗證前提:F-03「ReferencePrice = 前一交易日日盤結算價」對 Touchance 官方文件未查證(本環境無 TC4 文件通道;已 cap Nice + ask-user);F-05 的 0.33 ms 為 code-reviewer 以 node bench 逐字複製函式邏輯量得,非瀏覽器內實測。
- 未拍到真環境畫面:本輪為回溯 review,未重跑 UI 截圖(PR 內 verification.md 已記 08-27 盤後 prod 個股 ref 全 null、線本體待次一交易日過目)。
- Self-Verify:已執行(auditor 以 Read 讀取草稿檔本身,未讀其他產物)。R8 FAIL —— 原缺口:F-04 建議「`vi.resetModules()` + 動態 import」未附第一手驗證;修正方式:主 session 讀 `lib/storage.test.ts:13-22`(type-only import + `vi.resetModules()` + 每測試 `await import` 的既有樣板),F-04 的 inline comment / 總覽 Action 理由 / Nice to Have 條目三處改為引該樣板的語式,並明寫純靜態 import 下只呼叫 resetModules 不夠。修正後未重派 auditor,**本報告未經第二次獨立稽查**。
