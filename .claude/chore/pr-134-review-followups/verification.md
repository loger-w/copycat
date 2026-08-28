# verification — chore/pr-134-review-followups(2026-08-28)

分支 commit(依 08-28 拍板 (b) 引「第 n 筆 + subject」):第 1 筆 `chore(docs): /pr-review #134 報告落檔` → 第 2 筆 `test(capital): 紅先行 —— _note_price_type 本機日必須先於交易日求值` →
第 3 筆 `fix(capital): _note_price_type 先算本機日再算交易日,恢復改動前求值順序`(client.py 一檔,純 code + 註解)→ 第 4 筆 `refactor(tests): … 凍日界 _freeze_today …` →
第 5 筆 `chore(capital/docs): _Agg.date 語意降成「idx23 每筆覆寫、跨日是否變值未實證」…` → 第 6 筆 artifacts。

## 1. 自動化 gate(worktree `.worktrees/fix-n075-followups`,借主 tree `.venv`)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| 紅先行 | `pytest tests/capital/test_client.py -k evaluates_local_day`,client.py 換成 PR #134 版(fix 前) | **1 failed**(`calls == ["trade", "today"]`) | 1 |
| 綠 | 同上,HEAD | 1 passed(連同兩條 fuse 測試 3 passed) | 0 |
| capital 子集 | `pytest -q tests/capital` | 406 passed(#134 的 405 + 1 新) | 0 |
| 全量(review 前) | `pytest -q -p no:cacheprovider` | 3137 passed, 3 skipped(187 s) | 0 |
| 全量(review 收修 + 分支重寫後) | 同上 | **3137 passed, 3 skipped**(185 s) | 0 |
| lint | `ruff check copycat tests` | All checks passed | 0 |
| 型別 | `pyright` | 0 errors, 0 warnings | 0 |
| golden | `copycat validate`(主 tree) | 42/42 PASS | 0 |
| frontend | 未動 `frontend/` → 不跑 | — | — |

## 2. 反向驗證

- F-06:紅先行本身即 mutation —— 用 PR #134 版 `client.py` 跑新測試 1 failed,HEAD 1 passed;分支重寫後 `git diff <重寫前最終樹> HEAD` 為空。
- F-01 事實核:`RAW_N_PREORDER` 逐欄拆 `a[23]='20260610'`、`a[28]='PI'`、`a[29]='20260611'`、`a[31]='B'`(script assert;review S-P1 指出報告 F-07 的 idx28 為誤)。
- 殘留字面:`grep -rn "委託建立日\|最新事件日" copycat tests --include=*.py` → 只剩 `store.py:360` 條件句「idx23 不隨事件變 → 就是委託建立日」(刻意);`grep -E '[0-9a-f]{8}'` 於 `.claude/mod/n075-price-type-label-window/` 只剩 `1ce0c500`(master 祖先)。

## 3. 白名單逐條(change-spec §3)

| # | 既有行為 | 證據 |
|---|---|---|
| 1 | 保險絲 RuntimeError → WARNING + 只記本機日(#134 行為)不變 | 兩條 fuse 測試綠;`git diff` client.py 只 hoist 一行 + 傳參 |
| 2 | 唯一行為改動 = 求值順序恢復「本機日先」(= #134 前) | Spec 軸以 `git show e600f341:client.py:898-906` 核 #134 前順序一致;新測試釘住 |
| 3 | store 比對 / prune、`apply_reply`、三道下單閘零改動 | store.py / models.py / reply.py diff 全為註解 / docstring(兩軸皆核) |
| 4 | 既有 405 條斷言逐字不變 | 4 條既有測試只改 docstring;406 passed |

## 4. 真實環境

本分支唯一行為改動只在跨午夜一瞬可觀測(候選日集合),prod 不做觸發;健康路徑由 §3 + 全量測試覆蓋。
prod 8721 現跑 `1ce0c500`(00:44 起),不含 #134 與本分支。

## 5. 回頭核 goal(pr-134-review.md F-01–F-07)

| # | 落點 |
|---|---|
| F-01 / F-03 | `store.py:82` 註解 + `note_price_type` 段改「idx23 每筆覆寫、跨日是否變值未實證、兩種可能各自後果(含他方單入集母體變寬方向)」;`_price_type_of` / `_today_net_lots_locked` 同口徑;skill `tc4-market-facts` 條目改寫並加「第一筆跨日樣本即可定案」 |
| F-02 | `client.py:104` / `models.py:132` / `reply.py:55` / `test_reply.py:43` / `test_store.py:535` + `_trade_ymd` / `_note_price_type` docstring 六處同口徑 |
| F-04 | verification.md / JSON 全部改「PR #134 第 n 筆 + subject」,殘留 SHA 清光(review Spec P2 補抓 6 個) |
| F-05 | `_freeze_today` + 斷 `(_FIXED_YMD,)` |
| F-06 | `today = _today_ymd()` hoist(fix commit 純 code)+ 紅先行測試 |
| F-07 | next-time 08-28 節:seq 三日樣本前綴 2313091–2313092 < 2313209 < 2313211(三日樣本外推、機率趨近零);**idx29** 疑似交易日欄(報告寫 idx28 為誤);同一實驗順便定 idx23 跨日語意 |
| 順帶(Spec P3) | next-time :330 / :433 兩處舊句加「未實證」 |

## 6. 留尾

- Shotgun(review S-P3d):「idx23 未實證」口徑分佈十餘處;定案日以 `grep 未實證` 收斂,SoT = skill 條目。
- 已發布報告 `pr-134-review*.md` F-07 的 idx28 不回改(projection 合約),正確值 idx29 記於 skill / next-time / 本檔。
