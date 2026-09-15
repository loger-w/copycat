# feat/tick-persist — verification(spec #257,tickets #258–#262)

## 1. Seams 與紅先行

| Seam | 測試檔 | 紅先行證據 |
|---|---|---|
| S1 盤中寫入(engine 餵訊息看 jsonl) | `tests/server/test_tick_persist.py` | T1 `ModuleNotFoundError` → 14 綠;T2 3 紅 → 18 綠;T3 4 紅(opener 缺 / disabled 建目錄 / 無 log 行 / 預算常數缺)→ 74 綠(含 shutdown_budget + main_wiring) |
| S2 轉檔 + 讀回(CLI 入口函式) | `tests/test_ticks_compact.py` | `ModuleNotFoundError` → 12 綠 |
| S3 排程(fake clock + fake 呼叫端) | `tests/server/test_ticks_compactor.py` | `ModuleNotFoundError` → 12 綠(含真子程序 1 條) |
| 不另設 seam | `tests/test_ticks_config.py`(breadth 同款 parity)、`test_shutdown_budget` 一條不等式、`test_main_wiring` prod 顯式傳 `ticks_config` | — |

## 2. 突變體閘(spec Testing Decisions)

| 突變 | 結果 |
|---|---|
| 簿列比較只比買一賣一(`key = (bids[:1], asks[:1])`) | 1 紅(`test_book_row_only_when_any_of_twenty_numbers_changes`),還原綠 |
| 去重鍵少 `code`(`key = ("", cum_vol)`) | 4 紅,還原綠 |
| 列數不符仍刪 jsonl(`if False:`) | 1 紅(`test_row_count_mismatch_keeps_jsonl_and_fails`),還原綠 |
| `msg_seq` 不遞增 | 由 `test_msg_seq_counts_every_message…`(`[1, 4]`)與 T2 `("book", 4)` 釘住;未另做突變 |

## 3. 自動化 gate(closeout 時填最終數字)

- pytest 全量:見 §5
- ruff check:All checks passed
- pyright:0 errors
- `copycat validate`:見 §5

## 4. 與 spec 的已知偏差(two-axis review 要看的)

1. **parquet 排序鍵 `(code, recv_ns, msg_seq)`,spec 寫 `(code, msg_seq)`**:`msg_seq` 是進程內序號、同日重啟歸零,單看會把重啟後的列排到前面;`recv_ns` 是牆鐘、跨重啟單調。`load_day` 同理以 `(recv_ns, msg_seq)` 排。
2. **13:45 多一步 `seal_day`**(spec 沒寫):Windows 開著的檔刪不掉,子程序「列數核對後刪 jsonl」會 PermissionError;seal 後該日遲到列丟棄並 WARNING 一次(13:30 收盤後現貨零訊息,丟的只是殘影)。
3. **每日「tick 存檔」行印三處**(13:45、換日 stage2 舊日、關機當日),spec 只寫 13:45;判準「同日取最後」。
4. **retry 語意**:失敗後再試 `retry_max` 次 → 最多 1 + 3 = 4 次呼叫,第 4 次失敗與放棄合成同一行 WARNING。
5. `to_stock_tick()` 的 `bid_milli / ask_milli` 由存下的五檔重算 `_best_limit`(第一個 > 0 的價),與 engine 當時的值相等(S1 round-trip 釘住)。

## 5. 收尾鏈數字(closeout 填)

- [ ] pytest 全量
- [ ] validate 42/42
- [ ] two-axis review round-1

## 6. 真環境判準(上線第一個交易日盤後;prod 重啟後生效,前端不用 build)

1. `grep "tick 存檔\|tick 轉檔" logs/server-<日>.log`:
   - 「tick 存檔 <日>:成交 n / 簿 m / 重複簿略過 d / flush k / 寫入失敗 e」至少一行(13:45 那行 + 關機那行),**寫入失敗 = 0**
   - 「tick 轉檔 <日>:jsonl n 列 → 成交 a 列 + 簿 b 列(去重 x、壞行 y),耗時 s 秒,MB」一行,**壞行 = 0**;`去重` 應 ≈ 當日重啟次數 × 每檔一筆
   - 零「tick 轉檔 … 失敗」/「放棄」;零「已轉檔封住,之後到達的列丟棄」以外的 tick WARNING
2. `ls data/ticks/`:`<日>.parquet` + `<日>-book.parquet` 在、`<日>.jsonl` 不在
3. `grep 佇列滿 logs/server-<日>.log` 仍為 0(存檔不影響 WS)
4. 開盤 09:00–09:01 從 parquet 算每秒則數與 09-14 手抓樣本(82 檔 49,610 則 / 60 s、峰值 2,932 則/秒)同量級:
   `python -c "import pyarrow.parquet as pq, collections; t=pq.read_table('data/ticks/<日>-book.parquet', columns=['recv_ns']); c=collections.Counter(v//1_000_000_000 for v in t.column('recv_ns').to_pylist()); print(sorted(c.items())[:90])"`
5. 體積覆核(上線第一週):jsonl 峰值大小(13:45 前 `ls -l`)、兩個 parquet 大小、簿列去重後列數 vs spec 估計(jsonl ~700 MB、簿 parquet 60–100 MB)
6. 關機 log「關機 stock 段」不因存檔變慢(健康路徑 1–3 s 內),「關機收尾」彙總行多 `ticks` 段
7. 手動重轉演練(任一天盤後):`python -m copycat ticks-compact --date <YYYYMMDD>` 對已轉過的日 → exit 2「jsonl 不存在」
