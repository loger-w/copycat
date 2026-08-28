# chore/pr-134-review-followups — /pr-review #134 七條 finding 收修

日期:2026-08-28。來源:`docs/superpowers/specs/pr-134-review.md`(F-01–F-07,全 Nice / `auto-fix`,零 Must / Should)。
分支自 origin/master d34d372c。小活分流:無對外 API、無 migration。

## 1. 現況 vs 目標

| # | 現況 | 目標 |
|---|---|---|
| F-01 / F-03 | `store.py` docstring 把「`_Agg.date` = 最新事件日」當事實並推「沒拉寬窗」;`reply.py:55` 記同日 C/D 實測仍原單日期 —— 互斥並存 | 兩邊都降成機制描述:idx23 每筆回報覆寫、**跨日事件是否變值未實證**;兩種可能各自後果寫清(含他方單入集母體是變寬方向) |
| F-02 | `client.py:104` `_today_ymd`、`models.py:132` `OrderRecord.date`、`reply.py:55`、`test_reply.py:43`、`test_store.py:535` 仍寫「委託建立日」 | 六處(含 skill 條目)同一口徑 |
| skill | `tc4-market-facts` 群益節「最新事件日」條只推自覆寫機制 | 改成「覆寫機制 + 值是否變未實證 + idx29 疑似交易日欄(pr-134 報告寫 idx28 為誤,逐欄重數 idx28 恆 `PI`) + 第一筆跨日樣本即可定案」 |
| F-04 | `verification.md` / `code-review-round-1.json` 引 rebase 前 SHA | 改引「第 n 筆 + subject」(08-28 (b) 拍板) |
| F-05 | `test_submit_result_survives_trade_day_fuse` 未凍日界 | `_freeze_today` + 斷 `(_FIXED_YMD,)` |
| F-06 | `_note_price_type` 的 `_trade_ymd()` 提進 try 後先於 `_today_ymd()` 求值(#134 副作用) | `today = _today_ymd()` 提到 try 前,恢復原序;紅先行測試釘「本機日先」 |
| F-07 | next-time 08-28 節未引 06-10 真樣本 | 補 seq 全域遞增三日證據(06-10 / 08-26 / 08-27 前 7 位遞增)+ idx29 疑似交易日欄(pr-134 報告寫 idx28 為誤,逐欄重數 idx28 恆 `PI`) |

## 2. Caller map

- `_note_price_type`(三 caller 不變)、`_today_ymd` / `_trade_ymd`(唯一 caller `_note_price_type`,測試直呼)。
- `_Agg.date` / `OrderRecord.date` / `ReplyRecord.date`:只動註解 / docstring,零程式行。

## 3. 既有行為白名單

1. `_note_price_type` 記兩候選日 + 標的 + 方向;保險絲 RuntimeError → WARNING + 只記本機日(#134 行為)不變。
2. 唯一行為改動 = 求值順序恢復「本機日先、交易日後」(= #134 之前的順序;差異只在跨午夜一瞬)。
3. store 比對 / prune 規則、`apply_reply` 覆寫、三道下單閘零改動。
4. 測試:既有 405 條**斷言**逐字不變(4 條既有測試只改 docstring);F-05 只改一條測試的日界來源;新增一條求值順序測試。

## 4. Seams

- `tests/capital/test_client.py::test_note_price_type_evaluates_local_day_before_trade_day`(紅先行:pre-fix client.py 1 failed)
- `tests/capital/test_client.py::test_submit_result_survives_trade_day_fuse`(F-05 改日界來源,仍綠)
