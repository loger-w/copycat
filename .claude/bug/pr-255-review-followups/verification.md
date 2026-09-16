# fix/pr-255-review-followups — verification(2026-09-15)

來源:`docs/superpowers/specs/pr-255-review.md`(CC 單軸 post-merge review,5 條零 Must:F-01 Should 文件 + F-02~F-05 Nice),user 拍板「全修」。
分支自 master `d199149b`(PR #255 merge 結果)開,worktree。

## 1. 五條處置 → commit

| # | 處置 | commit | 類 |
|---|---|---|---|
| F-03 | JSON null 歸欄缺(`None if raw is None else (str(raw) or None)`),空字串 / int 2 語意不變 | 329d820b(紅先行 0c62399f) | 🔴 fix |
| F-02 | 0/1/2 以外的值當日首見每值一則 WARNING「個股旗標未知值 %r(首見 <股號> <時刻>)」,同日同值不再印、換日重武裝;三桶字面不動 | 7265e6c3(紅先行 0c62399f) | 🟢 feat |
| F-04 / F-05 | 計數分支不再第三次算 `is_futures_key`;`_FLAG_STATS_FMT` 後補空行 | 14d88bd6 | 🔵 refactor |
| F-01 | CLAUDE §4 :520 與 verification §6.2 判準改「不限檔名、對訊息尾交易日、多次重啟多行相加」;pr-review 255 報告雙檔入 docs | 76d6e53e | chore(docs) |

## 2. Two-axis review(`code-review-round-1.json`;fixed point d199149b,opus × 2)

Standards 5(2 Should 3 Nice)/ Spec 2 Nice / 零 Must;白名單八項零破壞;全部接受 → 收修三筆:

| 條 | 處置 | commit | 類 |
|---|---|---|---|
| S-01 已知值集合同源 `_FLAG_SIDE`;S-02 = Spec-S-01 未知值種數上界 `_FLAG_UNKNOWN_CAP = 8` + 封口一則;S-05 測試 helper 去冗參數 | 紅先行一案(9 種 → 8 則 + 1 封口、第 10 種零輸出、換日再印) | a3ae8e1e | 🟢 feat+test |
| S-03 `is_spot` 一次算好、`arms_the_day = is_spot`(武裝政策漂了計數母體不跟);S-04 正規化式守門讀序 | 行為不變 | 3091804c | 🔵 refactor |
| Spec-S-02 判準前綴 `grep "個股旗標 0:"`(不與未知值 WARNING 互撞) | | 4f5cedb5 | chore(docs) |

## 3. 反向驗證(突變;還原後 sleep 1)

| 突變 | 預期 | 實測 | 還原後 |
|---|---|---|---|
| F-03 式子退回 `str(msg.get(..., "")) or None` | null 案紅 | **1 failed**(`test_null_flag_is_missing_not_the_string_none`) | 綠 |
| cap 改 `< 10**9`(上界失效) | cap 案紅 | **1 failed**(`test_unknown_flag_values_are_capped_per_day`) | 綠 |
| 兩突變同時,其餘 12 案 | 綠 | 12 passed | 14 passed |

紅先行:F-02 / F-03 兩案修前 **2 failed**(0c62399f);cap 案修前 **1 failed**。

## 4. 自動化 gate(worktree,主樹 venv 絕對路徑)

| gate | 結果 | exit |
|---|---|---|
| pytest 全量(F-01~F-05 收修後、two-axis 收修前) | **3460 passed, 3 skipped**(218.0 s) | 0 |
| pytest 全量(two-axis 收修後,最終) | **3461 passed, 3 skipped**(214.6 s;+1 = cap 案) | 0 |
| ruff check copycat tests | All checks passed! | 0 |
| ruff format --diff(兩支改到的 .py) | 2 files already formatted | 0 |
| pyright | 0 errors, 0 warnings, 0 informations | 0 |
| validate(指主樹 out/) | 42/42 PASS | 0 |
| 前端 | 零改動,不跑 npm gate | — |

## 5. 白名單(spec §4 + two-axis 兩軸各自讀 code 驗)

`side` wire 三值 / `snapshot()` 與打包 item 鍵集(全檔 `"flag"` 零命中)/ `_FLAG_STATS_FMT` 三桶字面(未知值只進「總」)/ `_eval_sweep` / 回補 / survivors / seq / `/api/health` / 期貨鍵不計數 / 既有 `TestSideFromFlag` 8 案 + `TestFlagStatsLog` 3 案斷言只增不改 / 空字串 → None、int 2 → "2" —— 零破壞。

## 6. 真實環境判準(prod 重啟後第一個交易日;dist 不變)

沿 `.claude/mod/stock-side-flag/verification.md` §6(已依 F-01 / Spec-S-02 改口):
1. `grep "個股旗標 0:" logs/server-*.log` 對訊息尾交易日:`0:` 桶接近 0、`欄缺` = 0(含 null)。
2. `grep 個股旗標未知值 logs/server-*.log` **零行**(非零 = 達錢值域漂了;≤ 8 則逐值 + 至多 1 則封口)。
3. 判定率說明列 ≥ 95%;VP / 外盤比 / 能量副圖有值;掃單簇 jsonl 量級同前。

**2026-09-16 實錄**(細節見 `.claude/mod/stock-side-flag/verification.md` §6 同日段):
1. 13:47 盤後:`(2026-09-16)` 只有 08:11:05 前一台關機那行(`0:0 / 欄缺 0 / 總 2`,盤前);08:11 這台當日行未印(server 未跨日),
   明早 stage2 補看,不算 FAIL。
2. PASS —— 13:47 `grep -c 個股旗標未知值 logs/server-20260916-0811.log` = 0(抓檔 84,834 則亦只有 1 / 2 兩值,含試撮與集合競價)。
3. PASS —— 78 檔 176,892 筆判定率 99.64%(neutral 0.36%),4908 頁判定率 100%;VP 兩色 / 外盤比 55.0% / 能量副圖有值;
   sweep_cluster 全日 66 筆 / policy 34(09-15 55 / 51);`佇列滿` 0。
