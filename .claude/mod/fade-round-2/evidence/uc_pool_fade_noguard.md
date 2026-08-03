# UC 池無條件 fade 複驗(1K + guard;noguard)

## 方法論

- 進場 = T+1 首根 1K bar open − slippage(悲觀);出場 = guard/災難/鎖死/收盤。
- 成本 0.1956%/來回;guard —、災難 —、鎖死懲罰 —。
- 共同期間:t1_date ≤ 2026-06-25(標記截止;期間外不進對照)。
- 判定式(pre-registered):(i) tiger 淨 EV>0 且日聚類 z 單尾 p < 0.05;(ii) tiger − (control+scan) ≥ 0.003 且日內分層洗牌單尾 p < 0.05。

### 四池(base config)

| pool | n | days | 淨EV | 日聚類SE | med | p_win | 再鎖率 | guard排除 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| tiger_2plus | 148 | 94 | 0.0158 | 0.0046 | 0.0154 | 0.62 | 19.6% | 0 |
| tiger_1 | 399 | 166 | 0.0084 | 0.0029 | 0.0093 | 0.55 | 21.1% | 0 |
| control | 914 | 218 | 0.0062 | 0.0023 | 0.0042 | 0.53 | 25.5% | 0 |
| scan | 2762 | 237 | 0.0040 | 0.0017 | 0.0031 | 0.52 | 25.1% | 0 |

## 判定

- tiger(合併)淨 EV = 0.0104(日聚類 SE 0.0027,z = 3.83,單尾 p = 0.0001)
- tiger − 對照(control+scan)差 = 0.0059(日內分層洗牌 p = 0.0170;日×成交額雙重分層 p = 0.0010)
- tiger_mean_gt0: PASS
- p_positive_lt_threshold: PASS
- diff_ge_min_edge: PASS
- diff_p_lt_threshold: PASS

**UC 方向值得繼續:是**

## 敏感度(僅診斷,不入判定)

### stress

| pool | n | days | 淨EV | 日聚類SE | med | p_win | 再鎖率 | guard排除 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| tiger_2plus | 148 | 94 | 0.0140 | 0.0046 | 0.0134 | 0.61 | 19.6% | 0 |
| tiger_1 | 399 | 166 | 0.0065 | 0.0029 | 0.0070 | 0.54 | 21.1% | 0 |
| control | 914 | 218 | 0.0043 | 0.0023 | 0.0020 | 0.51 | 25.5% | 0 |
| scan | 2762 | 237 | 0.0017 | 0.0017 | 0.0011 | 0.51 | 25.1% | 0 |

Universe counts:daytrade_uncovered_date=0, excluded_disposition=673, excluded_high_gap=799, excluded_low_gap=2785, excluded_missing_1k=43, excluded_no_daytrade=2161, included=4439, total=10900

