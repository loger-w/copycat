# PR #188 Code Review 比較報告 · SHA 6cb42556
**Report projection schema**: 1

**PR**: [loger-w/copycat#188](https://github.com/loger-w/copycat/pull/188)
**標題**: fix: pr-187 review 收修 —— Should Fix #1–#8(快照前 flush / 盤前篩選列不切組 / 丟包窗結算)+ round-1 收修
**作者**: loger-w
**分支**: `fix/pr-187-review-followups` → `master`
**變更**: 18 檔案, +547 / -37
**審查日期**: 2026-09-03
**PR 狀態**: MERGED(post-merge 審查;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨)
**Review input basis**: source repo id `R_kgDOTsITBg` + source SHA `6cb42556cba367dc0faec7f4b43b2ebb98e87b48`;destination repo id `R_kgDOTsITBg` + destination SHA `97ab0600320acfe88ed20a9268dfc7ad89ef5c34`;`input_binding: verified`(`refs/pull/188/head` FETCH_HEAD 逐字等於 headRefOid、worktree HEAD 同值;base commit 本地可解析)
**Review continuity**: `source_continuity=CURRENT`(產報告前重抓 headRefOid 未變;分支已隨 rebase merge 刪除);`base_changed=true`(origin/master 自 `97ab0600` 前進至 `55295c65`,內容 = 本 PR 的 rebase merge 10 筆 + 後續 1 筆 docs `55295c65`);`review_context_changed=false`(head 未動,base 前進即本 PR 自身落地)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A** + Codex 對抗式 **N-A** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A**(Flash / Pro 皆不可用)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=typescript-reviewer(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(`codex` CLI 與 `~/.codex/config.toml` 皆不存在於本機);Gemini=N-A(`agy` CLI 不存在於本機)
**覆蓋 (ENH-A)**: |F|=18 → covered 10 / no-issues 8 / skipped 0 / **missed 0**(chunked: 否,8 source 檔 / 584 diff 行低於 15 檔 or 800 行門檻)
**定位 (ENH-B)**: anchored exact 10 / ambiguous 0 / **FAILED 1**(F-04 為刻意 `<none>` anchor —— 缺測試無可引行,inline 標「需人工確認」)
**React-doctor (2.97)**: 未引入新問題(既有 9 條不計;工具回報 newCount 1 / fixedCount 1 為同一條 `StockPage.tsx` 複雜度警告因 import 增一行由 78 移至 79,非 `+` 行、非新引入)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_IMPLEMENTATION_BINDING_CLAUSE)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 base `97ab0600` 執行、零輸出)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(typescript-reviewer)PASS(11 findings + 18/18 per-file accounting)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 使用者輸入處理)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 FAIL(`codex` CLI 不存在於本機、無法起軸)/ Codex 對抗式 FAIL(同上)/ Gemini Flash FAIL(`agy` CLI 不存在於本機)/ Gemini Pro N-A(未啟用、且工具不存在)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(11/11 verdict 齊、ID 集合精確相等)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-188`
**worktree HEAD**: `6cb42556cba367dc0faec7f4b43b2ebb98e87b48`

**Report generation**: sha256:fa5db1259e2c64622eaa7f533c259b3d06af25862b1484e3f931eec8ecb732c2

---

## Spec 依據

- 此 PR 未附 spec / plan 文件,按一般 PR 流程 review。PR 內兩份 `.claude/bug/pr-187-review-followups/` artifact(verification.md / code-review-round-1.json)是意圖陳述(收修來源 = `pr-187-review.md` Should Fix #1–#8),不是規範性 spec;reviewer 以其為 scope 參照、不作 normative 引用。
- spec 作者同人檢查:N-A(無 spec)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_IMPLEMENTATION_BINDING_CLAUSE`、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool call count=N-A(未派);0 clauses / 0 findings / 0 observations / 0 invalidated。
- Author calibration(Step 2.2):無作者校準檔(`xu-min-yu.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

provenance: N-A(base = master,18 檔全 authored)。

| 檔案 | 類型 | 說明 |
|---|---|---|
| `copycat/server/ws.py` | 修改 | `WsBroadcaster.window_dropped` 改為「本窗內筆數」;新增 `_settle_drop_window()` 掛 `publish()` 入口,窗到期印「上一窗共丟 N 則」(N > 1)並歸零 |
| `copycat/server/stock_engine.py` | 修改 | `snapshot()` / `group_snapshot()` 取值前 `_flush_ticks()`(取消在飛 timer);docstring 補「會 publish、只能在 loop 上」 |
| `frontend/src/lib/stock-accum.ts` | 修改 | 新增 `seqsByCode` / `isSeededDuplicate`(快照已含重複丟棄、rollover 型回退仍重拉) |
| `frontend/src/hooks/useStockStream.ts` | 修改 | 主圖 `ticks` 分支接 `isSeededDuplicate` |
| `frontend/src/hooks/useGroupLiveAccums.ts` | 修改 | 群組卡片 `ticks` 分支接 `isSeededDuplicate` |
| `frontend/src/components/stock/StockPage.tsx` | 修改 | 側欄點列:圖牆看不到的群組(盤前篩選)不切組,判定走 `visibleGroups` |
| `frontend/src/components/stock/GroupGridView.tsx` | 修改 | `subscribeTickView` 移到 conn 之後;`EMPTY_CODES` 改名 |
| `frontend/src/lib/watchlist-model.ts` | 修改 | export `visibleGroups`,pill 清單改用同一份過濾(零行為) |
| `tests/server/test_capital_api.py` | 測試 | `TestWsBroadcasterBackpressure` 新增丟包窗結算三案 |
| `tests/server/test_stock_engine.py` | 測試 | 快照前 flush / close 取消 timer 不 publish 等案 |
| `tests/server/test_stock_routes.py` | 測試 | route 測試 `_wait_until` poll 化;`tick_flush_secs` 接線 lock |
| `frontend/src/components/stock/GroupGridView.test.tsx` | 測試 | setTickView 登記三案(掛載 / 換組 / 卸載)+ 同組不重送 |
| `frontend/src/components/stock/StockPage.test.tsx` | 測試 | 盤前篩選列不切組 |
| `frontend/src/hooks/useGroupLiveAccums.test.tsx` | 測試 | 快照已含重複不重拉 / rollover 型回退仍重拉 |
| `frontend/src/hooks/useStockStream.test.ts` | 測試 | 同上(主圖) |
| `CLAUDE.md` | 文件 | §4 補快照與打包 seq 對齊雙邊不變式、窗結算語意 |
| `.claude/bug/pr-187-review-followups/verification.md` | 新增 | gate 證據與紅→綠紀錄 |
| `.claude/bug/pr-187-review-followups/code-review-round-1.json` | 新增 | 分支自身 two-axis round-1 + 增量快篩紀錄 |

## 發現總覽

| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | CLAUDE.md §4 新增的「雙邊不變式」把「後端不 flush → 每 60 s 各白打一趟重拉」與「盲點 60 s 自癒」兩個症狀寫錯 | MED | CONFIRMED(降 LOW:純文件;逐鏈重追 —— 快照 seq 領先 ⇔ 該筆仍在 pending ⇔ 下一則打包必含 `acc.seq`,`isSeededDuplicate` 必攔;主圖無週期重播種、同 PR 的 stock-accum.ts 已改述而 §4 未跟) | Nice to Have | `auto-fix` | 純文字改述,口徑已由 stock-accum.ts:411-414 給定 |
| F-02 | 收盤那一窗的丟包規模印不出來 —— 結算只掛 `publish` 入口,收盤後 stock broadcaster 不再 publish | MED | PARTIAL(降 LOW:結構面成立 —— 唯二呼叫點皆 publish 驅動、各 engine 各持一個 broadcaster、心跳不經 broadcaster;「永遠不會出現」不成立 —— `_flush_watchlist_loop` 在試撮窗翻轉時仍 publish,程序過夜則翌日 08:30 遲印;新診斷不完整而非回歸) | Nice to Have | `ask-user` | 結算掛哪裡是設計取捨(stock 迴圈只蓋 stock 軸;`stream()` finally / 關機段才通用),且兩條前提未驗(TC4 盤後是否推價、prod 是否每日重啟) |
| F-03 | `_note_drop` 內的 `_settle_drop_window(now)` 永遠不會結算(入口已結算、同一 publish 內跨不過 60 s),且 `dropped += 1` 排在它之前埋著記帳錯窗的順序陷阱 | LOW | CONFIRMED(手推「刪 105 行」突變體:三支新測試全綠;順序陷阱已由 `累計 dropped=7` 字面斷言證實為 load-bearing) | Nice to Have | `auto-fix` | 刪一行 + docstring 標唯一呼叫點 |
| F-04 | 「窗內只有一筆就不另印」(`> 1`)這條 docstring 明寫的刻意規則零測試,`> 0` 突變體全綠 | LOW | CONFIRMED(測試側 `window_dropped` 四處全為 7 / 1 / 0 / 7,兩個結算場景皆 7;手推補案形狀可殺 `> 0`) | Nice to Have | `auto-fix` | 補一案,fixture 現成 |
| F-05 | 新測試 `test_drop_warning_first_of_window_then_window_total` 與既有 `test_drops_are_counted_and_warned_once_per_window` 劇本逐字重複 | LOW | CONFIRMED(唯一增量 `window_dropped == 7` 已在 1146 行斷言;能殺的突變體都先被 1146 殺) | Nice to Have | `auto-fix` | 改寫成 F-04 缺的單筆窗案,零覆蓋洞 |
| F-06 | `_flush_ticks` 取消 timer 的註解把「防孤兒 handle 早送新窗」寫成「省一次喚醒」 | LOW | CONFIRMED(排程點唯一且以 `is None` 守門,孤兒與新 handle 可並存;走過不取消的反事實 = 打包週期漂移;CPython `TimerHandle.cancel()` 自取消安全屬實) | Nice to Have | `auto-fix` | 註解改述,`+` 行 |
| F-07 | `/api/stock/group-state` route docstring 仍寫「唯讀 batch」,但 engine 層已會 flush + publish | LOW | CONFIRMED(app.py:1689 未動;補一站:`stock_state` route 1654-1664 同樣經 `snapshot()` 得到 flush 副作用而 docstring 未提;「每打一次多送一則」是最壞情況、pending 空時不送) | Nice to Have | `auto-fix` | 兩處 docstring 各一行 |
| F-08 | `isSeededDuplicate` 註解把 `watchlist_changed` 列成主圖自癒路徑,但該分支只 invalidate 側欄 query、不重取主圖 accum | LOW | CONFIRMED(七處 `void refetch()` 無一在該分支;主圖 accum 是 useState + 手寫 refetch,非 TanStack query;間接路徑已被「切檔」涵蓋) | Nice to Have | `auto-fix` | 刪一項或併入「切檔」 |
| F-09 | `seqsByCode` 的 per-code 分群無測試釘住 —— 換成全域 Set 的突變體全綠 | LOW | CONFIRMED(兩支 hook 測試檔所有多檔打包的 seq 皆 `> acc.seq`,守門根本沒被走到;修法預期需修正:2330:12 是前向跳號同樣重拉,判別式應為 refetch 次數 2 vs 1) | Nice to Have | `auto-fix` | 補一案,斷言改成呼叫次數 |
| F-10 | 「同一組不重送」案在 `setTickView` 兩支 effect 整個刪掉時仍通過(`before` 未斷言非零) | LOW | CONFIRMED(`subscribeTickView` 不重播現值,故 before === 0 → 綠;且 `setTickView` 內建 `sameList` 去重,連拿掉 deps 也抓不到 —— 此案兩種敘事都測不到) | Nice to Have | `auto-fix` | 加一行 `expect(before).toBe(1)` |
| F-11 | 接線層測試 `test_prod_wiring_keeps_default_tick_flush_interval` 放進範圍是「入站 view 訊息」的 `TestStockWsView` | LOW | CONFIRMED(class docstring 995-997 不涵蓋;先例 `TestWebSockets` 為通用接線類;移動不需新 fixture) | Nice to Have | `auto-fix` | 搬到 `TestStockWs` 旁或新開 `TestStockWiring` |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: c28cc0deb9b458bb094e action=auto-fix
F-02 finding_uid: 0ff152c3214a7a3aac06 action=ask-user
F-03 finding_uid: 30a75137dec1f0eedce2 action=auto-fix
F-04 finding_uid: c4eb55e3b4da258c9b2b action=auto-fix
F-05 finding_uid: 2663f70ac4f8d8e44de0 action=auto-fix
F-06 finding_uid: 546bbf27f99c0fffb44a action=auto-fix
F-07 finding_uid: b9a69834ed35883e766b action=auto-fix
F-08 finding_uid: 8e7340158b98ddcfef86 action=auto-fix
F-09 finding_uid: 37e0e08daa1e9b8cd718 action=auto-fix
F-10 finding_uid: 3e9a2390e3603ef0bd01 action=auto-fix
F-11 finding_uid: b44ae14f3312943a6046 action=auto-fix

### Inline Comments per Finding（直接複製貼到 PR review）

#### #1 §4 這段把「拿掉後端 flush 會怎樣」寫成一個不會發生的症狀

**File**: `CLAUDE.md`
**Line**: 332-334

**Comment**:
```
「後端不 flush → 每 60 s 重播種後活躍檔各白打一趟單檔重拉」推不出來:pending item 帶的是
ingest 後的 state.seq,快照回同一個 seq → 快照領先時那一筆一定還在 pending,下一則打包
必含 acc.seq,isSeededDuplicate 直接 continue、不會重拉。拿掉後端那半的真實代價是「重複
在播種前還是播種後消化」由到達次序決定,不是每輪各一發。
另外「盲點 60 s 輪詢一分鐘內修正」只對群組卡片成立 —— 主圖沒有週期重播種,這句同 PR 在
stock-accum.ts:411-413 已經改成「靠重連 / 切檔的全量 refetch」,§4 沒跟。
兩句照 stock-accum.ts 的口徑改述就好:flush = 把含 acc.seq 的那則在快照前送出、
isSeededDuplicate = 反序到達的守門,同一個 race 的兩道閘。
```

#### #2 收盤那一窗丟了多少,log 上看不到 —— 結算只在下一次 publish 才發生

**File**: `copycat/server/ws.py`
**Line**: 65-66

**Comment**:
```
_settle_drop_window 只掛在 publish 入口(_note_drop 那支進不了結算分支,見 #3)。
stock broadcaster 13:30 後沒 dirty 就不 publish,所以「13:30 集合競價丟 200 則」的規模要等
_flush_watchlist_loop 下一次試撮窗翻轉(程序過夜的話是翌日 08:30)才印得出「上一窗共丟
200 則」;當晚重啟就整個沒了。當天 log 只剩窗首那則 累計 dropped=1。
不是回歸(修前連窗總數都沒有),但 #8 想消滅的症狀搬到了當日最後一窗。
掛哪裡要你拍板:掛 stock_engine._flush_watchlist_loop(1 s 一拍)只救 stock 軸;
stream() 的 finally(client 離線)+ 關機段各補一次才通用。
未驗前提兩條:TC4 盤後定價 / 零股會不會繼續推 quote 進 stock engine(會的話窗就自己
結了)、prod 是不是每天重啟。
```

#### #3 `_note_drop` 裡那支 `_settle_drop_window(now)` 永遠走不到結算分支

**File**: `copycat/server/ws.py`
**Line**: 103-105

**Comment**:
```
publish 入口(66 行)剛用幾乎同一個 now 結算過,同一次 publish 內跨不過 60 s,所以 105 行
進去一定命中前兩個早退 —— 刪掉它三支新測試全綠。
更要緊的是順序:self.dropped += 1 排在它前面,哪天有人把入口那支拿掉,結算那則的
「累計 dropped=%d」會把這一筆(屬於新窗)算進上一窗 —— test_capital_api.py:1155 釘的
字面值 7 就是靠入口先結算才成立的。
刪 105 行就好(now 留給 _drop_warned_at = now),_settle_drop_window docstring 補一句
「唯一呼叫點 = publish 入口」。
```

#### #4 「窗內只丟一筆就不另印」這條規則沒測試 —— `> 1` 改 `> 0` 全綠

**File**: `tests/server/test_capital_api.py`
**Line**: 需人工確認（anchor 未在綁定來源中比中或證據 binding 失效）

**Comment**:
```
(缺測試、無可引行;最近封閉符號 class TestWsBroadcasterBackpressure,1055 行起)
ws.py:91 的 if self.window_dropped > 1 是 docstring 明寫的刻意規則(窗首那則已經說過了),
但兩個結算場景的 window_dropped 都是 7,> 0 / >= 1 的突變體沒有任何測試會紅。
補一案:WsBroadcaster(maxsize=1)、publish 兩則(丟一筆、一則 WARNING)、drain、
monkeypatch 窗為 0、再 publish 一則不丟的 → 斷言 len(warned) == 1 且 window_dropped == 0。
> 0 的突變體會印兩則。
```

#### #5 新的 `test_drop_warning_first_of_window_then_window_total` 跟既有那支是同一個劇本

**File**: `tests/server/test_capital_api.py`
**Line**: 1184-1200

**Comment**:
```
maxsize=3、publish 10 則、dropped == 7、warned 一則 —— 跟 1098-1117 的
test_drops_are_counted_and_warned_once_per_window 逐字一樣,唯一多的
window_dropped == 7 在 1146 行已經斷言過。能被它殺的突變體都先被 1146 殺掉。
直接把這支改寫成 #4 缺的單筆窗案,才是這個 class 現在沒有的劇本。
```

#### #6 這條註解給的理由是錯的 —— 不取消不是「多跑一次空的」,是打包週期會漂

**File**: `copycat/server/stock_engine.py`
**Line**: 1752

**Comment**:
```
快照路徑 t+0.05 flush 後把 _tick_flush_timer 設 None,t+0.06 一筆新成交就會重排 H2
(1303 行條件正是 is None),t+0.1 孤兒 H1 醒來時 _pending_ticks 已經非空 → 提早把新窗
送出去,H2 再變成下一支孤兒。cancel() 擋的是這個,不是省一次喚醒。
程式對、理由錯 —— 照現在的註解讀,下次「簡化」很容易把 cancel 拿掉而測試不紅。
改述成「不取消 → 孤兒 handle 會在下一窗到期前提早 flush,打包週期靜默漂掉」。
```

#### #7 route 層 docstring 還說這條 GET 是唯讀,現在它會對所有 WS client 推一則

**File**: `copycat/server/stock_engine.py`
**Line**: 763

**Comment**:
```
engine 這層已經誠實寫了「不再純唯讀:取值前 _flush_ticks() 會 publish」,但外層
app.py:1689 stock_group_state 的第一句還是「群組檢視的唯讀 batch」;app.py:1654-1664
的 stock_state route 同樣經 snapshot() 拿到這個副作用、docstring 也沒提。
兩處各補一句「取值前會 _flush_ticks(),pending 非空時對所有 WS client 送一則 ticks,非唯讀」
跟 engine 同口徑就好。
```

#### #8 `watchlist_changed` 不會重取主圖,註解把它列成自癒路徑會把盲點暴露時間講短

**File**: `frontend/src/lib/stock-accum.ts`
**Line**: 412

**Comment**:
```
useStockStream.ts:500-503 的 case "watchlist_changed" 只有一句
queryClient.invalidateQueries(["stock-watchlist"]) —— 那是側欄清單的 query,主圖 accum 是
useState + 手寫 refetch(),七處 void refetch() 沒有一處在這個分支。
真正會自癒的只有重連 / 切檔(自選變更導致換股也是切檔)。把 watchlist_changed 那項刪掉。
```

#### #9 `seqsByCode` 按檔分群這件事沒測試釘住 —— 換成一份全域 Set 全綠

**File**: `frontend/src/hooks/useGroupLiveAccums.test.tsx`
**Line**: 109

**Comment**:
```
seqsByCode 存在的唯一理由是各檔 seq 各算各的(每檔獨立計數器、跨檔撞號很正常),
但現有多檔打包的 seq 全都 > acc.seq,守門根本沒走到;新增四案又都是單檔。
補一案:snaps = { 2330: seq 3, 2317: seq 12 },emitTicks([item("2330", 12), item("2317", 3)])
→ 正確版兩檔都重拉(2330 前向跳號、2317 rollover 回退)= fetchMock 2 次;
全域 Set 版會把 2317:3 當快照已含吞掉 = 只 1 次。斷言次數,不要斷言「2330 照常套用」。
```

#### #10 「同一組不重送」這案在 setTickView 整支被刪掉時照樣過

**File**: `frontend/src/components/stock/GroupGridView.test.tsx`
**Line**: 296

**Comment**:
```
before = seen.length 沒先斷言非零;subscribeTickView 訂閱時不重播現值,兩支 effect 全刪
before 跟結尾都是 0 → 綠。而且 setTickView 自己有 sameList 去重,連把 [csv] deps 拿掉
這案也不會紅 —— 它敘事的兩種回歸都測不到。
加一行 expect(before).toBe(1) 就夠(掛載那次送 ["2330","2317"])。順帶:這兩支 it 標了
async 但沒 await,可拿掉。
```

#### #11 接線層測試放錯 class —— `TestStockWsView` 的範圍是入站 view 訊息

**File**: `tests/server/test_stock_routes.py`
**Line**: 1003

**Comment**:
```
class docstring(995-997)寫的是「/ws/stock 入站 view 訊息:登記 / 斷線除名 / 壞輸入 WARNING」,
這支測的是 create_app 沒覆寫 _tick_flush_secs,連 websocket 都沒開。下次要找打包週期的
測試不會往這裡看。
搬到 TestStockWs 旁邊或新開 TestStockWiring;它自己引的先例
test_capital_api.py::TestWebSockets 就是通用接線類。只用 make_client(tmp_path),搬動零成本。
```

## CC 主軸原始 findings(first-pass, context-aware)

typescript-reviewer(requested=opus)first-pass 原文(11 條 + 18/18 per-file accounting),逐字照錄:

#### F-1 CLAUDE.md §4 新增的「雙邊不變式」把兩半的失效症狀都寫錯了
severity: MEDIUM
file: CLAUDE.md
lines: 332-334
anchor:   否則回退視為 rollover 型跳號 → 重拉)是第三條分支,兩支 hook 共用。任一邊單獨拿掉都零錯誤訊號:後端不 flush → 每 60 s
category: docs-drift
problem: 兩處與程式不符。(a)「後端不 flush → 每 60 s 重播種後活躍檔各白打一趟單檔重拉」推不出來:`stock_engine.py:1300` 把 **ingest 後的** `state.seq` 寫進每一筆 pending item,而 `stock_state.py:275` 的 `snapshot()["seq"]` 就是同一個 `self.seq` —— 所以快照 seq 領先時,那筆「等於快照 seq」的 item 必然還在 `_pending_ticks` 裡,下一則打包(最多 0.1 s 後)一定含 `acc.seq` 本人,`isSeededDuplicate`(stock-accum.ts:415-421)對整串 `seq ≤ acc.seq` 回 true → `continue`,不會重拉。拿掉後端那半的真實代價是「重複要不要出現改由 WS/HTTP 到達次序決定」,不是每輪每檔各一發重拉。(b)「已知盲點 …… 60 s 輪詢重播種一分鐘內修正」只對群組卡片成立;主圖沒有週期重播種 —— 這正是 r1 spec F-03 已經在 `stock-accum.ts` 改述過的那一句,CLAUDE.md 這一段是同批新增卻沒跟著改。
impact: none at runtime。但 §4 是本 repo「拿掉哪一半會怎樣」的規範性登記處:照這段文字驗收,未來有人拿掉 `isSeededDuplicate`(真正擋住重拉的那一半)會以為後端 flush 撐得住;或反過來為了追一個永遠不會出現的「每輪各一發重拉」症狀白繞。
repro: n/a (static)
fix: 改述為「後端 flush = 把含 `acc.seq` 的那則打包在快照回應**之前**送出(重複多半在播種前就消化掉);前端 `isSeededDuplicate` = 反序到達時的守門,兩者是同一個 race 的兩道閘,不是各自獨立的必要條件」;盲點那句補「群組卡片 60 s 輪詢自癒;主圖靠重連 / 切檔的全量 refetch」(與 stock-accum.ts:411-413 同口徑)。
search_proof: Grep `\.snapshot\(|group_snapshot\(` 全 `copycat/` → 只有 `app.py:1679`(async route)與 `app.py:1715`(async route)兩個 caller;Grep `_pending_ticks` → `stock_engine.py:1283-1301` 是唯一寫入點,`"seq": state.seq` 在 1300 行。
mechanism_traced: 追了 `_handle_quote`(`stock_engine.py:1279-1306`,經 `_on_raw_threadsafe` → `loop.call_soon_threadsafe` 恆在 event loop 上)→ item 的 `seq` = ingest 後的 `state.seq`;`StockDayState.ingest`(stock_state.py:87-96)每收一筆 +1;`snapshot()` / `light_snapshot()` 回同一個 `self.seq`(stock_state.py:262 / 275)。因此「快照 seq > 已送出打包尾筆」⇔「seq 等於快照值的那筆仍在 pending」⇔「下一則打包含 acc.seq」,`isSeededDuplicate` 的 `seqsInBundle.has(accSeq)` 條件必然成立。

#### F-2 收盤那一窗的丟包規模永遠印不出來(publish 停了就不會結算)
severity: MEDIUM
file: copycat/server/ws.py
lines: 65-66
anchor:     def publish(self, msg: dict) -> None:
        self._settle_drop_window(time.monotonic())
category: correctness
problem: `_settle_drop_window` 的唯一觸發點是「下一則 publish」。`_note_drop` 那一支結算不了(見 F-3),所以整個結算依賴「窗到期之後這條 broadcaster 還會再 publish 至少一則」。收盤後這個前提不成立:stock broadcaster 的推播來源是 `_handle_quote` 的 dirty 集合與 `_flush_watchlist_loop`(`stock_engine.py:1788-1793`,dirty 為空就不 publish),13:30 之後行情停了就整條靜默。於是「13:30 集合競價爆量丟了 200 則」在 log 上只留窗首那一則 `累計 dropped=1`,「上一窗共丟 200 則」永遠不會出現 —— 這正是 review #8 要消滅的症狀,只是搬到當日最後一窗。
impact: 盤後 `grep "佇列滿" logs/server-*.log` 仍會命中(判準不變),但操作者看到的規模是 1 而不是 200 → 把「收盤瞬間佇列被打穿」誤判成「掉了一則、無所謂」。零錯誤訊號。
repro: n/a (static)。可觀測版本:讓一條 broadcaster 在窗內丟包後停止 publish 60 s 以上,log 只有窗首那一則。
fix: 讓結算不只掛在 publish —— 例如開一支 public `settle_drop_window()` 由已存在的週期迴圈(`stock_engine._flush_watchlist_loop`,1 s 一拍)呼叫,或在 `stream()` 的 `finally`(client 離線)與 app lifespan 關機段各補一次;測試補「窗到期後不再 publish → 仍印得出上一窗筆數」。
search_proof: Grep `_settle_drop_window` 全 repo → 只有 `ws.py:66`(publish 入口)與 `ws.py:105`(`_note_drop` 內,見 F-3)兩個呼叫點,沒有任何 timer / 週期任務。Grep `_publish|publish(` in `stock_engine.py` → 推播全部由 quote 事件或 dirty 迴圈驅動,無空閒心跳(心跳走 `relay._beat` 直送,不經 broadcaster,ws.py:246-250)。
mechanism_traced: 追了 `relay` 的 `_beat`(ws.py:246-250)確認心跳不經 `WsBroadcaster.publish`(docstring 明說「不佔位、不受滿了丟最舊影響」),所以「連線還在」不等於「還有 publish」;再追 `_flush_watchlist_loop`(stock_engine.py:1774-1793)確認無資料時整輪不 publish。

#### F-3 `_note_drop` 裡的 `_settle_drop_window(now)` 是一支永遠不會結算的呼叫
severity: LOW
file: copycat/server/ws.py
lines: 103-105
anchor:         self.dropped += 1
        now = time.monotonic()
        self._settle_drop_window(now)
category: quality
problem: `_note_drop` 的唯一呼叫點是 `publish`(ws.py:80),而 `publish` 在入口(ws.py:66)已經以幾乎相同的 `now` 結算過一次;一次 `publish` 內走完 clients 迴圈是微秒級,不可能跨過 60 s 的窗界。所以第 105 行進 `_settle_drop_window` 後永遠命中前兩個早退分支之一,結算分支不可達 —— 刪掉它全量測試不會紅(存活突變體)。更麻煩的是順序:`self.dropped += 1` 排在它**之前**,萬一哪天有人把 publish 入口那支拿掉(或新增第二個 `_note_drop` 呼叫端),結算那則 WARNING 的「累計 dropped=%d」會把剛剛這一筆(屬於新窗)算進上一窗的報告裡。
impact: none at runtime。維護面:兩個結算呼叫點讓這台狀態機看起來像「兩處都要理解」,而其中一處是死的。
repro: n/a (defect is on the diff line itself)
fix: 刪掉 `ws.py:105` 那一行(`now` 仍留給 `_drop_warned_at = now` 用),並在 `_settle_drop_window` docstring 標明「唯一呼叫點 = `publish` 入口」;若刻意保留防禦,至少把 `self.dropped += 1` 移到結算之後,讓報告數字與窗一致。
search_proof: Grep `_note_drop|_settle_drop_window` 全 repo → `_note_drop` 定義 ws.py:102、唯一呼叫 ws.py:80;`_settle_drop_window` 呼叫僅 ws.py:66 / ws.py:105。
mechanism_traced: 逐條走 publish→note_drop 的兩種狀態(窗開著 / 窗已結算歸零):publish 入口結算後 `_drop_warned_at` 只可能是 None 或落在窗內,兩種在 105 行都早退;唯一理論例外是 `now0 - warned_at` 恰好落在 60.0 的微秒鄰域,行為上與早退等價。

#### F-4 「窗內只有一筆就不另印」這條刻意行為零測試(`> 1` 改成 `> 0` 全綠)
severity: LOW
file: tests/server/test_capital_api.py
lines: 1055-1200
anchor: <none> — 最近的封閉符號 `class TestWsBroadcasterBackpressure`(tests/server/test_capital_api.py:1055)
category: test-coverage
problem: `_settle_drop_window` 的 `if self.window_dropped > 1:`(ws.py:91)是明文寫進 docstring 的刻意規則(「窗內只有一筆時不另印(窗首那則已經說過了)」),但三支新測試的結算場景 `window_dropped` 都是 7 —— 把 `> 1` 改成 `> 0` / `>= 1` 的突變體不會有任何測試變紅。缺的案是「一窗內只丟 1 筆 → 窗到期 → 只該有窗首那一則,不得多出『上一窗共丟 1 則』」。
impact: none at runtime(現碼行為正確)。回歸面:這條規則是「節流不洗版」的一半,漂掉的症狀是零星丟包時每次多一則重複語意的 WARNING,而盤後判準正是 `grep 佇列滿` 的行數。
repro: n/a (static)
fix: 補一案:`maxsize=1` 之類讓整窗只丟一筆(或直接設 `b.window_dropped = 1` 前置),`monkeypatch` 窗為 0 後再 `publish` 一則不丟的訊息,斷言 `warned` 長度仍為 1 且 `b.window_dropped == 0`。
search_proof: Grep `window_dropped` 全 repo → 測試側只有 `test_capital_api.py:1146 / 1157 / 1179 / 1196` 四處,值分別是 7 / 1 / 0 / 7;沒有任何一處在「值為 1 的窗到期」時斷言 log 行數。
mechanism_traced: n/a

#### F-5 新測試 `test_drop_warning_first_of_window_then_window_total` 與既有那支幾乎逐字重複
severity: LOW
file: tests/server/test_capital_api.py
lines: 1184-1200
anchor:     async def test_drop_warning_first_of_window_then_window_total(
category: test-coverage
problem: 這支的 body 與同 class 既有的 `test_drops_are_counted_and_warned_once_per_window`(1098-1117)是同一個劇本:`maxsize=3`、`publish` 10 則、斷言 `dropped == 7` 且 WARNING 只有 1 則。唯一多出來的 `assert b.window_dropped == 7`,在同批新增的 `test_drop_warning_reports_window_count_and_relogs_after_window`(1146 行)已經以同一個劇本斷言過一次。任何一個能被它殺掉的突變體(例如把 `_note_drop` 的 `self.window_dropped = 1` 拿掉)都會先被 1146 那行殺掉。
impact: none at runtime。維護成本:同一劇本三份,改丟包政策時要同步改三處。
repro: n/a (static)
fix: 刪掉這支,或把它改寫成 F-4 缺的那個「單筆窗」案 —— 那才是同 class 目前沒有的劇本。
search_proof: 逐行比對 `test_capital_api.py:1104-1112`(既有)與 `1189-1198`(新增):兩者 `WsBroadcaster(maxsize=3)` + `for i in range(10)` + `assert b.dropped == 7` + `assert len(warned) == 1` 完全相同;`assert b.window_dropped == 7` 另見 1146。
mechanism_traced: n/a

#### F-6 `_flush_ticks` 取消 timer 的理由註解把「防早熄新窗」寫成「省一次喚醒」
severity: LOW
file: copycat/server/stock_engine.py
lines: 1751-1753
anchor:             # 由快照路徑提前呼叫時 timer 仍在飛:取消它,否則到期再跑一次(空 → 早退,無害但多一次喚醒)
category: docs-drift
problem: 註解說不取消的後果是「到期再跑一次(空 → 早退,無害)」。實際上不取消會留下孤兒 handle:快照路徑在 t+0.05 flush 後把 `_tick_flush_timer` 設 None,t+0.06 來一筆新成交會**重新排一支** H2(`stock_engine.py:1303-1306` 的條件就是 `_tick_flush_timer is None`),t+0.1 孤兒 H1 醒來時 `_pending_ticks` 已經**非空**,於是提早把新窗送出並把 H2 變成下一支孤兒 —— 是打包週期漂掉,不是空跑。程式碼是對的,錯的是它給出的理由。
impact: none at runtime。風險在下一位維護者:照這條註解讀,`cancel()` 看起來只是省一次 loop 喚醒的微優化,很容易在「簡化」時被拿掉,而拿掉之後測試不會紅(打包提早送出仍是合法輸出)。
repro: n/a (static)
fix: 改述為「不取消 → 孤兒 handle 會在下一窗到期前提早把新窗 flush 出去,打包週期靜默漂掉」。
search_proof: Grep `_tick_flush_timer` in `copycat/server/stock_engine.py` → 排程點只有 1303-1306(條件 `is None`)、卸載點 1751-1754 與 `close()` 430-432,無第四處;因此孤兒 handle 與新 handle 可以並存。
mechanism_traced: 追了 CPython `asyncio` 語意兩點:(1) `TimerHandle.cancel()` 對已執行的 handle 是安全 no-op —— `_run_once` 取出後先把 `handle._scheduled = False`,`BaseEventLoop._timer_handle_cancelled` 只在 `_scheduled` 為真時累加 `_timer_cancelled_count`,故現碼「timer 回呼裡取消自己」不會污染 loop 的取消計數;(2) 反過來,未取消的舊 handle 仍在 heap 上,到期照跑 `_flush_ticks`,而該函式沒有「這支是不是我排的」判斷。

#### F-7 `/api/stock/group-state` 這條 GET route 的 docstring 還寫著「唯讀 batch」
severity: LOW
file: copycat/server/stock_engine.py
lines: 762-766
anchor:         """群組檢視的 batch 快照(SC-4)。**不 set_main、不改訂閱池。**
category: docs-drift
problem: engine 這一層很誠實地把「自 pr-187 review #1 收修起**不再純唯讀**:取值前 `_flush_ticks()` 會 publish 一則打包」寫進 docstring,但同一條路的**外層** route `copycat/server/app.py:1688-1689` 的第一句仍是「群組檢視的唯讀 batch(group-grid SC-4)」,而那正是大多數人翻 API 行為時會先讀到的一份。現在這條 GET 會對**所有** WS client 廣播一則 `ticks`。
impact: none at runtime。誤導面:讀 route docstring 的人會以為這條路可以安全地在任何情境重打(例如加一個健康檢查輪詢它),實際上每打一次就切碎一次 0.1 s 打包窗並向全體 client 多送一則。
repro: n/a (static)
fix: `app.py:1689` 那句改成「群組檢視的 batch(取值前會 `_flush_ticks()`,**非唯讀**:會對所有 WS client 送出一則 `ticks`)」,與 engine 層同口徑。
search_proof: Read `copycat/server/app.py:1687-1715` → route 為 `async def stock_group_state`,docstring 第一行仍為「群組檢視的唯讀 batch(group-grid SC-4)。」,本 PR 未動該檔。
mechanism_traced: 確認兩個 caller 都是 `async def`(app.py:1651 / 1688)→ 在 event loop 上執行,`_flush_ticks` 動 `call_later` handle 與 `asyncio.Queue.put_nowait` 都安全;engine docstring 的「只能在 event loop 上呼叫」前提成立,這一條純粹是外層文字沒跟。

#### F-8 `isSeededDuplicate` 註解把 `watchlist_changed` 列成主圖的自癒路徑,但它不會 refetch 主圖
severity: LOW
file: frontend/src/lib/stock-accum.ts
lines: 412-413
anchor:  *  單則 0.1 s 打包內的薄股跨日;群組卡片由 60 s 輪詢重播種修正,主圖無週期重播種、靠重連 / 切檔 /
category: docs-drift
problem: 註解列了三條主圖自癒路徑。前兩條成立(`useStockStream.ts:533` 重連後 `void refetch()`;`useStockStream.ts:313-322` 換 instrumentKey 時 `void refetch()`),第三條不成立:`case "watchlist_changed"` 的整個 body 只有 `queryClient.invalidateQueries({ queryKey: ["stock-watchlist"] })`(useStockStream.ts:500-503),那是側欄自選清單的 query,不會重取主圖 accum,也不會碰 `accumRef`。
impact: none at runtime。誤導面:這段是本次 r1 spec F-03 專門為了「講清楚盲點怎麼自癒」而寫的;列了一條不存在的路徑,等於把盲點的實際暴露時間(可能整個交易時段,除非使用者換股或 WS 重連)講短了。
repro: n/a (static)
fix: 刪掉 `watchlist_changed` 那一項,只留「重連 / 切檔」;或改成「切檔(含由自選變更引發的換股)」。
search_proof: Grep `watchlist_changed` in `frontend/src` → 產生點 `useStockStream.ts:500-503` 只呼叫 `invalidateQueries(["stock-watchlist"])`;Grep `void refetch()` in `useStockStream.ts` → 242 / 304 / 321 / 344 / 381 / 481 / 533,無一位於 `watchlist_changed` 分支。
mechanism_traced: 追了 `refetch` 的全部觸發點(上列七處)與 `watchlist_changed` 分支;TanStack `invalidateQueries` 的 key 是 `["stock-watchlist"]`,主圖 accum 不是 query 而是 hook 內 `useState` + 手寫 `refetch()`,兩者無耦合。

#### F-9 `seqsByCode` 的 per-code 分群無測試釘住(換成一份全域 Set 的突變體全綠)
severity: LOW
file: frontend/src/hooks/useGroupLiveAccums.test.tsx
lines: 101-113
anchor:     act(() => emitTicks([item("2330", 11), item("2317", 4), item("2330", 12)]));
category: test-coverage
problem: `seqsByCode` 存在的唯一理由就是「同一則打包內各檔的 seq 要各算各的」(每檔 seq 是獨立計數器,跨檔撞號很正常)。但所有相關測試的打包不是單檔(新增四案全是單一 code),就是多檔而 seq 不重疊(本檔 101-113 的「一則打包多檔」用 2330:{11,12} / 2317:{4})。把 `seqsByCode` 換成「回一份含全部 code 的 Set」的突變體不會有任何測試變紅。缺的案:例如 2317 的 `acc.seq = 12`、同一則打包含 `2330:12` 與 `2317:3`(2317 的 rollover 型回退)—— per-code 版本應該重拉,全域 Set 版本會把它當重複吞掉。
impact: none at runtime(現碼正確)。回歸面:突變體在 prod 的樣態是「跨檔 seq 撞號時,真正的回退被靜默吞掉」→ 主圖 / 卡片停在昨日 accum 直到重連或下一次輪詢,零錯誤訊號。
repro: n/a (static)
fix: 在本檔補一案:`snaps = { "2330": snap({ seq: 3 }), "2317": snap({ seq: 12 }) }`,`emitTicks([item("2330", 12), item("2317", 3)])`,斷言 2317 觸發一次 `fetchMock`(跳號重拉)而 2330 照常套用。
search_proof: Grep `seqsByCode|isSeededDuplicate` in `frontend/src` → 只有兩支 hook 使用(useGroupLiveAccums.ts:148 / useStockStream.ts:369),`stock-accum.test.ts` 無直接測試;逐案檢查 `useGroupLiveAccums.test.tsx`(91 / 109 / 119 / 124-146)與 `useStockStream.test.ts`(新增兩案的 items 全為 "2330"),無任何「跨檔 seq 相等」劇本。
mechanism_traced: n/a

#### F-10 「同一組不重送」那案在 setTickView 整支被拿掉時仍會通過
severity: LOW
file: frontend/src/components/stock/GroupGridView.test.tsx
lines: 296-298
anchor:     const before = seen.length;
category: test-coverage
problem: 這案的唯一斷言是 `seen.length === before`,而 `before` 沒有先被斷言為非零。若 `setTickView` 的兩支 effect(GroupGridView.tsx:328-331)整個被刪掉,`before` 與結尾都是 0,這案照樣綠 —— 它只在「有送過」的前提下才有意義。(同 describe 的第一案會抓到全刪型突變,但這案自身的敘事「不能變成每秒一則」是靠 `before > 0` 才成立的。)順帶:第 288 行手抄了一份 `new QueryClient({ defaultOptions: { queries: { retry: false } } })`,而 `@/test-utils` 的 `wrap` 存在的理由就是收斂這一行(其 docstring 明寫「個股頁五個元件測試各抄一份逐字相同的定義」)。
impact: none at runtime;測試強度與可讀性。
repro: n/a (static)
fix: 加一行 `expect(before).toBeGreaterThan(0);`(或直接 `toBe(1)`);QueryClient 若要留在案內,考慮讓 `test-utils` 多導出一支可 rerender 的 helper,避免第六份逐字複製。另 `it(...)` 標了 `async` 卻無 `await`,可拿掉。
search_proof: Grep `new QueryClient` in `frontend/src` 的 `wrap` 定義 → `frontend/src/test-utils.tsx:16` 同一行逐字存在,docstring 就是「任何一處想調 defaultOptions 都會變成『這檔的 wrap 跟別檔不一樣』」。
mechanism_traced: 追了 React effect deps:`useEffect(..., [csv])`(GroupGridView.tsx:328-330)在 `csv` 不變時不重跑,所以「不重送」由 deps 保證;但斷言形式 `toBe(before)` 對「一次都沒送」與「送了一次沒再送」不可分辨。

#### F-11 接線層測試被放進 `TestStockWsView`(該 class 的範圍是入站 view 訊息)
severity: LOW
file: tests/server/test_stock_routes.py
lines: 1003-1011
anchor:     def test_prod_wiring_keeps_default_tick_flush_interval(self, tmp_path: Path) -> None:
category: quality
problem: `TestStockWsView` 的 class docstring 把範圍界定成「`/ws/stock` 入站 `view` 訊息(#182):瀏覽器告訴後端我正在看這些檔;斷線自動除名;壞輸入只記 WARNING」。新加的這支測的是 `create_app` 沒有覆寫 `_tick_flush_secs`,與 view 訊息無關(它連 websocket 都沒開)。放這裡之後,class docstring 與內容不再對得上,而下一個要找「打包週期」相關測試的人不會往這個 class 看。
impact: none at runtime;測試可發現性。
repro: n/a (static)
fix: 移到檔內既有的接線類測試旁(或新開 `TestStockWiring`),class docstring 維持原範圍;沿用它自己引的先例 `TestWebSockets::test_prod_wiring_keeps_default_flush_interval` 的擺法。
search_proof: Read `tests/server/test_stock_routes.py:995-1012` → class docstring 995-997 界定範圍;Grep `test_prod_wiring_keeps_default_flush_interval` → 先例在 `tests/server/test_capital_api.py:1204` 的 `class TestWebSockets`(該 class 名稱本身是通用接線類,不是單一訊息型別)。
mechanism_traced: n/a

### Section B — per-file accounting (18/18)

FINDINGS: copycat/server/ws.py (F-2, F-3)
FINDINGS: copycat/server/stock_engine.py (F-6, F-7)
FINDINGS: frontend/src/lib/stock-accum.ts (F-8)
REVIEWED_NO_ISSUES: frontend/src/hooks/useStockStream.ts
REVIEWED_NO_ISSUES: frontend/src/hooks/useGroupLiveAccums.ts
REVIEWED_NO_ISSUES: frontend/src/components/stock/StockPage.tsx
REVIEWED_NO_ISSUES: frontend/src/components/stock/GroupGridView.tsx
REVIEWED_NO_ISSUES: frontend/src/lib/watchlist-model.ts
FINDINGS: tests/server/test_capital_api.py (F-4, F-5)
REVIEWED_NO_ISSUES: tests/server/test_stock_engine.py
FINDINGS: tests/server/test_stock_routes.py (F-11)
FINDINGS: frontend/src/components/stock/GroupGridView.test.tsx (F-10)
REVIEWED_NO_ISSUES: frontend/src/components/stock/StockPage.test.tsx
FINDINGS: frontend/src/hooks/useGroupLiveAccums.test.tsx (F-9)
REVIEWED_NO_ISSUES: frontend/src/hooks/useStockStream.test.ts
FINDINGS: CLAUDE.md (F-1)
REVIEWED_NO_ISSUES: .claude/bug/pr-187-review-followups/verification.md
REVIEWED_NO_ISSUES: .claude/bug/pr-187-review-followups/code-review-round-1.json

## Codex 原始 findings

N-A —— `codex` CLI 與 `~/.codex/config.toml` 皆不存在於本機,中性軸與對抗軸皆未起,零 findings。

## Gemini 原始 findings

N-A —— `agy` CLI 不存在於本機,Flash / Pro 軸皆未起,零 findings。

## CC 對非 CC 軸的複查結果(Step 4.1)

N-A —— 無非 CC 軸 finding 可複查。

## 內部複查結果(Step 4.2 之替代;同軸 code-reviewer、非跨軸證據)

code-reviewer(requested=opus)以 fresh context 對 11 條逐條做反證式驗證(機制重追 / impact / baseline-comparable / 本 PR 引入 / 修法假設 / lone-finding 提問);ID 集合與輸入精確相等、每列四個必填欄齊。**這是同軸複查,只證明「同一模型的第二雙眼睛也看到」,不構成跨軸證據。**

| # | Verdict | 原始 → 校正 severity | 本 PR 引入 | diff-only 軸抓得到 | 未驗前提 | 修法假設 |
|---|---|---|---|---|---|---|
| F-01 | CONFIRMED | MED → LOW | 是 | 否 | 無 | 全驗 |
| F-02 | PARTIAL | MED → LOW | 是 | 否 | 兩條(TC4 盤後推價 / prod 每日重啟) | 部分:stock 迴圈掛法只蓋 stock 軸;關機段能否觸及全部 broadcaster 未驗 |
| F-03 | CONFIRMED | LOW → LOW | 是 | 是 | 無 | 全驗;「移 `dropped += 1`」替代方案會動到 1155-1156 字面斷言(原 finding 未說) |
| F-04 | CONFIRMED | LOW → LOW | 是 | 是 | 無 | 全驗(手推補案可殺 `> 0`) |
| F-05 | CONFIRMED | LOW → LOW | 是 | 否 | 無 | 全驗 |
| F-06 | CONFIRMED | LOW → LOW | 是 | 否 | 無 | 全驗 |
| F-07 | CONFIRMED | LOW → LOW | 是 | 否 | 無 | 全驗;補一站 `stock_state` route 同病 |
| F-08 | CONFIRMED | LOW → LOW | 是 | 否 | 無 | 全驗 |
| F-09 | CONFIRMED | LOW → LOW | 是 | 否 | 無 | **原修法預期錯**(2330:12 是前向跳號同樣重拉);判別式改為 refetch 次數 2 vs 1 後仍可殺突變體 |
| F-10 | CONFIRMED | LOW → LOW | 是 | 是 | 無 | 全驗(主修法);次要建議 `test-utils` helper 需新 export,原 finding 已用「考慮」措辭 |
| F-11 | CONFIRMED | LOW → LOW | 是 | 是 | 無 | 全驗 |

逐條 evidence 原文(JSON,逐字照錄):

```json
[
  {
    "id": "F-1",
    "verdict": "CONFIRMED",
    "original_severity": "MEDIUM",
    "corrected_severity": "LOW",
    "severity_reason": "Docs-only: CLAUDE.md §4 wording; zero runtime effect, but §4 is this repo's normative \"remove-one-half symptom\" registry so a wrong symptom misdirects future verification.",
    "evidence": "Re-traced every link. `copycat/server/stock_engine.py:1279-1306`: `state.ingest(tick)` first, then the pending item carries `\"seq\": state.seq` (1300), then the timer is armed only when `_tick_flush_timer is None` (1303). `copycat/live/stock_state.py:87-96` `ingest` does `self.seq += 1`; `snapshot()` returns the same `self.seq` (`stock_state.py:275`) and `light_snapshot` likewise (`:262`). So \"snapshot seq leads\" ⇔ the item whose seq == snapshot seq is still in `_pending_ticks`, and `_flush_ticks` (`stock_engine.py:1757`) sends the *whole* pending list in ONE bundle → that bundle necessarily contains `acc.seq`. `frontend/src/lib/stock-accum.ts:415-421` `isSeededDuplicate` then returns true for every item with `seq <= acc.seq`, and both hooks `continue` before the gap branch (`useStockStream.ts:379-381`, `useGroupLiveAccums.ts:158-160`). I also checked the reverse ordering the task asked about: if the flushed bundle reaches the browser BEFORE the HTTP snapshot, the main hook buffers those items (`useStockStream.ts:374-376` `refetchingRef` → pending, replayed only when `seq > snap.seq`, `:268-270`) and the group hook applies them to the pre-seed accum — neither path produces a refetch either. So the §4 sentence \"後端不 flush → 每 60 s 重播種後活躍檔各白打一趟單檔重拉\" is not derivable: with the frontend half present, removing the backend flush changes *when* the duplicate is consumed, not whether a refetch fires. Part (b) also stands: `useStockStream` has no periodic re-seed (accum is manual fetch, not a TanStack query; refetch triggers are `:242, :304, :321, :344, :381, :481, :533` — none periodic), while stock-accum.ts:411-413 was already reworded for exactly this in the same PR, so CLAUDE.md is internally inconsistent with its own sibling comment. Caveat I add to the finding: the doc's *intent* (both halves matter) is not wrong — the flush still buys the \"duplicate consumed before seeding\" case and narrows the docstring's own two-bundle residual (`stock-accum.ts:413-414`); only the quantified symptom is unsupported.",
    "introduced_by_pr": true,
    "fix_assumptions_verified": "all verified — the proposed rewording matches stock-accum.ts:411-414 口徑 and the refetch-trigger inventory I re-derived; no code change implied.",
    "diff_only_would_catch": false,
    "unverified_premises": "none"
  },
  {
    "id": "F-2",
    "verdict": "PARTIAL",
    "original_severity": "MEDIUM",
    "corrected_severity": "LOW",
    "severity_reason": "Incompleteness of a NEW diagnostic (pre-PR there was no window total at all), not a regression; `grep 佇列滿` criterion and cumulative `dropped` are unchanged.",
    "evidence": "Structural half CONFIRMED: `copycat/server/ws.py:66` and `:105` are the only two callers of `_settle_drop_window` (grep over the repo returns exactly those two plus the definition at `:82`), and there is no timer/periodic task — settlement is strictly publish-driven. Per-broadcaster isolation also confirmed: each engine owns its own instance (`app.py:548-556`, `index_engine.py:241`, `breadth_engine.py:246`, `stock_engine.py:349`), so the index 5 s poll / futures night session / corr engine cannot settle the *stock* broadcaster, and the heartbeat bypasses the broadcaster entirely (`ws.py:246-250`, direct `send_json`). `_flush_watchlist_loop` (`stock_engine.py:1774-1793`) is indeed silent when nothing is dirty. What does NOT hold: the finding's absolute \"永遠不會出現\". `_flush_watchlist_loop` also publishes on the four trial-window flips per trading day (`:1780-1787`, driven by wall clock + calendar via `_spot_trial_now`, `:673-680`), so a window opened during the 13:25–13:30 auction settles at the NEXT flip (08:30 the following trading day) if the process survives the night — i.e. a late, temporally misleading line rather than none; it is lost only across a restart. Backfill-status publishes (`:1548`, `:1595`, `:1625`, `:1656`) are another post-close path but only if the browser's 60 s group poll still enqueues (blocked by `_backfill_wanted` once codes are backfilled). Impact wording is otherwise honest: the window-head line prints cumulative `dropped` (`ws.py:111-117`), which for a day whose only drop burst is at the close reads `累計 dropped=1`; the new tail text \"本窗規模在窗到期結算那則\" at least points the operator somewhere, so \"零錯誤訊號\" is slightly overstated.",
    "introduced_by_pr": true,
    "fix_assumptions_verified": "partially verified — `_flush_watchlist_loop` does exist at `stock_engine.py:1774` and ticks at `self._throttle` (constructor default 1.0 s, wired per engine), so hanging a public `settle_drop_window()` there is feasible; but that loop belongs to the stock engine only, so the fix would NOT cover capital/futures/corr/river broadcasters (they have no comparable idle loop) — the `stream()` finally / lifespan-shutdown variants the finding also offers are the ones that generalize. Not verified: that a lifespan hook can reach every broadcaster instance.",
    "diff_only_would_catch": false,
    "unverified_premises": "Whether TC4 pushes post-13:30 quotes (盤後定價 14:00–14:30 / 零股) into the stock engine — that would keep publishing and settle the window; and whether prod is restarted nightly (memory suggests the user starts the server each morning, but I could not verify this in-repo)."
  },
  {
    "id": "F-3",
    "verdict": "CONFIRMED",
    "original_severity": "LOW",
    "corrected_severity": "LOW",
    "severity_reason": "Dead call + a latent ordering hazard in new code; no runtime behavior, maintenance cost only.",
    "evidence": "`ws.py:80` is the only caller of `_note_drop`, and `publish` already settled at `:66` with a `now` taken microseconds earlier. Enumerated the post-entry states: after `:66` runs, `_drop_warned_at` is either None (settle path cleared it at `:100`, or it was never set) → `:89` early-returns at `:90`; or it is within the window → `now - warned_at < 60` → same early return. The only theoretical escape is the client loop spanning 60 s of wall clock between `:66` and `:105`, which is impossible with `put_nowait`/`get_nowait`. I also verified the mutation claim by hand-running the three new tests against the mutant \"delete line 105\": `test_drop_warning_reports_window_count_and_relogs_after_window` (`tests/server/test_capital_api.py:1133-1159`) still yields exactly 3 warnings in the same order because the settle already happened at the publish entry, and the other two never expire a window inside `_note_drop`. Conversely the ordering argument is real and already load-bearing: if the entry settle were removed and only `:105` remained, the settle line would read `累計 dropped=8` and `test_capital_api.py:1155`'s literal `累計 dropped=7` would go red — i.e. `dropped += 1` at `:103` sitting before the settle is exactly the hazard described.",
    "introduced_by_pr": true,
    "fix_assumptions_verified": "all verified — deleting `:105` keeps `now` alive for `_drop_warned_at = now` at `:110`; moving `dropped += 1` after the settle would change the existing asserted literal `累計 dropped=7`/`=8`, so that alternative requires touching `test_capital_api.py:1155-1156` (the finding does not say so).",
    "diff_only_would_catch": true,
    "unverified_premises": "none"
  },
  {
    "id": "F-4",
    "verdict": "CONFIRMED",
    "original_severity": "LOW",
    "corrected_severity": "LOW",
    "severity_reason": "Test-coverage gap on a documented rule; current code is correct → none at runtime.",
    "evidence": "Grepped `window_dropped` repo-wide: the only test-side occurrences are `tests/server/test_capital_api.py:1146` (==7), `:1157` (==1, but that is the *new* window's opening count, asserted with no subsequent settle), `:1179` (==0 after settle) and `:1196` (==7). Both settlement scenarios (`:1149-1150` and `:1174-1175`) settle a window whose count is 7, so `ws.py:91` `> 1` → `> 0` / `>= 1` survives every test in the suite (only `DROP_WARN_WINDOW_SECS` monkeypatch sites are those two, so no other file exercises expiry). The rule is not incidental — CLAUDE.md:328 records it as contract text (\"窗內 > 1 筆才印\"), and `ws.py:86-87`'s docstring states it explicitly.",
    "introduced_by_pr": true,
    "fix_assumptions_verified": "all verified — I hand-ran the proposed shape: `WsBroadcaster(maxsize=1)`, publish 2 (→ window_dropped == 1, one WARNING), drain, monkeypatch window to 0.0, publish once more → entry settle takes the `> 1` false branch, so `len(warned) == 1` and `window_dropped == 0`; the `> 0` mutant produces 2 warnings. Feasible with existing fixtures (caplog + monkeypatch already used in the class).",
    "diff_only_would_catch": true,
    "unverified_premises": "none"
  },
  {
    "id": "F-5",
    "verdict": "CONFIRMED",
    "original_severity": "LOW",
    "corrected_severity": "LOW",
    "severity_reason": "Test duplication only; no runtime impact, cost is three copies of one scenario to keep in sync.",
    "evidence": "Read both bodies in full. Existing `test_drops_are_counted_and_warned_once_per_window` (`tests/server/test_capital_api.py:1098-1117`) and new `test_drop_warning_first_of_window_then_window_total` (`:1184-1200`) share `WsBroadcaster(maxsize=3)`, `for i in range(10)`, `assert b.dropped == 7`, `assert len(warned) == 1`; the new one's only delta is `assert b.window_dropped == 7` (`:1196`), which `:1146` already asserts under the same script inside the settlement test. I checked the \"unique mutant\" question: mutants at `ws.py:109` (`window_dropped = 1` → 0) and `:107` (`+= 1` → no-op / += 2) all fail at `:1146` first; `len(warned) == 1` is already pinned at `:1112`; `maxsize=3` message content and the drop-oldest policy are pinned only by the OLD test (`:1113-1115`), i.e. the redundancy runs new→old, not old→new.",
    "introduced_by_pr": true,
    "fix_assumptions_verified": "all verified — rewriting this test into the single-drop-window case (F-4) is compatible with the class's fixtures and would leave no coverage hole, since every assertion in it is duplicated at `:1110-1112` / `:1146`.",
    "diff_only_would_catch": false,
    "unverified_premises": "none"
  },
  {
    "id": "F-6",
    "verdict": "CONFIRMED",
    "original_severity": "LOW",
    "corrected_severity": "LOW",
    "severity_reason": "Comment states a wrong justification for a correct guard; no runtime effect, but it invites removing the guard during 'simplification'.",
    "evidence": "Confirmed the code and the asyncio semantics. `copycat/server/stock_engine.py:1751-1754` is the cancel site; the only scheduling site is `:1303-1306` guarded by `_tick_flush_timer is None`; the only other teardown is `close()` at `:430-432` — no fourth site, so an uncancelled handle and a freshly armed one can coexist. Walked the no-cancel counterfactual: snapshot path flushes at t+0.05 and (old form) merely nulls the field; a tick at t+0.06 re-arms H2 for t+0.16 because the field is None (`:1303`); orphan H1 fires at t+0.10 and `_flush_ticks` has no \"is this my handle\" check — `_pending_ticks` is non-empty, so it publishes the new window early (`:1755-1758`) and, under the *current* first-line cancel, would cancel H2, or under the old form leave H2 as the next orphan. So the comment's \"空 → 早退,無害\" is only the quiet-market case; in an active stock the effect is bundle-cadence drift, exactly as claimed. CPython detail also checks out: `TimerHandle.cancel()` on the currently-running handle is safe because `_run_once` clears `handle._scheduled` before invoking the callback, so `_timer_handle_cancelled` does not bump `_timer_cancelled_count`.",
    "introduced_by_pr": true,
    "fix_assumptions_verified": "all verified — the proposed rewording is a comment-only edit on a `+` line; no test depends on the comment.",
    "diff_only_would_catch": false,
    "unverified_premises": "none"
  },
  {
    "id": "F-7",
    "verdict": "CONFIRMED",
    "original_severity": "LOW",
    "corrected_severity": "LOW",
    "severity_reason": "Route docstring now contradicts the behavior this PR gave it; none at runtime, misleading to anyone reading the API layer.",
    "evidence": "Read `copycat/server/app.py:1687-1715`: the route docstring's first line is still \"群組檢視的唯讀 batch(group-grid SC-4)。\" (`:1689`) while the engine method it calls now flushes and may publish (`stock_engine.py:762-766` + `:794-797` + `self._flush_ticks()` at `:800`, all `+` lines in the diff). Both callers are `async def` (`app.py:1651`, `:1688`), so the engine docstring's \"只能在 event loop 上呼叫\" precondition holds and this is purely a text drift. Minor correction to the finding: `_flush_ticks` publishes only when `_pending_ticks` is non-empty (`stock_engine.py:1755-1758`), so \"每打一次就…多送一則\" is a worst case, not every call. Same drift exists one route up — `stock_state` (`app.py:1654-1664`) also gained a flush side-effect via `snapshot()` and its docstring says nothing either; the finding under-reports by one site.",
    "introduced_by_pr": true,
    "fix_assumptions_verified": "all verified — `app.py` is untouched by this PR, so the fix is a one-line docstring edit in an unmodified file; no callers or tests read the docstring.",
    "diff_only_would_catch": false,
    "unverified_premises": "none"
  },
  {
    "id": "F-8",
    "verdict": "CONFIRMED",
    "original_severity": "LOW",
    "corrected_severity": "LOW",
    "severity_reason": "New docstring names a self-heal path that does not exist; none at runtime, but it understates the blind spot's exposure window.",
    "evidence": "`frontend/src/lib/stock-accum.ts:412-413` (a `+` line) lists 重連 / 切檔 / `watchlist_changed` as the main chart's heal paths. The first two check out (`useStockStream.ts:530-533` onOpen → `void refetch()`; `:313-322` instrumentKey effect → `void refetch()`). The third does not: `case \"watchlist_changed\"` (`useStockStream.ts:500-503`) contains exactly one statement, `queryClient.invalidateQueries({ queryKey: [\"stock-watchlist\"] })`, and the main accum is not a TanStack query — it is `useState` + a hand-written `refetch()` (`:246-309`), touched only by the seven `void refetch()` sites (`:242, :304, :321, :344, :381, :481, :533`), none of which is in that branch. The only indirect route (watchlist change removes the current code → StockPage switches code → instrumentKey changes) is already covered by \"切檔\", so the third item adds nothing but false reassurance.",
    "introduced_by_pr": true,
    "fix_assumptions_verified": "all verified — deleting the item or folding it into \"切檔\" is a comment-only change.",
    "diff_only_would_catch": false,
    "unverified_premises": "none"
  },
  {
    "id": "F-9",
    "verdict": "CONFIRMED",
    "original_severity": "LOW",
    "corrected_severity": "LOW",
    "severity_reason": "Mutation-survivor on the one property `seqsByCode` exists for; current code correct → none at runtime.",
    "evidence": "Grepped `seqsByCode|isSeededDuplicate` across `frontend/src`: producers at `stock-accum.ts:391/415`, consumers only at `useStockStream.ts:369/379` and `useGroupLiveAccums.ts:148/158`; no direct unit test in `stock-accum.test.ts`. Then checked every bundle in the two hook test files for a cross-code seq collision that would discriminate a global-Set mutant: `useGroupLiveAccums.test.tsx:109` uses 2330:{11,12} / 2317:{4} against acc.seq 10 / 3 — every item is `> acc.seq`, so the guard is never even reached; the four new cases (`:126-144`) are single-code; `useStockStream.test.ts` mixed bundle (items `[2330:2, 2317:9, 2330:3, 2454:1]` against main acc.seq 1) is likewise all `> acc.seq`; the two new cases there use single-code bundles. So replacing the per-code Map with one global Set leaves the suite green. Prod 樣態 as stated is plausible: seq is a per-code counter (`stock_state.py:87-96`), so a 50-code bundle colliding on another code's `acc.seq` would make a genuine rollback look like a seeded duplicate.",
    "introduced_by_pr": true,
    "fix_assumptions_verified": "NOT fully verified — the proposed case's expected outcome is wrong as written. With `snaps = {2330: seq 3, 2317: seq 12}` and bundle `[2330:12, 2317:3]`, 2330's item (12) is a forward gap and DOES refetch, so \"2330 照常套用\" cannot hold; the discriminating assertion has to be the call count (correct code → 2 refetches, global-Set mutant → 1, because 2317's rollback gets swallowed). The scenario still works as a mutant-killer once the expectation is restated.",
    "diff_only_would_catch": false,
    "unverified_premises": "none"
  },
  {
    "id": "F-10",
    "verdict": "CONFIRMED",
    "original_severity": "LOW",
    "corrected_severity": "LOW",
    "severity_reason": "Vacuous-pass risk in a new test; assertion strength only, none at runtime.",
    "evidence": "`frontend/src/components/stock/GroupGridView.test.tsx:283-299`: `const before = seen.length` is captured with no prior assertion, and the only check is `expect(seen.length).toBe(before)`. Verified the mutant really passes: `subscribeTickView` (`frontend/src/lib/tick-stream.ts:45-47`) does NOT replay the current value on subscribe, so with both effects (`GroupGridView.tsx:328-331`) deleted, `before === 0` and the final length is 0 → green. The finding is in fact understated: `setTickView` itself dedups via `sameList` (`tick-stream.ts:39-43`), so even removing the `[csv]` deps array would not make this test red — the test cannot detect either regression it narrates; only the sibling case at `:286-299` catches wholesale deletion. Secondary points check out too: `test-utils.tsx:15-18` `wrap` is the shared 5-copy consolidation and its docstring says exactly that; both new `it(...)` are `async` with no `await`.",
    "introduced_by_pr": true,
    "fix_assumptions_verified": "all verified for the main fix — `expect(before).toBeGreaterThan(0)` (or `toBe(1)`) discriminates, since the mount effect fires once with `[\"2330\",\"2317\"]`. The secondary suggestion is correctly hedged: `wrap` cannot be reused here because it owns the QueryClient internally and its `rerender` would need the same provider tree, so a new `test-utils` export would indeed have to be added — the finding says \"考慮\", not \"should\".",
    "diff_only_would_catch": true,
    "unverified_premises": "none"
  },
  {
    "id": "F-11",
    "verdict": "CONFIRMED",
    "original_severity": "LOW",
    "corrected_severity": "LOW",
    "severity_reason": "Test placement/discoverability; none at runtime — suitable for 參考用.",
    "evidence": "`tests/server/test_stock_routes.py:995-997` scopes `TestStockWsView` to inbound `view` frames (register / auto-deregister / bad-input WARNING); the new `test_prod_wiring_keeps_default_tick_flush_interval` (`:1003-1011`) opens no websocket and only asserts `stock._tick_flush_secs == 0.1` on the `create_app` engine, so the class docstring no longer covers its contents. The precedent it cites is real and lives in a generically named class: `tests/server/test_capital_api.py:1203-1213` `class TestWebSockets::test_prod_wiring_keeps_default_flush_interval`. The file's other classes (`:911 TestStockWs`, `:715 TestGroupStateRoute`, …) are all route/feature-scoped, so a new `TestStockWiring` (or moving it beside `TestStockWs`) is consistent with the file's convention.",
    "introduced_by_pr": true,
    "fix_assumptions_verified": "all verified — the test uses only `make_client(tmp_path)` and module-level imports, so it moves to any class in the same file without new fixtures.",
    "diff_only_would_catch": true,
    "unverified_premises": "none"
  }
]
```

### Step 4.3b lone-finding 判斷

本輪只有一個 review 軸,11 條全為 lone finding;「他軸為何漏」在此無法用「他軸沉默」推論(他軸根本沒跑),改以內部複查的 `diff_only_would_catch` 欄位登記:F-03 / F-04 / F-10 / F-11 為 diff 本身可見的缺陷(diff-only 軸有機會抓到);其餘七條依賴跨檔追溯(`stock_state.py` / `app.py` / `tick-stream.ts` / `useStockStream.ts` 未動行),diff-only 軸抓不到屬合理。全部 verdict 為 CONFIRMED / PARTIAL,無「解釋不出他軸為何漏」的降級情境;severity 校正(F-01 / F-02 MED → LOW)依據為 impact(純文件 / 新診斷不完整),不是 lone 降級。

## Action Items

**Severity calibration**:6c Refactor Intent Gate —— 本 PR 無「移除 / 削弱既有防護」類 finding,N-A。6d-1 hedge:F-02 含未驗前提(已標)且為 PARTIAL,cap Should Fix 以下;6d-3:無任何 finding 有 user-visible 重現路徑 + release-blocking 後果(11 條全為文件 / 測試 / 新診斷完整度,runtime 行為零影響),Must Fix 為空;6d-2 由 4.3b 判斷取代。provenance cap N-A。
**校準套用**:無作者校準檔(`xu-min-yu.md` 不存在)、本輪無套用。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

無。

### Nice to Have(可選優化)

- **F-01** CLAUDE.md §4 兩句改述(口徑同 stock-accum.ts:411-414)。`auto-fix`
- **F-02** 丟包窗結算的觸發點補通用路徑(`stream()` finally / 關機段)或接受「翌日試撮翻轉遲印」現況並在 §4 記明;兩條前提(TC4 盤後推價 / 每日重啟)可由 log 實錄後再決定。`ask-user`
- **F-03** 刪 `ws.py:105` + `_settle_drop_window` docstring 標唯一呼叫點。`auto-fix`
- **F-04 + F-05** 把重複的 `test_drop_warning_first_of_window_then_window_total` 改寫成單筆窗案(殺 `> 1 → > 0`)。`auto-fix`
- **F-06** `_flush_ticks` 取消 timer 註解改述為孤兒 handle 早送新窗。`auto-fix`
- **F-07** `app.py` `stock_group_state` 與 `stock_state` 兩條 route docstring 補 flush 副作用。`auto-fix`
- **F-08** `isSeededDuplicate` 註解刪 `watchlist_changed`。`auto-fix`
- **F-09** `useGroupLiveAccums.test.tsx` 補跨檔 seq 撞號案,斷言 refetch 次數 2(全域 Set 突變體 = 1)。`auto-fix`
- **F-10** `GroupGridView.test.tsx` 同組不重送案加 `expect(before).toBe(1)`;拿掉無 `await` 的 `async`。`auto-fix`
- **F-11** 接線測試搬離 `TestStockWsView`。`auto-fix`

### 參考用(內部複查 REFUTED / OUT_OF_SCOPE)

無。

## 審查工具比較 (qualitative)

- CC 主軸(typescript-reviewer,context-aware):11 條全部依賴跨檔追溯或測試突變推理;兩條 MED 各有一半主張在複查中被修正(F-01 impact 高估、F-02「永遠不會」不成立)。
- Codex 中性 / 對抗、Gemini:本機無工具,重疊率無法計算。
- 內部複查(同軸 code-reviewer)結果分佈:CONFIRMED 10 / PARTIAL 1 / REFUTED 0 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0。REFUTED 率 0% —— 但同軸複查的 REFUTED 率天生偏低(共用盲點),不能拿它推論 first-pass 命中率;可靠的訊號是複查對 F-01 / F-02 / F-07 / F-09 / F-10 各補了一段原 finding 沒有的機制修正,說明第二雙眼睛有在做反證而非背書。
- 對抗式第三軸增益:N-A(未起)。
- 本輪與分支自身 round-1 two-axis review 的關係:round-1 抓的是「結算搬到 publish 入口」「close 斷言位置」等;本輪 11 條無一與 round-1 11 條重複,全部是 round-1 收修**之後**新寫的行(結算狀態機、docstring、新測試)—— 即 user 擔心的「context 滿時寫的最後三筆」正是本輪 findings 的來源,擔心成立但影響面全在文件與測試強度,runtime 零。

## 沒做的部分（結案對帳）

- Codex 中性軸:FAIL —— `codex` CLI 不存在於本機、`~/.codex/config.toml` 不存在,無法起軸;報告以 CC 單軸 + 同軸內部複查呈現。
- Codex 對抗式軸:FAIL —— 同上;未 retry(工具缺席非暫時性失敗)。
- Gemini Flash 軸:FAIL —— `agy` CLI 不存在於本機。Gemini Pro:N-A(未啟用、Step 2.96 未問 —— 工具缺席使問題無意義,報告註明「按預設只跑 Flash」亦不成立,兩軸皆 N-A)。
- Step 2.98 Codex preset 詢問:N-A(工具缺席未問)。
- Cross-axis verification 4.1:N-A(無非 CC finding)。4.2:以同軸 code-reviewer 內部複查代替(PASS),**非跨軸證據**。
- Blast radius(2.9):PASS(有跑)但空輸出跳過。
- React-doctor(2.97):PASS,未引入新問題(newCount 1 為既有警告行號位移)。
- Formal spec traceability(2.65):SKIPPED (C4_NO_IMPLEMENTATION_BINDING_CLAUSE);spec-compliance-reviewer 未派。
- Author calibration(2.2):無檔、本輪無套用。
- 未驗前提(集中揭露):F-02 兩條 —— TC4 盤後定價 / 零股是否繼續推 quote 進 stock engine;prod 是否每日重啟。F-02 修法「關機段能否觸及全部 broadcaster」未驗。其餘 finding 的修法假設由內部複查逐條驗過(F-09 原預期已修正)。
- Self-Verify:已執行(`skill-verify-auditor`,requested=opus / observed=UNAVAILABLE)。結果 R1–R9 PASS、**R10 FAIL** —— 原缺口 = 本節的 Self-Verify 項原先寫成「見發布後補記」,屬未定案的 silent gap;修正方式 = 以本行實際結果取代。依 Step 6 規則修正後不重派 auditor,本報告**未經第二次獨立稽查**。
- 定位 FAILED 1 條(F-04 刻意 `<none>`),inline 已標「需人工確認」。
