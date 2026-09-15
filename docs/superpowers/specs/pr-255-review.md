# PR #255 Code Review 比較報告 · SHA b718366f
**Report projection schema**: 1

**PR**: [loger-w/copycat#255](https://github.com/loger-w/copycat/pull/255)
**標題**: mod(backend): 個股內外盤改以達錢 FlagOfBuySell 為準,0 / 缺欄退回同則簿比;每日一行旗標計數
**作者**: loger-w
**分支**: `mod/stock-side-flag` → `master`
**變更**: 46 檔案, +94434 / -80405(其中 37 檔 / +94,032 / -80,399 為 `graphify-out/**` 生成產物;實質 9 檔 +402 / -6)
**審查日期**: 2026-09-15
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以收修 PR 處置,不阻擋任何出貨;merge commit `d199149b`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `b718366fd898df54cb2e00e7632a53223ee751a1`;destination repo id `R_kgDOTsITBg` + baseRefOid `f57efcd21b8e43963b807c9834b51a2f34bcc70d`;`input_binding: verified`(`refs/pull/255/head` fetch 後 `git rev-parse FETCH_HEAD` = headRefOid;worktree detached 於該 SHA;baseRefOid = 派工前 `git merge-base master HEAD`,可解析)
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 8 筆 SHA;分支已刪,`refs/pull/255/head` 仍指 `b718366f`,產報告前重抓 headRefOid 不變);`base_changed=true`(origin/master 已前進到 `d199149b` = 本 PR 自己的 merge 結果,無其他人 commit);`review_context_changed=false`(reviewed 內容即 master 現況,`d199149b` tree 與 `b718366f` tree 逐檔同內容)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A**(user 已停用,沿 #188 / #190 / #199 / #230 / #238 / #253 前例單軸)+ Codex 對抗式 **N-A** + Cross-axis verification(4.1 N-A 無非 CC finding;4.2 以 main session 內部逐條事實核代替,**非跨軸證據**)+ Gemini 軸 **N-A**(user 已停用)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer ×1(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .py 佔 source diff 100%;dispatch 17 tool uses / 419 s);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派,gate SKIPPED);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=46 → covered 4 / no-issues 9 / skipped 37 / **missed 0**(chunked: 否,9 source / docs 檔、實質 diff 408 行,低於 15 檔 / 800 行門檻;graphify 產物 37 檔全數 `INTENTIONALLY_SKIPPED — generated graphify artifact`,不計入 source 門檻)
**定位 (ENH-B)**: anchored exact 5 / ambiguous 0 / **FAILED 0**(F-02 與 F-05 共用同一行 anchor `:127`,兩條為同一行的不同關注點,各自獨立 pin;F-01 anchor `:1106`、F-03 `:248`、F-04 `:1340` 均唯一命中)
**React-doctor (2.97)**: N-A(非 React PR;F 無 .jsx / .tsx)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_SPEC)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出;`sem` 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer ×1)PASS(5 raw findings;46/46 accounting;白名單六條逐條讀 code 查過零破壞:`set[StockTick]` / tick 相等比較 零命中、`snapshot()` 六鍵與 `_flush_ticks` 十鍵無 `flag`、`.side` 讀者只 stock_state / stock_engine / relabel、`apply_backfill` 不經 `_handle_quote`)/ Codex 中性 N-A / Codex 對抗 N-A / Gemini Flash N-A / Gemini Pro N-A / cross-axis verification:4.1 N-A、4.2 以 main session 內部事實核代替 PASS(5/5 逐條對 worktree code:F-01 `__main__.py:127` 檔名 `server-%Y%m%d-%H%M.log` 啟動時定死 + `grep Rotating copycat/` 零命中 + 判準句 CLAUDE.md:520 / verification.md:51;F-02 :127 字面三桶無 inner/outer 計數;F-03 :248 `str(None)` 字面 `"None"`;F-04 :1281 `arms_the_day` vs :1340 同謂詞;F-05 :127–:128 無空行)/ 4.3a N-A(單軸無 consensus)/ 4.3b 逐條見備註
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-255`
**worktree HEAD**: `b718366fd898df54cb2e00e7632a53223ee751a1`

**Report generation**: sha256:ff43202f68d804cf106753fc9e6d0a008b35e48049526d2e872bb97a629be4d9

---
## [完整證據副檔](pr-255-review.audit.md)
### finding_uid 索引
[01b5a242a113f4ce3300](pr-255-review.audit.md#發現總覽) · [b791c2ef62cfb825ece7](pr-255-review.audit.md#發現總覽) · [d0c82379af126720ac34](pr-255-review.audit.md#發現總覽) · [bdfd9615e276c6ec00c0](pr-255-review.audit.md#發現總覽) · [3e14460632a43ef65a42](pr-255-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `stock_engine.py:1106` `_log_flag_stats` 只在 stage2(次日早上首筆)與 `close()` 印;log 檔名 `__main__.py:127` `server-%Y%m%d-%H%M.log` 於**啟動當下**定死、全 repo 零 rotating handler → server 當晚不重啟時 D 日那行落在**啟動日**檔、D+1 早上才印;CLAUDE.md:520 / verification.md:51 的判準 `grep "個股旗標 0" logs/server-<日>.log` 在 no-restart 日必零行 → 「健康跨日長跑」與「engine 漏印」不可分辨,判準自打;同日多次重啟則母體切成多行、判準卻寫「一行」 | MEDIUM | CONFIRMED(MED→MED:`grep -n "server-%Y" __main__.py` :127 唯一落點;repo-wide `grep -rn -i "RotatingFileHandler\|TimedRotating\|logging.config\|dictConfig\|fileConfig\|FileHandler("` 對 `*.py *.toml *.ps1 *.json`(排除 graphify-out / node_modules / .venv)**零檔命中** —— 謂詞語意 = 「除 `_setup_prod_log` :118–:135 那一次 `path.open("a")` tee 之外,repo 沒有任何會依日期重開檔的 log sink」;`run.ps1:9` 註解同名規則、不重導向;stage2 快路徑同經 `_log_flag_stats` 無旁路,機制本身正確,壞的是判準文件) | Should Fix | `auto-fix` | 文件層:判準改 `grep 個股旗標 logs/server-*.log` + 比對訊息尾 `(<交易日>)`、註明多次重啟多行桶相加;零 runtime 改動 |
| F-02 | `stock_engine.py:127` 三桶(0 / 欄缺 / 總)印不出「走 `derive_side` 退路的筆數」——達錢多出 `"3"` 或集合競價另給值時三個數字全看起來健康;本 PR 自己的 next-time 09-15 節就排了 09-16 抓檔看試撮 / 集合競價旗標值 = 團隊預期值域可能不只 0/1/2,而 prod 唯一儀器是這行(`/api/health` 刻意不含) | LOW | CONFIRMED(LOW→LOW:字面三桶事實;與已反駁 Spec-S-01「第三桶改字面」不同解法 —— 不動 pinned 字面、另加當日首見未知值 WARNING 一則,與 repo 既有節流 WARNING 樣板同款:`signal_hub.py:411` `_multi_group_warned: set[str]`(:719 換日清、:837 退訂 discard)+ :788 排除組名 WARNING(每次載入群組一次)、`trading_calendar.py:91–103` `_warned_years: set[int]`(每年份一次、跨年 clear)—— 第一手 file:line 已查) | Nice to Have | `auto-fix` | 加一則節流 WARNING,不動 `_FLAG_STATS_FMT` 字面與既有測試 |
| F-03 | `stock_models.py:248` `str(msg.get("FlagOfBuySell", ""))` 對 JSON `null` 產出字面 `"None"` → 既不進 `欄缺` 也不進 `0` 也不對映,靜默退路、兩桶雙 0,CLAUDE §4「`欄缺` 桶非 0 = 格式漂了(唯一訊號)」對 null 型漂移失效 | LOW | CONFIRMED(LOW→LOW:`str(None) == "None"` 為 Python 事實;`grep -n "str(msg.get" stock_models.py` 全檔同樣板(Security / PreciseTime / TradeDate),但那幾欄漂掉會被下游 parse 擋、本欄失效純靜默;09-14 抓檔 49,610 則旗標欄零 null,屬未觀察到的假設情境) | Nice to Have | `auto-fix` | `raw = msg.get(...); flag = str(raw) if raw is not None else None` 一行 + 一案測試 |
| F-04 | `stock_engine.py:1340` `if not is_futures_key(code):` 在同一次 `_handle_quote` 第三次求值,而 :1281 `arms_the_day = not is_futures_key(code)` 已持有同謂詞;成本可忽略(`startswith`),但同一謂詞在同函式兩個名字,讀者要自證兩處語意同一件事 | LOW | CONFIRMED(LOW→LOW::1281 / :1340 逐字;熱路徑但單次 `startswith` 無可量測開銷) | Nice to Have | `auto-fix` | 就地 `if arms_the_day:` + 註解點明「武裝換日 = 現貨鍵 = 計數母體」同一判準;或改中性名 `is_spot` 兩處共用 |
| F-05 | `stock_engine.py:127` 新常數與下一行 `#: TradeStatus 轉態觀測…` doc 註解之間缺空行;`#:` 慣例是「註解屬於下一個定義」,兩顆常數黏成一塊第一眼會讀錯歸屬(ruff 不擋) | LOW | CONFIRMED(LOW→LOW:`sed -n 126,129p` 逐字,:127 → :128 無空行) | Nice to Have | `auto-fix` | 加一行空白,不碰既有行 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 01b5a242a113f4ce3300 action=auto-fix
F-02 finding_uid: b791c2ef62cfb825ece7 action=auto-fix
F-03 finding_uid: d0c82379af126720ac34 action=auto-fix
F-04 finding_uid: bdfd9615e276c6ec00c0 action=auto-fix
F-05 finding_uid: 3e14460632a43ef65a42 action=auto-fix
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 盤後「grep 當日 log 一行」這條判準在 server 沒重啟的日子會自打
**File**: `copycat/server/stock_engine.py`
**Line**: 1106

**Comment**:
```
這行只在兩個時點印:次日早上 stage2(帶舊日)跟 close()。但 log 檔名是啟動當下
`server-%Y%m%d-%H%M.log` 定死的(__main__.py:127,全 repo 沒 rotating handler)——
server 從 D−1 連跑到 D+1 的話,D 日那行會在 D+1 早上 08:45–09:00 才印、而且寫進
D−1 命名的檔;`logs/server-<D>.log` 根本不存在 → CLAUDE §4:520 / verification §6.2
寫的 `grep "個股旗標 0" logs/server-<日>.log` 必零行,分不出「健康長跑」跟「engine 漏印」。
同日重啟兩次也會變兩行部分計數,判準卻寫「一行」。

機制本身沒錯(快路徑也經 _log_flag_stats),要改的是文件:
判準改 `grep 個股旗標 logs/server-*.log` 不限檔、看訊息尾的 (<交易日>) 對日,
並註明「同日多次重啟 = 多行、桶相加」。真要每日一落,候選掛載點是 signal_hub.py:1363–1386
那條每日 policy_outcome_time(13:40)的回填 worker 迴圈 —— 能不能共用、要不要為它多開一個
hook 沒驗過,只是指路,不是這條的修法。
```
#### #2 達錢哪天多送個「3」,這行三個數字會全部看起來很健康
**File**: `copycat/server/stock_engine.py`
**Line**: 127

**Comment**:
```
0 / 欄缺 / 總 三桶印得出來,但「走 derive_side 退路的筆數」推不出來——
未知值(不是 0 / 1 / 2)靜默退回簿比,判定率悄悄回 ~80%,這行零訊號。
next-time 09-15 節自己就排了 09-16 08:59 抓試撮 / 集合競價的旗標值,
等於預期值域可能不只三個;prod 唯一儀器又是這行(/api/health 刻意不含)。

不動這行字面(round-1 Spec-S-01 反駁成立),改加一則「當日首見未知旗標值」WARNING、
一天一次帶值,照既有節流樣板寫:signal_hub.py:411 `_multi_group_warned: set[str]`
(:719 換日 clear)/ :788 排除組名對不上的 WARNING,或 trading_calendar.py:93 `_warned_years`。
```
#### #3 旗標欄送 null 的話會變成字面 "None",正好躲過「欄缺」這個唯一訊號
**File**: `copycat/live/stock_models.py`
**Line**: 248

**Comment**:
```
str(msg.get("FlagOfBuySell", "")) 對「欄在、值是 JSON null」會得到 "None"
→ 不進欄缺、不進 0、也對不到 _FLAG_SIDE,靜默退路、兩桶雙 0;
CLAUDE §4 寫的「欄缺桶非 0 = 格式漂了(唯一訊號)」對這型漂移看不到。
(全檔 Security / PreciseTime / TradeDate 同樣板,但那幾欄漂掉會被下游 parse 擋,
這欄失效是純靜默;09-14 抓檔 49,610 則零 null,是假設情境。)

raw = msg.get("FlagOfBuySell")
flag = str(raw) if raw is not None else None

加一案 `"FlagOfBuySell": None → flag is None` 釘住。
```
#### #4 這個 `not is_futures_key(code)` 59 行前已經算過一次叫 `arms_the_day`
**File**: `copycat/server/stock_engine.py`
**Line**: 1340

**Comment**:
```
:1281 `arms_the_day = not is_futures_key(code)` 跟這裡是同一個謂詞,
同函式兩個名字,讀的人要自己確認「武裝換日的現貨鍵」跟「計數母體的現貨鍵」是不是同一件事。
成本可忽略(startswith),但這是每 tick 的熱路徑、順手就好:

if arms_the_day:  # 武裝換日 = 現貨鍵 = 旗標計數母體,同一把尺

或改個中性名 is_spot 兩處共用。刻意要留兩個概念的話在註解講一句。
```
#### #5 新常數跟下一顆常數的 `#:` 說明黏在一起了
**File**: `copycat/server/stock_engine.py`
**Line**: 127

**Comment**:
```
_FLAG_STATS_FMT 那行下面直接接 `#: TradeStatus 轉態觀測的…`,
`#:` 是「說明下一個定義」的慣例,兩顆常數黏成一塊第一眼會以為那段在講 _FLAG_STATS_FMT。
加一行空白就好,既有行不動。
```
