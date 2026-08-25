# PR #111 Code Review 比較報告 · SHA d1439bd6

**Report projection schema**: 1

**PR**: [loger-w/copycat#111](https://github.com/loger-w/copycat/pull/111)
**標題**: feat: 看盤 UX 四功能(指數疊線 / 側欄切群組 / 同步十字線 / corr 加四腿)+ 成交當下樂觀套用部位(#107)
**作者**: loger-w(commits 署名 Loger)
**分支**: `feat/chart-ux-batch-0826` → `master`(PR 狀態 OPEN)
**變更**: 61 檔案, +2333 / -165
**審查日期**: 2026-08-26
**Review input basis**: source repo R_kgDOTsITBg + d1439bd61e83b47076c736be67236efac4cd1a35;destination repo R_kgDOTsITBg + 7d50c948d8121c8a94f4088bcd3a584606dfa448;`input_binding: verified`(worktree HEAD = source SHA;`origin/master` = destination SHA,兩者皆於 Step 2.5 rev-parse 逐字相等)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-111`(detached)
**worktree HEAD**: d1439bd61e83b47076c736be67236efac4cd1a35
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer ×3(chunk 1 / 3 / 4)+ typescript-reviewer ×1(chunk 2)(依 chunk 主語言分派 —— 本 PR py 632 / tsx+ts 400 源碼行,py 61% 名義上獨佔「pick exactly one」,但兩種語言在 chunk 內是分離的,故偏離單一 primary 規則、逐 chunk 派語言 reviewer;dispatch 顯式 model=opus、effort 依 frontmatter xhigh;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=61 → covered 15 / no-issues 43 / skipped 3 / **missed 0**(chunked: 是,4 塊;FILE_COUNT=20 源檔 > 15、DIFF_LINES=2498 > 800,兩門檻皆觸發;chunk 1 = 30 檔 672 行(11 源檔)、chunk 2 = 19 檔 794 行(7 源檔)、chunk 3 = 7 檔 772 行(2 源檔)、chunk 4 = 5 檔 260 行(0 源檔);union = F;skipped 3 = `evidence/f1-index-overlay-2330.jpg` / `f2-sidebar-click-switches-group.jpg` / `f3-sync-crosshair-group-wall.jpg`,理由:jpg 截圖無可審文字,chunk 1 回 INTENTIONALLY_SKIPPED)
**定位 (ENH-B)**: anchored exact 21 / ambiguous 1 / **FAILED 0**(全部 anchor 於 worktree HEAD 逐字比中;line 以比中結果為準,reviewer 自報行號僅作參考)
**React-doctor (2.97)**: 未引入新問題(既有 2 條不計;工具 baseline 報 newCount=2 = `src/App.tsx:116 no-giant-component` 與 `src/components/stock/GroupGridView.tsx:70 only-export-components`,兩者皆不在本 PR 的 `+` 行:App.tsx hunks 在 152 / 331,GroupGridView.tsx 第 70 行 `export function gridShape` 是 base 既有行因上方刪 1 行位移 —— 與 PR #106 報告同一種 line-shift artifact)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問(/auto 無人值守)
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,61 檔全部 authored)
**審查軸狀態**: primary(python-reviewer chunk 1)PASS(5 findings、30/30 accounting);primary(typescript-reviewer chunk 2)PASS(6 findings、19/19);primary(python-reviewer chunk 3)PASS(9 findings、7/7);primary(python-reviewer chunk 4)PASS(5 findings、5/5);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條判斷式複查,見備註欄);React-doctor PASS(0 新增)
**Self-Verify**: SKIPPED (agent error)—— auditor 輸出缺 R4 行(格式錯誤,依 Step 6 規則不採信 verdict、不重派);其列出的 R3 / R6 / R7 / R8 缺口已補寫(見「沒做的部分」),R5 為命令固定 canonical record 格式(`F-NN finding_uid: … action=…`,ordinal 即 display_ordinal、reason 在表格欄)不適用;**本報告未經獨立稽查通過**

**Report generation**: sha256:5638863cff16055fda8cfab9cb3e010e08b20a7acb8a0eccb66fc6088ba1a349

---

## Spec 依據

- 偵測到 spec:`.claude/feat/chart-ux-batch-0826/spec.md`(PR 內新增,126 行;路徑不符 Step 2.6 的檔名 heuristic,但內容是本 PR 的 F1–F5 需求原文 + 13 條 `[auto-default]` 決定 + 測試 seams,以 spec 身分全文注入四支 reviewer)。另 `verification.md`、`code-review-round-{1,2}.json`、`evidence/corr-legs-probe.md` 為驗證 / review 紀錄,不當 spec 用;`docs/next-time.md` 本輪新段為留尾清單。
- 關鍵內容:F1「台指」= 加權指數 IX0001(非台指期)、相對昨收 % 映個股軸、指數鈕預設關;F2 只在群組檢視切、未分組不切、受控必傳;F3 分鐘為鍵、他卡錨收盤、十字線預設開;F4 四腿全加、台幣不加(TC4 全樹無 TWD)、標準 CL/GC、台積電走現貨、TWS 閘沿用 08:30–13:35;F5 走 /bug loop(FakeCom 模擬)、套用規則七條、前端 debounce 不動。明示 out-of-scope:台幣匯率腿、台指期版 F1、無券 / 零股 / 選擇權成交不套。
- ⚠️ spec 作者 = PR 作者(`git log --format=%an origin/feat/chart-ux-batch-0826 -- .claude/feat/chart-ux-batch-0826/spec.md` = Loger,與 commits 作者相同;out-of-scope 判定以此 spec 為據時,注意作者自寫 spec 的利益重疊)。本輪 F-01 直接指出 spec §F4 對 tc4-market-facts (b) 的引用方向讀反,即 spec 本身有錯。
- SPEC_COMPLIANCE receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED`(spec 在 `.claude/feat/`,reducer 只認 `openspec/**`;另本機 `pr-review-c4.py` permit 目錄為 POSIX-only,即使路徑合法 dispatch-envelope 亦會非 0)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool calls=0(無)。0 clauses / 0 findings / 0 observations / 0 invalidated。

## 變更概要

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `.claude/feat/chart-ux-batch-0826/code-review-round-1.json` | 新增(artifact) | spec / review JSON / verification / 探測證據 |
| `.claude/feat/chart-ux-batch-0826/code-review-round-2.json` | 新增(artifact) | spec / review JSON / verification / 探測證據 |
| `.claude/feat/chart-ux-batch-0826/evidence/corr-legs-probe.md` | 新增(artifact) | spec / review JSON / verification / 探測證據 |
| `.claude/feat/chart-ux-batch-0826/evidence/f1-index-overlay-2330.jpg` | 新增(截圖) | 真環境證據 |
| `.claude/feat/chart-ux-batch-0826/evidence/f2-sidebar-click-switches-group.jpg` | 新增(截圖) | 真環境證據 |
| `.claude/feat/chart-ux-batch-0826/evidence/f3-sync-crosshair-group-wall.jpg` | 新增(截圖) | 真環境證據 |
| `.claude/feat/chart-ux-batch-0826/spec.md` | 新增(artifact) | spec / review JSON / verification / 探測證據 |
| `.claude/feat/chart-ux-batch-0826/verification.md` | 新增(artifact) | spec / review JSON / verification / 探測證據 |
| `CLAUDE.md` | 修改 | §4 新契約:調色盤色數 ≥ 腿數 |
| `configs/correlation.json` | 修改 | +4 腿 VX / CL / GC / TSMC;_comment 改述加腿要動的檔 |
| `copycat/capital/client.py` | 修改 | 成交當下 emit capital_position(source: fill);三段回查鏈 ms log;期貨鍵差異 log |
| `copycat/capital/mapping.py` | 新增函式 | contract_from_fill(回報 idx8 + idx33 → 期交所契約碼) |
| `copycat/capital/reply.py` | 修改 | ReplyRecord.contract_ym(idx33 六位數字) |
| `copycat/capital/store.py` | 修改 | apply_reply 回傳部位是否變;_apply_fill_locked 樂觀套用(增量 / 殘量 / 均價 / 歸零) |
| `copycat/corr_config.py` | 修改 | DEFAULT_CONFIG 同步 11 腿 |
| `copycat/live/corr_source.py` | 修改 | taifex_leg_gate → segment_leg_gate(taifex=, tws=);TWS 腿以個股日盤閘自癒 |
| `copycat/live/stock_source.py` | 修改 | in_trading_hours_now 加 now= 參數(預設不變) |
| `copycat/server/app.py` | 修改 | _default_corr_source 組兩把閘 |
| `docs/next-time.md` | 修改 | 本輪留尾九條 |
| `frontend/src/App.tsx` | 修改 | indexOverlay useMemo 下傳 StockPage |
| `frontend/src/components/corr/river-colors.test.ts` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/corr/river-colors.ts` | 修改 | 調色盤 7 → 11 |
| `frontend/src/components/index/MarketChart.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/index/MarketPane.memo.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/index/MarketPane.size.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/index/MarketPane.storage.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/index/MarketPane.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/CardIntradayChart.tsx` | 修改 | indexSeries / syncHoverMin / onHoverMinute pass-through |
| `frontend/src/components/stock/GroupGridView.geometry.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/GroupGridView.memo.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/GroupGridView.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/GroupGridView.toggle.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/GroupGridView.tsx` | 修改 | 受控 selectedGroup / onSelectGroup;syncMin 共同 hover 分鐘;GRID_TOGGLES +3;NOOP_HOVER |
| `frontend/src/components/stock/StockChart.tsx` | 修改 | indexSeries 下傳 |
| `frontend/src/components/stock/StockIntradayChart.futures.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/StockIntradayChart.index.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/StockIntradayChart.indexlines.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/StockIntradayChart.memo.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/StockIntradayChart.synchover.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/StockIntradayChart.tsx` | 修改 | indexSeries / syncHoverMin / onHoverMinute 三個 prop;idxLines useMemo;指數線 + 右緣標籤;toggle 列 +2 鈕 |
| `frontend/src/components/stock/StockIntradayChart.variant.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/StockPage.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/StockPage.tsx` | 修改 | useStockGroup 持有群組;側欄 onSelect(code, group) 橋接;indexSeries 下傳 |
| `frontend/src/components/stock/WatchlistSidebar.test.tsx` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/components/stock/WatchlistSidebar.tsx` | 修改 | onSelect 第二參 = 列所在群組 |
| `frontend/src/hooks/useChartToggles.test.ts` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/hooks/useChartToggles.ts` | 修改 | 新鍵 idxTwse / idxOtc(預設關)/ syncHover(預設開) |
| `frontend/src/hooks/useStockGroup.ts` | 新增 | 群組選擇 + localStorage 記憶 hook |
| `frontend/src/index.css` | 修改 | --color-river-8..11 |
| `frontend/src/lib/index-overlay-lines.test.ts` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `frontend/src/lib/index-overlay-lines.ts` | 新增 | 指數相對昨收 % → 個股價格軸的純幾何 |
| `spikes/corr_legs_probe.py` | 新增 | TC4 四步探測(catalog / oracle / REALTIME / 1K) |
| `tests/capital/test_fill_latency.py` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `tests/capital/test_mapping.py` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `tests/capital/test_reply.py` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `tests/capital/test_store.py` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `tests/live/test_corr_source.py` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `tests/server/test_corr_routes.py` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `tests/server/test_main_wiring.py` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `tests/server/test_river_routes.py` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |
| `tests/test_corr_config.py` | 測試 | 新增 / 更新測試(見對應 chunk 逐檔交代) |

## 發現總覽

| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | 台積電腿跟個股引擎訂同一個 symbol、不同 key,任一邊退訂會把上游 2330 整個拔掉(`configs/correlation.json`) | HIGH [python-reviewer(chunk 1)+ python-reviewer(chunk 4)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Must Fix | `auto-fix` | 修法局部且明確(TWS 腿改用與個股引擎同一把訂閱窗 key),真環境可驗 |
| F-02 | 開機 backlog 重播會把「今日成交淨額」當部位疊在空集合上,出現可點平倉的幻影列(`copycat/capital/store.py`) | MED [python-reviewer(chunk 1)+ python-reviewer(chunk 3)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Must Fix | `auto-fix` | 加一個「首次券商快照落地前不套用」旗標即可,且真錢面板可點到幻影列 |
| F-03 | 反手翻倉(賣量 > 原部位但 < 兩倍)沿用舊方向均價,與 docstring 規則相反(`copycat/capital/store.py`) | MED [python-reviewer(chunk 1)+ python-reviewer(chunk 3)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Should Fix | `auto-fix` | 一行判號改法 + 一條測試;錯值只存活到券商鏈落地 |
| F-04 | contract_from_fill 對除權息調整碼 / 未白名單選擇權 / 月碼不合會捏出錯契約碼,不是 None(`copycat/capital/mapping.py`) | MED [python-reviewer(chunk 1)+ python-reviewer(chunk 3 ×2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Should Fix | `auto-fix` | 守門收成等值比對一行解決三個樣態;寧缺勿錯是函式自己宣告的原則 |
| F-05 | 指數疊線沒有域外守門:無漲跌停(對稱域 ±1.1%)時線畫到圖外、標籤消失(`frontend/src/components/stock/StockIntradayChart.tsx`) | MED [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Should Fix | `auto-fix` | 在 buildIndexOverlayLines 以 g.yDomain 剔域外點,與 overlayLines 同一把尺 |
| F-06 | 指數 toggle 開著時,每則指數推播讓每張卡各重跑一次同一份 Object.entries + sort(`frontend/src/components/stock/GroupGridView.tsx`) | MED [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Should Fix | `auto-fix` | 序列層折一次(窗內排序列)再給卡片只做 toY,改動小 |
| F-07 | probe 收工序缺 LOGOUT、UNSUB / listener 收尾不在 finally,中途拋錯會留下 60 s 後 reap 的殭屍 session(`spikes/corr_legs_probe.py`) | MED [python-reviewer(chunk 3)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Should Fix | `auto-fix` | 照 backfill_tc4.py 既有寫法搬進 finally 即可;離線重跑仍會影響 prod TC4 |
| F-08 | TWS 閘時鐘表收盤側沒夾到分鐘精度(_TRADING_END 改到 13:45 仍全綠)(`tests/live/test_corr_source.py`) | MED [python-reviewer(chunk 4)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 補一列 (13, 36, False) 即可 |
| F-09 | 指數疊線與右緣「加權 +0.35%」標籤不看 IndexSeries.stale(`frontend/src/components/stock/StockIntradayChart.tsx`) | LOW [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 既有三個指數讀者都拿 stale 當閘;末點標籤加註即可 |
| F-10 | emittedMinRef 在 onHoverMinute 由 NOOP 切回真回呼時不重置,同一分鐘內不再補發(`frontend/src/components/stock/StockIntradayChart.tsx`) | LOW [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 鍵盤切 toggle + 滑鼠停同分鐘才觸發;比對 callback identity 一行修 |
| F-11 | NOOP_HOVER 插在 GRID_TOGGLES 的 JSDoc 與宣告之間,說明掛錯符號且「五鈕」已過時(`frontend/src/components/stock/GroupGridView.tsx`) | LOW [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 搬一行 + 改一個字 |
| F-12 | toggle 列 5→8 顆,窄視窗可能換行成兩列 chrome,與同段「只有一列」的註解相衝(`frontend/src/components/stock/GroupGridView.tsx`) | LOW [typescript-reviewer(chunk 2)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `ask-user` | 要不要收成下拉是版面取捨,先在 prod build 窄寬度目視 |
| F-13 | `except zmq.ZMQError: continue` 把非 timeout 錯誤一起吞掉,socket 壞掉會被讀成「零推播」(`spikes/corr_legs_probe.py`) | LOW [python-reviewer(chunk 3)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 改抓 zmq.Again 一行 |
| F-14 | 測試名宣稱 six-digit,但 `return s or None` 的實作也會綠(`tests/capital/test_reply.py`) | LOW [python-reviewer(chunk 3)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 補兩行反例 |
| F-15 | loop 以真實 sleep 走 ~1 s,3 s 預算只剩 ~3x 餘裕(`tests/capital/test_fill_latency.py`) | LOW [python-reviewer(chunk 3)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | RTT 降到 0.02 不損任何斷言 |
| F-16 | xw 恆為 SPOT_WINDOW(x 斷言與實作同式),NaN ref 閘未釘(`frontend/src/lib/index-overlay-lines.test.ts`) | LOW [python-reviewer(chunk 3)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 補 STKFUT_WINDOW 一條與 NaN 兩條 |
| F-17 | minuteOfKey 與 index-accum-adapter 的 private minuteOf 重複,且「同判」宣稱不成立(`frontend/src/lib/index-overlay-lines.ts`) | LOW [python-reviewer(chunk 3)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 把 adapter 的 minuteOf export 共用 |
| F-18 | 調色盤 parity 只驗 STROKES 且 CSS token 只比個數,不比序位(`tests/test_corr_config.py`) | LOW [python-reviewer(chunk 4)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 前端 river-colors.test.ts 已釘三組與逐 token;Python 側改 set 包含即可 |
| F-19 | 函式內重複 import 遮蔽模組層同名 import;`import re` 與 `import json` 被空行拆開(`tests/test_corr_config.py`) | LOW [python-reviewer(chunk 4)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 刪三行、併一組 |
| F-20 | 11 腿 key 字面集合在 4 處複製,加第 12 腿要改 5 個地方(`tests/server/test_river_routes.py`) | LOW [python-reviewer(chunk 4)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `ask-user` | 改由 load_config 導出會弱化「逐字契約」語意,要 user 拍板 |
| F-21 | F5 spec 的證券套用條件與實作不符(零股 → cash、SEC_MARKETS)(`.claude/feat/chart-ux-batch-0826/spec.md`) | LOW [python-reviewer(chunk 1)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 改 spec 一行 |
| F-22 | 測試把「corr 自訂 2330」鎖成契約,卻無任何 seam 覆蓋兩引擎同持該 symbol 的互殺路徑(`tests/server/test_corr_routes.py`) | MED [python-reviewer(chunk 4)] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 隨 F-01 修法一起改:改鎖「TWS 腿與個股引擎同一把窗」 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: d7a70a7eb1992f6ec6c2 action=auto-fix
F-02 finding_uid: 2f1223906165ab87c19c action=auto-fix
F-03 finding_uid: d41dd383e13b08de36ed action=auto-fix
F-04 finding_uid: bdad827656895a0a922d action=auto-fix
F-05 finding_uid: 70833c6a00ca42bfb713 action=auto-fix
F-06 finding_uid: 39d7b54e597b626d5008 action=auto-fix
F-07 finding_uid: d2fdcf83a714a45b79cc action=auto-fix
F-08 finding_uid: 040fc556783e3bb3172e action=auto-fix
F-09 finding_uid: e538ae76d150d91846e5 action=auto-fix
F-10 finding_uid: bac4cd5986842a0c99c6 action=auto-fix
F-11 finding_uid: c3c6b0e277e9c2ba4b60 action=auto-fix
F-12 finding_uid: d9d041c9b458f04b9653 action=ask-user
F-13 finding_uid: 204d31fb3d0c284d1fb8 action=auto-fix
F-14 finding_uid: a06329003c0014f5cd52 action=auto-fix
F-15 finding_uid: 60d815de601cd9a9ab7d action=auto-fix
F-16 finding_uid: 2f11c55e31ce520ec3da action=auto-fix
F-17 finding_uid: fc3e687488cb9348df21 action=auto-fix
F-18 finding_uid: 5f915b0dde5612fe3cf8 action=auto-fix
F-19 finding_uid: 46eb9627a116589c7ec0 action=auto-fix
F-20 finding_uid: 3c0bb27414fd48d31534 action=ask-user
F-21 finding_uid: c5cf5ec3f08e78a3d39d action=auto-fix
F-22 finding_uid: 55031c0ea19d0e9c6331 action=auto-fix

### Inline Comments per Finding（直接複製貼到 PR review）

#### F-01 台積電腿跟個股引擎訂同一個 symbol、不同 key,任一邊退訂會把上游 2330 整個拔掉

**File**: `configs/correlation.json`
**Line**: 69

**Comment**:
```
corr 這條腿用全天窗訂 TC.S.TWS.2330,個股引擎用日盤窗訂同一個 symbol → 兩把不同的 refcount key。
tc4-market-facts (b) 講的是反方向:上游 feed 以 symbol 為單位,**任一把 key 歸零 → 整個 symbol 退訂**,
另一把 key 還 >0 但再也收不到推播(只能等各自的自癒)。
自選把 2330 拿掉 / rollover 換窗 → corr 的台積電腿靜默;corr 收工或自癒 UNSUB → 個股頁 2330 靜默。零錯誤訊號。
spec 那句「key 不同,退訂不互殺」讀反了,base 腿 TXF 走 futures_engine 就是為了避這個。

最省事的改法:corr_source._rt_window 對 TC.S.TWS. 前綴回 stock_window(當日),與個股引擎同一把 key ——
兩邊各持一份 count 2→1,永遠不會歸零;順手把 spec §F4 那句改掉。
```

#### F-02 開機 backlog 重播會把「今日成交淨額」當部位疊在空集合上,出現可點平倉的幻影列

**File**: `copycat/capital/store.py`
**Line**: 163

**Comment**:
```
store.py 開頭自己寫:重啟後靠 ConnectByID 的當日 backlog 重播重建委託。
F5 之後 apply_reply(D) 無條件套進 _positions,而開機時 _positions 是空的 →
昨日庫存 10 張、今天賣 3 張的檔,重播完會得到 qty=-3 的現股「空單」,每筆重播還各推一次 capital_position。
券商鏈落地才蓋掉;空窗至少 = 0.5 s debounce + 三段回查往返,GetRealBalance 回 1019 時 `_mark_balance_dirty(1.0)`(client.py:511)每輪再加 1 s,期間 position_for 回的是幻影列、平倉按得下去。
同一條:clear_orders() 清 _orders(含 applied_qty)但部位不動 → 日後重連重播會把同批 D 再套一次。

改法:store 加 _positions_seeded(第一次 set_positions 才 True),未 seeded 前 D 只累計不套;
clear_orders 順手把 seeded 清掉。補兩條測試:重播不產生幻影列、clear → 重播不翻倍。
```

#### F-03 反手翻倉(賣量 > 原部位但 < 兩倍)沿用舊方向均價,與 docstring 規則相反

**File**: `copycat/capital/store.py`
**Line**: 251-252

**Comment**:
```
docstring 寫「減碼不動;反向翻倉 = 這張單均價」,但判別用的是幅度不是正負號:
持 +3 口 @900 → 賣 5 口 @800 → 得到 qty=-2、avg 900(應為 800);持 +1 賣 3 → 正確 800。同一條規則兩種答案。
set_positions 對券商列 avg None 會沿用 prev,OI 均價欄序又「prod 未實測」→ 錯的 900 可能續命。

改成看號:
    elif (new_qty > 0) == (prev.qty > 0): avg = prev.avg_price
    else: avg = fill_avg
補一條 +3 口賣 5 口 → -2 口 @800 的測試。
```

#### F-04 contract_from_fill 對除權息調整碼 / 未白名單選擇權 / 月碼不合會捏出錯契約碼,不是 None

**File**: `copycat/capital/mapping.py`
**Line**: 195-196

**Comment**:
```
守門只看 order_code.startswith(prod),而 exchange_product_of 對非白名單碼走「去尾兩碼 / 取開頭字母段」啟發式:
EE106 → EEF6(正解 EE1F6)、TE122000(未白名單選擇權,剝掉履約價後)→ TEF6 且 is_option_contract 判 False、
QEF06 配 idx33 202609 → QEFI6(兩碼月與 idx33 不合也照組)。三個都會以捏造的契約碼套進 fut 部位、可被點平倉,
真部位同時缺席,只有鏈落地那行「期貨部位鍵差異」看得到。

改成等值:
    if order_code != prod + ym[4:6]: return None
QEF06 / TXF06 照過,三個壞樣態全落 None 走回查鏈。test_mapping / test_store 各補 EE106、TE122000、月碼不合三例。
```

#### F-05 指數疊線沒有域外守門:無漲跌停(對稱域 ±1.1%)時線畫到圖外、標籤消失

**File**: `frontend/src/components/stock/StockIntradayChart.tsx`
**Line**: 546-547

**Comment**:
```
spec 的前提「個股 y 域 = ±10%,指數 ±2% 恆在域內」只在漲跌停已知時成立。
buildIntradayGeometry 走對稱域 fallback(upper/lower 任一 null)時半幅下限只有 ±1.1% →
+2% 的指數 toY 會回負 y,這個 <g> 沒 clipPath,polyline 貼著頂緣畫成一條假線、右緣 <text> 直接看不見。
同檔兄弟 overlay 都有守門(overlayLines 直接丟域外值、hlines 註解「超出 y 域不畫」)。
可及母體:上市未滿 5 日 / 無漲跌幅限制、TC4 meta 缺 UpperLimitPrice。

改法:buildIndexOverlayLines 多收 g.yDomain(IntradayGeometry 既有欄位,lib/stock-intraday-svg.ts:131 `yDomain: [number, number]` 毫元),域外點剔除(該點不畫、末點標籤取最後一個域內點),與 overlayLines 同規。
```

#### F-06 指數 toggle 開著時,每則指數推播讓每張卡各重跑一次同一份 Object.entries + sort

**File**: `frontend/src/components/stock/GroupGridView.tsx`
**Line**: 422

**Comment**:
```
useIndexStream 每則 WS 都 {...minutes} 新物件 → App 的 useMemo 換 identity → 每張卡的 idxLines useMemo 重算,
而 buildIndexOverlayLines 對每一檔都重跑與個股無關的 Object.entries 過濾 + sort:
271 分鐘 × 2 指數 × 50 卡 ≈ 27k 次走訪 + 100 次排序,每則指數推播一次。真正 per-card 的只有最後那步 toY。

改法:把「窗內、已排序的 (minute, p) 列 + ref」在序列層折一次(useMemo deps = 兩個 series + xw),
卡片只吃折好的列做 toY。
```

#### F-07 probe 收工序缺 LOGOUT、UNSUB / listener 收尾不在 finally,中途拋錯會留下 60 s 後 reap 的殭屍 session

**File**: `spikes/corr_legs_probe.py`
**Line**: 349-351

**Comment**:
```
tc4-market-facts「Disconnect 不等於登出」:沒送 LOGOUT 的 session 60 s 後被 reap,reap 時它獨持的 key 歸零 → 上游退訂整個 symbol。
本檔 finally 只有 Disconnect;UNSUB 迴圈、sock.close / ctx.term 都在 happy path,第 3/4 步一拋就全留著。
VX/CL/GC 現在已是 prod 腿,離線重跑這支 probe(:8721 沒在跑時 guard 不擋)會留下殭屍 session 打斷 prod 同 symbol。

照 copycat/data/backfill_tc4.py:161-166 的寫法:UNSUB 全部 → 關 listener → api.Logout(session) → Disconnect,全部進 finally、各自 best-effort try/except。
```

#### F-08 TWS 閘時鐘表收盤側沒夾到分鐘精度(_TRADING_END 改到 13:45 仍全綠)

**File**: `tests/live/test_corr_source.py`
**Line**: 196-197

**Comment**:
```
開盤側夾得很準((8,29,False)/(8,30,True)),收盤側只有 (13,35,True) 與 (14,0,False):任何 _TRADING_END ∈ [13:35, 14:00) 都過。
F4 存在的理由正是「現貨 13:30 vs 台期交 13:45 不是同一把尺」—— 哪天有人把 _TRADING_END 對齊期貨改成 13:45,失效樣態正是這條要防的,測試零訊號。
補一列 (13, 36, False),與開盤側對稱。
```

#### F-09 指數疊線與右緣「加權 +0.35%」標籤不看 IndexSeries.stale

**File**: `frontend/src/components/stock/StockIntradayChart.tsx`
**Line**: 1381

**Comment**:
```
IndexBar / MarketPane / FuturesPage 三個既有指數讀者都把 stale 當「這個數字不能用」的閘。
F1 的 available 只看 indexSeries !== null && ref !== null → index_engine 斷流後線停在最後一格、右緣標籤照印一個看起來是當下的 %,
跟「大盤真的平盤」畫面同形。歷史分鐘本身還是真的,所以只要末點標籤 stale 時加註「(中斷)」或反灰,不必整條不畫。
```

#### F-10 emittedMinRef 在 onHoverMinute 由 NOOP 切回真回呼時不重置,同一分鐘內不再補發

**File**: `frontend/src/components/stock/StockIntradayChart.tsx`
**Line**: 1038-1039

**Comment**:
```
emitHoverMinute 只比 emittedMinRef.current === min,不看這輪 onHoverMinute 是誰。
十字線關著時 onHoverMinute 是 NOOP_HOVER,但 ref 照樣被寫成當下分鐘;用鍵盤把十字線切回開、滑鼠還停在同一分鐘 →
後續 mousemove 全被相等比對早退,其他卡要等游標跨分鐘才出十字線。滑鼠操作時 onMouseLeave 會先歸零所以不常見。
修法:多記一個 lastCbRef,onHoverMinute identity 變了就把 emittedMinRef 歸 null(不用 useEffect)。
```

#### F-11 NOOP_HOVER 插在 GRID_TOGGLES 的 JSDoc 與宣告之間,說明掛錯符號且「五鈕」已過時

**File**: `frontend/src/components/stock/GroupGridView.tsx`
**Line**: 258-259

**Comment**:
```
原本那段「圖牆頂 toggle 列的五鈕(SC-2…)恆可按」是 GRID_TOGGLES 的 doc comment,NOOP_HOVER 插進中間後 IDE 會把它掛到 NOOP_HOVER 上,GRID_TOGGLES 變無說明;內容也過時(現在八顆)。
把 NOOP_HOVER 移到那段註解上面,「五鈕」改「八鈕」。
```

#### F-12 toggle 列 5→8 顆,窄視窗可能換行成兩列 chrome,與同段「只有一列」的註解相衝

**File**: `frontend/src/components/stock/GroupGridView.tsx`
**Line**: 370

**Comment**:
```
群組 pill 與 toggle 列共用 flex-wrap,toggle 容器 ml-auto shrink-0 → 寬度不足整塊換行;多 3 顆鈕把門檻推高,
而換行的代價正是同段註解點名的「兩列 chrome 吃掉卡片的高」(AD-7 卡高評估建立在單列上)。
先在 prod build 以分割畫面寬度看一次;真會換行再考慮三顆新鈕收成一顆下拉或縮短 label。
```

#### F-13 `except zmq.ZMQError: continue` 把非 timeout 錯誤一起吞掉,socket 壞掉會被讀成「零推播」

**File**: `spikes/corr_legs_probe.py`
**Line**: 282-283

**Comment**:
```
RCVTIMEO 到期(EAGAIN)跟 ETERM / ENOTSOCK 走同一條 continue,socket 進不可用狀態後迴圈空轉到 listen_secs 用盡、push_counts 全 0 ——
跟「這支 symbol 真的沒 tick」同形,而那正是這支 probe 唯一要判的結論。改 `except zmq.Again: continue`,其餘 re-raise 或至少印一行。
```

#### F-14 測試名宣稱 six-digit,但 `return s or None` 的實作也會綠

**File**: `tests/capital/test_reply.py`
**Line**: 143-144

**Comment**:
```
只覆蓋「正常值」與「空字串」,_ym_or_none 的 len==6 / isdigit 兩個守門都沒反例 —— 實作退化成 `_at(arr,33) or None` 照樣綠。
補 arr[33]="20260A" 與 "2026" 各一行斷言 None。
```

#### F-15 loop 以真實 sleep 走 ~1 s,3 s 預算只剩 ~3x 餘裕

**File**: `tests/capital/test_fill_latency.py`
**Line**: 19

**Comment**:
```
因果順序斷言本身對(舊碼下第一則 capital_position 來自 _finalize_positions,com.sent 已有 get_real_balance → 紅),_run_chain 也走 prod 的 _pump_once。
留的是體質:test 2 要真睡完 0.5 s debounce + 3×0.15,Windows sleep 粒度 ~15 ms,3 s 預算只剩約 3x,每跑一次 suite 固定 +1 s。
_SIM_RTT_S 降到 0.02 不損失任何斷言(150 ms 只是敘事)。
```

#### F-16 xw 恆為 SPOT_WINDOW(x 斷言與實作同式),NaN ref 閘未釘

**File**: `frontend/src/lib/index-overlay-lines.test.ts`
**Line**: 29

**Comment**:
```
五條 case 全傳 SPOT_WINDOW,唯一的 x 斷言又用 minuteToX(..., SPOT_WINDOW) 自證 —— 把實作內的 xw 硬編成 SPOT_WINDOW 整檔照樣綠;
而個股期分時圖(stkfut)確實會拿 STKFUT_WINDOW 疊指數線(加權/櫃買鈕只擋 futures、不擋 stkfut)。
實作刻意寫 `!(ref !== null && ref > 0)` 防 NaN,但沒有 case 傳 NaN(search-proof:`grep -c NaN frontend/src/lib/index-overlay-lines.test.ts` = 0),改成 `ref === null || ref <= 0` 仍全綠。
補:同分鐘在 STKFUT_WINDOW 下 x 必須不同;stockRefMilli / s.ref 各一個 NaN case。
```

#### F-17 minuteOfKey 與 index-accum-adapter 的 private minuteOf 重複,且「同判」宣稱不成立

**File**: `frontend/src/lib/index-overlay-lines.ts`
**Line**: 36-37

**Comment**:
```
index-accum-adapter.ts:67 的 minuteOf 對同一份 IndexSeries.minutes 做同一件事,只是沒 export;新版註解寫「同判」但判準不同(adapter 用 /^\d{4}$/,新版 Number(slice) 會接受 "09.0" / "09+1")。
後端 %H%M 不會產生這種鍵,無實害,但兩份解析判準不同正是之後漂掉沒人發現的形狀;把 adapter 的 minuteOf export 出來共用(index-chart-svg.ts:24 toX 是第三份)。
```

#### F-18 調色盤 parity 只驗 STROKES 且 CSS token 只比個數,不比序位

**File**: `tests/test_corr_config.py`
**Line**: 184-185

**Comment**:
```
只 findall stroke-river-N 驗連續,FILLS / TEXTS 沒讀;CSS 只比 len(tokens) >= len(strokes) —— 少了 --color-river-8 多了 --color-river-12 個數相等照過。
實際風險已被前端 river-colors.test.ts 堵住(三組長度 + 序位 + 逐 token + 色值兩兩不同),Python 這半是弱化版重複。
二擇一:刪掉 CSS 那兩行(只留「色數 >= 腿數」這個唯一跨語言事實),或改 set(tokens) >= set(strokes)。
```

#### F-19 函式內重複 import 遮蔽模組層同名 import;`import re` 與 `import json` 被空行拆開

**File**: `tests/test_corr_config.py`
**Line**: 175-177

**Comment**:
```
Path、DEFAULT_CONFIG / load_config 模組層已 import,函式內又 import 一次只是遮蔽同一個物件。第 5-8 行 import re 與 import json 中間多一個空行把 stdlib 拆成兩組。
刪掉函式內三行,import re 併進 json 那組。
```

#### F-20 11 腿 key 字面集合在 4 處複製,加第 12 腿要改 5 個地方

**File**: `tests/server/test_river_routes.py`
**Line**: 36-37

**Comment**:
```
同一組 11 個 key 字面出現在 test_river_routes.py 兩處、test_corr_routes.py 兩處,加 test_corr_config 的 _EXPECTED_LEGS。
corr_routes 自己的 docstring 說「逐字契約鎖在 test_corr_config,這裡鎖 route 有把設定檔原封吐出來」——那句正確的寫法是從 load_config(CONFIG_PATH) 導出(create_app 走的就是 repo 設定檔,不是同義反覆)。
要不要改由設定檔導出、逐字值只留 _EXPECTED_LEGS 一處,你拍。
```

#### F-21 F5 spec 的證券套用條件與實作不符(零股 → cash、SEC_MARKETS)

**File**: `.claude/feat/chart-ux-batch-0826/spec.md`
**Line**: 110

**Comment**:
```
spec 寫「market ∈ SEC_MARKETS … 零股→cash」,實作是 _SEC_LOT_MARKETS = {TS,TA,TP}(零股 TL/TC 整個排除)且 _FILL_KIND 沒有「零股」。
code 是對的(零股 //1000 會吃成 0),錯的是 spec —— round 1 同步了 idx33 / 閘窗兩處,這處漏改。改 spec 一行。
```

#### F-22 測試把「corr 自訂 2330」鎖成契約,卻無任何 seam 覆蓋兩引擎同持該 symbol 的互殺路徑

**File**: `tests/server/test_corr_routes.py`
**Line**: 82-83

**Comment**:
```
這兩行把 corr 自己訂 TC.S.TWS.2330 定為契約,但 tc4-market-facts (b) 說任一把 key 歸零上游整個 symbol 退訂;
grep 全 tests 沒有一條讓 corr 與 stock 兩源同持 2330。F-01 修成同一把窗之後,這裡改成鎖「TWS 腿的訂閱窗 == stock_window(當日)」,那才是真正防互殺的 seam。
```

### Opus 原始 findings (first-pass, context-aware)

- **F-01** [python-reviewer(chunk 1)+ python-reviewer(chunk 4)] HIGH `configs/correlation.json:69-69`(anchored: exact;baseline: Design-4)— 台積電腿跟個股引擎訂同一個 symbol、不同 key,任一邊退訂會把上游 2330 整個拔掉。corr `all_day_window()`(…00/…23)vs stock_engine `stock_window()`(…00/…06)= 同 symbol 兩把 key;`stock_engine._release()` 最後一個 owner UNSUB 即歸零;probe 母體無 TWS。chunk 4 另指 `test_corr_routes.py:82-83` 把此訂閱鎖成契約卻無互殺 seam。
- **F-02** [python-reviewer(chunk 1)+ python-reviewer(chunk 3)] MEDIUM `copycat/capital/store.py:163-163`(anchored: exact;baseline: none)— 開機 backlog 重播會把「今日成交淨額」當部位疊在空集合上,出現可點平倉的幻影列。`apply_reply(D)` → `_apply_fill_locked` 無條件;`set_positions` 對 `avg_price is None` 沿用 prev;OI 欄序 prod 未實測;fut 平倉乘數閘失敗只 warning(client.py:976-987)。chunk 3:`clear_orders()` docstring 仍寫「部位不動」,重播 double-apply 未釘。
- **F-03** [python-reviewer(chunk 1)+ python-reviewer(chunk 3)] MEDIUM `copycat/capital/store.py:251-252`(anchored: exact;baseline: none)— 反手翻倉(賣量 > 原部位但 < 兩倍)沿用舊方向均價,與 docstring 規則相反。chunk 1 實跑重現 `QEFF6` +3@900 賣 5@800 → `qty=-2, avg_price=900.0`。chunk 3 指出 test_store 未釘翻倉分支。
- **F-04** [python-reviewer(chunk 1)+ python-reviewer(chunk 3 ×2)] MEDIUM `copycat/capital/mapping.py:195-196`(anchored: exact;baseline: Design-4)— contract_from_fill 對除權息調整碼 / 未白名單選擇權 / 月碼不合會捏出錯契約碼,不是 None。chunk 1 實跑 `contract_from_fill("EE106","202606")`→`EEF6`;chunk 3 實跑 `TE122000`→`TEF6` 且 `is_option_contract` False(履約價被剝掉,docstring 保證失效);chunk 3 另指 idx8 兩碼月與 idx33 不交叉檢查。
- **F-05** [typescript-reviewer(chunk 2)] MEDIUM `frontend/src/components/stock/StockIntradayChart.tsx:546-547`(anchored: exact;baseline: Quality-4)— 指數疊線沒有域外守門:無漲跌停(對稱域 ±1.1%)時線畫到圖外、標籤消失。`buildIntradayGeometry` lib/stock-intraday-svg.ts:366-383 對稱域半幅 `max(hi-ref, ref-lo, ref*0.01)*1.1`;`overlayLines` :537-539 丟域外值;該 `<g>` 無 clipPath。
- **F-06** [typescript-reviewer(chunk 2)] MEDIUM `frontend/src/components/stock/GroupGridView.tsx:422-422`(anchored: exact;baseline: Efficiency-1)— 指數 toggle 開著時,每則指數推播讓每張卡各重跑一次同一份 Object.entries + sort。鏈:`toSeries`(useIndexStream.ts:60-70)→ App useMemo → GroupCard memo 全數比不過 → `idxLines` useMemo(StockIntradayChart.tsx:1154-1167)→ `buildIndexOverlayLines` 排序。
- **F-07** [python-reviewer(chunk 3)] MEDIUM `spikes/corr_legs_probe.py:349-351`(anchored: exact;baseline: Reuse-1)— probe 收工序缺 LOGOUT、UNSUB / listener 收尾不在 finally,中途拋錯會留下 60 s 後 reap 的殭屍 session。skill 條目 + `backfill_tc4.py` search-proof;happy-path 收尾在 :326-329。
- **F-08** [python-reviewer(chunk 4)] MEDIUM `tests/live/test_corr_source.py:196-197`(anchored: exact;baseline: none)— TWS 閘時鐘表收盤側沒夾到分鐘精度(_TRADING_END 改到 13:45 仍全綠)。實作值 `_TRADING_END = time(13, 35)`(stock_source.py:32-33)。
- **F-09** [typescript-reviewer(chunk 2)] LOW `frontend/src/components/stock/StockIntradayChart.tsx:1381-1381`(anchored: ambiguous;baseline: Quality-4)— 指數疊線與右緣「加權 +0.35%」標籤不看 IndexSeries.stale。search-proof:`grep -rn "\.stale" frontend/src` 命中 IndexBar.tsx:16,41 / MarketPane.tsx:525 / FuturesPage.tsx:66。
- **F-10** [typescript-reviewer(chunk 2)] LOW `frontend/src/components/stock/StockIntradayChart.tsx:1038-1039`(anchored: exact;baseline: none)— emittedMinRef 在 onHoverMinute 由 NOOP 切回真回呼時不重置,同一分鐘內不再補發。可達路徑:GroupGridView.tsx:425 `NOOP_HOVER`;synchover 測試未涵蓋 toggle 切換後補發。
- **F-11** [typescript-reviewer(chunk 2)] LOW `frontend/src/components/stock/GroupGridView.tsx:258-259`(anchored: exact;baseline: Quality-8)— NOOP_HOVER 插在 GRID_TOGGLES 的 JSDoc 與宣告之間,說明掛錯符號且「五鈕」已過時。測試標題已改「八鈕」,註解未同步。
- **F-12** [typescript-reviewer(chunk 2)] LOW `frontend/src/components/stock/GroupGridView.tsx:370-370`(anchored: exact;baseline: none)— toggle 列 5→8 顆,窄視窗可能換行成兩列 chrome,與同段「只有一列」的註解相衝。外層 `flex flex-wrap`(:351);專案已有 `@[1050px]` 兩欄佈局先例。
- **F-13** [python-reviewer(chunk 3)] LOW `spikes/corr_legs_probe.py:282-283`(anchored: exact;baseline: none)— `except zmq.ZMQError: continue` 把非 timeout 錯誤一起吞掉,socket 壞掉會被讀成「零推播」。
- **F-14** [python-reviewer(chunk 3)] LOW `tests/capital/test_reply.py:143-144`(anchored: exact;baseline: none)— 測試名宣稱 six-digit,但 `return s or None` 的實作也會綠。
- **F-15** [python-reviewer(chunk 3)] LOW `tests/capital/test_fill_latency.py:19-19`(anchored: exact;baseline: Efficiency-1)— loop 以真實 sleep 走 ~1 s,3 s 預算只剩 ~3x 餘裕。
- **F-16** [python-reviewer(chunk 3)] LOW `frontend/src/lib/index-overlay-lines.test.ts:29-29`(anchored: exact;baseline: none)— xw 恆為 SPOT_WINDOW(x 斷言與實作同式),NaN ref 閘未釘。search-proof:`grep -c NaN index-overlay-lines.test.ts` = 0(worktree);stkfut 路徑 StockIntradayChart.tsx:1010 `xw = xWindow ?? (stkfut ? STKFUT_WINDOW : SPOT_WINDOW)`。
- **F-17** [python-reviewer(chunk 3)] LOW `frontend/src/lib/index-overlay-lines.ts:36-37`(anchored: exact;baseline: Reuse-2)— minuteOfKey 與 index-accum-adapter 的 private minuteOf 重複,且「同判」宣稱不成立。
- **F-18** [python-reviewer(chunk 4)] LOW `tests/test_corr_config.py:184-185`(anchored: exact;baseline: Quality-3)— 調色盤 parity 只驗 STROKES 且 CSS token 只比個數,不比序位。
- **F-19** [python-reviewer(chunk 4)] LOW `tests/test_corr_config.py:175-177`(anchored: exact;baseline: Reuse-3)— 函式內重複 import 遮蔽模組層同名 import;`import re` 與 `import json` 被空行拆開。
- **F-20** [python-reviewer(chunk 4)] LOW `tests/server/test_river_routes.py:36-37`(anchored: exact;baseline: Quality-3)— 11 腿 key 字面集合在 4 處複製,加第 12 腿要改 5 個地方。
- **F-21** [python-reviewer(chunk 1)] LOW `.claude/feat/chart-ux-batch-0826/spec.md:110-110`(anchored: exact;baseline: none)— F5 spec 的證券套用條件與實作不符(零股 → cash、SEC_MARKETS)。
- **F-22** [python-reviewer(chunk 4)] MEDIUM `tests/server/test_corr_routes.py:82-83`(anchored: exact;baseline: none)— 測試把「corr 自訂 2330」鎖成契約,卻無任何 seam 覆蓋兩引擎同持該 symbol 的互殺路徑。`grep -rn "TC.S.TWS.2330" tests/` 20 處無雙源;`grep -rln "refcount|SumSubCount" tests/` 10 檔無此組合。

原始 25 條 → 合併 3 組同根因後 22 條:F-01 ← chunk 1 HIGH(correlation.json)+ chunk 4 MEDIUM(test_corr_routes,另保留為測試面 F-22);F-03 ← chunk 1 MEDIUM(store 翻倉)+ chunk 3 LOW(test_store 翻倉未釘 a 半);F-02 ← chunk 1 MEDIUM(backlog 重播)+ chunk 3 LOW(clear_orders 重播 b 半);F-04 ← chunk 1 MEDIUM(EE106)+ chunk 3 MEDIUM(TE122000)+ chunk 3 LOW(月碼不合)。合併時取較高 severity;所有來源 tag 保留。

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查(Step 4.1 未執行)。

### Codex 對 Opus 的複查結果(對稱化 4.2)

Codex 複查 Opus 失敗 — 本輪 Step 4.2 輸入 findings 無 cross-axis 證據(本機無 codex CLI,batch 未起跑);所有送入 Step 4.2 的 findings 視同 INCONCLUSIVE。改以 Step 4.3b 判斷式複查逐條處理(主 agent;結果在下表「備註」欄,不冒充 cross-axis 證據):

| Opus # | Opus reviewer | Opus title | Verdict | 原始 → 校正 severity | Codex evidence | 備註(4.3b) |
| --- | --- | --- | --- | --- | --- | --- |
| F-01 | python-reviewer(chunk 1)+ python-reviewer(chunk 4) | 台積電腿跟個股引擎訂同一個 symbol、不同 key,任一邊退訂會把上游 2330 整個拔掉 | INCONCLUSIVE(4.2 N-A) | HIGH→HIGH | — | lone(axis 內兩支 reviewer 獨立命中,他軸未啟動);4.3b:機制為 skill (b) 白紙黑字 + code 路徑逐行追到,CONFIRMED 等級證據,不降級。6d-3:重現 = 自選移除 2330 後看 corr 台積電腿;不修 = prod runtime 靜默失效 → Must。 |
| F-02 | python-reviewer(chunk 1)+ python-reviewer(chunk 3) | 開機 backlog 重播會把「今日成交淨額」當部位疊在空集合上,出現可點平倉的幻影列 | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | lone(他軸未啟動);4.3b:重播路徑由 store.py:8-12 自述 + client ConnectByID 流程確認,機制可達;6d-3:重現 = 盤中有成交後重啟 server,部位面板在券商鏈落地前(≥ 0.5 s debounce + 三段往返,1019 退避每輪 +1 s,client.py:511)顯示幻影列且可按平倉;不修 = prod 重啟後真錢面板誤按風險 → Must(Must 理由只依 code 可讀的下限,不依未實測的上限)。 |
| F-03 | python-reviewer(chunk 1)+ python-reviewer(chunk 3) | 反手翻倉(賣量 > 原部位但 < 兩倍)沿用舊方向均價,與 docstring 規則相反 | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | lone;4.3b:實跑重現,CONFIRMED 等級;錯均價只在鏈落地前 ~1 s 可見且非幻影列 → Should。 |
| F-04 | python-reviewer(chunk 1)+ python-reviewer(chunk 3 ×2) | contract_from_fill 對除權息調整碼 / 未白名單選擇權 / 月碼不合會捏出錯契約碼,不是 None | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | lone;4.3b:三支獨立實跑重現;EE1/CD1 調整碼是 `is_option_contract` docstring 點名的既有類別 → Should(非 Must:期貨成交後鏈落地即覆蓋)。 |
| F-05 | typescript-reviewer(chunk 2) | 指數疊線沒有域外守門:無漲跌停(對稱域 ±1.1%)時線畫到圖外、標籤消失 | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | lone;4.3b:機制逐段追到(對稱域公式 + 無 clip);他軸未啟動。6d-3 重現 = 無漲跌停標的開指數線 → Should。 |
| F-06 | typescript-reviewer(chunk 2) | 指數 toggle 開著時,每則指數推播讓每張卡各重跑一次同一份 Object.entries + sort | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | lone;4.3b:掉幀類、無錯誤訊號;他軸未啟動。非 release-blocking → Should。 |
| F-07 | python-reviewer(chunk 3) | probe 收工序缺 LOGOUT、UNSUB / listener 收尾不在 finally,中途拋錯會留下 60 s 後 reap 的殭屍 session | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | lone;4.3b:skill 條目為第一手事實;spikes 慣例不豁免收工序 → Should。 |
| F-08 | python-reviewer(chunk 4) | TWS 閘時鐘表收盤側沒夾到分鐘精度(_TRADING_END 改到 13:45 仍全綠) | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | lone;測試強度,不阻擋發布 → Nice。 |
| F-09 | typescript-reviewer(chunk 2) | 指數疊線與右緣「加權 +0.35%」標籤不看 IndexSeries.stale | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;非 release-blocking → Nice。 |
| F-10 | typescript-reviewer(chunk 2) | emittedMinRef 在 onHoverMinute 由 NOOP 切回真回呼時不重置,同一分鐘內不再補發 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;邊角操作 → Nice。 |
| F-11 | typescript-reviewer(chunk 2) | NOOP_HOVER 插在 GRID_TOGGLES 的 JSDoc 與宣告之間,說明掛錯符號且「五鈕」已過時 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;純註解 → Nice。 |
| F-12 | typescript-reviewer(chunk 2) | toggle 列 5→8 顆,窄視窗可能換行成兩列 chrome,與同段「只有一列」的註解相衝 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;版面觀感,需 user 過目 → Nice / ask-user。 |
| F-13 | python-reviewer(chunk 3) | `except zmq.ZMQError: continue` 把非 timeout 錯誤一起吞掉,socket 壞掉會被讀成「零推播」 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;probe 腳本 → Nice。 |
| F-14 | python-reviewer(chunk 3) | 測試名宣稱 six-digit,但 `return s or None` 的實作也會綠 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;測試強度 → Nice。 |
| F-15 | python-reviewer(chunk 3) | loop 以真實 sleep 走 ~1 s,3 s 預算只剩 ~3x 餘裕 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;測試體質 → Nice。 |
| F-16 | python-reviewer(chunk 3) | xw 恆為 SPOT_WINDOW(x 斷言與實作同式),NaN ref 閘未釘 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;測試強度 → Nice。 |
| F-17 | python-reviewer(chunk 3) | minuteOfKey 與 index-accum-adapter 的 private minuteOf 重複,且「同判」宣稱不成立 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;Reuse → Nice。 |
| F-18 | python-reviewer(chunk 4) | 調色盤 parity 只驗 STROKES 且 CSS token 只比個數,不比序位 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;測試重複 → Nice。 |
| F-19 | python-reviewer(chunk 4) | 函式內重複 import 遮蔽模組層同名 import;`import re` 與 `import json` 被空行拆開 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;風格 → Nice。 |
| F-20 | python-reviewer(chunk 4) | 11 腿 key 字面集合在 4 處複製,加第 12 腿要改 5 個地方 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;測試 DRY vs 逐字契約取捨 → ask-user。 |
| F-21 | python-reviewer(chunk 1) | F5 spec 的證券套用條件與實作不符(零股 → cash、SEC_MARKETS) | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | lone;文件一致性 → Nice。 |
| F-22 | python-reviewer(chunk 4) | 測試把「corr 自訂 2330」鎖成契約,卻無任何 seam 覆蓋兩引擎同持該 symbol 的互殺路徑 | INCONCLUSIVE(4.2 N-A) | MEDIUM→MEDIUM | — | 與 F-01 同根因的測試面;lone;隨 F-01 一起處理 → Nice(測試),不重複計 Must。 |

## Action Items

**Severity calibration**:6c(移除既有防護類)本 PR 無此類 finding → 免;6d-1 hedge:F-02 的「1019 退避可到數十秒」為機制推論(退避邏輯 client.py 可讀),其餘斷言皆有實跑或 file:line;6d-3 Must 雙半條件逐條寫在備註;6d-2 由 4.3b 取代。Provenance cap N-A。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix(合併前必修)

- F-01 台積電腿跟個股引擎訂同一個 symbol、不同 key,任一邊退訂會把上游 2330 整個拔掉 —— 重現:重現 = 自選移除 2330 後看 corr 台積電腿;不修 = prod runtime 靜默失效 → Must。
- F-02 開機 backlog 重播會把「今日成交淨額」當部位疊在空集合上,出現可點平倉的幻影列 —— 重現:重現 = 盤中有成交後重啟 server,部位面板在券商鏈落地前(≥ 0.5 s debounce + 三段往返,1019 退避每輪 +1 s,client.py:511)顯示幻影列且可按平倉;不修 = prod 重啟後真錢面板誤按風險 → Must(Must 理由只依 code 可讀的下限,不依未實測的上限)。

### Should Fix(強烈建議)

- F-03 反手翻倉(賣量 > 原部位但 < 兩倍)沿用舊方向均價,與 docstring 規則相反
- F-04 contract_from_fill 對除權息調整碼 / 未白名單選擇權 / 月碼不合會捏出錯契約碼,不是 None
- F-05 指數疊線沒有域外守門:無漲跌停(對稱域 ±1.1%)時線畫到圖外、標籤消失
- F-06 指數 toggle 開著時,每則指數推播讓每張卡各重跑一次同一份 Object.entries + sort
- F-07 probe 收工序缺 LOGOUT、UNSUB / listener 收尾不在 finally,中途拋錯會留下 60 s 後 reap 的殭屍 session

### Nice to Have(可選優化)

- F-08 TWS 閘時鐘表收盤側沒夾到分鐘精度(_TRADING_END 改到 13:45 仍全綠)
- F-09 指數疊線與右緣「加權 +0.35%」標籤不看 IndexSeries.stale
- F-10 emittedMinRef 在 onHoverMinute 由 NOOP 切回真回呼時不重置,同一分鐘內不再補發
- F-11 NOOP_HOVER 插在 GRID_TOGGLES 的 JSDoc 與宣告之間,說明掛錯符號且「五鈕」已過時
- F-12 toggle 列 5→8 顆,窄視窗可能換行成兩列 chrome,與同段「只有一列」的註解相衝
- F-13 `except zmq.ZMQError: continue` 把非 timeout 錯誤一起吞掉,socket 壞掉會被讀成「零推播」
- F-14 測試名宣稱 six-digit,但 `return s or None` 的實作也會綠
- F-15 loop 以真實 sleep 走 ~1 s,3 s 預算只剩 ~3x 餘裕
- F-16 xw 恆為 SPOT_WINDOW(x 斷言與實作同式),NaN ref 閘未釘
- F-17 minuteOfKey 與 index-accum-adapter 的 private minuteOf 重複,且「同判」宣稱不成立
- F-18 調色盤 parity 只驗 STROKES 且 CSS token 只比個數,不比序位
- F-19 函式內重複 import 遮蔽模組層同名 import;`import re` 與 `import json` 被空行拆開
- F-20 11 腿 key 字面集合在 4 處複製,加第 12 腿要改 5 個地方
- F-21 F5 spec 的證券套用條件與實作不符(零股 → cash、SEC_MARKETS)
- F-22 測試把「corr 自訂 2330」鎖成契約,卻無任何 seam 覆蓋兩引擎同持該 symbol 的互殺路徑

### 參考用(任一軸驗證為 REFUTED 或 OUT_OF_SCOPE)

無 —— 本輪無 REFUTED / OUT_OF_SCOPE(4.1 / 4.2 皆 N-A;4.3b 判斷式複查未推翻任何一條)。

## 審查工具比較 (qualitative)

- Opus(CC context-aware)視角:四支 reviewer 各自實跑 worktree python 重現(F-03 / F-04 三例)、逐行追 skill 事實與 code 路徑(F-01 / F-02 / F-05);跨檔缺失類命中率高。
- Codex 中性 / 對抗視角:N-A(本機未裝)。重疊率無法計算;4.1 分佈 N-A;4.2 分佈:INCONCLUSIVE 22 / 22(工具缺席,非 Opus over-flag 的訊號)。
- 對抗式第三軸增益:N-A。Gemini 軸增益:N-A。
- 本輪 lone finding = 22 / 22(所有他軸皆未啟動),故 4.3b 一律以「機制可達 + 第一手證據」判斷,不因他軸沉默降級;唯一 within-axis 雙命中為 F-01(chunk 1 與 chunk 4 獨立指向同一機制)。
- 與 in-repo two-axis round 1(`.claude/feat/chart-ux-batch-0826/code-review-round-1.json`)對照:本輪 22 條全部是 round 1 未抓到的新 finding(round 1 已收修的 17 條無一重報),其中 F-01 直接推翻 round 1 期間寫進 spec 的「不互殺」判斷。

## 沒做的部分(結案對帳)

- Codex 中性軸:FAIL / N-A —— 本機無 `codex` CLI,未起跑,零 finding;報告以 CC 軸為主。
- Codex 對抗軸:FAIL / N-A —— 同上。
- Gemini Flash 軸(永久軸):FAIL / N-A —— 本機無 `agy`,未起跑;Pro 軸未啟用亦無工具。
- Step 4.1:N-A —— 無非 CC finding。
- Step 4.2:FAIL → 全部 INCONCLUSIVE —— codex-companion batch 無法起跑;以 4.3b 主 agent 判斷式複查補位,**不冒充 cross-axis 證據**。
- Step 2.9 blast radius:N-A —— 無 `sem`,空輸出跳過。
- Step 2.65 C4:SKIPPED(C4_AUTHORITY_PATH_NOT_ALLOWED);另本機 permit 目錄 POSIX-only,即使路徑合法亦無法 dispatch。
- Step 2.96 / 2.98 提問:未問(/auto 無人值守 + 工具缺席),按預設記錄。
- 未驗證前提:F-02 空窗**上限**未實測(只有 code 可讀的下限 0.5 s + 三段往返與 1019 每輪 +1 s,client.py:511;Must 分級不依上限);F-06 效能數字(27k 次走訪)為算式推估未量測;F-12 換行門檻未在真寬度目視。三條均非 Must Fix 的支點。
- 前端 chunk reviewer 無法在 review worktree 跑 tsc / vitest(無 node_modules,read-only);自動化 gate 以 PR 分支 worktree 的 verification.md 為準(rebase 後 pytest 3083 / vitest 2799 / tsc / eslint 全綠)。
- Self-Verify:auditor(skill-verify-auditor,model=opus)回 R1/R2/R9/R10 PASS、R3/R5/R6/R7/R8 FAIL,但**缺 R4 行** → 格式錯誤,verdict 不採信,記 SKIPPED (agent error)、不重派。主 agent 依其指出的缺口修正:R3 補三檔 skipped 檔名與理由;R6 F-16 補 grep 證據;R7 F-02 的 Must 理由改為只依 code 可讀的空窗下限(移除未實測的『數十秒』);R8 F-05 補 `g.yDomain` file:line。R5 不適用(canonical record 是命令固定格式)。**未經第二次獨立稽查。**

