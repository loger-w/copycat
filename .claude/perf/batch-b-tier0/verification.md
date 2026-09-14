# verification — perf/batch-b-tier0(spec #240;tickets #241–#250)

2026-09-15 00:15–02:30。worktree `.claude/worktrees/perf-batch-b-tier0`,分支 `perf/batch-b-tier0`,
fixed point `1e0720be`(origin/master)。python 一律主樹 venv 絕對路徑(worktree 無 .venv)。

## 1. 自動化 gate(全部 exit 0)

| gate | 指令 | 結果 |
|---|---|---|
| pytest 全量 | `C:/side-project/copycat/.venv/Scripts/python -m pytest -q`(worktree) | **3419 passed, 3 skipped**,214 s,exit 0(baseline master 3394 passed;+25 = 本批新測試) |
| 3 skipped 追查 | `pytest -rs tests/live/test_tc4.py tests/backtest/test_characterization.py`(Copy-Item `spikes/TCPY` 進 worktree 後) | test_tc4 **104 passed**(2 個 skip 是 worktree 缺 gitignored TCPY);剩 1 skip = backtest characterization 需 `data/` 種子(本批未動 backtest;主樹 baseline 含它全綠) |
| ruff | `ruff check copycat tests` | All checks passed,exit 0 |
| ruff format(新檔) | `ruff format --check` 於 corr_state / win_timer / test_ws_has_clients / test_win_timer / test_models | already formatted |
| pyright | `python -m pyright`(worktree) | 0 errors(中途 test_models parity 案 2 errors → 4bcecb2a 收) |
| validate | `python -m copycat validate --run-five C:/side-project/copycat/out/five_tigers --run-four .../four_tigers` | **42/42 PASS**,exit 0 |

紅先行證據(每張 ticket 先加測試看紅再改):0-1 兩案紅(`slept[0]` 0.15 ≠ 0.02)→ 綠;0-2 兩案 `AttributeError _window_vol` → 綠;
0-9 `calls["n"] == 0` 紅(before 呼叫 now_fn 一次)→ 綠;0-8 `seen` 停用 slot 收到 2330 紅 → 綠;0-3 ImportError(win_timer 不存在)→ 綠;
0-4 / 0-5 / 0-6 / 0-7 / 1-1 屬行為不變的 perf 改寫,守門測試在 before 與 after 都應綠(它們釘的是「不變」),red 由 harness 數字扮演。

## 2. 量測 gate(before = 主樹 master 1e0720be;after = worktree;同一支 harness,`evidence/out_{before,after}_*.json`)

| # | 尺(unit) | before | after | 目標 | 判 |
|---|---|---|---|---|---|
| 0-1 | `bench_01 --n 60 --timer-1ms`(ms p50;假 TC4 備妥分佈對齊 C1 掃描) | tc4 150.5 / river 150.4 | **20.6 / 20.6**(mean 30.5 / 35.8;p90 60.8 = 倍增第二輪落點 20+40) | ≤ 45 | **PASS**(p50);p90 61 見 §4 |
| 0-1 prod | 重啟後盤後 `bench_04_prod_overlay.py 150` | ≈5.8 s(C1 外推) | 待 user 重啟 | ≤ 3 s | 待驗 |
| 0-2 | `bench_02`(µs/tick p50 @ 窗 301 / 3001 / 9901) | 12.9 / 89.7 / 286.3 | **4.3 / 4.3 / 4.3** | 三窗 ≤ 5、窗長無關 | **PASS** |
| 0-3 | `bench_03 --mode apply` 60 s,run.ps1 同款 `Start-Process -NoNewWindow`(`out_bench_03_apply.json`) | base p50 12.586 / p99 14.2 | **p50 0.57 / p90 1.01 / p99 2.004**;每 10 s p50 0.50–0.62 全程無退回 | p50 全程 < 1 且 ≤ 0.6;p99 ≤ 2 | **PASS**(p50);p99 2.004 差 4 µs,T4 同值 2.010 |
| 0-4 | `bench_04 --drift`(push + correlations ms p50) | 9.041 | **0.061**(push 0.035 + corr 0.027;corr p90 0.029;review 收修前 0.067) | ≤ 0.1;n_mismatch 0 | **PASS**;n_mismatch 0、16,200 push max\|Δr\| 3.0e-14 |
| 0-5 | `bench_05`(µs p50) | 207.0 | **148.2**(第二次 212 → 155;−28%) | ≤ 140 | **未達 8–15 µs**,見 §4 |
| 0-6 | `bench_06 --n 400`(µs/await p50) | positions 794.5 / orders 1345.7 / fills 675.5 | **98.7 / 193.3 / 97.4** | positions ≤ 100 | **PASS** |
| 0-7 | `bench_03 --mode apply --cpu-threads 4 [--switch 0.001]` 60 s(`out_bench_03_apply_4thr*.json`) | switch 0.005:p50 17.12 / p90 52 / p99 102;worker 561k/s | **switch 0.001:p50 4.40 / p90 13.4 / p99 25.1**;worker 519k/s(−7.6%) | p50 ≤ 4 | **差 0.4 ms**,見 §4;p99 4x |
| 0-8 | spy 測試 | 停用 slot 收到 set_basis | 停用 slot 零呼叫、upsert 後新 slot `_basis` 有值 | 機制 | PASS |
| 0-9 | `bench_09`(µs p50 無 latch) | 2.3 | **0.1** | ≤ 0.5 | **PASS** |
| 1-1 | `check_11`(starlette send_json 同款 dumps sha256) | snapshot `01f4bb75…` / delta `3a34b497…`;鍵 int | **sha 逐位元相同**;snapshot 鍵 str | 相同 | **PASS** |

對照組(誠實記):`out_bench_03_tbp_only.json` 單獨 `timeBeginPeriod(1)` 本晚 60 s **沒有**被收回(p50 0.55 全程),
與 T4 §2.1「約 3 秒後退回 12.6 ms」不同 —— EcoQoS 收回與否可能隨電源狀態 / 前景判定變;兩行版(apply)在兩種情況下都穩,
這正是「缺一不可」的理由,不是本晚 tbp-only 的運氣可以取代的。`out_bench_03_base_4thr.json`:不套 timer 時 4 執行緒 p50 46 ms,
與 diagnosis §2「0-7 的收益整條掛在 0-3 上」一致。

其他不該退化的量:worker 吞吐 −7.6%(拍板接受);pytest 全量 218 → 214 s;corr push 0.005 → 0.037 ms(增量把成本搬到 push,合計仍 135x)。

## 3. 真實環境(prod-like)

本批全部改動在 server 進程內;prod 跑著(git_sha 1e0720be,started 23:59:44)且 TC4 夜盤連著,**依 ops-discipline 不起第二台、不重啟**。
真環境判準留給 user 重啟後(spec #240「收尾與真環境判準」):
1. 啟動 log 有「timer 1 ms 已套用(EcoQoS 豁免 + timeBeginPeriod)」與「switchinterval 0.0010 s」各一行(0-3 / 0-7)。
2. 盤後 `python .claude/perf/batch-b-tier0/evidence/bench_04_prod_overlay.py 150`(只打 prod API,零新訂閱;OverlayCache 重啟即冷)150 檔 ≤ 3 s(0-1)。
3. 次一交易日盤後:`grep "佇列滿" logs/server-<日>.log` 為 0;相關係數分頁數字與前一日同量級;江波圖首則 snapshot 正常。
4. 群益送單審計檔 `capital-<日>.jsonl` 照常一筆兩行(0-5;目錄由 CapitalClient 建構時建)。

## 4. 未達標與偏離(誠實列,交 user 拍板)

- **0-5**:212 → 155 µs(−27%,mkdir 那份 57 µs 拿掉了;測試釘熱路徑零 mkdir)。spec 的 140 是 T1 環境的絕對值
  (211.5 → 139.5);本機 open/close 一趟的底約 150 µs。再往下要改設計(常駐 handle + 日切),不在「零風險小改」內。
- **0-7**:p50 4.40 ms vs 4.0(T4 的 3.54 是 `sleep(0.005)` 400 樣本尺,本尺 `sleep(0.05)` 60 s);p99 101 → 25 ms(4x)、
  p90 52 → 13。機制成立(17.1 → 4.4),差 0.4 ms 在量測尺差內。
- **0-3 p99** 2.004 vs 2.0(T4 2.010);p50 0.57 達標。
- **0-1 p90 61 ms**:倍增退避第二輪落點(20 + 40);spec 寫「22–44 ms」是 C1 以固定 20 ms 間隔掃描得到的,
  倍增版第二輪必然 60 ms。user 拍板「倍增與上限不動」,故 p50 達標、p90 如實記。真數字看重啟後 150 檔牆鐘。
- 既有測試兩處改動:`test_fallback_1k_also_uses_short_deadline` 的 `sum(slept) <= 20.0` 容 +1e-9(假鐘 0.02·2^k 序列浮點累加
  尾差 4e-15,預算未變);`test_audit_pre_write_failure_fails_whole_request` 前置改 `rmdir` 再以檔案佔住(ctor 現在先建目錄,意圖不變)。
- 1-1 的 25 條 int 鍵斷言依 spec 預告改 str(regex 批次,逐條 diff 過目)。

## 4.5 two-axis review round-1 收修後重跑(closeout §1 → §2 順序)

- 收修內容見 `code-review-round-1.json` disposition(Standards 9 條:H 2 收、J 5 收 / 1 部分收 / 1 不改;Spec 17 條:零 Must-fix,
  收修 4 條、文件化 2 條、反駁 1 條(now 單調:engine now_fn 與 push ts 同源 time.monotonic))。
- 重跑:`ruff check` All passed;`pyright` 0 errors;受影響套件(corr_state / signal_state / win_timer / main_wiring /
  corr_engine / corr_routes / trade_audit / models)**238 passed**;`bench_04 --drift` after **0.061 ms**(n_mismatch 0、3.0e-14);
  `check_11` 欄名改正後 snapshot 鍵 int → str、in-memory 鍵 int → int、sha 仍同。
- `ruff format --diff` 兩檔存量:test_signal_state 25 行 / test_corr_state 4 行 = master 既有未 format 的量(本批新寫的 hunks 已對齊,不順手重排存量)。

## 5. Artifact

- `diagnosis.md`(baseline + 定位)、本檔、`code-review-round-1.json`(two-axis)。
- `evidence/bench_0{1,2,4,5,6,7,9}_*.py`、`check_11_river_wire.py`、`bench_03_timer_drift.py`、`run_all_benches.py`、`summarize_benches.py`;
  輸出 `out_before_*.json` / `out_after_*.json` / `out_bench_03_*.json`(六場 60 s)。
- 主樹 `.claude/perf/batch-b-tier0/`(untracked,早期落在主樹的副本)merge 後要先比對再刪,否則 `git pull --ff-only` 拒絕(ops-discipline 四坑 (1))。
