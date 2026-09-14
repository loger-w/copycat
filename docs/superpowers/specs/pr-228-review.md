# PR #228 Code Review 比較報告 · SHA 21385338
**Report projection schema**: 1

**PR**: [loger-w/copycat#228](https://github.com/loger-w/copycat/pull/228)
**標題**: mod(signal): 訊號層三件顯示層小改 —— CDP 列閘 / 放量離開 kind / 掃單簇大單筆數格(#224)
**作者**: loger-w
**分支**: `mod/signal-context-trio` → `master`
**變更**: 35 檔案, +2091 / -104
**審查日期**: 2026-09-14
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨;merge commit `e60024cd`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `213853381f61fbc24a06574defba3ba2f20118c5`;destination repo id `R_kgDOTsITBg` + baseRefOid `1a032b9b3c5c259abf44b24e83de934d884520df`;`input_binding: verified` —— `git fetch origin refs/pull/228/head` 取回的 FETCH_HEAD = headRefOid 逐字相等,review worktree detached 於該 SHA,`git merge-base origin/master HEAD` = baseRefOid
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 SHA;分支已隨 `--delete-branch` 刪除,但 `refs/pull/228/head` 仍指 `21385338`,產報告前重抓 headRefOid 仍為它);`base_changed=true`(origin/master 自 `1a032b9b` 前進至 `e60024cd`,內容 = 本 PR 自身 13 筆 rebase 後 commit,其後零新 commit);`review_context_changed=false`(審的是 PR head,與落地版逐檔等價)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用,沿 #188 / #190 / #199 / #202 / #211 / #218 / #220 / #222 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer ×2(chunked;requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .py 94% / .ts+.tsx 6% 的 source diff 行);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE;純讀碼 + grep + 只讀 pytest / 突變體模擬);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=35 → covered 8 / no-issues 19 / skipped 8 / **missed 0**(chunked: **是**,21 source 檔 / 1568 source diff 行(.py 1478 / .ts+.tsx 90)超過 15 檔 / 800 行門檻 → 依排序路徑切兩塊:chunk A = `.claude/**` + `CLAUDE.md` + `CONTEXT.md` + `copycat/**` + `frontend/**`(27 檔,source 14)、chunk B = `tests/**`(8 檔);35/35 per-file accounting 齊,skipped 8 = 4 張截圖 + 4 個證據 JSON)
**定位 (ENH-B)**: anchored exact 11 / ambiguous 1 / **FAILED 0**(全部 anchor 在 worktree 逐字命中:signal_state.py:3 / signal_hub.py:986 / :1195 / change-spec.md:53 / test_signal_state.py:1518(reviewer 自報 1515-1521)/ :1622(自報 1618-1624)/ :1496 / test_signal_hub.py:2614(自報 2613-2619)/ :1750 / :3195 / test_signal_policy.py:186 / test_signal_rules.py:1047(**ambiguous**:anchor 亦命中 :954 的 v3→v4 同型斷言,取 reviewer 自報 1046-1047 內的 1047))
**React-doctor (2.97)**: 未引入新問題(既有 2 條不計;`npx -y react-doctor@latest . --offline --no-score --scope changed --base 1a032b9b --json` 於 review worktree `frontend/` 執行,`newCount 0 / fixedCount 0 / baseTotalCount 2`,changedFileCount 9)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_CLAUSE)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出;`sem` 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer chunk A)PASS(4 findings + 27/27 accounting;只讀 pytest 371 passed)/ primary(python-reviewer chunk B)PASS(8 findings + 8/8 accounting;只讀 pytest 595 passed + 五組突變體模擬)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 請求體解析 / 秘鑰讀取)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(12/12 verdict 齊、ID 集合精確相等、每列八欄齊)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-228`
**worktree HEAD**: `213853381f61fbc24a06574defba3ba2f20118c5`

**Report generation**: sha256:99170a237d0aa18d9076aafc28d3d20f54bdcf68b05e223e899ca0e6ef6e0a38

---
## [完整證據副檔](pr-228-review.audit.md)
### finding_uid 索引
[cc3cd222c50a381499fc](pr-228-review.audit.md#發現總覽) · [d0e9ffac666699a55345](pr-228-review.audit.md#發現總覽) · [7ddbc5619e3938ffb6e8](pr-228-review.audit.md#發現總覽) · [8432ed56fbf4d719fdf3](pr-228-review.audit.md#發現總覽) · [7dd212ad8d301d65499f](pr-228-review.audit.md#發現總覽) · [02c73ead59cd885ea09a](pr-228-review.audit.md#發現總覽) · [806a5de91e5b4dad9067](pr-228-review.audit.md#發現總覽) · [da2731c9603af66c10ba](pr-228-review.audit.md#發現總覽) · [026bcfbba1c28da9173f](pr-228-review.audit.md#發現總覽) · [e071edf1d0c030b507ba](pr-228-review.audit.md#發現總覽) · [a4f7e30decd440f2ac2e](pr-228-review.audit.md#發現總覽) · [9ae5056d957a90170e0e](pr-228-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `signal_state.py:3` 模組 docstring 仍寫「六類訊號」清單,本 PR 加了第七類 `vol_breakout` 沒更新;`CLAUDE.md:60` 結構樹同一份清單也沒加(該行 base 上已漏 `surge_pullback`,本 PR 讓落差變兩項) | LOW | CONFIRMED(LOW→LOW:純文字陳舊,機器真值 `RULE_KINDS` 七值有測試釘) | Nice to Have | `auto-fix` | 兩處文字各改一行,零 runtime |
| F-02 | `signal_hub.py:986` `_gate_return_pct` 只對分母 `close[-6] ≤ 0` 回 None;分子 `close[-1] ≤ 0` 會算成 −100% 走「漲幅不足」INFO 桶,壞資料被記進不合格檔,round-1 F-02「兩種原因分講」只做了半邊 | LOW | PARTIAL(LOW→LOW:實跑 close[-1]=0 → −100.0 落 986 行 INFO 桶;但閘的**結果**不變(CDP 仍 None),差異止於 log 分桶;反例只在 `cdp_gate_pct ≤ −100` 時成立) | Nice to Have | `auto-fix` | 一行擴 `or done[-1]["close"] <= 0` + WARNING 文案「首尾日 K 收盤 ≤ 0」,以「log 分桶一致性」立案 |
| F-03 | `change-spec.md:53` W-14 寫「非掃單簇規則的 detector 不維護大單狀態以外的新東西 / 開銷 = 每 tick 一次 deque append」低估:每條規則的 detector 都無條件跑 `_eval_breakout` 狀態機(`_dwell` / `_break` 兩份 dict + 離帶時 dataclass / set 配置),非 vol_breakout slot 只推進不產出;結論 bounded 為真、理由句錯 | LOW | CONFIRMED(LOW→LOW:實測 enabled 只有 vol_burst 的 detector 餵 20,000 tick 後 `_dwell` / `_big_hits` 都有狀態,4.33 µs/tick/detector;上限 30 條規則 × 4.33 µs 仍 bounded) | Nice to Have | `auto-fix` | 改 W-14 敘述為「兩軸狀態機 per-detector 各一份、非該 kind 只推進不產出、per-tick O(1)、中位只在候選 tick 算」;spec artifact 文字修正 |
| F-04 | `test_signal_state.py:1518` `test_reset_day_clears_lots_and_hits` 前置大單 09:59:30.000、發訊 10:01:30.500,窗起點 09:59:30.500 → 即使 `reset_day` 不清 `_big_hits` 也被窗剪掉,兩邊都 0,不 discriminate;跨日殘留(自午夜秒數)是真風險 | MEDIUM | CONFIRMED(MEDIUM→MEDIUM:突變體「reset_day 不清 `_big_hits`」113 passed 存活;對照 `drop_code` 不 pop 與 `reset_day` 不清 `_dwell` 兩顆姊妹突變體都被殺;前置改 10:00:30.000 後正常 0 / 突變 1,鑑別成立) | Nice to Have | `auto-fix` | 一個字面(前置時刻改 10:00:30.000);影子期研究欄 `big_lots_120s` 跨日污染的唯一守門 |
| F-05 | `test_signal_state.py:1622` 迴盪「有成交分鐘 ≥ 4」地板(spec Q10、`_BREAKOUT_MIN_MINUTES`)無邊界案:唯一案 2 分鐘、其餘全 10 / 11 分鐘;常數改 3 / 5 / 8 / 10 全綠 | MEDIUM | CONFIRMED(MEDIUM→MEDIUM:四個突變值 113 passed 全存活;姊妹常數 `_BIG_LOT_MIN_TICKS` 29 / 31 兩顆都被殺、`breakout_min_dwell_secs` 有 599 / 600 精確邊界 —— 本條是同 feature 唯一漏網) | Nice to Have | `auto-fix` | 補「恰 4 個有成交分鐘 → 發 / 3 個 → 不發」兩案;研究同源常數不得靜默改掉 |
| F-06 | `test_signal_hub.py:2614` `test_vol_breakout_kind_text_by_direction` docstring 宣稱釘「方向缺值退向上」但零斷言;三元反轉照綠。前端鏡像 `signal-model.test.ts:350-352` 同樣沒補缺 direction 案 | MEDIUM | PARTIAL(MEDIUM→**LOW**:突變體「fallback 反轉」177 passed 存活,缺口為真;但 `direction` 線上恆由 detector 填,缺值只在舊 / 外來列,後果止於一則文案的方向字;真缺陷是 docstring 宣稱釘了而沒釘) | Nice to Have | `auto-fix` | 後端加無 direction 的 row 斷「放量向上離開」、前端 `kindLabel` 補同一案;兩邊逐字契約各一行 |
| F-07 | `test_signal_state.py:1496` `test_median_uses_the_most_recent_300_ticks` 沒釘 300:`_BIG_LOT_MEDIAN_TICKS` 改 200 / 299 / 301 / 400 全綠;CLAUDE.md §4 新契約逐字寫「中位取最近 300 筆」 | LOW | CONFIRMED(LOW→LOW:四顆突變全存活;構造只要求窗長落在 (0, 600) 且能翻轉中位;漂掉只改 `big_lots_120s` 命中數(研究欄),不改任何訊號是否發出) | Nice to Have | `auto-fix` | 補一案讓第 301 筆是否入母體翻轉結果(300 筆 1 張 + 1 筆 100 張的排列) |
| F-08 | `test_signal_hub.py:1750` 「日 K 不足」INFO 只斷 `"5" in lines[0]`(實得根數),需求根數 `(需 6)` 未斷;log 寫錯 `cdp_gate_days` 仍綠;CLAUDE.md 盤後判準「整批全『日 K 不足』= 抓取根數被改小」正是讀這兩個數 | LOW | CONFIRMED(LOW→LOW:突變體「第三個 arg −1」131 passed 存活;姊妹案 docstring 明寫「不得印成『只有 6 根(需 6)』」卻無案斷「需 6」) | Nice to Have | `auto-fix` | 改斷 `"只有 5 根(需 6)"` 子字串 |
| F-09 | `test_signal_hub.py:3195` `_fmt_secs` 是第三份時刻格式化微變體(`test_signal_policy._fmt` / `test_signal_state._ms_time`),且定義在檔尾唯一使用者之後(同檔慣例 helper 緊接使用者之前) | LOW | PARTIAL(LOW→LOW:「重複」半邊 REFUTED —— 三份輸入域不同(整數秒 / 浮點秒 / 毫秒),且 `grep "^def _bar("` 19 檔各持私有 helper 是 repo 既有形狀、`tests/helpers/` 無格式化先例;「位置」半邊 CONFIRMED —— 唯一使用者在 :3175、同檔 `_sweep_group` 緊接 `TestSweepCluster` 之前) | Nice to Have | `ask-user` | 只剩可讀性偏好(上移到使用者前);要不要動由 user 拍板 |
| F-10 | `test_signal_policy.py:186` round-1 F-06 收修的 bool / 非數值守門(`_emit_policies` 與 `format_policy_group_text` 各一處)零測試;產生點 `_advance_big_lots` 恆回 int,bool 只能由手改 jsonl / 未來新產生點帶入 | LOW | CONFIRMED(LOW→LOW:`grep "big_lots_120s.*True\|BIG_LOTS_KEY: True" tests/ frontend/src` 零命中;守門所防輸入在現行拓撲產不出來,屬防禦性程式碼的測試缺口) | Nice to Have | `ask-user` | 為不可達輸入補案是 user 對防禦性測試密度的偏好;要補 = 純函式層一案(`detail={BIG_LOTS_KEY: True}` → 頂層 None) |
| F-11 | `test_signal_rules.py:1047` v4→v5 撞名 WARNING 只斷 count 與 levelname,未斷 `skip_note`「(放量離開種子沒進去 = 影子期 rail 零放量離開列)」;v3→v4 同型案(`:954-955`)依 review F-29 斷後果句 | LOW | CONFIRMED(LOW→LOW:突變體「v4→v5 的 skip_note 清空」212 passed 存活;`:971` 的「放量離開」抓的是規則名不覆蓋 skip_note) | Nice to Have | `auto-fix` | 補 `"rail 零放量離開列" in hits[0].getMessage()` 一行,與姊妹案同口徑 |
| F-12 | `signal_hub.py:1195` `"sweep": dict(detail)` 是第二次淺拷貝(1153 行已 `dict(event.detail or {})`),讀起來像在防別名 | LOW | REFUTED(LOW→LOW:1195 位於 `for policy in ctx.hits:` **迴圈內**,同 dict 字面的 `"self": dict(me)` / `[dict(p) for p in ctx.peers]` 同手法 = 每列自己一份;同 tick 多政策列是常態(`test_signal_policy.py:284` `["B-a","B-b"]`、`:368` `["P","S"]`),拿掉會讓多列共用同一顆 dict) | 參考用 | `no-op` | 兩次拷貝防的不是同一件事,刪掉會引入真實別名;不是缺陷 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: cc3cd222c50a381499fc action=auto-fix
F-02 finding_uid: d0e9ffac666699a55345 action=auto-fix
F-03 finding_uid: 7ddbc5619e3938ffb6e8 action=auto-fix
F-04 finding_uid: 8432ed56fbf4d719fdf3 action=auto-fix
F-05 finding_uid: 7dd212ad8d301d65499f action=auto-fix
F-06 finding_uid: 02c73ead59cd885ea09a action=auto-fix
F-07 finding_uid: 806a5de91e5b4dad9067 action=auto-fix
F-08 finding_uid: da2731c9603af66c10ba action=auto-fix
F-09 finding_uid: 026bcfbba1c28da9173f action=ask-user
F-10 finding_uid: e071edf1d0c030b507ba action=ask-user
F-11 finding_uid: a4f7e30decd440f2ac2e action=auto-fix
F-12 finding_uid: 9ae5056d957a90170e0e action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 檔頭還寫「六類訊號」,第七類放量離開沒進清單
**File**: `copycat/live/signal_state.py`
**Line**: 3

**Comment**:
```
這支檔頭的六類清單是「寫或改 .py 前先讀」的第一眼資訊,本 PR 加了第七類卻沒更新;同檔下面
SWITCH_KEYS 註解已經是「#226 起七鍵」、測試也叫 test_seven_switch_keys_and_kind_map,只剩這句漂著。
CLAUDE.md:60 的結構樹那行 signal_state(CDP 穿越/爆拉跌/爆量/鎖板/掃單簇) 也一起補 —— 那行從 #174 起就漏了爆拉回檔。

改成「七類訊號:… / 掃單簇 / 放量離開」就好。
```
#### #2 分子那根日 K 收盤是 0 的話,會被記進「漲幅不足」桶而不是壞資料
**File**: `copycat/server/signal_hub.py`
**Line**: 986

**Comment**:
```
_gate_return_pct 只擋分母 close[-6] ≤ 0;最後一根 close[-1] ≤ 0 時算出 −100%,走 986 行的
「前 5 日累計 -100.00% < +5.00%」INFO → 盤後 grep "CDP 列閘" 會把壞資料當成一檔真的不合格。
閘的結果本身是對的(CDP 一樣不評),只是 round-1 F-02 要求「兩種原因分得出來」只做了分母半邊。

_gate_return_pct 的 `if base <= 0` 擴成 `if base <= 0 or done[-1]["close"] <= 0`,
WARNING 文案改「首尾日 K 收盤 ≤ 0(壞資料)」即可。
```
#### #3 W-14 那句「開銷 = 每 tick 一次 deque append」低估了
**File**: `.claude/mod/signal-context-trio/change-spec.md`
**Line**: 53

**Comment**:
```
實作上每條規則的 detector 都在 enabled gate 之前無條件跑 _eval_breakout(_dwell / _break 兩份 dict,
離帶時還配 _Dwell dataclass + set),非 vol_breakout 的 slot 只是推進不產出;實測 enabled 只有
vol_burst 的 detector 餵兩萬筆 tick 後 _dwell / _big_hits 都有狀態,4.33 µs/tick/detector。
「bounded」的結論沒錯(30 條規則 × 4.33 µs),但理由句會讓下一個加 kind 的人低估 N 條規則的乘法。

W-14 改寫成:兩軸狀態機 per-detector 各一份;非該 kind 的 slot 只推進不產出;per-tick O(1);中位只在候選 tick 算。
```
#### #4 reset_day 那條大單測試,前置命中本來就在 120 s 窗外 —— 不清 hits 也是 0
**File**: `tests/live/test_signal_state.py`
**Line**: 1518

**Comment**:
```
前置大單打在 09:59:30.000,發訊在 10:01:30.500,窗起點是 09:59:30.500 → 就算 reset_day 完全忘了清
_big_hits,那一筆也會被窗自己剪掉,正常跟突變都是 0。突變體「reset_day 不清 _big_hits」跑整檔
113 passed 存活;對照 drop_code 不 pop / reset_day 不清 _dwell 兩顆姊妹突變都被殺。
跨日殘留是真風險(secs 是自午夜秒數,昨日 10:00 的命中會落進今日 10:01 的窗)。

前置那筆改 "10:00:30.000"(窗內)就鑑別得了:正常 0、突變 1。
```
#### #5 「有成交分鐘 ≥ 4」這顆地板沒有邊界案,改 3 / 5 / 8 / 10 全綠
**File**: `tests/live/test_signal_state.py`
**Line**: 1622

**Comment**:
```
_BREAKOUT_MIN_MINUTES = 4 是研究 len(vols) >= 4 的線上對應,唯一碰到它的案只給 2 個有成交分鐘,
其餘全是 10 / 11 分鐘 —— 常數改成 3 / 5 / 8 / 10 跑整檔都 113 passed。同 feature 的其他邊界
(第 30 筆、窗含端點、帶含端點、停留 599 vs 600)都釘得精確,獨缺這顆;研究同源常數被靜默改掉零訊號。

補兩案:恰 4 個有成交分鐘 → 發;3 個 → 不發。
```
#### #6 docstring 說釘了「方向缺值退向上」,其實一條斷言都沒有
**File**: `tests/server/test_signal_hub.py`
**Line**: 2614

**Comment**:
```
只測了 direction="up" / "down" 兩列;把 _kind_text 的三元反轉成 '向上' if d == 'up' else '向下'
照樣 177 passed。線上 direction 恆由 detector 填,缺值只在舊列 / 外來列出現,後果止於一則文案的方向字,
所以不重 —— 但 docstring 宣稱釘了而沒釘,後手會以為有保護。前端 signal-model.test.ts:350 同樣沒補缺 direction 案。

後端加一列 self._row(kind="vol_breakout", pct=4.0)(不帶 direction)斷「放量向上離開 4.0 倍」;
前端 kindLabel 補同一案(direction: null)。
```
#### #7 「最近 300 筆」的 300 沒被釘住
**File**: `tests/live/test_signal_state.py`
**Line**: 1496

**Comment**:
```
_BIG_LOT_MEDIAN_TICKS 改 200 / 299 / 301 / 400 整檔全綠 —— 這案的構造(300 筆 100 張 + 300 筆 1 張)
只要求窗長落在 (0, 600) 且能翻轉中位。CLAUDE.md §4 新契約逐字寫「中位取最近 300 筆」,對帳靠它同源。
影響只到 big_lots_120s 的命中數(研究欄),不改任何訊號是否發出。

補一案讓第 301 筆是否入母體會翻轉結果,例如 300 筆 1 張 + 再 1 筆 100 張的排列。
```
#### #8 「日 K 不足」那行只斷了實得根數,需求根數 (需 6) 沒斷
**File**: `tests/server/test_signal_hub.py`
**Line**: 1750

**Comment**:
```
斷言是 "日 K" in lines[0] and "5" in lines[0];把 log 第三個參數寫錯成 cdp_gate_days(印成「只有 5 根(需 5)」)
照樣 131 passed 存活。CLAUDE.md 的盤後判準「整批全『日 K 不足』= 抓取根數被改小」正是靠這兩個數指向。
姊妹案的 docstring 還寫「不得印成『只有 6 根(需 6)』」,卻沒有任何一案斷過「需 6」。

改斷 "只有 5 根(需 6)" 子字串。
```
#### #9 _fmt_secs 放在檔尾、在唯一使用者之後
**File**: `tests/server/test_signal_hub.py`
**Line**: 3195

**Comment**:
```
「第三份時刻格式化」這半不成立:test_signal_policy._fmt 吃浮點秒帶毫秒、test_signal_state._ms_time 吃毫秒、
這份吃整數秒恆 .000,輸入域不同;而且 tests/ 下 19 檔各持自己的 _bar 變體本來就是 repo 形狀。
剩下的只是位置:定義在 :3195、唯一使用者在 :3175,同檔慣例是 helper 緊接使用者之前(_sweep_group 在 TestSweepCluster 前)。

要動就把它上移到 TestVolBreakoutRule 之前;不動也行,純可讀性。
```
#### #10 round-1 F-06 補的 bool 守門,零測試
**File**: `tests/server/test_signal_policy.py`
**Line**: 186

**Comment**:
```
_emit_policies 與 format_policy_group_text 各一處「bool 先擋」是 round-1 review 要來的改動,
但 grep tests/ frontend/src 找不到任何 big_lots_120s 帶 True 的案;產生點 _advance_big_lots 恆回 int,
這輸入現行拓撲產不出來,所以是防禦性程式碼的測試缺口,不是功能缺口。

要補的話一條純函式層案就夠:detail={BIG_LOTS_KEY: True} → 政策列頂層 None、Discord 第二行不印「大單」;
不補也說得過去,看你對防禦性測試密度的偏好。
```
#### #11 v4→v5 撞名 WARNING 的後果句沒人斷
**File**: `tests/test_signal_rules.py`
**Line**: 1047

**Comment**:
```
只斷了 count 與 levelname;把 _migrate_v4 傳給 _append_seed 的 skip_note 整段清空,212 passed 照綠。
v3→v4 的同型案(:954)依 review F-29 有斷「零政策列」那句後果;這裡少了「(放量離開種子沒進去 = 影子期 rail 零放量離開列)」的唯一讀者。
(:971 的 "放量離開" in hits[1] 抓的是規則名,不算。)

補一行 assert "rail 零放量離開列" in hits[0].getMessage()。
```
