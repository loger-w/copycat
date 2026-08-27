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

## Spec 依據

- 偵測到 `.claude/feat/txf-intraday-overlay/spec.md`(路徑不符 Step 2.6 預設 heuristic,但為本 repo /feat 流程的 originating spec,主 agent 手動納入;§0 九題拍板表、§1 使用者看到什麼、§2 資料流(借期貨 tab bars、active + enabled 雙閘、補尾走 index engine 轉供報價)、§3 `txfBarsToSeries` 六條語意、§4 seams S1–S3、§5 白名單五條:不動後端 / 不拉 x 軸 / 不 bump `TOGGLES_VERSION` / index·futures 態無鈕 / 江波圖調色盤不動)。同目錄 `verification.md` 與 `code-review-round-1.json`(in-flow two-axis review 處置)亦在 F 內。
- ⚠️ spec 作者 = PR 作者(`git log --format=%an` 於 spec 路徑 → Loger;PR author loger-w;同一 session 產出。out-of-scope 判定以此 spec 為據時注意利益重疊 —— 本輪 F-08 的 OUT_OF_SCOPE 正是引 spec §3.1「quote 沒給日期時不擋」)。

- `SPEC_COMPLIANCE` receipt:gate=SKIPPED;dispatch=NOT_APPLICABLE;dispatch_count=0;reason_code=C4_AUTHORITY_INPUT_INVALID(以 spec §3.1「必須等於 quote.date」為候選 INVARIANT 送 `pr-review-c4.py resolve-authority`,reducer 回 `status=SKIPPED`;spec 位於 `.claude/<flow>/<slug>/`,不在 authority 允許路徑,與 08-25 #106 / 08-27 #119 判定同因);requested_model=opus;observed_model=UNAVAILABLE;effort=xhigh;tools=0;clauses=0;findings=0;observations=0;invalidated=0;未派 reviewer。

## 變更概要

provenance:32 authored / 0 inherited(base = master,免驗)。

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `.claude/feat/txf-intraday-overlay/code-review-round-1.json` | 略過(新增) | in-flow two-axis round 1 處置紀錄(12 條) |
| `.claude/feat/txf-intraday-overlay/evidence/group-grid-toggle-row-afterhours.jpg` | 略過(新增) | 圖牆 toggle 列九鈕截圖 |
| `.claude/feat/txf-intraday-overlay/evidence/stock-2330-toggle-row-afterhours.jpg` | 略過(新增) | 個股頁 toggle 列八鈕截圖 |
| `.claude/feat/txf-intraday-overlay/spec.md` | 有 finding(新增) | originating spec(F-01:§3 輸入說明仍寫期貨 WS) |
| `.claude/feat/txf-intraday-overlay/verification.md` | 無 finding(新增) | gate / 真環境 / 核 goal 落檔 |
| `CLAUDE.md` | 無 finding(修改) | §4 補「台指期疊線分鐘鍵 = 1K 終點標記 −1」契約 |
| `CONTEXT.md` | 有 finding(修改) | glossary 台指期 / 加權 / 台指(禁用)三條(F-03:結算價語意未驗證) |
| `docs/next-time.md` | 無 finding(修改) | 08-27 節:期貨 tab 15:00 起算 /mod、S4 表格化、S5 分鐘編解碼 |
| `frontend/src/App.tsx` | 有 finding(修改) | 掛 `useFuturesBars("TXF")` 雙閘 + `txfBarsToSeries` memo + indexOverlay 三鍵(F-05) |
| `frontend/src/components/index/MarketChart.test.tsx` | 無 finding(修改) | toggles fixture 補 `idxTxf: false` |
| `frontend/src/components/index/MarketPane.memo.test.tsx` | 無 finding(修改) | 同上 |
| `frontend/src/components/index/MarketPane.size.test.tsx` | 無 finding(修改) | 同上 |
| `frontend/src/components/index/MarketPane.storage.test.tsx` | 無 finding(修改) | 同上 |
| `frontend/src/components/index/MarketPane.test.tsx` | 無 finding(修改) | 同上 |
| `frontend/src/components/stock/GroupGridView.test.tsx` | 無 finding(修改) | 九鈕表加 `["idxTxf","台指期"]` |
| `frontend/src/components/stock/GroupGridView.tsx` | 無 finding(修改) | `GRID_TOGGLES` 加台指期、indexSeries 條件加 `idxTxf` |
| `frontend/src/components/stock/StockIntradayChart.futures.test.tsx` | 無 finding(修改) | fixture 補欄 |
| `frontend/src/components/stock/StockIntradayChart.index.test.tsx` | 無 finding(修改) | 鈕清單 7 → 8(事前標記) |
| `frontend/src/components/stock/StockIntradayChart.indexlines.test.tsx` | 無 finding(修改) | txf 線 / 反灰文案 / 無結算價 三條斷言 |
| `frontend/src/components/stock/StockIntradayChart.memo.test.tsx` | 無 finding(修改) | fixture 補欄 |
| `frontend/src/components/stock/StockIntradayChart.synchover.test.tsx` | 無 finding(修改) | fixture 補欄 |
| `frontend/src/components/stock/StockIntradayChart.tsx` | 無 finding(修改) | 台指期線色 class、toggleDefs 加鈕(反灰:無台指期資料 / 無結算價)、idxLines memo 三鍵 |
| `frontend/src/components/stock/StockIntradayChart.variant.test.tsx` | 無 finding(修改) | 七鈕 → 八鈕 |
| `frontend/src/hooks/useChartToggles.test.ts` | 有 finding(修改) | S2 跨 instance 同步 + 外部清空回預設(F-04:模組 store 無測試重置出口) |
| `frontend/src/hooks/useChartToggles.ts` | 有 finding(修改) | module store + `useSyncExternalStore`(F-07:getSnapshot 每 render 讀 localStorage) |
| `frontend/src/hooks/useFuturesBars.test.ts` | 無 finding(修改) | enabled=false 零 fetch 一條 |
| `frontend/src/hooks/useFuturesBars.ts` | 有 finding(修改) | 第四參數 `enabled`(F-06:相鄰兩顆 positional boolean) |
| `frontend/src/index.css` | 無 finding(修改) | `--color-idx-txf` token |
| `frontend/src/lib/index-overlay-lines.test.ts` | 無 finding(修改) | txf 鍵映射 / 兩窗 |
| `frontend/src/lib/index-overlay-lines.ts` | 無 finding(修改) | `IndexOverlayKey` 三鍵、`OVERLAY_KEYS` 順序 |
| `frontend/src/lib/txf-overlay-series.test.ts` | 有 finding(新增) | S1 14 條(F-02:檔頭 / stale 條仍寫期貨 WS) |
| `frontend/src/lib/txf-overlay-series.ts` | 有 finding(新增) | `txfBarsToSeries` 純函式(F-08 quote.date 缺席不設防;F-09 時戳拆解第三份) |

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

#### F-06 active / enabled 兩顆相鄰 boolean —— 不是本 PR 缺陷,既有 hook 都這樣寫

**File**: `frontend/src/hooks/useFuturesBars.ts`
**Line**: 58-59

**Comment**:
```
不是 PR 缺陷:reviewer 擔心 (active, enabled) 兩顆 positional boolean 寫反不會紅,
但 useMarketBars / useStockBars / useBreadthRows / useFlashArm 五處既有 hook 全走同款 positional 預設值,
options 物件只有 useStockStream 一例;兩個 @param 各有獨立 doc,useFuturesBars.test 也釘了 (false, enabled) 組合。
唯一新呼叫端 App.tsx:193 兩格傳同一個 txfWanted,交換不可能;(true, false) 在 TQ 下 disabled query 不跑 interval,無害。
要統一成 options 物件是全 hooks 目錄的事,不在這支 PR。
```

#### F-07 getSnapshot 每次 render 讀 localStorage —— 不是本 PR 缺陷,fee-discount 同款已上線

**File**: `frontend/src/hooks/useChartToggles.ts`
**Line**: 110-111

**Comment**:
```
不是 PR 缺陷:lib/fee-discount.ts:41-68 的 readFeeDiscount 當 getSnapshot 同樣每次 readLocal、
消費端(三座梯 / 側欄 / header)比這裡六個 holder 還多,檔內 61-62 行明寫「每次 render 讀一次 localStorage 不會造成迴圈」;
useSignalSound.ts 同款。本檔還多一層 raw 字串比對、字串沒變直接回同一物件,比兩個先例更省。
舊 useState(load) 的省是用「跨 instance 不同步」換的,那正是這次要修的病(spec Q8)。
```

#### F-08 quote.date 缺席時不擋錨定日 —— spec 明文接受,而且那個窗畫面根本不畫疊線

**File**: `frontend/src/lib/txf-overlay-series.ts`
**Line**: 68

**Comment**:
```
不是 PR 缺陷:spec §3.1 逐字「quote 沒給日期時不擋」,code 註解同源,是已拍板取捨。
再追渲染:StockIntradayChart.tsx:1183 priceLine 空就早退,盤前個股無成交 → 整張圖走空態,疊線連算都不畫;
index engine 在 08:30 前 tradeDate 本來就還是前一交易日 = bars 錨定日,閘門有值也放行 —— 那正是 §1「盤後看盤疊最近交易日」的預期。
08:46–09:00 試撮窗的錯疊風險跟 quote.date 是否為 null 無關,是另一條題目(現在也沒人提)。
```

#### F-09 時戳拆解第三份 —— 已經在 next-time 排隊,這輪不動

**File**: `frontend/src/lib/txf-overlay-series.ts`
**Line**: 45-50

**Comment**:
```
不是要這輪改:splitStamp / hhmm 跟 candle.ts:26(未 export)、allday.ts:141/161、index-accum-adapter.ts::minuteOf 同形,
而且 minute → hhmm() → sortedIndexRows 再 minuteOf() 解回來,同一條路徑編碼又解碼 —
這是「IndexSeries 同形換零改動 reader」的代價,docs/next-time.md 08-27 節第 3 條已記(round 1 S5)。
收斂時要連 minuteOf 一起搬進 lib/allday.ts,只搬一半會變第四份。
```

### Opus 原始 findings (first-pass, context-aware)

- **F-01**(reviewer 原編號 TS-8,LOW [typescript-reviewer])`.claude/feat/txf-intraday-overlay/spec.md:57` —— spec §3 的輸入說明仍寫「期貨 WS」,與 §2 / CLAUDE.md 契約相反;實作與契約都站在 index engine 這一邊。anchor:`` `quote: {p, t, date} | null`(期貨 WS) ``。search-proof:reviewer 讀 App.tsx:200-203、txf-overlay-series.ts:21-27、CLAUDE.md:259-260 三處對照。
- **F-02**(reviewer 原編號 TS-9,LOW [typescript-reviewer])`frontend/src/lib/txf-overlay-series.test.ts:6` —— 測試檔頭與 stale 條(第 132 行)的敘述停在「期貨 WS 現價」;實際 `wsStale` 產生點是 App.tsx:206 兩條 WS 任一,補尾價來自 index WS。anchor:`期貨 allday 1K bars + 期貨 WS 現價`。
- **F-03**(reviewer 原編號 TS-6,LOW [typescript-reviewer])`CONTEXT.md:66-68` —— 「TC4 ReferencePrice = 前一交易日日盤結算價」是 vendor 語意斷言,repo 內查不到佐證;`ref` 產生鏈(stock_models.py:203 → futures_engine.py:467-468 → App.tsx:199)與期貨 tab 同源為真。anchor:`**台指期**:`。search-proof:`Grep ReferencePrice` 全庫只命中指數 probe 紀錄、tc4-market-facts 指數條、fake sidecar;`Grep 結算價` 只命中 FinMind `TaiwanOptionFinalSettlementPrice`。
- **F-04**(reviewer 原編號 TS-4,LOW [typescript-reviewer])`frontend/src/hooks/useChartToggles.test.ts:9-11` —— 模組層 store 快取無重置出口,測試隔離靠「persist 一定成功」隱性前提;存檔為空時 writeLocal 失敗再 set 會留下 `cached=使用者值`、`cachedRaw=null`,下一條 removeItem 是 no-op → 靜默拿到上一條 toggles。anchor:`beforeEach(() => {` / `window.localStorage.removeItem(KEY);`。
- **F-05**(reviewer 原編號 TS-1,MEDIUM [typescript-reviewer])`frontend/src/App.tsx:207-210` —— memo deps 含 `txfP` / `txfTime`(index_engine.py:173 `throttle_secs=1.0`、:683-688 價變自記)→ 每秒失效,`txfBarsToSeries` 從頭掃 5,700 根(`FUTURES_MINUTE_DAYS=5` × 1140)且 `minutes` 新物件讓 `SORTED_ROWS` WeakMap 每拍 miss;bars 60 s 才換。建議拆兩顆 memo。anchor:`const txfSeries = useMemo(`。
- **F-06**(reviewer 原編號 TS-2,MEDIUM [typescript-reviewer])`frontend/src/hooks/useFuturesBars.ts:58-59` —— 相鄰兩顆同型 positional boolean(active / enabled)互換不紅;唯一新呼叫端 App.tsx:193 同一運算式餵兩次;允許 `(…, true, false)` 無意義組合。建議 options 物件。anchor:`  active = true,` / `  enabled = true,`。reviewer 自標判斷題。
- **F-07**(reviewer 原編號 TS-3,LOW [typescript-reviewer])`frontend/src/hooks/useChartToggles.ts:110-111` —— `getSnapshot` 每次 render 同步 `readLocal`;六個持有者(App:190、IndexPage:108、FuturesChart:159、GroupGridView:294、StockChart:70、StockIntradayChart:1706);改前 `useState(load)` 每 mount 一次;實測未做、估遠低於一幀;不擋合併。anchor:`function getSnapshot(): ChartToggles {` / `  const raw = readLocal(CHART_TOGGLES_KEY);`。
- **F-08**(reviewer 原編號 TS-5,LOW [typescript-reviewer])`frontend/src/lib/txf-overlay-series.ts:68` —— `quote.date` 為 null 時錨定日不設防,冷啟動撞 05:00–08:46 窗可能疊前一日日盤段;spec §3.1 明文「quote 沒給日期時不擋」,reviewer 自標「已拍板取捨不是偏離」。anchor:`if (anchor !== null && quote !== null && quote.date !== null && quote.date !== anchor) anchor = null;`。
- **F-09**(reviewer 原編號 TS-7,LOW [typescript-reviewer])`frontend/src/lib/txf-overlay-series.ts:45-50` —— 時戳拆解第三份 + 分鐘編碼再解碼;已入 next-time(round 1 S5),reviewer 自註「不要求本輪處理」。anchor:`function splitStamp(t: string): [string, number] | null {`。search-proof:Grep 命中 candle.ts:26、allday.ts:141/161、index-accum-adapter.ts::minuteOf。

reviewer 另列「追加確認過、不成立因此未列」五條:(a) spec §2「TQ 同鍵只跑一支 timer」為真(FuturesChart observer 由 `active={tab === "futures"}` 關輪詢);(b) `getSnapshot` identity 穩定、persist 失敗不觸發無限重繪;(c) 分鐘鍵 −1 方向正確(allday.ts:178 以 08:46 為終點標記域起點);(d) `stroke-idx-txf` / `fill-idx-txf` 有 `@theme` token 且字面值出現於 StockIntradayChart.tsx:144,149;(e) 白名單五條逐條核過皆遵守。

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查。

### Codex 對 Opus 的複查結果（對稱化 4.2）

**Codex 複查 Opus 失敗 — 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(本機無 codex)。全部 CC finding 視同 INCONCLUSIVE,改由 4.3 同軸 `code-reviewer` 批次(6 條:TS-1–TS-6,輸出 ID 集合與輸入完全相符、每列四欄齊)+ 主 session 直核(3 條文件 / 註解類:TS-7/8/9)代之。**同軸、非獨立驗證**,權重低於真正的 cross-axis。

| Opus # | 原始 severity | 4.3 verdict | 校正 severity | 備註(baseline / 他軸為何漏) |
| --- | --- | --- | --- | --- |
| F-01 | LOW | CONFIRMED(主 session `sed -n 57p` spec.md 逐字) | LOW | 文件漂移;lone 原因:他軸缺席(工具) |
| F-02 | LOW | CONFIRMED(主 session `sed -n 6p;132p` 逐字) | LOW | 同上 |
| F-03 | LOW | CONFIRMED(code-reviewer:grep ReferencePrice / 結算價 全 repo,期指語意唯一出處即本 PR 新寫兩處;既有用法 stock_models.py:203 → futures_engine.py:467 → futures-accum-adapter.ts:131 → 期貨分時漲跌色 / FuturesLadder.tsx:136 同一格) | LOW | 慣例支持(同源用法)但對 Touchance 文件未驗證;本環境無 TC4 文件通道 |
| F-04 | LOW | PARTIAL(code-reviewer 逐條追狀態:第 85-98 條 line 86 先 setItem 成功才裝 spy → cachedRaw 非 null,必重載;實跑 17/17 passed;grep resetModules → storage.test.ts:21 有先例) | LOW | 慣例衝突(唯一有快取卻不重置的 store 測試);現況零觸發 |
| F-05 | MEDIUM | PARTIAL(code-reviewer 以 node bench 逐字複製函式邏輯、盤中形狀 4,725 根:0.3266 ms/次;sortedIndexRows 271 鍵 0.047 ms;WeakMap 每拍 miss 半條 REFUTED —— useIndexStream.ts:60-71 toSeries 每則推播展開新 minutes、twse/otc 本就每拍 miss;baseline FuturesChart.tsx:279-289 同型 memo deps 含 liveP 0.1 s 全掃 slice,08-05 起長跑) | LOW | 慣例支持;可選 nit:進函式先 sliceCurrentAllday |
| F-06 | MEDIUM | REFUTED(code-reviewer grep `active = true|enabled = true|boolean,$` hooks/lib:useStockBars.ts:65-69 已是兩相鄰 positional boolean 且 exported;useMarketBars.ts:56 / useBreadthRows.ts:40 / useFlashArm.ts:32 / useStockBars.ts:84 全 positional;options 僅 useStockStream 一例;useFuturesBars.test.ts:148-160 釘 (false, enabled)) | LOW | 慣例支持;交換不可能(同運算式);錯配組合在 TQ 下無害 |
| F-07 | LOW | REFUTED(code-reviewer grep useSyncExternalStore + readLocal:fee-discount.ts:41-68 同款每次 readLocal 且消費端更多、61-62 行明文取捨;useSignalSound.ts:21/43 同款;本檔多 raw 比對更省) | LOW | 慣例支持;無迴圈 |
| F-08 | LOW | OUT_OF_SCOPE(spec.md:63-64 逐字「quote 沒給日期時不擋」;StockIntradayChart.tsx:1183 priceLine 空早退;index_engine._rollover_loop 08:30 前不 swap day) | LOW | spec 明文;同人 spec(見 Spec 依據) |
| F-09 | LOW | CONFIRMED but deferred(主 session `grep -n "第三份" docs/next-time.md` 命中 08-27 節) | LOW | 已入 next-time;reviewer 自註不要求本輪 |

## Action Items

**Severity calibration**:6c(移除既有防護類)—— 本 PR 無移除既有防護類 finding(`useChartToggles` 重寫是加同步不是削弱;`enabled` 是加閘);6d-1 hedge cap / 6d-3 Must Fix 雙半條件逐條套用 —— 九條無一有 user-visible 重現路徑 + release-blocking 後果,故零 Must / 零 Should;6d-2 由 4.3b 取代(全部 lone finding,他軸缺席為工具缺席非判斷,不機械降級;F-05 / F-06 的降級來自 4.3 實測 / baseline 反證,非「他軸沉默」);provenance cap N-A;安全類矩陣 N-A(無安全 finding)。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix（合併前必修）

- 無

### Should Fix（強烈建議）

- 無

### Nice to Have（可選優化）

- F-01 spec §3 那行輸入說明還寫著「期貨 WS」(`.claude/feat/txf-intraday-overlay/spec.md:57`)—— 一句改口;留著會把下一個實作者導去 0.1 s 流
- F-02 測試檔頭跟 stale 條名還說「期貨 WS 現價」(`frontend/src/lib/txf-overlay-series.test.ts:6`)—— 兩處註解改字
- F-03 「ReferencePrice = 前一交易日日盤結算價」repo 內無佐證(`CONTEXT.md:66-68`)—— 請 user 在達錢 4 對一次;對不到就改「參考價,期交所口徑待實測」
- F-04 toggles 模組層快取無測試重置出口(`frontend/src/hooks/useChartToggles.test.ts:9-11`)—— 照 `lib/storage.test.ts:13-22` 樣板(type-only import + `vi.resetModules()` + 每測試 `await import`);現況 17/17 不觸發
- F-05 台指期鈕開著時每秒重掃 5 日 bars(`frontend/src/App.tsx:207-210`)—— 實測 0.33 ms/次、與期貨 tab 同型長跑無事故;可選 `sliceCurrentAllday` 先切當日

### 參考用（任一軸驗證為 REFUTED 或 OUT_OF_SCOPE）

- F-06 Opus [typescript-reviewer] 擔心 active / enabled 兩顆相鄰 positional boolean 寫反不紅 → code-reviewer 於 `useStockBars.ts:65-69` / `useMarketBars.ts:56` / `useBreadthRows.ts:40` / `useFlashArm.ts:32` 找到同 pattern 五處長跑、唯一呼叫端同運算式傳兩次 → 使用者自行判斷是否採納(統一成 options 物件是 hooks 目錄級的事)
- F-07 Opus [typescript-reviewer] 擔心 getSnapshot 每 render 讀 localStorage → code-reviewer 於 `lib/fee-discount.ts:41-68`(明文取捨)/ `useSignalSound.ts:21,43` 找到同款已上線 → 使用者自行判斷
- F-08 Opus [typescript-reviewer] 擔心 quote.date null 時疊前一日 → spec §3.1 明文「quote 沒給日期時不擋」(spec 作者 = PR 作者)+ 渲染早退 / 後端換日時序讓該窗打不到 → 如 scope 應擴大、使用者自行決定
- F-09 Opus [typescript-reviewer] 時戳拆解第三份 → 已在 `docs/next-time.md` 08-27 節排隊,reviewer 自註不要求本輪 → 收斂時連 `minuteOf` 一起搬

## 審查工具比較 (qualitative)

- CC 視角(typescript-reviewer):核心機制五項(TQ 同鍵單 timer、getSnapshot identity、分鐘鍵 −1 方向、token 字面值、白名單)逐一追過成立;9 條新發現全屬文件一致性 / 測試基建 / 可選最佳化 / API 形狀判斷題,無行為 bug、無安全面。
- Codex 中性 / 對抗 / Gemini:N-A,重疊率無法計算。
- 4.2 分佈:全部 INCONCLUSIVE(無 codex);4.3 同軸 code-reviewer 批次(6 條):CONFIRMED 1 / PARTIAL 2 / REFUTED 2 / OUT_OF_SCOPE 1;主 session 直核(3 條):CONFIRMED 3(其中 1 條已 deferred)。校正 severity:MEDIUM→LOW 2 條(F-05 實測、F-06 baseline)。
- 對抗式第三軸增益:N-A。
- React-doctor 機械軸:跑了,零新引入(baseline 模式的 newCount=1 經 hunk 對照判存量)。

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
