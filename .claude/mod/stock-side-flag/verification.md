# mod/stock-side-flag — verification(2026-09-15)

spec:`change-spec.md`(同目錄);盤點:`current-state.md`。分支 `mod/stock-side-flag`(worktree),fixed point f57efcd2。
commit 鏈:test c415d1d4 → fix b1c3fd13 → feat fec43340 → chore(docs) d19b4b3d → review 收修 fix 9df04481 + chore bd4368ea。

## 1. 紅先行(tdd)

- 紅:`pytest -k "TestSideFromFlag or TestFlagStatsLog"` → **10 failed**(7 models + 3 engine;`StockTick` 無 `flag`、
  engine 無「個股旗標」行),commit c415d1d4。
- 綠:T1 後 `tests/live/test_stock_models.py` 35 passed;T2 後 `tests/server/test_stock_engine.py` 210 passed(88.9 s)。
- review S-01 補測 `FlagOfBuySell: 2`(int)→ 修前紅(`_FLAG_SIDE.get(2)` miss → inner、`flag == 2`),修後綠。

## 2. 反向驗證(突變)

| 突變 | 預期 | 實測 | 還原後(sleep 1 避 pycache 同秒) |
|---|---|---|---|
| `_FLAG_SIDE` 對映對調(1→outer / 2→inner) | 旗標 1 / 旗標 2 / golden 三條紅,退路四條綠 | **3 failed, 4 passed** | 7 passed |
| `close()` 的 `_log_flag_stats` 呼叫換成 `pass` | 三條(都斷 close 那行)全紅 | **3 failed** | 3 passed |

## 3. 自動化 gate(全在 worktree,用主樹 venv 絕對路徑;ops-discipline worktree 三險)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| pytest 全量(review 收修前) | `C:/side-project/copycat/.venv/Scripts/python -m pytest -q -p no:cacheprovider` | **3457 passed, 3 skipped**(216.8 s) | 0 |
| pytest 全量(review 收修後,最終) | 同上 | **3458 passed, 3 skipped**(212.4 s;+1 = S-01 補測) | 0 |
| ruff | `… -m ruff check copycat tests` | All checks passed! | 0 |
| ruff format(只查改到的兩支 .py) | `… -m ruff format --diff copycat/live/stock_models.py copycat/server/stock_engine.py` | 2 files already formatted(兩支測試檔 master 本來就未 format,只確認 diff 不碰新增段) | 0 |
| pyright | `… -m pyright` | 0 errors, 0 warnings, 0 informations | 0 |
| validate | `… -m copycat validate --run-five C:/side-project/copycat/out/five_tigers --run-four C:/side-project/copycat/out/four_tigers --out <scratchpad>/validate-out` | **42/42 PASS** | 0 |
| 前端 | 零改動(side 三值 wire 不變),依 spec §5 不跑 npm gate、dist 不用 build | — | — |

## 4. 白名單逐條(spec §4 + current-state §3;兩軸 sub-agent 各自讀 code 驗過,零破壞)

- `side` wire 三值字面不變;`ticks[].b/a` 照舊 —— `_flush_ticks` 打包 item 與 `snapshot()` 鍵集未加 `flag`(`stock_state.py` 全檔零 `flag` 字樣)。
- VP / 外盤比 / 能量副圖算式不變;`vp_parity.json` 未動。
- `relabel_locked_side` 走 `replace()` 保留新欄、五道閘不動;`apply_backfill` / survivors / seq / 試撮 零改動。
- `_eval_sweep` 首筆外盤判準與 `ask_milli` 語意不動(skill 改述:09-15 起與 `side` **不等價**,知情)。
- `StockTick.flag` 有 default 且附在最後,16 處 keyword 建構點相容;期貨 / corr 經 `parse_stock_realtime` 行為不變(不讀 side;缺旗標退回現況)。
- `REALTIME_MSG` 既有斷言未改(退路相容證據);`/api/health` 未加欄。

## 5. Two-axis review(`code-review-round-1.json`)

Standards 5 條(1 Should 4 Nice)/ Spec 2 條 Nice / 零 Must。接受 S-01(`str()` 正規化 + 紅先行補測)、S-03、S-04(部分)、S-05、Spec-S-02(註解);
反駁 S-02(熱路徑 4 行不包型別)、Spec-S-01 第三桶(判準格式是 spec 釘的契約,09-14 零未知值)。已知偏離 1312 → 6209 兩軸判可接受。

## 6. 真實環境判準(spec §5;prod 重啟由 user 決定時點,本案 dist 不變,只重啟 server)

重啟後第一個交易日:
1. 09:30 後 `curl -s 127.0.0.1:8721/api/stock/state/<自選熱門股>` → 自訂閱起(回補段之後)的 `ticks[].side` neutral 比例 ≈ 0;
   個股頁判定率說明列 ≥ 95%(修前 ~80%)。
2. 盤後 `grep "個股旗標 0" logs/server-<日>.log` **一行**(close 那行;若當日跨過換日再多一行帶前日),`0:` 桶接近 0、
   `欄缺` 桶 = 0(非 0 = 達錢格式漂了)。
3. `grep 佇列滿 logs/server-<日>.log` 仍 0;掃單簇 / 政策列 jsonl 筆數量級與 09-15 同時段相當(掃單不讀 side)。
4. 白名單目視:VP 兩色、外盤比、能量副圖有值;鎖停股(若當日有)回補段仍靠 relabel 上色;TickTape b/a 欄照舊。
5. 09-16 08:59 排程 `copycat-flag-capture-0916` 抓檔另案(只改文件,next-time 09-15 節)。

## 7. 證據路徑

- golden 三則來源:`%LOCALAPPDATA%\Temp\claude\C--side-project-copycat\38ca5162-…\scratchpad\flag-capture\raw_20260914_090423.jsonl`
  (抽取腳本 scratchpad `pick_golden.py` / `pick_golden2.py`);fixture `tests/fixtures/stock_side_flag_golden.json`。
- validate 產物:scratchpad `validate-out/`(gitignored 等價物,不進 repo)。
