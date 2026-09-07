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
## [完整證據副檔](pr-171-review.audit.md)
### finding_uid 索引
[2948c9f9a4acfba35a41](pr-171-review.audit.md#發現總覽) · [e87e42c12a097b8da372](pr-171-review.audit.md#發現總覽) · [b2b7b799afc2384b1599](pr-171-review.audit.md#發現總覽) · [738ac77156914731fe44](pr-171-review.audit.md#發現總覽) · [4f952da4ae3778218d35](pr-171-review.audit.md#發現總覽) · [35567cab4689baaefad4](pr-171-review.audit.md#發現總覽) · [616a61399d835a803670](pr-171-review.audit.md#發現總覽) · [555e750294274da01203](pr-171-review.audit.md#發現總覽) · [263b7673e35a29e517bf](pr-171-review.audit.md#發現總覽) · [b5c2fe4554b97b48e5ee](pr-171-review.audit.md#發現總覽) · [2b40206119c02404d7cd](pr-171-review.audit.md#發現總覽) · [66608bb6273ee50bb9cb](pr-171-review.audit.md#發現總覽) · [3c6fc9a2f171d0f27dfa](pr-171-review.audit.md#發現總覽) · [90349a7874ce525b8bb1](pr-171-review.audit.md#發現總覽) · [49ded4f160a1a7677122](pr-171-review.audit.md#發現總覽)
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
