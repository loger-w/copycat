# verification — fix/index-chart-empty-minutes(2026-08-13)

## 收尾 review 後最終 gate(全綠;code-review-round-1.json:P0=0、P1=1 已修、P2 5 修 1 known-risk)

pytest 2622 passed / ruff clean / pyright 0 errors / validate 42/42 /
npm test 110 files 1741 passed / tsc clean / eslint clean / react-doctor no issues。
review 修復各自紅先行:T-1 `ab1c4469`→`945db63b`、T-6 `05685327`→`54cbd5ed`;
lock 測試(節流 / 完整即停)mutation-verified。

## 自動化 gate(review 前首輪,全綠)

| step | command | 結果 | exit |
|---|---|---|---|
| 後端測試 | `.venv\Scripts\python -m pytest -q` | 2617 passed, 1 warning(130s) | 0 |
| Lint | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed | 0 |
| 型別 | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| Replay four | `python -m copycat replay --watchlist watchlists/four_tigers.json` | 完成 → out\four_tigers | 0 |
| Replay five | `python -m copycat replay --watchlist watchlists/five_tigers.json` | 完成 → out\five_tigers | 0 |
| Golden gate | `python -m copycat validate` | 42/42 PASS | 0 |
| 前端測試 | `npm test`(frontend/) | 110 files / 1740 passed | 0 |
| 前端型別 | `npx tsc -b` | 無輸出 | 0 |
| 前端 lint | `npx eslint src` | 無輸出 | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | No issues found | 0 |

## TDD 紅綠證據

- 引擎自癒:red `0620a8be`(`assert {} == {'0901':1000,...}` 紅在 minutes 空)→ green `8fb40e56`
- 廣播送達:red `b4a51266`(2s 內廣播從未帶 minutes)→ green `c2f88576`
- 前端 refetch 重試:red `c887d6f6`(waitFor timeout = 永久缺線)→ green `38f8312d`
- FE 契約 lock `095c482e`:mutation-verified(toSeries 改 prev-first → 紅;還原 → 綠)
- flake 修:watchdog 測試與 heal 隔離 `dce097b1`(改前 6/10 紅 → 改後 10/10 綠)

## 反向驗證(/bug 專屬 gate)

實作檔 `git restore --source master`(測試留現版)→
- 後端:4 failed(lag self-heal / broadcast delivery / grace-at-open / does-not-clear-stale),紅在正確斷言
- 前端:1 failed(refetch 重試 timeout),lock 測試仍綠(toSeries master 版即正確)
還原 HEAD → 後端 26/26 綠、前端 6/6 綠。

## 真實環境

- **事故現場對照(修復前)**:prod 14:44 `/api/index/state` → twse minutes_n=0、p/ref/high/low
  有今日值;`/api/market/bars/TWSE?tf=1&days=1` 當場取回 270 根完整 1K(證明自癒路徑
  的資料源可用)。存證 repro.md。
- **驗證窗口**:修復生效需 prod 重啟(User 慣例盤後/明早自然重啟)。明日盤中檢核點:
  (a) 若早晨啟動再踩 1K timeout(log `history TC.S.TWS.IX0001(1K): ... 回空`),09:06 前後
  應出現 `index 分時自癒` log 且 `/api/index/state` twse minutes 回填;
  (b) 開著的台股綜合頁不重整,分時線應在一則廣播內自己回來。
- **窗口外降級**:引擎級測試以 2026-08-13 事故序列(回補空 + 推播零有效鍵)重演全鏈,
  broadcast 送達 + 前端 merge 契約各自有測試鎖住。

## Blast radius

- `_schedule_retry` 全部 caller 在 index_engine 內部(start/reconnect/rollover×2/heal + 測試),
  kwarg 預設值向後相容;futures/corr/stock 的 retry 為獨立實作未動。
- `FakeIndexSource.fetch_minutes_calls` 為純新增欄位,index/market routes 測試共用者不受影響
  (全量 pytest 2617 綠佐證)。
- 前端:`useIndexStream` 回傳 shape 未變;`!res.ok` 從靜默 return 改為重試(boot 期 503
  NOT_READY 會退避重試至成功 —— 初載空窗一併治,行為改動已在 commit 訊息載明)。
- 未改動功能抽樣:watchdog 窗界測試、rollover 兩段式測試、OTC 合成 bar 測試全綠(全量內含)。
