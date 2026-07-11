# T+1 Fade(跟倒貨做空)GA 回測報告(2026-07-10)

## 方法論

- 方向:T+1 當沖先賣(空),當日回補。
- 進場:7 臂竭盡訊號偵測拉高翻轉,以觸發 bar close − 1 tick 悲觀賣出。
- 成本:手續費 0.001425 ×(1−0.84)× 2 + 當沖稅 0.0015 = **0.1956%**/來回。
- 強制風控:防鎖 guard 距漲停 3.0% 強制回補、災難停損 entry+4.0%(不入搜索,永遠生效)。
- 鎖死語意(悲觀化):全日鎖死 → 漲停 ×(1+0.03)回補。
- 當沖資格過濾:**生效**(處置期間 + 非當沖名單剔除)。
- 驗證:**walk-forward**(fold test 起點 2026-01-01, 2026-03-01, 2026-05-01, 2026-07-01;GA 只在 core、選擇只在 val,fold-test 不進任何選擇)。OOS = 各 fold top-1 串接。
- Universe counts:daytrade_uncovered_date=0, excluded_disposition=673, excluded_high_gap=799, excluded_low_gap=2785, excluded_missing_1k=43, excluded_no_daytrade=2161, included=4439, total=10900。

## 各臂結果

| arm | param | triggered | rules(過三道) | lock_events |
|---|---|---:|---:|---:|
| pullback | x_pct=0.003 | 4260 | 0 | 0 |
| pullback | x_pct=0.008 | 4155 | 0 | 0 |
| pullback | x_pct=0.015 | 3949 | 0 | 0 |
| inner_flip | n_window=3 y_threshold=0.5 | 4028 | 0 | 0 |
| inner_flip | n_window=5 y_threshold=0.55 | 3817 | 0 | 0 |
| inner_flip | n_window=8 y_threshold=0.6 | 3087 | 0 | 0 |
| pin_bar | w_threshold=0.4 near_pct=0.005 | 2482 | 0 | 0 |
| pin_bar | w_threshold=0.6 near_pct=0.005 | 1304 | 0 | 0 |
| pin_bar | w_threshold=0.7 near_pct=0.003 | 652 | 0 | 0 |
| vol_exhaust | z_ratio=0.3 near_pct=0.005 | 2285 | 0 | 0 |
| vol_exhaust | z_ratio=0.5 near_pct=0.005 | 3107 | 0 | 0 |
| vol_exhaust | z_ratio=0.7 near_pct=0.005 | 3412 | 0 | 0 |
| delta_flip |  | 1676 | 0 | 0 |
| vwap_break |  | 3955 | 0 | 0 |
| fixed_time | target_m=4 | 4439 | 0 | 0 |
| fixed_time | target_m=7 | 4439 | 0 | 0 |
| fixed_time | target_m=14 | 4439 | 0 | 0 |

## 存活規則

無規則通過三道驗證。

## 臂間對決(walk-forward OOS)

> ⚠ 17 臂多重比較 caveat:本表排序僅供展示;每臂代表規則於 val 側選定,但「挑最高的臂」仍消耗 OOS,不得以本表排名回頭調參(R4/R5)。

| rank | arm | param | test_exp | stress_exp | p_win | payoff | MDD | lock% | stress | best_stop | best_tp | n_test | fold+ |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|
| 1 | pin_bar | {'w_threshold': 0.6, 'near_pct': 0.005} | 0.0079 | 0.0063 | 0.41 | 2.5 | 0.1068 | 0.0% | PASS | True|True|True | tp=tp1|lookback=5.0|min_profit=0.003|recovery=0.4|z=4.0|tp=tp2|inner_flip=0.7|min_profit=0.003|new_low_count=2.0|trend_n=3.0|z=3.0|tp=tp1|lookback=10.0|min_profit=0.015|recovery=0.5|z=4.0 | 17 | 2/3 |
| 2 | pullback | {'x_pct': 0.008} | 0.0050 | 0.0029 | 0.49 | 1.3 | 0.3724 | 0.0% | PASS | False|True|False|False | tp=tp2|inner_flip=0.5|min_profit=0.003|new_low_count=3.0|trend_n=10.0|z=3.0|tp=tp1|lookback=3.0|min_profit=0.003|recovery=0.3|z=4.0|tp=tp2|inner_flip=0.65|min_profit=0.005|new_low_count=2.0|trend_n=3.0|z=2.0|tp=tp2|inner_flip=0.7|min_profit=0.003|new_low_count=2.0|trend_n=5.0|z=3.0 | 61 | 3/4 |
| 3 | fixed_time | {'target_m': 7} | 0.0044 | -0.0000 | 0.59 | 0.9 | 0.1779 | 0.0% | FAIL | False|False|False | tp=None|tp=tp1|lookback=10.0|min_profit=0.003|recovery=0.6|z=5.0|tp=tp6|distance=0.02 | 75 | 3/3 |
| 4 | pullback | {'x_pct': 0.003} | 0.0032 | 0.0014 | 0.50 | 1.2 | 0.4148 | 0.0% | PASS | False|False|False|False | tp=tp2|inner_flip=0.5|min_profit=0.003|new_low_count=3.0|trend_n=10.0|z=3.0|tp=None|tp=tp2|inner_flip=0.65|min_profit=0.005|new_low_count=3.0|trend_n=8.0|z=2.0|tp=tp1|lookback=3.0|min_profit=0.02|recovery=0.7|z=4.0 | 82 | 3/4 |
| 5 | pullback | {'x_pct': 0.015} | 0.0031 | 0.0015 | 0.53 | 1.0 | 0.4224 | 0.0% | PASS | False|False|True|True | tp=tp2|inner_flip=0.5|min_profit=0.003|new_low_count=2.0|trend_n=5.0|z=3.0|tp=tp2|inner_flip=0.5|min_profit=0.008|new_low_count=4.0|trend_n=8.0|z=2.0|tp=tp1|lookback=15.0|min_profit=0.003|recovery=0.7|z=2.5|tp=tp2|inner_flip=0.55|min_profit=0.003|new_low_count=2.0|trend_n=3.0|z=1.5 | 107 | 3/4 |
| 6 | delta_flip | {} | 0.0021 | -0.0011 | 0.57 | 0.8 | 0.2266 | 0.0% | FAIL | True|False|False|True | tp=tp1|lookback=3.0|min_profit=0.015|recovery=0.7|z=2.5|tp=tp4|min_profit=0.003|n=7.0|tp=tp2|inner_flip=0.7|min_profit=0.008|new_low_count=3.0|trend_n=5.0|z=1.5|tp=tp1|lookback=3.0|min_profit=0.003|recovery=0.7|z=4.0 | 56 | 2/4 |
| 8 | vwap_break | {} | -0.0013 | -0.0052 | 0.44 | 1.2 | 0.4112 | 0.0% | FAIL | False|False | tp=tp2|inner_flip=0.55|min_profit=0.008|new_low_count=4.0|trend_n=8.0|z=2.5|tp=tp1|lookback=5.0|min_profit=0.003|recovery=0.7|z=2.0 | 41 | 1/2 |
| 9 | vol_exhaust | {'z_ratio': 0.5, 'near_pct': 0.005} | -0.0016 | -0.0035 | 0.38 | 1.5 | 0.4066 | 0.0% | FAIL | True|True|False|False | tp=tp2|inner_flip=0.5|min_profit=0.003|new_low_count=3.0|trend_n=5.0|z=2.5|tp=None|tp=tp1|lookback=3.0|min_profit=0.015|recovery=0.3|z=5.0|tp=tp1|lookback=10.0|min_profit=0.015|recovery=0.6|z=2.0 | 72 | 1/4 |
| 10 | inner_flip | {'n_window': 8, 'y_threshold': 0.6} | -0.0021 | -0.0044 | 0.45 | 1.1 | 0.4084 | 0.0% | FAIL | False|True|False|False | tp=tp2|inner_flip=0.55|min_profit=0.003|new_low_count=4.0|trend_n=8.0|z=3.0|tp=tp1|lookback=5.0|min_profit=0.02|recovery=0.6|z=3.0|tp=tp1|lookback=3.0|min_profit=0.005|recovery=0.7|z=4.0|tp=tp9|min_profit=0.003 | 74 | 0/4 |
| 11 | vol_exhaust | {'z_ratio': 0.7, 'near_pct': 0.005} | -0.0034 | -0.0051 | 0.40 | 1.2 | 0.2950 | 0.0% | FAIL | True|True|False|True | tp=None|tp=tp4|min_profit=0.003|n=8.0|tp=tp2|inner_flip=0.5|min_profit=0.003|new_low_count=2.0|trend_n=3.0|z=2.5|tp=tp9|min_profit=0.005 | 40 | 2/4 |
| 12 | inner_flip | {'n_window': 3, 'y_threshold': 0.5} | -0.0041 | -0.0072 | 0.47 | 0.9 | 0.2755 | 0.0% | FAIL | True|False|False | tp=tp9|min_profit=0.003|tp=tp2|inner_flip=0.5|min_profit=0.003|new_low_count=4.0|trend_n=10.0|z=3.0|tp=tp6|distance=0.03 | 49 | 1/3 |
| 13 | inner_flip | {'n_window': 5, 'y_threshold': 0.55} | -0.0044 | -0.0057 | 0.44 | 1.0 | 0.4005 | 0.0% | FAIL | False|True|False|False | tp=tp2|inner_flip=0.5|min_profit=0.003|new_low_count=4.0|trend_n=10.0|z=2.0|tp=tp1|lookback=10.0|min_profit=0.003|recovery=0.5|z=5.0|tp=tp2|inner_flip=0.5|min_profit=0.003|new_low_count=3.0|trend_n=5.0|z=3.0|tp=tp2|inner_flip=0.5|min_profit=0.008|new_low_count=4.0|trend_n=10.0|z=3.0 | 84 | 1/4 |
| 14 | fixed_time | {'target_m': 4} | -0.0055 | -0.0073 | 0.39 | 1.2 | 0.5108 | 0.0% | FAIL | False|True|True|False | tp=tp2|inner_flip=0.5|min_profit=0.003|new_low_count=4.0|trend_n=5.0|z=2.5|tp=tp1|lookback=3.0|min_profit=0.02|recovery=0.5|z=2.5|tp=tp1|lookback=10.0|min_profit=0.015|recovery=0.5|z=5.0|tp=tp1|lookback=8.0|min_profit=0.003|recovery=0.6|z=5.0 | 61 | 1/4 |
| 15 | fixed_time | {'target_m': 14} | -0.0075 | -0.0081 | 0.43 | 0.7 | 0.2690 | 0.0% | FAIL | False|False|False | tp=None|tp=tp2|inner_flip=0.7|min_profit=0.003|new_low_count=4.0|trend_n=8.0|z=3.0|tp=tp2|inner_flip=0.6|min_profit=0.003|new_low_count=2.0|trend_n=3.0|z=2.5 | 30 | 0/3 |
| 16 | pin_bar | {'w_threshold': 0.4, 'near_pct': 0.005} | -0.0086 | -0.0102 | 0.25 | 1.5 | 0.2499 | 0.0% | FAIL | True|False | tp=tp1|lookback=8.0|min_profit=0.02|recovery=0.3|z=4.0|tp=tp1|lookback=3.0|min_profit=0.008|recovery=0.3|z=5.0 | 24 | 0/2 |

### 附錄:n_test < 15 的臂(樣本不足,不列入主表)

| rank | arm | param | test_exp | stress_exp | p_win | payoff | MDD | lock% | stress | best_stop | best_tp | n_test | fold+ |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|
| 7 | pin_bar | {'w_threshold': 0.7, 'near_pct': 0.003} | 0.0013 | -0.0008 | 0.23 | 3.7 | 0.0907 | 0.0% | FAIL | False|True | tp=tp2|inner_flip=0.5|min_profit=0.005|new_low_count=3.0|trend_n=5.0|z=2.0|tp=tp1|lookback=10.0|min_profit=0.015|recovery=0.4|z=5.0 | 13 | 1/2 |

## Walk-forward 分層(tiger vs control)

| arm | param | source | OOS exp | p_win | payoff | MDD | n |
|---|---|---|---:|---:|---:|---:|---:|
| pullback | {'x_pct': 0.003} | control | 0.0036 | 0.44 | 1.5 | 0.1368 | 18 |
| pullback | {'x_pct': 0.003} | scan | 0.0034 | 0.52 | 1.1 | 0.3144 | 58 |
| pullback | {'x_pct': 0.003} | tiger_csv | 0.0000 | 0.50 | 1.0 | 0.0968 | 6 |
| pullback | {'x_pct': 0.008} | control | 0.0007 | 0.38 | 1.7 | 0.1186 | 13 |
| pullback | {'x_pct': 0.008} | scan | 0.0048 | 0.51 | 1.2 | 0.3144 | 45 |
| pullback | {'x_pct': 0.008} | tiger_csv | 0.0267 | 0.67 | 1.4 | 0.0436 | 3 |
| pullback | {'x_pct': 0.015} | control | -0.0005 | 0.48 | 1.1 | 0.1906 | 23 |
| pullback | {'x_pct': 0.015} | scan | 0.0042 | 0.55 | 1.0 | 0.2822 | 80 |
| pullback | {'x_pct': 0.015} | tiger_csv | 0.0011 | 0.50 | 1.1 | 0.0436 | 4 |
| inner_flip | {'n_window': 3, 'y_threshold': 0.5} | control | 0.0155 | 0.62 | 1.9 | 0.0567 | 8 |
| inner_flip | {'n_window': 3, 'y_threshold': 0.5} | scan | -0.0057 | 0.44 | 1.0 | 0.2044 | 34 |
| inner_flip | {'n_window': 3, 'y_threshold': 0.5} | tiger_csv | -0.0190 | 0.43 | 0.2 | 0.1328 | 7 |
| inner_flip | {'n_window': 5, 'y_threshold': 0.55} | control | -0.0000 | 0.50 | 1.0 | 0.1850 | 20 |
| inner_flip | {'n_window': 5, 'y_threshold': 0.55} | scan | -0.0047 | 0.43 | 1.0 | 0.2706 | 56 |
| inner_flip | {'n_window': 5, 'y_threshold': 0.55} | tiger_csv | -0.0133 | 0.38 | 0.3 | 0.1077 | 8 |
| inner_flip | {'n_window': 8, 'y_threshold': 0.6} | control | 0.0037 | 0.50 | 1.3 | 0.1289 | 14 |
| inner_flip | {'n_window': 8, 'y_threshold': 0.6} | scan | -0.0010 | 0.45 | 1.2 | 0.4462 | 49 |
| inner_flip | {'n_window': 8, 'y_threshold': 0.6} | tiger_csv | -0.0139 | 0.36 | 0.5 | 0.1887 | 11 |
| pin_bar | {'w_threshold': 0.4, 'near_pct': 0.005} | control | -0.0318 | 0.00 | — | 0.0955 | 3 |
| pin_bar | {'w_threshold': 0.4, 'near_pct': 0.005} | scan | -0.0017 | 0.29 | 2.2 | 0.0982 | 14 |
| pin_bar | {'w_threshold': 0.4, 'near_pct': 0.005} | tiger_csv | -0.0125 | 0.29 | 0.9 | 0.0872 | 7 |
| pin_bar | {'w_threshold': 0.6, 'near_pct': 0.005} | control | 0.0456 | 0.67 | 7.2 | 0.0101 | 3 |
| pin_bar | {'w_threshold': 0.6, 'near_pct': 0.005} | scan | 0.0043 | 0.40 | 2.1 | 0.0547 | 10 |
| pin_bar | {'w_threshold': 0.6, 'near_pct': 0.005} | tiger_csv | -0.0115 | 0.25 | 1.1 | 0.0735 | 4 |
| pin_bar | {'w_threshold': 0.7, 'near_pct': 0.003} | control | -0.0080 | 0.00 | — | 0.0080 | 1 |
| pin_bar | {'w_threshold': 0.7, 'near_pct': 0.003} | scan | 0.0046 | 0.30 | 3.2 | 0.0700 | 10 |
| pin_bar | {'w_threshold': 0.7, 'near_pct': 0.003} | tiger_csv | -0.0103 | 0.00 | — | 0.0207 | 2 |
| vol_exhaust | {'z_ratio': 0.5, 'near_pct': 0.005} | control | 0.0004 | 0.44 | 1.3 | 0.1208 | 16 |
| vol_exhaust | {'z_ratio': 0.5, 'near_pct': 0.005} | scan | -0.0039 | 0.33 | 1.5 | 0.4015 | 49 |
| vol_exhaust | {'z_ratio': 0.5, 'near_pct': 0.005} | tiger_csv | 0.0095 | 0.57 | 1.3 | 0.0627 | 7 |
| vol_exhaust | {'z_ratio': 0.7, 'near_pct': 0.005} | control | -0.0011 | 0.45 | 1.1 | 0.0777 | 11 |
| vol_exhaust | {'z_ratio': 0.7, 'near_pct': 0.005} | scan | -0.0083 | 0.33 | 1.3 | 0.3046 | 27 |
| vol_exhaust | {'z_ratio': 0.7, 'near_pct': 0.005} | tiger_csv | 0.0514 | 1.00 | — | 0.0000 | 2 |
| delta_flip | {} | control | -0.0053 | 0.55 | 0.6 | 0.1724 | 11 |
| delta_flip | {} | scan | 0.0014 | 0.54 | 0.9 | 0.2202 | 37 |
| delta_flip | {} | tiger_csv | 0.0157 | 0.75 | 0.8 | 0.0893 | 8 |
| vwap_break | {} | control | -0.0020 | 0.56 | 0.7 | 0.0965 | 9 |
| vwap_break | {} | scan | -0.0023 | 0.41 | 1.2 | 0.2820 | 27 |
| vwap_break | {} | tiger_csv | 0.0049 | 0.40 | 2.1 | 0.0327 | 5 |
| fixed_time | {'target_m': 4} | control | -0.0147 | 0.26 | 1.2 | 0.3332 | 19 |
| fixed_time | {'target_m': 4} | scan | 0.0003 | 0.46 | 1.2 | 0.1749 | 39 |
| fixed_time | {'target_m': 4} | tiger_csv | -0.0228 | 0.33 | 0.6 | 0.0981 | 3 |
| fixed_time | {'target_m': 7} | control | -0.0003 | 0.60 | 0.7 | 0.1228 | 15 |
| fixed_time | {'target_m': 7} | scan | 0.0038 | 0.56 | 1.0 | 0.2018 | 45 |
| fixed_time | {'target_m': 7} | tiger_csv | 0.0107 | 0.67 | 1.1 | 0.0606 | 15 |
| fixed_time | {'target_m': 14} | control | -0.0071 | 0.55 | 0.4 | 0.1520 | 11 |
| fixed_time | {'target_m': 14} | scan | -0.0055 | 0.39 | 1.0 | 0.2264 | 18 |
| fixed_time | {'target_m': 14} | tiger_csv | -0.0486 | 0.00 | — | 0.0486 | 1 |

## Guard 敏感度(僅診斷;dist 選擇依據 = train/val,不得依此表調參)

| arm | param | guard dist | OOS exp | n |
|---|---|---:|---:|---:|
| pullback | {'x_pct': 0.003} | 0.02 | 0.0033 | 82 |
| pullback | {'x_pct': 0.003} | 0.03 | 0.0032 | 82 |
| pullback | {'x_pct': 0.003} | 0.04 | 0.0022 | 79 |
| pullback | {'x_pct': 0.008} | 0.02 | 0.0050 | 61 |
| pullback | {'x_pct': 0.008} | 0.03 | 0.0050 | 61 |
| pullback | {'x_pct': 0.008} | 0.04 | 0.0059 | 59 |
| pullback | {'x_pct': 0.015} | 0.02 | 0.0032 | 107 |
| pullback | {'x_pct': 0.015} | 0.03 | 0.0031 | 107 |
| pullback | {'x_pct': 0.015} | 0.04 | 0.0000 | 103 |
| inner_flip | {'n_window': 3, 'y_threshold': 0.5} | 0.02 | -0.0035 | 49 |
| inner_flip | {'n_window': 3, 'y_threshold': 0.5} | 0.03 | -0.0041 | 49 |
| inner_flip | {'n_window': 3, 'y_threshold': 0.5} | 0.04 | -0.0030 | 47 |
| inner_flip | {'n_window': 5, 'y_threshold': 0.55} | 0.02 | -0.0022 | 84 |
| inner_flip | {'n_window': 5, 'y_threshold': 0.55} | 0.03 | -0.0044 | 84 |
| inner_flip | {'n_window': 5, 'y_threshold': 0.55} | 0.04 | -0.0038 | 83 |
| inner_flip | {'n_window': 8, 'y_threshold': 0.6} | 0.02 | 0.0003 | 74 |
| inner_flip | {'n_window': 8, 'y_threshold': 0.6} | 0.03 | -0.0021 | 74 |
| inner_flip | {'n_window': 8, 'y_threshold': 0.6} | 0.04 | 0.0004 | 70 |
| pin_bar | {'w_threshold': 0.4, 'near_pct': 0.005} | 0.02 | -0.0100 | 24 |
| pin_bar | {'w_threshold': 0.4, 'near_pct': 0.005} | 0.03 | -0.0086 | 24 |
| pin_bar | {'w_threshold': 0.4, 'near_pct': 0.005} | 0.04 | -0.0005 | 15 |
| pin_bar | {'w_threshold': 0.6, 'near_pct': 0.005} | 0.02 | 0.0025 | 17 |
| pin_bar | {'w_threshold': 0.6, 'near_pct': 0.005} | 0.03 | 0.0079 | 17 |
| pin_bar | {'w_threshold': 0.6, 'near_pct': 0.005} | 0.04 | -0.0077 | 12 |
| pin_bar | {'w_threshold': 0.7, 'near_pct': 0.003} | 0.02 | -0.0021 | 13 |
| pin_bar | {'w_threshold': 0.7, 'near_pct': 0.003} | 0.03 | 0.0013 | 13 |
| pin_bar | {'w_threshold': 0.7, 'near_pct': 0.003} | 0.04 | 0.0167 | 7 |
| vol_exhaust | {'z_ratio': 0.3, 'near_pct': 0.005} | 0.02 | — | 0 |
| vol_exhaust | {'z_ratio': 0.3, 'near_pct': 0.005} | 0.03 | — | 0 |
| vol_exhaust | {'z_ratio': 0.3, 'near_pct': 0.005} | 0.04 | — | 0 |
| vol_exhaust | {'z_ratio': 0.5, 'near_pct': 0.005} | 0.02 | -0.0029 | 72 |
| vol_exhaust | {'z_ratio': 0.5, 'near_pct': 0.005} | 0.03 | -0.0016 | 72 |
| vol_exhaust | {'z_ratio': 0.5, 'near_pct': 0.005} | 0.04 | -0.0017 | 58 |
| vol_exhaust | {'z_ratio': 0.7, 'near_pct': 0.005} | 0.02 | -0.0041 | 40 |
| vol_exhaust | {'z_ratio': 0.7, 'near_pct': 0.005} | 0.03 | -0.0034 | 40 |
| vol_exhaust | {'z_ratio': 0.7, 'near_pct': 0.005} | 0.04 | -0.0037 | 35 |
| delta_flip | {} | 0.02 | 0.0020 | 56 |
| delta_flip | {} | 0.03 | 0.0021 | 56 |
| delta_flip | {} | 0.04 | 0.0035 | 56 |
| vwap_break | {} | 0.02 | 0.0018 | 41 |
| vwap_break | {} | 0.03 | -0.0013 | 41 |
| vwap_break | {} | 0.04 | 0.0010 | 35 |
| fixed_time | {'target_m': 4} | 0.02 | -0.0033 | 61 |
| fixed_time | {'target_m': 4} | 0.03 | -0.0055 | 61 |
| fixed_time | {'target_m': 4} | 0.04 | -0.0049 | 59 |
| fixed_time | {'target_m': 7} | 0.02 | 0.0045 | 75 |
| fixed_time | {'target_m': 7} | 0.03 | 0.0044 | 75 |
| fixed_time | {'target_m': 7} | 0.04 | 0.0030 | 74 |
| fixed_time | {'target_m': 14} | 0.02 | -0.0093 | 30 |
| fixed_time | {'target_m': 14} | 0.03 | -0.0075 | 30 |
| fixed_time | {'target_m': 14} | 0.04 | -0.0073 | 27 |

## 逼近漲停診斷(全 universe;P(鎖|逼近)與嘎空回落深度)

| dist | bucket | n | P(鎖) | P(回落) | 回落深度 med | p25 | p75 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0.02 | overall | 2371 | 45.7% | 54.3% | 5.38% | 3.50% | 7.93% |
| 0.02 | early_heavy | 337 | 42.7% | 57.3% | 4.63% | 3.23% | 6.72% |
| 0.02 | early_light | 936 | 44.7% | 55.3% | 5.72% | 3.93% | 7.95% |
| 0.02 | late_heavy | 242 | 32.6% | 67.4% | 2.80% | 1.87% | 3.94% |
| 0.02 | late_light | 38 | 21.1% | 78.9% | 2.63% | 1.39% | 4.22% |
| 0.03 | overall | 2860 | 37.9% | 62.1% | 5.21% | 3.28% | 7.75% |
| 0.03 | early_heavy | 270 | 27.0% | 73.0% | 4.27% | 2.66% | 6.15% |
| 0.03 | early_light | 1050 | 33.3% | 66.7% | 5.28% | 3.61% | 7.43% |
| 0.03 | late_heavy | 190 | 23.2% | 76.8% | 2.37% | 1.31% | 3.70% |
| 0.03 | late_light | 29 | 20.7% | 79.3% | 2.13% | 1.22% | 3.29% |
| 0.04 | overall | 3286 | 33.0% | 67.0% | 4.82% | 3.04% | 7.52% |
| 0.04 | early_heavy | 231 | 19.9% | 80.1% | 4.00% | 2.75% | 5.83% |
| 0.04 | early_light | 952 | 24.6% | 75.4% | 4.70% | 3.01% | 7.13% |
| 0.04 | late_heavy | 143 | 16.8% | 83.2% | 2.29% | 1.20% | 3.71% |
| 0.04 | late_light | 18 | 11.1% | 88.9% | 2.10% | 1.37% | 3.35% |

## 負結果

- pullback ({'x_pct': 0.003}): triggered=4260, rules=0
- pullback ({'x_pct': 0.008}): triggered=4155, rules=0
- pullback ({'x_pct': 0.015}): triggered=3949, rules=0
- inner_flip ({'n_window': 3, 'y_threshold': 0.5}): triggered=4028, rules=0
- inner_flip ({'n_window': 5, 'y_threshold': 0.55}): triggered=3817, rules=0
- inner_flip ({'n_window': 8, 'y_threshold': 0.6}): triggered=3087, rules=0
- pin_bar ({'w_threshold': 0.4, 'near_pct': 0.005}): triggered=2482, rules=0
- pin_bar ({'w_threshold': 0.6, 'near_pct': 0.005}): triggered=1304, rules=0
- pin_bar ({'w_threshold': 0.7, 'near_pct': 0.003}): triggered=652, rules=0
- vol_exhaust ({'z_ratio': 0.3, 'near_pct': 0.005}): triggered=2285, rules=0
- vol_exhaust ({'z_ratio': 0.5, 'near_pct': 0.005}): triggered=3107, rules=0
- vol_exhaust ({'z_ratio': 0.7, 'near_pct': 0.005}): triggered=3412, rules=0
- delta_flip ({}): triggered=1676, rules=0
- vwap_break ({}): triggered=3955, rules=0
- fixed_time ({'target_m': 4}): triggered=4439, rules=0
- fixed_time ({'target_m': 7}): triggered=4439, rules=0
- fixed_time ({'target_m': 14}): triggered=4439, rules=0

