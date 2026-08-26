# fix/index-quote-no-filledtime — verification

branch 開在 worktree `C:\side-project\copycat-wt-idx`(主 tree 被另一 session 佔著,依 ops-discipline 不 switch)。
指令在 worktree 內以主 tree venv 跑(pytest 走 pyproject pythonpath,import 的是 worktree code)。

## 0. 症狀與定位(diagnosing-bugs Phase 1 之前的量測,2026-08-26 盤中)

- 12:21 `curl /api/index/state`:`trade_date=2026-08-26`、`twse.p=45811910`、`stale=False`、
  `twse.minutes` n=119(0901–**1059**),11:00–12:21 缺 82 鍵;`otc.minutes` n=199 到 1221。
- 當日 log `server-20260826-0851.log`:`index 分時自癒` 76 行,09:04 起每 7 分一發;換窗口那發有進展、同窗口那發
  「零新分鐘鍵」;10:56 `窗口階梯已達封頂(window_variant=17)` 之後全部無進展。IX0001 source 層 30 s 靜默閘 0 次(推播活著)。
- 12:23:45 **只聽不訂 probe**(LOGIN → SUB 連 SubPort topic "" → 讀 PUB 廣播 → LOGOUT → Disconnect,零 refcount 影響)
  收到 IX0001 原始 quote:
  ```
  {'Symbol': 'TC.S.TWS.IX0001', 'Security': 'IX0001', 'FilledTime': '0', 'PreciseTime': '0',
   'TradeDate': '20260826', 'TradingPrice': '45814.22', 'ReferencePrice': '45169.46', 'HighPrice': '45858.3', 'LowPrice': '44925.84'}
  ```
  → `minute_key('0', utc=True)` = `'000000'` → +8 → `0801` → 域外 → None → 分鐘不寫、`p` 照更新。

## 1. Phase 1 feedback loop(紅先行)

```
PYTHONDONTWRITEBYTECODE=1 ../copycat/.venv/Scripts/python -m pytest -q -p no:cacheprovider \
  tests/server/test_index_engine.py -k TestQuoteWithoutFilledTime
```
修前(commit f893d02b 當下):
```
E   AssertionError: assert {} == {'1006': 42039920}
FAILED ...::test_quote_without_filled_time_keys_minute_by_wall_clock
1 failed, 2 passed
```
紅在 user 症狀:`p` 更新了、`minutes` 空。另兩條(域外只寫現價 / 有 FilledTime 照舊)修前即綠 = 白名單鎖,不是紅。

## 2. Phase 2 最小重現

一個 engine、一筆 `FilledTime='0'` 的 quote、`now_fn` 釘 10:05:30。每個元素 load-bearing(拿掉 `'0'` 改成有值就綠)。

## 3. Phase 3 假說

單一假說,由 probe 直接證實(不是從 code 推的):**指數 quote 沒有時間欄位**。曾排除的替代解釋:
`_pending_date` 卡在換日 pending(否:自癒在 11:00 後照發,該條件要 `_pending_date is None`);TC4 推播死(否:`p` 在跳、
source 層靜默閘 0 次);1K 回補壞(部分:同窗口重抓回同一份是 08-14 已知的凍結 stub,但那是備援不是主路徑)。

## 4. 修法與 commit

| commit | 類 | 內容 |
|---|---|---|
| `f893d02b` | 🟢 | `TestQuoteWithoutFilledTime` 三條(1 紅 + 2 白名單) |
| `0fc698d9` | 🔴 | `_handle_quote`:`FilledTime` 去零為空 → `minute_key(self._now_fn().strftime("%H%M%S"), utc=False)`;有值照舊 UTC+8 |
| `a8ec7b54` | chore | tc4-market-facts「IX0001 quote 無時間欄位 + 只聽不訂 probe 寫法」;river_models docstring 更正 |
| `2afb5a1d` | chore | spec artifact |

## 5. 反向驗證(PASS)

`git stash push -- copycat/server/index_engine.py` → `1 failed, 2 passed`(紅回來)→ `git stash pop` → 綠。

## 6. Blast radius

- `minute_key(` callers:`_handle_quote`(本修)、`_apply_otc`(utc=False,MIS 快照自帶時戳,未動)、`breadth_engine.py:575`(utc=False,未動)。
- `FilledTime` 其他讀者:`corr_engine.py:264`(`minute_end_from_utc_hhmmss`,缺值已退回本機時鐘 — 同型既有做法)、
  `stock_models` / `stock_source`(個股 quote 的 FilledTime 正常,probe 同批看到 6182 / 3037 有值)。
- `_now_fn` 既有讀者:`_broadcast_loop` heal 判準、換日 08:30 門檻 — 型別 `datetime.time`,本修只多 `strftime`。

## 7. 自動化 gate(worktree HEAD 2afb5a1d)

| gate | 指令 | 結果 |
|---|---|---|
| 目標 | `pytest tests/server/test_index_engine.py tests/live` | 658 passed, 2 skipped(exit 0) |
| 全套 | `pytest -q` | FULL_SUITE_PLACEHOLDER |
| lint | `ruff check copycat tests` | All checks passed! |
| format(非 gate) | `ruff format --check` index_engine.py / test_index_engine.py | 與 master 基線相同(存量未格式化) |
| 型別 | `pyright` | 0 errors, 0 warnings |
| golden | `python -m copycat validate`(主 tree) | VALIDATE_PLACEHOLDER |
| 前端 | 未動 | n/a |

## 8. 真實環境(user 拍板:prod 收盤後才重啟)

- 重啟後(交易日 13:45 之後)看不到盤中效果;**次一交易日 09:10** `curl localhost:8721/api/index/state` 判準:
  `twse.minutes` 最大鍵 = 牆鐘分鐘(或 +1),`len(minutes)` ≈ 牆鐘 − 09:00;`grep "index 分時自癒" logs/server-*.log` 盤中應近零
  (開盤 1K timeout 那一發除外)。
- 畫面:台股綜合 tab 加權分時線整天連續、不再「卡一段跳一段」;重整分頁後線仍在(state 有分鐘)。

## 9. 留尾

- 08-13 fix/index-chart-empty-minutes 與 08-14 fix/index-heal-variant-escape 兩案都是在修「備援」(1K 自癒),主路徑從沒寫過分鐘 ——
  當時的真環境驗證只看到「線有出來」(自癒補的),沒量 `minutes` 最大鍵 vs 牆鐘。教訓入 ops-discipline:分時線類驗收要看
  **鍵 vs 牆鐘的差**,不是看線有沒有。
