# Verification — feat/surge-pullback-signal(spec #174)

日期:2026-09-02 深夜(盤後)。全部在 worktree 跑(主樹 venv;pytest pythonpath 取 worktree code)。

## 自動化(全綠)

| Gate | 結果 |
|---|---|
| `pytest -q`(扣 backtest 背景跑) | **3087 passed, 2 skipped**(exit 0) |
| `pytest tests\backtest -q` | 246 passed, 1 skipped |
| 其中 seam 測試 | `tests/live/test_signal_state.py` 70 passed(新 TestSurgePullback 13 條);`tests/test_signal_rules.py` 144 passed(新 TestMigrationV2ToV3 7 條) |
| `ruff check copycat tests` | All checks passed |
| `pyright` | 0 errors |
| `copycat validate`(four/five replay 先跑,`--data-dir` 指主樹) | **42/42 PASS** |
| `npm test -- --run` | **2925 passed(153 files)** |
| `npx tsc -b` | 乾淨 |
| `npx eslint src` | exit 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | No issues found |

紅先行證據:commit a06a8ada 當下 `pytest tests/live/test_signal_state.py::TestSurgePullback tests/test_signal_rules.py` = **30 failed, 114 passed**(狀態機/遷移/契約全紅),實作 commit c7b9ff9d 後轉綠。

Rebase 到 origin/master 6ef6b913(#176 併入)後複跑:`pytest -q` **3344 passed, 3 skipped**、
ruff / pyright 0、前端 `npm test -- --run` 2925 passed + tsc / eslint 乾淨(exit 0)。

## 真資料驗證(盤後可做的部分)

1. **prod 規則檔遷移 dry-run**(唯讀複本 `%TEMP%\claude-sr-copy.json`):prod `data/signal_rules.json`
   實際是 **v1**(4 條)→ 遷移鏈 v1→v2(補 rearm_dwell_secs)→ v2→v3(append 兩張種子卡)
   → 6 條全部載入成功,log 三行 INFO 可對帳。原檔未被觸碰(load 不回寫)。
2. **鼎元 2426 離線對照**(issue #174 判準;真 1K 自 prod `GET /api/stock/bars/2426?tf=1&days=2`,
   270 根 2026-09-01):每根 bar 展成 o→l/h→c 四筆合成 tick 餵 `SignalDetector`
   (腳本 scratchpad `replay_2426.py`):
   - 10:09 bar(達錢 APP 標 10:08 起點)h=104500、v=3251 = issue 說的上引線 K,峰 104.5 ✓
   - 該波兩張卡**各發恰一則**:10:09:45 於 102.0(自峰回檔 2.39%)。bar 粒度下 10:10 bar
     直落穿過兩個門檻,首筆合成 tick 即觸發 —— 精確觸價(1% 於 103.4、2% 於 102.4)
     是 tick 粒度的事,由 `test_dingyuan_2426_offline_reference` 以逐 tick 序列釘住 ✓
   - 1% 卡當日共 4 則、2% 卡 4 則(早盤 09:03/09:07 與 10:00 前後各有真實 ≥ 門檻的回檔,
     每波一則)—— 頻率量級合理,無連發。S-1 修正(發訊後窗 surge 重武裝)只讓 2% 卡多出
     10:04:30 一則(峰 103.0 未過前高 103.5 的獨立新波、真實回檔 2.91% —— 正是要接回的案型),
     1% 卡序列不變。
   - 證據檔:`evidence/replay_2426.py`(腳本)、`evidence/rules-dialog-new-pullback*.jpg/png`
     (worktree vite dev 5174 + prod 唯讀 proxy 的「新增規則 → 爆拉回檔」表單截圖:
     種類下拉五類、武裝漲幅 2 / 時間窗 300 / 回檔 1 預設值)。

## 待真環境(user 盤中)

- prod 重啟(現跑 f3326c4e+dirty)後:啟動 log 應見兩行「訊號規則檔 v2→v3:append 種子卡」
  (prod 檔是 v1,另有一行 v1→v2);規則管理 Dialog 應見「爆拉回檔 1%」「爆拉回檔 2%」兩卡。
- 盤中對榜上股觀察回檔訊號實發(rail 文案「爆拉回檔 x.xx%」、Discord 同字面)。
- 注意:載入期遷移**不回寫檔案**,第一次在 UI 動任何規則才落 v3 —— 回退窗內退回舊版 code
  直接可讀原檔。
