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
## [完整證據副檔](pr-188-review.audit.md)
### finding_uid 索引
[c28cc0deb9b458bb094e](pr-188-review.audit.md#發現總覽) · [0ff152c3214a7a3aac06](pr-188-review.audit.md#發現總覽) · [30a75137dec1f0eedce2](pr-188-review.audit.md#發現總覽) · [c4eb55e3b4da258c9b2b](pr-188-review.audit.md#發現總覽) · [2663f70ac4f8d8e44de0](pr-188-review.audit.md#發現總覽) · [546bbf27f99c0fffb44a](pr-188-review.audit.md#發現總覽) · [b9a69834ed35883e766b](pr-188-review.audit.md#發現總覽) · [8e7340158b98ddcfef86](pr-188-review.audit.md#發現總覽) · [37e0e08daa1e9b8cd718](pr-188-review.audit.md#發現總覽) · [3e9a2390e3603ef0bd01](pr-188-review.audit.md#發現總覽) · [b44ae14f3312943a6046](pr-188-review.audit.md#發現總覽)
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
