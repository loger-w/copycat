# PR #238 Code Review 比較報告 · SHA e0dbd2c5
**Report projection schema**: 1

**PR**: [loger-w/copycat#238](https://github.com/loger-w/copycat/pull/238)
**標題**: mod: 批 A 真錢正確性五件(#232)—— policy_ctx 族群快照 / 回報鏈量測去污染 + chain-stats / 回報線辨識 / 時鐘偏差監測 / networkMode always
**作者**: loger-w
**分支**: `mod/batch-a-real-money` → `master`
**變更**: 30 檔案, +1,678 / -56
**審查日期**: 2026-09-14
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨;merge commit `d9c39023`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `e0dbd2c559107ff81529a35827a5bb8d44c49d6c`;destination repo id `R_kgDOTsITBg` + baseRefOid `285c4b11b61d11ecb61b64669e3ecce7a5e5a77b`;`input_binding: verified` —— `git fetch origin refs/pull/238/head` 取回的 FETCH_HEAD = headRefOid 逐字相等,review worktree detached 於該 SHA,`git merge-base origin/master HEAD` = baseRefOid
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 SHA;分支已隨 `--delete-branch` 刪除,但 `refs/pull/238/head` 仍指 `e0dbd2c5`,產報告前重抓 headRefOid 仍為它);`base_changed=true`(origin/master 自 `285c4b11` 前進至 `d9c39023`,內容 = 本 PR 自身 9 筆 rebase 後 commit,其後零新 commit);`review_context_changed=false`(審的是 PR head,與落地版逐檔等價)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示「以單軸跑」,沿 #188 / #190 / #199 / #202 / #211 / #218 / #220 / #222 / #228 / #230 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer ×2 chunk instances(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .py 佔 source diff 行 91%(1,355 / 1,488),chunked 派工:chunk A = 14 source + 7 非 source 檔、chunk B = 9 測試檔);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE;純讀碼 + grep + 合成輸入實跑 + 突變體 scratch 副本實跑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=30 → covered 13 / no-issues 16 / skipped 1 / **missed 0**(chunked: **是**,24 source 檔 / 1,734 diff 行,超過 15 檔 / 800 行門檻 → 2 chunks(21 / 9,非 source 檔亦各有 owner);30/30 per-file accounting 齊;唯一 skipped = `evidence/t2-offline-save-failed.jpeg` 二進位截圖)
**定位 (ENH-B)**: anchored exact 22 / ambiguous 0 / **FAILED 0**(22 條 anchor 在 worktree 逐字唯一命中:chain_stats.py:74 / CLAUDE.md:127 / client.py:852 / :848 / :308 / :438 / app.py:1163 / clock_monitor.py:74 / :68 / signal_hub.py:198 / signal-model.ts:98 / query-client.ts:24 / test_chain_stats.py:130 / :133 / :103 / test_reply_watch.py:37 / :67 / :18 / test_clock_monitor.py:208 / :157 / test_fill_latency.py:179 / :257;reviewer 自報行號與重定位一致)
**React-doctor (2.97)**: 未引入新問題(`npx -y react-doctor@latest . --offline --no-score --scope changed --base 285c4b11 --json` 於 review worktree `frontend/` 執行(npm ci 後),`newCount 0 / fixedCount 0 / baseTotalCount 0`,changedFileCount 6,`ok: true`)
**Formal spec traceability (2.65)**: SKIPPED (C4_SPEC_NOT_IN_REPO)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出;`sem` 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer ×2 chunks)PASS(22 raw findings:A 12 / B 10;30/30 accounting;chunk A 另實跑 5 個觸及測試檔 88 passed + 合成 log / 假 SNTP 封包探針;chunk B 實跑指派範圍 141 passed + 全量 3386 passed / 3 skipped + ruff / pyright + 修前還原實跑紅→綠 + 突變體)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 請求體解析 / 秘鑰讀取;`clock_monitor` 的對外 UDP 是唯讀 SNTP 查詢,不在 trigger 清單)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(22/22 verdict 齊、ID 集合精確相等、每列五欄齊;另裁決八處矛盾)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-238`
**worktree HEAD**: `e0dbd2c559107ff81529a35827a5bb8d44c49d6c`

**Report generation**: sha256:a3d688ad5e6d26d75aec7ccbc99ee8f1cd7e274fd12590c28923a770e257fc48

---
## [完整證據副檔](pr-238-review.audit.md)
### finding_uid 索引
[041096602db654e10634](pr-238-review.audit.md#發現總覽) · [71ffce17c05ba87bf862](pr-238-review.audit.md#發現總覽) · [b46bdbf25f0327356e62](pr-238-review.audit.md#發現總覽) · [2464e0297847fed7048c](pr-238-review.audit.md#發現總覽) · [9ecbb4a67e91a703f2b6](pr-238-review.audit.md#發現總覽) · [9814359038d4b2804e00](pr-238-review.audit.md#發現總覽) · [b6cd3154b96210bfb721](pr-238-review.audit.md#發現總覽) · [a0139b7d97eb343e4801](pr-238-review.audit.md#發現總覽) · [7c6349f99c252bf273e1](pr-238-review.audit.md#發現總覽) · [4e6865f2f8bc956e0480](pr-238-review.audit.md#發現總覽) · [736e9eb90ed20879afca](pr-238-review.audit.md#發現總覽) · [b66e656456401e9c77d7](pr-238-review.audit.md#發現總覽) · [723a78fa1a2e747cc626](pr-238-review.audit.md#發現總覽) · [aa60ee08b28936f050bf](pr-238-review.audit.md#發現總覽) · [51aabf7cfec86e8ba64d](pr-238-review.audit.md#發現總覽) · [8efad9a32d4ce447081b](pr-238-review.audit.md#發現總覽) · [845f3350c0cba69db5b8](pr-238-review.audit.md#發現總覽) · [7e50e8da6584fb578c48](pr-238-review.audit.md#發現總覽) · [2fc67c004d090e7f8a73](pr-238-review.audit.md#發現總覽) · [9bf78f892e2bc0687f90](pr-238-review.audit.md#發現總覽) · [945f105631b17dabf069](pr-238-review.audit.md#發現總覽) · [a7fa7423169a81d19c0e](pr-238-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `test_chain_stats.py:130` parity 測試只釘 log「訊息」半邊:prod 前綴格式(`__main__.py:144` 的 `basicConfig(format=…)`)在測試裡是第二份手抄字面,零程式連結;改 prod format → `_STAGE_RE` 全不中 → `chain-stats` 印「回報鏈 0 條」而 CLAUDE §1 判準 `non_monotonic = 0` 字面通過(半靜默偽 PASS);round-1 S-01 disposition 宣稱「走 prod basicConfig format」與碼不符 | MEDIUM | CONFIRMED(MEDIUM→MEDIUM:突變體實跑 —— 改 `__main__.py:144` 加 `[%(threadName)s]` 後 27 passed 全綠,同 format 真行餵 `summarize` 得「回報鏈 0 條,乾淨 0 條(排除:無)」;`test_shutdown_budget.py:70-80` 讀 `run.ps1` 原文是同款判例) | Nice to Have | `auto-fix` | 讀 `__main__.py` 原文斷言 format 字串逐字存在,或抽成模組常數同源;零 runtime |
| F-02 | `test_reply_watch.py:67` 白名單「不重連」那半邊零覆蓋:只斷 `status == "ok"`(證「不翻 degraded」),`FakeCom.connect_reply` 無計數器;verification §3 把這格證據寫成「`test_reply_watch` 斷 status == ok」名實不符 | LOW | CONFIRMED(LOW→**MEDIUM**:突變體在 `client.py:848` 後插 `connect_reply(...)`,`tests/capital` 436 passed + `test_capital_api` 84 passed 全存活;spec #232 白名單逐字有「不新增自動重連」;repo 對「不做某事」一貫以計數斷言釘,`test_fill_latency.py:258` `balance_queries() == 1` 同款) | Nice to Have | `auto-fix` | `RecordingCom` 建 client 斷 `"connect_reply" not in com.calls`,或 FakeCom 加計數;verification §3 證據欄改寫 |
| F-03 | `chain_stats.py:74` `_classify` 只查首段 = 庫存段 / 末段 = 落地,中段可缺:pending 8 s 逾時強制落地(2 段)與 `get_profit_loss_gw` rc≠0 跳損益段(3 段)都進乾淨子集;CLAUDE §1 與 docstring 寫「四段累積值單調」是過度承諾 | LOW | PARTIAL(LOW→LOW:機制以合成行實跑證實;影響以 prod 198 條真語料量測 —— 段數 `{2:2, 3:3, 4:193}`,乾淨 150 條裡只 1 條缺段,剔除後 p50/p90/p99 1953/3027/6433 vs 已發布 1952/2993/6433,p99 不動、p90 差 1.1%;剔除後 p90 3027 恰等於研究 V2 §2.3 四段手算) | Nice to Have | `auto-fix` | 加 `partial_chain` 分桶(與既有五種排除同形)並把 CLAUDE §1 / docstring 改成實際口徑;尺沒壞 |
| F-04 | `CLAUDE.md:127` 基線是「新尺量舊 log」:舊碼無條件覆寫 `_fill_seen_at`,輪詢鏈飛行中到達的成交被 `no_start` 排除(4 條)、無乾淨樣本;新碼遞延到下一輪量,母體換了一批;下一批看 p90 上移會誤判 regression | LOW | PARTIAL(LOW→LOW:母體換批成立;但重建新碼口徑(誤差 max 1 ms)併入 6 條 `non_monotonic` 去污染樣本後 p50 1952→1950、p90 / p99 零位移,「系統性上移」不成立;只剩 4 條 `no_start`(2.6%)結構上無法重建) | Nice to Have | `auto-fix` | 該列補一句「基線由舊 client log 算出,重啟後首日數字寫回取代;兩邊 p90 / p99 不直接相減」 |
| F-05 | `client.py:308` `_set_status("ok")` 重置區塊沒清 `_fill_seen_at` / `_fill_count` / `_chain_started_at`;區塊自述「清點必須與 `_finalize_positions` 同組」,而 #234 後 `_finalize_positions` 清五項、這裡清三項;今天唯一 caller 是 `_init_com`(初值)無行為差,下一批接重連即成 p99 假右尾 | LOW | CONFIRMED(LOW→LOW:兩處清點清單逐欄比對;`_finalize_positions` :672-696 已變五項;spec Out of Scope 擋「接重連」不擋「同組清點補齊」) | Nice to Have | `auto-fix` | 三欄加進同組清點 + 註解點名「量測欄與守門旗標同組清」 |
| F-06 | `app.py:1163` 關機註解「`to_thread` 裡的 UDP 最多再等一個 timeout(2 s)」低估三倍:`probe` 依序試三台各 2 s + DNS,`to_thread` 執行緒不可 cancel、`shutdown_default_executor` 會 join;`shutdown_budget.py` 算式不含此段 | LOW | CONFIRMED(LOW→LOW:`probe` :81-92 迴圈 + `TIMEOUT_SECS` 2.0;83 s 預算完全吃得下(健康路徑 1–3 s),不會觸發 taskkill;CLAUDE §4 三方同源條明訂可計段要進算式或標註不計) | Nice to Have | `auto-fix` | 註解改「最壞 = len(NTP_HOSTS) × TIMEOUT_SECS(+DNS),執行緒不可 cancel」並在 `shutdown_budget` 列一項或明標不計 |
| F-07 | `clock_monitor.py:74` `t0` 在 DNS 解析之前取(`sendto((host,123))` 才 getaddrinfo),解析耗時全算去程 → offset 偏 dns/2、RTT 膨脹 dns;首發在 server 啟動當下(冷 DNS),正是 verification §2.2 T1 判準「首行 \|offset\| < 250 ms」那一行 | LOW | PARTIAL(LOW→LOW:注入延遲實跑 d=100 → offset −53.1 ms / d=500 → −253.3 ms,量級 d/2 對、**方向是負向**(finding 寫正向,反了);緩解 = INFO 行本身印 RTT,第二發起 DNS 已快取) | Nice to Have | `auto-fix` | `_udp_exchange` 先 `getaddrinfo` / `connect` 再取 t0;判準補「首行 RTT < 100 ms」 |
| F-08 | `signal-model.ts:98` `policy_ctx` JSDoc 只列 `no_ref` / `no_group`,同段 union(:114)與 CLAUDE §4 已含 `error`(085eb880 收修漏改);`PeerSnap` JSDoc(:25)仍寫「政策列的…`_emit_policies`」;round-1 P-03 disposition 宣稱「前端 union」已改為真但不完整 | LOW | CONFIRMED(LOW→LOW:註解與 union 同段互斥,肉眼可證;parity 測試缺席半邊份量低 —— `policy_ctx` 明文「前端不讀」,同批 `reply_connected` 同待遇,有 parity 的值域全是前端會讀的) | Nice to Have | `auto-fix` | 兩段 JSDoc 補 `error` / `_policy_context`;parity 測試不強求 |
| F-09 | `query-client.ts:24` `{ ...MUTATION_DEFAULTS, ...defaults.mutations }` 呼叫端後蓋:`createQueryClient({mutations:{networkMode:"online"}})` 可靜默關掉 #237 真錢保護,測試只釘現有兩個呼叫形狀;`MUTATION_DEFAULTS` export 零外部讀者 | LOW | PARTIAL(LOW→LOW:機制與零讀者 CONFIRMED;可利用性弱 —— 今天只有 `main.tsx` / `test-utils.tsx` 兩個呼叫端且都不傳 `mutations`;更大的洞(49 檔 `new QueryClient(`)已由 round-1 S-02 進 next-time) | Nice to Have | `auto-fix` | 展開順序反過來讓安全預設最後贏(三個字元)+ 補一案「傳 online 仍得 always」;拿掉 export |
| F-10 | `test_chain_stats.py:133` `log.setLevel(logging.INFO)` 未還原(`finally` 只 `removeHandler`),`copycat.capital.client` logger level 永久 INFO,檔名排序早於 test_client / test_fill_latency / test_store → 順序相依地雷 | LOW | CONFIRMED(LOW→LOW:scratch 加一支 `test_zzz_levelcheck` 斷 level == NOTSET → FAILED(20 == 0),其餘 436 passed;全 repo 只有 `test_ws_disconnect.py:157 / :615` 動 logger 且都不改 level) | Nice to Have | `auto-fix` | 改 `caplog.set_level` + 自行 `Formatter.format(record)`,或 finally 還原 level |
| F-11 | `test_reply_watch.py:37` `_probe_lines` 濾字「回報線」太寬:`client.py:853` 的耗時 WARNING「群益回報線 IsConnectedByID 耗時…」也命中,cost > 50 ms(GC / 防毒停頓)時三處 `==` 與一處 `len == 1` 一起紅,訊息誤導方向 | LOW | CONFIRMED(LOW→LOW:子字串包含與 caplog 層級可直讀;13 輪壓力未觸發,屬低機率 flake;同批 `_elapsed_info` 已用 `r.name` + 精準 regex 收窄) | Nice to Have | `auto-fix` | 濾 `"IsConnectedByID=" in msg`(耗時行無 `=`) |
| F-12 | `test_fill_latency.py:257` 三個小韌性 / 風格點:(a) :249 `_elapsed_info(caplog)[0] >= 500` budget 用盡時裸 `IndexError` 無訊息(:293 同形);(b) `_landed_info` 不濾 `r.name`,與 `_elapsed_info` 口徑不一;(c) lambda 賦值 + `# noqa: E731`(全 tests/ 唯一)與 lambda broadcast + `# type: ignore`,同檔既有慣例是 `def` | LOW | CONFIRMED(LOW→LOW:三點逐行確認;`# noqa: E731` repo 唯一先例是 `app.py:823`,tests/ 無第二處) | Nice to Have | `auto-fix` | 先斷非空帶訊息;`_landed_info` 補 `r.name`;兩個 lambda 改 `def` |
| F-13 | `client.py:852` `IsConnectedByID 耗時` WARNING 零節流:若 COM 呼叫本就 60–80 ms,每 10 s 一行、盤中 ~2,480 行(非 8,640),WARNING 占比 9% → ~34%,淹掉「回報線 / Solace」值序列 | LOW | PARTIAL(LOW→LOW:零節流 CONFIRMED;觸發前提(COM 耗時)未實證且正是探針要量的;next-time 判準本就二元、時限一個交易日;低頻逐筆 WARNING 有先例 `client.py:571` rc= 當日印 342 次未爆) | Nice to Have | `ask-user` | 現在就加「首次 + 每日一次」節流,還是等第一個交易日看數字 —— 若真的每 10 s 命中,那一天的 log 會很難讀 |
| F-14 | `client.py:848` `int()` 直接吃未實證的 COM 回傳,無自帶 try/except;非 int / COMError → `_pump_once` 傘 `logger.exception` + `sleep(1.0)`,`_run` 的 `_cmd_q.get` 排在其後 → 該輪送單 / 平倉命令多等 1 s;`_reply_probe_next` 已先推進故 10 s 一次不緊迴圈 | LOW | PARTIAL(LOW→LOW:後果半邊讀 `_run` 機械確認;前提半邊 INCONCLUSIVE(comtypes 回傳形狀無法在此環境實證);既有 COM 呼叫一律裸傳靠 caller 傘,差別是這支每 10 s 長跑) | Nice to Have | `ask-user` | 要不要給 `_probe_reply` 自帶 try/except + 連 3 次失敗停用探測;第一個交易日 log 會直接揭曉回傳形狀 |
| F-15 | `client.py:438` 「涵蓋 n 筆成交」把鏈起飛後才到的成交也算進 n,且那些成交的延遲樣本被丟棄(起點清空後下一輪走 DEBUG)—— 連續成交母體變窄;chain-stats 不讀 n 故百分位不受污染 | LOW | PARTIAL(LOW→LOW:「樣本丟棄」CONFIRMED;「文案不實」REFUTED —— `store.begin_snapshot` 水位 + `set_positions` 重套讓那些成交在**部位**意義上真的被涵蓋;實作與 spec #232 Implementation Decisions 第 4 條逐字相符) | Nice to Have | `ask-user` | 要「n 只算起飛前 + 未涵蓋者重設起點」(量測更完整)還是「改文案 + docstring 點明盲點」(最小動作) |
| F-16 | `clock_monitor.py:68` `recvfrom(48)` 在 Winsock 遇 > 48 bytes 回應是 WSAEMSGSIZE 失敗非截斷 → 該台恆失敗;`parse_offset` 無 LI=3 / stratum=0(KoD)檢查;docstring「Kiss-o'-Death?」掛在零時戳那句 | LOW | PARTIAL(LOW→LOW:recvfrom 半邊實跑 loopback 68 bytes → `WinError 10040` 證實,但 `probe` 的 `except OSError` 換台 + 三台全掛才 WARNING,失效是大聲的;KoD 半邊 INCONCLUSIVE,pool 的 RATE KoD 實務帶真時戳) | Nice to Have | `ask-user` | `recvfrom(512)` 只解前 48 + `response[0]>>6==3 or response[1]==0` → raise;是否值得動要看你對 NTP 邊角的容忍 |
| F-17 | `test_chain_stats.py:103` CLI「可多檔(依序合併)」語意(跨檔鏈接得起、1019 累加)零測試;不存在路徑直接 `FileNotFoundError` traceback 無收場定義 | LOW | CONFIRMED(LOW→LOW:`nargs="+"` 只 `test_chain_stats.py:103` 一處呼叫、單檔;`tests/test_cli.py` 對錯誤路徑有 exit 2 前例,`cli.py:292` 有收場慣例) | Nice to Have | `ask-user` | 加拆兩檔案(切在鏈中間)斷逐欄相同 + 不存在案釘 exit 2;要不要現在做還是併下一批 |
| F-18 | `test_reply_watch.py:18` `CapitalClient` 建構工廠又多兩份(本 PR 3 → 5 份:test_client / test_fill_latency / test_reply_watch / test_chain_stats / test_capital_api),六個必填參數逐字相同,`__init__` 一改五處 TypeError | LOW | CONFIRMED(LOW→LOW:grep 全 repo 五份;`tests/helpers/fake_sources.py:1-12` 檔頭是「散抄要上提」的明文判例) | Nice to Have | `ask-user` | 🔵 上提到 `tests/capital/client_fixture.py`;鐵則 B 要另批,併 test-hygiene |
| F-19 | `test_clock_monitor.py:157` `test_probes_immediately_then_every_interval…` 兩個宣稱都沒被斷言:interval 0.01 + 1 s 輪詢窗使「先量後睡 / 先睡後量」不可分;真正釘「立即量」的是同 PR 的 `TestAppWiring` | LOW | CONFIRMED(LOW→LOW:突變體(sleep 搬到迴圈首)實跑 1 failed / 20 passed,紅的是 `TestAppWiring`、此案綠;覆蓋無真缺口,是命名 / 責任歸屬) | Nice to Have | `ask-user` | 改名把責任明寫給 `TestAppWiring`,或 interval 5 s + 0.5 s 內斷首顆 |
| F-20 | `test_fill_latency.py:179` `_Broker` 是同檔 `_run_chain` 的嚴格泛化,兩份假券商並存,三份回覆列與 handler 綁定重複宣告 | LOW | CONFIRMED(LOW→LOW:`replies` dict 逐字相同,`_Broker` 對只答一輪的舊情境行為等價;09-09 PR #222 測試鷹架批是同型收斂判例) | Nice to Have | `ask-user` | 🔵 刪 `_run_chain`、兩個舊 caller 改 `_Broker`;鐵則 B 另批 |
| F-21 | `signal_hub.py:198` `_EMPTY_POLICY_CTX` 是 module-level 可變單例(frozen 只擋 rebinding,`groups` / `peers` / `hits` 是 list);今天 `_policy_ctx_payload` 全複製故安全,日後 `ctx.hits.append` 會永久污染 | LOW | PARTIAL(LOW→LOW:事實 CONFIRMED;風險 REFUTED —— 同型 pattern `stock_engine.py:68 _EMPTY_LIGHT` module-level 可變 dict 單例已存在且未爆,取用端一律 `dict(...)` 淺拷並有 :65-67 註解契約;真殘留 = 缺那句註解) | 參考用 | `no-op` | 非缺陷;要不要補一行「取用端一律複製」註解是品味,與 `_EMPTY_LIGHT` 同待遇 |
| F-22 | `test_clock_monitor.py:208` `from tests.server.test_app import FakeQuoteSource` 繞過共用件 `tests/helpers/fake_txo.py`,「全 repo 唯一一處跨測試檔 import」 | LOW | PARTIAL(LOW→LOW:「唯一」主張為假 —— `test_signal_outcome.py:22-23` / `test_signal_policy.py:28` / `test_signal_routes.py:43-44` 五處同型已在且未爆;`fake_txo.FakeTxoSource` 與 `test_app.FakeQuoteSource` 不是同一個類(前者全 no-op、後者可注入),替換可行但非等值;真正的重複在 `test_capital_api.py:39` 第三份 FakeQuoteSource) | 參考用 | `no-op` | 風格偏好、有先例;若日後收斂 QuoteSource fake 再一併 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 041096602db654e10634 action=auto-fix
F-02 finding_uid: 71ffce17c05ba87bf862 action=auto-fix
F-03 finding_uid: b46bdbf25f0327356e62 action=auto-fix
F-04 finding_uid: 2464e0297847fed7048c action=auto-fix
F-05 finding_uid: 9ecbb4a67e91a703f2b6 action=auto-fix
F-06 finding_uid: 9814359038d4b2804e00 action=auto-fix
F-07 finding_uid: b6cd3154b96210bfb721 action=auto-fix
F-08 finding_uid: a0139b7d97eb343e4801 action=auto-fix
F-09 finding_uid: 7c6349f99c252bf273e1 action=auto-fix
F-10 finding_uid: 4e6865f2f8bc956e0480 action=auto-fix
F-11 finding_uid: 736e9eb90ed20879afca action=auto-fix
F-12 finding_uid: b66e656456401e9c77d7 action=auto-fix
F-13 finding_uid: 723a78fa1a2e747cc626 action=ask-user
F-14 finding_uid: aa60ee08b28936f050bf action=ask-user
F-15 finding_uid: 51aabf7cfec86e8ba64d action=ask-user
F-16 finding_uid: 8efad9a32d4ce447081b action=ask-user
F-17 finding_uid: 845f3350c0cba69db5b8 action=ask-user
F-18 finding_uid: 7e50e8da6584fb578c48 action=ask-user
F-19 finding_uid: 2fc67c004d090e7f8a73 action=ask-user
F-20 finding_uid: 9bf78f892e2bc0687f90 action=ask-user
F-21 finding_uid: 945f105631b17dabf069 action=no-op
F-22 finding_uid: a7fa7423169a81d19c0e action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 這支 parity 測試釘的是自己手抄的 format,不是 prod 那一份
**File**: `tests/capital/test_chain_stats.py`
**Line**: 130

**Comment**:
```
sink.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")) —— 這串跟
copycat/server/__main__.py:144 的 basicConfig(format=...) 是同一串字面被抄了第二次,兩邊沒有程式連結。
實跑過:把 __main__.py 的 format 加個 [%(threadName)s],這檔 27 條照樣全綠,
但 chain-stats 對真 log 會印「回報鏈 0 條,乾淨 0 條(排除:無)」—— CLAUDE §1 的判準 non_monotonic = 0 字面上還「通過」。

照 test_shutdown_budget.py:70-80 讀 run.ps1 原文的做法:讀 __main__.py 原文斷言這串 format 逐字在裡面,
或把 format 抽成 __main__ 的模組常數、兩邊 import 同一顆。
```
#### #2 「不重連」這半白名單其實沒人擋
**File**: `tests/capital/test_reply_watch.py`
**Line**: 67

**Comment**:
```
assert client.status == "ok" 證的是「不翻 degraded」,證不到「不重連」——
在 _probe_reply 的 is_reply_connected 之後偷插一行 self._com.connect_reply(...),tests/capital 436 條 + test_capital_api 84 條全綠。
FakeCom.connect_reply 連計數器都沒有,結構上記不到。verification §3 把這一格的證據寫成「test_reply_watch 斷 status == ok」是名實不符。

用 RecordingCom 建 client,值翻 0 之後斷 "connect_reply" not in com.calls;或給 FakeCom 加個 reply_connect_calls(跟 reply_connected_calls 同款)斷恆 0。
verification §3 那一格順手改成真的證據。
```
#### #3 缺段的鏈會被算成乾淨樣本,文件說的「四段」是過度承諾
**File**: `copycat/capital/chain_stats.py`
**Line**: 74

**Comment**:
```
_classify 只看 stages[0] 是不是庫存段、stages[-1] 是不是落地,中間缺段不擋。
兩種真形狀會缺:pending 8 s watchdog 強制落地(只 2 段)、get_profit_loss_gw rc≠0 跳損益段(3 段)。
合成行餵進去都回 clean=1。不過拿 prod 198 條真鏈量過:段數分布 {2:2, 3:3, 4:193},乾淨 150 條裡只 1 條缺段,
剔掉後 p50/p90/p99 = 1953/3027/6433 vs 1952/2993/6433 —— 尺沒壞,只是 CLAUDE §1 跟 docstring 寫的「四段累積值單調」比程式嚴。
(剔掉後的 p90 3027 剛好等於研究 V2 §2.3 照四段手算的值。)

加一個 partial_chain 排除(set(stages) != set(_STAGES)),跟既有五種同形;或至少文件改成實際口徑。
```
#### #4 基線是拿新尺量舊 log 得來的,下一批別直接相減
**File**: `CLAUDE.md`
**Line**: 127

**Comment**:
```
「基線 2026-09-14(全部 log):乾淨 150 / 198 條,p50 1952 / p90 2993 / p99 6433」是對 09-14 前舊 client 的 log 跑新 chain-stats。
舊 client 每筆成交都重設起點,輪詢鏈飛行中到達的成交會被記成 no_start(4 條)、沒有乾淨樣本;新 client 把它遞延到下一輪量。
母體確實換了一批 —— 不過重建新碼口徑(誤差 ≤ 1 ms)把 6 條 non_monotonic 去污染後併回去,p90/p99 一格都沒動,
「系統性上移」沒發生,只剩 2.6% 的 no_start 結構上重建不了。

這一列補一句:「基線由舊 client log 算出;重啟後第一個交易日的數字寫回取代,兩邊 p90/p99 不直接相減」。
```
#### #5 重連的重置區塊沒清三個新量測欄,下一批接重連就會咬到
**File**: `copycat/capital/client.py`
**Line**: 308

**Comment**:
```
_set_status("ok") 這段自己寫「清點必須與 _finalize_positions 同組」,但 #234 之後 _finalize_positions 清的是
三個旗標 + _fill_seen_at + _fill_count 五項,這裡還是三項。今天唯一的 ok caller 是 _init_com、全是初值,沒差;
next-time 已排的「回報線修的那一半」接重連時會走這裡 → 斷線前的 _fill_seen_at 活到重連後第一輪鏈,
_chain_covers_fill() 成立,印出一條含斷線時長的「乾淨」樣本 —— 正是 #234 要消滅的那種假 p99。

_fill_seen_at / _fill_count / _chain_started_at 三個加進同組清點,註解點名「量測欄與守門旗標同組清」。
```
#### #6 這行註解把關機最壞等待低估了三倍
**File**: `copycat/server/app.py`
**Line**: 1163

**Comment**:
```
「to_thread 裡的 UDP 最多再等一個 timeout(2 s)」—— probe() 是 for host in hosts 依序試三台,每台 TIMEOUT_SECS 2 s,
外加 sendto 裡的 DNS 解析;clock_task.cancel() 只讓 await 早退,to_thread 那條執行緒照跑到底,asyncio.run 收尾的
shutdown_default_executor 會 join 它。最壞是 3 × 2 s + DNS。83 s 的關機預算吃得下(健康路徑 1–3 s),
但 CLAUDE §4「關機預算三方同源」要求可計段要進 shutdown_budget 算式或明標不計,這段兩邊都沒有。

註解改「最壞 = len(NTP_HOSTS) × TIMEOUT_SECS(+DNS),執行緒不可 cancel」;shutdown_budget 列一項或明標不計。
```
#### #7 t0 在 DNS 解析之前取,冷 DNS 那一發 offset 會偏
**File**: `copycat/server/clock_monitor.py`
**Line**: 74

**Comment**:
```
t0 = time.time() 在 exchange() 之前,而 _udp_exchange 的 sock.sendto(request, (host, 123)) 才做 getaddrinfo ——
解析耗時整段被算成去程,offset 偏 dns/2、RTT 膨脹 dns。注入延遲實跑:d=100 ms → offset −53 ms、d=500 ms → −253 ms
(方向是負向、本機看起來更落後)。第一發在 server 啟動當下,最可能冷 DNS,而那一行正是 verification §2.2 T1 的判準「首行 |offset| < 250 ms」。
好在 INFO 行本身印 RTT,看到 RTT 500 就分得出來;第二發起 DNS 已快取。

_udp_exchange 先 getaddrinfo(host, 123)(或 sock.connect)再取 t0;判準補一句「且 RTT < 100 ms」。
```
#### #8 JSDoc 只寫兩個 skip 值,union 已經有三個
**File**: `frontend/src/lib/signal-model.ts`
**Line**: 98

**Comment**:
```
「skip 是不評原因(no_ref / no_group,評了 = null)」—— 同一段第 114 行 union 是 "no_ref" | "no_group" | "error" | null,
CLAUDE §4 也寫四值;085eb880 收修加 error 時漏了上面這段散文。error 的語意正好相反(評了但炸了、其餘欄是空殼),
讀型別的人會以為「有 ctx 就是評過了」。這欄唯一的讀者是四週後的 jsonl 對帳,那時看的就是這段。
PeerSnap(:25)的「政策列的族群同伴快照(後端 _emit_policies 的 peers[])」同批漏改 —— 現在也是 policy_ctx.peers 的型別,產生點是 _policy_context。

兩段補上;跨語言 parity 測試不強求(這欄前端不讀,跟 reply_connected 同待遇)。
```
#### #9 呼叫端可以把 networkMode 蓋回 online,工廠沒守門
**File**: `frontend/src/lib/query-client.ts`
**Line**: 24

**Comment**:
```
mutations: { ...MUTATION_DEFAULTS, ...defaults.mutations } 是呼叫端後蓋 —— createQueryClient({ mutations: { networkMode: "online" } })
會把 #237 整個關掉,query-client.test.tsx 只釘了現有兩個呼叫形狀。今天只有 main.tsx / test-utils.tsx 兩個呼叫端且都沒傳 mutations,
所以是「沒守門」不是「已破」;更大的洞(49 檔 new QueryClient()）round-1 S-02 已進 next-time。
順帶 MUTATION_DEFAULTS 的 export 全 repo 零讀者。

反過來 { ...defaults.mutations, ...MUTATION_DEFAULTS } 讓安全預設最後贏(retry 等其他鍵不受影響),補一案「傳 online 仍得到 always」;export 拿掉。
```
#### #10 logger level 改了沒還原,整個 pytest session 都被污染
**File**: `tests/capital/test_chain_stats.py`
**Line**: 133

**Comment**:
```
log.setLevel(logging.INFO) 之後 finally 只 removeHandler,copycat.capital.client 這顆 logger 的 level 永久變 INFO。
在 tests/capital/ 加一支斷言 level == NOTSET 的檔跑全目錄:FAILED(20 == 0),其餘 436 passed —— 現在沒紅,
但 test_chain_stats 排序在 test_client / test_fill_latency / test_store 之前,之後任何「斷 caplog 沒多餘記錄」的測試會依順序時綠時紅。
全 repo 動 logger 的只有 test_ws_disconnect.py 兩處,都只 addHandler 不動 level。

改用 caplog.set_level(logging.INFO, logger=...)(pytest 會還原)再拿 Formatter.format(r) 把 caplog.records 格式化;或 finally 還原 level。
```
#### #11 濾字「回報線」會把耗時 WARNING 也撈進來,撞到三處 == 斷言
**File**: `tests/capital/test_reply_watch.py`
**Line**: 37

**Comment**:
```
_probe_lines 用 "回報線" in msg 篩,但 client.py:853 的「群益回報線 IsConnectedByID 耗時 … ms」也含這三個字,
而且是 WARNING ≥ 測試設的 INFO。FakeCom 是 µs 級、13 輪壓力沒觸發,但門檻是 50 ms 牆鐘,GC / 防毒停頓跨過去時
:53 / :61 / :66 / :71 四個斷言一起紅,錯誤訊息會指向「值變化 log 壞了」。

改成 "IsConnectedByID=" in msg 就好 —— 耗時行沒有那個 =。
```
#### #12 三個小地方:裸 IndexError、helper 口徑不一、lambda + noqa
**File**: `tests/capital/test_fill_latency.py`
**Line**: 257

**Comment**:
```
(a) :249 / :293 的 _elapsed_info(caplog)[0] 在 budget 用盡時丟裸 IndexError,同檔既有寫法都先斷非空帶訊息(:280 / :286)。
(b) _landed_info 只濾訊息不濾 r.name,跟旁邊的 _elapsed_info 口徑不一致。
(c) balance_queries = lambda … # noqa: E731 是 tests/ 唯一一處 lambda 賦值(repo 唯一先例是 app.py:823),
    :270-275 的 lambda broadcast 還帶 # type: ignore —— 同檔其餘 helper 全是 def。

先 elapsed = _elapsed_info(caplog); assert elapsed, "3 s 內沒有任何庫存段 INFO";_landed_info 補 r.name;兩個 lambda 改 def。
```
#### #13 耗時 WARNING 沒節流,真的每 10 s 命中會淹掉要看的那條線
**File**: `copycat/capital/client.py`
**Line**: 852

**Comment**:
```
if cost_ms > 50: logger.warning(...) 每 10 s 一次、沒有首次 / 每日 / 變化才印的閘。
COM 呼叫是不是本來就 60–80 ms 沒人知道 —— 那正是這根探針要量的;真的是的話,盤中約 2,480 行(拿 09-14 那份 log 算),
WARNING 占比從 9% 衝到 ~34%,「回報線 IsConnectedByID=…」的值序列會被埋掉。
next-time 的判準本來就只看有無命中,所以判準沒壞;是那一天的 log 會很難讀。

要拍板:現在就改成「首次 + 每日一次」(沿 _short_row_logged 的 (鍵, 交易日) 模式),還是等第一個交易日看數字再說。
```
#### #14 int() 直接吃 COM 回傳,炸了會讓送單命令那一輪多等 1 秒
**File**: `copycat/capital/client.py`
**Line**: 848

**Comment**:
```
value = int(self._com.is_reply_connected(self._user_id)) —— 註解自己說「語意未實證」,但形狀也未實證:
comtypes 對多 out-param 回 tuple、HRESULT 失敗拋 COMError,任一種都會落進 _pump_once 的傘 → logger.exception + time.sleep(1.0),
而 _run 的 _cmd_q.get 排在 _pump_once 之後 → 那一輪的送單 / 平倉命令多等 1 s。不會緊迴圈(_reply_probe_next 先推進了),
所以是每 10 s 一個 traceback + 一個 1 s 尖峰。會不會炸,第一個交易日的 log 立刻揭曉。

要拍板:_probe_reply 自帶 try/except、失敗記一次、連 3 次就停用探測(reply_connected 留 None),不讓它掉進共用的 sleep 傘。
```
#### #15 「涵蓋 n 筆成交」的 n 含起飛後才到的成交,那些成交的耗時永遠量不到
**File**: `copycat/capital/client.py`
**Line**: 438

**Comment**:
```
_fill_count += 1 無條件;_chain_covers_fill 只保證起點 ≥ 最早那筆成交。鏈起飛(_chain_started_at,跟 begin_snapshot 同刻)之後、
落地之前到達的成交會被計進 n,落地時 _fill_seen_at 一起清空,它武裝的下一輪走 DEBUG —— 那筆成交的「成交 → 落地」耗時永遠量不到。
文案倒不算假:begin_snapshot 水位 + set_positions 重套讓那些成交在部位意義上真的被這一輪涵蓋;實作也跟 spec 第 4 條逐字一致。
chain-stats 不讀 n,百分位不受影響,只是連續成交那一段母體變窄。

要拍板:n 只算起飛前的、其餘筆把 _fill_seen_at 重設成最早未涵蓋者(量得更完整);或改文案 + docstring 點明盲點(最小動作)。
```
#### #16 recvfrom(48) 在 Windows 上遇到超過 48 bytes 是失敗不是截斷;KoD 沒擋
**File**: `copycat/server/clock_monitor.py`
**Line**: 68

**Comment**:
```
Winsock 的 recvfrom 遇到 datagram 大於緩衝區回 WSAEMSGSIZE(loopback 實跑 68 bytes → WinError 10040),
帶 extension / MAC 的伺服器回應會讓那台恆失敗。不過 probe 的 except OSError 會換下一台、三台全掛才印 WARNING,失效是響的。
parse_offset 只擋 transmit=0,沒看 LI=3 / stratum=0(Kiss-o'-Death);pool.ntp.org 的 RATE KoD 實務上帶真時戳,所以「離譜 offset 假 ERROR」沒法在這裡重現。
docstring 的「Kiss-o'-Death?」掛在零時戳那句,依 RFC 4330 算寬鬆不算錯。

要拍板值不值得動:recvfrom(512) 只解前 48;parse_offset 加 response[0]>>6==3 or response[1]==0 → raise。
```
#### #17 chain-stats 的多檔合併跟檔案不存在兩條路沒測
**File**: `tests/capital/test_chain_stats.py`
**Line**: 103

**Comment**:
```
--log 是 nargs="+",help 跟 CLAUDE §1 都寫「可多檔(依序合併)」,實作是跨檔共用一個 generator —— 重點是切在鏈中間的兩檔要接得起來、1019 要累加。
TestCli 只餵一檔;有人改成 per-file 各自 summarize 再相加,鏈統計就悄悄變另一種東西,沒測試會紅。
不存在的路徑直接 FileNotFoundError traceback,收場沒定義(tests/test_cli.py 對 screen 的錯誤路徑有 exit 2 前例)。

加一案把 LINES 切在一條鏈中間分兩檔,斷言跟單檔逐欄相同;加一案不存在路徑釘 exit 2 + stderr 一行。現在做還是併下一批,你定。
```
#### #18 CapitalClient 的測試工廠又多了兩份,現在有五份
**File**: `tests/capital/test_reply_watch.py`
**Line**: 18

**Comment**:
```
def _client(com, tmp_path) 這份跟 test_chain_stats.py:135(直接寫在測試體內)、test_fill_latency.py:31、test_client.py:65(帶參最完整)、
test_capital_api.py:101 是同一段六參數建構抄五次;CapitalClient.__init__ 必填一改,五處同時 TypeError。
tests/helpers/fake_sources.py 檔頭寫的「同一個 fake 散在八個測試檔各抄一份 → 收斂成一份」就是這個情境。

🔵 純重構:上提到 tests/capital/client_fixture.py,五個呼叫點改 import。鐵則 B 要另批 —— 併 test-hygiene 那批。
```
#### #19 這個測試名說「立即量、每 interval 量」,兩件事都沒被斷言
**File**: `tests/server/test_clock_monitor.py`
**Line**: 157

**Comment**:
```
interval_secs=0.01 配 1 s 輪詢窗,「先量後睡」跟「先睡後量」在觀測上分不出來;「每 interval」也只驗了至少跑三輪。
突變體實跑(把 sleep 搬到迴圈首):1 failed / 20 passed,紅的是 TestAppWiring,這一案綠。
覆蓋沒有真缺口(TestAppWiring 就在同 PR、assert calls == [1]),是命名跟責任歸屬會誤導後手。

二選一:改名 test_loop_keeps_feeding_sink_and_survives_iterations、把「立即」的責任明寫給 TestAppWiring;或 interval 5 s + 斷 0.5 s 內有第一顆。
```
#### #20 _Broker 是 _run_chain 的泛化版,兩份假券商並存
**File**: `tests/capital/test_fill_latency.py`
**Line**: 179

**Comment**:
```
_Broker.run 跟 _run_chain(:52-72)的 replies dict 逐字相同、迴圈同構,差別只在 _answered 從 set 換成計數、_due 可重複武裝 → 能答多輪。
對只答一輪的兩個舊 caller(:96 / :118)行為等價。現在回報鏈再加一段要記得改兩邊,漏一邊的症狀是鏈永遠不落地、撞 3 s budget 才紅。

🔵 刪 _run_chain、兩個舊 caller 改 _Broker(client, com).run(...),跑一次確認不變。鐵則 B 另批。
```
