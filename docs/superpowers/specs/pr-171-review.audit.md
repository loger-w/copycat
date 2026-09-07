# PR #171 Code Review 比較報告 · SHA 8c8e7063

**Report projection schema**: 1

**PR**: [loger-w/copycat#171](https://github.com/loger-w/copycat/pull/171)
**標題**: fix(live): TC4 DK 同 session 同窗凍結快照 —— DK refetch 帶窗口 variant + 值未前進 WARNING
**作者**: XU MIN YU(loger-w)
**分支**: `fix/dk-frozen-snapshot` → `master`(PR 已 rebase merge、遠端分支已刪;review 環境以 `refs/pull/171/head` 重建)
**變更**: 15 檔案, +969 / −12
**審查日期**: 2026-09-01
**Review input basis**: source repo `R_kgDOTsITBg` + `8c8e706383dced15ef981281f82be6ab3df346c7`;destination repo `R_kgDOTsITBg` + `8de6fcfbdb4e2928501c838cb3847613d0582a47`;input_binding: verified(worktree HEAD 逐字節等於 source SHA;base 以精確 SHA 釘定並可解析)
**Review continuity**: source_continuity=CURRENT(產報告前重抓 headRefOid 仍為 8c8e7063);base_changed=true(master 已因本 PR 自身的 rebase merge 前進至 d309e718 —— diff 基準 8de6fcfb 為 PR API 之 baseRefOid,不受影響);review_context_changed=false
**審查工具**: CC context-aware reviewer agents(primary ×2 chunks)+ 同軸替代驗證(獨立 code-reviewer 踢館 + 突變體抽驗)。Codex 中性、Codex 對抗、Gemini Flash、Gemini Pro 四軸因本機無對應 CLI 全數缺軸 —— 本輪為 CC 單軸 + 同軸驗證,非 cross-axis,詳「沒做的部分」
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary=python-reviewer ×2 chunks(requested=opus / observed=opus);verifier=code-reviewer(requested=opus / observed=opus);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED 未派);Codex=UNAVAILABLE(CLI 不存在);Gemini=UNAVAILABLE(agy CLI 不存在)
**覆蓋 (ENH-A)**: |F|=15 → covered 12 / no-issues 2 / skipped 1 / missed 0(chunked: 是 —— DIFF_LINES 981 > 800 門檻;chunk 1 = 11 檔 756 行、chunk 2 = 4 測試檔 225 行)
**定位 (ENH-B)**: anchored exact 12 / ambiguous 1 / FAILED 0(另 2 條為缺失型 anchor:<none>,不計)
**React-doctor (2.97)**: N-A(非 React PR)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_AUTHORITY)
**Blast radius (2.9)**: 空輸出跳過(sem CLI 未安裝,script 無輸出)
**Codex preset (2.98)**: 未詢問(codex CLI 不存在,中性/對抗兩軸缺軸,preset 選擇無意義)
**Gemini 軸 (2.96)**: 未詢問(agy CLI 不存在;Flash 永久軸缺軸、Pro N-A)
**Quota (Gemini 軸)**: 未取 dashboard snapshot(軸未跑)
**審查軸狀態**: primary(python-reviewer ×2 chunks)PASS(逐檔 accounting 齊);domain reviewers N-A(security / spec-compliance 未觸發);Codex 中性 FAIL(CLI 不存在);Codex 對抗 FAIL(CLI 不存在);Gemini Flash FAIL(CLI 不存在);Gemini Pro N-A(opt-in 未啟用且 CLI 不存在);cross-axis verification FAIL → 以同軸替代驗證執行(獨立 code-reviewer 踢館,15/15 條逐條 verdict + 抽驗 5 隻存活突變體全屬實);C4 N-A(gate SKIPPED)
**校準套用**: 無作者校準檔(xu-min-yu.md 不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master)
**worktree**: C:\side-project\copycat\.worktrees\review-pr-171
**worktree HEAD**: 8c8e706383dced15ef981281f82be6ab3df346c7

**Report generation**: sha256:19de5c72f3dc78a1e52dfacb84eb9bb412ca941b078e174d4f1f80219b3263d4

---

## Spec 依據

- 依 Step 2.6 偵測規則,本 PR **未附正式 spec / plan 文件**(路徑 / 檔名 / frontmatter 全部不匹配)。
- 但 PR 自帶 de-facto plan:`.claude/bug/dk-frozen-snapshot/diagnosis.md`(/bug 流程的診斷 + 修法設計文件,含 Phase 1–2 紅迴圈實錄、root cause 定案、修法三條與 Phase 5 seam)。本輪把它當 reviewer 的 scope ground truth 使用(「序號不設上界」「fetch_daily_bars 不濾頭部」「不 UNSUB DK key」三個刻意決策以它 + `code-review-round-1.json` disposition 為據)。
- **⚠️ spec 作者 = PR 作者**(diagnosis.md 由本 PR 同一作者流程產出;out-of-scope 判定以此文件為據時,注意作者自寫 plan 的利益重疊 —— 本輪 reviewer 已依指示「決策本身不挑戰、只挑戰實作與決策矛盾或決策未記帳的缺陷」,實際產出 F-04 / F-08 / F-11 三條正是「決策記帳與事實不符」類)。
- `SPEC_COMPLIANCE` receipt:gate=SKIPPED;dispatch=NOT_APPLICABLE;dispatch_count=0;reason_code=C4_NO_NORMATIVE_AUTHORITY(diagnosis.md 為 informal plan prose,無 NORMATIVE_KEYWORD / INVARIANT / FORMULA / STATE_TRANSITION / ERROR_CONTRACT 型條文);requested_model=opus;observed_model=UNAVAILABLE;effort=xhigh;0 clauses / 0 findings。

## 變更概要

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| copycat/live/tc4.py | 行為 | 新增 `_next_dk_start`(per (symbol, start, end) 序號、每刷 start 前移一日)+ `_dk_fetch_seq` / `_dk_seq_lock` 狀態 |
| copycat/live/futures_source.py | 行為 | DK 分支接 `_next_dk_start` + 頭部過濾(含端點契約) |
| copycat/live/stock_source.py | 行為 | `fetch_bars_range_tagged` D 分支同上;`fetch_daily_bars` 接 variant(刻意不濾頭部,docstring 記帳) |
| copycat/server/bars.py | 行為 | `_daily_pre_final` set→dict(記寫入時刻)+ `_warn_if_not_advanced` 「值未前進」WARNING(`_INTRADAY_SNAPSHOT_END` 13:30 閘) |
| tests/live/test_futures_bars.py | 測試 | 新 `TestDkWindowVariant`(窗口遞移 / 頭部過濾 / 1K 不吃 variant) |
| tests/live/test_stock_bars.py | 測試 | 新 `TestDkWindowVariant`(tagged D / fetch_daily_bars / per-窗序號) |
| tests/live/test_stock_source.py | 測試 | N024 測試補 `_dk_fetch_seq.clear()`(事前標記該變) |
| tests/server/test_bars.py | 測試 | 新 `TestFrozenRefetchSignal`(warn ×2 / no-warn ×3) |
| .claude/skills/tc4-market-facts/SKILL.md | 文件 | 新增 DK 凍結快照條(UNSUB 不逃逸 + 窗口排除事實) |
| .claude/bug/dk-frozen-snapshot/*(6 檔) | 產物 | diagnosis / verification / review JSON / probe 腳本與輸出 |

## 發現總覽

| # | 問題 | 嚴重度(原 → 校正) | 複查(同軸替代驗證) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 「含端點」契約的界值零覆蓋:`>=`→`>` 突變體全量 3265 條存活 | MEDIUM → MEDIUM | CONFIRMED(突變體抽驗實跑) | Nice to Have | `auto-fix` | 各補一列界上 DK row 即殺,局部明確 |
| 2 | stock 側缺「1K 不吃 variant」守門條(futures 有、stock 漏) | MEDIUM → MEDIUM | CONFIRMED(突變體抽驗實跑) | Nice to Have | `auto-fix` | 照抄 futures 同名條即可 |
| 3 | 「DK 空手也要消耗 variant」零測試 —— 不設上界的核心理由沒被釘住 | MEDIUM → MEDIUM | CONFIRMED(突變體抽驗實跑) | Nice to Have | `auto-fix` | 補空頁治具測試,形狀既有 |
| 4 | tripwire 盲區:「今日 bar 整天缺席」型凍結(現貨/加權盤前開機)恆不鳴 | MEDIUM → LOW | CONFIRMED(機制;app.py 接線已查) | Nice to Have | `ask-user` | 補 doc caveat 或接交易日曆二選一,屬設計取捨 |
| 5 | 界前並發首抓會誤鳴一次「值未前進」(無 inflight dedup) | LOW → LOW | CONFIRMED(機制重演) | Nice to Have | `auto-fix` | 早退加一格界前 return,一行 |
| 6 | 序號 key 的 symbol 維度未斷言(拿掉 sym 全 suite 綠) | LOW → LOW | CONFIRMED(突變體抽驗;失效型態下修為成本面) | Nice to Have | `auto-fix` | 同測試多打一檔股號斷言首發原窗 |
| 7 | `_INTRADAY_SNAPSHOT_END` 界上瞬間未釘(同檔 DAILY_FINAL_TIME 有專釘前例) | LOW → LOW | CONFIRMED(突變體抽驗實跑) | Nice to Have | `auto-fix` | 加一條界上快照不鳴 |
| 8 | tc4 docstring「撞窗由值未前進 WARNING 兜底」不成立(fetch_daily_bars 不經 BarsCache)+ 序號跨閾值零 log | LOW → LOW | CONFIRMED(caller 鏈已查;實際風險比原述更小) | Nice to Have | `auto-fix` | docstring 校正 + 可選一行跨閾值 log |
| 9 | 頭部過濾逐字兩份;上輪 disposition「抽 helper = 逆依賴」只在放 tc4.py 時成立 | LOW → LOW | CONFIRMED(依賴方向已查,rationale 缺陷) | Nice to Have | `ask-user` | 上輪已拍板留兩行;新事證(放 stock_source 零逆依賴)是否翻案由你裁 |
| 10 | evidence 腳本硬綁已刪除的 worktree 路徑 + docstring/diagnosis 用舊名 `_dk_start_variant` | LOW → LOW | CONFIRMED(路徑已驗不存在) | Nice to Have | `auto-fix` | 相對路徑 + 兩處補「(收修後改名)」 |
| 11 | SKILL.md「caller 以 start_date 濾頭部」寫成全稱,fetch_daily_bars 例外未標 | LOW → LOW | CONFIRMED | Nice to Have | `auto-fix` | 補半句例外 |
| 12 | `_clock` 為 `_mutable_clock` 逐字副本(同檔 2 份可變 + 1 份凍結牆鐘 helper) | LOW → LOW | CONFIRMED(措辭「三份可變」校正為 2+1) | Nice to Have | `auto-fix` | 抽 module 級共用 |
| 13 | 治具不看 StartTime → head-extension 因果未真演出;`_subs` 兩份非 static | LOW → LOW | PARTIAL(前半屬實;`_subs` 非逐字副本) | Nice to Have | `ask-user` | 治具窗口感知重構值不值得,由你裁 |
| 14 | probe 腳本 finally 在 login 失敗路徑 NameError 被寬 except 吃掉 | LOW → LOW | PARTIAL(NameError 屬實;「靜默」不成立 —— 有 cleanup error 輸出、Disconnect 照走、無 UNSUB 被跳過) | Nice to Have | `auto-fix` | `session = None` 先綁,兩行 |
| 15 | fetch_daily_bars 測試吃真 `date.today()`,跨午夜理論 flake(~1e-11/run) | LOW → LOW | CONFIRMED(實質 INFO,驗證者判可不修) | Nice to Have | `no-op` | 相對式斷言已最小化暴露,機率可忽略 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 2948c9f9a4acfba35a41 action=auto-fix
F-02 finding_uid: e87e42c12a097b8da372 action=auto-fix
F-03 finding_uid: b2b7b799afc2384b1599 action=auto-fix
F-04 finding_uid: 738ac77156914731fe44 action=ask-user
F-05 finding_uid: 4f952da4ae3778218d35 action=auto-fix
F-06 finding_uid: 35567cab4689baaefad4 action=auto-fix
F-07 finding_uid: 616a61399d835a803670 action=auto-fix
F-08 finding_uid: 555e750294274da01203 action=auto-fix
F-09 finding_uid: 263b7673e35a29e517bf action=ask-user
F-10 finding_uid: b5c2fe4554b97b48e5ee action=auto-fix
F-11 finding_uid: 2b40206119c02404d7cd action=auto-fix
F-12 finding_uid: 66608bb6273ee50bb9cb action=auto-fix
F-13 finding_uid: 3c6fc9a2f171d0f27dfa action=ask-user
F-14 finding_uid: 90349a7874ce525b8bb1 action=auto-fix
F-15 finding_uid: 49ded4f160a1a7677122 action=no-op

### Inline Comments per Finding（直接複製貼到 PR review）

#### #1 含端點的界本身沒被釘住,`>=` 改 `>` 全量測試照綠

**File**: tests/live/test_futures_bars.py
**Line**: 276-287

**Comment**:

```
兩條 head-filter 測試(這裡跟 test_stock_bars.py 那條)治具只有界外 06-30 跟界內深處的列,
沒有一列剛好落在 start_date 上。把生產碼的 b["t"] >= start_date 改成 > ,全量 3265 條照綠
—— 「含端點」是這條過濾器唯一宣稱的性質,現在每次 DK 取數靜默丟掉區間首根也沒訊號
(週/月 K 首桶跟著少一根,圖照畫)。

各加一列 _dk_row("20260701", ...) 斷言它活著就殺掉這隻突變體;
同檔 test_boundary_instant_is_final_side 對 DAILY_FINAL_TIME 就是這樣專釘界的,標準拉齊。
```

#### #2 stock 側漏了「1K 不吃 variant」的守門條

**File**: tests/live/test_stock_bars.py
**Line**: 453

**Comment**:

```
futures 的 TestDkWindowVariant 有 test_1k_refetch_keeps_window 擋住「順手把 variant 套到 1K」,
stock 同名 class 宣稱同病同修卻沒這條 —— 把 fetch_bars_range_tagged 的 tf=="1" 分支
也接上 _next_dk_start,全量 3265 條照綠。

1K 已經有自己一套 variant(fetch_day_minutes 的 end-hour 階梯、有 CAP),
DK 這套 start 日期無上限 variant 洩進去等於兩套逃逸機制互踩,而 1K 是每天 ~270 列的熱路徑。
照抄 futures 那條:同參數打兩次,斷言兩發 1K SUBQUOTE 的 StartTime 相同。
```

#### #3 「空手那一刷也要消耗 variant」沒有任何測試 —— 但它正是不設上界的核心理由

**File**: tests/live/test_stock_bars.py
**Line**: 462

**Comment**:

```
三條 window-variant 測試的 DK 頁都有資料。docstring 把「序號不設上界」的正當性押在
「空結果 → 負向 TTL → 重試靠換窗才有意義」上,但這個性質零覆蓋:
我在空手路徑加 self._dk_fetch_seq[(sym, start, end)] -= 1(空手退還序號),721 條全綠。
這個「合理的成本優化」會讓 DK 空 → 重試永遠重用同一把凍結成空的 key,
把本 PR 修掉的病在最高頻那條路原地復發、零訊號。

補一條 pages = {"DK": {}} 的測試:連取兩次,斷言兩發 DK SUBQUOTE 的 StartTime 仍逐次 −1 日
(futures 側要用 pytest.raises(HistoryTimeoutError) 包,同檔既有姿態)。
```

#### #4 「今日 bar 整天沒出現」型凍結,值未前進 WARNING 恆不鳴

**File**: copycat/server/bars.py
**Line**: 420

**Comment**:

```
bars[-1]["t"] == day 這格把「末根不是今日」整類排除 —— docstring 寫它是誤鳴抑制(休市),
但同一格也吃掉一種真凍結:交易日 08:xx 開 server(prod 常態),現貨/加權當下今日 DK bar
還不存在,界前快照末根 = 前一交易日;這把 key 若凍結,14:00 後 refetch 末根仍是前一交易日
→ 條件不成立 → 靜默,症狀 = 當日 D bar 整天缺席。查過 app.py:bars 路徑的 today 是牆鐘
_date.today()(_today() docstring 明文列 bars 為例外),盤前「前一交易日」stage 不作用在這裡。

期指不受影響(夜盤先行、08:00 已有今日 bar),已觀測的 prod 事故形狀有覆蓋 ——
所以這是診斷網的洞、不是資料錯。兩條擇一:(a) 判準改「整份與作廢前相同」+ 交易日曆閘休市;
(b) 只補 doc:把 verification.md「凍結若再現:grep 值未前進 命中」那句限定為
「界前快照已含今日 bar 的情形」,別讓判準被當全覆蓋。
```

#### #5 界前並發首抓會誤鳴一行「值未前進」

**File**: copycat/server/bars.py
**Line**: 417

**Comment**:

```
build_daily / build_period 無 inflight dedup(grep 過,零命中)。同 key 兩請求同時首抓:
A 先完成(stale=None 不鳴、寫入 pre_final 時刻),B 後完成 —— B 眼中 stale = A 剛寫那份,
兩趟間無成交就逐字節同、寫入 < 13:30、末根是今日 → 鳴一行「疑似 TC4 凍結快照」,
但其實 A/B 用的是 n=0/n=1 兩把不同窗、一切正常。會誘導人去追不存在的 TC4 迴歸。

tripwire 語意本來就是「作廢後的 refetch」:_warn_if_not_advanced 開頭加
if _now_time() < DAILY_FINAL_TIME: return 就把整類並發誤鳴殺掉
(界前正常路徑本來就不存在「有 stale 可比的 refetch」,不損失訊號)。
```

#### #6 序號 key 的 symbol 維度沒被斷言

**File**: tests/live/test_stock_bars.py
**Line**: 507-518

**Comment**:

```
測試名寫「序號按 (symbol, 窗) 記」,但三次取數全是 2330 —— 把 key 改成 ("", start, end)
(拿掉 symbol 維度)全 suite 照綠。拿掉後同 base 窗下第二檔起首查就是 variant n>0,
「首查 = 原窗」這條安全性主張對第一檔以外全部靜默失效(驗證者補充:序號仍單調遞增、
不會拿回用過的窗字串,凍結不復發 —— 代價是窗寬被全體取數次數一起撐大,屬成本面)。

同條測試多打一次 fetch_bars_range_tagged("2454", ...),斷言 2454 首發 StartTime 是原窗
(不接著 2330 的序號走)即可。
```

#### #7 13:30 界上一瞬沒釘

**File**: tests/server/test_bars.py
**Line**: 948-966

**Comment**:

```
四條訊號測試用的寫入時刻是 09:00 跟 13:50,沒有 13:30 整 —— written >= _INTRADAY_SNAPSHOT_END
改成 > 全 suite 照綠,「界含不含端點」沒有可執行的答案。同檔上一輪才替 DAILY_FINAL_TIME
寫了 test_boundary_instant_is_final_side 專釘兩個界突變體,新界跟上同一標準:
加一條 now["t"] = bars_mod._INTRADAY_SNAPSHOT_END 建立快照、過界重查,斷言不鳴
(界上屬已定稿側)。順帶讓常數本身在測試裡被引用(現在 grep _INTRADAY_SNAPSHOT_END
在 tests/ 是零命中)。
```

#### #8 docstring「撞窗由 WARNING 兜底」對最會撞的那條路是空話

**File**: copycat/live/tc4.py
**Line**: 954-955

**Comment**:

```
_next_dk_start docstring 把跨 base 撞窗的代價交給 bars.py「值未前進」WARNING 兜底,
但最可能累積取數次數的 fetch_daily_bars(overlay don't-cache-empty 驅動)走 OverlayCache、
不經 BarsCache —— 那條路 tripwire 從不執行(驗證者補充:overlay 前端 staleTime Infinity、
非輪詢,140 次/日門檻其實很遠,純文件條目)。另外序號跨過 docstring 自己標的 140 門檻時
零 log、全函式零 logging。

docstring 那句改掉(或限定「僅 build_daily/build_period 路徑有兜底」),
可選:同 key 每日首次跨閾值印一行 WARNING,讓「今天有 key 走到撞窗區」可 grep。
```

#### #9 頭部過濾兩份逐字重複 —— 上輪拒絕抽 helper 的理由站不住

**File**: copycat/live/stock_source.py
**Line**: 858-859

**Comment**:

```
futures_source.py:218 跟這裡的過濾 comprehension 連註解逐字相同。上輪 disposition 拒絕
抽 helper 的理由是「會造成 tc4 → stock_source 的 Bar 型別逆依賴」—— 但那只在 helper
放 tc4.py 時成立;futures_source 本來就 from stock_source import parse_dk_bars,
放 stock_source(parse_dk_bars 本尊旁)零新增依賴方向。

不過「兩行不值得一支 helper」這個結論本身還是站得住 —— 要不要翻案你裁:
翻 → parse_dk_bars 加 since= 參數三處共用;不翻 → 把 disposition 那句理由改正確,
免得下次有人引用錯的 rationale。
```

#### #10 修後驗證腳本綁死一棵已經不存在的 worktree

**File**: .claude/bug/dk-frozen-snapshot/evidence/dk_fix_realenv.py
**Line**: 14

**Comment**:

```
sys.path.insert 硬綁 C:\side-project\copycat-wt-dk-frozen-snapshot —— 那棵臨時 worktree
已隨收尾刪除,verification.md 卻把這支列為可重跑的修後 end-to-end 證據,現在重跑直接
ModuleNotFoundError。順帶:本檔 docstring 跟 diagnosis.md:46 都還寫舊名 _dk_start_variant
(收修已改名 _next_dk_start),按 plan doc 去 grep 產生點會落空。

路徑改 Path(__file__).resolve().parents[3] 回推 repo root;兩處舊名補一句「(收修後改名)」。
```

#### #11 SKILL 條目把頭部過濾寫成全稱,漏了 fetch_daily_bars 例外

**File**: .claude/skills/tc4-market-facts/SKILL.md
**Line**: 157-158

**Comment**:

```
「每刷 start 前移一日,caller 以 start_date 濾頭部」是全稱句,但三個消費點裡
fetch_daily_bars 刻意不濾(靠 bars[-n:] 尾切,函式簽名根本沒有 start_date)。
skill 是「碰任何 DK 取數前先讀」的入口,下一個實作者會以為 variant 對所有 caller
都被過濾抵銷。補半句「(fetch_daily_bars 例外,見該函式 docstring)」就好。
```

#### #12 `_clock` 是同檔 `_mutable_clock` 的逐字副本

**File**: tests/server/test_bars.py
**Line**: 892-895

**Comment**:

```
TestFrozenRefetchSignal._clock 跟 TestDailySnapshotFinality._mutable_clock 除 docstring 外
逐字相同(另有 _freeze 是不可變凍結版)。名字不同會讓之後改凍結點語意的人 grep 不到同類、
只改到其中一份;TODAY = date(2026, 8, 31) 也跟著複製。抽成 module 級 _mutable_clock
兩個 class 共用即可。
```

#### #13 治具不看 StartTime,head-extension 其實沒被真的演出來

**File**: tests/live/test_stock_bars.py
**Line**: 18-31

**Comment**:

```
_pager / _source 的 handler 只分派 SubDataType / QryIndex,StartTime 完全不參與選頁 ——
head-extension 測試第二刷拿到的 rows 跟第一刷逐字相同,斷言證明的是「濾器存在且用
caller start」(這點有效:濾器用 variant start 的突變體有被殺),但「窗變寬才多收那列」
的因果沒真的發生。要補 #1 的界上列跟 #3 的空手情境,治具遲早要能按 StartTime 回不同頁
(rows_by_start dict、未命中回 base 那份)—— 要不要一起做你裁;
順帶把兩個 _subs 統一成帶 dtype 參數的 @staticmethod(現在 stock 版有 dtype、futures 版沒有)。
```

#### #14 probe 腳本 login 失敗路徑的 finally 會 NameError

**File**: .claude/bug/dk-frozen-snapshot/evidence/dk_frozen_probe.py
**Line**: 190-199

**Comment**:

```
session 只在 login 成功後綁定,但 finally 無條件用它發 LOGOUT —— login 失敗時 NameError
被 except Exception 收成一行 cleanup error(驗證者核過:此路徑 opened 為空、沒有 UNSUB
被跳過、Disconnect 照走,所以實害趨近零,也不是靜默)。form 上仍是「不懂的 error 全吞」
的形狀:session: str | None = None 先綁、finally 內 None 就跳過 LOGOUT,兩行了事。
一次性 evidence 腳本、要不要回頭修隨意。
```

#### #15 fetch_daily_bars 測試吃真牆鐘,跨午夜有理論 flake 窗

**File**: tests/live/test_stock_bars.py
**Line**: 494-505

**Comment**:

```
不是 PR 缺陷、不用改 —— 記錄用。兩次 fetch_daily_bars 之間跨過午夜的話 base 窗換日、
序號歸零,兩條斷言同時紅;但兩次呼叫間是零 IO 的微秒級間隔,機率 ~1e-11/run,
而且寫成相對式(second == first − 1day)已經是最小暴露。同 repo test_bars.py 的
TestModuleClock 有過 00:04 實跑 5 failed 的前科才集中凍結點,這裡量級差太多,列參考。
```

## 第一輪原始 findings(CC 單軸、chunked)

### Chunk 1(runtime + docs;python-reviewer,opus)

- **C1-F01(→F-04)MEDIUM**:`bars.py:420` `bars[-1]["t"] == day` 使「當日 bar 從頭到尾沒出現」型凍結恆不鳴;盤前開機(現貨今日 DK bar 尚不存在)的界前快照末根 = 前一交易日,凍結後 refetch 同值但日期格不過 → 靜默;SKILL.md:158 的 grep 判準因此非全覆蓋。search-proof:`grep TradingCalendar copycat/server/bars.py` → 只有 build_minute 收 calendar;plan doc 未替此格記帳。
- **C1-F02(→F-05)LOW**:build_daily / build_period 無 inflight dedup(grep `_run_once|inflight|asyncio.Lock` 零命中),同 key 界前並發首抓,後完成者比對先完成者剛寫的快照 → 誤鳴。
- **C1-F03(→F-08)LOW**:tc4.py:954-955「撞窗由 bars.py WARNING 兜底」—— fetch_daily_bars 全部 caller(app.py:1427 overlay / signal_hub)不經 BarsCache;序號跨 140 零 log;`base - timedelta(days=n)` в n≈739k 有 OverflowError 極端(列觀察)。
- **C1-F04(→F-09)LOW**:頭部過濾 comprehension + 註解兩份逐字;disposition「抽 helper = 逆依賴」只在放 tc4.py 成立,futures_source 已 import stock_source。
- **C1-F05(→F-10)LOW**:dk_fix_realenv.py:14 硬綁已刪 worktree;docstring 與 diagnosis.md:46 用舊名 `_dk_start_variant`(grep 全 repo 程式碼零命中、只剩三處文件)。
- **C1-F06(→F-14)LOW**:dk_frozen_probe.py finally 於 login 失敗路徑 NameError → 寬 except 吃掉。
- **C1-F07(→F-11)LOW**:SKILL.md:158 全稱「caller 以 start_date 濾頭部」,fetch_daily_bars 例外未標。
- 逐檔 accounting:9 檔有 finding;REVIEWED_NO_ISSUES: verification.md;INTENTIONALLY_SKIPPED: dk_frozen_probe_1.json(純 probe 輸出,已抽查內容支撐 diagnosis 四臂表)。無安全 finding(無外部輸入/sink;probe SKEY 為既有公開 vendor key)。

### Chunk 2(tests;python-reviewer,opus;附突變體實跑)

worktree 內以主 repo venv 實跑:四檔 203 passed;全 suite baseline 3265 passed + 3 skipped;13 隻重要突變體 KILLED(方向反 / variant 失效 / 漏接 / 濾器刪除 / 濾器用錯 start / 1K 吃 variant(futures)/ WARNING 恆鳴 / 只比日期 / 閘反向 / 降 info / 呼叫順序 / key 傳錯 / stale 取錯),5 隻 SURVIVED:

- **C2-F1(→F-01)MEDIUM**:含端點 `>=`→`>` 兩處突變全量 3265 綠(治具無界上列)。
- **C2-F2(→F-02)MEDIUM**:stock `tf=="1"` 分支吃 variant 突變全量綠;futures 有守門條、stock 漏,而 stock 是熱路徑。
- **C2-F3(→F-03)MEDIUM**:空手退還序號突變 721 條綠;「空結果重試靠換窗才有意義」零覆蓋。
- **C2-F4(→F-06)LOW**:key 去 sym 突變全量綠;同 base 窗下第二檔起首查即 variant n>0。
- **C2-F5(→F-07)LOW**:`written >=`→`>` 突變全量綠;13:30 界上未釘,同檔 DAILY_FINAL_TIME 有專釘前例(`test_bars.py:877`)。
- **C2-F6(→F-12)LOW**:`_clock` 逐字副本;同檔第三份 `_freeze` 為凍結版。
- **C2-F7(→F-15)LOW**:真牆鐘 `date.today()` 跨午夜理論 flake(~1e-11),相對式斷言已最小化。
- **C2-F8(→F-13)LOW**:`_pager`/`_source` 不讀 StartTime → head-extension 因果未演出;`_subs` 兩份(stock 版多 dtype 參數)。
- 逐檔 accounting:3 檔有 finding;REVIEWED_NO_ISSUES: test_stock_source.py(N024 `_dk_fetch_seq.clear()` 未削弱原意圖、戳私有 dict 符合 repo 既有慣例、放 `_run()` 內正確)。

## 同軸替代驗證複查結果(獨立 code-reviewer 踢館;非 cross-axis)

| # | verdict | 原 → 校正 | 關鍵證據 |
| --- | --- | --- | --- |
| 1 | CONFIRMED | MEDIUM → MEDIUM | 抽驗突變體①:兩處 `>=`→`>`,全量 3265 passed + 3 skipped 存活;治具界上列確認缺席;還原後 status 乾淨 |
| 2 | CONFIRMED | MEDIUM → MEDIUM | 抽驗突變體②:stock 1K 分支接 `_next_dk_start`,全量同數存活;對照條 `test_futures_bars.py:289` 存在 |
| 3 | CONFIRMED | MEDIUM → MEDIUM | 抽驗突變體③:三處空手 `-= 1`,全量同數存活;docstring 正當性條文與零覆蓋對上 |
| 4 | CONFIRMED(機制) | MEDIUM → LOW | 指定查證:`app.py:1456/1819` `today = _date.today()`、`_today()` docstring 明文列 bars 為例外 → 盲區形狀成立;期指夜盤先行不受影響、已觀測 prod 事故形狀有覆蓋、現行零資料錯 → 降 LOW(貼 MEDIUM 邊界:若 grep 判準視為契約級可上修) |
| 5 | CONFIRMED | LOW → LOW | 機制重演:無鎖屬實;B 眼中 stale = A 剛寫那份;`_daily` 無 TTL + `_api_lock` 串行化收窄可達窗;建議補丁不損失訊號 |
| 6 | CONFIRMED | LOW → LOW | 抽驗突變體④:key 去 sym,tests/live+server 2024 passed 存活;失效型態下修 —— 序號仍單調遞增、凍結不復發,屬成本面 |
| 7 | CONFIRMED | LOW → LOW | 抽驗突變體⑤:`>=`→`>`,test_bars.py 68 passed 存活;界上專釘前例 `test_bars.py:877` 確認 |
| 8 | CONFIRMED | LOW → LOW | caller 鏈:`_warn_if_not_advanced` 只有 bars.py:396/546 兩呼叫點;fetch_daily_bars 走 OverlayCache;另 `useStockOverlay staleTime: Infinity` → 非輪詢,風險比原述更小 |
| 9 | CONFIRMED(rationale) | LOW → LOW | `futures_source.py:20` 已 import stock_source → 放 stock_source 零逆依賴;惟「兩行不值一支 helper」結論仍成立 |
| 10 | CONFIRMED | LOW → LOW | `ls` 舊 worktree 路徑 No such file;Python script 執行 sys.path[0] = 腳本目錄 → 重跑必 ModuleNotFoundError;舊名三處文件屬實 |
| 11 | CONFIRMED | LOW → LOW | SKILL 全稱 vs `stock_source.py:898-903` 明寫刻意不濾;函式簽名無 start_date |
| 12 | CONFIRMED | LOW → LOW | 逐字比對屬實;「三份可變」校正為 2 份可變 + 1 份凍結(`_freeze` 為 staticmethod 凍結版) |
| 13 | PARTIAL | LOW → LOW | 前半屬實(handler 不讀 StartTime);後半不精確 —— 兩個 `_subs` 非逐字副本(stock 版多 dtype 參數) |
| 14 | PARTIAL | LOW → LOW | NameError 屬實且被寬 except 吃;但「靜默」不成立(有 cleanup error 輸出)、opened 為空無 UNSUB 被跳過、Disconnect 照走 → 實質影響 ≈ 0 |
| 15 | CONFIRMED(INFO) | LOW → LOW | 機制與機率如述;相對式斷言已最小暴露,可不修 |

驗證另核:chunk 2 附的突變體證據**經抽驗 5/5 屬實,無造假或誇大**;worktree 全程還原乾淨。數字對帳:verification.md 記全量 3267 passed,review worktree 為 3265 passed + 3 skipped —— 差異 = worktree 缺 `tcoreapi_mq`(spikes/TCPY 為 gitignored、review worktree 未複製)造成的環境 skip,與 PR 無關;日後拿 3267 當判準要注意環境差。

## Action Items

**Severity calibration**:6d-3 雙半條件逐條套過 —— 全 15 條皆「不阻擋出貨」(測試覆蓋缺口 / 文件記帳不符 / 一行誤鳴 log / 診斷網盲區 / evidence 腳本衛生),零條同時具備 user-visible 重現路徑 + release-blocking 後果 → **零 Must Fix / 零 Should Fix**。6c(移除既有防護類):本 PR 無此類 finding,免。6d-1 hedge cap:無 finding 依未驗證前提撐級(F-04 的機制推演已由驗證者以 app.py 第一手查證補實)。lone-finding(4.3b):本輪僅 CC 單軸,全數 lone 屬結構性(無他軸可沉默),以同軸替代驗證的逐條 verdict + 突變體實證替代「他軸為何漏」判斷;無機械降級。

**校準套用**:無作者校準檔(xu-min-yu.md 不存在)、本輪無套用。

### Must Fix(合併前必修)

無。(PR 已 merge;本輪亦無符合雙半條件的候選。)

### Should Fix(強烈建議)

無。

### Nice to Have(可選優化)

- **F-01 / F-02 / F-03(MEDIUM 三條,突變體實證)**:本 PR 核心契約(含端點界值 / 1K 隔離 / 空手換窗)的測試覆蓋缺口 —— 三條都是「補一條測試即殺」的局部改動,建議下一輪收修一起做。
- **F-05 / F-07**:「值未前進」訊號的精確度補強(界前早退 + 界上釘)。
- **F-04**:tripwire 盲區 —— 補 doc caveat(便宜)或接交易日曆(完整)二選一,`ask-user`。
- **F-06 / F-08 / F-10 / F-11 / F-12 / F-14**:斷言補強與文件/記帳校正,均小。
- **F-09 / F-13**:上輪已拍板事項的翻案候選與治具重構,`ask-user`。
- **F-15**:`no-op`,記錄用。

### 參考用

無(本輪零 REFUTED / 零 OUT_OF_SCOPE)。

## 審查工具比較

- 本輪實際佈局:CC 單軸(python-reviewer ×2 chunks)+ 同軸替代驗證(獨立 code-reviewer)。Codex / Gemini 四軸缺軸 → **無 cross-axis 對照資料**,重疊率 / REFUTED 率等跨軸統計不適用。
- Chunk 2(tests reviewer)自帶突變體實跑是本輪最高含金證據:13 killed / 5 survived 的清單把「測試網哪裡有洞」從推測變成實測;驗證者抽驗 5/5 屬實。
- 同軸替代驗證的結果分佈:CONFIRMED 12 / PARTIAL 2 / REFUTED 0 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0;嚴重度校正僅 F-04 下修(MEDIUM→LOW)與兩處措辭校正 —— first-pass 命中率高,但注意這是**同模型家族互驗**,共同盲點(兩者都想不到的失效模式)無從被此結構抓到,信心上限低於真 cross-axis。

## 沒做的部分(結案對帳)

- **Codex 中性軸**:FAIL —— `codex` CLI 本機不存在(`which codex` 空)。無 diff-only fresh-eyes 訊號。
- **Codex 對抗軸**:FAIL —— 同上。無紅隊訊號。
- **Gemini Flash 軸(永久軸)**:FAIL —— `agy` CLI 本機不存在。
- **Gemini Pro 軸**:N-A —— opt-in 未啟用(且 CLI 不存在,詢問無意義,依規記於 header)。
- **Step 2.96 / 2.98 preset 詢問**:未執行 —— 對應 CLI 不存在,選項無意義;非 user 跳過。
- **Step 4.1 / 4.2 cross-axis verification**:FAIL(無他軸)→ 以**同軸替代驗證**執行(獨立 fresh code-reviewer 踢館 + 突變體抽驗);同模型家族互驗的共同盲點風險已在「審查工具比較」揭露。
- **Step 4.3a consensus baseline check**:N-A —— 單軸無 consensus 條。
- **Blast radius (2.9)**:空輸出跳過(sem CLI 未安裝)。
- **C4 formal spec (2.65)**:SKIPPED (C4_NO_NORMATIVE_AUTHORITY) —— PR 內僅 informal plan prose(diagnosis.md),無 normative 條文文件;0 clauses / 0 findings。
- **React-doctor (2.97)**:N-A(非 React PR)。
- **Provenance (2.55)**:N-A(base = master)。
- **Quota snapshot**:未取(Gemini 軸未跑)。
- **測試數字環境差**:review worktree 全量 = 3265 passed + 3 skipped(缺 gitignored `spikes/TCPY` 致 `tcoreapi_mq` 相關 3 條 skip),與 PR verification.md 的 3267 passed + 1 skipped 為環境差、非行為差;兩個 baseline 都已列出。
- **未驗證前提**:無 —— 15 條 finding 的支點均有第一手查證(檔案引文 / 實跑輸出 / 突變體執行);F-04 的「盤前開機必有日 K 請求」屬合理但未實錄的使用情境(前端行為未在本輪實測),已反映在其 LOW 分級與 ask-user 處置。
- **Self-Verify**:見發布時補記。
