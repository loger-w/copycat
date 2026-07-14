> **性質註記**:本檔為實作驗證對照(guard/災難/鎖死懲罰全關),**事後加跑、不入 pre-registered 判定**。
> 用途:證明 1K 引擎在無風控下重現日線層證據(排除實作 bug),把正式判定的「否」歸因到風控語意。

# UC 池無條件 fade 複驗(1K + guard;noguard-full)

## 方法論

- 進場 = T+1 首根 1K bar open − slippage(悲觀);出場 = guard/災難/鎖死/收盤。
- 成本 0.1956%/來回;guard —、災難 —、鎖死懲罰 —。
- 共同期間:t1_date ≤ 2026-07-09(標記截止;期間外不進對照)。
- 判定式(pre-registered):(i) tiger 淨 EV>0 且日聚類 z 單尾 p < 0.05;(ii) tiger − (control+scan) ≥ 0.003 且日內分層洗牌單尾 p < 0.05。

### 四池(base config)

| pool | n | days | 淨EV | 日聚類SE | med | p_win | 再鎖率 | guard排除 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| tiger_2plus | 440 | 177 | 0.0110 | 0.0031 | 0.0125 | 0.58 | 22.3% | 0 |
| tiger_1 | 1298 | 226 | 0.0077 | 0.0021 | 0.0077 | 0.54 | 23.0% | 0 |
| control | 889 | 219 | 0.0058 | 0.0023 | 0.0034 | 0.52 | 25.4% | 0 |
| scan | 1812 | 242 | 0.0031 | 0.0017 | 0.0026 | 0.51 | 25.5% | 0 |

## 判定

- tiger(合併)淨 EV = 0.0085(日聚類 SE 0.0020,z = 4.17,單尾 p = 0.0000)
- tiger − 對照(control+scan)差 = 0.0045(日內分層洗牌 p = 0.0055;日×成交額雙重分層 p = 0.0000)
- tiger_mean_gt0: PASS
- p_positive_lt_threshold: PASS
- diff_ge_min_edge: PASS
- diff_p_lt_threshold: PASS

**UC 方向值得繼續:是**

## 敏感度(僅診斷,不入判定)

### stress

| pool | n | days | 淨EV | 日聚類SE | med | p_win | 再鎖率 | guard排除 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| tiger_2plus | 440 | 177 | 0.0089 | 0.0031 | 0.0097 | 0.57 | 22.3% | 0 |
| tiger_1 | 1298 | 226 | 0.0054 | 0.0021 | 0.0056 | 0.53 | 23.0% | 0 |
| control | 889 | 219 | 0.0040 | 0.0023 | 0.0016 | 0.51 | 25.4% | 0 |
| scan | 1812 | 242 | 0.0008 | 0.0017 | 0.0005 | 0.50 | 25.5% | 0 |

Universe counts:daytrade_uncovered_date=0, excluded_disposition=673, excluded_high_gap=799, excluded_low_gap=2785, excluded_missing_1k=43, excluded_no_daytrade=2161, included=4439, total=10900

