# PR #202 Code Review 比較報告 · SHA ca235bac
**Report projection schema**: 1

**PR**: [loger-w/copycat#202](https://github.com/loger-w/copycat/pull/202)
**標題**: mod(next-time-w1): 2026-09-07 盤點批 —— C17 日 K 末根定稿界 / B3 seed send close_sent / B2 新增群組保留輸入 + 置頂 + 守門 / B11 B15 測試 / B14 ruff PLE1205-1206
**作者**: loger-w
**分支**: `mod/next-time-batch-w1` → `master`
**變更**: 14 檔案, +574 / -56
**審查日期**: 2026-09-08
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨)
**Review input basis**: source repo id `R_kgDOTsITBg` + source SHA `ca235bac8b7da203abef18c101e72a5362a01bd5`;destination repo id `R_kgDOTsITBg` + destination SHA `556f497266a735f71688926d58c0ab902cd4f54d`;`input_binding: verified`(`refs/pull/202/head` FETCH_HEAD 逐字等於 headRefOid、worktree HEAD 同值;baseRefOid = `git merge-base` 同值)
**Review continuity**: `source_continuity=CURRENT`(產報告前重抓 headRefOid `ca235bac` 未變;分支已隨 rebase merge 刪除);`base_changed=true`(origin/master 自 `556f4972` 前進至 `e75837da`,內容 = 本 PR 的 rebase merge 9 筆,其後零新 commit);`review_context_changed=false`(head 未動,base 前進即本 PR 自身落地)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用,沿 #188 / #190 / #199 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;.py 改動行 69 vs .ts/.tsx 52 → python 57% 為主語言,tsx 檔納入同一 reviewer 的 per-file accounting);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=14 → covered 4 / no-issues 10 / skipped 0 / **missed 0**(chunked: 否,10 source 檔 / 630 diff 行低於 15 檔 or 800 行門檻)
**定位 (ENH-B)**: anchored exact 5 / ambiguous 0 / **FAILED 0**(五條 anchor 皆在 worktree 以 grep 逐字唯一命中:useMarketBars.ts:74 / app.py:1894 / pyproject.toml:22 / WatchlistManagerDialog.tsx:99 / WatchlistManagerDialog.tsx:123)
**React-doctor (2.97)**: 未引入新問題(`--scope changed --base 556f4972 --json`:newCount 1 / fixedCount 1 / baseTotalCount 3,changedFileCount 3 —— new 與 fixed 是**同一條** `no-high-complexity-react-function` `WatchlistManagerDialog.tsx:42`,diagnostic id 含訊息文字,複雜度數字隨新增的 `addInFlight` 分支上調而換 id;master 基準 `--scope all` 同規則同檔同行本就存在,實質零新引入)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_SPEC_DOCUMENT)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer)PASS(5 findings + 14/14 per-file accounting)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 使用者輸入解析;`ws_stock` 的入站 view 解析未在 diff)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(5/5 verdict 齊、ID 集合精確相等、每列四欄齊)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-202`
**worktree HEAD**: `ca235bac8b7da203abef18c101e72a5362a01bd5`

**Report generation**: sha256:b5e885dbdf6c93ae1be2c5b4d7f151b5b009d14fa152b9967364e4819cf71e49

---

## Spec 依據

- 此 PR 未附 spec / plan 文件(Step 2.6 heuristic 對 14 檔零命中:`docs/next-time.md` 與 `.claude/mod/next-time-batch-w1/verification.md` 的路徑與檔名皆不符 specs / plans / *-spec.md 規則)。實質 spec = `docs/next-time.md` 的 `## 2026-09-07(next-time 盤點,user 逐條拍板…)` 節(W1 六條)+ 該節指向的六條原始留尾 + user 對話中的追加要求(新增群組列搬到左欄最上方)。**該節作者 = PR 作者**(同一 session 寫入;out-of-scope 判定以此為據時注意利益重疊)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_SPEC_DOCUMENT`(無正式 spec 檔,留尾文字為非正式敘述、無 MUST / SHALL / INVARIANT 級可綁定條款)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool call count=N-A(未派);0 clauses / 0 findings / 0 observations / 0 invalidated。
- Author calibration(Step 2.2):無作者校準檔(`loger-w.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

provenance: N-A(base = master,14 檔全 authored)。

| 檔案 | 類型 | 說明 |
|---|---|---|
| `copycat/server/bars.py` | 修改 | C17:`is_partial_last` tf=D 分支同吃 `DAILY_FINAL_TIME`(+ `pre_final=` 參數);新 `period_bars_pre_final(cache, code, today)` 讀 `|L` 長窗界前標記(round-1 S-01 墊背路徑) |
| `copycat/server/app.py` | 修改 | 三處 relay 前 seed 改走 `send_seed`(B3);D/W/M 路徑 `partial_last` 餵 `pre_final=period_bars_pre_final(...)` |
| `copycat/server/ws.py` | 修改 | 新 `send_seed(websocket, payload) -> bool`:WebSocketDisconnect / close_sent RuntimeError 回 False,其餘照拋 |
| `frontend/src/components/stock/WatchlistManagerDialog.tsx` | 修改 | B2:群組名輸入框只在 `onDone` 且仍等於送出名字時清;`addInFlight` 守門 + 「新增」鈕 disabled;重開清 groupInput / 守門;新增列搬到 `<ul>` 上方(border-b);引導文案「可在上方新增」 |
| `frontend/src/components/stock/WatchlistManagerDialog.test.tsx` | 測試 | 新 describe 六案(撞名保留 / 4xx 保留 / 成功才清 / 在途新字不被吃 / 在途守門 / 新增列第一區塊);N115 #1 改釘守門(留尾預告);「上方新增」文案案;重開案加 groupInput 斷言 |
| `frontend/src/components/futures/FuturesChart.tsx` | 文件 | 註解補「D 分支另吃 14:00 定稿界,仍非夜盤口徑」(round-1 F-02) |
| `pyproject.toml` | 設定 | `[tool.ruff.lint] select = [E4, E7, E9, F, PLE1205, PLE1206]`(B14) |
| `tests/server/test_bars.py` | 測試 | B11 prune 兩案;`TestIsPartialLast` 五案(含 pre_final / `period_bars_pre_final` 三態) |
| `tests/server/test_market_routes.py` | 測試 | `TestPartialLast` 凍鐘 + after_final_time + stale_fallback 三案 |
| `tests/server/test_verify.py` | 測試 | B15 `_DAILY_PAD_ROWS == _DAILY_MIN_ROWS` parity |
| `tests/server/test_ws_disconnect.py` | 測試 | `TestSendSeed` 四案 |
| `docs/next-time.md` | 文件 | 2026-09-07 盤點節(結案 13 條 / W1 / W2 / W3 / 保留)+ W1 六條勾銷與出貨要點 |
| `.claude/mod/next-time-batch-w1/verification.md` | 新增 | gate 兩輪數字、紅→綠、八個突變體、pycache 假紅記帳、真環境判準 |
| `.claude/mod/next-time-batch-w1/code-review-round-1.json` | 新增 | 分支自身 two-axis round-1(9 條)處置 |

## 發現總覽

| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | C17 只對「重新載入」的大盤頁生效:`useMarketBars.ts:74-86` D/W/M 的 staleTime / refetchInterval 到午夜才重問,整天掛著的 preview 頁 14:00 後仍印「· 最後一根未收盤」;round-1 S-04 只改寫判準措辭,`docs/next-time.md` 無對應留尾(08-31 第 53 行那條只講期貨 15:00 錨定界) | MED | CONFIRMED(降 LOW:錯的只有 meta 字尾文案,bar 值正確;無緩解層 —— tab hidden 不 unmount、200 降級不進 60 s 重試;spec 未排除、W2 的 C16 也不涵蓋) | Nice to Have | `auto-fix` | 純文件:補一條留尾併 W2 與 C16 同議「大盤日 K 的 14:00 界要不要進 dayBarsRefetchInterval」 |
| F-02 | `pyproject.toml:22` 用 `select` 凍住預設集,註解寫「保留預設」但 ruff 日後調預設不會跟;`extend-select` 才是字面語意 | LOW | CONFIRMED(`ruff 0.15.20 --show-settings` enabled = E4/E7/E9/F 系,當下零差異;全庫無第二處可比照) | Nice to Have | `auto-fix` | 一行設定改 `extend-select = ["PLE1205", "PLE1206"]`,零行為 |
| F-03 | `WatchlistManagerDialog.tsx:99` 關窗再開無條件 `setAddInFlight(false)`,加上 `:124` 的 onSettled 無 key 解除:送出後立刻關窗再開可再送一發、第一發 settle 又放掉第三發 —— S-02 要擋的「第二發假 BAD_GROUP」在此路徑仍可達 | LOW | PARTIAL(可達但窗極窄:要在 PUT 在途中關窗再開並**重打同一組名**;後果 = 群組已建立卻跳 BAD_GROUP 橫幅,`addGroup` 冪等無資料遺失;`renameInFlight` 的開窗重置 `:98` 長期同形未見事故 → 非本 PR 新引入;keyed 解除只補第三發那半) | Nice to Have | `auto-fix` | onSettled 改 keyed 解除(比照 renameInFlight);開窗重置維持與 rename 同形 |
| F-04 | `WatchlistManagerDialog.tsx:116-125` 「只清送出的那個名字」那六行註解講的是 `:122` 的 onDone,中間被 `:119` 守門行隔開,讀起來像在解釋守門 | 參考用 | CONFIRMED(純可讀性;同檔 `submitRename` `:141-143` 是守門在前、註解緊貼 commit,有現成排法可比照) | Nice to Have | `auto-fix` | 守門連同其註解上移到空字串早退之後 |
| F-05 | `app.py:1894-1903` `period_bars_pre_final` 在 `build_period` 之後再讀一次快取,跨 await 兩發併發時 B 的 `daily_put` pop 掉標記可能讓 A 把界前快照標成已定稿 | LOW | REFUTED(兩道各自獨立:① route 內 `await build_period` 與 `period_bars_pre_final` 之間零 await,事件圈內不可插隊;② `daily_put` 是同一段同步碼「先寫 `_daily` 再 pop」,標記已 pop ⇔ `_daily` 已是定稿值,A 的墊背拿到的就是 B 的定稿 bars,`pre_final=False` 屬實) | 參考用 | `no-op` | 非缺陷;兩讀合一的重構(build_period 回墊背旗標)可入 W3 但不必要 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: f648446dc88b40d2f5ad action=auto-fix
F-02 finding_uid: a62556dc6e926b6fc042 action=auto-fix
F-03 finding_uid: bd1bcb263631c72418f8 action=auto-fix
F-04 finding_uid: 4387e81e15a891a5138d action=auto-fix
F-05 finding_uid: 601bd3e8d936d9f0e341 action=no-op

### Inline Comments per Finding（直接複製貼到 PR review）

#### #1 這個修法只救得到「重新載入」的大盤頁,整天掛著的那頁 14:00 後還是印「未收盤」

**File**: `frontend/src/hooks/useMarketBars.ts`
**Line**: 74-86

**Comment**:
```
C17 在後端把 tf=D 的 partial_last 改成 14:00 後回 False,但這支 hook 的日 / 週 / 月 K
staleTime 撐到午夜、refetchInterval 也是 msUntilDayRollover → 早上載入的那份 body
整個下午不會再問後端,MarketChart.tsx:162 那句「· 最後一根未收盤」照印到 00:01。
看盤日常正是 preview 整天掛著,所以主要情境其實沒被蓋到;只有 F5 / 新開分頁才對。

不是要現在改 code —— 只是 next-time 裡沒有這條(08-31 那條只講期貨 15:00 錨定界,
明寫「只有期貨那支該吃 15:00 界」)。建議補一條留尾,併 W2 的 C16 一起議:
大盤日 K 的重抓時點要不要加 14:00 這一界,或前端比照 FuturesChart 自算不信 partial_last。
```

#### #2 這裡用 `select` 其實把 ruff 預設集凍住了,想「保留預設」該用 `extend-select`

**File**: `pyproject.toml`
**Line**: 18-22

**Comment**:
```
select = [...] 是「只跑這幾組」,E4/E7/E9/F 是現在 0.15.20 的預設沒錯(已用
--show-settings 核過,今天零差異),但哪天 ruff 調預設就不會跟著動,而註解寫的是「保留預設」。

extend-select = ["PLE1205", "PLE1206"] 一行就是字面語意,預設集交給 ruff 自己維護。
```

#### #3 送出後立刻關窗再開,守門就被放掉了

**File**: `frontend/src/components/stock/WatchlistManagerDialog.tsx`
**Line**: 99

**Comment**:
```
prevOpen 那段重開時無條件 setAddInFlight(false),而 :124 的 onSettled 也是無條件 false。
PUT 在途中關窗再開 → 旗標歸零 → 重打同一個名字再送會排進佇列 → 第一發成功後第二發撞名
跳「群組名稱不合法」(群組其實已建好);接著第一發的 onSettled 又把旗標放掉,第三發也能排。
窗很窄、群組不會壞(addGroup 冪等),只是橫幅誤導。

renameInFlight 的開窗重置(:98)長期就是這樣、沒出過事,所以重置那半可以不動;
onSettled 那半比照 renameInFlight 改 keyed 解除就好:
  const [addInFlight, setAddInFlight] = useState<string | null>(null);
  ...
  () => setAddInFlight((cur) => (cur === name ? null : cur)),
```

#### #4 這六行註解講的是 onDone 那段,中間被守門那行隔開了

**File**: `frontend/src/components/stock/WatchlistManagerDialog.tsx`
**Line**: 116-125

**Comment**:
```
「群組名輸入框只在成功後清 … 只清這一發送出的那個名字」講的是 :122 的 onDone,
但 :119 的 if (addInFlight) return 夾在中間,第一眼會以為那段在解釋守門。
同檔 submitRename(:141-143)是守門在前、註解緊貼 commit —— 把守門連同它那行註解
上移到 if (name === "") return 之後,註解就直接貼著它要講的 commit 了。
```

#### #5 這條 Codex 式的併發疑慮其實走不到,route 裡兩讀之間沒有 await

**File**: `copycat/server/app.py`
**Line**: 1894-1903

**Comment**:
```
不是 PR 缺陷。擔心的是 build_period 回來後再讀 period_bars_pre_final 時,另一發已經
daily_put 把界前標記 pop 掉,讓墊背回的界前快照被標成已定稿。兩道理由各自否掉:
1. await build_period 到 period_bars_pre_final(...) 之間零 await,事件圈內插不了隊;
2. daily_put(bars.py:359-368)是同一段同步碼「先寫 _daily 再 pop」—— 標記被 pop 的那一刻
   _daily 已經是那份定稿值,A 的墊背拿到的就是 B 的定稿 bars,pre_final=False 沒說謊。
要讓 build_period 直接回「這趟是不是墊背」把兩讀合一是可以的重構,但不是為了修 bug。
```

## CC 主軸原始 findings(first-pass, context-aware)

### Section A — findings(python-reviewer,逐字;編號為 reviewer 原編號,與發現總覽重排後的 # 對照:R-01→F-01、R-02→F-05、R-03→F-02、R-04→F-03、R-05→F-04)

#### R-01 [MEDIUM] C17 的使用者面目標在「整天掛著的頁面」未達成,且此殘餘只寫在 `.claude` artifact,未進 tracker

- 檔案:`frontend/src/hooks/useMarketBars.ts:74-86`(連帶 `copycat/server/bars.py:539`)
- anchor:`staleTime: isMinute ? 0 : dayBarsStaleTime,`
- 問題:D/W/M 的 `refetchInterval` = `msUntilDayRollover(Date.now())`(`lib/day-bars-rollover.ts:114-118`),午夜前不重問。C17 的來源敘述是「14:00–24:00 一直印『最後一根未收盤』」,而 CLAUDE.md §1 的看盤日常正是 preview 整天掛著 → 修完後那頁整個下午仍印錯字樣,只有重新載入才對。
- 影響:行為修正正確但覆蓋不到主要情境;round-1 S-04 只改寫了「判準措辭」,`docs/next-time.md` 沒有對應留尾(第 53 行那條是**期貨** 15:00 錨定日 / CDP 基準,明寫「只有期貨那支該吃 15:00 界」,不涵蓋大盤 `partial_last`)。
- 建議:把「大盤日 K 的 14:00 界要不要進 `dayBarsRefetchInterval`」寫進 next-time(自然併 W2 的 C16 一起議);或前端自算(比照 `FuturesChart` 不信 `partial_last` 的作法)。
- search-proof:`grep -rn partial_last frontend/src` → 唯一讀者 `MarketChart.tsx:162`;`grep -n "常開\|staleTime" docs/next-time.md` → 無此條。

#### R-02 [LOW] `period_bars_pre_final` 與 `build_period` 分兩次讀同一份快取,跨 await 有窄競態

- 檔案:`copycat/server/app.py:1894-1903`
- anchor:`bars, tag = await build_period(tagged_source, bars_cache, code, today, tf)`
- 機制(已追):`build_*` 無 inflight dedup(`bars.py:415` 自述)。14:00 後兩發併發:A 取數空手 → `_period_stale_or_empty` 回界前快照;B 取數成功 → `daily_put` pop 掉標記。B 的 pop 若落在 A 的 `period_bars_pre_final` 之前,A 這一則就把界前快照標成「已定稿」= S-01 要修的形狀在併發下復現(下一發自癒)。
- 建議:讓 `build_period` 連同「這一趟是不是界前快照」一起回,route 不再二次讀 cache —— 順帶 `|L` 鍵不外洩、W/M 不用白算、也消掉 `pre_final=False` 這個「忘了傳就靜默退回舊 bug」的預設值。

#### R-03 [LOW] `select` 凍住預設集,`extend-select` 才符合註解寫的「保留預設」

- 檔案:`pyproject.toml:18-22`;anchor:`select = ["E4", "E7", "E9", "F", "PLE1205", "PLE1206"]`
- 已驗:`ruff config lint.select` → Default `["E4","E7","E9","F"]`(ruff 0.15.20),當下零差異;`ruff check --select PLE1205,PLE1206 copycat tests` → All checks passed(**B14「存量 0」屬實**)。
- 建議:`extend-select = ["PLE1205","PLE1206"]`,日後 ruff 調預設不必人工追。

#### R-04 [LOW] `addInFlight` 在關窗再開時無條件歸零,守門可提早解除

- 檔案:`frontend/src/components/stock/WatchlistManagerDialog.tsx:99`;anchor:`setAddInFlight(false);`
- 機制(已追):佇列住 module 層、關窗後回呼照跑(`useWatchlistCommit.ts:150-153` 明文),`onSettled` 由 `.finally` 保證(:142-145)。送出後立刻關窗再開 → 旗標歸零 → 可再送一發;第一發的 `onSettled`(:128 無條件 false)隨後放掉旗標,第三發又能排隊 —— S-02 要擋的「第二發假 BAD_GROUP」在此路徑仍可達。`renameInFlight` 的 keyed 解除(`(cur === from ? null : cur)`)正是同形問題的既有解法。
- 建議:旗標改存送出的名字(`string | null`)+ keyed 解除;順帶一提在途時輸入框未 disabled,按 Enter 是零回饋 no-op(僅鈕變淡)。

#### R-05 [參考用] 註解與被註解的程式碼被守門那行隔開

- 檔案:同上 `:119-124`;anchor:`if (addInFlight) return; // 重送防護(review S-02):見 addInFlight 宣告處`
- 上方六行「只清送出的那個名字」講的是 `:127` 的 `onDone`,讀起來像在解釋守門;建議守門連同其註解上移到空字串早退之後。

### Section B — per-file accounting (14/14)

| 檔案 | 狀態 |
|---|---|
| `copycat/server/app.py` | finding R-02(F-05) |
| `copycat/server/bars.py` | REVIEWED_NO_ISSUES(D 分支跨午夜無回歸:00:00–14:00 時刻判準恆 True,末根為昨日 → 早退 False;R-01 連帶提及但無獨立問題) |
| `copycat/server/ws.py` | REVIEWED_NO_ISSUES(7 個 `accept()` 全查:僅 txo-pnl / corr / river 有 relay 前 seed,breadth `:1977` / stock `:2069` 的 seed 在 `stream(seed=)` 內,「三處非四處」屬實;`except (WebSocketDisconnect, RuntimeError)` + `_is_disconnect` 後 re-raise 符合「不懂的錯不吞」) |
| `docs/next-time.md` | finding R-01(F-01)(六條勾銷已逐條核對:C17/B11/B3/B2/B14/B15 皆 `[x]` 且附出貨要點) |
| `frontend/src/components/futures/FuturesChart.tsx` | REVIEWED_NO_ISSUES(註解與新行為一致) |
| `frontend/src/components/stock/WatchlistManagerDialog.tsx` | findings R-04(F-03)/ R-05(F-04) |
| `frontend/src/components/stock/WatchlistManagerDialog.test.tsx` | REVIEWED_NO_ISSUES(N115 #1 改釘守門有留尾原文預告,屬「事前標為該變」;`makeGate` 於測試內呼叫 → 讀到 beforeEach 的新 `fetchMock`) |
| `pyproject.toml` | finding R-03(F-02) |
| `tests/server/test_bars.py` | REVIEWED_NO_ISSUES(檔頂 autouse 凍 09:00,新案各自 monkeypatch,無時鐘相依) |
| `tests/server/test_market_routes.py` | REVIEWED_NO_ISSUES(`Switchable` 與 `fake_sources.py:118` 同簽名;`bars_mod._now_time` 正是 cache 與 `is_partial_last` 共用的鐘;全庫僅本檔斷言 `partial_last`,未引入時段 flake) |
| `tests/server/test_verify.py` | REVIEWED_NO_ISSUES(`be` 已於 `:26` import) |
| `tests/server/test_ws_disconnect.py` | REVIEWED_NO_ISSUES(`caplog.at_level(WARNING)` 下 debug 不入 records,斷言「無 WARNING」語意成立) |
| `.claude/mod/next-time-batch-w1/verification.md` | REVIEWED_NO_ISSUES(§5 的 B3 grep 判準與新 debug 行不衝突:prod `__main__.py:143` basicConfig 為 INFO) |
| `.claude/mod/next-time-batch-w1/code-review-round-1.json` | REVIEWED_NO_ISSUES(9 條處置與 diff 逐條對得上) |

reviewer 自陳:review worktree 無 `node_modules` / `.venv`,前端型別與 vitest 未實跑,以 PR 內 `verification.md` 的紀錄為憑(主 session 出貨前已實跑:pytest 3531 / vitest 3021 / tsc 0 / eslint 0 / validate 42/42);後端 ruff 掃描 `--select PLE1205,PLE1206` 於 worktree 以主樹 venv 實跑(All checks passed)。

## Codex 原始 findings

N-A —— user 明示本輪不跑 Codex(中性與對抗式兩軸皆停用,沿 #188 / #190 / #199 前例)。

## Gemini 原始 findings

N-A —— user 明示本輪不跑 Gemini(Flash / Pro 皆停用)。

## CC 對非 CC 軸的複查結果(Step 4.1)

N-A —— 無非 CC finding。

## 內部複查結果(Step 4.2 之替代;同軸 code-reviewer、非跨軸證據)

批次一輪、5/5 回 verdict、ID 集合精確等於輸入、每列 verdict / corrected_severity / severity_reason / evidence 四欄齊;複查前於 worktree 以主樹 venv 實跑四個觸及測試檔 **162 passed**。**注意:這是同軸(CC)內部複查,不構成跨軸證據**;Must Fix 候選來源中的「Codex CONFIRMED verifications of Opus findings」本輪不存在。

| # | reviewer | title | Verdict | 原始 → 校正 severity | 內部複查 evidence | 修法假設核 | 備註 |
|---|---|---|---|---|---|---|---|
| F-01 | python-reviewer | C17 對整天掛著的大盤頁無效 | CONFIRMED | MED→LOW | `useMarketBars.ts:74-86` staleTime + refetchInterval → `lib/day-bars-rollover.ts:29-71` 界 = 本機午夜 + 60 s slack(D/W/M 不吃 `active`、無 14:00 分岔);失效閘只剩非 2xx 才 60 s 重試(`DAY_ERROR_RETRY_MS`,L73-84)→ 200 降級不進;`code-review-round-1.json:56-60` S-04 只改判準措辭;`docs/next-time.md` C17 已 [x] 無殘餘留尾,08-31 第 53 行逐字只講 `useFuturesBars` 15:00 錨定界 | 成立:補留尾為純文件;前端自算方向可比照 `FuturesChart` 不信 `partial_last` 的既有作法 | 4.3b:cross_file_context = yes(hook → lib → 元件 → docs 四檔);錯的只有 meta 字尾文案、bar 值正確 → 認知誤導非錯資料,降 LOW |
| F-02 | python-reviewer | `select` 應為 `extend-select` | CONFIRMED | LOW→LOW | `ruff 0.15.20 check --isolated --show-settings` 的 `linter.rules.enabled` = E401/E402/E7xx/E9/F 系,與 `pyproject.toml:18-22` 前四項等價;`grep "select = \["` 全庫僅此一筆,無平行案例 | 成立:一行設定、零執行期影響 | 4.3b:cross_file_context = no;開發期設定偏好 |
| F-03 | python-reviewer | `addInFlight` 關窗再開無條件歸零 | PARTIAL | LOW→LOW | 路徑 = 送出(`:119-125`)→ PUT 在途中關窗再開(`:92-104` 重置 false 且清 groupInput)→ 需**重打同一組名**再送 → `useWatchlistCommit.ts:118-127` transform 回 null → `onErrorRef.current?.("BAD_GROUP")`;第三發那半成立:`:124` onSettled 無 key,對比 `renameInFlight` keyed 解除 `:150` 與同檔已 keyed 的輸入框清空 `:122`;但 `setRenameInFlight(null)`(`:98`)長期同形、同樣有開窗洞、未見事故 → 非本 PR 新引入;「新增」鈕 `disabled={addInFlight}`(`:381`)已給可見回饋;測試 `:452-462` 只釘在途重按 | 半成立:keyed 解除只補第三發,第二發是開窗重置放掉的;修法建議縮成「onSettled keyed 解除」,重置維持與 rename 同形 | 4.3b:cross_file_context = yes(佇列 `.finally` 語意在 hook 檔);後果 = 誤導橫幅、無資料遺失 |
| F-04 | python-reviewer | 註解與被註解程式碼被守門行隔開 | CONFIRMED | 參考用→LOW | `WatchlistManagerDialog.tsx:116-125` 註解講 `:122` onDone、夾 `:119` 守門;`submitRename` `:141-143` 守門在前、註解緊貼 commit,同檔有現成排法 | 成立:純搬行 | 4.3b:cross_file_context = no;純可讀性 |
| F-05 | python-reviewer | `period_bars_pre_final` 跨 await 競態 | REFUTED | LOW→LOW | ① `app.py:1783-1784` route 為 `async def market_bars`,`:1894-1903` `await build_period` 與 `period_bars_pre_final(...)` 之間零 await → 事件圈內不可插隊;② `daily_put`(`bars.py:359-368`)`if not bars: return` 後**先寫 `_daily` 再 pop**,同一段同步碼 → 「標記已 pop」⇔「`_daily` 已是新鮮定稿值」,A 的 `_period_stale_or_empty`(`:591-601` → `daily_stale`)拿到的就是 B 那份定稿 bars,`pre_final=False` 屬實;「pop 了但沒寫新值」的狀態不存在;凍結快照(TC4 回同值)由 `_warn_if_not_advanced`(`:406-434`)蓋 | 兩讀合一的重構本身可行(build_period 回墊背旗標),但不是為了修 bug | 4.3b:cross_file_context = yes(route 型態 + 快取寫入原子性兩處合看);被機制追蹤直接反證 |

### Step 4.3a consensus baseline check

N-A —— 本輪單軸,無 consensus finding。

### Step 4.3b lone-finding 判斷

本輪只有 CC 一軸,五條全為 lone finding,「他軸為何漏」在單軸情境下無意義(N-A);改記「是否依賴跨檔脈絡」(diff-only 讀者會不會漏):F-01 / F-03 / F-05 yes、F-02 / F-04 no,列於上表備註欄。`effective_severity` 一律取 `corrected_severity`(五條全 LOW;F-01 MED→LOW 因錯的只是文案而非資料);無安全類 finding,severity-calibration 矩陣不適用。

## Action Items

**Severity calibration**:6c Refactor Intent Gate N-A(本 PR 無「移除 / 削弱既有防護」類 finding;B2 的守門是**新加**防護,F-03 講的是它的洞而非拿掉它)。6d-1 hedge cap:F-03「送出後立刻關窗再開並重打同名」為窄窗假設情境 → ≤ Should Fix(實際落 Nice);F-05 的「兩發併發」假設已被反證。6d-3 Must Fix 雙半條件:五條皆無 user-visible 且 release-blocking 的後果(F-01 是既有文案在常開頁上的殘留、bar 值正確;F-03 橫幅誤導無資料遺失)→ 零 Must / 零 Should。Provenance cap N-A(base = master)。未驗證前提檢查:F-01 的「preview 整天掛著」來自 CLAUDE.md §1 明文(第一手)、「200 降級不進重試」來自 `day-bars-rollover.ts:73-84` 引文;F-03 的窗與後果由內部複查逐步 trace;無 finding 的 severity 建立在未驗證前提上。

**校準套用**:無作者校準檔(`loger-w.md` 不存在)、本輪無套用。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

無。

### Nice to Have(可選優化)

- F-01 `docs/next-time.md` 補一條留尾:「大盤日 K 的 14:00 界要不要進 `dayBarsRefetchInterval`(或前端比照 FuturesChart 自算不信 `partial_last`)」,併 W2 的 C16 同議;純文件。
- F-02 `pyproject.toml` `select` → `extend-select = ["PLE1205", "PLE1206"]`,註解「保留預設」才成立。
- F-03 `WatchlistManagerDialog.tsx` `addInFlight` 改 `string | null` 存送出名字,onSettled `setAddInFlight((cur) => (cur === name ? null : cur))`;開窗重置維持(與 renameInFlight 同形);可選補一案「在途關窗再開再送同名」。
- F-04 `WatchlistManagerDialog.tsx` 守門 `if (addInFlight) return` 連同其註解上移到 `if (name === "") return` 之後,onDone 註解貼回 commit。

### 參考用(內部複查 REFUTED / OUT_OF_SCOPE)

- F-05 CC[python-reviewer] 擔心 `period_bars_pre_final` 與 `build_period` 兩讀之間的併發競態 → 內部複查於 `app.py:1894-1903` 找到兩讀之間零 await、且 `bars.py:359-368` `daily_put` 先寫 `_daily` 再 pop 標記(同步碼)→ 「pop 了但沒新值」狀態不存在 → 使用者自行判斷;兩讀合一的重構可入 W3 但非缺陷。

## 審查工具比較 (qualitative)

- CC 視角(context-aware):五條裡三條是「設定 / 註解 / 守門邊角」,一條是「修法沒蓋到主要使用情境」(F-01,分支上的 two-axis round-1 S-04 已看到但只改了判準措辭、沒開留尾 —— 本輪把它補成可追蹤的條目),一條併發疑慮被機制追蹤反證。與分支自身 round-1(9 條)相比,本輪抓到的是 round-1 收修後的殘留(F-03 是 S-02 守門本身的邊角、F-04 是 round-1 註解搬動的副作用)。
- Codex 中性 / 對抗式:N-A(user 停用),無重疊率可算。
- Gemini:N-A(user 停用)。
- 內部複查結果分佈(4.2 替代、同軸):CONFIRMED 3 / PARTIAL 1 / REFUTED 1 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0;REFUTED 率 20%,校正後五條全 LOW(F-01 MED→LOW)。
- 對抗式第三軸增益:N-A。
- React-doctor 機械軸:0 實質新引入(baseline 判 new 1 / fixed 1 為同一條複雜度規則因數字變動換 id;master 基準本就有)。

## 沒做的部分（結案對帳）

- Codex 中性軸:N-A —— user 明示「不用 Gemini 跟 Codex」(09-05 起 per-PR override,沿 #188 / #190 / #199 前例),未起軸、未 retry。
- Codex 對抗式軸:N-A —— 同上。
- Gemini Flash 軸:N-A —— user 明示停用。Gemini Pro:N-A(同上;Step 2.96 依前例不再問)。
- Step 2.98 Codex preset 詢問:N-A(Codex 停用,依前例不再問)。
- Cross-axis verification 4.1:N-A(無非 CC finding)。4.2:以同軸 code-reviewer 內部複查代替(PASS,5/5),**非跨軸證據** —— 三條 CONFIRMED 全來自同一模型家族,user 讀 Nice to Have 時應據此下調權重。
- Blast radius(2.9):PASS(有跑)但空輸出跳過。
- React-doctor(2.97):PASS,未引入新問題(new 1 / fixed 1 為同一條既有規則換 id,見 header)。
- Formal spec traceability(2.65):SKIPPED (C4_NO_SPEC_DOCUMENT);spec-compliance-reviewer 未派。
- Author calibration(2.2):無檔、本輪無套用。
- Reviewer 未實跑前端測試 / 型別:review worktree 無 `node_modules`,python-reviewer 對 .tsx 純讀 code;前端綠燈證據引自 PR 內 `verification.md`(主 session 出貨前實跑 vitest 3021 / tsc 0 / eslint 0);後端四個觸及測試檔由內部複查於 worktree 實跑 162 passed。
- 未驗前提(集中揭露):F-01 的「常開 preview 頁不 unmount」為 code 讀取(`useMarketBars` D 分支不吃 `active`)+ CLAUDE.md §1 看盤日常敘述,未在真瀏覽器實錄 14:00 後文案;F-03 的窄窗路徑由 code trace 推得、未以測試重現(建議補案列於 Nice)。其餘 finding 的修法假設由內部複查逐條驗過(F-03 修法縮成 keyed 解除)。
- 真環境:本 PR 出貨時即標 prod 未重啟、UI 驗收點與 C17 / B3 判準留 user 下一交易日過目(見 PR body 試用指引與 `verification.md` §5);本 review 亦未驗。
- Self-Verify:已執行(`skill-verify-auditor`,requested=opus / observed=UNAVAILABLE;唯讀、只讀本草稿,零 tool 呼叫)。結果 R1–R10 全 PASS、`VERDICT: COMPLIANT`,輸出格式完整(十行 + 一行 verdict、順序正確、無 FAIL)→ 零修正,直接發布。
