# 盤前篩選跨 attempt EOD memo + 處置股 fail-fast(`mod/screen-eod-attempt-memo`)— verification

分支自 master `77ef64a6` 切出(worktree)。spec = user 2026-09-08(另 session 帶入)原話 + next-time 原條
「screen_engine 跨 attempt memo」:重試不重抓 21 個 EOD 大檔,沿用上一輪 attempt 已抓到的;修法抄 breadth
`_streak_memo`(存 shrink 後列、目標日換日清空)+ disposition 提到資格查前;做完 next-time 原條與停放索引那行一併勾掉。
既有行為白名單:三道當沖名單閘、EOD 五道守門(日曆剔除 / 列數下限 / 回聲 / 最新日必須有資料 / 湊不滿 21 日)、
重試時間盒與放棄、快取 v2、群組寫入 —— 全部不變,只加 memo 與換順序。

註:user 原話「A-3 改成每小時重試後 … 一晚十幾次」是舊口徑 —— 現行(W2 T5 #209)是 08:00–09:00 每 10 分鐘的時間盒
(理論 6 次、實際 4–6 次),成本量級是「一早上最壞 6 × 21 = 126 個 MB 級大檔」;結論相同(要做),數字以本檔為準。

## 1. commits(三類分開)

| sha | 類 | 內容 |
|---|---|---|
| `5a4e81b4` | test(server) | 紅先行:重試只補抓上一輪失敗起未拿到的日子(21 + 1 次)/ 目標日換日重抓 / 處置股取數失敗在任何 EOD 前擋下 |
| `e47b561b` | 🔴 perf(server) | 第一版:instance 欄位 `_eod_memo` + 處置股取數搬到 EOD 前 |
| `40c0d00e` | test(server) | 換日案改「週二整早失敗放棄 → 週三重抓」(原對照組殺不掉突變體 B);同時釘六次失敗 attempt 之間 08-31 只抓一次 |
| `45f2f196` | chore(docs) | next-time 原條結案 + 09-08 盤點節停放索引該行拿掉 |
| `40d4c816` | 🔴 perf(server) | round-1 收修:memo 改 `_run_attempts` 區域變數往下傳(零 instance 狀態;成功 / 放棄 / 換日對稱)、空回應不進 memo(與 breadth 刻意不同)、算術 23 → 2 / 126 |
| `62952ae5` | test(server) | round-1:`_counting_daily` 合成 module 級一份、處置股案併入 `TestDayTradeFailFast`、檔頭列全 |
| `a60d2b04` | chore(docs) | round-1:next-time 09-08 盤點節計數 21(原 22)+ Q9 指標結案 |

## 2. 紅 → 綠 / 反向驗證 / 突變體

- 紅先行:`5a4e81b4` 當下 `-k TestEodAttemptMemo` → **2 failed, 1 passed**(memo 重用 / 處置股 fail-fast 紅;換日對照組本就綠)。
- 反向驗證:`git revert --no-commit e47b561b` → 同組 **2 failed, 1 passed** → `git revert --abort` → 綠。
- 突變體(scratchpad `mutcheck2.py` / round-1 後 `mutcheck3.py`,套用 → 跑整檔 → 還原;還原後 29 passed):

| 突變體 | 第一版 | 測試補強後 | round-1 重寫後(`mutcheck3.py`) |
|---|---|---|---|
| A memo 永不寫入 | KILLED(1) | KILLED(2) | KILLED(2:重用案 + 換日案) |
| B 換日不清 memo / memo 每 attempt 新建 | **SURVIVED**(對照組被「成功後也清」蓋住) | KILLED(換日案改放棄後換日) | KILLED(改為「每 attempt 傳空 dict」,2) |
| C 處置股搬回 EOD 之後 | KILLED(1) | KILLED(1) | KILLED(1,案已併入 `TestDayTradeFailFast`) |

## 3. 完成前 gate(round-1 收修後,worktree `a60d2b04`)

| 指令 | 結果 | exit |
|---|---|---|
| `C:/side-project/copycat/.venv/Scripts/python -m pytest -q`(worktree 全量) | 3558 passed, 3 skipped, 2 warnings(213.30 s) | 0 |
| `… -m ruff check copycat tests` | All checks passed | 0 |
| `… -m pyright` | 0 errors, 0 warnings, 0 informations | 0 |
| `… -m copycat validate --run-five <主樹 out/five_tigers> --run-four <主樹 out/four_tigers>` | 42/42 PASS(`45f2f196` 時跑;round-1 只動 screen_engine / 測試 / docs,replay 路徑零改動) | 0 |
| 前端 | 未動 `frontend/`,不跑 | — |

ruff format:自己新增的 hunk 全部手修;`screen_engine.py` 兩個 would-reformat 為既有舊 hunk(位移),不整檔重排。
第一版全量 pytest(`45f2f196`)= 3558 passed, 3 skipped(218.71 s)。

## 4. two-axis round-1(`code-review-round-1.json`)

標準軸 9 條全修(四條以「memo 改區域變數」一次解、負快取刪除、算術、註記、測試整理);spec 軸 7 條:修 5、note 1 註記、
1 條隨負快取刪除消失。零否決。Spec 軸逐條對帳 (1)–(6) 全 done;Standards 軸對 brief 四個指定問題皆通過。

## 5. 真實環境

runtime 行為改動兩處,都只在盤前篩選的取數路徑:(1) 同一目標交易日內重試不重抓已拿到的 EOD —— 下一交易日 08:00 若某次
attempt 在 EOD 中途失敗,下一次 attempt 的 log 之間看不到差別(成功那行相同),可觀測面 = FinMind 配額 / attempt 時長
(第二次 attempt 明顯短於第一次);(2) 處置股取數失敗(罕見)的 WARNING 會在 EOD 之前出現,attempt 幾乎零耗時。
成功路徑輸出(硬條件 / 資格後 / 當沖名單 / 群組更新)與 W2 §6、pr-211 收修判準逐字不變。
prod 未重啟(仍 #211 之前版本);本批零前端改動,dist 不必重 build(已於 #212 後 build)。
