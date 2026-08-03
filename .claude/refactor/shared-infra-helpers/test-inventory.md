# Test Inventory — refactor/shared-infra-helpers

Baseline:`pytest -q` = **612 passed**(2026-07-20,master fada3ca)。

## 三組目標的覆蓋現況

### 1) atomic write(27 處,13 檔)

| 站點 | 直接測試 | 間接覆蓋 |
|---|---|---|
| data/store.py:41 | tests/data/test_store.py(roundtrip) | replay golden |
| data/scan_events.py:38 | tests/data/test_scan_events.py(輸出內容) | — |
| data/label_events.py:107 | tests/data/test_label_events.py | — |
| data/backfill_finmind.py:100,162 | tests/data/test_backfill_finmind.py | — |
| data/backfill_daytrade.py:79,167 | tests/data/test_backfill_daytrade.py | — |
| data/backfill_brokers.py:150,161 | tests/data/test_backfill_brokers.py | — |
| backtest/pipeline.py:178,191,313,537 | tests/backtest/test_pipeline.py | test_cli_tday |
| backtest/fade_pipeline.py:732 | tests/test_cli_fade.py | — |
| backtest/fade_report.py:264,271 | tests/backtest/test_fade_report_round1.py | — |
| backtest/fade_anatomy.py:480,628 | tests/backtest/test_fade_anatomy.py | — |
| backtest/fade_entry_anatomy.py:441,595 | tests/backtest/test_fade_entry_anatomy.py | — |
| backtest/fade_diagnose.py:490,542 | tests/backtest/test_fade_diagnose.py | — |
| backtest/fade_cells.py:1174,1414,1892,1966,2058 | test_fade_cells*.py | — |

結論:各站點的**檔案輸出內容**皆有測試斷言(寫入路徑 + 內容),atomic 機制本身換 helper 後由內容測試保護。**覆蓋足夠,不需補 characterization**。

### 2) config JSON 載入器(3 份)

| Loader | 測試 | 涵蓋 unknown-key raise | 涵蓋 tuple 轉換 |
|---|---|---|---|
| strategy_config.load_config | tests/test_strategy_config.py | ✅ | ✅(lock_time_buckets) |
| backtest/config.load_backtest_config | tests/backtest/test_config.py | ✅ | ✅ |
| backtest/fade_config.load_fade_config | test_fade_round1~4_config.py | ✅ | ✅ + 事後 validate |

結論:**覆蓋足夠,不需補 characterization**。

### 3) 分位數 3 份 + _fmt 2 份 + _fmtq 2 份

| 函式 | 直接測試 | 演算法 |
|---|---|---|
| fade_anatomy._quantiles | ❌ 無 | `round(q*(n-1))`,回 p25/50/75/90 dict |
| fade_cells._pctl | ❌ 無 | `round(q*(n-1))`(與上同) |
| fade_diagnose._quantile | ❌ 無 | `int(p*n)` truncate(**不同**) |
| report._fmt | ❌ 無 | None→—;float→+.4f/.2f;int→str;str→原樣 |
| fade_report._fmt | ❌ 無 | float\|int→spec;其他→—(**int/str 語意不同**) |
| fade_anatomy._fmtq | ❌ 無 | 與 fade_entry_anatomy._fmtq **逐字相同** |
| fade_entry_anatomy._fmtq | ❌ 無 | 同上 |

結論:**全部零直接測試 → 必須先補 characterization**(🟢 獨立 commit),
特別要鎖住 round vs truncate 的分歧點(n=6, p=0.5:round 取 idx 2、truncate 取 idx 3)
與兩份 _fmt 對 int / str / None 的不同輸出。

範圍外(記 docs/next-time.md):backtest/search.py:_quantile(第四份,nearest-rank
`ceil(p*n)-1`,吃已排序輸入,契約不同)。
