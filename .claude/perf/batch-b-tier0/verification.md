# verification — perf/batch-b-tier0(spec #240;tickets #241–#250)

2026-09-15 00:15–02:30。worktree `.claude/worktrees/perf-batch-b-tier0`,分支 `perf/batch-b-tier0`,
fixed point `1e0720be`(origin/master)。python 一律主樹 venv 絕對路徑(worktree 無 .venv)。

## 1. 自動化 gate(全部 exit 0)

| gate | 指令 | 結果 |
|---|---|---|
| pytest 全量(最終,review 收修後) | `C:/side-project/copycat/.venv/Scripts/python -m pytest -q`(worktree,TCPY 已複製) | **3421 passed, 1 skipped**,210 s,exit 0(baseline master 3394;+27 = 本批新測試;首輪 3419 / 3 skipped 見下列) |
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
| 0-1 | `bench_01 --n 60 --timer-1ms`(ms p50;假 TC4,備妥分佈是**假設**:`exp` 對齊 C1 掃描、`uniform` 悲觀) | tc4 150.5 / river 150.4(兩分佈同) | exp **20.6 / 20.6**(mean 30.5 / 35.8);uniform **60.7 / 60.6**(mean 50 / 53;`out_after_01_uniform.json`) | 相對量:150 → **20–61 ms**(user 2026-09-15 拍板改口徑;原「≤ 45」只在 exp 假設下成立,pr-251 review F-01) | **PASS(相對量)**;絕對值等重啟後真 TC4 |
| 0-1 prod | **重啟後立刻、前端先別開** `bench_04_prod_overlay.py 150`(第 3 段 p50 須明顯高於第 2 段熱取基線,否則無效;F-02) | ≈5.8 s(C1 外推) | 待 user 重啟 | ≤ 3 s | 待驗 |
| 0-2 | `bench_02`(µs/tick p50 @ 窗 301 / 3001 / 9901;**只開 vol_burst** 隔離該 kind,不是 prod 每 tick 的 evaluate 總成本) | 12.9 / 89.7 / 286.3 | **4.3 / 4.3 / 4.3** | 三窗 ≤ 5、窗長無關 | **PASS** |
| 0-3 | `bench_03 --mode apply` 60 s,run.ps1 同款 `Start-Process -NoNewWindow`(`out_bench_03_apply.json`) | base p50 12.586 / p99 14.2 | **全程 p50 0.57 / p90 1.01 / p99 2.004**;每 10 s 桶 p50 0.50–0.62 全程無退回 | **全程** p50 ≤ 0.6 且**每 10 s 桶** p50 < 1 ms(桶不再與 0.6 比,pr-251 review F-21);p99 ≤ 2 | **PASS**(p50);p99 2.004 差 4 µs,T4 同值 2.010 |
| 0-4 | `bench_04 --drift`(push + correlations ms p50) | 9.041 | **0.061**(push 0.035 + corr 0.027;corr p90 0.029;review 收修前 0.067) | ≤ 0.1;n_mismatch 0 | **PASS**;n_mismatch 0、16,200 push max\|Δr\| 3.0e-14 |
| 0-5 | `bench_05`(µs p50) | 207.0 | **148.2**(−28%;首輪未存檔那次 212 → 155) | ≤ 140 | **未達 8 µs**,見 §4(user 拍板接受) |
| 0-6 | `bench_06 --n 400`(µs/await p50) | positions 794.5 / orders 1345.7 / fills 675.5 | **98.7 / 193.3 / 97.4** | positions ≤ 100 | **PASS** |
| 0-7 | `bench_03 --mode apply --cpu-threads 4 [--switch 0.001]` 60 s(`out_bench_03_apply_4thr*.json`) | switch 0.005:p50 17.12 / p90 52 / p99 102;worker 561k/s | **switch 0.001:p50 4.40 / p90 13.4 / p99 25.1**;worker 519k/s(−7.6%) | p50 ≤ 4 | **差 0.4 ms**,見 §4;p99 4x |
| 0-8 | spy 測試 | 停用 slot 收到 set_basis | 停用 slot 零呼叫、upsert 後新 slot `_basis` 有值 | 機制 | PASS |
| 0-9 | `bench_09`(µs p50 無 latch) | 2.3 | **0.1** | ≤ 0.5 | **PASS** |
| 1-1 | `check_11`(starlette send_json 同款 dumps sha256) | snapshot `01f4bb75…` / delta `3a34b497…`;鍵 int | **sha 逐位元相同**;snapshot 鍵 str | 相同 | **PASS** |

對照組(誠實記):`out_bench_03_tbp_only.json` 單獨 `timeBeginPeriod(1)` 本晚 60 s **沒有**被收回(p50 0.55 全程),
與 T4 §2.1「約 3 秒後退回 12.6 ms」不同 —— EcoQoS 收回與否可能隨電源狀態 / 前景判定變;兩行版(apply)在兩種情況下都穩,
這正是「缺一不可」的理由,不是本晚 tbp-only 的運氣可以取代的。`out_bench_03_base_4thr.json`:不套 timer 時 4 執行緒 p50 46 ms,
與 diagnosis §2「0-7 的收益整條掛在 0-3 上」一致。

其他不該退化的量:worker 吞吐 −7.6%(拍板接受);pytest 全量 218 s(master)→ 210 s(最終);corr push 0.0084 → 0.0345 ms
(增量把成本搬到 push,合計仍 148x;數字一律引 `out_before/after_04.json` 那一輪,pr-251 review F-22)。

## 3. 真實環境(prod-like)

本批全部改動在 server 進程內;prod 跑著(git_sha 1e0720be,started 23:59:44)且 TC4 夜盤連著,**依 ops-discipline 不起第二台、不重啟**。
真環境判準留給 user 重啟後(spec #240「收尾與真環境判準」):
1. 啟動 log 有「timer 1 ms 已套用(EcoQoS 豁免 + timeBeginPeriod)」與「switchinterval 0.0010 s」各一行(0-3 / 0-7)。
2. **重啟後立刻、前端先別開**(pr-251 review F-02,user 拍板):`python .claude/perf/batch-b-tier0/evidence/bench_04_prod_overlay.py 150`
   (只打 prod API,零新訂閱)。`OverlayCache` 是 per-(code, today) in-memory **無 TTL**,前端一開、進過群組,自選那批就全 hit ——
   盤後再跑量到的是熱路徑(腳本第 2 段基線 sub-ms),150 檔必然 ≪ 3 s、假 PASS。判讀(review 建議的額外守門,不在 user 選的 A 內):第 3 段每檔 p50 應**明顯高於**第 2 段
   熱取基線(冷取有 TC4 往返),否則本次量測可能又量到熱路徑、重來;150 檔牆鐘 ≤ 3 s(0-1)。順序 = 重啟 → 不開前端 → 跑腳本 → 再開前端。
3. 次一交易日盤後:`grep "佇列滿" logs/server-<日>.log` 為 0;相關係數分頁數字與前一日同量級;江波圖首則 snapshot 正常。
4. 群益送單審計檔 `capital-<日>.jsonl` 照常一筆兩行(0-5;目錄由 CapitalClient 建構時建)。

## 3.5 真環境結果(2026-09-15 12:32 重啟,server e05a964f;前端未開即跑,盤中,腳本只打 prod API)

| 判準 | 結果 | 判 |
|---|---|---|
| 啟動 log 兩行 | `logs/server-20260915-1232.log:1-2`:「timer 1 ms 已套用(EcoQoS 豁免 + timeBeginPeriod)」/「switchinterval 0.0010 s」(印讀回值) | **PASS**(0-3 / 0-7) |
| 0-1 冷取單發(§1,10 檔) | p50 **29.8 ms**(24–46 ms 八檔;3450 / 8064 落在第二 / 三輪 157–167 ms)vs C1 before 153 ms | **PASS**:相對量 150 → 30(5.1x),落在 harness 預測的 20–61 內 |
| 冷 / 熱可分辨(F-02 額外守門) | §2 熱取 p50 0.898 ms ≪ §1 29.8 ms | **有效**(量到的是冷路徑) |
| 0-1 進群組(§3,並發 68 檔,Semaphore(4)) | 牆鐘 **0.99 s**、68.4 檔/s → 外推 150 檔 **≈ 2.2 s**(C1 before 外推 5.8 s、25.7 檔/s) | **PASS**(≤ 3 s;自選 78 檔扣 §1 暖過 10 檔,150 為外推) |
| 灌入中互動 K 線延遲(§4) | 49 ms(C1 before 181 ms) | 順帶改善 |

待次一交易日盤後:`grep "佇列滿" logs/server-20260915-1232.log` 為 0;相關係數 / 江波圖分頁照常。

## 4. 未達標與偏離(誠實列,交 user 拍板)

- **0-5**:207 → 148 µs(−28%,committed `out_*_05.json`;首輪未存檔那次是 212 → 155;mkdir 那份 ~57 µs 拿掉了;
  測試釘熱路徑零 mkdir;user 2026-09-15 拍板接受)。spec 的 140 是 T1 環境的絕對值
  (211.5 → 139.5);本機 open/close 一趟的底約 150 µs。再往下要改設計(常駐 handle + 日切),不在「零風險小改」內。
- **0-7**:p50 4.40 ms vs 4.0(T4 的 3.54 是 `sleep(0.005)` 400 樣本尺,本尺 `sleep(0.05)` 60 s;同尺重跑 `out_bench_07_timer1ms.json`
  3.51 / 3.68 ms 達標);p99 101 → 25 ms(4x)、p90 52 → 13。機制成立(17.1 → 4.4);user 2026-09-15 拍板接受。
- **0-3 p99** 2.004 vs 2.0(T4 2.010);p50 0.57 達標。
- **0-1 的「達標」由假設分佈決定**(pr-251 review F-01,user 拍板改口徑):`exp` 備妥 p50 ≈ 19.6 ms 恰落在新起點 20 ms
  左邊 0.4 ms;`uniform` 悲觀分佈 p50 60.7 ms(首輪落空 → 第二輪 20 + 40)。「150 → 20–61 大幅改善」在任何分佈下成立,
  「≤ 45」不是量到的性質。spec 寫「22–44 ms」是 C1 以固定 20 ms 間隔掃描得到的,倍增版第二輪必然 60 ms;
  user 拍板「倍增與上限不動」。真數字看重啟後 §3 第 2 條(冷取)。
- 既有測試兩處改動:`test_fallback_1k_also_uses_short_deadline` 的 `sum(slept) <= 20.0` 先容 +1e-9,pr-251 review F-16 起改等式
  `abs(sum − 20) < 1e-9`(假鐘 0.02·2^k 序列浮點累加尾差 4e-15,預算未變;等式擋得住預算縮短);`test_audit_pre_write_failure_fails_whole_request` 前置改 `rmdir` 再以檔案佔住(ctor 現在先建目錄,意圖不變)。
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
