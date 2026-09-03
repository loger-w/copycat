# PR #187 Code Review 比較報告 · SHA b58ee057
**Report projection schema**: 1

**PR**: [loger-w/copycat#187](https://github.com/loger-w/copycat/pull/187)
**標題**: mod(group-grid-ticks): 群組圖牆逐筆 —— ticks 0.1 s 打包 + 檢視集合 + 不丟保險 + 三件群組 UI(C9,#179)
**作者**: Loger(loger-w)
**分支**: `mod/group-grid-ticks` → `master`(PR 已 rebase merge、遠端分支已刪;review 環境以 `refs/pull/187/head` 重建)
**變更**: 39 檔案, +1941 / −133
**審查日期**: 2026-09-03
**Review input basis**: source repo `R_kgDOTsITBg` + `b58ee057994456c05435c1f6ae0ac20468f4a6a5`;destination repo `R_kgDOTsITBg` + `a344da9f7ff782897dae8c36509de5632236f0fc`;input_binding: verified(worktree HEAD 逐字節等於 source SHA —— `git -C .worktrees/review-pr-187 rev-parse HEAD` = b58ee057…;base 以 PR API 的 baseRefOid 精確 SHA 釘定並可解析)
**Review continuity**: source_continuity=CURRENT(產報告前重抓 headRefOid 仍為 b58ee057、state=MERGED);base_changed=true(master 已因本 PR 自身的 rebase merge 前進至 1704db49、再加一筆契約回校 8d42098d —— diff 基準 a344da9f 為 PR API 之 baseRefOid,不受影響);review_context_changed=false
**審查工具**: CC context-aware reviewer agents(primary ×3 chunks + security-reviewer)+ 主 session 逐條機制核實(關鍵條 code trace / grep 反證)。Codex 中性、Codex 對抗、Gemini Flash、Gemini Pro 四軸因本機無對應 CLI 全數缺軸(第一手證據:主 session Bash 實跑 `which agy codex sqlite3` 三者皆 `no … in (PATH)`)—— 本輪為 CC 單軸多 reviewer + 同軸驗證,非 cross-axis,詳「沒做的部分」
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary=python-reviewer ×1 chunk(A:後端 + 文件)+ typescript-reviewer ×2 chunks(B:前端 components/hooks;C:前端 lib + 後端測試)(requested=opus / observed=opus,dispatch 皆顯式帶 model);domain=security-reviewer ×1(requested=opus / observed=opus);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED 未派);Codex=UNAVAILABLE(CLI 不存在);Gemini=UNAVAILABLE(agy CLI 不存在)
**覆蓋 (ENH-A)**: |F|=39 → covered 18 / no-issues 20 / skipped 1 / missed 0(chunked: 是 —— FILE_COUNT 15 source 檔未超,但 DIFF_LINES 2074 > 800 門檻;chunk A = `.claude/*` + `CLAUDE.md` + `copycat/*` + `docs/*` 11 檔、chunk B = `frontend/src/App.memo.test.tsx` + `components/stock/*` + `hooks/*` 14 檔、chunk C = `frontend/src/lib/*` + `tests/*` 14 檔;首輪 chunk B 漏記 `frontend/src/hooks/useStockStream.test.ts` → 4.5 repair 補審一輪(SendMessage 回同 instance)得 1 條 LOW;skipped 1 = `.claude/mod/group-grid-ticks/code-review-round-1.json`,理由 = 前一輪 review findings 原文資料檔、非行為)
**定位 (ENH-B)**: anchored exact 17 / ambiguous 3 / FAILED 0(另 1 條 `<none>`:#3 為缺測試型 finding,以 describe 區段錨定;ambiguous 3 = #11 `except ValueError:` 全檔三處取離 reviewer 報行最近的 2064、#17 `cum_vol: volume,` 兩分支 358/366 皆在報告區間、#21 `expect(ws.sent).toEqual([]);` 1060/1077 取 1077)
**React-doctor (2.97)**: 新引入 1 條(工具判)—— `--scope changed --base a344da9f --json` 實跑於 review worktree:`newCount 1 / fixedCount 2 / baseTotalCount 10`,唯一診斷 `src/components/stock/StockPage.tsx:78 no-high-complexity-react-function`;CC 判定為 master 基準已有同 rule 同函式(`StockPage` 元件,基準行 72)的**行號位移**(本 PR 在該元件加了側欄 onSelect 與 SignalRail onSelect 兩個 handler 分支,複雜度小幅上升但非新 rule 命中);見「React-doctor 機械掃描」段,建議級別 參考用
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_AUTHORITY)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 對 review worktree 實跑,exit 0 零輸出;sem CLI 未安裝)
**Codex preset (2.98)**: 未詢問(codex CLI 不存在,中性/對抗兩軸缺軸,preset 選擇無意義)
**Gemini 軸 (2.96)**: 未詢問(agy CLI 不存在;Flash 永久軸缺軸、Pro N-A)
**Quota (Gemini 軸)**: 未取 dashboard snapshot(軸未跑)
**審查軸狀態**: primary(python-reviewer ×1 + typescript-reviewer ×2 chunks)PASS(逐檔 accounting 齊,含一輪 4.5 repair);domain security-reviewer PASS(觸發:新 client WebSocket 入站訊息處理;3 條 LOW);spec-compliance N-A(gate SKIPPED);Codex 中性 FAIL(CLI 不存在);Codex 對抗 FAIL(CLI 不存在);Gemini Flash FAIL(CLI 不存在);Gemini Pro N-A(opt-in 未啟用且 CLI 不存在);cross-axis verification FAIL → 以同軸替代驗證執行(主 session 對全部 21 條逐條機制核實:#1/#2/#4/#9 以 code trace 或 grep 實證,其餘對 reviewer 附的 search-proof / 引文逐條對照);C4 N-A(gate SKIPPED)
**校準套用**: 無作者校準檔(loger.md 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master)
**worktree**: C:\side-project\copycat\.worktrees\review-pr-187
**worktree HEAD**: b58ee057994456c05435c1f6ae0ac20468f4a6a5

**Report generation**: sha256:278cb9f4d392bcddae8f350a926390e7af6ed0492d4065f304aaa37dc60f1952

---
## [完整證據副檔](pr-187-review.audit.md)
### finding_uid 索引
[cb04f1c6880ac5531ee8](pr-187-review.audit.md#發現總覽) · [ac4765f6c15215e28935](pr-187-review.audit.md#發現總覽) · [26ad7615d01370fe8d27](pr-187-review.audit.md#發現總覽) · [c63bc17ebb3e841fa1b9](pr-187-review.audit.md#發現總覽) · [751b183a0ee40cb47c50](pr-187-review.audit.md#發現總覽) · [f4e0427c55e1b17e51c1](pr-187-review.audit.md#發現總覽) · [2ba98fd69cc05a9ae124](pr-187-review.audit.md#發現總覽) · [f00b899b80327bdf07d9](pr-187-review.audit.md#發現總覽) · [f664ee3365645e262820](pr-187-review.audit.md#發現總覽) · [4a895a903e6f162a5aef](pr-187-review.audit.md#發現總覽) · [84fe0f9d947b332a501f](pr-187-review.audit.md#發現總覽) · [a3eb030f14441a117199](pr-187-review.audit.md#發現總覽) · [75ed8fd5737e4cd4f7b1](pr-187-review.audit.md#發現總覽) · [3b4bc6ff576cc4cbb6e2](pr-187-review.audit.md#發現總覽) · [cf2f0c67ce3dc8f8066d](pr-187-review.audit.md#發現總覽) · [34877c585721522367e7](pr-187-review.audit.md#發現總覽) · [9eec07af491940003ac8](pr-187-review.audit.md#發現總覽) · [54aa8df73e77a72c87ed](pr-187-review.audit.md#發現總覽) · [9aeacfa532b33dce1243](pr-187-review.audit.md#發現總覽) · [41b0576747958b0b1177](pr-187-review.audit.md#發現總覽) · [ddaa16a5d0309c90517a](pr-187-review.audit.md#發現總覽)
## React-doctor 機械掃描
- `react-doctor/no-high-complexity-react-function` · `src/components/stock/StockPage.tsx:78`(工具判「新引入」)。CC 判定:master 基準全量掃描(`npx react-doctor@latest --no-telemetry` 於主 tree,`StockPage.tsx:72` 同 rule 已在 baseTotalCount 10 內)→ 同函式行號位移;本 PR 對該元件加了兩個 handler 分支(側欄 onSelect 未分組分支、SignalRail onSelect 切組),複雜度小幅上升但仍是既有 warning。建議級別:參考用(不另列 finding;與模型 finding 無重合)。工具修法提示:抽 `useGroupNavigation`/handler 到 hook 可降 StockPage 的分支數,屬既有債,不在本 PR 範圍。
## 發現總覽
| # | 問題 | 嚴重度(原 → 校正) | 複查(同軸替代驗證) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 快照的 `seq` 領先尚未 flush 的打包窗:`ingest` 先推 `state.seq`、item 進 `_pending_ticks`、0.1 s 後才送;窗內回應的 `group-state` / `state` 快照 seq 比瀏覽器已收的多 k 筆 → 下一則打包首筆 `seq ≤ acc.seq` 判跳號 → 卡片單檔重拉 / 主圖**全量** refetch(含 tape),成功路徑無節流;60 s 重播種 × 活躍檔 = 每輪額外請求,正打在本 PR 動機上(reviewer python ×1 + typescript ×2 同根因三處) | MEDIUM → MEDIUM | CONFIRMED(主 session code trace:stock_engine.py 1266 `state.ingest` → 1270 append → 1290 `call_later`;stock_state.py `light_snapshot`/`snapshot` 讀 `self.seq` 同步;前端兩處 `seq !== acc.seq + 1` 對回退不分辨;修前單筆 `_publish` 同步送、窗 ≈ 0) | Should Fix | `auto-fix` | 後端 `group_snapshot()`/`snapshot()` 取值前先 `_flush_ticks()`(冪等)+ 前端「小幅回退(`acc.seq − seq` < `_BACKFILL_SEQ_MARGIN`)當已套用丟棄、大跳仍 refetch」,兩處局部 |
| 2 | 群組檢視下點側欄「盤前篩選」區段的列:側欄帶組名 → `selectGroup("盤前篩選")` → `resolveGroupPick` 濾掉後 fallback 第一個可見群組 → 圖牆跳到不相干的組、點的檔不在牆上、localStorage 寫入永遠解析不到的名字;同 PR 的訊號路徑對盤前篩選有明確政策(`groupForCode` 排除 → 不切),兩入口不一致 | MEDIUM → MEDIUM | CONFIRMED(主 session 對照 WatchlistSidebar.tsx:501 `onSelect(code, group)` 帶區段名;StockPage.tsx:272 無條件 `selectGroup`;watchlist-model.ts `resolveGroupPick` 對盤前篩選走 `visible[0]` fallback) | Should Fix | `auto-fix` | 側欄分支比照 `groupForCode`:`group === SCREEN_GROUP_NAME` 只換右欄不切組,一行 + 一條測試 |
| 3 | GroupGridView → `setTickView` 這條線零測試:`grep -rn "setTickView\|tick-stream" frontend/src --include=*.test.*` 只命中 `useStockStream.test.ts`(測消費端)與 `emitTicks` 三處;刪掉 GroupGridView.tsx 兩支 effect 全套仍綠,而 prod 症狀正是 CLAUDE.md §4 記的「圖牆只剩 60 s 輪詢、逐筆靜默消失、零錯誤訊號」—— 整個 feature 的唯一開關 | MEDIUM → MEDIUM | CONFIRMED(主 session grep 同結果;verification.md §6 US8 對「切群組即換集合」引的是 hook 與 route 測試,元件層確無) | Should Fix | `auto-fix` | GroupGridView.test 加一案:`subscribeTickView` 收集,掛載 `["2330","2317"]`、切未分組換集合、unmount `[]`(先 `resetTickStream()`) |
| 4 | 「藏盤前篩選」實際兩份實作:`visibleGroups` 是 module-private,pill 清單 `GroupGridView.tsx:395` 自己再 `g.name === SCREEN_GROUP_NAME ? [] : …` 濾一次 —— 改成「藏兩組」只改一邊,pill 列 A、解析回 B,兩邊都不報錯;正是 std F-03 抽 helper 要擋的漂移形狀 | MEDIUM → MEDIUM | CONFIRMED(主 session grep `SCREEN_GROUP_NAME` 非測試命中:constants / watchlist-model ×3 / GroupGridView.tsx:395) | Should Fix | `auto-fix` | export `visibleGroups`,pill items 由它 map;局部 |
| 5 | `TestStockWsView` 以 `time.sleep(0.1)` 賭 view 登記落地;沒落地時 2317 不在 `_tick_targets` → 永遠沒有 ticks 打包 → starlette TestClient `receive_json()` 無 timeout(pyproject 無 pytest-timeout)→ **suite hang 而不是紅**;同測試除名段已示範正確 poll(`stock._views` 50×0.02 s),三處 sleep 同病 | MEDIUM → MEDIUM | CONFIRMED(主 session 逐字對照 test_stock_routes.py 999–1005 vs 1007–1011;pyproject `[tool.pytest.ini_options]` 無 timeout) | Should Fix | `auto-fix` | 登記段改 poll `stock._views` / `_tick_targets` 含目標碼再灌報價;`_next_of_type` 加上限已在(12 則),補 timeout 式 poll |
| 6 | `test_view_does_not_touch_the_subscription_pool` 會空過:只斷言 `fake.subscribed` 沒變,無正控確認 view 真的被處理 —— 把 `relay(on_message=…)` 整段拿掉照樣綠(池本來就不會變),區分不了「有處理沒碰池」與「根本沒處理」 | MEDIUM → MEDIUM | CONFIRMED(主 session 讀 test_stock_routes.py 1013–1021:無 `_views` / ticks 斷言) | Should Fix | `auto-fix` | 先 poll 到 `stock._views` 非空(或收到含目標碼的 ticks)再斷言池不變 |
| 7 | `tick_flush_secs` 接線層沒釘(grep `tick_flush_secs\|_pending_ticks\|_tick_flush_timer\|_tick_targets` 於 tests/ 為 0):同 repo 已有先例 `test_prod_wiring_keeps_default_flush_interval`(五檔 0.1 s)並寫明理由;`create_app` 若順手傳 1.0 → 圖牆逐筆慢一秒、全綠。另 `close()` 新增的 timer cancel + `_pending_ticks.clear()` 無測試 | MEDIUM → MEDIUM | CONFIRMED(主 session grep 同結果;test_capital_api.py:1134 先例存在) | Should Fix | `auto-fix` | 補 `create_app` 出的 engine `_tick_flush_secs == 0.1` + close 後 pending 不再 publish 兩案 |
| 8 | 丟包 WARNING 只印「本窗第一筆」的累計值(丟 7 筆 → log 說 `dropped=1`,既有測試逐字證實),`dropped` 全 repo 只有 ws.py 與該測試讀、無 `/api/health` 或 WS payload 轉出(對照 engine.py `queue_dropped` 進 snapshot 的樣板)→ next-time 寫的「盤中看 dropped」看得到有無、看不到量;change-spec §2.3 指定的「丟最舊 n 則」也未實作;且「窗到期後重記」分支零測試(`DROP_WARN_WINDOW_SECS` 改 1e9 突變體全綠 —— 節流從降噪變靜默正是失效樣態) | MEDIUM → MEDIUM | CONFIRMED(主 session 讀 ws.py 76–88 + test_capital_api.py 1098–1117;grep `dropped` 全 repo 三處) | Should Fix | `auto-fix` | 加 `_dropped_in_window` 於下一則 WARNING 印本窗數 + `dropped` 掛 `/api/health`;測試 monkeypatch `DROP_WARN_WINDOW_SECS=0` 斷言第二則 |
| 9 | 入站 `view` 的 `codes` 無長度上限:通過型別驗證後 `frozenset(codes)` + 全連線聯集重算都在 event loop 上;uvicorn 預設 `ws_max_size` 16 MB 可攜 ~10⁶ 字串、連線數無上限、view 活到斷線;`/ws/stock` 無 Origin 檢查(CORSMiddleware 只管 HTTP)→ 使用者瀏覽的任意網頁可 CSWSH 送 view 阻塞 loop(僅可用性,無資料外洩:字串只做 `in _tick_targets` 比對)。同一行的元素型別分支也無測試:刪掉 `all(isinstance(c, str) …)` 突變體全綠,`frozenset({1,2})` 進集合後圖牆整場零逐筆 | LOW → LOW | CONFIRMED(主 session 讀 app.py 2070–2074 + stock_engine.py 1721/1730;test_stock_routes 壞輸入案三格無 `codes:[1,2]`;security-reviewer 四格事實:向量 localhost(CSWSH)/ public / 攻擊者輸入 yes / plausible → impact medium × likelihood low) | Nice to Have | `auto-fix` | `len(codes) > WATCHLIST_LIMIT` 拒收 + WARNING;補 `codes:[1,2]` 與 10k 長度兩案;Origin 檢查可另議 |
| 10 | 壞 frame 每則一行 WARNING 無節流:三條驗證失敗路徑無計數、prod log append 無輪替 → 持續送壞 frame 讓 log 無界成長並洗掉真告警;同 PR `_note_drop` 對同形問題已做對(60 s 節流);log injection 本身已受 `%.80r` 保護 | LOW → LOW | CONFIRMED(主 session 讀 app.py 2062–2073 vs ws.py 76–88;__main__.py log handler append 無輪替屬既有) | Nice to Have | `auto-fix` | 比照 `_note_drop` 加 per-connection 窗節流 + 計數;斷言連送 100 則壞 frame WARNING ≤ 2 |
| 11 | 深巢狀 JSON(`'['*100000`)`json.loads` 拋 `RecursionError`(MRO 為 RuntimeError 系,不是 ValueError)→ `except ValueError` 接不住 → 例外沿 `_recv` → `relay` 尾段 `raise exc` → 連線以例外收尾,違反自陳「壞 JSON … 連線不斷」;`finally: clear_view` 仍跑、只影響發送者自己 | LOW → LOW | CONFIRMED(security-reviewer 實測 `json.loads('['*100000+']'*100000)` 拋 RecursionError;主 session 對照 ws.py relay 例外分流:非 disconnect 一律 re-raise 屬設計) | Nice to Have | `auto-fix` | `except (ValueError, RecursionError)`;斷言送深巢狀後連線仍可收下一則合法 view |
| 12 | `close()` 逐筆殘骸清理不對稱:`_loop = None` 前已 `call_soon_threadsafe` 排隊的 `_handle_quote` 在 gather 讓出時才跑 → item 進 `_pending_ticks` 卻永不排 flush、不再被清(有界殘骸非洩漏);`_views` / `_tick_targets` 未清,close 後 `set_view` 仍可寫入 | LOW → LOW | CONFIRMED(主 session 讀 stock_engine.py 423–433:`_loop = None` → cancel timer → clear → gather;1290 的 `_loop is not None` 只擋排 timer 不擋 append) | Nice to Have | `auto-fix` | close 收尾三者一起歸零,或 1270 append 前也吃 `_loop is None` 早退 |
| 13 | change-spec 兩處與實作不符:§2.1 寫「新 task `_flush_ticks_loop` 每週期 publish」,實作是 `call_later` 單發 timer(commit 與 verification 都寫對);§2.3 WARNING 格式「丟最舊 n 則(累計 N,maxsize M)」與實作字面不同 —— plan-of-record 隨 PR 入庫,下一個人 grep `_flush_ticks_loop` 會撲空 | LOW → LOW | CONFIRMED(主 session 逐字對照 change-spec §2.1/§2.3 vs stock_engine.py `_flush_ticks` / ws.py `_note_drop` 字串) | Nice to Have | `auto-fix` | 兩句就地校正或加「實作偏離」註記(§1 對 F-02 已有先例) |
| 14 | `resolveGroupPick` 的說明變孤兒:F-03 把 `visibleGroups` 插進註解與函式之間並緊接第二段 `/** */`,TS/IDE 只認緊鄰段 → `resolveGroupPick` hover 無說明、`visibleGroups` 擁有一段講別人的文件;本 repo 把註解當契約 | LOW → LOW | CONFIRMED(主 session 讀 watchlist-model.ts 60–72) | Nice to Have | `auto-fix` | 註解段搬到 `resolveGroupPick` 正上方 |
| 15 | `UNGROUPED_PICK` 的 WHY 與事實相反:註解說「不用『未分組』字面因為群組名是自由字串會撞名」,但後端 `stock_watchlist.py:46` `UNGROUPED_NAME = "未分組"` 是保留名(讀時丟棄、canonicalize 拒收),反而 `__ungrouped__` 全 repo 無任何保留;真撞名時 pill 出兩顆同 value、`resolveGroupPick` 以未分組蓋掉真群組(機率極低) | LOW → LOW | CONFIRMED(主 session grep `UNGROUPED_NAME` copycat/stock_watchlist.py 命中;`UNGROUPED_PICK` 後端零命中) | Nice to Have | `auto-fix` | 改述 WHY 為事實,或把 sentinel 列入後端保留名 |
| 16 | watchdog 放棄路徑清 `openSock` 是載重行(放棄路徑卸掉 onclose,只有這行能收 send 的門;拿掉則 `send()` 對已 close 的 socket 靜默呼叫並回 true),但新測試只走 onclose / close() 兩路,突變刪掉本行三條全綠;`send` 回傳值 prod 零消費者 | LOW → LOW | CONFIRMED(主 session 讀 ws-reconnect.ts 172–181 + test 119–143) | Nice to Have | `auto-fix` | 補一條「watchdog 放棄後 send 回 false」 |
| 17 | 播種把 `last.cum_vol` 填成 `vwapVol`:同檔明文警告兩量(TC4 累積量 vs 去重剔試撮 Σqty)同名反義不可混用;`applyTick` 之後一路累加誤差;目前圖牆無 `cum_vol` 顯示點,是潛在陷阱非現行 bug,但與同段「vwap 不可得時分子取 0(不冒充)」原則不一致 | LOW → LOW | PARTIAL(機制屬實;主 session grep `cum_vol` frontend/src 唯一渲染 StockPage.tsx 主圖走 `fromSnapshot`,卡片零消費者 → 現況零症狀) | Nice to Have | `auto-fix` | 留 0,或 `GroupLikeSnapshot` 帶真 `cum_vol` |
| 18 | `CardIntradayChart` 的 `code` prop 已無讀者(函式簽名不再解構),介面仍宣告、每張卡照傳;後續讀者會以為圖以 `code` 為鍵。注意 memo test 的 `byCode` 探針靠這個 prop | LOW → LOW | CONFIRMED(主 session 讀 CardIntradayChart.tsx 20 / 37–44;GroupGridView.tsx 457 照傳) | Nice to Have | `auto-fix` | 刪 prop,memo test 探針改讀 `accum.code` |
| 19 | 手上就有 `codes`,卻用 csv 字串再 `split` 還原(GroupGridView `setTickView`;`useGroupLiveAccums` 播種迴圈同型);本 repo 沒裝 exhaustive-deps,`setTickView(codes)` 配 `[csv]` 合法,少一次往返與「代號含逗號就壞」的隱含前提 | LOW → LOW | CONFIRMED(主 session 讀 GroupGridView.tsx 327–330、useGroupLiveAccums.ts 73;GroupGridView.tsx:351 註解自述無 exhaustive-deps) | Nice to Have | `auto-fix` | 兩處改用 `codes` |
| 20 | `useGroupLiveAccums.test.tsx:134` 尾註「重拉期間到的 21、22 → 落地後重放」指涉的是下一案;本案送 13、14 並以 seq 20 快照落地,pending 全被丟棄 | LOW → LOW | CONFIRMED(主 session 逐字對照 134 vs 137–150) | Nice to Have | `auto-fix` | 刪那行註解 |
| 21 | 「unmount 後 setTickView 不再送」對 `unsubView` 是 vacuous:cleanup 同時跑 `unsubView()` 與 `conn.close()`,而 `close()` 把 `openSock` 設 null → `send` 早退回 false;註掉 `unsubView()` 照樣綠,真失效樣態(bus 永久持有已卸載 closure、多次掛載一則 view 送多次)沒被釘 | LOW → LOW | CONFIRMED(主 session 對照 ws-reconnect.ts 236–243 `close()` 清 openSock;useStockStream.test.ts 1072–1078) | Nice to Have | `auto-fix` | mount 兩次後 `setTickView` 一次斷言恰送一則(舊 listener 若在會多送),並以註掉 `unsubView` 應變紅做突變驗證 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: cb04f1c6880ac5531ee8 action=auto-fix
F-02 finding_uid: ac4765f6c15215e28935 action=auto-fix
F-03 finding_uid: 26ad7615d01370fe8d27 action=auto-fix
F-04 finding_uid: c63bc17ebb3e841fa1b9 action=auto-fix
F-05 finding_uid: 751b183a0ee40cb47c50 action=auto-fix
F-06 finding_uid: f4e0427c55e1b17e51c1 action=auto-fix
F-07 finding_uid: 2ba98fd69cc05a9ae124 action=auto-fix
F-08 finding_uid: f00b899b80327bdf07d9 action=auto-fix
F-09 finding_uid: f664ee3365645e262820 action=auto-fix
F-10 finding_uid: 4a895a903e6f162a5aef action=auto-fix
F-11 finding_uid: 84fe0f9d947b332a501f action=auto-fix
F-12 finding_uid: a3eb030f14441a117199 action=auto-fix
F-13 finding_uid: 75ed8fd5737e4cd4f7b1 action=auto-fix
F-14 finding_uid: 3b4bc6ff576cc4cbb6e2 action=auto-fix
F-15 finding_uid: cf2f0c67ce3dc8f8066d action=auto-fix
F-16 finding_uid: 34877c585721522367e7 action=auto-fix
F-17 finding_uid: 9eec07af491940003ac8 action=auto-fix
F-18 finding_uid: 54aa8df73e77a72c87ed action=auto-fix
F-19 finding_uid: 9aeacfa532b33dce1243 action=auto-fix
F-20 finding_uid: 41b0576747958b0b1177 action=auto-fix
F-21 finding_uid: ddaa16a5d0309c90517a action=auto-fix
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 快照的 seq 跑在打包前面,卡片一重播種就多打一輪重拉
**File**: copycat/server/stock_engine.py
**Line**: 1741

**Comment**:
```
ingest 先把 state.seq 推到 101、item 才進 _pending_ticks 等 0.1 s 後送;這 100 ms 內任何
/api/stock/group-state 或 /api/stock/state 回的快照 seq 都是 101,而瀏覽器手上還停在 100。
下一則打包送來的正是 seq=101 → 前端 `item.seq !== acc.seq + 1`(101 ≠ 102)判跳號 →
卡片單檔重拉、主圖是整份 refetch 含 tape,成功路徑沒有任何節流。
60 s 輪詢重播種 × 活躍檔數,開盤就是每輪多好幾發。資料不會錯(重拉後重放),但這正好打在
「卡片不卡」的動機上。改前單筆 tick 是 ingest 後同步 _publish,窗 ≈ 0,這是本 PR 新開的窗。

兩邊各補一行就好:
- 後端 group_snapshot() / snapshot() 取值前先 self._flush_ticks()(已冪等:首行卸 timer、空即早退),
  快照 seq 恆等於「已送出的最後一筆」;
- 前端 useStockStream / useGroupLiveAccums 的跳號判斷把「小幅回退」(acc.seq − item.seq 小於
  _BACKFILL_SEQ_MARGIN 1000)當已套用重複直接丟,大跳(rollover 歸零 / 回補 +1000)才 refetch。
```
#### #2 群組檢視下點側欄「盤前篩選」的列,圖牆會跳到不相干的第一組
**File**: frontend/src/components/stock/StockPage.tsx
**Line**: 272

**Comment**:
```
側欄的列會帶自己的區段名,盤前篩選那段點下去就是 selectGroup("盤前篩選");
resolveGroupPick 把它濾掉之後 fallback 第一個可見群組 → 圖牆跳到「半導體」,
你點的那檔根本不在牆上,localStorage 還記了一個永遠解析不到的名字。
同一支 PR 的訊號路徑(groupForCode)對盤前篩選是「排除 → 回 null → 不切」,兩個入口不一致。

比照過來:
  if (view !== "group" || group === undefined || group === SCREEN_GROUP_NAME) return;
  selectGroup(group === null ? UNGROUPED_PICK : group);
StockPage.test 補一格「點盤前篩選區段的列 → onSelect 有、pill 不動」。
```
#### #3 GroupGridView 送 view 的那兩支 effect 沒有任何測試,拆掉整套還是綠
**File**: frontend/src/components/stock/GroupGridView.test.tsx
**Line**: 需人工確認（anchor 未在綁定來源中比中或證據 binding 失效）

**Comment**:
```
(缺測試型 finding、無可錨定行:對應實作 GroupGridView.tsx:328-331,建議放在 describe
「GroupGridView pill:藏盤前篩選 + 未分組(T5)」旁邊。)
grep setTickView / tick-stream 在 *.test.* 只命中 useStockStream.test(測消費端)——
沒有任何測試斷言「掛載送成員、換組換集合、卸載送 []」是由 GroupGridView 發出的。
把 GroupGridView.tsx 那兩支 effect 刪掉,全套測試照綠,prod 症狀就是 CLAUDE.md §4 寫的
「圖牆只剩 60 s 輪詢、逐筆靜默消失、零錯誤訊號」—— 這是整個 feature 的唯一開關。

補一案:
  beforeEach resetTickStream();
  const seen: string[][] = []; const off = subscribeTickView((c) => seen.push([...c]));
  掛載 → expect(seen.at(-1)).toEqual(["2330","2317"]);
  點「未分組」pill → toEqual(["3231","2454"]);
  unmount → toEqual([]);
```
#### #4 「藏盤前篩選」其實有兩份實作,改一邊另一邊不會跟
**File**: frontend/src/lib/watchlist-model.ts
**Line**: 70

**Comment**:
```
visibleGroups 沒 export,GroupGridView 的 pill 清單(:395)自己又寫了一次
`g.name === SCREEN_GROUP_NAME ? [] : […]`。JSDoc 說「唯一一份解析」,實際是兩份 ——
哪天要多藏一組,pill 列得出 A、resolveGroupPick 回 B,兩邊都不會報錯。

export visibleGroups,pill items 改成
  ...visibleGroups(groups).map((g) => ({ value: g.name, label: g.name }))
就收成一份。
```
#### #5 view 登記用 sleep(0.1) 賭落地,沒落地整個 suite 會 hang 不是紅
**File**: tests/server/test_stock_routes.py
**Line**: 999

**Comment**:
```
登記走 relay 的 _recv task,這裡 time.sleep(0.1) 之後就灌報價、等 ticks。慢機器上沒落地 →
2317 不在 _tick_targets → 永遠不會有 ticks 打包 → starlette TestClient 的 receive_json()
沒有 timeout(pyproject 也沒 pytest-timeout)→ 整個 suite 停住。
同一支測試下面除名段已經是對的寫法(poll stock._views 最多 50×0.02 s),登記段照抄:

  for _ in range(50):
      if "2317" in stock._tick_targets: break
      time.sleep(0.02)
  assert "2317" in stock._tick_targets
三處 sleep 同病。
```
#### #6 「view 不碰訂閱池」這條測試把處理整個拿掉也會綠
**File**: tests/server/test_stock_routes.py
**Line**: 1019

**Comment**:
```
只斷言 fake.subscribed 沒變 —— 池本來就不會變。relay(on_message=…) 整段拿掉、
set_view 完全不實作,這條照樣綠;它分不出「有處理但沒碰池」跟「根本沒處理」。

先 poll 到 stock._views 非空(或收到一則含 2330 的 ticks)當正控,再斷言池不變。
```
#### #7 tick_flush_secs 的接線層沒釘,順手傳 1.0 圖牆慢一秒測試全綠
**File**: tests/server/test_stock_engine.py
**Line**: 4033

**Comment**:
```
grep tick_flush_secs / _pending_ticks / _tick_flush_timer 在 tests/ 是 0 命中。同 repo 早有一模一樣
的先例 test_prod_wiring_keeps_default_flush_interval(五檔 0.1 s,理由寫得很清楚:接線處順手傳個
1.0 盤中五檔慢一秒而測試全綠)—— 逐筆打包是同一種危險。close() 新增的 timer cancel +
_pending_ticks.clear() 也沒測,突變刪掉不會紅。

補兩案:create_app 出的 stock engine `_tick_flush_secs == 0.1`;close 後灌 tick 不再有 ticks publish。
```
#### #8 丟包 WARNING 一窗只印第一筆,dropped 沒地方讀得到量
**File**: copycat/server/ws.py
**Line**: 79

**Comment**:
```
_note_drop 首筆就記 log 然後靜音 60 s,所以一場只在單一窗內的爆量(= 開盤瞬間,正是要抓的)
log 永遠是 dropped=1;既有測試逐字證實(丟 7 筆、WARNING 1 則、訊息裡是 1)。
dropped 全 repo 只有 ws.py 自己跟那條測試讀 —— /api/health、任何 WS payload 都沒轉出
(engine.py 的 queue_dropped 是進 snapshot 的),next-time 寫的「盤中看 dropped」看得到有無、看不到量;
change-spec §2.3 說的「丟最舊 n 則」也沒做。窗到期後重記那條分支零測試,DROP_WARN_WINDOW_SECS 改 1e9 全綠。

加 _dropped_in_window,下一則 WARNING(或窗到期)印本窗數;dropped 掛進 /api/health。
測試 monkeypatch DROP_WARN_WINDOW_SECS=0 斷言第二則會出現。
```
#### #9 view 的 codes 沒長度上限,元素型別那半也沒測試
**File**: copycat/server/app.py
**Line**: 2071

**Comment**:
```
過了 list-of-str 驗證就 frozenset(codes) + 全連線聯集重算,都在 event loop 上;uvicorn 預設一則
frame 16 MB、連線數沒上限、view 活到斷線。/ws/stock 沒 Origin 檢查(CORSMiddleware 只管 HTTP),
瀏覽器裡任何網頁都能 new WebSocket("ws://127.0.0.1:8721/ws/stock") 送 view 把 loop 卡住 ——
只有可用性影響、沒資料外洩(字串只拿去 in _tick_targets 比對),所以 LOW。
另外 `all(isinstance(c, str) …)` 那半刪掉突變體全綠:frozenset({1,2}) 進集合後圖牆整場零逐筆、零訊號。

  if len(codes) > WATCHLIST_LIMIT: WARNING + return
補 codes:[1,2] 與 10k 長度兩案(拿掉上限該紅)。Origin 檢查另議。
```
#### #10 壞 frame 每則一行 WARNING,同 PR 的 _note_drop 有節流這裡沒有
**File**: copycat/server/app.py
**Line**: 2065

**Comment**:
```
三條驗證失敗路徑各記一則 WARNING、無計數無節流,prod log 是 append 無輪替 —— 持續送壞 frame
就是 log 無界成長 + 真告警被洗掉。同一支 PR 的 ws.py _note_drop 對同形問題已用 60 s 窗做對了。
(log injection 本身 `%.80r` 走 repr 已轉義並截 80 字,不用擔心。)

比照 _note_drop 加 per-connection 窗節流 + 計數;斷言連送 100 則壞 frame,caplog WARNING ≤ 2。
```
#### #11 深巢狀 JSON 丟的是 RecursionError,except ValueError 接不住、連線會斷
**File**: copycat/server/app.py
**Line**: 2064

**Comment**:
```
json.loads('['*100000 + ']'*100000) 拋 RecursionError(RuntimeError 系,不是 ValueError)→
一路冒到 relay 尾段 raise exc → ws_stock 的 except WebSocketDisconnect 不命中 → 連線以例外收尾,
跟 docstring 自己寫的「壞 JSON … 連線不斷」不符。finally 的 clear_view 還是會跑,只影響發送者自己。

  except (ValueError, RecursionError):
斷言送深巢狀後連線仍能收下一則合法 view 並生效。
```
#### #12 close() 清了 timer 跟 pending,但 _views / _tick_targets 沒清、pending 還會被回填
**File**: copycat/server/stock_engine.py
**Line**: 430

**Comment**:
```
_loop = None 之前已經 call_soon_threadsafe 排進去的 _handle_quote,要到 await gather 讓出時才跑 ——
那時 1290 的 `_loop is not None` 不成立,item 進了 _pending_ticks 卻永遠不排 flush、也不再被清
(有界、engine 隨後就棄,是殘骸不是洩漏)。_views / _tick_targets 同樣沒歸零,close 後 set_view 仍寫得進去。

close 收尾把三者一起歸零,或在 1270 append 前也吃 `_loop is None` 早退,讓「close 後不再累積」是單一不變式。
```
#### #13 change-spec 寫的是 `_flush_ticks_loop`,實作是 call_later —— 下一個人 grep 會撲空
**File**: .claude/mod/group-grid-ticks/change-spec.md
**Line**: 40

**Comment**:
```
§2.1「新 task _flush_ticks_loop 每週期非空才 publish」— 出貨的是 call_later 單發 timer(閒時零喚醒,
commit 24f77c5f 跟 verification §6 都寫對了);§2.3 的 WARNING 格式「丟最舊 n 則(累計 N,maxsize M)」
跟 ws.py 字面也不同。這份是隨 PR 入庫的 plan-of-record,照 §1 對 F-02 的做法加一句「實作偏離」就好。
```
#### #14 resolveGroupPick 的說明被插隊,現在掛在 visibleGroups 身上
**File**: frontend/src/lib/watchlist-model.ts
**Line**: 69

**Comment**:
```
60–68 那段(可選集合 / fallback 次序 / 唯一一份解析)講的是 resolveGroupPick,
但 visibleGroups 插進了註解與函式之間、又緊接第二段 /** */。IDE 只認緊鄰段:
resolveGroupPick hover 沒說明,visibleGroups「擁有」一段講別人的文件。搬到 resolveGroupPick 正上方。
```
#### #15 UNGROUPED_PICK 的「為什麼」跟後端事實相反
**File**: frontend/src/lib/constants.ts
**Line**: 119

**Comment**:
```
註解說不用「未分組」字面是怕使用者取同名撞掉虛擬項 —— 但 copycat/stock_watchlist.py:46 的
UNGROUPED_NAME = "未分組" 正是後端保留名(讀時丟棄、canonicalize 拒收),反而 __ungrouped__
全 repo 沒任何保留。真撞名(使用者手打這串)時 pill 會出兩顆同 value、resolveGroupPick 用未分組
蓋掉真群組。機率極低,但 WHY 反了會誤導下次改動 —— 改述成事實,或把 sentinel 一併列入後端保留名。
```
#### #16 watchdog 放棄那條路清 openSock 是載重行,但沒測試蓋到
**File**: frontend/src/lib/ws-reconnect.ts
**Line**: 177

**Comment**:
```
放棄路徑先卸掉 onclose,所以只剩這行能收 send 的門;拿掉它,重連 timer 燒到之前
`openSock === current` 仍成立,send() 對已 close 的 socket 呼叫並回 true(WebSocket.send 在
CLOSING/CLOSED 不丟例外,靜默吞)。新測試只走 onclose / close() 兩路,刪掉這行三條全綠。
順帶:send 的 boolean 回傳 prod 沒人讀(useStockStream 不看回傳)。

補一條「watchdog 放棄後 send 回 false」(推 35 s 靜默讓它放棄,再 send)。
```
#### #17 播種把 last.cum_vol 填成 vwapVol —— 本檔自己警告過的兩個量混用
**File**: frontend/src/lib/stock-accum.ts
**Line**: 358

**Comment**:
```
同檔 209–211 / 238–242 反覆講 cum_vol(TC4 當日累積量)跟 vwap_vol(去重剔試撮 Σqty)
同名反義、誤用不報錯只靜默偏移;這裡把後者填進前者,applyTick 之後一路 `cum_vol + q` 累加帶著跑。
目前圖牆沒有 cum_vol 顯示點,所以是陷阱不是現行 bug —— 但改前的 0 是誠實佔位,現在是像模像樣的錯數字,
跟同段「vwap 不可得時分子取 0(不冒充)」的原則不一致。留 0,或讓 GroupLikeSnapshot 帶真 cum_vol。
```
#### #18 CardIntradayChart 的 code prop 已經沒人讀,介面還留著、每張卡照傳
**File**: frontend/src/components/stock/CardIntradayChart.tsx
**Line**: 20

**Comment**:
```
換成吃 accum 之後函式簽名不再解構 code,但 Props 仍宣告、GroupGridView 仍照傳,TS/eslint 都不會叫。
留著的成本是讀者以為圖以 code 為鍵(其實只吃 accum,StockAccum 自帶 code)。
刪 prop;memo test 的 byCode 探針目前靠這個 prop,改成讀 accum.code。
```
#### #19 手上就有 codes,卻拿 csv 再 split 一次
**File**: frontend/src/components/stock/GroupGridView.tsx
**Line**: 329

**Comment**:
```
csv 的用途是穩定 deps,傳給 setTickView 的值不必從字串還原 —— 本 repo 沒裝 exhaustive-deps
(:351 註解自述),`setTickView(codes)` 配 `[csv]` 完全合法,少一次往返、也少一個「代號含逗號就壞」
的隱含前提。useGroupLiveAccums.ts:73 的 `for (const code of csv.split(","))` 同型,同一個 memo 內 codes 就在作用域裡。
```
#### #20 測試尾註講的是下一案的情節
**File**: frontend/src/hooks/useGroupLiveAccums.test.tsx
**Line**: 134

**Comment**:
```
這案送的是 13、14 並以 seq 20 的快照落地,pending 全被 `seq > snap.seq` 丟掉;
「重拉期間到的 21、22 → 落地後重放」是下一案(137–150)的事。刪掉這行,免得讀者以為本案蓋了重放。
```
#### #21 「unmount 後不再送」這案拿掉 unsubView 也會綠
**File**: frontend/src/hooks/useStockStream.test.ts
**Line**: 1077

**Comment**:
```
unmount 的 cleanup 同時跑 unsubView() 跟 conn.close(),而 close() 把 openSock 設 null →
send 在呼叫 openSock.send 前就 return false。所以註掉 useStockStream.ts:544 的 unsubView(),
`expect(ws.sent).toEqual([])` 照樣綠 —— 測試名宣稱的「訂閱已解除」量不到,真失效樣態
(bus 永久持有已卸載 hook 的 closure、多次掛載一則 view 送多次)沒被釘。

換探針:mount 兩次(第一個 unmount)後 setTickView 一次,斷言只送一則(舊 listener 還在會多送);
先註掉 unsubView 確認會紅再定案。
```
