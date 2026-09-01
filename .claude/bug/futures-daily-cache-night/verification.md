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

## 09-01 真環境結果(時段判準;主場景 FAIL 的根因見 memory futures-daily-cache-final-boundary-shipped)

- 00:23(prod 9f30c123)/ 10:08(fee0ad56):判準 3(memo 14–15 ms 不重付)、判準 4 PASS;
  TC4 DK 夜盤即時寫 D+1 partial bar 實錄。
- 15:02(server 08:57 起):**判準 2 主場景 FAIL** —— 14:00 後首刷 09-01 bar 凍在 ~10:08 值
  (h 46955 < 1K 實收 47209,v 逐字節同早上);非墊背非空手。15:16 重啟(f3326c4e)後首刷
  171 ms 直接定稿(c 47209/h 47220/v 82698)。根因 = TC4 DK 同 session 凍結快照,修法待
  /bug(DK refetch 帶窗口 variant + 「refetch 成功但值未前進」訊號)。
- **22:06 夜盤複核(15:16 台,排程 session)**:
  - API:09-01 bar 仍定稿(c 47209/h 47220/v 82698 逐字同 15:16);09-02 夜盤 partial bar
    不在序列(coverage_to 09-01)—— 定稿 memo 同日曆日不再打 DK 的設計行為 + 訂閱時點
    快照語意旁證。`meta.partial_last: True` 但 bar 已定稿 = pr-165-review #5 留尾的誤標常態實錄。
  - 畫面(新開分頁 = F5 等價,判準 1):期貨 tab 疊線基準印 **2026-09-01**;TXF CDP 線
    46857\*(= compute_cdp(47220,45788,47209) 46856.5 經 fmtIndexPts round)、TMF 46859\*
    (= TMF 自家 D bar 算的 46859.25)—— 兩合約各對各的 09-01 完整 D bar,**判準 1 PASS**
    (15:01–24:00 F5 路徑;「同 session 不重啟跨 14:00」的 FAIL 路徑不受此影響,另案)。
  - 順帶:SC-13(e)(futures-day-1500)個股頁台指期疊線夜盤時段仍在 —— 2455 單檔開
    台指期 toggle,橙線 + 「台指期 -0.28%」標籤正常,PASS。
