# pr-275 review 收修(13 條)—— verification

來源:`docs/superpowers/specs/pr-275-review.md`(本分支第 1 筆 commit 入 docs);user 2026-09-16 拍板:F-07 選「只記例外」、
版本維持 v1、F-11 在本分支重做一份驗證、其餘照建議、F-13 不修。
branch `fix/pr-275-review-followups`(worktree);venv = 主 tree `.venv`(worktree 無 venv,pyproject `pythonpath=["."]`
讓 worktree 的 copycat 蓋過 .pth;CLI 以 `python -m copycat` 在 worktree 根跑,吃 worktree 的碼)。動到 frontend/:否。

## 0. 逐條處置

| # | 處置 | 實作 / 位置 | 測試(議定 seam = `copycat.book_replay` 公開介面) | 證據 |
|---|---|---|---|---|
| F-01 | 修 | — | `TestPluginEncoding::test_payload_layout_matches_the_documented_v1_literal`(golden 4 則、keyframe_every=2、整個 payload 對寫死字面) | 突變體 kind-code-swap / trade-cells-reversed-symmetric KILLED(§1) |
| F-02 | 修 | — | `test_round_trip_keeps_labels_before_the_first_clock_point_and_on_anomalous_trades` | 突變體 decode-first-clock-index KILLED |
| F-03 | 修(隨 F-07 改寫成新格式的檢查) | `_check_header` anomalous 清單、`decode` 時鐘點成交 | `test_decode_refuses_an_anomalous_trade_list_that_contradicts_the_trades`(7 案) | 突變體 header-anomalous-* ×3、decode-rewind-check、decode-ms-none-check KILLED |
| F-04 | 修 | — | `TestClock::test_the_future_tolerance_is_sixty_seconds_inclusive`(60.000 / 60.001 s) | 突變體 tol-3000 / tol-60001 / tol-strict-lt KILLED |
| F-05 | 修 | — | `test_plugin_file_is_one_script_line_carrying_gzip_base64_json`(MTIME 位元組、三條 assert 拆開) | 突變體 gzip-mtime KILLED |
| F-06 | 修 | `cli.py::_book_replay`:先 mkdir,`load_day` / `replay_books` 進 `except OSError` | —(CLI 非議定 seam) | §2 edge 三條 |
| F-07 | 修(user 拍板「只記例外」,v1 不升版) | `encode` / `decode` / `_check_header` / `PluginPayload` / 模組說明:`clock` → `anomalous` | golden、round-trip、anomalous 竄改表 | §2 大小對照、獨立驗證 (a) |
| F-08 | 修 | `_check_header` kf_every、`encode` keyframe_every、`_apply_delta` 成對 / 欄號、`decode` 序號 / 內外盤、`book_at` 範圍 | `test_decode_refuses_messages_that_break_the_documented_values`(5 案)、檔頭表 `keyframe-interval-zero`、`test_encode_refuses_a_keyframe_interval_below_one`、`test_book_at_refuses_an_index_outside_the_messages` | 突變體 values 組 9/9 KILLED;真資料不誤擋(§2 Happy exit 0) |
| F-09 | 修 + 數字實算校正 | `CONTEXT.md`「簿重播」、模組說明 | — | §3 |
| F-10 | 修 + 數字實算校正 | `.claude/skills/tc4-market-facts/SKILL.md` | — | §3 |
| F-11 | 重做(舊 artifact 原樣保留) | `evidence/verify_against_parquet.py` | — | §2 |
| F-12 | 修 | `CLAUDE.md` §4 tick 存檔條、`ticks_compact.py` 註解 | — | — |
| F-13 | 不修(流程議題) | — | — | — |

## 1. 自動化 gate(CLAUDE.md §1「完成前 gate」)

全部在最終程式 commit(本分支第 14 筆「chore(docs): 格式說明補 seq 每項 > 0 …」)上跑;輸出導檔、exit 單獨取。

| # | 指令(worktree 根) | 結果 | exit |
|---|---|---|---|
| 1 | `.venv\Scripts\python -m pytest -q -rs -p no:cacheprovider`(全量) | **3606 passed, 3 skipped, 2 warnings in 241.00 s**(`evidence/gate_pytest.txt`) | 0 |
| 2 | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed!(`gate_ruff.txt`) | 0 |
| 3 | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings, 0 informations(`gate_pyright.txt`) | 0 |
| 4 | `.venv\Scripts\python -m copycat validate --run-five <主 tree>/out/five_tigers --run-four <主 tree>/out/four_tigers` | 42/42 PASS(`gate_validate.txt`) | 0 |
| 5 | `.venv\Scripts\python -m pytest -q tests/test_book_replay.py`(議定 seam 單檔) | 45 passed(merge-base 27 條;本分支新增 20、兩條 clock 竄改案隨格式退場由 anomalous 竄改表承接) | 0 |

- 3 skipped 皆既有環境 skip:`tests/backtest/test_characterization.py:47`(worktree 無 `data/` 種子)、`tests/live/test_tc4.py:521/531`(worktree 無 gitignored `spikes/TCPY`);2 warnings = 既有 fastapi testclient 棄用 + `test_tick_persist` 的 `_CloseFailingFile` unraisable(同 #267)。
- 格式:`copycat/book_replay.py` / `tests/test_book_replay.py` 以 venv ruff 0.15.20 format(兩檔在 merge-base 已 formatted);`copycat/cli.py` 在 master 未 format → F-06 以精確字串替換腳本改 4 行,不經自動排版整檔重排。

### 突變體(`evidence/mutants.py` → `mutants.out.txt`;最終碼上跑,記憶體寫回還原 + 每顆前後 sleep 1.1 s 避同秒 pyc)

**23/23 KILLED**,還原後 45 passed、`git diff HEAD -- copycat tests` 為空:

- pin(F-04 / F-05,既有行為首次被釘):容差改 3_000、改 60_001、`<=` 改 `<`、gzip mtime 改 12345 —— 各紅 1 條
- format(F-01 / F-02 / F-03 / F-07):decode 首筆成交前則號 −1→0(1)、kind t/b 對調(1,只有 golden 抓得到)、成交格序編解碼對稱反轉(3)、`Frame.anomalous_trade` 取反(8)/ 拿掉成交條件(3)、anomalous 清單不遞增 / 越界 / 落在簿則(各 1)、時鐘點倒退檢查(2)、無時刻檢查(1)
- values(F-08):header kf_every、encode keyframe_every、delta 奇數長度、欄號下界、欄號上界、序號 `<=`→`<`、內外盤值域、book_at 下界、book_at 上界 —— 各紅 1 條
- 紅先行:F-07 的 8 條(golden 1 + anomalous 竄改 7)與 F-08 的 9 條在實作前全紅,失敗原因逐條對過 review 所報缺口(commit body)

## 2. 真實環境(2026-09-16 tick 存檔,`C:\side-project\copycat\data\ticks`;兩個 parquet mtime 13:45:55 / 13:46:03 全程未動)

CLI shape:真 argv × 多 + exit code + stdout / stderr(`evidence/cli_runs.txt`,runner = `evidence/run_cli.ps1`)。輸出目錄在 session scratchpad(不進版控;同資料重跑逐位元組相同,可隨時重產)。

| 情境 | 結果 |
|---|---|
| Happy:全日 80 檔(F-07 格式 + F-08 檢查 + F-06 CLI) | exit 0;80 檔、2,841,208 則、時刻異常成交 1 則、**19.4 MB**(19,429,892 bytes)、90.6 s |
| 決定性:同碼重跑到另一目錄 | exit 0、85.7 s;80 檔逐位元組相同、無殘留 .tmp(`evidence/determinism.txt` 比對 1) |
| 最終版(two-axis review 收修後)再跑 | exit 0、81.9 s;與第 1 次逐位元組相同(比對 2)—— review 收修(Frame property、測試重構、docstring)零輸出差異 |
| 第 3 次重跑 | exit 0、71.6 s(本想量峰值記憶體:runner 量的是 venv launcher,量到 0,量測方式無效;峰值沿用 #267 的 5.7 GB,`load_day` 未改) |
| Edge F-06:`--out` 路徑中間是檔案 | exit 1、**0.3 s**,stderr 一行「簿重播 2026-09-16 失敗(IO):[WinError 183] …」—— 讀整天之前就失敗(修前要先讀完約 30 s) |
| Edge F-06:成交 parquet 讀取權限被拒(scratch 複本 `icacls /deny USER:(RD)`,驗完已移除) | exit 1、0.3 s,stderr 一行「失敗(IO):[WinError 5] Failed to open local file … 存取被拒」,無 traceback |
| Edge F-06:壞 parquet(18 bytes 文字) | exit 1,**完整 traceback 止於 `pyarrow.lib.ArrowInvalid`**(ValueError,刻意不接,照舊大聲失敗) |
| 副作用(知情):F-06 先 mkdir | 讀檔失敗的兩個情境留下空的 `<out>/2026-09-16/`(0 檔);前置檢查擋下的情境不建目錄 |
| Edge(前置檢查未改):只有 jsonl / 只剩成交 parquet / 無存檔日 / 日期格式 | 皆 exit 2,訊息同 #267;不建輸出目錄 |
| 回歸(未改功能):`ticks-compact --date 20260916 --dir <真資料>` | exit 2「jsonl 不存在」,parquet 未動 |

### F-07 大小對照(`evidence/size_old_vs_new.py` → `.out.txt`,exit 0)

從 CLI 產的新格式檔解碼、還原舊格式(`clock` = after == 0 的則,放回原鍵位)再走同一支 `plugin_js`:**舊 21,465,024 → 新 19,429,892 bytes(−9.5%)**;時鐘點 375,386、時刻異常 1;新格式重編碼 == 檔案原文。還原出的舊格式總位元組數,與改格式前(本 session 用當時的舊編碼器、逐檔讀 parquet 的唯讀探針 `evidence/f07_size_probe_pre_change.py`)量到的 21,465,024 相同 —— 還原忠實;探針同一趟另量「只存時鐘點則號」20,646,220(−3.8%),user 選了只記例外。

### 獨立驗證 vs 直讀 parquet(F-11 重做:`evidence/verify_against_parquet.py` → `.out.txt`,exit 0,最終版輸出)

真值側只用 pyarrow 讀兩個 parquet,不經引擎、不經 `load_day`、不經 `decode`;#267 版腳本原樣保留在 `.claude/feat/book-replay-engine/evidence/`。F-11 四點:

- (a) 全量 80 檔 **2,841,208 則**:msg_seq / 種類 / 五檔 20 格 / 收到時刻軸 / 成交欄 / **文字標籤 (clock_ms, after)** —— decode 不符 0 檔;**只照格式說明從原始 payload 推的標籤**不符 0 檔;`anomalous` 清單對真值側照模組說明重算的時刻異常則號不符 0 檔(唯一 1 則 = 1815 第 0 則,07:31:22.730 收到、蓋 14:30:00.000)
- (b) **代號集合 parquet 80 = 外掛檔 80**,少產 / 多產皆空
- (c) `book_at` 跳轉(keyframe 前後、首尾、隨機 200):48,978 則 0 不符
- (d) 指名時刻(標籤由真值側重算):2426 11:02:43.500 / 11:02:45.700(99.1×183)、3441 09:04:42.500(181×100)、2305 09:07:47.500、3441 09:09:01.500、1815 09:00:03.000(首筆成交前第 1 則)、1815 09:00:10.000(成交 09:00:09.000 之後第 9 則)—— 五檔與標籤皆相等
- (e) 空簿(本腳本算、印在輸出):賣方全空 27,963 / 買方全空 13,038(皆含兩邊全空)、兩邊全空 15;不含兩邊全空 = 27,948 / 13,023 —— 即 #267 verification 的口徑;2426 賣方全空 2,776 則(共 64,512 則)
- 第一個不符的定位改用 `next(..., None)`(前綴相同、長度不同也印得出來)

## 3. 文件數字的實算依據(F-09 / F-10;09-16 成交 parquet 全量,唯讀;`evidence/recv_lag_outliers.py` / `recv_lag_buckets.py` → `.out.txt`)

- 375,387 筆成交;`recv − 達錢時刻`(收到時刻換台北當日毫秒)全體 min −25,117,270 / max 118,594 ms、p50 614 / p90 1,023 / p99 1,114
- 離群 81 筆:13:30:00.000 收盤撮合 79 筆晚到 1,369–39,787 ms(56 筆 > 5 s);7772(`TradeStatus=1` 緩撮)1 筆 118,594 ms;1815 1 筆 −25,117,270 ms
- 一般盤中成交 375,306 筆:81–1,279 ms(310 筆落在 1,138–1,279 —— 修前文件寫的上界 1,137 不對)、p50 614 / p90 1,023 / p99 1,113;100–1,099 ms 每 100 ms 桶各 8.7–10.3%
- 同數字由 Spec 軸 sub-agent 以 pyarrow 獨立重算一致(code-review-round-1.json spec 末條)
- 新檢查不誤擋真資料(`evidence/decode_checks_vs_real_data.py` → `.out.txt`):兩個 parquet 合計 2,841,208 則 msg_seq 全不重複、最小 157;成交內外盤只有 inner 170,410 / outer 204,972 / neutral 5;成交時刻 / 價 / 張 / time / 內外盤零 null

## 4. Review(code-review-two-axis,fixed point `1c964d51`;原文與逐條處置 `code-review-round-1.json`)

- Standards:硬性違規 0;judgement 7 條 + 軸外備註 1。接受已修 S-02 / S-04 / S-06 / 軸外備註;部分接受 S-01(文件,不改型別)/ S-05(§1 大小已改,CONTEXT 數字維持 —— F-09 user 拍板的處置);反駁 S-03;S-07 知情不改寫歷史。
- Spec:must / should 0;nice 4 條全接受(P-01 merge 後在 #268 / #265 留言、P-02 刪句、P-03 seq 條、P-04 印 2426)。Spec 軸以 #267 舊編解碼器對新版做隨機差分 6,000 檔日 / 122,763 則 / 26,961 筆時刻異常成交:每則 (clock_ms, after) 與 `book_at` 全同。
- 收修後增量 4 筆 commit:main session 機械快篩(45 條單檔綠、ruff / pyright 0、最終版 CLI 輸出與收修前逐位元組相同、突變體在最終碼重跑);依鐵則 G 不開第二輪 sub-agent。

## 5. 留尾

- **收修 PR 不自動 `/pr-review`**:依 2026-09-03 拍板(review 收修 PR 不再自動,避免遞迴;前例 #162 / #168 / #169 / #172 / #176 / #178,之後 #229 / #239 / #252 / #264 亦無)。handoff 寫「merge 後再自動 /pr-review」與此不一致,回報 user。
- 峰值記憶體量測腳本只量到 venv launcher(Windows venv 的 python.exe 會再起 base interpreter 子行程),本批未重量;要量得用行程內 `GetProcessMemoryInfo` 或監看子行程。
- merge 後:#268 留言(新格式 / 19.4 MB / 可信規則 / #267 證據頁讀的是舊 `clock`)、#265 追記規則措辭。
