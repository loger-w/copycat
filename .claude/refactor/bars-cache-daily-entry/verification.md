# verification — refactor/bars-cache-daily-entry(W3 B1)

分支 commits(merge-base master `45df8dbd`):
- `4afce9b6` test(backend):四條 characterization(🟢)
- `b778214f` refactor(backend):`_daily` / `_daily_tag` / `_daily_pre_final` → `dict[(code, today), DailyEntry]`(🔵)
- `3af3c822` refactor(backend):two-axis 收修(更名 `_DailyEntry` / docstring / 測試搬 class)(🔵)
- artifacts + docs:另起 `chore(refactor-bars-cache-daily-entry)`(本檔落檔後)

worktree 環境:`C:/side-project/copycat/.venv/Scripts/python`(主樹 venv,pyproject `pythonpath=["."]` 讓 worktree 的
`copycat` 蓋過 .pth);`validate` 指向主樹 `out/{five,four}_tigers` replay 產物。

## 1. 自動化 gate(全在收修 commit `3af3c822` 之後跑)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| pytest 全量 | `python -m pytest -q -p no:cacheprovider`(先清 `__pycache__`) | **3562 passed, 3 skipped, 2 warnings** in 234 s | 0 |
| ruff | `python -m ruff check copycat tests` | All checks passed! | 0 |
| pyright | `python -m pyright` | 0 errors, 0 warnings, 0 informations | 0 |
| validate | `python -m copycat validate --run-five <主樹>/out/five_tigers --run-four <主樹>/out/four_tigers` | 42/42 PASS | 0 |
| ruff format(bars.py) | `ruff format --check copycat/server/bars.py` | 1 file already formatted(master 版反而「would reformat」,被移除的正是那段 comprehension) | 0 |

基準(handoff,master `de192ca3`):3531 passed / 3 skipped;現 master `45df8dbd` 含後續 PR 增量,本案 +4 條 = 3562。
2 warnings = `PytestUnhandledThreadExceptionWarning`(執行緒例外型,既有留尾 `_listen_loop` 測後洩漏一族);bars.py 純同步零執行緒,
與本案無關。frontend 未動,前端 gate 不適用。

## 2. 重構完成判準(handoff B1 明列)

- `test_prune_drops_stale_daily_tag` / `test_prune_drops_stale_pre_final_marker` + `TestDailySnapshotFinality` 全套
  (含 `test_period_pre_final_tracks_the_long_window_marker`)**不改仍綠**:`pytest tests/server/test_bars.py -q` → 82 passed
  (78 基準 + 4 新 characterization)。
- 公開方法簽名零改動;全 repo 零處直戳三份 dict(grep `_daily_tag|_daily_pre_final` 在 `copycat/` / `tests/` 零命中,只剩歷史 artifact 與 review 報告)。

## 3. 突變體驗證(evidence/mutants.txt;每輪還原 + 清 `bars.*` pyc,避同秒 pycache 陷阱)

| 突變 | 結果 | 擋下的測試 |
|---|---|---|
| M1 `daily_put` 整格替換(丟 tag) | 紅 | `TestDailyEntryFields::test_daily_tag_survives_daily_put_overwrite` |
| M2 `daily_tag_put` 整格替換(丟 bars / 標記) | 紅 | `TestDailyEntryFields::test_daily_tag_put_leaves_bars_and_marker_untouched` |
| M3 `daily_put` 拿掉空手早退 | 紅 | `TestDailyCache::test_daily_empty_not_cached`(`-x` 首紅;新 `test_daily_put_empty_is_noop_for_all_three` 同紅) |
| M4(參考)`daily_get` 拿掉 `entry.bars is None` guard | 綠(82 passed) | 無 —— 與 review Spec-03 預測一致:現行寫入路徑下該 guard 冗餘(只有 tag 的格 bars 本就是 None、標記必也 None),保留當意圖註記,不視為缺口 |

## 4. 真實環境(closeout §2.2:改動範圍行為跟 refactor 前完全一樣)

盤中(10:34,prod 8721 跑 master `45df8dbd` 08:12 起)—— 依 ops-discipline **不起第二台連 TC4 的後端**,改走零 ZMQ 側車:
`evidence/sidecar_bars.py`(`neutralize_external_env()` 在 `create_app` 前;`FakeTxoSource` + `FakeStockSource`(日 K 五根含今日)+
`FakeIndexSource(daily_bars=五根)` + fake futures / corr;自選檔落 tempdir 隔離;`sys.path` 錨定該 repo root 並 assert `bars.py` 載入路徑)。
兩台:主樹 master → 8731(`/api/health` git_sha `45df8dbd`)、worktree → 8732(git_sha `3af3c822`)。

`evidence/compare_bars.py` 同請求 diff(`evidence/sidecar-compare-master-vs-worktree.txt`):

| 請求 | 用途 | 結果 |
|---|---|---|
| `/api/stock/bars/2330?tf=D` ×2 | happy + memo hit(`build_daily`) | SAME 200/200,bars=5 |
| `/api/stock/bars/IX0001?tf=D` | 個股 session 的指數日 K(同 `build_daily` 另一鍵) | SAME |
| `/api/market/bars/TWSE?tf=D` ×2 | `build_period` happy + memo hit(tag 由 cache 還原 → meta.source `tc4_dk`、`partial_last` true) | SAME |
| `/api/market/bars/TWSE?tf=W` / `?tf=M` | edge:長窗聚合走同一格 | SAME(W bars=2 / M bars=1) |
| `/api/stock/bars/9999?tf=D` | edge:鍵隔離 | SAME |
| `/api/stock/bars/2330?tf=1&days=2` | 未改功能抽查 1(分 K 兩段式) | SAME(419 B) |
| `/api/calendar` | 未改功能抽查 2 | SAME(183 B) |

RESULT: ALL SAME。側車跑完即關(8731 / 8732 兩 pid 已 Stop-Process),prod 8721 全程未動。
定稿界後的路徑(14:00 後 `daily_get` 作廢、空手墊背)側車跑在 10:3x 走不到,由 `TestDailySnapshotFinality` 全套(單元)覆蓋,
且與 refactor 前同一批測試不改仍綠。

## 5. 回頭核動機(closeout §3)

- 動機 = 三份同鍵 dict 三處同步、漂掉零訊號 → 現在 `prune` 一段、`daily_put` 一格就地改欄;寫入半邊仍是單點約定(design.md Spec-01 回校),
  但不再有跨 dict 的「同鍵同刪」約定要維護。可量化:`prune` 日 K 段 7 行 → 2 行;`BarsCache.__init__` 日 K 相關宣告 3 → 1。
- next-time `三份同鍵平行結構` 條目已勾(docs/next-time.md 142 行附出貨註)。
