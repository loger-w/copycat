# PR #218 Code Review 比較報告 · SHA 8af45c42
**Report projection schema**: 1

**PR**: [loger-w/copycat#218](https://github.com/loger-w/copycat/pull/218)
**標題**: feat(frontend): 個股頁盤中即時末根 —— 分 K / 日 K 最後一根以逐筆成交即時更新(spec #214)
**作者**: loger-w
**分支**: `feat/live-last-bar` → `master`
**變更**: 13 檔案, +907 / -14
**審查日期**: 2026-09-08
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨;merge commit `16605b70`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `8af45c428d177695acd48a0b47667bcaa9086640`;destination repo id `R_kgDOTsITBg` + baseRefOid `410c0f1cbe7421b70c72456b2ecf5af6b2eb810d`;`input_binding: verified` —— `git fetch origin refs/pull/218/head` 取回的 commit = headRefOid 逐字相等,review worktree detached 於該 SHA,`git merge-base origin/master HEAD` = baseRefOid
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 SHA;分支已隨 `--delete-branch` 刪除,但 `refs/pull/218/head` 仍指 `8af45c42`,產報告前重抓 headRefOid 仍為它);`base_changed=true`(origin/master 自 `410c0f1c` 前進至 `16605b70`,內容 = 本 PR 自身 14 筆 rebase 後 commit,其後零新 commit);`review_context_changed=false`(審的是 PR head,與落地版逐檔等價)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用,沿 #188 / #190 / #199 / #202 / #211 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=typescript-reviewer(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .ts/.tsx 100% 的 source 改動,單派不 chunk);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE;純讀碼 + 後端對照);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=13 → covered 4 / no-issues 9 / skipped 0 / **missed 0**(chunked: **否**,7 source 檔 / 641 source diff 行,低於 15 檔 / 800 行門檻;13/13 per-file accounting 齊)
**定位 (ENH-B)**: anchored exact 5 / ambiguous 0 / **FAILED 0**(五條 anchor 在 worktree 逐字唯一命中:StockChart.tsx:174 / :166、live-last-bar.ts:109 / :22 / :72;行號以 grep 結果為準,R-03 reviewer 自報 :21-24 校正為 :22;F-03 的 inline 落點是 verification.md §6 判準 1,grep 校正為 :66)
**React-doctor (2.97)**: 未引入新問題(`--scope changed --base 410c0f1c --json` 於 review worktree:newCount 1 / fixedCount 1 / baseTotalCount 1,changedFileCount 7 —— 唯一命中 `no-high-complexity-react-function` StockChart.tsx:59 與 base 的 :48 是**同一條**,因行號位移被計為 new + fixed 各 1;命中行 `export function StockChart({` 非 `+` 行,依 2.97 判 pre-existing)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_CLAUSE)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出;`sem` 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(typescript-reviewer)PASS(5 findings + 13/13 accounting;無 node_modules 純讀碼,gate 數字引 PR 內 verification.md)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 請求體解析 / 秘鑰讀取)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(5/5 verdict 齊、ID 集合精確相等、每列六欄齊)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-218`
**worktree HEAD**: `8af45c428d177695acd48a0b47667bcaa9086640`

**Report generation**: sha256:7df89e3e1546a6f236de301aada9b20a68f6aaa2e05f53449ee224d69710e6cf

---
## [完整證據副檔](pr-218-review.audit.md)
### finding_uid 索引
[eb3e8304f3d1fe414256](pr-218-review.audit.md#發現總覽) · [483157557c4aaa01f5ad](pr-218-review.audit.md#發現總覽) · [07bf3ecaf54c56fca977](pr-218-review.audit.md#發現總覽) · [9bf028e15904ff61c793](pr-218-review.audit.md#發現總覽) · [41c126195a1c5f5a4387](pr-218-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `StockChart.tsx:174` 日 K 定稿閘只看 `dataUpdatedAt`,而達錢關著 / 忙時後端 14:01 回的是 **200 + 界前墊背舊快照 + status 非 ok**(`bars.py::_daily_stale_or_empty`,`stock_engine.bars_range` 斷線不 raise 回 `disconnected`),TQ 當成功、`dataUpdatedAt` 前進 → 閘關 → 今天那根從 accum 真值**退回早上半成品**,分 K 輪詢對非空墊背不重試、下一界午夜 → 鎖到午夜零訊號;spec story 5「14:01 失敗不退回」只兌現 HTTP 非 2xx 那半 | MEDIUM | CONFIRMED(MEDIUM→MEDIUM:五段機制第一手追過;無 mitigation;baseline「14:01 拿墊背鎖到午夜 user 拍板 F5」讓值不比 PR 前差,新增的是視覺退回一跳) | Should Fix | `auto-fix` | 一行條件 `\|\| data?.status !== "ok"` + 一條 RTL(14:05 + status disconnected + 非空 → 仍蓋),局部且方向明確 |
| F-02 | `live-last-bar.ts:109` 日 K h/l 直接以 accum 取代不取 max/min;`accum.high` 是後端逐 tick running max(非 TC4 當日高低欄),回補放棄(`_backfill_gave_up`)或盤中重啟未回補時只涵蓋之後成交 → 今天那根高低比正式半成品**窄**,side bar 同源看不出來 | MEDIUM | CONFIRMED(MEDIUM→LOW:回補成功即全量重建自癒、14:01 定稿封頂、只影響今日上下影線、`v` 走 cum_vol 不受影響;無先例,`Math.max/min` 單調安全) | Nice to Have | `auto-fix` | 取代分支改 `h: Math.max(last.h, live.high)` / `l: Math.min(last.l, live.low)` + 一案,註解與 spec.md:49「必然 ⊇」改口 |
| F-03 | `live-last-bar.ts:72` 補的分 bar `o` = 前一根 `c` 可落在 [l,h] 外 → 正式版換上時顏色 / 實體可能翻一格;資料層是 spec Out of Scope 明文近似(user Q11),成立的是 `verification.md` §6 判準 1「無跳動」分不出已知近似與真 bug | LOW | CONFIRMED(僅判準用語;資料層 OUT_OF_SCOPE:spec.md Out of Scope「每分鐘首筆價…用前一根收盤代替」;渲染不炸:`candle.ts` 值域吃 o、影線夾到實體外緣) | Nice to Have | `auto-fix` | 只改判準句:「時戳不位移;o 與顏色可能變一格(已知近似)」,不動 code |
| F-04 | `StockChart.tsx:166` 交易日閘只擋日曆知道的休市日;日曆漏的臨時休市(颱風假 / 日曆檔過期)當天 09:00 後引擎不換日、accum 仍前一交易日 → 分 K 隨牆鐘逐分鐘貼昨天的 K、日 K 補一根假今天;snapshot 無日期欄前端拿不到引擎日別 | LOW | CONFIRMED(已知類別:snapshot 無日期欄屬實、stage2 等首筆屬實;**mitigation reviewer 漏查**:`/api/calendar` 已回 `trade_date` 且前端全域取數,留尾修法比「snapshot 加欄」便宜;臨時休市是既有 KR-3,boot 有 WARNING + ops 解) | Nice to Have | `ask-user` | 留尾決策:要不要讓閘同時比 `/api/calendar` 的 `trade_date === today`(引擎日別),或維持「日曆過期靠 years_loaded WARNING」 |
| F-05 | `live-last-bar.ts:22` `Math.min(accumMinute + 1, 810)` 把 ≥13:30 **所有**分鐘都併進 13:30 那根(spec 只要求併收盤撮合那筆);repo 其他 accum 消費端(VP 窗)是窗外丟棄不是夾端點 | LOW | PARTIAL(LOW→LOW:**mitigation reviewer 未算到** —— 正式 1 分 K 一含 13:30 根 `endMin <= afterMinute` 整段跳過,分 K 輪詢到 13:35 → 曝險只有收盤後幾分鐘;盤後定價 = 收盤價只灌 `v`;「13:32 後 TC4 是否推 tick」reviewer 自陳未驗) | 參考用 | `no-op` | 不改 code;`barMinuteOf` doc 標明夾端點範圍即可,期貨 / 加權接線批(分鐘域不同)再一起想 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: eb3e8304f3d1fe414256 action=auto-fix
F-02 finding_uid: 483157557c4aaa01f5ad action=auto-fix
F-03 finding_uid: 07bf3ecaf54c56fca977 action=auto-fix
F-04 finding_uid: 9bf028e15904ff61c793 action=ask-user
F-05 finding_uid: 41c126195a1c5f5a4387 action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 達錢關著時 14:01 那發不是失敗、是 200 + 舊快照,定稿閘會關掉、今天那根退回早上的值
**File**: `frontend/src/components/stock/StockChart.tsx`
**Line**: 174

**Comment**:
```
這條閘的前提寫「14:01 那發失敗(TC4 關著)時 dataUpdatedAt 不前進」,但後端那條路不是失敗:
stock_engine.bars_range 斷線不 raise、回 ([], "disconnected"),bars.py 的 _daily_stale_or_empty
把界前的早上快照墊回去、status 照帶,app.py 回 200 → TQ 當成功、dataUpdatedAt 前進到 14:01
→ liveDay 變 null → 今天那根從逐筆算的真值退回早上開圖時的半成品,而且非空墊背不重試、
下一道界是午夜 → 整個下午都是舊值,畫面上零訊號。

status 已經在同一份 data 上,閘多看一眼就好:

const liveDay =
  liveOn && mode === "day" && (dataUpdatedAt < finalAt.getTime() || data?.status !== "ok")
    ? accum : null;

順手補一條 RTL:14:05 + status "disconnected" + 非空 bars → 仍以 accum 蓋;spec story 5 的措辭
改成「14:01 拿到失敗或墊背都不退回」。
```
#### #2 今天那根的高低直接拿 accum 的,回補沒到或放棄時會比正式版還窄
**File**: `frontend/src/lib/live-last-bar.ts`
**Line**: 109

**Comment**:
```
「accum 的 high/low 必然 ⊇ 半成品」只在當日 tick 回補落地後成立:high_milli 是逐筆 running max,
不是達錢報價的當日高低欄。盤中重啟 server 或這檔回補逾時放棄(_backfill_gave_up)後,accum 只算
重啟後的成交 → merge 完今天那根的上下影線比正式 DK 還短,側欄同源所以對不出來。

取代分支改成聯集就安全(兩邊都 ≤ 真極值,取 max/min 不會越界):

const merged = { h: Math.max(last.h, live.high), l: Math.min(last.l, live.low), c: …, v: … };

append 分支沒正式值可比、維持現狀。註解跟 spec.md 那句「必然 ⊇」一起改口。
```
#### #3 判準寫「換成正式版時畫面無跳動」,但補的根顏色本來就可能翻一格
**File**: `.claude/feat/live-last-bar/verification.md`
**Line**: 66

**Comment**:
```
補的分 bar 開盤價 = 前一根收盤(spec Out of Scope 明文、user Q11 知情),所以正式 1 分 K
換上時 o 會變、近平盤那幾根顏色會翻面 —— 這是預期內的近似,不是 bug。§6 判準 1 現在寫
「補的根被正式版換掉時畫面無跳動」,明天盤中驗的人會把預期內的翻色當 bug 回報、或反過來把
真的整條右移當成「就是那個已知近似」放過。

改成可判別的句子:「補的根換成正式版時**時戳不位移**;o 與顏色可能變一格(已知近似,見
next-time『即時末根已知近似』)」。code 不動。
```
#### #4 交易日閘只認日曆,日曆漏掉的休市日還是會貼出昨天的 K
**File**: `frontend/src/components/stock/StockChart.tsx`
**Line**: 166

**Comment**:
```
isTradingDay 靠 /api/calendar 的假日集合(沒載入時只擋週末)。颱風假或 trading_holidays.json
沒更新到當年時,那天 09:00 後引擎等不到新日首筆不換日、accum 整天是前一交易日的 →
分 K 會隨牆鐘一分鐘一分鐘把昨天貼成今天,日 K 補一根假的「今天」,零訊號。
低頻、而且 boot 已有日曆過期 WARNING,本批不動。

留尾要做的話最便宜的是:/api/calendar 已經回 trade_date(引擎日別),閘多比一句
trade_date === today,不用動 snapshot 形狀。要不要做請拍板。
```
