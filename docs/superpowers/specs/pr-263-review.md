# PR #263 Code Review 比較報告 · SHA fd613110
**Report projection schema**: 1

**PR**: [loger-w/copycat#263](https://github.com/loger-w/copycat/pull/263)
**標題**: feat(ticks): spec #257 tick persist - trade + book jsonl, 13:45 parquet compaction, loader, 120-day book retention
**作者**: loger-w
**分支**: `feat/tick-persist` → `master`
**變更**: 26 檔案, +2902 / -4(其中 8 檔 +160 為 `.claude/feat/tick-persist/**` 流程 artifact;實質 code 10 檔 +1,270 / -4、測試 6 檔 +1,450、docs 2 檔 +34)
**審查日期**: 2026-09-15
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以收修 PR 處置,不阻擋任何出貨;merge commit `bdf0a4b1`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `fd61311095fd66f52b1cbf7b17398ccdc1118ae0`;destination repo id `R_kgDOTsITBg` + baseRefOid `654bb1fe8a8ad5af2ccb9b49c9792ce5efda5c4a`;`input_binding: verified`(`refs/pull/263/head` fetch 後 `git rev-parse FETCH_HEAD` = headRefOid;worktree detached 於該 SHA;`git merge-base 654bb1fe FETCH_HEAD` = baseRefOid)
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 14 筆 SHA;分支已刪,`refs/pull/263/head` 仍指 `fd613110`,產報告前重抓 headRefOid 不變);`base_changed=true`(origin/master 已前進到 `fa0a8c88` = 本 PR merge `bdf0a4b1` + 一筆 graphify `chore` commit,無其他人 commit);`review_context_changed=false`(reviewed 內容即 master 現況,`bdf0a4b1` tree 與 `fd613110` tree 逐檔同內容;`fa0a8c88` 只動 `graphify-out/**`)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A**(user 已停用,沿 #188 / #190 / #199 / #230 / #238 / #253 / #255 前例單軸)+ Codex 對抗式 **N-A** + Cross-axis verification(4.1 N-A 無非 CC finding;4.2 以 main session 內部逐條事實核代替,**非跨軸證據**)+ Gemini 軸 **N-A**(user 已停用)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer ×4 chunk(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .py 佔 source diff 100%;dispatch A 32 tool uses / 730 s、B 36 / 710 s、C 27 / 511 s、D 38 / 683 s);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派,gate SKIPPED);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=26 → covered 16 / no-issues 10 / skipped 0 / **missed 0**(chunked: 是 —— source 10 檔 < 15 但 diff 2,906 行 > 800 門檻;四塊:A 15 檔(artifacts 8 + CLAUDE.md + cli / tick_persist / __main__ / app / shutdown_budget / stock_engine)、B 7 檔(ticks_compactor / ticks / ticks_compact / ticks_config / pyproject / test_main_wiring / test_shutdown_budget)、C 1 檔(test_tick_persist 678 行)、D 3 檔(test_ticks_compactor / test_ticks_compact / test_ticks_config);聯集 = F,零 repair 輪)
**定位 (ENH-B)**: anchored exact 33 / ambiguous 2 / **FAILED 0**(raw 35 條逐字 anchor 對 worktree 重定位;ambiguous 兩條 = B-8 `assert sb.lifespan_close_worst_secs() >= (` 三處命中取 :80(reported 76 所在測試的斷言行)、D-2 `pq.read_table(...)` 兩處取 :134;去重後 32 條 pin 全部落在 exact / ambiguous 行)
**React-doctor (2.97)**: N-A(非 React PR;F 無 .jsx / .tsx)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_REPO_SPEC_PATH)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出;`sem` 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer ×4 chunk)PASS(35 raw findings → 去重 32;26/26 accounting;三個 reviewer 各附實跑證據:B-1 tracemalloc 2.64 KB/列、B-8 突變體 84.0 ≥ 79.1 存活、D-1 / D-2 突變體 70 / 58 passed 全綠、D-4 兩 cwd `copycat.__file__` 對照、C-3 21:16 實跑觀察到子程序行)/ Codex 中性 N-A / Codex 對抗 N-A / Gemini Flash N-A / Gemini Pro N-A / cross-axis verification:4.1 N-A、4.2 以 main session 內部事實核代替 PASS(三條關鍵主張 main session 重跑:B-8 `lifespan 84.1 / rhs 79.1 / slack 5.0`;A-5 `json.loads(b'…\xe4\xb8')` → `UnicodeDecodeError`,`isinstance(JSONDecodeError)` False;A-2 stage2 觸發式 `stock_engine.py:1359–1362` 不看 `is_trial` → 丟棄窗校正為 08:00 重掛 → 08:30 首筆試撮;其餘逐條對 worktree file:line 讀過)/ 4.3a N-A(單軸無 consensus)/ 4.3b 逐條見備註
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-263`
**worktree HEAD**: `fd61311095fd66f52b1cbf7b17398ccdc1118ae0`

**Report generation**: sha256:61e518c716fd48e09b3c93dbcff95d8c4439daa9b726ef78350d07dd4beda6e8

---
## [完整證據副檔](pr-263-review.audit.md)
### finding_uid 索引
[0eb2bde09e4c52790b15](pr-263-review.audit.md#發現總覽) · [e25cb8e363a389f612dc](pr-263-review.audit.md#發現總覽) · [24bb6d4403181a069914](pr-263-review.audit.md#發現總覽) · [2e3240f13d7946b0b452](pr-263-review.audit.md#發現總覽) · [5cf219e9afc745bca1a1](pr-263-review.audit.md#發現總覽) · [9e21529057112f7fb07f](pr-263-review.audit.md#發現總覽) · [c0d244c68326c3b7b6e5](pr-263-review.audit.md#發現總覽) · [92cc63fe6956af75963c](pr-263-review.audit.md#發現總覽) · [ff55f7c587cee6c0d516](pr-263-review.audit.md#發現總覽) · [6bed1879e27b6d3958db](pr-263-review.audit.md#發現總覽) · [165e8b3d93f850d01f6c](pr-263-review.audit.md#發現總覽) · [576a46a63b0e215e920f](pr-263-review.audit.md#發現總覽) · [0306442889185b8175fb](pr-263-review.audit.md#發現總覽) · [03f5641b1064553722a2](pr-263-review.audit.md#發現總覽) · [f572094206e9a69309e7](pr-263-review.audit.md#發現總覽) · [4a016d017bf31a3fd006](pr-263-review.audit.md#發現總覽) · [1241a35ebb6898676fea](pr-263-review.audit.md#發現總覽) · [4aff75bbc543650ec702](pr-263-review.audit.md#發現總覽) · [80314feccc766047d598](pr-263-review.audit.md#發現總覽) · [277d9fc0d81294f9928d](pr-263-review.audit.md#發現總覽) · [ec49a851ee23473a2731](pr-263-review.audit.md#發現總覽) · [5e0410a6ec4ef9756ae9](pr-263-review.audit.md#發現總覽) · [7d5b6f82091ac58e9e68](pr-263-review.audit.md#發現總覽) · [55d84c327b594bf6315f](pr-263-review.audit.md#發現總覽) · [6241d1f58b6f5f23410b](pr-263-review.audit.md#發現總覽) · [ba88a854d50cc14b4399](pr-263-review.audit.md#發現總覽) · [62738c58e1055790229a](pr-263-review.audit.md#發現總覽) · [9e5825aa7c8869e0a8b1](pr-263-review.audit.md#發現總覽) · [131feb0bf3f363bd5a2d](pr-263-review.audit.md#發現總覽) · [b5859ac0ab7ceda38435](pr-263-review.audit.md#發現總覽) · [037c3b6fb1030d44f090](pr-263-review.audit.md#發現總覽) · [788f51427a81ec40427b](pr-263-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `ticks_compact.py:100` `compact_day` 把整日 jsonl 全部 `json.loads` 成 dict 堆在 `trades` / `books`,再建欄 list + Arrow table 同時在場;reviewer tracemalloc 實測簿列 2.64 KB/列 → 依 spec 自估 ~700 MB / 日 ≈ 1.47M 列 → 峰值 ~4.4 GB(spec §Further Notes 自己估「2–3 GB(在子程序內)」);MemoryError → rc≠0 → 四次後放棄 → jsonl 永遠不轉、每日 +700 MB、簿檔保留(只在成功後跑)一起停 | HIGH | PARTIAL(HIGH→MEDIUM:per-row 量測為 reviewer 第一手(worktree venv tracemalloc 100,000 列 = 264 MB);總量是**推估**(spec 體積本身也是推估,verification §6-5 排了上線第一週覆核);機制正確:`_write_parquet` 以 `row.get(name)` 造 27–35 條 list、`pa.Table.from_pydict` 再一份;失敗鏈 `_attempt_once` rc≠0 → 1+3 → `gave_up` 逐字。真資料量未驗 → 不能上 Must) | Should Fix | `ask-user` | 改成分批 RecordBatch(每 N 萬列 flush 一批、最後 `Table.from_batches().sort_by`)是設計選擇,且要先等第一個交易日的真 jsonl 大小;user 拍板要不要在體積覆核前就改 |
| F-02 | `ticks_compact.py:132` 成交 parquet 先 `os.replace` 落地、簿 parquet 後寫;被 kill 在兩次 replace 之間(逾時 300 s `proc.kill()` / 關機 `_close_segment("ticks")` cancel → kill)→ `<日>.parquet` 在、`-book.parquet` 不在、jsonl 還在 → 之後 CLI `CompactRefused`、排程 stray 分支不轉、`load_day` parquet 優先**靜默只回成交列**,簿列躺在 jsonl 永遠讀不到 | MEDIUM | CONFIRMED(MED→MED:`compact_day` :131–:141 順序逐字;`_tick_day` stray 分支 :213–:222 與 `compact_day` :94–:98 兩道閘都以「成交 parquet 存在」為已轉檔判準;`load_day` :158–:164 parquet 優先無 jsonl 回退;修法一行:先寫簿檔) | Should Fix | `auto-fix` | 交換兩行 `_write_parquet` 順序,讓「成交 parquet 存在」真的等於「兩檔都寫完」;零新結構 |
| F-03 | `cli.py:352` 只轉譯 `CompactRefused` / `CompactFailed`;`compact_day:141` `src.unlink()` 沒包 try —— CLAUDE §1 自己寫的情境(server 跑著、13:45 未 seal 就手動重跑)在 Windows 正是這步 PermissionError → traceback exit 1,但兩個 parquet 已落地 → 之後每次重跑命中「parquet 已在」exit 2,jsonl 永遠留著、判準第 2 條永遠不過,要人工刪檔;「轉檔在途時關機」殺在寫完 parquet、unlink 前也進同一格(`.tmp` 殘骸無人清) | LOW | CONFIRMED(LOW→MEDIUM:與 F-02 同一個「半途狀態不可重入」家族;`compact_day` :141 逐字無 try、CLI :352–:357 兩個 except 逐字;CLAUDE §1 :127 那句「否則 Windows 刪不掉 jsonl 直接 exit 1」證明作者知道這條路存在但沒寫出後續 exit 2;升 MEDIUM 因為它是 F-02 之外第二條通往同一死局的路) | Should Fix | `auto-fix` | `compact_day` 把 unlink 失敗收成 `CompactFailed` 並回滾兩個 parquet(狀態可重入);CLI 多接 `OSError` 印人話 exit 1;CLAUDE §1 補「之後只會拿到 exit 2」 |
| F-04 | `tick_persist.py:170` `seal_day` docstring 與 verification §4-2 宣稱「丟掉的只會是達錢的遲到殘影」,但 engine `_trade_date` 到 stage2(首筆帶 tick 的訊息,含 08:30 試撮)才前進,08:00 重掛訂閱到 08:30 之間的純簿更新(每檔一則快照 ~150 列)掛前一交易日 → 前一日 13:45 已 seal → `_write` sealed 分支丟棄;該日的一次性 WARNING 前一天下午已用掉 → **零訊號**;尾端情形「engine 整天沒換日」會丟一整天;`sealed_dropped`(:116)不在 `STATS_FMT` 五個數字裡、`open_day` 也不歸零(round-1 Standards F-06 標「接受」但只做了 per-day WARNING 那半) | MEDIUM | CONFIRMED(MED→MED:main session 重查 `stock_engine.py:1359–1362` stage2 觸發式 `tick is not None and trade_date == pending` **不看 `is_trial`** → 窗口 = 08:00 stage1 重掛 → 08:30 首筆試撮成交,比 reviewer 原述「到當日首筆 tick」更窄但確實存在;`_write` :279–:286 sealed 分支、`_sealed_warned` per-day、`open_day` :117 歸零清單不含 `sealed_dropped` 逐字;`code-review-round-1.json` Standards F-06 disposition 寫「封住 WARNING 每個日一次」= 只收了 WARNING 半邊) | Should Fix | `ask-user` | 把 `sealed_dropped` 加進 `STATS_FMT`(改契約字面,CLAUDE §4 判準句要同改)或另印一行;docstring / verification §4-2 改口徑「08:00–08:30 簿快照會丟」—— 字面契約改動要 user 拍板 |
| F-05 | `ticks_compactor.py:227` `_tick_day` 對**每一個**首次嘗試的日呼叫 `log_stats(day)`,含開機補跑的過去日;`TickPersist` 計數器是自上次 `open_day` 起的累計、開機剛歸零 → 印「tick 存檔 2026-09-14:成交 0 / 簿 0 / … / 寫入失敗 0」而那天寫了上百萬列;盤後判準(行存在、寫入失敗 0)照過,人眼看到「昨天沒存到」;`test_stale_jsonl_from_a_previous_day…` 沒給 `persist` 所以沒測到 | LOW | CONFIRMED(LOW→MEDIUM:`_tick_day` :225–:228 逐字對每個 day 都印;`open_day` :115–:117 歸零;`log_stats` docstring :141–:146 只涵蓋換日邊界;升 MEDIUM 因為它污染的是 CLAUDE §4 釘的盤後判準行,誤導方向是「假陰性」) | Should Fix | `auto-fix` | 只對 `day == persist` 當前日印 `log_stats`(persist 開 `current_day` 存取器),過去日只 `seal_day`;補一案帶 `persist` 的補跑測試 |
| F-06 | `CLAUDE.md:538`(§4 新契約條)仍寫「排序 `(recv_ns, msg_seq)` —— `msg_seq` 重啟歸零不能單看,parquet 也依 `(code, recv_ns, msg_seq)`」;`copycat/ticks.py:5` 與 `:74` 欄位註解仍寫「重啟歸零」,同檔 `load_day` :152 卻寫「不歸零」;§4 :535「啟動已過 13:45 且 jsonl 在則補跑」與 :529「對每則現貨訊息 observe」也是收修前字面 —— round-1 Spec F-03 / Standards F-02 / F-13 收修後文件沒跟;§4 是跨檔 SoT,研究讀者照它用 `recv_ns` 排序正好重現校時回撥交錯(三個 chunk 各自獨立抓到) | MEDIUM | CONFIRMED(MED→MED:`ticks_compact.py:72–74 _sort_key = (code, msg_seq)`、`ticks.py:174 rows.sort(key=msg_seq)`、`tick_persist.py:307 max(self._msg_seq, tail_msg_seq(path))` 逐字;CLAUDE.md :529 / :535 / :538 三句逐字;`verification.md` §4-1 已寫「撤銷」—— 文件與 artifact 自相矛盾) | Should Fix | `auto-fix` | CLAUDE §4 三句 + `ticks.py:5` / `:74` 改成碼的現況(排序只看 `msg_seq`、同日重啟自檔尾接續、補跑掃目錄、母體 = 進到引擎路由的現貨訊息);純文件 |
| F-07 | `ticks.py:173` `load_day` 的 jsonl 分支 `json.loads(line)` 零保護;寫入端承認當機會留半行(`tail_msg_seq` / `_ends_without_newline` 存在的理由)、`compact_day` 也把壞行當常態計入 `bad_lines`,但 `load_day` 在轉檔前讀同一份檔(模組 docstring :12 明說用途)就整天 `JSONDecodeError`;test `test_partial_trailing_line…`(:618)自己造了半行檔卻沒再 `load_day` 一次 | LOW / MEDIUM | CONFIRMED(LOW→MEDIUM:`load_day` :167–:173 逐字無 try;`_row_from_dict` 對純量拋 AttributeError;`grep -rn load_day copycat/` 只有 `__all__` 與 CLI 之外零 runtime caller(reviewer 查證)→ 影響限離線讀者,但半行是**本 PR 自己模擬過的情境**、兩個讀者口徑不對稱 → 取 MEDIUM) | Should Fix | `auto-fix` | `load_day` 與 `compact_day` 同口徑:壞行跳過(可回傳 / log 計數);測試 :618 尾巴補 `load_day` 斷言 |
| F-08 | `test_ticks_compactor.py:268` 唯一真子程序測試:`run_compact_subprocess` 不帶 `cwd` / `env`,`python -m copycat` 由 **cwd** 決定載哪棵樹的 copycat(venv editable `.pth` 釘主樹;reviewer 實測 cwd=C:\ → 主樹、cwd=worktree → worktree);pytest 不從 package root 起就靜默驗到另一棵樹(ops-discipline 同坑);無 timeout,子程序卡住 = 整個 pytest 掛死 | MEDIUM | CONFIRMED(MED→MED:`run_compact_subprocess` :66–:78 逐字無 `cwd=`;prod 由 `run.ps1` 在 repo root 起 uvicorn 所以 prod 路徑 cwd 正確,但同一支 runner 在測試 / 別的 cwd 起 server 時會漂;修法在 prod 側也是正確方向:`cwd=_REPO_ROOT`) | Should Fix | `auto-fix` | `run_compact_subprocess` 顯式 `cwd=<repo root>`(與 `resolve_ticks_dir` 同一顆 `_REPO_ROOT`);測試包 `asyncio.wait_for(..., 60)` |
| F-09 | `tick_persist.py:72` `tail_msg_seq` 只接 `(JSONDecodeError, AttributeError)`;`json.loads(bytes)` 對壞 byte 拋 `UnicodeDecodeError`(ValueError 但非 JSONDecodeError),64 KB 尾段首列本就可能切在多位元組字元中間;整段尾列都解不開(檔案截斷 / 撞壞)時 `start()` → `open_day` → `_file_for` 拋 ValueError → `_boot("stock")` 接住 → **整個 stock engine 停用**,與 round-1 Spec F-02 那條 Must 同失效樣態(該條只補了 OSError) | LOW | CONFIRMED(LOW→LOW:main session 實跑 `json.loads(b'{"msg_seq": 1, "x": "\xe4\xb8"}')` → `UnicodeDecodeError`、`isinstance(..., JSONDecodeError)` = False;`open_day` :162–:164 / `_write` :290–:294 只接 OSError 逐字;需整段 64 KB 尾都壞才觸發 → hedge,cap Should) | Should Fix | `auto-fix` | `except (ValueError, AttributeError)` 一字之差;或 `_file_for` 兩個呼叫端接 `Exception` 走 `_fail` |
| F-10 | `test_main_wiring.py:112` 把 prod kwargs 逐鍵鎖死並斷言 `"ticks_config": TicksConfig()`,等於假設這台機器沒有 `configs/ticks.json`;`ticks_config.py` docstring 教使用者建 `{"enabled": false}` 重啟即關 —— 照做之後完工 gate `pytest -q` 就因一條與改動無關的佈線測試變紅(與同檔 :77–:81 `TXO_SERVER_PORT` 要 `delenv` 隔離是同一種環境相依) | MEDIUM | CONFIRMED(MED→MED:`__main__.py:218 ticks_config=load_ticks_config()` 逐字;`load_ticks_config` 檔在即覆寫;測試 :112 逐字 `TicksConfig()`;`trading_calendar` 在同一 dict 已用 `isinstance` 抽出來比,前例就在上面) | Should Fix | `auto-fix` | 比照 `trading_calendar`:`isinstance(cap.create_kwargs["ticks_config"], TicksConfig)` 抽出來比,或 monkeypatch `main_mod.load_ticks_config` |
| F-11 | `test_shutdown_budget.py:80` 新不等式 `lifespan_close_worst_secs() >= … + TICK_PERSIST_FLUSH_SECS` 被 slack 吃掉:main session 實跑 lifespan 84.1 / 右式 79.1 / slack 5.0,把 `+ TICK_PERSIST_FLUSH_SECS` 從算式刪掉後 84.0 仍 ≥ 79.1 → **突變體存活**;上面那條 `CLOCK_PROBE` 擋得住是因 6.0 > 5.0 屬運氣;檔頭「改任一邊、別的邊沒跟上就紅」的保證對 0.1 s 常數不成立 | MEDIUM | CONFIRMED(MED→MED:main session 重算數字同 reviewer;`LIFESPAN_SLACK_SECS = 5.0` :48 逐字) | Should Fix | `auto-fix` | 改等式型:`lifespan_close_worst_secs() - LIFESPAN_SLACK_SECS == TC4_LANE_DEPTH*close_worst_secs() + COM_JOIN_TIMEOUT_SECS + CLOCK_PROBE_WORST_SECS + TICK_PERSIST_FLUSH_SECS` |
| F-12 | `test_ticks_compact.py:134` parquet 只有列數閘、無值層 parity:fixture 列形狀是手寫第二份,與寫入端 `tick_persist._common` 無任何測試相連(`grep compact_day tests/server/test_tick_persist.py` 零命中);`_write_parquet` 以 `row.get(name)` 取欄 → 寫入端欄名一漂就整欄 null、列數照樣相等 → 核對通過 → `src.unlink()` 刪掉唯一原始資料;reviewer 實跑突變(七欄改 None)S1+S2+S3 58 passed 全綠;`flag` 正是 09-15 內外盤旗標產物 | MEDIUM | CONFIRMED(MED→MED:`_write_parquet` :151–:154 `row.get(name)` 逐字;核對 :133 只比 `num_rows`;reviewer 突變證據第一手) | Should Fix | `auto-fix` | 補一條全鏈測試:S1 引擎寫 jsonl → `load_day` 取基準 → `compact_day` → `load_day` 再取,斷 `TickRow` 逐列相等 |
| F-13 | `test_ticks_compact.py:257` pyarrow 守門只掃 `copycat/server` 與 `copycat/live` 的字面 `"import pyarrow"`;唯一含 pyarrow import 的模組是 `copycat/ticks.py`(`live/tick_persist.py:32`、`server/ticks_compactor.py:30` 都 import 它),不在掃描範圍;`from pyarrow import` / `importlib` 也漏;有人把 `_read_parquet` 的函式內 import 提到頂層,server 進程開始載 pyarrow(違反 stdlib-only runtime),測試不紅 | MEDIUM | CONFIRMED(MED→MED:`ticks.py:180` 函式內 `import pyarrow.parquet as pq` 逐字;測試 :252–:261 掃描集合逐字;同進程斷言做不到因本檔頂層 :14 就 import pyarrow) | Should Fix | `auto-fix` | 改真斷言:子程序 `sys.executable -c "import copycat.server.app, sys; raise SystemExit('pyarrow' in sys.modules)"`;或 `ast` 掃 `copycat/**.py` module-level import |
| F-14 | `test_tick_persist.py:245` 測試名宣告 twenty numbers,實際只動買側(`BidVolume2`、`Bid`);全檔 asks 恆 "101" / "2380";把 `key = (tuple(book.bids), tuple(book.asks))` 突變成 `(tuple(book.bids),)` 全 S1 照綠 → 賣側單獨變動(盤中極常見)的簿列**靜默全丟**;verification §2 突變表只做 `(bids[:1], asks[:1])` 擋不住 | MEDIUM | CONFIRMED(MED→MED:reviewer `grep 'ask=\|Ask'` 全檔三處逐字;`observe` :187 key 兩側逐字;推演成立) | Should Fix | `auto-fix` | 加一案:同 code 只改 `Ask1` / `AskVolume1` → 斷言出一列 `book` |
| F-15 | `test_tick_persist.py:284` 「只存現貨」零測試:engine 是 `if is_spot and self._persist is not None:`,期貨 / 個股期腿不進存檔是 spec 明文非目標;本檔每則 quote 都是 `TC.S.TWS.*`,突變成 `if self._persist is not None:` 不紅 → 主圖 stkfut 腿整天寫進個股 tick 檔(`code` = CDF 之類)、`msg_seq` 灌水 | MEDIUM | CONFIRMED(MED→MED:`stock_engine.py:1450` 逐字;`grep 'TC.F' tests/server/test_tick_persist.py` 零命中(main session 補查);`test_stock_engine.py` 既有 `_quote(symbol=...)` 參數可直接用) | Should Fix | `auto-fix` | 加一案:送 `_quote(code="CDF", symbol="TC.F.TWF.CDF.HOT")` + 一則現貨 → 斷言 jsonl 只有現貨那列 |
| F-16 | `test_tick_persist.py:470` `TestAppWiring` 用 `create_app(ticks_config=…)` 建的 `TicksCompactor` 沒 runner / now_fn 注入口 → 真 `make_subprocess_runner` + `datetime.now`;`_loop()` 開場就 `tick()`;engine `_resolve_trade_date(before=08:00)` 讓當日 jsonl boot 時預開 → 08:00 前 / 週末 / 13:45 後啟動測試時 `_pending_days` 命中 → `seal_day` + 真 `python -m copycat` 子程序;reviewer 21:16 實跑觀察到 log 第一行「tick 存檔 2026-09-15:…」與 basetemp 留下被 kill 的空 jsonl;測試路徑依牆鐘、單測起真 interpreter | MEDIUM | CONFIRMED(MED→MED:`_make_ticks_compactor` app.py :1156–:1172 無 runner / now_fn 注入逐字;`TicksCompactor.start` → `_loop` → `tick` 逐字;reviewer 實跑觀察為第一手;與 F-08 同根:真子程序在測試裡由環境決定) | Should Fix | `auto-fix` | `create_app` 給 compactor 一個 runner 注入口(或測試 monkeypatch `ticks_compactor.run_compact_subprocess` 成 fake);同時 `now_fn` 注入避免依牆鐘 |
| F-17 | `test_ticks_compactor.py:202` 排程重試的唯一決定點 `_sleep_secs` pending 分支(:165–:172)零覆蓋:唯一碰它的測試在 `_days` 空的狀態;reviewer 實跑突變(刪整段 pending 只留 compact_time+5 s)S1+S2+S3+config 70 passed 全綠;prod 後果 = 13:45 失敗後 WARNING 印「900 s 後再試」,迴圈實際睡到隔天 13:45:05,當日 parquet 延一天、零訊號 | MEDIUM | CONFIRMED(MED→MED:`_sleep_secs` :162–:180 逐字;`test_failure_retries…` 只證明閘在 `next_attempt_at` 開;前例 `test_screen_engine.py:288 sleeps == [600.0]*11`) | Should Fix | `auto-fix` | 加一條:失敗一次後斷 `eng._sleep_secs(clock.now()) == 900`(或 900 − 已耗) |
| F-18 | `ticks_compactor.py:200` `tick()` 開頭取一次 `now`,`_tick_day` 失敗時用這個舊 `now` 算 `next_attempt_at`;一次逾時嘗試耗 300 s → 下次實際只等 600 s,與「失敗 15 分鐘 × 3」不符;多日待轉時後面幾天的 `now < next_attempt_at` 也用過期時刻 | LOW | CONFIRMED(LOW→LOW:`tick` :196–:202 / `_tick_day` :247 逐字;影響只是重試更密) | Nice to Have | `auto-fix` | `_tick_day` 內 `await` 之後重取 `self._now_fn()` 再算退避 |
| F-19 | `stock_engine.py:1450` `observe` 不在 `_handle_quote` 尾端:後面還有轉態補推 `_publish`(:1465–:1466)、主圖 `book` 廣播(:1467–:1468)、`signal_hub.on_book`(:1474–:1475);`observe` 內只擋 OSError(見 F-09),非 OSError 冒出來時這一則的五檔廣播與鎖板打開訊號一起被跳過 —— 存檔失效滲進看盤,正是模組 :16–:18 不變式要擋的;挪到 `on_book` 之後行為等價(兩者不改 `state.seq` / `book`) | LOW | CONFIRMED(LOW→LOW:三個後續步驟 file:line 逐字;等價性 reviewer 追過) | Nice to Have | `auto-fix` | 挪到函式真正尾端(`on_book` 之後),文件那句「尾端」順便成立 |
| F-20 | `test_tick_persist.py:148` `recv_ns` 唯一斷言 `rows[0] <= rows[1]` 比兩個相隔微秒的牆鐘,任何實作都過;規格性質「在 source thread 蓋章、loop 排隊延遲不算」(verification §6-4 要拿它算每秒則數)零覆蓋;`_handle_quote(quote, recv_ns=None)` 預設就地補 `time.time_ns()`,突變成 `call_soon_threadsafe(self._handle_quote, quote)` 全綠 | MEDIUM | CONFIRMED(MED→LOW:`_on_raw_threadsafe` :1209 / `_handle_quote` :1229–:1232 逐字;`grep -rn recv_ns tests/` 只有本檔兩行(reviewer);量測用途成立但目前無讀者依賴精確蓋章點 → 降 LOW) | Nice to Have | `auto-fix` | monkeypatch `stock_engine.time.time_ns` 成遞增計數器,送訊息後推進再 `_drain`,斷列上的 `recv_ns` = 推進前的值 |
| F-21 | `test_tick_persist.py:324` `_FailingFile` 只覆寫 `write`、`_RaisingOpener` 只擋開檔;`flush()` 與 `_close_file()` 的 `except OSError → _fail` 零覆蓋;硬碟滿真實順序常是 write 進緩衝成功、`flush` 才炸;若 try/except 被拿掉,例外從 `_on_flush_timer` 逃進 asyncio callback → `_arm_flush()` 不再執行 = 定時 flush 當日永久停擺,測試全綠 | LOW | CONFIRMED(LOW→LOW:`flush` :131–:138 / `_close_file` :330–:335 / `_on_flush_timer` :343–:348 逐字;opener seam 已在,補幾行) | Nice to Have | `auto-fix` | 補一個 `flush` / `close` 會拋的 handle,各一案 |
| F-22 | `tick_persist.py:82` `_put_levels` 對每則要落列的訊息跑 20 次 f-string 造固定鍵名 `bid0..askq4`;`ticks.py:138–139` 已有 `TRADE_FIELDS / BOOK_FIELDS`(同序含這 20 個名字),本檔已 import 同模組 | LOW | CONFIRMED(LOW→LOW:逐字;每則省 20 次字串建構,順帶讓欄名與 `TickRow` 同源機械保證) | Nice to Have | `auto-fix` | 模組層 `_BID_KEYS = tuple(f"bid{i}" …)` 四組常數或直接切 `BOOK_FIELDS` |
| F-23 | `tick_persist.py:99` `base_dir` 建構參數零呼叫者(app.py:772 + tests 六處都不傳;測試換目錄一律 `TicksConfig(dir=絕對路徑)`),`resolve_ticks_dir` 本來就有預設,`if base_dir is None / else` 把同一預設寫第二遍 | LOW | CONFIRMED(LOW→LOW:reviewer `grep -rn "TickPersist("` 七個建構點逐字) | Nice to Have | `auto-fix` | 刪參數,或收成 `resolve_ticks_dir(config, base_dir=base_dir or _REPO_ROOT)` 一行 |
| F-24 | `ticks_config.py:46` HH:MM 手刻驗證第三份:既有 `breadth_engine.py:134 _parse_hhmm`(strptime)與 `signal_hub.py:422`;`ticks_compactor.__init__` 又 `split(":")` 再解一次;`isdigit()` 會把全形「１３:４５」判合法 | LOW | CONFIRMED(LOW→LOW:reviewer grep `%H:%M` 兩處既有 file:line;compactor :122–:123 逐字) | Nice to Have | `auto-fix` | `__post_init__` 用 strptime 驗;開 `due_time` helper,compactor 直接用 |
| F-25 | `pyproject.toml:14` `pyarrow>=17`:本專案 Python 3.13(實測 3.13.13、裝的是 25.0.1),pyarrow cp313 wheel 要到 18.0.0 才有 → `>=17` 在本專案 Python 上其實裝不起來(resolver 永遠挑更新版才沒爆);dev 直接複製字串而非引用 `copycat[ticks]`,改版兩處要同步 | LOW | PARTIAL(LOW→LOW:runtime 零 import 那半確認無誤;18.0.0 = 首個 cp313 wheel 為 reviewer 記憶、**未以 `pip index versions` 查證** → hedge) | Nice to Have | `auto-fix` | 查證後改 `>=18`;dev 改引用 `copycat[ticks]`(setuptools 支援 self-referential extra) |
| F-26 | `test_ticks_compactor.py:233` `TestPersistHandoff` 建真 `TickPersist`(真 handle + 3600 s flush timer),`jsonl.unlink()` / `persist.close()` 裸放尾端;中途 assert 紅就洩漏 handle 與 timer(Windows 下 tmp_path 也刪不掉、失敗訊息被 PermissionError 蓋住);「handle 已放掉」唯一證據是 `unlink()` 不拋 —— POSIX 上刪開著的檔會成功,`seal_day` 退化 no-op 照綠 | LOW | CONFIRMED(LOW→LOW:測試 :211–:234 逐字;`TestSealDay`(test_tick_persist :640–:660)另有 `sealed_dropped` 正面斷言,本條只是 handoff 那案沒帶) | Nice to Have | `auto-fix` | try/finally 收尾;補 seal 後 `observe` → `sealed_dropped` 前進的正面斷言 |
| F-27 | `ticks_compactor.py:81` 逾時說「子程序已殺」,實際殺人的是 `run_compact_subprocess` 的 `except CancelledError: proc.kill()`;`make_subprocess_runner` 零測試 caller、`run_compact_subprocess` 只有 happy path;逾時測試用 fake `_Hang` 走不到 kill;分支壞掉 → Windows 孤兒子程序握著 jsonl / `.tmp`,三次重試撞 PermissionError 後放棄,log 卻說已殺 | LOW | CONFIRMED(LOW→LOW:`run_compact_subprocess` :79–:86 逐字;kill 分支零覆蓋為事實;後果鏈為假設 → hedge) | Nice to Have | `auto-fix` | 加一條:對真子程序 `create_task` 後立即 cancel,斷 `proc.returncode is not None` |
| F-28 | `test_ticks_config.py:57` `__post_init__` 擋五件事,parametrize 只覆蓋四件:`retry_secs <= 0`、`compact_time` 時 / 分越界(`"24:00"` / `"12:60"`)、非數字(`"aa:bb"`)沒案子;`retry_secs=0` 的後果正是檔頭要擋的「退避變 0 → 13:45 起每輪 tick 再開一個子程序」 | LOW | CONFIRMED(LOW→LOW:`__post_init__` :38–:48 五個 raise 逐字;parametrize :54–:63 五個字面逐字,缺 `retry_secs` 與兩種 compact_time) | Nice to Have | `auto-fix` | 四個字面加進既有 parametrize |
| F-29 | `test_tick_persist.py:58` `_TickRecorder` 與既有 `test_stock_engine.py::FakeHub` 只差存 `cum_vol` vs 存 StockTick 本體,而 `TestResilience` / `TestReviewRound1` 只用 `len(recorder.ticks)`;`TestBookRow` :245–:253 整段重抄 `_make` 只為拿 `persist`,但 `engine.tick_persist` property 已在 :571 / :629 / :656 用過;`_make` 補 `opener=` 參數也能收掉三處 8 行重複 | LOW | CONFIRMED(LOW→LOW:reviewer `grep -rn 'def on_rollover_pending' tests/` 兩處逐字;`test_load_day_rows_round_trip…` 需要 StockTick 本體所以 Recorder 不能整個刪) | Nice to Have | `auto-fix` | `_make(opener=…)`;`TestBookRow` 改用 `engine.tick_persist`;Recorder 保留或讓 FakeHub 多存 tick 本體 |
| F-30 | `test_tick_persist.py:3` 檔頭寫「只斷言檔案內容與 `load_day` 讀回,不碰 handle / 緩衝 / 私有計數器」,實際還斷言公開計數器(`dup_books` / `sealed_dropped`)、log 字面、緩衝未落地(:426)、`compactor.dir`;日後有人依它判斷「這裡不該碰計數器」會誤刪唯一釘住重複簿計數的斷言 | LOW | CONFIRMED(LOW→LOW:逐字) | Nice to Have | `auto-fix` | docstring 改成列出真正觀測面(檔案 / load_day / 公開計數器 / log 契約行) |
| F-31 | `verification.md:43` 章節序 1 → 2 → 3 → 4 → **7** → 5 → 6;§7 末列交叉引用「本檔 §6」指到真環境判準而非文件三處齊的證據 | LOW | CONFIRMED(LOW→LOW:標題行 :43 / :80 / :87 逐字) | Nice to Have | `auto-fix` | §7 移到 §6 之後(或改號),交叉引用改指 §3 gate 或 commit |
| F-32 | `ticks.py:23` `copycat.ticks`(列形狀 / 讀回底層)為了 `TickRow.to_stock_tick()` 反向依賴上層 `copycat.live.stock_models`,而 `live/tick_persist.py` 又 import `copycat.ticks` → 套件層面成環;已追過不是 import 迴圈(`stock_models` 只 import `tc4common`)、子程序不會被拖去要 pyzmq | LOW | CONFIRMED(LOW→LOW:reviewer 追過相依鏈;spec §34 明文要 `to_stock_tick` 給日後回補用,放哪一層是設計取捨) | 參考用 | `no-op` | 分層味道、無行為後果;spec 要求該方法存在,搬層與否留給日後「回補改讀自家存檔」那案一起決定 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 0eb2bde09e4c52790b15 action=ask-user
F-02 finding_uid: e25cb8e363a389f612dc action=auto-fix
F-03 finding_uid: 24bb6d4403181a069914 action=auto-fix
F-04 finding_uid: 2e3240f13d7946b0b452 action=ask-user
F-05 finding_uid: 5cf219e9afc745bca1a1 action=auto-fix
F-06 finding_uid: 9e21529057112f7fb07f action=auto-fix
F-07 finding_uid: c0d244c68326c3b7b6e5 action=auto-fix
F-08 finding_uid: 92cc63fe6956af75963c action=auto-fix
F-09 finding_uid: ff55f7c587cee6c0d516 action=auto-fix
F-10 finding_uid: 6bed1879e27b6d3958db action=auto-fix
F-11 finding_uid: 165e8b3d93f850d01f6c action=auto-fix
F-12 finding_uid: 576a46a63b0e215e920f action=auto-fix
F-13 finding_uid: 0306442889185b8175fb action=auto-fix
F-14 finding_uid: 03f5641b1064553722a2 action=auto-fix
F-15 finding_uid: f572094206e9a69309e7 action=auto-fix
F-16 finding_uid: 4a016d017bf31a3fd006 action=auto-fix
F-17 finding_uid: 1241a35ebb6898676fea action=auto-fix
F-18 finding_uid: 4aff75bbc543650ec702 action=auto-fix
F-19 finding_uid: 80314feccc766047d598 action=auto-fix
F-20 finding_uid: 277d9fc0d81294f9928d action=auto-fix
F-21 finding_uid: ec49a851ee23473a2731 action=auto-fix
F-22 finding_uid: 5e0410a6ec4ef9756ae9 action=auto-fix
F-23 finding_uid: 7d5b6f82091ac58e9e68 action=auto-fix
F-24 finding_uid: 55d84c327b594bf6315f action=auto-fix
F-25 finding_uid: 6241d1f58b6f5f23410b action=auto-fix
F-26 finding_uid: ba88a854d50cc14b4399 action=auto-fix
F-27 finding_uid: 62738c58e1055790229a action=auto-fix
F-28 finding_uid: 9e5825aa7c8869e0a8b1 action=auto-fix
F-29 finding_uid: 131feb0bf3f363bd5a2d action=auto-fix
F-30 finding_uid: b5859ac0ab7ceda38435 action=auto-fix
F-31 finding_uid: 037c3b6fb1030d44f090 action=auto-fix
F-32 finding_uid: 788f51427a81ec40427b action=no-op inline=none
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 700 MB 的 jsonl 整份載進記憶體,估 4 GB 以上,炸了就是那天永遠轉不成
**File**: `copycat/ticks_compact.py`
**Line**: 100

**Comment**:
```
compact_day 把每一列 json.loads 成 dict 全堆在 trades / books,排序後 _write_parquet
再造 27–35 條欄 list,最後 Arrow table 又一份 —— 三者同時在場。
實測一列簿列 476 bytes → dict 2.64 KB(tracemalloc 10 萬列 = 264 MB),
依 spec 自己估的 700 MB / 日 ≈ 147 萬列 → 峰值 4 GB 以上(spec 寫 2–3 GB,偏低)。
炸的方式不是報錯:子程序 MemoryError → rc≠0 → 四次後放棄 → jsonl 每天 +700 MB 留著、
簿檔 120 日保留(只在成功後跑)也跟著停,零錯誤訊號。

方向:每 N 萬列做一個 pa.RecordBatch 就丟掉 dict,最後
pa.Table.from_batches(...).sort_by([("code","ascending"),("msg_seq","ascending")]),
峰值可壓到幾百 MB。要不要在第一個交易日量到真 jsonl 大小之前就改,你拍板。
```
#### #2 成交 parquet 先落地、簿 parquet 後寫,中間被殺就卡成「已轉檔但簿列永遠讀不到」
**File**: `copycat/ticks_compact.py`
**Line**: 132

**Comment**:
```
兩個檔各自 .tmp + os.replace 沒錯,但成交檔先 replace。被殺在兩次 replace 之間有兩條真路:
逾時 300 s 的 proc.kill(),還有關機 _close_segment("ticks") 的 cancel → kill。
結果 = <日>.parquet 在、-book.parquet 不在、jsonl 還在;之後每條路都被自己擋死:
CLI 看 parquet 已在 → exit 2;排程走 stray 分支只 WARNING 不轉;load_day parquet 優先
→ 靜默只回成交列,簿列躺在沒刪的 jsonl 裡永遠讀不到。

最小修法就是交換順序:先寫 -book.parquet,再寫 <日>.parquet,
讓「成交 parquet 存在」真的等於「兩檔都寫完」。
```
#### #3 手動重跑碰到 Windows 刪不掉 jsonl,之後這一天只會一直拿到 exit 2
**File**: `copycat/cli.py`
**Line**: 352

**Comment**:
```
compact_day 最後一步 src.unlink() 沒包 try;CLAUDE §1 自己寫的情境(server 跑著、
13:45 還沒 seal 就手動跑)在 Windows 正是這一步 PermissionError → traceback exit 1。
但兩個 parquet 已經寫好落地了 → 之後每次重跑(手動或排程重試)都命中「parquet 已在」
exit 2,jsonl 永遠留著、判準第 2 條永遠不過,要人工刪 parquet 才解得開。
「13:45 轉檔在途時關機」殺在 parquet 寫完、unlink 之前也進同一格(.tmp 殘骸還沒人清)。

compact_day 把 unlink 失敗收成 CompactFailed 並把兩個 parquet 一起回滾(狀態才可重入);
CLI 多接一個 except OSError 印人話 exit 1;CLAUDE §1 那句補上「之後只會拿到 exit 2」。
```
#### #4 「丟掉的只會是遲到殘影」不成立:每天 08:00–08:30 的簿快照會被靜默丟掉,而且丟了多少沒地方看
**File**: `copycat/live/tick_persist.py`
**Line**: 170

**Comment**:
```
engine 的 _trade_date 要到 stage2(首筆帶 tick 的訊息,08:30 試撮就算)才前進;
08:00 stage1 重掛訂閱到 08:30 之間的純簿更新(每檔一則快照,~150 列)掛在前一交易日,
前一天 13:45 已 seal → _write 走 sealed 分支丟掉。那一天的 WARNING 前一天下午就用掉了,
所以早上這批丟棄零訊號;engine 整天沒換日那種尾端情形會丟一整天,判準照樣全綠 ——
因為 sealed_dropped 只是個屬性,不在 STATS_FMT 五個數字裡,open_day 也不歸零
(round-1 Standards F-06 只收了 per-day WARNING 那半)。

兩件事:(1) sealed_dropped 進 STATS_FMT(改契約字面,CLAUDE §4 判準句同改)或另印一行,
並在 open_day 歸零;(2) 這段 docstring 跟 verification §4-2 改口徑「08:00–08:30 簿快照會丟」。
要不要動 STATS_FMT 字面你決定。
```
#### #5 開機補跑昨天的 jsonl 時,會印一行「昨天成交 0 / 簿 0」,盤後看 log 會以為沒存到
**File**: `copycat/server/ticks_compactor.py`
**Line**: 227

**Comment**:
```
_tick_day 對每一個首次嘗試的日都呼叫 persist.log_stats(day),包含開機補跑的過去日。
但計數器是「自上次 open_day 起」的累計,開機時剛被 start() 歸零 →
印出「tick 存檔 2026-09-14:成交 0 / 簿 0 / 重複簿略過 0 / flush 0 / 寫入失敗 0」,
那天其實寫了上百萬列。自動判準(行存在、寫入失敗 0)照過,人眼看到的是假的。
test_stale_jsonl_from_a_previous_day… 建構時沒給 persist,所以沒測到。

只對 persist 當前日印 log_stats(開個 current_day 存取器比一下),過去日只 seal_day;
補一案帶 persist 的補跑測試。
```
#### #6a CLAUDE §4 這條契約寫的是 round-1 收修前的行為,照它做會把 recv_ns 排序加回來
**File**: `CLAUDE.md`
**Line**: 538

**Comment**:
```
這句「排序 (recv_ns, msg_seq) —— msg_seq 重啟歸零不能單看,parquet 也依 (code, recv_ns, msg_seq)」
跟碼相反:ticks_compact._sort_key 是 (code, msg_seq)、load_day 只排 msg_seq、
tick_persist.tail_msg_seq 讓 msg_seq 同日重啟自檔尾接續不歸零(round-1 Spec F-03 收修)。
同段 :535「啟動已過 13:45 且 jsonl 在則補跑」實作已放寬成掃目錄所有過期 jsonl,
:529「對每則現貨訊息 observe」也是 F-13 要改掉的字面(池外推播早退不算)。
§4 是跨檔 SoT,研究讀者照它用 recv_ns 排序,正好重現校時回撥交錯 —— 兩邊都讀得出數字。

三句改成碼的現況:排序只看 msg_seq / 重啟自檔尾接續 / 補跑掃目錄 / 母體限「進到引擎路由的現貨訊息」。
```
#### #6b 同一檔的 msg_seq 註解說「重啟歸零」,load_day docstring 說「不歸零」
**File**: `copycat/ticks.py`
**Line**: 74

**Comment**:
```
:5 跟 :74 還寫「重啟歸零」,:152 load_day 已寫「寫入端同日重啟自檔尾接續,不歸零」。
排序只看 msg_seq 的正確性就靠後者,讀者照 :74 推會得到「排序不可靠」。
兩處改成「同日重啟自檔尾接續(tail_msg_seq)」。
```
#### #7a load_day 讀 jsonl 遇到當機半行會整天讀不回來,而 compact_day 對同一份檔是容忍的
**File**: `copycat/ticks.py`
**Line**: 173

**Comment**:
```
寫入端承認會有半行(tail_msg_seq / _ends_without_newline 存在的理由),
compact_day 也把壞行當常態計進 bad_lines,但 load_day 的 jsonl 分支
json.loads(line) 零保護 → 轉檔前用 load_day 讀(模組 docstring :12 明說這是用途)直接 JSONDecodeError;
列是 JSON 純量還會在 _row_from_dict 拋 AttributeError。
目前沒有 runtime caller(只有 CLI 之外零命中),影響限離線讀者,但兩個讀者口徑不對稱。

跟 compact_day 同口徑:壞行跳過(可以回傳或 log 一個計數)。
```
#### #7b 這案自己造了半行檔,尾巴補一行 load_day 就能釘住上一條
**File**: `tests/server/test_tick_persist.py`
**Line**: 618

**Comment**:
```
lines[1] 解不開、新列另起一行都斷了,就差沒再 load_day(_DAY, tmp_path) 一次 ——
現況會 raise,容忍後應該是 2 列。補這一行,讓 ticks.py 那邊要走哪一邊有測試釘著。
```
#### #8 唯一的真子程序測試跑哪一棵樹的 copycat 由 cwd 決定,而且沒有時間上界
**File**: `tests/server/test_ticks_compactor.py`
**Line**: 268

**Comment**:
```
run_compact_subprocess 不帶 cwd / env,子程序 python -m copycat 以 cwd 決定載哪一份 copycat:
venv 是 editable 安裝,.pth 釘死主樹,實測 cwd=C:\ → 主樹、cwd=worktree → worktree。
pytest 不從 package root 起,這條唯一驗「prod 命令列跑得起來」的測試就靜默驗到另一棵樹
(ops-discipline 那個「worktree 內直跑腳本會 import 主 tree」同坑)。
另外沒 timeout(repo 沒裝 pytest-timeout),子程序卡住 = 整個 pytest 掛死。

run_compact_subprocess 顯式 cwd=<repo root>(跟 resolve_ticks_dir 同一顆 _REPO_ROOT,prod 也更穩);
測試包一層 asyncio.wait_for(..., 60)。
```
#### #9 tail_msg_seq 的 except 接不到 UnicodeDecodeError,穿過去又是整個 stock engine 停用
**File**: `copycat/live/tick_persist.py`
**Line**: 72

**Comment**:
```
json.loads 吃 bytes 時壞 byte 拋 UnicodeDecodeError —— 是 ValueError 但不是 JSONDecodeError,
這裡只接 (JSONDecodeError, AttributeError)。64 KB 尾段的第一列本來就可能切在多位元組字元中間,
正常檔會在更後面的列 return,所以要整段尾列都解不開(檔案截斷 / 撞壞)才走到。
真走到時:start() → open_day → _file_for 拋 ValueError → _boot("stock") 接住 → 整個 stock engine 停用,
跟 round-1 Spec F-02 那條 Must 是同一個失效樣態(那條只補了 OSError)。

except (ValueError, AttributeError) 一字之差;或 _file_for 兩個呼叫端接 Exception 走 _fail。
```
#### #10 這條佈線斷言偷偷假設機器上沒有 configs/ticks.json,建了檔整批測試就紅
**File**: `tests/server/test_main_wiring.py`
**Line**: 112

**Comment**:
```
prod 走 load_ticks_config(),configs/ticks.json 存在時回覆寫後的值;
這裡逐鍵鎖死整份 dict 並斷 == TicksConfig()。ticks_config.py docstring 正好教人
「盤中發現拖累看盤時建一份 {"enabled": false} 重啟即關」—— 照做之後,
完工 gate pytest -q 會因為這條與改動無關的測試變紅(跟上面 TXO_SERVER_PORT 要 delenv 隔離同一種病)。

比照同一個 dict 裡 trading_calendar 的做法:抽出來 isinstance(..., TicksConfig) 比,
或 monkeypatch main_mod.load_ticks_config。
```
#### #11 這條不等式被 slack 吃掉:把 TICK_PERSIST_FLUSH_SECS 從算式拿掉,測試照樣綠
**File**: `tests/server/test_shutdown_budget.py`
**Line**: 80

**Comment**:
```
實跑:lifespan_close_worst_secs() = 84.1,右式 = 79.1,slack 5.0。
把 + TICK_PERSIST_FLUSH_SECS 從 shutdown_budget 刪掉 → 84.0 仍 ≥ 79.1,突變體存活。
上面那條 CLOCK_PROBE 擋得住是因為 6.0 > 5.0,運氣不是設計;
檔頭「改任一邊、別的邊沒跟上就紅」對 0.1 s 這種常數不成立。

改等式型:
lifespan_close_worst_secs() - LIFESPAN_SLACK_SECS == (
    TC4_LANE_DEPTH * close_worst_secs() + COM_JOIN_TIMEOUT_SECS
    + CLOCK_PROBE_WORST_SECS + TICK_PERSIST_FLUSH_SECS)
```
#### #12 parquet 只有列數閘、沒有值層 parity:欄位靜默全 null 照樣核對通過、jsonl 照樣刪
**File**: `tests/test_ticks_compact.py`
**Line**: 134

**Comment**:
```
compact_day 的成功條件只有 _parquet_rows 列數相等;這裡也只讀回 code / msg_seq / price_milli 幾格。
fixture 的列形狀是手寫的第二份,跟寫入端 tick_persist._common 沒有任何測試相連
(test_tick_persist.py 零 compact_day)。_write_parquet 用 row.get(name) 取欄 →
寫入端欄名一漂就是整欄 null、列數照樣相等 → 核對通過 → src.unlink() 刪掉唯一原始資料。
實跑突變:寫檔前把 flag / trade_status / precise_time / bidq1..4 七欄改成 None,58 passed 全綠
(flag 正是 09-15 內外盤旗標的產物)。

補一條全鏈:S1 引擎寫出 jsonl → load_day 取基準 → compact_day → load_day 再取,斷 TickRow 逐列相等。
```
#### #13 pyarrow 守門掃不到真正含 pyarrow import 的 copycat/ticks.py
**File**: `tests/test_ticks_compact.py`
**Line**: 257

**Comment**:
```
只掃 copycat/server 與 copycat/live 的字面 "import pyarrow"。但 server 進程實際載入、
唯一含 pyarrow import 的模組是 copycat/ticks.py(live/tick_persist.py:32、server/ticks_compactor.py:30 都 import 它),
不在掃描範圍;from pyarrow import … / importlib 也漏。今天安全全靠 _read_parquet 的函式內 import,
哪天提到頂層,server 進程開始載 pyarrow,測試不會紅。

改真斷言(同進程做不到,本檔頂層就 import 了 pyarrow):
sys.executable -c "import copycat.server.app, sys; raise SystemExit('pyarrow' in sys.modules)" 斷 rc == 0;
或用 ast 掃 copycat/**.py 的 module-level import。
```
#### #14 「20 個數任一變」只測了買側,把 asks 從去重鍵拿掉整檔照綠
**File**: `tests/server/test_tick_persist.py`
**Line**: 245

**Comment**:
```
名字寫 twenty numbers,實際只動 BidVolume2 跟 Bid;全檔 asks 恆 "101" / "2380"。
把 observe 的 key = (tuple(book.bids), tuple(book.asks)) 突變成 (tuple(book.bids),),
逐案推過去沒有斷言會翻 → 賣側單獨變動(盤中極常見)的簿列靜默全丟,研究母體少一半深度。
verification §2 的突變表只做了 (bids[:1], asks[:1]),擋不住這條。

加一案:同 code 只改 Ask1 / AskVolume1 → 斷言出一列 book。
```
#### #15 「只存現貨」這條 spec 邊界零測試,拿掉 is_spot 閘全綠
**File**: `tests/server/test_tick_persist.py`
**Line**: 284

**Comment**:
```
engine 是 if is_spot and self._persist is not None:,期貨 / 個股期腿不進存檔是 spec 明文非目標。
本檔每則 quote 都是 TC.S.TWS.*,突變成 if self._persist is not None: 不會有任何紅 ——
失效樣態是主圖的 stkfut 腿整天寫進個股 tick 檔(code = CDF 之類),msg_seq 灌水,盤後那行照樣漂亮。

沿 test_stock_engine 既有寫法送 _quote(code="CDF", symbol="TC.F.TWF.CDF.HOT") 加一則現貨,
斷 jsonl 只有現貨那一列。
```
#### #16 這兩案會依牆鐘真的開出 python -m copycat ticks-compact 子程序
**File**: `tests/server/test_tick_persist.py`
**Line**: 470

**Comment**:
```
create_app(ticks_config=…) 內建的 TicksCompactor 沒有 runner / now_fn 注入口,
拿的是 make_subprocess_runner + datetime.now;_loop() 開場就 tick()。
engine 的 _resolve_trade_date(before=08:00) 讓當日 jsonl boot 時就預開,
所以 08:00 前 / 週末 / 13:45 後跑測試,_pending_days 立刻命中 → seal_day + 真子程序
(21:16 實跑:log 出現「tick 存檔 2026-09-15:…」、basetemp 留下被 kill 的空 jsonl)。
測試走哪條路依牆鐘而定,還起真 interpreter。

create_app 給 compactor 一個 runner 注入口(或測試 monkeypatch ticks_compactor.run_compact_subprocess 成 fake),
now_fn 也一起注入。
```
#### #17 重試會不會真的在 15 分鐘後醒來,沒有任何測試在看
**File**: `tests/server/test_ticks_compactor.py`
**Line**: 202

**Comment**:
```
排程的重試跨 tick 生效(_DayState.next_attempt_at),真正決定「15 分鐘後醒」的是
_sleep_secs 的 pending 分支;唯一碰 _sleep_secs 的測試在 _days 空的狀態呼叫,
test_loop_survives… 又把 tick 換掉。實跑突變:刪掉整段 pending 只留今天/明天 compact_time+5 s,
S1+S2+S3+config 70 passed 全綠。prod 後果:13:45 失敗後 WARNING 說「900 s 後再試」,
迴圈實際睡到隔天 13:45:05,當日 parquet 延一天,零錯誤訊號。

失敗一次後斷 eng._sleep_secs(clock.now()) == 900(前例:test_screen_engine.py:288 sleeps == [600.0]*11)。
```
#### #18 now 在整輪 tick 開頭取一次,逾時一次後下次只等 600 秒不是 900
**File**: `copycat/server/ticks_compactor.py`
**Line**: 200

**Comment**:
```
tick() 先 now = self._now_fn(),再逐日 await _tick_day(day, now);失敗時用這個舊 now 算 next_attempt_at。
一次逾時嘗試耗掉 300 s → 下次實際只等 900 − 300 = 600 s;多日待轉時後面幾天的比較也用過期時刻。
影響只是重試更密。_tick_day 內 await 之後重取 self._now_fn() 再算退避就好。
```
#### #19 observe 後面還有三件看盤的事,不算「尾端」
**File**: `copycat/server/stock_engine.py`
**Line**: 1450

**Comment**:
```
模組 docstring 跟 CLAUDE §4 都寫「在 _handle_quote 尾端呼叫」,實際落點後面還有:
轉態補推 _publish、主圖 book 廣播、signal_hub.on_book。observe 內只擋 OSError,
真有非 OSError 冒出來,這一則的五檔廣播與鎖板打開訊號會一起被跳過 —— 存檔失效滲進看盤。
on_book / _publish 都不改 state.seq 或 book,挪到 on_book 之後行為等價;挪過去文件那句就成立了。
```
#### #20 recv_ns「在 source thread 蓋章」零覆蓋,這條斷言任何實作都會過
**File**: `tests/server/test_tick_persist.py`
**Line**: 148

**Comment**:
```
rows[0].recv_ns <= rows[1].recv_ns 比的是相隔幾微秒的牆鐘。
規格性質是 _on_raw_threadsafe 在 source thread 蓋章、loop 排隊延遲不算(verification §6-4 要拿它算每秒則數);
_handle_quote(quote, recv_ns=None) 預設會就地補 time.time_ns(),
突變成 call_soon_threadsafe(self._handle_quote, quote) 不會有任何紅。

monkeypatch stock_engine.time.time_ns 成遞增計數器,送訊息後推進計數器再 _drain,斷列上的 recv_ns = 推進前的值。
```
#### #21 OSError 只測了開檔跟寫入,flush / 關檔那兩條 except 沒人碰
**File**: `tests/server/test_tick_persist.py`
**Line**: 324

**Comment**:
```
_FailingFile 只覆寫 write、_RaisingOpener 只擋開檔;flush() 與 _close_file() 的 except OSError → _fail 零覆蓋。
硬碟滿的真實順序常是 write 進 64 KB 緩衝成功、flush 才炸;那個 try/except 被拿掉的話,
例外從 _on_flush_timer 逃進 asyncio callback → _arm_flush() 不再執行 = 定時 flush 當日永久停擺,測試全綠。
opener seam 已經在了,補一個 flush / close 會拋的 handle 各一案。
```
#### #22 熱路徑每則訊息用 f-string 現組 20 個固定欄名
**File**: `copycat/live/tick_persist.py`
**Line**: 82

**Comment**:
```
_put_levels 對每一則要落列的訊息跑 20 次 f-string 造 bid0..askq4。
ticks.py 已有 TRADE_FIELDS / BOOK_FIELDS(同序、含這 20 個名字),本檔已 import 同模組。
改成模組層 _BID_KEYS = tuple(f"bid{i}" for i in range(DEPTH)) 四組(或直接切 BOOK_FIELDS),
每則省 20 次字串建構,順帶讓欄名跟 TickRow 同源變機械保證。
```
#### #23 base_dir 這個建構參數沒有人傳,只是把 resolve_ticks_dir 的預設再包一層
**File**: `copycat/live/tick_persist.py`
**Line**: 99

**Comment**:
```
七個 TickPersist(...) 建構點(app.py + tests)沒有一個傳 base_dir;測試換目錄一律 TicksConfig(dir=絕對路徑)。
resolve_ticks_dir 本來就有 base_dir=_REPO_ROOT 預設,這裡的 if/else 等於同一預設寫第二遍。
刪掉參數,或收成 resolve_ticks_dir(config, base_dir=base_dir or _REPO_ROOT) 一行。
```
#### #24 HH:MM 驗證手刻第三份,compactor 還再 split 一次
**File**: `copycat/ticks_config.py`
**Line**: 46

**Comment**:
```
既有 breadth_engine.py:134 _parse_hhmm 用 strptime("%H:%M"),signal_hub.py:422 也是 strptime 驗;
這裡 partition + isdigit + 範圍手刻,ticks_compactor.__init__ 又 split(":") 再解一次。
isdigit() 還會把全形「１３:４５」判合法。
__post_init__ 改 strptime 驗,開個 due_time helper,compactor 直接用。
```
#### #25 pyarrow>=17 在本專案的 Python 3.13 上其實裝不起來(要 18 才有 cp313 wheel)
**File**: `pyproject.toml`
**Line**: 14

**Comment**:
```
venv 是 3.13(裝的是 25.0.1),pyarrow 的 cp313 wheel 記得是 18.0.0 才開始 —— >=17 這個下限
只是因為 resolver 永遠挑更新版才沒爆;請先 pip index versions pyarrow 確認再改 >=18。
另外 dev 直接抄了一份 "pyarrow>=17" 而不是引用 copycat[ticks],改版要同步兩處。
```
#### #26 這案中途 assert 紅會洩漏真 handle 跟 flush timer,而且「handle 放掉」的證據只在 Windows 成立
**File**: `tests/server/test_ticks_compactor.py`
**Line**: 233

**Comment**:
```
建了真 TickPersist(start 開真 handle + 3600 s flush timer),jsonl.unlink() / persist.close() 裸放尾端:
中途任一 assert 紅就洩漏 handle 與 timer(Windows 下 tmp_path 也刪不掉,失敗訊息被 PermissionError 蓋住)。
「handle 已放掉」唯一證據是 unlink() 不拋 —— POSIX 上刪開著的檔會成功,seal_day 退化 no-op 也照綠。
try/finally 收尾;補一條正面斷言(seal 後 observe 該日 → sealed_dropped 前進 + WARNING 一次)。
```
#### #27 逾時說「子程序已殺」,但殺人的那個分支跟 prod 預設 runner 都零覆蓋
**File**: `copycat/server/ticks_compactor.py`
**Line**: 81

**Comment**:
```
_attempt_once 逾時回「(> N s,子程序已殺)」,實際殺的是 run_compact_subprocess 的 except CancelledError: proc.kill()。
make_subprocess_runner(prod 預設)零測試 caller、run_compact_subprocess 只有 happy path;逾時測試用 fake _Hang 走不到 kill。
分支壞了的話 Windows 孤兒子程序會繼續握著 jsonl / .tmp,三次重試撞 PermissionError 後放棄,log 卻說已殺。
加一條:對真子程序 create_task 後立即 cancel,斷 proc.returncode is not None。
```
#### #28 值域 parametrize 少了 retry_secs 跟兩種 compact_time 越界
**File**: `tests/test_ticks_config.py`
**Line**: 57

**Comment**:
```
__post_init__ 擋五件事,這裡只蓋四件:retry_secs <= 0、compact_time 時/分越界("24:00" / "12:60")、
非數字("aa:bb")都沒案子 —— 刪掉 retry_secs 那行本檔仍綠。
retry_secs=0 的後果正是檔頭要擋的:退避變 0 → 13:45 起每輪 tick 再開一個轉檔子程序。
四個字面加進既有 parametrize 就好。
```
#### #29 _TickRecorder 跟既有 FakeHub 幾乎一樣,TestBookRow 又重抄一份 _make
**File**: `tests/server/test_tick_persist.py`
**Line**: 58

**Comment**:
```
tests/ 裡 def on_rollover_pending 只有兩處:既有 test_stock_engine.py::FakeHub(存 cum_vol)跟這支(存 StockTick)。
TestResilience / TestReviewRound1 只用 len(recorder.ticks),FakeHub 直接可用;
round-trip 那案要 tick 本體,讓 FakeHub 多留一份也行。
另外 :245–:253 整段重抄 _make 只為拿 persist —— engine.tick_persist 這個 property 後面已經用了三次;
_make 補個 opener= 參數還能收掉 TestResilience 三處 8 行重複。
```
#### #30 檔頭說「不碰計數器」,檔內卻靠計數器釘住重複簿去重
**File**: `tests/server/test_tick_persist.py`
**Line**: 3

**Comment**:
```
docstring 寫「只斷言檔案內容與 load_day 讀回,不碰 handle / 緩衝 / 私有計數器」,
實際還斷了 persist.dup_books / sealed_dropped(公開計數器)、log 字面、緩衝未落地、compactor.dir。
這些都合理,但日後有人照 docstring 判「這裡不該碰計數器」就會誤刪唯一釘住重複簿計數的斷言。
改成列出真正的觀測面:檔案 / load_day / 公開計數器 / log 契約行。
```
#### #31 verification 的章節序是 1 2 3 4 7 5 6,交叉引用指錯節
**File**: `.claude/feat/tick-persist/verification.md`
**Line**: 43

**Comment**:
```
§7 夾在 §4 跟 §5 之間;§7 末列寫「本檔 §6」但 §6 是真環境判準,不是「文件三處齊」的證據。
§7 移到 §6 之後(或改號),交叉引用改指 §3 的 gate 或直接指 commit。
```
