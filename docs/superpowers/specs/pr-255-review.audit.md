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

## Spec 依據

- 此 PR 未附正式 spec / plan 文件;originating 依據 = `/mod` 流程 artifact `.claude/mod/stock-side-flag/change-spec.md`(§1 做 / 不做、§2 T1–T3 設計、§3 測試 1–8、§4 白名單、§5 驗證、§6 commit 切法;grilling 定案、小活分流不開 issue)+ `current-state.md`(caller map / 09-14 抓檔 / 09-15 側車對帳數字)。按一般 PR 流程 review,§1「不做」四項(回補零改動 / `_eval_sweep` 不動 / 前端零改動 / `TradeVolume` 恆 0 survivors 雙計另開 /bug)視為 scope 排除。two-axis round-1(`code-review-round-1.json`)已處置 7 條:S-01 / S-03 / S-04(部分)/ S-05 / Spec-S-02 接受收修,S-02 / Spec-S-01 反駁附理由 —— 本輪 reviewer 已讀該檔、不重提被反駁的兩條(F-02 以另一條路提出、附新論據)。
- **⚠️ spec 作者 = PR 作者**(change-spec / current-state / CLAUDE §4 契約條 / next-time 均由 loger-w 於同一分支寫成;「不做」清單是作者自訂的 scope 邊界 —— 本輪五條 finding 無一落在該清單內,不受其保護亦不與之衝突)。
- `SPEC_COMPLIANCE` receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_NORMATIVE_SPEC`(change-spec 為 grilling 定案的設計描述,`.claude/mod/` 路徑亦非 authority allowlist;無 MUST / SHALL 型 normative clause 可綁 path:line;0 clauses / 0 findings / 0 observations / 0 invalidated)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool calls N-A。
- Author calibration(Step 2.2):無作者校準檔(`loger-w.md` 不存在;`docs/pr-review-calibration/` 目錄不存在)、本輪無套用。

## 變更概要

provenance: N-A(base = master)。八筆 commit(PR head 序):test 紅先行 `c415d1d4` → fix `b1c3fd13` → feat `fec43340` → chore docs `d19b4b3d` → two-axis 收修 fix `9df04481` → chore `bd4368ea` → chore artifacts `a7d7a1cc` → chore graphify `b718366f`(SHA 為 PR head;master 上 rebase 後 SHA 已改寫,merge 結果 `d199149b`)。

| 檔案 | 變更類型 | 說明 |
|---|---|---|
| `copycat/live/stock_models.py` | M | `StockTick.flag: str \| None = None`(原始 `FlagOfBuySell`,不上 wire);模組級 `_FLAG_SIDE = {"1": "inner", "2": "outer"}` 唯一對映;`parse_stock_realtime` `flag = str(msg.get("FlagOfBuySell", "")) or None`、`side = _FLAG_SIDE.get(flag or "") or derive_side(...)`;`parse_hist_tick` 只加顯式 `flag=None` + 註解;`side` / `bid_ask` / `derive_side` docstring 改述成交後簿事實(數字指路 skill) |
| `copycat/server/stock_engine.py` | M | `_FLAG_STATS_FMT: str`;`__init__` 三個 int 計數;`_handle_quote` ingest 為真且非期貨鍵分支 +1 / 欄缺 / 0 分桶;`_log_flag_stats(day)`(INFO 一行 + 歸零)掛 `_rollover_stage2` assert 後第一句(帶舊 `_trade_date`)與 `close()` 的 `_loop = None` 之後 |
| `tests/live/test_stock_models.py` | M | `_FLAG_GOLDEN_PATH` 模組常數;`TestSideFromFlag` 8 案(旗標 2 壓 inner / 旗標 1 壓 outer / 0 退路 / 欄缺與空字串 / int 2 正規化 / 未知值退路 / hist 恆 None / 09-14 golden 三則) |
| `tests/server/test_stock_engine.py` | M | `TestFlagStatsLog` 3 案(stage2 舊日結算 + close 新日 / 零筆仍印 / 期貨鍵不計) |
| `tests/fixtures/stock_side_flag_golden.json` | A | 09-14 raw 抓檔三則逐字(2426 旗標 2 簿判 inner / 6209 旗標 1 簿判 outer / 5314 鎖跌停 Ask=0);`_source` 記 spec 指名 1312 無此型列改取 6209 |
| `CLAUDE.md` | M | §4 新契約條:`side` 產生點 `_FLAG_SIDE` + `derive_side` 退路、回補只有退路、讀者不變、漂掉症狀(判定率回 ~80% / `欄缺` 桶非 0 / 盤後 grep 零行)、釘住測試 |
| `CONTEXT.md` | M | 市場資料語意加「外盤」「內盤」「內外盤旗標」三詞條(各附 _Avoid_) |
| `docs/next-time.md` | M | 09-15 節:`TradeVolume` 恆 0 survivors 雙計 /bug 候選、09-16 08:59 排程抓檔只改文件、「前一列簿比先看」已拍板不做勿重提 |
| `.claude/skills/tc4-market-facts/SKILL.md` | M | 「同毫秒群 = 掃單」條改述 09-15 起 `side` 與掃單首筆外盤判準不等價;新條「REALTIME 帶成交那則五檔是成交後簿 / FlagOfBuySell 語意 / 歷史 TICKS 無旗標 / 回補規則對帳數字」 |
| `.claude/mod/stock-side-flag/{change-spec,current-state,verification}.md` + `code-review-round-1.json` | A | 流程 artifact(spec / 盤點 / 驗證證據 / two-axis 處置) |
| `graphify-out/**`(37 檔) | M/A | `graphify --update` 增量產物:29 檔 AST 重抽、12,647 → 12,773 節點、510 社群;code-only 零 token |

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

## CC 主軸原始 findings(first-pass, context-aware)

#### A-01 [MEDIUM] copycat/server/stock_engine.py:1106-1112 — 每日旗標行的落檔時機與「盤後 grep 當日 log」判準對不上,健康與「漏印」不可分辨
- 問題:`_log_flag_stats` 只有兩個呼叫點(stage2 / close);log 檔名在 process 啟動當下定死(`__main__._setup_prod_log`:`server-%Y%m%d-%H%M.log`,零 rotating handler),不隨日期輪替 → 不重啟時 D 日那行 D+1 早上才印且落啟動日檔;`grep "個股旗標 0" logs/server-<日>.log` 必零行。
- 機制追蹤:(a) `_handle_quote` 內 stage2 在 `state.ingest` 之前呼叫,觸發筆落新日,快路徑同經 `_log_flag_stats` 無旁路;(b) `close()` 呼叫在 `_loop = None` 之後、`gather` 之前(Spec-S-02 已知情);(c) reviewer 原查 `git grep Rotating copycat/` 零命中;main session 補查 repo-wide `RotatingFileHandler|TimedRotating|logging.config|dictConfig|fileConfig|FileHandler(` 對 py / toml / ps1 / json(排除產物目錄)零檔命中,`_setup_prod_log` :118–:135 是唯一檔案 sink、`path.open("a")` 一次、`run.ps1:9` 不重導向 —— 謂詞「沒有任何依日期重開檔的 sink」成立。
- 影響:判準在 no-restart 日誤報,反過來吞掉真漏印;同日多次重啟切成多行部分計數。
- 修法:文件層 —— 判準改 `grep 個股旗標 logs/server-*.log` + 比對訊息尾 `(<交易日>)`,註明多次重啟多行相加;「每日一落」的候選掛載點 = `signal_hub.py:1363–1386` 每日 `policy_outcome_time`(13:40)回填 worker 迴圈(**只是指路、未驗證可共用**,不是本條修法)。
- anchor: `    def _log_flag_stats(self, day: str) -> None:`

#### A-02 [LOW] copycat/server/stock_engine.py:127 / stock_models.py:256 — 未知旗標值靜默走退路,三個數字推不出退路筆數(與已反駁 Spec-S-01 不同解法)
- 問題:三桶都印但 inner/outer 命中數沒印 → 退路筆數不可導出;值域漂移三個數字全健康。
- 新論據:不動 pinned 字面,另加「當日首見未知旗標值」WARNING(一天一次帶值),與 repo 既有節流 WARNING 樣板同款(main session 補查 file:line:`signal_hub.py:411` `_multi_group_warned` / :788 排除組名 WARNING;`trading_calendar.py:91–103` `_warned_years`);next-time 09-15 節自己排了抓試撮 / 集合競價旗標值 = 預期值域可能不只 0/1/2。
- anchor: `_FLAG_STATS_FMT: str = "個股旗標 0:%d 筆 / 欄缺 %d 筆 / 總 %d 筆(%s)"`

#### A-03 [LOW] copycat/live/stock_models.py:248 — `str(msg.get("FlagOfBuySell", ""))` 對 JSON null 產出字面 "None",打掉「欄缺」唯一漂移訊號
- search-proof:`grep -n "str(msg.get" stock_models.py` → Security / PreciseTime / TradeDate 同款全檔一致;別欄漂掉會被下游 parse 擋,本欄失效純靜默。
- 修法:`raw = msg.get("FlagOfBuySell"); flag = str(raw) if raw is not None else None`。
- anchor: `    flag = str(msg.get("FlagOfBuySell", "")) or None`

#### A-04 [LOW] copycat/server/stock_engine.py:1340 — `is_futures_key(code)` 同函式第三次求值,同謂詞已算成 `arms_the_day`(:1281)
- 修法:`is_spot = not is_futures_key(code)` 算一次兩處用,或就地 `if arms_the_day:` + 註解點明同一判準。
- anchor: `            if not is_futures_key(code):`

#### A-05 [LOW] copycat/server/stock_engine.py:127-130 — 新常數與下一個 `#:` doc 註解之間缺空行
- 修法:加一行空白,不碰既有行。
- anchor: `_FLAG_STATS_FMT: str = "個股旗標 0:%d 筆 / 欄缺 %d 筆 / 總 %d 筆(%s)"`

reviewer 明確查過但**不**成立(避免下游重提):`StockTick` 加欄不影響去重 / 相等(survivors 走 `cum_vol`,全 repo 無 `set[StockTick]` / tick 相等比較);`flag` 未上 wire(`snapshot()` 六鍵、`_flush_ticks` 十鍵逐字確認);期貨 / corr 共用 `parse_stock_realtime` 無行為差(`.side` 讀者只 stock_state / stock_engine / relabel);回補列不污染計數(`apply_backfill` 不經 `_handle_quote`);S-02 / Spec-S-01 不重提。

## Codex 原始 findings(first-pass, diff-only)

N-A —— Codex 軸未啟用(user 已停用;沿 #188 / #190 / #199 / #230 / #238 / #253 前例)。零 Codex finding。

## Opus 對 Codex 的複查結果

N-A —— 無非 CC 軸 finding 可複查(Codex 中性 / 對抗 / Gemini 皆未啟用)。

## Codex 對 Opus 的複查結果(對稱化 4.2)

Codex 軸未啟用 → 本段以 **main session 內部逐條事實核**代替(同軸,**非跨軸證據**;所有 verdict 皆為 main session 自查、對 worktree code 逐字比對,不具備 4.2 設計的獨立性)。5 條全 non-strict-liability。

| Opus # | Opus reviewer | Opus title | Verdict(內部) | 原始 → 校正 severity | 內部 evidence | 備註 |
|---|---|---|---|---|---|---|
| A-01 | python-reviewer | 每日旗標行落檔時機 vs grep 當日 log 判準 | CONFIRMED | MEDIUM→MEDIUM | `__main__.py:127` `datetime.now().strftime("server-%Y%m%d-%H%M.log")` 啟動時一次;`grep -rn Rotating copycat/` 零命中;判準句 CLAUDE.md:520 / verification.md:51 逐字含 `logs/server-<日>.log`;stage2 / close 兩呼叫點逐字 | 4.3b lone:他軸 N-A 無從比較;機制正確、缺陷在文件判準 → 不降級 |
| A-02 | python-reviewer | 未知旗標值零訊號 | CONFIRMED | LOW→LOW | :127 字面三桶;`_handle_quote` :1340–:1346 只分 None / "0",其餘值只 +total;next-time.md 09-15 節第二條確有 09-16 抓檔 | 4.3b lone:與 round-1 Spec-S-01 反駁不衝突(不改字面);假設情境(09-14 零未知值)→ 維持 LOW |
| A-03 | python-reviewer | JSON null → "None" | CONFIRMED | LOW→LOW | :248 逐字;`python -c 'print(str(None))'` = `None`;09-14 抓檔旗標欄零 null | 4.3b lone:假設性(6d-1 hedge)→ Nice to Have 上限 |
| A-04 | python-reviewer | `is_futures_key` 重複求值 | CONFIRMED | LOW→LOW | :1281 `arms_the_day = not is_futures_key(code)` / :1340 `if not is_futures_key(code):` 逐字 | 4.3b lone:可讀性項,無行為差 |
| A-05 | python-reviewer | 常數後缺空行 | CONFIRMED | LOW→LOW | `sed -n 126,129p` :127 → :128 無空行 | 4.3b lone:格式項 |

## Action Items

**校準套用**:無作者校準檔(`loger-w.md` 不存在)、本輪無套用。6c Refactor Intent Gate:本 PR 無「移除 / 削弱既有防護」類 finding,免。6d-1:F-03 為假設性情境(null 未觀察到)cap Nice to Have;F-02 同為預期值域外的假設 cap Nice to Have。6d-3:無 Must Fix 候選(F-01 為文件判準錯,不修不壞會出貨的東西 → Should Fix)。Provenance cap:N-A(base = master)。

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

- **F-01** 判準文件改口:CLAUDE.md §4 :520 與 verification.md §6.2 的 `grep "個股旗標 0" logs/server-<日>.log` → `grep 個股旗標 logs/server-*.log` 對訊息尾 `(<交易日>)`;註明同日多次重啟多行相加。(MEDIUM,內部 CONFIRMED;runtime 零改動)

### Nice to Have(可選優化)

- **F-02** 當日首見未知旗標值 WARNING 一則(節流一天一次、帶值),不動 `_FLAG_STATS_FMT` 字面。
- **F-03** `flag = str(raw) if raw is not None else None` + 一案測試。
- **F-04** :1340 改 `if arms_the_day:` + 註解,或中性名 `is_spot` 兩處共用。
- **F-05** :127 後補一行空白。

### 參考用

無(五條皆 CONFIRMED,無 REFUTED / OUT_OF_SCOPE)。

## 審查工具比較 (qualitative)

- CC 主軸(python-reviewer,context-aware):5 條全落「儀器 / 判準 / 可讀性」層,主路徑(旗標優先 + 退路、計數掛 ingest 為真且非期貨鍵、stage2 前置結算、close 後置結算)逐條追過零缺陷;白名單六條讀 code 驗過零破壞。F-01 是唯一有實際觀測後果的條(盤後判準會誤報),其餘四條為 Nice。
- Codex 中性 / 對抗、Gemini 軸:N-A(user 已停用),重疊率無法計算;4.1 N-A;4.2 由 main session 內部事實核代替(CONFIRMED 5 / REFUTED 0 / PARTIAL 0 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0),**非跨軸證據**、REFUTED 率 0% 不可解讀為 first-pass 命中率。
- 對抗式第三軸增益:N-A。
- 與 two-axis round-1(merge 前)的關係:round-1 七條中五條已收修進本 PR;本輪五條全為新條(F-02 為 Spec-S-01 的替代解法,附新論據,不是重提)。

## 沒做的部分(結案對帳)

- Codex 中性軸:N-A(user 已停用)。
- Codex 對抗軸:N-A(user 已停用)。
- Gemini Flash / Pro 軸:N-A(user 已停用;2.96 未問、按前例)。
- Codex preset(2.98):N-A(未問、按前例)。
- Cross-axis verification 4.1:N-A(無非 CC finding);4.2:以 main session 內部事實核代替 PASS,**非獨立跨軸證據**;4.3a:N-A(無 consensus);4.3b:逐條備註 PASS。
- Blast radius(2.9):跑了、空輸出跳過(`sem` 未安裝)。
- React-doctor(2.97):N-A(非 React PR)。
- Formal spec traceability(2.65):SKIPPED (C4_NO_NORMATIVE_SPEC);C4 permit hook 未裝(Windows 未 patch),本輪 gate 本就 SKIPPED 不受影響。
- Author calibration(2.2):無檔、無套用。
- 逐檔覆蓋:46/46(covered 4 / no-issues 9 / skipped 37 generated / missed 0)PASS。
- 未驗證前提:F-03 的 null 情境與 F-02 的值域外情境皆為**假設**(09-14 抓檔 49,610 則零 null、去重 6,320 筆值只有 0/1/2),已標 hedge 並 cap Nice to Have;F-01 的「server 不重啟跨日」為 prod 常態(memory 多筆「prod 未重啟」),不是假設;F-01 修法內「13:40 回填 worker 可掛每日一落」**未驗證可共用**,已改成指路語式。
- Self-Verify(Step 6):`skill-verify-auditor`(requested=opus / observed=UNAVAILABLE,0 tool uses / 22 s)對第一版草稿判 `VERDICT: VIOLATIONS: R6, R8`,R1–R5 / R7 / R9 / R10 PASS。已修正:**R6** —— F-01 的「零 rotating handler」原只給 `grep Rotating copycat/`,補跑 repo-wide 六種 sink 謂詞(`RotatingFileHandler|TimedRotating|logging.config|dictConfig|fileConfig|FileHandler(`,py / toml / ps1 / json)零檔命中 + `_setup_prod_log` :118–:135 唯一 sink + `run.ps1:9` 佐證,謂詞語意寫明;**R8** —— F-01「13:40 日終 task」補 `signal_hub.py:1363–1386` file:line 並改為未驗證指路語式,F-02「節流 WARNING 樣板」補 `signal_hub.py:411 / :719 / :788 / :837` 與 `trading_calendar.py:91–103` 第一手 file:line。修正後**未重派 auditor、未經第二次獨立稽查**。
