# verification.md — fix/react-dev-measure-leak

## 自動化 gate(frontend/,2026-08-19 19:4x)

| step | command | exit |
|---|---|---|
| vitest | `npx vitest run` | 0(130 files / 2278 tests passed) |
| tsc | `npx tsc -b` | 0 |
| eslint | `npx eslint src` | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | 0(No issues found) |
| build | `npm run build` | 0;`grep -l clearMeasures dist/assets/*.js` = 0 檔;`Changed Props` = 0 檔(prod 無 guard、無 React track) |

## 真實環境(MCP 分頁,隱藏態,夜盤)

- SC-1/真環境:重載後 30 秒每 5 秒取樣 `getEntriesByType('measure').length` = 4794 / 2702 / 812 / 4017 / 2359 / 597
  → 在 5,000 閾值下震盪,不再單調上升(修前:21,746 @1min → 75,179 @~2min,632/s)。
- Phase 6 real-env finding(已修):第一版 setInterval(10 s) 在隱藏分頁被節流 —— 20 s 實測 interval 7 次 vs
  PerformanceObserver 256 次回呼 / 13,195 筆 → 改 observer 閾值版(commit 49c71196)。
- SC-3 renderer 記憶體:同款 in-page clearMeasures 在 PID 16404 上 19:17 裝、19:26 起 ~250 MB 走平 20+ 分鐘
  (修前 +70 MB/分);observer 版的 30 分鐘 OS 層曲線由 scratchpad `renderer-mem.csv` 續錄(見觀察紀錄)。

## 反向驗證

- mutation:`installUserTimingGuard` 開頭插 `if (maxEntries > 0) return () => {};` → `SC-1` 紅(expected 42 < 10),
  前提自檢 / SC-2 綠 → 還原(Edit 成對,無 MUTANT 殘留,git status 乾淨)→ 3/3 綠。
- `git revert --no-commit` 路徑因 test 檔衝突(2b07fa8b 含 test-infra-fix)不採。

## Code review round-1(2 lens opus:correctness / test-coverage)→ 14 findings(P1×2、P2×12)全 accepted 修畢

- 修後 gate 重跑:vitest 130 files / 2283 tests、tsc、eslint、react-doctor 全 0。
- mutation:閾值條件改恆真 → 「SC-1 邊界」紅;還原 → 8/8 綠(lock 測試 mutation-verified)。
- 真環境(review 修後,HMR 重載,隱藏分頁):measure 每 5 s 取樣 4933 / 3902 / 3895 / 3428 / 2077 / 805 → ≤ 5,000。
- SC-3 OS 層:renderer 16404(MCP 分頁)19:50 重載吃修後版 → 19:52–19:55 私有記憶體 129–175 MB 走平;
  25280(另一分頁,19:42 起修後版)761 → 480 MB 走平、CPU ≈ 0。修前同 process 每分鐘 +70 MB。
