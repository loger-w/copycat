# #267 簿重播引擎 + keyframe/delta 外掛檔 + CLI —— verification

spec #265 / ticket #267;branch `feat/book-replay-engine`(worktree);venv = 主 tree `.venv`(worktree 無 venv,pyproject `pythonpath=["."]` 讓 worktree 的 copycat 蓋過 .pth)。
動到 frontend/:否(npm / tsc / react-doctor 不適用)。

## 1. 自動化 gate(CLAUDE.md §1「完成前 gate」)

每條輸出導到檔案、exit code 單獨取,不接管線後綴。gate 1–4 皆在最終 commit(f86676a1)上跑。

| # | 指令(repo root = worktree) | 結果 | exit |
|---|---|---|---|
| 1 | `.venv\Scripts\python -m pytest -q -rs -p no:cacheprovider`(全量,最終版 f86676a1) | **3588 passed, 3 skipped, 2 warnings in 272.31 s** | 0 |
| 2 | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! | 0 |
| 3 | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings, 0 informations | 0 |
| 4 | `.venv\Scripts\python -m copycat validate --run-five <主 tree>/out/five_tigers --run-four <主 tree>/out/four_tigers` | 42/42 PASS | 0 |
| 5 | `.venv\Scripts\python -m pytest -q tests/test_book_replay.py`(議定 seam 單檔) | 27 passed | 0 |

- 3 skipped 皆既有環境 skip:`tests/backtest/test_characterization.py:47`(worktree 無 `data/` 種子)、`tests/live/test_tc4.py:521/531`(worktree 無 gitignored `spikes/TCPY`)。2 warnings = 既有 `test_tick_persist` 的 `_CloseFailingFile` unraisable。
- 新增檔 `copycat/book_replay.py` / `tests/test_book_replay.py` 已 `ruff format`;`copycat/cli.py` 在 master 就未 format,依 backend-conventions 不整檔重排。

### 突變驗證(review 收修的新檢查不是空轉)

`scratchpad/mutants_round2.py`(還原走記憶體寫回、每顆後 sleep 1.1 s 避同秒 pyc):5/5 KILLED —— trade 長度檢查拿掉(1 failed)、kind 字元檢查拿掉(1 failed)、收到時刻不做不倒退(1 failed)、異常筆數把時鐘點也算進去(2 failed)、成交欄位漏存內外盤(2 failed)。另 recv 長度檢查單獨突變 1 failed。round 2 新增的 5 條竄改測試(收到時刻倒退 / clock 長度奇數 / 時鐘點落在簿則 / 缺鍵 / 呼叫鍵不符)實作前全紅。

## 2. 真實環境(CLI shape:真 argv × 多 + exit code + stdout/stderr;evidence/cli_runs.txt)

| 情境 | 指令摘要 | 結果 |
|---|---|---|
| Happy | `book-replay --date 20260916 --dir data/ticks --out <scratchpad>` | exit 0;80 檔、2,841,208 則、「達錢時刻異常、不當標籤時刻的成交 1 則」、**21.5 MB、84.5 s(單獨跑)、peak WS 5.7 GB** |
| 決定性 | 同目錄重跑;最終版程式(f86676a1)再跑一次 | exit 0;80 檔 sha256 全同、無殘留 .tmp;最終版輸出與 round 2 收修前逐位元組相同 |
| Edge:未轉檔 | 只有 `20260916.jsonl` 的目錄 | exit 2「tick 存檔還沒轉檔」,零輸出 |
| Edge:只剩成交 parquet | 只複製 `20260916.parquet` | exit 2「簿 parquet 不在(過了保留期?)」,零輸出 |
| Edge:無存檔日 | `--date 20260915` | exit 2「沒有這天的 tick 存檔」 |
| Edge:日期格式 | `--date 2026-09-16` | exit 2「--date 須為 YYYYMMDD」 |
| 回歸:ticks-compact(未改) | `ticks-compact --date 20260916` | exit 2 照舊拒絕,parquet 未動 |
| 回歸:validate(引擎回放,未改) | 見 gate 4 | 42/42 PASS |

### 抽樣驗證 vs 直讀 parquet(evidence/verify_against_parquet.py → .out.txt,exit 0)

不經引擎、不經 `load_day`,pyarrow 直讀 `20260916.parquet` + `20260916-book.parquet`:

- (a) 全量 80 檔 **2,841,208 則**(msg_seq / 種類 / 五檔 20 格 / 收到時刻軸 / 成交欄位)**0 不符**
- (b) `book_at` 跳轉(keyframe 前後 kK−1 / kK / kK+1、首尾、隨機 200):**48,978 則 0 不符**
- (c) 指名時刻(收到時刻軸):2426 11:02:43.500 → 99.1×24;11:02:45.700 → 99.1×183;3441 09:04:42.500 → **181.0×100**(spec「09:04:42 該價位有 100 張」);2305 09:07:47.500;3441 09:09:01.500 —— 全部與 parquet 同一則逐格相等

### 瀏覽器 file://(evidence/file_url_decode_check.html、file_url_decode_results.txt、file_url_decode_2303.png)

chrome-devtools MCP 以 `file:///` 開頁、`<script src>` 載外掛檔、JS 照模組說明獨立解碼:2426 / 2303(最大檔 137,299 則,gunzip+parse 60 ms,跳轉 0.10 ms)/ 1815(第 0 則 = 07:31 收到的前一日成交)全 PASS;keyframe 對播放不符 0、收到時刻軸倒退 0、trade 欄長度相符;console 零訊息。第一版格式另驗 3441 市價佇列「0×3334」與 null 分得開。跨語言:Python `book_at(2303, 137042)` 與 JS 同一則逐格相同。

## 3. 驗收條件逐條對照(#267)

| AC | 實作 | 測試(`tests/test_book_replay.py`) | 真實環境證據 |
|---|---|---|---|
| CONTEXT 新增「簿重播」(區分引擎回放)、「厚檔」(區分大單敲檔) | `CONTEXT.md`「簿重播」節 + 分點指紋節「引擎回放」條目 | — | `git show 08f3beb8 828c0c29 -- CONTEXT.md` |
| 「五檔」修正不可回測敘述、指向 tick 存檔 | `CONTEXT.md`「五檔」;CLAUDE §0a 同步收窄 | — | 同上 |
| 吃 TickRow、嚴格按 msg_seq、吐每則簿狀態、不做 IO | `book_replay.replay_books` / `Frame`;模組只 import stdlib + `copycat.ticks`(grep `open(`/`Path`/`write` 0 命中) | `TestBookReplayOrdering::test_groups_by_code_and_orders_each_code_by_msg_seq`、`test_one_call_covers_one_trading_day` | verify (a) 0 不符 |
| 空簿不崩 | 20 格原樣保留 None / 0 | `TestPluginEncoding` 三條 round-trip / 跳轉(fixture 含市價佇列 0、賣方全空、兩邊全空) | 09-16 賣方全空 27,948 則、買方全空 13,023、兩邊全空 15(2426 賣方全空 2,776)全數編解 0 不符 |
| 時刻異常不讓時間軸倒退 | `_is_clock_point`(未來 > 60 s / 早於時鐘不推進)+ `recv_ms` 取不倒退值 | `TestClock` 四條、`TestRecvAxis::test_every_message_sits_on_a_never_rewinding_server_receive_time_axis` | 09-16 異常 1 則(1815 07:31 收到 14:30);收盤撮合晚到 5–40 s 照推進;收到時刻軸倒退 0 |
| keyframe + delta、gzip + base64、file:// 可讀 | `encode` / `plugin_js`(`window.__bk`,gzip mtime=0) | `test_plugin_file_is_one_script_line_carrying_gzip_base64_json` | 瀏覽器 file:// 三檔 PASS |
| round-trip 自檢含 keyframe 邊界 | `decode`(每個 keyframe 比對播放路徑 + 檔頭自檢)、`book_at` | `test_round_trip_reproduces_every_frame_across_keyframe_boundaries`、`test_jumping_to_any_message_from_its_keyframe_matches_the_book_replay`[K=1/3/256]、`test_decode_refuses_*`(delta 對不上 keyframe + 11 種檔頭竄改)、`test_parse_refuses_*`(非外掛檔 / 呼叫鍵不符) | CLI 每檔落檔前解回比對(80 檔全過);JS 端 keyframe 自檢 |
| CLI 產 09-16 全部個股、輸出目錄可指定 | `cli.py::_book_replay`(`--date` / `--dir` / `--out`) | —(議定無 CLI seam) | cli_runs.txt Happy + 4 edge |
| 抽樣驗證 vs parquet | — | — | verify_against_parquet.out.txt (a)(b)(c) |

## 4. 追加決定(review 後 user 拍板,已追記 #265 / #268)

- 時間軸 = server 收到時刻(`Frame.recv_ms`、外掛檔 `recv`);文字標籤維持「成交時刻之後第 N 則」。依據:即時個股成交時刻只到整秒(09-16 次秒全 0),收到時刻 − 達錢時刻最小 81 ms、每 100 ms 桶均勻。
- 成交則帶 `[達錢時刻, 價, 張, 內外盤]`(`Frame.trade`、外掛檔 `trade`)。
- 即時整秒 vs 研究歷史 TICKS 約 11% 帶毫秒 → 線上掃單分群尺不同 → issue #274(本批不改程式;skill tc4-market-facts 已標註)。

## 5. 已知限制 / 留尾

- CLI 峰值記憶體 5.7 GB 幾乎全來自 `load_day` 一次讀整天(本機 33 GB);未改 loader(已寫進 CLAUDE §1 列)。
- `--date` / `--dir` 參數與 ticks-compact 重複 → docs/next-time.md 2026-09-16 節。
- 回看頁資料夾尚未放外掛檔(資料夾命名與 `window.__bk` handler 屬 #268)。
