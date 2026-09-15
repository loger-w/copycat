# diagnosis — perf/batch-b-tier0(批 B:Tier 0 八件 + 1-1)

2026-09-15 00:15–00:40。量化目標 gate + 定位。定位不重做:四輪掃描(`docs/research/2026-09-13-MASTER-priorities.md`
§1 Tier 0 / Tier 1-1;`verify-bakeoff/{T1,T2,T4,C1}`;`arch-scan/{B04,B05,X4}`)已把每一條的瓶頸拆到行號與 µs,
本檔只做兩件事:(1) 用**可重跑、stdlib-only、before / after 同一把尺**的 harness 把 baseline 在本機重新量一次
(不引用 Opus session 的數字當 baseline);(2) 逐條寫下目標 threshold 與量測指令。
**§1 表的數字是首輪(未存檔)**,同量級但非逐格等於後來 committed 的 `evidence/out_before_*.json`(例:0-4 push 0.005 vs 0.0084、
0-6 orders 1328 vs 1345.7、bench_01 `--n 30` vs `--n 60`);正式 before 以 `out_before_*.json` 為準(pr-251 review F-20)。

## 0. Baseline 前置:auto-verify 全綠(壞 tree 量出的 baseline 無意義)

主樹 master `1e0720be`(working tree 只有兩份他 flow 的 verification.md 未 commit,不影響 code):

| gate | 結果 |
|---|---|
| `.venv\Scripts\python -m pytest -q` | **3394 passed**,218 s,exit 0 |
| `ruff check copycat tests` | All checks passed,exit 0 |
| `pyright` | 0 errors,exit 0 |
| `copycat validate` | 未跑(本批不碰 replay / engine;收尾 gate 再跑) |

環境:Windows 11 10.0.26200、Python 3.13(.venv)、prod server 跑著(`/api/health` git_sha 1e0720be,
started 23:59:44,TC4 夜盤連著)—— 全部 harness 都不碰 ZMQ / 不起第二台。

## 1. 逐條:現況數字 / 量測方式 / 目標

harness 全在 `evidence/`,`--repo <root>` 指向要量的那份 code(主樹 = before;worktree = after)。

| # | 現況(本機重量) | 量測指令(unit) | 目標 threshold | 依據 |
|---|---|---|---|---|
| 0-1 | tc4 `_collect_history` **150.5 ms** p50 / river `collect_1k_minutes` **150.3 ms** p50(假 TC4 首頁 15–40 ms 備妥;polls 4.0) | `bench_01_history_poll.py --n 30`(ms) | **≤ 45 ms** p50 兩條路徑;倍增 / 1.0 s 上限 / 預算不動 | C1 §4.1(153 ms 裡 150.5 ms 是 sleep) |
| 0-1 prod | 150 檔冷 overlay 進群組 **≈5.8 s**(C1 §4.2 由 M=4 25.7 檔/s 外推,非直量) | 重啟後盤後 `bench_04_prod_overlay.py 150`(s;OverlayCache per-app in-memory,重啟即冷) | **≤ 3 s** | C1 §4.2 |
| 0-2 | `evaluate`(只開 vol_burst)每 tick **13.2 / 89.9 / 287.5 µs** @ 窗 301 / 3001 / 9901 筆 | `bench_02_eval_volume.py --rates 1,10,33`(µs/tick p50) | **窗長無關、≤ 5 µs** 三個窗長同一數量級 | T2 §4、X4-01、B05-01 |
| 0-4 | `correlations()` **9.06 ms** p50 每秒(11 腿 × 3 窗 × 1800 筆;push 0.005 ms) | `bench_04_corr_state.py --warm 1900 --measure 300`(ms) | push + correlations 合計 **≤ 0.1 ms** p50;`--drift` 的 `n_mismatch == 0` | T2 §2、X4-02 |
| 0-5 | `append_audit` **205.9 µs** p50(mkdir 在鎖內) | `bench_05_audit.py --n 3000`(µs) | **≤ 140 µs** p50 | T1 §D1-05 |
| 0-6 | route n=400:positions **794 µs** / orders **1328 µs** / fills **670 µs** p50 | `bench_06_asdict.py --n 400`(µs/await) | positions **≤ 100 µs** p50;orders / fills 同比 | T1 §9 |
| 0-7 | prod-like(不動 timer):loop p50 **58.0 ms**(0.005)vs **58.2 ms**(0.001)—— **零差異**(首輪未存檔;重跑存檔 `evidence/out_bench_07_base.json`:72.1 / 58.3、57.5 / 58.1,p99 275–341 —— 同量級、無「0.001 更好」的方向);套 0-3 組態:**16.8 → 4.0 ms**(重跑 `out_bench_07_timer1ms.json`:17.3 → 3.68、16.6 → 3.51) | `bench_07_switchinterval.py --threads 4 --rounds 2 [--timer-1ms]`(ms) | 原目標 ≤ 4 ms **只在 0-3 組態成立**;prod-like 達不到 → 見 §2 | T4 §3.4(T4 表全程開著 timer_1ms);artifact 於 pr-251 review F-08 補跑 |
| 0-8 | 機制項:停用規則的 `set_basis` 死工(每次 basis 分發 × 停用 slot 數) | 測試斷言(spy)而非計時 | 停用 slot 零 `set_basis` 呼叫 | MASTER 0-8 |
| 0-9 | `evaluate_book` 無 latch **2.2 µs** p50(每則簿更新 × 每 slot) | `bench_09_evaluate_book.py`(µs) | **≤ 0.5 µs** p50 | MASTER 0-9(推估→本機實量) |
| 1-1 | 江波圖 snapshot in-memory 分鐘鍵 = `int`;wire sha256 `01f4bb75…`(snapshot)/ `3a34b497…`(delta) | `check_11_river_wire.py`(sha256) | **sha 逐位元相同**、snapshot(wire 前)鍵型別 `str`、in-memory `_minutes` 仍 `int`(pr-251 review F-18 更正) | T1 §6.3 |

## 2. 定位結論與意外

- **0-7 的收益整條掛在 0-3 上**(本機實量,兩輪重現):不動 timer 解析度時,switchinterval 0.001 與 0.005
  的 loop p50 都是 58 ms、p99 反而 292 → 356 ms;套 EcoQoS 豁免 + `timeBeginPeriod(1)` 後才是 T4 表的
  16.8 → 4.0 ms。機制:GIL 交棒等的是 condvar timeout,Windows 上同樣吃 15.6 ms 的 timer quantum,
  1 ms 與 5 ms 都被夾成 ~15.6 ms。**T4 表的 `main()` 第一行就是 `timer_1ms()`**,主文件把它壓平成
  「一行」時掉了這個前提。→ 0-7 單獨上 = 付 −8.7% 飽和吞吐買零收益;策略見 spec。
- **0-2 的「三個清空點」**:signal_state 沒有 `apply_backfill` —— 回補重放不經 detector
  (`stock_engine.py:1349-1352` SC-5 註解:`on_tick` 只掛在 `ingest` 為真的分支)。真正會動 `_window` 的地方
  = 首 tick 初始化(`:375`)/ append + popleft(`:379-383`)/ `reset_day`(`:311`)/ `drop_code`(`:332`),四處。
- **0-4 的真風險是窗邊界不是浮點**(T2 §9 意外 1):現況對**中價**序列逐出(`ts < now − 1800`)、配對報酬
  取較晚那筆 ts → 最長窗實際 1800 筆;60 / 300 窗因中價沒被逐出,`ts ≥ now − w` 是 w+1 筆。增量版必須
  兩道語意都鏡像(push 時依「最老倖存中價 ts」丟配對;`correlations(now)` 時逐窗 `ts < now − w` 丟),
  守門測試斷 `n{w}` 完全相等。另:`corr_engine.tick_once` 的 `now` 與 `state()` 內 `self._now()` 是**兩次取樣**
  (差 µs),增量版的逐出要以 `correlations(now)` 的 now 為準,與現況同。
- 0-5 的既有測試 `test_creates_missing_dirs` 是行為合約(append 自建缺目錄)—— 「搬啟動」不能單純搬走,
  熱路徑要留 FileNotFoundError 才 mkdir 的自癒退路。
- 0-6 三個 dataclass 全是純量欄(pyright 實查:`Position.kind` 是 Literal 字串),`asdict` 的遞迴 / deepcopy
  在這裡全是浪費;`{**o.__dict__, "code": …}` 輸出逐鍵相同。
- 0-1 的兩個常數在兩個檔各一份(`tc4.py:54` / `river_backfill.py:31`),既有測試
  `test_backoff_starts_well_below_poll_wait` 斷 `slept[0] <= 0.15`,改 0.02 仍綠。
