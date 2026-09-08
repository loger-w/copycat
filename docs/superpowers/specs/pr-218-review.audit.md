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

## Spec 依據

- 偵測到 spec 檔:`.claude/feat/live-last-bar/spec.md`(路徑在 `.claude/feat/` 且檔名 `spec.md`;GitHub issue #214 為同一份 + review 修訂留言四點)。關鍵:Solution = 前端「即時末根」蓋在正式 K 棒之後(分 K 補正式 1 分 K 之後含進行中分鐘;日 K 今天那根即時、定稿後不蓋);Implementation Decisions 明列分鐘鍵 +1 / 13:30 上限 / `o` = 前一根 `c` / 定稿閘 `dataUpdatedAt ≥ 14:00`(review 回校)/ 啟動閘四條(同檔 / 非期貨態 / 09:00 起 / 交易日);**Out of Scope**:期貨 / 加權頁、個股期合約態、**每分鐘首筆價(補的根用前一根收盤代替)**、後端 / 快取 / 輪詢、群組圖牆、視覺標示;白名單:`useStockBars` 輪詢 / 日界政策、`aggregateBars` 桶界、CandleChart geometry、StockIntradayChart、accum 形狀。
- **⚠️ spec 作者 = PR 作者**(`git log --format='%an' -- .claude/feat/live-last-bar/spec.md` = Loger = PR 作者 loger-w;out-of-scope 判定以此 spec 為據時注意利益重疊 —— 本輪唯一引 Out of Scope 免罪的是 F-03 的資料層,該條同時由 user grilling Q11 拍板背書)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_NORMATIVE_CLAUSE`(spec 全文無 MUST / SHALL / NEVER 等 normative keyword、無 INVARIANT / FORMULA / STATE_TRANSITION / ERROR_CONTRACT 形式條款;「不得改這些」「不得變」屬白名單敘述,非可綁 `path:line` 的實作契約)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool calls=N-A(未派);0 clauses / 0 findings / 0 observations / 0 invalidated。reducer 安全投影要求:未派故無 `human_projection`;本報告零 C4 內容,`invalidated_ids ∩ report_finding_ids = ∅`(兩集合皆空),無 invalidated 語意外洩,C4 對 Step 4.5 覆蓋零貢獻。
- Author calibration(Step 2.2):無作者校準檔(`loger-w.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

provenance: N-A(base = master,13 檔全 authored)。

| 檔案 | 類型 | 說明 |
|---|---|---|
| `frontend/src/lib/live-last-bar.ts` | 新增 | 兩支純函式:`mergeLiveMinuteBars`(accum 起點分 +1 對齊 1K 終點標記、13:30 併根、`o` = 前一根 `c`、uv/dv 恆給欄、identity 保留)/ `mergeLiveDailyBar`(今天那根 `o` 保留、h/l/c/v 換 accum、缺今日列 append) |
| `frontend/src/lib/live-last-bar.test.ts` | 測試 | 規則表 11 案(分 K 7 + 日 K 4),期望值字面量 |
| `frontend/src/components/stock/StockChart.tsx` | 修改 | 接線:分 K merge → `aggregateBars`;日 K merge + 定稿閘(`dataUpdatedAt < 當日 14:00`);啟動閘 = 同檔 / 非期貨態 / 09:00 起 / `isTradingDay`;`dayOpen` 讀 1 分 K TQ cache(`stockBarsKey`) |
| `frontend/src/components/stock/StockChart.livebar.test.tsx` | 測試 | RTL 10 案(分 K 5 含週六 / 日 K 5 含定稿閘與 14:01 失敗仍蓋) |
| `frontend/src/hooks/useStockBars.ts` | 修改 | export `stockBarsKey` 唯一 queryKey 產生式(two-axis S-01) |
| `frontend/src/lib/candle.ts` | 修改 | `splitStamp` / `stampOf` 由 private 改 export + doc(two-axis S-03) |
| `frontend/src/lib/day-bars-rollover.ts` | 文件 | `DAILY_FINAL_TIME` doc 改口(src/ 內多一個讀者) |
| `CLAUDE.md` | 文件 | §4 新契約「個股頁即時末根分鐘鍵 = accum 起點分 +1、上限 13:30」+ `DAILY_FINAL_TIME` 讀者一句 |
| `CONTEXT.md` | 文件 | 「正式 K 棒」「即時末根」兩詞 |
| `docs/next-time.md` | 文件 | 個股頁半邊結案;期貨 / 加權接線與「已知近似」兩條留尾 |
| `.claude/feat/live-last-bar/spec.md` / `verification.md` / `code-review-round-1.json` | 新增 | spec(review 回校版)/ 紅→綠逐票 + 六隻突變體 + 全 gate + prod bench 三場景 + 真環境判準 + goal 對帳 / two-axis 11 條處置 |

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

#### #5 13:30 之後的分鐘全被夾進 13:30 那根 —— 但正式版一到就整段跳過,不用改

**File**: `frontend/src/lib/live-last-bar.ts`
**Line**: 22

**Comment**:
```
Math.min(accumMinute + 1, 810) 讓 13:31 之後任何分鐘都併進 13:30 那根;spec 只要求併收盤撮合
那筆,repo 其他 accum 消費端(VP 窗)是窗外丟棄不是夾端點。不過正式 1 分 K 一含 13:30 根,
endMin <= afterMinute 就整段跳過,分 K 輪詢跑到 13:35,曝險只剩收盤後幾分鐘;盤後定價成交價
= 收盤價,只會多灌 v。13:32 之後達錢會不會推 tick 沒驗過。

不改 code,只在 barMinuteOf 的 doc 註明「≥13:30 全夾到 13:30、曝險窗收盤後幾分鐘」;
期貨 / 加權接線那批分鐘域不同(0846–1345),照抄這個夾法會錯,到時再一起想。
```

## CC 主軸原始 findings(first-pass, context-aware)

typescript-reviewer(requested=opus),逐字要點;reviewer 原編號 → 發現總覽:R-01→F-01、R-02→F-02、R-03→F-05、R-04→F-03、R-05→F-04。

#### R-01 [MEDIUM] StockChart.tsx:172-174 — 日 K 定稿閘只看 `dataUpdatedAt`,TC4 關著在後端是 200 + 墊背舊快照
問題:閘前提「14:01 那發失敗時 dataUpdatedAt 不前進」為假 —— `bars.py:453-463 _daily_stale_or_empty` 在 fetch 空手時回界前快照(`daily_put` 空 list no-op、`daily_stale` 保留舊值),`app.py:1531→1551` 200 送出;TQ 成功 → dataUpdatedAt 前進 → `liveDay` null。影響:spec story 5 指名場景行為相反,`barsPollInterval`(`useStockBars.ts:82`)非空不重試、下一道界午夜 → 整個下午錯值零訊號;verification §6 判準 2 分不出墊背與定稿。修法:`dataUpdatedAt < finalAt.getTime() || data?.status !== "ok"`(`bars.py:461` 明寫不洗白;`stock_engine.py:896-898` 斷線回 `disconnected`)+ RTL 一案 + spec story 5 回校。spec-ref:`docs/next-time.md`「14:01 那發拿到墊背不自救(知情)…實務 = F5」、`day-bars-rollover.ts:56`「TC4 關著時後端回 daily_stale 墊背」。anchor:`const liveDay = liveOn && mode === "day" && dataUpdatedAt < finalAt.getTime() ? accum : null;`

#### R-02 [MEDIUM] live-last-bar.ts:109 — 日 K h/l 直接以 accum 取代不取 max/min
問題:「accum 必然 ⊇ 正式半成品」只在 `StockDayState` 含當日全量 tick 時成立;`h`/`l` 產生點 `stock_engine.py:1333 state.high_milli` 是逐筆 running max(`stock_state.py:148-151`),全量要 `apply_backfill`(`stock_state.py:98` reset 後重放)落地;回補會失敗也會當日放棄(`stock_engine.py:327/339` `_backfill_failed` / `_backfill_gave_up`,`:864` 逾時放棄不再入列)。影響:盤中重啟或回補逾時兩次後今天那根高低比正式值窄,零訊號。修法:取代分支 `Math.max/min`。search-proof(Grep,worktree):`high_milli` 唯一寫入點 = `copycat/live/stock_state.py:149-152`(`_apply` 內 `if self.high_milli is None or tick.price_milli > self.high_milli`,逐 tick running max)→ wire `copycat/server/stock_engine.py:1333`(`"h": state.high_milli`)→ 前端 `frontend/src/lib/stock-accum.ts:464`(`high: msg.h ?? acc.high`);`apply_backfill` = `stock_state.py:98`(先 `reset()` 再重放整日,全量只在此之後);`_backfill_gave_up` = `stock_engine.py:332-339`(逾時放棄集合,`:864` 放棄後不再自動入列)。關鍵 predicate:「任一路徑把 TC4 REALTIME 當日高低欄寫進 `high_milli`」= 零命中 → 「accum.high ⊇ 半成品 h」只在回補落地後成立,finding 仍成立。anchor:`const merged = { h: live.high, l: live.low, c: live.last.p, v: live.last.cum_vol };`

#### R-03 [LOW] live-last-bar.ts:21-24 — `barMinuteOf` 13:30 上限無上界
問題:`Math.min` 把 ≥13:30 所有分鐘鍵折到 810;repo 其他消費端(`stock_state.py:191` VP 窗、`stock-accum.ts:188 foldVp`、`windowedEntries`)是窗外丟棄。影響:低;`inTradingHours` 開到 13:35 再打 3–5 發,正式 13:30 bar 一到整段跳過;「13:32 後是否推 tick」reviewer 自陳未驗證。未驗證前提(明示):「13:32 之後個股是否仍推 tick」reviewer 與內部複查皆未驗(tc4-market-facts 只記到 13:31 收盤撮合)—— 該子句**只作條件句**(若推,則灌 `v`),不作為 finding 成立依據;finding 仍成立的部分 = 夾端點語意與 VP 窗外丟棄慣例不同(`stock_state.py:191` / `stock-accum.ts:188` 第一手),而 mitigation(`live-last-bar.ts:53` 正式 13:30 根到了整段跳過)讓實害趨近零,故 PARTIAL + 參考用。修法:只讓 13:30/13:31 落 810、其餘 null,併期貨 / 加權接線批。anchor:`const end = Math.min(accumMinute + 1, LAST_BAR_MIN);`

#### R-04 [LOW] live-last-bar.ts:72 — 補的分 bar `o` 可落在 [l,h] 外,判準句分不出近似與 bug
問題:正式 1K 的 `o` 恆在 [l,h] 內,補的根用前一根收盤常越界;渲染有防禦(`candle.ts:237-241` 值域吃 o、`:280-281` 影線夾到實體外緣)但 `:271 dir = c > o` 顏色會翻面。影響:視覺一格閃動;真正成本是 verification §6 判準 1 措辭。修法:不改 code,判準改「時戳不位移;o 與顏色可能變一格」。spec-ref:Out of Scope 第 3 條 + next-time「即時末根已知近似」。anchor:`cur = { t: stampOf(today, endMin), o: prevClose ?? a.c, h, l, c: a.c, v: a.v, uv: a.o, dv: a.i };`

#### R-05 [LOW] StockChart.tsx:165-166 — 交易日閘只擋日曆知道的休市日
問題:`lib/trading-calendar.ts:8-16`「未載入 = 空集合 = 只擋週末」;日曆漏的臨時休市當天引擎 stage2 等不到新日首筆(`stock_engine.py:1093` / `_checkpoint_loop:1135`),accum 整天前一交易日 → 分 K 隨牆鐘貼昨天、日 K 補假今天。影響:低頻零訊號;正常交易日開盤 stage2 全域 reset 窗口亞秒級不受影響。修法:本批不動(spec 後端零改動);留尾 = 引擎日別進個股快照(先例 `app.py` signals/today docstring、`/api/health` 已回 `trade_date`;`stock_engine.snapshot():713-736` 無日期)。search-proof(Grep,worktree):`stock_state.py:274-306` `snapshot()` payload 鍵集無日期欄、tick `t` 只有 `HH:MM:SS`(前端拿不到引擎日別 → 斷言成立);`stock_engine.py:1123-1140` `_checkpoint_loop` 註「假日靠階段二天然不清空」+ stage2 等新日首筆(休市日不換日 → 成立);`app.py:1319-1320` `/api/calendar` 已回 `trade_date`、`frontend/src/hooks/useTradingCalendar.ts` 全域取數(內部複查補上的 mitigation:留尾修法不必動 snapshot);`app.py:584-631` 日曆過期 boot WARNING + `TXO_BACKFILL_DATE` ops 解(既有 KR-3)。關鍵 predicate:「前端在 render 期能取得引擎交易日」= 目前 false(需接 `/api/calendar`),finding 仍成立但已知類別。anchor:`!isFut && accum.code === code && !accum.noData && nowMinute >= 9 * 60 && isTradingDay(now);`

### Per-file accounting(13/13,reviewer 原文要點)

- `frontend/src/lib/live-last-bar.ts` — R-02 / R-03 / R-04;分鐘鍵 / 併根 / prevClose 遞推 / identity 逐條核過,`h ?? c` 不會造成 h < l;日 K `lastDate > today` 早退與 append 分支正確。
- `frontend/src/components/stock/StockChart.tsx` — R-01 / R-05;memo deps 完整,`liveOn` render body 現算不吃 stale 日曆;merge 在 `aggregateBars` 之前與 spec 一致。
- `frontend/src/lib/live-last-bar.test.ts` — REVIEWED_NO_ISSUES(字面量、Map 亂序、identity 雙向、`aggregateBars(…,3)` 串接案最有鑑別力)。
- `frontend/src/components/stock/StockChart.livebar.test.tsx` — REVIEWED_NO_ISSUES(只假造 Date、TODAY 字面量、無 jest-dom、afterEach 還原;R-01 修法需在此補一案)。
- `frontend/src/hooks/useStockBars.ts` — REVIEWED_NO_ISSUES(`stockBarsKey` `as const` 合法;輪詢 / 日界政策未動)。
- `frontend/src/lib/candle.ts` — REVIEWED_NO_ISSUES(private → export + doc,零行為改動)。
- `frontend/src/lib/day-bars-rollover.ts` — REVIEWED_NO_ISSUES(「src/ 內唯一讀者」grep 核實;常數字面未動,後端 parity regex 仍匹配)。
- `CLAUDE.md` — REVIEWED_NO_ISSUES(新契約條與 code 逐項對得上)。
- `CONTEXT.md` — REVIEWED_NO_ISSUES(14:00 定稿敘述與 `bars.py:79` 一致)。
- `docs/next-time.md` — REVIEWED_NO_ISSUES(bench 數字與 verification §4 逐格相符)。
- `.claude/feat/live-last-bar/spec.md` — 由 R-01 覆蓋(定稿閘段「14:01 那發失敗 → dataUpdatedAt 不前進」假前提)。
- `.claude/feat/live-last-bar/verification.md` — 由 R-04 覆蓋(§6 判準 1)、R-01 順帶(判準 2);§1 / §2 / §7 與 `git log` 對照無誤。
- `.claude/feat/live-last-bar/code-review-round-1.json` — REVIEWED_NO_ISSUES(11 條處置逐條覆核;S-05 rejected 理由成立;Spec-06 `v` 單位另查 tc4-market-facts:121 屬實;`head_reviewed: 545f2e4d` 與 commit 序一致)。

## 內部複查結果(同軸 code-reviewer,取代 4.2;非跨軸證據)

| # | 原編號 | Verdict | 原始 → 校正 severity | Evidence(要點) | baseline | 單軸可信度 |
|---|---|---|---|---|---|---|
| F-01 | R-01 | CONFIRMED | MEDIUM → MEDIUM | `stock_engine.py:891-898` ConnectionError → `BarsResult([], "disconnected")` 不 raise → `bars.py:409-418` → `_daily_stale_or_empty:453-465` 回 stale 非空 + 原 status → `app.py:1531` 200;前端 `useStockBars.ts:56-66` 判 success → dataUpdatedAt 前進 → `StockChart.tsx:174` 閘關;`barsPollInterval:82` 非空不重試、`day-bars-rollover.ts:141` 下一界午夜。RTL 只覆蓋 HTTP 非 2xx | 慣例支持但不救(CLAUDE.md §4「14:01 拿墊背鎖到午夜 user 拍板」;值不比 PR 前差,新增視覺退回一跳) | 五段機制第一手追過 |
| F-02 | R-02 | CONFIRMED | MEDIUM → LOW | `accum.high` = `stock_state.py:149-152` running max → wire `stock_engine.py:1333` → `stock-accum.ts:464`;非 TC4 REALTIME 當日高低;`_backfill_gave_up` 實存 `stock_engine.py:332-339`。mitigation:`apply_backfill` 成功即全量重建、14:01 定稿封頂、只影響上下影線 | 無先例(新合流點);修法單調安全 | 第一手 |
| F-05 | R-03 | PARTIAL | LOW → LOW(近 informational) | 夾端點 `live-last-bar.ts:22`;後端 `minute_key`(`stock_state.py:157`)無上界。**mitigation reviewer 未算到**:正式 13:30 根一到 `:53 endMin <= afterMinute` 整段跳過;輪詢到 13:35(`trading-hours.ts:21`);盤後定價 c 不動只灌 v;「13:32 後推 tick」未驗 | 慣例衝突但語意不同(VP 是幾何 x 窗) | mitigation 面第一手、tick 推播面未驗 |
| F-03 | R-04 | CONFIRMED(僅判準用語) | LOW → LOW | `candle.ts:271` dir 吃 o;不炸(`:281-283` / `:235-242`);spec.md Out of Scope 明文 → 資料層 OUT_OF_SCOPE;成立的是 verification §6 判準 1 措辭 | 慣例支持(判準句普遍「可能微調一格」) | 第一手 |
| F-04 | R-05 | CONFIRMED(已知類別) | LOW → LOW | `stock_state.py:274-306` snapshot 無日期欄;stage2 等首筆(`stock_engine.py:1123-1140`)。**mitigation reviewer 漏查**:`/api/calendar` 已回 `trade_date`(`app.py:1319-1320`)且前端全域取數(`useTradingCalendar.ts`);臨時休市 = 既有 KR-3,`app.py:584-631` boot WARNING + `TXO_BACKFILL_DATE` ops 解 | 慣例支持(`isTradingDay` 全 repo 同一把尺;未載入只擋週末是白名單既有降級) | 第一手;mitigation 由複查補齊 |

## Action Items

Severity calibration:6c(移除既有防護類)— 本 PR 無此類 finding,免。6d-1(hedge cap)— F-05「13:32 後是否推 tick」未驗 → 已在參考用;F-04「颱風假 / 日曆過期」是既有 KR-3 已記錄事實,非假設。6d-3(Must Fix 雙半條件)— F-01 有 user-visible 重現路徑(達錢關著 → 14:01 今天那根退回早上值)但**不阻擋出貨**:退回後的值 = PR 前的既有行為(CLAUDE.md §4 拍板「14:01 拿墊背鎖到午夜,實務 F5」),新增的只是「即時→舊值」的一跳,故落 Should Fix。未驗證前提檢查:F-01 五段機制皆 file:line 第一手;F-02 回補放棄路徑 file:line 第一手,「盤中重啟頻率」未量(不影響等級,已是 LOW);F-05 的 tick 推播面未驗(已 PARTIAL + 參考用)。Provenance cap:N-A。校準套用:無作者校準檔(`loger-w.md` 不存在)、本輪無套用。4.3b lone finding:本場 CC 單軸,五條全 lone,「他軸為何漏」改答單軸可信度(見內部複查表末欄);F-01 / F-02 機制第一手 → 維持校正後等級,F-05 PARTIAL 且推播面未驗 → 維持 LOW 落參考用。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

- **F-01** 日 K 定稿閘加 `|| data?.status !== "ok"`(墊背路徑 status 不洗白);RTL 補「14:05 + disconnected + 非空 bars → 仍蓋」;spec story 5 與 `StockChart.tsx:170` 註解、verification §6 判準 2 回校(「14:01 一發 tf=D 且 status ok 後 = 定稿」)。

### Nice to Have(可選優化)

- **F-02** 取代分支 h/l 改 `Math.max/min`;註解與 spec.md:49 改口;lib 加一案(正式 h 大於 accum.high 時保留正式)。
- **F-03** verification §6 判準 1 改「時戳不位移;o 與顏色可能變一格(已知近似)」。
- **F-04** 留尾拍板:閘多比 `/api/calendar` 的 `trade_date === today`,或維持現況;入 next-time。

### 參考用(任一軸驗證為 REFUTED / OUT_OF_SCOPE / PARTIAL 且不建議動 code)

- **F-05** `barMinuteOf` 夾端點:CC 主軸擔心 ≥13:30 全併 → 內部複查於 `live-last-bar.ts:53` 找到正式 13:30 根一到整段跳過、曝險只剩收盤後幾分鐘 → 使用者自行判斷是否要收斂(建議只補 doc,併期貨 / 加權接線批)。

## 審查工具比較(qualitative)

- CC 主軸(typescript-reviewer):context-aware,五條全是「前端 code 與後端真實路徑 / 引擎狀態機」的跨層對照(墊背 200、running max、rollover stage2),純看 diff 抓不到。
- 內部複查(code-reviewer):同軸、非跨軸證據;5/5 齊,CONFIRMED 4 / PARTIAL 1 / REFUTED 0 / OUT_OF_SCOPE 0(F-03 資料層 out-of-scope 但判準用語成立故計 CONFIRMED);severity 下修 1(F-02 M→L),兩條補上 reviewer 漏查的 mitigation(F-04 `/api/calendar` trade_date、F-05 正式根整段跳過)。
- Codex / Gemini:N-A(user 停用),無跨軸重疊率可算;對抗式增益 N-A。
- REFUTED 率 0%:主軸命中率高,但同模型家族互驗,user 讀 Should / Nice 時仍應以 file:line 證據自判。

## 沒做的部分(結案對帳)

- Codex 中性軸:N-A —— user 明示停用(沿 #188 / #190 / #199 / #202 / #211 前例),未起軸、未 retry。
- Codex 對抗式軸:N-A —— 同上。
- Gemini Flash 軸:N-A —— user 明示停用。Gemini Pro:N-A(同上;Step 2.96 依前例不再問)。
- Step 2.98 Codex preset 詢問:N-A(Codex 停用,依前例不再問)。
- Cross-axis verification 4.1:N-A(無非 CC finding)。4.2:以同軸 code-reviewer 內部複查代替(PASS,5/5),**非跨軸證據**。4.3a consensus:N-A(單軸無 consensus);4.3b lone:五條全 lone,處置見 Action Items。
- Review input binding:**verified**(`refs/pull/218/head` = headRefOid `8af45c42`,worktree detached 於該 SHA;merge-base = baseRefOid)。
- Blast radius(2.9):PASS(有跑)但空輸出跳過(`sem` 未安裝)。
- React-doctor(2.97):PASS,未引入新問題(同一條 StockChart 複雜度 warning 因行號位移計 new 1 / fixed 1;命中行非 `+` 行)。
- Formal spec traceability(2.65):SKIPPED (C4_NO_NORMATIVE_CLAUSE);spec-compliance-reviewer 未派。
- Author calibration(2.2):無檔、本輪無套用。
- Reviewer 未實跑前端測試 / 型別:review worktree 無 `node_modules`,typescript-reviewer 與 code-reviewer 純讀碼;前端綠燈證據引自 PR 內 `verification.md`(出貨前實跑 vitest 3067 / tsc 0 / eslint 0)。
- 未驗前提(集中揭露):F-05「13:32 之後個股是否仍推 tick」未驗(tc4-market-facts 只記到 13:31);F-02「盤中重啟 / 回補放棄」的實際頻率未量;F-01 的「達錢關著時 14:01 必回墊背」是後端 code 路徑第一手推導,prod 實錄以 `grep 墊背舊快照 logs/server-*.log`(既有判準)為證、本輪未跑。
- 真環境:PR 出貨時即標下一交易日判準(`verification.md` §6;prod 未重啟、dist 已 build);本 review 亦未驗。
- Self-Verify:已執行(`skill-verify-auditor`,requested=opus / observed=UNAVAILABLE;唯讀、只 Read 本草稿檔一次,1 tool 呼叫)。第一輪 `VERDICT: VIOLATIONS: R4, R6`:R4 = C4 receipt 缺「reducer 安全投影」陳述(SKIPPED 情境下的 `human_projection` / `invalidated_ids ∩ report_finding_ids = ∅` 兩句)→ 已補進「Spec 依據」receipt;R6 = R-02 / R-05 search-proof 只列 grep 關鍵字、缺 file:line 與 predicate 語意,R-03 的「13:32 後推 tick」子句未標為條件句 → 已把內部複查表既有的 file:line 證據回寫到 CC 原始 findings 段並明示條件句。其餘 R1 / R2 / R3 / R5 / R7 / R8 / R9 / R10 PASS。**修正後未重派 auditor,未經第二次獨立稽查。**
