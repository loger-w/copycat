# verification — fix/futures-daily-cache-night

worktree:`C:\side-project\copycat-wt-daily-cache-night`;venv = 主 tree `.venv`(pytest 吃
pyproject pythonpath,import 的是 worktree code —— ops-discipline worktree 節)。

## 紅迴圈(Phase 1/2)

- 指令:`.venv/Scripts/python -m pytest tests/server/test_bars.py -k morning_snapshot -q`
- 修前:`FAILED ... assert 100 == 200`(1 failed,0.31 s,確定性);修後綠。

## 自動化 gate(全部 exit 0)

| gate | 指令 | 結果 |
|---|---|---|
| pytest 全量 | `python -m pytest -q` | **3211 passed, 1 skipped**(204 s;review 收修後重跑見下) |
| ruff | `python -m ruff check copycat tests` | All checks passed! |
| pyright | `python -m pyright` | 0 errors, 0 warnings |
| 前端 vitest | `npm test` | **2914 passed**(day-bars-rollover.ts 註解校正連動) |
| 前端 tsc / eslint | `npx tsc -b` / `npx eslint src` | 皆無輸出 exit 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | exit 0,零新增 finding |
| replay four | `python -m copycat replay --watchlist watchlists/four_tigers.json` | 完成(n_events 11048) |
| replay five | `python -m copycat replay --watchlist watchlists/five_tigers.json` | 完成(n_events 11048) |
| golden gate | `python -m copycat validate` | **42/42 PASS** |

replay/validate 在 worktree 跑,data/ 以 junction 借主 tree、validate 後即拆
(`rmdir` 確認主 tree data/1k 完好)。replay 鏈 grep 證實不 import `copycat.server`,
gate 照跑純屬完工紀律。

## 反向驗證

`git stash push copycat/server/bars.py` → 同 4 條紅(morning_snapshot ×2 路徑、
stale 墊背 ×2)、2 條 guard 綠 → `git stash pop` → 6 條全綠(收修前母體;收修後
該 class 為 8 條全綠,見下節)。紅回來的正是修復所治的斷言,測試確實抓著 bug。

## 新測試(seam = tests/server/test_bars.py,handoff §2 議定)

`TestDailySnapshotFinality` 八條(pr-165-review #7 回校:原「六條」是 review 收修前
快照):紅先行六條 —— 症狀本體(build_period 早上快照過界必作廢)/ 界前 memo 不變
(guard)/ 界後寫入定稿不重付(guard)/ 過期 refetch 空手墊背舊快照 + 舊 tag + 15s
負向窗 + 過期恢復重試 / build_daily 同病同治 / 墊背 status 不洗白;加 review 收修兩條
—— S-1「作廢一次」discard 突變體 / S-2 build_daily 負向窗墊背(見下節)。
(fix/pr-165-review-followups 再加兩條:W 形狀墊背 + 界上 14:00 包含性 → 十條。)

## two-axis review round-1 收修

Standards 0 硬違規 + 7 judgement(收 J1/J2/J5/J7,反駁 J4/J6,J3 入 next-time);
Spec 收 S-1/S-2(各補一條測試:「作廢一次」的 discard 突變體現在會紅、build_daily
負向窗墊背)+ S-7 措辭,知情反駁 S-3(日曆)/ S-4(發起時刻)。收修後
`test_bars.py` **61 passed**;全量 pytest 收修後重跑 **3213 passed, 1 skipped**。

## 真實環境判準(prod 關著、TC4 不在 —— 留 user 重啟後下一個交易日核)

1. **主症狀**:交易日 22:00(或任何 15:01–24:00 時點)F5 期貨 tab →
   CDP 基準日 = 當日(core readout `date`),且 OHLC 與期交所 / FinMind 當日 D bar 一致
   (= handoff §2「先實錄一次」的同一把尺,改成修後驗證)。修前這裡是早上快照。
2. **定稿刷新**:14:00 後首個 `curl "localhost:8721/api/market/bars/TXF?tf=D"` 的末根
   = 當日完整 bar(c = 日盤收盤)。
3. **成本上界**:同日 14:00 後同 code 第二次請求不再觸發 DK 取數(access log 對照)。
4. **未改功能抽查**:期指 tf=1 分時照常;個股頁分時(build_minute 路徑)照常。
5. **開放問題(界值 14:00 的前提)**:TC4 DK 定稿寫入時點未實測 —— 若 14:00 首刷拿到的
   當日 bar 仍非定稿(與期交所收盤不符),界要往後調,記 next-time。
